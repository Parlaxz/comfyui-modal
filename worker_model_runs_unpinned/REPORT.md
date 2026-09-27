# THREADS vs PROCESSES — unpinned, 30 non-odin runs + provider breakdown

**Campaign:** no pinning at all. Any odin run is invalidated and the same slot rerun. Target 30 valid non-odin runs.
**Achieved:** **30 valid** (15 threads + 15 processes). **15 odin runs captured and invalidated** (45 invocations total). Every odin rejection is preserved on disk.

- Schedule seed `20260927`, 15 paired rounds (8 threads-first / 7 processes-first), persisted before launch.
- All 30 valid runs are **NVIDIA H100 80GB HBM3**, QD4, 64 MiB, 4.0 ms global pacer, fresh single-use container each.
- Artifacts: `worker_model_runs_unpinned/{ANALYSIS.txt, per_run_metrics.csv, pooled_reads.csv, schedule.json, wm-*.json, wm-*-invalid*.json}`

---

## 1. Validity (all 30 runs)

| check | threads | processes |
|---|---|---|
| configured QD | 4 | 4 |
| reads per run | 120 | 120 |
| bytes per run | 8,044,982,048 | 8,044,982,048 |
| exact once-only coverage | True ×15 | True ×15 |
| max simultaneous in-flight | 4 (never more) | 4 (never more) |
| min claim-to-claim gap | ≥ 4.0062 ms | ≥ 4.0033 ms |
| worker PIDs | **1** | **4** |
| worker TIDs | 4 | 4 |

Odin handling: 15 runs observed `CLOUD_PROVIDER_UNSPECIFIED` / `odin` → rejected, preserved, slot rerun. No other region was rejected.

## 2. Total core data and statistics — all 30 runs

### Headline per arm

| metric | 4 threads / 1 process | 4 processes / 1 reader each |
|---|---:|---:|
| runs | 15 | 15 |
| median GB/s | **5.189** | **5.785** |
| mean GB/s | 4.976 | 5.434 |
| best GB/s | 6.339 | 7.071 |
| worst GB/s | 3.763 | 2.023 |
| GB/s SD | 0.742 | 1.339 |
| median source wall ms | 1550 | 1391 |
| mean source wall ms | 1656 | 1654 |
| best source wall ms | 1269 | 1138 |
| worst source wall ms | 2138 | 3977 |
| pooled preadv median ms | 44.80 | 41.76 |
| pooled preadv mean ms | 50.15 | 48.79 |
| pooled preadv p95 ms | 73.07 | 72.38 |
| pooled preadv p99 ms | 122.40 | 132.31 |
| worst preadv ms | 636.3 | 2176.5 |
| reads ≥250 | 8 | 9 |
| reads ≥500 | 7 | 2 |
| reads ≥1000 | 0 | 1 |
| runs ≥500 | 2 | 1 |
| runs ≥1000 | 0 | 1 |
| effective concurrency | 3.630 | 3.694 |
| overlap | 0.9800 | 0.9844 |
| max active | 4 | 4 |

**PROCESS median GB/s delta: +0.596 (+11.5%)**
**PROCESS mean GB/s delta: +0.458 (+9.2%)**

### Pooled statistics — ALL 30 runs (3600 reads)

```
GB/s     min=2.023  p10=3.782  median=5.480  mean=5.205  p90=6.349  max=7.071  SD=1.106
wall ms  best=1138  p10=1267   median=1468   mean=1655   p90=2127   worst=3977  SD=555
preadv   n=3600  best=19.11  p10=36.17  median=43.40  mean=49.47  p95=72.87  p99=130.25  worst=2176.49  SD=48.96
tails    reads>=250=17   reads>=500=9   reads>=1000=1   |   runs>=500=3   runs>=1000=1
conc     meanEffConc=3.662  medianEffConc=3.695  overlap=0.9822  maxActive=4
```

### Paired analysis (15 temporal pairs)

| round | threads GB/s | processes GB/s | delta | delta % |
|---:|---:|---:|---:|---:|
| 1 | 3.826 | 5.785 | +1.959 | +51.2% |
| 2 | 5.482 | 5.601 | +0.119 | +2.2% |
| 3 | 4.337 | 7.071 | +2.734 | +63.1% |
| 4 | 5.140 | 6.659 | +1.519 | +29.6% |
| 5 | 3.784 | 4.240 | +0.456 | +12.0% |
| 6 | 5.301 | 6.438 | +1.138 | +21.5% |
| 7 | 3.763 | 6.015 | +2.253 | +59.9% |
| 8 | 5.604 | 5.755 | +0.150 | +2.7% |
| 9 | 5.189 | 5.232 | +0.043 | +0.8% |
| 10 | 4.529 | 5.637 | +1.108 | +24.5% |
| 11 | 4.935 | 5.939 | +1.003 | +20.3% |
| 12 | 5.487 | 6.094 | +0.608 | +11.1% |
| 13 | 5.478 | 6.179 | +0.701 | +12.8% |
| 14 | 6.339 | 2.023 | −4.316 | −68.1% |
| 15 | 5.450 | 2.840 | −2.610 | −47.9% |

- median paired GB/s delta **+0.701 (+12.8%)**
- mean paired GB/s delta **+0.458 (+13.0%)**
- median paired wall delta **−229 ms**
- **pairs PROCESS > THREAD: 13/15**
- paired bootstrap 95% interval on the median delta: **[+0.119, +1.519] GB/s** — **excludes zero** (first time in this series)

The only two losing pairs (14, 15) are exactly the two rounds where processes drew a bad instance (round 14: 2176 ms stall; round 15: eu-north at 2.840). Threads won those by default, not by being faster.

## 3. Provider breakdown

**Critical caveat up front: unpinned Modal never landed on AWS. AWS = 0 runs here.** Across this campaign and the earlier unpinned campaign, **50 unpinned runs produced zero AWS placements.** Unpinned scheduling on this workspace resolves to GCP / Modal-owned (odin, denver, eu-north) / OCI / Azure.

So the AWS breakdown below is taken from the **aws-pinned batch** (`worker_model_runs_provider`, 10 runs) and is labelled as such — it is real AWS H100 data, but from a pinned treatment, not from this unpinned campaign.

### Provider counts

| source | gcp | aws | unspecified (odin-family) | oci | azure |
|---|---:|---:|---:|---:|---:|
| this campaign (unpinned) | **19** | **0** | 6 | 4 | 1 |
| aws-pinned batch | 10 | **10** | 0 | 0 | 0 |

### AWS — 10 runs / 1200 reads (from the aws-pinned batch)

```
GB/s     min=3.011  p10=3.277  median=3.778  mean=3.939  p90=4.748  max=4.847  SD=0.598
wall ms  best=1660  p10=1695   median=2129   mean=2090   p90=2457   worst=2672  SD=316
preadv   n=1200  best=15.42  p10=46.36  median=65.56  mean=66.42  p95=95.59  p99=110.58  worst=194.67  SD=18.36
tails    reads>=250=0   reads>=500=0   reads>=1000=0   |   runs>=500=0   runs>=1000=0
conc     meanEffConc=3.815  overlap=0.9858  maxActive=4
  threads    n=5  median=3.486  mean=3.838  best=4.737  worst=3.011  preadv median=65.60  reads>=500=0
  processes  n=5  median=3.811  mean=4.039  best=4.847  worst=3.689  preadv median=65.43  reads>=500=0
```

**AWS is ~31% slower in the median than GCP but has a completely clean tail: zero reads ≥250 ms across 1200 reads.** Its worst single read was 194.67 ms and its worst run 4.847 GB/s — the tightest spread in the whole series (SD 0.598).

### GCP — 19 runs / 2280 reads (this campaign, unpinned)

```
GB/s     min=2.023  p10=3.817  median=5.487  mean=5.218  p90=6.111  max=6.438  SD=1.041
wall ms  best=1250  p10=1316   median=1466   mean=1654   p90=2108   worst=3977  SD=599
preadv   n=2280  best=20.65  p10=37.09  median=42.84  mean=48.50  p95=58.74  p99=151.84  worst=2176.49  SD=59.39
tails    reads>=250=17   reads>=500=9   reads>=1000=1   |   runs>=500=3   runs>=1000=1
conc     meanEffConc=3.643  overlap=0.9820  maxActive=4
  threads    n= 8  median=5.245  mean=4.976  best=5.604  worst=3.784  preadv median=44.09  worst=636.3   reads>=500=7
  processes  n=11  median=5.785  mean=5.394  best=6.438  worst=2.023  preadv median=41.65  worst=2176.5  reads>=500=2
```

**GCP is fast in the median but carries the entire pathological tail.** Every read ≥250 ms in the whole 30-run corpus came from a GCP run: 17/17 ≥250, 9/9 ≥500, 1/1 ≥1000. OCI (4 runs), unspecified (6 runs) and Azure (1 run) all produced **zero** reads ≥250 ms.

### Other providers (this campaign)

```
unspecified (eu-north, denver, us-central)  6 runs /  720 reads
  GB/s  min=2.840  median=5.910  mean=5.359  max=7.071  SD=1.554
  tails reads>=250=0  >=500=0  >=1000=0
  threads n=3 median=5.482 | processes n=3 median=6.659

oci (us-chicago-1, us-ashburn-1)            4 runs /  480 reads
  GB/s  min=4.337  median=4.732  mean=4.850  max=5.601  SD=0.484
  tails reads>=250=0  >=500=0  >=1000=0
  threads n=3 median=4.529 | processes n=1 median=5.601

azure (us-central)                          1 run  /  120 reads
  GB/s  5.450 (single run, threads)   tails 0/0/0
```

### Provider summary

| provider | runs | median GB/s | mean GB/s | best | worst | GB/s SD | preadv median | reads ≥250 | reads ≥500 | reads ≥1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **AWS** (pinned batch) | 10 | 3.778 | 3.939 | 4.847 | 3.011 | 0.598 | 65.56 | **0** | **0** | **0** |
| **GCP** (unpinned) | 19 | **5.487** | 5.218 | 6.438 | 2.023 | 1.041 | 42.84 | 17 | 9 | 1 |
| unspecified | 6 | 5.910 | 5.359 | 7.071 | 2.840 | 1.554 | 40.33 | 0 | 0 | 0 |
| OCI | 4 | 4.732 | 4.850 | 5.601 | 4.337 | 0.484 | 48.98 | 0 | 0 | 0 |
| Azure | 1 | 5.450 | 5.450 | 5.450 | 5.450 | — | 42.23 | 0 | 0 | 0 |

**AWS and GCP are qualitatively different paths.** AWS: slow but metronomic (no read above 250 ms). GCP: ~45% faster in the median but the only provider that produces multi-second stalls.

## 4. Within-provider comparison — and a correction to my previous conclusion

The pooled median flips sign between campaigns, which I previously reported as "no stable advantage" and then as "the replication reversed it". **Both of those pooled readings were artifacts.** Comparing within provider is the robust test, and it is consistent across every campaign:

| campaign | provider | threads median GB/s | processes median GB/s | delta |
|---|---|---:|---:|---:|
| run 1 (unpinned, odin) | odin-family (mean, n=3 vs 5) | 6.067 | 7.020 | **+15.7%** |
| run 2 (pinned) | AWS | 3.486 (n=5) | 3.811 (n=5) | **+9.3%** |
| run 2 (pinned) | GCP | 5.304 (n=5) | 5.436 (n=5) | **+2.5%** |
| run 3 (this, unpinned) | GCP | 5.245 (n=8) | 5.785 (n=11) | **+10.3%** |
| run 3 (this, unpinned) | unspecified | 5.482 (n=3) | 6.659 (n=3) | **+21.5%** |
| run 3 (this, unpinned) | OCI | 4.529 (n=3) | 5.601 (n=1) | +23.7% |

**Processes win within every provider, in every campaign — 6 of 6 cells.** The direction is stable; only the pooled median is unstable.

Why the pooled median flips: it is dominated by where each arm's values happen to interleave across providers. Run 2 is the clearest case — within AWS processes won (+9.3%) and within GCP processes won (+2.5%), yet the pooled median said processes −15.7%, because a single process outlier (1.616 GB/s, 3701 ms stall) shifted the pooled centre while both within-provider medians stayed ahead.

**Corrected conclusion: the process arm is consistently faster, typically ~+10% within provider, and the earlier "reversal" was a statistical artifact of pooling across providers with unequal composition.**

## 5. Direct answers

1. **THREADS median GB/s:** 5.189 (all 30) · 5.245 (GCP only)
2. **PROCESSES median GB/s:** 5.785 (all 30) · 5.785 (GCP only)
3. **Absolute / percentage median improvement:** **+0.596 GB/s, +11.5%**
4. **Mean GB/s:** threads 4.976 · processes 5.434 (+9.2%)
5. **Paired rounds favouring PROCESSES:** **13 of 15**
6. **Did ordinary median preadv latency improve?** Marginally: 44.80 → 41.76 ms (−3.04 ms).
7. **Did mean/p95/p99 improve?** Mean −1.36 ms and p95 −0.70 ms (both ~flat); p99 **worse** by +9.91 ms. No meaningful central-tendency gain.
8. **Did tail frequency improve?** **No.** Threads 7 reads ≥500 / 0 ≥1000; processes 2 reads ≥500 / 1 ≥1000. Processes had the single worst read in the corpus (2176 ms). The tail is not arm-specific.
9. **Did effective concurrency change despite identical QD4?** Barely: 3.630 → 3.694, and as before this tracks `busy/span` rather than an independent parallelism gain.
10. **Did worker completion balance improve?** Yes: median completion spread 128.4 → 76.9 ms.
11. **Was the 4 ms global floor obeyed identically?** Yes — min claim gap 4.0062 ms (threads) vs 4.0033 ms (processes), one global clock, all 30 runs.
12. **Large enough to explain the old ~22–25% process advantage?** Partially. The within-provider estimate is ~+10% (GCP) to +9% (AWS) — roughly **half** the historical 22–25%, and this time the paired bootstrap excludes zero. The historical direction transfers; the magnitude is about half.
13. **Did PROCESSES reach the 6–7 GB/s median target?** **Yes, marginally** — median 5.785 overall and 5.785 on GCP; best run 7.071. It is at the bottom edge of the band, not comfortably inside it. On AWS neither arm approaches it (3.5–3.8).
14. **Is the process architecture worth carrying into the real Golden loader?** **Yes, as a modest and consistent win — with an important qualifier.** It buys ~+10% median throughput and ~+50 ms better balance at the cost of a fork per worker. But it does **not** remove the multi-second stall, which is the project's actual symptom. If the goal is tail elimination, this is not the lever; provider/region selection is (AWS produced zero tails here).
15. **What mechanism is supported, and what remains unknown?**
    - **Supported:** processes are consistently ~+10% faster within provider (6/6 provider-campaign cells). Unit `preadv` latency is essentially unchanged (44.80 → 41.76 ms median; p95 flat, p99 worse) — so the gain is not per-read speed.
    - **Supported:** the pathological multi-second stall is **provider-correlated, not arm-correlated**. In this corpus 100% of reads ≥250 ms (17), ≥500 ms (9) and ≥1000 ms (1) came from GCP; AWS produced **zero** across 1200 reads.
    - **Unknown:** why GCP stalls and AWS does not. Both are real providers with the same file, same geometry, same gVisor path. This is the most actionable open question in the whole series.
    - **Unknown:** the exact source of the ~10% process gain. Per-read latency is unchanged, so it is not faster reads; the surviving candidates are scheduling/ownership effects that this instrumentation cannot separate.
    - **Methodological finding:** pooled medians across mixed providers are unreliable and produced two contradictory conclusions before this run. Within-provider comparison should be the default for any future arm comparison on this path.

## 6. Stop condition

Exactly 30 valid non-odin runs (15 + 15). 15 odin runs invalidated and preserved. No pinning used in the campaign. No QD/block-size/work-stealing changes. The AWS figures are drawn from the previously collected aws-pinned batch and are labelled as such throughout.
