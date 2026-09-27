# September UNET/CLIP Experiment 06: Source Block x QD Matrix

STATUS=COMPLETE
DECISION_METRIC=SOURCE_WALL_MS
SECONDARY_METRIC=FILE_TO_CUDA_WALL_MS

## Scope And Decision

The matrix contains 10 runtime-eligible single-use-container observations per model x block x QD cell: 320 total. The 256 MiB/QD2, QD4, and QD8 cells reuse the prior Experiment-05 10-valid cohorts; the remaining 260 observations were newly collected.
Lower wall time is better. Effective GB/s uses decimal GB and the median wall for that cell.

## Best Source Configuration

| model | block MiB | QD | nominal outstanding MiB | SOURCE median ms | FILE_TO_CUDA median ms | effective GB/s |
|---|---:|---:|---:|---:|---:|---:|
| CLIP | 256 | 2 | 512.000 | 1001.319 | 1009.779 | 8.034343 |
| UNET | 256 | 2 | 512.000 | 1553.951 | 1562.224 | 7.921625 |

Best means lowest median SOURCE_WALL_MS among the 16 cells for that model. It is not a claim that the two model winners share the same resource geometry.

## Performance By Block Size At Each QD

| role | QD | block | SOURCE median ms | FILE_TO_CUDA median ms |
|---|---|---|---|---|
| CLIP | 1 | 32 | 1771.405 | 1773.550 |
| CLIP | 2 | 32 | 1097.070 | 1098.927 |
| CLIP | 4 | 32 | 1278.592 | 1280.671 |
| CLIP | 8 | 32 | 1731.363 | 1733.291 |
| CLIP | 1 | 64 | 1621.966 | 1623.688 |
| CLIP | 2 | 64 | 1064.946 | 1068.189 |
| CLIP | 4 | 64 | 1180.390 | 1182.577 |
| CLIP | 8 | 64 | 1557.898 | 1560.216 |
| CLIP | 1 | 128 | 1588.659 | 1592.097 |
| CLIP | 2 | 128 | 1037.449 | 1041.538 |
| CLIP | 4 | 128 | 1267.622 | 1274.343 |
| CLIP | 8 | 128 | 1462.586 | 1465.533 |
| CLIP | 1 | 256 | 1586.953 | 1592.617 |
| CLIP | 2 | 256 | 1001.319 | 1009.779 |
| CLIP | 4 | 256 | 1247.263 | 1258.711 |
| CLIP | 8 | 256 | 1341.708 | 1348.698 |
| UNET | 1 | 32 | 2887.411 | 2889.318 |
| UNET | 2 | 32 | 1804.525 | 1806.870 |
| UNET | 4 | 32 | 1960.457 | 1962.792 |
| UNET | 8 | 32 | 2685.387 | 2686.817 |
| UNET | 1 | 64 | 2737.746 | 2739.980 |
| UNET | 2 | 64 | 1580.687 | 1582.711 |
| UNET | 4 | 64 | 1878.010 | 1880.266 |
| UNET | 8 | 64 | 2552.772 | 2554.811 |
| UNET | 1 | 128 | 2479.367 | 2482.474 |
| UNET | 2 | 128 | 1581.640 | 1584.587 |
| UNET | 4 | 128 | 1959.702 | 1962.670 |
| UNET | 8 | 128 | 2369.257 | 2372.834 |
| UNET | 1 | 256 | 2590.287 | 2595.426 |
| UNET | 2 | 256 | 1553.951 | 1562.224 |
| UNET | 4 | 256 | 1971.510 | 1977.688 |
| UNET | 8 | 256 | 2153.934 | 2157.375 |

## Performance By QD At Each Block Size

| role | block | QD | SOURCE median ms | FILE_TO_CUDA median ms |
|---|---|---|---|---|
| CLIP | 32 | 1 | 1771.405 | 1773.550 |
| CLIP | 32 | 2 | 1097.070 | 1098.927 |
| CLIP | 32 | 4 | 1278.592 | 1280.671 |
| CLIP | 32 | 8 | 1731.363 | 1733.291 |
| CLIP | 64 | 1 | 1621.966 | 1623.688 |
| CLIP | 64 | 2 | 1064.946 | 1068.189 |
| CLIP | 64 | 4 | 1180.390 | 1182.577 |
| CLIP | 64 | 8 | 1557.898 | 1560.216 |
| CLIP | 128 | 1 | 1588.659 | 1592.097 |
| CLIP | 128 | 2 | 1037.449 | 1041.538 |
| CLIP | 128 | 4 | 1267.622 | 1274.343 |
| CLIP | 128 | 8 | 1462.586 | 1465.533 |
| CLIP | 256 | 1 | 1586.953 | 1592.617 |
| CLIP | 256 | 2 | 1001.319 | 1009.779 |
| CLIP | 256 | 4 | 1247.263 | 1258.711 |
| CLIP | 256 | 8 | 1341.708 | 1348.698 |
| UNET | 32 | 1 | 2887.411 | 2889.318 |
| UNET | 32 | 2 | 1804.525 | 1806.870 |
| UNET | 32 | 4 | 1960.457 | 1962.792 |
| UNET | 32 | 8 | 2685.387 | 2686.817 |
| UNET | 64 | 1 | 2737.746 | 2739.980 |
| UNET | 64 | 2 | 1580.687 | 1582.711 |
| UNET | 64 | 4 | 1878.010 | 1880.266 |
| UNET | 64 | 8 | 2552.772 | 2554.811 |
| UNET | 128 | 1 | 2479.367 | 2482.474 |
| UNET | 128 | 2 | 1581.640 | 1584.587 |
| UNET | 128 | 4 | 1959.702 | 1962.670 |
| UNET | 128 | 8 | 2369.257 | 2372.834 |
| UNET | 256 | 1 | 2590.287 | 2595.426 |
| UNET | 256 | 2 | 1553.951 | 1562.224 |
| UNET | 256 | 4 | 1971.510 | 1977.688 |
| UNET | 256 | 8 | 2153.934 | 2157.375 |

## Performance Versus Nominal Outstanding Source Bytes

Nominal outstanding source bytes = block size x producer count. Rows compare configurations sharing the same nominal outstanding byte budget.

| model | nominal outstanding MiB | configurations | SOURCE medians ms | FILE_TO_CUDA medians ms |
|---|---:|---|---|---|
| CLIP | 32.000 | 32x1 | 32x1=1771.405 | 32x1=1773.550 |
| CLIP | 64.000 | 32x2, 64x1 | 32x2=1097.070; 64x1=1621.966 | 32x2=1098.927; 64x1=1623.688 |
| CLIP | 128.000 | 32x4, 64x2, 128x1 | 32x4=1278.592; 64x2=1064.946; 128x1=1588.659 | 32x4=1280.671; 64x2=1068.189; 128x1=1592.097 |
| CLIP | 256.000 | 32x8, 64x4, 128x2, 256x1 | 32x8=1731.363; 64x4=1180.390; 128x2=1037.449; 256x1=1586.953 | 32x8=1733.291; 64x4=1182.577; 128x2=1041.538; 256x1=1592.617 |
| CLIP | 512.000 | 64x8, 128x4, 256x2 | 64x8=1557.898; 128x4=1267.622; 256x2=1001.319 | 64x8=1560.216; 128x4=1274.343; 256x2=1009.779 |
| CLIP | 1024.000 | 128x8, 256x4 | 128x8=1462.586; 256x4=1247.263 | 128x8=1465.533; 256x4=1258.711 |
| CLIP | 2048.000 | 256x8 | 256x8=1341.708 | 256x8=1348.698 |
| UNET | 32.000 | 32x1 | 32x1=2887.411 | 32x1=2889.318 |
| UNET | 64.000 | 32x2, 64x1 | 32x2=1804.525; 64x1=2737.746 | 32x2=1806.870; 64x1=2739.980 |
| UNET | 128.000 | 32x4, 64x2, 128x1 | 32x4=1960.457; 64x2=1580.687; 128x1=2479.367 | 32x4=1962.792; 64x2=1582.711; 128x1=2482.474 |
| UNET | 256.000 | 32x8, 64x4, 128x2, 256x1 | 32x8=2685.387; 64x4=1878.010; 128x2=1581.640; 256x1=2590.287 | 32x8=2686.817; 64x4=1880.266; 128x2=1584.587; 256x1=2595.426 |
| UNET | 512.000 | 64x8, 128x4, 256x2 | 64x8=2552.772; 128x4=1959.702; 256x2=1553.951 | 64x8=2554.811; 128x4=1962.670; 256x2=1562.224 |
| UNET | 1024.000 | 128x8, 256x4 | 128x8=2369.257; 256x4=1971.510 | 128x8=2372.834; 256x4=1977.688 |
| UNET | 2048.000 | 256x8 | 256x8=2153.934 | 256x8=2157.375 |

## Explicit Equal-Outstanding-Byte Groups

| model | nominal MiB | configurations | SOURCE medians ms | FILE_TO_CUDA medians ms |
|---|---:|---|---|---|
| CLIP | 256.000 | 32x8, 64x4, 128x2, 256x1 | 32x8=1731.363; 64x4=1180.390; 128x2=1037.449; 256x1=1586.953 | 32x8=1733.291; 64x4=1182.577; 128x2=1041.538; 256x1=1592.617 |
| CLIP | 512.000 | 64x8, 128x4, 256x2 | 64x8=1557.898; 128x4=1267.622; 256x2=1001.319 | 64x8=1560.216; 128x4=1274.343; 256x2=1009.779 |
| UNET | 256.000 | 32x8, 64x4, 128x2, 256x1 | 32x8=2685.387; 64x4=1878.010; 128x2=1581.640; 256x1=2590.287 | 32x8=2686.817; 64x4=1880.266; 128x2=1584.587; 256x1=2595.426 |
| UNET | 512.000 | 64x8, 128x4, 256x2 | 64x8=2552.772; 128x4=1959.702; 256x2=1553.951 | 64x8=2554.811; 128x4=1962.670; 256x2=1562.224 |

## Cohort Audit

- New attempts retained: 336; new runtime-eligible observations: 260; new invalid attempts: 76.
- Final matrix: 320 runtime-eligible observations, exactly 10 per cell; all have status `ok` and byte validation true.
- Strict E27 proof: 289/320; 31 status-ok observations have proof `NO` and are retained/flagged in JSON and the ledger.
- Fallback count zero: 320/320.
- Distinct single-use container sessions: 320.
- Reused cells are the prior Experiment-05 256 MiB/QD2, QD4, and QD8 observations for both models; their prior image identity is retained separately from the new deployment image.
- All 76 pre-QD1-fix errors from the first matrix deployment remain under `06_source_block_qd_matrix_runs` and are listed as invalid attempts in JSON.

## Per-Cell Statistics And Ten Values

Each row includes all 10 primary and secondary values, achieved-QD values, source read counts, and GPU active-copy values. `UNAVAILABLE` is an observed null, not an imputation.

| model | block MiB | QD | nominal MiB | SOURCE values ms | FILE_TO_CUDA values ms | SOURCE median | SOURCE mean | SOURCE SD | SOURCE CV | effective GB/s | mean achieved QD | max achieved QD | source read counts | GPU active-copy ms | proof YES/NO |
|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| CLIP | 32 | 1 | 32.000 | 1812.826, 1803.140, 1605.958, 1582.048, 1611.238, 1799.636, 1743.173, 1858.411, 1839.299, 1627.067 | 1814.421, 1804.893, 1607.605, 1583.794, 1612.859, 1802.242, 1744.858, 1860.124, 1841.857, 1628.700 | 1771.405 | 1728.280 | 109.349 | 0.063270 | 4.541557 | 0.942 (0.951, 0.940, 0.935, 0.941, 0.944, 0.939, 0.944, 0.945, 0.944, 0.939) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 240, 240, 240, 240, 240, 240, 240, 240, 240, 240 | 149.874, 150.250, 157.888, 151.892, 147.464, 151.443, 148.885, 150.859, 147.888, 153.147 | YES=10 |
| CLIP | 32 | 2 | 64.000 | 2247.414, 1007.920, 2684.992, 1082.947, 1048.761, 1114.387, 3384.426, 1005.789, 1052.946, 1111.192 | 2249.173, 1009.829, 2687.151, 1084.591, 1050.941, 1116.418, 3386.474, 1007.540, 1054.655, 1113.263 | 1097.070 | 1574.077 | 870.675 | 0.553134 | 7.333112 | 1.839 (1.758, 1.863, 1.897, 1.865, 1.874, 1.801, 1.819, 1.873, 1.785, 1.849) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 241, 241, 241, 241, 241, 241, 241, 241, 241, 241 | 157.397, 158.925, 167.929, 155.818, 158.502, 158.240, 158.185, 178.139, 159.828, 154.840 | YES=10 |
| CLIP | 32 | 4 | 128.000 | 1297.137, 1260.047, 1343.289, 1218.615, 2775.349, 2127.152, 1202.247, 1317.099, 1211.702, 1175.797 | 1299.155, 1262.186, 1345.009, 1220.451, 2777.327, 2129.069, 1203.987, 1318.884, 1214.288, 1178.261 | 1278.592 | 1492.843 | 530.421 | 0.355309 | 6.292025 | 3.439 (3.626, 3.629, 3.549, 3.667, 2.504, 2.808, 3.591, 3.706, 3.745, 3.566) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 243, 243, 243, 243, 243, 243, 243, 243, 243, 243 | 168.606, 175.997, 190.855, 206.767, 174.149, 180.440, 187.865, 175.604, 194.720, 163.759 | YES=10 |
| CLIP | 32 | 8 | 256.000 | 2358.238, 1620.765, 1524.069, 1752.117, 1842.063, 1734.504, 1649.043, 1728.221, 1249.867, 1847.759 | 2360.198, 1622.815, 1525.798, 1753.744, 1843.880, 1736.308, 1651.151, 1730.275, 1251.516, 1849.573 | 1731.363 | 1730.665 | 281.472 | 0.162638 | 4.646593 | 6.458 (5.338, 6.628, 6.353, 6.707, 6.643, 6.619, 6.648, 6.468, 6.468, 6.707) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 247, 247, 247, 247, 247, 247, 247, 247, 247, 247 | 1029.517, 199.886, 226.081, 198.701, 195.816, 234.177, 222.833, 204.163, 205.902, 311.332 | NO=2, YES=8 |
| CLIP | 64 | 1 | 64.000 | 1749.912, 1606.458, 1581.221, 1637.474, 1683.857, 1543.345, 1726.194, 1596.610, 1580.190, 1786.873 | 1751.628, 1608.164, 1583.125, 1639.212, 1685.459, 1545.013, 1727.908, 1598.621, 1582.064, 1789.438 | 1621.966 | 1649.213 | 82.694 | 0.050141 | 4.959990 | 0.974 (0.974, 0.972, 0.975, 0.974, 0.976, 0.974, 0.975, 0.972, 0.975, 0.977) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 120, 120, 120, 120, 120, 120, 120, 120, 120, 120 | 149.172, 150.358, 146.993, 152.728, 146.670, 148.820, 149.141, 155.707, 145.649, 148.120 | YES=10 |
| CLIP | 64 | 2 | 128.000 | 1099.227, 1153.272, 985.333, 1044.421, 2639.058, 1061.403, 1035.519, 1042.427, 1068.488, 1081.239 | 1101.060, 1155.673, 987.425, 1047.263, 2641.661, 1063.294, 1037.183, 1046.756, 1073.084, 1083.226 | 1064.946 | 1221.039 | 500.175 | 0.409631 | 7.554315 | 1.860 (1.896, 1.910, 1.901, 1.948, 1.376, 1.942, 1.925, 1.924, 1.948, 1.831) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 121, 121, 121, 121, 121, 121, 121, 121, 121, 121 | 155.201, 150.869, 149.199, 149.963, 153.759, 149.070, 149.420, 152.546, 150.338, 148.419 | YES=10 |
| CLIP | 64 | 4 | 256.000 | 1150.017, 1118.751, 1382.473, 1289.993, 1108.391, 1325.996, 1136.702, 1290.123, 1131.243, 1210.763 | 1152.196, 1120.683, 1385.593, 1291.892, 1110.871, 1329.554, 1138.784, 1292.122, 1133.116, 1212.958 | 1180.390 | 1214.445 | 99.804 | 0.082181 | 6.815489 | 3.641 (3.826, 3.593, 3.766, 3.759, 3.618, 3.695, 3.576, 3.691, 3.504, 3.381) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 123, 123, 123, 123, 123, 123, 123, 123, 123, 123 | 154.683, 168.869, 165.794, 180.329, 188.211, 172.091, 155.082, 171.962, 219.100, 196.774 | NO=1, YES=9 |
| CLIP | 64 | 8 | 512.000 | 1510.025, 1594.966, 1517.387, 1660.897, 1555.369, 1606.194, 1507.789, 1560.427, 1747.624, 1366.908 | 1514.150, 1596.756, 1519.270, 1665.239, 1557.457, 1608.037, 1511.020, 1562.976, 1750.115, 1368.981 | 1557.898 | 1562.759 | 101.658 | 0.065050 | 5.163969 | 6.416 (5.883, 6.505, 5.933, 6.450, 6.825, 6.816, 6.190, 6.354, 6.936, 6.262) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 127, 127, 127, 127, 127, 127, 127, 127, 127, 127 | 235.183, 242.668, 192.331, 242.810, 211.362, 224.147, 189.298, 172.362, 219.075, 164.344 | YES=10 |
| CLIP | 128 | 1 | 128.000 | 1462.945, 1402.236, 1639.099, 1432.333, 1660.825, 1743.552, 1642.263, 1468.199, 1599.386, 1577.933 | 1466.088, 1405.226, 1642.139, 1436.106, 1663.855, 1746.288, 1645.210, 1471.368, 1602.426, 1581.769 | 1588.659 | 1562.877 | 114.361 | 0.073174 | 5.063978 | 0.987 (0.988, 0.987, 0.986, 0.988, 0.988, 0.989, 0.989, 0.987, 0.987, 0.986) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 60, 60, 60, 60, 60, 60, 60, 60, 60, 60 | 146.447, 145.214, 147.141, 145.901, 145.534, 148.387, 145.998, 149.482, 146.579, 146.111 | YES=10 |
| CLIP | 128 | 2 | 256.000 | 981.564, 2293.250, 1017.138, 1008.819, 1058.795, 1043.168, 991.557, 1031.731, 1100.688, 1093.310 | 984.971, 2295.914, 1020.969, 1012.784, 1062.028, 1048.579, 994.303, 1034.496, 1103.683, 1098.423 | 1037.449 | 1162.002 | 399.444 | 0.343755 | 7.754534 | 1.908 (1.895, 1.825, 1.923, 1.949, 1.877, 1.944, 1.859, 1.939, 1.898, 1.971) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 61, 61, 61, 61, 61, 61, 61, 61, 61, 61 | 146.776, 146.894, 146.278, 150.514, 145.654, 150.764, 148.105, 146.872, 147.033, 147.597 | YES=10 |
| CLIP | 128 | 4 | 512.000 | 1043.307, 1270.291, 2204.169, 1234.694, 1277.177, 1264.954, 1185.689, 1278.350, 1261.096, 1388.426 | 1050.576, 1273.120, 2207.312, 1239.567, 1280.224, 1267.781, 1189.433, 1281.499, 1275.566, 1391.610 | 1267.622 | 1340.815 | 315.616 | 0.235391 | 6.346478 | 3.405 (3.650, 3.490, 2.697, 3.722, 3.252, 3.402, 3.313, 3.449, 3.733, 3.343) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 63, 63, 63, 63, 63, 63, 63, 63, 63, 63 | 217.945, 199.655, 176.233, 177.458, 216.815, 259.821, 206.614, 150.894, 230.484, 211.915 | YES=10 |
| CLIP | 128 | 8 | 1024.000 | 1273.335, 1561.371, 1639.252, 1415.369, 1366.196, 1471.401, 1329.607, 1453.771, 1609.394, 1647.602 | 1284.216, 1573.925, 1644.494, 1419.464, 1369.177, 1475.699, 1337.197, 1455.368, 1613.233, 1650.583 | 1462.586 | 1476.730 | 133.303 | 0.090269 | 5.500487 | 5.608 (5.493, 5.610, 6.096, 5.654, 5.343, 5.196, 5.363, 5.503, 6.500, 5.321) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 67, 67, 67, 67, 67, 67, 67, 67, 67, 67 | 213.639, 234.142, 237.409, 246.490, 247.299, 405.342, 175.912, 316.739, 193.286, 353.278 | NO=1, YES=9 |
| CLIP | 256 | 1 | 256.000 | 1570.544, 1474.964, 1587.938, 1549.897, 1697.994, 1691.371, 1659.175, 1516.490, 1789.645, 1585.968 | 1576.820, 1480.986, 1592.965, 1556.219, 1704.385, 1697.696, 1665.424, 1522.513, 1795.736, 1592.269 | 1586.953 | 1612.399 | 95.574 | 0.059274 | 5.069422 | 0.994 (0.994, 0.994, 0.994, 0.994, 0.994, 0.994, 0.994, 0.994, 0.994, 0.994) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 30, 30, 30, 30, 30, 30, 30, 30, 30, 30 | 149.097, 144.658, 144.417, 144.137, 145.229, 145.600, 144.201, 144.797, 146.629, 144.413 | YES=10 |
| CLIP | 256 | 2 | 512.000 | 1076.102, 920.017, 950.238, 1050.245, 1039.203, 1117.855, 1142.647, 891.675, 915.017, 963.434 | 1081.484, 925.208, 960.753, 1056.415, 1045.687, 1123.985, 1148.981, 902.414, 925.866, 973.871 | 1001.319 | 1006.643 | 89.948 | 0.089355 | 8.034343 | 1.910 (1.933, 1.919, 1.943, 1.932, 1.822, 1.888, 1.839, 1.971, 1.970, 1.884) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 31, 31, 31, 31, 31, 31, 31, 31, 31, 31 | 143.472, 146.298, 145.987, 145.660, 144.496, 144.864, 145.270, 145.084, 144.814, 143.692 | YES=10 |
| CLIP | 256 | 4 | 1024.000 | 1155.468, 1279.317, 1305.380, 1297.464, 1341.323, 949.889, 1215.209, 1170.406, 1349.207, 1047.266 | 1168.641, 1299.203, 1313.744, 1303.579, 1358.845, 957.549, 1218.218, 1184.394, 1352.166, 1053.630 | 1247.263 | 1211.093 | 132.024 | 0.109012 | 6.450071 | 3.274 (3.547, 3.506, 3.342, 3.270, 3.250, 3.111, 3.364, 2.982, 3.370, 3.002) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 33, 33, 33, 33, 33, 33, 33, 33, 33, 33 | 211.802, 249.222, 230.078, 146.904, 274.049, 246.317, 188.042, 215.211, 199.820, 191.609 | YES=10 |
| CLIP | 256 | 8 | 2048.000 | 1262.518, 1438.049, 1369.136, 1090.569, 1460.832, 1309.869, 1342.793, 1290.757, 1399.744, 1340.624 | 1272.635, 1452.368, 1381.741, 1098.240, 1476.698, 1315.188, 1348.010, 1296.611, 1413.081, 1349.386 | 1341.708 | 1330.489 | 105.033 | 0.078943 | 5.996039 | 3.840 (3.545, 4.849, 3.663, 2.895, 4.064, 3.980, 4.031, 3.350, 4.737, 3.286) | 8 (7, 8, 7, 6, 7, 7, 7, 6, 7, 6) | 37, 37, 37, 37, 37, 37, 37, 37, 37, 37 | 429.838, 236.373, 353.618, 241.836, 329.160, 269.230, 363.450, 443.629, 266.946, 461.840 | YES=10 |
| UNET | 32 | 1 | 32.000 | 3021.954, 2893.284, 2312.792, 2821.534, 2766.516, 2945.738, 2885.837, 3793.806, 2725.426, 2888.986 | 3024.401, 2895.200, 2314.227, 2823.554, 2768.759, 2947.660, 2887.970, 3795.492, 2728.134, 2890.666 | 2887.411 | 2905.587 | 367.450 | 0.126463 | 4.263271 | 0.899 (0.903, 0.898, 0.895, 0.906, 0.897, 0.892, 0.895, 0.923, 0.887, 0.894) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 367, 367, 367, 367, 367, 367, 367, 367, 367, 367 | 306.677, 229.784, 231.556, 237.726, 230.113, 230.150, 229.380, 234.156, 234.604, 242.060 | YES=10 |
| UNET | 32 | 2 | 64.000 | 3673.638, 3643.199, 1606.154, 1654.129, 1708.623, 1667.393, 4994.550, 1781.113, 1827.936, 1889.104 | 3675.935, 3645.077, 1608.559, 1656.667, 1710.528, 1669.492, 4996.689, 1783.756, 1829.984, 1890.995 | 1804.525 | 2444.584 | 1204.253 | 0.492621 | 6.821640 | 1.764 (1.787, 1.665, 1.780, 1.758, 1.793, 1.768, 1.715, 1.783, 1.789, 1.805) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 368, 368, 368, 368, 368, 368, 368, 368, 368, 368 | 266.899, 247.252, 257.394, 343.722, 258.397, 264.135, 250.488, 326.615, 284.032, 266.680 | NO=9, YES=1 |
| UNET | 32 | 4 | 128.000 | 2523.798, 1868.490, 2081.279, 2113.566, 4597.733, 1950.346, 1585.738, 1970.569, 1763.716, 1875.120 | 2525.441, 1870.292, 2083.201, 2115.769, 4601.269, 1952.182, 1587.411, 1973.403, 1765.843, 1876.987 | 1960.457 | 2233.036 | 866.839 | 0.388189 | 6.279054 | 3.416 (2.887, 3.655, 3.568, 3.654, 2.269, 3.660, 3.609, 3.686, 3.554, 3.619) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 370, 370, 370, 370, 370, 370, 370, 370, 370, 370 | 544.566, 343.284, 319.545, 447.656, 258.243, 336.104, 289.606, 295.856, 327.818, 298.931 | NO=9, YES=1 |
| UNET | 32 | 8 | 256.000 | 4564.084, 2669.001, 2556.191, 2585.281, 4010.256, 2701.773, 2709.548, 2249.150, 5978.096, 2559.952 | 4566.644, 2671.025, 2557.968, 2586.020, 4012.778, 2702.610, 2711.345, 2251.455, 5978.805, 2561.679 | 2685.387 | 3258.333 | 1205.446 | 0.369958 | 4.584001 | 6.184 (4.717, 6.831, 6.825, 6.529, 5.103, 6.906, 7.030, 6.614, 4.598, 6.689) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 374, 374, 374, 374, 374, 374, 374, 374, 374, 374 | 321.874, 385.156, 305.276, 415.860, 1402.868, 337.390, 329.415, 287.769, 279.593, 310.999 | NO=9, YES=1 |
| UNET | 64 | 1 | 64.000 | 3538.333, 2697.031, 2793.103, 3090.272, 2440.817, 2778.460, 2446.753, 3147.890, 2218.349, 2493.299 | 3540.340, 2699.752, 2794.843, 3092.071, 2442.567, 2780.208, 2448.697, 3149.587, 2220.402, 2495.064 | 2737.746 | 2764.431 | 399.314 | 0.144447 | 4.496333 | 0.970 (0.975, 0.970, 0.968, 0.969, 0.970, 0.971, 0.969, 0.969, 0.971, 0.970) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 184, 184, 184, 184, 184, 184, 184, 184, 184, 184 | 230.722, 226.627, 253.068, 237.923, 225.585, 228.775, 225.069, 239.278, 222.723, 226.724 | YES=10 |
| UNET | 64 | 2 | 128.000 | 1567.904, 1657.533, 1566.718, 1451.891, 3578.070, 1632.956, 1439.693, 1640.980, 1577.348, 1584.026 | 1570.223, 1659.235, 1568.459, 1454.632, 3579.842, 1634.714, 1441.727, 1642.917, 1579.777, 1585.644 | 1580.687 | 1769.712 | 639.562 | 0.361393 | 7.787639 | 1.904 (1.935, 1.931, 1.914, 1.915, 1.826, 1.886, 1.944, 1.890, 1.894, 1.909) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 185, 185, 185, 185, 185, 185, 185, 185, 185, 185 | 228.975, 228.585, 235.031, 227.524, 240.872, 232.351, 225.582, 229.456, 247.056, 237.719 | YES=10 |
| UNET | 64 | 4 | 256.000 | 2090.160, 1935.414, 1816.168, 3005.906, 1927.094, 1875.233, 1879.824, 1660.162, 1752.422, 1876.197 | 2092.200, 1937.975, 1817.814, 3008.240, 1929.331, 1877.327, 1881.724, 1662.127, 1754.209, 1878.808 | 1878.010 | 1981.858 | 377.431 | 0.190443 | 6.554712 | 3.580 (3.840, 3.762, 3.814, 2.286, 3.730, 3.648, 3.613, 3.672, 3.809, 3.629) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 187, 187, 187, 187, 187, 187, 187, 187, 187, 187 | 261.257, 252.833, 237.748, 977.283, 257.024, 251.328, 291.162, 255.483, 274.892, 323.787 | YES=10 |
| UNET | 64 | 8 | 512.000 | 3318.145, 2488.520, 2395.748, 2344.935, 2635.882, 2611.183, 2336.139, 2593.847, 2592.877, 2512.667 | 3320.328, 2492.483, 2397.534, 2352.820, 2638.020, 2613.580, 2337.845, 2595.964, 2595.022, 2514.600 | 2552.772 | 2582.994 | 281.029 | 0.108800 | 4.822138 | 6.523 (5.116, 6.553, 6.403, 7.032, 6.505, 6.423, 6.705, 6.690, 6.970, 6.831) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 191, 191, 191, 191, 191, 191, 191, 191, 191, 191 | 274.614, 290.574, 319.987, 276.945, 322.505, 333.944, 328.637, 349.994, 277.473, 312.515 | YES=10 |
| UNET | 128 | 1 | 128.000 | 2701.281, 2752.145, 2513.826, 2444.907, 2570.473, 2804.328, 2361.680, 2381.770, 2332.063, 2428.358 | 2704.030, 2755.327, 2516.941, 2448.006, 2573.333, 2807.125, 2364.753, 2384.553, 2334.868, 2431.364 | 2479.367 | 2529.083 | 170.908 | 0.067577 | 4.964904 | 0.987 (0.987, 0.987, 0.986, 0.985, 0.987, 0.988, 0.986, 0.987, 0.986, 0.986) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 92, 92, 92, 92, 92, 92, 92, 92, 92, 92 | 222.890, 223.527, 223.464, 226.258, 225.939, 222.136, 222.769, 225.630, 230.064, 224.780 | YES=10 |
| UNET | 128 | 2 | 256.000 | 4213.012, 2896.751, 1645.226, 6937.351, 1518.054, 1421.772, 1488.913, 1649.693, 1389.004, 1489.592 | 4216.113, 2899.817, 1648.129, 6940.360, 1521.046, 1424.501, 1491.959, 1654.216, 1394.615, 1494.734 | 1581.640 | 2464.937 | 1814.375 | 0.736073 | 7.782945 | 1.901 (1.978, 1.650, 1.920, 1.825, 1.836, 1.946, 1.946, 1.969, 1.976, 1.968) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 93, 93, 93, 93, 93, 93, 93, 93, 93, 93 | 231.850, 227.452, 237.388, 228.687, 226.202, 228.367, 223.297, 222.957, 223.287, 226.228 | YES=10 |
| UNET | 128 | 4 | 512.000 | 2135.742, 1870.744, 2076.648, 1737.619, 1996.273, 2052.800, 2057.166, 1923.132, 1831.612, 1816.816 | 2138.952, 1873.796, 2081.766, 1740.743, 1999.139, 2057.386, 2060.023, 1926.202, 1835.033, 1819.772 | 1959.702 | 1949.855 | 132.747 | 0.068080 | 6.281474 | 3.655 (3.762, 3.527, 3.713, 3.582, 3.776, 3.739, 3.593, 3.633, 3.573, 3.651) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 95, 95, 95, 95, 95, 95, 95, 95, 95, 95 | 333.923, 308.853, 225.833, 254.006, 247.469, 301.234, 266.680, 294.554, 349.442, 228.046 | YES=10 |
| UNET | 128 | 8 | 1024.000 | 2404.216, 2223.860, 2370.833, 2383.778, 2396.293, 2357.989, 2367.682, 2172.262, 2258.057, 2577.824 | 2409.531, 2225.813, 2373.942, 2386.128, 2402.807, 2359.968, 2371.727, 2175.441, 2263.273, 2579.572 | 2369.257 | 2351.279 | 112.978 | 0.048050 | 5.195645 | 6.027 (6.036, 5.570, 6.227, 6.045, 6.146, 6.075, 6.008, 5.786, 5.936, 6.445) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 99, 99, 99, 99, 99, 99, 99, 99, 99, 99 | 345.706, 310.787, 381.228, 321.221, 347.274, 344.667, 305.188, 416.895, 257.803, 278.626 | YES=10 |
| UNET | 256 | 1 | 256.000 | 2601.580, 2607.876, 2775.066, 2578.994, 2660.255, 2551.096, 2469.636, 2220.333, 2291.387, 2613.265 | 2606.686, 2613.305, 2780.417, 2584.166, 2665.412, 2556.098, 2474.977, 2225.457, 2296.759, 2618.675 | 2590.287 | 2536.949 | 167.989 | 0.066217 | 4.752299 | 0.994 (0.994, 0.994, 0.993, 0.994, 0.994, 0.993, 0.994, 0.994, 0.994, 0.994) | 1 (1, 1, 1, 1, 1, 1, 1, 1, 1, 1) | 46, 46, 46, 46, 46, 46, 46, 46, 46, 46 | 220.349, 220.435, 224.294, 219.994, 220.140, 223.942, 219.589, 220.399, 221.218, 223.492 | YES=10 |
| UNET | 256 | 2 | 512.000 | 1550.996, 1602.401, 6015.151, 1418.799, 1449.927, 1775.092, 1578.943, 1487.556, 1395.117, 1556.906 | 1561.440, 1607.430, 6020.561, 1428.816, 1459.505, 1784.240, 1584.719, 1496.780, 1404.698, 1563.008 | 1553.951 | 1983.089 | 1420.928 | 0.716523 | 7.921625 | 1.888 (1.988, 1.903, 1.322, 1.970, 1.948, 1.943, 1.955, 1.972, 1.965, 1.920) | 2 (2, 2, 2, 2, 2, 2, 2, 2, 2, 2) | 47, 47, 47, 47, 47, 47, 47, 47, 47, 47 | 220.132, 222.544, 222.204, 220.157, 221.669, 224.353, 221.116, 221.120, 220.775, 221.695 | YES=10 |
| UNET | 256 | 4 | 1024.000 | 1939.933, 2030.988, 3658.831, 2003.088, 1692.532, 1708.548, 1678.711, 3258.046, 1837.197, 2029.338 | 1945.376, 2037.467, 3664.790, 2010.001, 1698.133, 1711.772, 1688.314, 3264.660, 1841.974, 2032.600 | 1971.510 | 2183.721 | 692.140 | 0.316954 | 6.243851 | 3.131 (3.469, 3.610, 1.976, 3.616, 2.937, 3.314, 3.289, 2.173, 3.639, 3.288) | 4 (4, 4, 4, 4, 4, 4, 4, 4, 4, 4) | 49, 49, 49, 49, 49, 49, 49, 49, 49, 49 | 296.786, 349.623, 462.369, 223.375, 375.433, 272.749, 348.836, 938.625, 221.005, 284.905 | YES=10 |
| UNET | 256 | 8 | 2048.000 | 4667.485, 1862.915, 2120.727, 1670.265, 2074.105, 2187.142, 3255.489, 2200.089, 2257.984, 1889.044 | 4680.310, 1868.105, 2124.792, 1675.255, 2083.819, 2189.959, 3258.386, 2202.888, 2260.975, 1894.805 | 2153.934 | 2418.525 | 897.008 | 0.370891 | 5.715038 | 4.737 (4.797, 4.804, 5.068, 4.370, 4.391, 4.710, 4.080, 4.913, 5.193, 5.048) | 8 (8, 8, 8, 8, 8, 8, 8, 8, 8, 8) | 53, 53, 53, 53, 53, 53, 53, 53, 53, 53 | 1315.769, 306.848, 391.904, 421.829, 430.321, 326.361, 930.542, 537.640, 478.176, 473.731 | YES=10 |

## Deployment And Fixed Contract

| field | value |
|---|---|
| worktree | `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal` |
| branch / HEAD | `TESTING2` / `f21b3ae29685abbc429813fadc32c8f41264c03e` |
| dirty worktree | true; pre-existing changes preserved |
| workspace / environment | Testing 7 / main |
| app | `sept-unetclip-06-source-block-qd` |
| deployment | `https://modal.com/apps/testing7/main/deployed/sept-unetclip-06-source-block-qd` |
| new image | `im-m6jT6Ib6tj3zlV7mEwuRe7` |
| reused Experiment-05 image | `im-VEOotGdbrzgtTFBFZJrYQM` |
| GPU | `rtx-pro-6000` |
| models Volume | `comfyui-models`, read-only at `/root/models` |
| source/H2D blocks | 32, 64, 128, 256 MiB |
| QD / producer counts | 1, 2, 4, 8 |
| aggregation / model construction / full Golden | false / false / not run |
| scheduling | serial, balanced round interleaving; reused 256/QD2,QD4,QD8 cells skipped |
| runtime change | one authorized static-E27 admission change to allow QD1; no other transport implementation change |

## Invalid Attempts And Raw Evidence

| attempt | status | error | raw artifact |
|---|---|---|---|
| clip_b128_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R1.json` |
| clip_b128_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R2.json` |
| clip_b128_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R3.json` |
| clip_b128_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R4.json` |
| clip_b128_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R5.json` |
| clip_b128_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R6.json` |
| clip_b128_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R7.json` |
| clip_b128_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R8.json` |
| clip_b128_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b128_qd1_R9.json` |
| clip_b256_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R1.json` |
| clip_b256_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R2.json` |
| clip_b256_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R3.json` |
| clip_b256_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R4.json` |
| clip_b256_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R5.json` |
| clip_b256_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R6.json` |
| clip_b256_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R7.json` |
| clip_b256_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R8.json` |
| clip_b256_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b256_qd1_R9.json` |
| clip_b32_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R1.json` |
| clip_b32_qd1_R10 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R10.json` |
| clip_b32_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R2.json` |
| clip_b32_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R3.json` |
| clip_b32_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R4.json` |
| clip_b32_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R5.json` |
| clip_b32_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R6.json` |
| clip_b32_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R7.json` |
| clip_b32_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R8.json` |
| clip_b32_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b32_qd1_R9.json` |
| clip_b64_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R1.json` |
| clip_b64_qd1_R10 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R10.json` |
| clip_b64_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R2.json` |
| clip_b64_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R3.json` |
| clip_b64_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R4.json` |
| clip_b64_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R5.json` |
| clip_b64_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R6.json` |
| clip_b64_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R7.json` |
| clip_b64_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R8.json` |
| clip_b64_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/clip_b64_qd1_R9.json` |
| unet_b128_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R1.json` |
| unet_b128_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R2.json` |
| unet_b128_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R3.json` |
| unet_b128_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R4.json` |
| unet_b128_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R5.json` |
| unet_b128_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R6.json` |
| unet_b128_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R7.json` |
| unet_b128_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R8.json` |
| unet_b128_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b128_qd1_R9.json` |
| unet_b256_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R1.json` |
| unet_b256_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R2.json` |
| unet_b256_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R3.json` |
| unet_b256_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R4.json` |
| unet_b256_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R5.json` |
| unet_b256_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R6.json` |
| unet_b256_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R7.json` |
| unet_b256_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R8.json` |
| unet_b256_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b256_qd1_R9.json` |
| unet_b32_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R1.json` |
| unet_b32_qd1_R10 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R10.json` |
| unet_b32_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R2.json` |
| unet_b32_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R3.json` |
| unet_b32_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R4.json` |
| unet_b32_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R5.json` |
| unet_b32_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R6.json` |
| unet_b32_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R7.json` |
| unet_b32_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R8.json` |
| unet_b32_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b32_qd1_R9.json` |
| unet_b64_qd1_R1 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R1.json` |
| unet_b64_qd1_R10 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R10.json` |
| unet_b64_qd1_R2 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R2.json` |
| unet_b64_qd1_R3 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R3.json` |
| unet_b64_qd1_R4 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R4.json` |
| unet_b64_qd1_R5 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R5.json` |
| unet_b64_qd1_R6 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R6.json` |
| unet_b64_qd1_R7 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R7.json` |
| unet_b64_qd1_R8 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R8.json` |
| unet_b64_qd1_R9 | error | RuntimeError:static_e27_qd_must_be_2_4_or_8 | `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/unet_b64_qd1_R9.json` |

Invalid attempts are retained and excluded from the 320 runtime-eligible observations. The 31 status-ok proof-NO observations remain included in cell values but are clearly marked in the per-cell proof counts and JSON.

## Raw Evidence Paths

- `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/`
- `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs_qd1_retry/`
- `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs_tail_retry/`
- Reused source: `unetClipExperimentsSeptember/05_qd_closure_runs_additional10/`
- Prior first invalid matrix artifacts: `unetClipExperimentsSeptember/06_source_block_qd_matrix_runs/`
- Machine-readable report: `unetClipExperimentsSeptember/06_source_block_qd_matrix.json`
