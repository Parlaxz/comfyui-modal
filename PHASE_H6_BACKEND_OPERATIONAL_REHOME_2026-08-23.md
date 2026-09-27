# PHASE H6 — BACKEND OPERATIONAL RE-HOME (H-WAVE A1 + A2) (2026-08-23)

**Batch type:** H6 implementation (additive re-home of frozen H5 §25 Wave-A sublanes A1+A2 into ONE writer lane). No legacy removals, no server changes, no deploy, no Modal invocation, no GPU, no live generation, no commit/push/branch/worktree/reset. H7/H8 ran concurrently in the shared tree; no lane-owned file outside H6 scope was touched.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §2/§10/§25/§26 (+ H1 §13 "must-not-remove-yet" #6, H2 §9/§10, H4 exit-checklist items 5–7). H5 supersedes conflicting preliminary recommendations.

---

## 0. VERDICT

`H6 COMPLETE — MODERN BACKEND IS OPERATIONALLY COMPLETE (A1+A2). PASS.`

Workspace, deployment/redeploy, deploy status/log, runtime readiness, credentials, and swap-blocking manifest repair now have a modern Backend home consuming the EXISTING server routes. The legacy Settings panel is untouched and remains fully functional. Secrets are never echoed. No provider selector, no Model Library duplication, no warmup controls. WARMUP = RETIRE.

---

## 1. BACKEND UI ARCHITECTURE

`web/studio-backend.js` remains the composition/export glue (all prior exports preserved: `renderBackend`, `getBackends`, `getCompareBackends`, `getRuntimePresets`, `invalidateRuntimePresetsCache`, `renderFeaturesChipGrid`, `renderEmptyState`, `_STATE`, `_PATCH`, wizard launchers). Top-level nav unchanged (five surfaces; no new tab).

Inside Backend, the frozen section tabs are now:

```
Overview | Workspaces | Deployment | Credentials | Backend Presets | Snapshots
```

- Default tab: **Overview** (`activeTab = "overview"`). Backend Presets still renders before Snapshots (existing pinned ordering invariant preserved).
- Operational sections render full-width into a single ops panel; Snapshots/Backend Presets keep their list+detail layout unchanged.
- New narrowly scoped modules (L-BE1 ownership per H5 §26):
  - `web/studio-backend-runtime.js` — Overview/readiness rows + page-local ops bus (`createOpsBus`) + pure `summarizeOperationalState`.
  - `web/studio-backend-workspaces.js` — workspace CRUD/activate/swap + swap-blocking manifest repair.
  - `web/studio-backend-deployment.js` — deploy/redeploy+restart/status/log.
  - `web/studio-backend-credentials.js` — Modal connection + HF/Civitai credential status/save.
- State model: page-local closures only (selected id, busy flags, fetched safe records, pending swap job). No new globals; no localStorage keys added. Sections coordinate via a plain-array pub/sub bus created per `renderBackend` call (events: `workspace-changed`, `deploy-status-changed` → receivers RE-READ server truth; nothing auto-mutates).
- `web/studio-backend-api.js`: additive-only "Backend Operations API (H6)" region (request helpers + pure normalizers). It remains a request helper — no state authority. No other regions touched.

## 2. WORKSPACE PARITY (A1)

Consumes exactly the existing routes (`__init__.py:4380–4524`; store `.modal_workspaces.json` via `modal_workspaces.py`):

| Legacy control (modal-settings.js Workspace section) | Modern Backend (Workspaces tab) | Route |
|---|---|---|
| Workspace list + status line | Card list with label/id/last-deploy metadata; ACTIVE badge on server-reported active row | `GET /workspaces` |
| Active select (implicit) | Explicit **Set Active** button on selected non-active row | `POST /workspaces/active {workspace_id}` |
| + Add Workspace | Inline add form (label/token-id/token-secret password) | `POST /workspaces {label, token_id, token_secret, set_active:false}` |
| Edit Workspace | Inline edit form; blank token fields = keep-current (legacy contract) | `POST /workspaces {workspace_id, label, token_id:"", token_secret:"", set_active:false}` |
| Swap Workspace | Full multi-phase flow (below) | `POST /workspaces/swap`, `GET /workspaces/swap/{id}` |
| Manifest Repair | Bounded repair panel (see §8) | `POST /manifest/repair/*` |
| Export/Import Workflow Manifest | **NOT re-homed** (model-data portability ≠ workspace registry; see §9) | — |

**Workspace-registry export/import:** H5 classifies it KEEP_AND_REHOME_BACKEND "low priority; rides A1". Finding: **no existing server route or legacy control exports/imports the workspace REGISTRY** (the legacy Export/Import buttons are `/workflow-manifest/*` — the MODEL deployment manifest, a different concept). Per "use current server authority / do not create duplicate routes", H6 does NOT fabricate a browser-side registry export/import. Recorded as a deferred gap for L-BE2 (server-side seam) before legacy-panel retirement; unit test pins its absence so it cannot silently regress.

## 3. ACTIVE WORKSPACE AUTHORITY

- Server truth (`active_workspace_id` in `.modal_workspaces.json`, resolved server-side at dispatch) is displayed verbatim ("Active workspace: X (server-resolved at dispatch)").
- Every mutation path replaces local mirror with the SERVER response envelope (`{status:"ok", active_workspace_id, workspaces:[…]}`) or re-fetches `GET /workspaces`.
- Activation failure keeps the previous server truth rendered: the previous active row keeps its ACTIVE badge and the failure surfaces as a bounded message (unit-tested W4).
- Swap terminal states re-read the registry and notify Deployment/Overview via the bus (read-only refresh — never a deploy trigger).

## 4. DEPLOYMENT PARITY (A2)

- **Deploy**: explicit button → `POST /deploy`; handles `{status:"started"|"already_deploying"|"error"}`; arms a 3 s status poll ONLY after a user-initiated deploy (legacy `startDeployPoll` semantics); dedupes rapid clicks via disabled+in-flight guard (single POST under triple-click, tested D12); never fires on mount (D13), from polling, or on workspace change.
- **Redeploy and Restart**: same steps/semantics as legacy (`modal-settings.js:1299–1395`): deploy → poll ready (10 min cap) → `POST /api/manager/restart` → poll `/api/object_info` (10 min cap) → sessionStorage flag → `location.reload()`. In-flight phase labels visible; bounded timeout messages.
- **Deploy status**: `GET /deploy/status` rendered verbatim — state badge + message + `deploy_state` metadata (comfyapp_version/deployed_at). States are preserved, not invented: `ready / deploying / starting / unknown / error / deployed_unwarmed / idle` all display as-is; readiness is never inferred from HTTP success or cached data (tested D9 with `deployed_unwarmed`).
- **Logs**: bounded inline viewer (explicit toggle) → `GET /deploy/log`, tail last 120 lines, manual Refresh; auto-refresh only while an in-flight deploy is being polled (mirrors legacy inline viewer behavior; no new background service, no remote tailing beyond current product behavior).

## 5. RUNTIME HEALTH / READINESS

Overview tab (read-only): active workspace identity · deployment state/message · Modal connection (`GET /auth/status`) · runtime health (`GET /health?mode=deploy`: ok→Ready, deploying→Deploying, else verbatim status/message) · explicit Refresh. Mount performs READ-ONLY probes only (zero POSTs, tested O24). GPU preference, output preference, Preview preference, and tracing LEVEL remain in Settings — none moved (ownership hint line included).

## 6. WARMUP VERDICT

**WARMUP = RETIRE.** Evidence:
1. The warmup RUN action executes through the V1 executor (`run_prompt_stream`, `__init__.py:7734`) scheduled for retirement (H5 §5/§25 Wave C/E).
2. Its only remaining consumer-gate is the LEGACY aggregate-experiment scheduler (`gate_experiment_on_stored_generation`, `__init__.py:6098–6115`) — a surface retiring per H5 §14/R1. V2 runs/experiments never consult warmup state.
3. The legacy panel exposes NO warmup control today (only banner phase coloring from `modal_status` events) — there is no legitimate user-facing control to re-home.
4. Deploy truth already reports the unwarmed condition honestly (`state:"deployed_unwarmed"` + message), which modern Backend displays without inventing controls.
Structural guard: no `deploy-warmup` reference in any modern Backend module (unit test O23). Routes/store untouched (retirement is a later wave's decision, not H6's).

## 7. REPAIR-ACTION TABLE (per-action verdicts)

| Legacy repair-type action | Verdict | Rationale |
|---|---|---|
| Manifest Repair (scan / apply / delete-placeholder) | **KEEP_AND_REHOME_BACKEND** | Still operationally required: `POST /workspaces/swap` hard-fails `repair_required` when `.model_manifest.json` has blocking/unresolved entries (`__init__.py:4445–4503`). Deployment-bootstrap prerequisite, not a preference. Re-homed bounded (scan → issue table → Save All Valid / Skip All / delete placeholder → rescan). |
| Redeploy and Restart | **KEEP_AND_REHOME_BACKEND** | Deployment recovery action; routes exist; re-homed with identical semantics. |
| Deploy trigger | **KEEP_AND_REHOME_BACKEND** | See §4. |
| Warmup run / invalidate | **RETIRE** | §6. |
| Workspace registry export/import | **DEFERRED (no route exists)** | Documented gap; not fabricated client-side (§2). |
| Change API Key (`buildAuthPanel` / `/auth/setup`) | **COMPATIBILITY_ONLY (legacy)** | Superseded functionally by Workspaces add/edit (workspace-scoped tokens) + Credentials status; legacy panel keeps its control untouched. |
| Resync Runtime / Sync Models / Sync Custom Nodes / inject placeholders | **RETIRE from Backend** | Model-library/custom-node dependency management belongs to Workflows (H7/A3); raw bulk flows RETIRE per H5 §10.1/§24. Not reproduced anywhere in modern Backend. |

No generic "Repair Everything" was created.

## 8. MODEL-MANIFEST REPAIR VERDICT

**KEEP_AND_REHOME_BACKEND (proven non-obsolete).** The V2-era workspace swap — the canonical deployment-bootstrap flow — hard-depends on manifest scan results (`repair_required` branches above), and the swap-completion path installs from the repaired manifest. Modern Backend exposes ONLY the swap-blocking repair loop (`/manifest/repair/scan|apply|delete-placeholder`), explicitly labeled as a deployment-bootstrap concern pointing model browsing/install to Workflows → Model Library. `/manifest/install` (bulk install) is NOT exposed (§9).

## 9. MODEL OPERATION EXCLUSIONS

Modern Backend contains NO: generic model browser, dependency-install UI, bulk/batch installer, raw download manager, download-progress polling, model inject/inject-all, or `/manifest/install`. Verified structurally (unit test O20 bans `/studio/models`, `install-request`, `batch-install`, `model/install`, `models/inject`, `manifest/install` in all four operational modules). Per H5 §10.1/§24: model-library actions → Workflows (H7/A3 parity); any proven deployment-bootstrap gap would land in Backend only with evidence — none found beyond manifest repair (§8). `/studio/backends` misnomer: untouched; no new functionality built on it; existing discovery consumers unchanged (Wave F will replace them).

## 10. CREDENTIALS / AUTH (no authority fork)

- **Modal connection**: `GET /auth/status` → CONNECTED / NOT CONFIGURED badge; copy points token management to the Workspaces tab (workspace-scoped tokens ARE the existing storage authority — no new store, no localStorage token key).
- **HF token / Civitai key**: existing routes only (`GET|POST /hf-token`, `GET|POST /civitai-token`). Status renders CONFIGURED / NOT CONFIGURED via `credentialConfigured()` which deliberately DISCARDS the returned (masked) value — saved credentials are never echoed (the legacy panel's masked-prefix display is intentionally stricter here). Inputs use `type="password"`; values live in memory until submit; input cleared after successful save; failures surface the bounded server message only and never contain the token (tested A15–A18). Empty save = clear (legacy semantics preserved).

## 11. BACKEND PRESETS

Preserved as transitional owner: tab labeled **"Backend Presets"** (never "Workflow Presets"), `.studio_presets.json` / `/studio/presets*` untouched, Playground consumption (`getRuntimePresets`) intact, wizard glue intact. Snapshots likewise unchanged (separate concept from History RequestSnapshots; store untouched).

## 12. EXACT LEGACY CONTROLS NOW SAFELY DUPLICATED IN MODERN BACKEND

Workspace list · active-workspace selection · add workspace · edit workspace (keep-current-token contract) · swap workspace (confirm-interrupt → review/select-models → job polling with phase/download/sync/deploy messages → completion summary) · manifest repair (scan/apply/skip/delete-placeholder) · deploy trigger · redeploy-and-restart · deploy status banner/state/message/details · deploy log viewing · HF token save/clear · Civitai key save/clear · auth/connection status. All consume the SAME routes as legacy — both surfaces stay live during the transition (H6 is additive; Wave E removes legacy only after parity proof).

## 13. REMAINING LEGACY-PANEL EXIT BLOCKERS (H4 checklist deltas)

Still blocking (unchanged by H6, by design):
1. **Workspace-registry export/import server seam** — no route exists today (§2); needs L-BE2 decision or explicit product drop.
2. **Model Library parity verification** for legacy Models/Sync edge cases (Add-Model folder list, download progress) — H7/A3 lane.
3. **Legacy experiment Setup draft shim + feature-registry copy rewrite** (items 10) — A4/D lanes.
4. Comparison Profiles compatibility surface (item 11) — Wave E per R1.
5. Redirects/removals themselves — Waves B/E.
Items 5/6/7 of the H4 exit checklist (deploy/warmup, workspace, credentials re-home) are NOW satisfied by this batch.

## 14. FAKE-BACKEND PARITY (deferred, per §23)

Fake backend mirrors only `GET /deploy/status` (consumed read-only where relevant). It lacks `/workspaces*`, `/auth/status`, `/hf-token`, `/civitai-token`, `/manifest/repair/*`. H8 may own those files, so H6 did NOT touch any shared fake/server file; browser-scenario parity is DEFERRED and covered instead by focused Node unit mocks (`tests/studio_backend_operations_unit.mjs`). If H8 later adds fake routes, the existing specs need no change; new browser specs can be layered then.

## 15. TEST EVIDENCE

New (direct-run, NOT registered in `tests/run_studio_tests.py` while H7/H8 are concurrent, per §24):
- `node tests/studio_backend_operations_unit.mjs` → **24/24 PASS** (W1–W8 workspace, D9–D14 deploy, A15–A18 auth, O19–O24 ownership/warmup/overview).

Focused regression (this lane):
- `pytest tests/test_studio_backend.py` → **298 passed** (one pinned assertion updated: `BackendTabOrderTests.test_default_tab_is_presets` now asserts the frozen H6 default `activeTab = "overview"` and never-snapshots; presets-before-snapshots DOM order assertion kept passing unchanged).
- `pytest tests/test_testing_shell_integration.py tests/test_model_library.py tests/test_model_library_routes.py tests/test_modal_settings_gpu_config.py tests/test_testing_ui_wired.py tests/test_modal_workspace_ui_ast.py` → all pass EXCEPT three failures in files owned by CONCURRENT lanes (ownership truth below).
- Node suites (read-only): `studio_phase_f4_settings_authority_unit.mjs` PASS · `studio_model_library_parity_unit.mjs` (H7's own) PASS · `studio_legacy_settings_authority_unit.mjs` PASS.
- Glue smoke: `renderBackend` mounts 6 tabs; Workspaces/Deployment sections mount; presets switch-back OK (temp-stubbed import; `scripts/app.js` dependency is pre-existing and ComfyUI-runtime-only).

Full gate attempt (`python tests/run_studio_tests.py`, python+node lanes):
```
python    run=1991  fail=2
node-unit run=21    fail=0   (21/21 PASS)
```
The 2 python failures are `test_experiment_disabled_run_reason_from_helper` (test_testing_shell_integration) and `test_experiment_disabled_run_experiment_reason` (test_testing_ui_wired) — both assert on `web/studio-experiment-mode.js`, which carries 181 insertions/146 deletions from the CONCURRENT experiment lane; H6 touched zero lines of that file. `--fake` Playwright lane was NOT run: §26 conditions it on the shared tree being stable after H7/H8 land, which has not happened yet; ownership truth for the transient python failures is recorded above instead.

## 16. FILES MODIFIED BY THIS LANE

- `web/studio-backend.js` — tab structure + ops-section wiring + bus (all exports/behavior preserved).
- `web/studio-backend-api.js` — additive Backend-operational helper region only.
- `web/studio-backend-runtime.js` — NEW.
- `web/studio-backend-workspaces.js` — NEW.
- `web/studio-backend-deployment.js` — NEW.
- `web/studio-backend-credentials.js` — NEW.
- `tests/studio_backend_operations_unit.mjs` — NEW (direct-run).
- `tests/test_studio_backend.py` — one pinned default-tab assertion updated to the frozen H6 structure.
- This report.

NOT touched: `modal-settings.js`, `__init__.py`, `modal_workspaces.py`, deployment/auth services, fake-backend/server files, `tests/run_studio_tests.py`, Settings/Workflows/Playground/History modules, openers/auto-open/aliases.

---

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
