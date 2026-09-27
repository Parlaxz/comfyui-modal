# Task 5 — is 4 ms pacing still too aggressive? (self-service QD4 / 64 MiB)

Control is the **frozen** 4.0 ms self-service cohort (`exp1_control_frozen/`, exactly the 42
files listed in `task5_report/CONTROL_MANIFEST.txt`; all `min_launch_gap_ms=4.0`,
`selfservice_allocator`, 64 MiB, QD4). It was not re-run and the older static controls were not used.

Treatments are fresh runs of the identical engine and geometry, changing only the global
minimum physical-start spacing, interleaved by the predetermined schedule
`[5,6,6,5,5,6]` (slots 1..). Odin excluded and retained separately.

- gap 4.0 ms: **42** valid non-Odin runs
- gap 5.0 ms: **42** valid non-Odin runs
- gap 6.0 ms: **42** valid non-Odin runs

## Pooled physical `preadv`

| gap | reads | median | mean | p90 | p95 | p99 | p99.5 | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.0 | 5040 | 43.87 | 50.70 | 73.58 | 95.60 | 134.70 | 149.66 | 220.5 |
| 5.0 | 5048 | 44.53 | 52.87 | 71.69 | 86.52 | 173.19 | 209.47 | 2052.0 |
| 6.0 | 5056 | 43.93 | 57.51 | 69.25 | 85.91 | 128.72 | 387.43 | 6134.9 |

## Tail counts (pooled reads)

| gap | >=100ms | >=150ms | >=250ms | >=500ms | >=1000ms | >=2000ms |
|---|---:|---:|---:|---:|---:|---:|
| 4.0 | 218 | 25 | 0 | 0 | 0 | 0 |
| 5.0 | 158 | 65 | 13 | 10 | 5 | 1 |
| 6.0 | 201 | 38 | 31 | 20 | 13 | 6 |

## Normalized tail incidence (per 1000 reads)

| gap | >=250 per 1000 | >=500 per 1000 | >=1s per 1000 |
|---|---:|---:|---:|
| 4.0 | 0.00 | 0.00 | 0.00 |
| 5.0 | 2.58 | 1.98 | 0.99 |
| 6.0 | 6.13 | 3.96 | 2.57 |

## Run-level incidence (the important one)

| gap | runs with >=250 | runs with >=500 | runs with >=1s | runs with >=2s |
|---|---:|---:|---:|---:|
| 4.0 | 0/42 | 0/42 | 0/42 | 0/42 |
| 5.0 | 3/42 | 2/42 | 2/42 | 1/42 |
| 6.0 | 3/42 | 2/42 | 2/42 | 1/42 |

## Normal performance cost

| gap | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4.0 | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 1566 |
| 5.0 | 42 | 5.476 | 5.366 | 3.537 | 7.090 | 7.620 | 2.336 | 1469 | 1641 |
| 6.0 | 42 | 5.548 | 5.292 | 3.526 | 6.788 | 7.282 | 0.774 | 1450 | 1797 |

## Concurrency / pacing detail

| gap | effective concurrency median | preadv median | source-wall median | pacing-wait/run median ms |
|---|---:|---:|---:|---:|
| 4.0 | 3.8761 | 43.75 | 1383 | 103.8 |
| 5.0 | 3.8673 | 46.14 | 1469 | 138.3 |
| 6.0 | 3.8195 | 43.99 | 1450 | 189.5 |

## Relative changes

| comparison | median GB/s | mean GB/s | wall median | >=250 incidence | >=500 incidence | >=1s incidence |
|---|---:|---:|---:|---:|---:|---:|
| 5.0 vs 4.0 | -5.9% | -3.0% | +6.3% | n/a | n/a | n/a |
| 6.0 vs 4.0 | -4.6% | -4.3% | +4.9% | n/a | n/a | n/a |
| 6.0 vs 5.0 | +1.3% | -1.4% | -1.3% | +0.0% | +0.0% | +0.0% |

(incidence columns are relative change in the fraction of runs affected; a negative value
means fewer affected runs at the larger spacing)

## Provider-stratified (arms with >=2 runs)

| provider | gap | n runs | median GB/s | preadv p99 | >=250 | >=500 | >=1s |
|---|---:|---:|---:|---:|---:|---:|---:|
| UNSPECIFIED | 4.0 | 21 | 5.795 | 133.0 | 0 | 0 | 0 |
| OCI | 4.0 | 12 | 5.442 | 138.0 | 0 | 0 | 0 |
| GCP | 4.0 | 9 | 5.999 | 120.3 | 0 | 0 | 0 |
| UNSPECIFIED | 5.0 | 29 | 5.448 | 184.9 | 8 | 6 | 3 |
| GCP | 5.0 | 5 | 4.895 | 204.9 | 5 | 4 | 2 |
| OCI | 5.0 | 5 | 5.566 | 71.2 | 0 | 0 | 0 |
| AZURE | 5.0 | 3 | 5.633 | 67.1 | 0 | 0 | 0 |
| UNSPECIFIED | 6.0 | 28 | 5.294 | 168.0 | 30 | 20 | 13 |
| GCP | 6.0 | 9 | 5.860 | 67.7 | 1 | 0 | 0 |
| OCI | 6.0 | 5 | 5.410 | 77.0 | 0 | 0 | 0 |

## Pathological-run region concentration

| gap | regions of runs whose worst read >=500 ms |
|---|---|
| 4.0 | none |
| 5.0 | ca (worst 2052 ms), asia-south2 (worst 1213 ms) |
| 6.0 | CANADA-2 (worst 1484 ms), us-south (worst 6135 ms) |

