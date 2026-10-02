# PHASE I4 — HISTORY POLISH & SHARED-PRIMITIVES MIGRATION — 2026-08-25

## Verdict

## `I4 COMPLETE — I5 READY`

History lane of Phase I, executed directly on the shared dirty working tree (no
reset/revert/stash/branch/worktree; no commit/push/deploy/Modal/GPU/live generation;
no subagents). I4 ran in parallel with I6/I7/I8; only I4-owned files were written.
No A/B-compare work was performed (I5-reserved surfaces untouched).

---

## 1. Pre-change re-measurement (I3 census verified, not assumed)

| I3 handoff item | Verified current truth before editing |
|---|---|
| Loading sites | `studio-history-v2.js` renderResults feed-loading + `showExperiment` swap placeholder; `-detail.js` `_renderLoading`; `-experiment.js` mount placeholder — all four rendered a bare `comfymodal-studio-history-v2-state` div with text `Loading…`, zero aria semantics |
| Chips | `comfymodal-studio-history-v2-chip status-*` built by `_statusChip()` in all three modules; vocabulary = completed / completed_with_failures / failed / canceled / interrupted / running (+ experiment canonical aliases incl. queued) |
| Empty states | feed `emptyStateEl()` ("No history matches your filters" + Clear filters); tiny placeholders: card `_assetPlaceholder`, cover-empty slots, detail output-thumb-empty span, cell `_cellAssetPlaceholder` |
| I1 a11y | no page h2 on History ✓ (confirmed); favorite stars emitted bare "Add to favorites"/"Remove from favorites" ✓ duplicate family confirmed (feed cards ×N); generation detail did not move focus in on open ✓ — and re-measurement showed WHY Escape-restore "worked": `registerLayerHandler` performs NO focus capture/restore; focus never entered the overlay, so the invoker simply never lost it. Experiment detail re-measured: page-swap drops focus to `<body>` on open AND on Back (same defect class) |

---

## 2. Loading migration result

Imported `renderLoadingState` from `web/studio-loading.js` (zero new module cycles —
the primitive is import-free). Four DOM sites migrated; state machine
(INITIAL/LOADING/EMPTY/READY/ERROR/STALE stale-token guard) untouched:

| Site | New primitive call |
|---|---|
| Feed initial/loading (`renderResults`) | `{ label: "Loading history…", size: "page", testid: "history-v2-loading" }` |
| Experiment sub-page swap placeholder (`showExperiment`) | `{ label: "Loading experiment…", size: "page", testid: "history-v2-experiment-loading" }` |
| Generation detail `_renderLoading` (close button preserved first) | `{ label: "Loading generation…", size: "page", testid: "history-v2-detail-loading" }` |
| Experiment detail mount placeholder | `{ label: "Loading experiment…", size: "page", testid: "history-v2-experiment-detail-loading" }` |

Not migrated (per freeze): "Load more" button stateful label, domain progress/action
notes ("Queuing…", "Generating Original…"), View Original inline states. The bare
generic `"Loading…"` string no longer exists anywhere in the three History modules
(source-pinned).

## 3. Chip migration result

All three `_statusChip` builders now emit
`class="comfymodal-studio-history-v2-chip status-<key> cm-chip"` +
`data-tone`. Legacy classes and their CSS blocks fully preserved; status meanings
unchanged. Mapping derived from actual source vocabulary:

| Status | tone | | Status | tone |
|---|---|---|---|---|
| completed | ok | | canceled | neutral |
| completed_with_failures | warn | | running / queued / pending | running |
| failed | error | | unknown passthrough | neutral |
| interrupted | warn | | | |

Unknown statuses keep the existing fallback key semantics (feed/detail fall back to
`status-running`; experiment canonicalizes then passes unknown keys through). The chip
dot (`::before`) identity is retained. Note: `.cm-chip[data-tone]` rules sit later in
studio-styles.js at equal specificity, so tones now recolor chip backgrounds/borders
from tokens — sanctioned convergence, recorded as the one visual delta (below).

## 4. Empty-state migration result

- **Migrated:** feed-level `emptyStateEl()` → `renderEmptyState({ title: "No history
  matches your filters", action: <Clear filters button>, testid: "history-v2-empty" })`.
  Copy, action control, and behavior identical; no alert/live semantics introduced.
- **Deliberately NOT migrated** (too small; forcing them through the section-level
  primitive would break layout): card thumb placeholder, cover-empty slots, detail
  `output-thumb-empty`, cell asset placeholder, cell-detail hint pane. Source-pinned as
  intentional.

## 5. Page heading result

`renderHistoryV2` now renders a truthful `<h2 data-testid="history-v2-page-title">
History</h2>` as the first child of the page root (both on initial mount and after
back-navigation rebuild). No visually-hidden utility existed in `web/`, so the heading
uses a local inline clip-pattern style
(`position:absolute;width:1px;height:1px;margin:-1px;padding:0;border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap`)
— never display:none / visibility:hidden / hidden; zero shared-style edits. Card titles
were NOT promoted into headings (no new h3 anywhere). The experiment sub-page already
carried its own h2 (experiment name), giving a truthful h2 under the shell h1 there too.

## 6. Favorite accessible-name result

New `_favoriteAccessibleName(record, favorite)` builds context-bearing names for every
feed star (generation and experiment cards): verb + kind + record context + to/from
favorites, e.g. `Add generation Aug 25, 2:31 PM (#b12cdf) to favorites`,
`Add experiment Seed Sweep — completed (e_007) from favorites`. Context = experiment
name when present, else formatted start time; a short id tail (last 6 chars) is always
included so simultaneously visible stars are deterministically unique without exposing
full UUIDs. Applied to both the initial attributes and the post-PATCH repaint.
Experiment detail: header star named by kind ("Add experiment to favorites"); per-cell
stars gained cell context via `cellAxisLabel` ("Add generation for seed 1 to
favorites") since N cell stars render simultaneously. Runtime proof (fake test C): all
visible star names unique across the seeded 48-record feed; toggle flips the verb while
preserving context.

## 7. Generation detail focus-in result

Defect root cause identified precisely: focus restoration previously "worked" only
because focus never entered the overlay. Fix keeps one authority path:

- **Open:** the invoking element is captured synchronously at entry
  (`document.activeElement`, null if body); after every mount-state render
  (`_renderLoading` / `_renderDetail` / `_renderNotFound`),
  `_ensureDialogFocus()` focuses the close button (first enabled control) ONLY when
  the dialog currently holds no focus — synchronous post-mount, no timeout race,
  no focus stealing during user interaction.
- **Close:** `_restoreInvokerFocus()` runs after overlay removal — restores the exact
  invoking element, or re-resolves it by its stable testid+id identity when the durable
  refetch (`onChanged → fetchFeed`) rebuilt the grid meanwhile. Escape flow itself is
  unchanged (layer 3 handler untouched); no second focus trap was built; shell
  inert/layer behavior remains authority.

Fake test D proves keyboard-only: Tab-focus card → Enter → activeElement is the Close
button inside the dialog → Escape → overlay gone → `activeElement === invoking card`.

## 8. Experiment detail result

Same-defect analog found and fixed in the same pattern (page-swap form): after
`showExperiment` appends the resolved page (or its not-found placeholder), focus moves
to the first enabled control — the "← Back to history" button; during fetch, the held
loading state uses the shared primitive. Back navigation rebuilds the feed via
`renderFeedPage`, which now returns focus deterministically to the Search input instead
of dropping to `<body>`. Fake test E proves: Enter on focused experiment card →
`role="status"` "Loading experiment…" → release → Back button focused → Enter on it →
feed restored with Search focused. Not rewritten into a dialog; no layer registered.

## 9. History authority regression proof

- Repository adapter paths untouched: feed/favorite/note/featured/original/retry/
  resume/export calls are byte-identical (only DOM construction changed).
- Phase-H suites green inside the gate: `test_run_history.py`,
  `test_run_history_save.py`, `test_task2_run_history_extensions.py`,
  `test_h15_wave_f_server_freeze.py` (179 passed + 42 subtests, focused run);
  full Python lane 2124/2124 with 0 fail/error/skip.
- Node History owners green: persisted-status, experiment, grid-columns, F6 actions,
  download, E4C/E4D units (focused standalone PASS each) plus presentation unit with
  new §17–23 pins asserting: replay/Original click-only ordering intact, retry routes
  unchanged, legacy chip classes verbatim, Load-more custom label retained.
- Existing fake History suites green: Studio History V2 (40-test focused sweep incl.
  annotations/download/resume/cancel/recent-runs), experiments, persistence.
- Download-vs-Export distinction untouched (helpers unmodified).

## 10. Test-count ledger

| Lane | Before I4 | After I4 | Delta |
|---|---|---|---|
| Python (`run_studio_tests.py`) | 2124 / 0 fail | **2124 run, 0 fail, 0 error, 0 skip** | 0 |
| Node unit files | 27 | **27** (no runner edit; extended existing owners) | 0 files |
| Fake Playwright (direct exact) | 219 | **225 passed / 225** | **+6 = exactly the six I4 spec tests** |

Arithmetic reconciles exactly: 219 + 6 = 225.

### Tests touched by THIS lane

- NEW permanent spec `tests/browser/fake/studio-fake-phase-i4-history-polish.spec.mjs`
  — 6 tests: A page h2 + chip tones; B deterministic loading semantics (feed + detail)
  via post-mount awaited route holds; C unique distinguishable favorite names + flip;
  D keyboard detail focus flow; E experiment loading + focus-in + back anchor; F no
  Compare UI (no Compare controls; `studio-image-compare.js` import rejects).
- Extended registered owner `tests/studio_phase_e_history_presentation_unit.mjs`
  (§17–23 source-contract pins for this lane's production changes).
- Stale-pin updates (documented drift, same precedent as I2's `_trapTab` re-point):
  - `tests/studio_phase_i3_shared_primitives_unit.mjs` §20: retired the three
    verbatim History loading pins and removed the three History files from the "must
    not reference primitives yet" list (that staged guard explicitly anticipated
    downstream consumption); non-History entries kept byte-intact for I6/I7/I8.
  - `tests/test_studio_backend.py::HistorySafeRenderingTests`: the exact-string pin
    `import { el } from "./studio-ui.js"` now asserts el() is imported BY NAME from
    studio-ui.js (regex) — the feed module legitimately gained `renderEmptyState` in
    the same import. innerHTML prohibitions unchanged.
- Regenerated ONE Playwright baseline:
  `tests/browser/fake/studio-fake-visual.spec.mjs-snapshots/history-grid-fake-chromium-win32.png`
  — sole visual delta is the sanctioned chip-tone recolor (token backgrounds/borders)
  plus 5px→4px chip gap from the shared base; playground/experiment-grid baselines
  passed unchanged. Regenerated via the command documented in the spec header.

## 11. Observed shared gate

```
python tests/run_studio_tests.py --fake   (tree visible to this lane, incl. concurrent siblings)
  python             run=2124  fail=0  error=0  skip=0
  node-unit          run=27    fail=0  error=0  skip=0
  fake-playwright    PASS        → ALL STUDIO LANES GREEN

npx playwright test --config=playwright.fake.config.mjs --reporter=line
  225 passed / 225   (direct exact count)
```

Sibling-lane tests visible in the shared fake total are attributed to their lanes;
this lane claims exactly its +6 above. A later convergence lane freezes the combined
baseline.

Known pre-existing quirk surfaced by artificial latency (NOT fixed here — out of
scope/files): holding `/history-v2/feed` across a Playground→History transition lets
Playground's late recent-runs response re-render Playground over the active History
page (stale-async guard gap in the Playground consumer, I8-owned surface). No gate
test exercises that artificial condition; normal flows unaffected.

## 12. Files modified by THIS lane only

Production:
- `web/studio-history-v2.js`
- `web/studio-history-v2-detail.js`
- `web/studio-history-v2-experiment.js`
- `web/history-v2-view-state.js` — **untouched** (no change required)

Tests:
- `tests/browser/fake/studio-fake-phase-i4-history-polish.spec.mjs` (NEW)
- `tests/studio_phase_e_history_presentation_unit.mjs` (extended, §17–23)
- `tests/studio_phase_i3_shared_primitives_unit.mjs` (§20 stale staged-guard update)
- `tests/test_studio_backend.py` (one assertion re-pointed, documented above)
- `tests/browser/fake/studio-fake-visual.spec.mjs-snapshots/history-grid-fake-chromium-win32.png` (regenerated baseline)

Not touched: `studio-ui.js`, `studio-styles.js`, `studio-loading.js`, `studio-shell.js`,
`modal-testing.js`, playground/workflows/models/portability/backend/settings files,
backend, `tests/run_studio_tests.py`.

Focused gates additionally run green: I2 fake spec (5), I3 fake spec (3), I4 fake spec
(6, stable across repeated runs), History V2 fake sweep (40), run-history + H15 Python
(179+42 subtests), nine History/I2 Node units standalone, `node --check` on all
modified JS.

## 13. Next dependency statement

`I5 READY` — generation-detail and experiment-detail surfaces are migrated and pinned;
Compare must be built strictly after this lane lands (I4 owns those files first).
No Compare UI exists (proven by fake test F): `createZoomableImageEl` /
`createImagePreviewOverlay` untouched, no `studio-image-compare.js`, no compare
buttons, no compare selection state, no schema/backend changes.

Deploy/live/GPU/generation/commit/push/branch/worktree/reset/revert/stash/clean by
this batch: **NONE**.
