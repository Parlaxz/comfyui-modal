# Allocator Headroom and OOM Fail-Closed Rule

Status: resolved (read-only research audit)

## Scope and current evidence

`comfymodal_runtime/golden_serial.py` currently samples `memory_allocated()`, `memory_reserved()`, and `max_memory_allocated()` at named UNET checkpoints (lines 12459-12490). It resets peak stats before skeleton construction, source H2D transport, and assign/adoption (12498, 12513, 12543), then compares peaks against the QD GPU byte count (12531-12539, 12556-12563). Those peaks are allocator-wide for the selected CUDA device, not UNET-owned: any concurrent CLIP allocation or unrelated stream/work can enter the interval. Therefore the result must be described as combined-device peak evidence, never as a UNET-only delta while CLIP is active.

The existing restore probe is the correct shape for passive state sampling: allocated/reserved/max allocated/max reserved plus `mem_get_info()` free/total, without freeing or purging (comfymodal_runtime/restore_state_probe.py:323-358).

## Admission threshold shape

Admission should be fail-closed and based on *post-operation combined peak headroom*, not merely current `memory_allocated`. Sample `(free, total) = torch.cuda.mem_get_info(device)` and current allocator state immediately before the overlap window; require the conservative inequality:

`free_bytes >= required_peak_bytes + safety_margin_bytes`

where `required_peak_bytes` is the measured or contract-bounded incremental requirement for the complete concurrent operation (CLIP + UNET overlap), and `safety_margin_bytes` is explicit, fixed/configured headroom. A ratio-only rule is insufficient: `mem_get_info` is global device free memory, while allocator reserved memory may include reusable cached blocks. Record free/total, allocated/reserved, and both peak allocated/reserved at every boundary. If any required sample/API is unavailable, stale, contradictory, or the estimate is absent, reject admission.

## Combined peak sampling and contamination

For each overlap attempt, establish a single observation interval and record both `max_memory_allocated()` and `max_memory_reserved()` after the interval, plus current allocated/reserved and `mem_get_info`. The peak must cover all participating work; do not reset between CLIP and UNET portions. `reset_peak_memory_stats()` defines the starting point for allocator peak counters and is global to the device, so resetting during a live CLIP forward destroys attribution and can make a later UNET checkpoint look isolated. The current resets are safe only for isolated pre-overlap UNET load phases; they are forbidden once CLIP is active or overlap attribution is being measured.

Concurrency also means allocator counters cannot attribute bytes to a model, thread, or stream. CUDA work is asynchronous; a boundary must use the project’s established completion/quiescence boundary before claiming the interval ended, while the telemetry itself must not be promoted to ownership attribution. If combined peak exceeds the budget, classify the whole overlap attempt degraded/failed; do not subtract CLIP or claim a UNET-only peak.

## Forbidden purges/resets

No `torch.cuda.empty_cache()` (or model-management soft-empty-cache), allocator purge, broad GC, model unload, or model-sized transfer may be inserted to make admission pass or to alter the measurement. PyTorch documents that `empty_cache()` releases only unused cached blocks; it does not free tensor-occupied memory and therefore cannot increase memory available to PyTorch for live tensors. It would also change allocator state and invalidate comparable evidence. During the active overlap interval, no `reset_peak_memory_stats()` is allowed. Existing single-use tail/teardown explicitly prohibit these operations (`golden_serial.py:13248-13254, 14230-14234`).

## Explicit fail-closed OOM/degraded rule

Catch `torch.cuda.OutOfMemoryError` (the documented CUDA-specific exception) and classify the attempt as `oom`, recording the phase, combined telemetry, and exception text; do not retry with purge, reset, or scheduling changes. A CUDA allocation failure that is not represented by that class but is clearly an OOM by stable exception text/runtime classification must also be classified `oom`; unknown CUDA/memory telemetry failures are `degraded` and fail closed. Any of these states means: no overlap admission, no success claim, preserve diagnostics, and terminate the request through the existing failure path.

Admission must also fail closed when free memory is below the combined requirement plus margin, when `free`/`total` sampling fails, when peak APIs are unavailable, when `peak_reserved` or `peak_allocated` violates the budget, or when a concurrent CLIP interval makes ownership attribution ambiguous. “OOM” is an observed allocation failure; “degraded” is insufficient/ambiguous evidence or non-OOM allocator telemetry failure. Neither is success.

## Authoritative references

- PyTorch CUDA memory management: https://docs.pytorch.org/docs/stable/notes/cuda.html — caching allocator semantics; `memory_allocated`/`max_memory_allocated` measure tensor occupancy; `memory_reserved`/`max_memory_reserved` measure total allocator-managed memory; `empty_cache` releases unused cached memory only; `memory_snapshot` is available for allocator patterns.
- PyTorch CUDA API source/docs: https://github.com/pytorch/pytorch/blob/main/torch/cuda/memory.py — `reset_peak_memory_stats()` resets device allocator peak counters; `max_memory_allocated()` reports peak allocated bytes since program start or reset; `mem_get_info()` returns global `(free, total)` bytes from `cudaMemGetInfo`.
- PyTorch CUDA binding: https://github.com/pytorch/pytorch/blob/main/torch/cuda/__init__.py — `torch.cuda.OutOfMemoryError = torch._C.OutOfMemoryError`.
- Repository evidence: `comfymodal_runtime/golden_serial.py:12459-12563, 13244-13254, 14220-14234`; `comfymodal_runtime/restore_state_probe.py:323-358`.

These sources support allocator/device-level evidence and OOM class handling; they do not provide per-model or per-stream attribution. That limitation is the reason for the combined-peak and fail-closed rule above.
