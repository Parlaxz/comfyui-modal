# V2 Host-Stability Evidence Report

**Question:** do slow runs correlate with underlying hardware or cloud placement,
or with our code?  A 12-valid-cold-run host-characteristics study with
unpinned (multi-region) placement, single-use containers, minimal teardown,
`late` UNET activation, production overlap arm, and variance + host
diagnostics ON for the measurement (both diagnostic gates default OFF in
production).

- Experiment dir (12 measured + 2 excluded attempts, all preserved):
  `comfymodal-data/benchmarks/runs/v2_2026-08-06_11-11-55/`
  (`attempt_0000..0013.json`, `summary.json`, `host_ab_report.md`)
- Calibration/QA block (first-run verification, excluded from the 12):
  `comfymodal-data/benchmarks/runs/v2_2026-08-06_11-01-52/`
- Commit: see final commit SHA at the bottom of this file.

## Protocol

1. Deploy `stable-modal-comfy-v2-variance-shadow` with the verified production
   config (CPU 16 / mem 49152 MiB, TBASE/O0, single-use containers, minimal
   teardown, VAE snapshot, exact CLIP conditioning cache, UNET `late`,
   diagnostics off by default) **plus** `COMFYMODAL_V2_HOST_DIAGNOSTICS=1`
   (new diagnostic gate, default off) and variance diagnostics ON for the
   synchronized transfer measurement — exactly the region-pinned protocol
   minus the region pin.
2. First-2 rule: attempts 0–1 excluded unconditionally (snapshot/cache build
   + the run after; attempt 0 was a 91.8 s-scheduled snapshot build, attempt 1
   was the 9.38 s cache-population run — both correctly discarded).
3. 12 valid cold runs collected (restore_count==1, request_count==1, fresh
   container identity) with 25 s gaps; 14 attempts total.
4. Every attempt preserved as `attempt_<seq>.json` with a once-per-container
   `host_diagnostics` payload (provider, region, task/container id, CPU
   vendor/family/model/stepping, socket/core/thread counts, lscpu, NUMA,
   kernel, GPU name/UUID/PCI bus/PCIe gen+width, driver, CUDA, VM probes).

## Instrumentation notes (container-level visibility limits)

- **CPU model name is redacted inside the container**: both `/proc/cpuinfo`
  and `lscpu` report `Model name: unknown` (hypervisor masking).  The CPU is
  still identifiable by vendor + family/model/stepping.
- **`MODAL_CONTAINER_ID` is not exported** by Modal in this environment; the
  per-container key is `MODAL_TASK_ID` (single-use ⇒ task == container).
- **NUMA topology is not observable in-container**: `numactl` is absent and
  `/sys/devices/system/node` is masked.  NUMA could not be measured.
- **VM family/instance-type probes return nothing**: GCP/AWS metadata
  endpoints are unreachable from the Modal sandbox and DMI/sysfs is masked.
- `nvidia-smi` reports `[Unknown Error]` for PCI bus id inside the sandbox;
  sysfs fallback is also masked.  PCIe generation/width, GPU name, UUID,
  driver and CUDA versions all read correctly.
- The report-table `cmd→resp (ms)` column of `host_ab_report.md` uses the
  batch-level `COMFYMODAL_COMMAND_START_UNIX_MS` (set before deploy), so it is
  inflated by deploy time.  Per-run command→response in this document uses
  `timing.wall_ms` (local submission→response for that request), which is the
  comparable value (region-pinned reports used per-run command start).

## Results — 12 valid cold runs

All 12 landed on **CLOUD_PROVIDER_GCP**; identical reported hardware on every
run: `AuthenticAMD family 191 / model 2 / stepping unknown`, 1 socket × 32
cores × 32 threads, kernel 4.4.0 (masked), `NVIDIA RTX PRO 6000 Blackwell
Server Edition`, PCIe 5.0 ×16, driver 580.95.05, CUDA 13.0.

| # | file | region | transfer (ms) | GB/s | class | restore (ms) | cmd→resp (ms)¹ | sched (ms)² | GPU UUID (prefix) |
|---|---:|---:|---:|---|---:|---:|---:|---|
| 1 | attempt_0002 | us-east4 | 3429.7 | 3.60 | MEDIUM | 2271.5 | 29 746 | 9 178 | GPU-f88ccf02 |
| 2 | attempt_0003 | us-east1 | 6174.9 | 2.00 | SLOW | 755.1 | 22 333 | 4 300 | GPU-78dab58e |
| 3 | attempt_0004 | us-east4 | 3042.4 | 4.05 | MEDIUM | 1078.9 | 20 727 | 4 960 | GPU-f7d37185 |
| 4 | attempt_0005 | us-east1 | 1027.9 | 12.05 | FAST | 546.8 | 21 798 | 9 121 | GPU-45c2656d |
| 5 | attempt_0006 | us-east4 | 8163.3 | 1.51 | SLOW | 696.8 | 23 518 | 3 625 | GPU-6c14e5a8 |
| 6 | attempt_0007 | us-east4 | 1238.9 | 9.98 | FAST | 442.0 | 22 307 | 9 970 | GPU-6c14e5a8 |
| 7 | attempt_0008 | us-east1 | 1079.9 | 11.47 | FAST | 741.6 | 23 434 | 10 458 | GPU-78dab58e |
| 8 | attempt_0009 | us-east4 | 5167.8 | 2.39 | SLOW | 933.3 | 22 320 | 5 240 | GPU-93edb52b |
| 9 | attempt_0010 | us-east1 | 1007.7 | 12.28 | FAST | 4233.0 | 22 651 | 6 502 | GPU-887c3ec9 |
| 10 | attempt_0011 | us-east4 | 1071.9 | 11.56 | FAST | 2950.6 | 21 586 | 6 627 | GPU-6c14e5a8 |
| 11 | attempt_0012 | us-east4 | 1013.7 | 12.22 | FAST | 1288.3 | 19 639 | 6 726 | GPU-18e806eb |
| 12 | attempt_0013 | us-east4 | 996.9 | 12.42 | FAST | 1753.1 | 22 914 | 8 482 | GPU-12490f1e |

¹ per-run `timing.wall_ms`; ² `submission_to_remote_python_resume_ms`
(Modal scheduling before python resume).

Classes: FAST ×7 (997–1 239 ms @ 10.0–12.4 GB/s), MEDIUM ×2 (3 042 / 3 430 ms
@ 3.6–4.1 GB/s), SLOW ×3 (5 168 / 6 175 / 8 163 ms @ 1.5–2.4 GB/s).
The UNET payload is the same ~12.3 GB snapshot in every run; the slow class
is 5–8× slower at 1.5–2.4 GB/s effective.

## Answers to the five questions

### 1. Do fast and slow runs correlate with provider, region, CPU, NUMA, PCIe?

**No — no visible characteristic separates the classes.**

- **Provider:** constant (12/12 GCP).  The calibration block's single AWS
  draw (us-east-1, Intel) was FAST (1.71 s), but it is not part of the 12 and
  cannot support a correlation.
- **Region:** both regions produced both classes — us-east4 (n=8):
  4 FAST / 2 MEDIUM / 2 SLOW; us-east1 (n=4): 3 FAST / 0 MEDIUM / 1 SLOW.
  Slow rate is 25% in both.  Region medians differ (us-east4 3 036 ms vs
  us-east1 1 073 ms) only because the slow draws happen to be concentrated
  (2-of-3) on us-east4; the classes themselves are not region-separable.
- **CPU:** constant across all 12 (AMD f191/m2, 32T).  Cannot explain any
  variance within the block.  (A second family — Intel f6/m207 on AWS — was
  seen only in the calibration block.)
- **NUMA:** not measurable in-container (see instrumentation notes); 12/12
  "unavailable".  No evidence either way.
- **PCIe / GPU model / driver / CUDA:** constant (PCIe5 ×16, RTX PRO 6000
  Blackwell, 580.95.05, CUDA 13.0) across all 12.  Cannot explain variance.

The strongest negative evidence is at the finest identity we have — the
**physical GPU UUID**:
- `GPU-6c14e5a8` (attempts 5/6/10 → SLOW 8 163 ms, FAST 1 239 ms, FAST
  1 072 ms),
- `GPU-78dab58e` (attempts 2/7 → SLOW 6 175 ms, FAST 1 080 ms).

The same physical GPU produces a 5–8 s transfer and a ~1 s transfer minutes
apart.  If slowness were a stable host property, the same GPU could not be
both.

Also non-correlating: restore time (the largest restore, 4 233 ms, was a FAST
run; SLOW runs restored in 697–933 ms) and Modal scheduling (SLOW runs had
the *lowest* scheduling times, 3.6–5.2 s, while FAST runs scheduled in
6.5–10.5 s).  Slow transfers are not a symptom of queue delay either.

### 2. Is there evidence of multiple hardware families?

**Within the 12: one family** (AMD f191/m2 + RTX PRO 6000 Blackwell +
PCIe5 ×16 + driver/CUDA identical on every run).  **Across deployments:
yes, ≥2 families** — the calibration block drew an Intel (f6/m207, Sapphire
Rapids-class) host on AWS us-east-1 with the same GPU/driver.  So the pool
contains at least two CPU families, but the block that produced all slow
runs used only one, and that family was also the one producing the fastest
runs.

### 3. Does any hardware characteristic perfectly predict slow runs?

**No.**  There is no host/GPU/CPU/region signature shared by the 3 SLOW runs
and absent from the 7 FAST runs — they share identical reported hardware,
and the two repeated GPU UUIDs each span SLOW and FAST.  No measurable
hardware characteristic predicts the slow class.

### 4. Is there a placement option (cloud/provider/hardware) that avoids region pinning?

**No evidence for one.**  Unpinned placement self-selected GCP 12/12 this
block (and mixed in the calibration block: GCP / AWS / GCP), but that is
scheduler behavior, not a lever we control.  Nothing in the measured data
identifies a region/provider/hardware choice that would avoid the tail —
region was not separable, and hardware was constant.  The only placement
option with prior controlled evidence remains explicit region pinning
(`COMFYMODAL_V2_REGION`), which changes the odds but — as this block shows
for unpinned GCP — cannot be shown to eliminate the mechanism.

### 5. Recommended production strategy

The evidence says the slow tail is **not a stable host attribute**: the same
physical GPU flips between 8.2 s and 1.0 s transfers minutes apart, with
constant CPU/GPU/PCIe identity and no region or scheduling signature.  The
slow class is therefore best modeled as a transient pool-level contention
effect (the synchronized CPU→GPU page traversal hitting degraded
storage/memory bandwidth on that draw), not as a placement problem our code
or a hardware choice can fix.

- **Stay unpinned** — do not pay the region-pinning premium: this block shows
  the tail occurs at the same rate (25 %) on both GCP regions drawn, and the
  pinned-block evidence (0/18 bad on us-east-2 but 2.2 s @ 5.7 GB/s always)
  shows pinning trades the tail for a permanently slower median, which the
  hardware evidence here does not justify.
- **Keep the production overlap unchanged** (`late` activation + early UNET
  lane): the transfer overlaps graph/prefill work; only the residual leaks
  into the sampler lane (SLOW runs show 4.7–5.8 s sampler-lane wait vs
  0.6–0.9 s on FAST runs), so the tail's *end-to-end* cost is already
  partially absorbed.  No application change ships (host diagnostics remain
  default-off).
- **If worst-case latency must be bounded**, pin `us-east-2` (never-slow
  prior evidence) knowing it costs ~2× median transfer — a latency-vs-tail
  product decision, explicitly **not** supported by host hardware evidence.

## Files changed

- `comfymodal_runtime/modal_app.py` — new `COMFYMODAL_V2_HOST_DIAGNOSTICS`
  gate (default off): once-per-container capture of provider/region/task/
  container id, CPU vendor/family/model/stepping + socket/core/thread counts
  + lscpu, NUMA (numactl or sysfs), kernel, GPU name/UUID/PCI bus/PCIe
  gen+width/driver/CUDA, VM probes (best-effort, never raises); attached to
  every result as `host_diagnostics`; env passthrough in `_runtime_env`.
- `tools/benchmark_v2_direct.py` — `--host-ab` mode (unpinned, skip-first-2,
  target 12 / cap 18 / skip configurable via env), host fields surfaced in
  every attempt artifact, `host_ab_report.md` with per-attempt table, by-host
  summary and unique-container inventory.
- `deploy_and_run_v2_single.bat`, `run_v2_single.bat` — `host_ab` branch
  (explicit opt-in via `V2_BENCHMARK_MODE=host_ab`).
- `V2_HOST_STABILITY_EVIDENCE_REPORT.md` — this report.

## Replication

```
set COMFYMODAL_V2_HOST_DIAGNOSTICS=1
set V2_BENCHMARK_MODE=host_ab
set V2_HOST_AB_TARGET_COLD=12
set V2_HOST_AB_MAX_ATTEMPTS=18
deploy_and_run_v2_single.bat
```

Final commit SHA: `c22844b` (instrumentation + benchmark mode); this report
and its final commit: see the head commit of `main` at the time of writing.
