#!/usr/bin/env python
"""Part A analysis: corrected per-worker-pool hedge (hedge_runs2)."""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "hedge_runs2"
ARMS = ["H75", "H150", "H250"]
FILE_BYTES = 8044982048
THR = [100, 150, 200, 250, 500, 1000]


def pctl(xs, p):
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
for p in sorted(D.glob("h2-*.json")):
    try:
        r = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        continue
    if r.get("status") != "ok" or not r.get("logical_records"):
        continue
    if "H100" not in str((r.get("identity") or {}).get("observed_gpu") or ""):
        continue
    arm = (r.get("_schedule") or {}).get("arm")
    if arm in runs:
        runs[arm].append(r)

print("=== runs per arm ===")
for a in ARMS:
    print(f"  {a}: {len(runs[a])}")

print("\n=== LOGICAL ACCEPTED LATENCY (from original T0) ===")
print(f"{'arm':>5}{'n':>6}{'best':>8}{'p10':>8}{'median':>8}{'mean':>8}{'p90':>8}"
      f"{'p95':>8}{'p99':>9}{'worst':>8}{'SD':>8}")
tot = {}
for a in ARMS:
    lg = [v for r in runs[a] for v in (r.get("logical_ms") or [])]
    tot[a] = lg
    if not lg:
        continue
    print(f"{a:>5}{len(lg):>6}{min(lg):>8.2f}{pctl(lg,10):>8.2f}{statistics.median(lg):>8.2f}"
          f"{statistics.fmean(lg):>8.2f}{pctl(lg,90):>8.2f}{pctl(lg,95):>8.2f}"
          f"{pctl(lg,99):>9.2f}{max(lg):>8.0f}{sd(lg):>8.2f}")

print("\n=== LOGICAL TAIL COUNTS ===")
print(f"{'arm':>5}" + "".join(f"{'>=%d'%t:>8}" for t in THR))
for a in ARMS:
    lg = tot[a]
    if not lg:
        continue
    print(f"{a:>5}" + "".join(f"{sum(1 for v in lg if v>=t):>8}" for t in THR))
    print(f"{'':>5}" + "".join(f"{100.0*sum(1 for v in lg if v>=t)/len(lg):>7.3f}%" for t in THR))

print("\n=== RUN PERFORMANCE ===")
print(f"{'arm':>5}{'wallMed':>9}{'wallMean':>10}{'wallBest':>10}{'wallWorst':>11}{'wallSD':>9}"
      f"{'gbpsMed':>9}{'gbpsMean':>10}{'gbpsBest':>10}{'gbpsWorst':>11}")
for a in ARMS:
    rs = runs[a]
    if not rs:
        continue
    walls = [r["full_file_wall_ms"] for r in rs]
    gb = [FILE_BYTES / (w / 1000.0) / 1e9 for w in walls]
    print(f"{a:>5}{statistics.median(walls):>9.0f}{statistics.fmean(walls):>10.0f}"
          f"{min(walls):>10.0f}{max(walls):>11.0f}{sd(walls):>9.0f}"
          f"{statistics.median(gb):>9.3f}{statistics.fmean(gb):>10.3f}"
          f"{max(gb):>10.3f}{min(gb):>11.3f}")

print("\n=== HEDGE ACTIVITY (VALIDITY) ===")
print(f"{'arm':>5}{'logical':>9}{'eligible':>10}{'launched':>10}{'SUPPRESSED':>12}"
      f"{'wins':>6}{'win%':>8}{'launch%':>9}{'amp':>8}")
for a in ARMS:
    rs = runs[a]
    lg = sum(len(r.get("logical_records") or []) for r in rs)
    el = sum((r.get("hedge") or {}).get("eligible", 0) for r in rs)
    ln = sum((r.get("hedge") or {}).get("launched", 0) for r in rs)
    sp = sum((r.get("hedge") or {}).get("suppressed_resource_busy", 0) for r in rs)
    wn = sum((r.get("hedge") or {}).get("rescue_wins", 0) for r in rs)
    amp = statistics.fmean([(r.get("hedge") or {}).get("amplification") or 1.0 for r in rs])
    print(f"{a:>5}{lg:>9}{el:>10}{ln:>10}{sp:>12}{wn:>6}"
          f"{(100.0*wn/ln if ln else 0):>7.1f}%{(100.0*ln/lg if lg else 0):>8.2f}%{amp:>8.4f}")

print("\n=== WIN EFFECT (time saved) ===")
for a in ARMS:
    rs = runs[a]
    sv = [x.get("time_saved_ms") for r in rs for x in (r.get("logical_records") or [])
          if x.get("time_saved_ms") is not None]
    ev = [(x.get("orig_exit_ns"), x.get("rescue_exit_ns"), x.get("t0_ns"))
          for r in rs for x in (r.get("logical_records") or []) if x.get("rescue_win")]
    cens = sum(1 for r in rs for x in (r.get("logical_records") or [])
               if x.get("rescue_win") and x.get("orig_censored"))
    if sv:
        print(f"  {a}: wins_with_observed_original={len(sv)} median={statistics.median(sv):.1f} ms "
              f"mean={statistics.fmean(sv):.1f} p95={pctl(sv,95):.1f} max={max(sv):.1f} "
              f"censored_originals={cens}")
    else:
        print(f"  {a}: no rescue wins with an observed original completion "
              f"(wins={len(ev)}, censored={cens})")

print("\n=== PACER CHECK (physical attempt start gaps) ===")
for a in ARMS:
    rs = runs[a]
    if not rs:
        continue
    mn = [r.get("min_attempt_gap_ms") for r in rs if r.get("min_attempt_gap_ms") is not None]
    md = [r.get("median_attempt_gap_ms") for r in rs if r.get("median_attempt_gap_ms") is not None]
    mx = [r.get("max_simultaneous_in_flight") for r in rs
          if r.get("max_simultaneous_in_flight") is not None]
    print(f"  {a}: min start-gap range={min(mn):.3f}-{max(mn):.3f} ms  "
          f"median start-gap median={statistics.median(md):.2f} ms  max_in_flight={max(mx)}")

print("\n=== PER-RUN (worst logical first) ===")
for a in ARMS:
    for r in sorted(runs[a], key=lambda x: -(x.get("logical_max_ms") or 0)):
        sc = r.get("_schedule") or {}
        hg = r.get("hedge") or {}
        lg = r.get("logical_ms") or []
        print(f"  {a:>5} ord{sc.get('ordinal'):>3} blk{sc.get('block')} wall={r['full_file_wall_ms']:>7.0f} "
              f"logMed={(statistics.median(lg) if lg else 0):>6.1f} logMax={r.get('logical_max_ms'):>7.0f} "
              f"l500={(r.get('logical_thresholds') or {}).get('ge_500',0):>2} "
              f"l1k={(r.get('logical_thresholds') or {}).get('ge_1000',0):>2} "
              f"elig={hg.get('eligible',0):>3} launch={hg.get('launched',0):>3} "
              f"supp={hg.get('suppressed_resource_busy',0):>2} wins={hg.get('rescue_wins',0):>2} "
              f"amp={hg.get('amplification'):.4f}")
