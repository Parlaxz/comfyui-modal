# R44C — Integrated R44A+R44B Deployment and Single Cold Gate Report

Batch: R44C · Owner: R44C (single integration/deployment owner)
Worktree: `../comfyui-modal-r42` · Branch: `r42-golden-reconciliation` · HEAD: `0c59f46e3238f421378e8852ebc548da815b70af` (unchanged, no commits/push/merge)
Profile deployed: `r44-request-fastsafe` · Exactly ONE deployment · Exactly ONE paid cold request · STOPPED after the gate.

---

## 0. Executive verdict

The combined tree was reconciled and locally verified (132 focused tests green), deployed exactly once, and exactly one true-cold request was executed.

- **R44A (generation determinism) is PROVEN working remotely**: the cold request compared against the final R44 construction state and got `skipped_generation_match / exact_match` with zero reload. This eliminates the `runtime_state_generation_reload` DEGRADED class that hit repeated earlier gates (04:51, 05:40, 15:13 today).
- **R44B (request-time FastSafe) did NOT execute remotely.** All four `COMFYMODAL_V2_REQUEST_*` flags were correctly resolved by the local control plane (=1) but never reached the Modal container: `_runtime_env()` (`modal_app.py:2974`), which builds Modal's class-level `env=` dict, contains explicit passthroughs for every historical flag (including the E28-era FastSafe tuning keys at `modal_app.py:3446-3463`) but was never extended with the four new R44B keys. The container therefore resolved them to default `"0"`, `request_fastpath.enabled()` returned False, `begin()` never ran, and both installers were passive wrappers. The request silently ran the legacy non-Golden composition end-to-end.
- The request itself was healthy: exact expected SHA, RuntimeStatus NOMINAL, canonical ledger ok/zero-gap, no fallbacks recorded.
- Per the batch stop rule, NO repair/redeploy was performed after the paid gate. Evidence preserved below.

```
R44C_R44A_INTEGRATED = YES
R44C_R44B_INTEGRATED = NO
R44C_GENERATION_MATCH = YES
R44C_CLIP_FASTSAFE_EXECUTED = NO
R44C_CLIP_DIRECT_CUDA = NO
R44C_CLIP_NO_SECOND_H2D = NO
R44C_CLIP_FORWARD_MEASURED = YES
R44C_UNET_SOURCE_PREP_EXECUTED = NO
R44C_UNET_FASTSAFE_EXECUTED = NO
R44C_UNET_D15_CLEAN = NO
R44C_UNET_R42_ADOPTION_SUCCESS = NO
R44C_EXACT_SHA = YES
R44C_RUNTIME_STATUS_NOMINAL = YES
R44C_ONE_COLD_GATE_COMPLETE = YES
R44C_READY_FOR_CLIP_RETUNE_OR_COHORT = NO
```

`R44C_R44B_INTEGRATED = NO` is scoped precisely: R44B is integrated and verified IN THE TREE (all §6 checks pass; 23/23 lane tests + 68 waterfall regressions green), but it is NOT integrated with the deployment boundary (`_runtime_env`), so it could not and did not execute on the paid gate. `R44C_UNET_D15_CLEAN = NO` reflects "not established", not "violated": the lane never ran, so no D15 evidence exists either way. No D15 violation occurred (no UNET GPU phase existed).

---

## 1. Repository state at start (recorded, preserved)

- `git rev-parse HEAD` → `0c59f46e3238f421378e8852ebc548da815b70af`
- `git branch --show-current` → `r42-golden-reconciliation`
- `git status --short` → 30 modified + 36 untracked entries (full list in raw log). No reset/revert/clean/stash/checkout used; all unrelated dirty work preserved.

## 2. R44A integration proof (tree inspection)

Verified present and intact in `comfymodal_runtime/runtime_generation.py`:

| Contract item | Evidence |
|---|---|
| `RUNTIME_STATE_VOLATILE_IDENTITY_KEYS` exists | line 112 |
| `_semantic_identity_bytes` canonical projection | line 118 |
| BUILD uses semantic hashing | `build_runtime_state_manifest` → `_identity_sha256_file` (line 187) |
| VERIFY uses identical projection | `verify_runtime_state_manifest` → `_identity_sha256_file` (line 327) |
| `_content_derived_generation` algorithm unchanged | deterministic over semantic manifest (report §4; tests confirm) |
| Reload guard untouched | `runtime_bootstrap.py` carries only pre-existing R42A drift-diagnostic hunks; `_decide_runtime_state_reload` unmodified |

Volatile keys excluded from identity: `captured_at`, `gpu_name` (gpu_capacity_frozen.json), `updated_at` (prescan_custom_nodes.json). Semantic fields (`total_vram_mib`, `custom_node_generation`, …) still alter generation (test-proven).

## 3. R44B integration proof (tree inspection)

| Contract item | Evidence |
|---|---|
| Request context begin in request lifecycle | `modal_app.py:18176-18195` — after `_remote_watcher.start()`, guarded, fail-closed |
| Both installers invoked when master flag resolves | `modal_app.py:18183-18193` (each try/except-passed) |
| Teardown in matching finally | `modal_app.py:18274-18284` (idempotent, bounded join) |
| CLIP critical-end callback hook | `gpu_lane_coordination.py:28` (`register_clip_critical_end_callback`), fired at `end_clip_critical` (line 448) after state release + `record_clip_ready()` |
| Config authority recognizes new arms | `config_authority.py:368-379`: master+role compound resolution returns CLIP `fastsafetensors_direct_gpu` / UNET `fastsafetensors` BEFORE residency arms; Golden branch untouched and first |
| Profile T8/B256MiB/bbuf512 | `r44-request-fastsafe.toml:38-40`; UNET knobs via base chain (`UNET_FASTSAFE_THREADS=8`, `BLOCK_BYTES=268435456`, `BBUF_KB=524288` confirmed in resolved deploy env) |
| Golden/QD/old arms OFF | profile lines 24-33 (ten zeros), confirmed in deployed child env |
| Workload byte-identical | forced_miss, SHA `20b10e1f…`, run_count 1, gap 35.0 |

### 3.1 Pre-spend semantic check: CLIP served-CUDA-dict seam (§7) — PASS, not redesigned

`request_clip_fastsafe._invoke_with_guard` (lines 460-500):
- substitution keyed by `normcase(abspath(path))` of EXACTLY our resolved paths; any other path passes through to the saved original;
- thread-local reentrancy guard (`_GUARD_LOCAL.active`) prevents nested stacking;
- original restored in `finally`, guarded by identity check (`is _guarded_load_torch_file`);
- unrelated `load_torch_file` callers cannot consume the override (target lookup miss → passthrough);
- partial failure → `_fail_closed`: owners closed, claim released, sticky terminal reason, `native_comfy` fallback observation, visible `clip_fastsafe_fallback` telemetry, then original method runs.

### 3.2 Pre-spend semantic check: UNET D15 ordering (§8) — PASS structurally

`request_unet_fastsafe`: source prep armed CPU-only outside any gate (C3) → prep joined BEFORE `_gpu_phase_with_arbitration` (`_inline_after_prep`) → `begin_unet_gpu_phase` acquired only around transfer+adoption, released in `finally` → race arbiter waits on `clip_forward_done_event` and retries once. Holding-across-read / E28 pattern structurally impossible in this code.

### 3.3 Reconciliation repair applied BEFORE deploy (one minimal hunk)

**Defect:** case-b handoff ("clip loaded, forward not done") called `ctx.result("unet")` with `timeout_s=None`. `FastPathRequestContext.result()` does not wait without a timeout, so the wrapper would instantly see `None`, fail-close with `result_future_empty`, fall back to native (double model-sized load) while the daemon continuation still ran the FastSafe pipeline and recorded a contradictory success observation. The code comment documents the opposite intent ("the node wrapper waits on ctx.result('unet')"). No test covered case b (the after-clip test pre-sets forward-done = case a).

**Repair (minimal, implements documented intent):**
```python
payload = ctx.result("unet", timeout_s=_CLIP_FORWARD_WAIT_S)
```
(`request_unet_fastsafe.py`, bounded 120 s, matching the continuation's own bound.) No other file touched. Note: this path was never exercised remotely because the lane disengaged (see §6).

## 4. Local verification counts (pre-deploy gate)

| Suite | Result |
|---|---|
| `tests/test_r44a_generation_determinism.py` | 9 passed |
| `tests/test_runtime_state_reload_guard.py` | 32 passed |
| `tests/test_r44b_request_fastsafe.py` | 23 passed |
| `tests/test_v2_waterfall.py` + `tests/test_v2_waterfall_contract.py` | 68 passed |
| **Total** | **132 passed, 0 failed** (`python -m pytest … -q` → `132 passed in 36.47s`) |
| `py_compile` on all touched R44 modules | clean |
| TOML parse of `r44-request-fastsafe.toml` | OK (`name`, SHA prefix `20b10e1f9983`, master flag `1`) |
| `v2ctl deploy --dry-run` resolution | correct flags/fingerprints |

Known unrelated local-env failures (CacheDiT / huggingface_hub in `test_modal_app_identity.py`) not run, unchanged, proven unrelated per prior batch reports.

## 5. Deployment identity (exactly one deploy)

- Command: `python tools/v2ctl.py deploy --profile r44-request-fastsafe --owner R44C` → exit 0, backend elapsed 626.7 s, version advanced (v2ctl E29 guard passed).
- Manifest: `.v2ctl/deployments/deploy_20260823-182508_b07c5619.json`
- `deploy_fingerprint` = `b07c5619eea7a28cd15123d3e21d57a564a9875517dc5427821a12a6b800ddae`
- `profile_config_fingerprint` = `c1b3170c83268e66edee2bffbe71ad94eb50934e0ddf354848a5624a2dc92646`
- `run_fingerprint` = `2e6038f1d5cb6518bcdf6d355bdddc85341fda48aae65df1aaccab050901c67d`
- Target app `stable-modal-comfy-v2-restore-only-shadow` · class `ModalRuntimeEntrypoint(V2)` · method `run_plan_stream`
- Resources unchanged: rtx-pro-6000, cpu 12, mem 32768 MiB, min_containers 0, scaledown 4, single-use containers 1
- Deployed child env contained all four REQUEST flags = "1" and all ten zeros (raw log §D).

## 6. Generation proof (construction → cold request)

Construction (deploy) wrote the R44A semantic runtime-state token; the single cold request compared against that FINAL state:

```json
runtime_state_reload_decision = {
  "decision": "skipped_generation_match",
  "reason": "exact_match",
  "expected_generation": "87e6cd247f7b287bef69c056e7b607fc",
  "current_generation":  "87e6cd247f7b287bef69c056e7b607fc",
  "file_diff": {},
  "runtime_state_reload_invoked": 0,
  "check_ms": 336.878
}
```

- `reload_runtime_state_ms = 0.0` in restore breakdown. No transitional reload occurred (the previous construction on this Volume lineage had already been replaced by R44A-era constructions during today's earlier deploys; regardless, the required contract "expected == current, skipped_generation_match, no reload" holds against the FINAL R44 construction state).
- Models generation also `skipped_generation_match / exact_match` (`a1e24903d0a1`).
- For contrast, gates at 04:51, 05:40, 15:13 today failed with `[structural] runtime_state_generation_reload` — the R44A repair eliminated this class on this gate.

## 7. THE GATE — one true-cold request

- Command: `python tools/v2ctl.py gate --profile r44-request-fastsafe --owner R44C` (exactly one invocation, run_count=1, forced-miss nonce `04910b79de53475ea65c5ca999b678c1`, fresh_required).
- Backend exit 0. Run artifacts: `comfymodal-data/benchmarks/runs/v2_2026-08-23_23-28-31/` (`run_0.json`, `run_001_sample.json`, `summary.json`).
- Gate manifest: `.v2ctl/gates/gate_20260823-232944_2e6038f1.json`.

### 7.1 Request identity

| Field | Value |
|---|---|
| request_id | `v2-benchmark-0-1ab2fe2f70d2` |
| task id | `ta-01M0RF954H3T8KTPV0F7KEQ96R` (input `in-01M0RF8MYDG1YF67YY01X3PVA8:1787527713741-0`) |
| restored instance | `6988deda94b24c448c26daded6abed4e` (restore session `b7a50fc5247546a183710ea6889db235`) |
| fresh | true · restore_count 1 · request_count 1 |
| provider / region | AWS (`CLOUD_PROVIDER_AWS`) / us-east-2 |
| GPU | NVIDIA RTX PRO 6000 Blackwell Server Edition, 97250 MiB, CUDA 13.0, CC 12.0 |
| visible CPUs | 28 (12 requested) |
| image id | `im-TWYpKWWLW5jMYEEfPQUnue` |
| deployment fingerprint | `b07c5619…` (matches deploy) · profile fp `c1b3170c…` · run fp `2e6038f1…` |
| runtime-state generation | expected == current == `87e6cd247f7b287bef69c056e7b607fc` · reload decision `skipped_generation_match/exact_match` |
| RuntimeStatus | **NOMINAL**, reasons [] |
| exact SHA | **`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`** = expected ✓ |
| conditioning | forced-miss nonce present; `profile_cache_hit=false`; encode_calls = 1 (`clip_raw_encode_calls=[{duration_ms:3418.3}]`); no persist hit (`EXACT_CACHE_PERSIST=false`) |
| ledger | canonical_ledger_status `ok`; endpoint_status `ok`; serial zero_gap `true`; 13 spans |

### 7.2 Structural truth: the R44B FastSafe lane did NOT engage

Remote-resolved controls (container truth, `resolved_config.controls`):

```
COMFYMODAL_V2_REQUEST_FASTSAFE           = False
COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE      = False
COMFYMODAL_V2_REQUEST_UNET_FASTSAFE      = False
COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP   = False
COMFYMODAL_V2_CLIP_FASTSAFE_THREADS      = 8      <- historical knobs DID cross
COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES  = 268435456
COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB      = 524288
COMFYMODAL_V2_UNET_FASTSAFE_THREADS/BLOCK/BBUF = 8 / 268435456 / 524288
```

while the local deploy child env carried `REQUEST_*="1"` (×4). Decisive contrast: local `effective_env` = "1" vs remote `controls` = False ⇒ the flags were lost at the **Modal class-env boundary**.

Root cause (exact): `_runtime_env()` (`comfymodal_runtime/modal_app.py:2974`) builds the dict passed as Modal's class-level `env=` at deploy time. It has explicit `os.environ.get(...)` passthroughs for every historical flag — including the E28 FastSafe tuning keys (`modal_app.py:3446-3463`) — but the four R44B keys were never added. R44B's modal_app changes were limited to the two request-lifecycle hunks; the deploy-boundary hunk does not exist anywhere in the tree (verified by grep: `REQUEST_FASTSAFE` appears in `config_authority.py`, `request_fastpath.py`, and nowhere in `_runtime_env`).

Consequences on this gate (all telemetry-negative):
- No `request_fastpath_begin` / `request_fastpath_end` events.
- `loader_selection`: CLIP requested/effective/observed = `snapshot_resident`; UNET = `cpu_snapshot_native`; VAE = `native_comfy`; `fallback_attempted=false` everywhere. (These are the config-authority fallback labels for a non-Golden composition with exclusion flags off — they do NOT describe physical transport; weights were in fact read from disk at request time, see timings.)
- CLIP was loaded natively from disk: t4 clip load wall **4771 ms**; no FastSafe transport, no served-dict seam, no direct-CUDA descriptor path, no bind-mode proof.
- UNET was loaded natively from disk: t4b wall **9334 ms**; no source-prep overlap, no D15 GPU-phase events, no R42 detection/adoption, no 453/453 storage proof.
- All §14–§17 structural questions are therefore UNANSWERED by this gate — the architecture never executed. Nothing was proven failed about FastSafe itself; the lane was off.

### 7.3 Observed composition timeline (what actually ran)

Wall-clock stages (unix seconds, remote): VAE load 736.512→736.978 (466 ms) → CLIP load 736.980→741.751 (**4771 ms**) → CLIP forward (t5 text encode) 741.751→745.176 (**3425 ms**) → UNET load 745.231→754.565 (**9334 ms**) → model_sampling bind 754.565→754.568 → sampler-node→sampling gap 1441 ms → sampling 756.009→759.740 (**3731 ms**) → post-transition 400 ms → VAE decode 760.140→760.606 (**466 ms**) → output persist/collect ≈ 344 ms.

Fully serial native loading; no overlap existed (nothing to overlap with — lane off).

### 7.4 ASCII Gantt (measured application window, █ bars, 1 char = 250 ms)

```text
scale: 1 char = 250 ms | axis 28.0 s | origin = application restore start
                           +---------+---------+---------+---------+---------+---------+---------+---------+---------+---------+---------+---------
restore                    |███████                                                                                                         |   1630.0 ms
restore->method_entry      |      █                                                                                                         |     34.0 ms
request/method_setup       |      ██████                                                                                                    |   1347.0 ms
VAE load (native)          |            ██                                                                                                  |    466.0 ms
CLIP load (native)         |              ███████████████████                                                                               |   4771.0 ms
CLIP forward               |                                 ██████████████                                                                 |   3425.0 ms
UNET load (native)         |                                               ██████████████████████████████████████                           |   9334.0 ms
model_sampling bind        |                                                                                    █                           |      3.0 ms
sampler_node->sampling     |                                                                                    ██████                      |   1441.0 ms
sampling                   |                                                                                          ███████████████       |   3731.0 ms
post_sampling_transition   |                                                                                                         ██     |    400.0 ms
VAE decode                 |                                                                                                          ███   |    466.0 ms
output persist/collect     |                                                                                                            ██  |    344.0 ms
```

No CLIP-forward/UNET-prep overlap row exists because the request-scoped prep lane was disengaged; the Gantt shows the truthfully serial native composition.

### 7.5 Timing table

| Metric | R43 mean/current | R44C gate | Historical healthy anchor |
|---|---|---|---|
| Application restore | ~1.0–1.6 s class | **1053.8 ms** (+ custom-node source copy 1628.2 ms inside restore method) | sub-2 s |
| Restore exit → method entry | ~34 ms class | 33.9 ms | — |
| Method/setup | ~0.7 s class | 681.8 ms (+ setup-schedule 664.8 ms) | — |
| Prompt executor setup | — | (inside graph lead-in) | — |
| CLIP physical load | n/a (native block) | **4771 ms** (native disk) | ~1.15 s integrated E37 / sub-second FastSafe capability |
| CLIP forward | embedded | **3425 ms** (t5) / clip_raw_encode 3418.3 ms → INTERMEDIATE class (≤3.5 s) | ~1110 ms |
| UNET prep | n/a | not executed (lane off) | sub-second-class / E24 hidden |
| UNET FastSafe file→GPU | n/a | not executed | ~477 ms best E28 |
| UNET construct/adopt | native block | not executed (native load 9334 ms) | ~0.14 s R42 |
| Sampling | ~3716 ms | **3731.0 ms** | ~3.7 s R42 |
| VAE decode | ~413 ms | **465.5 ms** | ~0.38–0.44 s |
| App wall (remote method) | ~26 406 ms | **48 092.4 ms** | historical fast territory |
| command→response | — | **72 299.4 ms** | — |
| Platform scheduling (separate) | — | 21 916.3 ms (submission→python resume) | — |
| Local preparation (separate, informational) | — | 24 044.0 ms | — |

One-run descriptive classification of CLIP forward: **INTERMEDIATE** (2.0 s < 3425 ms ≤ 3.5 s). Not a failure declaration — first gate, and the composition that produced it is the legacy native one, not the R44B target path.

### 7.6 Gate validator results (truthful, not normalized)

`[v2ctl.gate] valid=0` with exactly two failures:

1. `[e37_strict_proof] E37 actual conditioning-cache miss evidence missing` — requires a `clip_conditioning_cache_lookup`/`clip_conditioning_cache_decision` trace event with miss evidence (or a Golden-composition alternative). Neither event exists in this run's 222-event stream.
2. `[e37_clean_lane_proof] CLEAN_LANE_PROOF missing` — the `clean_lane_proof` event is emitted by `clean_lane.mark_forward(phase="end")` from the model_preload clip-forward span wrapper (`model_preload.py:9153`). That wrapper family did not fire in this run.

Anomaly characterization (not repaired, per stop rule): the entire model_preload clip-span instrumentation family (`clip_tokenize/gpu_prepare/raw_encode/scheduled_conditioning/forward` spans, `clip_state_checkpoint`, `clean_lane_proof`, conditioning lookup/decision events) is present in today's earlier GOLDEN-composition gate runs (e.g. 18:12 gate: `clip_forward_start/end`=1, `clean_lane_proof`=1, NOMINAL, reasons []) and completely absent in this non-Golden composition run. Event-histogram diff (18:12 Golden vs R44C): 17 clip/unet/conditioning/clean-lane event names differ, all 1→0. Whether the clip-span wrappers' installation path depends on Golden-context machinery (i.e., a second deployment-boundary/composition gap in the non-Golden path) or on another gate is a REQUIRED follow-up investigation before any retune cohort. What is positively proven despite this: encode_calls=1 with a real 3418 ms encode (forced miss physically happened), plan proof consumed (`plan_validation_fast_path`, reason ""), ledger ok/zero-gap.

Structural/SHA/ledger validators that PASSED: runtime_status NOMINAL, loader observations consistent with requested (no mismatch/unobserved/fallback failures), expected SHA, canonical ledger contract, plan proof, source identity.

## 8. Comparison to R43 and historical anchors

- R43's obstruction (FastSafe lanes unreachable without Golden/RestorePreparation) remains the operative reality on the remote because R44B never engaged; this gate therefore behaves like a non-Golden R43-lineage run, not like the intended R44 architecture.
- Versus R43 mean app wall (~26.4 s): this gate's 48.1 s remote wall is much slower — dominated by fully-native cold loads (CLIP 4.77 s + UNET 9.33 s serial) plus a 21.9 s platform scheduling interval and 24.0 s local preparation interval that are charged outside the accounted application window. One cold run; no statistical weight; restore itself was fast (1.05 s) and clean.
- Versus E37/E28 anchors: CLIP forward 3425 ms vs ~1110 ms anchor (INTERMEDIATE); UNET native load 9334 ms vs ~477 ms FastSafe class; sampling 3731 ms matches the stable ~3.7 s R42 baseline; VAE decode 465.5 ms within the 0.38–0.44 s band (slightly above, observational).

## 9. Anomalies register (all preserved, none repaired post-gate)

1. **BLOCKING (root cause of missed architecture): four R44B env keys missing from `_runtime_env()` Modal class-env passthrough** (`modal_app.py:2974`; cf. historical keys at 3402-3477). Fix shape: add the four `COMFYMODAL_V2_REQUEST_*` passthroughs next to the E28 tuning block, redeploy, re-gate. One-hunk-class change; deliberately NOT done in this batch.
2. **Fixed pre-deploy:** case-b `result_future_empty` immediate-fallback race in `request_unet_fastsafe.py` (see §3.3). Would have corrupted any FastSafe-engaged run whose node order is CLIPLoader→UNETLoader→CLIPTextEncode.
3. **Missing clip-span/clean-lane/conditioning instrumentation under non-Golden composition** → the two strict-proof validator failures. Needs its own investigation (installation path of `_ensure_core_wrappers`/clip-span family in non-Golden compositions).
4. **Latent (unexercised):** profile sets `CHECKPOINT_PREWARM_THREADS="0"`/`CHUNK_MB="0"`; `arm_unet_source_prep` clamps `"0"` via `max(1, …)` → request-scoped prep would run 1 thread / 1 MiB chunks (functional but slow; affects future overlap quality only).
5. **Latent (unexercised):** `join_unet_source_prep` computes a deadline but never passes remaining time into `before_demand_load()`/`stop_and_join_before_demand()`; bounded in practice by the prewarmer's internal `join_timeout_ms` (default 1000 ms, clamp 60 s).
6. Cosmetic: deploy-only manifests bind stale benchmark run dirs via artifact discovery (no run exists for deploy-only invocations); `console_capture=None` for deploy mode.
7. Label honesty: `snapshot_resident`/`cpu_snapshot_native` observed labels describe config-authority arm selection, not physical transport; actual transport this gate was native disk reads (timings prove it). Recorded as-is; no normalization attempted.

## 10. Stop condition compliance

- Exactly one deployment (one v2ctl deploy; zero redeploys).
- Exactly one paid request (single v2ctl gate invocation; no warmers, no probes, no source/model-value reads, no SHA sweeps, no second request).
- No repairs, redeploys, tuning, or cohort runs after the gate.
- No commits/pushes/merges; worktree dirty state preserved (plus the two report files and one intentional source hunk from §3.3).

## 11. Required next step (for the user's decision)

Add the four REQUEST_* keys to `_runtime_env()` (`modal_app.py`, alongside the E28 block), rerun the 132-test focused suite + `v2ctl deploy --dry-run`, redeploy once, and re-run ONE cold gate. Only then can §§14–17 of the batch contract be answered with remote evidence.

— R44C, stopped after the single cold gate.
