# Performance Baseline — stable-modal-comfy-v1

**Built:** comfyapp.py v2.14.0
**Workflow:** 37-node Flux2 production (UNETLoader + Flux2Scheduler + KSamplerSelect + SamplerCustomAdvanced,
4 uniform steps, VAE decode, SaveImage)
**GPU:** RTX PRO 6000 (Blackwell, SM 12.0)
**SageAttention:** baked_cuda (pre-compiled CUDA kernels for Blackwell)

---

## Expected Latency (cold start, 3-run median)

| Component | Expected | Notes |
|---|---|---|
| **remote_execute** (t3→t9) | **~5.4–5.6s** | Stable across runs |
| **app_restore** | **~4.6–6.6s** | CPU preload + GPU warmup + Sage select |
| **app_controlled** | **~10–12s** | Sum of app_restore + remote_execute |
| **platform_restore** | **~6–9s** | Modal GPU snapshot restore — outside app control |
| **wall clock** | **~16–20s** | Everything including platform + image return |

### remote_execute Breakdown

| Phase | ms | % of remote_exec |
|---|---:|---:|
| Sampler denoising (4 steps) | ~3010 | 55% |
| VAEDecode | ~380 | 7% |
| SaveImage | ~290 | 5% |
| Image Comparer | ~180 | 3% |
| prepare_sampling / load_models_gpu | ~500 | 9% |
| VAELoader | ~160 | 3% |
| SCA pre/post overhead | ~525 | 10% |
| CLIPTextEncode (WCE hit) | ~0.15 | ~0% |
| Executor residual | ~1 | ~0% |
| CLIPLoader / UNETLoader (cache) | ~2 | ~0% |

---

## Production Defaults

| Flag | Default | Notes |
|---|---|---|
| `COMFYMODAL_ENABLE_WARMUP` | 1 | Warmup models + CLIP encode |
| `COMFYMODAL_PRELOAD_MODE` | workers_2 | 2-thread CPU preload, optimal for FUSE |
| `COMFYMODAL_WARMUP_CLIP_ENCODE` | 1 | Prime CLIPTextEncode cache at restore |
| `COMFYMODAL_RETURN_MODE` | full_base64 | All images returned as base64 |
| `COMFYMODAL_EXEC_PROFILE` | 0 | Off |
| `COMFYMODAL_SAMPLER_PROFILE` | 0 | Off |
| `COMFYMODAL_GUIDER_PROFILE` | 0 | Off |
| `COMFYMODAL_DEEP_PROFILE` | 0 | Off |
| `COMFYMODAL_MODELPATCHER_CACHE` | 0 | Off (no measurable win) |
| `COMFYMODAL_LMG_FASTPATH` | 0 | Off (blocked by ModelPatcher identity) |
| `COMFYMODAL_LMG_FASTPATH_DRYRUN` | 0 | Off |
| `COMFYMODAL_MODELPATCHER_TRACE` | 0 | Off |
| `COMFYMODAL_ENABLE_GPU_SNAPSHOT` | 0 | Off (CPU snapshot sufficient) |
| `COMFYMODAL_ENABLE_TORCH_COMPILE` | 0 | Off (causes CUDA errors post-restore) |

**Active patches (always on):**
- CLIP loader cache (reuse warmup CLIP objects)
- CLIPTextEncode model-aware cache (WCE=1)
- Async `vol.commit()` (non-blocking response path)
- SageAttention baked_cuda policy

---

## Known Outliers

| Component | Typical | Outlier | Frequency | Cause |
|---|---|---|---|---|
| Preload | 2.5–3.0s | >5s | ~10% | FUSE volume I/O variance |
| platform_restore | 6–9s | >12s | ~20% | Modal container scheduling |
| VAE decode | ~380ms | >1300ms | ~15% | GPU clock ramp / memory bandwidth |

---

## Next Frontiers

| Area | Potential | Risk | Status |
|---|---|---|---|
| Image delivery (output path) | ~500–800ms | Low | Not started |
| Sampler CUDA graph / torch.compile | ~1500ms | Medium | Research only |
| ModelPatcher identity fix | ~450ms | High | Blocked (warmup ≠ prompt) |
| Modal scaledown_window tuning | N/A | Low | Intentionally excluded |

---

## No Workflow Edits

The 37-node production workflow is **unmodified**. No node pruning, hardcoded IDs, or
workflow-specific JSON edits are part of this build. All optimizations are generic
runtime/class patches in comfyapp.py.
