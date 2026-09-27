# Hedge audit — 107-run corpus (`imbalance_hedged_runs`), no new runs

## 1. The latency statistic was two different populations

My analyzer's core-stats block built its "preadv" line from `lat = [r["lat_median"] …]` — **per-run medians** — while the `≥250/≥500/≥1000` counts on the next line were computed from **individual reads**. Two populations under one label.

| | **A: pooled individual logical reads** | **B: per-run median read latency** |
|---|---|---|
| n | **12,840** (107 runs × 120 blocks) | **107** (one per run) |
| min | 17.36 ms | 32.21 ms |
| p10 / p25 | 36.27 / — | — |
| median | 43.26 ms | 42.93 ms |
| mean | 47.99 ms | 44.92 ms |
| p90 / p95 | 59.57 / 68.39 ms | — / 57.30 ms |
| p99 | 102.88 ms | (78.52 ms reported) |
| **max** | **2993.82 ms** | **89.18 ms** |
| SD | 46.27 ms | — |
| ≥250 ms | **35** | n/a |
| ≥500 ms | **15** | n/a |
| ≥1000 ms | **7** | n/a |

**Every value in the report's "preadv median / mean / p95 / p99 / worst" line is Population B.** The `≥250/≥500/≥1000` counts are Population A.

**Correction:** the reported "pooled preadv worst = 89.18 ms" was the worst *per-run median*, not the worst read. The true pooled worst individual read is **2993.82 ms — understated by ~33×**. Corrected line:

```
Pooled individual logical reads (n=12,840):
  min=17.36 p10=36.27 median=43.26 mean=47.99 p90=59.57 p95=68.39 p99=102.88
  max=2993.82 SD=46.27   |   >=250: 35   >=500: 15   >=1000: 7

Per-run median read latency (n=107):
  min=32.21 median=42.93 mean=44.92 p95=57.30 max=89.18
Per-run mean read latency max = 135.64 ms
Per-run worst single read max = 2993.82 ms
```

This also means the report's baseline comparison was apples-to-oranges: it set Population-B cohort stats (median 42.93) against Population-A baseline stats (median 41.76, worst 2176.5). The like-for-like pooled comparison is **43.26 vs 41.76 ms median**, and the like-for-like worst is **2993.82 vs 2176.5 ms** — i.e. the hedged cohort's worst tail was *worse* than baseline, not better.

## 2. Hedge implementation trace

### What the attempts per block are

`_mw_hedge_child`, per block: **1 original + 3 hedge attempts = up to 4 physical attempts.**

| attempt | FD | buffer | thread |
|---|---|---|---|
| `original` | worker's persistent `fd` (`os.open(file_path, O_RDONLY)`) | worker's single 64 MiB `view` | 1 thread, started immediately |
| `hedge` ×3 | `hedge_fds[i]` — a **separate `os.open` of the same path** | `hedge_views[i]` — separate 64 MiB buffer | 3 threads, started only after `done.wait(250 ms)` times out |

108 hedges / 36 blocks = **exactly 3.0** — every hedged block fired all three slots.

### Same-path duplicate, or fresh resource island?

**Same-path duplicate resources, in the same process, on the same inode.** All four attempts open the *same path*, so under `directfs` they resolve to the **same per-inode host `readFD`** and the same VolumeFS/FUSE client. Different userspace FD numbers and different buffers do not create a different resource.

The historical ROTATE4 architecture was different in kind: its docstring says *"a 150 ms crossing hedges one successor to the next **pristine resource island**"*, with the geometry rule `logical_qd < resources_per_worker`. That is failover to a **different resource** (different volume/host path), not a duplicate read of the same inode.

**→ This is not the architecture that historically removed our worst tails.** It is a same-path duplicate-read hedge.

### Why 35/36 hedged blocks were not rescued

The timeline shows the hedges **never overlapped their originals**:

| quantity | median | max |
|---|---:|---:|
| original `preadv` duration | 466.02 ms | 2993.82 ms |
| hedge `preadv` duration | 22.93 ms | 42.45 ms |
| original enter → first hedge **enter** | 466.3 ms | 2997.1 ms |
| original enter → hedge **claim** | 491.5 ms | 3037.8 ms |
| hedge gate wait | 0.01 ms | 3.40 ms |
| hedge enter − hedge claim | 0.016 ms | 0.062 ms |
| **original exit − hedge exit** | **−23.8 ms** | +0.3 ms |

The hedge's claim lands at **~466 ms — the moment the original finishes** (original duration 466.02 ms), not at the configured 250 ms. Once claimed it enters `preadv` in 0.016 ms and completes in 23 ms, so it exits ~24 ms *after* the original and loses.

- The pacer gate is **not** the cause (gate wait 0.01 ms).
- The delay is **before** `_mw_gate_launch`: the hedge thread's first Python instruction does not run until ~466 ms, i.e. ~216 ms after the 250 ms timer fires.
- The pattern is *systematic*, not random: delay ≈ original duration in every block, including a 2993.8 ms original whose hedge still entered at 2997.1 ms. Three seconds of idle process time was not enough for the hedge thread to start, which is hard to explain by mere thread starvation.

**Open question (not resolvable from this corpus):** whether the hedge threads were blocked on something held across the original's read, or were starved by the child's thread scheduling under gVisor/systrap. The engine records **no thread-start timestamp**, so these cannot be separated. That single field would settle it.

**Consequence for interpretation:** because the hedges never ran concurrently with their originals, **this corpus does not test whether same-path hedging helps.** It only shows that this implementation's hedges never raced. The 1 win (hn-089 block 34) saved **0.31 ms**.

### Did it remove the worst tails?

**No.** In the 107-run hedged cohort: max pooled read **2993.82 ms**, 7 reads ≥1000 ms, 15 ≥500 ms. The unhedged QD4 baseline had 1 read ≥1000 ms. The hedged cohort's tail is not improved.

## 3. Bottom line

| question | answer |
|---|---|
| What are the 3 attempts per block? | 3 hedge duplicates of the same block, each with its own FD + 64 MiB buffer, as threads in the same reader process (plus the 1 original) |
| Same-path duplicate or fresh island failover? | **Same-path duplicate**, same process, same inode — **not** a resource-island failover |
| Why 35/36 not rescued? | The hedge thread does not reach the pacer until ~the original's completion, so it starts after the original already finished; it exits ~24 ms later and loses |
| Is this the architecture that historically removed our worst tails? | **No** — different resource model, and in this corpus the hedges never even ran concurrently |
| Does this corpus prove same-path hedging is useless? | **No** — it shows the hedges never raced, which is an implementation/scheduling defect, not a test of the hypothesis |
