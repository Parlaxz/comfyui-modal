# R44I2 — Authoritative Sampler Boundary Telemetry (Direct sampling_start + First-Eval)

Batch: R44I2 · Lane: SAMPLER TELEMETRY PERSISTENCE ONLY · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46e3238f421378e8852ebc548da815b70af` (unchanged; no commits/push/merge/reset/revert/clean/stash)
No deploy. No Modal run. No paid request. No sampler numeric/behavior change. No CLIP loading/adoption change.

Authorities consumed in full: `R44H3_CAST_ONCE_CLIP_REMOTE_PROOF_REPORT.md`, `R44H3_CAST_ONCE_CLIP_REMOTE_PROOF_RAW_LOG.txt`, `R44H2_LIVE_GANTT_AND_SAMPLER_TELEMETRY_RECONCILIATION_REPORT.md`, `R44G3_SAMPLER_AND_POSTSAMPLING_FORENSICS_REPORT.md`, `R44G1_DYNAMIC_GANTT_AND_TELEMETRY_REPORT.md`.
Artifact inspected directly: request `v2-benchmark-0-476f84af0e92` → `comfymodal-data\benchmarks\runs\v2_2026-08-24_12-11-30\run_0.json` (250 trace events enumerated) + `dynamic_gantt_run_0.txt`.

---

## 1. H3 remote event inventory (sampler-related, from run_0.json)

| Event | Count | Verdict |
|---|---:|---|
| `sampling_start` (authoritative wrapper) | **0** | MISSING |
| `sampling_end` (wrapper pair) | **0** | MISSING |
| `sampler_prep_phase` | **0** | MISSING |
| `sampler_first_eval_start` | **0** | MISSING |
| `unet_first_cuda_op` | **0** | MISSING |
| `sampler_step_ticks` | 1 | PRESENT — 9 ticks, node 1242 `ClownsharKSampler_Beta`, dual-fed sources |
| `sampler_tail` | 1 | PRESENT — wall 502.259 ms; GC 470.742 ms (×1); deepcopy 16.379 ms (×12); `.cpu()` 0.138 ms / 2,088,960 B (×1); other 14.999 ms |
| `pre_sampler_stages.sampling_start_monotonic_ns` | — | empty; `sampling_start_source = "unavailable"` |
| `sampler_lane_wait_start/end` | 1+1 | PRESENT (existing) |

Dynamic Gantt therefore correctly fell back to `sampler node→first progress (PROXY)` ≈ 1520.5 ms. Tail/ticks working does NOT make the telemetry complete — exactly the three intended decomposition boundaries were absent.

## 2. Why H2's wrapper re-install failed — PROVEN at source level

H2's mechanism assumed the sampler-internal `load_models_gpu` sees the exact patcher early enough that a SAMPLER_SAMPLE wrapper installed into `model_patcher.model_options` would be carried into the guider's sample chain. The actual comfy control flow defeats this by ORDERING:

1. `SharkSampler.main` calls `guider.sample(...)` (`RES4LYF/beta/samplers.py:659`; guider is `SharkGuider(CFGGuider)` built fresh at :559 from the node's patcher).
2. `CFGGuider.sample` entry **clones model_options immediately** (`comfy/samplers.py:1303-1304`: `self.model_options = create_model_options_clone(self.model_options)`). Call this CLONE-1.
3. OUTER_SAMPLE executor → `CFGGuider.outer_sample` (:1232) → `prepare_sampling` (:1233) → `_prepare_sampling` → **`load_models_gpu([patcher], …)`** (`comfy/sampler_helpers.py:201`). H2's lmg seam fires HERE.
4. The seam installs the wrapper into `model_patcher.model_options` — the ORIGINAL dict. Installation SUCCEEDS (`ensure_sampling_timing_wrapper` returns True; no `[comfymodal] ensure_sampling_timing_wrapper failed` line in H3).
5. `CFGGuider.inner_sample` (:1214) clones CLONE-1 again (:1220, CLONE-2) and reads SAMPLER_SAMPLE wrappers from CLONE-2 only (:1227).

The lookup reads the clone chain captured BEFORE the install; the original dict is never consulted again for this invocation. **The wrapper never executed — the events never occurred; nothing was lost in emission or persistence.**

Object/identity trace answers (spec §3):
1. Was the lmg seam invoked? **YES** — proven by the tail sub-timings (GC/deepcopy/`.cpu()` patches install at the same seam).
2. Did `ensure_sampling_timing_wrapper` succeed? **YES** (plain dict insert; no failure line remotely).
3. Which object was modified? The ORIGINAL `model_patcher.model_options`.
4/5. Was that object later cloned for the live call? The clone happened EARLIER (step 2); CLONE-1/CLONE-2 contain no wrapper.
6. Wrapper key/name correct? YES (`WrappersMP.SAMPLER_SAMPLE` / `comfymodal_v2_sampling_timing`) — irrelevant given (4/5).
7. Another clone/replacement after install? Not needed to explain the loss; the pre-existing ordering alone is sufficient and deterministic.
8. Why did step ticks work? They are dual-fed from comfyapp progress events (`note_progress_tick`), wrapper-independent.
9. Why did the first-forward probe not survive? Same family: identity/registration-based attachment could not be relied on remotely (NextDiT class-patch + weak registry + CacheDiT lazy application inside the sampler window); no durable evidence distinguishes hook-not-installed vs not-invoked vs not-persisted — which is precisely why §11 status instrumentation was added and why first-eval now has its own direct seam.
10. Emission failure or never occurred? **Never occurred** (for sampling_start; proven by the clone-ordering trace).

## 3. New authoritative boundaries (clone-independent, runtime-owned)

### 3.1 `sampling_start` — DIRECT boundary (preferred hierarchy A)

Seam: class-level wrap of `comfy.samplers.CFGGuider.sample` — the exact semantic boundary "immediately before the deep sampling invocation" (`SharkSampler.main → guider.sample`). Comfy-generic (SharkGuider inherits), guaranteed on this path, telemetry-only.

* Recorded fields: `request_id`, `node_id`, `mono_ns`, `wall_unix_ns`, `steps` (= len(sigmas)−1), `sigmas_len`, latent dtype/device (from positional args — no introspection), `source="direct_sampler_call_boundary"`.
* Idempotent per request (first wins); invoked-flag latches for status; passthrough always.
* `pre_sampler_stages.sampling_start_source` now reports **`authoritative_direct_sampler_boundary`** when the direct boundary supplies the stamp.

### 3.2 `sampler_first_eval_start` — DIRECT boundary

Seam: class-level wrap of `comfy.model_base.BaseModel.apply_model` — the narrowest function EVERY underlying denoiser evaluation passes through (`calc_cond_batch` → `apply_model`, samplers.py:334/525), independent of model_options cloning, guider subclass, and CacheDiT's DIFFUSION_MODEL wrapper.

* Ordinary host `time.monotonic_ns()` immediately before invocation; recorded once per request; NO CUDA synchronize.
* `unet_first_cuda_op` keeps its distinct CUDA-op semantics via the existing probe; the two are NOT equated. Gantt consumes host call-entry time.

Both seams are installed idempotently at three trigger points inside `sampler_telemetry.py` itself (`reset_request`, `note_sampler_node_entry`, `note_load_models_gpu_enter`) — zero new integration edits in shared files; removable via `remove_direct_boundaries()` (tests/feature-off).

## 4. Persistence + status architecture

* Store-first: seams record into the request-scoped store (same thread as node execution — proven sink for ticks/tail).
* Durable emission at exec-node finally (proven sink): `emit_durable_events` now also emits
  * deferred authoritative `sampling_start` (only when the trace lacks one — deterministic dedup preferring the direct boundary), metadata carries `mono_ns` (TRUE stamp), `source`, `emission="deferred_boundary"`;
  * `sampler_telemetry_status` ALWAYS — `sampling_start_hook_installed/invoked/persisted`, `first_eval_hook_installed/invoked/persisted`, `tick_count`, `tail_present`, `lmg_record_count`. This permanently distinguishes never-installed vs never-invoked vs fired-but-not-persisted — the exact opaque-gate failure mode of H2/H3 can never recur silently.
* Consumers honor TRUE stamps: `dynamic_gantt.load_run_artifacts` normalization and `v2_waterfall._event_clock` prefer `metadata.mono_ns` strictly gated on `emission=="deferred_boundary"`; `modal_app` backfill precedence rewritten: direct-boundary store > wrapper event > store capture > milestone proxy (explicitly labeled). Previously the milestone fill starved the store fallback entirely.

## 5. Working H2 telemetry preserved (untouched)

`sampler_step_ticks` (dual-feed), `sampler_tail` closure at true node return, `gc_collect_ms/_count`, `state_info_deepcopy_ms/_count`, `cpu_transfer_wall_ms/_bytes/_count`, `subtiming_other_ms`, VAE `load_models_gpu` mono stamps + caller classification, `_CpuTimer` record fields, cutoff clipping semantics. H3 values (tail 502.259 / GC 470.742 / deepcopy 16.379 / CPU 0.138 ms·2,088,960 B) remain reproducible; GC remains the dominant tail suspect — NOT optimized now.

## 6. Tests reproducing the old failure + new guarantees

New `tests/test_r44i2_direct_boundary_telemetry.py` (16 tests):
* **H2WrapperLossReproductionTest** — real `comfy.patcher_extension` semantics (+ `create_model_options_clone` when importable): install-after-clone leaves the SAMPLER_SAMPLE lookup EMPTY while the original carries the wrapper ⇒ old failure reproduced deterministically.
* DirectSamplingStartSeamTest (record/passthrough/idempotence/inactive-gate/survives-full-clone-dance), DirectFirstEvalSeamTest (first-call recording, exactly-once), RealClassInstallRemoveTest (real `CFGGuider.sample`/`BaseModel.apply_model` swap, stub-driven invocation, exact restore, no double-wrap), StatusEventTest (all-true success scenario incl. deferred-event dedup + opaque-gate scenario reporting persisted=False/invoked=False with n=1), NoGpuSyncTest (AST scan — no synchronize/empty_cache/set_device CALLS), DeferredTimestampRoundTripTest (real artifact file → `load_run_artifacts` resolves TRUE stamps), ExistingTelemetryUnchangedTest (ticks/tail schema unchanged; resolver labels all four source classes), FeatureDisabledNativeBehaviorTest (flag off ⇒ classes untouched, recording inert).
Expectation updates REQUIRED by the mandatory status event: `test_r44h2…DurableEventEmissionTest` (4→6 events) and `test_r44h3…SchemaNeutralityTest` (4→6, names list extended) — legacy four keep order `[prep_phase, first_eval_start, step_ticks, tail]`, then `sampling_start`, then `sampler_telemetry_status`.

## 7. Dynamic Gantt effect

With the new events present a rich run renders the full five-way split under `Sampler node`: `sampler orchestration/prep` → `first-eval startup` → `first-step latency` → `progress sampling` → `RES4LYF sampler post-loop tail`; **no PROXY row** (`sampler.transition` absent); completeness flips `sampling wrapper start (true)`, `sampler prep phase`, `first eval start` to PRESENT. Verified end-to-end locally against synthetic deferred-shaped artifacts including a real-file `load_run_artifacts` round-trip. No dynamic_gantt row-registry changes were needed — H2 already registered the consumers; only timestamp normalization was corrected.

## 8. Overhead

Timestamp-only. `CFGGuider.sample` wrap: one function call + flag checks per SAMPLER NODE (not per step). `apply_model` wrap: two attribute reads + branch per denoiser eval after the first (ns-scale). Deferred emission adds two trace events per request. No sync, no cache ops, no I/O, no introspection, no extra locks on hot paths beyond the existing module-lock pattern used only during one-time recording.

## 9. Files changed

| File | Change |
|---|---|
| `comfymodal_runtime/sampler_telemetry.py` | Direct-boundary constants/seams/install-remove/triggers; source-aware resolver (`authoritative_direct_sampler_boundary`); deferred `sampling_start` + always-on `sampler_telemetry_status` emissions; snapshot hook flags |
| `comfymodal_runtime/dynamic_gantt.py` | Normalization honors `emission="deferred_boundary"` → `metadata.mono_ns` (flag-gated; legacy events untouched) |
| `comfymodal_runtime/v2_waterfall.py` | `_event_clock` same gated preference |
| `comfymodal_runtime/modal_app.py` | Backfill block (~14935-14969) rewritten: TRUE-source precedence (direct > wrapper event > store > labeled proxy), deferred-stamp-aware scan; downstream keys unchanged |
| `tests/test_r44i2_direct_boundary_telemetry.py` | NEW, 16 tests |
| `tests/test_r44h2_sampler_telemetry_gantt.py` | One expectation update (6 events) |
| `tests/test_r44h3_sampler_reset.py` | One expectation update (6 events) + docstring note |

Forbidden areas untouched: `request_clip_fastsafe.py`, all CLIP/adoption files, RES4LYF, sigmas/callbacks/model options behavior, loader logic.

## 10. Exact test counts

| Suite | Result |
|---|---|
| Combined required run (R44I2 + r44h3_sampler_reset + r44h2 + r44g1_dynamic_gantt + v2_waterfall + v2_waterfall_contract + v2_unet_forward_probe + e27 + e29 + r44e_evidence_durability + r44h3_bounded_validation) | **199 passed / 0 failed** |
| Broader runtime suites (r44a_generation_determinism, r44b_request_fastsafe, r44d_proof_installation, r44d_runtime_env_passthrough, r44h1_clip_cast_once, r44f_clip_zero_copy) | **101 passed / 0 failed** |
| `py_compile` (sampler_telemetry, dynamic_gantt, v2_waterfall, modal_app, comfyapp, 3 test files) | clean |

## 11. Concurrent overlap with R44I1

NONE by file ownership: `request_clip_fastsafe.py` and all CLIP namespace/adoption files untouched; R44I1-owned suites (`test_r44h1_clip_cast_once`, `test_r44f_clip_zero_copy`) green post-change. Shared-dirty file note: `modal_app.py` was already dirty from concurrent work; my delta is ONE localized block (pre-sampler backfill), re-read immediately before editing, exact-match applied, all unfamiliar concurrent changes preserved byte-for-byte. `runtime_executor.py`, `comfyapp.py` NOT edited by R44I2 (seam triggers live inside `sampler_telemetry.py`; the exec-node emitter call site already existed).

## 12. Checklist for the next remote gate

1. Deploy current tree; ONE cold run on `r44-request-fastsafe` (controls frozen).
2. In `run_0.json` verify: `sampling_start` present with `metadata.source="direct_sampler_call_boundary"`, `emission="deferred_boundary"`, and `metadata.mono_ns` strictly between `first_sampler_node_monotonic_ns` and `t6_sampler_start`; `sampler_prep_phase.wall_ms` ≈ historical ~100 ms class; `sampler_first_eval_start` present with mono between sampling_start and t6; `sampler_step_ticks.count == steps`; `sampler_tail` with GC/deepcopy/CPU splits; `pre_sampler_stages.sampling_start_source == "authoritative_direct_sampler_boundary"`.
3. `dynamic_gantt_run_0.txt`: five-way SAMPLER split, NO `(PROXY …)` row, completeness PRESENT for true start / prep / first eval / ticks / tail.
4. If anything is still missing, read `sampler_telemetry_status` FIRST: `*_hook_installed=false` ⇒ install trigger never ran; `installed=true, invoked=false` ⇒ CFGGuider.sample/apply_model never reached through the patched classes; `invoked=true, persisted=false` ⇒ recording gate blocked (request scope). Each state is now explicitly distinguishable — no more opaque gates.
5. Do NOT interpret residual prep-vs-first-eval numbers until a nominal (non-fallback) run lands; fallback runs carry cold-container first-step costs inside first_eval_startup.

---

```text
R44I2_H2_REMOTE_FAILURE_ROOT_CAUSE_PROVEN = YES
R44I2_OLD_WRAPPER_FAILURE_REPRODUCED_LOCALLY = YES
R44I2_SAMPLING_START_DIRECT_BOUNDARY_IMPLEMENTED = YES
R44I2_SAMPLING_START_SOURCE = direct_sampler_call_boundary (reported as authoritative_direct_sampler_boundary)
R44I2_FIRST_EVAL_DIRECT_BOUNDARY_IMPLEMENTED = YES
R44I2_FIRST_PROGRESS_FROM_STEP_TICKS = YES
R44I2_WORKING_TAIL_TELEMETRY_PRESERVED = YES
R44I2_NO_EXPLICIT_GPU_SYNC_ADDED = YES
R44I2_RUNTIME_PERFORMANCE_BEHAVIOR_CHANGED = NO
R44I2_REMOTE_RUN_PERFORMED = NO
R44I2_READY_FOR_RECONCILIATION = YES
```

STOP. No deploy. No Modal run performed.
