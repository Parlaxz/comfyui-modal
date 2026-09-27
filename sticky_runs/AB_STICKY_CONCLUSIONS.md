# Sticky-lane allocator — conclusions + Step 1 rescue reconstruction

Tables: `sticky_runs/AB_STICKY.md`.

## STEP 1 — the ≥1000 ms same-block rescue events

Exactly **one** original read ≥1000 ms exists in the allocator QD4 @64 cohort:

**`im-26.json`, block 63, gcp:us-east**

| field | value |
|---|---|
| original duration | **5233.2 ms** (reader 1) |
| 250 ms threshold | +250.0 ms |
| duplicate enter | **+259.2 ms** (reader 0) |
| duplicate duration | **4975.4 ms** |
| duplicate exit | +5234.6 ms |
| original exit | +5233.2 ms |
| **exit delta (dup − orig)** | **+1.3 ms** |
| logical winner | **primary** |
| other QD reads completed during the overlap | **37** (median 36.8 ms, max 59.2 ms) |

Answers to your specific questions:

- **Did the duplicate enter while the original was still blocked?** **Yes** — at +259.2 ms, i.e. **4974.0 ms before** the original exited.
- **How long before the original's exit did it enter?** **4974.0 ms.**
- **Did duplicate and original still exit essentially together?** **Yes — within 1.3 ms** of each other, out of a 5.2 s read.
- **While both were blocked, were the other QD readers continuing to complete normal reads?** **Yes — 37 reads**, median 36.8 ms, max 59.2 ms.

**Called out as requested:** the duplicate entered promptly (259 ms, right at the threshold) and ran **fully concurrently for 4.97 seconds**, yet still exited **1.3 ms after** the original. Meanwhile the other three readers were completely healthy, completing 37 normal reads inside that window.

So the stall is **local to that one read/block** — not resource-wide — but a same-block duplicate cannot escape it. Both attempts were released together. That is the cleanest demonstration in this whole series that same-block duplication does not decouple, even when launch timing and concurrency are perfect.

## STEP 2 — sticky-lane allocator A/B

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 30 | **6.015** | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | **1337** | 1408 |
| sticky-lane allocator QD4 | 30 | **5.294** | 4.745 | 2.933 | 6.221 | 7.152 | 0.494 | **1520** | 2706 |

**Sticky median delta vs static: −0.721 GB/s (−12.0%).**

| arm | preadv median | p95 | p99 | worst | ≥250 | ≥500 | ≥1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| static | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| sticky | 43.89 | 59.81 | 81.39 | 8585.0 | 30 | 23 | 18 |

Scheduler: lanes `[30,30,30,30]` · **affinity breaks 108** · lane-finish reassignments 108 · rescue launches 24 · **rescue wins 17** · savings median 0.10 / max 9.91 ms · amplification 1.0000/1.0667 · **max QD 4** · min spacing **4.0030 ms** · idle-no-work 13917 ms · stale duplicates 23.

Within provider: gcp 6.058 (n=23) → 5.642 (n=8); oci 5.293 (n=5) → 5.045 (n=6).

## Answers

**1. Does preserving four contiguous streams restore the static ~6 GB/s? — No. −12.0% (5.294 vs 6.015).** Essentially identical to the interleaved allocator's −11.7%.

**2. Was the ~13% regression caused by the interleaved/strided access pattern? — No. This is disproved.**

| allocator variant | access pattern | median GB/s | delta vs static |
|---|---|---:|---:|
| interleaved (global queue) | stride-4 blocks, 256 MiB apart | 5.310 | −11.7% |
| **sticky lanes (contiguous)** | **contiguous per lane, identical to static** | **5.294** | **−12.0%** |

Making the physical offset pattern contiguous changed the result by **−0.3%**. **My locality hypothesis was wrong**, and I'm retracting it. The penalty is common to both allocator variants, so it is caused by something the two share — not by the block ordering.

**3. Does sticky scheduling have effectively zero healthy-path cost? — No, ~12%.** But the composition is informative: sticky's per-read latency is only **+4.5%** (43.89 vs 41.99) versus interleaved's +10.8%, while its wall penalty is slightly *worse* (+13.7% vs +13.3%). Accounting for the wall:

| arm | reads × median latency ÷ 4 | observed wall | unaccounted |
|---|---:|---:|---:|
| static | 1260 ms | 1337 ms | 77 ms |
| sticky | 1317 ms | 1520 ms | **203 ms** |

So sticky pays less per read but more in scheduling overhead (~203 ms vs 77 ms), which is why the totals match. That points at the **dispatch path**, not the data path.

**Leading remaining hypothesis (untested): the coordinator round-trip between reads.** Static readers issue their next read immediately in a tight internal loop. Allocator readers must *wait for a task* from the parent before each read and *report back* after it — 2 IPC operations per read, 120 reads, with the parent polling on a 0.5 ms sleep. That inserts the coordinator's responsiveness into every reader's critical path, and it is common to both allocator variants, which fits the evidence. The metric that would confirm it (`allocator_latency_ms`, free→sent) is recorded in every run but I did not surface it in this report — that is the first thing to check.

**4. When a lane genuinely falls behind, does the allocator redistribute useful work? — Yes.** 108 affinity breaks across 30 runs (3.6/run), and two runs show substantial redistribution: `[43,32,32,13]` and `[42,26,31,21]`. So lane-finish reassignment does engage when one lane lags. Note that in the healthy majority the split is `[30,30,30,30]` (6 runs exactly, most within ±1) — i.e. there is nothing to rebalance when all readers are equal.

**5. What happened in the ≥1 s same-block rescue events? — See Step 1.** One event, and the duplicate entered at the threshold, ran concurrently for 4.97 s, and still lost by 1.3 ms while the rest of the system stayed healthy.

## Summary of what is now established

| claim | status |
|---|---|
| same-block duplication can decouple a stall | **disproved** (Step 1: duplicate ran 4.97 s concurrently, exited 1.3 ms after original) |
| the stall is resource-wide | **disproved** (37 other reads completed inside the overlap) |
| the allocator regression is caused by strided/interleaved access | **disproved** (sticky contiguous lanes: −12.0% vs interleaved −11.7%) |
| the allocator costs ~12% regardless of ordering | **established** (two independent variants, matched geometry) |
| allocator cost is per-read latency | **partly** — interleaved yes (+10.8%), sticky only +4.5%; sticky pays ~203 ms in dispatch overhead instead |
| coordinator IPC round-trip is the cause | **untested hypothesis** |

## Caveats

- Sticky provider mix differs from control (gcp 8 vs 23, plus 2 aws, and more `unspecified`), so the pooled medians are not perfectly matched; within-GCP the penalty persists (−6.9%).
- 34 valid sticky runs collected; the first 30 by slot were used (no performance selection).
- 11 odin runs retained and excluded.
- No further architecture was added, per instruction.
