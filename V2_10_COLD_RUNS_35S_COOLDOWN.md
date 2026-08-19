# V2 - 10 Cold Runs, 35 s Cooldown (Production-Equivalent Restore Characterization)

Deployment: `b557b2401f293223` (restore-only shadow app, UNET excluded from CPU snapshot, RTX PRO 6000 / 12 CPU / 32768 MB, cloud/region unrestricted, single-use cold, PNG level 1). No redeploy performed. Batch: `run_v2_single.bat` with `V2_BENCHMARK_RUNS=10`, `V2_BENCHMARK_GAP_SECONDS=35`. Log: `v2_c2f_10cold_35gap.log`. Artifacts: `comfymodal-data/benchmarks/runs/v2_2026-08-13_23-06-56/` (run_0..run_9.json).

## Cold validation

All 10 runs are **cold** (`Fresh: YES`, unique restored instance IDs, `STATUS OK`). The 35 s cooldown resolved the warm-container reuse seen in the earlier 20 s-gap batch (runs 2/5/7 there had repeated instance IDs, `Fresh: NO`, and `EXCEEDS_TOLERANCE`). Those runs were repeated in this batch.

| Run | Request ID | Provider/Region | Fresh | Scheduling | TOTAL WALL | Reconciliation |
| --- | ---------- | --------------- | ----- | ---------: | ----------: | -------------: |
| 1 | `v2-benchmark-0-3fd12cf96902` | GCP/us-east4 | YES | 1.231 s | 37.313 s | 1.126 ms |
| 2 | `v2-benchmark-1-2ba29b73d946` | GCP/us-east4 | YES | 1.441 s | 15.708 s | 2.641 ms |
| 3 | `v2-benchmark-2-98e5ac32b9c3` | GCP/us-east1 | YES | 25.927 s | 15.407 s | 0.754 ms |
| 4 | `v2-benchmark-3-3be52a7f2037` | GCP/us-east4 | YES | 2.313 s | 26.471 s | -0.253 ms |
| 5 | `v2-benchmark-4-6fbc1eab6772` | GCP/us-east4 | YES | 5.935 s | 15.404 s | -1.325 ms |
| 6 | `v2-benchmark-5-008cc501ccf4` | GCP/us-east1 | YES | 1.615 s | 16.426 s | -0.752 ms |
| 7 | `v2-benchmark-6-82d3a007a46d` | AWS/eu-south-2 | YES | 63.485 s | 15.456 s | -0.346 ms |
| 8 | `v2-benchmark-7-8d42af2d35ba` | GCP/us-east4 | YES | 1.332 s | 15.146 s | 0.693 ms |
| 9 | `v2-benchmark-8-33a16df15cd3` | GCP/us-east4 | YES | 1.982 s | 16.408 s | 5.708 ms |
| 10 | `v2-benchmark-9-42ab912f9de0` | GCP/us-east4 | YES | 0.699586 s | 15.018 s | 0.684 ms |

## Per-run waterfall tables (verbatim, first table per run)

### Run 1 - `v2-benchmark-0-3fd12cf96902` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              | 493.157 ms | 493.157 ms |   1.322% | #                                        |
|   2 | Modal handle and submission                    |    21.059s |    21.553s |  56.440% | #######################                  |
|   3 | Modal pre-Python snapshot restoration          |     3.452s |    25.005s |   9.252% | ####                                     |
|   4 | Python/application restore                     | 387.172 ms |    25.392s |   1.038% | #                                        |
|   5 | Restore-to-method entry                        |  20.341 ms |    25.412s |   0.055% | #                                        |
|   6 | Remote method setup                            | 478.709 ms |    25.891s |   1.283% | #                                        |
|     |   method entry to graph start                  |  87.919 ms |            |          |                                          |
|     |   method entry to runtime configuration        |  87.846 ms |            |          |                                          |
|     |   graph setup                                  | 390.790 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   9.822 ms |    25.901s |   0.026% | #                                        |
|   8 | Pre-sampler execution                          |     4.053s |    29.954s |  10.863% | ####                                     |
|     |   Conditioning cache exact_hit lookup=48.788ms |  48.788 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 624.564 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 132.655 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.477s |            |          |                                          |
|     |   Read end -> construction done                |   1.066 ms |            |          |                                          |
|     |   UNET get_model                               |  60.212 ms |            |          |                                          |
|     |   Bind                                         |  25.463 ms |            |          |                                          |
|     |   Synchronized H2D (5.0 GB/s)                  |     2.454s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.763 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 125.355 ms |    30.080s |   0.336% | #                                        |
|     |   lane acquired to actual stage                | 125.335 ms |            |          |                                          |
|  10 | Sampling                                       |     4.808s |    34.888s |  12.887% | #####                                    |
|  11 | Post-sampling / VAE transition                 | 744.609 ms |    35.633s |   1.996% | #                                        |
|  12 | VAE decode                                     | 380.572 ms |    36.013s |   1.020% | #                                        |
|     |   VAE load/H2D                                 | 764.426 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 245.419 ms |    36.259s |   0.658% | #                                        |
|     |   PNG encode                                   | 169.953 ms |            |          |                                          |
|  14 | Remote result handoff                          |     1.037s |    37.296s |   2.779% | #                                        |
|  15 | Local result handling / caller return          |  16.000 ms |    37.312s |   0.043% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.231s |            |          |                                          |
|     | RECONCILIATION                                 |   1.126 ms |            |          |                                          |
|     | STATUS                        
```

### Run 2 - `v2-benchmark-1-2ba29b73d946` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.085 ms |   0.085 ms |   0.001% | #                                        |
|   2 | Modal handle and submission                    |  31.513 ms |  31.598 ms |   0.201% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     3.856s |     3.887s |  24.546% | ##########                               |
|   4 | Python/application restore                     | 620.523 ms |     4.508s |   3.950% | ##                                       |
|   5 | Restore-to-method entry                        |  15.124 ms |     4.523s |   0.096% | #                                        |
|   6 | Remote method setup                            | 129.672 ms |     4.653s |   0.825% | #                                        |
|     |   method entry to graph start                  |  84.476 ms |            |          |                                          |
|     |   method entry to runtime configuration        |  84.394 ms |            |          |                                          |
|     |   graph setup                                  |  45.196 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   9.432 ms |     4.662s |   0.060% | #                                        |
|   8 | Pre-sampler execution                          |     3.618s |     8.280s |  23.030% | #########                                |
|     |   Conditioning cache exact_hit lookup=43.552ms |  43.552 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 671.119 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  25.707 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 134.683 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.187s |            |          |                                          |
|     |   Read end -> construction done                |   0.235 ms |            |          |                                          |
|     |   UNET get_model                               |  47.891 ms |            |          |                                          |
|     |   Bind                                         |  20.380 ms |            |          |                                          |
|     |   Synchronized H2D (5.3 GB/s)                  |     2.332s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.573 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 128.029 ms |     8.408s |   0.815% | #                                        |
|     |   lane acquired to actual stage                | 128.009 ms |            |          |                                          |
|  10 | Sampling                                       |     4.806s |    13.214s |  30.596% | ############                             |
|  11 | Post-sampling / VAE transition                 | 833.170 ms |    14.047s |   5.304% | ##                                       |
|  12 | VAE decode                                     | 400.626 ms |    14.448s |   2.550% | #                                        |
|     |   VAE load/H2D                                 | 863.368 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 248.735 ms |    14.696s |   1.583% | #                                        |
|     |   PNG encode                                   | 174.149 ms |            |          |                                          |
|  14 | Remote result handoff                          | 994.339 ms |    15.691s |   6.330% | ###                                      |
|  15 | Local result handling / caller return          |  15.000 ms |    15.706s |   0.095% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.441s |            |          |                                          |
|     | RECONCILIATION                                 |   2.641 ms |            |          |                                          |
|     | STATUS                        
```

### Run 3 - `v2-benchmark-2-98e5ac32b9c3` (GCP/us-east1)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.149 ms |   0.149 ms |   0.001% | #                                        |
|   2 | Modal handle and submission                    |  30.033 ms |  30.182 ms |   0.195% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     3.272s |     3.302s |  21.237% | ########                                 |
|   4 | Python/application restore                     | 470.762 ms |     3.773s |   3.055% | #                                        |
|   5 | Restore-to-method entry                        |  38.388 ms |     3.811s |   0.249% | #                                        |
|   6 | Remote method setup                            | 389.526 ms |     4.201s |   2.528% | #                                        |
|     |   method entry to graph start                  | 258.944 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 258.873 ms |            |          |                                          |
|     |   graph setup                                  | 130.581 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  16.410 ms |     4.217s |   0.107% | #                                        |
|   8 | Pre-sampler execution                          |     3.819s |     8.036s |  24.786% | ##########                               |
|     |   Conditioning cache exact_hit lookup=42.137ms |  42.137 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 576.665 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  48.042 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 145.122 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.280s |            |          |                                          |
|     |   Read end -> construction done                |   0.254 ms |            |          |                                          |
|     |   UNET get_model                               |  40.521 ms |            |          |                                          |
|     |   Bind                                         |  20.653 ms |            |          |                                          |
|     |   Synchronized H2D (5.1 GB/s)                  |     2.432s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.751 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 137.391 ms |     8.174s |   0.892% | #                                        |
|     |   lane acquired to actual stage                | 137.368 ms |            |          |                                          |
|  10 | Sampling                                       |     4.856s |    13.029s |  31.515% | #############                            |
|  11 | Post-sampling / VAE transition                 | 697.331 ms |    13.726s |   4.526% | ##                                       |
|  12 | VAE decode                                     | 380.148 ms |    14.107s |   2.467% | #                                        |
|     |   VAE load/H2D                                 | 721.597 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 251.417 ms |    14.358s |   1.632% | #                                        |
|     |   PNG encode                                   | 173.602 ms |            |          |                                          |
|  14 | Remote result handoff                          |     1.032s |    15.390s |   6.701% | ###                                      |
|  15 | Local result handling / caller return          |  16.000 ms |    15.406s |   0.104% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    25.927s |            |          |                                          |
|     | RECONCILIATION                                 |   0.754 ms |            |          |                                          |
|     | STATUS                        
```

### Run 4 - `v2-benchmark-3-3be52a7f2037` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.196 ms |   0.196 ms |   0.001% | #                                        |
|   2 | Modal handle and submission                    |  26.024 ms |  26.220 ms |   0.098% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     6.487s |     6.513s |  24.507% | ##########                               |
|   4 | Python/application restore                     |     1.535s |     8.048s |   5.797% | ##                                       |
|   5 | Restore-to-method entry                        |  15.202 ms |     8.063s |   0.057% | #                                        |
|   6 | Remote method setup                            | 297.737 ms |     8.361s |   1.125% | #                                        |
|     |   method entry to graph start                  | 228.823 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 228.764 ms |            |          |                                          |
|     |   graph setup                                  |  68.914 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  14.854 ms |     8.376s |   0.056% | #                                        |
|   8 | Pre-sampler execution                          |    10.681s |    19.057s |  40.349% | ################                         |
|     |   Conditioning cache exact_hit lookup=49.496ms |  49.496 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 736.999 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  41.868 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 144.049 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.336s |            |          |                                          |
|     |   Read end -> construction done                |   0.172 ms |            |          |                                          |
|     |   UNET get_model                               |  48.146 ms |            |          |                                          |
|     |   Bind                                         |  21.078 ms |            |          |                                          |
|     |   Synchronized H2D (1.3 GB/s)                  |     9.229s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.645 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 137.148 ms |    19.194s |   0.518% | #                                        |
|     |   lane acquired to actual stage                | 137.126 ms |            |          |                                          |
|  10 | Sampling                                       |     4.816s |    24.010s |  18.194% | #######                                  |
|  11 | Post-sampling / VAE transition                 | 844.012 ms |    24.854s |   3.188% | #                                        |
|  12 | VAE decode                                     | 378.742 ms |    25.233s |   1.431% | #                                        |
|     |   VAE load/H2D                                 | 871.225 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 255.737 ms |    25.489s |   0.966% | #                                        |
|     |   PNG encode                                   | 179.347 ms |            |          |                                          |
|  14 | Remote result handoff                          | 967.880 ms |    26.457s |   3.656% | #                                        |
|  15 | Local result handling / caller return          |  15.000 ms |    26.472s |   0.057% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     2.313s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.253 ms |            |          |                                          |
|     | STATUS                        
```

### Run 5 - `v2-benchmark-4-6fbc1eab6772` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.771 ms |   0.771 ms |   0.005% | #                                        |
|   2 | Modal handle and submission                    |  25.000 ms |  25.771 ms |   0.162% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     3.514s |     3.540s |  22.813% | #########                                |
|   4 | Python/application restore                     | 534.947 ms |     4.075s |   3.473% | #                                        |
|   5 | Restore-to-method entry                        |  20.287 ms |     4.095s |   0.132% | #                                        |
|   6 | Remote method setup                            | 127.541 ms |     4.223s |   0.828% | #                                        |
|     |   method entry to graph start                  |  87.459 ms |            |          |                                          |
|     |   method entry to runtime configuration        |  87.377 ms |            |          |                                          |
|     |   graph setup                                  |  40.082 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  16.803 ms |     4.239s |   0.109% | #                                        |
|   8 | Pre-sampler execution                          |     3.743s |     7.983s |  24.302% | ##########                               |
|     |   Conditioning cache exact_hit lookup=46.424ms |  46.424 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 577.631 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  25.146 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 130.306 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.199s |            |          |                                          |
|     |   Read end -> construction done                |   0.488 ms |            |          |                                          |
|     |   UNET get_model                               |  70.782 ms |            |          |                                          |
|     |   Bind                                         |  37.926 ms |            |          |                                          |
|     |   Synchronized H2D (5.1 GB/s)                  |     2.421s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.687 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 123.759 ms |     8.107s |   0.803% | #                                        |
|     |   lane acquired to actual stage                | 123.733 ms |            |          |                                          |
|  10 | Sampling                                       |     4.786s |    12.893s |  31.071% | ############                             |
|  11 | Post-sampling / VAE transition                 | 925.064 ms |    13.818s |   6.005% | ##                                       |
|  12 | VAE decode                                     | 366.221 ms |    14.184s |   2.377% | #                                        |
|     |   VAE load/H2D                                 | 944.466 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 242.061 ms |    14.426s |   1.571% | #                                        |
|     |   PNG encode                                   | 166.708 ms |            |          |                                          |
|  14 | Remote result handoff                          | 963.125 ms |    15.389s |   6.252% | ###                                      |
|  15 | Local result handling / caller return          |  16.000 ms |    15.405s |   0.104% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     5.935s |            |          |                                          |
|     | RECONCILIATION                                 |  -1.325 ms |            |          |                                          |
|     | STATUS                        
```

### Run 6 - `v2-benchmark-5-008cc501ccf4` (GCP/us-east1)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.297 ms |   0.297 ms |   0.002% | #                                        |
|   2 | Modal handle and submission                    |  22.829 ms |  23.126 ms |   0.139% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     4.895s |     4.918s |  29.799% | ############                             |
|   4 | Python/application restore                     | 611.526 ms |     5.530s |   3.723% | #                                        |
|   5 | Restore-to-method entry                        |  33.880 ms |     5.563s |   0.206% | #                                        |
|   6 | Remote method setup                            | 235.252 ms |     5.799s |   1.432% | #                                        |
|     |   method entry to graph start                  | 198.408 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 198.370 ms |            |          |                                          |
|     |   graph setup                                  |  36.844 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   7.869 ms |     5.807s |   0.048% | #                                        |
|   8 | Pre-sampler execution                          |     3.202s |     9.008s |  19.493% | ########                                 |
|     |   Conditioning cache exact_hit lookup=35.570ms |  35.570 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 551.910 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 110.398 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.062s |            |          |                                          |
|     |   Read end -> construction done                |   0.146 ms |            |          |                                          |
|     |   UNET get_model                               |  74.435 ms |            |          |                                          |
|     |   Bind                                         |  18.412 ms |            |          |                                          |
|     |   Synchronized H2D (6.1 GB/s)                  |     2.008s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.859 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 102.986 ms |     9.111s |   0.627% | #                                        |
|     |   lane acquired to actual stage                | 102.962 ms |            |          |                                          |
|  10 | Sampling                                       |     4.758s |    13.869s |  28.964% | ############                             |
|  11 | Post-sampling / VAE transition                 | 895.544 ms |    14.765s |   5.452% | ##                                       |
|  12 | VAE decode                                     | 365.645 ms |    15.130s |   2.226% | #                                        |
|     |   VAE load/H2D                                 | 914.498 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 251.026 ms |    15.381s |   1.528% | #                                        |
|     |   PNG encode                                   | 175.909 ms |            |          |                                          |
|  14 | Remote result handoff                          |     1.030s |    16.411s |   6.269% | ###                                      |
|  15 | Local result handling / caller return          |  16.000 ms |    16.427s |   0.097% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.615s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.752 ms |            |          |                                          |
|     | STATUS                        
```

### Run 7 - `v2-benchmark-6-82d3a007a46d` (AWS/eu-south-2)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.117 ms |   0.117 ms |   0.001% | #                                        |
|   2 | Modal handle and submission                    |  23.784 ms |  23.901 ms |   0.154% | #                                        |
|   3 | Modal pre-Python snapshot restoration          | 809.095 ms | 832.996 ms |   5.235% | ##                                       |
|   4 | Python/application restore                     | 987.361 ms |     1.820s |   6.388% | ###                                      |
|   5 | Restore-to-method entry                        | 270.029 ms |     2.090s |   1.747% | #                                        |
|   6 | Remote method setup                            | 806.132 ms |     2.897s |   5.216% | ##                                       |
|     |   method entry to graph start                  | 633.638 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 633.588 ms |            |          |                                          |
|     |   graph setup                                  | 172.494 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   4.845 ms |     2.901s |   0.031% | #                                        |
|   8 | Pre-sampler execution                          |     5.127s |     8.029s |  33.176% | #############                            |
|     |   Conditioning cache exact_hit lookup=94.514ms |  94.514 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           |     1.091s |            |          |                                          |
|     |   Node: ImpactSwitch                           |  39.142 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 137.808 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.708s |            |          |                                          |
|     |   Read end -> construction done                |   0.129 ms |            |          |                                          |
|     |   UNET get_model                               |  83.088 ms |            |          |                                          |
|     |   Bind                                         |  15.690 ms |            |          |                                          |
|     |   Synchronized H2D (3.8 GB/s)                  |     3.274s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.887 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 130.517 ms |     8.159s |   0.844% | #                                        |
|     |   lane acquired to actual stage                | 130.499 ms |            |          |                                          |
|  10 | Sampling                                       |     4.884s |    13.043s |  31.598% | #############                            |
|  11 | Post-sampling / VAE transition                 | 420.174 ms |    13.463s |   2.719% | #                                        |
|  12 | VAE decode                                     | 413.084 ms |    13.876s |   2.673% | #                                        |
|     |   VAE load/H2D                                 | 456.364 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 261.499 ms |    14.138s |   1.692% | #                                        |
|     |   PNG encode                                   | 168.974 ms |            |          |                                          |
|  14 | Remote result handoff                          |     1.302s |    15.440s |   8.425% | ###                                      |
|  15 | Local result handling / caller return          |  16.000 ms |    15.456s |   0.104% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |    63.485s |            |          |                                          |
|     | RECONCILIATION                                 |  -0.346 ms |            |          |                                          |
|     | STATUS                        
```

### Run 8 - `v2-benchmark-7-8d42af2d35ba` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.233 ms |   0.233 ms |   0.002% | #                                        |
|   2 | Modal handle and submission                    |  23.476 ms |  23.709 ms |   0.155% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     2.560s |     2.584s |  16.904% | #######                                  |
|   4 | Python/application restore                     |     1.201s |     3.785s |   7.929% | ###                                      |
|   5 | Restore-to-method entry                        |  15.988 ms |     3.801s |   0.106% | #                                        |
|   6 | Remote method setup                            | 241.023 ms |     4.042s |   1.591% | #                                        |
|     |   method entry to graph start                  | 181.221 ms |            |          |                                          |
|     |   method entry to runtime configuration        | 181.187 ms |            |          |                                          |
|     |   graph setup                                  |  59.801 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  14.900 ms |     4.057s |   0.098% | #                                        |
|   8 | Pre-sampler execution                          |     3.657s |     7.714s |  24.143% | ##########                               |
|     |   Conditioning cache exact_hit lookup=52.313ms |  52.313 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 595.726 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  27.754 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 133.049 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.323s |            |          |                                          |
|     |   Read end -> construction done                |   0.546 ms |            |          |                                          |
|     |   UNET get_model                               |  62.977 ms |            |          |                                          |
|     |   Bind                                         |  28.127 ms |            |          |                                          |
|     |   Synchronized H2D (5.5 GB/s)                  |     2.224s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.810 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 126.007 ms |     7.840s |   0.832% | #                                        |
|     |   lane acquired to actual stage                | 125.966 ms |            |          |                                          |
|  10 | Sampling                                       |     4.802s |    12.641s |  31.701% | #############                            |
|  11 | Post-sampling / VAE transition                 | 888.190 ms |    13.529s |   5.864% | ##                                       |
|  12 | VAE decode                                     | 376.628 ms |    13.906s |   2.487% | #                                        |
|     |   VAE load/H2D                                 | 916.155 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 251.883 ms |    14.158s |   1.663% | #                                        |
|     |   PNG encode                                   | 177.793 ms |            |          |                                          |
|  14 | Remote result handoff                          | 971.597 ms |    15.130s |   6.415% | ###                                      |
|  15 | Local result handling / caller return          |  16.000 ms |    15.146s |   0.106% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.332s |            |          |                                          |
|     | RECONCILIATION                                 |   0.693 ms |            |          |                                          |
|     | STATUS                        
```

### Run 9 - `v2-benchmark-8-33a16df15cd3` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.905 ms |   0.905 ms |   0.006% | #                                        |
|   2 | Modal handle and submission                    |  22.832 ms |  23.736 ms |   0.139% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     4.153s |     4.177s |  25.310% | ##########                               |
|   4 | Python/application restore                     |     1.081s |     5.257s |   6.587% | ###                                      |
|   5 | Restore-to-method entry                        |  18.771 ms |     5.276s |   0.114% | #                                        |
|   6 | Remote method setup                            | 135.984 ms |     5.412s |   0.829% | #                                        |
|     |   method entry to graph start                  |  92.757 ms |            |          |                                          |
|     |   method entry to runtime configuration        |  92.715 ms |            |          |                                          |
|     |   graph setup                                  |  43.227 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |  14.786 ms |     5.427s |   0.090% | #                                        |
|   8 | Pre-sampler execution                          |     3.545s |     8.972s |  21.607% | #########                                |
|     |   Conditioning cache exact_hit lookup=49.509ms |  49.509 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 618.244 ms |            |          |                                          |
|     |   Node: ImpactSwitch                           |  57.772 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 133.454 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.185s |            |          |                                          |
|     |   Read end -> construction done                |   0.189 ms |            |          |                                          |
|     |   UNET get_model                               |  59.976 ms |            |          |                                          |
|     |   Bind                                         |  23.288 ms |            |          |                                          |
|     |   Synchronized H2D (5.5 GB/s)                  |     2.219s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.705 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 125.330 ms |     9.098s |   0.764% | #                                        |
|     |   lane acquired to actual stage                | 125.303 ms |            |          |                                          |
|  10 | Sampling                                       |     4.837s |    13.935s |  29.479% | ############                             |
|  11 | Post-sampling / VAE transition                 | 888.642 ms |    14.823s |   5.416% | ##                                       |
|  12 | VAE decode                                     | 350.878 ms |    15.174s |   2.138% | #                                        |
|     |   VAE load/H2D                                 | 906.539 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 236.732 ms |    15.411s |   1.443% | #                                        |
|     |   PNG encode                                   | 163.283 ms |            |          |                                          |
|  14 | Remote result handoff                          | 975.458 ms |    16.386s |   5.945% | ##                                       |
|  15 | Local result handling / caller return          |  16.000 ms |    16.402s |   0.098% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     |     1.982s |            |          |                                          |
|     | RECONCILIATION                                 |   5.708 ms |            |          |                                          |
|     | STATUS                        
```

### Run 10 - `v2-benchmark-9-42ab912f9de0` (GCP/us-east4)

```text
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   # | Stage                                          |   Duration |       Cum. |        % | Relative wall (TOTAL WALL)               |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|   1 | Local preparation                              |   0.228 ms |   0.228 ms |   0.002% | #                                        |
|   2 | Modal handle and submission                    |  24.001 ms |  24.229 ms |   0.160% | #                                        |
|   3 | Modal pre-Python snapshot restoration          |     3.503s |     3.527s |  23.324% | #########                                |
|   4 | Python/application restore                     | 462.180 ms |     3.989s |   3.078% | #                                        |
|   5 | Restore-to-method entry                        |  20.517 ms |     4.010s |   0.137% | #                                        |
|   6 | Remote method setup                            | 124.561 ms |     4.134s |   0.829% | #                                        |
|     |   method entry to graph start                  |  86.948 ms |            |          |                                          |
|     |   method entry to runtime configuration        |  86.884 ms |            |          |                                          |
|     |   graph setup                                  |  37.612 ms |            |          |                                          |
|   7 | PromptExecutor/cache setup                     |   9.958 ms |     4.144s |   0.066% | #                                        |
|   8 | Pre-sampler execution                          |     3.497s |     7.641s |  23.285% | #########                                |
|     |   Conditioning cache exact_hit lookup=34.307ms |  34.307 ms |            |          |                                          |
|     |   CLIP encode skipped (cache hit)              |          - |            |          |                                          |
|     |   Node: ImpactSwitch                           | 586.718 ms |            |          |                                          |
|     |   Node: ClownsharKSampler_Beta                 | 124.251 ms |            |          |                                          |
|     |   Checkpoint read                              |     1.145s |            |          |                                          |
|     |   Read end -> construction done                |   0.373 ms |            |          |                                          |
|     |   UNET get_model                               |  73.698 ms |            |          |                                          |
|     |   Bind                                         |  36.281 ms |            |          |                                          |
|     |   Synchronized H2D (5.6 GB/s)                  |     2.209s |            |          |                                          |
|     |   H2D end -> UNET ready                        |   1.845 ms |            |          |                                          |
|   9 | Sampler node to sampling                       | 116.307 ms |     7.757s |   0.774% | #                                        |
|     |   lane acquired to actual stage                | 116.287 ms |            |          |                                          |
|  10 | Sampling                                       |     4.813s |    12.571s |  32.052% | #############                            |
|  11 | Post-sampling / VAE transition                 | 839.864 ms |    13.411s |   5.593% | ##                                       |
|  12 | VAE decode                                     | 365.270 ms |    13.776s |   2.432% | #                                        |
|     |   VAE load/H2D                                 | 864.117 ms |            |          |                                          |
|  13 | Output encode / descriptor                     | 249.873 ms |    14.026s |   1.664% | #                                        |
|     |   PNG encode                                   | 175.214 ms |            |          |                                          |
|  14 | Remote result handoff                          | 976.167 ms |    15.002s |   6.500% | ###                                      |
|  15 | Local result handling / caller return          |  15.000 ms |    15.017s |   0.100% | #                                        |
+-----+------------------------------------------------+------------+------------+----------+------------------------------------------+
|     | SCHEDULING                                     | 699.586 ms |            |          |                                          |
|     | RECONCILIATION                                 |   0.684 ms |            |          |                                          |
|     | STATUS                        
```

## Diagnostics (captured per run)

### Run 1

- PromptExecutor: `exec_to_cached_ms=7.62 dynamic_prompt_ms=0.007 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.035 cache_gather_ms=0.272 cleanup_gc_ms=2.029 residual_ms=5.277 c2f_cached_to_first_node_ms=1.107 c2f_topo_walk_ms=1.083 c2f_topo_input_info_ms=0.113 c2f_topo_other_ms=0.97 c2f_stage_ms=1.551 c2f_first_node_prefix_ms=0.173 c2f_residual_ms=-1.7 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.49 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=48.788 total_ms=48.552 key_build_ms=0.24 lock_wait_ms=0.006 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=16.134 header_bytes=3751 data_bytes=2900184 lru_touch_ms=31.388 lru_touch_mode=sync children_ms=47.768 residual_ms=0.784 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=22.601 prefetch_join_timeout=0 prefetch_overlap_ms=29.817 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=399.563 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=169.924 png_compress_ms=163.72 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 2

- PromptExecutor: `exec_to_cached_ms=6.643 dynamic_prompt_ms=0.008 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.025 cache_gather_ms=0.255 cleanup_gc_ms=1.487 residual_ms=4.868 c2f_cached_to_first_node_ms=1.121 c2f_topo_walk_ms=1.006 c2f_topo_input_info_ms=0.093 c2f_topo_other_ms=0.913 c2f_stage_ms=1.431 c2f_first_node_prefix_ms=0.187 c2f_residual_ms=-1.503 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.446 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=43.552 total_ms=43.24 key_build_ms=0.354 lock_wait_ms=0.005 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=12.302 header_bytes=3751 data_bytes=2900184 lru_touch_ms=30.013 lru_touch_mode=sync children_ms=42.674 residual_ms=0.566 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=16.923 prefetch_join_timeout=0 prefetch_overlap_ms=33.248 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=71.395 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=174.143 png_compress_ms=168.287 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 3

- PromptExecutor: `exec_to_cached_ms=14.559 dynamic_prompt_ms=0.009 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.025 cache_gather_ms=0.31 cleanup_gc_ms=1.005 residual_ms=13.21 c2f_cached_to_first_node_ms=1.026 c2f_topo_walk_ms=0.971 c2f_topo_input_info_ms=0.091 c2f_topo_other_ms=0.88 c2f_stage_ms=1.434 c2f_first_node_prefix_ms=0.178 c2f_residual_ms=-1.557 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=4.574 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=42.137 total_ms=41.754 key_build_ms=0.181 lock_wait_ms=0.006 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=18.306 header_bytes=3751 data_bytes=2900184 lru_touch_ms=22.72 lru_touch_mode=sync children_ms=41.213 residual_ms=0.541 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=15.418 prefetch_join_timeout=0 prefetch_overlap_ms=27.503 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=306.327 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=173.417 png_compress_ms=165.775 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 4

- PromptExecutor: `exec_to_cached_ms=12.468 dynamic_prompt_ms=0.003 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.035 cache_gather_ms=0.131 cleanup_gc_ms=7.801 residual_ms=4.498 c2f_cached_to_first_node_ms=0.709 c2f_topo_walk_ms=0.541 c2f_topo_input_info_ms=0.104 c2f_topo_other_ms=0.437 c2f_stage_ms=1.29 c2f_first_node_prefix_ms=0.146 c2f_residual_ms=-1.268 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.492 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=49.496 total_ms=49.261 key_build_ms=0.165 lock_wait_ms=0.001 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=13.778 header_bytes=3751 data_bytes=2900184 lru_touch_ms=30.438 lru_touch_mode=sync children_ms=44.382 residual_ms=4.879 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=24.976 prefetch_join_timeout=0 prefetch_overlap_ms=34.099 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=218.306 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=179.32 png_compress_ms=173.145 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 5

- PromptExecutor: `exec_to_cached_ms=14.356 dynamic_prompt_ms=0.008 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.033 cache_gather_ms=0.278 cleanup_gc_ms=0.959 residual_ms=13.078 c2f_cached_to_first_node_ms=1.034 c2f_topo_walk_ms=0.892 c2f_topo_input_info_ms=0.09 c2f_topo_other_ms=0.802 c2f_stage_ms=1.474 c2f_first_node_prefix_ms=0.24 c2f_residual_ms=-1.572 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=4.098 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=46.424 total_ms=46.123 key_build_ms=0.308 lock_wait_ms=0.006 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=19.007 header_bytes=3751 data_bytes=2900184 lru_touch_ms=26.295 lru_touch_mode=sync children_ms=45.616 residual_ms=0.507 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=17.129 prefetch_join_timeout=0 prefetch_overlap_ms=26.803 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=74.61 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=166.693 png_compress_ms=161.469 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 6

- PromptExecutor: `exec_to_cached_ms=6.654 dynamic_prompt_ms=0.004 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.015 cache_gather_ms=0.125 cleanup_gc_ms=0.966 residual_ms=5.544 c2f_cached_to_first_node_ms=0.741 c2f_topo_walk_ms=0.547 c2f_topo_input_info_ms=0.109 c2f_topo_other_ms=0.438 c2f_stage_ms=1.262 c2f_first_node_prefix_ms=0.153 c2f_residual_ms=-1.221 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=4.098 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=35.57 total_ms=35.301 key_build_ms=0.181 lock_wait_ms=0.001 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=12.434 header_bytes=3751 data_bytes=2900184 lru_touch_ms=22.159 lru_touch_mode=sync children_ms=34.775 residual_ms=0.526 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=11.448 prefetch_join_timeout=0 prefetch_overlap_ms=24.25 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=180.26 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=175.894 png_compress_ms=170.233 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 7

- PromptExecutor: `exec_to_cached_ms=4.014 dynamic_prompt_ms=0.003 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.015 cache_gather_ms=0.113 cleanup_gc_ms=0.44 residual_ms=3.443 c2f_cached_to_first_node_ms=0.526 c2f_topo_walk_ms=0.477 c2f_topo_input_info_ms=0.079 c2f_topo_other_ms=0.398 c2f_stage_ms=1.162 c2f_first_node_prefix_ms=0.094 c2f_residual_ms=-1.207 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=2.625 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=94.514 total_ms=94.194 key_build_ms=0.178 lock_wait_ms=0.001 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=52.742 header_bytes=3751 data_bytes=2900184 lru_touch_ms=40.793 lru_touch_mode=sync children_ms=93.714 residual_ms=0.48 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=247.842 prefetch_join_timeout=0 prefetch_overlap_ms=89.334 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=508.824 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=168.963 png_compress_ms=162.439 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 8

- PromptExecutor: `exec_to_cached_ms=5.333 dynamic_prompt_ms=0.004 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.017 cache_gather_ms=0.129 cleanup_gc_ms=1.043 residual_ms=4.14 c2f_cached_to_first_node_ms=0.619 c2f_topo_walk_ms=0.475 c2f_topo_input_info_ms=0.103 c2f_topo_other_ms=0.372 c2f_stage_ms=1.355 c2f_first_node_prefix_ms=0.159 c2f_residual_ms=-1.37 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=2.99 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=52.313 total_ms=52.017 key_build_ms=0.185 lock_wait_ms=0.002 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=16.729 header_bytes=3751 data_bytes=2900184 lru_touch_ms=34.777 lru_touch_mode=sync children_ms=51.693 residual_ms=0.324 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=27.992 prefetch_join_timeout=0 prefetch_overlap_ms=41.099 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=176.753 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=177.775 png_compress_ms=166.357 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 9

- PromptExecutor: `exec_to_cached_ms=13.381 dynamic_prompt_ms=0.003 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.019 cache_gather_ms=0.127 cleanup_gc_ms=8.306 residual_ms=4.926 c2f_cached_to_first_node_ms=0.759 c2f_topo_walk_ms=0.545 c2f_topo_input_info_ms=0.092 c2f_topo_other_ms=0.453 c2f_stage_ms=1.354 c2f_first_node_prefix_ms=0.169 c2f_residual_ms=-1.309 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=3.321 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=49.509 total_ms=49.299 key_build_ms=0.178 lock_wait_ms=0.001 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=11.958 header_bytes=3751 data_bytes=2900184 lru_touch_ms=35.425 lru_touch_mode=sync children_ms=47.562 residual_ms=1.737 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=27.177 prefetch_join_timeout=0 prefetch_overlap_ms=36.519 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=58.779 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=163.272 png_compress_ms=157.409 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

### Run 10

- PromptExecutor: `exec_to_cached_ms=7.961 dynamic_prompt_ms=0.009 is_changed_ms=absent signature_keys_ms=absent seed_apply_ms=absent clean_unused_ms=0.067 cache_gather_ms=0.258 cleanup_gc_ms=1.711 residual_ms=5.916 c2f_cached_to_first_node_ms=1.04 c2f_topo_walk_ms=0.983 c2f_topo_input_info_ms=0.103 c2f_topo_other_ms=0.88 c2f_stage_ms=1.257 c2f_first_node_prefix_ms=0.175 c2f_residual_ms=-1.375 signature_cache_eligible=True signature_cache_fallback= signature_cache_hit=True signature_cache_key_hash=c886cdac34eae03f17a5e0278b46f9f08fae5dcb75356a31185dfe9cb71d3063 signature_cache_requested=True signature_cache_source=volume signature_reuse_ms=4.429 topo_lazy_hits=36`
- Conditioning: `decision=exact_hit lookup_wall_ms=34.307 total_ms=34.057 key_build_ms=0.239 lock_wait_ms=0.008 manifest_read_ms=0.0 manifest_bytes=0 manifest_entries=25 entry_lookup_ms=6.291 header_bytes=3751 data_bytes=2900184 lru_touch_ms=26.058 lru_touch_mode=sync children_ms=32.596 residual_ms=1.461 entries_requested=1 hit_count=1 lru_async_batch_size=0 lru_async_batches=0 lru_async_dropped=0 lru_async_enqueued=0 lru_async_failed=0 lru_async_flush_count=0 lru_async_persist_ms=0.0 manifest_memory_hit=1 miss_count=0 normal_lookup_fallback=0 payload_memory_hit=1 payload_memory_source=key_hit prefetch_join_ms=7.652 prefetch_join_timeout=0 prefetch_overlap_ms=23.322 prefetch_payload_entries=3 prefetch_reason=key_build_partial:weight_dtype prefetch_reload=skipped_first prefetch_requested=1 prefetch_source=full prefetch_wall_ms=42.954 volume_reload_ms=0.0`
- PNG: `compress_level=1 png_encode_ms=175.205 png_compress_ms=170.268 width=1088 height=1920 bytes=3129718 sha=20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`

## Metrics table

| Run | Provider | Pre-Python restore | Python restore | PromptExecutor/cache setup | cached->first-node | Pre-sampler | Sampling | PNG | Handoff | Raw TOTAL WALL | Production-adjusted TOTAL WALL |
| --- | -------- | -----------------: | -------------: | -------------------------: | ----------------: | ----------: | -------: | --: | ------: | -------------: | -----------------------------: |
| 1 | GCP/us-east4 | 3452 | 387 | 10 | 1.107 | 4053 | 4808 | 245 | 1037 | 37.313 | 16376.7 |
| 2 | GCP/us-east4 | 3856 | 621 | 9 | 1.121 | 3618 | 4806 | 249 | 994 | 15.708 | 15708.0 |
| 3 | GCP/us-east1 | 3272 | 471 | 16 | 1.026 | 3819 | 4856 | 251 | 1032 | 15.407 | 15407.0 |
| 4 | GCP/us-east4 | 6487 | 1535 | 15 | 0.709 | 10681 | 4816 | 256 | 968 | 26.471 | 26471.0 |
| 5 | GCP/us-east4 | 3514 | 535 | 17 | 1.034 | 3743 | 4786 | 242 | 963 | 15.404 | 15404.0 |
| 6 | GCP/us-east1 | 4895 | 612 | 8 | 0.741 | 3202 | 4758 | 251 | 1030 | 16.426 | 16426.0 |
| 7 | AWS/eu-south-2 | 809 | 987 | 5 | 0.526 | 5127 | 4884 | 261 | 1302 | 15.456 | 15456.0 |
| 8 | GCP/us-east4 | 2560 | 1201 | 15 | 0.619 | 3657 | 4802 | 252 | 972 | 15.146 | 15146.0 |
| 9 | GCP/us-east4 | 4153 | 1081 | 15 | 0.759 | 3545 | 4837 | 237 | 975 | 16.408 | 16408.0 |
| 10 | GCP/us-east4 | 3503 | 462 | 10 | 1.04 | 3497 | 4813 | 250 | 976 | 15.018 | 15018.0 |

> **Production-adjusted TOTAL WALL note.** The harness subtracts the host node-registry init from every run's wall. In a single process the registry loads once (run 1 only; ~20.9 s measured here), so runs 2-10 did not pay it; their artifact `production_adjusted_total_wall_ms` values are negative artifacts of subtracting a cost not incurred. The corrected production-adjusted wall above is: run 1 = TOTAL WALL - registry init (16.376 s); runs 2-10 = TOTAL WALL (no benchmark-only cost paid). Scheduling is already excluded from TOTAL WALL; pre-Python/Python restore and application work are kept.

## Distributions (10 cold runs)

```text
Pre-Python restore (ms): 809, 2560, 3272, 3452, 3503, 3514, 3856, 4153, 4895, 6487
  min = 809.1  median = 3508.5  max = 6487.0
Python restore (ms):    387, 462, 471, 535, 612, 621, 987, 1081, 1201, 1535
  min = 387.2  median = 616.0  max = 1535.0
Production-adjusted TOTAL WALL (ms): 15018, 15146, 15404, 15407, 15456, 15708, 16377, 16408, 16426, 26471
  min = 15018.0  median = 15582.0  max = 26471.0
Sorted (s): 15.0, 15.1, 15.4, 15.4, 15.5, 15.7, 16.4, 16.4, 16.4, 26.5
```

## Analysis

- **Cold integrity:** 10/10 runs Fresh=YES with distinct instances; all reconciliations within tolerance (<= 5.7 ms).
- **cached->first-node:** 0.5-1.1 ms on every run (`topo_lazy` replay active; signature memo hit each time). PromptExecutor/cache setup is 5-17 ms - the ~1.47 s interval is fully eliminated.
- **Conditioning:** `exact_hit` on all runs with `manifest_memory_hit=1`/`payload_memory_hit=1` (prefetch default ON).
- **Platform restore:** pre-Python snapshot restore median 3.5 s (range 0.8-6.5 s; run 4's 6.5 s is the slow end, still valid); Python restore median 0.6 s.
- **Sub-14 assessment:** production-adjusted TOTAL WALL min 15.0 s, median 15.6 s, max 26.5 s (run 4's 26.5 s is driven by a slow pre-sampler window of 10.7 s plus a 6.5 s pre-Python restore on that host). Even the best run is ~15 s; application-after-resume alone is ~12-13 s (sampling 4.8 s + H2D 2.2 s + checkpoint read ~1.2 s + VAE/PNG/handoff ~3 s). Sub-14 is not consistently achievable with this platform+application profile.
