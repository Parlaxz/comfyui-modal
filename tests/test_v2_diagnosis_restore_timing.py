"""Focused V2 diagnosis-parity tests: restore timing lifecycle, event mapping, and result propagation.

All tests use mocks — no Modal/network calls, no ComfyUI imports.
"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from comfymodal_runtime.contracts import ExecutionOptions, ExecutionPlan, ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.modal_app import ModalRuntimeEntrypoint
from comfymodal_runtime.runtime_executor import ExecutionContext
from comfymodal_runtime.runtime_bootstrap import BootstrapConfig, RuntimeBootstrap, BootstrapState
from comfymodal_runtime.runtime_executor import RuntimeExecutor
from comfymodal_runtime.restore_plan import build_restore_model_spec
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.model_preload import V2LoaderBridge

# On Windows, ensure_models_symlink requires symlink privileges (admin/Developer Mode).
# Patching it at the module-import level so it is a no-op in all startup tests.
_MS_HOOK = patch("comfymodal_runtime.runtime_bootstrap.ensure_models_symlink", return_value="/tmp/void/models")
_MS_HOOK.start()

# Similarly patch configure_manager_offline to avoid env var side effects
_CM_HOOK = patch("comfymodal_runtime.runtime_bootstrap.configure_manager_offline", return_value={})
_CM_HOOK.start()


@pytest.fixture(autouse=True)
def _reset_module_level_counters():
    """Reset module-level counters before each test to prevent cross-test leakage.

    Production semantics are preserved at module scope — this fixture only
    ensures each test sees a fresh baseline so assertions like
    ``restore_count == 1`` are not affected by earlier tests.
    """
    import comfymodal_runtime.modal_app as _ma
    _ma._v2_container_restore_count = 0
    _ma._LATEST_LIFECYCLE_TIMING = None
    # Also reset the restore_count on any cached entrypoint instances
    yield


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
# 1b. Restore plan read events and phase-duration export
# ═══════════════════════════════════════════════════════════════════════════


def test_restore_plan_read_events():
    """restore() trace must contain restore_plan_read_start and restore_plan_read_end."""
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
    events = trace_dict.get("events", [])
    event_names = [e.get("name") for e in events]

    assert "restore_plan_read_start" in event_names, (
        f"Missing restore_plan_read_start in events: {event_names}"
    )
    assert "restore_plan_read_end" in event_names, (
        f"Missing restore_plan_read_end in events: {event_names}"
    )

    # Verify ordering
    idx_start = event_names.index("restore_plan_read_start")
    idx_end = event_names.index("restore_plan_read_end")
    assert idx_start < idx_end, (
        f"restore_plan_read_start ({idx_start}) must precede restore_plan_read_end ({idx_end})"
    )


def test_restore_phase_durations_exported():
    """restore() result must include phase_durations_ms from trace span boundaries."""
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

    assert "phase_durations_ms" in result, (
        f"Missing phase_durations_ms in result keys: {list(result.keys())}"
    )
    pd = result["phase_durations_ms"]
    assert isinstance(pd, dict), f"phase_durations_ms must be a dict, got {type(pd)}"
    # At minimum snapshot_restore must be present (paired _start/_end events)
    assert "snapshot_restore" in pd, (
        f"Expected snapshot_restore in phase_durations_ms keys: {list(pd.keys())}"
    )
    assert pd["snapshot_restore"] >= 0
    # All durations should be non-negative
    for name, dur in pd.items():
        assert isinstance(dur, (int, float)), f"Duration for {name!r} must be numeric, got {type(dur)}"
        assert dur >= 0, f"Duration for {name!r} must be >= 0, got {dur}"


def test_startup_phase_durations_exported():
    """startup() result must include phase_durations_ms."""
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )

    result = entrypoint.startup()

    assert "phase_durations_ms" in result, (
        f"Missing phase_durations_ms in startup result keys: {list(result.keys())}"
    )
    pd = result["phase_durations_ms"]
    assert isinstance(pd, dict)
    assert "snapshot_restore" in pd, (
        f"Expected snapshot_restore in phase_durations_ms keys: {list(pd.keys())}"
    )


def test_execution_phase_durations_exported():
    """Execution result from _run_in_process must include phase_durations_ms."""
    executor = _Executor()
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=_make_minimal_bootstrap(),
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
        executor=RuntimeExecutor(in_process_runner=lambda plan, ctx: {"images": [], "videos": [], "outputs": {}, "trace": {}}),
    )
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._legacy_api = SimpleNamespace(_executor=executor)
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: None,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    entrypoint.restore()

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    context = ExecutionContext(request_id="req-phase-exec")
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)
    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._run_in_process(plan, context))

    assert "phase_durations_ms" in result, (
        f"Missing phase_durations_ms in execution result keys: {list(result.keys())}"
    )
    pd = result["phase_durations_ms"]
    assert isinstance(pd, dict), f"phase_durations_ms must be a dict, got {type(pd)}"
    # Execution phases that should have explicit spans
    for expected_phase in ("prompt_validation", "executor_reset", "prompt_executor"):
        assert expected_phase in pd, (
            f"Expected {expected_phase!r} in phase_durations_ms keys: {list(pd.keys())}"
        )
        assert pd[expected_phase] >= 0


# ═══════════════════════════════════════════════════════════════════════════
# 1c. Extension: restore() extends existing preparation on handoff failure
# ═══════════════════════════════════════════════════════════════════════════


def _restore_plan_with_identity() -> RestorePlan:
    """Build a RestorePlan with model_key so the preload path is exercised."""
    model_key = ModelRestoreKey(
        unet_identity="unet.safetensors",
        clip_identity="clip.safetensors",
        clip_type="flux",
    )
    # Workflow with CLIPLoader so model_spec includes clip loaders for
    # _find_request + _load_clip to succeed during clip-only prepare.
    workflow = {
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors", "type": "flux"}},
    }
    return RestorePlan(
        generation=1,
        model_key=model_key,
        prefill_key=PrefillKey(model_key=model_key),
        model_spec=build_restore_model_spec(workflow, {"unet": []}),
        source_workflow_hash="test-hash",
    )


def _fake_comfy_nodes() -> SimpleNamespace:
    """Fake NODE_CLASS_MAPPINGS module for bridge installation."""
    class FakeCLIPLoader:
        def load_clip(self, clip_name, type="stable_diffusion", device="default"):
            return (SimpleNamespace(),)

    class FakeUNETLoader:
        def load_unet(self, unet_name, weight_dtype="default"):
            return (f"unet:{unet_name}:{weight_dtype}",)

    return SimpleNamespace(
        NODE_CLASS_MAPPINGS={
            "CLIPLoader": FakeCLIPLoader,
            "UNETLoader": FakeUNETLoader,
        }
    )


def _mock_defer_api_handoff_fails() -> SimpleNamespace:
    """API mock with deferral helpers where the UNET handoff returns submitted=False."""
    return SimpleNamespace(
        _patch_unet_loader_cache=lambda: None,
        _start_production_restore_unet=lambda *a, **kw: {"submitted": False},
        _executor=SimpleNamespace(success=True, history_result={}, reset=lambda: None),
        _wait_for_restore_preload_before_request=lambda wf: None,
        _preflight_before_prompt_execution=lambda wf: None,
        _preflight_already_ran=False,
        _repair_missing_workflow_nodes=lambda wf: {"missing_before": [], "missing_after": [], "blocked_by_mode": False},
        _begin_prompt_profile=lambda *a, **kw: None,
        _stage_windows=None,
        _actual_load_futures={},
    )


def test_restore_extends_preparation_when_handoff_fails():
    """When the UNET handoff returns submitted=False after clip-only prepare,
    restore() extends the existing preparation with UNET+VAE instead of
    clearing and doing a full reprepare (which would duplicate CLIP)."""
    bootstrap = _make_minimal_bootstrap()
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=bootstrap,
        config=BootstrapConfig(comfyui_root="/tmp/void", models_path="/tmp/void/models"),
    )
    # Inject API with deferral helpers that fail
    entrypoint._legacy_api = _mock_defer_api_handoff_fails()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )

    # Publisher returns a plan with model_key
    plan = _restore_plan_with_identity()
    publisher_mock = SimpleNamespace(
        read_current_plan=lambda: plan,
        publish_with_metrics=lambda p: {"changed": False},
    )
    entrypoint._restore_publisher = publisher_mock
    entrypoint._get_remote_restore_publisher = lambda: publisher_mock

    # Patch sys.modules['nodes'] so bridge.prepare() does not import real ComfyUI
    with patch.dict("sys.modules", {"nodes": _fake_comfy_nodes()}):
        result = entrypoint.restore()
    trace_dict = result.get("trace", {})
    events = trace_dict.get("events", [])
    event_names = [e.get("name") for e in events]

    # Verify we took the extension path
    assert "preload_fallback_mode" in event_names, (
        f"Missing preload_fallback_mode in events: {[e for e in event_names if 'preload' in e]}"
    )
    fallback_events = [e for e in events if e.get("name") == "preload_fallback_mode"]
    assert len(fallback_events) >= 1
    mode = fallback_events[0].get("metadata", {}).get("mode", "")
    assert mode == "extended_existing_preparation", (
        f"Expected extended_existing_preparation, got {mode!r}"
    )

    # CLIP was loaded only once (no duplicate)
    clip_events = [e for e in events if "clip" in e.get("name", "").lower()]
    clip_submitted = [e for e in events if e.get("name") == "preload_submitted" and e.get("metadata", {}).get("lane") == "clip"]
    assert len(clip_submitted) == 1, (
        f"Expected exactly one clip preload_submitted, got {len(clip_submitted)}"
    )

    # UNET was submitted via extension
    unet_submitted = [e for e in events if e.get("name") == "preload_submitted" and e.get("metadata", {}).get("lane") == "unet"]
    assert len(unet_submitted) >= 1, (
        f"Expected at least one unet preload_submitted via extension"
    )

    # preload_extension_submitted event present
    ext_events = [e for e in events if e.get("name") == "preload_extension_submitted"]
    assert len(ext_events) >= 1, (
        f"Missing preload_extension_submitted in events"
    )


def test_restore_full_reprepare_when_no_plan():
    """When _restore_plan is None, the preload path is skipped entirely."""
    bootstrap = _make_minimal_bootstrap()
    entrypoint = ModalRuntimeEntrypoint(
        bootstrap=bootstrap,
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
    events = trace_dict.get("events", [])
    event_names = [e.get("name") for e in events]

    # No preload_fallback_mode because the preload path was not entered
    assert "preload_fallback_mode" not in event_names
    # No preload_submission_start because _restore_plan is None
    assert "preload_submission_start" not in event_names


# ═══════════════════════════════════════════════════════════════════════════
# 1d. Pregraph ordering and milestone interception
# ═══════════════════════════════════════════════════════════════════════════


class _FakeExecutorWithMilestones:
    """Executor mock with add_message (3-arg) and server.send_sync."""
    success = True
    history_result = {}

    def __init__(self):
        self.add_message_calls = []
        self.send_sync_calls = []
        self.server = SimpleNamespace()
        self.server.send_sync = self._fake_send_sync

    def _fake_send_sync(self, event, *args, **kwargs):
        self.send_sync_calls.append((event, args, kwargs))
        return None

    def add_message(self, event: str, data: dict, broadcast: bool = True):
        self.add_message_calls.append((event, data, broadcast))
        return None

    def reset(self):
        pass

    async def execute_async(self, **kwargs):
        # Simulate execution: fire milestones
        self.add_message("execution_start", {"prompt_id": "p1"}, True)
        self._fake_send_sync("executing", "node_3", "client_1")
        self.add_message("execution_cached", {"nodes": ["3"]}, True)
        return None


def test_pregraph_setup_ordering():
    """pregraph_setup_start must follow prompt_validation_end, and
    pregraph_setup_end must precede prompt_executor_start, with
    executor_reset_start/end inside the pregraph span."""
    executor = _FakeExecutorWithMilestones()
    api = SimpleNamespace(_executor=executor)
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="pregraph-order", process="remote")
    context = ExecutionContext(request_id="pregraph-order", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    event_names = [e.name for e in trace.events]

    # Verify ordering
    try:
        idx_val_end = event_names.index("prompt_validation_end")
        idx_pg_start = event_names.index("pregraph_setup_start")
        idx_reset_start = event_names.index("executor_reset_start")
        idx_reset_end = event_names.index("executor_reset_end")
        idx_pg_end = event_names.index("pregraph_setup_end")
        idx_pex_start = event_names.index("prompt_executor_start")
    except ValueError as exc:
        assert False, f"Missing expected event: {exc}"

    assert idx_val_end < idx_pg_start, (
        f"prompt_validation_end ({idx_val_end}) must precede pregraph_setup_start ({idx_pg_start})"
    )
    assert idx_pg_start < idx_reset_start, (
        f"pregraph_setup_start ({idx_pg_start}) must precede executor_reset_start ({idx_reset_start})"
    )
    assert idx_reset_end < idx_pg_end, (
        f"executor_reset_end ({idx_reset_end}) must precede pregraph_setup_end ({idx_pg_end})"
    )
    assert idx_pg_end < idx_pex_start, (
        f"pregraph_setup_end ({idx_pg_end}) must precede prompt_executor_start ({idx_pex_start})"
    )


def test_milestone_interception_three_arg_add_message():
    """The add_message wrapper accepts the real 3-arg signature and
    captures execution_start/execution_cached timestamps."""
    executor = _FakeExecutorWithMilestones()
    api = SimpleNamespace(_executor=executor)
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="milestone-3arg", process="remote")
    context = ExecutionContext(request_id="milestone-3arg", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    event_names = [e.name for e in trace.events]
    assert "prompt_executor_milestones" in event_names, (
        f"Missing prompt_executor_milestones in events: {event_names}"
    )

    # All milestone delta values must be nonnegative and realistic
    ms_events = [e for e in trace.events if e.name == "prompt_executor_milestones"]
    assert len(ms_events) >= 1
    ms_meta = ms_events[0].metadata
    for key in ("executor_call_to_execution_start_ms", "execution_start_to_cached_ms", "cached_to_first_node_ms"):
        val = ms_meta.get(key)
        if val is not None:
            assert isinstance(val, (int, float)), f"{key} must be numeric, got {type(val)}"
            assert val >= 0, f"{key} must be >= 0, got {val}"
    # executor_call_to_execution_start_ms must be present (execution_start was fired)
    assert ms_meta.get("executor_call_to_execution_start_ms") is not None, (
        "executor_call_to_execution_start_ms must be present"
    )

    # add_message must be restored to original (sentinel absent)
    assert not getattr(executor.add_message, "_comfy_modal_milestone", False), (
        "add_message must be restored (sentinel removed)"
    )

    # send_sync must also be restored
    assert not getattr(executor.server.send_sync, "_comfy_modal_send_sync", False), (
        "send_sync must be restored (sentinel removed)"
    )

    # Original add_message and send_sync were called
    assert len(executor.add_message_calls) > 0, "original add_message must have been called"
    assert len(executor.send_sync_calls) > 0, "original send_sync must have been called"


def test_milestone_interception_both_restored_after_error():
    """Both add_message and send_sync are restored even when execute raises."""
    executor = _FakeExecutorWithMilestones()

    # Replace execute_async with one that raises, after firing both milestones
    async def broken_execute(**kwargs):
        executor.add_message("execution_start", {"prompt_id": "p1"}, True)
        executor.server.send_sync("executing", "node_3")
        raise RuntimeError("simulated execution crash")

    executor.execute_async = broken_execute

    api = SimpleNamespace(_executor=executor)
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="milestone-error", process="remote")
    context = ExecutionContext(request_id="milestone-error", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        with pytest.raises(RuntimeError, match="simulated execution crash"):
            asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    # Both wrappers must be restored after error
    assert not getattr(executor.add_message, "_comfy_modal_milestone", False), (
        "add_message must be restored after error"
    )
    assert not getattr(executor.server.send_sync, "_comfy_modal_send_sync", False), (
        "send_sync must be restored after error"
    )

    # Original methods were called
    assert len(executor.add_message_calls) > 0
    assert len(executor.send_sync_calls) > 0


def test_milestone_interception_unavailable_emits_reason():
    """When add_message/send_sync are absent, an unavailable reason is emitted."""
    # Create an executor-like object that has no add_message and no server.send_sync
    async def _noop_execute(**kw):
        return None
    executor = SimpleNamespace(
        reset=lambda: None,
        execute_async=_noop_execute,
        success=True,
        history_result={},
    )
    # Add server with no send_sync
    executor.server = SimpleNamespace()
    api = SimpleNamespace(_executor=executor)
    entrypoint = ModalRuntimeEntrypoint()
    entrypoint._legacy_module = SimpleNamespace(
        _materialize_input_images=lambda inputs: None,
    )
    entrypoint._executor_injected = True

    plan = ExecutionPlan(
        workflow={"107": {"class_type": "KSampler", "inputs": {}}},
        execution_options=ExecutionOptions(production_enabled=False),
    )
    trace = RuntimeTrace(request_id="milestone-unavail", process="remote")
    context = ExecutionContext(request_id="milestone-unavail", trace=trace)
    fake_execution = SimpleNamespace(validate_prompt=_validate_prompt_ok)

    with patch.dict("sys.modules", {"execution": fake_execution}):
        result = asyncio.run(entrypoint._execute_v2_prompt_executor(plan, context, api, trace))

    event_names = [e.name for e in trace.events]
    reason_events = [e for e in trace.events if e.name == "prompt_executor_internal_milestones_unavailable"]
    assert len(reason_events) >= 1, (
        f"Must emit unavailable reason when add_message/send_sync are absent"
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
    # prompt_executor_start should follow executor_reset_end (pregraph_setup_end
    # sits between them in the execution trace as the span boundary marker).
    assert idx_reset_end < idx_start, (
        f"executor_reset_end ({idx_reset_end}) must precede prompt_executor_start ({idx_start})"
    )
    assert idx_start > idx_reset_end, (
        f"prompt_executor_start should come after executor_reset_end, "
        f"but found: events between = {event_names[idx_reset_end+1:idx_start+1]}"
    )


def test_existing_trace_mappings_preserved():
    """Adding t3e_execution_start must not remove any existing legacy mapping."""
    from comfymodal_runtime.trace import _LEGACY_STAGE_NAMES
    assert "t3d_prompt_start" in _LEGACY_STAGE_NAMES.values()
    assert "t1_local_recv" in _LEGACY_STAGE_NAMES.values()
    assert "t3e_execution_start" in _LEGACY_STAGE_NAMES.values()
    assert "prompt_executor_start" in _LEGACY_STAGE_NAMES


def test_certificate_reload_has_proper_span():
    """certificate_reload_start and certificate_reload_end must both be emitted as a span pair."""
    from comfymodal_runtime.modal_app import _compute_v2_cert_identity
    trace = RuntimeTrace(request_id="cert-span", process="remote")
    trace.emit("certificate_reload_start", phase="execution",
               metadata={"cert_identity": "test-identity-1234"})
    trace.emit("certificate_reload_end", phase="execution",
               metadata={"cert_identity": "test-identity-1234", "hit": True})

    event_names = [e.name for e in trace.events]
    assert "certificate_reload_start" in event_names
    assert "certificate_reload_end" in event_names

    idx_start = event_names.index("certificate_reload_start")
    idx_end = event_names.index("certificate_reload_end")
    assert idx_start < idx_end, (
        f"certificate_reload_start ({idx_start}) must precede certificate_reload_end ({idx_end})"
    )

    # Verify the span is captured by durations_ms
    durs = trace.durations_ms()
    assert "certificate_reload" in durs, (
        f"certificate_reload must appear in durations_ms: {list(durs.keys())}"
    )
    assert durs["certificate_reload"] >= 0


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

    # phase_durations_ms is recomputed from the merged lifecycle+execution trace
    assert "phase_durations_ms" in data, (
        f"Missing phase_durations_ms in stream result data keys: {list(data.keys())}"
    )
    pd = data["phase_durations_ms"]
    assert isinstance(pd, dict)
    # Merged trace includes restore phases from lifecycle
    assert "snapshot_restore" in pd, (
        f"Expected snapshot_restore in phase_durations_ms keys: {list(pd.keys())}"
    )


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


# ═══════════════════════════════════════════════════════════════════════════
# 7. GPU not-observed classification propagation
# ═══════════════════════════════════════════════════════════════════════════


class TestGpuNotObservedInRestoreTiming:
    """gpu_not_observed_summary propagates through restore timing.

    The summary function is consumed by the caller (modal_app or diagnosis
    collector) which reads the request-scope wrapper state.  These tests
    verify the contract without calling modal_app.py.
    """

    def test_not_observed_under_request_scope_zero_calls(self):
        """Under request scope with zero GPU calls, classification is 'not_observed'."""
        from comfymodal_runtime.model_preload import (
            gpu_not_observed_summary,
            request_execution_trace_scope,
            _gpu_wrapper_installed,
            _gpu_request_call_count_var,
        )

        saved_installed = _gpu_wrapper_installed
        saved_count = _gpu_request_call_count_var.get()
        try:
            # Simulate wrapper installed but zero GPU calls
            import comfymodal_runtime.model_preload as mp
            mp._gpu_wrapper_installed = True
            mp._gpu_request_call_count_var.set(0)

            trace = RuntimeTrace(request_id="gpu-no-call-rt", process="remote")
            with request_execution_trace_scope(trace):
                summary = gpu_not_observed_summary()

            assert summary["caller_classification"] == "not_observed"
            assert summary["wrapper_status"] == "installed"
            assert summary["count"] == 0
            assert summary["request_id"] == "gpu-no-call-rt"
        finally:
            mp._gpu_wrapper_installed = saved_installed
            mp._gpu_request_call_count_var.set(saved_count)

    def test_wrapper_unavailable_when_not_installed(self):
        """When wrapper is not installed, classification is 'wrapper_unavailable'."""
        from comfymodal_runtime.model_preload import (
            gpu_not_observed_summary,
            _gpu_wrapper_installed,
        )

        saved = _gpu_wrapper_installed
        try:
            import comfymodal_runtime.model_preload as mp
            mp._gpu_wrapper_installed = False

            summary = gpu_not_observed_summary()

            assert summary["caller_classification"] == "wrapper_unavailable"
            assert summary["wrapper_status"] == "unavailable"
            assert summary["count"] == 0
        finally:
            mp._gpu_wrapper_installed = saved

    def test_summary_never_returns_numeric_zero_as_classification(self):
        """caller_classification is always a string, never None or 0."""
        from comfymodal_runtime.model_preload import request_execution_trace_scope
        import comfymodal_runtime.model_preload as mp
        saved = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = True
            trace = RuntimeTrace(request_id="gpu-str-cls", process="remote")
            with request_execution_trace_scope(trace):
                summary = mp.gpu_not_observed_summary()
            assert isinstance(summary["caller_classification"], str)
            assert summary["caller_classification"] != "0"
            assert summary["caller_classification"] != ""

            mp._gpu_wrapper_installed = False
            summary2 = mp.gpu_not_observed_summary()
            assert isinstance(summary2["caller_classification"], str)
            assert summary2["caller_classification"] != "0"
        finally:
            mp._gpu_wrapper_installed = saved
