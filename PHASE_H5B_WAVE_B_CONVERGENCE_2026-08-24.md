# PHASE H5 FOLLOW-UP B — WAVE-B CONVERGENCE EVIDENCE DETAIL (2026-08-24)

**Batch type:** H5 contract follow-up / same-batch Wave-B reconciliation. READ-ONLY against production code and tests. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset/stash/clean. Files modified by this batch: `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (appended "H5 FOLLOW-UP B" section — AUTHORITATIVE) + this document.
**Inputs read completely:** H5 contract freeze (incl. Follow-Up A errata), `PHASE_H5A_WAVE_A_OPERATIONAL_RECONCILIATION_2026-08-24.md`, `PHASE_H9_DEAD_HISTORY_LEGACY_TAB_RETIREMENT_2026-08-24.md`, `PHASE_H10_LEGACY_ENTRYPOINT_REDIRECTS_2026-08-24.md`, `PHASE_H11_DEAD_EXECUTION_HELPER_RETIREMENT_2026-08-24.md`. The current shared tree was inspected directly, not merely the reports.

---

## 0. VERDICT

`H5 FOLLOW-UP B COMPLETE — POST-WAVE-B SHARED TREE CONVERGED AND GREEN. ALL H9/H10/H11 INTENDED CHANGES COEXIST. ZERO MERGE REPAIRS REQUIRED. AUTHORITATIVE BASELINE: PYTHON 1941 · NODE 21 · FAKE 199.`

---

## 1. AUTHORITATIVE FULL GATE (run once, after all Wave-B writers finished)

```
python tests/run_studio_tests.py --fake
==============================================================================
STUDIO GATE SUMMARY
  python             run=1941  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=0    error=0    skip=0
ALL STUDIO LANES GREEN
```

Exact fake Playwright count: the npm wrapper reports only an aggregate pass/fail, so the fake config was run directly once:

```
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  199 passed (3.8m)
```

199 = the pre-B fake count exactly; Wave B added/removed zero fake tests.

Independent collection check (no test execution): `build_python_suite().countTestCases()` → **1941**, matching the gate.

## 2. 1941-VS-1991 NUMERICAL LEDGER

| Item | Δ | Evidence |
|---|---|---|
| Pre-Wave-B frozen baseline | 1991 | H5 §27 (inherited from G closure); re-observed by H11 |
| H9 retired in-gate assertions | −74 | H9 §5 itemization: timing −10 (`FormatPageMetadataRED` 5, `TotalCountWiringRED` 4, `TotalCountBeforeFilterBarWiringRED` 1), backend −15, shell-integration −24 net, ui-wired −25 net |
| H10 net in-gate additions | +24 | see attribution below |
| Accidental resurrection | 0 | §3/§4 of this document |
| **Current authoritative total** | **1941** | direct collection + green gate |

Arithmetic: 1991 − 74 + 24 = 1941 (matches H9's own account).

### +24 attribution
- H11 added **zero** tests: its entire diff is `execution_runtime.py` −12 lines (two dead helper functions). Verified against its report §2/§8 and by repo-wide grep (`def is_v2|def is_shadow` → zero matches).
- Therefore +24 is H10's net in-gate footprint. Currently present in `tests/test_testing_shell_integration.py`: `LegacyEntrypointRedirectTests` (**11 tests, explicitly NEW per H10 §10**), `RootCauseCachedShellLegacyRoutingTests` (1), `LegacyComparisonSidebarGuardTests` (5), `LegacySettingsSidebarGuardTests` (6) = 23 tests across four H10-owned classes, plus net routing-pin updates in shared structural files.
- The exact pre-B counts of the three REWRITTEN classes are not recoverable post-hoc because no Wave-B commit exists (the tree has been intentionally dirty since HEAD 2026-08-22, which predates Phases E–H). The aggregate reconciles exactly regardless; per-file confirmation below shows every H9-owned file matches H9's post-edit focused counts, so no third writer contributed.

### Per-file confirmation (current tree vs H9 post-edit focused runs)
| File | Current | H9 reported post-edit | Consistent |
|---|---|---|---|
| tests.test_studio_timing_integration | 54 | 54/54 | YES |
| tests.test_studio_backend | 283 | 283/283 | YES |
| tests.test_testing_shell_integration | 200 | 200/200 | YES |
| tests.test_testing_ui_wired | 170 | 170/170 | YES |

### Why H11 saw 1991 and H10 saw 1974+35 red
- **Not wrapper discovery/cache/order:** `tests/run_studio_tests.py` builds the suite fresh on every invocation from the explicit `STUDIO_PY_MODULES` allowlist (+ fixed pytest-style files). There is no cache, and ordering is deterministic.
- **H11's 1991:** a clean 1991 with zero failures is only possible if H9's deletions were NOT yet on disk — with them present, the then-current structural tests reading `studio-history.js`/`testing-dashboard.js`/`testing-history.js` would have failed and the count would have dropped. H11's own edit cannot move any count. Conclusion: H11's full gate measured an EARLIER filesystem state (temporal staleness), not a resurrected tree.
- **H10's 1974 (+29 fail, +8 error):** mid-flight snapshot, net −17 at that instant (partial landing of H9's pruning plus partial H10 additions). Every red it listed targeted concurrently-churning H9 surfaces or the pre-existing out-of-gate pins (§6) — none in H10 scope. Consistent with a partially-converged tree.

## 3. RETIRED-FILE INTEGRITY (H9 deletions stay deleted)

| Path | Exists |
|---|---|
| `web/studio-history.js` | NO |
| `web/testing-dashboard.js` | NO |
| `web/testing-history.js` | NO |

No production importer of any of the three remains; `web/studio-history-v2.js` and the four surviving legacy tab modules (`testing-setup/profiles/results/settings.js`) are present as intended. No lane restored any deleted file; nothing to repair.

## 4. OBSOLETE-TEST RESURRECTION SWEEP (current versions of H9-owned files)

Repo-wide sweep for retired symbols/classes across `tests/`:
`FormatPageMetadataRED`, `TotalCountWiringRED`, `TotalCountBeforeFilterBarWiringRED`, `DashboardHierarchyTests`, `HistoryRowLayoutTests`, `ProgressiveClarityDashboard*`, `ProgressiveClarityHistory*`, `StudioHistorySafetyTests`, `HistoryPaginationTests`, `HistoryFilterTests`, `HistorySortTests`, `HistoryGroupingToggleTests`, `HistoryFavoriteNoteTests`, `renderHistory`, `formatPageMetadata`, `resolveTotalCount` → **zero matches**.

Remaining references to the retired filenames are exclusively negative assertions or explanatory comments:
- `test_testing_ui_wired.py:662` — asserts the retired modules are NOT referenced;
- `test_testing_shell_integration.py:291/296` — retirement notes;
- `test_task3_progress_annotations.py:504`, `test_testing_ui_wired.py:1170` — comments.
- `.mjs` files: zero references to any retired filename.

Spot-verifications of rewritten pins:
- `test_studio_backend.test_settings_legacy_section` (:402) pins the four-entry Legacy list with `assertNotIn("Legacy Dashboard")` / `assertNotIn("Legacy History")`.
- `test_modal_workspace_ui_ast.StudioHistoryNormalizerTests` pins `studio-history-v2.js`'s normalizer import (moved-to-V2 form).
- `studio_history_v2_grid_columns_unit.mjs` and `studio_phase_f4_settings_authority_unit.mjs` contain no dead-source reads; both PASS.

Modern replacement assertions (favorite-star-as-button on V2, Playground↔V2 favorite/note parity, V2 grid columns, F4A authority) all remain and pass.

## 5. H9∩H10 SHARED-FILE MERGE INTEGRITY (`web/modal-testing.js`)

Both hold simultaneously in the current file:
- **A. H9 loader reduction:** `TAB_MODULES` (:435–440) contains exactly setup/profiles/results/settings → `./testing-{setup,profiles,results,settings}.js`. No `TAB_DASHBOARD`/`TAB_HISTORY` constants exist anywhere.
- **B. H10 alias map:** `ALIAS_PAGE_MAP` (:239–247) = `{playground→playground, dashboard→backend, setup→playground, profiles→playground, results→history, history→history, settings→settings}` with bounded deprecation notices for setup/profiles (:250–251), applied via `_applyLegacyAliasNavigation` on both cached-shell (:322) and fresh-shell (:379) paths.
- Zero `activeLegacyTab` occurrences in `modal-testing.js` (the remaining `activeLegacyTab` state machinery in `studio-settings.js`/`studio-shell.js` is the Settings-page legacy-group mechanism that intentionally survives until Wave E).
- Neither lane overwrote the other: loader entries (module loading) and compatibility aliases (external opener routing) are distinct concepts and both are intact.

## 6. OUT-OF-GATE FAILURES — AUDIT AND CLASSIFICATION

Current run: `pytest tests/test_task3_progress_annotations.py tests/test_modal_workspace_ui_ast.py -q` → 7 failed, 97 passed (104 collected).

### 6.1 Tracker-membership ×5 — CLASS B (pre-existing, unrelated to Wave B)
Failing: `SharedProgressConsumedByPlaygroundTests::{test_imports_progress_module, test_subscribes_to_tracker_progress, test_tracker_only_updates_in_flight, test_uses_get_shared_tracker}`, `PlaygroundUsesScopedTrackerTests::test_imports_create_scoped_tracker`.

Evidence:
- Current `web/studio-playground.js` contains no `comfymodal-progress` import, no `getSharedTracker()`, no `createScopedTracker`, no direct `onProgress` subscription; it retains `_scopedTracker` lifecycle refs via state (`_disposeScopedTracker` :2576) with a comment that creation moved to the run/experiment handlers.
- `git diff HEAD -- web/studio-playground.js` = exactly 3 hunks, ALL H10's documented edits (`navigateToLegacySetup` removal + two copy rewrites). No other uncommitted writer touched this file.
- `git show HEAD:web/studio-playground.js` already lacks every asserted symbol while HEAD's test file already asserts them → the failures exist at HEAD, i.e., they predate Phase H entirely.
- The live wiring is real and modern: `studio-experiment-mode.js:1083` creates the scoped tracker; `modal-node.js:3` owns the shared tracker. The invariant evolved; the assertions still target the old address.

Disposition: Wave G L-TST re-point at current owners. NOT caused by H9/H10/H11 (Class A ruled out by the diff proof).

### 6.2 `test_production_summary_labels` — CLASS B (pre-existing stale copy pin)
Asserts `"Production plan"` in `web/modal-settings.js`. The string exists neither in HEAD's copy nor anywhere in current `web/` (repo-wide grep). The feature row itself ("Sampler previews: disabled", :1983) still exists — only the asserted heading text is gone, removed before HEAD (pre-Aug-22). Disposition: Wave G prune/re-point; do NOT patch production copy to satisfy a stale pin.

### 6.3 `test_output_save_folder_defaults_are_normalized` — CLASS D (another completed phase's change now requiring reconciliation)
Asserts literal `"output/modal"` in BOTH `modal-node.js` and `modal-settings.js`. Current `modal-settings.js` imports `DEFAULT_OUTPUT_SAVEFOLDER` from the shared server-first authority `studio-output-preferences.js` (:27 `export const DEFAULT_OUTPUT_SAVEFOLDER = "output/modal"`) — the F4A-era single-shared-helper consolidation (uncommitted pre-B work; HEAD still had a local `const`). The normalization invariant is honored through the shared module; only the literal-in-file pin went stale. Not an H9/H10/H11 regression (H9/H11 never touched `modal-settings.js`; H10's edit there was region-scoped to hidden-sidebar-registration removal). Disposition: test-side re-point owned by that phase's reconciliation / Wave G; no production change warranted.

**Class A total: 0.** No Wave-B edit broke any still-required invariant; consequently NO narrow merge repair was performed and none was needed.

## 7. PRESERVATION PROOFS (converged tree)

- **Settings Legacy group:** exactly `Legacy Setup / Legacy Profiles / Legacy Results / Legacy Settings` (`studio-settings.js:658–661`) + temporary `Open Legacy Settings` opener (:649–651). Dashboard/History entries absent; group retained for Wave E.
- **Comparison (Wave E scope untouched):** `modal-comparison.js` retains `buildProfilesTab` (:157), `buildRunnerTab` (:743), `_initContextMenu` (:1425), `window.mountComparisonProfiles/Runner` (:1567/1578), `window.openComparisonProfilesOverlay/RunnerOverlay` (:1643/1649). Backend `/comfymodal/comparison/*` route family fully registered (`__init__.py:5424–5733`: profiles CRUD/duplicate/validate/slots/run/results/workflow/config/gallery).
- **Legacy overlay compat:** `window.open_comfymodal_settings` defined at `modal-settings.js:4155`; sole consumers are inside the Wave-E legacy surface (`testing-settings.js:90/109/173`). Modern sidebar ("Open Settings") routes to the modern Settings page; zero modern funnels into the overlay.
- **Hidden registrations:** `__comfyModalEnableLegacySidebarTabs` → zero occurrences in `web/`; `registerSidebarTab` has exactly one call site (`modal-testing.js:569/574`, the normal Studio sidebar entry).
- **History compatibility freeze:** `GET /comfymodal/run-history` (:6953), detail/logs/timing (:6996–7013), annotations PATCH (:7023), save (:7084), `GET /comfymodal/history` (:7797), `/comfymodal/experiments` family (:5839–6719), `.run_history` readers (`run_history.py` record/list/get functions), `legacy_mapping` + `LegacyMigrationSeam` (`history_v2_migration.py:56/85/193`), replay projection (`replay_capable` `history_v2_routes.py:850–882`, `history_v2_replay.py:123`), workspace fallback (`_resolve_replay_workspace` :831, `_resolve_workspace_dict` :1061). No destructive migration anywhere.
- **H8 invariant:** `experimentRunSurface()` (`studio-experiment-mode.js:1534`) returns `"legacy"` ONLY for an already-active legacy run (view/control compatibility; no enabled Run button); missing Workflow/Version/identity fails closed (:1755); valid new experiments submit ONE definition to `POST /studio/experiment-v2` (:1288). Node units confirm: "12. Run surface selection (H8: legacy creator never mounts)", "16. Missing identity fails closed".
- **Wave A preserved:** `studio-backend{,-api,-capture,-credentials,-deployment,-presets,-runtime,-snapshots,-workspaces}.js` and `studio-model-library.js` all present; H6 ops unit (24 checks incl. O24 readiness rows) and H7 parity unit PASS; `tests.test_studio_backend` 283/283.

## 8. FOCUSED SUITE RESULTS (post-convergence)

| Suite | Result |
|---|---|
| shell-integration + ui-wired + timing integration | 424 passed |
| studio-backend + routes_registered + history-v2 api/repository/modern-experiment | 432 passed |
| phase8 execution-mode resolver + model-library + model-library-routes | 52 passed |
| `studio_history_v2_grid_columns_unit.mjs` | PASS (11 checks) |
| `studio_phase_f4_settings_authority_unit.mjs` | PASS (12 checks) |
| `studio_experiment_v2_unit.mjs` | PASS |
| `studio_experiment_v2_frontend_unit.mjs` | PASS (18 checks incl. H8 surface selection) |
| `studio_backend_operations_unit.mjs` (H6, unregistered) | PASS |
| `studio_model_library_parity_unit.mjs` (H7, unregistered) | PASS |
| Comparison/sidebar guards (inside shell-integration suite) | PASS |

## 9. NEXT-WAVE DEPENDENCY ORDER (determination; nothing implemented)

**C and D can safely run in parallel** (option C of the mandate), both currently unblocked:
- Wave C's blockers were dissolved contractually (C/E sequencing rule preserves the Comparison-owned V1 executor path until Wave E).
- Wave D's prerequisite (A4 fallback closure) completed with H8.

Ownership conflict map:
- Wave C: `execution_runtime.py`, `studio_run_adapter.py`, `studio_workflow_run.py` (incl. the :1556 remnant retiring WITH its surrounding branch), `experiment_runner.py`, `__init__.py` canvas-v1/`/config`/`AVAILABLE_EXECUTION_MODES` regions, `web/studio-settings.js` (Run-mode row, engine selector, reset set), persisted v1→v2 migration + tests.
- Wave D: `web/studio-playground.js` (recent-runs/filmstrip/hydration regions), `web/studio-playground-state.js`, `web/studio-experiment-mode.js` (fallback remainder), legacy Experiment creator UI in `testing-setup.js`/`testing-results.js`, fake-backend mirrors.
- Production sets disjoint. Conditions: (1) `__init__.py` single-writer — D stays consumer/UI-side; any server-side reader-freeze substep sequences after C closes its regions; (2) coordinated (sequential) `tests/run_studio_tests.py` registration edits; (3) D's creator-retirement substep shares `testing-setup.js`/`testing-results.js` with Wave E Comparison parts — region-split or sequence against E.

## 10. FILES MODIFIED BY THIS BATCH

1. `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` — appended "H5 FOLLOW-UP B — POST-WAVE-B CONVERGENCE" (authoritative record; historical sections untouched).
2. `PHASE_H5B_WAVE_B_CONVERGENCE_2026-08-24.md` — this evidence detail.

Production code: NONE. Tests: NONE. No merge repair was required.

Deploy / Modal / GPU / live generation / commit / push / branch / worktree / reset / stash / clean by this batch: **NONE**.
