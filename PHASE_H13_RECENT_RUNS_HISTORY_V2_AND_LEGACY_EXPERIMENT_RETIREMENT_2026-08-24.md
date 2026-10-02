# PHASE H13 — PLAYGROUND RECENT-RUNS HISTORY-V2 MIGRATION & LEGACY EXPERIMENT CONSUMER RETIREMENT (2026-08-24)

**Batch type:** H-WAVE D implementation (H5 §23/§25 Wave D; H8 §7 deferred dependency). Consumer/UI-side only. No server route or backend edits. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` incl. Follow-Ups A/B, `PHASE_H3_REFERENCE_INTEGRITY_HISTORICAL_COMPATIBILITY_AUDIT_2026-08-23.md`, `PHASE_H8_EXPERIMENT_V2_FALLBACK_CLOSURE_2026-08-23.md`, `PHASE_H5B_WAVE_B_CONVERGENCE_2026-08-24.md`.
**Concurrency:** H12 (Wave C) landed concurrently in the shared tree. Zero file overlap; two mid-gate node-unit flakes (`f4`/`f8`) were H12 editing `web/studio-settings.js`/`/config` regions during the run — both pass standalone and in the final converged gate.

---

## 0. VERDICT

`H13 COMPLETE — Playground recent-runs is History-V2-backed with zero legacy-feed hydration; the modern legacy Experiment renderer/poller/reopen path is fully retired; legacy Experiment NEW-write UI is gone from Setup/Results while Comparison survives intact for Wave E. Full gate green on the converged tree.`

**Final gate (converged tree, this lane):**

```
python tests/run_studio_tests.py --fake
  python             run=1945  fail=0  error=0  skip=0
  node-unit          run=21    fail=0  error=0  skip=0
  fake-playwright    PASS   (exact count via direct config run: 211 passed / 211)
ALL STUDIO LANES GREEN
```

---

## 1. RECENT-RUNS CALL GRAPH — BEFORE vs AFTER

### BEFORE (measured pre-edit)
`refreshRecentRuns(apiBase)` (`studio-playground.js:392`) fetched THREE feeds in parallel:
1. `GET /comfymodal/run-history?limit=50` → filtered to Studio runs → `normalizeStudioRun` → completed+image items;
2. `GET /comfymodal/history?page=1&page_size=50` (unified platform feed) → concatenated into (1);
3. `GET /comfymodal/experiments` → filtered to "Studio Experiment:*" aggregates → hand-built EXP items.
Merge → sort newest-first by `completedAt||startedAt` → dedupe by `experimentId||id`. Filmstrip click: Single → canvas select; **EXP → `loadExperimentIntoPlayground` → `GET /experiments/{id}` → mounted the legacy Experiment Grid Viewport** (~1350 lines: matrix/linear/fallback grids, cell detail overlay, arrow navigation, progress bars). Selected-run favorite/note wrote `PATCH /run-history/{id}/annotations`; Save output used `POST /run-history/{id}/save`.

### AFTER
`refreshRecentRuns(apiBase)` = `createHistoryRepository({mode:"v2", apiBase}).listFeed({limit:50, sort:"newest"})` — the SAME canonical History V2 authority the History page reads (`GET /history-v2/feed?limit=50&kind=mixed&order=newest`). Normalized records map to filmstrip entries (generations: completed/completed_with_failures WITH image only; experiments: all statuses, EXP badge from `kind==="experiment"` — History projection truth, never route origin). Deterministic pin: client re-sort newest-first (identical comparator) then id-dedupe, first occurrence wins. Repository promise cached per apiBase.

## 2. HISTORY V2 ROUTE AUTHORITY USED

Exactly one new read: `GET /history-v2/feed` (mixed kinds, newest order, limit 50) through the existing `history-v2-repository.js` v2 adapter — no second feed route, no Playground-only index, no localStorage authority, no client-side reconstruction. Annotations/save migrated to durable truth: favorite/note → `POST /history-v2/generations/{id}/favorite|note` (repo `setFavorite/setNote`); Save output → `POST /history-v2/assets/{asset_id}/export` (F9/F10 configured-folder Export, gated on `featuredOutput.previewAssetId/originalAssetId` and `exportState !== "exported"`). Legacy annotation/save writers remain ONLY for stale non-History-backed persisted selections (below).

## 3. MIXED SINGLE + EXPERIMENT PROJECTION & OLD-RECORD VISIBILITY

Filmstrip items carry `_historyKind` ("generation"|"experiment") from History V2 record-kind truth. Old-record audit (§5): the History V2 feed already contains migrated legacy Singles (copied provenance, honest `replay_capable:false`/irreproducible), mirrored legacy Experiments (terminal cells), and modern records — proven by the new `history_v2_wave_d` fake seed (migrated legacy single WITH image appears in filmstrip; imageless migrated single stays viewable via History search/detail; mirrored legacy experiment shows EXP badge AND opens History detail) plus the default V2 seed. `/run-history`//history`//experiments` are NOT kept as hidden fallbacks anywhere.

## 4. CLICK / OPEN BEHAVIOR

- **Single**: unchanged UX — sets `lastRunOutput`/`_selectedRun`, canvas displays the durable thumb/preview URL (`/comfymodal/history-v2/assets/...`). No Workflow/Preset object required (copied provenance only; no live lookups added).
- **Experiment**: NEW seam `requestHistoryRecordFocus(id, "experiment")` (`studio-history-v2.js`, one-shot in-memory module flag — no URL routing) + `context.setPage("history")`; the next History mount consumes the focus and opens `renderExperimentDetail` (`[data-testid="history-v2-experiment-page"]`), falling back to the feed page if the record is gone. `loadExperimentIntoPlayground` is DELETED — the legacy grid can never reopen.

## 5. LEGACY RENDERER / POLLER RETIREMENT (§9)

With reopen gone, the caller set of the active-legacy surface reached zero and was retired cleanly:
- `studio-experiment-mode.js`: `experimentRunSurface()` now returns `"modern"` unconditionally; `_hasActiveLegacyRunState`/`LEGACY_ACTIVE_RUN_STATUSES` deleted; `_mountExperimentRunSurface` always mounts the modern section (watcher retained solely for gating resync); `renderExperimentRunButton`, `buildExperimentClickHandler`, `executeExperimentRun` and the `runStudioExperiment`/`stopExperiment` imports REMOVED. H8 semantics untouched: missing Workflow/Version fails closed with reasons; valid identity submits exactly one `POST /studio/experiment-v2`; single-flight guard intact (unit sections 12/16/17/18 re-pointed and green).
- `studio-playground.js`: Experiment Grid Viewport region (~1350 lines incl. exported `_buildCellOutputMap`) and the dead polling cascade removed; `_startPolling` keeps ONLY the canonical controller path (`applySnapshot`) that feeds live scheduled-single-run progress; single-run Cancel keeps `POST /experiments/{id}/stop-now` (live single-run control, hidden in experiment mode).

## 6. STALE LOCAL STATE (§10) — NO CLEANUP NEEDED

Inventory: `comfymodal.studio.experiment.active.v1` holds MODERN v2 ids only; a stale/ghost value triggers at most a bounded modern status poll (404 handled silently) and never creates/converts anything (new-spec scenario 17). No path imports legacy experiment ids into Playground state anymore. Draft namespaces (`comfymodal.studio.experiment.draft.v1`, playground draft/results namespaces) are byte-identical after navigation (scenario 18). No destructive clearing performed anywhere.

## 7. TESTING-SURFACE RETIREMENT + WAVE-E CLASSIFICATION (§12–§14)

**`testing-setup.js`** — RETIRED: `doCompile` (`POST /experiments/compile`), `doRun` (create+start via testing-api), payload builders, auto-preview compile loop, Compile/Run buttons → truthful notice `[data-testid="legacy-experiment-creator-retired"]`. Classification: `workflowsSection` profile CRUD/detect-slots/validate/duplicate/delete + stack/LoRA editors + triple pickers = **COMPARISON_OWNED** (untouched); `generationTypeSection`/`whatChangesSection`/`testValuesSection`/`validateSpec` = **STILL_HAS_NONCOMPARISON_FUNCTION** (inert shared form infrastructure, no execution actions); creator paths = **RETIRED**.

**`testing-results.js`** — RETIRED: `ROUTINE_CONTROLS`/`DANGER_CONTROLS`/`CONTROL_VARIANT`/`runControl` (pause/resume/stop-after-current/stop-now/run-missing POSTs) → notice `[data-testid="legacy-experiment-controls-retired"]`; the module now issues ZERO POSTs. Classification: picker/`GET /experiments`+snapshot+events reads, summary/progress/grid/cell rendering = **READ_ONLY_COMPATIBILITY**; `addToSelection` + `testing-selection-changed` contract, `renderComparison`, A/B slider wiring (`ab_slider_render`/`ab_slider_open_fullscreen`), Swap/Fullscreen delegation = **COMPARISON_OWNED** (byte-untouched). After Wave E removes Comparison: results residual = pure READ_ONLY_COMPATIBILITY → **DEAD_AFTER_WAVE_E**; setup residual = Comparison-owned CRUD (Wave E fate per R1) + inert form sections (**DEAD_AFTER_WAVE_E**). The Settings Legacy group itself still exists (Wave E owns removal).

## 8. ZERO-LEGACY-NETWORK PROOF (§21/§22)

New `tests/browser/fake/studio-fake-recent-runs-history-v2.spec.mjs` (12 tests) proves on a normally mounted Playground: recent Single + modern Experiment appear from History V2; newest-first ordering; unique rows; Single click renders; EXP click opens History detail with zero grid viewport; zero `GET /run-history`, zero old `GET /history`, zero `GET /experiments` hydration; zero `POST /studio/experiment` (page network + engine `experimentCreateRequests` cross-check); zero `/experiments/{id}` polls and zero stop-now during navigation/interaction; valid modern run still posts exactly one `/studio/experiment-v2`; stale ghost active-state creates nothing; draft/results namespaces byte-identical; favorite/note write exactly one `/history-v2/generations/{id}/favorite|note` each and zero `run-history/annotations`. Scope note: the scheduled-single-run snapshot poll (`GET /experiments/{single_run_id}`) and single-run Cancel stop-now are LIVE single-run acceptance/control behavior (H12-owned execution semantics, protected by scenario 20 + workflow-run specs), not legacy-hydration calls; they are absent unless a run is submitted.

Fake-backend support (additive, H13-owned regions): preset-path `POST /studio/run` now mirrors into `session.historyV2` (id === experiment_id, running→completed/failed/canceled with outputs at terminal) matching production's writer behavior; new `wave_d` V2 seed; obsolete `experiment-grid` visual baseline replaced by `playground-filmstrip.png`.

## 9. LEGACY ROUTE CALLER TABLE (§15) — no server edits

| Route | Frontend callers after H13 | Modern? | Legacy-only? | Wave F/G candidate |
|---|---|---|---|---|
| GET /run-history(?limit) | NONE (helper `listRunHistory` + `testing-api.getExperimentHistory` zero callers; bridge repo mode programmatic-only) | no | yes | YES |
| GET /run-history/{id}(/logs,/timing) | none modern (bridge mode only) | no | yes | YES |
| PATCH /run-history/{id}/annotations | studio-playground compat branch for stale persisted results.v1 entries ONLY (shrinking population); frozen-for-bridge | compat | mostly | after population ages out |
| POST /run-history/{id}/save | same compat branch only | compat | mostly | with above |
| GET /history (unified) | ZERO (auto-probe already dead code) | no | yes | YES |
| GET /experiments | testing-results picker ONLY (Settings Legacy surface until Wave E) | no | yes | with Wave E |
| GET /experiments/{id} | studio-playground single-run scheduler snapshot poll (LIVE single-run path) + testing-results reader | single-run path = live | reader=legacy | reader with Wave E; poll follows H12 execution consolidation |
| GET /experiments/{id}/events | testing-results only | no | yes | with Wave E |
| POST /experiments/{id}/stop-now | studio-playground single-run Cancel ONLY (live control) | single-run control | — | follows H12/V1 retirement |
| POST /experiments/{id}/pause|resume|stop-after-current|run-missing | ZERO (removed) | no | yes | YES |
| POST /experiments/compile | ZERO (removed) | no | yes | YES |
| POST /experiments + /{id}/start | ZERO frontend (helpers `createExperiment/createFromDraft/runFromDraft` retained, zero callers) | no | yes | YES (dead helpers, Wave G) |
| POST /studio/experiment | ZERO (helper `runStudioExperiment` retained, zero importers) | no | yes | YES (dead helper, Wave G) |
| POST /studio/experiment-v2 | modern D5 section (H8 intact) | YES | — | keep |

## 10. TEST DELTAS vs BASELINE (Python 1941 · Node 21 · Fake 199)

- **Python 1941 → 1945 (+4), 0 fail.** Mixed converged-tree delta: H13 structural reconciliation (test_studio_backend −14 net methods but +History-V2 authority pins/subTest shifts; testing_setup_js 5 inverted 1:1; testing_results_js +1; ui_wired −27 net; shell_integration −14 net; progress_tracker −1) is net-negative-to-flat, so the +4 rides primarily on concurrently-landed H12 Wave-C test rewrites (`test_phase8_execution_mode.py` +40 net lines-of-collection, `test_modal_settings_gpu_config.py` +113) measured together in the same gate. Per-file split between concurrent writers is not recoverable post-hoc (no commits exist); every H13-touched file is individually green (776 passed + 59 subtests across the five structural files).
- **Node 21/21** unchanged; `studio_experiment_v2_frontend_unit.mjs` updated in place (18 sections PASS).
- **Fake 199 → 211 (+12)**: exactly the new recent-runs spec (12 tests). Conversions were count-neutral (gating G5, workflow-run #28, experiments spec 3 tests, visual grid→filmstrip 1:1, playground d/f assertion updates).
- Out-of-gate pre-existing failures (`test_task3_progress_annotations` tracker-membership ×5, `test_modal_workspace_ui_ast` stale copy/literal pins ×2) remain Class B/D per H5B §6 — none reference any symbol this lane removed.

## 11. FILES MODIFIED BY THIS LANE

Production: `web/studio-history-v2.js` (focus seam), `web/studio-playground.js` (hydration/filmstrip/annotations/retirement), `web/studio-experiment-mode.js` (legacy surface retirement), `web/testing-setup.js`, `web/testing-results.js` (creator/execution-control retirement).
Fakes/specs: `fake-backend.mjs`, `scenarios.mjs`, NEW `studio-fake-recent-runs-history-v2.spec.mjs`, `studio-fake-{experiments,experiment-gating,workflow-run,visual,playground,history}.spec.mjs` (+ visual snapshots).
Tests: `test_studio_backend.py`, `test_testing_setup_js.py`, `test_testing_results_js.py`, `test_testing_ui_wired.py`, `test_testing_shell_integration.py`, `test_studio_progress_tracker.py`, `studio_experiment_v2_frontend_unit.mjs`.
NOT touched: `__init__.py`, `execution_runtime.py`, `studio_run_adapter.py`, `studio_workflow_run.py`, `experiment_runner.py`, `/config`, `web/studio-settings.js`, execution-engine UI, V1/shadow runtime, `tests/run_studio_tests.py`, all Comparison-owned modules (`modal-comparison.js`, `testing-profiles.js`, `testing-ab-slider.js`, `testing-api.js`, `testing-setup-adapter.js`).

## 12. EXACT WAVE-E IMPLICATIONS

1. Results tab residual = READ_ONLY_COMPATIBILITY + Comparison selection/slider; Setup tab residual = Comparison profile CRUD + inert form sections — Wave E deletes both groups' Comparison parts per R1 and the remainder becomes dead.
2. `GET /experiments` list + snapshot/events readers lose their last consumer when the Settings Legacy group goes → route-freeze candidates then.
3. `modal-testing.js` lazy-tab mounting of setup/results and the ALIAS "results→history" redirect stay as-is until Wave E (not this lane's files).
4. Dead helpers now carrying zero callers — `runStudioExperiment`, `listRunHistory`, `listExperiments`, `testing-api.createExperiment/createFromDraft/runFromDraft/previewDraft/getExperiment/getExperimentHistory` — are Wave-G deletions (left in place per "do not delete helpers while legacy surfaces may consume"; verified zero consumers).
5. Shrinking compat populations (PATCH annotations / legacy save for stale persisted selections) can be revisited after results.v1 entries age out or a one-time migration decision lands.
6. The single-run scheduler poll (`GET /experiments/{id}`) and single-run Cancel stop-now remain execution-path seams owned by H12/Wave-C follow-through; when single runs become fully V2-native these become the final `/experiments/*` modern departures.

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
