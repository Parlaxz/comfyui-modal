#!/usr/bin/env python
"""Part B: QD4 / 64 MiB / H100 source-only preadv distribution + survival.

Builds a deduplicated corpus manifest from all of today's source-only runs,
then the primary 4 ms no-hedge distribution, the secondary spacing-stratified
distribution, quantiles, and the conditional bad-state (survival) analysis.

Outputs CSVs + Markdown + PNG (if matplotlib is available).
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any

_R = Path(__file__).resolve().parents[1]
OUT = _R / "qd4_distribution"
FILE_BYTES = 8044982048

# cohort dir -> (glob, kind, spacing_ms_or_None)
COHORTS = [
    ("qd_compare_runs", "qc-q4-*.json", "qd4_vs_qd8_qd4_arm", 4.0),
    ("launch_spacing_confirm_runs", "cf-c4-*.json", "spacing_confirm_4ms", 4.0),
    ("hedge_runs", "hx-C-*.json", "hedge_pilot_CONTROL", 4.0),
    ("launch_spacing_boundary_runs", "bd-b25-*.json", "spacing_boundary_2p5ms", 2.5),
    ("launch_spacing_boundary_runs", "bd-b30-*.json", "spacing_boundary_3p0ms", 3.0),
    ("launch_spacing_boundary_runs", "bd-b35-*.json", "spacing_boundary_3p5ms", 3.5),
    ("launch_spacing_runs", "ls-g0-*.json", "spacing_screen_0ms", 0.0),
    ("launch_spacing_runs", "ls-g1-*.json", "spacing_screen_1ms", 1.0),
    ("launch_spacing_runs", "ls-g2-*.json", "spacing_screen_2ms", 2.0),
    ("launch_spacing_runs", "ls-g4-*.json", "spacing_screen_4ms", 4.0),
    ("launch_spacing_runs", "ls-g8-*.json", "spacing_screen_8ms", 8.0),
    ("launch_spacing_runs", "ls-g16-*.json", "spacing_screen_16ms", 16.0),
    ("launch_spacing_runs", "ls-g32-*.json", "spacing_screen_32ms", 32.0),
    ("launch_spacing_runs", "ls-g64-*.json", "spacing_screen_64ms", 64.0),
]
# exclude: ls-qd1 (QD1 oracle), bd hedge arms, any QD!=4 / read_mib!=64

BINS = [0, 20, 30, 40, 50, 60, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500,
        750, 1000, 1500, 2500, 5000, float("inf")]
X_GRID = [50, 60, 75, 90, 100, 110, 125, 150, 175, 200, 225, 250, 300, 350, 400, 500]


def pctl(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def sdev(xs: list[float]) -> float:
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


def annotate(run: dict[str, Any]) -> list[dict[str, Any]]:
    reads = sorted(run["reads"], key=lambda x: x["preadv_enter_ns"])
    seen: dict[int, int] = {}
    for i, r in enumerate(reads):
        w = r["worker"]
        r["_gen"] = seen.get(w, 0)
        seen[w] = r["_gen"] + 1
        r["_ordinal"] = i
    for r in reads:
        t = r["preadv_enter_ns"]
        r["_active"] = sum(
            1 for q in reads
            if q is not r and q["preadv_enter_ns"] < t < q["preadv_exit_ns"])
    return reads


def main() -> int:
    OUT.mkdir(exist_ok=True)
    manifest: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    seen_run: set[str] = set()

    for sub, glob, cohort, spacing in COHORTS:
        for p in sorted((_R / sub).glob(glob)):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            cfg = (r.get("config") or {})
            rid = f"{cohort}:{p.stem}"
            if rid in seen_run:
                manifest.append({"run_id": rid, "path": str(p), "cohort": cohort,
                                 "valid": False, "reason": "duplicate_run_id"})
                continue
            seen_run.add(rid)
            gpu = str((r.get("identity") or {}).get("observed_gpu") or "")
            qd = int(cfg.get("qd") or 0)
            mib = float(cfg.get("read_mib") or 0)
            ok = (r.get("status") == "ok" and "H100" in gpu and qd == 4
                  and abs(mib - 64.0) < 1e-6 and (r.get("reads") or []))
            if not ok:
                manifest.append({"run_id": rid, "path": str(p), "cohort": cohort,
                                 "valid": False,
                                 "reason": f"gpu={gpu!r} qd={qd} mib={mib} status={r.get('status')}"})
                continue
            hedge = (r.get("hedge") or {})
            hedge_launched = int(hedge.get("launched") or 0)
            wall = r.get("full_file_wall_ms") or 0.0
            reads = annotate(r)
            manifest.append({"run_id": rid, "path": str(p), "cohort": cohort,
                             "spacing_ms": spacing, "gpu": gpu, "region": r.get("region"),
                             "qd": qd, "read_mib": mib, "reads": len(reads),
                             "wall_ms": round(wall, 1),
                             "hedge_launched": hedge_launched,
                             "hedge_slots": hedge.get("hedge_slots_per_worker"),
                             "valid": True, "reason": ""})
            for x in reads:
                rows.append({
                    "run_id": rid, "cohort": cohort, "spacing_ms": spacing,
                    "worker": x["worker"], "generation": x["_gen"],
                    "ordinal": x["_ordinal"], "preadv_ms": x["preadv_ms"],
                    "active_at_enter": x["_active"],
                    "offset": x.get("offset"), "length": x.get("length"),
                    "region": r.get("region"), "wall_ms": round(wall, 1),
                    "hedge_launched": hedge_launched,
                })

    print(f"manifest rows={len(manifest)} valid={sum(1 for m in manifest if m['valid'])}")
    print(f"raw read rows={len(rows)}")

    # ---- write manifest + raw ----
    with (OUT / "qd4_64m_corpus_manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(manifest[0].keys()))
        w.writeheader()
        w.writerows(manifest)
    with (OUT / "qd4_64m_preadv_raw.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- PRIMARY: 4.0 ms, no hedge ----
    primary = [x for x in rows if x["spacing_ms"] == 4.0 and x["hedge_launched"] == 0]
    p_runs = sorted({x["run_id"] for x in primary})
    print(f"\nPRIMARY 4ms no-hedge: runs={len(p_runs)} reads={len(primary)}")
    prim_runs = [m for m in manifest if m["valid"] and m["spacing_ms"] == 4.0
                 and m["hedge_launched"] == 0]
    for m in prim_runs:
        print(f"   {m['cohort']:<26} runs_of_cohort  wall={m['wall_ms']}")

    def hist(dataset: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
        vals = [x["preadv_ms"] for x in dataset]
        n = len(vals)
        out = []
        cum = 0
        for i in range(len(BINS) - 1):
            lo, hi = BINS[i], BINS[i + 1]
            c = sum(1 for v in vals if lo <= v < hi)
            cum += c
            out.append({"bin_lo_ms": lo, "bin_hi_ms": hi, "count": c,
                        "pct": 100.0 * c / n if n else 0,
                        "cum_pct": 100.0 * cum / n if n else 0,
                        "survival_pct": 100.0 * (n - cum) / n if n else 0})
        with (OUT / f"qd4_64m_histogram_{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        return out

    h = hist(primary, "primary_4ms")
    print("\n=== PRIMARY 4 ms HISTOGRAM ===")
    print(f"{'bin':>16}{'count':>8}{'pct':>8}{'cum%':>8}{'surv%':>9}")
    for b in h:
        lab = (f">={b['bin_lo_ms']:.0f}" if b["bin_hi_ms"] == float("inf")
               else f"{b['bin_lo_ms']:.0f}-{b['bin_hi_ms']:.0f}")
        if b["count"] == 0:
            continue
        print(f"{lab:>16}{b['count']:>8}{b['pct']:>8.3f}{b['cum_pct']:>8.3f}{b['survival_pct']:>9.3f}")

    # ---- quantiles ----
    def quant_report(dataset, label):
        vals = [x["preadv_ms"] for x in dataset]
        if not vals:
            print(f"  {label}: (empty)")
            return
        qs = [("min", 0), ("p10", 10), ("p25", 25), ("p50", 50), ("p75", 75),
              ("p90", 90), ("p95", 95), ("p97", 97), ("p98", 98), ("p99", 99),
              ("p99.5", 99.5), ("p99.9", 99.9), ("max", 100)]
        parts = []
        for nm, q in qs:
            v = min(vals) if q == 0 else (max(vals) if q == 100 else pctl(vals, q))
            parts.append(f"{nm}={v:.2f}")
        print(f"  {label}: n={len(vals)} " + " ".join(parts))
        print(f"       mean={statistics.fmean(vals):.2f} SD={sdev(vals):.2f}")

    print("\n=== QUANTILES (primary 4 ms) ===")
    quant_report(primary, "all")
    quant_report([x for x in primary if x["generation"] == 0], "g0")
    quant_report([x for x in primary if x["generation"] >= 1], "g1+")

    # ---- survival / conditional ----
    def survival(dataset, label):
        vals = sorted(x["preadv_ms"] for x in dataset)
        n = len(vals)
        out = []
        for X in X_GRID:
            outl = [v for v in vals if v > X]
            k = len(outl)
            row = {"X_ms": X, "outstanding": k,
                   "frac_outstanding": 100.0 * k / n if n else 0}
            for t in (250, 500, 1000):
                c = sum(1 for v in outl if v >= t)
                row[f"P_ge{t}_given_outstanding"] = (100.0 * c / k) if k else None
                row[f"n_ge{t}"] = c
            if outl:
                rem = [v - X for v in outl]
                row["median_final_ms"] = statistics.median(outl)
                row["median_remaining_ms"] = statistics.median(rem)
                row["p90_final_ms"] = pctl(outl, 90)
                row["p95_final_ms"] = pctl(outl, 95)
                row["P_done_within_25ms"] = 100.0 * sum(1 for v in rem if v <= 25) / k
                row["P_done_within_50ms"] = 100.0 * sum(1 for v in rem if v <= 50) / k
                row["P_done_within_100ms"] = 100.0 * sum(1 for v in rem if v <= 100) / k
            out.append(row)
        with (OUT / f"qd4_64m_survival_{label}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
            w.writeheader()
            w.writerows(out)
        return out

    surv = survival(primary, "primary_4ms")
    print("\n=== SURVIVAL: P(final >= T | still outstanding at X) ===")
    print(f"{'X':>6}{'outstd':>8}{'%out':>8}{'P>=250':>9}{'P>=500':>9}{'P>=1000':>9}"
          f"{'medFinal':>10}{'medRemain':>11}{'done<=25':>10}{'done<=50':>10}{'done<=100':>11}")
    for r in surv:
        f = lambda v, n=1: "-" if v is None else format(v, f".{n}f")
        print(f"{r['X_ms']:>6}{r['outstanding']:>8}{r['frac_outstanding']:>8.2f}"
              f"{f(r.get('P_ge250_given_outstanding')):>9}{f(r.get('P_ge500_given_outstanding')):>9}"
              f"{f(r.get('P_ge1000_given_outstanding')):>9}"
              f"{f(r.get('median_final_ms')):>10}{f(r.get('median_remaining_ms')):>11}"
              f"{f(r.get('P_done_within_25ms')):>10}{f(r.get('P_done_within_50ms')):>10}"
              f"{f(r.get('P_done_within_100ms')):>11}")

    survival([x for x in primary if x["generation"] == 0], "g0")
    survival([x for x in primary if x["generation"] >= 1], "g1plus")

    # ---- crossing points ----
    print("\n=== EARLIEST X WHERE P(>=500 | outstanding) CROSSES ===")
    for target in (25, 50, 75, 90):
        found = None
        for r in surv:
            v = r.get("P_ge500_given_outstanding")
            if v is not None and v >= target:
                found = r
                break
        if found:
            print(f"  {target}%: first observed at X={found['X_ms']} ms "
                  f"(P={found['P_ge500_given_outstanding']:.1f}%, "
                  f"outstanding={found['outstanding']})")
        else:
            print(f"  {target}%: not reached in the tested X grid")

    # ---- secondary: spacing stratified ----
    print("\n=== SECONDARY: all clean QD4/64MiB non-hedged, stratified by spacing ===")
    print(f"{'spacing':>8}{'runs':>6}{'reads':>7}{'median':>9}{'p95':>9}{'p99':>10}"
          f"{'max':>9}{'n500':>6}{'n1k':>5}")
    sec_rows = []
    for sp in sorted({x["spacing_ms"] for x in rows if x["hedge_launched"] == 0}):
        sub = [x for x in rows if x["spacing_ms"] == sp and x["hedge_launched"] == 0]
        v = [x["preadv_ms"] for x in sub]
        nr = len({x["run_id"] for x in sub})
        sec_rows.append({"spacing_ms": sp, "runs": nr, "reads": len(v),
                         "median": statistics.median(v) if v else None,
                         "p95": pctl(v, 95), "p99": pctl(v, 99),
                         "max": max(v) if v else None,
                         "n500": sum(1 for x in v if x >= 500),
                         "n1000": sum(1 for x in v if x >= 1000)})
        print(f"{sp:>8.1f}{nr:>6}{len(v):>7}"
              f"{(statistics.median(v) if v else 0):>9.2f}{(pctl(v,95) or 0):>9.2f}"
              f"{(pctl(v,99) or 0):>10.2f}{(max(v) if v else 0):>9.0f}"
              f"{sum(1 for x in v if x >= 500):>6}{sum(1 for x in v if x >= 1000):>5}")
    with (OUT / "qd4_64m_secondary_by_spacing.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(sec_rows[0].keys()))
        w.writeheader()
        w.writerows(sec_rows)

    # ---- cohort sensitivity for primary ----
    print("\n=== COHORT SENSITIVITY (primary 4 ms) ===")
    for c in sorted({x["cohort"] for x in primary}):
        sub = [x for x in primary if x["cohort"] == c]
        v = [x["preadv_ms"] for x in sub]
        print(f"  {c:<26} reads={len(v):>5} median={statistics.median(v):>7.2f} "
              f"p99={pctl(v,99):>8.2f} max={max(v):>7.0f} "
              f"n500={sum(1 for x in v if x >= 500):>3} n1k={sum(1 for x in v if x >= 1000):>3}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
