# EXPERIMENT 1 — CPU AFFINITY

A = current behaviour, no explicit reader affinity.  B = each of the 4 reader
processes pinned to a different allowed CPU.  Parent not pinned.  Process count
unchanged.  Geometry LOCKED: 64 MiB / QD4 / 4 ms / fresh-window / MAP_PRIVATE.
Strong interleave: 30 rounds of 2 arms, each round a different permutation
(seed 20261005).

**Counting rule:** per arm, regions with >=3 runs; <3-run regions dropped; no US-only
filter; Odin excluded but retained; never excluded because slow. Target 15/arm.

| arm | affinity | launches | counted | excluded | regions counted |
|---|---|---:|---:|---:|---|
| A | none | 30 | 15 | 15 | {'asia-northeast1': 8, 'europe-west9': 3, 'uk': 1, 'europe-west2': 3} |
| B | per-reader CPU pin | 30 | 15 | 15 | {'ca': 4, 'asia-northeast1': 7, 'uk': 4} |

## Affinity audit

- `sched_getaffinity`/`sched_setaffinity` present: **True**
- allowed CPU set: **28 CPUs** ([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27])
- per-reader assignment (reader -> CPU, set_ok, observed after):
    - reader 0 -> CPU 0, set_ok=True, after=[0], errno=None
    - reader 1 -> CPU 1, set_ok=True, after=[1], errno=None
    - reader 2 -> CPU 2, set_ok=True, after=[2], errno=None
    - reader 3 -> CPU 3, set_ok=True, after=[3], errno=None
- physical-core topology: available=**False** distinct_physical_cores=None note=None
- **LIMITATION:** topology is NOT readable under this deployed gVisor, so the four CPUs are distinct allowed LOGICAL CPUs; whether they are distinct physical cores is unverified.

## Whole-run

| arm | n | median | mean | p10 | p90 | best | worst | wall med | wall mean | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 15 | 5.550 | 4.823 | 2.613 | 5.852 | 6.224 | 2.053 | 1450 | 1892 | 1.3682 | 0.2837 | 0.9352 | 3.239 |
| B | 15 | 5.534 | 5.800 | 5.122 | 6.864 | 7.002 | 4.904 | 1454 | 1405 | 0.6784 | 0.1170 | 0.5492 | 1.742 |

## Operation distribution

| arm | ops | med | p95 | p99 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | affected runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1800 | 47.9 | 125.9 | 170.7 | 272.2 | 289 | 23 | 1 | 0 | 0 | 0 | 1/15 (7%) |
| B | 1800 | 45.3 | 58.0 | 93.5 | 104.4 | 8 | 0 | 0 | 0 | 0 | 0 | 0/15 (0%) |

## Normalized tails — BOTH definitions, kept separate

| arm | (1) pooled worst/pooled med | (2) max per-run worst/own med |
|---|---:|---:|
| A | 5.68 | 2.69 |
| B | 2.31 | 2.14 |

## Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3.929 | 4 | 1407 | 0.059 | 45.3 | 2.38 | 47.9 | 4.004 |
| B | 3.922 | 4 | 1410 | 0.056 | 42.6 | 2.44 | 45.3 | 4.001 |

## Experiment 1 — per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected runs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | GCP:asia-northeast1 | 8 | 5.574 | 0.0582 | 0.2345 | 5.290 | 5.969 | 0 |
| A | GCP:europe-west2 | 3 | 2.899 | 0.1014 | 0.2261 | 2.517 | 3.060 | 0 |
| A | GCP:europe-west9 | 3 | 5.629 | 0.0185 | 0.0780 | 5.611 | 5.798 | 0 |
| B | GCP:asia-northeast1 | 7 | 5.421 | 0.0524 | 0.2088 | 5.123 | 5.785 | 0 |
| B | GCP:uk | 4 | 5.390 | 0.0702 | 0.3305 | 5.007 | 5.816 | 0 |
| B | UNSPECIFIED:ca | 4 | 6.848 | 0.0243 | 0.1476 | 6.629 | 6.980 | 0 |

## Experiment 1 — matched provider:region (n>=3 on BOTH sides, uncapped)

| provider:region | A n | A med | B n | B med | delta (B-A) |
|---|---:|---:|---:|---:|---:|
| GCP:asia-northeast1 | 10 | 5.626 | 14 | 5.643 | +0.3% |
| GCP:uk | 4 | 3.619 | 6 | 5.193 | +43.5% |

matched-restricted: A n=14 med=5.574 mean=5.239 p10=2.943 worst=2.002
matched-restricted: B n=20 med=5.482 mean=5.578 p10=4.869 worst=4.063
median delta (B-A): -1.7%

# EXPERIMENT 2 — FIXED-VA WINDOW REPLACEMENT

A = current normal `mmap` -> memcpy -> `munmap`.  B = one reader-owned 64 MiB VA
slot (anonymous PROT_NONE reservation) with each file window MAP_FIXED into that
same slot, so replacement removes the previous mapping; ONE final munmap at end.
Never MAP_FIXED outside the owned slot; every replacement asserted == slot_base.
Geometry LOCKED: 64 MiB / QD4 / 4 ms / fresh-window / MAP_PRIVATE / PROT_READ.
Strong interleave: 30 rounds of 2 arms (seed 20261006).

| arm | mode | launches | counted | excluded | regions counted |
|---|---|---:|---:|---:|---|
| A | mmap/munmap | 29 | 15 | 14 | {'europe-west2': 3, 'asia-northeast1': 5, 'uk': 2, 'ap-northeast': 3, 'CANADA-2': 2} |
| B | fixed-VA replace | 30 | 15 | 15 | {'europe-west2': 3, 'asia-northeast1': 6, 'uk': 4, 'CANADA-2': 2} |

## Fixed-VA safety / telemetry (arm B)

| metric | value |
|---|---:|
| replacements total (all counted B runs) | 1800 |
| replacement errors total | 0 |
| peak live mappings (max) | 1 |
| final live mappings (max) | 0 |
| slots leaked after cleanup | 0 / 60 |
| slots page-aligned | 60 / 60 |
| distinct slot bases (per reader) | 15 — [46950772637696, 46995332923392, 47039222120448, 47064387944448, 47064656379904, 47215248670720, 47287189372928, 47557707300864, 47665280712704, 47709304127488, 47780439523328, 47792988880896, 47836810969088, 47842582331392, 47925262548992] |
| worker errors (all B runs) | 0 |
| barrier errors | 0 |

## Cost decomposition (median per operation)

| arm | mmap/replacement ms | memcpy ms | explicit munmap ms | op_wall ms |
|---|---:|---:|---:|---:|
| A | 0.0610 | 46.0 | 2.2204 | 48.4 |
| B | 2.2388 | 44.0 | 0.0000 | 46.6 |

## Source-ready vs fully-cleaned wall

| arm | source-ready wall med ms | fully-cleaned wall med ms | final cleanup med ms |
|---|---:|---:|---:|
| A | 1494.7 | 1494.7 | 0.00 |
| B | 1433.2 | 1436.3 | 3.12 |

## Whole-run

| arm | n | median | mean | p10 | p90 | best | worst | wall med | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 15 | 5.382 | 4.827 | 2.495 | 6.351 | 6.797 | 2.313 | 1495 | 1.5019 | 0.3111 | 1.1835 | 3.855 |
| B | 15 | 5.613 | 5.142 | 2.837 | 6.649 | 6.920 | 2.438 | 1433 | 1.4809 | 0.2880 | 1.1386 | 3.812 |

## Operation distribution

| arm | ops | med | p95 | p99 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | affected runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1800 | 48.4 | 120.7 | 170.3 | 222.7 | 307 | 23 | 0 | 0 | 0 | 0 | 0/15 (0%) |
| B | 1800 | 46.6 | 113.0 | 139.5 | 224.9 | 196 | 12 | 0 | 0 | 0 | 0 | 0/15 (0%) |

## Normalized tails — BOTH definitions, kept separate

| arm | (1) pooled worst/pooled med | (2) max per-run worst/own med |
|---|---:|---:|
| A | 4.60 | 5.09 |
| B | 4.83 | 3.51 |

## Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 3.895 | 4 | 1449 | 0.0610 | 46.0 | 2.2204 | 48.4 | 4.001 |
| B | 3.863 | 4 | 1389 | 2.2388 | 44.0 | 0.0000 | 46.6 | 4.007 |

## Experiment 2 — per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected runs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| A | GCP:ap-northeast | 3 | 5.585 | 0.0702 | 0.3140 | 5.423 | 6.177 | 0 |
| A | GCP:asia-northeast1 | 5 | 5.402 | 0.0677 | 0.3128 | 5.138 | 5.962 | 0 |
| A | GCP:europe-west2 | 3 | 2.482 | 0.0363 | 0.0675 | 2.347 | 2.509 | 0 |
| B | GCP:asia-northeast1 | 6 | 5.740 | 0.0844 | 0.4019 | 5.308 | 6.386 | 0 |
| B | GCP:europe-west2 | 3 | 2.751 | 0.1129 | 0.2565 | 2.500 | 3.116 | 0 |
| B | GCP:uk | 4 | 5.480 | 0.2750 | 1.1074 | 3.649 | 6.560 | 0 |

## Experiment 2 — matched provider:region (n>=3 on BOTH sides, uncapped)

| provider:region | A n | A med | B n | B med | delta (B-A) |
|---|---:|---:|---:|---:|---:|
| GCP:asia-northeast1 | 7 | 5.359 | 7 | 5.637 | +5.2% |
| GCP:europe-west2 | 3 | 2.482 | 5 | 2.751 | +10.8% |
| GCP:uk | 3 | 3.997 | 4 | 5.480 | +37.1% |
| UNSPECIFIED:CANADA-2 | 4 | 6.542 | 4 | 6.402 | -2.1% |

matched-restricted: A n=17 med=5.359 mean=4.957 p10=2.502 worst=2.313
matched-restricted: B n=20 med=5.633 mean=5.167 p10=2.728 worst=2.438
median delta (B-A): +5.1%

