"""Focused tests for the gated sampling deep profile module.

No GPU / Modal.  Uses fakes for the KSamplerX0Inpaint class, the diffusion
model (fake nn.Module with forward-hook registry), CacheDiT counters, and
torch.cuda.  Covers:

  - flag resolution (default off, invalid -> off, env vs flag file)
  - off path never patches / never emits events
  - Level A: 8 steps x 2 evals + 1 final teardown eval (17) classification
    via callback indices 0..8
  - exact setup/steps/teardown reconciliation with derived residuals
  - missing/extra evals and callbacks reported as errors/absent flags
  - compute vs CacheDiT skip and the 17/10/7 cross-check using fakes
  - block attention / MLP / norm residual aggregation using fake nn.Modules
  - exception cleanup / restoration of the class patch and hooks
  - post-sampling finalization ordering: no CUDA sync before finalize
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from comfymodal_runtime import sampling_deep_profile as sdp
from comfymodal_runtime import golden_serial as golden


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
    """Minimal nn.Module-like object with a forward-hook registry."""

    # Dynamic submodule slots set on block fakes (declared for the type checker).
    attention: Any = None
    feed_forward: Any = None
    attention_norm1: Any = None
    attention_norm2: Any = None
    ffn_norm1: Any = None
    ffn_norm2: Any = None
    adaLN_modulation: Any = None
    _impl: Any = None

    def __init__(self, name="m"):
        self.name = name
        self._pre: list = []
        self._post: list = []
        self._children: list = []
        self._impl = None
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
        if self._impl is not None:
            return self._impl(*args, **kwargs)
        x = args[0]
        for c in self._children:
            x = c(x)
        return x

    @property
    def pre_hook_count(self):
        return len(self._pre)

    @property
    def post_hook_count(self):
        return len(self._post)


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
        # Optional injection point for failure tests (declared for type checker).
        self._impl: Any = None

    def _run(self, *args, **kwargs):
        if self.skip:
            return args[0]
        return super()._run(*args, **kwargs)


class _FakeKSamplerX0Inpaint:
    """Replacement for comfy.samplers.KSamplerX0Inpaint (patched by profile)."""

    def __init__(self, inner_model=None, sigmas=None):
        self.inner_model = inner_model
        self.sigmas = sigmas
        self.call_count = 0

    def __call__(self, x, sigma, denoise_mask=None, model_options=None, seed=None):
        self.call_count += 1
        if self.inner_model is not None:
            idx = self.call_count
            # CacheDiT cadence for warmup=3 / skip_interval=2 (1-indexed):
            # skips at 5,7,9,11,13,15,17.
            self.inner_model.skip = idx > 3 and (idx - 3) % 2 == 0
            return self.inner_model(x, sigma)
        return x


class _FakeCuda:
    sync_count = 0
    elapsed_total_ms = 0.0

    class _FakeEvent:
        def __init__(self, enable_timing=True):
            pass

        def record(self, stream=None):
            pass

        def elapsed_time(self, other):
            _FakeCuda.elapsed_total_ms += 0.05
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


class _FakeStream:
    def __init__(self, query_results, device="cuda:0"):
        self._query_results = iter(query_results)
        self.query_count = 0
        self.device = device

    def query(self):
        self.query_count += 1
        return next(self._query_results)


class _FakeCudaWithStream(_FakeCuda):
    stream: Any = None
    current_stream_count = 0

    @classmethod
    def current_stream(cls):
        cls.current_stream_count += 1
        return cls.stream


class _FakeTrace:
    def __init__(self, request_id="t"):
        self.request_id = request_id
        self.events = []

    def emit(self, name, **kwargs):
        ev = SimpleNamespace(
            name=name,
            monotonic_ns=time.monotonic_ns(),
            wall_unix_ns=time.time_ns(),
            metadata=dict(kwargs.get("metadata") or {}),
        )
        self.events.append(ev)
        return ev


class _CallableWithBrokenMetadata:
    def __getattribute__(self, name):
        if name in {"__module__", "__qualname__", "__name__", "__closure__"}:
            raise RuntimeError("broken callable metadata")
        return object.__getattribute__(self, name)

    def __call__(self, *args, **kwargs):
        return None


# ---------------------------------------------------------------------------
# Flag resolution
# ---------------------------------------------------------------------------


class FlagResolutionTests(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop(sdp.FLAG_ENV, None)
        self._old_file = sdp.FLAG_FILE

    def tearDown(self):
        if self._old is not None:
            os.environ[sdp.FLAG_ENV] = self._old
        else:
            os.environ.pop(sdp.FLAG_ENV, None)
        sdp.FLAG_FILE = self._old_file

    def test_default_off_when_unset_and_file_missing(self):
        sdp.FLAG_FILE = "/nonexistent/sampling_deep_profile.txt"
        self.assertEqual(sdp.resolve_profile_level(), "off")

    def test_invalid_value_off(self):
        os.environ[sdp.FLAG_ENV] = "bogus"
        self.assertEqual(sdp.resolve_profile_level(), "off")

    def test_empty_value_off(self):
        os.environ[sdp.FLAG_ENV] = ""
        self.assertEqual(sdp.resolve_profile_level(), "off")

    def test_steps_and_blocks_accepted_case_insensitive(self):
        os.environ[sdp.FLAG_ENV] = "STEPS"
        self.assertEqual(sdp.resolve_profile_level(), "steps")
        os.environ[sdp.FLAG_ENV] = "Blocks"
        self.assertEqual(sdp.resolve_profile_level(), "blocks")

    def test_flag_file_read_when_env_absent(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("steps")
            path = f.name
        try:
            sdp.FLAG_FILE = path
            self.assertEqual(sdp.resolve_profile_level(), "steps")
        finally:
            os.unlink(path)

    def test_env_wins_over_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("blocks")
            path = f.name
        try:
            sdp.FLAG_FILE = path
            os.environ[sdp.FLAG_ENV] = "off"
            self.assertEqual(sdp.resolve_profile_level(), "off")
        finally:
            os.unlink(path)

    def test_flag_file_invalid_value_off(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("loud")
            path = f.name
        try:
            sdp.FLAG_FILE = path
            self.assertEqual(sdp.resolve_profile_level(), "off")
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Off path
# ---------------------------------------------------------------------------


class OffPathTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)

    def test_off_returns_none_and_patches_nothing(self):
        trace = _FakeTrace()
        prof = sdp.begin_sampling_profile(
            trace, level="off", node_id="n", node_class="K", steps=8,
            sampling_start_monotonic_ns=time.monotonic_ns(),
            sampling_start_wall_unix_ns=time.time_ns(),
            patcher=None,
        )
        self.assertIsNone(prof)
        self.assertEqual(trace.events, [])
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(sdp._PATCH_ORIGINALS, {})

    def test_off_path_does_not_import_or_patch_comfy_class(self):
        calls = []

        def _boom():
            calls.append(1)
            raise AssertionError("must not be called on the off path")

        with patch.object(sdp, "_resolve_ksampler_x0_inpaint", _boom), \
             patch.object(sdp, "_resolve_cuda_module", _boom):
            prof = sdp.begin_sampling_profile(
                _FakeTrace(), level="off", steps=8,
                sampling_start_monotonic_ns=time.monotonic_ns(),
                sampling_start_wall_unix_ns=time.time_ns(),
            )
        self.assertIsNone(prof)
        self.assertEqual(calls, [])


# ---------------------------------------------------------------------------
# Level A classification + reconciliation helpers
# ---------------------------------------------------------------------------


def _run_standard_sampling(profile, steps=8, ksampler_cls=None):
    """Simulate the pinned RK cadence: 2 evals per step, callback after each
    step, then 1 final teardown eval + final callback index == steps."""
    assert profile is not None, "profile must not be None"
    cls = ksampler_cls or sdp._resolve_ksampler_x0_inpaint()
    assert cls is not None, "ksampler class must resolve"
    k = cls()
    for s in range(steps):
        k(1, 0.5)
        k(1, 0.3)
        profile.on_callback_index(s)
    k(1, 0.01)
    profile.on_callback_index(steps)
    return k


def _begin(trace, level="steps", steps=8, patcher=None, start_mono=None):
    prof = sdp.begin_sampling_profile(
        trace,
        level=level,
        node_id="1242",
        node_class="ClownsharKSampler_Beta",
        steps=steps,
        sampling_start_monotonic_ns=start_mono or time.monotonic_ns(),
        sampling_start_wall_unix_ns=time.time_ns(),
        patcher=patcher,
    )
    assert prof is not None, "profile should begin for a non-off level"
    return prof


def _finalize(profile, trace, end_mono=None):
    return sdp.finalize_sampling_profile(
        profile, trace,
        sampling_end_monotonic_ns=end_mono or time.monotonic_ns(),
        sampling_end_wall_unix_ns=time.time_ns(),
    )


class LevelAClassificationTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        _FakeCuda.sync_count = 0
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_17_evals_classified_into_8_steps_and_final(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        self.assertIsNotNone(prof)
        _run_standard_sampling(prof)
        art = _finalize(prof, trace)
        self.assertEqual(art["status"], "ok")
        self.assertEqual(art["evals"]["count"], 17)
        self.assertEqual(art["evals"]["expected"], 17)
        self.assertEqual(art["callbacks"]["observed_indices"], list(range(9)))
        self.assertEqual(len(art["reconciliation"]["steps_ms"]), 8)
        # final teardown eval distinct from the 8 steps
        self.assertIsNotNone(art["reconciliation"]["teardown_final_eval_ms"])
        self.assertIsNotNone(art["reconciliation"]["teardown_ms"])
        self.assertEqual(art["evals"]["per_eval"][0]["phase"], "sampling_step")
        self.assertTrue(art["evals"]["per_eval"][0]["is_first_eval"])
        self.assertEqual(art["evals"]["per_eval"][-1]["phase"], "teardown")
        self.assertTrue(art["evals"]["per_eval"][-1]["is_final_post_loop_eval"])
        self.assertTrue(art["sampler_invocation"]["final_post_loop_eval_distinct"])
        self.assertIn("solver_controller_gaps_ms", art["reconciliation"]["steps_ms"][0])
        self.assertFalse(art["instrumentation_overhead"]["synchronization_inside_sampling"])
        self.assertTrue(art["cleanup_complete"])

    def test_reconciliation_residuals_exact(self):
        trace = _FakeTrace()
        start = time.monotonic_ns()
        prof = _begin(trace, level="steps", steps=8, patcher=None, start_mono=start)
        _run_standard_sampling(prof)
        end = time.monotonic_ns()
        art = _finalize(prof, trace, end_mono=end)
        rec = art["reconciliation"]
        self.assertEqual(rec["residual_status"], "ok")
        self.assertEqual(rec["sampling_residual_ms"], 0.0)
        self.assertEqual(rec["teardown_residual_ms"], 0.0)
        self.assertTrue(all(e["residual_ms"] == 0.0 for e in rec["steps_ms"]))
        # authoritative window comes from the passed event timestamps
        self.assertEqual(art["authoritative_sampling_window_ms"],
                         round((end - start) / 1_000_000, 3))

    def test_missing_evals_reported_as_error(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        k = _FakeKSamplerX0Inpaint()
        for s in range(3):
            k(1, 0.5)
            k(1, 0.3)
            prof.on_callback_index(s)
        art = _finalize(prof, trace)
        self.assertEqual(art["status"], "incomplete")
        self.assertTrue(any("eval_count_mismatch" in e for e in art["errors"]))

    def test_missing_callbacks_warning_with_eval_index_fallback(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        k = _FakeKSamplerX0Inpaint()
        for _ in range(16):
            k(1, 0.4)
        k(1, 0.01)
        art = _finalize(prof, trace)
        self.assertTrue(any("callbacks_absent" in w for w in art["warnings"]))
        self.assertEqual(art["evals"]["count"], 17)
        self.assertEqual(art["status"], "ok")

    def test_excessive_eval_and_callback_records_remain_bounded(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        k = _FakeKSamplerX0Inpaint()
        for index in range(sdp._MAX_EVAL_RECORDS + 32):
            k(1, 0.4)
            prof.on_callback_index(index)
        art = _finalize(prof, trace)
        self.assertLessEqual(art["evals"]["stored_count"], sdp._MAX_EVAL_RECORDS)
        self.assertGreater(art["evals"]["overflow_count"], 0)
        self.assertLessEqual(art["callbacks"]["stored_count"], sdp._MAX_CALLBACK_RECORDS)
        self.assertGreater(art["callbacks"]["overflow_count"], 0)
        self.assertEqual(art["status"], "incomplete")

    def test_extra_callback_index_reported(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        _run_standard_sampling(prof)
        prof.on_callback_index(9)  # extra callback
        art = _finalize(prof, trace)
        self.assertTrue(any("callback_indices_mismatch" in e for e in art["errors"]))
        self.assertEqual(art["status"], "incomplete")


class ComputeSkipAndCacheDiTTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    def _run_blocks(self, cachedit_counters):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: cachedit_counters):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)
            for s in range(8):
                k(1, 0.5)
                k(1, 0.3)
                prof.on_callback_index(s)
            k(1, 0.01)
            prof.on_callback_index(8)
            art = _finalize(prof, trace)
        return art, dm

    def test_compute_vs_skip_10_7_and_cachedit_crosscheck_ok(self):
        counters = {
            "discoverable": True, "attached": True, "enabled": True,
            "call_count": 17, "compute_count": 10, "skip_count": 7,
        }
        art, _ = self._run_blocks(counters)
        self.assertEqual(art["evals"]["count"], 17)
        self.assertEqual(art["compute_or_skip"], {"compute": 10, "skip": 7, "unknown": 0})
        self.assertFalse(any("cachedit" in e for e in art["errors"]), art["errors"])
        self.assertEqual(art["status"], "ok")

    def test_cachedit_counter_mismatch_reports_error_not_exception(self):
        counters = {
            "discoverable": True, "attached": True,
            "call_count": 17, "compute_count": 9, "skip_count": 8,
        }
        art, _ = self._run_blocks(counters)
        self.assertTrue(any("cachedit_counter_mismatch" in e for e in art["errors"]))
        self.assertEqual(art["status"], "incomplete")

    def test_cachedit_counters_unavailable_warning(self):
        art, _ = self._run_blocks({"discoverable": False})
        self.assertTrue(any("cachedit_counters_unavailable" in w for w in art["warnings"]))

    def test_hook_derived_counts_mismatch_reported(self):
        counters = {
            "discoverable": True, "attached": True,
            "call_count": 17, "compute_count": 8, "skip_count": 9,
        }
        art, _ = self._run_blocks(counters)
        self.assertTrue(
            any("cachedit_counter_mismatch" in e or "cachedit_hook_mismatch" in e for e in art["errors"]),
            art["errors"],
        )


class ProcessResidencyTelemetryTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        _FakeCuda.sync_count = 0
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    @staticmethod
    def _snapshot(value):
        return {
            "rss_bytes": value,
            "minor_page_faults": value + 10,
            "major_page_faults": value + 1,
            "source": {"rss": "fake_statm", "page_faults": "fake_rusage"},
            "availability": {
                "rss_bytes": True,
                "minor_page_faults": True,
                "major_page_faults": True,
            },
        }

    def test_first_compute_is_actual_forward_not_eval_zero_and_no_sync(self):
        """A skipped first eval must not receive the first-compute snapshot."""
        dm = _FakeNextDiT(n_layers=2)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        snapshots = iter((self._snapshot(100), self._snapshot(120), self._snapshot(140)))

        class _SkipThenComputeSampler:
            def __init__(self, inner_model=None):
                self.inner_model = inner_model
                self.calls = 0

            def __call__(self, x, sigma):
                self.calls += 1
                dm.skip = self.calls == 1
                return dm(x, sigma)

        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_process_residency_snapshot", lambda: next(snapshots)), \
             patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _SkipThenComputeSampler):
            prof = _begin(trace, level="steps", steps=8, patcher=patcher)
            k = _SkipThenComputeSampler(inner_model=dm)
            k(1, 0.5)  # eval 0: CacheDiT-style whole-forward skip
            k(1, 0.4)  # eval 1: first actual inner-block compute
            k(1, 0.3)  # eval 2: later compute
            art = _finalize(prof, trace)

        residency = art["process_residency"]
        self.assertEqual(residency["entry"]["snapshot"]["rss_bytes"], 100)
        self.assertEqual(residency["first_compute"]["eval_index"], 1)
        self.assertEqual(residency["first_compute"]["snapshot"]["rss_bytes"], 120)
        self.assertEqual(len(residency["later_compute"]), 1)
        self.assertEqual(residency["later_compute"][0]["eval_index"], 2)
        self.assertEqual(residency["later_compute"][0]["delta_from_entry"]["rss_bytes"], 40)
        self.assertEqual(art["compute_or_skip"], {"compute": 2, "skip": 1, "unknown": 0})
        self.assertEqual(_FakeCuda.sync_count, 0)
        json.loads(json.dumps(art))

    def test_process_compute_records_are_bounded_and_overflow_is_explicit(self):
        trace = _FakeTrace()
        snapshots = iter(self._snapshot(i) for i in range(sdp._MAX_PROCESS_COMPUTE_RECORDS + 1))
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_process_residency_snapshot", lambda: next(snapshots)):
            prof = _begin(trace, level="steps", steps=1, patcher=None)
            for index in range(sdp._MAX_PROCESS_COMPUTE_RECORDS + 5):
                prof._record_process_compute_snapshot({
                    "index": index,
                    "process_compute_recorded": False,
                })
            art = _finalize(prof, trace)

        records = art["process_residency"]["compute_records"]
        self.assertEqual(records["stored_count"], sdp._MAX_PROCESS_COMPUTE_RECORDS)
        self.assertEqual(records["observed_count"], sdp._MAX_PROCESS_COMPUTE_RECORDS + 5)
        self.assertEqual(records["overflow_count"], 5)
        self.assertEqual(len(art["process_residency"]["later_compute"]), sdp._MAX_PROCESS_COMPUTE_RECORDS - 1)
        json.loads(json.dumps(art))

    def test_host_cpu_thread_and_wall_evidence_is_serialized(self):
        trace = _FakeTrace()
        snapshots = iter((
            {
                **self._snapshot(100),
                "process_cpu_time_ns": 1_000,
                "thread_cpu_time_ns": 700,
                "wall_monotonic_ns": 10_000,
                "wall_unix_ns": 20_000,
            },
            {
                **self._snapshot(120),
                "process_cpu_time_ns": 1_250,
                "thread_cpu_time_ns": 850,
                "wall_monotonic_ns": 13_000,
                "wall_unix_ns": 23_000,
            },
        ))
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_process_residency_snapshot", lambda: next(snapshots)):
            prof = _begin(trace, level="steps", steps=1, patcher=None)
            art = _finalize(prof, trace)
        host = art["host_cpu_wall"]
        self.assertEqual(host["delta"]["process_cpu_time_ns"], 250)
        self.assertEqual(host["delta"]["thread_cpu_time_ns"], 150)
        self.assertEqual(host["delta"]["wall_monotonic_ns"], 3_000)
        self.assertEqual(art["process_residency"]["sampling_end"]["boundary"],
                         "after_sampling_end_before_cuda_realization")
        json.loads(json.dumps(art))

    def test_host_evidence_is_unavailable_without_numeric_delta(self):
        trace = _FakeTrace()
        unavailable = sdp._unavailable_process_residency_snapshot()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_process_residency_snapshot", return_value=unavailable):
            prof = _begin(trace, level="steps", steps=1, patcher=None)
            art = _finalize(prof, trace)
        host = art["host_cpu_wall"]
        self.assertEqual(host["status"], "unavailable")
        self.assertEqual(host["available_fields"], [])
        self.assertEqual(host["scope"], "deep_profile_entry_to_after_sampling_end")
        self.assertEqual(
            host["limits"],
            [
                "process_cpu_time_ns", "thread_cpu_time_ns", "rss_bytes",
                "minor_page_faults", "major_page_faults",
            ],
        )


class CacheDiTDiscoveryTests(unittest.TestCase):
    """P0-1: already-loaded ComfyUI-CacheDiT module wins over a fresh import."""

    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self.addCleanup(self._restore_modules)
        self._removed = []

    def _restore_modules(self):
        for name, mod in self._removed:
            if mod is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = mod

    def _pop_real_cachedit(self):
        real = sys.modules.pop("ComfyUI-CacheDiT.nodes", None)
        self._removed.append(("ComfyUI-CacheDiT.nodes", real))

    @staticmethod
    def _make_fake_module(name, counters, file_path):
        mod = types.ModuleType(name)
        mod.__file__ = file_path
        setattr(mod, "_lightweight_cache_state", {
            "enabled": True,
            "call_count": counters[0],
            "compute_count": counters[1],
            "skip_count": counters[2],
        })
        return mod

    def test_loaded_module_wins_and_no_fresh_import(self):
        """A module already in sys.modules with the ComfyUI-CacheDiT path
        component is used; a competing fresh import must NOT happen."""
        self._pop_real_cachedit()
        loaded = self._make_fake_module(
            "fake_cachedit_loaded", (17, 10, 7), "/vol/ComfyUI-CacheDiT/nodes.py"
        )
        sys.modules["fake_cachedit_loaded"] = loaded
        fresh_calls = []

        def _competing(name):
            fresh_calls.append(name)
            return self._make_fake_module("fake_cachedit_fresh", (1, 0, 1), "/vol/other/nodes.py")

        with patch.object(importlib, "import_module", _competing):
            out = sdp._read_cachedit_counters(None, None)
        assert out is not None
        self.assertEqual(out["module_source"], "loaded")
        self.assertEqual(out["call_count"], 17)
        self.assertEqual(out["compute_count"], 10)
        self.assertEqual(out["skip_count"], 7)
        self.assertEqual(fresh_calls, [], "fresh import must not be attempted when a loaded module exists")


    def test_loaded_module_with_windows_style_path_wins(self):
        self._pop_real_cachedit()
        loaded = self._make_fake_module(
            "fake_cachedit_win", (17, 10, 7), "C:\\custom_nodes\\ComfyUI-CacheDiT\\nodes.py"
        )
        sys.modules["fake_cachedit_win"] = loaded

        def _competing(name):
            return self._make_fake_module("fake_cachedit_fresh", (1, 0, 1), "/vol/other/nodes.py")

        with patch.object(importlib, "import_module", _competing):
            out = sdp._read_cachedit_counters(None, None)
        assert out is not None
        self.assertEqual(out["module_source"], "loaded")
        self.assertEqual(out["call_count"], 17)

    def test_fresh_import_fallback_when_not_loaded(self):
        """No loaded module -> safe fresh import fallback."""
        self._pop_real_cachedit()

        def _fresh(name):
            self.assertEqual(name, "ComfyUI-CacheDiT.nodes")
            return self._make_fake_module("fake_cachedit_fresh", (17, 10, 7), "/vol/ComfyUI-CacheDiT/nodes.py")

        with patch.object(importlib, "import_module", _fresh):
            out = sdp._read_cachedit_counters(None, None)
        assert out is not None
        self.assertEqual(out["module_source"], "fresh_import")
        self.assertEqual(out["call_count"], 17)

    def test_loaded_state_17107_serializes_through_artifact(self):
        """The loaded-module 17/10/7 state survives artifact serialization."""
        self._pop_real_cachedit()
        loaded = self._make_fake_module(
            "fake_cachedit_ser", (17, 10, 7), "/vol/ComfyUI-CacheDiT/nodes.py"
        )
        sys.modules["fake_cachedit_ser"] = loaded
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint), \
             patch.object(sdp, "_resolve_cuda_module", lambda: None):
            prof = _begin(trace, level="steps", steps=8, patcher=None)
            _run_standard_sampling(prof)
            art = _finalize(prof, trace)
        self.assertEqual(art["cachedit"]["module_source"], "loaded")
        payload = json.loads(json.dumps(art))
        self.assertEqual(payload["cachedit"]["call_count"], 17)
        self.assertEqual(payload["cachedit"]["compute_count"], 10)
        self.assertEqual(payload["cachedit"]["skip_count"], 7)
        self.assertFalse(any("cachedit_counter_mismatch" in e for e in art["errors"]), art["errors"])


class BackendObservationTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_attention_override_closure_identifies_pytorch_fallback(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="blocks", steps=8, patcher=None)

        def attention_pytorch(*args, **kwargs):
            return None

        def attention_fallback(*args, **kwargs):
            return attention_pytorch(*args, **kwargs)

        options = {"optimized_attention_override": attention_fallback}
        prof._begin_eval()
        hook = sdp._make_pre_hook(prof, "block:0:attention", "attention")
        hook(object(), (SimpleNamespace(shape=(1, 2, 3), dtype="bf16", device="cuda:0"),), {
            "transformer_options": options,
        })
        self.assertEqual(prof.evals[-1]["backend"]["dispatch"]["pytorch_override"], 1)
        self.assertTrue(any("attention_fallback" in item for item in prof._backend_signatures["pytorch_override"][0]))
        prof._end_eval()

    def test_backend_observation_is_metadata_only_and_bounded(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="blocks", steps=8, patcher=None)
        prof._begin_eval()
        hook = sdp._make_pre_hook(prof, "block:0:attention", "attention")
        hook(object(), (SimpleNamespace(shape=(1, 2), dtype="bf16", device="cuda:0"),), {})
        self.assertEqual(prof._backend_observations[0]["input"]["shape"], [1, 2])
        self.assertEqual(prof._backend_observations[0]["input"]["device"], "cuda:0")
        prof._end_eval()

    def test_broken_callable_metadata_cannot_escape_attention_hook(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="blocks", steps=8, patcher=None)
        prof._begin_eval()
        hook = sdp._make_pre_hook(prof, "block:0:attention", "attention")

        # The hook must still record its span and return normally even when a
        # selected callable refuses all diagnostic metadata access.
        hook(object(), (), {"transformer_options": {
            "optimized_attention_override": _CallableWithBrokenMetadata(),
        }})
        prof._span_end("block:0:attention", "attention")
        self.assertEqual(
            prof.evals[-1]["backend"]["dispatch"],
            {"unknown_attention_dispatch": 1},
        )
        self.assertTrue(
            any(item.startswith("attention_callable_metadata_failed:") for item in prof.warnings)
        )
        prof._end_eval()

    def test_sdpa_seam_is_counted_per_eval_and_restored(self):
        fake_ops = types.ModuleType("comfy.ops")
        import comfy

        def original_sdpa(*args, **kwargs):
            return "original"

        setattr(fake_ops, "scaled_dot_product_attention", original_sdpa)
        with patch.dict(sys.modules, {"comfy.ops": fake_ops}), \
             patch.object(comfy, "ops", fake_ops), \
             patch.object(sdp, "_resolve_cuda_module", lambda: None):
            trace = _FakeTrace()
            prof = _begin(trace, level="blocks", steps=8, patcher=None)

            def attention_sage(*args, **kwargs):
                return None

            prof._begin_eval()
            hook = sdp._make_pre_hook(prof, "block:0:attention", "attention")
            hook(object(), (), {"transformer_options": {
                "optimized_attention_override": attention_sage,
            }})
            self.assertEqual(fake_ops.scaled_dot_product_attention(), "original")
            prof._span_end("block:0:attention", "attention")
            prof._end_eval()
            art = _finalize(prof, trace)

        per_eval = art["evals"]["per_eval"][0]["attention_backend"]
        self.assertEqual(per_eval["calls"], {"pytorch_sdpa": 1})
        self.assertIsNone(art["attention_backend"]["correlated_fallback_evals"])
        self.assertEqual(art["attention_backend"]["observed_sage_sdpa_evals"], 1)
        self.assertEqual(
            art["attention_backend"]["actual_backend"],
            "sage_override_and_pytorch_sdpa_observed_non_correlated",
        )
        self.assertIn("not correlated per call", art["semantics"]["attention_backend"])
        self.assertIs(fake_ops.scaled_dot_product_attention, original_sdpa)


class BlockAggregationTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_block_attention_mlp_norm_aggregation_and_residuals(self):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)
            for s in range(8):
                k(1, 0.5)
                k(1, 0.3)
                prof.on_callback_index(s)
            k(1, 0.01)
            prof.on_callback_index(8)
            art = _finalize(prof, trace)
        self.assertEqual(len(art["blocks"]), 4)
        for b in art["blocks"]:
            self.assertGreaterEqual(b["total_ms"], 0.0)
            self.assertGreaterEqual(b["attention_ms"], 0.0)
            self.assertGreaterEqual(b["mlp_ms"], 0.0)
            self.assertGreaterEqual(b["norm_ms"], 0.0)
            self.assertIsInstance(b["residual_ms"], (int, float))
        self.assertIn("attention", art["categories_ms"])
        self.assertIn("mlp", art["categories_ms"])
        self.assertIn("norm", art["categories_ms"])
        self.assertIn("refiner", art["categories_ms"])
        self.assertIn("embeddings", art["categories_ms"])
        self.assertIn("output", art["categories_ms"])
        # Only compute evals have block children; skip evals add none.
        self.assertFalse(any("forward_residual_negative" in e for e in art["errors"]), art["errors"])

    def test_steps_mode_compute_skip_and_minimal_hooks(self):
        """Steps mode drives the fake dm: 10 compute / 7 skip via the minimal
        block-total compute-marker hooks, with NO category sub-hooks and NO
        embeddings/output hooks."""
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="steps", steps=8, patcher=patcher)
            # dm forward + block-total compute markers (4 layers + 4 refiner
            # blocks); no category sub-hooks, no embeddings/output hooks.
            self.assertEqual(dm.pre_hook_count, 1)
            self.assertEqual(dm.layers[0].pre_hook_count, 1)
            self.assertEqual(dm.layers[0].attention.pre_hook_count, 0)
            self.assertEqual(dm.layers[0].attention_norm1.pre_hook_count, 0)
            self.assertEqual(dm.noise_refiner[0].pre_hook_count, 1)
            self.assertEqual(dm.x_embedder.pre_hook_count, 0)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)
            for s in range(8):
                k(1, 0.5)
                k(1, 0.3)
                prof.on_callback_index(s)
            k(1, 0.01)
            prof.on_callback_index(8)
            art = _finalize(prof, trace)
        self.assertEqual(art["level"], "steps")
        self.assertEqual(art["compute_or_skip"], {"compute": 10, "skip": 7, "unknown": 0})
        self.assertEqual(art["evals"]["count"], 17)
        self.assertEqual(art["blocks"], [])  # no per-block aggregation at steps level
        self.assertEqual(art["categories_ms"], {})  # no category sub-hooks at steps level

    def test_artifact_semantics_documented(self):
        """norm (measured) vs norm_gate_residual (derived) are clearly
        separated, and the step callback-partition convention is documented."""
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)
            for s in range(8):
                k(1, 0.5)
                k(1, 0.3)
                prof.on_callback_index(s)
            k(1, 0.01)
            prof.on_callback_index(8)
            art = _finalize(prof, trace)
        sem = art["semantics"]
        self.assertIn("norm_category", sem)
        self.assertIn("norm_gate_residual", sem)
        self.assertIn("step_callback_partition", sem)
        self.assertIn("cuda_realization", sem)
        self.assertIn("authoritative_wall", sem)
        self.assertIn("non_attention", sem)
        # Per-block entries separate measured norm from derived norm_gate_residual.
        self.assertTrue(art["blocks"], "blocks mode must produce per-block entries")
        for b in art["blocks"]:
            self.assertIn("norm_ms", b)
            self.assertIn("norm_gate_residual_ms", b)
            self.assertIn("attention_ms", b)
            self.assertIn("mlp_ms", b)
        self.assertIn("norm_gate_residual", art["categories_ms"])
        self.assertIn("attention_ms", art["nextdit"])
        self.assertIn("non_attention_ms", art["nextdit"])
        # Derived residual matches the per-block residual semantics.
        self.assertEqual(
            art["categories_ms"]["norm_gate_residual"],
            round(sum(b["norm_gate_residual_ms"] for b in art["blocks"]), 3),
        )


class CleanupAndRestoreTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)

    def test_finalize_restores_class_patch_hooks_and_owner(self):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            self.assertTrue(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
            self.assertEqual(dm.pre_hook_count, 1)
            self.assertGreater(dm.layers[0].pre_hook_count, 0)
            _run_standard_sampling(prof)
            _finalize(prof, trace)
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(sdp._PATCH_ORIGINALS, {})
        self.assertEqual(dm.pre_hook_count, 0)
        self.assertEqual(dm.post_hook_count, 0)
        self.assertEqual(dm.layers[0].pre_hook_count, 0)

    def test_partial_run_finalize_still_restores(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        k = _FakeKSamplerX0Inpaint()
        k(1, 0.5)  # only one eval before something goes wrong
        art = _finalize(prof, trace)
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(art["status"], "incomplete")

    def test_executor_exception_between_evals_records_partial_and_restores(self):
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        k = _FakeKSamplerX0Inpaint()
        for _ in range(2):
            k(1, 0.5)
        # simulate an exception mid-sampling; the wrapper finally still calls
        # finalize; here we just finalize the partially-recorded profile.
        art = _finalize(prof, trace)
        self.assertEqual(art["evals"]["count"], 2)
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)

    def test_concurrent_second_profile_rejected_sampling_unchanged(self):
        trace_a = _FakeTrace("a")
        trace_b = _FakeTrace("b")
        prof_a = _begin(trace_a, level="steps", steps=8, patcher=None)
        prof_b = _begin(trace_b, level="steps", steps=8, patcher=None)
        self.assertFalse(prof_a.rejected)
        self.assertTrue(prof_b.rejected)
        self.assertTrue(any("concurrency_rejected" in w for w in prof_b.warnings))
        # sampling behavior unchanged for the rejected profile: class still owned by A
        self.assertTrue(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        art_b = _finalize(prof_b, trace_b)
        self.assertEqual(art_b["status"], "rejected")
        # A still owns the patch and can finalize normally.
        k = _FakeKSamplerX0Inpaint()
        k(1, 0.5)
        art_a = _finalize(prof_a, trace_a)
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)

    def test_concurrent_second_profile_different_thread_rejected(self):
        results = {}
        barrier = threading.Barrier(2)

        def _thread_a():
            trace = _FakeTrace("ta")
            prof = _begin(trace, level="steps", steps=8, patcher=None)
            results["a"] = prof
            barrier.wait(timeout=5)

        t = threading.Thread(target=_thread_a)
        t.start()
        try:
            barrier.wait(timeout=5)
            prof_b = _begin(_FakeTrace("tb"), level="steps", steps=8, patcher=None)
            self.assertTrue(prof_b.rejected)
            self.assertTrue(any("concurrency_rejected" in w for w in prof_b.warnings))
            art_b = _finalize(prof_b, _FakeTrace("tb"))
            self.assertEqual(art_b["status"], "rejected")
        finally:
            t.join(timeout=5)
        prof_a = results.get("a")
        if prof_a is not None:
            _finalize(prof_a, _FakeTrace("ta"))
            self.assertIsNone(sdp._PATCH_OWNER)


# ---------------------------------------------------------------------------
# CUDA ordering (no sync before finalize)
# ---------------------------------------------------------------------------


    def test_mid_forward_exception_cleanup(self):
        """A forward raising mid-eval leaves unclosed spans; finalize still
        restores the class patch and every hook handle."""
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)

            def _boom(*a, **kw):
                raise RuntimeError("mid-forward")

            dm.layers[2]._impl = _boom
            with self.assertRaises(RuntimeError):
                for s in range(8):
                    k(1, 0.5)
                    k(1, 0.3)
                    prof.on_callback_index(s)
            art = _finalize(prof, trace)
        self.assertTrue(
            any(e.startswith("unclosed_spans_during_eval_") for e in art["errors"]),
            art["errors"],
        )
        self.assertEqual(art["status"], "incomplete")
        self.assertFalse(hasattr(_FakeKSamplerX0Inpaint, sdp._PATCH_MARKER))
        self.assertIsNone(sdp._PATCH_OWNER)
        self.assertEqual(dm.layers[0].pre_hook_count, 0)
        self.assertEqual(dm.pre_hook_count, 0)

    def test_json_serialization_roundtrip(self):
        """The artifact round-trips through json.dumps/loads (JSON scalars only)."""
        trace = _FakeTrace()
        prof = _begin(trace, level="steps", steps=8, patcher=None)
        _run_standard_sampling(prof)
        art = _finalize(prof, trace)
        payload = json.loads(json.dumps(art))
        self.assertEqual(payload["schema_version"], sdp.SCHEMA_VERSION)
        self.assertEqual(payload["evals"]["count"], 17)
        self.assertEqual(payload["callbacks"]["observed_indices"], list(range(9)))
        self.assertIsInstance(payload["authoritative_sampling_window_ms"], (int, float))


class CudaOrderingTests(unittest.TestCase):
    def setUp(self):
        sdp.reset_for_tests()
        self.addCleanup(sdp.reset_for_tests)
        self._p = patch.object(sdp, "_resolve_ksampler_x0_inpaint", lambda: _FakeKSamplerX0Inpaint)
        self._p.start()
        self.addCleanup(self._p.stop)
        _FakeCuda.sync_count = 0
        _FakeCuda.elapsed_total_ms = 0.0

    def test_no_cuda_sync_before_finalize(self):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCuda), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            k = _FakeKSamplerX0Inpaint(inner_model=dm)
            for s in range(8):
                k(1, 0.5)
                k(1, 0.3)
                prof.on_callback_index(s)
            k(1, 0.01)
            prof.on_callback_index(8)
            self.assertEqual(_FakeCuda.sync_count, 0, "no sync inside sampling window")
            art = _finalize(prof, trace)
        self.assertEqual(_FakeCuda.sync_count, 1, "exactly one post-boundary sync")
        self.assertTrue(art["clocks"]["cuda_events"])
        self.assertEqual(art["cuda_boundary"]["status"], "observed")
        self.assertEqual(
            art["cuda_boundary"]["stream_readiness"]["profile_start"]["status"],
            "unavailable",
        )
        self.assertTrue(art["cuda_boundary"]["start_recorded"])
        self.assertTrue(art["cuda_boundary"]["end_recorded"])
        self.assertEqual(art["cuda_boundary"]["realization"], "post_sampling_end_only")
        self.assertGreaterEqual(art["instrumentation_overhead"]["cuda_sync_ms"], 0.0)
        self.assertEqual(art["instrumentation_overhead"]["placement"], "post_sampling_end_cleanup")
        # ── P0-3: bounded CUDA timing results serialized in the artifact ──
        self.assertGreater(len(art["cuda_timings_ms"]), 0)
        self.assertIn("forward", art["cuda_timings_ms"])
        # per-eval forward GPU ms present (all evals have a forward span here).
        fwd_gpu = [e.get("forward_gpu_ms") for e in art["evals"]["per_eval"]]
        self.assertEqual(len([v for v in fwd_gpu if isinstance(v, (int, float))]), 17)
        # JSON roundtrip keeps scalars only.
        payload = json.loads(json.dumps(art))
        self.assertEqual(payload["evals"]["count"], 17)
        self.assertGreater(len(payload["cuda_timings_ms"]), 0)
        for v in payload["cuda_timings_ms"].values():
            self.assertIsInstance(v, (int, float))

    def test_stream_query_is_non_synchronizing_supporting_boundary_evidence(self):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        stream = _FakeStream((True, False), device="cuda:3")
        _FakeCudaWithStream.stream = stream
        _FakeCudaWithStream.current_stream_count = 0
        _FakeCudaWithStream.sync_count = 0
        with patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCudaWithStream), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            self.assertEqual(stream.query_count, 1)
            self.assertEqual(_FakeCudaWithStream.sync_count, 0)
            _run_standard_sampling(prof)
            self.assertEqual(stream.query_count, 1, "no query inside sampling window")
            art = _finalize(prof, trace)

        boundary = art["cuda_boundary"]
        self.assertEqual(stream.query_count, 2)
        self.assertEqual(_FakeCudaWithStream.sync_count, 1)
        self.assertEqual(boundary["status"], "observed")
        self.assertTrue(boundary["stream_readiness"]["query_observed"])
        self.assertEqual(
            boundary["stream_readiness"]["profile_start"]["status"], "ready"
        )
        self.assertEqual(
            boundary["stream_readiness"]["post_sampling_end"]["status"],
            "not_ready",
        )
        self.assertEqual(
            boundary["stream_readiness"]["profile_start"]["stream"]["device"],
            "cuda:3",
        )
        self.assertTrue(
            boundary["stream_readiness"]["profile_start"]["non_synchronizing"]
        )
        self.assertIn(
            "visible on that stream only",
            boundary["stream_readiness"]["semantics"],
        )
        self.assertIn("causal proof", boundary["semantics"])
        json.loads(json.dumps(art))

    def test_cuda_unavailable_warning_and_no_events(self):
        dm = _FakeNextDiT(n_layers=4)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: None), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            _run_standard_sampling(prof)
            art = _finalize(prof, trace)
        self.assertFalse(art["clocks"]["cuda_events"])
        self.assertTrue(any("cuda_events_unavailable" in w for w in art["warnings"]))

    def test_cuda_boundary_pair_is_cleared_when_realization_sync_fails(self):
        dm = _FakeNextDiT(n_layers=2)
        patcher = SimpleNamespace(model=SimpleNamespace(diffusion_model=dm))
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCuda), \
             patch.object(sdp, "_read_cachedit_counters", lambda d, p: {"discoverable": False}), \
             patch.object(_FakeCuda, "synchronize", side_effect=RuntimeError("sync")):
            prof = _begin(trace, level="blocks", steps=8, patcher=patcher)
            _run_standard_sampling(prof)
            art = _finalize(prof, trace)
        self.assertFalse(art["cuda_boundary"]["end_recorded"])
        self.assertIsNone(art["cuda_boundary"]["elapsed_ms"])
        self.assertTrue(any("cuda_realization_failed" in w for w in art["warnings"]))

    def test_steps_mode_never_enables_cuda(self):
        trace = _FakeTrace()
        with patch.object(sdp, "_resolve_cuda_module", lambda: _FakeCuda):
            prof = _begin(trace, level="steps", steps=8, patcher=None)
            self.assertIsNotNone(prof)
            self.assertIsNone(prof._cuda_module)
            _run_standard_sampling(prof)
            art = _finalize(prof, trace)
        self.assertFalse(art["clocks"]["cuda_events"])
        self.assertEqual(_FakeCuda.sync_count, 0)


class GoldenSamplingDecompositionTests(unittest.TestCase):
    def test_complete_stage_is_total_children_are_partial_and_residual_is_explicit(self):
        stage = SimpleNamespace(entry_monotonic_ns=100, end_monotonic_ns=900)
        out = golden._build_golden_sampling_decomposition(
            stage,
            sampling_start_event=SimpleNamespace(monotonic_ns=200),
            sampling_end_event=SimpleNamespace(monotonic_ns=700),
            sampling_start_ns=250,
            sampling_end_ns=650,
            ok=True,
        )
        self.assertEqual(out["total"]["scope"], "TOTAL")
        self.assertFalse(out["total"]["non_additive"])
        self.assertEqual(out["children"]["actual_sampler_invocation"]["scope"], "PARTIAL")
        self.assertTrue(out["children"]["actual_sampler_invocation"]["non_additive"])
        self.assertEqual(out["children"]["actual_sampler_invocation"]["start_monotonic_ns"], 250)
        self.assertEqual(out["residual"]["scope"], "RESIDUAL")
        self.assertEqual(out["residual"]["duration_ns"], 0)
        self.assertEqual(out["partition"]["status"], "verified")
        self.assertEqual(
            out["children"]["actual_sampler_invocation"]["semantics"],
            "actual_sampler_node_function_entry_to_return_or_await_completion",
        )
        self.assertIn("historical_complete_boundary_distinction", out["semantics"])
        json.loads(json.dumps(out))

    def test_invalid_or_overlapping_children_are_not_subtracted_as_verified(self):
        stage = SimpleNamespace(entry_monotonic_ns=100, end_monotonic_ns=900)
        out = golden._build_golden_sampling_decomposition(
            stage,
            sampling_start_ns=50,
            sampling_end_ns=950,
            ok=True,
        )
        actual = out["children"]["actual_sampler_invocation"]
        self.assertEqual(actual["status"], "overlap")
        self.assertEqual(actual["relative_to_total"], "overlaps_authoritative_total")
        self.assertFalse(actual["partition_verified"])
        self.assertEqual(out["residual"]["duration_ns"], 800)
        self.assertEqual(out["residual"]["status"], "observed")
        self.assertGreaterEqual(out["residual"]["duration_ns"], 0)

        invalid = golden._build_golden_sampling_decomposition(
            SimpleNamespace(entry_monotonic_ns=900, end_monotonic_ns=100),
            sampling_start_ns=200,
            sampling_end_ns=300,
            ok=False,
        )
        self.assertEqual(invalid["total"]["status"], "error")
        self.assertEqual(invalid["residual"]["status"], "error")
        self.assertIsNone(invalid["residual"]["duration_ns"])

    def test_unseparable_optional_sampler_work_is_explicitly_unavailable(self):
        stage = SimpleNamespace(entry_monotonic_ns=100, end_monotonic_ns=900)
        out = golden._build_golden_sampling_decomposition(
            stage,
            sampling_start_ns=200,
            sampling_end_ns=700,
            ok=True,
        )
        components = out["components"]
        self.assertEqual(components["feature_inj_latent"]["status"], "unavailable")
        self.assertEqual(components["res4lyf_sampler_work"]["status"], "unavailable")
        self.assertEqual(components["scheduler_sigma_preparation"]["status"], "unavailable")
        for name in ("feature_inj_latent", "res4lyf_sampler_work"):
            self.assertTrue(components[name]["unavailable_reason"])

    def test_decomposition_is_attached_to_closed_recorder_stage_and_event(self):
        monotonic_values = iter((100, 900))
        wall_values = iter((1_000, 9_000))
        recorder = golden.GoldenTelemetryRecorder(
            monotonic=lambda: next(monotonic_values, 900),
            wall=lambda: next(wall_values, 9_000),
        )
        recorder.begin_stage("golden_sampling")
        recorder.end_stage("golden_sampling", ready=True)
        golden._attach_golden_sampling_decomposition(
            recorder,
            sampling_start_ns=200,
            sampling_end_ns=700,
            ok=True,
        )
        details = recorder.intervals["golden_sampling"].details
        self.assertEqual(details["golden_sampling_decomposition"]["total"]["scope"], "TOTAL")
        self.assertTrue(any(
            event["name"] == "golden_sampling_decomposition"
            for event in recorder.events
        ))


class GoldenSerialRunnerSamplerBoundaryTests(unittest.TestCase):
    def test_async_sampler_boundary_includes_await_and_excludes_closure(self):
        class AsyncSampler:
            FUNCTION = "go"

            @classmethod
            def INPUT_TYPES(cls):
                return {"required": {}, "optional": {}}

            async def go(self):
                await asyncio.sleep(0.001)
                return ("sample",)

        runner = golden.GoldenSerialRunner(
            {"sampler": {"class_type": "AsyncSampler", "inputs": {}}},
            node_classes={"AsyncSampler": AsyncSampler},
        )
        runner.set_sampler_target("sampler", "AsyncSampler")
        runner.begin_scope({"sampling"})
        try:
            asyncio.run(runner.run_closure("sampler", include_target=True))
        finally:
            runner.end_scope()
        self.assertIsInstance(runner.sampler_call_start, int)
        self.assertIsInstance(runner.sampler_call_end, int)
        self.assertLessEqual(runner.sampler_call_start, runner.sampler_call_end)


if __name__ == "__main__":
    unittest.main()
