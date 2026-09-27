# Phase F1 — History Action Reconciliation Audit (2026-08-22)

**Lane:** Phase F opening batch — READ-ONLY architecture/reconciliation audit.
**Base:** `PHASE E COMPLETE — deterministic and live gates green.` (E6 + E7 + Follow-Up A).
**Scope:** Retry / Resume / Generate Original / Generate Again / Cancel as surfaced through History V2, Single vs Experiment parity, immutable-plan safety, race semantics, legacy behavior, deterministic coverage.
**Constraints honored:** no production/test edits, no deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset; unrelated V2/E40/R41 dirty files untouched. **Files modified by this batch: this audit document only.**

---

## 1. Executive verdict

**F1 verdict: History actions are substantially COMPLETE after Phase E; the only genuinely open action lane is RESUME for ordinary Singles (plus two narrow durability/parity gaps), and Generate Original needs zero further work.**

| Roadmap action | Classification |
|---|---|
| Generate Original | **COMPLETE — ALREADY SATISFIED BY PHASE E** (E3B2 backend + E4C frontend + E6/E7 gates) |
| Retry Original (dedicated) | **COMPLETE** (E4D: bodyless `/original/retry`, append-only, retained failure) |
| Generate Again (explicit rerender) | **COMPLETE** (E4C: `/original` with exactly `{rerender:true}`) |
| Experiment cell Retry | **COMPLETE** (D5 frozen route + guarded repo seam + UI tile/pane buttons) |
| Experiment Resume | **PARTIAL** — complete within a live process; post-host-restart resume creates durably queued attempts that nothing dispatches (§5.B) |
| Experiment Cancel | **BACKEND COMPLETE / NOT SURFACED IN HISTORY UI** — frozen route + truthful scheduler-gated semantics exist; the History experiment page renders no Cancel control (`repo.cancelExperiment` is wired but never called from History UI); cancel lives only in the live experiment-mode controller |
| Ordinary Single Retry (failed run) | **FUNCTIONALLY COMPLETE via the Original-retry machinery, PRESENTATION-MISMATCHED** — every modern Single attempt carries `mode="original"` (`history_v2_writer.semantic_output_mode` default), so a failed Single's detail view derives `phase="failed"` and its "Retry Original" button IS a same-Generation, immutable-snapshot, new-Attempt retry through `GenerateOriginalService`. No separate generic-retry service/route exists or is needed; what remains is a naming/intent reconciliation decision, not new machinery (§6) |
| Ordinary Single Resume | **MISSING — and the interrupted state itself is unreachable-by-design-today but reachable-by-accident**: no startup sweep marks stale running Singles `interrupted` (the sweep is scoped to modern experiments), so a host restart mid-Single leaves the Generation permanently `running`, which blocks every action via `busyGeneration`/`REUSE_ACTIVE` (§5.C). The architecture already persists replay-capable snapshots for Singles, so a safe canonical design exists if product wants it (§5.F) |
| Single queued/not-started state | **DOES NOT EXIST** — modern Singles are recorded `running` at acceptance; there is no durable queued Single to resume → N/A |
| Canceled → Resume | **INTENTIONALLY UNSUPPORTED** everywhere (canceled cells/attempts are skipped by resume; canceled is not auto-resumed) — matches authoritative semantics |
| Failed → Resume | **INTENTIONALLY UNSUPPORTED** (resume eligibility excludes failed; failed requires retry) — matches authoritative semantics |
| note / favorite | **COMPLETE** (PATCH routes generation+experiment, full UI) — listed here only to close the roadmap inventory |
| downloads / export | **DEFER / NOT PRODUCT CONTRACT (this batch)** — detail shows read-only `export_state`; no export action route exists in the modern surface |
| Settings consumers / stale hardcoded settings reads | **DEFER** to their own Phase-F batch (out of F1 action scope) |

No Phase-E action semantics were found weakened anywhere in the current tree.

---

## 2. Backend route inventory (exact)

### 2.A History V2 surface (`history_v2_routes.py`, all under `/comfymodal/history-v2`)

| Method | Path | Payload | Scope | State prerequisites | State result | Immutable plan source | Same Generation |
|---|---|---|---|---|---|---|---|
| GET | `/feed` | query params (kind/order/cursor/statuses/filters) | mixed feed | none | read-only projection | n/a | n/a |
| GET | `/generations/{id}` | — | Generation | exists | read-only detail (+attempts, snapshot-derived params, outputs) | n/a | n/a |
| POST | `/generations/{id}/original` | optional `{"rerender": bool}` (400 if non-bool) | Generation (Single lane *and* Experiment-cell lane) | replay-capable snapshot; dispatch lane constructible | decision policy: `original_created` / `original_already_active` / `original_already_completed` / `retry_required` (200) · `generation_busy` / `generation_not_reproducible` (409) · `dispatch_unavailable` (503) · 404 | `RequestSnapshot.execution_plan_json` → `validate_replay_capability` → `ExecutionPlan.from_dict` → `build_original_replay_plan` (output-intent-only delta, `validate_replay_delta`) | YES (append-only Attempt) |
| POST | `/generations/{id}/original/retry` | bodyless by contract | Generation | newest `mode="original"` attempt `failed`; NO active attempts; replay-capable snapshot | one new queued Original Attempt; failed Attempt/Preview/assets retained; refusals `retry_not_available` / `generation_busy` / `not_reproducible` | same snapshot pipeline (`create_original_retry_attempt` re-validates inside the transaction) | YES |
| GET | `/experiments/{id}` | — | Experiment | exists | read-only one-card detail incl. per-cell `generation` payloads | n/a | n/a |
| PATCH | `/generations/{id}/favorite` · `/note` · `/featured` | JSON body | Generation | exists / ownership validated | annotation write | n/a | n/a |
| PATCH | `/experiments/{id}/favorite` · `/note` | JSON body | Experiment | exists | annotation write | n/a | n/a |
| GET | `/assets/{id}` | — | Asset | exists; `modal://` proxied via workspace creds (3× retry on FileNotFoundError) | bytes | n/a | n/a |

### 2.B Modern Experiment surface (`experiment_modern_routes.py`, frozen D contract)

| Method | Path | Payload | Scope | Prerequisites | Result | Transaction/idempotency |
|---|---|---|---|---|---|---|
| POST | `/comfymodal/studio/experiment-v2` (+ alias `POST /history-v2/experiments`) | `{experiment_id, name?, definition}` (raw immutable shape rejected) | Experiment matrix | planner available | one-transaction matrix acceptance; `started:false` when no scheduler constructs (durable acceptance, never half-started) | `create_modern_matrix` single transaction; 409 `EXPERIMENT_EXISTS` on create race |
| GET | `/history-v2/experiments/{id}/status` | — | Experiment | exists | flat durable projection (six canonical counts, current-attempt tie-break) | read-only |
| POST | `.../experiments/{id}/start` | — | Experiment | accepted matrix | dispatches registered scheduler; never creates durably | idempotent dispatch |
| POST | `.../experiments/{id}/cancel` | — | Experiment | non-terminal | queued cells → `canceled` atomically (`cancel_queued_attempt` CAS); running cells require a truthful remote-cancel capability else `503 CANCELLATION_UNAVAILABLE` with running state left durable; already-all-canceled → idempotent 200; terminal → 409 | first-wins terminal writes; queued cancel never tied to remote primitive |
| POST | `.../experiments/{id}/resume` | — | Experiment | ≥1 interrupted or queued cell, else 409 `NO_RESUMABLE_CELLS` | live scheduler: interrupted→new attempt identity, queued→claim existing, completed/failed/canceled skipped; no scheduler: durable creation of queued attempts for interrupted cells ONLY (no execution) | `create_resume_attempt` atomic re-check inside transaction (duplicate resume = idempotent skip); scheduler claims atomic first-wins |
| POST | `.../cells/{cell_id}/retry` | — | Cell | current attempt `failed` (409 `CELL_NOT_FAILED` otherwise) | new queued attempt under SAME Generation/snapshot; scheduler dispatch when registered, guarded repo fallback otherwise | `create_retry_attempt` atomic re-check; race loser gets truthful 409 |

Lifecycle: startup sweep marks stale `running` attempts of **modern experiments only** → `interrupted` (idempotent); shutdown marks owned running attempts `interrupted` after best-effort remote stop. **Ordinary Singles are outside every sweep** (§5.C).

### 2.C Supporting repository seams (`history_v2_repository.py`)

- `claim_or_reuse_original_attempt(generation_id, explicit_rerender)` — one `BEGIN IMMEDIATE` transaction implementing the frozen duplicate policy (`decide_original_action`): active→reuse, newest success→reuse, active-preview→busy, failed-only→`retry_required`, else create. Two racing callers serialize; double-submit can never create two active Attempts.
- `create_original_retry_attempt(generation_id)` — busy-guard + `validate_original_retry` (mode/generation/snapshot identity) + append-only insert, one transaction.
- `create_resume_attempt(cell_id)` / `create_retry_attempt(cell_id)` — eligible only when the CURRENT attempt is `interrupted` / `failed` respectively; append-only; reuses the cell's existing Generation ⇒ its immutable request snapshot; `_create_cell_attempt` preserves mode.
- `cancel_queued_attempt(run_id)` — CAS queued→canceled only.
- `claim_attempt(run_id)` — CAS queued→running (`CLAIM_*` outcomes; terminal never reopened).
- `_update_attempt` — SQL predicate `status NOT IN (terminal)` so terminal attempts are never reopened and stale writers never win.
- Derived statuses recomputed in-transaction: `derive_generation_status` (any-attempt precedence), `derive_cell_status` (CURRENT attempt authoritative), `derive_experiment_status` (queued/running→running → interrupted → canceled → completed_with_failures → completed).

---

## 3. Single Generation action matrix

"Single" = ordinary modern workflow run (`POST /comfymodal/studio/run` → `handle_workflow_run_async` → PlaygroundService/V2 writer). Attempt mode is `semantic_output_mode(meta)` ⇒ `"original"` (or `"preview"` when Preview enabled).

| Generation state | Visible action (detail overlay) | Enabled? | Backend call | Resulting semantic |
|---|---|---|---|---|
| completed Preview-only | Generate Original | yes (unless busy) | `POST /original` | new Original Attempt, same Generation, immutable replay |
| completed Original | Generate Again | yes | `POST /original {rerender:true}` | explicit rerender; newest success wins, earlier retained |
| failed ordinary run (mode=original, no usable output) | **Retry Original** | yes | `POST /original/retry` | de-facto generic Single retry: same Generation/snapshot, new original-mode Attempt, failure retained |
| failed Preview-enabled run (mode=preview failed) | Generate Original | yes | `POST /original` | CREATE decision (no successful/active original) → full Original rerun |
| failed Original after prior success | Retry Original | yes | `POST /original/retry` | new Attempt; prior success + Preview retained |
| interrupted ordinary run | *(none — see §5.C)* | n/a | n/a | stale `running` rows are indistinguishable from live ones |
| canceled ordinary run | Generate Original path only | per policy | `POST /original` | canceled is not resumed; a fresh Original may be created by policy (canceled ≠ active) |
| running (live or stale) | Generate Original disabled "Generation busy" | disabled | — | `busyGeneration` guard prevents action spam |
| irreproducible legacy record | "Generate Original unavailable" (after click: server 409 sets persistent note) | disabled | 409 `generation_not_reproducible`, zero writes | truthful unavailability |

There is **no** Single-level Resume, Cancel, or separate "Retry run" control in the UI; the only re-execution actions are the three Generation-scoped Original actions. Feed cards expose no actions beyond favorite/open-detail.

---

## 4. Experiment cell action matrix

Cell actions use the cell's OWN `generationId` and the SAME Generation-scoped routes as Single (E4C parity; one dispatch per action, no browser fanout).

| Cell state | Header-level | Tile/pane action | Backend call | Same-Generation proof | New Attempt semantics |
|---|---|---|---|---|---|
| queued (not started) | Resume visible (if no running cell) | Generate Original (idle phase) | `POST .../resume` → claim existing queued attempt; `POST /original` also possible | resume claims SAME generation's queued attempt; Original appends under cell's generation_id | no duplicate attempt for resume (reuse); Original appends |
| interrupted | Resume visible | Generate Original / (Original actions per attempts) | `POST .../resume` → `create_resume_attempt` (or scheduler path) | new attempt appended to SAME generation (`_create_cell_attempt` reuses generation_id ⇒ snapshot) | fresh `run_` identity, old interrupted attempt untouched, mode preserved |
| failed | Retry-experiment button visible but DISABLED (D5 forbids retry-all) | **Retry** (tile) / **Retry cell** (pane) → `repo.retryCell(expId, cellId)` | `POST .../cells/{cellId}/retry` | `create_retry_attempt` reuses generation/snapshot | append-only; failed attempt retained |
| failed (Original-phase) | — | Retry Original (cell menu/pane) | `POST /generations/{genId}/original/retry` | identical route as Single | append-only Original Attempt |
| completed | — | Generate Again | `POST /original {rerender:true}` | same route | new Attempt; newest wins |
| running | Resume hidden (hasActive) | Generate Original disabled ("Generation busy") | — | — | — |
| canceled | excluded from resume eligibility | — | — | — | intentionally not resumed |

Backend↔frontend mismatches found:
1. **Cancel**: `repo.cancelExperiment` implemented against the frozen route but **never invoked from any History UI module** — History-side cancel is frontend-missing (backend + live experiment-mode controller only).
2. **"Retry experiment"** header button is rendered always-disabled by design (D5: no automatic retry-all) — documented, intentional, not a gap.
3. **Latent defect (untested path)**: `openCellMenu` in `web/studio-history-v2-experiment.js:430` calls `item.focus()` where no `item` binding exists in scope → ReferenceError when a user opens a cell ⋮ menu (menu still mounts; focus step crashes; no test exercises the menu open path — the fake spec drives the pane button). Cosmetic-but-real; flag for the owning UI lane.

---

## 5. Resume-specific audit

**A. Experiment queued-cell Resume — SUPPORTED.** Scheduler path claims the existing queued attempt (`atomically_claim_queued_attempt`, first-wins); route fallback leaves the queued attempt in place for a later scheduler. Tested (`test_resume_submits_only_interrupted_and_never_started`, `test_resume_double_call_no_duplicate_execution`).

**B. Experiment interrupted-cell Resume — SUPPORTED IN-PROCESS / PARTIAL ACROSS RESTART.** Live scheduler: new attempt identity + dispatch. Post-host-restart (registry empty): `POST .../resume` takes the durable-creation fallback — interrupted cells get queued attempts, response reports them as resumed, **but nothing ever dispatches them**: startup lifecycle only sweeps statuses, it does not reconstruct schedulers, and `build_experiment_scheduler` construction does not seed/dispatch (only `start()`/`resume()` on a live instance do; `GenerateOriginalService._ensure_dispatch_lane` reconstructs narrowly for ONE submitted cell). Net effect: a restart-interrupted Experiment can be "resumed" into indefinitely queued cells with a 200 response. This is the sharpest remaining Resume defect.

**C. Ordinary Single interrupted Resume — MISSING, and the state is unreachable-by-sweep but reachable-by-crash.** No code path ever writes `interrupted` for a non-experiment attempt (`interrupted` producers: modern-experiment startup sweep [scoped by `experiment_id IN modern ids`], scheduler shutdown/recovery). A ComfyUI restart mid-Single therefore leaves `status="running"` forever; `derive_generation_status` reports running; the UI shows "Generation busy"; `decide_original_action` returns `REUSE_ACTIVE` for the stale attempt — every action is blocked permanently with no recovery verb. This is simultaneously (a) the reason Single Resume has no state to act on and (b) a durability bug in its own right.

**D. Ordinary Single queued/not-started Resume — N/A.** The state does not exist: modern Singles are persisted `running` at acceptance (`_modern_save_history_success` records `running` then applies `completed`). Nothing to resume.

**E. Canceled Resume — INTENTIONALLY UNSUPPORTED.** `resume()` skips canceled; `list_recoverable_cells` excludes canceled; UI eligibility excludes canceled. Preserved.

**F. Failed Resume — INTENTIONALLY UNSUPPORTED.** `create_resume_attempt` requires current=`interrupted`; scheduler skips failed; UI `historyResumeEligible` excludes failed. Failed goes through Retry. Preserved.

**Feasibility note (no implementation performed):** the architecture already holds everything a canonical Single Resume would need — the exact executed plan is frozen into `RequestSnapshot.execution_plan_json` at success AND failure (`_build_plan_replay_meta` rides on both `record_run` paths), replay validation is generation-scoped and mode-agnostic, and `GenerateOriginalService` already proves the Single dispatch lane end-to-end. The narrowest future design would be: (1) extend the startup sweep to stale running SINGLE attempts → `interrupted` (fixes the durability bug independently), then (2) either reuse `/original/retry`-style append semantics under a resume purpose or simply let the existing Original actions serve (a failed/interrupted Single is already replay-capable). Recommendation ordering in §13.

---

## 6. Retry-specific audit

Three distinct concepts, audited separately:

1. **Retry Original (failed Original Attempt)** — COMPLETE (E4D). Dedicated bodyless route; only newest failed original retryable; append-only; Preview never retried as Original (`retry_not_available`/`generation_busy` refusals tested); failed Attempt + assets retained; frontend posts exactly once per click, never auto-retries on `retry_required`.
2. **Ordinary workflow Retry (failed Single)** — IMPLEMENTED DE FACTO through machinery (1). Because every modern Single attempt is `mode="original"`, the failed-Single case satisfies `create_original_retry_attempt` eligibility exactly (newest original failed, nothing active, snapshot validates). The UI surfaces it as "Retry Original" via `deriveOriginalActionState.phase==="failed"`. It uses the SAME canonical replay infrastructure (`GenerateOriginalService` → `canonical_execution.execute_plan`), preserves exact immutable request data, creates a new Attempt under the same Generation. **What does not exist**: a separately-named generic retry service/route, and any retry affordance for Singles whose snapshots predate plan freezing (those truthfully 409). E3B2 Original replay therefore DOES imply working generic Single retry for all modern snapshots — the inverse of the caution in the brief — but the product label conflates "my run failed, retry it" with "the Original derivative failed, retry it". This is a naming/semantics reconciliation decision for Phase F, not missing infrastructure.
3. **Generate Again (rerender)** — COMPLETE and correctly disjoint: only path that sends `{rerender:true}`; never touches `/original/retry`; newest-success-wins with retention (browser interception test asserts body exactly `{"rerender": true}`).
4. **Experiment cell Retry** — COMPLETE and separate from both above (cell-scoped route, current-attempt-failed guard, same generation/snapshot, scheduler-or-guarded-repo dispatch).
5. **Experiment-level retry-all** — deliberately forbidden (D5); button rendered disabled with explanatory note; `repo.retryExperiment` unavailable placeholder. Preserved.

---

## 7. Generate Original reconciliation (Phase-F status confirmation)

Current tree contradicts nothing; classification stands:

- **Backend canonical**: `POST /comfymodal/history-v2/generations/{id}/original` + `/original/retry` (`history_v2_routes.py:1242,1262`) → `GenerateOriginalService.generate/retry` (`history_v2_replay.py:893,936`) with pre-claim capability validation, pre-claim dispatch-lane construction (no orphan queued), transactional claim (`claim_or_reuse_original_attempt` / `create_original_retry_attempt`), canonical executor `canonical_execution.execute_plan`, required-output persistence before `completed`, newest-original promotion.
- **Frontend canonical**: `repo.generateOriginal[ForCell]` / `retryOriginal[ForCell]` target exactly those routes; detail + cell pane/menu share one state derivation.
- **Retry Original dedicated**: yes (separate route, bodyless, distinct refusals).
- **Generate Again explicit rerender**: yes (`{rerender:true}` only).
- **Single/Experiment parity**: proven — cells carry `generationId`; `_insert_original_attempt` is cell-aware (appends to the cell's attempt list, recomputes cell/experiment derived state); `ExperimentGenerateOriginalTests` prove same service + scheduler reconstruction without orphan attempts.
- **No eager Original fetch**: feed/detail project URLs only; `View Original` is the sole fetch trigger (E6 items 38–39, E7 live proof).
- **Legacy irreproducible gate**: fail-closed 409 with zero writes (`test_legacy_generation_is_irreproducible_and_non_destructive`).

**`Generate Original Phase-F roadmap item = ALREADY SATISFIED BY PHASE E.`**

---

## 8. Action-state source of truth (frontend)

Availability is derived almost entirely from **durable History data**, which is the correct Phase-F direction:

- `deriveOriginalActionState(record)` — reads `record.attempts` (durable attempt list) + featured-output projection; phases idle/active/success/failed + `busyGeneration` from generation status.
- `historyResumeEligible(rec)` / `historyRetryEligible(cell)` — pure functions over durable cell statuses.
- After every action the UI reloads/polls durable state (`getGeneration`/`getExperiment` every 2s, ≤150 ticks) and never invents optimistic Attempts (`reused:true` hydrates the RETURNED run; no client-side Attempt fabrication).
- Repository modes `bridge`/`fixture` are hard-ineligible for Original actions (legacy truthfulness).

Gaps / unsafe-state flags:
1. **Irreproducibility is reactive, not projected.** The detail payload carries no replay-capability signal; `generateOriginalEligibility` can only exclude bridge/fixture and a hypothetical `rec.irreproducible` flag the backend never sends today. A legacy row renders an ENABLED "Generate Original" that fails on click (409 → persistent unavailable note). Truthful, but the browser and durable History disagree until the click. Narrowest fix direction: project a replay-capable boolean onto the detail/feed item (server-side `validate_replay_capability` is cheap and offline).
2. **In-flight guards are per-document, not cross-tab** (`_originalInFlight`, `_inFlightOriginal`, playground `_inflight`). Two tabs can both POST; safety rests entirely on backend serialization (which holds — §10). Acceptable, but should be stated as the designed layering.
3. Favorite-star and per-cell favorite toggles mutate local record state optimistically (annotations only; self-healing on reload; low risk).
4. `DEFAULT_HIDDEN_STATUSES = ["failed","canceled"]` (view-state) hides failed Singles from the default feed — discoverability quirk for the retry flow, intentional per E5D1.

---

## 9. Immutable request semantics (re-execution safety)

Every re-execution action verified against the mutable-state prohibition:

| Action | Plan source | Mutable inputs consulted? | Verdict |
|---|---|---|---|
| Generate Original / Again | `snapshot.execution_plan_json` → raw validation → `ExecutionPlan.from_dict` → round-trip equality check → output-intent-only copy (`validate_replay_delta` allows ONLY `execution_options.output_conversion_options`, `output_intent`, correlation metadata) | NO — workflow/seed/preset/controls/model stack/deployment identity all frozen; workspace resolution prefers immutable `request_metadata.workspace_id`, fail-closed | SAFE |
| Retry Original | same snapshot via `create_original_retry_attempt` + `build_replay_dispatch` | NO | SAFE |
| Experiment cell Retry / Resume | new attempt reuses the cell's Generation ⇒ its immutable RequestSnapshot; scheduler submits the frozen `CellPlan.execution_plan` | NO | SAFE |
| Startup/shutdown sweeps | status-only writes | n/a | SAFE |

No re-execution path reads current Workflow versions, Presets, Settings, or model selections. `test_history_v2_replay_core` additionally proves: no synthesis for legacy rows, mutation-after-preparation cannot rewrite the plan, deployment identity required for production plans, identity cross-source consistency. **No Phase-F blocker.**

---

## 10. Duplicate / race semantics

| Scenario | Frontend guard | Backend transaction/CAS | Scheduler dedupe | Verdict |
|---|---|---|---|---|
| Double-click Retry Original | `_originalInFlight` disables button + early-return | `create_original_retry_attempt`: busy-guard (any active attempt → `generation_busy`) + single-transaction insert | n/a (Single lane background task claims via `claim_attempt` CAS) | SAFE (tested: `test_retry_is_busy_while_attempt_active`) |
| Double-click Resume | button disable during POST | `create_resume_attempt` re-checks CURRENT attempt inside `BEGIN IMMEDIATE`; second caller gets None → idempotent skip | claims atomic first-wins; `test_resume_double_call_no_duplicate_execution` | SAFE |
| Two-tab Generate Original | none (cross-tab) | `claim_or_reuse_original_attempt` serializes on the write transaction; loser receives reuse outcome — `test_concurrent_double_submit_creates_one_attempt`, `test_rerender_race_creates_exactly_one` | active-attempt reuse | SAFE |
| Duplicate rerender | per-page guard | same transactional policy (`explicit_rerender` create is still one-per-transaction; racing rerenders serialize, second sees active) | — | SAFE |
| Claim-vs-cancel race | — | `cancel_queued_attempt` CAS vs `claim_attempt` CAS; `test_claim_cancel_race_does_not_execute_canceled_cell` | cancelled-cells set + queue removal | SAFE |
| Stale terminal overwrite | — | `_update_attempt` SQL predicate `status NOT IN (terminal)`; first-terminal-wins everywhere | `handle_terminal` applies only to current non-terminal attempt | SAFE |

Only residual exposure: cross-tab double-fire produces benign reuse/refusal responses (no duplicates) — no gap requiring work.

---

## 11. Legacy records

- **Viewability**: preserved — legacy/unkeyed rows render via `legacy_run`/`legacy_asset` grouping; sparse failed/interrupted detail renders truthful terminal states (E6 items 40–42).
- **Generate Original / Retry**: unavailable truthfully. Frontend: bridge/fixture modes hard-blocked with the exact message. Backend: missing/mismatched `execution_plan_json` → `409 generation_not_reproducible` BEFORE any deserialization/write, zero Attempt rows (tested). Legacy snapshots with a saved workspace-less plan fall back to the sanctioned active-workspace resolution; unknown saved workspace fails closed (never silent fallback).
- **Experiment Resume/Retry on legacy (non-modern) experiments**: the guarded repo seams operate on any cell rows, but dispatch requires either a registered scheduler or — for Original actions — a snapshot carrying `request.cell_id` (`_experiment_cell_plan`), which legacy rows lack → `503 dispatch_unavailable` rather than reconstruction. Truthful.
- **Unsafe reconstruction**: NONE found. No code path rebuilds requests from current mutable Workflow/Preset to enable actions on legacy rows. Classification: all actions on incomplete-snapshot rows are **unavailable-truthfully**; the only compatibility path is the sanctioned active-workspace fallback for pre-workspace-id snapshots; no unsafe reconstruction exists.

---

## 12. Deterministic coverage map

| Feature | Test module(s) | Key cases | Gap |
|---|---|---|---|
| Replay core / capability | `test_history_v2_replay_core` (12) | valid single+cell snapshots, legacy rejection, round-trip exactness, delta allow-list, deployment identity, retry identity preservation | — |
| Generate/Retry Original backend | `test_history_v2_generate_original` (~34) | preview-only create, double/concurrent submit, rerender race, success reuse, retry_required, busy, irreproducible non-destructive, retry append+retention, execution-failure retention, no-orphan, cell-aware creation, experiment scheduler parity | — |
| E7 reconciliation | `test_e7_followup_reconciliation` (34) | clean first `/original`, workspace precedence A–F/no-leak/no-mutate, collision A–H, ownership, security scope | — |
| Matrix/repository primitives | `test_history_v2_modern_experiment` (repository+route classes) | atomic matrix, retry-resuses-snapshot, CAS double-claim, first-wins terminal, cancel_queued, resume-interrupted-new-attempt-same-generation, resume-skips-failed, retry-only-failed, recoverable order, startup sweep scoping, route cancel/resume/retry incl. 409s | — |
| Scheduler semantics | `test_modern_experiment_scheduler` | resume only interrupted+never-started, double-resume no dup exec, bounded 40-cell resume, retry accumulate/reject, cancel family, shutdown→interrupted | — |
| Frontend contracts | `studio_phase_e4c_generate_original_unit.mjs`, `studio_phase_e4d_original_retry_unit.mjs`, `studio_history_v2_experiment_unit.mjs`, `studio_phase_e_contract_unit.mjs`, `studio_phase_e_wave2_unit.mjs` | route shapes, no-auto-retry, single-call-site (§15 no fanout), state derivation | cell ⋮ menu open path untested (defect §4.3 invisible to gate) |
| Browser (fake) | `studio-fake-phase-e-original.spec.mjs` (15), `studio-fake-phase-e.spec.mjs`, `studio-fake-history-v2.spec.mjs`, wave2 spec | create/reuse/rerender/retry-required/busy/irreproducible/failure/success + cell same-Generation + View-Original-only + sparse states | — |
| Gate totals (authoritative, post-E7) | `python tests/run_studio_tests.py --fake` | Python 1609/0/0/0 · Node 16 files · Fake Playwright 126/126 · exit 0 | — |

Focused read-only executions were NOT needed beyond source inspection: every claim above is pinned by an existing named test in the green E6/E7/Follow-Up-A evidence chain.

Coverage gaps relevant to F1: (a) no test produces an interrupted/stale-running ORDINARY Single (state unreachable in tests too); (b) no test covers plain `/resume` when no scheduler is registered **followed by** an expectation of eventual execution (current behavior: stays queued — unasserted); (c) cell-menu open path (§4.3); (d) no test asserts a replay-capability projection on detail payloads (feature doesn't exist).

---

## 13. Exact remaining Phase-F action work (recommendation — NOT implemented here)

Independent lanes, each bounded, none blocking the others:

**Lane F-RESUME-DURABILITY (highest value, smallest diff).** Extend stale-running recovery to ordinary Singles: at startup, mark `running` attempts belonging to NON-experiment generations older than process start as `interrupted` (mirror `_sweep_stale_running` minus the modern-experiment filter, plus a process-lifetime guard). Fixes permanent "Generation busy" lockout; makes the interrupted state real; zero new routes. Tests: sweep scoping, idempotency, legacy-experiment exclusion preserved.

**Lane F-RESUME-DISPATCH (completes Experiment Resume).** When `/resume` (or `/start`) finds no registered scheduler, narrowly reconstruct the production scheduler from the persisted definition/cell plans (reuse `GenerateOriginalService._scheduler_factory` pattern) and dispatch — or return a truthful machine-readable "queued-not-dispatching" outcome instead of implying resumption. Tests: post-restart resume dispatch, no-second-engine assertion, queued-drain.

**Lane F-RETRY-NAMING (decision + presentation only).** Reconcile the de-facto generic Single retry: either (a) accept "Retry Original" as the canonical failed-Single retry and document it, or (b) relabel conditionally (e.g. "Retry run" when the Generation has exactly one original-mode attempt and no Preview). No backend change required for either option. Include the irreproducibility pre-projection (add a cheap `replay_capable` boolean to generation detail/feed enrichment) so legacy rows render disabled-with-reason instead of failing on click.

**Lane F-HISTORY-CANCEL (parity closure, optional).** Surface Cancel on the History experiment page behind the existing truthful backend semantics (hide when terminal; show `CANCELLATION_UNAVAILABLE` messaging for running-without-primitive), wiring the already-implemented `repo.cancelExperiment`.

**Lane F-UI-DEFECT (trivial fix).** `openCellMenu` undefined `item.focus()` (`web/studio-history-v2-experiment.js:430`) — bind the menu item and focus it, or drop the focus call; add a menu-open unit/browser case.

Explicitly NOT recommended: a separate generic Single-retry service/route (machinery (1) already covers it immutably), any mutable-state reconstruction for legacy rows, weakening canceled/failed resume exclusions, or any change to Generate Original (complete).

---

*Audit-only batch: no deploy, no Modal/GPU/live generation, no commit/push. Worktree dirtiness preserved.*

---

## 14. Implementation Follow-Up A — Durable Resume Backend (2026-08-23)

**Lane:** F1A implementation — closes §5.B/§5.C via §13 lanes F-RESUME-DURABILITY and F-RESUME-DISPATCH.
**Constraints honored:** backend/tests only; no frontend work, no deploy, no Modal/GPU/live generation, no commit/push; unrelated dirty worktree files untouched.

### 14.A What was implemented

| Audit item | Implementation |
|---|---|
| §13 F-RESUME-DURABILITY | `_sweep_stale_running_singles()` in `experiment_modern_routes.py`: at startup, stale `running` attempts with NO experiment/cell identity become `interrupted` (idempotent; terminal/queued untouched); reported as `marked_interrupted_singles`. Ownership boundary = the documented single-host/single-owner `history_v2.db` invariant. |
| §13 F-RESUME-DISPATCH | Post-restart Experiment Resume reconstructs the canonical scheduler from persisted immutable cell plans via `build_experiment_scheduler` under `_SCHEDULER_RECONSTRUCTION_LOCK` (single recovery owner); unavailable reconstruction fails closed with `503 DISPATCH_UNAVAILABLE` and writes NOTHING — no orphan queued attempts. Global concurrency `6`. |
| §5.C Ordinary Single Resume | New canonical route `POST /comfymodal/history-v2/generations/{generation_id}/resume` (bodyless) → `GenerateOriginalService.resume_single()` + guarded `HistoryV2Repository.create_single_resume_attempt()`: interrupted ordinary Singles only; same Generation/snapshot; append-only `BEGIN IMMEDIATE` claim; frozen semantic mode preserved verbatim (`build_resume_replay_plan` — Preview stays Preview, Original stays Original); refusals for active/terminal/legacy/experiment-cell cases. |

### 14.B Independent review reconciliation (oracle review)

Three findings, all fixed and regression-tested:

1. **Blocker — Preview→Original semantic conversion.** Generate Original from a saved Preview plan kept `output_mode="preview"` (ExecutionOptions re-derived preview defaults; assets would type as preview). Fixed: `_original_options` now also sets `output_mode="original"`; `_delta_allowed` permits exactly `execution_options.output_mode` as the intentional Original delta; Resume still never touches mode. Regression: `test_generate_original_from_saved_preview_plan_executes_as_original`.
2. **High — partial-scheduler reconstruction.** Reconstruction accepted any non-empty subset of persisted plans. Fixed: `_persisted_cell_plans` is fail-closed — non-list/empty cells, malformed entries, duplicate IDs, ID-set mismatch vs durable cells (missing or extra), or a queued/interrupted cell without a mapping `execution_plan` → no scheduler, before any factory call or attempt write. Five focused fail-closed tests cover missing/extra/duplicate IDs and queued/interrupted-without-plan.
3. **Medium — Resume accounting race.** Baseline attempt IDs were captured outside the reconstruction lock, so concurrent Resumes could double-report an appended attempt. Fixed: durable detail re-read, baseline capture, dispatch, and after-ID diff all occur inside one `_SCHEDULER_RECONSTRUCTION_LOCK` section; response fields unchanged.

Boundary caveat accepted: the sweep relies on the single-ComfyUI-owner-per-database invariant; no cross-process ownership lock exists (documented design).

### 14.C Scope note (explorer scope audit)

The shared worktree intentionally remains dirty with pre-existing E40/R41/E6/E7/F2–F4, web/, Modal/GPU-runtime, and config changes (64 tracked files + untracked artifacts). F1A's own footprint is limited to: `history_v2_repository.py`, `history_v2_replay.py`, `history_v2_routes.py`, `experiment_modern_routes.py`, `experiment_modern_scheduler.py` (factory/registry), `tests/test_f1_followup_a_durable_resume.py`, `tests/test_history_v2_generate_original.py`, `tests/test_history_v2_modern_experiment.py`, `tests/run_studio_tests.py`, and this document. No cleanup/separation was performed; consumers of this evidence must not treat the full `git status` as F1A scope.

Single Resume is explicitly **backend-only** in this batch: no frontend control was added or required by the F1A contract.

### 14.D Final evidence

- Combined focused run (final state): `python -m unittest tests.test_history_v2_generate_original tests.test_f1_followup_a_durable_resume tests.test_history_v2_modern_experiment tests.test_history_v2_replay_core` → **Ran 124 tests — OK** (35 + 30 + 46 + 13).
- Full Studio gate (pre-review baseline, unchanged tree regions): `python tests/run_studio_tests.py --fake` → exit 0, Python 1636/0/0/0 (wrapper summary truncated by shell timeout; captured in tool-output log).
- `py_compile` clean on both changed production files and both changed test files.

**F1A verdict: §5.B and §5.C are CLOSED. History actions are COMPLETE for Retry / Resume / Generate Original / Generate Again at the backend contract level; remaining open items are the presentation/naming lane (§13 F-RETRY-NAMING), optional Cancel surfacing (F-HISTORY-CANCEL), and the trivial UI defect (F-UI-DEFECT) — none blocking.**

---

## 15. Implementation Follow-Up B — F6 Frontend Reconciliation (2026-08-23)

**Lane:** Batch F6 — History V2 frontend. Closes the two remaining F1 frontend items (§13 F-RETRY-NAMING and Single Resume UI; F-HISTORY-CANCEL was already closed by F1B, F-UI-DEFECT by F1B).

| F1 item | Resolution |
|---|---|
| §13 F-RETRY-NAMING | **Closed.** `deriveRetryActionLabel` (web/history-v2-repository.js) conditionally presents "Retry run" for a plain failed ordinary Single (no successful Preview history, no prior Original success, no retained usable Original asset) vs "Retry Original" for the explicit derivative lifecycle — durable attempts/assets only. Both dispatch the unchanged bodyless `/original/retry`; no new retry route. |
| Ordinary Single Resume UI (§5.C/§14) | **Closed.** Detail Actions renders Resume only for durably `interrupted` ordinary Singles via `deriveSingleResumeState` + one bodyless `repo.resumeGeneration` POST to the frozen F1A route; durable refetch/poll only (no optimistic Attempt, no local interrupted→running flip); structured refusals recover the control. |
| §8.1 irreproducibility reactive-only | **Frontend half closed.** Normalization now threads `irreproducible` and tolerantly consumes F5's `replay_capable` projection (explicit false → disabled-with-reason before click; absent → POST stays authoritative). Backend projection itself remains F5's lane. |

Evidence: `PHASE_F6_HISTORY_FRONTEND_ACTIONS_DOWNLOAD_2026-08-23.md` (unit 6/6, browser 7/7, focused history specs 67/67; wrapper python 1682/0, node 21/0).

---

## 15. F5 Backend Truth Reconciliation — Replay Capability Projection

**Lane:** Phase F batch F5 — History V2 backend projection/filter truth (closes §8 gap 1, the reactive-irreproducibility defect). Constraints honored: backend/tests/docs only; no frontend JS, no GPU/runtime, no export, no deploy/Modal/live generation, no commit/push/branch/reset.

### 15.A What was implemented

| Item | Implementation |
|---|---|
| Canonical capability reuse | New read-only helper `_replay_capability_fields(snapshot, generation)` in `history_v2_routes.py`. It calls the EXISTING authoritative `history_v2_replay.load_replay_plan` — the exact validator gating Single Resume, and a strict superset of the raw `validate_replay_capability` gate used by Generate Original / Retry Original. No second approximation was invented; execution behavior of `history_v2_replay.py` is untouched. |
| Projected shape | `replay_capable: bool` always; `replay_unavailable_reason: <stable machine code>` only when false. Reason codes are the validator's existing constants (`missing_request_snapshot`, `missing_execution_plan`, `snapshot_hash_mismatch`, `missing_deployment_identity`, `identity_mismatch`, …). Validator `details`, raw exceptions, workspace identifiers, and credentials are never exposed. |
| Surfaces | Generation detail item, every generation feed item (`_generation_feed_item` via `_build_generation_items`), and Experiment-detail cell-generation payloads (`_cell_generation_payload`). Single and cell payloads share one helper on the same `GenerationDetail`, so they cannot disagree for the same Generation. |
| Semantic contract | `replay_capable=true` means ONLY: the saved immutable request passes canonical replay validation (raw validation + exact plan round-trip). It is NOT a promise about current Workflow/Preset existence, an Original existing, workspace credentials, dispatch availability, or execution success. Status eligibility stays separate (a completed Single projects capable=true while Resume refuses 409 `resume_not_available`; pinned by test). |
| Legacy rows | Remain viewable; project `replay_capable=false` with truthful stable reasons; nothing synthesized from current mutable state; records never mutated by projection. |

### 15.B Tests (`tests/test_f5_history_backend_truth.py`, new — 29 tests)

Replay-capability lane pins all ten required cases: modern completed/failed/interrupted Singles → true (detail AND feed); missing snapshot → false `missing_request_snapshot`; empty saved plan → false `missing_execution_plan`; tampered plan hash → false `snapshot_hash_mismatch`; stripped deployment identity → false `missing_deployment_identity`; explicit unknown saved workspace → still true (capability ≠ credential availability; dispatch preflight remains the POST-time gate) with zero credential material in projected fields; Experiment-cell parity true/true and false/false with matching reasons; full-table dump equality proves projection performs zero writes; legacy row projects false AND `POST /original` still fails closed 409 `generation_not_reproducible` with zero Attempt writes.

### 15.C Evidence

- Focused: `tests.test_f5_history_backend_truth` → **29/29 OK**.
- Regression: `test_history_v2_repository + test_history_v2_api + test_history_v2_replay_core + test_history_v2_generate_original + test_f1_followup_a_durable_resume + test_studio_history_v2_js` → **169 OK**; `test_history_v2_modern_experiment + test_modern_experiment_scheduler` → **96 OK**.
- Full wrapper `python tests/run_studio_tests.py --fake`: **python run=1642 fail=0 error=0 skip=0** (includes this batch's tests). Node-unit (6 files) and fake-playwright (~27 specs) failed AT WRAPPER TIME on a concurrent frontend defect owned by another lane: `web/history-v2-repository.js:1385` declares `_v2ResumeGeneration` twice (SyntaxError breaks every spec/unit importing that file). Several of those units pass when re-run directly minutes later; per ownership rules this lane did not touch frontend files. The fake browser lane never imports Python routes, so these failures are unrelated to F5 backend changes.

**Files modified by THIS lane:** `history_v2_routes.py`, `history_v2_repository.py`, `history_v2_store.py` (one idempotent index, see F2 doc §F5), `tests/test_f5_history_backend_truth.py` (new), this document, and the F2 audit document. Deploy/live/GPU/generation/commit/push: NONE.
