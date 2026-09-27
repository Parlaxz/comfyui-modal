# PHASE H19 — WAVE-G DEAD EXECUTION PYTHON / RUNTIME RESIDUE DELETION (2026-08-25)

**Batch type:** H-WAVE G dead-Python cleanup lane. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/revert/stash/clean. Shared tree intentionally dirty; H18 ran concurrently owning frontend files only — zero `web/*.js` or fake-lane files touched by this lane. `tests/run_studio_tests.py` NOT edited.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (incl. Follow-Ups), `PHASE_H17_WAVE_F_TEST_CONVERGENCE_AND_CLOSURE_2026-08-25.md`, `PHASE_H15_WAVE_F_SERVER_COMPATIBILITY_WRITE_FREEZE_2026-08-24.md`, `PHASE_H12_V2_ONLY_EXECUTION_CONSOLIDATION_2026-08-24.md`.

---

## 0. VERDICT

`H19 COMPLETE — WAVE-G DEAD PYTHON EXECUTION RESIDUE DELETED, CALLER-PROVEN, ALL LANES GREEN.`

Every deletion below was measured before cutting: definitions, imports, direct callers, registry references, monkeypatch/test references, and string-based lookups. No route decorator was deleted anywhere. No COMPAT_READ service, protected seam, migration path, or retired-string recognition was reduced.

## 1. PRE-DELETE CALLER GRAPH (measured, abridged)

```
_execute_comparison_profile   (__init__.py def-only since H14)          → 0 production callers
direct_studio_run_completion  (studio_run_adapter)                      → 0 production callers (H12 removed last)
execute_modal_prompt          (canonical_execution)                     → callers: direct_studio_run_completion + LocalRemoteInvoker.run_cell (both deleted in this same patch)
prepare_modal_execution       (canonical_execution)                     → sole caller: execute_modal_prompt
LocalRemoteInvoker            (experiment_runner)                       → 0 production registrations since H12; test-only
_prepare_studio_run_context   (studio_run_adapter)                      → sole caller: handle_studio_run_async `if not direct:` branch
_handle_studio_run_scheduler  (studio_run_adapter)                      → same branch
_playground_runtime_mode      (studio_run_adapter)                      → 0 callers anywhere (def-only)
handle_studio_run_async(direct=…)                                     → production call site __init__.py /studio/run passes NO direct arg (default True ⇒ always V2)
```

## 2. DELETED (production)

| Item | File | Proof |
|---|---|---|
| `_execute_comparison_profile` (~215 lines) | `__init__.py` | def-only residue since H14 410 freeze |
| `_playground_runtime_mode` | `studio_run_adapter.py` | zero callers repo-wide |
| `_prepare_studio_run_context` (+ nested `_studio_profile_preparer`) | `studio_run_adapter.py` | only reachable via `direct=False`; no production caller passes it |
| `direct_studio_run_completion` | `studio_run_adapter.py` | zero production callers since H12 |
| `_handle_studio_run_scheduler` | `studio_run_adapter.py` | same dead branch |
| `if not direct:` branch + `direct=` kwarg (async handler and sync wrapper) | `studio_run_adapter.py` | branch unreachable from the single production call site |
| `execute_modal_prompt` + `prepare_modal_execution` (~430 lines) | `canonical_execution.py` | both callers deleted in this same dependency-safe patch |
| `LocalRemoteInvoker` class (~390 lines) | `experiment_runner.py` | zero production registrations since H12 |
| Dead warmup helpers `_ws_id_for_active_next`, `_normalize_stable_warmup_profile`, `_compute_stable_warmup_profile_key`, `_build_next_warmup_activation` | `__init__.py` | zero production callers; live implementations are `warmup_profile._normalize_stable_profile/_compute_stable_key/build_activation_payload` |

### Import graph cleanup (§8)
- `__init__.py`: removed now-unused imports `run_comparison`, `save_comparison_manifest`, `save_comparison_result`, `set_slots`, `detect_slots`, `save_comparison_config`, `create/update/delete/duplicate_profile` (comparison writers), `run_prompt_stream` (modal_client), `prepare_modal_execution` (canonical_execution), `deployment_generation/ensure_warmup/gate_experiment/gate_experiment_on_stored_generation/WarmupRequiredError` (deploy_warmup), legacy preset writers ×8 (presets), `CURRENT_SCHEMA_VERSION/validate_definition` (experiment_models), `StaleEventError/LeaseActiveError/LeaseOwnershipError/UnknownCheckpointError` + `CheckpointStreamInvoker` (unused in this module — recovery constructs its own invoker in `experiment_service`). COMPAT_READ imports kept: `list_profiles/get_profile/auto_detect_slots/validate_profile/get_comparison_results/list_comparison_runs/load_comparison_config/get_workflow_nodes/get_profile_workflow`, presets list/get ×4, `WarmupState`, `LeaseError`, `compile_experiment`, `redact_log/format_timing`.
- `studio_run_adapter.py`: removed `RunTrace/execute_modal_prompt/prepare_modal_execution`, `HASH_SCHEMA_VERSION/PRODUCTION_PLAN_SCHEMA_VERSION`, `coerce_t0_from_browser`. Kept `TRACE_VERSION/merge_remote_trace_into` (live at finalization) and `prepare_active_next_profile` re-export (pinned seam).
- `experiment_runner.py`: removed `timing_trace` import (all five names LRI-only), `run_prompt_options` builders (LRI-only), `json/time/Path/control_key` (orphaned by LRI deletion), `Awaitable`.
- Comments/docstrings naming deleted symbols updated for truthfulness (`studio_run_adapter`, `experiment_runner`, `warmup_profile`, `playground_service`, `__init__`). `RunTrace.MARK_OPTIONAL` span-vocabulary strings (`"LocalRemoteInvoker"`, `"direct_studio_run_completion"`, …) deliberately RETAINED — trace data vocabulary, not dispatch code; historical trace summaries remain readable.

## 3. RETAINED — exact callers

| Helper | State | Caller proof |
|---|---|---|
| `modal_client.run_prompt_stream` | STILL_LIVE | V2 `ModalTransport` (mandated survivor); probe script only other caller |
| `_schedule_and_start` + `V2ExperimentInvoker` registration | DEFERRED | zero reachable production callers (both callers dead/inert), but it is the sole construction site of the §4-mandated-preserved `V2ExperimentInvoker` and is pinned by phase8/H12 "V2 invoker only" contract tests; route-pruning G lane should decide its + the legacy ExperimentScheduler chain's disposition together |
| `handle_studio_experiment` | DEFERRED | zero production callers (route is 410-inert), but registered F8 GPU-capture tests use it as their seam; migrating those belongs to the G test lane |
| `build_single_run_spec` | STILL_LIVE (tests) / DEFERRED | zero remaining production callers after context-path deletion, but heavily pinned by registered compilation-contract suites; not an H19 candidate |
| `__init__._collect_input_images` | DEFERRED | zero production callers post-deletion; dedicated unregistered input-image path suites unit-test it directly (live V2 twin lives in canonical_execution); migration = later G test lane |
| `CheckpointStreamInvoker` | STILL_LIVE | `experiment_service.recover_scheduler` ← protected stop-now route (`REGISTRY.recover_scheduler`) |
| `WarmupState` + status route | STILL_LIVE | deploy status (:1718) + GET /deploy-warmup/status |

## 4. WARMUP LIVE/DEAD SPLIT (§9)

- **A live:** deployment/readiness truth — `WarmupState` reads (deploy status + GET status 200 `{status,state}`).
- **B live:** `warmup_profile.prepare_active_next_profile` + `set/check_active_warmup_profile` (V2 plan boundary calls them via `execute_plan`).
- **C live:** status route behavior unchanged (H15 suite green).
- **D deleted:** `__init__` duplicate stable-profile/key/activation helpers + execution-only warmup imports (`ensure_warmup`, gates, `WarmupRequiredError`, `deployment_generation`).
- **E/F:** run/invalidate handlers were already pure 410/409 bodies (no dead code behind them); no streaming imports remain. Route decorators untouched (G route-pruning lane owns any removal).

## 5. LEGACY EXPERIMENT SERVICE (§10)

Conservative pass: `_record_experiment_cell_history`/`_on_remote_event`/REGISTRY/store/read-model code all RETAINED (recovered-scheduler event path feeds history read models). `compile` route's `compile_experiment` + `_enrich_checkpoint_from_profile`/`_resolve_latest_workflow_for_profile` RETAINED (pure-compute compile still live). Only provably-dead items removed: the unused writer/model/lease imports listed above. Protected GET `/experiments/{id}` and stop-now byte-untouched (H15 protection tests green).

## 6. AUTH / PRESETS / BACKENDS (§11)

All store/service libraries untouched (COMPAT_READ survives). Only route-local imports used solely by retired writers were removed (preset writers ×8). `.studio_backends.json` GET shim untouched.

## 7. TEST RECONCILIATION (§13/§14)

Removed/migrated dedicated dead-implementation tests; preserved every rejection/migration/freeze contract:

| File | Change |
|---|---|
| `tests/test_studio_direct_run.py` | rewritten 37→6: pins V2-only dispatch, absence of all four deleted helpers, removed `direct=` kwarg, retired-mode rejection, route registration |
| `tests/test_studio_timing_integration.py` | removed 5 LocalRemoteInvoker-dedicated classes (1 gate-visible GREEN + 4 RED backlog classes) |
| `tests/test_studio_runtime.py` | removed `SaveOutputImagesTests` (6); `ProductionSingleRunHashGuardTests` migrated to V2 (`build_execution_plan` compile-once; hash-truthfulness pin; obsolete mismatch-guard documented as obsolete-by-construction) |
| `tests/test_workflow_run_integration.py` | 3 tripwire patches retargeted `direct_studio_run_completion`→`playground_adapter_direct_run` (stronger: no executor at all) |
| `tests/test_phase8_execution_mode.py` | dropped dead tripwire patch + `direct=True` args (41/41 unchanged) |
| `tests/test_h12_v2_only_consolidation.py` | test_15 modernized; test_18 pin flipped to full absence of `_execute_comparison_profile`; test_21 flipped to assert LocalRemoteInvoker DELETED (21/21 unchanged) |
| `tests/test_h14_wave_e_retirement.py` | census `["_msg"]`→`[]`; residue-count pin → absence; zero-executor tripwires moved to source modules + import-absence pins (30/30) |
| `tests/test_h15_wave_f_server_freeze.py` | census `["_msg"]`→`[]` (36/36) |
| `tests/test_f8_gpu_authority.py` | dropped `direct=True` arg (41/41) |
| `tests/test_canonical_execution.py` | removed prepare/execute suites (kept RunTrace/V2 plan suites) |
| `tests/test_experiment_runner.py` | removed 3 LRI classes |
| `tests/test_studio_live_progress.py` | DELETED (wholly LRI stream-sink RED TDD suite; subject retired) |
| `test_run_prompt_options / test_production_phase1 / test_production_dispatch_plan / test_warmup_profile_dedup / test_audit_round7 / test_waterfall_attach_central / test_restore_timing_data_flow / test_v2_16_20_patch / test_runtime_playground_v2` | renamed/trimmed/re-pinned per deleted subjects; retired V1 canvas arming test removed |

Untouched: `tests/run_studio_tests.py`, all `web/*.js`, fake-lane files.

## 8. V2 REGRESSION EVIDENCE (§15–17)

- Single `POST /studio/run` → V2 adapter: new direct-run contract tests + F8 capture (GPU frozen per plan) ✓
- Workflow V2-only: `test_workflow_run_integration` 25/25 ✓
- Experiment modern: `test_history_v2_modern_experiment` 46 ✓ (combined run 71 OK with workflow suite)
- Canvas Cloud V2-only: phase8 canvas structural proofs ✓
- Retired explicit modes rejected truthfully + persisted modes migrate to v2 + COMFYMODAL_RUNTIME v2-only: phase8+h12 **62/62** ✓
- ModalTransport → shared `run_prompt_stream`: H14 `test_shared_transport_not_deleted` + H15 `test_shared_transport_survives_for_v2` ✓
- History/GPU invariants: F8 41/41; all history_v2_* suites green in gate; zero History/GPU production edits ✓
- Protected seams: H15 ProtectedSingleSeamTests (GET detail / stop-now) green inside the 36 ✓

## 9. DIRECT `run_prompt_stream` CENSUS (post-cleanup)

Production callers of `modal_client.run_prompt_stream`: **exactly one — `comfymodal_runtime/modal_transport.py` (V2 ModalTransport)**, plus the standalone dev probe `probe_modal_prompt.py`. `__init__.py` textual direct-call census = `[]` (pinned by H14+H15). Remote definition `comfyapp.run_prompt_stream` / `modal_app.py` untouched.

## 10. DEAD-CODE CENSUS FINAL STATE (§20)

| Symbol | Final state |
|---|---|
| `_execute_comparison_profile` | DELETED |
| `direct_studio_run_completion` | DELETED |
| `execute_modal_prompt` | DELETED |
| `LocalRemoteInvoker` | DELETED |
| `_prepare_studio_run_context` | DELETED |
| `_handle_studio_run_scheduler` | DELETED |
| `_playground_runtime_mode` | DELETED |

Remaining textual occurrences are: negative assertions in H12/phase8/H14 pins, the forbidden-symbol list in `test_deploy_no_auto_generation` (still-valid), `RunTrace.MARK_OPTIONAL` vocabulary strings + their test mirrors (data compat), and intentional H19 documentation notes. No UNKNOWN.

## 11. GATE COUNTS & DELTA (§18/§19)

Focused: phase8+h12 **62/62** · h14 **30/30** · h15 **36/36** · routes_registered **61/61** · f8 **41/41** · workflow+modern-experiment **71/71** · studio_runtime **228 direct / 197 gate** · runtime_playground_v2 **68/68** · canonical_execution **24/24** · timing_integration direct **42/42** · restore_timing+run_prompt_options **21/21**.

Full gate `python tests/run_studio_tests.py --fake`:
```
python             run=1824  fail=0    error=0    skip=0
node-unit          run=21    fail=0    error=0    skip=0
fake-playwright    PASS (wrapper aggregate run=1)
ALL STUDIO LANES GREEN
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (4.0m) / 211   (first attempt, zero flake)
```

**Delta ledger:** starting nominal baseline Python 2010 → 1824 = −186.
- **THIS lane: exactly −38**, fully itemized against pre-edit measurements of its own files: `test_studio_direct_run` 37→6 (−31), `test_studio_timing_integration` gate contribution 1→0 (−1, the LRI GREEN class; the 11 removed RED tests were already gate-excluded), `test_studio_runtime` 203→197 (−6, SaveOutputImagesTests). All other touched suites count-neutral (h14 30, h15 36, routes 61, f8 41, workflow 25, backend 286, presets 9+9…).
- **Remaining −148:** frontend-structural Python suites (`test_testing_shell_integration`, `test_testing_ui_wired`, `test_testing_results_js`, `test_testing_setup_js`, …) whose counts moved on the shared dirty tree relative to the nominal 2010 — owned by the concurrently-running H18 frontend lane / earlier waves; none of those files were touched by H19. Reconciliation belongs to the G test lane alongside broad registration cleanup.

Pre-existing out-of-gate failures re-measured, NOT caused by this lane (unregistered suites): `test_experiment_runner.PerInvocationMaterializationTests` ×4 and `test_audit_round7.WaterfallCategoryTests.test_no_parent_child_double_count` + `test_v2_16_20_patch.test_comfyapp_version_is_2_16_20` all stem from the dirty `comfyapp.py` working-tree state (attribute/label/version absent even at HEAD).

## 12. REMAINING PYTHON WAVE-G RESIDUE (for later G lanes)

1. `_schedule_and_start` + `V2ExperimentInvoker` + legacy `ExperimentScheduler`/`ExperimentRunner` chain — inert behind retired routes; needs a coordinated route-prune + invoker-disposition decision (V2ExperimentInvoker preservation mandate vs zero callers).
2. `handle_studio_experiment` — dead creator handler retained as the F8-test seam.
3. `build_single_run_spec` — production-orphaned spec builder pinned by registered contract suites.
4. `__init__._collect_input_images` — production-orphaned, unit-tested directly; migrate tests to the canonical_execution twin.
5. `RunTrace.MARK_OPTIONAL` legacy span names — retained deliberately (trace-data compatibility).
6. Warmup route family + legacy Experiment/Comparison/auth/presets/backends route decorators — registered-and-inert by design; Wave-G route-pruning lane decides physical removal.

## 13. FILES MODIFIED BY THIS LANE ONLY

Production: `__init__.py`, `studio_run_adapter.py`, `canonical_execution.py`, `experiment_runner.py`, `warmup_profile.py` (docstring), `comfymodal_runtime/playground_service.py` (docstring).
Tests modified: `tests/test_studio_direct_run.py` (rewritten), `tests/test_studio_timing_integration.py`, `tests/test_studio_runtime.py`, `tests/test_workflow_run_integration.py`, `tests/test_phase8_execution_mode.py`, `tests/test_h12_v2_only_consolidation.py`, `tests/test_h14_wave_e_retirement.py`, `tests/test_h15_wave_f_server_freeze.py`, `tests/test_f8_gpu_authority.py`, `tests/test_canonical_execution.py`, `tests/test_experiment_runner.py`, `tests/test_run_prompt_options.py`, `tests/test_production_phase1.py`, `tests/test_production_dispatch_plan.py`, `tests/test_warmup_profile_dedup.py`, `tests/test_audit_round7.py`, `tests/test_waterfall_attach_central.py`, `tests/test_restore_timing_data_flow.py`, `tests/test_v2_16_20_patch.py`, `tests/test_runtime_playground_v2.py`.
Deleted: `tests/test_studio_live_progress.py`.
NOT edited: `tests/run_studio_tests.py`, `web/*.js`, fake-server/specs, comfyapp.py.

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
