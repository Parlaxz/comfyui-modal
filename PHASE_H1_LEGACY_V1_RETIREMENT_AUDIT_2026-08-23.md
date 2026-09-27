# PHASE H1 — LEGACY/V1 SURFACE RETIREMENT & CONSOLIDATION AUDIT (2026-08-23)

**Batch:** H1 (read-only audit). No production code, tests, deploy, Modal, GPU, live generation, commit, push, branch, worktree, reset performed.
**Inputs:** `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` (§38 Phase-H handoff + MUST-preserve invariants).
**Method:** full reverse-import map of `web/*.js`, route-decorator sweep of `__init__.py` + all `*_routes.py`, localStorage-key sweep, storage-file inventory, test-gate registration review (`tests/run_studio_tests.py`, `playwright.fake.config.mjs`). Every classification below is traced to imports/callers, not filenames.

---

## 0. VERDICT SUMMARY

The modern product is the Studio shell (`modal-testing.js` → "Modal GPU" sidebar tab → `studio-shell.js`) with exactly five pages: **Playground, History (V2), Workflows, Backend, Settings**. Around it survive **13 distinct legacy/transitional surfaces** (§1). Most are concentrated in one place — the Settings "Legacy" group — which makes Wave-1/2 retirement unusually cheap. The genuinely risky items are not UI at all: they are the **stored-data references** (History rows → workflow_id/version_id/preset_id; legacy run-history records) and the **canvas execution path**, which is still the only consumer of the Run-mode toggle and shares output-option globals with modern surfaces.

Clearest RETIRE candidates: orphaned `web/studio-history.js` (zero importers), the six-tab Legacy group's dead tabs, hidden-by-default legacy sidebar tabs, the bridge History repository.
Clearest RE-HOME candidates: Comparison Profiles management (still the only profile editor), canvas Production-mode marking, model inject/download controls that exist only in the legacy panel.
Must remain as COMPATIBILITY-SHIM: legacy `/run-history/*` read + `/annotations` PATCH (bridge/migration source per F2), `/history` unified feed (Playground recent-runs still reads it), `/studio/backends` discovery, `.studio_backends.json`.

---

## 1. USER-VISIBLE SURFACE INVENTORY

Nav truth: `studio-shell.js` PAGES = playground/history/workflows/backend/settings. There is **no separate Experiments page** — modern Experiments live inside Playground (`studio-experiment-mode.js`) and render in History V2.

| # | Surface | Visible label | Implementation | Mount / navigation path | Backend routes used | State/storage | Modern replacement | Reachability | Tests exercising it |
|---|---|---|---|---|---|---|---|---|---|
| S1 | Modern Playground | "Playground" | `studio-playground.js` (+`-run/-state`, `studio-experiment-mode.js`, `studio-feature-registry.js`) | Shell nav | `/studio/run`, `/studio/experiment-v2`, `/history-v2/experiments/*`, `/experiments/{id}` (status poll), `/experiments/{id}/stop-now` (cancel), `/run-history?limit=50` + `/history` + `/experiments` (recent-runs hydration), `/studio/presets`, `/config` | LS: `comfymodal.studio.playground.v1`, `.drafts.v1`, `.results.v1`, `.workflow.v1`, `.workflow-handoff.v1`, `comfymodal.studio.experiment.draft.v1`, `.active.v1` | — (this IS modern) | Normal UI | many fake specs |
| S2 | Modern History | "History" | `studio-history-v2.js` (+detail/experiment, `history-v2-repository/view-state/browser-download/export`) | Shell nav | `/comfymodal/history-v2/*` | `comfymodal.history.v2.viewstate`; `comfymodal-studio-history-columns` | — | Normal UI | fake history specs |
| S3 | Modern Workflows | "Workflows" | `studio-workflows.js` (+portability, model-library) | Shell nav | `/studio/workflows*` incl. portability/export/import-manifest | domain JSON stores (read/write via API) | — | Normal UI | portability spec |
| S4 | Modern Backend page | "Backend" | `studio-backend.js` (+capture/presets/snapshots, preset-wizard, graph-binding) | Shell nav | `/studio/snapshots*`, `/studio/presets*`, `/studio/backends*` (discovery/import) | `.studio_snapshots.json`, `.studio_presets.json`, `.studio_backends.json` | — | Normal UI | structural tests |
| S5 | Modern Settings | "Settings" | `studio-settings.js` (+`studio-output-preferences.js`) | Shell nav | `/config` (GET/POST), `/deploy/status`, `/profile/level`, `/studio/snapshots|presets|backends` (counts), output sync | LS keys §8; server `.modal_settings.json` | — | Normal UI | settings specs |
| L1 | **Legacy group (6 tabs)** | "Legacy": Legacy Dashboard / Setup / Profiles / Results / History / Settings | `studio-settings.js` Advanced section → `renderLegacyView` → `studio-legacy.js` dynamic-imports `testing-{dashboard,setup,profiles,results,history,settings}.js` | Settings ▸ Advanced ▸ Legacy list (testids `settings-legacy-*`) | see §7 route map | LS `comfymodal_setup_draft`, comparison runner keys | partially Workflows/Playground/History | Normal UI (prominent) | `test_testing_*_js.py` (structural, in gate); no browser spec drives these tabs |
| L2 | **Legacy Settings overlay panel** | "Settings" modal ("Modal GPU" panel content) | `modal-settings.js` `open_comfymodal_settings()` / `mountSettingsPanel` | (a) modal-testing sidebar panel button "Open Legacy Settings"; (b) testing-dashboard/testing-settings buttons; (c) `window.open_comfymodal_settings()` global | `/config`, `/deploy/*`, `/models*`, `/auth/status`, `/download/*`, `/workspaces*`, `/manifest*` | same LS keys as modern (shared helper) | modern Settings covers outputs/GPU/engine/tracing; NOT deploy/model-inject | Normal UI (button) + programmatic global | `test_modal_settings_gpu_config.py`, `studio_legacy_settings_authority_unit.mjs` (**unregistered in gate**) |
| L3 | **Hidden legacy sidebar tabs** | "Modal GPU" (settings), "Comparison Profiles", "Comparison Runner" | `modal-settings.js:4246`, `modal-comparison.js:1663` | registered ONLY when `window.__comfyModalEnableLegacySidebarTabs === true` | same as parent modules | — | shell entry exists | Programmatic/opt-in only (dead by default) | none found |
| L4 | **Comparison canvas context menu** | node context-menu slot items (Prompt/Negative Prompt/Seed/Steps/Guidance/Width/Height/Input Image → "apply mapping to profile") | `modal-comparison.js:_initContextMenu()` wraps `app.canvas.getNodeMenuOptions` — **NOT gated by the sidebar flag; always active** | right-click any canvas node | `/comparison/profiles`, `/comparison/profiles/{id}/slots` | comparison profile files on disk | none (unique capability) | Normal UI (always on) | none found |
| L5 | **Comparison overlays** | "Comparison Profiles" / "Comparison Runner" dialogs | `modal-comparison.js` `window.openComparisonProfilesOverlay/openComparisonRunnerOverlay` | buttons in Legacy Dashboard (L1) | `/comparison/*` (profiles CRUD, run, results, gallery, config) | `user/default/comfy-modal/comparison_profiles/<id>/{profile,workflow_api,workflow,adapter}.json`; comparisons dir; LS `comfymodal_comparison_runner_inputs/config`, `_selected_profiles`, `_profiles_tab` | none (A/B runner unique; Workflow Portability is analysis-only, not execution) | Normal UI via Legacy Dashboard; overlays also programmatic globals | `test_comparison_*.py` (backend) |
| L6 | **Legacy experiment run surface inside modern Playground** | "Run Experiment" (aggregate preset matrix) + Cancel | `studio-experiment-mode.js` `experimentRunSurface()` returns `"legacy"` when no workflow/version selected → `runStudioExperiment` | Playground experiment block | POST `/studio/experiment`, GET `/experiments/{id}` (poll), POST `/experiments/{id}/stop-now` | data-root `experiments/` JSON store | modern experiment-v2 (same file, D5 section) | Normal UI (fallback state) | fake experiment specs |
| L7 | **V1 engine option** | "V1 - Legacy fallback" option in Execution Engine select | `studio-settings.js` Generation section (options from GET `/config` `available_execution_modes`); duplicated in legacy panel | Settings ▸ Generation | GET/POST `/config` (`execution_mode`) | `.modal_settings.json["execution_mode"]` | V2 default; H2 owns semantics decision | Normal UI | f4/f8 units touch reset copy |
| L8 | **Run mode Cloud/Local** | segmented Cloud/Local in Settings ▸ General | `studio-settings.js:409-441` (mirrors legacy panel toggle) | Settings ▸ General | none (LS only) | LS `comfymodal_enabled` + `window._comfyModalEnabled` | none — sole consumer is canvas `/prompt` interception (S9/modal-node.js:678) | Normal UI | settings spec asserts presence |
| L9 | **Canvas execution path ("legacy canvas")** | ComfyUI Generate button on canvas | `modal-node.js` `comfyui.modal` extension: patches `api.fetchApi` → POST `/prompt` becomes `/comfymodal/prompt`; attaches output options + production trace; progress bar | Canvas (always installed) | `/comfymodal/prompt`, `/comfymodal/benchmark/workflow` (silent capture), `/model/install` redirect | reads `window._comfyModalOutputOptions` + 6 output LS keys + `comfymodal_production` | none — this is the only path that executes arbitrary canvas graphs through Modal | Normal UI (core canvas feature) | tracker/timing tests |
| L10 | **Canvas Production mode** | "Mark as Production Output"/"Bypass in Production" context items | `modal-node.js` `comfyui.modal.production` | canvas node context menu | (rides `/comfymodal/prompt` body) | graph extra `comfymodal.production_mode_enabled`, node properties, LS `comfymodal_production` | none | Normal UI | structural |
| L11 | **Orphaned legacy History page module** | (unmounted; label would have been "History") | `web/studio-history.js` (1704 lines) — **zero static or dynamic importers**; exports `renderHistory` never called | NONE (would be `open_testing_modal("history")`→shell? no: shell renders V2; TAB_HISTORY maps to page "history"=V2) | would use `/run-history`, `/history`, `/experiments`, `/run-history/{id}/annotations`, `/run-history/{id}/save` | `comfymodal-studio-history-columns` (key SHARED with V2 grid!) | studio-history-v2.js | **Unreachable** (dead code) | `test_testing_shell_integration.py` + `test_studio_timing_integration.py` structurally test it (in gate) |
| L12 | **Bridge History repository** | n/a (code path) | `history-v2-repository.js:_createBridgeRepository` — selected only when `mode==="bridge"` via `context.historyMode`/`window.__COMFYMODAL_HISTORY_MODE__` | programmatic only | `/history`, `/run-history/{id}`, `/run-history/{id}/annotations` | — | v2 repository (auto default) | Programmatic/deep only; production always "auto"→v2 | e4c/e4d unit tests assert bridge-mode refusal behavior |
| L13 | **Legacy annotations + save routes (backend)** | n/a | `__init__.py` `/run-history/{id}/annotations` PATCH, `/run-history/{id}/save` POST | consumed by bridge repo (L12), `studio-backend-api.js updateRunAnnotation/saveRunOutput` (callers = L11 only), F2 migration source | see §7 | run-history store | History V2 favorite/note/export | API-level; UI writers are legacy-only | `test_run_history*.py` |

Also noted, not surfaces: `window._comfyModalGpu` already removed (F4B, zero readers confirmed). `window._comfyModalExecutionMode` is a display/carry global written by both settings surfaces and read by `studio-output-preferences.loadModalOptions` to stamp `modal_options.execution_mode` on modern runs — it is a live carrier, not dead.

---

## 2. FRONTEND MODULE MAP (web/)

**Entry points (ComfyUI extensions, loaded because `WEB_DIRECTORY="web"`):**
- `modal-node.js` — canvas integration + progress bar + `/prompt` interception + Production extension (L9/L10).
- `modal-testing.js` — primary "Modal GPU" sidebar tab; opens Studio shell; owns draft/experiment handoff state; exposes `open_testing_modal`.
- `modal-settings.js` — legacy settings panel + overlay opener + hidden sidebar tab (L2/L3).
- `modal-comparison.js` — comparison overlays + hidden sidebar tabs + always-on canvas context menu (L4/L5).

**Modern shell tree (KEEP):**
`studio-shell` → `studio-playground`(+`studio-playground-run`, `studio-playground-state`, `studio-experiment-mode`, `studio-feature-registry`, `studio-workflow-run`) · `studio-history-v2`(+detail/experiment, `history-v2-view-state`, `history-v2-browser-download`, `history-v2-export`) · `studio-workflows`(+`studio-portability`, `studio-portability-checklist`, `studio-model-library`) · `studio-backend`(+api/capture/presets/snapshots, `studio-preset-wizard`, `studio-graph-binding`) · `studio-settings`(+`studio-output-preferences`). Shared: `studio-ui`, `studio-styles`, `studio-run-model`, `studio-run-adapters`, `studio-run-normalizer`, `studio-backend-api`, `comfymodal-progress`, `history-v2-repository`, `history-v2-fixtures` (fixture repo for tests).

**Legacy tree (candidates):**
- Loader: `studio-legacy.js` (dynamic import + controller stop) — serves L1.
- Tabs: `testing-dashboard.js` (launchpad → other legacy tabs + comparison overlays), `testing-setup.js` (experiment compiler UI → `/comparison/profiles`, `/presets/prompts|images`, `/experiments/compile`), `testing-profiles.js` (comparison profile editor), `testing-results.js` (legacy experiment monitor → `/experiments/*` incl. pause/stop-after-current/stop-now/resume/run-missing/checkpoints/events), `testing-history.js` (read-only recent runs → `/run-history?limit=20`), `testing-settings.js` (thin wrapper mounting `mountSettingsPanel`).
- Support: `testing-api.js` (fetch helpers), `testing-setup-adapter.js` (draft normalization; ALSO imported by modal-testing for handoff state), `testing-styles.js`, `testing-ab-slider.js` (results A/B fullscreen).
- Orphan: `studio-history.js` (L11).

**Reverse-import facts (measured):** nothing imports `studio-history.js`. `testing-*` modules are reached ONLY via `studio-legacy.js`/`modal-testing.js` dynamic import maps. `studio-preset-wizard.js`/`studio-workflow-run.js`/`testing-ab-slider.js` are dynamic-imported by modern modules (KEEP).

---

## 3. DUPLICATED PRODUCT AUTHORITIES

| Concept | A. Canonical modern authority | B. Legacy authority | C. Can writes diverge today? | D. Legacy still required? |
|---|---|---|---|---|
| Output folder/format/quality/webp/autosave/sidecar | Server `.modal_settings.json` via `/config`; shared helper `studio-output-preferences.js` used by BOTH surfaces (F4B/F9) | legacy panel writes through same helper | transiently no (server-first, ack-rollback) | until L2 retires; helper must stay |
| Preview default/codec/quality | same helper + `/config` | same | no | same |
| GPU selection | Server persisted GPU (F8): POST `/config {gpu}`; frozen into plans | legacy panel explicit-change POST (single site) | no (both hit same route) | until L2 retires |
| Execution engine (v1/v2) | `.modal_settings.json["execution_mode"]` via `/config`; carried to runs as `modal_options.execution_mode` | legacy panel select writes same key | no (same key) but TWO UI writers exist | H2 decides; UI duplication removable |
| Run mode Cloud/Local | **none modern** — LS `comfymodal_enabled` + `window._comfyModalEnabled`; two writers (modern Settings General + legacy panel); ONE consumer (canvas interception L9) | same keys | yes (cosmetic divergence only; same keys) | canvas path needs it until/unless S1 semantics defined (H2) |
| Single-run execution | `/studio/run` (workflow branch when `workflow_version_id` present, else snapshot/preset branch) | canvas `/comfymodal/prompt` (separate concept: raw graph) | different artifacts; not duplicative | KEEP both (different products) |
| Experiments | modern: `/studio/experiment-v2` + `/history-v2/experiments/*` (History V2 SQLite) | legacy: POST `/studio/experiment` + `/experiments/*` (JSON store under data-root `experiments/`) | **YES** — Playground mounts exactly one surface based on selection, but both remain creatable; stores are disjoint | legacy creator needed while preset-only flows exist (RE-HOME decision for H) |
| History feed | History V2 `/history-v2/feed` | `/history` unified index + `/run-history` list | reads only from modern UI except Playground recent-runs hydration (reads all three legacy feeds) | reads required until Playground hydration re-homed |
| Favorites/Notes | History V2 columns (`/history-v2/generations|experiments/{id}/favorite|note`) | PATCH `/run-history/{id}/annotations` (one-way migration source; later legacy edits do NOT propagate — F2) | YES across generations (V2 write ≠ legacy record annotation) | bridge must stay until legacy-record editing is declared closed |
| Export/Download | bodyless `/history-v2/assets/{id}/export` + Browser Download | `/run-history/{id}/save` (legacy save pipeline; UI caller = L11 only) | no (disjoint records) | route frozen for old records' compatibility reads; writer UI already gone with L11 |
| Presets | THREE concepts: (1) Workflow Presets (version-scoped, G authority chain); (2) Studio snapshot-presets `/studio/presets` (Playground/Backend selection); (3) prompt/image presets `/presets/prompts|images` (Setup tab only) | (3) is legacy-only | disjoint stores; no divergence | (3) required by Legacy Setup; RE-HOME or RETIRE with it |
| Backends | presets power modern selection; `/studio/backends` explicitly "legacy compatibility / import-only" (comment at `__init__.py:7330`) | comparison profiles discovered as backends | `.studio_backends.json` writable via routes (manual backends get disabled_reason pointing at Legacy Profiles) | discovery/import path still wired into Backend page |
| Model install/download | Model Library `/studio/models/install-request` | legacy panel bulk download `/models/batch-install`, `/model/install`, download polling | YES (two install pipelines) | legacy panel is the only UI for batch/volume download today (RE-HOME candidate) |
| Deploy/workspace control | none in modern Settings beyond status row | legacy panel: deploy, swap, workspaces, manifest repair, warmup | YES (only writer) | REQUIRED — no modern equivalent (RE-HOME, not RETIRE) |

---

## 4. V1/V2 EXECUTION SURFACES (map only — H2 owns semantics)

**Toggles/selects:** modern Settings engine `<select>` (options = GET `/config` `available_execution_modes` = `[v2 "V2 — Recommended", v1 "V1 — Legacy"]`, `execution_mode_locked` when `COMFYMODAL_RUNTIME` env set); legacy panel engine select (same key).
**Routes:** GET/POST `/comfymodal/config` (`execution_mode`, `execution_readiness {v1:{status}, v2:{status}}`).
**State:** `.modal_settings.json["execution_mode"]` (currently `"v2"` on disk). Sanitization at load: unknown saved modes coerced to v2 (`__init__.py:1118-1150`).
**Resolver:** `execution_runtime.resolve_execution_mode` — precedence request-captured > env (locked) > persisted > default v2. Aliases `legacy→v1`, `shadow` accepted internally, never exposed.
**Dispatch branches:** **none found.** No runtime code branches execution on the resolved mode; `is_v2()`/`is_shadow()` have zero callers outside `execution_runtime.py`. The mode is *recorded*: frozen into queued requests (`__init__.py:4084-4104`), `studio_meta.execution_mode` (`studio_run_adapter.py:1402`), compilation metadata, and `modal_options.execution_mode` stamped by frontend `loadModalOptions()`. Shadow remnant: `studio_workflow_run.py:1556` hardcodes `"execution_mode": "v1"` as metadata default in the workflow-single compilation dict (metadata-only mislabel; flagged for H2).
**Labels:** "V2 - Recommended"/"V1 - Legacy fallback" (modern), "Managed by COMFYMODAL_RUNTIME" (locked), readiness line "V1 deployment: … V2 deployment: …".
**Consumers:** readiness display; plan/run metadata; diagnostics. Local/Cloud vocabulary is separate (Run mode, L8) and only gates the canvas interception.

---

## 5. LEGACY SETTINGS INVENTORY (delta over F4/F8 — F4 remains historical truth)

| Setting (legacy-panel reachability) | Key / route | Persistence authority | Modern consumer | Legacy-only consumer | Status |
|---|---|---|---|---|---|
| GPU | `comfymodal_gpu` LS cache + POST `/config {gpu}` | server `.modal_settings.json["gpu"]` | modern Settings display/reset | legacy panel display | KEEP (F8); LS = display cache |
| Output ×5 + preview ×3 | LS keys + `/config` | server | modern Outputs section | legacy panel | KEEP; single shared helper |
| Execution engine | `execution_mode` | server | modern Generation select stamps `modal_options` | legacy select | duplicated UI writer; retire one in H2 wave |
| Run mode Cloud/Local | `comfymodal_enabled` | localStorage only | **none** (canvas only) | legacy panel toggle + modern General segment | duplicated writer; semantics H2 |
| Production toggle | `comfymodal_production` | localStorage + graph extra | canvas production extension reads LS fallback | legacy panel toggle | KEEP while canvas path exists |
| Deploy status/log/trigger, workspace swap, manifest repair, warmup | `/deploy/*`, `/workspaces*`, `/manifest*`, `/deploy-warmup/*` | `.deployed_state.json`, `.deploy_log`, `.deploy_warmup_state.json`, `.modal_workspaces.json` | status row only (modern Settings shows deploy state text) | legacy panel controls | RE-HOME candidates (no modern control exists) |
| Model inject/inject-all/batch-install/download progress | `/models/inject*`, `/models/batch-install`, `/model/install`, `/download/*` | Modal volume state | Model Library install-request (per-item) | legacy panel bulk flows | RE-HOME candidates |
| Heavy tracing | `comfymodal_heavy_tracing` LS + `/profile/level` | server effective/persisted | modern Advanced section | (legacy panel has none) | KEEP (F4A model) |
| Stale keys | `comfymodal_global_concurrency`, `comfymodal_preview_auto_save`, `window._comfyModalGpu` | — | — | — | already removed (F4A/F4B); verified absent |

No new stale keys found beyond those F4 already removed. `window._comfyModalExecutionMode` is NOT stale (carried into `modal_options.execution_mode`).

---

## 6. LEGACY CANVAS / COMPARISON — WHAT THEY ACTUALLY ARE

**"Legacy canvas"** = the pre-Studio direct path: `modal-node.js` patches `api.fetchApi` so every canvas Generate (POST `/prompt`) is redirected to `/comfymodal/prompt` with output options, production trace, timing fields, and benchmark capture attached; gated by `window._comfyModalEnabled !== false` (the Run-mode toggle, L8). It is **still real user functionality** — the only way to execute an arbitrary ComfyUI graph through Modal — and the Progress bar + Production marking ride on it. It is partially duplicated by Studio runs (which compile presets/workflow versions server-side) but is NOT replaceable by them. Keyboard shortcuts: none added (ComfyUI defaults). Tests: tracker/timing suites. Verdict: KEEP (product surface), with its output-options global coupling documented below.

**"Comparison"** = three coupled pieces:
1. Backend `comparison.py` + `/comparison/*` routes: profile CRUD (schema v2, stored under `user/default/comfy-modal/comparison_profiles/<id>/…`), detect-slots, validate, run, results, gallery, config.
2. `modal-comparison.js`: Profiles/Runner overlays + hidden sidebar tabs + **always-on canvas context-menu slot mapping** (L4).
3. Consumers: Legacy Setup tab creates/validates profiles; Legacy Profiles tab edits them; Legacy Dashboard opens the overlays; Runner reads `window._comfyModalOutputOptions` (line 1163) for output options.
History dependency: none (comparison results live in their own store, not run-history). Navigation entry points: Legacy Dashboard buttons + programmatic window globals. Verdict: **still real functionality with NO modern replacement** (Workflow Portability analyzes; it does not execute A/B runs). RE-HOME the management UI; the canvas context menu either moves with it or is explicitly kept as the canvas-side entry.

---

## 7. BACKEND/API SURFACE INVENTORY (classification; nothing deleted)

**MODERN_CANONICAL:** `/history-v2/**` (feed, generations+actions, experiments create/status/start/cancel/resume/cell-retry, assets GET/export, favorite/note/featured) · `/studio/workflows**` incl. versions/mapping/presets/portability/export/import-manifest · `/studio/models**`, `/studio/custom-nodes**`, version dependencies/compatibility · `/studio/run` (workflow branch), `/studio/experiment-v2` · `/studio/snapshots**`, `/studio/presets**` (snapshot-presets; modern Playground/Backend authority) · `/config` GET/POST · `/profile/level` · `/studio/outputs/{filename}`.

**LEGACY_STILL_CONSUMED (by any UI incl. legacy tabs/modern hydration):**
- `/history` unified feed — modern Playground recent-runs + bridge repo.
- `/run-history?limit=` — Playground recent-runs, testing-history.
- `/run-history/{id}` GET — bridge repo.
- `/run-history/{id}/annotations` PATCH — bridge repo; migration source (F2).
- `/experiments` GET — Playground recent-runs, testing-results picker.
- `/experiments/{id}` GET, `/experiments/{id}/stop-now` — Playground run-status poll + cancel (single AND legacy-surface experiment), testing-results.
- `/experiments/{id}/{pause|stop-after-current|resume|run-missing}`, `/events`, checkpoints/* , cells/*/rerun, rerun-selected, clone, compile — Legacy Results/Setup only.
- `/studio/experiment` POST — Playground legacy experiment surface (L6).
- `/comparison/**` — Legacy Profiles/Setup/Dashboard + canvas context menu.
- `/presets/prompts**`, `/presets/images**` — Legacy Setup only.
- `/studio/backends**` — Backend page discovery/import + Settings counts row.
- `/assets/{asset_id}` — asset URL builder shared by normalizer/testing-results.
- `/deploy/status` — modern Settings status row.
- `/benchmark/workflow` POST — silent canvas capture.

**LEGACY_UNUSED (no remaining UI caller found):**
- `/run-history/{id}/save` POST — its only frontend callers were `studio-history.js` (orphan L11) via `saveRunOutput`; bridge does not call it. Route retained deliberately (F3 rejected reusing it for V2 export); classify UNUSED-by-UI, keep for old-record compatibility until H-wave storage decisions.
- `/run-history/{id}/logs`, `/run-history/{id}/timing` — no web/ caller found (diagnostic tooling may use them) → UNKNOWN-leaning-unused.
- `/cancel/{client_id}` DELETE, `/result/{prompt_id}`, `/object_info`, `/health`, `/sync/*`, `/runtime/*`, auth/token routes — infrastructure/runtime-project surface, out of Phase-H product scope (do not touch in consolidation waves).

**COMPATIBILITY_INTERNAL:** `/studio/backends` persistence (`.studio_backends.json`) — comment-documented bridge; comparison-profile discovery folded into backends list.

**UNKNOWN:** none material.

Special attention — routes WITH modern equivalents: `/history`↔`/history-v2/feed`; `/run-history/{id}/annotations`↔`/history-v2/*/favorite|note`; `/run-history/{id}/save`↔`/history-v2/assets/{id}/export`; `/experiments/*` lifecycle↔`/history-v2/experiments/*`; `/presets/prompts|images`↔Workflow Presets (different semantics — not equivalents, do not merge); `/studio/backends`↔presets (import-only equivalence).

---

## 8. STORAGE INVENTORY

| Store | Kind | Role | Active writer? | Writer removable? | Storage itself removable? |
|---|---|---|---|---|---|
| `.studio_workflows/versions/mappings/presets.json` | JSON (plugin root) | SOURCE OF TRUTH (G authority chain) | yes (modern) | NO | NO |
| `.studio_model_library.json`, `.studio_custom_nodes.json` | JSON | dependency evidence authorities | yes | NO | NO |
| `.studio_portability_reports.json` | JSON sidecar | DERIVED-ONLY cache (G10/11) | yes | n/a (regenerable by design; may be deleted anytime — G §38.8) | YES (derived) |
| `.studio_snapshots.json`, `.studio_presets.json` | JSON | snapshot/preset authority for Playground/Backend | yes | NO | NO |
| `.studio_backends.json` | JSON | compatibility bridge store | yes (routes) | YES (Wave 3/4) | keep read-only afterwards (existing manual rows) |
| History V2 `comfymodal-data/.studio_history_v2/history_v2.db` | SQLite | History authority (rows carry workflow_id/version_id/preset_id; RequestSnapshots w/ execution_plan_json) | yes | NO | NO |
| data-root `run-history/` (legacy JSON records) + derived `.history_index.db` | JSON+SQLite | legacy generation records; ONE-WAY migration source into V2; still READ by Playground hydration & bridge | yes (new legacy-format runs still recorded by `/comfymodal/prompt`-adjacent paths & legacy experiment surface) | writer retires only when legacy execution surfaces retire | NO — historical generations must remain viewable/honest (F invariant) |
| data-root `experiments/` (legacy aggregate experiments) | JSON | legacy experiment records rendered by Legacy Results + History legacy kinds | yes (while L6/L1 alive) | YES (with L6 retirement) | NO — old records stay readable |
| `.presets/prompts|images` | JSON dirs | legacy experiment prompt/image presets | yes (Setup tab) | YES (with Setup retirement/re-home) | keep for existing user presets |
| `user/default/comfy-modal/comparison_profiles/` + comparisons dir | JSON files | Comparison profiles/results authority | yes | NO (until Comparison is re-homed or killed as product decision) | NO |
| `.modal_settings.json` | JSON | canonical control-plane settings (gpu, execution_mode, output×5, preview×3) | yes | NO | NO |
| `.modal_workspaces.json`, `.deployed_state.json`, `.deploy_log`, `.deploy_warmup_state.json`, `.model_manifest.json`, `.profile_config.json` | JSON | deploy/workspace/profiler infra | yes | out of H product scope | NO |
| `.experiment_leases.db` | SQLite | lease registry (E) | yes | NO | NO |
| localStorage `comfymodal_enabled` | LS | Run mode (canvas gate) | modern Settings + legacy panel | one writer can be removed (H2) | keep (canvas reads it) |
| localStorage `comfymodal_gpu`, output×6, preview×3, `comfymodal_heavy_tracing`, `comfymodal_production` | LS | caches/selection mirrors | both surfaces via shared helpers | NO | keep |
| localStorage `comfymodal.studio.playground.*`, `comfymodal.studio.experiment.*`, `comfymodal.history.v2.viewstate`, `comfymodal-studio-history-columns` | LS | durable namespaces — explicitly OUTSIDE reset set (F4A) | modern | NO | NO |
| localStorage `comfymodal_setup_draft`, `comfymodal_comparison_runner_*`, `_selected_profiles`, `_profiles_tab` | LS | legacy tab drafts/state | legacy tabs only | YES (with tab retirement) | values are disposable drafts; removal OK after grace |
| sessionStorage `_comfymodal_redeploy_restart_done` | SS | redeploy banner | legacy panel | with L2 | disposable |

Key principle honored: **"legacy UI removable" ≠ "legacy data deletable."** Every legacy store above holds either migration-source records (run-history), still-renderable history (legacy experiments), or user-authored content (comparison profiles, prompt/image presets).

---

## 9. TEST OWNERSHIP (protecting legacy behavior; no tests modified)

| Test | Protects | Classification |
|---|---|---|
| `tests/test_testing_setup_js.py`, `test_testing_profiles_js.py`, `test_testing_results_js.py`, `test_testing_settings_js.py` (gate) | structure of legacy tab modules | can be removed when their surface retires |
| `tests/test_testing_shell_integration.py` (gate, 100KB) | shell wiring + **studio-history.js structural rules** (lines 1099, 1171-1183, 1845-1882) | split: shell parts KEEP; studio-history.js parts removable with L11 |
| `tests/test_testing_ui_wired.py` (gate) | cross-module wiring incl. legacy | prune with surface |
| `tests/test_presets_prompts.py`, `test_presets_images.py` (gate) | legacy prompt/image preset stores | rewrite against whatever re-homes them; until then KEEP |
| `tests/test_run_history.py`, `test_run_history_save.py`, `test_task2_run_history_extensions.py` (NOT in gate registration) | legacy run-history routes/store | still protects required compatibility (bridge/migration) — consider registering or explicitly declaring out-of-gate |
| `tests/test_modal_settings_gpu_config.py` (gate) | legacy panel GPU server-first/no-POST-on-open | protects required compat until L2 retires; then remove |
| `tests/studio_legacy_settings_authority_unit.mjs` (**exists but NOT registered in NODE_UNIT_FILES — gate gap**) | F4B legacy panel authority alignment | should be rewritten against modern surface OR registered; flag to H5 |
| `tests/studio_phase_f4_settings_authority_unit.mjs` (gate) | modern settings authority guard | KEEP |
| e4c/e4d unit `.mjs` bridge-mode assertions | bridge repository refusal semantics | KEEP while bridge exists |
| `tests/browser/fake/studio-fake-experiments.spec.mjs`, `studio-fake-phase-e*.spec.mjs` | include legacy-surface experiment flows via fake | classify per flow at retirement time |
| `tests/test_comparison_extended_mappings.py`, `test_comparison_loader_groups.py` (not gate-registered) | comparison backend | KEEP while Comparison is a product |
| `test_image_packaging_refactor.py` | runtime mount ignore-list must NOT exclude modal-*.js | KEEP (guards entry-point packaging) |

---

## 10. RETIREMENT CLASSIFICATION TABLE

Classifications: RETIRE (modern replacement complete, no valid consumer) · RE-HOME (valuable, belongs elsewhere) · KEEP (intended modern product) · COMPATIBILITY-SHIM (UI can go, read/API/storage compat remains) · UNKNOWN.

| Item | Current role | Modern replacement | Consumers | Data dependency | Classification | Deletion blockers | Suggested H owner lane |
|---|---|---|---|---|---|---|---|
| `web/studio-history.js` | orphaned legacy History page | studio-history-v2 | NONE (imports-only by tests) | none (reads only) | **RETIRE** | its gate tests (test_testing_shell_integration, test_studio_timing_integration reference `formatPageMetadata`/`buildWaterfallLines`/`renderHistory` source) must move/be deleted first; shared LS column key already owned by V2 | Wave 1 |
| Legacy tab: History (testing-history.js) | read-only recent runs | History V2 page | Legacy group click | none | **RETIRE** | trivial | Wave 1 |
| Legacy tab: Dashboard (testing-dashboard.js) | launchpad to other legacy tabs | shell nav itself | Legacy group | none | **RETIRE** | none (buttons point at things being retired/re-homed) | Wave 1 (after its targets) |
| Legacy tab: Results (testing-results.js) | monitor/control legacy aggregate experiments | History V2 experiment detail (modern records only) | Legacy group; documents legacy experiments | renders OLD experiment records | **COMPATIBILITY-SHIM** (view) / RETIRE controls once legacy creation stops | old experiment records must stay viewable somewhere or be declared read-only-frozen | Wave 2/3 decision |
| Legacy tab: Setup (testing-setup.js) | compile/create legacy experiments; manage prompt/image presets; create comparison profiles | modern experiment-v2 (different definition contract); Workflow Presets (different concept) | Legacy group | writes legacy experiments + .presets | **RE-HOME** (profile creation → Comparison home) then RETIRE experiment-creation path per H2/H4 product call | legacy experiment creation is the only writer of a still-live store | Wave 2 (with H2/H4) |
| Legacy tab: Profiles (testing-profiles.js) | comparison profile editor | none | Legacy group; Backend-page "configure via Settings > Legacy > Profiles" hint string | comparison profile files | **RE-HOME** (Comparison management) | unique editor | Wave 2 |
| Legacy tab: Settings (testing-settings.js → mountSettingsPanel) | hosts legacy panel inside Settings | modern Settings covers most | Legacy group + Open Legacy Settings button | none | **RETIRE after RE-HOME** of deploy/model-inject controls | deploy + model download controls have no modern home | Wave 2 |
| Legacy Settings overlay/global (`open_comfymodal_settings`, modal-settings.js panel) | standalone legacy control panel | modern Settings (partial) | sidebar button, dashboard, testing-settings, window global | writes via shared helper | **RE-HOME** deploy/workspace/model-inject clusters → RETIRE remainder | same as above; F4B tests | Wave 2 |
| Hidden legacy sidebar tabs (modal-gpu, comparison-*) | opt-in duplicates | shell | opt-in scripts only | none | **RETIRE** | confirm zero users of `__comfyModalEnableLegacySidebarTabs` (repo-wide: only definitions) | Wave 1 |
| Comparison canvas context menu (slot mapping) | maps canvas nodes→profile slots | none | canvas users | profile slots | **RE-HOME/KEEP** (product decision; only canvas-side Comparison entry) | none technical | Wave 2 (with Comparison home) |
| Comparison overlays + backend | A/B execution product | none (Portability is analysis-only) | Legacy Dashboard, globals | comparison stores | **KEEP** pending product decision; RE-HOME entry point | unique capability | Wave 2 |
| Legacy experiment surface in Playground (L6) | preset-matrix experiments | experiment-v2 | Playground fallback state | legacy experiments store | **RETIRE** after H2 defines run-mode/preset story; until then freeze | H2 owns Run-mode semantics; store readability | Wave 2/3 (H2-dependent) |
| V1 engine option (Settings + legacy panel) | selectable fallback engine label | V2 default | settings writers; metadata consumers | `.modal_settings.json["execution_mode"]` | **RETIRE the option** (keep resolver reading old persisted values = shim) per F deferral #1 | H2 owns; persisted "v1" values must normalize sanely; `studio_workflow_run.py:1556` hardcoded "v1" metadata remnant to fix in same lane | Wave 2 (H2) |
| Run mode Cloud/Local control | gates canvas interception | none | canvas only | LS only | **UNKNOWN → H2** (either define modern semantics or re-home as canvas setting) | canvas behavior change risk | Wave 2 (H2) |
| Canvas `/prompt` interception + progress bar + Production mode | core canvas-through-Modal product | none | every canvas user | output-option globals | **KEEP** | is the product's second execution surface | — (KEEP) |
| Bridge repository (`mode:"bridge"`) | legacy-endpoint adapter inside V2 repo | v2 repo | programmatic/tests only | none | **RETIRE** (unreachable in production) | e4c/e4d assertions; `HISTORY_V2_MODES` contains it | Wave 3 |
| `/run-history/{id}/annotations` PATCH | legacy annotation writer | V2 favorite/note | bridge; migration source | run-history records | **COMPATIBILITY-SHIM** (F2 froze it for bridge) | one-way migration semantics; old records editable? product call | Wave 3/4 |
| `/history`, `/run-history` list/detail GETs | legacy feeds | V2 feed | Playground hydration, bridge, testing-history | index db | **COMPATIBILITY-SHIM** until Playground hydration re-homes to V2; then shim for old records | recent-runs feature parity | Wave 3 |
| `/run-history/{id}/save` | legacy export writer | V2 export route | none (UI) | export copies on disk | **COMPATIBILITY-SHIM/UNUSED** | old exported-copy provenance | Wave 3/4 |
| `/experiments/*` legacy lifecycle routes | legacy experiment control | V2 experiment routes | Legacy Results, Playground poll/cancel | legacy experiments store | **COMPATIBILITY-SHIM** while legacy records viewable; RETIRE with L6 | record readability | Wave 3 |
| `/studio/backends` routes + `.studio_backends.json` | import/discovery bridge | presets | Backend page, Settings counts | manual rows | **COMPATIBILITY-SHIM** → eventually fold discovery into presets/model-library | disabled_reason UX references Legacy Profiles | Wave 3/4 |
| `/presets/prompts|images` + `.presets/` | legacy experiment presets | none equivalent | Setup tab | user presets | **RE-HOME or RETIRE-with-Setup** | user data | Wave 2/4 |
| `window._comfyModalOutputOptions` fallback chain | carries output prefs to canvas/Comparison readers | shared helper maintains it | modal-node, comparison runner | none | **KEEP** (F deferral #4; single maintenance point already) | canvas correctness | — |
| `execution_runtime.is_v2/is_shadow` | unused helpers | — | none | none | **RETIRE** (dead code) | none | Wave 1 |
| `MODE_SHADOW` alias acceptance | input normalization | — | resolver | persisted values | **KEEP** (normalizer) | stored values | — |

---

## 11. HARD SAFETY INVARIANTS — SURFACES WHOSE DELETION COULD VIOLATE THEM

Per G §37/§38 and F §7:

1. **History V2 rows + RequestSnapshots** — retiring V1 UIs must not touch `history_v2.db`; rows referencing `workflow_id/workflow_version_id/preset_id` must stay resolvable-or-honestly-stale. ⚠️ Deleting the **legacy experiments store** or its reader (Legacy Results) would orphan nothing in V2 (disjoint stores) — safe; deleting **run-history records** would break "old historical generations remain viewable."
2. **Immutable WorkflowVersion / Mapping / Preset chain** — none of the retirement candidates writes these stores; guard: Wave lanes must not "clean up" `.studio_workflow_*.json`.
3. **Manifest portability exactness** — G §38.6: legacy snapshots/presets pages and legacy canvas must never grow portability computation or alternate codecs. Retirement must not push Export/Import anywhere else.
4. **Portability cache derived-only** — `.studio_portability_reports.json` relocation only beside domain stores.
5. **Modern Settings authority (F4/F8)** — removing the legacy panel must migrate its UNIQUE controls first (deploy, workspace swap, model batch download); removing shared ones is safe because both surfaces already share `studio-output-preferences.js` and `/config`.
6. **Legacy irreproducible generations stay honestly irreproducible** — keep `replay_capable=false` truthfulness; do not delete run-history snapshots that make some rows replayable.
7. **No stored-graph rewriting because a UI retires** — e.g., do not "upgrade" legacy experiment records or comparison profiles when their editors move.
8. **Highest-risk single deletion:** the **legacy run-history store or its read routes** (breaks historical viewability + migration-source semantics), and secondarily **`/studio/backends` hard-delete** (Backend page currently calls it on every render — would break a modern page, proving "legacy-labeled" ≠ "unconsumed").

---

## 12. RECOMMENDED IMPLEMENTATION WAVES (evidence-derived; no runnable prompts)

**Wave 1 — obvious dead/unreachable frontend surface (lowest risk):**
- Delete `web/studio-history.js` + relocate its pure helpers (`formatPageMetadata`, `buildWaterfallLines`, `resolveTotalCount`) if still tested, and prune its structural tests.
- Remove hidden legacy sidebar-tab registrations (`__comfyModalEnableLegacySidebarTabs` blocks) in modal-settings.js/modal-comparison.js.
- Remove dead `is_v2`/`is_shadow` helpers (or register callers—none exist).
- Register-or-remove `tests/studio_legacy_settings_authority_unit.mjs` gate gap (H5 coordination).
- Retire Legacy **Dashboard** and Legacy **History** tabs (pure launchers/read-only views).

**Wave 2 — re-home still-needed controls (needs design/product input):**
- Re-home Comparison management (Profiles editor + Runner entry) out of the Legacy group; decide canvas context-menu ownership.
- Re-home deploy/workspace/manifest-repair/warmup + model batch-download controls from the legacy panel into modern surfaces (Backend page or new System section).
- H2-dependent: V1 engine option removal + `execution_runtime` persisted-"v1" normalization + fix `studio_workflow_run.py:1556` "v1" metadata remnant; Run-mode Cloud/Local semantics decision.
- Decide legacy experiment creation (Setup tab) fate with H2/H4.

**Wave 3 — route/API compatibility cleanup:**
- Retire bridge repository mode; collapse `HISTORY_V2_MODES`.
- Re-home Playground recent-runs hydration onto `/history-v2/feed` (removes modern dependence on `/history`+`/run-history`+`/experiments` GETs), then demote those to shims.
- Playground legacy-experiment poll/cancel switch (or retirement with L6).
- Fold `/studio/backends` discovery into a modern route; keep old route read-only.

**Wave 4 — storage/write-authority retirement:**
- Stop writing `.studio_backends.json` (read-only compat).
- Stop new legacy experiment/preset writes once creators retire; keep readers.
- Decide `/run-history/{id}/annotations` writability (freeze vs keep) — requires product call on editing old records.
- Only after Waves 1–3: declare which stores are frozen archives.

**Wave 5 — test consolidation:**
- Delete/prune tests of retired surfaces (§9 rows); rewrite legacy-panel authority tests against surviving surfaces; reconcile unregistered legacy test files (`test_run_history*`, comparison tests) into the gate or an explicit out-of-gate registry.

Ordering rationale: each wave strictly shrinks the consumer set of the next; no wave requires data migration; Wave 2 contains every item with a product decision attached (H2 dependencies isolated there).

---

## 13. EXACT ITEMS SAFEST TO REMOVE FIRST vs MUST-NOT-REMOVE-YET

**Safest first (zero production consumers, verified by reverse-import/route sweeps):**
1. `web/studio-history.js` (zero importers).
2. Hidden legacy sidebar-tab registrations (flag-gated off by default).
3. Legacy Dashboard tab + Legacy History tab (launcher/read-only, self-contained).
4. `execution_runtime.is_v2` / `is_shadow` (zero callers).
5. Bridge repository mode (programmatic-only; tests updated in same lane).

**MUST NOT be removed yet:**
1. Anything touching `history_v2.db`, the four workflow domain stores, or `.studio_portability_reports.json` semantics.
2. Legacy run-history store + `/history` + `/run-history*` GETs + annotations PATCH (migration source; Playground hydration still reads; old generations must stay viewable).
3. `/studio/backends` routes (modern Backend page + Settings counts consume them today).
4. Canvas `/prompt` interception, output-options global chain, Production mode (only canvas execution path; F deferral #4).
5. Comparison backend + profiles editor (unique capability, no replacement).
6. Deploy/workspace/model-download controls (no modern home yet).
7. V1 option/remnants **until H2 rules** (H1 maps only).
8. `window._comfyModalEnabled` / Run-mode key (sole gate for canvas path; H2 owns semantics).

---

## FINAL NOTES

- Gate baseline assumed: Python 1991 / Node 21 / Fake Playwright 192 (G closure). This batch ran no tests and modified nothing.
- Discovered gate gap worth carrying forward: `tests/studio_legacy_settings_authority_unit.mjs` exists but is not in `NODE_UNIT_FILES`; `test_run_history*.py` and comparison tests are outside `STUDIO_PY_MODULES`.
- All classifications cite measured consumers; where evidence was insufficient (Run-mode semantics, legacy-experiment product fate), the item is UNKNOWN and explicitly routed to H2/H4 rather than guessed.
