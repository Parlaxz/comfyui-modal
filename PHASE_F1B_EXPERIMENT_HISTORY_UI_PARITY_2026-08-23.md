# Phase F1 Follow-Up B — Experiment History UI Parity (Cancel + Cell Menu) — 2026-08-23

**Lane:** F1B — Experiment History FRONTEND parity only.
**Scope guard:** No backend Cancel redesign, no Single Resume UI, no History Python / replay / scheduler / startup-recovery / Settings / exports / GPU-authority changes. F1A (backend Resume/recovery) is a separate concurrent lane; nothing here depends on or modifies it. This report does not edit the shared F1 audit; a later reconciliation can merge evidence.

---

## 1. F1 audit findings addressed

| F1 finding | Resolution in this batch |
|---|---|
| Experiment Cancel: "BACKEND COMPLETE / NOT SURFACED IN HISTORY UI" (`repo.cancelExperiment` wired but never called from History) | **Closed.** History experiment detail now exposes a whole-Experiment Cancel action behind durable-state eligibility, calling `repo.cancelExperiment` exactly once per explicit click. |
| Latent defect: `openCellMenu` at `web/studio-history-v2-experiment.js:430` calls unbound `item.focus()` → ReferenceError when a cell `⋮` menu opens (menu mounts; focus step crashes; no test exercised menu open) | **Closed.** Root-caused, fixed with the existing UI convention, and pinned by a real rendered browser test that drives the previously-crashing path. |

## 2. Cancel UI contract

- Single action, whole-Experiment scope, header action row next to Resume: `data-testid="history-v2-experiment-cancel"` ("Cancel experiment").
- Uses the ONE existing cancellation concept: frozen route `POST .../history-v2/experiments/{id}/cancel` through the pre-existing `repo.cancelExperiment`. No second cancellation concept invented; no per-cell Cancel added.
- Click flow (no optimistic state anywhere):
  1. duplicate-submission guard (disabled + in-flight flag);
  2. exactly one `repo.cancelExperiment(experimentId)` POST;
  3. durable refetch via `repo.getExperiment`;
  4. full page re-render from the refetched record (`_rerenderPage`) so cells/counts/chips always show server truth;
  5. truthful status note on `[data-testid="history-v2-experiment-cancel-note"]`, resolved from the live DOM after any re-render.
- Repository normalization (narrow change to `_v2CancelExperiment` in `web/history-v2-repository.js`): non-OK responses whose bodies carry a structured code (`code`/`error_code`/`outcome`) resolve to `{ accepted:false, errorCode, message, httpStatus }` instead of a bare HTTP error — machine-readable codes are preserved rather than parsing human text. Unstructured failures still reject truthfully.

## 3. Eligibility matrix (derived from DURABLE cell state)

`historyExperimentCancelEligible(rec)` mirrors the backend truth table (`experiment_modern_routes._handle_cancel`: cancel applies iff ≥1 cell is queued/running; all-terminal aggregates are refused):

| Aggregate / cells | Cancel offered |
|---|---|
| queued cells (any) | Yes |
| running cell (any, incl. mixed terminal siblings) | Yes |
| completed | No (hidden) |
| completed_with_failures / failed aggregate | No (hidden) |
| canceled (all) | No (backend is idempotent-200; UI hides — nothing to do) |
| interrupted-only | No (backend terminal-like → 409; UI follows backend truth, no broadening) |

## 4. Failure semantics

- **503 CANCELLATION_UNAVAILABLE** (running cells + no truthful remote-cancel primitive): button re-enables (still eligible), experiment remains Running per the refetched durable record, running cells stay Running, queued cells show Canceled exactly as the backend atomically canceled them, concise note shows the preserved structured message ("running-cell cancellation is unavailable…"). No unhandled rejection, no synthetic "Cancel requested" terminal state, no locally fabricated canceled cells.
- **409 EXPERIMENT_TERMINAL / other refusals:** message surfaced verbatim from the normalized body; state re-rendered from durable truth.
- **Network/refetch failure:** control recovers without inventing state; error note shown.

## 5. No-close-cancel proof

Closing detail (Back), pressing Escape on detail, and navigating away send **zero** cancel requests — pinned by browser test C2 with a request counter around every close path. Only the explicit button invokes cancellation.

## 6. Cell-menu root cause and fix

- **Root cause:** `openCellMenu()` ended with `item.focus()` where no `item` binding exists in scope → ReferenceError on every cell `⋮` open (menu appended first, so it mounted, then the focus step threw as an uncaught page error). Reproduced by the new browser test driving the real click path (fails on the old code with a pageerror).
- **Fix:** focus the first actionable menu item — `menu.querySelector("button:not([disabled])").focus()` — matching the existing convention (plain container of native buttons; Escape already closes via the menu keydown handler; outside-mousedown closes; trigger focus-return follows the pane-star pattern used elsewhere).
- Not redesigned; Generate Original / Retry Original / Generate Again callbacks untouched; F2A Generation-backed cell favorite untouched (`repo.setFavorite(genId, …)` still the only cell-favorite write).

## 7. Fake backend parity (minimum needed)

`tests/browser/fake/fake-backend.mjs` already mirrored queued/running/terminal/idempotent cancel. Added only:
- optional per-experiment `remote_cancel_available === false` (set via the existing `/__comfymodal_test/modern-experiment-state` control), reproducing production's truthful-refusal path: queued cells still cancel atomically, running cells remain durable, response is 503 `CANCELLATION_UNAVAILABLE` with `running_cells`.
No fake behavior is more permissive than production.

## 8. Tests

- **Unit** (`tests/studio_history_v2_experiment_unit.mjs`, +2 sections): §9 cancel eligibility matrix (queued/running/mixed eligible; completed/completed_with_failures/failed/canceled/interrupted-only/null/no-cells not); §10 UI-contract source assertions (exactly one `repo.cancelExperiment` call site, eligibility-gated visibility, no local `status="canceled"` fabrication, `CANCELLATION_UNAVAILABLE` handled structurally, unbound `item.focus()` gone, first-actionable-menu-item focus present, Original actions + F2A favorite call sites intact).
- **Browser** (`tests/browser/fake/studio-fake-history-cancel-menu.spec.mjs`, NEW, 5 tests): C1 active shows Cancel + exactly one POST + durable refresh to Canceled + action disappears + no second request; C2 terminal completed hides Cancel + close/Escape/navigation = zero requests; C3 503 leaves Running truthfully + truthful message + recovery/re-enable + no unhandled rejection + server-side cell truth; C4 favorite+note survive post-cancel refresh and full reload; M1 real `⋮` menu open (zero console/page errors, first actionable control focused, Escape closes, reopens with focus restored, Generate Original callback fires, F2A cell favorite stays Generation-backed with Experiment favorite untouched).
- **Focused results:** unit 10/10 PASS; new spec 5/5 PASS; F2A annotations + Phase-E Original + D5 modern-experiment parity specs 29/29 PASS.
- **Full wrapper** (`python tests/run_studio_tests.py --fake`): python run=1642 fail=0; node-unit run=18 fail=0; fake-playwright lane PASS (141 tests in 17 files total). ALL STUDIO LANES GREEN.

## 9. Files modified by THIS lane

- `web/studio-history-v2-experiment.js` — cancel eligibility helper, header Cancel action, cell-menu focus fix.
- `web/history-v2-repository.js` — narrow `_v2CancelExperiment` structured-refusal normalization.
- `tests/browser/fake/fake-backend.mjs` — minimal remote-cancel-unavailable parity + test-control flag.
- `tests/studio_history_v2_experiment_unit.mjs` — sections 9–10.
- `tests/browser/fake/studio-fake-history-cancel-menu.spec.mjs` — NEW browser coverage.
- `PHASE_F1B_EXPERIMENT_HISTORY_UI_PARITY_2026-08-23.md` — this report.

## 10. Remaining F1 work (explicitly excluding active F1A backend scope)

- Single Resume History UI (blocked on F1A's Single Resume route — intentionally NOT implemented here).
- F1 reconciliation merge of this report into the main F1 audit.
- Optional polish (non-blocking): feed-level cancel affordance was deliberately not added (detail-page action satisfies parity); per-cell Cancel remains out of scope per batch contract.

Deploy/live/GPU/commit/push: NONE.
