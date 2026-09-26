# QD4/5/6/7 Process-Architecture Sweep — 64 MiB reads, 1 process/reader, global 4.0 ms pacer

**Question:** on the winning process architecture (one reader process per source stream), does raising aggregate source QD from 4 to 5/6/7 increase median full-file source throughput?

**Answer: no. QD4 remains the optimum. Throughput is flat-to-declining at higher QD while ordinary read latency inflates monotonically — the same failure mode previously seen at QD8 in the thread architecture, now reproduced in the process architecture with the knee already at QD5.**

- QD4 is the **frozen control**, loaded from the raw files of the previous unpinned campaign (`worker_model_runs_unpinned`, `worker_model=processes`, qd=4, 15 runs). Not reconstructed from summary numbers.
- QD5/QD6/QD7 = 10 new valid non-Odin runs each from `qd_sweep_runs` (seed `20260928`).
- **30/30 new runs valid; 1 odin run invalidated and preserved.** No provider/region pinning.
- Engine unchanged: `run_worker_model_probe` was already fully QD-parameterized. Locally validated at QD4/5/6/7 (uneven partitions, distinct PIDs = QD, claim gap ≥4.0, exact coverage, maxIF ≤ QD) before any H100 run.
- Artifacts: `qd_sweep_runs/{ANALYSIS.txt, per_run_metrics.csv, schedule.json, qd*-r*.json, qd*-r*-invalid*.json}`

---

## 1. Validity — all 45 counted runs pass

Every run: qd matches the arm, **120 reads**, 8,044,982,048 bytes, exact once-only coverage, no overlap, contiguous cover, no short reads, every process completed its region, no worker/barrier errors, **max in-flight ≤ configured QD**, min global claim-to-claim gap ≥ 4.0 ms, and not odin.

Worker PIDs equal QD in every run (4/5/6/7 distinct processes, one stream each). One odin run (`qd6 r03`) was invalidated and the same slot rerun.

## 2. Headline aggregate

| metric | QD4 (frozen) | QD5 | QD6 | QD7 |
|---|---:|---:|---:|---:|
| valid runs | 15 | 10 | 10 | 10 |
| **median GB/s** | **5.785** | 5.714 | 5.252 | 5.360 |
| **mean GB/s** | **5.434** | 5.320 | 4.880 | 5.156 |
| p10 GB/s | 3.400 | 3.387 | 3.566 | 4.132 |
| p90 GB/s | 6.571 | 6.102 | 5.640 | 5.919 |
| best GB/s | 7.071 | 6.765 | 5.821 | 6.064 |
| worst GB/s | 2.023 | 2.991 | 2.561 | 4.065 |
| GB/s SD | 1.339 | 1.132 | 0.965 | **0.674** |
| median wall | **1391** | 1408 | 1532 | 1501 |
| mean wall | 1654 | 1611 | 1748 | **1589** |
| best wall | 1138 | 1189 | 1382 | 1327 |
| worst wall | 3977 | 2690 | 3142 | **1979** |
| preadv median | **41.76** | 51.62 | 71.26 | 89.66 |
| preadv mean | **48.79** | 61.15 | 80.99 | 88.57 |
| preadv p95 | **72.38** | 77.02 | 150.54 | 123.08 |
| preadv p99 | 132.31 | 286.59 | 242.87 | 149.14 |
| worst preadv | 2176.5 | 1775.5 | 942.8 | **189.2** |
| reads ≥250 | 9 | 15 | 11 | **0** |
| reads ≥500 | 2 | 7 | 3 | **0** |
| reads ≥1000 | 1 | 5 | 0 | **0** |
| runs ≥500 | 1 | 2 | 2 | **0** |
| runs ≥1000 | 1 | 2 | 0 | **0** |
| effective concurrency | 3.694 | 4.635 | 5.561 | 6.675 |
| overlap | 0.9844 | 0.9892 | 0.9850 | 0.9892 |
| max active | 4 | 5 | 6 | 7 |
| completion spread median | 76.9 | **53.2** | 103.9 | 77.9 |

## 3. Deltas vs frozen QD4

| metric | QD5 | QD6 | QD7 |
|---|---:|---:|---:|
| median GB/s | −0.070 (−1.2%) | −0.532 (−9.2%) | −0.424 (−7.3%) |
| mean GB/s | −0.114 (−2.1%) | −0.553 (−10.2%) | −0.278 (−5.1%) |
| median wall ms | +18 (+1.3%) | +141 (+10.1%) | +110 (+7.9%) |
| **preadv median ms** | **+9.86 (+23.6%)** | **+29.49 (+70.6%)** | **+47.89 (+114.7%)** |
| preadv p95 ms | +4.65 (+6.4%) | +78.17 (+108.0%) | +50.70 (+70.1%) |
| preadv p99 ms | +154.28 (+116.6%) | +110.57 (+83.6%) | +16.83 (+12.7%) |
| effective concurrency | +0.940 (+25.4%) | +1.866 (+50.5%) | +2.981 (+80.7%) |

**The core result in one line: QD4→QD7 buys +80.7% effective concurrency and pays +114.7% ordinary read latency, for −7.3% throughput.**

## 4. The knee — throughput vs ordinary read inflation

| QD | effective conc | g0 median | steady (g1+) median | steady mean | steady p95 | median GB/s | mean GB/s |
|---:|---:|---:|---:|---:|---:|---:|---:|
| **4** | 3.694 | 63.48 | **41.52** | 47.27 | 68.26 | **5.785** | **5.434** |
| 5 | 4.635 | 86.76 | 50.78 | 53.66 | 72.52 | 5.714 | 5.320 |
| 6 | 5.561 | 112.64 | 69.85 | 77.47 | 147.19 | 5.252 | 4.880 |
| 7 | 6.675 | 112.14 | 88.71 | 86.79 | 120.52 | 5.360 | 5.156 |

**The knee is at QD4/QD5.** Effective concurrency rises near-linearly with QD (3.69 → 4.64 → 5.56 → 6.68) but throughput does not. Steady-state (g1+) read latency inflates at every step, and it inflates *first* — by QD5, latency is already +22% while throughput is −1.2%.

This is the same signature as the old QD4-thread vs QD8-thread result, now reproduced in the process architecture: more real concurrency, no throughput, worse per-read service time. **The ~5.8 GB/s ceiling is a path/bandwidth limit, not a concurrency limit.**

## 5. Generation analysis

| QD | gen | n | median | mean | p95 | worst | ≥250 | ≥500 | ≥1000 |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | g0 | 60 | 63.48 | 92.99 | 198.04 | 732.07 | 3 | 1 | 0 |
| 4 | g1 | 60 | 44.16 | 58.56 | 101.93 | 468.22 | 2 | 0 | 0 |
| 4 | g2 | 60 | 43.04 | 50.90 | 84.10 | 395.33 | 1 | 0 | 0 |
| 4 | g3 | 60 | 42.88 | 44.63 | 61.53 | 73.03 | 0 | 0 | 0 |
| 4 | g4+ | 1560 | 41.33 | 46.80 | 67.20 | 2176.49 | 3 | 1 | 1 |
| 5 | g0 | 50 | 86.76 | 233.49 | 1497.22 | 1775.47 | 7 | 5 | 5 |
| 5 | g1 | 50 | 56.43 | 56.43 | 74.45 | 82.59 | 0 | 0 | 0 |
| 5 | g2 | 50 | 54.61 | 78.28 | 247.02 | 665.42 | 3 | 1 | 0 |
| 5 | g3 | 50 | 54.07 | 63.32 | 67.85 | 557.73 | 1 | 1 | 0 |
| 5 | g4+ | 1000 | 49.78 | 51.80 | 71.65 | 475.49 | 4 | 0 | 0 |
| 6 | g0 | 60 | 112.64 | 147.76 | 404.34 | 545.86 | 7 | 2 | 0 |
| 6 | g1 | 60 | 69.72 | 77.35 | 141.91 | 357.82 | 1 | 0 | 0 |
| 6 | g2 | 60 | 71.31 | 81.18 | 162.76 | 243.83 | 0 | 0 | 0 |
| 6 | g3 | 60 | 68.00 | 81.53 | 162.84 | 266.31 | 2 | 0 | 0 |
| 6 | g4+ | 960 | 69.84 | 77.00 | 140.63 | 942.79 | 1 | 1 | 0 |
| 7 | g0 | 70 | 112.14 | 117.26 | 186.04 | 189.18 | 0 | 0 | 0 |
| 7 | g1 | 70 | 81.32 | 81.45 | 118.70 | 126.97 | 0 | 0 | 0 |
| 7 | g2 | 70 | 84.93 | 85.01 | 119.60 | 129.26 | 0 | 0 | 0 |
| 7 | g3 | 70 | 85.83 | 86.18 | 121.83 | 129.71 | 0 | 0 | 0 |
| 7 | g4+ | 920 | 89.70 | 87.38 | 120.49 | 129.81 | 0 | 0 | 0 |

**g0 is not obscuring anything.** g0 is uniformly the slowest generation at every QD, and removing it does not rescue higher QD: steady-state (g1+) latency still inflates 41.52 → 50.78 → 69.85 → 88.71 ms. QD4's advantage is in the *steady state*, not just in startup.

## 6. Provider breakdown

Provider counts per arm — **materially unbalanced**, which is why the pooled view cannot be treated as causal:

```
QD4: gcp=11, oci=1,  unspecified=3            (73% GCP)
QD5: gcp=5,  oci=3,  unspecified=2            (50% GCP)
QD6: gcp=6,  oci=2,  aws=1, azure=1           (60% GCP)
QD7: gcp=5,  oci=1,  azure=2, unspecified=2   (50% GCP)
```

| provider | QD | n | median GB/s | mean | best | worst | preadv median | ≥500 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| gcp | 4 | 11 | 5.785 | 5.394 | 6.438 | 2.023 | 41.65 | 2 |
| gcp | 5 | 5 | 5.827 | 5.404 | 6.765 | 2.991 | 50.23 | 5 |
| gcp | 6 | 6 | 5.339 | 4.977 | 5.821 | 2.561 | 67.78 | 3 |
| gcp | 7 | 5 | 5.410 | 5.261 | 5.903 | 4.548 | 88.67 | 0 |
| oci | 4 | 1 | 5.601 | 5.601 | 5.601 | 5.601 | 45.61 | 0 |
| oci | 5 | 3 | 5.601 | 5.598 | 6.011 | 5.183 | 55.84 | 0 |
| oci | 6 | 2 | 5.239 | 5.239 | 5.620 | 4.859 | 65.61 | 0 |
| oci | 7 | 1 | 5.311 | 5.311 | 5.311 | 5.311 | 87.82 | 0 |
| unspecified | 4 | 3 | 6.659 | 5.523 | 7.071 | 2.840 | 38.75 | 0 |
| unspecified | 5 | 2 | 4.691 | 4.691 | 5.951 | 3.431 | 47.39 | 2 |
| unspecified | 7 | 2 | 5.871 | 5.871 | 6.064 | 5.677 | 78.74 | 0 |
| aws | 6 | 1 | 3.677 | 3.677 | 3.677 | 3.677 | 110.54 | 0 |
| azure | 6 | 1 | 4.784 | 4.784 | 4.784 | 4.784 | 80.64 | 0 |
| azure | 7 | 2 | 4.102 | 4.102 | 4.140 | 4.065 | 116.19 | 0 |

AWS appears **once** (QD6) and is **not merged into the primary comparison**. Azure appears only in QD6/QD7.

## 7. GCP-only sensitivity (main causal check)

| QD | n | median GB/s | mean | best | worst | SD | preadv med | steady med | eff conc | ≥500 | ≥1000 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **4** | 11 | 5.785 | 5.394 | 6.438 | 2.023 | 1.204 | 41.65 | 41.43 | 3.640 | 2 | 1 |
| 5 | 5 | **5.827** | 5.404 | 6.765 | 2.991 | 1.284 | 50.23 | 49.21 | 4.627 | 5 | 3 |
| 6 | 6 | 5.339 | 4.977 | 5.821 | 2.561 | 1.099 | 67.78 | 66.97 | 5.525 | 3 | 0 |
| 7 | 5 | 5.410 | 5.261 | 5.903 | 4.548 | 0.480 | 88.67 | 87.00 | 6.650 | 0 | 0 |

GCP-only deltas vs QD4: **QD5 +0.7%**, QD6 −7.7%, QD7 −6.5%.

- pooled median ordering: **[4, 5, 7, 6]**
- GCP-only median ordering: **[5, 4, 7, 6]**
- orderings agree: **False** — but the disagreement is only QD4 vs QD5, and it is a **0.7% wash**. Both views agree that QD6 and QD7 are worse than QD4.

## 8. Target checks

| QD | ≥6.0 median | ≥6.5 median | ≥7.0 median | median | preadv med | ≥500 | ≥1000 | GB/s SD |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 4 | False | False | False | 5.785 | 41.76 | 2 | 1 | 1.339 |
| 5 | False | False | False | 5.714 | 51.62 | 7 | 5 | 1.132 |
| 6 | False | False | False | 5.252 | 71.26 | 3 | 0 | 0.965 |
| 7 | False | False | False | 5.360 | 89.66 | 0 | 0 | 0.674 |

**No arm reaches 6.0 GB/s median.** The 6–7 GB/s target is not reached by any QD on this architecture in this corpus.

## 9. Worker balance

| QD | spread median ms | spread max ms | worker wall median | worst worker read | bytes/worker distinct |
|---:|---:|---:|---:|---:|---|
| 4 | 76.9 | 2776.6 | 1350.0 | 2176.5 | [2005184288, 2013265920] |
| 5 | **53.2** | 1315.1 | 1355.6 | 1775.5 | [1602531104, 1610612736] |
| 6 | 103.9 | 434.9 | 1442.3 | 942.8 | [1334095648, 1342177280] |
| 7 | 77.9 | **118.9** | 1429.5 | **189.2** | [1132769056, 1140850688, 1207959552] |

QD7 has the tightest worst case (189.2 ms worst single read, 118.9 ms max spread) and the lowest variance (SD 0.674). QD5 has the best median spread. But **stability is not throughput** — QD7 is the most *predictable* arm and still ~7% slower than QD4 in the median.

## 10. Direct answers

1. **QD4 median GB/s:** 5.785
2. **QD5 median GB/s:** 5.714
3. **QD6 median GB/s:** 5.252
4. **QD7 median GB/s:** 5.360
5. **Highest raw non-Odin median:** **QD4** (5.785 GB/s)
6. **Does the ordering survive GCP-only?** **No, not exactly** — GCP-only gives [5, 4, 7, 6] vs pooled [4, 5, 7, 6]. But QD4↔QD5 is a 0.7% wash; both views agree QD6/QD7 are worse.
7. **Highest mean throughput:** **QD4** (5.434 GB/s)
8. **Where does ordinary preadv latency begin materially inflating?** **Immediately, at QD5.** Steady-state (g1+) median goes 41.52 → 50.78 ms (+22%) for −1.2% throughput. By QD6 it is +68% (69.85 ms) and by QD7 +114% (88.71 ms).
9. **How does effective concurrency scale?** Near-linearly: 3.694 → 4.635 → 5.561 → 6.675 (+80.7% at QD7).
10. **Does additional concurrency keep producing useful throughput?** **No.** Concurrency +80.7%, throughput −7.3%. The path is bandwidth-saturated at QD4.
11. **Best worker completion balance:** **QD5** (53.2 ms median spread); QD7 has the best worst-case (118.9 ms max spread).
12. **Lowest tail rate:** **QD7** — zero reads ≥250, ≥500, ≥1000. Caveat: QD7's 5 GCP runs all landed in `us-west`, which was clean throughout; this is partly region luck.
13. **Any arm ≥6.0 GB/s median?** **No.**
14. **Any arm ≥6.5 GB/s median?** **No.**
15. **Any arm ≥7.0 GB/s median?** **No.**
16. **Clear concurrency knee?** **Yes — at QD4/QD5.** Latency inflates before throughput benefits, and the benefit never arrives.
17. **Which QD to carry forward?** **QD4.** No higher QD improves throughput, and each one degrades per-read service time.
18. **How much faster than the QD4 control?** **0% — it *is* QD4.** QD5 is −1.2% median / −2.1% mean; QD6 −9.2% / −10.2%; QD7 −7.3% / −5.1%.
19. **Is the winner's gain from faster reads, concurrency, or balance?** There is no gain to explain. Relative to the alternatives, QD4 wins on **ordinary read latency** (41.76 vs 51.62/71.26/89.66 ms median) — it is not better concurrency (it has the least) and not better balance (QD5 is better). **The mechanism is per-read service time, and adding concurrency makes it worse.**
20. **What remains uncertain due to provider distribution?**
    - Provider mix is unbalanced (QD4 73% GCP vs QD5/QD7 50%), so the pooled medians are not strictly causal. The GCP-only view is the causal check, and it still puts QD6/QD7 behind QD4.
    - **QD7's zero-tail result is confounded**: all 5 of its GCP runs were in `us-west`, a region that was clean across every arm. QD7's stability may be region luck rather than a property of QD7.
    - QD5's worse tail (7 reads ≥500, 5 ≥1000) comes from just 2 of its 10 runs (`us-west` unspecified and `us-east4`). With n=10 per arm, tail incidence is still a lottery, so no tail-rate ranking between QD5/QD6/QD7 is trustworthy.
    - AWS (1 run) and Azure (3 runs) are too thin to say anything about.

## 11. Stop condition

Exactly QD5 ×10, QD6 ×10, QD7 ×10 valid non-Odin runs. QD4 not rerun. No QD8, no block-size change, no work stealing, no sharding, no pacing change, no hedging, no Golden integration.
