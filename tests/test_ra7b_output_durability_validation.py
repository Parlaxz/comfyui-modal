"""Focused RA7B tests for conditional request-output durability validation."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest
import tools.benchmark_v2_direct as benchmark
from tools.v2_control.validation import (
    CanonicalLedgerValidator,
    RunRecord,
    resolve_output_durability_mode,
)
from tests.v2ctl_fakes import FakeArtifactSet, FakeConfig, FakeFlag


SHA = "a" * 64
CANONICAL_CONFIGURATION_ERROR = (
    "configuration error: COMFYMODAL_OUTPUT_DURABILITY must be off or strict"
)


def _snapshot_proof() -> dict:
    return {
        "schema": "golden_snapshot_content_proof_v1",
        "passive": True,
        "proven": True,
        "surface_count": 1,
        "snapshot_size_bytes": 1,
        "snapshot_size_limit_bytes": 2,
        "snapshot_size_source": "process_rss_pre_capture_resident_memory_proxy",
        "snapshot_size_is_serialized": False,
        "tensor_count": 0,
        "parameter_bytes": 0,
        "model_patcher_count": 0,
        "qd_owner_count": 0,
        "open_payload_reader_count": 0,
        "preload_worker_count": 0,
        "future_count": 0,
        "nonzero": {},
        "nonzero_roles": {},
        "roles": {
            role: {"tensor_count": 0, "parameter_bytes": 0, "qd_owner_count": 0}
            for role in ("unet", "clip", "vae")
        },
    }


def _scan(mode: str = "off") -> dict:
    return {
        "terminal_results": [(0, {"type": "result"})],
        "error_events": [],
        "true_durable": [],
        "seriality": [(0, "result.seriality", {"ok": True, "violations": [], "count": 0})],
        "teardown": [(0, "result.teardown", {"ok": True})],
        "snapshot_proof": [(0, "result.snapshot_proof", _snapshot_proof())],
        "commit": [],
        "reopen": [],
        "true_first": [],
        "flags": [(0, "result.flags", dict(benchmark.GOLDEN_P1_REQUIRED_FLAGS))],
        "identities": [],
        "output_shas": [(0, "result.output_sha", SHA)],
        "output_sha_warnings": [],
        "output_durability_mode": [(0, "result.output_durability_mode", mode)],
        "result_ready": [(0, "result.result_ready", True)],
        "output_integrity": [],
        "durability_claims": [],
        "non_dict_events": 0,
    }


def test_mode_parser_is_fail_closed_and_runtime_compatible(monkeypatch):
    monkeypatch.delenv("COMFYMODAL_OUTPUT_DURABILITY", raising=False)
    assert resolve_output_durability_mode({}) == "off"
    assert resolve_output_durability_mode({"output_durability_mode": "strict"}) == "strict"
    with pytest.raises(ValueError) as excinfo:
        resolve_output_durability_mode({"output_durability_mode": "typo"})
    assert str(excinfo.value) == CANONICAL_CONFIGURATION_ERROR

    config = SimpleNamespace(
        flags=[SimpleNamespace(name="COMFYMODAL_OUTPUT_DURABILITY", value="invalid")],
        workload={},
    )
    with pytest.raises(ValueError) as excinfo:
        resolve_output_durability_mode(config=config)
    assert str(excinfo.value) == CANONICAL_CONFIGURATION_ERROR

    monkeypatch.setenv("COMFYMODAL_OUTPUT_DURABILITY", "typo")
    with pytest.raises(ValueError) as excinfo:
        resolve_output_durability_mode({"output_durability_mode": "off"})
    assert str(excinfo.value) == CANONICAL_CONFIGURATION_ERROR


def test_off_mode_accepts_result_ready_without_durability_and_marks_not_run():
    valid, failures, details = benchmark._golden_p1_validate_attempt(
        _scan(), expected_output_sha=SHA, expected_flags=None
    )

    assert valid, failures
    assert details["output_endpoint"] == "result_ready"
    assert details["durability_status"] == "NOT RUN"
    assert details["durability_waterfall"]["commit_ms"] is None
    assert details["durability_waterfall"]["reopen_ms"] is None


def test_off_mode_ignores_negative_and_not_run_durability_fields():
    scan = _scan()
    scan["true_durable"] = [
        (0, "result.true_durable", False),
        (0, "result.result_durable", None),
        (0, "result.true_durable_marked", "NOT RUN"),
    ]
    for key in ("commit", "reopen", "true_first", "asset_write", "fsync", "sidecar", "pending_durability"):
        scan[key] = [
            (0, f"result.{key}", False),
            (0, f"result.{key}_empty", {}),
            (0, f"result.{key}_not_run", "NOT RUN"),
        ]
    scan["durability_claims"] = [(0, {
        "true_durable": False,
        "reopen_verified": False,
        "asset_write": {},
        "commit": "NOT RUN",
    })]

    valid, failures, _details = benchmark._golden_p1_validate_attempt(
        scan, expected_output_sha=SHA, expected_flags=None
    )

    assert valid, failures


def test_scanner_does_not_promote_negative_named_durability_markers():
    scanned = benchmark._golden_p1_scan_events([{
        "type": "result",
        "data": {
            "output_durability_mode": "off",
            "true_durable": False,
            "reopen_verified": False,
            "golden_telemetry": {
                "events": [{
                    "name": "durable_reopen_verified",
                    "status": "NOT RUN",
                }],
            },
        },
    }])

    assert scanned["durability_claims"] == []


def test_off_mode_rejects_observed_durability_work():
    scan = _scan()
    scan["commit"] = [(0, "result.volume_commit", 123)]
    scan["durability_claims"] = [(0, {"volume_commit": True})]

    valid, failures, _details = benchmark._golden_p1_validate_attempt(
        scan, expected_output_sha=SHA, expected_flags=None
    )

    assert not valid
    assert any("off mode" in failure for failure in failures)


def test_scanner_classifies_asset_write_and_fsync_without_confusing_publication():
    scanned = benchmark._golden_p1_scan_events([{
        "type": "result",
        "data": {
            "output_asset_write": {"duration_ms": 2},
            "output_fsync_ms": 1,
            "s4_publication": {"commit": True, "fsync": True},
        },
    }])

    assert scanned["asset_write"]
    assert scanned["fsync"]
    # The generated-output markers are claims; the distinct S4 publication
    # branch must not create additional durability claims.
    assert len(scanned["durability_claims"]) == 1


def test_off_mode_rejects_asset_write_and_validates_exposed_byte_count():
    scan = _scan()
    scan["asset_write"] = [(0, "result.output_asset_write", {"duration_ms": 1})]
    scan["output_byte_counts"] = [(0, "result.output_descriptor.byte_count", 42)]

    valid, failures, details = benchmark._golden_p1_validate_attempt(
        scan, expected_output_sha=SHA, expected_flags=None
    )

    assert not valid
    assert any("off mode" in failure for failure in failures)
    assert details["durability_waterfall"]["commit_ms"] is None
    assert details["durability_waterfall"]["reopen_ms"] is None


def test_canonical_strict_ledger_requires_current_durable_evidence(tmp_path: Path):
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text(
        '{"output_durability_mode":"strict",'
        '"true_durable_marked":true,"reopen_verified":true,'
        '"canonical_ledger_status":"ok",'
        '"canonical_ledger":{"endpoint_status":"true_durable",'
        '"serial_ledger":{"zero_gap":true},'
        '"events":[{"name":"volume_commit_complete","mono_ns":10},'
        '{"name":"durable_reopen_verified","mono_ns":20}]}}',
        encoding="utf-8",
    )
    config = FakeConfig()
    config.flags.extend([
        FakeFlag(name="COMFYMODAL_V2_CRITICAL_PATH_LEDGER", value="1"),
        FakeFlag(name="COMFYMODAL_OUTPUT_DURABILITY", value="strict"),
    ])
    record = RunRecord(
        run_fingerprint="r", deploy_fingerprint="d", profile="production",
        target_app="app", target_class="class", fresh_required=False,
        expected_output_sha="", artifacts=FakeArtifactSet(run_artifact=artifact_path),
        backend_ok=True,
        telemetry={
            "canonical_ledger_status": "ok",
            "canonical_ledger_endpoint_status": "true_durable",
            "canonical_ledger_zero_gap": "True",
            "true_durable_marked": True,
            "reopen_verified": True,
        },
    )

    assert CanonicalLedgerValidator().validate(record, config) == []


def test_canonical_validator_reports_invalid_explicit_selector(tmp_path: Path):
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text('{"canonical_ledger_status":"ok"}', encoding="utf-8")
    config = FakeConfig()
    config.flags.extend([
        FakeFlag(name="COMFYMODAL_V2_CRITICAL_PATH_LEDGER", value="1"),
        FakeFlag(name="COMFYMODAL_OUTPUT_DURABILITY", value="invalid"),
    ])
    record = RunRecord(
        run_fingerprint="r", deploy_fingerprint="d", profile="production",
        target_app="app", target_class="class", fresh_required=False,
        expected_output_sha="", artifacts=FakeArtifactSet(run_artifact=artifact_path),
        backend_ok=True, telemetry={},
    )

    failures = CanonicalLedgerValidator().validate(record, config)
    assert failures == [CANONICAL_CONFIGURATION_ERROR]


def test_canonical_strict_ledger_rejects_missing_reopen_order_proof(tmp_path: Path):
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text(
        '{"output_durability_mode":"strict","canonical_ledger_status":"ok",'
        '"canonical_ledger":{"endpoint_status":"true_durable",'
        '"serial_ledger":{"zero_gap":true},"events":[]}}',
        encoding="utf-8",
    )
    config = FakeConfig()
    config.flags.extend([
        FakeFlag(name="COMFYMODAL_V2_CRITICAL_PATH_LEDGER", value="1"),
        FakeFlag(name="COMFYMODAL_OUTPUT_DURABILITY", value="strict"),
    ])
    record = RunRecord(
        run_fingerprint="r", deploy_fingerprint="d", profile="production",
        target_app="app", target_class="class", fresh_required=False,
        expected_output_sha="", artifacts=FakeArtifactSet(run_artifact=artifact_path),
        backend_ok=True,
        telemetry={
            "canonical_ledger_status": "ok",
            "canonical_ledger_endpoint_status": "true_durable",
            "canonical_ledger_zero_gap": "True",
            "true_durable_marked": True,
            "reopen_verified": True,
        },
    )

    failures = CanonicalLedgerValidator().validate(record, config)
    assert any("commit-before-reopen" in failure for failure in failures)


def test_strict_mode_keeps_true_durable_commit_and_reopen_gates():
    valid, failures, details = benchmark._golden_p1_validate_attempt(
        _scan(mode="strict"), expected_output_sha=SHA, expected_flags=None
    )

    assert not valid
    assert details["output_endpoint"] == "true_durable"
    assert any("true_durable" in failure for failure in failures)
    assert any("commit timestamp" in failure for failure in failures)
    assert any("reopen timestamp" in failure for failure in failures)
    assert any("TRUE_FIRST_DURABLE_RESULT" in failure for failure in failures)


def test_event_scan_preserves_mode_and_ready_evidence():
    scanned = benchmark._golden_p1_scan_events([{
        "type": "result",
        "data": {
            "output_durability_mode": "off",
            "result_ready": {"ok": True},
        },
    }])

    assert scanned["output_durability_mode"] == [
        (0, "data.output_durability_mode", "off")
    ]
    assert scanned["result_ready"] == [
        (0, "data.result_ready", {"ok": True})
    ]


def test_canonical_ledger_off_mode_uses_result_ready_endpoint(tmp_path: Path):
    artifact_path = tmp_path / "run.json"
    artifact_path.write_text(
        '{"output_durability_mode":"off",'
        '"result":{"first_result_ready_marked":true},'
        '"canonical_ledger_status":"ok",'
        '"canonical_ledger":{"endpoint_status":"result_ready",'
        '"serial_ledger":{"zero_gap":true}}}',
        encoding="utf-8",
    )
    config = FakeConfig()
    config.flags.extend([
        FakeFlag(name="COMFYMODAL_V2_CRITICAL_PATH_LEDGER", value="1"),
        FakeFlag(name="COMFYMODAL_OUTPUT_DURABILITY", value="off"),
    ])
    record = RunRecord(
        run_fingerprint="r",
        deploy_fingerprint="d",
        profile="production",
        target_app="app",
        target_class="class",
        fresh_required=False,
        expected_output_sha="",
        artifacts=FakeArtifactSet(run_artifact=artifact_path),
        backend_ok=True,
        telemetry={
            "canonical_ledger_status": "ok",
            "canonical_ledger_endpoint_status": "result_ready",
            "canonical_ledger_zero_gap": "True",
        },
    )

    assert CanonicalLedgerValidator().validate(record, config) == []
