# P (preadv) vs M2 (exact-window mmap) — same-time interleaved

Both engines ran in the **same time window**, alternating on the predetermined balanced
schedule `[P,M2,M2,P,P,M2]`, so region/placement exposure is interleaved rather than
time-separated. Everything else identical: CPU source-only, H100 host for placement
comparability with the GPU untouched, 4 processes, QD4, 64 MiB, 4 ms floor, same file,
same self-service scheduler, exact full-file coverage. No toucher, no M0, no M1, no CUDA,
no H2D, no O_DIRECT, no new QD/block size/pacing.

M2 operation cost is measured correctly as **mapping + source access/copy**
(`map_ms + preadv_ms`). MAP_POPULATE remains part of the implementation but is inert here;
this is a mapping-lifecycle variant, **not** eager population.

Counting rule: US only; singleton US regions excluded. Excluded runs retained below.

## Main table

| source | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | 30 | 5.904 | 5.583 | 4.188 | 6.236 | 6.394 | 3.594 | 1363 | 1473 |
| exact-window mmap (M2) | 30 | 6.503 | 6.466 | 5.401 | 7.337 | 8.247 | 4.265 | 1237 | 1266 |

## Tail table

| source | ops | median ms | p95 | p99 | worst | >=250 | >=500 | >=1s | >=2s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| preadv (P) | 3602 | 43.91 | 69.99 | 92.26 | 692.2 | 4 | 1 | 0 | 0 |
| M2 | 3600 | 38.05 | 57.44 | 89.49 | 949.6 | 9 | 6 | 0 | 0 |

## Outliers (provider:region on every one)

| source | kind | run | provider:region | GB/s | wall ms | worst op ms |
|---|---|---|---|---:|---:|---:|
| preadv (P) | bottom-decile GB/s | im-22.json | UNSPECIFIED:us-central | 3.842 | 2094 | 104.1 |
| preadv (P) | bottom-decile GB/s | im-23.json | UNSPECIFIED:us-central | 4.044 | 1989 | 113.7 |
| preadv (P) | bottom-decile GB/s | im-37.json | UNSPECIFIED:us-central | 3.594 | 2238 | 119.3 |
| preadv (P) | worst run | im-37.json | UNSPECIFIED:us-central | 3.594 | 2238 | 119.3 |
| M2 | bottom-decile GB/s | im-44.json | UNSPECIFIED:us-central | 5.100 | 1577 | 114.4 |
| M2 | bottom-decile GB/s | im-74.json | GCP:us-west | 4.265 | 1886 | 949.6 |
| M2 | bottom-decile GB/s | im-99.json | UNSPECIFIED:us-central | 5.201 | 1547 | 108.0 |
| M2 | worst run | im-74.json | GCP:us-west | 4.265 | 1886 | 949.6 |

Every operation at or above the thresholds:

| source | run | provider:region | block | offset | op ms |
|---|---|---|---:|---:|---:|
| P | im-43.json | GCP:us-east | 30 | 2013265920 | 486.9 |
| P | im-43.json | GCP:us-east | 90 | 6039797760 | 692.2 |
| P | im-43.json | GCP:us-east | 61 | 4093640704 | 372.4 |
| P | im-43.json | GCP:us-east | 90 | 6039797760 | 262.4 |
| M2 | im-24.json | GCP:us-east | 62 | 4160749568 | 388.9 |
| M2 | im-24.json | GCP:us-east | 90 | 6039797760 | 540.6 |
| M2 | im-42.json | GCP:us-east | 90 | 6039797760 | 500.3 |
| M2 | im-42.json | GCP:us-east | 30 | 2013265920 | 517.4 |
| M2 | im-50.json | GCP:us-east | 90 | 6039797760 | 458.9 |
| M2 | im-50.json | GCP:us-east | 62 | 4160749568 | 362.8 |
| M2 | im-74.json | GCP:us-west | 60 | 4026531840 | 920.4 |
| M2 | im-74.json | GCP:us-west | 90 | 6039797760 | 949.6 |
| M2 | im-74.json | GCP:us-west | 11 | 738197504 | 530.6 |

## Per-region

| region | preadv n/median | M2 n/median | delta % | preadv tails | M2 tails |
|---|---|---|---:|---:|---:|
| us-ashburn-1 | 1/5.049 | 3/7.007 | +38.8% | 0 | 0 |
| us-central | 5/4.044 | 3/5.201 | +28.6% | 0 | 0 |
| us-east | 5/5.925 | 8/6.196 | +4.6% | 4 | 6 |
| us-east4 | 1/5.427 | 0/- | - | 0 | 0 |
| us-west | 18/5.955 | 16/6.766 | +13.6% | 0 | 3 |

## Excluded runs (retained)

| source | run | provider:region | GB/s | wall ms | worst op ms | reason |
|---|---|---|---:|---:|---:|---|
| P | im-10.json | UNSPECIFIED:US-1 | 6.036 | 1333 | 65.7 | non-US |
| P | im-11.json | OCI:us-chicago-1 | 5.541 | 1452 | 85.8 | singleton US region |
| P | im-13.json | UNSPECIFIED:eu-north | 6.898 | 1166 | 51.8 | non-US |
| P | im-19.json | UNSPECIFIED:odin | 6.845 | 1175 | 63.9 | Odin |
| P | im-25.json | UNSPECIFIED:eu-north | 6.740 | 1194 | 57.1 | non-US |
| P | im-29.json | UNSPECIFIED:eu-north | 6.453 | 1247 | 59.6 | non-US |
| P | im-31.json | UNSPECIFIED:eu-north | 6.989 | 1151 | 56.6 | non-US |
| P | im-58.json | UNSPECIFIED:denver | 5.024 | 1601 | 94.1 | non-US |
| P | im-64.json | UNSPECIFIED:odin | 6.779 | 1187 | 56.2 | Odin |
| P | im-65.json | UNSPECIFIED:eu-north | 6.772 | 1188 | 58.4 | non-US |
| P | im-67.json | UNSPECIFIED:odin | 6.923 | 1162 | 65.2 | Odin |
| P | im-71.json | UNSPECIFIED:odin | 6.796 | 1184 | 56.1 | Odin |
| P | im-73.json | UNSPECIFIED:odin | 7.083 | 1136 | 56.7 | Odin |
| P | im-77.json | UNSPECIFIED:odin | 6.663 | 1207 | 56.9 | Odin |
| P | im-88.json | UNSPECIFIED:odin | 6.880 | 1169 | 59.7 | Odin |
| P | im-91.json | OCI:us-central | 5.711 | 1409 | 64.1 | singleton US region |
| P | im-94.json | UNSPECIFIED:us-central | 5.640 | 1426 | 86.8 | singleton US region |
| P | im-95.json | UNSPECIFIED:us-west | 5.276 | 1525 | 78.3 | singleton US region |
| P | im-97.json | UNSPECIFIED:us-central | 4.578 | 1757 | 121.8 | singleton US region |
| P | im-100.json | OCI:us-ashburn-1 | 5.513 | 1459 | 76.5 | singleton US region |
| P | im-101.json | UNSPECIFIED:odin | 6.647 | 1210 | 57.7 | Odin |
| P | im-103.json | UNSPECIFIED:us-central | 4.597 | 1750 | 103.7 | singleton US region |
| P | im-106.json | GCP:us-west | 5.962 | 1349 | 76.3 | singleton US region |
| P | im-107.json | GCP:us-west | 6.256 | 1286 | 56.2 | singleton US region |
| P | im-109.json | GCP:us-west | 6.858 | 1173 | 53.1 | singleton US region |
| P | im-112.json | GCP:us-east4 | 4.875 | 1650 | 650.8 | singleton US region |
| P | im-113.json | GCP:asia-northeast1 | 5.515 | 1459 | 62.7 | non-US |
| P | im-115.json | GCP:us-west | 6.574 | 1224 | 62.5 | singleton US region |
| P | im-118.json | GCP:us-east | 5.988 | 1344 | 71.8 | singleton US region |
| P | im-119.json | UNSPECIFIED:us-central | 4.282 | 1879 | 102.8 | singleton US region |
| M2 | im-09.json | UNSPECIFIED:odin | 7.597 | 1059 | 73.3 | Odin |
| M2 | im-14.json | UNSPECIFIED:denver | 5.124 | 1570 | 113.8 | non-US |
| M2 | im-18.json | UNSPECIFIED:eu-north | 7.528 | 1069 | 75.5 | non-US |
| M2 | im-20.json | UNSPECIFIED:odin | 7.319 | 1099 | 56.3 | Odin |
| M2 | im-21.json | UNSPECIFIED:eu-south | 7.342 | 1096 | 65.6 | non-US |
| M2 | im-27.json | UNSPECIFIED:eu-north | 7.257 | 1109 | 56.6 | non-US |
| M2 | im-33.json | UNSPECIFIED:odin | 8.222 | 978 | 61.0 | Odin |
| M2 | im-38.json | GCP:europe-west9 | 5.787 | 1390 | 89.7 | non-US |
| M2 | im-39.json | GCP:ap-south | 6.136 | 1311 | 90.3 | non-US |
| M2 | im-62.json | UNSPECIFIED:odin | 7.546 | 1066 | 71.2 | Odin |
| M2 | im-69.json | UNSPECIFIED:odin | 7.234 | 1112 | 72.9 | Odin |
| M2 | im-72.json | UNSPECIFIED:eu-north | 7.950 | 1012 | 62.2 | non-US |
| M2 | im-75.json | UNSPECIFIED:odin | 8.021 | 1003 | 57.9 | Odin |
| M2 | im-81.json | UNSPECIFIED:odin | 7.667 | 1049 | 66.8 | Odin |
| M2 | im-86.json | UNSPECIFIED:odin | 7.359 | 1093 | 70.0 | Odin |
| M2 | im-87.json | UNSPECIFIED:odin | 7.303 | 1102 | 78.5 | Odin |
| M2 | im-90.json | OCI:us-chicago-1 | 5.396 | 1491 | 70.4 | singleton US region |
| M2 | im-92.json | GCP:ap-south | 7.067 | 1138 | 69.0 | non-US |
| M2 | im-93.json | UNSPECIFIED:eu-north | 1.306 | 6161 | 5697.5 | non-US |
| M2 | im-96.json | UNSPECIFIED:odin | 7.270 | 1107 | 67.7 | Odin |
| M2 | im-98.json | UNSPECIFIED:odin | 8.192 | 982 | 81.1 | Odin |
| M2 | im-104.json | GCP:us-west | 4.302 | 1870 | 827.1 | singleton US region |
| M2 | im-105.json | GCP:us-west | 6.939 | 1159 | 70.1 | singleton US region |
| M2 | im-108.json | GCP:us-west | 6.576 | 1223 | 58.5 | singleton US region |
| M2 | im-110.json | GCP:asia-northeast1 | 6.281 | 1281 | 68.6 | non-US |
| M2 | im-111.json | GCP:us-east | 6.043 | 1331 | 382.4 | singleton US region |
| M2 | im-114.json | GCP:us-east4 | 6.196 | 1298 | 81.8 | singleton US region |
| M2 | im-116.json | GCP:us-west | 6.661 | 1208 | 65.6 | singleton US region |
| M2 | im-117.json | AZURE:us-central | 6.281 | 1281 | 74.6 | singleton US region |
| M2 | im-120.json | UNSPECIFIED:us-central | 4.898 | 1643 | 115.4 | singleton US region |

