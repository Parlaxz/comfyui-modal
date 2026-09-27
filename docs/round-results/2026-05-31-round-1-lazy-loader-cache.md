# Round 1 — Lazy Per-Class Loader-Object Cache

Date: 2026-05-31

---

## Baseline (Round 0)

Captured prior to any changes. Same workflow, same conditions.

| Metric | Run 1 | Run 2 |
|--------|-------|-------|
| Startup | ~12.6s (cold) + ~1.3s snapshot | — |
| Restore | ~0.225s | ~0.237s |
| `remote_total` | 13026.3ms | 13869.1ms |
| CLIPLoader | 3005.5ms | 3541.9ms |
| UNETLoader | 104.7ms | 110.3ms |
| SamplerCustomAdvanced | 8747.9ms | 9014.2ms |
| VAEDecode | 290.8ms | 302.1ms |
| VAELoader | 158.3ms | 152.1ms |
| CLIPTextEncode (x2) | ~549ms | ~581ms |
| Attention | sdpa / pytorch | sdpa / pytorch |
| Sampler progress | 3.13 it/s | 3.13 it/s |

---

## Change Implemented

**What:** Patch the FUNCTION method of `DualCLIPLoader`, `CLIPLoader`, `UNETLoader`, `VAELoader` in `nodes.NODE_CLASS_MAPPINGS` to cache their return values (live model objects) after the first run. On subsequent runs with identical inputs, return the cached object directly — skipping re‑constructing the model architecture and re‑loading state dicts.

**Why:** Baseline showed CLIPLoader at ~3‑3.5s and VAELoader at ~150ms on every run. The CPU state‑dict cache (`_patch_model_cpu_cache`) already eliminated volume I/O, but the model *objects* (Qwen 8B text encoder, VAE, UNet) were being reconstructed from those cached state dicts each time.

**Key design decisions:**
- **No cross‑class eviction** — each loader class populates its own cache entry. All 4 loaders coexist so the entire stack is cached after one run.
- **Live objects, no deepcopy** — the cached tensors are already on GPU. Returning them directly means `load_models_gpu` is effectively a no‑op on cache hit.
- **Lazy population** — cache is populated on first real request, never at startup or restore.
- **Opt‑out** via `COMFYMODAL_LOADER_CACHE=0`.

**Files changed:**
- `comfyapp.py`: added env var, `_patch_loader_object_cache()` method, call in `_start_in_process_backend()`
- `tests/test_comfyapp_auto_warmup.py`: 3 new AST tests

---

## Round 1 Data (Profiling On)

### First Run

- `remote_total`: **13922.5ms**
- `inproc_execute`: 13914.2ms

| Node | Duration | Cache Line |
|------|----------|-----------|
| VAELoader | 617.7ms | `loader_cache_miss class=VAELoader key=('VAELoader', ('vae_name', 'full_encoder_small_decoder.safetensors'))` |
| CLIPLoader | 3022.4ms | `loader_cache_miss class=CLIPLoader key=('CLIPLoader', ('clip_name', 'qwen_3_8b_fp8mixed.safetensors'), ('device', 'default'), ('type', 'flux2'))` |
| UNETLoader | 108.1ms | `loader_cache_miss class=UNETLoader key=('UNETLoader', ('unet_name', 'flux-2-klein-9b-fp8.safetensors'), ('weight_dtype', 'default'))` |
| CLIPTextEncode (pos) | 408.4ms | — |
| CLIPTextEncode (neg) | 175.6ms | — |
| SamplerCustomAdvanced | 9106.6ms | prep only (no progress events captured) |
| VAEDecode | 311.8ms | — |

### Second Run

- `remote_total`: **13297.8ms**
- `inproc_execute`: 13288.1ms

| Node | Duration | Cache Line |
|------|----------|-----------|
| VAELoader | 572.3ms | `loader_cache_miss class=VAELoader …` ⚠️ **BUG** |
| CLIPLoader | 2635.4ms | `loader_cache_miss class=CLIPLoader …` ⚠️ **BUG** |
| UNETLoader | 107.3ms | `loader_cache_miss class=UNETLoader …` ⚠️ **BUG** |
| CLIPTextEncode (pos) | 402.1ms | — |
| CLIPTextEncode (neg) | 166.9ms | — |
| SamplerCustomAdvanced | 8919.8ms | prep only |
| VAEDecode | 317.6ms | — |

---

## Bug Identified

**All 4 loaders show `loader_cache_miss` on the second run.** The cache wrapper was clearing the entire shared dict on any miss:

```python
# BUG: clears previous loader's entry within the same run
_cache.clear()  # ← removes VAELoader entry when CLIPLoader runs
```

In a single workflow execution, loaders execute in order (VAE → CLIP → UNET). When CLIPLoader runs, its key is not in the cache yet, so `_cache.clear()` evicts the VAELoader entry that was just stored. By the end, only the last loader is cached.

**Fix applied:** Removed the `_cache.clear()` call. The cache now accumulates entries per (class_type, params) pair without cross-class eviction. This is naturally bounded to at most one entry per distinct loader input — 4 entries for a typical stack.

---

## Expected Round 1b (after fix) — Projection

With all 4 entries cached after the first run, the second run should show:

| Metric | Projected Run 2 | Improvement vs Baseline |
|--------|----------------|----------------------|
| CLIPLoader | **~0ms** (cache hit) | −3.5s |
| VAELoader | **~0ms** (cache hit) | −0.15s |
| UNETLoader | **~0ms** (cache hit) | −0.1s |
| SamplerCustomAdvanced | ~8900ms (unchanged) | — |
| VAEDecode | ~300ms (unchanged) | — |
| **remote_total** | **~9600ms** | **−4.3s from baseline** |

This would bring second-run from ~13.9s toward ~9.6s — close to the <9s target but still needing sampler improvements (Round 3).

---

## Key Lessons

1. **One-hot eviction doesn't work with sequential per-run population** — the first run always clears entries set by earlier loaders.
2. **No cross-class eviction is safe** because the cache is naturally bounded: only 4 loader classes exist, and each holds at most one entry per distinct parameter set.
3. **CLIPLoader dominates non-sampler time** (~3s), which is entirely eliminated on cache hit.
