"""Q4 + Q5 from the frozen production-006 cohort (no new runs).

Q4: decompose source wall by QD occupancy, compute effective QD, and project
    throughput at perfect QD with per-copy speed held constant.
Q5: account for slot/H2D pressure on the source critical path.
"""
import csv, statistics, sys, collections

path = sys.argv[1]
rows = list(csv.DictReader(open(path, encoding="utf-8")))
print(f"cohort rows: {len(rows)}")

def f(r, k, d=0.0):
    v = r.get(k)
    if v in (None, "", "None"):
        return d
    try:
        return float(v)
    except ValueError:
        return d

by_role = collections.defaultdict(list)
for r in rows:
    by_role[r["role"]].append(r)

print("\n" + "=" * 78)
print("Q4  UTILISATION ACCOUNTING")
print("=" * 78)
for role, rs in sorted(by_role.items()):
    print(f"\n--- {role} (n={len(rs)}) ---")
    hdr = ("run", "src_wall_ms", "GB/s", "eff_conc", "tw_eff", "qd0", "qd1", "qd2",
           "qd3", "qd4", "frac_qd4", "pacer_zero", "slot_wait_ms", "cap_wait_ms",
           "rq_wait_ms")
    print("{:<30}{:>10}{:>8}{:>9}{:>8}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}{:>9}{:>11}{:>11}{:>9}"
          .format(*hdr))
    agg = collections.defaultdict(list)
    for r in sorted(rs, key=lambda x: x["run"]):
        wall = f(r, "source_wall_ms")
        qd = [f(r, f"time_at_qd{i}_ms") for i in range(5)]
        rec = dict(
            src_wall_ms=wall, gbps=f(r, "source_GBps"),
            eff_conc=f(r, "effective_reader_concurrency"),
            tw_eff=f(r, "time_weighted_effective_concurrency"),
            frac_qd4=f(r, "frac_time_at_qd4"),
            pacer_zero=f(r, "pacing_zero_delay_count"),
            slot_wait=f(r, "slot_wait_ms"), cap_wait=f(r, "capacity_wait_ms"),
            rq_wait=f(r, "ready_queue_wait_ms"),
        )
        vals = (r["run"][:30], wall, rec["gbps"], rec["eff_conc"], rec["tw_eff"],
                qd[0], qd[1], qd[2], qd[3], qd[4], rec["frac_qd4"],
                rec["pacer_zero"], rec["slot_wait"], rec["cap_wait"], rec["rq_wait"])
        print("{:<30}{:>10.1f}{:>8.2f}{:>9.2f}{:>8.2f}{:>9.1f}{:>9.1f}{:>9.1f}{:>9.1f}"
              "{:>9.1f}{:>9.3f}{:>9.0f}{:>11.1f}{:>11.1f}{:>9.1f}".format(*vals))
        for k in ("src_wall_ms", "gbps", "tw_eff", "frac_qd4", "slot_wait",
                  "cap_wait", "rq_wait", "pacer_zero"):
            agg[k].append(rec[k])
        for i in range(5):
            agg[f"qd{i}"].append(qd[i])
        agg["eff_conc"].append(rec["eff_conc"])

    med = {k: statistics.median(v) for k, v in agg.items() if v}
    qd_sum = sum(med[f"qd{i}"] for i in range(5))
    print(f"\n  MEDIANS: src_wall={med['src_wall_ms']:.0f}ms  GB/s={med['gbps']:.2f}  "
          f"time_weighted_eff_conc={med['tw_eff']:.3f}  frac_at_qd4={med['frac_qd4']:.3f}")
    print(f"  QD occupancy median ms: qd0={med['qd0']:.0f} qd1={med['qd1']:.0f} "
          f"qd2={med['qd2']:.0f} qd3={med['qd3']:.0f} qd4={med['qd4']:.0f}  sum={qd_sum:.0f}")
    print(f"  waits median ms: slot_wait={med['slot_wait']:.0f}  "
          f"capacity_wait={med['cap_wait']:.0f}  ready_queue_wait={med['rq_wait']:.0f}")
    print(f"  pacing_zero_delay_count median={med['pacer_zero']:.0f}")
    # Perfect-QD projection: scale the achieved rate by (4.0 / effective QD)
    eff = med["tw_eff"]
    if eff > 0:
        projected = med["gbps"] * (4.0 / eff)
        print(f"  => PERFECT-QD PROJECTION (speed held constant): "
              f"{med['gbps']:.2f} x (4.0/{eff:.3f}) = {projected:.2f} GB/s")
    # Sub-qd4 time recoverable
    below4 = med["qd0"] + med["qd1"] + med["qd2"] + med["qd3"]
    if qd_sum > 0:
        print(f"  => time below qd4 = {below4:.0f}ms of {qd_sum:.0f}ms "
              f"({100*below4/qd_sum:.1f}%)")

print("\n" + "=" * 78)
print("Q5  H2D / SLOT PRESSURE ON THE SOURCE CRITICAL PATH")
print("=" * 78)
for role, rs in sorted(by_role.items()):
    print(f"\n--- {role} (n={len(rs)}) ---")
    keys = ("source_wall_ms", "slot_wait_ms", "slot_wait_count",
            "all_slots_occupied_count", "capacity_wait_ms", "capacity_wait_count",
            "ready_queue_wait_ms", "gpu_copy_active_sum_ms",
            "h2d_event_completion_latency_ms", "final_drain_wall_ms",
            "dispatcher_reap_wall_ms", "below_four_reader_ms",
            "longest_zero_reader_ms", "min_source_gap_ms", "h2d_submitted_count")
    for k in keys:
        vals = [f(r, k) for r in rs]
        vals = [v for v in vals if v]
        if not vals:
            continue
        print(f"  {k:<34} n={len(vals)} p50={statistics.median(vals):.2f} "
              f"p90={sorted(vals)[int(0.9*(len(vals)-1))]:.2f} max={max(vals):.2f}")
    # exposed stall = waits that sit on the source critical path
    wall = statistics.median([f(r, "source_wall_ms") for r in rs if f(r, "source_wall_ms")])
    def med(k):
        vals = [f(r, k) for r in rs if f(r, k) is not None]
        return statistics.median(vals) if vals else 0.0
    slot = med("slot_wait_ms")
    cap = med("capacity_wait_ms")
    drain = med("final_drain_wall_ms")
    print(f"  => median source_wall={wall:.0f}ms  slot_wait={slot:.0f}ms  "
          f"capacity_wait={cap:.0f}ms  final_drain={drain:.1f}ms")
    exposed = slot + cap
    print(f"  => EXPOSED SOURCE STALL (slot+capacity, non-overlapping medians) "
          f"= {exposed:.0f}ms = {100*exposed/wall:.2f}% of source wall")