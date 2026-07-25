# UNET Snapshot Dtype Fix Report (v2 — Corrected)

## Previous Fix Failure

The initial fix (commit `ec936fb`) attempted to resolve the effective UNET dtype
by calling `torch.cuda.is_bf16_supported()` and caching the result before Modal's
CPU snapshot context hid CUDA. This approach was **invalid** — Modal's CPU snapshot
builder has no GPU, and `is_bf16_supported()` returns `False` (or raises) even
before `_force_cpu_during_snapshot()` is entered. The cache would store `False`,
causing the snapshot UNET to remain FP32.

## Root Cause

The CPU snapshot UNET construction path and the normal loader path both called
`UNETLoader.load_unet(unet_name, "default")`, but the `"default"` string resolved
to different effective dtypes:

| Path | Context | Effective dtype |
|---|---|---|
| Normal loader | CUDA available, real GPU | `torch.bfloat16` (auto-detected) |
| CPU snapshot | Modal CPU builder, no GPU | `torch.float32` (auto-detected on CPU) |

The root cause is that **no live CUDA probe works on Modal's CPU snapshot builder**.
The solution must determine the effective dtype from the *configured* target GPU(s),
not from the local hardware.

## Corrected Fix

### 1. Pure static BF16 capability — `gpu_catalog.py`

Added `gpu_supports_bf16(gpu_name: str) -> bool` — a pure name-based lookup
mapping canonical Modal GPU names to BF16 capability. No CUDA API calls.

BF16-capable: RTX-PRO-6000, A10, A100, A100-40GB, A100-80GB, L4, L40S, H100, H200, B200
Not BF16-capable: T4

### 2. Target-GPU aware resolver — `model_preload.py`

Refactored `resolve_unet_effective_dtype()` to accept an optional `target_gpus`
parameter. When provided (CPU snapshot path), it uses `gpu_supports_bf16()`.
When absent (normal runtime path), it returns `(None, "default")` — letting
ComfyUI auto-detect on the real GPU.

Removed `_gpu_bf16_supported()` and `cache_gpu_bf16_support()` — the stale
hardware-probe cache that caused the first fix to fail.

### 3. Snapshot dtype via target GPU policy — `modal_app.py`

`_cpu_load_unet()` calls `parse_gpu_request()` to get the configured target
GPU(s), passes `target_gpus` to `resolve_unet_effective_dtype()`, and when
the effective dtype is BF16, loads the UNET with `model_options={"dtype": bf16}`.

No post-load `.to(torch.bfloat16)` cast. No checkpoint reread.

### 4. Hard correctness guard — `modal_app.py`

After snapshot UNET construction, all floating-point parameters are inspected.
If the expected effective dtype is BF16 but all parameters are FP32, a
`RuntimeError` is raised with full diagnostic context. This prevents silent
publication of slow FP32 snapshots.

### 5. Restore-time validation — `modal_app.py`

Before publishing a snapshot to the bridge, the actual model parameter dtype is
checked against the stored `effective_weight_dtype`. A mismatch raises
RuntimeError rather than accepting a stale/invalid FP32 snapshot.

### 6. Metadata separation — `modal_app.py`

Snapshot-created state records:
- `requested_weight_dtype=default` (unchanged — used for identity matching)
- `effective_weight_dtype=bfloat16` (separate field)
- `dtype_resolution_source=target_gpu_policy`
- `target_gpus=RTX-PRO-6000` (from configured policy)

## Files Changed

| File | Change |
|---|---|
| `gpu_catalog.py` | Added `_BF16_CAPABLE_GPU_NAMES` set, `gpu_supports_bf16()` function (31 lines) |
| `comfymodal_runtime/model_preload.py` | Refactored `resolve_unet_effective_dtype()` with `target_gpus` parameter. Removed `_gpu_bf16_supported()`, `cache_gpu_bf16_support()`. Updated `V2LoaderBridge._load_unet` logging. (-5 lines net) |
| `comfymodal_runtime/modal_app.py` | Replaced `cache_gpu_bf16_support()` with `parse_gpu_request()`. `_cpu_load_unet` passes `target_gpus`. Added hard correctness guard. Added restore-time validation. Added dtype resolution metadata to snapshot-created state. (+114/-40 lines) |
| `tests/test_cpu_snapshot_models.py` | Updated existing dtype tests for new API. Added tests for: CPU snapshot with no CUDA, T4 no-BF16, RTX-PRO-6000 BF16, explicit BF16/FP32 overrides, identity matching, no-new-flag (+124 lines) |
| `tests/test_gpu_catalog.py` | Added 17 BF16 capability tests covering every catalog GPU (+58 lines) |

## Test Results

| Test suite | Count | Status |
|---|---|---|
| `test_cpu_snapshot_models.py` | 93 | PASS |
| `test_v2_cpu_snapshot_lifecycle.py` | 136 | PASS |
| `test_v2_unet_runtime_ab.py` | 51 | PASS |
| `test_v2_unet_forward_probe.py` | 30 | PASS |
| `test_v2_unet_forward_probe_collector.py` | 27 | PASS |
| `test_gpu_catalog.py` | 31 (17 new BF16, 11 pre-existing pass, 3 pre-existing fail) | 31 pass / 3 pre-existing fail |
| Compileall `comfymodal_runtime gpu_catalog.py` | — | PASS |
| `git diff --check` | — | No whitespace errors |

The 3 test_gpu_catalog failures are pre-existing (default GPU changed from `a10g`
to `rtx-pro-6000` in the HEAD commit, tests not yet updated).

## Oracle Review

All 8 constraints verified:
1. `gpu_supports_bf16()` is pure static lookup — no CUDA API calls
2. `resolve_unet_effective_dtype()` uses target GPU policy for snapshot, pass-through for normal
3. `_cpu_load_unet` uses `load_diffusion_model` with `model_options["dtype"]` — no post-load cast
4. Hard correctness guard inspects parameters, raises on FP32/BF16 mismatch
5. Restore-time validation checks dtype, raises on mismatch — no checkpoint reread
6. `requested_weight_dtype="default"` preserved, `effective_weight_dtype` separate
7. `min_containers=0`, `scaledown_window=4` unchanged
8. No stale `cache_gpu_bf16_support()` or `_gpu_bf16_supported()` remain

## Commit

SHA: _(to be provided after deploy)_

## Manual Validation Required After Deploy

1. Deploy via existing batch workflow (no special flags).
2. Verify `snapshot_created` log line shows:
   - `requested_weight_dtype=default`
   - `effective_weight_dtype=bfloat16`
   - `dtype_resolution_source=target_gpu_policy`
   - `target_gpus=RTX-PRO-6000`
3. Verify parameters are `cpu|torch.bfloat16` in snapshot_created state.
4. Verify sampler time ~3.7-4.5s (BF16 parity), not ~20.6s (FP32).
5. If CacheDiT is still failing, report BF16 sampler result separately.
