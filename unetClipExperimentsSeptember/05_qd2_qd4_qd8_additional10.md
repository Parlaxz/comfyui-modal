# September UNET/CLIP Experiment 05: 10 Additional Runs Per Model/QD

STATUS=COMPLETE
DECISION_METRIC=SOURCE_WALL_MS
SECONDARY_METRIC=FILE_TO_CUDA_WALL_MS

## Scope And Decision

This report adds 10 eligible serial observations for each of CLIP QD2/QD4/QD8 and UNET QD2/QD4/QD8. The prior four-run-per-cell cohort is included as a combined 14-run reference below.
Lower wall time is better.

## Additional-Only Median Gains

| model | metric | QD2 -> QD4 | QD4 -> QD8 | QD2 -> QD8 |
|---|---|---:|---:|---:|
| CLIP | SOURCE_WALL_MS | -24.562% | -7.572% | -33.994% |
| CLIP | FILE_TO_CUDA_WALL_MS | -24.652% | -7.149% | -33.564% |
| UNET | SOURCE_WALL_MS | -26.871% | -9.253% | -38.610% |
| UNET | FILE_TO_CUDA_WALL_MS | -26.594% | -9.086% | -38.096% |

The additional-only gains above use exactly 10 valid observations per model/QD cell.

## Combined 14-Run Median Gains

| model | metric | QD2 -> QD4 | QD4 -> QD8 | QD2 -> QD8 |
|---|---|---:|---:|---:|
| CLIP | SOURCE_WALL_MS | -25.088% | -4.138% | -30.264% |
| CLIP | FILE_TO_CUDA_WALL_MS | -25.297% | -3.752% | -29.999% |
| UNET | SOURCE_WALL_MS | -25.687% | -8.994% | -36.991% |
| UNET | FILE_TO_CUDA_WALL_MS | -25.490% | -8.991% | -36.774% |

## Result Summary

The additional campaign retained 61 attempts: 60 eligible observations and 1 invalid proof attempt. The invalid attempt is retained and excluded from all statistics.
Provider/region routing varied between GCP `us-east1` and GCP `us-east4`; all additional observations used image `im-VEOotGdbrzgtTFBFZJrYQM`.

## Additional-Only Statistics

Effective GB/s = source bytes / median wall time, using decimal GB.

| model | QD | metric | R5 | R6 | R7 | R8 | R9 | R10 | R11 | R12 | R13 | R14 | mean | median | sample SD | CV | effective GB/s |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 2 | SOURCE_WALL_MS | 1076.102 | 920.017 | 950.238 | 1050.245 | 1039.203 | 1117.855 | 1142.647 | 891.675 | 915.017 | 963.434 | 1006.643 | 1001.319 | 89.948 | 0.089355 | 8.034343 |
| CLIP | 2 | FILE_TO_CUDA_WALL_MS | 1081.484 | 925.208 | 960.753 | 1056.415 | 1045.687 | 1123.985 | 1148.981 | 902.414 | 925.866 | 973.871 | 1014.466 | 1009.779 | 88.330 | 0.087071 | 7.967028 |
| CLIP | 4 | SOURCE_WALL_MS | 1155.468 | 1279.317 | 1305.380 | 1297.464 | 1341.323 | 949.889 | 1215.209 | 1170.406 | 1349.207 | 1047.266 | 1211.093 | 1247.263 | 132.024 | 0.109012 | 6.450071 |
| CLIP | 4 | FILE_TO_CUDA_WALL_MS | 1168.641 | 1299.203 | 1313.744 | 1303.579 | 1358.845 | 957.549 | 1218.218 | 1184.394 | 1352.166 | 1053.630 | 1220.997 | 1258.711 | 133.021 | 0.108944 | 6.391410 |
| CLIP | 8 | SOURCE_WALL_MS | 1262.518 | 1438.049 | 1369.136 | 1090.569 | 1460.832 | 1309.869 | 1342.793 | 1290.757 | 1399.744 | 1340.624 | 1330.489 | 1341.708 | 105.033 | 0.078943 | 5.996039 |
| CLIP | 8 | FILE_TO_CUDA_WALL_MS | 1272.635 | 1452.368 | 1381.741 | 1098.240 | 1476.698 | 1315.188 | 1348.010 | 1296.611 | 1413.081 | 1349.386 | 1340.396 | 1348.698 | 107.513 | 0.080210 | 5.964965 |
| UNET | 2 | SOURCE_WALL_MS | 1550.996 | 1602.401 | 6015.151 | 1418.799 | 1449.927 | 1775.092 | 1578.943 | 1487.556 | 1395.117 | 1556.906 | 1983.089 | 1553.951 | 1420.928 | 0.716523 | 7.921625 |
| UNET | 2 | FILE_TO_CUDA_WALL_MS | 1561.440 | 1607.430 | 6020.561 | 1428.816 | 1459.505 | 1784.240 | 1584.719 | 1496.780 | 1404.698 | 1563.008 | 1991.120 | 1562.224 | 1419.959 | 0.713146 | 7.879677 |
| UNET | 4 | SOURCE_WALL_MS | 1939.933 | 2030.988 | 3658.831 | 2003.088 | 1692.532 | 1708.548 | 1678.711 | 3258.046 | 1837.197 | 2029.338 | 2183.721 | 1971.510 | 692.140 | 0.316954 | 6.243851 |
| UNET | 4 | FILE_TO_CUDA_WALL_MS | 1945.376 | 2037.467 | 3664.790 | 2010.001 | 1698.133 | 1711.772 | 1688.314 | 3264.660 | 1841.974 | 2032.600 | 2189.509 | 1977.688 | 692.309 | 0.316194 | 6.224346 |
| UNET | 8 | SOURCE_WALL_MS | 4667.485 | 1862.915 | 2120.727 | 1670.265 | 2074.105 | 2187.142 | 3255.489 | 2200.089 | 2257.984 | 1889.044 | 2418.525 | 2153.934 | 897.008 | 0.370891 | 5.715038 |
| UNET | 8 | FILE_TO_CUDA_WALL_MS | 4680.310 | 1868.105 | 2124.792 | 1675.255 | 2083.819 | 2189.959 | 3258.386 | 2202.888 | 2260.975 | 1894.805 | 2423.929 | 2157.375 | 898.908 | 0.370847 | 5.705923 |

## Combined 14-Run Statistics

The combined medians and dispersion use the prior 4 valid observations plus the 10 valid additional observations in each cell. The full prior four-run ledger remains in `05_qd2_qd4_qd8_closure.md`; the JSON report contains the combined observation records.

| model | QD | metric | n | mean | median | sample SD | CV | effective GB/s |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| CLIP | 2 | SOURCE_WALL_MS | 14 | 1411.198 | 1029.991 | 1284.855 | 0.910471 | 7.810689 |
| CLIP | 2 | FILE_TO_CUDA_WALL_MS | 14 | 1419.636 | 1038.644 | 1284.311 | 0.904676 | 7.745616 |
| CLIP | 4 | SOURCE_WALL_MS | 14 | 1730.481 | 1288.391 | 1525.577 | 0.881592 | 6.244174 |
| CLIP | 4 | FILE_TO_CUDA_WALL_MS | 14 | 1740.774 | 1301.391 | 1524.049 | 0.875500 | 6.181796 |
| CLIP | 8 | SOURCE_WALL_MS | 14 | 1714.749 | 1341.708 | 1422.524 | 0.829581 | 5.996039 |
| CLIP | 8 | FILE_TO_CUDA_WALL_MS | 14 | 1724.178 | 1350.225 | 1422.422 | 0.824986 | 5.958221 |
| UNET | 2 | SOURCE_WALL_MS | 14 | 2953.509 | 1567.925 | 2575.639 | 0.872061 | 7.851026 |
| UNET | 2 | FILE_TO_CUDA_WALL_MS | 14 | 2960.787 | 1573.863 | 2574.610 | 0.869570 | 7.821402 |
| UNET | 4 | SOURCE_WALL_MS | 14 | 2209.187 | 1970.675 | 692.379 | 0.313409 | 6.246498 |
| UNET | 4 | FILE_TO_CUDA_WALL_MS | 14 | 2214.562 | 1975.047 | 692.634 | 0.312763 | 6.232670 |
| UNET | 8 | SOURCE_WALL_MS | 14 | 2513.895 | 2147.918 | 971.741 | 0.386548 | 5.731047 |
| UNET | 8 | FILE_TO_CUDA_WALL_MS | 14 | 2520.113 | 2152.631 | 973.813 | 0.386416 | 5.718500 |

## Deployment And Fixed Contract

| field | value |
|---|---|
| worktree | `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal` |
| branch / HEAD | `TESTING2` / `f21b3ae29685abbc429813fadc32c8f41264c03e` |
| dirty worktree | true; pre-existing changes preserved |
| workspace / environment | Testing 7 / main |
| app | `sept-unetclip-05-qd-closure` |
| deployment | `https://modal.com/apps/testing7/main/deployed/sept-unetclip-05-qd-closure` |
| image | `im-VEOotGdbrzgtTFBFZJrYQM` |
| GPU | `rtx-pro-6000` |
| models Volume | `comfyui-models`, read-only at `/root/models` |
| source block / H2D target | 268435456 / 268435456 bytes |
| pinned resources | one 2 GiB arena, 8 logical 256 MiB slots, one dedicated H2D stream, fixed event set |
| aggregation | false |
| model construction / full Golden | false / not run |
| only variable | configured_qd / producer_count = 2, 4, 8 |

## Cohort Audit

- Requested: 60 additional observations; collected 61 attempts because CLIP QD8 R6 failed proof and was replaced by R15.
- Eligible: 60, exactly 10 per model/QD cell; all are serial and separately invoked.
- Eligible status: 60/60 `ok`; byte validation: 60/60 passed; proof: 60/60 `E27_SOURCE_MECHANISM_PROVEN=YES`; fallback count: zero in all 60.
- Distinct single-use container sessions: 60.
- Null `GPU_COPY_STREAM_SPAN_MS` values are preserved in the run ledger and JSON as `UNAVAILABLE`/null; no value was imputed.

## Invalid Additional Attempt

| attempt | status | proof | failed predicates | raw artifact |
|---|---|---|---|---|
| clip_qd8_R6 | ok | NO | fixed_contiguous_regions, fixed_ownership, monotonic_reads, coverage_exact, gaps, actual_syscall_qd_telemetry_complete, max_actual_source_inflight, source_total_wall_present, qd_occupancy_present, h2d_reconciliation_complete, quiescence_checkpoint_history, checkpoint_fields, bind_checkpoint, source_completion_checkpoint, final_completion_checkpoint, checkpoint_order, quiescence, required_evidence_persisted | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R6.json` |

This attempt is retained as evidence and excluded from the 60-run eligible cohort.

## Additional Run Ledger

All fields below are copied from the 60 eligible additional raw JSON artifacts. `UNAVAILABLE` is an observed null, not an imputation.

| run | model | QD | SOURCE_WALL_MS | FILE_TO_CUDA_WALL_MS | source bytes | reads | mean QD | max QD | syscall union ms | H2D wall ms | GPU active-copy ms | stream span ms | idle ms | fallback | proof | provider | region | raw artifact |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| clip_qd2_R5 | CLIP | 2 | 1076.102 | 1081.484 | 8044936192 | 31 | 1.933 | 2 | 1075.501 | 1019.189 | 143.472 | 1019.268 | 875.796 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R5.json` |
| unet_qd2_R5 | UNET | 2 | 1550.996 | 1561.440 | 12309817472 | 47 | 1.988 | 2 | 1550.996 | 1501.149 | 220.132 | 1501.008 | 1280.876 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R5.json` |
| clip_qd4_R5 | CLIP | 4 | 1155.468 | 1168.641 | 8044936192 | 33 | 3.547 | 4 | 1154.540 | 1112.215 | 211.802 | 1112.129 | 900.328 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R5.json` |
| unet_qd4_R5 | UNET | 4 | 1939.933 | 1945.376 | 12309817472 | 49 | 3.469 | 4 | 1938.460 | 1808.806 | 296.786 | 1808.844 | 1512.058 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R5.json` |
| clip_qd8_R5 | CLIP | 8 | 1262.518 | 1272.635 | 8044936192 | 37 | 3.545 | 7 | 1256.762 | 1223.572 | 429.838 | 1223.500 | 793.662 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R5.json` |
| unet_qd8_R5 | UNET | 8 | 4667.485 | 4680.310 | 12309817472 | 53 | 4.797 | 8 | 4656.849 | 4265.466 | 1315.769 | 4265.460 | 2949.692 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R5.json` |
| clip_qd2_R6 | CLIP | 2 | 920.017 | 925.208 | 8044936192 | 31 | 1.919 | 2 | 919.624 | 922.899 | 146.298 | 922.984 | 776.686 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R6.json` |
| unet_qd2_R6 | UNET | 2 | 1602.401 | 1607.430 | 12309817472 | 47 | 1.903 | 2 | 1601.501 | 1600.015 | 222.544 | 1599.995 | 1377.451 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R6.json` |
| clip_qd4_R6 | CLIP | 4 | 1279.317 | 1299.203 | 8044936192 | 33 | 3.506 | 4 | 1276.916 | 1268.107 | 249.222 | 1267.987 | 1018.765 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R6.json` |
| unet_qd4_R6 | UNET | 4 | 2030.988 | 2037.467 | 12309817472 | 49 | 3.610 | 4 | 2029.702 | 1997.331 | 349.623 | 1997.255 | 1647.632 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R6.json` |
| unet_qd8_R6 | UNET | 8 | 1862.915 | 1868.105 | 12309817472 | 53 | 4.804 | 8 | 1850.598 | 1748.232 | 306.848 | 1748.142 | 1441.295 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R6.json` |
| clip_qd2_R7 | CLIP | 2 | 950.238 | 960.753 | 8044936192 | 31 | 1.943 | 2 | 949.467 | 959.164 | 145.987 | 959.200 | 813.213 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R7.json` |
| unet_qd2_R7 | UNET | 2 | 6015.151 | 6020.561 | 12309817472 | 47 | 1.322 | 2 | 6008.685 | 5280.893 | 222.204 | 5280.755 | 5058.551 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R7.json` |
| clip_qd4_R7 | CLIP | 4 | 1305.380 | 1313.744 | 8044936192 | 33 | 3.342 | 4 | 1304.701 | 1272.782 | 230.078 | 1272.707 | 1042.630 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R7.json` |
| unet_qd4_R7 | UNET | 4 | 3658.831 | 3664.790 | 12309817472 | 49 | 1.976 | 4 | 3655.239 | 3046.219 | 462.369 | 3046.046 | 2583.677 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R7.json` |
| clip_qd8_R7 | CLIP | 8 | 1438.049 | 1452.368 | 8044936192 | 37 | 4.849 | 8 | 1429.948 | 1291.953 | 236.373 | 1291.884 | 1055.512 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R7.json` |
| unet_qd8_R7 | UNET | 8 | 2120.727 | 2124.792 | 12309817472 | 53 | 5.068 | 8 | 2112.305 | 2017.884 | 391.904 | 2017.844 | 1625.940 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R7.json` |
| clip_qd2_R8 | CLIP | 2 | 1050.245 | 1056.415 | 8044936192 | 31 | 1.932 | 2 | 1049.815 | 988.022 | 145.660 | 987.867 | 842.207 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R8.json` |
| unet_qd2_R8 | UNET | 2 | 1418.799 | 1428.816 | 12309817472 | 47 | 1.970 | 2 | 1418.799 | 1422.507 | 220.157 | 1422.381 | 1202.224 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R8.json` |
| clip_qd4_R8 | CLIP | 4 | 1297.464 | 1303.579 | 8044936192 | 33 | 3.270 | 4 | 1296.434 | 1212.057 | 146.904 | 1211.947 | 1065.044 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R8.json` |
| unet_qd4_R8 | UNET | 4 | 2003.088 | 2010.001 | 12309817472 | 49 | 3.616 | 4 | 2001.335 | 1869.980 | 223.375 | 1869.898 | 1646.524 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R8.json` |
| clip_qd8_R8 | CLIP | 8 | 1369.136 | 1381.741 | 8044936192 | 37 | 3.663 | 7 | 1365.246 | 1238.297 | 353.618 | 1238.239 | 884.620 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R8.json` |
| unet_qd8_R8 | UNET | 8 | 1670.265 | 1675.255 | 12309817472 | 53 | 4.370 | 8 | 1660.853 | 1636.007 | 421.829 | 1635.875 | 1214.046 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R8.json` |
| clip_qd2_R9 | CLIP | 2 | 1039.203 | 1045.687 | 8044936192 | 31 | 1.822 | 2 | 1037.786 | 986.763 | 144.496 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R9.json` |
| unet_qd2_R9 | UNET | 2 | 1449.927 | 1459.505 | 12309817472 | 47 | 1.948 | 2 | 1449.270 | 1407.628 | 221.669 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R9.json` |
| clip_qd4_R9 | CLIP | 4 | 1341.323 | 1358.845 | 8044936192 | 33 | 3.250 | 4 | 1339.404 | 1252.715 | 274.049 | 1252.660 | 978.611 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R9.json` |
| unet_qd4_R9 | UNET | 4 | 1692.532 | 1698.133 | 12309817472 | 49 | 2.937 | 4 | 1688.584 | 1641.935 | 375.433 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R9.json` |
| clip_qd8_R9 | CLIP | 8 | 1090.569 | 1098.240 | 8044936192 | 37 | 2.895 | 6 | 1087.790 | 897.185 | 241.836 | 897.177 | 655.341 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R9.json` |
| unet_qd8_R9 | UNET | 8 | 2074.105 | 2083.819 | 12309817472 | 53 | 4.391 | 8 | 2063.638 | 2026.218 | 430.321 | 2026.064 | 1595.743 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R9.json` |
| clip_qd2_R10 | CLIP | 2 | 1117.855 | 1123.985 | 8044936192 | 31 | 1.888 | 2 | 1117.172 | 1063.088 | 144.864 | 1063.012 | 918.148 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R10.json` |
| unet_qd2_R10 | UNET | 2 | 1775.092 | 1784.240 | 12309817472 | 47 | 1.943 | 2 | 1773.763 | 1722.737 | 224.353 | 1722.720 | 1498.367 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R10.json` |
| clip_qd4_R10 | CLIP | 4 | 949.889 | 957.549 | 8044936192 | 33 | 3.111 | 4 | 947.907 | 908.551 | 246.317 | 908.452 | 662.136 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R10.json` |
| unet_qd4_R10 | UNET | 4 | 1708.548 | 1711.772 | 12309817472 | 49 | 3.314 | 4 | 1706.886 | 1641.020 | 272.749 | 1640.898 | 1368.149 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R10.json` |
| clip_qd8_R10 | CLIP | 8 | 1460.832 | 1476.698 | 8044936192 | 37 | 4.064 | 7 | 1454.667 | 1357.688 | 329.160 | 1357.629 | 1028.469 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R10.json` |
| unet_qd8_R10 | UNET | 8 | 2187.142 | 2189.959 | 12309817472 | 53 | 4.710 | 8 | 2177.048 | 2072.371 | 326.361 | 2072.333 | 1745.972 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R10.json` |
| clip_qd2_R11 | CLIP | 2 | 1142.647 | 1148.981 | 8044936192 | 31 | 1.839 | 2 | 1141.569 | 1067.002 | 145.270 | 1066.969 | 921.699 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R11.json` |
| unet_qd2_R11 | UNET | 2 | 1578.943 | 1584.719 | 12309817472 | 47 | 1.955 | 2 | 1578.629 | 1522.882 | 221.116 | 1522.851 | 1301.736 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R11.json` |
| clip_qd4_R11 | CLIP | 4 | 1215.209 | 1218.218 | 8044936192 | 33 | 3.364 | 4 | 1212.949 | 1132.296 | 188.042 | 1132.212 | 944.170 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R11.json` |
| unet_qd4_R11 | UNET | 4 | 1678.711 | 1688.314 | 12309817472 | 49 | 3.289 | 4 | 1676.749 | 1600.687 | 348.836 | 1600.610 | 1251.774 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R11.json` |
| clip_qd8_R11 | CLIP | 8 | 1309.869 | 1315.188 | 8044936192 | 37 | 3.980 | 7 | 1303.721 | 1212.827 | 269.230 | 1212.758 | 943.528 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R11.json` |
| unet_qd8_R11 | UNET | 8 | 3255.489 | 3258.386 | 12309817472 | 53 | 4.080 | 8 | 3244.879 | 2903.733 | 930.542 | 2903.655 | 1973.112 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R11.json` |
| clip_qd2_R12 | CLIP | 2 | 891.675 | 902.414 | 8044936192 | 31 | 1.971 | 2 | 891.675 | 900.729 | 145.084 | 900.820 | 755.736 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R12.json` |
| unet_qd2_R12 | UNET | 2 | 1487.556 | 1496.780 | 12309817472 | 47 | 1.972 | 2 | 1487.556 | 1440.231 | 221.120 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R12.json` |
| clip_qd4_R12 | CLIP | 4 | 1170.406 | 1184.394 | 8044936192 | 33 | 2.982 | 4 | 1168.104 | 1106.349 | 215.211 | 1106.166 | 890.955 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R12.json` |
| unet_qd4_R12 | UNET | 4 | 3258.046 | 3264.660 | 12309817472 | 49 | 2.173 | 4 | 3256.046 | 2563.370 | 938.625 | 2563.222 | 1624.597 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R12.json` |
| clip_qd8_R12 | CLIP | 8 | 1342.793 | 1348.010 | 8044936192 | 37 | 4.031 | 7 | 1336.569 | 1287.275 | 363.450 | 1287.144 | 923.693 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R12.json` |
| unet_qd8_R12 | UNET | 8 | 2200.089 | 2202.888 | 12309817472 | 53 | 4.913 | 8 | 2189.926 | 2178.945 | 537.640 | 2178.980 | 1641.340 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R12.json` |
| clip_qd2_R13 | CLIP | 2 | 915.017 | 925.866 | 8044936192 | 31 | 1.970 | 2 | 915.017 | 923.192 | 144.814 | 923.308 | 778.494 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R13.json` |
| unet_qd2_R13 | UNET | 2 | 1395.117 | 1404.698 | 12309817472 | 47 | 1.965 | 2 | 1395.117 | 1399.099 | 220.775 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R13.json` |
| clip_qd4_R13 | CLIP | 4 | 1349.207 | 1352.166 | 8044936192 | 33 | 3.370 | 4 | 1346.148 | 1297.129 | 199.820 | 1297.003 | 1097.183 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R13.json` |
| unet_qd4_R13 | UNET | 4 | 1837.197 | 1841.974 | 12309817472 | 49 | 3.639 | 4 | 1835.344 | 1766.704 | 221.005 | 1766.568 | 1545.563 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R13.json` |
| clip_qd8_R13 | CLIP | 8 | 1290.757 | 1296.611 | 8044936192 | 37 | 3.350 | 6 | 1285.300 | 1240.607 | 443.629 | 1240.462 | 796.834 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R13.json` |
| unet_qd8_R13 | UNET | 8 | 2257.984 | 2260.975 | 12309817472 | 53 | 5.193 | 8 | 2246.820 | 2129.052 | 478.176 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R13.json` |
| clip_qd2_R14 | CLIP | 2 | 963.434 | 973.871 | 8044936192 | 31 | 1.884 | 2 | 962.514 | 915.626 | 143.692 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd2_R14.json` |
| unet_qd2_R14 | UNET | 2 | 1556.906 | 1563.008 | 12309817472 | 47 | 1.920 | 2 | 1556.528 | 1556.610 | 221.695 | UNAVAILABLE | 0.000 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd2_R14.json` |
| clip_qd4_R14 | CLIP | 4 | 1047.266 | 1053.630 | 8044936192 | 33 | 3.002 | 4 | 1044.040 | 986.230 | 191.609 | 986.102 | 794.493 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd4_R14.json` |
| unet_qd4_R14 | UNET | 4 | 2029.338 | 2032.600 | 12309817472 | 49 | 3.288 | 4 | 2026.627 | 1962.777 | 284.905 | 1962.718 | 1677.813 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd4_R14.json` |
| clip_qd8_R14 | CLIP | 8 | 1399.744 | 1413.081 | 8044936192 | 37 | 4.737 | 7 | 1388.939 | 1327.117 | 266.946 | 1327.079 | 1060.134 | 0 | YES | CLOUD_PROVIDER_GCP | us-east4 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R14.json` |
| unet_qd8_R14 | UNET | 8 | 1889.044 | 1894.805 | 12309817472 | 53 | 5.048 | 8 | 1882.179 | 1815.688 | 473.731 | 1815.605 | 1341.874 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/unet_qd8_R14.json` |
| clip_qd8_R15 | CLIP | 8 | 1340.624 | 1349.386 | 8044936192 | 37 | 3.286 | 6 | 1336.838 | 1293.631 | 461.840 | 1293.476 | 831.636 | 0 | YES | CLOUD_PROVIDER_GCP | us-east1 | `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/clip_qd8_R15.json` |

## Raw Evidence

- Additional raw evidence: `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/`.
- Prior valid raw evidence: `unetClipExperimentsSeptember/05_qd_closure_runs_v2/`.
- Prior invalid first campaign: `unetClipExperimentsSeptember/05_qd_closure_runs/`, retained and excluded.
- Machine-readable report: `unetClipExperimentsSeptember/05_qd2_qd4_qd8_additional10.json`.
