#!/usr/bin/env python
"""PART 0b — launch-spacing, GPU-stratified (removes the RTX stagger confound)."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

D = Path("source_fullfile_runs")
BINS = [0.0, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, float("inf")]
LABELS = ["<1", "1-2", "2-4", "4-8", "8-16", "16-32", "32-64", ">=64"]
THR = [250.0, 500.0, 1000.0]


def load(gpu_filter=None):
    runs = []
    for p in sorted(D.glob("*.json")):
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        gpu = str(r.get("observed_gpu") or "")
        if gpu_filter and gpu_filter not in gpu:
            continue
        cfg = r.get("config") or {}
        runs.append({"name": p.stem, "gpu": gpu,
                     "read_mib": float(cfg.get("read_mib") or 0),
                     "qd": int(cfg.get("qd") or 0),
                     "reads": r["reads"], "worst": r.get("max_ms")})
    return runs


def annotate(run):
    reads = sorted(run["reads"], key=lambda x: x["preadv_enter_ns"])
    t0 = reads[0]["preadv_enter_ns"]
    seen = {}
    for r in reads:
        w = r["worker"]
        r["generation"] = seen.get(w, 0)
        seen[w] = r["generation"] + 1
    prev = None
    for r in reads:
        ent = r["preadv_enter_ns"]
        r["gap_ms"] = None if prev is None else (ent - prev) / 1e6
        r["t_rel_ms"] = (ent - t0) / 1e6
        r["active_at_enter"] = sum(
            1 for r2 in reads if r2 is not r
            and r2["preadv_enter_ns"] < ent < r2["preadv_exit_ns"])
        prev = ent
    return reads


def bin_of(g):
    for i in range(len(BINS) - 1):
        if BINS[i] <= g < BINS[i + 1]:
            return LABELS[i]
    return LABELS[-1]


def table(label, groups):
    rows = {b: {"n": 0, **{t: 0 for t in THR}} for b in LABELS}
    for reads in groups:
        for r in reads:
            if r["gap_ms"] is None:
                continue
            b = bin_of(r["gap_ms"])
            rows[b]["n"] += 1
            for t in THR:
                if r["preadv_ms"] >= t:
                    rows[b][t] += 1
    print(f"\n[{label}] n={sum(v['n'] for v in rows.values())}")
    print(f"  {'gap':>7} {'n':>6} {'>=250':>7} {'>=500':>7} {'>=1000':>7}   rates")
    for b in LABELS:
        v = rows[b]
        if not v["n"]:
            continue
        print(f"  {b:>7} {v['n']:>6} {v[250.0]:>7} {v[500.0]:>7} {v[1000.0]:>7}   "
              + "/".join(f"{100.0*v[t]/v['n']:.1f}%" for t in THR))


def main() -> int:
    for flt in ("H100", "RTX"):
        runs = load(flt)
        if not runs:
            continue
        ann = [annotate(r) for r in runs]
        print(f"\n{'='*78}\nGPU filter={flt}: {len(runs)} runs, "
              f"{sum(len(a) for a in ann)} reads, worst={max(r['worst'] for r in runs):.0f} ms")

        # generation-0 gap distribution + rates
        def gsub(pred):
            return [[r for r in a if pred(r)] for a in ann]

        table(f"{flt} gen0 only", gsub(lambda r: r["generation"] == 0))
        table(f"{flt} gen0-3", gsub(lambda r: r["generation"] <= 3))
        table(f"{flt} gen4+", gsub(lambda r: r["generation"] >= 4))

        # 64 MiB QD4 slice
        idx = [i for i, r in enumerate(runs) if r["read_mib"] == 64.0 and r["qd"] == 4]
        if idx:
            sub = [ann[i] for i in idx]
            print(f"\n  --- {flt} 64MiB QD4: {len(sub)} runs, worst="
                  f"{max(runs[i]['worst'] for i in idx):.0f} ms")
            table(f"{flt} 64MiB QD4 gen0",
                  [[r for r in a if r["generation"] == 0] for a in sub])
            table(f"{flt} 64MiB QD4 all",
                  [[r for r in a if True] for a in sub])

        # how often does a gen-0 launch land within 1ms / 4ms of another
        g0 = [r for a in ann for r in a if r["generation"] == 0]
        for w in (1, 2, 4, 8, 16, 32):
            n = sum(1 for r in g0 if any(
                abs(r["t_rel_ms"] - r2["t_rel_ms"]) < w
                for r2 in g0 if r2 is not r))
            print(f"  gen0 having another gen0 launch within {w:>2} ms: "
                  f"{n}/{len(g0)} = {100.0*n/len(g0):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
