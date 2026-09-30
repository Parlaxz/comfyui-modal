"""Q1 from the frozen production per-extent records (real production copies)."""
import csv, statistics, sys, collections

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
print(f"per-extent production records: {len(rows)}")
N = 67108864

def f(r, k, d=0.0):
    v = r.get(k)
    try:
        return float(v)
    except (TypeError, ValueError):
        return d

by_role = collections.defaultdict(list)
for r in rows:
    by_role[r["role"]].append(r)

for role, rs in sorted(by_role.items()):
    print("\n" + "=" * 74)
    print(f"Q1  {role.upper()}  n={len(rs)} real production 64 MiB copies")
    print("=" * 74)
    walls = [f(r, "copy_wall_ns") for r in rs]
    cpus = [f(r, "copy_thread_cpu_ns") for r in rs]
    minf = [f(r, "rusage_minflt") for r in rs]
    print(f"  copy_wall_ns   p50={statistics.median(walls)/1e6:.2f}ms "
          f"p90={sorted(walls)[int(.9*(len(walls)-1))]/1e6:.2f}ms max={max(walls)/1e6:.2f}ms")
    print(f"  per-copy rate  p50={N/(statistics.median(walls)/1e9)/1e9:.2f} GB/s "
          f"(min={N/(max(walls)/1e9)/1e9:.2f} max={N/(min(walls)/1e9)/1e9:.2f})")
    print(f"  thread CPU ns  p50={statistics.median(cpus)/1e6:.2f}ms")
    ratios = [f(r, "cpu_wall_ratio") for r in rs if f(r, "cpu_wall_ratio")]
    print(f"  cpu/wall ratio p50={statistics.median(ratios):.3f} "
          f"(~1.0 => CPU/memory bound, not descheduled)")
    print(f"  rusage_minflt  p50={statistics.median(minf):.0f} max={max(minf):.0f} "
          f"total={sum(minf):.0f}")
    # correlation wall vs minor faults
    pairs = [(f(r, "rusage_minflt"), f(r, "copy_wall_ns")) for r in rs]
    pairs = [(a, b) for a, b in pairs if a or b]
    if len(pairs) > 2:
        xs = [a for a, _ in pairs]; ys = [b for _, b in pairs]
        n = len(xs); mx = sum(xs)/n; my = sum(ys)/n
        num = sum((x-mx)*(y-my) for x, y in pairs)
        den = (sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys)) ** 0.5
        corr = num/den if den else 0.0
        print(f"  corr(minflt, copy_wall) = {corr:+.3f}  (n={n})")
    # ordinal position effect: are the first extents of a run slower?
    byrun = collections.defaultdict(list)
    for r in rs:
        byrun[r["receipt"]].append(r)
    firsts, mids, ratio_all = [], [], []
    for _rc, grp in byrun.items():
        grp.sort(key=lambda x: int(f(x, "ordinal")))
        w = [f(x, "copy_wall_ns") for x in grp]
        if len(w) < 8:
            continue
        k = max(2, len(w)//8)
        firsts += w[:k]; mids += w[k:]
        ratio_all.append(statistics.mean(w[:k]) / statistics.mean(w[k:]))
    if firsts and mids:
        print(f"  first ~1/8 of each run  mean={statistics.mean(firsts)/1e6:.2f}ms")
        print(f"  remaining extents      mean={statistics.mean(mids)/1e6:.2f}ms")
        print(f"  first/rest ratio        median={statistics.median(ratio_all):.3f} "
              f"(~1.0 => no positional warming effect)")
    # pacing / slot waits
    pw = [f(r, "pacing_wait_ns") for r in rs]
    sw = [f(r, "slot_wait_ns") for r in rs]
    print(f"  pacing_wait_ns p50={statistics.median(pw)/1e6:.2f}ms  "
          f"nonzero={sum(1 for x in pw if x)}/{len(pw)}")
    print(f"  slot_wait_ns  p50={statistics.median(sw)/1e6:.2f}ms  "
          f"nonzero={sum(1 for x in sw if x)}/{len(sw)}")
    ec = [f(r, "effective_concurrency") for r in rs]
    print(f"  effective_concurrency p50={statistics.median(ec):.2f} "
          f"max={max(ec):.0f}")

print("\n" + "=" * 74)
print("REFERENCE: M1B post-load single-copy, WARM pages, NO concurrency")
print("  file-resident 64 MiB memmove : 11.41 GB/s (median of 3 valid runs)")
print("  cold file-backed first touch:  6.79 GB/s")
print("  anonymous control           : 14.12 GB/s")
print("=" * 74)