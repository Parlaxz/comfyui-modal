# THREADS vs PROCESSES — matched QD4 / 64 MiB / 4.0 ms / H100

**Question:** at identical QD4 / 64 MiB / 4.0 ms geometry, does replacing four reader threads in one process with four independent one-reader processes increase real full-file source throughput?

**Answer: yes, but the headline number is inflated by a region confound and by two catastrophic threads runs. The defensible effect is roughly +16% to +19%, not +36%.**

- Schedule seed `20260924`, 10 paired rounds, positional balance 5/5, persisted before launch.
- 20/20 runs accepted as valid H100 on the first attempt; **no reruns, no rebalancing**.
- Artifacts: `worker_model_runs/{ANALYSIS.txt, per_run_metrics.csv, pooled_reads.csv, schedule.json, wm-*.json}`
- Engine: `comfymodal_runtime.source_race_oracle.run_worker_model_probe` · Function: `run_worker_model_h100`

---

## 1. Validity — both arms provably identical except the worker model

| check | threads | processes |
|---|---|---|
| configured QD | 4 | 4 |
| reads per run | 120 | 120 |
| bytes per run | 8,044,982,048 | 8,044,982,048 |
| exact once-only coverage | True ×10 | True ×10 |
| max simultaneous in-flight | 4 (never more) | 4 (never more) |
| min claim-to-claim gap | 4.0095 ms | 4.0039 ms |
| worker PIDs | **1** | **4** |
| worker TIDs | 4 | 4 |
| mp start method | fork | fork |
| worker errors / barrier errors | none | none |

**The process arm did not become QD8 and did not get four independent pacers.** All 10 process runs show exactly 4 distinct PIDs (one read stream each), max in-flight never exceeded 4, and one global 4.0 ms claim floor held.

Cache-warming was excluded by construction: buffers are allocated empty, the FD is opened, both barriers are entered, and only then does the timed region start. `spawn→all-ready` was measured separately (threads 53.4 ms, processes 90.9 ms median) and is **not** inside the wall.

One rigor fix surfaced during local validation: the pacer gates the **claim**, while `preadv_enter` is a later clock read, so an enter-to-enter gap can land a hair below the floor. The gate is now verified on `observed_min_global_claim_gap_ms` (the quantity the pacer actually controls) and both arms pass.

## 2. Headline table

| metric | 4 threads / 1 process | 4 processes / 1 reader each |
|---|---:|---:|
| runs | 10 | 10 |
| median GB/s | **4.718** | **6.431** |
| mean GB/s | **4.572** | **5.930** |
| best GB/s | 6.442 | 7.165 |
| worst GB/s | 1.350 | 2.805 |
| GB/s SD | 1.722 | 1.357 |
| median source wall ms | 1706 | 1257 |
| mean source wall ms | 2331 | 1468 |
| best source wall ms | 1249 | 1123 |
| worst source wall ms | 5957 | 2868 |
| pooled preadv median ms | 41.39 | 40.39 |
| pooled preadv mean ms | 54.24 | 47.29 |
| preadv p95 ms | 76.90 | 83.63 |
| preadv p99 ms | 174.97 | 127.93 |
| worst preadv ms | 3787.4 | 199.3 |
| reads ≥250 | 8 | **0** |
| reads ≥500 | 5 | **0** |
| reads ≥1000 | 2 | **0** |
| runs ≥500 | 2 | **0** |
| runs ≥1000 | 2 | **0** |
| effective concurrency | 3.249 | 3.852 |
| overlap | 0.9700 | 0.9900 |
| max active | 4 | 4 |

**PROCESS median GB/s delta: +1.713 (+36.3%)**
**PROCESS mean GB/s delta: +1.358 (+29.7%)**

## 3. Paired analysis

| round | threads GB/s | processes GB/s | delta | delta % | tWall | pWall | wall delta |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4.591 | 7.165 | +2.574 | +56.1% | 1752 | 1123 | −629 |
| 2 | 6.052 | 2.805 | −3.247 | −53.6% | 1329 | 2868 | +1538 |
| 3 | 6.442 | 6.896 | +0.454 | +7.0% | 1249 | 1167 | −82 |
| 4 | 1.610 | 5.985 | +4.375 | +271.8% | 4998 | 1344 | −3654 |
| 5 | 6.226 | 4.933 | −1.293 | −20.8% | 1292 | 1631 | +339 |
| 6 | 5.924 | 5.820 | −0.104 | −1.8% | 1358 | 1382 | +24 |
| 7 | 4.845 | 7.149 | +2.303 | +47.5% | 1660 | 1125 | −535 |
| 8 | 1.350 | 7.016 | +5.666 | +419.6% | 5957 | 1147 | −4811 |
| 9 | 4.515 | 4.655 | +0.140 | +3.1% | 1782 | 1728 | −54 |
| 10 | 4.165 | 6.877 | +2.712 | +65.1% | 1932 | 1170 | −762 |

- median paired GB/s delta **+1.379 (+27.3%)**
- mean paired GB/s delta **+1.358**
- median paired wall delta **−309 ms** (processes faster)
- **pairs PROCESS > THREAD: 7/10** · threads > process: 3/10
- paired bootstrap 95% interval on the median delta: **[−0.576, +3.475] GB/s** (10 000 resamples, seed 20260924)

**The interval includes zero.** With n=10 and two threads runs dominated by a single 3.8 s stall, the paired evidence is directional but not decisive on its own.

## 4. Region confound — the single most important caveat

Modal placed the two arms in **different regions**, and the arms were not balanced. This is not a small nuisance: **region spread within an arm is larger than the arm effect.**

| region | arm | n | GB/s values | median |
|---|---|---:|---|---:|
| **odin** | threads | 3 | 5.92, 6.05, 6.23 | 6.052 |
| **odin** | processes | 5 | 6.88, 6.90, 7.02, 7.15, 7.16 | 7.016 |
| eu-north | threads | 2 | 1.35, 6.44 | 3.896 |
| eu-north | processes | 1 | 2.81 | 2.805 |
| us-central | threads / processes | 1 / 1 | 4.59 / 5.82 | — |
| us-east | threads / processes | 1 / 1 | 4.52 / 5.99 | — |
| us-chicago-1 | threads / processes | 1 / 1 | 4.17 / 4.66 | — |
| ap-northeast | threads | 1 | 1.61 | 1.610 |
| denver | threads | 1 | 4.85 | 4.845 |
| us-ashburn-1 | processes | 1 | 4.93 | 4.933 |

Both catastrophic threads runs (rounds 4 and 8) happened to land in `ap-northeast` and `eu-north`, while `odin` — the region that produced every ≥6.8 GB/s result — supplied 5 of 10 process runs but only 3 of 10 threads runs.

**Three estimates of the same effect:**

| basis | threads | processes | delta |
|---|---:|---:|---:|
| raw median (all 10) | 4.718 | 6.431 | **+36.3%** |
| threads clean-only (excl. rounds 4, 8) | 5.385 | 6.431 | **+19.4%** |
| **region-controlled (odin only)** | 6.067 (mean, n=3) | 7.020 (mean, n=5) | **+15.7%** |

The region-controlled comparison — same region, both arms — is the cleanest contrast this experiment can offer, and it puts the effect at **~+16%**.

## 5. Mechanism check

| metric | threads | processes | delta |
|---|---:|---:|---:|
| pooled preadv **median** ms | 41.39 | 40.39 | **−1.00** |
| pooled preadv mean ms | 54.24 | 47.29 | −6.95 |
| pooled preadv **p95** ms | 76.90 | 83.63 | **+6.74** |
| pooled preadv p99 ms | 174.97 | 127.93 | −47.05 |
| pooled preadv worst ms | 3787.41 | 199.30 | −3588.11 |
| effective concurrency | 3.249 | 3.852 | +0.602 |
| mean overlap | 0.9700 | 0.9900 | +0.0200 |
| min claim gap ms | 4.0095 | 4.0039 | −0.0056 |
| median claim gap ms | 8.386 | 8.496 | +0.110 |
| **pacer lock hold median µs** | 8.121 | 10.608 | **+2.487** |
| completion spread median ms | 146.6 | 42.5 | −104.2 |
| wall p10 ms | 1288 | 1125 | −163 |
| wall median ms | 1706 | 1257 | −449 |

**Shape C is the supported answer: process isolation primarily improves stability.** Ordinary read latency is unchanged (41.39 → 40.39 ms). Process p95 is actually *worse* than threads (+6.74 ms). What changes is the extreme tail: 5 reads ≥500 ms and 2 ≥1000 ms in threads → **zero** of either in processes, and the worst single read collapses from 3787 ms to 199 ms.

**Shape D is present but is downstream of C, not independent evidence.** Processes show a higher mean effective concurrency (3.249 → 3.852) and higher overlap. But concurrency is `busy_ns / span_ns`, and a single 3.8 s stall stretches `span` and depresses the ratio — which is exactly what the two bad threads runs show (2.079 and 1.771) while every clean threads run sits near 3.6. The concurrency gap is therefore largely the tail effect re-measured, not a separate mechanism.

**Shape B is rejected:** unit read latency did not improve.

Two further ruled-out explanations:
- **Not a cheaper pacer.** The process arm's pacer lock hold is *higher* (10.6 µs vs 8.1 µs) — the shared `Value.get_lock()` costs the same or marginally more across processes, and both arms hold the lock only for the claim.
- **Not wall-clock leakage from startup.** `spawn→all-ready` (90.9 ms) is excluded from the timed region, and the wall is computed from the children's own first-enter/last-exit timestamps on a system-wide monotonic clock.

## 6. Direct answers

1. **THREADS median GB/s:** 4.718
2. **PROCESSES median GB/s:** 6.431
3. **Absolute / percentage median improvement:** +1.713 GB/s, **+36.3%** (but see #12)
4. **Mean GB/s:** threads 4.572 · processes 5.930
5. **Paired rounds favouring PROCESSES:** **7 of 10**
6. **Did ordinary median preadv latency improve?** No — 41.39 → 40.39 ms, a −1.00 ms shift indistinguishable from noise.
7. **Did mean/p95/p99 improve?** Mean −6.95 ms and p99 −47.05 ms improved; **p95 got worse (+6.74 ms)**. The mean/p99 gains are tail-driven, not central-tendency gains.
8. **Did tail frequency improve?** **Yes, decisively and this is the strongest result.** threads 8 reads ≥250 / 5 ≥500 / 2 ≥1000 → processes **0 / 0 / 0** across 1200 reads each.
9. **Did effective concurrency change despite identical QD4?** Yes, 3.249 → 3.852 — but this is a consequence of tail elimination, not an independent gain in parallelism.
10. **Did worker completion balance improve?** Yes, strongly: median completion spread 146.6 → 42.5 ms, and worst worker read 3787 → 199 ms.
11. **Was the 4 ms global floor obeyed identically?** Yes — min claim gap 4.0095 ms (threads) vs 4.0039 ms (processes), both ≥ 4.0, with a single global clock in both arms.
12. **Large enough to explain the old ~22–25% process advantage?** The raw +36% *exceeds* it, but that number is inflated by region imbalance plus two catastrophic threads runs. The two defensible estimates — **+15.7% (region-controlled)** and **+19.4% (threads clean-only)** — are the *same order of magnitude* as the historical clue but sit **at or just below** its 22–25% band. The historical direction **does transfer** to the real model-file path; its magnitude is somewhat **overstated** for this configuration.
13. **Did PROCESSES reach the 6–7 GB/s median target?** The observed median (6.431) is inside that band, but it is region-weighted (5/10 runs in `odin`). In the region where both arms can be compared, processes reach ~7.02 and threads ~6.05. So yes, processes reach 6–7 GB/s — in a good region, and largely by not falling off a cliff.
14. **Worth carrying into the real Golden loader?** **Yes, as a strong candidate — but it is a stability fix more than a raw speed fix.** The value proposition is not "reads get faster" (they don't) but "the pathological multi-second stall stops showing up in the source arm". Given that the project's recurring symptom *is* a sporadic multi-second stall, that is arguably the more valuable framing. It should not be adopted on this evidence alone: it needs a region-controlled replication, because region moved throughput more than the worker model did.
15. **Mechanism supported vs unknown.**
    - **Supported:** process ownership removes the extreme worst-case read latency and the bad-state tail (shape C). Unit read latency is unchanged (shape B rejected). Higher effective concurrency is downstream of the tail, not independent (shape D is not separable here).
    - **Unknown:** *why* isolation removes the tail. The two candidate stories — per-worker kernel/runtime client-state separation vs per-process scheduling independence under gVisor's systrap — are not separable from these measurements. Specifically, this experiment cannot say whether a 3.8 s stall was caused by something thread-local (GIL-adjacent runtime state, a scheduler artifact) or by something in the shared gVisor/gofer client path that only a separate process can escape.
    - **Also unknown and now the biggest open variable:** region. Within-arm spread (threads 1.35–6.44, processes 2.81–7.17) exceeded the arm effect (~16%). Where a run lands matters more than which arm it is in, and the harness does not pin region.

## 7. Stop condition

Exactly 10 THREADS + 10 PROCESSES were run. No 2×2 split, no QD5/QD6/QD8, no work stealing, no other pacer or block size, no multi-file. As specified.
