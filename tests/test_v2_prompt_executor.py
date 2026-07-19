"""Focused tests for the live v2 PromptExecutor/output boundary."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
import comfymodal_runtime.modal_app as modal_app
from comfymodal_runtime.result_delivery import ConversionFailedError
from comfymodal_runtime.runtime_executor import ExecutionContext, RuntimeExecutor
from comfymodal_runtime.trace import RuntimeTrace


class _Executor:
    success = True
    history_result = {}

    def __init__(self):
        self.executed = []
        self.sync_called = False

    def reset(self):
        pass

    def execute(self, **kwargs):
        self.sync_called = True
        self.executed.append(kwargs)

    async def execute_async(self, **kwargs):
        self.executed.append(kwargs)


async def _validate_prompt(_prompt_id, _workflow, _extra):
    for node_spec in _workflow.values():
        assert isinstance(node_spec, dict)
        if "inputs" in node_spec:
            assert isinstance(node_spec["inputs"], dict)
    return True, {}, ["107"], {}


def test_v2_runner_uses_prompt_executor_and_live_registry_without_legacy_wrapper():
    registry = {
        "107": [
            {
                "filename": "production_req-1_107_0.png",
                "bytes": b"png-bytes",
                "node_id": "107",
                "output_key": "images",
                "mime_type": "image/png",
                "file_ext": ".png",
                "format": "original",
                "output_index": 0,
            },
        ],
    }
    registered = {}
    cleaned = []
    materialized_inputs = []
    fake_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: materialized_inputs.append(inputs),
        _register_production_request=lambda prompt_id, data: registered.update({prompt_id: data}),
        _cleanup_production_request=lambda prompt_id: cleaned.append(("request", prompt_id)),
        _cleanup_production_registry=lambda prompt_id: cleaned.append(("registry", prompt_id)),
        _pop_production_outputs=lambda _prompt_id: registry,
    )
    executor = _Executor()
    api = SimpleNamespace(
        _executor=executor,
        _wait_for_restore_preload_before_request=lambda wf: None,
        _preflight_before_prompt_execution=lambda wf: None,
        _preflight_already_ran=False,
        _repair_missing_workflow_nodes=lambda wf: {"missing_before": [], "missing_after": [], "blocked_by_mode": False},
    )
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = fake_module

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        input_images={"0.png": "dGVzdA=="},  # non-empty to exercise materialization span
        execution_options=ExecutionOptions(
            production_enabled=True,
            production_output_node_ids=("107",),
        ),
        production_report={
            "enabled": True,
            "output_node_ids": ["107"],
            "direct_output_rewritten_node_ids": ["107"],
        },
    )
    trace = RuntimeTrace(request_id="req-1", process="remote")
    context = ExecutionContext(request_id="req-1", trace=trace)

    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    assert result["images"][0]["data"]
    assert result["outputs"]["107"]["images"][0]["node_id"] == "107"
    assert registered["req-1"]["authorized_node_ids"] == ["107"]
    assert executor.executed[0]["prompt_id"] == "req-1"
    assert executor.sync_called is False
    assert cleaned == [("request", "req-1"), ("registry", "req-1")]

    # Verify all Phase 5 execution span events are present
    event_names = [event.name for event in trace.events]
    expected_spans = [
        "legacy_preload_check_start",
        "legacy_preload_check_end",
        "input_materialization_start",
        "input_materialization_end",
        "preflight_start",
        "preflight_end",
        "missing_node_repair_start",
        "missing_node_repair_end",
        "prompt_validation_start",
        "prompt_validation_end",
        "production_registry_setup_start",
        "production_registry_setup_end",
        "executor_reset_start",
        "executor_reset_end",
        "prompt_executor_start",
        "prompt_executor_end",
        "output_collect_start",
        "output_collect_end",
        "production_cleanup_start",
        "production_cleanup_end",
    ]
    for span in expected_spans:
        assert span in event_names, f"Missing span event: {span}"

    # Verify no two consecutive events have the same name (start/end pair count)
    for span_base in ["legacy_preload_check", "input_materialization", "preflight",
                       "missing_node_repair", "prompt_validation",
                       "production_registry_setup", "executor_reset",
                       "prompt_executor", "output_collect", "production_cleanup"]:
        start_count = event_names.count(f"{span_base}_start")
        end_count = event_names.count(f"{span_base}_end")
        assert start_count == end_count, (
            f"Mismatched start/end for {span_base}: {start_count} starts, {end_count} ends"
        )


def test_v2_fallback_conversion_failure_keeps_original_materialized_bytes():
    original = b"original-png"
    executor = _Executor()
    executor.history_result = {
        "outputs": {
            "107": {
                "images": [{
                    "filename": "out.png",
                    "data": base64.b64encode(original).decode("ascii"),
                    "type": "output",
                }],
            },
        },
    }
    api = SimpleNamespace(_executor=executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions.from_legacy(
            {"output_format": "webp_lossless"},
            default_production=False,
        ),
    )
    trace = RuntimeTrace(request_id="req-fallback", process="remote")
    context = ExecutionContext(request_id="req-fallback", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt)
    with patch.dict("sys.modules", {"execution": fake_execution}), patch.object(
        modal_app,
        "convert_output_items",
        side_effect=ConversionFailedError("converter unavailable"),
    ):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    assert base64.b64decode(result["images"][0]["data"]) == original
    assert result["output_attempts"][1]["metrics"]["conversion_fallback"] is True

    # Verify non-production spans are present, production spans are absent
    event_names = [event.name for event in trace.events]
    assert "legacy_preload_check_start" not in event_names  # no _wait_for_restore_preload_before_request on api
    assert "prompt_validation_start" in event_names
    assert "prompt_validation_end" in event_names
    assert "executor_reset_start" in event_names
    assert "executor_reset_end" in event_names
    assert "prompt_executor_start" in event_names
    assert "prompt_executor_end" in event_names
    assert "output_collect_start" in event_names
    assert "output_collect_end" in event_names
    assert "production_registry_setup_start" not in event_names  # production_enabled=False
    assert "production_cleanup_start" not in event_names  # production_enabled=False


def test_first_stream_event_contains_trace_id():
    """First stream event from run_plan_stream carries correlation identifiers."""
    executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: {"ok": True})
    entrypoint = modal_app.ModalRuntimeEntrypoint(executor=executor)

    async def run():
        messages = [
            message async for message in entrypoint.run_plan_stream(
                ExecutionPlan(workflow={"1": {}}).to_dict(),
                request_id="req-trace-id",
            )
        ]
        first = messages[0]
        assert first["type"] == "status"
        assert first["phase"] == "plan_received"
        assert first["request_id"] == "req-trace-id"
        assert isinstance(first.get("trace_id"), str)
        assert len(first["trace_id"]) > 0
        return messages

    messages = asyncio.run(run())
    assert messages[-1]["data"]["ok"] is True
