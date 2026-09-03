"""Offline RX9P/Golden evidence fixtures; no deploys or paid requests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import tools.v2_control.experiment_evidence as evidence_module

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


def _owner(cohort: Path):
    return SimpleNamespace(artifacts=SimpleNamespace(output_dir=cohort))


def test_evidence_derives_current_cohort_from_run_artifact_parent(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    current = _cohort(cohort_root, "run-owned", invocation="inv-run-owned")
    _cohort(cohort_root, "historical", invocation="inv-historical")
    owner = SimpleNamespace(
        artifacts=SimpleNamespace(output_dir=None, run_artifact=current / "attempt_0.json")
    )

    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "golden_p1", "v2ctl_invocation_id": "inv-run-owned"},
        verdict="ACCEPT",
        result=owner,
    )

    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert [item["cohort"] for item in index["cohorts"]] == ["run-owned"]


def test_evidence_indexes_current_cohort_without_scanning_historical_cohorts(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    current = _cohort(cohort_root, "clean_exact", invocation="inv-clean")
    historical = _cohort(cohort_root, "historical-large", invocation="inv-incomplete", complete=False)
    unrelated = historical / "large-historical-payload.bin"
    unrelated.write_bytes(b"historical evidence\n" * 100_000)
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
        result=_owner(current),
    )
    assert result.status == "OK"
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "clean_exact" in text
    assert "historical-large" not in text
    assert "large-historical-payload.bin" not in text
    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert [item["cohort"] for item in index["cohorts"]] == ["clean_exact"]
    assert result.markdown_path.parent == tmp_path


def test_evidence_identity_records_configured_and_resolved_sage_modes(tmp_path: Path):
    # 1. configured auto, no runtime observation -> resolved missing/unknown, NOT auto
    assert resolved_sage_runtime_mode({"sage_env_mode": "auto"}) == ""
    assert resolved_sage_runtime_mode({"configured_sage_runtime_mode": "auto"}) == ""
    assert resolved_sage_runtime_mode({"sage_runtime_mode": "auto"}) == ""
    assert resolved_sage_runtime_mode({"COMFYMODAL_SAGE_RUNTIME_MODE": "auto"}) == ""
    # 2-3. configured auto + observed
    assert resolved_sage_runtime_mode({"sage_env_mode": "auto", "sage_mode": "triton_fallback"}) == "triton_fallback"
    assert resolved_sage_runtime_mode({"sage_mode": "baked_cuda"}) == "baked_cuda"
    # 4. two observations both triton_fallback -> triton_fallback
    assert resolved_sage_runtime_mode({"sage_mode": "triton_fallback"}, {"resolved_sage_runtime_mode": "triton_fallback"}) == "triton_fallback"
    # 5. observed triton_fallback + observed baked_cuda -> mixed
    assert resolved_sage_runtime_mode({"sage_mode": "triton_fallback"}, {"sage_mode": "baked_cuda"}) == "mixed"
    # 6. policy auto + observed triton_fallback -> NOT mixed
    assert resolved_sage_runtime_mode({"sage_runtime_mode": "auto", "sage_env_mode": "auto", "sage_mode": "triton_fallback"}) == "triton_fallback"
    assert resolved_sage_runtime_mode({"configured_sage_runtime_mode": "auto"}, {"sage_mode": "triton_fallback"}) == "triton_fallback"

    # Persisted identity should store configured auto but resolved as observed (triton_fallback), not auto
    result = finalize_experiment_evidence(
        tmp_path,
        identity={
            "profile": "golden_p1",
            "v2ctl_invocation_id": "inv-sage",
            "configured_sage_runtime_mode": "auto",
            "resolved_sage_runtime_mode": "triton_fallback",
        },
        verdict="ACCEPT",
    )
    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert index["identity"]["configured_sage_runtime_mode"] == "auto"
    assert index["identity"]["resolved_sage_runtime_mode"] == "triton_fallback"
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "configured_sage_runtime_mode" in text
    assert "resolved_sage_runtime_mode" in text

    # completed real execution must not have resolved == auto
    assert resolved_sage_runtime_mode({"resolved_sage_runtime_mode": "auto"}) == ""


def test_evidence_ignores_runtime_resolved_sage_label_in_nested_identity(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "nested-sage-identity", invocation="inv-nested-sage")
    manifest = json.loads((cohort / "manifest.json").read_text(encoding="utf-8"))
    manifest.update({
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "golden_env",
        "sage_runtime_mode_resolved": "baked_cuda",
        "deployment_identity": {
            "deploy_fingerprint": "deploy-fp",
            "resources": {"cpu": 4, "gpu": "rtx-pro-6000", "memory_mb": 8192},
        },
    })
    (cohort / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    attempt = json.loads((cohort / "attempt_0.json").read_text(encoding="utf-8"))
    attempt.update({
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "golden_env",
        "sage_runtime_mode_resolved": "baked_cuda",
        "identity": {"sage_runtime_mode_configured": "baked_cuda"},
        "golden_telemetry": {"transport": {"predicates": {"fallback": True}}},
    })
    (cohort / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")

    result = finalize_experiment_evidence(
        tmp_path,
        identity={
            "profile": "golden_p1",
            "v2ctl_invocation_id": "inv-nested-sage",
            "configured_sage_runtime_mode": "auto",
            "sage_runtime_mode_configured": "auto",
            "sage_runtime_mode_effective_input": "auto",
            "sage_runtime_mode_resolution_source": "golden_env",
            "sage_runtime_mode_resolved": "baked_cuda",
        },
        verdict="ACCEPT",
        result=_owner(cohort),
    )

    indexed = _cohort_index(result)["nested-sage-identity"]
    assert indexed["exact"] == "EXACT"
    assert indexed["sage_runtime_mode_configured"] == "auto"
    assert indexed["deployment_fingerprint"] == "deploy-fp"
    assert indexed["ram"] == 8192
    assert indexed["fallback"] is False


def test_large_attempt_events_keep_integrity_metadata_without_embedding(tmp_path: Path):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "large-events", invocation="inv-large")
    events = cohort / "attempt_0_events.json"
    events.write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-large"},
        verdict="INCONCLUSIVE",
        result=_owner(cohort),
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
        result=_owner(cohort),
    )
    text = result.markdown_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(events.read_bytes()).hexdigest()
    assert "attempt_1_events.json" in text
    assert digest in text
    assert "cohort=later-events" in text
    assert "y" * 1000 not in text


def test_event_streams_are_not_parsed_for_path_references(tmp_path: Path, monkeypatch):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "event-paths", invocation="inv-event-paths")

    manifest_reference = tmp_path / "manifest-reference.txt"
    manifest_reference.write_text("manifest evidence", encoding="utf-8")
    manifest = json.loads((cohort / "manifest.json").read_text(encoding="utf-8"))
    manifest["evidence_path"] = str(manifest_reference)
    (cohort / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    event_reference = tmp_path / "event-reference.txt"
    event_reference.write_text("event evidence", encoding="utf-8")
    events = cohort / "attempt_0_events.json"
    with events.open("w", encoding="utf-8") as handle:
        json.dump(
            {
                "events": [
                    {"event": "progress", "evidence_path": str(event_reference)}
                    for _ in range(30_000)
                ]
            },
            handle,
        )

    original_read_json = evidence_module._read_json
    read_paths: list[str] = []

    def tracking_read_json(path: Path):
        read_paths.append(path.name)
        assert path.name != events.name
        return original_read_json(path)

    monkeypatch.setattr(evidence_module, "_read_json", tracking_read_json)
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-event-paths"},
        verdict="ACCEPT",
        result=_owner(cohort),
    )

    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    source_paths = {item["source_path"] for item in index["inventory"]}
    assert str(manifest_reference.resolve()) in source_paths
    assert str(event_reference.resolve()) not in source_paths
    assert "manifest.json" in read_paths
    assert "summary.json" in read_paths
    assert events.name not in read_paths
    assert any(item["source_path"] == str(events.resolve()) for item in index["inventory"])


def test_evidence_path_normalization_does_not_resolve_filesystem_paths(tmp_path: Path, monkeypatch):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "lexical-paths", invocation="inv-lexical-paths")

    def fail_resolve(self, *args, **kwargs):
        raise AssertionError("evidence finalization must not call Path.resolve()")

    monkeypatch.setattr(Path, "resolve", fail_resolve)
    relative_manifest = Path("artifacts") / "phase_p1_serial_golden_v1" / "lexical-paths" / "manifest.json"
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-lexical-paths"},
        verdict="ACCEPT",
        result=_owner(cohort),
        extra_paths=[cohort / "manifest.json", relative_manifest],
    )

    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    source_paths = {item["source_path"] for item in index["inventory"]}
    manifest_path = str(Path(os.path.abspath(cohort / "manifest.json")))
    assert manifest_path in source_paths
    assert sum(item["source_path"] == manifest_path for item in index["inventory"]) == 1
    assert result.status == "OK"


def test_large_non_event_json_is_not_parsed_or_embedded(tmp_path: Path, monkeypatch):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "large-json", invocation="inv-large-json")

    referenced = tmp_path / "should-not-be-projected.txt"
    referenced.write_text("large JSON reference", encoding="utf-8")
    large_json = tmp_path / "large-evidence.json"
    large_json.write_text(
        json.dumps({
            "evidence_path": str(referenced),
            "payload": "OVERSIZED_EVIDENCE_PAYLOAD",
            "padding": [0] * 400_000,
        }),
        encoding="utf-8",
    )
    assert large_json.stat().st_size > evidence_module._MAX_PATH_PROJECTION_BYTES

    original_read_text = Path.read_text
    original_read_json = evidence_module._read_json
    read_paths: list[str] = []

    def guarded_read_text(path: Path, *args, **kwargs):
        if path == large_json:
            raise AssertionError("oversized evidence source must not be read for markdown embedding")
        return original_read_text(path, *args, **kwargs)

    def tracking_read_json(path: Path):
        read_paths.append(path.name)
        assert path.name != large_json.name
        return original_read_json(path)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(evidence_module, "_read_json", tracking_read_json)
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-large-json"},
        verdict="ACCEPT",
        result=_owner(cohort),
        extra_paths=[large_json],
    )

    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    inventory = {item["source_path"]: item for item in index["inventory"]}
    assert str(large_json.resolve()) in inventory
    large_item = inventory[str(large_json.resolve())]
    assert Path(large_item["bundle_path"]).is_file()
    assert large_item["sha256"] == hashlib.sha256(large_json.read_bytes()).hexdigest()
    assert large_item["text_omitted"] is True
    assert large_item["omission_reason"] == "oversized evidence source; raw copy and integrity metadata retained"
    assert "OVERSIZED_EVIDENCE_PAYLOAD" not in result.markdown_path.read_text(encoding="utf-8")
    assert large_json.name not in read_paths
    assert str(referenced.resolve()) not in inventory


def test_path_projection_cutoff_is_inclusive_and_shared_with_embedding(tmp_path: Path, monkeypatch):
    cohort_root = tmp_path / "artifacts" / "phase_p1_serial_golden_v1"
    cohort = _cohort(cohort_root, "cutoff", invocation="inv-cutoff")

    at_reference = tmp_path / "at-cutoff-reference.txt"
    at_reference.write_text("included at cutoff", encoding="utf-8")
    over_reference = tmp_path / "over-cutoff-reference.txt"
    over_reference.write_text("excluded over cutoff", encoding="utf-8")

    def write_sized_json(path: Path, reference: Path, marker: str, size: int) -> None:
        prefix = {"evidence_path": str(reference), "marker": marker, "padding": ""}
        base_size = len(json.dumps(prefix, separators=(",", ":")).encode("utf-8"))
        padding_size = size - base_size
        assert padding_size >= 0
        value = dict(prefix)
        value["padding"] = "x" * padding_size
        encoded = json.dumps(value, separators=(",", ":")).encode("utf-8")
        assert len(encoded) == size
        path.write_bytes(encoded)

    cutoff = evidence_module._MAX_PATH_PROJECTION_BYTES
    at_cutoff = tmp_path / "at-cutoff.json"
    over_cutoff = tmp_path / "over-cutoff.json"
    write_sized_json(at_cutoff, at_reference, "AT_CUTOFF_MARKER", cutoff)
    write_sized_json(over_cutoff, over_reference, "OVER_CUTOFF_MARKER", cutoff + 1)

    original_read_text = Path.read_text
    original_read_json = evidence_module._read_json
    read_paths: list[str] = []

    def guarded_read_text(path: Path, *args, **kwargs):
        if path == over_cutoff:
            raise AssertionError("over-cutoff evidence must not be read for markdown embedding")
        return original_read_text(path, *args, **kwargs)

    def tracking_read_json(path: Path):
        read_paths.append(path.name)
        assert path.name != over_cutoff.name
        return original_read_json(path)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(evidence_module, "_read_json", tracking_read_json)
    # Keep this boundary test focused on the cutoff; the real redactor has a
    # costly regex scan on a 128 KiB payload and is covered separately.
    monkeypatch.setattr(evidence_module, "_redact", lambda text: text)
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "rx9p", "v2ctl_invocation_id": "inv-cutoff"},
        verdict="ACCEPT",
        result=_owner(cohort),
        extra_paths=[at_cutoff, over_cutoff],
    )

    index = json.loads((result.bundle_dir / "evidence_index.json").read_text(encoding="utf-8"))
    inventory = {item["source_path"]: item for item in index["inventory"]}
    at_item = inventory[str(at_cutoff.resolve())]
    over_item = inventory[str(over_cutoff.resolve())]
    assert at_item["bytes"] == cutoff
    assert over_item["bytes"] == cutoff + 1
    assert at_item["sha256"] == hashlib.sha256(at_cutoff.read_bytes()).hexdigest()
    assert over_item["sha256"] == hashlib.sha256(over_cutoff.read_bytes()).hexdigest()
    assert "text_omitted" not in at_item
    assert over_item["text_omitted"] is True
    assert str(at_reference.resolve()) in inventory
    assert str(over_reference.resolve()) not in inventory
    assert at_cutoff.name in read_paths
    assert over_cutoff.name not in read_paths
    text = result.markdown_path.read_text(encoding="utf-8")
    assert "AT_CUTOFF_MARKER" in text
    assert "OVER_CUTOFF_MARKER" not in text


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
    cohort_paths = [
        root / name
        for name in (
            "mismatch-warning", "failed", "adjacent-a", "adjacent-b",
            "multi-arm-a", "multi-arm-b", "mixed-backend", "missing-receipt",
        )
    ]
    result = finalize_experiment_evidence(
        tmp_path,
        identity={"profile": "golden_p1", "v2ctl_invocation_id": "fixture", "attention_backend": "pytorch"},
        verdict="INCONCLUSIVE",
        result=_owner(cohort_paths[0]),
        records=[_owner(path) for path in cohort_paths[1:]],
    )
    text = result.markdown_path.read_text(encoding="utf-8")
    for name in ("mismatch-warning", "failed", "adjacent-a", "adjacent-b", "mixed-backend", "missing-receipt", "multi-arm-a", "multi-arm-b"):
        assert name in text
    assert "mixed" in text.lower()
    assert "deployment receipt" in text
    assert _cohort_index(result)["failed"]["dnf"] == 1


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
        result=_owner(root / "exact"),
        records=[
            _owner(root / name)
            for name in ("mismatch", "missing-summary", "missing-summary-id", "missing-attempt-id", "malformed")
        ],
    )
    cohorts = _cohort_index(result)
    assert cohorts["exact"]["exact"] == "EXACT"
    assert cohorts["mismatch"]["exact"] == "MISMATCH"
    for name in ("missing-summary", "missing-summary-id", "missing-attempt-id", "malformed"):
        assert cohorts[name]["exact"] == "INCOMPLETE"
    assert any("missing-summary\\summary.json" in item or "missing-summary/summary.json" in item for item in cohorts["missing-summary"]["missing"])


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
