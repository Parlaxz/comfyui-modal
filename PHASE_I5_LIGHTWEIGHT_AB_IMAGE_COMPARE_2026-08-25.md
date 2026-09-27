# PHASE I5 — LIGHTWEIGHT A/B IMAGE COMPARE — 2026-08-25

## Verdict

## `I5 COMPLETE`

Executed directly in the shared working tree during the parallel I5 ∥ I9 window
(no subagents; no reset/revert/stash/branch/worktree; no commit/push/deploy/
Modal/GPU/live generation). The retired Comparison product stays retired: what
shipped is a client-only, transient comparison of EXACTLY TWO existing images.

---

## 1. Viewer-helper re-measurement (pre-edit, not assumed)

`web/studio-ui.js`:

| Helper | Current callers (re-traced) |
|---|---|
| `createZoomableImageEl` (:310) | imported by `studio-playground.js:54`, **invoked nowhere**. Registers layer 4 (zoom Escape/Numpad±), pointer pan when zoomed, wheel zoom, fullscreen, Ctrl +/− /0/R/F keyboard on a tabindex=0 image container. |
| `createImagePreviewOverlay` (:692) | same orphaned import only. role="dialog" aria-modal backdrop-click close, close/Save/Download toolbar below the image, optional sections/sideColumn, optional focus trap, **layer 3** Escape. Doc comment claimed "used by both experiment cell detail and history preview" — STALE (I1 finding reconfirmed). |
| Focus handling | overlay has an opt-in `focusTrap`; no focus-in on open; no invoker capture/restore (dead code never exercised it live). |

Stale-comment fix: the "used by both …" claim and the "(Phase I5 reserved)"
marker were replaced with a truthful region note (no production caller;
retained for the existing playground import; evaluated as compare host and
deliberately not used there). Byte-markers pinned by tests remain intact
(unit §14).

**Host decision (documented evidence):** both helpers are built around ONE
zoomable image whose pan/zoom transform would have to be kept pixel-aligned
across two independently clipped layers — their single-image architecture
does not model that. The compare therefore reuses only the generic
primitives (`el()`, `registerLayerHandler`) and keeps a smaller aligned
two-image stage. No dead code was preserved as a "foundation": the helpers
stay solely because deleting them breaks the existing playground import
(playground is not I5-owned).

## 2. Compare-session model (`web/studio-image-compare.js`, NEW)

Pure model (DOM-free, Node-tested):

```
normalizeImageDescriptor(input) → {url,label,kind,meta,alt} | null   (fail-soft)
clampPercent(v) → int 0..100 | null
shortIdTail(id) → "#abcdef"
createCompareSessionModel({normalize?, onChange?}) → {
  getState(): {a,b,position}      position defaults 50
  setA(input)                     selects A; an explicit new A discards any
                                  previous pairing (fresh pair, never mixed)
  setB(input)                     fills B; a further eligible pick REPLACES B
  setPosition(v) / nudgePosition(±delta)   clamped 0–100, integer
  reset()                         clears A+B, restores position 50
}
```

Descriptors carry ONLY client-side presentation data (URL, human label,
optional display id tail, optional alt) — never mutable History records or
backend models (unit §10 shape pin).

Singleton session + tray + view live in the same module. Public entry API:
`startCompare / addToCompareB / openComparePair / clearCompareSession /
buildAddToCompareItem / openCompareView / getCompareState / isCompareActive`.

## 3. Transient-state proof

- Exactly two slots (A/B), module memory only.
- **No persistence surface exists**: unit §12 pins the module free of
  `localStorage`, `sessionStorage`, `indexedDB`, `XMLHttpRequest`, `fetch(`,
  history.pushState/replaceState, POST/PATCH vocabulary, repo imports, and
  any `/comparison/` string. The module's sole import is
  `el/registerLayerHandler` from `./studio-ui.js`.
- Session lifecycle is anchored to the LIVE History page root
  (`[data-testid="history-v2-page"]`). A MutationObserver tears the session
  down the moment the anchor disconnects — i.e. changing away from the
  History/Experiment product context clears it. Within History it survives:
  generation-detail open/close AND feed↔experiment sub-page swaps (both swap
  root CHILDREN; shell page switches remove the whole root).
- Closing the view ALWAYS clears the session (Escape contract); the tray's
  Clear button ends it explicitly. Nothing survives reload.

## 4. Generation-detail entry (`studio-history-v2-detail.js`)

In the Preview slot action area (beside Download/Export, all preserved):

- `Compare` (testid `history-v2-compare`) — rendered ONLY when the displayed
  managed asset has a usable URL; preselects it as A and activates the tray.
- `Compare with Original` (testid `history-v2-compare-original`) — rendered
  only when a usable Original URL is ALREADY projected on the record
  (`originalUrl && !originalFailed`); one click opens Preview↔Original
  directly. Original bytes are fetched only by this explicit click (same
  class as View Original) — never eagerly to populate comparison.
- Per-output ⋯ menu gains `Add to compare (B)` while a session is active
  (eligible = output projects a thumb/preview URL; non-image outputs expose
  nothing).

## 5. Experiment-cell entries (`studio-history-v2-experiment.js`)

- Cell detail pane: `Compare` (testid `history-v2-cell-detail-compare-{key}`)
  when the cell displays a usable image (label = axis label, meta =
  experiment name · generation tail), plus `Add to compare (B)` row item
  while a session is active.
- Cell tile ⋯ menu: same Add-to-compare item.
- No scheduler mutation, no Experiment authority change, NO Experiment-
  specific compare store (unit §13 pins the module instantiates no second
  model). Cross-surface pairs work through the one shared transient session:
  cell↔cell, cell↔History generation, generation↔generation.

## 6. B-selection / replacement semantics

Second pick fills B; further picks truthfully REPLACE B with a visible
`Replaces B` pill inside the menu item (rendered whenever B already exists).
A remains stable until an explicit new Compare (fresh pair) or Clear/reset.
Runtime-proven in fake test E (A label unchanged across replacement; view
title shows the new pair).

## 7. Slider keyboard/pointer — one authority

`role="slider"` handle: aria-label naming both sides, valuemin 0, valuemax
100, valuenow, valuetext `"N% <B label>"`. Keyboard: ArrowLeft/Right ±5,
Home 0, End 100, clamped, preventDefault'd. Pointer: click-to-position
anywhere on the stage plus drag with pointer capture. ALL paths mutate the
single model position and repaint through ONE `_paint()` (aria attrs, clip
geometry, divider and handle can never diverge — fake D pins
`divider.style.left === aria-valuenow + "%"`. Arrows are also claimed at the
shared layer registry (newest layer-3 handler wins over the detail overlay's
older layer-3 entry) so no other surface can steal them while the slider is
focused.

## 8. Responsive result

≤640px (matchMedia-driven `data-mode="stacked"`): true stacked halves — A
fits the top region, B the bottom region, horizontal divider boundary;
labels stay in opposite corners; slider becomes ns-resize. Desktop: overlay
mode, vertical clip divider. Fake G sweeps 768 (overlay) / 480 / 360
(stacked): zero document horizontal overflow at every width, both labels
visible, Home/End operable, clean Escape teardown per width. Visual baseline
captured at 480px.

## 9. Image-failure result

Fake J: B pointing at an unregistered asset id renders the truthful
`Image unavailable` note for that side; labels remain visible; nothing is
silently substituted; slider stays operable; overlay closes cleanly (404
allowlisted as the expected resource noise). Entry-side truthfulness: no
usable image ⇒ NO Compare control at all (fake A on `gen_no_image`).

## 10. Focus / Escape result

Open: focus lands on the slider handle (fallback Close). Escape/backdrop/×:
view removed → session cleared → tray removed → focus restored via stable
re-resolution (opener if still connected, else origin invoker by
testid[+data-id], I4-analog). Fake F proves: Escape → overlay gone, tray
gone, `activeElement` = the detail's `history-v2-compare` button inside the
still-valid Generation detail, whose own Escape continues to work afterwards
(I4's focus contract not regressed — I4 spec D still green).

## 11. Preview / Original invariant proof (Phase F)

Preview, Original and Current output are never conflated: descriptors carry
explicit kind/label ("Preview", "Thumbnail", "Original", "Output N"); the
pair action renders only from ALREADY-projected record URLs; View Original/
Download Original/Export actions are untouched (`src: feat.originalUrl`
click-handler ordering pins still pass — presentation unit §17–23 green);
compare causes exactly one Original GET under the user's explicit pair
click, identical in class to the existing View Original action. All 57
Original/replay/experiment/history suites re-ran green post-change.

## 12. Zero-write network proof

Fake H attaches a request collector AFTER the detail fetch settles, then
performs the full compare interaction set (open session, add B, open view,
pointer click, keyboard nudges, Escape). Result: zero non-GET requests;
every request is a normal `/comfymodal/history-v2/assets/` image GET (the
harness's own pre-existing `__comfymodal_test/events` poll excluded);
nothing matches `/comparison/`. Opening and manipulating Compare writes
NOTHING anywhere.

## 13. Retirement guard

Node unit §12: the new module contains no `/comparison/`,
`ComparisonProfile`, `ComparisonRunner`, `ab-slider` strings. Runtime fake I:
feed body text lacks "Comparison Profiles"/"Comparison Runner"/"/comparison/run",
zero comparison-profile/-runner/ab-slider DOM nodes, dynamic import of the
retired `testing-dashboard/ab-slider.js` path rejects. I4's former
absence-pin (spec F) was re-pointed to this retirement contract (documented
drift — the sanctioned Compare entry now exists exactly once per detail).

## 14. Focused Node result (unregistered, §16 discipline)

`tests/studio_phase_i5_image_compare_unit.mjs` (standalone, NOT registered):
**14 sections PASS** — initial empty · select A · fill B · third-pick
replace-B · new-A resets pair · reset clears · default 50 · coercion/clamp/
rounding · ±5 nudges incl. boundary clamp · Home/End · fail-soft garbage
inputs · descriptor normalization/caps · onChange contract · structural
persistence/backend/retirement bans · entry-wiring pins · viewer byte-marker
pins. `tests/run_studio_tests.py` NOT edited; registered Node files stay 27.
A later convergence lane may register it.

## 15. Test-count ledger

| Lane | Before I5 | After I5 | I5-owned delta |
|---|---|---|---|
| Python | 2133/2133 | **2133 run, 0 fail/error/skip** (gate) | 0 |
| Registered Node files | 27 | **27** (runner untouched) | 0 (+1 standalone unregistered) |
| Fake Playwright (collected) | 246 exact | **268 collected** (`--list`: "268 tests in 32 files") | **+12 = exactly the I5 specs** (10 functional + 2 visual) |

Arithmetic reconciles exactly: 246 + 12 (I5) + 10 (I9's concurrent
`studio-fake-phase-i9-routing.spec.mjs`) = 268. I9's additions are NOT
claimed here.

### Observed shared gate (during the parallel window)

```
python tests/run_studio_tests.py --fake
  python             run=2133  fail=0  error=0  skip=0
  node-unit          run=27    fail=0  error=0  skip=0
  fake-playwright    247 passed / 20 failed (268 collected)
```

The 20 failures are ALL in concurrently-owned execution surfaces
(`studio-fake-workflow-run.spec.mjs` ×16, `studio-fake-playground.spec.mjs`
×2, `studio-fake-phase-i8-playground-polish.spec.mjs` ×1,
`studio-fake-persistence.spec.mjs` ×1 — e.g. `canvas-output` never renders
after reload). Mechanical isolation evidence that they are NOT I5-caused:

- Import-graph check: no playground/workflow-run/run-model module references
  `studio-image-compare` / `-detail` / `-experiment`.
- My lane's `studio-ui.js` delta is comment-only; my `studio-styles.js`
  delta is a pure appended region (diff shows zero deleted CSS lines).
- The failing cluster exercises run-execution/DOM-render paths in files with
  same-evening sibling modifications (`modal-testing.js` 22:15, 
  `studio-shell.js` 22:46 — I9 ownership; workflow-run/playground churn from
  other batches), none of which this lane touched.

Everything this lane owns — plus the entire History/I2/I3/I4 regression
surface — is green inside the same gate runs.

## 16. Regression results (§19)

- I4 permanent spec: 6/6 PASS (incl. re-pointed F retirement guard).
- History V2 sweep + experiments + annotations/download/export +
  cancel-menu/resume-retry + recent-runs + phase-e original/replay/wave2 +
  modern-experiment-ui: **115 focused fake tests PASS** post-change.
- I3 primitives spec + I2 nav spec: 8/8 PASS.
- Python history/H15 suites: green inside the gate (python lane 0 fail).
- Node owners (presentation §17–23, persisted-status, experiment, grid,
  E4C/E4D, F6, download, I2, I3 units): green inside node-unit 27/27.
- Existing visual baselines: no unrelated regeneration (only the two NEW
  I5 snapshots added; history-grid/playground/experiment baselines passed
  unchanged in gate runs).

## 17. Files modified by THIS lane

Production:
- `web/studio-image-compare.js` (NEW — model + tray + view)
- `web/studio-history-v2-detail.js` (Compare / Compare-with-Original /
  per-output Add-to-compare entries)
- `web/studio-history-v2-experiment.js` (cell pane + cell-menu entries)
- `web/studio-ui.js` (image-viewer region: stale comments truthed only)
- `web/studio-styles.js` (labelled Phase I5 compare/viewer region, appended)

Tests:
- `tests/browser/fake/studio-fake-phase-i5-image-compare.spec.mjs` (NEW, 10)
- `tests/browser/fake/studio-fake-phase-i5-image-compare-visual.spec.mjs`
  (NEW, 2) + its two snapshot baselines
- `tests/browser/fake/studio-fake-phase-i4-history-polish.spec.mjs`
  (test F re-pointed absence→retirement guard, documented drift)
- `tests/studio_phase_i5_image_compare_unit.mjs` (NEW, standalone/unregistered)

Not touched: `studio-shell.js`, `modal-testing.js`, `history-v2-view-state.js`,
playground/workflows/models/backend/settings files, backend/server/Python,
`tests/run_studio_tests.py`.

## 18. Remaining I5 debt

**ZERO.**

Deploy/live/GPU/generation/commit/push/branch/worktree/reset/revert/stash/
clean by this batch: **NONE**.
