# R44H1 — CLIP BF16→FP16 Semantics and the Single-Materialization Adoption Path

Worktree: `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (no commits made)
Batch type: LOCAL analysis + implementation only. **No deploy, no Modal run, no paid request, no transport tuning.**
Concurrent lane: R44H2 (observability/Gantt/sampler telemetry) — untouched by this batch.

---

## 1. R44F failure root cause

R44F (`v2-benchmark-0-cb40e0c40c4c`, gate `gate_20260824-050525_ff132f65.json`) skipped its own CLIP arm
before transport:

```
clip_fastsafe_skip reason=native_adoption_ineligible detail=dtype_parity_mismatch:file_0:BF16
gates: {device_arg: default, expected_te_dtype: torch.float16, te_device: cuda:0, file_0_dtypes: [BF16]}
```

Root cause chain:

1. `_expected_te_dtype_str()` (`request_clip_fastsafe.py`) mirrors native Comfy:
   `text_encoder_dtype(text_encoder_device())`.
2. Pinned `comfy/model_management.py:1171-1186`: `text_encoder_dtype()` returns `torch.float16`
   **unconditionally** unless CLI args (`--fp8-*`, `--bf16-text-enc`, `--fp32-text-enc`) say otherwise.
   No capability query participates for text encoders.
3. The R44F eligibility gate demanded **exact parity** between checkpoint dtype and expected runtime
   dtype because its bind mechanism was `load_state_dict(assign=True)` — assign never casts, so parity
   was a *correct* requirement *for that mechanism*.
4. `qwen_3_4b.safetensors` is BF16 ⇒ `dtype_parity_mismatch:file_0:BF16` ⇒ skip ⇒ observed loader stayed
   empty ⇒ `RuntimeStatus DEGRADED(loader_unobserved_clip)` ⇒ structural gate reasons ⇒ `gate_valid=false`,
   even though output SHA matched exactly through the native fallback and UNET control was healthy
   (453/453 same-storage, `file_to_gpu_wall_ms=629.2175`, `adopt_ms=123.22`, `copied_count=0`).

The bug was therefore **not** "wrong dtype check" but "**parity-only eligibility coupled to an
assign-only bind**". A BF16 checkpoint under an FP16-expecting runtime needs a *casting* adoption mode,
not a rejection and not a weakened check.

## 2. Exact native dtype-selection trace (why `expected_te_dtype` is FP16)

Pinned ComfyUI (files verified at `ComfyUI June Install\ComfyUI\comfy\`):

| Step | Location | Decision |
|---|---|---|
| 1 | `nodes.py` CLIPLoader/DualCLIPLoader → `comfy.sd.load_clip` → `load_text_encoder_state_dicts` | passes `model_options` without `dtype`/`load_device` |
| 2 | `comfy/sd.py:229` | `load_device = model_options.get("load_device", model_management.text_encoder_device())` → `cuda:0` |
| 3 | `comfy/sd.py:231-233` | `dtype = model_options.get("dtype", None)` → None → `model_management.text_encoder_dtype(load_device)` |
| 4 | `comfy/model_management.py:1171-1186` | returns `torch.float16` (arg-driven overrides only; **no bf16-capability consultation**) |
| 5 | `comfy/sd.py:235-239` | `params['dtype']=fp16; params['device']=text_encoder_initial_device(...)`; `cond_stage_model = clip(**params)` |
| 6 | `comfy/sd.py:241-246` | `supports_cast(load_device, dt)` loop — fp16 supported on cuda ⇒ no "shift TE back" |
| 7 | `comfy/sd.py:250-256` | tokenizer built; `CoreModelPatcher(load_device, offload_device)`; `set_model_compute_dtype(torch.float32)` (activation upcast policy, unchanged by us) |
| 8 | `comfy/sd.py:259-269` | `self.load_sd(state_dict)` **inside the constructor** |
| 9 | `comfy/sd1_clip.py:308-309` | `transformer.load_state_dict(sd, strict=False, assign=getattr(self,'can_assign_sd',False))` — fresh CLIP ⇒ `assign=False` ⇒ **copy-cast into the pre-created parameters** |

Qwen mapping: `comfy/sd.py:1590-1596` (`TEModel.QWEN3_4B`, FLUX/FLUX2 clip_type) →
`comfy/text_encoders/flux.py:209-230` (`klein_te`, `model_type="qwen3_4b"`) →
`comfy/text_encoders/llama.py:1030-1037` `class Qwen3_4B(...): Llama2_(config, device=device, dtype=dtype, ops=operations)`.

### Answers to the ten hard questions

1. **What function chooses torch.float16?** `comfy.model_management.text_encoder_dtype()` (`model_management.py:1186`), consumed at `sd.py:233`.
2. **Based on what input?** Only CLI text-encoder dtype args; otherwise the constant default. GPU capability is NOT consulted for TEs (unlike UNET `should_use_bf16`).
3. **Is FP16 a hard requirement of the Qwen TE implementation?** No. `Qwen3_4B.__init__` receives `dtype`/`device` as injected parameters (`llama.py:1031-1036`). Rope `inv_freq` is computed per-forward (`llama.py:407-417`), not stored as a persistent buffer.
4. **Policy or requirement?** Policy — ComfyUI's preferred runtime dtype for this configuration.
5. **Does native Comfy load BF16 checkpoint values into FP16 parameters?** Yes — via `load_state_dict(assign=False)` copy semantics (`sd1_clip.py:308-309`), which performs the BF16→FP16 conversion elementwise during the copy.
6. **Where does that conversion occur?** Inside `CLIP.__init__`'s `self.load_sd(state_dict)` call (`sd.py:259-269`), i.e., **inside the construction window**, into whatever device `text_encoder_initial_device()` selected (see §4).
7. **Does the native reference path intentionally keep an FP16 master/live copy?** Yes — the instantiated parameters ARE the master; there is no retained BF16 copy anywhere in the native path.
8. **Is any BF16 storage retained after native loading?** No (checkpoint tensor objects are dropped after `load_state_dict`; activations are upcast to FP32 at output only, `sd1_clip.py:282-294`).
9. **Does ModelPatcher expect offload/master distinct from active CUDA representation?** It tracks `model.device`, `model.model_lowvram`, `model.model_loaded_weight_memory`, `model.current_weight_patches_uuid` (`model_patcher.py:1040-1052`) and membership in `current_loaded_models` (`model_management.py:882-895`). A model physically on CUDA with zeroed bookkeeping looks "not loaded".
10. **What flags/bookkeeping caused the +8.10 GB later allocation?** After native construction the produced CLIP had `model_loaded_weight_memory == 0` and was absent from `current_loaded_models`, so `CLIP.load_model → load_models_gpu` scheduled a full `LoadedModel.model_load` → `ModelPatcher.load()` materialization (`model_management.py:956`, `model_patcher.py:928-1052`). Partial-load short-circuit (`model_patcher.py:1215-1223`) requires `model_lowvram == False and model_loaded_weight_memory > 0`.

## 3. Exact checkpoint dtype facts (authoritative artifacts)

- File: `qwen_3_4b.safetensors`; source bytes `8,044,982,048`; header tensors `398` (R44E raw log lines 111-150).
- Tensor dtype: **BF16** (uniform; R44F gate payload `file_0_dtypes: ["BF16"]`; E38 audit corroboration).
- No quant metadata, no native-transform marker keys (R44F gates passed everything except parity).
- UNET control: `z_image_turbo_bf16.safetensors`, targeted bytes `12,309,866,400`, 453/453 same-storage.

## 4. Where the BF16→FP16 conversion happens today (pre-fix paths)

- **R44E COPY_CUDA lane**: FastSafe copies disk BF16 → CUDA staging (8.04 GB, `1934.712 ms`, 4.159 GB/s cold);
  native ctor then copy-casts **CUDA BF16 → CPU FP16** (cross-device `copy_`) because the skeleton was
  materialized on CPU (proof: `cuda_allocated_after_construction_bytes == cuda_allocated_after_fastsafe_bytes`
  exactly, raw log lines 142-144); `load_models_gpu` then performs the second model-sized materialization
  CPU FP16 → CUDA (+8,101,709,312 B, `2283.612 ms`).
- **Native fallback (R44F)**: disk → CPU → FP16 params on CPU → same +8.10 GB `load_models_gpu` move.
- Conversion count today: **exactly one dtype conversion, but TWO model-sized representations exist
  transiently and the live one is created twice (CPU then CUDA)** — plus the redundant BF16 staging kept
  resident through forward in R44E (16.15 GB allocated before inner forward).

## 5. R44E 2670.544 ms construction — explanation

Artifact-proven shape of the window (`bind_ms=2670.544`, CUDA delta across it = 0):

1. Architecture/tokenizer detection + config parse (cheap).
2. **CPU FP16 parameter materialization**: `nn.Module` init of ~4.02 B params at `dtype=fp16,
   device=cpu` (~8 GB of allocations) — because `text_encoder_initial_device()` resolved to the
   offload device in that container (branch candidates: `aimdo_enabled` (`model_management.py:1155-1156`)
   or the free-memory heuristic at :1164-1169; not separately instrumented in R44E — the new
   `construction_ex_loadsd_wall_ms` / `load_sd_wall_ms` split settles the split at the next gate;
   the seam now makes the choice deterministic either way).
3. **Cross-device copy-cast**: `load_state_dict(assign=False)` copying 398 CUDA BF16 tensors into CPU
   FP16 params — a D2H transfer + cast of ~8 GB inside the constructor (`sd1_clip.py:308-309`).
4. Tokenizer construction, patcher creation, publication.

Classification: **legitimate dtype conversion + generic load_state_dict copying + CPU parameter
materialization — all three avoidable** by building the skeleton directly on the load device (§7).
Module-construction alone is known cheap from the UNET analogue (`skeleton_wall_ms=80.832`).

Verdict: `R44H1_R44E_CONSTRUCTION_2671MS_EXPLAINED = YES` (mechanism proven by artifact + source;
exact millisecond split between phases 2/3 lands with the new instrumentation).

## 6. Mode decision

**Selected: MODE B — `cast_once_fp16`.**

- Mode A (true BF16 same-storage live parameters) would change the TE compute dtype away from the
  native-default FP16 policy that produced canonical SHA `20b10e1f…`. That risks numeric divergence
  against the golden output and changes intended execution semantics — disqualifying under the batch's
  own Mode-A validity conditions, even though BF16 *capability* exists (`--bf16-text-enc`;
  `props.major >= 8`).
- Mode B preserves native execution semantics bit-for-bit: the ONE conversion performed is the very
  operation native Comfy executes (`load_state_dict` copy-cast), just relocated onto the final device.
  BF16→FP16 is exponent-range-narrowing but mantissa-exact; values within FP16 normal range convert
  exactly, identically on CPU or CUDA (IEEE round-to-nearest; validator proves bit-equality anyway).

Rejected alternative: meta-skeleton + pre-cast served dict + forced assign. Rejected because (a) assign
mode bypasses Comfy's own conversion logic, (b) meta skeletons risk non-persistent-buffer residuals
(fail-closed surface for zero benefit here since the FP16 allocations are needed regardless), and (c)
empty-CUDA-skeleton is a natively-supported configuration (`text_encoder_initial_device` returning
`load_device` is ordinary high-VRAM behavior).

## 7. New architecture (implemented locally)

```
disk BF16 (qwen_3_4b.safetensors, 8,044,982,048 B)
  → FastSafe CUDA BF16 staging            copy: YES (single physical read; T8/B256MiB/bbuf512/nogds unchanged)
      [telemetry: fastsafe_setup/copy walls, 4.159 GB/s-class cold band preserved]
  → native CLIP ctor on seamed initial_device = cuda:<target>
      skeleton = EMPTY FP16 CUDA parameters (FINAL live storage, allocated once)
      → CLIP.load_sd → transformer.load_state_dict(strict=False, assign=False)
          cast: EXACTLY ONE BF16→FP16 per tensor, CUDA→CUDA kernel, INTO final storage
          [seam wraps load_sd timing/capture-only; result passthrough]
  → _validate_cast_once_bind              meta-residual / shape / dtype / device /
                                          BIT-EXACT value proof per key (torch.equal)
                                          full bucket accounting; unbound param ⇒ fail closed
  → owner_attach + ON_DETACH hook (safety net) + mark_clip_hydrated
  → _register_residency: load_models_gpu([patcher], force_full_load=True)
                                          bookkeeping ONLY (modules already resident);
                                          movement detector armed (≥0.9×param-bytes ⇒ flag)
  → retire_source_owners(owners, bf16_bytes, clip)   NON-destructive staging release
                                          (release_storage(purge_allocator=False));
                                          partial failure keeps owners + hook, honest flags
  → publish (observed=fastsafetensors_direct_gpu, NOMINAL)
  → forward                               ONE model-weight representation; no model-sized copy
```

Adoption-mode nomenclature (honest, no SAME_STORAGE claim where mathematically impossible):
`same_storage_assign` (parity, meta+assign, unchanged R44F mechanics) · `cast_once_fp16` ·
`cast_once_bf16` (symmetric pair, gated) · `copy_cuda_legacy` (flag-off R44E lane) ·
fallback = `native_comfy` observed arm. Bind modes published: `same_storage` | `cast_once_fp16` | `copy_cuda`.

Eligibility (`_ADOPTION_DTYPE_PAIRS`): `(F16,fp16)`, `(BF16,bfloat16)`, `(F32,fp32)` → parity assign;
`(BF16,fp16)` → cast_once_fp16; `(F16,bfloat16)` → cast_once_bf16; **everything else fails closed**
(`unsupported_dtype_pair:file_i:FOUND->EXPECTED`); mixed modes across files ⇒ `mixed_adoption_modes`;
per-file uniformity, transform-marker keys, quant metadata checks unchanged.

## 8. Model-management integration

- **No pinned-Comfy patch was needed.** All integration uses native semantics:
  - skeleton device steered through the existing `text_encoder_initial_device` seam (scoped, restored,
    identity-checked restore);
  - readiness established by `load_models_gpu([patcher], force_full_load=True)` — the same call native
    `CLIP.load_model` makes — which registers the `LoadedModel` in `current_loaded_models` and sets
    `model_loaded_weight_memory`/`current_weight_patches_uuid` (`model_patcher.py:1040-1052`);
    with every module already on the load device, `patch_weight_to_device`'s `.to(device_to)` is a no-op,
    so the call is bookkeeping-only;
  - `force_patch_weights` semantics untouched; patch UUID coherent (no patches).
- Not a global bypass: `load_models_gpu` still runs, scoped to the adopted patcher, and its wall/deltas
  are telemetered with a movement detector (`model_sized_movement_detected`).

## 9. Ownership / lifetime

- Parity mode: unchanged R44F contract — owners attached, ON_DETACH release at full detach.
- Cast-once mode: owners attached (uniform lifecycle/failure cleanup), then **early retirement** after
  validation+residency, BEFORE publication/forward, via `retire_source_owners`
  (`clip_fast_hydration.py:1696-1811`): prefers non-destructive `release_storage(purge_allocator=False)`
  / `free_storage` / `release_buffer`; NEVER `close()`/`empty_cache()` on the hot path; fails closed on
  partial retirement (owners stay attached; ON_DETACH hook remains safety net;
  `duplicate_weight_bytes_before_forward=source_bytes` reported honestly instead of a false 0).
- Failure anywhere: `_fail_closed` closes owners, releases the physical-load claim, records sticky
  terminal reason + `native_comfy` fallback observation, then runs the original node method. No
  half-published CLIP is possible (publication is the last step; every predecessor raises into the
  except-arm).

## 10. Full tensor accounting (rules + expected next-gate counts)

Per staged key (validator `_validate_cast_once_bind`):

| Bucket | Rule | Expected for qwen_3_4b |
|---|---|---|
| comparable / cast_once | header shape+dtype match staged; live key resolves; shape/dtype/device/bit-value equal | 398 (all) |
| blob | tokenizer blob keys | 0 (plain TE safetensors) |
| transformed | header disagrees with staged payload | 0 (gates reject transform markers upstream) |
| missing | comparable key absent from live state_dict | 0 required, else fail closed |
| extra-parameter | live param with no staged source | 0 required, else `unbound_parameter` fail closed |
| extra-buffer | ctor-initialized buffer (tolerated, counted) | ~0 (rope inv_freq computed per-forward, `llama.py:407-417`) |

Tied/alias weights: safetensors stores tied tensors once; each mapped key casts independently — handled
by the name-keyed validator. No unexplained entries are permitted by construction.

## 11. Memory model

| Milestone | Allocated CUDA (expected) |
|---|---|
| before FastSafe | baseline (~0 in R44E cold container) |
| after FastSafe staging | ~8.045 GB |
| during construction (peak) | ~16.07 GB (staging + growing FP16 final storage) — the ONE unavoidable coexistence |
| after `retire_source_owners` | ~8.02 GB (final live only) |
| `load_models_gpu` delta | ~0 (bookkeeping-only; movement detector armed) |
| before inner forward | **ONE representation (~8.02 GB)** |

FastSafe constraint documented: whole-file materialization is inherent to the current
`add_filenames → copy_files_to_device → get_tensor` API, so per-tensor streaming (cast-and-free
incrementally) is not possible without changing the transport; temporary duplication is bounded to the
conversion window and released before forward, satisfying the acceptance metric.

## 12. Telemetry implemented for the next gate (all additive)

New fields on `clip_fast_load_start/end` (both native modes) and events:
`adoption_mode`, `checkpoint_dtype`, `expected_runtime_dtype`, `live_parameter_dtype`,
`comparable_tensor_count`, `cast_once_count`, `legacy_copy_count`, `transformed_exception_count`,
`missing_count`, `extra_count`, `checkpoint_bytes`, `final_live_weight_bytes`,
`temporary_source_bytes_peak`, `temporary_duplicate_weight_bytes_peak`,
`duplicate_weight_bytes_before_forward`, `load_sd_wall_ms`, `construction_ex_loadsd_wall_ms`,
`owner_release_wall_ms`, `owner_release_method`, `owners_retired`, `owners_failed`, `owner_bytes_before`,
`owner_release_point` (`after_cast_validation` | `on_detach_after`), `owner_retained` (honest),
`cuda_reserved_after_construction_bytes`, `cuda_allocated/reserved_after_source_release_bytes`,
`residency_register_wall_ms`, `model_sized_movement_detected`; residency event adds `wall_ms`,
reserved deltas, movement flag. Legacy lane tagged `adoption_mode="copy_cuda_legacy"` (behavior
otherwise byte-identical). No forced synchronization added beyond the validator's required correctness
comparison.

## 13. Files / functions changed

- `comfymodal_runtime/request_clip_fastsafe.py` — mode constants + `_ADOPTION_DTYPE_PAIRS`;
  `_native_adoption_gates` (classification, `mixed_adoption_modes`, `unsupported_dtype_pair`);
  `_install_native_construction_seams(..., skeleton_device, force_assign)` (parameterized device seam +
  timing-only load_sd capture wrapper); NEW `_validate_cast_once_bind`; `_register_residency(...,
  parameter_bytes)` (wall/reserved/movement); `_produce_clip_fastsafe_native` (mode selection, seam
  branching, true post-construction allocator snapshot, mode-specific validation, early
  `retire_source_owners` release, additive telemetry); legacy producer event tags; docstring.
- `tests/test_r44f_clip_zero_copy.py` — `World.expected_dtype`; BF16-parity rejection test replaced by
  `test_gates_classify_bf16_fp16_as_cast_once` + `test_gates_reject_unsupported_dtype_pair`;
  `native_meta_assign` → `same_storage_assign`; flag-off neutrality asserts `copy_cuda_legacy`.
- `tests/test_r44h1_clip_cast_once.py` — NEW (C1–C10: provenance, classification, end-to-end cast-once,
  accounting buckets, missing-key/value-mismatch/unsupported-pair fail-closed matrix, owner lifetime +
  double-release proof, residency no-movement, legacy neutrality).
- **Zero ComfyUI core edits.**

## 14. Local test evidence

- Focused new/updated suites (after oracle-review fixes): `pytest tests/test_r44f_clip_zero_copy.py
  tests/test_r44h1_clip_cast_once.py -q` → **42 passed**.
- Full focused set (batch §15), run after all fixes: R44A generation determinism, runtime-state reload
  guard, models-volume reload guard, R44B request FastSafe, R44D env passthrough + proof installation,
  R44E durability, R44F zero-copy, R44H1 cast-once, v2 waterfall + waterfall contract →
  **223 passed** (11.66 s).
- `py_compile` on all touched files: ok. `config/v2/profiles/r44-request-fastsafe.toml` TOML parse: ok
  (profile already carries `COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT=1` — no profile change needed).

## 15. Static nominal-path copy audit (post-implementation)

Sweep of `request_clip_fastsafe.py` for `.to( | .cuda( | copy_( | load_state_dict | manual_cast |
model_patches_to | load_model_gpu | model_load | clone | contiguous`:

| Hit | Class |
|---|---|
| docstring/comment mentions of `load_state_dict` (L55, L378, L990, L1455) | documentation |
| L1091 `staged.detach().to(t.dtype).cpu()` | validator value-proof temp (per-tensor, transient, correctness-required) |

Producer path contains **no** `.cuda()`, `copy_()`, `clone()`, `contiguous()`, `manual_cast`
manipulation, or patcher-dtype surgery. The single model-sized transformation is Comfy's own
`load_state_dict(assign=False)` copy-cast inside the constructor; the single model-sized "move"
candidate (`load_models_gpu`) is bookkeeping-only on resident modules and is telemetered with a
movement detector. Nominal diagram (§7) shows: one required transport copy, exactly one cast, zero
model-sized copies afterward. **No unexplained model-sized copy remains.**

## 16. Concurrent-file overlap assessment (vs R44H2)

This batch wrote only: `request_clip_fastsafe.py`, `tests/test_r44f_clip_zero_copy.py`,
`tests/test_r44h1_clip_cast_once.py` (new), this report. R44H2 owns `dynamic_gantt.py`,
`tools/render_dynamic_gantt.py`, `tests/test_r44g1_dynamic_gantt.py`, sampler/post-sampling telemetry.
**Zero file overlap.** Worktree-level concurrent dirty state (other agents' modifications present at
batch start) was preserved untouched; shared files were reread immediately before editing.

## 17. Recommendation for the ONE next remote gate

Run exactly one cold proof gate, profile `r44-request-fastsafe` (unchanged; NATIVE_ADOPT already on),
same workflow/workload as R44E/R44F, canonical SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` must match exactly.

Gate-valid requires ALL of:
1. no `clip_fastsafe_skip`; `bind_mode="cast_once_fp16"`; `adoption_mode="cast_once_fp16"`;
   `checkpoint_dtype="BF16"`; `expected_runtime_dtype="torch.float16"`; `live_parameter_dtype="torch.float16"`;
2. `cast_once_count == checkpoint_tensor_count == 398`; `missing_count==0`; `extra_count==0` (buffers aside);
   `legacy_copy_count==0`; `same_storage_count==0` (honest for this mode);
3. `duplicate_weight_bytes_before_forward == 0`; `owners_retired==1`, `owners_failed==0`;
4. `cuda_allocated_after_source_release_bytes ≈ cuda_allocated_after_construction_bytes − 8.045 GB`;
   peak ≈ staging+live coexistence only;
5. `load_models_gpu(CLIP)`: `model_sized_movement_detected=false`, alloc delta ≈ 0, wall ≪ 2283 ms;
6. `construction_wall_ms` decomposed via `load_sd_wall_ms` (expect order-of-magnitude below 2670 ms);
7. `RuntimeStatus=NOMINAL`; loader observed `fastsafetensors_direct_gpu`; exact SHA match;
   UNET control unchanged (453/453, D15 ordering intact).

If any comparable key is absent from the live TE namespace (remapping edge), the run degrades safely to
the native fallback with a precise `missing_key:*` terminal reason — that outcome would falsify the
name-keyed assumption and must be analyzed before any retry.

Independent adversarial review (@oracle) of the cast-once path, seams hygiene, fail-closed ordering,
and test adequacy was run in this batch. Findings and dispositions:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | BLOCKER | `("F16","torch.bfloat16")` gated as `cast_once_bf16` but producer routed only `cast_once_fp16` to the cast branch → wrong live dtype publishable under a BF16-expecting runtime (not reachable with current profiles; latent) | FIXED: `cast_mode` keys on the `cast_once_*` prefix; bind_mode publishes the selected mode |
| 2 | BLOCKER | Process-global construction seams not serialized across concurrent producers; partial-install leak possible | FIXED: module-level `_SEAM_LOCK` held across install→restore; install/restore hardened per-item |
| 3 | MAJOR | Pinned `sd.py:280-281` registers the patcher inside `CLIP.__init__` when skeleton==load_device, so post-construction failure left a stale registered patcher + dangling owner records | FIXED: `_discard_failed_clip` (unload+de-register, telemetered) + `_detach_partial_owners` run in the fail-closed arm before owner close |
| 4 | MAJOR | `publish_result` preceded `record_observed`; a late failure could leave the fast CLIP published while falling back | FIXED: order is now record_observed → mark_clip_loaded → publish_result (sticky truth first; residual mismatch surfaces honestly at the gate) |
| 5 | MAJOR | Residency movement detector was telemetry-only | ACCEPTED BY DESIGN: runtime fallback after correct construction would strictly worsen latency/memory; the movement flag is durable telemetry and gate-valid condition #5 enforces it |
| 6 | MINOR/MAJOR | Cast validator did not prove live/staged storage independence | FIXED: `data_ptr()` inequality required per comparable key (`aliasing_unexpected`) |
| 7 | NOTE | Validator's value proof performs a transient staging conversion for comparison | ACCEPTED: validation-only temp, documented; not a second conversion into live storage |

New tests pin fixes 1, 3, 4, 6 (F16→BF16 end-to-end, failed-patcher discard, publication-order
failure, aliasing rejection) plus a seam-engagement assertion. All suites re-run green after fixes
(see §14 counts).

---

R44H1_NATIVE_EXPECTED_DTYPE_TRACED = YES
R44H1_CHECKPOINT_DTYPE = BF16
R44H1_RUNTIME_DTYPE = FP16
R44H1_FP16_HARD_REQUIREMENT = NO
R44H1_CURRENT_CAST_LOCATION_IDENTIFIED = YES
R44H1_R44E_CONSTRUCTION_2671MS_EXPLAINED = YES
R44H1_ADOPTION_MODE_SELECTED = CAST_ONCE_FP16
R44H1_SINGLE_MATERIALIZATION_IMPLEMENTED_LOCALLY = YES
R44H1_MODEL_MANAGEMENT_SECOND_COPY_BLOCKED_LOCALLY = YES
R44H1_FULL_STATE_ACCOUNTING = YES
R44H1_FAIL_CLOSED = YES
R44H1_RUNTIME_CODE_CHANGED = YES
R44H1_REMOTE_RUN_PERFORMED = NO
R44H1_READY_FOR_ONE_COLD_PROOF_GATE = YES
