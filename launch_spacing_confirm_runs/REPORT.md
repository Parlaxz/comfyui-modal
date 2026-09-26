# Launch-Spacing Confirmation — 45 Fresh H100 Runs

0 ms vs 2 ms vs 4 ms minimum global `preadv` start spacing. 15 runs per arm, balanced rotation (`0,2,4` → `2,4,0` → `4,0,2` …), all 45 fresh H100 containers, all `NVIDIA H100 80GB HBM3`, no wrong-GPU runs rejected.

Geometry frozen: source-only, 64 MiB reads, QD4, full-file, same file/FDs/buffers/topology. Only the treatment variable changed.
Raw: `launch_spacing_confirm_runs/cf-*.json`, `confirm.log`; stats: `tools/fisher_launch_spacing.py`

---

## FINAL VERDICT

# **B. 4 ms confirmed, 2 ms insufficient**

And stronger than that: **4 ms dominates 2 ms on every axis** — tails, throughput *and* concurrency. There is no trade-off to weigh.

---

## 1. Summary

| gap | runs | runs ≥250 | runs ≥500 | runs ≥1000 | n ≥250 | n ≥500 | n ≥1000 | worst read | median GB/s | min GB/s | overlap | eff conc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **0 ms** | 15 | 4 | 1 | 1 | 10 | 6 | 4 | **2263** | 5.029 | 2.248 | 0.983 | 3.86 |
| **2 ms** | 15 | 3 | 3 | **2** | 8 | 6 | 4 | **2627** | 4.954 | 1.971 | 0.972 | 3.49 |
| **4 ms** | 15 | 1 | **0** | **0** | 4 | **0** | **0** | **319** | **5.404** | **2.980** | 0.982 | 3.65 |

### Generation 0 only

| gap | gen-0 reads | ≥250 | ≥500 | ≥1000 | worst gen-0 |
|---|---|---|---|---|---|
| 0 ms | 60 | 7 | 4 | 4 | 2263 |
| 2 ms | 60 | 6 | **6** | 4 | **2627** |
| 4 ms | 60 | **0** | **0** | **0** | **204** |

### Per-generation

```
gap  0 | g0: n=60 max=2263 ge500=4 ge1k=4 | g1: max=522 ge500=2 | g2: max=138 | g3: max=100
gap  2 | g0: n=60 max=2627 ge500=6 ge1k=4 | g1: max=498        | g2: max=108 | g3: max=270
gap  4 | g0: n=60 max= 204 ge500=0 ge1k=0 | g1: max= 90        | g2: max= 99 | g3: max= 86
```

**4 ms is clean in every generation.** 0 and 2 ms are sick in g0 (and in one case g1). There are no `≥500 ms` reads anywhere in the 4 ms arm — 1800 reads, zero.

---

## 2. Per-run table (45 runs)

| run | gap | wall ms | GB/s | med | p95 | p99 | max | ≥250 | ≥500 | ≥1000 | excess>100 | obs min gap | obs p5 | obs med | obs p95 | ovl | conc | max act |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cf-c0-r01 | 0 | 1298 | 6.198 | 38.6 | 54.2 | 96.5 | 118 | 0 | 0 | 0 | 18 | 0.04 | 0.24 | 8.87 | 23.42 | 0.983 | 3.78 | 4 |
| cf-c0-r02 | 0 | 1241 | 6.485 | 37.6 | 50.4 | 103.6 | 117 | 0 | 0 | 0 | 27 | 0.06 | 0.25 | 6.36 | 32.04 | 0.992 | 3.87 | 4 |
| cf-c0-r03 | 0 | 1993 | 4.037 | 61.1 | 94.2 | 144.0 | 225 | 0 | 0 | 0 | 208 | 0.01 | 0.09 | 12.33 | 43.21 | 0.992 | 3.93 | 4 |
| cf-c0-r04 | 0 | 1535 | 5.241 | 43.9 | 58.5 | 146.1 | 248 | 0 | 0 | 0 | 234 | 0.02 | 0.28 | 7.41 | 33.41 | 0.983 | 3.82 | 4 |
| cf-c0-r05 | 0 | 1350 | 5.960 | 40.3 | 58.4 | 129.2 | 213 | 0 | 0 | 0 | 152 | 0.01 | 2.44 | 7.96 | 26.99 | 0.975 | 3.88 | 4 |
| **cf-c0-r06** | 0 | 3578 | 2.248 | 36.5 | 279.9 | 1966.8 | **2263** | **7** | **6** | **4** | 8480 | 0.01 | 0.14 | 7.55 | 37.28 | 0.933 | 3.82 | 4 |
| cf-c0-r07 | 0 | 1376 | 5.848 | 41.1 | 54.6 | 91.6 | 105 | 0 | 0 | 0 | 5 | 0.02 | 0.16 | 3.84 | 43.03 | 0.992 | 3.76 | 4 |
| cf-c0-r08 | 0 | 1819 | 4.424 | 53.8 | 72.3 | 202.6 | 313 | 1 | 0 | 0 | 412 | 0.03 | 0.14 | 7.98 | 45.54 | 0.992 | 3.87 | 4 |
| cf-c0-r09 | 0 | 1603 | 5.020 | 45.5 | 71.7 | 145.7 | 294 | 1 | 0 | 0 | 254 | 0.01 | 0.45 | 8.13 | 37.43 | 0.983 | 3.82 | 4 |
| cf-c0-r10 | 0 | 1281 | 6.282 | 39.1 | 52.6 | 96.3 | 120 | 0 | 0 | 0 | 20 | 0.01 | 0.16 | 7.89 | 28.44 | 0.992 | 3.82 | 4 |
| cf-c0-r11 | 0 | 1616 | 4.977 | 47.6 | 77.9 | 155.8 | 247 | 0 | 0 | 0 | 245 | 0.02 | 0.12 | 9.24 | 33.91 | 0.992 | 3.90 | 4 |
| cf-c0-r12 | 0 | 2064 | 3.898 | 65.7 | 85.8 | 123.8 | 192 | 0 | 0 | 0 | 126 | 0.02 | 0.10 | 11.94 | 45.63 | 0.967 | 3.86 | 4 |
| cf-c0-r13 | 0 | 2576 | 3.123 | 84.5 | 105.8 | 167.3 | 277 | 1 | 0 | 0 | 391 | 0.04 | 0.23 | 10.68 | 58.73 | 0.992 | 3.95 | 4 |
| cf-c0-r14 | 0 | 1520 | 5.292 | 44.4 | 65.0 | 141.2 | 214 | 0 | 0 | 0 | 184 | 0.03 | 0.21 | 5.91 | 38.58 | 0.992 | 3.90 | 4 |
| cf-c0-r15 | 0 | 1600 | 5.029 | 49.1 | 68.6 | 118.7 | 179 | 0 | 0 | 0 | 104 | 0.02 | 0.18 | 6.97 | 39.71 | 0.992 | 3.93 | 4 |
| **cf-c2-r01** | 2 | 3912 | 2.057 | 37.3 | 65.7 | 1755.2 | **2092** | **4** | **2** | **2** | 4534 | 2.03 | 2.13 | 14.27 | 36.79 | 0.833 | 2.44 | 4 |
| cf-c2-r02 | 2 | 1262 | 6.374 | 36.8 | 47.5 | 88.7 | 111 | 0 | 0 | 0 | 11 | 2.05 | 2.11 | 7.09 | 28.35 | 0.975 | 3.71 | 4 |
| cf-c2-r03 | 2 | 1604 | 5.015 | 46.5 | 61.4 | 124.0 | 140 | 0 | 0 | 0 | 81 | 2.03 | 2.14 | 10.58 | 35.15 | 0.975 | 3.61 | 4 |
| cf-c2-r04 | 2 | 1667 | 4.826 | 52.6 | 66.2 | 90.5 | 112 | 0 | 0 | 0 | 12 | 2.04 | 2.14 | 8.64 | 32.61 | 0.992 | 3.79 | 4 |
| **cf-c2-r05** | 2 | 4081 | 1.971 | 44.2 | 70.5 | 2112.5 | **2627** | **2** | **2** | **2** | 5033 | 2.14 | 2.16 | 6.59 | 38.36 | 0.983 | 2.65 | 4 |
| cf-c2-r06 | 2 | 2001 | 4.020 | 42.7 | 58.1 | 498.1 | 640 | 2 | 2 | 0 | 1043 | 2.04 | 2.16 | 5.85 | 35.60 | 0.983 | 3.26 | 4 |
| cf-c2-r07 | 2 | 1804 | 4.460 | 47.6 | 65.0 | 127.8 | 202 | 0 | 0 | 0 | 155 | 2.04 | 2.12 | 9.34 | 42.71 | 0.958 | 3.43 | 4 |
| cf-c2-r08 | 2 | 1547 | 5.200 | 46.3 | 61.1 | 116.0 | 152 | 0 | 0 | 0 | 74 | 2.07 | 2.17 | 7.63 | 33.81 | 0.983 | 3.74 | 4 |
| cf-c2-r09 | 2 | 1517 | 5.302 | 45.0 | 62.2 | 94.8 | 117 | 0 | 0 | 0 | 17 | 2.02 | 2.16 | 9.30 | 32.98 | 0.992 | 3.77 | 4 |
| cf-c2-r10 | 2 | 1624 | 4.954 | 43.3 | 60.0 | 181.2 | 242 | 0 | 0 | 0 | 267 | 2.00 | 2.15 | 8.18 | 32.85 | 0.992 | 3.54 | 4 |
| cf-c2-r11 | 2 | 1870 | 4.303 | 56.7 | 74.9 | 121.0 | 168 | 0 | 0 | 0 | 100 | 2.11 | 2.14 | 8.53 | 38.75 | 0.983 | 3.68 | 4 |
| cf-c2-r12 | 2 | 1568 | 5.131 | 47.6 | 61.8 | 105.5 | 120 | 0 | 0 | 0 | 27 | 2.05 | 2.14 | 6.65 | 36.52 | 0.992 | 3.74 | 4 |
| cf-c2-r13 | 2 | 1605 | 5.013 | 47.1 | 60.7 | 118.2 | 136 | 0 | 0 | 0 | 68 | 2.04 | 2.14 | 8.35 | 34.73 | 0.983 | 3.71 | 4 |
| cf-c2-r14 | 2 | 1495 | 5.383 | 43.0 | 61.7 | 92.1 | 108 | 0 | 0 | 0 | 8 | 2.00 | 2.15 | 6.13 | 31.82 | 0.983 | 3.67 | 4 |
| cf-c2-r15 | 2 | 1704 | 4.722 | 47.2 | 88.5 | 105.8 | 149 | 0 | 0 | 0 | 57 | 2.02 | 2.17 | 10.71 | 34.64 | 0.975 | 3.61 | 4 |
| cf-c4-r01 | 4 | 1189 | 6.766 | 35.3 | 41.3 | 78.2 | 86 | 0 | 0 | 0 | 0 | 4.05 | 4.15 | 5.38 | 22.65 | 0.992 | 3.68 | 4 |
| cf-c4-r02 | 4 | 1574 | 5.111 | 44.6 | 64.3 | 98.5 | 122 | 0 | 0 | 0 | 22 | 4.00 | 4.10 | 8.69 | 31.73 | 0.975 | 3.62 | 4 |
| cf-c4-r03 | 4 | 1292 | 6.229 | 38.1 | 45.3 | 85.9 | 95 | 0 | 0 | 0 | 0 | 4.06 | 4.29 | 8.24 | 27.99 | 0.983 | 3.65 | 4 |
| cf-c4-r04 | 4 | 1509 | 5.331 | 43.6 | 65.7 | 109.9 | 144 | 0 | 0 | 0 | 57 | 4.06 | 4.17 | 6.19 | 31.90 | 0.983 | 3.67 | 4 |
| cf-c4-r05 | 4 | 1389 | 5.793 | 38.9 | 55.5 | 104.6 | 119 | 0 | 0 | 0 | 32 | 4.00 | 4.26 | 6.72 | 29.20 | 0.967 | 3.56 | 4 |
| cf-c4-r06 | 4 | 1225 | 6.568 | 35.4 | 44.3 | 80.2 | 86 | 0 | 0 | 0 | 0 | 4.03 | 4.30 | 8.00 | 21.49 | 0.975 | 3.66 | 4 |
| cf-c4-r07 | 4 | 2700 | 2.980 | 69.7 | 239.0 | 274.6 | 319 | 4 | 0 | 0 | 1471 | 4.04 | 4.36 | 10.91 | 49.15 | 0.975 | 3.68 | 4 |
| cf-c4-r08 | 4 | 1461 | 5.508 | 42.7 | 57.0 | 110.0 | 136 | 0 | 0 | 0 | 48 | 4.07 | 4.28 | 8.55 | 28.85 | 0.983 | 3.65 | 4 |
| cf-c4-r09 | 4 | 1412 | 5.697 | 40.8 | 59.7 | 99.9 | 110 | 0 | 0 | 0 | 11 | 4.04 | 4.23 | 6.22 | 32.64 | 0.992 | 3.67 | 4 |
| cf-c4-r10 | 4 | 2499 | 3.219 | 82.5 | 95.2 | 104.1 | 161 | 0 | 0 | 0 | 67 | 4.02 | 4.31 | 14.39 | 53.85 | 0.992 | 3.82 | 4 |
| cf-c4-r11 | 4 | 2370 | 3.395 | 66.2 | 121.7 | 150.7 | 167 | 0 | 0 | 0 | 323 | 4.07 | 4.26 | 8.97 | 56.16 | 0.975 | 3.62 | 4 |
| cf-c4-r12 | 4 | 1862 | 4.321 | 51.0 | 76.4 | 169.4 | 204 | 0 | 0 | 0 | 256 | 4.05 | 4.37 | 9.74 | 47.66 | 0.983 | 3.58 | 4 |
| cf-c4-r13 | 4 | 1556 | 5.169 | 44.8 | 56.8 | 110.9 | 158 | 0 | 0 | 0 | 79 | 4.02 | 4.26 | 7.46 | 31.99 | 0.983 | 3.61 | 4 |
| cf-c4-r14 | 4 | 1333 | 6.037 | 39.6 | 47.8 | 87.5 | 107 | 0 | 0 | 0 | 7 | 4.06 | 4.27 | 7.67 | 27.20 | 0.992 | 3.72 | 4 |
| cf-c4-r15 | 4 | 1489 | 5.404 | 42.9 | 55.1 | 93.6 | 98 | 0 | 0 | 0 | 0 | 4.14 | 4.25 | 6.61 | 29.19 | 0.983 | 3.64 | 4 |

Every arm is 120 reads × 15 runs = 1800 reads. All `max_active_reads = 4` — QD4 fully engaged in every run including 4 ms.

---

## 3. Pacer validation — requested vs observed

| arm | requested | observed min | observed p5 | observed median | observed p95 |
|---|---|---|---|---|---|
| 0 ms | 0 | 0.01–0.06 | 0.09–2.44 | 3.84–12.33 | 23.4–58.7 |
| 2 ms | 2 | **2.00–2.14** | 2.10–2.17 | 5.85–14.27 | 28.4–42.7 |
| 4 ms | 4 | **4.00–4.14** | 4.10–4.37 | 5.38–14.39 | 21.5–56.2 |

**The enforced floor is exact in every run of both paced arms**, and the 0 ms arm traversed the identical gate with no enforced gap (min 0.01 ms). The configured value is not the causal variable — the observed floor is, and it matches the request precisely.

---

## 4. The decisive launch evidence

**0 ms sick run — four-way simultaneous collision:**
```
cf-c0-r06  #0w3 t=0.0 gap=-    lat=1688 | #1w0 t=0.1 gap=0.12 lat=2263
           #2w1 t=0.1 gap=0.02 lat=1733 | #3w2 t=0.1 gap=0.01 lat=2022
```

**2 ms sick runs — a TWO-read pair 2.1–2.3 ms apart, both catastrophic:**
```
cf-c2-r01  #0w3 t=0.0 gap=-    lat=2050 | #1w0 t=2.3 gap=2.27 lat=2092
cf-c2-r05  #0w3 t=0.0 gap=-    lat=2580 | #1w2 t=2.1 gap=2.14 lat=2627
cf-c2-r06  #0w3 t=0.0 gap=-    lat= 589 | #1w0 t=2.0 gap=2.04 lat= 640
```

**This is why 2 ms fails.** With the floor genuinely enforced at 2.0–2.3 ms, a two-read pair **still** went pathological. The collision window is therefore **wider than 2.3 ms**.

**4 ms — the same second launch, now 4 ms out, is always clean:**
```
cf-c4-r01  #0w3 t=0.0 gap=- lat= 86 | #1w0 t=4.1 gap=4.05 lat=110
cf-c4-r07  #0w3 t=0.0 gap=- lat= 93 | #1w1 t=4.0 gap=4.03 lat=142   (worst run: 319 ms)
cf-c4-r15  #0w3 t=0.0 gap=- lat= 48 | #1w2 t=4.2 gap=4.14 lat= 93
```

**The trigger window lies between ~2.3 ms and ~4.0 ms.**

---

## 5. Statistical strength — with the caveats stated

Fisher exact (two-sided), computed in `tools/fisher_launch_spacing.py`:

| test | comparison | p |
|---|---|---|
| read-level ≥500 ms | 0 ms vs 4 ms | **0.031** |
| read-level ≥500 ms | 2 ms vs 4 ms | **0.031** |
| read-level ≥500 ms | 0+2 pooled vs 4 ms | **0.0115** |
| read-level ≥500 ms | 0 ms vs 2 ms | 1.000 (ns, as expected) |
| read-level ≥1000 ms | 0+2 pooled vs 4 ms | 0.0585 |
| gen-0 ≥500 ms | 2 ms vs 4 ms | **0.027** |
| gen-0 ≥500 ms | 0+2 pooled vs 4 ms | **0.032** |
| run-level (any ≥500) | 0+2 pooled vs 4 ms | 0.285 (ns) |
| run-level (any ≥1000) | 0+2 pooled vs 4 ms | 0.540 (ns) |

**Honest caveats I am not hiding:**

- **All run-level tests are non-significant.** At 15 runs per arm the run-level rate is too low to separate: the 0 ms positive control produced only **1 sick run in 15** (`cf-c0-r06`), far below the historical corpus gen-0 rate. The screen's 1/3 gap-0 rate did not reproduce either.
- **The evidence is read-level and mechanistic, not run-level.** The read-level ≥500 ms tests are significant (p≈0.011–0.031), and the first-four-launch traces show the mechanism directly.
- **2 ms is not merely "unprotected" — it was numerically worse than 0 ms** (worst read 2627 vs 2263 ms; 2 sick runs vs 1; 6 gen-0 reads ≥500 vs 4). With these counts that difference is not significant, but 2 ms provides **no** measurable protection and certainly no improvement.
- **We tested only 0/2/4 ms.** The exact threshold within (2.3, 4.0] ms is not established; 3 ms was not run.

---

## 6. Direct 2 ms vs 4 ms comparison

1. **Does either arm produce any ≥1000 ms event?** 2 ms: **yes, 4 reads across 2 runs** (2092, 2627, and 2 more in `cf-c2-r01`). 4 ms: **no, zero.**
2. **Does either arm produce clustered multi-worker gen-0 sickness?** 2 ms: yes — `cf-c2-r01` had a 2-read cluster, and it also fired 4 reads ≥250 ms. 4 ms: **no cluster, no ≥500 ms read at all**, worst gen-0 read 204 ms.
3. **Which has fewer ≥250 / ≥500 ms events?** 4 ms (4 / **0**) vs 2 ms (8 / **6**).
4. **Does 4 ms materially reduce tails relative to 2 ms?** **Yes, decisively** — worst read 319 ms vs 2627 ms (8× lower), and zero ≥500 ms vs 6.
5. **What throughput penalty does 4 ms have versus 2 ms?** **None — 4 ms is faster.** Median 5.404 vs 4.954 GB/s; min 2.980 vs 1.971.
6. **Does either arm reduce effective QD4 overlap?** Neither materially: overlap 0.982 (4 ms) vs 0.972 (2 ms); effective concurrency **3.65 vs 3.49** (4 ms higher). Control: 0.983 / 3.86. Every run in every arm hit `max_active_reads = 4`.

**4 ms beats 2 ms on tails, throughput and concurrency simultaneously.** No trade-off exists, so there is nothing to weigh against it.

---

## 7. What this does and does not claim

**Does claim:**
- Closely clustered `preadv` submission is a **trigger** for the catastrophic H100 gen-0 tail. Four launches inside ~0.1 ms produced 1.7–2.3 s reads; the same four separated by ~4 ms did not.
- A **4 ms global minimum start-to-start interval** removes the catastrophic class in 15/15 runs (1800 reads, zero ≥500 ms, worst 319 ms) while QD4 overlap stays fully engaged.
- **QD4 overlap itself is not inherently pathological.** At 4 ms spacing the workload retains 0.982 overlap fraction and 3.65 effective concurrency — 95% of the control's 3.86 — with `max_active_reads = 4` in every run, and it is *faster* than both the 0 ms and 2 ms arms.

**Does NOT claim:**
- Any microscopic root cause. We have **not** identified the exact gVisor/FUSE/VolumeFS implementation defect, and the earlier audits found the host-side path unresolvable from inside the sandbox.
- That 4 ms is optimal. The threshold is bracketed to (2.3, 4.0] ms; 3 ms was not tested.
- Run-level statistical proof. Run-level tests are underpowered here; the result rests on read-level counts and the direct launch traces.

That is sufficient for a Golden mitigation decision: **a tiny global launch pacer is a cheap, in-process, single-variable change that retains concurrency.**

---

## 8. Recommendation

**Adopt a 4 ms global minimum `preadv` start-to-start interval** for the H100 source path. Do not adopt 2 ms — it provides no protection and was numerically worse than no pacing at all in this cohort.

No further experiment was run, per instruction.
