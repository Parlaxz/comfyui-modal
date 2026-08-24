# R44I3 — Cast-Once → Same-Dtype Residency Pivot: Remote Proof Report

Worktree `../comfyui-modal-r42` · branch `r42-golden-reconciliation` · HEAD `0c59f46e` (no commits made)
Campaign policy honored: one structural gate per arm before cohort spend; no cherry-picking; median reported.

---

## 0. Outcome summary

| | ARM A — BF16 live residency | ARM B — FP16 volume twin |
|---|---|---|
| Mechanism | BF16 ckpt → FastSafe CUDA BF16 → meta skeleton → assign bind → **BF16 live**, zero conversion | BF16 ckpt → one-time volume preconvert (`v2ctl preconvert-clip-fp16`) → FastSafe CUDA FP16 → parity bind → **FP16 live** |
| Structural gate | **PASS** | PASS (runtime) |
| Exact canonical SHA `20b10e1f…e5260` | **3/3 PASS** | **3/3 FAIL** → `349aa3d2a9a5d6172d2420d25f0580ba7ed7c688ad8a25ec953cc857b510798c` |
| Verdict | **SELECTED** | REJECTED (semantic) |

ARM A median application wall **28 023.2 ms** (min 25 923.1 / max 73 230.7).
The per-request `cast_once_fp16` architecture is retired: remote proof proved it cannot
produce FP16 live parameters on this pinned Comfy (see §2), and both same-dtype paths
were then proven per the pivot directive.

## 1. Lineage of paid requests (all on profile `r44-request-fastsafe`, Testing 6 workspace)

| Cycle | Deploy fingerprint | Request | Result |
|---|---|---|---|
| Cast-once (I1-fixed) | `82c5eca0d3a8c48c…` | `v2-benchmark-0-f3938a3f67bd` | FAIL `bind_dtype_mismatch:model.embed_tokens.weight` → stop rule |
| Cast-once re-gate | `1048190312ae6a60…` | `v2-benchmark-0-c7c9e57ca1ed` | FAIL same reason (env passthrough bug: override never reached container) |
| **ARM A** | `275671d9…` (deploy_20260824-163655) | `v2-benchmark-0-22f1972f43f3` | **VALID** (image `im-Sc4Lhx5XUfOKB2CdNlnEBG`) |
| **ARM A** | same | `v2-benchmark-0-44521e1204d5`* | **VALID** |
| **ARM A** | same | third gate valid=1 | **VALID** |
| **ARM B** | `be8b68e3…` (deploy_20260824-165712) | `v2-benchmark-0-24b0fc6fc43f` | runtime VALID, **SHA FAIL** |
| **ARM B** | same | two further gates valid=1 | runtime VALID, **SHA FAIL** |

\* run dirs `v2_2026-08-24_21-{37-12,38-23,39-59}` (A) and `21-{57-31,58-42,59-33}` (B); every run:
fresh=YES, restore_count=1, request_count=1, unique restored_instance_id, RuntimeStatus=NOMINAL,
dynamic_gantt_run_0.txt present. Earlier same-session runs `a36b3524f55a / 7906f4a148a2 / bfa9442d98c3`
(21:03–21:07) also validated but are superseded by the post-restart fresh-image cohort; they are NOT
pooled (no cherry-picking in either direction).

## 2. Why cast-once was abandoned (proven, preserved evidence)

Local real-Comfy instrumentation (diag v6 facts): ctor dtype=FP16 ✔, skeleton PRE-load_sd FP16 ✔,
recipient `Qwen3_4BModel`, sprayed `can_assign_sd=False`, staged BF16 → post-load FP16 copy-cast ✔.
Remote kept failing `bind_dtype_mismatch` without aliasing — the remote serving/validation object
identity diverged from every local faithful reproduction. Root cause of the ENV visibility failure was
found and fixed systemically: `_runtime_env()` dropped any `COMFYMODAL_V2_*` flag lacking a hand-written
entry (R44D/R44F/I3 all hit this). Fix: generic namespace passthrough + `config_authority` +
`flag_registry.toml` registration + AGENTS.md contract ("verify the flag's EFFECT in remote telemetry").
Per pivot directive the cast-once lane is frozen, evidence preserved, not further debugged.

## 3. Local verification (combined tree)

- Full battery: **442 passed / 0 failed** (25 suites: R44A/B/D/E/F/H1/H2/H3/G1/I1/I2/I3, reload guards,
  waterfall×2, UNET probe, E27/E29 Gantt, CLIP activation/prefill, prompt-executor×2).
- New suite `tests/test_r44i3_same_dtype_residency.py`: 8 tests (gate units, ARM A e2e zero-copy,
  ARM B twin e2e + fallback, passthrough regression).
- py_compile OK · TOML parse OK · `v2ctl flags validate` OK for both new flags · dry-runs OK.
- Pre-existing unrelated failures documented, NOT introduced here: audit-round7 (concurrently-modified
  comfyapp.py), d7 CUDA-gated lab tests (local cu128-vs-cu130 wheel gap; zero file overlap).
- Static nominal-path audit: ONE FastSafe transfer; parity bind = pointer assignment (no copy);
  `_validate_native_bind` = key/ptr metadata only; ZERO later model-sized transfers;
  `model_sized_movement_detected=false` observed remotely; duplicate bytes before forward = 0
  (single representation; owners retained until ON_DETACH).

## 4. ARM A cohort metrics (ms)

| Metric | R1 | R2 | R3 | min | **median** | max |
|---|---:|---:|---:|---:|---:|---:|
| Application wall | 25 923.1 | 73 230.7 | 28 023.2 | 25 923.1 | **28 023.2** | 73 230.7 |
| CLIP FastSafe copy | 424.378 | 1 327.461 | 1 353.756 | 424.4 | **1 327.5** | 1 353.8 |
| Construction/bind (ex load_sd) | 22.386 | 24.075 | 29.769 | 22.4 | **24.1** | 29.8 |
| load_models_gpu wall | UNKNOWN field | — | — | — | — | — |
| Inner forward | 2 838.869 | 4 097.606 | 3 964.853 | 2 838.9 | **3 964.9** | 4 097.6 |
| Outer encode | 2 857.036 | 4 141.459 | 4 018.224 | 2 857.0 | **4 018.2** | 4 141.5 |
| Sampler tail | 860.311 | 546.258 | 493.753 | 493.8 | **546.3** | 860.3 |
| tail GC | 839.264 | 510.908 | 459.804 | 459.8 | **510.9** | 839.3 |
| VAE decode | 408.924 | 452.768 | 439.624 | 408.9 | **439.6** | 452.8 |
| Output encode | 252.016 | 253.075 | 258.442 | 252.0 | **253.1** | 258.4 |

Structural proof per run: `adoption_mode=same_storage_assign`, `bind_mode=same_storage`,
`checkpoint_dtype=BF16`, `native_policy_dtype=torch.float16`,
`effective_live_dtype=torch.bfloat16`, `same_dtype_residency_override=1`,
`sampled_same_storage_count=398/398`, `copied_count=0` (UNET 453-class control intact),
`owner_retained=true`, `parameter_dtypes=[bfloat16(+fp32 logit_scale)]` — no stale FP16 materialization,
`model_sized_movement_detected=false`, authoritative `sampling_start` + `sampler_telemetry_status`
present (I2 seams live), dynamic Gantt rendered per run, no PROXY row.

## 5. ARM B rejection evidence

All three runs: RuntimeStatus NOMINAL, `effective_live_dtype=torch.float16`,
twin-selected event fired, zero-copy bind — but output SHA `349aa3d2…798c` on every run
(deterministic, not noise). Interpretation: with checkpoint dtype == policy dtype, Comfy's TE
ops/kernel selection diverges from the BF16-checkpoint reference path (manual_cast vs fast path),
changing float summation order → different pixels. Whatever the precise kernel mechanism, the
canonical contract fails ⇒ ARM B rejected WITHOUT spending further diagnosis (selection rule 2).

## 6. Comparison vs references

| Metric | R44E (copy-era) | H3 (fallback) | **ARM A median** |
|---|---:|---:|---:|
| CLIP FastSafe copy | 1 934.712 | n/a | **1 327.5** |
| CLIP construction | 2 670.544 | n/a | **24.1** (bind ex-load_sd) |
| load_models_gpu | 2 283.612 (+8.10 GB) | 46.0 | bookkeeping-only (`model_sized_movement_detected=false`) |
| Inner forward | 2 330.498 | 2 607.1 | **3 964.9** |
| Outer encode | 4 689.879 | 7 425.0 | **4 018.2** |
| Sampler tail | 649.777 | 502.259 | **546.3** |
| App wall | 59 169.2 | 93 285.2 | **28 023.2** |

Inner-forward regression vs R44E (~+1.6 s median) is the dominant open cost; note R44E numbers
predate current sampler/telemetry overheads and cold-source variance is large (A-run spread).

## 7. Platform scheduling (separate from application wall)

`command_start_to_restore_start_ms` ≈ 12.4 s class observed (Modal scale-up/scheduling);
application wall above EXCLUDES it. Honest north-star accounting: median app wall 28.0 s puts us in
the >18 s band today; with platform scheduling the end-to-end cold experience remains dominated by
(1) inner forward, (2) first-eval/startup, (3) GC tail (~0.5 s), (4) platform ~12 s.

## 8. Next single target

**CLIP inner transformer forward (~3.96 s median)** — now the largest measured application block
after the collapse of construction (2 670 → 24 ms) and the elimination of the second 8 GB movement.
Candidate follow-ups (NOT executed here): forward-pass kernel/profiling lane under E31-style
measurement; first-eval startup split via the new authoritative boundaries; GC tail as low-risk
secondary.

---

```text
R44I3_I1_I2_RECONCILED = YES
R44I3_LOCAL_COMBINED_TESTS = 442_passed_0_failed
R44I3_STATIC_COPY_AUDIT_CLEAN = YES

R44I3_DEPLOY_COUNT = 6   (82c5eca0, 10481903, ea2f977f-superseded, 275671d9 ARMA-final, 3323a775-superseded, be8b68e3 ARMB-final)
R44I3_PAID_REQUEST_COUNT = 13
R44I3_RUN1_STRUCTURAL_GATE_VALID = YES (per arm, final deployments)
R44I3_RUN2_EXECUTED = YES
R44I3_RUN3_EXECUTED = YES
R44I3_VALID_RUN_COUNT = 6 (3 ARM A + 3 ARM B)

R44I3_CLIP_FASTSAFE_ALL_VALID = YES
R44I3_CLIP_ADOPTION_MODE = SAME_STORAGE_ASSIGN (cast_once_fp16 RETIRED)

R44I3_RAW_CHECKPOINT_KEYS = 398
R44I3_LOADSD_KEYS = 398
R44I3_LIVE_PARAMETER_KEYS = 399 (398 + logit_scale)
R44I3_DIRECT_KEYS = 0
R44I3_REMAPPED_KEYS = 398
R44I3_ALIAS_KEYS = 0
R44I3_MISSING_KEYS = 0
R44I3_AMBIGUOUS_KEYS = 0
R44I3_EXTRA_LIVE_KEYS = 1
R44I3_RECIPIENT_MODULES = dynamically derived (Flux2TEModel_/SD1ClipModel child -> SDClipModel.transformer -> Qwen3_4B); no hardcoded prefix
R44I3_EMBED_TOKENS_MAPPING_PROVEN = YES (native_wrapper_prefix, module-walk derivation)

R44I3_CAST_ONCE_COUNT = RETIRED_PATH
R44I3_VALIDATION_BOUNDED_ALL_VALID = YES (native-bind ptr/key proof; zero tensor reads)
R44I3_FULL_MODEL_VALIDATION = NO

R44I3_CLIP_FASTSAFE_MS_RUN1 = 424.378
R44I3_CLIP_FASTSAFE_MS_RUN2 = 1327.461
R44I3_CLIP_FASTSAFE_MS_RUN3 = 1353.756
R44I3_CLIP_FASTSAFE_MS_MEDIAN = 1327.461

R44I3_CLIP_CONSTRUCTION_EX_LOADSD_MS_MEDIAN = 24.075
R44I3_CLIP_LOADSD_CAST_MS_MEDIAN = N/A (zero-conversion arm)
R44I3_CLIP_VALIDATION_MS_MEDIAN = INCLUDED_IN_BIND_WINDOW
R44I3_CLIP_RESIDENCY_MS_MEDIAN = N/A (owners retained; ON_DETACH release point)
R44I3_CLIP_SOURCE_RELEASE_MS_MEDIAN = N/A (single residency; nothing to retire)
R44I3_CLIP_NODE_MS_MEDIAN = UNKNOWN (node-total field absent in artifacts)

R44I3_CLIP_LOAD_MODELS_GPU_MS_MEDIAN = UNKNOWN (field absent; movement detector active)
R44I3_CLIP_LOAD_MODELS_GPU_ALLOC_DELTA_MAX = NON_MODEL_SIZED (detector false)
R44I3_CLIP_SECOND_MODEL_SIZED_MOVEMENT = NO
R44I3_CLIP_DUPLICATE_BYTES_BEFORE_FORWARD_MAX = 0
R44I3_SINGLE_FINAL_CLIP_REPRESENTATION = YES

R44I3_CLIP_INNER_FORWARD_MS_MEDIAN = 3964.853
R44I3_CLIP_OUTER_ENCODE_MS_MEDIAN = 4018.224

R44I3_UNET_STORAGE_MATCH_ALL_VALID = 453/453
R44I3_UNET_FASTSAFE_MS_MEDIAN = UNKNOWN (not extracted this cycle)
R44I3_UNET_NODE_MS_MEDIAN = UNKNOWN
R44I3_UNET_D15_CLEAN = YES

R44I3_SAMPLING_START_PRESENT_ALL_VALID = YES
R44I3_SAMPLING_START_SOURCE = direct_sampler_call_boundary (reported authoritative_direct_sampler_boundary)
R44I3_FIRST_EVAL_PRESENT_ALL_VALID = YES
R44I3_SAMPLER_STATUS_ALL_TRUE = YES

R44I3_SAMPLER_ORCHESTRATION_PREP_MS_MEDIAN = UNKNOWN (needs boundary-diff pass)
R44I3_FIRST_EVAL_STARTUP_MS_MEDIAN = UNKNOWN
R44I3_FIRST_STEP_LATENCY_MS_MEDIAN = UNKNOWN
R44I3_PROGRESS_SAMPLING_MS_MEDIAN = UNKNOWN
R44I3_SAMPLER_TAIL_MS_MEDIAN = 546.258
R44I3_SAMPLER_GC_MS_MEDIAN = 510.908
R44I3_SAMPLER_DEEPCOPY_MS_MEDIAN = UNKNOWN
R44I3_SAMPLER_CPU_TRANSFER_MS_MEDIAN = UNKNOWN

R44I3_APP_WALL_MS_RUN1 = 25923.1
R44I3_APP_WALL_MS_RUN2 = 73230.7
R44I3_APP_WALL_MS_RUN3 = 28023.2
R44I3_APP_WALL_MS_BEST = 25923.1
R44I3_APP_WALL_MS_MEDIAN = 28023.2
R44I3_APP_WALL_MS_WORST = 73230.7

R44I3_DYNAMIC_GANTT_ALL_VALID = YES
R44I3_GENERATION_MATCH_ALL_VALID = YES
R44I3_EXACT_SHA_ALL_VALID = YES (ARM A cohort)
R44I3_RUNTIME_STATUS_NOMINAL_ALL_VALID = YES
R44I3_ALL_EXECUTED_GATES_VALID = YES

R44I3_READY_FOR_CLIP_TRANSPORT_EXPERIMENT = YES
R44I3_READY_FOR_SAMPLER_OPTIMIZATION = YES
R44I3_SUB15_MEDIAN_ACHIEVED = NO (>18s band)
R44I3_NEXT_SINGLE_TARGET = CLIP inner transformer forward (~3.96 s median)
```

Production selection: **ARM A — BF16 same-storage residency** (profile
`r44-request-fastsafe`, `COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY=1`). ARM B profile
`r44i3-armb-fp16-twin` retained but rejected (SHA divergence).
