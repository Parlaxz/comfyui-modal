#!/usr/bin/env python
"""Interim hedge analysis over completed runs (arm-level)."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "hedge_runs"
ARMS = ["C", "H75", "H125", "H200"]
FILE_BYTES = 8044982048


def pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (k - lo)


def sd(xs):
    return statistics.pstdev(xs) if len(xs) > 1 else 0.0


runs = {a: [] for a in ARMS}
for p in sorted(D.glob("hx-*.json")):
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if r.get("status") != "ok" or not r.get("logical_ms"):
        continue
    if "H100" not in str((r.get("identity") or {}).get("observed_gpu") or ""):
        continue
    sc = r.get("_schedule") or {}
    arm = sc.get("arm")
    if arm in runs:
        runs[arm].append(r)

print("=== INTERIM: completed runs per arm ===")
for a in ARMS:
    print(f"  {a:<5} {len(runs[a])}")

print("\n=== ARM SUMMARY (logical accepted reads) ===")
print(f"{'arm':>5}{'runs':>5}{'wall_med':>9}{'wall_mean':>10}{'wall_max':>10}"
      f"{'gbps_med':>9}{'gbps_mean':>10}{'log_med':>8}{'log_mean':>9}{'log_p95':>8}"
      f"{'log_p99':>9}{'log_max':>9}{'n500':>6}{'n1k':>5}{'r500':>5}{'r1k':>5}"
      f"{'hedges':>7}{'wins':>5}{'amp':>7}")
summary = {}
for a in ARMS:
    rs = runs[a]
    if not rs:
        continue
    pooled = [v for r in rs for v in (r.get("logical_ms") or [])]
    walls = [r["full_file_wall_ms"] for r in rs]
    gbps = [FILE_BYTES / (w / 1000.0) / 1e9 for w in walls]
    n500 = sum(1 for v in pooled if v >= 500)
    n1k = sum(1 for v in pooled if v >= 1000)
    r500 = sum(1 for r in rs if (r.get("logical_thresholds") or {}).get("ge_500", 0) > 0)
    r1k = sum(1 for r in rs if (r.get("logical_thresholds") or {}).get("ge_1000", 0) > 0)
    hedges = sum((r.get("hedge") or {}).get("launched", 0) for r in rs)
    wins = sum((r.get("hedge") or {}).get("rescue_wins", 0) for r in rs)
    amp = statistics.fmean([(r.get("hedge") or {}).get("amplification") or 1.0 for r in rs])
    summary[a] = dict(n=len(rs), pools=len(pooled), n500=n500, n1k=n1k, r500=r500,
                      r1k=r1k, hedges=hedges, wins=wins, amp=amp,
                      wall_med=statistics.median(walls), wall_mean=statistics.fmean(walls),
                      wall_max=max(walls), gbps_med=statistics.median(gbps),
                      gbps_mean=statistics.fmean(gbps),
                      log_med=statistics.median(pooled), log_mean=statistics.fmean(pooled),
                      log_p95=pct(pooled, 95), log_p99=pct(pooled, 99),
                      log_max=max(pooled), pooled=pooled, walls=walls, gbps=gbps)
    s = summary[a]
    print(f"{a:>5}{s['n']:>5}{s['wall_med']:>9.0f}{s['wall_mean']:>10.0f}{s['wall_max']:>10.0f}"
          f"{s['gbps_med']:>9.3f}{s['gbps_mean']:>10.3f}{s['log_med']:>8.1f}"
          f"{s['log_mean']:>9.1f}{s['log_p95']:>8.1f}{s['log_p99']:>9.1f}"
          f"{s['log_max']:>9.0f}{s['n500']:>6}{s['n1k']:>5}{s['r500']:>5}{s['r1k']:>5}"
          f"{s['hedges']:>7}{s['wins']:>5}{s['amp']:>7.4f}")

print("\n=== PER-RUN logical max, worst first, per arm ===")
for a in ARMS:
    rs = sorted(runs[a], key=lambda r: -(r.get("logical_max_ms") or 0))
    print(f"\n  [{a}]")
    for r in rs[:6]:
        sc = r.get("_schedule") or {}
        hg = r.get("hedge") or {}
        print(f"    ord{sc.get('ordinal'):>3} wall={r['full_file_wall_ms']:>8.0f}ms "
              f"logMax={r.get('logical_max_ms'):>7.0f} "
              f"l500={(r.get('logical_thresholds') or {}).get('ge_500',0):>2} "
              f"l1k={(r.get('logical_thresholds') or {}).get('ge_1000',0):>2} "
              f"hedges={hg.get('launched',0):>3} wins={hg.get('rescue_wins',0):>2} "
              f"amp={hg.get('amplification'):.4f} region={r.get('region')}")

print("\n=== HEDGE DETAIL (all arms with hedges) ===")
for a in ("H75", "H125", "H200"):
    rs = runs[a]
    h = sum((r.get("hedge") or {}).get("launched", 0) for r in rs)
    w = sum((r.get("hedge") or {}).get("rescue_wins", 0) for r in rs)
    lb = sum((r.get("hedge") or {}).get("lane_busy", 0) for r in rs)
    el = sum((r.get("hedge") or {}).get("eligible", 0) for r in rs)
    log = sum(len(r.get("logical_ms") or []) for r in rs)
    saved = [x.get("time_saved_ms") for r in rs for x in (r.get("logical_records") or [])
             if x.get("time_saved_ms") is not None]
    print(f"  {a}: logical={log} eligible={el} launched={h} lane_busy={lb} "
          f"wins={w} win_rate={(w/h if h else 0):.3f} launched%={(100*h/log if log else 0):.2f}%")
    if saved:
        print(f"       time_saved_ms: n={len(saved)} median={statistics.median(saved):.1f} "
              f"mean={statistics.fmean(saved):.1f} max={max(saved):.1f}")
    else:
        print("       time_saved_ms: (no rescue wins with observed original completion)")
