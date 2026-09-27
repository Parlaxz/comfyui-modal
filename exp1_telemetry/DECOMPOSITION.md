# Experiment 1a — manager bubble decomposition from existing telemetry (ZERO new runs)

Method: per-reader duty cycle = sum(preadv_ms) / (last_exit - first_enter).
The non-busy remainder is the per-reader overhead; divided by inter-read gaps it gives
ms of manager bubble per block. No assumptions about gate behaviour needed.

## allocator QD4 @64 MiB (interleaved/sticky mix) (n=30 runs)

| metric | median | p90 | p99 | max | n |
|---|---:|---:|---:|---:|---:|
| reader duty cycle | 0.9682 | 0.9805 | 0.9930 | 0.9953 | 120 |
| idle ms per inter-read gap | 1.658 | 2.212 | 2.739 | 4.325 | 120 |
| prev exit -> next preadv enter (ms) | 1.429 | 3.234 | 6.701 | 112.313 | 3494 |
| prev exit -> next gate CLAIM (ms) | 1.416 | 3.222 | 6.695 | 112.299 | 3494 |
| gate claim -> preadv enter (ms) | 0.0127 | 0.0178 | 0.0364 | 0.1436 | 3494 |

## allocator QD8 @64 MiB (n=30 runs)

| metric | median | p90 | p99 | max | n |
|---|---:|---:|---:|---:|---:|
| reader duty cycle | 0.9802 | 0.9884 | 0.9906 | 0.9913 | 240 |
| idle ms per inter-read gap | 2.212 | 4.130 | 6.302 | 7.442 | 240 |
| prev exit -> next preadv enter (ms) | 1.554 | 5.202 | 17.001 | 58.349 | 3366 |
| prev exit -> next gate CLAIM (ms) | 1.540 | 5.196 | 16.985 | 58.328 | 3366 |
| gate claim -> preadv enter (ms) | 0.0131 | 0.0192 | 0.0485 | 1.9253 | 3366 |

## allocator QD4 @128 MiB (n=30 runs)

| metric | median | p90 | p99 | max | n |
|---|---:|---:|---:|---:|---:|
| reader duty cycle | 0.9838 | 0.9886 | 0.9931 | 0.9946 | 120 |
| idle ms per inter-read gap | 1.693 | 2.548 | 3.073 | 3.418 | 120 |
| prev exit -> next preadv enter (ms) | 1.486 | 3.479 | 7.208 | 14.424 | 1682 |
| prev exit -> next gate CLAIM (ms) | 1.471 | 3.462 | 7.202 | 14.403 | 1682 |
| gate claim -> preadv enter (ms) | 0.0133 | 0.0186 | 0.0392 | 0.3612 | 1682 |

## static QD4 @64 MiB baseline (readers loop internally, no coordinator)

(n=220 runs)

| metric | median | p90 | p99 | max | n |
|---|---:|---:|---:|---:|---:|
| reader duty cycle | 3.8588 | 3.9052 | 3.9319 | 3.9462 | 220 |
| idle ms per inter-read gap | -34.033 | -29.787 | -26.146 | -25.503 | 220 |
| prev exit -> next preadv enter (ms) | 0.069 | 0.240 | 9.426 | 3783.799 | 355 |
| prev exit -> next gate CLAIM (ms) | 0.055 | 0.230 | 9.415 | 3783.781 | 355 |
| gate claim -> preadv enter (ms) | 0.0137 | 0.0195 | 0.0366 | 22.1566 | 26180 |

## Headline

| cohort | n | duty cycle (med) | idle ms/gap (med) | exit->enter gap (med) |
|---|---:|---:|---:|---:|
| allocator QD4 @64 MiB (interleaved/sticky mix) | 30 | 0.9682 | 1.658 | 1.429 |
| allocator QD8 @64 MiB | 30 | 0.9802 | 2.212 | 1.554 |
| allocator QD4 @128 MiB | 30 | 0.9838 | 1.693 | 1.486 |
| static QD4 @64 MiB | 220 | 3.8588 | -34.033 | 0.069 |

