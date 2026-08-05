"""Focused tests for the narrow strict V0/V1 VAE-policy comparator.

Tests ``tools/compare_vae_policy_runs`` with synthetic records.  These
tests never import heavy runtime modules and never invoke Modal.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPARATOR_PATH = REPO_ROOT / "tools" / "compare_vae_policy_runs.py"


def load_comparator():
    if not COMPARATOR_PATH.exists():
        raise AssertionError("tools/compare_vae_policy_runs.py missing")
    spec = importlib.util.spec_from_file_location(
        "compare_vae_policy_runs", COMPARATOR_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_record(
    policy: str = "v0",
    *,
    requested_prefetch: str = "off",
    applied_prefetch: str = "off",
    vae_decode_ms: float | None = 100.0,
    restore_count: int = 1,
    request_count: int = 1,
    fresh: Any = True,
    terminal_status: str = "ready",
    transfer_count: int = 1,
    workflow_hash: str | None = "wfhash",
    with_fallback: bool = False,
    run_index: int = 0,
    sampling_end_ns: int = 0,
    decode_end_ns: int = 5_000_000,
    applied_policy_override: str | None = None,
) -> dict[str, Any]:
    """Build a valid-able synthetic record; each kwarg can break one invariant."""
    applied_policy = policy if applied_policy_override is None else applied_policy_override
    events = [
        {
            "name": "cpu_snapshot_vae_policy_ready",
            "metadata": {"policy": applied_policy, "prefetch_mode": applied_prefetch},
        },
        {
            "name": "vae_early_activation_terminal",
            "metadata": {"status": terminal_status, "transfer_count": transfer_count},
        },
        {"name": "sampling_end", "monotonic_ns": sampling_end_ns},
        {"name": "vae_decode_end", "monotonic_ns": decode_end_ns},
    ]
    if with_fallback:
        events.append({"name": "vae_early_activation_fallback", "metadata": {}})

    provenance: dict[str, Any] = {}
    if workflow_hash is not None:
        provenance["workflow_hash"] = workflow_hash

    return {
        "run_index": run_index,
        "vae_policy": {
            "requested_policy": policy,
            "requested_prefetch_mode": requested_prefetch,
            "applied_policy": applied_policy,
        },
        "provenance": provenance,
        "timing": {"vae_decode_ms": vae_decode_ms},
        "waterfall": {
            "identity": {
                "restore_count": restore_count,
                "request_count": request_count,
                "fresh": fresh,
            }
        },
        "result": {"trace": {"events": events}},
    }


def assert_invalid(record: dict[str, Any], cmp, *, expected_hash=None):
    result = cmp.validate_record(record, expected_workflow_hash=expected_hash)
    assert result["status"] == "invalid", f"expected invalid, got {result}"
    return result


class ValidRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmp = load_comparator()

    def test_valid_v0_record(self):
        result = self.cmp.validate_record(make_record("v0"))
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["metrics"]["policy"], "v0")
        self.assertEqual(result["metrics"]["vae_decode_ms"], 100.0)
        self.assertEqual(result["metrics"]["sampling_end_to_decode_end_ms"], 5.0)

    def test_valid_v1_record(self):
        result = self.cmp.validate_record(make_record("v1"))
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["metrics"]["policy"], "v1")

    def test_valid_accepts_serialized_true_fresh(self):
        for serialized in ("true", "1", "yes", "on"):
            rec = make_record("v0", fresh=serialized)
            self.assertEqual(self.cmp.validate_record(rec)["status"], "valid")

    def test_valid_accepts_nested_result_trace_and_flat_trace(self):
        # Flat trace (no result wrapper) must also work.
        flat = make_record("v0")
        flat["trace"] = flat["result"]["trace"]
        del flat["result"]
        self.assertEqual(self.cmp.validate_record(flat)["status"], "valid")


class InvalidConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmp = load_comparator()

    def test_policy_mismatch(self):
        rec = make_record("v0", applied_policy_override="v1")
        assert_invalid(rec, self.cmp)

    def test_missing_requested_policy(self):
        rec = make_record("v0")
        rec["vae_policy"]["requested_policy"] = ""
        assert_invalid(rec, self.cmp)

    def test_missing_applied_policy_event(self):
        rec = make_record("v0")
        rec["result"]["trace"]["events"] = [
            e for e in rec["result"]["trace"]["events"]
            if e["name"] != "cpu_snapshot_vae_policy_ready"
        ]
        result = assert_invalid(rec, self.cmp)
        self.assertTrue(any("applied policy" in e for e in result["errors"]))
        self.assertEqual(result["status"], "invalid")

    def test_requested_prefetch_not_off(self):
        rec = make_record("v0", requested_prefetch="full")
        assert_invalid(rec, self.cmp)

    def test_applied_trace_prefetch_not_off(self):
        rec = make_record("v0", applied_prefetch="on")
        assert_invalid(rec, self.cmp)

    def test_missing_applied_prefetch_evidence(self):
        rec = make_record("v0")
        event = next(
            e for e in rec["result"]["trace"]["events"]
            if e["name"] == "cpu_snapshot_vae_policy_ready"
        )
        event["metadata"].pop("prefetch_mode", None)
        assert_invalid(rec, self.cmp)

    def test_missing_vae_decode_ms(self):
        rec = make_record("v0", vae_decode_ms=None)
        rec["timing"] = {}
        assert_invalid(rec, self.cmp)

    def test_restore_count_not_one(self):
        rec = make_record("v0", restore_count=2)
        assert_invalid(rec, self.cmp)

    def test_request_count_not_one(self):
        rec = make_record("v0", request_count=2)
        assert_invalid(rec, self.cmp)

    def test_fresh_false(self):
        rec = make_record("v0", fresh=False)
        assert_invalid(rec, self.cmp)

    def test_fresh_unknown_string(self):
        rec = make_record("v0", fresh="unknown")
        assert_invalid(rec, self.cmp)

    def test_missing_terminal_event(self):
        rec = make_record("v0")
        rec["result"]["trace"]["events"] = [
            e for e in rec["result"]["trace"]["events"]
            if e["name"] != "vae_early_activation_terminal"
        ]
        result = assert_invalid(rec, self.cmp)
        self.assertTrue(any("terminal" in e for e in result["errors"]))

    def test_terminal_status_not_ready(self):
        rec = make_record("v0", terminal_status="failed")
        assert_invalid(rec, self.cmp)

    def test_transfer_count_not_one(self):
        rec = make_record("v0", transfer_count=0)
        assert_invalid(rec, self.cmp)

    def test_fallback_event_invalid(self):
        rec = make_record("v0", with_fallback=True)
        assert_invalid(rec, self.cmp)

    def test_workflow_hash_mismatch(self):
        rec = make_record("v0", workflow_hash="other")
        assert_invalid(rec, self.cmp, expected_hash="wfhash")

    def test_workflow_hash_missing_when_expected(self):
        rec = make_record("v0", workflow_hash=None)
        assert_invalid(rec, self.cmp, expected_hash="wfhash")


class StrictVsNonStrictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmp = load_comparator()

    def test_missing_evidence_is_na_when_not_strict(self):
        rec = make_record("v0")
        rec["result"]["trace"]["events"] = [
            e for e in rec["result"]["trace"]["events"]
            if e["name"] != "vae_early_activation_terminal"
        ]
        result = self.cmp.validate_record(rec, strict=False)
        self.assertEqual(result["status"], "na")

    def test_missing_evidence_is_invalid_when_strict(self):
        rec = make_record("v0")
        rec["result"]["trace"]["events"] = [
            e for e in rec["result"]["trace"]["events"]
            if e["name"] != "vae_early_activation_terminal"
        ]
        result = self.cmp.validate_record(rec, strict=True)
        self.assertEqual(result["status"], "invalid")

    def test_mismatch_is_invalid_even_when_not_strict(self):
        rec = make_record("v0", applied_policy_override="v1")
        result = self.cmp.validate_record(rec, strict=False)
        self.assertEqual(result["status"], "invalid")


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cmp = load_comparator()

    def test_valid_matrix_two_each(self):
        records = [
            make_record("v0", run_index=0, vae_decode_ms=100.0, sampling_end_ns=0, decode_end_ns=5_000_000),
            make_record("v0", run_index=1, vae_decode_ms=200.0, sampling_end_ns=0, decode_end_ns=7_000_000),
            make_record("v1", run_index=2, vae_decode_ms=300.0, sampling_end_ns=0, decode_end_ns=9_000_000),
            make_record("v1", run_index=3, vae_decode_ms=400.0, sampling_end_ns=0, decode_end_ns=11_000_000),
        ]
        result = self.cmp.validate_matrix(records)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["counts"], {"v0": 2, "v1": 2})
        # No auto-selection of a winner.
        self.assertIsNone(result["winner"])

    def test_median_timing_values(self):
        records = [
            make_record("v0", run_index=0, vae_decode_ms=100.0, sampling_end_ns=0, decode_end_ns=5_000_000),
            make_record("v0", run_index=1, vae_decode_ms=200.0, sampling_end_ns=0, decode_end_ns=7_000_000),
            make_record("v1", run_index=2, vae_decode_ms=300.0, sampling_end_ns=0, decode_end_ns=9_000_000),
            make_record("v1", run_index=3, vae_decode_ms=400.0, sampling_end_ns=0, decode_end_ns=11_000_000),
        ]
        result = self.cmp.validate_matrix(records)
        self.assertEqual(
            result["summary"]["v0"]["median_vae_decode_ms"], 150.0
        )
        self.assertEqual(
            result["summary"]["v0"]["median_sampling_end_to_decode_end_ms"], 6.0
        )
        self.assertEqual(
            result["summary"]["v1"]["median_vae_decode_ms"], 350.0
        )
        self.assertEqual(
            result["summary"]["v1"]["median_sampling_end_to_decode_end_ms"], 10.0
        )
        # Per-run reporting present for each policy.
        self.assertEqual(len(result["summary"]["v0"]["per_run"]), 2)
        self.assertEqual(len(result["summary"]["v1"]["per_run"]), 2)

    def test_matrix_requires_exactly_two_v0_and_two_v1(self):
        # One V0 and three V1 -> both counts are wrong.
        records = [
            make_record("v0", run_index=0),
            make_record("v1", run_index=1),
            make_record("v1", run_index=2),
            make_record("v1", run_index=3),
        ]
        result = self.cmp.validate_matrix(records)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("V0 requires exactly 2" in e for e in result["errors"]))
        self.assertTrue(any("V1 requires exactly 2" in e for e in result["errors"]))

    def test_matrix_fails_on_invalid_record_in_strict_mode(self):
        records = [
            make_record("v0", run_index=0),
            make_record("v0", run_index=1, applied_policy_override="v1"),
            make_record("v1", run_index=2),
            make_record("v1", run_index=3),
        ]
        result = self.cmp.validate_matrix(records)
        self.assertEqual(result["status"], "invalid")

    def test_matrix_preserves_quality_evidence_and_never_na_in_strict(self):
        rec = make_record("v0", run_index=0)
        rec["quality"] = {"ssim": 0.99, "psnr": 40.0}
        records = [
            rec,
            make_record("v0", run_index=1),
            make_record("v1", run_index=2),
            make_record("v1", run_index=3),
        ]
        result = self.cmp.validate_matrix(records)
        self.assertEqual(result["status"], "valid")
        per_run = result["summary"]["v0"]["per_run"]
        self.assertEqual(per_run[0]["quality_evidence"]["quality"]["ssim"], 0.99)


if __name__ == "__main__":
    unittest.main()
