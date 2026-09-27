# V2 Run 4 Bad-Host Forensics — `v2-benchmark-3-3be52a7f2037`

Read-only forensic analysis. No code modified, no deployments, no runs issued.

Data sources:

- `V2_10_COLD_RUNS_35S_COOLDOWN.md` (authoritative; read in full)
- `v2_c2f_10cold_35gap.log` (UTF-16; run 4 section lines ~495–573)
- Run artifacts: `…\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-13_23-06-56\` — `run_0.json`…`run_9.json`, `summary.json`, `campaign_manifest.json` (note: the artifacts live under the ComfyUI root's `comfymodal-data`, not the custom-node-local copy; run_index N ↔ "Run N+1" in the MD, so **Run 4 = run_index 3**).

---

## 1. Executive verdict

**Run 4 is a degraded-worker (bad-host) event, not a checkpoint-read or application problem, and not an isolated H2D problem.**

Three distinct large-memory-movement stages degraded simultaneously; everything small, everything GPU-compute, and everything disk-I/O stayed at baseline:

| Stage | Run 4 | Median of other 9 | Ratio | Rank |
|---|---|---|---|---|
| Modal pre-Python snapshot restore | 6.487 s | 3.503 s | **1.85×** | 10/10 (max) |
| Python/application restore | 1.535 s | 0.612 s | **2.51×** | 10/10 (max) |
| — of which restore_gpu_state | 1.318 s | 0.249 s | **5.29×** | 10/10 (max) |
| Pre-sampler execution | 10.681 s | 4.933 s | **2.17×** | 10/10 (max) |
| — of which Synchronized H2D | 9.229 s | 2.333 s | **3.96×** | 10/10 (max) |
| TOTAL WALL | 26.471 s | 15.456 s | **1.71×** | 10/10 (max) |

**What stayed normal (the critical discriminator):** checkpoint active-read of the same 12.31 GB file at 9.22 GB/s (1.336 s; others 1.06–1.71 s), UNET get_model (48 ms), bind (21 ms), **sampling (4.816 s vs median 4.806 s — 1.00×)**, VAE H2D (0.869 s vs 0.862 s), VAE decode, PNG, handoff, conditioning lookup, scheduling (2.313 s — unremarkable for us-east4).

The failure pattern is: **all large bulk transfers (host-side snapshot hydration, GPU-state restore, 12.3 GB host→device copy) are slow; all latency-bound, compute-bound, and disk-bound operations are normal.** This is the signature of a degraded memory/PCIe-class path on the specific worker instance — H2D is a *symptom* of that host, not an independent defect of the transfer code path (the identical code path ran 5.3 GB/s on nine other hosts).

Classification: **C/G hybrid — "CPU/memory movement broadly bad (large-transfer class only)"**, with disk I/O and GPU compute intact. Not A (restore-only), not B (H2D-only), not D (I/O), not E (GPU), not F (everything).

---

## 2. Run 4 vs nine-run baseline

All comparisons below use the other 9 runs as baseline (median shown). Run 4 values in **bold**.

| Stage | Run 4 | med(9) | ratio | rank/10 |
|---|---:|---:|---:|---:|
| Pre-Python restore (ms) | **6487.0** | 3503.0 | 1.85 | 10 |
| Python restore (ms) | **1535.0** | 612.0 | 2.51 | 10 |
| restore_gpu_state (ms) | **1317.5** | 249.0 | 5.29 | 10 |
| snapshot_restore (ms) | **1500.0** | 467.6 | 3.21 | 10 |
| reload_models (ms) | 90.3 | 98.2 | 0.92 | 4 |
| cuda_init (ms) | 4.9 | 4.2 | 1.17 | 9 |
| folder_warm (ms) | 1490.6 | 1934.1 | 0.77 | 3 |
| Pre-sampler (ms) | **10680.9** | 4933.2 | 2.17 | 10 |
| Checkpoint read (ms) | 1335.7 | 1198.5 | 1.11 | 8 |
| UNET get_model (ms) | 48.1 | 63.0 | 0.76 | 3 |
| Bind (ms) | 21.0 | 23.2 | 0.90 | 5 |
| Synchronized H2D (ms) | **9229.0** | 2332.5 | 3.96 | 10 |
| UNETLoader total (ms) | **10653.1** | 3665.7 | 2.91 | 10 |
| Sampling (ms) | 3690.8 | 3682.5 | 1.00 | 7 |
| Sampler→sampling (ms) | 137.1 | 125.4 | 1.09 | 9 |
| Post-sampling/VAE transition (ms) | 844.0 | 839.9 | 1.00 | 6 |
| VAE load/H2D (ms) | 868.6 | 861.7 | 1.01 | 6 |
| VAE decode (ms) | 378.7 | 376.6 | 1.01 | 6 |
| Output encode (ms) | 255.7 | 249.9 | 1.02 | 9 |
| PNG encode (ms) | 179.3 | 173.6 | 1.03 | 10 |
| Handoff (ms) | 967.9 | 994.3 | 0.97 | 2 |
| Conditioning exact-hit lookup (ms) | 49.5 | 46.4 | 1.07 | 7 |
| ImpactSwitch node (ms) | 737.0 | 595.7 | 1.24 | 9 |
| Prefetch wall (ms) | 218.3 | 176.8 | 1.24 | 7 |
| Scheduling (ms) | 2313 | 1441 (us-east4) | — | normal |
| TOTAL WALL (ms) | **26471** | 15456 | 1.71 | 10 |

H2D arithmetic: file = 12,309,866,400 bytes; Run 4 → 1.33 GB/s; others → 5.0–6.1 GB/s. Pre-sampler delta (10681 − 4933 = 5748 ms) is **fully accounted for by the H2D delta (9229 − 2333 = 6896 ms)**; checkpoint read contributed nothing.

---

## 3. Full feature matrix

### Identity / platform (identical across all 10 runs unless noted)

| Field | Run 4 (index 3) | Other runs |
|---|---|---|
| Provider/Region | GCP/us-east4 | 6× us-east4, 2× us-east1, 1× AWS/eu-south-2 |
| Image | im-u4n8F9xm0ABjQwEfUImNLn | same (all) |
| GPU request | RTX-PRO-6000 | same |
| GPU actual | NVIDIA RTX PRO 6000 Blackwell Server Edition, compute 12.0, 97250 MiB, CUDA 13.0, torch 2.13.0+cu130 | same (all) |
| CPU / memory request | 12 / 32768 MB | same |
| Runtime-shape fingerprint | f504e296c398bdcb2c4c07e2 (TBASE, intraop 12, interop 14) | same |
| App fingerprint | 64bcf347…6433d46 | same |
| Restored instance id | 96c64d31152b472a9c81de7ebd423b9a | unique per run (all) |
| Restore session id | d8dfe15ad11f4013be736d315f56a1f5 | unique per run (all) |
| Container task id | ta-01KZYP8E0M25Q9GPTM34235FAR | unique (all) |
| Container session id | 968c4fcdf444452c | shared with runs 0/1/4 — not discriminating |
| Fresh / scheduling / reconciliation | YES / 2.313 s / −0.253 ms | YES / 0.70–63.5 s / ≤5.7 ms |
| Native thread counts | 51 (entry), 52–54 during load | 51–55 (all) |
| Warnings / fallbacks / retries | none in run-4 log region | none |

### Timing fields (ms) — per run index 0–9

```
Pre-Python restore:  [3452, 3856, 3272, 6487, 3514, 4895, 809, 2560, 4153, 3503]
Python restore:      [ 387,  621,  471, 1535,  535,  612, 987, 1201, 1081,  462]
restore_gpu_state:   [ 194,  423,  183, 1317,  282,  263, 222,  249,  729,  249]
snapshot_restore:    [ 358,  593,  438, 1500,  468,  527, 887,  408, 1005,  431]
reload_models:       [  69,   89,  117,   90,   98,  103, 388,   70,   99,   96]
cuda_init:           [ 4.2,  4.2,  3.9,  4.9,  4.0,  4.2, 3.4,  2.6,  5.0,  4.5]
folder_warm:         [2527,  551, 1706, 1491, 1934, 1972, 798, 2643, 2397, 1844]
Pre-sampler:         [5309, 4883, 5123,10681, 4998, 4418,6490, 4933, 4824, 4756]
Checkpoint read:     [1477, 1188, 1280, 1336, 1199, 1062,1708, 1323, 1185, 1145]
get_model:           [60.2, 47.9, 40.5, 48.1, 70.8, 74.4,83.1, 63.0, 60.0, 73.7]
bind:                [25.4, 20.3, 20.6, 21.0, 37.9, 18.4,15.6, 28.1, 23.2, 36.2]
H2D (fast_disk_to):  [2455, 2333, 2433, 9229, 2421, 2008,3274, 2224, 2219, 2209]
UNETLoader total:    [4189, 3615, 3796,10653, 3752, 3186,5242, 3666, 3510, 3488]
Sampling:            [3692, 3683, 3711, 3691, 3677, 3656,3672, 3681, 3707, 3683]
VAE H2D:             [ 762,  861,  719,  869,  942,  912, 454,  914,  904,  862]
VAE decode:          [ 381,  401,  380,  379,  366,  366, 413,  377,  351,  365]
Output encode:       [ 245,  249,  251,  256,  242,  251, 261,  252,  237,  250]
Handoff:             [1037,  994, 1032,  968,  963, 1030,1302,  972,  975,  976]
PNG encode:          [ 170,  174,  174,  179,  167,  176, 169,  178,  163,  175]
Conditioning lookup: [48.8, 43.6, 42.1, 49.5, 46.4, 35.6,94.5, 52.3, 49.5, 34.3]
ImpactSwitch:        [ 625,  671,  577,  737,  578,  552,1091,  596,  618,  587]
Prefetch wall:       [ 400,   71,  306,  218,   75,  180, 509,  177,   59,   43]
Scheduling:          [1231, 1441,25927, 2313, 5935, 1615,63485, 1332, 1982,  700]
TOTAL WALL (s):      [37.3, 15.7, 15.4, 26.5, 15.4, 16.4,15.5, 15.1, 16.4, 15.0]
```

### Unavailable fields (explicitly absent; do not fabricate)

- `host_diagnostics` — **empty `{}`** in all 10 run JSONs
- `unet_backing_evidence` — **empty `{}`** in all 10
- Process/thread CPU time per stage — only boot-time monotonic `process_time_ns` (≈106–143 s, not per-run CPU); no per-stage CPU deltas
- Page-fault counters — rusage fields present but **all zeros** (`minflt/majflt/inblock/oublock/nvcsw/nivcsw = 0`) — never populated
- RSS, cgroup stats, /proc/pressure, context-switch deltas — **not logged anywhere**
- GPU clocks, pstate, PCIe gen/width, utilization, VRAM utilization — **not logged**
- Host/machine id (physical node) — **not captured**; only container-level ids (instance/session/task) exist
- VAE H2D throughput — not logged (VAE H2D wall only)
- Transfer stream identity / cudaMemcpy vs staged-copy split — not logged

---

## 4. Biggest simultaneous degradations

Ranked by ratio vs median:

1. **restore_gpu_state 5.29×** (1317.5 vs 249 ms) — inside Python restore; accounts for ≈ all of the Python-restore delta (1068 of 923 ms excess).
2. **Synchronized H2D 3.96×** (9229 vs 2333 ms; 1.33 vs ~5.3 GB/s) — inside pre-sampler; accounts for all of the pre-sampler delta.
3. **snapshot_restore 3.21×** (1500 vs 468 ms) — same object as restore_gpu_state (GPU snapshot restore is the dominant child).
4. **Python restore 2.51×** (1535 vs 612 ms).
5. **Pre-sampler 2.17×** (10681 vs 4933 ms).
6. **Pre-Python snapshot restore 1.85×** (6487 vs 3503 ms).
7. **TOTAL WALL 1.71×** (26.471 vs 15.456 s).

All seven are the *same three physical phenomena*: host-side snapshot page-in (+2.98 s), GPU-state restore (+1.07 s), and the 12.3 GB host→device copy (+6.90 s). Sum of excesses ≈ 10.95 s ≈ observed wall excess (26.47 − 15.46 = 11.01 s). **The entire extra wall time is explained by these three.**

## 5. What stayed normal

- **Checkpoint active-read: 1.336 s @ 9.22 GB/s** (median 1.199 s; slowest non-Run-4 run, AWS, was 1.708 s). The same 12.31 GB file was read from the same volume path at full speed → volume, FUSE, and page-cache hydration of the checkpoint are all healthy.
- **Sampling: 4.816 s vs median 4.806 s (1.00×)** — GPU compute path fully healthy; all 10 runs are within 4.76–4.89 s.
- UNET get_model (48 ms), bind (21 ms), read-end→constructed (0.17 ms) — all normal.
- VAE H2D (869 vs 862 ms), VAE decode (379 vs 377 ms), PNG (179 vs 174 ms), handoff (968 vs 994 ms), output encode, post-sampling transition.
- Conditioning: exact_hit, payload_memory_hit=1, lookup 49.5 ms (median 46.4), prefetch_join no timeout, `prefetch_wall_ms=218` (rank 7/10).
- PromptExecutor/cache setup 14.9 ms; cached→first-node 0.709 ms; topo_lazy_hits 36.
- Thread counts (51–55), runtime shape, GPU identity, image, fingerprint — identical.
- Scheduling 2.313 s — ordinary for us-east4 (1.2–5.9 s across the batch).
- Reconciliation −0.253 ms, STATUS OK, Fresh YES — the run is valid; nothing exceptional about validation.

## 6. Provider/region comparison

| Group | Pre-Python restore | H2D | Sampling | Wall |
|---|---|---|---|---|
| us-east4 others (6 runs) | 2.56–4.15 s | 2.21–2.45 s | 4.78–4.84 s | 15.0–16.4 s |
| us-east1 (2 runs) | 3.27–4.90 s | 2.01–2.43 s | 4.76–4.86 s | 15.4–16.4 s |
| AWS/eu-south-2 (1 run) | 0.81 s | 3.27 s | 4.88 s | 15.5 s |
| **Run 4 (us-east4)** | **6.49 s** | **9.23 s** | **4.82 s** | **26.5 s** |

- Region is **not** the explanation: 6 other us-east4 runs are all healthy (H2D 2.2–2.5 s, walls 15.0–16.4 s). Run 4 is the *only* us-east4 outlier in both restore and H2D.
- The AWS run shows the same *direction* of trade-off (slowest H2D 3.27 s, lowest pre-Python restore 0.81 s) but with far smaller magnitude and normal total wall — i.e., per-host variance exists across providers, but Run 4 is ~4× beyond even the worst other host on H2D.
- Note: pre-Python restore does **not** predict H2D (rho = −0.22 across the batch) — the two slow events in Run 4 do not generally co-occur.

## 7. Correlations (N=10; descriptive only — no significance claims)

Spearman rho, all ten runs:

| Pair | rho |
|---|---|
| Checkpoint read vs H2D | **+0.89** |
| Prefetch wall vs H2D | +0.71 |
| restore_gpu_state vs Python restore | +0.66 (restore_gpu_state dominates Python restore) |
| Scheduling vs H2D | +0.50 |
| H2D vs VAE H2D | −0.49 |
| pre-Python restore vs H2D | −0.22 |
| H2D vs Sampling | +0.22 |
| pre-Python vs Python restore | +0.25 |
| pre-Python vs checkpoint read | −0.53 |
| pre-Python vs method setup | −0.39 |
| Prefetch wall vs Sampling | −0.05 |
| read vs Sampling | +0.10 |

Interpretation with the caveat N=10, one extreme point:

- **read↔H2D (+0.89)** and **prefetch↔H2D (+0.71)** are the only strong pairings. A consistent per-host "speed baseline" ordering is plausible (hosts that read fast also transfer fast), and Run 4 is *not* an outlier on read — so the read↔H2D correlation is driven by the healthy runs; Run 4 breaks the trend (slow H2D, normal read), which itself is diagnostic: **the read path was healthy while the transfer path was not**.
- H2D↔sampling ≈ 0 and VAE H2D↔H2D negative → the slow transfer is **not** accompanied by any GPU-compute or small-transfer degradation.
- pre-Python restore and H2D are independent in the batch → Run 4's two big degradations are concurrent but not causally linked by the data we have; both point at the same host.

## 8. Unique Run 4 evidence

1. **Only run where all three large-transfer stages are simultaneously max-ranked (10/10)**: pre-Python restore, restore_gpu_state/snapshot_restore, H2D.
2. **H2D 9.23 s at 1.33 GB/s vs 2.01–3.27 s / 5.0–6.1 GB/s everywhere else** — clean 4× gap with no intermediate values (next worst host 3.27 s).
3. **restore_gpu_state 1.318 s vs 183–729 ms elsewhere** — next worst (run 8) 729 ms with a *healthy* H2D, proving restore_gpu_state and H2D can degrade independently; Run 4 has both extreme.
4. Pre-sampler delta is entirely H2D; Python-restore delta is entirely restore_gpu_state — the excesses are not "spread" across many stages but concentrated in two.
5. No unique warnings, fallbacks, retries, scheduler hints, or identity differences in the log; instance/session/task ids unique as expected for a cold run; container session shared with healthy runs.
6. `unet_fast_disk_complete` decision identical (`complete`, native_assign=false, bind_assign=true) — same transfer mechanism as healthy runs; no fallback path taken.
7. rusage counters are uniformly zero across all runs (never populated) — no page-fault/context-switch data to inspect; this is a telemetry gap, not a Run-4 anomaly.
8. `process_time_ns` ≈142.84e9 for Run 4 vs 106.6–135.8e9 elsewhere — **not** interpretable (monotonic boot clock of the container, not per-run CPU); included for completeness only.
9. Run 4 sat between healthy us-east4 runs in time (run 3 → run 4 → run 5 with 35 s gaps) — a transient *batch-wide* condition is excluded.

## 9. Ranked root-cause hypotheses

| # | Hypothesis | Supporting | Contradicting | Confidence | Telemetry that would prove it |
|---|---|---|---|---|---|
| 1 | **Bad host: degraded memory/PCIe-class transfer path on the specific worker** (co-tenant bandwidth contention or link/uncore issue) | All large transfers slow (H2D 4×, GPU-state 5.3×, snapshot page-in 1.85×); small transfers, compute, disk all normal; read↔H2D correlation broken by this run only | Cannot distinguish memory vs PCIe without counters; run 8 had GPU-state anomaly with healthy H2D | **Medium-high** | PCIe gen/width + NVIDIA clocks/pstate at H2D; /proc/pressure/memory + memory; cgroup memory.stat; H2D staging vs cudaMemcpy split |
| 2 | **Snapshot-hydration + GPU-restore + H2D resource contention on a noisy host** (each individually plausible, all three hitting at once) | Matches simultaneous timing; no single-stage code change needed | They are sequential (restore before pre-sampler), so not overlapping each other; implies an external noise source anyway | Medium | /proc/pressure/*, cgroup cpu.stat/memory.events, host CPU load sampling |
| 3 | **PCIe link/GPU-fabric degradation (link width or error-retry behavior)** | H2D 4× and GPU-state restore 5.3×; GPU compute (sampling) unaffected; disk read unaffected | VAE H2D (also PCIe) is normal — though it is ~1 GB vs 12.3 GB, so bandwidth-bound only at the large end; no nvidia-smi data to confirm | Medium | nvidia-smi pstate/clocks/PCIe (or pynvml) sampled around H2D; cuMemcpy vs staged split; xid errors in dmesg |
| 4 | **Host CPU throttling / memory-bandwidth cgroup throttling** | Snapshot page-in and GPU-state restore are CPU/memory heavy | Checkpoint read (equally memory-heavy) is fast; sampling normal | Low | /proc/pressure/cpu, cgroup cpu.stat throttled_us, getrusage deltas |
| 5 | **NUMA placement / far-memory allocation** | Would explain transfer slowness on one host | No NUMA data exists; can't confirm | Low | /proc/self/numa_maps, numa node ids in smaps_rollup, allocation policy |
| 6 | **GPU hardware issue** | GPU-state restore slow | Sampling and VAE decode (pure GPU compute) are perfectly normal | Low | GPU clocks/util during sampling; ECC/xid errors |
| 7 | **Application/regression** | — | Identical code, 9 healthy runs, same fingerprint, no fallback path | Very low | — |
| 8 | **Volume/FUSE/network restore delay** | Pre-Python restore slow | Checkpoint read of same volume normal | Low | active-read latency breakdown; volume metrics |

## 10. Is H2D root cause or symptom?

**Symptom.** Three independent lines of evidence:

1. **Causally prior stages were slow first.** Pre-Python restore (6.49 s) and restore_gpu_state (1.32 s) precede the H2D in the run's critical path and are degraded independently of it. The H2D code path is byte-identical to the nine healthy runs (same `unet_fast_disk_to`/`bind`/`pagein` events, same decision flags, no fallback).
2. **The same run's disk I/O of the same bytes was fast.** The checkpoint read moved the same 12.31 GB from the volume at 9.22 GB/s — the slowness appears only at the host→device boundary, i.e., the transfer path specific to this worker.
3. **GPU compute was untouched.** Sampling at 1.00× median and VAE decode at 1.01× show the GPU and driver compute path are healthy; a defect in the transfer code would not selectively slow 12.3 GB copies while leaving 1 GB VAE copies and all compute at baseline.

H2D is the largest *visible* victim, which is why it dominates the pre-sampler delta — but it is one of three concurrently degraded large-memory-movement operations on a single host. Treating "H2D is slow" as the defect would misdirect the fix at the transfer implementation instead of the worker.

## 11. Telemetry missing today

- No physical-host identifier (only container-level instance/session/task ids) → cannot attribute recurrence to the same machine.
- No NVIDIA state: pstate, clocks, PCIe gen/width, utilization, VRAM, ECC/xid errors.
- No /proc/pressure/{cpu,memory,io}; no cgroup v2 cpu.stat/memory.events/memory.current/io.stat.
- No getrusage deltas: minflt/majflt/nvcsw/nivcsw are captured as fields but are **always zero** (unpopulated) — the plumbing exists but nothing fills it.
- No RSS/smaps_rollup snapshots; no NUMA info.
- H2D has wall only: no staging-copy vs device-copy split, no cudaEvent sync timing, no stream id, no per-tensor transfer timeline.
- VAE H2D throughput not computed; pre-Python restore has no internal breakdown (page-in vs network vs decompress).

## 12. Exact low-overhead instrumentation plan

Do **not** implement now. Five snapshot points (cheap, ~1–2 ms total per run, <0.02% of a 15 s run):

**Snapshot points**
1. **Python resume** (first line of remote method): full snapshot.
2. **Immediately before UNET read** (`read_start` event site): full snapshot.
3. **Immediately before H2D** (`unet_fast_disk_to_start`): full snapshot + `torch.cuda.synchronize()` pre-arm.
4. **Immediately after H2D** (`unet_fast_disk_to_end`): full snapshot + sync elapsed + copy-stream attribution.
5. **Sampling start**: full snapshot + GPU clocks/pstate + `torch.cuda.utilization` equivalent (via pynvml).

**Full snapshot contents (each ≈ 100–300 µs):**
- `resource.getrusage(RUSAGE_SELF)` deltas since last point: utime/stime, minflt, majflt, nvcsw, nivcsw, inblock, oublock.
- `psutil.Process().memory_info()` RSS/VMS or `/proc/self/status` VmRSS/VmHWM + `smaps_rollup` totals (Rss, Pss, Private).
- `/proc/pressure/cpu`, `/proc/pressure/memory`, `/proc/pressure/io` (parse `avg10`/`avg60`/`total`).
- cgroup v2 (if `/sys/fs/cgroup/cpu.max` exists): `cpu.stat` (usage_usec, throttled_usec), `memory.events` (throttling counters, oom), `memory.current`, `memory.stat` (pgfault, pgmajfault, workingset), `io.stat`.
- Thread count + `threads` snapshot via `/proc/self/task` count.
- `torch.cuda.current_device()`, `torch.cuda.get_device_properties`, `cudaGetLastError` (cheap), and a **single** `torch.cuda.Event` pair armed at H2D start, elapsed at end (µs-level sync timing of the copy).
- pynvml (≈1–5 ms, do **once per snapshot, not per tensor**): clock SM/mem, pstate, PCIe current gen/width (`nvmlDeviceGetCurrPcieLinkGeneration/Width`), utilization, memory used, ECC errors + last xid.

**GPU/PCIe detail at points 3–4 only** (higher cost, ~10–20 ms): `nvidia-smi -q -d CLOCK,PCI,UTILIZATION,ECC,POWER` once before H2D and once after — proves link/gen/width and throttle state exactly during the transfer.

**Torch/CUDA context first-touch:** log `torch.cuda.caching_allocator` device + a one-time `torch.cuda.memory_stats()` diff at snapshot 1 (context init cost) and snapshot 3→4 (transfer allocation).

**Overhead estimate:** snapshots 1,2,5 ≈ 0.3–0.5 ms each; snapshot 3/4 ≈ 2 ms (plus one 10–20 ms nvidia-smi if enabled). Total ≤25 ms/run ≈ 0.1% of wall — negligible. Optionally gate the nvidia-smi pair behind a trigger (see §13) so healthy runs pay ≈1–2 ms total.

**Host identity:** capture a host fingerprint at snapshot 1 (e.g., `os.uname().nodename`, `machine-id` from `/etc/machine-id`, and Modal env vars for the worker/pool) so recurrence can be attributed to the same physical node.

## 13. Trigger criteria for flagging a future similar incident

Flag "bad-host candidate" when **any two** of these fire on a run (all measurable with today's data, no new instrumentation needed):

1. **H2D wall > 4.0 s** (≈1.7× the healthy max of 3.27 s; Run 4 hit 9.2 s). Trigger telemetry at H2D start once past 4 s.
2. **restore_gpu_state > 800 ms** (≈2.5× median; Run 4 hit 1318 ms).
3. **pre-Python restore > 6.0 s** (Run 4 hit 6.49 s; healthy max 4.90 s).
4. **Pre-sampler > 8.0 s** and **TOTAL WALL > 20 s** jointly (rules out single-stage noise).
5. **H2D ratio vs rolling median > 3×** while checkpoint-read ratio < 1.5× — the specific "slow transfer, healthy disk" signature of §7.

Escalation: when the trigger fires, retain the run artifact, enable the nvidia-smi pair and deep counters for the *next* run (to catch the same host again), and record the host fingerprint. Do **not** treat a single stage in isolation — require the two-of-five rule to avoid flagging one-off platform variance (e.g., scheduling outliers like runs 3/7's 26–63 s scheduling).

## 14. Recommended next action

1. **Re-run the same 10-cold-run batch once** with instrumentation §12 (snapshot points 1–5, host fingerprint, H2D gated nvidia-smi) — cheap, no code-path changes, directly tests the bad-host hypothesis: if the slow-run pattern recurs with a distinct host fingerprint, the host explanation is confirmed; if it never recurs, quantify per-host variance (the batch already shows read↔H2D correlation implying host baselines exist).
2. If it recurs: correlate fingerprint + PCIe gen/width + pressure files to discriminate hypothesis 1 (memory vs PCIe contention) and report the host to the provider (Modal/GCP) as a suspected noisy neighbor.
3. In parallel, fix the **always-zero rusage plumbing** (§11) — the fields exist but nothing populates them; this is the single cheapest telemetry win.
4. Do **not** change the H2D implementation or the fast-disk path based on this run: evidence points to the worker, not the code (identical path ran 5.3 GB/s on nine hosts).

---

*Analysis notes: all values from the authoritative dataset MD and the run JSONs/log listed in the header; unavailable fields are marked explicitly in §3 and were never fabricated. N=10, so correlations are descriptive only. Run artifacts were found at the ComfyUI-root `comfymodal-data` path (the log's `[v2.experiment] saved=` line), not the custom-node-local copy.*
