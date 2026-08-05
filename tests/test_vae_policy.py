import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.c5_vae_policy_runner import (
    ALLOWED_ARMS,
    COLD_RUNS,
    ENV_POLICY,
    ENV_PREFETCH,
    FIXTURE_PATH,
    GAP_SECONDS,
    GPU,
    MIN_CONTAINERS,
    OUTPUT_NODE_ID,
    PREFETCH_MODES,
    SCALEDOWN_WINDOW,
    SEED,
    WINNER_COMPUTES,
    WINNER_MEMORY_FORMATS,
    WINNER_WEIGHTS,
    build_arms,
    build_manifest,
    parse_winner_policy,
    validate_knobs,
    validate_winner_policy,
    validate_winner_prefetch,
)
from tools.compare_vae_policy_runs import (
    DEFAULT_GATES,
    _canonical_policy,
    assert_policy_metadata,
    asset_sha,
    check_same_policy_sha,
    evaluate_candidate,
    load_run_records,
    locate_image_path,
    normalize_record,
    recover_applied_policy,
    run_comparison,
)
from tools.image_metrics import PIXEL_MAX, compute_metrics, to_json


def _write_png(path: str, arr: np.ndarray) -> None:
    Image.fromarray(arr.astype(np.uint8)).save(path)


def _gradient(h: int = 64, w: int = 64) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w]
    base = (xx * 200 // max(1, w - 1))[..., None]
    return np.concatenate([base, base * 0 + yy[:, :, None], np.full((h, w, 1), 40)], axis=2).astype(np.uint8)


def _record(arm, requested, applied=None, **extra):
    rec = {
        "arm": arm,
        "requested_policy": requested,
        "applied_policy": applied if applied is not None else requested,
    }
    rec.update(extra)
    return rec


class ImageMetricsTests(unittest.TestCase):
    def test_identical_images_zero_error_json_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _gradient(64, 64)
            pa = os.path.join(tmp, "a.png")
            pb = os.path.join(tmp, "b.png")
            _write_png(pa, a)
            _write_png(pb, a)
            res = compute_metrics(pa, pb)
            self.assertTrue(res["valid"])
            self.assertTrue(res["identical"])
            self.assertEqual(res["mean_abs_diff"], 0.0)
            self.assertEqual(res["max_abs_diff"], 0.0)
            self.assertEqual(res["rmse"], 0.0)
            self.assertIsNone(res["psnr"])
            self.assertAlmostEqual(res["ssim"], 1.0, places=4)
            # strict JSON: no Infinity/NaN tokens
            text = to_json(res)
            self.assertNotIn("Infinity", text)
            self.assertNotIn("NaN", text)
            parsed = json.loads(text)
            self.assertTrue(parsed["identical"])
            self.assertIsNone(parsed["psnr"])

    def test_constant_offset_normalized_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = _gradient(32, 32)
            b = np.clip(a.astype(np.int16) + 10, 0, 255).astype(np.uint8)
            pa = os.path.join(tmp, "a.png")
            pb = os.path.join(tmp, "b.png")
            _write_png(pa, a)
            _write_png(pb, b)
            res = compute_metrics(pa, pb)
            self.assertAlmostEqual(res["mean_abs_diff"], 10.0 / PIXEL_MAX, places=5)
            self.assertAlmostEqual(res["max_abs_diff"], 10.0 / PIXEL_MAX, places=5)
            self.assertAlmostEqual(res["rmse"], 10.0 / PIXEL_MAX, places=5)
            self.assertFalse(res["identical"])
            self.assertIsNotNone(res["psnr"])
            self.assertLess(res["mean_abs_diff"], 1.0)

    def test_shape_mismatch_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            pa = os.path.join(tmp, "a.png")
            pb = os.path.join(tmp, "b.png")
            _write_png(pa, _gradient(32, 32))
            _write_png(pb, _gradient(16, 16))
            res = compute_metrics(pa, pb)
            self.assertFalse(res["valid"])
            self.assertFalse(res["checks"]["same_size"])
            self.assertIsNone(res["psnr"])
            self.assertFalse(res["identical"])


class PlannerTests(unittest.TestCase):
    def test_plan_only_default_no_modal(self):
        arms = build_arms(["v0", "v1"])
        for a in arms:
            self.assertNotIn("execution", a)
            self.assertIn("env", a)
        manifest = build_manifest(["v0", "v1"])
        self.assertEqual(manifest["mode"], "plan")
        self.assertIsNone(manifest["winner"])

    def test_real_env_names(self):
        arm = build_arms(["v0"])[0]
        self.assertEqual(set(arm["env"].keys()), {ENV_POLICY, ENV_PREFETCH})
        self.assertEqual(ENV_POLICY, "COMFYMODAL_V2_VAE_POLICY")
        self.assertEqual(ENV_PREFETCH, "COMFYMODAL_V2_VAE_PREFETCH_MODE")

    def test_v0_binds_explicitly_to_v0(self):
        arm = build_arms(["v0"])[0]
        self.assertEqual(arm["policy"], "v0")
        self.assertEqual(arm["prefetch"], "off")
        self.assertEqual(arm["env"][ENV_POLICY], "v0")
        self.assertEqual(arm["env"][ENV_PREFETCH], "off")

    def test_arms_include_fixed_protocol_defaults(self):
        arm = build_arms(["v1"])[0]
        self.assertEqual(arm["output_node"], OUTPUT_NODE_ID)
        self.assertEqual(arm["seed"], str(SEED))
        self.assertEqual(arm["gpu"], GPU)
        self.assertEqual(arm["min_containers"], MIN_CONTAINERS)
        self.assertEqual(arm["scaledown_window"], SCALEDOWN_WINDOW)
        self.assertEqual(arm["expected_cold_runs"], COLD_RUNS)
        self.assertEqual(arm["gap_seconds"], GAP_SECONDS)
        self.assertEqual(arm["fixture_path"], FIXTURE_PATH)
        self.assertEqual(FIXTURE_PATH, "c5_latest_benchmark_workflow.json")

    def test_real_prefetch_modes(self):
        self.assertEqual(
            PREFETCH_MODES,
            ("off", "madvise_willneed", "madvise_populate_read", "bounded_native_touch"),
        )

    def test_winner_bound_arms_require_winner(self):
        with self.assertRaises(ValueError):
            build_arms(["v3"])
        with self.assertRaises(ValueError):
            build_arms(["v4"])
        arms = build_arms(
            ["v3", "v4"], winner=("tuple:float32:float32:contiguous", "madvise_willneed")
        )
        for a in arms:
            self.assertTrue(a["winner_bound"])
            self.assertEqual(a["policy"], "tuple:float32:float32:contiguous")
            self.assertEqual(a["prefetch"], "madvise_willneed")
            self.assertEqual(a["env"][ENV_POLICY], "tuple:float32:float32:contiguous")
            self.assertEqual(a["env"][ENV_PREFETCH], "madvise_willneed")

    def test_tuple_validation(self):
        self.assertEqual(
            parse_winner_policy("tuple:bfloat16:bfloat16_native:channels_last"),
            {"weight": "bfloat16", "compute": "bfloat16_native", "memory_format": "channels_last"},
        )
        validate_winner_policy("tuple:float32:float32:contiguous")
        validate_winner_policy("tuple:float16:float16_autocast:channels_last")
        with self.assertRaises(ValueError):
            validate_winner_policy("not-a-tuple")
        with self.assertRaises(ValueError):
            validate_winner_policy("tuple:float32:float32")
        with self.assertRaises(ValueError):
            build_arms(["v3"], winner=("bogus", "madvise_willneed"))

    def test_invalid_tuple_components_rejected(self):
        # unsupported weight
        with self.assertRaises(ValueError):
            validate_winner_policy("tuple:int8:float32:contiguous")
        # unsupported compute
        with self.assertRaises(ValueError):
            validate_winner_policy("tuple:float32:float16:contiguous")
        # unsupported memory format
        with self.assertRaises(ValueError):
            validate_winner_policy("tuple:float32:float32:nchw")
        # build_arms rejects as well (never silently falls back to v0)
        with self.assertRaises(ValueError):
            build_arms(["v3"], winner=("tuple:float32:float16:contiguous", "off"))

    def test_concrete_policy_sets(self):
        self.assertEqual(WINNER_WEIGHTS, ("float32", "bfloat16", "float16"))
        self.assertEqual(
            WINNER_COMPUTES,
            ("float32", "bfloat16_native", "bfloat16_autocast",
             "float16_native", "float16_autocast"),
        )
        self.assertEqual(WINNER_MEMORY_FORMATS, ("contiguous", "channels_last"))

    def test_prefetch_validation(self):
        validate_winner_prefetch("bounded_native_touch")
        with self.assertRaises(ValueError):
            validate_winner_prefetch("bogus")
        with self.assertRaises(ValueError):
            build_arms(["v3"], winner=("tuple:float32:float32:contiguous", "bogus"))

    def test_unknown_knobs_rejected(self):
        with self.assertRaises(ValueError):
            validate_knobs({"not_a_knob": 1})
        with self.assertRaises(ValueError):
            build_arms(["v0"], knobs={"bogus": True})

    def test_unknown_arms_rejected(self):
        with self.assertRaises(ValueError):
            build_arms(["v9"])

    def test_all_arms_known(self):
        self.assertEqual(ALLOWED_ARMS, ("v0", "v1", "v2", "v3", "v4"))


class FixtureInvariantTests(unittest.TestCase):
    C5 = REPO_ROOT / "c5_latest_benchmark_workflow.json"
    CLEAN = REPO_ROOT / "clean_workflow.json"

    def test_c5_workflow_derived_from_clean(self):
        with io.open(self.C5, encoding="utf-8") as f:
            doc = json.load(f)
        p = doc["payload"]
        self.assertEqual(p["modal_options"]["production"]["output_node_ids"], ["107"])
        self.assertEqual(p["prompt"]["202"]["inputs"]["action"], "fixed")
        self.assertEqual(p["prompt"]["202"]["inputs"]["value"], SEED)

    def test_seed_and_output_node_invariants(self):
        with io.open(self.C5, encoding="utf-8") as f:
            doc = json.load(f)
        p = doc["payload"]
        self.assertEqual(p["workflow_metadata"]["seed"], SEED)
        self.assertIn("107", p["prompt"])
        self.assertEqual(p["prompt"]["107"]["class_type"], "Image Comparer (rgthree)")

    def test_sampler_topology_unchanged_vs_clean(self):
        with io.open(self.CLEAN, encoding="utf-8") as f:
            clean = json.load(f)
        with io.open(self.C5, encoding="utf-8") as f:
            p = json.load(f)["payload"]["prompt"]
        self.assertEqual(set(clean), set(p))
        changed = [k for k in clean if clean[k] != p[k]]
        self.assertEqual(changed, ["202"])


class GateThresholdTests(unittest.TestCase):
    def test_default_thresholds_explicit(self):
        self.assertEqual(DEFAULT_GATES["psnr_min"], 30.0)
        self.assertEqual(DEFAULT_GATES["ssim_min"], 0.95)
        self.assertAlmostEqual(DEFAULT_GATES["mad_max"], 2.0 / 255.0)
        self.assertAlmostEqual(DEFAULT_GATES["max_ad_max"], 12.0 / 255.0)
        self.assertEqual(DEFAULT_GATES["decode_regression_max"], 25.0)

    def test_identical_candidates_pass_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(32, 32)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, img)
            _write_png(pc, img)
            baseline = {"image_path": pa, "decode_ms": 100}
            candidate = _record("v1", "v1", image_path=pc, decode_ms=100)
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            self.assertTrue(res["pass"])
            self.assertFalse(res["warnings"])

    def test_bad_candidate_fails_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _gradient(32, 32)
            cand = (255 - base).astype(np.uint8)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, base)
            _write_png(pc, cand)
            baseline = {"image_path": pa}
            candidate = _record("v1", "v1", image_path=pc)
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            self.assertFalse(res["pass"])

    def test_normalized_metric_values_used_for_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = _gradient(32, 32)
            cand = np.clip(base.astype(np.int16) + 10, 0, 255).astype(np.uint8)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, base)
            _write_png(pc, cand)
            baseline = {"image_path": pa, "decode_ms": 100}
            candidate = _record("v1", "v1", image_path=pc, decode_ms=100)
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            # offset 10/255 exceeds mad_max 2/255
            self.assertAlmostEqual(res["metrics"]["mean_abs_diff"], 10.0 / 255.0, places=5)
            mad_gate = next(g for g in res["gates"] if g["gate"] == "mad")
            self.assertEqual(mad_gate["status"], "fail")
            self.assertFalse(res["pass"])

    def test_missing_timing_is_warning_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, img)
            _write_png(pc, img)
            baseline = {"image_path": pa}
            candidate = _record("v1", "v1", image_path=pc)
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            self.assertTrue(res["pass"])
            self.assertTrue(any("decode timing" in w for w in res["warnings"]))


class DeterministicShaTests(unittest.TestCase):
    def test_same_policy_sha_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            p1 = os.path.join(tmp, "c1.png")
            p2 = os.path.join(tmp, "c2.png")
            _write_png(p1, img)
            _write_png(p2, img)
            cands = [
                _record("v1", "v1", image_path=p1),
                _record("v1", "v1", image_path=p2),
            ]
            res = check_same_policy_sha(cands)
            self.assertTrue(res["deterministic"])
            self.assertEqual(res["violations"], [])
            self.assertEqual(asset_sha(p1), asset_sha(p2))

    def test_distinct_sha_violation_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "c1.png")
            p2 = os.path.join(tmp, "c2.png")
            _write_png(p1, _gradient(16, 16))
            _write_png(p2, (255 - _gradient(16, 16)).astype(np.uint8))
            cands = [
                _record("v1", "v1", image_path=p1),
                _record("v1", "v1", image_path=p2),
            ]
            res = check_same_policy_sha(cands)
            self.assertFalse(res["deterministic"])
            self.assertEqual(len(res["violations"]), 1)


class PolicyMetadataTests(unittest.TestCase):
    def test_requested_applied_equality_pass(self):
        rec = _record("v1", "v1")
        self.assertTrue(assert_policy_metadata(rec)["ok"])

    def test_applied_policy_mismatch_fails(self):
        rec = _record("v1", "v1", applied="v2")
        meta = assert_policy_metadata(rec)
        self.assertFalse(meta["ok"])
        self.assertTrue(any("does not match" in e for e in meta["errors"]))

    def test_dict_policy_canonical_equality(self):
        requested = {"tuple": "tuple:2:seq:fp16", "weight": 2, "compute": "seq"}
        applied = {"compute": "seq", "weight": 2, "tuple": "tuple:2:seq:fp16"}
        self.assertEqual(_canonical_policy(requested), _canonical_policy(applied))
        rec = {
            "requested_policy": requested,
            "applied_policy": applied,
        }
        self.assertTrue(assert_policy_metadata(rec)["ok"])

    def test_dict_policy_mismatch_detected(self):
        rec = {
            "requested_policy": {"tuple": "tuple:2:seq:fp16"},
            "applied_policy": {"tuple": "tuple:3:par:bf16"},
        }
        self.assertFalse(assert_policy_metadata(rec)["ok"])


class RunRecordTests(unittest.TestCase):
    def test_locate_image_path(self):
        rec = _record("v0", "v0", image_path="/x/y.png")
        self.assertEqual(locate_image_path(rec), "/x/y.png")

    def test_load_plain_list_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = os.path.join(tmp, "plain.json")
            manifest = os.path.join(tmp, "manifest.json")
            with io.open(plain, "w") as f:
                json.dump([{"requested_policy": "v1", "applied_policy": "v1"}], f)
            with io.open(manifest, "w") as f:
                json.dump({"runs": [{"applied_policy": "v2"}, {"applied_policy": "v3"}]}, f)
            self.assertEqual(len(load_run_records(plain)), 1)
            self.assertEqual(len(load_run_records(manifest)), 2)

    def test_applied_policy_mismatch_fails_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, img)
            _write_png(pc, img)
            baseline = {"image_path": pa, "decode_ms": 100}
            candidate = _record("v1", "v1", applied="v2", image_path=pc, decode_ms=100)
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            self.assertFalse(res["metadata_ok"])
            self.assertFalse(res["pass"])

    def test_run_comparison_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "cand.png")
            _write_png(pa, img)
            _write_png(pc, img)
            bp = os.path.join(tmp, "base.json")
            cp = os.path.join(tmp, "cand.json")
            with io.open(bp, "w") as f:
                json.dump({"image_path": pa, "decode_ms": 100}, f)
            with io.open(cp, "w") as f:
                json.dump(_record("v1", "v1", image_path=pc, decode_ms=100), f)
            out = os.path.join(tmp, "result.json")
            result = run_comparison(bp, [cp])
            with io.open(out, "w") as f:
                json.dump(result, f, allow_nan=False)
            with io.open(out) as f:
                loaded = json.load(f)
            self.assertTrue(loaded["overall_pass"])
            self.assertTrue(loaded["results"][0]["metadata_ok"])
            self.assertFalse(loaded["results"][0]["warnings"])


# ── Runtime-side VAE policy contract tests (comfymodal_runtime) ─────────────
# These exercise the runtime policy resolver, extended policy identity
# metadata, ModelRestoreKey policy roundtrip/legacy fallback, canonical
# per-role identity, and the bounded-prefetch metric contract.  They are
# independent of the harness planner tools above and keep the existing
# harness tests intact.


def _contracts():
    from comfymodal_runtime import contracts
    return contracts


def _cpu_snapshot():
    from comfymodal_runtime import cpu_snapshot_models
    return cpu_snapshot_models


PREFETCH_METRIC_CONTRACT = frozenset({
    "vae_prefetch_mode", "status", "start_ms", "end_ms", "wall_ms",
    "process_cpu_ms", "effective_cores", "bytes", "page_count",
    "ready_before_sampling_end", "overlap_with_sampling_ms", "error",
})


@contextmanager
def _env_override(values):
    """Temporarily set env vars, clear the C5 runtime cache, and restore."""
    c = _contracts()
    saved = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    c._C5_RUNTIME_CACHE = None
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        c._C5_RUNTIME_CACHE = None


class ResolveVaePolicyLabelTests(unittest.TestCase):
    def test_controlled_matrix_labels(self):
        rv = _contracts().resolve_vae_policy
        expected = {
            "v0": ("float32", "float32", "contiguous"),
            "v1": ("bfloat16", "bfloat16_native", "contiguous"),
            "v2": ("bfloat16", "bfloat16_autocast", "contiguous"),
            "v3": ("bfloat16", "bfloat16_autocast", "channels_last"),
            "v4": ("bfloat16", "bfloat16_native", "channels_last"),
        }
        for label, (weight, compute, fmt) in expected.items():
            pol = rv(label)
            self.assertEqual(
                (pol["vae_weight_dtype"], pol["vae_compute_dtype"], pol["vae_memory_format"]),
                (weight, compute, fmt),
                f"label {label} must map unambiguously",
            )
            self.assertEqual(pol["vae_policy_mode"], label)

    def test_resolve_returns_exactly_five_keys(self):
        # restore_plan.derive_model_key splats resolve_vae_policy() minus
        # vae_policy_mode into ModelRestoreKey — keep this contract stable.
        pol = _contracts().resolve_vae_policy("v2")
        self.assertEqual(
            set(pol.keys()),
            {"vae_policy_version", "vae_weight_dtype", "vae_compute_dtype",
             "vae_memory_format", "vae_policy_mode"},
        )

    def test_valid_tuple_parsing(self):
        rv = _contracts().resolve_vae_policy
        pol = rv("tuple:bfloat16:bfloat16_autocast:channels_last")
        self.assertEqual(pol["vae_weight_dtype"], "bfloat16")
        self.assertEqual(pol["vae_compute_dtype"], "bfloat16_autocast")
        self.assertEqual(pol["vae_memory_format"], "channels_last")
        self.assertEqual(pol["vae_policy_mode"], "tuple:bfloat16:bfloat16_autocast:channels_last")

    def test_invalid_tuple_fails_closed_to_v0(self):
        rv = _contracts().resolve_vae_policy
        for bad in (
            "tuple:bogus:x:y",
            "tuple:bfloat16:notacompute:contiguous",
            "tuple:bfloat16:bfloat16_autocast:bogus",
            "tuple:bfloat16",
        ):
            pol = rv(bad)
            self.assertEqual(pol["vae_weight_dtype"], "float32")
            self.assertEqual(pol["vae_policy_mode"], "v0", f"bad tuple {bad!r}")

    def test_invalid_label_fails_closed_to_v0(self):
        rv = _contracts().resolve_vae_policy
        self.assertEqual(rv("v9")["vae_policy_mode"], "v0")
        self.assertEqual(rv("")["vae_policy_mode"], "v0")


class BuildVaePolicyMetadataTests(unittest.TestCase):
    def test_provenance_fields(self):
        bpm = _contracts().build_vae_policy_metadata
        md = bpm({"vae_policy_mode": "tuple:bfloat16:bfloat16_native:channels_last"})
        self.assertEqual(md["vae_policy_provenance"], "tuple_form_b")
        self.assertEqual(md["vae_prefetch_mode"], "off")
        self.assertEqual(md["c5_impl_version"], _contracts().C5_IMPL_VERSION)
        self.assertIn("torch_version", md)
        self.assertIn("cuda_version", md)
        self.assertIn("arch_identifier", md)
        self.assertIn("env_overrides", md)

    def test_runtime_versions_env_overrides(self):
        bpm = _contracts().build_vae_policy_metadata
        with _env_override({
            "COMFYMODAL_V2_C5_TORCH_VERSION": "2.4.5",
            "COMFYMODAL_V2_C5_CUDA_VERSION": "11.8",
            "COMFYMODAL_V2_C5_ARCH": "sm_120",
            "COMFYMODAL_V2_VAE_PREFETCH_MODE": "bounded_native_touch",
        }):
            md = bpm(include_runtime_versions=True)
            self.assertEqual(md["torch_version"], "2.4.5")
            self.assertEqual(md["cuda_version"], "11.8")
            self.assertEqual(md["arch_identifier"], "sm_120")
            self.assertEqual(md["vae_prefetch_mode"], "bounded_native_touch")

    def test_persistent_metadata_excludes_runtime_versions(self):
        bpm = _contracts().build_vae_policy_metadata
        md = bpm(include_runtime_versions=False)
        self.assertNotIn("torch_version", md)
        self.assertNotIn("cuda_version", md)
        self.assertEqual(md["vae_prefetch_mode"], "off")


class ModelRestoreKeyPolicyMetadataTests(unittest.TestCase):
    def test_roundtrip_preserves_metadata(self):
        c = _contracts()
        key = c.ModelRestoreKey(
            unet_identity="u.safetensors",
            vae_identity="v.safetensors",
            vae_policy_metadata=c.build_vae_policy_metadata(
                {"vae_policy_mode": "tuple:bfloat16:bfloat16_autocast:channels_last",
                 "vae_prefetch_mode": "madvise_willneed"},
                include_runtime_versions=False,
            ),
        )
        restored = c.ModelRestoreKey.from_dict(key.to_dict())
        self.assertEqual(restored, key)
        self.assertEqual(restored.stable_hash, key.stable_hash)

    def test_legacy_fallback_populates_default_metadata(self):
        c = _contracts()
        # A legacy-serialized key dict has no vae_policy_metadata field.
        legacy = {
            "unet_identity": "u.safetensors",
            "clip_identity": "c.safetensors",
            "vae_identity": "v.safetensors",
            "clip_type": "sd",
            "vae_policy_version": 1,
            "vae_weight_dtype": "float32",
            "vae_compute_dtype": "float32",
            "vae_memory_format": "contiguous",
        }
        key = c.ModelRestoreKey.from_dict(legacy)
        md = dict(key.vae_policy_metadata)
        self.assertIn("vae_prefetch_mode", md)
        self.assertIn("c5_impl_version", md)
        # Round-tripping a legacy key must remain stable.
        self.assertEqual(c.ModelRestoreKey.from_dict(key.to_dict()), key)

    def test_metadata_absent_defaults_equal_across_instances(self):
        c = _contracts()
        a = c.ModelRestoreKey(unet_identity="u")
        b = c.ModelRestoreKey(unet_identity="u")
        self.assertEqual(a, b)
        self.assertEqual(a.stable_hash, b.stable_hash)


class ComputeLoaderRoleIdentityPolicyTests(unittest.TestCase):
    @staticmethod
    def _vae_spec(prefetch, c5="1.0.0", fmt="channels_last", compute="bfloat16_autocast"):
        return {"loaders": {"vae": [{
            "loader_class": "VAELoader",
            "vae_name": "v.safetensors",
            "vae_policy_version": 1,
            "vae_weight_dtype": "bfloat16",
            "vae_compute_dtype": compute,
            "vae_memory_format": fmt,
            "vae_prefetch_mode": prefetch,
            "c5_impl_version": c5,
        }]}}

    def test_identical_specs_no_mismatch(self):
        c = _contracts()
        a = c.compute_loader_role_identity("vae", self._vae_spec("off"))
        b = c.compute_loader_role_identity("vae", self._vae_spec("off"))
        self.assertEqual(c.find_role_identity_mismatch_fields(a, b), [])

    def test_prefetch_strategy_change_is_detected(self):
        c = _contracts()
        a = c.compute_loader_role_identity("vae", self._vae_spec("off"))
        b = c.compute_loader_role_identity("vae", self._vae_spec("bounded_native_touch"))
        mismatched = c.find_role_identity_mismatch_fields(a, b)
        self.assertIn("vae_prefetch_mode", mismatched)

    def test_impl_version_change_is_detected(self):
        c = _contracts()
        a = c.compute_loader_role_identity("vae", self._vae_spec("off", c5="1.0.0"))
        b = c.compute_loader_role_identity("vae", self._vae_spec("off", c5="1.0.1"))
        mismatched = c.find_role_identity_mismatch_fields(a, b)
        self.assertIn("c5_impl_version", mismatched)

    def test_unet_clip_policy_untouched(self):
        c = _contracts()
        unet = {"loaders": {"unet": [{"loader_class": "UNETLoader", "unet_name": "u.safetensors", "weight_dtype": "default"}]}}
        a = c.compute_loader_role_identity("unet", unet)
        b = c.compute_loader_role_identity("unet", unet)
        self.assertEqual(c.find_role_identity_mismatch_fields(a, b), [])


class RestorePlanVaeSpecPolicyTests(unittest.TestCase):
    """build_restore_model_spec VAE loader must carry prefetch + C5 identity."""

    _PREFETCH_ENV = "COMFYMODAL_V2_VAE_PREFETCH_MODE"

    def _request_spec(self, prefetch: str = "bounded_native_touch") -> dict:
        old = os.environ.get(self._PREFETCH_ENV)
        os.environ[self._PREFETCH_ENV] = prefetch
        try:
            from comfymodal_runtime.restore_plan import build_restore_model_spec
            workflow = {
                "1": {"class_type": "VAELoader", "inputs": {"vae_name": "v.safetensors"}},
            }
            return build_restore_model_spec(workflow)
        finally:
            if old is None:
                os.environ.pop(self._PREFETCH_ENV, None)
            else:
                os.environ[self._PREFETCH_ENV] = old

    def test_request_spec_carries_prefetch_and_impl_version(self):
        """Request VAE loader must not fall back to legacy_unset."""
        c = _contracts()
        spec = self._request_spec(prefetch="bounded_native_touch")
        vae = spec["loaders"]["vae"][0]
        self.assertEqual(vae["vae_prefetch_mode"], "bounded_native_touch")
        self.assertEqual(vae["c5_impl_version"], c.C5_IMPL_VERSION)
        # Regression guard: an omitted field used to project "legacy_unset"
        # on the production side and fail C5 snapshot identity matching.
        self.assertNotEqual(vae["vae_prefetch_mode"], "legacy_unset")
        self.assertNotEqual(vae["c5_impl_version"], "legacy_unset")

    def test_request_spec_matches_cpu_snapshot_vae_identity(self):
        """Request VAE spec must equal the CPU snapshot VAE loader identity."""
        c = _contracts()
        req = self._request_spec(prefetch="off")
        vae = req["loaders"]["vae"][0]
        # Mirror the identity tuple consumed by compute_loader_role_identity.
        req_tuple = (
            str(vae.get("loader_class", "")),
            str(vae.get("vae_name", "")),
            str(vae.get("vae_policy_version", 0)),
            str(vae.get("vae_weight_dtype", "legacy_unset")),
            str(vae.get("vae_compute_dtype", "legacy_unset")),
            str(vae.get("vae_memory_format", "legacy_unset")),
            str(vae.get("vae_prefetch_mode", "legacy_unset")),
            str(vae.get("c5_impl_version", "legacy_unset")),
        )
        snapshot = c.compute_loader_role_identity(
            "vae", {"loaders": {"vae": [vae]}}
        )
        self.assertEqual(
            snapshot["vae_prefetch_mode"], "off",
            "request prefetch mode must match snapshot prefetch mode",
        )
        self.assertEqual(
            snapshot["c5_impl_version"], c.C5_IMPL_VERSION,
            "request C5 impl version must match snapshot C5 impl version",
        )
        # The projected tuple must not contain any legacy_unset fallback.
        self.assertNotIn("legacy_unset", req_tuple)


class VaePrefetchMetricContractTests(unittest.TestCase):
    def test_off_mode_presents_metric_contract(self):
        m = _cpu_snapshot()
        result = m.prefetch_vae_storage(m.StorageRegistry(), mode="off")
        self.assertEqual(result["status"], "off")
        self.assertEqual(result["vae_prefetch_mode"], "off")
        self.assertTrue(PREFETCH_METRIC_CONTRACT.issubset(set(result.keys())))

    def test_empty_registry_presents_metric_contract(self):
        m = _cpu_snapshot()
        result = m.prefetch_vae_storage(m.StorageRegistry(), mode="bounded_native_touch")
        self.assertEqual(result["status"], "empty")
        self.assertTrue(PREFETCH_METRIC_CONTRACT.issubset(set(result.keys())))

    def test_bounded_native_touch_safe_tiny_registry(self):
        import ctypes
        m = _cpu_snapshot()
        page_size = m._page_size()
        # Allocate a generous page-aligned region; align up to a page boundary
        # so the prefetch range never overruns the allocation.
        raw = ctypes.create_string_buffer(page_size * 3)
        base = ctypes.addressof(raw)
        aligned = (base + page_size - 1) & ~(page_size - 1)
        registry = m.StorageRegistry(
            ranges=(m.StorageRange(address=aligned, length=page_size),),
            total_bytes=page_size,
        )
        result = m.prefetch_vae_storage(registry, mode="bounded_native_touch")
        self.assertIn(result["status"], {"ok", "bounded"})
        self.assertEqual(result["vae_prefetch_mode"], "bounded_native_touch")
        self.assertEqual(result["effective_cores"], 1.0)
        self.assertGreaterEqual(result["page_count"], 1)
        self.assertGreaterEqual(result["bytes"], page_size)
        self.assertTrue(PREFETCH_METRIC_CONTRACT.issubset(set(result.keys())))

    def test_invalid_mode_falls_back_to_off(self):
        m = _cpu_snapshot()
        result = m.prefetch_vae_storage(m.StorageRegistry(), mode="bogus")
        self.assertEqual(result["status"], "off")
        self.assertEqual(result["vae_prefetch_mode"], "off")


def _raw_record(**extra):
    """Build a raw record mimicking fresh_requests_results.json shape."""
    rec = {
        "run_index": 0,
        "request_id": "v2-fresh-00",
        "result": {
            "images": [
                {"path": "output_assets/abc.png", "backend_path": "output_assets/abc.png"}
            ],
            "trace": {
                "events": [
                    {
                        "name": "cpu_snapshot_vae_policy_ready",
                        "metadata": {
                            "vae_policy_mode": "v3",
                            "vae_weight_dtype": "float32",
                            "vae_compute_dtype": "float32",
                            "vae_memory_format": "contiguous",
                        },
                    }
                ]
            },
        },
        "timing": {"vae_decode_ms": 123.4},
    }
    rec.update(extra)
    return rec


class RawRecordNormalizationTests(unittest.TestCase):
    def test_recover_applied_policy_from_trace(self):
        rec = _raw_record()
        self.assertEqual(recover_applied_policy(rec), "v3")

    def test_recover_applied_policy_tuple_from_dtypes(self):
        rec = _raw_record()
        rec["result"]["trace"]["events"][0]["metadata"].pop("vae_policy_mode")
        self.assertEqual(recover_applied_policy(rec), "tuple:float32:float32:contiguous")

    def test_normalize_raw_nested_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            norm = normalize_record(_raw_record(), image_root=tmp)
            self.assertEqual(norm["applied_policy"], "v3")
            self.assertEqual(norm["decode_ms"], 123.4)
            self.assertEqual(norm["image_path"], os.path.join(tmp, "output_assets/abc.png"))

    def test_raw_record_without_requested_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = _raw_record()  # no requested_policy present
            norm = normalize_record(rec, image_root=tmp)
            self.assertIsNone(norm["requested_policy"])
            meta = assert_policy_metadata(norm)
            self.assertFalse(meta["ok"])
            self.assertTrue(any("requested" in e for e in meta["errors"]))

    def test_raw_record_applied_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            pa = os.path.join(tmp, "base.png")
            _write_png(pa, img)
            pc = os.path.join(tmp, "output_assets/abc.png")
            os.makedirs(os.path.dirname(pc), exist_ok=True)
            _write_png(pc, img)
            baseline = {"image_path": pa, "decode_ms": 100}
            rec = _raw_record(requested_policy="tuple:float32:float32:contiguous")
            candidate = normalize_record(rec, image_root=tmp)
            # trace says applied v3, requested is the concrete tuple -> mismatch
            res = evaluate_candidate(baseline, candidate, DEFAULT_GATES)
            self.assertFalse(res["metadata_ok"])
            self.assertFalse(res["pass"])

    def test_run_comparison_with_raw_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            img = _gradient(16, 16)
            pa = os.path.join(tmp, "base.png")
            pc = os.path.join(tmp, "output_assets/abc.png")
            os.makedirs(os.path.dirname(pc), exist_ok=True)
            _write_png(pa, img)
            _write_png(pc, img)
            bp = os.path.join(tmp, "base.json")
            cp = os.path.join(tmp, "cand.json")
            with io.open(bp, "w") as f:
                json.dump({"image_path": pa, "decode_ms": 100}, f)
            rec = _raw_record(requested_policy="v3", applied_policy="v3")
            rec["timing"] = {"vae_decode_ms": 105}
            with io.open(cp, "w") as f:
                json.dump(rec, f)
            result = run_comparison(bp, [cp], image_root=tmp)
            self.assertTrue(result["results"][0]["metadata_ok"])
            self.assertEqual(result["results"][0]["decode_regression_pct"], 5.0)


class ExecuteGuardTests(unittest.TestCase):
    def test_execute_without_allow_modal_exits_nonzero(self):
        import contextlib

        from tools import c5_vae_policy_runner as runner

        old = sys.argv
        sys.argv = ["c5_vae_policy_runner.py", "--arms", "v0", "--execute"]
        try:
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(io.StringIO()):
                runner.main()
            self.assertNotEqual(cm.exception.code, 0)
        finally:
            sys.argv = old


if __name__ == "__main__":
    unittest.main()
