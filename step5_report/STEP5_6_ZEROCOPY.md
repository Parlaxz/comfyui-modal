# Step 5/6 — zero-copy mmap direct-consume vs M0 memcpy

Persistent mapping, 4 processes, QD4, 64 MiB, 4 ms floor. `consume_mode != memcpy` means
**no destination buffer exists and no payload byte is copied** — the native consumer reads
the mapping directly. Counting rule: US only, singleton US regions excluded.

## Zero-copy proof

| consume mode | payload_copy_bytes | payload_copy_bytes_per_block | dest_allocated |
|---|---:|---:|---|
| M0 memcpy -> bytearray | 8044982048 | 67108864.0 | True |
| D0 st_touch_pages (page probe) | 0 | 0.0 | False |
| D1 st_touch_lines (cache-line probe) | 0 | 0.0 | False |
| D2 st_reduce_full (full-byte consumer) | 0 | 0.0 | False |

## Counted results

| mode | counted n | GB/s median | mean | p10 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 memcpy -> bytearray | 12 | 5.621 | 5.384 | 4.264 | 6.870 | 2.688 | 1432 | 1593 |
| D0 st_touch_pages (page probe) | 13 | 5.350 | 5.381 | 4.806 | 6.818 | 3.968 | 1504 | 1523 |
| D1 st_touch_lines (cache-line probe) | 14 | 5.935 | 5.718 | 4.683 | 7.811 | 4.377 | 1356 | 1435 |
| D2 st_reduce_full (full-byte consumer) | 11 | 4.686 | 4.503 | 3.740 | 5.450 | 3.235 | 1717 | 1825 |

## Operation distribution and tails

| mode | ops | median | p90 | p95 | p99 | worst | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| memcpy | 1440 | 42.65 | 66.21 | 83.12 | 234.83 | 1174.0 | 13 | 6 | 2 |
| d0 | 1560 | 49.15 | 63.70 | 70.17 | 107.54 | 645.1 | 2 | 1 | 0 |
| d1 | 1680 | 43.40 | 54.98 | 61.49 | 88.76 | 713.9 | 8 | 3 | 0 |
| d2 | 1320 | 54.95 | 74.17 | 85.51 | 116.26 | 673.2 | 3 | 2 | 0 |

## Effective concurrency and per-run spread

| mode | eff concurrency median | source wall median | ops/run |
|---|---:|---:|---:|
| memcpy | 3.9155 | 1432 | 120.0 |
| d0 | 3.9255 | 1504 | 120.0 |
| d1 | 3.9040 | 1356 | 120.0 |
| d2 | 3.9140 | 1717 | 120.0 |

## The key comparison: M0 memcpy vs D2 direct full-byte consumer

- M0 memcpy: median 5.621 GB/s, wall median 1432 ms
- D2 direct: median 4.686 GB/s, wall median 1717 ms
- **D2 vs M0: -16.6% median GB/s, +19.9% wall median**

## Provider:region per run (counted)

| mode | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---:|---:|---:|
| memcpy | im-01.json | GCP:us-west | 5.875 | 1369 | 96.5 |
| memcpy | im-09.json | GCP:us-west | 5.776 | 1393 | 86.0 |
| memcpy | im-17.json | GCP:us-east4 | 6.409 | 1255 | 71.1 |
| memcpy | im-24.json | GCP:us-west | 6.797 | 1184 | 76.3 |
| memcpy | im-25.json | GCP:us-east | 4.510 | 1784 | 1002.8 |
| memcpy | im-33.json | GCP:us-west | 2.688 | 2993 | 311.7 |
| memcpy | im-40.json | GCP:us-west1 | 6.870 | 1171 | 83.1 |
| memcpy | im-41.json | GCP:us-east | 5.132 | 1568 | 784.5 |
| memcpy | im-56.json | UNSPECIFIED:us-central | 4.236 | 1899 | 129.3 |
| memcpy | im-65.json | GCP:us-east | 5.465 | 1472 | 91.9 |
| memcpy | im-73.json | GCP:us-west | 6.237 | 1290 | 79.7 |
| memcpy | im-80.json | GCP:us-east | 4.619 | 1742 | 1174.0 |
| d0 | im-02.json | UNSPECIFIED:us-central | 3.968 | 2028 | 143.6 |
| d0 | im-07.json | GCP:us-west | 5.804 | 1386 | 150.1 |
| d0 | im-10.json | GCP:us-west | 5.648 | 1424 | 86.3 |
| d0 | im-18.json | GCP:us-east4 | 6.623 | 1215 | 73.5 |
| d0 | im-23.json | GCP:us-west | 4.947 | 1626 | 105.0 |
| d0 | im-31.json | GCP:us-east | 5.350 | 1504 | 94.0 |
| d0 | im-39.json | GCP:us-west | 5.651 | 1424 | 90.7 |
| d0 | im-47.json | GCP:us-east | 5.075 | 1585 | 645.1 |
| d0 | im-55.json | GCP:us-west | 4.791 | 1679 | 96.3 |
| d0 | im-58.json | AZURE:us-central | 4.868 | 1652 | 105.7 |
| d0 | im-63.json | GCP:us-west1 | 6.818 | 1180 | 106.9 |
| d0 | im-66.json | UNSPECIFIED:us-central | 5.394 | 1491 | 83.7 |
| d0 | im-79.json | UNSPECIFIED:us-central | 5.022 | 1602 | 112.4 |
| d1 | im-03.json | GCP:us-west | 5.893 | 1365 | 87.7 |
| d1 | im-06.json | GCP:us-east | 4.377 | 1838 | 713.9 |
| d1 | im-11.json | GCP:us-west | 6.305 | 1276 | 92.5 |
| d1 | im-14.json | GCP:us-west | 6.062 | 1327 | 86.3 |
| d1 | im-19.json | GCP:us-west | 5.303 | 1517 | 79.7 |
| d1 | im-27.json | GCP:us-east | 6.021 | 1336 | 85.1 |
| d1 | im-35.json | GCP:us-west | 5.195 | 1549 | 348.9 |
| d1 | im-43.json | UNSPECIFIED:us-central | 5.976 | 1346 | 92.1 |
| d1 | im-46.json | GCP:us-east | 6.039 | 1332 | 63.3 |
| d1 | im-54.json | GCP:us-west | 7.811 | 1030 | 60.9 |
| d1 | im-59.json | UNSPECIFIED:us-central | 5.540 | 1452 | 89.7 |
| d1 | im-67.json | UNSPECIFIED:us-central | 4.904 | 1640 | 342.1 |
| d1 | im-70.json | UNSPECIFIED:us-central | 4.588 | 1753 | 114.5 |
| d1 | im-78.json | GCP:us-east | 6.039 | 1332 | 82.0 |
| d2 | im-12.json | GCP:us-west | 5.006 | 1607 | 88.9 |
| d2 | im-13.json | GCP:us-west | 4.869 | 1652 | 96.5 |
| d2 | im-21.json | GCP:us-east4 | 4.686 | 1717 | 102.2 |
| d2 | im-29.json | UNSPECIFIED:us-central | 4.104 | 1960 | 116.9 |
| d2 | im-36.json | UNSPECIFIED:us-central | 5.003 | 1608 | 96.0 |
| d2 | im-44.json | UNSPECIFIED:us-central | 4.095 | 1965 | 117.3 |
| d2 | im-53.json | AWS:us-west | 3.235 | 2487 | 163.5 |
| d2 | im-61.json | GCP:us-west1 | 4.944 | 1627 | 91.6 |
| d2 | im-68.json | GCP:us-west | 5.450 | 1476 | 75.2 |
| d2 | im-76.json | GCP:us-east | 3.740 | 2151 | 673.2 |
| d2 | im-77.json | UNSPECIFIED:us-central | 4.401 | 1828 | 129.7 |

