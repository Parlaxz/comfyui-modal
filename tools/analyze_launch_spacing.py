#!/usr/bin/env python
"""PART 0 — launch-spacing analysis over the existing source_fullfile_runs corpus.

Hypothesis under test: pathological reads are triggered when multiple preadv() are
LAUNCHED too close together in wall time (not merely when they overlap).

Everything here is derived from raw preadv_enter_ns / preadv_exit_ns.
No deploy, no new runs.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

D = Path("source_fullfile_runs")
BINS = [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, float("inf")]
BIN_LABELS = ["<1", "1-2", "2-4", "4-8", "8-16", "16-32", "32-64", ">=64"]
THRESHOLDS = [250.0, 500.0, 1000.0]


def load_runs():
    runs = []
    for p in sorted(D.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        cfg = r.get("config") or {}
        runs.append({
            "name": p.stem,
            "read_mib": float(cfg.get("read_mib") or 0),
            "qd": int(cfg.get("qd") or 0),
            "reads": r["reads"],
            "gbps": r.get("full_file_decimal_gbps") or r.get("decimal_gbps"),
            "worst": r.get("max_ms"),
        })
    return runs


def annotate(run):
    """Per-read: generation, global launch rank, gap from previous global launch,
    neighbours within preceding windows, active_at_enter."""
    reads = sorted(run["reads"], key=lambda x: x["preadv_enter_ns"])
    span_t0 = reads[0]["preadv_enter_ns"]

    # generation = ordinal of this read within its own worker (by enter time)
    seen: dict[int, int] = {}
    for r in reads:
        w = r["worker"]
        r["generation"] = seen.get(w, 0)
        seen[w] = r["generation"] + 1

    prev = None
    for r in reads:
        ent = r["preadv_enter_ns"]
        r["gap_ms"] = None if prev is None else (ent - prev) / 1e6
        r["t_rel_ms"] = (ent - span_t0) / 1e6
        r["neighbours"] = {w: 0 for w in (1, 2, 4, 8, 16, 32, 64)}
        for r2 in reads:
            if r2 is r:
                continue
            d = (ent - r2["preadv_enter_ns"]) / 1e6
            if d < 0:
                continue
            for w in r["neighbours"]:
                if d < w:
                    r["neighbours"][w] += 1
        r["active_at_enter"] = sum(
            1 for r2 in reads
            if r2 is not r and r2["preadv_enter_ns"] < ent < r2["preadv_exit_ns"]
        )
        prev = ent
    return reads


def bin_of(gap):
    for i in range(len(BINS) - 1):
        if BINS[i] <= gap < BINS[i + 1]:
            return BIN_LABELS[i]
    return BIN_LABELS[-1]


def rate_table(label, annotated):
    """gap-bin -> counts of reads at/above each threshold"""
    rows = {b: {"n": 0, **{t: 0 for t in THRESHOLDS}} for b in BIN_LABELS}
    for reads in annotated:
        for r in reads:
            if r["gap_ms"] is None:
                continue
            b = bin_of(r["gap_ms"])
            rows[b]["n"] += 1
            for t in THRESHOLDS:
                if r["preadv_ms"] >= t:
                    rows[b][t] += 1
    print(f"\n[{label}]  n_total={sum(v['n'] for v in rows.values())}")
    hdr = f"  {'gap_ms':>8} {'n':>6}"
    for t in THRESHOLDS:
        hdr += f" {int(t):>7}"
    hdr += "   rates(>=250/500/1000)"
    print(hdr)
    for b in BIN_LABELS:
        v = rows[b]
        if v["n"] == 0:
            continue
        line = f"  {b:>8} {v['n']:>6}"
        for t in THRESHOLDS:
            line += f" {v[t]:>7}"
        line += "   " + "/".join(
            f"{100.0*v[t]/v['n']:.1f}%" for t in THRESHOLDS
        )
        print(line)


def main() -> int:
    runs = load_runs()
    print(f"corpus runs: {len(runs)}")
    inv: dict[tuple, int] = {}
    for r in runs:
        inv[(r["read_mib"], r["qd"])] = inv.get((r["read_mib"], r["qd"]), 0) + 1
    print("inventory (read_mib, qd) -> runs:")
    for k in sorted(inv):
        print(f"   {k}: {inv[k]}")
    total_reads = sum(len(r["reads"]) for r in runs)
    print(f"total reads: {total_reads}")
    print("worst preadv per run: "
          f"min={min(r['worst'] for r in runs):.0f} "
          f"median={statistics.median(r['worst'] for r in runs):.0f} "
          f"max={max(r['worst'] for r in runs):.0f} ms")

    annotated = [annotate(r) for r in runs]

    # ---- gen-0 sickness rate by QD (the confounded baseline) ----
    print("\n=== gen-0 >=500ms rate by QD (all read sizes) ===")
    by_qd: dict[int, list[int]] = {}
    for reads in annotated:
        g0 = [r for r in reads if r["generation"] == 0]
        for r in g0:
            by_qd.setdefault(
                next(rr["qd"] for rr in runs if reads is annotate_cache[rr["name"]])
                if False else 0, []
            )
    # simpler: recompute with run context
    print("  qd | runs | gen0 reads | gen0>=250 | gen0>=500 | gen0>=1000")
    qd_runs: dict[int, list] = {}
    for run, reads in zip(runs, annotated):
        qd_runs.setdefault(run["qd"], []).append(reads)
    for qd in sorted(qd_runs):
        n = c250 = c500 = c1000 = 0
        for reads in qd_runs[qd]:
            for r in reads:
                if r["generation"] != 0:
                    continue
                n += 1
                if r["preadv_ms"] >= 250:
                    c250 += 1
                if r["preadv_ms"] >= 500:
                    c500 += 1
                if r["preadv_ms"] >= 1000:
                    c1000 += 1
        pct = lambda c: f"{100.0*c/n:.2f}%" if n else "-"
        print(f"  QD{qd} | {len(qd_runs[qd]):>4} | {n:>10} | {c250:>9} ({pct(c250)}) "
              f"| {c500:>9} ({pct(c500)}) | {c1000:>10} ({pct(c1000)})")

    # ---- stratification by generation window ----
    def subset(pred):
        return [[r for r in reads if pred(r)] for reads in annotated]

    rate_table("ALL reads (descriptive context)", subset(lambda r: True))
    rate_table("gen 0 only", subset(lambda r: r["generation"] == 0))
    rate_table("gen 0-1", subset(lambda r: r["generation"] <= 1))
    rate_table("gen 0-3 (early)", subset(lambda r: r["generation"] <= 3))
    rate_table("gen 4+ (later)", subset(lambda r: r["generation"] >= 4))

    # ---- 64 MiB / QD4 slice only (matches the recent cohort) ----
    idx64 = [i for i, r in enumerate(runs) if r["read_mib"] == 64.0 and r["qd"] == 4]
    if idx64:
        sub = [annotated[i] for i in idx64]
        print(f"\n### 64 MiB / QD4 slice: {len(sub)} runs")
        rate_table("64MiB QD4 — gen 0 only",
                   [[r for r in reads if r["generation"] == 0] for reads in sub])
        rate_table("64MiB QD4 — all reads (context)",
                   [[r for r in reads if True] for reads in sub])

    # ---- immediate-launch concentration: how often are >=2 launched within X ----
    print("\n=== launch concentration: fraction of reads having N neighbours "
          "launched within the preceding window ===")
    print("  window_ms | mean_neighbours | frac_having_>=1 | frac_having_>=3")
    for w in (1, 2, 4, 8, 16, 32, 64):
        vals = [r["neighbours"][w] for reads in annotated for r in reads]
        if not vals:
            continue
        print(f"  {w:>9} | {statistics.mean(vals):>15.2f} | "
              f"{100.0*sum(1 for v in vals if v >= 1)/len(vals):>14.1f}% | "
              f"{100.0*sum(1 for v in vals if v >= 3)/len(vals):>15.1f}%")

    # ---- active_at_enter distribution ----
    print("\n=== active_at_enter (overlap) for reads >=500ms vs <500ms ===")
    for label, pred in (("sick >=500ms", lambda r: r["preadv_ms"] >= 500),
                        ("healthy <250ms", lambda r: r["preadv_ms"] < 250)):
        vals = [r["active_at_enter"] for reads in annotated for r in reads if pred(r)]
        if not vals:
            continue
        print(f"  {label:>16}: n={len(vals):>5} mean={statistics.mean(vals):.2f} "
              f"median={statistics.median(vals):.0f} max={max(vals)}")

    # ---- first four global launches per run (both gap_ms and latency) ----
    print("\n=== first 4 global launches per run (first 12 runs + all sick runs) ===")
    shown = 0
    for run, reads in zip(runs, annotated):
        sick = run["worst"] and run["worst"] >= 500
        if shown >= 12 and not sick:
            continue
        shown += 1
        head = reads[:4]
        desc = " | ".join(
            f"g{r['generation']}w{r['worker']} t={r['t_rel_ms']:.1f} "
            f"gap={'-' if r['gap_ms'] is None else format(r['gap_ms'],'.2f')} "
            f"lat={r['preadv_ms']:.0f} act={r['active_at_enter']}"
            for r in head
        )
        print(f"  {run['name']:<34} qd{run['qd']} {run['read_mib']:.0f}MiB "
              f"worst={run['worst']:>7.0f}ms :: {desc}")

    return 0


annotate_cache: dict = {}

if __name__ == "__main__":
    raise SystemExit(main())
