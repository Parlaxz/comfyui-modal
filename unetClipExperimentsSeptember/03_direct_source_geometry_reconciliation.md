# Experiment 03 Direct-Source Geometry Reconciliation

STATUS=COMPLETE

Counted cohort: **72 / 72** explicit manifest rows.
All conclusions below are derived from the preserved per-run rows in the JSON companion. No requests, deployments, or runtime changes were performed.

## Executive Findings

- Authoritative application wall: `golden_adapter_timing.golden_call_wall_ms` from raw session events. It is the adapter-call wall from `golden_call_start_mono_ns` to `golden_call_end_mono_ns` and includes adapter post-stage work.
- Most likely live 12-14 s display: `Golden call wall [ADAPTER CALL]`, emitted by `comfymodal_runtime/modal_app.py` and backed by `golden_adapter_timing.golden_call_wall_ms`.
- 1024 MiB <13 s runs: 9; 32 MiB <13 s runs: 2.
- The previous report was an extractor/schema omission, not evidence loss: its direct-source branch never read session-event adapter timing or emitted per-run Golden stages.

## Evidence Definitions

- **scheduling_platform_wall:** attempt_artifact.duration_ms; request/invocation wall and not application performance
- **external_restore:** golden_telemetry.external_restore.restore_total_ms; separate from the tiny golden_restore application stage; exact platform boundary is not available in the persisted partial waterfall
- **golden_internal_wall:** raw session event golden_adapter_timing.golden_call_start_mono_ns to golden_call_end_mono_ns, exposed as golden_call_wall_ms; includes adapter post-stage work and persisted telemetry timing
- **serial_stage_sum:** sum of all authoritative serialized Golden stage entry-to-end monotonic walls from raw session-event telemetry
- **unaccounted_golden:** golden_internal_wall_ms - serial_stage_sum_ms; not assumed to be a missing stage
- **loader_total:** clip_load + unet_load + vae_load enclosing stage walls
- **time_local:** manifest cohort rounds compared descriptively; near-contemporaneous means manifest-created timestamps span <=360 seconds; not a randomized paired analysis

## Cohort And Geometry Audit

| geometry | n | CORE | EXTRA | geometry check | all valid | all true cold | all SHA |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12 | 8 | 4 | PASS | true | true | true |
| 64 | 12 | 8 | 4 | PASS | true | true | true |
| 128 | 12 | 8 | 4 | PASS | true | true | true |
| 256 | 12 | 8 | 4 | PASS | true | true | true |
| 512 | 12 | 8 | 4 | PASS | true | true | true |
| 1024 | 12 | 8 | 4 | PASS | true | true | true |

The six arms contain the explicit 72 counted rows. Geometry checks independently verify `source_block_bytes == h2d_target_bytes == logical_slot_bytes == arm_mib *  MiB`, `logical_slot_count == 8`, and aggregation disabled for CLIP, UNET, and VAE.

## Table A - Whole Golden

| geometry | n | mean ms | median ms | SD | CV | min | max | P25 | P75 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12 | 13291.116 | 13281.154 | 317.399 | 0.024 | 12769.139 | 14048.383 | 13141.762 | 13416.598 |
| 64 | 12 | 14041.331 | 12978.602 | 2777.694 | 0.198 | 12030.211 | 20261.011 | 12678.615 | 13661.907 |
| 128 | 12 | 13003.566 | 12514.461 | 1427.758 | 0.110 | 11954.478 | 16733.770 | 12156.550 | 12877.115 |
| 256 | 12 | 12781.249 | 12291.978 | 1739.635 | 0.136 | 11768.165 | 18238.873 | 12237.976 | 12494.372 |
| 512 | 12 | 13220.901 | 12441.497 | 1966.695 | 0.149 | 12095.460 | 19170.139 | 12339.881 | 13102.738 |
| 1024 | 12 | 13158.810 | 12921.393 | 861.849 | 0.065 | 12384.136 | 15557.676 | 12788.258 | 13058.383 |

## Table B - CLIP Load

| geometry | n | mean ms | median ms | SD | CV | min | max | P25 | P75 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12 | 1755.426 | 1759.871 | 136.927 | 0.078 | 1560.178 | 2090.187 | 1684.450 | 1811.639 |
| 64 | 12 | 2304.598 | 1768.162 | 1592.577 | 0.691 | 1402.075 | 6819.630 | 1574.588 | 1870.373 |
| 128 | 12 | 1791.789 | 1690.087 | 447.204 | 0.250 | 1330.891 | 2785.499 | 1571.898 | 1792.860 |
| 256 | 12 | 2083.525 | 1642.239 | 1632.720 | 0.784 | 1436.086 | 7255.241 | 1559.031 | 1687.644 |
| 512 | 12 | 2247.440 | 1803.951 | 1477.520 | 0.657 | 1676.806 | 6928.079 | 1746.055 | 1950.667 |
| 1024 | 12 | 2256.696 | 2189.984 | 351.703 | 0.156 | 1862.887 | 3262.027 | 2145.074 | 2281.338 |

## Table C - UNET Load

| geometry | n | mean ms | median ms | SD | CV | min | max | P25 | P75 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12 | 1891.636 | 1878.839 | 179.190 | 0.095 | 1601.502 | 2120.840 | 1787.802 | 2051.859 |
| 64 | 12 | 2400.713 | 1992.658 | 839.018 | 0.349 | 1549.938 | 4384.452 | 1881.630 | 2602.406 |
| 128 | 12 | 1986.835 | 1940.001 | 282.316 | 0.142 | 1567.420 | 2636.984 | 1840.506 | 2065.829 |
| 256 | 12 | 1866.007 | 1813.026 | 211.221 | 0.113 | 1466.724 | 2168.138 | 1735.518 | 2027.356 |
| 512 | 12 | 2004.014 | 1855.758 | 490.964 | 0.245 | 1574.326 | 3334.074 | 1729.152 | 2059.254 |
| 1024 | 12 | 2131.809 | 2000.621 | 516.250 | 0.242 | 1742.807 | 3675.424 | 1887.091 | 2091.582 |

## Table D - Combined Loader

| geometry | n | mean ms | median ms | SD | CV | min | max | P25 | P75 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12 | 3774.852 | 3805.095 | 259.043 | 0.069 | 3413.410 | 4318.499 | 3595.981 | 3910.660 |
| 64 | 12 | 4865.613 | 3927.614 | 2332.438 | 0.479 | 3058.176 | 10301.226 | 3741.898 | 4446.595 |
| 128 | 12 | 3919.159 | 3692.151 | 772.973 | 0.197 | 3274.677 | 5739.771 | 3392.465 | 3972.187 |
| 256 | 12 | 4057.370 | 3568.433 | 1739.468 | 0.429 | 3049.238 | 9530.462 | 3485.902 | 3810.608 |
| 512 | 12 | 4368.957 | 3746.965 | 1917.448 | 0.439 | 3420.186 | 10366.527 | 3576.264 | 4103.569 |
| 1024 | 12 | 4500.158 | 4306.723 | 847.852 | 0.188 | 3845.253 | 7032.427 | 4126.846 | 4417.140 |

## Stage-Sum Reconciliation

| geometry | stage span median | stage sum median | pre-stage median | post-stage median | span gap median | unaccounted median | unaccounted % median |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | 12216.552 | 12198.291 | 0.710 | 1069.050 | 17.109 | 1088.288 | 8.237 |
| 64 | 12390.741 | 12375.558 | 0.697 | 593.112 | 14.292 | 609.856 | 4.738 |
| 128 | 12154.096 | 12140.070 | 0.735 | 360.188 | 13.945 | 374.972 | 3.016 |
| 256 | 12047.058 | 12033.014 | 0.668 | 248.593 | 13.319 | 262.581 | 2.136 |
| 512 | 12251.765 | 12241.823 | 0.676 | 188.803 | 11.591 | 200.368 | 1.600 |
| 1024 | 12762.258 | 12750.420 | 0.741 | 158.879 | 12.031 | 172.538 | 1.329 |

## Restore And Reconciliation Statistics

| geometry | external restore mean | external restore median | Golden stage sum mean | Golden stage sum median | unaccounted mean | unaccounted median | unaccounted % median |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | 9904.273 | 868.817 | 12201.101 | 12198.291 | 1090.015 | 1088.288 | 8.237 |
| 64 | 8095.809 | 779.561 | 13400.865 | 12375.558 | 640.466 | 609.856 | 4.738 |
| 128 | 9865.057 | 839.497 | 12596.194 | 12140.070 | 407.372 | 374.972 | 3.016 |
| 256 | 2814.010 | 809.364 | 12520.632 | 12033.014 | 260.617 | 262.581 | 2.136 |
| 512 | 567.884 | 567.589 | 13018.028 | 12241.823 | 202.873 | 200.368 | 1.600 |
| 1024 | 7208.031 | 634.539 | 12986.207 | 12750.420 | 172.603 | 172.538 | 1.329 |

## Table E - Compute Stages

| geometry | clip_forward median | sampling median | decode median |
|---|---:|---:|---:|
| 32 | 1392.381 | 5960.062 | 531.670 |
| 64 | 1375.246 | 6014.723 | 528.611 |
| 128 | 1394.025 | 6026.100 | 526.716 |
| 256 | 1412.469 | 6025.197 | 531.048 |
| 512 | 1404.320 | 6101.096 | 527.144 |
| 1024 | 1408.031 | 6041.740 | 528.949 |

## Table F - Loader Residuals

| geometry | CLIP load - source->ready median | UNET load - source->ready median | CLIP load - source median | UNET load - source median |
|---|---:|---:|---:|---:|
| 32 | 768.652 | 364.430 | 770.443 | 366.478 |
| 64 | 578.012 | 223.366 | 581.569 | 225.517 |
| 128 | 489.673 | 146.695 | 494.198 | 152.652 |
| 256 | 514.315 | 110.591 | 518.826 | 115.788 |
| 512 | 623.852 | 81.171 | 644.394 | 93.884 |
| 1024 | 867.838 | 80.644 | 901.723 | 100.371 |

### Source Versus Enclosing Load

| geometry | CLIP source median | CLIP load median | CLIP residual median | UNET source median | UNET load median | UNET residual median |
|---|---:|---:|---:|---:|---:|---:|
| 32 | 989.790 | 1759.871 | 770.443 | 1517.348 | 1878.839 | 366.478 |
| 64 | 1182.350 | 1768.162 | 581.569 | 1773.854 | 1992.658 | 225.517 |
| 128 | 1200.764 | 1690.087 | 494.198 | 1787.350 | 1940.001 | 152.652 |
| 256 | 1134.168 | 1642.239 | 518.826 | 1695.244 | 1813.026 | 115.788 |
| 512 | 1165.471 | 1803.951 | 644.394 | 1759.096 | 1855.758 | 93.884 |
| 1024 | 1281.995 | 2189.984 | 901.723 | 1905.777 | 2000.621 | 100.371 |

## Table G - CORE Versus EXTRA

| geometry | CORE Golden median | EXTRA Golden median | ALL Golden median | CORE clip median | EXTRA clip median | CORE UNET median | EXTRA UNET median |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | 13332.668 | 13218.912 | 13281.154 | 1759.871 | 1751.572 | 1878.839 | 1896.361 |
| 64 | 13261.164 | 12902.522 | 12978.602 | 1818.514 | 1664.882 | 2126.077 | 1992.658 |
| 128 | 12560.149 | 12508.058 | 12514.461 | 1657.666 | 1701.852 | 2004.065 | 1870.351 |
| 256 | 12252.301 | 12359.509 | 12291.978 | 1626.240 | 1653.747 | 1813.026 | 1794.473 |
| 512 | 12746.287 | 12373.772 | 12441.497 | 1919.213 | 1756.967 | 1938.002 | 1814.541 |
| 1024 | 12866.106 | 12944.539 | 12921.393 | 2156.150 | 2247.962 | 1967.284 | 2000.621 |

## Table H - Provider / Region

| provider / region | n | Golden median | Golden mean | CLIP median | UNET median | sampling median | CLIP forward median |
|---|---:|---:|---:|---:|---:|---:|---:|
| CLOUD_PROVIDER_AWS / eu-south-2 | 1 | 20261.011 | 20261.011 | 4104.243 | 4384.452 | 6414.705 | 2380.289 |
| CLOUD_PROVIDER_GCP / us-central1 | 5 | 14049.305 | 15577.270 | 2434.204 | 2367.555 | 6074.920 | 1408.348 |
| CLOUD_PROVIDER_GCP / us-east1 | 62 | 12726.059 | 12876.361 | 1745.303 | 1888.214 | 6010.663 | 1399.753 |
| CLOUD_PROVIDER_GCP / us-east4 | 4 | 13737.431 | 14370.475 | 2057.519 | 2033.696 | 6040.834 | 1546.677 |

### Geometry By Provider / Region

| geometry | provider / region | n | Golden median | CLIP median | UNET median | sampling median | CLIP forward median |
|---|---:|---:|---:|---:|---:|---:|---:|
| 32 | CLOUD_PROVIDER_GCP / us-central1 | 1 | 14048.383 | 2090.187 | 2120.840 | 5962.643 | 1408.348 |
| 32 | CLOUD_PROVIDER_GCP / us-east1 | 11 | 13266.547 | 1742.034 | 1862.459 | 5957.480 | 1384.754 |
| 64 | CLOUD_PROVIDER_AWS / eu-south-2 | 1 | 20261.011 | 4104.243 | 4384.452 | 6414.705 | 2380.289 |
| 64 | CLOUD_PROVIDER_GCP / us-central1 | 2 | 16527.447 | 4330.169 | 2869.527 | 6055.774 | 1355.320 |
| 64 | CLOUD_PROVIDER_GCP / us-east1 | 9 | 12797.104 | 1587.949 | 1900.768 | 6004.319 | 1366.036 |
| 128 | CLOUD_PROVIDER_GCP / us-central1 | 1 | 16733.770 | 2580.510 | 2300.083 | 7058.510 | 2237.709 |
| 128 | CLOUD_PROVIDER_GCP / us-east1 | 11 | 12441.179 | 1654.509 | 1917.688 | 6009.006 | 1376.560 |
| 256 | CLOUD_PROVIDER_GCP / us-east1 | 10 | 12291.978 | 1642.239 | 1813.026 | 6040.150 | 1407.774 |
| 256 | CLOUD_PROVIDER_GCP / us-east4 | 2 | 15003.519 | 4369.659 | 1817.431 | 5980.857 | 1487.818 |
| 512 | CLOUD_PROVIDER_GCP / us-east1 | 11 | 12434.290 | 1794.921 | 1855.673 | 6091.776 | 1401.550 |
| 512 | CLOUD_PROVIDER_GCP / us-east4 | 1 | 14236.807 | 1892.304 | 2020.331 | 6475.061 | 1684.825 |
| 1024 | CLOUD_PROVIDER_GCP / us-central1 | 1 | 14049.305 | 2434.204 | 2380.350 | 6124.771 | 1616.383 |
| 1024 | CLOUD_PROVIDER_GCP / us-east1 | 10 | 12866.106 | 2156.868 | 1960.264 | 6032.083 | 1402.875 |
| 1024 | CLOUD_PROVIDER_GCP / us-east4 | 1 | 13238.055 | 2222.735 | 2047.061 | 6082.980 | 1528.044 |

## Table I - Median Decomposition Versus 32 MiB

Positive deltas mean the target is slower than 32 MiB; negative deltas mean faster. All values are target median minus 32 MiB median.

| metric | 256 - 32 ms | 512 - 32 ms | 1024 - 32 ms |
|---|---:|---:|---:|
| combined_loader_wall_ms | -236.661 | -58.130 | 501.628 |
| golden_internal_wall_ms | -989.176 | -839.657 | -359.761 |
| golden_post_stage_overhead_ms | -820.457 | -880.247 | -910.171 |
| golden_pre_stage_overhead_ms | -0.041 | -0.034 | 0.031 |
| golden_stage_span_ms | -169.493 | 35.214 | 545.707 |
| golden_stage_sum_ms | -165.277 | 43.532 | 552.129 |
| clip_forward | 20.088 | 11.939 | 15.649 |
| clip_load | -117.631 | 44.081 | 430.113 |
| golden_restore | -0.112 | -0.061 | 0.035 |
| output | -0.515 | -1.050 | -0.771 |
| request_setup | 0.020 | -0.043 | 0.200 |
| sampler_prepare | -57.562 | 5.908 | -29.813 |
| sampler_tail | 0.001 | -0.000 | 0.000 |
| sampling | 65.136 | 141.034 | 81.678 |
| teardown | 0.049 | 0.007 | 0.014 |
| unet_load | -65.813 | -23.081 | 121.782 |
| vae_decode | -0.622 | -4.526 | -2.721 |
| vae_load | -19.567 | -11.372 | -14.302 |
| stage_span_gap_ms | -3.790 | -5.518 | -5.078 |
| unaccounted_golden_ms | -825.707 | -887.920 | -915.750 |
| unaccounted_golden_percent | -6.101 | -6.638 | -6.908 |

### Table I Percentage Deltas

| metric | 256 - 32 % | 512 - 32 % | 1024 - 32 % |
|---|---:|---:|---:|
| combined_loader_wall_ms | -6.220 | -1.528 | 13.183 |
| golden_internal_wall_ms | -7.448 | -6.322 | -2.709 |
| golden_post_stage_overhead_ms | -76.746 | -82.339 | -85.138 |
| golden_pre_stage_overhead_ms | -5.849 | -4.722 | 4.440 |
| golden_stage_span_ms | -1.387 | 0.288 | 4.467 |
| golden_stage_sum_ms | -1.355 | 0.357 | 4.526 |
| clip_forward | 1.443 | 0.857 | 1.124 |
| clip_load | -6.684 | 2.505 | 24.440 |
| golden_restore | -1.229 | -0.666 | 0.382 |
| output | -0.316 | -0.644 | -0.472 |
| request_setup | 1.480 | -3.261 | 15.100 |
| sampler_prepare | -17.306 | 1.776 | -8.963 |
| sampler_tail | 9.587 | -2.381 | 0.440 |
| sampling | 1.093 | 2.366 | 1.370 |
| teardown | 15.808 | 2.351 | 4.596 |
| unet_load | -3.503 | -1.228 | 6.482 |
| vae_decode | -0.117 | -0.851 | -0.512 |
| vae_load | -15.395 | -8.948 | -11.252 |
| stage_span_gap_ms | -22.152 | -32.250 | -29.679 |
| unaccounted_golden_ms | -75.872 | -81.589 | -84.146 |
| unaccounted_golden_percent | -74.067 | -80.579 | -83.863 |

## Rankings

### Whole Golden adapter call

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 12291.978 | 12781.249 | 1739.635 | 0.136 | 11768.165 | 18238.873 |
| 2 | 512 | 12441.497 | 13220.901 | 1966.695 | 0.149 | 12095.460 | 19170.139 |
| 3 | 128 | 12514.461 | 13003.566 | 1427.758 | 0.110 | 11954.478 | 16733.770 |
| 4 | 1024 | 12921.393 | 13158.810 | 861.849 | 0.065 | 12384.136 | 15557.676 |
| 5 | 64 | 12978.602 | 14041.331 | 2777.694 | 0.198 | 12030.211 | 20261.011 |
| 6 | 32 | 13281.154 | 13291.116 | 317.399 | 0.024 | 12769.139 | 14048.383 |

### Golden stage span

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 12047.058 | 12533.594 | 1738.087 | 0.139 | 11529.678 | 17988.623 |
| 2 | 128 | 12154.096 | 12609.349 | 1351.314 | 0.107 | 11569.503 | 16033.706 |
| 3 | 32 | 12216.552 | 12217.668 | 301.238 | 0.025 | 11707.739 | 12901.418 |
| 4 | 512 | 12251.765 | 13029.495 | 1965.486 | 0.151 | 11909.330 | 18979.777 |
| 5 | 64 | 12390.741 | 13415.069 | 2722.065 | 0.203 | 11443.919 | 19409.562 |
| 6 | 1024 | 12762.258 | 12998.468 | 864.281 | 0.066 | 12224.343 | 15405.064 |

### Golden stage sum

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 12033.014 | 12520.632 | 1737.873 | 0.139 | 11517.430 | 17975.305 |
| 2 | 128 | 12140.070 | 12596.194 | 1352.533 | 0.107 | 11558.278 | 16026.166 |
| 3 | 32 | 12198.291 | 12201.101 | 300.933 | 0.025 | 11693.862 | 12886.429 |
| 4 | 512 | 12241.823 | 13018.028 | 1966.474 | 0.151 | 11897.200 | 18971.039 |
| 5 | 64 | 12375.558 | 13400.865 | 2721.920 | 0.203 | 11432.604 | 19397.078 |
| 6 | 1024 | 12750.420 | 12986.207 | 864.202 | 0.067 | 12211.656 | 15391.512 |

### CLIP load

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 1642.239 | 2083.525 | 1632.720 | 0.784 | 1436.086 | 7255.241 |
| 2 | 128 | 1690.087 | 1791.789 | 447.204 | 0.250 | 1330.891 | 2785.499 |
| 3 | 32 | 1759.871 | 1755.426 | 136.927 | 0.078 | 1560.178 | 2090.187 |
| 4 | 64 | 1768.162 | 2304.598 | 1592.577 | 0.691 | 1402.075 | 6819.630 |
| 5 | 512 | 1803.951 | 2247.440 | 1477.520 | 0.657 | 1676.806 | 6928.079 |
| 6 | 1024 | 2189.984 | 2256.696 | 351.703 | 0.156 | 1862.887 | 3262.027 |

### UNET load

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 1813.026 | 1866.007 | 211.221 | 0.113 | 1466.724 | 2168.138 |
| 2 | 512 | 1855.758 | 2004.014 | 490.964 | 0.245 | 1574.326 | 3334.074 |
| 3 | 32 | 1878.839 | 1891.636 | 179.190 | 0.095 | 1601.502 | 2120.840 |
| 4 | 128 | 1940.001 | 1986.835 | 282.316 | 0.142 | 1567.420 | 2636.984 |
| 5 | 64 | 1992.658 | 2400.713 | 839.018 | 0.349 | 1549.938 | 4384.452 |
| 6 | 1024 | 2000.621 | 2131.809 | 516.250 | 0.242 | 1742.807 | 3675.424 |

### Combined loader

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 3568.433 | 4057.370 | 1739.468 | 0.429 | 3049.238 | 9530.462 |
| 2 | 128 | 3692.151 | 3919.159 | 772.973 | 0.197 | 3274.677 | 5739.771 |
| 3 | 512 | 3746.965 | 4368.957 | 1917.448 | 0.439 | 3420.186 | 10366.527 |
| 4 | 32 | 3805.095 | 3774.852 | 259.043 | 0.069 | 3413.410 | 4318.499 |
| 5 | 64 | 3927.614 | 4865.613 | 2332.438 | 0.479 | 3058.176 | 10301.226 |
| 6 | 1024 | 4306.723 | 4500.158 | 847.852 | 0.188 | 3845.253 | 7032.427 |

### CLIP source wall

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 32 | 989.790 | 989.359 | 121.593 | 0.123 | 828.410 | 1287.308 |
| 2 | 256 | 1134.168 | 1563.859 | 1623.244 | 1.038 | 894.594 | 6704.588 |
| 3 | 512 | 1165.471 | 1602.201 | 1475.961 | 0.921 | 1048.825 | 6280.071 |
| 4 | 64 | 1182.350 | 1648.175 | 1499.548 | 0.910 | 821.023 | 6219.698 |
| 5 | 128 | 1200.764 | 1220.985 | 292.526 | 0.240 | 830.770 | 1814.632 |
| 6 | 1024 | 1281.995 | 1353.415 | 347.246 | 0.257 | 938.985 | 2346.265 |

### UNET source wall

| rank | geometry | median | mean | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 32 | 1517.348 | 1524.577 | 181.392 | 0.119 | 1224.320 | 1760.627 |
| 2 | 256 | 1695.244 | 1749.748 | 214.319 | 0.122 | 1360.042 | 2055.400 |
| 3 | 512 | 1759.096 | 1906.982 | 489.470 | 0.257 | 1489.487 | 3241.698 |
| 4 | 64 | 1773.854 | 2104.728 | 670.176 | 0.318 | 1332.018 | 3282.716 |
| 5 | 128 | 1787.350 | 1797.539 | 212.412 | 0.118 | 1417.620 | 2227.516 |
| 6 | 1024 | 1905.777 | 2016.325 | 502.611 | 0.249 | 1623.676 | 3537.608 |

### Top Three CLIP Geometries

| rank | geometry | mean | median | SD | CV | min | max | source wall median | H2D wall median | GPU active median | copy count median | arena bytes median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 2083.525 | 1642.239 | 1632.720 | 0.784 | 1436.086 | 7255.241 | 1134.168 | 1062.975 | 235.245 | 33.000 | 2147483648.000 |
| 2 | 128 | 1791.789 | 1690.087 | 447.204 | 0.250 | 1330.891 | 2785.499 | 1200.764 | 1164.311 | 186.508 | 63.000 | 1073741824.000 |
| 3 | 32 | 1755.426 | 1759.871 | 136.927 | 0.078 | 1560.178 | 2090.187 | 989.790 | 978.827 | 221.978 | 243.000 | 268435456.000 |

### Top Three UNET Geometries

| rank | geometry | mean | median | SD | CV | min | max | source wall median | H2D wall median | GPU active median | copy count median | arena bytes median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 1866.007 | 1813.026 | 211.221 | 0.113 | 1466.724 | 2168.138 | 1695.244 | 1651.982 | 267.877 | 49.000 | 2147483648.000 |
| 2 | 512 | 2004.014 | 1855.758 | 490.964 | 0.245 | 1574.326 | 3334.074 | 1759.096 | 1660.103 | 332.553 | 26.000 | 4294967296.000 |
| 3 | 32 | 1891.636 | 1878.839 | 179.190 | 0.095 | 1601.502 | 2120.840 | 1517.348 | 1506.136 | 407.057 | 370.000 | 268435456.000 |

### Top Three Whole-Golden Geometries

| rank | geometry | mean | median | SD | CV | min | max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 256 | 12781.249 | 12291.978 | 1739.635 | 0.136 | 11768.165 | 18238.873 |
| 2 | 512 | 13220.901 | 12441.497 | 1966.695 | 0.149 | 12095.460 | 19170.139 |
| 3 | 128 | 13003.566 | 12514.461 | 1427.758 | 0.110 | 11954.478 | 16733.770 |

## Transport Operation Counts

Counts are extracted from the raw per-role transport records. Missing counters remain unavailable; no count is inferred from elapsed time.

| geometry | role | source reads | H2D submits | event objects | event rerecords | GPU copies | producers | source blocks | max source inflight |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | CLIP | 243.000 | 243.000 | 18.000 | 470.000 | 243.000 | 4.000 | 243.000 | 4.000 |
| 32 | UNET | 370.000 | 370.000 | 18.000 | 1210.000 | 370.000 | 4.000 | 370.000 | 4.000 |
| 32 | VAE | 13.000 | 13.000 | 18.000 | 1236.000 | 13.000 | 4.000 | 13.000 | 4.000 |
| 64 | CLIP | 123.000 | 123.000 | 18.000 | 230.000 | 123.000 | 4.000 | 123.000 | 4.000 |
| 64 | UNET | 187.000 | 187.000 | 18.000 | 604.000 | 187.000 | 4.000 | 187.000 | 4.000 |
| 64 | VAE | 8.000 | 8.000 | 18.000 | 620.000 | 8.000 | 4.000 | 8.000 | 3.000 |
| 128 | CLIP | 63.000 | 63.000 | 18.000 | 110.000 | 63.000 | 4.000 | 63.000 | 4.000 |
| 128 | UNET | 95.000 | 95.000 | 18.000 | 300.000 | 95.000 | 4.000 | 95.000 | 4.000 |
| 128 | VAE | 6.000 | 6.000 | 18.000 | 312.000 | 6.000 | 4.000 | 6.000 | 2.000 |
| 256 | CLIP | 33.000 | 33.000 | 18.000 | 50.000 | 33.000 | 4.000 | 33.000 | 4.000 |
| 256 | UNET | 49.000 | 49.000 | 18.000 | 148.000 | 49.000 | 4.000 | 49.000 | 4.000 |
| 256 | VAE | 5.000 | 5.000 | 18.000 | 158.000 | 5.000 | 4.000 | 5.000 | 1.500 |
| 512 | CLIP | 18.000 | 18.000 | 18.000 | 20.000 | 18.000 | 4.000 | 18.000 | 4.000 |
| 512 | UNET | 26.000 | 26.000 | 18.000 | 72.000 | 26.000 | 4.000 | 26.000 | 4.000 |
| 512 | VAE | 4.000 | 4.000 | 18.000 | 80.000 | 4.000 | 4.000 | 4.000 | 2.000 |
| 1024 | CLIP | 11.000 | 11.000 | 18.000 | 6.000 | 11.000 | 4.000 | 11.000 | 3.000 |
| 1024 | UNET | 15.000 | 15.000 | 18.000 | 36.000 | 15.000 | 4.000 | 15.000 | 4.000 |
| 1024 | VAE | 4.000 | 4.000 | 18.000 | 44.000 | 4.000 | 4.000 | 4.000 | 1.500 |

## Golden-Wall Buckets

Buckets use the authoritative adapter-call wall. Bounds are lower-inclusive and upper-exclusive except the first/last buckets.

### 32 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 0 |  |
| 12.0-12.5 s | 0 |  |
| 12.5-13.0 s | 2 | 32_02=12769.139ms CLOUD_PROVIDER_GCP/us-east1; 32_06=12946.083ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 9 | 32_01=13398.789ms CLOUD_PROVIDER_GCP/us-east1; 32_03=13434.636ms CLOUD_PROVIDER_GCP/us-east1; 32_04=13266.547ms CLOUD_PROVIDER_GCP/us-east1; 32_05=13477.777ms CLOUD_PROVIDER_GCP/us-east1; 32_08=13162.768ms CLOUD_PROVIDER_GCP/us-east1; 32_09=13295.760ms CLOUD_PROVIDER_GCP/us-east1; 32_10=13410.585ms CLOUD_PROVIDER_GCP/us-east1; 32_11=13142.064ms CLOUD_PROVIDER_GCP/us-east1; 32_12=13140.856ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.5-14.0 s | 0 |  |
| 14.0-15.0 s | 1 | 32_07=14048.383ms CLOUD_PROVIDER_GCP/us-central1 |
| > 15.0 s | 0 |  |

### 64 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 0 |  |
| 12.0-12.5 s | 2 | 64_03=12030.211ms CLOUD_PROVIDER_GCP/us-east1; 64_09=12173.738ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.5-13.0 s | 4 | 64_04=12949.264ms CLOUD_PROVIDER_GCP/us-east1; 64_05=12725.641ms CLOUD_PROVIDER_GCP/us-east1; 64_06=12537.537ms CLOUD_PROVIDER_GCP/us-east1; 64_10=12797.104ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 2 | 64_11=13007.940ms CLOUD_PROVIDER_GCP/us-east1; 64_12=13030.190ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.5-14.0 s | 2 | 64_02=13928.437ms CLOUD_PROVIDER_GCP/us-east1; 64_08=13573.064ms CLOUD_PROVIDER_GCP/us-central1 |
| 14.0-15.0 s | 0 |  |
| > 15.0 s | 2 | 64_01=20261.011ms CLOUD_PROVIDER_AWS/eu-south-2; 64_07=19481.830ms CLOUD_PROVIDER_GCP/us-central1 |

### 128 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 1 | 128_03=11954.478ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.0-12.5 s | 5 | 128_02=12170.071ms CLOUD_PROVIDER_GCP/us-east1; 128_06=12115.985ms CLOUD_PROVIDER_GCP/us-east1; 128_08=12441.179ms CLOUD_PROVIDER_GCP/us-east1; 128_09=12032.824ms CLOUD_PROVIDER_GCP/us-east1; 128_12=12428.374ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.5-13.0 s | 3 | 128_04=12679.119ms CLOUD_PROVIDER_GCP/us-east1; 128_10=12808.075ms CLOUD_PROVIDER_GCP/us-east1; 128_11=12587.742ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 1 | 128_05=13084.235ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.5-14.0 s | 0 |  |
| 14.0-15.0 s | 0 |  |
| > 15.0 s | 2 | 128_01=15006.945ms CLOUD_PROVIDER_GCP/us-east1; 128_07=16733.770ms CLOUD_PROVIDER_GCP/us-central1 |

### 256 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 2 | 256_05=11881.104ms CLOUD_PROVIDER_GCP/us-east1; 256_06=11768.165ms CLOUD_PROVIDER_GCP/us-east4 |
| 12.0-12.5 s | 7 | 256_01=12206.379ms CLOUD_PROVIDER_GCP/us-east1; 256_03=12447.813ms CLOUD_PROVIDER_GCP/us-east1; 256_07=12249.154ms CLOUD_PROVIDER_GCP/us-east1; 256_08=12255.447ms CLOUD_PROVIDER_GCP/us-east1; 256_09=12328.509ms CLOUD_PROVIDER_GCP/us-east1; 256_10=12248.508ms CLOUD_PROVIDER_GCP/us-east1; 256_11=12390.509ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.5-13.0 s | 2 | 256_02=12726.478ms CLOUD_PROVIDER_GCP/us-east1; 256_12=12634.048ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 0 |  |
| 13.5-14.0 s | 0 |  |
| 14.0-15.0 s | 0 |  |
| > 15.0 s | 1 | 256_04=18238.873ms CLOUD_PROVIDER_GCP/us-east4 |

### 512 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 0 |  |
| 12.0-12.5 s | 7 | 512_04=12434.290ms CLOUD_PROVIDER_GCP/us-east1; 512_05=12197.977ms CLOUD_PROVIDER_GCP/us-east1; 512_07=12300.614ms CLOUD_PROVIDER_GCP/us-east1; 512_08=12448.704ms CLOUD_PROVIDER_GCP/us-east1; 512_10=12394.575ms CLOUD_PROVIDER_GCP/us-east1; 512_11=12095.460ms CLOUD_PROVIDER_GCP/us-east1; 512_12=12352.970ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.5-13.0 s | 1 | 512_09=12696.065ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 2 | 512_01=13279.339ms CLOUD_PROVIDER_GCP/us-east1; 512_06=13043.871ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.5-14.0 s | 0 |  |
| 14.0-15.0 s | 1 | 512_02=14236.807ms CLOUD_PROVIDER_GCP/us-east4 |
| > 15.0 s | 1 | 512_03=19170.139ms CLOUD_PROVIDER_GCP/us-east1 |

### 1024 MiB

| bucket | count | attempt IDs / values / provider / region |
|---|---:|---:|
| < 12.0 s | 0 |  |
| 12.0-12.5 s | 2 | 1024_04=12497.513ms CLOUD_PROVIDER_GCP/us-east1; 1024_06=12384.136ms CLOUD_PROVIDER_GCP/us-east1 |
| 12.5-13.0 s | 7 | 1024_02=12762.369ms CLOUD_PROVIDER_GCP/us-east1; 1024_07=12900.222ms CLOUD_PROVIDER_GCP/us-east1; 1024_08=12831.990ms CLOUD_PROVIDER_GCP/us-east1; 1024_09=12998.492ms CLOUD_PROVIDER_GCP/us-east1; 1024_10=12946.514ms CLOUD_PROVIDER_GCP/us-east1; 1024_11=12796.888ms CLOUD_PROVIDER_GCP/us-east1; 1024_12=12942.564ms CLOUD_PROVIDER_GCP/us-east1 |
| 13.0-13.5 s | 1 | 1024_01=13238.055ms CLOUD_PROVIDER_GCP/us-east4 |
| 13.5-14.0 s | 0 |  |
| 14.0-15.0 s | 1 | 1024_05=14049.305ms CLOUD_PROVIDER_GCP/us-central1 |
| > 15.0 s | 1 | 1024_03=15557.676ms CLOUD_PROVIDER_GCP/us-east1 |

## Raw Sorted Values

### 32 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_02 | 12769.139 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_06 | 12946.083 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_12 | 13140.856 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_11 | 13142.064 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_08 | 13162.768 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_04 | 13266.547 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_09 | 13295.760 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_01 | 13398.789 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_10 | 13410.585 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_03 | 13434.636 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_05 | 13477.777 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_07 | 14048.383 | CLOUD_PROVIDER_GCP | us-central1 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_02 | 3413.410 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_06 | 3465.926 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_01 | 3501.622 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_12 | 3627.433 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_08 | 3664.318 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_09 | 3796.494 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_11 | 3813.696 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_04 | 3836.621 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_10 | 3896.156 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_05 | 3954.175 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_03 | 4009.881 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_07 | 4318.499 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_02 | 1560.178 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_11 | 1587.575 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_08 | 1656.439 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_12 | 1693.788 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_06 | 1722.728 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_01 | 1742.034 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_03 | 1777.707 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_05 | 1780.242 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_09 | 1809.356 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_10 | 1818.490 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_04 | 1826.383 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_07 | 2090.187 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_06 | 1601.502 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_01 | 1639.504 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_02 | 1731.839 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_12 | 1806.456 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_09 | 1842.064 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_04 | 1862.459 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_08 | 1895.219 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_10 | 1950.658 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_05 | 2035.905 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_03 | 2099.722 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_11 | 2113.464 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_07 | 2120.840 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_03 | 5910.253 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_11 | 5911.915 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_09 | 5915.412 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_10 | 5948.989 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_04 | 5953.954 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_06 | 5957.480 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_07 | 5962.643 | CLOUD_PROVIDER_GCP | us-central1 |
| 8 | 32_08 | 5970.270 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_02 | 5973.793 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_05 | 6004.256 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_12 | 6010.077 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_01 | 6236.521 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_11 | 1296.150 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_02 | 1327.688 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_05 | 1351.376 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_03 | 1354.347 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_04 | 1373.582 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_12 | 1384.754 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_08 | 1400.009 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_06 | 1404.849 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_07 | 1408.348 | CLOUD_PROVIDER_GCP | us-central1 |
| 10 | 32_10 | 1412.456 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_09 | 1457.750 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_01 | 1519.233 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 32_09 | 519.656 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 32_05 | 522.082 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 32_11 | 522.249 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 32_02 | 525.654 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 32_08 | 529.942 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 32_03 | 530.700 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 32_06 | 532.640 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 32_12 | 533.257 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 32_04 | 545.903 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 32_01 | 563.326 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 32_10 | 566.297 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 32_07 | 607.828 | CLOUD_PROVIDER_GCP | us-central1 |

### 64 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_03 | 12030.211 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_09 | 12173.738 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_06 | 12537.537 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_05 | 12725.641 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_10 | 12797.104 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_04 | 12949.264 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_11 | 13007.940 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_12 | 13030.190 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 64_08 | 13573.064 | CLOUD_PROVIDER_GCP | us-central1 |
| 10 | 64_02 | 13928.437 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_07 | 19481.830 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 64_01 | 20261.011 | CLOUD_PROVIDER_AWS | eu-south-2 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_03 | 3058.176 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_06 | 3546.621 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_09 | 3568.711 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_05 | 3799.627 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_10 | 3833.971 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_12 | 3917.039 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_04 | 3938.188 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_11 | 4077.398 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 64_08 | 4316.375 | CLOUD_PROVIDER_GCP | us-central1 |
| 10 | 64_02 | 4837.258 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_01 | 9192.764 | CLOUD_PROVIDER_AWS | eu-south-2 |
| 12 | 64_07 | 10301.226 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_03 | 1402.075 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_02 | 1476.395 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_09 | 1549.072 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_06 | 1583.094 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_11 | 1587.949 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_12 | 1741.816 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_10 | 1794.507 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_05 | 1796.320 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 64_08 | 1840.707 | CLOUD_PROVIDER_GCP | us-central1 |
| 10 | 64_04 | 1959.370 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_01 | 4104.243 | CLOUD_PROVIDER_AWS | eu-south-2 |
| 12 | 64_07 | 6819.630 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_03 | 1549.938 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_06 | 1860.283 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_04 | 1872.722 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_05 | 1884.599 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_10 | 1900.768 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_09 | 1914.305 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_12 | 2071.010 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_08 | 2367.555 | CLOUD_PROVIDER_GCP | us-central1 |
| 9 | 64_11 | 2389.101 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 64_02 | 3242.321 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_07 | 3371.499 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 64_01 | 4384.452 | CLOUD_PROVIDER_AWS | eu-south-2 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_09 | 5800.032 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_05 | 5926.987 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_10 | 5942.716 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_06 | 5997.791 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_04 | 6004.319 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_11 | 6005.625 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_02 | 6023.820 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_07 | 6036.627 | CLOUD_PROVIDER_GCP | us-central1 |
| 9 | 64_03 | 6068.937 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 64_08 | 6074.920 | CLOUD_PROVIDER_GCP | us-central1 |
| 11 | 64_12 | 6095.346 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 64_01 | 6414.705 | CLOUD_PROVIDER_AWS | eu-south-2 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_09 | 1271.669 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_08 | 1326.185 | CLOUD_PROVIDER_GCP | us-central1 |
| 3 | 64_11 | 1336.653 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_03 | 1343.162 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_05 | 1355.930 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_06 | 1366.036 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_07 | 1384.455 | CLOUD_PROVIDER_GCP | us-central1 |
| 8 | 64_04 | 1399.546 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 64_02 | 1408.789 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 64_10 | 1415.364 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_12 | 1429.080 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 64_01 | 2380.289 | CLOUD_PROVIDER_AWS | eu-south-2 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 64_09 | 509.199 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 64_03 | 519.712 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 64_12 | 520.745 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 64_10 | 523.036 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 64_05 | 528.213 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 64_11 | 528.469 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 64_02 | 528.752 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 64_04 | 528.925 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 64_08 | 529.557 | CLOUD_PROVIDER_GCP | us-central1 |
| 10 | 64_06 | 534.068 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 64_07 | 604.732 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 64_01 | 690.015 | CLOUD_PROVIDER_AWS | eu-south-2 |

### 128 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_03 | 11954.478 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_09 | 12032.824 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_06 | 12115.985 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_02 | 12170.071 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_12 | 12428.374 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_08 | 12441.179 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_11 | 12587.742 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_04 | 12679.119 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_10 | 12808.075 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_05 | 13084.235 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_01 | 15006.945 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 128_07 | 16733.770 | CLOUD_PROVIDER_GCP | us-central1 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_09 | 3274.677 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_03 | 3297.628 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_06 | 3341.181 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_02 | 3409.560 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_08 | 3539.729 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_12 | 3591.809 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_11 | 3792.492 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_10 | 3898.055 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_05 | 3961.032 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_04 | 4005.651 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_07 | 5178.317 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 128_01 | 5739.771 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_02 | 1330.891 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_06 | 1345.105 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_03 | 1518.591 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_08 | 1589.667 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_09 | 1604.042 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_12 | 1654.509 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_05 | 1725.665 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_10 | 1749.195 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_11 | 1776.822 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_04 | 1840.974 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_07 | 2580.510 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 128_01 | 2785.499 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_09 | 1567.420 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_03 | 1680.228 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_12 | 1823.013 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_08 | 1846.337 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_06 | 1895.593 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_11 | 1917.688 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_02 | 1962.314 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_10 | 2040.670 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_04 | 2045.816 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_05 | 2125.869 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_07 | 2300.083 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 128_01 | 2636.984 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_04 | 5862.834 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_03 | 5921.656 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_02 | 5932.391 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_09 | 5941.708 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_11 | 5986.853 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_08 | 6009.006 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_06 | 6043.194 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_12 | 6084.421 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_10 | 6094.303 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_01 | 6123.592 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_05 | 6266.166 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 128_07 | 7058.510 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_03 | 1328.118 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_06 | 1355.667 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_02 | 1361.192 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_05 | 1370.800 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_12 | 1375.110 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_08 | 1376.560 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_10 | 1411.490 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_11 | 1425.260 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_09 | 1429.063 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_04 | 1439.155 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_01 | 1613.829 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 128_07 | 2237.709 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 128_12 | 505.365 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 128_05 | 508.688 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 128_04 | 521.789 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 128_06 | 524.140 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 128_11 | 524.317 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 128_09 | 524.351 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 128_10 | 529.080 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 128_03 | 550.480 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 128_01 | 554.982 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 128_08 | 567.039 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 128_02 | 592.782 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 128_07 | 676.030 | CLOUD_PROVIDER_GCP | us-central1 |

### 256 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_06 | 11768.165 | CLOUD_PROVIDER_GCP | us-east4 |
| 2 | 256_05 | 11881.104 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_01 | 12206.379 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_10 | 12248.508 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_07 | 12249.154 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_08 | 12255.447 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_09 | 12328.509 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_11 | 12390.509 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_03 | 12447.813 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_12 | 12634.048 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_02 | 12726.478 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_04 | 18238.873 | CLOUD_PROVIDER_GCP | us-east4 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_06 | 3049.238 | CLOUD_PROVIDER_GCP | us-east4 |
| 2 | 256_05 | 3334.370 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_01 | 3370.898 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_09 | 3524.236 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_08 | 3533.358 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_10 | 3563.537 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_07 | 3573.330 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_11 | 3686.844 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_02 | 3796.826 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_03 | 3851.954 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_12 | 3873.384 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_04 | 9530.462 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_05 | 1436.086 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 256_01 | 1447.314 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_06 | 1484.077 | CLOUD_PROVIDER_GCP | us-east4 |
| 4 | 256_03 | 1584.016 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_10 | 1612.811 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_12 | 1616.016 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_07 | 1668.463 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_08 | 1685.511 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_02 | 1686.366 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_09 | 1691.478 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_11 | 1834.920 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_04 | 7255.241 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_06 | 1466.724 | CLOUD_PROVIDER_GCP | us-east4 |
| 2 | 256_09 | 1724.778 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_08 | 1733.599 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_11 | 1736.158 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_05 | 1797.561 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_07 | 1805.894 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_01 | 1820.158 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_10 | 1852.789 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_02 | 1988.386 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_12 | 2144.265 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_03 | 2153.638 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_04 | 2168.138 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_06 | 5963.026 | CLOUD_PROVIDER_GCP | us-east4 |
| 2 | 256_07 | 5970.908 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_05 | 5972.933 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_04 | 5998.687 | CLOUD_PROVIDER_GCP | us-east4 |
| 5 | 256_10 | 6011.249 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_08 | 6017.144 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_03 | 6033.251 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_01 | 6047.050 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_11 | 6065.479 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_09 | 6129.583 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_12 | 6131.578 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_02 | 6139.680 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_03 | 1331.228 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 256_10 | 1355.376 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_05 | 1358.796 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_07 | 1396.323 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_12 | 1400.935 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_04 | 1410.326 | CLOUD_PROVIDER_GCP | us-east4 |
| 7 | 256_11 | 1414.613 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_08 | 1422.483 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_09 | 1435.006 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_02 | 1459.560 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_01 | 1521.944 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 256_06 | 1565.309 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 256_06 | 518.998 | CLOUD_PROVIDER_GCP | us-east4 |
| 2 | 256_03 | 519.456 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 256_05 | 520.523 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 256_10 | 524.721 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 256_11 | 526.813 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 256_09 | 529.297 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 256_07 | 532.799 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 256_12 | 534.526 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 256_08 | 537.015 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 256_02 | 538.105 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 256_04 | 542.072 | CLOUD_PROVIDER_GCP | us-east4 |
| 12 | 256_01 | 554.761 | CLOUD_PROVIDER_GCP | us-east1 |

### 512 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_11 | 12095.460 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_05 | 12197.977 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_07 | 12300.614 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_12 | 12352.970 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_10 | 12394.575 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_04 | 12434.290 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_08 | 12448.704 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_09 | 12696.065 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_06 | 13043.871 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 512_01 | 13279.339 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_02 | 14236.807 | CLOUD_PROVIDER_GCP | us-east4 |
| 12 | 512_03 | 19170.139 | CLOUD_PROVIDER_GCP | us-east1 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_11 | 3420.186 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_05 | 3526.088 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_10 | 3560.726 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_07 | 3581.443 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_08 | 3717.300 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_04 | 3718.425 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_12 | 3775.505 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_09 | 3877.833 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_02 | 4040.585 | CLOUD_PROVIDER_GCP | us-east4 |
| 10 | 512_01 | 4292.524 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_06 | 4550.346 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_03 | 10366.527 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_10 | 1676.806 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_07 | 1712.324 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_11 | 1738.500 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_08 | 1748.573 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_09 | 1775.434 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_12 | 1794.921 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_05 | 1812.982 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_02 | 1892.304 | CLOUD_PROVIDER_GCP | us-east4 |
| 9 | 512_04 | 1946.121 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 512_06 | 1964.303 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_01 | 1978.936 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_03 | 6928.079 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_11 | 1574.326 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_05 | 1594.744 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_04 | 1652.086 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_07 | 1754.841 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_10 | 1773.240 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_08 | 1855.673 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_12 | 1855.842 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_09 | 1987.127 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_02 | 2020.331 | CLOUD_PROVIDER_GCP | us-east4 |
| 10 | 512_01 | 2176.025 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_06 | 2469.863 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_03 | 3334.074 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_06 | 5904.026 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_05 | 5957.352 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_12 | 5983.301 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_04 | 6048.822 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_08 | 6075.279 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_09 | 6091.776 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_11 | 6110.416 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_01 | 6125.160 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_07 | 6166.906 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 512_03 | 6172.797 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_10 | 6205.542 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_02 | 6475.061 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_08 | 1338.317 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_11 | 1353.090 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_10 | 1364.157 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_07 | 1384.574 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_06 | 1399.436 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_04 | 1401.550 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_12 | 1407.090 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_03 | 1407.297 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_09 | 1409.191 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 512_05 | 1435.899 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_01 | 1578.985 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_02 | 1684.825 | CLOUD_PROVIDER_GCP | us-east4 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 512_12 | 507.573 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 512_03 | 520.602 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 512_05 | 521.732 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 512_11 | 522.552 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 512_06 | 526.769 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 512_08 | 527.115 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 512_10 | 527.173 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 512_07 | 529.986 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 512_09 | 532.594 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 512_04 | 545.509 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 512_01 | 557.267 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 512_02 | 1220.633 | CLOUD_PROVIDER_GCP | us-east4 |

### 1024 MiB

**golden_internal_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_06 | 12384.136 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_04 | 12497.513 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_02 | 12762.369 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_11 | 12796.888 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_08 | 12831.990 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_07 | 12900.222 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_12 | 12942.564 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_10 | 12946.514 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 1024_09 | 12998.492 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_01 | 13238.055 | CLOUD_PROVIDER_GCP | us-east4 |
| 11 | 1024_05 | 14049.305 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 1024_03 | 15557.676 | CLOUD_PROVIDER_GCP | us-east1 |

**combined_loader_wall_ms**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_04 | 3845.253 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_06 | 3895.860 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_02 | 4007.633 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_08 | 4166.583 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_11 | 4262.768 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_07 | 4278.930 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_10 | 4334.515 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_01 | 4366.466 | CLOUD_PROVIDER_GCP | us-east4 |
| 9 | 1024_12 | 4393.661 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_09 | 4487.576 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 1024_05 | 4930.227 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 1024_03 | 7032.427 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:clip_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_06 | 1862.887 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_04 | 1920.432 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_07 | 2137.698 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_02 | 2147.533 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_09 | 2148.969 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_08 | 2164.767 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_10 | 2215.200 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_01 | 2222.735 | CLOUD_PROVIDER_GCP | us-east4 |
| 9 | 1024_12 | 2280.724 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_11 | 2283.181 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 1024_05 | 2434.204 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 1024_03 | 3262.027 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:unet_load**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_02 | 1742.807 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_04 | 1810.406 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_11 | 1872.874 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_08 | 1891.829 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_06 | 1926.468 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_12 | 1994.059 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_10 | 2007.182 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_07 | 2008.101 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 1024_01 | 2047.061 | CLOUD_PROVIDER_GCP | us-east4 |
| 10 | 1024_09 | 2225.146 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 1024_05 | 2380.350 | CLOUD_PROVIDER_GCP | us-central1 |
| 12 | 1024_03 | 3675.424 | CLOUD_PROVIDER_GCP | us-east1 |

**stage:sampling**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_09 | 5881.846 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_03 | 5942.171 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_11 | 5982.427 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_06 | 6000.957 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_04 | 6027.445 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_07 | 6036.721 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_12 | 6046.759 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_02 | 6056.963 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 1024_10 | 6061.930 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_01 | 6082.980 | CLOUD_PROVIDER_GCP | us-east4 |
| 11 | 1024_08 | 6093.804 | CLOUD_PROVIDER_GCP | us-east1 |
| 12 | 1024_05 | 6124.771 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:clip_forward**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_12 | 1340.627 | CLOUD_PROVIDER_GCP | us-east1 |
| 2 | 1024_06 | 1360.170 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_10 | 1364.486 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_03 | 1368.187 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_08 | 1399.959 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_07 | 1405.792 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_11 | 1410.270 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_04 | 1423.584 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 1024_02 | 1430.314 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_09 | 1441.184 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 1024_01 | 1528.044 | CLOUD_PROVIDER_GCP | us-east4 |
| 12 | 1024_05 | 1616.383 | CLOUD_PROVIDER_GCP | us-central1 |

**stage:vae_decode**

| order | attempt | value ms | provider | region |
|---|---:|---:|---:|---:|
| 1 | 1024_05 | 515.315 | CLOUD_PROVIDER_GCP | us-central1 |
| 2 | 1024_06 | 516.978 | CLOUD_PROVIDER_GCP | us-east1 |
| 3 | 1024_12 | 518.658 | CLOUD_PROVIDER_GCP | us-east1 |
| 4 | 1024_04 | 523.214 | CLOUD_PROVIDER_GCP | us-east1 |
| 5 | 1024_11 | 526.362 | CLOUD_PROVIDER_GCP | us-east1 |
| 6 | 1024_08 | 528.913 | CLOUD_PROVIDER_GCP | us-east1 |
| 7 | 1024_09 | 528.985 | CLOUD_PROVIDER_GCP | us-east1 |
| 8 | 1024_02 | 530.108 | CLOUD_PROVIDER_GCP | us-east1 |
| 9 | 1024_10 | 533.824 | CLOUD_PROVIDER_GCP | us-east1 |
| 10 | 1024_07 | 535.916 | CLOUD_PROVIDER_GCP | us-east1 |
| 11 | 1024_01 | 562.312 | CLOUD_PROVIDER_GCP | us-east4 |
| 12 | 1024_03 | 578.383 | CLOUD_PROVIDER_GCP | us-east1 |

## Best Valid Runs

### 32 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 32_02 | 12769.139 | {"clip_forward":1327.688486,"clip_load":1560.178064,"golden_restore":8.990394,"output":159.696646,"request_setup":1.219559,"sampler_prepare":283.094498,"sampler_tail":0.01123,"sampling":5973.792608,"teardown":0.304529,"unet_load":1731.839436,"vae_decode":525.654439,"vae_load":121.392542} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":243,"event_object_count":18,"event_rerecord_count":470,"gpu_active_ms":199.14278389513493,"gpu_idle_inside_span_ms":641.3083269447088,"gpu_stream_span_ms":840.4511108398438,"h2d_submission_count":243,"h2d_target_bytes":33554432,"h2d_wall_ms":840.737155,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":243,"source_read_count":243,"source_to_gpu_ready_ms":854.701696,"source_wall_ms":852.081037,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":370,"event_object_count":18,"event_rerecord_count":1210,"gpu_active_ms":360.52211233973503,"gpu_idle_inside_span_ms":1003.2409491837025,"gpu_stream_span_ms":1363.7630615234375,"h2d_submission_count":370,"h2d_target_bytes":33554432,"h2d_wall_ms":1363.769382,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":370,"source_read_count":370,"source_to_gpu_ready_ms":1374.698745,"source_wall_ms":1372.413646,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":13,"event_object_count":18,"event_rerecord_count":1236,"gpu_active_ms":16.53814390534535,"gpu_idle_inside_span_ms":0.0,"gpu_stream_span_ms":null,"h2d_submission_count":13,"h2d_target_bytes":33554432,"h2d_wall_ms":47.40705,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":13,"source_read_count":13,"source_to_gpu_ready_ms":58.347372,"source_wall_ms":56.431553,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |
| 32_06 | 12946.083 | {"clip_forward":1404.84903,"clip_load":1722.728164,"golden_restore":9.110445,"output":163.551038,"request_setup":1.931119,"sampler_prepare":327.732512,"sampler_tail":0.01291,"sampling":5957.479938,"teardown":0.297929,"unet_load":1601.501666,"vae_decode":532.640068,"vae_load":141.695987} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":243,"event_object_count":18,"event_rerecord_count":470,"gpu_active_ms":269.0119695439935,"gpu_idle_inside_span_ms":703.9185114130378,"gpu_stream_span_ms":972.9304809570312,"h2d_submission_count":243,"h2d_target_bytes":33554432,"h2d_wall_ms":973.323476,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":243,"source_read_count":243,"source_to_gpu_ready_ms":984.8622,"source_wall_ms":982.615331,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":370,"event_object_count":18,"event_rerecord_count":1210,"gpu_active_ms":405.9453445225954,"gpu_idle_inside_span_ms":812.2409347742796,"gpu_stream_span_ms":1218.186279296875,"h2d_submission_count":370,"h2d_target_bytes":33554432,"h2d_wall_ms":1218.126453,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":370,"source_read_count":370,"source_to_gpu_ready_ms":1227.910488,"source_wall_ms":1224.319719,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":13,"event_object_count":18,"event_rerecord_count":1236,"gpu_active_ms":17.74608028680086,"gpu_idle_inside_span_ms":46.464223973453045,"gpu_stream_span_ms":64.2103042602539,"h2d_submission_count":13,"h2d_target_bytes":33554432,"h2d_wall_ms":64.214657,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":13,"source_read_count":13,"source_to_gpu_ready_ms":76.563381,"source_wall_ms":73.272542,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |
| 32_12 | 13140.856 | {"clip_forward":1384.753619,"clip_load":1693.787541,"golden_restore":8.981823,"output":161.895001,"request_setup":1.231499,"sampler_prepare":318.295141,"sampler_tail":0.0126,"sampling":6010.077436,"teardown":0.316949,"unet_load":1806.456327,"vae_decode":533.257338,"vae_load":127.189402} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":243,"event_object_count":18,"event_rerecord_count":470,"gpu_active_ms":211.36508798599243,"gpu_idle_inside_span_ms":729.6053709983826,"gpu_stream_span_ms":940.970458984375,"h2d_submission_count":243,"h2d_target_bytes":33554432,"h2d_wall_ms":941.087482,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":243,"source_read_count":243,"source_to_gpu_ready_ms":954.100493,"source_wall_ms":951.566335,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":370,"event_object_count":18,"event_rerecord_count":1210,"gpu_active_ms":422.535713031888,"gpu_idle_inside_span_ms":1011.0364305227995,"gpu_stream_span_ms":1433.5721435546875,"h2d_submission_count":370,"h2d_target_bytes":33554432,"h2d_wall_ms":1433.454557,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":370,"source_read_count":370,"source_to_gpu_ready_ms":1444.380309,"source_wall_ms":1441.291581,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":268435456,"copy_count":13,"event_object_count":18,"event_rerecord_count":1236,"gpu_active_ms":15.72272004187107,"gpu_idle_inside_span_ms":39.81667052209377,"gpu_stream_span_ms":55.539390563964844,"h2d_submission_count":13,"h2d_target_bytes":33554432,"h2d_wall_ms":55.361042,"logical_slot_bytes":33554432,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":33554432,"source_block_count":13,"source_read_count":13,"source_to_gpu_ready_ms":66.566085,"source_wall_ms":64.729606,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |

### 64 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 64_03 | 12030.211 | {"clip_forward":1343.162452,"clip_load":1402.075349,"golden_restore":9.459491,"output":161.397077,"request_setup":1.23514,"sampler_prepare":270.16971,"sampler_tail":0.01438,"sampling":6068.936895,"teardown":0.34069,"unet_load":1549.938033,"vae_decode":519.71204,"vae_load":106.162316} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":123,"event_object_count":18,"event_rerecord_count":230,"gpu_active_ms":155.04249566420913,"gpu_idle_inside_span_ms":653.8863983787596,"gpu_stream_span_ms":808.9288940429688,"h2d_submission_count":123,"h2d_target_bytes":67108864,"h2d_wall_ms":808.951246,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":123,"source_read_count":123,"source_to_gpu_ready_ms":826.165508,"source_wall_ms":821.023359,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":187,"event_object_count":18,"event_rerecord_count":604,"gpu_active_ms":246.70860788226128,"gpu_idle_inside_span_ms":1074.6677348911762,"gpu_stream_span_ms":1321.3763427734375,"h2d_submission_count":187,"h2d_target_bytes":67108864,"h2d_wall_ms":1321.417851,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":187,"source_read_count":187,"source_to_gpu_ready_ms":1338.33894,"source_wall_ms":1332.017611,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":8,"event_object_count":18,"event_rerecord_count":620,"gpu_active_ms":24.244895845651627,"gpu_idle_inside_span_ms":27.14451226592064,"gpu_stream_span_ms":51.389408111572266,"h2d_submission_count":8,"h2d_target_bytes":67108864,"h2d_wall_ms":51.424938,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":8,"source_read_count":8,"source_to_gpu_ready_ms":67.315677,"source_wall_ms":63.579047,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |
| 64_09 | 12173.738 | {"clip_forward":1271.668957,"clip_load":1549.071545,"golden_restore":8.22678,"output":159.624429,"request_setup":1.222599,"sampler_prepare":269.755717,"sampler_tail":0.01062,"sampling":5800.032136,"teardown":0.34475,"unet_load":1914.304942,"vae_decode":509.198887,"vae_load":105.33413} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":123,"event_object_count":18,"event_rerecord_count":230,"gpu_active_ms":176.69324833899736,"gpu_idle_inside_span_ms":840.7221569344401,"gpu_stream_span_ms":1017.4154052734375,"h2d_submission_count":123,"h2d_target_bytes":67108864,"h2d_wall_ms":1017.527424,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":123,"source_read_count":123,"source_to_gpu_ready_ms":1032.555193,"source_wall_ms":1030.409153,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":187,"event_object_count":18,"event_rerecord_count":604,"gpu_active_ms":265.80694445967674,"gpu_idle_inside_span_ms":1419.6347059309483,"gpu_stream_span_ms":1685.441650390625,"h2d_submission_count":187,"h2d_target_bytes":67108864,"h2d_wall_ms":1685.374163,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":187,"source_read_count":187,"source_to_gpu_ready_ms":1704.753212,"source_wall_ms":1702.348392,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":8,"event_object_count":18,"event_rerecord_count":620,"gpu_active_ms":16.57686397433281,"gpu_idle_inside_span_ms":33.13212803006172,"gpu_stream_span_ms":49.70899200439453,"h2d_submission_count":8,"h2d_target_bytes":67108864,"h2d_wall_ms":49.74082,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":8,"source_read_count":8,"source_to_gpu_ready_ms":66.90038,"source_wall_ms":64.11326,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |
| 64_06 | 12537.537 | {"clip_forward":1366.036254,"clip_load":1583.093507,"golden_restore":8.74493,"output":161.318277,"request_setup":1.259579,"sampler_prepare":310.383195,"sampler_tail":0.0121,"sampling":5997.791029,"teardown":0.30506,"unet_load":1860.283333,"vae_decode":534.067978,"vae_load":103.244622} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":123,"event_object_count":18,"event_rerecord_count":230,"gpu_active_ms":163.82751993834972,"gpu_idle_inside_span_ms":864.4470161944628,"gpu_stream_span_ms":1028.2745361328125,"h2d_submission_count":123,"h2d_target_bytes":67108864,"h2d_wall_ms":1028.324759,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":123,"source_read_count":123,"source_to_gpu_ready_ms":1044.466288,"source_wall_ms":1042.253658,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":187,"event_object_count":18,"event_rerecord_count":604,"gpu_active_ms":257.8307194560766,"gpu_idle_inside_span_ms":1362.7124934345484,"gpu_stream_span_ms":1620.543212890625,"h2d_submission_count":187,"h2d_target_bytes":67108864,"h2d_wall_ms":1620.518473,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":187,"source_read_count":187,"source_to_gpu_ready_ms":1647.028191,"source_wall_ms":1643.853871,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":536870912,"copy_count":8,"event_object_count":18,"event_rerecord_count":620,"gpu_active_ms":45.40572780370712,"gpu_idle_inside_span_ms":3.398654520511627,"gpu_stream_span_ms":48.80438232421875,"h2d_submission_count":8,"h2d_target_bytes":67108864,"h2d_wall_ms":48.794046,"logical_slot_bytes":67108864,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":67108864,"source_block_count":8,"source_read_count":8,"source_to_gpu_ready_ms":63.743555,"source_wall_ms":58.123675,"tail_submission_count":7}} | CLOUD_PROVIDER_GCP | us-east1 |

### 128 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 128_03 | 11954.478 | {"clip_forward":1328.118176,"clip_load":1518.59146,"golden_restore":9.28481,"output":163.507642,"request_setup":1.50326,"sampler_prepare":285.748394,"sampler_tail":0.01363,"sampling":5921.655546,"teardown":0.33819,"unet_load":1680.227819,"vae_decode":550.480405,"vae_load":98.809131} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":63,"event_object_count":18,"event_rerecord_count":110,"gpu_active_ms":181.16809545829892,"gpu_idle_inside_span_ms":817.8315383307636,"gpu_stream_span_ms":998.9996337890625,"h2d_submission_count":63,"h2d_target_bytes":134217728,"h2d_wall_ms":998.942493,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":63,"source_read_count":63,"source_to_gpu_ready_ms":1028.633153,"source_wall_ms":1024.288683,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":95,"event_object_count":18,"event_rerecord_count":300,"gpu_active_ms":223.73158299922943,"gpu_idle_inside_span_ms":1279.169906258583,"gpu_stream_span_ms":1502.9014892578125,"h2d_submission_count":95,"h2d_target_bytes":134217728,"h2d_wall_ms":1502.923028,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":95,"source_read_count":95,"source_to_gpu_ready_ms":1541.309748,"source_wall_ms":1537.115818,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":6,"event_object_count":18,"event_rerecord_count":312,"gpu_active_ms":25.924031525850296,"gpu_idle_inside_span_ms":15.259550780057907,"gpu_stream_span_ms":41.1835823059082,"h2d_submission_count":6,"h2d_target_bytes":134217728,"h2d_wall_ms":41.234361,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":6,"source_read_count":6,"source_to_gpu_ready_ms":60.670721,"source_wall_ms":58.543291,"tail_submission_count":6}} | CLOUD_PROVIDER_GCP | us-east1 |
| 128_09 | 12032.824 | {"clip_forward":1429.063253,"clip_load":1604.042302,"golden_restore":9.278649,"output":163.368014,"request_setup":1.86672,"sampler_prepare":312.390507,"sampler_tail":0.01454,"sampling":5941.70791,"teardown":0.29775,"unet_load":1567.420169,"vae_decode":524.351387,"vae_load":103.214733} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":63,"event_object_count":18,"event_rerecord_count":110,"gpu_active_ms":275.0001261457801,"gpu_idle_inside_span_ms":819.6287801042199,"gpu_stream_span_ms":1094.62890625,"h2d_submission_count":63,"h2d_target_bytes":134217728,"h2d_wall_ms":1094.56732,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":63,"source_read_count":63,"source_to_gpu_ready_ms":1126.371575,"source_wall_ms":1123.492025,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":95,"event_object_count":18,"event_rerecord_count":300,"gpu_active_ms":223.28230439126492,"gpu_idle_inside_span_ms":1163.9705032259226,"gpu_stream_span_ms":1387.2528076171875,"h2d_submission_count":95,"h2d_target_bytes":134217728,"h2d_wall_ms":1387.274017,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":95,"source_read_count":95,"source_to_gpu_ready_ms":1420.469463,"source_wall_ms":1417.619983,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":6,"event_object_count":18,"event_rerecord_count":312,"gpu_active_ms":27.594463527202606,"gpu_idle_inside_span_ms":16.031169712543488,"gpu_stream_span_ms":43.625633239746094,"h2d_submission_count":6,"h2d_target_bytes":134217728,"h2d_wall_ms":43.654373,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":1,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":6,"source_read_count":6,"source_to_gpu_ready_ms":63.777369,"source_wall_ms":61.899789,"tail_submission_count":6}} | CLOUD_PROVIDER_GCP | us-east1 |
| 128_06 | 12115.985 | {"clip_forward":1355.667017,"clip_load":1345.10506,"golden_restore":9.054131,"output":160.791198,"request_setup":1.28933,"sampler_prepare":308.762808,"sampler_tail":0.01327,"sampling":6043.193521,"teardown":0.48116,"unet_load":1895.592803,"vae_decode":524.139836,"vae_load":100.48291} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":63,"event_object_count":18,"event_rerecord_count":110,"gpu_active_ms":173.79344011098146,"gpu_idle_inside_span_ms":668.3006150647998,"gpu_stream_span_ms":842.0940551757812,"h2d_submission_count":63,"h2d_target_bytes":134217728,"h2d_wall_ms":842.061556,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":63,"source_read_count":63,"source_to_gpu_ready_ms":872.798278,"source_wall_ms":866.624048,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":95,"event_object_count":18,"event_rerecord_count":300,"gpu_active_ms":249.59465530514717,"gpu_idle_inside_span_ms":1468.3574931323528,"gpu_stream_span_ms":1717.9521484375,"h2d_submission_count":95,"h2d_target_bytes":134217728,"h2d_wall_ms":1717.932258,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":95,"source_read_count":95,"source_to_gpu_ready_ms":1758.129966,"source_wall_ms":1746.071456,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":1073741824,"copy_count":6,"event_object_count":18,"event_rerecord_count":312,"gpu_active_ms":28.801280796527863,"gpu_idle_inside_span_ms":10.89810961484909,"gpu_stream_span_ms":39.69939041137695,"h2d_submission_count":6,"h2d_target_bytes":134217728,"h2d_wall_ms":39.75896,"logical_slot_bytes":134217728,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":134217728,"source_block_count":6,"source_read_count":6,"source_to_gpu_ready_ms":59.90941,"source_wall_ms":57.43397,"tail_submission_count":6}} | CLOUD_PROVIDER_GCP | us-east1 |

### 256 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 256_06 | 11768.165 | {"clip_forward":1565.309137,"clip_load":1484.077302,"golden_restore":9.15433,"output":160.437938,"request_setup":1.487939,"sampler_prepare":249.447127,"sampler_tail":0.01143,"sampling":5963.026289,"teardown":0.31981,"unet_load":1466.724101,"vae_decode":518.998293,"vae_load":98.436599} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":33,"event_object_count":18,"event_rerecord_count":50,"gpu_active_ms":149.69507287442684,"gpu_idle_inside_span_ms":714.6816971451044,"gpu_stream_span_ms":864.3767700195312,"h2d_submission_count":33,"h2d_target_bytes":268435456,"h2d_wall_ms":864.41485,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":33,"source_read_count":33,"source_to_gpu_ready_ms":953.237966,"source_wall_ms":945.808556,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":49,"event_object_count":18,"event_rerecord_count":148,"gpu_active_ms":227.3548488020897,"gpu_idle_inside_span_ms":1061.8728123307228,"gpu_stream_span_ms":1289.2276611328125,"h2d_submission_count":49,"h2d_target_bytes":268435456,"h2d_wall_ms":1289.107245,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":49,"source_read_count":49,"source_to_gpu_ready_ms":1365.852863,"source_wall_ms":1360.042223,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":5,"event_object_count":18,"event_rerecord_count":158,"gpu_active_ms":6.4375360906124115,"gpu_idle_inside_span_ms":22.12716880440712,"gpu_stream_span_ms":28.56470489501953,"h2d_submission_count":5,"h2d_target_bytes":268435456,"h2d_wall_ms":28.537119,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":5,"source_read_count":5,"source_to_gpu_ready_ms":60.389989,"source_wall_ms":58.442749,"tail_submission_count":5}} | CLOUD_PROVIDER_GCP | us-east4 |
| 256_05 | 11881.104 | {"clip_forward":1358.79618,"clip_load":1436.085584,"golden_restore":8.96056,"output":161.877838,"request_setup":1.2137,"sampler_prepare":274.935019,"sampler_tail":0.01225,"sampling":5972.932858,"teardown":0.475599,"unet_load":1797.561089,"vae_decode":520.522638,"vae_load":100.72349} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":33,"event_object_count":18,"event_rerecord_count":50,"gpu_active_ms":145.05302526801825,"gpu_idle_inside_span_ms":753.4746846929193,"gpu_stream_span_ms":898.5277099609375,"h2d_submission_count":33,"h2d_target_bytes":268435456,"h2d_wall_ms":898.439666,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":33,"source_read_count":33,"source_to_gpu_ready_ms":958.397504,"source_wall_ms":950.655296,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":49,"event_object_count":18,"event_rerecord_count":148,"gpu_active_ms":224.73334270715714,"gpu_idle_inside_span_ms":1410.9008125662804,"gpu_stream_span_ms":1635.6341552734375,"h2d_submission_count":49,"h2d_target_bytes":268435456,"h2d_wall_ms":1635.555568,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":49,"source_read_count":49,"source_to_gpu_ready_ms":1686.488379,"source_wall_ms":1681.453179,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":5,"event_object_count":18,"event_rerecord_count":158,"gpu_active_ms":22.402815639972687,"gpu_idle_inside_span_ms":7.526433169841766,"gpu_stream_span_ms":29.929248809814453,"h2d_submission_count":5,"h2d_target_bytes":268435456,"h2d_wall_ms":29.985035,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":5,"source_read_count":5,"source_to_gpu_ready_ms":62.395028,"source_wall_ms":59.566668,"tail_submission_count":5}} | CLOUD_PROVIDER_GCP | us-east1 |
| 256_01 | 12206.379 | {"clip_forward":1521.944109,"clip_load":1447.313877,"golden_restore":8.991786,"output":164.634928,"request_setup":1.14444,"sampler_prepare":275.161429,"sampler_tail":0.01247,"sampling":6047.049832,"teardown":0.36366,"unet_load":1820.157661,"vae_decode":554.760836,"vae_load":103.425975} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":33,"event_object_count":18,"event_rerecord_count":50,"gpu_active_ms":214.9023378789425,"gpu_idle_inside_span_ms":703.0582944452763,"gpu_stream_span_ms":917.9606323242188,"h2d_submission_count":33,"h2d_target_bytes":268435456,"h2d_wall_ms":917.940126,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":33,"source_read_count":33,"source_to_gpu_ready_ms":922.670234,"source_wall_ms":894.594157,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":49,"event_object_count":18,"event_rerecord_count":148,"gpu_active_ms":221.08115312457085,"gpu_idle_inside_span_ms":1444.7411125004292,"gpu_stream_span_ms":1665.822265625,"h2d_submission_count":49,"h2d_target_bytes":268435456,"h2d_wall_ms":1665.774708,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":49,"source_read_count":49,"source_to_gpu_ready_ms":1715.180856,"source_wall_ms":1709.034679,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":2147483648,"copy_count":5,"event_object_count":18,"event_rerecord_count":158,"gpu_active_ms":6.712896078824997,"gpu_idle_inside_span_ms":0.0,"gpu_stream_span_ms":null,"h2d_submission_count":5,"h2d_target_bytes":268435456,"h2d_wall_ms":45.4259,"logical_slot_bytes":268435456,"logical_slot_count":8,"max_actual_source_inflight":1,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":268435456,"source_block_count":5,"source_read_count":5,"source_to_gpu_ready_ms":64.404131,"source_wall_ms":62.537702,"tail_submission_count":5}} | CLOUD_PROVIDER_GCP | us-east1 |

### 512 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 512_11 | 12095.460 | {"clip_forward":1353.090188,"clip_load":1738.499915,"golden_restore":9.454762,"output":161.556738,"request_setup":1.38765,"sampler_prepare":318.217633,"sampler_tail":0.01576,"sampling":6110.415619,"teardown":0.32368,"unet_load":1574.32593,"vae_decode":522.551698,"vae_load":107.360188} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":18,"event_object_count":18,"event_rerecord_count":20,"gpu_active_ms":326.5096971988678,"gpu_idle_inside_span_ms":637.5140454769135,"gpu_stream_span_ms":964.0237426757812,"h2d_submission_count":18,"h2d_target_bytes":536870912,"h2d_wall_ms":964.108733,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":18,"source_read_count":18,"source_to_gpu_ready_ms":1175.469003,"source_wall_ms":1162.624665,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":26,"event_object_count":18,"event_rerecord_count":72,"gpu_active_ms":321.3960602283478,"gpu_idle_inside_span_ms":0.0,"gpu_stream_span_ms":null,"h2d_submission_count":26,"h2d_target_bytes":536870912,"h2d_wall_ms":1377.488931,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":26,"source_read_count":26,"source_to_gpu_ready_ms":1499.332541,"source_wall_ms":1489.486921,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":4,"event_object_count":18,"event_rerecord_count":80,"gpu_active_ms":25.424736976623535,"gpu_idle_inside_span_ms":2.326815605163574,"gpu_stream_span_ms":27.75155258178711,"h2d_submission_count":4,"h2d_target_bytes":536870912,"h2d_wall_ms":27.74026,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":61.421499,"source_wall_ms":54.161179,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |
| 512_05 | 12197.977 | {"clip_forward":1435.898601,"clip_load":1812.981577,"golden_restore":8.206776,"output":161.242939,"request_setup":1.09077,"sampler_prepare":386.127316,"sampler_tail":0.012579,"sampling":5957.351826,"teardown":0.28948,"unet_load":1594.744444,"vae_decode":521.731614,"vae_load":118.361486} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":18,"event_object_count":18,"event_rerecord_count":20,"gpu_active_ms":322.8739459514618,"gpu_idle_inside_span_ms":707.4801800251007,"gpu_stream_span_ms":1030.3541259765625,"h2d_submission_count":18,"h2d_target_bytes":536870912,"h2d_wall_ms":1030.36587,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":18,"source_read_count":18,"source_to_gpu_ready_ms":1161.646949,"source_wall_ms":1113.405689,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":26,"event_object_count":18,"event_rerecord_count":72,"gpu_active_ms":411.755934715271,"gpu_idle_inside_span_ms":1000.2939920425415,"gpu_stream_span_ms":1412.0499267578125,"h2d_submission_count":26,"h2d_target_bytes":536870912,"h2d_wall_ms":1411.931456,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":26,"source_read_count":26,"source_to_gpu_ready_ms":1508.315712,"source_wall_ms":1498.089186,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":4,"event_object_count":18,"event_rerecord_count":80,"gpu_active_ms":35.3169606924057,"gpu_idle_inside_span_ms":13.40172827243805,"gpu_stream_span_ms":48.71868896484375,"h2d_submission_count":4,"h2d_target_bytes":536870912,"h2d_wall_ms":48.696758,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":1,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":69.300438,"source_wall_ms":63.154111,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |
| 512_07 | 12300.614 | {"clip_forward":1384.573679,"clip_load":1712.323669,"golden_restore":8.832237,"output":161.704755,"request_setup":1.201579,"sampler_prepare":270.39076,"sampler_tail":0.0124,"sampling":6166.906447,"teardown":0.31801,"unet_load":1754.841165,"vae_decode":529.985697,"vae_load":114.278023} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":18,"event_object_count":18,"event_rerecord_count":20,"gpu_active_ms":284.87702202796936,"gpu_idle_inside_span_ms":692.9893720149994,"gpu_stream_span_ms":977.8663940429688,"h2d_submission_count":18,"h2d_target_bytes":536870912,"h2d_wall_ms":977.924272,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":18,"source_read_count":18,"source_to_gpu_ready_ms":1135.616505,"source_wall_ms":1122.656739,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":26,"event_object_count":18,"event_rerecord_count":72,"gpu_active_ms":331.0653784275055,"gpu_idle_inside_span_ms":1212.983083486557,"gpu_stream_span_ms":1544.0484619140625,"h2d_submission_count":26,"h2d_target_bytes":536870912,"h2d_wall_ms":1543.978265,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":26,"source_read_count":26,"source_to_gpu_ready_ms":1679.51102,"source_wall_ms":1667.598964,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":4294967296,"copy_count":4,"event_object_count":18,"event_rerecord_count":80,"gpu_active_ms":27.147584557533264,"gpu_idle_inside_span_ms":9.554975867271423,"gpu_stream_span_ms":36.70256042480469,"h2d_submission_count":4,"h2d_target_bytes":536870912,"h2d_wall_ms":36.634678,"logical_slot_bytes":536870912,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":536870912,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":56.673422,"source_wall_ms":53.932233,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |

### 1024 MiB

| attempt | Golden ms | stage values ms | transport metrics | provider | region |
|---|---:|---:|---:|---:|---:|
| 1024_06 | 12384.136 | {"clip_forward":1360.170378,"clip_load":1862.887492,"golden_restore":9.18291,"output":161.11915,"request_setup":2.39506,"sampler_prepare":264.657903,"sampler_tail":0.01235,"sampling":6000.957494,"teardown":0.32228,"unet_load":1926.467729,"vae_decode":516.978123,"vae_load":106.505258} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":11,"event_object_count":18,"event_rerecord_count":6,"gpu_active_ms":143.13782572746277,"gpu_idle_inside_span_ms":644.4942543506622,"gpu_stream_span_ms":787.632080078125,"h2d_submission_count":11,"h2d_target_bytes":1073741824,"h2d_wall_ms":787.633537,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":11,"source_read_count":11,"source_to_gpu_ready_ms":974.853585,"source_wall_ms":938.985036,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":15,"event_object_count":18,"event_rerecord_count":36,"gpu_active_ms":377.2938256263733,"gpu_idle_inside_span_ms":1255.9439673423767,"gpu_stream_span_ms":1633.23779296875,"h2d_submission_count":15,"h2d_target_bytes":1073741824,"h2d_wall_ms":1633.14329,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":4,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":15,"source_read_count":15,"source_to_gpu_ready_ms":1836.85548,"source_wall_ms":1824.62545,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":4,"event_object_count":18,"event_rerecord_count":44,"gpu_active_ms":41.26339149475098,"gpu_idle_inside_span_ms":2.024831771850586,"gpu_stream_span_ms":43.28822326660156,"h2d_submission_count":4,"h2d_target_bytes":1073741824,"h2d_wall_ms":43.386459,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":1,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":63.168469,"source_wall_ms":57.798599,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |
| 1024_04 | 12497.513 | {"clip_forward":1423.583837,"clip_load":1920.432131,"golden_restore":9.185756,"output":163.314227,"request_setup":1.51226,"sampler_prepare":327.335031,"sampler_tail":0.01195,"sampling":6027.444543,"teardown":0.43815,"unet_load":1810.405954,"vae_decode":523.213859,"vae_load":114.415232} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":11,"event_object_count":18,"event_rerecord_count":6,"gpu_active_ms":313.86451387405396,"gpu_idle_inside_span_ms":547.978991985321,"gpu_stream_span_ms":861.843505859375,"h2d_submission_count":11,"h2d_target_bytes":1073741824,"h2d_wall_ms":861.912556,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":11,"source_read_count":11,"source_to_gpu_ready_ms":1056.272671,"source_wall_ms":1020.161779,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":15,"event_object_count":18,"event_rerecord_count":36,"gpu_active_ms":381.1685175895691,"gpu_idle_inside_span_ms":1173.2815556526184,"gpu_stream_span_ms":1554.4500732421875,"h2d_submission_count":15,"h2d_target_bytes":1073741824,"h2d_wall_ms":1554.548827,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":15,"source_read_count":15,"source_to_gpu_ready_ms":1739.709141,"source_wall_ms":1729.482586,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":4,"event_object_count":18,"event_rerecord_count":44,"gpu_active_ms":6.1112319231033325,"gpu_idle_inside_span_ms":38.30844962596893,"gpu_stream_span_ms":44.419681549072266,"h2d_submission_count":4,"h2d_target_bytes":1073741824,"h2d_wall_ms":44.393407,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":63.569788,"source_wall_ms":57.830261,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |
| 1024_02 | 12762.369 | {"clip_forward":1430.314093,"clip_load":2147.532861,"golden_restore":11.639737,"output":161.881535,"request_setup":1.5368,"sampler_prepare":378.464174,"sampler_tail":0.01306,"sampling":6056.963084,"teardown":0.33657,"unet_load":1742.806769,"vae_decode":530.10789,"vae_load":117.293342} | {"clip":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":11,"event_object_count":18,"event_rerecord_count":6,"gpu_active_ms":642.6401014328003,"gpu_idle_inside_span_ms":408.4383897781372,"gpu_stream_span_ms":1051.0784912109375,"h2d_submission_count":11,"h2d_target_bytes":1073741824,"h2d_wall_ms":1051.134809,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":11,"source_read_count":11,"source_to_gpu_ready_ms":1295.141543,"source_wall_ms":1273.288586,"tail_submission_count":7},"unet":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":15,"event_object_count":18,"event_rerecord_count":36,"gpu_active_ms":750.893417596817,"gpu_idle_inside_span_ms":667.407119512558,"gpu_stream_span_ms":1418.300537109375,"h2d_submission_count":15,"h2d_target_bytes":1073741824,"h2d_wall_ms":1418.365518,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":3,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":15,"source_read_count":15,"source_to_gpu_ready_ms":1657.849792,"source_wall_ms":1623.676297,"tail_submission_count":7},"vae":{"aggregated_submission_count":0,"aggregation_enabled":false,"aggregation_scheduler_enter_count":0,"aggregation_wait_count":0,"arena_bytes":8589934592,"copy_count":4,"event_object_count":18,"event_rerecord_count":44,"gpu_active_ms":34.85475146770477,"gpu_idle_inside_span_ms":2.8674546480178833,"gpu_stream_span_ms":37.722206115722656,"h2d_submission_count":4,"h2d_target_bytes":1073741824,"h2d_wall_ms":37.746294,"logical_slot_bytes":1073741824,"logical_slot_count":8,"max_actual_source_inflight":2,"producer_count":4,"slot_acquire_count":null,"slot_release_count":null,"source_block_bytes":1073741824,"source_block_count":4,"source_read_count":4,"source_to_gpu_ready_ms":75.782298,"source_wall_ms":68.291489,"tail_submission_count":4}} | CLOUD_PROVIDER_GCP | us-east1 |

## Median Representative Runs

| geometry | attempt | Golden ms | stage values ms | loader residuals | provider | region |
|---|---:|---:|---:|---:|---:|---:|
| 32 | 32_04 | 13266.547 | {"clip_forward":1373.581506,"clip_load":1826.382533,"golden_restore":9.15294,"output":163.203052,"request_setup":1.36156,"sampler_prepare":292.003364,"sampler_tail":0.0119,"sampling":5953.954233,"teardown":0.30226,"unet_load":1862.459204,"vae_decode":545.903156,"vae_load":147.779222} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":745.158846,"CLIP_LOAD_RESIDUAL_MS":742.100306,"UNET_LOAD_MINUS_SOURCE_WALL_MS":374.1584949999999,"UNET_LOAD_RESIDUAL_MS":373.1464450000001} | CLOUD_PROVIDER_GCP | us-east1 |
| 64 | 64_04 | 12949.264 | {"clip_forward":1399.545772,"clip_load":1959.370063,"golden_restore":10.44776,"output":162.67811,"request_setup":2.35899,"sampler_prepare":292.503123,"sampler_tail":0.01516,"sampling":6004.318935,"teardown":0.30208,"unet_load":1872.722375,"vae_decode":528.924625,"vae_load":106.095947} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":591.356818,"CLIP_LOAD_RESIDUAL_MS":588.068088,"UNET_LOAD_MINUS_SOURCE_WALL_MS":228.53867400000013,"UNET_LOAD_RESIDUAL_MS":226.02785400000016} | CLOUD_PROVIDER_GCP | us-east1 |
| 128 | 128_11 | 12587.742 | {"clip_forward":1425.259576,"clip_load":1776.821989,"golden_restore":9.16588,"output":160.772676,"request_setup":1.3973,"sampler_prepare":319.801093,"sampler_tail":0.01475,"sampling":5986.852959,"teardown":0.30589,"unet_load":1917.688105,"vae_decode":524.317212,"vae_load":97.981847} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":494.09376,"CLIP_LOAD_RESIDUAL_MS":490.90605900000014,"UNET_LOAD_MINUS_SOURCE_WALL_MS":152.82679699999994,"UNET_LOAD_RESIDUAL_MS":141.9781069999999} | CLOUD_PROVIDER_GCP | us-east1 |
| 256 | 256_08 | 12255.447 | {"clip_forward":1422.483312,"clip_load":1685.510701,"golden_restore":9.094111,"output":162.549336,"request_setup":1.38742,"sampler_prepare":323.424678,"sampler_tail":0.01663,"sampling":6017.143874,"teardown":0.36291,"unet_load":1733.599497,"vae_decode":537.01529,"vae_load":114.24806} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":493.356669,"CLIP_LOAD_RESIDUAL_MS":485.8191199999999,"UNET_LOAD_MINUS_SOURCE_WALL_MS":125.46823999999992,"UNET_LOAD_RESIDUAL_MS":118.08682999999996} | CLOUD_PROVIDER_GCP | us-east1 |
| 512 | 512_04 | 12434.290 | {"clip_forward":1401.550096,"clip_load":1946.121252,"golden_restore":14.810681,"output":180.407318,"request_setup":1.2291,"sampler_prepare":315.934663,"sampler_tail":0.01279,"sampling":6048.822137,"teardown":0.3345,"unet_load":1652.086138,"vae_decode":545.508995,"vae_load":120.217543} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":640.780542,"CLIP_LOAD_RESIDUAL_MS":622.4433099999999,"UNET_LOAD_MINUS_SOURCE_WALL_MS":95.39311999999995,"UNET_LOAD_RESIDUAL_MS":85.67294899999979} | CLOUD_PROVIDER_GCP | us-east1 |
| 1024 | 1024_07 | 12900.222 | {"clip_forward":1405.791602,"clip_load":2137.697509,"golden_restore":9.103506,"output":163.184531,"request_setup":1.719699,"sampler_prepare":298.497388,"sampler_tail":0.01432,"sampling":6036.721487,"teardown":0.33886,"unet_load":2008.100688,"vae_decode":535.915752,"vae_load":133.132047} | {"CLIP_LOAD_MINUS_SOURCE_WALL_MS":876.802019,"CLIP_LOAD_RESIDUAL_MS":865.6635040000001,"UNET_LOAD_MINUS_SOURCE_WALL_MS":97.19737400000008,"UNET_LOAD_RESIDUAL_MS":73.452855} | CLOUD_PROVIDER_GCP | us-east1 |

## CORE / EXTRA And Time-Local Interpretation

The CORE/EXTRA tables are descriptive and retain all rows. Round comparisons below use the existing `R01`-style cohort labels and creation timestamps; they are not formal paired trials.

- `R01` span=2431.0s near_contemporaneous=False: 32_01=13398.789ms; 64_01=20261.011ms; 128_01=15006.945ms; 256_01=12206.379ms; 1024_01=13238.055ms; 512_01=13279.339ms
- `R02` span=2376.0s near_contemporaneous=False: 32_02=12769.139ms; 64_02=13928.437ms; 128_02=12170.071ms; 256_02=12726.478ms; 1024_02=12762.369ms; 512_02=14236.807ms
- `R03` span=2486.0s near_contemporaneous=False: 32_03=13434.636ms; 64_03=12030.211ms; 128_03=11954.478ms; 256_03=12447.813ms; 512_03=19170.139ms; 1024_03=15557.676ms
- `R04` span=2092.0s near_contemporaneous=False: 64_04=12949.264ms; 128_04=12679.119ms; 32_04=13266.547ms; 256_04=18238.873ms; 512_04=12434.290ms; 1024_04=12497.513ms
- `R05` span=1695.0s near_contemporaneous=False: 64_05=12725.641ms; 32_05=13477.777ms; 128_05=13084.235ms; 256_05=11881.104ms; 512_05=12197.977ms; 1024_05=14049.305ms
- `R06` span=787.0s near_contemporaneous=False: 64_06=12537.537ms; 32_06=12946.083ms; 128_06=12115.985ms; 256_06=11768.165ms; 1024_06=12384.136ms; 512_06=13043.871ms
- `R07` span=384.0s near_contemporaneous=False: 64_07=19481.830ms; 128_07=16733.770ms; 32_07=14048.383ms; 256_07=12249.154ms; 1024_07=12900.222ms; 512_07=12300.614ms
- `R08` span=387.0s near_contemporaneous=False: 64_08=13573.064ms; 128_08=12441.179ms; 32_08=13162.768ms; 256_08=12255.447ms; 1024_08=12831.990ms; 512_08=12448.704ms
- `R09` span=325.0s near_contemporaneous=True: 64_09=12173.738ms; 128_09=12032.824ms; 32_09=13295.760ms; 256_09=12328.509ms; 1024_09=12998.492ms; 512_09=12696.065ms
- `R10` span=331.0s near_contemporaneous=True: 64_10=12797.104ms; 32_10=13410.585ms; 128_10=12808.075ms; 256_10=12248.508ms; 1024_10=12946.514ms; 512_10=12394.575ms
- `R11` span=264.0s near_contemporaneous=True: 64_11=13007.940ms; 128_11=12587.742ms; 32_11=13142.064ms; 256_11=12390.509ms; 512_11=12095.460ms; 1024_11=12796.888ms
- `R12` span=190.0s near_contemporaneous=True: 64_12=13030.190ms; 32_12=13140.856ms; 128_12=12428.374ms; 256_12=12634.048ms; 512_12=12352.970ms; 1024_12=12942.564ms

## Correlations

Pearson and Spearman values are descriptive across the 72 rows and are not causal estimates.

| pair | n | Pearson | Spearman |
|---|---:|---:|---:|
| arm_mib vs golden_internal_wall_ms | 72 | -0.059 | -0.223 |
| arm_mib vs combined_loader_wall_ms | 72 | 0.082 | 0.219 |
| arm_mib vs stage:clip_load | 72 | 0.108 | 0.376 |
| arm_mib vs transport:clip:source_wall_ms | 72 | 0.038 | 0.412 |
| arm_mib vs residual:CLIP_LOAD_RESIDUAL_MS | 72 | 0.375 | 0.182 |
| arm_mib vs stage:unet_load | 72 | 0.028 | 0.013 |
| arm_mib vs transport:unet:source_wall_ms | 72 | 0.187 | 0.351 |
| arm_mib vs residual:UNET_LOAD_RESIDUAL_MS | 72 | -0.532 | -0.940 |
| arm_mib vs stage:clip_forward | 72 | -0.021 | 0.192 |
| arm_mib vs stage:sampling | 72 | 0.029 | 0.295 |
| arm_mib vs stage:vae_decode | 72 | 0.003 | -0.092 |
| arm_mib vs transport:clip:copy_count | 72 | -0.666 | -1.000 |
| arm_mib vs transport:unet:copy_count | 72 | -0.667 | -1.000 |
| arm_mib vs transport:clip:event_rerecord_count | 72 | -0.666 | -1.000 |
| arm_mib vs transport:unet:event_rerecord_count | 72 | -0.667 | -1.000 |
| golden_internal_wall_ms vs combined_loader_wall_ms | 72 | 0.951 | 0.815 |
| golden_internal_wall_ms vs stage:clip_load | 72 | 0.877 | 0.648 |
| golden_internal_wall_ms vs transport:clip:source_wall_ms | 72 | 0.818 | 0.435 |
| golden_internal_wall_ms vs residual:CLIP_LOAD_RESIDUAL_MS | 72 | 0.481 | 0.600 |
| golden_internal_wall_ms vs stage:unet_load | 72 | 0.808 | 0.725 |
| golden_internal_wall_ms vs transport:unet:source_wall_ms | 72 | 0.734 | 0.510 |
| golden_internal_wall_ms vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.453 | 0.320 |
| golden_internal_wall_ms vs stage:clip_forward | 72 | 0.539 | 0.259 |
| golden_internal_wall_ms vs stage:sampling | 72 | 0.401 | 0.163 |
| golden_internal_wall_ms vs stage:vae_decode | 72 | 0.290 | 0.362 |
| golden_internal_wall_ms vs transport:clip:copy_count | 72 | 0.092 | 0.223 |
| golden_internal_wall_ms vs transport:unet:copy_count | 72 | 0.092 | 0.223 |
| golden_internal_wall_ms vs transport:clip:event_rerecord_count | 72 | 0.092 | 0.223 |
| golden_internal_wall_ms vs transport:unet:event_rerecord_count | 72 | 0.092 | 0.223 |
| combined_loader_wall_ms vs stage:clip_load | 72 | 0.955 | 0.804 |
| combined_loader_wall_ms vs transport:clip:source_wall_ms | 72 | 0.917 | 0.701 |
| combined_loader_wall_ms vs residual:CLIP_LOAD_RESIDUAL_MS | 72 | 0.368 | 0.555 |
| combined_loader_wall_ms vs stage:unet_load | 72 | 0.804 | 0.853 |
| combined_loader_wall_ms vs transport:unet:source_wall_ms | 72 | 0.797 | 0.796 |
| combined_loader_wall_ms vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.248 | -0.084 |
| combined_loader_wall_ms vs stage:clip_forward | 72 | 0.346 | 0.232 |
| combined_loader_wall_ms vs stage:sampling | 72 | 0.216 | 0.187 |
| combined_loader_wall_ms vs stage:vae_decode | 72 | 0.149 | 0.206 |
| combined_loader_wall_ms vs transport:clip:copy_count | 72 | -0.084 | -0.219 |
| combined_loader_wall_ms vs transport:unet:copy_count | 72 | -0.084 | -0.219 |
| combined_loader_wall_ms vs transport:clip:event_rerecord_count | 72 | -0.084 | -0.219 |
| combined_loader_wall_ms vs transport:unet:event_rerecord_count | 72 | -0.084 | -0.219 |
| stage:clip_load vs transport:clip:source_wall_ms | 72 | 0.985 | 0.818 |
| stage:clip_load vs residual:CLIP_LOAD_RESIDUAL_MS | 72 | 0.234 | 0.685 |
| stage:clip_load vs stage:unet_load | 72 | 0.594 | 0.464 |
| stage:clip_load vs transport:unet:source_wall_ms | 72 | 0.619 | 0.458 |
| stage:clip_load vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.095 | -0.226 |
| stage:clip_load vs stage:clip_forward | 72 | 0.212 | 0.398 |
| stage:clip_load vs stage:sampling | 72 | 0.157 | 0.180 |
| stage:clip_load vs stage:vae_decode | 72 | 0.100 | 0.232 |
| stage:clip_load vs transport:clip:copy_count | 72 | -0.113 | -0.376 |
| stage:clip_load vs transport:unet:copy_count | 72 | -0.113 | -0.376 |
| stage:clip_load vs transport:clip:event_rerecord_count | 72 | -0.113 | -0.376 |
| stage:clip_load vs transport:unet:event_rerecord_count | 72 | -0.113 | -0.376 |
| transport:clip:source_wall_ms vs residual:CLIP_LOAD_RESIDUAL_MS | 72 | 0.066 | 0.245 |
| transport:clip:source_wall_ms vs stage:unet_load | 72 | 0.529 | 0.455 |
| transport:clip:source_wall_ms vs transport:unet:source_wall_ms | 72 | 0.580 | 0.537 |
| transport:clip:source_wall_ms vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.005 | -0.277 |
| transport:clip:source_wall_ms vs stage:clip_forward | 72 | 0.115 | 0.371 |
| transport:clip:source_wall_ms vs stage:sampling | 72 | 0.114 | 0.280 |
| transport:clip:source_wall_ms vs stage:vae_decode | 72 | 0.069 | 0.190 |
| transport:clip:source_wall_ms vs transport:clip:copy_count | 72 | -0.133 | -0.412 |
| transport:clip:source_wall_ms vs transport:unet:copy_count | 72 | -0.133 | -0.412 |
| transport:clip:source_wall_ms vs transport:clip:event_rerecord_count | 72 | -0.133 | -0.412 |
| transport:clip:source_wall_ms vs transport:unet:event_rerecord_count | 72 | -0.133 | -0.412 |
| residual:CLIP_LOAD_RESIDUAL_MS vs stage:unet_load | 72 | 0.476 | 0.278 |
| residual:CLIP_LOAD_RESIDUAL_MS vs transport:unet:source_wall_ms | 72 | 0.321 | 0.179 |
| residual:CLIP_LOAD_RESIDUAL_MS vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.564 | -0.049 |
| residual:CLIP_LOAD_RESIDUAL_MS vs stage:clip_forward | 72 | 0.593 | 0.218 |
| residual:CLIP_LOAD_RESIDUAL_MS vs stage:sampling | 72 | 0.278 | 0.065 |
| residual:CLIP_LOAD_RESIDUAL_MS vs stage:vae_decode | 72 | 0.202 | 0.215 |
| residual:CLIP_LOAD_RESIDUAL_MS vs transport:clip:copy_count | 72 | 0.137 | -0.182 |
| residual:CLIP_LOAD_RESIDUAL_MS vs transport:unet:copy_count | 72 | 0.136 | -0.182 |
| residual:CLIP_LOAD_RESIDUAL_MS vs transport:clip:event_rerecord_count | 72 | 0.137 | -0.182 |
| residual:CLIP_LOAD_RESIDUAL_MS vs transport:unet:event_rerecord_count | 72 | 0.137 | -0.182 |
| stage:unet_load vs transport:unet:source_wall_ms | 72 | 0.955 | 0.904 |
| stage:unet_load vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.415 | 0.090 |
| stage:unet_load vs stage:clip_forward | 72 | 0.437 | 0.073 |
| stage:unet_load vs stage:sampling | 72 | 0.224 | 0.110 |
| stage:unet_load vs stage:vae_decode | 72 | 0.186 | 0.180 |
| stage:unet_load vs transport:clip:copy_count | 72 | -0.016 | -0.013 |
| stage:unet_load vs transport:unet:copy_count | 72 | -0.015 | -0.013 |
| stage:unet_load vs transport:clip:event_rerecord_count | 72 | -0.016 | -0.013 |
| stage:unet_load vs transport:unet:event_rerecord_count | 72 | -0.016 | -0.013 |
| transport:unet:source_wall_ms vs residual:UNET_LOAD_RESIDUAL_MS | 72 | 0.130 | -0.246 |
| transport:unet:source_wall_ms vs stage:clip_forward | 72 | 0.299 | 0.103 |
| transport:unet:source_wall_ms vs stage:sampling | 72 | 0.190 | 0.276 |
| transport:unet:source_wall_ms vs stage:vae_decode | 72 | 0.161 | 0.128 |
| transport:unet:source_wall_ms vs transport:clip:copy_count | 72 | -0.237 | -0.351 |
| transport:unet:source_wall_ms vs transport:unet:copy_count | 72 | -0.237 | -0.351 |
| transport:unet:source_wall_ms vs transport:clip:event_rerecord_count | 72 | -0.237 | -0.351 |
| transport:unet:source_wall_ms vs transport:unet:event_rerecord_count | 72 | -0.237 | -0.351 |
| residual:UNET_LOAD_RESIDUAL_MS vs stage:clip_forward | 72 | 0.513 | -0.052 |
| residual:UNET_LOAD_RESIDUAL_MS vs stage:sampling | 72 | 0.149 | -0.265 |
| residual:UNET_LOAD_RESIDUAL_MS vs stage:vae_decode | 72 | 0.125 | 0.203 |
| residual:UNET_LOAD_RESIDUAL_MS vs transport:clip:copy_count | 72 | 0.697 | 0.940 |
| residual:UNET_LOAD_RESIDUAL_MS vs transport:unet:copy_count | 72 | 0.697 | 0.940 |
| residual:UNET_LOAD_RESIDUAL_MS vs transport:clip:event_rerecord_count | 72 | 0.697 | 0.940 |
| residual:UNET_LOAD_RESIDUAL_MS vs transport:unet:event_rerecord_count | 72 | 0.697 | 0.940 |
| stage:clip_forward vs stage:sampling | 72 | 0.738 | 0.273 |
| stage:clip_forward vs stage:vae_decode | 72 | 0.441 | 0.279 |
| stage:clip_forward vs transport:clip:copy_count | 72 | -0.069 | -0.192 |
| stage:clip_forward vs transport:unet:copy_count | 72 | -0.069 | -0.192 |
| stage:clip_forward vs transport:clip:event_rerecord_count | 72 | -0.069 | -0.192 |
| stage:clip_forward vs transport:unet:event_rerecord_count | 72 | -0.069 | -0.192 |
| stage:sampling vs stage:vae_decode | 72 | 0.485 | 0.156 |
| stage:sampling vs transport:clip:copy_count | 72 | -0.189 | -0.295 |
| stage:sampling vs transport:unet:copy_count | 72 | -0.189 | -0.295 |
| stage:sampling vs transport:clip:event_rerecord_count | 72 | -0.189 | -0.295 |
| stage:sampling vs transport:unet:event_rerecord_count | 72 | -0.189 | -0.295 |
| stage:vae_decode vs transport:clip:copy_count | 72 | -0.042 | 0.092 |
| stage:vae_decode vs transport:unet:copy_count | 72 | -0.042 | 0.092 |
| stage:vae_decode vs transport:clip:event_rerecord_count | 72 | -0.042 | 0.092 |
| stage:vae_decode vs transport:unet:event_rerecord_count | 72 | -0.042 | 0.092 |
| transport:clip:copy_count vs transport:unet:copy_count | 72 | 1.000 | 1.000 |
| transport:clip:copy_count vs transport:clip:event_rerecord_count | 72 | 1.000 | 1.000 |
| transport:clip:copy_count vs transport:unet:event_rerecord_count | 72 | 1.000 | 1.000 |
| transport:unet:copy_count vs transport:clip:event_rerecord_count | 72 | 1.000 | 1.000 |
| transport:unet:copy_count vs transport:unet:event_rerecord_count | 72 | 1.000 | 1.000 |
| transport:clip:event_rerecord_count vs transport:unet:event_rerecord_count | 72 | 1.000 | 1.000 |

## Reporting Bug And Live Display Audit

The direct_source_geometry branch _geometry_report builds a schema-version-1 summary with request_wall_ms, combined_loader_wall_ms, and selected transport summaries only. It does not read session_events_path, event_data.golden_adapter_timing, or serialize per-run stage values/reconciliation. The older generic renderer has stage helpers, but direct_source_geometry returns before that path.

Live display: `Golden call wall [ADAPTER CALL]`; field `golden_adapter_timing.golden_call_wall_ms`; comfymodal_runtime/modal_app.py:_format_golden_waterfall, timing label at line 1532; emitted by _emit_golden_waterfall.

The persisted `waterfall` object is partial and `UNRESOLVED`; its total/scheduling fields are null. It cannot explain or replace the adapter-call wall.

## Conclusions

- SOURCE WINNER: CLIP source wall is 32 MiB by median; UNET source wall is 32 MiB by median. These are separate from enclosing loader walls.
- LOADER WINNER: 256 MiB by median, with the full mean/SD/CV ranking above.
- WHOLE-GOLDEN WINNER: 256 MiB by median, with the full mean/SD/CV ranking above.
- Loader residuals and compute-stage deltas are reported separately; a later-stage difference is cohort/server compute variance, not automatically a geometry gain.
- No production geometry decision is made from these observational cohorts alone; the persisted external/scheduling boundaries and host stratification are incomplete.

## Evidence Gaps

- The persisted waterfall object is partial/UNRESOLVED for all rows: modal restore begin, submission, and local receipt boundaries are unavailable, so no authoritative scheduling-delay decomposition exists.
- The application adapter wall includes post-stage adapter work; stage telemetry explains the stage interval but cannot be treated as equivalent to the enclosing call wall.
- Container ID fields are empty where the runtime did not persist them; container_session_id/modal_task_id are retained when present.
- One raw result event is persisted per request; no separate raw event stream with additional enclosing boundaries is present in the named session-events files.
- E27 source-mechanism proof is not uniform across roles/rows (CLIP, UNET, and VAE proof fields are retained per run); artifact validity and output SHA validity are separate claims.

## Ledger Path Inventory

Every run row in the companion JSON contains the exact attempt artifact, summary, session-events, run-manifest, and evidence-Markdown paths. The companion JSON is the authoritative complete ledger for those mappings.

## Final Disposition

1. Observed 12-14 s metric: adapter Golden call wall, not request/platform wall or stage sum.
2. The answer to every requested arm/ranking/delta question is represented in Tables A-I, rankings, decomposition_vs_32, and the JSON fields `rankings`, `core_extra_stats`, `provider_region_stats`, `best_valid_runs`, and `median_representative_runs`.
3. No evidence was filtered for speed, provider, region, or outlier status.

