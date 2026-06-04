# Restore Optimization Experiments — Batch 5

## Summary of Changes

| Change | Before | After | Savings |
|--------|--------|-------|---------|
| CLIP object cache + workflow clip_type | clip_load=375-524ms | clip_load=0.7ms | ~500ms |
| CLIPTextEncode model-aware cache | clip_encode=600-1000ms | clip_encode=0.2ms | ~600-1000ms |
| `vol.commit()` async (non-blocking) | t8b_to_t9=370-396ms | t8b_to_t9=3.7-4.8ms | ~370ms |
| Preload mode `workers_2` (was 4) | preload=2.7-3.4s | preload=2.4-2.8s | ~200ms |
| WARMUP_CLIP_ENCODE=0 (disable) | warmup_direct=1700ms | warmup_direct=670ms | ~1000ms restore, -900ms inference |

## Final Best Run (v2.10.0, workers_2, WCE=0, async commit)

```
RUN-3: wall_clock=17.7s  known_total=10240ms
  app_restore_total  = 3882ms
  remote_total       = 6358ms  
  untracked_gap      = 7433ms  (Modal platform overhead)
  t3b_to_t8          = 6160ms  (inference + clip_encode in real prompt)
  inference_total    = 5660ms
  clip_load          = 0.73ms  (CLIP object cache HIT)
  clip_encode        = 872ms   (first encode, uncached)
  sampler            = 4422ms
  vae_decode         = 365ms
  graph_overhead     = 500ms
  warmup_preload     = 2793ms
  warmup_direct      = 667ms   (no CLIP encode)
  t8b_total          = 3.7ms   (async commit)
  cpu_hits           = flux-2-klein:2, qwen_3_8b:1
  clip_cache_hits    = 1, misses = 1
```

## Issue Fixes

### Issue 1: Stale diagnostics
- Root cause: `warmup_vs_workflow` diagnostics used `load_warmup_profile()` (env vars) instead of actual restore profile.
- Fix: Store actual `_warmup_profile` dict in `_last_restore_timing["warmup_profile"]`. Diagnostics now read from restore timing.

### Issue 2: First cold after deploy
- Root cause: Module-level `WARMUP_CLIP_TYPE` constant froze at import time (`"flux"`). Restore function set `COMFYMODAL_WARMUP_CLIP_TYPE=flux2` at runtime but `load_warmup_profile()` ignored it due to `or` short-circuit.
- Fix: Changed `load_warmup_profile()` to prefer `os.environ.get()` over module-level constants.

## Experiment Results

### Experiment 1 — Preload variance

| Mode | preload_ms | restore_total | known_total | verdict |
|------|-----------|---------------|-------------|---------|
| default (4 workers) | 2529-2863ms | 4570-5219ms | 10648-10845ms | good |
| sequential (UNET first, 1w) | 3815-4266ms | 5943-6677ms | 11718-12688ms | worse |
| unet_only | 1812-2375ms | 5579-6751ms | 11161-12534ms | worse (CLIP loads from vol) |
| **workers_2** | **2412-2570ms** | **4514-4772ms** | **10279-10373ms** | **BEST** |
| workers_1 | 3734-5637ms | 5800-7910ms | 11459-13926ms | worse |
| vae (add VAE) | 2589-2845ms | 4687-5192ms | 10538-11118ms | neutral |

Conclusion: `workers_2` is the best — enough parallelism for FUSE I/O without excessive thread contention.

### Experiment 2 — t8b_to_t9 breakdown

| Component | Before (ms) | After (ms) |
|-----------|-------------|------------|
| save_last_model_stack | 370-396 | 2.5-3.4 |
| diagnostics | 0.2 | 0.6-1.0 |
| profile print | 0.1 | 0.1-0.2 |
| enrich | 0.0 | 0.0-0.1 |
| diag_print | 0.0 | 0.1-0.4 |
| **Total t8b_to_t9** | **370-396** | **3.7-4.8** |

Root cause: `vol.commit()` in `_save_last_model_stack()` is a synchronous network round-trip to Modal's volume service (~370ms). Fix: background thread.

### Experiment 3 — CLIP encode warmup toggle

| Config | warmup_direct | restore_total | clip_encode(real) | net |
|--------|---------------|---------------|-------------------|-----|
| WCE=1 (warmup) | ~1690ms | ~4772ms | ~0.2ms | ~4970ms |
| WCE=0 (skip) | ~670ms | ~4020ms | ~900ms | ~4920ms |

Net neutral (~50ms difference). Keeping WCE=0 since it makes restore shorter (better cold-time metric).

## Remaining Variances
- Preload variance: 2.4-4.2s (FUSE volume I/O variability)
- GPU snapshot restore cost: ~300-400ms (unavoidable)
- Modal platform overhead: 7-10s (network + container scheduling)
- graph_overhead: ~500-700ms (stable, not inspected)
