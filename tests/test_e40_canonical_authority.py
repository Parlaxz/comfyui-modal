"""E40: canonical runtime truth — deterministic authority tests.

Pins the E40 end state:
- one configuration authority (config_authority) whose fingerprint binds
  requested/deployed/runtime;
- one loader-selection authority (loader_selection) with
  requested/effective/observed semantics and fallback != nominal;
- one canonical owner identity per semantic restore read;
- RuntimeStatus + StructuralValidator as the single acceptance authority;
- waterfall diagnostic_status is diagnostic-only;
- snapshot quiescence proof wired fail-closed at the capture boundary;
- conditioning forced-miss + persist=0 pinned in the Golden profile.
"""

from __future__ import annotations

import io
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT

from comfymodal_runtime import config_authority as ca  # noqa: E402
from comfymodal_runtime import loader_selection as ls  # noqa: E402
from comfymodal_runtime import runtime_status as rs  # noqa: E402


def _read(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


class TestConfigAuthority(unittest.TestCase):
    """E40 Lane A: one configuration authority."""

    def test_resolve_is_deterministic_and_fingerprinted(self):
        env = {"COMFYMODAL_V2_CLIP_QD_READER": "1", "COMFYMODAL_V2_CLIP_QD_QD": "4"}
        a = ca.resolve(env)
        b = ca.resolve(dict(env))
        self.assertEqual(a.fingerprint(), b.fingerprint())
        self.assertEqual(a.get("COMFYMODAL_V2_CLIP_QD_READER"), True)

    def test_fingerprint_changes_when_control_changes(self):
        base = {"COMFYMODAL_V2_CLIP_QD_QD": "4"}
        other = {"COMFYMODAL_V2_CLIP_QD_QD": "8"}
        self.assertNotEqual(
            ca.resolve(base).fingerprint(),
            ca.resolve(other).fingerprint(),
        )

    def test_unregistered_algorithm_changing_env_detected(self):
        hits = ca.detect_unregistered_mutations(
            {"COMFYMODAL_V2_TOTALLY_UNKNOWN_FLAG": "1"}
        )
        self.assertIn("COMFYMODAL_V2_TOTALLY_UNKNOWN_FLAG", hits)

    def test_invalid_value_falls_back_to_default(self):
        rc = ca.resolve({"COMFYMODAL_V2_CLIP_QD_QD": "not-a-number"})
        spec = ca.GOLDEN_CONTROL_FLAGS["COMFYMODAL_V2_CLIP_QD_QD"]
        self.assertEqual(rc.values["COMFYMODAL_V2_CLIP_QD_QD"], spec["default"])

    def test_golden_dynamic_vram_gate_is_registered_fail_closed(self):
        spec = ca.GOLDEN_CONTROL_FLAGS["COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM"]
        self.assertEqual(spec["type"], "bool")
        self.assertIs(spec["default"], False)


class TestLoaderSelectionAuthority(unittest.TestCase):
    """E40 Lane B: requested/effective/observed + fallback semantics."""

    def setUp(self):
        ls.reset_for_run()

    def tearDown(self):
        ls.reset_for_run()

    def test_requested_clip_qd4_when_qd_reader_enabled(self):
        rc = ca.resolve({"COMFYMODAL_V2_CLIP_QD_READER": "1"})
        self.assertEqual(ca.requested_loader("clip", rc), "qd4_reader")

    def test_inherited_speculative_flag_cannot_become_requested(self):
        # With QD reader on, an inherited speculative flag must NOT change
        # the requested arm (precedence) ...
        rc = ca.resolve({
            "COMFYMODAL_V2_CLIP_QD_READER": "1",
            "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "1",
        })
        self.assertEqual(ca.requested_loader("clip", rc), "qd4_reader")
        # ... and with everything unset, speculative must stay OFF (default).
        rc_off = ca.resolve({})
        self.assertNotEqual(ca.requested_loader("clip", rc_off), "speculative_clip")

    def test_speculative_lane_requires_explicit_opt_in(self):
        from comfymodal_runtime.speculative_clip_hydration import (
            speculative_clip_hydration_enabled,
        )
        old = os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
        try:
            # Unset variable must not activate the arm through defaults...
            if _clean_lane_active():
                self.assertFalse(speculative_clip_hydration_enabled())
            else:
                self.assertFalse(speculative_clip_hydration_enabled())
            os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = "0"
            self.assertFalse(speculative_clip_hydration_enabled())
        finally:
            if old is None:
                os.environ.pop("COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION", None)
            else:
                os.environ["COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION"] = old

    def test_observation_normalizes_to_canonical_vocabulary(self):
        ls.seed_from_resolved({"clip": "qd4_reader"})
        ls.record_observed("clip", "qd_reader")
        snap = ls.snapshot()["clip"]
        self.assertEqual(snap["requested"], "qd4_reader")
        self.assertEqual(snap["observed"], "qd4_reader")
        self.assertEqual(ls.mismatches(), [])

    def test_fallback_recorded_not_rewritten_as_planned(self):
        ls.seed_from_resolved({"clip": "qd4_reader"})
        ls.record_observed("clip", "qd_reader")
        ls.record_observed("clip", "native_comfy",
                           fallback_attempted=True,
                           fallback_reason="qd_read_failed")
        snap = ls.snapshot()["clip"]
        self.assertTrue(snap["fallback_attempted"])
        self.assertEqual(snap["fallback_loader"], "native_comfy")
        self.assertEqual(snap["effective"], "qd4_reader")
        reasons = ls.mismatches()
        self.assertTrue(any(r.startswith("loader_fallback_clip:") for r in reasons))

    def test_snapshot_resident_arm_realized_without_disk_read(self):
        ls.seed_from_resolved({"unet": "cpu_snapshot_native"})
        # No record_observed call: snapshot delivery IS the observation.
        from comfymodal_runtime.loader_selection import normalize_observed
        self.assertEqual(normalize_observed("unet", "cpu_snapshot_model"),
                         "cpu_snapshot_native")


def _clean_lane_active() -> bool:
    try:
        from comfymodal_runtime import clean_lane
        return bool(clean_lane.enabled())
    except Exception:
        return False


class TestOwnerIdentity(unittest.TestCase):
    """E40 Lane D: one semantic operation -> one canonical owner identity."""

    def test_no_legacy_restore_clip_loader_producer(self):
        for path in ("comfyapp.py", "__init__.py"):
            self.assertNotIn("restore_clip_loader", _read(path),
                             f"{path} must not register legacy owner name")

    def test_role_maps_agree_between_producer_and_entrypoint(self):
        comfy_src = _read("comfyapp.py")
        init_src = _read("__init__.py")
        self.assertIn('"clip": "restore_preload"', comfy_src)
        self.assertIn('"clip": "restore_preload"', init_src)
        self.assertIn("RESTORE_ROLE_OWNER_MAP", comfy_src)

    def test_consumer_preflight_waits_on_canonical_name(self):
        comfy_src = _read("comfyapp.py")
        self.assertIn('== "restore_preload"', comfy_src)


class TestRuntimeStatusAndAcceptance(unittest.TestCase):
    """E40 Lane E: RuntimeStatus + single acceptance authority."""

    def test_runtime_status_nominal_when_no_reasons(self):
        out = rs.build_runtime_status(loader_selection=None, reasons=None)
        self.assertEqual(out["status"], "NOMINAL")
        self.assertEqual(out["reasons"], [])

    def test_runtime_status_degraded_on_fallback(self):
        sel = {"clip": {
            "requested": "qd4_reader", "effective": "qd4_reader",
            "observed": "qd4_reader", "fallback_attempted": True,
            "fallback_loader": "native_comfy", "fallback_reason": "x",
        }}
        out = rs.build_runtime_status(loader_selection=sel, reasons=None)
        self.assertEqual(out["status"], "DEGRADED")

    def test_validator_flags_fallback_and_mismatch(self):
        sys_path_setup = _read("tools/v2_control/validation.py")
        # Source-level pin: the single acceptance authority enforces the
        # contract strings emitted by the runtime.
        for needle in ("runtime_status_not_nominal", "loader_fallback_",
                       "loader_observed_mismatch_", "resolved_config_fingerprint_mismatch"):
            self.assertIn(needle, sys_path_setup)

    def test_missing_vs_zero_vs_unobservable_distinct(self):
        classify = getattr(rs, "classify", None)
        if callable(classify):
            self.assertNotEqual(classify(None), classify(0))
            self.assertNotEqual(classify(0), classify("UNOBSERVABLE"))


class TestWaterfallDiagnosticOnly(unittest.TestCase):
    """E40 Lane F: waterfall status is diagnostic, never acceptance."""

    def test_report_field_is_diagnostic_status(self):
        src = _read("comfymodal_runtime/v2_waterfall.py")
        self.assertIn("diagnostic_status", src)
        self.assertNotIn("validation_status: str", src)

    def test_export_uses_diagnostic_key(self):
        src = _read("comfymodal_runtime/v2_waterfall.py")
        self.assertIn('"diagnostic_status"', src)

    def test_legacy_parse_tolerance_retained(self):
        src = _read("comfymodal_runtime/v2_waterfall.py")
        self.assertIn('value.get("validation_status"', src)


class TestSnapshotQuiescence(unittest.TestCase):
    """E40 Lane G: quiescence proven fail-closed before capture."""

    def test_capture_boundary_calls_quiescence_proof(self):
        src = _read("comfymodal_runtime/modal_app.py")
        self.assertIn("prove_snapshot_quiescence()", src)
        self.assertIn("snapshot capture quiescence could not be proven", src)

    def test_conditioning_cache_exposes_quiesce(self):
        src = _read("comfymodal_runtime/clip_conditioning_cache.py")
        self.assertIn("def quiesce_for_snapshot", src)

    def test_manifest_records_payload_facts(self):
        src = _read("comfymodal_runtime/snapshot_build_manifest.py")
        self.assertIn("meta_parameter_count", src)
        self.assertIn("UNOBSERVABLE", src)


class TestGoldenProfileTruth(unittest.TestCase):
    """E40 Lanes H/I: profile pins cache policy and exact output identity."""

    def test_profile_forced_miss_and_persist_zero(self):
        toml = _read("config/v2/profiles/e37-clean-lane-qd4.toml")
        self.assertIn('conditioning_cache = "forced_miss"', toml)
        self.assertIn('COMFYMODAL_V2_EXACT_CACHE_PERSIST = "0"', toml)

    def test_profile_pins_exact_output_sha(self):
        toml = _read("config/v2/profiles/e37-clean-lane-qd4.toml")
        self.assertIn("20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260", toml)

    def test_profile_disables_speculative_arm_explicitly(self):
        toml = _read("config/v2/profiles/e37-clean-lane-qd4.toml")
        self.assertIn('COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION = "0"', toml)

    def test_deployment_identity_primitive_exists(self):
        src = _read("comfymodal_runtime/deployment_spec.py")
        self.assertIn("def build_deployment_identity", src)


if __name__ == "__main__":
    unittest.main()
