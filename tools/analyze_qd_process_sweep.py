#!/usr/bin/env python
"""QD4/5/6/7 process-architecture sweep analysis.

QD4 is the FROZEN control: the 15 valid process runs are loaded from the raw
files of the previous unpinned campaign (worker_model_runs_unpinned), never
reconstructed from summary numbers.

QD5/6/7 are the 10 new valid non-Odin runs each from qd_sweep_runs.

Provider composition differs between arms, so the pooled view is reported
alongside a GCP-only sensitivity view.  No provider/region is pinned in this
experiment; AWS appears only incidentally and is NOT merged into the primary
comparison.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from comfymodal_runtime.source_race_oracle import percentile  # noqa: E402

_QDS = (4, 5, 6, 7)
_GEN_KEYS: list[Any] = [0, 1, 2, 3, "g4+"]


def _norm_cloud(value: Any) -> str:
    text = str(value or "").strip().lower()
    prefix = "cloud_provider_"
    return text[len(prefix):] if text.startswith(prefix) else text


def _f(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _load_runs(unpinned_dir: Path, sweep_dir: Path) -> dict[int, list[dict[str, Any]]]:
    runs: dict[int, list[dict[str, Any]]] = {qd: [] for qd in _QDS}

    for path in sorted(unpinned_dir.glob("wm-*.json")):
        if "invalid" in path.name:
            continue
        r = json.loads(path.read_text(encoding="utf-8"))
        if str(r.get("worker_model") or "") != "processes":
            continue
        if int((r.get("config") or {}).get("qd") or 0) != 4:
            continue
        r["_source"] = "frozen_qd4"
        r["_file"] = path.name
        runs[4].append(r)

    for qd in (5, 6, 7):
        for path in sorted(sweep_dir.glob(f"qd{qd}-r*.json")):
            if "invalid" in path.name:
                continue
            r = json.loads(path.read_text(encoding="utf-8"))
            if int((r.get("config") or {}).get("qd") or 0) != qd:
                continue
            r["_source"] = "sweep"
            r["_file"] = path.name
            runs[qd].append(r)

    for qd in _QDS:
        runs[qd].sort(key=lambda r: r["_file"])
    return runs


def _provider(r: dict[str, Any]) -> str:
    return _norm_cloud((r.get("identity") or {}).get("provider")) or "unspecified"


def _region(r: dict[str, Any]) -> str:
    return str((r.get("identity") or {}).get("region") or "")


def _reads(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [x for r in runs for x in (r.get("reads") or [])]


def _lat(runs: list[dict[str, Any]]) -> list[float]:
    return [x["preadv_ms"] for x in _reads(runs)]


def _gbps(runs: list[dict[str, Any]]) -> list[float]:
    return [float(r["full_file_decimal_gbps"]) for r in runs]


def _wall(runs: list[dict[str, Any]]) -> list[float]:
    return [float(r["full_file_wall_ms"]) for r in runs]


def _tails(lat: list[float], t: float) -> int:
    return sum(1 for x in lat if x >= t)


def _gen_buckets(runs: list[dict[str, Any]]) -> dict[Any, list[float]]:
    buckets: dict[Any, list[float]] = {k: [] for k in _GEN_KEYS}
    for x in _reads(runs):
        g = int(x.get("generation") or 0)
        buckets[g if g <= 3 else "g4+"].append(x["preadv_ms"])
    return buckets


def _effconc(runs: list[dict[str, Any]]) -> float:
    return statistics.fmean(
        float((r.get("launch_spacing") or {})["mean_effective_concurrency"]) for r in runs
    )


def _overlap(runs: list[dict[str, Any]]) -> float:
    return statistics.fmean(
        float((r.get("launch_spacing") or {})["frac_entered_with_other_active"]) for r in runs
    )


def _maxif(runs: list[dict[str, Any]]) -> int:
    return max(int((r.get("launch_spacing") or {})["max_simultaneous_in_flight"]) for r in runs)


def _spread(runs: list[dict[str, Any]]) -> float:
    vals = [float(r["final_worker_completion_spread_ms"]) for r in runs
            if r.get("final_worker_completion_spread_ms") is not None]
    return percentile(vals, 50) if vals else float("nan")


def _gcp_only(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in runs if _provider(r) == "gcp"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unpinned-dir", default="worker_model_runs_unpinned")
    parser.add_argument("--sweep-dir", default="qd_sweep_runs")
    args = parser.parse_args()

    unpinned = _ROOT / args.unpinned_dir
    sweep = _ROOT / args.sweep_dir
    runs = _load_runs(unpinned, sweep)

    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text, flush=True)

    say("=" * 100)
    say("QD4/5/6/7 PROCESS-ARCHITECTURE SWEEP — 64 MiB reads, 1 process/reader, global 4.0 ms pacer")
    say("=" * 100)
    say(f"QD4 = frozen control from {args.unpinned_dir} (worker_model=processes, qd=4)")
    say(f"QD5/6/7 = new runs from {args.sweep_dir}")
    say(f"valid runs: " + ", ".join(f"QD{qd}={len(runs[qd])}" for qd in _QDS))
    say()

    # ---------------- validity ----------------
    say("=" * 100)
    say("VALIDITY (fail closed)")
    say("=" * 100)
    say(f"{'qd':>3}{'file':<26}{'prov':<12}{'region':<15}{'reads':>6}{'bytes':>13}"
        f"{'exact':>7}{'maxIF':>6}{'gapMin':>8}{'pids':>5}{'model':>10}")
    all_valid = True
    for qd in _QDS:
        for r in runs[qd]:
            cov = r.get("coverage") or {}
            ls = r.get("launch_spacing") or {}
            pac = r.get("pacer") or {}
            ok = (int((r.get("config") or {}).get("qd") or 0) == qd
                  and int(r.get("physical_reads") or 0) == 120
                  and cov.get("covers_entire_file_exactly_once")
                  and cov.get("no_overlap") and cov.get("contiguous_cover")
                  and cov.get("all_reads_returned_full_length")
                  and cov.get("all_workers_completed_region")
                  and not r.get("worker_errors") and not r.get("barrier_error")
                  and int(ls.get("max_simultaneous_in_flight") or 0) <= qd
                  and float(pac.get("observed_min_global_claim_gap_ms") or 0) >= 4.0)
            all_valid = all_valid and ok
            say(f"{qd:>3}{r['_file']:<26}{_provider(r):<12}{_region(r):<15}"
                f"{r.get('physical_reads'):>6}{r.get('useful_bytes'):>13}"
                f"{str(bool(cov.get('covers_entire_file_exactly_once'))):>7}"
                f"{ls.get('max_simultaneous_in_flight'):>6}"
                f"{_f(pac.get('observed_min_global_claim_gap_ms')):>8}"
                f"{len(set(r.get('worker_pids') or [])):>5}"
                f"{str(r.get('worker_model')):>10}")
    say(f"\nALL VALIDITY CONDITIONS HOLD: {all_valid}")
    say()

    # ---------------- per-run ----------------
    say("=" * 100)
    say("PER-RUN")
    say("=" * 100)
    say(f"{'qd':>3}{'prov':<12}{'region':<15}{'wall':>8}{'GB/s':>7}{'min':>7}{'p10':>7}{'med':>7}"
        f"{'mean':>7}{'p90':>7}{'p95':>7}{'p99':>8}{'max':>9}{'SD':>7}"
        f"{'>100':>6}{'>150':>6}{'>250':>6}{'>500':>6}{'>1k':>5}{'>2k':>5}"
        f"{'conc':>6}{'ovl':>6}{'mx':>4}{'gapMin':>8}{'spread':>8}")
    per_run_rows: list[dict[str, Any]] = []
    for qd in _QDS:
        for r in runs[qd]:
            lat = [x["preadv_ms"] for x in (r.get("reads") or [])]
            ls = r.get("launch_spacing") or {}
            pac = r.get("pacer") or {}
            say(f"{qd:>3}{_provider(r):<12}{_region(r):<15}"
                f"{_f(r.get('full_file_wall_ms'), 0):>8}{_f(r.get('full_file_decimal_gbps')):>7}"
                f"{_f(min(lat), 1):>7}{_f(percentile(lat, 10), 1):>7}"
                f"{_f(percentile(lat, 50), 1):>7}{_f(statistics.fmean(lat), 1):>7}"
                f"{_f(percentile(lat, 90), 1):>7}{_f(percentile(lat, 95), 1):>7}"
                f"{_f(percentile(lat, 99), 1):>8}{_f(max(lat), 1):>9}"
                f"{_f(statistics.pstdev(lat), 1):>7}"
                f"{_tails(lat, 100):>6}{_tails(lat, 150):>6}{_tails(lat, 250):>6}"
                f"{_tails(lat, 500):>6}{_tails(lat, 1000):>5}{_tails(lat, 2000):>5}"
                f"{_f(ls.get('mean_effective_concurrency')):>6}"
                f"{_f(ls.get('frac_entered_with_other_active')):>6}"
                f"{ls.get('max_simultaneous_in_flight'):>4}"
                f"{_f(pac.get('observed_min_global_claim_gap_ms')):>8}"
                f"{_f(r.get('final_worker_completion_spread_ms'), 1):>8}")
            per_run_rows.append({
                "qd": qd, "file": r["_file"], "provider": _provider(r), "region": _region(r),
                "wall_ms": r.get("full_file_wall_ms"), "gbps": r.get("full_file_decimal_gbps"),
                "preadv_min": min(lat), "preadv_p10": percentile(lat, 10),
                "preadv_median": percentile(lat, 50), "preadv_mean": statistics.fmean(lat),
                "preadv_p90": percentile(lat, 90), "preadv_p95": percentile(lat, 95),
                "preadv_p99": percentile(lat, 99), "preadv_max": max(lat),
                "preadv_sd": statistics.pstdev(lat),
                "ge100": _tails(lat, 100), "ge150": _tails(lat, 150), "ge250": _tails(lat, 250),
                "ge500": _tails(lat, 500), "ge1000": _tails(lat, 1000), "ge2000": _tails(lat, 2000),
                "eff_concurrency": ls.get("mean_effective_concurrency"),
                "overlap": ls.get("frac_entered_with_other_active"),
                "max_in_flight": ls.get("max_simultaneous_in_flight"),
                "min_claim_gap_ms": pac.get("observed_min_global_claim_gap_ms"),
                "completion_spread_ms": r.get("final_worker_completion_spread_ms"),
                "spawn_to_ready_ms": r.get("process_spawn_to_all_ready_ms"),
                "n_pids": len(set(r.get("worker_pids") or [])),
            })
    say()

    # ---------------- headline ----------------
    say("=" * 100)
    say("HEADLINE AGGREGATE")
    say("=" * 100)
    agg: dict[int, dict[str, Any]] = {}
    for qd in _QDS:
        rs = runs[qd]
        g, w, lat = _gbps(rs), _wall(rs), _lat(rs)
        agg[qd] = {
            "n": len(rs), "gbps": g, "wall": w, "lat": lat,
            "median_gbps": percentile(g, 50), "mean_gbps": statistics.fmean(g),
            "p10_gbps": percentile(g, 10), "p90_gbps": percentile(g, 90),
            "best_gbps": max(g), "worst_gbps": min(g), "sd_gbps": statistics.pstdev(g),
            "median_wall": percentile(w, 50), "mean_wall": statistics.fmean(w),
            "best_wall": min(w), "worst_wall": max(w),
            "lat_median": percentile(lat, 50), "lat_mean": statistics.fmean(lat),
            "lat_p95": percentile(lat, 95), "lat_p99": percentile(lat, 99),
            "lat_worst": max(lat),
            "ge250": _tails(lat, 250), "ge500": _tails(lat, 500), "ge1000": _tails(lat, 1000),
            "runs_ge500": sum(1 for r in rs if _tails([x["preadv_ms"] for x in (r.get("reads") or [])], 500)),
            "runs_ge1000": sum(1 for r in rs if _tails([x["preadv_ms"] for x in (r.get("reads") or [])], 1000)),
            "effconc": _effconc(rs), "overlap": _overlap(rs), "maxif": _maxif(rs),
            "spread": _spread(rs),
        }

    rows = [
        ("valid runs", "n", 0),
        ("median GB/s", "median_gbps", 3),
        ("mean GB/s", "mean_gbps", 3),
        ("p10 GB/s", "p10_gbps", 3),
        ("p90 GB/s", "p90_gbps", 3),
        ("best GB/s", "best_gbps", 3),
        ("worst GB/s", "worst_gbps", 3),
        ("GB/s SD", "sd_gbps", 3),
        ("median wall", "median_wall", 0),
        ("mean wall", "mean_wall", 0),
        ("best wall", "best_wall", 0),
        ("worst wall", "worst_wall", 0),
        ("preadv median", "lat_median", 2),
        ("preadv mean", "lat_mean", 2),
        ("preadv p95", "lat_p95", 2),
        ("preadv p99", "lat_p99", 2),
        ("worst preadv", "lat_worst", 1),
        ("reads >=250", "ge250", 0),
        ("reads >=500", "ge500", 0),
        ("reads >=1000", "ge1000", 0),
        ("runs >=500", "runs_ge500", 0),
        ("runs >=1000", "runs_ge1000", 0),
        ("effective concurrency", "effconc", 3),
        ("overlap", "overlap", 4),
        ("max active", "maxif", 0),
        ("completion spread median", "spread", 1),
    ]
    say(f"| {'metric':<24}| {'QD4 (frozen)':>14} | {'QD5':>10} | {'QD6':>10} | {'QD7':>10} |")
    say(f"|{'-'*25}|{'-'*16}|{'-'*12}|{'-'*12}|{'-'*12}|")
    for label, key, digits in rows:
        say(f"| {label:<24}| {_f(agg[4][key], digits):>14} | {_f(agg[5][key], digits):>10} "
            f"| {_f(agg[6][key], digits):>10} | {_f(agg[7][key], digits):>10} |")
    say()

    # ---------------- deltas vs QD4 ----------------
    say("=" * 100)
    say("DELTAS vs FROZEN QD4")
    say("=" * 100)
    say(f"{'metric':<28}{'QD4':>10}{'QD5':>10}{'QD6':>10}{'QD7':>10}")
    for label, key, digits in (("median GB/s", "median_gbps", 3), ("mean GB/s", "mean_gbps", 3),
                               ("median wall ms", "median_wall", 0), ("preadv median ms", "lat_median", 2),
                               ("preadv p95 ms", "lat_p95", 2), ("preadv p99 ms", "lat_p99", 2),
                               ("effective concurrency", "effconc", 3)):
        say(f"{label:<28}" + "".join(f"{_f(agg[qd][key], digits):>10}" for qd in _QDS))
    say()
    say(f"{'delta (abs / pct)':<28}{'QD4':>10}{'QD5':>10}{'QD6':>10}{'QD7':>10}")
    for label, key, digits in (("median GB/s", "median_gbps", 3), ("mean GB/s", "mean_gbps", 3),
                               ("median wall ms", "median_wall", 0), ("preadv median ms", "lat_median", 2),
                               ("preadv p95 ms", "lat_p95", 2), ("preadv p99 ms", "lat_p99", 2),
                               ("effective concurrency", "effconc", 3)):
        base = agg[4][key]
        cells = []
        for qd in _QDS:
            if qd == 4:
                cells.append("-")
                continue
            delta = agg[qd][key] - base
            pct = (100.0 * delta / base) if base else float("nan")
            cells.append(f"{delta:+.{digits}f}/{pct:+.1f}%")
        say(f"{label:<28}" + "".join(f"{c:>10}" for c in cells))
    say()

    # ---------------- knee table ----------------
    say("=" * 100)
    say("THROUGHPUT vs ORDINARY READ INFLATION  (the knee)")
    say("=" * 100)
    say(f"{'QD':>3}{'eff conc':>10}{'g0 median':>11}{'g1+ median':>12}{'steady mean':>13}"
        f"{'steady p95':>12}{'median GB/s':>13}{'mean GB/s':>11}")
    for qd in _QDS:
        b = _gen_buckets(runs[qd])
        g1p = b[1] + b[2] + b[3] + b["g4+"]
        say(f"{qd:>3}{_f(agg[qd]['effconc']):>10}{_f(percentile(b[0], 50), 2):>11}"
            f"{_f(percentile(g1p, 50), 2):>12}{_f(statistics.fmean(g1p), 2):>13}"
            f"{_f(percentile(g1p, 95), 2):>12}{_f(agg[qd]['median_gbps']):>13}"
            f"{_f(agg[qd]['mean_gbps']):>11}")
    say()

    # ---------------- generation analysis ----------------
    say("=" * 100)
    say("GENERATION ANALYSIS")
    say("=" * 100)
    say(f"{'QD':>3}{'gen':>5}{'n':>6}{'median':>9}{'mean':>9}{'p95':>9}{'worst':>10}"
        f"{'>=250':>7}{'>=500':>7}{'>=1000':>8}")
    for qd in _QDS:
        b = _gen_buckets(runs[qd])
        for key in _GEN_KEYS:
            vals = b[key]
            if not vals:
                continue
            say(f"{qd:>3}{str(key):>5}{len(vals):>6}{_f(percentile(vals, 50), 2):>9}"
                f"{_f(statistics.fmean(vals), 2):>9}{_f(percentile(vals, 95), 2):>9}"
                f"{_f(max(vals), 2):>10}{_tails(vals, 250):>7}{_tails(vals, 500):>7}"
                f"{_tails(vals, 1000):>8}")
        say()

    # ---------------- provider breakdown ----------------
    say("=" * 100)
    say("PROVIDER BREAKDOWN  (unpinned; odin excluded)")
    say("=" * 100)
    providers = sorted({_provider(r) for qd in _QDS for r in runs[qd]})
    say("provider counts per QD:")
    for qd in _QDS:
        counts: dict[str, int] = {}
        for r in runs[qd]:
            counts[_provider(r)] = counts.get(_provider(r), 0) + 1
        say(f"  QD{qd}: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    say()
    say(f"| {'provider':<12}| {'QD':>3} | {'n':>3} | {'median GB/s':>11} | {'mean':>7} | "
        f"{'best':>7} | {'worst':>7} | {'preadv med':>10} | {'>=500':>6} |")
    say(f"|{'-'*13}|{'-'*5}|{'-'*5}|{'-'*13}|{'-'*9}|{'-'*9}|{'-'*9}|{'-'*12}|{'-'*8}|")
    for provider in providers:
        for qd in _QDS:
            sub = [r for r in runs[qd] if _provider(r) == provider]
            if not sub:
                continue
            g, lat = _gbps(sub), _lat(sub)
            say(f"| {provider:<12}| {qd:>3} | {len(sub):>3} | {percentile(g,50):>11.3f} | "
                f"{statistics.fmean(g):>7.3f} | {max(g):>7.3f} | {min(g):>7.3f} | "
                f"{percentile(lat,50):>10.2f} | {_tails(lat,500):>6} |")
    say()

    # ---------------- GCP-only ----------------
    say("=" * 100)
    say("GCP-ONLY SENSITIVITY (main causal check)")
    say("=" * 100)
    say(f"{'QD':>3}{'n':>4}{'median GB/s':>13}{'mean GB/s':>11}{'best':>8}{'worst':>8}{'SD':>8}"
        f"{'preadv med':>11}{'steady med':>11}{'eff conc':>10}{'>=500':>7}{'>=1000':>8}")
    for qd in _QDS:
        sub = _gcp_only(runs[qd])
        if not sub:
            say(f"{qd:>3}   (no GCP runs)")
            continue
        g, lat = _gbps(sub), _lat(sub)
        b = _gen_buckets(sub)
        g1p = b[1] + b[2] + b[3] + b["g4+"]
        say(f"{qd:>3}{len(sub):>4}{percentile(g,50):>13.3f}{statistics.fmean(g):>11.3f}"
            f"{max(g):>8.3f}{min(g):>8.3f}{statistics.pstdev(g):>8.3f}"
            f"{percentile(lat,50):>11.2f}{percentile(g1p,50):>11.2f}"
            f"{_effconc(sub):>10.3f}{_tails(lat,500):>7}{_tails(lat,1000):>8}")
    say()
    gcp_med = {}
    for qd in _QDS:
        sub = _gcp_only(runs[qd])
        gcp_med[qd] = percentile(_gbps(sub), 50) if sub else float("nan")
    if all(gcp_med[qd] == gcp_med[qd] for qd in _QDS):
        base = gcp_med[4]
        say("GCP-only median GB/s deltas vs QD4:")
        for qd in (5, 6, 7):
            d = gcp_med[qd] - base
            say(f"  QD{qd}: {gcp_med[qd]:.3f}  delta={d:+.3f}  ({100.0*d/base:+.1f}%)")
    say()
    pooled_rank = sorted(_QDS, key=lambda q: -agg[q]["median_gbps"])
    gcp_rank = sorted((q for q in _QDS if gcp_med[q] == gcp_med[q]), key=lambda q: -gcp_med[q])
    say(f"pooled median ordering   : {pooled_rank}")
    say(f"GCP-only median ordering : {gcp_rank}")
    say(f"orderings agree: {pooled_rank == gcp_rank}")
    say()

    # ---------------- target checks ----------------
    say("=" * 100)
    say("TARGET CHECKS")
    say("=" * 100)
    say(f"{'QD':>3}{'>=6.0 med':>11}{'>=6.5 med':>11}{'>=7.0 med':>11}{'median':>9}"
        f"{'lat med':>9}{'>=500':>7}{'>=1000':>8}{'SD':>8}")
    for qd in _QDS:
        m = agg[qd]["median_gbps"]
        say(f"{qd:>3}{str(m >= 6.0):>11}{str(m >= 6.5):>11}{str(m >= 7.0):>11}{m:>9.3f}"
            f"{agg[qd]['lat_median']:>9.2f}{agg[qd]['ge500']:>7}{agg[qd]['ge1000']:>8}"
            f"{agg[qd]['sd_gbps']:>8.3f}")
    say()

    # ---------------- worker balance ----------------
    say("=" * 100)
    say("WORKER BALANCE")
    say("=" * 100)
    say(f"{'QD':>3}{'spread med':>12}{'spread max':>12}{'wkr wall med':>14}"
        f"{'wkr worst read max':>20}{'bytes/wkr distinct':>20}")
    for qd in _QDS:
        rs = runs[qd]
        spreads = [float(r["final_worker_completion_spread_ms"]) for r in rs
                   if r.get("final_worker_completion_spread_ms") is not None]
        wstats = [w for r in rs for w in (r.get("worker_stats") or [])]
        wwall = [float(w["source_wall_ms"]) for w in wstats if "source_wall_ms" in w]
        wworst = [float(w["worst_preadv_ms"]) for w in wstats if "worst_preadv_ms" in w]
        byt = sorted({int(w["bytes"]) for w in wstats if "bytes" in w})
        say(f"{qd:>3}{_f(percentile(spreads,50),1):>12}{_f(max(spreads),1):>12}"
            f"{_f(percentile(wwall,50),1):>14}{_f(max(wworst),1):>20}{str(byt):>20}")
    say()

    # ---------------- answers ----------------
    say("=" * 100)
    say("FINAL ANSWERS")
    say("=" * 100)
    best_pooled = max(_QDS, key=lambda q: agg[q]["median_gbps"])
    best_mean = max(_QDS, key=lambda q: agg[q]["mean_gbps"])
    say(f"1.  QD4 median GB/s        : {agg[4]['median_gbps']:.3f}")
    say(f"2.  QD5 median GB/s        : {agg[5]['median_gbps']:.3f}")
    say(f"3.  QD6 median GB/s        : {agg[6]['median_gbps']:.3f}")
    say(f"4.  QD7 median GB/s        : {agg[7]['median_gbps']:.3f}")
    say(f"5.  highest raw median QD  : QD{best_pooled} ({agg[best_pooled]['median_gbps']:.3f} GB/s)")
    say(f"6.  same ordering GCP-only : {pooled_rank == gcp_rank}  (pooled {pooled_rank}, GCP {gcp_rank})")
    say(f"7.  highest mean QD        : QD{best_mean} ({agg[best_mean]['mean_gbps']:.3f} GB/s)")
    say(f"8.  preadv median by QD    : " + ", ".join(
        f"QD{q}={agg[q]['lat_median']:.2f}" for q in _QDS) + " ms")
    say(f"9.  eff concurrency by QD  : " + ", ".join(
        f"QD{q}={agg[q]['effconc']:.3f}" for q in _QDS))
    say(f"11. best balance (spread)  : QD{min(_QDS, key=lambda q: agg[q]['spread'])} "
        f"({min(agg[q]['spread'] for q in _QDS):.1f} ms median spread)")
    say(f"12. lowest tail rate >=500 : QD{min(_QDS, key=lambda q: agg[q]['ge500'])} "
        f"({min(agg[q]['ge500'] for q in _QDS)} reads)")
    say(f"13. >=6.0 GB/s median      : " + ", ".join(
        f"QD{q}={agg[q]['median_gbps'] >= 6.0}" for q in _QDS))
    say(f"14. >=6.5 GB/s median      : " + ", ".join(
        f"QD{q}={agg[q]['median_gbps'] >= 6.5}" for q in _QDS))
    say(f"15. >=7.0 GB/s median      : " + ", ".join(
        f"QD{q}={agg[q]['median_gbps'] >= 7.0}" for q in _QDS))
    say()

    (sweep / "ANALYSIS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if per_run_rows:
        with (sweep / "per_run_metrics.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(per_run_rows[0].keys()))
            w.writeheader()
            w.writerows(per_run_rows)
    print(f"\nwritten: {sweep/'ANALYSIS.txt'}, {sweep/'per_run_metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
