# Optimization Targets — June 3rd

---

## Target 0: `buffer_containers` (REJECTED)

**Source:** Modal blog "Truly serverless GPUs"

**What:** Add `buffer_containers=1` to `app.cls()` to keep a warm idle GPU container.

**Rejected by user:** Idle GPU containers have prohibitively high cost. Will never use.

---

## Target 0b: `CUDA_CACHE_PATH` env var

**Source:** Modal blog "FLUX 3x faster"

**What:** Set `CUDA_CACHE_PATH=/root/models/.nv_cache` on the Modal image. Caches JIT-compiled CUDA kernels at the driver level (separate from Inductor/Triton caches). The FLUX blog uses this alongside the Inductor and Triton caches.

**Expected Benefit:** Slight reduction in kernel launch overhead, especially useful when `torch.compile` is in use (since compiled kernels often trigger additional driver-level JIT).

**Effort:** 1 line — add to the `.env({...})` block.

**Issues:**
- Benefits are modest without active `torch.compile` usage
- On a FUSE Volume, concurrent writes to `.nv_cache` could have the same race conditions as Triton cache
- Safest to point to `/tmp/.nv_cache` on local disk to avoid FUSE issues

**Bottom Line:** Low effort, low risk. Add alongside existing env vars. Safe fallback to local disk to avoid FUSE races.

---

## Target 0c: `torch.compile` on VAE Decode Only

**Source:** Modal blog "FLUX 3x faster"

**What:** Apply `torch.compile` to the VAE decoder only (not the full UNET). The VAE decode path does NOT use SageAttention — it's a standard convolutional decoder. `torch.compile` on this path should give 1.3-1.5x speedup (400ms → ~270ms) without any SageAttention conflict.

**Why UNET compile failed vs VAE compile:**
- UNET: SageAttention v2.2.0's hand-tuned CUDA kernels for Blackwell (SM 12.0) are faster than `torch.compile`'s Inductor/Triton output → 8% SLOWER
- VAE: Standard conv ops with no SageAttention replacement → `torch.compile` should speed up

**Issues:**
- Would need to access ComfyUI's internal VAE model patcher, similar to how `_enable_torch_compile_on_unet()` patches `diffusion_model`
- Compilation time: first call pays ~10-20 min without cache; with compilation caching env vars → ~2 min on subsequent containers
- Potential precision issues with fp8/fp16 VAE (flux2-vae.safetensors is bf16 — should be fine)
- Modal's GPU snapshot could capture compiled VAE (if GPU snapshots are enabled)

**Bottom Line:** Worth testing. Use `mode="max-autotune-no-cudagraphs"` with `dynamic=True` (same as FLUX blog). Test on Blackwell (RTX PRO 6000) since that's the target GPU.

---

## Target 0d: Channels-Last Memory Layout

**Source:** Modal blog "FLUX 3x faster"

**What:** Apply `memory_format=torch.channels_last` to VAE and transformer model tensors. The blog converts both `pipe.transformer` and `pipe.vae` to channels-last layout. This improves data locality for convolution operations in the VAE and attention operations in the transformer.

**Expected Benefit:** ~5-10% memory bandwidth improvement on conv-heavy ops (VAE decode). Smaller benefit on transformer ops that are already memory-bandwidth optimized.

**Issues:**
- ComfyUI doesn't expose this natively on the model patcher — would need to patch the model tensors after loading
- Channels-last layout is persistent on the model object — if done during snap=True, it's captured in the snapshot
- Must be compatible with ComfyUI's weight loading path (some loaders may expect channels-first)
- Works best combined with `torch.compile` (the two optimizations compound)

**Bottom Line:** Low effort to test. Apply to VAE model during model load, verify output quality isn't affected.

## Target 1: `torch.compile` on UNET + VAE

**Source:** Modal blog "Run FLUX.1-dev three times faster", PyTorch blog "Presenting Flux Fast", SageAttention issues

**What:** Apply `torch.compile` to ComfyUI's UNET (diffusion model) and VAE decoder, combined with `fuse_qkv_projections()`, `channels_last` memory layout, and Inductor configuration tweaks.

### Expected Benefit

~1.5x speedup on sampler (5,260ms → ~3,500ms) and VAE decode (400ms → ~270ms). PyTorch's own Flux benchmark shows 6.7s → 4.5s on H100 (1.5x) with `torch.compile` and **no quality loss**. Regional compile (`compile_repeated_blocks`) gives the same runtime speedup but cuts compile latency from 67.4s → 9.6s.

### Issues Found

**1. SageAttention + torch.compile = noise output (CRITICAL)**
- Known bug (thu-ml/SageAttention#162, ComfyUI#8689). SageAttention 2 with `torch.compile` produces noise images.
- **Fix:** `TORCHINDUCTOR_EMULATE_PRECISION_CASTS=1` env var, OR use SageAttention 1.0.6 instead of v2, OR use the recently merged PR #218 that adds `torch.compile` support to SageAttention 2.
- SageAttention's INT8 quantization + fp16 accumulation + torch.compile compound the precision issue. Each trades precision for speed — combined they degrade quality.
- The SageAttention team's own fix involves passing `torch.cuda.getCurrentCUDAStream()` to kernel launches and forcing the online-softmax LSE accumulator to fp32.

**2. Graph breaks from SageAttention**
- `sageattn()` calls `torch.cuda.set_device()` and `get_cuda_arch_versions()` which cause graph breaks in torch.compile.
- A community patch (woct0rdho/SageAttention commit ea23d40) fixes this by treating arch detection as a constant.
- Without this patch, torch.compile silently falls back to eager mode on SageAttention-attended blocks — no speedup.

**3. LoRA incompatibility**
- `torch.compile` with LoRA produces output as if no LoRA was applied (ComfyUI#5375). The compiled graph doesn't pick up LoRA weight changes.
- With `dynamic=True`, LoRA weights changing shape between prompts triggers recompilation, hitting the recompile limit of 64 (ComfyUI#9289).

**4. `fuse_qkv_projections()` availability**
- Available on Hugging Face Diffusers `FluxPipeline`. ComfyUI's internal model patcher may not expose this method. Need to verify by inspecting the `ModelPatcher` object.
- If not available, the QKV fusion must be done manually or via a ComfyUI custom node.

**5. PyTorch version brittleness**
- PyTorch 2.7.1 + recent ComfyUI works for torch.compile.
- PyTorch 2.8.0 introduced compilation bugs that broke many ComfyUI workflows. Some fixed in nightly.
- PyTorch 2.10+cu130 seems to work well again (per ComfyUI#9647 comments).
- We're on CUDA 13.0 + PyTorch from `cu130` index — need to verify torch.compile actually works.

**6. Compilation time**
- Full graph compile (`fullgraph=True, mode="max-autotune"`): 10-20 minutes on first call.
- Regional compile (`compile_repeated_blocks`): 9.6s cold, 2.4s warm (PyTorch blog, 2026).
- Without compile caching on a Volume, every container pays this cost.

### Bottom Line

Lowest risk path: set `TORCHINDUCTOR_EMULATE_PRECISION_CASTS=1`, use SageAttention 1.0.6 as base (not v2), and apply `compile_repeated_blocks` on the UNET only (not VAE). The modal-blog Flux example also uses `conv_1x1_as_mm=True`, `coordinate_descent_tuning=True`, `epilogue_fusion=False`. But SageAttention 1.0.6 is pure Triton and slower than v2 on Blackwell — we'd lose SageAttention speedup while gaining torch.compile speedup. Net effect unclear without testing.

---

## Target 2: GPU Memory Snapshots (SageAttention SIGSEGV Fix) — IMPLEMENTED June 2026

**Source:** Modal blogs "GPU Memory Snapshots" and "Truly serverless GPUs", Modal docs, vLLM blog post on weight caching

**Status:** Code implemented. Gated by `COMFYMODAL_ENABLE_GPU_SNAPSHOT=1` env var. Awaiting benchmark.

**What:** Use Modal's `enable_gpu_snapshot=True` to capture ComfyUI's GPU state (CUDA context, compiled kernels) in the memory snapshot. Previously blocked because SageAttention's C extensions called CUDA driver APIs directly in `PyInit_*` → dangling pointers on restore → SIGSEGV.

**Solution:** Created `_force_triton_during_snapshot()` context manager that:
1. Blocks SageAttention C extension imports via `sys.meta_path` (same as `_force_cpu_during_snapshot`)
2. Does NOT monkey-patch `torch.cuda.is_available` → ComfyUI detects and inits with GPU
3. Sets `comfy.cli_args.args.cpu = False` explicitly
4. SageAttention falls back to Triton path (torch CUDA APIs, Modal-checkpointable)

On restore, `_select_sage_runtime_mode()` detects baked CUDA available and switches to the CUDA path.

**Changes:**
- `ENABLE_GPU_SNAPSHOT` env var (default `"0"`)
- `_force_triton_during_snapshot()` context manager (~60 lines)
- `startup()` branches on `ENABLE_GPU_SNAPSHOT` to use triton path
- `restore()` skips `_restore_in_process_gpu_state()` when GPU snapshot used
- `_register_gpu_classes()` conditionally passes `experimental_options={"enable_gpu_snapshot": True}`
- memory.md updated with full documentation

**Expected Benefit (Phase 1, no model preload):**
- Skip `_restore_in_process_gpu_state()` → save ~few ms
- `_warmup_cuda()` faster (Modal restores CUDA context directly) → save ~50-200ms
- Total restore: ~3.0s → ~2.0-2.5s

**Future (Phase 2, model preload during snap=True):**
- Preload models into GPU during snap=True → capture in snapshot
- Eliminates warmup_preload (~2.7s) from restore path
- Restore total: ~3.0s → ~0.5s (matching Modal's 10x speedup claims)
- **Risk:** Snapshot size 5GB → 22GB, cold blob restore ~50s vs ~2.3s
- **Decision:** Hold until Phase 1 is proven stable. User constraint: "only pursue optimizations that do not increase snapshot restore time."

---

## Target 3: ComfyUI Node Output Caching

**Source:** ComfyUI `execution.py`, `comfy_execution/caching.py`, ComfyUI issues

**What:** Get ComfyUI's node output cache to actually persist the CLIPLoader node's output across executions, so the CLIP model isn't rebuilt from the state dict on every prompt.

### Expected Benefit

clip_load from ~545ms → ~5ms (just cache lookup for the CLIPLoader output). The cache key is the node's input signature (clip_name, type) — since these don't change between prompts, the cached CLIP model object should be reused.

### Issues Found

**1. The cache is ALREADY enabled — it's not hitting (SURPRISE)**
- We pass `cache_type=False` to `PromptExecutor.__init__`, which evaluates to `CacheType.CLASSIC` (the else branch in `CacheSet.__init__`). This enables `HierarchicalCache` — it's NOT disabled.
- The `HierarchicalCache` with `CacheKeySetInputSignature` SHOULD cache CLIPLoader outputs between executions with the same inputs.
- The fact that clip_load is 545ms every time means the cache is NOT hitting, despite being enabled.

**2. `IS_CHANGED` may bypass caching**
- In `execution.py`, when a node has `IS_CHANGED` defined, the cache is bypassed: *"Intentionally do not use cached outputs here. We only want constants"*.
- CLIPLoader likely doesn't have `IS_CHANGED`, but we should verify.
- Also: `fingerprint_inputs` is checked first — if the node class has this method overriding the default, it may invalidate cache on every call.

**3. Cache key includes node ID**
- `CacheKeySetInputSignature` generates a key from the node's input values. The key is scoped to the specific node ID (e.g., "256").
- If the workflow graph changes between prompts (e.g., node IDs shift), the old cache entry won't match even with identical inputs.
- For repeated prompts with the same workflow (our benchmark), node IDs are stable — this shouldn't be the issue.

**4. Subcache invalidation**
- `HierarchicalCache.set_prompt()` creates subcaches for each node's children. If the subcache structure changes between prompts, old entries are orphaned.
- The subcache key is derived from `CacheKeySetInputSignature.get_subcache_key(node_id)`. If this changes between prompts (unlikely for the same workflow), the cache misses.

**5. Potential fix: pre-warm the CLIPLoader node**
- Instead of relying on the cache, we could pre-execute the CLIPLoader node during warmup and store its output in the cache directly.
- This requires calling `caches.outputs.set(node_id, value)` with the pre-computed CLIP model output.
- The executor would then find the cached output and skip executing CLIPLoader on the real prompt.

### Bottom Line

The cache IS enabled but NOT hitting. The exact reason needs investigation: check if `IS_CHANGED` or `fingerprint_inputs` is causing the miss, or if subcache keys change between prompts. If we can identify and fix the miss, clip_load drops from 545ms to ~5ms. If not, a custom pre-warm of the CLIPLoader cache entry during warmup is a workable fallback.

---

## Target 4: Compilation Caching Env Vars on Modal Volume

**Source:** Modal blog ("FLUX 3x faster"), Modal docs, PyTorch docs, vLLM caching blog, fal.ai docs

**What:** Set `TORCHINDUCTOR_CACHE_DIR`, `TRITON_CACHE_DIR`, and related env vars on the Modal image so `torch.compile` artifacts are persisted to the model volume and shared across containers. Without this, torch.compile is impractical (10-20 minute recompilation per container).

### Expected Benefit

Reduces `torch.compile` recompilation from 10-20 minutes → ~2 minutes on subsequent containers (per Modal blog and fal.ai benchmarks).

### Issues Found

**1. Race conditions on FUSE (Modal Volume) — CRITICAL**
- Modal Volumes are FUSE mounts. When multiple containers write to the same Triton cache path, "Stale file handle" and "Device or resource busy" errors are reported (pytorch#173679, triton-lang/triton#9368).
- These occur when one container reads a `.so` file while another is overwriting it.
- **Fix:** Set `TRITON_CACHE_DIR` to a local path (`/tmp/triton_cache`) and use a sync mechanism to share artifacts. OR use `TORCHINDUCTOR_CACHE_DIR` which uses atomic renames (`.tmp` → final) that are safer on FUSE.

**2. Cache invalidation on version changes**
- torch.compile artifacts are specific to: GPU architecture, driver version, CUDA version, PyTorch version, triton version.
- Any of these changing invalidates the entire cache.
- The vLLM blog recommends **separate Volumes** for weight cache vs compile cache, so clearing the compile cache doesn't affect weights.
- **Recommendation:** Use separate subdirectory on the existing models volume (`/root/models/.inductor-cache`), or create a dedicated volume.

**3. Non-determinism with shared TRITON_CACHE_DIR**
- Triton autotuning is non-deterministic by design — it profiles multiple kernel configurations and selects the fastest. Cached autotune results may differ between runs (triton-lang/triton#9368).
- This can cause run-to-run variation in output images (bitwise non-determinism).
- **Mitigation:** Use `TORCHINDUCTOR_MAX_AUTOTUNE=0` to disable autotuning, at the cost of some performance.

**4. Disk space growth**
- Inductor cache can grow to hundreds of MB to GB over time as different graphs and shapes are compiled.
- On a shared Volume with model files (14.5GB), this is manageable but should be monitored.
- **Mitigation:** Occasional manual cleanup, or set `TORCHINDUCTOR_CACHE_DIR` to a separate Volume.

**5. Recommended env var combination**
```python
image = image.env({
    "TORCHINDUCTOR_CACHE_DIR": "/root/models/.inductor-cache",
    "TORCHINDUCTOR_FX_GRAPH_CACHE": "1",
    "TRITON_CACHE_DIR": "/tmp/triton_cache",  # local to avoid FUSE races
    "TORCHINDUCTOR_EMULATE_PRECISION_CASTS": "1",  # needed for SageAttention + compile
    "TORCHINDUCTOR_COMPILE_THREADS": "1",  # helps GPU snapshot compatibility
})
```
Note: `TORCHINDUCTOR_FX_GRAPH_CACHE=1` stores FX graph cache in the same `TORCHINDUCTOR_CACHE_DIR` location. The `TRITON_CACHE_DIR` pointing to local disk avoids FUSE race conditions on the .so files. The inductor cache dir on the Volume handles the higher-level graph cache and metadata.

### Bottom Line

Lowest risk target. Just env vars — no code changes. The FUSE race condition on Triton `.so` files is the main concern, solved by pointing `TRITON_CACHE_DIR` to local `/tmp`. Recommended to implement this BEFORE any torch.compile work (Target 1), since torch.compile is impractical without it. Can also be done independently — the env vars are harmless if torch.compile is never called.
