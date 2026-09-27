# Sticky-lane allocator vs static — matched QD4 / 64 MiB

- static control: **30** frozen runs (reused unchanged, same 30 as prior A/B)
- sticky-lane allocator: **30** fresh valid non-Odin runs (first 30 by slot; 34 collected)

## Main A/B

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 30 | 6.015 | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | 1337 | 1408 |
| sticky-lane allocator QD4 | 30 | 5.294 | 4.745 | 2.933 | 6.221 | 7.152 | 0.494 | 1520 | 2706 |

- sticky median delta vs static: **-0.721 GB/s (-12.0%)**

## Read latency

| arm | preadv median | p95 | p99 | worst | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| static (control, QD4) | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| sticky-lane allocator QD4 | 43.89 | 59.81 | 81.39 | 8585.0 | 30 | 23 | 18 |

## Sticky scheduler detail

| metric | value |
|---|---:|
| lane sizes | [30, 30, 30, 30] |
| affinity breaks (total) | 108 |
| lane-finish reassignments (total) | 108 |
| rescue launches | 24 |
| rescue wins | 17 |
| rescue savings median/max ms | 0.10 / 9.91 (n=17) |
| amplification median/max | 1.0000 / 1.0667 |
| max physical QD | 4 |
| min launch spacing ms | 4.0030 |
| idle-no-work total ms | 13917.5 |
| stale duplicates | 23 |

Lane block counts per reader (per-run vectors):

- [30, 30, 30, 30] x6
- [30, 29, 30, 31] x3
- [31, 30, 29, 30] x2
- [31, 30, 30, 29] x2
- [30, 31, 30, 29] x2
- [29, 31, 30, 30] x1
- [43, 32, 32, 13] x1
- [42, 26, 31, 21] x1

## Within-provider medians (GB/s)

| provider | static n | static med | sticky n | sticky med |
|---|---:|---:|---:|---:|
| aws | 0 | - | 2 | 3.737 |
| gcp | 23 | 6.058 | 8 | 5.642 |
| oci | 5 | 5.293 | 6 | 5.045 |
| unspecified | 2 | 6.850 | 14 | 5.432 |

## Sticky treatment — one row per run

| run | provider/region | GB/s | wall ms | worst preadv ms | rescues | wins | lane block counts |
|---|---|---:|---:|---:|---:|---:|---|
| im-06.json | unspecified:eu-north | 7.152 | 1125 | 57.8 | 0 | 0 | [30, 30, 30, 30] |
| im-28.json | unspecified:eu-north | 6.881 | 1169 | 54.6 | 0 | 0 | [30, 31, 30, 29] |
| im-25.json | unspecified:eu-north | 6.856 | 1173 | 55.3 | 0 | 0 | [31, 29, 29, 31] |
| im-36.json | gcp:us-west | 6.151 | 1308 | 57.4 | 0 | 0 | [30, 30, 30, 30] |
| im-38.json | gcp:us-west | 6.143 | 1310 | 61.3 | 0 | 0 | [30, 30, 30, 30] |
| im-17.json | unspecified:eu-north1 | 5.870 | 1370 | 121.4 | 0 | 0 | [31, 30, 30, 29] |
| im-11.json | gcp:us-east | 5.814 | 1384 | 71.8 | 0 | 0 | [30, 30, 30, 30] |
| im-27.json | unspecified:us-central | 5.749 | 1399 | 67.9 | 0 | 0 | [30, 29, 30, 31] |
| im-26.json | oci:us-chicago-1 | 5.707 | 1410 | 62.1 | 0 | 0 | [30, 30, 30, 30] |
| im-14.json | gcp:us-west | 5.665 | 1420 | 67.0 | 0 | 0 | [30, 30, 30, 30] |
| im-01.json | gcp:ap-south | 5.619 | 1432 | 69.2 | 0 | 0 | [29, 31, 30, 30] |
| im-16.json | unspecified:uk | 5.498 | 1463 | 71.8 | 0 | 0 | [31, 30, 29, 30] |
| im-05.json | unspecified:us-west | 5.458 | 1474 | 67.6 | 0 | 0 | [28, 32, 31, 29] |
| im-09.json | unspecified:us-central | 5.406 | 1488 | 71.5 | 0 | 0 | [29, 29, 31, 31] |
| im-32.json | oci:us-central | 5.303 | 1517 | 85.3 | 0 | 0 | [30, 31, 30, 29] |
| im-18.json | unspecified:eu-north | 5.286 | 1522 | 103.7 | 0 | 0 | [31, 30, 30, 29] |
| im-33.json | oci:us-chicago-1 | 5.111 | 1574 | 111.3 | 0 | 0 | [31, 29, 30, 30] |
| im-24.json | oci:us-chicago-1 | 4.978 | 1616 | 82.0 | 0 | 0 | [32, 29, 31, 28] |
| im-12.json | gcp:us-east | 4.779 | 1711 | 608.4 | 2 | 1 | [33, 35, 26, 26] |
| im-35.json | gcp:us-east4 | 4.708 | 1737 | 238.9 | 2 | 2 | [33, 36, 29, 22] |
| im-34.json | oci:us-chicago-1 | 4.106 | 1959 | 140.2 | 0 | 0 | [31, 29, 32, 28] |
| im-08.json | gcp:us-west | 4.078 | 2006 | 493.7 | 2 | 2 | [32, 38, 27, 23] |
| im-29.json | oci:us-chicago-1 | 3.949 | 2037 | 123.3 | 0 | 0 | [31, 30, 29, 30] |
| im-02.json | aws:us-east | 3.741 | 2150 | 100.0 | 0 | 0 | [30, 29, 30, 31] |
| im-20.json | aws:us-east | 3.733 | 2155 | 106.0 | 0 | 0 | [30, 30, 31, 29] |
| im-13.json | unspecified:us-central | 3.267 | 2462 | 135.5 | 0 | 0 | [29, 30, 31, 30] |
| im-10.json | unspecified:us-central | 3.165 | 2542 | 164.0 | 0 | 0 | [30, 29, 30, 31] |
| im-03.json | unspecified:eu-north | 0.843 | 9938 | 5404.4 | 5 | 5 | [43, 32, 32, 13] |
| im-04.json | unspecified:eu-north | 0.836 | 9947 | 8585.0 | 5 | 3 | [42, 26, 31, 21] |
| im-39.json | unspecified:us-south | 0.494 | 17371 | 7500.1 | 8 | 4 | [56, 15, 17, 32] |

