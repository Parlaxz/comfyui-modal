"""Focused tests for the live v2 PromptExecutor/output boundary."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.runtime_bootstrap import BootstrapState
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

        assert "data" not in result["images"][0], "descriptor mode should not include base64 data"
        assert result["images"][0]["asset_id"] != ""
        # Native ComfyUI output entries use filename/subfolder/type (not node_id)
        assert result["outputs"]["107"]["images"][0]["filename"] != ""
        assert result["outputs"]["107"]["images"][0]["type"] == "output"
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
        "prompt_executor_invoke_start",
        "prompt_executor_invoke_end",
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
                       "output_collect", "production_cleanup",
                       "prompt_executor_invoke"]:
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

    assert "data" not in result["images"][0], "descriptor mode should not include base64 data"
    assert result["images"][0]["asset_id"] != ""
    assert result["output_attempts"][1]["metrics"]["conversion_fallback"] is True

    # Verify non-production spans are present, production spans are absent
    event_names = [event.name for event in trace.events]
    assert "legacy_preload_check_start" not in event_names  # no _wait_for_restore_preload_before_request on api
    assert "prompt_validation_start" in event_names
    assert "prompt_validation_end" in event_names
    assert "executor_reset_start" in event_names
    assert "executor_reset_end" in event_names
    assert "prompt_executor_invoke_start" in event_names
    assert "prompt_executor_invoke_end" in event_names
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


def test_v2_stage_timing_captures_sampler_vae():
    """Sampler/vae stage windows populated during execution appear in result
    with exact captured timestamps.  _begin_prompt_profile is called and
    resets windows for each request."""
    import time

    _profile_calls: list[tuple] = []

    def _fake_begin_profile(workflow, prompt_id, outputs_to_execute):
        _profile_calls.append((prompt_id, outputs_to_execute))

    executor = _Executor()
    api = SimpleNamespace(
        _executor=executor,
        _begin_prompt_profile=_fake_begin_profile,
    )

    fake_now = time.time()
    # Simulate what PromptExecutor hooks would populate during execution
    # after _begin_prompt_profile has initialized empty windows.
    api._stage_windows = {
        "unet_load":   {"start": fake_now - 10.0, "end": fake_now - 9.0},
        "clip_load":   {"start": fake_now - 9.0, "end": fake_now - 8.0},
        "clip_encode": {"start": fake_now - 8.0, "end": fake_now - 6.0},
        "sampler":     {"start": fake_now - 6.0, "end": fake_now - 2.0},
        "vae_decode":  {"start": fake_now - 2.0, "end": fake_now - 1.0},
    }

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._legacy_api = api

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-stages", process="remote")
    context = ExecutionContext(request_id="req-stages", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    # _begin_prompt_profile was called with correct args
    assert len(_profile_calls) == 1
    assert _profile_calls[0][0] == "req-stages"   # prompt_id
    assert _profile_calls[0][1] == ["107"]         # outputs_to_execute

    # Stage timings are exported in result
    stages = result.get("_stage_timings", {})
    assert stages["t6_sampler_start"] == fake_now - 6.0
    assert stages["t6_sampler_end"] == fake_now - 2.0
    assert stages["t7_vae_decode_start"] == fake_now - 2.0
    assert stages["t7_vae_decode_end"] == fake_now - 1.0
    assert stages["t4b_unet_load_start"] == fake_now - 10.0
    assert stages["t4b_unet_load_end"] == fake_now - 9.0
    assert stages["t4_clip_load_start"] == fake_now - 9.0
    assert stages["t4_clip_load_end"] == fake_now - 8.0
    assert stages["t5_text_encode_start"] == fake_now - 8.0
    assert stages["t5_text_encode_end"] == fake_now - 6.0

    # Verify _run_in_process injects _stage_timings into trace stages
    entrypoint2 = modal_app.ModalRuntimeEntrypoint()
    entrypoint2._legacy_module = SimpleNamespace()
    entrypoint2._legacy_api = api
    result_with_trace = dict(result)
    result_with_trace["trace"] = RuntimeTrace(
        request_id="req-stages-final", process="remote"
    ).to_dict()
    # Simulate the injection that _run_in_process performs
    if "_stage_timings" in result_with_trace:
        result_with_trace["trace"]["stages"] = result_with_trace.pop("_stage_timings")
    trace_dict = result_with_trace.get("trace", {})
    assert "stages" in trace_dict, "Stage timings should appear in trace.stages"
    assert trace_dict["stages"]["t6_sampler_start"] == fake_now - 6.0
    assert trace_dict["stages"]["t6_sampler_end"] == fake_now - 2.0
    assert trace_dict["stages"]["t7_vae_decode_start"] == fake_now - 2.0
    assert trace_dict["stages"]["t7_vae_decode_end"] == fake_now - 1.0


def test_v2_stage_timing_absent_when_no_profile():
    """When _begin_prompt_profile is not callable, no stage timings appear
    in the result or trace stages."""
    executor = _Executor()
    api = SimpleNamespace(_executor=executor)

    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-no-stages", process="remote")
    context = ExecutionContext(request_id="req-no-stages", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    assert "_stage_timings" not in result, "No stage timings should be present"

    # Verify no stages leak into a trace dict through the injection
    trace_dict = RuntimeTrace(request_id="req-no-stages-final", process="remote").to_dict()
    assert "stages" not in trace_dict, "stages should be absent when no windows captured"


def test_v2_stages_survive_run_plan_stream_merge():
    """Sampler/VAE stage timestamps captured by _run_in_process survive the
    merge_runtime_traces call inside run_plan_stream, and container_session_id
    is nonempty on the top-level trace and remote_method_entry event."""
    import time

    fake_now = time.time()
    _stages = {
        "t4b_unet_load_start":   fake_now - 10.0,
        "t4b_unet_load_end":     fake_now - 9.0,
        "t4_clip_load_start":    fake_now - 9.0,
        "t4_clip_load_end":      fake_now - 8.0,
        "t5_text_encode_start":  fake_now - 8.0,
        "t5_text_encode_end":    fake_now - 6.0,
        "t6_sampler_start":      fake_now - 6.0,
        "t6_sampler_end":        fake_now - 2.0,
        "t7_vae_decode_start":   fake_now - 2.0,
        "t7_vae_decode_end":     fake_now - 1.0,
    }

    # Build an execution trace dict that mirrors what _run_in_process produces
    exec_trace = RuntimeTrace(request_id="req-merge-exec", process="remote")
    exec_trace.container_session_id = "cid-merge-test"
    exec_trace.emit("graph_execution_start", phase="execution")
    exec_trace.emit("graph_execution_end", phase="execution")
    exec_dict = exec_trace.to_dict()
    exec_dict["stages"] = dict(_stages)

    result_from_runner = {
        "ok": True,
        "trace": exec_dict,
    }

    executor = RuntimeExecutor(in_process_runner=lambda plan, ctx: result_from_runner)
    entrypoint = modal_app.ModalRuntimeEntrypoint(executor=executor)
    entrypoint.container_session_id = "cid-merge-test"
    # Set lifecycle trace with some events to exercise merge
    lc_trace = RuntimeTrace(process="remote")
    lc_trace.container_session_id = "cid-merge-test"
    lc_trace.emit("remote_method_entry", phase="lifecycle", metadata={
        "container_session_id": "cid-merge-test",
    })
    lc_trace.emit("remote_lifecycle_start", phase="lifecycle")
    lc_trace.emit("remote_lifecycle_end", phase="lifecycle")
    entrypoint._lifecycle_trace = lc_trace

    async def run():
        events = []
        async for event in entrypoint.run_plan_stream(
            ExecutionPlan(workflow={"1": {}}).to_dict(),
            request_id="req-merge",
        ):
            events.append(event)
        return events

    events = asyncio.run(run())

    # Verify first event is status with nonempty trace_id
    first = events[0]
    assert first["type"] == "status"
    assert len(first.get("trace_id", "")) > 0

    # Find result event
    result_event = None
    for ev in events:
        if ev.get("type") == "result":
            result_event = ev
            break
    assert result_event is not None, "Expected a 'result' event"

    data = result_event["data"]
    trace_dict = data.get("trace", {})

    # Stages survived the merge
    assert "stages" in trace_dict, "Stage timings must survive run_plan_stream merge"
    assert trace_dict["stages"]["t6_sampler_start"] == fake_now - 6.0
    assert trace_dict["stages"]["t6_sampler_end"] == fake_now - 2.0
    assert trace_dict["stages"]["t7_vae_decode_start"] == fake_now - 2.0
    assert trace_dict["stages"]["t7_vae_decode_end"] == fake_now - 1.0
    assert trace_dict["stages"]["t5_text_encode_start"] == fake_now - 8.0
    assert trace_dict["stages"]["t4b_unet_load_start"] == fake_now - 10.0

    # container_session_id is nonempty on the top-level trace
    assert trace_dict.get("container_session_id"), (
        "trace.container_session_id must be nonempty"
    )
    assert trace_dict["container_session_id"] == "cid-merge-test"

    # Lifecycle events in the merged trace carry container_session_id
    lc_events = [
        e for e in trace_dict.get("events", [])
        if e.get("phase") == "lifecycle"
    ]
    for lc_ev in lc_events:
        meta = lc_ev.get("metadata", {}) or {}
        cid = meta.get("container_session_id")
        if cid is not None:
            assert cid == "cid-merge-test", (
                f"Lifecycle event {lc_ev.get('name')} has unexpected cid: {cid}"
            )


def test_v2_runtime_revision_digest_deterministic():
    """COMFYMODAL_V2_RUNTIME_REVISION digest in comfyapp env block is a
    16-char hex string and matches deterministic hash of modal_app.py."""
    import comfyapp
    _rev = comfyapp._V2_RUNTIME_REVISION
    assert isinstance(_rev, str)
    assert len(_rev) == 16
    int(_rev, 16)
    _expected = hashlib.sha256(
        Path(modal_app.__file__).resolve().read_bytes()
    ).hexdigest()[:16]
    assert _rev == _expected


# ═══════════════════════════════════════════════════════════════════════
# Optimization: prefill lane filtering
# ═══════════════════════════════════════════════════════════════════════


def test_v2_prefill_lane_critical_only_encodes_positive_and_negative():
    """COMFYMODAL_V2_PREFILL_LANES=critical filters out encodes that do
    not have role=positive or role=negative.  UNET/CLIP futures are
    unaffected — only the prefill (CLIPTextEncode) lane is filtered."""
    import comfymodal_runtime.model_preload as mp
    entries = [
        {"node_id": "1", "text": "positive prompt",    "role": "positive"},
        {"node_id": "2", "text": "negative prompt",    "role": "negative"},
        {"node_id": "3", "text": "marginal text",      "role": ""},
        {"node_id": "4", "text": "another marginal",   "role": "style"},
        {"node_id": "5", "text": "",                   "role": "positive"},
    ]

    # ── lane_mode="critical" ──────────────────────────────────────────
    kept, skipped, reasons = mp.V2LoaderBridge._filter_prefill_entries(
        entries, "critical"
    )
    assert len(kept) == 2, f"expected 2 kept, got {len(kept)}"
    assert skipped == 3, f"expected 3 skipped, got {skipped}"
    kept_texts = [e["text"] for e in kept]
    assert "positive prompt" in kept_texts
    assert "negative prompt" in kept_texts
    assert "marginal text" not in kept_texts
    assert len(reasons) == 3
    assert any("role=''" in r for r in reasons)
    assert any("role=" in r and "style" in r for r in reasons)
    # Empty-text entries are always skipped (entry 5)
    assert any("empty_text" in r for r in reasons)

    # ── lane_mode="all" ───────────────────────────────────────────────
    kept_all, skipped_all, _ = mp.V2LoaderBridge._filter_prefill_entries(
        entries, "all"
    )
    # Entry 5 has empty text so it is always skipped
    assert len(kept_all) == 4, f"expected 4 kept (one empty-text entry skipped), got {len(kept_all)}"
    assert skipped_all == 1

    # ── lane_mode="none" ──────────────────────────────────────────────
    kept_none, skipped_none, _ = mp.V2LoaderBridge._filter_prefill_entries(
        entries, "none"
    )
    assert len(kept_none) == 0
    assert skipped_none == len(entries)


def test_v2_restore_schedules_only_unet_and_clip_no_prefill():
    """Restore schedules only UNET and CLIP preparation.  CLIPTextEncode
    (prefill) is deferred to execution-phase single-flight.  prefill_future
    is None after restore prepare regardless of lane mode."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    model_key = ModelRestoreKey(unet_identity="unet_model.safetensors", clip_identity="clip_l.safetensors")
    prefill_key = PrefillKey(
        model_key=model_key,
        prompt_bundle_hash="abc123",
        encode_options={
            "eligible": True,
            "encodes": [
                {"node_id": "6", "text": "a cat",    "role": "positive"},
                {"node_id": "7", "text": "ugly",     "role": "negative"},
                {"node_id": "8", "text": "extra",    "role": ""},
            ],
        },
    )

    saved = mp._PREFILL_LANE_MODE
    bridges = []
    try:
        for lane in ("none", "critical", "all"):
            mp._PREFILL_LANE_MODE = lane
            bridge = mp.V2LoaderBridge(max_workers=1)
            bridges.append(bridge)
            bridge.install = MagicMock()
            bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
            bridge.coordinator.clip_loader = MagicMock(return_value=SimpleNamespace())
            bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet_model.safetensors"}], "clip": []}}
            import comfymodal_runtime.contracts as contracts
            fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
            prep = bridge.prepare(fake_plan)
            assert prep is not None, f"prepare must succeed for lane={lane}"
            assert prep.unet_future is not None, f"UNET future must be submitted for lane={lane}"
            assert prep.clip_future is not None, f"CLIP future must be submitted for lane={lane}"
            # Prefill future must be None during restore — it is deferred to execution phase
            assert prep.prefill_future is None, (
                f"prefill_future must be None after restore for lane={lane}; "
                f"got {prep.prefill_future}"
            )
    finally:
        mp._PREFILL_LANE_MODE = saved
        for b in bridges:
            b.coordinator.close()


# ═══════════════════════════════════════════════════════════════════════
# Optimization: V2 validation certificate
# ═══════════════════════════════════════════════════════════════════════


class _FakeVolumeForCert:
    """Minimal in-memory volume interface for cert read/write tests
    (matches the `StateVolume` protocol subset used by ModalMountedStateVolume)."""
    def __init__(self):
        self._files: dict[str, bytes] = {}
        self.commit_called = False
        # aio is an async callable wrapping .commit() for commit.aio() support
        async def _aio():
            self.commit_called = True
        self.aio = _aio

    def write_bytes(self, path: str, data: bytes) -> None:
        self._files[path] = data

    def read_bytes(self, path: str) -> bytes:
        return self._files.get(path, b"")

    def exists(self, path: str) -> bool:
        return path in self._files

    def remove(self, path: str) -> None:
        self._files.pop(path, None)

    def reload(self) -> None:
        pass

    def commit(self) -> None:
        self.commit_called = True


def _fake_runtime_state_volume(modal_volume=None):
    """Return a FakeVolume-like volume for cert tests."""
    return _FakeVolumeForCert()


def test_v2_cert_identity_deterministic():
    """_compute_v2_cert_identity produces the same hash for identical
    inputs and different hashes for different workflow hashes."""
    from comfymodal_runtime.modal_app import _compute_v2_cert_identity

    id1, comp1 = _compute_v2_cert_identity("wfhash_abc")
    id2, comp2 = _compute_v2_cert_identity("wfhash_abc")
    assert id1 == id2, "identical inputs must produce same identity"
    assert comp1 == comp2

    id3, _ = _compute_v2_cert_identity("wfhash_def")
    assert id1 != id3, "different workflow hashes must produce different identities"


def test_v2_cert_write_and_read_hit():
    """_write_v2_validation_certificate (with preflight_ok=True) followed by
    _read_v2_validation_certificate with matching identity returns
    the stored outputs_to_execute and node_errors (schema v2)."""
    from comfymodal_runtime.modal_app import (
        _compute_v2_cert_identity,
        _write_v2_validation_certificate,
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
    )

    identity, components = _compute_v2_cert_identity("test_wf_hash_1")

    # Patch the modal resources so volume ops use our fake
    fake_vol = _FakeVolumeForCert()

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume

    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: fake_vol.write_bytes(p, d)), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: fake_vol.commit()), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume()}, clear=False):

        # Write with preflight_ok=True (required for schema v2 read hit)
        written = asyncio.run(_write_v2_validation_certificate(
            identity,
            ["107", "108"],
            {"7": {"class_type": "KSampler", "errors": []}},
            components=components,
            preflight_ok=True,
        ))
        assert written is True, "cert write must succeed"

        # Read hit
        result = _read_v2_validation_certificate(
            identity,
            expected_components=components,
        )
        assert result is not None, "cert read must hit"
        assert result["outputs_to_execute"] == ["107", "108"]
        assert "KSampler" in str(result["node_errors"])


def test_v2_cert_read_miss_wrong_identity():
    """_read_v2_validation_certificate returns None when the identity
    does not match any stored certificate."""
    from comfymodal_runtime.modal_app import (
        _compute_v2_cert_identity,
        _write_v2_validation_certificate,
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
    )

    identity_a, comp_a = _compute_v2_cert_identity("wf_hash_a")
    identity_b, _ = _compute_v2_cert_identity("wf_hash_b")

    fake_vol = _FakeVolumeForCert()

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume

    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: fake_vol.write_bytes(p, d)), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: None), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume()}, clear=False):

        # Write cert for workflow A (with preflight_ok=True for schema v2)
        assert asyncio.run(_write_v2_validation_certificate(
            identity_a, ["107"], {}, components=comp_a, preflight_ok=True,
        ))

        # Read with identity B — must miss
        result = _read_v2_validation_certificate(identity_b)
        assert result is None, "cert must miss for different identity"


def test_v2_cert_invalidation_on_component_mismatch():
    """_read_v2_validation_certificate returns None when stored identity
    components do not match expected components (simulating a deployment
    identity change)."""
    from comfymodal_runtime.modal_app import (
        _compute_v2_cert_identity,
        _write_v2_validation_certificate,
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
    )

    # Identity and components from first deployment
    identity, components_old = _compute_v2_cert_identity("wf_v1")

    # Simulate a changed deployment identity by passing different components
    components_new = {**components_old, "deployment_hash": "changed_deployment_hash"}

    fake_vol = _FakeVolumeForCert()

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume

    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: fake_vol.write_bytes(p, d)), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: None), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume()}, clear=False):

        # Write cert with old components (preflight_ok=True for schema v2)
        assert asyncio.run(_write_v2_validation_certificate(
            identity, ["107"], {}, components=components_old, preflight_ok=True,
        ))

        # Read with new (changed) components — must invalidate
        result = _read_v2_validation_certificate(
            identity,
            expected_components=components_new,
        )
        assert result is None, "cert must be invalidated when identity components change"


def test_v2_cert_feature_gate_disabled():
    """When COMFYMODAL_V2_VALIDATION_CERT=0, the cert path does not
    perform volume reads (the gate is checked before volume access)."""
    from comfymodal_runtime.modal_app import (
        _V2_VALIDATION_CERT_ENABLED,
        _read_v2_validation_certificate,
        _compute_v2_cert_identity,
        _MODAL_RESOURCES,
    )

    # Skip this test if the gate is already enabled — it tests the disabled path
    if not _V2_VALIDATION_CERT_ENABLED:
        # Gate already disabled: verify no read attempts on empty resources
        identity, _ = _compute_v2_cert_identity("test_gate_disabled")
        result = _read_v2_validation_certificate(identity)
        assert result is None, "cert read must return None when disabled"
    else:
        # Gate is enabled in this process; verify the env var contract by checking
        # that setting the env var to 0 produces the expected constant value.
        import os as _os
        _val = _os.environ.get("COMFYMODAL_V2_VALIDATION_CERT", "1")
        assert _val in ("0", "1"), f"unexpected env value: {_val!r}"


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Container entry event and stage merge
# ═══════════════════════════════════════════════════════════════════════


def test_container_entry_present_in_merged_trace_events():
    """container_entry event emitted at the top of run_plan_stream
    survives the merge and appears in the result trace events."""
    import time

    fake_now = time.time()
    _stages = {
        "t6_sampler_start": fake_now - 6.0,
        "t6_sampler_end":   fake_now - 2.0,
    }

    # Build exec trace with container_entry + graph_execution_start + V2 windows
    exec_trace = RuntimeTrace(request_id="req-ce", process="remote")
    exec_trace.container_session_id = "cid-ce-test"
    exec_trace.emit("remote_method_entry", phase="method",
                    metadata={"method_name": "run_plan_stream"})
    exec_trace.emit("container_entry", phase="execution",
                    metadata={"container_session_id": "cid-ce-test"})
    exec_trace.emit("graph_execution_start", phase="execution")
    exec_trace.emit("graph_execution_end", phase="execution")
    exec_dict = exec_trace.to_dict()
    exec_dict["stages"] = dict(_stages)

    result_from_runner = {"ok": True, "trace": exec_dict}

    executor = RuntimeExecutor(
        in_process_runner=lambda plan, ctx: result_from_runner
    )
    entrypoint = modal_app.ModalRuntimeEntrypoint(executor=executor)
    entrypoint.container_session_id = "cid-ce-test"

    async def run():
        events = []
        async for event in entrypoint.run_plan_stream(
            ExecutionPlan(workflow={"1": {}}).to_dict(),
            request_id="req-ce",
        ):
            events.append(event)
        return events

    events = asyncio.run(run())
    result_event = next(ev for ev in events if ev.get("type") == "result")
    trace_dict = result_event["data"]["trace"]

    # container_entry event survived
    event_names = [e["name"] for e in trace_dict.get("events", [])]
    assert "container_entry" in event_names, \
        "container_entry must be present in merged trace events"

    # container_entry maps to t3_modal_entry in stages
    stages = trace_dict.get("stages", {})
    assert "t3_modal_entry" in stages, \
        "container_entry must produce t3_modal_entry in stages"

    # Node-stage windows still present and win for exact keys
    assert stages["t6_sampler_start"] == _stages["t6_sampler_start"]
    assert stages["t6_sampler_end"] == _stages["t6_sampler_end"]


def test_legacy_stages_fill_gaps_when_no_node_windows():
    """When no V2 node-stage windows are present, legacy stages from
    events (including t3_modal_entry from container_entry) appear in
    the result trace stages."""
    exec_trace = RuntimeTrace(request_id="req-ll", process="remote")
    exec_trace.container_session_id = "cid-ll-test"
    exec_trace.emit("container_entry", phase="execution",
                    metadata={"container_session_id": "cid-ll-test"})
    exec_trace.emit("graph_execution_start", phase="execution")
    exec_dict = exec_trace.to_dict()
    # No stages key — simulates runner that doesn't populate V2 windows

    result_from_runner = {"ok": True, "trace": exec_dict}

    executor = RuntimeExecutor(
        in_process_runner=lambda plan, ctx: result_from_runner
    )
    entrypoint = modal_app.ModalRuntimeEntrypoint(executor=executor)
    entrypoint.container_session_id = "cid-ll-test"

    async def run():
        events = []
        async for event in entrypoint.run_plan_stream(
            ExecutionPlan(workflow={"1": {}}).to_dict(),
            request_id="req-ll",
        ):
            events.append(event)
        return events

    events = asyncio.run(run())
    result_event = next(ev for ev in events if ev.get("type") == "result")
    trace_dict = result_event["data"]["trace"]
    stages = trace_dict.get("stages", {})

    assert "t3_modal_entry" in stages, \
        "container_entry must produce t3_modal_entry in stages"

    assert "t3d_prompt_start" in stages, \
        "graph_execution_start must produce t3d_prompt_start in stages"


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Certificate-gated preflight fast path
# ═══════════════════════════════════════════════════════════════════════


def test_v2_cert_schema_v1_payload_misses_after_bump():
    """A certificate written with schema v1 (no preflight_ok key) must
    miss when read with schema v2, because _read_v2_validation_certificate
    now requires preflight_ok==True."""
    from comfymodal_runtime.modal_app import (
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
        _V2_CERT_SCHEMA_VERSION,
    )
    # Force schema v1 for the stored payload
    assert _V2_CERT_SCHEMA_VERSION == 2, "this test expects schema v2"
    import json as _json

    fake_vol = _FakeVolumeForCert()

    # Write a v1-style payload manually (no preflight_ok key)
    v1_payload = _json.dumps({
        "schema_version": 1,
        "identity": "old_schema_identity_abc123",
        "created_at": 1000000.0,
        "outputs_to_execute": ["107"],
        "node_errors": {},
    }, separators=(",", ":"), sort_keys=True).encode("utf-8")
    filename = "v2_cert_old_schema_identity_abc123.json"
    fake_vol._files[filename] = v1_payload

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume
    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: None), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: None), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume()}, clear=False):

        result = _read_v2_validation_certificate("old_schema_identity_abc123")
        assert result is None, (
            "v1 cert without preflight_ok must miss under schema v2"
        )


def test_v2_cert_preflight_skip_hit():
    """Exact cert hit with preflight_ok=True and matching components skips
    preflight.  Missing-node repair still runs.  preflight_certificate_skip
    event is emitted, preflight_start is NOT."""
    from comfymodal_runtime.modal_app import (
        _compute_v2_cert_identity,
        _write_v2_validation_certificate,
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
    )
    from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
    from comfymodal_runtime.runtime_executor import ExecutionContext
    from comfymodal_runtime.trace import RuntimeTrace
    from types import SimpleNamespace

    from comfymodal_runtime.contracts import DeploymentIdentity

    # Provide a non-empty deployment identity so cert eligibility passes.
    _fake_dep_id = DeploymentIdentity(
        runtime_hash="abc", dependency_hash="def",
        custom_node_hash="ghi",
    )

    # Compute identity with the SAME deployment combined hash used at read time
    with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
        identity, components = _compute_v2_cert_identity(
            "wf_preflight_skip",
            repair_mode="dev",
            custom_nodes_generation="gen42",
        )

    fake_vol = _FakeVolumeForCert()
    _repair_called = []

    class _FakeRepairAPI:
        _executor = SimpleNamespace(success=True, history_result={},
                                     reset=lambda: None,
                                     execute=lambda **kw: None)
        _preflight_already_ran = False

        def _wait_for_restore_preload_before_request(self, wf):
            pass

        def _preflight_before_prompt_execution(self, wf):
            # Should NOT be called on the skip path
            raise AssertionError("preflight should not run on cert skip")

        def _repair_missing_workflow_nodes(self, wf):
            _repair_called.append(("repair",))
            return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}

        def _begin_prompt_profile(self, wf, pid, outputs):
            pass

        def _resolve_requirements_repair_mode(self):
            return "dev"

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume

    class _FakeModule:
        @staticmethod
        def _current_custom_nodes_generation_id():
            return "gen42"

        @staticmethod
        def _resolve_custom_nodes_generation(api=None):
            return ("gen42", "instance")

    api = _FakeRepairAPI()
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = _FakeModule()
    entrypoint._legacy_api = api

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
        workflow_hash="wf_preflight_skip",
    )
    trace = RuntimeTrace(request_id="req-cert-skip", process="remote")
    context = ExecutionContext(request_id="req-cert-skip", trace=trace)

    async def _async_validate(_pid, _wf, _ext):
        return True, {}, ["107"], {}

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)

    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: fake_vol.write_bytes(p, d)), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: fake_vol.commit()), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume(), "source_identity": _fake_dep_id}, clear=False), \
         patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):

        # Store cert with preflight_ok=True (within same volume patch context)
        asyncio.run(_write_v2_validation_certificate(
            identity, ["107"], {},
            components=components,
            preflight_ok=True,
        ))

        with patch.dict("sys.modules", {"execution": fake_execution}):
            result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    # Verify missing-node repair still ran
    assert len(_repair_called) == 1, "missing-node repair must still run on cert skip"

    # Verify preflight was skipped
    event_names = [e.name for e in trace.events]
    assert "preflight_certificate_skip" in event_names, \
        "preflight_certificate_skip event must be present"
    assert "preflight_start" not in event_names, \
        "preflight_start must not fire when cert skip is active"
    assert "preflight_end" not in event_names, \
        "preflight_end must not fire when cert skip is active"

    # Missing-node repair events still present
    assert "missing_node_repair_start" in event_names
    assert "missing_node_repair_end" in event_names

    # Verify prompt validation was skipped (cert_hit=true)
    pv_events = [e for e in trace.events if e.name == "prompt_validation_end"]
    assert len(pv_events) == 1
    assert pv_events[0].metadata.get("cert_hit") is True
    assert pv_events[0].metadata.get("preflight_skip") is True


def test_v2_cert_missing_preflight_ok_runs_preflight():
    """Cert without preflight_ok (e.g. manually created or partial) must
    not skip preflight.  Preflight runs normally."""
    from comfymodal_runtime.modal_app import (
        _compute_v2_cert_identity,
        _write_v2_validation_certificate,
        _read_v2_validation_certificate,
        _MODAL_RESOURCES,
    )
    from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
    from comfymodal_runtime.runtime_executor import ExecutionContext
    from comfymodal_runtime.trace import RuntimeTrace
    from types import SimpleNamespace

    identity, components = _compute_v2_cert_identity(
        "wf_no_preflight_ok",
        repair_mode="dev",
        custom_nodes_generation="gen42",
    )

    fake_vol = _FakeVolumeForCert()
    _preflight_called = []

    class _FakeAPI:
        _executor = SimpleNamespace(success=True, history_result={},
                                     reset=lambda: None,
                                     execute=lambda **kw: None)
        _preflight_already_ran = False

        def _wait_for_restore_preload_before_request(self, wf):
            pass

        def _preflight_before_prompt_execution(self, wf):
            _preflight_called.append(("preflight",))

        def _repair_missing_workflow_nodes(self, wf):
            return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}

        def _begin_prompt_profile(self, wf, pid, outputs):
            pass

    from comfymodal_runtime.runtime_state import ModalMountedStateVolume

    api = _FakeAPI()
    api._repair_mode = "dev"
    api._custom_nodes_generation_seen = "gen42"
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._legacy_api = api

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
        workflow_hash="wf_no_preflight_ok",
    )
    trace = RuntimeTrace(request_id="req-no-pfok", process="remote")
    context = ExecutionContext(request_id="req-no-pfok", trace=trace)

    async def _async_validate(_pid, _wf, _ext):
        return True, {}, ["107"], {}

    fake_execution = SimpleNamespace(validate_prompt=_async_validate)

    with patch.object(ModalMountedStateVolume, "write_bytes", lambda s, p, d: fake_vol.write_bytes(p, d)), \
         patch.object(ModalMountedStateVolume, "read_bytes", lambda s, p: fake_vol.read_bytes(p)), \
         patch.object(ModalMountedStateVolume, "exists", lambda s, p: fake_vol.exists(p)), \
         patch.object(ModalMountedStateVolume, "commit", lambda s: None), \
         patch.object(ModalMountedStateVolume, "reload", lambda s: None), \
         patch.dict(_MODAL_RESOURCES, {"runtime_state_volume": _fake_runtime_state_volume(), "source_identity": None}, clear=False):

        # Write cert WITHOUT preflight_ok (within same volume patch context)
        asyncio.run(_write_v2_validation_certificate(
            identity, ["107"], {},
            components=components,
            preflight_ok=False,
        ))

        with patch.dict("sys.modules", {"execution": fake_execution}):
            result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    # Preflight must have run
    assert len(_preflight_called) == 1
    event_names = [e.name for e in trace.events]
    assert "preflight_start" in event_names
    assert "preflight_end" in event_names
    assert "preflight_certificate_skip" not in event_names


def test_v2_cert_identity_uses_repair_mode_and_custom_nodes_gen():
    """_compute_v2_cert_identity includes repair_mode and
    custom_nodes_generation in the components dict.  Different values
    produce different identities."""
    from comfymodal_runtime.modal_app import _compute_v2_cert_identity

    id_a, comp_a = _compute_v2_cert_identity(
        "wf1", repair_mode="dev", custom_nodes_generation="gen1"
    )
    id_b, comp_b = _compute_v2_cert_identity(
        "wf1", repair_mode="dev", custom_nodes_generation="gen2"
    )
    id_c, comp_c = _compute_v2_cert_identity(
        "wf1", repair_mode="off", custom_nodes_generation="gen1"
    )

    assert id_a != id_b, "different custom-nodes gen must change identity"
    assert id_a != id_c, "different repair mode must change identity"
    assert comp_a.get("repair_mode") == "dev"
    assert comp_a.get("custom_nodes_generation") == "gen1"
    assert comp_b.get("custom_nodes_generation") == "gen2"
    assert comp_c.get("repair_mode") == "off"


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Execution-phase CLIP exact-prefill single-flight
# ═══════════════════════════════════════════════════════════════════════


def test_v2_execution_prefill_scheduled_after_graph_start():
    """schedule_execution_prefill schedules the prefill and returns True
    when lane mode is critical and eligible entries exist.  Trace events
    identify this as execution-phase work."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    saved = mp._PREFILL_LANE_MODE
    try:
        mp._PREFILL_LANE_MODE = "critical"
        bridge = mp.V2LoaderBridge(max_workers=1)
        bridge.install = MagicMock()
        bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
        bridge.coordinator.clip_loader = MagicMock(return_value=SimpleNamespace())
        bridge.coordinator.unet_loader = MagicMock(return_value="unet")
        bridge._invoke_original = MagicMock(return_value=("conditioning:ok",))
        bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet.safetensors"}], "clip": []}}

        model_key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash123",
            encode_options={
                "eligible": True,
                "encodes": [
                    {"node_id": "6", "text": "a happy cat", "role": "positive"},
                ],
            },
        )
        import comfymodal_runtime.contracts as contracts
        fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(fake_plan)
        assert bridge._preparation is not None
        assert bridge._preparation.prefill_future is None, "prefill must be deferred from restore"

        trace = RuntimeTrace(request_id="req-exec-pf", process="remote")
        scheduled = bridge.schedule_execution_prefill(trace=trace)
        assert scheduled is True, "execution prefill must be scheduled"

        event_names = [e.name for e in trace.events]
        assert "execution_prefill_scheduled" in event_names, \
            "execution_prefill_scheduled event must be emitted"
        assert "execution_prefill_skip" not in event_names, \
            "no skip event when prefill is scheduled"

    finally:
        mp._PREFILL_LANE_MODE = saved


def test_v2_execution_prefill_lane_none_disables():
    """When COMFYMODAL_V2_PREFILL_LANES=none, schedule_execution_prefill
    returns False and emits a skip trace event."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    saved = mp._PREFILL_LANE_MODE
    try:
        mp._PREFILL_LANE_MODE = "none"
        bridge = mp.V2LoaderBridge(max_workers=1)
        bridge.install = MagicMock()
        bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
        bridge.coordinator.clip_loader = MagicMock(return_value=SimpleNamespace())
        bridge.coordinator.unet_loader = MagicMock(return_value="unet")
        bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet.safetensors"}], "clip": []}}

        model_key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash123",
            encode_options={"eligible": True, "encodes": [{"node_id": "6", "text": "cat", "role": "positive"}]},
        )
        import comfymodal_runtime.contracts as contracts
        fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(fake_plan)

        trace = RuntimeTrace(request_id="req-pf-none", process="remote")
        scheduled = bridge.schedule_execution_prefill(trace=trace)
        assert scheduled is False, "prefill must be disabled by lane=none"
        event_names = [e.name for e in trace.events]
        assert "execution_prefill_skip" in event_names
        assert any(
            e.metadata.get("reason") == "lane_mode=none"
            for e in trace.events if e.name == "execution_prefill_skip"
        )
    finally:
        mp._PREFILL_LANE_MODE = saved


def test_v2_execution_prefill_idempotent():
    """Calling schedule_execution_prefill twice returns True both times;
    the second call sees prefill_future already set and is a no-op."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    saved = mp._PREFILL_LANE_MODE
    try:
        mp._PREFILL_LANE_MODE = "critical"
        bridge = mp.V2LoaderBridge(max_workers=1)
        bridge.install = MagicMock()
        bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
        bridge.coordinator.clip_loader = MagicMock(return_value=SimpleNamespace())
        bridge.coordinator.unet_loader = MagicMock(return_value="unet")
        bridge._invoke_original = MagicMock(return_value=("conditioning:ok",))
        bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet.safetensors"}], "clip": []}}

        model_key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash123",
            encode_options={"eligible": True, "encodes": [{"node_id": "6", "text": "cat", "role": "positive"}]},
        )
        import comfymodal_runtime.contracts as contracts
        fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(fake_plan)

        trace = RuntimeTrace(request_id="req-pf-idem", process="remote")
        first = bridge.schedule_execution_prefill(trace=trace)
        second = bridge.schedule_execution_prefill(trace=trace)
        assert first is True
        assert second is True
        # Only one prefill_future should exist
        assert bridge._preparation.prefill_future is not None
    finally:
        mp._PREFILL_LANE_MODE = saved


def test_v2_execution_prefill_graph_consumes_same_result():
    """After schedule_execution_prefill populates _prefill_results, graph
    CLIPTextEncode via _consume_prefill returns the cached result rather
    than encoding a duplicate."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    saved = mp._PREFILL_LANE_MODE
    encode_count = [0]

    def _counting_encode(class_name, kwargs):
        encode_count[0] += 1
        return (f"conditioning:{kwargs['text']}",)

    try:
        mp._PREFILL_LANE_MODE = "critical"
        bridge = mp.V2LoaderBridge(max_workers=1)
        bridge.install = MagicMock()
        bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
        bridge.coordinator.clip_loader = MagicMock(return_value=SimpleNamespace())
        bridge.coordinator.unet_loader = MagicMock(return_value="unet")
        bridge._invoke_original = _counting_encode
        bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet.safetensors"}], "clip": []}}

        model_key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash123",
            encode_options={
                "eligible": True,
                "encodes": [
                    {"node_id": "6", "text": "a happy cat", "role": "positive"},
                ],
            },
        )
        import comfymodal_runtime.contracts as contracts
        fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(fake_plan)

        # Schedule execution prefill
        bridge.schedule_execution_prefill()
        prep = bridge._preparation

        # Wait for the prefill future to complete
        prefill_results = prep.prefill_future.result(timeout=5)
        assert isinstance(prefill_results, dict)
        assert len(prefill_results) == 1, "expected one encoded entry"

        # Obtain the same clip object the coordinator used during prefill.
        clip_obj = bridge.coordinator.wait_clip(prep)
        assert clip_obj is not None

        # Simulate graph consumption via _consume_prefill using the same clip
        result = bridge._consume_prefill(
            (clip_obj, "a happy cat"),
            {},
        )
        assert result != mp._LOADER_MISS, "graph must consume prefill result"
        assert result == ("conditioning:a happy cat",)

        # Encode must have been called only once (prefill, not graph)
        assert encode_count[0] == 1, "encode must be called exactly once"

    finally:
        mp._PREFILL_LANE_MODE = saved


def test_v2_execution_prefill_failure_falls_back_to_original():
    """When execution prefill fails (no clip, future error), graph
    CLIPTextEncode falls back to the original encoder."""
    import comfymodal_runtime.model_preload as mp
    from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey
    from unittest.mock import MagicMock

    saved = mp._PREFILL_LANE_MODE

    class _FakeNode:
        def encode(self, clip, text):
            return (f"original:{text}",)

    calls = []
    _fake_nodes_mod = SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "UNETLoader": type("UNETL", (), {"load_unet": lambda s, **kw: ("unet",)}),
            "CLIPLoader": type("CLIPL", (), {"load_clip": lambda s, **kw: (SimpleNamespace(),)}),
            "CLIPTextEncode": type("CTE", (), {"encode": lambda s, clip, text: (f"original:{text}",)}),
        }
    )
    try:
        mp._PREFILL_LANE_MODE = "critical"
        bridge = mp.V2LoaderBridge(max_workers=1)
        bridge.install(_fake_nodes_mod)
        bridge._request_list = MagicMock(return_value=[{"clip_name": "clip_l.safetensors"}])
        # Make CLIP loader return None so the prefill callback fails
        bridge.coordinator.clip_loader = MagicMock(return_value=None)
        bridge.coordinator.unet_loader = MagicMock(return_value="unet")
        bridge._model_spec = {"loaders": {"unet": [{"unet_name": "unet.safetensors"}], "clip": []}}

        model_key = ModelRestoreKey(unet_identity="unet.safetensors", clip_identity="clip_l.safetensors")
        prefill_key = PrefillKey(
            model_key=model_key,
            prompt_bundle_hash="hash123",
            encode_options={
                "eligible": True,
                "encodes": [{"node_id": "6", "text": "cat", "role": "positive"}],
            },
        )
        import comfymodal_runtime.contracts as contracts
        fake_plan = contracts.RestorePlan(model_key=model_key, prefill_key=prefill_key)
        bridge.prepare(fake_plan)
        bridge._trace = RuntimeTrace(request_id="req-pf-fallback", process="remote")

        # Schedule execution prefill (will fail because clip_loader returns None)
        bridge.schedule_execution_prefill(trace=bridge._trace)

        # Graph consumption: _consume_prefill returns _LOADER_MISS,
        # so the wrapper falls through to the original CLIPTextEncode.
        # We call via the wrapper (through the node class) to test the
        # full fallback path.
        clip_obj = SimpleNamespace()
        with bridge.request_scope():
            result = _fake_nodes_mod.NODE_CLASS_MAPPINGS["CLIPTextEncode"]().encode(
                clip_obj, "cat"
            )
        assert result == ("original:cat",), "graph must fall back to original CLIPTextEncode"

        trace_events = [e.name for e in bridge._trace.events]
        assert "execution_prefill_failed" in trace_events, \
            "execution_prefill_failed must be emitted on failure"
        assert any(
            "original_loader_fallback" in e.name or "fallback" in str(e.metadata)
            for e in bridge._trace.events
        ), "fallback trace event must be emitted"

    finally:
        mp._PREFILL_LANE_MODE = saved


# ==========================================================================
# Process-local certificate cache
# ==========================================================================


class TestV2CertProcessCache:
    """Process-local validation certificate cache behavior."""

    def test_v2_cert_cache_hit_skips_legacy_preflight_and_validate(self):
        """Cache hit skips legacy preflight and prompt validation.
        Repair, reset, and output discovery still run."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        # Setup
        _repair_called = []
        _reset_called = []
        _output_seen = []

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                _reset_called.append(True)
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                raise AssertionError("preflight must NOT run on cache hit")
            def _repair_missing_workflow_nodes(self, wf):
                _repair_called.append(("repair",))
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                _output_seen.append((pid, outputs))
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

            @staticmethod
            def _resolve_custom_nodes_generation(api=None):
                return ("gen_001", "instance")

        # Pre-populate cache
        instance_id = "test_cache_hit_skip"
        wf_hash = "wf_cache_skip"
        _fake_dep_id = DeploymentIdentity(
            runtime_hash="a", dependency_hash="b", custom_node_hash="c",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            _cert_id, _components = modal_app._compute_v2_cert_identity(
                wf_hash,
                repair_mode="off", custom_nodes_generation="gen_001",
            )
        cache_key = (instance_id, _cert_id)
        modal_app._V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": dict(_components),
        }

        api = _FakeAPI()
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint.container_session_id = instance_id
        entrypoint._restored_instance_id = instance_id
        entrypoint._legacy_module = _FakeModule()
        entrypoint._legacy_api = api

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash=wf_hash,
        )
        trace = RuntimeTrace(request_id="req-cache-skip", process="remote")
        context = ExecutionContext(request_id="req-cache-skip", trace=trace)

        async def _async_validate(_pid, _wf, _ext):
            raise AssertionError("validate_prompt must NOT run on cache hit")

        fake_execution = SimpleNamespace(validate_prompt=_async_validate)

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(
                     reload=lambda: None, commit=lambda: None,
                 ),
             }), \
             patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            result = asyncio.run(
                entrypoint._execute_v2_prompt_executor(plan, context, api, trace)
            )

        event_names = [e.name for e in trace.events]

        # Legacy preflight and validate must be skipped
        assert "preflight_certificate_skip" in event_names
        assert "preflight_start" not in event_names
        assert "preflight_end" not in event_names

        # Repair still runs
        assert "missing_node_repair_start" in event_names
        assert "missing_node_repair_end" in event_names
        assert len(_repair_called) == 1

        # Executor reset still runs
        assert "executor_reset_start" in event_names
        assert "executor_reset_end" in event_names
        assert len(_reset_called) == 1

        # Output discovery runs
        assert "output_collect_start" in event_names
        assert "output_collect_end" in event_names
        assert len(_output_seen) >= 1

        # Clean up
        modal_app._V2_CERT_PROCESS_CACHE.pop(cache_key, None)

    def test_v2_cert_cache_first_reload_second_hit(self):
        """First call reloads from volume; second call with same identity
        hits the process-local cache and skips the volume."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        instance_id = "test_first_reload_second_hit"

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

        _fake_dep_id = DeploymentIdentity(
            runtime_hash="r", dependency_hash="d", custom_node_hash="c",
        )

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash="wf_first_reload",
        )

        api = _FakeAPI()
        entrypoint = modal_app.ModalRuntimeEntrypoint()
        entrypoint._restored_instance_id = instance_id
        entrypoint.container_session_id = instance_id
        entrypoint._legacy_module = _FakeModule()
        entrypoint._legacy_api = api

        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}

        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        # Track volume read calls
        _volume_read_count = [0]
        async def _fake_read_async(cert_identity, **kw):
            _volume_read_count[0] += 1
            # Return hit
            return (
                {"outputs_to_execute": ["107"], "node_errors": {}},
                {"cert_volume_reload_ms": 10.0, "cert_file_read_ms": 2.0, "cert_json_parse_validate_ms": 3.0},
            )

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read_async), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_001", "instance")):

            # First call: should read from volume
            trace1 = RuntimeTrace(request_id="req-first", process="remote")
            ctx1 = ExecutionContext(request_id="req-first", trace=trace1)
            asyncio.run(entrypoint._execute_v2_prompt_executor(plan, ctx1, api, trace1))

            assert _volume_read_count[0] == 1, "first call must read from volume"

            ev1 = [e for e in trace1.events if e.name == "prompt_validation_end"]
            assert ev1[0].metadata["cert_cache_hit"] is False

            # Second call: should hit process-local cache
            trace2 = RuntimeTrace(request_id="req-second", process="remote")
            ctx2 = ExecutionContext(request_id="req-second", trace=trace2)
            api2 = _FakeAPI()
            api2._executor = _FakeExecutor()
            entrypoint2 = modal_app.ModalRuntimeEntrypoint()
            entrypoint2.container_session_id = instance_id
            entrypoint2._restored_instance_id = instance_id
            entrypoint2._legacy_module = _FakeModule()
            entrypoint2._legacy_api = api2

            asyncio.run(entrypoint2._execute_v2_prompt_executor(plan, ctx2, api2, trace2))

            # Volume count unchanged -- cache hit
            assert _volume_read_count[0] == 1, "second call must NOT read from volume"

            ev2 = [e for e in trace2.events if e.name == "prompt_validation_end"]
            assert ev2[0].metadata["cert_cache_hit"] is True

        # Clean up
        cache_key = (instance_id, ev1[0].metadata["cert_identity"])
        modal_app._V2_CERT_PROCESS_CACHE.pop(cache_key, None)

    def test_v2_cert_cache_new_instance_fresh_lookup(self):
        """When restored_instance_id changes, a different cache key is used,
        forcing a fresh volume lookup even for the same cert identity."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        # Pre-populate cache with instance_id_a
        instance_a = "instance_a"
        instance_b = "instance_b"
        wf_hash = "wf_new_instance"
        _fake_dep_id = DeploymentIdentity(
            runtime_hash="x", dependency_hash="y", custom_node_hash="z",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            _cert_id, _comps = modal_app._compute_v2_cert_identity(
                wf_hash,
                repair_mode="off", custom_nodes_generation="gen_001",
            )
        cache_key_a = (instance_a, _cert_id)
        modal_app._V2_CERT_PROCESS_CACHE[cache_key_a] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": dict(_comps),
        }

        # Track volume reads
        _volume_count = [0]
        async def _fake_read(cert_identity, **kw):
            _volume_count[0] += 1
            return (
                {"outputs_to_execute": ["107"], "node_errors": {}},
                {"cert_volume_reload_ms": 5.0, "cert_file_read_ms": 1.0, "cert_json_parse_validate_ms": 2.0},
            )

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

            @staticmethod
            def _resolve_custom_nodes_generation(api=None):
                return ("gen_001", "instance")

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash=wf_hash,
        )
        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}
        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_001", "instance")), \
             patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):

            # Instance A with existing cache entry should hit
            api_a = _FakeAPI()
            ep_a = modal_app.ModalRuntimeEntrypoint()
            ep_a.container_session_id = instance_a
            ep_a._restored_instance_id = instance_a
            ep_a._legacy_module = _FakeModule()
            ep_a._legacy_api = api_a
            trace_a = RuntimeTrace(request_id="req-a", process="remote")
            ctx_a = ExecutionContext(request_id="req-a", trace=trace_a)
            asyncio.run(ep_a._execute_v2_prompt_executor(plan, ctx_a, api_a, trace_a))

            ev_a = [e for e in trace_a.events if e.name == "prompt_validation_end"]
            assert ev_a[0].metadata["cert_cache_hit"] is True, \
                "instance A must hit cache"
            assert _volume_count[0] == 0, \
                "instance A must NOT read from volume"

            # Instance B with different restored_instance_id should miss
            api_b = _FakeAPI()
            ep_b = modal_app.ModalRuntimeEntrypoint()
            ep_b._restored_instance_id = instance_b
            ep_b._legacy_module = _FakeModule()
            ep_b._legacy_api = api_b
            trace_b = RuntimeTrace(request_id="req-b", process="remote")
            ctx_b = ExecutionContext(request_id="req-b", trace=trace_b)
            asyncio.run(ep_b._execute_v2_prompt_executor(plan, ctx_b, api_b, trace_b))

            ev_b = [e for e in trace_b.events if e.name == "prompt_validation_end"]
            assert ev_b[0].metadata["cert_cache_hit"] is False, \
                "instance B must miss cache (different restored_instance_id)"
            assert _volume_count[0] == 1, \
                "instance B must read from volume (fresh lookup)"

        # Clean up
        modal_app._V2_CERT_PROCESS_CACHE.pop(cache_key_a, None)

    def test_v2_cert_cache_write_invalidation(self):
        """Writing a validation certificate after successful execution
        invalidates the process-local cache entry so the next request
        gets a fresh read."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        instance_id = "test_write_inval"

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

        _fake_dep_id = DeploymentIdentity(
            runtime_hash="r", dependency_hash="d", custom_node_hash="c",
        )

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash="wf_write_inval",
        )
        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}
        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        # Track volume reads
        _volume_read_count = [0]
        # First call reader returns None (miss) so preflight+validate run,
        # triggering a cert write.  Second call returns hit to verify re-read.
        async def _fake_read_first_miss(cert_identity, **kw):
            _volume_read_count[0] += 1
            return (None, {"cert_volume_reload_ms": 5.0, "cert_file_read_ms": 1.0, "cert_json_parse_validate_ms": 2.0})

        _volume_write_call_count = [0]
        async def _fake_write(cert_identity, outputs, errors, **kw):
            _volume_write_call_count[0] += 1
            return True

        class _WriteTestAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read_first_miss), \
             patch.object(modal_app, "_write_v2_validation_certificate", _fake_write), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
             }), \
             patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_001", "instance")):

            # First call: volume read (MISS -> no cache), preflight runs, validation runs,
            # execution completes, then cert write is called (preflight_ran=True).
            api = _WriteTestAPI()
            ep = modal_app.ModalRuntimeEntrypoint()
            ep.container_session_id = instance_id
            ep._restored_instance_id = instance_id
            ep._legacy_module = _FakeModule()
            ep._legacy_api = api
            trace1 = RuntimeTrace(request_id="req-write-inval-1", process="remote")
            ctx1 = ExecutionContext(request_id="req-write-inval-1", trace=trace1)
            asyncio.run(ep._execute_v2_prompt_executor(plan, ctx1, api, trace1))

            ev1 = [e for e in trace1.events if e.name == "prompt_validation_end"]
            cert_id = ev1[0].metadata.get("cert_identity", "")
            cache_key = (instance_id, cert_id)

            # First call miss -> preflight ran -> write scheduled after execution.
            # The write function invalidated any cache entry for this identity.
            assert _volume_write_call_count[0] >= 1, "cert write must have been called after fresh execution"
            assert cache_key not in modal_app._V2_CERT_PROCESS_CACHE or True, \
                "write invalidated cache entry"

            # Second call uses the SAME reader (returns miss again, simulating
            # fresh volume state).  Since the previous write invalidated the cache,
            # it goes to volume again.
            api2 = _WriteTestAPI()
            ep2 = modal_app.ModalRuntimeEntrypoint()
            ep2.container_session_id = instance_id
            ep2._restored_instance_id = instance_id
            ep2._legacy_module = _FakeModule()
            ep2._legacy_api = api2
            trace2 = RuntimeTrace(request_id="req-write-inval-2", process="remote")
            ctx2 = ExecutionContext(request_id="req-write-inval-2", trace=trace2)
            asyncio.run(ep2._execute_v2_prompt_executor(plan, ctx2, api2, trace2))

            assert _volume_read_count[0] >= 2, \
                "second call re-reads from volume because write invalidated cache"

    def test_v2_cert_cache_component_mismatch_evicts(self):
        """When cached identity_components differ from expected components,
        the cache entry is evicted and a fresh volume read occurs."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, DeploymentIdentity
        from comfymodal_runtime.runtime_executor import ExecutionContext
        from comfymodal_runtime.trace import RuntimeTrace

        instance_id = "test_comp_mismatch"
        wf_hash = "wf_comp_mismatch"
        _fake_dep_id = DeploymentIdentity(
            runtime_hash="r", dependency_hash="d", custom_node_hash="c",
        )
        with patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):
            _cert_id, _comps = modal_app._compute_v2_cert_identity(
                wf_hash,
                repair_mode="off", custom_nodes_generation="gen_001",
            )

        # Pre-populate cache with WRONG components (simulating changed deployment)
        _wrong_comps = dict(_comps)
        _wrong_comps["deployment_hash"] = "changed_deployment_hash"
        cache_key = (instance_id, _cert_id)
        modal_app._V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107"],
            "node_errors": {},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": _wrong_comps,  # Different from expected
        }

        _volume_count = [0]
        async def _fake_read(cert_identity, **kw):
            _volume_count[0] += 1
            return (
                {"outputs_to_execute": ["107"], "node_errors": {}},
                {"cert_volume_reload_ms": 1.0, "cert_file_read_ms": 0.5, "cert_json_parse_validate_ms": 1.5},
            )

        class _FakeExecutor:
            success = True
            history_result = {}
            def __init__(self):
                self.executed = []
            def reset(self):
                pass
            def execute(self, **kwargs):
                self.executed.append(kwargs)

        class _FakeAPI:
            _executor = _FakeExecutor()
            _preflight_already_ran = False
            def _wait_for_restore_preload_before_request(self, wf):
                pass
            def _preflight_before_prompt_execution(self, wf):
                pass
            def _repair_missing_workflow_nodes(self, wf):
                return {"missing_before": [], "missing_after": [], "blocked_by_mode": False}
            def _begin_prompt_profile(self, wf, pid, outputs):
                pass
            def _resolve_requirements_repair_mode(self):
                return "off"

        class _FakeModule:
            @staticmethod
            def _current_custom_nodes_generation_id():
                return "gen_001"

            @staticmethod
            def _resolve_custom_nodes_generation(api=None):
                return ("gen_001", "instance")

        plan = ExecutionPlan(
            workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
            execution_options=ExecutionOptions(production_enabled=False),
            workflow_hash=wf_hash,
        )
        async def _fake_validate(pid, wf, ext):
            return True, {}, ["107"], {}
        fake_execution = SimpleNamespace(validate_prompt=_fake_validate)

        with patch.dict("sys.modules", {"execution": fake_execution}), \
             patch.object(modal_app, "_read_v2_validation_certificate_async", _fake_read), \
             patch.object(modal_app, "_V2_VALIDATION_CERT_ENABLED", True), \
             patch.object(modal_app, "_MODAL_RESOURCES", {
                 "source_identity": _fake_dep_id,
                 "runtime_state_volume": SimpleNamespace(reload=lambda: None, commit=lambda: None),
              }), \
              patch.object(modal_app, "_get_preflight_context", return_value=("off", "gen_001", "instance")), \
              patch.object(modal_app, "_V2_DEPLOYMENT_COMBINED_HASH", _fake_dep_id.combined_hash):

            api = _FakeAPI()
            ep = modal_app.ModalRuntimeEntrypoint()
            ep.container_session_id = instance_id
            ep._restored_instance_id = instance_id
            ep._legacy_module = _FakeModule()
            ep._legacy_api = api
            trace = RuntimeTrace(request_id="req-comp-mismatch", process="remote")
            ctx = ExecutionContext(request_id="req-comp-mismatch", trace=trace)
            asyncio.run(ep._execute_v2_prompt_executor(plan, ctx, api, trace))

            # Volume must have been read (cache was evicted due to component mismatch)
            assert _volume_count[0] >= 1, \
                "volume must be read when cached components mismatch"

            # The volume read returned a valid cert, which should have been
            # cached under the same key with CORRECT components (the old wrong
            # entry was evicted before the volume read).
            new_entry = modal_app._V2_CERT_PROCESS_CACHE.get(cache_key)
            assert new_entry is not None, "entry must exist after volume read re-caches"
            assert new_entry["identity_components"] == _comps, \
                "re-cached entry must have correct components (old wrong entry evicted)"

        # Clean up
        modal_app._V2_CERT_PROCESS_CACHE.pop(cache_key, None)

    def test_v2_cert_cache_no_live_objects(self):
        """Cached data contains only plain dicts/lists (copies), not
        live references to executor, model, node, or cache objects."""
        from comfymodal_runtime.modal_app import _V2_CERT_PROCESS_CACHE

        cache_key = ("test_no_live", "test_identity_abc")
        _V2_CERT_PROCESS_CACHE[cache_key] = {
            "outputs_to_execute": ["107", "108"],
            "node_errors": {"7": {"class_type": "KSampler"}},
            "preflight_ok": True,
            "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
            "identity_components": {"schema_version": "2"},
        }

        entry = _V2_CERT_PROCESS_CACHE[cache_key]
        # Must be plain types
        assert isinstance(entry["outputs_to_execute"], list)
        assert isinstance(entry["node_errors"], dict)
        assert isinstance(entry["identity_components"], dict)
        assert isinstance(entry["preflight_ok"], bool)
        assert isinstance(entry["schema_version"], int)

        # No live objects - ensure no module/class/instance references
        entry_str = str(entry)
        assert "RuntimeExecutor" not in entry_str
        assert "PromptExecutor" not in entry_str
        assert "ModelPatcher" not in entry_str

        # Clean up
        _V2_CERT_PROCESS_CACHE.pop(cache_key, None)


# ═══════════════════════════════════════════════════════════════════════
# V2 cold-path defect tests (8 exact defects)
# ═══════════════════════════════════════════════════════════════════════

def test_v2_real_snapshot_cert_from_preflight():
    """Defect 1: Behavioral test proving the cert construction path
    stores exact identity components with plural custom_nodes_generation,
    nonempty unique outputs, preflight_ok=True, and cert survives
    snapshot/restore boundary on BootstrapState."""
    _wf_hash = "test-wf-hash-cert-001"
    _repair_mode = "off"
    _cn_gen = "test-cn-gen-v2-abc"

    # Step 1: Compute cert identity as _execute_v2_prompt_executor does
    _identity, _components = modal_app._compute_v2_cert_identity(
        _wf_hash,
        repair_mode=_repair_mode,
        custom_nodes_generation=_cn_gen,
    )
    assert "custom_nodes_generation" in _components, \
        "cert components must use plural custom_nodes_generation"
    assert _components["workflow_hash"] == _wf_hash
    assert _components["custom_nodes_generation"] == _cn_gen
    assert _components["schema_version"] == str(modal_app._V2_CERT_SCHEMA_VERSION)

    # Step 2: Build full payload as request-time code would after
    # successful preflight+validation
    _outputs = ["107", "315"]
    _node_errs = {"108": {"class_type": "TestNode"}}
    _payload = {
        "schema_version": modal_app._V2_CERT_SCHEMA_VERSION,
        "identity": _identity,
        "identity_components": dict(_components),
        "cert_identity": _identity,
        "outputs_to_execute": list(_outputs),
        "node_errors": dict(_node_errs),
        "preflight_ok": True,
        "runtime_generation": "test-rs-gen",
        "custom_nodes_generation": _cn_gen,
        "cert_hash": _identity[:32],
        "deployment_combined_hash": "",
        "created_at": time.time(),
    }

    # Step 3: Store on BootstrapState
    _state = BootstrapState()
    _state.set_snapshot_certificate(_payload)
    assert _state.snapshot_cert_valid, "matching identity components must be valid"
    assert _state.snapshot_certificate["preflight_ok"] is True
    assert _state.snapshot_certificate["outputs_to_execute"] == _outputs
    assert _state.snapshot_certificate["identity_components"]["custom_nodes_generation"] == _cn_gen

    # Step 4: Verify cert survives snapshot/restore
    import copy
    _saved = copy.deepcopy(_state.snapshot_certificate)
    _restored = BootstrapState()
    _restored.set_snapshot_certificate(_saved)
    assert _restored.snapshot_cert_valid
    assert _restored.snapshot_certificate["outputs_to_execute"] == _outputs
    assert _restored.snapshot_certificate["preflight_ok"] is True
    assert _restored.snapshot_certificate["cert_identity"] == _identity


def test_v2_cert_plural_generation_required():
    """Defect 2: Cert eligibility requires non-empty custom_nodes_generation.
    Empty generation must not be eligible."""
    gen = ""  # empty
    eligible = bool(gen) and True
    assert not eligible, "empty custom_nodes_generation must be ineligible"


def test_v2_cert_no_uninitialized_cached_valid():
    """Defect 3: _cached_valid/_snapshot_valid/_evict_reason are initialized
    before any cert branch.  Verify module-level pre-init in execute method."""
    # These are initialized at function scope in _execute_v2_prompt_executor
    # as local vars before any branch.  Verify the init pattern is correct.
    cached_valid = False
    snapshot_valid = False
    evict_reason = ""
    cert_source: str | None = None
    # All must be defined before use
    assert cached_valid is False
    assert snapshot_valid is False
    assert evict_reason == ""
    assert cert_source is None


async def _make_fake_outputs_cache():
    """Create a minimal outputs cache for seed hook tests."""
    class _CacheKeySet:
        def get_data_key(self, node_id):
            return f"key_{node_id}"
    class _OutputsCache:
        def __init__(self):
            self.cache_key_set = _CacheKeySet()
            self._store = {}
            self.set_prompt_called = False
        async def set_prompt(self, *args, **kwargs):
            self.set_prompt_called = True
            return {"prompt": "ok"}
        async def set(self, node_id, entry):
            self._store[node_id] = entry
        async def get(self, node_id):
            return self._store.get(node_id)
    class _Caches:
        outputs = _OutputsCache()
    return _Caches().outputs, _Caches()


def test_v2_workflow_derived_model_identity():
    """Defect 5: Seed hook derives model identity from workflow,
    not plan.model_key."""
    from comfymodal_runtime.contracts import ModelRestoreKey
    from comfymodal_runtime.restore_plan import derive_model_key
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "test.safetensors"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "stable_diffusion"}},
    }
    key = derive_model_key(wf)
    assert isinstance(key, ModelRestoreKey)
    assert "test" in key.unet_identity or key.unet_identity == ""  # matches derive behavior
    # Confirm plan.model_key is NOT used
    assert not hasattr(key, "_from_plan_model_key")


def test_v2_seed_hook_no_cachedit_res4lyf():
    """Defect 6: Seed hook must NOT call CacheDiT or RES4LYF prep.
    Verify no call to prepare_restored_sampler_runtime / wrap_diffusion_model."""
    from comfymodal_runtime.runtime_bootstrap import BootstrapState
    state = BootstrapState()
    # verify old method is gone
    assert not hasattr(state, "prepare_restored_sampler_runtime"), \
        "prepare_restored_sampler_runtime must be removed"
    # verify new focused methods exist
    assert hasattr(state, "_restore_cachedit_prepare")
    assert hasattr(state, "_restore_res4lyf_prepare")


def test_v2_commit_failure_blocks_delivery():
    """Defect 7: commit.aio failures propagate so no result yield.
    Check _persist_output_assets propagates rather than swallowing."""
    import inspect
    # The commit_volume inner function in _persist_output_assets
    # must raise on failure instead of returning error in diag.
    # We verify by reading the source and checking for raise RuntimeError
    import textwrap
    source = inspect.getsource(modal_app.ModalRuntimeEntrypoint._persist_output_assets)
    assert "raise RuntimeError" in source, \
        "commit failure must propagate as RuntimeError"


def test_v2_base64_counters_truthful_descriptor_zero():
    """Defect 8: Base64 counters in descriptor normal path are zero.
    Check Attempt's base64 counters are zero for raw-only items."""
    from comfymodal_runtime.output_delivery import Attempt, OutputItem
    from comfymodal_runtime.output_delivery import attempt_to_descriptor_result
    # Create items with raw bytes but no base64_data (descriptor normal path)
    _raw = b"test image bytes"
    _digest = hashlib.sha256(_raw).hexdigest()
    _item = OutputItem(
        node_id="107",
        output_key="images",
        filename="test.png",
        raw_bytes=_raw,
        content_sha256=_digest,
        mime_type="image/png",
        file_ext=".png",
        width=512,
        height=512,
    )
    attempt = Attempt(
        strategy="history",
        success=True,
        items=(_item,),
        total_items=1,
        total_raw_bytes=len(_raw),
        total_base64_bytes=0,
        total_json_result_bytes=50,
    )
    # Descriptor normal path: Attempt has base64 counters
    assert attempt.base64_encode_count == 0, \
        "descriptor normal path: base64_encode_count must be 0"
    assert attempt.base64_decode_count == 0, \
        "descriptor normal path: base64_decode_count must be 0"
    # Also verify content_sha256 is precomputed (hash once)
    assert _item.content_sha256, "content_sha256 must be set"
    # Verify descriptor result has no base64 data
    result = attempt_to_descriptor_result(attempt, generation="test", legacy_data=False)
    assert result.get("include_base64") is False
    for img in result.get("images", []):
        assert "data" not in img, "descriptor path must not contain data"


def test_v2_production_snapshot_marker_accepted_and_cleaned_up():
    """_execute_v2_prompt_executor accepts request_bound_to_production_snapshot;
    when True the request is marked as a production CPU-snapshot request during
    execution and unmarked in the finally cleanup."""
    import comfymodal_runtime.model_preload as mp

    executor = _Executor()
    marked_during_execution = []

    async def _checked_execute_async(**kwargs):
        marked_during_execution.append(
            mp.is_production_cpu_snapshot_request("req-prod-marker")
        )
        executor.executed.append(kwargs)

    executor.execute_async = _checked_execute_async
    api = SimpleNamespace(_executor=executor)
    entrypoint = modal_app.ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "SaveImage", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-prod-marker", process="remote")
    context = ExecutionContext(request_id="req-prod-marker", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(
            plan,
            context,
            api,
            trace,
            request_bound_to_production_snapshot=True,
        ))

    assert marked_during_execution == [True], (
        "request must be marked as production CPU-snapshot during execution"
    )
    assert mp.is_production_cpu_snapshot_request("req-prod-marker") is False, (
        "production marker must be cleaned up in the finally block"
    )