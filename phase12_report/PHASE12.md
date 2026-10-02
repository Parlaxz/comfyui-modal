# PHASE 1 — pacing 0 / 2 / 4 ms (64 MiB, QD4, fresh-window mmap)

Geometry LOCKED: 64 MiB / QD4 / 4 reader processes / fresh-window `mmap` -> native
memcpy -> `munmap`, MAP_POPULATE removed, pure CPU source, H100 host (GPU untouched).
Only the intentional global launch-spacing floor changes. 0 ms = `_alloc_gate` returns
immediately at `gap_ns=0`; scheduler, QD, process count and allocator are unchanged.

**Counting rule:** per arm, regions with >=3 runs; drop <3-run regions; no US-only
filter; Odin excluded; no slow run ever removed. Target 15 counted/arm.

**Interleave:** 30 rounds of 3 arms, each round a different permutation (seed 20261003).

| arm | launches | counted | excluded | regions counted |
|---|---:|---:|---:|---|
| P0 (0 ms) | 30 | 15 | 15 | {'eu-west': 5, 'asia-northeast1': 3, 'europe-west9': 3, 'CANADA-2': 4} |
| P2 (2 ms) | 30 | 15 | 15 | {'CANADA-2': 5, 'uk': 5, 'europe-west2': 3, 'ca': 2} |
| P4 (4 ms) | 30 | 15 | 15 | {'CANADA-2': 4, 'us-west': 2, 'asia-northeast1': 3, 'europe-west9': 2, 'ca': 3, 'eu-west': 1} |

## Whole-run

| arm | n | median | mean | p10 | p90 | best | worst | wall med | wall mean | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 15 | 5.592 | 5.442 | 4.397 | 6.897 | 7.192 | 2.344 | 1439 | 1586 | 1.1815 | 0.2171 | 0.8933 | 2.499 |
| P2 | 15 | 6.179 | 5.431 | 2.194 | 7.307 | 7.970 | 2.097 | 1302 | 1873 | 2.0487 | 0.3772 | 1.5819 | 5.114 |
| P4 | 15 | 6.287 | 5.965 | 4.317 | 6.963 | 7.363 | 3.649 | 1280 | 1404 | 1.0491 | 0.1759 | 0.7738 | 2.646 |

## Operation distribution

| arm | ops | med | p90 | p95 | p99 | p99.5 | worst | >=100 | >=150 | >=250 | >=500 | >=1s | >=2s | per1000 | per TiB | affected runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 1800 | 45.2 | 63.7 | 71.2 | 125.0 | 294.4 | 1945.3 | 36 | 17 | 11 | 7 | 2 | 0 | 6.1 | 100.2 | 2/15 (13%) |
| P2 | 1800 | 39.8 | 126.2 | 134.4 | 162.3 | 194.1 | 218.3 | 420 | 29 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0/15 (0%) |
| P4 | 1800 | 41.9 | 67.6 | 74.6 | 90.6 | 102.9 | 151.3 | 10 | 1 | 0 | 0 | 0 | 0 | 0.0 | 0.0 | 0/15 (0%) |

## Normalized tails — BOTH definitions kept separate

| arm | (1) pooled worst / pooled median | (2) max per-run [worst / own median] | p95/med | p99/med |
|---|---:|---:|---:|---:|
| P0 | 43.03 | 65.01 | 1.58 | 2.77 |
| P2 | 5.49 | 3.76 | 3.38 | 4.08 |
| P4 | 3.61 | 2.45 | 1.78 | 2.16 |

## Execution

| arm | eff conc | max conc | finish spread ms | map_ms | memcpy_ms | unmap_ms | op_wall_ms | min spacing | median spacing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P0 | 3.966 | 4 | 1395 | 0.058 | 43.1 | 1.94 | 45.2 | 0.008 | 0.030 |
| P2 | 3.934 | 4 | 1266 | 0.057 | 37.5 | 2.31 | 39.8 | 2.010 | 2.041 |
| P4 | 3.907 | 4 | 1240 | 0.060 | 39.6 | 2.37 | 41.9 | 4.010 | 4.045 |

## Phase 1 — per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected runs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0.0 | GCP:asia-northeast1 | 3 | 5.665 | 0.1401 | 0.6568 | 5.310 | 6.886 | 0 |
| 0.0 | GCP:eu-west | 5 | 5.592 | 0.1259 | 0.5414 | 5.075 | 6.552 | 1 |
| 0.0 | GCP:europe-west9 | 3 | 4.652 | 0.0483 | 0.1656 | 4.312 | 4.710 | 0 |
| 0.0 | UNSPECIFIED:CANADA-2 | 4 | 6.160 | 0.3264 | 1.1196 | 3.468 | 6.547 | 1 |
| 2.0 | GCP:europe-west2 | 3 | 2.451 | 0.5875 | 1.6692 | 2.168 | 6.174 | 0 |
| 2.0 | GCP:uk | 5 | 6.000 | 0.4394 | 1.7397 | 2.194 | 6.621 | 0 |
| 2.0 | UNSPECIFIED:CANADA-2 | 5 | 6.791 | 0.0672 | 0.3393 | 6.232 | 7.186 | 0 |
| 4.0 | GCP:asia-northeast1 | 3 | 5.784 | 0.0545 | 0.2220 | 5.284 | 5.817 | 0 |
| 4.0 | UNSPECIFIED:CANADA-2 | 4 | 6.504 | 0.0257 | 0.1479 | 6.331 | 6.690 | 0 |
| 4.0 | UNSPECIFIED:ca | 3 | 6.692 | 0.0384 | 0.2081 | 6.528 | 7.028 | 0 |

## Phase 1 — every operation >=250 ms, with provider:region

| arm | run | provider:region | offset | length | op ms | historical hit |
|---|---|---|---:|---:|---:|---|
| 0.0 | im-03.json | GCP:eu-west | 6039797760 | 67108864 | 259.3 | [6039797760] |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 2013265920 | 67108864 | 730.9 | [2013265920] |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 4026531840 | 67108864 | 1945.3 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 6039797760 | 67108864 | 1891.9 | [6039797760] |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 67108864 | 67108864 | 823.8 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 2080374784 | 67108864 | 646.6 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 671088640 | 67108864 | 741.7 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 6106906624 | 67108864 | 952.8 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 4496293888 | 67108864 | 379.6 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 4831838208 | 67108864 | 299.1 | no |
| 0.0 | im-43.json | UNSPECIFIED:CANADA-2 | 7851737088 | 67108864 | 294.4 | no |

# PHASE 2 — deferred munmap (64 MiB / QD4 / 4 ms, fresh-window mmap)

`mmap` -> memcpy -> enqueue retired mapping -> continue; a bounded in-process reaper
THREAD (max 2 retired mappings per reader) performs the `munmap`. Never persistent-
segmented: every block is a fresh exact mapping. A mapping is retired only AFTER its
memcpy has fully returned.

launches=39 counted=20 excluded=19 regions(counted)={'uk': 5, 'us-central': 3, 'ca': 2, 'europe-west9': 4, 'CANADA-2': 2, 'eu-west': 2, 'asia-northeast1': 2}

## Dual clock (per-run median and pooled)

| metric | median | mean | min | max |
|---|---:|---:|---:|---:|
| source-ready wall ms | 1424.0 | 1759.6 | 1178.8 | 3186.2 |
| fully-drained wall ms | 1426.1 | 1761.9 | 1180.2 | 3189.0 |
| source-ready GB/s | 5.650 | 5.057 | 2.525 | 6.825 |
| fully-drained GB/s | 5.642 | 5.049 | 2.523 | 6.817 |
| final drain penalty ms | 2.24 | 2.30 | 1.39 | 3.10 |

## Reaper telemetry (summed over counted runs unless noted)

| metric | value |
|---|---:|
| queue_full_events (total) | 0 |
| max_queue_depth (max over runs) | 1 |
| avg_queue_depth (mean of per-run avgs) | 1.000 |
| reaper_queue_wait_ms_total | 0.00 |
| munmap_reaper_wall_ms_total | 5402.8 |
| munmaps_completed_total | 2400 |
| munmaps_completed_during_source_work | 2376 |
| munmaps_remaining_at_source_completion | 24 |
| live_mapping_peak (max) | 1 |
| mapping_leaks_after_drain | 0 |
| map_errors | 0 |
| unmap_errors | 0 |

## Whole-run + operation distribution (deferred-unmap)

- n=20 median=5.642 mean=5.049 p10=2.987 p90=6.633 best=6.817 worst=2.523 wall med=1426
- SD=1.4009 CV=0.2774 MAD=1.1189 p90-p10=3.646
- ops=2400 med=46.5 p95=108.0 p99=142.3 worst=2303.4
- >=100=188 >=150=19 >=250=7 >=500=5 >=1s=3 >=2s=1 affected=1/20 (5%)
- tails: (1) pooled worst/pooled med=49.54; (2) max per-run worst/own med=71.88
- eff conc=3.876 max conc=4 finish spread=1378 map=0.174 memcpy=46.1 unmap=0.00 retire=0.055 op_wall=46.5 spacing=4.002

## Phase 2 — per provider:region (n>=3)

| arm | provider:region | n | median GB/s | CV | MAD | p10 | p90 | affected runs |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| DU | GCP:europe-west9 | 4 | 5.708 | 0.0429 | 0.2134 | 5.355 | 5.848 | 0 |
| DU | GCP:uk | 4 | 3.103 | 0.1770 | 0.4253 | 2.940 | 4.044 | 0 |

## Phase 2 — every operation >=250 ms, with provider:region

| arm | run | provider:region | offset | length | op ms | historical hit |
|---|---|---|---:|---:|---:|---|
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 4026531840 | 67108864 | 1351.1 | no |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 6039797760 | 67108864 | 2303.4 | [6039797760] |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 2080374784 | 67108864 | 274.2 | no |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 335544320 | 67108864 | 857.1 | no |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 2214592512 | 67108864 | 1515.7 | no |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 4563402752 | 67108864 | 534.6 | no |
| DU | im-11.json | UNSPECIFIED:CANADA-2 | 2415919104 | 67108864 | 370.0 | no |

