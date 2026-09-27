# PHASE H9 — DEAD HISTORY SURFACE & LEGACY DASHBOARD/HISTORY TAB RETIREMENT (2026-08-24)

**Batch type:** H-WAVE B implementation (H5 §20 safe dead-surface retirement + §25 Wave B). No deploy, no Modal, no GPU, no live generation, no commit/push/branch/worktree/reset. The working tree was intentionally dirty (H10/H11 running concurrently in the same tree).
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §20 (Wave-B deletion set), §18 (route/data freeze), §22 (redirects — H10-owned, untouched here), §28 invariants 13/17/18; H1 L11/S1 findings; H3 §10/§14 do-not-delete list; H4 §1.3 orphan finding; H8 closure report.

---

## 0. VERDICT

`H9 COMPLETE — orphaned History V1 frontend deleted, Legacy Dashboard and Legacy History tabs retired, loaders/list updated fail-closed, legacy routes/data untouched, History V2 unchanged. Full gate green.`

---

## 1. REVERSE-IMPORT PROOF (re-measured this lane, not inherited from H1)

Fresh sweep over all production modules (`web/*.js`, production Python) before deletion:

| Instrument | Result |
|---|---|
| Static imports of `./studio-history.js` across `web/*.js` | **0** |
| Dynamic `import("./studio-history.js")` across `web/*.js` | **0** |
| Importers of its exports (`renderHistory`, `formatPageMetadata`, `resolveTotalCount`, `isRunCompleted`, `isRunFailed`) outside the file itself | **0** (`renderHistory` defined only at `studio-history.js:480`; never imported) |
| Mounted runtime callers | **0** — shell mounts `renderHistoryV2` (`studio-shell.js:13,22`); `open_testing_modal("history")` maps to page `"history"` = V2 (`modal-testing.js` pageMap), never to the module |
| Production Python references | **0** |
| Non-production references found | one stale doc comment in `studio-run-normalizer.js:5` (updated); historical docs/network-trace logs (not code) |

No new production consumer appeared since H1. Deletion proceeded.

## 2. PURE HELPER TRIAGE

Exports inventoried in the dead file: `resolveTotalCount`, `formatPageMetadata`, `renderHistory`, `isRunCompleted/isRunFailed` re-exports. Note: `buildWaterfallLines` was **already modern-owned** in `studio-run-normalizer.js` (the dead file merely imported it); its tests already target the normalizer and were kept verbatim.

| Helper | Class | Action |
|---|---|---|
| `formatPageMetadata(offset,limit,total)` | **C — DEAD** | Zero production consumers; no modern equivalent (History V2 uses cursor pagination + result-count line, no "Page X/Y" UI). Deleted with file; `FormatPageMetadataRED` (5 tests) deleted. |
| `resolveTotalCount(data,runs)` | **C — DEAD** | Zero production consumers; V2 repository derives `hasMore`/cursor, not list totals. Deleted with file; `TotalCountWiringRED` (4 tests) deleted. |
| `renderHistory` + internal render helpers | **C — DEAD** | Retired V1 UI. `TotalCountBeforeFilterBarWiringRED` (pins dead internal wiring order) deleted. |
| `isRunCompleted`/`isRunFailed` | **C — DEAD** | Trivial status aliases, zero external importers. Deleted with file. |
| favorite-star-is-a-button invariant | **B — moved** | `KeyboardA11yButtonTests.test_history_favorite_star_is_button` re-pointed from the dead file to `studio-history-v2.js renderFavoriteStar` (same invariant: semantic `<button>` + `aria-pressed`; V2 star verified to carry both). |
| Playground↔History favorite/note parity | **B — moved** | `AnnotationDataParityTests` rewritten: dead-file half dropped; assertion now pins Playground + `studio-history-v2.js` for favorite/note presence. |

No helper was preserved solely to keep an obsolete test green. No fake dead file or commented-out source was created.

## 3. DELETED PRODUCTION MODULES

- `web/studio-history.js` (1704 lines, orphaned History V1 page)
- `web/testing-dashboard.js` (Legacy Dashboard launcher tab)
- `web/testing-history.js` (Legacy History read-only tab)

Not replaced by any compatibility module. Modern History remains `studio-history-v2.js` + `-detail/-experiment` + `history-v2-*` support modules, unchanged.

## 4. LOADER / LIST REGISTRATION UPDATES

- `web/studio-legacy.js` — `LEGACY_MODULES` reduced to `setup/profiles/results/settings`; unknown tabs (incl. `dashboard`/`history`) hit the pre-existing fail-closed path ("Unknown legacy tab"). No dynamic import of a deleted module remains.
- `web/modal-testing.js` — `TAB_MODULES` loader map reduced to the four surviving legacy tabs; unused `TAB_DASHBOARD`/`TAB_HISTORY` constants removed. The `open_testing_modal` pageMap alias region was **NOT touched** (H10-owned per batch §9).
- `web/studio-settings.js` — Settings ▸ Advanced ▸ Legacy list reduced to exactly Legacy Setup / Profiles / Results / Settings (+ "Open Legacy Settings" button untouched); `data-search` string updated. Testids `settings-legacy-dashboard` / `settings-legacy-history` no longer exist.
- `web/studio-run-normalizer.js` — header caller comment updated (dead caller removed from the list).

## 5. TEST MIGRATION / DELETION LEDGER (this lane only)

In-gate Python structural tests pruned where their ONLY purpose was pinning retired surfaces:

| File | Removed | Rationale |
|---|---|---|
| `tests/test_studio_timing_integration.py` | −10 | `FormatPageMetadataRED` (5), `TotalCountWiringRED` (4), `TotalCountBeforeFilterBarWiringRED` (1): bind to dead-file exports/internal wiring. Stale "Test 21" section comment corrected to name the normalizer. All waterfall/normalizer tests targeting `studio-run-normalizer.js` kept verbatim. |
| `tests/test_studio_backend.py` | −15 | Dead-file-only classes/tests: `HistoryFlatStudioMetaTests` (2), `HistorySafeRenderingTests` dead halves (2; V2 el()-factory test kept), `HistoryGalleryTests` dead halves (6; both V2 tests kept), `SharedNormalizerConsumptionTests` history half (1; playground test kept, mixed test rewritten playground-only), `NullishChecksTests` history member (1), `HistoryPresetLabelTests` dead members (2; filmstrip carousel test kept against `studio-playground.js`), `HistoryTypeFilterStudioRunTests` (1). `test_settings_legacy_section` rewritten to pin the post-H9 four-entry list with negative assertions on the two retired entries. |
| `tests/test_testing_shell_integration.py` | −24 net | `ModuleReferenceTests`: two dashboard/history reference assertions replaced by one negative assertion (retired modules must NOT be referenced). Whole classes deleted: `DashboardHierarchyTests` (4), `HistoryRowLayoutTests` (7), `ProgressiveClarityDashboardTests` (2), `ProgressiveClarityHistoryTests` (2), `StudioHistorySafetyTests` (6). `StudioLegacyContractTests`: two dead-file history tests deleted; six-tab list assertion rewritten to the four surviving tabs + negative assertions. `test_studio_modules_exist` list updated (`studio-history.js` → `studio-history-v2.js`). |
| `tests/test_testing_ui_wired.py` | −25 net | `VisualRedesignTests` dashboard/history members (5), `ProgressiveClarityDashboardUiWiredTests` (3), `ProgressiveClarityHistoryUiWiredTests` (2), `StudioPresetExecutionUiWiredTests` five dead-file members (5), `StudioBackendWiredTests` three dead-file members (3), `HistoryPreviewDialogTests` six dead-file members (6; all five V2-detail overlay tests kept), `ResponsiveTests.test_history_filters_adapt` (1). Favorite-star test MOVED to V2 (§2). `test_studio_legacy_references_old_tab_modules` rewritten to the four surviving modules + negative assertions. |

Out-of-gate files also reconciled (not part of gate counts):
- `tests/test_task3_progress_annotations.py` −25 net: dead-file-only classes `HistoryPaginationTests` (3), `HistoryFilterTests` (9), `HistorySortTests` (7), `HistoryGroupingToggleTests` (2), `HistoryFavoriteNoteTests` (4) deleted; `AnnotationDataParityTests` re-added in moved-to-V2 form (+1).
- `tests/test_modal_workspace_ui_ast.py` net 0: `StudioHistoryNormalizerTests.test_history_imports_normalize_studio_run` rewritten to pin `studio-history-v2.js`'s normalizer import.
- Node units: `tests/studio_history_v2_grid_columns_unit.mjs` — dead-source read + "legacy reader must remain" assertion removed (modern sections 1–8/10–11 untouched); `tests/studio_phase_f4_settings_authority_unit.mjs` — unused `readWeb("studio-history.js")` read removed (no assertion consumed it).

## 6. LEGACY ROUTE / DATA PRESERVATION PROOF

Untouched and verified present after edits:

- `GET /comfymodal/run-history` — `__init__.py:6953`
- `GET /comfymodal/run-history/{run_id}` (+ `/logs`, `/timing`) — `__init__.py:6996–7013`
- `PATCH /comfymodal/run-history/{run_id}/annotations` — `__init__.py:7023`
- `POST /comfymodal/run-history/{run_id}/save` — `__init__.py:7084`
- `GET /comfymodal/history` — `__init__.py:7797`
- `GET /comfymodal/experiments` family — routes registered (startup banner)
- `.run_history` store + readers — `run_history.py` (`run_history_root()` → `.run_history/<run_id>`) unmodified
- `legacy_mapping` table + dormant `LegacyMigrationSeam` — `history_v2_migration.py` unmodified
- No destructive migration of any store was performed; no fake-backend route mirrors were touched (no production route changed).

## 7. HISTORY V2 REGRESSION EVIDENCE

- `studio-shell.js` still mounts `renderHistoryV2` as the sole History page.
- Focused greens: `tests.test_studio_backend` 283/283, `tests.test_studio_timing_integration` 54/54, `tests.test_testing_shell_integration` 200/200, `tests.test_testing_ui_wired` 170/170, `studio_history_v2_grid_columns_unit.mjs` PASS, `studio_phase_f4_settings_authority_unit.mjs` PASS, plus the full History-V2 API/migration/repository/replay/export suites inside the gate.
- Fake Playwright lane (includes `studio-fake-history*.spec.mjs`, experiment/history-v2 specs): PASS.
- No History V2 source file was modified by this lane.

## 8. FULL GATE

```
python tests/run_studio_tests.py --fake
  python             run=1941  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (npm wrapper run=1 fail=0)
ALL STUDIO LANES GREEN
```

Delta vs stated baseline (Python 1991 → 1941, Node 21 → 21, Fake PASS → PASS):

- This lane's in-gate deletions, itemized in §5: **−74 Python assertions** (timing −10, backend −15, shell-integration −24, ui-wired −25). Node file count unchanged (both edited .mjs files remain registered).
- Net observed delta is −50; the residual **+24** comes from concurrently landing H10/H11 work in the shared shared tree (their added/rewritten assertions are outside this lane's ownership and were not modified here).
- Two out-of-gate failures exist in the dirty shared tree and pre-date this lane's edits (verified: the relevant production files were already modified by concurrent lanes and contain none of the asserted content): `tests.test_task3_progress_annotations` tracker-membership tests ×5 (assert `getSharedTracker` wiring absent from the concurrently-modified `web/studio-playground.js`) and `tests.test_modal_workspace_ui_ast.ModalProductionUiAstTests` ×2 (assert copy in the concurrently-modified `web/modal-settings.js`). Both files are outside `STUDIO_PY_MODULES`; neither failure involves any file this lane touched, and per batch rules H10/H11 files were left alone.

## 9. FILES DELETED / MODIFIED BY THIS LANE

Deleted (production): `web/studio-history.js`, `web/testing-dashboard.js`, `web/testing-history.js`.

Modified (production): `web/studio-legacy.js`, `web/modal-testing.js` (loader-map regions only; pageMap aliases untouched), `web/studio-settings.js` (Legacy-list region only), `web/studio-run-normalizer.js` (header comment only).

Modified (tests): `tests/test_studio_timing_integration.py`, `tests/test_studio_backend.py`, `tests/test_testing_shell_integration.py`, `tests/test_testing_ui_wired.py`, `tests/test_task3_progress_annotations.py`, `tests/test_modal_workspace_ui_ast.py`, `tests/studio_history_v2_grid_columns_unit.mjs`, `tests/studio_phase_f4_settings_authority_unit.mjs`.

Created: this document.

## 10. PASS CRITERIA CHECK

- Orphaned History V1 frontend gone — YES (§1/§3)
- No runtime reference to it remains — YES (§1, §4; only explanatory comments in tests remain)
- Legacy Dashboard tab gone — YES (module deleted; loader entry, TAB_MODULES entry, Settings entry, and pinning tests removed)
- Legacy History tab gone — YES (same treatment)
- Setup/Profiles/Results/Settings legacy tabs remain — YES (loader maps + Settings list + their structural tests intact)
- Modern History V2 unchanged — YES (zero V2 source edits; all V2 specs green)
- Legacy routes/data untouched — YES (§6)
- No historical migration performed — YES
- Tests pass — YES (full gate green; out-of-gate concurrent-lane failures documented in §8)

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
