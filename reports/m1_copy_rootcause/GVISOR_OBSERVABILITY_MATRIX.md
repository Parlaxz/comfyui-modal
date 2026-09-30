# M1 GVISOR / OS OBSERVABILITY AVAILABILITY MATRIX

Environment: Modal container, gVisor (`4.19.0-gvisor` per historical ledger),
H100!, 12 vCPU, 24576 MiB, production-006 C0 source owner.

Every row records the mechanism actually attempted, the observed result, the
fallback, and whether the metric was used in the M1 analysis.

| desired metric | primary mechanism attempted | available? | result / error | fallback used | fallback available? | semantic caveats | used in analysis? |
|---|---|---|---|---|---|---|---|
| Per-extent source wall | `time.monotonic_ns()` around native `memmove` in `execute_block` | **YES** | full ns resolution; distinct wall values not quantized (e.g. 14.061, 22.739, 24.529 ms) | none needed | n/a | none | **YES** — primary source of per-op duration |
| Per-extent thread CPU | `time.thread_time_ns()` immediately around `memmove` | **YES, but COARSE** | returns a real non-zero delta, but **quantized to 10 ms**: all 41 distinct deltas are exact multiples of 10 ms (10,20,...,1420) | treat as a 10 ms-resolution estimator; report ratio bands not point values | yes, with reduced precision | **CPU>wall occurs on 288/1216 ops** purely from rounding-up of a 10 ms grid. Ratio p50 0.93-0.94 is meaningful; individual ratios >1 are artifacts, not evidence of extra CPU | **YES**, with the quantization caveat stated in every use |
| Page faults (minor) | `resource.getrusage(RUSAGE_THREAD).ru_minflt` | **NO (silent zeros)** | present and callable; returns 0 for every one of 1216 ops. Not an error, just never populated | none possible — gVisor does not account guest minor faults per thread | **NO** | cannot distinguish "no faults" from "counter not implemented". Historical ledger reached the same conclusion (`SOURCE_IO_EXPERIMENT_LEDGER.md:96`) | **NO** — recorded as UNAVAILABLE, not as zero faults |
| Page faults (major) | `ru_majflt` | **NO (silent zeros)** | 0 on all ops, same as above | none | **NO** | same | **NO** |
| Voluntary context switches | `ru_nvcsw` | **NO (silent zeros)** | 0 on all 1216 ops | none | **NO** | same | **NO** |
| Involuntary context switches | `ru_nivcsw` | **NO (silent zeros)** | 0 on all ops | none | **NO** | same | **NO** |
| Page residency | `mincore()` | **NOT ATTEMPTED in-container (deliberate)** | historical evidence: reports all pages resident even before access, i.e. semantically false | avoided | n/a | calling it would produce a confidently wrong number. Not re-run because it is already proven useless in this runtime and would risk touching source pages | **NO** — documented as UNAVAILABLE-IN-ENVIRONMENT |
| Prefetch hints | `MADV_WILLNEED` / `readahead()` | **NO** | historical: `readahead()` returns `EINVAL(22)`; `MADV_WILLNEED` functionally inert; `MAP_POPULATE` accepted but does not materialise | real-access timing (which M1 uses) | yes | n/a | indirectly — supports the whole-mapping + first-touch-cost model |
| Thread scheduler stats | `/proc/self/task/<tid>/schedstat` | **NO — confirmed absent** | `FileNotFoundError` on all 16 sampled tids; `/proc/self/task/<tid>/` exists but `schedstat` does not | `thread_time_ns` + per-extent concurrency flags | yes | runqueue-wait and timeslice counts are **not obtainable in this runtime** | **NO** — UNAVAILABLE-IN-ENVIRONMENT (now proven, not assumed) |
| Thread context switches | `/proc/self/task/<tid>/status` | **PARTIAL — present but always 0** | file exists; `voluntary_ctxt_switches: 0`, `nonvoluntary_ctxt_switches: 0` for every sampled tid | none | no | same silent-zero gap as `rusage`; corroborates rather than contradicts it | **NO** — corroborates the rusage finding |
| CPU affinity mask | `os.sched_getaffinity(0)` | **YES** | symbol present; **28 logical CPUs**; full list `[0..19, ...]` captured | n/a | n/a | logical CPU count only; no physical topology | **YES** — 28 logical CPUs vs 4 readers, so 7× oversubscribed |
| CPU placement / migration | `os.sched_getcpu()` | **NO — symbol absent** | `sched_getcpu_symbol_present = False`, `cpu_now = None` | none | **NO** | gVisor does not expose the executing CPU | **NO** — UNAVAILABLE-IN-ENVIRONMENT |
| `/proc/self/status` | read-only open | **YES** | captured (`Name: python`, `State: R (running)`, `Pid: 2`, `TracerPid: 0`) | n/a | n/a | process-level only | **YES** |
| `/proc/self/smaps_rollup` | read-only open | **NO** | `FileNotFoundError` | none | **NO** | RSS/Referenced/Locked aggregate unavailable | **NO** |
| `/proc/pressure/{cpu,memory,io}` | read-only open | **NO — all three absent** | `FileNotFoundError` on each | none | **NO** | PSI not implemented | **NO** — UNAVAILABLE-IN-ENVIRONMENT |
| cgroup v2 `cpu.stat` | `/sys/fs/cgroup/cpu.stat` | **NO** | `FileNotFoundError` (confirms historical "unreadable") | none | **NO** | no throttling visibility | **NO** |
| cgroup `memory.current` / `*.pressure` | `/sys/fs/cgroup/...` | **NO** | `FileNotFoundError` on all three | none | **NO** | | **NO** |
| `/proc/self/mountinfo` | read-only open | **YES (file) / NO (model entries)** | file opened successfully but contains **0** lines matching `safetensors`, `/models`, or `/root` — the container's mounts do not describe the model paths | exact `os.stat` on the model files instead | **YES** | a limitation of mount visibility under gVisor | **YES** — via the stat fallback |
| NUMA topology | `/proc/.../numa_maps`, sysfs CPU→node | **NOT ATTEMPTED** | expected absent | none | n/a | gVisor virtualizes topology | **NO** — UNAVAILABLE-IN-ENVIRONMENT |
| Model file identity | `os.stat` + seek-to-end size confirmation | **YES** | CLIP `/root/comfy/ComfyUI/models/text_encoders/qwen_3_4b.safetensors` size **8 044 982 048 B**, dev 31, inode 7, st_blksize 4096, st_blocks 15 712 856. UNET `/root/comfy/ComfyUI/models/diffusion_models/z_image_turbo_bf16.safetensors` size **12 309 866 400 B**, dev 31, inode 55, st_blocks 24 042 708 | n/a | n/a | `dev 31` is the gVisor-visible device id; **no filesystem type is asserted** and the path is NOT labelled "Modal storage" | **YES** |
| Monotonic clock | `time.get_clock_info("monotonic")` | **YES** | `clock_gettime(CLOCK_MONOTONIC)`, monotonic=True, adjustable=False, **resolution 1e-09** | n/a | n/a | the same domain Golden telemetry uses; not adjustable, so cross-run absolute comparison is invalid by design | **YES** |

## Consequences for the headline question (page-service vs CPU memcpy)

The one measurement that *does* work is the per-extent wall/CPU pair, and it is
good enough for a directional answer:

- median CPU/wall = **0.938 (CLIP)**, **0.942 (UNET)** across 1216 extents.
- median off-CPU residual = **3.80 ms (CLIP)**, **3.18 ms (UNET)** per 64 MiB extent.
- The CPU is therefore executing during ~94% of every physical copy. The copy is
  **CPU/memcpy-dominated**, not blocked-on-storage dominated.

What cannot be resolved here, and why:

1. **Exact fault attribution.** With `ru_minflt` pinned at 0, `mincore()`
   proven to lie, and `/proc/self/task/<tid>/status` reporting zero context
   switches, there is no in-environment way to count the page services that
   occur *inside* a `memmove` reading a file-backed mapping. The residual
   (~6% of wall, plus whatever the 10 ms grid hides) is an upper bound on
   non-executing time, not a measurement of storage service.
2. **Runqueue wait.** `schedstat` does not exist and both context-switch
   counters are zero, so involuntary descheduling cannot be separated from
   in-CPU page-handling work.
3. **CPU migration.** `os.sched_getcpu` is absent from this runtime's `os`
   module, so the executing CPU cannot be sampled at all.
4. **Host pressure.** PSI, `cpu.stat`, `memory.current` and the cgroup pressure
   files are all absent, so run-to-run slowness cannot be attributed to cgroup
   throttling or to PSI-visible queueing in this environment.
5. **RSS / page residency aggregate.** `smaps_rollup` does not exist.

What the Level-2 probe *did* settle:

- The monotonic clock is `clock_gettime(CLOCK_MONOTONIC)` with 1 ns resolution
  and `adjustable=False` — the same authoritative domain Golden telemetry uses,
  and non-adjustable by design (so absolute cross-run comparison is invalid,
  while within-run comparison is exact).
- The container exposes **28 logical CPUs** to a process driving **4** reader
  threads, i.e. 7× oversubscribed. This is consistent with the measured
  near-4 effective concurrency but does **not** by itself explain it, because
  the readers spend ~94% of their time inside `memmove` rather than competing
  for runqueue slots.
- Model file identity is now exact and reproducible (§20, §22 of the final
  report), including `st_blocks`, which lets actual allocated blocks be compared
  against file size.

## Recommended next bounded step

**None required for the questions this milestone was chartered to answer.** One
Level-2 request (deploy `aefe3302696ab83f449f786b17b9ec9a2499156e69ea885c1fabb5f43a8776b6`,
run `run_20260930-042450_28704bbe`) has now been executed and closed every
environment question that this runtime can answer. The remaining gaps are proven
environment limitations, not un-attempted measurements.

Level-3 invasive resident-copy calibration remains **not** justified: the Level-1
CPU/wall ratio already answers the page-service/memcpy split at the resolution
this environment permits, and no additional kernel surface exists that a
calibration could reveal.
