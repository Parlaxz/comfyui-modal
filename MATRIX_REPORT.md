# Full mmap geometry matrix — 4 window sizes × 3 QD levels

12 cells = {32, 64, 128, 256} MiB × QD{4, 6, 8}. Fresh-window architecture only:
`mmap` exact window → native memcpy → `munmap`, repeated.

**Fixed:** pure CPU source I/O · **H100 host (GPU untouched)** · Testing 5 (`ws_c1487d319820`) ·
same `qwen_3_4b.safetensors` · same self-service scheduler · MAP_POPULATE removed · exact
full-file coverage · no preadv / toucher / M0 / M1 / persistent / segmented mappings · no
CUDA/H2D. Spacing byte-normalized and NOT optimized: 32→2 ms, 64→4 ms, 128→8 ms, 256→16 ms.

**Counting rule (as directed):** per ARM, include runs from any region with **≥3 runs in that
arm**; exclude regions with <3 runs in that arm. **No US-only filter.** Odin excluded, all
excluded runs retained in `matrix_runs/`.

**Interleaving:** 20 rounds × 12 cells, each round a different permutation (seed `20261001`), so
no arm runs in a contiguous batch and none is systematically early or late. Verified: each cell
exactly 20× per schedule pass, every round a full permutation, mean slot positions all ~118–121.
The launch sequence is reproducible from the seed.

Artifacts: `matrix_runs/` (raw), `matrix_report/MATRIX.md` (full tables).

## Launch accounting

240 counted, min cell 20, all cells at target.

| window/QD | launches | counted | excluded | regions counted |
|---|---:|---:|---:|---|
| 32/4 | 37 | 20 | 17 | us-chicago-1 5, ap-northeast 3, us-central 9, us-west 3 |
| 32/6 | 36 | 20 | 16 | ap-northeast 3, europe-west2 3, CANADA-2 1, us-central 8, uk 1, us-chicago-1 2, us-east 2 |
| 32/8 | 36 | 20 | 16 | us-chicago-1 3, us-central 10, asia-northeast1 2, ca 2, eu-west 3 |
| 64/4 | 36 | 20 | 16 | us-west4 3, asia-northeast1 4, us-chicago-1 5, us-central 8 |
| 64/6 | 37 | 20 | 17 | us-chicago-1 8, CANADA-2 4, uk 2, us-central 6 |
| 64/8 | 36 | 20 | 16 | ap-northeast 2, CANADA-2 1, us-central 10, us-chicago-1 5, us-east 2 |
| 128/4 | 35 | 20 | 15 | us-chicago-1 5, us-central 11, ap-northeast 3, CANADA-2 1 |
| 128/6 | 36 | 20 | 16 | uk 4, CANADA-2 2, us-central 6, us-chicago-1 4, ap-northeast 4 |
| 128/8 | 36 | 20 | 16 | asia-northeast1 3, uk 2, CANADA-2 3, us-central 7, us-chicago-1 4, ap-northeast 1 |
| 256/4 | 37 | 20 | 17 | uk 2, us-central 12, ap-northeast 2, us-chicago-1 2, eu-west 2 |
| 256/6 | 35 | 20 | 15 | CANADA-2 3, us-chicago-1 7, us-central 10 |
| 256/8 | 36 | 20 | 16 | ca 3, uk 2, us-central 9, eu-west 3, us-east 3 |

## The matrices

**1. median GB/s**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 5.677 | 5.613 | **6.027** |
| 64 MiB | 5.773 | **6.152** | 5.362 |
| 128 MiB | 5.644 | 5.541 | 5.541 |
| 256 MiB | 5.559 | 5.693 | 5.580 |

**2. p10 GB/s**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 3.087 | 4.119 | 4.025 |
| 64 MiB | 4.914 | 3.734 | 4.507 |
| 128 MiB | 4.326 | 4.027 | 3.779 |
| 256 MiB | 3.279 | **5.075** | 3.966 |

**3. wall median (ms)**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 1417 | 1434 | **1335** |
| 64 MiB | 1394 | **1320** | 1502 |
| 128 MiB | 1425 | 1459 | 1454 |
| 256 MiB | 1447 | 1414 | 1442 |

**4. CV**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 0.2985 | 0.2628 | 0.2784 |
| 64 MiB | **0.1568** | 0.3192 | 0.3318 |
| 128 MiB | 0.1879 | 0.3325 | 0.3154 |
| 256 MiB | 0.2265 | 0.1804 | 0.2719 |

**5. MAD**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 1.3151 | 1.2078 | 1.4737 |
| 64 MiB | **0.7125** | 1.7777 | 1.3707 |
| 128 MiB | 0.8486 | 1.8107 | 1.5922 |
| 256 MiB | 0.9065 | 0.7945 | 1.0282 |

**6. p90−p10**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 4.894 | 3.949 | 4.658 |
| 64 MiB | 2.120 | 5.064 | 2.887 |
| 128 MiB | 2.796 | 4.490 | 4.495 |
| 256 MiB | 3.412 | **1.933** | 2.849 |

**7. worst-run GB/s**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 2.434 | 2.898 | 3.594 |
| 64 MiB | **4.095** | 2.191 | 0.216 |
| 128 MiB | 3.892 | 2.319 | 2.719 |
| 256 MiB | 2.597 | 3.839 | 1.495 |

**8. effective concurrency**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 3.9187 | 5.8901 | 7.7623 |
| 64 MiB | 3.9191 | 5.8244 | 7.7782 |
| 128 MiB | 3.8752 | 5.7518 | 7.5919 |
| 256 MiB | 3.7741 | 5.6105 | 7.2465 |

**9. normalized tail severity (worst op ÷ own median)**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 54.59 | 42.12 | 12.36 |
| 64 MiB | 20.33 | 26.15 | **378.56** |
| 128 MiB | 3.90 | 11.80 | 11.51 |
| 256 MiB | 2.85 | **2.20** | 13.06 |

**10. affected-run % (≥250 ms)**

| window \ QD | QD4 | QD6 | QD8 |
|---|---:|---:|---:|
| 32 MiB | 10.0% | 5.0% | 5.0% |
| 64 MiB | 10.0% | 10.0% | 20.0% |
| 128 MiB | **5.0%** | 40.0% | 60.0% |
| 256 MiB | 30.0% | **90.0%** | **100.0%** |

## Operation distribution

| cell | ops | op med | p95 | p99 | worst | worst/med | p95/med | p99/med | ≥250 | ≥500 | ≥1s | ≥2s | per1000 | per TiB | affected |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32/4 | 4440 | 14.6 | 24.0 | 35.7 | 1170.0 | 54.59 | 1.65 | 2.44 | 6 | 4 | 2 | 0 | 1.4 | 5.6 | 2/20 (10%) |
| 32/6 | 4320 | 16.1 | 26.0 | 36.5 | 1463.2 | 42.12 | 1.62 | 2.27 | 4 | 2 | 2 | 0 | 0.9 | 3.7 | 1/20 (5%) |
| 32/8 | 4320 | 15.3 | 24.5 | 34.5 | 506.0 | 12.36 | 1.60 | 2.25 | 3 | 2 | 0 | 0 | 0.7 | 2.8 | 1/20 (5%) |
| 64/4 | 2160 | 32.0 | 51.7 | 71.1 | 895.5 | 20.33 | 1.62 | 2.22 | 2 | 1 | 0 | 0 | 0.9 | 3.7 | 2/20 (10%) |
| 64/6 | 2220 | 33.2 | 52.4 | 76.2 | 1635.8 | 26.15 | 1.58 | 2.29 | 12 | 1 | 1 | 0 | 5.4 | 21.6 | 2/20 (10%) |
| 64/8 | 2160 | 36.7 | 56.4 | 84.7 | 1430.9 | 378.56 | 1.54 | 2.31 | 4 | 1 | 1 | 0 | 1.9 | 7.4 | 4/20 (20%) |
| 128/4 | 2100 | 65.4 | 103.3 | 140.0 | 259.6 | 3.90 | 1.58 | 2.14 | 1 | 0 | 0 | 0 | 0.5 | 2.0 | 1/20 (5%) |
| 128/6 | 2160 | 66.5 | 104.9 | 145.9 | 764.3 | 11.80 | 1.58 | 2.19 | 11 | 3 | 0 | 0 | 5.1 | 20.3 | 8/20 (40%) |
| 128/8 | 2160 | 66.9 | 103.0 | 141.6 | 754.7 | 11.51 | 1.54 | 2.12 | 9 | 3 | 0 | 0 | 4.2 | 16.6 | 12/20 (60%) |
| 256/4 | 2220 | 130.4 | 199.5 | 268.4 | 350.6 | 2.85 | 1.53 | 2.06 | 9 | 0 | 0 | 0 | 4.1 | 16.2 | 6/20 (30%) |
| 256/6 | 2100 | 132.9 | 200.4 | 270.5 | 312.1 | 2.20 | 1.51 | 2.04 | 23 | 0 | 0 | 0 | 11.0 | 43.7 | 18/20 (90%) |
| 256/8 | 2160 | 133.5 | 202.2 | 276.5 | 1745.6 | 13.06 | 1.51 | 2.07 | 22 | 6 | 1 | 0 | 10.2 | 40.5 | 20/20 (100%) |

## Execution

| cell | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 32/4 | 3.919 | 4 | 1130 | 0.041 | 13.6 | 1.05 | 14.6 | 2.002 |
| 32/6 | 5.890 | 6 | 1043 | 0.044 | 15.2 | 1.06 | 16.1 | 2.005 |
| 32/8 | 7.762 | 8 | 1014 | 0.042 | 14.4 | 1.03 | 15.3 | 2.004 |
| 64/4 | 3.919 | 4 | 1176 | 0.052 | 30.2 | 2.16 | 32.0 | 4.017 |
| 64/6 | 5.824 | 6 | 1121 | 0.055 | 31.1 | 2.19 | 33.2 | 4.012 |
| 64/8 | 7.778 | 8 | 1245 | 0.053 | 34.7 | 2.23 | 36.7 | 4.010 |
| 128/4 | 3.875 | 4 | 1204 | 0.061 | 61.9 | 4.02 | 65.4 | 8.031 |
| 128/6 | 5.752 | 6 | 1298 | 0.062 | 62.7 | 4.05 | 66.5 | 8.028 |
| 128/8 | 7.592 | 8 | 1362 | 0.063 | 62.8 | 4.06 | 66.9 | 8.027 |
| 256/4 | 3.774 | 4 | 1310 | 0.066 | 124.4 | 7.83 | 130.4 | 16.055 |
| 256/6 | 5.611 | 6 | 1421 | 0.068 | 125.2 | 8.14 | 132.9 | 16.041 |
| 256/8 | 7.247 | 8 | 1498 | 0.069 | 126.0 | 8.31 | 133.5 | 16.038 |

## Deltas — QD ladder per window (median GB/s)

| window | QD4→QD6 | QD6→QD8 | QD4→QD8 |
|---|---:|---:|---:|
| 32 MiB | −1.1% | **+7.4%** | +6.2% |
| 64 MiB | **+6.6%** | −12.8% | −7.1% |
| 128 MiB | −1.8% | −0.0% | −1.8% |
| 256 MiB | +2.4% | −2.0% | +0.4% |

## Deltas — size ladder per QD (median GB/s)

| QD | 32→64 | 64→128 | 128→256 |
|---|---:|---:|---:|
| QD4 | +1.7% | −2.2% | −1.5% |
| QD6 | **+9.6%** | **−9.9%** | +2.7% |
| QD8 | **−11.0%** | +3.3% | +0.7% |

## Pathological operations — region recurrence

All ≥250 ms operations are listed with absolute byte range in `matrix_report/MATRIX.md`. Key
observations:

- **The 256/QD6 and 256/QD8 pathology is NOT region-specific.** Affected runs appear in *every*
  region those cells sampled: 256/6 → OCI:us-central 7/9, OCI:us-chicago-1 7/7, CANADA-2 3/3;
  256/8 → OCI:us-central 9/9, GCP:eu-west 3/3, UNSPECIFIED:ca 3/3. That is a genuine
  configuration effect, not placement.
- **128/QD6 and 128/QD8 are similarly destabilized**: 128/6 GCP:uk 4/4 affected; 128/8
  asia-northeast1 3/3, CANADA-2 3/3, OCI:us-chicago-1 2/4.
- **128/QD4 and 32/QD6-8 are the cleanest**: 128/4 OCI:ap-northeast CV **0.0064** with 0 affected;
  32/6 and 32/8 have 0 affected runs in every region except their single slow run.
- **Historical-offset recurrence continues but is not exclusive.** `6039797760` appears in ≥250 ms
  ops in 32/4 (im-22, im-388), 32/8 (im-242) and 64/4 (im-117, im-408); `4093640704` in 32/4
  (im-388) and 64/6 (im-15); `4026531840` in 32/4 (im-22) and 32/6 (im-279). Those same offsets
  also appear in thousands of healthy operations, so this is recurrence, **not** evidence that the
  offsets are inherently bad.
- The two worst single operations are **not** at historical offsets: 64/6 im-15 offset 2147483648
  (1635.8 ms) and 32/6 im-279 offset 4026531840 (1463.2 ms).

## Guards — all 12 cells clean

| check | result |
|---|---|
| exact full-file coverage | 20/20 in every cell |
| amplification = 1.0 | 20/20 in every cell |
| max physical QD == requested QD | 20/20 in every cell |
| min spacing ≥ nominal | 20/20 in every cell |
| worker errors | 0 |
| map / unmap errors | 0 / 0 |
| mapping leaks | none (live maps return to 0) |
| SIGBUS / worker death | none |
| page-aligned offsets | by construction (32/64/128/256 MiB) |
| EOF clipping | final partial window clipped, never touched past EOF |

Effective concurrency confirms **real QD**: 3.77–3.92 at QD4, 5.61–5.89 at QD6, 7.25–7.78 at QD8.

---

## Answers

1. **Highest throughput at each QD?** QD4 → **64 MiB** (5.773). QD6 → **64 MiB** (6.152). QD8 → **32 MiB** (6.027).
2. **Highest throughput at each window?** 32 MiB → **QD8** (6.027). 64 MiB → **QD6** (6.152). 128 MiB → **QD4** (5.644). 256 MiB → **QD6** (5.693).
3. **Lowest variance?** **64/QD4** (CV 0.1568, MAD 0.7125) — best on both. Next: 256/QD6 (CV 0.1804).
4. **Best p10 / low-end?** **256/QD6** (p10 5.075), then 64/QD4 (4.914).
5. **Tightest relative operation distribution?** **256/QD6** (worst÷median 2.20, p99÷median 2.04), then 256/QD4 (2.85).
6. **Does QD6 or QD8 improve 32 MiB further?** **QD8 does** (+7.4% over QD6, +6.2% over QD4). **QD6 does not** (−1.1%).
7. **Does higher QD stabilize or destabilize 32 MiB?** **Stabilizes the tail** (worst-run 2.434 → 3.594 GB/s, affected 10% → 5%, severity 54.6 → 12.4) but **not the CV** (0.299 → 0.263 → 0.278, non-monotonic).
8. **Do larger windows benefit from higher QD?** **No — they are harmed.** 256 MiB goes from 30% affected at QD4 to **90% at QD6 and 100% at QD8**, and 128 MiB from 5% → 40% → 60%. Only 32 MiB benefits.
9. **When does service latency inflate faster than useful concurrency?** **Immediately above QD4 for windows ≥128 MiB.** Effective concurrency scales as designed (3.9 → 5.8 → 7.6) but median throughput is flat (5.5–6.0 GB/s) while affected-run rate explodes. QD buys concurrency, not throughput, and pays in tails.
10. **Obvious size × QD knee?** Yes. **64/QD4 and 256/QD6** are the best-behaved cells; **256/QD6-8, 128/QD6-8 and 64/QD8** are the worst. The knee sits at QD4–6 for 64–256 MiB; only 32 MiB tolerates QD8.
11. **Consistent within provider:region?** **Yes for the pathologies** (256/6-8 and 128/6-8 are affected in every region sampled — a configuration effect). **Less so for medians**: e.g. 64/6 OCI:us-central 8.506 vs CANADA-2 5.266; 128/6 OCI:us-central 8.375 vs GCP:uk 4.089. Region still moves medians materially.
12. **Strictly dominated?** **64/QD8** (worst run 0.216 GB/s, severity 378×) and **256/QD8** (100% of runs affected) are dominated — no axis favours them. **128/QD6** and **128/QD8** are also dominated by 128/QD4 (worse tails, same throughput).
13. **Which 2–4 deserve the pacing/final-validation phase?**
    - **64/QD4** — best variance (CV 0.157) and best worst-run (4.095), solid median (5.773)
    - **256/QD6** — best low-end (p10 5.075), best relative tail (2.20), best p90−p10 (1.933)
    - **32/QD8** — best small-window throughput (6.027) and best wall (1335 ms)
    - **128/QD4** — lowest affected-run rate of any cell (5%) with 5.644 median

## The frontier (presented, not decided)

| configuration | throughput | variance / tail cost | low-end |
|---|---|---|---|
| 64/QD4 | 5.773 med | **best CV 0.157, best MAD 0.713**, 10% affected | p10 4.914 |
| 256/QD6 | 5.693 med | 90% affected, but **tightest relative tail 2.20** | **p10 5.075 (best)** |
| 32/QD8 | **6.027 med (best)** | 5% affected, but CV 0.278 and severity 12.4 | p10 4.025 |
| 128/QD4 | 5.644 med | **5% affected (best)**, CV 0.188 | p10 4.326 |
| 64/QD6 | **6.152 med (best overall)** | 10% affected but one 1636 ms op | p10 3.734 |
| 256/QD8 | 5.580 | **100% affected, severity 13.1** | p10 3.966 |

- **Throughput is essentially flat** across the whole matrix (5.36–6.15 GB/s median, ~15% spread), so the *choice is dominated by variance and tails, not throughput*.
- **Higher QD does not buy throughput** — it buys concurrency that the path cannot convert, and it inflates tails for windows ≥128 MiB.
- **32 MiB is the only size where higher QD helps**, and it pays in CV.

**No winner declared.** 64/QD4 and 256/QD6 are the two most defensible, but they trade opposite things: 64/QD4 is the variance/low-end-consistency pick, 256/QD6 is the low-end/tail-shape pick. That tradeoff is yours.

## Honest limitations

- **Counting rule changed mid-experiment** (as you directed): runs collected under the earlier US-only rule are still valid; only the *filtering* changed, so no runs were wasted. All 433 valid non-Odin launches are retained.
- The 12 cells drew **different region mixes**, so per-cell medians carry composition effects. The pathological-run findings are robust to this because they reproduce *within* region.
- Cells are n=20; per-region sub-cells are n=3–12.
- `≥250 ms` is an absolute threshold and is size-biased (a 256 MiB op is 8× the work of a 32 MiB op), which is why the relative measures (worst÷median, p95÷median, per-TiB) are reported alongside.
- No pacing optimization was started.
