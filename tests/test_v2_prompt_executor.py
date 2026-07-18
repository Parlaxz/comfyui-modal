"""Focused tests for the live v2 PromptExecutor/output boundary."""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
import comfymodal_runtime.modal_app as modal_app
from comfymodal_runtime.result_delivery import ConversionFailedError
from comfymodal_runtime.runtime_executor import ExecutionContext
from comfymodal_runtime.trace import RuntimeTrace


class _Loop:
    def run_until_complete(self, awaitable):
        return asyncio.run(awaitable)


class _Executor:
    success = True
    history_result = {}

    def __init__(self):
        self.executed = []

    def reset(self):
        pass

    def execute(self, **kwargs):
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
    fake_module = SimpleNamespace(
        _register_production_request=lambda prompt_id, data: registered.update({prompt_id: data}),
        _cleanup_production_request=lambda prompt_id: cleaned.append(("request", prompt_id)),
        _cleanup_production_registry=lambda prompt_id: cleaned.append(("registry", prompt_id)),
        _pop_production_outputs=lambda _prompt_id: registry,
    )
    executor = _Executor()
    api = SimpleNamespace(_event_loop=_Loop(), _executor=executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = fake_module

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
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
        result = entrypoint._execute_v2_prompt_executor(plan, context, api, trace)

    assert result["images"][0]["data"]
    assert result["outputs"]["107"]["images"][0]["node_id"] == "107"
    assert registered["req-1"]["authorized_node_ids"] == ["107"]
    assert executor.executed[0]["prompt_id"] == "req-1"
    assert cleaned == [("request", "req-1"), ("registry", "req-1")]
    assert "prompt_executor_start" in [event.name for event in trace.events]
    assert "output_collect_end" in [event.name for event in trace.events]


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
    api = SimpleNamespace(_event_loop=_Loop(), _executor=executor)
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
        result = entrypoint._execute_v2_prompt_executor(plan, context, api, trace)

    assert base64.b64decode(result["images"][0]["data"]) == original
    assert result["output_attempts"][1]["metrics"]["conversion_fallback"] is True
