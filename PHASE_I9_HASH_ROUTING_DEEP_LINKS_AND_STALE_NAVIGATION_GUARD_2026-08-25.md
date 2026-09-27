# PHASE I9 — STUDIO HASH ROUTING, DEEP LINKS, BACK/FORWARD & NAVIGATION STALE-GUARD (2026-08-25)

**Batch type:** Phase-I implementation lane 9. Executed directly on the shared dirty working tree in parallel with I5 (no subagents; no reset/revert/stash/branch/worktree; no deploy/live/Modal/GPU/commit/push). I5's compare/History-detail/shared-viewer files and all page-module production files remained untouched.

---

## 1. VERDICT

## `I9 COMPLETE — I10 ROUTING PREREQUISITE READY`

Final gate (single command): `python tests/run_studio_tests.py --fake` → **ALL STUDIO LANES GREEN**

```
python             run=2133  fail=0  error=0  skip=0
node-unit          run=27    fail=0  error=0  skip=0
fake-playwright    PASS      (268 passed / 268 direct exact count, EXITCODE=0)
```

I9-owned fake delta: **+10** (`studio-fake-phase-i9-routing.spec.mjs`). The observed shared total moved during the parallel window exactly as sibling lanes landed (see §14).

---

## 2. PRE-CHANGE RE-MEASUREMENT (mandate §1)

Confirmed against current source before any edit:

| Item | Measured truth |
|---|---|
| `state.activePage` / `setPage` / `updateNavActive` | single authority in `studio-shell.js`; mounted page + `.active` + `aria-current="page"` all derive from `state.activePage` |
| Page mount flow | `renderActivePage()` clears `.comfymodal-studio-pagecontainer` and synchronously rebuilds via `PAGES[page].render(state, pageContext)`; `pageContext = {...context, setPage}` per render |
| URL APIs | zero `pushState/replaceState/hashchange/popstate/location.hash` anywhere in `web/` — nothing added since I1 except this lane |
| Aliases | seven frozen `ALIAS_PAGE_MAP` redirects intact; `_applyLegacyAliasNavigation` routes exclusively through `shellApi.setPage` |
| `comfymodal.open-section` | `modal-testing.js handleOpenSection` opens Settings via alias then scrolls to `[data-section]` (kept byte-intact — Python pins require its literal presence) |
| History V2 focus seam | `requestHistoryRecordFocus(recordId, kind)` (H13) already exported by `studio-history-v2.js`, consumed once per mount inside repo-init; generation detail fails soft with a "Generation not found" placeholder; experiment detail falls back to the feed on failure |
| Workflows focus seam | none exported (`_view` module-private, `openWorkflowDetail` internal) |
| Backend subtab seam | none exposed (`activeTab` render-local; tab ids overview/workspaces/deployment/credentials/presets/snapshots) |
| Settings section seam | static `[data-section]` attributes: general/generation/outputs/history/experiments/interface/advanced |
| No second page authority created | routing layer only parses/serializes/decides; every application path funnels through the shell's `setPage`/`applyRoute` |

---

## 3. FILES OF THIS LANE

New:
- `web/studio-routing.js` — pure parse/serialize/history-decision helpers. Zero imports, no DOM/storage/network, no eval/HTML interpretation; decoded values are opaque identifiers only.
- `tests/studio_phase_i9_routing_unit.mjs` — standalone Node unit (**not registered** — runner is single-writer during parallel I5; convergence lane registers it).
- `tests/browser/fake/studio-fake-phase-i9-routing.spec.mjs` — permanent E2E (auto-matched into the gate).

Modified:
- `web/studio-shell.js` — routing authority (§5–§8), navigation stale-guard (§11), hashchange listener, settings-section focus seam.
- `web/modal-testing.js` — one import + two small regions: cached-reopen hash honoring and fresh-mount alias precedence (§7).
- `tests/studio_phase_i2_shell_nav_accessibility_unit.mjs` — §7 router-ban staged guard re-pointed for I9 (documented drift, same precedent as I4/I6/I7/I8 updating the I3 unit).

Explicitly untouched: `history-v2-view-state.js` (zero changes needed — URL focus rides `studio-history-v2.js`'s existing H13 seam; view-state remains pure localStorage persistence), `studio-playground.js` (the shell-level guard made a Playground-local guard unnecessary), `studio-ui.js`, `studio-styles.js`, all History detail/experiment files, Workflows/Models, Backend/Settings, server/API, `tests/run_studio_tests.py`.

---

## 4. PARSER / SERIALIZER CONTRACT (`web/studio-routing.js`)

Frozen format: `#comfymodal=<page>[&focus=<id>]`; pages ∈ {playground, history, workflows, backend, settings}.

- `parseStudioHash(hash)` → `{matched, page, focus}`. Leading `#` optional. Unmatched (fail soft, never throw) for: empty/unrelated hashes, wrong key, missing page, unknown/case-mismatched page, malformed percent encoding in the page segment. Focus rules: first `focus=` segment wins; unknown extra params ignored; empty value or malformed percent encoding drops the focus but keeps the page route.
- `serializeStudioHash({page, focus})` → canonical `#comfymodal=<page>` (+ `&focus=<encodeURIComponent(id)>`); `""` for non-canonical input. Only navigation identity serializes — never drafts/run state/filters/GPU/transient compare/dialog/workflow-edit state (§3/§14 of the mandate).
- `routeHistoryAction(prev, next)` → `"push" | "replace" | "none"`: next unrouted → none; prev unrouted → replace (seed); different page → push; same page new focus → replace; identical → none.
- Unit-proven round-trip corpus includes spaces, `/ ? & = % #`, unicode, double-encoded sequences across all five pages.

## 5. PUSH / REPLACE BEHAVIOR (URL writes)

Writes happen ONLY inside the shell (`_syncUrl`, hash-only; `pathname+search` always preserved; wrapped in try/catch):

- **Page change** → `history.pushState` (host history state passed through untouched).
- **First managed navigation seeds** the current entry via `replaceState` to the previous route's canonical hash before the first push, so Back from the first pushed page stays inside Studio instead of exiting ComfyUI. Open/close without navigating leaves the host URL untouched (lazy seed).
- Same-page re-renders and no-op identical routes write nothing (no duplicate entries).
- `pushState/replaceState` emit no events, so the listener below only ever sees real browser navigation.

## 6. BACK / FORWARD

The shell owns exactly one `window.addEventListener("hashchange", …)` (removed in `destroy()`). On event: parse new hash → matched → `applyRoute(route, {passive:true})` through the same single authority (page swap, nav `.active`, `aria-current`, focus seams); unmatched → ignored, Studio never hijacks unrelated host navigation. Proven by E2E B/C (Playground→History→Workflows→Back→Forward→Back×2 lands back on the seeded Playground entry, still inside ComfyUI) and test I (unrelated `#host-panel=open` ignored both directions).

## 7. OPEN / RELOAD CONTRACT AND EXPLICIT-OPENER PRECEDENCE

- Host reload closes the modal (expected); the next `open_testing_modal()` honors a present `#comfymodal=…` hash. Fresh mount: the shell resolves `location.hash` itself when no explicit initial route is supplied. Cached reopen: `modal-testing.js` parses the hash and calls `applyRoute(..., {rerender:true})`.
- Absent/unrelated hash → today's default (Playground) exactly.
- **Precedence (documented at `mountOptions`, modal-testing.js:283–288):** an explicit programmatic opener wins for its invocation — the alias target is passed as the shell's `initialRoute`, so a stale hash can never silently override it; the resulting modern canonical route is then serialized through the normal `setPage` authority (legacy vocabulary never appears in the URL). Order: explicit alias > existing hash > Playground default. All seven aliases pinned unchanged (E2E F uses `results` over a stale `#comfymodal=backend`).
- The `setup` alias Experiment-mode side effect and deprecation notices are preserved verbatim.

## 8. PER-PAGE FOCUS-SUPPORT MATRIX

| Page | Route | Focus support | Mechanism / limitation |
|---|---|---|---|
| playground | SUPPORTED | PAGE_ONLY | no stable focus seam exists; none fabricated |
| history | SUPPORTED | SUPPORTED (generation ids) | existing H13 `requestHistoryRecordFocus(id,"generation")` invoked BEFORE first render so the pending request is consumed on THIS mount. A bare URL id cannot distinguish experiment ids → an experiment id lands on the truthful "Generation not found" placeholder (fail-soft, Close restores the feed). Documented limitation; fixing it would require editing I5-owned modules. Invalid/deleted id: History still opens, not-found overlay, no crash (E2E E2). Closing the detail does not rewrite the hash (detail overlay is I5-owned; recorded debt). |
| workflows | SUPPORTED | FAIL_SOFT | no public handoff/focus API; route opens the library page; focus ignored. `PAGE_ROUTE_SUPPORTED / FOCUS_FAIL_SOFT`. |
| backend | SUPPORTED | FAIL_SOFT | no exposed subtab API in `renderBackend`; page always opens on Overview regardless of focus id. `PAGE_ROUTE_SUPPORTED / FOCUS_FAIL_SOFT`. |
| settings | SUPPORTED | SUPPORTED (section ids) | shell-side seam scrolls `[data-section]` into view with the same smooth-scroll + outline-flash presentation as `comfymodal.open-section`; unknown ids resolve nothing (Settings opens normally). Observed pre-existing quirk: `outputs` populates its rows asynchronously and stays `display:none` until then (I7-owned surface); deep links therefore target sections visible at mount. |

No DOM scraping anywhere; no second state authority; History V2 remains sole record authority — URL focus is presentation/navigation only and is never persisted.

## 9. LATE PLAYGROUND RESPONSE DEFECT — REPRODUCTION, ROOT CAUSE, FIX

Reproduced end-to-end with held `/comfymodal/history-v2/feed` routes (E2E H1/H2); with the fix disabled both tests fail exactly as I4/I8 described (Playground re-rendered over active History), and pass with it enabled.

Exact root cause (measured):
1. `renderFilmstrip`'s reload path was already `isConnected`-guarded, but the run-completion hydration path (`setRunState` → `refreshRecentRuns().then(...)` → matched → `context.setPage("playground")`, studio-playground.js:1097–1145) had NO guard: a delayed feed response resolving after the user navigated to History forced a Playground re-render over the active page.
2. Generalized: any page-context closure could force `setPage(<other page>)` after `setPage` had moved elsewhere.

Fix (shell-owned, general mechanism, zero Playground edits): each `renderActivePage` bumps a navigation generation (`_navGen`); the per-render context's `setPage` is wrapped:

```js
if (nextPage !== state.activePage && capturedGen !== _navGen) return;  // stale cross-page attempt
```

Design note (found by the full gate mid-lane, fixed same lane): a blanket "drop everything stale" guard ALSO swallowed legitimate same-page refreshes from the live run-controller whose closure predates an intervening re-render — run-completion specs failed under load. The shipped rule drops only stale CROSS-page attempts; same-page refreshes always pass (harmless by definition). User-driven nav buttons and programmatic `shellApi.setPage` close over the unguarded authority, so explicit intent is never dropped.

No sleeps, no fetch cancellation, no execution-path changes.

## 10. ROUTING × I2 ACCESSIBILITY

Every routed change drives the same three derivations from `state.activePage` (mounted page, `.active`, `aria-current="page"`); the I2 unit's behavioral sections still pass unchanged apart from the documented §7 re-point. E2E asserts sole-current after click, programmatic, Back, Forward and post-release states. No tablist, no links-in-nav, no hamburger; native `<button data-page>` preserved.

## 11. ROUTING UNIT RESULT

`node tests/studio_phase_i9_routing_unit.mjs` → 7/7 sections PASS (canonical pages; focus rules incl. first-wins/extra-param/malformed handling; fail-soft inputs incl. null/undefined/non-string; serialization; 5×13 serialize↔parse round-trip corpus; full decision matrix; consumer/source pins: routing isolated to studio-routing.js + shell lane, page modules routing-free, zero router-library references in `web/*.js`, single shell-owned hashchange listener removed on destroy, alias map intact).

## 12. FAKE E2E (permanent) — 10 tests, deterministic

A hash+aria-current · B/C Back/Forward stack · D copied/reload honored · E valid focus deep link (default-seed `gen_ok`) · E2 invalid id fail-soft (allowlists exactly the one expected lookup 404) · F alias precedence · G settings section scroll + unknown-id fail-soft · **H1** filmstrip late response cannot flip the page · **H2** run-completion hydration cannot flip the page (drives a real single run, holds its feed, releases after navigating) · I unrelated host hash ignored both directions. Reproduction proof performed by temporarily disabling the guard: H1+H2 fail (Playground takeover), restored immediately after.

## 13. COUNT LEDGER

```
Python : 2133            (unchanged; expected — no server/authority change)
Node   : 27 registered   (unchanged; I9 unit intentionally UNREGISTERED)
Fake   : observed shared total 268 exact at final gate (268/268 PASS, EXITCODE=0)
         I9 owns exactly +10 (its spec). Sibling lanes (I5 et al.) continued
         landing specs concurrently in the shared tree; earlier intermediate
         observations were 247/247 and a --list snapshot of 267 — all green at
         every checkpoint, composition attributable to live sibling lanes.
Drift  : none unexplained; no existing test weakened or deleted.
```

Focused lanes also green: persistence + i8-playground + playground (13/13), workflow-run + i9-routing (42/42), both touched node units standalone, `node --check` on all three production files.

## 14. REMAINING ROUTING DEBT (explicit)

1. Experiment-id deep links resolve as generations (kind unknowable from a bare URL id) — needs an I5-owned resolution seam to improve.
2. Generation-detail Close does not rewrite the hash (selection-clearing replaceState lives in I5-owned detail code).
3. Workflows/Backend focus remain `PAGE_ROUTE_SUPPORTED / FOCUS_FAIL_SOFT` until their owners expose a stable seam (Backend subtab ids are known but not externally settable).
4. Settings `outputs` section is hidden until its async preference rows populate (pre-existing I7 surface); deep links target mount-visible sections.
5. Convergence lane: register `tests/studio_phase_i9_routing_unit.mjs` in `NODE_UNIT_FILES`.

---

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
