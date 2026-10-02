# V2 Batch E5 - High-Headroom Empty-Cache Bypass Audit

Date: 2026-08-16
Scope: source audit plus local fail-closed implementation. No Modal activity or commit.

Pinned local versions:

- ComfyUI: `v0.24.0`, source commit `f49bdb655707b97952dcef40e12e5af1f08d2007`.
- PyTorch: `2.8.0+cu128`, build commit `a1cb3cc05d46d198467bebbb6e8fba50a325d4e7`.
- CUDA runtime reported by PyTorch: `12.8`.

## Verdict

The allocator evidence justifies skipping the `torch.cuda.empty_cache()` operation
only for the source-proven defensive, no-unload `free_memory()` branch. It does
not justify suppressing the whole `soft_empty_cache()` bundle, because that
bundle also provides the explicit CUDA completion barrier and IPC collection.

The D18 telemetry reports `models_unloaded_count=0`, but that fact alone does not
identify the branch. `load_models_gpu()` first calls `cleanup_models_gc()`, which
always calls `reset_cast_buffers()`; `reset_cast_buffers()` unconditionally calls
`soft_empty_cache()` with reason `other`. The same cleanup function can also call
it a second time for a dead `LoadedModel`. The D18 target's observed
`load_models_gpu required_memory=0` is consistent with this pre-load cleanup path,
but the historical telemetry did not record the reason, so that old event cannot
be classified retroactively.

```text
EMPTY_CACHE_SKIP_LOCALLY_JUSTIFIED=YES, narrowly for the defensive no-unload free_memory branch; historical D18 attribution remains UNKNOWN
EXACT_CALL_TRIGGER=free_memory(): after no model unload, device is non-None, vram_state is not HIGH_VRAM, and mem_free_torch > mem_free_total * 0.25; additionally, load_models_gpu() -> cleanup_models_gc() -> reset_cast_buffers() calls soft_empty_cache() with reason other, and dead LoadedModel cleanup calls it with reason cleanup_models_gc_dead_model
ALLOCATOR_BACKEND=native
OOM_RECOVERY_CONTRACT=native CUDACachingAllocator first searches cached blocks, then on failed cudaMalloc releases available cached blocks and retries, then releases all releasable non-split cached blocks and retries; if still unsuccessful it raises CUDA OOM
SAFE_PREDICATE=authoritative defensive_no_unload_free_memory_branch AND models_unloaded_count == 0 AND immediate physical free bytes >= 2 * max(operation_required_bytes, minimum_memory_required) AND allocator backend == native/default native allocator AND no active CUDA graph capture, graph-private pool, custom allocator, or custom MemPool routing AND retain an explicit completion barrier and IPC collection
FAIL_CLOSED_PATH=if a later allocation cannot be satisfied, native allocator reclamation/retry runs; success continues normally, otherwise the allocator raises OOM. If any predicate input is missing, stale, non-native, captured, custom-pooled, or indicates dead-model cleanup, call the existing full soft_empty_cache path instead
EXPECTED_SAVING_MS=739-950 only for a confirmed qualifying D18-shaped empty_cache operation; D18 does not prove that every observed long call was the defensive free_memory branch
NEXT_IMPLEMENTATION_SHAPE=implemented in the pinned free_memory branch with default-off COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS; split CUDA soft cleanup so synchronize() and ipc_collect() remain, while empty_cache() is skipped only when the predicate is true; never bypass after unload, reset_cast_buffers, or cleanup_models_gc dead-model cleanup
```

## ComfyUI Call Conditions

The relevant source is `comfy/model_management.py`:

- `free_memory()` calls `cleanup_models_gc()` first (`:799-801`).
- After the unload scan, an actual unload calls `soft_empty_cache()`
  (`:834-835`).
- With zero unloads, the defensive fallback calls it only when
  `device is not None`, `vram_state != VRAMState.HIGH_VRAM`, and
  `get_free_memory(device, torch_free_too=True)` reports
  `mem_free_torch > mem_free_total * 0.25` (`:836-841`). Here
  `mem_free_torch` is allocator-reserved minus allocator-active memory, while
  `mem_free_total` includes CUDA-reported free memory.
- `load_models_gpu()` invokes `cleanup_models_gc()` before model preparation
  (`:843-844`) and can invoke `free_memory()` twice (`:903-915`).
- `cleanup_models_gc()` calls `reset_cast_buffers()` before scanning for dead
  models (`:972-976`). `reset_cast_buffers()` always calls `soft_empty_cache()`;
  this is classified as `other` and is never eligible. If a dead model is found,
  it additionally runs `gc.collect()` followed by a
  `cleanup_models_gc_dead_model` cache call (`:984-991`). Neither path is the
  defensive no-unload cache policy, and neither may be bypassed by an
  unload-count predicate.

`soft_empty_cache()` is a bundle, not an empty-cache-only operation. On CUDA it
executes, in order, `torch.cuda.synchronize()`,
`torch.cuda.empty_cache()`, and `torch.cuda.ipc_collect()`
(`:2065-2100` after the E5 helper split). The proposed saving therefore requires an operation-aware split,
not suppression of the complete helper.

## D18 Headroom

The saved D18 evidence reports:

```text
allocated_before = 20,427,641,856 bytes
reserved_before = 22,594,715,648 bytes
free physical ~= 80,845,794,304 bytes
VAE free_memory requirement = 1,462,827,161.8 bytes
models unloaded = 0
single_use = true
```

The observed physical-free amount is about `55.3x` the adjacent VAE
requirement. That is strong evidence for this particular high-headroom case,
but a generic guard must sample current memory immediately before the decision;
the old `load_models_gpu(memory_required=0)` value must not be interpreted as a
zero allocation requirement.

## PyTorch Contract

The installed `torch/cuda/memory.py` source documents that `empty_cache()` only
releases unoccupied cached allocator memory and does not increase memory
available to PyTorch (`:212-224`). The same source documents
`num_alloc_retries` as failed `cudaMalloc` calls that cause a cache flush and
retry (`:272-275`). `get_allocator_backend()` reports `native` for this
installation (`:1076-1085`).

The pinned PyTorch v2.8.0 native source (`c10/cuda/CUDACachingAllocator.cpp`,
`DeviceCachingAllocator::malloc`) implements the recovery sequence explicitly:

1. Search the stream's cached blocks.
2. Try a new allocation with `cudaMalloc`.
3. If that fails, release enough available cached blocks and retry.
4. If that fails, release all releasable non-split cached blocks and retry.
5. Raise CUDA OOM if the retry still fails.

This is a fail-closed allocation contract. It does not mean `empty_cache()` is
always free or unnecessary; it means a preemptive cache flush is not required
for correctness when the later allocation is a normal native-allocator
allocation. The allocator still has to be allowed to reclaim cache when needed.

The native source also reserves CUDA graph allocations in graph-private pools
because replay depends on stable virtual addresses. Allocation retry behavior
has capture-specific guards, so active graph capture, graph-private pools,
`torch.cuda.MemPool` routing, and custom/pluggable allocators are outside this
local proof. The generic guard must fail closed for all of them.

## HIGH_VRAM Comparison

Pinned ComfyUI already avoids the defensive no-unload branch in HIGH_VRAM at
`model_management.py:836-840`. That is not a suitable global recommendation:
HIGH_VRAM also changes model residency and device placement, including UNET
offload/initial-load behavior (`:1009-1022`) and text-encoder placement
(`:1116-1129`). The E5 shape should preserve the current VRAM policy and gate
only the narrow defensive cache operation.

## Single-Use Meaning

`single_use=true` is not part of the PyTorch correctness contract and is not
read by pinned ComfyUI memory management. It is policy: a single-use container
has no later request that can benefit from retained cached blocks, and its
post-request residency is irrelevant after teardown. The bypass remains
allocator-safe without single-use, but persistent processes may retain cache
and should use the same headroom guard rather than relying on single-use.

## E5 Implementation

The implementation is in `comfymodal_runtime/empty_cache_bypass.py` and the
pinned `comfy/model_management.py` source:

- `free_memory()` passes authoritative reasons, unload count, operation
  requirement, and effective minimum requirement into `soft_empty_cache()`.
- The CUDA path samples physical free bytes immediately before deciding.
- The default-off flag is `COMFYMODAL_V2_HIGH_HEADROOM_EMPTY_CACHE_BYPASS`.
- The eligible path executes `synchronize()`, skips only `empty_cache()`, then
  executes `ipc_collect()`.
- All unknown, non-native, captured, custom-allocator, custom-pool,
  post-unload, reset-buffer, dead-model, OOM-retry, and insufficient-headroom
  cases execute the native full sequence.
- `empty_cache_bypass_decision` emits the requested decision metadata when the
  feature is enabled and an active runtime trace is available.

The next D18 run will identify the long call through `soft_cache_reason`, with
`other` identifying the unconditional reset-buffer path and
`free_memory_defensive_no_unload` identifying the only bypass-eligible path.

## Next-Run Evidence

The next D18 run should retain these source-path fields:

- `free_memory` defensive no-unload branch versus `free_memory` after unload.
- `cleanup_models_gc` dead-model cleanup.
- active capture/custom MemPool/default native allocator state.
- immediate physical-free bytes and the exact effective minimum requirement.

The operation-only A/B should verify that the qualifying path has zero
`empty_cache()` calls, retains synchronization and IPC collection, preserves
normal VAE output, and falls back to the native retry/OOM path under pressure.

Local verification:

- `tests/test_v2_batch_e5_empty_cache_bypass.py`: **15 passed, 10 subtests**.
- `tests/test_v2_clip_cold_forensics.py`: **27 passed**.
- E5 helper, parent ComfyUI source, and E5 tests: **py_compile passed**.
- Modal deploys: **0**.
- Modal requests: **0**.
- Commit: **none**.

STOP.
