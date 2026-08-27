# PHASE H3 — LEGACY RETIREMENT REFERENCE INTEGRITY & HISTORICAL COMPATIBILITY AUDIT (2026-08-23)

**Batch type:** READ-ONLY AUDIT. No production code, no tests, no deploy/live/GPU/generation, no commit/push/branch/worktree/reset. Files modified by this batch: **this document only**.
**Inputs:** `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md`, History V2 models/store/repository/routes/replay/writer/migration/export sources, Workflow domain stores/services/routes, experiment modern plan/routes/scheduler, legacy stores (`studio_routes.py`, `experiment_service.py`, `presets.py`, `run_history.py`, `history_index.py`), portability modules, model-library compatibility routes, web frontend, fake backend.

---

## 0. VERDICT

`H3 COMPLETE — Phase H may retire UI surfaces, but the data/reference contracts below are hard constraints.`

History V2 is **self-contained for both rendering and replay**: every render path derives provenance from copied snapshot data inside `history_v2.db`, and every re-execution path replays only `request_snapshots.execution_plan_json`. **No History render or replay path reads `.studio_workflows.json`, `.studio_workflow_versions.json`, `.studio_workflow_mappings.json`, `.studio_workflow_presets.json`, `.studio_snapshots.json`, `.studio_presets.json`, the portability cache, or model-compatibility annotations.** Deleting any Workflow/Version/Mapping/Preset record therefore cannot crash or falsify History; it can only make an id dangle as a filter key. The real retirement hazards are elsewhere: (1) live consumers of "legacy" routes that are NOT UI-obsolete (Playground recent-runs strip, Playground runtime preset selection, Backend page, testing suite); (2) the workspace registry dependency of replay dispatch; (3) the bridge/migration readers over `.run_history`.

---

## 1. HISTORY REFERENCE INVENTORY (stored fields → classification)

Schema: `history_v2_store.py` (`generations`, `run_attempts`, `experiment_cells`, `experiments`, `assets`, `export_records`, `request_snapshots`, `legacy_mapping`). Models: `history_v2_models.py`.

| Stored field | Where | Written from | Classification | Live lookup today? |
|---|---|---|---|---|
| `workflow_id` | `generations` | writer copies `meta.workflow_id` else `workflow_hash` (`history_v2_writer.py:700`); migration copies `workflow_hash` (`history_v2_migration.py:108`) | **copied immutable provenance** (for migrated rows it is literally a hash, not a domain id) | Only as SQL equality filter/sort key (`query_generations`, `idx_generations_workflow_id`) |
| `workflow_version_id` | `generations`, `request_snapshots` | copied from run meta / cell plan at write time | **copied immutable provenance** | Filter key only; never resolved against version store |
| `preset_id` / `preset_name` | `generations` | copied from meta (`studio_preset_id`/`preset_name`) | **copied immutable provenance** (+ `preset_name` is a denormalized display copy) | Filter key + search LIKE only |
| `experiment_id` | `generations`, `run_attempts` | set at creation / mirror | **hard live reference** → `experiments` row in the SAME SQLite DB (FK) | Yes — but referent is in History itself, not a UI surface |
| `cell identity` (`cell_id`, `attempt_ids_json`, position, axis_labels) | `experiment_cells` | modern create route persists full cell plans into `experiments.definition_json`; mirror path lazily creates cells | **hard live reference** within History DB | Yes — powers cell detail/retry/resume |
| `generation_id` | `experiment_cells.generation_id`, `assets.generation_id`, `request_snapshots.generation_id`, `run_attempts.generation_id` | writer/mirror | **hard live reference** within History DB (FKs; assets/attempts CASCADE) | Yes |
| `request_snapshot_id` | `generations.request_snapshot_id` | `_ensure_request_snapshot` | **hard live reference** within History DB | Yes — THE replay authority |
| RequestSnapshot payload (`workflow_json`, `workflow_hash`, `workflow_version_id`, `generation_params_json`, `preset_snapshot_json`, `request_json`, `execution_plan_json`, `deployment_identity_json`) | `request_snapshots` | frozen once at acceptance (`history_v2_writer.py:977–1013`; modern cell plans embed the same plan) | **copied immutable provenance — self-contained replay authority** | Validated in place by `validate_replay_capability`; never re-fetched from anywhere |
| `workflow_json` (snapshot copy) | `request_snapshots.workflow_json` | run meta `workflow_json` | **copied immutable provenance** — sole source of display `workflow_name` (`history_v2_routes._workflow_name:412`: snapshot JSON name/title → `preset_snapshot.workflow_name` → **null**, never workflow_id) | Read-only JSON extraction for display/search |
| `execution_plan_json` | `request_snapshots` | frozen ExecutionPlan at acceptance | **copied immutable provenance — the ONLY plan source for every re-execution** (Phase F invariant 1) | `load_replay_plan` raw-validation + exact round-trip |
| `deployment_identity_json` (+ plan-embedded copy) | `request_snapshots`, plan | frozen at acceptance (`studio_run_adapter._collect_plan_deployment_identity`) | **copied immutable provenance** — used for presence/equality validation only; never re-resolved against deploy state during replay | Presence + snapshot↔plan equality check |
| Asset `managed_path` (`local path` or `modal://<workspace>||<gpu>||<path>`), `sha256` | `assets` | materializer/writer | **copied immutable provenance** pointing at managed bytes; `modal://` embeds a workspace id | Resolved lazily at serve/export time via `.modal_workspaces.json` registry |
| `legacy_mapping` (`legacy_run_id` → `generation_id`, `source`) | `legacy_mapping` | migration seam | **tombstone table** (idempotent skip key) | Migration reader only |

Classification legend: *hard live reference* = dangling id breaks behavior; *copied immutable provenance* = display/replay data frozen at write time; *optional annotation* = e.g. `featured_asset_id`, `favorite/note`, `logical_output_key`; *legacy-only* = `legacy_mapping`, mirrored legacy-cell rows.

### Render paths that assume a source object exists

**None.** Verified across `history_v2_routes.py` feed/detail/cell builders:
- `workflow_name` comes only from the snapshot (`_workflow_name`), unknown → `null` (never id-as-name).
- Experiment feed items show `definition.workflow` / `definition.preset` — labels copied into the persisted definition at acceptance.
- Cell axis labels come from `experiment_cells.axis_labels` / definition.
- Assets project truthfully missing states (`original_failed`, structural availability check, `modal://` ≠ absence).
- The only external resolution on ANY read path is `_resolve_workspace_dict(workspace_id)` for `modal://` asset serving — failure is a truthful 404 "asset workspace unavailable", not a crash.

---

## 2. WHAT HAPPENS IF THE SOURCE OBJECT DISAPPEARS

| Disappearance | History render | Replay/Resume/Retry | Notes |
|---|---|---|---|
| Workflow deleted from `.studio_workflows.json` | Unaffected. Name still rendered from snapshot; `workflow_id` remains a filter key that simply matches nothing in Workflows UI | Unaffected — plan is self-contained | No FK, no join, no lookup exists to break |
| WorkflowVersion missing | Unaffected (`workflow_version_id` displayed as opaque provenance) | Unaffected — `validate_replay_capability` checks ids for internal CONSISTENCY across plan/request/preset-snapshot/generation, never existence in the version store | Identity mismatch between stored copies fails closed honestly (`identity_mismatch`) |
| Mapping missing | Unaffected (History never reads mappings) | Unaffected | |
| Preset deleted (either store) | `preset_name` copy keeps rendering; `preset_id` filter matches nothing | Unaffected — `preset_snapshot` is embedded in the snapshot | Truthful stale display already achieved by design |
| Legacy snapshot (`.studio_snapshots.json`) missing/archived | Unaffected — History V2 never references it | Unaffected | Legacy snapshots are a Backend-page concept, not a History reference |
| Old custom-node dependency missing / registry gone | Unaffected | Unaffected — replay validates and dispatches the frozen graph; node availability is a runtime execution concern, reported as attempt failure, not a History integrity failure | Do not conflate with portability's dependency resolver |
| Portability cache (`.studio_portability_reports.json`) missing/corrupt | Unaffected | Unaffected — cache never gates anything (G10/G11 fail-open; History SQLite unused by cache) | Regenerable derived sidecar |
| Model-compatibility annotations (`.studio_workflow_compatibility.json`) removed | Unaffected | Unaffected — zero references from history_v2_* / replay / canonical_execution (grep-verified; only Workflow-detail display consumes them) | |
| Workspace in `.modal_workspaces.json` deleted | Feed/detail fine; `modal://` assets 404 truthfully | Generate Original/Resume refuse 503 `dispatch_unavailable`/`workspace_unresolved` BEFORE creating attempts (E7 fail-closed preflight, `history_v2_replay.py:1126–1137`) | This is the ONE live external lookup replay performs |
| Legacy Settings key removed | Unaffected (F4A already removed stale keys; durable namespaces excluded from reset) | Unaffected — replay sends zero option delta; saved GPU frozen in plan metadata (F8) | |
| `.run_history/<id>/meta.json` deleted after migration | Migrated Generation stays viewable (data was copied) | Legacy-migrated rows were ALREADY irreproducible unless `extra.workflow_json` existed — and even then they lack `execution_plan_json`/`deployment_identity` → stay viewable-not-replayable | See §4 |

---

## 3. REQUESTSNAPSHOT AUTHORITY (what replay/resume/retry actually needs)

`history_v2_replay.py` — the single canonical gate used by Generate Original, Retry Original, Single Resume, the F5 `replay_capable` projection, and (via cell plans) Experiment retry/resume:

**Necessary (all must be present INSIDE the snapshot):**
1. `schema_version ∈ {None, 1}` and plan `schema_version == CURRENT_PLAN_SCHEMA_VERSION`.
2. Non-empty `execution_plan` with: `workflow` + `workflow_hash` + `source_workflow_hash`, complete `execution_options` (incl. `production.enabled`), non-empty `output_node_ids`, maps for `production_report/model_stack/prompt_bundle/input_images/request_metadata`, non-empty `validation` proof.
3. Snapshot↔plan equality: `workflow` bytes equal; `deployment_identity` present (when production enabled) and equal on both copies; `workflow_hash` equal.
4. Identity consistency for `workflow_id` / `workflow_version_id` / `preset_id` across plan metadata, request, preset_snapshot, generation_params, generation row (single unique value each).
5. Non-empty `request`.
6. At dispatch: a resolvable Modal workspace — `plan.request_metadata.workspace_id`, else the ACTIVE workspace fallback for pre-workspace-id snapshots (`_resolve_replay_workspace` → `.modal_workspaces.json`).

**NOT necessary (display enhancement only):** current Workflow/Version/Mapping/Preset records; Settings; model selections; GPU catalog state (saved GPU rides in plan metadata); portability reports; compatibility annotations; custom-node registry; Model Library.

**Hard requirement status: MET.** Retiring any UI surface cannot make a previously reproducible Generation irreproducible, because reproducibility never depended on any UI-owned object. Conversely H must not ADD new dependencies (e.g., resolving `workflow_version_id` against the domain store before dispatch would newly break replays when workflows are deleted).

---

## 4. LEGACY IRREPRODUCIBLE RECORDS (capability projection trace)

Preserved exactly as Phase F left it:

1. Legacy row without `extra.workflow_json` → migration creates NO snapshot (`history_v2_migration.py:168–190`) → generation has `request_snapshot_id = NULL` → detail/feed project `replay_capable:false, reason:"missing_request_snapshot"` (`history_v2_routes._replay_capability_fields:858`).
2. Row with `workflow_json` but no frozen plan (all migrated rows; any pre-plan-era row) → snapshot exists with empty `execution_plan_json` → validator fails `missing_execution_plan` (or `missing_deployment_identity` when production-enabled plan semantics apply).
3. Tampered/hand-edited snapshot → `snapshot_hash_mismatch` / `snapshot_workflow_mismatch` / `invalid_plan` (round-trip).
4. UI consumption is tolerant: explicit false → disabled-with-reason BEFORE click; absent field → POST stays authoritative backstop returning 409 `generation_not_reproducible` before any deserialization or Attempt write (zero orphan rows).

**Phase H must not "upgrade" these rows.** No reconstruction from current Workflow/Preset state exists anywhere and none may be added (Phase F rejected approach #2). The ONLY sanctioned compatibility fallback is the active-workspace resolution for pre-workspace-id snapshots (§3 item 6). Migration seam stays non-destructive and idempotent (`legacy_mapping` skip).

---

## 5. WORKFLOW DELETION FUTURE-PROOFING (recommendation only — do not implement)

Current store facts (`studio_domain/store.py`): NO delete path exists for Workflow, Version, or Mapping; versions are write-once (`ImmutableVersionError`), mappings insert-once; only `delete_preset` exists (WorkflowPresets). Import atomicity (§7 G closure) removed the original deletion motivation; G §8 classified public deletion as a later lifecycle capability.

Consequence matrix if deletion is added later:

| Target deleted | History impact | Other impact |
|---|---|---|
| Workflow | None (provenance is copied; id becomes inert filter key) | Portability list chips null-safe; manifest export 404s; run-context 404s; imported-workflow rollback use-case |
| Version | None for History | Breaks: default-preset pointer, latest-version pointer, portability summary (`stale:null` honest "Needs check"), dependency routes 404. Versions are referenced by presets (`version-tied`) and mappings |
| Mapping | None | Run gating (`derive_version_state`) loses mapping → version becomes unrunnable for NEW runs; existing replays unaffected |
| Preset | None (`preset_name` copy persists) | Default-preset pointer dangles; experiments planned against it are unaffected (plans froze values) |

**Recommended referential policy (for a future lane):**
1. **Soft archival / tombstone over hard delete** for Workflows and Versions: add `archived_at`/`archived` flags, exclude from default lists, keep ids resolvable. Rationale: History carries `workflow_version_id` provenance forever; keeping the row costs nothing and preserves truthful round-trips (manifest export of an old version, audit of what produced a Generation).
2. **Prevent deletion (or require explicit cascade acknowledgment) when references exist**: Version has presets/mappings/portability rows; Workflow has versions. A cheap guard: refuse while child rows exist.
3. **Preset deletion may remain hard** (already exists) because every consumer that matters long-term reads copied values; UI should say "source preset unavailable" when a dangling `default_preset_id` or History filter key is encountered.
4. **Never cascade-delete History.** History rows are the durable product record; domain-store deletion must not touch `history_v2.db`, managed assets, or export records.
5. If hard deletion is ever required, write tombstone rows (id + name + archived_at) rather than erasing ids, so stale displays can distinguish "deleted" from "unknown".

---

## 6. LEGACY SNAPSHOT/PRESET STORES — INVENTORY & POLICY

| Store/file | Writer | Readers | Status |
|---|---|---|---|
| `.studio_snapshots.json` | `/comfymodal/studio/snapshots*` routes (`studio_routes.py:133–289`; soft-delete via `archived`) | same routes; Backend page (`web/studio-backend-snapshots.js`); fake backend mirrors all six routes | **UI-LIVE** (Backend page mounted in shell) |
| `.studio_presets.json` | `/comfymodal/studio/presets*` routes (`studio_routes.py:293+`) | same routes; Backend page; **Playground runtime selection** (`getRuntimePresets` → `listPresets` consumed at `studio-playground.js:521,810,1280,2826,3108`; `studio-experiment-mode.js:138,1246`); preset wizard | **UI-LIVE AND RUNTIME-AUTHORITATIVE for Playground single-run** (`POST /studio/run` body carries legacy `presetId`) |
| `.studio_workflows/versions/mappings/workflow_presets .json` | Workflow domain store | Workflows page, run adapter, portability | Canonical modern domain (not legacy) |
| Comparison profiles `user/default/comfy-modal/<dirname>/<profile>/workflow_api.json` | profile create/update | legacy experiment checkpoint enrichment (`__init__.py:_resolve_latest_workflow_for_profile`) | Legacy-experiment-only workflow store |
| `.presets/` prompt/image presets (`presets.py`) | testing-suite routes | testing suite tabs | Legacy testing-suite-only |
| `.run_history/<run_id>/{meta.json,thumbnail.webp,log.txt,timing.json}` | legacy runner writes (`run_history.py`, `studio_run_adapter` finalization) | `/comfymodal/run-history*` routes; `history_index.py` derived SQLite index; Playground recent-runs strip; migration seam (read-only) | **STILL WRITTEN** by the legacy recording path alongside History V2 mirroring |
| `.experiments/` (experiment_service REGISTRY) | legacy experiment engine | `/comfymodal/experiments*` routes; testing suite; Playground recent-runs filter | Legacy engine storage; terminal cells are MIRRORED into History V2 (`mirror_cell_terminal`) |
| `.studio_portability_reports.json` | portability GET | list/detail enrichment | Derived-only, regenerable |
| `.studio_workflow_compatibility.json` | PATCH compatibility | GET compatibility (Workflow detail display) | Display annotation sidecar |

**What Phase H MAY do:** remove/redesign UI writers and surfaces (Backend page snapshots/presets panels, legacy tabs) PROVIDED the route contracts below survive or every consumer is migrated first; keep files untouched; keep read-only readers.
**What Phase H should NOT do:** destructive migration/rewrite of any historical JSON/SQLite; delete `.run_history`/`.experiments`/`.presets` files; merge `.studio_presets.json` into `.studio_workflow_presets.json` silently (ids in History `preset_id` point at BOTH namespaces depending on era — merging would falsify provenance).

---

## 7. EXPERIMENT REFERENCES

Modern experiments (the ones History V2 renders):
- Created via `POST /comfymodal/studio/experiment-v2` (= `/comfymodal/history-v2/experiments`), which resolves Workflow/Version/Preset LIVE ONCE at acceptance (`experiment_modern_plan.resolve_workflow_axis_value` → `resolve_workflow_run_bundle`), then freezes everything into per-cell `CellPlan`s persisted inside `experiments.definition_json` in History SQLite.
- Resume/Retry/Cancel NEVER re-resolve the domain: post-restart reconstruction reads persisted cell plans verbatim, fail-closed (`_persisted_cell_plans`, `_reconstruct_scheduler_for_experiment`); cell retry creates a new attempt under the SAME Generation/snapshot; cancel operates on durable cell states.
- Cells link to Generations (`experiment_cells.generation_id`); cell favorite IS the Generation favorite (no second authority); cell History/detail ride the Generation-scoped routes; Original winner semantics are per-Generation logical-output groups.

Therefore: retiring the LEGACY Experiment UI/routes (`/comfymodal/experiments/compile|create|start|pause|stop-*|resume|clone|run-missing|checkpoints/*|cells/*|rerun-selected` — the testing-suite engine) does NOT affect modern Resume/Retry/Cancel/cell-History/favorite/note/Original, because those run entirely on `/comfymodal/history-v2/experiments/*` + `/generations/*` + persisted plans. Caveats:
1. Legacy-engine experiments continue to MIRROR terminal cells into History V2 (`history_v2_writer.mirror_cell_terminal`); stopping the legacy engine stops new mirrors but must not invalidate mirrored rows (they are self-contained generations with their own snapshots where meta provided them).
2. The Playground recent-runs strip still READS `GET /comfymodal/experiments` (§10) — that specific GET is not retirement-safe yet.
3. `GET /comfymodal/history-v2/experiments/{id}/status` is consumed by the Playground experiment controller (`studio-playground-run.js:854–861`, `studio-backend-api.js:200–239`) — modern, keep.

---

## 8. PORTABILITY REFERENCES

Portability attaches to WorkflowVersion (analysis unit invariant). Impact analysis:
- **Old version no longer latest:** version-scoped by design; report/cache keyed by `workflow_version_id`; list chips summarize only the LATEST version (`portability_summary` null otherwise). History unaffected (never reads portability).
- **Workflow UI consolidated:** panel/chips/checklist must survive intact (G handoff §38.7); no other surface may grow portability computation.
- **Cache disappears:** fail-open recompute; nothing else notices; History SQLite untouched.
- **Compatibility annotations disappear:** independent feature; absence changes nothing in portability (distinct vocabularies/endpoints enforced by G5/G12; duplicate-name collision cleaned).
- **Old imported Workflow exists:** foreign ids are provenance-only; deleting or keeping imported workflows has zero History effect.
**Conclusion:** portability is fully decoupled from History; consolidation may relocate the sidecar beside the domain stores but must keep it derived, TTL-free, and non-gating.

---

## 9. MODEL COMPATIBILITY VS PORTABILITY

- Compatibility = per-version human annotations (`compatible/incompatible/untested` + notes) in `.studio_workflow_compatibility.json`, served by `GET/PATCH /workflows/versions/{id}/compatibility` (`model_library_routes.py:302–364`), plus the frozen `compatible_models` list on the Version record. Consumed by Workflow detail display ONLY.
- **No History/replay path depends on them** (grep over `history_v2_*`, `experiment_modern_*`, `canonical_execution`, `studio_run_adapter` finds no consumer; hits are unrelated comments).
- Preservation requirements: keep the `/compatibility` naming and endpoints distinct from portability (G handoff §38.3: do not merge/rename/unify); keep `compatible_models` on the immutable Version record intact (it is part of the version record, and versions are write-once — stripping it would violate immutability); annotation sidecar may be archived but its absence must remain a benign display state ("untested"), never an error.

---

## 10. LEGACY API RETIREMENT RISK (routes that LOOK obsolete but are NOT)

| Route | Apparent status | Actual consumers today | Verdict |
|---|---|---|---|
| `GET /comfymodal/run-history` | legacy list | **Playground recent-runs strip** (`studio-playground.js:396`); bridge repository mode (`history-v2-repository.js:883`); legacy History page (orphaned); fake backend | CANNOT delete with a visual surface |
| `PATCH /comfymodal/run-history/{id}/annotations` | superseded by V2 favorite/note | Bridge repository mode (`history-v2-repository.js:921,933`); declared "frozen-for-bridge" by Phase F (one-way migration source) | Keep until bridge mode retires |
| `POST /comfymodal/run-history/{id}/save` | legacy save pipeline | `saveRunHistoryOutput` in `studio-backend-api.js:405`; fake backend; F7 deliberately did NOT reuse it | Keep while exposed; do not port V2 export onto it |
| `GET /comfymodal/run-history/{id}` `/logs` `/timing` | legacy detail | legacy History page (orphaned), testing suite diagnostics, fake backend | Low risk; logs/timing have no V2 equivalent yet — verify no consumer before removal |
| `GET /comfymodal/experiments` | legacy aggregate list | **Playground recent-runs strip** (`studio-playground.js:397`); testing-results; fake backend | CANNOT delete yet |
| `GET /experiments/{id}`, `POST /experiments/{id}/stop-now` | legacy engine control | `studio-backend-api.js:157,169` (legacy aggregate experiment surface); testing suite | Keep until legacy aggregate UI retired |
| All other `/comfymodal/experiments/*` (compile/create/start/pause/stop-after-current/stop-now/resume/clone/run-missing/checkpoints/*/cells/*/rerun-selected/rerun) | legacy testing engine | testing suite tabs (`testing-*.js`), experiment_runner/service/scheduler/lease | Retirement requires retiring the testing suite surface with it; mirrored History rows must stay valid |
| `GET/POST/PATCH/DELETE /comfymodal/studio/snapshots*` (+duplicate) | legacy snapshots | **Backend page (mounted)**; fake backend parity specs | Not UI-obsolete |
| `GET/POST/PATCH/DELETE /comfymodal/studio/presets*` (+duplicate) | legacy presets | **Backend page AND Playground runtime preset selection + wizard**; fake backend | **Highest-risk "legacy" store — it is the live single-run selection authority** |
| `POST /comfymodal/studio/run` | legacy single-run acceptance | Playground direct run (`runStudioPreset`) | Live production path |
| `GET /comfymodal/history` (ComfyUI unified) | platform history | Playground recent-runs merge | Platform route; leave alone |
| `GET /comfymodal/studio/outputs/{filename}` (+ legacy output dir fallback) | legacy image serving | normalizers/playground legacy runs | Keep while legacy-run images render |
| Fake-backend mirrors of ALL of the above | test infrastructure | 26 fake spec files incl. `studio-fake-experiments.spec.mjs`, `studio-fake-history.spec.mjs` | Removing a production route requires removing its fake + specs in the same contract change |

---

## 11. DATA MIGRATION NECESSITY

| Store | Does H NEED to migrate it? | Recommendation |
|---|---|---|
| `.run_history` meta.json | No. `LegacyMigrationSeam` exists, is idempotent, non-destructive, and is currently invoked by TESTS ONLY (no startup wiring found). Rows already migrated are self-contained | Leave inert/readable. Optionally wire an explicit (not automatic) migration command later; never rewrite legacy files |
| `.experiments/` legacy engine data | No. Mirrored terminal cells already exist in History V2; legacy engine owns its own history | Leave untouched while the testing suite exists |
| `.studio_snapshots.json` | No | Leave; retire writers with the Backend surface if desired |
| `.studio_presets.json` | **No file migration; only a careful CONSUMER migration** (Playground selection → Workflow-domain presets) if H consolidates preset authority. Never merge files in place | Two-step: new selection path ships and proves parity → then legacy routes become bridge-only |
| `.presets/` prompt/image presets | No (testing-suite-scoped) | Leave |
| `history_v2.db` | No schema change needed for retirement; SCHEMA_VERSION stays 2; additive ALTER pattern only | Preserve `legacy_mapping` table even if seam is dormant |
| Portability sidecar / compatibility sidecar | No (derived/display) | Optional relocation only |

Overriding principle: prefer leaving historical data inert/readable over rewriting historical JSON/SQLite; migrate only for clear correctness value (none identified).

---

## 12. STALE / TOMBSTONE SEMANTICS (future design)

Minimum fields History ALREADY has for meaningful provenance without any source object: `workflow_id`, `workflow_version_id`, `preset_id`, `preset_name` (denormalized), snapshot-embedded `workflow_name` (via `workflow_json`/`preset_snapshot.workflow_name`), `workflow_hash`, `created_at`, `model_stack`, `prompt_text`. That is sufficient to render "source workflow unavailable" / "source preset unavailable" states without crashing TODAY (name renders from snapshot; ids render as opaque keys).

Future UX rules when intentional removal lands:
1. Dangling id + snapshot name present → render copied name verbatim (current behavior; already truthful).
2. Dangling id + no name → render neutral "Unknown source" from null `workflow_name`; never print the raw id as a name (existing `_workflow_name` rule).
3. Action buttons must derive from `replay_capable` + durable attempt state only — never from source-object existence (already true server-side; keep it true).
4. If tombstones are added to the domain store later (§5), History MAY enrich display ("source workflow deleted <date>") but must not REQUIRE it.

---

## 13. REGRESSION TEST PLAN (design only — no implementation)

1. **Historical Generation opens after legacy UI removal:** seed a generation whose `workflow_id`/`preset_id` reference records absent from ALL domain stores; assert feed card + detail render with snapshot-derived name, actions gated solely by durable state, zero 4xx/5xx in network log.
2. **RequestSnapshot replay with source Workflow unavailable:** full valid snapshot; delete/not-seed the Workflow/Version/Mapping/Preset records; POST `/generations/{id}/original` → 200 `original_created`, plan delta allow-list green, one attempt, assets attached. (Proves deletion-independence.)
3. **Irreproducible legacy row stays viewable:** row with `missing_request_snapshot` / `missing_execution_plan` / `snapshot_hash_mismatch` → detail renders, action disabled-with-reason, click-path 409 `generation_not_reproducible`, ZERO attempt rows, full-table dump equality (projection performs no writes).
4. **Original winner semantics unchanged:** preview→Original conversion delta limited to allow-list; rerender newest-wins; retained winner after failed retry; resume preserves frozen mode.
5. **Experiment cell History unchanged:** cell favorite == generation favorite through the SAME route; cell retry under same Generation/snapshot; post-restart resume reconstruction fail-closed with malformed plan sets; cancel eligibility matrix.
6. **Portability cache deletion irrelevant:** delete `.studio_portability_reports.json` mid-session → list chips null/"Not analyzed", detail recomputes, History byte-identical, replay unaffected.
7. **Compatibility annotation removal/absence does not alter replay:** delete `.studio_workflow_compatibility.json` → replay/resume identical; Workflow detail shows untested defaults; portability vocabulary untouched.
8. **Deleted/archived preset produces truthful stale display:** generation with `preset_id` pointing at a deleted preset (both stores) → `preset_name` copy renders, filter yields nothing, no error; default-preset pointer dangle handled.
9. **Workspace-unresolved refusal stays pre-claim:** remove workspace from registry → Original/Resume return 503 with machine-readable reason BEFORE any attempt exists (no orphan queued).
10. **Bridge/migration integrity:** `LegacyMigrationSeam` re-run is idempotent via `legacy_mapping`; legacy files byte-identical after migration; PATCH legacy annotations still works while bridge exists.
11. **Fake-parity guard:** any route removed from production must be removed from `fake-server.mjs`/`fake-backend.mjs` in the same change, and vice versa (route-registry count assertion updated deliberately, not silently).

---

## 14. PHASE-H HARD BLOCKERS — DO-NOT-DELETE LIST

**DO NOT DELETE X UNTIL Y:**

1. **DO NOT DELETE `GET /comfymodal/run-history` until** the Playground recent-runs strip stops consuming it (`web/studio-playground.js:396`) and the bridge repository mode (`history-v2-repository.js`) is retired.
2. **DO NOT DELETE `PATCH /comfymodal/run-history/{id}/annotations` until** the bridge repository mode is gone AND a final one-way annotation migration pass is confirmed complete (Phase F froze it for exactly this reason).
3. **DO NOT DELETE `GET /comfymodal/experiments` until** the Playground recent-runs strip stops consuming it (`web/studio-playground.js:397`).
4. **DO NOT DELETE `/comfymodal/studio/presets*` routes or `.studio_presets.json` until** Playground runtime preset selection (`getRuntimePresets`/`listPresets` in `studio-backend.js`/`studio-backend-api.js`, consumed by playground + experiment mode + wizard) is migrated to a successor authority AND History's mixed-era `preset_id` provenance handling is re-verified. This is the highest-risk retirement in Phase H.
5. **DO NOT DELETE `POST /comfymodal/studio/run` until** the Playground single-run path is re-homed; it is the live acceptance path that freezes RequestSnapshots.
6. **DO NOT DELETE `/comfymodal/studio/snapshots*` until** the Backend page surface is retired or migrated (it is mounted in `studio-shell.js` today).
7. **DO NOT DELETE the legacy testing-suite experiment routes (`/comfymodal/experiments/compile|create|start|...`) until** the testing suite tabs are retired with them; mirrored History rows must remain readable afterward regardless.
8. **DO NOT REMOVE the legacy `.run_history` reader paths (`REGISTRY.history()`, `history_index.py`) until** a decision is recorded that no further migration/diagnostic read is needed; the migration seam (`history_v2_migration.py`) and `legacy_mapping` table must survive even if dormant.
9. **DO NOT REMOVE `request_snapshots.execution_plan_json` / `deployment_identity_json` columns, the `legacy_mapping` table, or any `replay_capable` projection code — ever** (they are the replay authority and the truthful-irreproducibility mechanism).
10. **DO NOT REMOVE the workspace-resolution fallback in `_resolve_replay_workspace` / `_resolve_workspace_dict` (`.modal_workspaces.json`)** until pre-workspace-id snapshots no longer exist in user data; removing it converts currently-reproducible Generations into irreproducible ones.
11. **DO NOT MERGE model-compatibility (`/compatibility`, `.studio_workflow_compatibility.json`, `compatible_models`) with portability** (G handoff §38.3); do not strip `compatible_models` from Version records (write-once immutability).
12. **DO NOT DELETE the portability sidecar handling/fail-open code or relocate `.studio_portability_reports.json` away from the domain-store convention**; keep it derived, TTL-free, non-gating.
13. **DO NOT ADD any live Workflow/Version/Preset lookup to History render or replay paths** "for freshness" — it would convert today's deletion-tolerance into a new failure mode and violate Phase F invariant 1.
14. **DO NOT run destructive migration over any historical store** (`.run_history`, `.experiments`, `.presets`, `.studio_snapshots.json`, `.studio_presets.json`, `history_v2.db`): leave inert/readable per §11.

---

## FINAL SCOPE NOTE

Deploy / live / GPU / generation / commit / push by this batch: **NONE**. Audit file only.
