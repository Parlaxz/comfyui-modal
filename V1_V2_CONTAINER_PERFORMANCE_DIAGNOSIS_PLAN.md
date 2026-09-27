# V1/V2 Container Performance Diagnosis Plan

## Implementation progress

| Work item | Status |
|---|---|
| Phase 0 — Deployment and invocation identity | Completed |
| Phase 1 — Local preparation and remote submission | Completed |
| Phase 2 — Modal queue and initialization correlation | Completed |
| Phase 3 — Snapshot startup and restore lifecycle | Completed |
| Phase 4 — Model preload and graph consumption | Completed |
| Phase 5 — Prompt execution breakdown | Completed |
| Phase 6 — Output collection and result delivery | Completed |
| Phase 7 — V1 parity instrumentation | Completed |
| Phase 8 — Trace integrity and focused tests | Completed |
| Phase 9 — Controlled data collection | Ready; awaiting approved runs |
| Phase 10 — Analysis | Pending |
| Verification and plan review | Completed |

Phases 0–8 are implemented. The complete diagnosis-boundary suite passes with
594 tests passed and 2 skipped. Phase 9 tooling now validates run identity,
correlates dashboard/OTel CSV data by Modal input ID, distinguishes partial
from complete correlation, and excludes failed or ambiguous runs from medians
without deleting their raw snapshots. Phases 9–10 still require explicit
approval for controlled Modal runs; no paid generation runs have been performed.

The repository-wide legacy suite is not currently green (4194 passed, 51
skipped, 388 failed, 41 errors), including failures from stale source/version
assertions and a missing `_run_benchmark.py`. This diagnosis work does not
claim those unrelated baseline failures are resolved.


## 1. Objective

Build an evidence trail that explains, without inference:

1. Why V2 consistently spends roughly one minute between Modal input creation and container scheduling while V1 schedules in roughly one second.
2. Why V2 spends roughly 34 seconds in execution while V1 spends roughly 11 seconds.
3. Which differences belong to:
   - Local preparation
   - RestorePlan/profile publication
   - Modal queueing
   - Container startup and lifecycle hooks
   - Model preload
   - PromptExecutor and graph execution
   - Output collection and materialization
4. Which measured component should be addressed first.

This phase is diagnosis only. It must not introduce performance optimizations.

## 2. Invariants

All work must preserve:

- `min_containers=0`
- `scaledown_window=4`
- Separate V1 and V2 Modal apps
- Read-only models Volume during normal generation
- No automatic model migration
- One generation per container
- No keep-warm calls or scheduled generations
- V2 must not fall back to:
  - `modal_client.run_prompt_stream`
  - `prepare_active_next_profile`
  - `api._execute_in_process`
- Existing workflow, output and production semantics
- Remote trace events must be merged, never replaced
- No prompt text, image contents, credentials, tokens or secrets in diagnostics
- No paid generation runs without explicit approval
- Instrumentation must not add retries, waits, concurrency changes or altered execution conditions

## 3. Evidence model

Every run will be represented as one correlated timeline:

| Boundary | Meaning |
|---|---|
| T0 | Local request received |
| T1 | Execution plan construction starts |
| T2 | Execution plan construction finishes |
| T3 | RestorePlan/profile publication starts |
| T4 | RestorePlan/profile publication finishes |
| T5 | GPU invocation begins submission |
| T6 | Modal input created |
| T7 | Container scheduled |
| T8 | Remote lifecycle begins |
| T9 | Remote method receives the plan |
| T10 | Graph preparation starts |
| T11 | PromptExecutor starts |
| T12 | PromptExecutor finishes |
| T13 | Output collection starts |
| T14 | Remote result is returned |
| T15 | Local materialization finishes |
| T16 | UI completion is delivered |

Modal's T6/T7 timestamps cannot be produced by application code. They must be collected from the dashboard or OTel and correlated through the Modal input ID.

### Clock rules

- Use monotonic time for durations within one process.
- Use wall-clock nanoseconds only for cross-process ordering.
- Never subtract monotonic timestamps from different processes.
- Every event must include its process: `local`, `publisher`, `remote_lifecycle`, or `remote_method`.

## 4. Common trace schema

All new structured events should use `RuntimeTrace` where available:

```text
name
trace_id
request_id
process
phase
wall_unix_ns
monotonic_ns
metadata
```

Common metadata:

```text
runtime_mode
workflow_hash_prefix
app_name
class_name
method_name
modal_input_id
container_task_id
container_session_id
image_id
gpu
cloud
region
cpu
memory_mb
snapshot_enabled
gpu_snapshot_enabled
restore_plan_generation
```

Sensitive values must be omitted or hashed.

## 5. Phase 0 — Deployment and invocation identity

### Purpose

Prove exactly which deployed object handled every measured input.

### V2 locations

- `comfymodal_runtime/modal_app.py`
  - `ModalRuntimeSpec`
  - `startup()`
  - `restore()`
  - `run_plan_stream()`
- `comfymodal_runtime/modal_transport.py`
  - `_v2_handle()`
  - `run_plan_stream()`

### V1 locations

- `modal_client.py`
  - `_workspace_api()`
  - `run_prompt_stream()`
- `comfyapp.py`
  - Remote `run_prompt_stream()`

### Required fields

For each GPU invocation:

- App name
- Class name
- Method name
- Modal input ID
- Container/task ID
- Image ID
- GPU
- Cloud
- Region
- CPU request
- Memory request
- Target/max inputs
- Models/custom-nodes/runtime-state Volume names and mount paths
- Memory-snapshot setting
- GPU-snapshot setting
- Container session ID
- Workflow hash prefix
- Request/trace ID

### Method

At the first remote method line, obtain `modal.current_input_id()` where supported and include it in the first status event returned to the local process.

Record relevant Modal environment values:

- `MODAL_TASK_ID`
- `MODAL_IMAGE_ID`
- `MODAL_CLOUD_PROVIDER`
- `MODAL_REGION`

Do not log the workspace token, secrets or raw workspace credentials.

### Acceptance criteria

- Every dashboard input can be matched to exactly one application request.
- Every measured V1/V2 run includes its effective resource configuration.
- The one-minute timeline is conclusively associated with the intended GPU generation input.
- No run with missing or ambiguous identity data enters the comparison dataset.

### Durability

Keep this instrumentation permanently. It has low overhead and prevents future deployment ambiguity.

## 6. Phase 1 — Local preparation and remote submission

### Purpose

Measure all work before Modal creates or begins handling the GPU invocation.

### Locations

- `__init__.py`
  - `_execute_job()`
- `canonical_execution.py`
  - `build_execution_plan()`
  - `execute_plan()`
  - V1 canonical executor
- `comfymodal_runtime/modal_transport.py`
  - `_v2_handle()`
  - `run_plan_stream()`
  - `publish_restore_plan()`
- `modal_client.py`
  - `_workspace_api()`
  - `run_prompt_stream()`
  - Active-profile publisher

### Required spans

#### Plan construction

- `plan_build_start/end`
- Workflow copy
- Source workflow hash
- Production workflow preparation
- Dispatch workflow hash
- Input-image discovery/read/base64
- Model-stack extraction
- Prefill-key derivation
- Execution-options parsing
- Plan freeze
- `plan.to_dict()` thaw/serialization

Record elapsed time and payload size, not payload content.

#### Restore publication

- `restore_publish_lookup_start/end`
- `restore_publish_call_start/end`
- State read
- Identity comparison
- State write
- Commit
- Readback
- Changed/unchanged result
- Generation before/after
- Bytes written

#### GPU transport

- Handle-cache hit/miss
- Client resolution
- Class lookup
- `with_options`
- Class instance construction
- Plan serialization
- Remote generator creation
- First generator iteration
- First remote event
- Final result received

### Optimization-neutral implementation rule

Convert `ExecutionPlan` to a dictionary once for instrumentation and transport only if doing so does not change behavior. Otherwise measure existing conversions individually during diagnosis.

### Acceptance criteria

- Local plan, publication, lookup and first-event intervals are independently measured.
- RestorePlan publication is visibly separate from GPU invocation time.
- GPU submission-to-first-event time can be compared with the sum of Modal queue and startup times.
- No unaccounted local delay exceeds 500 ms or 2% of local wall time, whichever is larger.

### Durability

Keep high-level plan, publication, GPU submission and first-event spans. Remove verbose per-copy/hash breakdown after diagnosis.

## 7. Phase 2 — Modal queue and initialization correlation

### Purpose

Separate:

1. Input-created → container-scheduled
2. Container-scheduled → remote method available
3. Remote lifecycle work
4. Method execution

### Required external evidence

For every run, capture:

- Modal input-created timestamp
- Container-scheduled timestamp
- Execution-started timestamp
- Execution-finished timestamp
- Input queue metric where available
- Cold-start metric where available
- Pending-input count
- Snapshot indicator
- Function/class ID
- Container ID

### Application-side evidence

Correlate those records with:

- `gpu_invocation_submit`
- `remote_lifecycle_start/end`
- `remote_method_entry`
- `first_stream_event`

### Acceptance criteria

- All five V1 and five V2 runs have complete dashboard/OTel and application correlation.
- The queue disparity is expressed using matched input IDs, not assumed timestamps.
- Effective V1/V2 resource specifications are displayed side by side.
- No application-code interval is incorrectly labeled as Modal queue time.

### Durability

The correlation fields remain permanent. Manual dashboard transcription is temporary until OTel collection is automated.

## 8. Phase 3 — Snapshot startup and restore lifecycle

### Purpose

Account for all initialization work performed before graph execution.

### V2 startup instrumentation

`comfymodal_runtime/modal_app.py::startup()` and `RuntimeBootstrap.startup()`:

- Startup entry
- Models symlink
- Manager offline configuration
- Models Volume reload
- Runtime-state Volume reload
- Custom-node synchronization
- Requirements installation
- ComfyUI path/import setup
- Backend startup
- Generation observation
- Startup completion/error

Because `snap=True` may not have a request ID, correlate through container session, task and image IDs.

### V2 restore instrumentation

`ModalRuntimeEntrypoint.restore()` and `RuntimeBootstrap.restore()`:

- Restore entry
- RestorePlan read
- GPU-state restoration
- CUDA initialization
- SageAttention policy
- Runtime-state Volume reload
- Models Volume reload
- Custom-node synchronization
- Generation observation
- Preload bridge submission
- Restore completion/error

### Required fields

- Duration per stage
- Success/error
- RestorePlan found/absent
- RestorePlan generation
- Observed runtime/custom-node generation
- Whether each preload future was submitted
- Effective backend
- CUDA device information without verbose hardware dumps

### Acceptance criteria

- Lifecycle stage durations approximately sum to total lifecycle duration.
- Snapshot startup and normal restore are distinguishable.
- Volume reload, custom-node sync, CUDA and preload submission costs are independently visible.
- The trace shows whether preload workers continue after lifecycle completion.

### Durability

Keep all lifecycle spans permanently. Cold-start regressions are otherwise difficult to diagnose.

## 9. Phase 4 — Model preload and graph consumption

### Purpose

Determine whether V2 preload is useful, late, mismatched or failing.

### Locations

- `comfymodal_runtime/model_preload.py`
  - `ModelPreloadCoordinator.prepare()`
  - `_submit()`
  - `_wait()`
  - `V2LoaderBridge.prepare()`
  - `_find_request()`
  - `_load_unet()`
  - `_load_clip()`
  - `_prefill()`
  - `_consume_unet()`
  - `_consume_clip()`
  - `_consume_prefill()`

### Required events per model lane

- `preload_submitted`
- `preload_worker_started`
- `preload_worker_finished`
- `preload_worker_failed`
- `graph_model_demand`
- `graph_wait_started`
- `graph_wait_finished`
- `prepared_result_consumed`
- `identity_mismatch`
- `request_spec_missing`
- `future_unavailable`
- `future_failed`
- `original_loader_fallback`

### Required metadata

- Lane: UNET, CLIP or prefill
- Loader class
- Hashed planned identity
- Hashed requested identity
- Worker duration
- Graph wait duration
- Completed before graph demand
- Error category, without full sensitive exception payloads
- Terminal outcome

### Important coverage rule

Every graph loader demand must end in exactly one terminal outcome:

- `prepared`
- `fallback_identity_mismatch`
- `fallback_missing_spec`
- `fallback_future_error`
- `fallback_unavailable`

No early `_LOADER_MISS` return may remain untraced.

### Acceptance criteria

For every V2 run:

- Every expected model lane has a start and terminal result.
- UNET and CLIP graph waits are measured.
- Any preload work crossing from restore into execution is directly visible.
- Loader misses and fallback reasons are counted.
- Preload diagnostics can be reconciled with actual graph loader behavior.

### Durability

Keep aggregate worker, wait, terminal-status and miss events permanently. Detailed identity comparison metadata may be reduced after diagnosis.

## 10. Phase 5 — Prompt execution breakdown

### Purpose

Make the 34-second V2 execution interval sum to measured subphases.

### V2 locations

`comfymodal_runtime/modal_app.py::_execute_v2_prompt_executor()`:

- Legacy preload check
- Input-image materialization
- Preflight
- Missing-node repair
- Prompt validation
- Production request registration
- Executor reset
- PromptExecutor execution
- Output collection
- Cleanup

### Required spans

- `legacy_preload_check_start/end`
- `input_materialization_start/end`
- `preflight_start/end`
- `missing_node_repair_start/end`
- `prompt_validation_start/end`
- `production_registry_setup_start/end`
- `executor_reset_start/end`
- `prompt_executor_start/end`
- `output_collect_start/end`
- `production_cleanup_start/end`

### Graph-level stages

Prefer existing plugin/runtime hooks rather than editing ComfyUI core:

- UNET load
- CLIP load
- CLIP text encode
- Sampler preparation
- Sampler
- VAE load
- VAE decode
- Save/output nodes

If existing events do not expose these stages, add the narrowest wrapper in the custom node/runtime layer. Do not modify ComfyUI core during the first diagnostic pass.

### Required fields

- Duration
- Success/error
- Node count
- Output count
- Loader/cache source
- Backend requested and selected
- Cancellation state
- Sampler step count where already available, without logging prompt content

### Acceptance criteria

- The remote method duration is decomposed without overlapping double-counted spans.
- PromptExecutor time is separated from V2 orchestration.
- Model waits are not counted as unexplained PromptExecutor time.
- Any multi-second unexplained interval is identified before optimization.

### Durability

Keep PromptExecutor total, validation, model-load, sampler, VAE and output totals. Remove excessively granular temporary spans after diagnosis.

## 11. Phase 6 — Output collection and result delivery

### Purpose

Determine whether V2 spends material time selecting, converting or packaging outputs.

### Locations

- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/output_delivery.py`
- `comfymodal_runtime/result_delivery.py`
- Local V2 materialization boundary in `__init__.py`

### Required measurements

Per strategy:

- Direct production registry
- Executor history
- Request-bounded filesystem
- Any subprocess fallback

Record:

- Strategy start/end
- Success/failure
- Selected strategy
- Number of attempts
- Item count
- Raw bytes
- Conversion duration
- Base64 duration
- Result serialization size
- Local decode/write/materialization duration

### Acceptance criteria

- Exactly one selected output source is reported.
- Failed strategies and fallback depth are visible.
- Remote output work is separated from local materialization.
- Modal “Execution finished” is not conflated with browser-visible completion.

### Durability

Keep selected strategy, fallback count, conversion time and byte totals.

## 12. Phase 7 — V1 parity instrumentation

### Purpose

Produce equivalent measurements rather than comparing rich V2 traces with incomplete V1 traces.

### V1 boundaries

Instrument or map existing V1 events for:

- Deployment/resource identity
- Profile publication
- GPU submission
- First remote event
- Lifecycle restore
- Cold-UNET early load
- Prompt async preload
- Prompt async actual load
- Preflight
- Executor reset/run
- UNET/CLIP/VAE load
- CLIP encode
- Sampler
- VAE decode
- Output collection
- Remote return
- Local materialization

Reuse existing V1 timing systems where they already provide equivalent evidence. Do not duplicate events merely to rename them.

### Acceptance criteria

- Each primary V2 phase has a comparable V1 phase or is explicitly marked V2-only.
- Effective options are captured and compared using redacted key sets and stable hashes.
- V1 instrumentation does not alter its execution order or optimization settings.

## 13. Phase 8 — Trace integrity and focused tests

Before deployment, add focused tests for:

1. Remote events survive local trace merging.
2. Duplicate events are deduplicated without deleting valid events.
3. Cross-process events sort by wall time.
4. Durations use monotonic clocks only within one process.
5. Loader mismatches emit a terminal fallback event.
6. Future failures emit error and fallback events.
7. Prepared loader consumption emits no fallback.
8. Sensitive fields are absent.
9. Result payload shape is unchanged.
10. Instrumentation does not change backend selection or execution options.
11. Restore and execution traces coexist in the final result.
12. First stream event contains correlation identifiers without changing its existing type/phase semantics.

Run only focused tests covering modified boundaries before deployment. Broaden testing only if focused checks expose integration uncertainty.

## 14. Phase 9 — Controlled data collection

### Protocol

- Same workflow
- Same seed
- Same GPU
- Same cloud and region — **explicit matched V1/V2 cloud placement required**
  - Set `COMFYMODAL_V2_CLOUD` to the same cloud as V1's placement on every
    diagnosis run. The implicit RTX Pro 6000 → GCP pin has been removed; V2
    cloud placement is empty (global scheduling) unless the env var is set.
  - After every paired run, verify placement by inspecting `MODAL_CLOUD_PROVIDER`
    in the remote identity metadata of both V1 and V2 traces.
- Same output/production settings
- Same effective runtime options
- Same input images
- `COMFYMODAL_ENABLE_GPU_SNAPSHOT=0` or unset for **both** V1 and V2 runs unless
  a separately matched snapshot experiment has been explicitly approved.
- Requirements installation at startup **disabled** for both V1 and V2.  The
  `install_requirements_on_startup` override in `_configure_runtime` has been
  removed; the BootstrapConfig default (``False``) applies.
- Five V1 cold runs
- Five V2 cold runs
- Interleave variants where practical
- Wait 20 seconds between runs
- Verify coldness using a different container/task ID; do not invoke a health endpoint that could warm the tested container
- Save every run as timestamped JSON
- Do not automatically launch paid runs without explicit approval

### Required JSON data

Each run must contain:

```text
run_id
variant
request_id
trace_id
modal_input_id
container_task_id
image_id
resource_identity
workflow_hash
effective_options_hash
local_wall_clock_ms
publisher_ms
gpu_submit_to_first_event_ms
dashboard_input_to_scheduled_ms
dashboard_scheduled_to_execution_ms
dashboard_execution_ms
lifecycle_breakdown
preload_breakdown
execution_breakdown
output_breakdown
trace
status
errors
```

### Storage

Use a timestamped diagnosis folder under the existing benchmark-log convention. Do not overwrite historical results.

### Acceptance criteria

- Ten complete correlated run files.
- No missing identity, lifecycle, preload or execution data.
- Every run is demonstrably cold.
- Failed runs are retained and labeled rather than discarded.
- Medians are accompanied by all individual values.

## 15. Phase 10 — Analysis

Produce one comparison table containing:

- Total user-facing wall clock
- RestorePlan/profile publication
- GPU submission to first event
- Modal input queue
- Scheduled-to-execution
- Lifecycle total
- Volume reloads
- CUDA/Sage setup
- UNET/CLIP preload work
- UNET/CLIP graph wait
- Loader misses/fallbacks
- Validation/preflight
- PromptExecutor
- Sampler
- VAE
- Output collection/conversion
- Local materialization

### Required interpretation rules

- Do not assign queue time to application code without correlated evidence.
- Do not call an isolated phase improvement a win if total wall time regresses.
- Do not hide cold filesystem variance.
- Do not discard outliers without identifying a concrete invalid-run condition.
- Separate facts from hypotheses.
- Do not optimize based on one run.
- Preserve V1/V2 raw measurements beside medians.

## 16. Decision branches

### If deployed resource metadata differs

Document the exact differing fields. A subsequent controlled experiment may normalize one field at a time, but only after the diagnosis report is reviewed.

### If V2 queue time remains high with stable identity/configuration

The evidence package should include matched input IDs, class/image/resource metadata and OTel/dashboard queue metrics. This becomes a deployment/scheduling investigation rather than an execution-code optimization.

### If loader identity mismatches occur

Fix RestorePlan/spec/loader identity alignment first, then repeat the complete benchmark before other optimization.

### If futures finish after graph demand

The measured graph wait becomes the target. Possible overlap or I/O changes are evaluated only in the optimization phase.

### If PromptExecutor core time differs

Compare effective backend, model/cache source, sampler, SageAttention and GPU environment before changing orchestration.

### If validation/preflight is material

Determine whether equivalent validation already occurred locally and whether removing duplication preserves safety. Do not bypass validation solely based on intuition.

### If output fallback is selected

Correct the intended direct output path before tuning conversion or filesystem behavior.

### If no single phase dominates

Use the measured sum of smaller V2-only costs. Do not label it “framework overhead” without accounting for the individual spans.

## 17. Diagnosis completion gate

Optimization may begin only when:

- Every run is tied to the correct Modal input and container.
- Effective V1/V2 resource configuration is known.
- Local preparation and publisher time are separated from GPU time.
- Queue and lifecycle timing are correlated.
- All V2 loader demands have terminal outcomes.
- Preload spillover and graph waits are measured.
- PromptExecutor, sampler, VAE and output times are separated.
- Remote events survive trace merging.
- Five complete cold runs exist for each runtime.
- No unexplained multi-second interval remains.
- A written evidence report identifies measured contributors without unsupported claims.

## 18. Instrumentation lifecycle

### Keep permanently

- Deployment/input/container identity
- High-level local and remote phase spans
- Lifecycle stage totals
- Preload worker/wait/miss outcomes
- PromptExecutor, sampler and VAE totals
- Selected output strategy
- Trace merge integrity
- Error/fallback categories

### Remove or reduce after diagnosis

- Verbose individual hash/copy timings
- Detailed identity-comparison metadata
- Repeated payload-size breakdowns
- Temporary debug prints
- Any diagnostics that materially increase trace size without ongoing value

## 19. Expected files touched during implementation

Likely implementation scope:

- `__init__.py`
- `canonical_execution.py`
- `modal_client.py`
- `comfyapp.py`
- `comfymodal_runtime/modal_transport.py`
- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/runtime_bootstrap.py`
- `comfymodal_runtime/model_preload.py`
- `comfymodal_runtime/output_delivery.py`
- `comfymodal_runtime/result_delivery.py`
- `comfymodal_runtime/trace.py`
- Focused tests under `tests/`
- Existing benchmark/result collection utilities where appropriate

No ComfyUI core files should be changed during the initial diagnostic pass.

## 20. Implementation order

1. Trace schema and correlation identifiers
2. Trace merge integrity tests
3. Local and GPU submission boundaries
4. Lifecycle breakdown
5. Preload terminal outcomes and graph waits
6. Execution and output spans
7. V1 parity mapping
8. Focused tests
9. Instrumented deployment
10. Five-plus-five manual cold runs
11. Analysis report
12. User review before any optimization
