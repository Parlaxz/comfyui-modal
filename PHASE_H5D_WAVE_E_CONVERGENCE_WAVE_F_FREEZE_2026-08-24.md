# PHASE H5 FOLLOW-UP D — WAVE-E CONVERGENCE & WAVE-F FREEZE — EVIDENCE DETAIL (2026-08-24)

**Batch type:** READ-ONLY audit + contract append. Files modified by this batch: `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (appended "H5 FOLLOW-UP D" section — AUTHORITATIVE) + this document. Zero production or test files modified. No deploy/live/GPU/generation/commit/push/branch/worktree/reset.
**Authority:** the appended H5 Follow-Up D section (FD-1…FD-26) in the contract freeze document. This report carries measurement evidence only.

---

## 1. GATE MEASUREMENTS (raw)

Run 1 — wrapper (`python tests/run_studio_tests.py --fake`):
```
STUDIO GATE SUMMARY
  python             run=1974  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=1    error=0    skip=0
FAILED LANES: fake-playwright
```
Failing fake test: `tests/browser/fake/studio-fake-lifecycle.spec.mjs:523` — "11. workflow node progress is not overwritten by sampler max" — `waitForStatus("Run completed", {timeout:20000})` timed out under full-suite parallel load.

Run 2 — failing spec alone (`npx playwright test --config=playwright.fake.config.mjs studio-fake-lifecycle.spec.mjs`): **14 passed (24.8s)**.

Run 3 — mandated exact-count command (`npx playwright test --config=playwright.fake.config.mjs --reporter=line`): **211 passed (3.2m)** / 211.

Conclusion: Python 1974/1974 · Node 21/21 files · Fake 211/211. The single wrapper failure is a parallel-load flake (timing), not a regression; delta vs H14's reported baseline = zero on all three lanes. FD-1 records both the flake and the authoritative triple.

## 2. WAVE-E STATE MARKERS (grep/read evidence)

| Marker | Evidence |
|---|---|
| Settings Legacy group absent | `web/studio-settings.js`: zero matches for `renderLegacyView`/`activeLegacyTab`/`settings-legacy-` testids; retirement comment :582–584; `.comfymodal-settings-legacy-open` remains only as dead CSS in `studio-styles.js:2090` |
| Legacy tabs unmountable | `studio-shell.js` no longer forwards `mountLegacyTab`; `modal-testing.js` lazy-tab machinery removed; `studio-legacy.js` has zero production importers |
| Overlay globals gone | `open_comfymodal_settings`/`mountSettingsPanel` matched ONLY in `web/testing-settings.js` (:63/:65/:90/:91/:109/:110/:173/:174) — UNREACHABLE_DEAD module |
| Comparison UI/globals/canvas menu gone | `modal-comparison.js:1387–1392` doc-comment only; zero live references to `mountComparisonProfiles`/`mountComparisonRunner`/`openComparison*Overlay`/`_initContextMenu` |
| `/comparison/run` inert | `__init__.py:5543–5563`: handler returns 410 `{"status":"error","error_code":"COMPARISON_RETIRED",...}` without parsing body |
| Alias routing intact | `modal-testing.js:227–234` ALIAS_PAGE_MAP = playground/dashboard→backend/setup→playground/profiles→playground/results→history/history→history/settings→settings |
| Sidebar intact | `studio-shell.js` PAGES = playground/history/workflows/backend/settings |
| Canvas shim intact | `modal-settings.js:45` STORAGE_KEY_ENABLED; :4125–4133 startup init `window._comfyModalEnabled = savedEnabled === null ? true : savedEnabled === "true"` |

Discrepancy (reported, unmodified): Settings ▸ Advanced "Runtime & Backend" group still present (`studio-settings.js:528–580`; refresh calls :626–627) with test pins `tests/test_studio_backend.py:392–407`. Contract debt vs H5 §2/§11, pre-existing; the sole live consumer of `GET /studio/backends`.

## 3. RUN-HISTORY WRITERS — CALL-SITE EVIDENCE (FD-4)

`web/studio-playground.js`:
- :45 `import { updateRunAnnotation, saveRunOutput } from "./studio-backend-api.js";`
- :3387–3394 favorite: `if (nr._historyKind) repo.setFavorite(...) else updateRunAnnotation(apiBase, runId, {favorite})`
- :3484–3496 note: same split with `{note}`
- :3743 Save-output: `if (nr._historyKind === "generation")` → `repo.exportAsset(_assetId)`; ELSE branch :3780–3819 → `saveRunOutput(apiBase, nr.id, {output_index: 0})` gated on `nr.id && nr.imageUrl && !recordSaved`

`nr._historyKind` producers: ONLY `refreshRecentRuns` (:345 experiment, :370 generation) over History-V2 feed items. `normalizeStudioRun` (`web/studio-run-normalizer.js:844–992`) sets NO `_historyKind`; `_handleDirectRunResult` (:2612–2673) assigns `_selectedRun = normalized` (:2665) with `id = result.runId` (:2632) — the fresh `.run_history` key. Persisted-selection restore `loadRunResult` (:476/:883) also lacks the tag.

Server handlers: PATCH annotations `__init__.py:6918–6964` merges favorite/note into `.run_history/<id>/meta.json` via `history.update_run`; POST save :6979+ copies output files (per-run locks :6966–6977). Both mutate stored data.

Reachability verdict: COMPAT_WRITE, LIVE callers (fresh direct-run panel + stale persisted selections). Freezing would break Playground result-panel favorite/note/save today.

## 4. RUN-HISTORY READERS — CALLER CENSUS (FD-5)

- `listRunHistory` (`studio-backend-api.js:275`) → GET `/run-history`: zero importers in `web/`.
- Bridge repository mode (`history-v2-repository.js`): opt-in only (`mode:"bridge"` explicit; default "auto"→v2, :116–127). Bridge endpoints: listFeed uses `/history` unified (:862); getGeneration uses `/run-history/{id}` (:883); setFavorite/setNote use PATCH annotations (:921/:933).
- logs/timing: zero callers anywhere; no V2 equivalent (H3 §10).
- Consumers of the underlying store that do NOT use HTTP: migration seam + `REGISTRY.history()` readers (internal).

## 5. BACKEND/RUNTIME PRESETS LIVENESS (FD-6)

- `getRuntimePresets` def `studio-backend.js:49–58` (wraps `listPresets` → `GET /studio/presets`, module cache); callers `studio-playground.js:707`, `:1177`, `:3005`; `studio-experiment-mode.js:137–138` (dynamic import).
- `listPresets` dynamic imports: `studio-playground.js:423`, `:2723`.
- Backend page tab: `studio-backend.js:240` `makeTab("presets","Backend Presets")` → :260 `renderPresetsPage` → `studio-backend-presets.js` CRUD (:43 list, :121/:423 delete, :379 update, :408 duplicate, :507 create).
- Wizard: `studio-preset-wizard.js:18` imports createPreset/updatePreset; :866 updatePreset, :925 createPreset.
- Settings counts fetch: `studio-settings.js:723`.
- Workflow Presets separation: `studio-backend-api.js:530–578` (`/studio/workflows/versions/{vid}/presets*`, `/studio/workflows/presets/*`) — distinct family.

## 6. `/STUDIO/BACKENDS` CONSUMER SWEEP (FD-8)

Fetch sites across `web/*.js` + fake specs for `studio/backends`: exactly `studio-backend-api.js:29` (getBackends) and `:42` (getCompareBackends, `?kind=comparable`) and `studio-settings.js:724` (counts row). Importers of `getBackends`/`getCompareBackends` from `./studio-backend.js`: NONE (only its own re-export wiring at :9/:29/:33). Modern Backend page modules (`studio-backend-{workspaces,deployment,credentials,runtime,presets,snapshots,capture}.js`): zero backends references. Server handlers: GET :7258 (reads store + folds comparison profiles via `_discover_legacy_profiles_as_backends()`), POST :7290, PATCH :7312, DELETE :7340, duplicate :7353 — all `_BACKENDS_STORE.write_atomic` (`.studio_backends.json`). Fake mirror: GET only (`fake-server.mjs:562`).

## 7. COMPARISON ROUTE REGISTRY (FD-9 verification notes)

All 17 decorators enumerated at :5437–5623 (methods as tabled). Handler semantics spot-verified: validate :5510–5517 (pure compute, returns validation), detect-slots :5519–5528 (pure compute, returns candidates), slots :5530–5541 (persists via `set_slots`). Read handlers return stored/computed values with no write path. Frontend fetch census: every `/comparison/` reference lives in `modal-comparison.js` (inert residue), `testing-profiles.js`, `testing-setup.js` (both UNREACHABLE_DEAD).

## 8. EXPERIMENT FAMILY REGISTRY (FD-12 verification notes)

22 routes enumerated at :5734–6614 (+ adjacent `/studio/experiment` :7531, `/studio/experiment-v2` in `experiment_modern_routes.py:1445`). Compile handler verified pure-compute (:5734–5776: validate → compile_experiment → enrich → return; no persistence). stop-now verified :6369–6387 (scheduler stop / pending-stop / 404). Detail verified :5910–5925 (REGISTRY read + snapshot rebuild; 404 unknown). Live frontend wiring: `studio-playground.js:121` poll via `getStudioRunStatus` (`studio-backend-api.js:157`), `:2845` cancel via `stopExperiment` (:169). `runStudioExperiment` (:143): zero importers.

## 9. WARMUP + AUTH/SETUP (FD-14/FD-15)

Warmup handlers: status :7588–7594 (read WarmupState), run :7596–7672 (workflow resolve → `from modal_client import run_prompt_stream` :7629 → direct stream → mark warmed/failed), invalidate :7674–7678 (state file write). Deploy relationship: `__init__.py:1714–1742` marks generation + prints manual-warmup instruction; NO internal invocation of the route. Last consumer-gate: `gate_experiment_on_stored_generation` invoked at :6005 inside legacy experiment create/start (zero-caller family). Zero `deploy-warmup` references in `web/`.

`/auth/setup` :3577–3607: writes global modal.toml (`_write_modal_toml`), upserts "Primary" workspace set_active, spawns `_run_deploy_background` thread. Zero `auth/setup` references in `web/`.

## 10. FAKE MIRROR INVENTORY (FD-19 source)

`fake-server.mjs` route table enumerated (86 mirrored method/path pairs). Relevant presence: experiments GET list/detail + stop-now POST + `/studio/experiment` POST + `/studio/experiment-v2` POST; run-history GET list + annotations PATCH + save POST; presets full CRUD; snapshots full CRUD; backends GET only; history unified GET; full history-v2 family; models/custom-nodes library; workflows domain; config GET/POST; deploy/status; profile/level; outputs; assets. Absent: comparison/* (all 17), warmup ×3, auth/setup, experiments compile/create/start/pause/resume/clone/run-missing/checkpoints*/cells*/rerun*, presets/prompts|images, legacy models/sync/runtime families.

## 11. TEST-REGISTRATION RE-MEASURE (FD-24 source)

`tests/run_studio_tests.py`: `test_h14_wave_e_retirement` registered at :95. Zero matches for `test_phase8_execution_mode`, `test_h12_v2_only_consolidation`, `studio_backend_operations_unit`, `studio_model_library_parity_unit`, `studio_legacy_settings_authority_unit` → all five remain unregistered (carried debt).

## 12. ROUTE-REGISTRY PINS

`tests/test_routes_registered.py` pins the legacy registry (experiments family :200–237, presets prompts/images :245–263, etc.). Keeping retired routes registered-and-inert preserves these pins without edits — the basis of FD-21's "keep registered" decisions.

---

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
