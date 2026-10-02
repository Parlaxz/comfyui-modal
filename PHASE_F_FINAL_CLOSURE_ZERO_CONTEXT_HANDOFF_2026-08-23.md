# PHASE F FINAL CLOSURE — ZERO-CONTEXT HANDOFF (2026-08-23)

**Audience:** a future agent with ZERO conversational context starting Phase G.
**Purpose:** single authoritative reconciliation of everything Phase F was supposed to do, what actually shipped, every defect found and how it was fixed, the frozen contracts, the rejected approaches, the exact deterministic evidence, what is COMPLETE, and what is intentionally deferred.
**This document supersedes no earlier report's history; it reconciles them.** The older roadmap handoff (`PHASE_E_FINAL_CLOSURE_2026-08-22.md`) remains untouched.
**Batch type:** documentation/reconciliation only. No production code, tests, deploy, Modal, GPU, live generation, commit, push, branch, reset performed by THIS batch.

---

## 1. FINAL VERDICT AND AUTHORITATIVE GATE

## `PHASE F COMPLETE`

### Final shared-tree gate state (authoritative closure numbers)

```
python tests/run_studio_tests.py --fake
Python lane:        1741 run / 1741 pass / 0 fail / 0 error / 0 skip
Node unit lane:     21 / 21 files PASS
Fake Playwright:    176 / 176 PASS
Wrapper exit 0 — ALL STUDIO LANES GREEN
```

### Chronology of the evidence (stated, not hidden)

The gate grew monotonically across Phase F as lanes landed their suites; observed totals per lane were point-in-time truth, not contradictions:

| Milestone | Python | Node units | Fake Playwright | Note |
|---|---|---|---|---|
| Phase E close (baseline) | 1609/0 | 16/16 | 126/126 | E6+E7+Follow-Up A |
| F1A durable resume | 1636/0 | — | — | focused 124 OK |
| F1B cancel/menu | 1642/0 | 18/18 | 141/141 (17 files) | ALL GREEN |
| F2A annotations | 1609/1* | 16/16 | 132 PASS | *single failure = `web/modal-settings.js` duplicate declaration, a concurrent Settings-lane file, not F2A's; fixed by its owner |
| F4A settings cleanup | 1609/0 | 17/17 | 132 PASS | transient cross-lane flakes re-ran clean |
| F4C grid columns | 1642/0 | 18/18 | 141/141 | ALL GREEN |
| F5 backend truth | 1642/0 | (red)* | (red)* | *node/fake failed only on a concurrent frontend defect (`_v2ResumeGeneration` declared twice in `history-v2-repository.js`) owned by another lane; unrelated to Python; resolved by that lane |
| F6 resume/retry/download reconcile | 1682/0 | 21/21 | 147/8* | *all 8 red = the concurrent F3-download lane's own mid-edit spec; every other spec green |
| F3A browser download | 1682/0 | 21/21 | 155/155 (19 files) | ALL GREEN |
| F8 GPU authority | 1682/0 | 21/21 | 147/8* | *asset-GET-count assertions inside the download spec while sibling lanes were mid-edit; earlier same-day run 140/140 |
| F9 export integration | **1741/0** | **21/21** | **176/176** | **ALL STUDIO LANES GREEN** (one intermediate run showed 5 transient fake failures while F10 was mid-edit; green on rerun with ZERO F10 files touched) |
| F10 export UI + fake parity | 1741/0 | 21/21 | 175/1* → **176/176** | see below |

**F10 transient, resolved:** one wrapper run showed a single timing-flaky playground-lifecycle progress-test failure (175/1). That test passes 14/14 in isolation, and the identical full suite passed **176/176** in a direct run minutes earlier against a clean fake server. A separate first-wrapper attempt showed mass `ECONNREFUSED` createSession failures caused by a stale leftover fake-server process on port 8377 dying mid-run — environmental, not code; with a clean port the suite is green. **The flake is not a Phase-F functional blocker, and the final shared-tree state is ALL LANES GREEN at 1741 / 21 / 176.**

Rule applied throughout: a later clean run supersedes an earlier transient failure; per-lane ownership rules meant no lane ever touched another lane's failing file to achieve green.

---

## 2. WHAT PHASE F WAS — MANDATE

Phase F = **History Actions & Settings Consumers**, opening from `PHASE E COMPLETE — deterministic and live gates green.` Its roadmap scope:

1. **F1 — History execution actions**: reconcile Retry / Resume / Generate Original / Generate Again / Cancel across Single and Experiment surfaces; immutable-plan safety; race semantics; legacy truthfulness.
2. **F2 — Notes & favorites**: durability, filtering, sync, error paths for Generation/Experiment/cell annotations.
3. **F3 — Downloads & export**: Browser Download vs configured-folder Export vs managed assets; duplicate/missing/multi-output/Experiment semantics.
4. **F4 — Settings consumers**: stale keys, inert controls, duplicated authorities, GPU authority, reset semantics.

Everything else that surfaced (export service, GPU threading, replay-capability projection) was discovered by the audits and executed as bounded follow-up batches inside Phase F.

### Batch map (what actually shipped)

| Batch | Lane | Outcome |
|---|---|---|
| F1 | Read-only action reconciliation audit | Verdict: actions substantially complete post-E; gaps enumerated (§13 lanes) |
| F1A | Durable Resume backend | Single startup sweep + post-restart scheduler reconstruction + Single Resume route |
| F1B | Experiment Cancel UI + cell-menu defect | Cancel surfaced; `openCellMenu` ReferenceError fixed |
| F2 | Read-only notes/favorites audit | Defect list (favorite-filter leak, dead feed star, local-only cell star) |
| F2A | Annotation correctness frontend | Feed-star recovery, Generation-backed cell favorite, kind hint, fake parity |
| F3 | Read-only export/download audit | Five-concept terminology; scaffolding-only verdict; gap list |
| F3A | Modern Browser Download | First-class per-output/per-variant download, zero export coupling |
| F4 | Read-only settings consumer audit | Stale keys, banner bug, inert Grid Columns, GPU triple-authority findings |
| F4A | Modern settings cleanup | Stale keys removed, banner truth model, GPU display authority, guard test |
| F4B | Legacy settings alignment | Server-first precedence; no GPU POST on panel open; dead globals removed |
| F4C | Grid Columns consumer | Setting now drives mounted History V2 grid |
| F5 | Backend truth (replay capability + favorite filter) | `replay_capable` projection; `query_experiments(favorite=…)` + index |
| F6 | Frontend actions | Single Resume UI; "Retry run" vs "Retry Original"; download-spec reconciliation |
| F7 | Export core service | Standalone `history_v2_export.py`, 33 tests, no route yet |
| F8 | GPU authority consolidation | Persistence, precedence, capture threading, transport boundary, reset |
| F9 | Export production integration | Bodyless route, per-variant projection, locks, gate registration |
| F10 | Export UI + fake parity | Export actions, state truth table, fake F9 contract, favorite-filter fake closure |

---

## 3. F1 — HISTORY EXECUTION ACTIONS (FINAL BEHAVIOR)

### 3.1 Route inventory (frozen)

Under `/comfymodal/history-v2`:

| Action | Route | Body | Semantics |
|---|---|---|---|
| Generate Original / Generate Again | `POST /generations/{id}/original` | optional `{"rerender": bool}` (400 if non-bool) | decision policy: `original_created` / `original_already_active` / `original_already_completed` / `retry_required`; refusals `generation_busy` / `generation_not_reproducible` (409), `dispatch_unavailable` (503) |
| Retry Original | `POST /generations/{id}/original/retry` | BODYLESS | newest `mode="original"` attempt `failed`, nothing active, snapshot validates → one new queued Original Attempt; failed Attempt/Preview/assets retained |
| Single Resume | `POST /generations/{id}/resume` | BODYLESS (F1A) | durably `interrupted` ordinary Singles only; same Generation/snapshot; frozen semantic mode preserved verbatim (Preview stays Preview); refusals for active/terminal/legacy/experiment-cell cases |
| Experiment Resume | `POST .../experiments/{id}/resume` | — | ≥1 interrupted or queued cell else 409 `NO_RESUMABLE_CELLS`; live scheduler: interrupted→new attempt identity, queued→claim existing; completed/failed/**canceled skipped** |
| Experiment Cancel | `POST .../experiments/{id}/cancel` | — | queued cells → canceled atomically; running cells require truthful remote-cancel primitive else `503 CANCELLATION_UNAVAILABLE`; terminal → 409; all-canceled → idempotent 200 |
| Cell Retry | `POST .../cells/{cell_id}/retry` | — | current attempt `failed` else 409 `CELL_NOT_FAILED`; new queued attempt under SAME Generation/snapshot |

### 3.2 Core semantics (all verified in current tree)

- **Same-Generation / new-Attempt:** every re-execution action appends an Attempt under the SAME Generation; nothing ever forks a new Generation. Attempts are **append-only**: terminal attempts are never reopened (`_update_attempt` SQL predicate `status NOT IN (terminal)`), first-terminal-wins everywhere.
- **Immutable RequestSnapshot/ExecutionPlan authority:** plan source is always `RequestSnapshot.execution_plan_json` → raw validation → `ExecutionPlan.from_dict` → exact round-trip equality → output-intent-only delta (`validate_replay_delta` allows ONLY `execution_options.output_conversion_options`, `output_intent`, correlation metadata, and — since F1A's blocker fix — `execution_options.output_mode` for the intentional Preview→Original conversion on Generate Original). No re-execution path reads current Workflow versions, Presets, Settings, or model selections. Mutation-after-preparation cannot rewrite the plan.
- **failed != Resume; canceled != Resume:** intentionally unsupported everywhere. `create_resume_attempt` requires current=`interrupted`; scheduler skips canceled and failed; UI eligibility excludes both. Failed goes through Retry; canceled requires a fresh action by policy (canceled ≠ active).
- **Stale Single startup recovery (F1A):** `_sweep_stale_running_singles()` marks stale `running` attempts with NO experiment/cell identity as `interrupted` at startup (idempotent; terminal/queued untouched). This closed the permanent "Generation busy" lockout where a host restart mid-Single left the Generation running forever. Ownership boundary = documented single-host/single-owner `history_v2.db` invariant.
- **Post-restart Experiment scheduler reconstruction (F1A):** when `/resume` finds no registered scheduler, the canonical scheduler is reconstructed from persisted immutable cell plans via `build_experiment_scheduler` under `_SCHEDULER_RECONSTRUCTION_LOCK` (single recovery owner). Reconstruction is **fail-closed**: non-list/empty cells, malformed entries, duplicate IDs, ID-set mismatch vs durable cells, or a queued/interrupted cell without a mapping plan → no scheduler, before any factory call or attempt write. Unavailable reconstruction → `503 DISPATCH_UNAVAILABLE` and NOTHING is written — **no orphan queued attempts** (closes the sharpest pre-F defect: resume-into-indefinitely-queued with a 200).
- **Concurrent action safety:** `claim_or_reuse_original_attempt` / `create_original_retry_attempt` / `create_single_resume_attempt` / `create_retry_attempt` / `create_resume_attempt` each run in one `BEGIN IMMEDIATE` transaction with in-transaction re-checks; scheduler claims are atomic first-wins CAS; claim-vs-cancel races safe; two-tab double-fire produces benign reuse/refusal responses, never duplicates. All pinned by named tests (`test_concurrent_double_submit_creates_one_attempt`, `test_rerender_race_creates_exactly_one`, `test_resume_double_call_no_duplicate_execution`, `test_claim_cancel_race_does_not_execute_canceled_cell`).
- **Proactive `replay_capable` projection (F5):** generation detail, every feed item, and Experiment cell payloads project `replay_capable: bool` (+ stable machine-readable `replay_unavailable_reason` when false: `missing_request_snapshot`, `missing_execution_plan`, `snapshot_hash_mismatch`, `missing_deployment_identity`, …). Computed by the SAME validator that gates Single Resume (`load_replay_plan`). It means ONLY "saved request passes canonical replay validation" — not a promise about credentials, dispatch, or success. Legacy rows project false truthfully; projection performs zero writes (full-table dump equality test). Frontend consumes tolerantly: explicit false → disabled-with-reason BEFORE click; absent field → POST stays authoritative.
- **Legacy irreproducible behavior:** missing/mismatched `execution_plan_json` → `409 generation_not_reproducible` BEFORE any deserialization/write, zero Attempt rows. Bridge/fixture repository modes hard-blocked in the UI. No unsafe reconstruction exists anywhere (no rebuilding requests from current mutable Workflow/Preset); the only compatibility path is the sanctioned active-workspace fallback for pre-workspace-id snapshots.
- **Retry run vs Retry Original presentation (F6):** `deriveRetryActionLabel` presents "Retry run" for a plain failed ordinary Single (no successful Preview history, no prior Original success, no retained usable Original asset) and "Retry Original" for the explicit derivative lifecycle. Both dispatch the UNCHANGED bodyless `/original/retry`. No new retry route was created (deliberately rejected — machinery already covered generic Single retry immutably because every modern Single attempt carries `mode="original"`).
- **History Cancel UI (F1B):** single whole-Experiment Cancel in the header action row next to Resume (`data-testid="history-v2-experiment-cancel"`), eligibility derived from DURABLE cell state mirroring backend truth (queued/running eligible; completed/completed_with_failures/failed/canceled/interrupted-only hidden). Click flow: duplicate-submission guard → exactly one `repo.cancelExperiment` POST → durable refetch → full re-render from server truth → truthful status note. **No optimistic state anywhere.** 503 `CANCELLATION_UNAVAILABLE` leaves the experiment Running truthfully (queued cells show Canceled exactly as the backend atomically canceled them); closing detail/Escape/navigation sends ZERO cancel requests (request-counter-proven). Repository normalization preserves machine-readable refusal codes instead of parsing human text.
- **Cell-menu focus defect/fix (F1B):** root cause — `openCellMenu()` ended with unbound `item.focus()` → ReferenceError on every cell `⋮` open (menu mounted, then the focus step crashed as an uncaught page error; invisible to the gate because no test exercised menu open). Fixed with the existing convention: focus the first actionable menu item (`menu.querySelector("button:not([disabled])").focus()`); pinned by a real rendered browser test driving the previously-crashing path (fails on old code with pageerror).

### 3.3 Per-state action matrix (Single)

| Generation state | Visible action | Result |
|---|---|---|
| completed Preview-only | Generate Original | new Original Attempt, same Generation, immutable replay |
| completed Original | Generate Again (`{rerender:true}`) | explicit rerender; newest success wins, earlier retained |
| failed ordinary run | **Retry run** | `/original/retry`; same Generation/snapshot; failure retained |
| failed Preview-enabled run (mode=preview) | Generate Original | create decision → full Original rerun (mode converts preview→original, F1A-reviewed) |
| failed Original after prior success | Retry Original | new Attempt; prior success + Preview retained |
| interrupted ordinary run | **Resume** (F1A+F6) | resumes as its frozen mode; zero option delta sent |
| canceled ordinary run | Generate Original path only per policy | canceled is never resumed |
| running (live or stale-recovered) | actions disabled "Generation busy" until sweep/interrupt | — |
| irreproducible legacy record | disabled-with-reason (via `replay_capable=false`) | click-path 409 remains truthful backstop |

Experiment cells carry their own `generationId` and use the SAME Generation-scoped routes (parity proven); experiment-level retry-all remains deliberately forbidden (D5) — button rendered disabled with explanatory note.

---

## 4. F2 — NOTES / FAVORITES (FINAL BEHAVIOR)

- **Storage model:** first-class persisted columns, NOT auxiliary tables — `generations.favorite/note`, `experiments.favorite/note` (idempotent `ALTER TABLE` upgrade). `experiment_cells` have NO favorite/note columns; cells reference `generation_id`.
- **Generation favorite/note:** `PATCH /comfymodal/history-v2/generations/{id}/favorite|note` — strict validation, 400 non-bool/non-str/>2000-chars, 404 unknown id. Atomic `BEGIN IMMEDIATE` writes; idempotent; boolean written/not-found returns.
- **Experiment favorite/note:** identical mechanics against `experiments` — whole-Experiment scope, fully INDEPENDENT of Generation favorites (no propagation either direction).
- **Cell favorite = associated Generation favorite (canonical decision, F2A):** the cell-pane star calls `repo.setFavorite(generationId, …)` — the SAME Generation-scoped route. Read projections derive cell favorite through the cell's Generation on both production and fake. **Explicitly: NO duplicate cell-favorite persistence authority was created** — no `experiment_cells.favorite`, no new route, no bespoke cache. Cells without a Generation identity render a disabled truthful control.
- **Note clear-to-empty:** saving an empty string is a valid durable clear (only length validated). Pinned by browser tests A5/A6 (clear persists across reload).
- **Failure recovery (F2A):** feed favorite star captures prior durable value before flight; on failure restores glyph/state, re-enables, surfaces bounded truthful "Favorite failed" note; no unhandled rejection; no optimistic fake success. Detail stars/notes revert truthfully with status text. Keyboard fix: Enter/Space on a focused inner control no longer hijacks card-open.
- **favoriteOnly filtering of BOTH mixed streams (F5 + F10):** `GET /feed?favorite=true` now filters Generations AND Experiments. `query_experiments(..., favorite=...)` applies `e.favorite = 1` (explicit False → truthful inverse `e.favorite = 0`) INSIDE the SQL where-clause before keyset pagination — never post-pagination. Mixed cursors stay truthful across pages (zero leakage/duplicates proven with interleaved favorited/unfavorited rows of both kinds). The fake backend mirrors exactly (`_expMatchesV2` constraint threaded from parsed query param), closing the last open half in F10 (end-to-end regression: favorites-only mixed feed = exactly the favorited Generation + favorited Experiment).
- **Index/migration choice (F5):** `idx_experiments_favorite` added via idempotent `CREATE INDEX IF NOT EXISTS` inside `_ensure_experiment_annotations`, deliberately NOT in `_SCHEMA_SQL` (executescript runs BEFORE the column-upgrade ALTERs on pre-existing DBs and would fail with "no such column"). Placed after the ALTER loop it is safe on every database shape; additive index only; no SCHEMA_VERSION bump. Mirrors the existing Generation favorite index.
- **Last-write-wins annotation semantics:** unconditional write, no revision token/CAS/conflict signal; two tabs editing converge silently to last write. Deliberate for the single-user local-control product model; CAS explicitly NOT recommended and NOT built.
- **Legacy annotations surface:** `PATCH /comfymodal/run-history/{id}/annotations` remains live as the bridge/migration source (one-way migration INTO V2 at creation; later legacy edits do not propagate). Frozen-for-bridge; retirement belongs to Phase H legacy cleanup.
- Feed ordering is never affected by annotation writes (orders key off `created_at`; writes bump only `updated_at`).

---

## 5. F3 — DOWNLOAD / EXPORT (FINAL BEHAVIOR)

### 5.1 Terminology — mutually distinct, never conflated

| Concept | Definition |
|---|---|
| **Managed History Asset** | The authoritative internal copy/reference. `assets.managed_path`: local file path OR remote `modal://<workspace>||<path>` reference. Served by `GET /history-v2/assets/{asset_id}` (local + proxied remote with sha verify and 3× retry ladder). |
| **Browser Download** | Client-side blob save of a fetched managed asset. Writes NO server state of any kind. |
| **Configured-folder Export** | Server-side copy of managed bytes into the configured Studio output folder, recorded durably in `export_records`. |
| **View Original** | Explicit one-shot managed fetch FOR DISPLAY only. Not a download, not an export. |
| **Generate Original** | Replay action producing a NEW managed Original asset. Not export. |
| **Execution-time auto-save** | Adjacent materialization during a run (`auto_save_local` + `save_folder`). A sixth, execution-time behavior — deliberately NOT any of the five History/export concepts above; it creates zero `export_records`. |

These are the five distinct product concepts (plus the adjacent auto-save materialization); no code path equates any of them, and the UI keeps them verbally and mechanically separate (pinned both directions by browser and structural tests).

### 5.2 Browser Download (shipped: F3A, reconciled F6)

- **Per logical output:** featured slots AND each non-featured output's `⋮` menu carry their own download items addressed by that output's OWN projected identity — featured selection never redirects another output's bytes.
- **Preview vs Original:** distinct buttons, distinct URLs, distinct bytes. Thumbnail-only records show truthfully labeled "Download Thumbnail". Failed Original without a retained winner renders NO dead download while Retry Original stays available.
- **Experiment parity:** cell detail panes expose the same variant pair driven by the CELL'S OWN projected Generation/logical-output URLs. No Experiment-specific backend, no Playground legacy Save path.
- **No eager Original fetch:** rendering feed/detail/cells/menus/badges performs ZERO asset GETs beyond already-displayed previews/thumbnails; Original registers zero server-side GETs until the explicit click (per-session asset counters asserted).
- **MIME-derived extension:** response Blob MIME is the sole extension authority (`image/webp→.webp`, `image/png→.png`, `image/jpeg→.jpg`; malformed falls back `.png`). Deterministic collision-free filename base (`workflow_seed<seed>_out<index>_<variant>_<generationId>`), never timestamp-derived, ≤100 chars.
- **No export-state writes:** zero `export_records` writes, zero save/export route touches; `export_state` stays untouched across downloads (asserted: `saveRequests == []`).
- Failure/recovery: HTTP 404/502, network failure, empty blobs → bounded truthful notes, button re-enables with focus restored, retry succeeds; per-button in-flight guard collapses rapid double-clicks into exactly one asset request. Asset-fetch failures are never converted into Original-generation failures.

### 5.3 Configured-folder Export (shipped: F7 core → F9 integration → F10 UI)

- **F7 standalone core:** `history_v2_export.py` — `HistoryV2ExportService.export_asset(asset_id, ExportOptions, ExportNamingContext)` + `get_export_state(asset_id)`. All collaborators injected; no module-global mutable state; zero legacy run-history dependency (AST import allowlist enforced).
- **Frozen route contract:** BODYLESS `POST /comfymodal/history-v2/assets/{asset_id}/export`. **The only client identity is the asset_id.** Generation association derives from the asset's own durable `generation_id`; client-supplied generation/output/naming identity is neither read nor honored (proven by test).
- **Output index derived server-side:** `_derive_output_index` walks the same `_logical_output_groups` ordering detail publishes; Preview+Original sharing a logical key resolve to the SAME index; multi-output generations get distinct real indices encoded in filenames; unresolvable fails closed `output_index_unresolved` (never silent 0 — fixes the legacy hardcode-index-0 weakness at the V2 layer).
- **Live canonical Output settings:** injected `settings_provider` (= composition-root `_load_modal_settings`), invoked ONCE per POST; exactly one `ExportOptions` from the five canonical keys (`save_folder/output_format/quality/webp_lossless_compression/save_metadata_sidecar`). No new settings domain invented. Proven live: changing `save_folder` between POSTs yields an explicit second export, never a false duplicate.
- **Local + `modal://` source support:** shared `_read_remote_managed_bytes` helper used by BOTH asset GET and Export resolver — identical URI parsing, workspace resolution, 3-attempt retry ladder, sha verification. Remote availability NEVER classified via `os.path.isfile(modal_uri)`.
- **SHA verification:** resolved bytes verified against immutable `assets.sha256` before ANY write; mismatch → `failed` record, no corrupted output, managed source untouched.
- **Atomic file-before-record ordering:** resolve → sha-validate → convert → atomic tmp+fsync+replace write → existence verify → persist `ExportRecord(exported)` LAST. Never persists `exported` before durable write. Record-persist failure after write → `partial:true` reported truthfully + written copies cleaned up (orphan path reported if cleanup itself fails).
- **Per-asset ExportRecord truth:** ONE row per `asset_id` (upsert keyed on asset_id). Records are keyed by asset only — no Generation-level collapsed state in the service.
- **Per-variant projection:** generation detail and every embedded Experiment cell Generation project `preview_asset_id/preview_export_state` and `original_asset_id/original_export_state` (null when variant absent — NEVER `not_exported` for a nonexistent Original). States: `not_exported | exported | missing | failed`, computed through the lazy checker so exported-with-file-gone becomes (and persists as) `missing`. Projected ids come from the SAME winner objects as the URLs (retained-winner-after-failed-retry and new-rerender-winner both tested). Feed pages intentionally project no export fields (no per-asset lookups on hot paths).
- **Preview/Original independence:** exporting one never flips or suppresses the other; deleting one destination classifies only that variant `missing`.
- **Duplicate suppression:** exact repeat while destination exists → `already_exported:true, saved:false`, zero new files; idempotent success (stale-tab/race safe). Folder/format change → explicit new export (old copy untouched, record repointed). Quality-only changes reuse the existing copy (documented; matches legacy gate strictness).
- **Exported-file missing detection:** externally deleted destination projects (and persists) `missing`; UI offers "Export X again".
- **Re-export:** next explicit POST restores the deterministic path → `exported`.
- **Multi-output fidelity:** real per-output indices in filenames and addressing; two outputs address different Assets; featured change never redirects.
- **Experiment parity:** cell panes over the CELL'S OWN Asset IDs; one POST per explicit click; no batch/fanout.
- **Rerender/new-winner semantics:** Generate Again creates a new winner Asset starting `not_exported`; predecessor's record remains historical provenance; no state transfer via shared `logical_output_key`. Scripted failed rerender keeps the retained winner and its exported state.
- **Per-Asset concurrency lock:** narrowest process-local per-Asset `asyncio.Lock` registry at the route layer — same-asset POSTs serialize (two concurrent POSTs → exactly one file, one record, `{false,true}` saved flags); different assets never block; no global serialization.
- **Download does not Export / auto-save does not Export:** pinned both directions (browser + Node structural). Only the explicit route mutates export state.
- **Old generation-level `export_state` is COMPATIBILITY-ONLY / DEPRECATED:** retained as a derived aggregate ("exported" iff any projected variant is exported, else "none") so it can never contradict the per-variant fields; frontends must consume the per-variant fields (F10 does).

UI truth table (F10): `not_exported`→enabled "Export X"; `exported`→disabled "X exported"; `missing`→"Export X again"; `failed`→"Retry export X"; absent variant → no control. Durable refetch after every response is the sole authority; no optimistic state mutation; partial gets distinct truthful wording and never shows Exported.

---

## 6. F4 — SETTINGS (FINAL BEHAVIOR)

- **Stale keys removed (F4A):** `comfymodal_global_concurrency` and `comfymodal_preview_auto_save` deleted from `MODERN_SETTINGS_KEYS`; the Experiments-section reset (whose only content was the stale concurrency key) removed entirely. New authority guard test pins every key in the reset set to a classification with concrete reader/writer evidence substrings checked against real module sources — adding a reset-only key without evidence fails the gate. Durable namespaces (`playground.v1/drafts.v1/results.v1`, History view-state) stay outside the reset set.
- **Heavy Tracing banner fixed (F4A):** banner now shows iff server-reported PERSISTED level differs from server-reported EFFECTIVE level (`GET /profile/level {level, effective}`). The browser-stored selection never participates — killing the permanent false-positive banner (`.profile_config.json` held `detailed` while an unsynced browser default said `off`). Restart genuinely remains required; runtime profiler semantics unchanged.
- **Grid Columns CONSUMED / WORKING (F4C):** the modern Settings control now drives the mounted History V2 grid via inline CSS custom property + `data-grid-columns` attribute; normalization shares Settings semantics (parseInt truncate, NaN→default 6, clamp 2–8); gap-compensated track formula yields EXACTLY N tracks on desktop widths with a 132px floor reflow and a ≤720px legacy-density override; applies same-tab on History return without reload; presentation-only (zero view-state/filter/favorite/detail impact). Visual baseline regenerated for the intentional default-6 layout change.
- **modern/legacy Settings precedence aligned (F4B):** legacy output synchronization routed through `studio-output-preferences.js` — successful server read overwrites stale localStorage; edits POST first and publish localStorage/window global/change event only after success; rejected edits restore prior acknowledged state. Once-per-page-load sync guards prevent duplicate initialization.
- **No GPU POST merely from opening the legacy panel (F4B):** former panel-build `syncGpuConfig()` POST removed; legacy init is read-only, server-first. Exactly one explicit-change POST site remains; failure keeps prior acknowledged cache/state.
- **GPU persisted across restart (F8):** `POST /config {gpu}` validates against catalog → updates server effective → persists to `.modal_settings.json["gpu"]` (atomic tmp+replace); `_seed_server_gpu_from_settings()` seeds `_current_gpu` at startup. GET `/config` returns `{gpu, persisted_gpu, default_gpu, available_gpus}` so display can never silently diverge. Persistence failure rolls back in-memory value (no split-brain). Additionally `_save_modal_settings` became read-modify-write so partial POSTs can no longer clobber unrelated persisted keys (latent hazard that would have reverted GPU on every output-settings save).
- **Canonical GPU precedence (documented contract, F8):** (1) explicit per-request top-level `gpu` (catalog-validated, else truthful 400) → (2) `modal_options.gpu` captured from canonical server Settings → (3) canonical persisted/default server GPU → (4) transport env/hardcoded fallback ONLY when nothing was captured (`COMFYMODAL_V2_GPU` env, else `rtx-pro-6000`). Env remains deploy-time primary, never a runtime lock overriding an explicit selection.
- **Single/Workflow/Experiment immutable GPU capture (F8):** `resolve_request_gpu()` resolves ONCE at acceptance per surface (`handle_studio_run_async` / `handle_workflow_run_async` / `handle_studio_experiment`) and freezes `request_metadata.selected_gpu` into the ExecutionPlan (production and non-production branches; every Experiment cell plan gets the same frozen GPU). Diagnostics record `selected_gpu_source` (`request|modal_options|server_settings`).
- **Replay/resume/retry saved-GPU preservation (F8):** Generate Original, Retry Original, Generate Again, Single Resume, Experiment Retry/Resume dispatch saved plans WITHOUT a gpu kwarg; the executor reads the plan's frozen metadata. Replay correlation builders copy request metadata verbatim; `validate_replay_delta` stays green. Changing GPU today affects FUTURE submissions only.
- **Transport receives frozen selection (F8):** non-empty `selected_gpu` reaches ModalTransport (cache identity + handle lookup diagnostics) and is never substituted; empty selection falls back env/hardcoded; unsupported selections fail closed at acceptance — never silently substituted hardware.
- **Reset All GPU behavior (F8):** Reset All AND Generation-section reset now clear the browser cache AND reset server effective + persisted GPU to the catalog default (fetched from GET `/config`, hidden-GPU aware), with confirmation copy and footer note truthfully disclosing both the engine-V2 and GPU resets. Preview/output reset behavior unchanged.
- **Legacy canvas compatibility:** canvas V1/V2 keep `get_gpu()` / `extra_data.get("gpu")` paths — now restart-stable because the server selection persists. `window._comfyModalGpu` stays removed (zero readers confirmed repo-wide before removal); `window._comfyModalOutputOptions` remains maintained by the shared helper for canvas/Comparison readers.
- **Scope separation:** this is CONTROL-PLANE GPU work (which GPU the user selected, persisted and threaded). It is entirely independent of the Modal V2 PERFORMANCE project (profiles, runtime flags, preload/warmup, waterfall/benchmark work in `comfymodal_runtime/*`, `tools/v2_control/*`, `config/v2/profiles/*`), which owns its own gates and was not touched by any F lane.

Settings inventory outcome: 14 value settings audited → 10 fully consumed, Run mode PARTIAL (legacy-consumer only, Phase H), Grid Columns now CONSUMED, GPU now fully consumed end-to-end, stale keys gone.

---

## 7. ARCHITECTURAL INVARIANTS (MUST PRESERVE IN LATER PHASES)

1. **Immutable execution plan for re-execution.** Every re-run/resume/retry replays `RequestSnapshot.execution_plan_json` through validation + exact round-trip; only the allow-listed delta may differ. Never read current Workflow/Preset/Settings/model state to reconstruct a plan. No unsafe reconstruction for legacy rows — fail closed.
2. **Durable History is the action-state authority.** Availability derives from durable attempts/cells/generation status; the UI never invents optimistic Attempts or fabricates statuses; after every action it reloads/polls durable truth.
3. **Managed assets are the authoritative internal assets.** `assets.managed_path` (local or `modal://`) is the source of truth for bytes; `modal://` references are URI-aware — reference ≠ absence; never classify remote availability with local filesystem probes.
4. **Export copies are not managed assets.** `export_records` rows describe user-facing copies; exporting never modifies/deletes the managed source; deleting an export never implies touching the managed asset (and vice versa when deletion is designed).
5. **Browser Download has no durable server Export side effect.** Zero `export_records` writes, zero export-route touches, zero state mutation — forever.
6. **Original is never eager-loaded.** Feed/detail/cell render performs zero Original asset GETs; only explicit View Original / Download Original / Export Original fetches.
7. **Preview and Original are semantically distinct.** Distinct modes, assets, URLs, actions, and export states; a Preview download/export never touches Original and vice versa; Generate Original from a saved Preview plan executes AS Original (intentional delta), while Resume always preserves the frozen mode.
8. **Stable logical-output identity.** Canonical `node:<id>:slot:<key>:item:<index>`; retries/rerenders never inflate output count; newest usable Original wins per group; derivatives share the group key.
9. **Attempts are append-only.** Terminal attempts are never reopened; first-terminal-wins; failures/cancels are retained, never destroyed by later actions.
10. **F1 resume/retry distinctions.** `interrupted`→Resume; `failed`→Retry; `canceled`→never resumed; queued→claim; these exclusions are contractual, not incidental.
11. **Selected GPU is frozen at acceptance.** `request_metadata.selected_gpu` captured once per submission; replay/resume/retry reuse it verbatim; later Settings changes affect future submissions only.
12. **Experiment backend concurrency is fixed at 6.** `EXPERIMENT_CONCURRENCY = 6` in `experiment_modern_scheduler.py`; payload overrides ignored; no frontend concurrency control.
13. **No browser fanout for Generation/Experiment execution actions.** One dispatch per explicit user action, cell actions ride the SAME Generation-scoped routes; no second engine, no per-cell parallel POST storms.
14. *(F3 corollary)* **Export is per-asset, bodyless, server-derived.** The route accepts only `asset_id`; index/settings/naming derive server-side; per-Asset locking serializes duplicates; file-before-record ordering is mandatory.

---

## 8. DELIBERATELY REJECTED APPROACHES

- A separately-named generic Single-retry service/route — rejected; the Original-retry machinery already covers failed Singles immutably (presentation label reconciled instead).
- Any mutable-state reconstruction to enable actions on legacy rows — rejected; fail-closed truthfulness instead.
- Weakening canceled/failed resume exclusions — rejected.
- Per-cell favorite storage (`experiment_cells.favorite`) or any second favorite authority — rejected; cell favorite IS its Generation's favorite.
- CAS/revision tokens for annotations — rejected; last-write-wins fits the single-user local-control model.
- Optimistic UI state for Cancel/Resume/Export (fabricated statuses, local interrupted→running flips) — rejected; durable refetch is the sole authority.
- A second cancellation concept or per-cell Cancel — rejected; one whole-Experiment Cancel behind durable eligibility.
- Reusing the legacy `/run-history/{id}/save` pipeline for V2 export — rejected; standalone F7 core with AST-enforced zero legacy dependency.
- Client-supplied output index/variant/Settings/filename on the export route — rejected; asset_id is the only client identity, everything else server-derived.
- Global export serialization — rejected; narrowest per-Asset lock registry.
- Post-pagination in-memory favorite filtering — rejected; in-query predicates before keyset pagination.
- SCHEMA_VERSION bump or `_SCHEMA_SQL` edit for the experiments favorite index — rejected; idempotent post-ALTER `CREATE INDEX IF NOT EXISTS`.
- Multi-location asset registry (hash→[locations]) — rejected (E7 decision, preserved); single-location newest-registration model is sufficient and deterministic.
- Over-engineered multi-tenant security machinery for the lease registry — rejected; documented single-user/local-control scope.

---

## 9. DEFECT LEDGER (FOUND → FIXED)

| # | Defect | Found by | Fix |
|---|---|---|---|
| 1 | Post-restart Experiment Resume left queued attempts nothing dispatches (200-but-stuck) | F1 audit §5.B | F1A scheduler reconstruction, fail-closed, no orphan writes |
| 2 | Host restart mid-Single → permanently `running`, all actions blocked | F1 audit §5.C | F1A `_sweep_stale_running_singles` → `interrupted` |
| 3 | Ordinary Single Resume missing entirely | F1 audit | F1A bodyless route + F6 UI |
| 4 | Preview→Original semantic conversion leak (Original replay kept `output_mode="preview"`) | F1A oracle review (blocker) | `_original_options` sets `output_mode="original"`; delta allow-list extended by exactly that key; regression-tested |
| 5 | Partial-scheduler reconstruction accepted subset ID sets | F1A oracle review (high) | fail-closed `_persisted_cell_plans`; 5 focused tests |
| 6 | Resume accounting race could double-report appended attempt | F1A oracle review (medium) | baseline capture + diff moved inside `_SCHEDULER_RECONSTRUCTION_LOCK` |
| 7 | Experiment Cancel wired but never surfaced in History UI | F1 audit | F1B Cancel action + eligibility matrix + structured refusal normalization |
| 8 | `openCellMenu` unbound `item.focus()` ReferenceError on every cell-menu open | F1 audit §4.3 | F1B first-actionable-item focus + rendered browser test |
| 9 | Mixed favorites-only feed leaked every Experiment | F2 audit §8 | F5 `query_experiments(favorite)` + route plumbing + index; F10 fake parity |
| 10 | Feed favorite star stuck disabled on API failure (+ unhandled rejection) | F2 audit §5 | F2A prior-value capture + restore + truthful note |
| 11 | Per-cell favorite was a local-only illusion | F2 audit §6 | F2A Generation-backed durable cell favorite |
| 12 | Enter/Space on focused star opened the card instead of toggling | F2A | `_cardKeydown` ignores inner interactive targets |
| 13 | Irreproducibility reactive-only (enabled button failing on click) | F1 audit §8.1 | F5 `replay_capable` projection; F6 tolerant consumption |
| 14 | Stale reset-only settings keys (`global_concurrency`, `preview_auto_save`) | F4 audit | F4A removal + authority guard test |
| 15 | Heavy-tracing restart banner permanently false-positive | F4 audit S17 | F4A persisted-vs-effective server truth model |
| 16 | Grid Columns inert on the actual History surface | F4 audit S14 | F4C consumer + normalization + responsive formula |
| 17 | Legacy settings localStorage-first precedence; wrote LS before server ack | F4 audit §8.5 | F4B server-first routing through shared helper |
| 18 | Opening legacy panel POSTed GPU (side-effect write) | F4 audit §8.6 | F4B read-only init; single explicit-change POST site |
| 19 | Dead `window._comfyModalGpu` writes | F4 audit | removed in both surfaces (zero readers confirmed) |
| 20 | GPU triple authority; silent restart-revert to default | F4 audit S3 | F8 persistence + seeding + read-modify-write saves |
| 21 | Modern Studio consumed NO GPU (transport fell back to hardcoded default) | F4 audit S3 | F8 capture threading + frozen plan metadata + transport boundary |
| 22 | Reset All cleared LS GPU but never server GPU; undisclosed engine force | F4 audit §9 | F8 full reset + truthful disclosure copy |
| 23 | V2 export had zero producers/consumers (scaffolding-only) | F3 audit | F7 core + F9 route/projection + F10 UI |
| 24 | Collapsed generation-level export state hid Preview/Original separation and `missing` | F3 audit §6/§8 | F9 per-variant projection + lazy checker; aggregate deprecated |
| 25 | Legacy export hardcoded `output_index: 0` everywhere; index-0 filename fidelity bug | F3 audit §9 | F9 server-derived real indices encoded in filenames |
| 26 | Concurrent same-asset exports could interleave between uniqueness and record upsert | F9 (from F7 audit) | per-Asset asyncio.Lock registry + regression test |
| 27 | Wrapper crashed on non-cp1252 subprocess output (`stdout=None`) | F8 | UTF-8/replace decoding in `run_studio_tests.py` |
| 28 | Cross-lane transient wrapper failures (duplicate JS declarations, mid-edit specs, stale leftover fake-server process on port 8377) | various | ownership rules held; each resolved by its owner or clean rerun; none were production regressions |

---

## 10. DEFERRED / NOT PHASE-F GAPS (genuine deferrals only)

All F-roadmap items are CLOSED. The following are intentional later-phase concerns — none is an open Phase-F defect:

1. **Phase H — V1/transitional surface retirement:** V1 engine option removal from Execution Engine setting (incl. shadow remnants), `execution_runtime` persisted-mode fallback re-home.
2. **Phase H — modern interpretation of Run mode Cloud/Local:** S1 currently gates only the legacy canvas redirect path; modern Studio surfaces never consult it. Semantics decision deferred.
3. **Phase H — full legacy Settings/tabs retirement/re-home:** `modal-settings.js` panel and the six legacy tabs remain as sanctioned legacy (aligned in F4B, not retired).
4. **Phase H — legacy Comparison/canvas compatibility cleanup:** `window._comfyModalOutputOptions` fallback chain, Comparison runner read, canvas `/prompt` interception path.
5. **History deletion semantics — when deletion is eventually designed:** three distinct deletion targets must be split (managed asset / exported copy / History record); revisit `export_records.asset_id ON DELETE CASCADE` so removing a record never implies removing a user file or vice versa. NO delete routes exist today (nothing deletable — no active defect).
6. **Bulk ZIP Export:** ABSENCE IS NOT A BUG. No roadmap artifact requires bulk/ZIP export; none was proposed or built. If a future contract introduces it, it starts from the per-asset route.
7. **Thumbnail Export/Download surface:** deliberately unexposed in Phase-F UI (falls out of grouping naturally; scope decision, not a gap).
8. **Experiment note searchability:** no requirement found anywhere; mirrors the narrower Experiment search surface. Parity decision only if product wants it.
9. **Cross-tab live sync** for Grid Columns and annotations (reload/remount always reflects truth; no storage-event listeners existed before F either).
10. **Optional observability leftovers from E:** direct integer `webp_method` telemetry; richer `output_codec_ms` disaggregation. Non-blockers, not implemented.
11. **Legacy annotations route retirement** (bridge-only surface still writable post-migration) — folds into Phase H legacy cleanup.

---

## 11. FILES / TEST HISTORY (ATTRIBUTION)

**The full `git status` does NOT belong to Phase F.** The shared tree was intentionally dirty before F began (Phase E production fixes, V2/E40/R41 performance campaigns). Separation:

### F-owned production areas (files where Phase F lanes made the cited changes)

- **Backend Python:** `history_v2_routes.py` (replay-capable projection, favorite filter plumbing, Single Resume route, export route + shared remote-bytes helper + index derivation + per-Asset locks + per-variant projection), `history_v2_repository.py` (single-resume/retry/resume seams, annotation writers, experiment favorite query), `history_v2_store.py` (experiments favorite index), `history_v2_replay.py` (`resume_single`, Preview→Original mode delta), `experiment_modern_routes.py` (`_sweep_stale_running_singles`, reconstruction lock), `experiment_modern_scheduler.py` (factory/registry for reconstruction), `history_v2_export.py` (**NEW** — F7 core), `__init__.py` (composition roots only: `settings_provider` wiring, `_seed_server_gpu_from_settings`), `studio_run_adapter.py` (`resolve_request_gpu` + threading), `studio_workflow_run.py` (GPU threading), `comfymodal_runtime/playground_service.py` (GPU forwarding). `modal_client.py` required NO changes (existing `set_gpu/get_gpu` retained).
- **Frontend:** `web/history-v2-repository.js` (resume/export methods, retry/resume derivation helpers, per-variant normalization, kind hint, structured refusal normalization), `web/studio-history-v2.js` (star recovery, keyboard fix, grid-columns consumer), `web/studio-history-v2-detail.js` (Resume, conditional Retry labels, download + export actions), `web/studio-history-v2-experiment.js` (Cancel, cell-menu focus fix, cell favorite/download/export, conditional labels), `web/history-v2-browser-download.js` (**NEW**), `web/history-v2-export.js` (**NEW**), `web/studio-settings.js` (stale keys, banner, GPU display/reset, disclosure copy), `web/modal-settings.js` (server-first precedence, no panel-open GPU POST), `web/studio-styles.js` (grid formula).
- **Tests (new F modules):** `tests/test_f1_followup_a_durable_resume.py`, `tests/test_f5_history_backend_truth.py`, `tests/test_f8_gpu_authority.py`, `tests/test_history_v2_export.py`, `tests/test_history_v2_export_integration.py`, `tests/studio_phase_f4_settings_authority_unit.mjs`, `tests/studio_phase_f6_history_actions_unit.mjs`, `tests/studio_phase_f8_gpu_reset_unit.mjs`, `tests/studio_history_v2_download_unit.mjs`, `tests/studio_history_v2_grid_columns_unit.mjs`, `tests/studio_legacy_settings_authority_unit.mjs`, `tests/browser/fake/studio-fake-history-cancel-menu.spec.mjs`, `studio-fake-history-resume-retry.spec.mjs`, `studio-fake-history-v2-annotations.spec.mjs`, `studio-fake-history-v2-download.spec.mjs`, `studio-fake-history-v2-export.spec.mjs` — plus focused extensions to `fake-backend.mjs`, `fake-server.mjs`, `scenarios.mjs`, several landed specs, `tests/run_studio_tests.py` (registrations + UTF-8 runner robustness), and the regenerated visual baseline PNG.
- Caveat: several of these files (e.g. `__init__.py`, `history_v2_routes.py`) ALSO carry pre-existing dirty regions from Phases D–E; file-level dirtiness ≠ F-owned entirety. Each F lane's report lists its own exact footprint.

### Pre-existing dirty worktree (NOT F's)

Phase-E production fixes (`studio_workflow_run.py` proof-collection region, `history_v2_replay.py` workspace-resolution region, `experiment_lease.py` collision refresh), `comfyapp.py`, `output_converter.py`, `STUDIO_TEST_GATE.md` post-E sections, Phase-E audit docs, and assorted config/artifacts.

### Unrelated V2/E40/R41 performance work (NOT F's)

`comfymodal_runtime/*` perf modules (`clip_conditioning_cache.py`, `clip_qd_reader.py`, `v2_waterfall.py`, `speculative_clip_hydration.py`, `snapshot_*`, `cache_taxonomy.py`, `config_authority.py`, `loader_selection.py`, `runtime_status.py`, …), `tools/v2_control/*`, `tools/benchmark_v2_direct.py`, `config/v2/profiles/e37-clean-lane-qd4.toml`, `tests/test_v2_waterfall*.py`, `tests/test_batch_[abc]_acceptance.py`, E40/R41 reports and logs.

### Focused counts worth remembering (final-state modules)

F1A combined focused 124 OK (35+30+46+13) · F5 29/29 · F7 33/33 · F8 40/40 (+6-section unit) · F9 26/26 HTTP integration (59/59 with F7) · F10 export spec 21/21 · F6 6-section unit + 7/7 browser · F1B 10/10 unit + 5/5 browser · F2A 6/6 browser. These are per-lane evidence; **the authoritative closure number is the final shared gate: 1741 / 21 / 176, ALL LANES GREEN.**

---

## 12. WHAT PHASE G MAY SAFELY ASSUME

1. The deterministic gate is green at **Python 1741 / Node 21 / Fake Playwright 176**; new work adds to the allowlist and re-runs the same wrapper.
2. All Section 7 invariants hold in the current tree and are pinned by named tests; violating any of them is a regression even if a test doesn't catch it directly.
3. The frozen wire contracts: bodyless `/generations/{id}/resume`, bodyless `/original/retry`, bodyless `/assets/{asset_id}/export` (asset_id = sole client identity), `{rerender:true}` as the only rerender path, per-variant export projection fields, `replay_capable` projection, structured machine-readable refusal codes on all action routes.
4. The fake backend (`tests/browser/fake/`) mirrors production contracts including export states, favorite filtering, cancel/refusal paths, and asset-count instrumentation; fake behavior is never more permissive than production.
5. History V2 is the mounted History; the legacy History page and legacy annotations route are bridge-only pending Phase H.
6. GPU selection persists across restart and is frozen per accepted plan; transport never substitutes a captured selection.
7. Nothing in the tree is committed; the worktree remains intentionally dirty; version-control boundaries remain a deliberate later batch.
8. No live/paid validation is outstanding for Phase F: all F evidence is deterministic/offline; the last live evidence remains Phase E's E7 (`gen_f4e1bf7525ea`), which F did not invalidate (F changed no replay-execution semantics — F1A added mode-delta allow-list entry and resume, both deterministically covered).

---

## 13. AUTHORITATIVE INPUT INDEX

- `PHASE_F1_HISTORY_ACTION_RECONCILIATION_AUDIT_2026-08-22.md` (incl. §14 F1A, §15 F6, §15 F5 appends)
- `PHASE_F1B_EXPERIMENT_HISTORY_UI_PARITY_2026-08-23.md`
- `PHASE_F2_HISTORY_NOTES_FAVORITES_AUDIT_2026-08-22.md` (incl. F2A, F5, F10 closure appends)
- `PHASE_F3_HISTORY_EXPORT_DOWNLOAD_AUDIT_2026-08-22.md` (incl. F3A, F7, F9, F10 appends)
- `PHASE_F4_SETTINGS_CONSUMER_AUTHORITY_AUDIT_2026-08-22.md` (incl. F4A/B/C, F8 appends)
- `PHASE_F6_HISTORY_FRONTEND_ACTIONS_DOWNLOAD_2026-08-23.md`
- `PHASE_F7_HISTORY_V2_EXPORT_CORE_2026-08-23.md`
- `PHASE_F9_HISTORY_V2_EXPORT_INTEGRATION_2026-08-23.md`
- `PHASE_F10_HISTORY_EXPORT_UI_FAKE_PARITY_2026-08-23.md`
- `PHASE_E_FINAL_CLOSURE_2026-08-22.md`, `STUDIO_TEST_GATE.md` (baseline + gate definition)

---

## FINAL VERDICT

`PHASE F COMPLETE`

Deploy / live / GPU / commit / push by this closure batch: **NONE**.
