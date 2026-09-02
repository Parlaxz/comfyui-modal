"""Offline RX9P/Golden evidence fixtures; no deploys or paid requests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.v2_control.experiment_evidence import (
    _redact,
    finalize_experiment_evidence,
    resolved_sage_runtime_mode,
)


def _cohort(root: Path, name: str, *, invocation: str, backend: str = "pytorch", complete: bool = True,
            failed: bool = False, arm: str = "control", receipt: str = "") -> Path:
    path = root / name
    path.mkdir(parents=True)
    attempt = {
        "request_id": f"request-{name}",
        "v2ctl_invocation_id": invocation,
        "attention_backend": backend,
        "valid": complete and not failed,
        "dnf": not complete or failed,
        "failures": [],
        "validation": {"observed_output_shas": ["a" * 64]},
    }
    (path / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")
    if complete:
        summary = {
            "v2ctl_invocation_id": invocation,
            "attention_backend": backend,
        }
        (path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    manifest = {
        "v2ctl_invocation_id": invocation,
        "profile": "golden_p1",
        "profile_config_fingerprint": "profile-fp",
        "attention_backend": backend,
        "arm": arm,
        "expected_output_sha": "a" * 64,
        "run_fingerprint": "run-fp",
        "attempts": [{"request_id": f"request-{name}"}],
        "deployment_receipt_path": receipt,
    }
    (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_evidence_indexes_every_cohort_and_declares_incomplete(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    _cohort(cohort_root, "clean_exact", invocation="inv-clean")
    _cohort(cohort_root, "incomplete", invocation="inv-incomplete", complete=False)
    result = finalize_experiment_evidence(
        tmp_path,
        identity={
            "profile": "golden_p1",
            "v2ctl_invocation_id": "inv-clean",
            "request_id": "request-clean_exact",
            "profile_config_fingerprint": "profile-fp",
            "run_fingerprint": "run-fp",
            "attention_backend": "pytorch",
        },
        verdict="ACCEPT",
    )
    assert result.status == "OK"
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "clean_exact" in text and "incomplete" in text
    assert "MISSING:" in text and "summary.json" in text
    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert len(index["cohorts"]) == 2
    assert result.markdown_path.parent == tmp_path


def test_evidence_identity_records_configured_and_resolved_sage_modes(tmp_path: Path):
    assert resolved_sage_runtime_mode({"sage_env_mode": "auto", "sage_mode": "triton_fallback"}) == "triton_fallback"
    result = finalize_experiment_evidence(
        tmp_path,
        identity={
            "profile": "golden_p1",
            "v2ctl_invocation_id": "inv-sage",
            "configured_sage_runtime_mode": "auto",
            "resolved_sage_runtime_mode": "auto",
        },
        verdict="ACCEPT",
    )
    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert index["identity"]["configured_sage_runtime_mode"] == "auto"
    assert index["identity"]["resolved_sage_runtime_mode"] == "auto"
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "configured_sage_runtime_mode" in text
    assert "resolved_sage_runtime_mode" in text


def test_large_attempt_events_keep_integrity_metadata_without_embedding(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "large-events", invocation="inv-large")
    events = cohort / "attempt_0_events.json"
    events.write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-large"},
        verdict="INCONCLUSIVE",
    )
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "large repeated attempt event stream" in text
    assert hashlib.sha256(events.read_bytes()).hexdigest() in text
    assert "x" * 1000 not in text


def test_large_later_attempt_events_are_omitted_with_cohort_metadata(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "later-events", invocation="inv-later")
    events = cohort / "attempt_1_events.json"
    events.write_text("y" * (256 * 1024 + 1), encoding="utf-8")
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-later"},
        verdict="INCONCLUSIVE",
    )
    text = result.markdown_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(events.read_bytes()).hexdigest()
    assert "attempt_1_events.json" in text
    assert digest in text
    assert "cohort=later-events" in text
    assert "y" * 1000 not in text


def test_synthetic_fixture_matrix_keeps_failure_and_identity_cases(tmp_path: Path):
    root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    _cohort(root, "mismatch-warning", invocation="other")
    _cohort(root, "failed", invocation="failed", failed=True)
    _cohort(root, "adjacent-a", invocation="a")
    _cohort(root, "adjacent-b", invocation="b")
    _cohort(root, "multi-arm-a", invocation="arm-a", arm="arm-a")
    _cohort(root, "multi-arm-b", invocation="arm-b", arm="arm-b")
    mixed = _cohort(root, "mixed-backend", invocation="mixed")
    (mixed / "attempt_1.json").write_text(json.dumps({
        "request_id": "request-mixed-2", "attention_backend": "sage", "valid": False,
    }), encoding="utf-8")
    _cohort(root, "missing-receipt", invocation="receipt", receipt="missing-receipt.json")
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "golden_p1", "v2ctl_invocation_id": "fixture", "attention_backend": "pytorch"},
        verdict="INCONCLUSIVE",
    )
    text = result.markdown_path.read_text(encoding="utf-8")
    for name in ("mismatch-warning", "failed", "adjacent-a", "adjacent-b", "mixed-backend", "missing-receipt", "multi-arm-a", "multi-arm-b"):
        assert name in text
    assert "mixed" in text.lower()
    assert "deployment receipt" in text


def _cohort_index(result):
    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    return {item["cohort"]: item for item in index["cohorts"]}


def test_evidence_classification_fails_closed_for_identity_and_schema_gaps(tmp_path: Path):
    root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    _cohort(root, "exact", invocation="inv-exact")
    _cohort(root, "mismatch", invocation="inv-other")
    _cohort(root, "missing-summary", invocation="inv-missing")
    (root / "missing-summary" / "summary.json").unlink()

    missing_summary_id = _cohort(root, "missing-summary-id", invocation="inv-summary-id")
    summary = json.loads((missing_summary_id / "summary.json").read_text(encoding="utf-8"))
    del summary["v2ctl_invocation_id"]
    (missing_summary_id / "summary.json").write_text(json.dumps(summary), encoding="utf-8")

    missing_attempt_id = _cohort(root, "missing-attempt-id", invocation="inv-attempt-id")
    attempt = json.loads((missing_attempt_id / "attempt_0.json").read_text(encoding="utf-8"))
    del attempt["v2ctl_invocation_id"]
    (missing_attempt_id / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")

    malformed = root / "malformed"
    malformed.mkdir()
    for name in ("manifest.json", "summary.json", "attempt_0.json"):
        (malformed / name).write_text("{", encoding="utf-8")

    result = finalize_experiment_evidence(
        tmp_path,
        identity={
            "profile": "golden_p1",
            "v2ctl_invocation_id": "inv-exact",
            "profile_config_fingerprint": "profile-fp",
            "run_fingerprint": "run-fp",
            "attention_backend": "pytorch",
        },
        verdict="INCONCLUSIVE",
        experiment_id="classification-matrix",
    )
    cohorts = _cohort_index(result)
    assert cohorts["exact"]["exact"] == "EXACT"
    assert cohorts["mismatch"]["exact"] == "MISMATCH"
    for name in ("missing-summary", "missing-summary-id", "missing-attempt-id", "malformed"):
        assert cohorts[name]["exact"] == "INCOMPLETE"


def test_redact_covers_nested_json_and_quoted_assignment_secrets():
    text = (
        '{"nested": {"api_key": "REAL-SECRET", '
        '"quoted_password": "PASSWORD-SECRET", '
        '"credential": "CREDENTIAL-SECRET"}}\n'
        "api_key='ASSIGNMENT-SECRET'"
    )
    redacted = _redact(text)
    for secret in (
        "REAL-SECRET",
        "PASSWORD-SECRET",
        "CREDENTIAL-SECRET",
        "ASSIGNMENT-SECRET",
    ):
        assert secret not in redacted
    assert redacted.count("<redacted>") == 4, redacted
