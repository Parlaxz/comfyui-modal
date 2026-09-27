# Pure CPU source I/O — mmap investigation (Steps 1–10)

Scope: **pure source I/O only**. No GPU, CUDA, H2D, `cudaHostRegister`, pinned staging, model
construction, ComfyUI execution, O_DIRECT, new QD, new block size, new pacing gap, sharding or
primers. CPU-only Modal functions where possible; the H100 wrapper is used only where placement
comparability with the frozen preadv cohort requires it, and the GPU is never touched.

Counting rule (fixed before collection): **US regions only**; a US region appearing **once** in an
arm is excluded from counted statistics. Excluded runs are retained with provider:region.

Raw artifacts: `step1_fio/`, `step2b_touch/`, `step2_touch/` (invalidated), `step3_m0m2/`,
`step5_zerocopy/`, `phase0_probe/`, `exp1_control_frozen/`. Reports: `step1_fio/STEP1_FIO_REPORT.md`,
`step2_report/STEP2_TOUCHER.md`, `step3_report/STEP3_4_M0_M2_PREADV.md`,
`step5_report/STEP5_6_ZEROCOPY.md`, `PHASE0_MMAP_CAPABILITY_AUDIT.md`,
`SOURCE_IO_EXPERIMENT_LEDGER.md`.

---

## 1. Does fio independently agree that mmap > pvsync/preadv-like reads?

**Yes — once region-stratified.** Counted (us-east only, the single eligible US region):

| engine | counted n | GB/s values | median |
|---|---:|---|---:|
| fio pvsync | 5 | 1.325, 1.178, 3.514, 4.230, 2.004 | **2.004** |
| fio mmap | 7 (first 5 used) | 3.043, 2.886, 3.212, 2.773, 2.835 | **2.967** |

mmap is ~48% faster within the matched region. **Important correction:** a region-blind first
reading of the first 10 runs suggested the *opposite* (pvsync 2.576 vs mmap 1.795). fio did not
record provider/region in that batch; once identity was captured and the rule applied, the
direction reversed. This is the same composition trap that earlier produced a false pacing effect.

## 2. Does a manual toucher help?

**No. It hurts, and the branch is closed.** `st_touch_pages` (native, one volatile load per page,
no Python loop, no copy, never calls preadv/read), one toucher thread per reader walking ahead in
its own lane. Interleaved `[0,1,2,2,1,0]`.

| arm | counted n | GB/s median | wall median | ops ≥250 | ≥500 | ≥1000 | READY_AHEAD |
|---|---:|---:|---:|---:|---:|---:|---:|
| T0 no toucher | 2 | **5.295** | **1521** | 0 | 0 | 0 | — |
| T1 1 block ahead | 5 | 3.568 (−32.6%) | 2255 (+48.3%) | 2 | 1 | 0 | **0** |
| T2 2 blocks ahead | 7 | 3.717 (−29.8%) | 2165 (+42.3%) | 26 | 9 | 1 | **0** |

**The mechanism is decisive: READY_AHEAD = 0 in both arms.** The consumer caught the toucher on
every one of 599 (T1) and 840 (T2) paired blocks. The toucher never once completed before the
consumer arrived, so it did not move work earlier — it added a *second concurrent source consumer
for the same bytes*. The toucher itself also went sick (T2 max **1045.5 ms**, 28 events ≥250 ms).

## 3. Is 1-block or 2-block lookahead better?

**Neither.** T1 −32.6% and T2 −29.8% median throughput; T2 has *worse* tails (26 ops ≥250 ms vs
T1's 2). T2 is the more damaging depth. No further depths were added, per instruction.

## 4. Does touching a page materially accelerate a subsequent full-block memcpy?

**Unanswerable from this data, and I will not infer it.** Because READY_AHEAD was 0, there is no
observation of "touch finished, then memcpy ran" to compare against a plain memcpy. The honest
statement is that the configuration never produced that case, so the question stays open.

## 5. Does M0 beat frozen preadv at n=30 eligible?

**No — it does not beat it, and the pooled comparison is region-confounded.**

| source | counted n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 persistent mmap | 32 | 5.419 | 5.267 | 4.030 | 6.490 | 7.407 | 3.437 | 1485 | 1585 |
| M2 exact-window mmap | 33 | 5.856 | 5.651 | 4.338 | 6.817 | 6.882 | 3.347 | 1374 | 1474 |
| preadv QD4/64/4ms (frozen) | 27 | 5.487 | 5.370 | 3.969 | 6.108 | 7.076 | 2.800 | 1466 | 1556 |

M0 is *slightly below* preadv on the pooled median (−1.2%); M2 is above (+6.7%). Within the
regions where both arms have counted runs:

| region | M0 n/med | M2 n/med | preadv n/med |
|---|---|---|---|
| us-ashburn-1 | 5/5.860 | 3/5.501 | 9/5.487 |
| us-central | 14/4.336 | 14/5.032 | 10/4.857 |
| us-west | 3/6.678 | 4/6.738 | 8/5.985 |

So mmap is ahead in us-west and us-ashburn-1, and M0 is behind in us-central. There is **no
consistent mmap throughput advantage at this sample size.**

## 6. Does M0 have fewer pathological source operations?

**Not demonstrated — and in matched regions both are equally clean.** Pooled:

| source | ops | median | p99 | worst | ≥250 | ≥500 | ≥1000 | ≥2000 | runs ≥250 | ≥500 | ≥1s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 | 3840 | 47.31 | 112.55 | 657.4 | 9 | 3 | 0 | 0 | 5/32 | 3/32 | 0/32 |
| M2 | 3960 | 43.10 | 124.05 | 1119.4 | 8 | 4 | 1 | 0 | 4/33 | 3/33 | 1/33 |
| preadv | 3240 | 46.58 | 121.66 | 220.5 | **0** | **0** | **0** | **0** | **0/27** | **0/27** | **0/27** |

Taken alone that looks like mmap being more tail-prone. **It is not established.** Every mmap
pathological operation sits in **GCP:us-east or GCP:us-east4** — regions where the preadv arm has
**zero counted runs**. In every *overlapping* region (us-central, us-west, us-ashburn-1) both mmap
and preadv show **0 tails**. Region composition cannot be excluded, so the tail difference is
**not attributable to the access mechanism** on this evidence.

One detail worth recording: M0's events repeatedly hit **block 90 (offset 6039797760)** across
four different runs (im-137, im-36, im-53, im-81). A repeated single-offset concentration is more
consistent with a specific slow backing region than with a random syscall-level effect, but this
is an observation, not a proven cause.

## 7. Does M2 remain worse or pathological?

**No — M2 is the best pooled arm and is not pathological.** Median 5.856 GB/s (best of the three),
wall median 1374 ms (lowest). It does carry the single worst operation (1119.4 ms) and the only
≥1 s run in the mmap arms, but those again sit in us-east/us-east4. M2's earlier "~6.4 s worst" did
not reproduce at this sample size; the worst observed here is 1119 ms.

**Measurement correction:** M2's operation cost is `map_ms + preadv_ms`. Counting only `preadv_ms`
made M2 appear to have an 8.82 ms median — a 5× illusion. Corrected, M2's median operation is
43.10 ms, comparable to M0 (47.31) and preadv (46.58). M2 is a **mapping-lifecycle variant**, not
an eagerly-populated mmap, because MAP_POPULATE is inert here.

## 8. Is M1 completely closed as inert?

**Yes.** Phase 0 proved `MADV_WILLNEED` is a functional no-op (cold first touch 24.7 ms vs 27.0 ms
with the advice issued first), while `MADV_POPULATE_READ/WRITE` and `readahead()` return EINVAL and
MAP_POPULATE does not materialize (64 MiB window mapped in 4.8 ms). M1 is therefore M0 plus an
inert syscall; no 30-run cohort was spent on it.

## 9. Can M0's memcpy be removed?

**Yes, mechanically — proven.** With `consume_mode != memcpy` there is no destination buffer and no
payload byte is copied:

| consume mode | payload_copy_bytes | per block | dest_allocated |
|---|---:|---:|---|
| M0 memcpy | 8044982048 | 67108864.0 | True |
| D0 / D1 / D2 | **0** | **0.0** | **False** |

Each logical block is represented as mapping + offset + length; the native consumer reads the
mapping directly.

## 10. How fast is direct full-byte mmap consumption?

| mode | counted n | GB/s median | mean | p10 | best | worst | wall median | eff concurrency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 memcpy | 12 | 5.621 | 5.384 | 4.264 | 6.870 | 2.688 | 1432 | 3.9155 |
| D0 `st_touch_pages` | 13 | 5.350 | 5.381 | 4.806 | 6.818 | 3.968 | 1504 | 3.9255 |
| D1 `st_touch_lines` | 14 | **5.935** | 5.718 | 4.683 | 7.811 | 4.377 | **1356** | 3.9040 |
| D2 `st_reduce_full` | 11 | 4.686 | 4.503 | 3.740 | 5.450 | 3.235 | 1717 | 3.9140 |

## 11. Is direct-consume mmap faster than mmap+memcpy?

**No.** The real full-byte consumer (D2) is **−16.6% median GB/s and +19.9% wall** versus M0
memcpy. The reason is CPU cost: `st_reduce_full` reads every byte through a volatile load, which is
far slower than an optimised `memcpy` (SIMD). The memcpy was never the bottleneck — it is cheap
relative to the source fetch — so replacing it with a slower consumer makes the wall worse.

D1 appears faster (5.935 / 1356) but **is not a legitimate drop-in consumer**: it touches one byte
per 64-byte cache line, i.e. reads 1/64 of the payload. It is a *cache-line materialization probe*,
not a full-byte consumer, and must not be presented as a faster equivalent of M0.

**Conclusion: keep the memcpy.** It is effectively free.

## 12. Does toucher + zero-copy improve further?

**Not tested.** Step 7's gate was that Step 2 must show T1 or T2 helps end-to-end. It did not — the
toucher hurt by ~30% — so per instruction Step 7 was skipped.

## 13. Which results survive provider:region stratification?

- **fio mmap > fio pvsync** — survives (single region, us-east).
- **Toucher hurts** — survives mechanistically (READY_AHEAD = 0 is region-independent).
- **M0 vs preadv throughput** — does **not** survive as a clean win; direction flips by region.
- **mmap tail-proneness** — does **not** survive; all mmap tails are in regions where preadv has no
  counted runs, and matched regions are equally clean.
- **D2 slower than M0 memcpy** — survives (CPU-bound, not placement-driven).

## 14. What is the fastest current PURE CPU source path?

By pooled counted median: **M2 exact-window mmap, 5.856 GB/s** (n=33), wall median 1374 ms.
By matched-region evidence it is not distinguishable from preadv, which is 5.487 pooled and ahead
in us-central. The honest answer is that **no pure-CPU source path is established as fastest**;
M2 and preadv are within noise of each other and both are region-dominated.

## 15. What is the most tail-resistant PURE CPU source path?

**preadv QD4 / 64 MiB / 4 ms** on this evidence: 0 operations ≥250 ms across 3240 counted
operations and 0/27 affected runs. That said, the mmap arms' tails all live in regions preadv never
sampled, so this is the strongest available answer rather than a proven mechanism difference.

## 16. Should mmap replace preadv as our source mechanism?

**No — not on this evidence.** M0 does not beat preadv on pooled throughput (−1.2%), does not win
consistently within matched regions, and the tail comparison is region-confounded. M2 is a
*mapping-lifecycle* variant whose only distinct feature (MAP_POPULATE) is inert here, so it offers
no mechanism advantage either. The memcpy that zero-copy removes is not a bottleneck. Recommendation:
**keep preadv as the primary source mechanism**; keep M0/M2 as candidates only if a future
matched-region cohort shows a real win.

## 17. What remains unresolved about the source pathology?

Evidence-bounded statements only:

1. **Can preadv originate sickness?** Yes — observed repeatedly (e.g. 5233 ms, 8783 ms primaries).
2. **Can mmap originate sickness?** Yes — independently, with no preadv in the path: first touch of
   a 64 MiB mapping took 1116 ms in one container and 61 ms in another.
3. **Does mmap originate it *less often*?** **Unknown.** The pooled counts differ but the
   comparison is region-confounded; matched regions are equally clean. This question needs a
   matched-region cohort to answer.
4. **Is the pathological fetch associated with source state shared by both mechanisms?** That is the
   most economical reading of the evidence: both mechanisms read the same bytes from the same
   backing store, and the same range becomes ~5–95× faster on second access (1116 ms → 11.7 ms;
   61 ms → 6.0 ms). A shared underlying fetch is consistent with every observation.
5. **Does rescue co-stall prove a shared mechanism?** **No.** It proves only that *once a fetch is
   already pathological, a later mmap access to the same logical data often cannot escape it*. It
   says nothing about origin probability, and it must not be used to argue that mmap-primary is
   equally tail-prone.
6. **What remains unknown below guest access?** Essentially everything below the guest syscall
   boundary: the page cache, the FUSE/VolumeFS layer, the host disk, and gVisor itself are all
   candidates, and this work does **not** identify which. The only mechanism-level fact established
   is that no advisory path exists in this runtime to move materialization earlier, so the fetch
   itself is the cost.

---

## CURRENT BEST SOURCE CONFIGS

| purpose | configuration |
|---|---|
| best preadv | 4 procs · QD4 · 64 MiB · 4 ms · self-service · persistent FD · static contiguous regions; counted median 5.487 GB/s, 0 ops ≥250 ms |
| best mmap memcpy (M0) | 4 procs · QD4 · 64 MiB · 4 ms · one persistent whole-file mapping per proc · cached base + cached native memcpy · preallocated destination; counted median 5.419 GB/s |
| best mmap zero-copy / direct-consume | **none recommended** — D2 full-byte consumer is −16.6% vs M0 memcpy; D1 is faster only because it reads 1 byte per cache line and is not a full consumer |
| best toucher configuration | **none** — toucher rejected (READY_AHEAD = 0; −30% throughput; +42–48% wall) |
| best independent fio result | `ioengine=mmap`, 4 independent jobs, bs=64m, non-overlapping quarters; us-east median 2.967 GB/s vs pvsync 2.004 GB/s |
| best tail distribution | preadv QD4/64/4 ms — 0 ops ≥250/500/1000/2000 ms in counted regions |

## Corrections made during this work

- An interim region-blind fio reading pointed the wrong way; capturing provider/region reversed it.
- The first toucher cohort was **invalid** — the toucher recorded 0 events due to an off-by-one, so
  its apparent "+16.8%" was not a toucher effect. Only after the fix does the true (negative)
  result appear.
- M2's operation cost was initially counted as copy-only, making it look ~5× faster than it is; the
  correct cost is `map_ms + preadv_ms`.
- M0's operation cost for window mode is not comparable to M0's without that correction.

No CUDA, GPU, H2D, O_DIRECT, new QD, new block size, new pacing gap, sharding or primers were used.
