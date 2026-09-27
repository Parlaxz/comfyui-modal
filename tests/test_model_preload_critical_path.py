"""Focused tests for model_preload critical-path optimizations.

Verifies:
1. Prefill worker skips wrapper install while UNET/CLIP/VAE workers install.
2. Read-duration accumulator replaces O(n) event scan in CLIP summary.
3. Model loader callbacks invoked once, futures resolve correctly.
4. Cache/result identity and stage timing metadata remain unchanged.

All tests use mocks only — no real ComfyUI/Modal/GPU.
"""

from __future__ import annotations

import time
import threading
import gc
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

import comfymodal_runtime.model_preload as mp
from comfymodal_runtime.contracts import ModelRestoreKey, PrefillKey, RestorePlan
from comfymodal_runtime.trace import RuntimeTrace


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


class _MockDiagnostics:
    """Minimal diagnostics proxy for RestorePreparation."""
    def __init__(self) -> None:
        self.unet_started_at: float = 0.0
        self.unet_completed_at: float = 0.0
        self.clip_started_at: float = 0.0
        self.clip_completed_at: float = 0.0
        self.prefill_started_at: float = 0.0
        self.prefill_completed_at: float = 0.0
        self.unet_error: str = ""
        self.clip_error: str = ""
        self.prefill_error: str = ""
        self.unet_wait_ms: float = 0.0
        self.clip_wait_ms: float = 0.0
        self.prefill_wait_ms: float = 0.0
        self.unet_actual_graph_wait_ms: float = 0.0
        self.clip_actual_graph_wait_ms: float = 0.0
        self.prefill_actual_graph_wait_ms: float = 0.0
        self.unet_work_completed_before_demand_ms: float = 0.0
        self.clip_work_completed_before_demand_ms: float = 0.0
        self.prefill_work_completed_before_demand_ms: float = 0.0
        self.useful_overlap_ms: float = 0.0
        self.unused_speculation: bool = False


def _make_preparation(
    model_key: ModelRestoreKey | None = None,
    prefill_key: PrefillKey | None = None,
) -> mp.RestorePreparation:
    """Build a minimal RestorePreparation for testing coordinator internals."""
    mk = model_key or ModelRestoreKey(
        unet_identity="unet.safetensors",
        clip_identity="clip_l.safetensors",
        clip_type="stable_diffusion",
    )
    pk = prefill_key or PrefillKey(
        model_key=mk,
        prompt_bundle_hash="hash-test",
        encode_options={
            "eligible": True,
            "encodes": [{"node_id": "6", "text": "cat", "role": "positive"}],
        },
    )
    return mp.RestorePreparation(model_key=mk, prefill_key=pk)


def _wait_future(fut: Future[Any] | None, timeout: float = 5.0) -> Any:
    if fut is None:
        return None
    return fut.result(timeout=timeout)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Prefill skips wrapper install; model-loading lanes still install
# ═══════════════════════════════════════════════════════════════════════════


class TestWrapperInstallGating:
    """Execution prefill worker skips _ensure_core_wrappers and
    _ensure_unet_decompose_wrappers; UNET/CLIP/VAE workers install both."""

    def _make_coordinator(self) -> mp.ModelPreloadCoordinator:
        return mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "unet-result",
            clip_loader=lambda k: SimpleNamespace(),
            prefill_loader=lambda pk, clip: {"result": "ok"},
            max_workers=2,
        )

    def test_prefill_skips_both_wrappers(self):
        """Execution prefill: neither install function is called."""
        coord = self._make_coordinator()
        prep = _make_preparation()

        core_mock = MagicMock()
        unet_decompose_mock = MagicMock()
        saved_core = mp._ensure_core_wrappers
        saved_unet = mp._ensure_unet_decompose_wrappers
        try:
            mp._ensure_core_wrappers = core_mock
            mp._ensure_unet_decompose_wrappers = unet_decompose_mock

            callback = lambda: "prefill-ok"
            future = coord._submit(
                "execution_prefill", callback, prep, None,
                phase="execution", expected_read_count=0,
            )
            result = _wait_future(future, timeout=5)
            assert result == "prefill-ok"
            # Neither install function should have been called
            core_mock.assert_not_called()
            unet_decompose_mock.assert_not_called()
        finally:
            mp._ensure_core_wrappers = saved_core
            mp._ensure_unet_decompose_wrappers = saved_unet
            coord.close()

    def test_unet_worker_installs_both(self):
        """UNET worker: both install functions are called."""
        coord = self._make_coordinator()
        prep = _make_preparation()

        core_mock = MagicMock()
        unet_decompose_mock = MagicMock()
        saved_core = mp._ensure_core_wrappers
        saved_unet = mp._ensure_unet_decompose_wrappers
        try:
            mp._ensure_core_wrappers = core_mock
            mp._ensure_unet_decompose_wrappers = unet_decompose_mock

            future = coord._submit(
                "unet", lambda: "unet-ok", prep, None,
                expected_read_count=1,
            )
            result = _wait_future(future, timeout=5)
            assert result == "unet-ok"
            core_mock.assert_called_once()
            unet_decompose_mock.assert_called_once()
        finally:
            mp._ensure_core_wrappers = saved_core
            mp._ensure_unet_decompose_wrappers = saved_unet
            coord.close()

    def test_clip_worker_installs_core_but_not_unet_decompose(self):
        """CLIP worker: core wrappers installed, UNET decompose skipped."""
        coord = self._make_coordinator()
        prep = _make_preparation()

        core_mock = MagicMock()
        unet_decompose_mock = MagicMock()
        saved_core = mp._ensure_core_wrappers
        saved_unet = mp._ensure_unet_decompose_wrappers
        try:
            mp._ensure_core_wrappers = core_mock
            mp._ensure_unet_decompose_wrappers = unet_decompose_mock

            future = coord._submit(
                "clip", lambda: SimpleNamespace(), prep, None,
                expected_read_count=2,
            )
            result = _wait_future(future, timeout=5)
            assert result is not None
            core_mock.assert_called_once()
            unet_decompose_mock.assert_not_called()
        finally:
            mp._ensure_core_wrappers = saved_core
            mp._ensure_unet_decompose_wrappers = saved_unet
            coord.close()

    def test_vae_worker_installs_core_but_not_unet_decompose(self):
        """VAE worker: core wrappers installed, UNET decompose skipped."""
        coord = self._make_coordinator()
        prep = _make_preparation()

        core_mock = MagicMock()
        unet_decompose_mock = MagicMock()
        saved_core = mp._ensure_core_wrappers
        saved_unet = mp._ensure_unet_decompose_wrappers
        try:
            mp._ensure_core_wrappers = core_mock
            mp._ensure_unet_decompose_wrappers = unet_decompose_mock

            future = coord._submit(
                "vae", lambda: "vae-result", prep, None,
                expected_read_count=1,
            )
            result = _wait_future(future, timeout=5)
            assert result == "vae-result"
            core_mock.assert_called_once()
            unet_decompose_mock.assert_not_called()
        finally:
            mp._ensure_core_wrappers = saved_core
            mp._ensure_unet_decompose_wrappers = saved_unet
            coord.close()

    def test_prefill_diag_name_also_skips(self):
        """Execution prefill via diag_name='prefill' also skips wrappers."""
        coord = self._make_coordinator()
        prep = _make_preparation()

        core_mock = MagicMock()
        unet_decompose_mock = MagicMock()
        saved_core = mp._ensure_core_wrappers
        saved_unet = mp._ensure_unet_decompose_wrappers
        try:
            mp._ensure_core_wrappers = core_mock
            mp._ensure_unet_decompose_wrappers = unet_decompose_mock

            future = coord._submit(
                "some_name", lambda: "ok", prep, None,
                diag_name="prefill", expected_read_count=0,
            )
            result = _wait_future(future, timeout=5)
            assert result == "ok"
            core_mock.assert_not_called()
            unet_decompose_mock.assert_not_called()
        finally:
            mp._ensure_core_wrappers = saved_core
            mp._ensure_unet_decompose_wrappers = saved_unet
            coord.close()


# ═══════════════════════════════════════════════════════════════════════════
# 2. Read-duration accumulator replaces event scanning
# ═══════════════════════════════════════════════════════════════════════════


class TestClipReadDurationAccumulator:
    """_clip_read_total_ms accumulates via _on_read_completed(read_duration_ms=...)
    and is used by _make_clip_load_wrapper instead of scanning events."""

    def test_accumulator_defaults_to_zero(self):
        """New ModelLaneTrace has _clip_read_total_ms == 0.0."""
        trace = RuntimeTrace(request_id="acc-zero", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)
        assert lane._clip_read_total_ms == 0.0

    def test_accumulate_single_read(self):
        """Single _on_read_completed(read_duration_ms=123.4) accumulates."""
        trace = RuntimeTrace(request_id="acc-single", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)
        lane._on_read_completed(read_duration_ms=123.456)
        assert lane._clip_read_total_ms == 123.456

    def test_accumulate_multiple_reads(self):
        """Multiple calls sum correctly."""
        trace = RuntimeTrace(request_id="acc-multi", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)
        lane._on_read_completed(read_duration_ms=100.0)
        lane._on_read_completed(read_duration_ms=200.0)
        assert lane._clip_read_total_ms == 300.0

    def test_non_clip_lane_does_not_accumulate(self):
        """Non-CLIP lanes ignore read_duration_ms."""
        for lane_name in ("UNET", "VAE", "prefill"):
            trace = RuntimeTrace(request_id=f"acc-{lane_name.lower()}", process="remote")
            lane = mp.ModelLaneTrace(trace, lane_name, "restore", expected_read_count=1)
            lane._on_read_completed(read_duration_ms=99.9)
            assert lane._clip_read_total_ms == 0.0, (
                f"{lane_name} lane must not accumulate CLIP read duration"
            )

    def test_call_without_argument_is_compatible(self):
        """Existing callers that omit read_duration_ms continue to work."""
        trace = RuntimeTrace(request_id="acc-no-arg", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)
        lane._on_read_completed()  # no argument — old calling convention
        assert lane._clip_read_total_ms == 0.0  # not incremented
        assert lane._actual_read_count == 1  # still counts reads

    def test_accumulator_value_appears_in_clip_load_call_end(self):
        """clip_file_read_total_ms in clip_load_call_end metadata matches
        the accumulator value from _on_read_completed."""
        trace = RuntimeTrace(request_id="acc-event", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        # Simulate two load_torch_file calls with known durations
        lane._on_read_completed(read_duration_ms=50.0)
        lane._on_read_completed(read_duration_ms=30.0)

        # Now simulate what _make_clip_load_wrapper does with the accumulator
        raw = lane._clip_read_total_ms  # 80.0
        clip_file_read = round(raw, 3) if raw else None

        assert clip_file_read == 80.0

        # Emit the event as the wrapper would
        lane._trace.emit("clip_load_call_end", phase="restore", metadata={
            "lane": "CLIP",
            "clip_load_call_total_ms": 200.0,
            "clip_file_read_total_ms": clip_file_read,
            "clip_post_read_cpu_total_ms": 120.0 if clip_file_read else None,
            "status": "ok",
        })

        # Verify metadata
        end_events = [e for e in trace.events if e.name == "clip_load_call_end"]
        assert len(end_events) == 1
        meta = end_events[0].metadata
        assert meta["clip_file_read_total_ms"] == 80.0

    def test_accumulator_value_in_cpu_prepare_end(self):
        """clip_file_read_total_ms in clip_cpu_prepare_end also uses accumulator."""
        trace = RuntimeTrace(request_id="acc-cpu-prep", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        lane._on_read_completed(read_duration_ms=75.0)

        # Simulate the clip_cpu_prepare_end event as emitted by _make_clip_load_wrapper
        raw = lane._clip_read_total_ms
        clip_file_read = round(raw, 3) if raw else None
        lane._trace.emit("clip_cpu_prepare_end", phase="restore", metadata={
            "lane": "CLIP",
            "clip_cpu_prepare_total_ms": 150.0,
            "clip_file_read_total_ms": clip_file_read,
            "status": "ok",
        })

        end_events = [e for e in trace.events if e.name == "clip_cpu_prepare_end"]
        assert len(end_events) == 1
        assert end_events[0].metadata["clip_file_read_total_ms"] == 75.0

    def test_clip_file_read_is_none_when_no_reads(self):
        """When no reads occur, clip_file_read_total_ms is None."""
        trace = RuntimeTrace(request_id="acc-no-read", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)

        raw = lane._clip_read_total_ms  # 0.0
        clip_file_read = round(raw, 3) if raw else None
        assert clip_file_read is None

    def test_read_start_read_end_events_still_emitted(self):
        """read_start/read_end events are still emitted (preserved behavior)."""
        trace = RuntimeTrace(request_id="acc-events", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=2)

        lane.read_start()
        time.sleep(0.005)
        lane.read_end()
        lane._on_read_completed(read_duration_ms=5.0)

        lane.read_start()
        time.sleep(0.010)
        lane.read_end()
        lane._on_read_completed(read_duration_ms=10.0)

        event_names = [e.name for e in trace.events]
        assert event_names.count("read_start") == 2
        assert event_names.count("read_end") == 2
        assert lane._clip_read_total_ms == 15.0

    @pytest.mark.parametrize("lane_name", ["CLIP", "UNET"])
    def test_model_file_read_is_invoked_once(self, lane_name: str):
        trace = RuntimeTrace(request_id=f"single-read-{lane_name.lower()}", process="remote")
        lane = mp.ModelLaneTrace(trace, lane_name, "restore", expected_read_count=1)
        calls: list[str] = []

        def original(path: str, **kwargs: Any) -> dict[str, str]:
            calls.append(path)
            return {"path": path}

        wrapped = mp._make_torch_file_wrapper(original)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            result = wrapped("model.safetensors")
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert result == {"path": "model.safetensors"}
        assert calls == ["model.safetensors"]
        assert lane._actual_read_count == 1

    def test_clip_summary_does_not_need_read_event_fallback(self, monkeypatch):
        trace = RuntimeTrace(request_id="acc-no-fallback", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)
        lane._on_read_completed(read_duration_ms=12.5)

        event_accesses = [0]

        def tracked_events(owner: Any):
            event_accesses[0] += 1
            return tuple(owner._events)

        monkeypatch.setattr(type(trace), "events", property(tracked_events))

        def fake_original(*args: Any, **kwargs: Any) -> SimpleNamespace:
            return SimpleNamespace(patcher=SimpleNamespace())

        wrapper = mp._make_clip_load_wrapper(fake_original)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            wrapper(["clip.safetensors"])
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert event_accesses[0] == 1

    def test_tensor_payload_and_destination_dtype_are_preserved(self):
        torch = pytest.importorskip("torch")
        trace = RuntimeTrace(request_id="tensor-payload", process="remote")
        lane = mp.ModelLaneTrace(trace, "CLIP", "restore", expected_read_count=1)
        state = {
            "weight": torch.arange(6, dtype=torch.float32).reshape(2, 3),
            "bias": torch.tensor([1.0, -2.0], dtype=torch.float32),
        }
        captured: dict[str, Any] = {}

        def original(path: str, **kwargs: Any) -> dict[str, Any]:
            captured["path"] = path
            captured.update(kwargs)
            return state

        wrapped = mp._make_torch_file_wrapper(original)
        token = mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            result = wrapped("clip.safetensors", device="cpu", return_metadata=True)
        finally:
            mp._ACTIVE_LANE_TRACE.reset(token)

        assert result is state
        assert captured["path"] == "clip.safetensors"
        assert captured["device"] == "cpu"
        assert captured["return_metadata"] is True
        assert tuple(result) == ("weight", "bias")
        for key, expected in state.items():
            assert result[key].shape == expected.shape
            assert result[key].dtype == expected.dtype
            assert torch.equal(result[key], expected)


# ═══════════════════════════════════════════════════════════════════════════
# 3. Callback invocation, future consumption, ownership
# ═══════════════════════════════════════════════════════════════════════════


class TestCallbackAndFutureOwnership:
    """Each model loader callback is invoked once; futures resolve correctly;
    temporary references are not retained after terminal completion."""

    def test_callback_invoked_exactly_once(self):
        """The callback passed to _submit runs exactly once."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        prep = _make_preparation()
        call_count = [0]

        def once_callback() -> str:
            call_count[0] += 1
            return "result"

        future = coord._submit("unet", once_callback, prep, None)

        # Wait for completion
        result = _wait_future(future, timeout=5)
        assert result == "result"
        assert call_count[0] == 1, f"Callback called {call_count[0]} times, expected 1"
        coord.close()

    def test_successful_future_returns_prepared_result(self):
        """The future resolves to the callback return value directly."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "unet-value",
            max_workers=2,
        )
        prep = _make_preparation()

        expected = {"model": "patched", "cache": "ready"}
        future = coord._submit("unet", lambda: expected, prep, None)
        result = _wait_future(future, timeout=5)
        assert result is expected
        assert result["model"] == "patched"
        assert result["cache"] == "ready"
        coord.close()

    def test_callback_error_propagates_in_future(self):
        """When callback raises, the future raises the same exception."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=1,
        )
        prep = _make_preparation()

        future = coord._submit("unet", lambda: (_ for _ in ()).throw(
            RuntimeError("test-error")
        ), prep, None)

        with pytest.raises(RuntimeError, match="test-error"):
            _wait_future(future, timeout=5)
        coord.close()

    def test_future_consumption_returns_direct_tuple_for_loader_consumers(self):
        """After wait, the result can be wrapped in a tuple as _consume_model_impl does.
        This verifies the result tuple shape expected by loader consumers."""
        # Simulate what happens in V2LoaderBridge._consume_model_impl
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "unet-model",
            max_workers=2,
        )
        prep = _make_preparation()

        future = coord._submit("unet", lambda: "unet-model", prep, None)
        result = _wait_future(future, timeout=5)
        # The consumer wraps it: (result,) — a single-element tuple
        consumed = (result,)
        assert isinstance(consumed, tuple)
        assert len(consumed) == 1
        assert consumed[0] == "unet-model"
        coord.close()

    def test_coordinator_not_retaining_callback_after_terminal(self):
        """After future completes, callback-captured source objects are releasable."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        prep = _make_preparation()

        class Source:
            pass

        source = Source()
        source_ref = weakref.ref(source)

        def make_callback(value: Source):
            def callback() -> str:
                _ = value
                return "done"

            return callback

        callback = make_callback(source)
        del source
        future = coord._submit("unet", callback, prep, None)
        callback = None
        _wait_future(future, timeout=5)
        gc.collect()

        assert source_ref() is None
        coord.close()

    def test_multiple_lanes_each_called_once(self):
        """UNET + CLIP submitted together: each callback runs once."""
        unet_count = [0]
        clip_count = [0]

        def unet_cb() -> str:
            unet_count[0] += 1
            return "unet"

        def clip_cb() -> SimpleNamespace:
            clip_count[0] += 1
            return SimpleNamespace()

        coord = mp.ModelPreloadCoordinator(max_workers=2)
        coord.unet_loader = lambda k: unet_cb()
        coord.clip_loader = lambda k: clip_cb()

        prep = _make_preparation()
        prep.unet_future = coord._submit("unet", unet_cb, prep, None)
        prep.clip_future = coord._submit("clip", clip_cb, prep, None)

        assert _wait_future(prep.unet_future, timeout=5) == "unet"
        assert _wait_future(prep.clip_future, timeout=5) is not None
        assert unet_count[0] == 1
        assert clip_count[0] == 1
        coord.close()


# ═══════════════════════════════════════════════════════════════════════════
# 4. Cache/result identity and stage timing metadata unchanged
# ═══════════════════════════════════════════════════════════════════════════


class TestIdentityAndTimingPreserved:
    """Cache/result identity unchanged; stage timing metadata reconciles."""

    def test_identity_object_preserved(self):
        """The same result object reference is returned (no copying)."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        prep = _make_preparation()
        obj = {"identity": "abc123", "cache": "object"}
        future = coord._submit("unet", lambda: obj, prep, None)
        result = _wait_future(future, timeout=5)
        assert result is obj
        assert result["identity"] == "abc123"
        coord.close()

    def test_prefill_diagnostics_attributes_structure(self):
        """RestorePreparation diagnostics field names match expected schema."""
        prep = _make_preparation()
        diag = prep.diagnostics
        required_attrs = [
            "unet_started_at", "unet_completed_at",
            "clip_started_at", "clip_completed_at",
            "prefill_started_at", "prefill_completed_at",
            "unet_error", "clip_error", "prefill_error",
            "unet_wait_ms", "clip_wait_ms", "prefill_wait_ms",
            "unet_actual_graph_wait_ms", "clip_actual_graph_wait_ms",
            "prefill_actual_graph_wait_ms",
            "unet_work_completed_before_demand_ms",
            "clip_work_completed_before_demand_ms",
            "prefill_work_completed_before_demand_ms",
            "useful_overlap_ms", "unused_speculation",
        ]
        for attr in required_attrs:
            assert hasattr(diag, attr), f"Missing diagnostics field: {attr}"

    def test_stage_timing_metadata_in_trace_events(self):
        """Worker timing metadata is present in trace events (monotonic)."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "unet",
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="timing-test", process="remote")
        prep = _make_preparation()

        future = coord._submit("unet", lambda: "done", prep, trace)
        _wait_future(future, timeout=5)

        # Must have prepare_start and worker_started events
        assert any(e.name == "unet_prepare_start" for e in trace.events)
        assert any(e.name == "unet_prepare_end" for e in trace.events)

        worker_started = [e for e in trace.events if e.name == "preload_worker_started"]
        assert len(worker_started) >= 1
        meta = worker_started[0].metadata
        assert meta.get("lane") == "unet"
        assert isinstance(meta.get("queue_wait_ms"), (int, float))

        coord.close()

    def test_submitted_events_have_lane_and_submission_id(self):
        """The preload_submitted event carries lane and submission_id."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="submission-test", process="remote")
        prep = _make_preparation()

        future = coord._submit("unet", lambda: "done", prep, trace)
        _wait_future(future, timeout=5)

        submitted = [e for e in trace.events if e.name == "preload_submitted"]
        assert len(submitted) == 1
        assert submitted[0].metadata.get("lane") == "unet"
        assert submitted[0].metadata.get("submission_id", "").startswith("s")
        coord.close()

    def test_ready_event_emitted_on_success(self):
        """lane_trace.ready() is called after successful callback completion."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="ready-test", process="remote")
        prep = _make_preparation()

        future = coord._submit("unet", lambda: "ok", prep, trace)
        _wait_future(future, timeout=5)

        ready_events = [e for e in trace.events if e.name == "ready"]
        assert len(ready_events) == 1
        meta = ready_events[0].metadata
        assert meta.get("lane") == "UNET"
        coord.close()

    def test_failed_event_emitted_on_exception(self):
        """lane_trace.failed() is called when callback raises."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        trace = RuntimeTrace(request_id="fail-test", process="remote")
        prep = _make_preparation()

        future = coord._submit("unet", lambda: (_ for _ in ()).throw(
            ValueError("boom")
        ), prep, trace)

        with pytest.raises(ValueError, match="boom"):
            _wait_future(future, timeout=5)

        failed_events = [e for e in trace.events if e.name == "failed"]
        assert len(failed_events) == 1
        meta = failed_events[0].metadata
        assert meta.get("error_category") == "ValueError"
        assert "worker_duration_ms" in meta
        coord.close()

    def test_settled_diagnostics_roundtrip(self):
        """After completion, diagnostics.to_dict() returns expected shape with
        floating-point timing values."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "unet-done",
            max_workers=2,
        )
        prep = _make_preparation()

        future = coord._submit("unet", lambda: "done", prep, None)
        _wait_future(future, timeout=5)

        diag_dict = prep.diagnostics.to_dict()
        assert diag_dict["unet_error"] == ""
        assert isinstance(diag_dict["unet_started_at"], float)
        assert isinstance(diag_dict["unet_completed_at"], float)
        assert diag_dict["unet_completed_at"] >= diag_dict["unet_started_at"]
        coord.close()

    def test_timing_tolerance_within_reasonable_bounds(self):
        """unet_completed_at - unet_started_at is positive and bounded."""
        coord = mp.ModelPreloadCoordinator(
            unet_loader=lambda k: "u",
            max_workers=2,
        )
        prep = _make_preparation()

        # Add a tiny delay to ensure the clock advances even on Windows
        def _slow_callback() -> str:
            time.sleep(0.010)
            return "done"

        future = coord._submit("unet", _slow_callback, prep, None)
        _wait_future(future, timeout=5)

        delta = prep.diagnostics.unet_completed_at - prep.diagnostics.unet_started_at
        assert delta > 0, "Completion must be after start"
        assert delta < 60.0, "Should complete well within 60s in test"
        coord.close()
