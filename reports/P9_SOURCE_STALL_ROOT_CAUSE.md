# Production 009 — Pathological Source Copy Stalls: Root Cause

## 1. Exact source and deploy identity

| item | value |
|---|---|
| starting SHA | `95e90b26bb739080884009ba7189a93b334cfac8` |
| lane | `.slim/worktrees/p8fix` (clean, detached) |
| instrumentation commit | `dce3c4ac` |
| diagnostic profile commit | `28506a03` |
| child-launch fix commit | `cfee2acf` |
| flag-plumbing fix commit | `975aec14` |
| profile | `golden_p1_parallel_p9opt1_source_diag_h100` |
| app | `batch-p9opt1-diag-h100` (isolated; `batch-p9opt1-h100` and `batch-p9opt1-prof` untouched) |
| deploy fingerprint | `a556c13683c691b0eb4ce04b82111d7d34c92f921b2b8b3f089dc2e7e2f3e005` |
| source identity | `verdict=MATCH`, `RESULT=PASS`, all 16 required modules byte-identical |
| GPU / CPU | `H100!` / `CPU=12`, memory 24576 MB |
| source path | whole mmap lifecycle, thread owner, 4 readers, 64 MiB blocks, 16 x 64 MiB arena |
| exact output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` (10/10) |

Two production defects were found and fixed en route, both of which had silently
disabled the diagnostic. They are recorded here because they are the reason an
earlier attempt produced no usable evidence.

1. **The source owner is launched as a standalone script**
   (`python .../golden_source_threads.py --source-child ...`), so it is
   `__main__` with no parent package. The relative import added by `dce3c4ac`
   raised `ImportError` in the child, which died before emitting READY, and
   because the child's `stderr` is a pipe nobody drains, the only symptom was a
   silent `source_process_exited_before_ready` during restore — a crash loop on
   H100. Fixed in `cfee2acf`.
2. **A Golden control flag must be declared in three places**, and the probe was
   declared in two. `_runtime_env()` in `modal_app.py` is a hand-written
   allowlist that becomes Modal's class-level `env=`; anything missing from it
   never reaches the container. The probe therefore stayed inert, reported
   itself unavailable, and `copy_wall_ns` stayed 0 so the reported wall silently
   fell back to the wider `memcpy_end - memcpy_start` span. Fixed in
   `975aec14`, with `tests/test_golden_flag_reaches_container.py` requiring the
   three declarations to agree (confirmed to fail when the passthrough is
   removed).

## 2. Local tests

- `tests/test_source_copy_probe.py` — 35 synthetic tests: rusage/thread-CPU
  deltas, sentinel-vs-zero, fail-soft, all five classifications, every stall
  threshold, top-8 ordering and cap, zero-CPU ratio guard, per-reader/model
  summaries preserved, old telemetry fields unchanged, and a recursive
  assertion that no list in compact telemetry exceeds 8 entries.
- `tests/test_source_child_script_launch.py` — executes the module the way
  production does; proves a relative import genuinely fails under the child's
  `__main__` conditions while `_load_probe_module()` resolves.
- `tests/test_golden_flag_reaches_container.py` — the three-layer flag gate.
- Source suites: **161 passed**, 6 skipped. `fast_unit`: **609 passed**,
  unchanged, with only the two pre-existing `test_rx9p_h_identity_chain`
  failures (`INCOMPLETE` vs `MISMATCH`), which reproduce identically on a
  pristine `production-007` tree.

**Instrumentation overhead:** measured **1.2 µs per 64 MiB block** (p50, 20 000
iterations), 833x below the 1 ms/block ceiling and ~0.3 ms per model. The probe
cannot account for a stall it observes.

## 3. Ten-run validity

All ten requests were run serially and never concurrently.

| check | result |
|---|---|
| `valid` | 10/10 |
| `dnf` | 0/10 |
| `true_cold` | 10/10 |
| exact output SHA | 10/10 |
| `failures` | none |
| structurally invalid / excluded | none |

**No run was discarded.** Runs 3, 6, 7 and 10 reproduced the pathological
regime and are kept precisely because they are pathological.

## 4. Source wall distribution

| # | request ms | clip_load | clip_forward | unet_load | sampling | vae_load | vae_decode | src wall ms | src GB/s |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 16000.8 | 1649.4 | 2575.1 | 2502.1 | 3739.4 | 619.6 | 499.7 | 1535.1 | 5.241 |
| 2 | 19516.4 | 1953.3 | 2919.5 | 2998.0 | 3922.9 | 483.3 | 550.6 | 1817.4 | 4.427 |
| 3 | 21889.4 | 3070.6 | 2797.7 | 2637.3 | 3836.1 | 395.7 | 536.5 | 2906.5 | 2.768 |
| 4 | 14110.5 | 1404.5 | 1948.0 | 1874.2 | 3626.2 | 301.0 | 467.9 | 1282.7 | 6.272 |
| 5 | 57165.9 | 1896.9 | 3163.8 | 2897.5 | 4170.3 | 582.4 | 691.4 | 1753.4 | 4.588 |
| 6 | 17873.8 | 2153.5 | 3017.3 | 4127.5 | 3959.4 | 400.4 | 661.5 | 2025.8 | 3.971 |
| 7 | 18937.8 | 2514.0 | 2730.7 | 2877.8 | 3796.9 | 701.9 | 536.2 | 2395.9 | 3.358 |
| 8 | 15817.8 | 1803.3 | 2302.3 | 2234.7 | 3676.0 | 326.0 | 513.6 | 1668.3 | 4.822 |
| 9 | 14380.8 | 1568.6 | 2555.3 | 2254.2 | 3900.4 | 357.9 | 669.8 | 1453.8 | 5.534 |
| 10 | 33979.2 | 3021.8 | 3550.1 | 3038.9 | 4256.5 | 577.0 | 645.0 | 2763.6 | 2.911 |

Source throughput spans 2.768–6.272 GB/s. `sampling` remains the most stable
stage (3626–4257 ms); `clip_load` and source wall carry the variance, exactly as
in the Easy Optimization Pass.

## 5. CLIP per-block latency distribution (120 copies)

| run | p50 | p90 | p99 | max | wall/cpu p50 | cpu p50 | >100 | >250 | >500 | >1000 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 47.6 | 65.2 | 85.1 | 91.7 | 1.07 | 40.0 | 0 | 0 | 0 | 0 |
| 2 | 56.3 | 75.2 | 96.3 | 113.6 | 1.07 | 50.0 | 1 | 0 | 0 | 0 |
| 3 | 51.5 | 79.8 | 939.7 | **1460.0** | 1.07 | 50.0 | 3 | 2 | 2 | 2 |
| 4 | 35.0 | 62.3 | 75.2 | 87.9 | 1.09 | 30.0 | 0 | 0 | 0 | 0 |
| 5 | 53.6 | 74.5 | 93.6 | 107.3 | 1.06 | 50.0 | 1 | 0 | 0 | 0 |
| 6 | 52.1 | 75.5 | 335.9 | 521.8 | 1.05 | 50.0 | 2 | 2 | 1 | 0 |
| 7 | 47.4 | 79.3 | 558.7 | **1239.6** | 1.07 | 50.0 | 10 | 6 | 2 | 1 |
| 8 | 50.8 | 70.5 | 85.0 | 87.8 | 1.05 | 50.0 | 0 | 0 | 0 | 0 |
| 9 | 44.7 | 62.0 | 70.6 | 78.8 | 1.08 | 40.0 | 0 | 0 | 0 | 0 |
| 10 | 79.0 | 119.9 | 219.8 | 721.0 | 1.06 | 70.0 | 27 | 1 | 1 | 0 |

## 6. UNET per-block latency distribution (184 copies)

| run | p50 | p90 | p99 | max | wall/cpu p50 | cpu p50 | >100 | >250 | >500 | >1000 |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 44.5 | 54.8 | 84.0 | 324.7 | 1.06 | 40.0 | 1 | 1 | 0 | 0 |
| 2 | 47.8 | 66.0 | 360.5 | 681.3 | 1.06 | 50.0 | 6 | 4 | 1 | 0 |
| 3 | 46.2 | 68.6 | 118.1 | 192.8 | 1.06 | 40.0 | 6 | 0 | 0 | 0 |
| 4 | 35.5 | 40.0 | 66.2 | 155.2 | 1.10 | 30.0 | 1 | 0 | 0 | 0 |
| 5 | 50.2 | 64.5 | 104.0 | 340.2 | 1.03 | 50.0 | 4 | 1 | 0 | 0 |
| 6 | 43.5 | 160.3 | 735.0 | 904.1 | 1.05 | 40.0 | 22 | 10 | 8 | 0 |
| 7 | 49.2 | 66.5 | 184.7 | 366.7 | 1.06 | 50.0 | 6 | 1 | 0 | 0 |
| 8 | 43.0 | 48.8 | 61.7 | 164.0 | 1.05 | 40.0 | 1 | 0 | 0 | 0 |
| 9 | 42.6 | 50.1 | 93.3 | 233.9 | 1.09 | 40.0 | 1 | 0 | 0 | 0 |
| 10 | 50.7 | 80.5 | 121.3 | 309.6 | 1.04 | 50.0 | 8 | 1 | 0 | 0 |

## 7. Top slow blocks

The ten slowest copies in the entire cohort, with full evidence:

| wall ms | cpu ms | ratio | majflt | inblk | nvcsw | nivcsw | reader | ordinal | model | class |
|--:|--:|--:|--:|--:|--:|--:|--:|--:|:--|:--|
| 1460.0 | 1370.0 | 1.07 | 0 | 0 | 0 | 0 | 1 | 88 | CLIP | CPU_MEMORY_STALL |
| 1239.6 | 1160.0 | 1.07 | 0 | 0 | 0 | 0 | 0 | 15 | CLIP | CPU_MEMORY_STALL |
| 1136.1 | 1070.0 | 1.06 | 0 | 0 | 0 | 0 | 0 | 37 | CLIP | CPU_MEMORY_STALL |
| 904.1 | 860.0 | 1.05 | 0 | 0 | 0 | 0 | 0 | 100 | UNET | CPU_MEMORY_STALL |
| 793.2 | 750.0 | 1.06 | 0 | 0 | 0 | 0 | 3 | 127 | CLIP | CPU_MEMORY_STALL |
| 723.1 | 690.0 | 1.05 | 0 | 0 | 0 | 0 | 1 | 107 | CLIP | CPU_MEMORY_STALL |
| 722.4 | 690.0 | 1.05 | 0 | 0 | 0 | 0 | 3 | 91 | CLIP | CPU_MEMORY_STALL |
| 721.0 | 680.0 | 1.06 | 0 | 0 | 0 | 0 | 1 | 28 | CLIP | CPU_MEMORY_STALL |
| 681.3 | 640.0 | 1.06 | 0 | 0 | 0 | 0 | 1 | 121 | CLIP | CPU_MEMORY_STALL |
| 616.3 | 590.0 | 1.04 | 0 | 0 | 0 | 0 | 3 | 35 | CLIP | CPU_MEMORY_STALL |

Every one of the ten slowest copies in the cohort consumed thread CPU for
essentially its entire wall interval, and none recorded a single major fault,
block-I/O operation or context switch.

## 8. Thread CPU versus wall

- `wall/cpu` p50 is **1.03–1.10** on every model in every one of the ten runs.
- Of the 65 copies over 100 ms sampled in the top-8 sets, **56 had ratio ≤ 1.5**
  (thread CPU tracked wall) and the p50 ratio was **1.06**.
- The thread was **burning CPU**, not sleeping, for the large copies.

## 9. Fault and I/O deltas

Across all 3040 classified copies:

```
total minflt = 0   total majflt = 0   total inblock = 0
```

Zero major faults and zero block-I/O operations, including on every copy over
100 ms and every copy over 1000 ms. Minor faults were also zero.

## 10. Context-switch deltas

```
total nvcsw = 0   total nivcsw = 0
```

Zero context switches on every copy, including the pathological ones. This is
decisive against the descheduling hypothesis: a thread that was descheduled for
1.4 s would necessarily record voluntary switches.

## 11. Residency evidence

None. `mincore()` was implemented but is held behind its own opt-in gate and
was **off** for this cohort, for two independent reasons:

1. Its residency semantics for a file-backed mapping on a Modal Volume under
   gVisor are unverified, and cannot be verified from this host.
2. Its per-block cost was never priced (the build host is Windows), so claiming
   it is cheap would be unsupported.

`probe_availability.resident` is `false` in every run, and
`pre_resident_fraction` is `null` in every top-slow record. No conclusion in
this report rests on residency.

`probe_availability.cpu_id` is likewise `false`: `sched_getcpu` did not
resolve, consistent with the documented unreliability of CPU identity under
gVisor. No conclusion rests on CPU placement.

## 12. Classification

| class | count | share |
|---|--:|--:|
| CPU_MEMORY_STALL | 3026 | 99.5% |
| UNRESOLVED | 14 | 0.5% |
| PAGE_IO_STALL | 0 | 0% |
| DESCHEDULE_STALL | 0 | 0% |
| MIXED | 0 | 0% |

The 14 UNRESOLVED are **all ordinal 0** — the first block of a UNET load:

| run | wall ms | cpu ms | ratio | faults | switches | reader | ordinal |
|--:|--:|--:|--:|--:|--:|--:|--:|
| 1 | 324.7 | 30.0 | 10.82 | 0 | 0 | 1 | 0 |
| 2 | 260.0 | 30.0 | 8.67 | 0 | 0 | 1 | 0 |
| 3 | 192.8 | 30.0 | 6.43 | 0 | 0 | 2 | 0 |
| 4 | 155.2 | 20.0 | 7.76 | 0 | 0 | 1 | 0 |
| 5 | 340.2 | 30.0 | 11.34 | 0 | 0 | 0 | 0 |
| 7 | 366.7 | 40.0 | 9.17 | 0 | 0 | 0 | 0 |
| 8 | 164.0 | 20.0 | 8.20 | 0 | 0 | 1 | 0 |
| 9 | 233.9 | 30.0 | 7.80 | 0 | 0 | 0 | 0 |
| 10 | 309.6 | 40.0 | 7.74 | 0 | 0 | 1 | 0 |

These copies are stalled (ratio 6–11) yet carry **no** fault evidence and
**no** switch evidence, so the classifier refuses to label them. That is the
intended behaviour, not a gap: forcing a label here would be exactly the guess
this phase exists to avoid.

## 13. Evidence for and against NUMA

**No direct evidence either way.** NUMA page placement is not observable in this
environment, and `sched_getcpu` did not resolve.

What the evidence does constrain: a pure remote-memory/NUMA-placement penalty
would present as the thread running but making very slow progress. That is
*consistent* with the observed CPU_MEMORY_STALL signature, so NUMA-locality
remains a **live hypothesis inside** the CPU_MEMORY_STALL bucket — it is not
separated from it by this data, and no claim is made either way.

The following are explicitly **not** evidence for NUMA: the fact that the stall
is CPU-bound, and the fact that all four readers are affected. CPU-bound simply
rules out I/O and descheduling; it does not identify *which* CPU-bound mechanism
is at fault.

## 14. Evidence for and against Volume / page-fault behaviour

**Against the fault-driven story, decisively.** Major faults, minor faults and
block-I/O operations are all exactly zero, on healthy and pathological copies
alike. If backing-page acquisition from the Volume were the mechanism, the
counting would have to show it, and it does not.

**For a first-touch effect, weakly and only on ordinal 0.** Every one of the 14
UNRESOLVED copies is the first block of a UNET load, with wall 155–367 ms
against only 20–40 ms of CPU. That is the signature of paying a first-touch
cost. The fact that it appears *only* at ordinal 0 is consistent with later
blocks reusing pages the runtime has already brought in.

**Why the counters cannot see it.** Under gVisor the guest does not perform real
block I/O: file-backed page faults are serviced in userspace by the Sentry, so
`ru_majflt` and `ru_inblock` — which are host-kernel concepts — have nothing to
count. The first-touch cost is therefore real and observable only as wall ≫ CPU
with no fault counters at all. This is an environment limitation, and it is the
reason ordinal-0 copies stay UNRESOLVED instead of being labelled PAGE_IO_STALL.

## 15. Exact recommended source treatment

**The recommended treatment is: change nothing in the source path.**

The evidence contradicts the leading hypothesis this phase was opened to test.
`posix_fadvise(POSIX_FADV_WILLNEED)`, `readahead()` and `madvise(MADV_WILLNEED)`
are all **page-prefetch** treatments, and they treat a mechanism that the
counters rule out: **zero major faults, zero block-I/O, zero context switches**.
Adding them would be treating a symptom that was measured not to exist.

The stall is CPU-bound memory work inside `memmove`. The correct next step is
therefore *not* a prefetch syscall but a decision about where the 64 MiB copies
run and how wide they are:

1. **Memory placement / memcpy path (primary).** The signature — thread CPU
   equal to wall time — points at memory bandwidth and page placement, not at
   scheduling. Investigate NUMA-local placement of the mapped source pages
   against the arena, and whether the copy is crossing a node boundary. This
   needs a host where page placement is observable; it cannot be settled here.
2. **Host CPU contention (also consistent).** Twelve vCPUs running four reader
   threads, a CUDA context and the ComfyUI stack can be descheduled *by the
   hypervisor* without ever appearing as an in-guest context switch. That would
   present exactly as CPU time accruing slowly against a long wall interval. A
   cheap discriminating experiment is to vary `CPU` (12 versus a larger value)
   with everything else fixed and watch whether `wall/cpu` moves.
3. **Ordinal-0 first touch (secondary, bounded).** Worth one targeted
   measurement — a `MADV_WILLNEED` or `readahead()` arm applied *only* to the
   first block of each model, judged solely on whether ordinal-0 wall time falls.
   This is explicitly not recommended as a blanket treatment.

None of the three is implemented in this phase, by design.

## 16. What NOT to change

- **Do not** add `posix_fadvise`, `readahead()`, `MADV_WILLNEED`,
  `MADV_HUGEPAGE` or `mlock` as a general fix: the counters rule out the
  mechanism they address.
- **Do not** change source geometry, block size, QD, reader count or the pacer.
  None is implicated, and changing them would confound the next measurement.
- **Do not** change the mmap lifecycle. Whole-file `MAP_PRIVATE` mapped once is
  already the architecture; there is no per-block mmap syscall to remove.
- **Do not** add NUMA binding or CPU affinity on the current evidence. That is
  a treatment for a mechanism that has not been demonstrated, and it would also
  perturb the measurement needed to demonstrate it.
- **Do not** treat these results as describing the 4.3 s BAD_SOURCE extreme.
  This cohort's worst single copy was 1460 ms; the mechanism was unambiguous at
  that magnitude, but the full 4.3 s regime was not reproduced here.
- **Do not** read `capacity_wait` as proof of physical slot starvation. For the
  pathological CLIP runs in the Easy Optimization Pass, `slot_wait`,
  `all_slots_occupied` and `capacity_wait` were all zero.