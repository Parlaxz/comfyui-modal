# Always-On Sentinel Campaign — Localization Deliverable

Scope: diagnosis only. No Golden changes, no QD/block-size/priming changes, no mitigation, no retries/hedging.

- Campaign: 11 fresh H100 containers (hard cap 25), stopped when >=3 large episodes and >=3 clean runs existed.
- Large episode: worst normal source read >= 500 ms. Clean run: no read >= 250 ms.
- Engine: `comfymodal_runtime/source_race_oracle.py::run_sentinel_probe`
- App: `e04_source_race_modal.py::run_sentinel_h100` (Testing 4)
- Runner: `tools/run_sentinel_campaign.py` (`--smoke` and campaign modes)
- Analysis: `tools/analyze_sentinel.py`, `tools/analyze_sentinel_cpu.py`, `tools/analyze_sentinel_recovery.py`
- Raw: `sentinel_runs/sn-r01..r11.json`, `sentinel_runs/{campaign.log,analysis.txt,cpu_analysis.txt,recovery.txt}`, smoke arms `sentinel_runs/smoke-*.json`

---

## 1. Executive summary

**The blocking domain is the main Python process's own execution — not the sandbox, not the model file, not the Volume, not the gVisor filesystem.**

The decisive instrument was the separate-PID CPU canary: a pure-userspace spin loop (no syscalls in steady state, `perf_counter_ns` confirmed vDSO at 60 ns/op vs `getpid` 1225 ns/op). During a **1583 ms** source freeze, that canary never lost its 2 ms cadence (max gap **2.26 ms**), while the main process's heartbeat stalled **1541 ms** and every one of its I/O sentinels stalled for essentially the whole episode.

Sentinels during the three large episodes (scheduling delay / syscall latency, ms):

| run | episode | A model file | B other same-Volume file | C tmpfs | canary gap | main hb gap |
|---|---|---|---|---|---|---|
| sn-r02 | 1583 ms, 3 workers | 1580 / 330 | 1538 / 329 | 1577 / 18 | **2.26** | 1541 |
| sn-r03 | 986 ms, 4 workers | 711 / 1.0 | 711 / 1.9 | 711 / 1.0 | **6.65** | 731 |
| sn-r11 | 998 ms, 4 workers | 1607 / 149 | 830 / 1629 | 980 / 21 | **7.30** | 778 |

tmpfs has no disk path at all, yet it freezes identically to the model file and to a second file on the same Volume. So there is **no file, Volume, or filesystem-domain specificity**. Within the frozen process the stall is dominated by *scheduling delay* (couldn't run), not *syscall latency* (r03: 711 ms scheduling vs 1.0 ms syscall for all three paths).

Recovery is **instant**, not gradual: median sentinel latency is back to 0.13–0.27 ms within the first 0–100 ms after each episode ends. This corrects the previous campaign's "15–60x recovery tail", which was an artifact of triggered probes queueing behind the workers' refill.

Two instrument-validity results also matter:
- `perf_counter_ns`/`monotonic_ns` are **vDSO-backed** (60 ns/op), so a wall-clock heartbeat gap cannot be a "stalled clock syscall" artifact. That alternative is now excluded.
- `time.process_time_ns()` is **unreliable in this environment**: it reports 262–777% of wall time even in clean runs, which is physically implausible for an I/O-bound process. Deliverable 7 is therefore reported as inconclusive, and no conclusion rests on it.

The mechanism behind a process-local freeze is **not** established by this data. The GIL is the leading hypothesis for a process-wide freeze that spares a separate PID, but this campaign did not instrument the GIL and does not prove it.

---

## 2. Instrumentation topology

Threads (main Python process):
- **4 source workers** — unchanged base workload: 64 MiB reads, QD4, persistent FDs, reusable buffers, 120 blocks, no primer, `qwen_3_4b.safetensors`.
- **main heartbeat** — 2 ms cadence, records `(perf_counter_ns, process_time_ns, seq)`.
- **sentinel A** — pre-opened FD on the model file, fixed range = last 256 KiB, preallocated 256 KiB buffer, 25 ms cadence.
- **sentinel B** — pre-opened FD on `/root/models/diffusion_models/z_image_turbo_bf16.safetensors` (`st_dev=31`, same device as the model), fixed offset 0, 256 KiB.
- **sentinel C** — pre-opened FD on `/tmp/c0_sentinel_local.bin` (`st_dev=18`, tmpfs), fixed offset 0, 256 KiB.

Separate process:
- **CPU canary** — `os.fork()` child, PID distinct, pure userspace spin, **no I/O and no syscalls in steady state**. Records `(perf_counter_ns, seq)` every 2 ms into an anonymous `mmap` shared mapping, plus `(perf_counter_ns, process_time_ns)` every 50 ms. Stopped and read via the shared mapping — never through disk.

Ordering guarantee (no diagnostic resource is created in response to sickness):
1. stat identities, create the tmpfs file
2. open sentinel FDs + allocate sentinel buffers
3. `mmap` + `fork` the canary
4. start heartbeat and sentinel threads
5. allocate worker buffers, open worker FDs
6. start worker threads

Every sentinel FD, buffer and range exists before the worker threads start, and all diagnostics run continuously. `settle_ms` is an explicit knob; the campaign used **0** (see §3).

Read size 256 KiB at 25 ms cadence = ~10 MB/s per sentinel, ~30 MB/s total against a ~4–5 GB/s source. Fixed for all sentinels.

---

## 3. Perturbation validation

Three-arm smoke, 3 runs per arm, plus a fourth arm added to break a confound:

| arm | diagnostics | settle_ms | n | clean (<250 ms) | sick >=500 ms | median gbps (all) | median refill gap | max refill gap |
|---|---|---|---|---|---|---|---|---|
| smoke-off | False | 0 | 3 | 0 | 3 | 2.16 | 0.017 ms | 0.1 ms |
| smoke-offs | False | 150 | 3 | 0 | 1 | 4.58 | 0.015 ms | 0.0 ms |
| smoke-on | True | 150 | 3 | 3 | 0 | 4.91 | 0.009 ms | 0.1 ms |
| smoke-on0 | True | 0 | 3 | 1 | 2 | 2.89 | 0.010 ms | 0.1 ms |

Findings:
- **QD unchanged**: per-worker read counts are exactly `{0:30, 1:30, 2:30, 3:30}` and balanced in all 12 smoke runs and all 11 campaign runs.
- **Refill gaps unchanged**: median 0.009–0.017 ms across all arms; no systematic degradation with diagnostics on. One 23.9 ms outlier in one ON run did not recur.
- **Sentinel traffic negligible**: ~300–370 samples per run.
- **No throughput destruction**: the fastest arms are the diagnostics-ON arms.
- **The settle delay, not the diagnostics, changes the phenomenon.** `smoke-off` (no diagnostics, settle 0) was 3/3 sick; `smoke-offs` (no diagnostics, settle 150) was 1/3 sick; `smoke-on` (diagnostics, settle 150) was 0/3 sick; `smoke-on0` (diagnostics, settle 0) was 2/3 sick. So diagnostics do not suppress pathology — delaying worker start by 150 ms does.

Because `settle_ms=150` was my own addition and it materially changed the observed phenomenon, the campaign used **settle_ms=0**, which preserves the original base probe's worker-start timing (workers start immediately) while still creating every diagnostic before the worker threads.

Caveat: the canary busy-spins one CPU for the duration. Declared container CPU is 12. The measured effect is not throughput destruction (ON arms were fastest), but a busy-spinning process is not a zero-cost instrument and this is not a fully clean perturbation control.

---

## 4. Per-run summary

Values are **in-episode** (restricted to the worst source episode). "whole-run hb" is the max main-process heartbeat gap over the entire run, which includes the pre-source setup phase.

| run | region | severity | whole-run hb | in-ep hb | canary in-ep | A sched/lat | B sched/lat | C sched/lat | classification |
|---|---|---|---|---|---|---|---|---|---|
| sn-r01 | GCP/us-east | 299 | 1008 | 205 | 2.00 | 983 / 22 | 183 / 1007 | 204 / 23 | CASE B |
| sn-r02 | GCP/us-west | **1583** | 1541 | **1541** | **2.26** | 1580 / 330 | 1538 / 329 | 1577 / 18 | **CASE B** |
| sn-r03 | GCP/us-east4 | **986** | 731 | **731** | **6.65** | 711 / 1.0 | 711 / 1.9 | 711 / 1.0 | **CASE B** |
| sn-r04 | GCP/us-east5 | 130 | 129 | – | 3.30 | – | – | – | CLEAN |
| sn-r05 | GCP/us-west | 140 | 96 | – | 2.01 | – | – | – | CLEAN |
| sn-r06 | GCP/asia-south2 | 453 | 4585 | 11 | 9.46 | 32 / 0.4 | 32 / 0.7 | 32 / 0.3 | unclear (no main-process stall) |
| sn-r07 | GCP/us-east5 | 237 | 448 | – | 4.55 | – | – | – | CLEAN |
| sn-r08 | UNSPECIFIED/us-central | 228 | 141 | – | 2.12 | – | – | – | CLEAN |
| sn-r09 | GCP/us-east | 257 | 254 | 254 | 2.41 | 237 / 27 | 240 / 49 | 237 / 27 | CASE B |
| sn-r10 | GCP/us-west4 | 143 | 157 | – | 2.04 | – | – | – | CLEAN |
| sn-r11 | GCP/asia-northeast1 | **998** | 1629 | **778** | **7.30** | 1607 / 149 | 830 / 1629 | 980 / 21 | **CASE B** |

Canary mode was `separate_pid` in all 11 runs. Canary whole-run max gap: 2.0–11.1 ms in 10 runs; **258.7 ms in sn-r06**, which occurred at t=-1055 ms (during setup, before the source window) — the only canary stall of the campaign and it did not coincide with a source episode.

`unclear` for sn-r06: it has a 453 ms worst read but the main-process heartbeat gap inside that episode is only 11 ms, and sentinel scheduling delays are only 32 ms. That episode is not explained by a main-process freeze and is not forced into a case.

---

## 5. Detailed timelines for large episodes

### sn-r02 EP#0 — 1583 ms, workers [0,1,3], main process frozen, canary unaffected

```
t=0      source w0/w1/w3 preadv  |===============================|  exit 1583 ms
         (w2 short read)

         MAIN PROCESS (heartbeat, sentinels A/B/C)
         |......................................... 1541 ms GAP ................|

         SEPARATE-PID CPU CANARY
         tick tick tick tick tick tick tick tick tick tick tick tick tick tick   (max gap 2.26 ms)
         canary consumed 1460 ms CPU in the 1583 ms window (92% of wall)

         A same-file (pre-opened FD, last 256 KiB)      sched 1580 ms | lat 330 ms
         B other same-Volume file                       sched 1538 ms | lat 329 ms
         C tmpfs                                        sched 1577 ms | lat  18 ms
t=1583   source + all three sentinels release together
```

### sn-r03 EP#1 — 986 ms, all 4 workers, scheduling delay with clean syscalls

```
t=551    source w0..w3 preadv    |=========================|  exit 1537 ms (worst 986 ms)
         MAIN PROCESS            |..... 731 ms GAP ........|
         CANARY                  tick tick tick ... (max gap 6.65 ms; 920 ms CPU / 986 ms wall = 93%)
         A model file            sched 710.9 ms | syscall latency 1.03 ms
         B other Volume file     sched 710.6 ms | syscall latency 1.89 ms
         C tmpfs                 sched 710.5 ms | syscall latency 0.97 ms
t=1537   everything releases together
```

This is the cleanest scheduling-vs-syscall separation in the campaign: all three sentinels waited ~711 ms for the CPU and then completed their 256 KiB read in ~1 ms.

### sn-r11 EP#0 — 998 ms, all 4 workers

```
t=0      source w0..w3 preadv    |================|  exit 998 ms
         MAIN PROCESS            |.. 778 ms GAP ...|
         CANARY                  tick tick ... (max gap 7.30 ms; 940 ms CPU / 998 ms wall = 94%)
         A model file            sched 1607 ms | lat 149 ms
         B other Volume file     sched  830 ms | lat 1629 ms
         C tmpfs                 sched  980 ms | lat   21 ms
t=998    release
```

A and C show large scheduling delay with modest syscall latency; B shows a large syscall latency on one sample. Mixed within a single process-wide freeze — reported as-is, not forced.

### sn-r09 EP#0 — 257 ms, workers [1,2,3]

```
t=0      source w1..w3 preadv    |=========|  exit 257 ms
         MAIN PROCESS            |254 ms GAP|
         CANARY                  tick tick (max gap 2.41 ms)
         A / B / C               sched 237 / 240 / 237 ms | lat 27 / 49 / 27 ms
```

Same shape at ~250 ms scale: a 254 ms main-process gap, canary fine, all three sentinels stalled ~238 ms.

---

## 6. Clean-run baseline

Runs with no source episode >= 250 ms. Values are `median/max` over the whole run, in ms.

| run | A model file sched / lat | B other-Volume sched / lat | C tmpfs sched / lat |
|---|---|---|---|
| sn-r04 | 0.56 / 50.3 , 0.15 / 129.2 | 0.47 / 80.0 , 0.15 / 129.3 | 0.41 / 50.1 , 0.14 / 186.2 |
| sn-r05 | 0.57 / 83.4 , 0.12 / 49.6 | 0.47 / 83.6 , 0.14 / 49.7 | 0.58 / 83.3 , 0.13 / 24.7 |
| sn-r07 | 0.29 / 423.0 , 0.17 / 136.4 | 0.45 / 232.2 , 0.16 / 447.4 | 0.47 / 232.2 , 0.17 / 18.0 |
| sn-r08 | 0.37 / 137.8 , 0.13 / 31.2 | 0.41 / 16.5 , 0.14 / 140.7 | 0.57 / 15.2 , 0.12 / 136.7 |
| sn-r10 | 0.51 / 139.9 , 0.18 / 157.0 | 0.62 / 101.2 , 0.16 / 95.2 | 0.64 / 44.1 , 0.16 / 130.9 |

Baseline: **median scheduling delay 0.29–0.64 ms, median syscall latency 0.12–0.18 ms** for all three paths — identical across model file, other Volume file and tmpfs.

Important: "clean" is not stall-free. sn-r07 has no source episode but shows a 423 ms max scheduling delay on A and a 447 ms max syscall latency on B. The phenomenon is a continuum.

---

## 7. Wall-time vs process-time analysis — **INCONCLUSIVE**

Raw result (main heartbeat, largest gaps):

| run | wall gap | process CPU-time delta | ratio |
|---|---|---|---|
| sn-r02 | 1541.4 ms | 11980 ms | 777% |
| sn-r03 | 730.6 ms | 4880 ms | 668% |
| sn-r11 | 777.8 ms | 5290 ms | 680% |
| sn-r04 (clean) | 128.9 ms | 740 ms | 574% |
| sn-r05 (clean) | 95.9 ms | 550 ms | 573% |
| sn-r08 (clean) | 141.1 ms | 370 ms | 262% |

The ratio exceeds 100% in **every** run, including clean ones, and implies 3–8 threads burning CPU continuously — implausible for a workload whose threads are blocked in `preadv` or sleeping.

Interpretation: `CLOCK_PROCESS_CPUTIME_ID` under gVisor is not behaving as a trustworthy per-process CPU-time clock in this environment (it is also syscall-backed at 1446 ns/op). Possible causes not distinguishable from this data: the clock includes container-wide or Sentry CPU, or it advances on a wall-like basis.

Consequence: the intended discriminator "large wall gap + tiny CPU delta => descheduled" **could not be applied**. I do not claim the process was descheduled, nor that it was CPU-busy, on the basis of this clock. The canary's own `process_time` shows the same anomaly (e.g. sn-r06: 250 ms CPU delta across a 258.7 ms wall gap).

The classification in §1 rests only on wall-clock evidence (`perf_counter_ns`), which is vDSO-backed and therefore trustworthy.

---

## 8. Scheduling-delay vs syscall-delay

Separated by construction: each sentinel records intended-issue, actual syscall-enter and exit.

| episode | path | scheduling delay | syscall latency | ratio |
|---|---|---|---|---|
| sn-r03 EP#1 (986 ms) | A model file | 710.9 ms | 1.03 ms | 690x |
| | B other Volume file | 710.6 ms | 1.89 ms | 376x |
| | C tmpfs | 710.5 ms | 0.97 ms | 732x |
| sn-r02 EP#0 (1583 ms) | A model file | 1579.7 ms | 329.9 ms | 4.8x |
| | B other Volume file | 1538.0 ms | 329.4 ms | 4.7x |
| | C tmpfs | 1577.2 ms | 18.0 ms | 88x |
| sn-r11 EP#0 (998 ms) | A model file | 1606.5 ms | 149.0 ms | 10.8x |
| | B other Volume file | 829.8 ms | 1629.2 ms | 0.5x |
| | C tmpfs | 980.2 ms | 21.1 ms | 46x |
| clean baseline | all paths | 0.29–0.64 ms | 0.12–0.18 ms | ~2x |

**Scheduling delay dominates.** In the cleanest episode (sn-r03) the sentinels waited ~711 ms for CPU and then completed the read in ~1 ms. Even where a syscall component exists (sn-r02, ~330 ms), it is smaller than the scheduling component and affects all three paths together.

---

## 9. Recovery-tail analysis

Samples after each large episode ends, bucketed by time since episode end. Values are `median / max` syscall latency (ms), with sample count.

| run / episode | 0–100 ms | 100–250 ms | 250–500 ms | 500–1000 ms | >1000 ms |
|---|---|---|---|---|---|
| sn-r02 EP#0 | A 0.13/0.21 (4), B 0.15/0.29 (3), C 0.27/0.35 (4) | A 0.26/0.32 (6) | A 0.14/0.30 (9) | – | A 0.16/38.1 (85) |
| sn-r02 EP#1 | A 0.16/0.21 (3) | A 0.16/0.49 (7) | A 0.15/0.22 (9) | A 0.25/38.1 (18) | A 0.15/0.32 (46) |
| sn-r03 EP#0 | A 0.15/0.47 (5) | A 0.18/0.50 (6) | A 0.18/0.69 (10) | A 0.17/0.50 (19) | A 0.13/38.0 (44) |
| sn-r11 EP#0 | A 0.13/0.26 (4) | A 0.12/0.32 (6) | A 0.14/0.54 (10) | A 0.19/0.40 (19) | A 0.16/1.24 (66) |

(B and C track A within noise; omitted for width.)

**Recovery is instant, not gradual.** Median latency in the 0–100 ms bucket after each episode is 0.12–0.27 ms — baseline — for all three paths. There is no decaying tail. The occasional max spikes (38 ms, 101 ms) are isolated samples, not a systematic tail.

This corrects the previous campaign's finding of a "15–60x recovery tail including tmpfs": those measurements came from probes that fired *after* the stall had already cleared and then queued behind the four workers re-issuing 64 MiB reads. With sentinels that were already in flight, no such tail exists.

---

## 10. Evidence table

| Finding | Episodes | Confidence | Implication |
|---|---|---|---|
| Separate-PID pure-userspace canary keeps executing during source freeze | 3/3 large (gaps 2.26, 6.65, 7.30 ms vs 731–1541 ms main-process freeze); 10/11 runs overall | High | The sandbox/host kept scheduling. CASE A excluded. |
| Main Python process freezes | 4 episodes (r01, r02, r03, r09, r11) | High | Freeze is process-local. |
| tmpfs sentinel freezes identically to the model file | 3/3 large (711/711/711; 1577 vs 1580) | High | No filesystem-domain specificity. CASE C/D/E excluded. |
| Second file on the same Volume freezes identically | 3/3 large | High | CASE D excluded. |
| Sentinels do freeze (they are not spared) | 3/3 large | High | CASE F excluded — it is not only the worker cohort. |
| Stall is scheduling delay, not syscall latency | r03 711 ms sched vs 1.0 ms lat for all three paths | High | The threads could not run; the reads themselves were healthy once scheduled. |
| Recovery is instant | 4 large episodes, 0–100 ms bucket median 0.12–0.27 ms | High | No gradual sandbox/fs recovery. Corrects prior "recovery tail". |
| `perf_counter_ns` is vDSO-backed (60 ns/op vs getpid 1225 ns/op) | 1 calibration per ON run | High | Wall-clock gaps cannot be stalled-clock artifacts. |
| `process_time_ns` is unreliable here (262–777% of wall in clean runs) | all 11 runs | High | Deliverable 7 inconclusive; no conclusion rests on it. |
| Diagnostics do not suppress pathology | 4-arm smoke | Medium (n=3/arm) | The 150 ms settle delay, not instrumentation, changes the phenomenon. |
| Canary stalled once, 258.7 ms, during setup | sn-r06 at t=-1055 ms | Medium | Not coincident with any source episode; unexplained but isolated. |
| Clean runs still contain stalls | sn-r07: 423 ms sched, 447 ms syscall latency | Medium | Phenomenon is a continuum, not binary. |

---

## 11. Direct answers

**Does a separate PID continue executing during the source stall?**
Yes. During a 1583 ms source freeze the pure-userspace canary never lost its 2 ms cadence (max gap 2.26 ms), and across all 11 runs its max gap was 2.0–11.1 ms except one 258.7 ms stall during setup.

**Is the whole sandbox actually descheduled?**
No. A separate process in the same container kept executing throughout. CASE A is excluded.

**Is only the main Python process affected?**
Yes. That is the finding.

**Do pre-existing filesystem sentinels ENTER their syscalls on schedule?**
No. All three show 711–1580 ms of *scheduling* delay — they could not run.

**If they enter, which source domains actually block?**
None is spared. Model file, a second file on the same Volume, and tmpfs all block by the same amount at the same time.

**Does tmpfs block during the same episode?**
Yes, identically (711 / 711 / 711 ms in sn-r03).

**Does the alternate file on the same Volume block?**
Yes, identically to the model file (1538 vs 1580 ms in sn-r02).

**Does the same-file independent reader block?**
Yes. A pre-opened, preallocated, fixed-range FD on the model file stalled 711–1607 ms.

**Are delays primarily scheduling delay or syscall latency?**
Scheduling delay. sn-r03: 711 ms scheduling vs ~1 ms syscall for all three paths. Where a syscall component exists (sn-r02, ~330 ms) it is smaller and equally shared.

**Is there a gradual post-stall recovery?**
No. Recovery is instant — median latency is back to baseline (0.12–0.27 ms) within 0–100 ms of episode end.

**Which of CASE A–F best fits?**
**CASE B — main process only.** A, C, D, E and F are each excluded by direct evidence.

**What is now the narrowest defensible owner/state domain?**
**The main Python process's own execution** — its threads' ability to be scheduled. Not the sandbox, not the model file, not the Volume, not the gVisor filesystem, and not the worker cohort alone.

**What is not established:** the mechanism. A process-wide freeze that spares a separate PID is most simply explained by the GIL, but this campaign did not instrument the GIL, and the `process_time` clock needed to test "descheduled vs CPU-busy" is unreliable in this environment. That is the next thing to measure, and it needs a trustworthy per-thread/per-process CPU accounting source or direct GIL instrumentation — not another source-geometry sweep.
