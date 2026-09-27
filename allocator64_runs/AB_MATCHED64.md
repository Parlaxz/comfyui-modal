# Scheduler-only A/B — greedy allocator vs static, matched 64 MiB

- static control: **30** frozen runs (reused unchanged from the prior A/B)
- allocator QD4 @64 MiB: **30** fresh valid non-Odin
- allocator QD8 @64 MiB: **30** fresh valid non-Odin (20 requested, 30 collected)

Geometry is matched at 64 MiB for all three arms, so this isolates the scheduler.

## Main A/B

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 30 | 6.015 | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | 1337 | 1408 |
| allocator QD4 @64 | 30 | 5.310 | 4.999 | 3.343 | 6.071 | 6.494 | 1.197 | 1515 | 1884 |
| allocator QD8 @64 | 30 | 4.865 | 5.187 | 4.516 | 6.133 | 7.088 | 4.242 | 1654 | 1579 |

- allocator QD4 @64: median delta vs static **-0.706 GB/s (-11.7%)**
- allocator QD8 @64: median delta vs static **-1.150 GB/s (-19.1%)**

## Read latency

| arm | preadv median | p95 | p99 | worst | >=250ms | >=500ms | >=1000ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| allocator QD4 @64 | 46.52 | 56.42 | 63.91 | 5233.2 | 20 | 2 | 2 |
| allocator QD8 @64 | 104.24 | 127.07 | 131.48 | 291.9 | 4 | 0 | 0 |

## Treatment scheduler summary

| metric | allocator QD4 @64 | allocator QD8 @64 |
|---|---:|---:|
| rescue-eligible blocks | 15 | 6 |
| rescue launches | 15 | 6 |
| rescue wins | 7 | 2 |
| ms saved per win (median/max) | 0.27 / 0.89 | 0.11 / 0.12 |
| physical amplification (median/max) | 1.0000 / 1.1000 | 1.0000 / 1.0500 |
| max physical QD observed | 4 | 8 |
| min observed start spacing ms | 4.0019 | 4.0157 |
| total idle-no-work ms | 3609.1 | 4842.4 |
| stale duplicates | 14 | 6 |

Blocks completed per reader (per-run vectors):

- allocator QD4 @64: [30, 30, 30, 30] x18; [31, 30, 30, 29] x3; [30, 31, 30, 29] x2; [31, 32, 27, 30] x1; [32, 33, 27, 28] x1; [30, 31, 29, 30] x1
- allocator QD8 @64: [15, 15, 15, 15, 15, 15, 15, 15] x13; [15, 16, 15, 14, 15, 15, 15, 15] x2; [16, 15, 15, 15, 14, 15, 15, 15] x2; [15, 15, 15, 15, 16, 15, 14, 15] x1; [15, 14, 15, 15, 15, 15, 16, 15] x1; [16, 15, 15, 14, 15, 15, 15, 15] x1

## Within-provider A/B medians (GB/s)

| provider | static n | static med | q4 n | q4 med | q8 n | q8 med |
|---|---:|---:|---:|---:|---:|---:|
| azure | 0 | - | 2 | 5.285 | 1 | 4.280 |
| gcp | 23 | 6.058 | 17 | 5.543 | 25 | 4.860 |
| oci | 5 | 5.293 | 2 | 5.040 | 1 | 5.936 |
| unspecified | 2 | 6.850 | 9 | 4.466 | 3 | 6.302 |

## allocator QD4 @64 — one row per run

| run | provider/region | GB/s | wall ms | worst preadv ms | rescues | wins | reader block counts |
|---|---|---:|---:|---:|---:|---:|---|
| im-39.json | unspecified:eu-north | 6.494 | 1239 | 43.6 | 0 | 0 | [30, 30, 30, 30] |
| im-27.json | gcp:us-west | 6.434 | 1250 | 49.5 | 0 | 0 | [30, 30, 30, 30] |
| im-21.json | gcp:us-west | 6.123 | 1314 | 55.6 | 0 | 0 | [30, 30, 30, 30] |
| im-29.json | gcp:us-west | 6.065 | 1326 | 55.4 | 0 | 0 | [30, 30, 30, 30] |
| im-43.json | gcp:us-west | 6.002 | 1340 | 54.0 | 0 | 0 | [30, 31, 30, 29] |
| im-13.json | unspecified:london | 5.827 | 1381 | 55.1 | 0 | 0 | [31, 30, 30, 29] |
| im-16.json | gcp:us-west | 5.806 | 1386 | 55.4 | 0 | 0 | [30, 30, 30, 30] |
| im-18.json | gcp:us-west | 5.754 | 1398 | 55.9 | 0 | 0 | [30, 30, 30, 30] |
| im-45.json | gcp:us-east | 5.615 | 1433 | 57.7 | 0 | 0 | [29, 31, 30, 30] |
| im-22.json | gcp:ap-south | 5.605 | 1435 | 64.0 | 0 | 0 | [31, 30, 30, 29] |
| im-40.json | gcp:us-west | 5.543 | 1451 | 83.7 | 0 | 0 | [30, 30, 29, 31] |
| im-42.json | gcp:us-west | 5.483 | 1467 | 60.7 | 0 | 0 | [30, 30, 30, 30] |
| im-02.json | gcp:us-west1 | 5.476 | 1469 | 65.0 | 0 | 0 | [30, 30, 30, 30] |
| im-38.json | unspecified:eu-north | 5.407 | 1488 | 67.6 | 0 | 0 | [30, 31, 30, 29] |
| im-08.json | oci:us-chicago-1 | 5.333 | 1509 | 60.4 | 0 | 0 | [30, 30, 30, 30] |
| im-20.json | azure:us-central | 5.286 | 1522 | 68.3 | 0 | 0 | [30, 31, 29, 30] |
| im-23.json | azure:us-central | 5.284 | 1522 | 69.3 | 0 | 0 | [30, 30, 30, 30] |
| im-14.json | gcp:ap-northeast | 5.200 | 1560 | 249.6 | 1 | 0 | [31, 32, 27, 30] |
| im-41.json | gcp:us-east | 5.166 | 1557 | 65.5 | 0 | 0 | [30, 30, 30, 30] |
| im-07.json | gcp:us-east | 5.048 | 1594 | 67.2 | 0 | 0 | [30, 30, 30, 30] |
| im-25.json | unspecified:us-central | 5.016 | 1604 | 87.7 | 0 | 0 | [31, 30, 30, 29] |
| im-44.json | gcp:us-east4 | 4.998 | 1610 | 64.8 | 0 | 0 | [30, 30, 30, 30] |
| im-17.json | gcp:us-east | 4.839 | 1662 | 78.9 | 0 | 0 | [30, 30, 30, 30] |
| im-05.json | oci:us-chicago-1 | 4.748 | 1694 | 65.8 | 0 | 0 | [30, 30, 30, 30] |
| im-04.json | unspecified:us-central | 4.466 | 1802 | 76.1 | 0 | 0 | [30, 30, 30, 30] |
| im-06.json | unspecified:us-central | 3.915 | 2055 | 101.9 | 0 | 0 | [30, 30, 30, 30] |
| im-24.json | unspecified:denver | 3.400 | 2366 | 115.5 | 0 | 0 | [31, 29, 30, 30] |
| im-10.json | unspecified:eu-north | 2.831 | 2842 | 132.1 | 0 | 0 | [30, 30, 30, 30] |
| im-15.json | unspecified:eu-north | 1.615 | 5481 | 366.0 | 12 | 6 | [32, 33, 27, 28] |
| im-26.json | gcp:us-east | 1.197 | 6776 | 5233.2 | 2 | 1 | [22, 17, 43, 38] |

## allocator QD8 @64 — one row per run

| run | provider/region | GB/s | wall ms | worst preadv ms | rescues | wins | reader block counts |
|---|---|---:|---:|---:|---:|---:|---|
| im-45.json | unspecified:eu-north | 7.088 | 1135 | 98.6 | 0 | 0 | [16, 15, 14, 15, 15, 15, 15, 15] |
| im-37.json | gcp:us-west | 6.372 | 1263 | 113.9 | 0 | 0 | [15, 16, 15, 14, 15, 15, 15, 15] |
| im-21.json | unspecified:CANADA-2 | 6.302 | 1277 | 120.8 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-34.json | gcp:us-west | 6.115 | 1316 | 137.6 | 0 | 0 | [15, 15, 15, 14, 15, 16, 15, 15] |
| im-44.json | oci:us-ashburn-1 | 5.936 | 1355 | 111.5 | 0 | 0 | [15, 16, 14, 15, 15, 15, 15, 15] |
| im-42.json | gcp:us-west | 5.834 | 1379 | 131.1 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-27.json | gcp:us-west | 5.824 | 1450 | 291.9 | 6 | 2 | [14, 17, 13, 17, 14, 15, 16, 14] |
| im-19.json | gcp:asia-northeast1 | 5.764 | 1396 | 138.8 | 0 | 0 | [15, 15, 16, 15, 14, 15, 15, 15] |
| im-28.json | gcp:us-east | 5.760 | 1397 | 130.9 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-12.json | gcp:us-west | 5.579 | 1442 | 124.6 | 0 | 0 | [16, 15, 15, 14, 15, 15, 15, 15] |
| im-04.json | gcp:us-west | 5.362 | 1500 | 129.4 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-14.json | gcp:us-west | 5.140 | 1565 | 134.6 | 0 | 0 | [16, 15, 15, 15, 15, 15, 15, 14] |
| im-30.json | gcp:uk | 5.062 | 1589 | 145.4 | 0 | 0 | [15, 15, 14, 16, 15, 15, 15, 15] |
| im-31.json | gcp:asia-south2 | 5.044 | 1595 | 151.2 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-03.json | gcp:us-west | 4.870 | 1652 | 129.7 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-32.json | gcp:us-west | 4.860 | 1655 | 134.5 | 0 | 0 | [15, 15, 15, 15, 15, 15, 16, 14] |
| im-26.json | gcp:us-east | 4.845 | 1660 | 210.1 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-24.json | gcp:asia-northeast1 | 4.843 | 1661 | 135.0 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-07.json | gcp:us-west | 4.782 | 1682 | 128.2 | 0 | 0 | [15, 16, 15, 14, 15, 15, 15, 15] |
| im-18.json | gcp:us-east4 | 4.775 | 1685 | 129.5 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-35.json | gcp:us-west | 4.733 | 1700 | 135.7 | 0 | 0 | [16, 15, 15, 15, 14, 15, 15, 15] |
| im-25.json | gcp:us-west | 4.686 | 1717 | 202.1 | 0 | 0 | [15, 15, 16, 14, 14, 15, 15, 16] |
| im-05.json | gcp:us-west | 4.679 | 1719 | 138.9 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-06.json | gcp:us-west | 4.648 | 1731 | 127.4 | 0 | 0 | [15, 14, 15, 15, 15, 15, 16, 15] |
| im-17.json | unspecified:us-central | 4.594 | 1751 | 166.2 | 0 | 0 | [16, 15, 15, 15, 14, 15, 15, 15] |
| im-01.json | gcp:us-west | 4.568 | 1761 | 142.8 | 0 | 0 | [15, 15, 15, 15, 16, 15, 14, 15] |
| im-43.json | gcp:us-west1 | 4.519 | 1780 | 141.9 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-33.json | gcp:us-west | 4.492 | 1791 | 133.8 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-41.json | azure:centralus | 4.280 | 1880 | 148.6 | 0 | 0 | [15, 15, 15, 15, 15, 15, 15, 15] |
| im-29.json | gcp:uk | 4.242 | 1897 | 162.1 | 0 | 0 | [15, 14, 15, 16, 15, 15, 15, 15] |

## Control — frozen 30 (unchanged from prior A/B)

| run | provider/region | GB/s | wall ms | worst preadv ms |
|---|---|---:|---:|---:|
| im-10-invalid10.json | unspecified:eu-north | 7.194 | 1118 | 51.0 |
| im-11-invalid1.json | unspecified:CANADA-2 | 6.506 | 1236 | 59.0 |
| im-10-invalid20.json | gcp:us-west1 | 6.447 | 1248 | 62.3 |
| im-10-invalid6.json | gcp:us-east | 6.422 | 1253 | 69.2 |
| im-10-invalid30.json | gcp:us-west | 6.252 | 1287 | 68.6 |
| im-10-invalid18.json | gcp:us-west1 | 6.250 | 1287 | 60.8 |
| im-10-invalid15.json | gcp:us-west | 6.248 | 1288 | 56.9 |
| im-10-invalid25.json | gcp:us-west1 | 6.228 | 1292 | 60.7 |
| im-10-invalid12.json | gcp:us-west1 | 6.196 | 1299 | 61.2 |
| im-11-invalid2.json | gcp:us-west | 6.120 | 1314 | 68.5 |
| im-10-invalid29.json | gcp:us-west | 6.097 | 1320 | 61.7 |
| im-11-invalid4.json | gcp:us-west | 6.070 | 1325 | 68.0 |
| im-10-invalid16.json | gcp:us-west1 | 6.062 | 1327 | 60.6 |
| im-10-invalid19.json | gcp:us-west | 6.058 | 1328 | 65.1 |
| im-11-invalid5.json | gcp:us-central | 6.016 | 1337 | 67.7 |
| im-10-invalid22.json | gcp:us-west1 | 6.015 | 1338 | 61.9 |
| im-11-invalid6.json | gcp:us-west | 6.008 | 1339 | 68.1 |
| im-10-invalid28.json | gcp:us-west1 | 5.752 | 1399 | 62.6 |
| im-10-invalid21.json | gcp:us-west | 5.737 | 1402 | 62.3 |
| im-10-invalid9.json | gcp:us-central | 5.672 | 1418 | 78.6 |
| im-11-invalid8.json | gcp:us-east4 | 5.600 | 1437 | 64.2 |
| im-10-invalid23.json | gcp:us-west | 5.562 | 1446 | 62.4 |
| im-10-invalid26.json | gcp:us-west | 5.532 | 1454 | 65.5 |
| im-10-invalid17.json | gcp:us-east | 5.420 | 1484 | 74.5 |
| im-11-invalid3.json | oci:us-central | 5.392 | 1492 | 74.2 |
| im-10-invalid24.json | oci:us-chicago-1 | 5.309 | 1515 | 76.3 |
| im-10-invalid8.json | oci:us-central | 5.293 | 1520 | 65.5 |
| im-10-invalid27.json | gcp:us-central | 5.276 | 1525 | 63.3 |
| im-10-invalid7.json | oci:us-chicago-1 | 5.085 | 1582 | 78.7 |
| im-10-invalid11.json | oci:us-central | 3.060 | 2629 | 248.8 |

