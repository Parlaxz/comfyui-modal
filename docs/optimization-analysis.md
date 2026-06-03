# Optimization Analysis — Full Cold-Start Breakdown

> Baseline from instrumented run data. Document for planning optimization strategy.

---

## Baseline Breakdown (L40S)

| Phase | Time | % of total | Priority |
|-------|------|-----------|----------|
| `restore()` subtotal | **~9,375ms** | **42%** | **Our code** |
| └─ `warmup_preload` (model loading + inference) | ~7,810ms | 35% | **#1** |
| └─ `sage_runtime` (mode select + verify) | ~1,214ms | 5% | #2 |
| └─ `cuda_warmup` (context sync + GEMM) | ~194ms | 1% | |
| └─ `gpu_state` (ComfyUI GPU mode flip) | ~162ms | 1% | |
| **Inference** (clip | sampler | vae) | **~5,087ms** | **23%** | |
| └─ sampler | ~4,574ms | 20% | |
| └─ clip_encode | ~222ms | 1% | |
| └─ vae_decode | ~291ms | 1% | |

**Primary metric for any optimization:** `t3b_to_t8` (validate-done to outputs-written). This captures restore + warmup + inference in one number. Isolated section improvements that make total time worse are regressions.

---

## Option 1: FLATTEN — Parallel Model Loading

**Load UNET and CLIP models in parallel threads instead of sequential workflow execution.**

**Estimated saving:** ~2,000-3,000ms on warmup_preload (bounded by single largest file).

**Risk:** FUSE volume may not support parallel reads efficiently. GPU memory spike (9GB + 8GB = 17GB, fine on 80GB+ GPUs).

**Complexity:** Moderate.

---

## Option 2: REWARM — Skip Warmup Entirely

**Remove `_preload_warmup_profile()` from `restore()`. Let the first prompt load models lazily.**

**Estimated saving:** ~0ms on total wall clock (wash). Restore drops by 7.8s, first prompt increases by ~8s.

**Time displaced:** YES — 7.8s moves from restore to first inference. Total unchanged.

**Risk:** None.

---

## Option 3: UNLOAD — Remove VAE + Inference from Warmup

**Stop the warmup workflow after UNETLoader and CLIPLoader. Drop VAE, CLIPTextEncode, Sampler, VAEDecode.**

**Estimated saving:** Unknown — depends on whether warmup-loaded models are found in cache during real prompt. If cache miss, warmup savings are offset by inference penalty.

**Risk:** CLIP model cache mismatch between warmup and real prompt loader (different loader types or parameters) can negate savings.

**Complexity:** Trivial.

---

## Option 4: CACHE_SAGE — Persist Sage Runtime Mode to Volume

**After sage runtime mode is verified, cache it to volume. On next restore, skip re-verification.**

**Estimated saving:** ~1,000ms.

**Risk:** Low — cache keyed by GPU name + sage version; stale cache detected automatically.

**Complexity:** Low.

---

## Option 5: SKIP_SAGE — Hardcode Sage Runtime Mode

**Skip all sage verification. Hardcode `baked_cuda` for known GPUs.**

**Estimated saving:** ~1,200ms.

**Risk:** If GPU or sage version changes, wrong mode may cause slower inference.

**Complexity:** Trivial.

---

## Option 6: NETWORK_COMPRESS — JPEG Output

**Use JPEG (quality 90%) instead of PNG for output transfer.**

**Estimated saving:** 0-500ms on network transfer.

**Risk:** Lossy compression.

---

## Top Candidates (Testing Order)

| Order | Option | Target | Est. Saving |
|-------|--------|--------|-------------|
| 1 | **UNLOAD** | warmup_preload (~7.8s) | Depends on CLIP cache |
| 2 | **CACHE_SAGE** | sage_runtime (~1.2s) | ~1,000ms |
| 3 | **FLATTEN** | warmup_preload (~7.8s) | ~2,000-3,000ms |
| 4 | **SKIP_SAGE** | sage_runtime (~1.2s) | ~1,200ms |
| 5 | **REWARM** | entire restore | ~0ms (wash) |
