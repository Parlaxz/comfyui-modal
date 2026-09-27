# PHASE I9A — POST-I5/I9 CONVERGENCE, TEST REGISTRATION & ROUTING-DEBT FREEZE (2026-08-25)

**Batch type:** short convergence / test-authority lane after I5 ∥ I9. Executed directly in the shared dirty working tree (no subagents; no reset/revert/stash/branch/worktree; no deploy/live/Modal/GPU/commit/push). No broad product work.

---

## 0. VERDICT

## `I9A COMPLETE — I10 READY`

Final deterministic gate (single command): `python tests/run_studio_tests.py --fake` → **ALL STUDIO LANES GREEN** (Python 2133/2133 · node-unit **29/29** · fake-playwright PASS), plus direct exact count `npx playwright test --config=playwright.fake.config.mjs --reporter=line` → **271 passed / 271**.

---

## 1. PRE-REGISTRATION GATE (mandated order: runner untouched at this point)

```
python tests/run_studio_tests.py --fake
  python             run=2133  fail=0  error=0  skip=0
  node-unit          run=27    fail=0  error=0  skip=0
  fake-playwright    PASS
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  268 passed (3.8m)   (direct exact count)
```

Matches the authoritative post-I5+I9 shared baseline **exactly** (2133 / 27 / 268). I9's later clean shared-tree result is confirmed authoritative; I5's intermediate concurrent observation (247/20 unrelated execution-surface failures) is disproven by current re-measurement — those surfaces are green in the same gate. Zero drift to reconcile.

---

## 2. I5 + I9 COEXISTENCE VERIFICATION (source census)

Current source contains both lanes' deliverables with no ownership overwrite:

| I5 | Present |
|---|---|
| `web/studio-image-compare.js` | yes — pure model (`normalizeImageDescriptor`/`clampPercent`/`createCompareSessionModel`) + transient singleton/tray/view; sole import `el/registerLayerHandler` from `./studio-ui.js`; zero persistence/backend/route vocabulary |
| Generation-detail Compare entry | `studio-history-v2-detail.js` imports compare module; `history-v2-compare`, `history-v2-compare-original`, per-output Add-to-compare(B) all wired |
| Experiment-cell Compare entry | `studio-history-v2-experiment.js`: cell pane Compare + cell menu Add-to-compare(B); no second model instantiated |
| Exactly-two-image model, no persistence, no backend writes | pinned by unit §12 (bans incl. `/comparison/`, `pushState`, `fetch(`, storage APIs) |

| I9 | Present |
|---|---|
| `web/studio-routing.js` | pure parse/serialize/decision helpers, zero imports, DOM-free |
| Shell routing authority | `studio-shell.js`: `_resolveInitialRoute`, `_syncUrl` (hash-only push/replace + lazy seed), exactly one `hashchange` listener (removed in `destroy()`), alias precedence via `initialRoute` in `modal-testing.js`, `_navGen` late-Playground cross-page stale guard |
| Router dependency | none — unit pins zero router/state-library references across `web/*.js`; page modules routing-free |

No file owned by one lane carries the other's markers beyond their designed seams.

---

## 3. I5 NODE UNIT AUDIT — REGISTERED

`tests/studio_phase_i5_image_compare_unit.mjs` — standalone re-run PASS (14 numbered sections). Every section still protects CURRENT Phase-I behavior: empty session · A selection · B fill · third pick replaces B · new A resets pair · reset · position 50 default · coercion/clamp/rounding · ±5 nudges with boundary clamp · Home/End · malformed input fail-soft · descriptor normalization/caps/presentation-only shape · onChange contract · persistence/backend/retirement bans · entry-wiring pins · viewer byte-marker contract. No stale assertions found; nothing removed. **REGISTERED in `NODE_UNIT_FILES`.**

## 4. I9 NODE UNIT AUDIT — REGISTERED

`tests/studio_phase_i9_routing_unit.mjs` — standalone re-run PASS (7 sections). Coverage current and complete: five canonical pages · parse no-focus/focus · malformed & unrelated-hash fail-soft (incl. case sensitivity, traversal, non-string inputs) · unknown page · serialization · percent encoding + 5×13 serialize↔parse round-trip corpus · full routeHistoryAction push/replace/none matrix · no routing library · single shell-owned hashchange listener (+destroy removal) · alias-map survival pin · page modules routing-free. **REGISTERED in `NODE_UNIT_FILES`.**

## 5. NODE COUNT LEDGER

27 (pre-existing) + 1 (I5 unit) + 1 (I9 unit) = **29 registered Node files**. Neither unit merged nor dropped — each protects a distinct contract surface. After registration there is ZERO meaningful current deterministic Node unit left unregistered.

## 6. ROUTING-DEBT CLASSIFICATION TABLE (no UNKNOWN)

| # | Limitation (from I9 §14) | Classification | Basis |
|---|---|---|---|
| 1 | Experiment-id History deep links resolve as generations (bare id has no kind) | **DEFER_PHASE_I** | §7 below — frozen format cannot encode kind; fail-soft is truthful, not a blocker |
| 2 | Closing generation detail does not clear/update `focus=` in the hash | **FIX_BEFORE_I10 — IMPLEMENTED (I9A)** | §8 below — measured URL-lie + dismissed-record resurrection on cached reopen/reload |
| 3 | Workflows focus is fail-soft only | **DEFER_PHASE_I** | §9 below |
| 4 | Backend focus is fail-soft only | **DEFER_PHASE_I** | §9 below |
| 5 | Settings outputs-section focus can be delayed/blocked by async row population | **DEFER_PHASE_I** | §10 below — measured permanent miss; blocker is Settings-owned visibility, not shell-retryable |

New convergence finding (not in I9's list): a body-level generation-detail overlay could survive a routed page swap (Back→Forward) and block the newly mounted page. Folded into the single bounded I9A fix (§8c).

## 7. EXPERIMENT-ID DEEP-LINK CLASSIFICATION — `DEFER_PHASE_I`

Re-measured current public seams: `requestHistoryRecordFocus(recordId, kind)` accepts `"generation"|"experiment"`, but `kind` must be supplied by the CALLER — the shell routes a bare URL id and has no id→kind discriminator before data arrives. The feed knows `record.kind === "experiment"` only after fetch; using that would require either a backend lookup, DOM scraping, or amending the frozen I1 §3.8 URL schema (second param / `kind=`) — all explicitly out of bounds without an evidenced contract amendment. None found. Preferred outcome adopted: **DEFER_PHASE_I**, limitation documented. A generation-focused deep link fail-softs on an experiment id onto the truthful "Generation not found" placeholder (Close restores the feed; E2E E2 stays green) — not automatically a blocker when the frozen format cannot encode kind.

## 8. DETAIL-CLOSE HASH CLEARING — `FIX_BEFORE_I10` (IMPLEMENTED)

Measured user behavior starting from `#comfymodal=history&focus=<valid-generation>` (probe + permanent spec):

- Close detail → hash KEPT `focus=gen_ok` while the UI showed the feed → **URL lies about current state** (measured).
- Cached modal close/reopen and reload-then-reopen honor the still-present hash (I9 spec D/E mechanics, individually runtime-proven) → the record the user explicitly closed **reopens unexpectedly** (code-path chain of two runtime-proven mechanisms; probe captured the stale-hash precondition directly).

Per the mandate decision rule this is `FIX_BEFORE_I10`, implemented as the SMALLEST safe integration using ONLY the existing routing authority — no second router, no routing vocabulary in page modules:

a. `web/studio-shell.js` — new shell-owned `clearRouteFocus()`: drops the focus identity from the managed route and rewrites the hash to the bare page route through the existing `_syncUrl` replace path; marks the current entry seeded so the rewrite replaces IN PLACE (never pushes a resurrectable duplicate entry). Exposed on both `pageContext` and `shellApi`.
b. `web/studio-history-v2.js` — the already-existing (empty) detail `onClose` callback now calls `context.clearRouteFocus?.()` (guarded; fail-soft when absent). I5-owned detail file semantics unchanged by this seam.
c. `web/studio-history-v2-detail.js` — routed-page anchor: the body-level overlay observes the live `[data-testid="history-v2-page"]` root (the SAME teardown-anchor contract as the I5 compare tray) and closes itself if its page root disconnects, so Back/Forward page swaps can never leave a stale full-screen dialog intercepting the new page's pointer events. Observer disconnected on normal close.

Post-fix proof (permanent spec L + K): close detail → hash becomes exactly `#comfymodal=history`; cached reopen and reload-reopen show the FEED (no resurrection); fresh deep links still honored (E contract intact); Back off a focused entry applies deterministic deep-link semantics; Forward/hash-swap away auto-closes the overlay; `routeHistoryAction` matrix, single-hashchange-owner, and page-module routing-free pins all still green.

## 9. WORKFLOWS / BACKEND FOCUS — `DEFER_PHASE_I` (both)

No stable public focus/subtab API exists in either owner (`_view` module-private in workflows; Backend `activeTab` render-local with known-but-unsettable subtab ids). Page-level deep links ARE truthful: `#comfymodal=workflows` / `#comfymodal=backend&focus=…` open the correct page; unknown focus ids resolve nothing; **no false state is shown**; no DOM-scraping introduced. No current product requirement justifies editing I6/I7 production merely to satisfy focus examples. Frozen as `PAGE_ROUTE_SUPPORTED / FOCUS_FAIL_SOFT`.

## 10. SETTINGS OUTPUTS FOCUS — `DEFER_PHASE_I` (measured miss; root cause deeper than I9 stated)

Runtime reproduction of `#comfymodal=settings&focus=outputs` (probe M): the section wrapper and header render synchronously, BUT `rebuildPage()` runs the search filter (`applyFilter`) once at mount with zero `[data-search]` rows present in Outputs → the section is set `display:none`; the preference rows populate asynchronously afterwards and NOTHING re-runs the filter. Measured end state: `display:"none"`, `scrollTop:0` — `scrollIntoView` on a hidden element is a permanent no-op, so the deep link misses permanently (worse than "delayed"). The shell focus seam itself has no retry/handling and a shell-owned post-render retry CANNOT fix this: the blocker is Settings-owned visibility logic, and fixing it means touching Settings authority (re-running its filter after population) — out of I9A scope per ownership rules. Classified **DEFER_PHASE_I**; the finding (including the one-line-shaped owner-side remedy) is documented here for the Settings/I7 owner. Permanent spec M pins the routing-side fail-soft contract (page mounts, sole-current, canonical hash, rows eventually populate, no crash) and references this deferral.

## 11. I5 × I9 INTERACTION RESULT (main convergence proof)

`tests/browser/fake/studio-fake-phase-i9a-convergence.spec.mjs` (NEW, 3 tests, extends the existing fake suite rather than a new framework):

- **K** — deep-link directly to a History generation → open Compare → fill B → assert URL remains exactly canonical during ALL compare activity → operate slider (ArrowRight → aria-valuenow 55) → Escape closes view AND clears session while the underlying detail stays valid → closing the detail clears the stale focus from the URL → Workflows nav push / Back (no resurrection from cleared route) / Forward deterministic → focused-entry Back/Forward semantics + routed-swap overlay auto-close (orphan regression pin) → live compare session torn down the moment History is left (tray gone) → returning to History shows NO stale tray/overlay.
- **L** — after dismissing a focused detail: cached modal close/reopen AND reload-then-reopen land on the feed (dismissed record stays dismissed) while fresh deep links keep working.
- **M** — settings `focus=outputs` routing-side fail-soft contract + documented deferral boundary.

Result: **all green**. Routing never corrupts compare state; compare never perturbs the route.

## 12. RETIRED COMPARISON GUARD (re-run census)

Static: `web/modal-comparison.js`, `web/testing-dashboard/ab-slider.js` (+ retired dashboard profiles/runner/history files) ABSENT from disk; zero `comparison/run` / `ComparisonProfile` / `ComparisonRunner` strings anywhere in `web/*.js`. Runtime: I5 spec I (feed body text free of Comparison Profiles/Runner//comparison/run vocabulary; zero comparison-profile/-runner/ab-slider DOM nodes; dynamic import of the retired ab-slider path rejects) — re-ran green. New module remains purely client-side (zero persistence/backend route logic; network proof H: only asset GETs). The server-side legacy `/comfymodal/comparison/*` route registration visible in Python harness logs is the pre-existing 410-retired stub, not modern-UI usage.

## 13. ROUTING GUARDS (re-run)

Focused re-run post-production-changes: I2 semantic nav spec + I9 routing spec (**20/20**) and I8 stale-response reproduction + visual specs (**8/8**) — proving exactly one `aria-current="page"` after click/programmatic/Back/Forward, page route ↔ nav synchronization, stale async page cannot overwrite active page (H1 held-response + H2 run-completion paths), deterministic Back/Forward including the seeded-entry landing inside Studio, unrelated host hashes ignored both directions, alias precedence (F), and all three touched Node units standalone-green (I2 unit's routing-isolation ban list still satisfied — page modules gained no banned routing vocabulary).

## 14. FULL REGISTERED GATE (after registration)

```
python tests/run_studio_tests.py --fake
  python             run=2133  fail=0  error=0  skip=0
  node-unit          run=29    fail=0  error=0  skip=0
  fake-playwright    PASS
npx playwright test --config=playwright.fake.config.mjs --reporter=line
  271 passed (4.0m)   (direct exact count)
```

One transient timing failure (`studio-fake-lifecycle.spec.mjs` #11) occurred in the first full-suite pass under load; it passes 14/14 in isolation and the complete fake lane then passed **271/271** twice-checked. Not attributable to any I9A delta (Playground lifecycle surface; none of this lane's files participate in its path).

### Exact count ledger

| Lane | Pre-I9A | Delta | Post-I9A |
|---|---|---|---|
| Python | 2133 | 0 | **2133/2133** |
| Registered Node files | 27 | +1 I5 unit, +1 I9 unit | **29/29** |
| Fake Playwright | 268 (= 246 base + 12 I5 + 10 I9) | +3 I9A convergence (K, L, M) | **271/271 exact** |

## 15. REPEAT ORDER / ISOLATION CHECK

Bounded probe (workers=1, deterministic): **(A)** I5 spec alone 10/10 · **(B)** I9 spec alone 10/10 · **(C)** I5→I9 20/20 · **(D)** I9→I5 20/20 · **(E)** combined I5+I9+I9A-convergence 23/23. Each fake test starts from a fresh page/session (fresh ES-module instance), so compare-session module state and hash/history state reset per test; the compare tray/observer teardown is exercised within-test (K steps 5/9). Static census: **BroadcastChannel does not exist yet** anywhere in `web/` (I10 untouched) — no cross-tab machinery to leak. No order dependence observed; nothing hidden via magic ordering; no fixture changes were needed.

## 16. PRE-I10 STATE

- I5/I9 coexist (§2, §11) ✓
- Both Node units authoritative and registered (29/29) ✓
- Every I9 routing limitation classified — no UNKNOWN ✓
- No routing correctness blocker remains: the two measured defects (stale-focus resurrection; orphaned overlay across routed swaps) are FIXED with the single bounded integration ✓
- No compare lifecycle leak (order/isolation probe + K) ✓
- Full deterministic gate green: 2133 / 29 / 271 ✓

**I10 READY.** (Carried-forward deferrals, none blocking: experiment-kind ambiguity, workflows/backend focus seams, Settings outputs visibility — owners documented above.)

## 17. FILES MODIFIED BY THIS LANE ONLY

Production (single bounded routing-correctness integration, §8):
- `web/studio-shell.js` — shell-owned `clearRouteFocus()` + exposure on `pageContext`/`shellApi`
- `web/studio-history-v2.js` — existing empty detail `onClose` now invokes the optional shell hook
- `web/studio-history-v2-detail.js` — routed-page teardown anchor (auto-close when the History page root disconnects; observer released on close)

Tests/registration:
- `tests/run_studio_tests.py` — registered both Node units in `NODE_UNIT_FILES` (27 → 29)
- `tests/studio_phase_i5_image_compare_unit.mjs` — header comment updated to registered status (assertions untouched)
- `tests/studio_phase_i9_routing_unit.mjs` — header comment updated to registered status (assertions untouched)
- `tests/browser/fake/studio-fake-phase-i9a-convergence.spec.mjs` — NEW permanent convergence spec (K/L/M)

Documentation:
- `PHASE_I9A_POST_I5_I9_CONVERGENCE_AND_TEST_AUTHORITY_2026-08-25.md` (this report)

Not touched: playground/workflow-run/models/backend/portability production files, `modal-testing.js`, `history-v2-view-state.js`, `studio-ui.js`, `studio-styles.js`, server/Python, all other specs.

---

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
