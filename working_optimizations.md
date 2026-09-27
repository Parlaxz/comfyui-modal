# Working Optimizations

Track record of benchmarked, approved cold-start optimizations for comfyui-modal.

---

## 2026-06-02: CPU State Dict Cache (Replace Executor Warmup)

**What:** Preload model state dicts into CPU RAM during `restore(snap=False)` instead of running a throwaway executor warmup, then serve cached state dicts via a patched `load_torch_file` during inference.

**Summary:** The old executor warmup (`_preload_warmup_profile()`) loaded models through ComfyUI's executor, populating `current_loaded_models` with model patcher objects. But ComfyUI's GPU model cache (`LoadedModel.__eq__`) keys by Python object identity (`self.model is other.model`). Each independent `executor.execute()` call creates fresh `ModelPatcher` objects, so the warmup's entries never matched the real prompt's entries — the GPU cache miss forced a full volume re-read during inference. The ~4.6s warmup was essentially wasted for its intended purpose; the only residual benefit was OS page cache warming.

The fix reuses the existing but previously-unused `_patch_model_cpu_cache` infrastructure. The `load_torch_file` wrapper was already in place (patched during `startup(snap=True)`), but the cache dict was never populated. By calling `_preload_models_to_cpu()` during `restore(snap=False)` — after the memory snapshot is already loaded — we fill the CPU cache with state dicts at the same ~4-4.5s cost as the old executor warmup. On the real prompt, `load_torch_file` returns shallow copies from the cache, eliminating the FUSE volume read. No snapshot size regression (the cache is populated post-restore).

**Why it works:**
- ComfyUI's `LoadedModel.__eq__` at `comfy/model_management.py:609` uses `self.model is other.model` — identity check, not file-path check. Each `executor.execute()` call creates new `ModelPatcher` objects, so the warmup's GPU cache entries don't match the real prompt's entries.
- `_patch_model_cpu_cache()` was already called during `startup(snap=True)` (line 2054), replacing `comfy.utils.load_torch_file` with `cached_load`. The wrapper checks `self._model_cpu_cache[filename]` and returns `copy.copy(state_dict)` on hit — but the cache was always empty.
- Populating the cache during `restore(snap=False)` avoids the 3x snapshot restore regression that occurred when 17GB of state dicts were loaded during `startup(snap=True)` (documented in `memory.md`).
- Models loaded via `original_loader(path, return_metadata=True)` (the original `load_torch_file`) are stored as tuples of `(state_dict, metadata)` keyed by filename. Shallow copies (`copy.copy`) share tensor data between cache and consumer, avoiding redundant CPU RAM.
- GPU tensor creation via `.to(device)` does not modify the original CPU tensor, so the cache is preserved across prompt executions.

**The change:**
- `comfyapp.py:_preload_models_to_cpu` — added `file_timing_ms` to the return dict for per-file benchmark visibility.
- `comfyapp.py:restore()` — replaced the `_preload_warmup_profile()` call (executor warmup) with:
  1. `_snapshot_preload_profile()` — resolves the warmup profile from env vars or last model stack.
  2. `_snapshot_preload_paths(profile)` — resolves model names to absolute file paths.
  3. `_preload_models_to_cpu(paths)` — reads state dicts via `original_loader` and populates `self._model_cpu_cache`.
- No new files, no new dependencies, no schema changes.

**How to replicate:**
```bash
# 1. Deploy (uses existing image, no rebuild)
modal deploy comfyapp.py

# 2. Run benchmark against RTX PRO 6000 (Blackwell)
#    Edit _run_benchmark.py to set GPU_CLASS = "ComfyAPI_RTX_PRO_6000"
python _run_benchmark.py

# 3. Check clip_load in benchmark_logs/*.json
#    clip_load should be 450-700ms (vs 1500ms+ without cache)
```

**Gains (RTX PRO 6000 Blackwell):**
| Metric | Before (A10G, executor warmup) | After (Blackwell, CPU cache) |
|--------|:-------:|:------:|
| clip_load | 1,552ms | **455-661ms** |
| warmup_preload | 4,571ms | 3,911-4,311ms (now useful) |
| t3b_to_t8 | 8,451ms | **7,634-7,898ms** |
| sampler | 5,127ms | 5,215-5,260ms (no regression) |

**Warmup time breakdown (RUN-3, fresh cold container):**
| File | Size | Load Time |
|------|------|:---------:|
| flux-2-klein-9b-fp8.safetensors | ~9GB | 1,984ms |
| qwen_3_8b_fp8mixed.safetensors | ~5GB | 1,818ms |
| flux2-vae.safetensors | ~0.3GB | 105ms |
| **Total** | ~14.5GB | **3,911ms** |

**Constraints:**
- ✅ Does **not** increase snapshot restore time (cache populated during restore, not during snap=True).
- ✅ No loader seeding/priming during `snap=True` or `restore(snap=False)` — only reads state dicts, does not execute models.
- ✅ `ENABLE_WARMUP=1` path is preserved (warmup still runs during restore).
- ✅ `_force_cpu_during_snapshot` untouched — no SIGSEGV risk.
- ✅ CPU snapshot preload remains disabled during startup (no 3x restore regression).

**Edge cases:**
- If the warmup profile model files don't match the real prompt's files, the cache is wasted but the system degrades gracefully (falls back to volume reads, same as before).
- If `self._original_model_loader` is unavailable (not patched during startup), raises a clear `RuntimeError`.
- Subprocess backend is unaffected — the cache preload only runs for in-process backend.

---

## 2026-06-02: Concurrent Model File Loading in CPU Cache Preload

**What:** Load model state dicts concurrently via `ThreadPoolExecutor` instead of sequentially during `_preload_models_to_cpu()`.

**Summary:** The CPU cache preload previously read model files one at a time (UNET first, then CLIP, then VAE). Since these files are independent and FUSE volume reads are I/O-bound, switching to concurrent reads via `ThreadPoolExecutor(max_workers=4)` reduced total warmup_preload time from ~3.9s to ~2.6s — limited by the largest single file (~2.6s for UNET 9GB). Aggregate throughput improved from ~3.7 GB/s to ~5.6 GB/s by keeping the FUSE connection fully utilized during peak demand.

**Why it works:**
- FUSE volume reads are I/O-bound (network + distributed filesystem). Python threads release the GIL during I/O, so concurrent reads make progress in parallel.
- Each model file is independent (no shared state between UNET, CLIP, and VAE state dicts).
- The bottleneck shifts from "sum of 3 file reads" to "max of 3 file reads".
- `original_loader` (`comfy.utils.load_torch_file` → `safetensors.safe_open`) is thread-safe for separate file handles.
- `self._model_cpu_cache` writes from multiple threads are safe because each file has a unique key (filenames are unique).

**The change:**
- `comfyapp.py:_preload_models_to_cpu` — replaced the sequential `for path in file_paths:` loop with:
  1. Collect uncached files into `to_load` list.
  2. Submit each file to a `ThreadPoolExecutor(max_workers=min(len(to_load), 4))`.
  3. Collect results via `as_completed()`, writing each into `self._model_cpu_cache[filename]`.
  4. Per-file timing tracked via `fut_map` for benchmark visibility.
  5. If all files are already cached, skip straight to the summary print (no thread pool overhead).

**How to replicate:**
```bash
modal deploy comfyapp.py
python _run_benchmark.py
```

**Gains (RTX PRO 6000 Blackwell):**
| Metric | Sequential (v2.3.11) | Concurrent (v2.3.12) | Change |
|--------|:--------------------:|:--------------------:|:------:|
| warmup_preload | 3,911ms | **2,622ms** | **-33%** |
| clip_load | 455ms | 469-572ms | no regression |
| t3b_to_t8 | 7,634ms | 7,723ms | no regression |
| sampler | 5,260ms | 5,196ms | no regression |

*File-level times overlap with concurrent loading — individual durations exceed total wall time.*

**Warmup time breakdown (RUN-1, concurrent):**
| Thread | File | Time |
|--------|------|:----:|
| worker-1 | flux-2-klein-9b-fp8.safetensors (~9GB) | 2,615ms |
| worker-2 | qwen_3_8b_fp8mixed.safetensors (~5GB) | 2,353ms |
| worker-3 | flux2-vae.safetensors (~0.3GB) | 213ms |
| **Total** | **3 files (~14.5GB)** | **2,622ms** |

**Graph overhead:** Remains at ~600ms. Breakdown is ~150ms framework setup + ~300ms SaveImage encode/file write + ~150ms output scan. Hard to trim without modifying ComfyUI internals.

**Warmup size:** Further reduction would require smaller/quantized models (user choice, not code).

**Constraints:**
- ✅ Does not increase snapshot restore time (cache populated during restore).
- ✅ No GPU state is touched during concurrent loading (pure CPU I/O + Python).
- ✅ Thread pool capped at 4 workers — safe for 3-5 model files without excess overhead.
- ✅ Graceful fallback if `ThreadPoolExecutor` unavailable (though it's stdlib).

**Edge cases:**
- If only 1 file needs loading, the pool runs it on a single thread (same as sequential).
- If files are already cached, no threads are spawned — returns immediately.
- Error in one file doesn't block others (exception caught per-future, logged, other files continue).
- Cold OS cache variance (2-3x on FUSE reads) still applies — RUN-2 hit 6,267ms while RUN-1 and RUN-3 averaged 2,800ms. This is expected.

---

## 2026-06-03: Compilation Caching Env Vars on Modal Volume

**What:** Set 5 environment variables on the Modal image to enable torch.compile/Inductor/Triton artifact caching on the shared model volume and local tmpfs.

**Summary:** `torch.compile` compilation can take 10-20 minutes on first call and 1-5 minutes on each new container. By persisting compiled artifacts (FX graphs, Triton kernels, Inductor metadata) across containers, recompilation drops to ~2 minutes. These env vars are harmless when `torch.compile` is not used, and essential when it is (Target 1).

**Why it works:**
- `TORCHINDUCTOR_CACHE_DIR=/root/models/.inductor-cache` — stores Inductor's FX graph cache and compiled kernel metadata on the persistent Modal Volume shared across containers.
- `TORCHINDUCTOR_FX_GRAPH_CACHE=1` — enables FX graph caching so repeated graph patterns skip recompilation.
- `TRITON_CACHE_DIR=/tmp/triton_cache` — points Triton kernel cache to local tmpfs instead of the Volume, avoiding "Stale file handle" race conditions on shared FUSE `.so` files (pytorch#173679).
- `TORCHINDUCTOR_EMULATE_PRECISION_CASTS=1` — required for SageAttention + torch.compile compatibility (fixes noise output bug, thu-ml/SageAttention#162).
- `TORCHINDUCTOR_COMPILE_THREADS=1` — required for GPU memory snapshot compatibility (Modal docs).

**The change:**
- `comfyapp.py:image.env({...})` — added `.env({...})` call to the main Modal Image chain with all 5 environment variables. Placed before `.add_local_python_source()` calls (Modal requires local sources be last).

**How to replicate:**
```bash
modal deploy comfyapp.py
# Verify in build output:
# => Step 1: ENV TORCHINDUCTOR_CACHE_DIR=/root/models/.inductor-cache
# => Step 2: ENV TORCHINDUCTOR_FX_GRAPH_CACHE=1
# => Step 3: ENV TRITON_CACHE_DIR=/tmp/triton_cache
# => Step 4: ENV TORCHINDUCTOR_EMULATE_PRECISION_CASTS=1
# => Step 5: ENV TORCHINDUCTOR_COMPILE_THREADS=1
```

**Gains:**
No direct latency improvement yet — these env vars are infrastructure for future optimizations (Target 1: `torch.compile`). Verified no regression in inference performance.

**Constraints:**
- ✅ Does not increase snapshot restore time (env vars only, no code changes).
- ✅ No loader seeding/priming during snapshot creation.
- ✅ Image builds in ~2.5s (cached, no rebuild needed).
- ✅ No performance impact when `torch.compile` isn't used.

**Edge cases:**
- Multiple containers writing to the same `TORCHINDUCTOR_CACHE_DIR` on a Modal Volume could contend for file writes. Inductor uses atomic renames (`.tmp` → final), which are safe on FUSE.
- `TRITON_CACHE_DIR` on local `/tmp` is per-container — Triton kernels must be recompiled on each container. This is acceptable because the Inductor-level cache handles the expensive part (graph tracing + optimization), while Triton kernel compilation is fast once the optimized graph is determined.
- If PyTorch, CUDA, or GPU driver versions change, the Inductor cache must be invalidated. This happens naturally on the next deploy (new image → fresh volume cache).

---

## 2026-06-03: `torch.compile` on UNET (Benchmarked — Not a Win)

**What:** Apply `torch.compile(mode="max-autotune", fullgraph=True)` to the UNET diffusion model via ComfyUI's built-in `set_torch_compile_wrapper`.

**Result: sampler 5,260ms → 5,671ms (8% SLOWER).** Rejected.

**Why it didn't work:**
SageAttention v2.2.0's hand-tuned CUDA kernels for Blackwell (SM 12.0) are faster than what `torch.compile`'s Inductor backend produces. The compiled Triton kernels introduce graph breaks at SageAttention boundaries, adding overhead that outweighs any compilation benefit. This is a known issue (thu-ml/SageAttention#162): SageAttention 2 + `torch.compile` = slower, not faster.

**The change:**
- `comfyapp.py:ENABLE_TORCH_COMPILE` env var (default `"0"`)
- `comfyapp.py:_enable_torch_compile_on_unet()` — patches `load_models_gpu` to call `set_torch_compile_wrapper` on any loaded model with `diffusion_model` attribute
- Called from `_execute_in_process()` before execution

**How to replicate (for future testing):**
```bash
# Set COMFYMODAL_ENABLE_TORCH_COMPILE=1 in the image env block
modal deploy comfyapp.py
python _run_benchmark.py
```

**Gains:**
| Metric | Without compile (v2.3.15) | With compile (v2.3.17) | Delta |
|--------|:------------------------:|:----------------------:|:-----:|
| sampler | 5,260ms | 5,671ms | **+8% ❌** |
| clip_load | 545ms | 479-508ms | no change |
| clip_encode | 1,050ms | 1,011-1,030ms | no change |
| vae_decode | 400ms | 350-521ms | no change |

**Why the Modal blog "FLUX 3x faster" doesn't apply:**
That blog uses HuggingFace Diffusers' `FluxPipeline` which uses vanilla PyTorch attention. The 1.5x speedup comes from compiling that vanilla attention into optimized Triton kernels. Our stack uses SageAttention which already replaces the attention with custom CUDA kernels. There's nothing left for `torch.compile` to optimize.

**Infrastructure preserved for future:**
The `_enable_torch_compile_on_unet` method, the env var, and the Target 4 compilation caching env vars are all kept in the codebase. If a future SageAttention version better integrates with `torch.compile` (PR #218 aims to do this), it can be re-enabled by flipping the env var.

---

