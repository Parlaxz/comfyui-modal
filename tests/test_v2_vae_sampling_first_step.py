"""Focused tests for the experimental ``sampling_first_step`` VAE activation mode.

``COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step`` schedules the
transfer-only VAE early-start worker (the same worker the Experiment 2
``vae_overlap`` B arm uses) at the FIRST completed sampler step:

  - default remains ``late``; ``sampling_end`` keeps the production timing;
    ``sampling_first_step`` is the new experimental opt-in
  - the scheduler (``schedule_vae_early_activation_at_first_step``) is a
    no-op in every other mode and never creates state or trace events there
  - scheduling is exact-once / idempotent (one scheduled event, one state
    entry, one worker thread, at most one physical transfer)
  - the worker pre-copies VAE CPU params/buffers to CUDA on a side stream
    DURING sampling (no lane, no model mutation), then waits for the
    authoritative sampling_end event and performs a narrow lane-bound
    ``.data`` rebind strictly after the sampler released the mutation lane
  - VAEDecode demand joins the same future outside the lane; any
    resolution/load/validation failure falls back to the unchanged original
    graph loader path
  - emitted overlap timing (trigger_mono_ns / precopy_start_mono_ns /
    sampling_end_mono_ns / overlap_ms) reconciles against the real clocks
  - no UNET activation state/teardown or device mutation is introduced
"""

from __future__ import annotations

import contextlib
import time
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

from comfymodal_runtime import model_preload as mp
from comfymodal_runtime.trace import RuntimeTrace


# ── Fakes ────────────────────────────────────────────────────────────────


class _FakeCudaTensor:
    """Stand-in for the destination GPU tensor produced by ``.to(cuda)``."""

    def __init__(self) -> None:
        self.device = "cuda:0"
        self.dtype = "torch.float16"

    def element_size(self) -> int:
        return 4

    def numel(self) -> int:
        return 1


class _FakeDetachResult:
    """Stand-in for ``param.detach()`` whose ``.to(...)`` yields a fake cuda
    tensor WITHOUT real CUDA hardware."""

    def to(self, *args: Any, **kwargs: Any) -> _FakeCudaTensor:
        return _FakeCudaTensor()


class _FakeParam:
    """A non-torch parameter object: the worker's copy loop only touches
    ``.device.type``, ``.detach()``, ``.data`` (settable) and sizes."""

    def __init__(self, device_type: str = "cpu") -> None:
        self.device = SimpleNamespace(type=device_type)
        self.data = None

    def detach(self) -> _FakeDetachResult:
        return _FakeDetachResult()

    def element_size(self) -> int:
        return 4

    def numel(self) -> int:
        return 1


class _FakeInnerModel:
    def __init__(self, params: list[_FakeParam]) -> None:
        self._params = params

    def parameters(self):
        return iter(self._params)

    def buffers(self):
        return iter(())


class _DummyStream:
    def wait_stream(self, other: Any) -> None:
        return None


def _make_fake_vae(*, with_param: bool = False, param_device: str = "cpu"):
    """A SimpleNamespace-based fake VAE whose ``model`` exposes
    ``parameters()``/``buffers()``.  ``with_param=True`` adds ONE CPU param so
    the worker's copy loop produces one entry; ``param_device="cuda"`` makes
    that param already-resident so the copy loop skips it."""
    params: list[_FakeParam] = []
    if with_param:
        params.append(_FakeParam(device_type=param_device))
    return SimpleNamespace(
        model=_FakeInnerModel(params),
        patcher=SimpleNamespace(
            load_device="cuda:0",
            model_dtype=lambda: "torch.float16",
        ),
    )


class _FakeBridge:
    """Stand-in bridge: carries the real ``_join_vae_early_activation`` /
    ``_consume_vae_decode`` methods (bound from ``V2LoaderBridge``) so the
    graph-demand join path runs the actual production logic."""

    _preparation: Any = None
    _model_key: Any = None
    _trace: RuntimeTrace | None = None

    def __init__(self, vae: Any) -> None:
        self._preparation = object()
        self._model_key = SimpleNamespace(vae_identity="vae-test-id")
        self._trace = None
        self.resolve_vae_object = lambda trace=None: (vae, "snapshot_vae")
        self.coordinator = SimpleNamespace(
            schedule_vae_activation=lambda cb, prep, trace=None: None,
        )
        self.join_vae_cpu_prefetch_bounded = (
            lambda trace=None, request_id="", timeout_s=None, sampling_end_mono_ns=0: None
        )

    _join_vae_early_activation = mp.V2LoaderBridge._join_vae_early_activation
    _consume_vae_decode = mp.V2LoaderBridge._consume_vae_decode


def _make_fake_bridge(vae: Any) -> _FakeBridge:
    return _FakeBridge(vae)


# ── Test base ────────────────────────────────────────────────────────────


class _VaeFirstStepBase(unittest.TestCase):
    """Per-test environment reset + worker CUDA fakes.

    The worker requires real CUDA in production; on test machines we patch
    the CUDA touchpoints (side stream factory, ``torch.cuda.stream`` context
    manager, and ``_module_device``) so the full worker runs end-to-end with
    no GPU hardware.
    """

    def setUp(self) -> None:
        self._orig_mode = mp._VAE_ACTIVATION_MODE
        mp._VAE_ACTIVATION_MODE = mp._VAE_ACTIVATION_MODE_SAMPLING_FIRST_STEP
        # The global sampling-end Event is sticky — clear it every test so a
        # previously-set event can never release a worker early.
        mp._VAE_SAMPLING_END_EVENT.clear()
        mp._VAE_SAMPLING_END_MONO_NS = 0
        with mp._VAE_ACTIVATION_LOCK:
            mp._VAE_ACTIVATION_STATE.clear()
        self._orig_side_stream = mp._vae_side_stream
        mp._vae_side_stream = lambda: _DummyStream()
        self._orig_module_device = mp._module_device
        mp._module_device = lambda module: "cuda:0"
        self._stream_patcher = unittest.mock.patch(
            "torch.cuda.stream",
            return_value=contextlib.nullcontext(),
        )
        self._stream_patcher.start()
        self.addCleanup(self._stream_patcher.stop)
        self.addCleanup(self._restore_env)

    def _restore_env(self) -> None:
        with mp._VAE_ACTIVATION_LOCK:
            mp._VAE_ACTIVATION_STATE.clear()
        mp._VAE_SAMPLING_END_EVENT.clear()
        mp._VAE_SAMPLING_END_MONO_NS = 0
        lane = mp._get_mutation_lane()
        try:
            if lane.owner is not None:
                lane.release(lane.owner)
        except Exception:
            pass
        mp._VAE_ACTIVATION_MODE = self._orig_mode
        mp._vae_side_stream = self._orig_side_stream
        mp._module_device = self._orig_module_device

    def _set_mode(self, mode: str) -> None:
        mp._VAE_ACTIVATION_MODE = mode

    def _events_named(self, trace: RuntimeTrace, name: str):
        return [e for e in trace.events if e.name == name]

    def _schedule(
        self,
        bridge: _FakeBridge,
        trace: RuntimeTrace,
        request_id: str,
        first_step_mono_ns: int | None = None,
    ) -> bool:
        return mp.schedule_vae_early_activation_at_first_step(
            bridge,
            trace=trace,
            request_id=request_id,
            sampler_node_id="sampler_1",
            sampler_node_class="KSampler",
            first_step_mono_ns=first_step_mono_ns or time.monotonic_ns(),
        )

    def _wait_for_precopy_start(self, state: dict[str, Any], timeout: float = 5.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline and not state.get("precopy_start_mono_ns"):
            time.sleep(0.01)
        return bool(state.get("precopy_start_mono_ns"))

    def _release_sampling_end(self, trace: RuntimeTrace, request_id: str) -> None:
        """Simulate the authoritative sampling_end boundary exactly like
        production: the sampler owns the lane, then releases it (the release
        sets ``_VAE_SAMPLING_END_EVENT`` + ``_VAE_SAMPLING_END_MONO_NS``
        BEFORE the lane release)."""
        lane = mp._get_mutation_lane()
        try:
            if lane.owner is not None:
                lane.release(lane.owner)
        except Exception:
            pass
        lane.acquire("sampler")
        mp.release_sampler_mutation_lane_at_sampling_end(
            trace=trace,
            request_id=request_id,
        )

    def _run_worker_to_terminal(
        self,
        bridge: _FakeBridge,
        request_id: str,
        trace: RuntimeTrace,
        first_step_mono_ns: int | None = None,
    ) -> dict[str, Any]:
        ok = self._schedule(bridge, trace, request_id, first_step_mono_ns)
        self.assertTrue(ok, "schedule_vae_early_activation_at_first_step returned False")
        state = mp._vae_activation_get(request_id)
        self.assertIsNotNone(state, "no activation state after scheduling")
        # Guarantee the pre-copy already started before the sampling_end
        # boundary so the emitted overlap timings reconcile deterministically.
        self.assertTrue(self._wait_for_precopy_start(state))
        self._release_sampling_end(trace, request_id)
        state["future"].result(timeout=10)
        return state


# ── A. default sampling_end unchanged / default-off flag ────────────────


class ModeAndDefaultTests(_VaeFirstStepBase):
    def test_resolve_mode_normalization(self) -> None:
        self.assertEqual(mp._resolve_vae_activation_mode(""), "late")
        self.assertEqual(mp._resolve_vae_activation_mode("banana"), "late")
        self.assertEqual(mp._resolve_vae_activation_mode("sampling_end"), "sampling_end")
        self.assertEqual(
            mp._resolve_vae_activation_mode("sampling_first_step"),
            "sampling_first_step",
        )

    def test_active_set_membership(self) -> None:
        self.assertEqual(
            set(mp._VAE_ACTIVATION_MODE_ACTIVE),
            {"sampling_end", "sampling_first_step"},
        )

    def test_late_mode_is_noop(self) -> None:
        self._set_mode("late")
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="late-noop", process="test")
        self.assertFalse(self._schedule(bridge, trace, "late-noop"))
        self.assertIsNone(mp._vae_activation_get("late-noop"))
        vae_events = [
            e.name for e in trace.events
            if e.name.startswith("vae_early_activation_")
        ]
        self.assertEqual(vae_events, [])

    def test_sampling_end_mode_is_noop_for_first_step_scheduler(self) -> None:
        # The sampling_end scheduler owns the activation in that mode; the
        # first-step scheduler must stay a no-op (exactly one activation).
        self._set_mode("sampling_end")
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="se-noop", process="test")
        self.assertFalse(self._schedule(bridge, trace, "se-noop"))
        self.assertIsNone(mp._vae_activation_get("se-noop"))
        vae_events = [
            e.name for e in trace.events
            if e.name.startswith("vae_early_activation_")
        ]
        self.assertEqual(vae_events, [])


# ── B. sampling_first_step schedules once ───────────────────────────────


class ScheduleTests(_VaeFirstStepBase):
    def test_schedules_once_and_completes(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-sched", process="test")
        first_step_ns = time.monotonic_ns()
        state = self._run_worker_to_terminal(bridge, "fs-sched", trace, first_step_ns)
        self.assertEqual(state["trigger"], "sampling_first_step")
        self.assertEqual(state["owner"], "sampling_first_step")
        self.assertEqual(state["trigger_mono_ns"], first_step_ns)
        self.assertGreater(state["trigger_mono_ns"], 0)
        self.assertEqual(state["sampling_start_mono_ns"], first_step_ns)
        scheduled = self._events_named(trace, mp._EVENT_VAE_EA_SCHEDULED)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0].metadata.get("trigger"), "sampling_first_step")
        self.assertEqual(scheduled[0].metadata.get("trigger_mono_ns"), first_step_ns)
        self.assertEqual(state["status"], "ready")
        self.assertTrue(state["terminal"])
        # with_param=False -> the copy loop copied nothing.
        self.assertEqual(state["transfer_count"], 0)


# ── C. duplicate first-step notifications do not duplicate transfer ─────


class DuplicateScheduleTests(_VaeFirstStepBase):
    def test_duplicate_notifications_single_transfer(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-dup", process="test")
        real_thread = mp.Thread
        starts = {"count": 0}

        def counting_thread(*args: Any, **kwargs: Any):
            thread = real_thread(*args, **kwargs)
            orig_start = thread.start

            def counting_start():
                starts["count"] += 1
                return orig_start()

            thread.start = counting_start
            return thread

        patcher = unittest.mock.patch.object(mp, "Thread", side_effect=counting_thread)
        patcher.start()
        self.addCleanup(patcher.stop)
        t0 = time.monotonic_ns()
        self.assertTrue(self._schedule(bridge, trace, "fs-dup", t0))
        # A second first-step notification (different timestamp) must be an
        # idempotent no-op: no second state, no second thread, no reschedule.
        self.assertTrue(self._schedule(bridge, trace, "fs-dup", t0 + 100_000))
        self.assertEqual(len(self._events_named(trace, mp._EVENT_VAE_EA_SCHEDULED)), 1)
        self.assertEqual(len(mp._VAE_ACTIVATION_STATE), 1)
        self.assertEqual(starts["count"], 1)
        state = mp._vae_activation_get("fs-dup")
        self.assertIsNotNone(state)
        self.assertTrue(self._wait_for_precopy_start(state))
        self._release_sampling_end(trace, "fs-dup")
        state["future"].result(timeout=10)
        self.assertEqual(state["status"], "ready")
        # Never 2: the single transfer remains at its single value.
        self.assertEqual(state["transfer_count"], 0)


# ── D. VAE already ready -> no second load ──────────────────────────────


class AlreadyResidentTests(_VaeFirstStepBase):
    def test_already_cuda_param_not_retransferred(self) -> None:
        vae = _make_fake_vae(with_param=True, param_device="cuda")
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-ready", process="test")
        state = self._run_worker_to_terminal(bridge, "fs-ready", trace)
        # The copy loop skips the already-CUDA param -> no transfer performed.
        self.assertEqual(state["transfer_count"], 0)
        self.assertEqual(state["status"], "ready")
        self.assertTrue(state["terminal"])
        self.assertEqual(len(self._events_named(trace, mp._EVENT_VAE_EA_SCHEDULED)), 1)


# ── E. background not ready at decode -> bounded join ───────────────────


class BoundedJoinTests(_VaeFirstStepBase):
    def test_join_waits_for_background_with_bounded_timeout(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-joinwait", process="test")
        self.assertTrue(self._schedule(bridge, trace, "fs-joinwait"))
        state = mp._vae_activation_get("fs-joinwait")
        self.assertIsNotNone(state)
        self.assertTrue(self._wait_for_precopy_start(state))
        with ThreadPoolExecutor(max_workers=1) as pool:
            join_fut = pool.submit(
                bridge._join_vae_early_activation,
                trace=trace,
                demanded_vae=vae,
            )
            # Hold the worker in its phase-2 sampling-end wait, then release.
            time.sleep(0.2)
            self.assertFalse(join_fut.done())
            self._release_sampling_end(trace, "fs-joinwait")
            outcome = join_fut.result(timeout=5)
        self.assertTrue(outcome["valid"])
        self.assertEqual(outcome["status"], "ready")
        # The join is a full wait that completes when the background does —
        # measured, and bounded by the timeout-protected result().
        self.assertGreater(outcome["join_wait_ms"], 50.0)
        self.assertGreaterEqual(state.get("join_wait_ms", 0.0), 0.0)


# ── F. background ready before sampling end -> near-zero post-sampling join ─


class PostSamplingJoinTests(_VaeFirstStepBase):
    def test_join_after_completion_is_near_zero(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-joindone", process="test")
        state = self._run_worker_to_terminal(bridge, "fs-joindone", trace)
        outcome = bridge._join_vae_early_activation(trace=trace, demanded_vae=vae)
        self.assertTrue(outcome["valid"])
        self.assertEqual(outcome["status"], "ready")
        self.assertLess(outcome["join_wait_ms"], 50.0)
        consumed = self._events_named(trace, mp._EVENT_VAE_EA_CONSUMED)
        self.assertEqual(len(consumed), 1)
        self.assertEqual(consumed[0].metadata.get("transfer_count"), 0)
        self.assertEqual(consumed[0].metadata.get("trigger"), "sampling_first_step")


# ── G. background exception -> safe existing fallback ───────────────────


class FailureFallbackTests(_VaeFirstStepBase):
    def test_background_exception_safe_fallback(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-fail", process="test")
        # Force the worker's phase-1 pre-copy to raise; the real worker's own
        # except marks the state failed and completes the future with None.
        raiser = unittest.mock.patch(
            "torch.cuda.stream", side_effect=RuntimeError("boom"),
        )
        raiser.start()
        self.addCleanup(raiser.stop)
        self.assertTrue(self._schedule(bridge, trace, "fs-fail"))
        state = mp._vae_activation_get("fs-fail")
        self.assertIsNotNone(state)
        state["future"].result(timeout=10)
        self.assertEqual(state["status"], "failed")
        self.assertTrue(state["terminal"])
        self.assertEqual(state["reason"], "precopy_failed")
        failed = self._events_named(trace, mp._EVENT_VAE_EA_FAILED)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].metadata.get("reason"), "precopy_failed")
        outcome = bridge._join_vae_early_activation(trace=trace, demanded_vae=vae)
        self.assertFalse(outcome["valid"])
        self.assertTrue(state["fallback_elected"])
        self.assertEqual(state["fallback_reason"], "precopy_failed")
        fallback = self._events_named(trace, mp._EVENT_VAE_EA_FALLBACK)
        self.assertEqual(len(fallback), 1)
        # Decode demand falls back to the unchanged original path.
        bridge._trace = trace
        result = bridge._consume_vae_decode(("fake_vae",), {}, demanded_vae=vae)
        self.assertIs(result, mp._LOADER_MISS)
        current = mp._vae_activation_get("fs-fail")
        self.assertEqual(current["status"], "failed")
        self.assertTrue(current["terminal"])


# ── H. transfer_count remains exactly one ───────────────────────────────


class TransferCountTests(_VaeFirstStepBase):
    def test_transfer_count_exactly_one(self) -> None:
        vae = _make_fake_vae(with_param=True)
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-xfer1", process="test")
        state = self._run_worker_to_terminal(bridge, "fs-xfer1", trace)
        self.assertEqual(state["transfer_count"], 1)
        self.assertEqual(state["status"], "ready")
        self.assertTrue(state["terminal"])
        outcome = bridge._join_vae_early_activation(trace=trace, demanded_vae=vae)
        self.assertTrue(outcome["valid"])
        consumed = self._events_named(trace, mp._EVENT_VAE_EA_CONSUMED)
        self.assertEqual(len(consumed), 1)
        self.assertEqual(consumed[0].metadata.get("transfer_count"), 1)
        terminal = self._events_named(trace, mp._EVENT_VAE_EA_TERMINAL)
        self.assertEqual(len(terminal), 1)
        self.assertEqual(terminal[0].metadata.get("transfer_count"), 1)
        # A duplicate schedule after completion never transfers again.
        self.assertTrue(self._schedule(bridge, trace, "fs-xfer1"))
        self.assertEqual(state["transfer_count"], 1)
        self.assertEqual(
            len(self._events_named(trace, mp._EVENT_VAE_EA_SCHEDULED)), 1,
        )


# ── I. no UNET teardown/device mutation introduced ──────────────────────


class NoUnetMutationTests(_VaeFirstStepBase):
    def test_lane_deferral_and_no_unet_teardown(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-lane", process="test")
        unet_mode_before = mp._UNET_ACTIVATION_MODE
        with mp._UNET_ACTIVATION_LOCK:
            unet_state_before = dict(mp._UNET_ACTIVATION_STATE)
        lane = mp._get_mutation_lane()
        try:
            if lane.owner is not None:
                lane.release(lane.owner)
        except Exception:
            pass
        lane.acquire("sampler")
        self.assertTrue(self._schedule(bridge, trace, "fs-lane"))
        state = mp._vae_activation_get("fs-lane")
        self.assertIsNotNone(state)
        self.assertTrue(self._wait_for_precopy_start(state))
        time.sleep(0.05)
        # While sampling (event not released) the worker must NOT grab the
        # lane — the sampler keeps it until the authoritative boundary.
        self.assertEqual(lane.owner, "sampler")
        with mp._UNET_ACTIVATION_LOCK:
            self.assertEqual(dict(mp._UNET_ACTIVATION_STATE), unet_state_before)
        self.assertEqual(mp._UNET_ACTIVATION_MODE, unet_mode_before)
        # Release the boundary; only then does the worker's phase-3 bind run.
        mp.release_sampler_mutation_lane_at_sampling_end(
            trace=trace, request_id="fs-lane",
        )
        state["future"].result(timeout=10)
        self.assertEqual(state["status"], "ready")
        self.assertTrue(state["terminal"])
        self.assertIsNone(lane.owner)


# ── J. emitted overlap timing reconciles ────────────────────────────────


class ReconciliationTimingTests(_VaeFirstStepBase):
    def test_emitted_overlap_timing_reconciles(self) -> None:
        vae = _make_fake_vae()
        bridge = _make_fake_bridge(vae)
        trace = RuntimeTrace(request_id="fs-timing", process="test")
        trigger_ns = time.monotonic_ns()
        state = self._run_worker_to_terminal(bridge, "fs-timing", trace, trigger_ns)
        outcome = bridge._join_vae_early_activation(trace=trace, demanded_vae=vae)
        self.assertTrue(outcome["valid"])
        # The worker's phase-3 reconciliation carries the new telemetry.
        rec_events = self._events_named(trace, mp._EVENT_VAE_EA_RECONCILIATION)
        self.assertGreaterEqual(len(rec_events), 1)
        rec = rec_events[0].metadata
        self.assertEqual(rec.get("trigger"), "sampling_first_step")
        self.assertGreater(rec.get("trigger_mono_ns", 0), 0)
        # transfer started at or after the first-step trigger ...
        self.assertGreaterEqual(
            rec.get("precopy_start_mono_ns", 0),
            rec.get("trigger_mono_ns", 0),
        )
        # ... and sampling end came after the transfer started.
        self.assertGreaterEqual(
            rec.get("sampling_end_mono_ns", 0),
            rec.get("precopy_start_mono_ns", 0),
        )
        overlap = rec.get("overlap_ms", -1.0)
        self.assertGreaterEqual(overlap, 0.0)
        expected_ms = (
            (rec.get("sampling_end_mono_ns", 0) - rec.get("precopy_start_mono_ns", 0))
            / 1_000_000
        )
        self.assertAlmostEqual(overlap, expected_ms, delta=1.0)
        self.assertGreaterEqual(rec.get("sampling_end_wait_ms", -1.0), 0.0)
        self.assertGreaterEqual(state.get("join_wait_ms", -1.0), 0.0)
        self.assertIn(state.get("transfer_count", -1), (0, 1))

        def first_mono(name: str):
            events = self._events_named(trace, name)
            return events[0].monotonic_ns if events else None

        t_sched = first_mono(mp._EVENT_VAE_EA_SCHEDULED)
        t_load = first_mono(mp._EVENT_VAE_EA_LOAD_START)
        t_term = first_mono(mp._EVENT_VAE_EA_TERMINAL)
        t_cons = first_mono(mp._EVENT_VAE_EA_CONSUMED)
        self.assertIsNotNone(t_sched)
        self.assertIsNotNone(t_load)
        self.assertIsNotNone(t_term)
        self.assertIsNotNone(t_cons)
        self.assertLessEqual(t_sched, t_load)
        self.assertLessEqual(t_load, t_term)
        self.assertLessEqual(t_term, t_cons)
        # Request-end cleanup pops the state and emits its own reconciliation.
        finalized = mp.finalize_vae_early_activation("fs-timing", trace=trace)
        self.assertIsNotNone(finalized)
        self.assertEqual(finalized["status"], "ready")
        self.assertEqual(finalized["trigger"], "sampling_first_step")
        self.assertIsNone(mp._vae_activation_get("fs-timing"))
        self.assertGreaterEqual(
            len(self._events_named(trace, mp._EVENT_VAE_EA_RECONCILIATION)), 2,
        )
