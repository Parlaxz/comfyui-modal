"""Parity oracle guard: v2 matrix valid; PASS implies required ⊆ current; smoke quarantined."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
STATUSES = {"PASS", "FAIL", "UNKNOWN", "NA", "INTENTIONAL_CHANGE"}
LEVELS = {"STATIC", "UNIT", "INTEGRATION", "BROWSER", "RACE", "REAL_BACKEND"}
TYPES = {"product_behavior", "migration_architecture", "retirement"}
REQUIRED_KEYS = {"id", "contract_type", "area", "behavior", "authorities",
                 "required_evidence", "current_evidence", "status", "reason",
                 "legacy_evidence", "vue_evidence", "tests_or_traces",
                 "implementation_invariant", "notes"}


@pytest.mark.fast_unit
def test_parity_manifest_valid_and_honest():
    r = subprocess.run([sys.executable, "-m", "tools.parity_oracle.run"],
                       cwd=str(REPO), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    manifest = json.loads((REPO / "parity" / "manifest.json").read_text(encoding="utf-8"))
    rows = manifest["rows"]
    assert len(rows) >= 250, f"matrix too small to be comprehensive: {len(rows)}"
    ids = [row["id"] for row in rows]
    assert len(set(ids)) == len(ids), "duplicate row ids"
    for row in rows:
        assert REQUIRED_KEYS <= set(row), row.get("id")
        assert row["status"] in STATUSES, row["id"]
        assert row["contract_type"] in TYPES, row["id"]
        assert isinstance(row["required_evidence"], list) and row["required_evidence"], row["id"]
        assert isinstance(row["current_evidence"], list) and row["current_evidence"], row["id"]
        assert set(row["required_evidence"]) <= LEVELS, row["id"]
        assert set(row["current_evidence"]) <= LEVELS, row["id"]
        assert row["authorities"], row["id"]
        if row["status"] == "PASS":
            assert set(row["required_evidence"]) <= set(row["current_evidence"]), row["id"]
        if row["status"] == "INTENTIONAL_CHANGE":
            assert any("blueprint" in str(a.get("ref", "")) or "Ahmed" in str(a) or "owner" in str(a.get("kind", ""))
                       for a in row["authorities"]), row["id"]
    # Legacy smoke harness is quarantined: never counted, never colliding.
    smoke = manifest["legacy_smoke"]
    assert len(smoke) == 17
    assert manifest["legacy_smoke_label"].startswith("LEGACY SMOKE")
    assert not ({s["id"] for s in smoke} & set(ids)), "smoke IDs collide with atomic rows"
    # Counts separate scopes and agree with rows.
    by_type = manifest["counts"]["by_type"]
    assert set(by_type) == TYPES or set(by_type) <= TYPES
    total = sum(sum(d.values()) for d in by_type.values())
    assert total == len(rows), "counts do not match rows"
    # Generated artifacts agree with manifest.
    report = (REPO / "parity" / "REPORT.md").read_text(encoding="utf-8")
    assert "LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS" in report
    assert "migration_architecture" in report and "retirement" in report
    coverage = (REPO / "parity" / "coverage.md").read_text(encoding="utf-8")
    assert "Needs BROWSER" in coverage and "Needs RACE" in coverage
    assert manifest["static_checks"]["no-provider-branch"]["ok"] is True
    assert manifest["static_checks"]["no-old-css"]["ok"] is True
