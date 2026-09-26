# Task 2 — source-wall accounting (self-service QD4, 64 MiB, 4 ms gate)

n = **12** valid non-Odin healthy runs. Every run: exact coverage, amp 1.0, zero stale/rescue attempts.

## Occupancy — time at each active-physical-preadv level

| active physical preadvs | wall ms (mean/run) | % of source wall |
|---:|---:|---:|
| 0 | 0.0 | 0.00% |
| 1 | 10.6 | 0.65% |
| 2 | 14.6 | 0.89% |
| 3 | 107.8 | 6.62% |
| 4 | 1496.0 | 91.84% |

Useful concurrency is identical here: these are healthy runs, so there are no stale or
rescue attempts to separate out (amplification 1.0, `stale_duplicates` 0 in all runs).

## Identity validation

`sum(preadv durations) == integral(active concurrency over wall)`

| run | sum preadv ms | integral(conc) ms | abs error ms |
|---|---:|---:|---:|
| im-01.json | 5267.0 | 5267.0 | 0.000000 |
| im-03.json | 5819.0 | 5819.0 | 0.000000 |
| im-04.json | 4962.9 | 4962.9 | 0.000000 |
| im-05.json | 11912.8 | 11912.8 | 0.000000 |
| im-06.json | 6945.1 | 6945.1 | 0.000000 |
| im-07.json | 5280.1 | 5280.1 | 0.000000 |
| im-08.json | 5216.2 | 5216.2 | 0.000000 |
| im-09.json | 10442.8 | 10442.8 | 0.000000 |
| im-10.json | 5923.1 | 5923.1 | 0.000000 |
| im-11.json | 3848.3 | 3848.3 | 0.000000 |
| im-12.json | 5254.7 | 5254.7 | 0.000000 |
| im-13.json | 5294.4 | 5294.4 | 0.000000 |

- max absolute error across all runs: **0.000000 ms** (numerical only; the identity holds by construction and the sweep reproduces it)

## Source-wall decomposition (mean per run)

| quantity | ms |
|---|---:|
| source wall | 1629.0 |
| sum preadv service | 6347.2 |
| theoretical lower bound = sum preadv / 4 | 1586.8 |
| observed minus theoretical lower bound (residual) | 42.2 |

## Residual attribution (mean per run)

| residual owner | ms | % residual |
|---|---:|---:|
| worker turnaround (ready->claim_begin) | 1.77 | 4.2% |
| claim/lock | 0.43 | 1.0% |
| pre-gate dispatch (claim_end->gate) | 0.17 | 0.4% |
| 4 ms pacing wait | 27.47 | 65.1% |
| gate->preadv enter | 0.24 | 0.6% |
| post-read bookkeeping (exit->pub_begin) | 0.02 | 0.0% |
| publish/lock | 0.63 | 1.5% |
| loop back (pub_end->ready_again) | 0.44 | 1.0% |
| **sum of attributed** | **31.17** | **73.9%** |
| unattributed | 11.02 | 26.1% |

Reconciliation: attributed 31.17 ms vs residual 42.20 ms (difference 11.0241 ms).

## Structural metrics (mean per run)

| metric | ms |
|---|---:|
| first read enter -> first time physical QD4 achieved (ramp) | 13.30 |
| steady-state duration | 1582.8 |
| time with physical QD < 4 (ramp + drain + any gap) | 132.99 |
| final drain (last QD4 -> last exit) | 32.90 |

Note: the QD<4 row is the complement of the QD4 occupancy row, so it is the *union* of ramp,
drain and any mid-run gap - not an isolated defect. Ramp and drain are the dominant parts:
ramp 13.30 ms + drain 32.90 ms = 46.19 ms of the 132.99 ms.

## Per-read statistics and effective concurrency

| run | preadv median | preadv p95 | effective concurrency | wall ms |
|---|---:|---:|---:|---:|
| im-01.json | 42.60 | 56.67 | 3.8828 | 1356.5 |
| im-03.json | 43.59 | 59.53 | 3.8717 | 1502.9 |
| im-04.json | 39.25 | 52.83 | 3.8596 | 1285.9 |
| im-05.json | 68.97 | 278.36 | 3.9395 | 3023.9 |
| im-06.json | 45.12 | 66.65 | 3.8959 | 1782.6 |
| im-07.json | 43.16 | 53.86 | 3.8868 | 1358.5 |
| im-08.json | 42.32 | 53.25 | 3.9039 | 1336.2 |
| im-09.json | 88.89 | 139.55 | 3.9356 | 2653.4 |
| im-10.json | 48.96 | 61.89 | 3.9008 | 1518.4 |
| im-11.json | 31.76 | 35.48 | 3.8424 | 1001.5 |
| im-12.json | 41.03 | 59.97 | 3.8672 | 1358.8 |
| im-13.json | 43.33 | 57.09 | 3.8666 | 1369.3 |

- mean effective concurrency = sum preadv / source wall = **3.8877**
- mean preadv median 48.25 ms, mean p95 81.26 ms

## Does 120 x ~50 ms / effective concurrency explain the wall?

- sum preadv service = 6347.2 ms; divided by effective concurrency 3.8877 gives 1632.6 ms vs observed 1629.0 ms.
- equivalently, sum/4 = 1586.8 ms is the perfect-packing bound and the
  observed wall exceeds it by 42.2 ms (2.6% of wall).

