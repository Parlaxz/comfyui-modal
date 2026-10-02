# mmap window-size sweep — fresh-window architecture (C)

Carries forward ONLY C (fresh mmap -> native memcpy -> munmap). Fixed: pure CPU source,
H100 host (GPU untouched), 4 processes, QD4, same file, same self-service scheduler,
MAP_POPULATE removed, exact full-file coverage, no toucher / preadv / M0 / M1 / segmented.

Spacing scales with window size so the **byte launch rate stays ~constant**:
32 MiB→2 ms, 64 MiB→4 ms, 128 MiB→8 ms, 256 MiB→16 ms. This is geometry isolation, **not**
a pacing optimum — pacing is optimised separately later.

Counting: US only; singleton US regions excluded; excluded retained; Odin excluded.
Workspace: **Testing 5** (`ws_c1487d319820`).

## Counted arms

| window | counted n | valid runs | excluded (non-US) |
|---|---:|---:|---:|
| 32 MiB | 6 | 36 | 28 |
| 64 MiB | 6 | 36 | 27 |
| 128 MiB | 6 | 36 | 28 |
| 256 MiB | 6 | 36 | 29 |

## Throughput / wall

| window | n | GB/s med | mean | p10 | p90 | best | worst | wall med | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 MiB | 6 | 6.879 | 6.167 | 4.368 | 7.255 | 7.262 | 3.569 | 1171 | 1395 |
| 64 MiB | 6 | 5.189 | 4.970 | 3.879 | 5.843 | 6.096 | 3.331 | 1551 | 1682 |
| 128 MiB | 6 | 5.351 | 5.217 | 3.949 | 6.350 | 6.392 | 3.769 | 1509 | 1606 |
| 256 MiB | 6 | 5.581 | 5.321 | 4.097 | 6.283 | 6.664 | 3.969 | 1441 | 1564 |

## Variance

| window | SD | CV | MAD | p90-p10 |
|---|---:|---:|---:|---:|
| 32 MiB | 1.3686 | 0.2219 | 1.0394 | 2.8873 |
| 64 MiB | 0.8886 | 0.1788 | 0.6748 | 1.9643 |
| 128 MiB | 1.0070 | 0.1930 | 0.9046 | 2.4014 |
| 256 MiB | 0.9402 | 0.1767 | 0.7327 | 2.1855 |

## Per provider:region (n>=2)

| window | provider:region | n | median GB/s | CV | MAD | p90-p10 |
|---|---|---:|---:|---:|---:|---:|
| 32 MiB | GCP:us-west4 | 2 | 6.138 | 0.1583 | 0.9719 | 1.5550 |
| 32 MiB | OCI:us-central | 2 | 6.955 | 0.0441 | 0.3069 | 0.4910 |
| 32 MiB | UNSPECIFIED:us-central | 2 | 5.409 | 0.3401 | 1.8395 | 2.9432 |
| 64 MiB | GCP:us-west4 | 2 | 5.673 | 0.0747 | 0.4238 | 0.6781 |
| 64 MiB | OCI:us-chicago-1 | 2 | 5.360 | 0.0431 | 0.2307 | 0.3692 |
| 128 MiB | OCI:us-central | 2 | 5.986 | 0.0538 | 0.3223 | 0.5157 |
| 128 MiB | UNSPECIFIED:us-central | 2 | 4.404 | 0.1441 | 0.6347 | 1.0155 |
| 256 MiB | OCI:us-central | 3 | 5.902 | 0.0743 | 0.3567 | 0.8561 |

## Operation cost (map + memcpy + unmap) and tails

| window | ops | median ms | p95 | p99 | worst | >=250 | >=500 | >=1s | >=2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 MiB | 1440 | 19.22 | 41.95 | 58.76 | 80.4 | 0 | 0 | 0 | 0 |
| 64 MiB | 720 | 50.50 | 86.92 | 118.29 | 143.3 | 0 | 0 | 0 | 0 |
| 128 MiB | 360 | 98.30 | 155.48 | 188.02 | 208.5 | 0 | 0 | 0 | 0 |
| 256 MiB | 180 | 183.02 | 287.37 | 352.15 | 360.1 | 26 | 0 | 0 | 0 |

**Normalized tails** (raw counts are NOT comparable across window sizes):

| window | ops/TiB | >=250 per 1000 ops | >=250 per TiB | >=500 per TiB | >=1s per TiB |
|---|---:|---:|---:|---:|---:|
| 32 MiB | 32800.9 | 0.00 | 0.00 | 0.00 | 0.00 |
| 64 MiB | 16400.5 | 0.00 | 0.00 | 0.00 | 0.00 |
| 128 MiB | 8200.2 | 0.00 | 0.00 | 0.00 | 0.00 |
| 256 MiB | 4100.1 | 144.44 | 592.24 | 0.00 | 0.00 |

## Affected-run count

| window | runs >=250 | runs >=500 | runs >=1s | runs >=2s |
|---|---:|---:|---:|---:|
| 32 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 64 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 128 MiB | 0/6 | 0/6 | 0/6 | 0/6 |
| 256 MiB | 2/6 | 0/6 | 0/6 | 0/6 |

## Phase split, concurrency, spacing, finish spread

| window | map_ms med | memcpy_ms med | unmap_ms med | op_wall med | eff concurrency | achieved min spacing ms | finish spread ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 MiB | 0.039 | 17.84 | 1.203 | 19.22 | 3.9328 | 2.0051 | 1153 |
| 64 MiB | 0.056 | 47.66 | 2.725 | 50.50 | 3.9341 | 4.0270 | 1504 |
| 128 MiB | 0.062 | 94.76 | 4.719 | 98.30 | 3.8847 | 8.0296 | 1415 |
| 256 MiB | 0.068 | 172.72 | 9.568 | 183.02 | 3.7866 | 16.0813 | 1272 |

## Every operation >=250 ms, with absolute byte range

| window | run | provider:region | offset | length | op ms | intersects historical offset |
|---|---|---|---:|---:|---:|---|
| 256 MiB | im-101.json | AWS:us-west | 4294967296 | 268435456 | 269.6 | no |
| 256 MiB | im-101.json | AWS:us-west | 2147483648 | 268435456 | 262.1 | no |
| 256 MiB | im-101.json | AWS:us-west | 6174015488 | 268435456 | 265.8 | no |
| 256 MiB | im-101.json | AWS:us-west | 0 | 268435456 | 252.5 | no |
| 256 MiB | im-101.json | AWS:us-west | 5368709120 | 268435456 | 252.6 | no |
| 256 MiB | im-101.json | AWS:us-west | 3221225472 | 268435456 | 259.6 | no |
| 256 MiB | im-101.json | AWS:us-west | 1073741824 | 268435456 | 350.6 | no |
| 256 MiB | im-101.json | AWS:us-west | 5637144576 | 268435456 | 258.2 | no |
| 256 MiB | im-101.json | AWS:us-west | 3489660928 | 268435456 | 260.2 | no |
| 256 MiB | im-101.json | AWS:us-west | 1342177280 | 268435456 | 360.1 | no |
| 256 MiB | im-101.json | AWS:us-west | 3758096384 | 268435456 | 255.4 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 4294967296 | 268435456 | 262.8 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 6174015488 | 268435456 | 275.6 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 2147483648 | 268435456 | 329.6 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 0 | 268435456 | 287.2 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 4563402752 | 268435456 | 314.1 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 6442450944 | 268435456 | 329.4 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 268435456 | 268435456 | 310.3 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 2415919104 | 268435456 | 358.0 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 4831838208 | 268435456 | 290.0 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 6710886400 | 268435456 | 283.7 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 536870912 | 268435456 | 264.5 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 2684354560 | 268435456 | 287.3 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 2952790016 | 268435456 | 287.3 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 3221225472 | 268435456 | 287.9 | no |
| 256 MiB | im-52.json | UNSPECIFIED:us-central | 3489660928 | 268435456 | 269.0 | no |

## Outliers (provider:region on every one)

| window | kind | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---|---:|---:|---:|
| 32 MiB | bottom-decile | im-25.json | UNSPECIFIED:us-central | 3.569 | 2254 | 80.4 |
| 32 MiB | worst run | im-25.json | UNSPECIFIED:us-central | 3.569 | 2254 | 80.4 |
| 64 MiB | bottom-decile | im-114.json | AWS:us-west | 3.331 | 2415 | 143.3 |
| 64 MiB | worst run | im-114.json | AWS:us-west | 3.331 | 2415 | 143.3 |
| 128 MiB | bottom-decile | im-03.json | UNSPECIFIED:us-central | 3.769 | 2134 | 208.5 |
| 128 MiB | worst run | im-03.json | UNSPECIFIED:us-central | 3.769 | 2134 | 208.5 |
| 256 MiB | bottom-decile | im-52.json | UNSPECIFIED:us-central | 3.969 | 2027 | 358.0 |
| 256 MiB | worst run | im-52.json | UNSPECIFIED:us-central | 3.969 | 2027 | 358.0 |

## Guards

| window | exact coverage | amp=1.0 | maxQD=4 | min spacing >= nominal | worker errors | map/unmap errors |
|---|---|---|---|---|---:|---|
| 32 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 64 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 128 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |
| 256 MiB | 6/6 | 6/6 | 6/6 | 6/6 | 0 | 0/0 |

