# PHASE H5 FOLLOW-UP A — WAVE-A OPERATIONAL RECONCILIATION (2026-08-24)

**Batch type:** H5 contract follow-up / reconciliation only. READ-ONLY against production code and tests. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. Files modified by this batch: **this document** + the appended errata section in `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md`.
**Authority:** This report carries the evidence detail; the appended H5 contract errata section is the AUTHORITATIVE record and supersedes named rows of H5 §10.2/§21/§25 where stated. H6/H7 historical reports are NOT modified.

---

## 0. VERDICT

`H5 FOLLOW-UP A COMPLETE — POST-WAVE-A1/A2/A3 RECONCILIATION FROZEN. ZERO REMAINING LEGACY MODELS/SYNC EXIT BLOCKERS FROM THE H7 HANDOFF SET.`

Source verifications performed by this lane (contradiction checks only):
- `__init__.py:4380–4524` — workspace route family is exactly `GET/POST /comfymodal/workspaces`, `POST /workspaces/active`, `POST /workspaces/swap`, `GET /workspaces/swap/{id}`. No export/import route exists.
- `modal_workspaces.py` — functions are load/save/upsert/set_active/migrate_from_legacy_toml/get/get_active/summary. No export/import capability exists server-side either.
- `web/modal-settings.js:2084/2089` — the legacy Export/Import buttons are labeled "Export Workflow Manifest"/"Import Workflow Manifest" and call `/workflow-manifest/export|import` (MODEL deployment manifest portability — a different concept).
- All ten-plus-one handoff routes verified present: `/comfymodal/models` (:4892), `/models/inject` (:4900), `/models/inject-all` (:4920), `DELETE /models/{folder}/{filename}` (:4943), `/manifest/repair/*` (:4532–4549), `/manifest/install` (:4567), `/sync/status` (:4960), `/sync/models` (:5022), `/sync/custom-nodes` (:5085), `/runtime/resync` (:5100), `/runtime/state` (:5122).
- Sole web consumer of every handoff route is the legacy panel (`modal-settings.js`). Zero references in any `web/studio-backend*.js` module (confirms H6 unit bans O20/O23). Zero Python-internal HTTP consumers.
- `_run_workspace_swap_job` (`__init__.py:3292–3493`) internally performs: deploy ensure (Phase 1), remote model removal via `delete_model()` (Phase 2), model install via `download_model_stream()` over user-selected `to_install` (Phase 3), custom-node package/upload via `_build_custom_nodes_archive()` + `sync_custom_nodes()` (Phase 4), conditional redeploy (Phase 4b), and `resync_runtime("custom_nodes")` (Phase 4c), then sets active workspace.
- Warmup: routes at `__init__.py:7693–7779`; sole consumer gate is the legacy aggregate-experiment scheduler `gate_experiment_on_stored_generation` (:6100–6115); `web/modal-settings.js` contains NO `deploy-warmup` reference (no user-facing control exists).
- `/auth/setup` (:3570–3600) writes global `modal.toml`, upserts a "Primary" workspace, and fires a background deploy — a first-run bootstrap whose function is superseded by workspace-scoped add/edit + Credentials status.
- Test registration: `tests/run_studio_tests.py` registers NEITHER `tests/studio_backend_operations_unit.mjs` NOR `tests/studio_model_library_parity_unit.mjs` (nor the known `studio_legacy_settings_authority_unit.mjs` debt). Both new files exist on disk.

---

## 1. WORKSPACE-REGISTRY EXPORT/IMPORT — ERRATUM CONFIRMED

Question re-verified exactly as framed: does the product have (A) a legacy user-facing Workspace REGISTRY export/import operation, or (B) an existing server route exporting/importing `.modal_workspaces.json` as a registry?

**Answer: NO to both.**

- The legacy workspace-section buttons that H5's freeze interpreted as candidate registry export/import are `Export Workflow Manifest` / `Import Workflow Manifest` (`modal-settings.js:2084/2089`) calling `/comfymodal/workflow-manifest/export|import` — MODEL deployment-manifest portability operations, already modernized in Workflows (H7 F2/F3 ALREADY_MODERN). They are NOT workspace-registry operations.
- The server has no such route and `modal_workspaces.py` has no such function. Nothing exports or imports `.modal_workspaces.json` as a registry.
- Explicitly excluded confusables checked and ruled out: workflow-manifest export/import (F2/F3), model deployment manifest ops (`/manifest*`), portability ops (`/studio/workflows/*/export`, import-manifest), workspace swap, workspace add/edit, token configuration.

**FROZEN CORRECTION:** `WORKSPACE_REGISTRY_EXPORT_IMPORT = NOT_AN_EXISTING_PRODUCT_CAPABILITY`

Consequences (binding):
1. REMOVED from the Backend parity prerequisite (supersedes H5 §10.2 row "Workspace registry export/import = KEEP_AND_REHOME_BACKEND" and §25 A1 parenthetical "(registry export/import)").
2. REMOVED from the legacy-panel exit-blocker list (supersedes H6 §13 blocker #1).
3. DO NOT create a route; DO NOT add browser-side JSON export/import; absence is NOT missing parity.
4. If ever desired, classify as NEW PRODUCT SCOPE — never Phase-H migration debt.

## 2. FINAL POST-WAVE-A LEDGER — H7 HANDOFF OPERATIONS

Count note: H7's prose says "ten," but H7's own tables plus this mandate enumerate **ELEVEN** conceptual operations (M1–M4, F1, F4, S1-upload-compare, S2–S5); H7's §1d S1 row carries a split classification (installed-truth ALREADY_MODERN + upload-compare handed off), which made the prose count drift. The ledger below covers all eleven enumerated operations. H7's concurrent-time statement "the ten BACKEND_OPERATIONAL actions still have no modern home" was accurate at its observation point and is superseded by this converged reconciliation without modifying the H7 report.

| # | Legacy operation | Route(s) | Actual purpose | H7 preliminary | H6 evidence/verdict | FINAL CLASS | Modern replacement | Blocks legacy Settings retirement |
|---|---|---|---|---|---|---|---|---|
| M1 | Browse models list (Models "Refresh"/list, `loadModels` :838) | `GET /comfymodal/models` | LIVE remote-volume inventory annotated with local-placeholder state — deployment-state domain, distinct from canonical library records | BACKEND_OPERATIONAL | Not re-homed; Backend bans a second model browser (O20); swap/repair compute their own server-side truth; canonical Model Library + contextual swap plan provide product truth | **RETIRE** (UI) | Workflows Model Library (`GET /studio/models`); swap review plan (already_present/to_install/to_remove); repair issue table. No second browser built (H5 duplicate-authority ban) | **NO** |
| M2 | Per-model "Create local" placeholder (:956) | `POST /comfymodal/models/inject` | Creates local 0-byte placeholder so the ComfyUI canvas dropdown can list remote-only models | BACKEND_OPERATIONAL (H5 leaned RETIRE) | Not reproduced; no surviving canvas/deployment correctness dependency requires a USER-FACING operation; the placeholder MECHANISM itself (automatic/internal consumption by canvas/object_info) is untouched and needs no button | **RETIRE** (UI) | None user-facing. Canvas compatibility layer keeps consuming existing automatic/internal placeholder behavior — this does NOT imply a modern button | **NO** |
| M3 | "Create All Placeholders" (:3422) | `POST /comfymodal/models/inject-all` | Bulk variant of M2 | BACKEND_OPERATIONAL / duplicate-UI RETIRE lean | Not reproduced anywhere modern | **RETIRE** (UI) | Same as M2 | **NO** |
| M4 | Delete model from volume (✕ :985) | `DELETE /comfymodal/models/{folder}/{filename}` | Destructive remote-volume administration + local placeholder cleanup | BACKEND_OPERATIONAL | Swap Phase 2 removes flagged models INTERNALLY via the same `delete_model()` function (`__init__.py:3334`); no surviving modern workflow requires hand-deletion outside swap review; not required by repair (repair deletes PLACEHOLDERS locally, not volume objects) | **RETIRE** (UI); underlying function retained (swap depends on it); route untouched compatibility until Wave F/G review | Workspace Swap review ("to_remove" selection) | **NO** |
| F1 | Manifest Repair (:2079/:2411) | `POST /manifest/repair/scan\|apply\|delete-placeholder` | Repairs blocking/unresolved `.model_manifest.json` entries | BACKEND_OPERATIONAL (pending non-obsolescence proof) | PROVEN NON-OBSOLETE: `POST /workspaces/swap` hard-fails `repair_required` when blocking/unresolved entries exist (`__init__.py:4445–4503`); bounded repair loop re-homed in Backend → Workspaces tab | **MODERN_BACKEND** | Backend → Workspaces → manifest repair panel (scan → issues → Save All Valid / Skip All / delete placeholder → rescan) | **NO** |
| F4 | Install from Manifest (:2093/:2941) | `POST /manifest/install` | Bulk-install manifest entries into the volume (standalone dialog, `showManifestInstallDialog`, `modal-settings.js:3068–3103`) | BACKEND_OPERATIONAL | H6 intentionally did NOT expose it; the canonical swap job performs the necessary install phase INTERNALLY (Phase 3 `download_model_stream` over user-selected `to_install`, `__init__.py:3358–3392`) — the higher-level Workspace Swap operation supersedes a second raw bulk installer | **RETIRE** (standalone UI) | Workspace Swap (select models during confirm; job reports download progress/summary) | **NO** |
| S1 | "Refresh Status" upload-compare (:3167) | `GET /comfymodal/sync/status` | LOCAL-vs-REMOTE UPLOAD comparison (files on disk vs volume); installed/presence-truth portion already modern | Split: installed-truth ALREADY_MODERN; upload-compare BACKEND_OPERATIONAL | No modern consumer; Workflows owns installed-model + custom-node registry truth (H7); swap computes remote availability server-side via `_scan_swap_plan`; duplicating upload-compare in Backend would fork dependency state | **RETIRE** (upload-compare UI) | Model Library presence badges + custom-node registry (Workflows); swap plan for deployment deltas | **NO** |
| S2 | "Sync Models" upload (:3174) | `POST /comfymodal/sync/models` | Uploads ALL local non-placeholder models to the volume (raw bulk flow) | BACKEND_OPERATIONAL | Raw bulk flows RETIRE per H5 §10.1/§24; the legitimate higher-level transfer happens inside swap (user-selected, reviewed, with progress + summary) | **RETIRE** (standalone UI); route untouched while legacy panel lives | Workspace Swap (selected transfer) | **NO** |
| S3 | "Sync Custom Nodes" (:3185) | `POST /comfymodal/sync/custom-nodes` | Packages + uploads custom nodes + conditionally redeploys | BACKEND_OPERATIONAL | Swap Phase 4 performs package/upload/redeploy-check/resync INTERNALLY (`__init__.py:3412–3467`); Workflows owns custom-node dependency/install-request truth (H7 C1–C3); Backend owning a second node manager would violate ownership | **RETIRE** (standalone UI) | Workspace Swap (automatic) + Workflows install requests | **NO** |
| S4 | "Resync Remote Runtime" (:3196) | `POST /comfymodal/runtime/resync` | Reloads the running Modal ComfyUI container to pick up volume changes | BACKEND_OPERATIONAL | Swap calls `resync_runtime("custom_nodes")` internally after node sync (:3449); modern recovery for a stale/undesired runtime is Redeploy and Restart (re-homed, identical semantics); no surviving V2-runtime scenario requires a standalone no-deploy resync button | **RETIRE** (standalone UI); internal function retained (swap uses it) | Redeploy and Restart (Backend → Deployment) + swap auto-resync | **NO** |
| S5 | "Check Runtime State" (:3207) | `GET /comfymodal/runtime/state` | Manual staleness readout ("stale → use Resync") pairing with S4 | BACKEND_OPERATIONAL | Modern Backend Overview/readiness represents runtime truth: active workspace, deploy state/message (incl. honest `deployed_unwarmed`), Modal connection, `GET /health?mode=deploy` readiness; staleness ACTIONABILITY is absorbed by readiness + Redeploy-and-Restart now that standalone resync retires | **MODERN_BACKEND** (via Overview/readiness surface; raw route remains server-side untouched, unconsumed — no duplicate Sync-section panel) | Backend → Overview readiness rows + Deployment status | **NO** |

### Final tally (11 operations)
- **MODERN_BACKEND: 2** (F1 manifest repair, S5 runtime state/readiness)
- **MODERN_WORKFLOWS: 0**
- **RETIRE: 9** (M1, M2, M3, M4, F4, S1-upload-compare, S2, S3, S4)
- **COMPATIBILITY_ONLY: 0** (operations; routes simply remain untouched per H5 §18 "UI retirement does not imply route deletion")
- **STILL_BLOCKED: 0**

Route-disposition note (uniform): no route is deleted or modified by this reconciliation. Routes with surviving INTERNAL callers (`delete_model`, `resync_runtime`, `sync_custom_nodes` functions used by the swap job) keep their server functions; their HTTP routes have zero modern consumers and become Wave-F/G review candidates together with the retiring legacy panel. Structural test pins (`test_modal_runtime_routes.py`, `test_modal_workspace_backend.py`, `test_modal_workspace_ui_ast.py`) remain valid because routes/UI source are untouched.

## 3. M1 DEEP-DIVE (mandate §4 resolution)

Outcome **B (RETIRE)** chosen over A (MODERN_BACKEND) and C (COMPATIBILITY_ONLY):
- No modern Backend operation renders or requires human-browsable remote-volume inventory: swap computes its plan server-side (`_scan_swap_plan`), repair consumes manifest scans, deploy status is state-metadata. Exposing `/comfymodal/models` as a Backend browser would create exactly the duplicate model-management authority H5 forbids (§10.1/§24, invariant 12).
- No old tooling/readers were found requiring the HTTP route (sole web consumer: legacy panel; sole test references are structural pins and the H6/H7 ban-lists). Hence C is unnecessary as a UI class; the route itself simply persists untouched under §18 until Wave F/G.

## 4. WARMUP — H6 VERDICT ACCEPTED

H5 §10.2 froze warmup as KEEP_AND_REHOME_BACKEND *(conditional)*. The condition resolves to **RETIRE**, accepted as the authoritative post-Wave-A verdict. Evidence verified this lane:
1. Warmup RUN executes through the V1-bound path (`/deploy-warmup/run` family, `__init__.py:7693–7779`; V1 executor scheduled for retirement per H5 §5/§25 Wave C/E).
2. Sole remaining consumer-gate is the LEGACY aggregate-experiment scheduler (`gate_experiment_on_stored_generation`, :6100–6115) — retiring per H5 §14/R1. V2 runs/experiments never consult warmup state.
3. The legacy panel exposes NO warmup control (zero `deploy-warmup` references in `modal-settings.js`) — there is no user-facing control to re-home.
4. V2 does not depend on it; deploy truth reports the unwarmed condition honestly (`state:"deployed_unwarmed"`), which modern Backend displays verbatim (H6 D9).
No warmup work is reopened. Route/store retirement remains a later wave's decision.

## 5. AUTH / CREDENTIAL CLARIFICATION

H6 classified legacy Change API Key (`buildAuthPanel` → `POST /auth/setup`) COMPATIBILITY_ONLY. Verified: `/auth/setup` writes the GLOBAL `modal.toml`, upserts a "Primary" workspace, and triggers a background deploy — a first-run bootstrap pattern superseded by workspace-scoped credentials (Workspaces add/edit with keep-current-token contract) + Credentials status/connection truth + HF/Civitai controls (all re-homed by H6).

**FROZEN:** legacy `/auth/setup` UI is NOT required parity for modern Backend; it is removed from any exit-blocker interpretation. The compatibility ROUTE is not deleted yet (untouched; Wave F/G review).

## 6. REVISED LEGACY MODELS/SYNC EXIT-BLOCKER LEDGER

After reconciling all eleven handoff operations: **NONE remain from the Models/Sync set.**
Every live purpose is re-homed (F1, S5), superseded by the canonical swap job (F4, S2, S3, S4, M4-removal-path), owned by Workflows (M1 library truth, S1 installed-truth), or retired as obsolete UI (M2, M3).

Whole-panel context (unchanged, for accuracy): the remaining legacy-Settings exit items OUTSIDE Models/Sync are H4 checklist item 10 (legacy experiment Setup draft shim + feature-registry copy rewrite — A4/D lanes), item 11 (Comparison Profiles compatibility surface — Wave E per R1), and the redirect/removal steps themselves (Waves B/E). H6's former blocker #1 (registry export/import seam) is dissolved by §1 of this report.

## 7. TEST-REGISTRATION DEBT (confirmed, unchanged)

- `tests/studio_backend_operations_unit.mjs` (H6, 24/24 PASS direct-run) — unregistered.
- `tests/studio_model_library_parity_unit.mjs` (H7, 16/16 PASS direct-run) — unregistered.
- Verified absent from `tests/run_studio_tests.py` registrations this lane. Both remain INTENTIONAL Wave-G L-TST MIGRATE/REGISTER candidates per H5 §27. The runner was NOT edited by this batch.

## 8. FULL-GATE REDS ATTRIBUTION (recorded, not rerun)

H6: focused GREEN (backend ops unit 24/24; `pytest tests/test_studio_backend.py` 298 passed; node-unit lane 21/21) with 2 python failures attributed to H8-owned `web/studio-experiment-mode.js` churn. H7: focused GREEN (parity unit 16/16; fake-models spec 3/3; python model-library suites 33 passed) with the same 2 python failures plus 2 flaky experiment fake failures, all on H8-owned surfaces. Shared-tree final gate: **DEFERRED until H8 settles** (H5 §26 condition). This batch ran no tests and reran no gate.

## 9. WAVE-B ENTRY GATE

```
H5A_BACKEND_REHOME_READY      = YES   (H6 complete; H4 items 5/6/7 satisfied; F1 re-homed; warmup accepted RETIRE; auth/setup clarified not-required-parity)
H5A_MODEL_LIBRARY_PARITY_READY = YES  (H7 complete; C1–C4 landed; A1–A4 retire; handoff set reconciled with zero remaining blockers)
H5A_EXPERIMENT_A4_PENDING      = YES
H5A_WAVE_B_GLOBAL_READY        = NO_PENDING_H8
```

This is the H6/H7 portion of the Wave-A prerequisite only; the global Wave-B gate awaits H8 (Experiment A4) settlement and the deferred shared-tree gate.

---

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
