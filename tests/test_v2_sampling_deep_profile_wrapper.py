"""Wrapper-integration tests for the gated sampling deep profile.

Runs the REAL production ``SAMPLER_SAMPLE`` wrapper
(``comfymodal_runtime.runtime_executor._COMFYMODAL_V2_SAMPLING_WRAPPER``)
through a faithful WrapperExecutor chain with fake KSamplerX0Inpaint /
diffusion model / CacheDiT counters / torch.cuda.

Covers:
  - off path: no ``sampling_deep_profile`` trace event, no class patch
  - blocks flow: event ordering sampling_start < sampling_end < profile event,
    exact 17 evals, compute/skip 10/7, patch/hook restoration
  - post-sampling finalization ordering: no CUDA synchronize within the
    sampling window, exactly one after ``sampling_end``
  - exception path still emits ``sampling_end`` + profile event and restores
  - None callback still profiles (callbacks absent warning)
  - steps mode keeps hook overhead minimal (forward hooks only)

No GPU / Modal.  The dev machine may have a real GPU; ``_resolve_cuda_module``
is always stubbed so no real CUDA API is touched.
"""

from __future__ import annotations

import json
import asyncio
import os
import time
import unittest
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

from comfymodal_runtime import golden_serial as gs
from comfymodal_runtime import sampling_deep_profile as sdp
from comfymodal_runtime.runtime_executor import _COMFYMODAL_V2_SAMPLING_WRAPPER
from comfymodal_runtime.trace import RuntimeTrace


def _unfreeze_json(o):
    """JSON default handler: convert RuntimeTrace-frozen containers back to
    plain dicts/lists for serialization assertions."""
    if isinstance(o, MappingProxyType):
        return dict(o)
    if isinstance(o, tuple):
        return list(o)
    raise TypeError(f"not serializable: {type(o).__name__}")


def _make_faithful_wrapper_executor(original, wrappers):
    try:
        import comfy.patcher_extension as pe  # type: ignore[import-not-found]
        return pe.WrapperExecutor.new_executor(original, wrappers, 0)
    except ImportError:
        class _FakeWE:
            def __init__(self, orig, wlist, idx):
                self.original = orig
                self.wrappers = list(wlist)
                self.idx = idx
                self.is_last = idx == len(wlist)

            def __call__(self, *args, **kwargs):
                return _FakeWE(self.original, self.wrappers, self.idx + 1).execute(*args, **kwargs)

            def execute(self, *args, **kwargs):
                if self.is_last:
                    return self.original(*args, **kwargs)
                return self.wrappers[self.idx](self, *args, **kwargs)

        return _FakeWE(original, wrappers, 0)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeHandle:
    def __init__(self, owner, hook):
        self.owner = owner
        self.hook = hook

    def remove(self):
        if self.hook in self.owner._pre:
            self.owner._pre.remove(self.hook)
        if self.hook in self.owner._post:
            self.owner._post.remove(self.hook)


class _FakeNN:
    attention: Any = None
    feed_forward: Any = None
    attention_norm1: Any = None
    attention_norm2: Any = None
    ffn_norm1: Any = None
    ffn_norm2: Any = None
    adaLN_modulation: Any = None

    def __init__(self, name="m"):
        self.name = name
        self._pre = []
        self._post = []
        self._children = []
        self.device = "cuda:0"
        self.current_device = "cuda:0"

    def register_forward_pre_hook(self, hook, **kw):
        self._pre.append(hook)
        return _FakeHandle(self, hook)

    def register_forward_hook(self, hook, **kw):
        self._post.append(hook)
        return _FakeHandle(self, hook)

    def parameters(self):
        return iter([])

    @property
    def pre_hook_count(self):
        return len(self._pre)

    @property
    def post_hook_count(self):
        return len(self._post)

    def __call__(self, *args, **kwargs):
        for h in self._pre:
            h(self, args, kwargs)
        out = self._run(*args, **kwargs)
        for h in self._post:
            r = h(self, args, out)
            if r is not None:
                out = r
        return out

    def _run(self, *args, **kwargs):
        x = args[0]
        for c in self._children:
            x = c(x)
        return x


def _make_block(i):
    b = _FakeNN(f"block{i}")
    b.attention = _FakeNN(f"block{i}.attention")
    b.feed_forward = _FakeNN(f"block{i}.mlp")
    b.attention_norm1 = _FakeNN("an1")
    b.attention_norm2 = _FakeNN("an2")
    b.ffn_norm1 = _FakeNN("fn1")
    b.ffn_norm2 = _FakeNN("fn2")
    b.adaLN_modulation = _FakeNN("adain")
    b._children = [
        b.adaLN_modulation, b.attention_norm1, b.attention,
        b.attention_norm2, b.ffn_norm1, b.feed_forward, b.ffn_norm2,
    ]
    return b


class _FakeNextDiT(_FakeNN):
    def __init__(self, n_layers=4):
        super().__init__("NextDiT")
        self.layers = [_make_block(i) for i in range(n_layers)]
        self.noise_refiner = [_make_block("nr0"), _make_block("nr1")]
        self.context_refiner = [_make_block("cr0"), _make_block("cr1")]
        self.x_embedder = _FakeNN("x_embedder")
        self.final_layer = _FakeNN("final_layer")
        self.t_embedder = _FakeNN("t_embedder")
        self.cap_embedder = _FakeNN("cap_embedder")
        self._children = (
            [self.t_embedder, self.cap_embedder, self.x_embedder]
            + self.noise_refiner + self.context_refiner + self.layers
            + [self.final_layer]
        )
        self.skip = False

    def _run(self, *args, **kwargs):
        if self.skip:
            return args[0]
        return super()._run(*args, **kwargs)


class _FakeKSamplerX0Inpaint:
    def __init__(self, inner_model=None, sigmas=None):
        self.inner_model = inner_model
        self.sigmas = sigmas
        self.call_count = 0

    def __call__(self, x, sigma, denoise_mask=None, model_options=None, seed=None):
        self.call_count += 1
        if self.inner_model is not None:
            idx = self.call_count
            self.inner_model.skip = idx > 3 and (idx - 3) % 2 == 0
            return self.inner_model(x, sigma)
        return x


class _FakeCuda:
    sync_count = 0

    class _FakeEvent:
        def __init__(self, enable_timing=True):
            pass

        def record(self, stream=None):
            pass

        def elapsed_time(self, other):
            return 0.05

    @classmethod
    def Event(cls, enable_timing=True):
        return cls._FakeEvent(enable_timing)

    @classmethod
    def is_available(cls):
        return True

    @classmethod
    def synchronize(cls):
        cls.sync_count += 1


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


class _WrapperHarnessMixin(unittest.TestCase):
    _level = "blocks"

    def setUp(self):
        from comfymodal_runtime.runtime_executor import _sampler_wrapper_dedup
        _sampler_wrapper_dedup.clear()
        from comfymodal_runtime import model_preload as mp
        self.mp = mp
        with mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            mp._SAMPLER_STALL_WATCHDOGS.clear()
        self.addCleanup(self._cleanup)
        self._old_flag = os.environ.get(sdp.FLAG_ENV)
        os.environ[sdp.FLAG_ENV] = self._level
        self.trace = RuntimeTrace(request_id="sdp-wrap", process="test")
        self._token = self.mp._ACTIVE_REQUEST_TRACE.set(self.trace)
        self.dm = _FakeNextDiT(n_layers=4)
        self.patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=self.dm))
        self.guider = SimpleNamespace(
            _node_id="1242", _class_type="ClownsharKSampler_Beta", model_patcher=self.patcher,
        )
        self.ksampler = _FakeKSamplerX0Inpaint(inner_model=self.dm)
        self.p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self.p.start()
        self.addCleanup(self.p.stop)

    def _cleanup(self):
        try:
            self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        except Exception:
            pass
        with self.mp._SAMPLER_STALL_WATCHDOG_LOCK:
            for wd in list(self.mp._SAMPLER_STALL_WATCHDOGS.values()):
                wd.cancel()
            self.mp._SAMPLER_STALL_WATCHDOGS.clear()
        if self._old_flag is None:
            os.environ.pop(sdp.FLAG_ENV, None)
        else:
            os.environ[sdp.FLAG_ENV] = self._old_flag
        sdp.reset_for_tests()

    def _run_wrapper(self, callback=None, failing=False):
        def original(*args, **kwargs):
            cb = args[3] if len(args) > 3 else None
            if failing:
                self.ksampler(1, 0.5)
                raise RuntimeError("sampler boom")
            for s in range(8):
                self.ksampler(1, 0.5)
                self.ksampler(1, 0.3)
                if callable(cb):
                    cb(s, "denoised", "x", 8)
            self.ksampler(1, 0.01)  # final teardown eval
            if callable(cb):
                cb(8, "denoised", "x", 8)
            return {"latent": "ok"}

        executor = _make_faithful_wrapper_executor(original, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
        return executor.execute(
            self.guider,
            type("S", (), {"__len__": lambda self: 9})(),
            {}, callback, None, None, None, None,
        )

    def _profile_events(self):
        return [e for e in self.trace.events if e.name == "sampling_deep_profile"]

    def _event_names(self):
        return [e.name for e in self.trace.events]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class OffPathWrapperTests(_WrapperHarnessMixin):
    _level = "off"

    def test_off_path_no_profile_event_no_patch(self):
        with patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCuda):
            result = self._run_wrapper(callback=lambda *a: "cb")
        self.assertEqual(result, {"latent": "ok"})
        self.assertEqual(self._profile_events(), [])
        self.assertNotIn("sampling_deep_profile", self._event_names())
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        # normal authoritative events still present
        names = self._event_names()
        self.assertIn("sampling_start", names)
        self.assertIn("sampling_end", names)


class BlocksWrapperTests(_WrapperHarnessMixin):
    _level = "blocks"

    def _set_fakes(self):
        _FakeCuda.sync_count = 0
        cuda_p = patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCuda)
        cd_p = patch.object(
            sdp, "_read_cachedit_counters",
            lambda d, p: {"discoverable": True, "attached": True,
                          "call_count": 17, "compute_count": 10, "skip_count": 7},
        )
        cuda_p.start()
        cd_p.start()
        self.addCleanup(cuda_p.stop)
        self.addCleanup(cd_p.stop)

    def test_full_blocks_flow_and_event_ordering(self):
        self._set_fakes()
        seen = []
        result = self._run_wrapper(callback=lambda *a: seen.append(a[0]))
        self.assertEqual(result, {"latent": "ok"})
        self.assertEqual(seen, list(range(9)))
        names = self._event_names()
        self.assertEqual(
            names.index("sampling_start") < names.index("sampling_end") < names.index("sampling_deep_profile"),
            True,
        )
        art = self._profile_events()[0].metadata
        self.assertEqual(art["status"], "ok")
        self.assertEqual(art["level"], "blocks")
        self.assertEqual(art["evals"]["count"], 17)
        self.assertEqual(art["evals"]["expected"], 17)
        self.assertEqual(art["compute_or_skip"], {"compute": 10, "skip": 7, "unknown": 0})
        self.assertEqual(art["cachedit"]["call_count"], 17)
        # sampling_end emitted BEFORE the profile finalization (post-boundary)
        self.assertEqual(art["instrumentation_overhead"]["placement"], "post_sampling_end_cleanup")
        # patch and hooks restored
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(self.dm.pre_hook_count, 0)
        self.assertEqual(self.dm.layers[0].pre_hook_count, 0)

    def test_lane_trace_context_profiles_when_request_context_is_absent(self):
        self._set_fakes()
        request_trace = self.trace
        self.mp._ACTIVE_REQUEST_TRACE.reset(self._token)
        lane = self.mp.ModelLaneTrace(request_trace, "UNET")
        lane_token = self.mp._ACTIVE_LANE_TRACE.set(lane)
        try:
            self._run_wrapper(callback=lambda *a: None)
        finally:
            self.mp._ACTIVE_LANE_TRACE.reset(lane_token)
            self._token = self.mp._ACTIVE_REQUEST_TRACE.set(request_trace)
        self.assertEqual(len(self._profile_events()), 1)
        self.assertEqual(self._profile_events()[0].metadata["status"], "ok")

    def test_no_cuda_sync_within_sampling_window(self):
        self._set_fakes()
        sync_inside = {"v": 0}

        def original(*args, **kwargs):
            cb = args[3]
            for s in range(8):
                self.ksampler(1, 0.5)
                self.ksampler(1, 0.3)
                sync_inside["v"] = _FakeCuda.sync_count
                cb(s, "d", "x", 8)
            self.ksampler(1, 0.01)
            sync_inside["v"] = _FakeCuda.sync_count
            cb(8, "d", "x", 8)
            return {"latent": "ok"}

        executor = _make_faithful_wrapper_executor(original, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
        executor.execute(
            self.guider, type("S", (), {"__len__": lambda self: 9})(),
            {}, lambda *a: "cb", None, None, None, None,
        )
        self.assertEqual(sync_inside["v"], 0, "no synchronize inside sampling_start→sampling_end")
        self.assertEqual(_FakeCuda.sync_count, 1, "exactly one post-boundary synchronize")
        art = self._profile_events()[0].metadata
        self.assertTrue(art["clocks"]["cuda_events"])
        # the profile event is emitted after sampling_end in the trace
        names = self._event_names()
        self.assertLess(names.index("sampling_end"), names.index("sampling_deep_profile"))
        # P0-3: CUDA timing results serialize through the trace metadata.
        self.assertGreater(len(art.get("cuda_timings_ms") or {}), 0)
        self.assertIn("forward", art.get("cuda_timings_ms") or {})
        # RuntimeTrace freezes metadata (mappingproxy); unfreeze for the JSON
        # round-trip assertion.
        payload = json.loads(json.dumps(dict(art), default=_unfreeze_json))
        self.assertGreater(len(payload["cuda_timings_ms"]), 0)
        for v in payload["cuda_timings_ms"].values():
            self.assertIsInstance(v, (int, float))

    def test_sampling_end_emission_failure_still_finalizes_and_restores(self):
        """P1-4: if trace.emit('sampling_end') raises, the deep-profile
        finalization must still run (patch/hooks restored, owner cleared) and
        the original sampler exception must propagate unaltered."""
        from comfymodal_runtime.model_preload import _ACTIVE_REQUEST_TRACE

        class _RaisingEndTrace(RuntimeTrace):
            def emit(self, name, **kwargs):
                if name == "sampling_end":
                    raise RuntimeError("emit boom")
                return super().emit(name, **kwargs)

        trace = _RaisingEndTrace(request_id="sdp-fail", process="test")
        token = _ACTIVE_REQUEST_TRACE.set(trace)
        try:
            _FakeCuda.sync_count = 0
            with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
                 patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
                def failing(*args, **kwargs):
                    self.ksampler(1, 0.5)
                    raise ValueError("sampler boom")

                executor = _make_faithful_wrapper_executor(failing, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
                with self.assertRaises(ValueError) as ctx:
                    executor.execute(
                        self.guider, type("S", (), {"__len__": lambda self: 9})(),
                        {}, lambda *a: "cb", None, None, None, None,
                    )
                self.assertIn("sampler boom", str(ctx.exception))
        finally:
            _ACTIVE_REQUEST_TRACE.reset(token)
        # Patch/hooks restored despite the sampling_end emission failure.
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(self.dm.pre_hook_count, 0)
        # Profile event still emitted (with the failure warning recorded).
        prof_events = [e for e in trace.events if e.name == "sampling_deep_profile"]
        self.assertEqual(len(prof_events), 1)
        meta = prof_events[0].metadata
        self.assertTrue(any("sampling_end_emission_failed" in w for w in meta["warnings"]))

    def test_exception_still_emits_profile_event_and_restores(self):
        self._set_fakes()
        with patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            with self.assertRaises(RuntimeError):
                self._run_wrapper(callback=None, failing=True)
        names = self._event_names()
        self.assertIn("sampling_start", names)
        self.assertIn("sampling_end", names)
        self.assertIn("sampling_deep_profile", names)
        art = self._profile_events()[0].metadata
        self.assertEqual(art["status"], "incomplete")
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(self.dm.pre_hook_count, 0)

    def test_none_callback_still_profiles(self):
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            result = self._run_wrapper(callback=None)
        self.assertEqual(result, {"latent": "ok"})
        art = self._profile_events()[0].metadata
        self.assertEqual(art["evals"]["count"], 17)
        self.assertTrue(any("callbacks_absent" in w for w in art["warnings"]))
        self.assertEqual(art["status"], "ok")


class StepsWrapperTests(_WrapperHarnessMixin):
    _level = "steps"

    def test_steps_mode_forward_hooks_only_low_overhead(self):
        hook_counts = {}

        def original(*args, **kwargs):
            hook_counts["dm_pre"] = self.dm.pre_hook_count
            hook_counts["block_pre"] = self.dm.layers[0].pre_hook_count
            hook_counts["refiner_pre"] = self.dm.noise_refiner[0].pre_hook_count
            hook_counts["attn_pre"] = self.dm.layers[0].attention.pre_hook_count
            hook_counts["norm_pre"] = self.dm.layers[0].attention_norm1.pre_hook_count
            hook_counts["embed_pre"] = self.dm.x_embedder.pre_hook_count
            cb = args[3]
            for s in range(8):
                self.ksampler(1, 0.5)
                self.ksampler(1, 0.3)
                cb(s, "d", "x", 8)
            self.ksampler(1, 0.01)
            cb(8, "d", "x", 8)
            return {"latent": "ok"}

        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            executor = _make_faithful_wrapper_executor(original, [_COMFYMODAL_V2_SAMPLING_WRAPPER])
            result = executor.execute(
                self.guider, type("S", (), {"__len__": lambda self: 9})(),
                {}, lambda *a: "cb", None, None, None, None,
            )
        self.assertEqual(result, {"latent": "ok"})
        art = self._profile_events()[0].metadata
        self.assertEqual(art["level"], "steps")
        self.assertEqual(art["evals"]["count"], 17)
        # Steps mode installs the dm forward hook + block-total compute-marker
        # hooks on main/refiner blocks — no category sub-hooks, no
        # embeddings/output hooks — and still classifies compute vs skip.
        self.assertEqual(hook_counts["dm_pre"], 1)
        self.assertEqual(hook_counts["block_pre"], 1)
        self.assertEqual(hook_counts["refiner_pre"], 1)
        self.assertEqual(hook_counts["attn_pre"], 0)
        self.assertEqual(hook_counts["norm_pre"], 0)
        self.assertEqual(hook_counts["embed_pre"], 0)
        self.assertEqual(
            dict(art.get("compute_or_skip") or {}),
            {"compute": 10, "skip": 7, "unknown": 0},
        )
        # No block-category data at steps level (RuntimeTrace freezes metadata
        # lists into tuples, so normalize before comparing).
        self.assertEqual(list(art.get("blocks") or []), [])
        self.assertEqual(dict(art.get("categories_ms") or {}), {})
        # Hooks removed after finalize.
        self.assertEqual(self.dm.pre_hook_count, 0)


class GoldenRunnerProfileTests(_WrapperHarnessMixin):
    """The canonical Golden runner bypasses ComfyUI's wrapper executor."""

    _level = "blocks"

    def _run_golden(self, *, failing=False):
        class _Runner:
            def __init__(self, fail):
                self.fail = fail
                self.cache = {}
                self.executed = []

            def begin_scope(self, _allowed):
                pass

            def end_scope(self):
                pass

            async def run_closure(self, target_id, *, include_target):
                assert include_target is True
                if self.fail:
                    raise RuntimeError("golden sampler boom")
                self.executed.append({
                    "node_id": target_id,
                    "class_type": "ClownsharKSampler_Beta",
                    "stage_class": "sampling",
                })
                self.cache[target_id] = gs._CacheEntry(outputs=[["latent"]])
                return self.executed_summary()

            def executed_summary(self):
                return [
                    (item["node_id"], item["class_type"], item["stage_class"])
                    for item in self.executed
                ]

        runner = _Runner(failing)
        session = SimpleNamespace(
            recorder=gs.GoldenTelemetryRecorder(),
            request=SimpleNamespace(
                prompt={"1242": {"inputs": {"steps": 8}}},
            ),
            contract=SimpleNamespace(sampler_class_type="ClownsharKSampler_Beta"),
            node_map=SimpleNamespace(sampler_id="1242"),
            runner=runner,
            patcher=self.patcher,
        )
        return session, runner

    def _execute_golden(self, session):
        runtime_executor = __import__(
            "comfymodal_runtime.runtime_executor",
            fromlist=["ensure_sampling_timing_wrapper"],
        )
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(runtime_executor, "ensure_sampling_timing_wrapper", return_value=True):
            return asyncio.run(gs.golden_sampling(session))  # type: ignore[arg-type]

    def test_canonical_runner_emits_profile_to_trace_and_recorder(self):
        session, _runner = self._run_golden()
        result = self._execute_golden(session)

        self.assertEqual(result, [["latent"]])
        names = [event.name for event in self.trace.events]
        self.assertLess(names.index("sampling_start"), names.index("sampling_end"))
        self.assertLess(names.index("sampling_end"), names.index("sampling_deep_profile"))
        recorder_events = [
            event for event in session.recorder.events
            if event["name"] == "sampling_deep_profile"
        ]
        self.assertEqual(len(recorder_events), 1)
        artifact = recorder_events[0]["fields"]["metadata"]
        self.assertEqual(artifact["level"], "blocks")
        self.assertLess(len(json.dumps(artifact)), 512 * 1024)

    def test_canonical_runner_finalizes_profile_on_exception(self):
        session, _runner = self._run_golden(failing=True)
        with self.assertRaisesRegex(RuntimeError, "golden sampler boom"):
            self._execute_golden(session)

        names = [event.name for event in self.trace.events]
        self.assertIn("sampling_start", names)
        self.assertIn("sampling_end", names)
        self.assertIn("sampling_deep_profile", names)
        recorder_events = [
            event for event in session.recorder.events
            if event["name"] == "sampling_deep_profile"
        ]
        self.assertEqual(len(recorder_events), 1)

    def test_profile_setup_failure_does_not_escape_golden_sampler(self):
        session, _runner = self._run_golden()
        with patch.object(
            sdp,
            "begin_sampling_profile",
            side_effect=RuntimeError("profile setup boom"),
        ):
            result = self._execute_golden(session)

        self.assertEqual(result, [["latent"]])
        names = [event.name for event in self.trace.events]
        self.assertEqual(names.count("sampling_start"), 1)
        self.assertEqual(names.count("sampling_end"), 1)
        self.assertLess(names.index("sampling_start"), names.index("sampling_end"))
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        markers = [
            event for event in session.recorder.events
            if event["name"] == "sampling_deep_profile_setup_failed"
        ]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["fields"]["error"], "RuntimeError")
        self.assertTrue(markers[0]["fields"]["profiling_disabled"])
        self.assertTrue(markers[0]["fields"]["measurement_only"])

    def test_existing_profile_owner_is_not_duplicated(self):
        session, _runner = self._run_golden()
        token = sdp._CURRENT_PROFILE.set(cast(Any, object()))
        try:
            self._execute_golden(session)
        finally:
            sdp._CURRENT_PROFILE.reset(token)
        names = [event.name for event in self.trace.events]
        self.assertNotIn("sampling_start", names)
        self.assertNotIn("sampling_deep_profile", names)


if __name__ == "__main__":
    unittest.main()
