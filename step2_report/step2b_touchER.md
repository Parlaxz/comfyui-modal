# Step 2 — manual toucher discriminator (T0 / T1 / T2)

Toucher = `st_touch_pages` from `/opt/source_touch.so`: native, one volatile load per
guest page, no Python per-page loop, no payload copy, never calls preadv/read. One toucher
thread per reader process walks ahead in that reader's own lane. Consumer is the M0 C
memcpy into a preallocated private bytearray. Persistent mapping, QD4, 64 MiB, 4 ms floor.

Runs collected: 21 valid non-Odin; US 17; **counted 14**
(US only, singleton US regions excluded).

## Arm summary (counted)

| arm | counted n | GB/s median | mean | p10 | best | worst | wall median | consumer wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| T0 no toucher | 2 | 5.295 | 5.295 | 5.166 | 5.457 | 5.134 | 1521 | 1521 |
| T1 1 block ahead | 5 | 3.568 | 3.549 | 3.174 | 4.177 | 3.078 | 2255 | 2290 |
| T2 2 blocks ahead | 7 | 3.717 | 3.512 | 2.687 | 4.512 | 2.115 | 2165 | 2412 |

## Consumer-operation tails (counted)

| arm | ops | median | p90 | p95 | p99 | worst | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| T0 | 240 | 48.96 | 59.27 | 66.68 | 87.18 | 90.9 | 0 | 0 | 0 |
| T1 | 600 | 69.46 | 113.25 | 131.66 | 150.73 | 659.9 | 2 | 1 | 0 |
| T2 | 840 | 62.12 | 112.91 | 144.13 | 492.96 | 1041.1 | 26 | 9 | 1 |

## Toucher health (T1/T2 only)

| arm | touch events | touch median ms | touch p95 | touch max | touch >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| T1 | 599 | 70.61 | 140.52 | 660.9 | 2 | 1 | 0 |
| T2 | 840 | 59.59 | 147.43 | 1045.5 | 28 | 8 | 1 |

## Per-block touch/consumer relationship (T1/T2)

| arm | blocks paired | READY_AHEAD | CONSUMER_CAUGHT_TOUCHER | consumer ms when READY_AHEAD (median) | consumer ms when CAUGHT (median) |
|---|---:|---:|---:|---:|---:|
| T1 | 599 | 0 | 599 | - | 69.49 |
| T2 | 840 | 0 | 840 | - | 62.12 |

## Does a completed touch make the subsequent memcpy cheap?

| condition | n | consumer memcpy median ms | p90 ms |
|---|---:|---:|---:|
| T0 (no toucher at all) | 240 | 48.96 | 59.27 |
| T1, touch already finished | 0 | - | - |
| T2, touch already finished | 0 | - | - |

## Gate decision

- T1 vs T0: median GB/s 3.568 vs 5.295 (-32.6%), wall median 2255 vs 1521 ms (+48.3%)
- T2 vs T0: median GB/s 3.717 vs 5.295 (-29.8%), wall median 2165 vs 1521 ms (+42.3%)

