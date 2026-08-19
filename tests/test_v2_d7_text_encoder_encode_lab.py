"""Deterministic local tests for the Batch D7 generic text-encoder encode lab
(tools/benchmark_text_encoder_encode.py).

The lab is a zero-spend LOCAL benchmark: it builds small deterministic
synthetic text encoders from ComfyUI's own generic classes and measures the
encode path across eight primary arms (P0A/P0B fp32, P1A/P1B fp32+TF32,
P2A/P2B TRUE bf16, P3A/P3B TRUE fp16 -- each with its own resident dtype) plus
the first-pass autocast-legacy arms P0..P4.  These tests cover:

  1. Pure ``DtypePolicy`` arm-planning across the capability matrix
     (13 arms: 8 new + 5 legacy; gates bf16/TF32 >= sm8.0, fp16 >= sm7.0).
  2. Below-threshold capabilities classify arms UNSUPPORTED without raising.
  3. Model-name independence: the arm planner never consults model names
     (behavioral + structural AST scan of the harness source).
  4. P0 fixture behavior against the real Comfy path: manual_cast_dtype is
     fp32, force_cast_weights True, resident dtype matches the production
     text-encoder dtype.
  5. BF16/FP16 fallback: unsupported devices classify arms UNSUPPORTED while
     P0A/P0B still run.
  6. TF32 application + restoration toggles exactly (no leaks).
  7. A full arm sweep restores every global torch setting (autocast off,
     allow_tf32, float32 matmul precision, cudnn.allow_tf32).
  8. CUDA-unavailable behavior: arms classify UNSUPPORTED and the harness
     completes without exception.
  9. ``Correctness`` metrics classify exact / near / far / nan / inf /
     shape-mismatch inputs correctly.
 10. Timing-boundary integrity: warmup encodes strictly precede the first
     timed repeat; timed repeat counts match; CUDA events bracket only encode
     calls.
 11. P4 preferred-dtype selection (bf16 > fp16 > fp32).
 12. Synthetic token structure validity for ClipTokenWeightEncoder.
 13. New-arm descriptors: 8 arm ids, resident dtypes, cast policies, and
     ``autocast_legacy`` labels; default ``--arms`` = the 8 new arms.
 14. Transformer-wrap capability check + exact wrap/restore identity; wrap
     actually coerces real encode Linear inputs to bf16/fp16 with fp32 output.
 15. Resident policy B: exact bitwise state_dict restoration after a
     P2B-style resident conversion; one-time conversion measured outside the
     timed region and only for resident-changing arms.
 16. Hard validity gate: skipped wrap classifies ARM_INVALID_NOT_LOW_PRECISION;
     applied wrap is VALID on bf16-capable devices.
 17. Cast accounting split: materialized-vs-short-circuit counts on a tiny
     synthetic model.

GPU/comfy-dependent tests skip cleanly; everything else runs CPU-only.
"""

from __future__ import annotations

import ast
import inspect
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOLS_DIR = os.path.join(_REPO_ROOT, "tools")
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_COMFY_ROOT = str(Path(__file__).resolve().parents[3])
if _COMFY_ROOT not in sys.path:
    sys.path.insert(0, _COMFY_ROOT)

# The lab + comfy are imported lazily: pure-logic tests need neither.
import benchmark_text_encoder_encode as lab  # noqa: E402

# comfy.cli_args parses sys.argv at import time; run_tests.py passes a module
# name as argv[1], which comfy's parser would reject.  Wipe it before the
# guarded comfy import below.
_SYS_ARGV_BACKUP = list(sys.argv)
sys.argv = [sys.argv[0]]

try:
    import comfy.model_management  # noqa: F401

    _HAS_COMFY = True
    _COMFY_IMPORT_ERROR = None
except Exception as _exc:  # pragma: no cover
    _HAS_COMFY = False
    _COMFY_IMPORT_ERROR = f"{type(_exc).__name__}: {_exc}"

sys.argv = _SYS_ARGV_BACKUP

# Forbidden model-name tokens for the structural independence check (test 3b).
FORBIDDEN_MODEL_TOKENS = ("qwen", "zimage", "z_image", "flux", "t5")


def _status(plan, arm_id):
    return lab.DtypePolicy.status_for(plan, arm_id)["status"]


class TestArmPlanSelection(unittest.TestCase):
    def test_plan_matrix(self) -> None:
        cuda80 = lab.DtypePolicy.plan_arms("cuda", (8, 0), True, True)
        cuda70 = lab.DtypePolicy.plan_arms("cuda", (7, 0), True, True)
        cuda60 = lab.DtypePolicy.plan_arms("cuda", (6, 0), True, True)
        cpu = lab.DtypePolicy.plan_arms("cpu", None, False, False)

        # Legacy arms keep their first-pass matrix.
        self.assertEqual(
            [_status(cuda80, a) for a in ("P0", "P1", "P2", "P3", "P4")],
            ["OK", "OK", "OK", "OK", "OK"],
        )
        # cap (7,0): TF32 and BF16 need >= (8,0), FP16 needs >= (7,0).
        self.assertEqual(
            [_status(cuda70, a) for a in ("P0", "P1", "P2", "P3", "P4")],
            ["OK", "UNSUPPORTED", "UNSUPPORTED", "OK", "OK"],
        )
        # cap (6,0): everything compute-reduced unsupported, P0 + P4 (fp32) OK.
        self.assertEqual(
            [_status(cuda60, a) for a in ("P0", "P1", "P2", "P3", "P4")],
            ["OK", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "OK"],
        )
        # No CUDA: P0 only.
        self.assertEqual(
            [_status(cpu, a) for a in ("P0", "P1", "P2", "P3", "P4")],
            ["OK", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
        )

        # New arms: P0* always OK; TF32/bf16 need >= (8,0); fp16 needs >= (7,0).
        self.assertEqual(
            [_status(cuda80, a) for a in lab.NEW_ARM_IDS], ["OK"] * 8
        )
        self.assertEqual(
            [_status(cuda70, a) for a in lab.NEW_ARM_IDS],
            ["OK", "OK", "UNSUPPORTED", "UNSUPPORTED",
             "UNSUPPORTED", "UNSUPPORTED", "OK", "OK"],
        )
        self.assertEqual(
            [_status(cuda60, a) for a in lab.NEW_ARM_IDS],
            ["OK", "OK", "UNSUPPORTED", "UNSUPPORTED",
             "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
        )
        self.assertEqual(
            [_status(cpu, a) for a in lab.NEW_ARM_IDS],
            ["OK", "OK", "UNSUPPORTED", "UNSUPPORTED",
             "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED", "UNSUPPORTED"],
        )
        # Ordered NEW + LEGACY, every entry carries a reason + descriptors.
        self.assertEqual([e["arm"] for e in cuda80], list(lab.ARM_IDS))
        for entry in cuda80:
            self.assertIn("reason", entry)
            self.assertIn("compute_dtype", entry)
            self.assertIn("resident_dtype", entry)
            self.assertIn("mechanism", entry)
            self.assertIn("cast_policy", entry)
            self.assertIn("tf32", entry)

    def test_support_flags_respected(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cuda", (8, 0), False, True)
        for arm_id in ("P2", "P2A", "P2B"):
            self.assertEqual(_status(plan, arm_id), "UNSUPPORTED")
        for arm_id in ("P3", "P3A", "P3B"):
            self.assertEqual(_status(plan, arm_id), "OK")
        plan = lab.DtypePolicy.plan_arms("cuda", (8, 0), True, False)
        for arm_id in ("P3", "P3A", "P3B"):
            self.assertEqual(_status(plan, arm_id), "UNSUPPORTED")
        for arm_id in ("P2", "P2A", "P2B"):
            self.assertEqual(_status(plan, arm_id), "OK")


class TestNewArmPlanDescriptors(unittest.TestCase):
    def test_eight_new_arms_and_default(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        ids = [e["arm"] for e in plan]
        for arm_id in lab.NEW_ARM_IDS:
            self.assertIn(arm_id, ids)
        self.assertEqual(len(list(lab.NEW_ARM_IDS)), 8)
        self.assertEqual(list(lab.DEFAULT_ARMS), list(lab.NEW_ARM_IDS))

    def test_descriptors_per_arm(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        p0a = lab.DtypePolicy.status_for(plan, "P0A")
        self.assertEqual((p0a["compute_dtype"], p0a["resident_dtype"]), ("fp32", "fp16"))
        self.assertEqual(p0a["cast_policy"], "cast_every_forward")
        self.assertEqual(p0a["mechanism"], "cast_every_forward")
        p0b = lab.DtypePolicy.status_for(plan, "P0B")
        self.assertEqual((p0b["compute_dtype"], p0b["resident_dtype"]), ("fp32", "fp32"))
        self.assertEqual(p0b["cast_policy"], "resident")
        p1b = lab.DtypePolicy.status_for(plan, "P1B")
        self.assertTrue(p1b["tf32"])
        p2b = lab.DtypePolicy.status_for(plan, "P2B")
        self.assertEqual((p2b["compute_dtype"], p2b["resident_dtype"]), ("bf16", "bf16"))
        self.assertEqual(p2b["mechanism"], "no_cast")
        p3a = lab.DtypePolicy.status_for(plan, "P3A")
        self.assertEqual((p3a["compute_dtype"], p3a["resident_dtype"]), ("fp16", "fp32"))
        legacy = lab.DtypePolicy.status_for(plan, "P2")
        self.assertEqual(legacy["mechanism"], "autocast_legacy")


class TestCapabilityRejection(unittest.TestCase):
    def test_below_threshold_unsupported_no_raise(self) -> None:
        for capability, bf16, fp16 in (
            ((6, 0), True, True),
            ((5, 2), True, True),
            ((7, 0), True, True),
            ((3, 0), False, False),
        ):
            plan = lab.DtypePolicy.plan_arms("cuda", capability, bf16, fp16)
            self.assertEqual(len(plan), 13)  # 8 new + 5 legacy

        plan = lab.DtypePolicy.plan_arms("cuda", (5, 0), True, True)
        for arm_id in ("P1", "P2", "P3", "P1A", "P1B", "P2A", "P2B", "P3A", "P3B"):
            self.assertEqual(_status(plan, arm_id), "UNSUPPORTED")
        for arm_id in ("P0", "P0A", "P0B", "P4"):
            self.assertEqual(_status(plan, arm_id), "OK")
        # P4 still OK (falls back to fp32 compute) — never raises.
        self.assertEqual(lab.DtypePolicy.status_for(plan, "P4")["compute_dtype"], "fp32")


class TestModelNameIndependence(unittest.TestCase):
    def _string_constants(self, node):
        found = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                found.append(sub.value)
        return found

    def test_plan_has_no_model_name_parameter(self) -> None:
        signature = inspect.signature(lab.DtypePolicy.plan_arms)
        for param in signature.parameters:
            self.assertNotIn(param, ("model", "name", "fixture", "class"))

    def test_plan_is_pure_and_repeatable(self) -> None:
        a = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        b = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        self.assertEqual(a, b)

    def test_no_model_name_constants_in_core_code(self) -> None:
        source = Path(lab.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)

        scanned = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in (
                "DtypePolicy",
                "GlobalTorchSettings",
            ):
                scanned.append(node)
            elif isinstance(node, ast.FunctionDef) and node.name in (
                "_plan_entry_for",
                "_autocast_spec",
                "run_arm",
                "run_matrix",
                "_compare_outputs",
                "_stability",
                "_verification_pass",
                "_deep_profile",
                "_op_bucket",
                "_call_encode",
                "_dtype_from_name",
                "_policy_dtype_for",
                "_forward_accepts_dtype_or_embeds",
                "_wrap_transformers",
                "_snapshot_model_state",
                "_restore_model_state",
                "_set_manual_cast_dtype",
                "_restore_manual_cast_dtype",
            ):
                scanned.append(node)

        violations = []
        for node in scanned:
            label = getattr(node, "name", type(node).__name__)
            for constant in self._string_constants(node):
                lowered = constant.lower()
                for token in FORBIDDEN_MODEL_TOKENS:
                    if token in lowered:
                        violations.append((label, constant))

        self.assertEqual(violations, [], "core arm code must not mention model names")


class TestP0ExactBehavior(unittest.TestCase):
    @unittest.skipUnless(_HAS_COMFY, f"comfy unavailable: {_COMFY_IMPORT_ERROR}")
    def test_p0_fixture_production_settings(self) -> None:
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)
        self.assertEqual(fixture.patcher.object_patches["manual_cast_dtype"], torch.float32)
        self.assertTrue(fixture.patcher.force_cast_weights)
        if torch.cuda.is_available():
            import comfy.model_management as mm

            self.assertEqual(
                fixture.resident_dtype,
                mm.text_encoder_dtype(mm.get_torch_device()),
            )
            self.assertEqual(
                fixture.identity["params_off_device"], [],
                "all parameters must be resident on the load device",
            )
        # Encode runs and returns a (cond, pooled) pair.
        cond, pooled = fixture.encode_fn(fixture.encode_tokens)
        self.assertEqual(cond.shape[0], 1)
        self.assertEqual(cond.shape[1], 77)
        self.assertIsInstance(pooled, torch.Tensor)


class TestBF16FP16Fallback(unittest.TestCase):
    def test_unsupported_device_falls_back_to_p0(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cpu", None, False, False)
        for arm_id in ("P1", "P2", "P3", "P2A", "P2B", "P3A", "P3B"):
            self.assertEqual(_status(plan, arm_id), "UNSUPPORTED")
        for arm_id in ("P0", "P0A", "P0B"):
            self.assertEqual(_status(plan, arm_id), "OK")

    def test_p0_still_runs_when_low_capability(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cuda", (6, 0), True, True)
        for arm_id in ("P0", "P0A", "P0B"):
            self.assertEqual(_status(plan, arm_id), "OK")
        for arm_id in ("P2", "P2A", "P2B", "P3", "P3A", "P3B"):
            self.assertEqual(_status(plan, arm_id), "UNSUPPORTED")


class TestTf32SettingsRestored(unittest.TestCase):
    def test_p1_apply_and_restore_toggles_exactly(self) -> None:
        snapshot = lab.GlobalTorchSettings.snapshot()
        plan = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        p1 = lab.DtypePolicy.status_for(plan, "P1")

        lab.GlobalTorchSettings.apply("P1", p1)
        self.assertTrue(torch.backends.cuda.matmul.allow_tf32)
        if hasattr(torch, "get_float32_matmul_precision"):
            self.assertEqual(str(torch.get_float32_matmul_precision()), "high")

        lab.GlobalTorchSettings.restore(snapshot)
        self.assertEqual(lab.GlobalTorchSettings.snapshot(), snapshot)
        self.assertEqual(
            torch.backends.cuda.matmul.allow_tf32,
            snapshot["cuda_matmul_allow_tf32"],
        )

    def test_restore_is_idempotent(self) -> None:
        snapshot = lab.GlobalTorchSettings.snapshot()
        lab.GlobalTorchSettings.restore(snapshot)
        lab.GlobalTorchSettings.restore(snapshot)
        self.assertEqual(lab.GlobalTorchSettings.snapshot(), snapshot)


class TestNoLeakedGlobalTorchSettings(unittest.TestCase):
    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_full_arm_sweep_restores_globals(self) -> None:
        fixture = lab.prepare_fixture("classic_clip", seed=3, max_length=77, batch=1)
        pre = lab.GlobalTorchSettings.snapshot()
        device_kind, capability, bf16, fp16 = lab._device_info(None)
        plan = lab.DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)
        for entry in plan:
            result = lab.run_arm(
                fixture,
                entry["arm"],
                repeats=2,
                warmup=1,
                batch=1,
                plan_entry=entry,
            )
            self.assertEqual(
                result["classification"]["status"], "OK", entry["arm"]
            )
            self.assertTrue(result["_restored"], f"{entry['arm']} did not restore globals")
            self.assertFalse(torch.is_autocast_enabled())
            self.assertEqual(lab.GlobalTorchSettings.snapshot(), pre)


class TestCudaUnavailableBehavior(unittest.TestCase):
    def test_cpu_plan_unsupported_arms(self) -> None:
        plan = lab.DtypePolicy.plan_arms("cpu", None, False, False)
        statuses = {e["arm"]: e["status"] for e in plan}
        for arm_id in ("P1", "P2", "P3", "P4", "P1A", "P1B", "P2A", "P2B", "P3A", "P3B"):
            self.assertEqual(statuses[arm_id], "UNSUPPORTED")
        for arm_id in ("P0", "P0A", "P0B"):
            self.assertEqual(statuses[arm_id], "OK")

    def test_run_arm_unsupported_returns_without_comfy(self) -> None:
        stub = SimpleNamespace(
            class_names=["stub"],
            param_count=0,
            resident_dtype=torch.float32,
            max_length=77,
            batch=1,
            attention_function="stub",
        )
        plan = lab.DtypePolicy.plan_arms("cpu", None, False, False)
        p1 = lab.DtypePolicy.status_for(plan, "P1")
        result = lab.run_arm(stub, "P1", repeats=1, warmup=0, plan_entry=p1)
        self.assertEqual(result["classification"]["status"], "UNSUPPORTED")
        self.assertIn("reason", result["classification"])
        self.assertEqual(result["structure"]["timed_repeats"], 0)

    @unittest.skipUnless(not torch.cuda.is_available(), "runs only when CUDA absent")
    def test_real_matrix_completes_without_cuda(self) -> None:
        results = lab.run_matrix(["classic_clip"], ["P0", "P1", "P2", "P3", "P4"],
                                 repeats=1, warmup=0)
        self.assertEqual(results["meta"]["device_kind"], "cpu")
        p1 = results["fixtures"]["classic_clip"]["arms"]["P1"]
        self.assertEqual(p1["classification"]["status"], "UNSUPPORTED")


class TestCorrectnessMetrics(unittest.TestCase):
    def test_classification_matrix(self) -> None:
        generator = torch.Generator().manual_seed(11)
        reference = torch.randn(4, 8, generator=generator)

        exact = lab.Correctness.compare(reference, reference.clone())
        self.assertEqual(exact["class"], lab.Correctness.EXACT)
        self.assertEqual(exact["max_abs_error"], 0.0)
        self.assertAlmostEqual(exact["cosine_similarity"], 1.0, places=6)

        near = reference + 1e-4 * torch.randn_like(reference)
        close = lab.Correctness.compare(reference, near)
        self.assertEqual(close["class"], lab.Correctness.NUMERICALLY_CLOSE)
        self.assertGreaterEqual(close["cosine_similarity"], 0.999)
        self.assertLessEqual(close["max_abs_error"], 1e-2)

        far = lab.Correctness.compare(reference, -reference)
        self.assertEqual(far["class"], lab.Correctness.MATERIAL_DIFFERENCE)
        self.assertLess(far["cosine_similarity"], 0.999)

        nan_candidate = reference.clone()
        nan_candidate[0, 0] = float("nan")
        nan_result = lab.Correctness.compare(reference, nan_candidate)
        self.assertEqual(nan_result["class"], lab.Correctness.INVALID)
        self.assertEqual(nan_result["nan_cand"], 1)

        inf_candidate = reference.clone()
        inf_candidate[1, 1] = float("inf")
        inf_result = lab.Correctness.compare(reference, inf_candidate)
        self.assertEqual(inf_result["class"], lab.Correctness.INVALID)
        self.assertEqual(inf_result["inf_cand"], 1)

        mismatch = lab.Correctness.compare(reference, torch.randn(8, 4))
        self.assertEqual(mismatch["class"], lab.Correctness.INVALID)
        self.assertFalse(mismatch["shape_equal"])

        missing = lab.Correctness.compare(reference, None)
        self.assertEqual(missing["class"], lab.Correctness.UNSUPPORTED)

    def test_finite_percentage_reported(self) -> None:
        generator = torch.Generator().manual_seed(5)
        reference = torch.randn(2, 2, generator=generator)
        candidate = reference.clone()
        candidate[0, 0] = float("nan")
        result = lab.Correctness.compare(reference, candidate)
        self.assertEqual(result["finite_percentage"], 0.0)
        result = lab.Correctness.compare(reference, reference.clone())
        self.assertEqual(result["finite_percentage"], 100.0)


class TestTimingBoundaryIntegrity(unittest.TestCase):
    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_warmup_precedes_timed_repeats_and_counts_match(self) -> None:
        fixture = lab.prepare_fixture("classic_clip", seed=5, max_length=77, batch=1)
        phases = []

        def on_encode(index, phase):
            phases.append((index, phase))

        entry = lab._plan_entry_for("P0")
        result = lab.run_arm(
            fixture, "P0", repeats=4, warmup=2, batch=1, plan_entry=entry,
            on_encode=on_encode,
        )

        # First two encodes are warmup, strictly before any timed repeat.
        self.assertEqual([p for _, p in phases[:2]], ["warmup", "warmup"])
        self.assertEqual([p for _, p in phases[2:]], ["timed"] * 4)
        self.assertEqual(phases[0], (0, "warmup"))
        # Timed repeat counts match the result structure.
        self.assertEqual(result["structure"]["timed_repeats"], 4)
        self.assertEqual(result["structure"]["warmup_repeats"], 2)
        self.assertEqual(len(result["timing"]["forward_wall_ms_list"]), 4)
        self.assertEqual(len(result["timing"]["forward_cuda_event_ms_list"]), 4)
        # CUDA events bracket only encode calls (one event pair per timed rep).
        self.assertIsNotNone(result["timing"]["forward_cuda_event_median_ms"])
        # Load re-entry is measured separately, after the timed region.
        self.assertGreaterEqual(result["timing"]["load_reentry_wall_ms"], 0.0)


class TestP4PreferredDtypeSelection(unittest.TestCase):
    def test_preference_order(self) -> None:
        self.assertEqual(lab.DtypePolicy.preferred_compute_dtype((8, 0)), torch.bfloat16)
        self.assertEqual(lab.DtypePolicy.preferred_compute_dtype((8, 6)), torch.bfloat16)
        self.assertEqual(lab.DtypePolicy.preferred_compute_dtype((7, 0)), torch.float16)
        self.assertEqual(lab.DtypePolicy.preferred_compute_dtype((6, 0)), torch.float32)
        self.assertEqual(lab.DtypePolicy.preferred_compute_dtype(None), torch.float32)

    def test_plan_p4_compute_follows_preference(self) -> None:
        for capability, expected in (
            ((8, 6), "bf16"),
            ((7, 0), "fp16"),
            ((6, 0), "fp32"),
        ):
            plan = lab.DtypePolicy.plan_arms("cuda", capability, True, True)
            entry = lab.DtypePolicy.status_for(plan, "P4")
            self.assertEqual(entry["compute_dtype"], expected)

    def test_autocast_spec_wiring(self) -> None:
        plan8 = lab.DtypePolicy.plan_arms("cuda", (8, 6), True, True)
        spec = lab._autocast_spec("P4", lab.DtypePolicy.status_for(plan8, "P4"))
        self.assertEqual(spec, ("cuda", torch.bfloat16))
        plan6 = lab.DtypePolicy.plan_arms("cuda", (6, 0), True, True)
        spec = lab._autocast_spec("P4", lab.DtypePolicy.status_for(plan6, "P4"))
        self.assertIsNone(spec)  # fp32 preferred -> no autocast
        self.assertIsNone(lab._autocast_spec("P0", lab.DtypePolicy.status_for(plan8, "P0")))
        self.assertEqual(
            lab._autocast_spec("P2", lab.DtypePolicy.status_for(plan8, "P2")),
            ("cuda", torch.bfloat16),
        )
        self.assertEqual(
            lab._autocast_spec("P3", lab.DtypePolicy.status_for(plan8, "P3")),
            ("cuda", torch.float16),
        )


class TestSyntheticTokensShape(unittest.TestCase):
    def test_structure_for_clip_token_weight_encoder(self) -> None:
        tokens = lab.synthetic_tokens(max_length=77, batch=1, seed=42)
        self.assertIsInstance(tokens, list)
        self.assertEqual(len(tokens), 1)
        batch_tokens = tokens[0]
        self.assertEqual(len(batch_tokens), 77)
        for token_id, weight in batch_tokens:
            self.assertIsInstance(token_id, int)
            self.assertIsInstance(weight, float)
            self.assertEqual(weight, 1.0)
            self.assertGreaterEqual(token_id, 1)
            self.assertLess(token_id, 49408)

    def test_multi_batch_and_vocab_bounding(self) -> None:
        tokens = lab.synthetic_tokens(max_length=64, batch=3, seed=42)
        self.assertEqual(len(tokens), 3)
        for batch_tokens in tokens:
            self.assertEqual(len(batch_tokens), 64)
        small = lab.synthetic_tokens(77, 1, 1234, vocab_size=32000)
        for token_id, _ in small[0]:
            self.assertLess(token_id, 32000)
            self.assertGreaterEqual(token_id, 1)

    def test_deterministic(self) -> None:
        a = lab.synthetic_tokens(77, 1, 1234)
        b = lab.synthetic_tokens(77, 1, 1234)
        self.assertEqual(a, b)


class TestTransformerWrapCapability(unittest.TestCase):
    """(a) transformer-wrap capability check + exact wrap/restore identity."""

    def test_capability_matrix(self) -> None:
        accepts = lab._forward_accepts_dtype_or_embeds

        def f_var_kwargs(**kwargs):
            return None

        def f_explicit(input_tokens=None, attention_mask=None, embeds=None, dtype=None):
            return None

        def f_llama_style(input_ids, *args, **kwargs):
            return None

        def f_plain(x):
            return None

        def f_pos_only(x, attention_mask=None):
            return None

        self.assertTrue(accepts(f_var_kwargs))
        self.assertTrue(accepts(f_explicit))
        self.assertTrue(accepts(f_llama_style))
        self.assertFalse(accepts(f_plain))
        self.assertFalse(accepts(f_pos_only))
        self.assertFalse(accepts(42))
        self.assertFalse(accepts(None))

    def test_wrap_restore_exact_identity(self) -> None:
        class _Trans(torch.nn.Module):
            def forward(self, embeds=None, dtype=None):
                return embeds

        class _Container(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.transformer = _Trans()

        container = _Container()
        original_func = container.transformer.forward.__func__
        wrapped = lab._wrap_transformers(container, torch.bfloat16)
        self.assertEqual(len(wrapped), 1)
        transformer, restored_orig = wrapped[0]
        self.assertIs(transformer, container.transformer)
        # the stored original is the exact same underlying function object
        self.assertIs(restored_orig.__func__, original_func)
        self.assertIsNot(transformer.forward, restored_orig)
        # restore re-binds the exact original bound method (same __func__)
        transformer.forward = restored_orig
        self.assertIs(container.transformer.forward.__func__, original_func)
        # and it behaves identically (returns embeds unchanged)
        embeds = torch.randn(1, 3, 4)
        self.assertIs(container.transformer(embeds=embeds, dtype=torch.float32), embeds)

    def test_wrap_coerces_kwargs(self) -> None:
        calls = []

        class _Trans(torch.nn.Module):
            def forward(self, input_ids=None, attention_mask=None, embeds=None, dtype=None):
                calls.append((embeds.dtype if embeds is not None else None, dtype))
                return embeds

        class _Container(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.transformer = _Trans()

        container = _Container()
        wrapped = lab._wrap_transformers(container, torch.bfloat16)
        try:
            embeds = torch.randn(1, 3, 4, dtype=torch.float32)
            container.transformer(None, None, embeds=embeds, dtype=torch.float32)
        finally:
            for transformer, original in wrapped:
                transformer.forward = original
        self.assertEqual(calls, [(torch.bfloat16, torch.bfloat16)])


class TestTransformerWrapCoercion(unittest.TestCase):
    """(b) wrap coerces real encode Linear inputs to bf16/fp16; output stays
    fp32; unwrap restores fp32 compute."""

    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_coercion_bf16_and_fp16(self) -> None:
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)

        def _observed_linear_dtypes():
            import comfy.ops

            seen = set()
            handles = []
            linear_type = comfy.ops.disable_weight_init.Linear

            def _hook(module, args, kwargs):
                if args and torch.is_tensor(args[0]):
                    seen.add(str(args[0].dtype))

            for _name, module in fixture.model.named_modules():
                if isinstance(module, linear_type):
                    handles.append(module.register_forward_hook(_hook))
            fixture.encode_fn(fixture.encode_tokens)
            for handle in handles:
                handle.remove()
            return seen

        # bf16 wrap
        wrapped = lab._wrap_transformers(fixture.model, torch.bfloat16)
        try:
            self.assertEqual(_observed_linear_dtypes(), {"torch.bfloat16"})
            cond, pooled = fixture.encode_fn(fixture.encode_tokens)
            self.assertEqual(cond.dtype, torch.float32)
            self.assertEqual(pooled.dtype, torch.float32)
        finally:
            for transformer, original in wrapped:
                transformer.forward = original

        # fp16 wrap
        wrapped = lab._wrap_transformers(fixture.model, torch.float16)
        try:
            self.assertEqual(_observed_linear_dtypes(), {"torch.float16"})
        finally:
            for transformer, original in wrapped:
                transformer.forward = original

        # unwrapped -> fp32 compute again (CURRENT_COMFY behavior)
        self.assertEqual(_observed_linear_dtypes(), {"torch.float32"})


class TestResidentPolicyB(unittest.TestCase):
    """(c) one-time resident conversion outside the timed region + exact
    bitwise state_dict restoration."""

    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_state_dict_roundtrip_bitwise(self) -> None:
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)
        before = lab._snapshot_model_state(fixture.model)

        fixture.model.to(dtype=torch.bfloat16)
        wrapped = lab._wrap_transformers(fixture.model, torch.bfloat16)
        try:
            fixture.encode_fn(fixture.encode_tokens)  # P2B-style resident encode
        finally:
            for transformer, original in wrapped:
                transformer.forward = original

        lab._restore_model_state(fixture.model, before)
        after = fixture.model.state_dict()
        self.assertEqual(set(before.keys()), set(after.keys()))
        for key in before:
            self.assertEqual(after[key].dtype, before[key].dtype, key)
            self.assertTrue(torch.equal(after[key], before[key]), key)

        # The restored model computes fp32 again (resident restored to fp16 +
        # fp32 manual_cast): run an encode and check the output is finite.
        cond, pooled = fixture.encode_fn(fixture.encode_tokens)
        self.assertTrue(torch.isfinite(cond).all())


class TestValidityGate(unittest.TestCase):
    """(d) hard validity gate: skipped wrap -> ARM_INVALID_NOT_LOW_PRECISION;
    applied wrap -> VALID on a bf16-capable device."""

    @staticmethod
    def _cuda_plan():
        device_kind, capability, bf16, fp16 = lab._device_info(None)
        if device_kind != "cuda" or not (capability and capability[0] >= 8):
            return None
        return lab.DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)

    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_skipped_wrap_classifies_invalid(self) -> None:
        plan = self._cuda_plan()
        if plan is None:
            self.skipTest("needs CUDA sm>=8.0 for bf16 arms")
        p2a = lab.DtypePolicy.status_for(plan, "P2A")
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)

        original_check = lab._forward_accepts_dtype_or_embeds
        lab._forward_accepts_dtype_or_embeds = lambda f: False
        try:
            result = lab.run_arm(fixture, "P2A", repeats=1, warmup=0, batch=1, plan_entry=p2a)
        finally:
            lab._forward_accepts_dtype_or_embeds = original_check

        self.assertEqual(
            result["classification"]["status"], lab.ARM_INVALID_NOT_LOW_PRECISION
        )
        self.assertFalse(result["validity"]["valid"])
        # Without the wrap the encoder runs fp32 (sd1_clip hardcodes fp32 embeds).
        self.assertEqual(result["validity"]["actual_linear_input_dtype"], "torch.float32")
        self.assertTrue(result["_restored"])

    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_wrap_applied_is_valid(self) -> None:
        plan = self._cuda_plan()
        if plan is None:
            self.skipTest("needs CUDA sm>=8.0 for bf16 arms")
        p2b = lab.DtypePolicy.status_for(plan, "P2B")
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)

        result = lab.run_arm(fixture, "P2B", repeats=1, warmup=0, batch=1, plan_entry=p2b)
        self.assertEqual(result["classification"]["status"], "OK")
        self.assertTrue(result["validity"]["valid"])
        self.assertEqual(result["validity"]["actual_linear_input_dtype"], "torch.bfloat16")
        self.assertEqual(
            result["validity"]["actual_weight_compute_dtype_seen"], "torch.bfloat16"
        )
        self.assertEqual(
            result["validity"]["manual_cast_dtype_during_arm"], "torch.bfloat16"
        )
        self.assertTrue(result["validity"]["sdpa_flash_capable"])
        self.assertTrue(result["_restored"])


class TestCastAccountingSplit(unittest.TestCase):
    """(f) materialized-vs-short-circuit cast split on a tiny synthetic model."""

    @unittest.skipUnless(_HAS_COMFY, f"comfy unavailable: {_COMFY_IMPORT_ERROR}")
    def test_materialized_split(self) -> None:
        import comfy.ops

        def _make_model(dtype):
            class TinyModel(torch.nn.Module):
                def __init__(self):
                    super().__init__()
                    self.lin = comfy.ops.disable_weight_init.Linear(4, 4, dtype=dtype)
                    torch.nn.init.normal_(self.lin.weight)

                def encode_token_weights(self, tokens):
                    x = torch.randn(1, 2, 4, dtype=torch.float32)
                    return self.lin(x), None

            m = TinyModel()
            m.lin.comfy_cast_weights = True
            return m

        # resident fp32 == input fp32 -> cast short-circuits, materialized == 0
        m = _make_model(torch.float32)
        fx = SimpleNamespace(model=m, encode_fn=m.encode_token_weights, encode_tokens=None)
        info = lab._verification_pass(fx, None, False, policy_dtype=torch.float32)
        self.assertGreaterEqual(info["cast_op_count"], 1)
        self.assertEqual(info["cast_materialized_count"], 0)
        self.assertEqual(info["cast_materialized_bytes"], 0)
        self.assertEqual(info["actual_linear_input_dtype"], "torch.float32")
        self.assertEqual(info["actual_weight_compute_dtype_seen"], "torch.float32")

        # resident fp16, fp32 input -> every call materializes a fp32 weight
        m2 = _make_model(torch.float16)
        fx2 = SimpleNamespace(model=m2, encode_fn=m2.encode_token_weights, encode_tokens=None)
        info2 = lab._verification_pass(fx2, None, False, policy_dtype=torch.float32)
        self.assertEqual(info2["cast_op_count"], info["cast_op_count"])
        self.assertEqual(info2["cast_materialized_count"], info2["cast_op_count"])
        self.assertGreater(info2["cast_materialized_bytes"], 0)
        self.assertEqual(info2["actual_weight_compute_dtype_seen"], "torch.float32")


class TestResidentConvertTiming(unittest.TestCase):
    """(h) one_time_resident_convert_ms > 0 only for resident-changing arms."""

    @unittest.skipUnless(
        _HAS_COMFY and torch.cuda.is_available(), "needs comfy + CUDA"
    )
    def test_resident_convert_timing_split(self) -> None:
        device_kind, capability, bf16, fp16 = lab._device_info(None)
        if device_kind != "cuda" or not (capability and capability[0] >= 8):
            self.skipTest("needs CUDA sm>=8.0 for all resident arms")
        plan = lab.DtypePolicy.plan_arms(device_kind, capability, bf16, fp16)
        by_arm = {entry["arm"]: entry for entry in plan}
        fixture = lab.prepare_fixture("classic_clip", seed=7, max_length=77, batch=1)

        changing = {"P0B", "P1B", "P2B", "P3A"}
        for arm_id in ("P0A", "P0B", "P1A", "P1B", "P2A", "P2B", "P3A", "P3B"):
            result = lab.run_arm(
                fixture, arm_id, repeats=1, warmup=0, batch=1, plan_entry=by_arm[arm_id]
            )
            self.assertEqual(result["classification"]["status"], "OK", arm_id)
            convert_ms = result["timing"]["one_time_resident_convert_ms"]
            if arm_id in changing:
                self.assertGreater(convert_ms, 0.0, arm_id)
            else:
                self.assertEqual(convert_ms, 0.0, arm_id)
            # forward wall is measured separately (conversion not inside it)
            self.assertGreater(result["timing"]["forward_wall_median_ms"], 0.0, arm_id)


if __name__ == "__main__":
    unittest.main()
