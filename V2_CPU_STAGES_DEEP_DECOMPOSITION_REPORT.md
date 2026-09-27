# V2 CPU Stage Deep Decomposition — `load_model_weights` (~2.8s) and ModelPatcher creation (~1.4s)

**Date:** 2026-08-11
**Scope:** Code-only deep decomposition of the two CPU stages in the deployed V2 runtime (plain `ModelPatcher`, HIGH_VRAM, safetensors mmap), plus the smallest native fast-disk optimization that preserves normal ModelPatcher, patching, SageAttention, CacheDiT, dtype, and output semantics.

---

## 1. Ground truth: active deployment path

| Property | Value | Evidence |
|---|---|---|
| Patcher class | Plain `ModelPatcher` (not `ModelPatcherDynamic`) | `comfy/model_patcher.py:2051` (`CoreModelPatcher = ModelPatcher`); `main.py:233` never runs in-process |
| DynamicVRAM / comfy-aimdo | Disabled | `comfy/memory_management.py:173` `aimdo_enabled=False`; V1 relaunch uses `--gpu-only --disable-smart-memory` (`comfyapp.py:18206-18212`) |
| VRAM state | HIGH_VRAM | `comfyapp.py:20010`; UNET offload resolves to CUDA (`model_management.py:1009-1013`) |
| Weight load mode | `assign=False` | `sd.py:2016` → full CPU→GPU copy per parameter |
| File read | safetensors `safe_open` mmap | `comfy/utils.py:122-167`; `COMFYMODAL_SAFETENSORS_READ_MODE=normal` |
| Model | Flux-class UNET (6.15B params) | cache-dit==1.2.3 family baked (`cachedit_dependency_lock.txt`); SageAttention v2.2.0 baked |
| Timing instrumentation | `time.monotonic_ns()`, **no `torch.cuda.synchronize()`** | `model_preload.py:4525-4538`, `:3288-3322`; by design `optimizations.py:2394` |

### Loader call sequence (`comfy/sd.py:1925-2020`)

```
load_diffusion_model_state_dict
  ├─ calculate_parameters / weight_dtype        (sd.py:1961-1962)  metadata scans
  ├─ model_config_from_unet                     (sd.py:1965)        model detection
  ├─ model_config.get_model(new_sd, "")         (sd.py:2011)        CPU torch.empty 12-24 GB
  ├─ ModelPatcher(model, cuda, cuda)            (sd.py:2013)        dict/uuid bookkeeping, µs
  ├─ model.to(cuda)                             (sd.py:2014-2015)   async H2D of EMPTY params  ← the ~1.4s
  └─ model.load_model_weights(new_sd, "", assign=False)  (sd.py:2016)  ← the ~2.8s
       └─ process_unet_state_dict               (model_base.py:347)  Flux key rebuild + rename
       └─ diffusion_model.load_state_dict(to_load, strict=False, assign=False)  (model_base.py:348)
            └─ per-param param.copy_(mmap_cpu_tensor) → H2D + (possible) dtype cast
```

---

## 2. Why `load_model_weights` takes ~2.8s

`comfy/model_base.py:340-355`:

1. `keys = list(sd.keys())` — materialized key list.
2. Filter/move `unet_prefix` entries into a new `to_load` dict (mutates `sd`).
3. `process_unet_state_dict(to_load)` — for Flux this is a pure-Python rebuild renaming `*_norm.scale` → `*_norm.weight`.
4. `load_state_dict(to_load, strict=False, assign=False)` — the dominant cost.

With `assign=False` and the model already on CUDA (`sd.py:2015`), PyTorch copies every mmap-backed checkpoint tensor into its pre-allocated CUDA parameter via per-parameter `copy_`. The measured 2.8s is a CPU-observed wall window containing:

- **Safetensors mmap page faults** + disk reads from the Modal volume (cold pages).
- **Python traversal + key matching** of the state dict (~450 keys for Flux).
- **One full-model CPU→GPU transfer** (~13-24 GB) enqueued across ~450 `copy_` calls.
- **CUDA allocation/synchronization debt** — the first `copy_` absorbs the caching-allocator's device-wide synchronize (a fresh multi-GB segment was allocated by `model.to(cuda)` in the prior step).
- **Possible dtype conversion** if checkpoint dtype ≠ model parameter dtype (e.g., fp16 file into bf16 model).

**Important:** the timer measures wall time between Python calls with no CUDA synchronization at either boundary. It therefore captures CPU-blocked latency, not isolated PCIe/GPU event time. GPU-side H2D execution surfaces later in waterfall windows (`clip_to_sampler_node` ≈ 2.6-2.8s in `C8_BENCHMARK_COMPLETE_RUN_LOG.md`).

---

## 3. Why "ModelPatcher creation" shows ~1.4s

### Native `ModelPatcher.__init__` is NOT 1.4s

`comfy/model_patcher.py:293-353` is pure bookkeeping: dicts, UUIDs, flags, callback/wrapper tables, attribute defaults. It does **no** parameter iteration, no tensor access, no `model_size()` (that is lazy at `:357-361`), no CUDA. **µs at most.**

### What the 1.4s actually is

With HIGH_VRAM, `offload_device` is CUDA, so `sd.py:2014-2015` executes:

```python
model.to(offload_device)   # == model.to(cuda)
```

on freshly `torch.empty`'d parameters (12-24 GB of uninitialized memory). This:

1. Allocates a fresh multi-GB CUDA segment (device-wide synchronize inside the caching allocator).
2. **Reads and transfers an entire model's worth of blank memory over PCIe** — a full-size H2D pass of garbage.
3. Immediately afterwards, `load_model_weights` transfers the *real* weights (the ~2.8s).

So the deployed flow ships **~26-48 GB of PCIe traffic when ~13-24 GB would suffice**: the weights are moved to GPU twice — once empty, once real.

**Label caveat (must be resolved before trusting any number):**

- If "ModelPatcher creation" names the broad *model/patcher placement* stage, the 1.4s is the wasteful `model.to(cuda)` zero-data pass.
- If the literal `model_patcher_constructor_ms` field reported 1.4s, that attribution is invalid/contaminated. The constructor timer (`model_preload.py:3288-3322`) measures native `__init__` **plus** two comfyui-modal helpers (`ensure_sampling_timing_wrapper`, `register_unet_forward_probe`) — both idempotent, µs after first call, no model traversal. A literal 1.4s under that label would be scheduling/import/allocator debt bleeding into the window, not native construction work.
- The `model_to_ms` child span (`model_preload.py:3333-3353`) is the honest owner of the placement pass — but it is only recorded when a UNET lane ContextVar is active; otherwise the time falls into the SD-span residual (`model_preload.py:4596`).

---

## 4. Repeated traversals and shared work

### The double H2D (dominant, both stages)

1. `model.to(cuda)` walks every parameter and transfers blank storage (≈1.4s).
2. `load_state_dict(assign=False)` walks every parameter again and transfers the real checkpoint value (≈2.8s).

Same parameter set, same destination device, twice. Removing pass 1 is the core of the optimization below.

### Later repeated model traversals (post-load)

- `model_size()` → `module_size()` → full `state_dict()` materialization (`model_management.py:618-624`) — triggered by the first `model_size()` call (clone / `LoadedModel.model_memory()`).
- `ModelPatcher.load` → `_load_list()` (`model_patcher.py:891-926`): `named_modules()`, `named_parameters()` twice per module, per-module `state_dict()`.
- `patch_weight_to_device()` per parameter + a second `module.to(device)` pass.
- `add_patches()`/LoRA path — another full `model.state_dict()` (`model_patcher.py:791`).

### The checkpoint `sd` dict is also scanned ~10-12 times

`unet_prefix_from_state_dict`, `calculate_parameters`, `weight_dtype`, `convert_old_quants`, `detect_unet_config`, `matches`/`required_keys`, `detect_layer_quantization`, the `load_model_weights` prefix filter, Flux `process_unet_state_dict` rebuild, PyTorch `load_state_dict` key matching (plus VAE `state_dict_prefix_replace` and CLIP `process_clip_state_dict` on the checkpoint path).

### Summary

| Item | Cost class | Removable? |
|---|---|---|
| `model.to(cuda)` of empty params | ~1.4s H2D | **Yes — fuse into the real weight load** |
| `load_state_dict(assign=False)` H2D | ~2.8s H2D floor | No (exact semantics) — weights must reach GPU |
| Later `model_size()`/`_load_list()` traversals | ~0.3-0.5s | Yes — `size=` pass-through / traversal cache (v2/v3) |
| Python `sd` scans | ~10-50 ms | Marginal — reject |

---

## 5. Smallest native fast-disk optimization (design)

### Recommended: guarded reorder + `assign=True` in `comfy/sd.py:2011-2019`

```python
model = model_config.get_model(new_sd, "")
model_patcher = ModelPatcher(model, load_device=load_device, offload_device=offload_device)

fast = (
    not model_patcher.is_dynamic()                 # plain patcher
    and load_device == offload_device              # HIGH_VRAM / gpu-only
    and not model_management.is_device_cpu(load_device)
    and custom_operations is None
    and model_config.quant_config is None
    and not model_options.get("fp8_optimizations", False)
    and weight_dtype == unet_dtype                 # no dtype conversion needed
    and not model_management.force_channels_last()
    and <native fast-disk opt-in flag>
)
if fast:
    model.load_model_weights(new_sd, "", assign=True)   # rebind mmap tensors, no copy
    model.to(load_device)                               # single fused alloc + page-in + H2D
else:
    if not model_management.is_device_cpu(offload_device):
        model.to(offload_device)
    model.load_model_weights(new_sd, "", assign=False)
```

### Why it is correct (semantics-equivalence argument)

- `assign=True` (torch ≥2.8) rebinds the checkpoint tensors into the model parameters (`setattr(module, name, Parameter(input_param))`) — **no copy, no dtype/device conversion**. With the guard `weight_dtype == unet_dtype`, parameter dtype equals the file dtype, which equals the dtype construction produced (bf16 Flux/SD3.5, fp16 SDXL in the common cases).
- The subsequent `model.to(cuda)` performs one `_apply` pass that transfers the **real** weights once — the same fused alloc+copy the dynamic (`assign=True`) path already relies on.
- End state is identical to today's HIGH_VRAM end state: all params on CUDA, correct dtype/values, `requires_grad=False`, `model.device == cuda`.
- LoRA patching (`add_patches`/`patch_weight_to_device` keyed by parameter name), hooks, backups, cloning, `model_options` cloning, CacheDiT (`_cache_dit_config`, OUTER_SAMPLE/DIFFUSION_MODEL wrappers, same diffusion_model identity), and SageAttention (dtype/device-preserving) all operate on the same tensor set — unaffected.
- The mmap-backed checkpoint tensors are only *read* by `.to(cuda)` then unlinked from the model; no code path writes into them.

### Guards (each cheap, each forces the legacy branch otherwise)

1. `load_device == offload_device` non-CPU — **critical**. On NORMAL/LOW VRAM, weights must stay CPU-resident until execution-time `load()`; taking the fast path would break eviction/memory accounting in `load_models_gpu`.
2. `weight_dtype == unet_dtype` — otherwise `assign=False`'s `copy_` performs the conversion that `assign=True` silently skips.
3. `custom_operations is None` / `quant_config is None` / no fp8 — keeps quantized/scaled wrappers out of the rebind path.
4. `not force_channels_last()` — `assign=True` would discard the construction-time memory format.
5. `not is_dynamic()` — trivially true for the standard loader, kept for upstream safety.
6. Explicit opt-in env/flag so the standard path remains the default fallback everywhere else.

### Expected effect

- `load_model_weights` span drops to ~rebinding + Python overhead (~0.05s).
- The single `model.to(cuda)` absorbs the real ~2.8s H2D.
- Combined loader moves from ~4.2s → ~2.8-3.0s (one H2D pass instead of two).

### Explicit flag

The ~2.8s H2D floor is **not** removable by any exact-semantics-preserving native loader change. Only quantization (fewer bytes) or deferred device placement (moves time, doesn't reduce it) can go below it — both outside the "exact outputs / standard fallback" constraint.

### v2 follow-up (independent, zero semantic risk)

Pass the correct size into the constructor to skip the first full `model_size()` → `module_size()` `state_dict()` traversal:

```python
parameters = calculate_parameters(new_sd)   # recompute on processed UNET-only sd
size = parameters * model_management.dtype_size(unet_dtype)
model_patcher = ModelPatcher(model, load_device, offload_device, size=size)
```

Note: `calculate_parameters` at `sd.py:1961` overcounts for full checkpoints (includes CLIP+VAE) — recompute against `new_sd` or restrict to the UNET-file path (`load_diffusion_model`, `sd.py:2022`).

### Rejected options

- **Meta construction + `assign=True`** — breaks models that compute buffer values at `__init__` (positional/time embeddings not in the file stay meta → crash at forward). Plain-CPU construction + `assign=True` achieves the same end state with none of the risk.
- **Direct `safe_open(device="cuda")`** — loader-level semantic change affecting every caller; collides with the CPU-snapshot preload design; with `assign=False` causes a *double* transfer.
- **Reorder only (no `assign`)** — CPU memcpy *plus* later H2D = strictly more bytes + 13-24 GB RAM staging.
- **Prefix-processing fusion** — saves only ~10-50 ms; not worth the change surface.

---

## 6. Verification performed

- One diagnostic deployment (`COMFYMODAL_V2_ENV_PROFILE=diagnostic`, `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`, `COMFYMODAL_V2_VAE_SNAPSHOT=0`) via the mandated `deploy_and_run_v2_single.bat`.
- Three remote non-model-snapshot requests; container logs confirm `cpu_snapshot_active=0` throughout.
- All three remote requests completed; the local harness then rejected them with `C8 runtime-shape validation failed: stored snapshot order=None deployed='O0'` — a validator bug at `tools/benchmark_v2_direct.py:293-309` that requires stored snapshot order `O0` even when model snapshots are disabled. **Run artifacts were therefore not persisted.**
- `[v2.bg_unet_stages]`/`[v2.bg_unet_io]` lines were absent from container logs because the deployed path runs with `COMFYMODAL_V2_RESTORE_BACKGROUND_UNET=0`; the stage values in this report are therefore from static decomposition + prior in-repo artifacts, not fresh per-stage measurements.
- No source files were modified. The workspace contains uncommitted changes from other concurrent agents (`comfyapp.py`, `comfymodal_runtime/modal_app.py`, both `.bat` scripts, `tools/benchmark_v2_direct.py`, two untracked tests) — preserved untouched.

## 7. Remaining uncertainty

- The literal `model_patcher_constructor_ms ≈ 1400` attribution is inferred from code ordering, not confirmed against a captured `[v2.bg_unet_stages]` line (the emitter is compiled out of production and not reached in the restore path). The 1.4s could belong to `model_to_ms` or the SD-span residual instead.
- The exact split of the 2.8s among allocator-sync / volume page-in / CPU cast / H2D enqueue is unmeasured (instrumentation deliberately omits CUDA events and page-fault deltas).
- The deployed container's ComfyUI may differ from the local pinned snapshot (unverified `comfy_aimdo` presence; local alias at `model_patcher.py:2051`).

## 8. Recommended implementation checks

1. Confirm `weight_dtype == unet_dtype` for the target checkpoint family (bf16 Flux); fp16→bf16 mismatches must stay on the legacy path.
2. Guard NORMAL/LOW_VRAM fallback is untouched (the `load_device == offload_device` guard is the only thing keeping accounting correct).
3. After fast-path load, assert byte-equality of every `state_dict` entry vs. the standard path, all params on CUDA, no remaining mmap-backed storage in the model.
4. Run one full denoise with CacheDiT + SageAttention + a LoRA and compare outputs bitwise.
5. Load→unload→reload the same file and verify mmap handle counts return to baseline (the `.to(cuda)` rebind must free the original mmap storages).
