#!/usr/bin/env python
"""Wall gap vs PROCESS CPU-time delta, for the main heartbeat and the separate-PID canary.

process_time_ns() sums CPU time of ALL threads in the calling process, so:
  wall gap large + proc cpu delta ~= wall gap  => process was EXECUTING (a thread was burning CPU)
  wall gap large + proc cpu delta ~ 0          => process was not executing
The canary is a pure-userspace spin (no syscalls in steady state), so its wall gap
directly measures whether the container kept giving that process CPU.
"""
from __future__ import annotations
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _window_cpu(pairs, a, b):
    inside = [p for p in pairs if a <= p[0] <= b]
    if len(inside) < 2:
        return None
    return (inside[-1][1] - inside[0][1]) / 1e6


def main() -> int:
    for path in sorted((_ROOT / "sentinel_runs").glob("sn-r*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("status") != "ok":
            continue
        hb = r.get("heartbeat") or []
        cf = r.get("canary_fast") or []
        cc = r.get("canary_cpu") or []
        reads = r.get("reads") or []
        if not hb or not reads:
            continue
        t0 = min(x["preadv_enter_ns"] for x in reads)
        t_end = max(x["preadv_exit_ns"] for x in reads)
        print(f"\n{path.stem}  src_max={r['max_ms']:.0f}ms gbps={r['decimal_gbps']:.2f} "
              f"src_window=0..{(t_end-t0)/1e6:.0f}ms")

        hg = [(hb[i + 1][0] - hb[i][0], hb[i][0], hb[i + 1][0]) for i in range(len(hb) - 1)]
        hg.sort(reverse=True)
        print("  MAIN HEARTBEAT (whole process):")
        for wall, a, b in hg[:3]:
            cpud = (hb[[x[0] for x in hb].index(a) + 1][1] - hb[[x[0] for x in hb].index(a)][1]) / 1e6
            ratio = cpud / (wall / 1e6) if wall else 0
            print(f"    gap={wall/1e6:8.1f}ms at t={(a-t0)/1e6:7.0f}ms  proc_cpu_delta={cpud:8.1f}ms "
                  f"({ratio*100:5.1f}% of gap)  {'CPU-BUSY' if ratio > 0.5 else 'cpu~0'}")

        cg = [(cf[i + 1][0] - cf[i][0], cf[i][0], cf[i + 1][0]) for i in range(len(cf) - 1)]
        cg.sort(reverse=True)
        print("  SEPARATE-PID CANARY (pure userspace spin):")
        for wall, a, b in cg[:3]:
            can_cpu = _window_cpu(cc, a, b)
            ratio = (can_cpu / (wall / 1e6)) if (can_cpu is not None and wall) else None
            txt = "n/a" if ratio is None else f"{ratio*100:5.1f}% of gap"
            print(f"    gap={wall/1e6:8.2f}ms at t={(a-t0)/1e6:7.0f}ms  canary_cpu_delta="
                  f"{'n/a' if can_cpu is None else format(can_cpu, '8.1f')+'ms'}  ({txt})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
