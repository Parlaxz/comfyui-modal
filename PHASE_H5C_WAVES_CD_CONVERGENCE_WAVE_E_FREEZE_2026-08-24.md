# PHASE H5 FOLLOW-UP C — WAVES C/D CONVERGENCE, LEGACY-ROUTE CLASSIFICATION & WAVE-E ENTRY FREEZE (2026-08-24)

**Batch type:** H5 contract follow-up / same-batch Waves-C/D reconciliation. READ-ONLY against production code and tests. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset/stash/clean. The working tree was intentionally dirty (H12 Wave C + H13 Wave D both landed uncommitted in the shared tree). Files modified by this batch: `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (appended "H5 FOLLOW-UP C" section — AUTHORITATIVE) + this document.
**Inputs read completely:** H5 contract freeze incl. Follow-Ups A/B, `PHASE_H5A_WAVE_A_OPERATIONAL_RECONCILIATION_2026-08-24.md`, `PHASE_H5B_WAVE_B_CONVERGENCE_2026-08-24.md`, `PHASE_H12_V2_ONLY_EXECUTION_CONSOLIDATION_2026-08-24.md`, `PHASE_H13_RECENT_RUNS_HISTORY_V2_AND_LEGACY_EXPERIMENT_RETIREMENT_2026-08-24.md`, `PHASE_H3_REFERENCE_INTEGRITY_HISTORICAL_COMPATIBILITY_AUDIT_2026-08-23.md`. The current shared tree was inspected directly (route registrations, handlers, frontend call graphs re-traced from source), not merely the reports.

---

## 0. VERDICT

`H5 FOLLOW-UP C COMPLETE — WAVES C AND D CONVERGE GREEN ON THE SHARED TREE; V2 EXECUTION IS DISTINGUISHED FROM SCHEDULER-ROUTE NAMING; THE LIVE SINGLE-RUN POLL/CANCEL SEAMS ARE CLASSIFIED TRANSITIONAL_MODERN AND ARE WAVE-E-PROTECTED; COMPARISON EXECUTION HAS ONE FROZEN DISPOSITION; SETTINGS LEGACY REMOVAL GATE = YES. WAVE E READY.`

---

## 1. AUTHORITATIVE POST-C/D SHARED-TREE GATE (measured by this batch, sole baseline going forward)

```
python tests/run_studio_tests.py --fake
  python             run=1945  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    PASS      (npm wrapper aggregate run=1)

npx playwright test --config=playwright.fake.config.mjs --reporter=line
  211 passed / 211   (direct count; wrapper does not expose counts)
```

**POST-WAVES-C/D BASELINE (2026-08-24): Python 1945 · Node-unit 21 files · Fake Playwright 211.**
Supersedes FB-7's post-Wave-B 1941/21/199 as the Wave-E entry baseline. Delta vs post-B: +4 Python and +12 fake, exactly as accounted by H12 §14 / H13 §10 (H12 in-gate additions + test rewrites; H13's new 12-test recent-runs spec). No unexplained drift; no ledger required beyond the two writer lanes' own accounts, both of which match this measurement exactly.

## 2. C+D COEXISTENCE VERIFICATION (current tree, spot-verified this batch)

H12 markers present: `AVAILABLE_EXECUTION_MODES` absent from production (only a negative assertion in `test_phase8_execution_mode.py:233`); `EXECUTION_MODE_RETIRED` guards in `studio_run_adapter.py:3911/:4061` and `studio_workflow_run.py:1484`; `_workflow_legacy_run` absent; scheduler registers `V2ExperimentInvoker` only (`LocalRemoteInvoker(` absent from `studio_run_adapter.py`); canvas dispatch unconditional plan-build; modern Settings has no Run-mode/engine selector; legacy overlay engine subsection non-interactive (`modal-settings.js:1566/1573`); Reset POSTs `{gpu}` only; `/comparison/run` → `_execute_comparison_profile` → `run_prompt_stream` intact (`__init__.py:5543→5222→5306`).

H13 markers present: `refreshRecentRuns` = `createHistoryRepository({mode:"v2"}).listFeed` (`studio-playground.js:302–398`); zero `/run-history`, `/history`, `/experiments` hydration; `loadExperimentIntoPlayground` deleted (zero matches in `web/`); `experimentRunSurface()` returns `"modern"` unconditionally (`studio-experiment-mode.js:1133–1138`); creator notice `[data-testid="legacy-experiment-creator-retired"]` (`testing-setup.js:1305`) with zero compile/create/start callers; controls notice `[data-testid="legacy-experiment-controls-retired"]` (`testing-results.js:131`) with ZERO POSTs issued by the module; Comparison-owned regions byte-intact (`testing-results.js:315/436/446/1108/1131/1137`; `testing-setup.js:614 workflowsSection`); Settings Legacy group = opener + Setup/Profiles/Results/Settings (`studio-settings.js:590–632`).

Conflict found: **NONE.** No intended edit is missing; no repair performed.

## 3. V2-ONLY EXECUTION — PRECISE SEMANTIC FREEZE

Two independent axes must never be conflated:

### 3.1 EXECUTION ENGINE
New model execution is **Modal V2 only**: request acceptance → immutable ExecutionPlan → `canonical_execution.execute_plan` → `ModalTransport`. No request can newly select v1/legacy/shadow (explicit retired requests rejected pre-acceptance at every carrier; env vocabulary collapsed to `{v2}`; persisted values migrated once). Comparison is the single temporarily-grandfathered direct execution seam until Wave E.

### 3.2 ORCHESTRATION / STATUS STORAGE
A route named `/experiments/{id}` is NOT a V1 execution engine. After H12, modern Single uses it (when wired) purely as a **scheduler/status snapshot + cancellation-signalling transport** over the legacy experiment-service REGISTRY (`.experiments/` store) — it reads definition/snapshot/events and drives scheduler stop verbs. It performs no execution. History persistence is independent (below). Future agents MUST NOT delete these routes merely because the URL contains `/experiments`.

### 3.3 TRANSPORT-VS-EXECUTOR TERMINOLOGY (prevents a future false "V1 still live" claim)
`modal_client.run_prompt_stream` is the shared Modal streaming TRANSPORT primitive. It remains load-bearing for **V2** (`execute_plan` → `ModalTransport` → remote stream). What retires with Comparison/Warmup is the **direct un-planned invocation pattern** (calling `run_prompt_stream` without an ExecutionPlan). Do not delete `modal_client.run_prompt_stream` and do not call its remaining presence "a live V1 product path" after Wave E.

## 4. MODERN SINGLE RUN — EXACT CALL GRAPH (traced from source, not inferred)

```
UI Run click (web/studio-playground.js:3086/2758/2125)
  → runStudioPreset → POST /comfymodal/studio/run        (__init__.py:7497)
    workflow_version_id present → handle_workflow_run_async (:7561–7604; V2-only post-H12)
    else → validate_studio_request_controls → handle_studio_run_async (:7624–7633)
      studio_run_adapter.py:3848 — direct=True is the DEFAULT (:3859) and the route
      passes no direct flag → ALWAYS direct in production.
      retired-mode guard :3903–3913 → playground_adapter_direct_run :3949–3957
      → PlaygroundService.execute (comfymodal_runtime/playground_service.py:744)
          Stage 3: immutable ExecutionPlan build (:804)
          Stage 4: self._execute_plan → canonical execute_plan + ModalTransport (:354–393)  [V2]
          Stage 5: output materialization (:858)
          Stage 8: _default_save_history (:404) → REGISTRY.history().record_run/update_run
                   (.run_history legacy store) — best-effort mirrored into History V2 by
                   experiment_service._v2_try_mirror_record/_update (:800–859)
          Stage 9: returns {status ok, runId play_<hex>, experimentId <preset>_<hex8>,
                   direct_run: true} (:991–1003)
    ← the HTTP response carries the COMPLETED result (600s wait_for). Production never
      returns a scheduler submission response (the only caller passes no direct flag;
      direct=False has ZERO production callers — tests only).
  ← frontend _handleDirectRunResult (studio-playground.js:2612) renders terminal state.
```

**Scheduler-state truth:** for a direct single run NOTHING is written to `.experiments/` — no definition, snapshot, events, or scheduler ever exist for the returned `experimentId`. `GET /experiments/{id}` therefore 404s for single-run ids ("unknown experiment", `__init__.py:6037`). The durable record lives in `.run_history` + History V2 (mirrored), keyed by `runId` (`play_<hex>`), NOT by the experiment id.

**Frontend poll/cancel wiring (live code, conditional activation):**
- `_startPolling` (`studio-playground.js:88–197`) polls `getStudioRunStatus` = `GET /experiments/{id}` every 3s — but only when projected runState status is `submitted`/`waiting` (`projectRunToLegacy`, `studio-playground-run.js:517–537`: only `applySubmission` or poll/WS waiting states produce those). In the all-direct flow the POST holds the lifecycle and the poll never engages against a real id.
- Cancel button (`studio-playground.js:2838–2847`) → `stopExperiment` = `POST /experiments/{id}/stop-now` (`studio-backend-api.js:167–172`) — rendered during `running`/`submitted`/`waiting`. Server-side (`__init__.py:6491–6509`) it stops a legacy aggregate-experiment scheduler, records a pending stop if a definition exists, else 404s. For a direct V2 single run there is no scheduler and no definition → harmless 404 (frontend swallows it). In-flight cancellation of a synchronous direct run is simply not implemented server-side today.

Answers to §4 A–I:
- A. acceptance route: `POST /comfymodal/studio/run` (`__init__.py:7497`).
- B. execution engine: Modal V2 via `PlaygroundService.execute` → `canonical_execution.execute_plan` → `ModalTransport`.
- C. identifiers: `runId` = `play_<hex16>` (run-history/History key); `experimentId` = `<preset>_<hex8>` label only (no server-side single-run object).
- D. scheduler state: NONE for direct singles; `.experiments/` REGISTRY store exists only for legacy aggregate experiments.
- E. `GET /experiments/{id}` returns `{definition, snapshot, events}` read from `REGISTRY.store(exp_id)` (`__init__.py:6032–6047`) — legacy aggregate data; 404 for single-run ids.
- F. writers of that state: legacy experiment creation/start routes + scheduler journal (`experiment_service`); nothing in the modern Single path writes it.
- G. History V2 written independently: YES — `.run_history` record/update best-effort-mirrored into History V2 (`experiment_service.py:800–859`); replay authority stays `request_snapshots.execution_plan_json` (meta carries the serialized plan, `playground_service.py:488–505`).
- H. Cancel: UI → `POST /experiments/{id}/stop-now`; effective only against legacy aggregate schedulers; no-op(404) for direct V2 runs.
- I. stop-now stops: a legacy aggregate-experiment SCHEDULER (orchestration job), never a V1 executor and never a V2 executor; there is no shared scheduler abstraction behind direct V2 runs.

## 5. FINAL CLASSIFICATION OF THE SINGLE-RUN SEAMS

| Seam | Classification | Basis |
|---|---|---|
| `GET /experiments/{id}` (single-run progress transport) | **TRANSITIONAL_MODERN** | Live-wired into the one modern product path's run controller (`applySnapshot` feed); orchestration/status reuse only; resolves no single-run state in the all-direct flow; NOT execution. |
| `POST /experiments/{id}/stop-now` (single-run Cancel transport) | **TRANSITIONAL_MODERN** | Live-wired Cancel control of the modern Single path; stops only legacy aggregate schedulers today; harmless 404 for direct V2 runs. |

**FROZEN:** Wave E MUST NOT delete, disable, or read-only-freeze either seam. They are protected as live control surfaces of the modern Playground run lifecycle until a successor transport exists.

## 6. IS SINGLE ORCHESTRATION MIGRATION PHASE-H SCOPE? — NO

The Phase-H roadmap (§14 order, §23 hydration migration, §25 Wave D) required migrating recent-runs hydration, closing the legacy creator/fallback, and retiring legacy renderers — all DONE (H8/H13). Nothing in the frozen contract requires replacing the Single progress/cancel transport merely because its route family is historically named `/experiments`. The current Single path already satisfies every product criterion: V2 execution, immutable ExecutionPlan, History-V2 durable record, one canonical Playground UI. The route reuse is duplicate-PRODUCT-authority-free internal implementation reuse beneath one modern path.

**Classification: `LATER_INTERNAL_REFACTOR`.**
Not REQUIRED_BEFORE_H_CLOSE; not a Wave-F blocker; explicitly NOT "invent a new scheduler for naming purity." Consequence: Wave F must NOT freeze/tag these two routes as legacy while they remain the Single path's wired transport (see §8 map).

## 7. `/experiments` ROUTE FAMILY — FINAL SPLIT (22 registered routes, per-route dispositions)

Frontend-caller evidence re-measured this batch. "Python/internal callers": none — server code consumes `REGISTRY` directly; no internal HTTP client exists.

| Route (line) | Frontend callers after H13 | Modern-live | Legacy-UI-only | Old-data read compat | Zero-caller | Wave E action | Wave F action | Wave G action |
|---|---|---|---|---|---|---|---|---|
| GET `/experiments` (:6003) | testing-results picker only (:143) | no | YES | yes (list) | after E | none (UI consumer retires with group) | READ_ONLY_COMPAT tag | delete candidate after freeze |
| GET `/experiments/{id}` (:6032) | studio-playground poll (LIVE-WIRED) + testing-results reader (:1175) + testing-api.getExperiment (dead) | **poll seam YES** | reader only | yes | — | NONE — PROTECTED (reader side dies with UI) | DO NOT freeze; INTERNAL_ONLY/MODERN_LIVE | reader helpers die with testing-results; route stays |
| GET `/experiments/{id}/events` (:6049) | testing-results only (:1190) | no | YES | yes | after E | none | READ_ONLY_COMPAT | delete candidate |
| POST `/experiments/compile` (:5856) | ZERO (testing-api.compileExperiment retained, zero importers) | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete route + dead helper |
| POST `/experiments` create (:5900) | ZERO (createExperiment/createFromDraft dead) | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete route + dead helpers |
| POST `/experiments/{id}/start` (:6068) | ZERO (startExperiment/runFromDraft dead) | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete route + dead helpers |
| POST `.../pause` (:6469) | ZERO (control removed H13) | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../stop-after-current` (:6480) | ZERO | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../stop-now` (:6491) | studio-playground Cancel (LIVE-WIRED) | **YES (control seam)** | — | n/a | — | NONE — PROTECTED | DO NOT freeze; MODERN_LIVE | stays |
| POST `.../resume` (:6511) | ZERO | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../clone` (:6523) | ZERO | no | — | no | YES | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../run-missing` (:6603) | ZERO | no | — | no | YES now | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../checkpoints/{cp}/continue|restart|restart-from|skip|unskip` (:6615–6673) | ZERO | no | — | no | YES | none | ZERO_CALLER → inert/freeze | delete candidates |
| GET `.../checkpoints/{cp}/logs` (:6689) | ZERO | no | — | yes | YES | none | READ_ONLY_COMPAT | delete candidate |
| GET `.../cells/{cell}` (+`/attempts`) (:6707/:6719) | ZERO | no | — | yes | YES | none | READ_ONLY_COMPAT | delete candidates |
| POST `.../cells/{cell}/rerun` (:6723) | ZERO | no | — | no | YES | none | ZERO_CALLER → inert/freeze | delete candidate |
| POST `.../rerun-selected` (:6736) | ZERO | no | — | no | YES | none | ZERO_CALLER → inert/freeze | delete candidate |

Adjacent (same retirement family): `POST /studio/experiment` (:7653) — registered, handler creates REGISTRY experiment + ensures History V2 + starts scheduler; frontend helper `runStudioExperiment` has ZERO importers → ZERO_CALLER now; Wave F freeze, Wave G delete with helper. `POST /studio/experiment-v2` — modern, KEEP untouched.

**No single disposition covers the family.** Exactly two rows are modern-live (detail-get, stop-now); everything else is legacy-only or already zero-caller.

## 8. WAVE-E ROUTE RULE (FROZEN)

Wave E is primarily **UI/product-surface retirement**. It MAY modify exactly one execution endpoint: `POST /comfymodal/comparison/run` — because leaving it executable would preserve a hidden direct V1 product execution seam after its product surface is gone. Wave E MUST NOT perform broad `/experiments*` route cleanup; legacy route/write freezing belongs to Wave F, except where disabling the hidden executable Comparison endpoint is necessary to complete the Wave-E product retirement. Deleting either protected Single seam in E is a contract violation.

## 9. COMPARISON EXECUTION ENDPOINT — EXACT WAVE-E DISPOSITION

Current chain (verified): `POST /comfymodal/comparison/run` (`__init__.py:5543`) → `run_comparison` manifest build → sequential/parallel `_execute_comparison_profile` (:5222) → `async for _msg in run_prompt_stream(...)` (:5306) — direct un-planned V1-pattern execution. Sole web caller of the endpoint: the Runner UI (`modal-comparison.js:1179`).

**FROZEN DISPOSITION: `EXECUTION_RETIRE` via bounded truthful retired response.** In Wave E the endpoint must cease executing and return a bounded JSON error naming the retirement (follow the established `EXECUTION_MODE_RETIRED` precedent: non-executing `{"status":"error","error_code":"COMPARISON_RETIRED", ...}` with an appropriate 4xx status — implementer picks the exact verb consistent with existing error conventions; 409/410-style acceptable). Full route removal is permitted ONLY if the implementing lane updates `test_routes_registered` pins and the fake-backend mirror in the SAME change (H3 §13 #11 parity rule); the bounded-response form is preferred because it is the smallest honest change and keeps old clients truthful. `_execute_comparison_profile` becomes dead residue → Wave G.

Per-route classification of `/comparison/*` (17 routes):

| Route | Class |
|---|---|
| GET `/comparison/profiles` (:5437) | READ_COMPAT |
| POST `/comparison/profiles` (:5445) | MUTATION_RETIRE |
| GET `/comparison/profiles/{id}` (:5461) | READ_COMPAT |
| PUT `/comparison/profiles/{id}` (:5472) | MUTATION_RETIRE |
| DELETE `/comparison/profiles/{id}` (:5484) | MUTATION_RETIRE |
| POST `.../duplicate` (:5495) | MUTATION_RETIRE |
| POST `.../validate` (:5510) | READ_COMPAT (non-persisting compute) |
| POST `.../detect-slots` (:5519) | READ_COMPAT (non-persisting compute) |
| POST `.../slots` (:5530) | MUTATION_RETIRE |
| POST `/comparison/run` (:5543) | **EXECUTION_RETIRE (Wave E)** |
| GET `/comparison/results` (:5687) | READ_COMPAT |
| GET `/comparison/results/{id}` (:5695) | READ_COMPAT |
| GET `.../workflow/nodes` (:5706) | READ_COMPAT |
| GET `.../workflow` (:5717) | READ_COMPAT |
| GET `/comparison/config` (:5728) | READ_COMPAT |
| POST `/comparison/config` (:5736) | MUTATION_RETIRE |
| GET `/comparison/gallery/{id}` (:5745) | READ_COMPAT |

MUTATION_RETIRE actions land in Wave F (write freeze); Wave E removes the UI that issues them. UNKNOWN count: 0.

## 10. COMPARISON STORED DATA (re-freeze, unchanged)

Stored profiles (`user/default/comfy-modal/comparison_profiles/<id>/…`), comparison manifests/results dirs, gallery assets, and old artifacts remain untouched. No destructive migration; no deletion. Readers may keep whatever helper code they need (e.g., profile-workflow resolution used by read routes). No writer is preserved solely because a reader shares the file.

## 11. `RUN_PROMPT_STREAM` CALLER CENSUS (post-H12/H13, production)

| Caller | Kind | Classification |
|---|---|---|
| `_execute_comparison_profile` (`__init__.py:5306`) ← `/comparison/run` | direct un-planned invocation | product execution reachability ends at Wave E (EXECUTION_RETIRE) |
| warmup route (`__init__.py:7751–7752`) ← `POST /deploy-warmup/run` | direct un-planned invocation | RETIRE per FA-3 — destination frozen below |
| `canonical_execution.execute_modal_prompt` (:3749) | V1 executor body | DEAD post-H12 (zero production callers; kept for registered `test_studio_direct_run`) → Wave G |
| `experiment_runner.LocalRemoteInvoker` (:1236 wraps injected fn) | legacy invoker | DEAD post-H12 (zero production registrations; test-consumed) → Wave G |
| `canonical_execution.execute_plan` → `ModalTransport` | V2 transport streaming through the SAME remote method | MODERN — KEEP (this is why `modal_client.run_prompt_stream` itself must never be deleted as "V1") |

**WARMUP DESTINATION: `WAVE_F`** (route/write-freeze review together with the legacy-panel/experiment route families) **with code deletion in `WAVE_G`.** Explicitly NOT Wave E. Why: FA-3 deliberately deferred warmup retirement to "a later wave"; warmup already has zero UI consumers, so Wave E gains nothing by absorbing it; the warmup region lives in `__init__.py` deploy/warmup territory owned by L-BE2/L-FRZ, not the Wave-E Comparison/overlay lanes — bundling it would expand Wave E's `__init__.py` blast radius beyond the frozen ownership plan. Its last consumer-gate (`gate_experiment_on_stored_generation`, `__init__.py:6115–6132`) belongs to the legacy aggregate-experiment start route that goes zero-caller with H13 and freezes in F.

## 12. FOUR CONCEPTS THAT MUST NEVER BE MERGED (terminology freeze)

1. **Product execution reachability** — after Wave E: zero V1-pattern product paths remain reachable from any user surface.
2. **Old executor code remaining on disk** — `execute_modal_prompt`, `LocalRemoteInvoker`, `_execute_comparison_profile` bodies persist until Wave G; existence ≠ reachability.
3. **Old routes remaining registered but retired/unreachable** — `/comparison/run` returning a truthful retired error; warmup route inert-until-F; registered ≠ executable product surface.
4. **Dead helper residue** — the §26 list; deleted only in Wave G with their tests.

A function definition surviving Wave E is NOT evidence that "Phase H failed to retire V1."

## 13. SETTINGS ▸ ADVANCED ▸ LEGACY — CURRENT CONTENT AND WAVE-E FATES

Verified content (`studio-settings.js:590–632`): temporary "Open Legacy Settings" opener + exactly four entries (Setup/Profiles/Results/Settings) mounted through `renderLegacyView` → `studio-legacy.js mountLegacyTab` (`LEGACY_MODULES` = setup/profiles/results/settings; unknown tabs fail closed).

| Tab | Current behavior (verified) | Wave-E fate |
|---|---|---|
| Setup | creator-retired notice; `workflowsSection` Comparison profile CRUD/detect-slots/validate/duplicate/delete residual; inert `generationType`/`whatChanges`/`testValues` form sections (no execution actions) | **RETIRE/UNMOUNT whole tab.** After Comparison retirement nothing unique remains; inert forms are NOT ported forward. Module file deletion Wave G. |
| Profiles | Comparison Profiles editor UI (`testing-profiles.js` full CRUD against `/comparison/profiles*`) | **RETIRE.** No modern replacement domain; stored readers/data survive. Disable mount/export/global; file may remain unreachable until G. |
| Results | read-only legacy Experiment display (picker/snapshot/events/grid rendering, ZERO POSTs) + Comparison selection/A-B slider workspace | **RETIRE from the Settings group.** Historical records remain viewable through History V2 (migrated Singles + mirrored terminal Experiment cells are already projected — H13 §3). Legacy records that were never mirrored (never-terminal aggregates; un-migrated `.run_history` rows — the seam is test-invoked only) stay accessible via hidden readers/data only; that is acceptable: UI retirement ≠ data deletion, and no entire Results UI is preserved merely because a hidden reader exists. |
| Settings | embeds `window.mountSettingsPanel` (legacy overlay panel) + standalone launcher via `window.open_comfymodal_settings` (callers :90/:109/:173) | **RETIRE tab + overlay access.** See §14/§15. |

## 14. TESTING-SETTINGS / STANDALONE OVERLAY FATE

No valid user-facing capability still requires `testing-settings.js`, `window.open_comfymodal_settings`, or the standalone overlay: workspace ops → Backend (H6), deployment/runtime → Backend, credentials → Backend, manifest repair → Backend (FA-2 F1), model library → Workflows (H7), run-mode/engine → retired (H12), obsolete ops → RETIRE (FA-2), auth/setup → not-required-parity (FA-4). **Product blocker: NONE.**

**FROZEN:** Wave E removes normal access (Legacy group + four tabs) and the standalone overlay UI, and deletes `window.open_comfymodal_settings` WITH the overlay (its only remaining callers are inside `testing-settings.js`, which retires in the same wave — re-measured this batch; zero external callers).

## 15. MODAL-SETTINGS.JS SHARED-CODE SPLIT (region ownership for the Wave-E prompt)

| Region | Items | Wave E |
|---|---|---|
| A. Overlay/UI-only | `open_comfymodal_settings` overlay builder (:4107–4161); `mountSettingsPanel` exposure (:4095; sole external consumer is retiring testing-settings.js); panel-body operational sections (deploy banner/log/poll, models/sync lists, auth panel, workspace section, download-progress UI) insofar as they exist only inside `buildPanel()` | REMOVE |
| B. Canvas compatibility state/writers | `window._comfyModalEnabled` semantics; `updateModalSections`; the Cloud/Local toggle's persisted-key chain. The interactive toggle UI dies with the overlay, but canvas pass-through semantics (H5 §8) MUST be preserved: Wave E must retain a bounded startup initialization reading the persisted `comfymodal_enabled` LS key into `window._comfyModalEnabled` so existing Local-mode users keep identical canvas behavior (`modal-node.js:678/841` reads `!== false`; undefined currently defaults enabled) | PRESERVE (bounded shim allowed) |
| C. Output-preference shared wiring | imports/init from `studio-output-preferences.js`; `syncLegacyOutputPrefsOnce` (:184) | PRESERVE |
| D. Initialization required by other modules | `syncLegacyGpuConfigOnce` (:176) read-only server sync consumed by the toggle/GPU display; extension registration/setup() hygiene (:4163–4199) | PRESERVE (trim to what survives B/C) |
| E. Dead residue | anything left unreachable after A's removal (unused section builders, orphaned helpers) | Wave G deletes |

Do NOT delete `modal-settings.js` wholesale (H5 §21 rule stands).

## 16. `OPEN_COMFYMODAL_SETTINGS` GLOBAL — DECISION

Re-measured: callers = `testing-settings.js:90/109/173` only (all inside the Wave-E-retiring surface) + the comment at `modal-settings.js:4197`. Zero callers outside retiring modules → **freeze DELETION of the global together with the overlay in Wave E.** No redirect symbol is needed (the modern sidebar already routes to modern Settings; H10/FB-3 verified). If an unexpected external consumer is discovered during E, prefer a bounded redirect to modern Settings over reopening retired UI — but today's evidence requires no symbol retention.

## 17. COMPARISON GLOBALS / CANVAS MENU — WAVE-E DELETION SET

Re-measured callers (all inside `modal-comparison.js` itself + retiring legacy tabs):
- `window.mountComparisonProfiles` (:1567) / `window.mountComparisonRunner` (:1578) — defined in modal-comparison.js; consumed by overlay builders and legacy tabs → DELETE in E.
- `window.openComparisonProfilesOverlay` (:1643) / `window.openComparisonRunnerOverlay` (:1649) — DELETE in E.
- Comparison canvas context menu: `_initContextMenu` (:1425) wraps `app.canvas.getNodeMenuOptions` to add slot-mapping items (always-on) → DISABLE/REMOVE registration in E. Canvas `/prompt` interception itself remains untouched; Production mode remains untouched; no other canvas menu item is disturbed.

## 18. SETTINGS LEGACY GROUP REMOVAL GATE

| Prerequisite | Status |
|---|---|
| Backend operational parity (workspace/deploy/runtime/credentials/repair) | SATISFIED (H6; FA-2 ledger, zero blockers) |
| Model Library parity | SATISFIED (H7; FA-5 zero blockers) |
| No legacy Experiment creator | SATISFIED (H8 fallback closure; H13 creator UI retirement) |
| Modern recent-runs migrated off legacy feeds | SATISFIED (H13; zero legacy hydration proven by spec) |
| Comparison scheduled to retire in the SAME Wave E | SATISFIED (this freeze, §9/§17) |
| Redirects already modern | SATISFIED (H10; FB-3) |
| Execution selector / Run mode gone | SATISFIED (H12) |
| Workspace-registry fake blocker | DISSOLVED (FA-1: not an existing capability) |
| Auth/setup not required parity | SATISFIED (FA-4) |

**`SETTINGS_LEGACY_GROUP_REMOVAL_READY = YES`** — proven row-by-row above; no manufactured blockers.

## 19. HISTORY / OLD-DATA PRESERVATION (re-frozen)

Wave E must not alter: History V2 (schema/routes/writer/replay), `.run_history`, legacy experiment JSON (`.experiments/`), comparison stored data, RequestSnapshots, `legacy_mapping` + dormant `LegacyMigrationSeam`, replay-capability projection, `_resolve_replay_workspace`/`_resolve_workspace_dict` fallback, historical annotations, old images/assets. UI retirement ≠ data deletion (H3 §14 blockers all stand).

## 20. WAVE-E TEST GATE — DESIGN (do not implement in E's planning; this is the E exit contract)

The Wave-E implementation lane must prove, on the converged tree:
1. Settings Legacy group absent (no `settings-legacy-*` testids).
2. Standalone legacy overlay cannot open (`open_comfymodal_settings` absent or bounded-redirect per §16 freeze — deletion is the frozen expectation).
3. Modern Settings still opens; sections/filter/reset intact.
4. Backend still owns operational controls (H6 unit pins hold).
5. Workflows Model Library remains (H7 unit pins hold).
6. Normal Studio aliases still land modern (`ALIAS_PAGE_MAP` intact).
7–10. Setup/Profiles/Results/Settings legacy tabs no longer mountable (`studio-legacy.js` loader entries removed or loader retired; unknown-tab fail-closed preserved).
11. Comparison canvas menu absent (no slot-mapping items; `/prompt` menu otherwise intact).
12. Comparison overlay globals absent (or redirected per freeze).
13. `POST /comparison/run` cannot execute (retired response asserted; no `run_prompt_stream` invocation reachable from it).
14. Comparison stored profiles byte-identical before/after (fixture hash).
15. Comparison read compatibility remains (READ_COMPAT routes still answer from stored data).
16. History old records remain (feed/detail projections unchanged; migrated-single + mirrored-experiment seeds still render).
17. Canvas `/prompt` Local/Cloud gate behavior unchanged (LS-key init shim per §15-B).
18. Canvas Production mode remains.
19. Output options remain.
20. Modern V2 execution remains (single + workflow happy paths green).
21. H13 History-V2 recent-runs remains (12-test spec still green).
22. Zero legacy Experiment creation remains (network absence pins hold).
23. Live Single poll/Cancel behavior remains (protected seams still wired; run-lifecycle specs green).
24. No broad `/experiments` route deletion (registry count unchanged except — if chosen — the single Comparison run endpoint entry, with same-change pin updates).

## 21. WAVE-E FILE OWNERSHIP PLAN (writer lanes for the next implementation batch)

| File | Owned region | Scope |
|---|---|---|
| `web/studio-settings.js` | Legacy-group region only (:590–632 + `activeLegacyTab` machinery) | remove group/opener/embed |
| `web/studio-legacy.js` | whole loader | retire entries or file-surface (G deletes file) |
| `web/modal-settings.js` | overlay/UI regions ONLY (§15-A); preserve §15-B/C/D | overlay removal + LS-key init shim |
| `web/modal-comparison.js` | Comparison UI/overlay/context-menu regions (builders, mounts, globals, `_initContextMenu`) | retire UI layer |
| `web/testing-setup.js` | residual tab UI | unmount/retire |
| `web/testing-profiles.js` | Comparison UI | retire |
| `web/testing-results.js` | residual legacy Results/Comparison UI | retire |
| `web/testing-settings.js` | legacy Settings tab | retire |
| `web/testing-ab-slider.js` | legacy A/B UI retirement; feature itself deferred to Phase I, NOT ported | retire consumers |
| `web/modal-testing.js` | only if lazy-tab loader/group removal needs cleanup; PRESERVE modern alias map + sidebar entry | bounded cleanup |
| `__init__.py` | Comparison route region ONLY (`/comparison/run` handler → retired response) | single region; coordinate sequentially with any L-FRZ touch |
| comparison-specific tests/fakes | registry pins (only if route removed), structural tests of retired surfaces, fake mirrors of retired UI flows | same-change updates |

Avoid unrelated execution-mode regions (H12-complete). `__init__.py` stays single-writer during E.

## 22. WAVE-F CONSEQUENCE MAP (after prospective Wave E; classification only)

| Route family | Post-E class |
|---|---|
| `/comparison/*` reads (profiles/results/workflow/config/gallery/validate/detect-slots) | READ_ONLY_COMPAT (hidden) |
| `/comparison/*` writes (profile create/update/delete/duplicate/slots/config POST) | MUTATION_RETIRE → freeze writes |
| `POST /comparison/run` | retired-response (landed in E) → INERT |
| `GET /experiments` · `/{id}/events` · checkpoints/cells reads | READ_ONLY_COMPAT (last UI consumer gone with E) |
| `GET /experiments/{id}` · `POST .../stop-now` | **MODERN_LIVE / INTERNAL_ONLY — DO NOT FREEZE** (protected Single seams, §5/§6) |
| compile/create/start/pause/resume/stop-after-current/run-missing/rerun*/clone · `POST /studio/experiment` | ZERO_CALLER → freeze/inert |
| `/run-history` list/detail/logs/timing | READ_ONLY_COMPAT (bridge programmatic-only) |
| `PATCH /run-history/{id}/annotations` · `POST .../save` | READ_ONLY_COMPAT until stale results.v1 population ages out (shrinking) |
| `/studio/backends` | replace modern consumers with truthfully named seam, then demote hidden read-only shim (§19) |
| `/auth/setup` | COMPATIBILITY route untouched; F/G review |
| warmup (`/deploy-warmup/*`) | F decision lane: RETIRE confirmed (FA-3); freeze/disable route here |
| `/history` (unified platform feed) | KEEP (platform route; leave alone) |
| `/studio/experiment-v2` · `/history-v2/*` · `/studio/run` · presets/snapshots | MODERN_LIVE — untouched |

## 23. WAVE-G CONSEQUENCE MAP (caller-based residue list, re-measured)

Confirmed dead-or-dying after E (delete with their dedicated tests/specs):
- `direct_studio_run_completion` (`studio_run_adapter.py:3302`) — zero production callers post-H12; exercised by registered `test_studio_direct_run` (delete suite portions with it).
- `execute_modal_prompt` (`canonical_execution.py:3615`) — zero production callers; test-consumed.
- `LocalRemoteInvoker` (`experiment_runner.py:1236`) — zero production registrations; widely test-consumed (`test_experiment_runner`, `test_studio_live_progress`, `test_studio_timing_integration`, `test_studio_runtime`, `test_studio_direct_run`).
- `_prepare_studio_run_context` (~:3081) + `_handle_studio_run_scheduler` (:3689) — reachable only via `direct=False` (zero production callers; test-only).
- `_playground_runtime_mode` (`studio_run_adapter.py:1910`) — re-measure callers at G (H12-listed residue).
- Frontend dead helpers: `runStudioExperiment` (:143), `listExperiments` (:269), `listRunHistory` (:275), `setRunAnnotation` (:385), `saveRunHistoryOutput` (:405) in `studio-backend-api.js`; `getExperimentHistory`/`previewDraft`/`createFromDraft`/`createExperiment`/`compileExperiment`/`startExperiment`/`runFromDraft`/`getExperiment` in `testing-api.js` — zero importers verified.
- Retired module files after E: `testing-setup/profiles/results/settings.js`, `testing-ab-slider.js`, `modal-comparison.js` UI layer, `studio-legacy.js`, overlay regions of `modal-settings.js`, lazy-tab remnants in `modal-testing.js`.
- `_execute_comparison_profile` (`__init__.py:5222`) after the E retired-response lands.
- Stale/out-of-gate tests: see §24.

NOT dead (do not delete): `modal_client.run_prompt_stream` (V2 transport), `REGISTRY.history()` readers + `history_index.py`, `LegacyMigrationSeam`/`legacy_mapping`, replay projection, workspace fallback, `GET /history` platform feed.

## 24. CURRENT TEST-REGISTRATION DEBT (carried forward; nothing registered now)

- Unregistered Node units: `tests/studio_backend_operations_unit.mjs` (H6), `tests/studio_model_library_parity_unit.mjs` (H7), `tests/studio_legacy_settings_authority_unit.mjs` (H1-era; MIGRATE-THEN-REGISTER per §27) — verified absent from `NODE_UNIT_FILES` (`tests/run_studio_tests.py:120–149`).
- Unregistered Python suites: `tests/test_phase8_execution_mode.py` (rewritten by H12) and `tests/test_h12_v2_only_consolidation.py` (new) — verified absent from `STUDIO_PY_MODULES` (:40–103).
- Out-of-gate stale pins (Class B/D per H5B §6, unchanged): `test_task3_progress_annotations` tracker-membership ×5; `test_modal_workspace_ui_ast` production-summary-label + output-savefolder-literal ×2.
- H12 reverse-order isolation artifact: running `test_f8_gpu_authority` BEFORE `test_workflow_run_integration` trips the `history_v2_writer` singleton leak (gate order is correct; L-TST note).

All of the above are Wave-G L-TST items. This batch edited no test registration.

## 25. FINAL WAVE-E ENTRY VERDICT

**`WAVE E READY`**

No Phase-H-contract blocker remains. All listed F/G items (scheduler-route refactor, warmup route/code deletion, dead-helper deletion, test registration debt) are explicitly out of E scope by this freeze and are NOT E blockers.

---

Deploy / live / GPU / generation / commit / push / branch / worktree / reset / stash / clean by this batch: **NONE**.
