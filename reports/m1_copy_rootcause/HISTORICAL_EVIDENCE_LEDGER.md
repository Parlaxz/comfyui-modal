# M1 HISTORICAL EVIDENCE LEDGER

Purpose: guarantee this campaign never unknowingly repeats an already-answered
experiment, and record which historical conclusions still apply to the
production-006 runtime.

## 0. Applicability correction (READ THIS FIRST)

**CODE-PROVEN.** production-006 runs, inside the single CUDA-sterile source-owner
process, **four reader THREADS** (`c0-source-0..3`, native tids 64/65/66/67) and a
**whole-file `MAP_PRIVATE` mapping installed once per model generation**.

Evidence: `source_concurrency`-bearing artifacts of the frozen 10-run cohort,
`source_detail.arena_ensure.child_ready_evidence` →
`{"architecture":"source_owner","source_worker_kind":"thread","workers_configured":4,"workers_ready":4,
"reader_identities":[{"reader_id":0,"name":"c0-source-0","thread_id":64}, ... {"thread_id":67}],
"process_id":62,"mmap_lifecycle":"whole","fallback":false}`.

**The dominant historical ledger was produced on a DIFFERENT architecture.**
`SOURCE_IO_EXPERIMENT_LEDGER.md` describes *"4 reader processes, persistent FD,
eager workers, self-service allocator, fresh 64 MiB MAP_PRIVATE windows"*
(ledger lines 96-101, `FINAL_MAPSHARE_CPU_REPORT.md:1-6`).

Consequence: every row below is re-judged against the **thread + whole** runtime,
not against its own historical baseline. Several rows that the historical ledger
marked `YES` are downgraded to `PARTIAL` or `NO` for production-006. This is the
single most important correction in this document.

| production-006 fact | value | evidence class |
|---|---|---|
| source-owner processes | 1 | DIRECTLY MEASURED (child_ready_evidence.process_id, single pid 62) |
| reader processes | 0 | DIRECTLY MEASURED (worker_kind=thread) |
| reader threads | 4 | DIRECTLY MEASURED (workers_ready=4, tids 64-67) |
| mmap lifecycle | whole | DIRECTLY MEASURED (mmap_lifecycle=whole) |
| per-extent mmap/munmap executed | 0 | DIRECTLY MEASURED (`mmap_map_count=0`, `mmap_unmap_count=0` on 10/10 runs, both roles) |
| source ops CLIP / UNET | 120 / 184 | DIRECTLY MEASURED (h2d_submitted_count) |
| slot bytes | 67108864 (64 MiB) | DIRECTLY MEASURED (slot_bytes, h2d_max_submission_bytes) |
| QD target | 4 | DIRECTLY MEASURED (source_qd_target=4) |
| arena | 536870912 (512 MiB), 8 slots | DIRECTLY MEASURED (arena_bytes, slot_count) |

## 1. Mechanism ledger — do-not-repeat list

| # | Mechanism / question | Evidence + date | Architecture it was measured on | Samples | Exact result | Applies to production-006? | Why |
|---|---|---|---|---|---|---|---|
| 1 | Fresh vs Whole mmap lifecycle | `SOURCE_IO_EXPERIMENT_LEDGER.md:10-16,27,105-108`; `ABC_MMAP_LIFECYCLE_REPORT.md:137-143`; production-006 tag message | Fresh-window readers | M1 cohort; A n=8 / B n=7 / C n=8 | `whole` 6.2-6.4 GB/s vs `fresh` 0.145-1.597 GB/s; production-006 single-variable contrast: whole 6.4/6.2 vs fresh 0.145-1.597 GB/s, identical output SHA, valid=true, fallback=0 | **YES (settled, closed)** | production-006 IS the `whole` arm. The question is answered and is the reason the tag exists. Re-testing would re-open a closed catastrophic bug. |
| 2 | preadv vs mmap | `SOURCE_IO_EXPERIMENT_LEDGER.md:22,46-49,78`; `SOURCE_IO_LEDGER.md:52-66` | 4 reader **processes**, QD4, 64 MiB, 4 ms | n=27 counted; later n≈42 | preadv median 5.487 GB/s; frozen median 5.818 GB/s vs control ~6.015 GB/s | **PARTIAL** | Same host class and geometry, but measured on the *process* topology. The thread+whole path was not the subject. Ranking is suggestive, not dispositive. |
| 3 | MAP_SHARED vs MAP_PRIVATE | `FINAL_MAPSHARE_CPU_REPORT.md:17-90` | H100, 4 readers, QD4, 64 MiB, 4 ms | 15 counted/arm; 1800 ops/arm | PRIVATE 6.224 GB/s vs SHARED 5.506 GB/s (−12.1%); ops ≥100 ms: 8 vs 102; CV 0.1520 vs 0.2504 | **NO for further testing** | Decisively rejected, and the production mapping is MAP_PRIVATE. No reason to spend a run. |
| 4 | Slot-count sweeps | `SOURCE_IO_EXPERIMENT_LEDGER.md:86-89`; `SIZE_SWEEP_REPORT.md` | H100 fresh mmap, QD4/6/8, 32/64/128/256 MiB | 12 cells × 20 | Throughput flat 5.36-6.15 GB/s. Higher QD worsened tails: 256 MiB 30%→90%→100% QD6→QD8 | **PARTIAL** | Geometry is inside the measured matrix, but on fresh+process. production-006 is whole+thread at 8×64 MiB. |
| 5 | QD2 / QD8 | `SOURCE_IO_EXPERIMENT_LEDGER.md:46-49,86-88`; `qd_sweep_runs/REPORT.md`; `qd_compare_runs/REPORT.md` | historical source cohorts; H100 matrix | matrix n=20/cell | QD5 −1%, QD6 −9%, QD7 −7%, QD8 pathological. Effective concurrency tracked configured QD (3.9/5.8/7.6) without throughput gain | **PARTIAL** | Direction (higher QD does not add throughput, adds tails) is consistent with what this campaign measures directly. Exact numbers are not transferable. |
| 6 | 4 ms pacing vs zero | `SOURCE_IO_EXPERIMENT_LEDGER.md:91-92`; `pace_runs/`; `task5_pacing/` | H100, 64 MiB, QD4, fresh mmap | 30 balanced rounds; 15 counted/arm | P0 5.592, P2 6.179, P4 6.287 GB/s; ops ≥250 ms: P0 11, P2 0, P4 0. Zero pacing ~10-12% worse with worst tails | **PARTIAL** | Confirms the floor is worth its cost, measured on fresh+process. This campaign MEASURES the enforced floor in the thread+whole path instead of re-testing it. |
| 7 | 128/256 MiB geometry | `SOURCE_IO_EXPERIMENT_LEDGER.md:81-87`; `SIZE_SWEEP_REPORT.md` | H100 fresh-window mmap | n=6/size; matrix n=20/cell | 128 MiB 5.351 GB/s CV 0.193; 256 MiB 5.581 GB/s CV 0.177 but 26 ops ≥250 ms | **PARTIAL** | Already answered on a sibling architecture. |
| 8 | Pretouch / page touching | `SOURCE_IO_EXPERIMENT_LEDGER.md:25,56`; `step2_touch/` | mmap source path, native toucher | n not stated in ledger | T1/T2 3.568/3.717 GB/s vs T0 5.295 GB/s; T2 max 1045.5 ms, READY_AHEAD=0 | **PARTIAL** | Negative result is strong and mechanistically relevant (touching adds contention). Not re-run. |
| 9 | WILLNEED / readahead / MAP_POPULATE | `SOURCE_IO_EXPERIMENT_LEDGER.md:10-15,27,105-108` | gVisor `4.19.0-gvisor` | M1 cohort | `MADV_WILLNEED` cold first touch 24.7 vs 27.0 ms (inert); `readahead()` **EINVAL(22)**; `MAP_POPULATE` accepted but does not materialise; 64 MiB mapping in 4.8 ms | **YES (environment limit)** | Directly transferable: it is a property of this gVisor runtime, not of the reader topology. |
| 10 | CPU affinity / pinning | `SOURCE_IO_EXPERIMENT_LEDGER.md:99,116-117`; `aff_fva_report/AFF_FVA.md` | H100, 4 readers, gVisor, 28 logical CPUs | 15 counted/arm | Unpinned 5.550 vs pinned 5.534 GB/s (−0.3%); matched −1.7%. Topology unavailable under gVisor | **PARTIAL** | No clean gain, and physical topology is unprovable in this environment. |
| 11 | Processes vs threads as readers | `SOURCE_IO_EXPERIMENT_LEDGER.md:49`; `SOURCE_IO_LEDGER.md:14`; `worker_model_runs*/REPORT.md` | historical source readers | n not stated | Threads→4 processes: +10-12% median. 8-process/4 MiB topology 25-33% worse | **NO (historical premise inverted)** | production-006 deliberately runs **threads**. The historical "+10-12% for processes" finding is the exact reason the reader topology is a live question, but re-running the A/B is a *new* optimization experiment, out of scope for this forensics milestone. |
| 12 | Direct-pinned / zero-copy redesign | `SOURCE_IO_EXPERIMENT_LEDGER.md:26,53-55`; `step5_zerocopy/`; `V2_BATCH_C6_PINNED_RING_*` | H100/RTX, mmap vs pinned destination | D0/D1/D2 n not stated; C6 separate | D2 zero-copy 4.686 vs M0 5.621 GB/s (−16.6%); D1 invalid (read 1 byte/64); pinned vs pageable ≈1% | **PARTIAL** | Tested and not a production win on sibling paths. |
| 13 | H2D aggregation | `SOURCE_IO_EXPERIMENT_LEDGER.md:54,72-74`; `V2_BATCH_C6_*`; `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md:177-186` | UNET/CLIP transport, H100/RTX | report-specific | Persistent registered arena makes H2D cheap; no proven aggregate-transfer win | **PARTIAL / partially moot** | production-006 runs `aggregated_submission_count=0` and `non_aggregated_submission_count=120` — aggregation is OFF and every extent is its own H2D. This campaign MEASURES the consequence instead of re-testing the mechanism. |
| 14 | Deferred munmap | `SOURCE_IO_EXPERIMENT_LEDGER.md:93`; `du_runs/`; `FINAL_MAPSHARE_CPU_REPORT.md:190-203` | H100, 64 MiB, QD4, 4 ms | P4 n=20 vs DU n=25; 2400 ops | Source-ready 5.650 vs 5.642 GB/s; drain penalty 2.24 ms; matched P4 6.331 vs DU 5.853 GB/s (−7.5%) | **NO** | Structurally moot: `mmap_map_count=0` and `mmap_unmap_count=0` on 10/10 runs — there is no per-extent mapping to defer. |
| 15 | Duplicate Whole mappings | `SOURCE_IO_EXPERIMENT_LEDGER.md:31-35`; `ABC_MMAP_LIFECYCLE_REPORT.md:1-7,137-143` | H100 + CPU cross-check | A n=8, B n=7, C n=8 | Whole A 5.657 GB/s, 0 ops ≥250 ms, CV 0.228; fresh C 5.535 GB/s, CV 0.098 | **NO** | production-006 already has exactly one whole mapping per generation. Nothing to duplicate. |

## 2. Prior measurements of questions this campaign would otherwise rebuild

| Question | Prior evidence | Result | Class |
|---|---|---|---|
| (a) per-reader throughput / imbalance | `exp1_telemetry/DECOMPOSITION.md:1-4`; `allocator_runs/AB_CONCLUSIONS.md:40`; `aff_fva_report/AFF_FVA.md` | Static/greedy assignment usually exactly balanced `[15,15,15,15]` in 21/30 runs; QD4 `[30,30,30,30]` in 18/30. Dynamic rebalancing never engaged because no reader was materially faster | HISTORICAL, different architecture |
| (b) effective QD collapse at end of model | `SOURCE_IO_EXPERIMENT_LEDGER.md:86-89`; `qd4_distribution/FINAL_REPORT.md`; `RX1_QD4_TELEMETRY_REPAIR_REPORT_2026-08-31.md` | Effective concurrency ≈3.9/5.8/7.6 for configured QD4/6/8. Real QD, no throughput scaling, worse tails at higher QD | HISTORICAL. **This campaign measures the thread+whole QD integral directly and does not rely on it.** |
| (c) page-service vs memcpy split | `FINAL_MAPSHARE_CPU_REPORT.md:94-185`; `SOURCE_IO_EXPERIMENT_LEDGER.md:96` | **Most valuable prior row.** 1800/1800 ops had CPU data: median memcpy wall 39.799 ms vs thread CPU 40.000 ms, CPU fraction 0.9449; aggregate CPU/wall across 4 readers 3.504 (~100% of 4 cores). `mincore()` falsely reported all pages resident; gVisor fault counters 0/0 | HISTORICAL + environment limits that transfer |
| (d) CLIP-forward vs UNET-load contention | `V2_CLIP_UNET_OVERLAP_REPORT.md:109-155`; `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTION.md:45-46,115` | Overlap 89.4-90.0%. Concurrent CLIP encode +39-62%; UNET H2D +17.8-23.2%; bind +6.7-9.7x. Pre-sampling critical path still improved 12.7-23.4% | HISTORICAL |
| (e) why UNET costs more than byte-proportional CLIP | `V2_CLIP_UNET_OVERLAP_REPORT.md:144-155`; `V2_UNET_READ_H2D_OVERLAP_RESEARCH.md:91-110`; `E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:69` | Representative UNET: read 1199-1372 ms, bind 125.5-180.3 ms, H2D 2503-2619 ms, total 4297-4368 ms; UNET variance 0.8-18.5 s vs QD read ≈1.15 s | HISTORICAL. **This campaign recomputes the excess term from the frozen cohort and from new per-op data.** |
| (f) straggler / tail analysis | `SOURCE_IO_EXPERIMENT_LEDGER.md:22-35,65-71,78-101`; `cross_source_runs/DELIVERABLE.md:185-221` | Tails are region/provider sensitive; M0 rescue produced 0 meaningful escapes in 53 events ≥1 s; whole mmap 0 ops ≥250 ms in n=8 | HISTORICAL |
| (g) cgroup / CPU pressure correlation | `COMFYUI_MODAL_V2_AUG9_RESOURCE_GPU_OPTIMIZATION_REPORT.md:42-44,68,83,158-160,237`; `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTENTION.md:45,80,105-115` | H100 peak p50 8.5 against an 8-core quota in one matrix; no recurring throttling elsewhere. `cpu.stat` unreadable. Reading 12.3 GB moved cgroup memory only +230..325 MB | HISTORICAL + environment limit |
| (h) gVisor observability limits | `SOURCE_IO_EXPERIMENT_LEDGER.md:5-16,96,99`; `FINAL_MAPSHARE_CPU_REPORT.md:96-100` | `MADV_POPULATE_*` and `readahead()` → EINVAL(22); `MAP_POPULATE` inert; `mincore()` all-resident; fault counters 0/0; `thread_time_ns()`/`process_time_ns()` can be permanently zero; `cpu.stat` unreadable; CPU topology unavailable. Working alternatives: real-access timing, `CLOCK_THREAD_CPUTIME_ID`, process ticks, explicit `/proc/self/maps` | HISTORICAL + **directly reusable fallback list** |

## 3. Evidence-quality warnings carried forward

- `SOURCE_IO_EXPERIMENT_LEDGER.md:46-58` states several results with no sample count
  and incomplete hardware detail. Treat as **directional**, not production-grade A/B.
- The affinity cohort explicitly lacks physical topology under gVisor
  (`SOURCE_IO_EXPERIMENT_LEDGER.md:99`).
- Historical raw QD and 40-45 GB/s E27 figures are **not** comparable to
  integrated cold-loader throughput (`E38_01_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:37,196`).
- `ABC_MMAP_LIFECYCLE_REPORT.md:189-199` warns its A/B/C cohort had incomplete
  coverage and region concentration.
- The two pre-existing local test failures
  (`tests/test_rx9p_h_identity_chain.py::test_success_path_exact`,
  `::test_compact_nested_sage_observation_is_mismatch`) reproduce **identically on
  the pristine production-006 worktree** and are environment-dependent identity
  assertions (empty `arm`/`app` fields). They are not caused by M1 instrumentation.

## 4. Bottom line — no-repeat list for this campaign

Do **not** spend a run on: Fresh mmap, preadv, MAP_SHARED, slot sweeps, QD2/QD8,
zero pacing, 128/256 MiB geometry, pretouch, WILLNEED/readahead, CPU affinity,
process-vs-thread A/B, direct-pinned/zero-copy, H2D aggregation, deferred munmap,
duplicate Whole mappings.

Instead of re-testing them, this campaign **measures their consequences inside the
production-006 thread+whole runtime**: the enforced 4 ms floor, the QD4
occupancy integral, slot scarcity, the H2D tail, and the per-extent copy cost.
