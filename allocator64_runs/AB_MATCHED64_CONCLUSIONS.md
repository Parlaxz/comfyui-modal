# Scheduler-only A/B at matched 64 MiB — conclusions

Tables: `allocator64_runs/AB_MATCHED64.md` (main A/B, latency, scheduler summary, within-provider, per-run rows for both allocator arms, frozen control table).

## Headline

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 30 | **6.015** | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | **1337** | 1408 |
| allocator QD4 @64 | 30 | **5.310** | 4.999 | 3.343 | 6.071 | 6.494 | 1.197 | **1515** | 1884 |
| allocator QD8 @64 | 30 | **4.865** | 5.187 | 4.516 | 6.133 | 7.088 | 4.242 | **1654** | 1579 |

- allocator QD4 @64: **−11.7%** median vs static
- allocator QD8 @64: **−19.1%** median vs static

| arm | preadv median | p95 | p99 | worst | >=250ms | >=500ms | >=1000ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| allocator QD4 @64 | 46.52 | 56.42 | 63.91 | 5233.2 | 20 | 2 | 2 |
| allocator QD8 @64 | 104.24 | 127.07 | 131.48 | 291.9 | 4 | 0 | 0 |

Scheduler: QD4 → 15 rescue-eligible, 15 launches, **7 wins**, saved 0.27 ms median / 0.89 max, amplification 1.0000/1.1000, **max QD 4**, min spacing **4.0019 ms**, idle-no-work 3609 ms, 14 stale duplicates. QD8 → 6 eligible, 6 launches, 2 wins, saved 0.11/0.12 ms, amplification 1.0000/1.0500, **max QD 8**, min spacing **4.0157 ms**, idle-no-work 4842 ms.

Within provider (median GB/s): gcp static 6.058 (n=23) / q4 5.543 (n=17) / q8 4.860 (n=25). The allocator is slower inside GCP too, so this is not composition.

## Answers

**1. At identical 64 MiB, faster/slower/equal? — Slower: −11.7% median (QD4).** Wall median 1515 vs 1337 ms (+13.3%). Not a wash.

**2. Measurable healthy-path scheduler/IPC overhead? — Yes, ~11%.** At the *same* block size, median per-read latency is 46.52 ms vs 41.99 ms (+10.8%), and that fully accounts for the wall difference (46.52 × 120 / 4 = 1396 ms vs 41.99 × 120 / 4 = 1260 ms). Since the syscall is timed around `preadv` alone, this is a real change in read service time caused by the scheduler.

**Leading hypothesis (not proven): destroyed read locality.** Static partitioning gives each reader a contiguous ~2 GB region — reader *i* walks blocks 30i…30i+29 sequentially. The allocator hands out blocks in global order, so reader *i* walks blocks *i, i+4, i+8, …* — a 256 MiB stride. If the FUSE/VolumeFS path benefits from sequential access (readahead, block-cache adjacency), striding would inflate per-read latency by roughly this amount. This is testable cheaply (allocate contiguous *chunks* to readers instead of interleaved blocks) and would distinguish locality from IPC overhead.

**3. Does dynamic allocation reduce finish imbalance or idle tail? — No.** Blocks-per-reader came out `[30,30,30,30]` in 18/30 QD4 runs and `[15×8]` in 13/30 QD8 runs — i.e. perfectly even, so no rebalancing occurred at all. Idle-no-work was substantial (3609 ms QD4, 4842 ms QD8 across the cohort). The "fast readers do more work" mechanism never engaged because no reader was materially faster.

**4. Did a genuine pathological read occur, and was it rescued at QD4? — Yes, and yes — but the rescue was worth almost nothing.** QD4 had 2 reads ≥500 ms and 2 ≥1000 ms (worst **5233 ms**). 15 rescue-eligible blocks, 15 launches, **7 wins**, max physical QD held at **4**, amplification ≤1.10. So the mechanism is functional and the invariant holds. But **ms saved per win was 0.27 ms median, 0.89 ms max** — the rescues won by a hair, which is the same near-tie signature seen in every previous hedging attempt.

**5. Does the previous ~12–14% regression disappear once block size is matched? — No, and this corrects my earlier conclusion.**

| arm | wall median |
|---|---:|
| static 64 MiB | 1337 ms |
| allocator 128 MiB | 1518 ms (+13.5%) |
| allocator 64 MiB | 1515 ms (+13.3%) |

Matching the block size changed the allocator's wall by **3 ms**. So the penalty is **~13% at both geometries** — it is the **scheduler**, not the block size.

**My previous report was wrong.** I attributed the whole deficit to block size via a read-count × latency decomposition, and that decomposition happened to match. It was a coincidence: the 128 MiB arm did half the reads at ~2.28× the latency, and the 64 MiB arm does double the reads at ~1.11× the latency — both land near 1515 ms. The block size is not the cause; the scheduler costs ~13% regardless.

## Caveats

- QD8 arm: you asked for 20, I collected 30 valid non-Odin.
- Control is the same frozen 30 witness-engine runs as before (static QD4, 64 MiB, no hedge/allocator). They carry canary instrumentation the allocator arms lack.
- Odin runs retained separately and excluded from all counts (15 QD4, 15 QD8).
- The locality hypothesis in (2) is a hypothesis, not a measurement.
- Rescue is now exercised (7 wins QD4) but the saving is negligible, consistent with all prior same-path duplication results.
