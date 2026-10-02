# PHASE H FINAL CLOSURE — ZERO-CONTEXT HANDOFF (2026-08-25)

**Audience:** a completely fresh agent with ZERO conversation context, starting work after Phase H (Studio Consolidation). Assume this conversation disappears; this file plus the referenced reports are the only inherited memory.
**Status authority:** `PHASE H COMPLETE` (see `PHASE_H_FINAL_CLOSURE_2026-08-25.md`). Final gate: **Python 2124/2124 · Node-unit 25/25 files · Fake Playwright 211/211 exact** (one known-flake occurrence; direct rerun green).
**Batch discipline inherited by every lane:** no deploy, no Modal invocation, no GPU/live generation, no commit/push/branch/worktree/reset/revert/stash/clean unless a future batch explicitly authorizes it. The working tree is intentionally dirty and shared.

---

## A. PROJECT PURPOSE

**ComfyModal Studio** is a custom ComfyUI node (`comfyui-modal`) that turns ComfyUI into a Modal-cloud product. High-level execution architecture:

- The user composes prompts/experiments in a modern in-app Studio (five pages) or uses the legacy ComfyUI canvas.
- Modern execution: an accepted request is frozen into an immutable **ExecutionPlan**, executed by **Modal V2** (`execute_plan` → `ModalTransport` → `modal_client.run_prompt_stream`, a Modal-cloned remote ComfyUI function), materialized locally, and recorded durably in **History V2** (SQLite) with `RequestSnapshot.execution_plan_json` as replay authority.
- GPU selection is server-authoritative and frozen per plan at acceptance.
- Workflows domain: Workflow → immutable WorkflowVersion → immutable Mapping → version-scoped Workflow Presets; Model Library + custom-node registry own dependency truth; Portability (Phase G) provides exact manifest export/import + advisory six-target risk analysis.
- Backend page owns Modal workspace identity, deployment, readiness, logs, credentials, snapshots, repair.
- Deterministic quality gate: `python tests/run_studio_tests.py --fake` (Python unittest allowlist + Node units + fake Playwright browser suite against `tests/browser/fake/fake-server.mjs`). Live Modal validation is a separate, explicitly-authorized activity.

---

## B. PRE-H CONTEXT NEEDED TO UNDERSTAND H (inherited Phase F/G architecture)

Phase H was forbidden to break these (all still binding):

1. **Immutable WorkflowVersion** — write-once (`ImmutableVersionError` on update); Mapping insert-once; exactly one per version.
2. **ExecutionPlan immutability** — built once per accepted run; never reconstructed from current mutable state.
3. **RequestSnapshot replay authority** — every re-execution (Generate Original / Retry / Resume / Generate Again) replays `request_snapshots.execution_plan_json` through validation + exact round-trip; only an allow-listed delta may differ.
4. **History V2** — sole durable History (`history_v2.db`); append-only attempts; first-terminal-wins; durable favorite/note columns; five distinct download/export concepts (managed asset ≠ browser download ≠ configured-folder export ≠ view original ≠ generate original).
5. **Portability manifest exactness** — Studio Workflow Manifest v1 is the sole portability artifact; export→dry-run-import→commit→re-export is canonically byte-equal; import is dry-run-first and atomically compensated (`commit_import_transaction`); credential-like exports refuse closed; no ZIP, no model bytes, no local install paths exported.
6. **GPU freeze** — `resolve_request_gpu()` captures ONCE at acceptance into plan metadata; replay/resume/retry reuse verbatim; later Settings changes affect future submissions only.
7. **No live replay lookups** — History render/replay never reads current Workflow/Version/Mapping/Preset/Model-Library/compatibility/portability state; the ONE sanctioned external resolution is the active-workspace fallback for pre-workspace-id snapshots.
8. **Old irreproducible rows stay truthfully irreproducible** — `replay_capable=false` + machine-readable reasons; fail-closed 409 `generation_not_reproducible`; no reconstruction ever.
9. Phase-G §37 invariants (28) and Phase-F §7 invariants (14) remain in force in full — see those handoffs.

---

## C. WHY PHASE H EXISTED

Pre-H duplication/legacy problems (from H1–H4 audits):

- **Legacy Studio surfaces**: hidden sidebar tabs, Legacy Dashboard/History tabs, Settings ▸ Advanced ▸ Legacy group (Setup/Profiles/Results/Settings), standalone legacy settings overlay (`open_comfymodal_settings`), dual design systems.
- **V1 execution engine** still dispatchable (Single non-V2 branch, workflow legacy run, experiment LocalRemoteInvoker, canvas v1 branch, `/config` accepting v1, `AVAILABLE_EXECUTION_MODES` advertising `{v2,v1}`).
- **Run mode ambiguity**: modern Settings Cloud/Local "Run mode" controlled only legacy canvas interception; triple meaning of "Local" (portability target / canvas pass-through / implied Studio mode).
- **Comparison product**: Profiles editor + Runner UI executing through V1 `run_prompt_stream`, slot-path graph mutation conflicting with immutable Version+Mapping.
- **Multiple experiment authorities**: modern experiment-v2 vs legacy `/studio/experiment` creator + `.experiments/` scheduler store; Playground fallback could create legacy experiments.
- **Legacy Settings** owning operational readouts that belong to Backend.
- **Backend ownership ambiguity**: `/studio/backends` misnomer (comparison-profile compatibility data, not a provider registry).
- **Models/Sync duplication**: raw installer/bulk-download/sync UIs duplicating Workflows Model Library truth.
- **Old History feeds**: Playground recent-runs hydrating from three legacy feeds (`/run-history?limit=50`, `/history`, `/experiments`).
- **Stale dead code/tests**: orphaned modules, unregistered meaningful suites, stale structural pins.

---

## D. H1–H5 AUDITS AND CONTRACT DECISIONS

Audits: H1 inventoried legacy/V1 retirement candidates; H2 froze Run-mode Option C (single-engine, remove S1) and designed the persisted-mode migration; H3 proved which routes/stores are NOT deletion-ready (compatibility freeze list); H4 mapped surface ownership and the legacy exit checklist.

H5 (`PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md`) is THE authoritative contract. Key frozen decisions:

- **R1 Comparison = RETIRE** product/UI in Wave E while keeping stored-data/read compatibility hidden; A/B slider deferred to Phase I.
- **R2 Canvas Production mode stays** with the canvas compatibility layer.
- **R3/R4 Run mode = RETIRED** from modern Settings; `comfymodal_enabled` leaves all modern reset sets but the canvas key is untouched until canvas retirement.
- **R5 V1 = compatibility-only, scheduled for retirement** in Wave C after Comparison/shadow blockers were dissolved by the C/E sequencing rule.
- **R6 Bridge History mode** may retire programmatically; legacy run-history read routes/storage remain compatibility shims.
- **R7 Legacy experiment creator** retires consumer-migration-first (six-step order §14).
- Five-surface IA frozen (§2); single-engine Modal V2 (§3); shadow retires with V1 and env vocabulary collapses to `{v2}` (§6); Settings keeps preferences only (§11); Reset All degrades to `{gpu}` (§11); three preset authorities never conflated (§15); History no-live-lookup hard freeze (§16); Waves A–G order (§25); 26 must-preserve invariants (§28); Phase-I boundary (§29).

---

## E. EVERY IMPLEMENTATION BATCH H6–H20

| Batch | Purpose | Exact architectural change | Important files | Test result | Key discovery | Follow-up |
|---|---|---|---|---|---|---|
| **H6** | Wave A1+A2 Backend re-home | Modern Backend gains workspace CRUD/select/swap, deploy/redeploy/status/log, readiness, credentials (no echo), swap-blocking manifest repair; WARMUP=RETIRE verdict | `web/studio-backend*.js` (+4 new modules), `studio-backend-api.js` additive region | ops unit 24/24; backend suite 298 | No workspace-registry export/import route exists anywhere | FA errata |
| **H7** | Wave A3 Model Library parity | Custom-node registry browse/refresh/install-request + dependency→library handoff added to Workflows using existing routes; 18 legacy Models/Sync ops classified (4 already-modern, 4 gaps landed, 4 retire, 10 backend-operational) | `web/studio-model-library.js`, `web/studio-workflows.js` deps region | parity unit 16/16; model suites 33 | Route+API existed with zero UI callers | FA-2 ledger |
| **H8** | Wave A4 experiment fallback closure | `experimentRunSurface()` can no longer offer a legacy creator; missing identity fails closed; valid runs post exactly one `/studio/experiment-v2`; dual zero-write instrumentation | `web/studio-experiment-mode.js` | gate 1991/21/199 green | Normal fresh Playground state used to create legacy experiments | — |
| **H9** | Wave B dead History/Dashboard retirement | Deleted `web/studio-history.js` (1704 lines), `testing-dashboard.js`, `testing-history.js`; loaders fail-closed; −74 stale assertions | deleted files + loader/list regions | 1941/21 green | Reverse-import proof before deletion | FB |
| **H10** | Wave B redirects | `ALIAS_PAGE_MAP` 7 aliases → modern owners with bounded deprecation notices; hidden sidebar registrations removed; legacy funnel copy rewritten truthfully | `web/modal-testing.js`, `modal-settings.js`, `modal-comparison.js`, feature-registry/playground copy | focused green | Historically-flagged "auto-open" did not exist | FB |
| **H11** | Wave B dead helpers | Deleted `is_v2`/`is_shadow` (−12 lines, resolver untouched) | `execution_runtime.py` | 1991/21 green | Zero callers re-proven | — |
| **H12** | Wave C V2-only consolidation | Deleted ALL V1/shadow branches (Single non-V2 branch, workflow `_workflow_legacy_run` incl. :1556 remnant, experiment LocalRemoteInvoker registration, canvas v1 dispatch, `AVAILABLE_EXECUTION_MODES`); `/config` accepts v2 only; env vocabulary `{v2}`; persisted v1→v2 idempotent migration + one-time notice; Settings Run mode/engine selector removed; Reset `{gpu}`-only | `execution_runtime.py`, `__init__.py`, `studio_run_adapter.py`, `studio_workflow_run.py`, `web/studio-settings.js`, `web/modal-settings.js` | phase8+h12 62/62; f8 41/41; gate 1945/21/211 | Retired explicit requests surfaced `retired=true`, never silently relabeled | FC freeze |
| **H13** | Wave D recent-runs migration | `refreshRecentRuns` = History-V2 `listFeed` only; EXP click opens History detail via focus seam; legacy grid viewport (~1350 lines) + poller cascade deleted; Setup/Results creators retired with zero POSTs | `web/studio-playground.js`, `studio-history-v2.js`, `studio-experiment-mode.js`, `testing-setup/results.js` | 1945/21/211 | Single poll/stop-now seams identified as LIVE modern transport | FC protected seams |
| **H14** | Wave E legacy Settings + Comparison retirement | Settings Legacy group + standalone overlay + 4 legacy tabs removed; `open_comfymodal_settings`/`mountSettingsPanel` deleted; Comparison extension/globals/canvas menu deleted; `/comparison/run` → bounded 410 `COMPARISON_RETIRED` (body unparsed, byte-integrity proven); modal-settings split executed (canvas shim preserved) | `web/studio-settings.js`, `studio-shell.js`, `modal-testing.js`, `modal-comparison.js`, `modal-settings.js`, `__init__.py` comparison region | h14 27; gate 1974/21/211 | Settings Runtime & Backend group = pre-existing debt (Backends row later removed by H16) | FD freeze |
| **H15** | Wave F server write freeze (F-SRV) | All RETIRED_WRITE → 409 `<FEATURE>_READ_ONLY`; RETIRED_EXECUTION → 410 `<FEATURE>_RETIRED`; hash-proven zero mutation across comparison/experiments/warmup/presets/backends/modal.toml; protected seams byte-untouched; fake `/studio/experiment` mirror parity | `__init__.py` frozen regions, `fake-server.mjs` | h15 36; gate 1974/21/211 | Response standard FD-17 (410=gone capability, 409=readable-data conflict) | FE closure |
| **H16** | Wave F Settings Backends consumer removal (F-BE) | Removed Backends count row + fetch leg from Settings Runtime group; no replacement API built | `web/studio-settings.js`, `tests/test_studio_backend.py` pins | backend 286/286; gate green | Sole live `/studio/backends` consumer needed no real data | FD-8 executed |
| **H17** | Wave F test convergence (F-TST) | Audited + registered H15 suite (36); count ledger 1974+36=2010 proven twice; FD-23 matrix all 21 rows accounted | `tests/run_studio_tests.py`, h15 docstring | 2010/21/211 first-attempt | Ordering constraint documented (stub-server harness after Workflows block) | FE appendix |
| **H18** | Wave G frontend deletion | Deleted 9 dead module files (`testing-setup/profiles/results/settings/ab-slider.js`, `studio-legacy.js`, `modal-comparison.js`, `testing-api.js`, `testing-setup-adapter.js`); `modal-settings.js` 4139→158-line compat module (canvas shim/output wiring/GPU read-only sync/redeploy banner kept); 7 dead API helpers deleted; COMPAT_WRITE pair + protected-seam helpers kept; testing-styles pruned to live tokens | see report §13 | 1862/21/211 (−148 obsolete assertions) | ComfyUI auto-load means deletion safety requires zero top-level side effects, not just zero importers | FF |
| **H19** | Wave G Python execution deletion | Deleted `_execute_comparison_profile` (~215 lines), `direct_studio_run_completion`, `execute_modal_prompt`+`prepare_modal_execution` (~430), `LocalRemoteInvoker` (~390), `_prepare_studio_run_context`, `_handle_studio_run_scheduler`, `_playground_runtime_mode`, dead warmup helpers + orphaned imports; census of direct `run_prompt_stream` calls in `__init__.py` = `[]` | `__init__.py`, `studio_run_adapter.py`, `canonical_execution.py`, `experiment_runner.py` | 1824/21/211 (this lane exactly −38) | `run_prompt_stream` itself NEVER deleted (V2 transport) | FF-8 residue map |
| **H20** | Wave G test consolidation | Registered phase8(+41), h12(+21), progress annotations(+71, renamed from task3), run-history family(+143), workspace AST(+24); Node 21→25 (backend ops, model parity, settings-compat renamed from legacy-settings-authority, e4d retry); fixed tracker-membership ×5 (stale premise re-pointed at run controller), F8×workflow fixture leaks ×2 (GPU restore + writer-seam pin); deleted stale image-packaging file | `tests/run_studio_tests.py` + listed suites | **2124/25/211 final** | "Meaningful deterministic suite simply unregistered" = ZERO | FF-8/FF-9 hygiene |

H5 Follow-Ups A–F (contract appendices, authoritative): **A** = post-Wave-A errata (workspace-registry export/import dissolved as never-existing capability; warmup RETIRE accepted; auth/setup not-required-parity; 11-operation ledger). **B** = post-Wave-B convergence (baseline 1941/21/199; H11's 1991 explained as temporal staleness). **C** = post-C/D convergence + Wave-E entry freeze (V2-vs-orchestration semantics; protected Single seams TRANSITIONAL_MODERN; comparison EXECUTION_RETIRE disposition; SETTINGS_LEGACY_GROUP_REMOVAL_READY=YES). **D** = post-E convergence + Wave-F entry freeze (route-class vocabulary FD-2; run-history COMPAT_WRITE correction FD-4; presets exclusion FD-6; backends disposition FD-8; response standard FD-17; do-not-touch list FD-18). **E** = post-F closure (Wave F COMPLETE; baseline 2010/21/211). **F** = post-G convergence (baseline 2124/25/211; residue map FF-8; route pruning FF-9).

---

## F. FINAL PRODUCT ARCHITECTURE

Five surfaces (`web/studio-shell.js` PAGES, verified):

1. **PLAYGROUND** (`studio-playground.js` + `studio-playground-run.js` controller + `studio-experiment-mode.js`): compose/run Single; compose/run Experiment (always experiment-v2; gated with truthful reasons when Workflow/Version missing); immediate progress/result via run controller (poll fallback `_startPolling` → protected GET seam; Cancel → protected stop-now seam); Workflow/Version/Preset selection for execution; recent-runs filmstrip hydrated ONLY from History-V2 feed (`listFeed`, mixed kinds, newest-first, id-dedupe); lightweight selected-run actions — favorite/note branch on `_historyKind`: History-backed records use durable V2 routes, untagged records (fresh direct-run panels, stale persisted selections) use the run-history COMPAT_WRITE pair; Save output uses V2 asset export for tagged records else run-history save.
2. **HISTORY** (`studio-history-v2.js` + `-detail/-experiment` + `history-v2-repository.js`): sole durable feed/detail; actions Generate Original / Generate Again / Retry (Original) / Resume / Experiment Cancel / Cell Retry — all immutable-plan replays; Browser Download + configured-folder Export; durable favorite/note; Timing/diagnostics.
3. **WORKFLOWS** (`studio-workflows.js` + `studio-model-library.js` + `studio-portability*.js`): library, immutable versions, mapping, Workflow Presets, dependencies, Model Library (browse/search/rescan/notes/install-request click-gated), custom-node registry, Compatibility annotations (distinct concept), Portability panel/chips/export/import/checklist (G freeze), manifest import/export.
4. **BACKEND** (`studio-backend.js` + `-workspaces/-deployment/-credentials/-runtime/-presets/-snapshots/-capture`): Overview readiness rows; Workspaces CRUD/activate/swap + repair; Deployment deploy/redeploy-restart/status/log; Credentials (Modal/HF/Civitai, never echoed); Backend Presets tab; Snapshots.
5. **SETTINGS** (`studio-settings.js`): preferences only — GPU default (server-authoritative), Preview defaults, Outputs, History grid columns, Interface, Tracing level, Reset All (`{gpu}` + tracing-off only), H12 migration notice display.

Cross-surface rules: Experiments have no dedicated tab (Playground compose/live + History records); Portability solely in Workflows; Compatibility ≠ Portability; operational state never in Settings.

---

## G. FINAL EXECUTION ARCHITECTURE

- **Single**: UI Run → `POST /comfymodal/studio/run` → retired-mode guard (400 `EXECUTION_MODE_RETIRED` pre-acceptance) → `playground_adapter_direct_run` → `PlaygroundService.execute` (plan build → `_execute_plan` V2 → materialize → `.run_history` record best-effort mirrored into History V2) → HTTP response carries completed result (`runId play_<hex>`; `experimentId` label-only; `direct_run:true`). No `.experiments/` scheduler state for direct singles.
- **Workflow**: same route with `workflow_version_id` → unconditional `_workflow_v2_run` → PlaygroundService (immutable plan). `_workflow_legacy_run` deleted.
- **Experiment**: `POST /studio/experiment-v2` → scheduler → `V2ExperimentInvoker` (only registered invoker). Legacy `/studio/experiment` returns 410 before any side effect.
- **Canvas Cloud**: `/prompt` interception → retired-request 400 guard → capture (v2) → `build_execution_plan` → `execute_plan`. Canvas Local = pass-through compatibility, never a Studio engine.
- **V2-only behavior**: resolver vocabulary `{v2}`; explicit retired requests rejected everywhere pre-acceptance; persisted garbage/v1/legacy/shadow migrated once to `"v2"` with one-time notice; `COMFYMODAL_RUNTIME` env lock mechanism preserved, retired values logged-and-refused.
- **Retained recognition/migration of retired strings**: alias recognition (for migration + truthful diagnostics), rejection codes, migration notices, trace span vocabulary. Executable outcome always V2.
- **ModalTransport / run_prompt_stream**: `execute_plan` → `ModalTransport` → `modal_client.run_prompt_stream` — the SOLE production caller chain (plus dev probe `probe_modal_prompt.py`). Never delete `run_prompt_stream` as "the V1 executor"; what retired was the direct un-planned invocation pattern.

---

## H. FINAL HISTORY ARCHITECTURE

- **History V2** (`history_v2.db`): generations/experiments/attempts/assets/export_records; append-only attempts; durable favorite/note columns; mixed feed with kind truth.
- **RequestSnapshots**: `execution_plan_json` is replay authority; snapshot hash validated; identity consistency enforced.
- **Replay**: Original/Retry/Resume/Again all replay the saved plan; `validate_replay_delta` allow-list only; Preview→Original conversion is the intentional delta on Generate Original; Resume preserves frozen mode.
- **Old rows**: migrated Singles carry copied provenance with honest `replay_capable:false`; mirrored terminal Experiment cells stay valid; never-mirrored legacy rows remain readable via hidden readers only.
- **run-history compatibility**: reads ×4 COMPAT_READ (rows never mirrored into V2 readable only here; logs/timing have NO V2 equivalent yet); writes ×2 COMPAT_WRITE (annotations/save) still live for fresh direct-run panels + stale persisted selections (retirement condition frozen FD-4: tag direct-run records as History-backed AND decide/expire the stale persisted population; once zero callers remain, a later wave may freeze).
- **Protected assets**: old images/assets untouched; `/studio/outputs/{filename}` + legacy output dir fallback retained while legacy-run images render.

---

## I. FINAL WORKFLOW ARCHITECTURE

Workflow → immutable WorkflowVersion (write-once) → immutable Mapping (insert-once) → version-scoped WorkflowPreset(s) (mutable values, version-tied) → accepted ExecutionPlan (runtime-derived, immutable per run). Stores: `.studio_workflows.json` / `.studio_workflow_versions.json` / `.studio_workflow_mappings.json` / `.studio_workflow_presets.json` — the ONLY graph authorities. Model Library (`.studio_model_library.json`) + custom-node registry (`.studio_custom_nodes.json`) own dependency truth. Portability: manifest v1 exact round-trip; dry-run-first atomic import; derived TTL-free fail-open cache sidecar; six advisory targets; environment isolation policy. Compatibility annotations are a separate feature (`/workflows/versions/{id}/compatibility`); never merged with portability. No PortableWorkflow entity, no second graph store, no provider-specific copies, no ZIP authority.

---

## J. FINAL BACKEND ARCHITECTURE

Modern Backend owns: workspace identity/lifecycle (`.modal_workspaces.json`, server-resolved active id; add/edit keep-current-token contract; multi-phase swap job that internally removes/installs models, syncs nodes, resyncs runtime), deployment/redeployment (explicit-only, dedupe, honest states incl. `deployed_unwarmed`), readiness/runtime health, logs (bounded viewer), credentials (workspace-scoped tokens; HF/Civitai; never echoed), snapshots, swap-blocking manifest repair, Backend Presets (transitional owner). `/studio/backends` is a MISNOMER: comparison-profile compatibility/import data (`.studio_backends.json`), NOT a provider registry, NOT modern Backend authority, NOT a portability matrix. Writers inert (409 `BACKENDS_READ_ONLY` ×4); GET hidden COMPAT_READ shim answering stored data; modern frontend consumers = 0.

---

## K. FINAL SETTINGS ARCHITECTURE

Surviving preferences: GPU default (server-authoritative catalog; reset to canonical default), Preview defaults (method/codec/quality), Outputs (format/quality/webp/auto-save/save-folder/sidecar/open-folder), History grid columns (consumed by the V2 grid), Interface preferences, Tracing LEVEL preference (persisted-vs-effective truth model). Reset All POSTs `{gpu: defaultGpu}` and resets tracing via its own route; durable namespaces (`playground.v1/drafts.v1/results.v1`, History view-state) are outside the reset set.

Removed authorities (must NOT return): Run mode (Cloud/Local), execution engine selector, legacy UI group, legacy settings overlay, Backends count row, workspace writer, deployment controls, provider selector. `comfymodal_enabled` has no modern writer/resetter. Residual "Runtime & Backend" informational rows (Deploy state, Snapshots count, Presets count, Open-Backend link) = OPTIONAL_G_HYGIENE display-only debt.

---

## L. FINAL CANVAS COMPATIBILITY BOUNDARY

Retained (Phase H preserved it deliberately): `/prompt` interception (`api.fetchApi` patch in `modal-node.js`; route === "/prompt" → `${MODAL_PREFIX}/prompt`); Local pass-through gated by persisted `comfymodal_enabled` read at startup into `window._comfyModalEnabled` (shim in minimal `modal-settings.js`; readers `!== false` at modal-node.js :678/:841 — undefined defaults enabled); Cloud path is V2-only with a 400 retired-mode guard; output-option chain (`window._comfyModalOutputOptions` + shared-helper maintenance); Production mode marking (`modal-node.js`, LS `comfymodal_production`). None of these are exposed as modern Studio execution choices. Canvas retirement is OUTSIDE Phase H and must not be attempted casually — it has its own compatibility population.

---

## M. FINAL COMPARISON STATE

UI retired (all module files deleted H18); execution retired (`POST /comparison/run` → 410 `COMPARISON_RETIRED`, body unparsed, zero executor/history/profile mutation); no modern Comparison domain exists; no slot-path mutation product flow; old A/B slider absent. Server compatibility retained: 10 COMPAT_READ routes answer stored data (profiles/results/workflow/config/gallery/validate/detect-slots — validate & detect-slots stay POST but are pure compute); 6 writers inert (409 `COMPARISON_READ_ONLY`). Stored profiles/manifests/results/gallery untouched. Physical route deletion = FUTURE_MAJOR_API. A/B image compare = PHASE_I_PRODUCT_WORK.

---

## N. FINAL EXPERIMENT STATE

Modern authority: `experiment-v2` (`POST /studio/experiment-v2`; Playground compose/run/live grid; History V2 records/actions). Legacy: creation/execution writers inert (10× 410 `EXPERIMENT_RETIRED`, 5× 409 `EXPERIMENT_READ_ONLY`); old-data readers retained where required (5 COMPAT_READ); compile stays pure-compute ZERO_CALLER per FD-12. Protected seams survive byte-untouched: `GET /experiments/{id}` (`__init__.py` :5521) and `POST /experiments/{id}/stop-now` (:5912). WHY they still exist: they are the Single run's wired progress-poll (`getStudioRunStatus`) and Cancel (`stopExperiment`) transport — an implementation seam over the legacy experiment-service REGISTRY, classified TRANSITIONAL_MODERN with `WAVE_F_DO_NOT_FREEZE=TRUE`. They execute nothing and are NOT a second modern Experiment product authority. For direct V2 single runs the GET 404s harmlessly and stop-now is a harmless 404 (no scheduler exists for direct runs).

---

## O. FINAL PRESET TAXONOMY

Three distinct systems, never merged:

1. **Workflow Presets** — Workflows-owned, version-scoped, `.studio_workflow_presets.json` via `/studio/workflows/*/presets*`. MODERN_LIVE.
2. **Backend/Runtime Presets** — `.studio_presets.json` via `/studio/presets*`; consumed by Playground runtime selection (`getRuntimePresets` → carried as `presetId` on `POST /studio/run`), Backend tab CRUD, preset wizard. **MODERN_LIVE_TRANSITIONAL** — intentionally NOT converged during H because History `preset_id` provenance spans both namespaces by era (merging would falsify provenance) and consumers were never migrated. Convergence remains a future explicit architecture decision (FUTURE_ARCH_DECISION).
3. **Legacy prompt/image presets** — `.presets/prompts|images`; data readable for compatibility (COMPAT_READ ×4); writes frozen (RETIRED_WRITE ×8, 409 `LEGACY_PRESETS_READ_ONLY`); UI retired.

---

## P. FINAL ROUTE CLASSIFICATIONS

Vocabulary (FD-2): MODERN_LIVE / TRANSITIONAL_MODERN / COMPAT_READ / COMPAT_WRITE / RETIRED_WRITE / RETIRED_EXECUTION / INTERNAL_ONLY / ZERO_CALLER / UNKNOWN(=0 everywhere).

| Family | Classes |
|---|---|
| Modern core | `/studio/run`, `/studio/experiment-v2`, `/history-v2/*`, Workflow domain routes, workspaces/deploy/credentials/models/custom-nodes/snapshots, `/history` platform feed, canvas `/prompt` chain = MODERN_LIVE |
| Single seams | `GET /experiments/{id}`, `POST .../stop-now` = TRANSITIONAL_MODERN PROTECTED |
| Legacy Experiment (22+1) | COMPAT_READ ×5 · ZERO_CALLER ×1 (compile) · RETIRED_EXECUTION ×10 · RETIRED_WRITE ×5 · MODERN_LIVE ×1 |
| Comparison (17) | COMPAT_READ ×10 · RETIRED_WRITE ×6 · RETIRED_EXECUTION ×1 |
| run-history | COMPAT_READ ×4 · COMPAT_WRITE ×2 |
| `/studio/backends` | GET COMPAT_READ · writers ×4 RETIRED_WRITE · modern callers 0 |
| Warmup | status ZERO_CALLER · run RETIRED_EXECUTION · invalidate RETIRED_WRITE |
| auth/setup | RETIRED_WRITE |
| Legacy prompt/image presets | reads COMPAT_READ ×4 · writes RETIRED_WRITE ×8 |
| Backend/Runtime Presets | MODERN_LIVE_TRANSITIONAL |

Response standard (FD-17): EXECUTION retirement → HTTP 410 `<FEATURE>_RETIRED`; WRITE retirement on readable compat data → HTTP 409 `<FEATURE>_READ_ONLY` (warmup invalidate intentionally uses 409 `WARMUP_RETIRED`). All bounded deterministic JSON, no body parsing where irrelevant, no mutation before response.

---

## Q. FILES DELETED / MAJOR DEAD-CODE CLEANUP

**H18 frontend deletions (9 files):** `web/testing-setup.js`, `testing-profiles.js`, `testing-results.js`, `testing-settings.js`, `testing-ab-slider.js`, `studio-legacy.js`, `modal-comparison.js`, `testing-api.js`, `testing-setup-adapter.js`. Plus: `modal-settings.js` rewritten 4139→158 lines (kept: `_comfyModalEnabled` startup shim, output-preferences wiring, read-only GPU sync, redeploy-restart banner, extension registration); `modal-testing.js` draft/preview/experimentId machinery removed (alias map/sidebar/wizard-sync kept); dead API helpers deleted from `studio-backend-api.js`/`studio-backend.js` (`getBackends`, `getCompareBackends`, `runStudioExperiment`, `listExperiments`, `listRunHistory`, `listUnifiedHistory`, `getModalConfig`); testing-styles pruned to live tokens; two dead CSS blocks in studio-styles.js.

**Earlier wave deletions:** H9 deleted `web/studio-history.js`, `testing-dashboard.js`, `testing-history.js`. H11 deleted `is_v2`/`is_shadow`.

**H19 Python deletions:** `_execute_comparison_profile`, `direct_studio_run_completion`, `execute_modal_prompt`, `prepare_modal_execution`, `LocalRemoteInvoker`, `_prepare_studio_run_context`, `_handle_studio_run_scheduler`, `_playground_runtime_mode`, four dead warmup helpers, orphaned imports. Census: direct `run_prompt_stream` calls in `__init__.py` = `[]`.

**Intentionally remaining:** `modal_client.run_prompt_stream` (V2 transport), REGISTRY history readers + `history_index.py`, `legacy_mapping` + dormant `LegacyMigrationSeam`, replay-capability projection, workspace fallback, `GET /history`, all COMPAT_READ services, protected-seam handlers, `CheckpointStreamInvoker` (recovered-scheduler path), `WarmupState` (deploy truth), `_schedule_and_start`+`V2ExperimentInvoker` chain (pinned seam), `handle_studio_experiment`/`build_single_run_spec`/`_collect_input_images`/`createScopedTracker` (OPTIONAL_DELETE candidates), MARK_OPTIONAL span vocabulary (KEEP_COMPAT).

---

## R. TEST ARCHITECTURE

- Gate command: `python tests/run_studio_tests.py --fake` → Python lane (allowlist `STUDIO_PY_MODULES` 40 modules + `PYTEST_STYLE_FILES` 5 files, fresh-built suite each run, no discovery cache) + Node unit lane (`NODE_UNIT_FILES`, 25 files) + fake Playwright wrapper (`npm run test:fake`).
- Exact fake count requires the direct command: `npx playwright test --config=playwright.fake.config.mjs --reporter=line` → **211**.
- Final registered counts: **Python 2124 · Node 25 files · Fake 211 exact**.
- Major registered families: shell/navigation (`test_testing_shell_integration`, `test_testing_ui_wired`, `test_modal_workspace_ui_ast`), backend (`test_studio_backend`, `test_routes_registered`), execution V2-only (`test_phase8_execution_mode` 41, `test_h12_v2_only_consolidation` 21, `test_studio_direct_run`, `test_workflow_run_integration`), GPU (`test_f8_gpu_authority` 41), API freeze (`test_h14_wave_e_retirement` 30, `test_h15_wave_f_server_freeze` 36), History V2 families (`test_history_v2_*`), Workflows/portability (`test_workflow_*`, `test_portability_*`), Model Library (`test_model_library*`, `test_dependency_resolver`), presets (`test_presets_*`), progress/annotations (`test_studio_progress_annotations` 71), run-history family (+143).
- Node units include H6 ops (24 sections), H7 parity (16 sections), settings-compat authority (renamed from legacy-settings-authority after overlay deletion), e4c/e4d retry, f4/f8 phase units.
- Fixture-leak fixes landed in H20: F8 GPU restore via addCleanup; workflow-run suite pins `set_writer_enabled(False)` against the stub-server harness leak.
- Fake known timing flake: see §S.

---

## S. KNOWN FLAKES / ENVIRONMENTAL FACTS

1. **Fake parallel-load lifecycle flake**: `tests/browser/fake/studio-fake-lifecycle.spec.mjs` test 11 ("workflow node progress is not overwritten by sampler max") can time out (20–30 s wait) under full-suite parallel load. First recorded FD-1 (H5D); recurred in FF-2/H20 §22 and once in this closure batch (first direct run 210/1; immediate direct rerun 211/211; passes in isolation). **Environmental parallel-load timing behavior, NOT a current product bug.** Protocol: preserve evidence, rerun direct, never weaken timeout/assertion, classify only with existing evidence.
2. **Dirty `comfyapp.py`**: carries a UTF-8 BOM permanently (HEAD and worktree). Registered suites tolerant (`test_comfyapp_ast`, `test_comfyapp_packaging` green). Some out-of-gate suites (`test_v2_16_20_patch` version pin etc.) target attributes absent even at HEAD — pre-existing observations, not Studio-gate items.
3. **F8/workflow reverse-order artifact**: FIXED in H20 (was a stacked fixture leak: un-restored `_current_gpu` + stub-server `sys.modules["server"]` enabling the production writer singleton). Matrix A–E green post-fix.
4. The tree is intentionally dirty since before Phase E; there are no Phase-H commits; file-level dirtiness ≠ any single lane's ownership.

---

## T. OPTIONAL NON-BLOCKING HYGIENE

| Item | Disposition |
|---|---|
| `handle_studio_experiment` (zero production callers; F8-test seam) | OPTIONAL_DELETE (migrate tests first) |
| `build_single_run_spec` (production-orphaned; pinned by registered compilation suites) | OPTIONAL_DELETE (de-pin first) |
| `__init__._collect_input_images` (zero production callers; live twin in canonical_execution) | OPTIONAL_DELETE (migrate tests to twin) |
| `createScopedTracker` export (zero production consumers) | OPTIONAL_DELETE |
| MARK_OPTIONAL legacy span names | KEEP_COMPAT (trace-data vocabulary) |
| ~40 registered-and-inert compatibility routes | KEEP_INERT_COMPAT now; FUTURE_MAJOR_API for physical pruning |
| Residual Settings Runtime & Backend informational rows | OPTIONAL_G_HYGIENE (display-only) |
| `_schedule_and_start` + legacy Scheduler/Runner chain | FUTURE_ARCH_DECISION (bundle with route pruning; V2ExperimentInvoker preservation mandate vs zero callers) |

None of these blocks Phase I.

---

## U. FUTURE-MAJOR API ITEMS

Route pruning decision: **`PHASE_H_ROUTE_PRUNING_REQUIRED = NO`** (re-verified: handlers bounded/non-mutating; maintenance/security cost negligible; old-client truthfulness benefits from explicit 409/410; no duplicate product authority; registry pins + fake parity stay valid without deletion cascades). Physical pruning is DEFER_FUTURE_MAJOR — if ever done, it must bundle same-change registry-pin/fake/spec updates (H3 §13 #11 rule) and should decide the `_schedule_and_start`/invoker-chain disposition together. Backend/Runtime Preset convergence is likewise a future explicit contract (conditions frozen in FD-6).

---

## V. PHASE-I ROADMAP (do not implement without a new mandate)

From H5 §29 + follow-ups: lightweight A/B image slider (History/Experiment result space); navigation/accessibility polish (`aria-current`, keyboard semantics); responsive nav redesign; heading hierarchy cleanup; generic loading component; chip visual taxonomy (incl. portability-vs-compatibility distinction); wording/verb polish ("Make Preset"/"New Preset"/label normalization; Settings info-row copy); URL/deep-link routing infrastructure; general focus-visible polish; cross-tab state sync; deeper model/custom-node entry links beyond landed basic behavior.

Distinctions: **PHASE_I_PRODUCT_WORK** = the list above. **OPTIONAL_G_HYGIENE** = §T items (need not precede Phase I). **FUTURE_MAJOR_API** = §U items (require their own contracts).

---

## W. DO-NOT-BREAK INVARIANTS (consolidated numbered list)

Inherited Phase-F (1–14):
1. Immutable execution plan for re-execution; never reconstruct from current state; fail closed for legacy rows.
2. Durable History is the action-state authority; no optimistic fabrication.
3. Managed assets are authoritative internal assets; `modal://` is URI-aware, reference ≠ absence.
4. Export copies ≠ managed assets.
5. Browser Download has zero durable server side effects.
6. Original is never eager-loaded.
7. Preview and Original are semantically distinct.
8. Stable logical-output identity; retries never inflate outputs.
9. Attempts append-only; first-terminal-wins.
10. interrupted→Resume; failed→Retry; canceled→never resumed.
11. Selected GPU frozen at acceptance; replay/resume/retry reuse verbatim.
12. Experiment concurrency fixed at 6.
13. No browser fanout for execution actions.
14. Export is per-asset, bodyless, server-derived; file-before-record ordering.

Inherited Phase-G (15–42):
15. WorkflowVersion is the portability analysis unit.
16. One graph authority (no PortableWorkflow, no second store).
17. Manifest v1 sole portability artifact; checklist derived advice only.
18. ExecutionPlan is not a portability payload.
19. Exact persisted graph/API JSON round-trips byte-equal.
20. Foreign ids are provenance only.
21. Import dry-run precedes commit; committed import atomic/compensated.
22. Missing dependencies import but never bypass run gating.
23. No auto-install/fetch/shell during import/export.
24. Workflow risk ≠ target readiness ≠ environment reproducibility; UNKNOWN never becomes LOW.
25. Six frozen target ids; advisory only; never execution engines.
26. Cache derived-only, evidence-based invalidation (no TTL), null-always-stale, fail-open corruption, never gates anything.
27. Workflow list never performs live analysis; browser never computes risk.
28. Secrets/local install paths never exported; credential-shaped export refuses closed.
29. Graph identity = canonical hash of executable API prompt (intentional dedupe rule).
30. Stale results never presented as current.
31. Portability vocabulary distinct from model-compatibility.

Phase-H final (32–57):
32. Top nav remains exactly five surfaces; no new top-level tabs.
33. Modern Studio execution = Modal V2, single engine; env vocabulary `{v2}`.
34. Portability targets are advisory analysis, never selectable execution.
35. WorkflowVersion immutable; Mapping insert-once.
36. History replay authority remains `RequestSnapshot.execution_plan_json`.
37. No live domain lookup added to History render/replay (workspace fallback is the ONLY sanctioned external resolution).
38. Legacy irreproducible rows remain honestly irreproducible.
39. No destructive historical-data migration of ANY store.
40. Workspace fallback for old snapshots retained until pre-workspace-id snapshots vanish from user data.
41. Settings owns preferences only.
42. Backend owns operational Modal state.
43. Workflows owns Model Library/dependencies/portability.
44. History V2 remains sole durable History.
45. Modern Experiments = Playground compose/live + History records/actions; no third surface.
46. Comparison stays retired; no modern Comparison domain; no slot-path mutation; A/B slider is Phase-I justification for nothing.
47. Legacy canvas remains compatibility-only (interception, pass-through gate, output chain, production marking).
48. Old data readers may outlive old UI; UI retirement does not imply store deletion.
49. No new legacy writes after creator-authority retirement (freeze classes 409/410 stand).
50. Model Compatibility ≠ Portability; `compatible_models` untouched on Versions.
51. Portability cache remains derived/non-gating/TTL-free.
52. GPU server-authoritative and frozen per plan; replay/resume/retry never reread GPU or Settings.
53. New modern runs remain V2-only; retired modes recognized/rejected/migrated, never executed.
54. `.studio_presets.json` (Backend/Runtime Presets) remains live until its convergence contract lands.
55. Protected Single seams (`GET /experiments/{id}`, `stop-now`) must not be frozen/deleted while wired.
56. run-history annotations/save remain COMPAT_WRITE until their frozen retirement condition completes.
57. Any production route behavior change requires same-change fake-mirror/spec updates.

---

## X. VALIDATION CONVENTIONS

Deterministic Studio gate (the ONLY routine validation):

```
python tests/run_studio_tests.py --fake
npx playwright test --config=playwright.fake.config.mjs --reporter=line   # exact count
```

Expect Python 2124 / Node 25 / Fake 211. On the known flake (§S): rerun direct; do not weaken anything. Registration changes go through `tests/run_studio_tests.py` allowlists (never double-register; respect documented ordering constraints: stub-server-harness suites after the Workflows block).

Live Modal validation philosophy (separate activity, NEVER part of deterministic gates): live deploy/run/GPU work requires explicit user authorization, is excluded from every Phase-H batch, and historically has its own campaign reports (E7 was the last live evidence; G/H touched no replay-execution semantics). Do not invoke Modal, deploy, or generate on GPUs while closing/auditing phases.

---

## Y. CURRENT KNOWN TRANSITIONAL SEAMS

| Seam | Status | Retirement condition |
|---|---|---|
| Backend/Runtime Presets (`.studio_presets.json`) | MODERN_LIVE_TRANSITIONAL | Future explicit convergence contract (consumer migration + provenance re-verification) |
| run-history annotations/save COMPAT_WRITE pair | Live (fresh direct-run panels + stale persisted selections) | Tag direct-run records as History-backed AND expire stale population; then freeze in a later wave |
| Protected Single detail/stop-now routes | TRANSITIONAL_MODERN, wired | Successor Single transport (LATER_INTERNAL_REFACTOR; do not invent one for naming purity) |
| Canvas compatibility layer | Retained deliberately | Separate future decision; must not block anything |
| Settings Runtime & Backend informational rows | Display-only debt | Optional hygiene removal |
| Inert registered compatibility routes (~40) | KEEP_INERT_COMPAT | FUTURE_MAJOR_API physical pruning |

These are NOT bugs by themselves.

---

## Z. EXACT NEXT SAFE STARTING POINT

A fresh agent may safely assume:

- **Phase H is closed** (`PHASE H COMPLETE`; final gate 2124/25/211 green on the closure tree).
- There is ONE modern Studio architecture: five surfaces, V2-only execution, History V2 sole durable authority, Workflows domain authority, Backend operational authority, Settings preferences-only authority.
- No legacy UI authority exists anywhere user-reachable; compatibility routes are deliberately retained and inert where retired.
- Do NOT reopen legacy architecture, recreate retired surfaces, or reinterpret retired strings as engines.
- Optional cleanup (§T) does NOT need to precede Phase I.
- Next architecture/product work is **Phase I** (§V list) unless the user chooses another project objective; any Backend/Runtime-Preset convergence or route pruning needs its own explicit contract batch first.
- Keep the working tree dirty/shared discipline and the batch report conventions (verdict + exact counts + files-modified-by-this-lane + "deploy/live/GPU/commit/push: NONE") used by every report in this series.

Authoritative reading order for a new session: this handoff → `PHASE_H_FINAL_CLOSURE_2026-08-25.md` → `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (incl. Follow-Ups A–G) → `PHASE_G_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` → `PHASE_F_FINAL_CLOSURE_ZERO_CONTEXT_HANDOFF_2026-08-23.md` → individual wave reports as needed.

---

## FINAL VERDICT

`PHASE H COMPLETE`

Deploy / live / GPU / generation / commit / push by the H21 closure batch: **NONE**.
