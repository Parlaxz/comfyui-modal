# PHASE H17 — WAVE-F TEST CONVERGENCE & CLOSURE (F-TST FINALIZATION) (2026-08-25)

**Batch type:** H-WAVE F test/reconciliation lane, ran AFTER H15 (F-SRV) and H16 (F-BE); no concurrent production writer. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean; unrelated dirty-tree work untouched. No production code modified.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` incl. Follow-Ups A/B/C/D (FD-1…FD-26), `PHASE_H5D_WAVE_E_CONVERGENCE_WAVE_F_FREEZE_2026-08-24.md`, `PHASE_H15_WAVE_F_SERVER_COMPATIBILITY_WRITE_FREEZE_2026-08-24.md`, `PHASE_H16_WAVE_F_SETTINGS_BACKENDS_CONSUMER_REMOVAL_2026-08-24.md`, `PHASE_H14_LEGACY_SETTINGS_COMPARISON_RETIREMENT_2026-08-24.md`, H12/H13 where referenced by FD-23.
**Authoritative summary:** H5 FOLLOW-UP E appendix in the contract freeze document. This report is evidence detail.

---

## 0. VERDICT

`H17 COMPLETE — WAVE F COMPLETE.`

Combined H15+H16 tree verified coexisting with zero conflicts. The 36-test H15 Wave-F compatibility suite audited (33 UNIQUE_MEANINGFUL / 3 DUPLICATE_BUT_USEFUL / 0 redundant / 0 stale) and registered in the authoritative gate after `test_h14_wave_e_retirement`. Count ledger reconciles exactly: 1974 + 36 = **2010**. One authoritative full gate green: **Python 2010/2010 · Node-unit 21/21 · Fake Playwright 211/211 exact (first attempt, zero flake)**. FD-23 matrix: all 21 rows accounted. Route census: zero UNKNOWN.

## 1. REGISTRATION AUDIT (`tests/run_studio_tests.py`, inspected before edits)

| Suite | Pre-H17 status |
|---|---|
| `tests.test_h14_wave_e_retirement` | REGISTERED (:95) |
| `tests.test_h15_wave_f_server_freeze` | NOT registered ← known Wave-F gate debt |
| `tests.test_phase8_execution_mode` | NOT registered (G debt) |
| `tests.test_h12_v2_only_consolidation` | NOT registered (G debt) |
| Node `studio_backend_operations_unit.mjs` | NOT registered (G debt) |
| Node `studio_model_library_parity_unit.mjs` | NOT registered (G debt) |
| Node `studio_legacy_settings_authority_unit.mjs` | NOT registered (MIGRATE-THEN-REGISTER, G debt) |

H5D's census was still exact; no registration drift existed beyond the declared H15 debt.

**Edit made:** one insertion after `tests.test_h14_wave_e_retirement` — `"tests.test_h15_wave_f_server_freeze"` with an ordering-constraint comment. Placement rationale: the suite builds its own cached stubbed `__init__.py` instance via the `test_routes_registered` harness and must stay after the Workflows block for the identical in-process loading constraint documented for F8/H14. Not arbitrary; not hiding any ordering bug (none found — §6).

Also corrected the suite's own module docstring ("Not registered…" → "Registered … by H17 F-TST"). Comment-only; no assertion touched.

## 2. IMPLEMENTATION COEXISTENCE VERIFICATION (§1 of mandate)

### H15 markers verified in `__init__.py` (freeze-code census)
COMPARISON_READ_ONLY ×6 · COMPARISON_RETIRED ×1 · EXPERIMENT_RETIRED ×10 · EXPERIMENT_READ_ONLY ×5 · WARMUP_RETIRED ×2 routes (+1 docstring mention) · AUTH_SETUP_RETIRED ×1 · BACKENDS_READ_ONLY ×4 · LEGACY_PRESETS_READ_ONLY ×8. Matches H15 §1 route-for-route:

- Comparison: six mutation routes → 409 `COMPARISON_READ_ONLY`; ten COMPAT_READ routes unchanged (validate/detect-slots still pure-compute POSTs, proven NOT 409 by registered test); `/comparison/run` → 410 `COMPARISON_RETIRED`. ✅
- Legacy Experiment: execution-retired → 410 `EXPERIMENT_RETIRED`; write-retired → 409 `EXPERIMENT_READ_ONLY`; compile unchanged pure compute 200; GET `/experiments/{id}` + stop-now byte-untouched. ✅
- Legacy Studio Experiment: `POST /studio/experiment` → 410 before preset load/REGISTRY/History-V2/scheduler; `/studio/experiment-v2` untouched (zero freeze codes in `experiment_modern_routes.py`). ✅
- Warmup: run → 410 `WARMUP_RETIRED`; invalidate → 409 `WARMUP_RETIRED`; status reads 200 `{status,state}`. ✅
- auth/setup → 409 `AUTH_SETUP_RETIRED` before token validation/toml write/workspace upsert/deploy thread. ✅
- Legacy prompt/image presets: writes ×8 → 409 `LEGACY_PRESETS_READ_ONLY`; reads survive. ✅
- `/studio/backends`: GET (+`?kind=comparable`) survives answering stored data; writers ×4 → 409 `BACKENDS_READ_ONLY`. ✅
- Live exclusions: presets CRUD end-to-end green; Workflow Presets distinct/unfrozen; run-history reads answer; annotations PATCH actually mutates meta.json; save delegates to pipeline; V2 ModalTransport `run_prompt_stream` reference pinned; census `async for X in run_prompt_stream(` == `["_msg"]` only. ✅

### H16 markers verified in `web/studio-settings.js`
`settings-runtime-backends` testid ABSENT · `/studio/backends` fetch ABSENT · no replacement row/API/portability-target surface · Deploy state row, Snapshots count, Presets count, "Open Backend tab" link all PRESENT · removal-marker comment at :559. ✅

No missing marker anywhere → nothing compensated, nothing weakened.

## 3. H15 TEST QUALITY AUDIT (all 36 classified)

| Class | Tests |
|---|---|
| A UNIQUE_MEANINGFUL (33) | six-writers-409+message · writers+run hash-integrity · ten-read-routes-answer · validate/detect-slots-not-409 · exec-410 set · write-409 set · REGISTRY snapshot equality · compile-pure-compute · experiment COMPAT_READs · detail-404 · detail-shape · stop-now-404 · stop-now handler-region pin · detail-not-frozen pin · studio-experiment-410-no-side-effect · creator-pipeline-unreachable · fake-mirror parity · experiment-v2-live · warmup-run-410 · invalidate-409+file-hash · warmup-status-reads · no-streaming-in-warmup+census · shared-transport-survives · auth-setup-tripwired · legacy-presets-409 · presets-dir-hash+reads · backends-writers-409+store-hash · backends-GET-shim · backend-preset-CRUD-live · workflow-presets-distinct · run-history reads+COMPAT_WRITE-mutates · freeze-vocabulary-hygiene · frozen-routes-stay-registered |
| B DUPLICATE_BUT_USEFUL (3) | run-stays-410 (overlaps H14 pin) · seventeen-routes-registered (overlaps `test_routes_registered`) · profile-list-contains-seeded (subsumed by sibling's first check) |
| C DUPLICATE_REDUNDANT (0) | — |
| D STALE/WRONG (0) | — |

Every test pins product/API behavior (codes, zero mutation, survival, exclusions), not line placement. All 36 registered unchanged.

## 4. H16 COVERAGE CHECK (§5) — already fully inside the gate

Registered pins in `tests/test_studio_backend.py`: Backends testid absent (:400) · "Backends" label absent (:410) · Settings-side `/studio/backends` fetch absent (:464) while `/studio/snapshots` + `/studio/presets` fetches present (:462–463) · Deploy state (:396/:407), Snapshots (:397/:408), Presets (:398/:409), Open Backend link (:401) preserved. **All six required behaviors proven by meaningful registered assertions → NO duplicate H16 suite created; no combined assertion was missing → no edit to any existing file needed.**

## 5. FAKE PARITY CHECK (§6) — sufficient, no new fake work

`fake-server.mjs`: `POST /comfymodal/studio/experiment` mirror returns bounded 410 `EXPERIMENT_RETIRED` with zero creation (:415–419); harness-only seed endpoint `/__comfymodal_test/legacy-experiment-seed` (:821); stop-now (:428) and experiment-v2 (:498) mirrors intact. Runtime spec `studio-fake-experiment-gating.spec.mjs` G5: seeds ONLY via the control endpoint, proves the retired route answers 410 `EXPERIMENT_RETIRED`, creator log stays at exactly the harness seed, zero legacy creates from product state, v2 create path normal (G2). Existing coverage sufficient → no new fake file/spec.

## 6. ORDER / GLOBAL-STATE AUDIT (§11)

| Check | Command cohort | Result |
|---|---|---|
| A alone | `tests.test_h15_wave_f_server_freeze` | Ran 36 — OK (21.7s) |
| B predecessor→H15 | h14 + h15 | Ran 63 — OK |
| C H15→successor | h15 + presets_images + presets_prompts | Ran 54 — OK |
| D route/H14 context | routes_registered + f8_gpu_authority + h14 + h15 | Ran 165 — OK |
| Reverse probe | h15 + f8_gpu_authority | Ran 77 — OK |

Conclusion: H15 leaks no global state (its `_COMFYUI_ROOT`/`_NODE_DIR` mutations are try/finally-restored on its own cached init instance; patches are context-scoped). Preceding-suite leakage: none observed. Runner isolation: sufficient at this insertion point. The historical F8-before-workflow-reverse-order artifact is unrelated to this placement (insertion is after both) and remains G debt.

## 7. DIRECT RUNS OF OUT-OF-GATE SUITES (§8/§9/§10)

| Suite | Result | Disposition |
|---|---|---|
| `tests.test_phase8_execution_mode` | Ran 41 — OK | G owns registration; adequate surviving V2-only protection exists in-gate (H12-era guards + H15 suite) |
| `tests.test_h12_v2_only_consolidation` | Ran 21 — OK | same |
| Node `studio_backend_operations_unit.mjs` (H6) | PASS | modern Backend operations unregressed by Wave-F freezes; registration stays G |
| Node `studio_model_library_parity_unit.mjs` (H7) | PASS | Model Library parity unregressed; registration stays G |
| Node `studio_legacy_settings_authority_unit.mjs` | ALL PASS | currently executes without pinning dead UI (surviving authority/output/canvas/Comparison compat sections); MIGRATE-THEN-REGISTER unchanged, G-owned |
| Node `studio_phase_f4_settings_authority_unit.mjs` | PASS (registered) | — |
| Node `studio_phase_f8_gpu_reset_unit.mjs` | PASS (registered) | — |

## 8. FOCUSED COMBINED WAVE-F RUN (§13)

| Cohort | Result |
|---|---|
| h15 + h14 + routes_registered + studio_backend | Ran 410 — OK |
| workflow_routes + workflow_domain + history_v2_modern_experiment | Ran 104 — OK |
| phase8 + h12_v2_only (direct) | Ran 62 — OK |
| Settings authority / F8 GPU reset / H6 ops / H7 parity node units | PASS ×4 |
| Full gate (below) | 2010 / 21 / wrapper PASS |

## 9. STORE INTEGRITY RE-PROOF (§14)

The now-registered H15 suite contains and passes all required integrity proofs: Comparison temp-store SHA-256 equality across 6 writers + run · Experiment REGISTRY snapshot equality across 14 retired requests · `.deploy_warmup_state.json` SHA+mtime · `.presets/` full-tree SHA · `.studio_backends.json` SHA+mtime · `modal.toml` SHA+mtime (+ tripwires proving `_write_modal_toml`/workspace upsert/`_run_deploy_background` unreachable).

## 10. EXCLUSION REGRESSION CHECK (§15)

All protected exclusions verified unchanged through registered tests + source census: GET `/experiments/{id}` + stop-now (handler-region pins, no freeze vocabulary) · `/studio/experiment-v2` · `/studio/run` (registered direct-run suite green in gate) · History V2 family (history_v2_* suites green) · run-history annotations/save (mutation proven) + reads · `/studio/presets*` CRUD live · Workflow Presets distinct · workspaces/deploy/credentials/models/snapshots (backend suites + fake specs green) · Model Library (suites + H7 unit) · canvas `/prompt` chain (structural tests green) · V2 `run_prompt_stream` (census + transport pin) · Comparison COMPAT_READ set. Zero production edits made by this lane.

## 11. COUNT LEDGER (§12)

```
1974   starting registered Python baseline (FD-1; confirmed pre-registration)
+ 36   newly registered (tests.test_h15_wave_f_server_freeze, all kept)
+  0   new tests elsewhere
-  0   removed
= 2010 FINAL
```
Independently proven twice: `build_python_suite().countTestCases() == 2010` AND full-gate python lane `run=2010 fail=0 error=0 skip=0`.

## 12. AUTHORITATIVE FULL GATE (§17/§18)

```
python tests/run_studio_tests.py --fake
  python             run=2010  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (wrapper aggregate run=1)
ALL STUDIO LANES GREEN

npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (4.1m) / 211
```

Known timing flake (`studio-fake-lifecycle.spec.mjs` test 11): did NOT recur this batch. Occurrence count this batch: **0**. No timeout/assertion weakened; nothing hidden.

## 13. FD-23 MATRIX — FINAL COVERAGE MAP (§7)

| # | Requirement | Test file | Method/section | Registered? | Fake? | Focused-only? | Disposition |
|---|---|---|---|---|---|---|---|
| 1 | Comparison mutations 409 + zero writes | tests/test_h15_wave_f_server_freeze.py | ComparisonWriteFreezeTests (both tests) | YES (H17) | n/a | no | gate |
| 2 | Comparison reads work | same | ComparisonReadCompatTests | YES | n/a | no | gate |
| 3 | /comparison/run 410 | same (+ test_h14_wave_e_retirement pin) | test_run_stays_410_comparison_retired | YES | n/a | no | gate |
| 4 | Experiment retired 410/409 + zero mutation | same | ExperimentRetirementTests | YES | n/a | no | gate |
| 5 | /studio/experiment cannot execute | same | StudioExperimentRetirementTests | YES | runtime: gating spec G5 | no | gate |
| 6 | experiment-v2 live | same + test_history_v2_modern_experiment | test_experiment_v2_route_still_registered_and_live | YES | yes | no | gate |
| 7 | GET /experiments/{id} unchanged | same | ProtectedSingleSeamTests (detail ×2) | YES | n/a | no | gate |
| 8 | stop-now unchanged | same | ProtectedSingleSeamTests (stop-now ×2) | YES | mirror intact | no | gate |
| 9 | warmup cannot execute | same | WarmupFreezeTests | YES | n/a | no | gate |
| 10 | V2 uses run_prompt_stream | same | test_shared_transport_survives_for_v2 + census | YES | n/a | no | gate |
| 11 | run-history reads remain | same | LiveFamiliesRegressionTests | YES | recent-runs/lifecycle specs | no | gate |
| 12 | annotations/save still write | same | LiveFamiliesRegressionTests (mutation proven) | YES | annotations specs | no | gate |
| 13 | Backend/Runtime Presets writable | same | test_backend_runtime_presets_crud_still_live | YES | preset/wizard specs | no | gate |
| 14 | Workflow Presets unaffected | same + workflow suites | test_workflow_presets_distinct_and_unfrozen | YES | portability/workflow specs | no | gate |
| 15 | Backends row absent + GET shim | test_studio_backend.py :392–464 + H15 BackendsFreezeTests | three H16 pins + GET-shim test | YES | settings-page spec | no | gate |
| 16 | auth/setup inert | H15 suite | AuthSetupRetirementTests | YES | n/a | no | gate |
| 17 | stores byte-identical under retired writes | H15 suite | hash sweeps (6 store families) | YES | n/a | no | gate |
| 18 | fake /studio/experiment mirrors production | H15 suite + gating spec G5 | test_fake_mirror_matches_production_retirement | YES | YES | no | gate |
| 19 | H12 V2-only contract green | test_phase8_execution_mode (41) + test_h12_v2_only_consolidation (21) | direct run | NO (G debt) | n/a | focused-direct | green; in-gate V2 protection via H12 guards + H15 |
| 20 | H13 recent-runs contract green | browser/fake/studio-fake-recent-runs-history-v2.spec.mjs + node units | fake lane | YES (fake lane) | YES | no | 211-green |
| 21 | H14 retirement contract green | tests/test_h14_wave_e_retirement.py | whole suite (27) | YES | n/a | no | gate |

Every row has authoritative gate coverage or a clearly justified lower-level equivalent.

## 14. ROUTE CENSUS (§19)

See FE-2 in the contract appendix (authoritative). Summary counts: Comparison 10/6/1 · Experiment 2 TRANSITIONAL_MODERN protected + 5 COMPAT_READ + 1 ZERO_CALLER + 10 RETIRED_EXECUTION (incl. adjacent /studio/experiment) + 5 RETIRED_WRITE + 1 MODERN_LIVE · run-history 4 COMPAT_READ + 2 COMPAT_WRITE · presets authorities MODERN_LIVE(_TRANSITIONAL) · backends 1 COMPAT_READ + 4 RETIRED_WRITE + 0 modern consumers · warmup ZERO_CALLER/RETIRED_EXECUTION/RETIRED_WRITE · auth/setup RETIRED_WRITE · legacy prompt/image presets 4 COMPAT_READ + 8 RETIRED_WRITE. **UNKNOWN rows: 0.**

## 15. OUT-OF-GATE DEBT RE-MEASURE (§16; none fixed except lane-caused)

| Item | Current state |
|---|---|
| tracker-membership ×5 (`test_task3_progress_annotations`) | STILL FAILING (failures=5) — G |
| Production summary-label pin (`ModalProductionUiAstTests`) | STILL FAILING (class failures=2, includes next row) — G |
| output-savefolder literal pin (same class) | STILL FAILING — G |
| F8/workflow reverse-order isolation artifact | unchanged historical G debt; unrelated to new registration point (proven §6) |
| dirty comfyapp.py BOM SyntaxError | RE-MEASURED GREEN: BOM bytes present (EF BB BF) but `test_comfyapp_ast` 1/1 OK — resolved in current tree; G re-verifies |
| dirty comfyapp.py packaging TypeError | RE-MEASURED GREEN: `test_comfyapp_packaging` 14/14 OK |
| Unregistered H6/H7/H12/legacy-settings-authority suites | all re-run GREEN directly (§7); registration remains G-owned |

## 16. FILES MODIFIED BY THIS LANE ONLY

- `tests/run_studio_tests.py` — one registration entry + ordering comment.
- `tests/test_h15_wave_f_server_freeze.py` — module-docstring registration-status correction only (no assertion/fixture change needed).
- `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` — appended H5 FOLLOW-UP E (authoritative).
- `PHASE_H17_WAVE_F_TEST_CONVERGENCE_AND_CLOSURE_2026-08-25.md` — this report.

Production code modified: NONE. New test files created: NONE (not needed). Deleted: NONE.

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
