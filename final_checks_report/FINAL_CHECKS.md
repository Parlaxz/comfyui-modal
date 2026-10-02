# CHECK 1 — MAP_PRIVATE vs MAP_SHARED (64 MiB / QD4 / 4 ms / fresh-window)

Everything identical except the mmap flag: A = `MAP_PRIVATE`, B = read-only
`MAP_SHARED`. Both are `PROT_READ`. Strong interleave: 30 rounds of 2 arms, each
round a different permutation (seed 20261004).

**Counting rule:** per arm, regions with >=3 runs; drop <3-run regions; no US-only
filter; Odin excluded but retained; never excluded because slow. Target 15 counted/arm.

| arm | map flag | launches | counted | excluded | regions counted |
|---|---|---:|---:|---:|---|
| A | MAP_PRIVATE | 30 | 15 | 15 | {'asia-northeast1': 4, 'us-central': 3, 'us-west': 3, 'ca': 5} |
| B | MAP_SHARED | 30 | 15 | 15 | {'asia-northeast1': 3, 'uk': 3, 'ap-northeast': 2, 'us-west': 4, 'CANADA-2': 3} |

## Whole-run

| arm | n | median | mean | p10 | p90 | best | worst | wall med | wall mean | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 15 | 6.224 | 6.208 | 5.345 | 7.282 | 8.228 | 4.128 | 1293 | 1328 | 0.9433 | 0.1520 | 0.6992 | 1.937 |
| B | 15 | 5.506 | 5.423 | 3.072 | 6.966 | 7.364 | 2.878 | 1461 | 1616 | 1.3582 | 0.2504 | 0.9586 | 3.894 |

## Operation distribution

| arm | ops | med | p95 | p99 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | per1000 | per TiB | affected runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1800 | 40.3 | 64.7 | 90.1 | 578.8 | 8 | 2 | 1 | 1 | 0 | 0 | 0.6 | 9.1 | 1/15 (7%) |
| B | 1800 | 44.9 | 101.4 | 130.8 | 706.8 | 102 | 11 | 2 | 2 | 0 | 0 | 1.1 | 18.2 | 1/15 (7%) |

## Normalized tails — BOTH definitions kept separate

| arm | (1) pooled worst/pooled med | (2) max per-run worst/own med | p95/med | p99/med |
|---|---:|---:|---:|---:|
| A | 14.35 | 13.76 | 1.60 | 2.23 |
| B | 15.75 | 21.02 | 2.26 | 2.92 |

## Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3.897 | 4 | 1257 | 0.056 | 38.3 | 2.07 | 40.3 | 4.001 |
| B | 3.895 | 4 | 1416 | 0.060 | 42.3 | 2.20 | 44.9 | 4.005 |

## Per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected runs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | GCP:asia-northeast1 | 4 | 6.142 | 0.0697 | 0.3397 | 5.812 | 6.697 | 0 |
| A | GCP:us-west | 3 | 5.698 | 0.0715 | 0.3344 | 5.361 | 6.163 | 1 |
| A | UNSPECIFIED:ca | 5 | 6.639 | 0.1181 | 0.5889 | 6.032 | 7.678 | 0 |
| A | UNSPECIFIED:us-central | 3 | 5.448 | 0.2460 | 1.1363 | 4.392 | 7.119 | 0 |
| B | GCP:asia-northeast1 | 3 | 5.726 | 0.1337 | 0.6194 | 5.550 | 7.036 | 0 |
| B | GCP:uk | 3 | 3.011 | 0.3068 | 0.8368 | 2.904 | 4.913 | 0 |
| B | GCP:us-west | 3 | 5.495 | 0.0050 | 0.0221 | 5.463 | 5.516 | 1 |
| B | UNSPECIFIED:CANADA-2 | 3 | 6.483 | 0.0590 | 0.2922 | 6.425 | 7.126 | 0 |

## Matched provider:region (n>=3 on BOTH sides, uncapped)

| provider:region | A n | A med | B n | B med | delta (B-A) |
|---|---:|---:|---:|---:|---:|
| GCP:asia-northeast1 | 10 | 6.639 | 6 | 5.804 | -12.6% |
| GCP:us-west | 3 | 5.698 | 3 | 5.495 | -3.6% |

matched-restricted pooled: A n=13 med=6.279 mean=6.370 p10=5.548 worst=5.276
matched-restricted pooled: B n=9 med=5.521 mean=5.855 p10=5.428 worst=5.321
median delta (B-A): -12.1%

## Every operation >=250 ms, with provider:region

| arm | run | provider:region | offset | length | op ms | historical hit |
|---|---|---|---:|---:|---:|---|
| A | im-14.json | GCP:us-west | 6039797760 | 67108864 | 578.8 | [6039797760] |
| B | im-23.json | GCP:us-west | 6039797760 | 67108864 | 522.0 | [6039797760] |
| B | im-23.json | GCP:us-west | 4160749568 | 67108864 | 706.8 | [4160749568] |

# CHECK 2 — CPU time vs wall time around memcpy (instrumented baseline)

Baseline source path unchanged except an opt-in CPU-time read around the memcpy.
Per-thread CPU time (`CLOCK_THREAD_CPUTIME_ID`) with fallback to `getrusage`/
`/proc/self/stat`; a candidate clock is accepted only if it ADVANCES across real
CPU work (gVisor stubs `time.thread_time_ns`/`time.process_time_ns`, which read as
a permanent zero and must not be silently trusted).

counted runs: 15 · CPU clock used: **thread**

## Per-operation memcpy wall vs CPU

| metric | median | mean | p90 | p99 | min | max |
|---|---:|---:|---:|---:|---:|---:|
| wall ms | 39.799 | 46.613 | 72.337 | 119.353 | 7.939 | 411.124 |
| CPU ms | 40.000 | 43.533 | 70.000 | 110.000 | 0.000 | 250.000 |
| CPU fraction | 0.9449 | 0.9408 | 1.0945 | 1.2178 | 0.0000 | 1.5777 |

operations with CPU data: 1800/1800

## CPU fraction distribution

| bucket | count | share |
|---|---:|---:|
| [0.00, 0.25) | 8 | 0.4% |
| [0.25, 0.50) | 8 | 0.4% |
| [0.50, 0.75) | 61 | 3.4% |
| [0.75, 0.90) | 633 | 35.2% |
| [0.90, 1.01) | 510 | 28.3% |

## Healthy vs pathological operations

| class | n | median wall ms | median CPU ms | median CPU fraction |
|---|---:|---:|---:|---:|
| healthy (<250 ms) | 1798 | 39.766 | 40.000 | 0.9451 |
| pathological (>=250 ms) | 2 | 360.264 | 210.000 | 0.5788 |

## Aggregate CPU fraction of the whole source window (summed across readers)

| run | provider:region | wall ms | CPU ms (window) | aggregate CPU/wall |
|---|---|---:|---:|---:|
| im-01.json | UNSPECIFIED:ca | 1206.6 | 4240.0 | 3.5139 |
| im-03.json | UNSPECIFIED:ca | 1212.7 | 4300.0 | 3.5458 |
| im-04.json | GCP:uk | 2031.1 | 7100.0 | 3.4956 |
| im-05.json | UNSPECIFIED:CANADA-2 | 1266.0 | 4450.0 | 3.5150 |
| im-06.json | GCP:uk | 2048.9 | 5800.0 | 2.8307 |
| im-07.json | GCP:uk | 3028.8 | 10170.0 | 3.3578 |
| im-08.json | GCP:uk | 1525.8 | 5310.0 | 3.4802 |
| im-09.json | UNSPECIFIED:CANADA-2 | 1238.6 | 4340.0 | 3.5041 |
| im-12.json | GCP:asia-northeast1 | 1526.4 | 5540.0 | 3.6295 |
| im-13.json | UNSPECIFIED:CANADA-2 | 1217.5 | 4310.0 | 3.5399 |
| im-14.json | UNSPECIFIED:ca | 1230.2 | 4310.0 | 3.5036 |
| im-15.json | GCP:ap-northeast | 1526.8 | 5470.0 | 3.5827 |
| im-16.json | UNSPECIFIED:ca | 1106.7 | 3800.0 | 3.4337 |
| im-17.json | GCP:ap-northeast | 1462.6 | 5240.0 | 3.5828 |
| im-18.json | UNSPECIFIED:ca | 1141.3 | 3980.0 | 3.4873 |

aggregate CPU/wall: median 3.5041 · mean 3.4668 · min 2.8307 · max 3.6295

## Pathological runs — provider:region

| run | provider:region | worst op ms | CPU fraction of worst |
|---|---|---:|---:|
| im-06.json | GCP:uk | 413.8 | 0.6081 |

