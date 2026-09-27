# PHASE H20 — WAVE-G TEST CONSOLIDATION & POST-DELETION CONVERGENCE (2026-08-25)

**Batch type:** H-WAVE G test consolidation lane on the CURRENT shared (intentionally dirty) tree. Ran AFTER H18 (frontend deletion, COMPLETE) and H19 (execution-Python deletion, COMPLETE); no concurrent production writer. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean; unrelated dirty-tree work untouched.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` incl. Follow-Ups A–E, `PHASE_H17_WAVE_F_TEST_CONVERGENCE_AND_CLOSURE_2026-08-25.md`, `PHASE_H18_WAVE_G_DEAD_FRONTEND_CLEANUP_2026-08-25.md`, `PHASE_H19_WAVE_G_DEAD_EXECUTION_PYTHON_CLEANUP_2026-08-25.md`, `PHASE_H15_WAVE_F_SERVER_COMPATIBILITY_WRITE_FREEZE_2026-08-24.md`; H12/H13/H14 invariants where referenced by surviving tests. Current source = final truth.

---

## 0. VERDICT

`WAVE G TEST CONSOLIDATION COMPLETE`

Combined H18+H19 tree verified coexisting; pre-H20 baseline reconciled exactly (1824/21/211); every meaningful deterministic Studio contract now registered; all named debts truthfully resolved with evidence; final gate green twice: **Python 2124/2124 · Node-unit 25/25 files · Fake Playwright 211/211 exact**.

---

## 1. H18 + H19 COEXISTENCE VERIFICATION (§1)

All markers verified in current source before any test edit:

- **H18:** all nine files absent (`testing-setup/profiles/results/settings/ab-slider.js`, `studio-legacy.js`, `modal-comparison.js`, `testing-api.js`, `testing-setup-adapter.js`); `modal-settings.js` = 115-line minimal compatibility module; dead API helpers (`getBackends`, `getCompareBackends`, `runStudioExperiment`, `listExperiments`, `listRunHistory`, `listUnifiedHistory`, `getModalConfig`) have zero definitions under web/; `updateRunAnnotation` (:225)/`saveRunOutput` (:245)/`getStudioRunStatus` (:121)/`stopExperiment` (:132) survive in `studio-backend-api.js`; five-page shell (`PAGES`, studio-shell.js:18) + `ALIAS_PAGE_MAP` (modal-testing.js:161) intact; modal-testing retired draft/preview/experimentId machinery gone (single H18 comment remains); Comparison UI unreachable (no comparison registerExtension anywhere).
- **H19:** zero production def/class for `_execute_comparison_profile`, `direct_studio_run_completion`, `execute_modal_prompt`, `prepare_modal_execution`, `LocalRemoteInvoker`, `_prepare_studio_run_context`, `_handle_studio_run_scheduler`, `_playground_runtime_mode`. Retained: `V2ExperimentInvoker` (v2_experiment_invoker.py:26), `CheckpointStreamInvoker` (experiment_runner.py:1227), V2 `ModalTransport` (modal_transport.py:387), `modal_client.run_prompt_stream` (:433). Freeze-code census exact vs H15: COMPARISON_READ_ONLY ×6 · COMPARISON_RETIRED ×1 · EXPERIMENT_RETIRED ×10 · EXPERIMENT_READ_ONLY ×5 · WARMUP_RETIRED ×3 (2 routes + 1 docstring) · AUTH_SETUP_RETIRED ×1 · BACKENDS_READ_ONLY ×4 · LEGACY_PRESETS_READ_ONLY ×8. Protected GET `/experiments/{id}` + stop-now present; run-history COMPAT_WRITE pair present (:6395/:6456).

**Conflict found: NONE → test cleanup proceeded.**

## 2. PRE-H20 COMBINED GATE (§2)

| Lane | Result |
|---|---|
| `python tests/run_studio_tests.py --skip-node` | run=1824 fail=0 error=0 skip=0 |
| Node lane | 21 files PASS |
| `npx playwright test --config=playwright.fake.config.mjs --reporter=line` | **211 passed (4.1m)** |

Expected 2010 −148 −38 = 1824 — **exact match, zero drift**. Arithmetic identity: H17's 2010 = 1469 (untouched suites) + 393 (seven frontend-structural suites); H18 moved those seven to 393→245 net −148; H19 removed exactly −38 (direct_run −31, timing_integration −1, studio_runtime −6); 2010−148−38 = 1824 confirmed by measurement.

## 3. TEST INVENTORY / REGISTRATION MAP (§3)

Registered-gate inventory audited suite-by-suite (all 40 STUDIO_PY_MODULES entries + 25 NODE_UNIT_FILES). Dispositions applied this batch:

| Suite | Disposition |
|---|---|
| tests/test_phase8_execution_mode.py | REGISTER (41) |
| tests/test_h12_v2_only_consolidation.py | REGISTER (21) |
| tests/test_run_history.py / test_task2_run_history_extensions.py / test_run_history_save.py | REGISTER (143 total; H5 §27 debt) |
| tests/test_task3_progress_annotations.py | MERGE_THEN_REGISTER executed in place → renamed `test_studio_progress_annotations.py`, REGISTER (71) |
| tests/test_modal_workspace_ui_ast.py | REGISTER (24) |
| tests/test_image_packaging_refactor.py | DELETE_STALE (41; never registered) |
| tests/studio_backend_operations_unit.mjs | REGISTER (H6) |
| tests/studio_model_library_parity_unit.mjs | REGISTER (H7) |
| tests/studio_legacy_settings_authority_unit.mjs | MIGRATE-THEN-REGISTER resolved via Option B → renamed `studio_settings_compat_authority_unit.mjs`, REGISTER |
| tests/studio_phase_e4d_original_retry_unit.mjs | repaired slice bug, REGISTER |
| tests/test_experiment_runner.py | KEEP_FOCUSED_ONLY after deleting stale class (73 green) |
| tests/test_studio_workflow_run_plan_identity.py | stale assertion fixed; KEEP_FOCUSED_ONLY (redundant with registered workflow-run-integration + F8 freeze pins) |
| tests/test_modal_settings_gpu_config.py | REDUNDANT (contract now behaviorally pinned by registered settings-compat + F8 units); stays unregistered, green |
| tests/test_workstream_e_patches.py | KEEP_FOCUSED_ONLY (buffer units) + retirement half redundant with registered testing_results_js |
| ~200 V2/runtime/benchmark/v2ctl modules | NON_STUDIO (runner charter) |

No historical phase test was blindly registered; every registration above protects a current product invariant.

## 4. H12 SUITES AUDIT (§4)

- `test_phase8_execution_mode.py` (41): resolver recognition vocabulary (recognition-for-migration preserved), collapsed `{v2}` env lock, retired-request surfacing (`retired=True`, never silently relabeled), `/config` validation matrix, capture backstop, Single dispatch rejection before execution, scheduler V2-only source pin, workflow legacy-run absence, canvas structural proof. Every category maps to a current contract; the two source-shape checks pin architecture-as-contract (no mode branch, single V2 path) per §19 judgment. **REGISTER unchanged.**
- `test_h12_v2_only_consolidation.py` (21): persisted migration matrix (idempotent rewrite, notice-once, env precedence, save-never-persists-retired, comfymodal_enabled never mapped), real-route `/config` rejection via stub harness, adapter-level rejection for Single + Experiment creator, survival audits updated by H19 (`_execute_comparison_profile` absence, LocalRemoteInvoker deletion). Not duplicative of phase8 (different layers). **REGISTER unchanged**, placed after Workflows block (stub-server constraint), reverse-order probe also green.

## 5. H6 BACKEND OPERATIONS UNIT (§5)

23 of 24 sections were current modern-Backend contracts (workspace CRUD/swap exact-request pins, deploy explicit-only/dedupe/no-mount-deploy, credential no-echo, ownership guards O19–O21/O23–O24). Section O22 pinned the H18-deleted legacy overlay controls in `modal-settings.js` — rewritten to the current contract: overlay retired, zero operational sections in modal-settings.js, Backend sole operations owner (negative pins retained). No overlap loss against the 21 previously-registered Node files (workspace/deploy/credential behavioral coverage was unique). **REGISTER.**

## 6. H7 MODEL-LIBRARY PARITY UNIT (§6)

Sections 1–14 current (canonical routes only, explicit-only rescan/refresh/install-request, no raw-installer routes, Compatibility≠Portability, bounded failures, dedupe). Section 15 pinned the deleted legacy Models/Sync panel content in modal-settings.js — rewritten as a retirement pin (zero residue of the nine legacy markers). Useful Model Library/custom-node registry/dependency install-request/no-duplicate-installer coverage preserved. **REGISTER.**

## 7. LEGACY SETTINGS AUTHORITY — MIGRATE-THEN-REGISTER FINISHED (§7)

The H18-re-sliced unit already covered only surviving authority (GPU read-only init server-wins-stale-LS zero-POST, deleted commitGpuSelection path pinned absent, single-sync lifecycle, output preferences through shared helper incl. failed-edit no-false-authority, canvas reader intact, Comparison module-absence sweep). Option B executed: renamed to **`studio_settings_compat_authority_unit.mjs`** (fits `studio_phase_f4_settings_authority_unit.mjs` conventions), header updated, **REGISTERED**. The unresolved MIGRATE-THEN-REGISTER debt from H5 §27 is closed. No dead DOM assertions retained; no legacy Settings recreated.

## 8. TRACKER-MEMBERSHIP ×5 — ROOT CAUSES (§8)

Failing assertions (measured): `SharedProgressConsumedByPlaygroundTests.{test_imports_progress_module, test_uses_get_shared_tracker, test_subscribes_to_tracker_progress, test_tracker_only_updates_in_flight}` + `PlaygroundUsesScopedTrackerTests.test_imports_create_scoped_tracker`.

Per-failure classification — all **B: TEST STALE** (evidence: `git grep` proves studio-playground.js has NO comfymodal-progress import, NO getSharedTracker/onProgress/isInFlight/createScopedTracker references at HEAD or worktree; FB-5 had already located the architecture move):

| # | Asserted responsibility | Lives NOW |
|---|---|---|
| 1 | playground imports shared progress module | nowhere — playground progress owned by `createPlaygroundRunController` (studio-playground-run.js) |
| 2 | playground calls getSharedTracker() | canvas only (modal-node.js:3) |
| 3 | playground subscribes tracker.onProgress | controller `attachEventSource` wiring |
| 4 | isInFlight guard before applying updates | controller lifecycle (`beginRun`/apply*) |
| 5 | playground imports createScopedTracker | export has ZERO production consumers (module + browser harnesses only) |

Product defect: NONE — progress display is fully wired and proven in-gate (`studio_playground_run_unit.mjs`, fake lifecycle/playground specs). Required behavior not lost. Fix: rewrote the class as `PlaygroundProgressWiringTests` (controller import, beginRun/attachEventSource lifecycle, state fields overallPercent/samplerStep/completedNodes/elapsedMs driving the section, negative no-global-subscription pin, polling fallback); deleted the obsolete scoped-tracker-premise class. File runs GREEN.

## 9. FATE OF THE TASK3 FILE (§9)

Renamed **`tests/test_studio_progress_annotations.py`** (naming rule §14: "task3" materially misstated permanent current-product contracts). Category audit: kept SharedProgressModuleTests (live module consumed by canvas), SharedProgressConsumedByModalNodeTests, RunNormalizerAnnotationTests (timing normalization + annotation precedence), PlaygroundProgressDisplayTests, BackendApiAnnotationsTests + BackendApiHistoryQueryTests (COMPAT_WRITE survival + H18 helper retirement), AnnotationDataParityTests, NormalGraphProgressPreservedTests (canvas extension/fetchApi patch), ScopedProgressTrackerTests (module API surface; sibling deep-pin lives in registered test_studio_progress_tracker). 78 → 71 tests. **REGISTERED.**

## 10. MODAL-WORKSPACE UI AST (§10)

Re-measured: **24/24 GREEN** — the two historically-stale pins are resolved truthfully by H18's deletion (no false debt label remains). Content audit: five classes pin current architecture (retired workspace controls, sidebar→modern Settings, no Settings-side workspace routes, canvas Production mode + context-menu marks, protected getStudioRunStatus poll seam, versioned persistence keys, History-V2 normalizer import). Unique + current → **REGISTERED**.

## 11. IMAGE-PACKAGING (§11) — SUPERSEDED BY EVIDENCE

The docstring fix was applied, but unblocking `ast.parse` (BOM) exposed that the suite's architecture pins are wholesale stale: `_compute_comfymodal_deploy_fingerprint_helper`, `dependency_validation_code_schema`, schema versions 3/2, bare `comfyui-modal` combined-ignore entry, size diagnostics — **all absent at HEAD AND worktree** (proven by `git show HEAD:comfyapp.py` marker scan). The BOM setUpClass error had masked 37 latent failures. Current packaging surface is covered by green `test_comfyapp_packaging` (14). **File DELETED (DELETE_STALE)**; docstring debt item closed by deletion.

## 12. DIRTY COMFYAPP FAILURES — FINAL CLASSIFICATION (§12)

- BOM `EF BB BF`: present at HEAD and worktree → permanent file property, NOT transient dirty state.
- `test_comfyapp_ast` 1/1 GREEN (string check; never parses) · `test_comfyapp_packaging` 14/14 GREEN → **removed from active debt**.
- `test_image_packaging_refactor`: was ERROR (harness read comfyapp.py as utf-8 instead of utf-8-sig → TEST HARNESS BUG), then 37 failures vs HEAD-absent symbols → stale suite, deleted (§11).
- Remaining dirty-comfyapp-dependent failures elsewhere (`test_v2_16_20_patch` version pin, audit-round labels, former PerInvocationMaterializationTests) target attributes/labels absent even at HEAD → pre-existing out-of-gate observations; the materialization class was deleted this batch (HEAD-evidenced).

## 13. F8/WORKFLOW REVERSE-ORDER ISOLATION ARTIFACT (§13)

Reproduction matrix (before fix): A normal wf→f8 OK · **B f8→wf FAILED** (`WorkflowRunIntegrationTests.test_05_v2_handler_path`: `'error' != 'ok'`) · C each alone OK · D f8,wf,f8 FAILED · E wf,f8,wf OK.

Captured error: `"v2 history success commit failed: v2 history finalization failed: output-producing run 'r_1' has no associated History output"`.

Root causes — classification **TEST_FIXTURE_LEAK (×2 stacked)**:

1. `test_f8_gpu_authority.F8PlanFreezeTests.test_later_settings_change_does_not_mutate_accepted_plan` wrote `modal_client._current_gpu = "h100"` with no restore (probe: rtx-pro-6000 → h100 across the suite boundary). Fixed with captured-value addCleanup restore (the file's own `_restore_gpu` house pattern used by every other class).
2. The stub-server harness (`test_routes_registered._build_init_with_stub`, used by f8's first class) permanently installs `sys.modules["server"]` with non-None `PromptServer.instance`. `history_v2_writer.get_writer()` then silently enables the production writer singleton at default_data_root(), so `studio_workflow_run.py:1007`'s headless-skip no longer applies and the output-association check runs against a real DB knowing nothing about fake run `r_1`. Fixed per §13 preference ("context-scoped patch / declared environment", explicitly NOT a magic order): `WorkflowRunIntegrationTests.setUp` pins `set_writer_enabled(False)` + `addCleanup(reset_writer_config)`; writer-exercising tests inside the suite keep their own enable/reset scopes.

Post-fix matrix: A OK · B OK · C OK · D OK · E OK. PRODUCT_GLOBAL_LEAK: none (production behaves identically; in real deployments PromptServer exists and the check legitimately runs).

## 14. NAMING CLEANUP (§14)

Renamed where the old name materially misstated content: `test_task3_progress_annotations.py` → `test_studio_progress_annotations.py`; `studio_legacy_settings_authority_unit.mjs` → `studio_settings_compat_authority_unit.mjs`. Everything else retains historical names with accurate docstrings (git/history clarity preserved through this report).

## 15. DEAD TEST FILES (§15)

Deleted: `tests/test_image_packaging_refactor.py` (unique-current-invariant check: none — HEAD-absent symbols; runner references: none; docs claiming authority: none). Deleted class: `PerInvocationMaterializationTests` (unregistered test_experiment_runner.py; four comfyapp helpers absent at HEAD); remaining 73 tests green. No empty historical shells remain among Studio-relevant files.

## 16–17. RUNNER CONSOLIDATION + NODE LEDGER (§16/§17)

`tests/run_studio_tests.py`: six Python registrations + three Node registrations added with ordering comments only where a real constraint exists (h12 after Workflows block — stub-server harness; phase8 next to direct_run — lazy `__init__` patching; run-history_save after Workflows — own stub harness). Resolved-debt comment removed (deleted `test_studio_live_progress` exclusion line replaced with deletion note).

Node ledger: **21 → 25**: +`studio_backend_operations_unit.mjs` (H6), +`studio_model_library_parity_unit.mjs` (H7), +`studio_settings_compat_authority_unit.mjs` (renamed), +`studio_phase_e4d_original_retry_unit.mjs` (E4D Retry Original; slice-bounded transport pin fixed — its "one fetch" count-to-EOF broke when the F3 asset-export helper joined the file). Zero merges/deletions among previously-registered files.

## 18. PYTHON COUNT LEDGER (§18)

```
1824   pre-H20 combined baseline (measured; = 2010 −148 H18 −38 H19)
 +41   tests.test_phase8_execution_mode            (registered)
 +21   tests.test_h12_v2_only_consolidation        (registered)
 +71   tests.test_studio_progress_annotations      (renamed task3 file; 78→71 stale cleanup)
+143   run-history family (run_history + task2 extensions + run_history_save)
 +24   tests.test_modal_workspace_ui_ast           (registered)
 − 0   registered deletions (image-packaging file was never in the gate)
−  4   (out-of-gate only: PerInvocationMaterializationTests deleted; no gate effect)
= 2124 FINAL
```
Independently proven: `build_python_suite().countTestCases() == 2124` AND full-gate python lane `run=2124 fail=0 error=0 skip=0`.

## 19. QUALITY RULE APPLIED (§19)

Registrations favor behavior/public contract/durable architecture: rejection matrices, migration idempotency, COMPAT_WRITE mutation proofs, hash sweeps, protected-seam shape pins, authority absence pins. Source-string checks retained only where the architecture itself is the contract (no mode branch, no legacy importer, route inertness, module minimalism). Arbitrary line-topology assertions were not introduced anywhere.

## 20. SURVIVING CONTRACT MATRIX (§20) — authoritative registered family per row

Shell: five modern pages/aliases/single sidebar → `test_modal_workspace_ui_ast` + `test_testing_shell_integration` + h14 WaveG class. Playground: Single V2 dispatch (`test_studio_direct_run`, phase8), runtime presets (backend CRUD + fake specs), protected progress/cancel (workspace_ui_ast seam pins + h15 ProtectedSingleSeamTests), run-history COMPAT_WRITE (h15 LiveFamiliesRegressionTests + run-history family). Experiments: experiment-v2 live (h15 + `test_history_v2_modern_experiment`), legacy routes inert (h15 + routes_registered), transitional seams (h15). History: V2 sole authority/replay/favorite/note/export/irreproducibility (history_v2_* suites + e4c/e4d/F6/F3/download units). Workflows: immutable Version/Mapping/Workflow Presets/Model Library/Compatibility/Portability (`test_workflow_domain/routes/metadata/run_integration` + model_library* + portability* + H7 unit). Backend: workspaces/deployment/readiness/credentials/Backend Presets/snapshots/repair (`test_studio_backend` + backend suites + H6 unit). Settings: preferences-only/GPU/output authority/no old run mode/no legacy UI (f8 + f4 unit + settings-compat unit + gpu_config pins + testing_settings_js). Canvas compatibility: `/prompt` chain/pass-through/Production/output options (phase8/h12 structural + workspace_ui_ast + modal-node pins). API freeze: H15 409/410 matrix + byte-integrity hash sweeps (h15). Execution: V2-only + retired-vocabulary recognition/rejection/migration + ModalTransport→shared `run_prompt_stream` (phase8 + h12 + h14/h15 census pins). **Every category ≥1 authoritative registered family.**

## 21. REGRESSION COHORT (§21)

| Cohort | Result |
|---|---|
| H14 retirement + H15 freeze + H18 frontend contracts (testing_* ×5, gpu_config, workstream_e) | 451 OK |
| H19 execution cleanup (direct_run, runtime, workflow_run_integration, canonical_execution, experiment_runner, f8) | 401: 397 OK + 4 pre-existing dirty-comfyapp errors → class deleted → re-run clean |
| Workflow domain + modern experiment | 85 OK |
| Routes registered + backend | 347 OK |
| History V2 families + presets + portability + phase-E blocks | green inside full lane |

## 22. FULL GATE (§22)

Run twice end-to-end on the final tree (isolation changes landed):

```
python tests/run_studio_tests.py --fake          # run 1
  python             run=2124  fail=0  error=0  skip=0
  node-unit          run=25    fail=0  error=0  skip=0
  fake-playwright    PASS (wrapper aggregate)
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (3.8m) / 211

python tests/run_studio_tests.py --fake          # run 2
  python             run=2124  fail=0  error=0  skip=0
  node-unit          run=25    fail=0  error=0  skip=0
  fake-playwright    wrapper flake ×1 (known parallel-load family, first occurrence this batch)
npx playwright ... (immediate direct rerun)      211 passed (3.7m) / 211
npm run test:fake (bounded repeat)               211 passed (3.7m) / 211
```
Exact fake count green in all three direct executions; no assertion/timeout weakened; no hidden focused-only failure for any REGISTER-classified suite.

## 23. POST-H20 UNREGISTERED SUITE CENSUS (§23)

Studio-relevant remainder (all green unless noted): `test_experiment_runner` 73 (focused: legacy scheduler chain + CheckpointStreamInvoker units), `test_canonical_execution`, `test_run_prompt_options`, `test_warmup_profile_dedup`, `test_restore_timing_data_flow`, `test_production_*` (V2 plan/dispatch infra), `test_comfyapp_ast/packaging` (deploy infra), `test_workstream_e_patches` (worker-progress buffer units; Results-retirement half redundant with registered testing_results_js), `test_modal_settings_gpu_config` (REDUNDANT — registered settings-compat + F8 units pin the same contract behaviorally), `test_studio_workflow_manifest` + `test_studio_workflow_run_plan_identity` (identity matrix duplicated by registered workflow-run-integration + F8 freeze tests), `test_history_index` (covered via registered run-history family), `test_experiment_modern_binding/plan/scheduler/store/models/setup_adapter/lease` (modern-experiment units; end-to-end authority in-gate via history_v2_modern_experiment + routes_registered), `test_deploy_no_auto_generation` (still-valid forbidden-symbol list incl. H19 names). All other unregistered modules (~200 `test_v2_*`, `test_runtime_*`, benchmarks, v2ctl, step3, e2x forensics) = NON_STUDIO per the runner charter. Browser `.mjs` harnesses = fake-lane/runtime internals. **"Meaningful current unit suite simply unregistered": ZERO.**

## 24. WAVE-G REMAINING PRODUCTION RESIDUE MAP (§24) — UNKNOWN = 0

See FF-8 in the contract appendix (authoritative table). Summary: KEEP_MODERN `_schedule_and_start`+chain (pinned seam) and `V2ExperimentInvoker` (mandated survivor) · KEEP_COMPAT MARK_OPTIONAL span vocabulary · DELETE_HELPER candidates requiring coordinated test migrations first: `handle_studio_experiment`, `build_single_run_spec`, `__init__._collect_input_images`, plus NEW finding `createScopedTracker` export (zero production consumers) · ROUTE_PRUNE_CANDIDATE: registered-and-inert Comparison writers/run, legacy Experiment writers/executors, `/studio/experiment`, warmup run/invalidate (+status ZERO_CALLER read), `/auth/setup`, legacy prompt/image preset writers, `/studio/backends` writers.

## 25. ROUTE PRUNING NECESSITY (§25)

Per-candidate factors recorded in FF-9. External compatibility value: bounded truthful responses already serve old clients; stored-data readers require COMPAT_READ survival; fake mirrors exist only for live families (+ intentional experiment mirror); registry pins valid; inert-shim maintenance/security downside negligible; dead implementation behind shims ≈ zero post-H19 (handlers are bounded response bodies). **Recommendation: KEEP_INERT_COMPAT everywhere in Phase H; DEFER_FUTURE_MAJOR for physical pruning bundled with a future major API-boundary decision; DELETE_IN_G: none.** Not executed here.

## 26. PHASE-H CLOSURE BLOCKER CHECK (§26)

**BLOCKS_H_CLOSURE: NONE** — no architectural duplication or dead authority violating Phase-H goals remains; all §28 must-preserve invariants carry registered coverage (§20 matrix).
**OPTIONAL_G_HYGIENE (non-blocking):** physical route pruning (FF-9); deferred-helper deletions with test migrations (FF-8); residual Settings Runtime-&-Backend display rows (Deploy/Snapshots/Presets counts — read-only consumers of live authorities; Backends row already removed by H16); compatibility naming.
**PHASE_I:** A/B slider + frozen §29 list.

## 27. FILES MODIFIED / DELETED BY THIS LANE ONLY

Modified tests: `tests/run_studio_tests.py` (registrations + comments), `tests/test_f8_gpu_authority.py` (one restore), `tests/test_workflow_run_integration.py` (writer-seam pin + tearDown preserved), `tests/test_task3_progress_annotations.py` → renamed `tests/test_studio_progress_annotations.py` (docstring, rewritten wiring class, obsolete class removal), `tests/test_experiment_runner.py` (stale class removal), `tests/test_studio_workflow_run_plan_identity.py` (one stale selected_gpu expectation conformed to F8 overlay), `tests/studio_backend_operations_unit.mjs` (O22 rewrite), `tests/studio_model_library_parity_unit.mjs` (§15 rewrite), `tests/studio_legacy_settings_authority_unit.mjs` → renamed `tests/studio_settings_compat_authority_unit.mjs` (header/footer), `tests/studio_phase_e4d_original_retry_unit.mjs` (slice bound), `STUDIO_TEST_GATE.md` (table refresh).
Deleted: `tests/test_image_packaging_refactor.py`.
Docs: `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (FF appendix), this report.
Production code modified: **NONE**. Stored data touched: **NONE**.

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.

---

## FINAL VERDICTS

`WAVE G TEST CONSOLIDATION COMPLETE`

`PHASE H CLOSURE READY` — closure does not require another implementation lane; remaining items are optional hygiene (FF-9/FF-10) or Phase-I scope.
