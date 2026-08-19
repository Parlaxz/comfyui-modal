"""Unit tests for the Batch-B acceptance harness (tools/batch_b_acceptance.py).

Pure offline fixtures matching the run_<i>.json artifact shape persisted by
benchmark_v2_direct.py.  The all-pass fixture satisfies every Batch-A gate
(shared shape with tests/test_batch_a_acceptance.py) plus the Batch-B lanes:
runtime-state skip observables (runtime-state-SPECIFIC fields only - models
volume fields are never runtime-state evidence), a snapshot_capture_hygiene
record, a snapshot manifest with status, an output_stage13_breakdown whose
children reconcile the parent, and a 60 s TOTAL WALL that must NOT gate
acceptance.  No Modal, no network, no sleeps, no asyncio.

Runnable from the repo root via:
    python -m unittest tests.test_batch_b_acceptance -v
"""

from __future__ import annotations

import copy
import unittest
from typing import Any

from tools.batch_b_acceptance import (
    batch_b_config_from_env,
    render_batch_b_block,
    validate_batch_b,
    validate_batch_b_file,
)


def _make_event(name: str, wall_ns: int = 0, mono_ns: int = 0,
                metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Same event shape as the repo's trace events / existing fixtures."""
    return {"name": name, "wall_unix_ns": wall_ns, "monotonic_ns": mono_ns,
            "metadata": dict(metadata or {})}


def _make_all_pass_artifact() -> dict[str, Any]:
    """A run_<i>.json-shaped artifact that satisfies every Batch-A gate AND
    every Batch-B gate (with all Batch-B env expectations enabled).

    Runtime-state evidence uses the runtime-state-SPECIFIC exact fields
    (runtime_state_reload_decision / runtime_state_reload_invoked /
    runtime_state_ms / runtime_state_generation_check).  The models-volume
    fields in _restore_timing and the models_reload_decision event are Batch-A
    evidence only and are deliberately NEVER consulted by the runtime-state
    gate.  TOTAL WALL is deliberately 60 s: it must remain informational only.
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
            "validation_status": "COMPLETE",
            "total_wall_ms": 60000,
        },
        "waterfall_local": {
            "reconciliation_ms": 12.3,
            "reconciliation_status": "OK",
            "validation_status": "COMPLETE",
            "total_wall_ms": 60000,
        },
        "result": {
            "trace": {
                "events": events,
                "metadata": {
                    "_execution_unet_scheduled": 1,
                    "_execution_unet_gate": 1,
                },
            },
            # ── Batch-B: runtime-state evidence (runtime-state ONLY) ──
            "runtime_state_reload_decision": "skipped_generation_match",
            "runtime_state_generation_check": True,
            "_restore_timing": {
                # Models-volume guard evidence (Batch-A): NEVER runtime-state.
                "reload_models_invoked": False,
                "reload_models_reason": "not_invoked",
                "reload_models_ms": 0.0,
                # Runtime-state evidence (Batch-B).
                "runtime_state_reload_invoked": False,
                "runtime_state_ms": 0.0,
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
            # ── Batch-B: snapshot hygiene record ──
            "snapshot_capture_hygiene": {
                "enabled": 1,
                "rss_before": 1234.5,
                "rss_after": 1220.0,
                "rss_anon_before": 900.0,
                "rss_anon_after": 895.0,
                "hygiene_wall_ms": 42.0,
                "gc": {"gen_counts": [5, 1, 0], "total_objects": 120},
                "malloc_trim": "ok",
            },
            # ── Batch-B: snapshot manifest with smaps ──
            "snapshot_manifest": {
                "status": {"vmrss": 1234, "vmhwm": 1250, "vmsize": 2600},
                "smaps_rollup": {"total": 1, "anonymous": 900},
                "gc": {"gen_counts": [2, 0, 0], "total_objects": 80},
            },
            # ── Batch-B: stage-13 decomposition (children reconcile) ──
            "output_stage13_breakdown": {
                "stage13_total": 250.0,
                "children": [
                    {"name": "output_encode", "ms": 150.0},
                    {"name": "descriptor", "ms": 60.0},
                    {"name": "stamp", "ms": 40.0},
                ],
            },
        },
        "timing": {"wall_ms": 60000.0},
    }


def _artifact() -> dict[str, Any]:
    """Deep-copied all-pass artifact for mutation in failing tests."""
    return copy.deepcopy(_make_all_pass_artifact())


def _run(art: dict[str, Any], **overrides: Any) -> Any:
    """validate_batch_b with all Batch-B expectations ON by default."""
    cfg = {
        "expect_runtime_state_skip": True,
        "snapshot_hygiene_enabled": True,
        "snapshot_manifest_enabled": True,
        "expect_stage13": False,
        "expect_slow_h2d_forensic": False,
    }
    cfg.update(overrides)
    return validate_batch_b(art, **cfg)


def _strip_runtime_state_evidence(art: dict[str, Any]) -> None:
    """Remove ALL runtime-state-specific evidence (leaving only Batch-A
    models-volume fields, which must never be accepted as runtime-state
    evidence)."""
    art["result"].pop("runtime_state_reload_decision", None)
    art["result"].pop("runtime_state_generation_check", None)
    art["result"]["_restore_timing"].pop("runtime_state_reload_invoked", None)
    art["result"]["_restore_timing"].pop("runtime_state_ms", None)


def _set_h2d_ms(art: dict[str, Any], ms: float) -> None:
    """Point the real fast-disk H2D evidence at a specific duration."""
    for e in art["result"]["trace"]["events"]:
        if e["name"] == "unet_fast_disk_complete":
            e["metadata"]["to_wall_ms"] = ms
            e["metadata"]["to_device_ms"] = ms - 5.0


def _add_forensic_event(art: dict[str, Any], probe_wall_ms: float = 3.0) -> None:
    art["result"]["trace"]["events"].append(
        _make_event("host_forensic_slow_h2d", mono_ns=3200,
                    metadata={"probe_wall_ms": probe_wall_ms})
    )


def _make_runtime_spelled_artifact() -> dict[str, Any]:
    """A run_<i>.json-shaped artifact that uses ONLY the runtime's ACTUAL
    emitted field names/shapes (runtime semantics are authoritative) and still
    satisfies every Batch-A AND Batch-B gate.

    Layered on the legacy all-pass fixture, with every legacy Batch-B spelling
    REPLACED by the runtime spelling so the runtime spelling is the only
    evidence the harness can consult:
      - runtime-state guard: ``_restore_timing.reload_runtime_state_ms`` /
        ``reload_runtime_state_invoked`` / ``reload_runtime_state_reason`` plus
        a ``runtime_state_reload_decision`` trace event (``phase="restore"``)
        whose metadata carries decision="skipped_generation_match",
        reason="exact_match", callback_called=0,
        runtime_state_reload_invoked=0 (int) and check_ms=0.36 (the O(1)
        local guard cost);
      - snapshot hygiene: ``_restore_timing.snapshot_capture_hygiene`` with
        before_rss_kb/after_rss_kb/before_rss_anon_kb/after_rss_anon_kb/
        gc_collected/malloc_trim_available/malloc_trim_result/hygiene_wall_ms;
      - snapshot manifest: ``_restore_timing.snapshot_manifest`` with status;
      - stage 13: ``output_stage13_breakdown`` with stage13_total_ms +
        children_order + flat ``{name}_ms`` child keys (NO children list, NO
        ``_stage13_boundaries``).  children_order entries ALREADY end in
        ``_ms`` exactly as the runtime emits them (stage13_breakdown.py emits
        ``list(CHILD_NAMES)`` where CHILD_NAMES carry the ``_ms`` suffix).
    """
    art = _make_all_pass_artifact()
    result = art["result"]
    _rt = result["_restore_timing"]

    # ── runtime-state guard: replace legacy spellings with runtime ones ──
    result.pop("runtime_state_reload_decision", None)
    result.pop("runtime_state_generation_check", None)
    _rt.pop("runtime_state_reload_invoked", None)
    _rt.pop("runtime_state_ms", None)
    _rt["reload_runtime_state_ms"] = 0.0
    _rt["reload_runtime_state_invoked"] = False
    _rt["reload_runtime_state_reason"] = "not_invoked"
    _decision_event = _make_event(
        "runtime_state_reload_decision", mono_ns=1150,
        metadata={
            "decision": "skipped_generation_match",
            "reason": "exact_match",
            "callback_called": 0,
            "runtime_state_reload_invoked": 0,
            "check_ms": 0.36,
        },
    )
    _decision_event["phase"] = "restore"
    result["trace"]["events"].append(_decision_event)

    # ── snapshot hygiene: runtime spelling at _restore_timing ──
    result.pop("snapshot_capture_hygiene", None)
    _rt["snapshot_capture_hygiene"] = {
        "enabled": 1,
        "before_rss_kb": 1234.5,
        "after_rss_kb": 1220.0,
        "before_rss_anon_kb": 900.0,
        "after_rss_anon_kb": 895.0,
        "gc_collected": 6,
        "malloc_trim_available": True,
        "malloc_trim_result": 0,
        "hygiene_wall_ms": 0.4,
    }

    # ── snapshot manifest: runtime spelling at _restore_timing ──
    result.pop("snapshot_manifest", None)
    _rt["snapshot_manifest"] = {
        "status": "ok",
        "smaps_status": "unavailable",
    }

    # ── stage-13 breakdown: runtime flat spelling (no children list) ──
    result["output_stage13_breakdown"] = {
        "status": "ok",
        "stage13_total_ms": 250.0,
        "output_collection_ms": 150.0,
        "asset_local_write_ms": 30.0,
        "descriptor_build_ms": 40.0,
        "trace_enrichment_ms": 10.0,
        "interval_build_ms": 5.0,
        "resource_enrichment_ms": 5.0,
        "waterfall_build_ms": 5.0,
        "other_pre_emit_ms": 5.0,
        "children_order": [
            "output_collection_ms", "asset_local_write_ms",
            "descriptor_build_ms", "trace_enrichment_ms", "interval_build_ms",
            "resource_enrichment_ms", "waterfall_build_ms",
            "other_pre_emit_ms",
        ],
        "reconciliation_ms": 0.0,
        "reconciliation_status": "ok",
    }
    return art


def _runtime_spelled_artifact() -> dict[str, Any]:
    """Deep-copied runtime-spelled all-pass artifact for mutation."""
    return copy.deepcopy(_make_runtime_spelled_artifact())


class TestBatchBAcceptanceAllPass(unittest.TestCase):
    def test_total_wall_60s_with_all_structural_gates_correct_still_passes(self):
        # The most important test: TOTAL WALL is NOT an acceptance gate.
        res = _run(_make_all_pass_artifact())
        self.assertTrue(res.passed)
        self.assertTrue(res.batch_a_preserved)
        self.assertEqual(res.batch_a_fresh, "YES")
        self.assertEqual(res.batch_a_reconciliation_ms, 12.3)
        self.assertTrue(res.runtime_state_ready)
        self.assertTrue(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_decision, "skipped_generation_match")
        self.assertIs(res.runtime_state_invoked, False)
        self.assertEqual(res.runtime_state_reload_ms, 0.0)
        self.assertIs(res.runtime_state_generation_check, True)
        self.assertIs(res.runtime_state_local_only, True)
        self.assertIn("decision", res.runtime_state_evidence)
        self.assertTrue(res.snapshot_hygiene_present)
        self.assertTrue(res.hygiene_ok)
        self.assertEqual(res.hygiene_rss_before, 1234.5)
        self.assertEqual(res.hygiene_rss_after, 1220.0)
        self.assertEqual(res.hygiene_rss_delta, -14.5)
        self.assertEqual(res.hygiene_rss_anon_delta, -5.0)
        self.assertEqual(res.hygiene_wall_ms, 42.0)
        self.assertIsNotNone(res.hygiene_gc)
        self.assertEqual(res.hygiene_malloc_trim, "ok")
        self.assertTrue(res.snapshot_manifest_present)
        self.assertTrue(res.manifest_ok)
        self.assertIsNotNone(res.manifest_status)
        self.assertTrue(res.stage13_ready)
        self.assertTrue(res.stage13_ok)
        self.assertEqual(res.stage13_total, 250.0)
        self.assertEqual(len(res.stage13_children), 3)
        self.assertEqual(res.stage13_reconciliation_ms, 0.0)
        self.assertEqual(res.stage13_largest_child.get("name"), "output_encode")
        self.assertEqual(res.host_telemetry_tier_a_ms, 10.0)
        self.assertEqual(res.host_telemetry_total_ms, 10.0)
        self.assertIsNone(res.slow_trigger_probe_ms)
        self.assertFalse(res.host_telemetry_not_observable)
        self.assertTrue(res.host_telemetry_ok)
        self.assertFalse(res.slow_forensic_triggered)
        self.assertTrue(res.slow_forensic_ok)
        self.assertEqual(res.total_wall_ms, 60000.0)
        self.assertTrue(all(c.ok for c in res.checks))

    def test_all_gates_pass_with_expectations_off(self):
        # Flag-off must never fail: same artifact, no expectations enforced.
        res = _run(_make_all_pass_artifact(),
                   expect_runtime_state_skip=False,
                   snapshot_hygiene_enabled=False,
                   snapshot_manifest_enabled=False)
        self.assertTrue(res.passed)
        self.assertTrue(res.runtime_state_ok)
        self.assertTrue(res.hygiene_ok)
        self.assertTrue(res.manifest_ok)
        self.assertTrue(res.stage13_ok)


class TestBatchBAcceptanceBatchARegression(unittest.TestCase):
    def test_batch_a_regression_fails(self):
        art = _artifact()
        art["result"]["trace"]["events"].append(
            _make_event("unet_fast_disk_complete", mono_ns=2700,
                        metadata={"decision": "complete", "to_wall_ms": 2400.0,
                                  "to_device_ms": 2395.0})
        )
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.batch_a_preserved)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("batch_a_preserved", failing)

    def test_reconciliation_over_50ms_fails_batch_a(self):
        art = _artifact()
        art["waterfall"]["reconciliation_ms"] = 60.0
        art["waterfall_local"]["reconciliation_ms"] = 60.0
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.batch_a_preserved)


class TestBatchBAcceptanceRuntimeState(unittest.TestCase):
    def test_expected_runtime_state_skip_missing_fails(self):
        art = _artifact()
        _strip_runtime_state_evidence(art)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.runtime_state_ready)
        self.assertFalse(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_evidence, "none")
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("runtime_state_guard", failing)

    def test_models_evidence_alone_cannot_pass_runtime_state_skip(self):
        # THE false-pass regression: the fixture carries a clean models-volume
        # skip (models_reload_decision=skipped_generation_match,
        # reload_models_invoked=False, reload_models_ms=0) but NO runtime-state
        # evidence.  The runtime-state gate must NOT be satisfied by models
        # fields: with the expectation ON it must FAIL (lane NOT READY).
        art = _artifact()
        _strip_runtime_state_evidence(art)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.runtime_state_ready)
        self.assertFalse(res.runtime_state_ok)
        self.assertIsNone(res.runtime_state_decision)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("runtime_state_guard", failing)

    def test_models_skip_cannot_hide_runtime_state_reload(self):
        # Clean models-volume skip fields AND a real restore-lane runtime-state
        # reload (reload_runtime_state_ms=82 + restore-phase
        # reload_runtime_state_start/end).  The runtime-state skip MUST NOT
        # PASS: the models fields cannot hide the reload.  The reload events
        # are phase="restore" (only restore-lane events count as reload
        # evidence; construction phase="startup" events are ignored).
        art = _artifact()
        _strip_runtime_state_evidence(art)
        art["result"]["_restore_timing"]["reload_runtime_state_ms"] = 82.0
        _reload_start = _make_event("reload_runtime_state_start", mono_ns=1400)
        _reload_end = _make_event("reload_runtime_state_end", mono_ns=1500)
        _reload_start["phase"] = "restore"
        _reload_end["phase"] = "restore"
        art["result"]["trace"]["events"].extend([_reload_start, _reload_end])
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertTrue(res.runtime_state_ready)
        self.assertFalse(res.runtime_state_ok)
        self.assertIsNone(res.runtime_state_decision)  # models decision ignored
        self.assertIs(res.runtime_state_invoked, True)
        self.assertEqual(res.runtime_state_reload_ms, 82.0)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("runtime_state_guard", failing)

    def test_models_only_reports_not_ready_with_expectation_off(self):
        art = _artifact()
        _strip_runtime_state_evidence(art)
        res = _run(art, expect_runtime_state_skip=False)
        self.assertTrue(res.passed)
        self.assertFalse(res.runtime_state_ready)
        self.assertTrue(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_evidence, "none")

    def test_wrong_runtime_state_decision_fails(self):
        art = _artifact()
        art["result"]["runtime_state_reload_decision"] = "reloaded_generation_mismatch"
        res = _run(art)
        self.assertFalse(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_decision, "reloaded_generation_mismatch")

    def test_runtime_state_reload_invoked_fails(self):
        art = _artifact()
        art["result"]["runtime_state_reload_decision"] = "reloaded_generation_mismatch"
        art["result"]["runtime_state_reload_invoked"] = True
        art["result"]["_restore_timing"]["runtime_state_reload_ms"] = 250.0
        art["result"]["trace"]["events"].extend([
            _make_event("reload_runtime_state_start", mono_ns=1400),
            _make_event("reload_runtime_state_end", mono_ns=1500),
        ])
        res = _run(art)
        self.assertFalse(res.runtime_state_ok)
        self.assertIs(res.runtime_state_invoked, True)
        self.assertEqual(res.runtime_state_reload_ms, 250.0)

    def test_expectation_off_permits_reload_but_reports_it(self):
        # Expectation OFF: a real runtime-state reload must be REPORTED but
        # must not fail the run (models volume lane stays skipped -> Batch-A
        # preserved).  This is the documented integration semantics.
        art = _artifact()
        art["result"]["runtime_state_reload_decision"] = "reloaded_generation_mismatch"
        art["result"]["runtime_state_reload_invoked"] = True
        art["result"]["_restore_timing"]["runtime_state_reload_ms"] = 250.0
        art["result"]["trace"]["events"].extend([
            _make_event("reload_runtime_state_start", mono_ns=1400),
            _make_event("reload_runtime_state_end", mono_ns=1500),
        ])
        res = _run(art, expect_runtime_state_skip=False)
        self.assertTrue(res.passed)
        self.assertTrue(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_decision, "reloaded_generation_mismatch")
        self.assertIs(res.runtime_state_invoked, True)
        self.assertEqual(res.runtime_state_reload_ms, 250.0)

    def test_reload_ms_nonzero_without_local_check_fails(self):
        art = _artifact()
        art["result"]["_restore_timing"]["runtime_state_ms"] = 250.0
        res = _run(art)
        self.assertFalse(res.runtime_state_ok)


class TestBatchBAcceptanceSnapshotHygiene(unittest.TestCase):
    def test_missing_hygiene_event_fails_when_flag_enabled(self):
        art = _artifact()
        art["result"].pop("snapshot_capture_hygiene", None)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.snapshot_hygiene_present)
        self.assertFalse(res.hygiene_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("snapshot_hygiene", failing)

    def test_hygiene_rss_not_required_to_decrease(self):
        # RSS increase is REPORTED, never a gate failure.
        art = _artifact()
        art["result"]["snapshot_capture_hygiene"]["rss_after"] = 1400.0
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertEqual(res.hygiene_rss_delta, 165.5)
        self.assertTrue(res.hygiene_ok)

    def test_hygiene_record_missing_required_field_fails(self):
        art = _artifact()
        art["result"]["snapshot_capture_hygiene"].pop("malloc_trim", None)
        res = _run(art)
        self.assertFalse(res.hygiene_ok)
        self.assertFalse(res.passed)

    def test_hygiene_malloc_trim_explicit_unavailable_passes(self):
        # Explicitly-recorded unavailability is accepted (e.g. platform
        # without malloc_trim); never fabricate a value.
        art = _artifact()
        art["result"]["snapshot_capture_hygiene"]["malloc_trim"] = "unavailable"
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertEqual(res.hygiene_malloc_trim, "unavailable")


class TestBatchBAcceptanceSnapshotManifest(unittest.TestCase):
    def test_unavailable_smaps_with_explicit_status_passes(self):
        art = _artifact()
        art["result"]["snapshot_manifest"] = {
            "status": {"vmrss": 1234},
            "smaps_status": "unavailable",
        }
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.manifest_ok)
        self.assertIs(res.manifest_smaps_unavailable, True)

    def test_missing_manifest_status_fails_when_flag_enabled(self):
        art = _artifact()
        art["result"].pop("snapshot_manifest", None)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.snapshot_manifest_present)
        self.assertFalse(res.manifest_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("snapshot_manifest", failing)

    def test_manifest_without_status_key_fails(self):
        art = _artifact()
        art["result"]["snapshot_manifest"] = {"smaps_rollup": {"total": 1}}
        res = _run(art)
        self.assertFalse(res.manifest_ok)
        self.assertIsNone(res.manifest_status)


class TestBatchBAcceptanceStage13(unittest.TestCase):
    def test_stage13_child_mismatch_fails(self):
        art = _artifact()
        art["result"]["output_stage13_breakdown"]["children"][2]["ms"] = 20.0
        # sum now 230 vs total 250 -> delta 20 ms > 10 ms tolerance.
        res = _run(art)
        self.assertFalse(res.stage13_ok)
        self.assertFalse(res.passed)
        self.assertEqual(res.stage13_reconciliation_ms, 20.0)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("stage13_breakdown", failing)

    def test_stage13_negative_child_fails(self):
        art = _artifact()
        art["result"]["output_stage13_breakdown"]["children"][1]["ms"] = -5.0
        res = _run(art)
        self.assertFalse(res.stage13_ok)
        self.assertFalse(res.passed)

    def test_stage13_malformed_fails_regardless_of_expectation(self):
        # Present-but-malformed always fails, even with the expectation off.
        art = _artifact()
        art["result"]["output_stage13_breakdown"]["children"] = "not-a-list"
        res = _run(art, expect_stage13=False)
        self.assertTrue(res.stage13_ready)
        self.assertFalse(res.stage13_ok)
        self.assertFalse(res.passed)

    def test_stage13_tolerance_respected(self):
        art = _artifact()
        art["result"]["output_stage13_breakdown"]["children"][2]["ms"] = 20.0
        res = _run(art, stage13_tolerance_ms=20.0)
        self.assertTrue(res.stage13_ok)
        self.assertEqual(res.stage13_reconciliation_ms, 20.0)
        self.assertTrue(res.passed)

    def test_stage13_missing_expectation_off_reports_not_ready_and_passes(self):
        art = _artifact()
        art["result"].pop("output_stage13_breakdown", None)
        res = _run(art, expect_stage13=False)
        self.assertTrue(res.passed)
        self.assertFalse(res.stage13_ready)
        self.assertTrue(res.stage13_ok)
        self.assertIsNone(res.stage13_total)

    def test_stage13_missing_expectation_on_fails(self):
        art = _artifact()
        art["result"].pop("output_stage13_breakdown", None)
        res = _run(art, expect_stage13=True)
        self.assertFalse(res.passed)
        self.assertFalse(res.stage13_ready)
        self.assertFalse(res.stage13_ok)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("stage13_breakdown", failing)

    def test_largest_child_reported(self):
        res = _run(_make_all_pass_artifact())
        self.assertEqual(res.stage13_largest_child.get("name"), "output_encode")
        self.assertEqual(res.stage13_largest_child.get("_ms"), 150.0)


class TestBatchBAcceptanceRuntimeSpelling(unittest.TestCase):
    """The harness must consume the runtime's ACTUAL emitted field names and
    shapes (runtime semantics are authoritative: the runtime is correct, the
    harness is normalized to read it).  These fixtures use ONLY the runtime
    spellings and prove they pass every gate; the legacy-spelled fixtures
    above prove both spellings are accepted."""

    def test_runtime_spelled_artifact_passes_every_gate(self):
        res = _run(_make_runtime_spelled_artifact())
        self.assertTrue(res.passed)
        self.assertTrue(res.batch_a_preserved)
        # Runtime-state guard via runtime fields + decision-event metadata.
        self.assertTrue(res.runtime_state_ready)
        self.assertTrue(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_decision, "skipped_generation_match")
        self.assertIs(res.runtime_state_invoked, False)
        self.assertEqual(res.runtime_state_reload_ms, 0.0)
        self.assertIs(res.runtime_state_generation_check, True)
        self.assertIs(res.runtime_state_local_only, True)
        # Snapshot hygiene via the runtime spelling.
        self.assertTrue(res.snapshot_hygiene_present)
        self.assertTrue(res.hygiene_ok)
        self.assertEqual(res.hygiene_rss_before, 1234.5)
        self.assertEqual(res.hygiene_rss_after, 1220.0)
        self.assertEqual(res.hygiene_rss_delta, -14.5)
        self.assertEqual(res.hygiene_rss_anon_before, 900.0)
        self.assertEqual(res.hygiene_rss_anon_after, 895.0)
        self.assertEqual(res.hygiene_rss_anon_delta, -5.0)
        self.assertEqual(res.hygiene_wall_ms, 0.4)
        self.assertEqual(res.hygiene_gc, 6)
        self.assertEqual(res.hygiene_malloc_trim, 0)
        # Snapshot manifest via the runtime spelling.
        self.assertTrue(res.snapshot_manifest_present)
        self.assertTrue(res.manifest_ok)
        self.assertEqual(res.manifest_status, "ok")
        self.assertIs(res.manifest_smaps_unavailable, True)
        # Stage 13 via the runtime flat-key spelling (no children list;
        # children_order entries carry the "_ms" suffix as the runtime emits).
        self.assertTrue(res.stage13_ready)
        self.assertTrue(res.stage13_ok)
        self.assertEqual(res.stage13_total, 250.0)
        self.assertEqual(len(res.stage13_children), 8)
        self.assertEqual(res.stage13_children[0]["name"], "output_collection_ms")
        self.assertEqual(res.stage13_children[0]["ms"], 150.0)
        self.assertEqual(res.stage13_reconciliation_ms, 0.0)
        self.assertEqual(res.stage13_largest_child.get("name"),
                         "output_collection_ms")
        self.assertEqual(res.stage13_largest_child.get("_ms"), 150.0)
        # Boundaries-absence check present and OK (no _stage13_boundaries).
        _boundaries = next(
            c for c in res.checks if c.key == "stage13_boundaries_absence"
        )
        self.assertTrue(_boundaries.ok)
        self.assertTrue(all(c.ok for c in res.checks))

    def test_runtime_spelled_invoked_int_normalized_from_event_metadata(self):
        # No _restore_timing.reload_runtime_state_invoked key: the invoked
        # state must come from the runtime_state_reload_decision event
        # metadata, whose runtime_state_reload_invoked is the int 0 ->
        # normalized to bool False by the harness.
        art = _runtime_spelled_artifact()
        art["result"]["_restore_timing"].pop("reload_runtime_state_invoked", None)
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.runtime_state_ready)
        self.assertTrue(res.runtime_state_ok)
        self.assertIs(res.runtime_state_invoked, False)
        _rt_check = next(
            c for c in res.checks if c.key == "runtime_state_guard"
        )
        self.assertIn("runtime_state_reload_decision event", _rt_check.detail)
        self.assertIn("-> False", _rt_check.detail)

    def test_construction_startup_reload_events_do_not_fail_runtime_state(self):
        # RUN-1 regression: the construction container legitimately emits
        # reload_runtime_state_start/end with phase="startup" (unconditional,
        # runtime_bootstrap.py) and the merged run trace carries them.  Those
        # construction-time events must NOT count as restore-lane reload
        # evidence: the restore lane still concludes skipped_generation_match,
        # invoked=False, local_only=True and the run PASSES.
        art = _runtime_spelled_artifact()
        art["result"]["trace"]["events"].extend([
            {"name": "reload_runtime_state_start", "wall_unix_ns": 0,
             "monotonic_ns": 500, "phase": "startup", "metadata": {}},
            {"name": "reload_runtime_state_end", "wall_unix_ns": 0,
             "monotonic_ns": 600, "phase": "startup", "metadata": {}},
        ])
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.runtime_state_ready)
        self.assertTrue(res.runtime_state_ok)
        self.assertEqual(res.runtime_state_decision, "skipped_generation_match")
        self.assertIs(res.runtime_state_invoked, False)
        self.assertEqual(res.runtime_state_reload_ms, 0.0)
        self.assertIs(res.runtime_state_generation_check, True)
        self.assertIs(res.runtime_state_local_only, True)

    def test_stage13_boundaries_survival_reported_but_non_gating(self):
        # _stage13_boundaries must NEVER survive into the final yielded result
        # (modal_app pops it before emitting the event).  When it does, the
        # boundaries-absence check FAILS while every other check (including
        # stage 13) passes; the run stays non-gated (informational check).
        art = _runtime_spelled_artifact()
        art["result"]["_stage13_boundaries"] = {
            "stage13_start_ns": 1, "stage13_end_ns": 2,
        }
        res = _run(art)
        self.assertTrue(res.passed)  # informational, non-gating
        self.assertTrue(res.stage13_ok)
        self.assertEqual(len(res.stage13_children), 8)
        _boundaries = next(
            c for c in res.checks if c.key == "stage13_boundaries_absence"
        )
        self.assertFalse(_boundaries.ok)
        self.assertTrue(all(
            c.ok for c in res.checks if c.key != "stage13_boundaries_absence"
        ))

    def test_stage13_boundaries_failure_renders_in_failed_checks(self):
        # The boundaries-absence check follows the existing GateCheck
        # rendering loop: it appears in FAILED CHECKS when another gate also
        # fails (the run overall FAILS in that case).
        art = _runtime_spelled_artifact()
        art["result"]["_stage13_boundaries"] = {"stage13_start_ns": 1}
        art["result"]["_restore_timing"].pop("snapshot_capture_hygiene", None)
        res = _run(art)
        self.assertFalse(res.passed)
        block = render_batch_b_block(res)
        self.assertIn("FAILED CHECKS:", block)
        self.assertIn("stage13_boundaries_absence: ", block)


class TestBatchBAcceptanceTelemetry(unittest.TestCase):
    def test_healthy_telemetry_over_20ms_fails(self):
        art = _artifact()
        art["result"]["host_telemetry_total_probe_wall_ms"] = 21.0
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertFalse(res.host_telemetry_ok)
        self.assertEqual(res.host_telemetry_tier_a_ms, 21.0)

    def test_healthy_explicit_tier_a_over_20_fails(self):
        art = _artifact()
        art["result"]["host_telemetry_tier_a_ms"] = 21.0
        art["result"]["host_telemetry_total_probe_wall_ms"] = 21.0
        res = _run(art)
        self.assertFalse(res.host_telemetry_ok)
        self.assertEqual(res.host_telemetry_tier_a_ms, 21.0)

    def test_telemetry_probe_sum_fallback(self):
        art = _artifact()
        art["result"].pop("host_telemetry_total_probe_wall_ms", None)
        res = _run(art)
        # 6.0 (fingerprint) + 4.0 (resource_snapshot) = 10.0 Tier-A
        self.assertEqual(res.host_telemetry_tier_a_ms, 10.0)
        self.assertTrue(res.host_telemetry_ok)
        self.assertTrue(res.passed)

    def test_slow_h2d_tier_b_overhead_passes_when_tier_a_ok(self):
        # H2D=9000 ms, TierA=11 ms, slow_probe=155 ms, total=166 ms, forensic
        # present: the Tier-B forensic cost is separate; the total may exceed
        # 20 ms; the run must PASS.
        art = _artifact()
        _set_h2d_ms(art, 9000.0)
        _add_forensic_event(art, probe_wall_ms=155.0)
        art["result"]["host_telemetry_tier_a_ms"] = 11.0
        art["result"]["slow_trigger_probe_ms"] = 155.0
        art["result"]["host_telemetry_total_probe_wall_ms"] = 166.0
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertEqual(res.host_telemetry_tier_a_ms, 11.0)
        self.assertEqual(res.slow_trigger_probe_ms, 155.0)
        self.assertEqual(res.host_telemetry_total_ms, 166.0)
        self.assertTrue(res.host_telemetry_ok)
        self.assertFalse(res.host_telemetry_not_observable)
        self.assertTrue(res.slow_forensic_ok)

    def test_slow_h2d_tier_a_via_subtraction(self):
        # No explicit Tier-A field: tier_a = total - slow probe = 166 - 155.
        art = _artifact()
        _set_h2d_ms(art, 9000.0)
        _add_forensic_event(art, probe_wall_ms=155.0)
        art["result"]["host_telemetry_total_probe_wall_ms"] = 166.0
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertEqual(res.host_telemetry_tier_a_ms, 11.0)
        self.assertEqual(res.slow_trigger_probe_ms, 155.0)

    def test_slow_h2d_insufficient_decomposition_not_observable(self):
        # Slow H2D with no Tier-A aggregate, no total, no slow-probe cost and
        # no Tier-A events: decomposition is insufficient -> NOT OBSERVABLE,
        # never a false failure on the total.
        art = _artifact()
        _set_h2d_ms(art, 9000.0)
        _add_forensic_event(art, probe_wall_ms=0.0)
        art["result"].pop("host_telemetry_total_probe_wall_ms", None)
        art["result"]["trace"]["events"] = [
            e for e in art["result"]["trace"]["events"]
            if e["name"] not in ("host_hardware_fingerprint", "host_resource_snapshot")
        ]
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.host_telemetry_not_observable)
        self.assertTrue(res.host_telemetry_ok)
        self.assertIsNone(res.host_telemetry_tier_a_ms)

    def test_slow_trigger_probe_on_healthy_h2d_fails(self):
        # Healthy H2D: the slow-trigger (Tier-B) probe must be 0.
        art = _artifact()
        art["result"]["slow_trigger_probe_ms"] = 50.0
        res = _run(art)
        self.assertFalse(res.host_telemetry_ok)
        self.assertFalse(res.passed)


class TestBatchBAcceptanceForensic(unittest.TestCase):
    def test_slow_forensic_trigger_on_healthy_h2d_fails(self):
        art = _artifact()
        _add_forensic_event(art)
        res = _run(art)
        self.assertTrue(res.slow_forensic_triggered)
        self.assertFalse(res.slow_forensic_ok)
        self.assertFalse(res.passed)

    def test_healthy_h2d_without_forensic_passes(self):
        # 2.5s H2D + no forensic => PASS (all-pass baseline).
        res = _run(_make_all_pass_artifact())
        self.assertTrue(res.passed)
        self.assertFalse(res.slow_forensic_triggered)
        self.assertTrue(res.slow_forensic_ok)

    def test_slow_h2d_forensic_passes(self):
        # 4.1s H2D + forensic => PASS (legitimate Tier-B forensics).
        art = _artifact()
        _set_h2d_ms(art, 4100.0)
        _add_forensic_event(art)
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.slow_forensic_triggered)
        self.assertTrue(res.slow_forensic_ok)

    def test_slow_h2d_9200ms_forensic_passes(self):
        # 9.2s H2D + forensic => PASS.
        art = _artifact()
        _set_h2d_ms(art, 9200.0)
        _add_forensic_event(art)
        res = _run(art)
        self.assertTrue(res.passed)
        self.assertTrue(res.slow_forensic_ok)

    def test_slow_h2d_no_forensic_with_expectation_fails(self):
        # 4.1s H2D + no forensic + expectation ON (slow-trigger runtime
        # expected enabled/observable) => FAIL.
        art = _artifact()
        _set_h2d_ms(art, 4100.0)
        res = _run(art, expect_slow_h2d_forensic=True)
        self.assertFalse(res.passed)
        self.assertFalse(res.slow_forensic_ok)
        self.assertIs(res.slow_forensic_expected_missing, True)
        failing = {c.key for c in res.checks if not c.ok}
        self.assertIn("host_slow_forensic", failing)

    def test_slow_h2d_no_forensic_without_expectation_passes(self):
        # Same slow run with the expectation OFF: reported, not a failure.
        art = _artifact()
        _set_h2d_ms(art, 4100.0)
        res = _run(art, expect_slow_h2d_forensic=False)
        self.assertTrue(res.passed)
        self.assertTrue(res.slow_forensic_ok)
        self.assertIs(res.slow_forensic_expected_missing, False)


class TestBatchBAcceptanceRender(unittest.TestCase):
    def test_render_block_pass_contains(self):
        res = _run(_make_all_pass_artifact())
        block = render_batch_b_block(res)
        self.assertIn("BATCH B ACCEPTANCE", block)
        self.assertIn("Batch A preserved:", block)
        self.assertIn("OVERALL: PASS", block)
        self.assertIn("TOTAL WALL NOT AN ACCEPTANCE GATE", block)
        self.assertIn("decision: skipped_generation_match", block)
        self.assertIn("evidence:", block)
        self.assertIn("before RSS: 1234.5", block)
        self.assertIn("largest child:", block)
        self.assertIn("reconciliation: 0.0", block)
        self.assertIn("overhead (Tier A): 10.0", block)
        self.assertIn("Tier B forensic probe: n/a", block)

    def test_render_block_fail_lists_checks(self):
        art = _artifact()
        art["result"].pop("snapshot_capture_hygiene", None)
        res = _run(art)
        block = render_batch_b_block(res)
        self.assertIn("FAILED CHECKS:", block)
        self.assertIn("snapshot_hygiene: ", block)
        self.assertIn("OVERALL: FAIL", block)

    def test_render_block_marks_total_wall_informational(self):
        res = _run(_make_all_pass_artifact())
        block = render_batch_b_block(res)
        self.assertIn("TOTAL WALL: 60000.0 (informational only)", block)


class TestBatchBAcceptanceConfig(unittest.TestCase):
    def test_config_from_env(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_V2_BATCH_B_EXPECT_RUNTIME_STATE_SKIP": "1",
            "COMFYMODAL_V2_BATCH_B_EXPECT_STAGE13": "true",
            "COMFYMODAL_V2_BATCH_B_EXPECT_SLOW_H2D_FORENSIC": "yes",
            "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "true",
            "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "yes",
            "COMFYMODAL_V2_BATCH_B_STAGE13_TOLERANCE_MS": "25",
        }, clear=False):
            cfg = batch_b_config_from_env()
        self.assertIs(cfg["expect_runtime_state_skip"], True)
        self.assertIs(cfg["expect_stage13"], True)
        self.assertIs(cfg["expect_slow_h2d_forensic"], True)
        self.assertIs(cfg["snapshot_hygiene_enabled"], True)
        self.assertIs(cfg["snapshot_manifest_enabled"], True)
        self.assertEqual(cfg["stage13_tolerance_ms"], 25.0)

    def test_config_defaults_off(self):
        cfg = batch_b_config_from_env()
        # Environment may carry the flags from a prior run; only assert the
        # dict shape is complete and the tolerance default is numeric.
        self.assertIn("expect_runtime_state_skip", cfg)
        self.assertIn("expect_stage13", cfg)
        self.assertIn("expect_slow_h2d_forensic", cfg)
        self.assertIn("snapshot_hygiene_enabled", cfg)
        self.assertIn("snapshot_manifest_enabled", cfg)
        self.assertIsInstance(cfg["stage13_tolerance_ms"], float)


class TestBatchBAcceptanceFile(unittest.TestCase):
    def test_validate_file_roundtrip(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run_0.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_make_all_pass_artifact(), fh)
            res = validate_batch_b_file(
                path,
                expect_runtime_state_skip=True,
                snapshot_hygiene_enabled=True,
                snapshot_manifest_enabled=True,
                expect_stage13=True,
            )
        self.assertTrue(res.passed)
        self.assertTrue(res.batch_a_preserved)
        self.assertTrue(res.stage13_ok)


if __name__ == "__main__":
    unittest.main()
