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
        # Per-block entries separate measured norm from derived norm_gate_residual.
        self.assertTrue(art["blocks"], "blocks mode must produce per-block entries")
        for b in art["blocks"]:
            self.assertIn("norm_ms", b)
            self.assertIn("norm_gate_residual_ms", b)
            self.assertIn("attention_ms", b)
            self.assertIn("mlp_ms", b)
        self.assertIn("norm_gate_residual", art["categories_ms"])
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


if __name__ == "__main__":
    unittest.main()
