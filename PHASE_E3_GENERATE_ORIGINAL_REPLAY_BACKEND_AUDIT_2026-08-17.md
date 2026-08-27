# Phase E3: Generate Original Replay Backend Audit

Date: 2026-08-17

## Scope And Evidence

This is a read-only Phase E discovery audit. No endpoint, production source,
frontend source, preview compression implementation, deployment, live
generation, GPU work, or commit was performed.

The requested file
`COMFY_AI_HUB_STUDIO_POST_PHASE_D_ZERO_CONTEXT_HANDOFF_2026-08-17.md` was not
present under the available `Documents` tree and is not in the tracked files
for this worktree. The conclusions below therefore use the current History V2,
Studio Workflow, modern Experiment, canonical execution, and test sources as
the evidence authority. The worktree was already intentionally dirty; its
existing changes were not reverted or modified.

## Executive Verdict

| Question | Verdict |
| --- | --- |
| Is the current saved data sufficient for immutable Original replay? | **No for ordinary modern Single and legacy records. Conditionally yes for a valid modern Experiment cell whose snapshot has a non-empty serialized `ExecutionPlan`.** |
| Can a serialized `ExecutionPlan` be replayed directly? | **Yes.** `ExecutionPlan.from_dict` plus canonical `canonical_execution.execute_plan` is the correct execution path. |
| What is missing? | Ordinary Single snapshots omit the exact request, serialized plan, deployment identity, full runtime options, and a complete control/request projection. |
| Is schema migration needed? | Existing snapshot columns already exist and are backward-filled with `{}`. A data backfill cannot make old rows reproducible. A new active-attempt uniqueness index or idempotency field would require an additive migration. |
| Is Attempt-purpose persistence needed? | The existing persisted `RunAttempt.mode` is already a purpose field for `preview`, `original`, and `secondary`. Use it explicitly as purpose; do not encode retry/resume as status or as new status values. Explicit provenance is optional. |
| What is the service/API seam? | Add a Generation-scoped replay service behind `history_v2_routes.py`; it loads the immutable snapshot, creates an append-only Attempt in the same Generation, and dispatches through the canonical execution path. |
| How should duplicate Original requests behave? | Serialize the decision in one SQLite transaction: return the existing active Original Attempt; return the newest successful Original by default; create a new Attempt only for an explicit rerender action. |
| Is special Experiment execution code needed? | **No new execution engine.** Modern Experiment cells already use stable Generations, immutable plans, and the canonical scheduler/executor. Scheduler reconstruction after restart is still needed for durable queued work to execute. |
| Are protected-runtime changes needed? | **No for plan replay.** The existing transport sends the serialized plan and the protected Modal runtime deserializes it. Output-intent consumption is already represented by `ExecutionOptions` in the current runtime, but end-to-end Original materialization still needs implementation proof. |

## A. What Is Saved Today?

### A.1 History V2 schema and models

The database schema is in `history_v2_store.py`:

- `generations` at lines 71-88 stores `generation_id`, `workflow_id`, `workflow_version_id`, `preset_id`, `preset_name`, `request_snapshot_id`, `experiment_id`, status, prompt text, negative prompt text, model stack JSON, and timestamps.
- `run_attempts` at lines 97-113 stores `run_id`, `generation_id`, optional Experiment/cell links, `mode`, `status`, timestamps, error, timing JSON, and creation time. There is no separate `purpose`, `retry`, `resume`, or `idempotency_key` column.
- `assets` at lines 115-131 stores output identity, generation/attempt ownership, asset type, managed path/reference, format, digest, metadata, and creation time.
- `request_snapshots` at lines 144-159 stores `workflow_json`, `workflow_hash`, `workflow_version_id`, `generation_params_json`, `preset_snapshot_json`, `request_json`, `execution_plan_json`, `deployment_identity_json`, and `created_at`.
- Existing databases receive `request_json`, `execution_plan_json`, and `deployment_identity_json` through `_ensure_request_snapshot_columns` at `history_v2_store.py:214-232`. `SCHEMA_VERSION` remains 1 at line 173; this is an idempotent additive-column upgrade, not a proof that old rows are complete.

The typed models mirror those columns:

- `Generation` is `history_v2_models.py:227-268`.
- `RunAttempt` is `history_v2_models.py:271-302`; `mode` is the only purpose-like field and `status` is separate.
- `RequestSnapshot` is `history_v2_models.py:427-460`; every heavy replay field is optional and defaults to an empty dict.
- `GenerationDetail` loads the optional snapshot at `history_v2_models.py:478-503`.

The repository deserializes snapshots from their JSON columns at
`history_v2_repository.py:297-321`. A Generation detail loads attempts, assets,
exports, and the linked snapshot at `history_v2_repository.py:465-518`.

### A.2 Ordinary modern Single writer path

The production writer creates the single Generation and Attempt at
`history_v2_writer.py:546-582`:

- `workflow_id` is taken from `meta.workflow_id`, falling back to the passed workflow hash.
- `workflow_version_id`, `preset_id`, and preset name are copied from metadata.
- prompt and negative prompt are extracted from metadata.
- `model_stack` is read only from `meta.model_stack`.
- the Attempt is always created with `mode="original"` at lines 572-575 and again in the update-before-record path at lines 627-630.

The snapshot writer is `_ensure_request_snapshot` at
`history_v2_writer.py:820-844`. It currently passes only:

- `workflow_json` from `meta.workflow_json`;
- `_extract_snapshot_params(meta)`;
- `workflow_hash`;
- `workflow_version_id`;
- a small `preset_snapshot` containing preset/workflow names;
- `generation_id`.

It does **not** pass `request`, `execution_plan`, or `deployment_identity`.
Those three columns therefore remain `{}` for ordinary modern Single rows even
though the repository API supports all three.

The parameter extraction is intentionally reduced. `_SNAPSHOT_PARAM_KEYS` at
`history_v2_writer.py:215-218` permits only:

`seed`, `steps`, `guidance`, `cfg`, `sampler`, `scheduler`, `denoise`,
`width`, `height`, `prompt`, and `negative_prompt`.

Modern V2 success metadata is assembled at
`studio_workflow_run.py:774-844`. It does preserve the executed plan workflow
at `meta.workflow_json` (lines 785-790) and promotes the nine scalar controls
at lines 792-801, so seed and common sampling geometry are usually present.
That code still does not put the full `ExecutionPlan`, its `execution_options`,
its input images, its model stack, or its deployment identity into the V2
snapshot writer call.

The modern legacy/shadow path also writes an applied `workflow_json` in
`studio_workflow_run.py:1434-1477`, but it uses the same History V2 writer
contract and therefore has the same missing-plan problem.

Consequences for ordinary modern Single:

| Required value | Current saved state | Evidence |
| --- | --- | --- |
| Same Generation identity | Saved | `generations.generation_id`; writer `history_v2_writer.py:548-565` |
| Workflow ID/version/preset ID | Saved when modern metadata is present | `history_v2_writer.py:556-560` |
| Applied workflow graph | Usually saved | `studio_workflow_run.py:785-790`, writer `history_v2_writer.py:824-844` |
| Workflow hash | Saved | `history_v2_writer.py:840` |
| Seed/common controls | Partial projection saved | `history_v2_writer.py:215-218`, `studio_workflow_run.py:792-801` |
| Full controls/request | Missing | `history_v2_writer.py:820-844` does not pass `request`; allowlist is narrow |
| Preset values | Missing as a snapshot; only ID/name and applied graph remain | `history_v2_writer.py:827-836` |
| Model selections/model stack | Not reliably saved as `Generation.model_stack`; may be implicit in graph node inputs | `history_v2_writer.py:563`, `studio_workflow_run.py:774-801` |
| Serialized ExecutionPlan | Missing | `history_v2_writer.py:837-844` |
| ExecutionOptions/runtime options | Missing from snapshot | `ExecutionPlan` supports them at `contracts.py:422-574`, but Single writer does not pass plan |
| Deployment identity/validation proof | Missing from snapshot | `contracts.py:805-877`; writer does not pass these fields |
| Outputs | Saved separately as assets, linked to Generation and Attempt | `history_v2_repository.py:885-969`, writer `history_v2_writer.py:848-931` |
| Output intent | No snapshot field; Attempt `mode` is always `original` in this writer | `history_v2_writer.py:572-575` |

Therefore an ordinary modern Single Generation cannot be claimed to contain
everything required for an exact rerun without consulting mutable Workflow or
Preset state. The applied graph is useful evidence, but rebuilding a runnable
plan from that graph would still be a new compilation path and is not the
authoritative immutable replay contract.

### A.3 Modern Experiment matrix path

Modern Experiment planning resolves workflow version and preset exactly once at
plan time. `experiment_modern_plan.py:335-486` defines the frozen `CellPlan`,
including resolved workflow/version/preset identity, controls, merged values,
hashes, modal options, and `execution_plan_dict`. `CellPlan.to_dict()` includes
the serialized plan at lines 460-486.

The route accepts and persists the fixed matrix through
`experiment_modern_routes.py:685-729` and
`history_v2_repository.py:1323-1554`. For each cell,
`create_modern_matrix` stores:

- the exact `execution_plan["workflow"]` in `workflow_json`;
- the exact serialized plan in `execution_plan_json`;
- the full cell plan in `request_json`;
- axis values, controls, merged values, mapping, hashes, resolved names and IDs in `generation_params_json`;
- preset identity/name and merged values in `preset_snapshot_json`;
- the plan deployment identity in `deployment_identity_json`.

These writes are one transaction. A valid cell receives one queued Attempt;
planning-invalid cells receive a terminal failed Attempt, at
`history_v2_repository.py:1492-1541`. The tests verify the same Generation,
linked snapshot, full request, and serialized plan at
`tests/test_history_v2_modern_experiment.py:139-183`.

For a valid modern Experiment cell, this is the current strongest immutable
replay record. It is still conditional: `execution_plan` must be non-empty and
valid, and absent deployment identity or input images must be treated according
to the runtime's actual requirements rather than silently synthesized.

## B. ExecutionPlan Replay

### B.1 Model and serialization

`ExecutionOptions` is defined at `comfymodal_runtime/contracts.py:421-574`.
It serializes production state, output conversion options, backend, profiling,
cancellation, progress, compatibility, and legacy passthrough values.

`ExecutionPlan` is defined at `comfymodal_runtime/contracts.py:805-877`:

- frozen workflow and workflow/source hashes;
- production report;
- model stack;
- prompt bundle;
- output node IDs;
- input images;
- `ExecutionOptions`;
- request metadata;
- validation proof;
- deployment identity.

`ExecutionPlan.from_dict` is at lines 843-860 and `to_dict` at lines 862-877.
The nested dataclass is immutable in memory and `to_dict` thaws a safe JSON
copy.

Important fail-closed consequence: `ExecutionPlan.__post_init__` fills a blank
`workflow_hash` from the workflow and a blank `source_workflow_hash` from that
hash at `contracts.py:839-841`. That behavior is acceptable for general plan
construction but not sufficient proof for replay. Replay validation must first
inspect the raw saved serialized plan and reject a required hash that is absent,
then call `from_dict`. Otherwise a partial legacy payload can appear complete
because the constructor synthesized a hash.

### B.2 Canonical execution entrypoint

The canonical entrypoint is `canonical_execution.execute_plan` at
`canonical_execution.py:1547-1558`. It materializes `plan.to_dict()` once at
lines 1586-1600 and passes the resulting canonical plan through
`ModalTransport.run_plan_stream` at lines 2300-2312.

The transport sends the serialized plan, not a current Workflow/Preset
reconstruction, at `comfymodal_runtime/modal_transport.py:969-1111`. The
protected runtime reconstructs it with `ExecutionPlan.from_dict` at
`comfymodal_runtime/modal_app.py:16766-16767`.

This proves the permitted replay direction:

```text
request_snapshots.execution_plan_json
    -> raw replay validation
    -> ExecutionPlan.from_dict
    -> output-intent-only execution copy
    -> canonical_execution.execute_plan
    -> ModalTransport.run_plan_stream
```

The forbidden direction is:

```text
latest Workflow
    -> latest version/mapping/default preset
    -> current preset values
    -> new plan compilation
```

The mutable resolution path is visible in
`studio_workflow_run.resolve_workflow_run_bundle` at
`studio_workflow_run.py:86-202`; it is appropriate for a new run, not for
Generate Original.

### B.3 Hash and immutability rules

The replay service must compare the persisted plan's own hashes against its
persisted workflow before deserialization and preserve both
`workflow_hash` and `source_workflow_hash`. It must not recompute a production
plan, repair its graph, apply current mappings, or replace model/control fields.

The only allowed derived copy is an Attempt-scoped execution copy that changes
output intent and a new transport correlation identity. The saved snapshot and
serialized plan remain unchanged.

## C. Smallest Legal Delta

The authoritative semantic delta is only Preview versus Original output
behavior. These fields are classified as follows:

| Candidate | Generate Original behavior |
| --- | --- |
| Workflow graph | Must not differ. Do not rewrite SaveImage/PreviewImage nodes or remap controls. |
| Workflow/version/preset IDs | Must not differ. |
| Seed, controls, model selections | Must not differ. |
| Workflow/source/plan hashes | Must not differ. |
| Output intent/format | May differ. The current typed surface is `ExecutionOptions.output_conversion_options`, serialized by `contracts.py:560-574` and passed to the protected runtime through `to_legacy_dict`. |
| Codec, quality, WebP compression | May differ only as the output-intent policy requires. The Preview compression lane owns the implementation. Current conversion definitions are in `output_converter.py:20-48`; E3 must not invent or implement them. |
| Export/materialization behavior | May differ at the Attempt/output boundary: Original assets attach to the new Attempt and Preview assets remain. |
| Thumbnail behavior | Must remain a post-execution asset policy, not a graph mutation. Current History writer generates 256px WebP thumbnails at `history_v2_writer.py:1016-1053`; whether the Original policy changes this is implementation work outside E3. |
| Diagnostics/profiling/cancellation flags | Must not differ unless required solely for the new Attempt lifecycle. |
| Deployment identity | Must not differ. A new remote request ID is not a new deployment identity. |
| Attempt/retry metadata | May differ. It identifies a new Attempt and retry provenance, but purpose stays `original`. |

The recommended replay copy preserves every `ExecutionPlan` field and replaces
only the output conversion/intent field plus per-attempt correlation metadata
such as `prompt_id`/`request_id`. If the existing output conversion field cannot
express the product's exact Preview/Original contract, add a typed
`output_intent` field to `ExecutionOptions`; do not encode it by modifying the
workflow graph. That choice needs end-to-end output-materialization proof.

## D. Attempt Purpose And Status

The two dimensions are already separate in the model:

- `RunMode` at `history_v2_models.py:47-51` has `preview`, `original`, and `secondary`.
- `RunStatus` at `history_v2_models.py:53-68` has `queued`, `running`, `completed`, `failed`, `canceled`, and `interrupted`.
- `RunAttempt` persists both fields at `history_v2_models.py:271-302` and the database has both columns at `history_v2_store.py:97-109`.

Current behavior does **not** explicitly persist `retry`, `resumed`, `initial`,
or `normal` as purpose values. Those are inferred from call path and Attempt
ordering:

- initial is usually the first Attempt;
- retry is inferred from `create_retry_attempt`;
- resume is inferred from `create_resume_attempt`;
- the actual durable purpose is `mode`.

Modern Experiment matrix creation currently defaults every initial Attempt to
`mode="original"` at `history_v2_repository.py:1512`. The modern Single
production writer also always uses `mode="original"` at
`history_v2_writer.py:572-575`. Consequently the current production paths do
not faithfully model a real Preview Attempt even though the schema can store
one.

### Recommended representation

Use `RunAttempt.mode` as the durable purpose field for now, document its
canonical meaning as `purpose`, and always pass `mode="original"` for Generate
Original. Do not create a second competing status vocabulary and do not use
`status="retry"` or `status="preview_failed"`.

No purpose-column migration is required if `mode` remains the canonical field.
If a future API requires an explicit `purpose` column, migrate by copying
`mode` values and default old/unknown rows to `original` only when their legacy
writer semantics prove that default; otherwise mark them non-replayable.

An optional `origin_attempt_id` or `attempt_reason` can be added later for
audit provenance. It is not required to preserve Original purpose through
Retry because the existing retry method copies the current mode.

## E. New Attempt Under The Same Generation

### Existing canonical paths

Generic `add_attempt` is at `history_v2_repository.py:524-567`. It inserts a
new `run_id`, links it to the supplied Generation, queues it, and recomputes
Generation status. It does not guard against two concurrent active Attempts
and it sets `started_at` immediately.

Modern Experiment has the stronger cell path:

- `_create_cell_attempt` at `history_v2_repository.py:2037-2086` creates a fresh Attempt under the existing cell Generation and appends its ID.
- `create_resume_attempt` only accepts a current `interrupted` Attempt at lines 2088-2107.
- `create_retry_attempt` only accepts a current `failed` Attempt at lines 2109-2125.
- all three use one `BEGIN IMMEDIATE` transaction and leave old Attempts append-only.

Claim and terminal CAS behavior is already reusable:

- `claim_attempt` is `history_v2_repository.py:683-725`;
- modern cell `atomically_claim_queued_attempt` is `history_v2_repository.py:1800-1844`;
- cell `record_running` is lines 1855-1885;
- cell `record_terminal` is lines 1887-1930 and checks current Attempt identity plus terminal first-wins;
- scheduler in-memory guards are `experiment_modern_scheduler.py:1414-1452`.

### Required same-Generation enforcement

The new service must perform all of these in one transaction before dispatch:

1. Load the Generation by ID and require the linked snapshot.
2. Validate the snapshot's exact serialized plan and replay capability.
3. Check for an active Original Attempt.
4. Insert a new queued Attempt with the same `generation_id` and `mode="original"` only when policy permits.
5. Recompute derived Generation status.
6. Commit before dispatch.

For a modern Experiment cell, resolve `cell_id -> generation_id` and reuse the
existing cell plan. Do not create a new Generation or a new Experiment cell.

The current generic `add_attempt` is not sufficient as the service seam because
it has no active-Original guard. Add a guarded repository operation such as
`create_original_attempt(generation_id, cell_id=None)` modeled on
`_create_cell_attempt`, or add equivalent logic in a replay service that owns
the same transaction.

## F. Backend/API Attachment Point

### Recommended route

Use the already registered History V2 route module and Generation identity:

```text
POST /comfymodal/history-v2/generations/{generation_id}/original
```

This is preferable to a new frontend-specific route because ordinary Single
Generations and Experiment-cell Generations already share the History V2
Generation/Attempt/asset model. The existing History V2 routes are registered
in `__init__.py:7119-7123`.

The route belongs in `history_v2_routes.py`, alongside the Generation detail
route at lines 1074-1107. Route code should remain thin. Add a replay service
module, for example `history_v2_replay_service.py`, if the existing repository
is not the desired orchestration layer.

### Service sequence

The service should:

1. Parse an optional explicit rerender action and `Idempotency-Key` if the API chooses to expose one.
2. Load the Generation and linked `RequestSnapshot`.
3. Reject missing/partial/unsupported snapshots without consulting current Workflow/Preset state.
4. Validate raw plan hashes and deserialize with `ExecutionPlan.from_dict`.
5. Make the transactionally guarded active/success/failed decision.
6. Create a new queued Original Attempt under the same Generation when required.
7. Dispatch the new Attempt through canonical execution.
8. Persist `running`, then terminal status with first-terminal-wins.
9. Attach Original assets to the new Attempt and retain all Preview assets and old Attempts.
10. Promote the newest successful Original asset to the Generation's preferred/featured asset, without deleting Preview.

The response should include at least:

```json
{
  "status": "ok",
  "generation_id": "gen_...",
  "run_id": "run_...",
  "purpose": "original",
  "attempt_status": "queued",
  "reused": false
}
```

An existing active/successful Attempt response should set `reused: true`.
Existing `GET /comfymodal/history-v2/generations/{generation_id}` already
polls Attempts, errors, outputs, and snapshot-backed detail at
`history_v2_routes.py:1076-1107`; no new polling endpoint is required.

### Canonical execution reuse

For a Single Generation, use the direct canonical V2 execution service already
used by `studio_workflow_run._workflow_v2_run` and
`PlaygroundService`, but replace its mutable plan-building stage with the
deserialized snapshot plan. The actual execution call is
`canonical_execution.execute_plan`.

For a modern Experiment cell, reuse the existing modern scheduler binding:
`experiment_modern_scheduler._execution_plan_from_cell_plan` at lines 603-623
returns the existing `ExecutionPlan` or calls `ExecutionPlan.from_dict`, and
`_make_binding_execute` calls `canonical_execution.execute_plan` at lines
694-705. No Experiment-specific Generate Original executor is justified.

The current scheduler has an important lifecycle limitation: scheduler
instances are process-local and constructed on new Experiment acceptance at
`experiment_modern_routes.py:356-407` and `879-894`. Startup marks stale
running Attempts interrupted at `experiment_modern_routes.py:1319-1371` but
does not reconstruct schedulers from persisted plans. That is an implementation
gap for restart/recovery, not a reason to create a second execution engine.

## G. Duplicate And Concurrent Original Requests

There is no current Generate Original endpoint or duplicate policy. The
repository's `BEGIN IMMEDIATE` transactions provide the required serialization
primitive, but generic `add_attempt` does not itself enforce active uniqueness.

### Recommended deterministic contract

- Double-click or two tabs while an Original Attempt is queued/running: return the existing active Original Attempt. Do not create another Attempt.
- A successful Original already exists: return the newest successful Original by default. Do not spend another execution.
- Only Preview exists: create one queued Original Attempt under the same Generation.
- Only failed Original Attempts exist: return the newest failed Attempt with Retry available; do not silently reinterpret Generate Original as Retry.
- Explicit rerender (`rerender=true` or a separate explicit rerender action): create one new Original Attempt, but still return an already active Original Attempt if a concurrent request wins first.
- Two explicit rerender requests racing: one transaction creates the new active Attempt; the other returns that Attempt.
- A Preview Attempt that is still active: recommended default is `409 GENERATION_BUSY` until the Preview Attempt is terminal, because the authoritative flow is Preview completed then Original. If parallel Preview/Original is later desired, it must be an explicit contract and test.

An idempotency key is useful for client retries, but it is not required for the
smallest predictable server contract if active/success decisions and the
explicit rerender flag are transactionally serialized. If a durable key is
required, add an Attempt request-key column or table and a unique constraint;
never rely on an in-memory lock. A partial unique index over active Original
Attempts is also a reasonable defense-in-depth migration.

## H. Original Failure And Retry

The intended durable sequence is:

```text
Preview Attempt completed
  -> Original Attempt queued/running
  -> Original Attempt failed
  -> Preview asset remains usable
  -> Retry creates a new Original Attempt
  -> same Generation and same immutable snapshot
  -> Original purpose preserved
```

History V2's derived status already supports this. `derive_generation_status`
returns `completed` when any Attempt completed even if another Attempt failed,
at `history_v2_models.py:131-151`. Existing tests verify Preview retention and
failed Original durability at `tests/test_history_v2_repository.py:74-149`.

Retry must be append-only and must not reopen the failed Attempt. For an
Experiment cell, `create_retry_attempt` already copies the failed Attempt's
`mode` at `history_v2_repository.py:2109-2125`; this preserves `original`.
For Single, add a guarded retry operation that requires the current Original
Attempt to be `failed`, calls the same immutable snapshot loader, and inserts a
new `mode="original"` Attempt under the same Generation.

The retry route must not rebuild from the current Workflow/Preset and must not
create a logical Generation. A Retry of a failed Original must never revert to
Preview purpose.

One current output-preference gap must be corrected during implementation:
`history_v2_writer._attach_output_assets` only sets a featured asset when the
Generation has no featured asset at `history_v2_writer.py:921-931`. If Preview
is already featured, a successful Original will not automatically become the
preferred newest successful Original. The new successful-Original finalization
must promote the newest successful Original deliberately while retaining the
Preview asset.

## I. Legacy And Irreproducible History

No persisted `reproducible` capability flag exists. Reproducibility is currently
implicitly visible only through an optional `request_snapshot_id` and the
snapshot's fields. `GenerationDetail.request_snapshot` can be `None` at
`history_v2_models.py:478-503`.

The legacy migration seam is `history_v2_migration.py:56-194`:

- it never mutates legacy files;
- it creates an Original-mode Attempt at lines 121-126;
- it creates a request snapshot only when legacy `extra.workflow_json` is a non-empty dict at lines 167-190;
- old rows without executable workflow JSON have no exact replay snapshot.

The correct backend behavior is a non-destructive rejection:

```text
409 GENERATION_NOT_REPRODUCIBLE
```

with machine-readable reasons such as:

- `missing_request_snapshot`;
- `missing_execution_plan`;
- `unsupported_snapshot_schema`;
- `invalid_execution_plan`;
- `workflow_hash_missing_or_mismatched`;
- `deployment_identity_missing_when_required`.

Do not reconstruct a plan from mutable current Workflow, Mapping, or Preset
state. A current Single snapshot containing only `workflow_json` is also
insufficient for the strict E3 contract because it lacks the serialized
ExecutionPlan and runtime/output options.

The service may derive this capability at request time. A persisted capability
flag is optional and should not become an authority separate from the raw
snapshot validation.

## J. Experiment Cell Compatibility

Modern Experiment acceptance already follows:

```text
Experiment
  -> fixed Cell
  -> stable Generation
  -> immutable RequestSnapshot
  -> append-only Attempts
```

The matrix transaction at `history_v2_repository.py:1323-1554` links each cell
to exactly one stable Generation and stores the full cell plan. The cell's
`generation_id` and `attempt_ids` are persisted in `experiment_cells`.

Generate Original therefore needs no separate Experiment execution engine. It
can use the same Generation-scoped replay service and dispatch the cell through
the existing modern scheduler, which already runs the frozen plan through
`canonical_execution.execute_plan`.

The remaining Experiment-specific implementation proof is lifecycle, not
execution semantics:

- `experiment_modern_routes.py:1057-1129` resume and `1132-1220` retry can create queued Attempts when no scheduler is registered;
- `_build_scheduler_for_experiment` is only called from new matrix acceptance;
- startup recovery marks stale Attempts interrupted but does not rebuild a scheduler from persisted cell plans.

Generate Original must not copy the no-scheduler fallback that creates queued
work and claims success while nothing can claim it. It must either construct a
canonical scheduler before dispatch or return an explicit unavailable response
without creating an orphan queued Attempt.

## K. Test Architecture

The existing tests provide good fixtures but do not prove the complete E3
contract. Extend the following suites and add a focused replay/service suite.

1. Same Generation: create Preview, call Generate Original, assert one `generation_id` and two distinct `run_id` values.
2. New Attempt: assert old Attempts remain append-only and the new Attempt is queued/running/completed independently.
3. Exact seed: compare replay plan and original plan seed, including falsy/zero values.
4. Exact Workflow Version: compare `workflow_version_id` from Generation, snapshot, and deserialized plan.
5. Exact Preset: compare `preset_id` and persisted preset snapshot identity without consulting current preset values.
6. Exact controls: compare the complete saved request/control surface, not only the nine feed parameters.
7. Exact graph and ExecutionPlan: assert raw `execution_plan_json`, `ExecutionPlan.from_dict`, and `to_dict` preserve graph, hashes, model stack, inputs, output nodes, options, validation, and deployment identity.
8. Output intent only: deep-compare the original and replay plans and allow only output intent/conversion plus new attempt correlation metadata to differ.
9. Original success: assert Original assets attach to the new Attempt, Preview assets remain, and the newest successful Original becomes preferred.
10. Original failure: assert Preview remains usable, failed Original Attempt is durable, error is visible, and no new Generation exists.
11. Retry failed Original: assert a new Original-mode Attempt reuses the same Generation/snapshot and never reopens the failed Attempt.
12. Multiple Original Attempts: assert all Attempts remain and newest successful Original is preferred over older success and Preview.
13. Double-submit: issue concurrent POSTs and assert one active Original Attempt is returned to both callers.
14. Already-running Original: assert no second Attempt is inserted and the response identifies the existing active Attempt.
15. Existing successful Original: assert default Generate Original returns the newest success; explicit rerender creates exactly one additional Attempt.
16. Legacy irreproducible Generation: assert a non-destructive `409 GENERATION_NOT_REPRODUCIBLE` and zero execution/Attempt writes.
17. Experiment cell: assert the cell's Generation is unchanged, a new Attempt is created, and the existing canonical scheduler receives the deserialized cell plan.
18. Experiment Original failure/retry: assert `mode="original"` survives failure and retry, with cell status derived from the newest Attempt.
19. Restart/recovery: persist a running Original, restart lifecycle, assert it becomes interrupted, reconstruct/attach a scheduler, then resume or retry without a new Generation.
20. No scheduler: assert Generate Original does not create an orphan queued Attempt when dispatch cannot be constructed.
21. Hash fail-closed: assert missing or mismatched raw plan hashes are rejected before `ExecutionPlan.from_dict` can synthesize defaults.
22. Remote asset preference: assert `modal://` Original references are treated as valid assets and can become preferred; current `original_failed` checks at `history_v2_routes.py:257-260` and `825-839` only test local filesystem paths.

Best existing extension points:

- `tests/test_history_v2_repository.py:56-166` for Single Generation/Attempt retention and failure semantics;
- `tests/test_history_v2_modern_experiment.py:139-183` for full immutable matrix persistence and `:308-` onward for CAS/retry/status behavior;
- `tests/test_history_v2_production_writer.py:87-124` for ordinary writer snapshot gaps and identity threading;
- `tests/test_workflow_run_integration.py` for modern Single plan construction and V2 history capture;
- `tests/test_studio_workflow_run_plan_identity.py` for canonical plan field preservation;
- `tests/test_modern_experiment_scheduler.py:333-` for scheduler claims, retries, terminal guards, and transport binding;
- `tests/test_history_v2_api.py` for aiohttp route responses and Generation detail polling.

## L. Required Verdict Categories

### VERIFIED CURRENT BEHAVIOR

- History V2 has immutable-snapshot columns for request, serialized plan, and deployment identity.
- Modern Experiment matrix acceptance persists the full per-cell request and serialized `ExecutionPlan` in one transaction.
- `ExecutionPlan` is frozen and has `to_dict`/`from_dict` round-trips.
- `canonical_execution.execute_plan` materializes and executes a supplied plan directly.
- Modal transport sends the plan and the protected runtime deserializes it.
- Attempt status and purpose-like mode are separate dimensions.
- Cell retry/resume create new Attempts under the existing Generation and preserve the current mode.
- terminal first-wins and queued-to-running CAS protections exist for modern cell execution.
- failed Original after successful Preview can leave the Generation completed and Preview assets usable.
- modern Experiment cells use stable Generations and do not require a separate execution engine.

### RECOMMENDED PHASE-E CONTRACT

- Make Generate Original a Generation-scoped backend action, not an export/fetch operation.
- Require a complete validated serialized `ExecutionPlan` snapshot; reject all partial/legacy records.
- Deserialize the saved plan and execute it through `canonical_execution.execute_plan`.
- Change only output intent/conversion and new Attempt correlation metadata; never rebuild or mutate the graph.
- Reuse the same Generation, insert a fresh Original-mode Attempt, retain old Attempts/assets, and promote the newest successful Original.
- Use a single SQLite transaction for active/success/idempotency decisions and return an existing active Attempt for duplicate requests.
- Treat Retry as a new Original-mode Attempt under the same Generation and snapshot.
- Use the same service for Experiment cells and the existing modern scheduler for dispatch; do not add an Experiment execution engine.
- Return a non-destructive irreproducibility error for legacy or incomplete snapshots.

### UNKNOWN / NEEDS IMPLEMENTATION PROOF

- Whether the currently persisted `ExecutionOptions.output_conversion_options` fully expresses the product's Preview versus Original semantics across every output/materialization path.
- Whether Original should allow execution while a Preview Attempt is still active; the recommended default is to reject busy Generations.
- Whether deployment identity must be present for every replay or only for production-enabled plans.
- Whether a durable client idempotency key is required beyond transactionally returning active/successful Attempts.
- How existing remote `modal://` assets should be ranked and promoted by the final preferred-output policy.
- How modern Experiment schedulers are reconstructed after process restart; current lifecycle recovery marks state but does not build scheduler instances.
- Whether the absent Phase-D handoff contains additional contract constraints that are not present in this worktree.

## Future Implementation Map

### Files to modify

- `history_v2_routes.py`: add the Generation-scoped POST action and response/error mapping.
- `history_v2_repository.py`: add guarded snapshot capability validation helpers, active/successful Original queries, same-Generation Original attempt creation, and successful-Original preferred-asset promotion.
- `history_v2_writer.py`: persist the exact modern Single request, serialized `ExecutionPlan`, and deployment identity when the plan is available; retain first-terminal-wins and append-only assets.
- `studio_workflow_run.py` and/or `comfymodal_runtime/playground_service.py`: carry the exact plan and output-intent metadata into the History V2 snapshot capture rather than only the applied workflow projection.
- `history_v2_models.py`: document `RunAttempt.mode` as purpose or add a non-competing purpose alias only if the API needs it.
- `experiment_modern_scheduler.py`: reuse the existing frozen-plan execution binding; only add a narrowly scoped dispatch/reconstruction seam if required by restart or the Generation replay service.
- `experiment_modern_routes.py`: only if the service needs Experiment-cell route dispatch or startup scheduler reconstruction; do not create a second execution path.
- `__init__.py`: likely no route change because History V2 is already registered; modify only if a lifecycle hook is needed.

### Migrations

- No data backfill can make old incomplete snapshots exact.
- Existing `request_json`, `execution_plan_json`, and `deployment_identity_json` columns are already present through `history_v2_store.py:214-232`.
- If active uniqueness is enforced in SQL, add an idempotent partial unique index for active Original Attempts and test it against old rows.
- If a durable idempotency key or explicit attempt provenance is required, add an additive schema migration and define old-row defaults explicitly.
- Do not make a migration that fabricates plans from mutable Workflow/Preset state.

### Models and service

- Preserve `RunStatus` unchanged.
- Use `RunAttempt.mode` as purpose with `original` for Generate Original and its Retry.
- Add a replay service that returns capability reasons, transaction results, dispatch results, and existing/reused Attempt identity.

### Scheduler and canonical execution reuse

- Single: deserialize the saved plan and invoke `canonical_execution.execute_plan` with a new Attempt/request correlation ID and the approved output-intent delta.
- Experiment: pass the persisted cell plan to the existing `ExperimentModernScheduler`; its `_execution_plan_from_cell_plan` and `_make_binding_execute` already call canonical execution.
- Never call `resolve_workflow_run_bundle`, current Mapping, current default preset, or planner expansion during replay.

### Tests

- Add a focused `tests/test_history_v2_replay.py` for raw snapshot validation, plan round-trip, Single route/service, duplicate policy, failure/retry, and preferred output.
- Extend the repository, modern Experiment, writer, scheduler, API, and Workflow integration suites listed in Section K.
- Keep all tests offline: temp SQLite, fake transport/canonical executor seams, no Modal, no deployment, no GPU.

### Cross-lane conflicts

- Preview compression/output conversion lane owns `output_converter.py`, `comfymodal_runtime/result_delivery.py`, and protected runtime output conversion behavior. E3 should consume the existing output-intent contract and not implement compression.
- Frontend lane owns `web/history-v2-*` and Experiment UI behavior. E3 supplies backend route/payload semantics only.
- Existing Phase-D/Phase-E dirty work touches History V2, scheduler, canonical runtime, and Studio routes. Reconcile before any implementation; do not overwrite unrelated changes.
- Protected runtime files, especially `comfymodal_runtime/modal_app.py`, should remain unchanged unless implementation proof shows a missing serialized output-intent field. Plan deserialization and execution already work.

## Final E3 Decision

Generate Original is implementable as an immutable rerun, but the current
ordinary modern Single snapshot is not yet sufficient. The modern Experiment
cell path is substantially ready because it persists the complete serialized
cell plan, while Single persistence must start storing the exact plan and full
request/runtime identity. The canonical replay method is raw snapshot
validation, `ExecutionPlan.from_dict`, output-intent-only copying, and
`canonical_execution.execute_plan`. Persisted `RunAttempt.mode` is sufficient
for purpose; Retry must preserve `original` while status remains an independent
dimension. Duplicate requests should return an existing active or newest
successful Original and only explicit rerender should append another Attempt.
No Experiment-specific execution engine or protected-runtime change is
required, although scheduler restart reconstruction and output-intent
materialization need implementation proof.

## E3 IMPLEMENTATION FOLLOW-UP A — SINGLE SNAPSHOT COMPLETENESS

Date: 2026-08-17

### Exact plan capture seam

The modern Single V2 path now preserves the one `ExecutionPlan` produced by
the accepted execution pipeline; it does not rebuild a plan for History. The
capture points are:

- `studio_workflow_run.py:363-413` — `_build_plan_replay_meta` calls only the
  plan's existing `to_dict()` and derives all snapshot fields from that exact
  serialization.
- `studio_workflow_run.py:1213-1245` — `_workflow_v2_run` installs a plan
  observer on `PlaygroundService`; the observer runs after plan validation and
  before execution, so accepted execution failures still retain the exact
  plan when no completion callback occurs.
- `studio_workflow_run.py:653-704` — the post-materialization capture callback
  retains the same plan object passed by the service.
- `studio_workflow_run.py:795-843` — successful History preparation adds the
  serialized plan, request envelope, deployment identity, exact workflow, and
  model stack to the History metadata before the first V2 write.
- `studio_workflow_run.py:996-1077` — failure recording uses the observed
  executed plan when available; without one it keeps the existing incomplete
  fallback and does not synthesize plan fields.
- `comfymodal_runtime/playground_service.py:681-768` — `plan_observer_fn` is
  an injectable, non-executing observation seam. The default save callback at
  `:384-486` also serializes the plan directly for direct modern Single use.

### Fields now persisted

For a new modern Single whose accepted plan is available and serializable,
History V2 now receives:

- `request_snapshots.workflow_json` — the exact serialized plan workflow,
  including applied controls and any canonical production compilation;
- `request_snapshots.workflow_hash` — the plan hash, with source hash retained
  inside `execution_plan_json`;
- `request_snapshots.workflow_version_id` and Generation identity — the
  immutable workflow/version/preset metadata already carried by the plan;
- `request_snapshots.request_json` — complete accepted controls (including
  zero, false, empty, and controls outside the old scalar allowlist), prompt
  bundle, model stack, execution options, request metadata, and supplied
  modern modal options on the Studio V2 path;
- `request_snapshots.execution_plan_json` — the exact `ExecutionPlan.to_dict()`
  payload, including workflow/source hashes, graph, model stack, output node
  IDs, input-image structures, prompt bundle, `ExecutionOptions`, validation
  proof, request metadata, and deployment identity;
- `request_snapshots.deployment_identity_json` — the plan-carried identity
  only; no deployment state file is consulted after execution;
- `generations.model_stack_json` — the plan model stack is also mirrored into
  the existing Generation projection.

`history_v2_writer.py:820-858` now forwards the three existing JSON payloads
to `HistoryV2Repository.create_request_snapshot`; it still skips an existing
immutable snapshot and still leaves absent fields as `{}`. No schema or
serialization format change was introduced. The default
`PlaygroundService` builder also carries all submitted controls in
`studio_controls` at `comfymodal_runtime/playground_service.py:253-260`, so
its direct save callback does not depend on the narrow History feed keys.

### Files changed

- `history_v2_writer.py` — pass request, serialized plan, and deployment JSON
  into the existing snapshot columns.
- `studio_workflow_run.py` — observe the exact accepted plan, construct the
  request envelope from plan data, and persist complete success/failure
  snapshot metadata.
- `comfymodal_runtime/playground_service.py` — carry complete controls,
  expose the pre-execution plan observer, and make the default Single history
  callback persist the exact plan fields.
- `tests/test_phase_e_single_snapshot_replay.py` — focused offline coverage
  for plan capture, snapshot completeness, round-trip, falsy controls,
  immutability, and legacy incompleteness.
- `tests/test_workflow_run_integration.py` — update affected failure assertions
  to require the actual executed plan rather than the old pre-compilation
  workflow projection.
- `PHASE_E3_GENERATE_ORIGINAL_REPLAY_BACKEND_AUDIT_2026-08-17.md` — this
  follow-up only; no Generate Original endpoint or service was added.

### Verification

Offline tests pass with no Modal, deployment, live generation, or GPU work:

- `tests.test_phase_e_single_snapshot_replay`: 3 passed;
- `tests.test_workflow_run_integration`: 25 passed;
- `tests.test_history_v2_production_writer`: 33 passed;
- `tests.test_runtime_playground_v2`: 69 passed;
- `tests.test_studio_workflow_run_plan_identity`: 6 passed.

The focused test proves `ExecutionPlan.from_dict(saved.execution_plan)` is an
exact `to_dict()` round-trip, preserves hashes, graph, output nodes, input
images, model stack, complete execution options, output conversion options,
validation, deployment identity, seed `0`, and false controls. It also proves
that later metadata mutation does not rewrite the immutable snapshot and that
legacy rows retain empty replay fields.

### Replay-capability verdict after E3A

New modern Single Generations are now replay-capable when the accepted plan
reaches the owned History capture path and `ExecutionPlan.to_dict()` produces
a JSON-safe payload. The plan is authoritative for replay; current Workflow,
Version, Mapping, Preset, Settings, and deployment-state files are not read to
populate the snapshot after execution. A plan with no workflow, an unavailable
History write, a non-JSON-serializable plan/request, or a capture path that
never observes the accepted plan remains irreproducible and is not marked
complete by this batch. Legacy and previously incomplete rows remain
irreproducible; this batch intentionally does not backfill or guess them.

### Remaining E3B Generate Original work

E3B still owns the Generation-scoped Generate Original action. It must validate
the complete snapshot capability, deserialize `execution_plan_json`, apply only
the approved output-intent delta, and dispatch through canonical execution.
It must add a new `mode="original"` Attempt under the same Generation, retain
Preview and prior Attempts/assets, make duplicate active/success responses
deterministic, preserve Original purpose on Retry, and reject legacy rows
non-destructively. E3B also still needs the repository transaction/CAS seam,
route/service attachment, preferred Original promotion, Experiment-cell
dispatch reuse, restart recovery proof, and the output-intent contract from
the parallel E2 lane. This follow-up does not implement any of those routes,
services, frontend changes, compression behavior, protected-runtime changes,
deployment, or live generation.

## E3 Implementation Follow-Up B1 — Replay Core

Date: 2026-08-17

### E3B1 verdict

The immutable Generate Original replay core is implemented as a pure, isolated
module in `history_v2_replay.py`. It does not create SQLite rows, mutate History
state, call a route, or execute remote work. It is usable by both modern Single
Generations and modern Experiment-cell Generations because both enter through
the same raw `RequestSnapshot.execution_plan` contract.

### Capability contract

`validate_replay_capability(snapshot)` validates the raw serialized snapshot
before `ExecutionPlan.from_dict` is called. It fails closed when any of these
are absent or inconsistent:

- non-empty snapshot and serialized plan;
- supported plan schema, workflow, workflow hash, and source workflow hash;
- exact snapshot workflow/hash projection;
- all current canonical `ExecutionOptions.to_dict()` keys;
- non-empty output-node identity;
- request data with consistent Workflow ID, Workflow Version ID, and Preset ID;
- validation proof, when marked, must be `validated=True`;
- deployment identity in both plan and snapshot for production-enabled plans.

The structured `ReplayCapability` result exposes `capable`, `reason`, and
details without synthesizing defaults. The important machine reasons are
`missing_request_snapshot`, `missing_execution_plan`, `missing_workflow`,
`missing_workflow_hash`, `missing_source_workflow_hash`,
`missing_execution_options`, `missing_output_node_identity`,
`missing_request`, `missing_identity`, `missing_validation_proof`,
`missing_deployment_identity`, `identity_mismatch`, `invalid_plan`,
`unsupported_snapshot_schema`, and snapshot projection mismatch reasons.
Legacy or incomplete rows therefore remain non-replayable; the validator never
uses current Workflow, Version, Mapping, Preset, Settings, or deployment state.

### Plan round-trip and approved delta

`load_replay_plan(snapshot)` performs raw validation, then deserializes the
saved dictionary and requires an exact `ExecutionPlan.to_dict()` round-trip.
`prepare_original_replay(snapshot, ...)` composes that load with
`build_original_replay_plan(...)`. The saved plan is never mutated or replaced.

The Original copy preserves the workflow graph, workflow/source hashes,
Workflow Version, Preset identity, seed and all controls, model stack, input
images, prompt bundle, output-node IDs, validation proof, deployment identity,
and every execution option except the approved output policy. With the current
E2 contract, the sole execution-policy delta is
`execution_options.output_conversion_options`, set to `{"format": "original"}`.
Attempt-scoped correlation metadata may add or replace only the explicit
correlation keys (`request_id`, `prompt_id`, `run_id`, `attempt_id`, and related
trace/provenance IDs). `validate_replay_delta(saved, original)` reports every
changed path and rejects any other difference.

### Duplicate and retry decision model

`decide_original_action(attempts, explicit_rerender=False)` is pure and returns
an `OriginalDecisionResult`:

- `reuse_active` for the newest queued/running Original;
- `reuse_successful` for the newest completed Original by default;
- `create_original` for Preview-only Generations or explicit rerender;
- `retry_required` when only failed Originals exist by default;
- `busy` while a Preview is queued/running and no reusable Original wins first.

`validate_original_retry(...)` requires a failed `mode="original"` Attempt,
preserves its Generation identity and snapshot identity, and does not introduce
a retry status. The later repository transaction must create the new Attempt
append-only under the same Generation and immutable snapshot.

### Exact E3B2 integration API

E3B2 should use this sequence after loading the Generation and its linked
snapshot in one repository transaction:

1. Call `validate_replay_capability(snapshot, generation=generation)` and map a
   failed result to the non-destructive irreproducibility response.
2. Call `decide_original_action(attempts, explicit_rerender=...)` while holding
   the transaction; return an existing active/successful Attempt or create the
   guarded new Original Attempt according to that result.
3. Call `build_replay_dispatch(snapshot, generation_id, attempt_id, ...)` after
   the new Attempt identity is known. It returns `ReplayDispatchRequest` with a
   validated Original `ExecutionPlan`, `mode="original"`, and
   `executor_name="canonical_execution.execute_plan"`.
4. Dispatch `dispatch.plan` through the existing
   `canonical_execution.execute_plan` seam. The replay core itself never calls
   it and does not provide an Experiment-specific executor.
5. Use `validate_original_retry` for failed-Original retry paths and keep all
   Preview/Original Attempts and assets append-only.

The dispatch request is the handoff contract, not a persistence transaction or
execution result. Repository active/success uniqueness, Attempt creation,
asset association, terminal CAS, Original preferred-output promotion, route
mapping, and Experiment scheduler/restart attachment remain E3B2 work.

### Files and tests

Changed files for B1:

- `history_v2_replay.py` — pure capability, plan, delta, decision, retry, and
  dispatch contracts;
- `tests/test_history_v2_replay_core.py` — deterministic offline Single and
  Experiment replay-core coverage;
- `PHASE_E3_GENERATE_ORIGINAL_REPLAY_BACKEND_AUDIT_2026-08-17.md` — this
  follow-up.

The focused suite has 13 passing tests. It covers valid Single and Experiment
snapshots, legacy/missing-plan rejection, raw hash rejection before
deserialization, malformed plans, exact round-trip, output-only deltas,
zero/false controls, Workflow Version and Preset identity, model stack, input
images, graph/hashes, validation/deployment identity, immutable snapshot use,
active/success/failed/rerender/busy decisions, Original retry purpose, and the
non-executing canonical dispatch contract. No route/repository transaction,
SQLite mutation, Modal call, deployment, live generation, GPU work, or commit
was performed in B1.

## E3 Implementation Follow-Up B2 — Production Generate Original

Date: 2026-08-22

### Verdict

Production Generate Original is implemented end-to-end behind the frozen
Generation-scoped contract. One POST creates at most one queued
`mode="original"` Attempt under the SAME Generation, replays ONLY the exact
persisted immutable ExecutionPlan through `canonical_execution.execute_plan`
with an output-intent-only delta, persists required outputs/History
association BEFORE the terminal `completed` write, and leaves Preview assets,
prior Attempts, and Generation logical identity untouched. No deployment, no
live Modal generation, no GPU spend, no commit.

### Exact routes

- `POST /comfymodal/history-v2/generations/{generation_id}/original`
  body optional `{"rerender": bool}` (non-bool → 400). Workflow, seed,
  preset, controls, plan, and model stack come ONLY from the immutable
  snapshot; the browser never resends them.
- `POST /comfymodal/history-v2/generations/{generation_id}/original/retry`
  narrowly scoped Retry for a failed Original Attempt (no body needed).
- No `/experiments/.../generate-original` route was created; Experiment cells
  use the SAME Generation-scoped action. Polling stays on the existing
  `GET /comfymodal/history-v2/generations/{generation_id}` surface; no new
  polling architecture.

### Transaction semantics

`HistoryV2Repository.claim_or_reuse_original_attempt(generation_id,
*, explicit_rerender)` runs ONE `BEGIN IMMEDIATE` transaction: load
Generation → linked RequestSnapshot → all Attempts → pure
`decide_original_action` → on `create_original` insert one queued
`mode="original"` Attempt (`started_at` NULL until claimed), cell-aware via
`experiment_cells.generation_id` (appends to `attempt_ids`, recomputes
generation/cell/experiment derived status) → commit. Two racing callers
serialize on the write transaction, so a double-click/two-tab storm can never
create two active Original Attempts and no orphan Attempt is left.
`create_original_retry_attempt(generation_id)` is the retry twin: busy when
ANY attempt is active; requires the newest `mode="original"` Attempt to be
`failed` via `validate_original_retry`; append-only insert; the failed
Attempt is never reopened or mutated. Duplicate checking is never bolted on
outside the transaction.

### Duplicate / rerender / retry behavior

- Active Original (queued/running): returned as-is (`reuse_active`,
  `reused: true`); nothing inserted, no execution spent.
- Newest successful Original by default: returned (`reuse_successful`,
  `reused: true`); zero execution.
- Only failed Originals: `retry_required` identifying the newest failed
  run_id; Generate Original is never silently reinterpreted as Retry.
- Active Preview with no reusable Original: HTTP 409 `GENERATION_BUSY`.
- Explicit `rerender=true`: exactly one new Attempt unless an Original is
  already active (then reuse_active) or a Preview is active (busy).
- Retry: new queued Original Attempt, same Generation, same immutable
  snapshot, old failed Attempt retained; a Preview is never retried as an
  Original (`409 RETRY_NOT_AVAILABLE`).

### Replay core usage (immutable proof)

Service sequence per action: load detail → `validate_replay_capability`
(raw serialized snapshot, BEFORE any write; failure ⇒ non-destructive
`409 GENERATION_NOT_REPRODUCIBLE` with machine reason/details and ZERO
attempt writes) → transactional claim → `build_replay_dispatch` (re-validates
raw hashes before `ExecutionPlan.from_dict`, requires exact `to_dict()`
round-trip, applies the sole approved delta
`execution_options.output_conversion_options = {"format": "original"}` plus
correlation keys only). Tests prove `validate_replay_delta(saved, executed)`
is allowed, and that workflow graph, both hashes, seed (including 0), false
controls, Workflow Version, Preset identity, model stack, input images,
validation proof, and deployment identity are byte-identical; the saved
snapshot dict is unchanged after the whole flow. Current Workflow/Mapping/
Preset/planner/Settings are never consulted.

### Single dispatch

Fresh per-Attempt correlation identity (new request_id/prompt_id plus
run_id/attempt_id metadata; deployment identity preserved). A background task
CAS-claims queued→running via `claim_attempt`, executes through the injected
executor seam whose production default is
`canonical_execution.execute_plan(plan, transport=ModalTransport(),
trace=RuntimeTrace(request_id=fresh))` — the response carries
`"executor": "canonical_execution.execute_plan"` and no runtime logic is
duplicated. Materialization reuses `result_delivery.materialize_modal_result`
off-loop into the studio outputs dir; assets attach ONLY via the existing
`HistoryV2ProductionWriter.attach_result_assets` writer/result path (no
direct Asset insertion from the replay route).

### Experiment dispatch

Lane resolved from `generation.experiment_id`. The scheduler is resolved via
`experiment_modern_scheduler.get_scheduler`; when absent (restart), a narrow
reconstruction seam rebuilds the EXISTING production binding with
`build_experiment_scheduler(experiment_id, [cell_plan],
persistence=experiment-bound repository, transport_factory=...)` from the
persisted cell plan in `request_snapshots.request_json`. The submitted cell
plan is the persisted dict with `execution_plan` replaced by the validated
replay plan; `_make_binding_execute` still reaches
`canonical_execution.execute_plan`. No second Experiment execution engine and
no special executor exist.

### No-scheduler behavior

Dispatch capability is constructed BEFORE the claim transaction: transport
construction failure (Single) or unresolvable/unconstructable scheduler
(Experiment) returns `503 DISPATCH_UNAVAILABLE` with zero attempt writes —
never an orphan queued Attempt. If `submit_cell` fails after creation, the
Attempt is truthfully marked `failed` and 503 is returned.

### Terminal ordering

queued → running (CAS claim) → execution → materialization → required-output
persistence/History association via the writer → `completed` → deliberate
featured promotion of this Attempt's newest original (Preview retained).
Required-output gate: execution without remote output ⇒ `failed` ("v2
execution returned no output"); writer attach failure ⇒ `failed` ("History
output finalization failed") — completed-before-asset is impossible.
Execution failure marks the Attempt failed with persisted error while prior
Preview and prior successful Original remain; E1A/E1B projection owns winner
truth (tests prove the prior success stays selected after a later rerender
failure). Restart/recovery truthfulness: pre-existing queued/running Original
Attempts are REUSED, never duplicated, matching current lifecycle rules;
logical_output_key from result descriptors survives into E1B grouping
(`node:<id>:slot:<key>:item:<n>` verified end-to-end through GET detail).

### Files changed

- `history_v2_repository.py` — `OriginalClaimOutcome`,
  `claim_or_reuse_original_attempt`, `create_original_retry_attempt`,
  cell-aware `_insert_original_attempt`.
- `history_v2_replay.py` — E3B2 production section: outcome/code constants,
  `GenerateOriginalResult`, `GenerateOriginalService` with injectable
  transport/executor/materializer/writer/scheduler seams and the Single
  attempt runner; pure B1 core unchanged.
- `history_v2_routes.py` — the two POST routes, service factory injection
  point, `_json_error` code/extra extension (backward compatible).
- `tests/test_history_v2_generate_original.py` — new focused suite.
- NOT modified: `history_v2_store.py`, `history_v2_models.py`,
  `history_v2_writer.py`, `comfyapp.py`, output conversion runtime, `web/**`,
  `__init__.py` (routes were already registered).

### Tests and results (all offline)

- `tests/test_history_v2_generate_original.py`: 33 passed — preview-only
  create, same-Generation retention, mode/snapshot/seed/version/preset/
  controls/graph/hashes preservation, delta-only output intent + correlation,
  sequential + concurrent double-submit single-Attempt, running reuse,
  success reuse without execution, explicit rerender, failed-only
  retry-required, Retry append-only with retained failure, retry busy /
  not-available, active-Preview busy, legacy irreproducible 409 with no
  Attempt, invalid raw hash fail-closed with no Attempt, canonical-executor
  seam proof, Experiment same-service/scheduler dispatch with delta plan,
  no-scheduler 503 with zero orphan Attempts, execution-failure Preview +
  prior-success retention with E1B winner projection, no-output and
  finalization-failure gates blocking completion, polling surface (new
  Attempt, error entry, attached Original, retained Preview),
  logical_output_key survival, restart-truthful reuse, cell-aware creation.
- Adjacent suites green: replay_core+repository+api 55 passed;
  modern_experiment+single_snapshot_replay 48 passed;
  modern_experiment_scheduler 50 passed; production_writer+migration
  39 passed. Temp SQLite + fake seams only; no Modal, deployment, live
  generation, GPU work, or commit.

### Exact frontend contract (frozen for E4)

Success (HTTP 200):

```json
{
  "status": "ok",
  "outcome": "original_created",
  "generation_id": "gen_...",
  "run_id": "run_...",
  "purpose": "original",
  "attempt_status": "queued",
  "reused": false,
  "decision": "create_original",
  "reason": "no_successful_or_active_original",
  "executor": "canonical_execution.execute_plan"
}
```

`outcome` ∈ `original_created` | `original_already_active` |
`original_already_completed` | `retry_required`. Reuse responses set
`reused: true` and report the existing Attempt's `run_id`/`attempt_status`;
`retry_required` reports the newest failed Attempt and `reused: false`;
`executor` appears only on created. Errors (HTTP status + stable code):
`404 generation_not_found`, `409 generation_not_reproducible` (+`reason`,
`details`), `409 generation_busy`, `409 retry_not_available`,
`503 dispatch_unavailable`; bodies are
`{"status":"error","code","message",...}`. Body schema:
`{"rerender": bool}` optional; anything non-bool is 400. Retry:
`POST .../original/retry` with no body. Polling: unchanged Generation detail
GET already exposes new Attempts, statuses, failures (`errors[]`), newly
attached Original (`outputs[].original_url`), `original_failed`, and the
retained Preview. This shape is frozen; E4C reconciles against it as-is.
