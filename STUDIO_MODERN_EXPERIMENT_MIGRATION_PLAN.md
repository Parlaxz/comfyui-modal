# Studio Modern Experiment Migration Plan

| | |
|---|---|
| Batch | C2 — Modern Experiment Migration (read-only architecture plan) |
| Date | 2026-08-14 |
| Status | COMPLETE (plan only; no production code changed) |
| Rev | 2 — Batch C2 Follow-Up contract corrections: Generate Original = rerun; recovery preserves queued cells; no `partial` status; workflow-axis resolution exposed |
| Gate | Implementation starts ONLY after modern Single execution completes one successful live smoke (Batch C1 gate) |
| Scope | Migrate Experiment execution from the legacy Preset/tracker/scheduler path to ordinary modern Workflow generation requests |

---

## 0. Constraints & Non-Negotiables (from batch brief)

- Experiments live inside Playground. An Experiment is a batch of ordinary independent generation requests. No special backend architecture.
- Cells are fixed. Global default concurrency = 6. Continuously fill available slots. Each cell is one Generation.
- Failure remains in its cell. Retry creates a new attempt for the same cell. Cancel truthfully stops active + queued work where possible.
- Closing the Playground popup does not stop the Experiment. Closing ComfyUI creates Interrupted state. Reopen offers explicit Resume for unfinished/interrupted/not-started cells. Failed cells require Retry, not Resume.
- Generate Original is per cell. Experiment may span Workflows. History displays one Experiment card with its cells.
- No silent replacement/substitution of Workflow Version/Preset.
- Do NOT modify: `studio_workflow_run.py`, `history_v2_writer.py`, `web/studio-playground.js`, `comfymodal_runtime/**`, `experiment_service.py`, `experiment_runner.py`, `studio_run_adapter.py`. Reuse read-only.
- Do not deploy, do not run real generations, do not alter the Studio test gate. Test gate = `tests/run_studio_tests.py --fake` + `npm run test:fake` (deterministic only).

---

## 1. Current Architecture (Task 1 — traced path)

### 1.1 Entry points

| Hop | Where | Notes |
|---|---|---|
| Compile | `POST /comfymodal/experiments/compile` (`__init__.py:5723`) → `matrix_compiler.compile_experiment` (`matrix_compiler.py:98`) | Legacy axis compiler |
| Create | `POST /comfymodal/experiments` (`__init__.py:5767`) → `REGISTRY.store` + History V2 `ensure_experiment` (`:5836`) | |
| Studio experiment | `POST /comfymodal/studio/experiment` (`__init__.py:7454`) → `handle_studio_experiment` (`studio_run_adapter.py:4021`) → `build_experiment_spec` (`:1485`) → `_create_experiment` (`:3073`) → fire-and-forget `_schedule_and_start` (`:2500`) | The Playground path |
| Scheduler boot | `_schedule_and_start` → invoker by mode (`V2ExperimentInvoker` or `LocalRemoteInvoker`) → `REGISTRY.get_or_create_scheduler` (`experiment_service.py:239`) → `await sched.start()` | |

### 1.2 Axis expansion → cells

- `matrix_compiler.compile_experiment` (`matrix_compiler.py:98`): cartesian nesting per `_CHEAP_AXIS_ORDER` (`:56`; seed innermost), range-mode expansion (`_axis_values`, `:374`), `WORKFLOW_OWNED` sentinel (`:29`).
- Cell structure (`_build_cell`, `matrix_compiler.py:535-655`): `cell_key` (sha256), `sequence`, model triple, `lora_signature`, `prompt`, `negative_prompt`, `input_image_hash`, `normalized_dimensions`, `axis_values` (`:70-93`).
- Playground axes are expanded in `build_experiment_spec` (`studio_run_adapter.py:1569-1660`).

### 1.3 Cell/request generation (legacy)

- `resolve_and_inject_cell` (`experiment_runner.py:257-600`): deep-copies the checkpoint profile workflow and **mutates arbitrary graph fields via slot paths** (`_set_path_value` `:192`, `_set_field` `:239`) after preflight mapping checks (`:295-357`). Injects prompt, negative, model triple, LoRA chain, 6 sampler axes, resolution, i2i image (`:361-539`). Throws `MissingMappedField` for unmapped axes (`:479`).
- **This is the logic that must NOT be duplicated.** The target reuses the modern mapping/control path instead.

### 1.4 Legacy preset concepts (three, plus one modern)

| Concept | File | Role |
|---|---|---|
| Prompt/image presets | `presets.py` | Content-hash referenced inputs (i2i), SHA-256 verified (`experiment_runner.py:111-138`) |
| Comparison profiles (legacy "preset") | `comparison.py:718`, enriched in `__init__.py:5703` | Workflow + slots + loader groups merged via slot-path mutation |
| Studio preset/snapshot | `studio_run_adapter.py:551, 947, 992` | `.studio_presets.json` + `.studio_snapshots.json`, nodeBindings → slots |
| **Modern workflow platform** | `studio_workflow_routes.py:6-8`, `studio_workflow_run.py:59-60`, `studio_domain.services` | `.studio_workflows.json` / `_versions` / `_mappings` / `_presets`, immutable versions, control-schema mappings, runnable presets |

### 1.5 Legacy scheduler / status / progress

- `experiment_scheduler.py` — own status family: `draft, running, pause_requested, paused, stop_after_current_requested, stop_now_requested, stopped, completed, completed_with_failures, failed_fatal` (`:40-49`); `TERMINAL_STATUSES` (`:52`); completion inference `_compute_terminal_status` (`:353-395`) from journal snapshots; persisted `scheduler_state.json` (`experiment_service.py:384-406`, `:539`); `recover_scheduler` (`experiment_service.py:265-382`) coerces running-like statuses to `paused` and invalidates leases.
- Concurrency: cells grouped by checkpoint (`experiment_runner.py:859-861`), one `asyncio.Semaphore(max_containers)` (`:864`), one Modal invocation per checkpoint (`CheckpointStreamInvoker._drive`, `:1697, 1845`).
- Poll cascade: UI polls `GET /experiments/{id}` every 3 s (`studio-playground.js:78, 217-303`); events via `GET /experiments/{id}/events` (`__init__.py:5916`); WS via `_EventBridge` (0.2 s loop, `experiment_service.py:492-509`) → `experiment.event` / `experiment.worker.progress`.
- Scoped tracker: `WorkerProgressBuffer` (`experiment_service.py:109-191`), per-experiment, in-memory only.
- Request IDs (legacy): `w_<8>` worker invocation, `a_<8>` attempt, `r_<12>` run, `ck_` checkpoint, `studio_<16>` exp, `studio_cell_<8>` cell, Modal `prompt_id` = cell_key.
- Cancellation: `POST .../stop-now` (`__init__.py:6358`) → `sched.stop_now` (`experiment_scheduler.py:174`) → `runner.stop_now` (`experiment_runner.py:811-830`, lease invalidation `experiment_lease.py:197-273`) → `invoker.cancel_worker` (`:1886-1924`, `ControlBackend` stop_now). Late events rejected by `validate_and_accept` (`experiment_lease.py:386-447`).

### 1.6 History writes today

- Legacy: `RunHistoryService.record_run` (`experiment_service.py:862-910`) → `.run_history/<run_id>/meta.json` + `HistoryIndex` + `_v2_try_mirror_record` (`:800`). Cell history: `_record_experiment_cell_history` (`__init__.py:6034-6085`), terminal events only, from `_on_remote_event` (`__init__.py:6087`).
- Modern writer: `HistoryV2ProductionWriter` — `record_run` (`history_v2_writer.py:388`), `update_run` (`:496`), `mirror_cell_terminal` (`:784`), `ensure_experiment` (`:991`), `finalize_experiment` (`:1046`). Deterministic ids `gen_/run_/cell_` + sha256 (`:131-152`).

### 1.7 Modern single path (the target template)

```
Workflow → Version (immutable) → Mapping → Preset → run-context
→ merge_workflow_controls(preset, overrides, control_schema)   studio_workflow_run.py:283
→ apply_workflow_values_to_prompt                                studio_workflow_run.py:355
→ build_workflow_execution_plan(bundle, values, ...)             studio_workflow_run.py:462
→ canonical execute_plan / execute_modal_prompt                 canonical_execution.py:1427 / :3305
→ History V2 (writer)                                           history_v2_writer.py
```

- Route branch: `POST /comfymodal/studio/run` (`__init__.py:7298`); modern branch when `workflow_version_id` present → `handle_workflow_run_async` (`studio_workflow_run.py:1004`), wrapped in `asyncio.wait_for(..., 600)` (`__init__.py:7377-7387`). **Modern single is synchronous; it has NO cancel and writes History only at completion (V2) or submission+running (v1).**
- Immutability: `ExecutionPlan` is a frozen dataclass with `MappingProxyType` everywhere (`comfymodal_runtime/contracts.py:805-841`); `workflow_hash` = `prompt_sha256` (`workflow_metadata.py:45`); deployment identity frozen post-deploy (Batch C1: `canonical_execution.py:1046-1271`).
- The composable, Experiment-reusable seam is the chain:
  `resolve_workflow_run_bundle` (`:84`) → `merge_workflow_controls` (`:283`) → `apply_workflow_values_to_prompt` (`:355`) → `build_workflow_execution_plan` (`:462`).

---

## 2. Legacy Dependencies (Task 2 — classification)

Classification: **A** = must be replaced · **B** = can remain temporarily · **C** = can be deleted after migration · **D** = unrelated.

| Legacy dependency | Where | Class | Notes |
|---|---|---|---|
| Runtime Preset graph-injection (`resolve_and_inject_cell` slot-path mutation) | `experiment_runner.py:257-600` | **A** | Replaced by modern mapping/control merge. Must not be copied. |
| Comparison-profile "preset" enrichment | `__init__.py:5703`, `comparison.py` | **A** (C after) | Replaced by workflow presets/versions. |
| Prompt/image preset blob store | `presets.py`, `experiment_runner.py:111-138` | **B** | Keep as i2i input-asset source (content-hash references); orthogonal to execution migration. |
| Scoped tracker (`WorkerProgressBuffer`) | `experiment_service.py:109-191` | **A** | Replaced by per-cell canonical runs + frontend per-experiment controller. |
| Old status vocabulary (`draft/running/pause_requested/…/failed_fatal`) | `experiment_scheduler.py:40-52` | **A** (B at boundary) | New path uses canonical `queued/running/completed/failed/canceled/interrupted`; keep legacy route responses for old cards only. |
| Old poll cascade (3 s `GET /experiments/{id}` + events journal) | `studio-playground.js:217-303`, `__init__.py:5916` | **A** (B for legacy cards) | New path: per-experiment canonical controller + status endpoint + existing WS channels. `studio-playground.js` itself is C1-owned and must not change — experiment mode must adopt the controller branch (`:202-207`) which already exists. |
| Old request IDs (`w_/a_/r_/ck_/studio_`) | `experiment_runner.py:928, 945`, `experiment_service.py:875` | **A** (C after) | New path uses deterministic History V2 ids (`gen_/run_/cell_` pattern, `history_v2_writer.py:131-152`). |
| Legacy completion inference (`_compute_terminal_status` from journal snapshots) | `experiment_scheduler.py:353-395`, `experiment_store.rebuild_snapshot` (`:272-455`) | **A** | Replaced by `derive_experiment_status` over canonical cell attempts (`history_v2_models.py:148-184`). |
| Special scheduler state (`.scheduler_state.json`, recover→paused coercion, lease invalidation) | `experiment_service.py:265-406`, `experiment_scheduler.py:539` | **A** | Replaced by History V2 as the durable scheduler state + startup recovery sweep. |
| Lease registry / event validation | `experiment_lease.py` | **B** (C after) | Still used by legacy single scheduler path (`direct=False`); new path uses attempt-identity checks instead of leases. |
| Journal/events store | `experiment_store.py` | **B** (C after) | Read-only for old experiment cards. |
| Axis matrix expansion (cheap-axis nesting, ranges, axis_values) | `matrix_compiler.py:56-374` | **B** | Pure axis-value expansion is reusable; graph injection must not be. |
| Legacy Studio experiment route + `_schedule_and_start` | `studio_run_adapter.py:4021, 2500` | **A** | Replaced by new modern endpoint (file itself untouched — C1-owned). |
| Old WS event names (`experiment.event`, `experiment.worker.progress`) | `experiment_service.py:453`, `comfymodal-progress.js:943-1085` | **B** | Scoped tracker already understands them; new path may emit the same channel. |
| Legacy run-history meta.json mirror | `experiment_service.py:800-910` | **C** | V2 mirror supersedes. |
| History V2 writer (`record_run`/`update_run`/`mirror_cell_terminal`/`ensure_experiment`) | `history_v2_writer.py` | **Reuse read-only** | The migration target; already routes on `meta.experiment_id`/`meta.cell_key` (`:414-432`). |
| Modern request-builder chain | `studio_workflow_run.py:84-565` | **Reuse read-only** | The seam every cell must go through. |

---

## 3. Target Architecture (Task 3, Task 6)

```
Playground Experiment UI (studio-experiment-mode.js)
  → one definition: workflow(s), version(s)/preset(s), axis defs, concurrency=6
  → POST /comfymodal/studio/experiment-v2          (new route)
  → Cell Plan Generator (new module, pure):
        axes × presets → ordered immutable cell list
        per cell: workflow_id, workflow_version_id, preset_id,
                  axis labels/values, mapped control overrides
  → Modern Scheduler (new module):
        fixed cell list · concurrency 6 · fill slots continuously
        each cell → resolve_workflow_run_bundle → merge_workflow_controls
                    → apply_workflow_values_to_prompt → build_workflow_execution_plan
                    → canonical execute_plan (background asyncio task)
        per-cell terminal → History V2 writer (record_run/update_run/mirror_cell_terminal)
  → aggregate derived from cells (derive_experiment_status)
  → GET status endpoint + existing WS channels → frontend controller → grid/progress
```

Principles:
- **No duplicate graph-merge logic.** Every cell is an ordinary modern request produced by the exact same seam Single uses (section 1.7). The legacy `resolve_and_inject_cell` and profile-slots machinery are not reused for execution.
- **One generation per cell; one active attempt per cell at a time; attempts are append-only.**
- **History V2 is the durable state.** No `.scheduler_state.json`, no journal, no leases for the new path.
- **Cells run as independent asyncio tasks** (not one shared Modal invocation, unlike the legacy checkpoint-stream model). This is what makes per-cell cancel/failure isolation and continuous slot filling trivial.
- **Synchronous submit, asynchronous execution.** The start route returns `{experiment_id, cell_count}` immediately; the scheduler owns background tasks.

### 3.1 Cell request contract (Task 3)

Each cell resolves to an ordinary modern request carrying:

| Field | Source | Notes |
|---|---|---|
| `experiment_id` | created experiment | Writer routes on this (`history_v2_writer.py:414-432`) |
| `cell_id` / `cell_key` | deterministic (position + axis-values hash) | Stable across attempts/resume; `cell_` prefix pattern |
| `workflow_id` | cell plan | May differ per cell (workflow axis) |
| `workflow_version_id` | cell plan (immutable, baked at plan time) | Persisted on `generations.workflow_version_id` (`history_v2_store.py:79`) |
| `preset_id` | cell plan (immutable, baked at plan time) | Persisted on `generations.preset_id` |
| `axis_labels` | axis name(s) | Persisted `experiment_cells.axis_labels_json` |
| `axis_values` | per-axis value(s) | Persisted; used for grid display + `generation_params_json` |
| `controls` (exact mapped overrides) | axis values → control-schema fields | Only mapping-exposed controls; validated by `validate_workflow_controls` (`studio_workflow_run.py:221`) |
| `immutable executable request` | `build_workflow_execution_plan` output | Frozen `ExecutionPlan` + `workflow_hash` + `deployment_identity` (C1) |
| `attempt_id` / `run_id` | fresh per submission | `run_` prefix; new identity on Retry/Resume |
| `modal_options` | experiment-level passthrough | GPU/region etc. from the single-run path |

Reuse exactly: `resolve_workflow_run_bundle` (`studio_workflow_run.py:84`) → `merge_workflow_controls` (`:283`) → `apply_workflow_values_to_prompt` (`:355`) → `build_workflow_execution_plan` (`:462`), then canonical `execute_plan` (`canonical_execution.py:1427`). No new request-builder may be written.

Resolved `workflow_version_id`/`preset_id` (including workflow-axis resolutions, section 4) are part of the cell plan record and are exposed verbatim by the status and history APIs; the UI shows the resolved values, and execution never re-resolves them.

---

## 4. Workflow Axis (Task 4)

- The axis value names a Workflow. Version and Preset are resolved **once, at cell-plan build time**, never at execution time:
  - Explicit: axis definition may pin `(workflow_id, workflow_version_id, preset_id)` — used verbatim.
  - Workflow-only: resolve `version = workflow.latest_version_id`, `preset = workflow.default_preset_id` **at plan generation** (same rule as `resolve_workflow_run_bundle`'s empty-version fallback, `studio_workflow_run.py:118, 172`).
- **Resolution is frozen into the cell plan.** The resolved `workflow_version_id` and `preset_id` are persisted in the cell plan record (and on the generation row + `request_snapshots`) at plan-build time — they are data of the plan, not a lookup performed at execution.
- **UI/status/history expose the resolved values.** The status endpoint and History V2 detail return the resolved `workflow_version_id`/`preset_id` (and their names) per cell, so the user sees exactly what will run; the UI renders the resolved Version/Preset, not "latest".
- **Execution never re-resolves latest/default.** The run path consumes only the baked ids from the plan; it has no code path that consults `latest_version_id`/`default_preset_id` at submission or execution time.
- **No silent substitution after plan creation.** If `workflow.latest_version_id` changes after the plan is generated, existing cells keep their baked ids. If the baked version becomes unrunnable, the cell fails with the existing `WORKFLOW_VERSION_NOT_RUNNABLE` reasons (`studio_workflow_run.py:131-136`) — it never silently slides to another version.
- Every cell plan prefers immutable IDs; the `workflow_hash` from the plan is stored in `request_snapshots` (writer already does this when `meta.workflow_json` is supplied).
- Determinism test: simulate a workflow gaining a new latest version between plan build and run; assert cell plans unchanged.

---

## 5. Other Axes (Task 5)

Axis → mapped control mapping (modern controls only, per the selected Version's Mapping control schema; **an axis is valid only when the mapping exposes the control** — the frontend already implements this gating via `getAxisEligibilityForPresets` (`studio-preset-capabilities.js:488-522`) and `CONTROL_DEFS.experimentEligible` (`studio-feature-registry.js:37-205`)):

| Axis | Maps to (control / override) | Valid only when mapping exposes |
|---|---|---|
| Prompt | `prompt` control | yes |
| Negative prompt | `negative_prompt` control | yes |
| Steps | `steps` | yes |
| Guidance/CFG | `guidance` | yes |
| Denoise | `denoise` | yes |
| Seed | `seed` | yes |
| LoRA strength | `lora_strength` | yes |
| Mask blur | `mask_blur` | yes |
| Mask expand | `mask_expand` | yes |
| Sampler | `sampler` | yes |
| Scheduler | `scheduler` | yes |
| Model (where permitted) | `model_choices` override (wins over preset values in `merge_workflow_controls`, `studio_workflow_run.py:304-307`) | only when mapping defines model choices |
| Width/Height | `width`/`height` (currently eligible in the UI) | yes |
| Workflow | cell `workflow_id/version_id/preset_id` selection (section 4) | always |

Rules:
- Axis values become **control values** and are merged via `merge_workflow_controls`; anything not exposed by the mapping is rejected at plan time with the existing validation errors — **an axis never mutates arbitrary graph fields** (this replaces the legacy slot-path mutation).
- Axis validity is re-validated per selected version/preset at plan build (not just at UI submit), because a Mapping can differ per Version.
- Invalid combination ⇒ that cell fails fast with a validation error (failed cell), not a mis-generated graph.

---

## 6. Scheduler Design (Task 6)

New module (`experiment_modern_scheduler.py`) — deliberately simple:

- **Input**: immutable ordered list of cell plans (generated once at submit; `cell_ordering_json` + `expected_cell_count` persisted on the experiment row).
- **Concurrency**: global default `EXPERIMENT_CONCURRENCY = 6` (configurable per experiment), implemented as a semaphore + task-per-cell; as a task finishes, the next queued cell is submitted — continuous slot filling by construction (ordered FIFO over the immutable list).
- **Cell state machine** (canonical vocabulary only):

```
queued ──submit──▶ running ──terminal event──▶ completed
   │                  │                          │
   │ cancel           │ cancel / interrupt        │
   ▼                  ▼                          ▼
 canceled           canceled / interrupted      (unchanged)
running ──error──▶ failed ──retry──▶ (new attempt) queued/running
```

| State | Canonical source | Meaning |
|---|---|---|
| queued | `GenerationStatus.pending` (exposed as `queued` in API) | Plan built, not yet submitted |
| running | `GenerationStatus.running` | Attempt submitted |
| completed | `GenerationStatus.completed` | Terminal, first-wins |
| failed | `GenerationStatus.failed` | Terminal, needs explicit Retry |
| canceled | `GenerationStatus.canceled` | Terminal; queued cells are canceled without submission |
| interrupted | `GenerationStatus.interrupted` | Terminal; ComfyUI shutdown — eligible for Resume |

- **Queued is not active work.** A queued cell has no active attempt; it survives process death unchanged as queued/not-started (never swept to `interrupted` — see section 9).
- **No global success inference**: experiment aggregate is derived from cells (`derive_experiment_status`, `history_v2_models.py:148-184` — with a small extension for `canceled`, see section 11). One child's failure never changes another child's state.
- **State is written, not remembered**: each transition is a History V2 write (attempt status). On restart, the scheduler rehydrates purely from History V2.

---

## 7. Canonical Lifecycle Integration (Task 7)

- **Per-cell identity**: each cell run = one `run_attempts` row (`run_id` PK, `experiment_id`, `cell_id`, `generation_id` — columns already exist, `history_v2_store.py:97-109`) plus one `generations` row per cell (`experiment_id` already exists, `:79`).
- **Sampler progress per cell / workflow progress per cell**: the frontend canonical store (`createRunStore`, `studio-run-model.js:476`) already isolates sampler vs workflow progress (Rule 5, `:388-407`) and keys everything by `runId` (Rule 6/7, `:417-437`). A per-experiment controller creates one store **per cell** (`runId = cell run_id`) and subscribes to the existing WS channels (`execution_start/executing/progress/progress_state/execution_success/execution_error`, plus `experiment.event`), reusing `adaptComfyUIWsEvents`/`adaptExperimentEvent` (`studio-run-adapters.js:179-323`, `studio-playground-run.js:440-538`).
- **Terminal first-wins**: store Rule 2 (`studio-run-model.js:308-325`) + controller `_terminal` lock (`studio-playground-run.js:177-179`). Backend side: writer writes terminal status via `update_run`/`mirror_cell_terminal`; terminal rows are written once (idempotent status transitions in `_update_attempt`, `history_v2_repository.py:555-626`).
- **Duplicate events ignored**: `event.id` dedup (Rule 1, `studio-run-model.js:491-510`); backend attempt writes are keyed by attempt identity.
- **Stale events isolated**: per-`runId` stores never cross; backend rejects events whose attempt identity does not match the active attempt (replaces lease validation with a simple active-attempt check).
- **Sibling failure isolation**: cells are independent asyncio tasks with independent stores and independent attempt rows — nothing shared except the experiment aggregate derivation.
- **Canonical store support for cells: ALREADY PRESENT.** `generations.experiment_id`, `run_attempts.experiment_id/cell_id`, `experiment_cells.generation_id/attempt_ids_json` exist. **No schema change needed.** Small extension required: `CellStatus` gains `canceled` (section 11) and `derive_experiment_status` accounts for canceled cells.

---

## 8. Cancel Semantics (Task 8)

| Cell state | Behavior |
|---|---|
| queued | Cancel **without submission**: never launched; write attempt status `canceled` (or record cell-level canceled). No Modal call ever made. |
| running | Request cancellation of the running attempt: cancel the asyncio task and close the Modal transport stream (existing primitive family: `ModalTransport` stream close / legacy `cancel_worker` `aclose()` path, `experiment_runner.py:1886-1924` — verify the exact modern primitive during implementation). Write attempt status `canceled`. |
| completed | Unchanged; outputs preserved. |
| failed | Unchanged; failed cells are NOT auto-canceled and never auto-retried. |

Experiment-level Cancel:
1. Cancel all queued cells immediately (no submission).
2. Request cancellation of all running cells (best-effort; a cancel that arrives after terminal first-wins is ignored).
3. Preserve completed outputs.
4. Aggregate derives truthfully into the EXISTING Experiment status vocabulary only — `running`, `interrupted`, `canceled`, `completed_with_failures`, `completed` (mapping in section 11). **No new `partial` status is introduced. No fake `completed` after cancellation.**

Notes: the modern single lane has no cancel today (`DELETE /comfymodal/cancel/{client_id}` returns `not_supported`, `__init__.py:4771`); the experiment scheduler adds cancel natively because cells are background tasks. Cell-level `CellStatus.canceled` is the one enum addition required (section 11); `derive_cell_status` must treat a canceled active attempt as canceled (currently it would fall back to pending).

---

## 9. Interrupted + Resume Semantics (Task 9)

**Detection** (ComfyUI/Studio disappears):
- The scheduler task group is cancelled (`asyncio.CancelledError` on loop shutdown). Catch it, and for every cell whose active attempt is still `running`, write terminal `interrupted` via the writer (`_LEGACY_STATUS_MAP` already maps `interrupted` → `interrupted`, `history_v2_writer.py:169-179`).
- Startup recovery sweep (replaces `recover_scheduler`, `experiment_service.py:265-382`): on ComfyUI boot, scan History V2 for any experiment with attempts that were actively executing when the process died (i.e., still `running` after a crash or a shutdown that bypassed the handler) and mark ONLY those `interrupted`. **Queued/not-yet-submitted cells are preserved as queued/not-started** — they have no active attempt and are never swept to `interrupted`. Completed, failed, and canceled cells are unchanged. No lease machinery needed: the sweep is idempotent (attempt status transitions are guarded).

**Persistence**: History preserves the experiment row (fixed matrix: `cell_ordering_json`, `expected_cell_count`, `axis_labels_json` — all untouched by execution) and all cell rows. Interruption never deletes or reorders cells.

**Resume** submits ONLY:
- cells with an interrupted active attempt,
- cells never started (queued/not-started — no attempt row or non-terminal queued attempt).

Resume does NOT submit:
- failed cells (they require explicit Retry, section 10),
- completed cells,
- canceled cells (unless a future explicit product action defines otherwise).

**Duplicate prevention**:
- Cell plans are immutable (baked ids/hashes) — resume reuses the stored plan/snapshot, never re-resolves versions.
- One active attempt per cell: before submit, assert the cell's active attempt is not terminal and has no newer attempt; each resume creates a **new attempt with a new run identity**; previous attempts remain in `run_attempts` (attempt history preserved).
- The submit is guarded by an atomic status transition (queued→running) so two resume calls cannot double-submit.

---

## 10. Retry Semantics (Task 10)

- Retry is **per failed cell**, explicit user action.
- Retry creates: same cell (`cell_id` stable, same `generation_id`), **new attempt** (`run_id` new), same immutable plan (same `workflow_version_id`, `preset_id`, `workflow_hash`, controls).
- Previous failed attempts remain in History (`run_attempts` is append-only; `experiment_cells.attempt_ids_json` accumulates; `history-v2` generation detail already lists `attempts[]` via `_attempt_dict`, `history_v2_routes.py:645-661`).
- Writer/repository calls available today: `record_run(kind="experiment_cell", meta={experiment_id, cell_key, workflow_version_id, preset_id, workflow_json, ...})` → new generation+attempt (writer routes on meta, `history_v2_writer.py:414-432`); `mirror_cell_terminal` (`:784`) for terminal states; `update_run` (`:496`) for transitions.
- **Missing API endpoints** (all new; none exist today):
  - `POST /history-v2/experiments/{id}/cells/{cell_id}/retry` (or the modern experiment-v2 surface) — creates the new attempt and submits.
  - `POST /history-v2/experiments/{id}/resume` — section 9.
  - `POST /history-v2/experiments/{id}/cancel` — section 8.
  - Frontend repository stubs to implement: `retryExperiment`, `generateOriginalForCell`, `generateOriginal` (`web/history-v2-repository.js:408, 410, 598-600` — today all return `_notAvailable()`).
- **Generate Original per cell is a RERUN, not an asset action.** Product contract:
  1. Preview attempt completes (its output remains the cell's preview).
  2. User chooses Generate Original for the cell.
  3. Load the cell Generation's **immutable saved executable request** (the frozen cell plan / `request_snapshots`: same `workflow_version_id`, `preset_id`, `workflow_hash`, controls, seed, `workflow_json`).
  4. Rerun the ENTIRE Workflow with identical generation parameters; **only the Preview/Original output behavior differs** (output preference applied at the execution/write layer, not a parameter change).
  5. Create a NEW attempt under the SAME Generation/cell (new `run_id`; `attempt_ids_json` accumulates).
  6. Retain the Preview and all previous attempts in History.
  7. A successful Original becomes the cell's preferred display; a failed Original leaves the Preview usable (no display regression).
  8. Retrying Original creates another attempt.
  Generate Original must NOT: fetch an existing `original_url`, export an existing asset, reconstruct from mutable current Workflow state, or silently use the latest Workflow Version/Preset.
- **Phase D scope note:** Generate Original is a future execution action. It is NOT implemented in Phase D unless a later orchestrator explicitly includes Original generation in that phase. If deferred, Phase D ships only the API surface + repository stubs behind `_notAvailable()`-style gating, with its tests marked deferred. Retry/resume/cancel remain in Phase D.

---

## 11. History V2 Contract (Task 11)

Already sufficient (no schema changes):

| Concept | Existing | Where |
|---|---|---|
| One experiment card | `experiments` row + feed item builder | `history_v2_store.py:44-55`, `history_v2_routes.py:384-478` |
| Fixed cell matrix | `experiment_cells.position/axis_labels_json` + `cell_ordering_json` | `:57-67`; frontend `_matrixLayout` (`studio-history-v2-experiment.js:286-302`) |
| Generation per cell | `generations` + `experiment_id` | `:71-88` |
| Attempt history | `run_attempts` append-only + `attempt_ids_json` | `:97-109` |
| Axis labels/values | `axis_labels_json`, `generation_params_json`, `request_snapshots.generation_params_json` | |
| Output/thumbnail | `assets` (type thumbnail/preview/original) | `:115-128` |
| Immutable version/preset per cell | `generations.workflow_version_id/preset_id`, `request_snapshots.workflow_version_id/workflow_hash/workflow_json` | columns exist |
| Aggregate status | `derive_experiment_status` + recompute on attempt write | `history_v2_models.py:148-184`, `history_v2_repository.py:555-626` |
| Cell terminal mirroring | `mirror_cell_terminal` | `history_v2_writer.py:784-904` |

Missing (small, non-schema):

1. `CellStatus` has no `canceled` (`history_v2_models.py:92-98`) and `derive_cell_status` (`:134-145`) would derive a canceled active attempt back to pending → **add `canceled` to `CellStatus`** and handle it in derivation (non-breaking additive enum value; coordinate with C1's History persistence work since models are shared-adjacent).
2. `derive_experiment_status` must treat canceled cells truthfully using ONLY the existing Experiment status vocabulary (mixed-outcome mapping below); no new `partial` status is introduced. Small derivation extension.
3. Modern cell runner must supply meta keys the writer already consumes: `experiment_id`, `cell_key`, `workflow_version_id`, `preset_id`, `preset_name`, `workflow_json` (+ `workflow_hash`) — plumbing in the new module only; **`history_v2_writer.py` is not modified** (its `_mirror_cell_terminal` passes meta through at `:852-854`).
4. New endpoints: create/start, status, cancel, resume, retry, cell actions (favorites/notes exist: `PATCH /experiments/{id}/favorite|note`, `history_v2_routes.py:1094-1124`), plus a **Generate Original rerun endpoint** (new attempt under the same Generation/cell from the immutable saved request — see section 10; deferred out of Phase D unless a later orchestrator includes it, in which case the endpoint is simply not registered until then).
5. Detail/status APIs must expose the resolved `workflow_version_id`/`preset_id` per cell (including workflow-axis resolutions, section 4); the columns already exist — this is API-surface work only.

**Mixed cell outcome → aggregate mapping (existing vocabulary only; no status invented):**

| Cell mix (after terminal settle) | Aggregate |
|---|---|
| any queued/running | `running` |
| any interrupted, no failed | `interrupted` |
| any failed, no interrupted/canceled | `completed_with_failures` |
| any canceled, no failed/interrupted | `canceled` |
| all completed | `completed` |
| interrupted + failed mix | **OPEN DECISION for Phase D** (resumable cells + failed cells coexist; neither `interrupted` nor `completed_with_failures` is fully truthful) |
| canceled + failed mix | **OPEN DECISION for Phase D** (user canceled but failures exist; not truthfully expressible) |

The base derivation order extends `derive_experiment_status` (`history_v2_models.py:148-184`): non-terminal → interrupted → failed → canceled → completed_with_failures → completed. Combinations the existing enum cannot truthfully express are marked as Phase D decisions — they are not papered over with a new status.

---

## 12. Progress UX Contract (Task 12)

Target text: `18/40 complete · 6 running · 16 queued`

Derived purely from canonical cell states (status endpoint returns per-cell status; counts are a fold):

| Token | Count = cells with status |
|---|---|
| complete | `completed` |
| running | `running` |
| queued | `queued` (pending/not-started) |
| failures | `failed` |
| canceled | `canceled` |
| interrupted | `interrupted` |

- Experiment status endpoint response: `{experiment_id, status, total, counts: {queued, running, completed, failed, canceled, interrupted}, cells: [{cell_id, status, attempt_id, error, duration_ms, thumb_url, workflow_id, workflow_version_id, preset_id}]}` — the resolved ids are exposed per cell (section 4), so the UI shows exactly which Version/Preset each cell runs.
- Frontend text derivation is a pure function (unit-testable) placed in the experiment-mode module; existing bars ("Current image" sampler, "Total cells" breakdown) keep working because cell statuses flow into the same grid state (`_mergeCellStateForGrid`, `studio-playground.js:3803-3850` — unchanged).
- No visual redesign. The "Current image" bar finally gets a live data source via the per-cell sampler store (fixes the known gap where the scoped tracker's state is never consumed, `studio-playground.js`/`comfymodal-progress.js`).

---

## 13. Exact Production Files to Edit (Task 13 — Phase D patch map)

Legend — Category: **P** = request/cell-plan generation · **S** = scheduling/lifecycle · **H** = History actions · **U** = UI.

### New files (preferred; keeps C1-owned files untouched)

| File (new) | Purpose | Functions | Cat | Depends on |
|---|---|---|---|---|
| `experiment_modern_plan.py` | Pure cell-plan generation: axes × presets → immutable ordered cell list; per-cell (workflow_id, version_id, preset_id, controls, axis labels/values); reuses `resolve_workflow_run_bundle` → `merge_workflow_controls` → `apply_workflow_values_to_prompt` → `build_workflow_execution_plan`; validation errors → fast-fail cells | `build_cell_plan`, `resolve_workflow_axis_value`, `validate_cell_controls`, `cell_plan_hash` | P | none (reads modern seam read-only) |
| `experiment_modern_scheduler.py` | Scheduler: immutable cell list, concurrency 6, continuous slot filling, per-cell asyncio task → canonical `execute_plan`; cancel/resume/retry orchestration; shutdown → `interrupted` (active attempts only); startup recovery sweep (only `running` attempts → `interrupted`; queued/not-started preserved); History V2 writes via writer (read-only reuse). Generate Original rerun `rerun_original` only if a later orchestrator includes Original generation in scope | `ExperimentModernScheduler`, `submit_cell`, `cancel_cell`, `cancel_experiment`, `resume`, `retry_cell`, `_shutdown_mark_interrupted`, `_startup_recovery` | S | A (plan contract) |
| `experiment_modern_routes.py` | Route handlers (thin); registered additively in `__init__.py` | `handle_experiment_v2_create/status/cancel/resume/retry` | S/H | A, B |
| `tests/test_modern_experiment_*.py` | Deterministic backend tests (section 17) | — | test | A–C |

### Existing files to edit (all NOT in the C1 do-not-modify list)

| File | Purpose | Functions affected | Cat | Depends on |
|---|---|---|---|---|
| `__init__.py` | Additive route registration for the experiment-v2 surface (single small block) | new route decorators only | S/H | A–C; **coordinate with C1** (shared file; C1 owns `studio_run` seam at `:7298-7389`) |
| `history_v2_models.py` | `CellStatus` + `canceled`; `derive_cell_status`/`derive_experiment_status` canceled handling | enums + derivation | H | —; **coordinate with C1** History persistence work |
| `history_v2_routes.py` | New action endpoints: cell retry, experiment resume/cancel; Generate Original rerun endpoint (deferred out of Phase D unless a later orchestrator explicitly includes Original generation — see section 10) | `_retry_cell`, `_resume_experiment`, `_cancel_experiment` | H | A, B |
| `web/studio-experiment-mode.js` | Submit via experiment-v2 endpoint; own per-experiment controller + status poll; cancel/resume/retry buttons; counts text (12) | `executeExperimentRun`, new `attachExperimentController`, `renderProgressText`, `handleCancel/Resume/Retry` | U | API contract (A–C) |
| `web/studio-playground-run.js` | Small extension: per-experiment controller factory (per-cell stores) reusing `createRunStore`/`createPlaygroundRunController` | new factory (existing factory untouched) | U | B contract |
| `web/studio-backend-api.js` | New API calls: `runExperimentV2`, `getExperimentV2Status`, `cancelExperimentV2`, `resumeExperiment`, `retryCell` | additive functions | U | API contract |
| `web/history-v2-repository.js` | Implement stubs: `retryExperiment`, `resumeExperiment`; `generateOriginal`/`generateOriginalForCell` stay stubbed (deferred) or are wired to the rerun endpoint ONLY if the orchestrator explicitly includes Original generation in Phase D — they must trigger a rerun (new attempt from the immutable saved request), never an asset fetch/export | repository methods | U/H | C endpoints |
| `web/studio-history-v2-experiment.js` | Enable Retry (experiment/cell) + Resume buttons, wire counts text | button handlers, status chip text | U | repository methods |

### Files that MUST NOT be modified (reuse read-only)

| File | Why |
|---|---|
| `studio_workflow_run.py` | The modern Single seam (C1-owned). Its chain is CALLED per cell; no edits. If a passthrough (e.g., `experiment_id` in trace meta) is ever needed, negotiate with C1. |
| `history_v2_writer.py` | C1-owned; all experiment writes go through existing public methods; meta plumbing happens in the new scheduler module. |
| `web/studio-playground.js` | C1-owned. Experiment mode adopts the existing controller branch (`:202-207`) so the legacy cascade (`:217-303`) is bypassed without editing this file. |
| `comfymodal_runtime/**` | C1-owned runtime/execution boundary. |
| `experiment_service.py` | C1-owned; new path does not use `ServiceRegistry`/`WorkerProgressBuffer`/scheduler-state. |
| `experiment_runner.py` | C1-owned; legacy graph injection is not reused. |
| `studio_run_adapter.py` | C1-owned; legacy `_schedule_and_start`/`handle_studio_experiment` remain for old cards only. |
| `canonical_execution.py` | Modern execution boundary; called read-only (`execute_plan`/`execute_modal_prompt`). (Not on the C1 list, but touching it collides with C1's seam work — treat as read-only.) |
| `web/studio-run-model.js`, `web/studio-run-adapters.js`, `web/comfymodal-progress.js` | Canonical stores/adapters — reuse, do not change semantics. |

---

## 14. Parallelization Plan (Task 14 — Phase D implementation lanes)

Interface-freeze milestone first: the **cell-plan contract** (module A's data shape) and the **REST contract** (routes/payloads) are written down before any lane starts — that is this document's sections 3.1, 8, 9, 10, 12.

| Lane | Ownership (disjoint files) | Starts after |
|---|---|---|
| **L1 — Cell/request generation** | `experiment_modern_plan.py` | contract freeze |
| **L2 — Scheduler/canonical lifecycle** | `experiment_modern_scheduler.py` | L1 interface (can stub) |
| **L3 — History V2 actions** | `history_v2_models.py`, `history_v2_routes.py`, `experiment_modern_routes.py` | L1/L2 contracts |
| **L4 — Frontend experiment** | `web/studio-experiment-mode.js`, `web/studio-playground-run.js`, `web/studio-backend-api.js`, `web/studio-history-v2-experiment.js`, `web/history-v2-repository.js` | REST contract (L3) |
| **L5 — Deterministic tests** | `tests/test_modern_experiment_*.py`, `web/*.unit.mjs` additions | per-lane, incremental |

Genuinely disjoint file ownership: L1/L2/L3/L4/L5 touch no common file **except** `__init__.py` (route registration, lane L3) and `history_v2_models.py` (lane L3). L4's five frontend files are disjoint from each other; keep them in one lane so UX decisions stay coherent (buttons/status text interlock), or split `studio-experiment-mode.js` from the history files if needed.

**Explicit conflicts:**
- `__init__.py` — shared with **Batch C1** (single-run seam `:7298-7389`) and any other lane; registration must be one additive block merged at integration time (orchestrator-owned).
- `history_v2_models.py` / `history_v2_routes.py` — shared-adjacent with C1's "failed History persistence" work; coordinate ownership of the `CellStatus.canceled` addition and any route additions (C1 may already be adding routes for single-run persistence).
- `web/studio-playground-run.js` — C1 touches the single-run controller factory; L4 must only ADD a factory, never alter `createPlaygroundRunController`.
- `history_v2_writer.py` is deliberately in NO lane (read-only reuse).

---

## 15. Test Plan (Task 15 — deterministic, fake backend; gate stays green)

All backend tests: `tests/run_studio_tests.py --fake` style (fake Modal transport, in-memory/sqlite History V2); frontend: `npm run test:fake` + node unit lane. The gate's documented RED suites are never touched.

| # | Scenario | Assertions |
|---|---|---|
| 1 | 1 cell | plan built; one `generations` + one `run_attempts`; aggregate `completed` |
| 2 | 2 cells | both complete; grid rows preserved; counts `2/2 complete` |
| 3 | 40 cells | max simultaneously-running ≤ 6 at all times (fake transport tracks submissions) |
| 4 | continuous slot filling | running count stays ≤ 6 and > 0 while queued remain; every cell eventually terminal |
| 5 | mixed Workflow axis | two workflows with pinned versions/presets; per-cell `generations.workflow_version_id/preset_id` match plan; `workflow_hash` in `request_snapshots` matches |
| 6 | no silent version substitution | workflow gains new `latest_version_id` after plan build; cells still use baked ids; unrunnable baked version → cell fails with `WORKFLOW_VERSION_NOT_RUNNABLE` reasons |
| 7 | one failed sibling | A/C complete, B failed; aggregate `completed_with_failures`; B not auto-retried |
| 8 | multiple failed siblings | counts truthful; per-cell errors isolated |
| 9 | cancel: queued cells | canceled without any submission call; attempts `canceled`; aggregate `canceled` |
| 10 | cancel: running cells | active attempts → `canceled`; completed outputs preserved; no fake `completed` |
| 11 | interrupted (shutdown) | scheduler task cancelled → running cells `interrupted`; matrix rows untouched |
| 12 | startup recovery | only attempts stuck `running` → `interrupted`; queued/not-started cells remain queued; completed/failed/canceled unchanged; idempotent on re-run |
| 13 | resume | submits only interrupted + never-started; skips completed, failed, and canceled; new attempt identity per cell |
| 14 | resume double-call | second resume no-ops (atomic queued→running guard) — no duplicate execution |
| 15 | retry | failed cell retry → new `run_id` under same `cell_id`/`generation_id`; old attempt retained; counts update |
| 16 | duplicate terminal events | same terminal write twice → second ignored; generation status stable |
| 17 | stale events | event for previous attempt of same cell → rejected (attempt identity mismatch) |
| 18 | out-of-order events | terminal before progress → terminal first-wins; later progress recorded as diagnostics; aggregate stable |
| 19 | History fixed-grid preservation | after cancel/interrupt/retry: `experiment_cells.position/axis_labels_json`, `cell_ordering_json`, `expected_cell_count` unchanged |
| 20 | exact immutable version/preset per cell | every generation row + `request_snapshots` match the frozen cell plan (ids + hash + `workflow_json`) |
| 21 | axis→control mapping | valid axis values land in `controls` via merge; unmapped axis for the selected Version → fast-fail cell with validation error, no graph mutation |
| 22 | counts text (frontend unit) | `18/40 complete · 6 running · 16 queued` derivation from cell statuses; failures/canceled/interrupted counts |
| 23 | frontend repository methods | `retryExperiment`/`resumeExperiment`/cell retry/cancel wire to the new endpoints with correct payloads |
| 24 | experiment detail matrix | renders with `axis_labels`, `cells[].axis.{x,y}` for mixed workflow axis |
| 25 | Generate Original = rerun (in scope only if the orchestrator includes it in Phase D; otherwise deferred) | new attempt under same `generation_id`/`cell_id` with new `run_id`; rerun uses the immutable saved request (same `workflow_version_id`, `preset_id`, `workflow_hash`, controls); NO re-resolution of latest/default; preview + all previous attempts retained; success → original becomes preferred display; failure → preview remains usable; retry creates another attempt |
| 26 | mixed-outcome aggregate | completed+canceled mix → `canceled` (no `partial` invented); failed+canceled and failed+interrupted mixes → recorded as OPEN Phase D decisions per section 11 mapping |

Regression guard: existing canonical playground coverage (duplicate completion, late progress ignored, stale event ignored, terminal lock, fresh retry identity, sampler/workflow isolation) and History V2 production contracts (feed orders, mixed cursors, immutable snapshots, first-terminal-wins, distinct canceled/interrupted) must remain green — the gate's 16 + 10 contract checks (`STUDIO_TEST_GATE.md:103-136`).

---

## 16. Estimated Dependency Order (Task 15)

```
P0  Contract freeze: cell-plan shape (§3.1) + REST surface (§8-10, 12)   [orchestrator, this document]
P1  L1 cell-plan generation (experiment_modern_plan.py)                  ← P0
P2  L2 scheduler (experiment_modern_scheduler.py)                        ← P1 interface
P3  L3 History V2 actions + routes (models/routes + __init__ block)      ← P1, P2 contracts
P4  L4 frontend (experiment-mode controller, API client, repo, UI)       ← P3 REST contract
P5  L5 tests across lanes (26-scenario matrix)                           ← each lane, incremental
P6  Integration: __init__.py registration merge, full deterministic gate ← P2-P4
P7  Gate: modern Single live smoke (C1) done → Phase D live smoke (manual, explicit env flags)
```

Parallelizable: P1‖P2-proto‖(P3 spec); P4 after P3 contract; L5 rides along. Serialization points: contract freeze (P0), REST contract (P3), integration (P6).

---

## 17. Phase D Gate Criteria

- `tests/run_studio_tests.py --fake` exit 0 with new experiment suites; `npm run test:fake` green; node unit lanes green.
- No change to any C1-owned or reuse-read-only file (section 13 list).
- Experiment-v2 runs on the modern seam: per-cell `ExecutionPlan` production is verified in unit tests with fake transport; no live Modal run before the C1 smoke gate.
- History V2 rows match the cell plan exactly (matrix preservation + immutable ids).

## 18. Open Questions / Risks

1. **Modern cancel primitive**: the modern `execute_plan` path's cancellation (task cancel + transport close) must be verified against `ModalTransport`/`playground_service` during P2 — the legacy `ControlBackend stop_now` family (`experiment_runner.py:1886-1924`) is the known-good reference.
2. **Controller adoption without touching `studio-playground.js`**: the design relies on the existing controller branch (`studio-playground.js:202-207`) engaging for experiment mode. Verify during P4 that attaching a controller from `studio-experiment-mode.js` is sufficient; otherwise the poller fallback (legacy cascade) remains a safety net, which would degrade status fidelity — escalate to C1 if a change to that branch is unavoidable.
3. **`history_v2_models.py` coordination**: `CellStatus.canceled` and derivation changes (including the mixed-outcome mapping and the open-decision combinations in section 11) must be sequenced with C1's History persistence work (same file family) — treat as one coordinated edit.
4. **`__init__.py` merge**: single additive registration block, merged by the orchestrator at P6 to avoid edit conflicts with C1's `studio_run` seam.

---

## 19. Batch C1 Conflict Register

| C1-owned / C1-active surface | C2 stance |
|---|---|
| `studio_workflow_run.py` (single seam incl. `resolve_workflow_run_bundle`…`build_workflow_execution_plan`) | Read-only reuse; never edited. Any need for `experiment_id` passthrough is handled in the new scheduler module (meta layer), not the seam. |
| `history_v2_writer.py` (record_run/update_run/mirror_cell_terminal/ensure_experiment) | Read-only reuse. Missing meta plumbing (preset_name, snapshot preset) is supplied by the new scheduler — writer untouched. |
| `web/studio-playground.js` (poll cascade, run button, controller branch) | Untouched; experiment mode rides the existing controller branch. |
| `comfymodal_runtime/**`, `experiment_service.py`, `experiment_runner.py`, `studio_run_adapter.py` | Untouched; new path bypasses `ServiceRegistry`/legacy scheduler entirely. |
| C1 immutable plan identity (deploy-frozen `deployment_identity`, `canonical_execution.py:1046-1271`) | Inherited automatically: per-cell plans are built by the same seam and carry the same frozen identity rules. Test #20 covers it per cell. |
| Shared files: `__init__.py` (routes), `history_v2_models.py`, `history_v2_routes.py`, `web/studio-playground-run.js` | Additive, coordinated edits only; flagged in sections 13/14. No overlap with C1's single-run seam or History persistence scope. |
