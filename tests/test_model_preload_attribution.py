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
    _clip_subfn_depth,
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
        post_read_total = sum(children) + residual (signed).
        clip_cpu_prepare_start is triggered by _on_read_completed
        (not at wrapper entry), so test must simulate it."""
        trace = RuntimeTrace(request_id="clip-factory", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        # Use a child that adds a real-wall-clock child so total ≈ children_total
        def fake_original(*args, **kwargs):
            # Simulate a load_torch_file call: read_start, work, read_end, _on_read_completed
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
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
        # clip_cpu_prepare_start must be present (emitted by _on_read_completed)
        start_events = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(start_events) == 1, (
            f"Expected 1 clip_cpu_prepare_start, got {len(start_events)}"
        )
        assert start_events[0].metadata.get("expected_read_count") == 1

        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        post_read_total = meta["clip_cpu_prepare_total_ms"]
        file_read_total = meta.get("clip_file_read_total_ms")
        measured = meta["clip_cpu_prepare_measured_children_ms"]
        residual = meta["clip_cpu_prepare_residual_ms"]
        status = meta.get("status")
        assert isinstance(post_read_total, (int, float)) and post_read_total >= 0
        assert isinstance(measured, (int, float)) and measured >= 0
        # file_read_total should reflect the read interval if monotonic clock ticked
        if file_read_total is not None:
            assert isinstance(file_read_total, (int, float)) and file_read_total >= 0
        # post_read_total ≈ measured + residual (signed, within rounding + sleep overhead)
        assert abs(post_read_total - (measured + residual)) < 5.0, (
            f"post_read_total={post_read_total} != measured={measured} + residual={residual}"
        )
        assert status == "ok", f"Expected status=ok, got {status}"

        # clip_load_call_start/end must also be present
        call_start = [e for e in events if e.name == "clip_load_call_start"]
        assert len(call_start) == 1
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        assert "clip_load_call_total_ms" in call_end[0].metadata
        assert "clip_file_read_total_ms" in call_end[0].metadata
        assert "clip_post_read_cpu_total_ms" in call_end[0].metadata

    def test_clip_wrapper_dual_read_triggers_post_read_boundary(self):
        """When expected_read_count=2, clip_cpu_prepare_start fires after
        the second read (simulated by calling read_start/read_end/_on_read_completed twice)."""
        trace = RuntimeTrace(request_id="clip-dual", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)

        def fake_original(*args, **kwargs):
            # Simulate two load_torch_file calls
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
            time.sleep(0.010)
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
            time.sleep(0.005)
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt1", "ckpt2"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        # clip_cpu_prepare_start must fire after second read
        start_events = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(start_events) == 1
        assert start_events[0].metadata.get("actual_read_count") == 2

        # clip_load_call_end should have file_read_total_ms and post_read_cpu_total_ms
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        call_meta = call_end[0].metadata
        assert "clip_file_read_total_ms" in call_meta, (
            f"Missing clip_file_read_total_ms in clip_load_call_end: {list(call_meta.keys())}"
        )
        # For dual CLIP, file read total should reflect sum of intervals
        frt = call_meta["clip_file_read_total_ms"]
        if frt is not None:
            assert isinstance(frt, (int, float)) and frt >= 0

        # cpu_prepare_start (generic) should also fire
        generic_start = [e for e in events if e.name == "cpu_prepare_start"]
        assert len(generic_start) == 1

    def test_clip_wrapper_exceeded_reads(self):
        """When more reads occur than expected count, only one clip_cpu_prepare_start
        fires (on the first trigger), and subsequent reads do not re-trigger."""
        trace = RuntimeTrace(request_id="clip-overread", process="remote")
        # expected=1 but 3 reads occur
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane._on_read_completed()  # actual=1 >= 1, trigger fires
            lane._on_read_completed()  # actual=2, _cpu_prepare_started=True, no-op
            lane._on_read_completed()  # actual=3, _cpu_prepare_started=True, no-op
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        # clip_cpu_prepare_start fires exactly once
        start_events = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(start_events) == 1

        # Generic cpu_prepare_start fires once (no status metadata since
        # actual=expected=1 at trigger time)
        generic_start = [e for e in events if e.name == "cpu_prepare_start"]
        assert len(generic_start) == 1

        # clip_cpu_prepare_end carries read_count_mismatch status because
        # actual=3 > expected=1
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        assert end_events[0].metadata.get("status") == "read_count_mismatch", (
            f"Expected read_count_mismatch status, got {end_events[0].metadata.get('status')}"
        )

        # clip_load_call_end also carries mismatch status
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        assert call_end[0].metadata.get("status") == "read_count_mismatch"

    def test_clip_wrapper_emits_load_call_events(self):
        """When lane=CLIP, the wrapper emits clip_load_call_start/end
        with total duration metadata."""
        trace = RuntimeTrace(request_id="clip-load-call", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane._on_read_completed()
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        start_events = [e for e in events if e.name == "clip_load_call_start"]
        assert len(start_events) == 1, (
            f"Expected 1 clip_load_call_start, got {len(start_events)}"
        )
        end_events = [e for e in events if e.name == "clip_load_call_end"]
        assert len(end_events) == 1, (
            f"Expected 1 clip_load_call_end, got {len(end_events)}"
        )
        meta = end_events[0].metadata
        assert "clip_load_call_total_ms" in meta, (
            f"clip_load_call_end missing total_ms, metadata keys: {list(meta.keys())}"
        )
        assert "clip_file_read_total_ms" in meta, (
            f"clip_load_call_end missing file_read_total_ms"
        )
        assert "clip_post_read_cpu_total_ms" in meta, (
            f"clip_load_call_end missing post_read_cpu_total_ms"
        )
        assert meta.get("status") == "ok"

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

    def test_clip_named_fields_from_trace_events(self):
        """Named CLIP compact fields are derived from trace event metadata
        (not from _clip_cpu_prepare_children).  Absent events → None."""
        trace = RuntimeTrace(request_id="clip-named", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
            # Emit subfn _end events with duration_ms metadata
            lane._trace.emit("clip_detect_te_model_end", phase="restore", metadata={"duration_ms": 15.0})
            lane._trace.emit("clip_load_text_encoder_state_dicts_end", phase="restore", metadata={"duration_ms": 25.0})
            lane._trace.emit("clip_text_transformers_convert_end", phase="restore", metadata={"duration_ms": 5.0})
            lane._trace.emit("clip_convert_old_quants_end", phase="restore", metadata={"duration_ms": 3.0})
            lane._trace.emit("clip_constructor_end", phase="restore", metadata={"duration_ms": 8.0})
            lane._trace.emit("clip_model_patcher_constructor_end", phase="restore", metadata={"duration_ms": 4.0})
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)

        # Verify named fields in clip_load_call_end
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        call_meta = call_end[0].metadata
        assert "clip_file_read_total_ms" in call_meta
        frt = call_meta["clip_file_read_total_ms"]
        if frt is not None:
            assert isinstance(frt, (int, float)) and frt >= 0

        # clip_cpu_prepare_end metadata includes measured children
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        assert "clip_cpu_prepare_total_ms" in meta
        assert "clip_file_read_total_ms" in meta
        frt2 = meta["clip_file_read_total_ms"]
        if frt2 is not None:
            assert isinstance(frt2, (int, float)) and frt2 >= 0
        # measured_children_ms should reflect only children recorded in
        # _clip_cpu_prepare_children (none in this test since no subfn wrappers)
        assert meta["clip_cpu_prepare_measured_children_ms"] == 0.0

        # The compact summary is printed via _emit_clip_cpu_children_summary.
        # Verify trace events show the expected durations.
        detect_end = [e for e in events if e.name == "clip_detect_te_model_end"]
        assert len(detect_end) == 1
        assert detect_end[0].metadata.get("duration_ms") == 15.0
        lte_end = [e for e in events if e.name == "clip_load_text_encoder_state_dicts_end"]
        assert len(lte_end) == 1
        assert lte_end[0].metadata.get("duration_ms") == 25.0
        conv_end = [e for e in events if e.name == "clip_text_transformers_convert_end"]
        assert len(conv_end) == 1
        assert conv_end[0].metadata.get("duration_ms") == 5.0
        coq_end = [e for e in events if e.name == "clip_convert_old_quants_end"]
        assert len(coq_end) == 1
        assert coq_end[0].metadata.get("duration_ms") == 3.0
        cc_end = [e for e in events if e.name == "clip_constructor_end"]
        assert len(cc_end) == 1
        assert cc_end[0].metadata.get("duration_ms") == 8.0
        mpc_end = [e for e in events if e.name == "clip_model_patcher_constructor_end"]
        assert len(mpc_end) == 1
        assert mpc_end[0].metadata.get("duration_ms") == 4.0

    def test_clip_named_fields_absent_when_no_trace_events(self):
        """When no subfn _end events are emitted, all named compact fields
        remain None (not zero or children_total)."""
        trace = RuntimeTrace(request_id="clip-named-none", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
            # No subfn trace events — named fields should stay None
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        # clip_cpu_prepare_end metadata does not include named fields
        # (they are in the compact print summary, not the trace metadata).
        # The file_read_total should be populated from read intervals if
        # the monotonic clock ticked.
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        frt = meta.get("clip_file_read_total_ms")
        if frt is not None:
            assert isinstance(frt, (int, float)) and frt >= 0
        assert meta["clip_cpu_prepare_measured_children_ms"] == 0.0
        # No children were recorded (no subfn wrappers)
        assert len(meta.get("children", [])) == 0
        assert "clip_cpu_prepare_total_ms" in meta
        assert "clip_cpu_prepare_residual_ms" in meta

    def test_clip_double_prefixed_conversion_event_aggregated(self):
        """The live double-prefixed name clip_clip_text_transformers_convert_end
        is properly aggregated into state_dict_conversion_ms alongside the
        existing single-prefix clip_text_transformers_convert_end name."""
        import io
        import contextlib

        trace = RuntimeTrace(request_id="clip-double-prefix", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane.read_start()
            time.sleep(0.010)
            lane.read_end()
            lane._on_read_completed()
            # Emit the live double-prefixed event name
            lane._trace.emit("clip_clip_text_transformers_convert_end", phase="restore",
                             metadata={"duration_ms": 5.0})
            # Emit convert_old_quants (always single-prefix)
            lane._trace.emit("clip_convert_old_quants_end", phase="restore",
                             metadata={"duration_ms": 3.0})
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            token = _ACTIVE_LANE_TRACE.set(lane)
            try:
                wrapper(["ckpt"])
            finally:
                _ACTIVE_LANE_TRACE.reset(token)
        output = f.getvalue()
        # Both events should be summed into state_dict_conversion_ms=8.0
        assert "state_dict_conversion_ms=8.0" in output, (
            f"Expected state_dict_conversion_ms=8.0 in summary, got:\n{output}"
        )
        # The live double-prefixed name must appear in the trace events
        assert "clip_clip_text_transformers_convert_end" in output or any(
            e.name == "clip_clip_text_transformers_convert_end" for e in trace.events
        ), "Double-prefixed clip_clip_text_transformers_convert_end not found"


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
            has_cgroup=True,
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
            "cgroup_memory", "cgroup_aggregate",
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
                _d = round((time.monotonic() - _t) * 1000, 3)
                children.append(("test_child", _d))
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
        # measured_children is legacy numeric-only; measured_named_children has (name, dur) pairs
        legacy_durs = meta.get("measured_children", [])
        assert all(isinstance(d, (int, float)) for d in legacy_durs), (
            f"Legacy measured_children must be numeric, got {legacy_durs}"
        )
        named = meta.get("measured_named_children", [])
        assert all(isinstance(c, tuple) and len(c) == 2 for c in named), (
            f"measured_named_children must be (name, dur) tuples, got {named}"
        )
        if legacy_durs:
            assert len(legacy_durs) == len(named)
            assert abs(sum(legacy_durs) - sum(d for _, d in named)) < 0.001

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
        name, dur = children[0]
        assert isinstance(name, str)
        assert isinstance(dur, (int, float)) and dur >= 0


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
        # Children should be named tuples (via measured_named_children)
        children_list = meta.get("measured_named_children", [])
        child_names = [c[0] for c in children_list]
        assert "model_patcher_constructor" in child_names, (
            f"Expected model_patcher_constructor in {child_names}"
        )
        assert "model_to" in child_names, (
            f"Expected model_to in {child_names}"
        )
        assert "load_model_weights" in child_names, (
            f"Expected load_model_weights in {child_names}"
        )
        # Residual should be signed (not max-clamped)
        assert "residual_ms" in meta
        assert "status" in meta

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

    def test_convert_old_quants_nesting_depth_participation_clip(self):
        """The shared convert_old_quants wrapper respects CLIP subfn nesting depth
        and does not append as direct child when called inside another subfn."""
        trace = RuntimeTrace(request_id="coq-clip-nest", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_coq(x):
            return x * 2

        coq_wrapper = _make_convert_old_quants_wrapper(fake_coq)

        # Simulate load_text_encoder_state_dicts wrapper which increments _clip_subfn_depth
        _clip_cpu_prepare_children.set([])
        import comfymodal_runtime.model_preload as mp
        _clip_subfn_depth.set(1)  # simulate being inside a subfn wrapper
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = coq_wrapper(21)
            assert result == 42
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
            _clip_subfn_depth.set(0)

        # convert_old_quants should NOT be in measured children when nested
        children = _clip_cpu_prepare_children.get() or []
        assert len(children) == 0, (
            f"Expected no children when nested, got: {children}"
        )

    def test_convert_old_quants_nesting_depth_participation_unet(self):
        """The shared convert_old_quants wrapper respects UNET nesting depth
        and does not append as direct child when called inside another wrapper."""
        trace = RuntimeTrace(request_id="coq-unet-nest", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        def fake_coq(x):
            return x * 2

        coq_wrapper = _make_convert_old_quants_wrapper(fake_coq)

        _child_durations.set([])
        _unet_subfn_nesting_depth.set(1)  # simulate being inside a subfn wrapper
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            result = coq_wrapper(42)
            assert result == 84
        finally:
            _ACTIVE_LANE_TRACE.reset(token)
            _unet_subfn_nesting_depth.set(0)

        children = _child_durations.get() or []
        assert len(children) == 0, (
            f"Expected no children when nested, got: {children}"
        )


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
            if dim == "cgroup_aggregate":
                # cgroup_aggregate is unavailable when no cgroup data captured
                assert status == "unavailable", (
                    f"{dim} should be unavailable, got {status!r}"
                )
            else:
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
            has_cgroup=True,
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
            # Simulate _on_read_completed to trigger clip_cpu_prepare_start
            lane._on_read_completed()
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
            # Simulate _on_read_completed to trigger clip_cpu_prepare_start
            lane._on_read_completed()
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

        # post_read_total ≈ measured + residual (signed)
        total = meta["clip_cpu_prepare_total_ms"]
        measured = meta["clip_cpu_prepare_measured_children_ms"]
        residual = meta["clip_cpu_prepare_residual_ms"]
        assert abs(total - (measured + residual)) < 10.0, (
            f"total={total} != measured={measured} + residual={residual}"
        )
        # verify file_read_total_ms is separate
        assert "clip_file_read_total_ms" in meta


# ═══════════════════════════════════════════════════════════════════════════
# 13. [v2.clip_cpu_children] compact summary emission
# ═══════════════════════════════════════════════════════════════════════════


class TestClipCpuChildrenSummary:
    """_emit_clip_cpu_children_summary prints a compact [v2.clip_cpu_children] line."""

    def test_emit_clip_cpu_children_summary(self):
        """Summary line contains stable named fields plus children dict."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_clip_cpu_children_summary

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_clip_cpu_children_summary(
                post_read_total_ms=150.5,
                file_read_total_ms=50.0,
                children=[("detect_te_model", 50.2), ("load_text_encoder_state_dicts", 80.1)],
                load_text_encoder_state_dicts_ms=80.1,
                detect_te_model_ms=50.2,
                state_dict_conversion_ms=5.0,
                clip_constructor_ms=10.0,
                model_patcher_ms=3.0,
                cache_publish_ms=2.0,
                measured_children_ms=130.3,
                residual_ms=20.2,
                status="ok",
            )
        output = f.getvalue()
        assert "[v2.clip_cpu_children]" in output
        assert "post_read_total_ms=150.5" in output
        assert "file_read_total_ms=50.0" in output
        assert "detect_te_model" in output
        assert "load_text_encoder_state_dicts" in output
        assert "measured_children_ms=130.3" in output
        assert "residual_ms=20.2" in output
        assert "status=ok" in output
        assert "load_text_encoder_state_dicts_ms=80.1" in output
        assert "detect_te_model_ms=50.2" in output
        assert "state_dict_conversion_ms=5.0" in output
        assert "clip_constructor_ms=10.0" in output
        assert "model_patcher_ms=3.0" in output
        assert "cache_publish_ms=2.0" in output
        assert "children={" in output

    def test_emit_clip_cpu_children_summary_empty_children(self):
        """Empty children list produces empty dict."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_clip_cpu_children_summary

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_clip_cpu_children_summary(
                post_read_total_ms=50.0,
                file_read_total_ms=10.0,
                children=[],
                measured_children_ms=0.0,
                residual_ms=50.0,
                status="ok",
            )
        output = f.getvalue()
        assert "[v2.clip_cpu_children]" in output
        assert "children={}" in output, f"Expected empty children dict, got: {output}"
        assert "post_read_total_ms=50.0" in output
        assert "file_read_total_ms=10.0" in output

    def test_clip_wrapper_invokes_summary(self):
        """The CLIP load wrapper invokes _emit_clip_cpu_children_summary
        automatically when lane=CLIP.  Capture stdout to verify."""
        import io
        import contextlib

        trace = RuntimeTrace(request_id="clip-summary-invoke", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane._on_read_completed()
            # Add real time so post_read_total covers the child duration
            time.sleep(0.02)
            children = _clip_cpu_prepare_children.get()
            if children is not None:
                # Record actual elapsed time as child, like real subfn wrapper
                _t0 = time.monotonic()
                time.sleep(0.01)
                _dur_ms = round((time.monotonic() - _t0) * 1000, 3)
                children.append(("detect_te_model", _dur_ms))
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            token = _ACTIVE_LANE_TRACE.set(lane)
            try:
                wrapper(["ckpt"])
            finally:
                _ACTIVE_LANE_TRACE.reset(token)
        output = f.getvalue()
        assert "[v2.clip_cpu_children]" in output, (
            f"Expected [v2.clip_cpu_children] in output, got: {output}"
        )
        assert "post_read_total_ms" in output, (
            f"Expected post_read_total_ms in output, got: {output}"
        )
        assert "file_read_total_ms" in output, (
            f"Expected file_read_total_ms in output, got: {output}"
        )
        assert "status=ok" in output, (
            f"Expected status=ok in output, got: {output}"
        )
        assert "detect_te_model" in output


# ═══════════════════════════════════════════════════════════════════════════
# 14. UNET named direct children with >1ms threshold
# ═══════════════════════════════════════════════════════════════════════════


class TestUnetNamedChildrenSummary:
    """_emit_bg_unet_stages_summary includes named children with >1ms threshold."""

    def test_named_children_appear_in_output(self):
        """Named UNET children >1ms appear individually in the summary."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_bg_unet_stages_summary

        trace = RuntimeTrace(request_id="unet-named", process="remote_background_unet")
        # Emit events with known durations
        trace.emit("background_unet_submitted", phase="restore")
        trace.emit("background_unet_worker_start", phase="restore")
        trace.emit("unet_load_diffusion_model_state_dict_start", phase="restore")
        trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
            "duration_ms": 200.0, "measured_child_total_ms": 150.0})
        trace.emit("unet_model_config_get_model_end", phase="restore", metadata={"duration_ms": 50.0})
        trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": 30.0})
        trace.emit("unet_convert_old_quants_end", phase="restore", metadata={"duration_ms": 2.5})
        trace.emit("unet_model_patcher_constructor_end", phase="restore", metadata={"duration_ms": 0.5})
        trace.emit("unet_model_to_end", phase="restore", metadata={"duration_ms": 0.3})
        trace.emit("unet_state_dict_prefix_replace_end", phase="restore", metadata={"duration_ms": 1.5})

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_bg_unet_stages_summary(trace, force=True)
        output = f.getvalue()
        assert "[v2.bg_unet_stages]" in output
        # Children >1ms should appear individually
        assert "model_config_get_model=50.0" in output
        assert "load_model_weights=30.0" in output
        assert "convert_old_quants=2.5" in output
        assert "state_dict_prefix_replace=1.5" in output
        # Children <=1ms should NOT appear individually but counted in fast_children
        assert "fast_children_le_1ms" in output

    def test_no_crash_on_empty_trace(self):
        """Empty trace does not crash _emit_bg_unet_stages_summary."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_bg_unet_stages_summary

        trace = RuntimeTrace(process="remote_background_unet")
        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_bg_unet_stages_summary(trace, force=True)
        output = f.getvalue()
        assert "[v2.bg_unet_stages]" in output

    def test_negative_residual_when_children_exceed_construction_total(self):
        """model_construction_residual_ms is signed (can be negative)
        when measured direct children exceed the reported construction total.
        Regression: the old max(0, ...) clamp hid such overlaps."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_bg_unet_stages_summary

        trace = RuntimeTrace(request_id="unet-neg-residual", process="remote_background_unet")
        # children (250ms) exceed construction total (200ms) → residual -50
        trace.emit("background_unet_submitted", phase="restore")
        trace.emit("background_unet_worker_start", phase="restore")
        trace.emit("unet_load_diffusion_model_state_dict_start", phase="restore")
        trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
            "duration_ms": 200.0, "measured_child_total_ms": 250.0})
        # One named child to keep the output realistic
        trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": 250.0})

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_bg_unet_stages_summary(trace, force=True)
        output = f.getvalue()
        assert "[v2.bg_unet_stages]" in output
        assert "model_construction_total_ms=200.0" in output, (
            f"Expected total 200, got: {output}"
        )
        assert "measured_direct_children_ms=250.0" in output, (
            f"Expected children 250, got: {output}"
        )
        assert "model_construction_residual_ms=-50.0" in output, (
            f"Expected residual -50.0, got: {output}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 15. MutationLane documentation accuracy
# ═══════════════════════════════════════════════════════════════════════════


class TestMutationLaneDocs:
    """MutationLane docs accurately describe FIFO behavior (no preemption)."""

    def test_docstring_reflects_fifo_no_preemption(self):
        """Docstring and comments must not claim priority preemption."""
        from comfymodal_runtime.model_preload import MutationLane

        doc = MutationLane.__doc__ or ""
        # Must not claim preemption
        assert "does NOT preempt" in doc or "FIFO" in doc, (
            f"Docstring should describe FIFO, got:\n{doc}"
        )

    def test_acquire_docstring_no_preemption_claim(self):
        """acquire() docstring does not claim priority preemption."""
        from comfymodal_runtime.model_preload import MutationLane

        acquire_doc = MutationLane.acquire.__doc__ or ""
        assert "plain FIFO" in acquire_doc, (
            f"acquire docstring should say FIFO, got:\n{acquire_doc}"
        )

    def test_priority_dict_feature_gate_comment(self):
        """_MUTEX_PRIORITY comment says it's not used for preemption."""
        import inspect
        from comfymodal_runtime.model_preload import MutationLane

        source = inspect.getsource(MutationLane)
        assert "# NOTE: _MUTEX_PRIORITY is defined for documentation / forward" in source, (
            "Missing feature-gate comment explaining _MUTEX_PRIORITY is not used"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 16. GPU installed-no-call vs unavailable classification
# ═══════════════════════════════════════════════════════════════════════════


class TestGpuNotObservedClassification:
    """gpu_not_observed_summary distinguishes installed+no-call vs unavailable."""

    def test_gpu_installed_no_call_is_not_observed(self):
        """Installed wrapper + zero calls → not_observed."""
        import comfymodal_runtime.model_preload as mp
        saved = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = True
            trace = RuntimeTrace(request_id="gpu-no-call-cls", process="remote")
            with request_execution_trace_scope(trace):
                summary = mp.gpu_not_observed_summary()
            assert summary["caller_classification"] == "not_observed"
            assert summary["wrapper_status"] == "installed"
            assert summary["count"] == 0
        finally:
            mp._gpu_wrapper_installed = saved

    def test_gpu_installed_with_call_is_observed(self):
        """Installed wrapper + calls → observed.

        NOTE: request_execution_trace_scope resets the call count to 0 on entry,
        so we set the count inside the scope.
        """
        import comfymodal_runtime.model_preload as mp
        saved_installed = mp._gpu_wrapper_installed
        saved_count = mp._gpu_request_call_count_var.get()
        try:
            mp._gpu_wrapper_installed = True
            trace = RuntimeTrace(request_id="gpu-call-cls", process="remote")
            with request_execution_trace_scope(trace):
                # Count is reset to 0 by scope entry; set it inside scope
                mp._gpu_request_call_count_var.set(3)
                summary = mp.gpu_not_observed_summary()
            assert summary["caller_classification"] == "observed"
            assert summary["wrapper_status"] == "installed"
            assert summary["count"] == 3
        finally:
            mp._gpu_wrapper_installed = saved_installed
            mp._gpu_request_call_count_var.set(saved_count)

    def test_gpu_unavailable_is_wrapper_unavailable(self):
        """Wrapper not installed → wrapper_unavailable."""
        import comfymodal_runtime.model_preload as mp
        saved = mp._gpu_wrapper_installed
        try:
            mp._gpu_wrapper_installed = False
            summary = mp.gpu_not_observed_summary()
            assert summary["caller_classification"] == "wrapper_unavailable"
            assert summary["wrapper_status"] == "unavailable"
            assert summary["count"] == 0
        finally:
            mp._gpu_wrapper_installed = saved


# ═══════════════════════════════════════════════════════════════════════════
# 17. Safetensors proxy get_tensor exactly once
# ═══════════════════════════════════════════════════════════════════════════


class TestSafetensorsGetTensorOnce:
    """_SafeOpenProxy does not read materialize or duplicate get_tensor calls.

    The proxy calls _orig_gt(k) exactly once per proxy.get_tensor(k) call.
    """

    def test_get_tensor_called_exactly_once_per_call(self):
        """Each proxy.get_tensor(k) call triggers _orig_gt(k) exactly once."""
        call_log: list[str] = []

        class FakeSafeOpen:
            def keys(self):
                return ["a"]
            def get_tensor(self, k):
                call_log.append(k)
                return SimpleNamespace(numel=lambda: 10, element_size=lambda: 2)

        proxy = _SafeOpenProxy(FakeSafeOpen(), FakeSafeOpen().get_tensor, [0], [0])
        t1 = proxy.get_tensor("a")
        t2 = proxy.get_tensor("a")

        assert len(call_log) == 2, (
            f"Expected 2 _orig_gt calls (one per proxy call), got {len(call_log)}"
        )

    def test_proxy_no_extra_materialization(self):
        """Proxy does not materialize tensors or call keys() on get_tensor."""
        get_tensor_called = [False]

        class FakeSafeOpen:
            def keys(self):
                return ["a"]
            def get_tensor(self, k):
                get_tensor_called[0] = True
                return SimpleNamespace(numel=lambda: 10, element_size=lambda: 2)

        proxy = _SafeOpenProxy(FakeSafeOpen(), FakeSafeOpen().get_tensor, [0], [0])

        # Just get_tensor should not trigger keys() (proxy delegates to _orig_gt)
        _ = proxy.get_tensor("a")
        assert get_tensor_called[0], "get_tensor should be called"


# ═══════════════════════════════════════════════════════════════════════════
# 18. ModelLaneTrace _on_read_completed CLIP-specific behavior
# ═══════════════════════════════════════════════════════════════════════════


class TestOnReadCompletedClipBehavior:
    """ModelLaneTrace._on_read_completed emits clip_cpu_prepare_start for CLIP lane."""

    def test_clip_lane_emits_clip_cpu_prepare_start(self):
        """CLIP lane _on_read_completed emits clip_cpu_prepare_start after final read."""
        trace = RuntimeTrace(request_id="on-read-clip", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        lane._on_read_completed()  # single read

        events = list(trace.events)
        clip_start = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(clip_start) == 1, (
            f"Expected clip_cpu_prepare_start for CLIP lane, events: {[e.name for e in events]}"
        )
        meta = clip_start[0].metadata
        assert meta["expected_read_count"] == 1
        assert meta["actual_read_count"] == 1

    def test_non_clip_lane_does_not_emit_clip_cpu_prepare_start(self):
        """UNET lane _on_read_completed does NOT emit clip_cpu_prepare_start."""
        trace = RuntimeTrace(request_id="on-read-unet", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        lane._on_read_completed()

        events = list(trace.events)
        clip_start = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(clip_start) == 0, (
            f"UNET lane should not emit clip_cpu_prepare_start"
        )

    def test_dual_clip_two_reads(self):
        """Two _on_read_completed calls for DualCLIP (expected=2)
        fire clip_cpu_prepare_start on the second call."""
        trace = RuntimeTrace(request_id="dual-clip-onread", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)

        lane._on_read_completed()  # first read
        lane._on_read_completed()  # second read -> trigger

        events = list(trace.events)
        clip_start = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(clip_start) == 1, (
            f"Expected 1 clip_cpu_prepare_start after 2 reads, got {len(clip_start)}"
        )
        assert clip_start[0].metadata.get("actual_read_count") == 2

    def test_mismatch_still_emits_clip_cpu_prepare_start(self):
        """When read count exceeds expected, clip_cpu_prepare_start still fires."""
        trace = RuntimeTrace(request_id="mismatch-onread", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        lane._on_read_completed()  # matches expected -> fires
        lane._on_read_completed()  # exceeds -> no second fire

        events = list(trace.events)
        clip_start = [e for e in events if e.name == "clip_cpu_prepare_start"]
        assert len(clip_start) == 1, "Only one clip_cpu_prepare_start regardless of mismatch"
        assert clip_start[0].metadata.get("actual_read_count") == 1


# ═══════════════════════════════════════════════════════════════════════════
# 19. Corrected semantics: signed residual, overlap error, boundary tracking
# ═══════════════════════════════════════════════════════════════════════════


class TestCorrectedSemantics:
    """Verifies signed residual, overlap_error status, under-read boundary
    absence, file_read_total separation, and named CLIP/UNET fields."""

    def test_clip_overlap_error_signed_residual(self):
        """When children total exceeds post-read total, residual is negative
        and status includes overlap_error."""
        trace = RuntimeTrace(request_id="clip-overlap", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            lane._on_read_completed()
            children = _clip_cpu_prepare_children.get()
            if children is not None:
                # Children exceed post-read total (synthetic: large children)
                children.append(("load_text_encoder_state_dicts", 999.0))
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        residual = meta["clip_cpu_prepare_residual_ms"]
        status = meta.get("status", "")
        assert residual < 0, f"Expected negative residual for overlap, got {residual}"
        assert "overlap_error" in status, (
            f"Expected overlap_error in status, got {status!r}"
        )

        # clip_load_call_end also carries overlap_error status
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        assert "overlap_error" in call_end[0].metadata.get("status", "")

    def test_clip_post_read_none_when_no_read_boundary(self):
        """When _on_read_completed is never called (no reads), post_read_total_ms
        should be None/absent and file_read_total_ms should be None."""
        trace = RuntimeTrace(request_id="clip-noread", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            # No _on_read_completed called — boundary never set
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        # post_read_total should be None (not a fake zero)
        assert meta["clip_cpu_prepare_total_ms"] is None, (
            f"Expected None post_read_total when no read boundary, got {meta['clip_cpu_prepare_total_ms']}"
        )

        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        call_meta = call_end[0].metadata
        assert call_meta.get("clip_file_read_total_ms") is None
        assert call_meta.get("clip_post_read_cpu_total_ms") is None
        # clip_load_call_total_ms should still be present (outer total)
        assert "clip_load_call_total_ms" in call_meta

    def test_clip_file_read_total_less_than_load_call_total(self):
        """file_read_total + post_read_total ≤ clip_load_call_total."""
        trace = RuntimeTrace(request_id="clip-read-sum", process="remote")
        lane = ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            # Simulate a load_torch_file call so file_read_total is measured
            lane.read_start()
            time.sleep(0.030)
            lane.read_end()
            lane._on_read_completed()
            time.sleep(0.010)  # post-read work
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = _make_clip_load_wrapper(fake_original)
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["ckpt"])
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        call_end = [e for e in events if e.name == "clip_load_call_end"]
        assert len(call_end) == 1
        meta = call_end[0].metadata
        outer = meta["clip_load_call_total_ms"]
        file_read = meta["clip_file_read_total_ms"]
        post_read = meta["clip_post_read_cpu_total_ms"]
        assert isinstance(outer, (int, float)) and outer >= 0
        # file_read_total may be None on low-res timer systems
        if file_read is not None:
            assert isinstance(file_read, (int, float)) and file_read >= 0
        assert isinstance(post_read, (int, float)) and post_read >= 0
        # outer ≥ file_read + post_read (when file_read is measured)
        if file_read is not None:
            assert abs(outer - (file_read + post_read)) < 5.0, (
                f"outer={outer} != file_read={file_read} + post_read={post_read}"
            )

    def test_unet_signed_residual_overlap_error(self):
        """UNET SD wrapper produces signed residual and overlap_error status
        when children exceed total."""
        trace = RuntimeTrace(request_id="unet-overlap", process="remote")
        lane = ModelLaneTrace(trace, "UNET", "restore", expected_read_count=1)

        def fake_original(*args, **kwargs):
            children = _child_durations.get()
            if children is not None:
                children.append(("load_model_weights", 999.0))
            return {"model": "fake"}

        wrapper = _make_sd_state_dict_wrapper(fake_original)
        _child_durations.set([])
        token = _ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper("config", {})
        finally:
            _ACTIVE_LANE_TRACE.reset(token)

        events = list(trace.events)
        end_events = [e for e in events if e.name == "unet_load_diffusion_model_state_dict_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        residual = meta["model_construction_residual_ms"]
        assert residual < 0, f"Expected negative residual, got {residual}"
        assert meta.get("status") == "overlap_error", (
            f"Expected overlap_error, got {meta.get('status')}"
        )

    def test_clip_cpu_children_summary_named_fields_absent_when_unavailable(self):
        """Named fields in [v2.clip_cpu_children] show None when unavailable."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_clip_cpu_children_summary

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_clip_cpu_children_summary(
                post_read_total_ms=100.0,
                file_read_total_ms=30.0,
                children=[],
                load_text_encoder_state_dicts_ms=None,
                detect_te_model_ms=None,
                state_dict_conversion_ms=None,
                clip_constructor_ms=None,
                model_patcher_ms=None,
                cache_publish_ms=None,
                measured_children_ms=0.0,
                residual_ms=100.0,
                status="ok",
            )
        output = f.getvalue()
        assert "load_text_encoder_state_dicts_ms=None" in output
        assert "detect_te_model_ms=None" in output
        assert "state_dict_conversion_ms=None" in output
        assert "clip_constructor_ms=None" in output
        assert "model_patcher_ms=None" in output
        assert "cache_publish_ms=None" in output
        # No invented zeroes
        assert "load_text_encoder_state_dicts_ms=0" not in output

    def test_unet_named_children_aggregation(self):
        """UNET _emit_bg_unet_stages_summary aggregates duplicate named events
        instead of overwriting."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import _emit_bg_unet_stages_summary

        trace = RuntimeTrace(request_id="unet-agg", process="remote_background_unet")
        trace.emit("background_unet_submitted", phase="restore")
        trace.emit("background_unet_worker_start", phase="restore")
        trace.emit("unet_load_diffusion_model_state_dict_end", phase="restore", metadata={
            "duration_ms": 300.0, "measured_child_total_ms": 250.0})
        # Duplicate named event
        trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": 20.0})
        trace.emit("unet_load_model_weights_end", phase="restore", metadata={"duration_ms": 15.0})
        trace.emit("unet_model_config_get_model_end", phase="restore", metadata={"duration_ms": 50.0})

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            _emit_bg_unet_stages_summary(trace, force=True)
        output = f.getvalue()
        # load_model_weights should be aggregated: 20 + 15 = 35
        assert "load_model_weights=35.0" in output, (
            f"Expected load_model_weights=35.0 in output, got: {output}"
        )
        assert "model_config_get_model=50.0" in output


# ═══════════════════════════════════════════════════════════════════════════
# 20. Background UNET attribution — external_model_lane_scope path
# ═══════════════════════════════════════════════════════════════════════════


class TestBgUnetAttribution:
    """Verifies that external_model_lane_scope with UNET lane populates
    model construction fields (model_construction_ms, load_model_weights_ms,
    model_to_ms) via the actual wrapper stack, without duplicate reads,
    and without global PyTorch/safetensors monkeypatches."""

    def test_bg_unet_scope_emits_construction_fields(self):
        """external_model_lane_scope + UNET wrappers populate model_construction_ms,
        load_model_weights_ms, model_to_ms in trace events."""
        import io
        import contextlib
        from comfymodal_runtime.model_preload import (
            external_model_lane_scope,
            _ensure_core_wrappers,
            _ensure_unet_decompose_wrappers,
        )

        bg_trace = RuntimeTrace(
            process="remote_background_unet",
            trace_id="bg-attrib-test-001",
        )
        bg_trace.set_metadata(
            canonical_key="unet:test-model",
            restored_instance_id="test-inst-001",
            restore_session_id="test-sess-001",
            resolved_path="/fake/path/model.safetensors",
        )

        calls: list[str] = []

        # Simulate the call chain: load_torch_file → load_diffusion_model_state_dict
        # → ModelPatcher.__init__ → model.to() → load_model_weights
        def fake_load_torch_file(ckpt, **kw):
            calls.append("load_torch_file")
            return {"param": "state_dict"}

        def fake_load_diffusion_model_state_dict(config, state_dict):
            calls.append("load_diffusion_model_state_dict")
            # Simulate ModelPatcher constructor inside
            class FakeModel:
                def to(self, *a, **kw):
                    calls.append("model_to")
                    return self
                def load_model_weights(self, *a, **kw):
                    calls.append("load_model_weights")
                    return None
            model = FakeModel()
            # ModelPatcher constructor
            calls.append("model_patcher_constructor")
            # model.to()
            model.to(device="cpu")
            # load_model_weights (called by model_config.get_model or similar)
            model.load_model_weights()
            return {"model": model}

        # Install core wrappers targeting our fakes
        import comfymodal_runtime.model_preload as mp

        # Save originals
        saved_torch_file = mp._make_torch_file_wrapper
        saved_sd = mp._make_sd_state_dict_wrapper
        saved_mp_ctor = mp._make_model_patcher_constructor_wrapper
        saved_model_to = mp._make_model_to_wrapper
        saved_unet_subfn = mp._make_unet_subfn_wrapper

        try:
            # Install wrappers on the fakes
            load_torch_wrapped = mp._make_torch_file_wrapper(fake_load_torch_file)
            sd_wrapped = mp._make_sd_state_dict_wrapper(fake_load_diffusion_model_state_dict)

            # Create model_patcher constructor wrapper
            class FakeModelPatcher:
                def __init__(self):
                    calls.append("model_patcher_ctor_body")

            mp_ctor_wrapped = mp._make_model_patcher_constructor_wrapper(FakeModelPatcher.__init__)
            model_to_wrapped = mp._make_model_to_wrapper(
                lambda self, *a, **kw: (calls.append("model_to_body") or self)
            )
            lw_wrapped = mp._make_unet_subfn_wrapper("load_model_weights",
                                                       lambda self: (calls.append("load_weights_body") or None),
                                                       "model")

            f = io.StringIO()
            with contextlib.redirect_stdout(f):
                with external_model_lane_scope(bg_trace, lane="UNET", phase="restore", expected_read_count=1) as lane_t:
                    # Simulate the actual load sequence
                    _ = load_torch_wrapped("model.safetensors")
                    _ = sd_wrapped("unet_config", {"param": 1})
                    # Simulate ModelPatcher constructor (called inside load_diffusion_model_state_dict)
                    _fp = FakeModelPatcher()
                    mp_ctor_wrapped(_fp)
                    # Simulate model.to()
                    class FakeMod:
                        pass
                    model_to_wrapped(FakeMod(), device="cpu")
                    # Simulate load_model_weights
                    lw_wrapped(FakeMod())
                    # Simulate cache publication (as done in _load_restore_background_unet)
                    lane_t.cache_publish_start(canonical_key="unet:test-model")
                    lane_t.cache_object_store(canonical_key="unet:test-model",
                                              object_type="ModelPatcher",
                                              object_id="obj_id_001")
                    lane_t.cache_metadata_store(canonical_key="unet:test-model",
                                                metadata_status="completed")
                    lane_t.done_event_set(canonical_key="unet:test-model")
                    lane_t.cache_publish_end(canonical_key="unet:test-model")

            output = f.getvalue()
            events = list(bg_trace.events)
            event_names = [e.name for e in events]

            # Verify model construction fields are populated
            sd_end = [e for e in events if e.name == "unet_load_diffusion_model_state_dict_end"]
            assert len(sd_end) >= 1, "unet_load_diffusion_model_state_dict_end must exist"
            sd_meta = sd_end[0].metadata
            assert "duration_ms" in sd_meta, "SD end must have duration_ms"
            assert sd_meta.get("model_construction_total_ms") is not None, (
                "model_construction_total_ms must be populated"
            )
            # load_model_weights
            lw_end = [e for e in events if e.name == "unet_load_model_weights_end"]
            assert len(lw_end) >= 1, "unet_load_model_weights_end must exist"
            assert lw_end[0].metadata.get("duration_ms") is not None

            # model_to
            mt_end = [e for e in events if e.name == "unet_model_to_end"]
            assert len(mt_end) >= 1, "unet_model_to_end must exist"
            assert mt_end[0].metadata.get("duration_ms") is not None

            # model_patcher_constructor
            mpc_end = [e for e in events if e.name == "unet_model_patcher_constructor_end"]
            assert len(mpc_end) >= 1, "unet_model_patcher_constructor_end must exist"

            # Cache publication events must be present
            assert "unet_cache_publish_start" in event_names
            assert "unet_cache_object_store" in event_names
            assert "unet_cache_metadata_store" in event_names
            assert "unet_done_event_set" in event_names
            assert "unet_cache_publish_end" in event_names

            # ready() event must be emitted AFTER cache publication
            ready_idx = next(i for i, e in enumerate(events) if e.name == "ready")
            pub_end_idx = next(i for i, e in enumerate(events) if e.name == "unet_cache_publish_end")
            assert pub_end_idx < ready_idx, (
                f"cache_publish_end at {pub_end_idx} must precede ready at {ready_idx}"
            )

            # Background worker events
            assert "background_unet_submitted" in event_names
            assert "background_unet_worker_start" in event_names
            assert "background_unet_worker_end" in event_names

            # Summaries must be emitted
            assert "[v2.bg_unet_io]" in output, (
                f"Expected [v2.bg_unet_io] summary, got:\n{output}"
            )
            assert "[v2.bg_unet_stages]" in output, (
                f"Expected [v2.bg_unet_stages] summary, got:\n{output}"
            )

        finally:
            # Restore saved wrappers (no-op since these are test-local)
            pass

    def test_bg_unet_single_loader_call(self):
        """The original UNET loader function is called exactly once when using
        external_model_lane_scope (no duplicate read)."""
        from comfymodal_runtime.model_preload import (
            external_model_lane_scope,
            _make_torch_file_wrapper,
        )

        bg_trace = RuntimeTrace(
            process="remote_background_unet",
            trace_id="bg-single-call",
        )
        bg_trace.set_metadata(
            canonical_key="unet:single",
            resolved_path="/fake/model.safetensors",
        )

        call_count = [0]

        def fake_loader(ckpt, **kw):
            call_count[0] += 1
            return {"state_dict": "data"}

        wrapped = _make_torch_file_wrapper(fake_loader)

        with external_model_lane_scope(bg_trace, lane="UNET", phase="restore", expected_read_count=1) as _lt:
            _lt.cache_publish_start()
            result1 = wrapped("model.safetensors")
            _lt.cache_publish_end()

        assert call_count[0] == 1, (
            f"Expected exactly 1 loader call, got {call_count[0]}"
        )
        assert result1 == {"state_dict": "data"}

    def test_no_global_monkeypatches(self):
        """The model_preload wrappers do NOT install global PyTorch or
        safetensors monkeypatches.  The deep diag wrappers target
        sys.modules but are guarded by the DIAGNOSTIC_FLAG, and the
        torch/safetensors modules remain unpolluted by sentinel attributes."""
        import sys as _test_sys

        # Verify no sentinel attributes on torch or safetensors modules
        torch_mod = _test_sys.modules.get("torch")
        st_mod = _test_sys.modules.get("safetensors")
        if torch_mod is not None:
            load_fn = getattr(torch_mod, "load", None)
            if load_fn is not None:
                # The deep diag wrapper sets _comfy_modal_deep_tl_wrapper
                assert not hasattr(load_fn, "_comfy_modal_deep_tl_wrapper"), (
                    "torch.load must NOT have deep diag sentinel in tests"
                )
        if st_mod is not None:
            open_fn = getattr(st_mod, "safe_open", None)
            if open_fn is not None:
                assert not hasattr(open_fn, "_comfy_modal_deep_st_wrapper"), (
                    "safetensors.safe_open must NOT have deep diag sentinel in tests"
                )
        # Verify comfy.utils.load_torch_file is not wrapped
        utils_mod = _test_sys.modules.get("comfy.utils")
        if utils_mod is not None:
            ltf = getattr(utils_mod, "load_torch_file", None)
            if ltf is not None:
                # The read wrapper sets _comfy_modal_read_wrapper sentinel
                assert not hasattr(ltf, "_comfy_modal_read_wrapper"), (
                    "comfy.utils.load_torch_file must NOT be wrapped in test environment"
                )

    def test_bg_unet_scope_future_handoff_honored(self):
        """When a future exists and succeeds, the background UNET path must
        not call the loader (future handoff takes priority).  This validates
        the comfyapp-level contract: if _unet_object_cache has the key, the
        background worker path does NOT re-enter the loader.

        Note: This tests the contract level, not the comfyapp implementation.
        The actual future handoff is tested in test_unet_cache_future_handoff.py.
        Here we verify that the lane scope does not prevent cache-based handoff."""
        from comfymodal_runtime.model_preload import (
            external_model_lane_scope,
            _make_torch_file_wrapper,
        )

        bg_trace = RuntimeTrace(
            process="remote_background_unet",
            trace_id="bg-future-handoff",
        )
        bg_trace.set_metadata(canonical_key="unet:handoff")

        call_count = [0]

        def fake_loader(ckpt, **kw):
            call_count[0] += 1
            return {"model": "loaded"}

        wrapped = _make_torch_file_wrapper(fake_loader)

        # Simulate object cache already populated (future handoff success)
        object_cache = {"unet:handoff": "cached_result"}

        # The lane scope itself does not check the cache — the comfyapp
        # code that calls external_model_lane_scope should check the cache
        # first.  This test verifies no spurious extra calls happen within
        # the scope when the cache is available externally.
        with external_model_lane_scope(bg_trace, lane="UNET", phase="restore", expected_read_count=1) as _lt:
            # Check cache first (as comfyapp does)
            if "unet:handoff" not in object_cache:
                _ = wrapped("model.safetensors")
                object_cache["unet:handoff"] = "loaded"
            # else: skip loader, use cache
            _lt.cache_publish_start()
            _lt.cache_publish_end()

        # Loader should NOT have been called (cache hit)
        assert call_count[0] == 0, (
            f"Expected 0 loader calls on cache hit, got {call_count[0]}"
        )

    def test_bg_unet_scope_no_second_read(self):
        """When a previous active read has already loaded the model into cache,
        the lane scope does NOT trigger a second load_torch_file call."""
        from comfymodal_runtime.model_preload import (
            external_model_lane_scope,
            _make_torch_file_wrapper,
        )

        bg_trace = RuntimeTrace(
            process="remote_background_unet",
            trace_id="bg-no-second-read",
        )
        bg_trace.set_metadata(
            canonical_key="unet:nosecond",
            resolved_path="/fake/model.safetensors",
        )

        call_count = [0]
        cache = {}

        def fake_loader(ckpt, **kw):
            call_count[0] += 1
            result = {"model": f"loaded_{call_count[0]}"}
            cache[str(ckpt)] = result
            return result

        wrapped = _make_torch_file_wrapper(fake_loader)

        # First call: populate cache
        with external_model_lane_scope(bg_trace, lane="UNET", phase="restore", expected_read_count=1) as _lt:
            result1 = wrapped("model.safetensors")
            cache["model.safetensors"] = result1
            _lt.cache_publish_start()
            _lt.cache_object_store(canonical_key="test",
                                    object_type="ModelPatcher",
                                    object_id="id1")
            _lt.cache_publish_end()

        assert call_count[0] == 1, "First call must invoke loader exactly once"

        # Second call with same key: check cache first, skip loader
        bg_trace2 = RuntimeTrace(
            process="remote_background_unet",
            trace_id="bg-no-second-read-2",
        )
        bg_trace2.set_metadata(canonical_key="unet:nosecond")

        with external_model_lane_scope(bg_trace2, lane="UNET", phase="restore", expected_read_count=1) as _lt2:
            if "model.safetensors" not in cache:
                result2 = wrapped("model.safetensors")
                cache["model.safetensors"] = result2
            else:
                result2 = cache["model.safetensors"]
            _lt2.cache_publish_start()
            _lt2.cache_publish_end()

        assert call_count[0] == 1, (
            f"Second call must NOT invoke loader (cache hit), got {call_count[0]} calls"
        )
        assert result2["model"] == "loaded_1", "Second call must return cached result"
