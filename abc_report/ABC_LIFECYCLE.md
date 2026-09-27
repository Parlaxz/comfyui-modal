# A/B/C — mmap life-cycle architecture (WHOLE vs SEGMENTED vs FRESH)

Identical everything else: CPU source-only, H100 host (GPU untouched), 4 processes, QD4,
64 MiB, 4 ms floor, same file, same scheduler, same native memcpy consumer, exact
full-file coverage. No preadv, no toucher, no M1, no O_DIRECT, no CUDA/H2D, no new
block size / QD / pacing. MAP_POPULATE **removed from all three arms** (proven inert; a
same-window interleaved sanity check gave 7.265 vs 7.293 GB/s, 0.4% apart).

Counting rule: US only; singleton US regions excluded. Excluded runs retained.

| arm | counted n | valid runs | note |
|---|---:|---:|---|
| A WHOLE (persistent whole-file) | 8 | 29 | as specified |
| B SEGMENTED-PERSISTENT | 7 | 22 | **ONE SHORT of the specified 8** |
| C FRESH-WINDOW (current M2) | 8 | 28 | as specified |

## Main

| arm | n | GB/s med | mean | p10 | p90 | best | worst | wall med | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE (persistent whole-file) | 8 | 5.657 | 5.400 | 3.859 | 6.926 | 7.007 | 3.630 | 1423 | 1577 |
| B SEGMENTED-PERSISTENT | 7 | 4.469 | 4.956 | 3.859 | 6.395 | 7.154 | 3.429 | 1755 | 1681 |
| C FRESH-WINDOW (current M2) | 8 | 5.535 | 5.610 | 5.079 | 6.429 | 6.517 | 4.832 | 1453 | 1447 |

## Variance

| arm | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|
| A WHOLE (persistent whole-file) | 1.2327 | 0.2283 | 1.0687 | 3.0666 |
| B SEGMENTED-PERSISTENT | 1.1580 | 0.2336 | 0.9109 | 2.5360 |
| C FRESH-WINDOW (current M2) | 0.5483 | 0.0977 | 0.4254 | 1.3496 |

Per provider:region where n>=2:

| arm | provider:region | n | SD | CV | MAD | p90-p10 |
|---|---|---:|---:|---:|---:|---:|
| A WHOLE (persistent whole-file) | GCP:us-west | 3 | 1.1234 | 0.1949 | 0.8869 | 2.1286 |
| A WHOLE (persistent whole-file) | UNSPECIFIED:us-central | 3 | 0.9587 | 0.2147 | 0.7260 | 1.7423 |
| B SEGMENTED-PERSISTENT | GCP:us-east | 4 | 0.9824 | 0.1726 | 0.8288 | 2.0687 |
| B SEGMENTED-PERSISTENT | UNSPECIFIED:us-central | 3 | 0.3953 | 0.0994 | 0.3074 | 0.7378 |
| C FRESH-WINDOW (current M2) | GCP:us-east | 5 | 0.5180 | 0.0943 | 0.3844 | 1.0805 |
| C FRESH-WINDOW (current M2) | UNSPECIFIED:us-central | 3 | 0.5444 | 0.0939 | 0.4395 | 1.0549 |

## Operation tails

| arm | op median | p95 | p99 | worst | >=250 | >=500 | >=1s | >=2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE (persistent whole-file) | 44.63 | 97.66 | 142.84 | 199.0 | 0 | 0 | 0 | 0 |
| B SEGMENTED-PERSISTENT | 50.74 | 86.19 | 131.97 | 378.7 | 1 | 0 | 0 | 0 |
| C FRESH-WINDOW (current M2) | 44.39 | 61.07 | 102.15 | 534.2 | 4 | 1 | 0 | 0 |

## Life-cycle costs (means over counted runs)

| arm | prep/map ms | consume wall | cleanup ms | first-use inclusive wall | peak mappings | live maps | map bytes | map errs | unmap errs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A WHOLE (persistent whole-file) | 1.26 | 1577 | 70.49 | 1649 | 1.0 | 4.0 | 32179928192 | 0 | 0 |
| B SEGMENTED-PERSISTENT | 2.15 | 1681 | 60.11 | 1743 | 30.0 | 120.0 | 8044982272 | 0 | 0 |
| C FRESH-WINDOW (current M2) | 0.01 | 1447 | 0.00 | 1447 | 0.0 | 0.0 | 0 | 0 | 0 |

Reading note: for A and B the mapping work is deliberately done **before** consumption, so
`prep/map` is the honest cost of creating those mappings and `consume wall` is the cost once
mappings already exist. `first-use inclusive wall` = prep + consume + cleanup, i.e. what a
run would cost if the mappings had to be created for that run. Both numbers are reported.

## Every pathological operation (>=250 ms)

| arm | run | provider:region | abs offset | length | op ms |
|---|---|---|---:|---:|---:|
| B | im-59.json | GCP:us-east | 6106906624 | 67108864 | 378.7 |
| C | im-16.json | GCP:us-east | 6106906624 | 67108864 | 267.4 |
| C | im-52.json | GCP:us-east | 6039797760 | 67108864 | 308.7 |
| C | im-63.json | GCP:us-east | 6039797760 | 67108864 | 534.2 |
| C | im-63.json | GCP:us-east | 2281701376 | 67108864 | 388.1 |

## Recurrence at the historically slow offsets

Watched offsets: [2013265920, 4093640704, 4160749568, 6039797760] (not claimed to be permanently bad)

| arm | watched-offset ops | of which >=250 ms | offsets hit |
|---|---:|---:|---|
| A WHOLE (persistent whole-file) | 32 | 0 | none |
| B SEGMENTED-PERSISTENT | 28 | 0 | none |
| C FRESH-WINDOW (current M2) | 32 | 2 | {6039797760: 2} |

## Outliers (provider:region on every one)

| arm | kind | run | provider:region | GB/s | wall ms |
|---|---|---|---|---:|---:|
| A | bottom-decile | im-24.json | UNSPECIFIED:us-central | 3.630 | 2217 |
| A | worst run | im-24.json | UNSPECIFIED:us-central | 3.630 | 2217 |
| B | bottom-decile | im-02.json | UNSPECIFIED:us-central | 3.429 | 2288 |
| B | worst run | im-02.json | UNSPECIFIED:us-central | 3.429 | 2288 |
| C | bottom-decile | im-63.json | GCP:us-east | 4.832 | 1665 |
| C | worst run | im-63.json | GCP:us-east | 4.832 | 1665 |

## Correctness / guards

| arm | exact coverage | amp=1.0 | maxQD=4 | min spacing >=4ms | worker errors |
|---|---|---|---|---|---:|
| A WHOLE (persistent whole-file) | 8/8 | 8/8 | 8/8 | 8/8 | 0 |
| B SEGMENTED-PERSISTENT | 1/7 | 7/7 | 7/7 | 7/7 | 12 |
| C FRESH-WINDOW (current M2) | 8/8 | 8/8 | 8/8 | 8/8 | 0 |

