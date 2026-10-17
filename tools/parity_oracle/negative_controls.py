"""Negative controls: break behavior/metadata, prove harness/tests catch it, revert.

Behavior mutations touch real product files temporarily (restored in finally;
a grep for zzNo*/__broken__ must be clean afterwards). Metadata mutations
exercise the manifest validator against temp copies, never the real rows.

Usage: python tools/parity_oracle/negative_controls.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src"
ROWS = Path(__file__).resolve().parent / "rows"
SMOKE = "SMOKE::"


def _run_oracle() -> dict:
    r = subprocess.run([sys.executable, "-m", "tools.parity_oracle.run"],
                       cwd=str(REPO), capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-1500:]
    m = json.loads((REPO / "parity" / "manifest.json").read_text(encoding="utf-8"))
    return {s["id"]: s["smoke_result"] for s in m["legacy_smoke"]}


def _mutate(path: Path, old: str, new: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"mutation anchor missing in {path}"
    assert old not in new, "replacement must not contain the anchor"
    path.write_text(text.replace(old, new), encoding="utf-8")
    return text


def _behavior_control(name: str, path: Path, old: str, new: str, smoke_id: str) -> bool:
    print(f"[NC] {name}: breaking {path.relative_to(REPO)}")
    backup = _mutate(path, old, new)
    try:
        got = _run_oracle()[smoke_id]
        ok = got == "FAIL"
        print(f"     broken run: {smoke_id}={got} -> {'CAUGHT' if ok else 'MISSED (test invalid)'}")
        return ok
    finally:
        path.write_text(backup, encoding="utf-8")


def _vitest_bin() -> str:
    import shutil as _sh
    for cand in ("npx.cmd", "npx"):
        p = _sh.which(cand)
        if p:
            return p
    local = REPO / "frontend" / "node_modules" / ".bin" / "vitest.cmd"
    assert local.exists(), "no vitest/npx binary found"
    return str(local)


def _vitest_control() -> bool:
    target = SRC / "app" / "router" / "studioHistory.ts"
    text = target.read_text(encoding="utf-8")
    anchor = '"push"' if '"push"' in text else "'push'"
    assert anchor in text
    print("[NC] ROUTER-PUSH-REPLACE: inverting push/replace in studioHistory.ts")
    backup = text
    target.write_text(text.replace(anchor, '"__broken__"'), encoding="utf-8")
    try:
        binary = _vitest_bin()
        cmd = [binary, "vitest", "run", "src/app/router"] if "npx" in binary.lower() \
            else [binary, "run", "src/app/router"]
        r = subprocess.run(cmd, cwd=str(REPO / "frontend"), capture_output=True,
                           text=True, timeout=180, encoding="utf-8", errors="replace")
        ok = r.returncode != 0
        print(f"     broken run: vitest exit={r.returncode} -> {'CAUGHT' if ok else 'MISSED (test invalid)'}")
        return ok
    finally:
        target.write_text(backup, encoding="utf-8")


def _metadata_control(name: str, mutate) -> bool:
    """Run the validator against a temp rows-copy with a bogus row; expect rejection."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_manifest as bm
    tmp = Path(tempfile.mkdtemp())
    print(f"[NC] {name}")
    try:
        for f in ROWS.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        rows = []
        for f in sorted(tmp.glob("*.json")):
            rows.extend(json.loads(f.read_text(encoding="utf-8")))
        mutate(rows)
        problems = bm.validate(rows, {"no-provider-branch": (True, ""),
                                      "no-old-css": (True, ""),
                                      "teleport-body-present": (True, "")})
        ok = len(problems) > 0
        print(f"     validator problems={len(problems)} -> {'CAUGHT' if ok else 'MISSED (validator blind)'}")
        return ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    print("baseline run...")
    base = _run_oracle()
    for k in ("PG-SEED", "UP-GUARD", "PG-MODEL-ROLES", "GQ-EXPERIMENT"):
        assert base[SMOKE + k] == "PASS", (k, base)

    results = [
        ("NC-SEED-RANDOMIZE", _behavior_control(
            "NC-SEED-RANDOMIZE", SRC / "components" / "PlaygroundControls.vue",
            "randomizeSeed", "zzNoRandom", SMOKE + "PG-SEED")),
        ("NC-UPLOAD-GUARD", _behavior_control(
            "NC-UPLOAD-GUARD", SRC / "stores" / "playground.ts",
            "commitUpload", "zzNoGuard", SMOKE + "UP-GUARD")),
        ("NC-MODEL-ROLES", _behavior_control(
            "NC-MODEL-ROLES", SRC / "api" / "workflows.ts",
            "model_unet", "zzNoRole", SMOKE + "PG-MODEL-ROLES")),
        ("NC-EXP-RETRY", _behavior_control(
            "NC-EXP-RETRY", SRC / "api" / "history.ts",
            "retryExperimentCell", "zzNoRetry", SMOKE + "GQ-EXPERIMENT")),
        ("NC-ROUTER-UNIT", _vitest_control()),
        # False architecture PASS: PASS with required BROWSER but current STATIC.
        ("NC-BOGUS-ARCH-PASS", _metadata_control(
            "NC-BOGUS-ARCH-PASS",
            lambda rows: rows.append({"id": "NC-FAKE", "contract_type": "migration_architecture",
                                      "area": "operations", "behavior": "fake",
                                      "authorities": [{"kind": "migration_contract", "ref": "x"}],
                                      "required_evidence": ["BROWSER"], "current_evidence": ["STATIC"],
                                      "status": "PASS", "reason": "bogus",
                                      "legacy_evidence": "", "vue_evidence": "",
                                      "tests_or_traces": [], "implementation_invariant": "", "notes": ""}))),
        # Missing required behavior row shape: PASS with empty current evidence.
        ("NC-BOGUS-EVIDENCE", _metadata_control(
            "NC-BOGUS-EVIDENCE",
            lambda rows: rows.append({"id": "NC-FAKE2", "contract_type": "product_behavior",
                                      "area": "history", "behavior": "fake",
                                      "authorities": [{"kind": "legacy_impl", "ref": "x"}],
                                      "required_evidence": ["UNIT"], "current_evidence": [],
                                      "status": "PASS", "reason": "bogus",
                                      "legacy_evidence": "", "vue_evidence": "",
                                      "tests_or_traces": [], "implementation_invariant": "", "notes": ""}))),
        # Duplicate ID.
        ("NC-DUPLICATE-ID", _metadata_control(
            "NC-DUPLICATE-ID",
            lambda rows: rows.append(dict(rows[0])))),
    ]

    # Smoke contamination: atomic totals must be independent of smoke labels.
    print("[NC] SMOKE-QUARANTINE")
    m = json.loads((REPO / "parity" / "manifest.json").read_text(encoding="utf-8"))
    smoke_ids = {s["id"] for s in m["legacy_smoke"]}
    row_ids = {r["id"] for r in m["rows"]}
    counted = m["counts"]
    quarantine_ok = (not (smoke_ids & row_ids)
                     and sum(sum(d.values()) for d in counted["by_type"].values()) == len(m["rows"]))
    print(f"     no collision + counts==rows -> {'CAUGHT (guard holds)' if quarantine_ok else 'MISSED'}")
    results.append(("NC-SMOKE-QUARANTINE", quarantine_ok))

    print("restored run (must be green)...")
    base2 = _run_oracle()
    restored = all(base2[SMOKE + k] == "PASS" for k in ("PG-SEED", "UP-GUARD", "PG-MODEL-ROLES", "GQ-EXPERIMENT"))
    print(f"     restored: {'GREEN' if restored else 'NOT GREEN'}")

    print("\nnegative-control summary:")
    ok = True
    for name, passed in results:
        print(f" - {name}: {'caught' if passed else 'MISSED (test invalid)'}")
        ok = ok and bool(passed)
    print(f" - restore-green: {'yes' if restored else 'NO'}")
    ok = ok and restored
    _run_oracle()  # rebuild final artifacts unbroken
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
