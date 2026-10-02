# Source race campaign — descriptive statistics

Raw distributions and summary statistics only. H100 and RTX PRO 6000 cohorts are reported separately and never pooled.

## H100

### Accepted (winner) PREADV latency by race width

| arm | count | mean_ms | median_ms | p90_ms | p95_ms | p99_ms | max_ms | stdev_ms | ge_100 | ge_250 | ge_500 | ge_1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| width 1 | 300 | 107.125 | 119.327 | 140.564 | 147.548 | 216.474 | 876.211 | 67.413 | 152 | 2 | 2 | 0 |
| width 2 | 300 | 111.834 | 110.146 | 188.338 | 215.662 | 310.250 | 462.196 | 60.922 | 171 | 7 | 0 | 0 |
| width 4 | 300 | 136.762 | 114.671 | 261.566 | 347.047 | 632.360 | 913.143 | 117.550 | 163 | 32 | 8 | 0 |
| width 8 | 300 | 159.211 | 113.514 | 296.781 | 492.346 | 736.955 | 940.118 | 142.256 | 179 | 40 | 12 | 0 |
| width 16 | 300 | 239.482 | 172.330 | 467.677 | 590.278 | 1373.713 | 1650.985 | 221.511 | 244 | 99 | 27 | 5 |

### All physical PREADV attempts by race width

| arm | count | mean_ms | median_ms | p90_ms | p95_ms | p99_ms | max_ms | stdev_ms | ge_100 | ge_250 | ge_500 | ge_1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| width 1 | 300 | 107.018 | 119.171 | 140.454 | 147.374 | 216.188 | 875.901 | 67.403 | 152 | 2 | 2 | 0 |
| width 2 | 600 | 158.253 | 160.616 | 241.181 | 285.997 | 365.662 | 507.055 | 74.974 | 471 | 54 | 1 | 0 |
| width 4 | 1200 | 292.983 | 275.882 | 491.446 | 631.742 | 862.418 | 1491.924 | 176.155 | 1062 | 679 | 116 | 6 |
| width 8 | 2400 | 471.709 | 458.286 | 796.917 | 914.723 | 1178.423 | 1646.760 | 254.776 | 2274 | 1872 | 1052 | 70 |
| width 16 | 4800 | 980.628 | 964.378 | 1606.018 | 1771.191 | 2491.280 | 3070.816 | 514.658 | 4742 | 4487 | 3821 | 2278 |

### Amplification / loser accounting by race width

| width | attempts per accepted read | loser attempts | loser lifetime mean ms | winner→loser delta mean ms |
|---|---|---|---|---|
| 1 | 1.00 | 0 | - | - |
| 2 | 2.00 | 300 | 205.065 | 94.308 |
| 4 | 4.00 | 900 | 345.216 | 209.916 |
| 8 | 8.00 | 2100 | 516.838 | 364.241 |
| 16 | 16.00 | 4500 | 1030.190 | 793.824 |

## RTX

### Accepted (winner) PREADV latency by race width

| arm | count | mean_ms | median_ms | p90_ms | p95_ms | p99_ms | max_ms | stdev_ms | ge_100 | ge_250 | ge_500 | ge_1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| width 1 | 300 | 45.804 | 43.596 | 53.338 | 55.363 | 107.586 | 816.118 | 62.567 | 4 | 2 | 2 | 0 |
| width 2 | 300 | 51.616 | 45.963 | 70.011 | 78.572 | 179.269 | 757.699 | 64.826 | 7 | 3 | 3 | 0 |
| width 4 | 300 | 66.481 | 53.244 | 114.040 | 193.520 | 298.825 | 390.725 | 54.370 | 43 | 6 | 0 | 0 |
| width 8 | 300 | 63.870 | 50.765 | 88.701 | 129.445 | 478.331 | 933.873 | 84.169 | 23 | 9 | 3 | 0 |
| width 16 | 300 | 74.557 | 58.712 | 108.334 | 181.993 | 427.680 | 1209.619 | 93.653 | 37 | 11 | 3 | 1 |

### All physical PREADV attempts by race width

| arm | count | mean_ms | median_ms | p90_ms | p95_ms | p99_ms | max_ms | stdev_ms | ge_100 | ge_250 | ge_500 | ge_1000 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| width 1 | 300 | 45.713 | 43.562 | 53.280 | 55.282 | 107.523 | 815.812 | 62.560 | 4 | 2 | 2 | 0 |
| width 2 | 600 | 68.853 | 61.064 | 87.123 | 94.179 | 565.185 | 789.332 | 79.092 | 23 | 9 | 9 | 0 |
| width 4 | 1200 | 132.212 | 108.833 | 283.921 | 341.878 | 451.205 | 655.285 | 94.865 | 673 | 153 | 5 | 0 |
| width 8 | 2400 | 173.221 | 158.135 | 256.155 | 322.112 | 762.611 | 1154.271 | 126.724 | 1775 | 289 | 61 | 10 |
| width 16 | 4800 | 304.928 | 296.394 | 487.910 | 540.593 | 829.998 | 1638.755 | 180.097 | 4268 | 2852 | 400 | 35 |

### Amplification / loser accounting by race width

| width | attempts per accepted read | loser attempts | loser lifetime mean ms | winner→loser delta mean ms |
|---|---|---|---|---|
| 1 | 1.00 | 0 | - | - |
| 2 | 2.00 | 300 | 86.454 | 36.239 |
| 4 | 4.00 | 900 | 154.379 | 92.642 |
| 8 | 8.00 | 2100 | 189.021 | 128.369 |
| 16 | 16.00 | 4500 | 320.471 | 253.139 |

## Accepted latency vs block index (all widths pooled, per family)

| block index | h100 | rtx |
|---|---|---|
| 0 | 596.826 | 248.626 |
| 1 | 238.422 | 137.170 |
| 2 | 100.803 | 38.414 |
| 3 | 165.156 | 90.445 |
| 4 | 94.882 | 88.269 |
| 5 | 192.577 | 59.968 |
| 6 | 91.547 | 38.390 |
| 7 | 227.372 | 64.349 |
| 8 | 127.533 | 32.965 |
| 9 | 203.884 | 58.273 |
| 10 | 126.344 | 40.918 |
| 11 | 192.584 | 110.581 |
| 12 | 113.363 | 48.187 |
| 13 | 176.865 | 68.055 |
| 14 | 123.157 | 54.116 |
| 15 | 159.014 | 65.967 |
| 16 | 131.750 | 32.018 |
| 17 | 189.459 | 67.161 |
| 18 | 81.477 | 58.641 |
| 19 | 169.421 | 65.108 |
| 20 | 107.698 | 31.215 |
| 21 | 179.300 | 68.738 |
| 22 | 76.545 | 50.047 |
| 23 | 158.770 | 63.093 |
| 24 | 109.293 | 42.258 |
| 25 | 193.921 | 64.711 |
| 26 | 108.022 | 51.576 |
| 27 | 205.307 | 64.728 |
| 28 | 93.586 | 48.415 |
| 29 | 200.305 | 77.674 |
| 30 | 93.197 | 35.098 |
| 31 | 182.305 | 60.483 |
| 32 | 95.504 | 60.616 |
| 33 | 181.341 | 60.353 |
| 34 | 98.871 | 37.084 |
| 35 | 168.628 | 62.883 |
| 36 | 118.685 | 45.282 |
| 37 | 167.361 | 61.253 |
| 38 | 80.346 | 42.329 |
| 39 | 195.159 | 63.111 |
| 40 | 104.783 | 42.251 |
| 41 | 173.969 | 70.933 |
| 42 | 92.956 | 35.493 |
| 43 | 160.082 | 76.166 |
| 44 | 93.899 | 37.474 |
| 45 | 184.747 | 69.159 |
| 46 | 103.340 | 30.396 |
| 47 | 146.731 | 67.406 |
| 48 | 117.614 | 32.739 |
| 49 | 162.819 | 77.261 |
| 50 | 94.504 | 36.590 |
| 51 | 161.080 | 66.742 |
| 52 | 88.132 | 35.485 |
| 53 | 184.663 | 78.377 |
| 54 | 133.848 | 31.340 |
| 55 | 209.236 | 64.620 |
| 56 | 82.445 | 43.056 |
| 57 | 179.854 | 68.792 |
| 58 | 118.518 | 41.824 |
| 59 | 143.167 | 63.252 |

## Accepted latency vs cumulative speculative bytes

| cumulative bytes bucket (GiB) | h100 | rtx |
|---|---|---|
| 0-8 | 136.090 | 60.609 |
| 8-32 | 147.268 | 59.347 |
| 32-128 | 180.960 | 61.903 |
| 128-512 | - | - |
| 512-1024 | - | - |
| 1024-4096 | - | - |
| 4096-16384 | - | - |

## Winner→loser completion delta distribution

| delta bucket (ms) | h100 | rtx |
|---|---|---|
| 0-5 | 0 | 0 |
| 5-10 | 0 | 0 |
| 10-25 | 0 | 438 |
| 25-50 | 346 | 796 |
| 50-100 | 477 | 1363 |
| 100-250 | 1403 | 2839 |
| 250-500 | 1892 | 2187 |
| 500-1000 | 2112 | 170 |
| 1000-5000 | 1570 | 7 |

(Bucket counts are reported in the JSON aggregate; the mean delta per arm is in the amplification table above.)

## Run provenance

| artifact | attempt | round | width | observed GPU | provider | region | container session | fresh vs prev | accepted wave wall ms | total wall ms |
|---|---|---|---|---|---|---|---|---|---|---|
| h100-r1-w1.json | h100-r1-w1 | 1 | 1 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-east4 | ta-01M33RXY6NNSAAAWP7DZZ169SR | None | 4980.992 | 12182.299 |
| h100-r1-w16.json | h100-r1-w16 | 1 | 16 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | eu-north | ta-01M33S31M22NH5NHZ25C14WDXR | True | 9987.883 | 60093.335 |
| h100-r1-w2.json | h100-r1-w2 | 1 | 2 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | eu-north | ta-01M33S09KJT43EGBM9RMDDR76R | None | 4578.660 | 13626.566 |
| h100-r1-w4.json | h100-r1-w4 | 1 | 4 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | denver | ta-01M33S0X7BWCWB1FK583DQ4YAR | True | 5343.251 | 22842.054 |
| h100-r1-w8.json | h100-r1-w8 | 1 | 8 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | odin | ta-01M33S230MGDC355R4A76GQX3R | True | 6858.736 | 26690.675 |
| h100-r2-w1.json | h100-r2-w1 | 2 | 1 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-east4 | ta-01M33SA4X6WCFMYDP3HH8GV36R | True | 4218.867 | 11104.194 |
| h100-r2-w16.json | h100-r2-w16 | 2 | 16 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-south2 | ta-01M33S5F8GGJN9JYZGCZT5ZS2R | True | 11382.838 | 58186.134 |
| h100-r2-w2.json | h100-r2-w2 | 2 | 2 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-northeast3 | ta-01M33S9GY3D7SGKQNGXY0NB8JR | True | 4285.780 | 13836.456 |
| h100-r2-w4.json | h100-r2-w4 | 2 | 4 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-northeast1 | ta-01M33S8QEND3893A7C0XAEPPNR | True | 5715.932 | 19919.572 |
| h100-r2-w8.json | h100-r2-w8 | 2 | 8 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west4 | ta-01M33S7G8WWX10024KSSDP5VSR | True | 8459.100 | 35188.872 |
| h100-r3-w1.json | h100-r3-w1 | 3 | 1 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west4 | ta-01M33SEDQS85A2757XK08VW5FR | True | 3881.724 | 10773.140 |
| h100-r3-w16.json | h100-r3-w16 | 3 | 16 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west4 | ta-01M33SEWWBHHHZYQ68DGX6MC5R | True | 8974.782 | 54312.105 |
| h100-r3-w2.json | h100-r3-w2 | 3 | 2 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-northeast3 | ta-01M33SCPSDTFY338T172SGKF0R | None | 6173.998 | 14991.286 |
| h100-r3-w4.json | h100-r3-w4 | 3 | 4 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-northeast1 | ta-01M33SHNP3DR4DWV07T5RGV77R | True | 6805.952 | 20191.939 |
| h100-r3-w8.json | h100-r3-w8 | 3 | 8 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west4 | ta-01M33SDAC53H7P7N9X41F7K71R | True | 8031.936 | 31105.673 |
| h100-r4-w1.json | h100-r4-w1 | 4 | 1 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | ap-northeast | ta-01M33SKAP60MFE32247SG9C5PR | True | 3996.667 | 9563.359 |
| h100-r4-w16.json | h100-r4-w16 | 4 | 16 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-northeast3 | ta-01M33SKRTQZWY8D2MKT1EF5KYR | True | 11893.650 | 62318.328 |
| h100-r4-w2.json | h100-r4-w2 | 4 | 2 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | us-east1-a | ta-01M33SNZCTT2VDRAK7BCKQAMMR | True | 4629.906 | 13996.449 |
| h100-r4-w4.json | h100-r4-w4 | 4 | 4 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | ap-northeast | ta-01M33SJFPPDMQG1M5NSM761Y9R | True | 7419.105 | 21484.487 |
| h100-r4-w8.json | h100-r4-w8 | 4 | 8 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-east | ta-01M33SPVB9M7MTDK9WSDAG3CYR | True | 7011.270 | 32629.800 |
| h100-r5-w1.json | h100-r5-w1 | 5 | 1 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-east | ta-01M33SWGSW46MR46E14V1PRMBR | True | 3926.511 | 11057.118 |
| h100-r5-w16.json | h100-r5-w16 | 5 | 16 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | asia-south2 | ta-01M33SS44GQWE2XCXV2HT1MQHR | True | 9569.387 | 56649.278 |
| h100-r5-w2.json | h100-r5-w2 | 5 | 2 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west4 | ta-01M33SV81BB98REYKGX1ZHJZVR | True | 3824.686 | 12348.659 |
| h100-r5-w4.json | h100-r5-w4 | 5 | 4 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_GCP | us-west | ta-01M33SVS7ZK6EHJK4J11P07XDR | True | 5199.308 | 18737.528 |
| h100-r5-w8.json | h100-r5-w8 | 5 | 8 | NVIDIA H100 80GB HBM3 | CLOUD_PROVIDER_UNSPECIFIED | odin | ta-01M33SR5NKSJY850Z5A4TSTFGR | True | 5138.045 | 25026.489 |
| rtx-r1-w1.json | rtx-r1-w1 | 1 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SCPXKDCXQKNH3MG5YB5XR | None | 2371.585 | 6692.903 |
| rtx-r1-w16.json | rtx-r1-w16 | 1 | 16 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SE9DEPGN1K7CC9S225QGR | True | 4100.396 | 21323.129 |
| rtx-r1-w2.json | rtx-r1-w2 | 1 | 2 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SD0YWDP2DWB0RH0ZTNZAR | True | 3677.416 | 8820.576 |
| rtx-r1-w4.json | rtx-r1-w4 | 1 | 4 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SDCZB9GQ9BY92E5Z18G6R | True | 2220.359 | 9202.296 |
| rtx-r1-w8.json | rtx-r1-w8 | 1 | 8 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SDS8FAZTJNR36ZV3BGSTR | True | 3114.911 | 13557.274 |
| rtx-r2-w1.json | rtx-r2-w1 | 2 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SKNEMQ7SQGNR8GNDCG5HR | True | 1490.774 | 5790.913 |
| rtx-r2-w16.json | rtx-r2-w16 | 2 | 16 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SHRBWK7JD4ERAEHRBSFHR | True | 4101.416 | 21294.982 |
| rtx-r2-w2.json | rtx-r2-w2 | 2 | 2 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SKCCQTNTNF07E2R4QTSVR | True | 1557.667 | 6655.007 |
| rtx-r2-w4.json | rtx-r2-w4 | 2 | 4 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SK0FN37TX5W5X1DS91RWR | True | 2348.207 | 9393.806 |
| rtx-r2-w8.json | rtx-r2-w8 | 2 | 8 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SJGQC7RJEV1YRCJEACC3R | True | 2704.474 | 13018.201 |
| rtx-r3-w1.json | rtx-r3-w1 | 3 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SNMQVT1WYB6YNA6RXYVGR | True | 1593.723 | 5888.958 |
| rtx-r3-w16.json | rtx-r3-w16 | 3 | 16 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SNZSKM73FX5J1D44RV10R | True | 2545.221 | 20766.345 |
| rtx-r3-w2.json | rtx-r3-w2 | 3 | 2 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SKXNZGN3XPWW7V85DDTER | True | 1752.861 | 6818.931 |
| rtx-r3-w4.json | rtx-r3-w4 | 3 | 4 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SSWH8DZSBVBBP0A6CDT6R | True | 2410.664 | 9506.830 |
| rtx-r3-w8.json | rtx-r3-w8 | 3 | 8 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SN4YSR2TY4S1SM8ZG6ZVR | True | 2470.374 | 12451.174 |
| rtx-r4-w1.json | rtx-r4-w1 | 4 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33STZ19CFTQ1YRSBN83SKTR | True | 1552.448 | 5842.136 |
| rtx-r4-w16.json | rtx-r4-w16 | 4 | 16 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SV77X36EZ1K8708J69GQR | True | 2548.705 | 19409.679 |
| rtx-r4-w2.json | rtx-r4-w2 | 4 | 2 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SVXEWVGXPCEFTK9Q036ER | True | 2046.589 | 7295.455 |
| rtx-r4-w4.json | rtx-r4-w4 | 4 | 4 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_AWS | eu-south | ta-01M33ST88RMZVSMKA9WRSAHRZR | True | 4528.046 | 18576.450 |
| rtx-r4-w8.json | rtx-r4-w8 | 4 | 8 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SW89R6C9Q88FMHJ1PJB3R | True | 2916.697 | 13000.518 |
| rtx-r5-w1.json | rtx-r5-w1 | 5 | 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SZEPNPVX74P9H91NVZ0BR | True | 1566.965 | 5840.238 |
| rtx-r5-w16.json | rtx-r5-w16 | 5 | 16 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SX7AKND8N8WZYFACYHTGR | True | 2920.683 | 19874.460 |
| rtx-r5-w2.json | rtx-r5-w2 | 5 | 2 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SYSNXK66GTK2NQG7CRBKR | True | 1787.434 | 6767.985 |
| rtx-r5-w4.json | rtx-r5-w4 | 5 | 4 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SZ2Q1AM8JEAEHBW98A9JR | True | 2671.764 | 9363.665 |
| rtx-r5-w8.json | rtx-r5-w8 | 5 | 8 | NVIDIA RTX PRO 6000 Blackwell Server Edition | CLOUD_PROVIDER_GCP | us-east | ta-01M33SWQP6FXZ8V8WSQTZRQ85R | True | 2333.122 | 12411.585 |

## Integrity and exclusions

- runs included: 50
- distinct block counts observed: [60]
- attempts_alive_after_drain != 0 events: 0
- engine errors: 0
- excluded artifacts: 0
