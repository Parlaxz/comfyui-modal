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
the effective dtype is resolved (BF16, FP32, FP8, etc.), loads the UNET via
`comfy.sd.load_diffusion_model(path, model_options={"dtype": effective_dtype})`.
This preserves loader semantics with no blanket post-load cast and no checkpoint
reread.  Previously the fast-path only activated for BF16 — it now activates
for any resolved dtype including FP32 (T4 default) and explicit FP8 overrides.

### 4. Reusable parameter validation helper — `cpu_snapshot_models.py`

Added `inspect_and_validate_snapshot_params(model, *, expected_dtype, require_cpu, context)`.
This function iterates **all** parameters (not just the first), reports
`param_count`, `total_param_numel`, `param_dev_dtype_count`,
`param_dev_dtype_numel`, and a deterministic `param_distribution_hash`.
It raises `RuntimeError` when any parameter is on a non-CPU device or when
`expected_dtype` is set and no floating-point parameter matches it (stale-FP32
detection).  Used both at snapshot-creation time and at restore time.

### 5. Hard correctness guard — `modal_app.py` (snapshot creation)

After snapshot UNET construction, the reusable helper inspects all floating-point
parameters.  If the expected effective dtype is BF16 but all parameters are FP32,
a `RuntimeError` is raised with full diagnostic context.  This prevents silent
publication of slow FP32 snapshots.  The parameter distribution is also recorded
in the emitted `param_distribution` state field.

### 6. Restore-time validation — `modal_app.py`

Before publishing a snapshot to the bridge, the snapshot model's dtype is
independently validated against the restore plan + target-GPU policy (not
against snapshot-creation-local variables).  The resolver
`resolve_unet_effective_dtype(weight_dtype, target_gpus=parse_gpu_request())`
derives the expected dtype from the restore plan's `model_spec`, then the
reusable helper inspects the actual model parameters.  On mismatch, the
exception propagates to the activation handler which reports a miss rather
than accepting a stale/invalid FP32 snapshot.

### 7. Metadata separation — `modal_app.py`

Snapshot-created state records:
- `requested_weight_dtype=default` (unchanged — used for identity matching)
- `effective_weight_dtype=bfloat16` (separate field)
- `dtype_resolution_source=target_gpu_policy`
- `target_gpus=RTX-PRO-6000` (from configured policy)
- `param_distribution={...}` (full parameter device/dtype distribution)

## Files Changed

| File | Change |
|---|---|
| `gpu_catalog.py` | Added `_BF16_CAPABLE_GPU_NAMES` set, `gpu_supports_bf16()` function (31 lines) |
| `comfymodal_runtime/model_preload.py` | Refactored `resolve_unet_effective_dtype()` with `target_gpus` parameter. Removed `_gpu_bf16_supported()`, `cache_gpu_bf16_support()`. Updated `V2LoaderBridge._load_unet` logging. (-5 lines net) |
| `comfymodal_runtime/modal_app.py` | Replaced `cache_gpu_bf16_support()` with `parse_gpu_request()`. `_cpu_load_unet` passes `target_gpus`. Added hard correctness guard. Added restore-time validation. Added dtype resolution metadata to snapshot-created state. The `_cpu_load_unet` fast-path now activates for any resolved dtype (not just BF16). Restore-time validation independently derives expected dtype from plan + policy (no `_snap_state` reference). Dtype validation exception properly propagates (not caught by silent handler). (+114/-40 lines) |
| `comfymodal_runtime/cpu_snapshot_models.py` | Added `inspect_and_validate_snapshot_params()` reusable helper — iterates ALL params, reports device|dtype distribution, rejects non-CPU or dtype mismatch. Used at both snapshot creation and restore. |
| `tests/test_cpu_snapshot_models.py` | Updated dtype tests for CPU/no-CUDA, T4, RTX-PRO-6000, explicit overrides, identity, construction-loader, and parameter-validation coverage. |
| `tests/test_gpu_catalog.py` | Added pure-policy BF16 tests covering every catalog GPU and the no-CUDA guarantee. |
| `tests/test_v2_gpu_config.py` | Updated stale assertions to the current RTX-PRO-only default, 24 GiB memory, and host-memory `absent` contract. |

## Test Results

| Test suite | Count | Status |
|---|---|---|
| `test_cpu_snapshot_models.py` | 103 | PASS |
| `test_v2_cpu_snapshot_lifecycle.py` | 130 | PASS |
| `test_v2_unet_runtime_ab.py` | 15 | PASS |
| `test_v2_unet_forward_probe.py` | 32 | PASS |
| `test_v2_unet_forward_probe_collector.py` | 25 | PASS |
| `test_gpu_catalog.py` | 29 | PASS |
| `test_v2_gpu_config.py` | 54 | PASS |
| Compileall `comfymodal_runtime gpu_catalog.py` | — | PASS |
| `git diff --check` | — | No whitespace errors |

The GPU-config assertions were synchronized with the current repository
contracts; no dtype-specific regressions remain in the required suites.

## Oracle Review

All constraints verified:
1. `gpu_supports_bf16()` is pure static lookup — no CUDA API calls
2. `resolve_unet_effective_dtype()` uses target GPU policy for snapshot, pass-through for normal
3. `_cpu_load_unet` uses `load_diffusion_model` with `model_options["dtype"]` for ANY resolved effective dtype (BF16, FP32, FP8) — no post-load cast, no checkpoint reread
4. `inspect_and_validate_snapshot_params()` reusable helper iterates ALL parameters, reports full device|dtype distribution, raises on non-CPU or dtype mismatch
5. Snapshot-creation guard uses the reusable helper — raises immediately on stale FP32
6. Restore-time validation independently derives expected dtype from restore plan + `parse_gpu_request()` — no reference to `_snap_state`. Raises on mismatch; exception propagates to activation handler for fail-closed miss reporting
7. `requested_weight_dtype="default"` preserved in model_spec for identity matching; `effective_weight_dtype` tracked separately
8. `min_containers=0`, `scaledown_window=4` unchanged
9. No stale `cache_gpu_bf16_support()` or `_gpu_bf16_supported()` remain
10. Metadata fields `requested_weight_dtype`, `effective_snapshot_weight_dtype` (effective_weight_dtype), `dtype_resolution_source=target_gpu_policy`, `target_gpus`, and `param_distribution` emitted at snapshot creation and restore

## Commit

SHA: _(to be provided after deploy)_

## Deployment Validation

The standard `deploy_and_run_v2_single.bat` workflow completed successfully
without new flags or environment variables. The deployed target was
`RTX-PRO-6000`.

Remote trace evidence:

- `snapshot_created`: requested `default`, effective `bfloat16`, source
  `target_gpu_policy`, target `RTX-PRO-6000`.
- Snapshot parameter distribution: `cpu|torch.bfloat16`, 453 parameters,
  6,154,908,736 floating-point elements.
- `snapshot_restored_pre_retarget` and `snapshot_restored_post_retarget`:
  same BF16 distribution and requested `default`.
- `cpu_snapshot_unet_reused=1`, `unet_source=cpu_snapshot`.
- First-forward and post-`load_models_gpu` probe events were not emitted by
  this standard run, so those two distributions remain unobserved here.

Three fresh runs with 20-second gaps were saved under
`ComfyUI/comfymodal-data/benchmarks/runs/v2_2026-07-25_18-01-47`:

| Run | sampler_ms | t3b_to_t8_ms | restore_total_ms |
|---|---:|---:|---:|
| 0 | 41,752.833 | 81,983.193 | 5,160.131 |
| 1 | 39,035.474 | 53,621.593 | 1,518.715 |
| 2 | 39,038.934 | 46,415.589 | 1,518.715 |

Median sampler time was 39,038.934 ms, not the expected 3.7–4.5 s. The saved
trace contains no explicit CacheDiT exception, but also provides no evidence
of a functioning CacheDiT speedup; the previously supplied `flash_attn`
import failure remains a separate unresolved issue. The BF16 repair is
therefore validated independently from the remaining sampler optimization.
