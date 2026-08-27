# PHASE I8 — PLAYGROUND ACCESSIBILITY, LOADING, EMPTY-STATE & COPY POLISH — 2026-08-25

## Verdict

## `I8 COMPLETE`

Playground lane of Phase I, executed directly on the shared dirty working tree (no
reset/revert/stash/branch/worktree; no commit/push/deploy/Modal/GPU/live generation;
no subagents). I8 ran in parallel with I4/I6/I7; only I8-owned files were written
(`web/studio-playground.js`, `web/studio-experiment-mode.js`; `studio-playground-state.js`
and `studio-playground-run.js` required **zero** changes). No execution-architecture,
backend, or transport change of any kind.

---

## 1. Re-measurement (I3 census verified against current truth)

| I3 handoff item | Verified |
|---|---|
| Loading sites (5) | capabilities `renderControlPanel`; backends `<option>` (mojibake); workflow gating line; workflow `<option>`; recent runs — all confirmed present |
| Chip families | `timing-tag` (metadata timing card); carousel EXP badge; experiment cell chip `history-v2-chip status-*` (`studio-experiment-mode.js`, the fourth I3-listed site — the other three were migrated by I4) |
| Empty states | `comfymodal-studio-empty-state` ×5 in playground (:1192 backend-empty, :1667 handoff error, :4123 cleared, :4132 loading, :4162 no-runs-yet) + ×3 in experiment-mode (:158 presets empty, :279 catch error, :346 matrix hint) — richest set confirmed |
| I1 findings | no Playground h2 ✓; mojibake ellipsis ×2 ✓; carousel duplicate accessible names ✓; "Go to Backend tab…" wording ✓ |

Additional re-measurement finding beyond the I1 pair: four more USER-FACING strings carried
double-encoded em-dashes (`â€"`): the file-selection notice (`title:` + `text:`), the
schema-options tooltip, and the canvas "Not Implemented" placeholder. Treated as genuine
mojibake under the §4 mandate (user-visible defects); see §4.

## 2. Page heading

`renderPlayground` now renders a truthful visually-hidden `<h2 data-testid="playground-page-title">Playground</h2>`
as first child of the page root, using the same local clip pattern as the I4 History heading
(`position:absolute;width:1px;height:1px;margin:-1px;padding:0;border:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap`
— never display:none). Shell h1 untouched; no card/run label promoted to a heading (zero new h3).

## 3. Loading migration census — 2 migrated / 3 retained

Migrated to `renderLoadingState({ size: "inline", testid })`:

| Site | Call |
|---|---|
| Preset-capabilities section container | `{ label: "Loading preset capabilities…", testid: "playground-capabilities-loading" }` — legal section DOM container, fully replaced when capabilities resolve |
| Recent-runs filmstrip loading branch | `{ label: "Loading recent runs…", testid: "playground-recent-runs-loading" }` — this site previously MISUSED the empty-state class; now correctly a loading state |

Retained as textual control states (intentional per freeze):

| Site | Why retained |
|---|---|
| `<option>Loading backends…</option>` | control-specific placeholder inside `<select>`; never put a div primitive inside a select |
| Workflow gating line `"Loading…"/"Loading workflow…"` | single imperative-updated status NOTE that also renders non-loading states ("Ready to run", reasons); `_syncWorkflowGating` writes `textContent` directly — not a section container |
| `<option>Loading…</option>` (workflow selector) | control state inside `<select>` (already real `\u2026`) |

## 4. Mojibake fixes — 6 user-facing strings

All replacements are exact-string, count-verified (each needle asserted present exactly once
before replace):

| Fixed string (now real Unicode) | Location |
|---|---|
| `Select a backend…` | backend selector placeholder option (frozen) |
| `Loading backends…` | backend selector loading option (frozen) |
| `File selection is out of scope — the current value comes from the preset/graph.` | control title attr |
| `File selection is out of scope — value preserved from preset/graph.` | control body text |
| `Schema options unavailable — value preserved from saved defaults` | schema-option tooltip |
| `${currentSpec.label} — Not Implemented` | canvas honest-placeholder headline |

Source-pinned: the double-encoded ellipsis byte sequence `\u00e2\u20ac\u00a6` is now absent
from the entire file. Deliberately NOT rewritten: ~40 COMMENT occurrences of double-encoded
em-dashes/box-drawing rules elsewhere in the file (pre-existing dirty-tree encoding state,
non-rendering). Fixing those would be exactly the broad Unicode rewriting the freeze
prohibits; they are recorded as cosmetic source hygiene, not product debt.
`studio-experiment-mode.js`, `-state.js`, `-run.js`: no mojibake found, none introduced.

## 5. Backend copy

Frozen wording applied: `Go to Backend tab to create presets` → **`Open Backend to create presets`**
(controls prompt link, `studio-playground.js`). The identical assembled phrase in the
experiment-mode Compare-Presets empty state received the same fix (`Open Backend to create
presets.`), since it composes the exact frozen sentence inside an I8-owned file. Navigation
behavior unchanged (both still call `navigateToBackendTab`); Backend/Runtime Preset naming
untouched. Retained deliberately: the backend-selector variant "Go to Backend tab to add
backends." — different sentence, not in the frozen list; flagged for a later convergence pass
if desired.

## 6. Recent-run accessible names

New `_carouselAccessibleNames()` builds one name per filmstrip button from stable context:

```
Preset A, completed at 2:31 PM. Open run.
Seed Sweep, running at 2:35 PM. Open experiment.
Preset A, completed at 2:31 PM (#b12cdf). Open run.   ← short id ONLY on collision
```

- Base = `presetLabel || presetId || featureId || "Run"` (existing display-label chain preserved),
  truthful status, wall-clock completion/start time (`_formatRunClock`, local h:mm AM/PM).
- Run type in the call to action: `Open run.` / `Open experiment.` / truthful `No image.`
- Short id tail (last 6 alphanumerics of experimentId/runId/id) appended **only** when another
  visible item produces the identical base name; long ids never dumped.
- Old generic `" - Click to view"` text removed everywhere. Visual presentation unchanged
  (title attr, thumbnails, status dots identical).

## 7. Chip/meta migration

| Family | Change | Tone |
|---|---|---|
| `comfymodal-studio-timing-tag` | + `cm-chip` + `data-tone="meta"` (legacy class preserved for page CSS) | meta (informational) |
| `comfymodal-studio-carousel-exp-badge` | + `cm-chip` + `data-tone="meta"`; stays `aria-hidden` decoration (accessible name carries experiment identity); identity badge reads as informational, never error/status | meta |
| Experiment cell chip (`studio-experiment-mode.js`) | + `cm-chip` + truthful `data-tone` via `_cellStatusTone()`: completed→ok, completed_with_failures/interrupted→warn, failed→error, running/queued/pending→running, unknown→neutral (identical mapping table to I4's history chips); legacy `status-*` class + `::before` dot preserved | truthful status tones |

Shared-region rule respected: consumed `.cm-chip[data-tone]` / `.cm-loading` / `.cm-empty-state*`
as-is; no shared CSS defined or edited; `studio-styles.js`, `studio-ui.js`, `studio-loading.js`
untouched. Carousel colored status DOT and reveal-bar left as-is (not chip families).

Sanctioned visual delta: chip geometry (pill radius/border/padding/typography) now comes from
the shared base on the three families above; the three Playground visual baselines were
regenerated accordingly (§11).

## 8. Empty-state migration — 5 migrated / 3+1 retained

Migrated to `renderEmptyState({ title, detail?, action?, testid })` (all copy caller-supplied;
no alert/live semantics):

| Site | testid |
|---|---|
| Backend selector "No backends configured." + action link | `playground-backend-empty` (cleanup marker class `comfymodal-studio-backend-empty-msg` preserved) |
| Cleared recent runs ("Recent runs cleared." / "Submit a new run to see results here.") | `playground-recent-runs-cleared` |
| Fresh no-runs-yet ("Recent runs will appear here once you use the Playground.") | `playground-recent-runs-empty` (Python source pin string kept verbatim) |
| Experiment Compare-Presets "No presets configured." + action link | `experiment-presets-empty` |
| Matrix Summary axis hint ("Check boxes next to controls …") | `experiment-matrix-empty` |

Deliberately NOT migrated (not "empty"):

| Site | Reason |
|---|---|
| Workflow handoff error (`studio-playground.js`) | execution/validation ERROR — keeps legacy class; exactly one `comfymodal-studio-empty-state` use remains in the file (source-pinned) |
| `catch` → "Could not load presets." (experiment-mode) | fetch-failure ERROR — legacy class retained (source-pinned count = 1) |
| Cell tile "Queued"/"No image" mini-placeholder | too small; section-level primitive would break tile layout (same precedent as I4's thumb placeholders) |
| Canvas "Generated output will appear here." | tiny inline hint inside fixed canvas region; not in the I3 census; layout-sensitive |

The recent-runs LOADING pseudo-empty was converted to the loading primitive instead (§3) —
loading is not empty.

## 9. Experiment-mode guards (Phase H authority preserved)

Zero behavioral change: `experimentRunSurface()` still modern-only; no legacy creator fallback,
no Comparison/V1 surface; concurrency-6 semantics, V2 creator route (`/studio/experiment-v2`),
resume/retry identities, History-V2 durable results, draft persistence keys — all untouched
(diff limited to the two empty-state constructions, one import, and the cell-chip class/tone).
E2E test F re-proves V2-only submission and toned cell chips at runtime.

## 10. Single-execution guards preserved

`POST /studio/run`, accepted immutable ExecutionPlan flow, `getStudioRunStatus` /
`stopExperiment` seams, scoped progress-tracker ownership, fresh direct-run run-history
compatibility actions, polling lifecycle — byte-identical (no hunks in any execution path;
only DOM construction, copy strings, aria attributes changed). E2E test E re-proves the V2
single-run seam end-to-end (exactly one `POST /studio/run`, canvas output renders, terminal
"Run completed").

## 11. Test-count ledger

Own additions (exact):

| Item | Delta |
|---|---|
| NEW spec `tests/browser/fake/studio-fake-phase-i8-playground-polish.spec.mjs` | **+6 fake tests** (A h2/copy/mojibake · B held-route loading semantics · C unique names + meta-chip geometry · D cleared empty primitive · E V2 single-run seam · F experiment matrix-empty + V2-only creator + toned cell chips) |
| Extended registered unit `tests/studio_playground_run_unit.mjs` (new §20 source-contract block; no runner edit) | +1 section, 0 files |
| Updated `tests/studio_phase_i3_shared_primitives_unit.mjs` §20 staged guard | retired the two Playground verbatim pins + no-reference entry (documented drift; same precedent as I4/I6/I7 updates in that file) |
| Regenerated visual baselines | `playground-idle`, `playground-running`, `playground-filmstrip` (sole delta: sanctioned chip geometry on EXP badge / timing tags; history-grid untouched) |

Observed shared gate (tree includes concurrent sibling work):

```
python tests/run_studio_tests.py --fake
  python             run=2133  fail=0  error=0  skip=0     (2124 baseline + 9 sibling-added Python tests; I8 added 0)
  node-unit          run=27    fail=0  error=0  skip=0     (27 files; I8 file delta 0)
  fake-playwright    PASS        → ALL STUDIO LANES GREEN

npx playwright test --config=playwright.fake.config.mjs --reporter=line
  246 passed / 246   (direct exact count)
```

Attribution: fake total moved 225 → 246 during the parallel window; I8 claims exactly its +6
(the I8 spec). Remaining +15 are sibling-lane specs (I6/I7) landing concurrently; their two
transient mid-flight failures observed in one intermediate gate run passed in the final green
run and are not attributable to I8 (different owned surfaces).

Focused results: I8 spec 6/6 (stable across repeated runs); `node tests/studio_playground_run_unit.mjs`
20 sections PASS standalone; `node --check` clean on both modified production files.

## 12. Files modified by THIS lane only

Production:
- `web/studio-playground.js`
- `web/studio-experiment-mode.js`
- `web/studio-playground-state.js`, `web/studio-playground-run.js` — **untouched (no change needed)**

Tests:
- `tests/browser/fake/studio-fake-phase-i8-playground-polish.spec.mjs` (NEW)
- `tests/studio_playground_run_unit.mjs` (extended, §20)
- `tests/studio_phase_i3_shared_primitives_unit.mjs` (§20 stale staged-guard update only)
- `tests/browser/fake/studio-fake-visual.spec.mjs-snapshots/playground-{idle,running,filmstrip}-fake-chromium-win32.png` (regenerated baselines)

Not touched: `studio-ui.js`, `studio-styles.js`, `studio-loading.js`, shell/modal-testing,
History/Workflows/Models/Backend/Settings files, backend/API, `tests/run_studio_tests.py`.

## 13. Remaining Playground Phase-I debt

**ZERO polish debt against the I1 freeze**, except cross-cutting work reserved for other lanes:

1. **Late-response page-transition guard** (pre-existing, surfaced by I4): holding
   `/history-v2/feed` (or the hydration promise) across a Playground→History transition can let
   the late response re-render Playground over the active page. No gate test exercises it; it
   requires a current-page guard on `setPage`-driven re-renders — a navigation concern that
   belongs to the **I9 routing lane**, which owns page switching.
2. Non-rendering comment-level mojibake in `studio-playground.js` (encoding hygiene only; broad
   rewrite prohibited by this freeze).
3. "Go to Backend tab to add backends." variant wording (not in the frozen copy list; kept for
   minimal scope).

Deploy/live/GPU/generation/commit/push/branch/worktree/reset/revert/stash/clean by this
batch: **NONE**.
