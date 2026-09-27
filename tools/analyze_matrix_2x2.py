#!/usr/bin/env python
"""2x2 matrix in-episode analysis: what does each instrument do DURING a source stall?"""
from __future__ import annotations
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
STALL_MS = 250.0


def _gaps(recs, window):
    """max gap whose interval intersects window; also the gap's start"""
    best = (0.0, None)
    for i in range(len(recs) - 1):
        a, b = recs[i][0], recs[i + 1][0]
        if not (a < window[1] and b > window[0]):
            continue
        d = (b - a) / 1e6
        if d > best[0]:
            best = (d, a)
    return best


def _sys_stats(recs, window):
    """max scheduling delay and max syscall latency for ticks inside window"""
    sel = [r for r in recs if window[0] - 50e6 <= r[0] <= window[1] + 50e6]
    if not sel:
        return (None, None, 0)
    sch = max((r[1] - r[0]) / 1e6 for r in sel)
    lat = max((r[2] - r[1]) / 1e6 for r in sel)
    return (sch, lat, len(sel))


def _episodes(reads):
    st = sorted((r for r in reads if r["preadv_ms"] >= STALL_MS),
                key=lambda r: r["preadv_enter_ns"])
    eps = []
    for r in st:
        if eps and r["preadv_enter_ns"] <= eps[-1]["end"]:
            eps[-1]["end"] = max(eps[-1]["end"], r["preadv_exit_ns"])
            eps[-1]["reads"].append(r)
        else:
            eps.append({"start": r["preadv_enter_ns"], "end": r["preadv_exit_ns"],
                        "reads": [r]})
    for e in eps:
        e["worst"] = max(r["preadv_ms"] for r in e["reads"])
        e["workers"] = sorted({r["worker"] for r in e["reads"]})
    return eps


def main() -> int:
    pat = sys.argv[1] if len(sys.argv) > 1 else "mx-*.json"
    print("run | region | worst src | workers | py_hb | U_main | S_main sched/lat | "
          "U_child | S_child sched/lat | class")
    rows = []
    for p in sorted((_ROOT / "sentinel_runs").glob(pat)):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        eps = _episodes(r["reads"])
        if not eps:
            rows.append((p.stem, r, None))
            print(f"| {p.stem} | {r.get('provider')}/{r.get('region')} | {r['max_ms']:.0f} | "
                  f"- | - | - | - | - | - | CLEAN |")
            continue
        e = max(eps, key=lambda x: x["worst"])
        w = (e["start"], e["end"])
        hb, _ = _gaps(r.get("heartbeat") or [], w)
        um, _ = _gaps(r.get("native_records") or [], w)
        uc, _ = _gaps(r.get("u_child_records") or [], w)
        sm_s, sm_l, sm_n = _sys_stats(r.get("s_main_records") or [], w)
        sc_s, sc_l, sc_n = _sys_stats(r.get("s_child_records") or [], w)
        fmt = lambda v: "-" if v is None else f"{v:.1f}"
        if hb < 100:
            cls = "no python freeze"
        elif um < 20 and uc < 20 and sm_s is not None and sc_s is not None:
            if sm_s < 20 and sc_s < 20:
                cls = "CASE C (trivial syscalls healthy everywhere)"
            elif sm_s >= 50 and sc_s >= 50:
                cls = "CASE A (global syscall-path stall)"
            elif sm_s >= 50 and sc_s < 20:
                cls = "CASE B (main-PID scoped syscall stall)"
            else:
                cls = "mixed"
        else:
            cls = "instrument anomaly (CASE D?)"
        rows.append((p.stem, r, e))
        print(f"| {p.stem} | {r.get('provider')}/{r.get('region')} | {e['worst']:.0f} | "
              f"{e['workers']} | {fmt(hb)} | {fmt(um)} | {fmt(sm_s)}/{fmt(sm_l)} | "
              f"{fmt(uc)} | {fmt(sc_s)}/{fmt(sc_l)} | {cls} |")
        if sm_n or sc_n:
            print(f"      ticks in episode: S_main={sm_n} S_child={sc_n}")
    print()
    print("=== clock / syscall separation (whole-run) ===")
    for p in sorted((_ROOT / "sentinel_runs").glob(pat))[:4]:
        r = json.loads(p.read_text(encoding="utf-8"))
        nat = r.get("native") or {}
        if nat.get("mode") == "matrix_2x2":
            print(f"  {p.stem}: monotonic={nat.get('clock_monotonic_ns_per_call'):.1f} ns/call  "
                  f"{nat.get('syscall_name')}({nat.get('syscall_number')})="
                  f"{nat.get('clock_syscall_ns_per_call'):.1f} ns/call  "
                  f"ratio={nat.get('clock_syscall_ns_per_call')/nat.get('clock_monotonic_ns_per_call'):.0f}x")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
