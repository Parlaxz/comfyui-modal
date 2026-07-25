# UNET Snapshot Dtype Fix Report

## Root Cause

The CPU snapshot UNET construction path and the normal loader path both called
`UNETLoader.load_unet(unet_name, "default")`, but the `"default"` string resolved
to **different effective dtypes** depending on execution context:

| Path | Context | `unet_dtype()` result | Effective dtype |
|---|---|---|---|
| Normal loader (GPU) | CUDA available, `args.cpu=False` | `should_use_bf16(None,...)=True` | `torch.bfloat16` |
| CPU snapshot | `_force_cpu_during_snapshot` patches CUDA | `cpu_mode()=True` → BF16 skipped | `torch.float32` |

The chain is:

1. `UNETLoader.load_unet(unet_name, "default")` sets empty `model_options` (no `"dtype"` key).
2. `load_diffusion_model_state_dict` calls `model_management.unet_dtype()` which auto-detects
   the inference dtype.
3. `unet_dtype()` → `should_use_bf16()` → checks `cpu_mode()`.
4. During CPU snapshot, `_force_cpu_during_snapshot` sets `comfy.cli_args.args.cpu = True`,
   making `cpu_mode()` return `True` → `should_use_bf16()` returns `False`.
5. Result: UNET created with FP32 weights → runs FP32 on GPU → ~20.6s sampler time.

The `requested_weight_dtype="default"` string was **not wrong** by itself — the
bug was that both paths used the same string but the **resolution of that string
depended on context** that differed between the two paths.

## Files Changed

| File | Change |
|---|---|
| `comfymodal_runtime/model_preload.py` | Added `_gpu_bf16_supported()`, `cache_gpu_bf16_support()`, `resolve_unet_effective_dtype()`. Updated `V2LoaderBridge._load_unet` to log `effective_weight_dtype`. |
| `comfymodal_runtime/modal_app.py` | Modified `_cpu_load_unet` to use the shared resolver and explicitly set `model_options["dtype"]` when the effective dtype differs from "default". Updated `snapshot_created` runtime state to include `effective_weight_dtype`. |
| `docs/unet_snapshot_dtype_fix_report.md` | This report. |

### `model_preload.py` — New Functions

- **`_gpu_bf16_supported()`** — Checks if the GPU supports bfloat16, with a
  module-level cache (`_CACHED_GPU_BF16_SUPPORT`) so the answer is captured once.
- **`cache_gpu_bf16_support()`** — Public API to prime the cache *before* a
  CPU-snapshot context hides CUDA. Returns the cached value.
- **`resolve_unet_effective_dtype(weight_dtype_str)`** — Shared resolver that
  returns `(torch_dtype | None, label)`. For `"default"`, determines what the
  normal GPU path would use (not the CPU-snapshot path). Checks CLI flags first,
  then GPU BF16 capability. Used by **both** the snapshot and normal loader paths.

### `modal_app.py` — Modified `_cpu_load_unet`

Before entering `_force_cpu_during_snapshot()`, `cache_gpu_bf16_support()` is
called to capture the real GPU BF16 status. Inside `_cpu_load_unet`, when
`weight_dtype == "default"` and the resolved dtype is not FP32 (i.e., BF16),
the function calls `load_diffusion_model(unet_path, model_options={"dtype": bf16})`
directly, bypassing the ComfyUI auto-detection that would choose FP32 on CPU.

This is **construction-time** BF16 — the model parameters are created in BF16
during snapshot construction, not cast afterward.

## Why the Previous Behavior Was Wrong

The `requested_weight_dtype="default"` string was treated as a **pass-through**
value that relied on implicit context-dependent auto-detection. When the snapshot
and normal paths ran in different CUDA/CliArgs contexts, they got different
results from the same string. The string alone was not a sufficient contract
between the two paths.

## How the Shared Resolver Fixes It

`resolve_unet_effective_dtype()` is the single source of truth for dtype
resolution. Both paths call it:

```
  Snapshot path: _cpu_load_unet
       normal path: V2LoaderBridge._load_unet (for logging)
                \         /
                 \       /
          resolve_unet_effective_dtype()
                      |
          GPU BF16 support (cached once)
          CLI flags (checked always)
                      |
           Returns deterministic dtype
```

The GPU BF16 capability is cached at module level and primed before the snapshot
context hides it, so the resolver returns the same answer regardless of context.

## Test Results

### New tests (5 added to `tests/test_cpu_snapshot_models.py`):

| Test | What it verifies |
|---|---|
| `test_unet_effective_dtype_resolver_default` | `resolve_unet_effective_dtype("default")` returns a concrete dtype (BF16 or FP32 depending on hardware) |
| `test_unet_effective_dtype_explicit_fp8` | fp8 strings resolve to correct torch dtype (or None if unsupported) |
| `test_unet_effective_dtype_explicit_fp8_e5m2` | fp8_e5m2 resolves correctly |
| `test_unet_effective_dtype_unknown_string` | Unknown strings return `(None, string)` |
| `test_unet_effective_dtype_cache_gpu_bf16` | `cache_gpu_bf16_support()` returns a bool |

### Existing test results (all pass):

| Test file | Count | Status |
|---|---|---|
| `test_cpu_snapshot_models.py` | 86 | PASS |
| `test_v2_cpu_snapshot_lifecycle.py` | 136 | PASS |
| `test_v2_snapshot_model_bridge.py` | 9 | PASS |
| `test_v2_unet_runtime_ab.py` | 51 | PASS |
| `test_model_preload_critical_path.py` | 83 | PASS |
| `test_model_preload_attribution.py` | 38 | PASS |
| `test_model_preload_prefill_overlap.py` | 49 | PASS |
| **Total** | **452** | **ALL PASS** |

## Manual Validation Required After Deploy

1. Deploy via existing batch workflow (no special flags).
2. Confirm snapshot-backed run works without `--benchmark` flags.
3. Verify sampler time drops from ~20.6s to ~4s (BF16 parity with normal path).
4. Check logs for:
   - `[v2.unet_runtime_state] stage=snapshot_created ... effective_weight_dtype=bfloat16`
   - `[v2.unet_runtime_state] stage=normal_loader_ready ... effective_weight_dtype=bfloat16`
   - First forward shows BF16 on CUDA (not FP32).

## Remaining Uncertainty / Fallback

- On GPU hardware **without** BF16 support (CC < 8.0, e.g. Tesla T4, GTX 10xx),
  `_gpu_bf16_supported()` returns `False` and the resolver returns FP32. This
  is **correct** — the normal GPU path would also use FP32 on such hardware.
- The fix does not apply when explicit `--fp32-unet` CLI flag is set (the
  resolver respects CLI overrides).
- If `cache_gpu_bf16_support()` is never called before the snapshot context
  hides CUDA (defensive coding only — the call site in `modal_app.py` ensures
  it), the internal import of `comfy.model_management` is wrapped in try/except.

## Commit Information

- Commit SHA: _(to be provided after commit)_
- Files changed: 3 (model_preload.py, modal_app.py, this report)
- Tests added: 5
- All existing tests: 452 pass

## Sampler Timing (Before vs After)

| Metric | Before | After (expected) |
|---|---|---|
| Snapshot UNET first forward dtype | FP32 on CUDA | BF16 on CUDA |
| Sampler time | ~20.6s | ~3.7s (parity with normal path) |
| `effective_weight_dtype` log field | absent | `bfloat16` |
| Flags required | benchmark-only | none |
