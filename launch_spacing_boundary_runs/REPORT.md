# Launch-Spacing Boundary — 2.5 / 3.0 / 3.5 ms (new) vs 4.0 ms (prior cohort)

45 new fresh H100 runs (15 per arm, balanced rotation `2.5,3.0,3.5` → `3.0,3.5,2.5` → `3.5,2.5,3.0` …) plus the existing 15-run 4.0 ms cohort. All 60 runs are `NVIDIA H100 80GB HBM3`, 1800 reads per arm.

**All four arms were recomputed from raw per-read records with identical code** (`tools/analyze_launch_spacing_four_arm.py`), so the 4.0 ms arm is not taken from an old summary table.

Raw: `launch_spacing_boundary_runs/bd-*.json`, `boundary.log`, `FOUR_ARM.txt`; prior: `launch_spacing_confirm_runs/cf-c4-*.json`

---

## 1. Main output table

| gap | runs | reads | pooled median | pooled mean | p95 | p99 | worst | runs ≥500 | reads ≥500 | reads ≥1000 | median GB/s | overlap | eff conc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **2.5** | 15 | 1800 | 43.40 | **82.92** | 100.61 | 788.38 | **11818** | 4 | **21** | **11** | 4.538 | 0.961 | 3.40 |
| **3.0** | 15 | 1800 | 42.98 | **48.07** | 77.11 | 111.36 | 656 | 1 | **2** | **0** | 5.292 | 0.979 | 3.64 |
| **3.5** | 15 | 1800 | 42.76 | **55.00** | 70.42 | 129.31 | **4082** | 3 | **10** | **6** | 5.169 | 0.984 | 3.53 |
| **4.0** prior | 15 | 1800 | 43.03 | **50.54** | 90.02 | 135.74 | **319** | 0 | **0** | **0** | 5.404 | 0.982 | 3.65 |

## 2. Generation-0 only

| spacing | gen0 n | gen0 median | gen0 mean | ≥250 | ≥500 | ≥1000 | worst |
|---|---|---|---|---|---|---|---|
| 2.5 | 60 | 105.41 | **870.29** | 10 | 10 | 8 | 11818 |
| 3.0 | 60 | 98.37 | **113.23** | 2 | 2 | 0 | 656 |
| 3.5 | 60 | 103.96 | **285.73** | 7 | 7 | 3 | 4082 |
| 4.0 | 60 | 92.80 | **94.33** | 0 | 0 | 0 | 204 |

**All generations:**

```
gap 2.5 | g0: n=60 med=105.4 mean=870.3 max=11818 ge500=10 ge1k=8 | g1: max=2791 ge500=1 ge1k=1 | g2: max=928 ge500=2 | g3: max=131
gap 3.0 | g0: n=60 med= 98.4 mean=113.2 max= 656 ge500=2  ge1k=0 | g1: max=106 | g2: max=87 | g3: max=89
gap 3.5 | g0: n=60 med=104.0 mean=285.7 max= 4082 ge500=7  ge1k=3 | g1: max=1205 ge500=2 ge1k=2 | g2: max=1214 ge500=1 ge1k=1 | g3: max=151
gap 4.0 | g0: n=60 med= 92.8 mean= 94.3 max= 204 ge500=0  ge1k=0 | g1: max=90 | g2: max=99 | g3: max=86
```

The phenomenon remains **front-loaded**: every arm's gen-0 median (~93–105 ms) is roughly double its later-generation medians (~43–55 ms), *including the clean 4.0 ms arm*. Pacing does not remove that front-loading — it removes the catastrophic tail on top of it.

---

## 3. Per-run distribution (pooled means can be distorted by one sick run)

| gap | median of per-run medians | mean of per-run medians | median of per-run means | mean of per-run means | max run mean |
|---|---|---|---|---|---|
| 2.5 | 41.43 | 46.78 | 54.23 | 82.92 | **358.09** |
| 3.0 | 42.20 | 45.27 | 46.63 | 48.07 | 68.29 |
| 3.5 | 43.08 | 44.03 | 47.96 | 55.00 | 145.60 |
| 4.0 | 42.89 | 47.74 | 45.13 | 50.54 | 82.89 |

---

## 4. Median vs mean — pacing deletes tails, it does not speed ordinary reads

| gap | pooled median | pooled mean | mean − median | p95 | p99 |
|---|---|---|---|---|---|
| 2.5 | 43.40 | 82.92 | **39.53** | 100.61 | 788.38 |
| 3.0 | 42.98 | 48.07 | **5.09** | 77.11 | 111.36 |
| 3.5 | 42.76 | 55.00 | **12.25** | 70.42 | 129.31 |
| 4.0 | 43.03 | 50.54 | **7.51** | 90.02 | 135.74 |

**This is the cleanest result in the whole investigation.** The pooled **median is essentially identical across all four arms — 42.76 to 43.40 ms, a spread of 0.64 ms (1.5%)**. The pooled **mean swings from 48.07 to 82.92 ms**, and the swing is entirely the mean−median gap, i.e. tail contamination.

**Pacing does not make ordinary/median reads faster.** It **deletes the multi-second tail**, and the mean collapses accordingly. The 2.5 ms arm's mean of 82.92 ms is not "slower reads" — its median is 43.40 ms, identical to everything else.

---

## 5. Pacer validity — observed floors are exact

| gap | obs min (range) | obs p5 (range) | obs median (range) | obs p95 (range) |
|---|---|---|---|---|
| 2.5 | **2.51–2.61** | 2.73–3.25 | 4.92–34.54 | 26.03–262.89 |
| 3.0 | **3.00–3.20** | 3.10–3.30 | 5.18–14.35 | 26.49–42.88 |
| 3.5 | **3.50–3.59** | 3.61–4.10 | 5.55–12.52 | 27.95–46.03 |
| 4.0 | **4.00–4.14** | 4.10–4.37 | 5.38–14.39 | 21.49–56.16 |

Every arm's enforced floor matches its request exactly, so arms are classified on **observed** spacing, not configured values. (The 2.5 ms arm's wide median/p95 ranges reflect its sick runs: once a worker blocks for seconds, subsequent launch gaps stretch as a consequence.)

---

## 6. Concurrency / throughput

| gap | median GB/s | mean GB/s | min GB/s | median wall | overlap mean | eff conc mean | max active |
|---|---|---|---|---|---|---|---|
| 2.5 | 4.538 | 4.191 | 0.385 | 1773 | 0.961 | 3.40 | 4 |
| 3.0 | 5.292 | 5.154 | 3.652 | 1520 | 0.979 | 3.64 | 4 |
| 3.5 | 5.169 | 4.791 | 1.239 | 1556 | 0.984 | 3.53 | 4 |
| 4.0 | 5.404 | 5.169 | 2.980 | 1489 | 0.982 | 3.65 | 4 |

**QD4 overlap survives at every spacing** — `max_active = 4` in all 60 runs, overlap fraction 0.961–0.984, effective concurrency 3.40–3.65.

---

## 7. Fisher exact (two-sided)

```
read-level >=500 ms (1800 reads per arm)
   2.5 vs 3.0:  21 vs  2  p=0.0001
   2.5 vs 3.5:  21 vs 10  p=0.0696
   2.5 vs 4.0:  21 vs  0  p<0.0001
   3.0 vs 3.5:   2 vs 10  p=0.0383      <-- 3.5 significantly WORSE than 3.0
   3.0 vs 4.0:   2 vs  0  p=0.4999      <-- not distinguishable
   3.5 vs 4.0:  10 vs  0  p=0.0019

read-level >=1000 ms
   2.5 vs 3.0:  11 vs  0  p=0.0010
   2.5 vs 4.0:  11 vs  0  p=0.0010
   3.0 vs 3.5:   0 vs  6  p=0.0311      <-- 3.5 worse again
   3.5 vs 4.0:   6 vs  0  p=0.0311
   3.0 vs 4.0:   0 vs  0  p=1.0000

gen0 >=500 ms (60 gen-0 reads per arm)
   2.5 vs 3.0:  10 vs  2  p=0.0295
   2.5 vs 4.0:  10 vs  0  p=0.0013
   3.5 vs 4.0:   7 vs  0  p=0.0130
   3.0 vs 4.0:   2 vs  0  p=0.4958

run-level (any >=500 ms, 15 runs per arm)  -- ALL NON-SIGNIFICANT
   2.5 vs 4.0: 4 vs 0  p=0.0996 ; 3.0 vs 4.0: 1 vs 0  p=1.0000 ; 3.5 vs 4.0: 3 vs 0  p=0.2241
```

**Qualifications I am applying:**
- **All run-level comparisons are underpowered and non-significant.** The read-level tests treat 1800 reads as independent, which they are not — reads cluster within runs, and a single catastrophic run can contribute many tail reads. **The effective sample size is closer to 15 runs per arm than 1800 reads.** These p-values are indicative, not confirmatory.
- The two results that survive that scepticism are the **large** read-level effects: 2.5 vs 4.0 (p<0.0001) and 3.5 vs 4.0 (p=0.0019).
- **3.0 vs 4.0 is not distinguishable on any measure** (p=0.50 on ≥500, p=1.0 on ≥1000).

---

## 8. Pathological runs and their launch signatures

Every sick run in every arm shows the **same signature**: the first read launches at t≈0, and a second read launches 2.6–4.0 ms later — both going slow together.

```
2.5  bd-b25-r02  worst=5565  :: #0w3 t=0.0 lat=5565 | #1w2 t=2.6 gap=2.57 lat=5563
2.5  bd-b25-r03  worst=11818 :: #0w3 t=0.0 lat=6062 | #1w2 t=2.7 gap=2.73 lat=11818
2.5  bd-b25-r06  worst= 908  :: #0w3 t=0.0 lat= 851 | #1w1 t=3.5 gap=3.54 lat= 908
2.5  bd-b25-r11  worst=2455  :: #0w3 t=0.0 lat=2416 | #1w0 t=2.6 gap=2.61 lat=2455
3.0  bd-b30-r07  worst= 656  :: #0w3 t=0.0 lat= 609 | #1w1 t=3.7 gap=3.68 lat= 656
3.5  bd-b35-r06  worst= 598  :: #0w3 t=0.0 lat= 549 | #1w2 t=3.5 gap=3.50 lat= 598
3.5  bd-b35-r07  worst=4082  :: #0w3 t=0.0 lat=4044 | #1w1 t=3.6 gap=3.59 lat=4082
3.5  bd-b35-r14  worst= 727  :: #0w3 t=0.0 lat= 679 | #1w0 t=4.0 gap=4.04 lat= 727
4.0  (none)
```

**Two things stand out, and one of them complicates the spacing story:**

1. The failure mode is always a **two-read front pair**, not a four-way collision. Once the pair is stuck, later launches are delayed by the block and the run's other reads are mostly healthy (low ge500 in g1–g3).
2. **`bd-b35-r14` had an *observed* first-pair gap of 4.04 ms — squarely inside the 4.0 ms arm's observed range (4.00–4.14 ms) — and it still went sick (679/727 ms).** So the outcome is **not a deterministic function of the observed first-pair gap**. At ~4.0 ms we observe both sick (1 run) and clean (15+3 runs).

---

## 9. Finding the line — the narrowest conclusion the evidence supports

**There is no clean line between 2 and 4 ms. The transition is non-monotonic and probabilistic.**

| spacing | verdict | evidence |
|---|---|---|
| **2.5 ms** | **clearly insufficient** | 21 reads ≥500, 11 ≥1000, worst 11.8 s; p<0.0001 vs 4.0 |
| **3.0 ms** | **appears sufficient** | 2 reads ≥500, **0 ≥1000**, worst 656 ms; **statistically indistinguishable from 4.0** |
| **3.5 ms** | **clearly insufficient** | 10 reads ≥500, 6 ≥1000, worst 4.08 s; significantly worse than *both* 3.0 (p=0.038) and 4.0 (p=0.0019) |
| **4.0 ms** | **clean** | 0 reads ≥500 in 1800; worst 319 ms |

**The narrowest supported statements:**

- **2.5 ms fails** — the protective region, if there is one, lies above 2.5 ms.
- **3.5 ms fails**, and it is *worse* than the smaller 3.0 ms spacing. So the ordering is **not monotonic in spacing**.
- **3.0 and 4.0 are statistically indistinguishable** on tails (p=0.50 / p=1.0).
- Therefore: **no spacing in the tested range (2.5–4.0 ms) is demonstrably a deterministic cure.** The 3.5 ms result proves spacing alone does not monotonically control the outcome.

**Smallest empirically robust spacing in this corpus: 4.0 ms** — the only spacing with **zero** `≥500 ms` reads across 15 runs (18 including the screening cohort, also zero). But I am not calling it a physical threshold: it is the smallest spacing at which we have **never observed** the failure, and 3.5 ms shows the property is probabilistic.

---

## 10. Direct answers

1. **Pooled median and mean preadv at each spacing?**

| spacing | pooled median | pooled mean |
|---|---|---|
| 2.5 ms | **43.40 ms** | **82.92 ms** |
| 3.0 ms | **42.98 ms** | **48.07 ms** |
| 3.5 ms | **42.76 ms** | **55.00 ms** |
| 4.0 ms (prior) | **43.03 ms** | **50.54 ms** |

2. **Smallest mean preadv?** **3.0 ms (48.07 ms)** — then 4.0 (50.54), 3.5 (55.00), 2.5 (82.92). But the spread is tail-driven, not latency-driven.
3. **Smallest median?** **3.5 ms (42.76 ms)** — but all four are within 0.64 ms (1.5%), i.e. effectively tied.
4. **Where do ≥500 ms tails disappear?** Only at **4.0 ms** (0 reads). 3.0 ms had 2, 3.5 ms had 10, 2.5 ms had 21.
5. **Where do ≥1000 ms tails disappear?** At **3.0 ms and 4.0 ms** (both 0). 2.5 ms had 11; 3.5 ms had 6.
6. **What happens to generation 0?** It carries essentially the whole effect in every arm — 10/2/7/0 of the `≥500 ms` reads are gen-0 for 2.5/3.0/3.5/4.0. Gen-0 medians are ~93–105 ms in *all* arms (front-loading persists) while gen-0 **means** diverge 94 → 870 ms. The tail is a gen-0 phenomenon.
7. **Narrowest supported transition bracket?** **None that is monotonic.** 3.5 ms fails while 3.0 ms is clean, so the data do not support a bracket of the form "protective above X". The only defensible bracket is `2.5 ms insufficient → 4.0 ms clean`, with 3.0 and 3.5 contradicting monotonicity.
8. **Smallest empirically robust spacing?** **4.0 ms** — the only spacing with zero `≥500 ms` reads in 15 runs (zero in 18 including the screen cohort).
9. **Does it retain real QD4 overlap?** **Yes** — overlap 0.982, effective concurrency 3.65 (the highest of the four arms), `max_active = 4` in all 15 runs.
10. **What throughput does it retain?** **The best of the four**: median 5.404 GB/s, mean 5.169, min 2.980.
11. **Does pacing improve ordinary/median reads, or primarily eliminate tails?** **Primarily eliminate tails.** Pooled medians are identical to within 1.5% across all arms (42.76–43.40 ms). The mean improvement is entirely the disappearance of multi-second outliers. Pacing does not make normal reads faster.
12. **What spacing to carry into the QD8 experiment?** **4.0 ms.**

---

## 11. Recommendation for the QD8 experiment

**Carry 4.0 ms.**

The case is not "more margin". It is:
- **4.0 ms is the only spacing with zero tail events** — 0 of 1800 reads ≥500 ms, 0 ≥1000 ms, worst 319 ms across 15 runs (and 18 when the screening cohort is included).
- **3.0 ms is statistically indistinguishable from it on tails** (2 vs 0 events, p=0.50) — so 3.0 is a legitimate candidate too, but it has observed failures where 4.0 has none.
- **4.0 ms also has the best throughput (5.404 GB/s median) and the best effective concurrency (3.65)**, so choosing it costs nothing measurable against 3.0.
- **3.5 ms must be avoided** — significantly worse than both 3.0 and 4.0.

**Important caveat for QD8:** because the 3.5 ms arm produced a sick run at an observed 4.04 ms gap, **spacing is a probabilistic risk-reducer, not a deterministic guarantee.** QD8 raises concurrency, so the QD8 experiment must treat 4.0 ms as *likely-but-unproven* protection and keep monitoring `≥500 ms` counts rather than assuming the tail is gone.

Stopping here. QD8 and hedging were not run.
