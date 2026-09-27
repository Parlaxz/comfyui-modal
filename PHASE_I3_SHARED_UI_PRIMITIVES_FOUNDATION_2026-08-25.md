# PHASE I3 — SHARED UI PRIMITIVES FOUNDATION — 2026-08-25

## Verdict

**I3 COMPLETE — PAGE LANES READY**

Phase I of ComfyModal Studio, shared-primitives foundation lane. Executed directly on the shared
dirty working tree (no reset/revert/stash/branch; no commit/push/deploy/Modal/GPU/live generation;
no subagents). I1 freeze honored with two documented drift corrections (§2 below).

---

## 1. Pre-change census (re-measured, not assumed)

`web/studio-ui.js` (pre-edit SHA256 `8C9F24953B4649F970FF526BE991E967406C4FC35A3F444CD51744906616063B`):

| Symbol | Line | Status |
|---|---|---|
| `el()` | 247 | live, 20 importing modules |
| `statusBadge()` | 277 | **LIVE** — 5 modules, 8 call sites (`studio-backend-workspaces.js:175`, `-snapshots.js:97,112`, `-credentials.js:103-104,130-131`, `-deployment.js:113`, `studio-workflows.js:197`). Kind vocabulary in the wild: `"ok"`, `"warn"`, `"error"`, `"neutral"` — nothing else. |
| `createZoomableImageEl()` | 302 | imported by playground only (I5-reserved) — UNTOUCHED |
| `createImagePreviewOverlay()` | 684 | same — UNTOUCHED |
| `renderEmptyState(listContent, detailPanel, context, state)` | 939 | **ZERO runtime callers**. Only consumer: re-export wrapper in `studio-backend.js:21`, itself never invoked (no module imports it). Baked copy: *"No backends configured via legacy discovery."* Python structural pin (`test_testing_shell_integration.py::test_render_empty_state_receives_state`) asserts on **studio-backend.js source**, not studio-ui.js — stays green untouched. |

Existing loading call sites confirmed present and untouched (full census in §10). Spinner CSS:
two behaviorally IDENTICAL keyframes existed — `@keyframes comfymodal-spin` (:2903, wizard) and
`@keyframes cm-exp-spin` (:3270, experiment cell), both `to { transform: rotate(360deg); }`.
Focus-visible: 38 existing rules, all outline-based (zero box-shadow rings) — verified before
adding the fallback. Accent token: `--color-accent: #5a7fdb` on `:root` in testing-styles.js:40.

## 2. I1 premise corrections (documented drift)

1. **No element carries a bare `comfymodal-studio` class.** All Studio classes are compound
   (`comfymodal-studio-modal`, `.comfymodal-studio-pagecontainer`, …). The literal frozen selector
   would match nothing. Resolution: the fallback ships THREE arms — the frozen literal scope,
   the real dialog root `.comfymodal-studio-modal`, and the shell page container
   `.comfymodal-studio-pagecontainer` (hosts every page surface in both production dialog and
   standalone fake harness). Current truth wins; frozen literal preserved verbatim as first arm.
2. **Duplicate spinner keyframe** (`cm-exp-spin`) was byte-identical to `comfymodal-spin`. Aliased
   `.cm-exp-cell-loading` onto `comfymodal-spin` and deleted the duplicate definition. Zero visual
   change anywhere; wizard declaration untouched (unit §9 asserts both).

Everything else in the I1 freeze held true as written.

## 3. Loading primitive — `web/studio-loading.js` (NEW)

Frozen API implemented exactly:

```js
renderLoadingState({ label = "Loading…", size = "page" | "inline", testid? }) → HTMLElement
```

- Root: `div.cm-loading`, `data-size="<page|inline>"`, `role="status"`, `aria-live="polite"`,
  optional `data-testid`. No global `aria-busy` — the element itself is the announced status.
- Children in order: decorative spinner (`span.cm-loading-spinner`, `aria-hidden="true"`) then
  visible label (`span.cm-loading-label`, exact caller text).
- Normalization (deterministic, never throws): missing/null/blank/non-string label → `"Loading…"`;
  unknown/non-string size → `"page"`; valid `"inline"` preserved; non-string testid ignored.
- Dependency-light: the module contains ZERO imports (direct DOM construction) so circular
  dependencies are structurally impossible. `studio-ui.js` was NOT restructured to share `el()`
  (explicitly out of scope).

Page/section migration count performed by I3: **ZERO** (by design; §10).

## 4. Shared spinner CSS result

ONE spinner animation source now exists. `.cm-loading-spinner` reuses the pre-existing wizard
keyframe `comfymodal-spin` (16px, 2px border, accent top, 0.8s linear infinite). The duplicate
`cm-exp-spin` keyframe was deleted; `.cm-exp-cell-loading` aliases `comfymodal-spin` with identical
behavior. Runtime proof: fake Test B asserts computed `animationName === "comfymodal-spin"` on a
mounted loader; fake Test C enumerates document stylesheets and asserts `comfymodal-spin` present /
`cm-exp-spin` absent. Wizard rule bytes unchanged (unit §9).

## 5. Chip taxonomy/base result

`.cm-chip` base owns geometry/typography ONLY: `inline-flex`, gap 4px, padding 2px 8px, radius
999px, border 1px, font 10px/600/1.5, letter-spacing, `white-space: nowrap`, vertical-align. The
base block contains no tone selectors (unit §10 enforces). Tone mechanism is `data-tone` with the
six frozen shared tones — `neutral`, `ok`, `warn`, `error`, `running`, `meta` — colored exclusively
from existing Studio tokens (`--color-success/warning/danger/accent*`, muted-text) with the house
literal fallbacks; no second color system invented. Frozen categories map: STATUS→tones directly;
INFORMATION/FILTER/CAPABILITY/RISK→tones at page-lane migration time; PORTABILITY_TARGET and
COMPATIBILITY additionally get family markers (§6).

## 6. Compatibility-vs-Portability distinction proof

Distinct family hooks shipped and proven three ways:

- `cm-chip--portability`: transparent fill, tone-colored text/border (preserves the Phase-G12
  outline-pill presentation), `box-shadow:none`.
- `cm-chip--compatibility`: filled toggle-family presentation — `background:
  var(--color-accent-muted)` + pointer cursor.
- Unit §12 asserts both selectors exist with divergent background declarations; fake Test C mounts
  both families at tone `ok` in the real browser and asserts **same** computed borderRadius (999px,
  shared geometry) but **different** computed backgroundColor (distinct semantics). They cannot
  collapse into one generic visual meaning.

## 7. statusBadge result (live shared primitive — migrated)

`statusBadge()` now emits `class="comfymodal-studio-status-badge <kind> cm-chip"` +
`data-tone="<kind>"`, with truthful mapping from actual source vocabulary: ok→ok, warn→warn,
error→error, everything else (incl. `"neutral"`/unknown)→neutral. No fabricated aliases. Legacy
feature-specific classes AND their CSS blocks are fully preserved (uppercase/letter-spacing still
come from the legacy rules), satisfying the structural pins (`"status-badge"` in studio-ui.js;
testing-styles retirement pin untouched). Net visual delta on the 8 live badge sites: pill radius
and inline-flex geometry from the shared base — explicitly sanctioned by §23 ("possibly statusBadge
geometry"). Its page CALLERS were not edited (§8 respected).

## 8. No mass chip migration — proof

Zero edits to any page module. Unit §20 asserts verbatim survival of original chip-producing lines
(`wf-chip`, `models-page`, `history-v2-chip status-*`, etc.) and that no page module references
`studio-loading.js`/`renderLoadingState`. Git diff confirms no page/shell files touched by this lane.

## 9. Focus-visible result

Fallback added exactly per freeze (with §2 correction):

```css
.comfymodal-studio :is(button,[role="button"],[tabindex="0"],a):focus-visible,
.comfymodal-studio-modal :is(...):focus-visible,
.comfymodal-studio-pagecontainer :is(...):focus-visible {
  outline: 2px solid var(--color-accent, #5a7fdb);
  outline-offset: 2px;
}
```

Runtime keyboard proof over THREE previously weak families (fake Test A, real Studio, real Tab presses):

| Family | Control | Proven |
|---|---|---|
| Workflows tag-chip remove | `.comfymodal-studio-wf-chip .chip-x` ("Remove tag txt2img") in workflow DETAIL view | outline 2px visible |
| Model Library row control | `[data-testid="models-page"] a` ("source" link) | outline 2px visible |
| Carousel Clear/close | `.comfymodal-studio-carousel-btn` ("Clear") | outline 2px visible |

Pointer contract proven FIRST in the same test: mouse-clicking a nav control leaves computed
outline-style `none` — no permanent always-on ring. No bare `:focus` rule was introduced by I3 and
all pre-existing field `:focus` rules remain (unit §§14–16). Previously weak targets now visibly
gain focus without any markup change: workflow cards (`div[tabindex=0][role=button]`), portability
chips, backend inline action buttons, preset-wizard footer buttons, dependency rows, carousel
controls, chip remove buttons.

## 10. Double-ring audit result

Structurally impossible for outline-only systems: `outline` is a single cascaded property, so where
the fallback coexists with a specific rule exactly one outline renders. Every pre-existing focus
rule was inspected — ALL use `outline` (none use box-shadow rings). Runtime confirmation: focused
carousel Clear control computes `box-shadow: none` under keyboard focus (Test A assertion).
Specificity consequence (documented, not a regression): the fallback arm (0,3,0) outranks some
legacy specific rules like topnav/history-card/portability (≤0,2,1), so those controls' offset
normalizes 1px→2px under keyboard focus — same color, same width, single ring, no layout movement
(outlines never affect layout). Preview-overlay/zoom controls live outside all three roots
(body-appended overlays) and keep their own dedicated rules unchanged. I2's nav keyboard spec
(outline width 2px, style ≠ none) remains green inside the gate.

## 11. Empty-state primitive result

`renderEmptyState` rewritten in place to the generic frozen API:

```js
renderEmptyState({ title, detail = "", action = null, testid } = {}) → HTMLElement
```

- Root `div.cm-empty-state` + optional `data-testid`; title `div.cm-empty-state-title` (deliberately
  NOT a heading level — page owner owns hierarchy); optional detail `div.cm-empty-state-detail`;
  optional existing Node appended WITHOUT cloning into `div.cm-empty-state-action`.
- NO `role="alert"`, no `aria-live` — normal application state, not an announcement (asserted).
- Legacy domain copy is DEAD: *"No backends configured via legacy discovery."*, *"Use the Snapshots
  or Backend Presets tabs above."*, "No workflows", "No models" — absent from studio-ui.js (unit §17)
  and from runtime output (`bakedCopy:false`, Test B). Blank title/detail render nothing.
- Minimal shared CSS base added (`.cm-empty-state`, `-title`, `-detail`, `-action`) using existing
  spacing/muted-text conventions. No illustrations, no icons, no page-card redesign.
- **Deliberately staged**: zero production callers immediately after I3. This is planned downstream
  consumption by I4/I6/I7/I8, NOT accidental dead code. The stale doc comment claiming backward
  compatibility was removed; the studio-backend.js pass-through wrapper (never invoked, pinned by
  its own Python source test) was left untouched since that file is not I3-owned.

## 12. Page-call-site NON-migration proof (ZERO by design)

Unit §20 pins eleven verbatim loading lines across nine page modules (workflows ×2, model-library,
history-v2 ×3 views, backend presets/snapshots/workspaces, playground ×2) plus absence of
`renderLoadingState`/`studio-loading.js` references in ten page modules. Git hunk proof below.

## 13. Files modified by THIS lane only

Production:
- `web/studio-loading.js` (NEW, 55 lines)
- `web/studio-ui.js` — 3 hunks: header comment, statusBadge region (~277), renderEmptyState (~939)
- `web/studio-styles.js` — 2 hunks: spinner dedupe (@@ -3296,11 +3264,7) and the labelled appended
  I3 shared region after the I2 additions (@@ -5902,6 +5895,306 tail)

Tests:
- `tests/run_studio_tests.py` — registration entry only (NODE_UNIT_FILES)
- `tests/studio_phase_i3_shared_primitives_unit.mjs` (NEW)
- `tests/browser/fake/studio-fake-phase-i3-shared-primitives.spec.mjs` (NEW)

Pre-edit hashes recorded before editing: studio-ui.js
`8C9F2495…6616063B`, studio-styles.js `655870FA…34D0613`. I2's prior hunks in studio-styles.js
(@1524/@2119/@3785/@5899+161) were neither reordered nor reformatted; no unrelated CSS normalized.
Image-viewer helpers: zero hunks between them; defining markers byte-intact (unit §19). Shell,
modal-testing, and all page modules untouched. `i1-audit.spec.mjs` unregistered/untouched; I3
coverage uses the required `studio-fake-*` filename (matches `testMatch`).

## 14. I2 regression result

- `studio_phase_i2_shell_nav_accessibility_unit.mjs`: PASS (run standalone + inside gate).
- `studio-fake-phase-i2-shell-nav-accessibility.spec.mjs` (5 tests): PASS inside the full fake lane.
- Semantic nav, sole aria-current, keyboard traversal, shell h1, dialog Escape/focus-restore/inert,
  responsive valve — all green. Visual snapshots (playground idle/running, history grid,
  experiment grid) passed unchanged inside the lane run → no gross CSS shift on Playground/History/
  Experiments; Backend/Settings show no diff sources (their pages consume nothing new except the
  migrated statusBadge pill geometry, sanctioned).

## 15. Node test result

`tests/studio_phase_i3_shared_primitives_unit.mjs` — **21 sections, all PASS**, exercising REAL
modules under the house DOM stub: loading default/semantics/spinner/labels/sizes/testid/malformed-
options/no-imports (§1–8); one-spinner-source (§9); chip base/tones/family-guards/statusBadge (§10–13);
focus fallback/no-broad-:focus/specific-rules-retained (§14–16); generic empty state + CSS (§17–18);
scope guards: image-viewer intact, zero page migrations, no routing/BroadcastChannel/Compare (§19–21).

## 16. Fake runtime result (focused)

`npx playwright test --config=playwright.fake.config.mjs -g "I3 shared UI primitives"` →
**3 passed** (stable across repeated runs, fastest 7.8s):

- A. keyboard fallback over 3 weak families + pointer-no-ring + single-ring audit
- B. primitive DOM semantics from real modules (loading role/live/spinner-hidden/label-visible,
  animationName resolution, normalization table, copy-free empty state w/ action identity, badge
  shared geometry: radius 999px / inline-flex / 10px)
- C. family separation at identical tone + runtime keyframe census (one spin keyframe)

## 17. Exact test-count ledger

| Lane | Before I3 | After I3 | Delta |
|---|---|---|---|
| Python (`run_studio_tests.py`) | 2124 / 2124 | **2124 run, 0 fail, 0 error, 0 skip** | 0 |
| Node units (files) | 26 | **27** | +1 (I3 unit registered) |
| Fake Playwright (tests) | 216 exact | **219 passed** | +3 (exactly the 3 new I3 tests) |

Arithmetic reconciles exactly: 216 + 3 = 219; node 26 + 1 = 27; python unchanged. The known
lifecycle test-11 timing flake did NOT appear (single clean full-gate run; no assertions or
timeouts weakened). Full gate command: `python tests/run_studio_tests.py --fake` →
`ALL STUDIO LANES GREEN`.

## 18. Downstream migration census (handoff for parallel I4/I6/I7/I8)

### I4 — History
- Loading sites (4 DOM): `studio-history-v2.js:380` (grid), `:627` (secondary state);
  `studio-history-v2-detail.js:1133-1136` (`_renderLoading`); `studio-history-v2-experiment.js:220`.
  (Button-label only, not a primitive site: `studio-history-v2.js:437` "Load more".)
- Chip families: `comfymodal-studio-history-v2-chip status-*` at `studio-history-v2.js:127`,
  `-experiment.js:70`, `-detail.js:80`, `studio-experiment-mode.js:1468`.
- Empty-state helpers: `history-v2-cell-empty` (:4542 CSS; usage `-experiment.js:204`),
  `history-v2-cover-empty` (`studio-history-v2.js:571`), `history-v2-output-thumb-empty`
  (`-detail.js:415`).
- Weak-focus residue: none structurally — fallback covers; lane may add semantic refinements only.

### I6 — Workflows / Models / Portability
- Loading sites (3 DOM): `studio-workflows.js:750,1533`; `studio-model-library.js:219`.
  Secondary inline texts: `studio-workflows.js:1713` ("Loading selected version…"),
  `:2141` ("Loading mapping candidates…").
- Chip families: `wf-chip` (`studio-workflows.js:203,1606,2360`; `studio-model-library.js:732,739`);
  `model-badge` (`studio-model-library.js:85`); `portability-chip`
  (`studio-workflows.js:536,575` + raw `studio-portability.js:251`).
- Empty-state helpers: `comfymodal-studio-workflows-empty` (`studio-workflows.js:473,752`),
  `comfymodal-studio-models-empty` (`studio-model-library.js:221,223`).
- Weak-focus residue: none structurally — workflow cards, chip-x, portability chips, dependency
  rows all ringed by fallback now.

### I7 — Backend / Settings
- Loading sites (3 DOM): `studio-backend-presets.js:42`; `studio-backend-snapshots.js:38`;
  `studio-backend-workspaces.js:50`. Settings: none (static page).
- Status/info chips: all 8 `statusBadge()` call sites already emit the shared base automatically;
  `feature-chip` (`studio-backend.js:83`) is the compatibility-family candidate for
  `cm-chip--compatibility`; dead `renderEmptyState` wrapper in `studio-backend.js` may be deleted
  by this lane if desired (it owns the file).
- Empty-state helpers: none active (legacy renderer already dead).
- Weak-focus residue: none structurally — inline deployment/workspace action buttons now ringed.

### I8 — Playground
- Loading sites (5): `studio-playground.js:692` (capabilities), `:1170` (backends option — carries
  pre-existing mojibake "Loading backendsâ¦", wording fix belongs to this lane per §17 boundary),
  `:1381` (workflow status text), `:1396` (version option), `:4133` (recent runs).
- Chip families: `timing-tag` (`studio-playground.js:3847`), carousel item meta badges,
  experiment-mode cell badges (`studio-experiment-mode.js`).
- Empty-state helpers: `comfymodal-studio-empty-state` at `studio-playground.js:1192,1667,4123,4132,4162`
  and `studio-experiment-mode.js:158,279,346` — richest convergence target.
- Weak-focus residue: none structurally — carousel controls and wizard footer buttons now ringed.

Shared-region rule for all four lanes: consume `.cm-loading` / `.cm-chip[data-tone]` /
`.cm-empty-state*` as-is; do not redefine shared primitives in page CSS; `studio-image-compare.js`
remains I5-only.

## 19. Next dependency verdict

The I1/I2 contracts hold, the primitives exist with permanent Node + fake coverage, the full
deterministic gate is green with exact arithmetic, and every page lane can now migrate call sites
in parallel without touching shared files. **PAGE LANES READY.**

Deploy/live/GPU/commit/push: **NONE**.
