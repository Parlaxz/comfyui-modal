# PHASE H FINAL CLOSURE (2026-08-25)

**Batch type:** H21 = final Phase-H closure / independent verification / reconciliation / documentation. READ-ONLY against production code and tests. No deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/revert/stash/clean; the working tree remains intentionally dirty and untouched beyond documents.
**Files modified by this batch:** `PHASE_H_FINAL_CLOSURE_2026-08-25.md` (this document), `PHASE_H_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-25.md`, `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (H5 FOLLOW-UP G appendix only).
**Inputs read completely:** the H5 contract freeze incl. Follow-Ups A–F, H5A/H5B/H5C/H5D evidence reports, H6–H20 wave reports, Phase-F and Phase-G final closure handoffs.

---

## 0. FINAL VERDICT

## `PHASE H COMPLETE`

Every closure precondition is independently re-measured and green: final deterministic gate green on the closure tree, all seven waves reconciled to a completion ledger, no architectural duplication remains, no meaningful deterministic Studio test debt remains unregistered, zero UNKNOWN invariant/status/classification rows, remaining hygiene explicitly non-blocking, route-pruning decision explicit (`NOT REQUIRED`), Phase-I boundary explicit, zero-context handoff complete.

---

## 1. FINAL GATE (authoritative, run once on the closure tree)

```
python tests/run_studio_tests.py --fake
  python             run=2124  fail=0    error=0    skip=0
  node-unit          run=25    fail=0    error=0    skip=0
  fake-playwright    PASS      (wrapper aggregate)

npx playwright test --config=playwright.fake.config.mjs --reporter=line
  run 1: 210 passed / 1 failed   — KNOWN FLAKE ×1
         (studio-fake-lifecycle.spec.mjs test 11 "workflow node progress is not
          overwritten by sampler max", 30 s wait timeout under full-suite
          parallel load; identical signature to FD-1/FF-2/H20 §22)
  run 2 (immediate direct rerun): 211 passed / 211 — GREEN
```

Known-flake occurrence count this batch: **1** (classified with existing evidence; no timeout/assertion weakened; passes in isolation and on direct rerun). This triple — **Python 2124 · Node-unit 25 files · Fake Playwright 211 exact** — is the FINAL Phase-H deterministic gate and supersedes all prior baselines (1991 → 1941 → 1945 → 1974 → 2010 → 1824 → 2124).

Independent collection proof: the runner builds its suite fresh from the explicit allowlist every invocation; the python lane measured 2124 both by count and by green execution.

---

## 2. FINAL ARCHITECTURE (all statements re-verified against current source)

### 2.1 Product IA — five surfaces, exactly

`web/studio-shell.js` `PAGES` = **Playground | History | Workflows | Backend | Settings** (verified :18–24). No other top-level modern page exists. No user-reachable legacy Dashboard/Setup/Profiles/Results/Settings, Comparison Profiles/Runner, old A/B slider, or standalone legacy settings overlay: all nine legacy module files are deleted from disk (H18), `studio-legacy.js` is gone, `experimentRunSurface()` returns `"modern"` unconditionally, `open_comfymodal_settings`/`mountSettingsPanel`/Comparison overlay globals have zero definitions in `web/`, and the only opener surface is `ALIAS_PAGE_MAP` (7 aliases) which lands exclusively on modern pages (dashboard→backend, setup→playground+Experiment context, profiles→playground+deprecation, results/history→history, settings→settings).

### 2.2 Surface ownership (frozen table)

| Surface | Owns |
|---|---|
| **PLAYGROUND** | compose/run Single; compose/run Experiment (experiment-v2); immediate progress/result; Workflow/Version/Preset selection for execution; contextual recent-run filmstrip (History-V2-backed); lightweight selected-run actions (favorite/note/save/duration). |
| **HISTORY** | sole durable History V2; generation/experiment detail; replay/retry/resume/original semantics; durable favorite/note; download/export; diagnostics/timing. |
| **WORKFLOWS** | Workflow library; immutable Versions; Mapping; Workflow Presets; model dependencies; Model Library + custom-node dependency surfaces; Model Compatibility (distinct concept); Portability (Phase-G freeze intact); manifest import/export. |
| **BACKEND** | Modal workspaces/account; deployment/redeployment; runtime/readiness; logs; credentials; snapshots; repair; Backend/Runtime Presets (transitional owner). |
| **SETTINGS** | preferences ONLY: GPU default, Preview, outputs, History layout, interface, tracing level. |

Residual Settings ▸ Advanced "Runtime & Backend" informational rows (Deploy state, Snapshots count, Presets count, Open-Backend link) = **OPTIONAL_G_HYGIENE**, not architectural authority (read-only consumers of live authorities; the Backends count row was already removed by H16).

### 2.3 Execution authority — `MODERN_STUDIO_EXECUTION = MODAL_V2_ONLY`

Verified across Single (`handle_studio_run_async` → retired-mode guard → `playground_adapter_direct_run`), Workflow (unconditional `_workflow_v2_run`; `_workflow_legacy_run` deleted), Experiment (`_schedule_and_start` → `V2ExperimentInvoker` only), canvas Cloud (`build_execution_plan` → `execute_plan`, retired-request 400 pre-enqueue). No reachable modern V1 execution, no Shadow execution, no generic provider selector, no Local Studio engine. Retired strings (`v1`/`legacy`/`shadow`) survive only for recognition, rejection (`EXECUTION_MODE_RETIRED`), migration (`_migrate_persisted_execution_mode`), and truthful diagnostics; env vocabulary collapsed to `{v2}`; executable mode outcome is always V2.

### 2.4 ExecutionPlan authority — one production caller chain

Production callers of `modal_client.run_prompt_stream`: **exactly one — V2 `ModalTransport`** (`comfymodal_runtime/modal_transport.py`), plus the standalone dev probe `probe_modal_prompt.py`. Chain: user action → immutable accepted request → WorkflowVersion/Mapping/Preset resolution as applicable → ExecutionPlan → `execute_plan` → ModalTransport → `run_prompt_stream`. All eight former dead helpers (`_execute_comparison_profile`, `direct_studio_run_completion`, `execute_modal_prompt`, `prepare_modal_execution`, `LocalRemoteInvoker`, `_prepare_studio_run_context`, `_handle_studio_run_scheduler`, `_playground_runtime_mode`) have zero production definitions (deleted H19). No blocker.

### 2.5 GPU authority

Server-authoritative canonical catalog/default; GPU captured/frozen into the accepted plan at acceptance (`request_metadata.selected_gpu`); later Settings changes never mutate accepted plans; replay/resume/retry never reread current GPU; canvas compatibility startup read is not a second Studio writer. F8 coverage green in-gate (`tests.test_f8_gpu_authority` 41/41 inside the 2124).

### 2.6 History authority — `HISTORY_V2 = SOLE_DURABLE_MODERN_HISTORY`

Replay authority = `RequestSnapshot.execution_plan_json` (+ copied provenance). No live lookup from History render/replay into mutable current Workflow/Version/Mapping/Presets/Model Library/compatibility/portability cache; the single sanctioned external resolution remains the old-snapshot active-workspace fallback. Irreproducible historical records remain truthfully irreproducible (`replay_capable=false`); no destructive migration occurred in any H wave; History survives deletion of all old product UI.

### 2.7 Workflow authority

Workflow → immutable WorkflowVersion → immutable Mapping → version-scoped WorkflowPreset(s) → accepted ExecutionPlan. No PortableWorkflow duplicate authority, no second graph store, no provider-specific copies, no ZIP authority. Manifest import/export follows Phase-G exactness rules (round-trip suites green in-gate); portability advisory/non-execution; Compatibility distinct from Portability.

### 2.8 Preset taxonomy (final, three distinct authorities)

| System | Store/routes | Status |
|---|---|---|
| Workflow Presets | `.studio_workflow_presets.json` via `/studio/workflows/*/presets*` | MODERN_LIVE, Workflows-owned, version-scoped |
| Backend/Runtime Presets | `.studio_presets.json` via `/studio/presets*` | **MODERN_LIVE_TRANSITIONAL** — consumed by Playground runtime selection, Backend tab, wizard; intentionally NOT converged during H; convergence remains a future explicit architecture decision |
| Legacy prompt/image presets | `.presets/prompts\|images` | reads COMPAT_READ ×4; writes RETIRED_WRITE ×8 (409 `LEGACY_PRESETS_READ_ONLY`); UI retired |

### 2.9 Comparison final state

UI absent (files deleted), execution absent (410 `COMPARISON_RETIRED`, body unparsed), no modern Comparison domain, no slot-path mutation flow, old A/B slider absent. Server compatibility: 10 COMPAT_READ routes answer stored data; 6 writers inert (409 `COMPARISON_READ_ONLY`); `/comparison/run` RETIRED_EXECUTION. Physical route deletion = optional future-major work. A/B image compare = Phase I.

### 2.10 Legacy Experiment final state

Modern `experiment-v2` is authority (`POST /studio/experiment-v2` MODERN_LIVE). Legacy creation/execution writers inert (10× 410 `EXPERIMENT_RETIRED`, 5× 409 `EXPERIMENT_READ_ONLY`); old-data readers retained (5 COMPAT_READ); compile stays pure-compute ZERO_CALLER per FD-12. Protected seams survive byte-untouched: `GET /experiments/{id}` (:5521) and `POST /experiments/{id}/stop-now` (:5912) — these are the Single path's wired progress-poll/cancel transport (implementation seam, `TRANSITIONAL_MODERN`, `WAVE_F_DO_NOT_FREEZE=TRUE`), NOT a second modern Experiment product authority.

### 2.11 Run-history final state

COMPAT_READ ×4 (list/detail/logs/timing) · COMPAT_WRITE ×2 (`PATCH .../annotations` :6395, `POST .../save` :6456). The write pair is still live because fresh direct-run result panels and stale persisted `results.v1` selections lack `_historyKind` and fall through to them — freezing would break Playground favorite/note/save today. The entire family is NOT read-only. Retirement condition (frozen FD-4): tag direct-run records as History-backed (or resolve runId→V2 generation) AND decide/expire the stale persisted population; once zero callers remain, a later wave may freeze.

### 2.12 Canvas compatibility

Retained and structurally/test-proven: `/prompt` interception (fetchApi patch → `${MODAL_PREFIX}/prompt`), Local pass-through gated by `comfymodal_enabled`/`window._comfyModalEnabled` (startup shim in minimal `modal-settings.js`; readers `!== false` at modal-node.js :678/:841), Cloud V2-only path, output-option chain (`window._comfyModalOutputOptions`), Production mode. None exposed as modern Studio execution choices. Canvas retirement is OUTSIDE Phase H.

### 2.13 Backend authority

Modern Backend owns workspace identity/lifecycle, deployment/redeployment, readiness/runtime, logs, credentials, snapshots, repair, Backend Presets. `/studio/backends` is none of: provider registry, modern Backend authority, portability matrix. Writers inert (409 `BACKENDS_READ_ONLY` ×4); GET hidden COMPAT_READ shim; modern frontend consumers 0.

### 2.14 Model Library ownership

Workflows Model Library owns model presence/dependency truth, custom-node registry/dependencies, click-gated install-request behavior. Legacy raw installer UI, bulk duplicate installer UI, Models/Sync legacy UI gone (files deleted H18). Operational swap/deployment behavior remains Backend.

### 2.15 Settings final contract

No Run mode, no execution engine selector, no legacy UI group, no legacy settings overlay, no Backends count row, no workspace writer, no deployment controls, no provider selector. Reset All POSTs `{gpu: defaultGpu}` (+ tracing off via its own route) — never touches workspace/deploy state, never writes `comfymodal_enabled`, never forces execution mode.

---

## 3. API-FREEZE MATRIX (final; re-verified census, UNKNOWN = 0)

| Family | Final classification |
|---|---|
| Comparison (17 routes) | COMPAT_READ ×10 · RETIRED_WRITE ×6 · RETIRED_EXECUTION ×1 |
| run-history | COMPAT_READ ×4 · COMPAT_WRITE ×2 |
| `/studio/backends` | GET COMPAT_READ · writers ×4 RETIRED_WRITE · modern frontend callers 0 |
| Warmup | status ZERO_CALLER · run RETIRED_EXECUTION (410) · invalidate RETIRED_WRITE (409) |
| auth/setup | RETIRED_WRITE (409 `AUTH_SETUP_RETIRED`) |
| Legacy prompt/image presets | reads COMPAT_READ ×4 · writes RETIRED_WRITE ×8 |
| Backend/Runtime Presets | MODERN_LIVE_TRANSITIONAL (full CRUD live) |
| Legacy Experiment (22+1 routes) | TRANSITIONAL_MODERN ×2 PROTECTED · COMPAT_READ ×5 · ZERO_CALLER ×1 (compile) · RETIRED_EXECUTION ×10 · RETIRED_WRITE ×5 · MODERN_LIVE ×1 (experiment-v2) |

Freeze-code census re-counted in `__init__.py`: COMPARISON_READ_ONLY ×6 · COMPARISON_RETIRED ×1 · EXPERIMENT_RETIRED ×10 · EXPERIMENT_READ_ONLY ×5 · WARMUP_RETIRED ×2 routes (+1 docstring) · AUTH_SETUP_RETIRED ×1 · BACKENDS_READ_ONLY ×4 · LEGACY_PRESETS_READ_ONLY ×8 — exact match to H15/H17/H20.

---

## 4. DATA IMMUTABILITY

No Phase-H cleanup destructively removed any historical store. Verified preserved by contract + registered hash-sweep tests: history_v2 DB, RequestSnapshots, `.run_history`, old `.experiments`, Comparison stores, `.studio_presets.json`, legacy `.presets`, `.studio_backends.json`, Workflow domain stores, workspace registry, portability cache, old assets. This closure audit mutated no user data (source/tests/fake fixtures only).

---

## 5. TEST AUTHORITY (re-measured)

- Python registered: **2124** (40 STUDIO_PY_MODULES + 5 PYTEST_STYLE_FILES; runner allowlist verified).
- Node unit files: **25** (NODE_UNIT_FILES verified).
- Fake Playwright: **211 exact** (direct config run).
- Statement re-proven: **meaningful current deterministic Studio suite simply unregistered = ZERO.**

Remaining unregistered categories (no UNKNOWN):
- **KEEP_FOCUSED_ONLY:** `test_experiment_runner` (73, legacy scheduler chain + CheckpointStreamInvoker units), `test_canonical_execution`, `test_run_prompt_options`, `test_warmup_profile_dedup`, `test_restore_timing_data_flow`, `test_production_*` (V2 plan/dispatch infra), `test_comfyapp_ast/packaging` (deploy infra), `test_workstream_e_patches` (buffer units; retirement half redundant in-gate), `test_studio_workflow_manifest` + `test_studio_workflow_run_plan_identity` (identity matrix duplicated by registered workflow-run-integration + F8 pins), `test_history_index` (covered via registered run-history family), `test_experiment_modern_*` family (end-to-end authority in-gate via history_v2_modern_experiment + routes_registered), `test_deploy_no_auto_generation` (forbidden-symbol list incl. H19 names).
- **REDUNDANT:** `test_modal_settings_gpu_config` (same contract pinned behaviorally by registered settings-compat + F8 units).
- **NON_STUDIO:** ~200 `test_v2_*` / `test_runtime_*` / benchmark / v2ctl modules (runner charter).
- Browser `.mjs` harnesses under tests/browser = fake-lane/runtime internals.

---

## 6. WAVE COMPLETION LEDGER (exact; no wave "mostly complete")

| Wave | Batches | Key result | Final status | Superseding follow-up |
|---|---|---|---|---|
| **A** (Backend re-home, Model Library parity, experiment fallback closure) | H6 (A1+A2), H7 (A3), H8 (A4) | Modern Backend operationally complete (workspaces/deploy/credentials/repair); Model Library parity closed (C1–C4 gaps landed, 18 legacy ops classified); Playground can no longer create legacy experiments | COMPLETE | FA-1..FA-8 (registry export/import dissolved as non-capability; warmup RETIRE accepted; auth/setup not-required-parity) |
| **B** (dead surfaces, redirects, dead mode helpers) | H9, H10, H11 | Orphaned History-V1 frontend + Legacy Dashboard/History tabs deleted; 7 alias redirects to modern owners; hidden sidebar registrations removed; `is_v2`/`is_shadow` deleted | COMPLETE | FB-1..FB-7 (baseline 1941/21/199 frozen) |
| **C** (V2-only execution consolidation) | H12 | V1/shadow branches deleted everywhere; persisted v1→v2 migration; env vocabulary `{v2}`; Run mode + engine selectors removed; Reset `{gpu}`-only | COMPLETE | FC-1..FC-21 (V2-vs-orchestration semantic freeze; protected Single seams classified) |
| **D** (recent-runs migration, legacy creator migration) | H13 | Recent-runs hydrates solely from History-V2 feed; legacy grid/poller/reopen deleted; Setup/Results creators retired with zero POSTs | COMPLETE | (covered by FC) |
| **E** (legacy Settings retirement, Comparison retirement) | H14 | Settings Legacy group + standalone overlay + 4 legacy tabs removed; Comparison UI/globals/canvas menu removed; `/comparison/run` → bounded 410 | COMPLETE | FD-1..FD-26 (route-class vocabulary; COMPAT_WRITE correction; presets exclusion) |
| **F** (compatibility/API write freeze) | H15 (F-SRV), H16 (F-BE), H17 (F-TST) | All RETIRED_WRITE/EXECUTION targets inert with exact 409/410 classes, hash-proven zero mutation; Settings Backends consumer removed; H15 suite registered | COMPLETE | FE-1..FE-8 (Wave F COMPLETE verdict) |
| **G** (frontend deletion, Python deletion, test consolidation) | H18, H19, H20 | 9 frontend files deleted; modal-settings.js → 115-line compat module; 7 dead helpers removed; 8 Python symbols deleted; registrations completed to 2124/25 | COMPLETE | FF-1..FF-10 (residue map FF-8; route pruning FF-9) |

---

## 7. INVARIANT MATRIX (H5 §28 + inherited F/G; final status)

All 26 H5 §28 invariants: **PASS** (each carries ≥1 authoritative registered family per H20 §20 / FF-6 matrix; spot-re-verified this batch: five-page shell, V2-only dispatch, plan immutability, replay authority, no-live-lookup, irreproducibility truthfulness, no destructive migration, workspace fallback, Settings-preferences-only, Backend-operational, Workflows ownership, History sole authority, two-surface Experiments, Comparison retirement, canvas compatibility, old-reader survival, UI-retirement≠store-deletion, no new legacy writes, Compatibility≠Portability, derived non-gating portability cache, GPU server-authority + freeze, replay never rereads Settings, V2-only post-C, A/B slider Phase-I, `.studio_presets.json` live).

Inherited Phase-F §7 invariants (14): **PASS** (immutable plan replay, durable action-state authority, managed assets, export separation, bodyless download/export contracts, append-only attempts, resume/retry distinctions, GPU freeze, concurrency 6, no browser fanout, per-asset export locking).

Inherited Phase-G §37 invariants (28): **PASS** (WorkflowVersion analysis unit, one graph authority, manifest-v1 sole artifact, exact JSON round-trip, dry-run-first atomic import, UNKNOWN-never-LOW, six target ids advisory, derived TTL-free fail-open cache, environment isolation, secrets/local-path refusal, graph-hash identity rule).

**SUPERSEDED rows:** none required — the only historical statement superseded during H was H14's interim "run-history annotations/save READ_ONLY_COMPAT (shrinking)", superseded BY CONTRACT FD-4 (COMPAT_WRITE), which is itself recorded as authoritative. No invariant ends Phase H as UNKNOWN.

---

## 8. OPTIONAL HYGIENE (frozen, NOT implemented)

| Item | Current callers | Why non-blocking | Disposition |
|---|---|---|---|
| `handle_studio_experiment` | zero production (route 410-inert before handler); F8-test seam | dead behind inert route; test migration required first | OPTIONAL_DELETE (with coordinated test migration) |
| `build_single_run_spec` | production-orphaned; pinned by registered compilation suites | de-pin registered suites first | OPTIONAL_DELETE (with test migration) |
| `__init__._collect_input_images` | zero production; dedicated unregistered suites test it directly | live V2 twin exists in canonical_execution | OPTIONAL_DELETE (migrate tests to twin) |
| `createScopedTracker` export | zero production consumers (module/browser harnesses only) | harmless export | OPTIONAL_DELETE |
| MARK_OPTIONAL legacy span naming | trace-data vocabulary only | historical trace summaries stay readable | KEEP_COMPAT |
| Registered-and-inert compatibility routes (~40) | bounded truthful 409/410 responses; registry pins valid | maintenance/security cost negligible; old-client truthfulness benefits | FUTURE_MAJOR_API (KEEP_INERT_COMPAT now) |
| Residual Settings Runtime & Backend informational rows | read-only consumers of live authorities | display-only; Backends row already removed | OPTIONAL_G_HYGIENE (group removal later debt) |
| `_schedule_and_start` + legacy Scheduler/Runner chain | inert behind retired routes; sole construction site of mandated `V2ExperimentInvoker` | pinned seam | FUTURE_ARCH_DECISION (bundle with route pruning) |

---

## 9. ROUTE-PRUNING FINAL DECISION

Re-verified against H20 FF-9 factors: handlers are bounded/non-mutating; maintenance/security cost negligible; old-client truthfulness benefits from explicit 409/410; no duplicate product authority exists; registry pins and fake-mirror parity stay valid without deletion cascades.

**`PHASE_H_ROUTE_PRUNING_REQUIRED = NO`**

Physical deletion remains optional future-major work (`DEFER_FUTURE_MAJOR`), bundled where applicable with the `_schedule_and_start`/invoker-chain disposition. No routes were deleted in H21.

---

## 10. PHASE-I BOUNDARY (restated; nothing implemented)

Deferred Phase-I list (H5 §29 + follow-ups): lightweight A/B image slider (History/Experiment result space); navigation/accessibility polish (`aria-current`, keyboard semantics); responsive nav redesign; heading hierarchy cleanup; generic loading component; chip visual taxonomy (incl. portability-vs-compatibility distinction); wording/verb polish; URL/deep-link routing infrastructure; focus-visible polish; cross-tab state sync; deeper model/custom-node entry links.

Distinctions:
- **PHASE_I_PRODUCT_WORK** — the list above (new UX capability/polish).
- **OPTIONAL_G_HYGIENE** — §8 items (cleanup that does not need to precede Phase I).
- **FUTURE_MAJOR_API** — physical route pruning + preset-convergence decisions requiring their own contracts.

---

## 11. NEXT-PHASE ENTRY STATE

A fresh agent may safely assume: one modern Studio architecture; no legacy UI authority; V2-only modern execution; History V2 durable authority; Workflows domain authority; Backend operational authority; Settings preferences-only authority; compatibility routes deliberately retained; all deterministic gates green (2124/25/211).

Deliberately transitional items that still matter (NOT bugs): Backend/Runtime Presets (MODERN_LIVE_TRANSITIONAL); run-history COMPAT_WRITE pair; protected Single experiment detail/stop-now seams; canvas compatibility layer.

Full detail: `PHASE_H_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-25.md`.

---

## FINAL VERDICTS

`PHASE H COMPLETE`

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / revert / stash / clean by this batch: **NONE**.
