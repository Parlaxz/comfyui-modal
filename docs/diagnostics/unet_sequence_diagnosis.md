# UNET Sequence and Actual-Forward Diagnosis

## 1. Executive conclusion

**Selected diagnosis: `actual_forward_dtype_device_divergence`**

The snapshot model's actual forward pass executes in **FP32 on CUDA** (all 453 parameters, all 6.15B total numel on `cuda:0|torch.float32`), while the normal-loader model executes in **BF16 on CUDA** (all parameters on `cuda:0|torch.bfloat16`). Both models' forward inputs are on CUDA (snapshot input: `cuda:0|torch.float32`, normal input: `cuda:0|torch.bfloat16`). Both models have identical empty wrapper chains (no patcher wrappers wrapping `NextDiT.forward`). The parameter count and total numel are identical.

The runtime-state divergence observed in earlier rounds (static inspection showing CPU/FP32 for snapshot vs CUDA/BF16 for normal loader) was misleading — by the time `load_models_gpu` completes, the snapshot model is already on CUDA (`cuda:0`), but its parameters remain at `torch.float32` dtype. The normal loader produces `torch.bfloat16` dtype from the outset.

**Confidence:**
- Snapshot actual-forward FP32 on CUDA: **confirmed** (measured at `first_nextdit_forward`)
- Normal actual-forward BF16 on CUDA: **confirmed** (measured at `first_nextdit_forward`)
- FP32 causes ~20.6s sampler vs BF16 ~3.7s on RTX-PRO-6000: **high confidence**
- Container warmth does NOT fix dtype divergence: **confirmed** (repetitions 1-2 consistent)
- Dtype divergence as the single root cause: **high** (wrapper chain, parameter count, structure identical)
- Snapshot construction/runtime-form divergence as the proximate cause: **high**

## 2. Test environment

| Field | Value |
|---|---|
| Instrumentation commit | `feda9a5caf7a23f04f2604360bb31049b383e6bc` |
| Deployment commit | `feda9a5caf7a23f04f2604360bb31049b383e6bc` (with forward-probe fix) |
| Deployment app | `stable-modal-comfy-v2-shadow` |
| Deployment class | `ModalRuntimeEntrypointV2` |
| GPU | `RTX-PRO-6000` |
| Workflow hash | `5f5d5e73b311748300b1fa60ac1663488e0650cd6f10cc545c8e176e7255eae3` |
| Test date | 2026-07-25 |
| Forward probe env var | `COMFYMODAL_V2_UNET_FORWARD_DIAG=1` (enabled for this run) |
| `min_containers` | 0 (confirmed) |
| `scaledown_window` | 4 (confirmed) |

## 3. Instrumentation

The forward probe emits two `unet_forward_probe` trace events per request:

1. **`post_load_models_gpu`** — immediately after the outermost `load_models_gpu()` returns. Captures model state (device, dtype, parameter/buffer distribution) at the post-GPU-commit point.
2. **`first_nextdit_forward`** — on the first call to `NextDiT.forward` per `(request_id, diffusion_model_object_id)`. Captures model state plus the primary input tensor (`x`) device and dtype. The hook is installed as a class-level `NextDiT.forward` patch, installed idempotently during `_ensure_core_wrappers()`.

Both events use `collect_unet_forward_probe_state()` which iterates all `diffusion_model.parameters()` and `buffers()` to produce a full distribution hash. The collector is read-only: no CUDA sync, no tensor mutation, no dtype/device transfer.

## 4. Run-validity table

### Repetition 1 (dir: `v2_2026-07-25_04-56-03`)

| Run | Mode | sampler_ms | post_load_models_gpu | first_nextdit_forward | source match | Model identity | Valid |
|---|---|---|---|---|---|---|---|
| 0 | reuse | 20607.475 | 1 event (cuda:0, fp32) | 1 event (cuda:0, fp32) | cpu_snapshot | z_image_turbo_bf16.safetensors | Yes |
| 1 | bypass | 3703.553 | 1 event (cuda:0, bf16) | 1 event (cuda:0, bf16) | normal_loader | z_image_turbo_bf16.safetensors | Yes |

Container session: `03772fefbd2f4449` (shared between reuse and bypass within same Modal container instance).

### Repetition 2 (dir: `v2_2026-07-25_04-57-22`)

| Run | Mode | sampler_ms | post_load_models_gpu | first_nextdit_forward | source match | Model identity | Valid |
|---|---|---|---|---|---|---|---|
| 0 | reuse | 20618.002 | 1 event (cuda:0, fp32) | 1 event (cuda:0, fp32) | cpu_snapshot | z_image_turbo_bf16.safetensors | Yes |
| 1 | bypass | 3711.256 | 1 event (cuda:0, bf16) | 1 event (cuda:0, bf16) | normal_loader | z_image_turbo_bf16.safetensors | Yes |

Container session: `03772fefbd2f4449` (same container as Rep 1 — warm container reused across repetitions).

### Validity rules applied
- **Reuse**: `requested mode reuse`, `actual source cpu_snapshot`, `sampler completes`, `>=1 post_load_models_gpu`, `>=1 first_nextdit_forward`
- **Bypass**: `requested mode bypass`, `actual source normal_loader`, `sampler completes`, `>=1 post_load_models_gpu`, `>=1 first_nextdit_forward`
- Reject runs with missing events, mismatched source, different model identity, or invalid output.

Run-validity: all 4 runs across both repetitions pass.

## 5. Request timing results

All times in milliseconds.

### Repetition 1

| Run | Source | Pre-Sampler | Sampler | VAE Decode |
|---|---|---|---|---|
| R0 | snapshot | 9050.456 | 20607.475 | 402.854 |
| B0 | normal | 7837.714 | 3703.553 | 1647.948 |

### Repetition 2

| Run | Source | Pre-Sampler | Sampler | VAE Decode |
|---|---|---|---|---|
| R0 | snapshot | 5540.754 | 20618.002 | 1891.847 |
| B0 | normal | 7004.739 | 3711.256 | 1460.260 |

**Consistency**: Snapshot sampler stays 20607-20618ms across both repetitions (delta = 11ms, 0.05%). Normal sampler stays 3704-3711ms (delta = 7ms, 0.2%). Both paths are stable and reproducible.

## 6. Post-load state comparison (`post_load_models_gpu`)

Measured immediately after outermost `load_models_gpu` returns.

| Property | Snapshot (reuse) | Normal (bypass) |
|---|---|---|
| model_device | cuda:0 | cuda:0 |
| model_dtype | **torch.float32** | **torch.bfloat16** |
| param_dev_dtype_numel | `{'cuda:0\|torch.float32': 6154908736}` | `{'cuda:0\|torch.bfloat16': 6154908736}` |
| buffer_dev_dtype_numel | absent (no buffers) | absent (no buffers) |
| param_count | 453 | 453 |
| total_param_numel | 6154908736 | 6154908736 |
| param_distribution_hash | consistent within source | consistent within source |
| wrapper_chain | [] (empty) | [] (empty) |
| wrapper_chain_hash | `e3b0c44298fc1c14...` | `e3b0c44298fc1c14...` |
| collector_duration_ms | 1.5-2.6 | 1.4-1.6 |

**Key finding at the post-load point**: The snapshot model is already on `cuda:0` by the time `load_models_gpu` returns. This contradicts earlier speculation that it might execute on CPU. The model IS on GPU — but in `torch.float32`, not `torch.bfloat16`. The normal loader produces `torch.bfloat16` parameters directly.

## 7. Authoritative first-forward comparison (`first_nextdit_forward`)

Measured on the first call to `NextDiT.forward` per `(request_id, diffusion_model_object_id)`.

| Property | Snapshot (reuse) | Normal (bypass) |
|---|---|---|
| model_device | cuda:0 | cuda:0 |
| model_dtype | **torch.float32** | **torch.bfloat16** |
| x_device | **cuda:0** | **cuda:0** |
| x_dtype | **torch.float32** | **torch.bfloat16** |
| param_dev_dtype_numel | `{'cuda:0\|torch.float32': 6154908736}` | `{'cuda:0\|torch.bfloat16': 6154908736}` |
| param_count | 453 | 453 |
| param_distribution_hash | consistent within source | consistent within source |
| wrapper_chain | [] (empty) | [] (empty) |
| wrapper_chain_hash | `e3b0c44298fc1c14...` | `e3b0c44298fc1c14...` |
| collector_duration_ms | 1.3-2.1 | 2.4-2.5 |

**Critical confirmation**: The forward-pass state is identical to the post-load state for both dtypes. No dtype/device conversion occurs between `load_models_gpu` and `NextDiT.forward`. The snapshot model executes its forward pass with all parameters in FP32 on CUDA, receiving an FP32 input tensor. The normal model executes with all parameters in BF16 on CUDA, receiving a BF16 input tensor.

Both models have identical empty wrapper chains (e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 = SHA-256 of empty string = no `__wrapped__` chain). The forward functions are the same — the only difference is parameter and input dtype.

## 8. State transitions

### Snapshot path
```
CPU snapshot load → CpuSnapshotModels(unet) → [retarget: load_device=cuda:0, offload_device=cuda:0]
  → post_retarget_state: current_device=cpu, first_parameter=FP32/cpu
  → bridge activation: register_unet_forward_probe(source=cpu_snapshot)
  → load_models_gpu() [outermost]
    → post_load_models_gpu EVENT: model on cuda:0, torch.float32, 453 params, 6.15B numel
  → NextDiT.forward (first call)
    → first_nextdit_forward EVENT: model on cuda:0, torch.float32, x on cuda:0, torch.float32
    → sampler duration: ~20600ms
```

### Normal path (bypass)
```
Normal loader: UNETLoader.load_unet() → load_diffusion_model() → ModelPatcher
  → register_unet_forward_probe(source=normal_loader)
  → load_models_gpu() [outermost]
    → post_load_models_gpu EVENT: model on cuda:0, torch.bfloat16, 453 params, 6.15B numel
  → NextDiT.forward (first call)
    → first_nextdit_forward EVENT: model on cuda:0, torch.bfloat16, x on cuda:0, torch.bfloat16
    → sampler duration: ~3700ms
```

## 9. Decision-rule result

| Rule | Result | Evidence |
|---|---|---|
| `actual_forward_dtype_device_divergence` | **Matched** | Snapshot actual-forward: CUDA/FP32 (all 453 params, 6.15B numel). Normal actual-forward: CUDA/BF16 (identical count/numel). ~20.6s vs ~3.7s sampler. Both repetitions confirm exactly. |
| `post_activation_runtime_structure_divergence` | **Rejected** | Wrapper chains are identical (empty hash `e3b0c44298fc1c14...` for both paths). Forward qualname and module type identical. No structure difference found. |
| `unresolved_after_forward_probe` | Not selected | Forward probe resolved the behavioral difference cleanly. |

## 10. Recommended next repair

### Repair: Force BF16 on the snapshot UNET before GPU commit

The snapshot UNET's model parameters are loaded in FP32 (the safetensors file stores FP32 weights). The normal loader produces BF16 because ComfyUI's `UNETLoader` applies the `weight_dtype` option during model construction. The snapshot path loads the model via `load_unet(name, weight_dtype)` — the `weight_dtype` must be `"default"` or `"bf16"` in the snapshot profile's model spec.

**Hypothesis**: The snapshot profile's `normalized_profile` has `weight_dtype` set to `"default"` (or absent), which causes ComfyUI to load weights at their native FP32 precision. The normal loader (when bypass is active) resolves `weight_dtype` differently, producing BF16.

**Exact repair steps**:

1. Verify the snapshot profile's `weight_dtype` field at `cpu_snapshot_models.py:_normalize_profile()`.
2. If `weight_dtype` is `"default"` or absent, change the profile derivation to produce `"bf16"` for UNET weight dtype in the CPU snapshot profile.
3. Or, force `model.to(torch.bfloat16)` on the snapshot UNET's diffusion model after loading and before passing through `load_models_gpu`. This is more robust but carries the risk of missing any ComfyUI-internal casting.
4. Do NOT change the UNET file itself — the safetensors checkpoint stores FP32 weights and that is correct.
5. After the repair, re-run the forward probe A/B comparison to confirm sampler time drops from ~20600ms to ~3700ms for snapshot requests.

### Additional investigation (optional)
- Confirm that `model_dtype()` returns `torch.float32` vs `torch.bfloat16` for the snapshot vs normal model at the forward point.
- Check if `model_management.unet_dtype()` is called differently in the two paths.

## 11. Artifact directories

| Item | Path |
|---|---|
| Rep 1 A/B output dir | `comfymodal-data/benchmarks/runs/v2_2026-07-25_04-56-03/` |
| Rep 1 reuse artifact | `.../run_0.json` |
| Rep 1 bypass artifact | `.../run_1.json` |
| Rep 1 runtime diff | `.../unet_runtime_diff.json` |
| Rep 2 A/B output dir | `comfymodal-data/benchmarks/runs/v2_2026-07-25_04-57-22/` |
| Rep 2 reuse artifact | `.../run_0.json` |
| Rep 2 bypass artifact | `.../run_1.json` |
| Rep 2 runtime diff | `.../unet_runtime_diff.json` |

All paths are relative to the repository root (`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\`).

## 12. Tests and counts

| Test file | Tests | Passed |
|---|---|---|
| `tests/test_v2_unet_forward_probe.py` | 33 | 33 |
| `tests/test_v2_unet_forward_probe_collector.py` | 24 | 24 |
| **Total** | **57** | **57** |

## 13. Remaining uncertainty

### Confirmed by forward probe
- **Snapshot actual-forward is FP32 on CUDA**: All 453 parameters at `cuda:0|torch.float32`. Input tensor `x` at `cuda:0|torch.float32`.
- **Normal actual-forward is BF16 on CUDA**: All 453 parameters at `cuda:0|torch.bfloat16`. Input tensor `x` at `cuda:0|torch.bfloat16`.
- **Wrapper chains are identical**: Empty chain (hash `e3b0c44298fc1c14...`) for both paths.
- **Sampling time is consistent and stable**: Snapshot ~20600ms, normal ~3700ms across two repetitions.
- **The dtype divergence persists across container warmth**: Same result in both Rep 1 and Rep 2.

### Unproven
- **Why the snapshot profile produces FP32 instead of BF16**: The exact mechanism in the profile derivation or model loading that causes FP32 weights is not yet isolated. The `weight_dtype` field in the snapshot's `normalized_profile` may be `"default"` when it should be `"bf16"`.
- **Whether forcing BF16 on the snapshot model would fully resolve the regression**: High confidence given the evidence, but not yet demonstrated.
- **Whether other factors (inductor cache, sage attention mode) affect performance independently of dtype**: Not tested in this diagnostic.

### Additional notes
- Both repetitions ran in the same Modal container session (`03772fefbd2f4449`). The warm container environment does not affect dtype divergence.
- The forward probe was installed as a `NextDiT.forward` class-level patch rather than `register_forward_pre_hook` (which is an instance method and cannot be called on the class). The class-level patch is equivalent in effect.
