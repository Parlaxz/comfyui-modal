# PHASE H7 — WORKFLOWS MODEL LIBRARY PARITY & LEGACY MODELS/SYNC RETIREMENT READINESS (2026-08-23)

**Batch:** H-WAVE A3 implementation (L-WF Model Library lane). Additive parity only. No deploy, no Modal run, no GPU, no live generation, no installs, no commit/push/branch/worktree/reset. Legacy Models/Sync UI left intact. Backend UI, Settings, Experiment mode, History, portability rules untouched.

**Authoritative inputs:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (§10.1/§10.2/§24/§25 A3), H1 §3/§5, H4 §2/§10 (items 8–9), Phase G handoff invariants.

---

## 0. VERDICT

`H7 COMPLETE — MODEL LIBRARY PARITY CLOSED FOR ALL LIBRARY/DEPENDENCY CAPABILITIES; LEGACY MODELS/SYNC REDUNDANT FOR THOSE CAPABILITIES AND READY FOR WAVE E/G PENDING THE BACKEND-OPERATIONAL HANDOFF SET.`

18 legacy Models/Sync actions classified (table §1). 4 capabilities ALREADY_MODERN (verified, not assumed). 4 real parity gaps implemented additively in Workflows using EXISTING backend routes (zero route changes). 4 RETIRED per frozen default. 10 classified BACKEND_OPERATIONAL and handed to H6/Backend. No automatic installs anywhere; proven by tests.

---

## 1. COMPLETE LEGACY MODELS/SYNC OPERATION TABLE

Sources: `web/modal-settings.js` (legacy panel), `__init__.py` route handlers, `model_library_routes.py`, `web/studio-model-library.js`, `web/studio-workflows.js`.

### 1a. Legacy MODELS section (`modal-settings.js:3400–3446`)

| # | Legacy UI action | Route | Storage | Modern equivalent (Workflows) | Behavior difference | Classification | Decision |
|---|---|---|---|---|---|---|---|
| M1 | Browse models list (`loadModels` :838) | `GET /comfymodal/models` | Modal **remote volume** live listing + local-placeholder state | Model Library list `GET /studio/models` over `.studio_model_library.json` | Different data domain: remote volume inventory vs canonical local library records (hash/provenance/notes) | **BACKEND_OPERATIONAL** | Remote-volume inventory is deployment state → H6/Backend verdict; not duplicated in Workflows |
| M2 | Per-model "Create local" placeholder (:956) | `POST /comfymodal/models/inject` | local 0-byte placeholder files | none | Canvas-dropdown integration for remote-only models | **BACKEND_OPERATIONAL** (H5 §10.2: inject = RETIRE as duplicate UI; operational remote-volume bootstrap if genuinely required) | Handed off; NOT implemented in H7 |
| M3 | "Create All Placeholders" (:3422) | `POST /comfymodal/models/inject-all` | same as M2 | none | Bulk variant of M2 | **BACKEND_OPERATIONAL** / duplicate-UI RETIRE | Handed off |
| M4 | Delete model from volume (✕ :985) | `DELETE /comfymodal/models/{folder}/{filename}` | remote volume + placeholder cleanup | none | Destructive volume operation | **BACKEND_OPERATIONAL** | Handed off |
| M5 | Models "Refresh" button (:3420) | `GET /comfymodal/models` | — | "Scan models" (`POST /studio/models/rescan`) + list reload | Modern refreshes the CANONICAL library, not the remote volume | **ALREADY_MODERN** (library truth) | None |

### 1b. Legacy ADD MODEL section (`modal-settings.js:3448–3700`)

| # | Legacy UI action | Route | Storage | Modern equivalent | Behavior difference | Classification | Decision |
|---|---|---|---|---|---|---|---|
| A1 | Single "Download" (:3534) | `POST /comfymodal/model/install` | Modal volume | Explicit install REQUEST `POST /studio/models/install-request` (detail dialog) | Legacy executes the download; modern records approval only (operator executes) | **RETIRE** raw downloader (H5 §10.1/§24); approval flow **ALREADY_MODERN** | Not reproduced; download-execution documented as deployment-operational |
| A2 | "+ Add to Batch" queue + "Download Batch" (:3579/:3629) | `POST /comfymodal/models/batch-install` | Modal volume | Dependency-driven per-item install request | Mass download vs explicit per-item approval | **RETIRE** (frozen default; no code evidence of a required gap) | Not reproduced |
| A3 | Download progress bar/polling (:3505) | `GET /comfymodal/download/status/{id}`, `/download/active` | transient | none | Raw-pipeline telemetry | **RETIRE** (rides A1/A2) | Not reproduced |
| A4 | "Get Download Progress" resume (:3460) | `GET /comfymodal/download/active` | — | none | Same pipeline | **RETIRE** | Not reproduced |

### 1c. Legacy manifest operations (workspace section, `modal-settings.js:2079–3149`)

| # | Legacy UI action | Route | Storage | Modern equivalent | Behavior difference | Classification | Decision |
|---|---|---|---|---|---|---|---|
| F1 | Manifest Repair (:2079/:2411) | `POST /comfymodal/manifest/repair/scan\|apply\|delete-placeholder` | `.model_manifest.json` | none | Deployment-bootstrap repair | **BACKEND_OPERATIONAL** (H5 §10.2: KEEP_AND_REHOME_BACKEND pending non-obsolescence proof) | H6 owns the verdict; NOT moved into Workflows |
| F2 | Export Workflow Manifest (:2084/:3105) | `POST /comfymodal/workflow-manifest/export` | manifest JSON | Workflows Portability Export (`GET /studio/workflows/versions/{id}/export`) | Version-scoped canonical export incl. presets choice | **ALREADY_MODERN** | None |
| F3 | Import Workflow Manifest (:2089/:3126) | `POST /comfymodal/workflow-manifest/import` | workflow stores | Workflows Import manifest dialog (`POST /studio/workflows/import-manifest?dry_run=` with preview) | Dry-run preview + atomic import are modern | **ALREADY_MODERN** | None |
| F4 | Install from Manifest (:2093/:2941) | `POST /comfymodal/manifest/install` | volume + manifest | per-item install request only | Bulk workspace bootstrap during swap/deploy | **BACKEND_OPERATIONAL** | Handed off to H6/Backend |

### 1d. Legacy SYNC section (`modal-settings.js:3151–3397`)

| # | Legacy UI action | Route | Storage | Modern equivalent | Behavior difference | Classification | Decision |
|---|---|---|---|---|---|---|---|
| S1 | "Refresh Status" (:3167) | `GET /comfymodal/sync/status` | live local-vs-remote compare | Custom-node registry truth `GET /studio/custom-nodes`; model presence via library | Sync-status compares UPLOAD state against the remote volume; installed-truth portion is modern | Split: installed-truth **ALREADY_MODERN**; upload-compare **BACKEND_OPERATIONAL** | Registry browse added (gap C1 below); upload-compare handed off |
| S2 | "Sync Models" upload (:3174) | `POST /comfymodal/sync/models` | remote volume | none | Uploads local models to the volume | **BACKEND_OPERATIONAL** | Handed off |
| S3 | "Sync Custom Nodes" (:3185) | `POST /comfymodal/sync/custom-nodes` | remote volume + deploy | none | Packages + uploads + deploys | **BACKEND_OPERATIONAL** | Handed off |
| S4 | "Resync Remote Runtime" (:3196) | `POST /comfymodal/runtime/resync` | running runtime | none | Reloads the running Modal ComfyUI | **BACKEND_OPERATIONAL** | Handed off |
| S5 | Runtime stale check (:3207) | `GET /comfymodal/runtime/state` | runtime | none | Staleness readout | **BACKEND_OPERATIONAL** | Handed off |

**Totals:** 18 actions — ALREADY_MODERN 4 (M5, F2, F3, S1-installed-truth) · implemented parity gaps 4 (§2) · RETIRE 4 (A1–A4) · BACKEND_OPERATIONAL 10 (M1–M4, F1, F4, S1-upload-compare, S2–S5) · COMPATIBILITY_ONLY 0 new · UNKNOWN 0.

---

## 2. IMPLEMENTED PARITY GAPS (all additive, zero backend changes)

Verified missing before implementation (route + API client existed with ZERO UI callers, or data loaded but never rendered):

| Gap | What was added | Where | Backend route used (pre-existing) |
|---|---|---|---|
| C1 Custom-node registry browse | "Custom nodes" section in Model Library: canonical registry rows (name, Installed badge, commit provenance, class count, install path, repo link) + count. `md.customNodes` was loaded since earlier phases but never rendered. | `web/studio-model-library.js` (`renderCustomNodesSection`, `renderRegistryNodeRow`) | `GET /studio/custom-nodes` |
| C2 Custom-node registry refresh | Explicit "Refresh registry" button → loading state → authoritative list refresh → success/failure message. Dedupe: in-flight clicks ignored. Never fires on render. | `web/studio-model-library.js` (`handleNodesRefresh`) | `POST /studio/custom-nodes/refresh` |
| C3 Custom-node install request | "Request install" on MISSING dependency node rows (requires `repository_url`). Records approval ONLY — inline note states "Approval recorded — nothing was installed." Click-gated; deduped while in flight. | `web/studio-model-library.js` (`renderNodeInstallRequestControl`) | `POST /studio/custom-nodes/install-request` |
| C4 Dependency→Library handoff | "Find in library" on missing model dependency rows opens the SINGLE Model Library view with the search prefilled to the filename (one-shot refetch via `_queryDirty`). No second model-management UI, no deep-link infrastructure (Phase-I boundary respected). | `web/studio-model-library.js` (`renderDependencySection` opts) + `web/studio-workflows.js` (`openModelLibraryFiltered`) | `GET /studio/models?search=…` |

**Backend route changes: NONE.** Every gap is served by existing canonical routes (`model_library_routes.py` untouched). No second registry, no localStorage authority, no URL/deep-link infra.

Also fixed within the owned file (required by the §5 behavior contract "success/failure message"): the pre-existing rescan status line was destroyed by the post-scan full re-render; both rescan and registry-refresh outcomes are now written to the freshly rendered status element.

---

## 3. EXPECTED-MODERN-CAPABILITY VERIFICATION (proved, not assumed)

| Capability | Status | Evidence |
|---|---|---|
| Browse registered models | ✅ pre-existing | `renderModelLibraryView` list over `GET /studio/models` |
| Search/filter (query/type/state) | ✅ pre-existing | toolbar + `_modelQuery` server-side filtering |
| Model detail | ✅ pre-existing | detail dialog (metadata + editable fields) |
| Presence/install state | ✅ pre-existing | Installed/Missing badges (rows, filters, dependency rows) |
| Model hash/provenance | ✅ pre-existing | row hash chip + detail metadata (hash/provider/revision/dates) |
| Rescan/refresh (models) | ✅ pre-existing | "Scan models" + Full-rehash option; explicit-only (pinned by test) |
| Notes | ✅ pre-existing | notes/tags/source-URL editing in detail dialog |
| Dependency context from Version | ✅ pre-existing | `renderDependencySection` over `GET …/dependencies` |
| Custom-node dependency rows | ✅ pre-existing | state/commit/required-revision/path/repo columns |
| Custom-node provenance/status | ➕ now browsable | Gap C1 (registry section) |
| Registry refresh/rescan (nodes) | ➕ now exposed | Gap C2 (was route-only) |
| Node install request | ➕ now exposed | Gap C3 (was route-only) |
| Dependency→library path | ➕ now present | Gap C4 (§11-preferred pattern) |

---

## 4. SAFETY — NO-AUTO-INSTALL PROOF

- **No install on page load:** mounting the Model Library issues exactly three GETs (models, types, custom-nodes) and ZERO POSTs — pinned by unit test 8.
- **Rescan/refresh explicit-only:** `POST /models/rescan` and `POST /custom-nodes/refresh` fire only from their buttons (tests 5, 6+14); double-click dedupe proven.
- **Install requests require user action:** model "Request download" remains inside the detail dialog with its "never fetched from here" disclosure; node "Request install" fires one POST per explicit click and renders "nothing was installed" (test 7a; fake spec asserts exactly 1 request POST after click).
- **No automatic batch install:** modern modules reference none of `/models/batch-install`, `/model/install`, `/download/status`, `/sync/models`, `/runtime/resync`, `inject-all` (test 9).
- **No install during portability check/import:** `studio-portability.js` references no install-request APIs (test 10).
- **Compatibility ≠ Portability:** distinct endpoint families and vocabulary preserved; Model Library module carries no portability strings; "Compatible models" label untouched (test 11).

## 5. AUTHORITY PRESERVATION

- No new persistence. Reads/writes only via canonical routes backed by `.studio_model_library.json` and `.studio_custom_nodes.json`. The custom-node section renders the canonical registry — no UI-only list, no localStorage cache-as-authority.
- `local_path` display behavior unchanged (pre-existing library UI only); nothing new exports environment-local internals into portability/manifests (portability module untouched; G freeze intact).
- Workflows remains the sole modern Model Library owner; Backend gained no duplicate model management.

## 6. LEGACY PANEL RETIREMENT READINESS (Models/Sync)

Redundant after H7 (Wave E/G may remove once the gate below clears): M5, A1–A4 (approval flow supersedes raw downloads), F2, F3, S1-installed-truth, plus all browse/detail/notes/rescan surfaces.

**Remaining retirement blocker:** the ten BACKEND_OPERATIONAL actions (M1–M4, F1, F4, S1-upload-compare, S2–S5) still have NO modern home. Until H6/Backend either re-homes them (workspace/deploy family owns most) or proves obsolescence, the legacy panel remains the only UI for remote-volume inventory, placeholders, volume delete, raw download execution, manifest repair/install, sync uploads, and runtime resync/state. H7 deliberately did not implement any of them (H5 §10.2 frozen ownership).

## 7. TEST EVIDENCE

| Suite | Result |
|---|---|
| NEW `tests/studio_model_library_parity_unit.mjs` (focused, 16 sections mapping to mandate §17 items 1–15) | **16/16 PASS** (`node tests/studio_model_library_parity_unit.mjs`) |
| Extended `tests/browser/fake/studio-fake-models.spec.mjs` (new test C: registry browse, explicit refresh, click-gated install request, library handoff) | **3/3 PASS** (`npx playwright test --config=playwright.fake.config.mjs studio-fake-models.spec.mjs`) |
| Python model-library suites (`tests.test_model_library`, `tests.test_model_library_routes`, `tests.test_dependency_resolver`) | **33 passed** |
| Full gate `python tests/run_studio_tests.py --fake` (shared tree, H6/H8 concurrent) | python run=1991 **fail=2**; node-unit **21/21**; fake-playwright **197 passed / 2 failed** |

Failure attribution (not this lane's files): the 2 Python failures (`test_experiment_disabled_run_reason_from_helper`, `test_experiment_disabled_run_experiment_reason`) assert on `web/studio-experiment-mode.js` internals; the 2 fake failures (`studio-fake-experiment-gating` "H8", `studio-fake-visual` experiment grid; a third, `studio-fake-experiments` "post-H8", flaked in an earlier run) are experiment specs. All target H8-owned files/surfaces that H7 never touched, and they vary between runs (concurrent-lane churn). Per mandate §19 they were not "fixed".

Registration note: the new focused unit is intentionally NOT registered in `tests/run_studio_tests.py` (edits forbidden to this lane); registration belongs to the Wave-G L-TST lane per H5 §27.

## 8. FILES MODIFIED BY THIS LANE

- `web/studio-model-library.js` — imports (`refreshCustomNodes`, `requestCustomNodeInstall`), authority header note, custom-nodes section + registry rows, dependency-row ctx threading, node install-request control, find-in-library control, `_queryDirty` refetch, rescan/refresh status-after-rerender fix.
- `web/studio-workflows.js` — Dependencies region only: `renderDependenciesSection` passes `{ apiBase, onFindInLibrary }`; new `openModelLibraryFiltered` helper.
- `tests/studio_model_library_parity_unit.mjs` — NEW focused unit.
- `tests/browser/fake/studio-fake-models.spec.mjs` — test C added (spec-local route interception; shared fake backend untouched).

Not touched: `web/studio-backend.js`, `web/studio-backend-api.js`, `web/studio-settings.js`, `web/studio-experiment-mode.js`, `web/modal-settings.js`, `model_library_routes.py`, `tests/run_studio_tests.py`, all fake-backend/server shared files.

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
