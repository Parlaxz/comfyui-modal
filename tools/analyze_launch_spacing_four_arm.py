#!/usr/bin/env python
"""Four-arm boundary analysis: 2.5 / 3.0 / 3.5 / 4.0 ms.

All four arms are recomputed from RAW per-read records with identical code, so
the 4.0 ms arm is not taken from an old summary table.

Pools:  launch_spacing_boundary_runs/bd-{b25,b30,b35}-*.json   (new, 45 runs)
        launch_spacing_confirm_runs/cf-c4-*.json               (prior, 15 runs)
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path
from typing import Any

_R = Path(__file__).resolve().parents[1]
BOUNDARY = _R / "launch_spacing_boundary_runs"
CONFIRM = _R / "launch_spacing_confirm_runs"

ARMS: list[tuple[str, float, list[Path]]] = [
    ("2.5", 2.5, sorted(BOUNDARY.glob("bd-b25-*.json"))),
    ("3.0", 3.0, sorted(BOUNDARY.glob("bd-b30-*.json"))),
    ("3.5", 3.5, sorted(BOUNDARY.glob("bd-b35-*.json"))),
    ("4.0", 4.0, sorted(CONFIRM.glob("cf-c4-*.json"))),
]


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


def load(paths: list[Path]) -> list[dict[str, Any]]:
    runs = []
    for p in paths:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        gpu = str((r.get("identity") or {}).get("observed_gpu") or "")
        if "H100" not in gpu:
            continue
        runs.append(r)
    return runs


def gen_of(run: dict[str, Any], gen: int) -> list[float]:
    """preadv_ms for generation `gen` of every worker (per-worker ordinal)."""
    out = []
    per: dict[int, list[dict]] = {}
    for x in run["reads"]:
        per.setdefault(x["worker"], []).append(x)
    for w, xs in per.items():
        xs = sorted(xs, key=lambda z: z["preadv_enter_ns"])
        if len(xs) > gen:
            out.append(xs[gen]["preadv_ms"])
    return out


def fisher(a: int, b: int, c: int, d: int) -> float:
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def pr(x: int) -> float:
        return math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)

    lo, hi = max(0, r1 - (n - c1)), min(r1, c1)
    obs = pr(a)
    return sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= obs + 1e-12)


def main() -> int:
    data: dict[str, dict[str, Any]] = {}
    for label, gap, paths in ARMS:
        runs = load(paths)
        pooled = [x["preadv_ms"] for r in runs for x in r["reads"]]
        per_med = [statistics.median([x["preadv_ms"] for x in r["reads"]]) for r in runs]
        per_mean = [statistics.fmean([x["preadv_ms"] for x in r["reads"]]) for r in runs]
        g0 = [v for r in runs for v in gen_of(r, 0)]
        g1 = [v for r in runs for v in gen_of(r, 1)]
        g2 = [v for r in runs for v in gen_of(r, 2)]
        g3 = [v for r in runs for v in gen_of(r, 3)]
        gbps = [r["full_file_decimal_gbps"] for r in runs if r.get("full_file_decimal_gbps")]
        walls = [r.get("full_file_wall_ms") or 0 for r in runs]
        ovl = [(r.get("launch_spacing") or {}).get("frac_entered_with_other_active")
               for r in runs]
        conc = [(r.get("launch_spacing") or {}).get("mean_effective_concurrency")
                for r in runs]
        gmin = [(r.get("launch_spacing") or {}).get("observed_min_inter_start_ms")
                for r in runs]
        gp5 = [(r.get("launch_spacing") or {}).get("observed_p5_inter_start_ms")
               for r in runs]
        gmed = [(r.get("launch_spacing") or {}).get("observed_median_inter_start_ms")
                for r in runs]
        gp95 = [(r.get("launch_spacing") or {}).get("observed_p95_inter_start_ms")
                for r in runs]
        mx = [(r.get("launch_spacing") or {}).get("max_simultaneous_in_flight")
              for r in runs]
        data[label] = {
            "gap": gap, "runs": runs, "n_runs": len(runs), "pooled": pooled,
            "per_med": per_med, "per_mean": per_mean,
            "g0": g0, "g1": g1, "g2": g2, "g3": g3,
            "gbps": gbps, "walls": walls,
            "ovl": [v for v in ovl if v is not None],
            "conc": [v for v in conc if v is not None],
            "gmin": [v for v in gmin if v is not None],
            "gp5": [v for v in gp5 if v is not None],
            "gmed": [v for v in gmed if v is not None],
            "gp95": [v for v in gp95 if v is not None],
            "mx": [v for v in mx if v is not None],
        }

    def out(s: str = "") -> None:
        print(s)

    out("=" * 118)
    out("FOUR-ARM LAUNCH-SPACING BOUNDARY  (all arms recomputed from raw per-read records)")
    out("=" * 118)
    for label, d in data.items():
        out(f"  gap {label:>4} ms : {d['n_runs']} runs, {len(d['pooled'])} reads")

    # ---- MAIN OUTPUT TABLE ----
    out("\n=== MAIN TABLE ===")
    out(f"{'gap':>5}{'runs':>6}{'reads':>7}{'poolMed':>9}{'poolMean':>10}{'p95':>8}"
        f"{'p99':>9}{'worst':>9}{'r>=500':>8}{'n>=500':>8}{'n>=1000':>9}"
        f"{'medGBps':>9}{'ovl':>7}{'conc':>6}")
    for label, d in data.items():
        p = d["pooled"]
        r500 = sum(1 for r in d["runs"] if r.get("thresholds", {}).get("ge_500", 0) > 0)
        n500 = sum(1 for v in p if v >= 500)
        n1000 = sum(1 for v in p if v >= 1000)
        out(f"{label:>5}{d['n_runs']:>6}{len(p):>7}"
            f"{statistics.median(p):>9.2f}{statistics.fmean(p):>10.2f}"
            f"{pct(p,95):>8.2f}{pct(p,99):>9.2f}{max(p):>9.0f}"
            f"{r500:>8}{n500:>8}{n1000:>9}"
            f"{statistics.median(d['gbps']):>9.3f}"
            f"{statistics.fmean(d['ovl']):>7.3f}{statistics.fmean(d['conc']):>6.2f}")

    # ---- per-run distribution of medians/means ----
    out("\n=== PER-RUN DISTRIBUTION (pooled mean can be distorted by one sick run) ===")
    out(f"{'gap':>5}{'med_of_meds':>13}{'mean_of_meds':>14}{'med_of_means':>14}"
        f"{'mean_of_means':>15}{'max_run_mean':>14}")
    for label, d in data.items():
        out(f"{label:>5}{statistics.median(d['per_med']):>13.2f}"
            f"{statistics.fmean(d['per_med']):>14.2f}"
            f"{statistics.median(d['per_mean']):>14.2f}"
            f"{statistics.fmean(d['per_mean']):>15.2f}"
            f"{max(d['per_mean']):>14.2f}")

    # ---- median vs mean discussion aid ----
    out("\n=== MEDIAN vs MEAN (is pacing deleting tails, or speeding ordinary reads?) ===")
    out(f"{'gap':>5}{'pooled median':>15}{'pooled mean':>13}{'mean-median gap':>18}"
        f"{'p95':>9}{'p99':>10}")
    for label, d in data.items():
        p = d["pooled"]
        m, mn = statistics.median(p), statistics.fmean(p)
        out(f"{label:>5}{m:>15.2f}{mn:>13.2f}{mn-m:>18.2f}{pct(p,95):>9.2f}{pct(p,99):>10.2f}")

    # ---- generation 0 ----
    out("\n=== GENERATION 0 ONLY ===")
    out(f"{'spacing':>8}{'gen0 n':>8}{'median':>9}{'mean':>10}{'>=250':>7}{'>=500':>7}"
        f"{'>=1000':>8}{'worst':>9}")
    for label, d in data.items():
        g = d["g0"]
        if not g:
            continue
        out(f"{label:>8}{len(g):>8}{statistics.median(g):>9.2f}{statistics.fmean(g):>10.2f}"
            f"{sum(1 for v in g if v >= 250):>7}{sum(1 for v in g if v >= 500):>7}"
            f"{sum(1 for v in g if v >= 1000):>8}{max(g):>9.0f}")

    out("\n=== ALL GENERATIONS ===")
    for label, d in data.items():
        parts = []
        for name, g in (("g0", d["g0"]), ("g1", d["g1"]), ("g2", d["g2"]), ("g3", d["g3"])):
            if not g:
                continue
            parts.append(f"{name}: n={len(g)} med={statistics.median(g):.1f} "
                         f"mean={statistics.fmean(g):.1f} max={max(g):.0f} "
                         f"ge500={sum(1 for v in g if v >= 500)} "
                         f"ge1k={sum(1 for v in g if v >= 1000)}")
        out(f"  gap {label:>4} | " + " | ".join(parts))

    # ---- pacer validity ----
    out("\n=== PACER VALIDITY (observed floors) ===")
    out(f"{'gap':>5}{'obs_min(range)':>26}{'obs_p5(range)':>24}{'obs_median(range)':>26}"
        f"{'obs_p95(range)':>26}")
    for label, d in data.items():
        def rng(vs, p=2):
            return f"{min(vs):.{p}f}-{max(vs):.{p}f}" if vs else "-"
        out(f"{label:>5}{rng(d['gmin']):>26}{rng(d['gp5']):>24}{rng(d['gmed']):>26}"
            f"{rng(d['gp95']):>26}")

    # ---- concurrency / throughput ----
    out("\n=== CONCURRENCY / THROUGHPUT ===")
    out(f"{'gap':>5}{'medGBps':>9}{'meanGBps':>10}{'minGBps':>9}{'medWall':>9}"
        f"{'ovl_mean':>10}{'conc_mean':>11}{'max_active':>11}")
    for label, d in data.items():
        out(f"{label:>5}{statistics.median(d['gbps']):>9.3f}"
            f"{statistics.fmean(d['gbps']):>10.3f}{min(d['gbps']):>9.3f}"
            f"{statistics.median(d['walls']):>9.0f}"
            f"{statistics.fmean(d['ovl']):>10.3f}{statistics.fmean(d['conc']):>11.2f}"
            f"{max(d['mx']) if d['mx'] else '-':>11}")

    # ---- Fisher ----
    out("\n=== FISHER EXACT (two-sided) ===")
    labels = [l for l, _, _ in ARMS]
    out("  read-level >=500 ms (out of 1800 reads per arm)")
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = data[labels[i]], data[labels[j]]
            na = sum(1 for v in a["pooled"] if v >= 500)
            nb = sum(1 for v in b["pooled"] if v >= 500)
            p = fisher(na, len(a["pooled"]) - na, nb, len(b["pooled"]) - nb)
            out(f"    {labels[i]:>4} vs {labels[j]:>4}: {na:>3} vs {nb:>3}  p={p:.4f}")
    out("  read-level >=1000 ms")
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = data[labels[i]], data[labels[j]]
            na = sum(1 for v in a["pooled"] if v >= 1000)
            nb = sum(1 for v in b["pooled"] if v >= 1000)
            p = fisher(na, len(a["pooled"]) - na, nb, len(b["pooled"]) - nb)
            out(f"    {labels[i]:>4} vs {labels[j]:>4}: {na:>3} vs {nb:>3}  p={p:.4f}")
    out("  gen0 >=500 ms (out of 60 gen-0 reads per arm)")
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = data[labels[i]], data[labels[j]]
            na = sum(1 for v in a["g0"] if v >= 500)
            nb = sum(1 for v in b["g0"] if v >= 500)
            if not a["g0"] or not b["g0"]:
                continue
            p = fisher(na, len(a["g0"]) - na, nb, len(b["g0"]) - nb)
            out(f"    {labels[i]:>4} vs {labels[j]:>4}: {na:>3} vs {nb:>3}  p={p:.4f}")
    out("  run-level: runs with any >=500 ms read (out of 15 runs per arm)")
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            a, b = data[labels[i]], data[labels[j]]
            na = sum(1 for r in a["runs"] if r.get("thresholds", {}).get("ge_500", 0) > 0)
            nb = sum(1 for r in b["runs"] if r.get("thresholds", {}).get("ge_500", 0) > 0)
            p = fisher(na, a["n_runs"] - na, nb, b["n_runs"] - nb)
            out(f"    {labels[i]:>4} vs {labels[j]:>4}: {na:>3} vs {nb:>3}  p={p:.4f}")

    # ---- pathological runs: first four launches ----
    out("\n=== PATHOLOGICAL RUNS (any read >=500 ms): first four launches ===")
    any_sick = False
    for label, d in data.items():
        for r in d["runs"]:
            th = r.get("thresholds") or {}
            if th.get("ge_500", 0) <= 0:
                continue
            any_sick = True
            fl = r.get("first_launches") or []
            desc = " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
                for x in fl
            )
            out(f"  gap {label:>4} {(r.get('attempt_id') or ''):<16} "
                f"worst={r.get('max_ms'):.0f} ge500={th.get('ge_500')} ge1k={th.get('ge_1000')}")
            out(f"        {desc}")
    if not any_sick:
        out("  (none: no run in any arm had a read >=500 ms)")

    # ---- first four launches for the protected arms (head) ----
    out("\n=== FIRST FOUR LAUNCHES, first 6 runs of each arm (full traces in raw JSON) ===")
    for label, d in data.items():
        for r in d["runs"][:6]:
            fl = r.get("first_launches") or []
            desc = " | ".join(
                f"#{x['ordinal']}w{x['worker']} t={x['t_rel_ms']:.1f} "
                f"gap={'-' if x['gap_from_previous_ms'] is None else format(x['gap_from_previous_ms'],'.2f')} "
                f"lat={x['preadv_ms']:.0f} act={x['active_at_enter']}"
                for x in fl
            )
            out(f"  gap {label:>4} {(r.get('attempt_id') or ''):<16} :: {desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
