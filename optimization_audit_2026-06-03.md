# Optimization Audit — June 3rd Cod Review

## Current 15.5s Wall Clock Breakdown

```
Modal restore (3.2s) ─→ Our restore (3.5s) ─→ Inference (7.8s) ─→ Overhead (1.0s)
                            │
                            ├─ gpu_state         246ms
                            ├─ cuda_warmup        75ms
                            ├─ sage_runtime       18ms
                            ├─ warmup_preload  2,481ms  ← 17GB FUSE volume read
                            └─ warmup_wf         652ms  ← executor overhead
```

## Junior Dev Findings — Assessment

### Item 1: Parallelize FUSE stat calls in path resolution
**Claim:** `_snapshot_preload_paths` does 12-16 sequential `os.path.isfile()` calls at 10-50ms each = 200-600ms wasted.

**Assessment: PARTIALLY WRONG for current data.** Our logs show path resolution takes ~1ms. File stat calls hit the page cache after `vol.reload()`. The junior is correct in theory (FUSE stats CAN be slow), but not for our specific workload. File under "real if volume is cold, negligible if warm."

### Item 2: Overlap path resolution with CUDA warmup
**Claim:** Start resolving model paths in parallel with `gpu_state_restore` + `cuda_warmup`.

**Assessment: WRONG.** Path resolution is ~1ms. There's nothing to overlap. Even if it were slower, the GPU phases (340ms total) are dwarfed by warmup_preload (2,481ms). Saving 1ms on path resolution is noise.

### Item 3: CLIP cache miss in __eq__ patch  ← HIGHEST VALUE
**Claim:** The `_patch_model_cache_comparison` isn't hitting for CLIP because warmup uses `CLIPLoader(type='flux2')` but the real prompt uses `DualCLIPLoader(type='flux')` or similar — different class names cause `__eq__` to compare different `model.__class__.__name__` values → always miss → CLIP reloads every time.

**Assessment: CORRECT.** This is the smoking gun. clip_load at 437ms is way too high for a true GPU cache hit (should be ~0ms). The UNET is matching fine (same class name both sides), but CLIP is always missed. This explains:
- clip_load stuck at 437ms (was 531ms — the ~100ms savings is just from warmup_wf's own ModelPatcher being kept warm, not from cache reuse)
- clip_encode didn't improve (wrong CLIP model on GPU)
- The __eq__ patch appears to only work for the UNET

**The fix:** Make warmup_wf use the same loader/type as the real prompt, OR change __eq__ to match by model file path instead of class name.

### Item 4: Warmup WF bypass → direct GPU cache injection  ← HIGHEST VALUE
**Claim:** Replace `_execute_in_process(warmup_wf)` with directly creating ModelPatchers from cached state dicts and injecting into `current_loaded_models` — bypassing ComfyUI executor validation, graph building, event dispatch, cleanup.

**Assessment: CORRECT.** The executor overhead dominates warmup_wf (652ms total, maybe ~150ms actual model-to-GPU copy). We already have state dicts in CPU RAM from warmup_preload. Direct injection saves ~500ms.

**Approach:** Instead of `_execute_in_process`, call `comfy.utils.load_torch_file` (hits CPU cache), then create `ModelPatcher`, then `load_models_gpu([patcher])` which adds to `current_loaded_models`.

### Item 5: Redundant profile load
**Claim:** `_snapshot_preload_profile` loads profile, then `load_warmup_profile` loads the same thing again for warmup_wf.

**Assessment: CORRECT but trivial.** Saves ~1ms. Clean code.

### Item 6: Skip VAE preload
**Claim:** VAE (190ms) is wasted because warmup_wf doesn't use it and ComfyUI loads VAE differently anyway.

**Assessment: WRONG.** The VAE is 0.3GB at 174ms. Loading it into CPU cache actually DOES help: the real prompt's `vae_decode` uses `load_torch_file` internally. Without the CPU cache, that 174ms moves into inference (vae_decode increases). Plus 0.3GB is negligible. Not worth optimizing.

### Item 7: Skip profiling infra in warmup
**Claim:** `_begin_prompt_profile`, `_stage_windows`, event dispatch all run pointlessly during warmup.

**Assessment: CORRECT but moot if we implement Item 4.** If we bypass `_execute_in_process` entirely (Item 4), the profiling infra doesn't run at all.

## Priority Order

| Priority | Item | Est. Savings | Effort |
|----------|------|-------------|--------|
| 1 | Fix CLIP cache miss (Item 3) | ~437ms clip_load + ~100ms clip_encode | Medium |
| 2 | Direct GPU cache injection (Item 4) | ~500ms | Low-Medium |
| 3 | Remove redundant profile load (Item 5) | ~1ms | Trivial |
| | **Total code-only** | **~1.0-1.5s** | |

## Remaining Gap to 12s

After Items 3+4: 15.5s → ~14.0-14.5s. Remaining ~2.0-2.5s to reach 12s requires addressing warmup_preload (2,481ms), which is FUSE volume throughput-bound. Options:
- Models in Docker image (page cache survives snapshot)
- Accept warm NVMe snapshot restores (12s when hot)
