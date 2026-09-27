#!/usr/bin/env python
"""Static-partition worker-imbalance analysis (main goal) + hedge on/off side check.

Handles both read schemas:
  unhedged (run_worker_model_probe)   -> reads[] with preadv_enter_ns / preadv_exit_ns / preadv_ms
  hedged   (run_worker_model_hedge_probe) -> logical_reads[] with logical_enter_ns / logical_exit_ns / logical_ms

All imbalance metrics are derived from those raw timestamps.  No architecture
change is assumed; this is measurement only.
"""
from __future__ import annotations

import argparse
import csv
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


def _f(v: Any, d: int = 2) -> str:
    if v is None:
        return "-"
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return str(v)


def normalize_reads(r: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-worker accepted reads with a common (enter, exit, ms) shape."""
    if r.get("logical_reads"):
        return [{
            "worker": int(x["worker"]), "pid": x.get("pid"),
            "offset": int(x["offset"]), "length": int(x["length"]),
            "bytes": int(x.get("bytes_returned") or 0),
            "enter": int(x["logical_enter_ns"]), "exit": int(x["logical_exit_ns"]),
            "ms": float(x["logical_ms"]), "accepted": x.get("accepted"),
        } for x in r["logical_reads"]]
    return [{
        "worker": int(x["worker"]), "pid": x.get("pid"),
        "offset": int(x["offset"]), "length": int(x["length"]),
        "bytes": int(x.get("bytes_returned") or 0),
        "enter": int(x["preadv_enter_ns"]), "exit": int(x["preadv_exit_ns"]),
        "ms": float(x["preadv_ms"]), "accepted": "original",
    } for x in (r.get("reads") or [])]


def _snapshot(reads: list[dict[str, Any]], t: int) -> dict[str, Any]:
    inflight = [x for x in reads if x["enter"] <= t < x["exit"]]
    unstarted = [x for x in reads if x["enter"] > t]
    return {
        "in_flight_reads": len(inflight),
        "in_flight_bytes": sum(x["length"] for x in inflight),
        "unstarted_reads": len(unstarted),
        "unstarted_bytes": sum(x["length"] for x in unstarted),
        "_inflight": inflight,
    }


def analyse_run(r: dict[str, Any]) -> dict[str, Any]:
    reads = normalize_reads(r)
    if not reads:
        raise ValueError("no reads")
    workers = sorted({x["worker"] for x in reads})
    t0 = min(x["enter"] for x in reads)
    t_end = max(x["exit"] for x in reads)
    wall_ms = (t_end - t0) / 1e6
    file_bytes = int((r.get("coverage") or {}).get("file_size") or 0)

    per_worker: dict[int, dict[str, Any]] = {}
    for w in workers:
        ws = [x for x in reads if x["worker"] == w]
        ms = [x["ms"] for x in ws]
        first_enter = min(x["enter"] for x in ws)
        last_exit = max(x["exit"] for x in ws)
        per_worker[w] = {
            "worker": w,
            "bytes": sum(x["bytes"] for x in ws if x["bytes"] > 0),
            "reads": len(ws),
            "first_enter": first_enter,
            "last_exit": last_exit,
            "active_span_ms": (last_exit - first_enter) / 1e6,
            "finish_from_t0_ms": (last_exit - t0) / 1e6,
            "idle_after_finish_ms": (t_end - last_exit) / 1e6,
            "median_ms": percentile(ms, 50),
            "mean_ms": statistics.fmean(ms),
            "worst_ms": max(ms),
        }

    order = sorted(workers, key=lambda w: per_worker[w]["last_exit"])
    f = [per_worker[w]["last_exit"] for w in order]
    spread_ms = (f[-1] - f[0]) / 1e6
    slowest_minus_second = (f[-1] - f[-2]) / 1e6
    total_stranded = sum(per_worker[w]["idle_after_finish_ms"] for w in workers)
    stranded_frac = total_stranded / (len(workers) * wall_ms) if wall_ms else None

    first_snap = _snapshot(reads, f[0])
    second_snap = _snapshot(reads, f[1]) if len(f) > 1 else first_snap
    slowest = order[-1]
    second_last_finish = f[-2] if len(f) > 1 else f[0]
    slow_reads = [x for x in reads if x["worker"] == slowest]
    slow_snap = _snapshot(slow_reads, second_last_finish)
    remaining_inflight_ms = None
    if slow_snap["_inflight"]:
        remaining_inflight_ms = (max(x["exit"] for x in slow_snap["_inflight"])
                                 - second_last_finish) / 1e6
    inflight = slow_snap["in_flight_reads"]
    unstarted = slow_snap["unstarted_reads"]
    if inflight and unstarted:
        shape = "B_inflight_plus_unstarted"
    elif inflight:
        shape = "A_stuck_on_one_inflight"
    elif unstarted:
        shape = "C_only_unstarted"
    else:
        shape = "D_nearly_complete"

    lat = [x["ms"] for x in reads]
    return {
        "wall_ms": wall_ms, "gbps": float(r.get("full_file_decimal_gbps") or 0.0),
        "provider": _norm_cloud((r.get("identity") or {}).get("provider")),
        "region": str((r.get("identity") or {}).get("region") or ""),
        "file_bytes": file_bytes,
        "per_worker": per_worker, "order": order,
        "earliest_finish_ms": per_worker[order[0]]["finish_from_t0_ms"],
        "second_finish_ms": per_worker[order[1]]["finish_from_t0_ms"] if len(order) > 1 else None,
        "third_finish_ms": per_worker[order[2]]["finish_from_t0_ms"] if len(order) > 2 else None,
        "slowest_finish_ms": per_worker[order[-1]]["finish_from_t0_ms"],
        "finish_spread_ms": spread_ms,
        "slowest_minus_second_slowest_ms": slowest_minus_second,
        "total_stranded_worker_ms": total_stranded,
        "stranded_capacity_fraction": stranded_frac,
        "first_finish_unstarted_reads": first_snap["unstarted_reads"],
        "first_finish_unstarted_bytes": first_snap["unstarted_bytes"],
        "first_finish_unstarted_fraction": (first_snap["unstarted_bytes"] / file_bytes
                                            if file_bytes else None),
        "first_finish_inflight_bytes": first_snap["in_flight_bytes"],
        "second_finish_unstarted_reads": second_snap["unstarted_reads"],
        "second_finish_unstarted_bytes": second_snap["unstarted_bytes"],
        "second_finish_unstarted_fraction": (second_snap["unstarted_bytes"] / file_bytes
                                             if file_bytes else None),
        "second_finish_inflight_bytes": second_snap["in_flight_bytes"],
        "slowest_inflight_reads_at_second_last_finish": slow_snap["in_flight_reads"],
        "slowest_unstarted_reads_at_second_last_finish": slow_snap["unstarted_reads"],
        "slowest_unstarted_bytes_at_second_last_finish": slow_snap["unstarted_bytes"],
        "tail_unstarted_reads": slow_snap["unstarted_reads"],
        "tail_unstarted_bytes": slow_snap["unstarted_bytes"],
        "remaining_inflight_ms": remaining_inflight_ms,
        "tail_shape": shape,
        "worst_preadv_ms": max(lat),
        "lat_median": percentile(lat, 50), "lat_mean": statistics.fmean(lat),
        "lat_p95": percentile(lat, 95), "lat_p99": percentile(lat, 99),
        "ge250": sum(1 for x in lat if x >= 250), "ge500": sum(1 for x in lat if x >= 500),
        "ge1000": sum(1 for x in lat if x >= 1000),
        "eff_conc": (r.get("launch_spacing") or {}).get("mean_effective_concurrency"),
        "max_inflight": (r.get("launch_spacing") or {}).get("max_simultaneous_in_flight"),
        "hedge_attempts": r.get("hedge_attempts"), "hedge_wins": r.get("hedge_wins"),
        "blocks_with_hedge": r.get("blocks_with_hedge"),
        "physical_attempts": r.get("physical_attempts") or len(reads),
    }


def _dist(vals: list[float]) -> str:
    if not vals:
        return "-"
    s = sorted(vals)
    return (f"min={_f(s[0])} p10={_f(percentile(s,10))} p25={_f(percentile(s,25))} "
            f"med={_f(percentile(s,50))} mean={_f(statistics.fmean(s))} "
            f"p75={_f(percentile(s,75))} p90={_f(percentile(s,90))} p95={_f(percentile(s,95))} "
            f"max={_f(s[-1])} SD={_f(statistics.pstdev(s) if len(s)>1 else 0)}")


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


def _ranks(vals: list[float]) -> list[float]:
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    for pos, i in enumerate(order):
        ranks[i] = float(pos)
    return ranks


def load(dir_path: Path, pattern: str) -> list[dict[str, Any]]:
    out = []
    for path in sorted(glob.glob(str(dir_path / pattern))):
        r = json.loads(Path(path).read_text(encoding="utf-8"))
        try:
            a = analyse_run(r)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {Path(path).name}: {exc}")
            continue
        a["file"] = Path(path).name
        a["cohort"] = "hedged" if r.get("logical_reads") else "unhedged"
        out.append(a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hedged-dir", default="imbalance_hedged_runs")
    ap.add_argument("--hedged-glob", default="hn-*.json")
    ap.add_argument("--unhedged-dir", default="imbalance_runs")
    ap.add_argument("--unhedged-glob", default="im-[0-9][0-9].json")
    args = ap.parse_args()

    hedged = load(_ROOT / args.hedged_dir, args.hedged_glob)
    unhedged = load(_ROOT / args.unhedged_dir, args.unhedged_glob)

    lines: list[str] = []

    def say(t: str = "") -> None:
        lines.append(t)
        print(t, flush=True)

    say("=" * 110)
    say("QD4 STATIC-PARTITION WORKER IMBALANCE — main goal")
    say("=" * 110)
    say(f"hedged cohort (250 ms): {len(hedged)} runs   |   hedge-off cohort: {len(unhedged)} runs")
    say()

    # ---- core source stats -------------------------------------------------
    def core(rows: list[dict[str, Any]], label: str) -> None:
        if not rows:
            say(f"--- {label}: no runs ---")
            return
        g = [r["gbps"] for r in rows]
        w = [r["wall_ms"] for r in rows]
        lat = []
        for r in rows:
            lat.append(r["lat_median"])
        say(f"--- {label} (n={len(rows)}) core source stats ---")
        say(f"  GB/s    median={_f(percentile(g,50),3)} mean={_f(statistics.fmean(g),3)} "
            f"best={_f(max(g),3)} worst={_f(min(g),3)} SD={_f(statistics.pstdev(g),3)}")
        say(f"  wall ms median={_f(percentile(w,50),0)} mean={_f(statistics.fmean(w),0)}")
        say(f"  preadv  median={_f(percentile(lat,50))} mean={_f(statistics.fmean(lat))} "
            f"p95={_f(percentile(lat,95))} p99={_f(percentile(lat,99))} worst={_f(max(lat))}")
        say(f"  reads   >=250={sum(r['ge250'] for r in rows)} >=500={sum(r['ge500'] for r in rows)} "
            f">=1000={sum(r['ge1000'] for r in rows)}")
        ec = [r["eff_conc"] for r in rows if r["eff_conc"] is not None]
        mi = [r["max_inflight"] for r in rows if r["max_inflight"] is not None]
        say(f"  conc    eff={_f(statistics.fmean(ec),3) if ec else '-'} "
            f"maxActive={max(mi) if mi else '-'}")
        say()

    core(hedged, "HEDGED 250 ms (primary)")
    core(unhedged, "HEDGE OFF (invalid side cohort)")
    say("  baseline reference: QD4 process median GB/s 5.785, preadv median 41.76 ms, eff conc 3.694")
    say()

    # ---- mandatory distributions -----------------------------------------
    say("=" * 110)
    say("25-RUN AGGREGATE STATISTICS (hedged cohort)")
    say("=" * 110)
    metrics = [
        ("full_file_source_wall_ms", "wall_ms", 0),
        ("GB/s", "gbps", 3),
        ("finish_spread_ms", "finish_spread_ms", 1),
        ("slowest_minus_second_slowest_ms", "slowest_minus_second_slowest_ms", 1),
        ("total_stranded_worker_ms", "total_stranded_worker_ms", 1),
        ("stranded_capacity_fraction", "stranded_capacity_fraction", 4),
        ("first_finish_unstarted_bytes", "first_finish_unstarted_bytes", 0),
        ("first_finish_unstarted_fraction", "first_finish_unstarted_fraction", 4),
        ("second_finish_unstarted_bytes", "second_finish_unstarted_bytes", 0),
        ("second_finish_unstarted_fraction", "second_finish_unstarted_fraction", 4),
        ("tail_unstarted_reads", "tail_unstarted_reads", 0),
        ("tail_unstarted_bytes", "tail_unstarted_bytes", 0),
        ("remaining_inflight_ms", "remaining_inflight_ms", 1),
    ]
    for label, key, _d in metrics:
        vals = [r[key] for r in hedged if r.get(key) is not None]
        say(f"{label:<36}{_dist(vals)}")
    say()

    # ---- worker active span ----------------------------------------------
    say("=" * 110)
    say("WORKER ACTIVE-SPAN DISTRIBUTION")
    say("=" * 110)
    all_spans = [w["active_span_ms"] for r in hedged for w in r["per_worker"].values()]
    say(f"all {len(all_spans)} worker observations: {_dist(all_spans)}")
    say()
    for idx in range(4):
        spans = [r["per_worker"][idx]["active_span_ms"] for r in hedged if idx in r["per_worker"]]
        say(f"  worker{idx}: n={len(spans)} {_dist(spans)}")
    say()

    # ---- finish order -----------------------------------------------------
    say("=" * 110)
    say("FINISH-ORDER DISTRIBUTION")
    say("=" * 110)
    say(f"| {'worker':>6} | {'first':>6} | {'second':>7} | {'third':>6} | {'last':>6} |")
    say(f"|{'-'*8}|{'-'*8}|{'-'*9}|{'-'*8}|{'-'*8}|")
    for idx in range(4):
        counts = [0, 0, 0, 0]
        for r in hedged:
            if idx in r["order"]:
                counts[r["order"].index(idx)] += 1
        say(f"| {idx:>6} | {counts[0]:>6} | {counts[1]:>7} | {counts[2]:>6} | {counts[3]:>6} |")
    say()

    # ---- tail correlation -------------------------------------------------
    say("=" * 110)
    say("TAIL CORRELATION (worst preadv vs imbalance metrics)")
    say("=" * 110)
    for label, key in (("finish_spread_ms", "finish_spread_ms"),
                       ("slowest_minus_second_slowest_ms", "slowest_minus_second_slowest_ms"),
                       ("tail_unstarted_bytes", "tail_unstarted_bytes"),
                       ("total_stranded_worker_ms", "total_stranded_worker_ms")):
        xs = [r["worst_preadv_ms"] for r in hedged]
        ys = [float(r[key]) for r in hedged]
        say(f"  worst_preadv vs {label:<34} pearson={_f(_pearson(xs,ys),3)} "
            f"spearman={_f(_pearson(_ranks(xs),_ranks(ys)),3)}")
    say()

    # ---- provider breakdown ----------------------------------------------
    say("=" * 110)
    say("PROVIDER BREAKDOWN (hedged)")
    say("=" * 110)
    provs = sorted({r["provider"] for r in hedged})
    say(f"| {'provider':<12} | {'runs':>4} | {'med GB/s':>8} | {'med spread':>10} | "
        f"{'med slow-2nd':>12} | {'med 1st-unstart MiB':>19} | {'med tail-unstart MiB':>20} | {'worst spread':>12} |")
    say(f"|{'-'*14}|{'-'*6}|{'-'*10}|{'-'*12}|{'-'*14}|{'-'*21}|{'-'*22}|{'-'*14}|")
    for p in provs:
        sub = [r for r in hedged if r["provider"] == p]
        if len(sub) < 3:
            continue
        say(f"| {p:<12} | {len(sub):>4} | {_f(percentile([x['gbps'] for x in sub],50),3):>8} | "
            f"{_f(percentile([x['finish_spread_ms'] for x in sub],50),1):>10} | "
            f"{_f(percentile([x['slowest_minus_second_slowest_ms'] for x in sub],50),1):>12} | "
            f"{_f(percentile([x['first_finish_unstarted_bytes'] for x in sub],50)/_MIB,1):>19} | "
            f"{_f(percentile([x['tail_unstarted_bytes'] for x in sub],50)/_MIB,1):>20} | "
            f"{_f(max(x['finish_spread_ms'] for x in sub),1):>12} |")
    say()

    # ---- final table ------------------------------------------------------
    say("=" * 110)
    say("FINAL TABLE — one row per hedged run")
    say("=" * 110)
    say(f"{'run':<10}{'provider/region':<24}{'GB/s':>7}"
        f"{'P0 fin':>8}{'P1 fin':>8}{'P2 fin':>8}{'P3 fin':>8}"
        f"{'spread':>8}{'slow-2nd':>9}{'1stUnst MiB':>12}{'2ndUnst MiB':>12}"
        f"{'tailUnst MiB':>13}{'remInfl':>8}{'shape':>26}")
    for r in sorted(hedged, key=lambda x: x["file"]):
        fins = [r["per_worker"][w]["finish_from_t0_ms"] for w in range(4) if w in r["per_worker"]]
        say(f"{r['file']:<10}{r['provider'] + ':' + r['region']:<24}{_f(r['gbps'],3):>7}"
            + "".join(f"{_f(v,0):>8}" for v in fins)
            + f"{_f(r['finish_spread_ms'],1):>8}{_f(r['slowest_minus_second_slowest_ms'],1):>9}"
            f"{_f(r['first_finish_unstarted_bytes']/_MIB,1):>12}"
            f"{_f(r['second_finish_unstarted_bytes']/_MIB,1):>12}"
            f"{_f(r['tail_unstarted_bytes']/_MIB,1):>13}"
            f"{_f(r['remaining_inflight_ms'],1):>8}{r['tail_shape']:>26}")
    say()

    # ---- decision ---------------------------------------------------------
    def share(rows: list[dict[str, Any]], key: str, thr: float) -> str:
        n = sum(1 for r in rows if r.get(key) is not None and r[key] >= thr)
        return f"{n}/{len(rows)} ({100.0*n/len(rows):.0f}%)"

    say("=" * 110)
    say("DIRECT ANSWERS (hedged cohort)")
    say("=" * 110)
    spans = all_spans
    fs = [r["finish_spread_ms"] for r in hedged]
    s2 = [r["slowest_minus_second_slowest_ms"] for r in hedged]
    say(f"1.  median worker active span      : {_f(percentile(spans,50),1)} ms")
    say(f"2.  mean worker active span        : {_f(statistics.fmean(spans),1)} ms")
    say(f"3.  median finish spread           : {_f(percentile(fs,50),1)} ms")
    say(f"4.  mean finish spread             : {_f(statistics.fmean(fs),1)} ms")
    say(f"5.  p90/p95/worst finish spread    : {_f(percentile(fs,90),1)} / {_f(percentile(fs,95),1)} / {_f(max(fs),1)} ms")
    say(f"6.  median slowest-minus-2nd       : {_f(percentile(s2,50),1)} ms")
    say(f"7.  spread >=100 ms                : {share(hedged,'finish_spread_ms',100)}")
    say(f"8.  spread >=250 ms                : {share(hedged,'finish_spread_ms',250)}")
    say(f"9.  spread >=500 ms                : {share(hedged,'finish_spread_ms',500)}")
    say(f"10. spread >=1000 ms               : {share(hedged,'finish_spread_ms',1000)}")
    f1 = [r["first_finish_unstarted_bytes"] for r in hedged]
    f1p = [r["first_finish_unstarted_fraction"] for r in hedged if r["first_finish_unstarted_fraction"] is not None]
    f2 = [r["second_finish_unstarted_bytes"] for r in hedged]
    say(f"11. median 1st-finish unstarted    : {_f(percentile(f1,50)/_MIB,1)} MiB")
    say(f"12. median 1st-finish unstarted fr : {_f(percentile(f1p,50),4)}")
    say(f"13. median 2nd-finish unstarted    : {_f(percentile(f2,50)/_MIB,1)} MiB")
    tu = [r["tail_unstarted_reads"] for r in hedged]
    say(f"14. median tail unstarted reads    : {_f(percentile(tu,50),1)} reads")
    shapes: dict[str, int] = {}
    for r in hedged:
        shapes[r["tail_shape"]] = shapes.get(r["tail_shape"], 0) + 1
    say(f"15. tail shape counts              : {dict(sorted(shapes.items(), key=lambda kv:-kv[1]))}")
    big = [r for r in hedged if r["finish_spread_ms"] >= 250]
    if big:
        bs: dict[str, int] = {}
        for r in big:
            bs[r["tail_shape"]] = bs.get(r["tail_shape"], 0) + 1
        say(f"    in spread>=250 runs ({len(big)}): {dict(sorted(bs.items(), key=lambda kv:-kv[1]))}")
    say(f"16. stranded capacity median/p90   : {_f(percentile([r['total_stranded_worker_ms'] for r in hedged],50),1)} / "
        f"{_f(percentile([r['total_stranded_worker_ms'] for r in hedged],90),1)} ms "
        f"(fraction median {_f(percentile([r['stranded_capacity_fraction'] for r in hedged],50),4)})")
    lastcounts = [0, 0, 0, 0]
    for r in hedged:
        lastcounts[r["order"][-1]] += 1
    say(f"17. last-finisher counts by worker : {lastcounts}")
    say(f"18. worst_preadv vs spread pearson : {_f(_pearson([r['worst_preadv_ms'] for r in hedged], fs),3)}")
    say()

    # ---- hedge on/off side comparison ------------------------------------
    say("=" * 110)
    say("SIDE COMPARISON — hedging ON (250 ms) vs OFF  [hedge-off cohort is INVALID for the main result]")
    say("=" * 110)
    if hedged and unhedged:
        for label, rows in (("HEDGED 250ms", hedged), ("HEDGE OFF", unhedged)):
            g = [r["gbps"] for r in rows]
            say(f"  {label:<12} n={len(rows):>3}  median GB/s={_f(percentile(g,50),3)} "
                f"mean={_f(statistics.fmean(g),3)}  median wall={_f(percentile([r['wall_ms'] for r in rows],50),0)} ms  "
                f"median spread={_f(percentile([r['finish_spread_ms'] for r in rows],50),1)} ms  "
                f"median preadv={_f(percentile([r['lat_median'] for r in rows],50),2)} ms  "
                f"reads>=500={sum(r['ge500'] for r in rows)}")
        hg = [r["hedge_attempts"] for r in hedged if r["hedge_attempts"] is not None]
        hw = [r["hedge_wins"] for r in hedged if r["hedge_wins"] is not None]
        hb = [r["blocks_with_hedge"] for r in hedged if r["blocks_with_hedge"] is not None]
        if hg:
            say(f"  hedged: total hedge attempts={sum(hg)} wins={sum(hw)} "
                f"blocks hedged={sum(hb)} across {len(rows)} runs")
            say(f"          per run: median hedge attempts={_f(percentile(hg,50),1)} "
                f"median wins={_f(percentile(hw,50),1)}")
    say()

    (_ROOT / args.hedged_dir / "IMBALANCE.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows_out = []
    for r in hedged:
        row = {"file": r["file"], "provider": r["provider"], "region": r["region"],
               "gbps": r["gbps"], "wall_ms": r["wall_ms"],
               "finish_spread_ms": r["finish_spread_ms"],
               "slowest_minus_second_slowest_ms": r["slowest_minus_second_slowest_ms"],
               "total_stranded_worker_ms": r["total_stranded_worker_ms"],
               "stranded_capacity_fraction": r["stranded_capacity_fraction"],
               "first_finish_unstarted_bytes": r["first_finish_unstarted_bytes"],
               "second_finish_unstarted_bytes": r["second_finish_unstarted_bytes"],
               "tail_unstarted_reads": r["tail_unstarted_reads"],
               "tail_unstarted_bytes": r["tail_unstarted_bytes"],
               "remaining_inflight_ms": r["remaining_inflight_ms"],
               "tail_shape": r["tail_shape"], "worst_preadv_ms": r["worst_preadv_ms"]}
        for w in range(4):
            if w in r["per_worker"]:
                row[f"p{w}_finish_ms"] = r["per_worker"][w]["finish_from_t0_ms"]
                row[f"p{w}_span_ms"] = r["per_worker"][w]["active_span_ms"]
        rows_out.append(row)
    with (_ROOT / args.hedged_dir / "imbalance_per_run.csv").open("w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        wtr.writeheader()
        wtr.writerows(rows_out)
    print(f"\nwritten: IMBALANCE.txt, imbalance_per_run.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
