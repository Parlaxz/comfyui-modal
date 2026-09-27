# Phase F2 — History Notes & Favorites Reconciliation Audit (2026-08-22)

**Lane:** Phase F batch F2 — READ-ONLY notes/favorites audit.
**Base:** `PHASE E COMPLETE` (E6 + E7 + Follow-Up A) + F1 audit.
**Constraints honored:** no production/test edits, no deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. **Files modified by this batch: this audit document only.**

---

## 1. Executive verdict

**F2 verdict: note/favorite are REAL, DURABLE, FIRST-CLASS History V2 actions for both Generations and Experiments — backend COMPLETE, frontend PARTIAL. The largest defect is that the favorite-only filter does not apply to the Experiment stream, so a mixed favorites-only feed shows every experiment. One frontend error-path defect (feed star stuck disabled on API failure) and one misleading control (per-cell favorite is local-only) complete the gap list.**

| Surface | Classification |
|---|---|
| Generation favorite (model/repo/route/UI/persistence) | **COMPLETE** |
| Generation note | **COMPLETE** (explicit-save UI; searchable; migrated from legacy) |
| Experiment favorite / note (whole-experiment) | **COMPLETE** backend + UI |
| Experiment-cell favorite | **INCONSISTENT** — read projection derives from the cell's Generation; the cell-pane star is a LOCAL-ONLY toggle nothing persists |
| Experiment-cell note | **MISSING** (no field, no route, no UI — consistent with Generation-owned cell identity) |
| Favorite-only filter | **PARTIAL** — Generation COMPLETE; Experiment MISSING; mixed feed INCONSISTENT |
| Note search | **PARTIAL** — Generation note searchable (implemented, untested); Experiment note NOT searchable (mirrors its search surface; no roadmap requirement found) |
| Legacy annotations (`PATCH /run-history/{id}/annotations`) | **LEGACY** — still live, duplicated surface; migrated one-way into V2 |

F1's "COMPLETE" classification for note/favorite is confirmed at the layer F1 audited (route inventory); this audit adds the filter/search/sync/error-path precision F1 did not scope.

---

## 2. Schema / model

First-class persisted columns — **not** auxiliary tables:

| Store | Field | DDL | Evidence |
|---|---|---|---|
| `generations` | `favorite INTEGER NOT NULL DEFAULT 0` | + `idx_generations_favorite` | `history_v2_store.py:81,94` |
| `generations` | `note TEXT NOT NULL DEFAULT ''` | — | `history_v2_store.py:82` |
| `experiments` | `favorite INTEGER NOT NULL DEFAULT 0`, `note TEXT NOT NULL DEFAULT ''` | fresh schema + idempotent `ALTER TABLE` upgrade (`_ensure_experiment_annotations`) | `history_v2_store.py:53-54,200-214` |
| `experiment_cells` | **no favorite/note columns** | cells reference `generation_id`; favorite projects through it | `history_v2_store.py:57-67` |

Models (`history_v2_models.py`): `Generation.favorite: bool = False`, `Generation.note: str = ""` (282-283); `Experiment.favorite/note` (422-423); both `from_dict`s coerce tolerantly. Frozen dataclasses; round-trip verbatim. `ExperimentCell` has neither field.

Timestamps: no per-annotation timestamp in V2 — the row's `updated_at` is bumped on every write. (Legacy `meta.annotations` carries its own `updated_at` inside the legacy store only.)

Migrations: SCHEMA_VERSION=2; experiment columns upgraded in place silently (duplicate-column OperationalError swallowed); legacy annotations migrate INTO V2 at `history_v2_migration.py:116-117` via `create_generation(favorite=..., note=...)`. One-way: later legacy edits do not propagate.

---

## 3. Repository

All four writers (`history_v2_repository.py`):

| Method | Line | Semantics |
|---|---|---|
| `set_favorite(generation_id, favorite)` | 1138 | `BEGIN IMMEDIATE` tx; `UPDATE generations SET favorite=?, updated_at=utc_now_iso() WHERE generation_id=?`; returns `rowcount > 0` |
| `set_note(generation_id, note)` | 1147 | raises `ValueError("note exceeds 2000 characters (legacy limit)")` when len>2000; otherwise same shape |
| `set_experiment_favorite(experiment_id, favorite)` | 1721 | same shape against `experiments` |
| `set_experiment_note(experiment_id, note)` | 1730 | same shape + 2000-char guard |

- **Transaction:** single `BEGIN IMMEDIATE` write; commit/rollback via store contextmanager. Atomic.
- **Idempotency:** re-applying the same value succeeds → True.
- **Return values:** boolean written/not-found. No revision token, no previous-value echo.
- **Not-found:** False → routes translate to 404. No exception.
- **Stale-update/CAS:** none — unconditional last-write-wins; no `updated_at` precondition.
- **Ordering side effects:** `updated_at` IS bumped, but every feed order keys off `created_at` (`_keyset_order`, repo.py:146-150) — note/favorite writes NEVER move a card under any of the six orders.
- **Clear semantics:** note clear = empty string (allowed; only length validated). Unfavorite = `favorite=false`.
- Reads: `_row_to_generation` maps with legacy-DB tolerance (repo.py:310-311); `create_generation` accepts `favorite/note` (repo.py:454-455).

---

## 4. API routes

### 4.A History V2 (production, `history_v2_routes.py`)

| Method | Path | Payload | Success | Errors |
|---|---|---|---|---|
| PATCH | `/comfymodal/history-v2/generations/{id}/favorite` (1338) | `{"favorite": bool}` | 200 `{"status":"ok","favorite":<bool>}` | 400 non-bool/bad JSON; 404 unknown id |
| PATCH | `/comfymodal/history-v2/generations/{id}/note` (1352) | `{"note": str}` | 200 `{"status":"ok","note":<str>}` | 400 non-str / >2000 chars / bad JSON; 404 |
| PATCH | `/comfymodal/history-v2/experiments/{id}/favorite` (1403) | same as generation favorite | same | same ("experiment not found") |
| PATCH | `/comfymodal/history-v2/experiments/{id}/note` (1417) | same as generation note | same | same |

Scope is explicit per kind — no polymorphic id resolution server-side. Validation: strict isinstance checks; max length 2000 enforced repo-side, surfaced as 400. Clear = empty string / false. No duplicate V2 routes exist (F1 inventory concurs).

Read projections carrying favorite/note: feed items both kinds (464-465, 536-537), generation detail (same builder), experiment detail header + per-cell `"favorite": bool(fav_by_gen.get(cell.generation_id))` (954-956) and per-cell generation payload incl. favorite/note (`_cell_generation_payload` 868-869). Cells expose **no note**.

Feed filter plumbing: `GET /feed` parses `favorite` via `_parse_bool` (invalid → None → no filter) into `gen_filters` ONLY; `exp_filters = {search, date_from, date_to}` (1062, 1077-1096). `query_generations(favorite=…)` → `g.favorite = ?` (2633-2635); **`query_experiments` has no favorite parameter at all** (2766-2777).

### 4.B Legacy duplicate

`PATCH /comfymodal/run-history/{run_id}/annotations` (`__init__.py:6946-6992`): body `{favorite?, note?}`, 422 on validation failure, merges into legacy `meta.annotations` with its own `updated_at`, 404 unknown run. Bridge-repository target and migration source. **Duplicated/inconsistent:** legacy-row annotation edits after migration diverge from the migrated V2 Generation forever.

---

## 5. Generation UI

- **Feed card star** (`web/studio-history-v2.js:387-412`): star button, `aria-pressed`, stopPropagation (no card open). Durable-first: disables → `await repo.setFavorite(id, next)` → on success updates `record.favorite` + glyph. **DEFECT: no `.catch`** — in v2 mode a rejected PATCH leaves the star permanently `disabled` plus an unhandled promise rejection; no false state is shown (flip happens after server ack), but the control deadlocks.
- **Detail overlay** (`web/studio-history-v2-detail.js`): star section (247-268) with try/catch — on failure keeps prior state and re-renders truthfully; explicit-save Note section (270-301): textarea prefilled from `record.note`, "Save note" button, `Saved`/`Save failed` status span. **Explicit save, not autosave.** Empty textarea + save = durable clear. Both call `cbs.onChanged()` after every attempt (including failures — harmless extra refetch).
- **Keyboard:** cards are `role="button"` `tabindex=0` with Enter/Space handlers (414-419); stars are native buttons. No dedicated shortcut for either action.
- Loading/error handling: button-disable during flight (feed); status text (detail). No toast.

## 6. Experiment UI

(`web/studio-history-v2-experiment.js`)

- **Whole-experiment star** (433-454) in the title row + **Note** section (456-487) in the header — identical mechanics to generation detail (try/catch revert; explicit Save note; Saved/Save failed).
- **Per-cell favorite** (811-825): cell detail pane renders a star that flips `cell.favorite` **in memory only** — code comment states "the repository has no per-cell setter". Never persisted, lost on reload/re-render, syncs to nothing. Misleading affordance.
- Per-cell **note**: none rendered (consistent with backend).
- `onChanged` → parent `fetchFeed(true)` (studio-history-v2.js:544-546) — experiment-card changes reach the feed immediately.

## 7. Synchronization

- **Generation detail → feed card:** `onChanged` → `fetchFeed(true)` refetches page 1 and re-renders the grid beneath the overlay — coherent. Cost: scroll position and pagination depth reset to page 1 on every detail mutation; deep-paginated items leave the visible window (server state stays truthful).
- **Generation detail → favorite-only filter:** while `favoriteOnly` is active, unfavoriting in detail then closing shows the card gone after the triggered refetch — correct.
- **Experiment detail → experiment card:** same mechanism, works.
- **Cell pane ↔ anything:** per-cell star syncs nowhere (local object mutation).
- **Feed → detail:** detail always loads fresh from `GET /generations/{id}` / `GET /experiments/{id}` on open — no stale cache.
- **Cross-tab:** no broadcast/storage events; a second tab sees changes only on its next fetch. No duplicated client-side annotation state found (normalization reads `raw.favorite`/`raw.note` with legacy `annotations.{favorite,note}` fallback, history-v2-repository.js:468-476).
- **Verdict:** synchronization is COHERENT everywhere the data is durable; the only stale/duplicated-state problem is the per-cell local toggle.

---

## 8. Favorite filter (end-to-end)

UI chip "Favorites only" (`BOOL_LABELS`, studio-history-v2.js:678-698) -> persisted `viewState.filters.favoriteOnly` (localStorage schema 2, history-v2-view-state.js:39,68) -> `q.favoriteOnly` -> `favorite=true` query param (repository.js:929) -> route `gen_filters["favorite"]` -> `query_generations(favorite=True)` -> `g.favorite = 1` (indexed).

| Stream | Works? |
|---|---|
| `kind=generation` | **YES** — complete chain |
| `kind=experiment` | **NO** — parameter dropped; `query_experiments` cannot express it |
| `kind=mixed` | **INCONSISTENT** — generation stream filters, experiment stream does not: favorites-only mixed feed lists EVERY experiment plus favorited generations |

Semantics differ by kind: Generation favorite is per-output-record; Experiment favorite is per-matrix (cells inherit nothing in either direction). Legacy bridge sends `favorite_only=true`; the legacy index honors it (`history_index.py:490-491`).

## 9. Notes search

- **Generation: YES** — `search` matches `g.note LIKE ? ESCAPE '\'` among 12 targets (repo.py:2651-2664); fake mirrors exactly (fake-backend.mjs:2498 includes `rec.note`).
- **Experiment: NO** — search covers `experiment_id`, `name`, `definition_json` only (repo.py:2812-2815; fake `_expMatchesV2` mirrors).
- **Product intent:** no roadmap/phase document found that requires notes to be searchable (F1 mentions notes only as route inventory; STUDIO_TEST_GATE.md never references note search). Generation-side search is implemented behavior (currently untested); experiment-side absence mirrors its narrower search surface. No invented requirement asserted here.

## 10. Race / failure semantics (current truth)

| Case | Current behavior |
|---|---|
| Duplicate favorite click | Feed: guarded by `star.disabled` during flight. Detail: no disable, but both clicks compute the same `next` from unchanged state -> two identical PATCHes, benign |
| Note save race (same tab) | Button disabled during flight; sequential |
| Two tabs editing note | Last-write-wins silently; no revision/CAS; no conflict signal. Given single-user local-control product model this appears deliberate — CAS NOT recommended |
| API failure after optimistic UI | Detail star/note revert truthfully with status text. FEED STAR DEFECT: no rejection handler -> stuck disabled + unhandled rejection (v2 mode) |
| Empty note | Valid durable clear ("" passes validation) |
| Clear favorite | `favorite=false` PATCH; idempotent |
| Legacy row via V2 route | 404 from generations then experiments (frontend fallback tries both); legacy ids only writable through the legacy annotations route (bridge mode) |

No revision/CAS semantics exist anywhere in the annotation path. Recommendation: keep last-write-wins; do not over-engineer.

## 11. Fake backend parity

(`tests/browser/fake/fake-backend.mjs`, `fake-server.mjs`)

Parity (mirrors production exactly):
- Routes `PATCH .../generations|experiments/{id}/favorite|note` with identical validation and error messages incl. the 2000-char limit (3031-3069, fake-server.mjs:502-519).
- Favorite feed filter for generations (`_genMatchesV2` 2479), note-in-generation-search (2498).
- Experiment-stream gaps mirrored: `_expMatchesV2` has NO favorite check and NO note search (2504-2513) — production's favorite-filter gap is faithfully reproduced.
- Modern-experiment fallback: fake `setHistoryV2Favorite(kind="experiment")` miss falls back to `session.modernExperiments` registry (3037-3043); production equivalent is the experiments table itself.

Fake-only capabilities / divergences:
- **Per-cell favorite seeded values** (`favorite: j % 7 === 0`, line 2091) surfaced in experiment detail cells (`_experimentDetailItem` 2277). Production derives cell favorite from the cell's Generation (`fav_by_gen`). A cell whose Generation is favorited can therefore show DIFFERENT favorite state in fake vs production. Read-only divergence (no setter exists on either side).
- Legacy mock project (`tests/browser/studio-mock-api.mjs`) implements the legacy annotations route + `favorite_only` filtering for bridge-mode tests.

Production-only: true durability across sessions/hosts (SQLite WAL), migration of legacy annotations.

## 12. Test coverage matrix

Covered today:
| Case | Lane | Evidence |
|---|---|---|
| Generation favorite set/unset persistence + feed reflection + 404 | Python API | `test_history_v2_api.py:365-388` |
| Generation note set + feed reflection + >2000 -> 400 + 404 | Python API | `test_history_v2_api.py:390-409` |
| Experiment favorite+note durable (direct DB rows) + feed + 404 + >2000 | Python API | `test_history_v2_api.py:489-517` |
| Repo set_note/set_favorite, >2000 raises, favorite query filter | Python repo | `test_history_v2_repository.py:198-208,473-475` |
| Legacy annotations migrate into V2 | Python migration | `test_history_v2_migration.py:61-69` |
| Note/favorite controls present in generation detail | Fake browser | `studio-fake-history-v2.spec.mjs` #2 |
| Favorite toggle persists server-side across reload | Fake browser | spec #4 |
| Note persists server-side across reload ("Saved" status) | Fake browser | spec #5 |
| Repository contract exposes setFavorite/setNote | Node unit | `test_studio_history_v2_js.py:87` |
| favoriteOnly view-state default round-trip | Node unit | `studio_history_v2_persisted_status_unit.mjs` |

Exact missing cases:
1. **favoriteOnly filter end-to-end** (any lane): UI chip -> feed shows only favorited records. NONE anywhere.
2. **Mixed-feed favorite=true experiment leak** (the §8 defect) — untested, unfixed.
3. **Experiment favorite/note UI flows** (browser lane): toggle star / save note on experiment detail, persist across reload. NONE (only API-level).
4. **Note clear-to-empty**: no test saves "" after a non-empty note (only over-long rejection covered).
5. **Unfavorite-across-reload in browser lane** (API covers toggle-off but not reload visibility).
6. **Note-search correctness** (generation note text matches search; experiment note does NOT match).
7. **API-failure UI recovery**: no fake scenario simulates favorite/note failure; the feed-star-stuck defect is invisible to the gate.
8. **Two-tab / concurrent LWW race** for annotations.
9. **Per-cell favorite contract** (whatever is decided: remove vs bind to Generation) — currently zero coverage of the local-only toggle.
10. **Legacy post-migration divergence** (legacy annotation edit after migration stays legacy-only).

## 13. Exact implementation gaps (NOT implemented by this batch)

1. **Favorite-only filter ignores Experiments** — add `favorite` param to `query_experiments` (+ `e.favorite = ?`) and pass it through `exp_filters` in the feed route (mixed + experiment kinds). Largest product-facing gap.
2. **Feed favorite star has no rejection handler** (`studio-history-v2.js:403`) — add `.catch` that re-enables the star and restores prior glyph (mirror detail's try/catch).
3. **Per-cell favorite toggle is local-only/misleading** (`studio-history-v2-experiment.js:811-825`) — decide ownership: either remove the control or bind it to the cell's `generationId` via the existing Generation-scoped favorite route (recommended canonical model: Experiment-level AND Generation-level ownership already exist; cell favorite should simply BE its Generation's favorite — no new storage).
4. **Experiment note not searchable** — parity decision only if product wants it; no requirement found.
5. **Test gaps 1-10 above**, minimum gate-worthy set: favoriteOnly end-to-end (generation + mixed-leak regression), experiment favorite/note browser flow, note clear-to-empty, favorite-failure UI recovery.
6. **Documentation/freeze of the LEGACY annotations surface** — still live and writable post-migration; either document as frozen-for-bridge-only or plan retirement.

History defaults preserved everywhere: completed visible, interrupted visible, failed hidden, canceled hidden (`DEFAULT_HIDDEN_STATUSES`, history-v2-view-state.js:24), no Trash; favorite/note writes touch neither status fields nor status filters nor feed ordering.

---

*Read-only audit. No deploy, no live run, no GPU, no commit/push.*

---

## F2 Implementation Follow-Up A — Frontend Annotation Correctness

**Lane:** Phase F batch F2 follow-up A — History notes/favorites FRONTEND implementation (concurrent F1 backend Resume agent owns shared History Python; untouched by this lane).
**Verdict: PASS.** All four known frontend defects in scope are fixed and covered; the mixed-feed `favoriteOnly` Experiment leak remains backend-owned (see §F2A.7).

### F2A.1 Feed favorite star failure recovery (§5 defect → FIXED)

Root cause: `renderFavoriteStar` (`web/studio-history-v2.js`) chained only `.then()` on `repo.setFavorite` — a rejected PATCH left the star permanently `disabled`, produced an unhandled promise rejection, and had no error surface.

Fix (`web/studio-history-v2.js`): capture prior durable value before flight; disable during request; on success adopt the acknowledged value (`ack.favorite`) into the record + glyph + `aria-pressed`/label/title and re-enable; on failure restore the prior glyph/state, re-enable, and surface a bounded truthful "Favorite failed" note using the existing `comfymodal-studio-history-v2-action-note` pattern (empty by default — cards render unchanged). The star+note live in a neutral `.comfymodal-studio-history-v2-fav-wrap` span inside `card-top`. No optimistic fake success; ordering untouched (writes bump `updated_at`, feed orders key off `created_at`).

Keyboard activation fix (same file): `_cardKeydown` no longer hijacks Enter/Space when the event target is an inner interactive control (`button/input/select/textarea`) — previously Enter on a focused star opened the card instead of toggling it.

### F2A.2 Canonical cell favorite ownership (§6 defect → FIXED)

Decision implemented: **a cell's favorite IS the favorite of its associated Generation.** The cell-pane star (`web/studio-history-v2-experiment.js` `buildCellDetail`) is now a real durable control:

- reads the cell's existing `generationId` (`_cellGenerationId`);
- calls `repo.setFavorite(generationId, next)` — the SAME Generation-scoped route as feed/detail stars;
- disables during flight (duplicate clicks impossible); cells without a Generation identity render disabled with a truthful title;
- success → refresh through the EXISTING Experiment detail flow (`repo.getExperiment` → `_rerenderPage(fresh)`, same durable refetch the Original poll loop uses) so the cell projection reflects server truth; then `cbs.onChanged()` keeps the feed consistent; focus is restored to the rebuilt star;
- failure → restores prior state, re-enables, shows bounded "Favorite failed" note; nothing persists locally (no local-only illusion);
- new stable testid: `history-v2-cell-favorite`.

No `experiment_cells.favorite`, no new route, no duplicated storage, no bespoke cache. Whole-Experiment favorite remains independent (Experiment = entire matrix; Generation = one cell/generation; no propagation either direction).

### F2A.3 Repository kind hint (narrow change, `web/history-v2-repository.js`)

`setFavorite(id, favorite, opts)` / `setNote(id, note, opts)` accept an optional `{kind:"experiment"}` hint that tries the experiments scope FIRST (falling back to the other scope once on 404, as before). The Experiment UI passes the hint so whole-experiment annotation writes no longer produce a spurious generations 404 round-trip (and its console noise). Bridge/fixture repositories ignore the extra argument; generation callers are unchanged.

### F2A.4 Fake backend parity (§11 divergence → FIXED)

- `_experimentDetailItem(session, rec)` now derives per-cell `favorite` from the cell's Generation record (`fav_by_gen` mirror of production routes 954-956). Cells carry NO favorite storage of their own: removed `favorite: !!c.favorite` from `_makeV2Experiment` cell objects and the hardcoded cell `favorite:false` from `_modernHistoryRecord`. Fixtures needing a favorited cell must favorite its Generation.
- One-shot/request-scoped failure injection: `/__comfymodal_test/history-v2-fail {mode:"favorite_once"}` fails exactly the NEXT favorite PATCH with 500 and self-clears (later retries succeed; never a global breakage). Existing `feed` mode unchanged.

### F2A.5 New coverage (`tests/browser/fake/studio-fake-history-v2-annotations.spec.mjs`, 6 tests — all PASS)

| Test | Proves |
|---|---|
| A1 | Feed star failure: re-enables, prior glyph/aria kept, "Favorite failed" note, server state unchanged, no unhandled rejection, card still opens, keyboard retry succeeds |
| A2 | Star disabled while PATCH in flight (route-gated), reverts on rejection, duplicate clicks impossible, retry succeeds |
| A3 | Cell star drives the GENERATION route (`gen_phase_e_original_cell_0` favorited), full reload preserves it, focus preserved after refetch, whole-Experiment favorite stays false, feed's Generation card reflects the same favorite |
| A4 | Cell star failure leaves zero local state; reload shows server truth; Experiment favorite unchanged |
| A5 | Whole-Experiment favorite + note persist across reload/reopen; note clear-to-empty persists; favorite unaffected by note ops |
| A6 | Generation note save → clear-to-empty → persists empty across reload |

Also covered throughout: native `<button>` semantics, `aria-pressed` truthfulness, keyboard activation (Enter on focused star), no card-open side effect from star clicks.

### F2A.6 Test results

- Focused annotation spec: **6/6 PASS**.
- Full fake Playwright suite (`playwright.fake.config.mjs`): **132 passed / 0 failed** (includes all pre-existing history-v2/experiment/phase-e specs).
- Node units: `studio_history_v2_experiment_unit.mjs` 8 PASS, `studio_history_v2_persisted_status_unit.mjs` 9 PASS.
- Python structural: `tests.test_studio_history_v2_js` 49 OK.
- Full wrapper `python tests/run_studio_tests.py --fake`: node-unit 16/16 PASS, fake-playwright PASS; python run=1609 fail=1 — the single failure is `test_testing_shell_integration.test_modal_settings_js_syntax`: `web/modal-settings.js` declares `normalizeOutputSaveFolder` twice. **NOT this lane's file** (Settings is out of scope; file was modified concurrently in the shared dirty tree). Reported separately; not fixed here per ownership rules.

### F2A.7 Remaining gap (unchanged, backend-owned)

**F2 backend follow-up pending:** mixed-feed `favorite=true` filters Generations but not Experiments (`query_experiments` has no favorite parameter; `exp_filters` drops it). Deliberately NOT touched — concurrent F1 agent owns shared History Python. The `favoriteOnly` UI chip remains intact and unweakened.

**Files modified by THIS lane:** `web/studio-history-v2.js`, `web/studio-history-v2-experiment.js`, `web/history-v2-repository.js` (kind hint only), `tests/browser/fake/fake-backend.mjs`, `tests/browser/fake/studio-fake-history-v2-annotations.spec.mjs` (new), this audit document. Deploy/live/GPU/generation/commit/push: NONE.

---

## F5 Backend Reconciliation — Experiment Favorite Filter (backend truth closure)

**Lane:** Phase F batch F5 — closes §8/§13-gap-1, the backend-owned half of the favoriteOnly defect that F2A deliberately left untouched. Constraints honored: backend/tests/docs only; no frontend JS; no deploy/Modal/GPU/live generation; no commit/push/branch/reset.

### F5.1 What was implemented

| Item | Implementation |
|---|---|
| Repository | `query_experiments(...)` gains `favorite: Optional[bool] = None`. `True` → `e.favorite = 1`; explicit `False` → truthful inverse `e.favorite = 0` (mirrors generation semantics exactly); omitted/None → no predicate, byte-for-byte unchanged query behavior. The predicate is ANDed INSIDE the SQL where-clause before keyset pagination — filtering is never post-pagination in memory, so single-kind and mixed cursors stay truthful. Composes with the existing `search` / `date_from` / `date_to` / statuses predicates and all six orders without replacing any of them. |
| Route plumbing | `GET /comfymodal/history-v2/feed` now passes `favorite` into `exp_filters` (previously generation-only), so `kind=experiment` and `kind=mixed` both filter the Experiment stream. Invalid `favorite` values still parse to None → no filter (unchanged). |
| Mixed feed | `favorite=true` mixed merge now contains ONLY favorited Generations and favorited Experiments; unfavorited Experiments can no longer leak on any page. Generation-only behavior is preserved exactly (same `query_generations` path, untouched). |
| Indexing choice | `experiments.favorite` had NO index while generations had `idx_generations_favorite`. Added idempotent `CREATE INDEX IF NOT EXISTS idx_experiments_favorite ON experiments(favorite)` inside `HistoryV2Store._ensure_experiment_annotations` (`history_v2_store.py`) — deliberately NOT in `_SCHEMA_SQL`, because `executescript(_SCHEMA_SQL)` runs BEFORE the column-upgrade ALTERs on pre-existing databases and would fail with "no such column" on legacy DBs. Placed after the ALTER loop it is guaranteed safe on every database shape, needs no SCHEMA_VERSION/user_version bump (additive index only), and mirrors the Generation favorite indexing for consistency. |

### F5.2 Tests (`tests/test_f5_history_backend_truth.py`, new)

Favorite lane covers all eleven required cases plus inverse semantics and the migration itself: generation-only `favorite=true`; experiment-only `favorite=true`; mixed `favorite=true` filters both streams; mixed page-1→cursor→page-N continuation with interleaved favorited/unfavorited rows of both kinds proves zero leakage and zero duplicates across pages (filtering happens in-query); favorited-Generation+unfavorited-Experiment, unfavorited-Generation+favorited-Experiment, both-favorited, neither-favorited; `favorite=true&search=…` composition; `favorite=true&date_from/date_to` composition; no-favorite-param preserves prior behavior verbatim (totals, kinds, newest ordering); explicit `favorite=false` returns only unfavorited experiments; repository-level composition with search/date/order/limit-cursor; index existence + double-initialize idempotency + legacy DB (table without the columns) upgrades cleanly and gains the index.

### F5.3 Fake backend parity — REQUIRED FOLLOW-UP (not landed here, by design)

This batch did NOT edit `tests/browser/fake/fake-backend.mjs`: a concurrent frontend lane owns that file in the shared dirty tree (F6 asset controls), and the batch contract prefers no concurrent-write collision. Exact parity update required for later reconciliation:

1. In `_expMatchesV2` (~line 2504): add the same favorite check `_genMatchesV2` has (~line 2479) — when `filters.favorite === true` require `rec.favorite === true`; when `=== false` require `!rec.favorite`; absent/undefined → no constraint.
2. Thread the parsed `favorite` query param into the experiment branch of the V2 feed handler exactly as the generation branch already does.
3. Optional regression spec: seed one favorited + one unfavorited experiment, `GET feed?kind=mixed&favorite=true` must return only the favorited experiment.

Until then the fake mirrors the OLD broken behavior (documented in §11) while production filters correctly — a read-only divergence invisible to every existing fake test (none exercises favoriteOnly end-to-end).

### F5.4 Evidence

- Focused: `tests.test_f5_history_backend_truth` → **29/29 OK** (replay-capability + favorite lanes together).
- Regression: History V2 repository/API/replay-core/generate-original/F1A-resume/JS-structural → **169 OK**; modern-experiment + scheduler → **96 OK**.
- Full wrapper `python tests/run_studio_tests.py --fake`: **python run=1642 fail=0 error=0 skip=0**. Node-unit (6 files) and fake-playwright (~27 specs) failed AT WRAPPER TIME on a concurrent frontend defect owned by another lane (`web/history-v2-repository.js:1385` declares `_v2ResumeGeneration` twice → SyntaxError in every unit/spec importing it; several pass when re-run directly afterward). Not touched by this lane per ownership rules; unrelated to backend changes (the fake browser lane never imports Python routes).

**Files modified by THIS lane:** `history_v2_repository.py`, `history_v2_routes.py`, `history_v2_store.py` (index only), `tests/test_f5_history_backend_truth.py` (new), this document, and the F1 audit document (§15). Deploy/live/GPU/generation/commit/push: NONE.

---

## F10 Closure — F5 §F5.3 Fake Favorite-Filter Parity (2026-08-23)

The exact fake gap §F5.3 deferred is now closed in the fake-owner batch (no production Python touched):

- `tests/browser/fake/fake-backend.mjs` `_expMatchesV2` gained the same favorite constraint `_genMatchesV2` already had — `favorite === true` requires `rec.favorite === true`, `=== false` requires unfavorited, absent → no constraint — applied INSIDE the stream match before keyset pagination (never post-filtered).
- The parsed `favorite` query param is threaded into `expFilters` exactly as production's feed route now does, so `kind=experiment` and `kind=mixed` both filter the Experiment stream.
- End-to-end regression (NEW `tests/browser/fake/studio-fake-history-v2-export.spec.mjs`, tests 18–19): favorites-only mixed feed contains exactly the favorited Generation + favorited Experiment and neither unfavorited record; filter persists across reload; whole-Experiment favorite keeps working through real UI flow; F2A Generation-backed cell favorite remains independent under the filter. 21/21 PASS in that spec; full-suite counts in `PHASE_F10_HISTORY_EXPORT_UI_FAKE_PARITY_2026-08-23.md`.

This closes §13-gap-1's last open half (fake parity); production truth landed in F5. Files modified by THIS closure: `fake-backend.mjs`, the new export spec, `web/history-v2-repository.js` / detail / experiment / export-helper (Export lane scope), two registered Node units, this document, and the F3 audit document. Deploy/live/GPU/commit/push: NONE.
