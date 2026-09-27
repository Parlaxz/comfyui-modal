# Phase D Interface Freeze

| Field | Value |
|---|---|
| Batch | D1 |
| Phase | Phase D — Modern Experiments |
| Date | 2026-08-15 |
| Status | **BLOCKED** |
| Writer-lane verdict | **DO NOT START WRITERS** |
| Scope | Read-only reconciliation and interface freeze; no Phase D production behavior implemented |

This document freezes the interfaces for later Phase D work. It does not authorize
implementation, deployment, Modal execution, or real generation.

The post-freeze evidence reconciliation is recorded in
`PHASE_D_FOLLOWUP_RECONCILIATION_2026-08-15.md`. That follow-up supersedes the
initial cancellation and deployment-identity observations below for current
status; the original findings remain here as the D1 historical freeze record.

The requested zero-context handoff file
`COMFY_AI_HUB_STUDIO_PHASES_A_C_ZERO_CONTEXT_HANDOFF_2026-08-15.md` was not
present in the repository. The available baseline was therefore the current
working tree, `STUDIO_MODERN_EXPERIMENT_MIGRATION_PLAN.md`, and
`STUDIO_TEST_GATE.md`.

The working tree already contains substantial unrelated dirty/untracked work,
including untracked `history_v2_*` files and pre-existing
`experiment_modern_plan.py`, `experiment_modern_scheduler.py`, and
`experiment_modern_routes.py`. D1 did not edit, delete, reset, or reconcile
those files. Their presence is not evidence that Phase D is production-ready;
the modern routes are not registered and the cancellation path is not truthful
for running cells.

## 1. Current-source reconciliation

### 1.1 C2 assumptions versus the current tree

| C2 assumption | Current source reality | Still valid? | Phase D consequence |
|---|---|---:|---|
| The modern Single seam is `resolve_workflow_run_bundle → merge_workflow_controls → apply_workflow_values_to_prompt → build_workflow_execution_plan`. | All four functions remain in `studio_workflow_run.py:86, 285, 363, 470`; modern Single enters through `handle_workflow_run_async` at `:1495`. | Yes, with line drift | D2 must call this seam read-only. No legacy graph injector or second request builder. |
| C2 line references describe the current source. | C12–C16-era work enlarged `studio_workflow_run.py`, `history_v2_writer.py`, `history_v2_repository.py`, and `history_v2_routes.py`; for example the writer methods are now `record_run:491`, `update_run:598`, `mirror_cell_terminal:1014`, `ensure_experiment:1221`. | No | Later implementation must use symbol names/current anchors, not old C2 line numbers. |
| A modern request is recorded after execution using the existing Single history behavior. | `studio_workflow_run.py` now has capture-only history, strict JSON checks, output preflight, a nonterminal `running` write, a terminal write, and same-identity failure recording (`_workflow_v2_run` and helpers around `:592-950`). | Partly | A cell planner must persist the immutable plan before scheduling. It must not rely on terminal-only history capture. |
| The returned `ExecutionPlan` is frozen and can be serialized at the JSON boundary. | `ExecutionPlan` is a frozen dataclass with recursive `MappingProxyType` fields (`contracts.py:805-841`), `to_dict()` (`:862-877`), and `from_dict()` (`:843-860`). | Yes | Persist `plan.to_dict()`; never mutate the plan, pass it directly to `json.dumps`, or use `default=str`. |
| Phase C CLIP/VAE repairs are part of every modern plan. | `build_workflow_execution_plan` applies `_repair_missing_clip_inputs` and `_repair_missing_vae_inputs` to the applied copy before hashing (`studio_workflow_run.py:501-526`). | Yes | Reusing the seam automatically carries the repairs and hashes the repaired workflow. Do not duplicate repair logic. |
| Deployment identity is automatically carried by the modern seam. | `ExecutionPlan` has `deployment_identity`, and canonical build carries it (`canonical_execution.py:1525-1528`), but the production branch of `studio_workflow_run.build_workflow_execution_plan` reconstructs the plan at `:560-572` without passing `validation` or `deployment_identity`. | **No / blocker** | D2 must persist exactly the returned plan, but C1 must confirm/fix deployment-identity propagation before claiming deployment identity is complete. D2 must not edit the seam. |
| History V2 already supports one durable generation per cell and append-only attempts. | The schema supports those relationships (`history_v2_store.py:57-109`), and the current repository contains `create_modern_matrix` (`history_v2_repository.py:1313-1444`) that can create them. The terminal-only `HistoryV2ProductionWriter._mirror_cell_terminal` remains lazy (`history_v2_writer.py:1034-1134`). | Only as a capability | The actual modern acceptance path must use one atomic matrix repository seam, not terminal-only writer mirroring. |
| “No schema change needed” means no persistence work is needed. | Current models/store now include `RequestSnapshot.request`, `execution_plan`, and `deployment_identity` (`history_v2_models.py:428-460`; `history_v2_store.py:144-156`; additive column upgrade `:214-232`). | No, as phrased | No new DDL is required, but repository/API code and field mapping are required. |
| Exact mapped controls can be recovered from current History V2 snapshots. | `HistoryV2ProductionWriter._extract_snapshot_params` remains a narrow legacy parameter projection; it does not preserve arbitrary control-schema fields. The arbitrary JSON columns can carry them when written directly. | No for current writer flow | Persist controls and merged values explicitly in the modern cell request snapshot/definition. Never re-resolve a preset or mapping. |
| Deployment identity is not persisted. | `request_snapshots.deployment_identity_json` exists and `RequestSnapshot.deployment_identity` is modeled, but the current Single writer does not populate it in `_ensure_request_snapshot`; the modern matrix method accepts it. | No longer true at schema level | Store the exact returned plan/deployment payload when available; keep the C1 propagation gap explicit. |
| `CellStatus.canceled` is missing and cancellation would derive to pending. | Current `CellStatus` includes `CANCELED` (`history_v2_models.py:92-100`); `derive_cell_status` maps canceled (`:154-179`); aggregate derivation is queued/running → interrupted → canceled → failed → completed (`:182-221`). | Resolved in current tree | Preserve this order. Do not reintroduce `partial`. Verify the current untracked model work before any future lane owns it. |
| Repository status writes are terminal-first-wins. | Current `_update_attempt` has a SQL `status NOT IN (terminal...)` predicate (`history_v2_repository.py:613-660`). `claim_attempt` and `cancel_queued_attempt` are CAS-like (`:673-752`). | Yes in current tree | Scheduler writes must use these semantics or an equivalent explicit adapter; late terminal results cannot reopen an attempt. |
| The modern experiment route is absent. | A pre-existing untracked `experiment_modern_routes.py` exists, but `__init__.py` has no `register_experiment_modern_routes` or startup lifecycle call. It also contains a fallback from missing `create_experiment_matrix` to ordinary `create_experiment` (`:426-454`). | Not integrated | Treat the file as partial dirty work, not a frozen production contract. No route is accepted until atomic creation and scheduler/cancel gates are resolved. |
| The experiment scheduler can be a bounded task dispatcher. | The pre-existing untracked scheduler has an ordered deque, strong active-task map, `asyncio.wait(...FIRST_COMPLETED)`, and immediate refill (`experiment_modern_scheduler.py:577-607`). Its persistence protocol is not implemented by `HistoryV2Repository`, and its remote cancel callback is injectable but not a true current primitive. | Algorithm yes; implementation no | Freeze the algorithm/API below, but do not start D3 production work while cancellation and persistence adapters are unresolved. |
| ComfyUI restart recovery changes all running/queued work to interrupted. | Legacy recovery is in `experiment_service.py:265-382`; it is not the modern contract. Current modern lifecycle helper, if used, sweeps only `run_attempts.status == 'running'` (`experiment_modern_routes.py:607-622`), but is not registered. | No | Queued/not-started remains queued. Only stale running attempts become interrupted. Terminal states are unchanged. |
| Current Settings provide a backend Experiment concurrency source. | `web/studio-settings.js:495-515` has browser-local `comfymodal_global_concurrency`, default 6, but no backend reader. The pre-existing planner accepts a per-definition `concurrency` and the scheduler constructor accepts one. | No | Phase D uses one backend constant `6`; no per-Experiment request/UI override. Settings consumer wiring is deferred. |
| Experiment UI already uses the canonical per-run controller. | `studio-experiment-mode.js` currently uses legacy `runState`, `runStudioExperiment`, `stopExperiment`, and the legacy polling/tracker path. Canonical stores/adapters exist in `studio-run-model.js`, `studio-run-adapters.js`, and `studio-playground-run.js`, but are not wired to this mode. | No | D5 must own an Experiment controller/status hydration path without editing `studio-playground.js`; if that cannot be achieved, stop and escalate rather than modify the shared playground. |
| Generate Original belongs in this migration. | Current History V2 frontend methods are still `_notAvailable()` stubs (`web/history-v2-repository.js:431-433, 621-623`). | No | No Generate Original route, controller, or implementation in Phase D. |
| `partial` is a valid modern aggregate status alias. | Existing History V2 compatibility aliases still map generation `partial` to `completed` (`history_v2_routes.py:61-70`). | **No for Phase D** | Modern Experiment responses must never emit or accept `partial`. Legacy compatibility code must not be used to derive modern status. |

### 1.2 Legacy Experiment modules: read-only findings

- `matrix_compiler.py` expands Cartesian axes and preserves legacy ordering, ranges,
  and cell metadata. Its expansion mechanics can inform deterministic ordering;
  its graph injection must not be reused.
- `experiment_runner.py` performs arbitrary slot-path graph mutation in
  `resolve_and_inject_cell` and groups legacy work by checkpoint. This is not a
  modern mapped-control request builder.
- `experiment_scheduler.py` uses a legacy status family, journal inference,
  persisted scheduler state, and a semaphore around legacy invocations.
- `experiment_service.py` owns the legacy `ServiceRegistry`, journal/event bridge,
  `.scheduler_state.json`, and recovery coercion. None is the durable state machine
  for modern Experiments.
- `studio_run_adapter.py` owns the legacy Playground Experiment acceptance and
  fire-and-forget scheduling path. It remains read-only for Phase D.
- The legacy cancellation boundary (invalidate leases before worker cancel, then
  reject late events) is a useful race model, not a modern implementation seam.

## 2. Modern request-builder API freeze

These are current read-only signatures and return shapes in
`studio_workflow_run.py`:

```python
resolve_workflow_run_bundle(
    workflow_id: str,
    version_id: str,
    preset_id: str,
    node_dir: str | os.PathLike,
) -> dict[str, Any]

validate_workflow_controls(
    controls: dict[str, Any],
    control_schema: dict[str, Any],
) -> list[dict[str, str]]

merge_workflow_controls(
    preset: dict[str, Any],
    overrides: dict[str, Any],
    control_schema: dict[str, Any],
) -> dict[str, Any]

apply_workflow_values_to_prompt(
    executable_prompt: dict[str, Any],
    control_schema: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]

build_workflow_execution_plan(
    bundle: dict[str, Any],
    values: dict[str, Any],
    modal_options: dict[str, Any] | None = None,
    trace_ctx: dict[str, Any] | None = None,
) -> tuple[Any, str | None]
```

### Return contracts

- `resolve_workflow_run_bundle` returns an `ok` bundle containing `workflow`,
  `version`, `mapping`, `preset`, `state`, `executable_prompt`, and
  `control_schema`, or a fail-closed error dictionary. Empty version resolves
  `workflow.latest_version_id`; empty preset resolves the workflow default at
  this call only.
- `validate_workflow_controls` returns `[]` or strict field/message errors.
  Unknown controls, unmapped roles, enum mismatches, numeric bounds, and required
  values are rejected; values are not coerced.
- `merge_workflow_controls` returns `{"values": merged, "errors": [...]}`.
  Preset values are the base, model choices are applied for mapped roles, and
  explicit overrides win.
- `apply_workflow_values_to_prompt` returns `{"workflow": applied_prompt}` or
  `{"error": message}`. It deep-copies the executable prompt, writes only through
  mapping `node_id`/`input_name`, and performs strict read-back checks.
- `build_workflow_execution_plan` returns `(ExecutionPlan, None)` or
  `(None, error_message)`. It is the only execution-plan builder for Phase D.

### Serialization contract

`ExecutionPlan` is the immutable in-memory request. It is never mutated and is
never serialized with `default=str`. The only accepted complete serialization is:

```python
serialized = plan.to_dict()
json.dumps(serialized, allow_nan=False)
```

`to_dict()` recursively thaws `MappingProxyType` and tuples into JSON-safe plain
containers without changing scalar types. Rehydration is
`ExecutionPlan.from_dict(serialized)`. For a history sub-payload, use the existing
strict thaw helper (`studio_workflow_run._plain_copy` or the equivalent contracts
thaw), then strict `json.dumps` without `default=str`.

The cell plan stores both:

1. the frozen `ExecutionPlan` in memory for the scheduler; and
2. the exact `ExecutionPlan.to_dict()` payload in the durable snapshot.

The serialized copy does not weaken the internal immutability contract; it is only
the established JSON boundary. Any strict serialization failure is a planning
error before scheduling, not a stringification opportunity.

### Phase C repair proof

`build_workflow_execution_plan` applies the shared CLIP/VAE repair helpers after
mapped controls are applied and before `prompt_sha256` is calculated
(`studio_workflow_run.py:501-526`). The helpers are narrow, no-guess,
no-overwrite repairs. Therefore a Phase D planner that reuses the exact seam gets
the repaired graph and a `workflow_hash` over that repaired graph automatically.
No Phase D repair or arbitrary graph mutation is permitted.

The deployment-identity propagation omission in the current production branch
(`studio_workflow_run.py:560-572`) remains a C1 blocker. D2 must persist the plan
actually returned by the seam and must not silently manufacture a deployment
identity.

## 3. Frozen immutable cell-plan contract

The public planner result is an immutable ordered `ExperimentCellPlan`; each item
is an immutable `CellPlan`. The current pre-existing planner's shape is compatible
with this contract, subject to the concurrency and persistence corrections below.

### 3.1 ExperimentCellPlan

```text
experiment_id: str
cells: tuple[CellPlan, ...]                 # fixed order, never filtered
axis_labels: tuple[str, ...]
modal_options: Mapping                     # frozen, if allowed by product policy
expected_cell_count = len(cells)
cell_ordering = tuple(cell.cell_id for cell in cells)
```

The product does not expose a per-Experiment `concurrency` field. The scheduler
reads the single backend global constant `6`.

### 3.2 CellPlan

```text
experiment_id: str
cell_id: str                                # stable across retry/resume
position: int                               # zero-based fixed matrix position
axis_labels: tuple[str, ...]
axis_values: Mapping                        # exact user/display values
axis_to_control: Mapping                   # exact label → mapped role

workflow_id: str
workflow_version_id: str                    # resolved and frozen
preset_id: str                              # resolved and frozen
workflow_name: str | None
preset_name: str | None

controls: Mapping                          # exact mapped axis overrides only
merged_values: Mapping                     # final preset + override controls
execution_plan: ExecutionPlan | None       # frozen in-memory executable request
execution_plan_dict: Mapping | None        # exact plan.to_dict() boundary copy
workflow_hash: str                         # hash of repaired executable graph
source_workflow_hash: str | None           # immutable version/source hash
plan_hash: str                             # deterministic content hash

error: str | None
error_code: str | None
errors: tuple[{field: str, message: str}, ...]
```

`execution_plan` is present for a valid cell and absent for an individually
invalid cell. `execution_plan_dict` is the only serialized executable-request
representation; it is produced by `ExecutionPlan.to_dict()` and strict JSON
checked. `controls` never contains arbitrary graph paths.

### 3.3 Validation and fixed-matrix rules

- Globally malformed definitions reject the entire create request before any
  History V2 transaction: wrong top-level types, missing workflow declarations,
  empty axis lists, invalid ranges, invalid axis labels, non-JSON values, and
  duplicate/invalid global identity data.
- Cell-local failures do not remove cells. A mapping that does not expose an axis,
  a non-runnable selected Version, a missing mapping entry, a preset/version
  mismatch, or a plan-build/strict-JSON error leaves the cell at its fixed
  `position` with its `cell_id`, axis labels/values, resolved identity where
  available, and a planning error.
- An invalid cell is persisted as failed with no Modal submission. The preferred
  upfront model creates its Generation and first Attempt in the same acceptance
  transaction, with that first Attempt terminal `failed` and the planning error.
- Workflow axis values may choose workflow/version/preset combinations. Empty
  version/preset values are resolved exactly once during planning. After the plan
  is persisted, resume/retry consumes the snapshot and never consults latest,
  default, mutable Mapping, or mutable Preset state.

## 4. Durable queued-cell reproducibility

### 4.1 Required acceptance write

Before scheduling starts, one atomic History V2 operation must persist:

1. the Experiment row;
2. fixed ordered cell rows and `expected_cell_count`;
3. one stable Generation per cell;
4. one queued first Attempt per valid cell, with `started_at` unset;
5. a terminal failed first Attempt for each planning-invalid cell;
6. the immutable request snapshot for every cell; and
7. the fixed cell ordering and full plan definition.

The scheduler must not be launched until this transaction commits.

### 4.2 Exact storage locations

| Data | Durable location | Required content |
|---|---|---|
| Fixed matrix and complete plan index | `experiments.definition_json` | Versioned definition plus every `CellPlan.to_dict()`; authoritative for queued cells before execution. |
| Cell identity/order/status | `experiment_cells` | `cell_id`, `experiment_id`, `position`, `axis_labels_json`, `generation_id`, append-only `attempt_ids_json`, status, error. |
| Stable one-per-cell Generation | `generations` | `generation_id`, `workflow_id`, frozen `workflow_version_id`, `preset_id/name`, `experiment_id`. |
| Repaired executable graph | `request_snapshots.workflow_json` | The exact `ExecutionPlan.workflow`, not mutable current Version data. |
| Exact executable request | `request_snapshots.execution_plan_json` | Strict `ExecutionPlan.to_dict()` payload, including plan metadata present in the returned plan. |
| Exact mapped controls/axis values | `request_snapshots.request_json` and/or `generation_params_json` | `axis_values`, `controls`, `merged_values`, `axis_to_control`, `plan_hash`, names, and request identity. `generation_params_json` alone is not sufficient. |
| Frozen preset values | `request_snapshots.preset_snapshot_json` | Resolved preset id/name and the exact values/model choices used for the merge. |
| Workflow Version identity | `generations.workflow_version_id` and snapshot | The resolved id, never a latest lookup at resume. |
| Preset identity | `generations.preset_id` and snapshot | The resolved id, never a default lookup at resume. |
| Deployment identity | `request_snapshots.deployment_identity_json` and plan payload | Only when present in the returned plan; no fabricated identity. |
| Attempts | `run_attempts` | One queued attempt at acceptance; later Resume/Retry attempts append new rows. |

The current schema has the necessary JSON columns and transaction primitive. The
current `create_modern_matrix` method is the intended repository seam, but its
current field mapping is not accepted as final: it writes `spec.get("workflow_hash")`
into the Generation `workflow_id` slot and omits `preset_id`/`preset_name` from the
Generation insert (`history_v2_repository.py:1387-1412`). It also is not the method
called by the current modern route.

The current `experiment_modern_routes._create_matrix` looks for a non-existent
`create_experiment_matrix` and then falls back to `create_experiment`, which only
persists cells (`experiment_modern_routes.py:426-454`; repository
`create_experiment` at `history_v2_repository.py:1267-1311`). That fallback is
not a valid queued-reproducibility contract and must not be used by D4.

### 4.3 Explicit answers to the required questions

1. **Generation created for every cell upfront?** The ordinary current route: no.
   The current repository has an intended `create_modern_matrix` capability: yes,
   once its field mapping is corrected and it is actually called.
2. **Attempt created for every cell upfront?** Ordinary terminal writer flow: no.
   Frozen modern contract: yes, one queued first Attempt per valid cell, and a
   terminal failed first Attempt for a planning-invalid cell.
3. **Where does queued `workflow_json` live?** `request_snapshots.workflow_json`,
   with the full plan also in `experiments.definition_json`.
4. **Where do exact mapped controls live?** `request_snapshots.request_json`
   (and the full cell plan in `definition_json`); not only the legacy narrow
   parameter projection.
5. **Where does `workflow_version_id` live?** Generation and request snapshot.
6. **Where does `preset_id` live?** Generation and the exact preset snapshot.
7. **Is enough plan/deployment identity persisted?** The current schema can store
   the full serialized plan and deployment JSON. The current Single seam does not
   reliably propagate deployment identity through its production reconstruction,
   so exact identity completeness remains blocked on the C1 seam decision.
8. **Can current storage do this without schema change?** Yes at the DDL level;
   no at the current route/API level. A single corrected repository method and
   route call are required.

## 5. Queued Attempt, Resume, Retry, and append-only semantics

| Operation | Cell | Generation | Attempt |
|---|---|---|---|
| Initial acceptance | fixed `cell_id` | create exactly one | create first queued attempt; invalid plan uses terminal failed first attempt |
| Queue dispatch | unchanged | unchanged | atomically claim queued → running; no duplicate claim |
| Queued cancel | unchanged | unchanged | queued → canceled without Modal submission |
| Running shutdown | unchanged | unchanged | current attempt → interrupted after best-effort remote close |
| Resume interrupted | unchanged | unchanged | create a new queued attempt; leave interrupted attempt untouched |
| Resume never-started queued | unchanged | unchanged | claim the existing queued attempt; do not create a duplicate |
| Retry failed | unchanged | unchanged | create a new queued attempt; leave failed attempt untouched |
| Completed/failed/canceled terminal replay | unchanged | unchanged | first terminal wins; late writes are ignored |

The Generation is the stable cell identity. Attempts are append-only and have
fresh `run_id` identities on Resume and Retry. A retry never rebuilds the plan.

## 6. Atomic creation seam

`HistoryV2Store.transaction()` (`history_v2_store.py:261-277`) is a single
`BEGIN IMMEDIATE` / commit-or-rollback transaction. The exact repository seam to
use is a corrected `HistoryV2Repository.create_modern_matrix`
(`history_v2_repository.py:1313-1444` in the current tree), or one exact additive
alias with the same all-in-one implementation. It must insert the complete
matrix, generations, snapshots, and attempts on the same connection.

The invariant is:

```text
complete accepted Experiment + fixed matrix + immutable cell requests
OR
no accepted Experiment row
```

The route must not fall back to `create_experiment`, and it must not schedule
between independent repository calls. A crash before commit rolls back all rows;
a crash after commit but before scheduler launch leaves a complete queued matrix
that startup recovery can dispatch. Asset files are execution outputs and are not
part of acceptance atomicity.

## 7. Cancellation verdict

### Initial classification: **B — LOCAL CONSUMER CANCEL ONLY**

This was the classification at the original D1 freeze. The follow-up probe
reclassified the current protected blocker as **C — DIFFERENT PROTECTED
ARCHITECTURE REQUIRED**; see
`PHASE_D_FOLLOWUP_RECONCILIATION_2026-08-15.md`.

Current modern execution retains a `ModalTransport`, the async stream/iterator,
and a modal input id. The path is:

```text
canonical_execution.execute_plan (:1547)
  → ModalTransport.run_plan_stream (:627)
  → remote_gen.aio(...) / async iterator
  → local async-for result
```

`ModalTransport.run_plan_stream` currently does this in its `finally`
(`modal_transport.py:1170-1185`): when the consumer ends before the stream is
exhausted it spawns a shielded persistence drain. That is correct for the normal
“result arrived before the trailing persistence event” case, but it means local
task cancellation does not stop the remote invocation. `_aclose_iterator`
(`modal_transport.py:112-135`) is local iterator cleanup, not a proven remote
cancel RPC.

The installed Modal SDK has a private `FunctionCall.cancel()` primitive, but the
modern path does not retain the required `fc_...` FunctionCall id; it retains an
`in_...` input id. The remote `run_plan_stream(..., cancelled=None)` callback is
accepted by the runtime but no current local caller supplies it. Therefore there
is no safe callable that D3 can truthfully label “remote cancel available now.”

### Exact missing seam

The narrow missing seam is a supported per-invocation cancellation handle owned by
the transport and exposed to the scheduler. It must either:

1. retain/expose a supported remote FunctionCall cancellation identity and abort
   the actual remote invocation; or
2. provide a supported transport/runtime cooperative cancellation mechanism whose
   remote effect is documented and tested.

The drain-on-normal-result behavior must remain separate from the abort-on-cancel
behavior. This requires C1/runtime ownership and is outside this D1 change. No
protected runtime file was edited.

### Race contract

- Remote completion terminal write wins first → `completed` remains `completed`; a
  later cancel is a no-op/conflict and cannot rewrite it.
- A supported cancel terminal write wins first → `canceled`; a late completion is
  ignored by attempt identity and terminal-first-wins guards.
- Until the missing remote primitive exists, a running cancel must not be marked
  `canceled` merely because a local task stopped waiting. It must return a truthful
  cancellation-unavailable response and leave the running attempt to recovery.

Queued cancellation is independently safe because it requires no remote primitive.

## 8. Scheduler algorithm and public API freeze

### 8.1 Algorithm

The modern scheduler owns one Experiment and receives the already-built immutable
ordered cell plan. It must:

1. load the durable ordered queued cells;
2. retain strong references to active cell tasks in a map keyed by attempt id;
3. launch at most six active cell tasks;
4. use `asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)`;
5. process every task in the returned `done` set;
6. immediately fill newly free slots from the durable ordered queue;
7. convert an ordinary child exception into that cell's `failed` terminal without
   cancelling siblings;
8. handle `CancelledError` by persisting the semantic interruption/cancel result,
   performing best-effort remote cleanup, and re-raising after state persistence;
9. never create one task per cell behind a semaphore; and
10. never use a TaskGroup whose sibling-failure behavior cancels independent cells.

The scheduler does not rebuild plans, resolve latest/default, mutate an
`ExecutionPlan`, or infer completion from task disappearance.

### 8.2 Frozen public surface

The implementation-facing interface is:

```python
start_experiment(experiment_id: str) -> Awaitable[ExperimentSnapshot]
cancel_experiment(experiment_id: str, *, reason: str = "user_cancel") -> Awaitable[ExperimentSnapshot]
cancel_cell(experiment_id: str, cell_id: str, *, reason: str = "user_cancel") -> Awaitable[CellSnapshot]
resume_experiment(experiment_id: str) -> Awaitable[ExperimentSnapshot]
retry_cell(experiment_id: str, cell_id: str) -> Awaitable[CellSnapshot]
shutdown(*, reason: str = "shutdown") -> Awaitable[None]
active_snapshot(experiment_id: str) -> ExperimentSnapshot
```

`ExperimentSnapshot` and `CellSnapshot` are read-only projections; they are not
the source of truth. All state transitions go through the repository adapter and
are guarded by attempt identity/terminal-first-wins semantics.

The registry is a strongly referenced process-local map keyed by
`experiment_id`. It is not a weak map and is not the legacy `ServiceRegistry`.

## 9. App lifecycle ownership

Current ComfyUI creates `PromptServer` and its `aiohttp.web.Application` in
`server.py:203-251`; `main.py:start_comfyui` constructs it, initializes custom
nodes, calls `setup`, and starts the server (`main.py:456-510`). The custom node
currently registers History V2 routes at `__init__.py:7123`, but no modern
Experiment route or lifecycle callback is registered. No existing custom-node
`on_startup`/`on_shutdown`/`on_cleanup` registration was found.

The frozen ownership is:

- Create one strong modern scheduler registry when the modern route/lifecycle
  block is registered.
- Register modern routes additively after the current route setup; do not replace
  legacy Experiment routes.
- Register an aiohttp application startup callback on the current
  `PromptServer.app` if that host hook is available. The callback performs the
  idempotent startup sweep before accepting work. The sweep marks only stale
  `running` attempts from a prior process as `interrupted`.
- Register an aiohttp `on_shutdown` callback for the registry. It first stops
  launching new cells, leaves queued cells queued, asks active schedulers to
  best-effort cancel/close remote work, marks active attempts `interrupted`, and
  preserves all cells/order/results.
- Use `on_cleanup` only for bounded joining/cleanup of local background tasks or
  persistence drains if the transport exposes that seam. Do not use `atexit`,
  signal guesses, legacy `.scheduler_state.json`, or legacy lease recovery.
- If the installed ComfyUI host cannot retain these callbacks, the startup sweep
  remains the durable idempotent fallback, and D4 must report the missing host
  hook rather than silently claim shutdown coverage.

Recovery is idempotent: already terminal attempts remain unchanged; queued
attempts remain queued; only attempts still stored as `running` are transitioned
to `interrupted`. A second startup sweep makes no further change.

## 10. Aggregate-status truth table

The aggregate is derived from fixed cell statuses, in this strict order:

| Cell condition | Aggregate |
|---|---|
| Any `queued` or `running` | `running` |
| Otherwise any `interrupted` | `interrupted` |
| Otherwise any `canceled` | `canceled` |
| Otherwise any `failed` | `completed_with_failures` |
| Otherwise | `completed` |

Consequences:

| Mix | Result |
|---|---|
| completed + failed | `completed_with_failures` |
| completed + canceled | `canceled` |
| failed + canceled | `canceled` |
| failed + interrupted | `interrupted` |
| canceled + interrupted | `interrupted` |
| all canceled | `canceled` |
| any queued/running plus anything | `running` |

`partial` is forbidden. The aggregate is never inferred from a journal, missing
event, popup closure, or task count. Counts remain truthful even when precedence
chooses `interrupted` or `canceled` over failed siblings.

## 11. REST contract freeze

Use one additive modern surface. Existing History V2 detail routes remain read
routes; no legacy route is replaced and no alias is required.

### 11.1 Create/start

```text
POST /comfymodal/studio/experiment-v2
```

Request:

```json
{
  "experiment_id": "exp_client_stable_id",
  "name": "optional label",
  "definition": {
    "workflows": [
      {
        "workflow_id": "wf_1",
        "workflow_version_id": "wv_1",
        "preset_id": "preset_1"
      }
    ],
    "axes": {
      "steps": {"values": [20, 30]},
      "seed": {"values": [1, 2]}
    },
    "modal_options": {}
  }
}
```

The server builds the fixed cell plan, rejects globally malformed definitions,
atomically persists the complete matrix, and only then starts/backgrounds the
scheduler. There is no `concurrency` request field and no Generate Original
field.

Success is HTTP `200` after durable acceptance:

```json
{
  "status": "ok",
  "experiment_id": "exp_client_stable_id",
  "started": true,
  "aggregate_status": "running",
  "total": 4,
  "counts": {
    "queued": 4,
    "running": 0,
    "completed": 0,
    "failed": 0,
    "canceled": 0,
    "interrupted": 0
  }
}
```

`started` may be false only when the complete matrix was accepted and remains
durably queued for lifecycle recovery; that is not a partial acceptance.

### 11.2 Status

```text
GET /comfymodal/history-v2/experiments/{experiment_id}/status
```

Success is HTTP `200`:

```json
{
  "status": "ok",
  "experiment_id": "exp_client_stable_id",
  "aggregate_status": "running",
  "total": 4,
  "counts": {
    "queued": 2,
    "running": 1,
    "completed": 1,
    "failed": 0,
    "canceled": 0,
    "interrupted": 0
  },
  "cells": [
    {
      "cell_id": "cell_...",
      "position": 0,
      "status": "running",
      "active_attempt_id": "run_...",
      "generation_id": "gen_...",
      "workflow_id": "wf_1",
      "workflow_version_id": "wv_1",
      "preset_id": "preset_1",
      "workflow_name": "Workflow",
      "preset_name": "Default",
      "axis_labels": {"steps": 20, "seed": 1},
      "axis_values": {"steps": 20, "seed": 1},
      "error": null,
      "duration_ms": null,
      "thumbnail_url": "",
      "output_reference": null
    }
  ]
}
```

Cells are returned in fixed `position` order. `active_attempt_id` is the current
queued/running attempt and is null when the current cell is terminal. Attempt
history may be included additively, but the frontend must key active state by
stable `cell_id` and current `attempt_id`.

### 11.3 Actions

```text
POST /comfymodal/history-v2/experiments/{experiment_id}/cancel
POST /comfymodal/history-v2/experiments/{experiment_id}/resume
POST /comfymodal/history-v2/experiments/{experiment_id}/cells/{cell_id}/retry
```

All action bodies are `{}`. Optional diagnostic reason fields may be added, but
they are not execution inputs.

- **Cancel**: cancels queued cells without submission. Running cells require the
  true remote cancellation primitive. If it is unavailable, return `503`
  `CANCELLATION_UNAVAILABLE` and do not fake running cells as canceled. A fully
  completed/failed/interrupted terminal Experiment returns `409
  EXPERIMENT_TERMINAL`; a repeated cancel of an already canceled Experiment is
  idempotent `200`.
- **Resume**: creates new attempts only for interrupted cells and claims queued
  never-started cells. Completed, failed, and canceled cells are skipped. If no
  cell is resumable, return `409 NO_RESUMABLE_CELLS`; a duplicate Resume cannot
  create duplicate attempts.
- **Retry**: only a failed cell is eligible. It creates a new attempt under the
  same cell/Generation and same immutable snapshot. A non-failed cell returns
  `409 CELL_NOT_FAILED`.

### 11.4 HTTP errors

| Condition | HTTP | Code/message |
|---|---:|---|
| Invalid JSON/body or globally malformed definition | 400 | `INVALID_DEFINITION` plus field errors |
| Duplicate Experiment id | 409 | `EXPERIMENT_EXISTS` |
| Missing Experiment | 404 | `EXPERIMENT_NOT_FOUND` |
| Missing cell or wrong Experiment | 404 | `CELL_NOT_FOUND` |
| Resume has no interrupted/queued work | 409 | `NO_RESUMABLE_CELLS` |
| Retry non-failed cell | 409 | `CELL_NOT_FAILED` |
| Cancel non-canceled terminal Experiment | 409 | `EXPERIMENT_TERMINAL` |
| True running cancel unavailable | 503 | `CANCELLATION_UNAVAILABLE` |
| Persistence/transaction failure | 500 | `PERSISTENCE_ERROR`; accepted row must not be presented if the transaction failed |

No route is frozen for Generate Original. No route emits `partial`.

## 12. Global concurrency source

The server-side source is a single constant:

```python
EXPERIMENT_CONCURRENCY = 6
```

There is no per-Experiment `concurrency` field in the REST payload, persisted
definition, or UI. The current browser setting at
`web/studio-settings.js:495-515` is local-only and is not a backend canonical
source; its eventual consumer wiring is deferred to Phase F.

## 13. Frontend contract

`studio-experiment-mode.js` owns the Experiment controller. It must:

- submit the modern create endpoint and keep the backend `experiment_id`;
- hydrate/reconnect from the durable status endpoint;
- subscribe to existing canonical event-bus messages through the existing
  adapters/stores without changing their semantics;
- keep one cell store keyed by stable `cell_id`;
- key active execution by `attempt_id`/`run_id`;
- replace the active attempt identity on Resume/Retry without moving the cell;
- use status responses as truth and never infer completion from journal absence;
- detach only the popup/controller listeners when the Experiment closes; the
  backend scheduler continues;
- reconstruct the whole matrix from the status endpoint when reopened;
- display the six counts and exact resolved Version/Preset per cell;
- never expose `partial`, Generate Original, or per-Experiment concurrency.

The canonical shared files are read-only seams for D5:

- `web/studio-run-model.js` — `createRunStore` and terminal/identity rules;
- `web/studio-run-adapters.js` — existing WS/status adapters;
- `web/studio-playground-run.js` — existing controller identity rules.

Current `studio-experiment-mode.js` still bypasses those seams and uses the
legacy `studio-playground.js` polling/run-state branch. The exact missing seam is
an Experiment-owned controller/status/event path from Experiment mode that does
not depend on `_startPolling` journal completion inference. `web/studio-playground.js`
must not be modified for D1 or D5. If the controller cannot be attached entirely
from Experiment-specific files, stop and escalate before touching the playground.

## 14. Lane/file ownership freeze

| Lane | Sole write ownership after D1 unblocks | Read-only dependencies |
|---|---|---|
| D2 planner | New `experiment_modern_plan.py` and planner tests only | `studio_workflow_run.py`, domain services, `contracts.py` |
| D3 scheduler | New/owned `experiment_modern_scheduler.py` and scheduler tests only | D2 CellPlan contract, repository adapter, canonical execution; no `comfymodal_runtime/**` edits |
| D4 History/routes/lifecycle | `history_v2_models.py`, `history_v2_repository.py`, `history_v2_routes.py`, new modern route file, one additive `__init__.py` registration/lifecycle block | `history_v2_store.py` transaction/schema, `history_v2_writer.py` read-only unless ownership is explicitly renegotiated |
| D5 frontend | `web/studio-experiment-mode.js`, `web/studio-backend-api.js`, `web/history-v2-repository.js`, `web/studio-history-v2-experiment.js`, and Experiment-only frontend tests | `studio-playground.js`, `studio-run-model.js`, `studio-run-adapters.js`, `studio-playground-run.js` |
| D6 integration/tests | Cross-lane fake adapters, integration tests, test registration/glue only | All production files owned by D2–D5 |

### Shared/conflict files

- `__init__.py`: D4 additive registration/lifecycle block conflicts with existing
  route registration and unrelated dirty work. One merge owner only.
- `history_v2_models.py`, `history_v2_repository.py`, and
  `history_v2_routes.py`: current History V2/C-era dirty work and D4 overlap.
- `studio_workflow_run.py`, `canonical_execution.py`, and
  `comfymodal_runtime/**`: C1/protected execution ownership; Phase D is read-only.
- `history_v2_writer.py`: C1/current History writer ownership; modern acceptance
  must not extend it casually.
- `web/studio-playground-run.js`, `web/studio-run-model.js`, and
  `web/studio-run-adapters.js`: canonical frontend seams; D5 consumes them but
  does not alter their semantics.
- `web/studio-playground.js`: explicitly read-only and out of all Phase D lanes.

The pre-existing untracked modern planner/scheduler/routes are not adopted as a
writer lane by this freeze. Their current defects and lack of registration are
recorded above; they must be reconciled by their eventual owners rather than
silently overwritten.

## 15. Schema-change verdict

**No new SQLite DDL is required for the frozen contract.** The current schema has
the required experiment/cell/generation/attempt relationships and JSON snapshot
columns, including request, execution-plan, and deployment-identity payloads.

**Code/API changes are required:**

1. use/fix one atomic modern-matrix repository method;
2. persist full cell-plan/request fields, not only the legacy eleven-key projection;
3. ensure Generation workflow/preset identity mappings are correct;
4. wire queued/running/terminal transitions through the modern repository adapter;
5. register the modern routes and lifecycle exactly once; and
6. provide/approve a truthful running-cell remote cancellation seam.

If C1 determines that deployment identity cannot be preserved by the current
read-only request seam, that is a contract blocker, not a reason to add mutable
runtime re-resolution.

## 16. Blockers

1. **Running-cell cancellation is B.** No safe current remote cancel callable is
   retained; local `aclose()`/task cancellation is not sufficient. D3 cannot
   mark a running cell canceled on that basis.
2. **Atomic matrix route is not wired.** The repository has a partial
   `create_modern_matrix`, while the current route looks for a different method and
   falls back to cell-only persistence.
3. **Current matrix field mapping is incomplete/incorrect.** Workflow/preset
   identity and full snapshot fields require reconciliation before acceptance.
4. **Deployment identity propagation through the modern plan builder is not
   proven.** The returned production plan reconstruction omits fields present in
   the canonical plan.
5. **Modern lifecycle is unregistered.** The current helper functions do not make
   a durable registry/recovery path until the additive `__init__.py`/aiohttp hook
   is wired.
6. **Frontend Experiment mode is still legacy-attached.** The controller/status
   seam must be proven without editing `studio-playground.js`.
7. **The required zero-context handoff artifact is absent.** This freeze uses the
   current source and the two available planning documents.
8. **The working tree contains concurrent untracked Phase-D-shaped files.** They
   were not changed or removed by D1 and cannot be treated as validated production
   implementation.

## 17. Exact implementation dependency graph

```text
D1 interface freeze (this artifact)
  ├─ C1 decision: preserve/expose remote cancellation handle
  │    └─ D3 scheduler can truthfully implement running cancel/shutdown
  ├─ C1 decision: preserve deployment identity in returned ExecutionPlan
  │    └─ D2 can persist/reload exact executable identity
  ├─ D2 planner contract
  │    └─ D4 atomic matrix persistence and route request validation
  ├─ D3 scheduler protocol + repository adapter
  │    └─ D4 action routes and lifecycle registry
  └─ D4 REST/status contract
       └─ D5 Experiment controller/API/history UI

D2 + D3 + D4 + D5 deterministic tests
  └─ D6 fake parity/integration tests
       └─ deterministic Studio gate only
```

The graph is not a permission to start writers. The first implementation gate is
the cancellation decision and the corrected atomic persistence seam. Until both
are resolved, the correct writer-lane state is **DO NOT START WRITERS**.
