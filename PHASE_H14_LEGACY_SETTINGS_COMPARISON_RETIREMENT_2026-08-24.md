# PHASE H14 — LEGACY SETTINGS & COMPARISON PRODUCT RETIREMENT (WAVE E) (2026-08-24)

**Batch type:** H-Wave E implementation on the CURRENT shared (intentionally dirty) tree. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset/stash/clean, no unrelated dirty-tree work discarded. Wave F/G/Phase-I NOT started.
**Authority:** `PHASE_H5C_WAVES_CD_CONVERGENCE_WAVE_E_FREEZE_2026-08-24.md` (final scope authority; §8 route rule, §9 EXECUTION_RETIRE disposition, §13–§17 retirement sets, §15 modal-settings split, §20 exit contract) + `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` incl. Follow-Ups A/B/C + H12 + H13 + H5B.

---

## 0. VERDICT

`H14 COMPLETE — WAVE E LANED GREEN. Settings Legacy group gone; standalone legacy overlay retired with its globals; Setup/Profiles/Results/Settings legacy tabs unmountable; Comparison Profiles/Runner UI, overlays, canvas menu and A/B slider unreachable; POST /comparison/run returns a bounded truthful 410 COMPARISON_RETIRED response with zero executor/manifest/history/profile mutation; stored Comparison data byte-identical; READ_COMPAT intact; run_prompt_stream preserved (V2 transport + warmup); warmup untouched; transitional Single GET /experiments/{id} + stop-now preserved; canvas Local/Cloud/Production/output wiring preserved; modern execution V2-only. FULL GATE: Python 1974 · Node-unit 21 files · Fake Playwright 211 — ALL GREEN.`

---

## 1. BEFORE-STATE CALLER MAP (re-measured from current source at H14 entry)

| Target | Callers before H14 (current tree, re-measured) |
|---|---|
| Settings ▸ Advanced ▸ Legacy group | `studio-settings.js:590–632` only UI surface (opener `settings-legacy-open` + 4 entries); rendered via `renderLegacyView` (`:1058`) ← `activeLegacyTab` branch (`:168`) |
| `mountLegacyTab` | def `studio-legacy.js:32`; imported by `modal-testing.js:8` → shell context `:353`; forwarded by `studio-shell.js:93`; consumed by `studio-settings.js:1078` |
| `LEGACY_MODULES` | `studio-legacy.js:37–42` (setup/profiles/results/settings; unknown-tab fail-closed) |
| `TAB_MODULES` / `mountLazyTab` | `modal-testing.js:435–500` — ZERO callers (dead machinery carried from H5B/H5C) |
| `window.open_comfymodal_settings` | def `modal-settings.js:4107`; callers `testing-settings.js:91/110/174` ONLY (+ comment `:4197`) — zero external callers, matching H5C §16 |
| `window.mountSettingsPanel` | def `modal-settings.js:4095`; sole consumer `testing-settings.js:65` |
| `testing-setup.js` / `-profiles.js` / `-results.js` / `-settings.js` | imported ONLY by `studio-legacy.js` + dead `TAB_MODULES`; `-ab-slider.js` dynamically imported only by `testing-results.js:1129/1255` |
| Comparison overlay globals | defined+consumed inside `modal-comparison.js` only (`:1567/:1578/:1643/:1649`) |
| Comparison canvas menu | `_initContextMenu` (`:1425`) wraps `app.canvas.getNodeMenuOptions`; invoked once from extension `setup()` (`:1659`) |
| `/comparison/run` frontend | `modal-comparison.js:1179` (Runner UI) ONLY |
| `POST /comfymodal/comparison/run` backend | `__init__.py:5543` → `run_comparison` manifest → `_execute_comparison_profile` (`:5222`) → `run_prompt_stream` (`:5306`) |
| `run_prompt_stream` production callers | `__init__.py:5306` (Comparison), `__init__.py:7752` (warmup), `canonical_execution.py:3749` (`execute_modal_prompt`, dead post-H12), `experiment_runner.LocalRemoteInvoker` (dead post-H12), `ModalTransport` (V2 — KEEP) |

## 2. SETTINGS LEGACY GROUP — REMOVED

`studio-settings.js`: the entire Advanced ▸ Legacy group deleted (opener button "Open Legacy Settings", entries Legacy Setup/Profiles/Results/Settings, `openLegacyTab`, `activeLegacyTab` early-return branch, and the whole `renderLegacyView` export). No empty heading, no deprecation card. Modern Settings remains preferences-only with all seven sections (General/Generation/Outputs/History/Experiments/Interface/Advanced), search, reset-all, GPU, preview defaults, outputs, History layout, interface prefs, tracing level, H12 migration notice — all preserved and pinned green.

## 3. STUDIO LEGACY MOUNT SURFACE — RETIRED

- `studio-shell.js`: no longer imports `stopLegacyController`, forwards `mountLegacyTab`, exposes `setSettingsLegacyTab`, or keeps `state.settings.activeLegacyTab`. PAGES remain exactly Playground/History/Workflows/Backend/Settings.
- `modal-testing.js`: `mountLegacyTab` import/context-passing removed; dead lazy-tab machinery (`TAB_MODULES`, `mountLazyTab`, `resolveModule`, `_stopCurrentController`, `_currentController/_currentTab`, now-unused `bootstrapLoader` import) REMOVED so no legacy tab is mountable. H10 alias map (`ALIAS_PAGE_MAP`), deprecation notices, single sidebar registration, `open_testing_modal` global, `comfymodal.open-section` handler all preserved unchanged.
- `web/studio-legacy.js`: file LEFT ON DISK (unknown-tab fail-closed intact) as UNREACHABLE_DEAD — zero production importers (pinned). Wave G deletes it.

## 4. MODAL-SETTINGS RESPONSIBILITY SPLIT (H5C §15 executed)

| Region | Disposition |
|---|---|
| A. Overlay/UI-only | REMOVED: `window.mountSettingsPanel`, `window.open_comfymodal_settings` + overlay builder. `buildPanel()` body and helpers remain on disk as unreachable residue (Wave G) — deleting them was not required to kill reachability and would have churned ~3.7k lines against the freeze's "smallest honest change" rule. |
| B. Canvas compatibility state/writers | PRESERVED + SHIM: new bounded startup init in `setup()` reads persisted `comfymodal_enabled` into `window._comfyModalEnabled` with the exact former precedence (`savedEnabled === null ? true : savedEnabled === "true"`; absent key → enabled/cloud). `modal-node.js` readers (`!== false`, ×2) unchanged. No new Studio Run-mode UI, no new writer, no new global authority, Local pass-through untouched. |
| C. Output-preference shared wiring | PRESERVED: `studio-output-preferences.js` import chain, `syncLegacyOutputPrefsOnce()` in setup, shared `_comfyModalOutputOptions` authority. |
| D. Required initialization | PRESERVED: `syncLegacyGpuConfigOnce()` read-only server sync in setup; idempotent timer cleanup; redeploy-restart banner. |
| E. Dead residue | Left for Wave G (buildPanel internals, deploy/models/sync/auth/download sections, style helpers). |

## 5. SETUP / PROFILES / RESULTS / SETTINGS TABS — FINAL FATE

All four RETIRED from every mountable path (loader registrations deleted; both loaders' module references gone). None ported. No experiment creation resurrected; no inert forms moved. Module classifications (per §35):

| Module | Classification |
|---|---|
| `testing-setup.js` | UNREACHABLE_DEAD (Wave G deletes) |
| `testing-profiles.js` | UNREACHABLE_DEAD |
| `testing-results.js` | UNREACHABLE_DEAD (read-only display + Comparison selection/A-B workspace; zero POSTs already proven in H13) |
| `testing-settings.js` | UNREACHABLE_DEAD |
| `testing-ab-slider.js` | UNREACHABLE_DEAD (only dynamic importer is testing-results.js) |
| `testing-setup-adapter.js` | SHARED_HELPER_STILL_USED (modal-testing context draft getters) — re-measure at G |
| `studio-legacy.js` | UNREACHABLE_DEAD |

## 6. COMPARISON UI / OVERLAYS / GLOBALS — RETIRED

`modal-comparison.js`: extension registration DELETED (module is now inert at import — auto-loaded by ComfyUI but registers nothing), `_initContextMenu` + node-resolution helpers DELETED, all four window globals (`mountComparisonProfiles`, `mountComparisonRunner`, `openComparisonProfilesOverlay`, `openComparisonRunnerOverlay`) + `_openOverlayPanel` DELETED. Zero redirect symbols recreated. The pre-builder UI code above the retirement marker remains solely as unreachable Wave-G residue (pinned: `registerExtension` absent ⇒ builders can never execute).

## 7. COMPARISON CANVAS MENU — REMOVED

The slot-mapping wrapper around `app.canvas.getNodeMenuOptions` (including "Set as comparison" submenu) is gone. Normal ComfyUI canvas menus, `/prompt` interception, Production mode, and unrelated context-menu extensions untouched (canvas matrix pinned in the new suite + existing fake/live specs still green).

## 8. POST /COMFYMODAL/COMPARISON/RUN — EXECUTION RETIRED (H5C §9 frozen disposition)

Route stays REGISTERED; handler body replaced with the bounded truthful retired response:

```json
HTTP 410
{"status": "error", "error_code": "COMPARISON_RETIRED", "message": "Comparison execution was retired in Phase H14 (Wave E). Modern execution is Modal V2 only via the Studio Playground. Stored profiles and historical results remain readable."}
```

Proven by route-level tests: zero `run_prompt_stream` invocation, zero `run_comparison` manifest build, zero `save_comparison_manifest` write, regardless of payload (body is not even parsed). No silent redirect to experiment-v2, no Workflow auto-creation, no profile deletion. `_execute_comparison_profile` body remains as dead residue (exactly one textual occurrence = its own def; zero call sites) → Wave G. The six MUTATION_RETIRE routes were NOT frozen (Wave F owns that); all 17 `/comparison/*` routes verified still registered.

## 9. COMPARISON STORED DATA — BYTE-INTEGRITY PROVEN

No comparison data directories exist under the repo user tree (nothing to snapshot repo-side). Proof is behavioral: with a temp store seeded via `comparison.create_profile`, SHA-256 snapshots of every file are identical before/after invoking the retired endpoint (test `test_retired_endpoint_writes_nothing_to_stored_profiles`). READ_COMPAT proven: `GET /comparison/profiles` answers 200 from stored data after retirement. No destructive migration anywhere.

## 10. RUN_PROMPT_STREAM — POST-H14 CALLER MAP (NOT deleted)

| Caller | Status after H14 |
|---|---|
| `_execute_comparison_profile` (`__init__.py`) | DEAD residue — unreachable (retired endpoint never reaches it); census test pins exactly two textual direct calls: `_msg` (this dead body) + `ev` (warmup) |
| warmup route (`POST /deploy-warmup/run`) | LIVE — untouched (Wave F route freeze / Wave G deletion) |
| `canonical_execution.execute_modal_prompt` | DEAD residue (pre-existing post-H12) → Wave G |
| `LocalRemoteInvoker` | DEAD residue (pre-existing post-H12) → Wave G |
| `execute_plan` → `ModalTransport` → `modal_client.run_prompt_stream` | MODERN V2 transport — KEEP |

Reachable product callers of the un-planned invocation pattern: **zero** (warmup is Wave-F/G property, explicitly out of E scope).

## 11. WARMUP — UNTOUCHED PROOF

Route registered (`WarmupUntouchedTests.test_warmup_route_still_registered`), handler body byte-untouched by this lane (single-hunk diff confined to the comparison_run region), state machine and executor call intact. Destination unchanged: Wave F freeze, Wave G deletion.

## 12. TRANSITIONAL MODERN SINGLE SEAMS — PRESERVED (H5C §5)

Pinned in `TransitionalSingleSeamTests`: `GET /experiments/{id}` and `POST .../stop-now` remain registered with unchanged contracts (unknown-id → harmless 404, exactly the all-direct-V2 behavior); frontend wiring intact (`getStudioRunStatus` poll feed at `studio-playground.js:121`, Cancel via `stopExperiment` at `:2845`). Not frozen, not deleted, not reclassified. No broad `/experiments` cleanup performed (registry count unchanged except nothing — no route removed).

## 13. H12 / H13 INVARIANTS — PRESERVED

V2-only rejection vocabulary, persisted migration, env collapse, canvas Cloud V2 dispatch, Workflow/Experiment V2-only invocation all green (H12 suite 21/21 after test_18 rewrite). Recent-runs History-V2 hydration, creator absence, zero legacy network pins all green (12-test spec inside the 211). Comparison retirement strictly SHRANK execution reachability; general V2 transport altered nowhere.

## 14. STRUCTURAL CONSUMER SWEEP (§36) — CLASSIFICATION OF EVERY REMAINING MATCH

- `Legacy Setup` → truthful deprecation copy/comments only (`modal-testing.js` alias notice, `studio-playground.js:1152` comment). `Legacy Results` → comment. `Legacy Settings` → comments ("consumes same routes…") in Backend helper headers. `Open Legacy Settings` → ZERO matches.
- `open_comfymodal_settings` / `mountSettingsPanel` → only inside dead `testing-settings.js`.
- `mountLegacyTab` → only studio-legacy.js own def.
- `testing-*` names → dead-family self-references + CSS class names in testing-styles.js (dies with family in G).
- Comparison globals → only the retirement doc-comment in modal-comparison.js.
- `/comparison/run` → only dead Runner builder body (G residue).
- `run_prompt_stream` → warmup (live, protected), dead residue bodies, V2 transport, tests/docs.
**No user-visible retired-product caller remains.**

## 15. TESTS — CHANGES BY THIS LANE

New: `tests/test_h14_wave_e_retirement.py` (27 tests; registered in `STUDIO_PY_MODULES` after `test_f8_gpu_authority` per the in-process-load ordering rule): Settings-group absence, overlay absence + shim precedence, mount-surface retirement, alias/sidebar preservation, Comparison inertness + web-wide global sweep, route-level 410/no-exec/no-write/byte-integrity/READ_COMPAT/17-route registry, transitional seam protection, warmup census.
Inverted/updated pins (each formerly asserted the pre-E state "until Wave E"): `test_testing_shell_integration.py` (legacy-group, items-clickable→no-mount-path, overlays/canvas-menu, overlay-global, cleanup-trigger ×3, testing-api reference), `test_studio_backend.py` (×3), `test_modal_workspace_ui_ast.py` (sidebar launcher), `test_testing_ui_wired.py` (×3), `test_testing_settings_js.py` (embedded mount hook), `test_h12_v2_only_consolidation.py::test_18` (rewritten to retired-response + handler-slice no-stream + residue-def-only).

## 16. GATE + DELTA ACCOUNTING

Focused lanes (all green unless noted): h14+h12 = 48; shell_integration/ui_wired/workspace_ast/gpu_config/studio_backend/h14 = 723 (2 fails = documented pre-existing out-of-gate stale pins, see below); routes_registered/image_packaging/integration_acceptance/testing_*_js/history_v2_js = 272 → after fixes only the 2 stale pins + 2 pre-existing environmental errors remain outside the gate.

FULL GATE `python tests/run_studio_tests.py --fake`:

```
python             run=1974  fail=0  error=0  skip=0     (baseline 1945)
node-unit          run=21    fail=0  error=0  skip=0     (baseline 21)
fake-playwright    PASS      211 passed / 211 (direct count)  (baseline 211)
```

Delta explanation (+29 Python, +0 node, ±0 fake):
- +27 = new registered `test_h14_wave_e_retirement.py`.
- +1 = `StudioLegacyContractTests` 2→3 (group-retired split into absence/modern-sections/no-mount-path).
- +1 = `LegacySettingsSidebarGuardTests` 7→8 (added canvas-shim presence pin).
- All other edits are count-neutral inversions/renames. Fake Playwright unchanged because the retired surfaces never had fake specs and no fake backend/spec was touched.

Out-of-gate observations (NOT regressions; carried debt confirmed still failing identically): `test_modal_workspace_ui_ast` production-summary-label + output-savefolder-literal (H5B §6/H5C §24 Class B/D); `test_image_packaging_refactor` setUpClass BOM SyntaxError from dirty `comfyapp.py`; `test_integration_acceptance.test_i2i_payload_contract_end_to_end` TypeError from dirty `comfyapp.py` packaging harness — none touch H14 files.

## 17. WAVE-F HANDOFF TABLE (classification after E; act without re-audit)

### Comparison
| Route | Class |
|---|---|
| GET profiles · profiles/{id} · results · results/{id} · profiles/{id}/workflow/nodes · profiles/{id}/workflow · config GET · gallery/{id} · validate · detect-slots | READ_ONLY_COMPAT (hidden; keep answering from stored data) |
| POST profiles · PUT profiles/{id} · DELETE profiles/{id} · duplicate · slots · config POST | MUTATION_RETIRE → freeze writes here (zero UI callers since E) |
| POST /comparison/run | INERT (410 COMPARISON_RETIRED landed in E; delete route in G if desired with same-change pin updates) |

### Experiments
| Route | Class |
|---|---|
| GET /experiments/{id} · POST .../stop-now | **MODERN_LIVE / INTERNAL_ONLY — DO NOT FREEZE** (protected Single poll/Cancel seams) |
| GET /experiments · GET /{id}/events · checkpoints/{cp}/logs · cells/{cell}(+/attempts) | READ_ONLY_COMPAT (last UI consumer died with E) |
| compile · create · start · pause · resume · stop-after-current · run-missing · clone · checkpoints continue/restart/restart-from/skip/unskip · cells rerun · rerun-selected | ZERO_CALLER → freeze/inert |
| POST /studio/experiment | ZERO_CALLER (helper `runStudioExperiment` has zero importers) → freeze; G deletes with helper |
| POST /studio/experiment-v2 · /history-v2/* · /studio/run · presets/snapshots | MODERN_LIVE — untouched |

### Other
| Route | Class |
|---|---|
| /run-history list/detail/logs/timing | READ_ONLY_COMPAT (programmatic bridge) |
| PATCH /run-history/{id}/annotations · save | READ_ONLY_COMPAT (shrinking) |
| /studio/backends | hidden read-only shim; replace consumers then demote (§19) |
| /auth/setup | COMPATIBILITY — untouched; F/G review |
| /deploy-warmup/* | RETIRE confirmed (FA-3) → freeze route HERE in F; G deletes code |
| /history (platform feed) | KEEP |

## 18. WAVE-G HANDOFF TABLE (caller-count-based residue, re-measured post-E)

UNREACHABLE_DEAD (delete with their dedicated tests/specs):
- Files: `testing-setup.js`, `testing-profiles.js`, `testing-results.js`, `testing-settings.js`, `testing-ab-slider.js`, `studio-legacy.js`; `modal-comparison.js` UI layer (whole file once builders go); overlay regions of `modal-settings.js` (`buildPanel` + section builders + style helpers + download-progress machinery); `testing-styles.js` legacy sections (re-measure).
- Machinery: `modal-testing.js` draft/preview/experimentId context getters + storage keys (`comfymodal_setup_draft`, `comfymodal_last_experiment_id`) now consumer-less (re-measure at G); `testing-setup-adapter.js` (after those getters go); harness-bootstrap `mountLegacyTab` stub.
- Python: `_execute_comparison_profile` (`__init__.py`, def-only occurrence) + now-unused imports `run_comparison`, `save_comparison_manifest`; `direct_studio_run_completion`; `execute_modal_prompt`; `LocalRemoteInvoker`; `_prepare_studio_run_context` + `_handle_studio_run_scheduler`; `_playground_runtime_mode` (re-measure); frontend dead helpers `runStudioExperiment`/`listExperiments`/`listRunHistory`/`setRunAnnotation`/`saveRunHistoryOutput` (`studio-backend-api.js`) and the testing-api dead creator family.
- Test debt (unchanged from H5C §24): unregistered H6/H7/H12 suites + `studio_legacy_settings_authority_unit.mjs` migrate-then-register; stale tracker-membership ×5; stale Production copy pins ×2 (still failing, out-of-gate); F8/workflow reverse-order isolation note.

NOT dead (do not delete): `modal_client.run_prompt_stream` (V2 transport), REGISTRY history readers, `history_index.py`, `LegacyMigrationSeam`/`legacy_mapping`, replay projection, workspace fallback, `GET /history`.

## 19. FILES MODIFIED BY THIS LANE

Production: `web/studio-settings.js`, `web/studio-shell.js`, `web/modal-testing.js`, `web/modal-comparison.js`, `web/modal-settings.js`, `__init__.py` (single region: comparison_run handler).
Tests: `tests/test_h14_wave_e_retirement.py` (NEW), `tests/run_studio_tests.py` (registration), `tests/test_testing_shell_integration.py`, `tests/test_studio_backend.py`, `tests/test_modal_workspace_ui_ast.py`, `tests/test_testing_ui_wired.py`, `tests/test_testing_settings_js.py`, `tests/test_h12_v2_only_consolidation.py`.
Deleted: NONE (freeze: dead modules stay for Wave G).

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / stash / clean by this batch: **NONE**.
