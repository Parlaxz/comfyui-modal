# PHASE I7 — BACKEND & SETTINGS ACCESSIBILITY, LOADING AND COPY POLISH — 2026-08-25

**Verdict: I7 COMPLETE**

Executed directly on the CURRENT shared tree (no subagents). Parallel with I4/I6/I8 — all four
page lanes landed on the same tree; sibling additions are attributed separately in §10.
No deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert /
stash / clean. No server edits. `tests/run_studio_tests.py` NOT edited.

---

## 1. Pre-page re-measurement (all confirmed on the shared tree before editing)

| Item | Measured state |
|---|---|
| Backend loading sites | exactly three DOM sites: `studio-backend-presets.js` (`listContent.textContent = "Loading presets..."`), `studio-backend-snapshots.js` (`"Loading snapshots..."`), `studio-backend-workspaces.js` (`activeLine` plain text `"Loading workspaces…"` replaced by `renderActiveLine`) |
| `statusBadge()` sites | workspaces :175, snapshots :97/:112, credentials ×3, deployment :113 — all already emit `cm-chip` + `data-tone` via the I3-migrated primitive (zero page-side work needed; runtime-verified in fake test F) |
| Settings | no page h2; reset controls share the bare accessible name "Reset section" ×5 (Generation/Outputs/History/Interface/Advanced); frozen wording rows at :403/:461/:471; zero loading sites (static page) |
| Backend headings | NONE (I1 §3.3 table held); card/section titles are styled divs/h3/h4 |
| Backend tabs | six native `<button>`s (Overview/Workspaces/Deployment/Credentials/Backend Presets/Snapshots), `.active` class only — selection invisible to AT; no tablist keyboard model exists |
| Dead wrapper | `studio-backend.js renderEmptyState(listContent, detailPanel, context, state)` re-export: re-measured ZERO importers (only definition + `_renderEmptyState` import inside the glue file itself; grep over repo confirms no module imports it) |

---

## 2. Page h2s

- **Backend**: truthful `h2` "Backend", `data-testid="backend-page-title"`, first child of the page container; visually hidden with the local clip offscreen pattern (same pattern as I4 History) — never `display:none` / `visibility:hidden`. No card title was promoted into a heading (Overview view census = exactly one heading, the h2).
- **Settings**: truthful `h2` "Settings", `data-testid="settings-page-title"`, first child of the settings container, same clip pattern. Frozen hierarchy preserved: seven section headings stay `h3`, the Runtime & Backend group stays `h4` (runtime census asserted: H2×1, H3×7, H4×1).
- Shell h1 remains the sole `h1` (untouched).

## 3. Backend loading migration

All three sites now mount `renderLoadingState({ label, size, testid })` from `web/studio-loading.js`:

| Site | Label | Size | Testid |
|---|---|---|---|
| Backend Presets list | "Loading presets…" | page | `backend-presets-loading` |
| Snapshots list | "Loading snapshots…" | page | `backend-snapshots-loading` |
| Workspaces active line | "Loading workspaces…" | inline | `backend-workspaces-loading` |

Preserved exactly: fetches (`listPresets`/`listSnapshots`/`listWorkspacesRegistry`), error cards ("Could not load … from server"), empty states, auto-select detail behavior, and the workspaces server-truth replacement path (`renderActiveLine`). No new polling; warmup/API freeze untouched; deployment/readiness state machines untouched.

## 4. Chip audit result

- `statusBadge()` consumers inherit the shared base automatically (I3 global migration); verified at runtime: workspace ACTIVE badge computes `border-radius: 999px`, `data-tone="ok"`.
- **feature-chip producer** (`renderFeaturesChipGrid`, studio-backend.js): semantics measured = FILTER (interactive `aria-pressed` toggles selecting compatible features). Disposition per freeze: kept `aria-pressed`; adopted the shared geometry base only — class is now `"comfymodal-studio-feature-chip cm-chip"`. **Not** labeled `cm-chip--compatibility`, carries no `data-tone` (current semantics win; the compatibility-family candidate was rejected). Legacy checked/hover/chip-check rules intact; typography stays owned by the legacy `button.…feature-chip { font-size: inherit }` rule (geometry-only adoption, mirroring statusBadge's sanctioned precedent). Runtime note: computed display blockifies `inline-flex→flex` inside the flex chip-grid per CSS display spec — radius/padding carry the base (asserted).

## 5. Reset accessible names

`buildSectionHeader` now emits `"aria-label": "Reset " + title + " section"` on each section reset button. Accessible names: **Reset Generation section / Reset Outputs section / Reset History section / Reset Interface section / Reset Advanced section** — pairwise unique (also unique vs "Reset panel layout" and "Reset all settings"). Visible button text stays concise ("Reset section"). Reset behavior untouched (F4 §9 Reset-All GPU-only POST flow still green).

## 6. Frozen wording changes (I1 §3.6 rows implemented)

1. General → `Primary navigation: Playground / History / Workflows / Backend / Settings.` (apologetic phrasing removed)
2. History → `Run history is stored locally and is kept until you delete it.`
3. Experiments → `Experiments run up to 6 cells concurrently. Per-experiment overrides are not available.` (concurrency value 6 frozen and pinned)

NOT done (out of scope): Workflow Presets/Backend Presets renames (forbidden), Runtime & Backend info-row physical cleanup (OPTIONAL_G_HYGIENE — rows left in place, ownership unchanged), any cross-system copy edits.

## 7. Backend tab accessibility

Widget semantics: exclusive view-switcher buttons (no roving tabindex, no Arrow-key tablist model, panels not linked via ARIA) → forcing `role=tablist` would be untruthful. Smallest correct state added: `aria-current="true"` on the active tab, attribute fully removed from inactive tabs (`makeTab` initial state + `switchTab` sync). Keyboard behavior unchanged (native buttons): fake test E walks all six tabs with Tab presses and activates with Enter — traversal order and activation both proven; exactly one `aria-current` at any time.

## 8. Dead backend empty-wrapper disposition

Still zero callers after re-measurement → **deleted**: the `renderEmptyState` wrapper export and its `_renderEmptyState` import leg in `studio-backend.js`. I3's shared generic `renderEmptyState(options)` in `studio-ui.js` is untouched (byte-marker unit pins stay green). Directly affected structural test updated (`tests/test_testing_shell_integration.py::RootCauseEmptyStateBugTests`): now asserts the shared options API lives in studio-ui.js AND that the glue file contains no `renderEmptyState` reference at all (the deletion comment was worded to keep this pin honest).

## 9. Authority regression

- **Settings guards hold**: preferences-only surface unchanged; GPU authority (server-first) intact; Preview/Outputs/History layout/Interface/tracing intact; Run mode, engine selector, provider selector, Backends count row, legacy Settings UI all absent (unit 9b + python pins + fake G). Reset All keeps Phase-H semantics (GPU-only POST + truthful disclosure + durable-data preservation — f4 §9 green). Zero new fetches; `/studio/backends` appears nowhere in Settings source or recorded traffic (fake G asserts zero matching requests during a full Settings visit).
- **Backend guards hold**: full H6 operations unit (W1–W8 workspace CRUD/activate/swap incl. exact POST bodies and failure-truth retention, D9–D14 deploy/redeploy/dedupe/no-deploy-on-mount/bounded failure, A15–A18 credential secrecy, O19–O24 ownership/warmup/overview) passes unchanged alongside the two new I7 sections. `/studio/backends` remains hidden compat only; no server files touched.

## 10. Count discipline & observed shared gate

Full gate command: `python tests/run_studio_tests.py --fake` → **ALL STUDIO LANES GREEN**

| Lane | Before I-lanes page wave | After (shared tree) | Attribution |
|---|---|---|---|
| Python | 2124 (I3 close) | **2133 run, 0 fail/error/skip** | **+9 ALL I7** (+1 net shell-integration class, −1/+1 nav-copy methods, +8 `PhaseI7BackendSettingsPolishTests`); siblings added none |
| Node-unit files | 27 (I3 close) | **27 files PASS** | **0 delta** (I7 extended registered `studio_backend_operations_unit.mjs` [+2 sections] and `studio_phase_f4_settings_authority_unit.mjs` [+3 sections]; no new files, runner untouched) |
| Fake Playwright | 219 (I3 close) | **246 passed** (direct exact count) | **I7 +7** (`studio-fake-phase-i7-backend-settings-polish.spec.mjs`: A–G). Siblings visible in full count: I4 +6, I6 +8, I8 +6 (219+6+8+7+6=246, arithmetic exact). Auto-discovered via `testMatch` — no registration edit |

Focused runs: I7 spec 7/7 passed standalone (stable across repeats); all four extended/updated node units pass individually; `test_studio_backend.py` + `test_testing_shell_integration.py` + `test_h14_wave_e_retirement.py` = 523 passed / 417 subtests.

## 11. Exact files

**Production (5):**
- `web/studio-backend.js`
- `web/studio-backend-presets.js`
- `web/studio-backend-snapshots.js`
- `web/studio-backend-workspaces.js`
- `web/studio-settings.js`

**Tests (6 changed + 1 new):**
- `tests/backend_operations` → `tests/studio_backend_operations_unit.mjs` (extended)
- `tests/studio_phase_f4_settings_authority_unit.mjs` (extended + concurrency pin repointed)
- `tests/test_studio_backend.py` (nav-copy pins updated + I7 structural class)
- `tests/test_testing_shell_integration.py` (empty-state pin repointed to current truth)
- `tests/studio_phase_e_preview_settings_unit.mjs` (concurrency string pin repointed)
- `tests/studio_phase_i3_shared_primitives_unit.mjs` (§20 drift update; merged coherently with concurrent I6/I8 updates — I7 entries retained)
- `tests/browser/fake/studio-fake-phase-i7-backend-settings-polish.spec.mjs` (NEW, 7 tests)

**Report:** this document.

Deploy / live / GPU / commit / push: **NONE**.
