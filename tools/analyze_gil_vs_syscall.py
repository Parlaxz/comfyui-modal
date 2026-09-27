#!/usr/bin/env python
"""GIL-vs-syscall discriminator.

If a thread held the GIL for hundreds of ms, then a worker returning from
os.preadv could not run Python loop bookkeeping until it reacquired the GIL,
so its refill_gap (next preadv enter - previous preadv exit) would be large.

If the GIL was free, refill_gap stays tiny and the entire stall is inside the
preadv syscall itself.
"""
from __future__ import annotations
import json
import statistics
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("LARGE EPISODES: where is the time spent?\n")
    for path in sorted((_ROOT / "sentinel_runs").glob("ncr-*.json")):
        r = json.loads(path.read_text(encoding="utf-8"))
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        reads = r["reads"]
        worst = max(x["preadv_ms"] for x in reads)
        if worst < 500.0:
            continue
        t0 = min(x["preadv_enter_ns"] for x in reads)
        print(f"{path.stem} worst={worst:.0f}ms gbps={r['decimal_gbps']:.2f} "
              f"native_max_gap={r.get('native_max_gap_ms')} "
              f"hb_max_gap={r.get('heartbeat_max_gap_ms')}")
        for w in sorted({x["worker"] for x in reads}):
            wr = [x for x in reads if x["worker"] == w]
            sick = [x for x in wr if x["preadv_ms"] >= 250.0]
            gaps = [x["refill_gap_ms"] for x in wr if x["refill_gap_ms"] is not None]
            gaps_sick = [x["refill_gap_ms"] for x in sick if x["refill_gap_ms"] is not None]
            print(f"   w{w}: n={len(wr):3d} sick_reads={len(sick):2d} "
                  f"max_preadv={max(x['preadv_ms'] for x in wr):7.1f}ms  "
                  f"refill_gap med={statistics.median(gaps):.3f}ms max={max(gaps):.3f}ms  "
                  f"| refill_gap right after a sick read: "
                  f"{'none' if not gaps_sick else f'med={statistics.median(gaps_sick):.3f} max={max(gaps_sick):.3f}ms'}")
        # the single most informative number: refill gap immediately following the worst read
        wrst = max(reads, key=lambda x: x["preadv_ms"])
        nxt = [x for x in reads if x["worker"] == wrst["worker"]
               and x["preadv_enter_ns"] >= wrst["preadv_exit_ns"]]
        if nxt:
            nx = min(nxt, key=lambda x: x["preadv_enter_ns"])
            print(f"   -> after worst read (w{wrst['worker']} {wrst['preadv_ms']:.0f}ms), "
                  f"next preadv entered {nx['refill_gap_ms']:.3f}ms later")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
