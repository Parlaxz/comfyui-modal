"""Build the frozen parity manifest from atomic row files + legacy smoke harness.

Inputs : tools/parity_oracle/rows/*.json (curated atomic rows, v2 schema)
Outputs: parity/manifest.json (single source of truth)
         parity/REPORT.md     (generated; never hand-edited)
         parity/coverage.md   (generated evidence gaps)

Validation:
 - unique IDs; full v2 field set; controlled vocab;
 - PASS requires set(required_evidence) <= set(current_evidence);
 - FAIL by code absence may carry current ["STATIC"] with absence noted;
 - every row has at least one authority;
 - legacy smoke statuses are quarantined under legacy_smoke and never
   counted in product/architecture/retirement totals.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ROWS_DIR = Path(__file__).resolve().parent / "rows"
PARITY = REPO / "parity"
SRC = REPO / "frontend" / "src"

STATUSES = {"PASS", "FAIL", "UNKNOWN", "NA", "INTENTIONAL_CHANGE"}
LEVELS = {"STATIC", "UNIT", "INTEGRATION", "BROWSER", "RACE", "REAL_BACKEND"}
TYPES = {"product_behavior", "migration_architecture", "retirement"}
REQUIRED_KEYS = {"id", "contract_type", "area", "behavior", "authorities",
                 "required_evidence", "current_evidence", "status", "reason",
                 "legacy_evidence", "vue_evidence", "tests_or_traces",
                 "implementation_invariant", "notes"}


def _grep_count(root: Path, include: str, pattern: str) -> list[str]:
    hits = []
    rx = re.compile(pattern)
    for p in root.rglob(include):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rx.search(text):
            hits.append(str(p.relative_to(REPO)))
    return hits


def run_static_checks() -> dict:
    out = {}
    prov = _grep_count(SRC, "*.ts", r"[Ii]deogram|[Qq]wen|[Ff]lux")
    prov += _grep_count(SRC, "*.vue", r"[Ii]deogram|[Qq]wen|[Ff]lux")
    out["no-provider-branch"] = (len(prov) == 0, f"hits={prov}")
    old = _grep_count(SRC, "*.ts", r"studio-styles|testing-styles")
    old += _grep_count(SRC, "*.vue", r"studio-styles|testing-styles")
    out["no-old-css"] = (len(old) == 0, f"hits={old}")
    tele = _grep_count(SRC, "*.vue", r"<Teleport to=\"body\">")
    out["teleport-body-present"] = (len(tele) > 0, f"hits={tele}")
    return out


def load_rows() -> list[dict]:
    rows = []
    for f in sorted(ROWS_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        assert isinstance(data, list), f
        for r in data:
            r["_source_file"] = f.name
            rows.append(r)
    ids = [r["id"] for r in rows]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate row ids: {dupes}"
    return rows


NAV_KILL = re.compile(r"abort.{0,40}navigat|kill.{0,30}navigat|navigat.{0,30}kill", re.I)
NAV_CONTINUE = re.compile(r"navigat.{0,60}does\s+not.{0,60}(kill|abort|stop|cancel)|continu.{0,40}across.{0,20}(navigat|page)|must\s+not\s+die", re.I)
DOM_FREEZE = re.compile(r"exact\s+(old\s+)?(selector|test-?id|wording|class|dom)|legacy\s+(class|dom|selector)|wording\s+preserv|selectors?\s+preserv", re.I)
MECH_FREEZE = re.compile(
    r"canvas\s*2d.{0,40}(required|requires|must|needs)|"
    r"single-threaded.{0,40}(required|requires|must|needs)|"
    r"(requires|must|needs).{0,40}canvas\s*2d|"
    r"(requires|must|needs).{0,40}single-threaded", re.I)


def contract_guards(rows: list[dict]) -> list[str]:
    """Targeted guards against recurring oracle mistakes (cheap keyword rules)."""
    problems = []
    nav_rows = [r for r in rows
                if "poll" in r["id"].lower() or "poll" in r.get("area", "").lower()
                or "long-running" in r.get("behavior", "").lower()]
    def _affirmative_kill(text: str) -> bool:
        # A kill/abort requirement counts only when neither the match nor its
        # surroundings negate it ("does NOT kill", "never aborts"). Negated
        # mentions are the corrected policy, not the contradiction.
        for m in NAV_KILL.finditer(text):
            window = (text[max(0, m.start() - 24):m.start()] + " " + m.group(0)).lower()
            if re.search(r"\b(not|never|without|no|isn't)\b", window):
                continue
            return True
        return False
    if any(_affirmative_kill(r.get("behavior", "") or "") for r in nav_rows) and \
       any(NAV_CONTINUE.search(r.get("behavior", "") or "") for r in nav_rows):
        problems.append("contradictory navigation-poll policy: rows both require and forbid abort/kill on navigation")
    for r in rows:
        blob = " ".join(str(r.get(k, "") or "") for k in ("behavior", "reason", "notes"))
        exempt = bool(re.search(r"\bNOT\b.{0,80}(migration\s+)?requirements?", blob))
        is_engine_row = "sketch" in r["id"].lower() or r["id"].startswith(("POST", "SK"))
        if not exempt and is_engine_row and DOM_FREEZE.search(blob):
            problems.append(f"{r['id']}: reused-engine row freezes old DOM/copy (selectors/test-ids/wording/classes)")
        if (r["id"].startswith("POST") or r["area"] == "post") and MECH_FREEZE.search(blob):
            problems.append(f"{r['id']}: post row freezes implementation mechanism (Canvas 2D / single-threaded)")
    return problems


def validate(rows: list[dict], checks: dict) -> list[str]:
    problems = []
    ids = [r.get("id") or "" for r in rows]
    dupes = sorted({i for i in ids if i and ids.count(i) > 1})
    if dupes:
        problems.append(f"duplicate row ids: {dupes}")
    problems.extend(contract_guards(rows))
    for r in rows:
        missing = REQUIRED_KEYS - set(r)
        if missing:
            problems.append(f"{r.get('id')}: missing keys {sorted(missing)}")
            continue
        if r["status"] not in STATUSES:
            problems.append(f"{r['id']}: bad status {r['status']}")
        if r["contract_type"] not in TYPES:
            problems.append(f"{r['id']}: bad contract_type {r['contract_type']}")
        for k in ("required_evidence", "current_evidence"):
            v = r[k]
            if not isinstance(v, list) or not v or any(x not in LEVELS for x in v):
                problems.append(f"{r['id']}: bad evidence set {k}={v}")
        if not r.get("authorities"):
            problems.append(f"{r['id']}: no authorities")
        if r["status"] == "PASS" and not set(r["required_evidence"]) <= set(r["current_evidence"]):
            problems.append(f"{r['id']}: PASS requires {r['required_evidence']} but current is {r['current_evidence']}")
        if r["status"] == "INTENTIONAL_CHANGE" and not any(
                a.get("ref", "").startswith("blueprint") or "Ahmed" in str(a) for a in r["authorities"]):
            problems.append(f"{r['id']}: INTENTIONAL_CHANGE without binding authority cite")
    if not checks["no-provider-branch"][0]:
        problems.append(f"STATIC-CHECK no-provider-branch broken: {checks['no-provider-branch'][1]}")
    if not checks["no-old-css"][0]:
        problems.append(f"STATIC-CHECK no-old-css broken: {checks['no-old-css'][1]}")
    if not checks["teleport-body-present"][0]:
        problems.append("STATIC-CHECK teleport-body-present broken (WZ-PORTAL evidence changed)")
    return problems


def run_legacy_smoke() -> list[dict]:
    """Old 17-case differential smoke harness. Diagnostic only.

    Output is labeled LEGACY SMOKE and quarantined: it never enters totals.
    """
    from . import legacy_adapter, vue_adapter
    from .comparator import compare, roll_up
    from .scenarios import SCENARIOS

    def resolve(trace, dotted):
        cur = trace.to_dict()
        for part in dotted.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else cur
        return cur

    out = []
    for sc in SCENARIOS:
        leg = legacy_adapter.build_trace(sc["id"], sc["fixture"])
        vue = vue_adapter.build_trace(sc["id"], sc["fixture"])
        checks, verdicts = [], []
        for field in sc["checks"]:
            v, detail = compare(field, resolve(leg, field), resolve(vue, field))
            verdicts.append(v)
            checks.append({"field": field, "verdict": v, "detail": detail})
        out.append({"id": "SMOKE::" + sc["id"], "fixture": sc["fixture"], "smoke_result": roll_up(verdicts),
                    "checks": checks, "note": sc.get("note", "")})
    return out


def counts(rows: list[dict]) -> dict:
    by_type: dict[str, dict[str, int]] = {}
    for r in rows:
        t = by_type.setdefault(r["contract_type"], {})
        t[r["status"]] = t.get(r["status"], 0) + 1
    total: dict[str, int] = {}
    for t in by_type.values():
        for k, v in t.items():
            total[k] = total.get(k, 0) + v
    return {"by_type": by_type, "total": total, "rows": len(rows)}


def write_report(manifest: dict) -> None:
    rows = manifest["rows"]
    c = manifest["counts"]
    L = [f"# Legacy-vs-Vue Parity Report",
         "",
         f"Generated from `parity/manifest.json` at {manifest['generated_at']} (sha {manifest['repo_sha']}).",
         "The atomic manifest below is authoritative. The legacy smoke section at the end is",
         "LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS and never enters totals.",
         "",
         "## Totals by contract type", "",
         "| scope | PASS | FAIL | UNKNOWN | NA | INTENTIONAL_CHANGE |",
         "|---|---|---|---|---|---|"]
    for t in ("product_behavior", "migration_architecture", "retirement"):
        d = c["by_type"].get(t, {})
        L.append(f"| {t} | {d.get('PASS', 0)} | {d.get('FAIL', 0)} | {d.get('UNKNOWN', 0)} | "
                 f"{d.get('NA', 0)} | {d.get('INTENTIONAL_CHANGE', 0)} |")
    d = c["total"]
    L.append(f"| Total | {d.get('PASS', 0)} | {d.get('FAIL', 0)} | {d.get('UNKNOWN', 0)} | "
             f"{d.get('NA', 0)} | {d.get('INTENTIONAL_CHANGE', 0)} |")
    L += ["", "## Atomic matrix", "",
          "| id | scope | area | behavior | status | required / current | reason |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['id']} | {r['contract_type']} | {r['area']} | {r['behavior']} | {r['status']} | "
                 f"{','.join(r['required_evidence'])} / {','.join(r['current_evidence'])} | {r['reason']} |")
    fails = [r for r in rows if r["status"] == "FAIL" and r["contract_type"] == "product_behavior"]
    L += ["", "## Product failures (ranked)", ""]
    rank = {"broken core behavior": [], "safety/race failure": [], "missing feature": [],
            "missing QoL": [], "presentation difference": []}
    for r in fails:
        if r["area"] in ("playground", "generate/sketch", "generate/text", "edit/select") or \
                r["id"].startswith(("PG-MODEL", "WZ-SUG", "SK-", "LAY-", "GUI-", "POST-")):
            rank["broken core behavior"].append(r["id"])
        elif "safety" in r["reason"].lower() or r["contract_type"] == "product_behavior" and \
                ("RACE" in r["required_evidence"] or "gate" in r["behavior"].lower() or "freeze" in r["behavior"].lower() or "frozen" in r["behavior"].lower()):
            rank["safety/race failure"].append(r["id"])
        elif "qol" in r["area"] or "Advanced" in r["behavior"] or "order" in r["behavior"].lower() or "reorder" in r["behavior"].lower():
            rank["missing QoL"].append(r["id"])
        elif "overlay" in r["behavior"].lower() or "portal" in r["behavior"].lower():
            rank["presentation difference"].append(r["id"])
        else:
            rank["missing feature"].append(r["id"])
    for k, v in rank.items():
        L.append(f"- {k}: {', '.join(v) or 'none'}")
    L += ["", "## Unknowns (evidence required)", ""]
    for r in rows:
        if r["status"] == "UNKNOWN":
            L.append(f"- {r['id']} needs {','.join(r['required_evidence'])} (has {','.join(r['current_evidence'])}): {r['reason']}")
    L += ["", "## LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS", "",
          "The 17 legacy differential scenarios below are diagnostic only. Their labels must not be",
          "quoted as parity evidence and never enter the totals above.", ""]
    for s in manifest["legacy_smoke"]:
        L.append(f"- {s['id']} [{s['fixture']}]: {s['smoke_result']}" + (f" — {s['note']}" if s["note"] else ""))
    L.append("")
    (PARITY / "REPORT.md").write_text("\n".join(L), encoding="utf-8")


def write_coverage(manifest: dict) -> None:
    rows = manifest["rows"]
    L = ["# Parity coverage gaps", "",
         "Unresolved rows grouped by the evidence still required.",
         "These groups OVERLAP by design: evidence is a set, so one row appears under every",
         "level it still needs. Do not sum groups; manifest counts are the row totals.", ""]
    for level in ["BROWSER", "RACE", "REAL_BACKEND", "INTEGRATION", "UNIT", "STATIC"]:
        need = [r for r in rows if r["status"] in ("UNKNOWN", "FAIL")
                and level in r["required_evidence"] and level not in r["current_evidence"]]
        L.append(f"## Needs {level} ({len(need)})")
        L.append("")
        for r in need:
            L.append(f"- {r['id']} [{r['status']}/{r['contract_type']}] {r['area']}: {r['behavior']}")
        L.append("")
    (PARITY / "coverage.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO)).decode().strip()
    except Exception:
        sha = "unknown"
    checks = run_static_checks()
    rows = load_rows()
    problems = validate(rows, checks)
    if problems:
        print("MANIFEST VALIDATION FAILED:")
        for p in problems:
            print(" -", p)
        return 1
    smoke = run_legacy_smoke()
    smoke_ids = {s["id"] for s in smoke}
    assert not (smoke_ids & {r["id"] for r in rows}), "smoke IDs must not collide with atomic row IDs"
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "repo_sha": sha,
                "oracle": "parity/ORACLE_FREEZE.json",
                "migration_contract": "docs/VUE_MIGRATION_BLUEPRINT.md (revised; binding for architecture)",
                "verdict_rule": ("PASS only when required_evidence ⊆ current_evidence. "
                                 "FAIL provable by code absence with current ['STATIC']. "
                                 "No hand-typed PASS; no LIKELY PARITY."),
                "counts": counts(rows),
                "static_checks": {k: {"ok": v[0], "detail": v[1]} for k, v in checks.items()},
                "legacy_smoke": smoke,
                "legacy_smoke_label": "LEGACY SMOKE HARNESS OUTPUT — NOT PARITY VERDICTS",
                "rows": rows}
    (PARITY / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    write_report(manifest)
    write_coverage(manifest)
    d = manifest["counts"]["total"]
    print(f"rows={len(rows)} PASS={d.get('PASS', 0)} FAIL={d.get('FAIL', 0)} UNKNOWN={d.get('UNKNOWN', 0)} "
          f"NA={d.get('NA', 0)} IC={d.get('INTENTIONAL_CHANGE', 0)} smoke={len(smoke)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
