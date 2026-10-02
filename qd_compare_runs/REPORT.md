# QD4 vs QD8 at a Fixed 4.0 ms Launch Spacing — 40 Fresh H100 Runs

20 fresh QD4 + 20 fresh QD8, alternating arm order per round. All `NVIDIA H100 80GB HBM3`. 2400 pooled reads per arm.
Fixed treatment: global `preadv` start-to-start floor = **4.0 ms**. Only variable: queue depth.

Raw: `qd_compare_runs/qc-*.json`, `qd.log`, `QD_COMPARE.txt`; analysis: `tools/analyze_qd_compare.py`

---

## 1. QD8 validity audit (done before running)

`run_fullfile_probe` allocates everything from `qd`, so QD8 is **genuinely QD8** — no shared staging resource throttles it:

| resource | QD4 | QD8 | source |
|---|---|---|---|
| workers / threads | 4 | 8 | one thread per worker |
| buffers (`bytearray(read_bytes)`) | 4 | 8 | `[bytearray(read_bytes) for _ in range(qd)]` |
| memoryviews | 4 | 8 | `[memoryview(buffer) for buffer in buffers]` |
| records | 4 | 8 | `[... for _ in range(qd)]` |
| FDs (`os.open`, O_RDONLY) | 4 | 8 | `[os.open(file_path, os.O_RDONLY) for _ in range(qd)]` |
| barrier parties | 4 | 8 | `threading.Barrier(qd)` |
| blocks per worker | 30 | 15 | `divmod(total_blocks, qd)` |
| buffer memory | 256 MiB | 512 MiB | declared 16 GiB |
| peak in-flight (observed) | 4 | **8** | `max_simultaneous_in_flight` |

No harness change was required. The hardware invariant is one buffer + one FD per worker, and it scales with `qd`.

---

## 2. Headline comparison

| metric | QD4 @ 4 ms | QD8 @ 4 ms |
|---|---:|---:|
| runs | 20 | 20 |
| total reads | 2400 | 2400 |
| preadv best | 19.14 | 20.24 |
| preadv p10 | 36.60 | 44.99 |
| preadv median | **42.93** | **102.67** |
| preadv mean | **49.81** | **100.07** |
| preadv p95 | 70.63 | 152.48 |
| preadv p99 | 144.70 | 216.86 |
| preadv worst | **828.13** | **1154.90** |
| preadv SD | 44.29 | 53.94 |
| reads ≥500 | 9 | 7 |
| reads ≥1000 | **0** | **2** |
| runs ≥500 | 5 | 4 |
| runs ≥1000 | **0** | **1** |
| median GB/s | **4.782** | **3.953** |
| mean GB/s | **4.818** | **4.018** |
| best GB/s | 6.529 | 5.543 |
| worst GB/s | 3.432 | 2.860 |
| GB/s SD | 0.859 | 0.660 |
| avg total time | **1722.9 ms** | **2057.1 ms** |
| median total time | 1682.2 ms | 2035.1 ms |
| best total time | 1232.2 ms | 1451.5 ms |
| worst total time | 2344.4 ms | 2813.3 ms |
| total-time SD | 303.1 ms | 339.7 ms |
| overlap | 0.980 | 0.975 |
| effective concurrency | **3.49** | **5.89** |

**QD8 vs QD4 delta:**
- median GB/s: **−0.829 (−17.3%)**
- mean GB/s: **−0.801 (−16.6%)**
- avg total time: **+334 ms (+19.4%)**

---

## 3. Pooled preadv detail

| arm | reads | best | p10 | median | mean | p95 | p99 | worst | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QD4 | 2400 | 19.14 | 36.60 | 42.93 | 49.81 | 70.63 | 144.70 | 828.13 | 44.29 |
| QD8 | 2400 | 20.24 | 44.99 | 102.67 | 100.07 | 152.48 | 216.86 | 1154.90 | 53.94 |

Tail counts (pathological reads retained in mean/SD):

| arm | ≥250 | ≥500 | ≥1000 | ≥2000 | ≥5000 |
|---|---:|---:|---:|---:|---:|
| QD4 | 14 (0.583%) | 9 (0.375%) | 0 | 0 | 0 |
| QD8 | 18 (0.750%) | 7 (0.292%) | 2 (0.083%) | 0 | 0 |

**QD8's pooled median read is 2.39× QD4's (102.67 vs 42.93 ms).** This is the mechanism behind the throughput result (§5).

---

## 4. Per-run distribution

| arm | wall best | p10 | median | mean | p95 | p99 | worst | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| QD4 | 1232.2 | 1362.2 | 1682.2 | 1722.9 | 2126.2 | 2300.8 | 2344.4 | 303.1 |
| QD8 | 1451.5 | 1688.7 | 2035.1 | 2057.1 | 2523.6 | 2755.3 | 2813.3 | 339.7 |

| arm | GB/s best | p10 | median | mean | p95 | p99 | worst | SD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| QD4 | 6.529 | 3.850 | 4.782 | 4.818 | 6.380 | 6.500 | 3.432 | 0.859 |
| QD8 | 5.543 | 3.220 | 3.953 | 4.018 | 4.880 | 5.410 | 2.860 | 0.660 |

**QD4 beats QD8 at every point of the distribution except the tail SD** — best, p10, median, mean, p95, p99, worst. This is not a tail-effect; QD8 is slower run-to-run across the board.

---

## 5. Why QD8 is slower: per-read latency inflation

| arm | g0 median | g1 median | g2 median | g3 median | g4 median |
|---|---:|---:|---:|---:|---:|
| QD4 | 105.14 | 44.90 | 49.55 | 45.81 | 43.51 |
| QD8 | 121.21 | 74.15 | 94.28 | 104.94 | 107.97 |

| arm | g0 mean | g0 p95 | g0 worst | g0 ≥500 | g0 ≥1000 |
|---|---:|---:|---:|---:|---:|
| QD4 | 180.58 | 606.93 | 828 | 9 | 0 |
| QD8 | 166.98 | 470.73 | 1155 | 7 | 2 |

**Steady-state generations tell the story**: QD4's g1–g4 medians sit at 44–50 ms; QD8's sit at 74–108 ms. With 6 concurrent 64 MiB reads instead of 3.5, each individual read takes roughly **2× longer**, so 15 blocks/worker × ~100 ms ≈ 1500 ms ≈ the same wall as 30 blocks/worker × ~45 ms at QD4. The extra concurrency is entirely absorbed by per-read latency inflation; net throughput falls because the deeper queue adds overhead without adding delivered bandwidth.

**Interpretation:** the host read path behind the model inode is already **bandwidth-saturated at ~4.8 GB/s** at QD4. QD8 does not find more bandwidth; it queues deeper and pays latency for it.

---

## 6. Pacer validity

| arm | observed min gap | p10 | median | p95 |
|---|---|---|---|---|
| QD4 | 4.000 (range 4.000–4.151) | ~4.23 | 8.03 | ~32.8 |
| QD8 | 4.001 (range 4.001–4.111) | ~4.26 | 6.29 | ~48.4 |

**The 4 ms floor holds exactly in both arms**, including QD8 with twice the workers. The comparison is valid.

---

## 7. Concurrency

| arm | overlap mean | overlap median | eff conc mean | eff conc median | max active |
|---|---|---|---|---|---|
| QD4 | 0.980 | 0.983 | 3.49 | 3.61 | 4 |
| QD8 | 0.975 | 0.975 | **5.89** | **6.04** | **8** |

**The pacer did not collapse QD8.** Effective concurrency rose from 3.49 to 5.89 (+69%) and max in-flight reached 8. So QD8's failure to gain throughput is *not* a pacer artifact — it is a property of the underlying read path.

---

## 8. Tail behavior

| arm | runs with ≥500 | runs with ≥1000 | reads ≥500 | reads ≥1000 | worst read (run) |
|---|---:|---:|---:|---:|---|
| QD4 | 5/20 | 0/20 | 9 | 0 | 828 ms (qc-q4-r04, us-east) |
| QD8 | 4/20 | 1/20 | 7 | 2 | 1155 ms (qc-q8-r08, us-west) |

**Both arms show the same front-pair signature.** Every ≥500 ms run is a first-read/second-read pair:

```
QD4 qc-q4-r04 worst=828  :: #0w3 t=0.0 lat=779  | #1w1 t=4.8 gap=4.80 lat=828
QD4 qc-q4-r08 worst=797  :: #0w3 t=0.0 lat=751  | #1w0 t=4.1 gap=4.07 lat=797
QD8 qc-q8-r08 worst=1155 :: #0w7 t=0.0 lat=1155 | #1w5 t=4.3 gap=4.31 lat=1151
QD8 qc-q8-r07 worst=608  :: #0w7 t=0.0 lat=521  | #1w3 t=4.8 gap=4.84 lat=608
```

The second launch's observed gap is **4.07–5.08 ms in every sick run** — i.e. the pacer was obeyed, and the pair still went slow together. This is the same phenomenon seen at 3.5 ms in the boundary experiment.

---

## 9. ⚠ Important: the 4 ms protection did NOT fully reproduce in this cohort

The prior 4 ms cohort (`cf-c4`, 15 runs) was **completely clean**: 0 reads ≥500, worst 319 ms. **This contemporaneous QD4 @ 4 ms cohort is not**: 5/20 runs with ≥500 ms reads, 9 reads ≥500, worst 828 ms.

**Pooled 4 ms @ QD4 across both cohorts:**

| cohort | runs | reads | reads ≥500 | reads ≥1000 | worst |
|---|---:|---:|---:|---:|---:|
| `cf-c4` (prior) | 15 | 1800 | 0 | 0 | 319 ms |
| `qc-q4` (this, fresh control) | 20 | 2400 | 9 | 0 | 828 ms |
| **combined** | **35** | **4200** | **9 (0.21%)** | **0** | **828 ms** |

This is exactly what the boundary experiment predicted: the transition is **probabilistic, not a hard threshold**. I am not going to smooth this over — **4 ms is a strong risk-reducer, not a guarantee**, and its apparent total cleanliness in the earlier cohort was partly cohort luck.

What *does* hold across 35 runs at 4 ms: **zero ≥1000 ms reads.** Severity is bounded at sub-second (worst 828 ms) rather than the 11.8 s seen at 2.5 ms.

---

## 10. Direct answers

1. **Does QD8 materially increase median GB/s over QD4?** **No — it decreases it by 17.3%** (4.782 → 3.953).
2. **Mean GB/s?** **No — decreases 16.6%** (4.818 → 4.018).
3. **Average full-file time?** QD4 **1722.9 ms (1.723 s)**; QD8 **2057.1 ms (2.057 s)** — QD8 is 19.4% slower.
4. **Pooled median / mean preadv?** QD4 **42.93 / 49.81 ms**; QD8 **102.67 / 100.07 ms**.
5. **p10 / p95 / p99 / best / worst / SD?** QD4: 36.60 / 70.63 / 144.70 / 19.14 / 828.13 / 44.29. QD8: 44.99 / 152.48 / 216.86 / 20.24 / 1154.90 / 53.94.
6. **Reads ≥500?** QD4 **9**, QD8 **7**.
7. **Reads ≥1000?** QD4 **0**, QD8 **2**.
8. **Runs containing those tails?** ≥500: QD4 5/20, QD8 4/20. ≥1000: QD4 0/20, QD8 1/20.
9. **Does QD8 bring back catastrophic multi-second sickness?** **No.** Worst QD8 read is 1155 ms — no multi-second or 10 s+ events. But QD8 **did** produce the only two ≥1000 ms reads in the experiment, so it did not retain QD4's zero-≥1000 property.
10. **Is generation 0 still protected at QD8?** **Only partially.** QD8 g0: 7 reads ≥500, **2 ≥1000**, worst 1155 ms. QD4 g0: 9 reads ≥500, **0 ≥1000**, worst 828 ms. Gen-0 remains the locus of every tail in both arms, and QD4's gen-0 tails are shallower.
11. **Does QD8 achieve higher effective concurrency?** **Yes, strongly**: 5.89 vs 3.49 mean (median 6.04 vs 3.61), max in-flight 8 vs 4.
12. **Does the extra concurrency justify itself?** **No.** It buys **+69% concurrency** and delivers **−17% throughput** with a **≥1000 ms tail that QD4 did not have**.
13. **Better throughput/tail tradeoff?** **QD4 @ 4 ms, decisively** — faster at every distribution point, shallower tail, same pacer compliance.
14. **Which QD for the hedging experiment?** **QD4 @ 4 ms.**

---

## 11. Causal boundary — what this does and does not show

- **It is not a pacer failure.** The 4 ms floor held exactly at QD8 (observed min 4.001 ms), and QD8 achieved 5.89 effective concurrency. The pacer did its job.
- **It is not launch burstiness.** Sick QD8 runs had second-launch gaps of 4.31–4.84 ms, i.e. fully paced.
- **It is the number of simultaneously outstanding operations.** QD8 roughly doubles concurrent in-flight reads (3.49 → 5.89), and per-read latency inflates ~2.4× (median 42.93 → 102.67 ms). Delivered bandwidth *falls*.
- **Gen-0 remains the vulnerable window** in both arms, consistent with every earlier experiment.

**Conclusion:** the model-file read path is **bandwidth-saturated by QD4**. Increasing queue depth adds concurrency, latency and tail risk without adding throughput.

---

## 12. Recommendation

**Carry QD4 @ 4 ms into the hedging experiment.** QD8 is strictly worse here on throughput, total time and tail depth, while buying concurrency the workload cannot convert into bandwidth.

**Two caveats to carry forward:**
1. **4 ms is a risk-reducer, not a guarantee.** 9 reads ≥500 ms occurred at 4 ms across 35 runs, all as first-pair events obeying the pacer. Hedging should be evaluated against that residual, not against an assumed-clean baseline.
2. **Zero reads ≥1000 ms across all 35 runs at 4 ms @ QD4** is the property worth protecting — it is what QD8 broke.

Stopping here. Hedging, spacing tuning, QD6/QD12, and block-size changes were not run.
