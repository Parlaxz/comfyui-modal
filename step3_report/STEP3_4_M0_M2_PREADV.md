# Step 3/4 — M0 vs M2 vs frozen preadv (region rule applied)

Counting rule (fixed before collection): US regions only; a US region appearing once
in an arm is excluded from counted statistics. Non-US and singleton runs are retained in
the raw directories and listed in the exclusion table below.

Geometry: 4 processes, logical QD4, 64 MiB, 4 ms floor, self-service scheduler, same file,
exact full-file coverage. M0/M2 have **no preadv payload path**; the consumer is the M0 C
memcpy into a preallocated private bytearray. No rescue, no toucher, no GPU, no CUDA.

## Primary table (counted)

| source | counted n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 persistent mmap | 32 | 5.419 | 5.267 | 4.030 | 6.490 | 7.407 | 3.437 | 1485 | 1585 |
| M2 exact-window mmap | 33 | 5.856 | 5.651 | 4.338 | 6.817 | 6.882 | 3.347 | 1374 | 1474 |
| preadv QD4/64/4ms (frozen) | 27 | 5.487 | 5.370 | 3.969 | 6.108 | 7.076 | 2.800 | 1466 | 1556 |

## Operation distribution (counted, pooled)

| source | ops | median | mean | p90 | p95 | p99 | p99.5 | worst |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M0 persistent mmap | 3840 | 47.31 | 51.56 | 71.55 | 81.04 | 112.55 | 128.23 | 657.4 |
| M2 exact-window mmap | 3960 | 43.10 | 47.97 | 65.84 | 79.36 | 124.05 | 147.91 | 1119.4 |
| preadv QD4/64/4ms (frozen) | 3240 | 46.58 | 50.42 | 65.91 | 77.83 | 121.66 | 135.73 | 220.5 |

## Tail counts (counted, pooled operations)

| source | >=100 | >=150 | >=250 | >=500 | >=1000 | >=2000 |
|---|---:|---:|---:|---:|---:|---:|
| M0 persistent mmap | 59 | 15 | 9 | 3 | 0 | 0 |
| M2 exact-window mmap | 73 | 19 | 8 | 4 | 1 | 0 |
| preadv QD4/64/4ms (frozen) | 66 | 8 | 0 | 0 | 0 | 0 |

## Normalized (per 1000 operations)

| source | >=250/1000 | >=500/1000 | >=1s/1000 |
|---|---:|---:|---:|
| M0 persistent mmap | 2.34 | 0.78 | 0.00 |
| M2 exact-window mmap | 2.02 | 1.01 | 0.25 |
| preadv QD4/64/4ms (frozen) | 0.00 | 0.00 | 0.00 |

## Run-level incidence (counted)

| source | runs >=250 | >=500 | >=1s | >=2s |
|---|---:|---:|---:|---:|
| M0 persistent mmap | 5/32 | 3/32 | 0/32 | 0/32 |
| M2 exact-window mmap | 4/33 | 3/33 | 1/33 | 0/33 |
| preadv QD4/64/4ms (frozen) | 0/27 | 0/27 | 0/27 | 0/27 |

## Every pathological operation (>=250 ms), with provider:region

| arm | run | provider:region | block | offset | operation ms |
|---|---|---|---:|---:|---:|
| M0 persistent mmap | im-112.json | GCP:us-east | 0 | 0 | 344.8 |
| M0 persistent mmap | im-137.json | GCP:us-east | 90 | 6039797760 | 276.0 |
| M0 persistent mmap | im-36.json | GCP:us-east4 | 90 | 6039797760 | 657.4 |
| M0 persistent mmap | im-36.json | GCP:us-east4 | 65 | 4362076160 | 280.5 |
| M0 persistent mmap | im-53.json | GCP:us-east | 90 | 6039797760 | 571.4 |
| M0 persistent mmap | im-53.json | GCP:us-east | 32 | 2147483648 | 324.7 |
| M0 persistent mmap | im-53.json | GCP:us-east | 63 | 4227858432 | 275.9 |
| M0 persistent mmap | im-53.json | GCP:us-east | 100 | 6710886400 | 250.0 |
| M0 persistent mmap | im-81.json | GCP:us-east | 90 | 6039797760 | 544.4 |

## Outliers: bottom-decile throughput, top-decile wall, worst per arm

| arm | kind | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---|---:|---:|---:|
| M0 persistent mmap | bottom-decile GB/s | im-01.json | UNSPECIFIED:us-central | 4.028 | 1997 | 125.8 |
| M0 persistent mmap | bottom-decile GB/s | im-28.json | UNSPECIFIED:us-central | 3.437 | 2341 | 122.8 |
| M0 persistent mmap | bottom-decile GB/s | im-77.json | UNSPECIFIED:us-central | 3.767 | 2136 | 124.9 |
| M0 persistent mmap | top-decile wall | im-01.json | UNSPECIFIED:us-central | 4.028 | 1997 | 125.8 |
| M0 persistent mmap | top-decile wall | im-28.json | UNSPECIFIED:us-central | 3.437 | 2341 | 122.8 |
| M0 persistent mmap | top-decile wall | im-77.json | UNSPECIFIED:us-central | 3.767 | 2136 | 124.9 |
| M0 persistent mmap | worst GB/s | im-28.json | UNSPECIFIED:us-central | 3.437 | 2341 | 122.8 |
| M2 exact-window mmap | bottom-decile GB/s | im-107.json | GCP:us-east | 4.326 | 1860 | 875.6 |
| M2 exact-window mmap | bottom-decile GB/s | im-122.json | UNSPECIFIED:us-central | 4.061 | 1981 | 126.3 |
| M2 exact-window mmap | bottom-decile GB/s | im-39.json | UNSPECIFIED:us-central | 4.078 | 1973 | 124.0 |
| M2 exact-window mmap | top-decile wall | im-107.json | GCP:us-east | 4.326 | 1860 | 875.6 |
| M2 exact-window mmap | top-decile wall | im-122.json | UNSPECIFIED:us-central | 4.061 | 1981 | 126.3 |
| M2 exact-window mmap | top-decile wall | im-39.json | UNSPECIFIED:us-central | 4.078 | 1973 | 124.0 |
| M2 exact-window mmap | worst GB/s | im-42.json | UNSPECIFIED:us-central | 3.347 | 2403 | 171.3 |
| preadv QD4/64/4ms (frozen) | bottom-decile GB/s | im-15.json | OCI:us-central | 2.800 | 2873 | 220.5 |
| preadv QD4/64/4ms (frozen) | bottom-decile GB/s | im-42.json | UNSPECIFIED:us-central | 3.765 | 2137 | 106.5 |
| preadv QD4/64/4ms (frozen) | bottom-decile GB/s | im-50.json | UNSPECIFIED:us-central | 3.733 | 2155 | 118.9 |
| preadv QD4/64/4ms (frozen) | top-decile wall | im-15.json | OCI:us-central | 2.800 | 2873 | 220.5 |
| preadv QD4/64/4ms (frozen) | top-decile wall | im-42.json | UNSPECIFIED:us-central | 3.765 | 2137 | 106.5 |
| preadv QD4/64/4ms (frozen) | top-decile wall | im-50.json | UNSPECIFIED:us-central | 3.733 | 2155 | 118.9 |
| preadv QD4/64/4ms (frozen) | worst GB/s | im-15.json | OCI:us-central | 2.800 | 2873 | 220.5 |

## Within-region comparison (regions present in >1 arm with >=2 counted runs)

| region | M0 n/med | M2 n/med | preadv n/med |
|---|---|---|---|
| us-ashburn-1 | 5/5.860 | 3/5.501 | 9/5.487 |
| us-central | 14/4.336 | 14/5.032 | 10/4.857 |
| us-east | 5/5.903 | 8/6.125 | 0/- |
| us-east4 | 5/5.767 | 4/6.592 | 0/- |
| us-west | 3/6.678 | 4/6.738 | 8/5.985 |

## Excluded runs (retained, not counted)

| arm | run | provider:region | GB/s | wall ms | worst op ms | reason |
|---|---|---|---:|---:|---:|---|
| M0 persistent mmap | im-08.json | UNSPECIFIED:eu-north | 6.226 | 1292 | 80.3 | non-US |
| M0 persistent mmap | im-101.json | UNSPECIFIED:eu-north | 6.802 | 1183 | 74.9 | non-US |
| M0 persistent mmap | im-12.json | UNSPECIFIED:eu-north | 7.054 | 1140 | 72.9 | non-US |
| M0 persistent mmap | im-132.json | UNSPECIFIED:eu-north | 7.048 | 1142 | 72.3 | non-US |
| M0 persistent mmap | im-16.json | GCP:asia-south2 | 5.689 | 1414 | 173.9 | non-US |
| M0 persistent mmap | im-17.json | UNSPECIFIED:eu-north | 7.152 | 1125 | 74.3 | non-US |
| M0 persistent mmap | im-20.json | UNSPECIFIED:eu-south | 7.868 | 1022 | 65.3 | non-US |
| M0 persistent mmap | im-21.json | UNSPECIFIED:eu-north | 7.285 | 1104 | 70.6 | non-US |
| M0 persistent mmap | im-24.json | UNSPECIFIED:eu-north | 6.049 | 1330 | 84.9 | non-US |
| M0 persistent mmap | im-37.json | UNSPECIFIED:ca | 6.668 | 1207 | 75.3 | non-US |
| M0 persistent mmap | im-41.json | UNSPECIFIED:eu-north | 7.171 | 1122 | 70.6 | non-US |
| M0 persistent mmap | im-48.json | UNSPECIFIED:eu-north | 2.263 | 3554 | 1743.5 | non-US |
| M0 persistent mmap | im-56.json | UNSPECIFIED:CANADA-2 | 2.529 | 3181 | 1780.8 | non-US |
| M0 persistent mmap | im-60.json | UNSPECIFIED:eu-north | 6.005 | 1340 | 84.8 | non-US |
| M0 persistent mmap | im-61.json | UNSPECIFIED:eu-north | 6.742 | 1193 | 83.7 | non-US |
| M0 persistent mmap | im-69.json | UNSPECIFIED:eu-north | 6.908 | 1165 | 72.8 | non-US |
| M0 persistent mmap | im-84.json | UNSPECIFIED:eu-north | 7.091 | 1135 | 75.0 | non-US |
| M2 exact-window mmap | im-10.json | UNSPECIFIED:eu-north | 7.808 | 1030 | 78.0 | non-US |
| M2 exact-window mmap | im-114.json | UNSPECIFIED:eu-south | 5.547 | 1450 | 74.8 | non-US |
| M2 exact-window mmap | im-115.json | UNSPECIFIED:eu-north | 7.089 | 1135 | 77.0 | non-US |
| M2 exact-window mmap | im-123.json | UNSPECIFIED:eu-north | 7.038 | 1143 | 79.2 | non-US |
| M2 exact-window mmap | im-19.json | UNSPECIFIED:eu-north | 7.789 | 1033 | 70.8 | non-US |
| M2 exact-window mmap | im-23.json | UNSPECIFIED:eu-north | 7.962 | 1010 | 56.8 | non-US |
| M2 exact-window mmap | im-34.json | UNSPECIFIED:US-1 | 6.202 | 1297 | 89.2 | non-US |
| M2 exact-window mmap | im-46.json | UNSPECIFIED:eu-south | 7.819 | 1029 | 60.1 | non-US |
| M2 exact-window mmap | im-47.json | UNSPECIFIED:eu-south | 7.409 | 1086 | 61.2 | non-US |
| M2 exact-window mmap | im-51.json | UNSPECIFIED:eu-north | 7.228 | 1113 | 55.1 | non-US |
| M2 exact-window mmap | im-58.json | GCP:europe-west9 | 7.653 | 1051 | 65.3 | non-US |
| M2 exact-window mmap | im-63.json | UNSPECIFIED:eu-north | 7.742 | 1039 | 56.7 | non-US |
| M2 exact-window mmap | im-67.json | UNSPECIFIED:eu-north | 7.457 | 1079 | 72.7 | non-US |
| M2 exact-window mmap | im-74.json | UNSPECIFIED:CANADA-2 | 7.084 | 1136 | 78.5 | non-US |
| M2 exact-window mmap | im-87.json | UNSPECIFIED:us-south | 6.234 | 1290 | 78.8 | singleton US region |
| M2 exact-window mmap | im-94.json | UNSPECIFIED:eu-north | 7.367 | 1092 | 60.5 | non-US |
| preadv QD4/64/4ms (frozen) | im-00.json | UNSPECIFIED:eu-north | 6.680 | 1204 | 53.0 | non-US |
| preadv QD4/64/4ms (frozen) | im-01.json | UNSPECIFIED:eu-north | 6.882 | 1169 | 58.9 | non-US |
| preadv QD4/64/4ms (frozen) | im-03.json | UNSPECIFIED:eu-north | 6.949 | 1158 | 57.8 | non-US |
| preadv QD4/64/4ms (frozen) | im-05.json | UNSPECIFIED:eu-north | 6.951 | 1157 | 54.5 | non-US |
| preadv QD4/64/4ms (frozen) | im-07.json | UNSPECIFIED:eu-north | 6.908 | 1165 | 59.6 | non-US |
| preadv QD4/64/4ms (frozen) | im-08.json | UNSPECIFIED:eu-north | 2.807 | 2866 | 193.4 | non-US |
| preadv QD4/64/4ms (frozen) | im-10.json | UNSPECIFIED:eu-north1 | 2.361 | 3407 | 182.9 | non-US |
| preadv QD4/64/4ms (frozen) | im-12.json | UNSPECIFIED:eu-north | 5.795 | 1388 | 70.1 | non-US |
| preadv QD4/64/4ms (frozen) | im-20.json | GCP:us-east | 5.927 | 1357 | 68.6 | singleton US region |
| preadv QD4/64/4ms (frozen) | im-21.json | GCP:us-west4 | 6.067 | 1326 | 70.2 | singleton US region |
| preadv QD4/64/4ms (frozen) | im-22.json | UNSPECIFIED:CANADA-2 | 6.669 | 1206 | 58.9 | non-US |
| preadv QD4/64/4ms (frozen) | im-38.json | GCP:ap-northeast | 2.852 | 2820 | 194.2 | non-US |
| preadv QD4/64/4ms (frozen) | im-43.json | UNSPECIFIED:eu-north | 7.055 | 1140 | 55.7 | non-US |
| preadv QD4/64/4ms (frozen) | im-48.json | UNSPECIFIED:eu-north | 6.669 | 1206 | 63.5 | non-US |
| preadv QD4/64/4ms (frozen) | im-53.json | UNSPECIFIED:eu-north | 6.681 | 1204 | 60.6 | non-US |

