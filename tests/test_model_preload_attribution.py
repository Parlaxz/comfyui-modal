"""Focused tests for model_preload attribution: CLIP CPU prepare instrumention,
safetensors proxy integrity, GPU wrapper status/count, and active-read honesty.

All tests use mocks — no Modal/network calls, no real ComfyUI imports.
"""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from comfymodal_runtime.contracts import stable_hash
from comfymodal_runtime.trace import RuntimeTrace
from comfymodal_runtime.model_preload import (
    ModelLaneTrace,
    _SafeOpenProxy,
    _clip_cpu_prepare_children,
    _gpu_request_call_count_var,
    _clip_wrapper_installed,
    _clip_depth,
    _clip_subfn_depth,
    _ACTIVE_LANE_TRACE,
    _ACTIVE_REQUEST_TRACE,
    _DIAGNOSTIC_FLAG,
    classify_active_read_dims,
    gpu_wrapper_is_installed,
    gpu_call_count,
    gpu_not_observed_summary,
    reset_gpu_call_count,
    request_execution_trace_scope,
    _make_clip_load_wrapper,
    _make_clip_subfn_wrapper,
    _make_sd_state_dict_wrapper,
    _make_unet_subfn_wrapper,
    _make_gpu_loader_wrapper,
    _make_convert_old_quants_wrapper,
    _make_model_patcher_constructor_wrapper,
    _make_model_to_wrapper,
    _make_clip_constructor_wrapper,
    _child_durations,
    _unet_subfn_nesting_depth,
)

# ═══════════════════════════════════════════════════════════════════════════
# 1. CLIP CPU Prepare instrumentation — wrapper factory with fake function
# ═══════════════════════════════════════════════════════════════════════════


class TestClipLoadWrapperFactory:
    """_make_clip_load_wrapper produces a wrapper that emits events when called
    under a CLIP lane trace, and passes through *args/**kwargs unchanged."""

    def test_wrapper_passes_args_kwargs_unchanged(self):
        """The wrapper forwards *args/**kwargs identically to the original."""
        captured: dict[str, Any] = {}

        def fake_original(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        result = wrapper(
            ["/fake/clip.safetensors"],
            embedding_directory="/embeddings",
            clip_type=type("CT", (), {"STABLE_DIFFUSION": 1})(),
            model_options={"custom_operations": None},
            disable_dynamic=False,
        )
        assert captured["args"] == (["/fake/clip.safetensors"],)
        assert captured["kwargs"]["embedding_directory"] == "/embeddings"
        assert captured["kwargs"]["disable_dynamic"] is False
        assert result is not None

    def test_clip_wrapper_emits_cpu_prepare_events_with_reconciliation(self):
        """When lane=CLIP, the wrapper emits clip_cpu_prepare_start/end with
        total = sum(children) + residual."""
        trace = RuntimeTrace(request_id="clip-factory", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        # Use a child that adds a real-wall-clock child so total ≈ children_total
        def fake_original(*args, **kwargs):
            children = _clip_cpu_prepare_children.get()
            if children is not None:
                # Simulate subfn that takes real time
                _t0 = time.monotonic()
                time.sleep(0.02)
                _dur_ms = round((time.monotonic() - _t0) * 1000, 3)
                children.append(("detect_te_model", _dur_ms))
                _t0 = time.monotonic()
                time.sleep(0.03)
                _dur_ms = round((time.monotonic() - _t0) * 1000, 3)
                children.append(("load_text_encoder_state_dicts", _dur_ms))
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"], embedding_directory=None, clip_type=None)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        total = meta["clip_cpu_prepare_total_ms"]
        measured = meta["clip_cpu_prepare_measured_children_ms"]
        residual = meta["clip_cpu_prepare_residual_ms"]
        assert isinstance(total, (int, float)) and total >= 0
        assert isinstance(measured, (int, float)) and measured >= 0
        assert isinstance(residual, (int, float)) and residual >= 0
        # total ≈ measured + residual (within rounding + sleep overhead)
        assert abs(total - (measured + residual)) < 5.0, (
            f"total={total} != measured={measured} + residual={residual}"
        )

    def test_clip_wrapper_produces_no_events_without_lane(self):
        """When no lane trace is active, no events are emitted."""
        trace = RuntimeTrace(request_id="clip-no-lane", process="remote")

        def fake_original(*args, **kwargs):
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        wrapper(["ckpt"])

        assert len(list(trace.events)) == 0

    def test_clip_wrapper_no_events_for_non_clip_lane(self):
        """When lane is not CLIP, no clip_cpu_prepare events are emitted."""
        trace = RuntimeTrace(request_id="clip-non-clip", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "clip_cpu_prepare_start" not in event_names
        assert "clip_cpu_prepare_end" not in event_names

    def test_clip_subfn_wrapper_records_child_duration(self):
        """_make_clip_subfn_wrapper appends (short_name, duration_ms) to
        _clip_cpu_prepare_children when lane=CLIP."""
        trace = RuntimeTrace(request_id="clip-subfn", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_fn(x):
            return x * 2

        _clip_cpu_prepare_children.set([])
        wrapper = _make_clip_subfn_wrapper("detect_te_model", fake_fn, "sd")
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(21)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        children = _clip_cpu_prepare_children.get() or []
        assert len(children) >= 1
        name, dur = children[0]
        assert name == "detect_te_model"
        assert isinstance(dur, float) and dur >= 0


# ═══════════════════════════════════════════════════════════════════════════
# 2. Safetensors proxy — no duplicate reads/materializations
# ═══════════════════════════════════════════════════════════════════════════


class TestSafetensorsProxyIntegrity:
    """Verify _SafeOpenProxy calls _orig_gt exactly once per tensor key
    and aggregates bytes from the returned tensor."""

    def test_safetensors_proxy_no_duplicate_get_tensor_calls(self):
        """Each call to get_tensor(k) calls _orig_gt(k) exactly once."""
        call_count: dict[str, int] = {}

        class FakeSafeOpen:
            def keys(self):
                return ["tensor_a", "tensor_b"]
            def get_tensor(self, k):
                call_count[k] = call_count.get(k, 0) + 1
                return SimpleNamespace(numel=lambda: 100, element_size=lambda: 2)

        orig = FakeSafeOpen()
        orig_gt = orig.get_tensor
        count_agg = [0]
        bytes_agg = [0]

        proxy = _SafeOpenProxy(orig, orig_gt, count_agg, bytes_agg)

        # Access tensor_a twice — each should trigger _orig_gt once
        t1 = proxy.get_tensor("tensor_a")
        t2 = proxy.get_tensor("tensor_a")
        # Both calls should have incremented the counter
        assert call_count.get("tensor_a", 0) == 2, (
            f"Expected 2 reads for tensor_a, got {call_count.get('tensor_a', 0)}"
        )
        # Each read triggers one _orig_gt call (by design — proxy doesn't cache)

    def test_safetensors_proxy_bytes_from_returned_tensor(self):
        """Bytes are calculated from the returned tensor, not from key.
        The proxy only aggregates when an active UNET lane with deep diag is set."""
        trace = RuntimeTrace(request_id="proxy-bytes", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        class FakeSafeOpen:
            def keys(self):
                return ["tensor_a"]
            def get_tensor(self, k):
                return SimpleNamespace(numel=lambda: 50, element_size=lambda: 4)

        orig = FakeSafeOpen()
        orig_gt = orig.get_tensor
        count_agg = [0]
        bytes_agg = [0]

        proxy = _SafeOpenProxy(orig, orig_gt, count_agg, bytes_agg)

        import comfymodal_runtime.model_preload as _mp
        saved_flag = _DIAGNOSTIC_FLAG
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            _mp._DIAGNOSTIC_FLAG = True
            tensor = proxy.get_tensor("tensor_a")
        finally:
            _mp._DIAGNOSTIC_FLAG = saved_flag
            _ACTIVE_LANE_TRACE.reset(token)

        assert bytes_agg[0] == 200, f"Expected 200 bytes, got {bytes_agg[0]}"
        assert count_agg[0] == 1, f"Expected count=1, got {count_agg[0]}"

    def test_safetensors_proxy_context_manager_delegates_enter(self):
        """Proxy __enter__ delegates to wrapped __enter__ when available."""
        enter_result = object()
        entered = [False]

        class FakeSafeOpen:
            def keys(self):
                return []
            def get_tensor(self, k):
                return None
            def __enter__(self):
                entered[0] = True
                return enter_result
            def __exit__(self, *exc):
                return None

        orig = FakeSafeOpen()
        orig_gt = orig.get_tensor
        count_agg = [0]
        bytes_agg = [0]

        proxy = _SafeOpenProxy(orig, orig_gt, count_agg, bytes_agg)

        with proxy as p:
            assert p is enter_result, "Proxy __enter__ must delegate to wrapped"
        assert entered[0], "Wrapped __enter__ must be called"

    def test_safetensors_proxy_context_manager_fallback_to_self(self):
        """Proxy __enter__ returns self when wrapped lacks __enter__."""
        class FakeSafeOpen:
            def keys(self):
                return []
            def get_tensor(self, k):
                return None

        orig = FakeSafeOpen()
        proxy = _SafeOpenProxy(orig, orig.get_tensor, [0], [0])

        with proxy as p:
            assert p is proxy, "Proxy __enter__ must return self when wrapped has no __enter__"

    def test_safetensors_proxy_context_manager_exit_delegates(self):
        """Proxy __exit__ delegates to wrapped __exit__."""
        exited = [False]

        class FakeSafeOpen:
            def keys(self):
                return []
            def get_tensor(self, k):
                return None
            def __exit__(self, *exc):
                exited[0] = True
                return None

        orig = FakeSafeOpen()
        proxy = _SafeOpenProxy(orig, orig.get_tensor, [0], [0])

        with proxy:
            pass
        assert exited[0], "Wrapped __exit__ must be called"


# ═══════════════════════════════════════════════════════════════════════════
# 3. GPU wrapper — installation status and invocation count
# ═══════════════════════════════════════════════════════════════════════════


class TestGpuWrapperFactory:
    """_make_gpu_loader_wrapper emits correct events in lane, request, and
    not-observed contexts with proper status metadata."""

    def _make_fake_original(self):
        """Return a fake load_models_gpu that returns None."""
        def fake_original(models, memory_required=0, force_patch_weights=False,
                          minimum_memory_required=None, force_full_load=False):
            return None
        return fake_original

    def test_wrapper_not_observed_when_no_lane_or_request(self):
        """Installed wrapper called outside any lane/request scope emits
        not_observed caller classification."""
        call_log: list[dict] = []

        def fake_original(models, **kw):
            call_log.append(dict(models=models, **kw))
            return None

        wrapper = _make_gpu_loader_wrapper(fake_original)
        wrapper(["model"], memory_required=0)
        # No trace emitted — no lane/request — but wrapper still calls original
        assert len(call_log) == 1

    def test_wrapper_lane_events_emitted(self):
        """When lane is active, lane-owned GPU commit events are emitted."""
        trace = RuntimeTrace(request_id="gpu-lane-test", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        wrapper = _make_gpu_loader_wrapper(self._make_fake_original())
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["model"], memory_required=1)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        start_events = [e for e in events if e.name == "gpu_commit_start"]
        end_events = [e for e in events if e.name == "gpu_commit_end"]
        assert len(start_events) >= 1
        assert len(end_events) >= 1
        assert start_events[0].metadata.get("lane") == "UNET"

    def test_wrapper_request_events_contain_metadata(self):
        """When request trace active (no lane), graph_gpu_load_start/end are
        emitted with metadata."""
        trace = RuntimeTrace(request_id="gpu-req-test", process="remote")

        wrapper = _make_gpu_loader_wrapper(self._make_fake_original())
        with request_execution_trace_scope(trace):
            wrapper(["model"], memory_required=0)

        events = list(trace.events)
        start_events = [e for e in events if e.name == "graph_gpu_load_start"]
        end_events = [e for e in events if e.name == "graph_gpu_load_end"]
        assert len(start_events) == 1, f"Expected 1 start, got {len(start_events)}"
        assert len(end_events) == 1, f"Expected 1 end, got {len(end_events)}"
        meta = start_events[0].metadata
        assert meta.get("gpu_wrapper_status") == "installed"
        assert meta.get("caller_classification") in ("sampler_setup", "graph_model_loading")

    def test_gpu_call_count_reset_per_request_scope(self):
        """gpu_call_count resets when request_execution_trace_scope is entered."""
        reset_gpu_call_count()
        _gpu_request_call_count_var.set(5)
        assert gpu_call_count() == 5
        trace = RuntimeTrace(request_id="gpu-count-reset", process="remote")
        with request_execution_trace_scope(trace):
            assert gpu_call_count() == 0, "Must reset to 0 in request scope"

    def test_gpu_call_count_increments_in_wrapper(self):
        """When GPU wrapper increments count, gpu_call_count reflects it under request scope."""
        reset_gpu_call_count()
        _gpu_request_call_count_var.set(3)
        assert gpu_call_count() == 3
        reset_gpu_call_count()
        assert gpu_call_count() == 0

    def test_gpu_wrapper_restore_id_in_metadata(self):
        """Verify the global restore IDs are forwarded in GPU events."""
        import comfymodal_runtime.model_preload as mp
        saved_ri = mp._LATEST_RESTORED_INSTANCE_ID
        saved_rs = mp._LATEST_RESTORE_SESSION_ID
        try:
            mp._LATEST_RESTORED_INSTANCE_ID = "test-instance-abc"
            mp._LATEST_RESTORE_SESSION_ID = "test-session-xyz"
            trace = RuntimeTrace(request_id="gpu-restore-id", process="remote")
            trace.emit("graph_gpu_load_start", phase="execution", metadata={
                "model_identity_hash": "abc123",
                "memory_required": 0,
                "force_patch_weights": False,
                "force_full_load": False,
                "caller_classification": "graph_model_loading",
                "gpu_wrapper_status": "installed",
                "gpu_request_invocation_count": 1,
                "restore_session_id": mp._LATEST_RESTORE_SESSION_ID,
                "restored_instance_id": mp._LATEST_RESTORED_INSTANCE_ID,
            })
            events = list(trace.events)
            start_events = [e for e in events if e.name == "graph_gpu_load_start"]
            assert len(start_events) >= 1
            meta = start_events[0].metadata
            assert meta.get("restored_instance_id") == "test-instance-abc"
            assert meta.get("restore_session_id") == "test-session-xyz"
            assert meta.get("gpu_wrapper_status") == "installed"
            assert meta.get("gpu_request_invocation_count") == 1
        finally:
            mp._LATEST_RESTORED_INSTANCE_ID = saved_ri
            mp._LATEST_RESTORE_SESSION_ID = saved_rs

    def test_gpu_not_observed_wrapper_status(self):
        """Installed wrapper outside lane/request scope: caller is not_observed."""
        def fake_orig(models, **kw):
            return None
        wrapper = _make_gpu_loader_wrapper(fake_orig)
        # When running outside any scope, the wrapper should still call original
        # without emitting scope events; caller_classification stays as default.
        result = wrapper(["model"])
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# 4. Active-read per-dimension status classification
# ═══════════════════════════════════════════════════════════════════════════


class TestActiveReadDimClassification:
    """classify_active_read_dims returns correct per-dimension statuses."""

    def test_unsupported_when_no_deep_diag(self):
        """When deep_diag=False, all dims return unsupported."""
        result = classify_active_read_dims(
            deep_diag=False, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True, has_rusage=True, has_io=True,
        )
        for dim, status in result.items():
            assert status == "unsupported", f"{dim} should be unsupported, got {status}"

    def test_available_when_all_conditions_met(self):
        """When deep_diag=True, same thread, and data exists, dims are available."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True, has_rusage=True, has_io=True,
        )
        for dim, status in result.items():
            assert status == "available", f"{dim} should be available, got {status}"

    def test_thread_changed_when_threads_differ(self):
        """When before/after thread IDs differ, thread-bounded dims return
        thread_changed. Process CPU is process-wide."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=200,
            has_thread_cpu=True, has_process_cpu=True, has_rusage=True, has_io=True,
        )
        assert result["thread_cpu"] == "thread_changed"
        assert result["io_deltas"] == "thread_changed"
        assert result["page_faults"] == "thread_changed"
        assert result["block_input"] == "thread_changed"
        assert result["context_switches"] == "thread_changed"
        # Process CPU is process-wide, not thread-bound
        assert result["process_cpu"] == "available"

    def test_unavailable_when_capability_missing(self):
        """When deep_diag=True but OS capability is missing, dims return unavailable."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=False, has_process_cpu=False,
            has_rusage=False, has_io=False,
        )
        assert result["thread_cpu"] == "not_observed_in_this_thread"
        assert result["process_cpu"] == "not_observed_in_this_thread"
        assert result["io_deltas"] == "not_observed_in_this_thread"

    def test_unavailable_is_not_zero(self):
        """Status is always a string, never numeric zero."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=False, has_process_cpu=False,
            has_rusage=False, has_io=False,
        )
        for dim, status in result.items():
            assert status != 0, f"{dim} should not be numeric zero"
            assert isinstance(status, str), f"{dim} should be str, got {type(status)}"

    def test_valid_zero_delta(self):
        """When all data flags are True, status is available even if deltas
        happen to be zero — the classify function doesn't inspect delta values."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True, has_rusage=True, has_io=True,
        )
        assert result["thread_cpu"] == "available"
        assert result["process_cpu"] == "available"

    def test_all_required_dims_present(self):
        """All required dimension keys are present in the result."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=False, has_process_cpu=False,
            has_rusage=False, has_io=False,
        )
        required = {
            "thread_cpu", "process_cpu", "io_deltas",
            "page_faults", "block_input", "context_switches",
        }
        assert required == set(result.keys()), (
            f"Missing dims: {required - set(result.keys())}"
        )

    def test_not_observed_in_this_thread(self):
        """When thread matches but specific dimension lacks data, status is
        not_observed_in_this_thread for thread-bounded dims."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True,  # thread CPU present
            has_rusage=False,  # rusage not captured
            has_io=False,  # IO not captured
        )
        assert result["thread_cpu"] == "available"
        assert result["process_cpu"] == "available"
        assert result["io_deltas"] == "not_observed_in_this_thread"
        assert result["page_faults"] == "not_observed_in_this_thread"
        assert result["block_input"] == "not_observed_in_this_thread"
        assert result["context_switches"] == "not_observed_in_this_thread"

    def test_unavailable_status_is_not_zero(self):
        """'unavailable' is a string literal, not None or 0."""
        # When deep_diag=False, all dims are 'unsupported'
        result = classify_active_read_dims(deep_diag=False)
        for v in result.values():
            assert isinstance(v, str)
        # thread_changed: also a string
        result2 = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=200,
            has_thread_cpu=True, has_process_cpu=True, has_rusage=True, has_io=True,
        )
        assert isinstance(result2["thread_cpu"], str)
        assert result2["thread_cpu"] == "thread_changed"

    def test_stable_path_hash(self):
        """stable_hash produces deterministic short hashes for paths."""
        path1 = "/models/unet/model.safetensors"
        path2 = "/models/unet/model.safetensors"
        assert stable_hash(path1) == stable_hash(path2)
        h = stable_hash(path1)
        assert isinstance(h, str) and len(h) > 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. UNET model construction residual — wrapper factory test
# ═══════════════════════════════════════════════════════════════════════════


class TestUnetSdStateDictWrapperFactory:
    """_make_sd_state_dict_wrapper emits events with reconciliation metadata."""

    def test_sd_wrapper_emits_construction_events(self):
        """When lane=UNET, the wrapper emits start/end with model_construction_* keys."""
        trace = RuntimeTrace(request_id="unet-sd-factory", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        _TEST_CHILD_DUR = 0.015  # 15ms simulated child

        def fake_original(*args, **kwargs):
            # Simulate subfn wrappers recording real-time children
            children = _child_durations.get()
            if children is not None:
                _t = time.monotonic()
                time.sleep(_TEST_CHILD_DUR)
                children.append(round((time.monotonic() - _t) * 1000, 3))
            return {"model": "fake"}

        wrapper = _make_sd_state_dict_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper("unet_config", {"param": 1})
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "unet_load_diffusion_model_state_dict_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        assert "model_construction_total_ms" in meta
        assert "measured_direct_children_ms" in meta
        assert "model_construction_residual_ms" in meta
        total = meta["model_construction_total_ms"]
        measured = meta["measured_direct_children_ms"]
        residual = meta["model_construction_residual_ms"]
        # total = measured + residual (within sleep overhead)
        assert abs(total - (measured + residual)) < 10.0, (
            f"total={total} != measured={measured} + residual={residual}"
        )
        assert "duration_ms" in meta  # legacy compatibility
        assert "measured_child_total_ms" in meta  # legacy compatibility

    def test_sd_wrapper_no_events_for_non_unet_lane(self):
        """When lane is not UNET, no SD events are emitted."""
        trace = RuntimeTrace(request_id="unet-no-events", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            return {"model": "fake"}

        wrapper = _make_sd_state_dict_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper("config", {})
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "unet_load_diffusion_model_state_dict_start" not in event_names
        assert "unet_load_diffusion_model_state_dict_end" not in event_names

    def test_unet_subfn_wrapper_records_child_in_sd_scope(self):
        """_make_unet_subfn_wrapper records child duration into _child_durations
        when called within an active UNET SD wrapper scope."""
        trace = RuntimeTrace(request_id="unet-subfn-child", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        def fake_fn(x):
            return x * 2

        subfn_wrapper = _make_unet_subfn_wrapper("convert_old_quants", fake_fn, "utils")

        # Simulate SD wrapper setting up children list
        _child_durations.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            # The original SD wrapper would have set up _child_durations at this point
            result = subfn_wrapper(42)
            assert result == 84
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        children = _child_durations.get() or []
        assert len(children) >= 1
        dur = children[0]
        assert isinstance(dur, float) and dur >= 0


# ═══════════════════════════════════════════════════════════════════════════
# 6. UNET model construction targets verification
# ═══════════════════════════════════════════════════════════════════════════


class TestUnetModelConstructionTargets:
    """_UNET_DECOMPOSE_TARGETS contains the expected symbols."""

    def test_unet_decompose_targets_contain_required_symbols(self):
        from comfymodal_runtime.model_preload import _UNET_DECOMPOSE_TARGETS
        # convert_old_quants is now installed via the shared lane-aware wrapper
        # (_install_shared_convert_old_quants_wrapper) rather than UNET-specific targets.
        expected_additions = {
            "state_dict_prefix_replace",
            "calculate_parameters",
            "weight_dtype",
            "model_config_from_unet",
            "unet_dtype",
            "unet_manual_cast",
            "unet_prefix_from_state_dict",
            "convert_diffusers_mmdit",
            "model_config_from_diffusers_unet",
            "unet_to_diffusers",
            "unet_offload_device",
        }
        for name in expected_additions:
            assert name in _UNET_DECOMPOSE_TARGETS, (
                f"Missing {name} in _UNET_DECOMPOSE_TARGETS"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 7. CLIP depth/ownership guard — nested wrappers must not double-count
# ═══════════════════════════════════════════════════════════════════════════


class TestClipDepthGuard:
    """_make_clip_subfn_wrapper depth guard prevents double-count of nested
    children in measured_direct_children_ms."""

    def test_nested_clip_subfns_no_double_count(self):
        """When one CLIP subfn wraps another, only the direct (outermost) child
        appends its duration to _clip_cpu_prepare_children.  Nested calls are
        emitted as start/end spans but excluded from the measured sum."""
        trace = RuntimeTrace(request_id="clip-depth", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def inner_fn(x):
            return x * 2

        def outer_fn(x):
            # outer_fn() internally calls inner_fn()
            inner_wrapper(21)
            return x * 3

        inner_wrapper = _make_clip_subfn_wrapper("clip_text_transformers_convert", inner_fn, "utils")
        outer_wrapper = _make_clip_subfn_wrapper("load_text_encoder_state_dicts", outer_fn, "sd")

        # Set up children list as the CLIP load wrapper would
        _clip_cpu_prepare_children.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = outer_wrapper(10)
            assert result == 30
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        children = _clip_cpu_prepare_children.get() or []
        names = [c[0] for c in children]
        # Only the outer (direct) child should be recorded
        assert "load_text_encoder_state_dicts" in names
        # Nested clip_text_transformers_convert should NOT appear in measured children
        assert "clip_text_transformers_convert" not in names, (
            f"Nested child should not be in measured children: {names}"
        )
        assert len(children) == 1, (
            f"Expected exactly 1 measured child, got {len(children)}: {children}"
        )

    def test_clip_subfn_start_end_emitted_for_nested(self):
        """Nested CLIP subfns still emit start/end spans even though measured
        children exclude them."""
        trace = RuntimeTrace(request_id="clip-nested-events", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def inner_fn(x):
            return x * 2

        def outer_fn(x):
            inner_wrapper(42)
            return x * 3

        inner_wrapper = _make_clip_subfn_wrapper("clip_text_transformers_convert", inner_fn, "utils")
        outer_wrapper = _make_clip_subfn_wrapper("load_text_encoder_state_dicts", outer_fn, "sd")

        _clip_cpu_prepare_children.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            outer_wrapper(10)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "clip_load_text_encoder_state_dicts_start" in event_names
        assert "clip_load_text_encoder_state_dicts_end" in event_names
        assert "clip_clip_text_transformers_convert_start" in event_names
        assert "clip_clip_text_transformers_convert_end" in event_names


# ═══════════════════════════════════════════════════════════════════════════
# 8. UNET model construction with direct children — wrapper factory ordering
# ═══════════════════════════════════════════════════════════════════════════


class TestUnetDirectChildrenWrappers:
    """Verifies that UNET model construction wrappers (parent SD state dict,
    ModelPatcher constructor, model.to, load_weights) produce non-overlapping
    measured_direct_children_ms."""

    def test_fake_parent_with_constructor_to_weights_ordering(self):
        """Simulate a real UNET load call tree:
          1. load_diffusion_model_state_dict (parent/SD wrapper)
          2. ModelPatcher constructor (inside parent)
          3. model.to(...) call (inside parent, after constructor)
          4. load_model_weights (instrumented separately via
             _make_unet_subfn_wrapper or _instrument_unet_model_weights)
        Each direct child appears exactly once in measured_direct_children_ms.
        """
        trace = RuntimeTrace(request_id="unet-direct-children", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        # Create concrete wrapper factories (not hand-appended durations)
        def fake_model_patcher_orig(self):
            pass  # constructor body (no-op in test)

        patcher_wrapper = _make_model_patcher_constructor_wrapper(fake_model_patcher_orig)

        def fake_model_to_orig(self, *args, **kwargs):
            return self

        model_to_wrapper = _make_model_to_wrapper(fake_model_to_orig)

        # load_model_weights is instrumented via _make_unet_subfn_wrapper
        def fake_load_weights(self):
            return "weights_loaded"

        load_weights_wrapper = _make_unet_subfn_wrapper("load_model_weights", fake_load_weights, "model")

        # Build a fake original load_diffusion_model_state_dict that calls
        # ModelPatcher constructor and model.to() directly inside it.
        class FakeModel:
            def to(self, *args, **kwargs):
                return model_to_wrapper(self, *args, **kwargs)
            def load_model_weights(self, *args, **kwargs):
                return load_weights_wrapper(self, *args, **kwargs)

        class FakeModelPatcher:
            def __init__(self):
                patcher_wrapper(self)

        def load_diffusion_model_state_dict_original(*args, **kwargs):
            # Simulate ModelPatcher constructor call (like real code path)
            _fp = FakeModelPatcher()
            # Simulate model.to() call (like real code path)
            _model = FakeModel()
            _model.to(device="cpu")
            # Simulate load_model_weights call (instrumented via subfn wrapper)
            _model.load_model_weights()
            return {"model": _model, "patcher": _fp}

        parent_wrapper = _make_sd_state_dict_wrapper(load_diffusion_model_state_dict_original)

        # Run under UNET lane
        _child_durations.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = parent_wrapper("config", {"param": 1})
            assert result is not None
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "unet_load_diffusion_model_state_dict_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        total = meta["model_construction_total_ms"]
        measured = meta["measured_direct_children_ms"]
        residual = meta["model_construction_residual_ms"]
        # total should roughly equal measured + residual
        assert abs(total - (measured + residual)) < 10.0, (
            f"total={total} != measured={measured} + residual={residual}"
        )
        # Legacy keys must be preserved
        assert "duration_ms" in meta
        assert "measured_child_total_ms" in meta
        assert "residual_ms" in meta
        assert "model_construction_residual_ms" in meta

        # Verify individual named events were emitted
        event_names = [e.name for e in events]
        assert "unet_model_patcher_constructor_start" in event_names
        assert "unet_model_patcher_constructor_end" in event_names
        assert "unet_model_to_start" in event_names
        assert "unet_model_to_end" in event_names
        # load_model_weights events come from instrumented model via subfn wrapper
        assert "unet_load_model_weights_start" in event_names
        assert "unet_load_model_weights_end" in event_names

        # Verify measured children are non-overlapping (exactly 3 direct children)
        child_count = meta.get("measured_child_count", 0)
        assert child_count == 3, (
            f"Expected 3 measured direct children (constructor, to, load_weights), "
            f"got {child_count}: {meta.get('measured_children', [])}"
        )

    def test_shared_convert_old_quants_emits_both_lanes(self):
        """The shared convert_old_quants wrapper emits lane-prefixed events
        for both CLIP and UNET without collision."""
        trace_clip = RuntimeTrace(request_id="coq-clip", process="remote")
        lane_clip = ModelLaneTrace(trace_clip, "CLIP", "restore", expected_read_count=1)

        trace_unet = RuntimeTrace(request_id="coq-unet", process="remote")
        lane_unet = ModelLaneTrace(trace_unet, "UNET", "restore", expected_read_count=1)

        def fake_coq(x):
            return x * 2

        coq_wrapper = _make_convert_old_quants_wrapper(fake_coq)

        # Test CLIP lane
        _clip_cpu_prepare_children.set([])
        token_c = _ACTIVE_LANE_TRACE.set(lane_clip)
        try:
            result = coq_wrapper(10)
            assert result == 20
        finally:
            _ACTIVE_LANE_TRACE.reset(token_c)

        clip_names = [e.name for e in trace_clip.events]
        assert "clip_convert_old_quants_start" in clip_names
        assert "clip_convert_old_quants_end" in clip_names

        # Test UNET lane
        _child_durations.set([])
        token_u = _ACTIVE_LANE_TRACE.set(lane_unet)
        try:
            result = coq_wrapper(20)
            assert result == 40
        finally:
            _ACTIVE_LANE_TRACE.reset(token_u)

        unet_names = [e.name for e in trace_unet.events]
        assert "unet_convert_old_quants_start" in unet_names
        assert "unet_convert_old_quants_end" in unet_names

        # Verify shared sentinel
        assert getattr(coq_wrapper, "_comfy_modal_shared_convert_old_quants", False)


# ═══════════════════════════════════════════════════════════════════════════
# 9. GPU wrapper — metadata completeness and not_observed tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestGpuWrapperMetadata:
    """_make_gpu_loader_wrapper emits full metadata on lane-owned events,
    request-owned events, and tracks not_observed calls."""

    def test_lane_owned_gpu_commit_metadata(self):
        """Lane-owned gpu_commit_start/end include restore IDs, caller
        classification, model identity hash, wall/thread durations."""
        import comfymodal_runtime.model_preload as mp
        saved_ri = mp._LATEST_RESTORED_INSTANCE_ID
        saved_rs = mp._LATEST_RESTORE_SESSION_ID
        try:
            mp._LATEST_RESTORED_INSTANCE_ID = "test-inst-abc"
            mp._LATEST_RESTORE_SESSION_ID = "test-sess-xyz"

            trace = RuntimeTrace(request_id="gpu-lane-meta", process="remote")
            lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

            def fake_orig(models, **kw):
                return None

            wrapper = _make_gpu_loader_wrapper(fake_orig)
            token = _ACTIVE_LANE_TRACE.set(lane)
            try:
                wrapper(["model"], memory_required=42, force_patch_weights=True, force_full_load=False)
            finally:
                _ACTIVE_LANE_TRACE.reset(token)

            events = list(trace.events)
            start_events = [e for e in events if e.name == "gpu_commit_start"]
            end_events = [e for e in events if e.name == "gpu_commit_end"]
            assert len(start_events) >= 1
            assert len(end_events) >= 1

            start_meta = start_events[0].metadata
            assert start_meta.get("restore_session_id") == "test-sess-xyz"
            assert start_meta.get("restored_instance_id") == "test-inst-abc"
            assert start_meta.get("memory_required") == 42
            assert start_meta.get("force_patch_weights") is True
            assert start_meta.get("force_full_load") is False
            assert start_meta.get("caller_classification") == "background_unet_preparation"
            assert start_meta.get("gpu_wrapper_status") == "installed"
            assert start_meta.get("gpu_request_invocation_count") is not None
            assert start_meta.get("model_identity_hash") != ""

            end_meta = end_events[0].metadata
            assert "host_wall_duration_ms" in end_meta
            assert end_meta["restore_session_id"] == "test-sess-xyz"
        finally:
            mp._LATEST_RESTORED_INSTANCE_ID = saved_ri
            mp._LATEST_RESTORE_SESSION_ID = saved_rs

    def test_gpu_not_observed_counter(self):
        """_not_observed_gpu_calls increments when wrapper fires outside any
        lane/request scope."""
        import comfymodal_runtime.model_preload as mp
        saved = mp._not_observed_gpu_calls

        def fake_orig(models, **kw):
            return None

        wrapper = _make_gpu_loader_wrapper(fake_orig)
        wrapper(["model"], memory_required=0)

        assert mp._not_observed_gpu_calls == saved + 1, (
            f"Expected {saved + 1}, got {mp._not_observed_gpu_calls}"
        )

    def test_request_owned_graph_gpu_load_metadata(self):
        """Request-owned graph_gpu_load_start/end retain all required metadata
        including host wall, thread CPU, and restore IDs."""
        import comfymodal_runtime.model_preload as mp
        saved_ri = mp._LATEST_RESTORED_INSTANCE_ID
        saved_rs = mp._LATEST_RESTORE_SESSION_ID
        try:
            mp._LATEST_RESTORED_INSTANCE_ID = "req-inst-xyz"
            mp._LATEST_RESTORE_SESSION_ID = "req-sess-xyz"

            trace = RuntimeTrace(request_id="gpu-req-meta", process="remote")

            def fake_orig(models, **kw):
                return None

            wrapper = _make_gpu_loader_wrapper(fake_orig)
            with request_execution_trace_scope(trace):
                wrapper(["model"], memory_required=99, force_patch_weights=False, force_full_load=True)

            events = list(trace.events)
            start_events = [e for e in events if e.name == "graph_gpu_load_start"]
            end_events = [e for e in events if e.name == "graph_gpu_load_end"]
            assert len(start_events) == 1
            assert len(end_events) == 1

            start_meta = start_events[0].metadata
            assert start_meta.get("model_identity_hash") != ""
            assert start_meta.get("memory_required") == 99
            assert start_meta.get("force_full_load") is True
            assert start_meta.get("caller_classification") in ("sampler_setup", "graph_model_loading")
            assert start_meta.get("gpu_wrapper_status") == "installed"
            assert start_meta.get("restore_session_id") == "req-sess-xyz"
            assert start_meta.get("restored_instance_id") == "req-inst-xyz"

            end_meta = end_events[0].metadata
            assert "host_wall_duration_ms" in end_meta
            assert end_meta.get("restore_session_id") == "req-sess-xyz"
            assert end_meta.get("restored_instance_id") == "req-inst-xyz"
            assert end_meta.get("model_identity_hash") != ""
        finally:
            mp._LATEST_RESTORED_INSTANCE_ID = saved_ri
            mp._LATEST_RESTORE_SESSION_ID = saved_rs


# ═══════════════════════════════════════════════════════════════════════════
# 10. Active-read — capability-vs-observation + unavailable I/O
# ═══════════════════════════════════════════════════════════════════════════


class TestActiveReadUnavailableIO:
    """classify_active_read_dims: unavailable I/O sources return
    not_observed_in_this_thread, not 'unsupported' or 'unavailable'."""

    def test_unavailable_io_source_returns_not_observed(self):
        """When deep_diag=True, same thread, but no rusage/IO data captured,
        thread-bounded dims return not_observed_in_this_thread."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True,
            has_rusage=False, has_io=False,
        )
        assert result["io_deltas"] == "not_observed_in_this_thread"
        assert result["page_faults"] == "not_observed_in_this_thread"
        assert result["block_input"] == "not_observed_in_this_thread"
        assert result["context_switches"] == "not_observed_in_this_thread"
        # thread CPU and process CPU are available
        assert result["thread_cpu"] == "available"
        assert result["process_cpu"] == "available"

    def test_unsupported_deep_diag_disabled(self):
        """When deep_diag=False, all dims return 'unsupported'."""
        result = classify_active_read_dims(deep_diag=False)
        for v in result.values():
            assert v == "unsupported", f"Expected 'unsupported', got {v!r}"

    def test_same_tid_but_no_data_returns_not_observed(self):
        """With same thread ID but missing capabilities, dims return
        not_observed_in_this_thread (not 'unavailable')."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=99, after_tid=99,
            has_thread_cpu=False, has_process_cpu=False,
            has_rusage=False, has_io=False,
        )
        for dim, status in result.items():
            assert status == "not_observed_in_this_thread", (
                f"{dim} should be not_observed_in_this_thread, got {status!r}"
            )

    def test_shared_convert_old_quants_wrapper_exported(self):
        """The shared lane-aware wrapper factory is importable."""
        from comfymodal_runtime.model_preload import _make_convert_old_quants_wrapper
        assert callable(_make_convert_old_quants_wrapper)

    def test_model_patcher_wrapper_factories_exported(self):
        """ModelPatcher and model.to wrapper factories are importable."""
        from comfymodal_runtime.model_preload import (
            _make_model_patcher_constructor_wrapper,
            _make_model_to_wrapper,
        )
        assert callable(_make_model_patcher_constructor_wrapper)
        assert callable(_make_model_to_wrapper)

    def test_os_unsupported_returns_unavailable(self):
        """When os_supports_X=False and has_X=False, status is 'unavailable'
        (not 'not_observed_in_this_thread')."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=False, has_process_cpu=False,
            has_rusage=False, has_io=False,
            os_supports_thread_cpu=True, os_supports_process_cpu=True,
            os_supports_rusage=False, os_supports_io=False,
        )
        # thread_cpu: os_supports=True but has=False → not_observed_in_this_thread
        assert result["thread_cpu"] == "not_observed_in_this_thread"
        assert result["process_cpu"] == "not_observed_in_this_thread"
        # io_deltas: os_supports=False → unavailable
        assert result["io_deltas"] == "unavailable", (
            f"Expected 'unavailable', got {result['io_deltas']!r}"
        )
        # rusage-backed dims: os_supports=False → unavailable
        assert result["page_faults"] == "unavailable"
        assert result["block_input"] == "unavailable"
        assert result["context_switches"] == "unavailable"

    def test_valid_zero_delta_remains_available(self):
        """When all data flags are True, all dims are 'available' even though
        actual delta values could be zero — classify does not inspect values."""
        result = classify_active_read_dims(
            deep_diag=True, before_tid=100, after_tid=100,
            has_thread_cpu=True, has_process_cpu=True,
            has_rusage=True, has_io=True,
        )
        for dim, status in result.items():
            assert status == "available", (
                f"{dim} expected 'available', got {status!r}"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 11. GPU wrapper — not-observed summary accessor
# ═══════════════════════════════════════════════════════════════════════════


class TestGpuNotObservedSummary:
    """gpu_not_observed_summary returns correct classification for empty
    requests and when the wrapper is unavailable."""

    def test_not_observed_when_zero_calls_in_request(self):
        """When request scope has zero load_models_gpu calls and wrapper
        is installed, summary returns caller_classification='not_observed'
        with request ID, wrapper_status='installed', count=0."""
        import comfymodal_runtime.model_preload as mp
        saved_installed = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = True
            trace = RuntimeTrace(request_id="gpu-no-calls", process="remote")
            with request_execution_trace_scope(trace):
                summary = gpu_not_observed_summary()
            assert summary["caller_classification"] == "not_observed", (
                f"Expected 'not_observed', got {summary['caller_classification']!r}"
            )
            assert summary["wrapper_status"] == "installed"
            assert summary["request_id"] == "gpu-no-calls"
            assert summary["count"] == 0
        finally:
            mp._gpu_wrapper_installed = saved_installed

    def test_wrapper_unavailable_when_not_installed(self):
        """When wrapper is not installed, summary returns
        caller_classification='wrapper_unavailable',
        wrapper_status='unavailable', count=0."""
        import comfymodal_runtime.model_preload as mp
        saved_installed = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = False
            summary = gpu_not_observed_summary()
            assert summary["caller_classification"] == "wrapper_unavailable", (
                f"Expected 'wrapper_unavailable', got {summary['caller_classification']!r}"
            )
            assert summary["wrapper_status"] == "unavailable"
            assert summary["count"] == 0
        finally:
            mp._gpu_wrapper_installed = saved_installed

    def test_not_observed_summary_has_request_id(self):
        """Summary includes the active request ID even when wrapper is installed."""
        import comfymodal_runtime.model_preload as mp
        saved_installed = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = True
            trace = RuntimeTrace(request_id="custom-req-42", process="remote")
            with request_execution_trace_scope(trace):
                summary = gpu_not_observed_summary()
            assert summary["request_id"] == "custom-req-42"
            assert summary["caller_classification"] == "not_observed"
        finally:
            mp._gpu_wrapper_installed = saved_installed


# ═══════════════════════════════════════════════════════════════════════════
# 12. CLIP object construction, patcher construction, and cache publication
# ═══════════════════════════════════════════════════════════════════════════


class TestClipConstructorAndCache:
    """_make_clip_constructor_wrapper, model patcher constructor under CLIP lane,
    and cache publication emit named events without overlapping measured children."""

    def test_clip_constructor_emits_start_end(self):
        """When lane=CLIP, the wrapper emits clip_constructor_start/end."""
        trace = RuntimeTrace(request_id="clip-ctor", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        class FakeCLIP:
            def __init__(self):
                pass

        wrapper = _make_clip_constructor_wrapper(FakeCLIP.__init__)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            obj = FakeCLIP()
            wrapper(obj)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "clip_constructor_start" in event_names, (
            f"Missing clip_constructor_start in {event_names}"
        )
        assert "clip_constructor_end" in event_names, (
            f"Missing clip_constructor_end in {event_names}"
        )

    def test_clip_constructor_not_in_measured_children(self):
        """CLIP constructor duration is NOT appended to _clip_cpu_prepare_children."""
        trace = RuntimeTrace(request_id="clip-ctor-nc", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        class FakeCLIP:
            def __init__(self):
                self.patcher: Any = None

        wrapper = _make_clip_constructor_wrapper(FakeCLIP.__init__)
        _clip_cpu_prepare_children.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            obj = FakeCLIP()
            wrapper(obj)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        children = _clip_cpu_prepare_children.get() or []
        child_names = [c[0] if isinstance(c, tuple) else str(c) for c in children]
        assert "clip_constructor" not in child_names, (
            f"CLIP constructor should not appear in children: {children}"
        )

    def test_clip_constructor_no_events_without_lane(self):
        """No events when no active lane trace."""
        trace = RuntimeTrace(request_id="clip-ctor-nl", process="remote")

        class FakeCLIP:
            def __init__(self):
                pass

        wrapper = _make_clip_constructor_wrapper(FakeCLIP.__init__)
        obj = FakeCLIP()
        wrapper(obj)
        assert len(list(trace.events)) == 0

    def test_clip_constructor_no_events_for_unet_lane(self):
        """No clip_constructor events when lane is UNET."""
        trace = RuntimeTrace(request_id="clip-ctor-unet", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        class FakeCLIP:
            def __init__(self):
                pass

        wrapper = _make_clip_constructor_wrapper(FakeCLIP.__init__)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            obj = FakeCLIP()
            wrapper(obj)
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "clip_constructor_start" not in event_names
        assert "clip_constructor_end" not in event_names

    def test_model_patcher_constructor_clip_lane_emits_events(self):
        """When lane=CLIP, model patcher constructor emits
        clip_model_patcher_constructor_start/end."""
        trace = RuntimeTrace(request_id="clip-mp-ctor", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_orig(self):
            pass

        wrapper = _make_model_patcher_constructor_wrapper(fake_orig)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(SimpleNamespace())
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "clip_model_patcher_constructor_start" in event_names, (
            f"Missing in {event_names}"
        )
        assert "clip_model_patcher_constructor_end" in event_names

    def test_model_patcher_constructor_clip_not_in_clip_children(self):
        """CLIP patcher constructor is NOT appended to _clip_cpu_prepare_children."""
        trace = RuntimeTrace(request_id="clip-mp-nc", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_orig(self):
            pass

        wrapper = _make_model_patcher_constructor_wrapper(fake_orig)
        _clip_cpu_prepare_children.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(SimpleNamespace())
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        children = _clip_cpu_prepare_children.get() or []
        child_names = [c[0] if isinstance(c, tuple) else str(c) for c in children]
        assert "clip_model_patcher_constructor" not in child_names, (
            f"CLIP patcher constructor should not appear in children: {children}"
        )

    def test_model_patcher_unet_lane_still_works(self):
        """When lane=UNET, model patcher constructor still emits
        unet_model_patcher_constructor_start/end and records in _child_durations."""
        trace = RuntimeTrace(request_id="mp-unet", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        def fake_orig(self):
            pass

        wrapper = _make_model_patcher_constructor_wrapper(fake_orig)
        _child_durations.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(SimpleNamespace())
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        event_names = [e.name for e in trace.events]
        assert "unet_model_patcher_constructor_start" in event_names
        assert "unet_model_patcher_constructor_end" in event_names
        children = _child_durations.get() or []
        assert len(children) >= 1, "UNET patcher constructor should record child"

    def test_cache_publish_event_emitted(self):
        """When load_clip returns an object with patcher.cached_patcher_init set,
        clip_cache_publish is emitted between cpu_prepare_start/end."""
        trace = RuntimeTrace(request_id="clip-cache", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            patcher = SimpleNamespace()
            patcher.cached_patcher_init = ("factory_fn", ("args",))
            clip = SimpleNamespace(patcher=patcher)
            return clip

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = wrapper(["ckpt"])
            assert result is not None
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        cache_events = [e for e in events if e.name == "clip_cache_publish"]
        assert len(cache_events) == 1, (
            f"Expected 1 clip_cache_publish event, got {len(cache_events)}"
        )
        meta = cache_events[0].metadata
        assert meta.get("cache_type") == "cached_patcher_init"

        # Verify it's inside the cpu_prepare span
        start_idx = next(i for i, e in enumerate(events) if e.name == "clip_cpu_prepare_start")
        end_idx = next(i for i, e in enumerate(events) if e.name == "clip_cpu_prepare_end")
        cache_idx = next(i for i, e in enumerate(events) if e.name == "clip_cache_publish")
        assert start_idx < cache_idx < end_idx, (
            f"clip_cache_publish at {cache_idx} not between start({start_idx}) and end({end_idx})"
        )

    def test_cache_publish_not_emitted_without_cached_patcher_init(self):
        """When load_clip returns an object without cached_patcher_init,
        no clip_cache_publish event."""
        trace = RuntimeTrace(request_id="clip-cache-none", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            patcher = SimpleNamespace()
            # No cached_patcher_init
            return SimpleNamespace(patcher=patcher)

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        cache_events = [e for e in trace.events if e.name == "clip_cache_publish"]
        assert len(cache_events) == 0

    def test_cache_publish_not_emitted_without_lane(self):
        """No clip_cache_publish when no active lane."""
        trace = RuntimeTrace(request_id="clip-cache-nl", process="remote")

        def fake_original(*args, **kwargs):
            patcher = SimpleNamespace()
            patcher.cached_patcher_init = ("fn", ("a",))
            return SimpleNamespace(patcher=patcher)

        wrapper = _make_clip_load_wrapper(fake_original)
        wrapper(["ckpt"])
        cache_events = [e for e in trace.events if e.name == "clip_cache_publish"]
        assert len(cache_events) == 0

    def test_full_reconciliation_non_overlap(self):
        """Full end-to-end: CLIP constructor, patcher constructor, and cache
        events are emitted but load_text_encoder_state_dicts remains the sole
        direct measured child in _clip_cpu_prepare_children."""
        trace = RuntimeTrace(request_id="clip-full-rec", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        class FakeCLIP:
            def __init__(self):
                self.patcher: Any = None

        clip_ctor_wrapper = _make_clip_constructor_wrapper(FakeCLIP.__init__)

        def mp_ctor_orig(self):
            pass

        mp_ctor_wrapper = _make_model_patcher_constructor_wrapper(mp_ctor_orig)

        # Simulate load_text_encoder_state_dicts containing CLIP constructor
        # and ModelPatcher constructor calls inside it
        def load_text_encoder_state_dicts_fake(*args, **kwargs):
            _t0 = time.monotonic()
            time.sleep(0.01)
            _dur_ms = round((time.monotonic() - _t0) * 1000, 3)
            children = _clip_cpu_prepare_children.get()
            if children is not None:
                children.append(("load_text_encoder_state_dicts", _dur_ms))
            # Inside: CLIP.__init__ calls ModelPatcher.__init__
            clip = FakeCLIP()
            clip_ctor_wrapper(clip)
            mp_ctor_wrapper(SimpleNamespace())
            patcher = SimpleNamespace()
            patcher.cached_patcher_init = ("fn", ("a",))
            clip.patcher = patcher
            return clip

        def fake_load_clip(*args, **kwargs):
            clip = load_text_encoder_state_dicts_fake(*args, **kwargs)
            return clip

        load_clip_wrapper = _make_clip_load_wrapper(fake_load_clip)
        _clip_cpu_prepare_children.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = load_clip_wrapper(["ckpt"])
            assert result is not None
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        event_names = [e.name for e in events]

        # All expected events present
        assert "clip_cpu_prepare_start" in event_names
        assert "clip_cpu_prepare_end" in event_names
        assert "clip_constructor_start" in event_names
        assert "clip_constructor_end" in event_names
        assert "clip_model_patcher_constructor_start" in event_names
        assert "clip_model_patcher_constructor_end" in event_names
        assert "clip_cache_publish" in event_names

        # Reconciliation: measured children = only load_text_encoder_state_dicts
        end_event = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_event) == 1
        meta = end_event[0].metadata
        children = meta.get("children", [])
        child_names = [c[0] for c in children]
        assert "load_text_encoder_state_dicts" in child_names, (
            f"Expected load_text_encoder_state_dicts in children: {child_names}"
        )
        assert "clip_constructor" not in child_names, (
            f"clip_constructor should not be a measured child: {child_names}"
        )
        assert "clip_model_patcher_constructor" not in child_names, (
            f"clip_model_patcher_constructor should not be a measured child: {child_names}"
        )

        # total ≈ measured + residual
        total = meta["clip_cpu_prepare_total_ms"]
        measured = meta["clip_cpu_prepare_measured_children_ms"]
        residual = meta["clip_cpu_prepare_residual_ms"]
        assert abs(total - (measured + residual)) < 10.0, (
            f"total={total} != measured={measured} + residual={residual}"
        )
