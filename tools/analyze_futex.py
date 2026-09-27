#!/usr/bin/env python
"""Bounded-futex campaign analysis: does the identical futex wake late, and where?"""
from __future__ import annotations
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
STALL = 250.0


def _gaps(recs, w):
    best = (0.0, None)
    for i in range(len(recs) - 1):
        a, b = recs[i][0], recs[i + 1][0]
        if not (a < w[1] and b > w[0]):
            continue
        d = (b - a) / 1e6
        if d > best[0]:
            best = (d, a)
    return best


def _fut(recs, w):
    """(max_excess, max_blocking, n, worst_record) for ticks whose ENTER is in w"""
    sel = [r for r in recs if w[0] - 50e6 <= r[1] <= w[1] + 50e6]
    if not sel:
        return (None, None, 0, None)
    ex = [((r[2] - r[1]) - r[5]) / 1e6 for r in sel]
    bl = [(r[2] - r[1]) / 1e6 for r in sel]
    k = max(range(len(sel)), key=lambda i: ex[i])
    return (max(ex), max(bl), len(sel), sel[k])


def _sys(recs, w):
    sel = [r for r in recs if w[0] - 50e6 <= r[0] <= w[1] + 50e6]
    if not sel:
        return (None, 0)
    return (max((r[2] - r[1]) / 1e6 for r in sel), len(sel))


def _eps(reads):
    st = sorted((r for r in reads if r["preadv_ms"] >= STALL), key=lambda r: r["preadv_enter_ns"])
    out = []
    for r in st:
        if out and r["preadv_enter_ns"] <= out[-1]["end"]:
            out[-1]["end"] = max(out[-1]["end"], r["preadv_exit_ns"])
            out[-1]["reads"].append(r)
        else:
            out.append({"start": r["preadv_enter_ns"], "end": r["preadv_exit_ns"], "reads": [r]})
    for e in out:
        e["worst"] = max(r["preadv_ms"] for r in e["reads"])
        e["workers"] = sorted({r["worker"] for r in e["reads"]})
    return out


def main() -> int:
    pat = sys.argv[1] if len(sys.argv) > 1 else "fx-[0-9][0-9].json"
    print("run | region | worst src | workers | py_hb | S_main lat | B_MAIN excess | "
          "S_child lat | B_CHILD excess | class")
    late_without_source = []
    source_without_late = []
    for p in sorted((_ROOT / "sentinel_runs").glob(pat)):
        r = json.loads(p.read_text(encoding="utf-8"))
        if r.get("status") != "ok" or not r.get("reads"):
            continue
        eps = _eps(r["reads"])
        bm = r.get("b_main_stats") or {}
        bc = r.get("b_child_stats") or {}
        if not eps:
            # clean source run: is there any late futex anywhere?
            if (bm.get("max_excess_ms") or 0) > 100:
                late_without_source.append((p.stem, bm.get("max_excess_ms")))
            print(f"| {p.stem} | {r.get('provider')}/{r.get('region')} | {r['max_ms']:.0f} | "
                  f"- | - | - | whole-run {bm.get('max_excess_ms')} | - | "
                  f"whole-run {bc.get('max_excess_ms')} | CLEAN |")
            continue
        e = max(eps, key=lambda x: x["worst"])
        w = (e["start"], e["end"])
        hb, _ = _gaps(r.get("heartbeat") or [], w)
        sm, _ = _sys(r.get("s_main_records") or [], w)
        sc, _ = _sys(r.get("s_child_records") or [], w)
        bme, bmb, bmn, bmw = _fut(r.get("b_main_records") or [], w)
        bce, bcb, bcn, bcw = _fut(r.get("b_child_records") or [], w)
        f = lambda v: "-" if v is None else f"{v:.0f}"
        if bme is None or bce is None:
            cls = "no futex ticks in episode"
        elif bme > 100 and bce <= 100:
            cls = "CASE 2 (futex late in MAIN pid only)"
        elif bme > 100 and bce > 100:
            cls = "CASE 1 (futex late in BOTH pids)"
        else:
            cls = "CASE 3 (futex healthy in both)"
        if (bme or 0) > 100 and e["worst"] < 500:
            pass
        if e["worst"] >= 500 and (bme or 0) <= 100:
            source_without_late.append((p.stem, e["worst"], bme))
        print(f"| {p.stem} | {r.get('provider')}/{r.get('region')} | {e['worst']:.0f} | "
              f"{e['workers']} | {f(hb)} | {f(sm)} | {f(bme)} | {f(sc)} | {f(bce)} | {cls} |")
        if bmw:
            print(f"      B_MAIN worst tick: enter={bmw[1]/1e6:.0f} blocking={((bmw[2]-bmw[1])/1e6):.0f}ms "
                  f"expected_wake=+{bmw[5]/1e6:.1f}ms actual_exit={bmw[2]/1e6:.0f}ms "
                  f"retval={bmw[3]} errno={bmw[4]} ticks={bmn}")
        if bcw:
            print(f"      B_CHILD worst tick: enter={bcw[1]/1e6:.0f} blocking={((bcw[2]-bcw[1])/1e6):.0f}ms "
                  f"expected_wake=+{bcw[5]/1e6:.1f}ms actual_exit={bcw[2]/1e6:.0f}ms "
                  f"retval={bcw[3]} errno={bcw[4]} ticks={bcn}")
    print()
    print("=== separability ===")
    print(f"late futex (>100ms) in a CLEAN source run: {late_without_source or 'none'}")
    print(f"large source episode (>=500ms) with healthy futex: {source_without_late or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
