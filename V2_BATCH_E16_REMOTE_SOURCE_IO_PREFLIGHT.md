# V2 Batch E16 Remote Source-I/O Preflight

Date: 2026-08-17  
Scope: source-I/O validation only. No graph execution, inference, sampling, or production-loader change was performed.

## Execution Identity

- Dedicated app: `comfyui-modal-e16-source-io`
- Resource shape: `rtx-pro-6000`, 12 CPU, 32768 MiB memory, single-use container, read-only mount
- Models Volume: `comfyui-models` mounted at `/root/models`
- RUN1 container/image: `ta-01M070MQMYG8ZZ66MWF43K3G9R` / `im-HCCxo0LDVJAQwAi2HQ92Mb`
- RUN1 placement: `CLOUD_PROVIDER_AWS`, `us-east-2`
- RUN2 container/image: `ta-01M070XQC5B31Z8CFY8QZSCDDR` / `im-2TxFbK5pFmdkbNEIBqoZX9`
- RUN2 placement: `CLOUD_PROVIDER_GCP`, `us-east1`
- Provider and region were intentionally unpinned. The differing placements prevent a clean cross-request causal performance claim.
- The two requests used the same model plan, image recipe, resource shape, mounted Volume, and source code state at request time. The Modal run command materialized distinct image IDs.

## Volume Generation

The endpoint performed the requested read-only probe:

```python
modal.Volume.from_name(
    "comfyui-models",
    create_if_missing=False,
    version=1,
).hydrate()
```

The probe succeeded in both requests:

```text
CURRENT_VOLUME_GENERATION = V1
```

No Volume was created, migrated, renamed, deleted, committed, or written.

## Authoritative Model Resolution

The packaged `v2_restore_plan.json` supplied the current canonical model plan. The endpoint resolved model names from that plan, attempted ComfyUI `folder_paths.get_full_path`, and then used the mounted Volume path when the resolver did not expose the mounted path directly. No model was loaded.

| Role | Plan filename | Canonical path | Remote resolved path | Resolver | File bytes | Tensor-data bytes | Tensors |
|---|---|---|---|---|---:|---:|---:|
| CLIP | `qwen_3_4b.safetensors` | `/root/models/text_encoders/qwen_3_4b.safetensors` | `/__modal/volumes/vo-QI6fCKykvocVkUBVGsuZgm/text_encoders/qwen_3_4b.safetensors` | mounted Volume fallback | 8,044,982,048 | 8,044,936,192 | 398 |
| UNET | `z_image_turbo_bf16.safetensors` | `/root/models/diffusion_models/z_image_turbo_bf16.safetensors` | `/__modal/volumes/vo-QI6fCKykvocVkUBVGsuZgm/diffusion_models/z_image_turbo_bf16.safetensors` | mounted Volume fallback | 12,309,866,400 | 12,309,817,472 | 453 |

The stored `.model_manifest.json` has no authoritative SHA-256 for these entries. The per-arm payload digests were therefore used for read validation, without adding a separate full-file hash pass:

- CLIP payload digest: `e48ed5beffc1b93d4c244f36e9c336b707707ed262666b4c2102819dfab101a1`
- UNET payload digest: `f0660776d3ec870bf0a5f74497e7e6e324fb207b9d257265de896af06fd93d30`

## E11 Eligibility

The actual `comfymodal_runtime.staged_safetensors.plan()` path was run with source-order enabled and the actual `source_order_safetensors.assess_eligibility()` gate was evaluated against the real headers.

| Role | Total tensors | Eligible tensors | Eligible bytes | Total tensor bytes | Eligible by tensor | Eligible by bytes | Density gap |
|---|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 398 | 398 | 8,044,936,192 | 8,044,936,192 | 100.000% | 100.000% | 0 |
| UNET | 453 | 453 | 12,309,817,472 | 12,309,817,472 | 100.000% | 100.000% | 0 |

Fallback reason counts and bytes were zero for both models: alignment, dtype, shape/density, bounds, size mismatch, unsupported representation, and other exact reason.

## Linux Pinned `preadv` Proof

The bounded proof allocated four 256 MiB CUDA-capable PyTorch CPU slabs, verified every slab as pinned, and read 256 MiB per model through the E11 `source_order_safetensors.read_into()` Linux `os.preadv` branch.

```text
PREADV_BRANCH_USED = True
PREADV_CALLS = 2 per request (1 CLIP + 1 UNET)
PREADV_BYTES = 536,870,912 per request
HOST_SLAB_IS_PINNED_ALL = True
BYTE_VALIDATION = True
DIRECT_SOURCE_TO_PINNED_COPY_BYTES = 0
```

The bounded probe returned byte-identical data for every checked range. Full source-order arms also reported `io_backend=e11.preadv`, 256 MiB blocks, exact digest matches, and zero source-to-pinned copy bytes.

## `/tmp` and Cache Control

Both containers reported:

- filesystem: `overlay`
- available/free bytes: `9,223,372,036,849,594,368`
- exact CLIP + UNET file bytes required: `20,354,848,448`
- safety headroom used: `4,294,967,296`
- `TMP_STAGE_CAPACITY = PASS`

The reported overlay capacity is unusually large and should not be interpreted as a guarantee beyond this worker observation.

```text
LOCAL_CACHE_RESET_CAPABILITY = PARTIAL
```

`posix_fadvise(POSIX_FADV_DONTNEED)` was available and permitted for file-local hints. Mmap release was available. `/proc/sys/vm/drop_caches` did not exist and no global cache state was changed. All timings remain `cold_unknown`; provider-side and distributed-storage cache state was not proven cold.

## Primary Results

All primary arms processed the same tensor-data bytes. `CURRENT_RANGE` used 32 MiB extent chunks. `SEQUENTIAL_SOURCE_ORDER` used E11's 256 MiB contiguous source blocks into pinned slabs. Every primary and secondary digest matched.

### CLIP

| Request | Current range wall / GBps | Source-order wall / GBps | Source-order delta |
|---|---:|---:|---:|
| RUN1, AWS us-east-2 | 9,252.483 ms / 0.869 | 6,417.157 ms / 1.254 | -30.644% |
| RUN2, GCP us-east1 | 5,369.775 ms / 1.498 | 5,872.120 ms / 1.370 | +9.355% |

RUN1 CLIP geometry: current 529 calls, 256 B / 16,252,928 B median / 33,554,432 B max; source-order 30 calls, 268,435,456 B median, 260,307,968 B final block.  
RUN2 used the same geometry.

### UNET

| Request | Current range wall / GBps | Source-order wall / GBps | Source-order delta |
|---|---:|---:|---:|
| RUN1, AWS us-east-2 | 11,095.192 ms / 1.109 | 12,262.137 ms / 1.004 | +10.518% |
| RUN2, GCP us-east1 | 9,715.240 ms / 1.267 | 7,467.020 ms / 1.649 | -23.141% |

RUN1 UNET geometry: current 725 calls, 128 B / 11,534,336 B median / 33,554,432 B max; source-order 46 calls, 268,435,456 B median, 230,221,952 B final block.  
RUN2 used the same geometry.

### MMAP

MMAP was materially similar to the direct arms rather than a separate fast tier:

- CLIP: RUN1 7,899.468 ms / 1.018 GBps; RUN2 5,758.703 ms / 1.397 GBps
- UNET: RUN1 11,924.798 ms / 1.032 GBps; RUN2 8,839.045 ms / 1.393 GBps

### TMP_STAGE

TMP results include the complete Volume-to-`/tmp` copy plus local reread. The relevant first-cold number is `copy + reread`, not the local reread alone.

| Request / role | Volume -> `/tmp` copy ms | `/tmp` reread ms | Combined ms | Copy GBps | Reread GBps |
|---|---:|---:|---:|---:|---:|
| RUN1 / CLIP | 2,654.102 | 7,486.704 | 10,140.806 | 3.031 | 1.075 |
| RUN1 / UNET | 3,981.407 | 11,482.275 | 15,463.682 | 3.092 | 1.072 |
| RUN2 / CLIP | 1,709.403 | 4,966.368 | 6,675.771 | 4.706 | 1.620 |
| RUN2 / UNET | 2,312.613 | 7,545.748 | 9,858.361 | 5.323 | 1.631 |

TMP combined time did not beat direct source access for either model in either request. The first remote artifact left the aggregate `wall_ms` field empty for TMP while preserving the per-model `combined_ms`; the local post-run fix now sets aggregate TMP wall/CPU fields for future runs. This report uses the captured per-model copy/reread timings above.

## Pageable Versus Pinned Fill

This was a bounded 512 MiB UNET source-range subtest with 256 MiB read geometry, no H2D:

- RUN1: pageable 701.352 ms; pinned 703.063 ms; overhead `+0.244%`
- RUN2: pageable 447.845 ms; pinned 436.736 ms; overhead `-2.481%`
- Crossover mean: pageable 574.598 ms; pinned 569.900 ms; overhead `-0.818%`

The two samples do not show a material pinned-fill penalty.

## Timing Semantics

- `wall_ms` is elapsed wall time for one arm in one process.
- `process_cpu_ms` is process CPU time for the arm; it is not worker-summed time.
- The source-order benchmark is a single sequential endpoint loop, not a threaded worker accumulation measurement.
- `TMP_STAGE` combined time is copy wall plus local reread wall. Its copy and reread legs are reported separately.
- Effective GBps is decimal bytes per elapsed second. Primary direct-arm GBps uses tensor-data bytes. TMP uses copy bytes plus local reread bytes divided by combined wall.
- `cold_unknown` is the only defensible cache label. `posix_fadvise` success is not proof of provider-side eviction.

## E12 Physical Estimate Only

No E12 prewarmer was integrated or run. Using the two measured combined source-order rates only as a physical estimate:

- RUN1 combined source-order: 1.090 GBps, so 0.5 s / 1 s / 2 s estimates are 545,000,000 / 1,090,000,000 / 2,180,000,000 bytes.
- RUN2 combined source-order: 1.526 GBps, so 0.5 s / 1 s / 2 s estimates are 763,000,000 / 1,526,000,000 / 3,052,000,000 bytes.
- Crossover mean: 1.308 GBps, so the 1 s and 2 s estimates are approximately 1,308,000,000 and 2,616,000,000 bytes.

These are `ESTIMATE_FROM_MEASURED_THROUGHPUT`, not observed prewarm savings.

## Decision

The real E11 path is mechanically proven for both major files: 100% eligibility, Linux `preadv`, fully pinned slabs, byte validation, zero hidden source-to-pinned copy, and zero repack. However:

- Source-order did not win consistently per model across the crossover.
- RUN1 and RUN2 used different provider/region placements.
- CURRENT_RANGE, source-order, and MMAP all sit in the same broad storage-throughput neighborhood.
- A 12.31 GB UNET physically takes roughly 7.5 to 12.3 seconds for these direct source reads; H2D time cannot remove the Volume-to-host arrival time.
- `/tmp` staging does not win after copy-in.
- The bounded pinned-fill result shows no material pageable-to-pinned overhead.

```text
RESULT = INCONCLUSIVE
NEXT_STEP = Do not change production defaults or add E15 loaders. Keep native E11 staged-B and E12 independently opt-in; if revisited, use a same-provider/same-region controlled source-only comparison before enabling integration.
```

The evidence is compatible with `STORAGE_THROUGHPUT_LIMITED`, but the placement mismatch and per-model crossover reversal make `INCONCLUSIVE` the required final classification for this batch.

## Required Final Values

```text
E16_COMPLETE

REMOTE_DEPLOYS = 1
REMOTE_REQUESTS = 2

PROVIDER_RUN1 = CLOUD_PROVIDER_AWS
REGION_RUN1 = us-east-2
PROVIDER_RUN2 = CLOUD_PROVIDER_GCP
REGION_RUN2 = us-east1

CURRENT_VOLUME_GENERATION = V1

CLIP_PATH = /root/models/text_encoders/qwen_3_4b.safetensors
CLIP_FILE_BYTES = 8044982048
CLIP_TENSOR_BYTES = 8044936192
CLIP_TENSORS = 398
CLIP_SOURCE_ORDER_ELIGIBLE_BYTES_PERCENT = 100.000

UNET_PATH = /root/models/diffusion_models/z_image_turbo_bf16.safetensors
UNET_FILE_BYTES = 12309866400
UNET_TENSOR_BYTES = 12309817472
UNET_TENSORS = 453
UNET_SOURCE_ORDER_ELIGIBLE_BYTES_PERCENT = 100.000

LINUX_PREADV_PROVEN = YES
HOST_SLAB_IS_PINNED_ALL = YES
DIRECT_SOURCE_TO_PINNED_COPY_BYTES = 0

TMP_FREE_BYTES = 9223372036849594368
TMP_STAGE_CAPACITY = PASS

LOCAL_CACHE_RESET_CAPABILITY = PARTIAL

CLIP_CURRENT_RANGE_WALL_MS = RUN1 9252.483; RUN2 5369.775
CLIP_CURRENT_RANGE_GBPS = RUN1 0.869; RUN2 1.498
CLIP_SOURCE_ORDER_WALL_MS = RUN1 6417.157; RUN2 5872.120
CLIP_SOURCE_ORDER_GBPS = RUN1 1.254; RUN2 1.370
CLIP_SOURCE_ORDER_DELTA_PERCENT = RUN1 -30.644%; RUN2 +9.355%

UNET_CURRENT_RANGE_WALL_MS = RUN1 11095.192; RUN2 9715.240
UNET_CURRENT_RANGE_GBPS = RUN1 1.109; RUN2 1.267
UNET_SOURCE_ORDER_WALL_MS = RUN1 12262.137; RUN2 7467.020
UNET_SOURCE_ORDER_GBPS = RUN1 1.004; RUN2 1.649
UNET_SOURCE_ORDER_DELTA_PERCENT = RUN1 +10.518%; RUN2 -23.141%

MMAP_RESULT = CLIP RUN1 7899.468 ms/1.018 GBps; CLIP RUN2 5758.703 ms/1.397 GBps; UNET RUN1 11924.798 ms/1.032 GBps; UNET RUN2 8839.045 ms/1.393 GBps
TMP_COPY_MS = RUN1 CLIP 2654.102 / UNET 3981.407; RUN2 CLIP 1709.403 / UNET 2312.613
TMP_REREAD_MS = RUN1 CLIP 7486.704 / UNET 11482.275; RUN2 CLIP 4966.368 / UNET 7545.748
TMP_COMBINED_MS = RUN1 CLIP 10140.806 / UNET 15463.682; RUN2 CLIP 6675.771 / UNET 9858.361

PAGEABLE_FILL_MS = mean 574.598 (RUN1 701.352; RUN2 447.845)
PINNED_FILL_MS = mean 569.900 (RUN1 703.063; RUN2 436.736)
PINNED_FILL_OVERHEAD_PERCENT = mean -0.818% (RUN1 +0.244%; RUN2 -2.481%)

PREWARM_1S_ESTIMATED_BYTES = RUN1 1090000000; RUN2 1526000000; mean 1308000000
PREWARM_2S_ESTIMATED_BYTES = RUN1 2180000000; RUN2 3052000000; mean 2616000000

STRUCTURAL_VALIDITY = VALID_PRIMARY_AND_DIGESTS_PER_REQUEST; CROSS_REQUEST_PLACEMENT_MISMATCH=YES

RESULT = INCONCLUSIVE
NEXT_STEP = HOLD_PRODUCTION_INTEGRATION; RETAIN_NATIVE_E11_AND_E12_OPT_IN; NO_E15_BACKEND

LOCAL_TESTS = E11 8 passed; E14 27 passed; E16 8 passed
PYCOMPILE = PASS
DIFF_CHECK = PASS

DIRECT_PYTHON_REMOTE_INVOKE_USED=NO
COMMIT=none
```
