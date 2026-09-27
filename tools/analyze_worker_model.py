#!/usr/bin/env python
"""Analysis for the paired THREADS-vs-PROCESSES H100 discriminator.

Descriptive-first.  Adds a region-stratified view because Modal placed the two
arms in different regions, which is a confound that must be reported rather
than ignored.  A paired bootstrap of the median delta is included as a
descriptive interval, not as a significance claim.
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
from comfymodal_runtime.source_race_oracle import percentile  # noqa: E402

_RUNS = _ROOT / "worker_model_runs"
_ARMS = ("threads", "processes")
_LABEL = {"threads": "4 threads / 1 process", "processes": "4 processes / 1 reader each"}
_BOOT_SEED = 20260924
_BOOT_N = 10000


def _load() -> dict[str, dict[int, dict[str, Any]]]:
    out: dict[str, dict[int, dict[str, Any]]] = {a: {} for a in _ARMS}
    for arm in _ARMS:
        for path in sorted(_RUNS.glob(f"wm-{arm}-r*.json")):
            if "invalid" in path.name:
                continue
            run = json.loads(path.read_text(encoding="utf-8"))
            out[arm][int(path.stem.split("-r")[1])] = run
    return out


def _f(value: Any, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _norm_cloud(value: Any) -> str:
    """Modal reports the provider as the proto enum name, e.g. CLOUD_PROVIDER_AWS."""
    text = str(value or "").strip().lower()
    prefix = "cloud_provider_"
    if text.startswith(prefix):
        text = text[len(prefix):]
    return text


def _dist(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "min": min(values),
        "p10": percentile(values, 10),
        "median": percentile(values, 50),
        "mean": statistics.fmean(values),
        "p90": percentile(values, 90),
        "p95": percentile(values, 95),
        "p99": percentile(values, 99),
        "max": max(values),
        "sd": statistics.pstdev(values) if len(values) > 1 else 0.0,
    }


def _pooled(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for run in runs for r in (run.get("reads") or [])]


def main() -> int:
    global _RUNS
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", default="worker_model_runs")
    args = parser.parse_args()
    _RUNS = _ROOT / args.dir

    data = _load()
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text, flush=True)

    n_runs = {a: len(data[a]) for a in _ARMS}
    say("=" * 92)
    say("THREADS vs PROCESSES — matched QD4 / 64 MiB / 4.0 ms global pacer / H100")
    say("=" * 92)
    say(f"runs per arm: {n_runs}")
    say(f"seed: {json.loads((_RUNS / 'schedule.json').read_text())['seed']}")
    say()

    # ---------------- validity ----------------
    say("=" * 92)
    say("VALIDITY CHECK (must hold identically in both arms)")
    say("=" * 92)
    say(f"{'arm':<10}{'qd':>4}{'reads':>7}{'bytes':>13}{'exact':>7}{'maxIF':>7}"
        f"{'clmGapMin':>11}{'model':>11}{'startM':>8}{'PIDs':>5}{'TIDs':>5}")
    validity_ok = True
    for arm in _ARMS:
        for round_no in sorted(data[arm]):
            r = data[arm][round_no]
            cfg, cov = r.get("config") or {}, r.get("coverage") or {}
            ls, pac = r.get("launch_spacing") or {}, r.get("pacer") or {}
            ok = (int(cfg.get("qd") or 0) == 4
                  and int(ls.get("max_simultaneous_in_flight") or 0) <= 4
                  and cov.get("covers_entire_file_exactly_once")
                  and not r.get("worker_errors") and not r.get("barrier_error")
                  and float(pac.get("observed_min_global_claim_gap_ms") or 0) >= 4.0)
            validity_ok = validity_ok and ok
            say(f"{arm:<10}{cfg.get('qd'):>4}{r.get('physical_reads'):>7}"
                f"{r.get('useful_bytes'):>13}{str(bool(cov.get('covers_entire_file_exactly_once'))):>7}"
                f"{ls.get('max_simultaneous_in_flight'):>7}"
                f"{_f(pac.get('observed_min_global_claim_gap_ms')):>11}"
                f"{str(r.get('worker_model')):>11}"
                f"{int(len(set(r.get('worker_pids') or []))):>5}"
                f"{int(len(set(r.get('worker_tids') or []))):>5}")
    say(f"\nALL VALIDITY CONDITIONS HOLD: {validity_ok}")
    same_reads = len({int(r.get('physical_reads') or 0)
                      for a in _ARMS for r in data[a].values()}) == 1
    same_bytes = len({int(r.get('useful_bytes') or 0)
                      for a in _ARMS for r in data[a].values()}) == 1
    say(f"identical read count across every run: {same_reads}")
    say(f"identical byte count across every run: {same_bytes}")
    say()

    # ---------------- per-run ----------------
    say("=" * 92)
    say("PER-RUN")
    say("=" * 92)
    say(f"{'arm':<10}{'rnd':>4}{'prov':<10}{'region':<16}{'wall':>8}{'GB/s':>7}{'best':>7}{'p10':>7}"
        f"{'med':>7}{'mean':>7}{'p95':>8}{'p99':>9}{'worst':>9}{'SD':>7}"
        f"{'>250':>6}{'>500':>6}{'>1k':>5}{'conc':>6}{'ovl':>6}{'mx':>4}{'spread':>8}")
    per_run_rows: list[dict[str, Any]] = []
    for arm in _ARMS:
        for round_no in sorted(data[arm]):
            r = data[arm][round_no]
            d = [x["preadv_ms"] for x in (r.get("reads") or [])]
            th = r.get("thresholds") or {}
            ls = r.get("launch_spacing") or {}
            say(f"{arm:<10}{round_no:>4}{_norm_cloud((r.get('identity') or {}).get('provider')):<10}"
                f"{str(r.get('region')):<16}"
                f"{_f(r.get('full_file_wall_ms'), 0):>8}"
                f"{_f(r.get('full_file_decimal_gbps')):>7}"
                f"{_f(min(d), 1):>7}{_f(percentile(d, 10), 1):>7}"
                f"{_f(percentile(d, 50), 1):>7}{_f(statistics.fmean(d), 1):>7}"
                f"{_f(percentile(d, 95), 1):>8}{_f(percentile(d, 99), 1):>9}"
                f"{_f(max(d), 1):>9}"
                f"{_f(statistics.pstdev(d), 1):>7}"
                f"{th.get('ge_250', 0):>6}{th.get('ge_500', 0):>6}{th.get('ge_1000', 0):>5}"
                f"{_f(ls.get('mean_effective_concurrency')):>6}"
                f"{_f(ls.get('frac_entered_with_other_active')):>6}"
                f"{ls.get('max_simultaneous_in_flight'):>4}"
                f"{_f(r.get('final_worker_completion_spread_ms'), 1):>8}")
            per_run_rows.append({
                "arm": arm, "round": round_no, "region": r.get("region"),
                "provider": (r.get("identity") or {}).get("provider"),
                "pin_cloud": r.get("pin_cloud"), "pin_region": r.get("pin_region"),
                "gpu": (r.get("identity") or {}).get("observed_gpu"),
                "wall_ms": r.get("full_file_wall_ms"),
                "gbps": r.get("full_file_decimal_gbps"),
                "preadv_median": percentile(d, 50), "preadv_mean": statistics.fmean(d),
                "preadv_p95": percentile(d, 95), "preadv_p99": percentile(d, 99),
                "preadv_worst": max(d), "preadv_best": min(d),
                "ge_250": th.get("ge_250"), "ge_500": th.get("ge_500"),
                "ge_1000": th.get("ge_1000"),
                "eff_concurrency": ls.get("mean_effective_concurrency"),
                "overlap": ls.get("frac_entered_with_other_active"),
                "max_in_flight": ls.get("max_simultaneous_in_flight"),
                "min_claim_gap_ms": (r.get("pacer") or {}).get("observed_min_global_claim_gap_ms"),
                "median_claim_gap_ms": (r.get("pacer") or {}).get("observed_median_global_claim_gap_ms"),
                "lock_hold_median_us": (r.get("pacer") or {}).get("lock_hold_median_us"),
                "completion_spread_ms": r.get("final_worker_completion_spread_ms"),
                "spawn_to_ready_ms": r.get("process_spawn_to_all_ready_ms"),
                "start_method": (r.get("env") or {}).get("multiprocessing_start_method"),
                "n_pids": len(set(r.get("worker_pids") or [])),
                "n_tids": len(set(r.get("worker_tids") or [])),
            })
    say()

    # ---------------- headline per arm ----------------
    gbps = {a: [float(r["full_file_decimal_gbps"]) for r in data[a].values()] for a in _ARMS}
    wall = {a: [float(r["full_file_wall_ms"]) for r in data[a].values()] for a in _ARMS}
    pooled = {a: _pooled(list(data[a].values())) for a in _ARMS}
    pooled_ms = {a: [x["preadv_ms"] for x in pooled[a]] for a in _ARMS}

    say("=" * 92)
    say("HEADLINE AGGREGATE PER ARM")
    say("=" * 92)
    for metric, series in (("GB/s", gbps), ("source wall ms", wall)):
        say(f"--- {metric} ---")
        say(f"{'arm':<10}{'min/best':>10}{'p10':>9}{'median':>9}{'mean':>9}{'p90':>9}"
            f"{'max/worst':>11}{'SD':>9}")
        for arm in _ARMS:
            s = series[arm]
            lo, hi = (min(s), max(s)) if metric == "GB/s" else (min(s), max(s))
            say(f"{arm:<10}{_f(lo):>10}{_f(percentile(s, 10)):>9}{_f(percentile(s, 50)):>9}"
                f"{_f(statistics.fmean(s)):>9}{_f(percentile(s, 90)):>9}{_f(hi):>11}"
                f"{_f(statistics.pstdev(s)):>9}")
        say()
    say("--- pooled preadv latency (ms) ---")
    say(f"{'arm':<10}{'n':>6}{'best':>8}{'p10':>8}{'median':>8}{'mean':>8}{'p95':>9}"
        f"{'p99':>10}{'worst':>10}{'SD':>8}")
    for arm in _ARMS:
        d = pooled_ms[arm]
        say(f"{arm:<10}{len(d):>6}{_f(min(d), 2):>8}{_f(percentile(d, 10), 2):>8}"
            f"{_f(percentile(d, 50), 2):>8}{_f(statistics.fmean(d), 2):>8}"
            f"{_f(percentile(d, 95), 2):>9}{_f(percentile(d, 99), 2):>10}"
            f"{_f(max(d), 2):>10}{_f(statistics.pstdev(d), 2):>8}")
    say()
    say("--- tails ---")
    say(f"{'arm':<10}{'reads>=250':>12}{'reads>=500':>12}{'reads>=1000':>13}"
        f"{'runs>=250':>11}{'runs>=500':>11}{'runs>=1000':>12}")
    for arm in _ARMS:
        runs = list(data[arm].values())
        say(f"{arm:<10}"
            f"{sum(1 for x in pooled_ms[arm] if x >= 250):>12}"
            f"{sum(1 for x in pooled_ms[arm] if x >= 500):>12}"
            f"{sum(1 for x in pooled_ms[arm] if x >= 1000):>13}"
            f"{sum(1 for r in runs if (r.get('thresholds') or {}).get('ge_250')):>11}"
            f"{sum(1 for r in runs if (r.get('thresholds') or {}).get('ge_500')):>11}"
            f"{sum(1 for r in runs if (r.get('thresholds') or {}).get('ge_1000')):>12}")
    say()
    say("--- concurrency / pacer ---")
    say(f"{'arm':<10}{'meanEffConc':>13}{'medEffConc':>12}{'meanOverlap':>13}"
        f"{'maxActive':>10}{'minClaimGap':>13}{'medClaimGap':>13}{'lockHoldUs':>12}")
    for arm in _ARMS:
        runs = list(data[arm].values())
        ec = [float((r.get('launch_spacing') or {})['mean_effective_concurrency']) for r in runs]
        ov = [float((r.get('launch_spacing') or {})['frac_entered_with_other_active']) for r in runs]
        mx = [int((r.get('launch_spacing') or {})['max_simultaneous_in_flight']) for r in runs]
        cg = [float((r.get('pacer') or {})['observed_min_global_claim_gap_ms']) for r in runs]
        mcg = [float((r.get('pacer') or {})['observed_median_global_claim_gap_ms']) for r in runs]
        lh = [float((r.get('pacer') or {})['lock_hold_median_us']) for r in runs]
        say(f"{arm:<10}{_f(statistics.fmean(ec)):>13}{_f(percentile(ec, 50)):>12}"
            f"{_f(statistics.fmean(ov), 4):>13}{max(mx):>10}{_f(min(cg), 4):>13}"
            f"{_f(statistics.fmean(mcg)):>13}{_f(statistics.fmean(lh)):>12}")
    say()
    say("--- worker balance ---")
    say(f"{'arm':<10}{'bytes/wkr':>11}{'wallMed':>9}{'wallSpreadMed':>14}"
        f"{'worstPreadvMax':>16}{'meanPreadvMax':>15}")
    for arm in _ARMS:
        runs = list(data[arm].values())
        wstats = [w for r in runs for w in (r.get("worker_stats") or [])]
        spans = [float(w["source_wall_ms"]) for w in wstats if "source_wall_ms" in w]
        means = [float(w["mean_preadv_ms"]) for w in wstats if "mean_preadv_ms" in w]
        worsts = [float(w["worst_preadv_ms"]) for w in wstats if "worst_preadv_ms" in w]
        bytes_set = {int(w["bytes"]) for w in wstats if "bytes" in w}
        spreads = [float(r["final_worker_completion_spread_ms"]) for r in runs
                   if r.get("final_worker_completion_spread_ms") is not None]
        say(f"{arm:<10}{str(sorted(bytes_set)):>11}{_f(percentile(spans, 50), 1):>9}"
            f"{_f(percentile(spreads, 50), 1):>14}{_f(max(worsts), 1):>16}"
            f"{_f(max(means), 1):>15}")
    say()

    # ---------------- headline table ----------------
    say("=" * 92)
    say("HEADLINE TABLE")
    say("=" * 92)
    rows = [
        ("runs", n_runs["threads"], n_runs["processes"], "0"),
        ("median GB/s", percentile(gbps["threads"], 50), percentile(gbps["processes"], 50), "3"),
        ("mean GB/s", statistics.fmean(gbps["threads"]), statistics.fmean(gbps["processes"]), "3"),
        ("best GB/s", max(gbps["threads"]), max(gbps["processes"]), "3"),
        ("worst GB/s", min(gbps["threads"]), min(gbps["processes"]), "3"),
        ("GB/s SD", statistics.pstdev(gbps["threads"]), statistics.pstdev(gbps["processes"]), "3"),
        ("median source wall ms", percentile(wall["threads"], 50), percentile(wall["processes"], 50), "0"),
        ("mean source wall ms", statistics.fmean(wall["threads"]), statistics.fmean(wall["processes"]), "0"),
        ("best source wall ms", min(wall["threads"]), min(wall["processes"]), "0"),
        ("worst source wall ms", max(wall["threads"]), max(wall["processes"]), "0"),
        ("pooled preadv median", percentile(pooled_ms["threads"], 50), percentile(pooled_ms["processes"], 50), "2"),
        ("pooled preadv mean", statistics.fmean(pooled_ms["threads"]), statistics.fmean(pooled_ms["processes"]), "2"),
        ("preadv p95", percentile(pooled_ms["threads"], 95), percentile(pooled_ms["processes"], 95), "2"),
        ("preadv p99", percentile(pooled_ms["threads"], 99), percentile(pooled_ms["processes"], 99), "2"),
        ("worst preadv", max(pooled_ms["threads"]), max(pooled_ms["processes"]), "1"),
        ("reads >=250", sum(1 for x in pooled_ms["threads"] if x >= 250),
         sum(1 for x in pooled_ms["processes"] if x >= 250), "0"),
        ("reads >=500", sum(1 for x in pooled_ms["threads"] if x >= 500),
         sum(1 for x in pooled_ms["processes"] if x >= 500), "0"),
        ("reads >=1000", sum(1 for x in pooled_ms["threads"] if x >= 1000),
         sum(1 for x in pooled_ms["processes"] if x >= 1000), "0"),
        ("runs >=500", sum(1 for r in data["threads"].values() if (r.get("thresholds") or {}).get("ge_500")),
         sum(1 for r in data["processes"].values() if (r.get("thresholds") or {}).get("ge_500")), "0"),
        ("runs >=1000", sum(1 for r in data["threads"].values() if (r.get("thresholds") or {}).get("ge_1000")),
         sum(1 for r in data["processes"].values() if (r.get("thresholds") or {}).get("ge_1000")), "0"),
        ("effective concurrency",
         statistics.fmean([float((r.get('launch_spacing') or {})['mean_effective_concurrency']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('launch_spacing') or {})['mean_effective_concurrency']) for r in data["processes"].values()]), "3"),
        ("overlap",
         statistics.fmean([float((r.get('launch_spacing') or {})['frac_entered_with_other_active']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('launch_spacing') or {})['frac_entered_with_other_active']) for r in data["processes"].values()]), "4"),
        ("max active",
         max(int((r.get('launch_spacing') or {})['max_simultaneous_in_flight']) for r in data["threads"].values()),
         max(int((r.get('launch_spacing') or {})['max_simultaneous_in_flight']) for r in data["processes"].values()), "0"),
    ]
    say(f"| {'metric':<24}| {_LABEL['threads']:>24} | {_LABEL['processes']:>29} |")
    say(f"|{'-'*25}|{'-'*26}|{'-'*31}|")
    for name, t, p, digits in rows:
        say(f"| {name:<24}| {_f(t, int(digits)):>24} | {_f(p, int(digits)):>29} |")
    d_med = percentile(gbps["processes"], 50) - percentile(gbps["threads"], 50)
    d_mean = statistics.fmean(gbps["processes"]) - statistics.fmean(gbps["threads"])
    say()
    say(f"PROCESS median GB/s delta   : {d_med:+.3f}  ({100.0 * d_med / percentile(gbps['threads'], 50):+.1f}%)")
    say(f"PROCESS mean   GB/s delta   : {d_mean:+.3f}  ({100.0 * d_mean / statistics.fmean(gbps['threads']):+.1f}%)")
    say()

    # ---------------- provider breakdown ----------------
    def _provider_block(label: str, runs: list[dict[str, Any]]) -> None:
        if not runs:
            say(f"--- {label}: NO RUNS ---")
            return
        g = [float(r["full_file_decimal_gbps"]) for r in runs]
        w = [float(r["full_file_wall_ms"]) for r in runs]
        pm = [x["preadv_ms"] for r in runs for x in (r.get("reads") or [])]
        ec = [float((r.get("launch_spacing") or {})["mean_effective_concurrency"]) for r in runs]
        ov = [float((r.get("launch_spacing") or {})["frac_entered_with_other_active"]) for r in runs]
        mx = [int((r.get("launch_spacing") or {})["max_simultaneous_in_flight"]) for r in runs]
        say(f"--- {label}: {len(runs)} runs / {len(pm)} reads ---")
        say(f"  GB/s    min={min(g):.3f}  p10={percentile(g,10):.3f}  median={percentile(g,50):.3f}  "
            f"mean={statistics.fmean(g):.3f}  p90={percentile(g,90):.3f}  max={max(g):.3f}  "
            f"SD={statistics.pstdev(g):.3f}")
        say(f"  wall ms best={min(w):.0f}  p10={percentile(w,10):.0f}  median={percentile(w,50):.0f}  "
            f"mean={statistics.fmean(w):.0f}  p90={percentile(w,90):.0f}  worst={max(w):.0f}  "
            f"SD={statistics.pstdev(w):.0f}")
        say(f"  preadv  n={len(pm)}  best={min(pm):.2f}  p10={percentile(pm,10):.2f}  "
            f"median={percentile(pm,50):.2f}  mean={statistics.fmean(pm):.2f}  "
            f"p95={percentile(pm,95):.2f}  p99={percentile(pm,99):.2f}  worst={max(pm):.2f}  "
            f"SD={statistics.pstdev(pm):.2f}")
        say(f"  tails   reads>=250={sum(1 for x in pm if x >= 250)}  "
            f">=500={sum(1 for x in pm if x >= 500)}  >=1000={sum(1 for x in pm if x >= 1000)}  |  "
            f"runs>=500={sum(1 for r in runs if (r.get('thresholds') or {}).get('ge_500'))}  "
            f"runs>=1000={sum(1 for r in runs if (r.get('thresholds') or {}).get('ge_1000'))}")
        say(f"  conc    meanEffConc={statistics.fmean(ec):.3f}  medianEffConc={percentile(ec,50):.3f}  "
            f"overlap={statistics.fmean(ov):.4f}  maxActive={max(mx)}")
        for arm in _ARMS:
            sub = [r for r in runs if str(r.get("worker_model") or "") == arm]
            if not sub:
                continue
            sg = [float(r["full_file_decimal_gbps"]) for r in sub]
            sw = [float(r["full_file_wall_ms"]) for r in sub]
            spm = [x["preadv_ms"] for r in sub for x in (r.get("reads") or [])]
            say(f"    {arm:<10} n={len(sub):>2}  gbps median={percentile(sg,50):.3f} mean={statistics.fmean(sg):.3f} "
                f"best={max(sg):.3f} worst={min(sg):.3f}  |  wall median={percentile(sw,50):.0f}  |  "
                f"preadv median={percentile(spm,50):.2f} mean={statistics.fmean(spm):.2f} "
                f"worst={max(spm):.1f}  |  reads>=500={sum(1 for x in spm if x >= 500)}")

    all_runs = [r for a in _ARMS for r in data[a].values()]
    by_provider: dict[str, list[dict[str, Any]]] = {}
    for r in all_runs:
        key = _norm_cloud((r.get("identity") or {}).get("provider")) or "unspecified"
        by_provider.setdefault(key, []).append(r)

    say("=" * 92)
    say("PROVIDER BREAKDOWN  (no pinning; odin runs invalidated and excluded)")
    say("=" * 92)
    _provider_block("ALL", all_runs)
    say()
    for provider in ("aws", "gcp"):
        _provider_block(provider.upper(), by_provider.get(provider, []))
        say()
    for provider in sorted(k for k in by_provider if k not in ("aws", "gcp")):
        _provider_block(f"other/{provider}", by_provider[provider])
        say()
    say("provider counts: " + ", ".join(
        f"{k}={len(v)}" for k, v in sorted(by_provider.items(), key=lambda kv: -len(kv[1]))))
    say()

    # ---------------- paired ----------------
    say("=" * 92)
    say("PAIRED ANALYSIS (temporal pairs from the saved schedule)")
    say("=" * 92)
    say(f"| {'round':>5} | {'threads GB/s':>12} | {'processes GB/s':>14} | {'delta':>8} | {'delta %':>8} "
        f"| {'tWall':>7} | {'pWall':>7} | {'wall delta':>10} |")
    say(f"|{'-'*7}|{'-'*14}|{'-'*16}|{'-'*10}|{'-'*10}|{'-'*9}|{'-'*9}|{'-'*12}|")
    pairs: list[dict[str, Any]] = []
    for round_no in sorted(data["threads"]):
        t, p = data["threads"][round_no], data["processes"][round_no]
        tg, pg = float(t["full_file_decimal_gbps"]), float(p["full_file_decimal_gbps"])
        tw, pw = float(t["full_file_wall_ms"]), float(p["full_file_wall_ms"])
        d, dp = pg - tg, 100.0 * (pg - tg) / tg
        pairs.append({"round": round_no, "t_gbps": tg, "p_gbps": pg, "delta": d,
                      "delta_pct": dp, "t_wall": tw, "p_wall": pw, "wall_delta": pw - tw})
        say(f"| {round_no:>5} | {tg:>12.3f} | {pg:>14.3f} | {d:>+8.3f} | {dp:>+7.1f}% "
            f"| {tw:>7.0f} | {pw:>7.0f} | {pw - tw:>+10.0f} |")
    deltas = [x["delta"] for x in pairs]
    pcts = [x["delta_pct"] for x in pairs]
    wall_deltas = [x["wall_delta"] for x in pairs]
    win_p = sum(1 for x in pairs if x["delta"] > 0)
    win_t = sum(1 for x in pairs if x["delta"] < 0)
    rng = random.Random(_BOOT_SEED)
    boot = []
    for _ in range(_BOOT_N):
        sample = [deltas[rng.randrange(len(deltas))] for _ in range(len(deltas))]
        boot.append(percentile(sample, 50))
    say()
    say(f"median paired GB/s delta : {percentile(deltas, 50):+.3f} ({percentile(pcts, 50):+.1f}%)")
    say(f"mean   paired GB/s delta : {statistics.fmean(deltas):+.3f} ({statistics.fmean(pcts):+.1f}%)")
    say(f"median paired wall delta : {percentile(wall_deltas, 50):+.0f} ms (negative = processes faster)")
    say(f"pairs PROCESS > THREAD   : {win_p} / {len(pairs)}")
    say(f"pairs THREAD > PROCESS   : {win_t} / {len(pairs)}")
    say(f"paired bootstrap 95% interval on median delta: "
        f"[{percentile(boot, 2.5):+.3f}, {percentile(boot, 97.5):+.3f}] GB/s "
        f"({_BOOT_N} resamples, seed {_BOOT_SEED})")
    say()

    # ---------------- region stratification ----------------
    say("=" * 92)
    say("REGION STRATIFICATION (Modal placed the arms in different regions)")
    say("=" * 92)
    regions: dict[str, dict[str, list[float]]] = {}
    for arm in _ARMS:
        for r in data[arm].values():
            regions.setdefault(str(r.get("region")), {"threads": [], "processes": []})[arm].append(
                float(r["full_file_decimal_gbps"]))
    say(f"{'region':<16}{'arm':<11}{'n':>3}{'GB/s values':>40}{'median':>9}")
    for region in sorted(regions, key=lambda k: -(len(regions[k]['threads']) + len(regions[k]['processes']))):
        for arm in _ARMS:
            vals = regions[region][arm]
            if not vals:
                continue
            say(f"{region:<16}{arm:<11}{len(vals):>3}"
                f"{' '.join(f'{v:.2f}' for v in sorted(vals)):>40}"
                f"{percentile(vals, 50):>9.3f}")
    say()
    odin_t = regions.get("odin", {}).get("threads", [])
    odin_p = regions.get("odin", {}).get("processes", [])
    if odin_t and odin_p:
        mt, mp_ = statistics.fmean(odin_t), statistics.fmean(odin_p)
        say(f"REGION-CONTROLLED (odin only): threads n={len(odin_t)} mean={mt:.3f} | "
            f"processes n={len(odin_p)} mean={mp_:.3f} | delta={mp_ - mt:+.3f} "
            f"({100.0 * (mp_ - mt) / mt:+.1f}%)")
    say()

    # ---------------- mechanism ----------------
    say("=" * 92)
    say("MECHANISM CHECK")
    say("=" * 92)
    say(f"{'metric':<34}{'threads':>14}{'processes':>14}{'delta':>12}")
    def _row(name: str, tv: float, pv: float, digits: int = 2) -> None:
        delta = f"{pv - tv:+.{digits}f}"
        say(f"{name:<34}{_f(tv, digits):>14}{_f(pv, digits):>14}{delta:>12}")
    _row("pooled preadv median ms", percentile(pooled_ms["threads"], 50),
         percentile(pooled_ms["processes"], 50))
    _row("pooled preadv mean ms", statistics.fmean(pooled_ms["threads"]),
         statistics.fmean(pooled_ms["processes"]))
    _row("pooled preadv p95 ms", percentile(pooled_ms["threads"], 95),
         percentile(pooled_ms["processes"], 95))
    _row("pooled preadv p99 ms", percentile(pooled_ms["threads"], 99),
         percentile(pooled_ms["processes"], 99))
    _row("pooled preadv worst ms", max(pooled_ms["threads"]), max(pooled_ms["processes"]))
    _row("effective concurrency",
         statistics.fmean([float((r.get('launch_spacing') or {})['mean_effective_concurrency']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('launch_spacing') or {})['mean_effective_concurrency']) for r in data["processes"].values()]), 3)
    _row("mean overlap",
         statistics.fmean([float((r.get('launch_spacing') or {})['frac_entered_with_other_active']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('launch_spacing') or {})['frac_entered_with_other_active']) for r in data["processes"].values()]), 4)
    _row("min claim gap ms",
         min(float((r.get('pacer') or {})['observed_min_global_claim_gap_ms']) for r in data["threads"].values()),
         min(float((r.get('pacer') or {})['observed_min_global_claim_gap_ms']) for r in data["processes"].values()), 4)
    _row("median claim gap ms",
         statistics.fmean([float((r.get('pacer') or {})['observed_median_global_claim_gap_ms']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('pacer') or {})['observed_median_global_claim_gap_ms']) for r in data["processes"].values()]), 3)
    _row("pacer lock hold median us",
         statistics.fmean([float((r.get('pacer') or {})['lock_hold_median_us']) for r in data["threads"].values()]),
         statistics.fmean([float((r.get('pacer') or {})['lock_hold_median_us']) for r in data["processes"].values()]), 3)
    _row("completion spread median ms",
         percentile([float(r['final_worker_completion_spread_ms']) for r in data["threads"].values()], 50),
         percentile([float(r['final_worker_completion_spread_ms']) for r in data["processes"].values()], 50), 1)
    _row("wall p10 ms",
         percentile(wall["threads"], 10), percentile(wall["processes"], 10), 0)
    _row("wall median ms", percentile(wall["threads"], 50), percentile(wall["processes"], 50), 0)
    pr = [float(r["process_spawn_to_all_ready_ms"]) for r in data["processes"].values()]
    tr = [float(r["process_spawn_to_all_ready_ms"]) for r in data["threads"].values()]
    _row("spawn->all ready median ms", percentile(tr, 50), percentile(pr, 50), 1)
    say()

    # ---------------- clean-subset view ----------------
    say("=" * 92)
    say("EXCLUDING THE TWO CATASTROPHIC THREADS RUNS (sensitivity)")
    say("=" * 92)
    bad = [rn for rn, r in data["threads"].items() if (r.get("thresholds") or {}).get("ge_500")]
    good_t = [float(data["threads"][rn]["full_file_decimal_gbps"])
              for rn in data["threads"] if rn not in bad]
    good_w = [float(data["threads"][rn]["full_file_wall_ms"])
              for rn in data["threads"] if rn not in bad]
    say(f"excluded threads rounds with any read >=500 ms: {sorted(bad)}")
    say(f"threads clean-only n={len(good_t)} median GB/s={percentile(good_t, 50):.3f} "
        f"mean={statistics.fmean(good_t):.3f} median wall={percentile(good_w, 50):.0f} ms")
    say(f"processes      n={n_runs['processes']} median GB/s={percentile(gbps['processes'], 50):.3f} "
        f"mean={statistics.fmean(gbps['processes']):.3f}")
    say()
    say("=" * 92)
    say("OSCILLATION / TAIL SUMMARY")
    say("=" * 92)
    for arm in _ARMS:
        runs = list(data[arm].values())
        worst = max(runs, key=lambda r: float(r["full_file_wall_ms"]))
        say(f"{arm:<10} worst run: round={[k for k,v in data[arm].items() if v is worst][0]} "
            f"region={worst.get('region')} wall={float(worst['full_file_wall_ms']):.0f} ms "
            f"max preadv={worst.get('max_ms'):.1f} ms "
            f"reads>=500={(worst.get('thresholds') or {}).get('ge_500')}")
    say()

    (_RUNS / "ANALYSIS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (_RUNS / "per_run_metrics.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(per_run_rows[0].keys()))
        w.writeheader()
        w.writerows(per_run_rows)
    pooled_rows = [{"arm": a, **x} for a in _ARMS for x in pooled[a]]
    if pooled_rows:
        cols = ["arm", "worker", "pid", "tid", "generation", "block_index", "offset",
                "length", "bytes_returned", "preadv_ms", "global_launch_gap_ms",
                "gate_wait_ms", "pacer_lock_hold_us", "active_at_enter", "refill_gap_ms"]
        with (_RUNS / "pooled_reads.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(pooled_rows)
    print(f"\nwritten: {_RUNS/'ANALYSIS.txt'}, per_run_metrics.csv, pooled_reads.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
