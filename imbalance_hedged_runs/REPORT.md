# QD4 Static-Partition Worker Imbalance — is coarse work stealing worth pursuing?

**Answer: LOW OPPORTUNITY for the typical run.** Median finish spread is **39 ms on a 1424 ms read** (2.7%). When workers go idle, the median unstarted backlog is **0 MiB**, and **82% of runs have nothing at all to steal** — the tail is one already-in-flight `preadv` with a median of only ~9 ms left. Stranded worker capacity is a median **1.3%**.

There is a real but *rare* exception: in the ~10% of runs with spread ≥250 ms, 8 of 11 **do** carry genuine unstarted backlog, and those are exactly the pathological runs. So work stealing would help a small minority of runs and do nothing in the other ~82%.

**Cohort:** 107 valid non-Odin H100 runs with 250 ms hedging on, QD4, 4 reader processes, static contiguous regions, 64 MiB reads, global 4.0 ms pacer, no pinning.

> **Note on how this cohort was obtained.** The first hedged campaign collected 181 invocations but my runner rejected **all** of them. 74 were genuinely odin (correct). The other **107 were valid and were falsely rejected by a bug in the new engine's `observed_min_global_claim_gap_ms`** — it differenced an *unsorted* list while sorting a throwaway copy, producing large negative "gaps" (−1041 to −7076 ms). Recomputed from the raw per-attempt `gate_claim_ns`, the true minimum claim gap is **4.0000–4.1690 ms in every run** — the pacer was perfect throughout. The bug is fixed in `run_worker_model_hedge_probe`; all 107 runs were re-validated offline against the full corrected gate and promoted rather than re-spent. 74 odin files remain preserved as evidence.

---

## 1. Core source statistics vs the established QD4/process baseline

| | hedged 250 ms (n=107) | hedge off (n=16, invalid side cohort) | QD4 process baseline |
|---|---:|---:|---:|
| median GB/s | 5.651 | 5.544 | 5.785 |
| mean GB/s | 5.461 | 5.226 | 5.434 |
| best / worst GB/s | 7.059 / 1.647 | 6.513 / 3.750 | 7.071 / 2.023 |
| GB/s SD | 0.973 | 0.879 | 1.339 |
| median wall ms | 1424 | 1451 | 1391 |
| mean wall ms | 1550 | 1589 | 1654 |
| **pooled individual read** median ms | **43.26** (n=12,840) | 44.24 (n=1,920) | 41.76 |
| **pooled individual read** mean ms | 47.99 | 47.54 | 48.79 |
| pooled individual p95 / p99 | 68.39 / 102.88 | 66.23 / 68.07 | 72.38 / 132.31 |
| **pooled individual read worst ms** | **2993.82** | 68.53 | 2176.5 |
| per-run **median** read latency (n=runs) | 42.93 | 44.24 | 41.76 |
| per-run median read latency p95 / worst | 57.30 / **89.18** | — / — | — |
| reads ≥250 / ≥500 / ≥1000 | 35 / 15 / 7 | 7 / 3 / 0 | 9 / 2 / 1 |
| effective concurrency | 3.753 | 3.811 | 3.694 |
| max active | 6 | 4 | 4 |

The cohort behaves like the established baseline (median 5.651 vs 5.785; preadv median 42.93 vs 41.76; eff conc 3.753 vs 3.694). **No architecture drift.** Max active 6 reflects the extra in-flight hedge reads.

## 2. Completion spread — the core imbalance result

| metric | min | p10 | p25 | **median** | mean | p75 | p90 | p95 | max | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| finish_spread_ms | 10.4 | 19.9 | 28.4 | **39.2** | 112.7 | 64.1 | 202.5 | 519.8 | **2072.4** | 264.9 |
| slowest − second-slowest ms | 0.3 | 4.4 | 6.8 | **10.6** | 26.2 | 24.4 | 47.4 | 115.6 | 298.4 | 44.3 |
| total_stranded_worker_ms | 17.3 | 36.5 | 52.1 | **72.0** | 208.7 | 118.5 | 450.1 | 1001.2 | 2796.3 | 428.1 |
| stranded_capacity_fraction | 0.000 | 0.006 | 0.010 | **0.013** | 0.031 | 0.020 | 0.050 | 0.131 | 0.201 | 0.038 |
| first_finish_unstarted_bytes | 0 | 0 | 59.0 MB | **67.1 MB** | 303.0 MB | 193.2 MB | 442.9 MB | 1.49 GB | 5.63 GB | 765.3 MB |
| first_finish_unstarted_fraction | 0.0000 | 0.0000 | 0.0073 | **0.0083** | 0.0404 | 0.0240 | 0.0551 | 0.1892 | 0.6999 | 0.1005 |
| second_finish_unstarted_bytes | 0 | 0 | 0 | **0** | 162.2 MB | 67.1 MB | 201.3 MB | 1.11 GB | 2.94 GB | 441.1 MB |
| second_finish_unstarted_fraction | 0.0000 | 0.0000 | 0.0000 | **0.0000** | 0.0202 | 0.0083 | 0.0250 | 0.1383 | 0.3661 | 0.0548 |
| tail_unstarted_reads | 0 | 0 | 0 | **0** | 0.43 | 0 | 1 | 3 | 7 | 1.19 |
| tail_unstarted_bytes | 0 | 0 | 0 | **0** | 27.9 MB | 0 | 67.1 MB | 193.2 MB | 461.7 MB | 78.0 MB |
| remaining_inflight_ms | 0.28 | 2.87 | 5.60 | **9.41** | 12.45 | 18.36 | 27.08 | 30.45 | 36.14 | 8.84 |

**Spread thresholds:** ≥100 ms in **17/107 (16%)** · ≥250 ms in **11/107 (10%)** · ≥500 ms in **6/107 (6%)** · ≥1000 ms in **2/107 (2%)**.

## 3. Tail composition — the decisive metric

At the moment the second-slowest worker finishes, the slowest worker's remaining work classifies as:

| shape | count | share |
|---|---:|---:|
| **A — stuck on one already-in-flight preadv** (0 unstarted) | **88** | **82%** |
| B — one in-flight read + additional unstarted reads | 18 | 17% |
| C — only unstarted work | 1 | 1% |
| D — nearly complete | 0 | 0% |

Within the 11 large-spread runs (≥250 ms): **B 8, A 2, C 1**.

So the typical tail is **fundamentally unstealable**: one syscall already in flight, with a median of just **9.4 ms** remaining (p95 30.5 ms). There is no queued work for an idle process to take.

In the rare large-spread runs the picture inverts — 8 of 11 do have unstarted backlog — but those runs are only ~10% of the population.

## 4. Worker active span and finish order

Across **428 worker observations** (107 runs × 4):

```
all workers  min=1082.8  p10=1214.5  p25=1308.9  med=1388.1  mean=1492.0  p75=1527.4  p90=1788.5  p95=2222.8  max=4884.1  SD=418.7 ms
  worker0    med=1372.96   mean=1453.45
  worker1    med=1388.09   mean=1482.80
  worker2    med=1397.85   mean=1511.50
  worker3    med=1395.52   mean=1520.09
```

**No static region is systematically slower.** Per-worker medians span only 1372.96–1397.85 ms (1.8%), and worker0's *max* (3405) is the smallest while worker3's (4884) is the largest — i.e. the differences are in the tail, not the centre.

Finish order:

| worker | first | second | third | last |
|---|---:|---:|---:|---:|
| 0 | **41** | 26 | 20 | 20 |
| 1 | 17 | 27 | 37 | 26 |
| 2 | 16 | 28 | 36 | 27 |
| 3 | 33 | 26 | 14 | **34** |

Worker 0 finishes first 38% of the time and worker 3 finishes last 32%. **This is the global pacer, not region geometry**: the 4 ms launch floor staggers starts in claim order, so worker 0 is systematically ~12 ms ahead of worker 3 before any read variance. The effect is small in absolute terms (median spread 39 ms).

## 5. Tail correlation

| pair | pearson | spearman |
|---|---:|---:|
| worst_preadv vs finish_spread | **0.906** | 0.536 |
| worst_preadv vs slowest−2nd | 0.620 | 0.424 |
| worst_preadv vs tail_unstarted_bytes | 0.631 | 0.349 |
| worst_preadv vs total_stranded_worker_ms | **0.908** | 0.513 |

Imbalance is driven by **pathological individual reads**, not by accumulation of many mildly-slower reads: Pearson ~0.91 for spread and stranded capacity. But Spearman is only ~0.51 — the relationship is carried by a handful of extreme runs, not monotonic across the distribution. Do not read this as a tight causal law.

## 6. Provider breakdown

| provider | runs | median GB/s | median spread | median slow−2nd | median 1st-unstart | median tail-unstart | worst spread |
|---|---:|---:|---:|---:|---:|---:|---:|
| gcp | 48 | 5.774 | 41.6 ms | 17.3 ms | 120.3 MiB | 0.0 MiB | 644.1 ms |
| oci | 23 | 5.459 | 33.4 ms | 7.9 ms | 64.0 MiB | 0.0 MiB | 83.2 ms |
| unspecified | 33 | 5.650 | 37.5 ms | 9.8 ms | 64.0 MiB | 0.0 MiB | **2072.4 ms** |
| azure | 3 | 5.256 | 34.2 ms | 7.8 ms | 120.3 MiB | 0.0 MiB | 80.7 ms |

Provider barely moves the *median* imbalance (33–42 ms spread everywhere) but drives the *worst case*: the two extreme spreads came from `unspecified` (2072 ms) and `gcp` (644 ms). OCI and Azure never exceeded 84 ms. **The tail is a provider/instance lottery, consistent with earlier findings — not a partitioning property.**

## 7. Side comparison — hedging ON (250 ms) vs OFF

> The hedge-off cohort (16 runs) is **invalid for the main result** and is shown only as a sanity cross-check.

| cohort | n | median GB/s | mean GB/s | median wall | median spread | median preadv | reads ≥500 |
|---|---:|---:|---:|---:|---:|---:|---:|
| HEDGED 250 ms | 107 | 5.651 | 5.461 | 1424 ms | 39.2 ms | 42.93 ms | 15 |
| HEDGE OFF | 16 | 5.544 | 5.226 | 1451 ms | 51.3 ms | 44.24 ms | 3 |

**Hedging at 250 ms is essentially inert.** Across the 107 hedged runs there were only **108 hedge attempts, 36 blocks ever hedged, and 1 win**. That is 0.28% of reads (36 of 12 840) — because the median read is 43 ms, so almost nothing crosses a 250 ms threshold. The two cohorts are indistinguishable within sampling noise, and the apparent 0.1 GB/s edge is far smaller than the 0.97 GB/s SD.

This is consistent with the earlier hedged experiments: even when a hedge fires, it shares the underlying stall and saves only milliseconds.

## 8. Decision

**A. LOW OPPORTUNITY.** All three low-opportunity criteria hold for the median run:

- worker finish spread is usually small — **median 39 ms** on a 1424 ms operation;
- when workers become idle, almost no unstarted work remains — **median 0 MiB** at the second finisher, and **0 unstarted reads** on the lagging worker;
- the tail is overwhelmingly one already-in-flight stuck syscall — **82% shape A**, with only ~9 ms left on that read.

**Coarse work stealing is not worth implementing on this evidence.** It would be a no-op in ~82% of runs, and in the median run it could recover at most the ~9 ms of the final in-flight read — which stealing cannot touch anyway.

The honest caveat: in the ~10% of runs with spread ≥250 ms, 8 of 11 carry real unstarted backlog (up to 184 MiB), and those are the runs where the wall clock actually suffers. If the goal were to shave the *worst* runs rather than the median, there is a genuine but narrow target there. That is a different, much more selective intervention than coarse stealing.

## 9. Direct answers

1. **Median worker active span:** 1388.1 ms
2. **Mean worker active span:** 1492.0 ms
3. **Median finish spread:** **39.2 ms**
4. **Mean finish spread:** 112.7 ms
5. **p90 / p95 / worst spread:** 202.5 / 519.8 / **2072.4 ms**
6. **Median slowest-minus-second-slowest:** **10.6 ms**
7. **Spread ≥100 ms:** 17/107 (16%)
8. **≥250 ms:** 11/107 (10%)
9. **≥500 ms:** 6/107 (6%)
10. **≥1000 ms:** 2/107 (2%)
11. **Median unstarted when the FIRST worker finishes:** **64.0 MiB**
12. **As a fraction of the file:** **0.83%**
13. **Median unstarted when the SECOND worker finishes:** **0.0 MiB**
14. **Median unstarted reads left on the slowest worker at the second-last finish:** **0**
15. **In large-spread runs, is the slowest worker stuck on one active preadv or sitting on unstarted work?** In runs with spread ≥250 ms: **8 of 11 are shape B (in-flight + unstarted backlog)**; 2 are shape A, 1 is shape C. Across all runs the answer is the opposite: 88/107 are shape A. **The pathological runs are the ones with stealable work; the ordinary runs have none.**
16. **Stranded worker capacity:** median **72.0 ms** (1.3% of worker-time); p90 **450.1 ms** (5.0%); max 2796 ms (20.1%).
17. **Is any static region systematically slower?** **No.** Per-worker median active spans span 1372.96–1397.85 ms (1.8%). The only positional effect is finish *order* (worker 0 first 38%, worker 3 last 32%), which is the 4 ms pacer's launch stagger, not region geometry.
18. **Worst-preadv vs finish spread:** Pearson **0.906**, Spearman 0.536. Strongly tail-driven, but carried by few extreme points.
19. **Does provider affect worker imbalance?** Median spread barely (33–42 ms across all providers), but it controls the worst case: the two extreme spreads were `unspecified` 2072 ms and `gcp` 644 ms, while OCI and Azure never exceeded 84 ms.
20. **Coarse work stealing opportunity:** **LOW.**
21. **How much of the tail is theoretically stealable queued work vs fundamentally unstealable in-flight work?** By run: **19 of 107 (18%) have any stealable queued tail; 88 (82%) have none** — the tail is a single in-flight syscall with a median of 9.4 ms remaining. By volume, stealable queued tail averages **27.9 MiB (0.36% of the 7.5 GiB file)**, median 0. So **roughly four-fifths of the observed tail is fundamentally unstealable in-flight work**, and the remaining fifth is concentrated in ~10% of runs.

## 10. Stop condition

107 valid non-Odin hedged runs analysed (far exceeding the 25 requested, since all valid runs were retained). No work stealing, no dynamic queues, no hedging change, no QD change, no block-size change, no process-count change, no pacing change. The hedge-off cohort is labelled invalid and used only as a side cross-check.
