#!/usr/bin/env python
"""Align every sentinel to the source episode on one monotonic timeline.

For each run: build source stall windows, then report what each instrument did
DURING those windows (not over the whole run, which includes the recovery tail).
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
STALL_MS = 250.0
NEAR_MS = 100.0


def _merge(reads, thr=STALL_MS):
    """Merge stall reads into time-overlapping episodes."""
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
        e["workers"] = sorted({r["worker"] for r in e["reads"]})
    return eps


def _gap_stats(pairs, window=None):
    """Max gap (and its start), optionally restricted to gaps intersecting window."""
    best = (0.0, None)
    for i in range(len(pairs) - 1):
        a, b = pairs[i][0], pairs[i + 1][0]
        if window and not (a < window[1] and b > window[0]):
            continue
        d = (b - a) / 1e6
        if d > best[0]:
            best = (d, a)
    return best


def _cpu_delta(pairs, t_a, t_b):
    """process CPU-time consumed between the two wall timestamps."""
    inside = [p for p in pairs if t_a <= p[0] <= t_b]
    if len(inside) < 2:
        return None
    return (inside[-1][1] - inside[0][1]) / 1e6


def analyse(path: Path, verbose: bool = True) -> dict[str, Any] | None:
    r = json.loads(path.read_text(encoding="utf-8"))
    if r.get("status") != "ok" or not r.get("reads"):
        return None
    reads = r["reads"]
    t0 = min(x["preadv_enter_ns"] for x in reads)
    t_end = max(x["preadv_exit_ns"] for x in reads)
    eps = _merge(reads)
    hb = r.get("heartbeat") or []
    cf = r.get("canary_fast") or []
    cc = r.get("canary_cpu") or []
    nat = r.get("native_records") or []
    sent = r.get("sentinels") or {}

    out = {
        "run": path.stem, "region": f"{r.get('provider')}/{r.get('region')}",
        "gbps": r.get("decimal_gbps"), "max_ms": r.get("max_ms"),
        "t0": t0, "t_end": t_end, "episodes": eps,
        "canary_mode": (r.get("canary") or {}).get("mode"),
    }

    if verbose:
        print(f"\n{'='*104}")
        print(f"{path.stem}  {out['region']}  gbps={r.get('decimal_gbps'):.2f} "
              f"src_max={r['max_ms']:.0f}ms  window=0..{(t_end-t0)/1e6:.0f}ms  "
              f"episodes={len(eps)}  canary={out['canary_mode']}")
        print(f"  whole-run: main_hb_max={(r.get('heartbeat_max_gap_ms') or 0):.1f}ms "
              f"canary_max={(r.get('canary_max_gap_ms') or 0):.2f}ms")

    for i, e in enumerate(eps):
        w = (e["start"], e["end"])
        hb_gap, hb_at = _gap_stats(hb, w)
        can_gap, can_at = _gap_stats(cf, w)
        nat_gap, nat_at = _gap_stats(nat, w)
        can_cpu = _cpu_delta(cc, w[0], w[1])
        dur = (e["end"] - e["start"]) / 1e6
        if verbose:
            print(f"  EPISODE#{i} t={(e['start']-t0)/1e6:.0f}..{(e['end']-t0)/1e6:.0f}ms "
                  f"dur={dur:.0f}ms worst={e['worst_ms']:.0f}ms workers={e['workers']}")
            print(f"     main_hb max_gap_in_episode={hb_gap:.1f}ms"
                  + (f" at t={(hb_at-t0)/1e6:.0f}ms" if hb_at else "")
                  + f"   SAME-PID-NATIVE max_gap_in_episode={nat_gap:.2f}ms"
                  + (f" at t={(nat_at-t0)/1e6:.0f}ms" if nat_at else "")
                  + f"   separate_pid max_gap_in_episode={can_gap:.2f}ms"
                  + (f" at t={(can_at-t0)/1e6:.0f}ms" if can_at else "")
                  + (f"   canary cpu_delta={can_cpu:.1f}ms" if can_cpu is not None else ""))
        e["hb_gap_in_ep"] = hb_gap
        e["native_gap_in_ep"] = nat_gap
        e["canary_gap_in_ep"] = can_gap
        e["canary_cpu_delta_in_ep"] = can_cpu
        for name, s in sorted(sent.items()):
            near = [(t, en, ex) for t, en, ex, _g in s["records"]
                    if en <= e["end"] + NEAR_MS * 1e6 and ex >= e["start"] - NEAR_MS * 1e6]
            if not near:
                e.setdefault("sentinels", {})[name] = None
                if verbose:
                    print(f"     {name:20s} no sample inside episode")
                continue
            sched = max((en - t) / 1e6 for t, en, _x in near)
            lat = max((ex - en) / 1e6 for _t, en, ex in near)
            e.setdefault("sentinels", {})[name] = {"sched_ms": sched, "lat_ms": lat,
                                                   "samples": len(near)}
            if verbose:
                print(f"     {name:20s} n={len(near):2d} max_sched_delay={sched:8.1f}ms "
                      f"max_syscall_latency={lat:7.2f}ms")
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="sn-r*.json")
    ap.add_argument("--dir", default=str(_ROOT / "sentinel_runs"))
    args = ap.parse_args()

    results = []
    for p in sorted(Path(args.dir).glob(args.glob)):
        got = analyse(p)
        if got:
            results.append(got)

    print(f"\n\n{'='*104}\nSUMMARY  ({len(results)} runs)")
    print("run | region | gbps | src_max | eps | worst_ep | py_hb_in_ep | SAME-PID_NATIVE_in_ep | "
          "sep-PID_in_ep | A sched/lat | B sched/lat | C sched/lat | class")
    for o in results:
        if not o["episodes"]:
            print(f"| {o['run']} | {o['region']} | {o['gbps']:.2f} | {o['max_ms']:.0f} | 0 | "
                  f"- | - | - | {(o['canary_mode'] or '-')} | - | - | - | CLEAN |")
            continue
        e = max(o["episodes"], key=lambda x: x["worst_ms"])
        def _s(name):
            v = (e.get("sentinels") or {}).get(name)
            return "-" if not v else f"{v['sched_ms']:.0f}/{v['lat_ms']:.1f}"
        hb_gap = e["hb_gap_in_ep"]
        nat_gap = e["native_gap_in_ep"]
        can_gap = e["canary_gap_in_ep"]
        sents = {n: (e.get("sentinels") or {}).get(n) for n in
                 ("A_same_file", "B_other_volume_file", "C_tmpfs_local")}
        blocked = [n for n, v in sents.items() if v and v["sched_ms"] >= 50]
        native_moves = nat_gap < 20.0
        can_moves = can_gap < 20.0
        if not can_moves:
            cls = "CASE 3 (all three freeze)"
        elif hb_gap >= 100 and native_moves:
            if len(blocked) == 3:
                cls = "CASE 1 (python/GIL domain; all fs paths freeze)"
            elif len(blocked) == 0:
                cls = "CASE 1 + F (python freeze, sentinels healthy)"
            else:
                cls = "CASE 1 (python/GIL domain, partial fs)"
        elif hb_gap >= 100 and not native_moves:
            cls = "CASE 2 (whole PID/thread-group)"
        elif hb_gap < 100 and not native_moves:
            cls = "CASE 2 (native-only freeze)"
        else:
            cls = "CASE 4 / unclear (python did not freeze)"
        print(f"| {o['run']} | {o['region']} | {o['gbps']:.2f} | {o['max_ms']:.0f} | "
              f"{len(o['episodes'])} | {e['worst_ms']:.0f} | {hb_gap:.0f} | {nat_gap:.2f} | "
              f"{can_gap:.2f} | "
              f"{_s('A_same_file')} | {_s('B_other_volume_file')} | {_s('C_tmpfs_local')} | {cls} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
