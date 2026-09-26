# Experiment 3 — mmap / page-fault alternate read paths (QD4 / 64 MiB)

Audited prior art first: `.slim/worktrees/rx3/tools/benchmark_source_io_e14.py` sliced the
mapping (`mapping[pos:pos+count]`), materialising a Python bytes object per block - the
naive path. `unet_qd_probe.py` did a numpy strided first-touch; `unet_salvage_probe.py`
already used a page-aligned exact window; `c5_vae_policy_runner.py` already had
`madvise_willneed` / `madvise_populate_read` arms. These arms therefore copy through the
buffer protocol with a C-level `memcpy` into a preallocated destination - never Python slices.

Control: the frozen Experiment-1 self-service preadv cohort (n=42).

## Main comparison

| method | n | GB/s median | mean | p10 | p90 | best | worst | wall median | worst block |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv control (Exp-1, 64 MiB) | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 220.5 |
| M0 persistent mmap + memcpy | 12 | 6.069 | 6.183 | 5.431 | 7.174 | 7.218 | 4.627 | 1328 | 443.4 |
| M1 + MADV_WILLNEED | 13 | 5.954 | 5.949 | 4.504 | 7.425 | 7.956 | 3.970 | 1351 | 813.0 |
| M2 exact-window MAP_POPULATE | 13 | 5.946 | 5.668 | 4.625 | 7.353 | 7.546 | 0.126 | 1353 | 6387.7 |

## Block latency and tails

| method | median | p95 | p99 | max | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| preadv control (Exp-1, 64 MiB) | 43.87 | 95.60 | 134.70 | 220.5 | 0 | 0 | 0 |
| M0 persistent mmap + memcpy | 41.70 | 52.97 | 90.74 | 443.4 | 3 | 0 | 0 |
| M1 + MADV_WILLNEED | 42.71 | 73.52 | 94.78 | 813.0 | 2 | 2 | 0 |
| M2 exact-window MAP_POPULATE | 41.11 | 152.03 | 4293.49 | 6387.7 | 72 | 69 | 67 |

## mmap timing split (medians over runs; per-block medians in ms)

| method | advice | map/populate | copy | unmap |
|---|---:|---:|---:|---:|
| M0 persistent mmap + memcpy | 0.000 | 0.000 | 43.386 | 0.000 |
| M1 + MADV_WILLNEED | 0.038 | 0.000 | 41.649 | 0.000 |
| M2 exact-window MAP_POPULATE | 0.000 | 33.190 | 7.208 | 2.041 |

## Correctness / invariants

| method | n | exact coverage | bytes match | no overlap | maxQD=4 | minGap>=4ms | amp=1.0 | errors |
|---|---:|---|---|---|---|---|---|---:|
| preadv control (Exp-1, 64 MiB) | 42 | 42/42 | 42/42 | 42/42 | 42/42 | 42/42 | 42/42 | 0 |
| M0 persistent mmap + memcpy | 12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 12/12 | 0 |
| M1 + MADV_WILLNEED | 13 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 | 0 |
| M2 exact-window MAP_POPULATE | 13 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 | 13/13 | 0 |

## Fault deltas — NOT TRUSTWORTHY on this platform

Every reader reported an exact `minflt`/`majflt` delta of 0 across 120 x 64 MiB paged
reads. That is not plausible for demand paging, and the cause is the runtime: this is
gVisor, whose `/proc/self/stat` does not report real page-fault counters. Fault deltas are
therefore reported as unavailable rather than as zeros.

## Provider / region per run

| method | run | provider/region | GB/s | wall ms | block median | worst block | exact |
|---|---|---|---:|---:|---:|---:|---|
| M0 persistent mmap + memcpy | im-01.json | UNSPECIFIED:eu-north | 6.839 | 1176 | 37.65 | 69.8 | Y |
| M0 persistent mmap + memcpy | im-04.json | AZURE:centralus | 5.811 | 1384 | 43.56 | 97.5 | Y |
| M0 persistent mmap + memcpy | im-05.json | GCP:us-west4 | 5.680 | 1416 | 47.11 | 84.7 | Y |
| M0 persistent mmap + memcpy | im-06.json | GCP:us-east | 4.627 | 1739 | 47.81 | 443.4 | Y |
| M0 persistent mmap + memcpy | im-07.json | OCI:us-chicago-1 | 7.027 | 1145 | 36.27 | 70.5 | Y |
| M0 persistent mmap + memcpy | im-08.json | GCP:us-east | 6.327 | 1272 | 43.23 | 95.8 | Y |
| M0 persistent mmap + memcpy | im-09.json | UNSPECIFIED:eu-north | 7.218 | 1115 | 36.10 | 73.7 | Y |
| M0 persistent mmap + memcpy | im-10.json | OCI:us-central | 5.403 | 1489 | 48.31 | 90.9 | Y |
| M0 persistent mmap + memcpy | im-11.json | GCP:us-west1 | 6.604 | 1218 | 38.84 | 85.9 | Y |
| M0 persistent mmap + memcpy | im-12.json | UNSPECIFIED:us-central | 7.190 | 1119 | 36.50 | 64.7 | Y |
| M0 persistent mmap + memcpy | im-13.json | GCP:us-west1 | 5.772 | 1394 | 45.26 | 82.3 | Y |
| M0 persistent mmap + memcpy | im-14.json | GCP:us-west1 | 5.698 | 1412 | 45.36 | 97.6 | Y |
| M1 + MADV_WILLNEED | im-01.json | GCP:us-west | 4.999 | 1609 | 41.73 | 813.0 | Y |
| M1 + MADV_WILLNEED | im-02.json | GCP:ap-northeast | 4.385 | 1835 | 55.36 | 166.3 | Y |
| M1 + MADV_WILLNEED | im-03.json | GCP:asia-northeast3 | 5.404 | 1489 | 48.02 | 107.2 | Y |
| M1 + MADV_WILLNEED | im-04.json | UNSPECIFIED:us-central | 3.970 | 2026 | 64.78 | 104.8 | Y |
| M1 + MADV_WILLNEED | im-05.json | GCP:us-west | 7.042 | 1142 | 35.55 | 81.9 | Y |
| M1 + MADV_WILLNEED | im-06.json | UNSPECIFIED:eu-north | 7.115 | 1131 | 36.19 | 83.2 | Y |
| M1 + MADV_WILLNEED | im-07.json | UNSPECIFIED:us-central | 4.981 | 1615 | 50.19 | 84.0 | Y |
| M1 + MADV_WILLNEED | im-08.json | GCP:us-west | 6.270 | 1283 | 40.43 | 82.5 | Y |
| M1 + MADV_WILLNEED | im-09.json | GCP:us-west | 7.956 | 1011 | 32.43 | 72.6 | Y |
| M1 + MADV_WILLNEED | im-10.json | OCI:us-central | 6.681 | 1204 | 38.04 | 73.5 | Y |
| M1 + MADV_WILLNEED | im-11.json | GCP:us-east | 5.954 | 1351 | 43.48 | 86.7 | Y |
| M1 + MADV_WILLNEED | im-12.json | UNSPECIFIED:eu-north | 7.502 | 1072 | 33.11 | 78.5 | Y |
| M1 + MADV_WILLNEED | im-13.json | UNSPECIFIED:us-central | 5.074 | 1585 | 50.46 | 107.0 | Y |
| M2 exact-window MAP_POPULATE | im-01.json | UNSPECIFIED:eu-north | 6.941 | 1159 | 36.78 | 84.3 | Y |
| M2 exact-window MAP_POPULATE | im-02.json | UNSPECIFIED:eu-north | 7.456 | 1079 | 35.03 | 81.8 | Y |
| M2 exact-window MAP_POPULATE | im-03.json | UNSPECIFIED:us-west | 5.946 | 1353 | 43.93 | 83.7 | Y |
| M2 exact-window MAP_POPULATE | im-04.json | UNSPECIFIED:us-central | 4.731 | 1701 | 50.87 | 92.9 | Y |
| M2 exact-window MAP_POPULATE | im-05.json | UNSPECIFIED:eu-north | 6.731 | 1195 | 38.44 | 70.4 | Y |
| M2 exact-window MAP_POPULATE | im-06.json | UNSPECIFIED:eu-north | 0.126 | 64068 | 2165.57 | 6387.7 | Y |
| M2 exact-window MAP_POPULATE | im-07.json | GCP:us-west | 5.945 | 1353 | 44.53 | 99.4 | Y |
| M2 exact-window MAP_POPULATE | im-08.json | OCI:us-central | 7.546 | 1066 | 33.95 | 61.2 | Y |
| M2 exact-window MAP_POPULATE | im-09.json | GCP:us-east | 6.026 | 1335 | 42.45 | 90.6 | Y |
| M2 exact-window MAP_POPULATE | im-10.json | GCP:us-east4 | 5.471 | 1471 | 47.42 | 81.9 | Y |
| M2 exact-window MAP_POPULATE | im-11.json | UNSPECIFIED:us-central | 4.599 | 1749 | 54.51 | 93.1 | Y |
| M2 exact-window MAP_POPULATE | im-12.json | GCP:us-east4 | 6.795 | 1184 | 35.45 | 74.1 | Y |
| M2 exact-window MAP_POPULATE | im-13.json | GCP:us-west | 5.366 | 1499 | 36.02 | 733.1 | Y |

## Reading

- M0/M1 pay the page-fault cost inside `memcpy` (copy median ~38-45 ms). M2 pre-populates
  in `mmap`, so its copy is far cheaper (~6 ms) but `map/populate` costs ~29 ms; the sum is
  comparable, so M2 mainly *relocates* the cost rather than removing it.
- All three are in the same throughput band as the preadv control at the median, but every
  mmap arm shows a worse worst-case than the control. M2 in particular has severe outliers.
- This is a characterization result only; nothing here is integrated into production.

