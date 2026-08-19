"""Unit tests for the Batch-C acceptance harness (tools/batch_c_acceptance.py).

Pure offline fixtures matching the run_<i>.json artifact shape persisted by
benchmark_v2_direct.py.  Batch-C WRAPS tools/batch_b_acceptance.validate_batch_b
and adds the optional plan fast-path expectation flag
COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH: expectation ON fails closed on
missing/contradictory fast-path evidence; expectation OFF reports only and
never fails.

The all-pass fixture is self-contained (copied from the Batch-B all-pass shape:
same identity / waterfall / runtime-state skip / snapshot hygiene / snapshot
manifest / stage-13 decomposition / host telemetry / terminal stamps) and
satisfies every Batch-A + Batch-B gate with the default Batch-C test config.
The healthy fast-path fixture layers the real runtime-spelled fast-path
events on top (plan_snapshot_parity + plan_proof_decision +
certificate_read_outcome, all phase="setup" exactly as modal_app.py emits
them).  The motivating failure - plan_proof_decision=legacy_validation_fallback,
consumed=False, certificate_read_outcome cert_source="volume"
cert_decision="volume_read" - is exercised by the legacy-fallback / volume
fallback / mismatch fixtures.  No Modal, no network, no sleeps, no asyncio.

Runnable from the repo root via:
    python -m unittest tests.test_batch_c_acceptance -v
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from typing import Any
from unittest import mock

from tools.batch_c_acceptance import (
    FAST_PATH_GATE_KEYS,
    batch_c_config_from_env,
    render_batch_c_block,
    validate_batch_c,
    validate_batch_c_file,
)


def _make_event(name: str, wall_ns: int = 0, mono_ns: int = 0,
                metadata: dict[str, Any] | None = None,
                phase: str | None = None) -> dict[str, Any]:
    """Same event shape as the repo's trace events / existing fixtures."""
    _e = {"name": name, "wall_unix_ns": wall_ns, "monotonic_ns": mono_ns,
          "metadata": dict(metadata or {})}
    if phase is not None:
        _e["phase"] = phase
    return _e


def _make_all_pass_artifact() -> dict[str, Any]:
    """A run_<i>.json-shaped artifact that satisfies every Batch-A gate AND
    every Batch-B gate (with all Batch-B env expectations enabled).  Same
    structure as the Batch-B all-pass fixture: runtime-state skip evidence,
    snapshot_capture_hygiene record, snapshot manifest with status,
    output_stage13_breakdown whose children (150+60+40) reconcile the parent
    (250), host telemetry 10.0 ms, terminal cleanup stamps, and a 60 s TOTAL
    WALL that must never gate acceptance.  Deliberately carries NO fast-path
    events (that is the missing-evidence fixture base)."""
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


def _make_healthy_fast_path_artifact() -> dict[str, Any]:
    """The all-pass Batch-B artifact PLUS the real runtime-spelled fast-path
    events:

      - plan_snapshot_parity (phase="setup") with every parity key True and
        future_fast_path_eligible=True (contract: contracts.py:677-742,
        emission: modal_app.py:12242);
      - plan_proof_decision (phase="setup") with consumed=True,
        decision="plan_validation_fast_path", reason="" (modal_app.py:12897);
      - certificate_read_outcome (phase="setup") with
        cert_source="plan_validation", cert_decision="plan_validation_fast_path",
        hit=True, preflight_skip=True, consumed=True (modal_app.py:12347).
    """
    art = _make_all_pass_artifact()
    art["result"]["trace"]["events"].extend([
        _make_event("plan_snapshot_parity", mono_ns=1350, phase="setup",
                    metadata={
                        "snapshot_proof_present": True,
                        "snapshot_proof_complete": True,
                        "snapshot_proof_valid": True,
                        "plan_deployment_complete": True,
                        "deployment_hash_match": True,
                        "custom_nodes_generation_match": True,
                        "workflow_registry_match": True,
                        "registry_fingerprint_match": True,
                        "dependency_proof_match": True,
                        "future_fast_path_eligible": True,
                        "future_fast_path_ineligible_reason": "",
                    }),
        _make_event("plan_proof_decision", mono_ns=1400, phase="setup",
                    metadata={"consumed": True,
                              "decision": "plan_validation_fast_path",
                              "reason": ""}),
        _make_event("certificate_read_outcome", mono_ns=1450, phase="setup",
                    metadata={"cert_source": "plan_validation",
                              "cert_decision": "plan_validation_fast_path",
                              "hit": True, "preflight_skip": True,
                              "consumed": True}),
    ])
    return art


def _artifact() -> dict[str, Any]:
    """Deep-copied all-pass artifact (NO fast-path events) for mutation."""
    return copy.deepcopy(_make_all_pass_artifact())


def _fast_path_artifact() -> dict[str, Any]:
    """Deep-copied healthy fast-path artifact for mutation."""
    return copy.deepcopy(_make_healthy_fast_path_artifact())


def _run(art: dict[str, Any], expect_plan_fast_path: bool = True,
         **batch_b_kwargs: Any) -> Any:
    """validate_batch_c with all Batch-B expectations ON by default (same
    defaults as tests/test_batch_b_acceptance._run)."""
    cfg = {
        "expect_runtime_state_skip": True,
        "snapshot_hygiene_enabled": True,
        "snapshot_manifest_enabled": True,
        "expect_stage13": False,
        "expect_slow_h2d_forensic": False,
    }
    cfg.update(batch_b_kwargs)
    return validate_batch_c(art, expect_plan_fast_path=expect_plan_fast_path,
                            **cfg)


def _failing_keys(res: Any) -> set[str]:
    return {c.key for c in res.checks if not c.ok}


def _gate(res: Any, key: str) -> Any:
    for _c in res.checks:
        if _c.key == key:
            return _c
    raise AssertionError(f"gate {key!r} not present")


def _set_parity(art: dict[str, Any], **overrides: Any) -> None:
    """Override metadata keys of the plan_snapshot_parity event (in place)."""
    for _e in art["result"]["trace"]["events"]:
        if _e.get("name") == "plan_snapshot_parity":
            _e["metadata"].update(overrides)
            return
    raise AssertionError("plan_snapshot_parity event not present")


def _set_plan_proof_decision(art: dict[str, Any], *,
                             decision: str = "legacy_validation_fallback",
                             consumed: bool = False,
                             reason: str = "") -> None:
    """Replace the plan_proof_decision event (in place)."""
    _events = art["result"]["trace"]["events"]
    _events[:] = [e for e in _events if e.get("name") != "plan_proof_decision"]
    _events.append(_make_event(
        "plan_proof_decision", mono_ns=1400, phase="setup",
        metadata={"consumed": consumed, "decision": decision, "reason": reason},
    ))


def _set_cert_outcome(art: dict[str, Any], *,
                      source: str = "volume", decision: str = "volume_read",
                      hit: bool = False, preflight_skip: bool = False) -> None:
    """Replace every certificate_read_outcome with one (legacy) cert-style
    outcome (in place)."""
    _events = art["result"]["trace"]["events"]
    _events[:] = [e for e in _events if e.get("name") != "certificate_read_outcome"]
    _events.append(_make_event(
        "certificate_read_outcome", mono_ns=1500, phase="execution",
        metadata={"cert_identity": "abc123",
                  "cert_source": source, "cert_decision": decision,
                  "hit": hit, "preflight_skip": preflight_skip,
                  "cert_cache_hit": False,
                  "cert_volume_reload_ms": 121.0,
                  "cert_file_read_ms": 2.0,
                  "cert_json_parse_validate_ms": 1.0,
                  "cert_total_ms": 124.0},
    ))


def _add_cert_reload_events(art: dict[str, Any]) -> None:
    """Append real certificate_reload_start/end volume-reload markers."""
    _events = art["result"]["trace"]["events"]
    _events.append(_make_event(
        "certificate_reload_start", mono_ns=1500, phase="execution",
        metadata={"cert_identity": "abc123"},
    ))
    _events.append(_make_event(
        "certificate_reload_end", mono_ns=1600, phase="execution",
        metadata={"cert_identity": "abc123", "hit": True,
                  "cert_volume_reload_ms": 121.0,
                  "cert_file_read_ms": 2.0,
                  "cert_json_parse_validate_ms": 1.0,
                  "cert_total_ms": 124.0},
    ))


class TestBatchCAllPass(unittest.TestCase):
    def test_healthy_fast_path_passes(self):
        res = _run(_make_healthy_fast_path_artifact())
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "PASS")
        self.assertTrue(res.fast_path_ready)
        self.assertTrue(res.fast_path_ok)
        self.assertTrue(res.batch_b.passed)
        self.assertTrue(all(
            c.ok for c in res.checks if c.key in FAST_PATH_GATE_KEYS
        ))

    def test_total_wall_60s_non_gating(self):
        # TOTAL WALL is never an acceptance gate (informational only).
        res = _run(_make_healthy_fast_path_artifact())
        self.assertEqual(res.batch_b.total_wall_ms, 60000.0)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "PASS")


class TestBatchCLegacyFallback(unittest.TestCase):
    def _legacy_artifact(self) -> dict[str, Any]:
        # The motivating failing-run shape: parity ineligible on
        # custom_nodes_generation_mismatch + dependency_proof_mismatch,
        # plan_proof_decision=legacy_validation_fallback consumed=False, and a
        # certificate_read_outcome cert_source="volume" cert_decision="volume_read".
        art = _fast_path_artifact()
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="custom_nodes_generation_mismatch,dependency_proof_mismatch",
        )
        _set_cert_outcome(art, source="volume", decision="volume_read",
                          hit=False, preflight_skip=False)
        return art

    def test_legacy_fallback_fails_when_expectation_on(self):
        res = _run(self._legacy_artifact())
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertIs(res.legacy_fallback, True)
        self.assertIs(res.cert_volume_fallback, True)
        self.assertEqual(res.plan_proof_decision, "legacy_validation_fallback")
        self.assertIs(res.consumed, False)
        self.assertEqual(res.fallback_classification, "mismatch")
        self.assertEqual(
            res.fallback_reason,
            "custom_nodes_generation_mismatch,dependency_proof_mismatch",
        )
        failing = _failing_keys(res)
        self.assertIn("no_legacy_validation_fallback", failing)
        self.assertIn("no_cert_volume_read_fallback", failing)
        self.assertIn("fast_path_decision", failing)
        self.assertIn("fast_path_consumed", failing)


class TestBatchCConsumedFalse(unittest.TestCase):
    def test_consumed_false_fails(self):
        # Parity fully eligible (fast path) but plan_proof_decision.consumed is
        # False with a legacy decision: the fast-path lane must FAIL.
        art = _fast_path_artifact()
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="custom_nodes_generation_mismatch",
        )
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertIs(res.consumed, False)
        self.assertTrue(res.consumed_ready)
        self.assertTrue(res.plan_parity_eligible_ready)
        self.assertIs(res.plan_parity_eligible, True)
        failing = _failing_keys(res)
        self.assertIn("fast_path_consumed", failing)


class TestBatchCCertVolumeFallback(unittest.TestCase):
    def test_volume_read_outcome_fails(self):
        # Parity eligible + plan_proof_decision fast path consumed=True BUT the
        # certificate_read_outcome says volume_read: the cert contract
        # disagrees and no_cert_volume_read_fallback must fail.
        art = _fast_path_artifact()
        _set_cert_outcome(art, source="volume", decision="volume_read",
                          hit=True, preflight_skip=True)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertIs(res.cert_volume_fallback, True)
        self.assertTrue(res.cert_volume_fallback_ready)
        # The decision/consumed observables stay healthy (only the cert lane
        # contradicts).
        self.assertEqual(res.plan_proof_decision, "plan_validation_fast_path")
        self.assertIs(res.consumed, True)
        failing = _failing_keys(res)
        self.assertIn("no_cert_volume_read_fallback", failing)
        self.assertIn("no_cert_volume_read_fallback",
                      [c.key for c in res.checks])

    def test_cert_reload_events_fail(self):
        # Real certificate_reload_start/end markers are the volume fallback:
        # presence alone must fail the gate when the expectation is ON.
        art = _fast_path_artifact()
        _add_cert_reload_events(art)
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertIs(res.cert_volume_fallback, True)
        failing = _failing_keys(res)
        self.assertIn("no_cert_volume_read_fallback", failing)
        self.assertIn(
            "certificate_reload_start", _gate(res, "no_cert_volume_read_fallback").detail
        )


class TestBatchCGenerationMismatch(unittest.TestCase):
    def test_generation_mismatch_fails(self):
        art = _fast_path_artifact()
        _set_parity(art,
                    custom_nodes_generation_match=False,
                    future_fast_path_eligible=False,
                    future_fast_path_ineligible_reason="custom_nodes_generation_mismatch")
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="custom_nodes_generation_mismatch",
        )
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertTrue(res.custom_nodes_generation_ready)
        self.assertIs(res.custom_nodes_generation_match, False)
        self.assertIs(res.plan_parity_eligible, False)
        failing = _failing_keys(res)
        self.assertIn("custom_nodes_generation_match", failing)
        self.assertIn("fast_path_parity_eligible", failing)


class TestBatchCDependencyMismatch(unittest.TestCase):
    def test_dependency_mismatch_fails(self):
        art = _fast_path_artifact()
        _set_parity(art,
                    dependency_proof_match=False,
                    future_fast_path_eligible=False,
                    future_fast_path_ineligible_reason="dependency_proof_mismatch")
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="dependency_proof_mismatch",
        )
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertTrue(res.dependency_proof_ready)
        self.assertIs(res.dependency_proof_match, False)
        failing = _failing_keys(res)
        self.assertIn("dependency_proof_match", failing)


class TestBatchCExpectationOffReportOnly(unittest.TestCase):
    def test_legacy_fallback_expectation_off_report_only(self):
        # The same legacy-fallback artifact as TestBatchCLegacyFallback but
        # with the expectation OFF: reported only, never a failure, and clearly
        # NOT a strict fast-path PASS.
        art = _fast_path_artifact()
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="custom_nodes_generation_mismatch,dependency_proof_mismatch",
        )
        _set_cert_outcome(art, source="volume", decision="volume_read",
                          hit=False, preflight_skip=False)
        res = _run(art, expect_plan_fast_path=False)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "REPORT_ONLY")
        self.assertNotEqual(res.verdict, "PASS")
        self.assertIs(res.legacy_fallback, True)
        self.assertIs(res.cert_volume_fallback, True)
        self.assertEqual(res.fallback_classification, "mismatch")
        self.assertIn("report-only", render_batch_c_block(res))

    def test_healthy_expectation_off_report_only(self):
        res = _run(_make_healthy_fast_path_artifact(),
                   expect_plan_fast_path=False)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "REPORT_ONLY")
        self.assertTrue(res.fast_path_ready)
        self.assertIn("report-only", render_batch_c_block(res))


class TestBatchCMissingEvidenceFailsClosed(unittest.TestCase):
    def test_expectation_on_fails_closed(self):
        # All-pass Batch-B artifact with NO fast-path events: the fast-path
        # lane is NOT READY and must fail closed when the expectation is ON.
        res = _run(_make_all_pass_artifact())
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertFalse(res.fast_path_ready)
        self.assertTrue(res.batch_b.passed)  # Batch-B alone is fine
        # At least the decision / consumed / parity gates are NOT READY.
        self.assertFalse(res.plan_proof_decision_ready)
        self.assertFalse(res.consumed_ready)
        self.assertFalse(res.plan_parity_eligible_ready)
        self.assertFalse(res.deployment_hash_ready)
        self.assertIn("NOT READY", _gate(res, "fast_path_decision").detail)
        self.assertIn("NOT READY", _gate(res, "fast_path_consumed").detail)
        self.assertIn("NOT READY", _gate(res, "fast_path_parity_eligible").detail)

    def test_expectation_off_report_only(self):
        res = _run(_make_all_pass_artifact(), expect_plan_fast_path=False)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "REPORT_ONLY")
        self.assertFalse(res.fast_path_ready)
        self.assertTrue(res.fast_path_ok)


class TestBatchCFailureWins(unittest.TestCase):
    def test_batch_b_failure_wins(self):
        # Healthy fast-path events added to a Batch-B-FAILING artifact: Batch-C
        # fails unconditionally on the wrapped Batch-B result regardless of the
        # fast-path fields.
        art = _fast_path_artifact()
        art["result"].pop("snapshot_capture_hygiene", None)  # Batch-B gate 3
        res = _run(art)
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertFalse(res.batch_b.passed)
        # The fast-path fields are still healthy and reported.
        self.assertEqual(res.plan_proof_decision, "plan_validation_fast_path")
        self.assertIs(res.consumed, True)
        self.assertIs(res.cert_volume_fallback, False)
        failing = _failing_keys(res)
        self.assertIn("batch_b_acceptance", failing)


class TestBatchCRuntimeSpelledHealthy(unittest.TestCase):
    def test_runtime_spelled_healthy_passes(self):
        # The exact runtime-emitted fast-path shapes (healthy fixture) must
        # PASS with all observables resolved from real evidence.
        res = _run(_make_healthy_fast_path_artifact())
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "PASS")
        self.assertIs(res.consumed, True)  # bool, not int
        self.assertEqual(res.plan_proof_decision, "plan_validation_fast_path")
        self.assertIs(res.plan_parity_eligible, True)
        self.assertIs(res.deployment_hash_match, True)
        self.assertIs(res.custom_nodes_generation_match, True)
        self.assertIs(res.dependency_proof_match, True)
        self.assertIs(res.cert_volume_fallback, False)
        self.assertIs(res.legacy_fallback, False)
        self.assertIsNone(res.fallback_classification)


class TestBatchCIdentityTransitionDiagnosable(unittest.TestCase):
    def _identity_transition_artifact(self) -> dict[str, Any]:
        # A brand-new snapshot/deployment identity (snapshot proof incomplete
        # + deployment hash mismatch): diagnosable as identity_transition, NOT
        # mismatch, even though deployment_hash_mismatch is also present.
        art = _fast_path_artifact()
        _set_parity(art,
                    snapshot_proof_complete=False,
                    deployment_hash_match=False,
                    future_fast_path_eligible=False,
                    future_fast_path_ineligible_reason=(
                        "snapshot_proof_incomplete,deployment_hash_mismatch"))
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="snapshot_proof_incomplete,deployment_hash_mismatch",
        )
        return art

    def test_identity_transition_fails_but_is_diagnosable(self):
        res = _run(self._identity_transition_artifact())
        self.assertFalse(res.passed)
        self.assertEqual(res.verdict, "FAIL")
        self.assertEqual(res.fallback_classification, "identity_transition")
        self.assertNotEqual(res.fallback_classification, "mismatch")
        self.assertEqual(
            res.fallback_reason,
            "snapshot_proof_incomplete,deployment_hash_mismatch",
        )

    def test_identity_transition_expectation_off_report_only(self):
        res = _run(self._identity_transition_artifact(),
                   expect_plan_fast_path=False)
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "REPORT_ONLY")
        self.assertEqual(res.fallback_classification, "identity_transition")


class TestBatchCConfig(unittest.TestCase):
    def test_expect_plan_fast_path_env_on(self):
        with mock.patch.dict(os.environ, {
            "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "1",
        }, clear=False):
            cfg = batch_c_config_from_env()
        self.assertIs(cfg["expect_plan_fast_path"], True)

    def test_expect_plan_fast_path_env_off_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            cfg = batch_c_config_from_env()
        self.assertIs(cfg["expect_plan_fast_path"], False)
        # Batch-B flags are inherited unchanged (config shape is complete).
        self.assertIn("expect_runtime_state_skip", cfg)
        self.assertIn("snapshot_hygiene_enabled", cfg)
        self.assertIn("snapshot_manifest_enabled", cfg)


class TestBatchCRender(unittest.TestCase):
    def test_render_block_pass_contains(self):
        res = _run(_make_healthy_fast_path_artifact())
        block = render_batch_c_block(res)
        self.assertIn("BATCH C ACCEPTANCE", block)
        self.assertIn("OVERALL: PASS", block)
        self.assertIn("plan proof decision: plan_validation_fast_path", block)
        self.assertIn("consumed: YES", block)
        self.assertIn("TOTAL WALL NOT AN ACCEPTANCE GATE", block)
        self.assertIn("TOTAL WALL: 60000.0 (informational only)", block)
        self.assertIn("fast-path lane: READY", block)

    def test_render_block_fail_lists_checks(self):
        art = _fast_path_artifact()
        _set_plan_proof_decision(
            art, decision="legacy_validation_fallback", consumed=False,
            reason="custom_nodes_generation_mismatch,dependency_proof_mismatch",
        )
        _set_cert_outcome(art, source="volume", decision="volume_read")
        res = _run(art)
        block = render_batch_c_block(res)
        self.assertIn("FAILED CHECKS:", block)
        self.assertIn("no_legacy_validation_fallback: ", block)
        self.assertIn("no_cert_volume_read_fallback: ", block)
        self.assertIn("OVERALL: FAIL", block)
        self.assertIn("fallback classification: mismatch", block)


class TestBatchCFile(unittest.TestCase):
    def test_validate_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "run_0.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(_make_healthy_fast_path_artifact(), fh)
            res = validate_batch_c_file(
                path,
                expect_plan_fast_path=True,
                expect_runtime_state_skip=True,
                snapshot_hygiene_enabled=True,
                snapshot_manifest_enabled=True,
                expect_stage13=False,
                expect_slow_h2d_forensic=False,
            )
        self.assertTrue(res.passed)
        self.assertEqual(res.verdict, "PASS")
        self.assertTrue(res.batch_b.passed)


if __name__ == "__main__":
    unittest.main()
