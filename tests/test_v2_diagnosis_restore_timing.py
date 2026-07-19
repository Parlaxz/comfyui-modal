"""Focused V2 diagnosis-parity tests: restore timing lifecycle, event mapping, and result propagation.

All tests use mocks — no Modal/network calls, no ComfyUI imports.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan
from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
from comfymodal_runtime.runtime_executor import ExecutionContext
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap, BootstrapState
from comfymodal_runtime.runtime_executor import RuntimeExecutor
from comfymodal_runtime.trace import RuntimeTrace

# On Windows, ensure_models_symlink requires symlink privileges (admin/Developer Mode).
# Patching it at the module-import level so it is a no-op in all startup tests.
_MS_HOOK = patch("comfymodal_runtime.runtime_bootstrap.ensure_models_symlink", return_value="/tmp/void/models")
_MS_HOOK.start()

# Similarly patch configure_manager_offline to avoid env var side effects
_CM_HOOK = patch("comfymodal_runtime.runtime_bootstrap.configure_manager_offline", return_value={})
_CM_HOOK.start()


# ═══════════════════════════════════════════════════════════════════════════
# 1. V2 restore timing shape / lifecycle
# ═══════════════════════════════════════════════════════════════════════════


def _make_minimal_bootstrap() -> RuntimeBootstrap:
    """Bootstrap that succeeds without real GPU or ComfyUI."""
    def _noop(*_a, **_kw):
        return None

    def _state_result():
        return {"runtime_state": "gen-1", "custom_nodes": "gen-1"}

    config = BootstrapConfig(
        comfyui_root="/tmp/void",
        models_path="/tmp/void/models",
    )
    return RuntimeBootstrap(
        config,
        reload_models=_noop,
        reload_runtime_state=_noop,
        sync_custom_nodes=_noop,
        start_backend=lambda: "in_process",
        restore_gpu_state=_noop,
        initialize_cuda=lambda: {"device": "cuda:0", "cuda_available": "1"},
        apply_sage_policy=lambda: True,
        observe_generations=_state_result,
    )


def test_restore_returns_restore_timing_with_required_keys():
    """restore() return dict must contain _restore_timing with standard keys."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    # Inject publisher mock so restore plan read does not fail
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    result = entrypoint.restore()

    assert "_restore_timing" in result, f"Missing _restore_timing in keys: {list(result.keys())}"
    rt = result["_restore_timing"]

    # Required keys (always present)
    assert "restore_total_ms" in rt, f"_restore_timing keys: {list(rt.keys())}"
    assert isinstance(rt["restore_total_ms"], (int, float))
    assert rt["restore_total_ms"] >= 0

    assert "restore_session_id" in rt
    assert isinstance(rt["restore_session_id"], str)
    assert len(rt["restore_session_id"]) > 0

    assert "container_session_id" in rt
    assert isinstance(rt["container_session_id"], str)
    assert len(rt["container_session_id"]) > 0

    assert "restore_count" in rt
    assert rt["restore_count"] == 1  # first call


def test_restore_timing_stage_timings_included_when_available():
    """Stage timings from bootstrap state appear in _restore_timing when > 0."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    result = entrypoint.restore()
    rt = result["_restore_timing"]

    # The bootstrap emits _start/_end pairs that durations_ms() computes;
    # at least snapshot_restore_ms should be present.
    stage_keys = [k for k in rt if k.endswith("_ms") and k != "restore_total_ms"]
    # snapshot_restore covers the full restore span
    assert any("snapshot_restore" in k for k in stage_keys), (
        f"No snapshot_restore_ms among stage keys: {stage_keys}"
    )


def test_restore_count_increments():
    """Sequential restore() calls increment restore_count."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    r1 = entrypoint.restore()
    assert r1["_restore_timing"]["restore_count"] == 1

    r2 = entrypoint.restore()
    assert r2["_restore_timing"]["restore_count"] == 2


def test_container_session_id_stable_across_restores():
    """container_session_id remains constant across restore calls."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    r1 = entrypoint.restore()
    r2 = entrypoint.restore()

    assert r1["_restore_timing"]["container_session_id"] == r2["_restore_timing"]["container_session_id"]
    assert r1["_restore_timing"]["container_session_id"] == entrypoint.container_session_id


def test_restore_session_id_unique_per_call():
    """Each restore() generates a unique restore_session_id."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    r1 = entrypoint.restore()
    r2 = entrypoint.restore()

    assert r1["_restore_timing"]["restore_session_id"] != r2["_restore_timing"]["restore_session_id"]


def test_restore_trace_has_container_session_id():
    """The trace dict from restore() carries container_session_id in metadata."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    result = entrypoint.restore()
    trace_dict = result.get("trace", {})
    meta = trace_dict.get("metadata", {})
    assert meta.get("container_session_id") == entrypoint.container_session_id, (
        f"container_session_id not in trace metadata: {list(meta.keys())}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. Prompt-executor event mapping / emission
# ═══════════════════════════════════════════════════════════════════════════


def test_prompt_executor_events_emitted():
    """The prompt executor emits start/end trace events around the real executor call."""
    executor = _Executor()
    api = SimpleNamespace(
        _executor=executor,
    )
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-map-test", process="remote")
    context = ExecutionContext(request_id="req-map-test", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    event_names = [e.name for e in trace.events]
    assert "prompt_executor_start" in event_names, (
        f"Missing prompt_executor_start in events: {event_names}"
    )
    assert "prompt_executor_end" in event_names


def test_prompt_executor_maps_to_legacy_t3e_execution_start():
    """prompt_executor_start maps to legacy t3e_execution_start in to_legacy_timing()."""
    trace = RuntimeTrace(process="remote")
    trace.emit("prompt_executor_start", phase="execution", metadata={"prompt_id": "p1"})
    trace.emit("prompt_executor_end", phase="execution", metadata={"elapsed_ms": 100})

    legacy = trace.to_legacy_timing(prompt_id="p1")
    stages = legacy.get("stages", {})
    assert "t3e_execution_start" in stages, (
        f"Legacy stages missing t3e_execution_start, have: {list(stages.keys())}"
    )
    # Ensure existing mappings are preserved
    assert "t3d_prompt_start" not in stages  # graph_execution_start not emitted — OK


def test_prompt_executor_start_immediately_before_executor_call():
    """prompt_executor_start must occur after executor_reset_end and before executor.execute()."""
    executor = _Executor()
    api = SimpleNamespace(
        _executor=executor,
    )
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace()
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="req-order", process="remote")
    context = ExecutionContext(request_id="req-order", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    event_names = [e.name for e in trace.events]
    # Find the indices
    try:
        idx_reset_end = event_names.index("executor_reset_end")
        idx_start = event_names.index("prompt_executor_start")
        idx_end = event_names.index("prompt_executor_end")
    except ValueError as exc:
        assert False, f"Missing expected event: {exc}"

    assert idx_reset_end < idx_start, (
        f"executor_reset_end ({idx_reset_end}) must precede prompt_executor_start ({idx_start})"
    )
    assert idx_start < idx_end, (
        f"prompt_executor_start ({idx_start}) must precede prompt_executor_end ({idx_end})"
    )
    # prompt_executor_start should be immediately after executor_reset_end
    assert idx_start == idx_reset_end + 1, (
        f"prompt_executor_start should be right after executor_reset_end, "
        f"but found gap: events between = {event_names[idx_reset_end+1:idx_start+1]}"
    )


def test_existing_trace_mappings_preserved():
    """Adding t3e_execution_start must not remove any existing legacy mapping."""
    from comfymodal_runtime.trace import _LEGACY_STAGE_NAMES
    assert "t3d_prompt_start" in _LEGACY_STAGE_NAMES.values()
    assert "t1_local_recv" in _LEGACY_STAGE_NAMES.values()
    assert "t3e_execution_start" in _LEGACY_STAGE_NAMES.values()
    assert "prompt_executor_start" in _LEGACY_STAGE_NAMES


# ═══════════════════════════════════════════════════════════════════════════
# 3. Result propagation — _restore_timing in execution result
# ═══════════════════════════════════════════════════════════════════════════


def test_run_in_process_includes_restore_timing():
    """When restore() was called, _run_in_process includes _restore_timing in result."""
    executor = _Executor()
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"images": [], "videos": [], "outputs": {}, "trace": {}}),
    )
    # Ensure _load_legacy_runtime returns something with _executor
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._legacy_api = SimpleNamespace(
        _executor=executor,
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    # Call restore first to populate _restore_timing
    entrypoint.restore()
    assert entrypoint._restore_timing is not None

    # Now execute via _run_in_process (the wrapper that adds _restore_timing)
    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    context = ExecutionContext(request_id="req-prop")
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._run_in_process(plan, context))

    assert "_restore_timing" in result, (
        f"Missing _restore_timing in execution result keys: {list(result.keys())}"
    )
    rt = result["_restore_timing"]
    assert rt["restore_count"] >= 1
    assert "restore_total_ms" in rt
    assert "restore_session_id" in rt
    assert "container_session_id" in rt


def test_run_plan_stream_propagates_restore_timing():
    """run_plan_stream result event carries _restore_timing from lifecycle."""
    executor = RuntimeExecutor(
        in_process_runner=lambda plan, ctx: {
            "images": [],
            "videos": [],
            "outputs": {},
            "trace": RuntimeTrace(request_id="req-stream", process="remote").to_dict(),
        }
    )
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=executor,
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    # Populate restore timing
    entrypoint.restore()

    plan = ExecutionPlan(workflow={"1": {"class_type": "KSampler", "inputs": {}}})

    async def run():
        messages = [
            msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-stream")
        ]
        return messages

    messages = asyncio.run(run())
    result_msgs = [m for m in messages if m.get("type") == "result"]
    assert len(result_msgs) >= 1, "No result event in stream"
    data = result_msgs[0].get("data", {})
    assert "_restore_timing" in data, (
        f"Missing _restore_timing in stream result data keys: {list(data.keys())}"
    )
    rt = data["_restore_timing"]
    assert rt["restore_count"] >= 1
    assert "restore_session_id" in rt


def test_restore_timing_flows_through_meta_to_history():
    """Verify _restore_timing reaches the _meta dict shape that _finish_job expects."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    r = entrypoint.restore()
    # This is the exact shape that __init__.py line 2653 reads:
    #   "restore_timing": result.get("_restore_timing", {})
    meta = {
        "model_stack": [],
        "prompt_summary": {},
        "trace": {},
        "workflow_hash": "abc",
        "restore_timing": r.get("_restore_timing", {}),
    }
    assert "restore_timing" in meta
    rt = meta["restore_timing"]
    assert rt["restore_total_ms"] >= 0
    assert rt["restore_session_id"]
    assert rt["container_session_id"]
    assert rt["restore_count"] == 1
    # Has stage timings
    stage_keys = [k for k in rt if k.endswith("_ms")]
    assert len(stage_keys) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# 4. V1 behavior preserved
# ═══════════════════════════════════════════════════════════════════════════


def test_v1_to_legacy_timing_still_works():
    """to_legacy_timing() still produces a valid legacy dict with the new mapping."""
    trace = RuntimeTrace(process="remote")
    trace.emit("container_entry", phase="lifecycle")
    trace.emit("graph_execution_start", phase="execution")
    trace.emit("prompt_executor_start", phase="execution")
    trace.emit("prompt_executor_end", phase="execution")

    legacy = trace.to_legacy_timing(prompt_id="v1-test")
    assert "prompt_id" in legacy
    assert "stages" in legacy
    assert "events" in legacy
    # Existing mappings should still be present
    assert "t3_modal_entry" in legacy["stages"]
    assert "t3d_prompt_start" in legacy["stages"]
    # New mapping should be present
    assert "t3e_execution_start" in legacy["stages"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Startup lifecycle timing
# ═══════════════════════════════════════════════════════════════════════════


def test_startup_returns_restore_timing():
    """startup() return dict must contain _restore_timing with required keys."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    result = entrypoint.startup()

    assert "_restore_timing" in result, f"Missing _restore_timing in keys: {list(result.keys())}"
    rt = result["_restore_timing"]

    # Required keys (always present)
    assert "restore_total_ms" in rt, f"_restore_timing keys: {list(rt.keys())}"
    assert isinstance(rt["restore_total_ms"], (int, float))
    assert rt["restore_total_ms"] >= 0

    assert "restore_session_id" in rt
    assert isinstance(rt["restore_session_id"], str)
    assert len(rt["restore_session_id"]) > 0

    assert "container_session_id" in rt
    assert isinstance(rt["container_session_id"], str)
    assert len(rt["container_session_id"]) > 0

    # Cold startup classification: restore_count = 1
    assert "restore_count" in rt
    assert rt["restore_count"] == 1, (
        f"startup restore_count should be 1 for cold classification, got {rt['restore_count']}"
    )


def test_startup_restore_timing_includes_stage_durations():
    """startup _restore_timing includes stage durations from bootstrap when available."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    result = entrypoint.startup()
    rt = result["_restore_timing"]

    # Bootstrap emits _start/_end pairs; at minimum snapshot_restore_ms should be present
    stage_keys = [k for k in rt if k.endswith("_ms") and k != "restore_total_ms"]
    # The startup trace emits snapshot_restore_start/snapshot_restore_end events
    assert any("snapshot_restore" in k for k in stage_keys), (
        f"No snapshot_restore_ms among stage keys: {stage_keys}"
    )


def test_startup_sets_restore_timing_on_instance():
    """After startup(), self._restore_timing is populated on the instance."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    assert entrypoint._restore_timing is None  # before
    entrypoint.startup()
    assert entrypoint._restore_timing is not None, "startup() should populate _restore_timing"
    assert entrypoint._restore_timing["restore_count"] == 1


def test_startup_updates_process_local_fallback():
    """startup() writes _LATEST_LIFECYCLE_TIMING for downstream fallback."""
    from comfymodal_runtime.modal_app import _LATEST_LIFECYCLE_TIMING

    # Reset to known state
    import comfymodal_runtime.modal_app as ma
    ma._LATEST_LIFECYCLE_TIMING = None

    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    entrypoint.startup()

    assert ma._LATEST_LIFECYCLE_TIMING is not None, (
        "_LATEST_LIFECYCLE_TIMING should be set after startup()"
    )
    assert ma._LATEST_LIFECYCLE_TIMING["restore_count"] == 1
    assert "restore_session_id" in ma._LATEST_LIFECYCLE_TIMING
    assert "container_session_id" in ma._LATEST_LIFECYCLE_TIMING
    assert "restore_total_ms" in ma._LATEST_LIFECYCLE_TIMING


def test_startup_trace_has_container_session_id():
    """The trace dict from startup() carries container_session_id in metadata."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    result = entrypoint.startup()
    trace_dict = result.get("trace", {})
    meta = trace_dict.get("metadata", {})
    assert meta.get("container_session_id") == entrypoint.container_session_id, (
        f"container_session_id not in trace metadata: {list(meta.keys())}"
    )


def test_startup_lifecycle_identity_in_trace_events():
    """startup trace events contain lifecycle_session_id and lifecycle_count in remote_method_entry."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    result = entrypoint.startup()
    trace_dict = result.get("trace", {})
    events = trace_dict.get("events", [])

    entry_events = [e for e in events if e.get("name") == "remote_method_entry"]
    assert len(entry_events) >= 1, "No remote_method_entry event in startup trace"
    meta = entry_events[0].get("metadata", {})
    assert meta.get("lifecycle_session_id", "") != "", (
        "lifecycle_session_id should be present in startup entry metadata"
    )
    assert meta.get("lifecycle_count") == "1", (
        f"lifecycle_count should be '1' for cold startup, got {meta.get('lifecycle_count')}"
    )
    assert meta.get("method_name") == "startup"
    assert meta.get("snapshot") == "True"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Process-local fallback for Modal instance separation
# ═══════════════════════════════════════════════════════════════════════════


def test_run_stream_uses_process_local_fallback_when_instance_empty():
    """run_plan_stream propagates _restore_timing via process-local fallback
    when the executing instance has no _restore_timing (simulating Modal
    method-instance separation)."""
    import comfymodal_runtime.modal_app as ma

    # Set the fallback directly (as startup() or restore() would on a different instance)
    fake_timing: dict[str, Any] = {
        "restore_total_ms": 1234.5,
        "restore_session_id": "fallback-session-001",
        "container_session_id": "fallback-container-001",
        "restore_count": 1,
        "snapshot_restore_ms": 1000.0,
    }
    ma._LATEST_LIFECYCLE_TIMING = fake_timing

    # Create fresh entrypoint that has NOT called startup/restore (instance empty)
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=RuntimeExecutor(
            in_process_runner=lambda plan, ctx: {
                "images": [],
                "videos": [],
                "outputs": {},
                "trace": RuntimeTrace(request_id="req-fallback", process="remote").to_dict(),
            }
        ),
    )
    # Ensure _load_legacy_runtime returns something with _executor
    executor = _Executor()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._legacy_api = SimpleNamespace(_executor=executor)
    # Do NOT call startup() or restore() — _restore_timing should remain None
    assert entrypoint._restore_timing is None, "Instance should have no _restore_timing"

    plan = ExecutionPlan(workflow={"1": {"class_type": "KSampler", "inputs": {}}})

    async def run():
        messages = [
            msg async for msg in entrypoint.run_plan_stream(plan.to_dict(), request_id="req-fallback")
        ]
        return messages

    messages = asyncio.run(run())
    result_msgs = [m for m in messages if m.get("type") == "result"]
    assert len(result_msgs) >= 1, "No result event in stream"
    data = result_msgs[0].get("data", {})
    assert "_restore_timing" in data, (
        f"Missing _restore_timing in stream result (instance empty, should use fallback): "
        f"keys: {list(data.keys())}"
    )
    rt = data["_restore_timing"]
    assert rt["restore_session_id"] == "fallback-session-001"
    assert rt["restore_count"] == 1
    assert rt["container_session_id"] == "fallback-container-001"

    # Clean up
    ma._LATEST_LIFECYCLE_TIMING = None


def test_run_in_process_uses_fallback_when_instance_empty():
    """_run_in_process uses process-local fallback when instance _restore_timing is None."""
    import comfymodal_runtime.modal_app as ma

    fake_timing: dict[str, Any] = {
        "restore_total_ms": 5678.9,
        "restore_session_id": "inproc-fallback-001",
        "container_session_id": "inproc-container-001",
        "restore_count": 1,
    }
    ma._LATEST_LIFECYCLE_TIMING = fake_timing

    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"images": [], "videos": [], "outputs": {}, "trace": {}}),
    )
    executor_obj = _Executor()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._legacy_api = SimpleNamespace(_executor=executor_obj)
    assert entrypoint._restore_timing is None

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    context = ExecutionContext(request_id="req-inproc-fb")
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._run_in_process(plan, context))

    assert "_restore_timing" in result, (
        f"Missing _restore_timing in _run_in_process result (fallback should apply): "
        f"keys: {list(result.keys())}"
    )
    rt = result["_restore_timing"]
    assert rt["restore_session_id"] == "inproc-fallback-001"

    ma._LATEST_LIFECYCLE_TIMING = None


def test_instance_timing_preferred_over_fallback():
    """When instance _restore_timing is set, it takes priority over process-local fallback."""
    import comfymodal_runtime.modal_app as ma

    # Set fallback with different values
    ma._LATEST_LIFECYCLE_TIMING = {
        "restore_total_ms": 9999.0,
        "restore_session_id": "fallback-only",
        "container_session_id": "fallback-container",
        "restore_count": 0,
    }

    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"images": [], "videos": [], "outputs": {}, "trace": {}}),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    # Call restore to populate instance _restore_timing (will be > fallback values)
    entrypoint.restore()
    assert entrypoint._restore_timing is not None
    instance_rt = entrypoint._restore_timing

    executor_obj = _Executor()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._legacy_api = SimpleNamespace(_executor=executor_obj)

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    context = ExecutionContext(request_id="req-priority")
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._run_in_process(plan, context))

    rt = result["_restore_timing"]
    # Instance value should win — restore_session_id should NOT be "fallback-only"
    assert rt["restore_session_id"] != "fallback-only", (
        "Instance _restore_timing should override process-local fallback"
    )
    assert rt["restore_session_id"] == instance_rt["restore_session_id"]

    ma._LATEST_LIFECYCLE_TIMING = None


def test_restore_updates_process_local_fallback():
    """restore() overwrites _LATEST_LIFECYCLE_TIMING for subsequent fallback use."""
    import comfymodal_runtime.modal_app as ma
    ma._LATEST_LIFECYCLE_TIMING = None

    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    result = entrypoint.restore()

    assert ma._LATEST_LIFECYCLE_TIMING is not None, (
        "restore() should set _LATEST_LIFECYCLE_TIMING"
    )
    assert ma._LATEST_LIFECYCLE_TIMING["restore_count"] == 1
    assert ma._LATEST_LIFECYCLE_TIMING["restore_session_id"] == result["_restore_timing"]["restore_session_id"]

    ma._LATEST_LIFECYCLE_TIMING = None


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


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


async def _validate_prompt_ok(_prompt_id, _workflow, _extra):
    return True, {}, ["107"], {}


def api_with_executor(executor) -> SimpleNamespace:
    return SimpleNamespace(
        _executor=executor,
        _wait_for_restore_preload_before_request=lambda wf: None,
        _preflight_before_prompt_execution=lambda wf: None,
        _preflight_already_ran=False,
        _repair_missing_workflow_nodes=lambda wf: {"missing_before": [], "missing_after": [], "blocked_by_mode": False},
    )
