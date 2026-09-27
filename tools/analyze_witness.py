#!/usr/bin/env python
"""TEST 1 — scope the freeze.

For every pathological read, measure how long each of the five witnesses
stopped ticking inside that read's window.

Witnesses:
  1 reader Python canary (own worker)      2 reader native pthread canary (own worker)
  3 control-process Python canary          4 control-process native canary
  5 parent/coordinator Python canary
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from comfymodal_runtime.source_race_oracle import percentile  # noqa: E402

_MIB = 1024 * 1024


def _norm_cloud(v: Any) -> str:
    t = str(v or "").strip().lower()
    return t[len("cloud_provider_"):] if t.startswith("cloud_provider_") else t


def _f(v, d=1):
    return "-" if v is None else f"{float(v):.{d}f}"


def max_gap(ticks: list[int], lo: int, hi: int) -> tuple[float, int | None, int | None]:
    """Largest consecutive-tick gap whose interval overlaps [lo, hi]."""
    best, a_best, b_best = 0.0, None, None
    for i in range(1, len(ticks)):
        a, b = ticks[i - 1], ticks[i]
        if b < lo or a > hi:
            continue
        gap = (b - a) / 1e6
        if gap > best:
            best, a_best, b_best = gap, a, b
    return best, a_best, b_best


def median_gap(ticks: list[int]) -> float:
    if len(ticks) < 3:
        return float("nan")
    g = [(ticks[i] - ticks[i - 1]) / 1e6 for i in range(1, len(ticks))]
    return percentile(g, 50)


def load(dir_path: Path, glob_pat: str) -> list[dict[str, Any]]:
    out = []
    for path in sorted(glob.glob(str(dir_path / glob_pat))):
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") != "ok":
            continue
        if not (d.get("coverage") or {}).get("covers_entire_file_exactly_once"):
            continue
        d["_file"] = Path(path).name
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="witness_runs")
    ap.add_argument("--glob", default="*invalid*.json")
    ap.add_argument("--sick-ms", type=float, default=250.0)
    ap.add_argument("--out", default="TEST1_FREEZE_SCOPE.md")
    args = ap.parse_args()

    runs = load(_ROOT / args.dir, args.glob)
    lines: list[str] = []

    def say(t: str = "") -> None:
        lines.append(t)
        print(t, flush=True)

    say(f"# TEST 1 — freeze scope ({len(runs)} usable witness runs, no new runs)")
    say()
    if not runs:
        say("no usable runs found")
        return 1

    # baseline tick health per witness type
    base = {"reader_py": [], "reader_nc": [], "control_py": [], "control_nc": [], "parent_py": []}
    for d in runs:
        for w, tl in (d.get("witness_reader_py_ticks") or {}).items():
            base["reader_py"].append(median_gap(tl))
        for w, tl in (d.get("witness_reader_nc_ticks") or {}).items():
            base["reader_nc"].append(median_gap(tl))
        base["control_py"].append(median_gap(d.get("witness_control_py_ticks") or []))
        base["control_nc"].append(median_gap(d.get("witness_control_nc_ticks") or []))
        base["parent_py"].append(median_gap(d.get("witness_parent_py_ticks") or []))

    say("## Witness tick health (median inter-tick gap, ms)")
    say()
    say("| witness | median of medians | p90 | max |")
    say("|---|---:|---:|---:|")
    for k, v in base.items():
        v = [x for x in v if x == x]
        if not v:
            say(f"| {k} | - | - | - |")
            continue
        say(f"| {k} | {_f(percentile(v,50),2)} | {_f(percentile(v,90),2)} | {_f(max(v),2)} |")
    say()

    rows = []
    for d in runs:
        ident = d.get("identity") or {}
        where = f"{_norm_cloud(ident.get('provider'))}:{ident.get('region')}"
        rpy = {int(k): v for k, v in (d.get("witness_reader_py_ticks") or {}).items()}
        rnc = {int(k): v for k, v in (d.get("witness_reader_nc_ticks") or {}).items()}
        cpy = d.get("witness_control_py_ticks") or []
        cnc = d.get("witness_control_nc_ticks") or []
        ppy = d.get("witness_parent_py_ticks") or []
        for r in d.get("reads") or []:
            dur = float(r.get("preadv_ms") or 0.0)
            if dur < args.sick_ms:
                continue
            w = int(r["worker"])
            lo, hi = int(r["preadv_enter_ns"]), int(r["preadv_exit_ns"])
            own_py, a1, b1 = max_gap(rpy.get(w, []), lo, hi)
            own_nc, _, _ = max_gap(rnc.get(w, []), lo, hi)
            others = [max_gap(v, lo, hi)[0] for k, v in rpy.items() if k != w]
            c_py, _, _ = max_gap(cpy, lo, hi)
            c_nc, _, _ = max_gap(cnc, lo, hi)
            p_py, _, _ = max_gap(ppy, lo, hi)
            rows.append({
                "run": d["_file"], "where": where, "worker": w, "dur": dur,
                "enter": lo, "exit": hi,
                "own_py": own_py, "own_nc": own_nc,
                "other_py_max": max(others) if others else 0.0,
                "control_py": c_py, "control_nc": c_nc, "parent_py": p_py,
                "gap_start": a1, "gap_end": b1,
                "saved": dur - max(own_py, own_nc),
            })

    rows.sort(key=lambda r: -r["dur"])
    say(f"## Pathological reads (>= {args.sick_ms:.0f} ms): {len(rows)} across "
        f"{len({r['run'] for r in rows})} runs")
    say()
    say("| run | provider/region | worker | preadv dur | reader Py gap | reader native gap | "
        "other reader Py gaps (max) | control Py gap | control native gap | parent gap |")
    say("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in rows[:60]:
        say(f"| {r['run']} | {r['where']} | {r['worker']} | {_f(r['dur'])} | "
            f"{_f(r['own_py'])} | {_f(r['own_nc'])} | {_f(r['other_py_max'])} | "
            f"{_f(r['control_py'])} | {_f(r['control_nc'])} | {_f(r['parent_py'])} |")
    if len(rows) > 60:
        say(f"| … {len(rows)-60} more rows in the CSV | | | | | | | | | |")
    say()

    say("## Enter / gap / exit detail (top 20 by duration)")
    say()
    say("| run | worker | enter (rel ms) | reader Py gap start (rel ms) | gap end (rel ms) | exit (rel ms) |")
    say("|---|---:|---:|---:|---:|---:|")
    for r in rows[:20]:
        t0 = r["enter"]
        say(f"| {r['run']} | {r['worker']} | 0.0 | "
            f"{_f((r['gap_start']-t0)/1e6) if r['gap_start'] else '-'} | "
            f"{_f((r['gap_end']-t0)/1e6) if r['gap_end'] else '-'} | {_f(r['dur'])} |")
    say()

    say("## Gap magnitudes vs baseline")
    say()
    for label, key in (("reader Py (own)", "own_py"), ("reader native (own)", "own_nc"),
                       ("other readers Py (max)", "other_py_max"),
                       ("control Py", "control_py"), ("control native", "control_nc"),
                       ("parent Py", "parent_py")):
        v = [r[key] for r in rows]
        say(f"- {label:<26} median={_f(percentile(v,50))} ms  p90={_f(percentile(v,90))}  "
            f"max={_f(max(v))} ms")
    say()

    # classification per sick read
    def cls(r: dict[str, Any]) -> str:
        thr = max(50.0, 0.4 * r["dur"])
        py = r["own_py"] >= thr
        nc = r["own_nc"] >= thr
        ctl = max(r["control_py"], r["control_nc"], r["parent_py"]) >= thr
        oth = r["other_py_max"] >= thr
        if ctl and (py or nc):
            return "D_whole_sandbox"
        if py and not nc:
            return "A_python_only"
        if py and nc:
            return "C_all_readers" if oth else "B_whole_reader_process"
        if nc and not py:
            return "E_native_only"
        return "E_neither_froze"

    counts: dict[str, int] = {}
    for r in rows:
        c = cls(r)
        r["class"] = c
        counts[c] = counts.get(c, 0) + 1
    say("## Classification of the 5 witnesses, per sick read")
    say()
    say("| class | meaning | count | share |")
    say("|---|---|---:|---:|")
    meaning = {
        "A_python_only": "only Python threads freeze",
        "B_whole_reader_process": "whole affected reader process freezes",
        "C_all_readers": "all reader processes freeze, control survives",
        "D_whole_sandbox": "control also freezes -> whole sandbox",
        "E_native_only": "native froze, Python did not",
        "E_neither_froze": "no witness froze (gap elsewhere)",
    }
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        say(f"| {k} | {meaning.get(k,'')} | {v} | {100.0*v/len(rows):.0f}% |")
    say()

    (_ROOT / args.dir / args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    import csv
    with (_ROOT / args.dir / "test1_sick_reads.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k != "saved"], extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwritten: {args.out}, test1_sick_reads.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
