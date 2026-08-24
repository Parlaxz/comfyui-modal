# R44I3 — FINAL ARM A PRODUCTION CHECKPOINT & REPRODUCTION HANDOFF (2026-08-24)

Audience: a fresh agent with ZERO prior context. Everything below was re-read from raw
artifacts immediately before writing; exact values are recovered, not paraphrased.

---

## 1. Exact repository checkpoint

| Item | Value |
|---|---|
| Worktree | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal-r42` |
| Branch | `r42-golden-reconciliation` |
| Pre-commit HEAD | `0c59f46e3238f421378e8852ebc548da815b70af` |
| Final committed HEAD | see verdict block (`R44I3_CHECKPOINT_COMMIT`) |
| Remote | `origin https://github.com/Parlaxz/comfyui-modal.git` |
| Pushed ref | `r42-golden-reconciliation` → `origin/r42-golden-reconciliation` |

`git status` before this batch: 35 tracked-modified files + 60 untracked files (full lists in
§1.3/§1.4). No reset/revert/clean/stash was used at any point.

### 1.1 Files included in the checkpoint commit

Tracked-modified (staged in full — all are part of the tree that produced the proof):
`AGENTS.md`, `__init__.py`, `comfyapp.py`*, `comfymodal_runtime/{clip_conditioning_cache,
clip_fast_hydration_wiring,clip_forward_forensics,clip_qd_reader,contracts,
experiment_result_store,gantt_telemetry,gpu_lane_coordination,modal_app,model_preload,
output_delivery,runtime_bootstrap,runtime_executor,runtime_generation,snapshot_build_manifest,
snapshot_capture_hygiene,speculative_clip_hydration,unet_forward_probe,v2_waterfall}.py`,
`config/v2/flag_registry.toml`, `deploy_and_run_v2_single.bat`, `run_v2_single.bat`,
`tests/{test_v2_waterfall,test_v2_waterfall_contract,test_v2ctl_fingerprints}.py`,
`tools/benchmark_v2_direct.py`, `tools/v2_control/{backend,cli,config,fingerprints,validation}.py`.

Untracked (staged): all `R41_* / R42_* / R43_* / R44A–I3` reports and raw logs;
`comfymodal_runtime/{cache_taxonomy,config_authority,dynamic_gantt,golden_runtime_bridge,
loader_selection,request_clip_fastsafe,request_fastpath,request_unet_fastsafe,runtime_status,
sampler_telemetry}.py`; `comfymodal_runtime/golden/`;
`config/v2/profiles/{r42-golden-qd4,r43-known-fast,r44-request-fastsafe,r44i3-armb-fp16-twin}.toml`;
`tests/golden/`; `tests/test_e40_canonical_authority.py`;
`tests/test_r42_{config_truth,golden_integration}.py`; `tests/test_r42a_*.py`;
`tests/test_r44{a,b,d×2,e,f,g1,h1,h2,h3×2,i1,i2,i3}*.py`;
`tools/{golden_local_benchmark,preconvert_clip_fp16_volume,render_dynamic_gantt}.py`;
and this handoff file.

\* `comfyapp.py` carries concurrent-lane edits authored during R44H3 era. They were present in
EVERY deployed image of the proven campaign (deploys run from this working tree), so excluding
them would make the committed tree differ from the proven state. Preserved deliberately;
authored-by-another-lane is recorded here.

### 1.2 Deliberately excluded and why

| Excluded | Reason |
|---|---|
| `config/v2/profiles/e37-clean-lane-qd4.toml` (dirty +4) | E37 lane profile; NOT in ARM A's inheritance chain (`r44-request-fastsafe → r43-known-fast → r42-golden-qd4 → e29-tracer`). Concurrent E37 work. |
| `.opencode/tmp_h2_fixture_gantt.txt`, `.opencode/tmp_h2_fixture_run/`, `.opencode/tmp_r44e_dynamic_gantt.txt` | Scratch fixtures from earlier diagnostic sessions; not code, not evidence of record. |
| Any other untracked root junk (screenshots, one-off patches/logs predating R41) | Not part of R44 lineage; left untouched for their owners. |

No shared file required hunk-level splitting: every staged file's full dirty delta was present in
the proven deployments.

## 2. Production selection

```
R44I3_PRODUCTION_CLIP_PATH = ARM_A_BF16_SAME_STORAGE
```

Reproduction controls (profile `r44-request-fastsafe`):

```
COMFYMODAL_V2_REQUEST_FASTSAFE=1
COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE=1
COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE_NATIVE_ADOPT=1
COMFYMODAL_V2_REQUEST_UNET_FASTSAFE=1
COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP=1
COMFYMODAL_V2_CLIP_SAME_DTYPE_RESIDENCY=1      # ARM A selector
COMFYMODAL_V2_CLIP_FP16_VOLUME_TWIN absent/0   # ARM B stays OFF
CLIP transport frozen: T8 / B256MiB / bbuf512 (nogds/disable_cache/use_buf_register per base chain)
conditioning_cache = forced_miss ; fresh_required = true ; run_count = 1
expected_output_sha = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
min_containers=0, scaledown_window=4, single-use containers (base chain)
```

Dtype truth table (do NOT rewrite history):

| Quantity | Value | Source |
|---|---|---|
| Native Comfy TE policy dtype | **torch.float16** | `model_management.text_encoder_dtype()` — Comfy policy, not a Qwen requirement |
| Checkpoint dtype | **BF16** | safetensors header, 398 tensors |
| Effective live ARM A dtype | **torch.bfloat16** | parity same-storage bind under explicit override |
| Same-dtype residency override | **enabled (=1)** | our flag; BF16 live is NOT native Comfy default |

Mechanism: BF16 checkpoint → FastSafe direct-GPU CUDA BF16 staging → native CLIP construction on
`torch.device("meta")` skeleton → `load_state_dict(assign=True)` binds the served CUDA tensors →
live weights ARE the staging storage (single residency) → owners retained until ON_DETACH →
`load_models_gpu` bookkeeping only.

## 3. Exact correctness proof (final post-restart ARM A cohort)

Canonical SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
Deploy fingerprint (complete): `275671d962dec7ed904cf06211ecad3f1c1fb451ac5b9da5115dddb31d9c1445`
Image: `im-Sc4Lhx5XUfOKB2CdNlnEBG`

| Run dir | Request ID | Cloud / region | GPU | fresh | Status | SHA |
|---|---|---|---|---|---|---|
| `v2_2026-08-24_21-37-12` | `v2-benchmark-0-22f1972f43f3` | GCP / us-east1 | RTX-PRO-6000 | rc=1 qc=1 | NOMINAL | CANON ✔ |
| `v2_2026-08-24_21-38-23` | `v2-benchmark-0-19ca8bef7898` | AWS / eu-south-2 | RTX-PRO-6000 | rc=1 qc=1 | NOMINAL | CANON ✔ |
| `v2_2026-08-24_21-39-59` | `v2-benchmark-0-44521e1204d5` | AWS / eu-south-2 | RTX-PRO-6000 | rc=1 qc=1 | NOMINAL | CANON ✔ |

All three: unique restored_instance_ids (`ae00c7bc…`, `966439d3…`, `b21a3a5b…`), generation match,
runtime reload = 0, no loader fallback, dynamic_gantt_run_0.txt present.
The third request ID (`19ca8bef7898`) was recovered from `run_0.json` directly.
Earlier same-session ARM A runs (`a36b3524f55a`, `7906f4a148a2`, `bfa9442d98c3`, superseded
deployment ea2f977f…) were NOT pooled into this cohort.

Run artifacts root: `ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\`.

## 4. Exact CLIP residency proof

Per-run fields on `clip_fast_load_start` / `clip_fast_load_end` (all 3 runs identical values):

```
adoption_mode                = same_storage_assign
bind_mode                    = same_storage
checkpoint_dtype             = BF16
native_policy_dtype          = torch.float16
effective_live_dtype         = torch.bfloat16
same_dtype_residency_override= 1
tensor_count_expected        = 398        source_bytes_total = 8044982048
sampled_same_storage_count   = 398/398    non_same_storage_count = 1 (tokenizer blob U8)
parameter_count              = 399 (398 + ctor-owned FP32 logit_scale, outside recipient)
owner_retained               = true       owner_release_point = on_detach_after
parameter_dtypes             = [torch.bfloat16, torch.float32]   # NO stale FP16 materialization
model_sized_movement_detected= false      duplicate bytes before forward = 0
UNET control                 = copied_count=0, sampled_tensor_count=453, same-storage intact
```

Validation is pointer/key metadata only (`_validate_native_bind`) — zero tensor reads on the hot
path. Recipient mapping is derived dynamically by `_resolve_loadsd_recipients` walking
`named_modules()` for verbatim containment; there is NO hardcoded `transformer.` assumption.

Real wrapper chain discovered this batch (supersedes the I1-era single-prefix sketch):

```
cond_stage_model = Flux2TEModel_                      (comfy/text_encoders/flux.py klein_te)
 └─ SD1ClipModel child attribute ".qwen3_4b"          (sd1_clip.py SD1ClipModel.__init__)
     └─ Qwen3_4BModel(SDClipModel)                    flux.py:209
         └─ .transformer = llama.Qwen3_4B             llama.py:1030
             └─ .model = Llama2_  (embed_tokens/layers/norm; lm_head=False)
Outer live key example: qwen3_4b.transformer.model.embed_tokens.weight
```

## 5. ARM B rejection record

Profile `r44i3-armb-fp16-twin` (`RESIDENCY=0`, `FP16_VOLUME_TWIN=1`), twin produced once via
`python tools/v2ctl.py preconvert-clip-fp16 --name qwen_3_4b.safetensors`
(`qwen_3_4b.fp16.safetensors`, 398 tensors, 8 044 981 672 bytes).
Deploy fingerprint (complete): `be8b68e3a688adf842019f80d7276b8344b6e26c791099bbca5a305234f0496e`,
image `im-TKp6Z1hL0GvuG4wdeoUI9l`.

| Run dir | Request ID | Runtime | Output SHA |
|---|---|---|---|
| `v2_2026-08-24_21-57-31` | `v2-benchmark-0-24b0fc6fc43f` | NOMINAL, FP16 same-storage bound | `349aa3d2a9a5d6172d2420d25f0580ba7ed7c688ad8a25ec953cc857b510798c` ❌ |
| `v2_2026-08-24_21-58-42` | `v2-benchmark-0-3b83484a6cc4` | NOMINAL | same ❌ |
| `v2_2026-08-24_21-59-33` | `v2-benchmark-0-91ff1a9857b9` | NOMINAL | same ❌ |

Deterministic wrong SHA ⇒ rejected on exactness. Working hypothesis (unproven, not needed for the
decision): with checkpoint dtype == policy dtype, Comfy selects different TE ops/kernels than the
BF16-checkpoint reference path, changing float summation order. Do NOT invest in ARM B unless the
canonical contract itself changes.

## 6. Retired cast-once lane (frozen evidence)

- Paid failures: `v2-benchmark-0-f3938a3f67bd` and `v2-benchmark-0-c7c9e57ca1ed`, both
  `RuntimeError: bind_dtype_mismatch:model.embed_tokens.weight` → fail-closed → native fallback
  (which itself reproduced canonical SHA both times).
- H3-era failure `missing_key:model.embed_tokens.weight` was fixed by I1's dynamic recipient
  derivation (`_resolve_loadsd_recipients`); the dtype failure that replaced it was never fully
  root-caused remotely despite faithful local reproductions (local real-Comfy probes proved:
  FP16 skeleton pre-load, `can_assign_sd=False` spray, assign=False BF16→FP16 copy-cast works).
- Env-visibility bug found and FIXED systemically: `_runtime_env()` silently dropped any
  `COMFYMODAL_V2_*` flag without a hand-written entry. Now generic namespace passthrough
  (deploy env is v2ctl-sanitized), plus registration in `config_authority.py` and
  `config/v2/flag_registry.toml`. Contract documented in `AGENTS.md`.
- The cast-once `is_dynamic` pin repair remains in the code but only on the retired lane.
- Why abandoned: two paid cycles failed structurally on live-dtype grounds while BOTH same-dtype
  paths succeeded; per-request conversion is strictly dominated by ARM A (zero conversion).
- MUST NOT become the next optimization target.

## 7. Reproduction runbook (v2ctl ONLY — never bare Modal CLI)

Workspace: ACTIVE workspace in `.modal_workspaces.json` is **Testing 6**
(`ws_175a616152c5`). v2ctl injects its credentials automatically (`cli._active_workspace_env()`,
same pattern as `_app_version_number`); the deploy BAT re-verifies workspace identity.

```bat
:: 0) sanity
python tools\v2ctl.py lock status
git -C . rev-parse HEAD

:: 1) deploy ARM A (one deployment per cohort)
python tools\v2ctl.py --profile r44-request-fastsafe --owner <YOURNAME> deploy

:: 2) cold structural gate (repeat x3 for a cohort; NOTHING may change between gates)
python tools\v2ctl.py --profile r44-request-fastsafe --owner <YOURNAME> gate

:: 3) artifacts (per gate):
::    %REPO%\.v2ctl\gates\gate_<ts>_<id>.json          (valid flag, deploy_fingerprint)
::    %REPO%\.v2ctl\deployments\deploy_<ts>_<id>.json  (deploy_fingerprint complete value)
::    ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_<ts>\run_0.json
::    ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_<ts>\dynamic_gantt_run_0.txt
```

Validation checks per run (fields inside `run_0.json`):
- identity: `image_id` matches the deployment's freshly built image; `restore_count=1`,
  `request_count=1`; unique `restored_instance_id`
- status: `"status": "NOMINAL"`; NO `loader_fallback_clip` anywhere
- correctness: output sha256 == `20b10e1f…e5260`
- CLIP residency: `clip_fast_load_start.adoption_mode=same_storage_assign`,
  `effective_live_dtype=torch.bfloat16`, `same_dtype_residency_override=1`,
  `checkpoint_dtype=BF16`, `native_policy_dtype=torch.float16`
- same-storage: `clip_fast_load_end.sampled_same_storage_count=398`, `copied_count=0` (UNET),
  `owner_retained=true`, `model_sized_movement_detected=false`
- sampler: events `sampling_start` (source `direct_sampler_call_boundary`),
  `sampler_first_eval_start`, `sampler_step_ticks`, `sampler_tail`, `sampler_telemetry_status`
  with all hook flags true
- gantt: `dynamic_gantt_run_0.txt` exists, five-way sampler split, no PROXY row

HISTORICAL MISTAKE — do not repeat: a bare `modal run …` bypasses `.modal_workspaces.json`,
lands on the raw CLI default profile (**testing3**, spend-limited) instead of Testing 6, and can
crash on cp1252 (`✓` charmap). Every Modal interaction must go through `python tools/v2ctl.py …`.

ARM B appendix (rejected; do NOT use in production runbooks):
`python tools\v2ctl.py preconvert-clip-fp16 --name qwen_3_4b.safetensors` then deploy/gate with
`--profile r44i3-armb-fp16-twin`.

## 8. Trustworthy performance baseline (metric conflict documented)

The prior report's `application_wall` cohort field (25 923 / 73 230 / 28 023 ms) mixes an
unreconciled timing axis with cold-variance outliers.

**Status: `UNRESOLVED_TIMING_AXIS / DO NOT USE AS NORTH-STAR UNTIL RECONCILED`.**
It is kept in history (prior report §4) but must not be quoted as the app total.

Trusted single-run remote timeline for `v2-benchmark-0-44521e1204d5`
(dir `v2_2026-08-24_21-39-59`; values corroborated from `run_0.json`):

| Boundary | Value |
|---|---|
| Python-resume → output/full remote Gantt | ~17.041 s |
| command → response | ~20.463 s |
| old waterfall cumulative | 11.923 s (NOT a full application total — omits main sampling interval) |
| executor graph span | ~15.79 s |
| restore | ~475 ms method / ~413 ms total |
| restore → method entry | ~156 ms (artifact: 155.525) |
| CLIP inner forward | ~3.964 s |
| legacy outer CLIP encode | ~4.09 s |
| UNET broad H2D | ~1.498 s |
| sampler lane → first visible progress | ~0.922 s |
| visible progress sampling | ~4.260 s |
| sampler tail | ~0.497 s |
| VAE | ~0.440 s (artifact: 439.958) |
| output | ~0.258 s (artifact: 258.46) |

Cohort medians already proven (ARM A, n=3): FastSafe copy 1327.461 · construction/bind ex-load_sd
24.075 · inner forward 3964.9 · outer encode 4018.2 · sampler tail 546.258 · tail GC 510.908 ·
VAE 439.6 · output 253.1 (ms).

## 9. Canonical working Gantt (ASCII)

Axis A — remote Python-resume → durable result (trusted, ~17.0 s class for 44521e…):

```text
Python resume ───────────────────────────────────────────────────────────► durable result
│ restore ▓ 475ms
│ method/setup ▓ ~0.8s
│ graph/CLIP load (FastSafe+bind) █ ~1.4s copy + 24ms bind
│ CLIP forward ██████████████ ~3.96s
│ UNET commit ██ ~1.5s broad-H2D class (target 0.6–0.9s)
│ sampler startup ▌ ~0.92s
│ sampling ███████████████ ~4.26s visible progress
│ sampler tail ██ ~0.50s (GC-dominated)
│ VAE ▌ ~0.44s
│ output ▏ ~0.26s
```

North-star boundary (project definition, separate axis):
`Modal "Restoring Function from memory snapshot." banner → first durable result`.
Do NOT conflate: placement/scheduling · banner→Python-resume · Python-resume→result ·
command→response (~20.5 s class) · post-result cleanup.

## 10. Post-result lifecycle observation

For `44521e…`: request/ledger completes ≈16:40:19.927; a no-request-id
`[v2.clip_conditioning_cache] event=mode` line appears ≈16:40:27.365 (~7.44 s later). Another run
shows ~6.7 s. Label: `POST_RESULT_CONTAINER_ACTIVITY — ROOT CAUSE NOT YET PROVEN`. Possible
lifecycle/billing relevance is an open issue; it is NOT inference latency.

## 11. Next optimization plan (frozen architecture)

```text
RESTORE / EARLY SETUP
│
├── CLIP source hydration       ← MOVE LEFT
│
└── UNET source preparation     ← MOVE LEFT
│
▼
CLIP FORWARD                    ← RUN QUIET / NO SOURCE-PREP CONTENTION
▼
UNET GPU COMMIT                 ← recover ~0.6–0.9 s class
▼
SAMPLER
▼
REQUIRED SAMPLER PACKAGING
├── SKIP/defer gc.collect       ← ~0.5 s candidate
▼
VAE → OUTPUT
```

Preserved lessons: "earliest possible" is NOT automatically correct (E36 poisoned the path);
CLIP has priority; source prep may move left but CLIP forward stays resource-quiet; UNET GPU
commit still waits for CLIP compute; do NOT resurrect Golden QD4 off host-side microbenchmarks
(ARM A uses direct-GPU FastSafe); preserve exactness + same-storage semantics.

## 12. Verdict block

```text
R44I3_PRODUCTION_CLIP_PATH = ARM_A_BF16_SAME_STORAGE
R44I3_ARM_A_EXACT_3_OF_3 = YES
R44I3_ARM_A_RUNTIME_NOMINAL_3_OF_3 = YES
R44I3_ARM_A_CLIP_SAME_STORAGE_398_OF_398 = YES
R44I3_ARM_A_CLIP_COPIED_COUNT = 0
R44I3_ARM_A_MODEL_SIZED_SECOND_MOVEMENT = NO
R44I3_ARM_A_EFFECTIVE_DTYPE = torch.bfloat16
R44I3_ARM_B_REJECTED = YES (deterministic wrong SHA 349aa3d2…798c on 3/3)
R44I3_CAST_ONCE_RETIRED = YES
R44I3_CANONICAL_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
R44I3_TRUSTED_REMOTE_BASELINE_REQUEST = v2-benchmark-0-44521e1204d5
R44I3_TRUSTED_REMOTE_PYTHON_TO_RESULT_MS = 17041
R44I3_APPLICATION_WALL_REPORT_FIELD_STATUS = UNRESOLVED_TIMING_AXIS__DO_NOT_USE_AS_NORTH_STAR_UNTIL_RECONCILED
R44I3_NEXT_PHASE = R44J1 (CLIP-forward-quiet + move-left source hydration/prep + UNET commit recovery + gc defer)
R44I3_CHECKPOINT_COMMIT = 9a428fdb19b958b1b217f8f805055fca56207965
R44I3_CHECKPOINT_PUSHED_REF = origin/r42-golden-reconciliation @ 9a428fdb19b958b1b217f8f805055fca56207965
```
