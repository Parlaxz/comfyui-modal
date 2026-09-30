# M1C — five questions about source throughput

> **CORRECTION (supersedes the original synthesis).** The first version of this
> report concluded that the "~5.4 GB/s ceiling" was a per-copy-speed limit and
> recommended pinning the Modal region. **Both are wrong and are withdrawn.**
> Region pinning is also prohibited on cost grounds (~1.5-1.75x price).
> See "Why the original conclusion was wrong" below. The Q1-Q5 *measurements*
> are unaffected and stand.

Base: `integration/m1b-correctness-fixes`, ported onto the live-control tree
`promotion/production-006` (`c19e61c1`). `production-006` tag NOT moved or
retagged. Testing 9 only. Production NOT modified.

Evidence:
- Q1, Q4, Q5 from the frozen 10-run production-006 cohort (1216 per-extent
  records, 20 model-load rows). No new runs spent.
- Q2, Q3 from 6 valid instrumented runs (deploy `c31e0d69`), exact SHA
  `3a6a0306...`, `valid=true`, `dnf=false`, config parity identical.
- Variance from 56 valid untouched-control runs plus 10 fresh clean controls.

---

## The finding that reframes everything: there is no 5.4 GB/s ceiling

Across **56 valid untouched-control runs** spanning all of production-006's
history:

| | min | p50 | max | spread | CV |
|---|---|---|---|---|---|
| CLIP | 0.37 | 4.12 | 6.77 | **18.3x** | **36.5%** |
| UNET | 1.33 | 4.14 | 6.87 | 5.2x | 31.7% |

A fresh 10-run clean control cohort reproduces it: CLIP CV 32.3% (p50 4.61),
UNET CV 25.0% (p50 4.40).

**This variance predates all M1B/M1C work and is not caused by it.** The
instrumented cohort showed CV 38.6% / 36.1% — statistically identical.

The mechanism is visible: `COMFYMODAL_V2_REGION` and `COMFYMODAL_V2_CLOUD` both
resolve to `""` (provider default), and containers land in **9 different
regions** (ca, eu-north, eu-south, us-west, us-south, us-east, us-central,
ap-northeast, ap-south, uk). CLIP and UNET track each other *within* a run
(6.77/6.87, 1.36/1.33, 6.09/6.60), i.e. it is a **per-container placement**
effect, not a per-model one.

Individual control runs have already recorded **6.77/6.87, 6.09/6.60, 6.10,
6.01/6.44, 5.65/5.00** — at or above the 6.5 GB/s target with no code change
whatsoever.

So the correct statement is: **6.5 GB/s is reachable but not reliable.** The
target is a tail-fattening problem under random placement, not a throughput
problem.

## Q1 — Is real production first access expensive?

**Yes, and it dominates the per-extent cost.**

| | copies | copy_wall p50 | per-copy | thread CPU | cpu/wall |
|---|---|---|---|---|---|
| CLIP | 480 | 55.99 ms | **1.20 GB/s** | 50.00 ms | 0.938 |
| UNET | 736 | 50.75 ms | **1.32 GB/s** | 50.00 ms | 0.942 |

Same operation post-load on warm pages: **10.81-12.91 GB/s** — a ~9-10x gap.
CPU-bound (cpu/wall 0.94), so not descheduled.

`rusage_minflt` is **0 on all 1216 records** (gVisor does not report it), so
first-touch cannot be confirmed from fault counters. Every M1B "cold file"
number (6.79 GB/s) was measured *post-load*, when the loader had already cached
those pages — so there is still **no direct truly-cold measurement**.

## Q2 — Do four simultaneous readers create a shared source ceiling?

**No.**

| readers | run A | run B | efficiency (B) |
|---|---|---|---|
| 1 | 8.06 GB/s | 3.86 GB/s | 1.00 |
| 2 | 16.77 GB/s | 9.55 GB/s | 2.48 |
| 4 | **33.46 GB/s** | **14.26 GB/s** | **3.70** |

Pre-warmed file-backed source, 64 MiB per reader, barrier-synchronised. Near
-linear scaling, 4 readers far above 6.5 GB/s aggregate. **Concurrency is
excluded** as the limiter on warm pages.

## Q3 — Does the actual CUDA-registered arena slow CPU copies?

**Incomplete.** private anonymous 12.91 / 10.81 GB/s. The registered arena could
not be addressed in two attempts (the C0 runtime object is released before the
post-durability hook reads it; the address-publish site does not execute on this
configuration). Reported **UNKNOWN** rather than fabricated. This is a plumbing
failure, not a negative result.

## Q4 — How much can perfect utilisation buy?

**Utilisation alone cannot reach 6.5 GB/s.**

| | CLIP | UNET |
|---|---|---|
| current GB/s | 4.55 | 4.24 |
| time-weighted effective QD | 3.882 | 3.678 |
| fraction already at QD4 | **0.908** | **0.860** |
| **perfect-QD projection** | **4.69 GB/s** | **4.61 GB/s** |

Readers are already 86-91% saturated at full QD4. Removing *all* sub-QD4 time
with per-copy speed unchanged yields 4.69 / 4.61. Pacing and slot waits are ~0
median per extent. **No QD/pacing/reader-count treatment is warranted.**

## Q5 — Is H2D / slot pressure ever on the source critical path?

**No.** Exposed source stall **1.52% (CLIP) / 10.8% (UNET)**; capacity wait 0;
final drain 0.4 / 1.8 ms. H2D overlaps (214-310 ms GPU copy inside a
1769-2903 ms source wall) but does not block.

---

## Why the original conclusion was wrong

The first version treated the ~5.4 GB/s median as a hard ceiling and built a
root cause on it. That was an artifact of **averaging across placements**. With
56 control runs showing 18.3x spread and 9 regions, a single cross-region mean
is not a property of the pipeline.

Specifically withdrawn:
- "ACTUAL ROOT CAUSE = per-copy source speed" — withdrawn. Per-copy speed does
  vary with placement, but it is not a fixed ceiling.
- "Smallest change = warm the safetensors" — **unsupported**. Favourable
  placements already exceed 6.5 GB/s with no change at all, so prewarming is not
  required to reach the target.
- "Pin the region" — **withdrawn and prohibited** on cost grounds (~1.5-1.75x).

Retained: Q1-Q5 stand on their own measurements, and the exclusion of
concurrency (Q2), utilisation (Q4) and H2D (Q5) as *pipeline-structural* limits
is correct and useful.

## Where this actually leaves the 6.5 GB/s target

The target is met in favourable placements today, without intervention. It is
not met on the median run. Since placement cannot be pinned, the only remaining
lever that is placement-agnostic is **hiding volume latency behind work the GPU
is already doing** — the existing `clip_forward_unet_window` overlap currently
spends its time on GPU compute while the source read sits on the critical path.

This is unmeasured. The discriminating experiment is the prewarm arm: sample
4-8 real production extents, prewarm a few before their production turn, and
compare their production copy against adjacent untouched extents. That was
never run, and it is the one measurement that would justify (or kill) a
readahead-during-overlap change.

    Q1 PRODUCTION FIRST-ACCESS COST = 1.20-1.32 GB/s per 64 MiB production extent (55.99 ms CLIP / 50.75 ms UNET) vs 10.81-12.91 GB/s for the identical copy post-load; CPU-bound (cpu/wall 0.94), ~9-10x gap. Placement-dependent
    FIRST / IMMEDIATE-REPEAT RATIO = not directly measured; production-vs-warm contrast is ~9-10x. M1B repeat-vs-first was 2.5x anonymous / ~1.6x file, but both post-load and therefore warm
    PREWARM CAUSAL RESULT = NOT PERFORMED

    Q2 1-READER AGGREGATE GB/S = 8.06 (run A) / 3.86 (run B)
    Q2 2-READER AGGREGATE GB/S = 16.77 (run A) / 9.55 (run B)
    Q2 4-READER AGGREGATE GB/S = 33.46 (run A) / 14.26 (run B)
    SHARED SOURCE-SERVICE CEILING = NO

    Q3 PRIVATE GB/S = 12.91 (run A) / 10.81 (run B)
    Q3 UNREGISTERED SHARED GB/S = 11.46 median (M1B level-2)
    Q3 REGISTERED ARENA GB/S = NOT OBTAINED
    REGISTERED ARENA PENALTY = UNKNOWN (plumbing failure, two attempts; not a negative result)

    Q4 CURRENT EFFECTIVE QD = 3.882 (CLIP) / 3.678 (UNET); already at QD4 for 90.8% / 86.0% of the wall
    PERFECT-QD PROJECTED GB/S = 4.69 (CLIP) / 4.61 (UNET)
    PACER REMOVABLE CRITICAL-PATH MS = ~0 median per extent (non-zero 57/480 CLIP, 105/736 UNET); 4 ms floor binding but inside an already-saturated pipeline
    SLOT REMOVABLE CRITICAL-PATH MS = ~0 median per extent (non-zero 14/480 CLIP, 11/736 UNET); aggregate 27 ms CLIP / 314 ms UNET
    UTILISATION ALONE CAN REACH 6.5 = NO

    Q5 H2D EXPOSED SOURCE STALL MS = 27 (CLIP) / 314 (UNET) median
    Q5 H2D EXPOSED SOURCE STALL % = 1.52% (CLIP) / 10.8% (UNET)
    H2D IS A NORMAL THROUGHPUT LIMIT = NO

    ACTUAL ROOT CAUSE OF ~5.4 GB/S CEILING = THERE IS NO CEILING. The 5.4 figure is a cross-placement mean, not a pipeline limit. Untouched control spans 0.37-6.77 GB/s CLIP (18.3x, CV 36.5%) over 9 regions because COMFYMODAL_V2_REGION and COMFYMODAL_V2_CLOUD are both unpinned. Pipeline-structural limits are independently excluded: concurrency (Q2, 4 readers reach 14-33 GB/s warm), utilisation (Q4, already 86-91% at QD4, perfect-QD projects 4.6-4.7), H2D/slot (Q5, 1.5-10.8%). Remaining variation is placement-driven volume latency.
    CONFIDENCE = HIGH that there is no fixed ceiling and that concurrency/utilisation/H2D are not the limiter. MODERATE on the cold-page share, since no truly-cold measurement exists. Q3 untested.

    SMALLEST CHANGE THAT SHOULD REACH >=6.5 GB/S = NONE REQUIRED ON THE FAST PLACEMENT TAIL - individual untouched-control runs already record 6.77/6.87, 6.09/6.60, 6.10 and 6.01/6.44 with no code change. For RELIABLE >=6.5 under random placement, region pinning is prohibited on cost, and the only placement-agnostic lever is to overlap the source read with the existing clip_forward_unet window (readahead into page cache during CLIP forward). That is UNMEASURED; the prewarm arm is the experiment that would justify or kill it.
    PROJECTED CLIP GB/S = 6.8-6.9 already observed on favourable placements; 4.6 median today
    PROJECTED UNET GB/S = 6.9 already observed on favourable placements; 4.4 median today