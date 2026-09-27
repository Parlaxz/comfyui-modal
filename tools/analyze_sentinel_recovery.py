#!/usr/bin/env python
"""Recovery-tail analysis + clean-run sentinel baselines.

For each source episode: bucket every sentinel sample by time since episode end and
report median/max scheduling delay and syscall latency per bucket.
"""
from __future__ import annotations
import json
import statistics
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
BUCKETS = [(0, 100), (100, 250), (250, 500), (500, 1000), (1000, 10 ** 9)]
STALL_MS = 250.0
NAMES = ("A_same_file", "B_other_volume_file", "C_tmpfs_local")


def _merge(reads, thr=STALL_MS):
    stalls = sorted((r for r in reads if r["preadv_ms"] >= thr),
                    key=lambda r: r["preadv_enter_ns"])
    eps = []
    for r in stalls:
        if eps and r["preadv_enter_ns"] <= eps[-1]["end"]:
            eps[-1]["end"] = max(eps[-1]["end"], r["preadv_exit_ns"])
            eps[-1]["reads"].append(r)
        else:
            eps.append({"start": r["preadv_enter_ns"], "end": r["preadv_exit_ns"],
                        "reads": [r]})
    for e in eps:
        e["worst_ms"] = max(r["preadv_ms"] for r in e["reads"])
    return eps


def main() -> int:
    print("=== CLEAN-RUN SENTINEL BASELINE (runs with no source episode >= 250 ms) ===")
    print("run | A sched med/max, lat med/max | B ... | C ...")
    for path in sorted((_ROOT / "sentinel_runs").glob("sn-r*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        if _merge(r["reads"]):
            continue
        parts = []
        for n in NAMES:
            s = (r.get("sentinels") or {}).get(n)
            if not s:
                parts.append("-")
                continue
            parts.append(f"{s['median_scheduling_delay_ms']:.2f}/{s['max_scheduling_delay_ms']:.1f}, "
                         f"{s['median_syscall_latency_ms']:.2f}/{s['max_syscall_latency_ms']:.2f}")
        print(f"| {path.stem} | " + " | ".join(parts) + " |")

    print("\n=== RECOVERY TAIL (samples after the end of each large episode) ===")
    print("run/eps | bucket(ms) | n | A sched med/max lat med/max | B | C")
    for path in sorted((_ROOT / "sentinel_runs").glob("sn-r*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        eps = [e for e in _merge(r["reads"]) if e["worst_ms"] >= 500.0]
        if not eps:
            continue
        sent = r.get("sentinels") or {}
        for ei, e in enumerate(eps):
            print(f"  {path.stem} EP#{ei} worst={e['worst_ms']:.0f}ms end="
                  f"{e['end']/1e6:.0f}")
            for lo, hi in BUCKETS:
                row = []
                total = 0
                for n in NAMES:
                    s = sent.get(n)
                    if not s:
                        row.append("-")
                        continue
                    sel = [(en, ex) for _t, en, ex, _g in s["records"]
                           if lo * 1e6 <= (en - e["end"]) < hi * 1e6]
                    if not sel:
                        row.append("-")
                        continue
                    total += len(sel)
                    sc = [(en - t) for (t, en, _ex) in
                          [(tt, ee, xx) for tt, ee, xx, _g in s["records"]
                           if lo * 1e6 <= (ee - e["end"]) < hi * 1e6]]
                    lat = [(ex - en) / 1e6 for en, ex in sel]
                    row.append(f"n={len(sel)} "
                               f"{statistics.median(lat):.2f}/{max(lat):.2f}")
                if total == 0:
                    continue
                label = f"{lo}-{hi}" if hi < 10 ** 9 else f">{lo}"
                print(f"      {label:>12s} | A {row[0]} | B {row[1]} | C {row[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
