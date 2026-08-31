# Batch E13: Modal Storage Topology and Volume v2 Audit

> **SUPERSESSION NOTICE (2026-08-30):** This is a historical storage audit;
> its observations remain historical truth. Do not use any generated-output
> durability wording here as current policy. Current output durability is off
> by default and strict is opt-in; see
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`. S4 source publication
> durability remains mandatory.

**Date:** 2026-08-16  
**Scope:** repository audit plus current official Modal documentation research  
**Constraints:** read-only audit; no loader changes, deploys, Modal resource creation, paid Modal runs, or commit

## Executive Determination

- Phase E checkpoint weights are read from the Modal Volume named `comfyui-models`, mounted at `/root/models`.
- The repository does not prove whether that existing Volume is v1 or v2. The code omits the optional `version` argument and contains no live Volume ID or backend-generation metadata.
- Modal Volume v2 is available as an experimental/Beta API, but its documented advantages are primarily file-count scale, concurrent writes, commits/reloads, and random-access writes. Modal publishes no v1-v2 single-large-file read benchmark.
- No storage migration is justified for the first cold sequential safetensors read based on current evidence. If a storage-only A/B is warranted, local ephemeral SSD staging at `/tmp` is the only documented candidate with a lower-latency read-path rationale, but its copy cost and lifecycle need to be measured.
- The provider/region observations do not establish a provider-specific Modal Volume storage mechanism. Official docs do not document a provider/region performance difference for Volumes.

## Evidence Boundary

Repository claims below come from static inspection and existing local reports. Official Modal claims come only from current `modal.com/docs` pages fetched for this audit. No Modal API call was made.

The worktree already contains unrelated concurrent changes from other E11-E15 lanes. This audit added only the report named in `FILES_CHANGED` below.

## 1. Current Storage Topology

### 1.1 Checkpoint Volume

| Logical role | Logical name | Creation/lookup API | Mount path | Usage | Generation | Checkpoints present? | Evidence |
|---|---|---|---|---|---|---|---|
| Model weights | `comfyui-models` | `modal.Volume.from_name(..., create_if_missing=True)` in both runtimes | `/root/models` | Read-only by intent during generation, but the mounted handle is not configured read-only; download/upload/delete paths write and call `commit()` | **UNKNOWN** | **YES** | `comfyapp.py:6537-6538,7828,8273-8274,8304-8308`; `comfymodal_runtime/modal_app.py:268,271,3516-3519,18249-18253`; `.model_manifest.json`; `V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md:33-35`; `FULL_RUN_LOGS.md:524-527,534` |

The V1 path and V2 path intentionally use the same default Volume name and mount path. V2 permits an environment override through `COMFYMODAL_MODELS_VOLUME` (`modal_app.py:268`). The model downloader writes to `/root/models/<folder>/<filename>.part`, atomically renames it, and calls `vol.commit()` (`comfyapp.py:8322-8364,8367-8423`).

The model directory is linked into ComfyUI without copying the weights: `ensure_models_symlink()` creates `ComfyUI/models -> /root/models` (`comfymodal_runtime/runtime_bootstrap.py:1107-1124`). The actual read remains the upstream ComfyUI `load_torch_file` path, including `safetensors.safe_open`; the native fast-disk work does not change the source storage layer.

### 1.2 Other mounted Volumes

| Logical role | Logical name | Creation/lookup API | Mount path | Usage | Generation | Checkpoints present? | Evidence |
|---|---|---|---|---|---|---|---|
| Custom-node source/dependencies | `comfyui-custom-nodes` | `modal.Volume.from_name(..., create_if_missing=True)` | V1 `/root/custom_nodes_vol`; V2 `/root/custom_nodes_vol` | Read/write synchronization and dependency files | UNKNOWN | NO | `comfyapp.py:6541,7829,8312`; `modal_app.py:269,272,3518-3519,18250-18252` |
| Runtime state/configuration | `comfymodal-runtime-config` | `modal.Volume.from_name(..., create_if_missing=True)` | V1 `/root/comfymodal_runtime_state`; V2 `/mnt/comfymodal_runtime_state` | Read/write restore plans, certificates, runtime state, and cache files; commits are used | UNKNOWN | NO | `comfyapp.py:6539-6540,8282-8287`; `modal_app.py:270,273,3519,18252`; `comfyapp.py:7932` |
| Prompt-encoding cache | `comfymodal-prompt-encoding-cache` | Conditional `modal.Volume.from_name(..., create_if_missing=True)` | `/root/prompt_cache_vol` | Read/write cache, only when the cache feature is enabled | UNKNOWN | NO | `comfyapp.py:6542-6548,8309-8310`; `modal_app.py:284-289,3528-3536,18263-18267` |
| V2 profile data | `comfymodal-v2-profiles` | Conditional `modal.Volume.from_name(..., create_if_missing=True)` | `/mnt/comfymodal_profiles` | Read/write full-trace/profile data | UNKNOWN | NO | `modal_app.py:282-283,3520-3526,18254-18262` |

No `CloudBucketMount`, `NetworkFileSystem`, or `ephemeral_disk` use was found in the repository. The current model volume is not an image filesystem and is not a cloud-bucket mount.

### 1.3 Image filesystem

The image definition installs CUDA, Python packages, ComfyUI, and source modules (`comfyapp.py:7862-7927,8260-8266`). It does not copy `.safetensors` files or the model directory into image layers. Existing weight evidence therefore points to `comfyui-models`, not the image filesystem.

### 1.4 Read path and measured payloads

- The production U-Net is `z_image_turbo_bf16.safetensors`, with a 12,309,817,472-byte payload and 453 tensors (`V2_BATCH_C10_EXTERNAL_LOADER_SURVEY.md:16`; `V2_BATCH_C12_SAFETENSORS_LAYOUT_SHARDING_REPORT.md:33-47`).
- The CLIP/text-encoder critical-path report measures approximately 8 GB of checkpoint bytes (`V2_BATCH_D12_CLIP_CRITICAL_PATH_FORENSICS.md:78-89,136-139`). The exact user-described `~8 GB` file is not uniquely mapped by the repository to one manifest entry.
- The existing reports identify the U-Net read as a mounted-Volume read. No report proves a Volume v1/v2 backend generation.

## 2. Volume Generation Determination

### 2.1 Result

```text
CURRENT_CHECKPOINT_STORAGE = Modal Volume "comfyui-models" mounted at "/root/models"
CURRENT_VOLUME_GENERATION = UNKNOWN
```

The following code uses the Volume API but does not identify the backend generation:

- V1: `modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)` (`comfyapp.py:8273-8274`).
- V2: `modal.Volume.from_name(runtime_spec.models_volume_name, create_if_missing=True)` (`comfymodal_runtime/modal_app.py:3516-3519`).
- Neither call supplies `version=1` or `version=2`.
- No Volume object ID or generation is persisted in the repository. The runtime model-generation field is not populated according to the existing storage audit (`V2_BATCH_C11_MODAL_STORAGE_AUDIT.md:75-89`).

Omitting `version` is not proof of v1. The current official SDK reference says `Volume.from_name(..., version=...)` is optional and, when supplied, must match an existing Volume. Therefore the source is insufficient to classify an already-named Volume.

### 2.2 Exact later read-only proof

Run this only in the correct Modal workspace/environment and only when a read-only API check is allowed:

```python
import modal

vol = modal.Volume.from_name(
    "comfyui-models",
    create_if_missing=False,
    version=1,
)
vol.hydrate()
```

Interpretation:

- Success proves the named Volume accepts the v1 version pin.
- A version-mismatch `InvalidError` stating that the existing Volume has v2 proves v2.
- `create_if_missing=False` is required so the probe cannot create a Volume.

`modal volume list` is useful for inventory, but the current CLI reference documents no backend-version field in its output. The SDK version-pin probe is the stronger generation check. The repository also contains a local helper with the same read-only probe instructions at `tools/inspect_modal_model_storage.py:108-122`; it was not run for this audit.

```text
VOLUME_V2_AVAILABLE = YES (current official API; experimental/Beta)
V2_MIGRATION_CANDIDATE = UNKNOWN (existing generation is unverified)
```

## 3. Current Official Volume v2 API

Sources used:

- [Volumes guide](https://modal.com/docs/guide/volumes), sections `Creating a Volume`, `Using a Volume on Modal`, `Volume commits and reloads`, `Volume performance`, `Volumes v2 overview`, and `Upgrading v1 Volumes`.
- [`modal.Volume` SDK reference](https://modal.com/docs/sdk/py/latest/Volume), sections `objects.create`, `from_name`, `with_mount_options`, `ephemeral`, `commit`, `reload`, and `copy_files`.
- [`modal volume` CLI reference](https://modal.com/docs/cli/latest/volume), sections `create`, `list`, `ls`, `cp`, `put`, and `rm`.

### 3.1 Creation and use

The current docs support these forms:

```bash
modal volume create --version=2 <new-volume-name>
```

```python
modal.Volume.objects.create("<new-volume-name>", version=2)
modal.Volume.from_name("<new-volume-name>", version=2)
modal.Volume.ephemeral(version=2)
```

The SDK reference labels the backend `version` parameter experimental. The Volume guide still labels v2 Beta. A v2 handle must be looked up with a matching version when the version is explicitly supplied.

### 3.2 v1/v2 coexistence

Official docs describe v1 and v2 as different per-Volume filesystem backends and expose the version on per-Volume creation/lookup. That supports independently named v1 and v2 Volumes in the API model. The docs do **not** make an explicit guarantee that one Function may mount both generations simultaneously, so same-Function mixed-generation mounting remains **not documented** rather than assumed.

### 3.3 Migration and copy semantics

The current Volumes guide states that there is no automated v1-to-v2 upgrade tool. The documented migration is:

1. Create a new v2 Volume.
2. Copy from the v1 Volume with `cp` for a one-shot copy or `rsync` for an incremental copy.
3. Persist v2 writes with `sync` when using a shell/Sandbox, or normal filesystem writes followed by `commit()` when mounted through the SDK.
4. Point a separately verified deployment at the new Volume.

The guide warns that deleting the old Volume and reusing its name is unsafe while Apps are deployed or running because Volume IDs are opaque and resolved at deployment/start time. A new shadow name avoids that risk. No such Volume was created or copied for E13.

### 3.4 Mount semantics and read-only use

`Volume.with_mount_options(read_only=True)` is a per-mount option, not a property of the Volume. `sub_path` is also per mount and is directory-only. The existing model mount does not call `with_mount_options(read_only=True)` because the same codebase has download and delete paths that write the model Volume.

For a future read-only benchmark deployment, a read-only mount could be tested without changing the loader, provided no downloader or model-mutating method is used in that deployment.

### 3.5 Commits, reloads, open files, and caching

Official docs state:

- Volume changes become durable/visible through `commit()`; background commits also occur periodically and on container shutdown.
- A container does not see a later external commit until `reload()`.
- `reload()` fails with a busy-volume error if files on the Volume are open.
- v2 additionally supports the `sync` command from a shell/Sandbox.
- Volumes have built-in caching and chunking optimizations, but the docs do not publish cache size, eviction, read-ahead, page-cache persistence, or safetensors-specific behavior.

The open-file rule is relevant to a process using lazy/mmap-backed safetensors, but Modal does not specifically document safetensors integration. It is not evidence that v2 improves the first read.

### 3.6 Throughput and random access

The current Volumes guide says Volumes are designed for up to 2.5 GB/s, with actual throughput not guaranteed. It does not split that figure by v1/v2.

Documented v2 differences are:

- No v1 500,000-inode limit, with a v2 per-directory limit of 262,144 files and unbounded directory depth.
- Concurrent writes from hundreds of containers to distinct files, compared with the v1 guidance of no more than five writers.
- Improved **random-access writes** because v1 could rewrite substantial portions of a file.
- Faster commits and reloads in the v2 overview.
- Filesystem tree traversal may be slower in v2 because the tree is demand-loaded.

There is no official v1-v2 number for single-file sequential reads, mmap reads, safetensors reads, IOPS, or range-read latency. The existing workload has approximately 19 model files and writes them once, so the documented v2 advantages do not directly target its first cold read.

### 3.7 Global/region/provider behavior

The Volumes guide says Volumes are distributed by default and backed by multiple underlying cloud providers. It says this allows use with Modal's global compute pool without managing replicas across regions.

The [region-selection guide](https://modal.com/docs/guide/region-selection) documents container placement and request routing, not a Volume replica/placement control or a provider-specific Volume throughput guarantee. It does not document data-residency guarantees or a region-specific Volume performance table.

This supports the conclusion that Volumes are intended to be globally available, but it does not support a claim that AWS versus GCP or one container region makes the Volume read faster.

### 3.8 Safetensors-specific limitations

The current official Modal docs contain no `safetensors`-specific section or benchmark. The applicable documented constraints are generic filesystem rules: open files can block Volume reload, and cache/readahead internals are not specified. Any claim about mmap page faults, range reads, or safetensors performance by Volume generation requires a controlled measurement.

## 4. `/tmp` and Local Ephemeral Disk

### 4.1 Current repository topology

The code uses `/tmp` for runtime-local artifacts, not model staging:

- `TRITON_CACHE_DIR=/tmp/triton_cache` (`comfyapp.py:7929-7935`).
- Full execution trace output uses `/tmp/comfymodal_full_trace` when enabled (`comfymodal_runtime/full_execution_trace.py:37`).
- Small probe files use `/tmp` (`comfymodal_runtime/unet_qd_probe.py:1172-1285`).
- No current production path copies either the CLIP or U-Net checkpoint to `/tmp`.
- No current deployment passes `ephemeral_disk=`.

The runtime state/Inductor cache is on the runtime-state Volume, not `/tmp` (`comfyapp.py:7932`).

### 4.2 Official disk facts

The current [Modal resources guide](https://modal.com/docs/guide/resources), section `Disk limits`, states that a running container has SSD disk subject to both:

1. The underlying worker's SSD capacity.
2. A default per-container disk quota of 512 GiB.

The same page documents `ephemeral_disk` up to 3.0 TiB. Modal's dataset-ingestion guidance describes `/tmp` as local SSD staging and says local SSD has lower I/O latency than a mounted Volume for that staging use.

The default quota is not a guarantee that every worker has 512 GiB of physically available SSD. The worker capacity, current free space, and exact runtime cache sizes are not recorded in this repository.

### 4.3 Capacity arithmetic

The requested staging payload is approximately:

```text
~8.0 GB CLIP + 12.3 GB U-Net = ~20.3 GB
```

That is only about 4% of the documented 512 GiB default quota. On quota arithmetic alone, both files can coexist. The overall feasibility remains unproven because:

- the underlying worker SSD capacity may bind before the quota;
- current `/tmp` free space and trace/cache growth have not been measured;
- the exact file represented by the `~8 GB` description is not uniquely identified locally;
- Modal does not document `/tmp` file persistence across a memory-snapshot restore;
- staging before a snapshot could change the snapshot working set and memory pressure.

Therefore:

```text
TMP_STAGING_FEASIBLE = UNKNOWN
```

This means “capacity arithmetic is conditionally favorable,” not “staging is known to fit on every scheduled worker.”

### 4.4 Lifecycle and snapshot implications

The [Modal Memory Snapshots guide](https://modal.com/docs/guide/memory-snapshots) documents CPU snapshots as saving container state and restoring it into a new container state. It also states that Volume changes do not update snapshots and that deleting Volume files used by restore can cause restore failures. For GPU snapshots, Modal explicitly says snapshots do not speed up model loading from storage and can add overhead.

The repository enables CPU memory snapshots (`comfyapp.py:24291`; V2 wiring at `modal_app.py:18279`) and uses scale-to-zero/single-use behavior. No repository code relies on `/tmp` surviving a restore, and the official docs do not specify that it does. A staging design must treat `/tmp` as container-lifetime ephemeral storage unless a later controlled experiment proves otherwise.

## 5. Provider Sensitivity

### 5.1 Existing observations

The requested observations are:

```text
bucket-first AWS/us-east-1:  MODEL_READINESS_GATE ~19.782 s
corrected bucket-first GCP/us-east1: ~10.163 s, ~9.948 s
```

Existing repository evidence also shows provider/region variation in other paths:

- D12 reports approximately 5.10 GB/s on GCP versus 4.05 GB/s on AWS for a CLIP file-to-GPU segment (`V2_BATCH_D12_CLIP_CRITICAL_PATH_FORENSICS.md:78-89,107-118`).
- The provider/page-path report finds a real U-Net H2D tail on both AWS and GCP and does not establish that provider selection fixes it (`V2_PROVIDER_AND_PAGE_PATH_FINAL_REPORT.md:5-17,42-57`).
- The V2 code supports diagnostic `region=` and `cloud=` pins, but those are compute-placement controls (`comfymodal_runtime/modal_app.py:18268-18291`).

These are observations, not a causal storage explanation. In particular, “bucket-first” does not establish that the current checkpoint Volume itself is an AWS or GCP bucket mount; the repository has no `CloudBucketMount` use.

### 5.2 Official documentation result

The official Volumes guide documents distributed storage and multiple underlying cloud providers, but does not publish provider-specific or region-specific Volume read throughput/latency. The region-selection guide documents where containers and routed inputs run, not a storage placement/performance mapping.

The [Cloud bucket mounts guide](https://modal.com/docs/guide/cloud-bucket-mounts) does document S3 bucket-region detection and warns that an AWS worker in another region can affect automatic detection. That is relevant to `CloudBucketMount`, not proof of a Modal Volume provider effect. CloudBucketMount is also documented as optimized for large sequential reads and having filesystem-operation limitations.

```text
PROVIDER_STORAGE_DIFFERENCE_DOCUMENTED = NO
PROVIDER_STORAGE_DIFFERENCE = UNKNOWN
```

No explanation such as “GCP is closer to the Volume replica” is supported by current authoritative public documentation.

## 6. Storage/API Knob Audit

| Knob | Current status | Relevance to first cold sequential read |
|---|---|---|
| Volume v2 | Available, experimental/Beta; current generation unknown | No documented v1-v2 single-file read gain; migration is manual and adds risk |
| `read_only=True` Volume mount | Supported per mount, not used for current model mount | Safety/consistency option; no documented throughput gain |
| `commit()` / background commits | Used by model download/write paths | Write durability only; not a first-read accelerator |
| `reload()` | Used in runtime Volume workflows | Required for later external commits; open safetensors files can make reload busy |
| v2 `sync` | Supported only for v2 shell/Sandbox writes | Persistence tool, not a first-read accelerator |
| Volume cache/chunking | Documented generally; sizing and eviction undocumented | Cannot be tuned from documented public knobs |
| Local `/tmp` / `ephemeral_disk` | `/tmp` is used locally; no `ephemeral_disk` request exists | Only documented lower-latency disk candidate; must pay copy-in cost and verify capacity |
| Image inclusion | Supported, but Modal says weight-read performance is similar to Volumes | No documented cold-read gain; couples weights to image rebuilds |
| `CloudBucketMount` | No repository use | Poor fit to mmap/range-style access; docs emphasize sequential reads and limitations |
| `region=` / `cloud=` | Diagnostic controls exist in V2 | Changes compute placement, not a documented Volume backend/replica selection |
| CPU/GPU memory snapshots | CPU enabled; GPU snapshot disabled by default | Useful for non-storage initialization, not documented as a storage-read cache |

## 7. Conclusion Before Custom Loader Investment

The current cold checkpoint path is a mounted Modal Volume read. Volume v2 should not be treated as a proven read-throughput upgrade: the official docs provide no version-specific single-file read numbers, and the documented v2 changes mostly address write behavior, concurrency, file scale, and commit/reload behavior.

The most relevant storage-only change is therefore:

```text
MOST_RELEVANT_MODAL_STORAGE_CHANGE = No immediate migration; if an A/B is funded, test boot-time copy of the exact checkpoint to local ephemeral SSD (/tmp) with the loader and runtime unchanged.
```

That A/B must account for the copy being sourced from the current Volume. A 12.3 GB copy has a nonzero startup cost that can erase any local-SSD read benefit for a one-shot container. It should also be run without relying on undocumented `/tmp` snapshot persistence. This is a future experiment design only; it was not implemented or run by E13.

CloudBucketMount is not recommended for this path: current Modal docs characterize it as optimized for large sequential reads and document unsupported file operations, while the current safetensors path uses lazy/mmap-style access. Image-baking is not recommended as a read optimization because Modal documents similar performance to Volumes.

## 8. Conditional v1-to-v2 Shadow Plan

The current generation is **not confirmed v1**, so no migration is authorized by this audit and no v1-only conclusion is asserted.

If, and only if, the read-only version-pin probe proves `comfyui-models` is v1, the future shadow experiment should be:

1. Keep `comfyui-models` unchanged as the control.
2. Create a new, separately named v2 Volume, for example `comfyui-models-v2-shadow`, with `modal volume create --version=2`. Do not delete or rename the control.
3. Copy the complete model tree from the v1 control to the v2 Volume with the documented `cp -rp` or `rsync -a` procedure, then `sync`/`commit` as appropriate.
4. Verify every model hash and the manifest before any benchmark. Include the 8 GB-class CLIP file and the 12.3 GB U-Net.
5. Point a shadow V2 deployment at the new Volume by setting the existing `COMFYMODAL_MODELS_VOLUME` configuration (`modal_app.py:268`) and make the lookup explicit with `version=2` in the shadow storage configuration. Keep mount path `/root/models`, image, runtime shape, snapshot policy, region/cloud, and loader unchanged.
6. Run source-only file/read measurements first, then the same cold benchmark protocol on both arms. Do not compare a different loader, image, model hash, or snapshot state.
7. Stop if v2 does not improve the measured source-read metric; do not infer a benefit from general v2 throughput claims.

This plan is deliberately conditional. No new Volume, copy, deployment, or benchmark was performed.

## 9. Remote Proof Still Required

```text
REMOTE_PROOF_STILL_REQUIRED =
1. Read-only SDK version-pin probe for comfyui-models to classify v1 vs v2.
2. Read-only live listing/hash confirmation for the exact CLIP and U-Net files on the current Volume.
3. In a permitted future container, measure actual /tmp free space, worker SSD capacity, and copy-in time.
4. If staging is pursued, empirically test the cold-container and snapshot-restore lifecycle without changing the loader.
5. Only after those gates, run a controlled current-Volume vs local-SSD or v1-v2 source-only A/B.
```

## Final Fields

```text
E13_COMPLETE

CURRENT_CHECKPOINT_STORAGE = Modal Volume "comfyui-models" mounted at "/root/models"
CURRENT_VOLUME_GENERATION = UNKNOWN

VOLUME_V2_AVAILABLE = YES (official experimental/Beta API)
V2_MIGRATION_CANDIDATE = UNKNOWN (generation must be proven first)

TMP_STAGING_FEASIBLE = UNKNOWN (quota arithmetic is favorable; worker/free-space and snapshot facts are unproven)

PROVIDER_STORAGE_DIFFERENCE_DOCUMENTED = NO
PROVIDER_STORAGE_DIFFERENCE = UNKNOWN

MOST_RELEVANT_MODAL_STORAGE_CHANGE = No immediate change; if measured, local ephemeral-SSD /tmp staging A/B is the relevant storage-only candidate, not an unproven v2 migration.
REMOTE_PROOF_STILL_REQUIRED = Read-only Volume generation/file proof, actual worker /tmp capacity/lifecycle proof, then a controlled source-only A/B if still justified.

FILES_CHANGED = V2_BATCH_E13_MODAL_STORAGE_AUDIT.md
MODAL_RESOURCES_CREATED=0
MODAL_RUNS=0
COMMIT=none
```
