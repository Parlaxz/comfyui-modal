# mmap window-size sweep — fresh-window architecture (C)

Carries forward **only C**: fresh `mmap` → native memcpy → `munmap`, repeated. Fixed: pure CPU
source I/O, **H100 host (GPU untouched)**, 4 processes, QD4, same `qwen_3_4b.safetensors`, same
self-service scheduler, MAP_POPULATE removed, exact full-file coverage, no toucher / preadv / M0 /
M1 / segmented mappings, no CUDA/H2D.

Workspace: **Testing 5** (`ws_c1487d319820`). Raw runs: `size_sweep/`. Report: `size_report/SIZE_SWEEP.md`.

Spacing scales with window size to hold the byte launch rate ~constant: 32 MiB→2 ms, 64 MiB→4 ms,
128 MiB→8 ms, 256 MiB→16 ms. This is **geometry isolation, not a pacing optimum** — pacing is
optimised separately later.

Counting: US only; singleton US regions excluded; excluded retained; Odin excluded.

| window | counted n | valid runs | excluded non-US |
|---|---:|---:|---:|
| 32 MiB | 6 | 36 | 28 |
| 64 MiB | 6 | 36 | 27 |
| 128 MiB | 6 | 36 | 28 |
| 256 MiB | 6 | 36 | 29 |

## Throughput / wall

| window | n | GB/s med | mean | p10 | p90 | best | worst | wall med | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **32 MiB** | 6 | **6.879** | **6.167** | 4.368 | **7.255** | **7.262** | 3.569 | **1171** | **1395** |
| 64 MiB | 6 | 5.189 | 4.970 | 3.879 | 5.843 | 6.096 | 3.331 | 1551 | 1682 |
| 128 MiB | 6 | 5.351 | 5.217 | 3.949 | 6.350 | 6.392 | 3.769 | 1509 | 1606 |
| 256 MiB | 6 | 5.581 | 5.321 | 4.097 | 6.283 | 6.664 | **3.969** | 1441 | 1564 |

**32 MiB is fastest on median (+32.5% vs 64 MiB), mean, p90, best and wall**, and 256 MiB has the
best worst-case.

## Variance

| window | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|
| 32 MiB | 1.3686 | **0.2219** | 1.0394 | **2.8873** |
| 64 MiB | 0.8886 | 0.1788 | 0.6748 | 1.9643 |
| 128 MiB | 1.0070 | 0.1930 | 0.9046 | 2.4014 |
| 256 MiB | 0.9402 | **0.1767** | 0.7327 | 2.1855 |

**32 MiB has the worst consistency** (CV 0.222, spread 2.89) despite being fastest; 256 MiB is
the most consistent (CV 0.177), with 64 MiB essentially tied (0.179).

## Per provider:region (n≥2)

| window | provider:region | n | median GB/s | CV | MAD | p90-p10 |
|---|---|---:|---:|---:|---:|---:|
| 32 MiB | GCP:us-west4 | 2 | 6.138 | 0.1583 | 0.9719 | 1.5550 |
| 32 MiB | OCI:us-central | 2 | 6.955 | 0.0441 | 0.3069 | 0.4910 |
| 32 MiB | UNSPECIFIED:us-central | 2 | 5.409 | 0.3401 | 1.8395 | 2.9432 |
| 64 MiB | GCP:us-west4 | 2 | 5.673 | 0.0747 | 0.4238 | 0.6781 |
| 64 MiB | OCI:us-chicago-1 | 2 | 5.360 | 0.0431 | 0.2307 | 0.3692 |
| 128 MiB | OCI:us-central | 2 | 5.986 | 0.0538 | 0.3223 | 0.5157 |
| 128 MiB | UNSPECIFIED:us-central | 2 | 4.404 | 0.1441 | 0.6347 | 1.0155 |
| 256 MiB | OCI:us-central | 3 | 5.902 | 0.0743 | 0.3567 | 0.8561 |

`OCI:us-central` is the only region appearing in all four arms (2/2/2/3): 6.955 / — / 5.986 /
5.902. Note 32 MiB's lead is concentrated in `OCI:us-central` and `GCP:us-west4`; in
`UNSPECIFIED:us-central` it is mid-pack. Cells are small (n=2–3), so this is indicative only.

## Operation cost (map + memcpy + unmap) and tails

| window | ops | median ms | p95 | p99 | worst | ≥250 | ≥500 | ≥1s | ≥2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 MiB | 1440 | 19.22 | 41.95 | 58.76 | 80.4 | 0 | 0 | 0 | 0 |
| 64 MiB | 720 | 50.50 | 86.92 | 118.29 | 143.3 | 0 | 0 | 0 | 0 |
| 128 MiB | 360 | 98.30 | 155.48 | 188.02 | 208.5 | 0 | 0 | 0 | 0 |
| 256 MiB | 180 | 183.02 | 287.37 | 352.15 | 360.1 | **26** | 0 | 0 | 0 |

**Normalized tails** — raw counts are not comparable, because each arm performs a different number
of operations for the same bytes:

| window | ops/TiB | ≥250 per 1000 ops | ≥250 per TiB | ≥500 per TiB | ≥1s per TiB |
|---|---:|---:|---:|---:|---:|
| 32 MiB | 32800.9 | 0.00 | 0.00 | 0.00 | 0.00 |
| 64 MiB | 16400.5 | 0.00 | 0.00 | 0.00 | 0.00 |
| 128 MiB | 8200.2 | 0.00 | 0.00 | 0.00 | 0.00 |
| 256 MiB | 4100.1 | **144.44** | **592.24** | 0.00 | 0.00 |

### The absolute threshold is size-biased — read this before comparing tails

`≥250 ms` is an **absolute** threshold, and a 256 MiB operation is 8× the work of a 32 MiB one, so
it crosses that bar far more easily. Normalising each arm against **its own median** inverts the
picture:

| window | median op | worst op | worst ÷ median |
|---|---:|---:|---:|
| 32 MiB | 19.22 | 80.4 | **4.18×** |
| 64 MiB | 50.50 | 143.3 | 2.84× |
| 128 MiB | 98.30 | 208.5 | 2.12× |
| **256 MiB** | 183.02 | 360.1 | **1.97×** |

So on an absolute threshold **256 MiB looks tail-prone** (26 ops ≥250 ms, 2/6 runs affected), while
on a size-relative basis **256 MiB has the tightest worst-case and 32 MiB the loosest**. Both
statements are true; they answer different questions. **No tail winner is declared.**

## Affected-run count

| window | runs ≥250 | runs ≥500 | runs ≥1s | runs ≥2s |
|---|---:|---:|---:|---:|
| 32 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 64 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 128 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 256 MiB | 2/6 | 0/6 | 0/6 | 0/6 |

## Phase split, concurrency, spacing, finish spread

| window | map_ms med | memcpy_ms med | unmap_ms med | op_wall med | eff concurrency | achieved min spacing | finish spread |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 MiB | 0.039 | 17.84 | 1.203 | 19.22 | 3.9328 | 2.0051 | 1153 |
| 64 MiB | 0.056 | 47.66 | 2.725 | 50.50 | 3.9341 | 4.0270 | 1504 |
| 128 MiB | 0.062 | 94.76 | 4.719 | 98.30 | 3.8847 | 8.0296 | 1415 |
| 256 MiB | 0.068 | 172.72 | 9.568 | 183.02 | 3.7866 | 16.0813 | 1272 |

- **`mmap` itself is essentially free** (0.04–0.07 ms) at every size.
- **memcpy dominates** the operation (93–94% of op_wall).
- **unmap scales with window size** (1.2 → 9.6 ms), but stays a similar *fraction* (~5–6%).
- **Achieved spacing matches nominal almost exactly** (2.0051 / 4.0270 / 8.0296 / 16.0813 ms).
- Effective concurrency ≈3.8–3.9 for all arms.

## Every operation ≥250 ms, with absolute byte range

| window | run | provider:region | offset | length | op ms | intersects historical offset |
|---|---|---|---:|---:|---:|---|
| 256 MiB | im-29 | OCI:us-central | 4026531840 | 268435456 | 268.8 | **4160749568** |
| 256 MiB | im-29 | OCI:us-central | 3758096384 | 268435456 | 265.2 | no |
| 256 MiB | im-29 | OCI:us-central | 3489660928 | 268435456 | 276.1 | no |
| 256 MiB | im-29 | OCI:us-central | 3221225472 | 268435456 | 287.4 | no |
| 256 MiB | im-29 | OCI:us-central | 2952790016 | 268435456 | 250.5 | no |
| 256 MiB | im-29 | OCI:us-central | 2684354560 | 268435456 | 256.4 | no |
| 256 MiB | im-29 | OCI:us-central | 2415919104 | 268435456 | 255.2 | no |
| 256 MiB | im-29 | OCI:us-central | 2147483648 | 268435456 | 360.1 | no |
| 256 MiB | im-29 | OCI:us-central | 4294967296 | 268435456 | 254.8 | no |
| 256 MiB | im-29 | OCI:us-central | 4563402752 | 268435456 | 264.4 | no |
| 256 MiB | im-29 | OCI:us-central | 4831838208 | 268435456 | 270.7 | no |
| 256 MiB | im-29 | OCI:us-central | 5100273664 | 268435456 | 262.3 | no |
| 256 MiB | im-29 | OCI:us-central | 5368709120 | 268435456 | 276.4 | no |
| 256 MiB | im-29 | OCI:us-central | 5637144576 | 268435456 | 273.6 | no |
| 256 MiB | im-29 | OCI:us-central | 5905580032 | 268435456 | 259.4 | no |
| 256 MiB | im-29 | OCI:us-central | 6174015488 | 268435456 | 272.7 | no |
| 256 MiB | im-29 | OCI:us-central | 6442450944 | 268435456 | 282.5 | no |
| 256 MiB | im-29 | OCI:us-central | 6710886400 | 268435456 | 270.2 | no |
| 256 MiB | im-29 | OCI:us-central | 6979321856 | 268435456 | 281.6 | no |
| 256 MiB | im-29 | OCI:us-central | 7247757312 | 268435456 | 277.9 | no |
| 256 MiB | im-29 | OCI:us-central | 7516192768 | 268435456 | 266.8 | no |
| 256 MiB | im-29 | OCI:us-central | 7784628224 | 268435456 | 291.3 | no |
| 256 MiB | im-29 | OCI:us-central | 134217728 | 268435456 | 264.9 | no |
| 256 MiB | im-29 | OCI:us-central | 402653184 | 268435456 | 267.3 | no |
| 256 MiB | im-29 | OCI:us-central | 671088640 | 268435456 | 271.5 | no |
| 256 MiB | im-29 | OCI:us-central | 939524096 | 268435456 | 266.1 | no |

**All 26 ≥250 ms operations come from a single run (`im-29`, OCI:us-central)**, and they are
*contiguous across the file* rather than concentrated at any one offset. That is the signature of a
uniformly slow host/period, not of specific bad byte ranges. Only one intersects a historical
offset (`4160749568`), and only because 256 MiB windows cover 1/30th of the file each. **No
evidence that the historical offsets are inherently bad.**

## Outliers (provider:region on every one)

| window | kind | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---|---:|---:|---:|
| 32 MiB | bottom-decile | im-09 | UNSPECIFIED:us-central | 3.569 | 2254 | 80.4 |
| 32 MiB | bottom-decile | im-25 | UNSPECIFIED:us-central | 4.903 | 1640 | 62.4 |
| 32 MiB | worst run | im-09 | UNSPECIFIED:us-central | 3.569 | 2254 | 80.4 |
| 64 MiB | bottom-decile | im-38 | GCP:us-west4 | 3.331 | 2412 | 143.3 |
| 64 MiB | worst run | im-38 | GCP:us-west4 | 3.331 | 2412 | 143.3 |
| 128 MiB | bottom-decile | im-55 | UNSPECIFIED:us-central | 3.769 | 2134 | 208.5 |
| 128 MiB | worst run | im-55 | UNSPECIFIED:us-central | 3.769 | 2134 | 208.5 |
| 256 MiB | bottom-decile | im-76 | OCI:us-central | 3.969 | 2026 | 360.1 |
| 256 MiB | worst run | im-76 | OCI:us-central | 3.969 | 2026 | 360.1 |

## Guards

| window | exact coverage | amp=1.0 | maxQD=4 | min spacing ≥ nominal | worker errors | map/unmap errors |
|---|---|---|---|---|---|---|
| 32 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 64 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 128 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 256 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |

No SIGBUS, no worker death, no mapping leaks (live maps return to 0), no offsets beyond EOF — the
final partial window is clipped to the logical block and never touched past EOF. Offsets are
page-aligned by construction (32/64/128/256 MiB are all multiples of 4096).

---

## The tradeoff (presented, not decided)

| | 32 MiB | 64 MiB | 128 MiB | 256 MiB |
|---|---|---|---|---|
| throughput (median) | **best (+32.5% vs 64)** | worst | mid | mid-high |
| consistency (CV) | **worst (0.222)** | good (0.179) | mid (0.193) | **best (0.177)** |
| worst-case absolute | 80 ms | 143 ms | 209 ms | 361 ms |
| worst ÷ own median | **worst (4.18×)** | 2.84× | 2.12× | **best (1.97×)** |
| ops per TiB | 32,801 | 16,401 | 8,200 | **4,100** |
| mmap cost | 0.04 ms | 0.06 ms | 0.06 ms | 0.07 ms |

- **32 MiB buys throughput at the cost of consistency** — fastest median by a wide margin, but the
  loosest tail relative to its own scale and the worst CV.
- **256 MiB buys consistency and fewest operations** — best CV, tightest worst÷median, 8× fewer
  operations than 32 MiB — at the cost of the lowest pooled median of the three larger arms.
- **64 MiB sits mid-pack on throughput and near-best on consistency**; it is the only arm with no
  distinguishing advantage in this cohort.
- The `≥250 ms` tail count for 256 MiB is an artefact of an absolute threshold applied to 8× larger
  operations, not evidence of a worse path.

**No winner is declared.** Picking between 32 MiB (throughput) and 256 MiB (consistency, fewer
operations) is Ahmed's tradeoff. No QD or pacing optimisation was started.
