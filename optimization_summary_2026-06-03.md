# Optimization Summary — June 3rd, 2026

## Best Wall Clock: 17.7s (from 20.9s baseline)

## Changes Deployed

| Change | File | Status | Savings |
|--------|------|--------|---------|
| `_patch_model_cache_comparison` — patched `LoadedModel.__eq__` from identity to class+size+device (with model_type fallback for CLIP) | `comfyapp.py:2637` | LIVE | clip_load -91ms, clip_encode -92ms |
| Warmup workflow — runs model-loading nodes via executor after CPU preload | `comfyapp.py:2884` | LIVE | GPU cache populated for real prompt |
| `_force_triton_during_snapshot` — blocks SageAttention C extensions, allows GPU init | `comfyapp.py:2098` | GATED | Usable if GPU snapshots ever enabled |
| Sage runtime mode in restore_timing | `comfyapp.py:2835` | LIVE | Diagnostic value only |
| Memory allocator warmup in `_warmup_cuda` | `comfyapp.py:2600` | LIVE | 512MB alloc+zero (~19ms) |
| Warmup profile env vars in image | `comfyapp.py env block` | LIVE | Resolves warmup profile for both startup and restore |
| `ENABLE_GPU_SNAPSHOT` env var | `comfyapp.py:21` | LIVE, OFF | Gates GPU snapshot path |

## 17.7s Breakdown (best RUN-3)

```
Phase                    Time      %      Notes
────────────────────────────────────────────────────
Modal restore           ~3,500ms  19.8%  Outside our control, varies 3-6s
gpu_state                 246ms    1.4%  _restore_in_process_gpu_state
cuda_warmup                75ms    0.4%  sync+GEMMs+alloc
sage_runtime               18ms    0.1%  cache hit → skip verification
warmup_preload          2,875ms   16.3%  17GB concurrent FUSE read
warmup_wf                 734ms    4.2%  executor model loading
clip_load                 440ms    2.5%  CLIP model from GPU cache hit
clip_encode             1,026ms    5.8%  Qwen 8B text encoder
sampler                 5,174ms   29.3%  20-step Flux, SageAttention baked_cuda
vae_decode                377ms    2.1%  VAE decoder
graph_overhead            429ms    2.4%  executor wiring
network/other            ~2,806ms  15.9%  Modal routing + client RTT
────────────────────────────────────────────────────
Total                  ~17,700ms
```

## What Was Tried and Rejected

| Approach | Wall Clock | Issue |
|----------|-----------|-------|
| GPU snapshots (CUDA checkpoint) | 44-54s | `cuCheckpointProcessCheckpoint` copies ALL GPU VRAM pages (96GB on Blackwell) |
| GPU snapshots + subprocess | 54s | Same VRAM dump problem; inference slower (HTTP overhead) |
| Subprocess backend alone | ~12s theory | GPU snapshot restore dominated by decompress; inference slower |
| `torch.compile` on UNET | +8% on sampler | SageAttention CUDA kernels faster than compiled Triton |
| SageAttention warmup | 0 benefit | Pre-compiled .so files, no JIT cost to pay |
| Direct node warmup (no executor) | 1002ms | Executor was actually faster (652ms) |
| TeaCache / FBCache | — | User rejected |

## Key Insights

1. **`LoadedModel.__eq__` was the critical fix.** Without it, warmup GPU cache entries are never reused. The model_type fallback handles CLIPLoader vs DualCLIPWrapper differences.

2. **warmup_preload (2.9s) is the hard floor.** FUSE volume read of 17GB at ~6 GB/s is fundamental. The only way past it is:
   - Models in Docker image (page cache survives gVisor checkpoint/restore)
   - Accept that warm NVMe restores are fast and cold blobs are slow

3. **GPU snapshots are wrong for weight-loading workloads.** Modal's own docs: *"if the majority of your initialization latency is spent loading weights, GPU Memory Snapshots will generally not improve your cold start times."*

4. **The 40% inference speedup in the early GPU snapshot test was from different physical GPU nodes**, not from the snapshot mechanism.

## Optimization Audit (from `optimization_audit_2026-06-03.md`)

Junior identified 7 findings. 3 correct, 2 wrong, 2 moot:

| # | Finding | Verdict | Implemented? |
|---|---------|---------|--------------|
| 1 | Parallelize FUSE stat calls | WRONG (1ms) | Not needed |
| 2 | Overlap path resolution with CUDA warmup | WRONG (1ms) | Not needed |
| 3 | CLIP cache miss in __eq__ | **CORRECT** | ✅ Fixed (model_type fallback) |
| 4 | Warmup WF bypass executor | CORRECT but executor was faster | Not beneficial |
| 5 | Redundant profile load | CORRECT but 1ms | Not worth |
| 6 | Skip VAE preload | WRONG (0.3GB, used by inference) | Not needed |
| 7 | Skip profiling infra in warmup | CORRECT but moot with executor | Not implemented |

## Recommendations for Further Gains

### Short-term code-only (estimated ~2-3s):
- Break warmup_wf into sub-phases with direct profiling to see where the 734ms goes
- Add granular timing to every step inside `_execute_in_process` for the warmup path
- Profile `_snapshot_preload_paths` per-check under cold FUSE conditions

### Medium-term (requires modal or model changes):
- Models in Docker image → warmup_preload drops from 2.9s → ~0.5s (page cache survives snapshot)
- Accept warm NVMe restore variance (best case hits 12s)

### Long-term (when ComfyUI gets sleep mode):
- Revisit GPU snapshots with weight offloading (vLLM sleep/SGLang release pattern)
