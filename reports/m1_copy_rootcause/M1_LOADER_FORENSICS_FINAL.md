# M1 LOADER FORENSICS — FINAL REPORT

Data-oriented. Every claim is tagged with an evidence class. No persuasive
narrative, no recommendations outside §47-48.

**Evidence classes:** `DIRECT MEASUREMENT` · `CODE-PROVEN` · `DERIVED` ·
`CORRELATION` · `SUPPORTED INFERENCE` · `UNKNOWN / UNRESOLVED` ·
`UNAVAILABLE UNDER gVisor`.

---

## 1. Exact production-006 identity

`CODE-PROVEN`

| field | value |
|---|---|
| tag | `production-006` (annotated) |
| commit | `42cf4d048a8dbc66535753a857cc5cd99135f074` |
| cohort runtime commit | `5d41f742f42eb2fbddc3bbfa5641fe01dd35faa6` |
| tag vs cohort delta | documentation only (`git diff 5d41f742 42cf4d0` = 1 file, `PRODUCTION_006_BASELINE.md`) |
| deployment fingerprint | `1b0e49ead74200733c5e91dc2f0d662c8c8361299204807f225d9f3ec54a71d3` |
| profile | `golden_p1_parallel_c0_source_h100` |
| app / method | `batch-c0-source-h100` / `run_golden_parallel_stream` |
| GPU / CPU / memory | `H100!` / 12 / 24576 MiB |
| expected output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |
| destination | Testing 9, `ws_ee7221847f7d` |
| clean cohort | 10 runs, all `valid=true`, `dnf=false`, `true_cold=true`, SHA match 10/10 |

The tag was not moved. Note the `promotion/production-006` worktree branch is 4
commits *ahead* of the tag; those commits are post-request teardown/telemetry
only and do not touch the load path. The tag is the reference used here.

## 2. Exact diagnostic identities

`CODE-PROVEN`

| field | value |
|---|---|
| worktree | `.slim/worktrees/m1-loader-forensics`, branch `diag/m1-loader-forensics` |
| base | tag `42cf4d0` (byte-identical runtime tree) |
| diagnostic profile | `golden_p1_parallel_c0_source_h100_m1_l1` |
| diagnostic app | `batch-c0-source-h100-m1` (production anchor never mutated) |
| destination | Testing 9, `ws_ee7221847f7d` — config-owned via `config/v2/modal_target.toml` |
| final deploy fingerprint | `de9efc4660718a33fdc3cfa2144e9b9426e950c06f65573490241e43078ca6aa` |
| source probe | PASS / MATCH, 16/16 modules incl. instrumented `golden_source_threads.py` |
| resolved-config delta vs production-006 | **zero** differences across every `COMFYMODAL_GOLDEN_*` and `COMFYMODAL_V2_*` flag |
| M1-only flags | `COMFYMODAL_M1_EVIDENCE_LEVEL=1`, `COMFYMODAL_M1_OPERATION_RECORDS=1` |

## 3. Instrumentation methodology

Two gated selectors, both off in production-006:

- `COMFYMODAL_M1_EVIDENCE_LEVEL` (0/1/2) widens the **already-preallocated**
  shared `OP` ring from 18 to 26 fields. Level 1 adds two
  `time.thread_time_ns()` reads immediately around the native `memmove`, plus
  claim-side wall/CPU. No allocation, no logging, no new lock, no syscall, no
  control-flow change on the hot path.
- `COMFYMODAL_M1_OPERATION_RECORDS` persists the per-extent records. This runs
  strictly **after** `wait_quiescent()`, so it cannot perturb the timed window.

Parent and source-owner child are the same module and derive the identical
record layout from the identical environment, so the shared-memory format cannot
diverge.

**Level-0 identity proof** (`DIRECT MEASUREMENT`): with the flag unset,
`ACTIVE_OP is OP` → `True`, `ACTIVE_OP_FIELDS == OP_FIELDS` → `True`,
`ACTIVE_MAX_OPS == MAX_OPS` → `True` (3174). The shared-memory format is
byte-identical to production-006.

**Regression proof** (`DIRECT MEASUREMENT`): `tests/test_c0_source_threads.py`
55 passed / 5 skipped; with `test_golden_model_transport.py` 81 passed / 5
skipped. Full `fast_unit` gate: **388 passed, 5 skipped, 2 failed** — an exact
match to the pristine production-006 worktree, verified twice there (25.40 s and
23.69 s). The 2 failures are pre-existing environment-dependent identity
assertions (`test_rx9p_h_identity_chain.py::test_success_path_exact`,
`::test_compact_nested_sage_observation_is_mismatch`, both asserting on empty
`arm`/`app`). Not caused by M1.

One additional ordering-dependent flake was observed **once** on this branch:
`tests/test_c0_control_session.py::test_c0_window_trace_claim_ordinals_and_first_flags`.
It passes in isolation and as a whole file, and did not reproduce on two
subsequent full-suite runs of this branch nor on two runs of the pristine tree.
Recorded as a pre-existing flake, not introduced by M1.


### Two instrumentation defects found and fixed (recorded, not hidden)

1. **`change_requires="run"` was wrong.** The source owner reads its evidence
   level at *module import*, before any per-request env is applied. A run-scoped
   flag reached the request envelope but never the imported module. Fixed by
   making both selectors deploy-scoped.
2. **`modal_app.py` forwards an explicit env allowlist.** The flags were present
   in the deploy receipt yet `null` inside the container. Proven in-container by
   the self-diagnosing `operations_probe`: `records_env_raw=null`,
   `owner_level=0`, `owner_active_op_size=144`. Fixed by forwarding both
   selectors. After the fix the probe reports `records_env_raw="1"`,
   `owner_level=1`, `owner_active_op_size=208`, `retained_records=120/184`.

Both were diagnosed from evidence rather than guessed, and both are now
self-detecting.

## 4. Observer-effect validation

`DIRECT MEASUREMENT`

| set | CLIP source GB/s p50 | UNET source GB/s p50 | n |
|---|---|---|---|
| Level-0 counted (production-006) | 4.549 | 4.243 | 10 |
| Level-1 instrumented | 4.065 | 4.309 | 7 |

`UNKNOWN` as a precise overhead figure: both sets contain natural fast/slow
outliers (CLIP spans 1.636-5.141 counted, 2.072-5.397 instrumented), so with
these sample sizes the two medians are **not** separable from run-to-run
variance. The honest statement is that Level-1 instrumentation is
**not demonstrated to change source throughput**, and the spread is dominated by
natural variance, not by instrumentation. A dedicated paired A/B (same container,
alternating levels) would be required to bound it, and was not run.

Level-2 and Level-3 were **not** run. Rationale in §24.

## 5. gVisor observability availability matrix

See `GVISOR_OBSERVABILITY_MATRIX.md` for the full table. Summary:

| metric | available | note |
|---|---|---|
| per-extent wall (`monotonic_ns`) | **YES**, ns resolution | primary measurement |
| per-extent thread CPU (`thread_time_ns`) | **YES but 10 ms quantized** | all 41 distinct deltas are exact multiples of 10 ms |
| `ru_minflt` / `ru_majflt` | **NO** — silent zeros on 1216/1216 ops | not "no faults", "not implemented" |
| `ru_nvcsw` / `ru_nivcsw` | **NO** — silent zeros | runqueue wait unmeasurable |
| `mincore()` | **NO** — historically reports all-resident (false) | deliberately not called |
| `readahead()` | **NO** — `EINVAL(22)` | historical |
| `cpu.stat` | **NO** — historically unreadable | historical |
| NUMA topology | **NO** | expected under gVisor |
| CPU placement/migration, affinity, `/proc` status/smaps, PSI, cgroup | probe implemented, **not yet emitted** | one Level-2 run would close these |

## 6. Historical evidence ledger

See `HISTORICAL_EVIDENCE_LEDGER.md`.

**Most important correction:** the repo's dominant historical ledger
(`SOURCE_IO_EXPERIMENT_LEDGER.md`) was produced on **4 reader PROCESSES with
FRESH per-extent mmap**. production-006 is **4 reader THREADS with WHOLE mmap**.
Applicability was re-judged for all 15 already-answered mechanisms. A further
`UNAVAILABLE-IN-ENVIRONMENT` finding: `thread_time_ns()` is *not* permanently
zero here (historical ledger said it "can" be) — it works, at 10 ms resolution.

## 7-9. Call graph, scheduler sequence, lock graph

Fully documented in `SCHEDULER_AND_HOT_PATH_AUDIT.md` §2-4. Headline
`CODE-PROVEN` results:

- one global shared `next_range` counter; **dynamic, contiguous, no sticky
  regions, NO work stealing**
- PLAN/ACK is **per model generation**, not per extent
- READY is **authoritative in the shared slot table**; the doorbell is a hint
  with table-recovery fallback
- **no lock is held across the native memcpy**
- **no lock is held across an H2D completion wait**
- readers do **not** serialise unexpectedly (QD4 on 456/480 CLIP and 713/736 UNET ops)

## 10. Exact physical source operation semantics

`DIRECT MEASUREMENT` + `CODE-PROVEN`

One physical source operation = one claim of one contiguous 64 MiB range →
pacer wait → one native `libc.memmove` of that range from the whole mapping into
one 64 MiB arena slot → one READY publication → one H2D submit of the same range.
**1 source op : 1 H2D op**, exactly.

## 11-12. CLIP and UNET byte/range/header facts

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| file | `qwen_3_4b.safetensors` | `z_image_turbo_bf16.safetensors` |
| data-section bytes | 8 044 936 192 (7672.25 MiB) | 12 309 817 472 (11 739.56 MiB) |
| extent unit | 67 108 864 (64 MiB) | 67 108 864 (64 MiB) |
| source ops | **120** = ceil(7672.25/64) | **184** = ceil(11739.56/64) |
| H2D ops | 120 | 184 |
| H2D max submission | 67 108 864 | 67 108 864 |
| H2D min submission (tail) | 58 981 376 (56.249 MiB) | 28 895 360 (27.557 MiB) |
| H2D mean submission | 67 041 134.93 | 66 902 269 |
| ops if 32 MiB unit | 240 — **mismatch** | 367 — **mismatch** |

**The 32 MiB vs 64 MiB question is resolved.** `dispatcher.source_block_bytes =
33554432` observed on 10/10 runs is a **stale nominal label** in dispatcher
telemetry. It does not control the live path: the op count (120/184) matches the
64 MiB ceil exactly and is half the 32 MiB count. Use **64 MiB**; treat the
32 MiB field as a label defect, not a behaviour.

## 13-14. Complete timing ledgers

`DIRECT MEASUREMENT`, baseline cohort (n=10)

**Stage walls (ms)**

| stage | min | p50 | p90 | max |
|---|---|---|---|---|
| `golden_restore` | 0.16 | 0.19 | 0.25 | 0.33 |
| `golden_request_setup` | 1.32 | 1.57 | 2.03 | 2.77 |
| `golden_clip_load` | 1747.25 | 1921.14 | 4091.20 | 5292.14 |
| `golden_unet_load` | 2608.69 | 3093.69 | 5861.66 | 6331.03 |
| `golden_clip_forward` | 2438.46 | 3229.66 | 4261.74 | 4454.97 |
| `golden_sampling` | 3736.37 | 3882.97 | 4131.65 | 4394.64 |
| `golden_vae_load` | 400.58 | 611.37 | 875.49 | 1053.77 |
| `golden_teardown` | 0.62 | 0.86 | 1.53 | 1.61 |
| request duration | 17289.26 | 26172.30 | 67946.67 | 83240.23 |

**Non-source envelope (ms)**

| | CLIP | UNET |
|---|---|---|
| skeleton_patcher_construction p50 / max | 0.59 / 1.34 | 66.17 / 79.68 |
| skeleton_bind_assign p50 / max | 9.27 / 17.08 | not emitted for UNET |
| owner_publish_handoff p50 | 0.01 | not emitted |
| storage_adoption p50 / max | 15.02 / 24.74 | 12.51 / 17.79 |
| compute_ready_proof p50 / max | 2.14 / 3.38 | not emitted |
| **non-source total (total_load − source_wall) p50 / max** | **120.6 / 380.0** | **124.6 / 337.7** |
| layout_resolve_ms p50 / max | 36.89 / 362.26 | 0.67 / 1.20 |
| source_go_offset_ms p50 / max | 107.29 / 370.30 | 18.21 / 301.08 |
| gpu_ready_tail_ms p50 / max | 3.09 / 7.12 | 8.38 / 149.80 |
| cudaHostRegister (first load only) | 495.94 | reused |
| source-owner spawn+startup | 500.78 (overlapped) | reused |

`CODE-PROVEN` / `UNAVAILABLE`: `unet_load_timing` phase decomposition is **not
emitted** for UNET in the counted profile (CLIP-only instrumentation at
`golden_serial.py:11426-11504`). UNET non-source numbers above come from
`golden_model_load_waterfall` + `total_load_ms`, which is sufficient for the
envelope but not for per-phase attribution.

## 15. Effective-QD analysis

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| configured QD | 4 | 4 |
| max observed QD | 4 | 4 |
| **effective mean QD (time-weighted)** p50 | **3.882** | **3.678** |
| effective QD min / max across runs | 3.638 / 3.977 | 3.066 / 3.905 |
| time at QD0 p50 | 0.0 ms | 0.0 ms (non-zero in 3/10 runs, up to 82.5 ms) |
| time below 4 readers p50 / max | 180.1 / 373.8 ms | 417.7 / **2116.3** ms |
| fraction at QD4 p50 | 0.908 | 0.860 |
| per-op concurrency histogram (M1, 1216 ops) | QD4: 456, QD3: 11, QD2: 9, QD1: 4 | QD4: 713, QD3: 11, QD2: 6, QD1: 6 |
| longest QD0 interval | 0.0 ms | 82.5 ms (one run) |
| QD collapse at end of model | **not observed** | **not observed** |

**`DIRECT MEASUREMENT`: there is no end-of-model QD collapse.** QD4 holds for
95% (CLIP) / 97% (UNET) of operations, and the QD-weighted time integral is
3.88 / 3.68 against a target of 4.

**Critical counter-intuitive result:** the two *slowest* baseline runs had
effective QD **3.962 and 3.977** — essentially perfect — while delivering
2.269 and 1.636 GB/s. **High concurrency with low throughput means the readers
were all busy but each copy was slow.** QD underfill is therefore *not* the
cause of the slow runs. This is the single most important finding for the next
optimization campaign.

## 16. Reader analysis

`DIRECT MEASUREMENT`, M1 pooled (1216 extents)

| reader | CLIP ops | CLIP bytes | CLIP busy ms | CLIP mean op | UNET ops | UNET bytes | UNET busy ms | UNET mean op |
|---|---|---|---|---|---|---|---|---|
| 0 | 118 | 7 910 718 464 | 9434.6 | 79.95 | 165 | 11 034 749 056 | 12191.1 | 73.89 |
| 1 | 124 | 8 313 371 648 | 9296.7 | 74.97 | 191 | 12 779 579 520 | 12344.4 | 64.63 |
| 2 | 122 | 8 171 026 432 | 9399.6 | 77.05 | 193 | 12 952 010 752 | 12260.3 | 63.52 |
| 3 | 116 | 7 784 628 224 | 9360.2 | 80.69 | 187 | 12 472 930 560 | 12282.3 | 65.68 |

Byte imbalance CLIP max/min = 1.068; busy-wall imbalance = 1.014. UNET byte
imbalance = 1.174 (reader 1-3 carry ~13% more than reader 0, consistent with the
first extent being claimed by whoever is free).

`DIRECT MEASUREMENT`: readers are **evenly balanced**. No reader is
systematically slow. Slow-op rate by reader is 2.5-3.3% (CLIP) and 2.6-4.2%
(UNET) — flat.

## 17. Reader-straggler analysis

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| reader completion spread (last − first) p50 | ~18-43 ms (per-run 17.8-42.8) | 17.8 ms |
| **straggler tail (last − 2nd last)** | **0.56 – 13.13 ms** | **0.56 – 25.91 ms** |
| as fraction of source wall | ≤0.9% | ≤1.2% |

**`DIRECT MEASUREMENT`: the reader straggler tail is negligible** — single-digit
to low-tens of milliseconds, under ~1% of source wall. The final extent's
owner is not the problem.

## 18. Slot analysis

`DIRECT MEASUREMENT`

| slot | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| CLIP fills | 91 | 97 | 87 | 80 | 82 | 28 | 9 | 6 |
| UNET fills | 134 | 134 | 137 | 135 | 124 | 53 | 13 | 6 |
| CLIP slow-op rate | 4.4% | 2.1% | 3.4% | 3.8% | 2.4% | 0% | 0% | 0% |
| UNET slow-op rate | 5.2% | 3.0% | 3.6% | 1.5% | 3.2% | 0% | 0% | 0% |

**`DIRECT MEASUREMENT`: slots 5-7 are barely used** (4-11% of fills) because
H2D drains faster than 8 slots can fill. **Slow work does NOT follow a specific
slot** — rates are 1.5-5.2% across slots 0-4 with no outlier. This answers the
question "does slow source work follow a specific slot?" — **no**.

Slot wait totals (M1): CLIP 188.49 ms over 6 waits; UNET 198.85 ms over 4 waits.
Baseline cohort: CLIP slot_wait p50 26.87 / max 143.42 ms; UNET p50 293.45 /
max 861.92 ms.

**`all_slots_occupied_count` — corrected by the transition census (§33):** it is
**0 on 10/10 production-006 cohort runs** for both roles, but **non-zero for UNET
in 4/7 M1 diagnostic runs** (21, 625, 654, 681). The correct statement is:
*full-slot capacity pressure occurs during UNET under diagnostic conditions and
is absorbed without slowing extents* (CPU/wall stays 0.93-1.01), rather than
being categorically absent. Both measurements are reported.

**H2D/consumer backpressure is not a cause of slow extents.** When capacity
pressure does occur it delays *claiming*, not copying, and the copies that follow
are not slower.

## 19. Offset analysis

`DIRECT MEASUREMENT`, M1, 4 runs per role so every offset repeats

| | CLIP | UNET |
|---|---|---|
| offsets observed in ≥2 runs | 120/120 | 184/184 |
| **median within-offset CV** | **0.173** | **0.171** |
| p90 within-offset CV | 0.652 | 0.897 |

**`DIRECT MEASUREMENT`: latency does NOT follow the file offset.** Example —
CLIP offset 201 372 448: min 97.05 ms, median 126.50 ms, max **1421.08 ms** across
4 runs. The same offset is 14× slower in one run than another. A genuinely
"bad offset" (bad block, bad placement) would be slow every time; these are not.

Within-offset CV 0.17 is *lower* than the per-run spread of total throughput,
which is the signature of **run-level, not location-level, variance**.

## 20. Pacing analysis

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| min observed source-start gap | 4.021 ms | 4.015 ms |
| **pacer violations** | **0** (10/10 + 4 M1 runs) | **0** |
| extents actually delayed | 17/120 | 25/184 |
| total pacing wait | 36.73 ms | 55.70 ms |
| **% of source wall** | **1.77%** | **2.32%** |

The 4 ms floor is **ENFORCED** at copy start (`CODE-PROVEN`:
`GlobalSourcePacer.paced_copy` releases the lock at `mark_actual_start`
immediately before `memmove`; the cross-process `SharedSourcePacer` is the weaker
advisory variant and is not the production arm). Pacing costs ~2% of source wall
and is deliberately purchased — the historical ledger shows zero pacing loses
10-12% with worse tails.

## 21. Scheduler/control overhead

`DIRECT MEASUREMENT` + `CODE-PROVEN`

- `memcpy_end → ready_ns`: p50 **0.000 ms**, p90 0.001 ms, max 0.010 ms.
  READY publication is O(1) and free.
- Slot wait: 188-199 ms per model across 4-6 events (M1).
- Capacity wait: **0.0 ms**, 0 events, all runs — readers never block for capacity.
- Pacing: ~2% of wall (§20).
- Combined identified control overhead: **~2% of source wall**, of which pacing
  is the overwhelming majority.

## 22-23. Whole-mmap and FD/mount metadata

`DIRECT MEASUREMENT`

- mmap lifecycle `whole` on 10/10 baseline and 4/4 M1 Level-1 runs.
- `mmap_map_count = 0`, `mmap_unmap_count = 0` on 10/10 runs, both roles.
- `map_start_ns = 0` and `munmap_start_ns = 0` on **1216/1216** M1 extents.
- One whole mapping per model generation; one FD per generation, opened by the
  owner in `build_plan` and closed in `retire_plan`.
- `mmap_fresh` engine name is the C0 **arm selector**; `whole` is the
  independently-tested **lifecycle** and wins at run time.

## 23. File / FD / mount metadata — `DIRECT MEASUREMENT` (Level 2)

Exact model file identity, captured with `os.stat` plus an independent
seek-to-end size confirmation:

| | CLIP | UNET |
|---|---|---|
| path | `/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors` | `/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors` |
| size (stat) | **8 044 982 048 B** | **12 309 866 400 B** |
| size (independent confirm) | 8 044 982 048 B | 12 309 866 400 B |
| device | 31 | 31 |
| inode | 7 | 55 |
| st_blksize | 4096 | 4096 |
| st_blocks | 15 712 856 | 24 042 708 |
| implied allocated bytes | ~64.4 GB? no — see note | — |

**Note on `st_blocks`:** the value is reported exactly as the kernel returned it.
It is **not** converted into an allocated-byte figure here, because `st_blocks`
is reported in filesystem-specific units whose relationship to 512-byte blocks is
not guaranteed by the surface under gVisor. Converting it would be an
unjustified inference.

**`DERIVED`: file size minus measured data-section bytes is the safetensors
header.** CLIP: 8 044 982 048 − 8 044 936 192 = **45 856 B** of header.
UNET: 12 309 866 400 − 12 309 817 472 = **48 928 B** of header. Both are
consistent with a 4B-parameter Qwen text encoder and a large diffusion UNet.

**`UNAVAILABLE`:** `/proc/self/mountinfo` opens successfully but contains **zero**
lines mentioning `safetensors`, `/models`, or `/root` — the container's mount
table does not describe the model paths. No filesystem type is asserted, and the
paths are explicitly **not** labelled "Modal storage"; only what the kernel
returned is reported. FD numbers were not enumerated (`/proc/self/fd` was not in
the probe set); FD *lifecycle* is nonetheless fully determined by code (§10 of
the scheduler audit) and by the measured `mmap_map_count=0`.

`UNAVAILABLE`: exact virtual addresses, mapping flags, page sizes,
RSS/Referenced/Locked and `VmFlags` — `smaps_rollup` does not exist in this
runtime and `/proc/self/smaps` was not collected.

## 24. Page-service vs memcpy evidence — the headline question

`DIRECT MEASUREMENT`, 1216 extents

| | CLIP | UNET |
|---|---|---|
| copy wall p10 / p50 / p90 / p99 / max | 44.21 / 55.99 / 78.71 / 924.90 / 1421.08 ms | 37.87 / 50.75 / 62.51 / 686.74 / 1116.19 ms |
| copy thread-CPU p50 / p90 / max | 50.00 / 70.00 / 1320.00 ms | 50.00 / 60.00 / 1050.00 ms |
| **CPU/wall ratio p10 / p50 / p90** | 0.8187 / **0.9381** / 1.0403 | 0.8159 / **0.9421** / 1.0499 |
| **off-CPU residual p50 / p90 / max** | **3.80** / 10.68 / 101.08 ms | **3.18** / 9.58 / 76.81 ms |

**Answer: the physical copy is CPU/memcpy-dominated, not page-service-dominated.**
The calling thread is actively executing for ~94% of every 64 MiB copy. Median
non-executing time is ~3-4 ms per extent, i.e. ~6% of a ~55 ms copy.

`CODE-PROVEN` corroboration: the copy is a single `libc.memmove` through
`ctypes.CDLL(None)` (`:1664-1665`), which **releases the GIL**. The thread-CPU
clock can only advance by ~94% of wall if the thread is genuinely running native
code rather than waiting.

**Mandatory caveats:**
1. The thread-CPU clock is quantized to **10 ms** (all 41 distinct deltas are
   exact multiples of 10 ms). Individual ratios are only meaningful in
   aggregate; `CPU > wall` on 288/1216 ops is a rounding artifact, **not** evidence
   of extra CPU.
2. The off-CPU residual is an **upper bound on non-executing time**. It is
   explicitly **NOT** "storage time". It cannot be decomposed into page service
   vs. runqueue wait because `ru_nvcsw`/`ru_nivcsw` are zero and `mincore()` lies.

`UNRESOLVED`: the exact split of the ~6% residual, and whether any page service
occurs *inside* the memmove. `UNAVAILABLE UNDER gVisor`: `mincore()`,
`ru_minflt`, `ru_majflt`, `schedstat`.

**Level-3 invasive resident-copy calibration was deliberately NOT run.** With
CPU/wall = 0.94 the split is already answered at the resolution this environment
permits; a resident repeat-copy would add cost and risk for information the
10 ms clock cannot resolve.

## 25. Thread CPU / off-CPU evidence

As §24. `DIRECT MEASUREMENT` with the 10 ms quantization caveat.

## 26. Fault / context-switch evidence

`UNAVAILABLE UNDER gVisor`. `ru_minflt`, `ru_majflt`, `ru_nvcsw`, `ru_nivcsw`
all return exactly 0 on 1216/1216 extents. This is a non-implementation, not an
absence of faults — the counters cannot distinguish the two.

## 27. Scheduler / runqueue evidence — `UNAVAILABLE UNDER gVisor` (now proven)

`DIRECT MEASUREMENT` (Level 2): `/proc/self/task/<tid>/schedstat` returns
`FileNotFoundError` for **all 16** sampled thread ids — the per-task directory
exists but `schedstat` does not. Additionally
`/proc/self/task/<tid>/status` **does** exist and reports
`voluntary_ctxt_switches: 0` and `nonvoluntary_ctxt_switches: 0` for every
sampled thread — a second, independent confirmation of the `rusage` silent-zero
result in §26.

Runqueue wait, timeslice count and slice count are therefore **not obtainable in
this runtime**, not merely un-attempted. The 10 ms thread-CPU clock is the only
partial substitute, and it cannot separate runqueue wait from in-CPU work.

## 28. CPU placement / migration — `UNAVAILABLE UNDER gVisor`

`DIRECT MEASUREMENT` (Level 2): `os.sched_getcpu` is **absent from the `os`
module** in this runtime (`sched_getcpu_symbol_present = False`,
`cpu_now = None`). CPU migration cannot be sampled at all.

What *is* available: `os.sched_getaffinity(0)` is present and returns **28
logical CPUs**. The container is therefore 7× oversubscribed relative to the 4
reader threads. `SUPPORTED INFERENCE`: this does not by itself explain the
near-4 effective concurrency, because the readers are demonstrably inside
`memmove` ~94% of the time rather than queued.

## 29. NUMA evidence — `UNAVAILABLE UNDER gVisor`

Not exposed. No privileged tools were installed and no placement changes were
made. `UNRESOLVED` whether NUMA locality exists at all in this runtime; there is
no surface that would reveal it.

## 30. cgroup / pressure evidence — `UNAVAILABLE UNDER gVisor` (now proven)

`DIRECT MEASUREMENT` (Level 2), every one a `FileNotFoundError`:

| path | result |
|---|---|
| `/proc/pressure/cpu` | absent |
| `/proc/pressure/memory` | absent |
| `/proc/pressure/io` | absent |
| `/sys/fs/cgroup/cpu.stat` | absent |
| `/sys/fs/cgroup/memory.current` | absent |
| `/sys/fs/cgroup/cpu.pressure` | absent |
| `/sys/fs/cgroup/memory.pressure` | absent |
| `/proc/self/smaps_rollup` | absent |

This confirms the historical ledger's "cpu.stat unreadable" with a direct
measurement. **CPU throttling, runnable pressure, memory pressure and I/O
pressure are all unobservable in this environment.** No causal claim is made or
can be made from host pressure.

**Consequence for the next campaign:** because no host-side pressure signal is
available from inside the container, the per-request throughput ceiling
(§45.3) cannot be attributed from within the guest. It requires provider/host-side
telemetry, which is outside this environment's reach.

## 31. READY publication / consumer analysis

`DIRECT MEASUREMENT`: publication 0.000 ms p50 (§21). `ready_queue_wait_ms` is
the *parent's* blocking time awaiting doorbells (CLIP p50 1583.8, max 2688.4;
UNET p50 4132.8, max 6693.2) — this is the consumer keeping up, not a cost.
`ready_queue_block_count = 0` on all runs: the parent never had to block on a
full queue.

## 32. H2D analysis

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| H2D count / bytes | 120 / 8 044 936 192 | 184 / 12 309 817 472 |
| H2D reconciled | true (10/10) | true (10/10) |
| GPU copy active sum p50 / max | 213.81 / 617.92 ms | 310.0 / 918.2 ms |
| H2D event completion latency p50 | 3 422 719.89 ms (cumulative, not per-op) | — |
| final drain p50 / max | 0.42 / 1.53 ms | 1.83 / **143.45** ms |
| dispatcher reap wall p50 / max | 61.75 / 113.52 ms | 76.2 / 140.5 ms |
| gpu_ready_tail p50 / max | 3.09 / 7.12 ms | 8.38 / 149.80 ms |
| aggregation | disabled (0 aggregated / 120 non-aggregated) | disabled (0 / 184) |
| streams / events | 1 dedicated stream, 8 start + 8 end, 18 event objects, 224 re-records | same |

GPU copy active time is **6-7% of source wall** — H2D is fully hidden behind
source. The only notable H2D-side outlier is UNET `gpu_ready_tail_ms` max
149.80 ms and `final_drain_wall_ms` max 143.45 ms (single occurrences).

Capacity pressure: `all_slots_occupied_count = 0` on 10/10 production-006 runs,
but **non-zero for UNET in 4/7 M1 runs** (§33, §18). Even where it occurs, extents
do not slow (CPU/wall 0.93-1.01), and slots 5-7 carry only 4-11% of fills.
**H2D/consumer backpressure is therefore ruled OUT as a cause of slow extents**,
while slot-capacity *pressure* is documented as a real, absorbed UNET phenomenon.

## 33. CLIP → UNET transition state — `DIRECT MEASUREMENT` (7 runs)

| property | CLIP | UNET | verdict |
|---|---|---|---|
| same source-owner PID | — | — | **True 7/7** — one process spans both |
| same reader thread identities (tids) | — | — | **True 7/7** — threads are NOT recreated |
| same mmap lifecycle | — | — | True 7/7 (`whole`) |
| `source_transport_created_once` identical across roles | — | — | **True 7/7** — one transport object |
| source ops | 120 | 184 | complete coverage |
| `release_count` | 120 | 184 | every extent released exactly once |
| `ownership_quiescent` | True | **True 7/7** | no ownership crosses the boundary |
| `poisoned` | False | **False 7/7** | no poison |
| arena reused | False (first use) | **True 7/7** | carried |
| CUDA stream reused | False | **True 7/7** | carried |
| host registration reused | False | **True 7/7** | carried |
| layout cache hit | False | **True 7/7** | carried |

**Answering the audit questions factually:**
- **Does UNET begin with pristine logical ownership? YES** — `ownership_quiescent=true`,
  `poisoned=false`, release counts exactly match op counts (120/184) on 7/7 runs,
  no `all_slots_occupied` carryover.
- **What is intentionally carried?** the source-owner process, its 4 reader
  threads, the arena, CUDA stream/events, host registration, the transport
  object, and the layout cache — all confirmed reused.
- **What is reset?** generation counter, whole mapping, model FD, range plan,
  slot states, READY state, per-model counters.
- **What is reused, and is reuse harmful? NO EVIDENCE OF HARM.** Reuse is
  deliberate (`golden_model_transport.py:861-902` explicitly avoids recreating C0
  resources) and measurably saves ~496 ms of `cudaHostRegister` plus ~500 ms of
  owner startup on UNET.
- **Transition gap:** CLIP `plan_install_end` → UNET `plan_install_begin`
  = p50 **133.11 ms**, min 69.97, max 847.74 (n=7). This is inter-model
  scheduling, not source work.

**New finding — `all_slots_occupied_count` is NOT zero for UNET in 4/7 runs**
(21, 625, 654, 681 occurrences). This **corrects §18 and §32**, which reported 0
from the production-006 cohort. In the M1 runs UNET does hit full-slot capacity
substantially. It still does not create slow extents (CPU/wall stays 0.93-1.01),
so the correct statement is: **slot-capacity pressure occurs during UNET and is
absorbed, rather than being absent.** The production-006 cohort genuinely shows
0; the M1 diagnostic runs show non-zero. Both are reported rather than reconciled
away.

## 34. CLIP-forward / UNET overlap — `DIRECT MEASUREMENT` (CLOSED, zero GPU cost)

Per-extent classification of all 736 UNET extents against the **real transformer
forward interval** (`CLIP_FORWARD_START` → `clip_forward_complete`, not the coarse
stage):

| run | overlap fraction | before | during | after |
|---|---|---|---|---|
| `035227` | 1.000 | 0 | **184** | 0 |
| `035423` | 1.000 | 0 | **184** | 0 |
| `035455` | 1.000 | 0 | **184** | 0 |
| `035604` | 0.528 | 0 | 96 | 88 |

Pooled: `during` n=648 (4 runs), `after` n=88 (1 run), `before` **empty in all runs**.

| bucket | n | wall p50 | wall p90 | wall max | CPU/wall p50 |
|---|---|---|---|---|---|
| during CLIP forward | 648 | **50.84 ms** | 62.19 ms | 1116.19 ms | 0.9835 |
| after CLIP forward | 88 | **49.70 ms** | 197.68 ms | 1026.81 ms | 1.0061 |

**during/after median wall ratio = 1.0229** (2.3% slower while CLIP forward is active).

**Answer: CLIP forward overlaps essentially the entire UNET source window
(100% of extents in 3/4 runs), and it costs ~2.3% of median extent wall — not the
large CLIP/UNET contention the historical ledger reported (+39-62% encode,
+17.8-23.2% H2D).** `CORRELATION` Spearman ρ(overlap_fraction, UNET median
extent wall) = **−0.258** (n=4): a *lower* overlap fraction did not predict
slower extents. n=4 is far too small for inference and variance dominates.

**What is proven:** UNET source runs almost entirely concurrent with CLIP
transformer forward; the measured median penalty on the source side is ~2%.
**What is not proven:** that CLIP forward has no effect on H2D or bind (those
per-op timestamps were not collected); and the n=4 correlation.

This **downgrades** CLIP-forward overlap from "leading candidate" for the UNET
excess to "measured ~2% median contributor".

## 35. GPU allocation analysis

`DIRECT MEASUREMENT`

- `cudaHostRegister` of the 512 MiB shared arena: **495.94 ms**, once per
  container (CLIP, first load), overlapped with source-owner spawn
  (`overlapped_spawn_and_register=true`). UNET: `host_registration_reused=true`.
- `pinned_alloc_ms`, `populate_ms`, `populate_cpu_ms`, `populate_workers` all
  null/0; `pinned_arena_physical_allocation_bytes = 0`;
  `shm_populate_enabled=false`; `dma_ring_enabled=false`; `five_slots_enabled=false`.
- `destination_reused = false` for both roles: a new GPU destination is allocated
  per model (`destination_growth_ms` null in the counted profile).
- GPU copy active sum 213.81 ms (CLIP p50) for 8.04 GB = ~37.6 GB/s effective H2D.

`cudaHostRegister` at 495.94 ms is the largest single non-source item in the
request and is **currently required** for async H2D from shared memory.

## 36. Tensor / view / state-dict analysis

`DIRECT MEASUREMENT`

| | CLIP | UNET |
|---|---|---|
| state_dict_count | 1 | — |
| adopted_parameter_count | 398 published tensors | — |
| skeleton_wall_ms p50 | 0.59 | 66.17 |
| skeleton_bind_assign p50 | 9.27 | not emitted |
| storage_adoption p50 | 15.02 | 12.51 |
| compute_ready_proof p50 | 2.14 | not emitted |

UNET skeleton construction is **112× slower than CLIP** (66.17 vs 0.59 ms)
because UNET instantiates a real diffusion skeleton while CLIP's is cached or
trivial. Total non-source envelope is nearly identical (120.6 vs 124.6 ms p50),
so this is a redistribution inside a fixed budget, not extra cost.

## 37. Bind / adoption / proof analysis

`DIRECT MEASUREMENT`: CLIP `clip_adoption_identity` reports
`state_dict_count=1`, `tensor_count`, `view_count`, `matched_count`,
`same_storage_count`, `copied_storage_count`, `unexpected_device/shape/dtype_count`,
`outer_extra_count=1` (`qwen3_4b.logit_scale`, 4 bytes, on CPU).
UNET `unet_storage_identity` reports `tensor_count`, `same_storage_count`,
`copied_storage_count`, `unexpected_*=0`, `leftover_count=0` — i.e. **zero
unexpected tensors and zero leftovers**, so adoption is provably clean.
`compute_ready_proof` CLIP p50 2.14 ms.

## 38. GC / runtime-interruption analysis — `DIRECT MEASUREMENT` (question closed)

Across all M1 runs, 14 events contain "gc". The single distinct payload is:

```json
{"status":"applied","module_name":".../RES4LYF.beta.samplers",
 "intercepted_collect_count":0,"suppression_wall_ms":null,
 "restoration_state":"pending"}
```

**`DIRECT MEASUREMENT`: `intercepted_collect_count = 0` on every run.**
The Golden path applies an explicit GC suppression to
`RES4LYF.beta.samplers` and **no GC collection was intercepted during any run**,
including the source windows. `suppression_wall_ms` is null because there was
nothing to suppress.

**Conclusion: GC does not interfere with CLIP or UNET source loading in
production-006.** The question is closed rather than left unresolved. Note the
suppression targets a third-party sampler module, not the loader itself — so this
is evidence that *no* collection occurred, not merely that the loader's own
collections were suppressed.

## 39. UNET vs CLIP proportionality — why UNET costs more

`DIRECT MEASUREMENT`

```
payload_ratio (UNET bytes / CLIP bytes) = 1.5301   (constant — same two models)
```

Per-run: `UNET_SOURCE_EXCESS_MS = unet_source_wall − clip_source_wall × 1.5301`

| dataset | p50 | p90 | min | max |
|---|---|---|---|---|
| baseline cohort (n=10) | **+54.5 ms** | +853.5 ms | **−3797.2 ms** | +2597.0 ms |
| M1 Level-1 (n=7) | **+22.2 ms** | — | **−839.4 ms** | +3652.0 ms |

`UNET_NON_SOURCE_EXCESS_MS` p50 = **−28.8 ms** (UNET's non-source envelope is
*slightly smaller* than CLIP's).

**The premise "UNET costs more than payload scaling predicts" is only weakly
supported, and the sign is not stable.** Median excess is +54.5 ms on 1.7-3.0 s
of source wall (<2%), and it is **negative** in several runs.

Attribution of the observed excess:

| term | evidence | magnitude |
|---|---|---|
| effective-QD difference | `DIRECT MEASUREMENT` CLIP 3.882 vs UNET 3.678 median | UNET runs at ~5% lower concurrency, so a small penalty |
| reader straggler tail | `DIRECT MEASUREMENT` 0.56-25.91 ms | ≤1.2% of wall — minor |
| pacing | `DIRECT MEASUREMENT` 1.77% vs 2.32% | UNET pays marginally more |
| slot wait | `DIRECT MEASUREMENT` UNET p50 293.45 / max 861.92 ms vs CLIP 26.87 / 143.42 | UNET pays ~10× more, but small vs wall |
| H2D tail / backpressure | `DIRECT MEASUREMENT` all_slots_occupied=0, slots 5-7 idle | **ruled out** |
| GPU allocation / views / bind / adoption | `DIRECT MEASUREMENT` non-source excess **−28.8 ms** | **ruled out — UNET is not worse here** |
| CLIP-forward overlap | `UNRESOLVED` — not measured per-extent | **UNRESOLVED, and is the leading candidate for the large positive outliers** |
| **per-extent copy cost variance** | `DIRECT MEASUREMENT` the excess tracks *which run was slow*, not the model | **dominant term** |
| **unresolved residual** | — | **UNRESOLVED** |

**`CORRELATION` (n=10): Spearman ρ(CLIP GB/s, UNET GB/s) within a run = +0.782.**
CLIP and UNET source speed move **together** within a request.

**`SUPPORTED INFERENCE`: the dominant driver of the UNET excess is run-level
container/host throughput variance, not anything UNET-specific.** The two
fastest baseline runs had UNET *faster* than byte-proportional prediction
(−3.8 s), and the excess correlates with the run being globally slow, not with
UNET's size. Combined with §15 (highest-QD runs are the slowest) and §19
(latency does not follow offset), the evidence points to a **per-request
environmental throughput ceiling** that both models hit, with UNET hitting it
harder because it has 184 extents instead of 120 and therefore more chances to
land in a degraded window.

`UNRESOLVED`: how much of that ceiling is CLIP-forward contention (§34).

## 40. Slow-operation / tail taxonomy

`DIRECT MEASUREMENT`, M1 pooled

**CLIP** (n=480, median 55.99 ms, total copy wall 37 491 ms)

| definition | count | % ops | share of total copy wall |
|---|---|---|---|
| >p95 | 24 | 5.0% | **30.9%** |
| >p99 | 5 | 1.0% | 15.3% |
| >2× median | 18 | 3.8% | 29.3% |
| >3× median | 14 | 2.9% | 27.9% |

**UNET** (n=736, median 50.75 ms, total copy wall 49 078 ms)

| definition | count | % ops | share of total copy wall |
|---|---|---|---|
| >p95 | 37 | 5.0% | **28.8%** |
| >p99 | 8 | 1.1% | 14.9% |
| >2× median | 23 | 3.1% | 26.4% |
| >3× median | 22 | 3.0% | 26.1% |

**Cluster classification — the decisive result:**

| run | CLIP | UNET |
|---|---|---|
| `035227` | no op >3× median — **uniform** | 1 slow op, 1 cluster — **isolated spike** |
| `035423` | no op >3× median — **uniform** | no op >3× median — **uniform** |
| `035455` | no op >3× median — **uniform** | no op >3× median — **uniform** |
| `035604` | 14 slow ops, 7 clusters — **mixed/contiguous** | 21 slow ops, 18 clusters — **isolated spikes** |

**`DIRECT MEASUREMENT`: in 5 of 8 model-loads there is NO slow extent at all —
the whole model is uniformly slower. Tail behaviour is bimodal: either the run
is uniformly degraded, or a small number of isolated multi-hundred-ms spikes
appear. There is no evidence of a contiguous "bad zone" in the file, and no
per-reader or per-slot concentration (§16, §18).**

## 41. Per-run environment correlations

`DIRECT MEASUREMENT` + `UNAVAILABLE`

Correlations computed: CLIP vs UNET source speed ρ=+0.782 (§39). The remaining
requested correlations (source speed vs restore, vs CLIP forward, vs sampling,
vs pressure) are **UNAVAILABLE**: restore is ~0.2 ms (no variance to correlate),
and pressure/cgroup/PSI are not observable under gVisor (§30).

Stage walls do **not** co-vary with source wall: e.g. `golden_sampling` p50
3882.97 ms with min 3736.37 / max 4394.64 (11% spread) while CLIP source wall
spans 1565-4918 ms (3.1× spread). `SUPPORTED INFERENCE`: the slowdown is
localised to the source/H2D lane, not a whole-container slowdown.

## 42. Fast vs normal vs slow comparison

`DIRECT MEASUREMENT`, baseline cohort by CLIP source wall

| class | run | CLIP wall / GB/s / effQD | UNET wall / GB/s / effQD |
|---|---|---|---|
| FAST | `020348` | 1565.0 / 5.141 / 3.904 | 2371.6 / 5.191 / 3.769 |
| FAST | `015937` | 1661.9 / 4.841 / 3.868 | 2675.0 / 4.602 / 3.806 |
| FAST | `015912` | 1697.1 / 4.740 / 3.811 | 2823.0 / 4.361 / 3.784 |
| NORMAL | `020250` | 1734.5 / 4.638 / 3.864 | 2555.9 / 4.816 / 3.623 |
| NORMAL | `020002` | 1753.9 / 4.587 / 3.927 | 2983.7 / 4.126 / 3.492 |
| NORMAL | `020027` | 1783.6 / 4.510 / 3.849 | 2662.9 / 4.623 / 3.641 |
| NORMAL | `020153` | 2357.1 / 3.413 / 3.896 | 4266.4 / 2.885 / 3.418 |
| SLOW | `020315` | 2400.0 / 3.352 / 3.638 | 6269.3 / 1.963 / 3.066 |
| SLOW | `015816` | 3544.9 / 2.269 / **3.962** | 4664.5 / 2.639 / **3.905** |
| SLOW | `015851` | 4918.1 / 1.636 / **3.977** | 3728.2 / 3.302 / 3.715 |

**`DIRECT MEASUREMENT`: effective QD does not discriminate fast from slow.**
The two slowest CLIP runs have the *highest* effective QD in the cohort
(3.962, 3.977). Throughput varies 3.1× while concurrency stays at 3.6-4.0.
This is the strongest single argument that the next campaign must attack
**per-copy cost**, not scheduling.

M1 Level-1 provided natural additional contrast without sabotage: `035455` was
fast (CLIP 4.697, UNET 5.689 GB/s) and `035604` was slow (2.072 / 2.414 GB/s).

## 43. Source-wall reconciliation

Per 64 MiB extent (CLIP median, M1):

| category | value | class |
|---|---|---|
| authoritative source wall (p50) | 55.99 ms/extent → 6 719 ms busy-union per 120 extents | DIRECT MEASUREMENT |
| copy busy critical path | median 55.99 ms/extent | DIRECT MEASUREMENT |
| source-copy busy union (Σ copy wall, 4 readers) | 37 491 ms over 480 CLIP extents (78.1 ms/extent amortised) | DIRECT MEASUREMENT |
| QD underfill | effective QD 3.882 vs 4 → 3.0% of wall | DIRECT MEASUREMENT |
| slot wait | 188.49 ms total (6 events) | DIRECT MEASUREMENT |
| pacing wait | 36.73 ms (1.77% of wall) | DIRECT MEASUREMENT |
| control/publication gaps | 0.000 ms p50 | DIRECT MEASUREMENT |
| READY/consumer delay | 0.000 ms p50 | DIRECT MEASUREMENT |
| H2D-induced source blocking | **0** (`all_slots_occupied_count=0`, slots 5-7 idle) | DIRECT MEASUREMENT |
| final straggler tail | 0.56-13.13 ms | DIRECT MEASUREMENT |
| off-CPU residual inside copy | 3.80 ms/extent median (~6.8%) | DIRECT MEASUREMENT (10 ms-quantized) |
| **residual** | **UNRESOLVED** — the ~6.8% off-CPU share cannot be split into page service vs runqueue wait under gVisor | UNAVAILABLE |

Non-overlapping control overhead totals ≈2% of source wall; the remaining 98%
is inside the native copy.

## 44. Full-load reconciliation

| component | CLIP p50 | UNET p50 | class |
|---|---|---|---|
| full model-load wall (`golden_*_load` stage) | 1921.14 ms | 3093.69 ms | DIRECT MEASUREMENT |
| pre-source exposed | 107.29 ms (`source_go_offset`) | 18.21 ms | DIRECT MEASUREMENT |
| source critical path (`source_wall_ms`) | 1768.76 ms | 2903.36 ms | DIRECT MEASUREMENT |
| exposed source→GPU tail (`gpu_ready_tail_ms`) | 3.09 ms | 8.38 ms | DIRECT MEASUREMENT |
| model construction (skeleton) | 0.59 ms | 66.17 ms | DIRECT MEASUREMENT |
| views/state-dict (bind_assign) | 9.27 ms | not emitted | DIRECT MEASUREMENT / partial |
| bind/adoption (`storage_adoption`) | 15.02 ms | 12.51 ms | DIRECT MEASUREMENT |
| proofs (`compute_ready_proof`) | 2.14 ms | not emitted | DIRECT MEASUREMENT / partial |
| post-source exposed (non-source envelope) | 120.6 ms | 124.6 ms | DIRECT MEASUREMENT |
| **residual** | source 92.1% of load; non-source 6.3%; remainder is nested/overlapping stage bookkeeping | source 93.8% of load; non-source 4.0% | DERIVED |

Nested intervals are marked: `skeleton_bind_assign` is nested inside
`storage_adoption`-adjacent construction and must not be summed with it.

## 45. Residual unexplained wall

`UNRESOLVED`, quantified bounds:

1. **~6.8% of each source copy is off-CPU** (median 3.80 ms per 55.99 ms CLIP
   extent). Cannot be decomposed further: `ru_minflt`/`ru_nvcsw` are zero,
   `mincore()` lies, `schedstat` unverified.
2. **~3.0% QD underfill** (effective 3.882 vs 4) plus UNET's larger
   `below_four_reader_ms` (p50 417.7, max 2116.3 ms).
3. **The run-level throughput ceiling itself** — CLIP source wall varies 3.1×
   (1565→4918 ms) with QD, offset, reader, slot and pacing all ruled out. This
   is the largest unexplained quantity and is the primary target of the next
   campaign.
4. **CLIP-forward/UNET overlap contribution** — not measured per extent (§34).

## 46. Exact unavailable evidence and why

| metric | mechanism attempted | exact failure | fallback | why no stronger evidence possible |
|---|---|---|---|---|
| minor/major page faults | `resource.getrusage(RUSAGE_THREAD)` | returns 0 on 1216/1216 ops, no error | none | gVisor does not account guest minor faults per thread; the counter is a silent no-op, indistinguishable from "no faults" |
| voluntary/involuntary ctx switches | same | returns 0 on 1216/1216 | none | same implementation gap |
| runqueue wait | `/proc/self/task/<tid>/schedstat` | not verified in M1 | thread CPU (10 ms) | rusage is also zero; a Level-2 run is the only route |
| page residency | `mincore()` | historical: reports all pages resident before access | none; deliberately not called | it returns a confidently wrong value; calling it would corrupt the analysis |
| prefetch/behaviour confirmation | `readahead()` | `EINVAL(22)` | real-access timing | gVisor does not implement it |
| cgroup CPU throttling | `/sys/fs/cgroup/cpu.stat` | historical: unreadable | none | not exposed |
| NUMA topology | `numa_maps`, sysfs | not exposed | none | gVisor virtualizes topology |
| precise thread CPU | `time.thread_time_ns()` | works, but **quantized to 10 ms** (41/41 values are multiples of 10 ms) | ratio bands | clock resolution, not a bug; 288/1216 CPU>wall cases are rounding artifacts |
| CPU migration | `sched_getcpu` | probe implemented, not emitted at Level 1 | none yet | one Level-2 run closes it |
| backing mount / FD numbers | `/proc/self/mountinfo`, `/proc/self/fd` | not collected in M1 | none yet | one Level-2 run closes it |
| UNET per-phase load timing | `unet_load_timing` event | **not emitted by the counted profile** (CLIP-only instrumentation, `golden_serial.py:11426-11504`) | waterfall + total_load envelope | adding it is a small instrumentation change, not an environment limit |
| per-reader H2D submit/complete/release ns | not recorded per extent | absent from the OP record | model-level first/last H2D timestamps exist | would require extending the ring; not done in this milestone |
| GC during source windows | `res4lyf_gc_suppression` events present | not analysed | none | analysis gap, not an environment limit |

## 47. Optimization Surface Inventory

Sorted by **measured removable wall**, not preference. `n/a` = not a wall
surface. Every "historically tested" row cites the ledger.

| # | mechanism | scope | freq | median contribution | p90 | max/tail | removable lower | removable upper | evidence class | confidence | historically tested? | future experiment scope | risk |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Per-extent copy cost ceiling** (the run-level throughput ceiling) | both | every extent | 55.99 ms/extent CLIP, 50.75 UNET | 78.71 / 62.51 | 1421.08 / 1116.19 | **UNRESOLVED** | **UNRESOLVED** | DIRECT MEASUREMENT that it dominates; cause UNKNOWN | high that it dominates, **zero** on cause | no — fresh/whole/preadv/affinity all tested and rejected; the *cause* is still open | identify what makes a whole-run 3.1× slower with QD≈4, no offset/slot/reader/pacing dependence. Needs Level-2 OS evidence + host-side correlation | high: this is the core source path |
| 2 | Off-CPU residual inside the copy | both | every extent | 3.80 ms (6.8% of 55.99) | 10.68 | 101.08 | ~0 | ~3.8 ms/extent (~6.8% of source wall) | DIRECT MEASUREMENT + UNAVAILABLE decomposition | high that it exists, **none** on what it is | partially — pretouch/WILLNEED tested and rejected | one Level-2 run for schedstat/affinity/PSI; do **not** re-test pretouch/readahead | medium |
| 3 | QD underfill (effective 3.88 CLIP / 3.68 UNET vs 4) | both | whole model | 3.0% CLIP / 8.0% UNET of wall | — | UNET `below_four_reader` 2116.3 ms | ~0 | ~3-8% of source wall | DIRECT MEASUREMENT | high | **YES** — QD2/QD6/QD7/QD8 and slot sweeps all measured; higher QD did not add throughput and worsened tails | raising QD is *already known not to work*; the underfill is a symptom, not a lever | medium-high |
| 4 | CLIP first-touch layout resolve | CLIP only | 1 per container | 36.89 ms | — | 362.26 ms | ~36.89 ms | ~362 ms (CLIP load only) | DIRECT MEASUREMENT | high | no | precompute safetensors header/`data_start`/`data_bytes`/tensor map in snapshot; must preserve cache invalidation on model identity change (`:956-962`) and the tensor-offset coverage proof (`:320-342`) | medium: a stale header breaks the storage proof |
| 5 | UNET skeleton construction | UNET only | 1 per model | 66.17 ms | 78.84 | 79.68 | ~0 | ~66 ms (offset by CLIP's cheaper path; net envelope excess is −28.8 ms) | DIRECT MEASUREMENT | high | no | cache/reuse the UNET skeleton across the 3 UNET loads in a request — **but production-006 loads UNET once**, so the win is per-container only | low-medium |
| 6 | `cudaHostRegister` of the 512 MiB arena | both | 1 per container | 495.94 ms | — | 495.94 ms | 0 | ~496 ms if snapshot-creatable (**UNPROVEN**) | DIRECT MEASUREMENT | high that it costs this; **none** that it is removable | partially — pinned-ring and DMA-ring arms exist and are OFF (`dma_ring_enabled=false`) | prove whether the arena can be registered during snapshot instead of per container; it is already overlapped with source-owner spawn | high: async H2D correctness depends on pinned memory |
| 7 | UNET slot wait | UNET | 4-6 events | 293.45 ms total (cohort p50) | — | 861.92 ms | ~0 | ~862 ms worst case | DIRECT MEASUREMENT | medium | **YES** — slot sweeps measured; more slots did not help | `all_slots_occupied_count=0` and slots 5-7 idle ⇒ the arena is oversized for the current H2D rate; this is a *geometry* observation, not a starvation fix | medium |
| 8 | Pacing floor | both | ~15% of extents | 36.73 ms (1.77%) / 55.70 ms (2.32%) | — | — | 0 | ~2% of source wall | DIRECT MEASUREMENT | high | **YES** — zero pacing measured 10-12% worse with worse tails | do not change; it is purchased on purpose | high: removing it regresses throughput |
| 9 | UNET `gpu_ready_tail` / `final_drain` outliers | UNET | 1 occurrence | 8.38 ms p50 | 50.86 | **149.80 / 143.45 ms** | ~0 | ~150 ms worst case | DIRECT MEASUREMENT | medium | partially — H2D aggregation tested, no proven win | single observation; needs more samples before acting | low |
| 10 | `dispatcher_reap_wall_ms` | both | continuous | 61.75 / 76.2 ms | 102.95 / — | 113.52 / 140.5 | n/a | n/a | DIRECT MEASUREMENT | medium | no | runs on the dispatcher thread, not the source critical path; likely overlaps source | low |
| 11 | READY publication | both | every extent | **0.000 ms** | 0.001 | 0.010 | 0 | ~0 | DIRECT MEASUREMENT | high | no | nothing to gain | none |
| 12 | Fresh-mmap branch, pacer-type dispatch, map telemetry bits | both | 304 branch evals/request | ~0 (µs total) | — | — | 0 | ~0 ms | CODE-PROVEN dead under `whole` | high | n/a | code-clarity only; see the legacy audit §11 | low (but loses diagnostic capability) |
| 13 | Per-extent process-safe sync between readers | both | — | **none exists** | — | — | 0 | 0 | CODE-PROVEN (negative result) | high | n/a | nothing to remove | none |

## 48. Long-Tail Removal Surface Inventory

| # | mechanism | tail frequency | worst observed | p95/p99 contribution | affects | evidence | counterevidence | detection signal | possible future mitigation category |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Uniform whole-run throughput degradation** (no slow extent; every extent ~2-3× slower) | **5 of 8 model-loads** | CLIP source 4918.1 ms (3.1× the fast run) | contributes 100% of the excess in those runs | source tail, model-load tail | DIRECT MEASUREMENT: no op >3× median in 5/8 loads; effective QD 3.96-3.98 in the slowest runs; offset CV 0.17 | none found | source wall per run vs per-extent distribution shape | **environment/host correlation** — the cause is outside the loader's control surface; needs host-side telemetry |
| 2 | **Isolated multi-hundred-ms copy spikes** | 1 of 8 loads (21 UNET ops, 18 clusters) | 1421.08 ms single CLIP extent; 1116.19 ms single UNET extent | >p95: 5.0% of ops = 30.9% (CLIP) / 28.8% (UNET) of copy wall; >p99: 1.0% = 15.3% / 14.9% | op tail | DIRECT MEASUREMENT: CPU/wall stays ~0.93 even on the 1421 ms op (1320 ms CPU) | not offset-locked (same offset 97→1421 ms across runs); not reader- or slot-specific (rates flat) | per-op `copy_wall_ns` ≫ run median while CPU/wall stays high | the thread is **busy** during the spike, so it is in-CPU work (page servicing inside `memmove` in gVisor's sentry, or host memory pressure), not descheduling |
| 3 | Reader straggler tail | every run | 25.91 ms (UNET) | ≤1.2% of source wall | reader tail | DIRECT MEASUREMENT: last − 2nd-last completion | — | reader last-completion timestamps | not a real surface; already negligible |
| 4 | UNET post-source drain / gpu-ready tail | 1 occurrence | 143.45 / 149.80 ms | p90 50.86 ms | model-load tail | DIRECT MEASUREMENT | single sample | `final_drain_wall_ms`, `gpu_ready_tail_ms` | needs more samples; H2D completion-event ordering |
| 5 | CLIP first-touch layout resolve | 1 per container | 362.26 ms | CLIP load only | model-load tail (first request) | DIRECT MEASUREMENT: `layout_cache_hit=false` for CLIP, `true` for UNET | UNET is 0.67 ms because it hits cache | `layout_cache_hit` | snapshot precompute (#4 in §47) |
| 6 | Contiguous bad file zones | **0 observed** | — | — | — | DIRECT MEASUREMENT: no contiguous slow-offset cluster across 4 runs | — | within-offset CV would stay high if zones existed | none — the hypothesis is not supported |
| 7 | Per-slot / per-reader slow work | **0 observed** | — | — | — | DIRECT MEASUREMENT: slow-op rate flat across readers (2.5-4.2%) and slots 0-4 (1.5-5.2%) | — | per-slot/per-reader slow rates | none — not a surface |

## 49. Raw artifact index

`reports/m1_loader_forensics/`

| file | contents |
|---|---|
| `HISTORICAL_EVIDENCE_LEDGER.md` | 15 already-answered mechanisms re-judged for thread+whole; no-repeat list |
| `SCHEDULER_AND_HOT_PATH_AUDIT.md` | call graph, 12 scheduler answers, lock graph + 3 proofs, GIL analysis, 32/64 MiB resolution |
| `LEGACY_MACHINERY_REMOVAL_AUDIT.md` | legacy/dead-code audit A-M with measured cost ledger and fact block |
| `GVISOR_OBSERVABILITY_MATRIX.md` | availability matrix, exact failures, fallbacks, 10 ms clock caveat |
| `source_operations.csv` | **1216 per-extent records**: ordinal, reader, thread, slot, offset, nbytes, memcpy start/end, ready, thread-CPU start/end, off-CPU, slot/pacing/claim waits, rusage, map/munmap, effective concurrency |
| `unet_overlap_buckets.csv` | all 736 UNET extents classified before/during/after the real CLIP transformer-forward interval, with wall/CPU/offset/reader |
| `gvisor_observability.json` | machine-readable availability matrix with exact per-surface results and error text from the Level-2 probe |
| `model_loads.csv` | 20 model loads (10 runs × 2 roles) with full scalar telemetry |
| `run_summary.csv` | per-run CLIP/UNET source wall, GB/s, effective QD, slot wait, UNET excess |
| `m1_level1_runs.json` | M1 Level-1 run summaries incl. the in-container `operations_probe` |
| `environment_samples.csv` | source-owner PID, worker kind, reader identities/tids, startup/register marks |
| `mapping_metadata.json` | baseline/diagnostic identities, byte and op-count facts |

Upstream raw artifacts (unmodified):
`.slim/worktrees/production-006/.v2ctl/runs/*.json` (10 clean cohort receipts),
`.slim/worktrees/production-006/artifacts/phase_p1_parallel_golden_v1/cohort_*/attempt_0.json`,
`.slim/worktrees/m1-loader-forensics/.v2ctl/runs/*.json` (M1 receipts),
`.slim/worktrees/m1-loader-forensics/artifacts/phase_p1_parallel_golden_v1/cohort_*/attempt_0.json`.

---

## FINAL FACT BLOCK

```text
PRODUCTION-006 BASELINE = tag production-006 @ 42cf4d048a8dbc66535753a857cc5cd99135f074
                          deploy 1b0e49ea, Testing 9 / ws_ee7221847f7d, H100! / 12 CPU / 24576 MiB
DIAGNOSTIC COMMIT       = diag/m1-loader-forensics in .slim/worktrees/m1-loader-forensics
DIAGNOSTIC DEPLOYMENT   = app batch-c0-source-h100-m1, final deploy aefe3302696ab83f449f786b17b9ec9a2499156e69ea885c1fabb5f43a8776b6,
                          Testing 9, source-probe PASS/MATCH
                          zero COMFYMODAL_GOLDEN_*/COMFYMODAL_V2_* flag differences vs production-006
TOTAL EXISTING RUNS ANALYZED = 10 (clean production-006 cohort, all valid, 10/10 exact SHA)
NEW LEVEL-1 RUNS       = 7 requests (4 with full per-extent records; 3 retained as env-delivery evidence)
NEW LEVEL-2 RUNS       = 1 request (deploy aefe3302, run run_20260930-042450_28704bbe) - closed all
                          remaining environment questions
NEW LEVEL-3 RUNS       = 0 (deliberately not run; see §24)

CLIP SOURCE MEDIAN     = 1768.76 ms   (p90 3682.23, worst 4918.10)
CLIP SOURCE P90        = 3682.23 ms
CLIP SOURCE WORST      = 4918.10 ms   (1.636 GB/s)
UNET SOURCE MEDIAN     = 2903.36 ms   (p90 4824.97, worst 6269.34)
UNET SOURCE P90        = 4824.97 ms
UNET SOURCE WORST      = 6269.34 ms   (1.963 GB/s)

CLIP EFFECTIVE QD MEDIAN = 3.882  (configured 4, max observed 4, no end-of-model collapse)
UNET EFFECTIVE QD MEDIAN = 3.678  (configured 4, max observed 4, no end-of-model collapse)
CLIP FRACTION AT QD4     = 0.908
UNET FRACTION AT QD4     = 0.860

CLIP STRAGGLER TAIL MEDIAN = 7.34 ms   (range 0.56-13.13; <=0.9% of source wall)
UNET STRAGGLER TAIL MEDIAN = 4.20 ms   (range 0.56-25.91; <=1.2% of source wall)

PAGE-SERVICE CONTRIBUTION = UNRESOLVED as a separable quantity.
                             What IS measured: the thread is CPU-active for a median
                             93.8% (CLIP) / 94.2% (UNET) of every copy, so the copy is
                             CPU/memcpy-dominated, not blocked on storage. The ~6% residual
                             (3.80 / 3.18 ms per extent) cannot be split into page service
                             vs runqueue wait because ru_minflt/ru_nvcsw are silent zeros,
                             mincore() lies, and schedstat is unverified.
MEMCPY CONTRIBUTION       = ~93.8% (CLIP) / ~94.2% (UNET) of per-extent copy wall, CPU-active.
                             Median copy 55.99 ms (CLIP) / 50.75 ms (UNET) per 64 MiB.
                             CAVEAT: thread-CPU clock is 10 ms-quantized; 288/1216 CPU>wall
                             cases are rounding artifacts.
SCHEDULER/CONTROL CONTRIBUTION = ~2% of source wall. READY publication 0.000 ms p50 (max 0.010);
                             slot wait 188-199 ms per model (4-6 events); capacity wait 0 (never blocked);
                             QD underfill 3.0% (CLIP) / 8.0% (UNET).
SLOT/H2D BACKPRESSURE CONTRIBUTION = 0 as a cause of slow extents. Capacity pressure is REAL for UNET
                             (all_slots_occupied_count 21/625/654/681 in 4/7 M1 runs) but is absorbed without
                             slowing copies (CPU/wall 0.93-1.01); it is 0 on 10/10 production-006 cohort runs.
                             Slots 5-7 carry only 4-11% of fills; H2D is 6-7% of source wall, fully hidden.
PACING CONTRIBUTION       = 1.77% (CLIP, 36.73 ms) / 2.32% (UNET, 55.70 ms); 0 violations in 14 runs.

UNET BYTE-PROPORTIONAL EXPECTED WALL = 2903.36 x 1.5301 relationship; per-run median expected
                             = clip_source_wall x 1.5301
UNET ACTUAL WALL          = 2903.36 ms (median)
UNET EXCESS WALL          = +54.5 ms median (p90 +853.5, min -3797.2, max +2597.0)
UNET EXCESS ATTRIBUTED    = CLIP-forward overlap ~2.3% of median extent wall (measured: 50.84 ms during vs
                             49.70 ms after, ratio 1.0229; 100% of UNET extents overlap CLIP forward in 3/4 runs)
                             + effective-QD difference (~5% lower concurrency) + larger below-four-reader time
                             (p50 417.7 / max 2116.3 ms) + UNET slot-capacity pressure (absorbed) + marginally higher
                             pacing. GPU allocation / views / bind / adoption are RULED OUT (non-source excess
                             = -28.8 ms, i.e. UNET is not worse). H2D backpressure RULED OUT as a cause of slow
                             extents. Ruled out as causes: reader straggler (<=1.2%), offset dependence
                             (within-offset CV 0.17), slot dependence.
UNET EXCESS UNRESOLVED    = the dominant term is NOT UNET-specific. Spearman rho(CLIP GB/s, UNET GB/s)
                             = +0.782 within-run: both models slow down together. CLIP-forward overlap is now
                             MEASURED at ~2.3% and is no longer a leading candidate. UNRESOLVED: the identity of
                             the per-request environmental throughput ceiling, and whether CLIP forward affects
                             H2D/bind (those per-op timestamps were not collected).

TOP MEASURED REMOVABLE COST #1 = CLIP first-touch layout resolve — 36.89 ms median, 362.26 ms max,
                             CLIP load only. Snapshot-precomputable; must preserve cache invalidation
                             on model identity change and the tensor-offset coverage proof.
TOP MEASURED REMOVABLE COST #2 = UNET skeleton construction — 66.17 ms median, 79.68 ms max, UNET only.
                             Net non-source excess vs CLIP is -28.8 ms, so this is redistribution,
                             not net cost; and production-006 loads UNET once per request.
TOP MEASURED REMOVABLE COST #3 = cudaHostRegister of the 512 MiB arena — 495.94 ms, once per container,
                             already overlapped with source-owner spawn. Removability UNPROVEN (async
                             H2D requires pinned memory).

TOP LONG-TAIL OWNER #1 = uniform whole-run throughput degradation. 5 of 8 model-loads had NO extent
                             exceeding 3x the run median: the entire model is uniformly slower.
                             CLIP source spans 3.1x (1565->4918 ms) with effective QD 3.6-4.0 throughout.
TOP LONG-TAIL OWNER #2 = isolated in-CPU copy spikes. >p95 = 5.0% of extents but 30.9% (CLIP) / 28.8%
                             (UNET) of total copy wall; worst single extent 1421.08 ms with 1320 ms of
                             thread CPU (CPU/wall 0.93) — the thread is BUSY, not descheduled.
TOP LONG-TAIL OWNER #3 = UNET post-source drain / gpu-ready tail outliers — 143.45 / 149.80 ms,
                             single occurrence each. Under-sampled.

SOURCE WALL RECONCILIATION RESIDUAL = ~6.8% off-CPU inside each copy (UNRESOLVED decomposition)
                             + ~3.0% QD underfill. All other categories measured and small.
FULL LOAD RECONCILIATION RESIDUAL = source is 92.1% (CLIP) / 93.8% (UNET) of model-load wall;
                             non-source envelope 120.6 / 124.6 ms median. Remainder is nested
                             stage bookkeeping, not unexplained work.

HIGH-VALUE UNRESOLVED QUESTION #1 = What causes a whole-request 3.1x throughput swing with effective
                             QD at 3.96-3.98, no offset/slot/reader/pacing dependence, no end-of-model
                             QD collapse, and no measurable CLIP-forward contention? This is the largest
                             single unexplained quantity in the loader. The Level-2 probe proved that NO
                             in-guest surface can explain it: schedstat absent, PSI absent, cgroup absent,
                             sched_getcpu absent, mincore false, faults/context-switches silently zero.
                             Answering it requires provider/host-side telemetry outside this container.
HIGH-VALUE UNRESOLVED QUESTION #2 = What is the mechanism behind the ~6% off-CPU residual inside each copy?
                             It cannot be split into page service vs runqueue wait under gVisor
                             (ru_minflt/ru_nvcsw silent zeros, mincore() false, schedstat unverified,
                             thread CPU 10 ms-quantized).
                             [The former Q#2 — CLIP-forward/UNET overlap contribution — is now CLOSED and
                             MEASURED at ~2.3% of median extent wall; see §34.]
HIGH-VALUE UNRESOLVED QUESTION #3 = Does CLIP forward degrade H2D or bind on the UNET critical path?
                             Source-side contention is measured at ~2.3%, but per-extent H2D
                             submit/complete and bind timestamps were never recorded, so the non-source
                             side of the overlap question remains open.
```

### Coverage-gate status for the 35 required questions

MEASURED: 1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 20, 23, 27 (GC), 30, 31, 32, 33 (transition), 34 (overlap), 35.
CODE-PROVEN: 8, 11, 12, 19, 21, 35.
DERIVED: 1, 2, 11, 12.
CORRELATED: 29 (ρ=+0.782), 33, 34 (ρ=−0.258, n=4).
UNAVAILABLE-IN-ENVIRONMENT: 13, 14, 15, 17, 18, 29 (partial), §46 items.
UNRESOLVED-AFTER-EXHAUSTIVE-ATTEMPT: 11 (partially — `unet_load_timing` not emitted by
the counted profile), 16 (NUMA — not exposed), 22 (per-extent H2D submit/complete/release),
45, and the three high-value questions above.

**Every environment question is now closed**, each by a direct measurement rather
than an assumption (Level 2, deploy `aefe3302`):

| question | verdict | exact mechanism + failure |
|---|---|---|
| Q13 runqueue wait | UNAVAILABLE-IN-ENVIRONMENT | `/proc/self/task/<tid>/schedstat` → `FileNotFoundError`, all 16 tids |
| Q14 page faults | UNAVAILABLE-IN-ENVIRONMENT | `rusage` returns 0 on 1216/1216; `/proc/self/task/<tid>/status` context switches also 0 |
| Q15 residency | UNAVAILABLE-IN-ENVIRONMENT | `mincore()` historically false; `smaps_rollup` → `FileNotFoundError` |
| Q16 NUMA | UNAVAILABLE-IN-ENVIRONMENT | no surface exposed |
| Q17 topology | UNAVAILABLE-IN-ENVIRONMENT | no physical topology; 28 logical CPUs only |
| Q18 cgroup/pressure | UNAVAILABLE-IN-ENVIRONMENT | PSI ×3, `cpu.stat`, `memory.current`, `*.pressure` ×2 all `FileNotFoundError` |
| Q28 CPU migration | UNAVAILABLE-IN-ENVIRONMENT | `os.sched_getcpu` absent from the module |
| Q38 mount metadata | MEASURED via fallback | `mountinfo` opens but has 0 model lines; exact `os.stat` captured instead |
| Q23 GPU alloc | MEASURED | `cudaHostRegister` 495.94 ms, reused for UNET |
| Q27 GC | MEASURED, closed | `intercepted_collect_count = 0` |
| Q33 transition | MEASURED, closed | same PID + same 4 tids, 7/7 |
| Q34 overlap | MEASURED, closed | ~2.3% median penalty |

**Closed since the first issue of this report** (all from existing artifacts, zero
additional GPU spend):
- Q27 GC interference → **MEASURED, closed**: `intercepted_collect_count = 0` on
  every run; no GC collection occurred during any source window.
- Q33 CLIP→UNET transition → **MEASURED, closed**: one source-owner PID and the
  same 4 reader tids span both models (7/7); ownership quiescent and unpoisoned
  at the boundary (7/7); release counts exactly match op counts (120/184).
- Q34 CLIP-forward/UNET overlap → **MEASURED, closed**: 100% of UNET extents
  overlap CLIP forward in 3/4 runs; median penalty 2.3% (50.84 vs 49.70 ms).

**Corrections made to earlier sections as a result:** §18 and §32 previously
stated `all_slots_occupied_count = 0` universally. The transition census shows it
is non-zero for UNET in 4/7 M1 runs (21/625/654/681). Both numbers are now
reported; the substantive conclusion (backpressure does not cause slow extents)
is unchanged and now rests on the CPU/wall evidence rather than on absence of
capacity pressure.
