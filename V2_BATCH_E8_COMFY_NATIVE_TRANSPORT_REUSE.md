# Batch E8 ComfyUI Native Async/Pinned Transport Reuse Audit

Scope: first-cold model transport only, CPU-resident model state to GPU. Low-VRAM inference, dynamic inference policy, and Modal execution are out of scope.

Audit basis:

- Local ComfyUI commit: `f49bdb655707b97952dcef40e12e5af1f08d2007`.
- Native AIMDO Python package inspected: `comfy_aimdo 0.4.8`, commit `g7bbb4d4ac`.
- Native source inspected: `comfy/ops.py`, `comfy/model_management.py`, `comfy/memory_management.py`, `comfy/pinned_memory.py`, `comfy/model_prefetch.py`, `comfy/model_patcher.py`, `comfy/sd.py`, `comfy/utils.py`, `comfy/cli_args.py`, and the installed `comfy_aimdo` host/VRAM buffer bindings.

Verdict meanings below apply to Phase-E integration. `REUSE` means call the native seam. `ADAPT` means reuse the native primitive but retain a thin Phase-E source/lifetime adapter. `DO_NOT_USE` means it is not part of first-cold transport.

## REUSABLE_COMPONENTS=

| Phase-E need | Verdict | Native seam | Finding |
|---|---|---|---|
| Pinned host pool | **ADAPT** | `comfy/pinned_memory.py:66-105`; `comfy/model_patcher.py:1799-1804`; `comfy_aimdo/host_buffer.py:78-130` | A growable pooled `HostBuffer`, subviews, registration, truncation, pin stealing, and storage ownership already exist. The pool is coupled to `ModelPatcherDynamic` pin state, so a plain snapshot-resident `ModelPatcher` needs a small adapter or the generic tensor pin API. Do not create a second pool. |
| Pinned budget enforcement | **REUSE** | `comfy/model_management.py:643-675`, `:1482-1497`; `comfy/pinned_memory.py:87-90` | Reuse `ensure_pin_budget`, `ensure_pin_registerable`, `MAX_PINNED_MEMORY`, and `TOTAL_PINNED_MEMORY`. Do not add a Phase-E byte counter or pressure policy. |
| Asynchronous H2D | **ADAPT** | `comfy/model_management.py:1424-1475`; `comfy/ops.py:166-208` | Native `cast_to`, `cast_to_gathered`, and `copy_(non_blocking=True, stream=...)` provide the copy primitive. A source adapter is still needed to present Phase-E tensors/geometries and retain CPU references. Calling `load_models_gpu` alone is not sufficient: the regular full-load path still reaches `model.to(device)` at `comfy/model_patcher.py:1028-1029`. |
| Copy stream | **REUSE** | `comfy/model_management.py:1273-1422`; CLI `--async-offload` / `--disable-async-offload` at `comfy/cli_args.py:148-149` | Reuse `get_offload_stream`, `sync_stream`, `current_stream`, and the native stream rotation. Do not allocate a Phase-E stream pool. |
| Event/lifetime tracking | **ADAPT** | `comfy/ops.py:385-404`; `comfy/model_management.py:1346-1355`; `comfy/model_prefetch.py:34-66` | Native ordering is mostly stream-based: consumer streams wait on the copy stream, and cast buffers are synchronized before reset. It does not expose a generic event token for an arbitrary Phase-E staging slot. If Phase E reuses slots or an external source, keep a minimal per-slot fence and owner reference until the native stream is safe. |
| Contiguous buffer allocation | **ADAPT** | `comfy/memory_management.py:124-171`; `comfy/model_management.py:1307-1344`; `comfy_aimdo/vram_buffer.py:27-60` | Native aligned byte geometry, packed views, per-stream cast buffers, and AIMDO VRAM buffers exist. They are GPU/cast buffers, not a generic full-model CPU staging-ring API. Reuse the geometry/view helpers; add no allocator beyond the smallest source adapter required. |
| Dtype cast staging | **REUSE** | `comfy/ops.py:140-165`, `:219-230`; `comfy/model_management.py:1449-1479` | Native cast geometry, reusable cast buffers, quantized-tensor handling, and stream-aware dtype conversion already cover this. Phase E should route casts through these APIs or fail closed, not implement another cast staging path. |
| Offload/prefetch coordination | **ADAPT** | `comfy/model_management.py:718-754`, `:843-940`, `:1381-1422`; `comfy/model_prefetch.py:8-77` | Reuse `load_models_gpu`/`LoadedModel` ownership and native stream waits where the Phase-E path is integrated with a patcher. The `model_prefetch.py` queue is dynamic-vbar, inference-time prefetch and is not a first-cold transport primitive. |

Native mechanisms that are directly reusable are therefore the pin-budget policy, stream rotation/waits, cast/geometry helpers, and patcher load ownership. The pooled host-buffer and H2D paths require only a narrow integration seam, not replacement machinery.

## COMPONENTS_WE_STILL_NEED=

- A source adapter for the actual first-cold source: retained CPU snapshot tensors, ordinary CPU tensors, or a file-backed `TensorFileSlice`. Native `read_tensor_file_slice_into` only recognizes ComfyUI's `_comfy_tensor_file_slice` contract; it is not a generic Modal/file reader.
- A plain-model versus dynamic-patcher decision. In this checkout `CoreModelPatcher = ModelPatcher` (`comfy/model_patcher.py:2051`), while the pooled `HostBuffer` path is implemented in `ModelPatcherDynamic`. Phase E must not assume the dynamic pool is active for the standard loader.
- Eligibility checks for contiguous CPU storage, supported device, non-blocking capability, dtype/layout/quantization, and pin failure. `device_supports_non_blocking` is the native gate at `comfy/model_management.py:1252-1263`.
- A small lifetime boundary: retain source tensors and any native buffer owner until the copy stream has been joined, then publish the GPU-ready model. This is not a new scheduler.
- A fail-closed fallback and the existing first-cold readiness/telemetry boundary. Native helpers do not decide Phase-E identity, source validity, or fallback policy.
- If Phase E remains a direct file-to-GPU loader, its file reader and device-buffer owner remain necessary. That path is not the same as native CPU-pinned transport and should not be represented as a reuse of it.

## CODE_WE_CAN_AVOID_WRITING=

- A second growable pinned host pool, pin balancer, pin budget counter, or unregister-pressure policy.
- A Phase-E `torch.cuda.Stream` pool, stream rotation scheme, or duplicate current-stream wait logic.
- A general event manager for native cast/offload work. Only a narrow slot-reuse fence is justified when Phase E owns a reusable external staging slot.
- A duplicate packed-buffer allocator, byte alignment calculator, or dtype/quantized cast staging implementation.
- A dynamic-vbar prefetch queue or a second offload/prefetch scheduler for the cold model.
- The existing custom pinned-ring mechanics should not be copied into E1: `comfymodal_runtime/unet_pinned_staging.py:34-40,144-183`, `comfymodal_runtime/unet_meta_direct.py:213-375`, and the probe ring in `comfymodal_runtime/model_preload.py:889-1055` already reproduce pieces that native ComfyUI owns.
- The direct `fastsafetensors` path (`comfymodal_runtime/unet_fastsafetensors.py:584-615`) is a separate file-to-GPU ownership model. It cannot be made shorter by pretending its device buffer is a native pinned host pool.

## COMPATIBILITY_RISKS=

- AIMDO is optional. `main.py:44-45` initializes it only when dynamic VRAM is enabled; `HostBuffer`, `VRAMBuffer`, and VBAR operations depend on the native shared library and matching ABI.
- `--disable-pinned-memory`, platform/device policy, deterministic mode, MPS/XPU/DirectML, or `NUM_STREAMS == 0` can make pinning or non-blocking copies unavailable. Native helpers must be treated as capability-gated, not guaranteed.
- `cudaHostRegister` can fail even when a CPU tensor exists. Native `get_pin` can return an unregistered source after registration failure, and generic `model_management.pin_memory` returns `False`; Phase E must preserve the fallback path.
- Native accounting covers registrations made through native pin paths. A separate `torch.empty(pin_memory=True)` ring is not automatically represented by `TOTAL_PINNED_MEMORY`; mixing the two creates an unsafe budget view.
- `comfy.pinned_memory` uses module metadata (`_pin_state`, `_pin_registered`, stack indices, balancer entries) and may steal or truncate pins. Its views must not be treated as independently owned stable storage.
- `cast_modules_with_vbar` and `model_prefetch.py` require dynamic VBAR state (`_v`, signatures, dynamic pin state). They are not generic first-cold full-model transport APIs and would broaden scope into low-VRAM inference.
- Native `get_offload_stream` is an offload/cast stream, not a proof that the ordinary `Module.to()` full-load path is asynchronous. The E1 adapter must explicitly use the native cast seam or accept the authoritative synchronous baseline.
- Native `interpret_gathered_like` requires a one-dimensional byte buffer and applies aligned geometry offsets. Views, tied storage, quantized tensors, non-contiguous tensors, and dtype conversion need the same guards as native code.
- Any direct file-to-device owner, including `fastsafetensors.FilesBufferOnDevice`, has its own lifetime contract. Native stream waits do not release or protect that external owner automatically.
- The report assumes the deployed container keeps the pinned ComfyUI commit and compatible `comfy_aimdo` build together. A ComfyUI update must re-audit these private/semi-private seams.

## RECOMMENDED_E1_REFACTOR_IF_ANY=

**YES: refactor the E1 design before writing runtime code.** Make native ComfyUI the transport owner and reduce E1 to a source/lifetime adapter:

1. Keep the authoritative `ModelPatcher`/`load_models_gpu` lifecycle and existing readiness/fallback gates.
2. Use native pin-budget helpers and native pin APIs; do not maintain Phase-E pin totals.
3. Use `get_offload_stream` plus `cast_to`/`cast_to_gathered` and `sync_stream` for the async route. Retain source references until the stream join/final readiness fence.
4. Do not use `model_prefetch.py`, VBAR faults, or dynamic-vbar queues for this first-cold-only phase.
5. First verify whether the plain patcher can be routed through the native cast seam without changing model semantics. If it cannot, add only the smallest per-module/source adapter needed; do not reintroduce a custom pinned ring, stream pool, budget system, or cast allocator.

Net: E1 still needs source eligibility, ownership, and publication/fallback glue. It should not need new pinned-pool, budget, stream, event scheduler, contiguous-buffer, dtype-staging, or inference-prefetch machinery.
