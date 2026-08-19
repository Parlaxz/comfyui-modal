# V2 Host Hardware & Pressure Telemetry

Instrumentation-only implementation. No runtime behavior, scheduling, CPU/RAM/GPU
requests, snapshot composition, model loading, sampling, or placement changed.
No cloud/region pins. No sandbox-escape attempts; only information legitimately
visible to the container is collected.

---

## 1. Executive result

A bounded, guarded, never-raises host-hardware and pressure telemetry family was
added to the V2 runtime and validated with one cold run (RUN 1, Fresh:YES,
STATUS OK, reconciliation 5.5 ms). It captures CPU identity/flags/topology,
GPU/PCIe state, cgroup/PSI/rusage pressure signals, and an internal H2D
host-vs-CUDA decomposition on every ordinary cold run, once per container.

What Modal/gVisor actually exposes (validated in production, not assumed):

- **CPU vendor + full feature flags: REAL and visible.** `AuthenticAMD` with a
  complete AVX-512 set (avx512f/bw/vl/dq/vnni/vbmi2, fma, bmi1/2) passed through
  by gVisor from the host CPUID FeatureSet. No masking observed.
- **CPU model name / stepping strings: hidden** (hardcoded `unknown` by gVisor,
  exactly as its source code shows).
- **CPU family/model numerics: visible but AMBIGUOUS** — 191/2 across two
  different hosts, but that encoding does not map cleanly to a public AMD family
  (see §5).
- **CPU count: 28 visible everywhere** (proc, os, affinity, lscpu, psutil) but
  the count is gVisor-configured sandbox CPUs (`--cpu-num`), not a proven
  physical-core count; gVisor synthesizes siblings/cores topology.
- **GPU + PCIe: REAL host data via NVML passthrough** — `NVIDIA RTX PRO 6000
  Blackwell Server Edition`, **PCIe Gen5 x16**, P0 @ 2340/12481 MHz, power,
  utilization all visible. One query field (`memory.bar1.used`) is rejected by
  the gVisor nvproxy allowlist; everything else works.
- **PSI: not exposed** (ENOENT under gVisor — no `/proc/pressure`).
- **cgroup: v1 visible but sentry-virtualized** (task-ID paths, not the outer
  worker cgroup); `cpu.stat` throttling counters unavailable.
- **Page faults: reported as true zeros** by gVisor sentry accounting (not fake);
  context switches: `ru_nvcsw` nonzero (43,640), `ru_nivcsw` 0, static across
  phases.
- **H2D host/CUDA split: working** — 12.31 GB in 453 copies; `cuda_elapsed ≈
  to_device_ms` with `sync_wait` of ~1 ms. A future 9 s H2D will be classifiable
  as device-side vs host-stall by construction.

Probe cost: fingerprint ~125 ms once per container; snapshots 1.7–105 ms each;
total added overhead ≈ 0.3 s per run on a ~40–57 s run. Recommend keeping it.

## 2. What Modal/gVisor exposes

| Source | Exposed | Notes |
|---|---|---|
| `/proc/cpuinfo` | vendor_id, family, model, MHz, microcode, full flags | REAL host values (gVisor synthesizes the file from a snapshot of the host CPUID) |
| `/proc/cpuinfo` model name / stepping | `unknown` | hardcoded by gVisor (`pkg/cpuid/cpuid_amd64.go`) |
| `/proc/cpuinfo` siblings/cores/physical id | synthetic | "pretend all CPUs same socket, each a distinct core" |
| `lscpu -J` | architecture, CPU(s), vendor, family/model, sockets, hypervisor | works; `Model name: unknown`; no NUMA fields |
| CPUID instruction | (blocked here: no py-cpuinfo/cpuid module in image) | gVisor emulates CPUID from the real host FeatureSet — would return real brand string |
| NVML / nvidia-smi | GPU name, UUID, driver, clocks, P-state, power, util, **PCIe gen/width** | real physical GPU via nvproxy ioctl passthrough |
| env | `MODAL_CLOUD_PROVIDER`, `MODAL_REGION`, `MODAL_IMAGE_ID`, `MODAL_TASK_ID` | official Modal env channel |
| `/proc/self/cgroup` | v1 with task-ID paths | sentry-internal; outer worker cgroup NOT visible |
| `/proc/pressure/*` | nothing (ENOENT) | not implemented by gVisor sentry |
| `/proc/self/stat`, `getrusage` | utime/stime/num_threads/nvcsw/RSS | real sentry accounting; minflt/majflt/maxrss… maxrss visible |

## 3. What is blocked

- **Direct CPUID**: no `cpuinfo`/`cpuid` Python module in the image (checked at
  runtime, `cpuid_status=unavailable`). Adding one would make the real brand
  string visible, but was out of scope (no image-weight changes). `/dev/cpu/*/cpuid`
  is not exposed by gVisor.
- **`memory.bar1.used` nvidia-smi field**: rejected by nvproxy field allowlist
  (`Field "memory.bar1.used" is not a valid field to query.`) — handled by a
  FULL→CORE→MINIMAL fallback chain; CORE succeeds.
- **PCIe bus ID string**: driver returns `[Unknown Error]` for `pci.bus_id`
  under nvproxy; tolerated as None. PCIe gen/width themselves query fine.
- **PSI** (`/proc/pressure/cpu|memory|io`): ENOENT — recorded unavailable.
- **NUMA**: no NUMA fields from lscpu/sysfs under gVisor; `numa=UNAVAILABLE`.
- **cgroup v2 throttling** (`cpu.stat` nr_periods/nr_throttled/throttled_usec):
  the sandbox exposes cgroup **v1**, so these counters do not exist here.
- **Host-private identifiers** (DMI product name, host PIDs, host cgroups,
  co-tenant inference): not attempted.

## 4. What appears virtualized

| Item | Status | Evidence |
|---|---|---|
| cgroup hierarchy | VIRTUALIZED | `/proc/self/cgroup` shows Modal task-ID paths (`7:pids:/ta-… \| 6:memory:/ta-…`), not host paths; sentry-internal by design (`cgroup_likely_virtualized=True`) |
| CPU topology (siblings/cores/sockets) | VIRTUALIZED | siblings == cores == cpu_count (28), single "physical id 0"; gVisor fakes these fields |
| CPU model name / stepping | VIRTUALIZED | `unknown` |
| CPU count | AMBIGUOUS | 28 everywhere, but gVisor-configurable (`--cpu-num`), likely sandbox quota, not physical cores |
| Page-fault counters | VIRTUALIZED (zeros) | sentry handles faults internally; getrusage + /proc/self/stat both report 0 — real zeros from sandbox accounting, not fabrication |
| PSI | BLOCKED | ENOENT |
| GPU/PCIe | NOT virtualized | nvproxy passes ioctls through to the host driver; values are genuine hardware state |

## 5. CPU identity evidence

RUN 1 (final), instance `4e2b449344a745d5`, GCP **us-east4**:

```
cpu_vendor           AuthenticAMD
cpu_family           191
cpu_model            2
cpu_model_name       unknown        (gVisor hardcoded)
cpu_stepping         unknown
cpu_microcode        (absent)
cpu_mhz              4128.84        (real host MHz, excluded from fingerprint hash)
cpu_count_proc       28
cpu_entries_homogeneous  true
cpuinfo_fingerprint_hash  bfeb099636eb45638c691e05d0532f2c502323508b41dd88270f3aaacb469d31
```

- The **identical fingerprint hash appeared on the previous RUN-1 attempt
  (us-east1)** — two independent hosts presented the same CPUID identity,
  confirming the value is stable per CPU class, not per-container noise.
- `cpu_identity_sources_agree=true` (proc_cpuinfo vs lscpu), but both sources
  are gVisor-synthesized from the same CPUID FeatureSet, so agreement is
  expected by construction; confidence is therefore labeled
  `virtualized_or_inconsistent` (triggered by `model name: unknown`).
- **Family 191 / model 2 does not map cleanly to a public AMD family**
  (public EPYC families are 0x17/0x19/0x1A etc.). The raw encoding is
  consistent across hosts, but its public-class meaning is unverified —
  do not cite a concrete CPU-class name from this alone.
- `lscpu_hypervisor_vendor=KVM` (GCP on KVM, consistent with provider GCP).

## 6. CPU feature evidence

```
flags (proc) = fpu vme de pse tsc msr pae mce cx8 apic sep mtrr pge mca cmov
  pat pse36 clflush mmx fxsr sse sse2 ht syscall nx mmxext fxsr_opt pdpe1gb
  rdtscp lm pni pclmulqdq monitor ssse3 fma cx16 pcid sse4_1 sse4_2 x2apic
  movbe popcnt aes xsave avx f16c rdrand hypervisor lahf_lm cmp_legacy
  cr8_legacy abm sse4a misalignsse 3dnowprefetch osvw topoext mwaitx fsgsbase
  tsc_adjust bmi1 avx2 smep bmi2 invpcid avx512f avx512dq rdseed adx smap
  clwb avx512cd sha_ni avx512bw avx512vl xsaveopt xsavec xgetbv1 xsaves
  avx512vbmi umip pku ospke avx512_vbmi2 gfni vaes vpclmulqdq avx512_vnni
  avx512_bitalg avx512_vpopcntdq rdpid movdiri movdir64b avx512_vp2intersect
  flush_l1d
```

Feature booleans: `avx=true avx2=true avx512f=true avx512bw=true avx512vl=true
avx512dq=true avx512_vnni=true fma=true bmi1=true bmi2=true`. `lscpu_flags`
identical to proc flags. This is a **complete, unmasked AVX-512 presentation**
— gVisor only masks features when the `dev.gvisor.internal.cpufeatures`
annotation is set; Modal does not set it. `cpu_flags_hash=e108889d028ad821`
(sha256-16 of the flags string).

**CPU FLAGS LIKELY MASKED BY GVISOR = NO** (no evidence of masking; full modern
AMD feature set including AVX-512 passed through; matches gVisor upstream
default `HostFeatureSet()`).

## 7. CPU-count/topology evidence

```
cpu_count_proc           28        (/proc/cpuinfo entries, homogeneous)
cpu_count_os             28        (os.cpu_count)
cpu_affinity_count       28        (sched_getaffinity, min 0 max 27)
cpu_count_multiprocessing 28
cpu_count_psutil_logical 28
cpu_count_psutil_physical 28
cpu_count_lscpu          28
lscpu_sockets            1
siblings                 28   (cpuinfo)
cpu cores                28   (cpuinfo)
```

All sources agree (`cpu_count_sources_agree=true`), and `cpu_entries_homogeneous
=true`. However gVisor hardcodes `siblings == numCPU`, `cpu cores == numCPU`,
and `physical id 0` ("pretend each CPU is a distinct core"), so 28 is the
**configured sandbox CPU count**, not a verified physical-core count
(notably, the CPU request for this run was 12 cores while 28 are exposed —
Modal may grant/overcommit differently). Treat as AMBIGUOUS; do not cite as
physical topology. Threads: torch 12 / interop 14, OMP/MKL/OpenBLAS 12.

## 8. GPU/PCIe evidence

```
gpu_source             nvidia_smi
gpu_name               NVIDIA RTX PRO 6000 Blackwell Server Edition
gpu_uuid_hash          cceb455d50f9dffd   (sha256-16 of UUID; raw UUID never stored)
gpu_driver_version     (CORE level; present)
gpu_pstate             P0
gpu_sm_clock_mhz       2340 → 2332/2325 across phases
gpu_mem_clock_mhz      12481
gpu_power_w            64.0
gpu_util               0 → 5 (post-H2D query catches idle; transfer is instantaneous)
gpu_mem_util           0
gpu_pcie_gen_current   5.0
gpu_pcie_gen_max       5.0
gpu_pcie_width_current 16.0
gpu_pcie_width_max     16.0
gpu_pci_bus            null (driver returned "[Unknown Error]" under nvproxy)
gpu_error              'Field "memory.bar1.used" is not a valid field to query.'
gpu_pcie_error         null
```

- PCIe Gen5 x16 on a healthy host — exactly the field needed to test the
  degraded-large-transfer hypothesis (a bad host may present Gen4/Gen3 or a
  reduced width; the probe surfaces both current and max).
- `pci.bus_id` is unavailable under nvproxy (`[Unknown Error]` tolerated → None).
- GPU state is queried at fingerprint time and every snapshot phase via the 2 s
  success / 5 s failure TTL cache — a transient early-init failure self-heals on
  the next phase (this was validated during development: the first attempt
  failed, the retry at pre_h2d succeeded).

## 9. PSI evidence

`/proc/pressure/cpu|memory|io` → ENOENT under gVisor (sentry does not implement
PSI). Recorded as `psi_status=unavailable` on every probe; **no zeros are
fabricated**. PSI is not usable on Modal today.

## 10. cgroup evidence

- `/proc/self/cgroup` visible with **v1** layout: `7:pids:/ta-… | 6:memory:/ta-…`
  (Modal task-ID paths).
- `cgroup_source=v1`, `cgroup_likely_virtualized=True`
  (`cgroup_virtualization_reason`: gVisor runsc serves sentry-internal cgroupfs;
  the outer worker cgroup is never visible — confirmed against gVisor upstream:
  `/proc/self/cgroup` is generated from sentry-internal state).
- Because it is v1 here, `cpu.stat` throttling counters
  (`nr_periods/nr_throttled/throttled_usec`) do not exist in this sandbox
  layout; they are recorded only if a v2 mount is ever present (the module
  discovers the layout from `/proc/self/mountinfo` and `/proc/self/cgroup`
  rather than hardcoding paths).
- Even a v2 layout would be sentry-virtualized — never outer-host contention
  proof. **CGROUP THROTTLING VISIBLE = NO** (as a host-contention signal).

## 11. getrusage evidence

`resource.getrusage(RUSAGE_SELF)` works under gVisor and returns **real
sentry accounting** (utime/stime/maxrss/nvcsw populated), while
**minflt/majflt are genuinely 0** (sentry handles guest page faults internally)
and `nivcsw` is 0:

```
post_restore: utime 94760ms  stime 18250ms  nvcsw 43640  nivcsw 0  minflt 0  majflt 0  rss 36.5 GiB(peak)  threads 49
pre_h2d:      utime 97510ms  delta_wall 2604.75ms (restore→H2D incl. checkpoint read)
post_h2d:     utime 100860ms delta_wall 3091.01ms (H2D interval)
sampling:     utime 102450ms delta_wall 771.26ms
```

- `nvcsw` is constant (43640) across all phases — sentry-reported, not
  phase-varying; treat as a per-container watermark, not contention signal.
- **Why the old fields were always zero — fixed**: `_PageFaultSnapshot.now()`
  returned `(0,0)` on *any* exception and deltas were `max(0, 0-0)=0` —
  fabricated zeros on failure. Now: getrusage → `/proc/self/stat` fallback →
  `unavailable=True`, and deltas emit JSON `null` (never 0) when unmeasured.
  Under gVisor the counters are available-but-true-0, which is reported honestly
  as 0 (they are sentry zeros, not missing).
- Faults are therefore **not** a usable host-contention signal on Modal
  (sentry-internal), while utime/stime deltas are real per-phase CPU usage.

## 12. H2D internal timing evidence

Real production site `_fast_disk_replay_to` (the `unet_fast_disk_complete`
producer) and the measurement clone `measure_tensors_synced_h2d` now emit a
host/CUDA decomposition **without touching the copy loop**:

```
to_wall_ms            2983.763
to_device_ms          2983.748        (existing metric, unchanged)
h2d_cuda_elapsed_ms   2983.748        (CUDA events on current stream)
h2d_enqueue_host_ms   2982.588        (host wall of the enqueue loop)
h2d_sync_wait_host_ms 1.175           (to_wall − enqueue)
h2d_copy_count        453
h2d_total_bytes       12309817472     (12.31 GB)
h2d_largest_copy_bytes 88473600
h2d_stream_id         <torch.cuda.Stream device=cuda:0 cuda_stream=0x0>
h2d_sync_method       torch.cuda.synchronize (full device)
```

Interpretation on this healthy host: enqueue time ≈ CUDA elapsed ≈ device time,
sync-wait ≈ 1 ms — the transfer is **device-time-bound**, not host-stall-bound.
On a degraded host with a 9 s H2D, the split immediately distinguishes
device-side slowdown (`cuda_elapsed` ≈ 9 s, sync-wait small) from host-side
stall (`enqueue`/`sync_wait` large while `cuda_elapsed` is small). This directly
tests the run-4 bad-host hypothesis without touching the transfer mechanism.

## 13. Probe overhead

| Probe | Wall |
|---|---|
| Full host fingerprint (once per container) | 124.7 ms (includes lscpu + nvidia-smi) |
| Snapshot post_restore | 1.7–2 ms (cached GPU) |
| Snapshot pre_h2d | 100–105 ms (fresh GPU query after failure-TTL expiry) |
| Snapshot post_h2d | 72–100 ms |
| Snapshot sampling_start | 8–37 ms |
| **Total per run** | **≈ 0.3 s** on a 40–57 s run (<1%) |

No probe runs in a tight loop; lscpu timeout 8 s, nvidia-smi timeout 10 s, both
fail-safe. The GPU failure result is cached 5 s, success 2 s.

## 14. Exact structured fields added

Two trace events (carried in the standard trace, ride existing identity
metadata including `restored_instance_id`, region, cloud):

**`host_hardware_fingerprint`** (phase="host", emitted once per container at
post-restore):
`cpu_vendor, cpu_family, cpu_model, cpu_model_name, cpu_stepping, cpu_microcode,
cpu_mhz, cpu_cache_size, cpu_siblings, cpu_cores, cpu_physical_id, cpu_core_id,
cpu_count_proc, cpu_entries_homogeneous, cpu_flags, cpu_flags_hash, avx, avx2,
avx512f, avx512bw, avx512vl, avx512dq, avx512_vnni, fma, bmi1, bmi2,
cpuinfo_fingerprint_hash, cpu_count_os, cpu_affinity_count, cpu_affinity_min,
cpu_affinity_max, cpu_count_multiprocessing, cpu_count_psutil_logical,
cpu_count_psutil_physical, torch_threads, torch_interop_threads, omp_num_threads,
mkl_num_threads, openblas_num_threads, numexpr_num_threads, lscpu_architecture,
lscpu_cpu_count, lscpu_vendor_id, lscpu_model_name, lscpu_cpu_family,
lscpu_cpu_model, lscpu_sockets, lscpu_hypervisor_vendor, lscpu_flags,
lscpu_status, cpuid_status, cpuid_source, cpu_identity_sources_agree,
cpu_count_sources_agree, cpu_features_source, cpu_identity_confidence,
gpu_source, gpu_name, gpu_uuid_hash, gpu_driver_version, gpu_index, gpu_pci_bus,
gpu_pcie_gen_current, gpu_pcie_gen_max, gpu_pcie_width_current,
gpu_pcie_width_max, gpu_pstate, gpu_sm_clock_mhz, gpu_mem_clock_mhz, gpu_power_w,
gpu_util, gpu_mem_util, gpu_bar1_used_mib, gpu_error, gpu_pcie_error,
gpu_query_wall_ms, psi_status, cgroup_source, cgroup_likely_virtualized,
cgroup_lines_snippet, provider, region, modal_image_id, modal_task_id,
probe_statuses, probe_wall_ms`

**`host_resource_snapshot`** (phase ∈ post_restore|pre_h2d|post_h2d|sampling_start):
`phase, ru_utime, ru_stime, ru_minflt, ru_majflt, ru_nvcsw, ru_nivcsw,
ru_maxrss, minflt, majflt, utime_ms, stime_ms, num_threads, gpu_pstate,
gpu_sm_clock_mhz, gpu_mem_clock_mhz, gpu_util, gpu_mem_util, gpu_power_w,
gpu_bar1_used_mib, gpu_pcie_gen, gpu_pcie_width, delta_minflt, delta_majflt,
delta_nvcsw, delta_nivcsw, delta_utime_ms, delta_stime_ms, delta_wall_ms,
probe_wall_ms`

**`unet_fast_disk_complete` / unet_backing H2D record additions** (existing keys
untouched):
`h2d_cuda_elapsed_ms, h2d_enqueue_host_ms, h2d_sync_wait_host_ms, h2d_copy_count,
h2d_total_bytes, h2d_largest_copy_bytes, h2d_stream_id, h2d_stream_cuda_stream,
h2d_sync_method`

**Fixed**: `_PageFaultSnapshot`/`_pagefault_delta` now emit `null` (never
fabricated 0) when unmeasured, with `/proc/self/stat` fallback.

## 15. RUN 1 output

Instrumentation was developed against two shorter debug attempts, then fixed
per the Part 12 gate and re-run. Final accepted RUN 1:

```
RUN 1 ID             v2-benchmark-0-d860910cc182
Instance             4e2b449344a745d5   (restored_instance_id)
Deployment           ed44795a17ff9489 (deploy #3)
Provider/Region      GCP / us-east4
GPU                  RTX-PRO-6000
Fresh                YES (restore_count=1, request_count=1)
STATUS               OK
Reconciliation       5.518 ms  (≤10 ms target AND ≤50 ms hard gate)

SOURCE                         STATUS        OBSERVED VALUE
/proc/cpuinfo vendor/model     available     AuthenticAMD family 191 model 2 (model name "unknown", virtualized)
/proc/cpuinfo flags            available     full AVX-512 set, unmasked
os.cpu_count                   available     28
sched_getaffinity              available     28 (range 0–27)
multiprocessing.cpu_count      available     28
psutil cpu_count               available     28 logical / 28 physical (synthetic per gVisor)
lscpu                          available     x86_64, 28 CPUs, 1 socket, hypervisor KVM, model name unknown
direct CPUID                   unavailable   no cpuinfo/cpuid module in image
NUMA                           unavailable   no NUMA fields exposed (gVisor sysfs)
PSI cpu/memory/io              unavailable   ENOENT (not implemented by gVisor)
cgroup                         v1 visible    task-ID paths; sentry-virtualized (outer worker NOT visible)
cgroup cpu.stat throttling     unavailable   v1 layout has no cpu.stat
NVML/nvidia-smi                available     RTX PRO 6000 Blackwell; bar1.used rejected (fallback OK)
NVML PCIe gen                  available     5.0 current / 5.0 max
NVML PCIe width                available     16 current / 16 max
NVML pstate/clocks             available     P0, SM 2340 MHz, MEM 12481 MHz, 64.0 W
getrusage faults               available     0/0 — true sentry zeros (sentry-internal accounting)
getrusage context switches     available     nvcsw 43640 (per-container watermark), nivcsw 0
/proc/self/stat                available     utime/stime/threads real; minflt/majflt 0 (sentry)
H2D decomposition              working       cuda 2983.7 ms ≈ enqueue 2982.6 ms, sync-wait 1.2 ms
```

Earlier debug attempts (not counted as RUN 1): `v2-benchmark-0-9ad62e73da66`
(us-south1; GPU probe missing — fixed), and a us-east1 run with CORE-level GPU
fields but no PCIe fields — fixed by the standalone PCIe probe.

## 16. How to correlate future slow runs

Every ordinary cold run now emits the fingerprint once plus four phase
snapshots, keyed by `restored_instance_id`. A slow-run forensics pass can:

1. Join run metrics (H2D ms, `restore_gpu_state_ms`, pre-Python restore ms,
   VAE H2D ms) with `cpuinfo_fingerprint_hash`, `gpu_uuid_hash`, region.
2. Compare `h2d_cuda_elapsed_ms` vs `h2d_enqueue_host_ms`/`h2d_sync_wait_host_ms`
   — device-bound vs host-stall classification for any future 9 s H2D.
3. Compare `gpu_pcie_gen_current/width_current` vs max across hosts — a degraded
   lane (e.g. Gen4 x16, Gen5 x8) would show up as a bad-host marker.
4. Use `gpu_pstate`/clocks/power per phase — a throttled/off-clocks host is
   visible (P0 vs P2+).
5. Use utime/stime deltas per phase for genuine CPU usage; treat PSI and
   cgroup-throttling as permanently unavailable on Modal, and fault counters as
   sentry-internal.
6. The fingerprint hash is stable across hosts of the same CPU class (verified:
   identical hash on us-east1 and us-east4 attempts) — safe as a grouping key.

## 17. Remaining blind spots

- **Physical CPU core count / real topology**: gVisor synthesizes; the exposed
  28 is sandbox-config, not host topology. Unknown if it tracks host quota.
- **CPU class name**: family 191/model 2 does not map to a public AMD family
  name — the raw encoding is stable but its public meaning is unverified.
  Adding the `cpuinfo`/`cpuid` Python package to the image would surface the
  real brand string via CPUID (gVisor emulates it from the real host FeatureSet).
- **PSI / cgroup throttling**: unusable on Modal (ENOENT / v1 sentry-virtualized).
- **PCIe bus ID**: `[Unknown Error]` under nvproxy; gen/width are the useful
  fields and they work.
- **Page faults**: sentry-internal zeros — no host-fault signal available.
- **nvcsw/nivcsw**: sentry watermark, not phase-varying; no per-phase context
  switch signal.
- **Instance-level host identity**: UUIDs are hashed; no host name is exposed.
  Correlation relies on fingerprint-hash grouping, which is exactly what the
  forensics need (class-level), not instance-level.
- **`memory.bar1.used`**: rejected by nvproxy allowlist; bar1 utilization
  remains unavailable.

---

## 18. Telemetry overhead correction

The pass-1 design ran GPU/lscpu subprocess probing on every healthy run:

| Component | Pass-1 measured | Root cause |
|---|---|---|
| Fingerprint | 124.7 ms | `lscpu` subprocess (~25 ms) + `nvidia-smi` subprocess (~95 ms) |
| pre_h2d / post_h2d snapshots | 70–105 ms each | fresh `nvidia-smi` subprocess after failure-TTL expiry |
| post_restore / sampling snapshots | 1.7–8.4 ms | cached GPU result |
| **Total per run** | **~300 ms** | subprocess spawn cost dominates under runsc |

First correction attempt (ctypes NVML static probe) measured **402 ms** in the container
(`nvmlInit`/library load is slow under gVisor) and still returned `pcie_max=None`
(max-link NVML calls are unsupported under nvproxy) — removed in favor of the
torch identity path. Final accepted validation (RUN 1 follow-up):

| Component | Final measured (validation RUN) |
|---|---|
| cpu_fingerprint_ms (fingerprint probe_wall_ms) | **4.28 ms** |
| static_gpu_probe_ms | **0** (torch-only identity, in-process; no ctypes/NVML) |
| post_restore_snapshot_ms | 0.14 ms |
| pre_h2d_snapshot_ms | 4.52 ms |
| post_h2d_snapshot_ms | 0.96 ms |
| sampling_snapshot_ms | 0.25 ms |
| slow_trigger_probe_ms (healthy H2D < 4 s) | **0** |
| **host_telemetry_total_probe_wall_ms** | **10.15 ms** |

Healthy critical-path telemetry overhead: **~300 ms → 10.15 ms (PASS, ≤ 20 ms
target; ~10 ms preferred achieved).**

## 19. Lightweight production profile

ALWAYS-ON (Tier A — in-process only, zero subprocesses, ~10 ms total):

- `/proc/cpuinfo` parse: vendor/family/model numerics, feature flags, entry
  count/homogeneity, `cpuinfo_fingerprint_hash` (1–2 file opens)
- `os.cpu_count`, `sched_getaffinity`, multiprocessing count, torch thread
  counts, thread-policy env vars
- provider/region/modal env (`MODAL_CLOUD_PROVIDER`, `MODAL_REGION`)
- torch GPU identity (`gpu_name`, capability, total memory) — torch is already
  loaded in the runtime; µs cost
- `getrusage` + `/proc/self/stat` per phase (utime/stime/threads/deltas)
- H2D host/CUDA decomposition (CUDA events, reuses the existing final
  synchronize — no extra sync, overhead negligible)
- PSI/cgroup **capability probe once** (gated: absent PSI → 1 stat, never 3
  opens; v1 cgroup detected from `/proc/self/cgroup` alone → no mountinfo, no
  controller-file reads; v2 path retained for the rare case)

SLOW-TRIGGER (Tier B — subprocesses allowed, only after a slow H2D observed):

- `nvidia-smi` FULL→CORE→MINIMAL chain: PCIe gen current/max, width
  current/max, P-state, SM/MEM clocks, power, utilization, name, UUID-hash,
  driver version, `gpu_pcie_error`
- `lscpu -J`: architecture, CPU count, vendor/model, sockets, hypervisor
- emitted as `host_forensic_slow_h2d` (once per slow run) with trigger_reason,
  classification, and probe wall

DIAGNOSTICS-ONLY: the same Tier B probe set runs when
`COMFYMODAL_V2_HOST_DIAGNOSTICS=1` (explicit opt-in) even on healthy runs.

REMOVED-AS-USELESS (per RUN 1 evidence + gVisor research):

- per-phase nvidia-smi dynamic GPU polling (post_restore/pre_h2d/post_h2d/
  sampling_start) — static fields were queried 4× per run
- ctypes NVML static probe — 402 ms under gVisor, max-link calls unsupported
- per-phase PSI file reads (3 ENOENT opens each) — capability-cached to 1 stat
- per-phase cgroup v1 controller-file reads (mountinfo + cpuacct.usage +
  memory.usage_in_bytes + oom_control) — sentry-virtualized, no host signal
- `static_gpu_probe_ms` fingerprint field (the 402 ms probe it measured)
- nvcsw/nivcsw kept (free watermark) but explicitly labeled non-phase-varying;
  minflt/majflt kept as honest sentry zeros, never interpreted as host signal

## 20. Slow-H2D forensic trigger

- Threshold: `h2d_wall_ms >= COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS` (default
  **4000 ms**; between observed healthy 2.0–3.0 s and known-bad 9.229 s),
  OR `COMFYMODAL_V2_HOST_DIAGNOSTICS=1`.
- Evaluated once per production H2D in `_fast_disk_replay_to` immediately
  after the post_h2d snapshot; on trigger, `emit_slow_h2d_forensics()` runs the
  Tier B probes (~100–200 ms) and emits `host_forensic_slow_h2d` carrying the
  H2D decomposition, classification, and full GPU/PCIe/lscpu data.
- Healthy runs: trigger evaluated, not fired — **0 GPU subprocess calls, 0
  lscpu calls, slow_trigger_probe_ms = 0** (validated on the healthy 2.82 s
  validation run; no forensic event in the trace).
- Unit-verified without a real bad host (mocked timings): 2.5 s → no probe;
  4.1 s → probe; 9.2 s → probe; env-threshold override; diag-flag override;
  forensic event attaches to the run trace with real field wiring.

## 21. Correct H2D classification semantics

Terminology correction: `enqueue ≈ cuda_elapsed` does NOT prove "device-bound".
Synchronous/pageable H2D calls may block the host while the DMA proceeds, so
the decomposition describes *where wall time went*, not the root cause. Each
`unet_fast_disk_complete` event now carries `h2d_classification`:

- `TRAILING_SYNC_STALL` — `sync_wait_host_ms` large relative to CUDA elapsed
- `COPY_INTERVAL_SLOW` — enqueue ≈ cuda elapsed, both large (time spent inside
  the copy interval; the healthy shape too)
- `HOST_OVERHEAD_AROUND_COPY` — enqueue materially exceeds CUDA elapsed
- `UNKNOWN/MIXED` — missing/unmeasurable fields

Healthy validation runs classify `COPY_INTERVAL_SLOW` (enqueue ≈ cuda,
sync-wait 0–1.3 ms). Root-cause claims (PCIe/device vs host) must pair the
classification with Tier B PCIe gen/width, P-state/clocks, and the CPU
fingerprint. A zero-value `sync_wait` (sub-ms rounding) is treated as a valid
measurement, not missing (edge fixed post-validation, unit-verified with the
exact real-data shape; the deployed validation build predates this label-only
fix, raw `h2d_*` timings are unaffected).

## 22. Final production recommendation

**YES — ship as-is.** The healthy-run cost is 10.15 ms total (~0.02 % of a
typical 40–60 s run), zero subprocesses, and the bad-run evidence (CPU
fingerprint hash + GPU PCIe gen/width + P-state/clocks + H2D host/CUDA split)
is fully retained behind a 4 s trigger that adds ~150 ms only when a run is
already abnormal. CPU physical brand/class stays AMBIGUOUS (family 191/2 does
not map to a public AMD family; report as gVisor-exposed CPUID-derived
grouping data, not physical identity). No image/dependency changes were made.
Lane ready to close.

---

## Completion output

```
report path = V2_HOST_HARDWARE_AND_PRESSURE_TELEMETRY.md
changed files (this pass) =
  comfymodal_runtime/host_hardware_telemetry.py          (two-tier restructure; Tier A in-process-only; classify_h2d/should_trigger_slow_probe/emit_slow_h2d_forensics; PSI 1-stat gate; cgroup v1 short-circuit; ctypes-NVML removed; zero-sync classification edge fix)
  comfymodal_runtime/model_preload.py                    (h2d_classification on unet_fast_disk_complete; slow-trigger after post_h2d)
  comfymodal_runtime/unet_backing.py                     (h2d_classification on measurement clone)
  tests/test_host_hardware_telemetry.py                  (51 tests, incl. tier-A zero-subprocess, trigger thresholds, forensics, capability cache, zero-sync edge)
commit = none
deploy count this pass = 3 (30ffbba364151c10, 231daac350166a7b, 893627cebba8e5cb)
validation RUN ID = v2-benchmark-0-2b31639a0c6e  (Fresh:YES, STATUS OK, reconciliation -8.27 ms)

healthy telemetry overhead before = ~300 ms per run
healthy telemetry overhead after  = 10.15 ms per run (fingerprint 4.28 + snapshots 0.14/4.52/0.96/0.25)

CPU fingerprint always-on cost = 4.28 ms (fingerprint probe_wall_ms)
GPU subprocess calls on healthy run = 0 (validated: no nvidia-smi on Tier A; forensic absent on healthy run)
slow-H2D trigger threshold = 4000 ms default (env COMFYMODAL_V2_SLOW_H2D_THRESHOLD_MS)
slow-trigger probe tested = YES (unit: 2.5s→no probe, 4.1s→probe, 9.2s→probe, env + diag-flag overrides; no real slow run needed)

H2D decomposition overhead = negligible (CUDA events reuse existing final synchronize; no extra sync; enqueue≈cuda on healthy runs)
H2D interpretation corrected = YES (classification A–D; "device-bound" claim removed; zero-sync edge fixed)

CPU physical class identifiable = AMBIGUOUS
CPU grouping fingerprint usable = YES (hash bfeb099636eb… stable across hosts)
PCIe forensic data retained on slow run = YES (Tier B nvidia-smi: gen/width current+max, pstate, clocks, power, util)

healthy overhead target <=20 ms = PASS (10.15 ms)
recommend production telemetry = YES
lane ready to close = YES
```
