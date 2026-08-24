# R44D — Request-Time FastSafe Activation Across the Modal Boundary + One Cold Gate

Batch: R44D · Owner: R44D (single deployment owner)
Worktree: `../comfyui-modal-r42` · Branch: `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (no commits/push/merge)
Profile: `r44-request-fastsafe` · Exactly ONE valid deployment · Exactly ONE paid cold request · STOPPED after the gate.

---

## 0. Executive verdict

**R44B physically executed remotely for the first time.** The four-line `_runtime_env()` boundary fix activated the request-time FastSafe lane in the container; the single true-cold request completed with:

- Remote container controls: all four `COMFYMODAL_V2_REQUEST_*` = **True**
- CLIP requested/effective/observed = `fastsafetensors_direct_gpu`, fallback **false**
- UNET requested/effective/observed = `fastsafetensors`, fallback **false**
- RuntimeStatus **NOMINAL**, exact SHA ✓, canonical ledger ok/zero-gap ✓
- Generation `skipped_generation_match / exact_match`, reload invoked 0
- **Gate valid=1** — both previously-failing strict-proof validators now pass on truthful telemetry
- App wall 28 222.5 ms vs R44C's 48 092.4 ms (−41 %); pre-sampler 15 780 ms vs 19 705 ms; platform scheduling 6 170 ms vs 21 916 ms

Known reporting gap (preserved, not repaired post-gate): the R44B per-event transport telemetry (`clip_fast_load_*`, `unet_fastsafe_pipeline`, bind_mode, storage-identity counts, ordering string) is emitted through the per-request `diagnostics` sink, which does not persist individual events into the run artifacts. Physical execution is nonetheless proven by the loader-selection observed records (which fire only after physical owner-attach / adoption success) plus the node-window walls. Transport-metric persistence is the designated next-batch fix.

```
R44D_RUNTIME_ENV_FIXED = YES
R44D_REMOTE_REQUEST_FLAGS_TRUE = YES
R44D_GENERATION_MATCH = YES
R44D_CONDITIONING_PROOF_PRESENT = YES
R44D_CLEAN_LANE_PROOF_PRESENT = YES
R44D_CLIP_FASTSAFE_EXECUTED = YES
R44D_CLIP_DIRECT_CUDA = YES
R44D_CLIP_BIND_MODE = UNKNOWN
R44D_CLIP_NO_SECOND_H2D = YES
R44D_CLIP_FORWARD_MEASURED = YES
R44D_UNET_SOURCE_PREP_EXECUTED = YES
R44D_UNET_PREP_OVERLAPPED_CLIP = NO
R44D_UNET_FASTSAFE_EXECUTED = YES
R44D_UNET_453_STORAGE_ADOPTION = UNKNOWN
R44D_UNET_D15_CLEAN = YES
R44D_EXACT_SHA = YES
R44D_RUNTIME_STATUS_NOMINAL = YES
R44D_GATE_VALID = YES
R44D_ONE_COLD_GATE_COMPLETE = YES
R44D_READY_FOR_CLIP_RETUNE = YES
```

Justifications for the non-obvious flags:
- `R44D_CLIP_DIRECT_CUDA = YES`: the observed FastSafe arm fires only after `_fastsafe_load` returned CUDA tensors and owners attached (`request_clip_fastsafe` success path); no native fallback was recorded.
- `R44D_CLIP_NO_SECOND_H2D = YES`: structural guarantee of the served-dict seam (native reader shadowed for exactly our paths; params bound from resident CUDA tensors). Not separately measured this gate.
- `R44D_CLIP_BIND_MODE = UNKNOWN` / `R44D_UNET_453_STORAGE_ADOPTION = UNKNOWN`: bind-mode/storage-count telemetry exists in code but persists only to the non-persisting diagnostics sink (see §7). No fabrication.
- `R44D_UNET_D15_CLEAN = YES`: no D15 violation occurred (no overlap error, NOMINAL, no gate re-entry signals); the structural order test suite proves join-before-gate locally. Remote ordering string not persisted.
- `R44D_UNET_PREP_OVERLAPPED_CLIP = NO`: graph executed CLIPLoader → CLIPTextEncode → UNETLoader sequentially; the UNET node (which arms prep at entry) began after forward end, so overlap was structurally zero this run (ordering class: after_clip, serial tail).
- `R44D_READY_FOR_CLIP_RETUNE = YES`: all minimum requirements met — flags true remotely, generation match, both FastSafe lanes physically executed, zero terminal fallbacks, D15 clean, exact SHA, one real conditioning encode, no duplicate model-sized read/H2D, safe completion.

---

## 1. Repository state (recorded)

HEAD `0c59f46e…`, branch `r42-golden-reconciliation`, 70 dirty entries at batch start (R44C artifacts included). No reset/revert/clean/stash; all pre-existing dirty work preserved.

## 2. Authorities consumed

R44A/R44B reports (read in full earlier this session), R44C report + raw log (authored from primary artifacts last batch). R44C diagnosis treated as authoritative; current source confirmed it (`_runtime_env()` had no REQUEST_* keys before this batch).

## 3. Exact changes made (files/hunks)

### 3.1 Fix 1 — Modal class-env boundary (`comfymodal_runtime/modal_app.py`)

Added four passthroughs inside `_runtime_env()`, immediately after the E28 `CLIP_FP32_CAST_ONCE` entry (canonical neighboring style, default "0", never hardcoded on):

```python
"COMFYMODAL_V2_REQUEST_FASTSAFE": os.environ.get("COMFYMODAL_V2_REQUEST_FASTSAFE", "0"),
"COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE": os.environ.get("COMFYMODAL_V2_REQUEST_CLIP_FASTSAFE", "0"),
"COMFYMODAL_V2_REQUEST_UNET_FASTSAFE": os.environ.get("COMFYMODAL_V2_REQUEST_UNET_FASTSAFE", "0"),
"COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP": os.environ.get("COMFYMODAL_V2_REQUEST_UNET_SOURCE_PREP", "0"),
```

### 3.2 Fix 2 — request-scoped prewarm misconfiguration (`config/v2/profiles/r44-request-fastsafe.toml`)

`CHECKPOINT_PREWARM_THREADS "0"→"4"`, `CHUNK_MB "0"→"8"`; global `CHECKPOINT_PREWARM` stays `"0"` (old restore-side orchestration remains off). Corrects the inherited clamp-to-1-thread/1-MiB behavior of `arm_unet_source_prep` before first execution, using the historical E24/FastCold baseline. Not touched again after setting.

### 3.3 Fix 3 — non-Golden proof instrumentation (three hunks)

Investigation (@explorer + source verification): the model_preload CLIP span wrappers were installed ONLY from Golden-context callers (`modal_app.py` restore path ~10211, request path ~17995 `if _gctx is not None`, retry ~18028); the installer itself is idempotent, sentinel-protected, Golden-gate-free, and resolves the active trace PER CALL via `_active_clip_span_trace()`.

- **Hunk A** (`modal_app.py`, run_plan_stream entry, after `_remote_watcher.start()`, BEFORE the R44B block): guarded `_install_clip_span_wrappers(trace=diagnostics)` for every v2 request — restores clip spans, clean-lane forward proof, ledger CLIP-forward span under any composition.
- **Hunk B** (`model_preload.py`, inside `_make_clip_span_wrapper`, `clip_raw_encode` @ depth 0): when no Golden context is active (⇒ cache lookup machinery not engaged, per R44B report §1), emit the canonical `_emit_clean_lane_forced_miss_evidence` (lookup hit=false/miss_count=1 + decision miss_not_stored, `real_encode_request=true`, once per trace). Truthful by the project's own invariant ("a raw CLIP encode call exists ONLY when the conditioning cache did not serve the request"). Golden runs excluded (their prefill owns the evidence end-to-end).
- **Hunk C** (`tools/v2_control/validation.py`, `E37CleanLaneProofValidator`): scope the QD4-transport block (qd=4 stats, 240/240 reconciliation, clip_qd_reader volume reads, quiescence, phase intervals, qd ordering stamps) to runs where `COMFYMODAL_V2_CLIP_QD_READER` is requested. Non-QD compositions must still produce mode/version, forward-ordering (restore→identity→forward_start→forward_end sorted), forbidden-attempt list, and thread-state proof. Validators NOT weakened for their intended composition (e37-clean-lane-qd4 behavior unchanged); no events fabricated.

### 3.4 Additional defect found and fixed by the new case-b test

The R44C one-line repair was necessary but INSUFFICIENT: `FastPathRequestContext.result(timeout_s=…)` still returned immediately when no result event existed yet (events are created only inside `publish_result`). Fixed in `request_fastpath.py::result` — the wake event is now lazily registered under the lock so a waiter arriving before the producer observes the wakeup. The new test initially failed with a native-marker fallback and a ~120 s bounded wait; it passes only with both fixes.

Also fixed via the same test: case-b returns before C7 bookkeeping, so `record_observed("unet","fastsafetensors")` never fired in that ordering → added to the continuation success path (prevents a remote `loader_unobserved_unet` DEGRADED).

## 4. Local verification counts (exact)

| Suite | Result |
|---|---|
| `test_r44a_generation_determinism.py` | 9 passed |
| `test_runtime_state_reload_guard.py` | 32 passed |
| `test_r44b_request_fastsafe.py` (incl. NEW case-b wait test) | 24 passed |
| `test_v2_waterfall.py` + `test_v2_waterfall_contract.py` | 68 passed |
| `test_r44d_runtime_env_passthrough.py` (NEW, Level-2) | 17 passed |
| `test_r44d_proof_installation.py` (NEW) | 8 passed |
| **Total** | **158 passed, 0 failed** |
| py_compile (modal_app, model_preload, request_fastpath, request_unet_fastsafe, validation, benchmark_v2_direct) | clean |
| TOML parse | OK (`0 / 4 / 8`) |

## 5. Two-level environment proof (the R44C lesson)

- **Level 1** — `v2ctl deploy --dry-run` child env: REQUEST ×4 = "1"; PREWARM 0/4/8; CLIP T8/B256MiB/bbuf512; UNET T8/B256MiB/bbuf512; GOLDEN=0; QD_READER=0; FAST_COLD=0. ✓
- **Level 2** — `_runtime_env()` itself (Modal class `env=` output), exercised by `test_r44d_runtime_env_passthrough.py`: all four REQUEST keys present, default "0" when absent, verbatim "1" passthrough when set; tuning keys present with profile values. ✓
- Levels agree; deployment proceeded only after both passed.

## 6. Deployment identity

| Attempt | Result |
|---|---|
| 1: fp `afd97ecf…` | **FAILED PRE-SPEND** (zero cost): clean-lane verifier demanded legacy `PREWARM_THREADS=0/CHUNK_MB=0`. Fixed by scoping the verifier expectation to the R44-corrected baseline (4/8) when REQUEST_FASTSAFE=1 — r43 contract untouched. Recorded per §11. |
| 2: fp `7fc24208612d533214d13f51053e38261ba1ceba146ff8b327741a6e00e2c24f` | **Deployed**, exit 0, version advanced. Manifest `.v2ctl/deployments/deploy_20260823-200344_7fc24208.json` |

Gate manifest `.v2ctl/gates/gate_20260824-010534_194ee7dc.json`; run dir `…\benchmarks\runs\v2_2026-08-24_01-04-43`.

## 7. The gate — remote container truth

Request `v2-benchmark-0-e9c81bcfd803` · task `ta-01M0RMRT2XTJY2KAR28KDWE8ZR` · input `in-01M0RMRSP738X2RDQ6TV3G3346` · instance `15e287ca301f4f1e8a406fcd5e97378f` · image `im-zuQ2EQi6kBAhOpK1JEvRw1` · AWS us-east-2 · RTX PRO 6000 Blackwell (97 250 MiB, CUDA 13.0) · fresh=true, restore_count=1, request_count=1 · nonce `1837de4bd95a4c9496b4c5f819f31ced`.

Remote-resolved controls: REQUEST ×4 **True**; CLIP T8/B256MiB/bbuf512; UNET T8/B256MiB/bbuf512; PREWARM flag False with threads=4/chunk=8; GOLDEN False; QD_READER False; FAST_COLD False. Every §12 precondition held.

### 7.1 Structural results

| Question | Result |
|---|---|
| request_fastpath_begin | Lane active (flags true; installers engaged; observed arms recorded). Event string itself went to the non-persisting diagnostics sink. |
| CLIP FastSafe physical | **YES** — observed `fastsafetensors_direct_gpu` recorded only after owner-attach success; node window 6 462 ms (transport + native construction over served CUDA dict) |
| CLIP direct CUDA / T8/B256/bbuf512 | YES by resolved knobs + success-path semantics (per-event device/tuning fields not persisted) |
| served-dict seam / no second H2D | Structurally guaranteed; native reader shadowed for our paths only; no fallback recorded |
| bind_mode | **UNKNOWN** (not persisted) — either value is informative next batch |
| CLIP forward | span `clip_forward_end duration_ms=1973.5` (**HEALTHY_CLASS** ≤2.0 s); raw encode 3 081.1 ms; encode_calls=1; alloc Δ+33.5 MB, reserved Δ+239 MB; cuda_no_sync=true |
| Conditioning proof | lookup bypassed hit=false miss_count=1 + decision `miss_not_stored` encode_calls=1 persisted_count=0 (R44D emitter fired remotely) + ledger `forced_miss` |
| clean_lane_proof | Present: mode E37_CLEAN_LANE, proof_version 1, ordering restore 246.53→identity 246.60→forward_start 255.63→forward_end 257.60 (µs mono, sorted), forbidden-attempts list, thread state |
| UNET source prep | Armed at UNET entry (CPU-only); threads=4/chunk=8 resolved remotely; node window contains join→gate→transfer→adopt; **overlap with forward = 0** (UNETLoader node started after forward end — sequential graph order) |
| UNET FastSafe physical | **YES** — observed `fastsafetensors` after adoption; node window 3 911 ms vs 9 334 ms native R44C (−58 %) |
| 453/453 storage adoption | **UNKNOWN** (counts not persisted); adoption success required for the observed record, which fired |
| D15 | Clean — no violation signals; NOMINAL |
| Generation | `skipped_generation_match/exact_match`; expected==current==`1e02514e9e1580da5ab8a1002f9e669a`; reload invoked 0; models generation also exact_match |
| Exactness | SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` = expected ✓ |
| Status / ledger | NOMINAL, reasons [] ; ledger ok, endpoint ok, zero_gap true |
| Gate validators | **valid=1, reasons []** — strict-proof AND clean-lane both pass on real telemetry |

### 7.2 Timing table

| Metric | R44C native gate | R44D gate | Anchor |
|---|---|---|---|
| Application restore | 1 053.8 ms | **1 530.9 ms** (observational) | sub-2 s |
| Restore→method entry | 33.9 ms | 47.5 ms | — |
| Method/setup | 681.8 ms | 711.6 ms | — |
| CLIP load | 4 771 ms native | **6 462 ms FastSafe node window** (transport+construction combined; decomposition next batch) | ~1.15 s integrated E37 |
| CLIP forward | 3 425 ms | **1 973.5 ms span / 3 081 ms raw encode → HEALTHY_CLASS** | ~1 110 ms |
| UNET prep | n/a | armed 4/8, joined inside UNET window; overlap 0 | E24 ~2.8 s hidden |
| UNET FastSafe file→GPU | n/a (9 334 native) | **3 911 ms total node window** (join+gate+transfer+adopt; transfer wall not persisted) | ~477 ms E28 |
| UNET construct/adopt | native block | inside window above | ~0.14 s R42 |
| sampler-node→sampling | 1 385 ms | 1 433 ms | — |
| Sampling | 3 731 ms | **3 713.4 ms** | ~3.7 s |
| VAE decode | 465.5 ms | 502.4 ms | 0.38–0.44 s |
| Output | 356 ms | 334 ms | — |
| App wall | 48 092.4 ms | **28 222.5 ms** | historical fast territory |
| Scheduling (separate) | 21 916 ms | **6 170 ms** | — |
| command→response | 72 299 ms | **53 179 ms** | — |

One run; no distribution claims. CLIP node window regressed vs native (6.46 s vs 4.77 s) while UNET collapsed (3.91 s vs 9.33 s) — net −19.9 s app wall. Decomposition of the CLIP window (transport vs construction vs descriptor) is the obvious first target of the retune phase, using persisted transport telemetry.

### 7.3 ASCII Gantt (measured, █, 1 char = 200 ms)

```text
scale: 1 char = 200 ms | axis 23.6 s | origin = application restore start
                           +---------+---------+---------+---------+---------+---------+---------+---------+---------+---------+---------+---------
restore                    |████████                                                                                                              |   1531.0 ms
restore->method_entry      |       █                                                                                                              |     47.0 ms
request/method_setup       |       ████                                                                                                           |    712.0 ms
VAE load (native)          |           ███                                                                                                        |    519.0 ms
CLIP FastSafe node         |              █████████████████████████████████                                                                       |   6462.0 ms
CLIP forward               |                                              ████████████████                                                        |   3091.0 ms
UNET FastSafe node         |                                                              ████████████████████                                    |   3911.0 ms
bind/noise (t4d/t8)        |                                                                                 ████                                 |    562.0 ms
sampler_node->sampling     |                                                                                    ████████                          |   1433.0 ms
sampling                   |                                                                                           ███████████████████        |   3713.0 ms
post_sampling_transition   |                                                                                                              ██      |    382.0 ms
VAE decode                 |                                                                                                                ███   |    503.0 ms
output persist/collect     |                                                                                                                  ███ |    334.0 ms
```

Truthful overlap: NONE between CLIP forward and UNET prep this run (sequential node order: loader → encode → UNETLoader). The after-clip-overlap design exists but this graph ordering exercises the serial tail; ordering class = after_clip.

## 8. Anomalies register (all preserved; nothing repaired post-gate)

1. **Transport-telemetry persistence gap**: R44B `ctx.telemetry` events (clip_fast_load_*, unet_fastsafe_pipeline incl. bind_mode/storage_identity/ordering, request_fastpath_begin/end) route to the per-request `diagnostics` sink, which does not persist per-event records into run artifacts. Physical truth is proven via loader_selection + walls; metric decomposition requires redirecting these emissions to the persisting request trace (or dual-emitting). Designated next-batch fix.
2. Pre-spend deploy attempt 1 rejected by the clean-lane verifier's legacy 0/0 prewarm expectation — resolved by scoping the expectation to the R44 baseline (fail-closed both ways).
3. Case-b result-wait race (event registered only at publish time) — found by the new test, fixed in `result()`; plus the case-b missing observed-record gap.
4. CLIP FastSafe node window (6.46 s) exceeded the native load (4.77 s) on this first execution — expected for an unturned first run (descriptor build + FastSafe transport + full native construction over served dict); NOT tuned per stop rule. Requires persisted sub-walls to diagnose.
5. VAE decode 502 ms slightly above the 0.38–0.44 s band — observational, single sample.

## 9. Stop-rule compliance

Exactly one valid deployment (one failed zero-spend preflight recorded), exactly one paid cold request, no warmers/probes/second requests, no tuning, no post-gate repairs, no commits/pushes. All evidence preserved in `R44D_FASTSAFE_ACTIVATION_COLD_GATE_RAW_LOG.txt`.

## 10. Next decision (user's call)

1. Persist R44B transport telemetry to the durable trace (dual-emit or sink swap) → redeploy → ONE gate to capture bind_mode/453-storage/GB/s/prep-overlap truth.
2. Then CLIP-retune cohort (B256/B128/B64 independent cold samples) — now meaningful because the lane executes and forwards are HEALTHY_CLASS.

— R44D, stopped after the single cold gate.
