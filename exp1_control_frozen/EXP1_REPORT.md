# Experiment 1 — self-service fast allocator vs static (QD4 / 64 MiB)

- treatment (frozen control): **42** self-service runs (im-00 = the qualifying >5 GB/s smoke, then first 41 valid non-Odin by slot)
- baseline: **42** most recent valid non-Odin static QD4/64 controls (no new static runs)
- Odin excluded from both arms; provider+region preserved per run.

## Main A/B

| arm | n | GB/s median | mean | p10 | p90 | best | worst | wall median | wall mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| self-service (new control) | 42 | 5.818 | 5.529 | 3.736 | 6.905 | 7.076 | 2.361 | 1383 | 1566 |
| static QD4/64 (baseline) | 42 | 6.015 | 5.852 | 5.276 | 6.445 | 7.194 | 3.060 | 1337 | 1398 |

- self-service median delta vs static: **-0.197 GB/s (-3.3%)**

## Read latency (physical preadv)

| arm | median | p95 | p99 | max | >=250 | >=500 | >=1000 |
|---|---:|---:|---:|---:|---:|---:|---:|
| self-service | 43.87 | 95.60 | 134.70 | 220.5 | 0 | 0 | 0 |
| static | 42.41 | 58.86 | 78.92 | 421.9 | 2 | 0 | 0 |

## Completion -> next-start statistics (the manager-bubble metric)

| arm | exit->next enter median ms | p90 | p99 |
|---|---:|---:|---:|
| self-service | 0.1095 | 2.7999 | 7.3524 |
| static | 0.0779 | 3.0965 | 7.1332 |

Reference from the pre-implementation telemetry audit (Exp 1a):
static internal loop 0.0788 ms; old greedy manager allocator 1.4290 ms.

## Provider-stratified medians (GB/s)

| provider | self-service n | med | static n | med | delta |
|---|---:|---:|---:|---:|---:|
| GCP | 9 | 5.999 | 29 | 6.058 | -0.060 |
| OCI | 12 | 5.442 | 8 | 5.284 | +0.157 |
| UNSPECIFIED | 21 | 5.795 | 5 | 6.630 | -0.835 |

## Region-stratified (>=3 runs in either arm)

| region | self-service n | med | static n | med |
|---|---:|---:|---:|---:|
| eu-north | 10 | 6.781 | 3 | 7.066 |
| us-ashburn-1 | 9 | 5.487 | 0 | - |
| us-central | 10 | 4.857 | 8 | 5.343 |
| us-chicago-1 | 0 | - | 4 | 5.197 |
| us-east | 1 | 5.927 | 5 | 5.525 |
| us-west | 8 | 5.985 | 10 | 6.064 |
| us-west1 | 0 | - | 10 | 6.179 |

## Self-service control — one row per run

| run | provider/region | GB/s | wall ms | preadv med | max | amp | maxQD | minGap | exact |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| im-00.json | UNSPECIFIED:eu-north | 6.680 | 1204 | 38.34 | 53.0 | 1.000 | 4 | 4.062 | Y |
| im-01.json | UNSPECIFIED:eu-north | 6.882 | 1169 | 37.36 | 58.9 | 1.000 | 4 | 4.085 | Y |
| im-02.json | UNSPECIFIED:us-west | 5.252 | 1532 | 49.70 | 85.2 | 1.000 | 4 | 4.019 | Y |
| im-03.json | UNSPECIFIED:eu-north | 6.949 | 1158 | 36.89 | 57.8 | 1.000 | 4 | 4.056 | Y |
| im-04.json | UNSPECIFIED:us-west | 5.971 | 1347 | 41.45 | 78.0 | 1.000 | 4 | 4.013 | Y |
| im-05.json | UNSPECIFIED:eu-north | 6.951 | 1157 | 36.52 | 54.5 | 1.000 | 4 | 4.054 | Y |
| im-07.json | UNSPECIFIED:eu-north | 6.908 | 1165 | 37.14 | 59.6 | 1.000 | 4 | 4.127 | Y |
| im-08.json | UNSPECIFIED:eu-north | 2.807 | 2866 | 80.52 | 193.4 | 1.000 | 4 | 4.078 | Y |
| im-09.json | OCI:us-central | 5.977 | 1346 | 41.94 | 72.9 | 1.000 | 4 | 4.023 | Y |
| im-10.json | UNSPECIFIED:eu-north1 | 2.361 | 3407 | 111.40 | 182.9 | 1.000 | 4 | 4.074 | Y |
| im-11.json | UNSPECIFIED:us-central | 5.375 | 1497 | 46.25 | 72.5 | 1.000 | 4 | 4.087 | Y |
| im-12.json | UNSPECIFIED:eu-north | 5.795 | 1388 | 43.83 | 70.1 | 1.000 | 4 | 4.102 | Y |
| im-15.json | OCI:us-central | 2.800 | 2873 | 94.43 | 220.5 | 1.000 | 4 | 4.073 | Y |
| im-17.json | UNSPECIFIED:us-central | 4.105 | 1960 | 63.71 | 108.0 | 1.000 | 4 | 4.157 | Y |
| im-18.json | GCP:us-west | 6.519 | 1234 | 39.50 | 55.8 | 1.000 | 4 | 4.044 | Y |
| im-20.json | GCP:us-east | 5.927 | 1357 | 42.63 | 68.6 | 1.000 | 4 | 4.007 | Y |
| im-21.json | GCP:us-west4 | 6.067 | 1326 | 40.66 | 70.2 | 1.000 | 4 | 4.022 | Y |
| im-22.json | UNSPECIFIED:CANADA-2 | 6.669 | 1206 | 38.23 | 58.9 | 1.000 | 4 | 4.029 | Y |
| im-23.json | OCI:us-central | 5.003 | 1608 | 51.69 | 78.6 | 1.000 | 4 | 4.018 | Y |
| im-24.json | UNSPECIFIED:us-central | 5.715 | 1408 | 44.99 | 76.1 | 1.000 | 4 | 4.075 | Y |
| im-25.json | OCI:us-ashburn-1 | 6.063 | 1327 | 40.11 | 59.7 | 1.000 | 4 | 4.116 | Y |
| im-26.json | UNSPECIFIED:us-central | 4.710 | 1708 | 55.57 | 82.7 | 1.000 | 4 | 4.066 | Y |
| im-27.json | OCI:us-ashburn-1 | 5.623 | 1431 | 46.17 | 69.5 | 1.000 | 4 | 4.012 | Y |
| im-28.json | UNSPECIFIED:us-central | 5.482 | 1468 | 47.50 | 66.8 | 1.000 | 4 | 4.031 | Y |
| im-29.json | OCI:us-ashburn-1 | 5.396 | 1491 | 46.92 | 64.0 | 1.000 | 4 | 4.101 | Y |
| im-31.json | OCI:us-ashburn-1 | 5.191 | 1550 | 48.93 | 81.5 | 1.000 | 4 | 4.083 | Y |
| im-33.json | OCI:us-ashburn-1 | 6.165 | 1305 | 39.84 | 62.9 | 1.000 | 4 | 4.014 | Y |
| im-35.json | OCI:us-ashburn-1 | 5.487 | 1466 | 46.98 | 65.0 | 1.000 | 4 | 4.030 | Y |
| im-38.json | GCP:ap-northeast | 2.852 | 2820 | 89.11 | 194.2 | 1.000 | 4 | 4.004 | Y |
| im-42.json | UNSPECIFIED:us-central | 3.765 | 2137 | 68.52 | 106.5 | 1.000 | 4 | 4.034 | Y |
| im-43.json | UNSPECIFIED:eu-north | 7.055 | 1140 | 36.78 | 55.7 | 1.000 | 4 | 4.096 | Y |
| im-46.json | GCP:us-west | 6.066 | 1326 | 41.66 | 58.7 | 1.000 | 4 | 4.062 | Y |
| im-48.json | UNSPECIFIED:eu-north | 6.669 | 1206 | 38.93 | 63.5 | 1.000 | 4 | 4.102 | Y |
| im-50.json | UNSPECIFIED:us-central | 3.733 | 2155 | 68.30 | 118.9 | 1.000 | 4 | 4.065 | Y |
| im-52.json | GCP:us-west | 5.999 | 1341 | 41.65 | 69.9 | 1.000 | 4 | 4.046 | Y |
| im-53.json | UNSPECIFIED:eu-north | 6.681 | 1204 | 38.24 | 60.6 | 1.000 | 4 | 4.077 | Y |
| im-54.json | GCP:us-west | 7.076 | 1137 | 37.04 | 53.8 | 1.000 | 4 | 4.037 | Y |
| im-55.json | GCP:us-west | 5.842 | 1377 | 43.90 | 65.9 | 1.000 | 4 | 4.044 | Y |
| im-56.json | OCI:us-ashburn-1 | 4.904 | 1640 | 53.23 | 64.6 | 1.000 | 4 | 4.033 | Y |
| im-57.json | GCP:us-west | 5.658 | 1422 | 43.68 | 69.7 | 1.000 | 4 | 4.085 | Y |
| im-58.json | OCI:us-ashburn-1 | 6.069 | 1325 | 41.21 | 60.8 | 1.000 | 4 | 4.006 | Y |
| im-60.json | OCI:us-ashburn-1 | 5.031 | 1599 | 51.78 | 68.4 | 1.000 | 4 | 4.034 | Y |

## Invariant check on the frozen 42

- violations: **0** (all 42 clean)

