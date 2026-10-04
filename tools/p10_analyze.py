"""P10 2x2 factorial analysis: hoisted CUDA context preinit x arena slot depth.

Reads the per-run records collected by p10_collect.py and reports raw arm results,
main effects, and the interaction.  Medians are the primary statistic because
root wall in this deployment has a documented sick-container tail; means and
ranges are reported alongside so an outlier cannot hide.
"""

from __future__ import annotations

import json
import statistics as stats
from pathlib import Path

ART = Path("artifacts/p10_agent2")

ARMS = {
    "A": {"slots": 16, "preinit": 0},
    "B": {"slots": 16, "preinit": 1},
    "C": {"slots": 12, "preinit": 0},
    "D": {"slots": 12, "preinit": 1},
}

METRICS = [
    "register_ms",
    "arena_establish_wall_ms",
    "restore_total_ms",
    "root_wall_ms",
    "clip_load_wall_ms",
    "unet_load_wall_ms",
    "preinit_wall_ms",
    "preinit_join_wait_ms",
]


def load(arm: str) -> list[dict]:
    out = []
    for path in sorted(ART.glob(f"{arm}_*.json")):
        if "probe" in path.name:
            continue
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["_file"] = path.name
        out.append(rec)
    return out


def main() -> None:
    data = {arm: load(arm) for arm in ARMS}
    for arm, rows in data.items():
        print(f"\n===== ARM {arm}  slots={ARMS[arm]['slots']} "
              f"preinit={ARMS[arm]['preinit']}  n={len(rows)} =====")
        hdr = f"{'file':8} {'valid':5} {'cold':5} {'sha':4} {'cap':9} {'ver':4} {'reg':>8} {'est':>8} {'restore':>8} {'root':>8} {'clip':>7} {'unet':>7} {'pw':>7} {'join':>7} {'sw':>3} {'aso':>3}"
        print(hdr)
        for r in sorted(rows, key=lambda x: x["_file"]):
            armrec = r.get("experiment_arm") or {}
            def g(k):
                v = r.get(k)
                return f"{v:.1f}" if isinstance(v, (int, float)) else "-"
            print(f"{r['_file']:8} {str(r['valid']):5} {str(r['true_cold']):5} "
                  f"{str(r['output_sha_match']):4} {str(r['capture_classification']):9} "
                  f"{str(armrec.get('arm_verified')):4} "
                  f"{g('register_ms'):>8} {g('arena_establish_wall_ms'):>8} "
                  f"{g('restore_total_ms'):>8} {g('root_wall_ms'):>8} "
                  f"{g('clip_load_wall_ms'):>7} {g('unet_load_wall_ms'):>7} "
                  f"{g('preinit_wall_ms'):>7} {g('preinit_join_wait_ms'):>7} "
                  f"{str(r.get('slot_wait_count')):>3} {str(r.get('all_slots_occupied_count')):>3}")

    def usable(arm):
        return [r for r in data[arm]
                if r["valid"] and r["true_cold"] and r["output_sha_match"]
                and r["capture_classification"] == "ELIGIBLE" and r["capture_counted"]
                and not r.get("dnf") and not r.get("failures")]

    print("\n\n########## USABLE COUNTS ##########")
    for arm in ARMS:
        rows = usable(arm)
        shas = sorted({s for r in rows for s in (r.get("observed_output_shas") or [])})
        slots = sorted({r.get("slot_count") for r in rows})
        pre = sorted({(r.get("experiment_arm") or {}).get("observed_context_preinit") for r in rows})
        arms = sorted({(r.get("experiment_arm") or {}).get("declared_arm") for r in rows})
        print(f"  {arm}: {len(rows)}/{len(data[arm])}  slots={slots} preinit={pre} "
              f"arm={arms} sha={[s[:12] for s in shas]} "
              f"restore_count={sorted({r.get('restore_count') for r in rows})} "
              f"request_count={sorted({r.get('request_count') for r in rows})} "
              f"fallback={sorted({r.get('fallback_reason') for r in rows})} "
              f"fatal={sorted({r.get('fatal_failure') for r in rows})}")

    print("\n\n########## PER-ARM MEDIANS (usable only) ##########")
    med = {}
    for arm in ARMS:
        rows = usable(arm)
        med[arm] = {}
        for m in METRICS:
            vals = [r[m] for r in rows if isinstance(r.get(m), (int, float))]
            med[arm][m] = round(stats.median(vals), 4) if vals else None
        med[arm]["slot_wait_total"] = sum(r.get("slot_wait_count") or 0 for r in rows)
        med[arm]["all_slots_occupied_total"] = sum(r.get("all_slots_occupied_count") or 0 for r in rows)
        med[arm]["capacity_wait_total"] = sum(r.get("capacity_wait_count") or 0 for r in rows)

    keys = METRICS + ["slot_wait_total", "all_slots_occupied_total", "capacity_wait_total"]
    print(f"{'metric':28} {'A(16,off)':>12} {'B(16,on)':>12} {'C(12,off)':>12} {'D(12,on)':>12}")
    for k in keys:
        cells = []
        for arm in "ABCD":
            v = med[arm].get(k)
            cells.append(f"{v:.2f}" if isinstance(v, (int, float)) else "-")
        print(f"{k:28} {cells[0]:>12} {cells[1]:>12} {cells[2]:>12} {cells[3]:>12}")

    print("\n########## MEAN / MIN / MAX / RANGE (usable only) ##########")
    for m in ("register_ms", "arena_establish_wall_ms", "restore_total_ms", "root_wall_ms",
              "clip_load_wall_ms", "unet_load_wall_ms"):
        print(f"\n-- {m}")
        for arm in "ABCD":
            vals = [r[m] for r in usable(arm) if isinstance(r.get(m), (int, float))]
            if not vals:
                continue
            sd = stats.stdev(vals) if len(vals) > 1 else 0.0
            cv = (sd / stats.mean(vals) * 100) if stats.mean(vals) else 0.0
            print(f"   {arm}: n={len(vals)} mean={stats.mean(vals):9.2f} med={stats.median(vals):9.2f} "
                  f"min={min(vals):9.2f} max={max(vals):9.2f} range={max(vals)-min(vals):9.2f} "
                  f"sd={sd:8.2f} cv={cv:5.1f}%")

    print("\n\n########## 2x2 MAIN EFFECTS (median, positive = slower) ##########")
    def eff(x, y, m):
        a, b = med[x].get(m), med[y].get(m)
        if a is None or b is None:
            return None
        return round(b - a, 2)

    for m in ("register_ms", "arena_establish_wall_ms", "restore_total_ms", "root_wall_ms",
              "clip_load_wall_ms", "unet_load_wall_ms"):
        c16 = eff("A", "B", m)
        c12 = eff("C", "D", m)
        s_off = eff("A", "C", m)
        s_on = eff("B", "D", m)
        inter = None
        if None not in (c16, c12):
            inter = round(c12 - c16, 2)
        print(f"\n-- {m}")
        print(f"   context effect @16 slots (B-A) : {c16}")
        print(f"   context effect @12 slots (D-C) : {c12}")
        print(f"   12-slot effect, preinit OFF (C-A): {s_off}")
        print(f"   12-slot effect, preinit ON  (D-B): {s_on}")
        print(f"   INTERACTION (12ctx - 16ctx)    : {inter}")

    print("\n\n########## SLOT-CAPACITY GUARD ##########")
    for arm in "ABCD":
        rows = usable(arm)
        sw = [r.get("slot_wait_count") or 0 for r in rows]
        aso = [r.get("all_slots_occupied_count") or 0 for r in rows]
        cw = [r.get("capacity_wait_count") or 0 for r in rows]
        swm = [r.get("slot_wait_ms") or 0.0 for r in rows]
        print(f"  {arm}: slot_wait_count={sw} total={sum(sw)} | "
              f"all_slots_occupied={aso} total={sum(aso)} | "
              f"capacity_wait={cw} total={sum(cw)} | slot_wait_ms={swm} total={sum(swm):.2f}")

    Path("artifacts/p10_agent2/medians.json").write_text(
        json.dumps({"medians": med, "counts": {a: len(usable(a)) for a in ARMS}}, indent=1),
        encoding="utf-8",
    )
    print("\nwrote artifacts/p10_agent2/medians.json")


if __name__ == "__main__":
    main()