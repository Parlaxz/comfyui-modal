# Phase F3 — History Downloads / Export & Managed-Asset Semantics Audit (2026-08-22)

**Lane:** Phase F — History Actions & Settings Consumers, Batch F3 (downloads/export audit)
**Type:** READ-ONLY audit. No production code, tests, deploy, Modal, GPU, live generation, commit, push, branch, or reset performed.
**Base:** Phase E COMPLETE (`PHASE_E_FINAL_CLOSURE_2026-08-22.md`, `PHASE_E7_LIVE_PREVIEW_ORIGINAL_GATE_2026-08-22.md`).

---

## 1. Executive verdict

**F3 verdict: EXPORT IN HISTORY V2 IS SCAFFOLDING-ONLY — the persistence model exists end-to-end (schema → repository → model → one read projection) but has ZERO producers and ZERO action consumers.** The only working configured-folder export in the repo is the LEGACY `POST /comfymodal/run-history/{run_id}/save` pipeline, which is unreachable from the mounted History V2 UI, hardcodes `output_index: 0` at every caller, and refuses remote-only `modal://` generations — which is exactly what modern cloud generations are unless local auto-save materialized them. The mounted History tab (`renderHistoryV2`) exposes **no Download and no Save/export action at all**; its sole export surface is a read-only, generation-level, Preview/Original-collapsing "Export State" label. Browser Download exists only in legacy/orphaned surfaces (old unified-history overlay, playground cell overlay, legacy testing results) and is a pure managed-asset blob save that writes no export state. Phase E's `modal://` URI-aware semantics are intact here (no false-missing regression), but every F-relevant export behavior (duplicate prevention, missing-export detection, Preview/Original separation, multi-output, Experiment export) is MISSING or LEGACY-ONLY in the live UI.

Per-area classification:

| Area | Classification |
|---|---|
| Export data model (V2) | **PARTIAL** (model/schema/repository/projection exist; no producer, no digest, no per-output projection) |
| Managed-asset fetch | **COMPLETE** (local + `modal://` + sha256 verify; correctly named "managed asset serving") |
| Browser Download | **LEGACY-ONLY** in live surfaces (playground/testing); **MISSING** in History V2 |
| Configured output-folder export | **LEGACY-ONLY / BROKEN for remote-only assets** (works only against legacy run-history records with local materialized paths) |
| Preview vs Original export separation | **BROKEN/INCONSISTENT** (backend per-asset capable; API+UI collapse to one generation flag) |
| Duplicate export prevention | **PARTIAL (legacy only)**; **MISSING** in V2 |
| Missing exported-file detection | **PARTIAL (legacy, lazy)**; **MISSING** in V2 (`MISSING` state never set nor surfaced) |
| Multi-output export | **MISSING** in UI (backend `output_index` capable; all callers hardcode 0) |
| Experiment export | **MISSING** (cell browser-download legacy-only; no configured-folder export, no bulk) |
| Deletion | **NOT IMPLEMENTED** (no History delete routes; conflation risk is future, flagged in §11) |

---

## 2. Terminology and canonical semantics

Authoritative distinctions observed in code:

- **Managed History asset** — the authoritative internal copy/reference. Stored as `assets.managed_path`: either a local file path or a remote `modal://<workspace>||<backend_path>` reference (`history_v2_store.py:115-132`). Served by `GET /comfymodal/history-v2/assets/{asset_id}`. This is what Phase E made URI-aware.
- **Exported copy** — a user-facing copy in the configured output folder. Represented (in V2, nominally) by `export_records.destination_path`. **Not the same thing** as the managed asset, and not the same as a browser download.
- **Browser download** — client-side blob save of a fetched managed asset (`studio-ui.js:_buildDownloadButton`; `testing-results.js`). Writes no server state. Button copy says "Download image" — mechanically it is *save-managed-asset-to-disk*, not export.
- **Generate Original** — replay action producing a NEW managed Original asset (`POST .../original`, `/original/retry`). NOT export.
- **View Original** — explicit one-shot managed fetch for display (`studio-history-v2-detail.js:379-403`). NOT export; E7 proved it distinct from Generate Original on the wire.
- **Auto-save (execution-time)** — `auto_save_local` + `save_folder` materialization during a run (`modal-node.js`, `result_delivery.py`, `v2_experiment_invoker.py`). Adjacent third concept; must not be conflated with History export.

No code path equates these five today, but the mounted UI offers verbs for only two of them (View Original, Generate Original); Download/Export verbs are absent precisely where the managed asset lives (History V2).

---

## 3. Export persistence model

- **Enum:** `ExportState = {not_exported, exported, missing, failed}` (`history_v2_models.py:146-149`).
- **Record:** frozen `ExportRecord{export_id, asset_id, state, updated_at, destination_path?, exported_at?}` (`history_v2_models.py:388-409`).
- **Table:** `export_records(export_id PK, asset_id FK→assets ON DELETE CASCADE, destination_path, exported_at, state, updated_at)` + `(asset_id, updated_at)` index (`history_v2_store.py:134-143`).
- **Repository:** `upsert_export_record(asset_id, ...)` — ONE row per `asset_id`, upsert keyed on asset_id (`history_v2_repository.py:1266-1305`); `get_export_record(asset_id)` (1307-1315); generation detail joins export rows for the generation's assets (`get_generation`, ~522-546).
- **Only projection:** generation detail `item["export_state"] = "exported" if any(er.state=="exported") else "none"` (`history_v2_routes.py:1225-1229`).
- **Producers: NONE.** The only caller of `upsert_export_record` in the repo is `tests/test_history_v2_api.py:258`.

**Binding: export is tied to `asset_id`** — not `logical_output_key`, not Generation. Implications:

1. Per-variant separation is *representable* (a Preview asset row and an Original asset row are independent) — the model can satisfy Phase E's "separate export state" requirement.
2. Rerender/retry creates a NEW Original asset (newest-wins); an export record pinned to the superseded asset_id silently stops representing "this output was exported." No logical-key rollup and no migration of export state to the newest winner exists.
3. No digest/hash/byte-count of exported bytes is stored on the export record (the managed asset's `sha256` lives on `assets`), so a re-export after a lease location refresh cannot be verified against the earlier copy.
4. Overwrite behavior is undefined beyond "upsert replaces destination_path/state" — re-export to a new folder loses the old destination with no history.
5. `ON DELETE CASCADE` couples export rows to asset deletion — see §11.

---

## 4. Browser download behavior

Surfaces exposing a Download control today:

| Surface | File | Live? | Target |
|---|---|---|---|
| Unified-history preview overlay | `web/studio-history.js:916` → `studio-ui.js:875` | **NO — orphaned**: `studio-shell.js:22` mounts `renderHistoryV2`; nothing imports `renderHistory` | `nr.imageUrl` = featured/primary asset (`resolveRunImageUrl`: primary_asset_id → `/assets/<id>`, else `/studio/outputs/<path>`) |
| Playground experiment-cell overlay | `web/studio-playground.js:4827` → same `_buildDownloadButton` | YES | `entry.outputUrl` (the cell's displayed image) |
| Legacy testing results cell cards | `web/testing-results.js:396-438` | Legacy suite UI | `/comfymodal/assets/<assetId>` per cell |

Mechanics (identical implementations): `fetch(imageUrl)` → blob → extension from `blob.type` → sanitized filename (`meta.filename || output_path || primary_asset_id || prompt || alt`, basename, `[^a-zA-Z0-9_-]→_`, ≤100 chars; testing uses `cell_key`) → object-URL anchor click, revoked after 100 ms. Failure surfaces via button title / "DL failed" chip; no navigation.

Findings:

- **Which asset:** always the *displayed* asset — thumbnail/preview/primary. There is **no "Download Original"** anywhere; even after View Original loads the full PNG inline there is no action to save it.
- **Preview vs Original:** indistinguishable to the download path; a Preview WebP downloads as `.webp` labeled generically "image."
- **Selected vs featured:** featured/primary only; no per-output picker.
- **Remote Original lazy fetch:** clicking Download on a preview/thumb does NOT trigger an Original GET. View Original fetches exactly once on click (E7 §8 HAR-proven; zero automatic asset GETs on render). No regression.
- **Hidden when absent:** the button renders only when a URL exists (`if (opts.imageUrl)`), so it hides for no-image records — but there is no Original-presence gating because no Original download exists.
- **History V2 (the mounted History): NO Download button at all** — feed cards have favorite/open only (`studio-history-v2.js`); detail overlay has View Original / Generate Original / Retry / Generate Again / note / favorite only (`studio-history-v2-detail.js`); experiment detail likewise (`studio-history-v2-experiment.js`).
- Browser download performs **no export**: no `export_records` write, no destination folder, no dedup.

---

## 5. Configured output-folder export

Chain that actually exists (legacy):

```
Settings (.modal_settings.json: output_format, quality, webp_lossless_compression,
          save_folder, save_metadata_sidecar)
  → POST /comfymodal/run-history/{run_id}/save   (__init__.py:7007-7110, per-run lock,
          meta re-read under lock)
    → studio_run_adapter.save_run_history_output (2071-2480)
        · idempotency gate: extra.output_saved + output_saved_index + os.path.isfile(prev_path)
        · resolve_run_output_path: extra.output_paths[i] → top-level/legacy output_path (i=0)
          → asset registry fallback (primary_asset_id / asset_ids[i]; thumbnail→parent;
            modal:// REJECTED "remote-only asset")
        · optional conversion via output_converter.convert_image_bytes
        · output_saver.save_output_image (<folder>/images + <folder>/metadata sidecar,
          _unique_filename anti-collision)
    → persist_state_fn → history.update_run(extra.output_saved*) → history-index upsert
```

Does it work today?

- **For legacy run-history records with local materialized paths: YES** — deterministically proven by `tests/test_run_history_save.py` (29 tests incl. route-level happy path/idempotency).
- **For modern runs: CONDITIONAL.** Modern Singles/Experiments dual-write into the legacy store (`studio_workflow_run._modern_save_history_success` → `REGISTRY.history().record_run`, ~973/1147) carrying either `meta.output_paths` (local materialized) or descriptor-only `primary_asset_id`. Descriptor-only ⇒ registry path is `modal://` ⇒ `resolve_run_output_path` refuses (`studio_run_adapter.py:2173-2177`). In the current remote-first architecture (managed bytes live in Modal volumes; local files exist only when auto-save materialized them), **Save fails with "no materialized local path (remote-only asset)" for typical cloud generations.**
- **From the mounted History V2 UI: UNREACHABLE.** No V2 surface calls `saveRunOutput`; the endpoint is legacy-store-only and knows nothing about `history_v2.db` generations/assets or `export_records`.
- **Stale/legacy paths:** `save_folder` default migrated off `ComfyUI/output/modal/` to external `<data-root>/outputs/modal` (`output_saver._normalize_save_folder`/`_resolve_save_folder`; `tests/test_output_saver_paths.py`); `.run_history` → `run-history` dir mapping in `local_artifacts.py`. No other stale output-folder consumers found.
- **V2 export service: DOES NOT EXIST.** No `POST /history-v2/.../export`, no filesystem writer for V2, no bridge from the legacy saver into `upsert_export_record`.

---

## 6. Preview vs Original separation

Backend presentation separates variants correctly per logical output (`_build_outputs`: `thumb_url` / `preview_url` / `original_url` / `original_failed`; `history_v2_routes.py:333-365`), and Phase E proved the lifecycle scenarios for *generation* state (A preview-only; C/D original added; E/F mixed; G failed-original-with-preview-retained badge "Original failed — preview retained").

Export-state separation is **not satisfied**:

- The single API field collapses everything: `"exported" if ANY export record is exported else "none"` — one bit per GENERATION (`history_v2_routes.py:1225-1229`). Scenario E (Preview exported, Original not) and F (Original exported, Preview not) are **indistinguishable**; "exported then file deleted" projects `"none"` because `missing` is never checked.
- The UI renders one read-only row: `Export → State: Not exported` (`studio-history-v2-detail.js:785-787`, `_exportStateLabel` 504-509). No per-slot export indicator in the Preview/Original slots (`buildPreviewOriginalSlots`), no export action per variant.
- Because no producer exists, scenarios B/D cannot occur through the product today; the collapsed flag is always `"none"` in practice (fixtures hardcode it too — `tests/phase_e_fixtures.py:101`).

**Verdict: BROKEN/INCONSISTENT** — model capable (per-asset rows), API contract and UI collapsed.

---

## 7. Duplicate export detection

Product direction: if the exact asset is already exported, avoid a redundant Download/Save.

- **What is tracked:**
  - Legacy save: exact prior `output_saved_path` + `output_saved_index` + **file-existence probe** (`os.path.isfile`) under a per-run lock. No content-digest comparison (byte identity is assumed via the gate, not verified).
  - V2: `export_records.state` could answer "already exported," but **nothing queries it for gating**; no route, no frontend read beyond the collapsed label.
  - Browser Download: tracks nothing; always re-downloads.
- **Already exported && file still exists:** legacy UI hides the Save button (`_isRecordOutputSaved` / `entry.attempt.output_saved`); backend returns `already_saved: true` with the recorded path (tests `test_retry_after_success_returns_same_path_no_duplicate`, `test_happy_path_is_idempotent_across_requests`). V2 UI shows only the label; no action exists to be suppressed.
- **Export record exists && file missing:** legacy gate detects at the *next save attempt* (lazy), deletes nothing, and **re-exports**, returning a fresh path (`test_deleted_recorded_file_allows_resave`). Frontend caveat: the Save button stays hidden on the stale `output_saved===true` flag until reload — minor UI-truth lag (backend remains correct). V2: `missing` never produced, never projected (collapses to `"none"`); no re-export path.

**Verdict: PARTIAL (legacy only); MISSING in V2.**

---

## 8. Missing exported file

Expected: exported file deleted externally → managed History asset remains valid → export marked missing → user may export again.

- **Legacy:** satisfied lazily. Detection time = next save click (existence probe in the idempotency gate). Managed source untouched; re-save allowed; new state persisted. No proactive scan; the index keeps `output_saved=true` until a save attempt corrects it.
- **V2:** `ExportState.MISSING` defined but **nothing sets, projects, or acts on it**. The projection's `any(er.state == "exported")` means a `missing` row degrades to `"none"` — the UI cannot distinguish "never exported" from "export lost."
- **Remote managed assets falsely considered missing? NO — protected.** `_asset_is_structurally_available` returns True for any `modal://` reference without touching the local filesystem (`history_v2_routes.py:235-239`), so availability/feed projections never mark remote assets missing due to local path checks (Phase E semantics preserved). Truthful failure only at actual serve time: local-missing → 404 "asset file not found" (1490-1491; `test_c14_asset_endpoint_regression_missing_reference_404` proves deleted backing file ⇒ 404, never stale bytes); remote-missing → 404 after bounded retries, other failures → 502 (1475-1487). The E7 lease-repair case (stale workspace pointer) was an availability bug fixed upstream; future export logic must reuse the same "reference ≠ absence" rule.

**Verdict: legacy PARTIAL (lazy but correct); V2 MISSING (state dead-lettered).**

---

## 9. Multi-output

- One Generation CAN hold multiple logical outputs: `output_count` counts groups; each output carries independent `thumb_url/preview_url/original_url`; per-output "Set as featured" menu (`openOutputMenu` → `PATCH /featured` by `output_index` or `asset_id`); featured resolution through group membership (`_featured_output_index`).
- **Export/download per output: NONE in History V2** (no download at all). The backend does NOT assume the featured output is the only exportable one — but the UI offers non-featured outputs nothing beyond "Set as featured."
- **Legacy save backend is index-capable:** `output_index` validated, range-checked, per-index resolution incl. `asset_ids[i]` (`test_selected_output_index_saves_only_that_output`, `test_out_of_range_output_index_errors`) — yet **every frontend caller hardcodes `{output_index: 0}`** (`studio-history.js:903`, `studio-playground.js:4812`, `:5316`). Non-featured outputs are unreachable from the product.
- **Filename collisions:** server save uses `_unique_filename` (no overwrite), but `save_run_history_output` always passes `index=0` to `_build_filename` regardless of the real `output_index` (`studio_run_adapter.py:2417`) — two different outputs saved in the same second share a base name (disambiguated only by the uniquifier); the real index survives only in the sidecar `extra_meta`. Browser download names collide trivially across outputs of the same prompt (browser appends "(1)").
- **Bulk export: none anywhere** (no multi-select, no ZIP, no batch route).

**Verdict: MISSING (UI); PARTIAL (legacy backend capability, with an index-fidelity naming bug).**

---

## 10. Experiment

- **Modern Experiment detail** (`studio-history-v2-experiment.js`): per-cell note/favorite/Generate Original via the cell's own `generationId` (E parity). **No download, no configured-folder export, no bulk export.** Cells inherit the collapsed export story (experiment detail does not even project `export_state`).
- **Playground cell overlay** (live): browser Download of the cell image + Save wired to legacy `saveRunOutput(apiBase, cellRunId, {output_index: 0})` (`studio-playground.js:4805-4825`). Works only when the cell's run resolves in the legacy store AND has a local materialized path; remote-only cells error "remote-only asset." Saved-state flag hides the button thereafter.
- **Preview-only / Original-unavailable cells:** browser download yields the preview bytes; Save behaves as above; no Original-specific action exists.
- **Bulk Experiment export: DOES NOT EXIST** — no route, no UI, and no in-repo roadmap artifact proposing ZIP/bulk; none is proposed here per instructions.
- Legacy `testing-results.js` per-cell download remains the only per-cell affordance outside Studio.

**Verdict: MISSING for modern Experiments; LEGACY-ONLY partial affordances elsewhere.**

---

## 11. Deletion semantics

- **History V2 implements NO deletion.** Routes: feed, generation detail, original, original/retry, experiment detail, favorite/note/featured (generations + experiments), asset serve. No DELETE method; `history_v2_repository.py` contains no `DELETE FROM`/delete method. Legacy run-history likewise has no delete route. Existing DELETE routes are unrelated domains (models, comparison profiles, prompt presets, preset images, studio backends).
- **Latent conflation hazards to design against when deletion lands (do NOT implement now):**
  1. `export_records.asset_id FK ON DELETE CASCADE` — deleting a Generation/asset would silently destroy export bookkeeping while the user-facing exported FILE remains on disk (orphan file without record).
  2. Deleting an exported copy must never touch `assets.managed_path` (local file or `modal://` volume bytes) — the managed asset is authoritative.
  3. Deleting the managed asset must not imply deleting the exported copy or vice versa. The roadmap's "distinguish what is being removed" maps onto three targets — managed asset / exported copy / History record — none deletable today, so no active defect, but the schema cascade already biases toward conflation (1).

---

## 12. Output-settings consumption (narrow, export-relevant only)

| Setting | Store | Consumers |
|---|---|---|
| `save_folder` | `.modal_settings.json` (+ localStorage `comfymodal_save_folder`, default `output/modal`, normalized/migrated) | legacy `/run-history/{id}/save` → `output_saver`; prompt-run auto-save (`__init__.py:2701/2718` via `modal_options`); `v2_experiment_invoker.py:186` (runtime-side auto-save) |
| `save_metadata_sidecar` | `.modal_settings.json` (default true) | same two paths |
| `output_format` / `quality` / `webp_lossless_compression` | `.modal_settings.json` | conversion inside legacy save + runtime result delivery |
| `auto_save_local` | localStorage `comfymodal_auto_save_local` | execution-time materialization (modal-node/settings → modal_options) |
| Filename rules | none (fixed `_build_filename` template: timestamp+workflow+seed+index) | — |

Not audited (per scope): all other Settings tabs. Note: **no V2 export settings exist.** A future V2 export service must decide whether to reuse `save_folder/format/quality/sidecar` (recommended for consistency) and whether `auto_save_local`-materialized files count as pre-existing exports — they currently do NOT create `export_records`, so they are invisible to any future duplicate-prevention gate. That semantic decision belongs to F explicitly.

---

## 13. Test coverage inventory (deterministic)

Present:

- **Local managed download/serve (V2):** `test_history_v2_api.py::test_managed_asset_serves_correct_file` (523), `test_asset_route_rejects_invalid` (534), `test_c14_asset_endpoint_regression_missing_reference_404` (679 — deleted backing file ⇒ truthful 404, never stale bytes); fake-browser `studio-fake-history-v2.spec.mjs` #2/#7/#8 (detail images served; missing original 404 doesn't break card).
- **Remote `modal://` projection semantics:** `test_phase_e_history_projection.py` (URI-aware availability; remote originals projected, not failed), `test_e2c_history_handoff.py`, `test_phase_e_logical_output_integration.py`. Live-only: E7 §8 proved actual `modal://` serve 200 + explicit View Original.
- **Original explicit display fetch (not file download):** `studio-fake-phase-e-original.spec.mjs` "detail UI: Generate Original keeps Preview, then surfaces View Original" (+ retry/again/busy/irreproducible/failure-retention matrix); no-eager-fetch proven live (E7 HAR: zero automatic asset GETs).
- **Configured-folder export success/duplicate/missing (LEGACY):** `tests/test_run_history_save.py` — 29 tests: happy path, idempotency across requests, retry-returns-same-path, deleted-recorded-file-allows-resave, selected-index-only, out-of-range, per-format parity, sidecar on/off, configured folder used, experiment-cell resolver + thumbnail reparent + remote-only rejection, missing/empty/non-image/unresolvable errors, state-persist failure, route-level 400/404.
- **Multi-output (legacy backend):** selected-index and range-error tests above.

Exact gaps (no deterministic test exists):

1. **V2 export success** — no producer exists; blocked on implementation.
2. **V2 duplicate-export prevention** — absent.
3. **V2 missing-exported-file detection/projection** — `ExportState.MISSING` never exercised end-to-end (only the collapsed `"exported"` projection is asserted, `test_generation_detail:283`).
4. **Preview/Original SEPARATE export state** — untestable in the current single-field API shape.
5. **History V2 Download action** — no UI, no test.
6. **Preview download / Original explicit FILE download** — no such action anywhere; untested by construction.
7. **`modal://` branch of `GET /history-v2/assets/{id}`** — no deterministic unit test mocking `modal_client.read_output_asset` for THIS route (live-proven in E7; route retry/404/502 branches deterministically untested).
8. **Multi-output export from any frontend path** — callers hardcode index 0; nothing pins the `index=0` filename-fidelity behavior either.
9. **Experiment cell configured-folder export for MODERN cells** — adapter-seam tests cover legacy resolution only; no cell download/save fake-browser test.
10. **Negative no-eager-fetch assertion** ("zero asset GETs during detail render") — implicit in fake specs, never asserted negatively; moot for Download until one exists.

---

## 14. Exact implementation gaps (for later F batches — NOT implemented here)

1. **V2 export service + route** (e.g. `POST /history-v2/generations/{id}/exports` with `{logical_output_key|output_index, variant: preview|original}`) that fetches managed bytes (local or via the existing `read_output_asset` seam), applies configured format conversion, writes via `output_saver`, and calls `upsert_export_record(state="exported", destination_path=...)`.
2. **Per-variant export-state projection**: replace the collapsed generation-level `export_state` with per-output/per-variant fields (e.g. `outputs[i].preview_export_state` / `.original_export_state` ∈ not_exported/exported/missing/failed), surfacing `missing` truthfully instead of collapsing to `"none"`.
3. **Duplicate-export gate**: before writing, consult `export_records` (+ destination existence probe, optionally digest verify against `assets.sha256`) and return `already_exported` so the UI can suppress/disable Save for an exact already-exported asset.
4. **Missing-export detection + re-export**: project `missing` when `destination_path` no longer exists (on-read check is sufficient initially), and allow re-export (upsert already supports it).
5. **History V2 Download actions**: per-output Download (Preview and Original separately), including a save path for an already-loaded View Original blob; explicit naming distinguishing managed-download from folder-export; hide/gate by variant availability (no Original download offered when `original_available=false`).
6. **Multi-output reachability**: thread real `output_index` through every save/download caller (currently hardcoded 0) and pass the true index into `_build_filename` (fixes the `index=0` fidelity bug at `studio_run_adapter.py:2417`).
7. **Experiment parity**: expose the same per-cell export/download actions in experiment detail (cells already carry `generationId`; reuse generation-scoped routes). Bulk/ZIP remains out of scope unless a roadmap artifact introduces it.
8. **Rerender/export interaction policy**: decide whether an export record pinned to a superseded Original asset marks the NEW winner as not-exported (recommended: resolve export state per logical key against the newest usable asset, keeping asset_id rows as provenance).
9. **Deletion design guard**: when History deletion is implemented, split targets (managed asset / exported copy / record) and revisit the `ON DELETE CASCADE` on `export_records.asset_id` so removing a record never implies removing a user file and vice versa.
10. **Test debt**: close gaps §13.1–§13.10 alongside items 1–7 (each new behavior lands with its deterministic test; add the negative no-eager-fetch assertion once Download exists).

---

## 15. Batch statement

- Files modified by THIS batch: `PHASE_F3_HISTORY_EXPORT_DOWNLOAD_AUDIT_2026-08-22.md` (this audit) ONLY.
- Production code: untouched. Tests: untouched. Deploy/Modal/GPU/live generation: NONE. Commit/push/branch/worktree/reset/revert/stash/clean: NONE. Worktree left dirty as found.

---

## 16. Reconciliation Note — F6 Browser Download Landing (2026-08-23)

Gap §14.5 (History V2 Download actions) and §13.5–§13.7, §13.10 are now substantially closed by the Phase-F frontend batches in the shared tree:

- **Browser Download is first-class in History V2** (concurrent F3-download lane): per-output Download Preview / Download Original (truthful Thumbnail labeling), experiment cell-pane parity via each cell's own projection, explicit-fetch-only with per-target in-flight dedupe, MIME-authoritative extensions, deterministic collision-free filenames, truthful failure + recovery, and ZERO export-record writes / zero eager Original GETs. Module: `web/history-v2-browser-download.js` (+ detail/experiment wiring); coverage: `studio-fake-history-v2-download.spec.mjs`, `studio_history_v2_download_unit.mjs`.
- **F6 lane reconciliation:** Single Resume / Retry-naming landed alongside (see `PHASE_F6_HISTORY_FRONTEND_ACTIONS_DOWNLOAD_2026-08-23.md`); this lane reconciled the download UI's collisions with landed specs (note-selector scoping, preview=WebP MIME expectations, `gen_failed` production-shaped failed Attempt) and confirmed zero export-state coupling (`saveRequests` stays empty; `export_state` untouched).
- Still open (unchanged): configured-folder Export service/route, per-variant export-state projection, duplicate/missing-export detection — backend lanes, not addressed by any frontend batch.

---

## F7 Implementation Follow-Up — History V2 Export CORE Service (2026-08-23)

Closes §14 gap **1** (V2 export service core) and the service-side substrate for gaps **2–4** (per-variant projection, duplicate gate, missing detection), without touching route/frontend owner files:

- New `history_v2_export.py`: `HistoryV2ExportService.export_asset(asset_id, ExportOptions, ExportNamingContext)` + `get_export_state(asset_id)` — managed bytes (local or `modal://` via injected async/sync byte resolver) → sha256 verify against `assets.sha256` → canonical `output_converter` conversion (byte-preserving fast path for `original`) → atomic write into `output_saver._resolve_save_folder`-resolved `<folder>/images` → durable `upsert_export_record(exported, destination_path)` LAST.
- Settings authority unchanged: options are passed in pre-resolved from the canonical Output settings (`save_folder/output_format/quality/webp_lossless_compression/save_metadata_sidecar`); no new settings domain.
- Duplicate gate returns `already_exported` when record=exported + file exists + same resolved folder/format semantics; missing destination classifies/persists `missing` then allows re-export; folder/format changes are explicit exports; real `output_index` is encoded in filenames (fixes the legacy index-0 fidelity weakness at the V2 layer).
- Per-asset records give independent Preview/Original export state and rerender successors start `not_exported`; failure ordering never persists `exported` before the file exists; record-persist failure after write reports partial truthfully and cleans up written copies.
- No legacy run-history dependency (AST import allowlist test enforces it).
- Tests: `tests/test_history_v2_export.py` 33/33 OK; regression green (`test_run_history_save`, `test_output_saver_paths`, `test_output_contract`, `test_history_v2_repository`, `test_history_v2_api` 76/76; converter lanes 24/24). Full report: `PHASE_F7_HISTORY_V2_EXPORT_CORE_2026-08-23.md`. Remaining integration (route/frontend/projection) tracked there.

Deploy / live / GPU / commit / push: NONE.


## F3 Implementation Follow-Up A � Modern History Browser Download

**Lane:** Batch F3 Follow-Up A (Modern History V2 Browser Download). **Verdict: IMPLEMENTED � mounted History V2 now has first-class, per-output Browser Download actions for Single Generations AND Experiment cells, with zero export-state coupling.** Configured-folder Export remains NOT implemented in this lane (see the F7 service-core section above for that substrate).

### Semantics implemented

- **Browser Download ? Export.** Every control performs an explicit browser-side blob save of an EXISTING managed asset. Zero `export_records` writes, zero `upsert_export_record` calls, no legacy `/run-history/{id}/save`, no export route of any kind is touched; the detail's read-only "Export ? State" row is untouched and stays "none" across downloads (asserted in tests).
- **Single Generation (detail overlay):** featured Preview slot gains `Download Preview` (or truthfully-labeled `Download Thumbnail` when only a thumbnail is projected); Original slot gains `Download Original` alongside � never replacing � View Original, gated to usable projections (`originalUrl && !originalFailed`), so a failed Original without a retained winner renders NO dead download while Retry Original stays available. Each non-featured output's ? menu gains its own per-output download items (`history-v2-output-download-{variant}-{index}`) addressed by projected output index � featured selection never redirects another output's identity or bytes.
- **Experiment cells:** cell detail pane gains the same variant pair (`history-v2-cell-download-{variant}-{key}`) driven by the CELL'S OWN projected Generation/logical-output URLs. No Experiment-specific backend, no Playground legacy Save path, no browser fanout.
- **Preview/Original separation:** distinct buttons, distinct URLs, distinct bytes. Downloading Preview never fetches Original; downloading Original never enters View Original display state. Generate Original remains a separate action (proven: a Preview download fires zero `/original` POSTs).
- **No-eager-fetch:** rendering feed/detail/cells/menus/badges performs ZERO asset GETs beyond the already-displayed preview/thumbnail images; Original assets register zero server-side GETs until the explicit click (per-session asset counter asserted).
- **Filenames/MIME:** deterministic base `workflow_seed<seed>_out<index>_<variant>_<generationId>` (producer filename preferred when filename-shaped, extension stripped; sanitized; =100 chars; never timestamp-derived); the response Blob MIME is the sole extension authority (`image/webp?.webp`, `image/png?.png`, `image/jpeg?.jpg`; unknown image subtypes pass through sanitized; malformed MIME falls back to `.png`). Original extensions are never derived from Preview names.
- **Failure/recovery:** HTTP 404/502, network failure, and empty blobs surface as bounded truthful notes ("Download failed: HTTP 502"), the button re-enables with focus restored, retry succeeds, and the managed record + export state remain unchanged. Asset-fetch failures are never converted into Original-generation failures.
- **In-flight guard:** per-button guard collapses rapid double-clicks into exactly one asset request without blocking other outputs/variants.

### Files modified by THIS lane

- `web/history-v2-browser-download.js` (NEW � reusable helper: MIME?extension, sanitization, deterministic filename base, `buildManagedAssetDownloadButton`). Named distinctly from the concurrently-authored `web/history-v2-download.js` (F6 lane) to end a same-path write race observed mid-batch; both modules coexist, this lane's UI consumes only its own file.
- `web/studio-history-v2-detail.js` (download actions in featured slots + per-output menus + shared status line)
- `web/studio-history-v2-experiment.js` (per-cell download actions + shared status line)
- `tests/browser/fake/fake-backend.mjs` (per-session asset GET counters, one-shot asset-failure arming, suffix-aware asset MIME: `_preview`?`image/webp`)
- `tests/browser/fake/fake-server.mjs` (asset-route status passthrough incl. 502; `/__comfymodal_test/asset-fail` control endpoint)
- `tests/studio_history_v2_download_unit.mjs` (NEW Node unit) + registered in `tests/run_studio_tests.py`
- `tests/browser/fake/studio-fake-history-v2-download.spec.mjs` (NEW focused browser spec)

### Verification

- **Focused F3 browser spec:** 11/11 passed � single matrix (preview-only; preview+original separation; original-only explicit fetch; failed-Original hiding + Retry retention via `gen_orig_failed_original`; retained-winner targeting after failed rerender; two-output byte identity under featured changes; 502 failure?truthful note?recovery?retry; rapid double-click single request) + experiment matrix (cell parity/no-eager/per-cell addressing; Generate-Original separation + F2A durable cell favorite + independent experiment favorite; Cancel eligibility + menu open/close regression). Fanout authority is the page's own network requests (one explicit click ? exactly one managed-asset request); server counters back the no-eager-Original zeros.
- **Export-state non-mutation:** asserted after successful downloads � `saveRequests == []`, generation `export_state == "none"`, zero requests matching save/export routes.
- **Full Studio gate (`python tests/run_studio_tests.py --fake`): ALL STUDIO LANES GREEN** � Python run=1682 fail=0 error=0 skip=0; Node unit files=21/21 PASS (incl. new `studio_history_v2_download_unit.mjs`); fake Playwright wrapper PASS exit 0 (155 tests / 19 spec files, includes this lane's 11). Counts reflect the shared tree after concurrent F1A/F6/F7/F8 lanes landed their own additions.
- Deploy / Modal / GPU / live generation / commit / push / branch / reset: NONE.

### Remaining configured-folder Export work (beyond this lane)

Route/frontend integration of the F7 export service (per-variant projection surfacing, duplicate-gate UI suppression, missing-export re-export flow), multi-output `output_index` fidelity end-to-end, rerender/export interaction policy in the UI, deletion design guards, and the §13 test-debt items not closed above.

---

## F10 Implementation Closure — Configured-Folder Export UI + Fake Parity (2026-08-23)

Closes this audit's §14 gaps **2, 3, 4, 7 (frontend/fake halves)** and the UI side of gap **1**, without touching any production Python file (route/projection remain F9-owned):

- **Configured-folder Export is first-class in mounted History V2** (`web/history-v2-export.js` + detail/experiment wiring): featured Preview/Original slots, per-output ⋮ menu items addressed by each output's OWN projected Asset IDs, and Experiment cell-pane parity — all over exactly ONE bodyless POST `/history-v2/assets/{asset_id}/export` per explicit click (frozen F9 contract; no legacy Save route; no client-provided output index/variant/Settings/filename).
- **Per-variant export-state projection consumed truthfully** (`previewAssetId/originalAssetId` + states threaded through `normalizeHistoryOutput`; null when absent — never inferred from URL text): not_exported→`Export X`; exported→disabled `X exported` (duplicate suppressed); missing→`Export X again`; failed→`Retry export X`; absent variant renders nothing. Preview/Original fully independent; rerender successors start not_exported while old records stay historical.
- **Missing/re-export, failure/retry, partial, already_exported**: durable refetch after every response is the sole authority; backend message preferred and bounded; partial:true gets distinct truthful wording and never shows Exported; already_exported is an idempotent success (stale-tab/race safe); per-Asset in-flight guard collapses rapid duplicate clicks into one POST.
- **Download-vs-Export distinction pinned both directions** (browser + Node structural): Download fires zero export POSTs and leaves state untouched; Export causes zero browser blob downloads. Zero eager export POSTs on render/menus/View Original; auto-save never marks exported.
- **Fake parity**: fake backend/server implement the F9 contract (per-session per-Asset records, simulated destination files with lazy persisted `missing`, one-shot armed failures incl. partial, captured POST log) — coverage: NEW `studio-fake-history-v2-export.spec.mjs` 21/21 plus F10 sections in registered Node units.
- Full evidence/counts: `PHASE_F10_HISTORY_EXPORT_UI_FAKE_PARITY_2026-08-23.md`. Still open (backend-owned): production route wiring + per-output projection landing (F9), deletion design guards (§11).

Deploy / live / GPU / commit / push: NONE.

---

## F9 Implementation Follow-Up — Production Export Route Integration (2026-08-23)

Closes the remaining backend gaps from this audit (§14 items 1–4 substrate: route, per-variant projection, duplicate gate, missing detection) on top of the F7 core:

- **Route:** bodyless `POST /comfymodal/history-v2/assets/{asset_id}/export` in `history_v2_routes.py`. The selected `asset_id` is the only client input; generation association (via the asset's own durable `generation_id`), real logical-output index, naming context, and live Output settings are derived server-side. Client-supplied generation/output/naming identity is neither read nor honored (proven by test).
- **Settings authority:** new `settings_provider` injection seam on `register_history_v2_routes`; composition root (`__init__.py`) wires `_load_modal_settings` — no circular import, no settings parsing copied into routes. Exactly one F7 `ExportOptions` is built per POST from the acknowledged live settings; a folder/format change between exports is an explicit new export (proven live-read test).
- **Server-derived index:** `_derive_output_index` reuses the canonical `_logical_output_groups` ordering that detail projection publishes as each output's `index`; Preview+Original sharing a logical key resolve to the SAME index, multi-output generations get distinct real indices, unresolvable assets fail closed with `output_index_unresolved` (never silent 0).
- **Remote resolver:** the managed-asset GET's `modal://` semantics were factored into one shared helper (`_read_remote_managed_bytes` + typed `_ManagedAssetError` + structural pre-flight) used by BOTH asset GET and the Export byte resolver — identical URI parsing, workspace resolution, 3-attempt retry ladder, sha verification. Remote-missing classifies 404, retrieval failure 502, without diverging from serving truth.
- **Response/error contract:** 200 `{status, asset_id, export_state, saved, already_exported, destination_path, metadata_path, byte_count, file_ext, mime_type, exported_at}` with `saved=false` + `already_exported=true` on exact reuse; stable error payloads `{status, asset_id, reason, message(<=200 chars), export_state, partial}` mapped 404 unknown/missing-source, 502 remote retrieval/hash mismatch/resolver-unavailable, 500 conversion/write/record-persist/settings/crash, preserving F7 `partial:true`.
- **Per-variant projection:** generation detail and every embedded Experiment cell Generation now project `preview_asset_id/preview_export_state` and `original_asset_id/original_export_state` (None when the variant is absent — never `not_exported` for a nonexistent Original), computed through the F7 lazy checker so exported-with-file-gone becomes (and persists as) `missing`. Projected ids are the same winner objects the URLs point at (retained-winner-after-failed-retry and new-rerender-winner-starts-not_exported both tested). Feed pages are unchanged (no per-asset lookups). The old collapsed generation-level `export_state` is retained as a DEPRECATED aggregate derived from the per-variant truth (never contradicting it); frontends must move to the per-variant fields.
- **Duplicate/missing/rerender:** first export saved=true; exact repeat already_exported=true with zero new files; externally deleted destination projects missing then re-exports; folder/format changes are explicit exports; rerender successors start not_exported with no state transfer.
- **Concurrency:** narrowest per-Asset `asyncio.Lock` registry added at the route layer (no global serialization): two concurrent POSTs for the same asset produce exactly one file, one record, and one `already_exported` response (regression-tested).
- **Separation held:** Browser Download (asset GET) writes zero export state (tested); auto-save materialization untouched; no legacy run-history dependency.
- **Tests:** new `tests/test_history_v2_export_integration.py` (26 HTTP tests covering the full F9 matrix: local/modal x Preview/Original exports, unknown-404, remote-failure-502/404, workspace-unavailable, local-missing, SHA-mismatch, conversion/write failures, response contract, already-exported, missing->re-export, variant independence, distinct real indices, retained/rerender winners, Experiment parity, zero eager remote fetches during projection, Download-separation, concurrent-duplicate safety, live-settings timing, snapshot-only naming, bodylessness). `tests.test_history_v2_export` (F7, 33) + the new module are registered in `STUDIO_PY_MODULES`.
- **Gate:** focused regression all green (F7+F9 59/59; repository/api/logical-output/projection/F5/F1A/generate-original/output_saver/output_contract 226/226; converter+migration/pagination/writer/modern-experiment/replay-core 144/144); full wrapper `python tests/run_studio_tests.py --fake`: **python 1741/0/0/0, node-unit 21/21, fake Playwright 176 passed — ALL STUDIO LANES GREEN** (one earlier run showed 5 transient fake-lane failures while the parallel F10 frontend/fake lane was mid-edit; all green on rerun with zero F10 files touched).
- Remaining: F10 frontend consumption of the per-variant fields + Export actions against this frozen route contract.

Deploy / live / GPU / commit / push: NONE.

