# September UNET/CLIP Experiment 04 - Contemporary Source Ceiling Oracle

PERFORMANCE_COMPARISON=NOT_PERFORMED

PERFORMANCE_VERDICT=NOT_PROVIDED

STATUS=COMPLETE

DECISION_CATEGORY=SOURCE_CEILING_NOT_RECOVERED

## Scope

This experiment measured source-to-CUDA readiness directly, without model construction, ComfyUI execution, snapshot capture, restore, binding, sampling, or output generation. It used one isolated deployment in the Testing 7 Modal workspace and 16 serial single-use-container requests: CLIP and UNET, each under QD256 and FastSafe, with four observations per arm.

The decision category is an experiment result, not a production promotion decision. The existing reporting contract therefore retains `PERFORMANCE_COMPARISON=NOT_PERFORMED` and `PERFORMANCE_VERDICT=NOT_PROVIDED`.

## Deployment Identity

| field | value |
|---|---|
| workspace | Testing 7 |
| environment | main |
| app | `sept-unetclip-04-source-ceiling-oracle` |
| deployment | `https://modal.com/apps/testing7/main/deployed/sept-unetclip-04-source-ceiling-oracle` |
| image | `im-v2C7hQYVNqlPjiTAGPuwOh` |
| provider | `CLOUD_PROVIDER_GCP` |
| region | `us-east1` |
| GPU | `rtx-pro-6000` |
| models volume | `comfyui-models`, mounted read-only at `/root/models` |
| source evidence | `unetClipExperimentsSeptember/04_source_ceiling_runs/` |
| runner | `tools/run_exp04_source_ceiling.py` |

Deployment receipt path, deployment fingerprint, request IDs, output/durability fields, and ComfyUI stage fields are `UNAVAILABLE`; this oracle intentionally has no ComfyUI request lifecycle.

## Fixed Arms

| arm | fixed configuration | gate |
|---|---|---|
| QD256 | `static_e27`, QD=4, 4 producers, 256 MiB source blocks, 256 MiB H2D target, aggregation disabled | 8/8 arm records passed |
| FastSafe CLIP | T8, 512 MiB bbuf, 64 MiB copy blocks, `nogds=True`, `use_buf_register=False`, `disable_cache=True` | 4/4 arm records passed |
| FastSafe UNET | T8, 512 MiB bbuf, 256 MiB copy blocks, `nogds=True`, `use_buf_register=False`, `disable_cache=True` | 4/4 arm records passed |

QD physical syscall provenance was `golden_serial._read_at` and `E27_SOURCE_MECHANISM_PROVEN=YES` on all QD records.

## Cohort Audit

| property | result |
|---|---:|
| ordered observations | 16 |
| valid observations | 16 |
| DNF observations | 0 |
| distinct container sessions | 16 |
| serial execution | true |
| byte validation | 16/16 passed |
| model construction | false for all 16 |
| snapshot capture | not applicable, not counted |

The source files were `qwen_3_4b.safetensors` (8,044,982,048 bytes) and `z_image_turbo_bf16.safetensors` (12,309,866,400 bytes). Every record used the fixed read-only models mount.

## Source-to-CUDA Statistics

Metric: `FILE_TO_CUDA_WALL_MS`.

| role | arm | n | min | max | mean | median | sample SD | CV |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CLIP | QD256 | 4 | 1086.160 | 4088.560 | 1875.983 | 1164.606 | 1475.641 | 0.787 |
| CLIP | FastSafe | 4 | 1539.873 | 1624.089 | 1582.579 | 1583.178 | 36.463 | 0.023 |
| UNET | QD256 | 4 | 1929.050 | 3824.398 | 2706.861 | 2536.999 | 812.476 | 0.300 |
| UNET | FastSafe | 4 | 2163.885 | 2844.403 | 2487.921 | 2471.698 | 279.204 | 0.112 |

## Historical Reference

The supplied historical reference values were CLIP `490.7 ms` and UNET `699.4 ms`. The contemporary medians are descriptively 2.37x / 3.23x historical for CLIP QD256 / FastSafe, and 3.63x / 3.53x historical for UNET QD256 / FastSafe. None reaches the historical reference; this supports `SOURCE_CEILING_NOT_RECOVERED`.

## Invariants And Decomposition

- All 16 records report `model_construction=false`.
- All 16 records report successful source-to-device byte validation using sampled tensor payloads.
- All QD records report `configured_qd=4`, `producer_count=4`, `source_block_bytes=268435456`, `h2d_target_bytes=268435456`, and `aggregation_enabled=false`.
- All QD records report `E27_SOURCE_MECHANISM_PROVEN=YES` and the expected physical syscall provenance.
- All FastSafe records report the required T8, no-GDS, no buffer registration, disabled cache, and role-specific block size settings.
- QD copy activity and stream-span telemetry are retained in each raw JSON artifact; nested telemetry is not added to the primary wall metric.
- No output, durability, snapshot, restore, binding, compute, or ComfyUI stage was applicable to this source-only oracle.

## Ordered Attempt Ledger

| attempt | role | arm | status | `FILE_TO_CUDA_WALL_MS` | artifact |
|---|---|---|---|---:|---|
| `clip_qd256_R1` | CLIP | QD256 | ok | 4088.560 | `04_source_ceiling_runs/clip_qd256_R1.json` |
| `clip_qd256_R2` | CLIP | QD256 | ok | 1188.259 | `04_source_ceiling_runs/clip_qd256_R2.json` |
| `clip_qd256_R3` | CLIP | QD256 | ok | 1140.952 | `04_source_ceiling_runs/clip_qd256_R3.json` |
| `clip_qd256_R4` | CLIP | QD256 | ok | 1086.160 | `04_source_ceiling_runs/clip_qd256_R4.json` |
| `clip_fastsafe_R1` | CLIP | FastSafe | ok | 1568.327 | `04_source_ceiling_runs/clip_fastsafe_R1.json` |
| `clip_fastsafe_R2` | CLIP | FastSafe | ok | 1598.029 | `04_source_ceiling_runs/clip_fastsafe_R2.json` |
| `clip_fastsafe_R3` | CLIP | FastSafe | ok | 1624.089 | `04_source_ceiling_runs/clip_fastsafe_R3.json` |
| `clip_fastsafe_R4` | CLIP | FastSafe | ok | 1539.873 | `04_source_ceiling_runs/clip_fastsafe_R4.json` |
| `unet_qd256_R1` | UNET | QD256 | ok | 1929.050 | `04_source_ceiling_runs/unet_qd256_R1.json` |
| `unet_qd256_R2` | UNET | QD256 | ok | 2351.572 | `04_source_ceiling_runs/unet_qd256_R2.json` |
| `unet_qd256_R3` | UNET | QD256 | ok | 3824.398 | `04_source_ceiling_runs/unet_qd256_R3.json` |
| `unet_qd256_R4` | UNET | QD256 | ok | 2722.425 | `04_source_ceiling_runs/unet_qd256_R4.json` |
| `unet_fastsafe_R1` | UNET | FastSafe | ok | 2446.596 | `04_source_ceiling_runs/unet_fastsafe_R1.json` |
| `unet_fastsafe_R2` | UNET | FastSafe | ok | 2163.885 | `04_source_ceiling_runs/unet_fastsafe_R2.json` |
| `unet_fastsafe_R3` | UNET | FastSafe | ok | 2844.403 | `04_source_ceiling_runs/unet_fastsafe_R3.json` |
| `unet_fastsafe_R4` | UNET | FastSafe | ok | 2496.801 | `04_source_ceiling_runs/unet_fastsafe_R4.json` |

## Raw Artifact Inventory

The complete JSON companion is `04_contemporary_source_ceiling_oracle.json`. It contains the fixed arm definitions, cohort audit, statistics, ordered artifact paths, and explicitly unavailable fields. The 16 per-attempt JSON artifacts under `04_source_ceiling_runs/` retain identity, timing, fixed configuration, byte validation, ownership, transport telemetry, and cleanup-related evidence.
