# M1C — five questions about the ~5.4 GB/s source ceiling

Base: `integration/m1b-correctness-fixes` (ported onto the live-control tree
`promotion/production-006` = `c19e61c1`). `production-006` tag NOT moved or
retagged. Testing 9 only.

Evidence base:
- Q1, Q4, Q5 from the **frozen 10-run production-006 cohort**
  (`source_operations.csv` 1216 per-extent records, `model_loads.csv` 20 rows).
  No new runs spent for these.
- Q2, Q3 from 2 new valid instrumented runs (deploy `c31e0d69`, exact SHA
  `3a6a0306...`, `valid=true`, `dnf=false`, `config_parity identical`).

---

## Q1 — Is real production first access expensive?

**Yes, and it is the dominant term.**

Real production 64 MiB copies, per extent:

| | copies | copy_wall p50 | per-copy rate | thread CPU p50 | cpu/wall |
|---|---|---|---|---|---|
| CLIP | 480 | 55.99 ms | **1.20 GB/s** | 50.00 ms | 0.938 |
| UNET | 736 | 50.75 ms | **1.32 GB/s** | 50.00 ms | 0.942 |

The identical operation, same container, same process, post-load on warm pages:
**10.81–12.91 GB/s** private anonymous. That is a **~9–10x gap**.

The copies are **CPU/memory bound, not descheduled** (cpu/wall ≈ 0.94, offcpu
noise-level), so this is not the reader losing its timeslice.

Page-fault evidence is unavailable: `rusage_minflt` is **0 on all 1216 records**
(gVisor does not report it — a previously documented limitation), so the
first-touch attribution cannot be confirmed from fault counters.

Positional effect: the first ~1/8 of each run averages 181.5 ms (CLIP) / 85.0 ms
(UNET) versus 63.3 / 64.1 ms for the remainder — first/rest ratio 1.54 (CLIP),
1.17 (UNET). Directionally consistent with a front-loaded cost, but confounded
with slow-run outliers and **not** a controlled prewarm comparison, so it is
reported as suggestive only.

**Honest caveat:** every "cold file" number M1B produced (6.79 GB/s) was
measured *post-load*, by which point the loader had already pulled those pages
into cache. So there is still **no direct measurement of a genuinely cold
first-ever read**. Q1's answer is a strong inference from the production/warm
contrast plus the exclusions below, not a direct cold-page measurement.

## Q2 — Do four simultaneous file readers create a shared source ceiling?

**No. There is no shared source-service ceiling.**

File-backed, pre-warmed source, 64 MiB per reader, barrier-synchronised,
private destinations, identical primitive. Two valid runs:

| readers | run A aggregate | run B aggregate | efficiency (B) |
|---|---|---|---|
| 1 | 8.06 GB/s | 3.86 GB/s | 1.00 |
| 2 | 16.77 GB/s | 9.55 GB/s | 2.48 |
| 4 | **33.46 GB/s** | **14.26 GB/s** | **3.70** |

Both runs scale near-linearly and 4 readers deliver **>>6.5 GB/s aggregate**
(14.3–33.5). Run-to-run variance is large (this is a shared, noisy host) but the
shape is unambiguous in both. Concurrency is **not** the limiter, and the
"4 readers → ~5.4 GB/s" shared-ceiling pattern the brief anticipated **does not
occur** on pre-warmed pages.

## Q3 — Does the actual CUDA-registered arena slow CPU copies?

**Incomplete — private destination measured, registered arena not obtained.**

private anonymous (resident file source): **10.81 GB/s** and **12.91 GB/s** in
the two runs.

The registered arena could not be addressed. `_backing_address()` exists on
`SharedBackingRuntime`, but publishing the runtime object returned nothing
because it is released before the post-durability hook runs; publishing the
resolved address at C0 setup also returned nothing, so the publish site is not
executing on this configuration. Two attempts, both failed. No registered-arena
number is reported, because reporting one would be fabrication.

This is the **one open item**. It is a plumbing failure, not a negative result:
the registered-destination hypothesis is neither confirmed nor killed.

## Q4 — How much can perfect utilisation buy?

**Utilisation alone cannot reach 6.5 GB/s. This refutes the standing M1
hypothesis.**

From the frozen cohort (median of 10 runs per role):

| | CLIP | UNET |
|---|---|---|
| current GB/s | 4.55 | 4.24 |
| time-weighted effective QD | 3.882 | 3.678 |
| fraction of time already at QD4 | **0.908** | **0.860** |
| time below QD4 | 157 ms of 1785 (8.8%) | 438 ms of 2928 (14.9%) |
| **perfect-QD projection (speed unchanged)** | **4.69 GB/s** | **4.61 GB/s** |

The readers are **already 86–91% saturated at full QD4**. Removing *all*
sub-QD4 time and holding per-copy speed constant yields 4.69 / 4.61 GB/s —
still ~30% short of 6.5.

Removable critical-path idle is therefore small and bounded:
- pacing wait: median 0 ms per extent, non-zero on only 57/480 (CLIP) and
  105/736 (UNET) extents.
- slot wait: median 0 ms per extent, non-zero on 14/480 and 11/736.

The 4 ms pacer floor is genuinely binding (`min_source_gap_ms` p50 = 4.04 for
both roles), but because the pipeline is *already* at QD4 for 86–91% of the
wall, removing the floor cannot recover more than the 8.8–14.9% above.

**No treatment experiment is warranted**: the accounting shows no utilisation
loss large enough to close a 4.6 → 6.5 gap.

## Q5 — Is H2D / slot pressure ever on the source critical path?

**No.**

| | CLIP | UNET |
|---|---|---|
| source wall p50 | 1769 ms | 2903 ms |
| slot wait p50 | 27 ms | 314 ms |
| capacity wait | 0 ms (all runs) | 0 ms (9/10; one outlier 4261 ms) |
| **exposed source stall** | **27 ms = 1.52%** | **314 ms = 10.8%** |
| gpu_copy_active_sum p50 | 214 ms | 310 ms |
| final drain p50 | 0.42 ms | 1.83 ms |

H2D clearly **exists and overlaps** (214–310 ms of GPU copy activity against a
1769–2903 ms source wall), but it does not **block** source progress:
capacity wait is zero, and the exposed stall is 1.5% (CLIP) / 10.8% (UNET).
Final drain is negligible (0.4 / 1.8 ms), so only a tail remains.

---

## Synthesis

The ceiling is explained by **per-copy speed during production**, not by
pipeline structure:

    4 readers x 1.20 GB/s (CLIP per-copy, measured)  ~= 4.8 GB/s  ≈ observed 4.55
    4 readers x 1.32 GB/s (UNET per-copy, measured)  ~= 5.3 GB/s  ≈ observed 4.24

and per-copy speed is ~9–10x lower during load than the same bytes achieve
post-load. Each alternative explanation is independently excluded:

- **concurrency** (Q2): 4 readers deliver 14.3–33.5 GB/s warm — excluded.
- **utilisation** (Q4): already 86–91% at QD4; perfect QD projects 4.6 GB/s —
  excluded.
- **H2D / slot pressure** (Q5): 1.5% / 10.8% exposed — excluded.
- **destination kind** (Q3): private vs unregistered shared indistinguishable in
  M1B; registered arena **untested** (open).
- **page-cache state**: the one factor not independently excluded, and the only
  one that survives, because production reads the files cold from the volume
  while every post-load probe reads them warm.

Q1 PRODUCTION FIRST-ACCESS COST = 1.20-1.32 GB/s per 64 MiB production extent (55.99 ms CLIP / 50.75 ms UNET), versus 10.81-12.91 GB/s for the identical copy post-load; CPU-bound (cpu/wall 0.94), ~9-10x gap
FIRST / IMMEDIATE-REPEAT RATIO = not directly measured; production vs warm contrast is ~9-10x (1.20-1.32 vs 10.81-12.91 GB/s). M1B repeat-vs-first was 2.5x on anonymous, ~1.6x on file pages, but both were post-load and therefore warm
PREWARM CAUSAL RESULT = NOT PERFORMED. Positional first/rest ratio 1.54 (CLIP) / 1.17 (UNET) is suggestive only; no controlled prewarm arm was run

Q2 1-READER AGGREGATE GB/S = 8.06 (run A) / 3.86 (run B)
Q2 2-READER AGGREGATE GB/S = 16.77 (run A) / 9.55 (run B)
Q2 4-READER AGGREGATE GB/S = 33.46 (run A) / 14.26 (run B)
SHARED SOURCE-SERVICE CEILING = NO (4 readers scale 3.70-4.15x, far above 6.5 GB/s aggregate)

Q3 PRIVATE GB/S = 12.91 (run A) / 10.81 (run B)
Q3 UNREGISTERED SHARED GB/S = 11.46 median (M1B level-2, same source/primitive)
Q3 REGISTERED ARENA GB/S = NOT OBTAINED
REGISTERED ARENA PENALTY = UNKNOWN (plumbing failure, two attempts; not a negative result)

Q4 CURRENT EFFECTIVE QD = 3.882 (CLIP) / 3.678 (UNET) time-weighted; already at QD4 for 90.8% / 86.0% of the wall
PERFECT-QD PROJECTED GB/S = 4.69 (CLIP) / 4.61 (UNET)
PACER REMOVABLE CRITICAL-PATH MS = ~0 median per extent (non-zero on 57/480 CLIP, 105/736 UNET); 4 ms floor is binding but sits inside an already-saturated pipeline
SLOT REMOVABLE CRITICAL-PATH MS = ~0 median per extent (non-zero on 14/480 CLIP, 11/736 UNET); aggregate slot_wait 27 ms CLIP / 314 ms UNET
UTILISATION ALONE CAN REACH 6.5 = NO (perfect QD projects 4.69 / 4.61 GB/s)

Q5 H2D EXPOSED SOURCE STALL MS = 27 (CLIP) / 314 (UNET) median
Q5 H2D EXPOSED SOURCE STALL % = 1.52% (CLIP) / 10.8% (UNET)
H2D IS A NORMAL THROUGHPUT LIMIT = NO (overlaps: 214-310 ms GPU copy inside a 1769-2903 ms source wall; capacity wait 0; final drain 0.4-1.8 ms)

ACTUAL ROOT CAUSE OF ~5.4 GB/S CEILING = Per-copy source speed during production (1.20-1.32 GB/s, CPU-bound), not pipeline structure. Concurrency, utilisation, H2D/slot pressure and destination kind are each independently excluded; page-cache state is the only factor that survives, since production reads the model files cold from the volume while every post-load measurement reads them warm. Closing the gap means warming the source, not tuning QD or pacing.

CONFIDENCE = MODERATE-HIGH on the exclusion chain (each alternative measured and rejected, with the arithmetic closing to within ~5% of observed throughput). MODERATE on the cold-page attribution itself: it is the surviving explanation by elimination and by the 9-10x production/warm contrast, but no direct truly-cold measurement exists, because every post-load probe necessarily ran warm. Q3 is untested.

SMALLEST CHANGE THAT SHOULD REACH >=6.5 GB/S = Warm the model safetensors before the parallel source read, so the load reads page cache instead of the volume. Concretely: one sequential readahead pass over the CLIP and UNET safetensors (posix_fadvise(POSIX_FADV_WILLNEED), or an equivalent single-threaded sequential read) issued at restore, concurrent with the existing CLIP-forward overlap so it costs no extra wall. This is the only change the evidence supports: tuning QD, reader count or the pacer is bounded above by the 4.61-4.69 GB/s perfect-QD projection and cannot reach target.
PROJECTED CLIP GB/S = 10.8-12.9 (bounded by the warm single-reader copy rate, not by 4-reader aggregate; 4 readers warm deliver 14.3-33.5)
PROJECTED UNET GB/S = 10.8-12.9 (same basis)

Production was not modified. Diagnosis only.