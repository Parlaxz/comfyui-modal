# V2 Batch E7 - PyTorch CUDA Allocator Policy Audit

Date: 2026-08-16
Scope: installed Torch/runtime inspection plus D18 evidence mapping.
Mode: read-only. No runtime edits, no Modal deploys, no Modal requests.

## Required Output

```text
CURRENT_BACKEND=native
LOW_RISK_CANDIDATES=NONE_CONFIRMED; max_non_split_rounding_mb is the only bounded remote A/B candidate
DOES_ANY_OPTION_REMOVE_EXPLICIT_EMPTY_CACHE_COST=NO
REMOTE_AB_WORTHY=YES, max_non_split_rounding_mb only, measure-first
RECOMMENDED_FLAGS=NONE
RISKS=see option decisions below; no setting is justified for production from current evidence
```

## Installed Runtime

The inspected process was the local Python/Torch environment, not the remote
D18 container:

```text
PYTHON=C:\Program Files\Python311\python.exe
TORCH_VERSION=2.8.0+cu128
TORCH_SOURCE=C:\Users\parla\AppData\Roaming\Python\Python311\site-packages\torch\__init__.py
TORCH_CUDA_BUILD=12.8
CUDA_AVAILABLE=True
CUDA_DEVICE_COUNT=1
CUDA_DEVICE=NVIDIA GeForce RTX 3070
CUDA_DEVICE_CAPABILITY=8.6
CUDA_DEVICE_TOTAL_BYTES=8589410304
CUDA_VISIBLE_DEVICES=UNSET
PYTORCH_ALLOC_CONF=UNSET
PYTORCH_CUDA_ALLOC_CONF=UNSET
CURRENT_BACKEND=native
```

The local inspection process reported approximately 7.46 GB free of 8.59 GB
from `cudaMemGetInfo`. This is process-time local host state and must not be
treated as the D18 remote GPU state.

The installed `torch/cuda/memory.py:1076-1085` exposes the active backend. The
installed `torch/include/c10/cuda/CUDAAllocatorConfig.h` reads
`PYTORCH_CUDA_ALLOC_CONF` at lines 96-108. Its parser declarations do not show
`pinned_reserve_segment_size_mb`; the installed `c10_cuda.dll` import surface
also has no matching option name.

Read-only allocator getter results from the installed `c10_cuda.dll` were:

```text
garbage_collection_threshold=0.0
expandable_segments=False
max_non_split_rounding_mb=20
max_non_split_rounding_bytes=20971520
pinned_use_cuda_host_register=False
pinned_num_register_threads=1
pinned_use_background_threads=False
pinned_reserve_segment_size_mb=UNSUPPORTED
```

`expandable_segments` and the existing pinned settings are reported for
inventory only. They are not evaluated as candidates here, per the requested
scope.

## Actual Cleanup Path And D18 Evidence

The installed ComfyUI source has the following behavior:

- `comfy/model_management.py:799-841` calls `soft_empty_cache()` after model
  unloading, and can also call it when the native allocator's inactive portion
  exceeds the ComfyUI predicate at lines 836-840.
- `comfy/model_management.py:1647-1691` defines that inactive native portion
  as `reserved - active` and returns it as `mem_free_torch`.
- `comfy/model_management.py:1944-1960` executes the CUDA cleanup in this
  fixed order: `torch.cuda.synchronize()`, `torch.cuda.empty_cache()`, then
  `torch.cuda.ipc_collect()`.

D18 remote decomposition identified the target as:

```text
native VAE load_models_gpu -> model_management.soft_empty_cache
model_class=AutoencodingEngine
models_unloaded=0
allocated_before=20427641856
reserved_before=22594715648
free_memory_before=80845794304
allocated_after=20427641856
reserved_after=20449329152
VAE transfer=167639366 bytes
adjacent VAE free_memory requirement=1462827161.8 bytes
decode demand=9099509760 bytes
```

The three D18 target events measured `empty_cache` at 950.460 ms, 739.241 ms,
and 934.173 ms. It accounted for 99.87-99.91% of each target
`soft_empty_cache` interval. Synchronize was 0.028-0.044 ms and IPC collection
was 0.010-0.014 ms. The approximately 2.17 GB difference between the target
reserved and allocated values shows inactive native cache, but D18 did not
capture a request-size/block histogram or an allocator-internal GC event.

Therefore the expensive observed operation is an explicit full cache cleanup
inside ComfyUI's VAE path, not a proven allocator-internal garbage-collection
stall. Physical headroom and zero model unloads do not make that explicit call
redundant.

## Option Decisions

### native `garbage_collection_threshold`

Current value: `0.0`, disabled.

This is native allocator-internal, allocation-triggered reclamation. It can
change when inactive blocks are reclaimed during later allocation pressure,
but it does not change the ComfyUI `soft_empty_cache()` call. The explicit
`synchronize`, `empty_cache`, and `ipc_collect` sequence remains.

D18 has no allocation retry, OOM, or allocator-internal GC evidence. Its long
interval was the explicit `empty_cache` operation while the VAE was activated,
with no observed model unload. Enabling a threshold could add incremental
reclamation and allocator latency earlier without addressing the measured
explicit call. No production flag and no remote A/B arm are justified.

### native `max_non_split_rounding_mb`

Current value: `20` MB.

This is the only bounded A/B candidate. It may affect whether cached larger
blocks are reused instead of split for a near-sized request, which could
change future fragmentation and allocation stalls. D18 does show about 2.17 GB
of inactive native cache and a repeated large-model lifecycle, so a
measure-first remote A/B is technically relevant.

The evidence does not show the block-size distribution, near-size reuse
misses, allocation retries, or a value that should be selected. A larger value
could also retain more reserved memory and reduce available headroom. It does
not remove the explicit `empty_cache` call; at most it may indirectly change
the cached block inventory that the call processes. No production value is
recommended.

### `cudaMallocAsync` backend

Current backend: `native`.

This is a process-wide allocator backend switch, not a narrow VAE policy. It
would change allocator accounting and behavior for the entire ComfyUI process;
native allocator settings such as `garbage_collection_threshold` and
`max_non_split_rounding_mb` would no longer be the applicable controls. The
installed D18 evidence contains no async-backend comparison.

It does not remove ComfyUI's explicit cleanup call or its preceding device-wide
synchronize and following IPC collection. The backend may change the work
performed inside `empty_cache`, but that effect is unmeasured here. It is not a
low-risk candidate and is not remote-A/B-worthy for this audit.

### `pinned_reserve_segment_size_mb`

Unsupported by installed Torch `2.8.0+cu128`. The installed allocator header
exposes pinned host-register, register-thread, and background-thread settings,
but no reserve-segment setting or parser. No flag is valid to recommend.

Even if a later Torch supported this option, it would concern pinned host
allocation behavior, not the device-side native cache cleared by D18. It would
not remove the explicit `torch.cuda.empty_cache()` call or its surrounding
ComfyUI synchronization/IPC calls.

## A/B Boundary

`REMOTE_AB_WORTHY` is limited to one isolated
`max_non_split_rounding_mb` arm, after an explicit approval. It is not a
recommendation to deploy a value. The arm would need a fresh process and
matching D18 workload, with output identity, VAE lifecycle, allocated/reserved
bytes, inactive bytes, allocation retries/OOMs, `empty_cache` wall, and total
`soft_empty_cache` wall compared against the native 20 MB baseline. No Modal
activity was performed for this audit.

## Final Risk Register

- `garbage_collection_threshold`: earlier allocator reclamation can add
  latency and has no evidence of reducing the measured explicit cleanup.
- `max_non_split_rounding_mb`: can increase reserved memory or worsen
  availability if the request-size pattern does not benefit; no value is
  evidence-backed yet.
- `cudaMallocAsync`: global backend change with different allocator
  accounting/statistics and unmeasured ComfyUI cleanup behavior.
- `pinned_reserve_segment_size_mb`: unavailable in the installed Torch.
- All options: none removes the explicit ComfyUI `empty_cache` cost proven by
  D18; changing allocator policy cannot be treated as removing that call.

```text
STOP.
```
