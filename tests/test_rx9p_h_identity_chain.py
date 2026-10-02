"""FAST_UNIT: RX9P-H invocation + request binding and provenance tests.

No ComfyUI, no Modal, no Torch, no model scans.
All assertions are pure logic against tools.v2_control.experiment_evidence.
"""
from __future__ import annotations

import json
import ast
from pathlib import Path

import pytest

from tools.v2_control import experiment_evidence
from tools.v2_control.experiment_evidence import (
    _golden_p1_consensus,
    _golden_p1_runtime_provenance,
)

pytestmark = pytest.mark.fast_unit


def _benchmark_source() -> str:
    return (
        Path(__file__).resolve().parents[1] / "tools" / "benchmark_v2_direct.py"
    ).read_text(encoding="utf-8-sig")


def _cohort(tmp_path: Path, *, invocation_id: str, request_id: str, extra: dict | None = None):
    cohort = tmp_path / f"cohort_{invocation_id[:8]}"
    cohort.mkdir(parents=True, exist_ok=True)
    base = {
        "v2ctl_invocation_id": invocation_id,
        "request_id": request_id,
        "profile": "golden_p1",
        "profile_config_fingerprint": "fp-profile",
        "run_fingerprint": "fp-run",
        "expected_output_sha": "a" * 64,
        "attention_backend_configured": "pytorch",
        "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution",
        "sage_runtime_mode_resolved": "baked_cuda",
        "attempts": [{"v2ctl_invocation_id": invocation_id, "request_id": request_id}],
    }
    if extra:
        base.update(extra)
    (cohort / "manifest.json").write_text(json.dumps(base), encoding="utf-8")
    summary = {
        "v2ctl_invocation_id": invocation_id,
        "request_id": request_id,
        "attention_backend_configured": "pytorch",
        "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution",
        "sage_runtime_mode_resolved": "baked_cuda",
        "attempts": [{"v2ctl_invocation_id": invocation_id, "request_id": request_id}],
    }
    if extra:
        # propagate extras to summary where relevant
        for k in ("attention_backend_configured", "attention_backend_resolved",
                  "sage_runtime_mode_configured", "sage_runtime_mode_effective_input",
                  "sage_runtime_mode_resolution_source", "sage_runtime_mode_resolved"):
            if k in extra:
                summary[k] = extra[k]
                summary["attempts"][0][k] = extra[k]
    (cohort / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    attempt = {
        "v2ctl_invocation_id": invocation_id,
        "request_id": request_id,
        "valid": True,
        "dnf": False,
        "failures": [],
        "attention_backend_configured": "pytorch",
        "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution",
        "sage_runtime_mode_resolved": "baked_cuda",
    }
    if extra:
        for k in attempt:
            if k in extra:
                attempt[k] = extra[k]
    (cohort / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")
    return cohort


def _identity(invocation_id: str, request_id: str):
    return {
        "profile": "golden_p1",
        "v2ctl_invocation_id": invocation_id,
        "request_id": request_id,
        "profile_config_fingerprint": "fp-profile",
        "run_fingerprint": "fp-run",
        "attention_backend_configured": "pytorch",
        "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto",
        "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution",
        "sage_runtime_mode_resolved": "baked_cuda",
    }


def test_success_path_exact(tmp_path: Path):
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id=inv, request_id=req)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert c["exact"] == "EXACT", c


def test_missing_invocation_fails(tmp_path: Path):
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id="", request_id=req)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert c["exact"] in ("MISMATCH", "INCOMPLETE")


def test_missing_request_fails(tmp_path: Path):
    inv = "a" * 32
    cohort = _cohort(tmp_path, invocation_id=inv, request_id="")
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, "golden-p1-0-abc123"))
    assert c["exact"] in ("MISMATCH", "INCOMPLETE")


def test_adjacent_cohort_cannot_satisfy_current_invocation(tmp_path: Path):
    inv_current = "a" * 32
    inv_adjacent = "b" * 32
    req = "golden-p1-0-abc123"
    # Adjacent cohort has different invocation
    cohort = _cohort(tmp_path, invocation_id=inv_adjacent, request_id=req)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv_current, req))
    assert c["exact"] != "EXACT"
    assert any("v2ctl_invocation_id" in m for m in c["mismatch"])


def test_concurrent_cohort_cannot_satisfy_current_invocation(tmp_path: Path):
    inv_current = "a" * 32
    inv_concurrent = "c" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id=inv_concurrent, request_id=req)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv_current, req))
    assert c["exact"] != "EXACT"


def test_correct_invocation_wrong_request_fails(tmp_path: Path):
    inv = "a" * 32
    req_correct = "golden-p1-0-abc123"
    req_wrong = "golden-p1-0-wrong123"
    cohort = _cohort(tmp_path, invocation_id=inv, request_id=req_correct)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req_wrong))
    assert c["exact"] != "EXACT"


def test_wrong_invocation_correct_request_fails(tmp_path: Path):
    inv_correct = "a" * 32
    inv_wrong = "d" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id=inv_wrong, request_id=req)
    c = experiment_evidence._compact_cohort(cohort, _identity(inv_correct, req))
    assert c["exact"] != "EXACT"


def test_failure_path_marks_mismatch(tmp_path: Path):
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id=inv, request_id=req)
    # simulate failure attempt
    attempt = json.loads((cohort / "attempt_0.json").read_text(encoding="utf-8"))
    attempt["valid"] = False
    attempt["failures"] = ["injected failure"]
    (cohort / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert c["exact"] != "EXACT"


def test_timeout_dnf_path(tmp_path: Path):
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(tmp_path, invocation_id=inv, request_id=req)
    attempt = json.loads((cohort / "attempt_0.json").read_text(encoding="utf-8"))
    attempt["dnf"] = True
    attempt["valid"] = False
    (cohort / "attempt_0.json").write_text(json.dumps(attempt), encoding="utf-8")
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert c["exact"] != "EXACT"


def test_serialization_failure_no_durable_attempt(tmp_path: Path):
    # No attempt file -> INCOMPLETE, not fabricated EXACT
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = tmp_path / "cohort_no_attempt"
    cohort.mkdir()
    (cohort / "manifest.json").write_text(json.dumps({
        "v2ctl_invocation_id": inv, "profile": "golden_p1",
        "profile_config_fingerprint": "fp-profile", "run_fingerprint": "fp-run",
        "attempts": [{"v2ctl_invocation_id": inv, "request_id": req}],
        "attention_backend_configured": "pytorch", "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto", "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution", "sage_runtime_mode_resolved": "baked_cuda",
    }), encoding="utf-8")
    (cohort / "summary.json").write_text(json.dumps({
        "v2ctl_invocation_id": inv, "request_id": req,
        "attempts": [{"v2ctl_invocation_id": inv, "request_id": req}],
        "attention_backend_configured": "pytorch", "attention_backend_resolved": "pytorch",
        "sage_runtime_mode_configured": "auto", "sage_runtime_mode_effective_input": "auto",
        "sage_runtime_mode_resolution_source": "auto_resolution", "sage_runtime_mode_resolved": "baked_cuda",
    }), encoding="utf-8")
    c = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert c["exact"] == "INCOMPLETE"
    assert any("attempt_*.json" in m for m in c["missing"])


def test_runtime_telemetry_is_the_only_resolved_success_evidence():
    provenance = _golden_p1_runtime_provenance(
        {
            "attention_backend_resolved": "pytorch",
            "sage_runtime_mode_resolved": "baked_cuda",
            "sage_runtime_mode_effective_input": "auto",
            "sage_runtime_mode_resolution_source": "auto_resolution",
        },
        {},
        sage_effective_input="auto",
        sage_resolution_source="auto_resolution",
    )
    assert provenance["attention_backend_resolved"] == "pytorch"
    assert provenance["sage_runtime_mode_resolved"] == "baked_cuda"


def test_dnf_without_telemetry_cannot_be_projected_as_resolved_success():
    provenance = _golden_p1_runtime_provenance(
        None,
        {"attention_backend": "pytorch", "sage_runtime_mode_configured": "auto"},
        sage_effective_input="auto",
        sage_resolution_source="auto_resolution",
    )
    assert provenance["attention_backend_resolved"] == "missing"
    assert provenance["sage_runtime_mode_resolved"] == "missing"


def test_auto_and_nested_observed_sage_evidence_is_mixed():
    assert experiment_evidence.resolved_sage_runtime_mode(
        {"sage_runtime_mode_resolved": "auto"},
        {"full_trace_artifact": {"golden_telemetry": {"sage_runtime_mode_resolved": "baked_cuda"}}},
    ) == "mixed"


def test_provenance_auto_only_preserves_missing_sentinel():
    provenance = _golden_p1_runtime_provenance(
        {"sage_runtime_mode_resolved": "auto"},
        {},
        sage_effective_input="auto",
        sage_resolution_source="auto_resolution",
    )
    assert provenance["sage_runtime_mode_resolved"] == "missing"


def test_provenance_auto_and_nested_observed_sage_evidence_is_mixed():
    provenance = _golden_p1_runtime_provenance(
        {"sage_runtime_mode_resolved": "auto"},
        {"full_trace_artifact": {"golden_telemetry": {"sage_mode": "baked_cuda"}}},
        sage_effective_input="auto",
        sage_resolution_source="auto_resolution",
    )
    assert provenance["sage_runtime_mode_resolved"] == "mixed"


def test_provenance_policy_auto_does_not_conflict_with_observed_sage_mode():
    provenance = _golden_p1_runtime_provenance(
        {"sage_runtime_mode": "auto"},
        {"full_trace_artifact": {"golden_telemetry": {"sage_mode": "baked_cuda"}}},
        sage_effective_input="auto",
        sage_resolution_source="auto_resolution",
    )
    assert provenance["sage_runtime_mode_resolved"] == "baked_cuda"


def test_compact_nested_sage_observation_is_mismatch(tmp_path: Path):
    inv = "a" * 32
    req = "golden-p1-0-abc123"
    cohort = _cohort(
        tmp_path,
        invocation_id=inv,
        request_id=req,
        extra={
            "sage_runtime_mode_resolved": "auto",
            "full_trace_artifact": {
                "golden_telemetry": {"sage_mode": "baked_cuda"},
            },
        },
    )
    compact = experiment_evidence._compact_cohort(cohort, _identity(inv, req))
    assert compact["sage_runtime_mode_resolved"] == "mixed"
    assert compact["exact"] == "MISMATCH"


def test_contradictory_runtime_records_fail_closed():
    records = [
        {"attention_backend_resolved": "pytorch"},
        {"attention_backend_resolved": "sage"},
    ]
    assert _golden_p1_consensus(records, "attention_backend_resolved", "missing") == "mixed"


def test_golden_invocation_id_is_captured_once_and_summary_uses_local_value():
    benchmark_path = Path(__file__).resolve().parents[1] / "tools" / "benchmark_v2_direct.py"
    source = _benchmark_source()
    tree = ast.parse(source, filename=str(benchmark_path))
    run_node = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_run_golden_p1"
    )
    source = ast.get_source_segment(source, run_node) or ""
    assert source.count('os.environ.get("COMFYMODAL_V2CTL_INVOCATION_ID"') == 1
    assert '"v2ctl_invocation_id": invocation_id' in source


def test_fast_identity_tests_do_not_import_benchmark_runtime():
    source = Path(__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "tools.benchmark_v2_direct" not in modules


def test_benchmark_reexports_canonical_pure_identity_helpers():
    tree = ast.parse(_benchmark_source())
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "tools.v2_control.experiment_evidence"
        for alias in node.names
    }
    assert {
        "_golden_p1_consensus",
        "_golden_p1_runtime_provenance",
    } <= imported
    assert not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {
            "_golden_p1_consensus",
            "_golden_p1_runtime_provenance",
        }
        for node in tree.body
    )
