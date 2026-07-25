# UNET Sequence Diagnosis

## 1. Executive conclusion

**Selected diagnosis: Snapshot construction or runtime-form divergence**

**Confidence: medium**

The CPU snapshot model persists in FP32 on CPU (`torch.float32`, `current_device=cpu`) while the normal loader produces BF16 on CUDA (`torch.bfloat16`, `current_device=cuda:0`). Every request using the snapshot UNET takes approximately 20.6 seconds for sampling regardless of container warmth, while every request using the normal-loader bypass takes approximately 3.7 seconds from the very first execution in a restored container. The difference in dtype/device between the two paths is the most visible and measurable divergence. However, this correlation does not fully prove that restoration-time dtype/device alone determines forward speed -- the snapshot path may also produce a structurally different model that cannot exploit CUDA tensor cores even if moved to GPU.

**Container warmth does NOT fix:**
- **Graph/cache setup:** Container warmth removes pre-sampler overhead (graph load, GPU commit, model loading) but the sampler duration remains unchanged.
- **Sampler setup:** After warmth, pre-sampler time drops from approximately 16-34s to approximately 4-8s but sampler stays at approximately 20.6s.
- **Actual UNET sampling:** Remains at approximately 20.6s in all snapshot-reuse requests regardless of container warmth. Only the normal-loader bypass achieves approximately 3.7s sampling.

## 2. Test environment

| Field | Value |
|---|---|
| Commit SHA tested | `2cb32a8530f9ac804d592660f86a4f3c63b78d8e` |
| Deployment app | `stable-modal-comfy-v2-shadow` |
| Deployment class | `ModalRuntimeEntrypointV2` |
| GPU | `RTX-PRO-6000` |
| Workflow hash | `5f5d5e73b311748300b1fa60ac1663488e0650cd6f10cc545c8e176e7255eae3` |
| Test date | 2026-07-25 |
| Relevant environment variables | `V2_BENCHMARK_RUNS=2`, `V2_BENCHMARK_GAP_SECONDS=0`. Additional vars set by deployment configuration: `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`, `COMFYMODAL_V2_DEEP_MODEL_DIAG=1` via Modal environment. Not explicitly set in benchmark invocation. |
| `min_containers` | 0 (confirmed) |
| `scaledown_window` | 4 (confirmed) |

## 3. Sequence validity

| Sequence | Valid | Container ID | Restored Instance | Restore Session | Task/PID | Notes |
|---|---|---|---|---|---|---|
| RR | Yes | `576be42a962b400a` | `cabe87bcddd94aa5a674af6fb3ee93dd` | `9a6dc99e37cb4e5c9622aac38c799cc1` | PID 2, hostname `modal` | Both RR requests share all three identity fields. |
| BB | Yes | `576be42a962b400a` | `62cf7f1a70be4b93a4a73859ffa027eb` | `fe1e8078b8234aea9df7bc07563349c6` | PID 2, hostname `modal` | Both BB requests share all three identity fields. Container_session_id matches RR because the same Modal container process handled both sequences (container did not fully scale down). However, a new restore occurred due to the changed execution plan (bypass flag), producing a new restored_instance_id. Valid for within-sequence comparison. |
| RBR | Yes | `ead69123aebf408f` | R1: `83f5ee0f725e4e7e814f7f1f049b1c99`, B2/R3: `f68cc2ec858a43d3a2fc780a5934dbb7` | R1: `a6d0bdce221c4cffa35f4f07fbdc4713`, B2/R3: `ba022c5955824917a942129bfcdf76d2` | PID 2, hostname `modal` | All three requests in the same Modal container. R1 has a different restored_instance_id because the initial snapshot session was replaced when the bypass flag changed the restore plan. B2 and R3 share the same restore session. All three share `container_session_id=ead69123aebf408f`. |

## 4. Request timing results

All times in milliseconds.

| Sequence | Request | Source | Restore | Pre-Sampler | Sampler | VAE Decode | Wall Total |
|---|---|---|---|---|---|---|---|
| RR | R0 | snapshot CPU/FP32 | 3259 | 16233 | 20647 | 529 | 74300 |
| RR | R1 | snapshot CPU/FP32 | 3259 | 3651 | 20616 | 264 | 25158 |
| BB | B0 | normal CUDA/BF16 | 7785 | 17663 | 3689 | 385 | 127014 |
| BB | B1 | normal CUDA/BF16 | 7785 | 7549 | 3689 | 261 | 12119 |
| RBR | R1 | snapshot CPU/FP32 | 7058 | 34238 | 20574 | 409 | 84378 |
| RBR | B2 | normal CUDA/BF16 | 10135 | 15478 | 3729 | 353 | 50603 |
| RBR | R3 | snapshot CPU/FP32 | 10135 | 8657 | 20599 | 257 | 30750 |

Key observations:
- Snapshot sampler: consistently 20574-20647ms across all sequences (R0, R1, RBR-R1, RBR-R3).
- Normal-loader sampler: consistently 3689-3729ms across all sequences (B0, B1, RBR-B2).
- First-request wall times are inflated by Modal cold-start overhead (`first_iteration_to_first_remote_event` up to 93750ms).
- `restore_total_ms` values differ between sequences because the restore plan payload changed (different execution flags).

## 5. Runtime-state comparison

| Property | RR snapshot (FP32) | BB normal (BF16) | RBR final snapshot (FP32) |
|---|---|---|---|
| load_device | cuda:0 | cuda:0 | cuda:0 |
| offload_device | cuda:0 | cuda:0 | cuda:0 |
| current_device | **cpu** | **cuda:0** | **cpu** |
| first_parameter_device | **cpu** | **cuda:0** | **cpu** |
| first_parameter_dtype | **torch.float32** | **torch.bfloat16** | **torch.float32** |
| model_dtype | **torch.float32** | **torch.bfloat16** | **torch.float32** |
| manual_cast_dtype | absent | absent | absent |
| loaded_models_member | 0 | 0 | 0 |
| model_loaded_weight_memory | 0 | 0 | 0 |

The critical difference: the snapshot model's `first_parameter_device` is `cpu` and `first_parameter_dtype` is `torch.float32` even after retargetting to `load_device=cuda:0`. The snapshot restoration does load the model into CUDA memory (restore_gpu_state_ms is significant: 2449-5038ms), but the parameter tensors themselves remain in FP32 on the CPU. The normal loader produces parameters that are already `torch.bfloat16` on `cuda:0`.

Both paths report `manual_cast_dtype=absent`, meaning no automatic dtype casting is applied after loading.

## 6. RR analysis

Between R0 and R1 (same restored container, both using snapshot UNET):

| Metric | R0 | R1 | Delta |
|---|---|---|---|
| wall_ms | 74300 | 25158 | -49142 (-66%) |
| pre_sampler_ms | 16233 | 3651 | -12582 (-78%) |
| sampler_ms | 20647 | 20616 | -31 (-0.2%) |
| vae_decode_ms | 529 | 264 | -265 (-50%) |

**What improved:** Pre-sampler work including graph setup, GPU commit, model loading to CUDA, and other initialization that only runs on the first request in a restored container. The pre-sampler dropped from 16.2s to 3.7s.

**What remained slow:** The actual UNET sampling/forward pass stayed at approximately 20.6s. Container warmth does not speed up the snapshot model's forward pass. The VAE decode also improved slightly (from 529ms to 264ms), likely due to CUDA kernel caching.

**Identity confirmation:** Both requests share `container_session_id=576be42a962b400a`, `restored_instance_id=cabe87bcddd94aa5a674af6fb3ee93dd`.

## 7. BB analysis

**Was B0 fast despite being the first request in the restored container?**
Yes. B0's sampler was 3689ms (3.7s), compared to R0's 20647ms (20.6s). This is despite B0 being the first request in the restored container (wall time 127s was dominated by Modal restore/submit latency, not the sampler).

**Was B2 materially faster?**
No. B1's sampler was 3689ms (3.7s), essentially identical to B0's 3689ms. The normal-loader bypass produces a fast UNET from the very first request; there is no second-request sampler improvement.

**Did the normal-loader model use BF16/CUDA?**
Yes. The `normal_loader_ready` state shows `first_parameter_dtype=torch.bfloat16`, `current_device=cuda:0`, `first_parameter_device=cuda:0`. This contrasts with the snapshot state which shows `torch.float32` and `current_device=cpu`.

**Was there a generic first-request sampler penalty?**
No. The sampler itself did not have a first-request penalty in the normal-loader path. The first-request penalty (visible in pre-sampler: 17663ms vs 7549ms) is entirely in the pre-sampler phase -- graph setup, model patching, conditioning, and GPU commit.

## 8. RBR analysis

**Did normal loading change the final snapshot request?**
No. R3 continued to use the snapshot UNET (`cpu_snapshot_unet_reused=1`, `unet_source=cpu_snapshot`). The normal-loader bypass in B2 did not modify the snapshot state.

**Did R3 remain slow?**
Yes. R3's sampler was 20599ms (20.6s), essentially identical to R1's 20574ms and the RR sequence's approximately 20.6s.

**Did R3 still use the snapshot UNET?**
Yes, confirmed by `unet_source=cpu_snapshot` and `cpu_snapshot_unet_reused=1` in R3's trace events.

**Did visible snapshot state change after B2?**
No. R3's `snapshot_restored_post_retarget` state is identical to R1's: FP32 on CPU (`first_parameter_dtype=torch.float32`, `current_device=cpu`). The snapshot object persisted in memory unaffected by the normal-loader execution.

**Container identity:**
- R1: restored_instance_id=83f5..., restore_session_id=a6d0...
- B2: restored_instance_id=f68c..., restore_session_id=ba02... (new restore due to bypass flag)
- R3: restored_instance_id=f68c..., restore_session_id=ba02... (same as B2)
- All: container_session_id=ead69123aebf408f

## 9. Decision-rule result

| Rule | Result | Evidence |
|---|---|---|
| **Snapshot object remains persistently slow** | **Matched** | RR sampler 20.6s -> 20.6s; BB sampler 3.7s -> 3.7s; RBR sampler 20.6s -> 3.7s -> 20.6s. R3 confirmed to use snapshot UNET. Container warmth does not improve the snapshot sampler. |
| **Generic first-request GPU initialization** | **Matched** | BB0 pre_sampler=17663ms vs BB1 pre_sampler=7549ms. RR0 pre_sampler=16233ms vs RR1 pre_sampler=3651ms. The first-request penalty affects pre-sampler work (graph setup, GPU commit), not the forward pass. This penalty applies to both UNET sources. |
| **Normal loader initializes shared state needed by snapshot** | **Rejected** | R3 remained at 20599ms after B2's 3729ms. R3 still used the snapshot UNET source. The normal loader's BF16/CUDA state did not transfer to the snapshot path. |
| **Snapshot construction or runtime-form divergence** | **Matched** | Snapshot: FP32/CPU (first_parameter_dtype=torch.float32, current_device=cpu). Normal loader: BF16/CUDA (torch.bfloat16, current_device=cuda:0). BB fast from B0; RR remains slow; RBR ends with slow R3. The runtime-form divergence is the leading hypothesis. |
| **Unresolved** | Not selected | The results cleanly match the divergence rule. |

## 10. Separate bottlenecks

**Graph/cache initialization:**
Improves with container warmth. Pre-sampler drops from approximately 16-34s to approximately 4-9s. This affects both snapshot and normal-loader paths equally. The warm-container improvement is substantial (10-25s saved) but does not affect the sampler itself.

**Sampler setup:**
The pre-sampler phase includes sampler node resolution, model patching, conditioning, and graph execution. After container warmth, the pre-sampler for snapshot requests drops to approximately 3.7-8.7s. This is the same pattern as graph/cache initialization.

**UNET forward/sampling:**
This is the dominant bottleneck. Snapshot: approximately 20.6s regardless of container warmth. Normal-loader: approximately 3.7s regardless of container warmth. The 5.6x difference (20600/3690) correlates with the dtype/device divergence. The snapshot model runs its forward pass in FP32 on CPU (after retarget, parameters remain on CPU despite load_device=cuda:0), while the normal-loaded model runs in BF16 on CUDA. An RTX-PRO-6000 with tensor cores would be expected to execute BF16 matrix multiplications 4-8x faster than FP32 CPU execution, consistent with the observed gap.

## 11. Recommended next step

Capture the snapshot and normal-loader model's actual dtype and device at the first `NextDiT.forward` call. If confirmed FP32 (snapshot) versus BF16 (normal loader), construct the CPU snapshot through the original loader using the explicit intended BF16 weight dtype. Retest RR.

Do not implement this repair in this task -- this is a diagnostic recommendation only.

## 12. Artifact locations

| Item | Path |
|---|---|
| RR output directory | `comfymodal-data/benchmarks/runs/v2_2026-07-25_03-38-01/` |
| RR run 0 artifact | `.../run_0.json` |
| RR run 1 artifact | `.../run_1.json` |
| RR summary | `.../summary.json` |
| BB output directory | `comfymodal-data/benchmarks/runs/v2_2026-07-25_03-45-52/` |
| BB run 0 artifact | `.../run_0.json` |
| BB run 1 artifact | `.../run_1.json` |
| BB summary | `.../summary.json` |
| RBR output directory | `comfymodal-data/benchmarks/runs/v2_rbr_2026-07-25_03-49-35/` |
| RBR run 0 (R1) artifact | `.../run_0.json` |
| RBR run 1 (B2) artifact | `.../run_1.json` |
| RBR run 2 (R3) artifact | `.../run_2.json` |
| RBR summary | `.../summary.json` |

All paths are relative to the repository root (`C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\`).

## 13. Remaining uncertainty

- The test did not confirm that FP32 on CPU is the *sole* cause of the slow sampler. The snapshot and normal-loader models may also differ in structure (e.g., memory format, graph compilation state, CUDA graph capture) that affects forward speed independently of dtype.
- The BB sequence ran in the same Modal container process as RR (same `container_session_id`). While a new restore occurred (different `restored_instance_id`), some residual GPU state from RR's snapshot restore may have persisted. This does not affect the within-sequence comparison but means the BB-first-request wall time of 127s included some shared initialization.
- No Modal-side logs were available to confirm container task IDs, GPU metrics, or CUDA kernel timing at runtime. The analysis relies entirely on the generated JSON artifacts and trace events.
- The workflow uses a Z-Image-Turbo (Lumina2/NextDiT) model. The findings may not generalize to other model architectures.
