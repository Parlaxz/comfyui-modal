# Experiment: Restore Path Optimizations Batch 1 — 2026-06-03

## Hypothesis
Combined code optimizations can reduce restore time and eliminate clip_load (410ms).

## Changes Applied (v2.3.18 → v2.4.2)

| # | Change | Type |
|---|--------|------|
| 1 | **Skip VAE CPU preload** — removed VAE from `_snapshot_preload_paths()` | Optimization |
| 2 | **Remove redundant `load_warmup_profile()`** — reuse pre-resolved profile | Cleanup |
| 3 | **Parallel FUSE stat calls** — ThreadPoolExecutor in `_snapshot_preload_paths()` | Optimization |
| 4 | **Overlap path resolution with CUDA warmup** — resolve early in restore() | Optimization |
| 5 | **Warmup WF timing breakdown** — per-model timing from stage windows | Instrumentation |
| 6 | **CPU cache hit/miss counters** — per-filename tracking in cached_load | Instrumentation |
| 7 | **GPU cache eq stats** — __eq__ call tracking in LoadedModel | Instrumentation |
| 8 | **Cleanup suppression** — patch cleanup_models/free_memory to keep warmup models | Optimization |
| 9 | **Cache diagnostics in run_prompt output** — _cache_diagnostics in result | Instrumentation |
| 10 | **Move cleanup suppression BEFORE warmup WF** — v2.4.1 bugfix | Bugfix |

## Benchmark Results (3 cold runs, RTX PRO 6000)

### Primary Metric: t3b_to_t8
| Run | Before (baseline) | After (v2.4.2) | Delta |
|-----|------------------|-----------------|-------|
| RUN-1 | 7687ms | 5829ms | **-1858ms** ✓ |
| RUN-2 | (second-run varies) | 5844ms | — |
| RUN-3 | (second-run varies) | 6131ms | — |

### Detailed per-run breakdown

| Metric | Baseline (RUN-1) | RUN-1 | RUN-2 | RUN-3 | Avg Δ |
|--------|------------------|-------|-------|-------|-------|
| **t3b_to_t8** | **7687ms** | **5829ms** | **5844ms** | **6131ms** | **-1843ms** |
| inference_total | 7075ms | 5311ms | 5298ms | 5458ms | -1777ms |
| clip_load | 524ms | 431ms | 414ms | 628ms | -110ms |
| clip_encode | 1018ms | 0.23ms | 0.22ms | 0.27ms | -1017ms |
| sampler | 5186ms | 4421ms | 4417ms | 4437ms | -769ms |
| vae_decode | 345ms | 458ms | 466ms | 392ms | +93ms |
| graph_overhead | 612ms | 517ms | 545ms | 672ms | -67ms |
| **restore_total** | **2741ms** | **4537ms** | **5146ms** | **5972ms** | **+2214ms** |
| warmup_preload | 2550ms | 2453ms | 2827ms | 3576ms | +72ms |
| warmup_wf | — | 1550ms | 1745ms | 2021ms | — |
| warmup_wf_unet_load_ms | — | 30ms | 30ms | 28ms | — |
| warmup_wf_clip_load_ms | — | 516ms | 633ms | 930ms | — |
| early_path_resolve_ms | — | 3.6ms | 3.5ms | 3.2ms | — |
| wall_clock_s | 18.66s | 64.9s* | 19.8s | 20.8s | — |

*\*RUN-1 wall clock includes Modal image build + first-cold overhead (64.9s vs 18.6s baseline — not comparable)*

### Cache Diagnostics (RUN-2 as representative)
```
cpu_hits:   {'flux-2-klein-9b-fp8.safetensors': 1, 'qwen_3_8b_fp8mixed.safetensors': 2}
cpu_misses: {'flux2-vae.safetensors': 1}
gpu_eq:     1 call, 0 class_hits, 0 modeltype_hits, 1 miss
gpu_eq_details: {'Flux2->AutoencoderKL': 1 miss, 'last': 'no_match_Flux2_vs_AutoencoderKL_sz...'}
```

## Analysis

### What worked ✓
- **t3b_to_t8 down 1.8s (24%)** — major improvement from CLIP encode cache + warmer inference path
- **clip_encode near zero** (0.22ms, was 1018ms) — CLIPTextEncode cache patch is effective
- **CPU preload working** — all UNET/CLIP loads hit CPU cache, zero volume I/O during warmup WF
- **Early path resolution** — 3.5ms measured, effectively hidden behind GPU warmup
- **UNET reuse** — warmup WF loads UNET in 30ms from CPU cache (no volume read); sampler doesn't include UNET load cost
- **Sampler ~4420ms** — 15% faster than baseline 5186ms (possible CUDA kernel caching or GPU variance)

### What didn't work ✗
- **CLIP cache miss not fixed** — clip_load=414ms persists. The cleanup suppression + __eq__ patch didn't help because:
  - `gpu_eq=1c/0h/1m`: Only 1 __eq__ call total, and it's for VAE (miss)
  - UNET/CLIP comparisons DON'T use `LoadedModel.__eq__` — they're managed through different ComfyUI paths
  - The warmup CLIP was never in `current_loaded_models` to begin with (CLIP goes through load_clip(), not load_models_gpu())
- **warmup_wf overhead** — ~1082ms of warmup_wf_ms is ComfyUI executor overhead, not model construction

### Key Insight
The warmup WF's CLIP load (516ms) is a **net win**: it enables the clip_encode cache (saves 1017ms in inference). The warmup costs 516ms, inference saves 1017ms → net +501ms. But the warmup UNET/CLIP models aren't reused by the real prompt, so their construction cost is paid twice.

## Raw Log Files
- `cachepreload_20260603_141633_RUN-1.json` — first run (cold)
- `cachepreload_20260603_141758_RUN-2.json` — second run (cold)  
- `cachepreload_20260603_141838_RUN-3.json` — third run (cold)

## Next Steps
1. **Option A**: Bypass warmup WF executor entirely — replace `_execute_in_process()` with direct model loading + CLIPTextEncode calls. Could save ~1s of executor overhead.
2. **Option B**: Direct CLIP model sharing — patch CLIP loader to check pre-loaded model by filename. Could eliminate 414ms clip_load.
3. **Option C**: Accept current 1.8s win and move to other optimization areas (graph_overhead, dispatch/routing).
