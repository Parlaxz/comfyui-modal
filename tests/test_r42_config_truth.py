"""R42 five-layer configuration truth tests.

Covers the E40 config-anomaly root-cause fix (deployed-truth fingerprints),
the Golden cache of documented legacy-control mappings, the r42-golden-qd4
profile contract, and fail-closed validator coverage for unexplained
config-truth mismatches.
"""

from __future__ import annotations

import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from comfymodal_runtime import config_authority as ca  # noqa: E402
from comfymodal_runtime import loader_selection as ls  # noqa: E402

PROFILE_PATH = ROOT / "config" / "v2" / "profiles" / "r42-golden-qd4.toml"
EXPECTED_SHA = "20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260"


# ── duck-typed v2ctl config stubs ──────────────────────────────────────────


class _Flag:
    def __init__(self, name: str, value: object, change_requires: str = "deploy"):
        self.name = name
        self.value = value
        self.change_requires = change_requires


class _Git:
    head = "0c59f46e3238f421378e8852ebc548da815b70af"
    dirty = True
    dirty_hashes: dict = {}


class _Target:
    app = "app.py"
    class_name = "Cls"
    method = "m"


class _Resources:
    gpu = "any"
    cpu = 12
    memory_mb = 32768
    min_containers = 0
    scaledown_window = 5


class _Workload:
    fresh_required = True
    conditioning_cache = "forced_miss"
    expected_output_sha = EXPECTED_SHA
    run_count = 1
    gap_seconds = 35.0
    nonce = "n"


class _Config:
    def __init__(self, flags):
        self.git = _Git()
        self.target = _Target()
        self.resources = _Resources()
        self.flags = flags
        self.unregistered = []
        self.profile_name = "r42-golden-qd4"
        self.runtime_override_policy = "forbid"
        self.workload = _Workload()


def _selector_flags():
    return [
        _Flag("V2_E19_FINAL_COLD_LOADER", "1", change_requires="none"),
        _Flag("COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS", "0"),
        _Flag("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION", "0"),
        _Flag("COMFYMODAL_V2_UNET_FASTSAFETENSORS", "0"),
    ]


class TestDeployedTruthFingerprints(unittest.TestCase):
    """The deploy record must never masquerade projection as deployed env."""

    def test_deploy_flags_carry_env_truth_with_selector_active(self):
        from tools.v2_control.fingerprints import FingerprintEngine

        engine = FingerprintEngine(_Config(_selector_flags()))
        inputs = engine.deploy_inputs()
        self.assertEqual(inputs["deploy_flags"]["COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS"], "0")
        self.assertEqual(inputs["deploy_flags"]["COMFYMODAL_V2_FAST_COLD_ORCHESTRATION"], "0")
        self.assertEqual(inputs["deploy_flags"]["COMFYMODAL_V2_UNET_FASTSAFETENSORS"], "0")

    def test_post_selector_projection_reported_separately(self):
        from tools.v2_control.fingerprints import FingerprintEngine

        engine = FingerprintEngine(_Config(_selector_flags()))
        inputs = engine.deploy_inputs()
        projection = inputs["post_selector_projection"]
        self.assertIsInstance(projection, dict)
        self.assertEqual(projection["selector"], "V2_E19_FINAL_COLD_LOADER")
        self.assertEqual(
            projection["projected_flags"]["COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS"], "1"
        )
        self.assertIn("NOT applied", projection["note"])

    def test_projection_absent_when_selector_inactive(self):
        from tools.v2_control.fingerprints import FingerprintEngine

        flags = [_Flag("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION", "0")]
        engine = FingerprintEngine(_Config(flags))
        self.assertIsNone(engine.post_selector_projection())


class TestBuildConfigTruth(unittest.TestCase):
    def test_all_agree_when_no_overrides(self):
        rc = ca.resolve({})
        truth = ca.build_config_truth(rc)
        self.assertEqual(truth["unexplained_mismatches"], [])
        for row in truth["controls"]:
            if row["reason"]:
                # documented legacy-policy divergence is allowed
                self.assertFalse(row["agreement"], row)
            else:
                self.assertTrue(row["agreement"], row)

    def test_legacy_mapping_documented_not_unexplained(self):
        rc = ca.resolve({"COMFYMODAL_GOLDEN_PIPELINE": "1", "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "0"})
        truth = ca.build_config_truth(rc)
        row = next(r for r in truth["controls"] if r["name"] == "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS")
        self.assertFalse(row["agreement"])
        self.assertEqual(row["reason"], "superseded_by_golden_snapshot_policy")
        self.assertTrue(row["semantic_effective"])
        self.assertNotIn(row["name"], truth["unexplained_mismatches"])

    def test_unexplained_mismatch_detected(self):
        rc = ca.resolve({})
        truth = ca.build_config_truth(
            rc,
            requested_overrides={"COMFYMODAL_MINIMAL_RESTORE": False},
        )
        row = next(r for r in truth["controls"] if r["name"] == "COMFYMODAL_MINIMAL_RESTORE")
        self.assertFalse(row["agreement"])
        self.assertEqual(row["reason"], "")
        self.assertIn("COMFYMODAL_MINIMAL_RESTORE", truth["unexplained_mismatches"])

    def test_observed_layer_passes_through(self):
        rc = ca.resolve({})
        truth = ca.build_config_truth(
            rc,
            observed={"COMFYMODAL_GOLDEN_PIPELINE": True},
        )
        row = next(r for r in truth["controls"] if r["name"] == "COMFYMODAL_GOLDEN_PIPELINE")
        self.assertEqual(row["observed"], True)

    def test_deployed_env_layer_normalized(self):
        rc = ca.resolve({})
        truth = ca.build_config_truth(
            rc,
            deployed_env={"COMFYMODAL_MINIMAL_RESTORE": "true"},
        )
        row = next(r for r in truth["controls"] if r["name"] == "COMFYMODAL_MINIMAL_RESTORE")
        self.assertEqual(row["deployed"], True)


class TestExplainLegacyControl(unittest.TestCase):
    def test_three_e40_anomaly_controls_mapped(self):
        clip = ca.explain_legacy_control("COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS")
        orch = ca.explain_legacy_control("COMFYMODAL_V2_FAST_COLD_ORCHESTRATION")
        unet = ca.explain_legacy_control("COMFYMODAL_V2_UNET_FASTSAFETENSORS")
        self.assertEqual(clip["reason"], "superseded_by_golden_snapshot_policy")
        self.assertTrue(clip["semantic_effective"])
        self.assertEqual(orch["reason"], "superseded_by_golden_pipeline_orchestration")
        self.assertFalse(orch["semantic_effective"])
        self.assertEqual(unet["reason"], "superseded_by_golden_qd4_loader")
        self.assertFalse(unet["semantic_effective"])

    def test_unknown_control_returns_none(self):
        self.assertIsNone(ca.explain_legacy_control("COMFYMODAL_MINIMAL_RESTORE"))
        self.assertIsNone(ca.explain_legacy_control("NOT_A_FLAG"))


class TestGoldenRequestedLoader(unittest.TestCase):
    def test_golden_pipeline_true_requests_golden_qd4_everywhere(self):
        rc = ca.resolve({"COMFYMODAL_GOLDEN_PIPELINE": "1"})
        for role in ("clip", "unet", "vae"):
            self.assertEqual(ca.requested_loader(role, rc), "golden_qd4")

    def test_golden_pipeline_off_keeps_legacy_precedence(self):
        rc = ca.resolve({"COMFYMODAL_V2_CLIP_QD_READER": "1"})
        self.assertEqual(ca.requested_loader("clip", rc), "qd4_reader")


class TestR42ProfileContract(unittest.TestCase):
    def test_profile_parses_with_mandated_values(self):
        with open(PROFILE_PATH, "rb") as handle:
            data = tomllib.load(handle)
        env = data["environment"]
        mandated = {
            "COMFYMODAL_GOLDEN_PIPELINE": "1",
            "COMFYMODAL_V2_CLIP_QD_READER": "1",
            "COMFYMODAL_V2_CLIP_QD_QD": "4",
            "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
            "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
            "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "1",
            "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
            "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
            "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
            "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "0",
            "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
            "COMFYMODAL_V2_EXECUTION_PREFILL": "0",
            "COMFYMODAL_V2_BACKGROUND_PERSISTENCE": "0",
            "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
            "COMFYMODAL_V2_MODEL_PRELOAD": "0",
            "COMFYMODAL_V2_GRAPH_PRELOAD": "0",
            "COMFYMODAL_MINIMAL_RESTORE": "1",
            "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
            "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
            "COMFYMODAL_V2_EXACT_CACHE_PERSIST": "0",
        }
        for name, value in mandated.items():
            self.assertEqual(env.get(name), value, name)
        self.assertEqual(data["workload"]["expected_output_sha"], EXPECTED_SHA)
        self.assertEqual(data["workload"]["conditioning_cache"], "forced_miss")
        # placement unpinned
        self.assertNotIn("COMFYMODAL_V2_CLOUD", env)
        self.assertNotIn("COMFYMODAL_V2_REGION", env)


class TestValidatorConfigTruthFailClosed(unittest.TestCase):
    """Unexplained config-truth disagreement rejects validation."""

    @staticmethod
    def _record(config_truth):
        class _Record:
            def __init__(self, truth):
                self.telemetry = {"config_truth": truth}
                self.artifacts = None

        return _Record(config_truth)

    def test_unexplained_mismatch_rejected(self):
        from tools.v2_control import validation as val

        truth = {
            "controls": [
                {"name": "COMFYMODAL_MINIMAL_RESTORE", "agreement": False, "reason": ""},
            ]
        }
        failures = val._validate_runtime_contract(self._record(truth), None)
        self.assertIn("config_truth_unexplained_mismatch:COMFYMODAL_MINIMAL_RESTORE", failures)

    def test_documented_reason_row_passes(self):
        from tools.v2_control import validation as val

        truth = {
            "controls": [
                {
                    "name": "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS",
                    "agreement": False,
                    "reason": "superseded_by_golden_snapshot_policy",
                },
            ]
        }
        failures = val._validate_runtime_contract(self._record(truth), None)
        self.assertEqual(failures, [])


class TestLoaderSelectionGoldenArm(unittest.TestCase):
    def test_golden_qd4_in_every_role_vocabulary(self):
        self.assertIn("golden_qd4", ls._CLIP_ARMS)
        self.assertIn("golden_qd4", ls._UNET_ARMS)
        self.assertIn("golden_qd4", ls._VAE_ARMS)

    def test_normalize_maps_golden_spellings(self):
        self.assertEqual(ls.normalize_observed("clip", "golden_qd4"), "golden_qd4")
        self.assertEqual(ls.normalize_observed("unet", "golden-qd4"), "golden_qd4")


if __name__ == "__main__":
    unittest.main()
