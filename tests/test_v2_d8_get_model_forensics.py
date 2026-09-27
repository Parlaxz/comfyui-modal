"""Deterministic local tests for the V2 Batch D8 get_model forensics
instrumentation and accounting (tools/v2_d8_get_model_forensics.py).

Covers, without any Modal run and without touching production wiring:

1. The synthetic ZImage meta state dict detects as ``ZImage`` through the
   production ComfyUI detection path (``model_config_from_unet``) with the
   expected unet_config (dim=3840, n_layers=32).
2. The instrumented ``get_model`` span tree is DISJOINT: children walls are
   non-negative, never exceed the parent wall, and account for the parent
   within a bounded residual; the ``tree_disjoint_errors`` list stays empty.
3. Instrumentation is fully restored after the run: ``torch.nn.Module.__init__``
   and ``gc.callbacks`` are back to their original state (process-local patch,
   no production file edited).
4. Meta construction is storage-free: all parameters and buffers are meta,
   physical bytes = 0, logical bytes match the 6.5B-param ZImage shape.
5. The production forensics gate ``COMFYMODAL_V2_UNET_FORENSICS`` defaults to
   OFF when the environment variable is absent (read-only check).
6. The mirrored post-construction steps detect the poisoned meta
   ``model_sampling`` and rebuild it, leaving zero meta tensors.
7. The inventory counters match the ZImage construction shape
   (594 modules, 477 parameters) so regressions in the harness are caught.

Skips cleanly when ComfyUI/torch are unavailable.  No timing assertions are
made (Windows thread_time granularity makes them flaky); accounting is
structural only.
"""

from __future__ import annotations

import gc
import os
import sys
import unittest

_COMFY_ROOT = r"C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI"
if _COMFY_ROOT not in sys.path:
    sys.path.insert(0, _COMFY_ROOT)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_DIR = os.path.join(_REPO_ROOT, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import torch
    import comfy.model_detection  # noqa: F401
    import v2_d8_get_model_forensics as d8
    _HAS_D8 = True
except Exception as _exc:  # pragma: no cover
    _HAS_D8 = False
    _D8_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

try:
    import comfymodal_runtime.model_preload as mp
    _HAS_MP = True
except Exception:  # pragma: no cover
    _HAS_MP = False


def _build() -> tuple[dict, dict]:
    """(meta_sd, probe_cpu_tensor) — synthetic ZImage, allow_fp16 probe."""
    header = d8.synthetic_zimage_header()
    probe = torch.randn(3840, dtype=torch.float32) * 0.1  # std 0.1 < 0.42
    meta_sd = d8.header_to_meta_sd(header, probe_tensor=probe)
    return meta_sd, probe


@unittest.skipUnless(_HAS_D8, "d8 harness/comfy unavailable")
class TestSyntheticDetection(unittest.TestCase):
    """The synthetic sd follows the SAME detection path production uses."""

    def test_detects_as_zimage_with_expected_config(self):
        meta_sd, _probe = _build()
        config, diag = d8.derive_config(meta_sd)
        self.assertEqual(type(config).__name__, "ZImage")
        uc = config.unet_config
        self.assertEqual(uc.get("dim"), 3840)
        self.assertEqual(uc.get("n_layers"), 32)
        self.assertEqual(uc.get("image_model"), "lumina2")
        self.assertTrue(uc.get("z_image_modulation"))
        self.assertTrue(uc.get("allow_fp16"))
        self.assertEqual(str(diag.get("unet_dtype")), "torch.bfloat16")

    def test_meta_sd_is_all_meta_except_probe(self):
        meta_sd, probe = _build()
        meta_count = sum(1 for t in meta_sd.values() if getattr(t, "is_meta", False))
        self.assertEqual(meta_count, len(meta_sd) - 1)
        probe_key = "layers.30.ffn_norm1.weight"
        self.assertFalse(meta_sd[probe_key].is_meta)
        self.assertIs(meta_sd[probe_key], probe)


@unittest.skipUnless(_HAS_D8, "d8 harness/comfy unavailable")
class TestSpanAccounting(unittest.TestCase):
    """Disjoint accounting tree invariants (structural, no timing asserts)."""

    def setUp(self):
        meta_sd, _probe = _build()
        self.config, _diag = d8.derive_config(meta_sd)
        self.meta_sd = meta_sd

    def tearDown(self):
        del self.config
        del self.meta_sd
        gc.collect()

    def _run_once(self):
        r = d8.instrumented_get_model(self.config, self.meta_sd)
        self.addCleanup(lambda: r.pop("model", None))
        return r

    def test_tree_disjoint_and_accounted(self):
        r = self._run_once()
        self.assertEqual(r["tree_disjoint_errors"], [],
                         f"disjoint violations: {r['tree_disjoint_errors']}")
        tree = r["tree"]
        self.assertGreaterEqual(tree["wall_ms"], 0.0)
        children_sum = sum(c["wall_ms"] for c in tree.get("children", []))
        self.assertAlmostEqual(children_sum, r["children_wall_sum_ms"], places=1)
        # Children must account for a meaningful share, with residual >= 0.
        self.assertGreaterEqual(r["residual_wall_ms"], 0.0)
        self.assertGreaterEqual(tree["wall_ms"], children_sum)
        acct = r["accounted_percent"]
        self.assertIsNotNone(acct)
        self.assertGreater(acct, 0.0)
        self.assertLessEqual(acct, 100.0)

    def test_expected_top_level_spans_present(self):
        r = self._run_once()
        names = {c["name"] for c in r["tree"].get("children", [])}
        for expected in ("ops_selection", "diffusion_model_construct",
                         "archive_dtypes", "model_sampling_construct"):
            self.assertIn(expected, names,
                          f"missing span {expected}; got {names}")

    def test_module_attribution_nested_not_double_counted(self):
        r = self._run_once()
        ma = r["module_attribution"]
        self.assertEqual(ma["count"], 594)
        self.assertEqual(sum(v["count"] for v in ma["by_class"].values()), 594)
        self.assertLessEqual(ma["total_wall_ms"], r["tree"]["wall_ms"])

    def test_instrumentation_restored(self):
        orig_init = torch.nn.Module.__init__
        orig_callbacks = list(gc.callbacks)
        r = self._run_once()
        self.assertIs(torch.nn.Module.__init__, orig_init,
                      "torch.nn.Module.__init__ was not restored")
        self.assertEqual(list(gc.callbacks), orig_callbacks,
                         "gc.callbacks were not restored")
        self.assertEqual(r["tree_disjoint_errors"], [])


@unittest.skipUnless(_HAS_D8, "d8 harness/comfy unavailable")
class TestMetaStorageFree(unittest.TestCase):
    """Part 7 audit: construction is storage-free (no physical allocations)."""

    def test_all_params_and_buffers_meta_zero_physical_bytes(self):
        meta_sd, _probe = _build()
        config, _diag = d8.derive_config(meta_sd)
        r = d8.instrumented_get_model(config, meta_sd)
        self.addCleanup(lambda: r.pop("model", None))
        inv = d8.model_inventory(r["model"])
        self.assertTrue(inv["param_all_meta"])
        self.assertTrue(inv["buffer_all_meta"])
        self.assertEqual(inv["param_physical_bytes"], 0)
        self.assertEqual(inv["param_logical_bytes"], 13_053_109_376)
        self.assertEqual(inv["param_numel"], 6_526_554_688)
        # Construction shape regression guard.
        self.assertEqual(inv["modules"], 594)
        self.assertEqual(inv["parameters"], 477)
        self.assertEqual(inv["tensor_objects"], 478)


@unittest.skipUnless(_HAS_D8, "d8 harness/comfy unavailable")
class TestPostConstructionSteps(unittest.TestCase):
    """Mirrors production _fs_meta_construct post-steps."""

    def test_sampling_poisoned_then_rebuilt(self):
        meta_sd, _probe = _build()
        config, _diag = d8.derive_config(meta_sd)
        r = d8.instrumented_get_model(config, meta_sd)
        self.addCleanup(lambda: r.pop("model", None))
        post = d8.post_construction_steps(r["model"], config)
        self.assertGreaterEqual(post["sampling_poisoned"], 1)
        self.assertTrue(post["sampling_fixed"])
        self.assertGreaterEqual(post["sampling_fix_ms"], 0.0)
        self.assertEqual(d8.collect_meta_tensors(r["model"].model_sampling), [])


@unittest.skipUnless(_HAS_MP, "model_preload unavailable")
class TestProductionGateDefaultOff(unittest.TestCase):
    """Read-only check: production forensics gate stays OFF without env."""

    def test_forensics_gate_default_off(self):
        import unittest.mock as mock
        from comfymodal_runtime.unet_fastsafetensors import (
            _fs_forensics_enabled,
        )
        env = dict(os.environ)
        env.pop("COMFYMODAL_V2_UNET_FORENSICS", None)
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertFalse(_fs_forensics_enabled())
        # Explicitly ON produces True (documented behavior).
        env["COMFYMODAL_V2_UNET_FORENSICS"] = "1"
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertTrue(_fs_forensics_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
