"""Unit tests for the Batch-A acceptance harness (tools/batch_a_acceptance.py).

Pure offline fixtures matching the run_<i>.json artifact shape persisted by
benchmark_v2_direct.py, using the exact event/field names the Batch-A runtime
lanes emit (G1 plan-receipt schedule marker, models_reload_decision trace
event, unet_fast_disk_complete H2D evidence, start_perf_ns/end_perf_ns node
timing, terminal_cleanup_{start,end}_{mono,wall_unix}_ns stamps).  No Modal,
no network, no sleeps, no asyncio.

Runnable from the repo root via:
    python -m unittest tests.test_batch_a_acceptance -v
"""

from __future__ import annotations

import copy
import unittest
from typing import Any

from tools.batch_a_acceptance import render_acceptance_block, validate_batch_a


def _make_event(name: str, wall_ns: int = 0, mono_ns: int = 0,
                metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Same event shape as the repo's trace events / existing fixtures."""
    return {"name": name, "wall_unix_ns": wall_ns, "monotonic_ns": mono_ns,
            "metadata": dict(metadata or {})}


def _make_all_pass_artifact() -> dict[str, Any]:
    """A run_<i>.json-shaped artifact that satisfies every Batch-A gate.

    Mirrors the actual runtime emissions for the snapshot-unet-absent
    fast-disk deployment shape:
    - unet_execution_plan_receipt_schedule fires at plan receipt, BEFORE the
      first status yield (run_plan_first_status_yield);
    - the later binding-block schedule is a single-flight no-op
      (unet_execution_schedule reason=already_prepared);
    - the real H2D evidence is unet_fast_disk_complete (to_wall_ms > 0); the
      unet_h2d page-fault delta belongs to the VAE lane and must not count;
    - the models reload decision rides a models_reload_decision trace event;
    - identity_matches is a dict, identity_mismatch_reasons is [] on healthy;
    - per-node rows carry start_perf_ns/end_perf_ns/duration_ms;
    - terminal stamps are terminal_cleanup_{start,end}_mono_ns at result
      top level (same-process monotonic pair).
    """
    events = [
        _make_event("unet_execution_plan_receipt_schedule", mono_ns=800,
                    metadata={"request_id": "req-1",
                              "unet_identity_hash": "0fdc3f933123160f",
                              "snapshot_unet_absent": 1, "snapshot_active": 1,
                              "role_compatible": 1}),
        _make_event("run_plan_first_status_yield", mono_ns=1000),
        _make_event("models_reload_decision", mono_ns=1100,
                    metadata={"decision": "skipped_generation_match",
                              "reason": "exact_match", "callback_called": 0,
                              "check_ms": 0.01}),
        _make_event("run_plan_method_entry_gap", mono_ns=1200,
                    metadata={
                        "identity_matches": {
                            "restored_instance_id": True,
                            "restore_session_id": True,
                            "modal_task_id": True,
                            "pid": True,
                            "boot_id": True,
                            "hostname": True,
                        },
                        "identity_mismatch_reasons": [],
                        "same_process": True,
                        "restore_return_to_method_first_line_ms": 15.6,
                    }),
        _make_event("unet_execution_schedule", mono_ns=1300,
                    metadata={"request_id": "req-1", "reason": "already_prepared",
                              "unet_future_done": False}),
        _make_event("unet_fast_disk_bind_start", mono_ns=2000,
                    metadata={"decision": "bind", "bind_assign": True}),
        _make_event("unet_fast_disk_bind_end", mono_ns=2050,
                    metadata={"decision": "bind", "bind_wall_ms": 50.0}),
        _make_event("unet_fast_disk_complete", mono_ns=2500,
                    metadata={"decision": "complete", "to_wall_ms": 2500.0,
                              "to_device_ms": 2495.0,
                              "h2d_classification": "COPY_INTERVAL_SLOW"}),
        # VAE lane page-fault delta: must NOT count as UNET H2D evidence.
        _make_event("unet_h2d", mono_ns=2600,
                    metadata={"lane": "VAE", "duration_ms": 762.0,
                              "caller_classification": "restore_vae_preparation"}),
        _make_event("host_hardware_fingerprint", mono_ns=3000,
                    metadata={"probe_wall_ms": 6.0}),
        _make_event("host_resource_snapshot", mono_ns=3100,
                    metadata={"probe_wall_ms": 4.0}),
    ]
    return {
        "identity": {
            "restored_instance_id": "inst_A",
            "restore_count": 1,
            "request_count": 1,
        },
        "waterfall": {
            "reconciliation_ms": 12.3,
            "reconciliation_status": "OK",
            "diagnostic_status": "COMPLETE",
            "total_wall_ms": 5000,
        },
        "waterfall_local": {
            "reconciliation_ms": 12.3,
            "reconciliation_status": "OK",
            "diagnostic_status": "COMPLETE",
            "total_wall_ms": 5000,
        },
        "result": {
            "trace": {
                "events": events,
                "metadata": {
                    "_execution_unet_scheduled": 1,
                    "_execution_unet_gate": 1,
                },
            },
            "_restore_timing": {
                "reload_models_invoked": False,
                "reload_models_reason": "not_invoked",
                "reload_models_ms": 0.0,
            },
            "pre_sampler_structured_report": {
                "per_node_timings": [
                    {"node_id": "3", "class_type": "CLIPTextEncode",
                     "duration_ms": 20.0, "start_perf_ns": 100000000,
                     "end_perf_ns": 120000000, "pass_outcome": "COMPLETE"},
                ],
                "active_read_records": [
                    {"loader_type": "", "owner": "graph_loader",
                     "wall_ms": 1477.09},
                ],
            },
            "terminal_cleanup_start_mono_ns": 10000000000,
            "terminal_cleanup_end_mono_ns": 10015500000,
            "host_telemetry_total_probe_wall_ms": 10.0,
        },
        "timing": {},
    }


def _artifact() -> dict[str, Any]:
    """Deep-copied all-pass artifact for mutation in failing tests."""
    return copy.deepcopy(_make_all_pass_artifact())


class TestBatchAAcceptanceAllPass(unittest.TestCase):
    def test_all_pass(self):
        res = validate_batch_a(_make_all_pass_artifact())
        self.assertTrue(res.passed)
        self.assertEqual(res.fresh, "YES")
        self.assertTrue(res.fresh_ok)
        self.assertTrue(res.status_ok)
        self.assertTrue(res.reconciliation_ok)
        rec_ms = res.reconciliation_ms
        self.assertIsNotNone(rec_ms)
        self.assertEqual(rec_ms, 12.3)
        self.assertTrue(res.g1_early_schedule)
        self.assertEqual(res.unet_read_count, 1)
        self.assertTrue(res.unet_read_ok)
        self.assertEqual(res.unet_bind_count, 1)
        self.assertTrue(res.unet_bind_ok)
        self.assertEqual(res.unet_h2d_count, 1)
        self.assertTrue(res.unet_h2d_ok)
        self.assertTrue(res.identity_match_ok)
        self.assertTrue(res.no_duplicate_ok)
        self.assertEqual(res.models_reload_decision, "skipped_generation_match")
        self.assertTrue(res.models_reload_decision_ok)
        self.assertEqual(res.models_reload_remote_calls, 0)
        self.assertTrue(res.models_reload_remote_ok)
        self.assertTrue(res.node_timing_ok)
        self.assertEqual(res.node_timing_rows, 1)
        cleanup_ms = res.terminal_cleanup_ms
        self.assertIsNotNone(cleanup_ms)
        self.assertEqual(cleanup_ms, 15.5)
        self.assertTrue(res.terminal_ok)
        self.assertIsNone(res.transport_after_cleanup_ms)
        self.assertFalse(res.transport_claimed)
        probe_ms = res.host_telemetry_probe_ms
        self.assertIsNotNone(probe_ms)
        self.assertEqual(probe_ms, 10.0)
        self.assertTrue(res.host_telemetry_ok)
        self.assertFalse(res.slow_forensic_triggered)
        self.assertTrue(res.slow_forensic_ok)
        self.assertTrue(res.h2d_below_slow_threshold)
        self.assertTrue(all(c.ok for c in res.checks))


class TestBatchAAcceptanceG1(unittest.TestCase):
    def test_duplicate_unet_event_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"].append(
            _make_event("unet_fast_disk_complete", mono_ns=2700,
                        metadata={"decision": "complete", "to_wall_ms": 2400.0,
                                  "to_device_ms": 2395.0})
        )
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertNotEqual(res.unet_h2d_count, 1)
        self.assertFalse(res.unet_h2d_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("g1_unet_h2d_count", failing)

    def test_missing_plan_marker_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"] = [
            e for e in art["result"]["trace"]["events"]
            if e["name"] != "run_plan_first_status_yield"
        ]
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("g1_plan_before_schedule", failing)

    def test_schedule_after_status_yield_fails(self):
        art = _artifact()
        for e in art["result"]["trace"]["events"]:
            if e["name"] == "unet_execution_plan_receipt_schedule":
                e["monotonic_ns"] = 9000
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("g1_plan_before_schedule", failing)

    def test_vae_lane_h2d_does_not_count(self):
        # The fixture already carries a VAE-lane unet_h2d event; the UNET H2D
        # count must remain 1 (evidence: unet_fast_disk_complete).
        art = _artifact()
        res = validate_batch_a(art)
        self.assertEqual(res.unet_h2d_count, 1)
        self.assertTrue(res.unet_h2d_ok)


class TestBatchAAcceptanceModelsReload(unittest.TestCase):
    def test_missing_reload_skip_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"] = [
            e for e in art["result"]["trace"]["events"]
            if e["name"] != "models_reload_decision"
        ]
        art["result"]["_restore_timing"].pop("reload_models_invoked", None)
        art["result"]["_restore_timing"].pop("reload_models_reason", None)
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertIsNone(res.models_reload_decision)
        self.assertFalse(res.models_reload_decision_ok)

    def test_wrong_reload_decision_fails(self):
        art = _artifact()
        for e in art["result"]["trace"]["events"]:
            if e["name"] == "models_reload_decision":
                e["metadata"]["decision"] = "reloaded_generation_mismatch"
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.models_reload_decision_ok)

    def test_reload_remote_calls_nonzero_fails(self):
        art = _artifact()
        art["result"]["_restore_timing"]["reload_models_count"] = 1
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.models_reload_remote_calls, 1)
        self.assertFalse(res.models_reload_remote_ok)


class TestBatchAAcceptanceNodeTimestamps(unittest.TestCase):
    def test_missing_node_timestamp_fails(self):
        art = _artifact()
        art["result"]["pre_sampler_structured_report"]["per_node_timings"] = [
            {"node_id": "3", "class_type": "CLIPTextEncode", "duration_ms": 20.0},
        ]
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.node_timing_rows, 0)
        self.assertFalse(res.node_timing_ok)

    def test_node_end_before_start_fails(self):
        art = _artifact()
        art["result"]["pre_sampler_structured_report"]["per_node_timings"] = [
            {"node_id": "3", "class_type": "CLIPTextEncode",
             "duration_ms": 20.0, "start_perf_ns": 120000000,
             "end_perf_ns": 100000000, "pass_outcome": "COMPLETE"},
        ]
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.node_timing_ok)

    def test_missing_node_timings_list_fails(self):
        art = _artifact()
        art["result"]["pre_sampler_structured_report"].pop("per_node_timings", None)
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.node_timing_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("node_timestamps", failing)


class TestBatchAAcceptanceTelemetry(unittest.TestCase):
    def test_telemetry_over_20ms_fails(self):
        art = _artifact()
        art["result"]["host_telemetry_total_probe_wall_ms"] = 21.0
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertIsNotNone(res.host_telemetry_probe_ms)
        self.assertEqual(res.host_telemetry_probe_ms, 21.0)
        self.assertFalse(res.host_telemetry_ok)

    def test_telemetry_probe_sum_fallback(self):
        art = _artifact()
        art["result"].pop("host_telemetry_total_probe_wall_ms", None)
        res = validate_batch_a(art)
        # 6.0 (fingerprint) + 4.0 (resource_snapshot) = 10.0, still under cap
        self.assertIsNotNone(res.host_telemetry_probe_ms)
        self.assertEqual(res.host_telemetry_probe_ms, 10.0)
        self.assertTrue(res.host_telemetry_ok)
        self.assertTrue(res.passed)

    def test_slow_trigger_on_healthy_run_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"].append(
            _make_event("host_forensic_slow_h2d", mono_ns=3200,
                        metadata={"probe_wall_ms": 3.0})
        )
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertTrue(res.slow_forensic_triggered)
        self.assertFalse(res.slow_forensic_ok)

    def test_slow_h2d_duration_flagged(self):
        art = _artifact()
        for e in art["result"]["trace"]["events"]:
            if e["name"] == "unet_fast_disk_complete":
                e["metadata"]["to_wall_ms"] = 5500.0
                e["metadata"]["to_device_ms"] = 5490.0
        res = validate_batch_a(art)
        # informational field only: still one H2D op, gates otherwise pass
        self.assertIs(res.h2d_below_slow_threshold, False)
        self.assertTrue(res.passed)


class TestBatchAAcceptanceReconciliation(unittest.TestCase):
    def test_reconciliation_over_50ms_fails(self):
        art = _artifact()
        art["waterfall"]["reconciliation_ms"] = 60.0
        art["waterfall_local"]["reconciliation_ms"] = 60.0
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertIsNotNone(res.reconciliation_ms)
        self.assertEqual(res.reconciliation_ms, 60.0)
        self.assertFalse(res.reconciliation_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("reconciliation", failing)

    def test_reconciliation_missing_fails(self):
        art = _artifact()
        art["waterfall_local"].pop("reconciliation_ms", None)
        art["waterfall"].pop("reconciliation_ms", None)
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertIsNone(res.reconciliation_ms)
        self.assertFalse(res.reconciliation_ok)


class TestBatchAAcceptanceIdentity(unittest.TestCase):
    def test_not_fresh_fails(self):
        art = _artifact()
        art["identity"]["restore_count"] = 2
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.fresh, "NO")
        self.assertFalse(res.fresh_ok)

    def test_identity_mismatch_reason_fails(self):
        art = _artifact()
        for e in art["result"]["trace"]["events"]:
            if e["name"] == "run_plan_method_entry_gap":
                e["metadata"]["identity_mismatch_reasons"] = ["hostname differs"]
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.identity_match_ok)

    def test_identity_marker_absent_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"] = [
            e for e in art["result"]["trace"]["events"]
            if e["name"] != "run_plan_method_entry_gap"
        ]
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("g1_identity_match", failing)


class TestBatchAAcceptanceTerminal(unittest.TestCase):
    def test_missing_terminal_stamps_fails(self):
        art = _artifact()
        art["result"].pop("terminal_cleanup_start_mono_ns", None)
        art["result"].pop("terminal_cleanup_end_mono_ns", None)
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.terminal_ok)
        self.assertIsNone(res.terminal_cleanup_ms)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("terminal_cleanup", failing)

    def test_terminal_end_before_start_fails(self):
        art = _artifact()
        art["result"]["terminal_cleanup_start_mono_ns"] = 10015500000
        art["result"]["terminal_cleanup_end_mono_ns"] = 10000000000
        res = validate_batch_a(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.terminal_ok)


class TestBatchAAcceptanceRender(unittest.TestCase):
    def test_render_block_pass_contains(self):
        res = validate_batch_a(_make_all_pass_artifact())
        block = render_acceptance_block(res)
        self.assertIn("BATCH A ACCEPTANCE", block)
        self.assertIn("OVERALL: PASS", block)
        self.assertIn("Reconciliation: 12.3 ms", block)
        self.assertIn("Host telemetry overhead: 10.0 ms", block)

    def test_render_block_fail_lists_checks(self):
        art = _artifact()
        art["result"].pop("terminal_cleanup_start_mono_ns", None)
        art["result"].pop("terminal_cleanup_end_mono_ns", None)
        res = validate_batch_a(art)
        block = render_acceptance_block(res)
        self.assertIn("FAILED CHECKS:", block)
        self.assertIn("terminal_cleanup: ", block)
        self.assertIn("OVERALL: FAIL", block)


class TestBatchAAcceptanceFile(unittest.TestCase):
    def test_validate_file_roundtrip(self):
        import json
        import tempfile
        import os
        from tools.batch_a_acceptance import validate_batch_a_file

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run_0.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_make_all_pass_artifact(), fh)
            res = validate_batch_a_file(path)
        self.assertTrue(res.passed)
        self.assertEqual(res.unet_read_count, 1)


if __name__ == "__main__":
    unittest.main()
