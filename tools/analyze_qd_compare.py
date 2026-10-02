#!/usr/bin/env python
"""QD4 vs QD8 at fixed 4.0 ms global launch spacing.

Pools all physical preadv records per arm, plus run-level distributions.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

D = Path(__file__).resolve().parents[1] / "qd_compare_runs"
ARMS = [("QD4", 4), ("QD8", 8)]


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def sd(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def load(qd: int) -> list[dict[str, Any]]:
    runs = []
    for p in sorted(D.glob(f"qc-q{qd}-*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        if "H100" not in str((r.get("identity") or {}).get("observed_gpu") or ""):
            continue
        runs.append(r)
    return runs


def generations(run: dict[str, Any], g: int) -> list[float]:
    per: dict[int, list[dict]] = {}
    for x in run["reads"]:
        per.setdefault(x["worker"], []).append(x)
    out = []
    for _w, xs in per.items():
        xs = sorted(xs, key=lambda z: z["preadv_enter_ns"])
        if len(xs) > g:
            out.append(xs[g]["preadv_ms"])
    return out


def line(label: str, xs: list[float], unit: str = "ms") -> None:
    if not xs:
        print(f"  {label}: (none)")
        return
    print(f"  {label:<12} best={min(xs):>9.2f}  p10={pct(xs,10):>9.2f}  "
          f"median={statistics.median(xs):>9.2f}  mean={statistics.fmean(xs):>9.2f}  "
          f"p95={pct(xs,95):>9.2f}  p99={pct(xs,99):>9.2f}  worst={max(xs):>9.2f}  "
          f"SD={sd(xs):>8.2f}  [{unit}]")


def main() -> int:
    data: dict[str, dict[str, Any]] = {}
    for name, qd in ARMS:
        runs = load(qd)
        pooled = [x["preadv_ms"] for r in runs for x in r["reads"]]
        data[name] = {
            "qd": qd, "runs": runs, "n": len(runs), "pooled": pooled,
            "wall": [r["full_file_wall_ms"] for r in runs],
            "gbps": [r["full_file_decimal_gbps"] for r in runs],
            "ovl": [(r.get("launch_spacing") or {}).get("frac_entered_with_other_active")
                    for r in runs],
            "conc": [(r.get("launch_spacing") or {}).get("mean_effective_concurrency")
                     for r in runs],
            "gmin": [(r.get("launch_spacing") or {}).get("observed_min_inter_start_ms")
                     for r in runs],
            "gp10": [(r.get("launch_spacing") or {}).get("observed_p5_inter_start_ms")
                     for r in runs],
            "gmed": [(r.get("launch_spacing") or {}).get("observed_median_inter_start_ms")
                     for r in runs],
            "gp95": [(r.get("launch_spacing") or {}).get("observed_p95_inter_start_ms")
                     for r in runs],
            "mx": [(r.get("launch_spacing") or {}).get("max_simultaneous_in_flight")
                   for r in runs],
        }
        for k in ("ovl", "conc", "gmin", "gp10", "gmed", "gp95", "mx"):
            data[name][k] = [v for v in data[name][k] if v is not None]

    W = 100
    print("=" * W)
    print("QD4 vs QD8 @ 4.0 ms global launch spacing")
    print("=" * W)
    for name, d in data.items():
        print(f"  {name}: {d['n']} runs, {len(d['pooled'])} pooled reads")

    # ---------- pooled preadv ----------
    print("\n=== POOLED PREADV (all physical reads, pathological reads INCLUDED) ===")
    for name, d in data.items():
        p = d["pooled"]
        if not p:
            continue
        print(f"\n[{name}]  reads={len(p)}")
        print(f"  best={min(p):.2f} p10={pct(p,10):.2f} median={statistics.median(p):.2f} "
              f"mean={statistics.fmean(p):.2f} p95={pct(p,95):.2f} p99={pct(p,99):.2f} "
              f"worst={max(p):.2f} SD={sd(p):.2f}  (ms)")
        for t in (250, 500, 1000, 2000, 5000):
            c = sum(1 for v in p if v >= t)
            print(f"    >= {t:>5} ms : {c:>4}  ({100.0*c/len(p):.3f}%)")

    # ---------- per-run distribution ----------
    print("\n=== PER-RUN DISTRIBUTION ===")
    for name, d in data.items():
        print(f"\n[{name}]")
        line("wall ms", d["wall"])
        line("GB/s", d["gbps"], "GB/s")
        print(f"  mean total wall = {statistics.fmean(d['wall']):.1f} ms "
              f"= {statistics.fmean(d['wall'])/1000.0:.3f} s")

    # ---------- tails ----------
    print("\n=== TAIL BEHAVIOR ===")
    for name, d in data.items():
        p = d["pooled"]
        r500 = sum(1 for r in d["runs"] if (r.get("thresholds") or {}).get("ge_500", 0) > 0)
        r1k = sum(1 for r in d["runs"] if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)
        n500 = sum(1 for v in p if v >= 500)
        n1k = sum(1 for v in p if v >= 1000)
        wr = max(d["runs"], key=lambda r: r.get("max_ms") or 0)
        print(f"\n[{name}] runs with >=500ms: {r500}/{d['n']}   runs with >=1000ms: {r1k}/{d['n']}")
        print(f"        physical reads >=500ms: {n500}   >=1000ms: {n1k}")
        print(f"        worst read {wr.get('max_ms'):.0f} ms in {wr.get('attempt_id')} "
              f"({wr.get('region')})")

    # ---------- pace validity ----------
    print("\n=== PACER VALIDITY (observed launch gaps, ms) ===")
    for name, d in data.items():
        print(f"  {name}: min={min(d['gmin']):.3f} (range {min(d['gmin']):.3f}-{max(d['gmin']):.3f})  "
              f"p10~{statistics.median(d['gp10']):.2f}  median={statistics.median(d['gmed']):.2f}  "
              f"p95~{statistics.median(d['gp95']):.2f}")

    # ---------- concurrency ----------
    print("\n=== CONCURRENCY ===")
    for name, d in data.items():
        print(f"  {name}: overlap mean={statistics.fmean(d['ovl']):.3f} "
              f"median={statistics.median(d['ovl']):.3f} | eff conc mean={statistics.fmean(d['conc']):.2f} "
              f"median={statistics.median(d['conc']):.2f} | max active={max(d['mx'])}")

    # ---------- generation ----------
    print("\n=== GENERATION ANALYSIS ===")
    print(f"{'QD':>4}{'gen':>5}{'n':>6}{'median':>9}{'mean':>10}{'p95':>9}{'worst':>9}{'>=500':>7}{'>=1000':>7}")
    for name, d in data.items():
        for g in range(0, 6):
            vals = [v for r in d["runs"] for v in generations(r, g)]
            if not vals:
                continue
            tag = f"g{g}" if g < 5 else "g4+"
            if g == 5:
                continue
            print(f"{name:>4}{tag:>5}{len(vals):>6}{statistics.median(vals):>9.2f}"
                  f"{statistics.fmean(vals):>10.2f}{pct(vals,95):>9.2f}{max(vals):>9.0f}"
                  f"{sum(1 for v in vals if v>=500):>7}{sum(1 for v in vals if v>=1000):>7}")

    # ---------- headline ----------
    print("\n=== HEADLINE COMPARISON ===")
    q4, q8 = data["QD4"], data["QD8"]
    p4, p8 = q4["pooled"], q8["pooled"]
    rows = [
        ("runs", q4["n"], q8["n"]),
        ("total reads", len(p4), len(p8)),
        ("preadv best", f"{min(p4):.2f}", f"{min(p8):.2f}"),
        ("preadv p10", f"{pct(p4,10):.2f}", f"{pct(p8,10):.2f}"),
        ("preadv median", f"{statistics.median(p4):.2f}", f"{statistics.median(p8):.2f}"),
        ("preadv mean", f"{statistics.fmean(p4):.2f}", f"{statistics.fmean(p8):.2f}"),
        ("preadv p95", f"{pct(p4,95):.2f}", f"{pct(p8,95):.2f}"),
        ("preadv p99", f"{pct(p4,99):.2f}", f"{pct(p8,99):.2f}"),
        ("preadv worst", f"{max(p4):.2f}", f"{max(p8):.2f}"),
        ("preadv SD", f"{sd(p4):.2f}", f"{sd(p8):.2f}"),
        ("reads >=500", sum(1 for v in p4 if v >= 500), sum(1 for v in p8 if v >= 500)),
        ("reads >=1000", sum(1 for v in p4 if v >= 1000), sum(1 for v in p8 if v >= 1000)),
        ("runs >=500", sum(1 for r in q4["runs"] if (r.get("thresholds") or {}).get("ge_500", 0) > 0),
         sum(1 for r in q8["runs"] if (r.get("thresholds") or {}).get("ge_500", 0) > 0)),
        ("runs >=1000", sum(1 for r in q4["runs"] if (r.get("thresholds") or {}).get("ge_1000", 0) > 0),
         sum(1 for r in q8["runs"] if (r.get("thresholds") or {}).get("ge_1000", 0) > 0)),
        ("median GB/s", f"{statistics.median(q4['gbps']):.3f}", f"{statistics.median(q8['gbps']):.3f}"),
        ("mean GB/s", f"{statistics.fmean(q4['gbps']):.3f}", f"{statistics.fmean(q8['gbps']):.3f}"),
        ("best GB/s", f"{max(q4['gbps']):.3f}", f"{max(q8['gbps']):.3f}"),
        ("worst GB/s", f"{min(q4['gbps']):.3f}", f"{min(q8['gbps']):.3f}"),
        ("GB/s SD", f"{sd(q4['gbps']):.3f}", f"{sd(q8['gbps']):.3f}"),
        ("avg total time ms", f"{statistics.fmean(q4['wall']):.1f}", f"{statistics.fmean(q8['wall']):.1f}"),
        ("median total time ms", f"{statistics.median(q4['wall']):.1f}", f"{statistics.median(q8['wall']):.1f}"),
        ("best total time ms", f"{min(q4['wall']):.1f}", f"{min(q8['wall']):.1f}"),
        ("worst total time ms", f"{max(q4['wall']):.1f}", f"{max(q8['wall']):.1f}"),
        ("total-time SD", f"{sd(q4['wall']):.1f}", f"{sd(q8['wall']):.1f}"),
        ("overlap", f"{statistics.fmean(q4['ovl']):.3f}", f"{statistics.fmean(q8['ovl']):.3f}"),
        ("eff concurrency", f"{statistics.fmean(q4['conc']):.2f}", f"{statistics.fmean(q8['conc']):.2f}"),
    ]
    print(f"| {'metric':<22} | {'QD4 @ 4 ms':>12} | {'QD8 @ 4 ms':>12} |")
    print(f"|{'-'*24}|{'-'*14}|{'-'*14}|")
    for k, a, b in rows:
        print(f"| {k:<22} | {a:>12} | {b:>12} |")

    # ---------- deltas ----------
    print("\n=== QD8 vs QD4 THROUGHPUT DELTA ===")
    m4, m8 = statistics.median(q4["gbps"]), statistics.median(q8["gbps"])
    a4, a8 = statistics.fmean(q4["gbps"]), statistics.fmean(q8["gbps"])
    w4, w8 = statistics.fmean(q4["wall"]), statistics.fmean(q8["wall"])
    print(f"  median GB/s : QD4={m4:.3f}  QD8={m8:.3f}  delta={m8-m4:+.3f} ({100*(m8-m4)/m4:+.1f}%)")
    print(f"  mean   GB/s : QD4={a4:.3f}  QD8={a8:.3f}  delta={a8-a4:+.3f} ({100*(a8-a4)/a4:+.1f}%)")
    print(f"  avg total   : QD4={w4:.0f} ms  QD8={w8:.0f} ms  delta={w8-w4:+.0f} ms ({100*(w8-w4)/w4:+.1f}%)")

    # ---------- first launches for pathological runs ----------
    print("\n=== FIRST-LAUNCH TRACE for runs containing >=500 ms reads ===")
    found = False
    for name, d in data.items():
        for r in d["runs"]:
            if (r.get("thresholds") or {}).get("ge_500", 0) <= 0:
                continue
            found = True
            qd = d["qd"]
            fl = (r.get("first_launches") or [])[:qd]
            print(f"  {name} {(r.get('attempt_id'))} worst={r.get('max_ms'):.0f} "
                  f"ge500={(r.get('thresholds') or {}).get('ge_500')} "
                  f"ge1k={(r.get('thresholds') or {}).get('ge_1000')}")
            print("      " + " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}" for x in fl))
    if not found:
        print("  (no run in either arm had a >=500 ms read)")

    # ---------- first 8 launches, first 3 runs per arm ----------
    print("\n=== FIRST LAUNCHES (first 3 runs per arm) ===")
    for name, d in data.items():
        for r in d["runs"][:3]:
            qd = d["qd"]
            fl = (r.get("first_launches") or [])[:qd]
            print(f"  {name} {(r.get('attempt_id')):<14} :: " + " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}" for x in fl))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
