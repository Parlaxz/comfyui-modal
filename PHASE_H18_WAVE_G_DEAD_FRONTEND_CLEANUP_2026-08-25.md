# PHASE H18 — WAVE G DEAD FRONTEND CLEANUP (2026-08-25)

**Batch type:** H-WAVE G implementation on the CURRENT shared (intentionally dirty) tree. Frontend production code + directly affected structural/frontend tests only. No Python execution modules, no `__init__.py`, no `tests/run_studio_tests.py` edits. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/stash/clean; unrelated dirty-tree work untouched. H19 owns Python/execution residue concurrently.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` incl. Follow-Ups A–E (esp. §20/§21/§25 Wave G, FC-12/FC-19, FD-4/FD-8/FD-25, FE-7), `PHASE_H17_WAVE_F_TEST_CONVERGENCE_AND_CLOSURE_2026-08-25.md`, `PHASE_H14_LEGACY_SETTINGS_COMPARISON_RETIREMENT_2026-08-24.md`, `PHASE_H13_RECENT_RUNS_HISTORY_V2_AND_LEGACY_EXPERIMENT_RETIREMENT_2026-08-24.md`, `PHASE_H10_LEGACY_ENTRYPOINT_REDIRECTS_2026-08-24.md`.

---

## 0. VERDICT

`H18 COMPLETE — WAVE G FRONTEND DELETION LANDED GREEN.`

Nine dead frontend module files deleted after per-candidate re-measurement; `modal-settings.js` pruned from 4,139 → 158 lines (canvas/shared compatibility surface only); `modal-testing.js` draft/preview/experimentId machinery removed with alias map/sidebar/wizard-sync preserved; six caller-proven dead API helpers deleted while the run-history COMPAT_WRITE pair and protected Single seams survive; legacy-only CSS pruned from the shared stylesheet; every affected registered suite updated to pin the retirement instead of dead source. FULL GATE: **Python 1862/1862 · Node-unit 21/21 files · Fake Playwright 211/211 — ALL GREEN** (exact fake count re-run: 211 passed).

---

## 1. REVERSE-IMPORT GRAPH BEFORE DELETION (re-measured at H18 entry)

Method: static import/dynamic-import/script-inclusion sweep over `web/*.js`, `tests/**`, HTML, plus ComfyUI auto-load semantics (every file in the custom node's web dir is fetched/imported by the client; a module without `registerExtension` still executes top-level code — so deletion safety requires zero required top-level side effects, not merely zero ES importers).

| Candidate | Static importers | Dynamic importers | Auto-load side effects | Test-only readers |
|---|---|---|---|---|
| `testing-setup.js` | none live (`studio-legacy.js` LEGACY_MODULES map — itself unreachable) | none | none (no registerExtension) | 5 registered/unregistered suites |
| `testing-profiles.js` | same as above | none | none | 1 suite |
| `testing-results.js` | same as above | none | none | 3 suites |
| `testing-settings.js` | same as above | none | none | 2 suites |
| `testing-ab-slider.js` | none (only `testing-results.js:1129/1255` dynamic imports — themselves dead) | (dead) | none | 2 suites |
| `studio-legacy.js` | ZERO importers (H14 removed the last); `mountLegacyTab` consumer set empty | n/a | none (no extension) | 3 suites |
| `modal-comparison.js` | ZERO importers | none | NONE — H14 deleted `registerExtension`; top level is consts/functions only; no globals, no listeners, no fetch at import | 4 suites/units |
| `testing-api.js` | ZERO importers anywhere (bootstrapLoader import was removed in H14) | none | none (exports only) | 1 negative assertion |
| `testing-setup-adapter.js` | `modal-testing.js` (createDefaultDraft/createPreviewState/normalizeDraft — all feeding only the retired context getters) + deleted `testing-setup.js` | none | none | adapter-boundary source strings |
| `testing-styles.js` | **LIVE: `modal-testing.js`** (`ensureTestingStyles` in open + setup) | none | injects shared token stylesheet (REQUIRED by Studio shell/pages) | token/clarity suites |
| modal-testing context getters (`draft`/`previewState`/`experimentId`/`onDraftChange`/`onRun`) | consumed ONLY by `studio-legacy.js:23–27` | — | — | getter-pattern pins |
| storage keys `comfymodal_setup_draft`, `comfymodal_last_experiment_id` | writer+reader only inside `modal-testing.js` dead machinery | — | — | — |
| Comparison runner LS keys (`comfymodal_comparison_*` ×4) | only inside `modal-comparison.js` | — | — | — |
| dead API helpers (`getBackends`, `getCompareBackends`, `runStudioExperiment`, `listExperiments`, `listRunHistory`, `listUnifiedHistory`, `getModalConfig`) | definition + `studio-backend.js` re-export of the first two; sole other reference = comment `studio-playground.js:1150` | none | none | export-presence pins |

Conclusion: every deletion candidate had zero reachable production callers and zero required surviving side effects. Evidence changed for nothing; no candidate was preserved.

## 2. FILES DELETED (9)

`web/testing-setup.js` · `web/testing-profiles.js` · `web/testing-results.js` · `web/testing-settings.js` · `web/testing-ab-slider.js` · `web/studio-legacy.js` · `web/modal-comparison.js` · `web/testing-api.js` · `web/testing-setup-adapter.js`

`modal-comparison.js` needed no shim: the loader requires nothing of it (registration-free inert module; deleting it only removes it from the client's extension list). No Compatibility surface lost — Comparison read compatibility is server-side.

## 3. MODULES RETAINED + EXACT SURVIVING CALLERS

| Module | Surviving callers |
|---|---|
| `testing-styles.js` (pruned 2,812 → ~330 lines) | `modal-testing.js` (`ensureTestingStyles()` ×2). Retains: design tokens, overlay/close, sidebar panel, fallback launcher, primary/secondary/destructive buttons, input, focus-visible, scrollbar, prefers-reduced-motion. Removed: ALL `testing-{setup,profiles,results,settings,dashboard,history}-*` rules, hero/mode-badge/status-badge/progress-bar/section-card/dashboard/utility-toolbar/deploy-strip/settings-wrapper/history-row/nav/loader classes (zero live consumers each), and the caller-less `removeTestingStyles` export. |
| `studio-backend-api.js` | Live importers unchanged (playground/history/backend/workflows/models modules). Deleted helpers: see §6. Preserved: `updateRunAnnotation`/`saveRunOutput` (COMPAT_WRITE, FD-4), `getStudioRunStatus`/`stopExperiment` (protected seams), presets/workflow/model/v2 families. |
| `studio-backend.js` | shell import of `renderBackend`; re-export pair `getBackends`/`getCompareBackends` deleted. |
| `studio-playground.js` | one stale comment re-pointed (`getBackends` → `getRuntimePresets`); no behavior change. |
| `studio-styles.js` | deleted two dead `.comfymodal-studio-legacy*` blocks (zero JS consumers). |

## 4. MODAL-SETTINGS.JS — BEFORE/AFTER RESPONSIBILITY MAP

| Region (H5C §15 / batch §5) | Before (4,139 lines) | After (158 lines) |
|---|---|---|
| A. Overlay/UI-only | `buildPanel` (:1183–3887), `buildAuthPanel`, deploy banner/log/poll machinery, models/sync lists, workspace section, download-progress UI, style helpers, confirm dialogs | **DELETED** (zero callers; only textual ref was its own def + auth-panel recursion) |
| B. Canvas `_comfyModalEnabled` startup semantics | setup shim | **PRESERVED verbatim** (same precedence; `modal-node.js` readers untouched ×2) |
| C. Output-preference shared wiring | import block + `syncLegacyOutputPrefsOnce` | **PRESERVED**, import trimmed to `syncOutputConfigFromServer` (panel-only preference widgets deleted) |
| D. Required GPU/read-only sync | `loadGpuConfig`/`pickInitialGpu`/`syncLegacyGpuConfigOnce` (+ panel POST path `commitGpuSelection`) | **PRESERVED read-only half**; explicit-change POST path deleted (modern Settings owns the writer since F8) |
| E. Redeploy-restart success banner | setup toast | **PRESERVED** — live writer exists in modern `studio-backend-deployment.js:279` |
| F. Event listeners/status engine (`api.addEventListener` ×6, STATUS/STATUS_STYLE, setStatus/setRuntimeStatus/checkHealth) | top-level side effects mutating overlay-only DOM/state (incl. a latent ReferenceError on `prodSummaryEl`) | **DELETED** (no observable effect once the panel is gone) |
| G. Storage keys | GPU/ENABLED/PRODUCTION | GPU + ENABLED kept; PRODUCTION const deleted (canvas keeps its own in `modal-node.js`) |

## 5. MODAL-TESTING.JS STATE CLEANUP

Deleted: `testing-setup-adapter.js` import; `_draftState`/`_previewState`; `DRAFT_STORAGE_KEY` ("comfymodal_setup_draft") / `EXPERIMENT_ID_KEY` ("comfymodal_last_experiment_id") + all four storage accessors + `_debounce`; studioContext `draft`/`onDraftChange`/`onRun`/`previewState`/`experimentId` (sole consumer was deleted `studio-legacy.js`); unused `TAB_RESULTS`.
Preserved: `ALIAS_PAGE_MAP` (7 aliases), deprecation notices, single `registerSidebarTab` ("comfymodal-testing-suite"), `open_testing_modal`/`close_testing_modal`/diagnostics globals, `comfymodal.open-section` redirect handling, wizard inert/aria-modal sync, focus trap/inert background, `window.__comfyModalUnifiedUI`.

## 6. FRONTEND API-HELPER CALLER CENSUS

| Helper | Callers found | Action |
|---|---|---|
| `getBackends` / `getCompareBackends` | 0 (re-export only + 1 comment) | DELETED both files' copies |
| `runStudioExperiment` | 0 | DELETED |
| `listExperiments` | 0 | DELETED |
| `listRunHistory` | 0 | DELETED |
| `listUnifiedHistory` | 0 (dead since H13 auto-probe removal) | DELETED |
| `getModalConfig` | 0 | DELETED |
| `updateRunAnnotation` / `saveRunOutput` | LIVE (`studio-playground.js:3393/:3490/:3802` compat branch) | KEPT (FD-4 COMPAT_WRITE) |
| `getStudioRunStatus` / `stopExperiment` | LIVE protected seams | KEPT |
| `/studio/presets*`, Workflow, History-V2, model-library, backend-ops helpers | LIVE | KEPT |
| testing-api family (`createExperiment/createFromDraft/runFromDraft/previewDraft/getExperiment/getExperimentHistory/getExperiments/bootstrapLoader/fetchJson/assetUrl`) | 0 importers | DELETED with file |

## 7. STORAGE-KEY CENSUS

| Key | Reader/writer after H18 | Disposition |
|---|---|---|
| `comfymodal_setup_draft`, `comfymodal_last_experiment_id` | none (machinery deleted) | constants/accessors removed; no migration added; user browsers keep their persisted values (non-destructive) |
| `comfymodal_comparison_*` (×4) | none (file deleted) | died with module |
| `comfymodal_gpu` | `modal-settings.js` read-only sync + modern Settings authority | KEPT |
| `comfymodal_enabled` | canvas shim write-once-at-startup + `modal-node.js` readers | KEPT |
| `comfymodal_production` | `modal-node.js` only (canvas Production mode) | KEPT there; modal-settings copy removed |

No global storage clearing; no startup migration.

## 8. TESTS — REMOVED / INVERTED / MIGRATED

Registered suites (all updated in this lane; runner untouched):
- `test_testing_setup_js.py` rewritten → 4-test retirement contract (file absent, no importer, no registry/loader reference, alias lands Playground).
- `test_testing_profiles_js.py` → 3-test contract (+ never-recreated-editor pin).
- `test_testing_results_js.py` → 8 tests: results/ab-slider retirement contract + surviving-owner pins (shell five pages, diagnostics keys) moved here.
- `test_testing_settings_js.py` → 4-test contract (+ overlay-unreachable + open-section survival).
- `test_testing_shell_integration.py`: inverted/updated 14 tests across 10 classes (overlay launcher, hero/status-badge/progress-bar/setup-summary CSS, settings-nav hooks, clarity selectors, studio-modules list, stopLegacyController export, Comparison sidebar guard class rewritten to file-absence + web-wide sweep, FreshLegacyOptions → machinery-absence, getBackends pins → absence, onRun pin, legacy-sections pins → minimal-module pins, comparison syntax check → absence). 201 → 198.
- `test_testing_ui_wired.py`: retired-UI classes replaced with `RetiredTestingModulesContractTests` + absence inversions (ModalSettings sections, clarity markers, StudioLegacyWired, LegacyCleanupWired, backend-helper exports, getter pattern). 171 → 146.
- `test_h14_wave_e_retirement.py`: `test_studio_legacy_fail_closed_preserved_for_wave_g` and `test_comparison_module_is_inert` inverted to absence; comparison-run sweep now covers all of web/; NEW `WaveGDeadFrontendFileContractTests` (§15 dead-file contract: 9 paths absent, zero filename references in code, zero legacy reachability, modal-settings minimal-surface pin). 28 → 30.
- Node unit `studio_phase_f8_gpu_reset_unit.mjs` section 5: loadGpuConfig read-only init pinned; GPU POST sites asserted **0** (was exactly-1).

Unregistered but directly affected (reconciled to keep the tree honest):
- `test_modal_settings_gpu_config.py` rewritten to the surviving authority contract (11 green; was 13 incl. panel pins).
- `test_modal_workspace_ui_ast.py` 24 tests now ALL GREEN — the two long-standing stale pins (`Production plan` label, `output/modal` literal) resolved truthfully by the retirement itself.
- `test_workstream_e_patches.py` Results/A-B UI classes → retirement contract (26 → 11, green).
- `test_task3_progress_annotations.py` listRunHistory pins → absence + COMPAT_WRITE-survival pins (79 → 78; the 5 pre-existing tracker-membership failures are UNCHANGED pre-existing debt, untouched by this lane).
- `tests/studio_legacy_settings_authority_unit.mjs` re-sliced to surviving functions; commitGpuSelection sections → zero-POST-site pins; Comparison reader pin → module-absence pin. Runs green directly.

## 9. COUNT DELTA (exact)

```
Python : 2010 → 1862   (−148)
Node   : 21 files → 21 files (±0)
Fake   : 211 → 211     (±0)
```

Python ledger identity: the seven edited registered suites sum to 393 now; all other registered suites contribute 1469 (unchanged); 1469 + 393 = 1862; pre-H18 the same seven summed to 541 (2010 − 1469) ⇒ Δ = −148 exactly. Per-file current counts: setup_js 4 · profiles_js 3 · results_js 8 · settings_js 4 · shell_integration 198 · ui_wired 146 · h14 30. The −148 is obsolete retired-UI source-string tests legitimately removed, partly offset by new retirement-contract tests (+13 across the four contracts + h14's WaveG class). Fake Playwright unchanged: the retired surfaces never had fake specs. No test was kept solely to preserve 2010.

## 10. GATES

Focused (all green): shell/navigation 198 · ui_wired 146 · h14 retirement 30 · testing_*_js contracts 19 · gpu_config 11 · workspace_ast 24 · workstream_e 11 · task3 78 (5 pre-existing tracker failures only) · node units F8 + legacy-settings-authority direct PASS · `node --check` clean on all 43 web files.

FULL GATE `python tests/run_studio_tests.py --fake`:
```
python             run=1862  fail=0  error=0  skip=0
node-unit          run=21    fail=0  error=0  skip=0
fake-playwright    PASS      (wrapper aggregate)
ALL STUDIO LANES GREEN
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed (4.4m) / 211
```
(Run twice end-to-end on this lane's final tree; second run after the last cosmetic export removal.)

## 11. PRODUCT-INVARIANT PROTECTION (§13/§14 verified)

Top nav exactly Playground | History | Workflows | Backend | Settings (`studio-shell.js` PAGES). H10 aliases intact (dashboard→backend, setup→playground+Experiment context, profiles→playground+deprecation, results/history→history, settings→settings). Single sidebar registration preserved. `open_testing_modal` compatibility + `comfymodal.open-section` modern redirect preserved. Canvas `/prompt` interception, Local/Cloud pass-through gate, Production mode (modal-node), output-options chain, run-history COMPAT_WRITE pair, protected Single poll/Cancel seams — all present and pinned green. Source/runtime sweep proves NO product code can mount/open legacy Setup/Profiles/Results/Settings, old Comparison UI, old A/B slider, or the standalone overlay via sidebar, aliases, globals, context menu, dynamic import, or lazy loader. No user-facing feature disappeared beyond the already-retired Wave-E surfaces.

## 12. REMAINING FRONTEND G DEBT (not fixed by this lane)

- `tests/test_image_packaging_refactor.py` docstring still names `web/modal-comparison.js` in the runtime-mount-ignore context (assertion remains true; docstring-only staleness).
- `test_task3_progress_annotations.py` tracker-membership ×5 remain failing (pre-existing, Python-side progress-tracker re-pointing — H19/G L-TST debt).
- Historical F8/workflow reverse-order isolation artifact (unchanged).
- Unregistered H6/H7/H12 suites + `studio_legacy_settings_authority_unit.mjs` registration decisions remain G-owned (this lane did not touch the runner).
- `studio-styles.js` retains historical "Override testing-styles" comments (compatibility rationale, kept per §11).

## 13. FILES MODIFIED / DELETED BY THIS LANE ONLY

Deleted (9): `web/testing-setup.js`, `web/testing-profiles.js`, `web/testing-results.js`, `web/testing-settings.js`, `web/testing-ab-slider.js`, `web/studio-legacy.js`, `web/modal-comparison.js`, `web/testing-api.js`, `web/testing-setup-adapter.js`.

Modified production (6): `web/modal-settings.js` (rewritten to 158-line compatibility module), `web/modal-testing.js` (context-machinery removal), `web/testing-styles.js` (pruned to live tokens/components), `web/studio-backend-api.js` (7 dead helpers removed), `web/studio-backend.js` (dead re-exports removed), `web/studio-playground.js` (one stale comment), `web/studio-styles.js` (two dead CSS blocks).

Modified tests (12): `tests/test_testing_setup_js.py`, `tests/test_testing_profiles_js.py`, `tests/test_testing_results_js.py`, `tests/test_testing_settings_js.py`, `tests/test_testing_shell_integration.py`, `tests/test_testing_ui_wired.py`, `tests/test_h14_wave_e_retirement.py`, `tests/studio_phase_f8_gpu_reset_unit.mjs`, `tests/test_modal_settings_gpu_config.py`, `tests/test_modal_workspace_ui_ast.py`, `tests/test_workstream_e_patches.py`, `tests/test_task3_progress_annotations.py`, `tests/studio_legacy_settings_authority_unit.mjs`.

NOT touched: `__init__.py`, all Python execution modules, server routes, `tests/run_studio_tests.py`, fake backend/specs, stored data.

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
