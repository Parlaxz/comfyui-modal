# PHASE I6 — WORKFLOWS / MODELS / PORTABILITY POLISH — 2026-08-25

## Verdict

**I6 COMPLETE**

Phase I Workflows/Models lane, executed directly on the shared dirty working tree in parallel
with I4/I7/I8. No subagents. I3 primitives consumed as-is; no shared-file edits
(`studio-ui.js` / `studio-styles.js` / `studio-loading.js` untouched by this batch). Workflow /
Version / Mapping authority and all portability semantics unchanged.

---

## 1. Re-measured census (confirmed before editing)

Loading DOM sites (I3 handoff §18 verified): `studio-workflows.js` library grid + detail view;
inline "Loading selected version…" (run bar) and "Loading mapping candidates…" (mapping
editor); `studio-model-library.js` model list first-open.
Chips: `wf-chip` (card tags, detail tags, compatible models, preset tags/Default, dependency
metadata chips), `model-badge` (installed/missing/warning/unknown/type/role),
`portability-chip` (card xN + detail).
Empty: `workflows-empty`, `models-empty` ad-hoc renderers.
I1 gaps confirmed: no custom-node find-handoff; no reverse usage link; duplicate portability
accessible names ("Portability: Not analyzed…" per card); pre-existing workflow-detail h1.

## 2. Heading hierarchy

- Page h2 "Workflows" preserved untouched (library view).
- **Detail h1 → h3** (`workflow-detail-name`): text, test id, class/styling preserved
  (the CSS is class-based with `margin:0`, so rendering is identical); the second application
  h1 is gone. Runtime proof: spec A asserts document-wide exactly one h1 ("Modal GPU") with
  the detail name an H3 and zero H1/H2 inside `[data-testid="workflow-detail"]`.
- Model Library sub-view title promoted h3 → **h2** using the existing page-title class
  (`comfymodal-studio-workflows-title`, new testid `models-page-title`) so the models mode has
  a truthful page-level h2 under the shell h1; "Custom nodes" stays h3 beneath it. The old
  element rule `.comfymodal-studio-model-library-header h3` no longer applies — styling
  intentionally converges on the sibling page-title pattern (documented visual delta:
  uppercase title).
- Section titles (Versions/Dependencies/Portability/Mapping/Presets) remain consistent h3
  siblings; dialog titles h3; editor blocks h4 — no blind card-title promotion.

## 3. Loading migration (shared primitive)

| Site | Now |
|---|---|
| Library grid | `renderLoadingState({label:"Loading workflows…", size:"page", testid:"workflows-loading"})` |
| Detail | `"Loading workflow…"` / `workflow-detail-loading` |
| Run-bar version line | `"Loading selected version…"` inline / `workflow-version-loading` |
| Mapping editor | `"Loading mapping…"` inline / `mapping-loading` |
| Model list first open | `"Loading models…"` page / `models-loading` |

Retained custom loading sites (with reason):
1. `renderModelPicker` option text "Loading models…" — a `<select>` content model cannot
   contain the div-based primitive; text option stays (mandate §3 carve-out).
2. Button-embedded busy labels ("Capturing…", "Checking portability…", "Scanning…",
   "Refreshing…", "Exporting…", "Importing…", "Requesting…") — button-state family stays
   custom per the I1 freeze.

## 4. Chip migration (page-specific classes kept)

- `_chip()` / `renderTagChip` / dependency metadata chips gain `cm-chip` +
  `data-tone="neutral"` (IDENTITY). The Default preset chip gains `cm-chip` +
  `data-tone="running"` (accent highlight; the later-in-stylesheet tone block would cascade-
  override legacy `.default` colors anyway, and running IS the truthful accent tone for it).
- `model-badge` gains `cm-chip` + truthful tones: installed→ok, missing/wrong-version→warn
  (CAPABILITY family per frozen taxonomy, consistent with version-state incomplete→warn),
  unknown/type/role→neutral. Legacy uppercase/letter-spacing still come from the legacy rules
  (statusBadge precedent); geometry/colors now have one shared source.
- Portability chips (card + detail) gain `cm-chip cm-chip--portability` + `data-tone=<kind>`.
  The Phase-G12 outline-pill presentation is preserved via the I3 family hook (transparent
  fill).

## 5. Portability remains distinct

Runtime proof (spec C): a portability chip computes `rgba(0, 0, 0, 0)` background with
`cm-chip--portability`; Compatibility annotations ("Compatible models" identity chips in the
detail header) compute a filled background — distinct families at equal tone.
Six-target advisory matrix, risk calculation, cache, manifest exactness, execution gating:
**zero logic edits** — `studio-portability.js` and `studio-portability-checklist.js` are
byte-unchanged this batch. Portability stays advisory.

## 6. Duplicate accessible names resolved

Card chips: `aria-label = "Portability for <workflow name>: <state>. Opens the portability
panel."` Detail chip adds workflow name + `v<N>` context. Visible text unchanged.
Spec D asserts all simultaneously rendered chip names are unique and match the format.

## 7. Empty states

`renderLibraryEmpty` → `renderEmptyState` ("No workflows yet" / "No workflows match your
filters", Clear-filters action preserved); model list → "No models scanned yet" (+detail line)
and "No models match your filters". Domain copy supplied by callers only; nothing baked in the
helper. No illustrations, no card redesign. Error states (loadError + Retry) kept custom.

## 8. Custom-node "Find in registry"

`renderDependencyNodeRow` gains a click-gated `Find in registry` button
(`dependency-node-find-registry`) on MISSING rows when the owner passes `onFindInRegistry`.
Handoff opens the EXISTING single Model Library view scoped to its custom-node registry
section: client-side name/class substring filter, truthful scope banner
(`custom-nodes-focus`) with explicit Clear, exact-name row highlighted inline
(`data-registry-match="true"`), honest no-match note when nothing installed matches.
No installation, no install-request fired, no raw installer, no new store (specs E/F assert
zero installer POSTs through the whole flow). The click-gated install REQUEST control is
unchanged and remains the only installer on the row.

## 9. Model "Used by N workflows · View" — implemented portion + exact missing seam

Implemented: a session-derived, purely in-memory index (`view.usageByModel`: filename →
Set(workflow_id)) filled ONLY from dependency payloads already fetched through normal detail
navigation (`getVersionDependencies`; recorded in `loadVersionData` and `refreshDependencies`).
Model rows with derivable data show `Used by N workflows · View`
(`model-used-by` / `model-used-by-view`; tooltip discloses the session scope). View navigates
the EXISTING Workflows view reusing existing filter state (`filters.usageModel` clause in
`applyFilters`) with a dismissible truthful notice (`workflows-usage-focus`). No persistence,
no reverse-index authority, no router.

Missing seam (reported, NOT invented): globally-complete counts require either embedding
per-model usage aggregates in `/studio/models` responses or a bulk versions/dependencies
surface — both are Phase-I-forbidden backend additions, so none was made. Rows without
observed data show nothing rather than an undercounted claim, and the notice states the
session scope truthfully.

## 10. Filter/handoff authority

Reused `openModelLibraryFiltered` (extended with exact-match highlight, cleared when the user
edits search manually) and added sibling `openRegistryFiltered`. All navigation is in-memory
product navigation through `_view.mode` + existing render/load functions. No new router
(I9 owns deep links).

## 11. Tests added / changed

New permanent fake spec (auto-registered via `testMatch studio-fake-*`, runner untouched):
`tests/browser/fake/studio-fake-phase-i6-workflows-models-polish.spec.mjs` — 8 tests:
A heading hierarchy (one shell h1 + Workflows h2 + Model Library h2 + detail H3, driven
through the real production dialog entry); B loading primitive on five sites incl. held-route
determinism; C shared chip geometry + tones + Portability≠Compatibility runtime distinction;
D unique portability accessible names; E Find-in-registry filtered landing + zero install
traffic; F exact registry-match highlight; G model-handoff exact-row highlight + Used-by
derivation/navigation/clear; H single-installer-authority census across library, registry,
dialog, and dependency rows.

Changed: `tests/studio_phase_i3_shared_primitives_unit.mjs` §20 — retired the migrated
`studio-workflows.js` / `studio-model-library.js` pins and removed those modules from the
"no primitive references yet" loop, documented as drift per the I2/I4/I7 re-point precedent
(I7 and I8 updated sibling entries of the same block concurrently on the shared tree; final
file credits all four lanes). Runner registration unchanged.

Authority regression run green: `studio-fake-workflow-portability.spec.mjs` (19) +
`studio-fake-models.spec.mjs` — immutable Version revision flow, Mapping authority, Workflow
Presets, exact manifest round-trip payloads, Compatibility≠Portability vocabulary/endpoints,
no provider execution selector, no duplicate installer authority; plus
`studio_model_library_parity_unit.mjs` (all 16 sections) against the edited sources.

## 12. Gate ledger

| Lane | Own delta | Observed shared-tree gate (final clean full run) |
|---|---|---|
| Python (`run_studio_tests.py`) | 0 | run=2133 fail=0 error=0 skip=0 (+9 vs pre-I baseline from sibling-lane registrations, none by I6) |
| Node unit files | 0 registered by I6 | 27 files, 0 failures (incl. updated I3 §20) |
| Fake Playwright | **+8 (I6 spec)** | **246 passed / 246 exact**, including the 8 I6 tests |

Note: during the parallel window, intermediate full runs showed transient History-V2
(pagination/search/feed) and one visual-baseline failure while sibling lanes were mid-flight;
those tests pass consistently in isolation and in the final clean full-suite run recorded
above. My lane's specs passed identically on every focused run.

## 13. Files modified by THIS batch

Production:
- `web/studio-workflows.js` — headings, loading/empty migration, chip/tone adoption,
  portability chip naming, usage index + filter clause + focus notice, registry handoff wiring
- `web/studio-model-library.js` — Model Library h2, loading/empty migration, badge tones,
  registry focus filter/highlight/Clear, model exact-match highlight, Used-by row,
  Find-in-registry control

Tests:
- `tests/browser/fake/studio-fake-phase-i6-workflows-models-polish.spec.mjs` (NEW)
- `tests/studio_phase_i3_shared_primitives_unit.mjs` (§20 pin retirement only)

Unchanged by design: `web/studio-portability.js`, `web/studio-portability-checklist.js`,
all shared files, backend/server/schema, `tests/run_studio_tests.py`.

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert /
stash / clean by this batch: **NONE**.
