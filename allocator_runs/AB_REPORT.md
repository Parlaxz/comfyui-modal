# Greedy allocator vs static ~2 GB-per-reader — A/B

Treatment: 30 fresh allocator runs (`allocator_runs/`, 128 MiB blocks, QD4, 4 ms).
Control:   30 most-recent valid non-Odin static runs (64 MiB blocks, QD4, 4 ms).

> **Block size differs by design.** Control = 64 MiB, treatment = 128 MiB as specified.
> The comparison therefore includes BOTH scheduler and block-size differences.
> A 64 MiB control run does 120 reads; a 128 MiB treatment run does 60.

Control pool composition (by source dir): {'witness_runs': 30}

## Control files used (frozen, most-recent by mtime)

- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid8.json`  (us-east4)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid6.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid5.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid4.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid3.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid2.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-11-invalid1.json`  (CANADA-2)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid30.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid29.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid28.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid27.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid26.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid25.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid24.json`  (us-chicago-1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid23.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid22.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid21.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid20.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid19.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid18.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid17.json`  (us-east)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid16.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid15.json`  (us-west)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid12.json`  (us-west1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid11.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid10.json`  (eu-north)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid9.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid8.json`  (us-central)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid7.json`  (us-chicago-1)
- `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\witness_runs\im-10-invalid6.json`  (us-east)

## Main summary

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static (control) | 30 | 6.015 | 5.829 | 5.292 | 6.425 | 7.194 | 3.060 | 1337 | 1408 |
| allocator (treatment) | 30 | 5.300 | 5.422 | 4.723 | 6.785 | 7.143 | 2.814 | 1518 | 1534 |

## Tail / read summary

| arm | preadv median | p95 | p99 | worst | >=250ms | >=500ms | >=1000ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| static (control) | 41.99 | 54.25 | 62.36 | 248.8 | 0 | 0 | 0 |
| allocator (treatment) | 95.78 | 115.57 | 119.98 | 388.3 | 18 | 0 | 0 |

## Treatment scheduler detail

| metric | value |
|---|---:|
| rescue-eligible blocks (total across runs) | 2 |
| rescue launches | 2 |
| rescue wins | 1 |
| runs with >=1 rescue | 1 / 30 |
| ms saved per win | median=1.33 max=1.33 (n=1) |
| physical read amplification | median=1.0000 max=1.0333 |
| max observed physical QD | max=4 (structural 4) |
| min global start spacing | min=4.0022 ms (configured 4.0) |
| idle time from lack of work | total=2952.1 ms across all runs |

## Provider-stratified (where both arms overlap)

| provider | arm | n | GB/s median | GB/s mean | wall median |
|---|---|---:|---:|---:|---:|
| gcp | static | 23 | 6.058 | 5.958 | 1328 |
| gcp | allocator | 17 | 5.250 | 5.247 | 1532 |
| oci | static | 5 | 5.293 | 4.828 | 1520 |
| oci | allocator | 4 | 5.175 | 5.124 | 1555 |
| unspecified | static | 2 | 6.850 | 6.850 | 1177 |
| unspecified | allocator | 8 | 6.090 | 5.727 | 1323 |

## TREATMENT — one row per run

| run | provider/region | GB/s | wall ms | worst preadv ms | rescues | wins | physical reads | reader block counts |
|---|---|---:|---:|---:|---:|---:|---:|---|
| im-33.json | azure:us-west | 7.143 | 1126 | 80.1 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-44.json | unspecified:eu-north | 7.059 | 1140 | 90.0 | 0 | 0 | 60 | [16, 14, 15, 15] |
| im-38.json | unspecified:eu-north | 6.789 | 1185 | 86.3 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-40.json | unspecified:eu-north | 6.784 | 1186 | 88.3 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-42.json | unspecified:eu-north | 6.304 | 1276 | 95.9 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-29.json | gcp:us-east | 5.893 | 1365 | 112.3 | 0 | 0 | 60 | [16, 14, 15, 15] |
| im-05.json | unspecified:london | 5.877 | 1369 | 106.8 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-26.json | gcp:us-east | 5.873 | 1370 | 109.2 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-30.json | gcp:us-east4 | 5.827 | 1381 | 111.6 | 0 | 0 | 60 | [15, 16, 15, 14] |
| im-43.json | oci:us-ashburn-1 | 5.624 | 1430 | 125.5 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-27.json | gcp:us-east | 5.624 | 1430 | 111.5 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-37.json | gcp:us-east | 5.515 | 1459 | 107.8 | 0 | 0 | 60 | [15, 16, 14, 15] |
| im-12.json | unspecified:US-1 | 5.447 | 1477 | 111.7 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-16.json | gcp:us-east4 | 5.425 | 1483 | 133.2 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-04.json | gcp:us-central | 5.324 | 1511 | 118.5 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-14.json | gcp:us-west | 5.276 | 1525 | 126.8 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-13.json | gcp:us-west | 5.250 | 1532 | 116.2 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-45.json | oci:us-ashburn-1 | 5.223 | 1540 | 121.5 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-07.json | gcp:us-east4 | 5.191 | 1550 | 132.7 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-15.json | gcp:us-east4 | 5.175 | 1555 | 135.4 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-08.json | oci:us-chicago-1 | 5.127 | 1569 | 123.2 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-28.json | gcp:us-east4 | 5.079 | 1584 | 126.9 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-24.json | gcp:us-east | 5.061 | 1590 | 222.3 | 0 | 0 | 60 | [16, 16, 14, 14] |
| im-23.json | gcp:us-east | 5.039 | 1597 | 146.2 | 0 | 0 | 60 | [14, 15, 16, 15] |
| im-31.json | gcp:us-east | 4.975 | 1617 | 196.8 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-18.json | gcp:us-east | 4.899 | 1642 | 146.3 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-06.json | unspecified:uk | 4.745 | 1696 | 164.2 | 0 | 0 | 60 | [15, 15, 15, 15] |
| im-25.json | oci:us-chicago-1 | 4.524 | 1778 | 158.2 | 0 | 0 | 60 | [15, 16, 14, 15] |
| im-03.json | gcp:us-central | 3.782 | 2198 | 388.3 | 2 | 1 | 62 | [15, 15, 15, 15] |
| im-17.json | unspecified:eu-north | 2.814 | 2859 | 265.9 | 0 | 0 | 60 | [15, 15, 15, 15] |

## CONTROL — one row per run

| run | provider/region | GB/s | wall ms | worst preadv ms | rescues | wins | physical reads | reader block counts |
|---|---|---:|---:|---:|---:|---:|---:|---|
| im-10-invalid10.json | unspecified:eu-north | 7.194 | 1118 | 51.0 | - | - | - | - |
| im-11-invalid1.json | unspecified:CANADA-2 | 6.506 | 1236 | 59.0 | - | - | - | - |
| im-10-invalid20.json | gcp:us-west1 | 6.447 | 1248 | 62.3 | - | - | - | - |
| im-10-invalid6.json | gcp:us-east | 6.422 | 1253 | 69.2 | - | - | - | - |
| im-10-invalid30.json | gcp:us-west | 6.252 | 1287 | 68.6 | - | - | - | - |
| im-10-invalid18.json | gcp:us-west1 | 6.250 | 1287 | 60.8 | - | - | - | - |
| im-10-invalid15.json | gcp:us-west | 6.248 | 1288 | 56.9 | - | - | - | - |
| im-10-invalid25.json | gcp:us-west1 | 6.228 | 1292 | 60.7 | - | - | - | - |
| im-10-invalid12.json | gcp:us-west1 | 6.196 | 1299 | 61.2 | - | - | - | - |
| im-11-invalid2.json | gcp:us-west | 6.120 | 1314 | 68.5 | - | - | - | - |
| im-10-invalid29.json | gcp:us-west | 6.097 | 1320 | 61.7 | - | - | - | - |
| im-11-invalid4.json | gcp:us-west | 6.070 | 1325 | 68.0 | - | - | - | - |
| im-10-invalid16.json | gcp:us-west1 | 6.062 | 1327 | 60.6 | - | - | - | - |
| im-10-invalid19.json | gcp:us-west | 6.058 | 1328 | 65.1 | - | - | - | - |
| im-11-invalid5.json | gcp:us-central | 6.016 | 1337 | 67.7 | - | - | - | - |
| im-10-invalid22.json | gcp:us-west1 | 6.015 | 1338 | 61.9 | - | - | - | - |
| im-11-invalid6.json | gcp:us-west | 6.008 | 1339 | 68.1 | - | - | - | - |
| im-10-invalid28.json | gcp:us-west1 | 5.752 | 1399 | 62.6 | - | - | - | - |
| im-10-invalid21.json | gcp:us-west | 5.737 | 1402 | 62.3 | - | - | - | - |
| im-10-invalid9.json | gcp:us-central | 5.672 | 1418 | 78.6 | - | - | - | - |
| im-11-invalid8.json | gcp:us-east4 | 5.600 | 1437 | 64.2 | - | - | - | - |
| im-10-invalid23.json | gcp:us-west | 5.562 | 1446 | 62.4 | - | - | - | - |
| im-10-invalid26.json | gcp:us-west | 5.532 | 1454 | 65.5 | - | - | - | - |
| im-10-invalid17.json | gcp:us-east | 5.420 | 1484 | 74.5 | - | - | - | - |
| im-11-invalid3.json | oci:us-central | 5.392 | 1492 | 74.2 | - | - | - | - |
| im-10-invalid24.json | oci:us-chicago-1 | 5.309 | 1515 | 76.3 | - | - | - | - |
| im-10-invalid8.json | oci:us-central | 5.293 | 1520 | 65.5 | - | - | - | - |
| im-10-invalid27.json | gcp:us-central | 5.276 | 1525 | 63.3 | - | - | - | - |
| im-10-invalid7.json | oci:us-chicago-1 | 5.085 | 1582 | 78.7 | - | - | - | - |
| im-10-invalid11.json | oci:us-central | 3.060 | 2629 | 248.8 | - | - | - | - |

