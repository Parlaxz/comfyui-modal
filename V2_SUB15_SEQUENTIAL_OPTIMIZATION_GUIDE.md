# ComfyUI Modal V2 — Sequential Sub-15-Second Optimization Execution Guide

**Repository:** `Parlaxz/comfyui-modal`  
**Source state reviewed:** `75d78dc1dbd8aa23a3c6f0d2de2adb745dbf2404`  
**Production reference before the snapshot-ablation experiments:** `4ac77e453d01697b0bbbb1837898d38474676450`  
**Primary target:** consistent true-cold command-to-response times below 15 seconds without warm containers  
**Non-negotiable deployment policy:** `min_containers=0`, `scaledown_window=4`  
**Primary GPU:** NVIDIA RTX PRO 6000 Blackwell Server Edition  
**Production model policy:** retain both the BF16 UNET and CLIP in the CPU memory snapshot unless a later measured step proves a better production configuration

---

# 1. Authority, safety, and execution rules

This document is a plan and implementation specification. **It is not authorization to execute anything automatically.**

The agent or engineer reading this document must obey all of the following:

1. Do not modify code until the user explicitly names the step to implement.
2. Do not deploy automatically.
3. Do not invoke Modal automatically.
4. Do not run paid benchmark generations automatically.
5. Do not commit automatically before the selected step passes its checklist.
6. Do not push, open a pull request, merge, or change branches unless explicitly requested.
7. Do not continue from one numbered step to the next without a new explicit instruction.
8. Do not combine multiple optimization steps into one commit.
9. Do not silently alter model precision, workflow semantics, sampling settings, image dimensions, seed behavior, CacheDiT behavior, or output encoding.
10. Do not claim an optimization win by moving time from one measured stage into another.
11. Do not delete diagnostic or experimental capabilities merely because they are disabled in production. Preserve them behind flags.
12. Do not use warm containers, keep-warm pings, scheduled warmups, a larger scaledown window, or `min_containers > 0`.
13. Do not treat Modal placement/scheduling outliers as application regressions, but always display them in the waterfall.
14. Do not hide failed runs or replace them with only the best run.
15. Stop immediately after completing the selected step, its local checks, and its implementation report. The user performs or explicitly authorizes deployment and benchmark runs.

The required workflow for **every** numbered step is:

```text
User explicitly authorizes one step
    ↓
Record starting commit and working-tree state
    ↓
Implement only that step
    ↓
Run only the local checks authorized for that step
    ↓
Show changed files, exact behavior, and expected markers
    ↓
STOP — no deploy and no paid generation
    ↓
User deploys with the batch file
    ↓
User performs three true-cold runs
    ↓
Review all three waterfalls and the step checklist
    ↓
If the checklist passes, create one commit for that step
    ↓
STOP — do not begin the next step
```

If a step fails its success checklist:

```text
Do not commit it
Do not begin the next step
Identify whether the failure is correctness, timing, identity, or variance
Make only a bounded correction to the same step after approval
Repeat its three-run validation
```

---

# 2. Global measurement rules

## 2.1 The optimization accounting rule

Every candidate must be judged using the complete non-overlapping waterfall.

A stage is not considered improved merely because its own timer decreases. The candidate must reduce one or both of:

```text
APP-CONTROLLED PATH
    app restore
  + restore-to-method gap controlled by this application
  + remote method setup
  + graph setup
  + PromptExecutor cache resolution
  + pre-sampler model/conditioning preparation
  + sampler startup
  + sampling
  + VAE decode
  + output encode/persist
  + local response processing

USER-VISIBLE PATH
    command start
  → durable response received locally
```

The following are prohibited accounting tricks:

- Moving CLIP encoding from pre-sampler into restore and calling it a pre-sampler win.
- Starting UNET activation in a background task, ending the restore timer, and then waiting for the same task later without including that wait.
- Ending a stage before a future, thread, file read, GPU transfer, or cache publication is complete.
- Excluding result collection or asset retrieval when the normal command waits for it.
- Comparing a first cold request against a second request in an already-restored container without labeling them differently.
- Comparing different workflow hashes, seeds, model identities, image dimensions, sampler steps, precision, or output behavior.
- Comparing a diagnostic model-free run against a production full-snapshot run as though they were equivalent.

## 2.2 Required benchmark identity

Each counted run must report and retain:

```text
repository commit
deployment app name
deployment class name
Modal image ID
GPU
cloud and region
workflow hash
source workflow hash
custom-node generation
deployment combined hash
restored_instance_id
restore_session_id
container_session_id
Modal task ID
request ID
sampler step count
UNET identity
CLIP identity
VAE identity
UNET effective weight dtype
UNET effective compute dtype
UNET manual_cast_dtype
CacheDiT version and activation status
```

A run with missing or conflicting identity fields remains visible but cannot be used as proof of success.

## 2.3 True-cold definition

A true-cold remote run must show:

- A fresh `restored_instance_id`.
- `restore_count=1`.
- `request_count=1` at the request entry.
- A restore lifecycle for that container.
- A gap long enough for the four-second scaledown policy to remove the previous container.
- No reuse of the prior remote container.
- No warm-container configuration.

Use a **20-second gap** between the three measured requests. This is longer than `scaledown_window=4` and leaves margin for result completion and platform cleanup.

The local Python process should remain alive across the three runs when testing local handle reuse. The remote container should not.

## 2.4 Commit discipline

Use one commit per successful step. Suggested messages are included in each step.

Before starting a step:

```powershell
git status --short
git rev-parse HEAD
```

After implementation but before deployment:

```powershell
git diff --check
git status --short
git diff --stat
```

Do not commit generated benchmark artifacts, downloaded traces, temporary files, Modal credentials, workspace secrets, or output images.

---

# 3. Standard deployment and three-run procedure

These procedures are referenced by every step.

## 3.1 Deploy only through the repository batch file

Direct `modal deploy` is not an accepted deployment method for this project. The batch file handles:

- Active workspace credentials.
- Warmup-profile extraction.
- V1/V2 deployment selection.
- Correct app and class names.
- Concurrent V1/V2 deployment when needed.
- Deployment output validation.
- The current environment inherited by the deployment subprocess.

Use:

```powershell
$env:COMFYMODAL_V2_ENV_PROFILE = "production"
$env:COMFYMODAL_DEPLOY_ONLY = "1"

.\deploy_and_run_v2_single.bat

$deployExit = $LASTEXITCODE
Remove-Item Env:COMFYMODAL_DEPLOY_ONLY -ErrorAction SilentlyContinue

if ($deployExit -ne 0) {
    throw "V2 deployment failed with exit code $deployExit"
}
```

The `COMFYMODAL_DEPLOY_ONLY=1` guard is added in Step 1. It must stop the batch after deployment verification and before the acceptance benchmark.

Expected ending:

```text
=== V2 deploy verified OK ===
=== Deploy-only requested; acceptance benchmark skipped ===
```

or, when V1 had to be deployed too:

```text
=== V1 and V2 deploys both verified OK ===
=== Deploy-only requested; acceptance benchmark skipped ===
```

## 3.2 Run three extra true-cold requests after deployment

Use one local Python process so Steps involving local handle reuse can be measured correctly, while retaining 20-second gaps so each remote request is cold.

Step 1 changes `run_v2_single.bat` so it respects caller-provided run-count and gap values instead of overwriting them.

```powershell
$env:COMFYMODAL_V2_ENV_PROFILE = "production"
$env:V2_BENCHMARK_RUNS = "3"
$env:V2_BENCHMARK_GAP_SECONDS = "20"

.\run_v2_single.bat

$runExit = $LASTEXITCODE

Remove-Item Env:V2_BENCHMARK_RUNS -ErrorAction SilentlyContinue
Remove-Item Env:V2_BENCHMARK_GAP_SECONDS -ErrorAction SilentlyContinue

if ($runExit -ne 0) {
    throw "Three-run V2 benchmark failed with exit code $runExit"
}
```

Required output:

- One detailed ASCII waterfall immediately after each run.
- One compact three-run comparison at the end.
- Three distinct restored instance IDs.
- Three run JSON artifacts.
- One summary JSON artifact.
- No automatic commit.

## 3.3 Production environment profile

The production profile must disable expensive diagnostics and experimental eviction behavior while preserving the code for later use.

Production values:

```text
COMFYMODAL_V2_FULL_TRACE=0
COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS=0
COMFYMODAL_V2_DEEP_MODEL_DIAG=0
COMFYMODAL_V2_PAGEFAULT_TRACKING=0
COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0
COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0
COMFYMODAL_V2_EVICT_RETAIN_ROLE=
COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1
COMFYMODAL_V2_PREFILL_LANES=critical
COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0
COMFYMODAL_V2_RESTORE_TORCH_THREADS=
```

The profile must not remove any implementation. An explicit diagnostic or experiment profile may re-enable any of these later.

---

# 4. Step order

The optimization sequence is:

1. Add a safe production environment profile and deploy-only control.
2. Add the detailed end-of-run ASCII waterfall.
3. Make the first cold request achieve warm-request cache timing without moving the time elsewhere.
4. Persist and asynchronously reuse the local Modal client/class/instance handle path.
5. Lock in the known BF16 + CacheDiT 3.7–4.0-second sampler path.
6. Prepare exact prompt conditioning before graph CLIP demand.
7. Start the exact UNET activation earlier using one shared future.
8. Compare deterministic sequential CLIP/UNET preparation orders.
9. Enable bounded CLIP/UNET concurrency only if it beats the sequential winner.
10. Trim proven duplicate snapshot ownership while retaining both models.

There is no separate final “benchmark everything” step. Every optimization is deployed, measured with three cold runs, approved, and committed before the next optimization begins.

---

# STEP 1 — Production environment profile and deploy-only control

## Objective

Return to a real production full-snapshot configuration without deleting diagnostic capabilities, and make deployment possible without automatically running a paid acceptance benchmark.

This step is configuration and safety plumbing. It should not alter model loading, execution, sampling, or outputs.

## Current relevant files

### `deploy_and_run_v2_single.bat`

Current behavior includes:

- Unconditionally setting `COMFYMODAL_V2_DEEP_MODEL_DIAG=1`.
- Unconditionally setting `V2_BENCHMARK_RUNS=1`.
- Deploying through the correct workspace-aware path.
- Automatically running `tools\benchmark_v2_direct.py --acceptance` after deployment.

### `run_v2_single.bat`

Current behavior includes:

- Unconditionally setting `COMFYMODAL_V2_DEEP_MODEL_DIAG=1`.
- Unconditionally setting `V2_BENCHMARK_RUNS=1`.
- Unconditionally setting `V2_BENCHMARK_GAP_SECONDS=0`.
- Capturing the command start and printing total command-to-response time.

### `comfymodal_runtime/modal_app.py`

Relevant symbol:

```python
def _runtime_env() -> dict[str, str]:
```

The current runtime environment allowlist already includes the snapshot-eviction flags. Do not replace the allowlist. Extend it only if a newly introduced production-profile variable must be sent to the remote class.

## Required implementation

### A. Add an explicit profile selector

In both batch files, add:

```bat
if not defined COMFYMODAL_V2_ENV_PROFILE set "COMFYMODAL_V2_ENV_PROFILE=inherit"
```

Supported values:

```text
inherit
production
diagnostic
```

Behavior:

- `inherit`: preserve externally supplied experimental values. This protects existing ablation workflows.
- `production`: explicitly disable diagnostic and eviction paths.
- `diagnostic`: keep existing diagnostic defaults or honor externally supplied values.

Do not make `production` silently override a user who explicitly requests an experiment unless the profile itself is explicitly set to production.

Recommended batch structure:

```bat
if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="production" (
    set "COMFYMODAL_V2_FULL_TRACE=0"
    set "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS=0"
    set "COMFYMODAL_V2_DEEP_MODEL_DIAG=0"
    set "COMFYMODAL_V2_PAGEFAULT_TRACKING=0"
    set "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=0"
    set "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0"
    set "COMFYMODAL_V2_EVICT_RETAIN_ROLE="
    set "COMFYMODAL_V2_PREFILL_LANES=critical"
    set "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET=0"
    set "COMFYMODAL_V2_RESTORE_TORCH_THREADS="
)

if /i "!COMFYMODAL_V2_ENV_PROFILE!"=="diagnostic" (
    if not defined COMFYMODAL_V2_DEEP_MODEL_DIAG set "COMFYMODAL_V2_DEEP_MODEL_DIAG=1"
)
```

For `inherit`, change existing unconditional diagnostic assignments to conditional defaults:

```bat
if not defined COMFYMODAL_V2_DEEP_MODEL_DIAG set "COMFYMODAL_V2_DEEP_MODEL_DIAG=0"
```

### B. Respect caller-provided benchmark settings

Change:

```bat
set "V2_BENCHMARK_RUNS=1"
set "V2_BENCHMARK_GAP_SECONDS=0"
```

to:

```bat
if not defined V2_BENCHMARK_RUNS set "V2_BENCHMARK_RUNS=1"
if not defined V2_BENCHMARK_GAP_SECONDS set "V2_BENCHMARK_GAP_SECONDS=0"
```

Apply this to both batch files where appropriate.

### C. Add deploy-only behavior

In `deploy_and_run_v2_single.bat`, after deployment verification and immediately before:

```bat
echo === Running V2 acceptance benchmark ===
```

add:

```bat
if /i "!COMFYMODAL_DEPLOY_ONLY!"=="1" (
    echo === Deploy-only requested; acceptance benchmark skipped ===
    exit /b 0
)
```

The default remains unchanged. Without the flag, the batch still runs acceptance.

### D. Preserve current app and class identity

Do not change:

```text
COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-shadow
COMFYMODAL_V2_CLASS_NAME=ModalRuntimeEntrypointV2
COMFYMODAL_V2_GPU=rtx-pro-6000
```

### E. Add lightweight verification output

Immediately before deployment, print a sanitized profile summary:

```text
[v2.env_profile]
profile=production
cpu_model_snapshot=1
full_trace=0
residency_diagnostics=0
deep_model_diag=0
pagefault_tracking=0
eviction_enabled=0
eviction_role=none
eviction_idle_seconds=0
prefill_lanes=critical
prefill_wait_for_unet=0
```

Never print credentials.

## Tests and checks

Suggested files:

- Add `tests/test_v2_batch_profiles.py`.
- Extend `tests/test_v2_static_modal_target.py` if it already validates batch constants.
- Extend `tests/test_run_deploys_concurrent.py` only if deploy-only changes interact with concurrent deployment.

The tests should read the batch files as text and assert:

- Explicit profile selector exists.
- Production profile disables diagnostics and eviction.
- Diagnostic paths remain present.
- `COMFYMODAL_DEPLOY_ONLY` skips only acceptance.
- App/class/GPU names remain unchanged.
- Caller-provided run count and gap are respected.
- No credential value is printed.

Local commands:

```powershell
python -m pytest -q tests/test_v2_batch_profiles.py tests/test_v2_static_modal_target.py tests/test_run_deploys_concurrent.py
python -m py_compile comfymodal_runtime\modal_app.py
git diff --check
```

Do not run them unless this step was explicitly authorized.

## Three-run success checklist

- [ ] Three runs used the production profile.
- [ ] `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1`.
- [ ] No `snapshot_model_eviction_idle` line appeared.
- [ ] No `retain_role=clip`, `retain_role=unet`, or `retain_role=none` experiment marker appeared.
- [ ] Full-trace collection remained disabled.
- [ ] Residency diagnostics remained disabled.
- [ ] Deep model diagnostics remained disabled.
- [ ] Both CLIP and UNET were available from the normal snapshot path.
- [ ] CacheDiT activated.
- [ ] Sampler remained approximately 3.7–4.0 seconds.
- [ ] No output-quality or workflow change.
- [ ] No paid acceptance run occurred during deploy-only mode.
- [ ] The three measured runs were invoked only after the user manually started them.

Suggested commit after approval:

```powershell
git add deploy_and_run_v2_single.bat run_v2_single.bat tests/test_v2_batch_profiles.py tests/test_v2_static_modal_target.py tests/test_run_deploys_concurrent.py
git commit -m "Add explicit V2 production deployment profile"
```

Stop after the commit.

---

# STEP 2 — Detailed ASCII waterfall at the end of every run

## Objective

Create one authoritative, readable, non-overlapping performance waterfall that appears immediately after each run and can be understood at a glance.

The waterfall must make it obvious:

- Where command time went.
- What belongs to Modal scheduling/platform restore.
- What belongs to application restore.
- What belongs to local submission.
- What belongs to graph setup and PromptExecutor.
- What belongs to CLIP, UNET, sampler startup, sampling, VAE, and output.
- Whether durations overlap.
- Whether stage totals reconcile with command-to-response wall time.
- Which values are measured, derived, unavailable, or inferred.
- Whether the run is fresh or reused.

The formatter must execute **after the response is received** so it cannot slow the measured remote path.

## Recommended file structure

### New file: `tools/v2_waterfall.py`

Keep formatting and extraction out of the remote runtime. This module should be local-only and pure.

Recommended types:

```python
@dataclass(frozen=True)
class Boundary:
    name: str
    wall_unix_ns: int | None
    monotonic_ns: int | None
    process: str
    source: str

@dataclass(frozen=True)
class WaterfallStage:
    key: str
    label: str
    group: str
    start_ns: int | None
    end_ns: int | None
    duration_ms: float | None
    cumulative_ms: float | None
    percentage: float | None
    source: str
    status: str
    overlaps: tuple[str, ...] = ()

@dataclass(frozen=True)
class WaterfallReport:
    run_label: str
    request_id: str
    identity: Mapping[str, Any]
    total_ms: float | None
    stages: tuple[WaterfallStage, ...]
    reconciliation_ms: float | None
    warnings: tuple[str, ...]
```

Recommended public functions:

```python
def build_waterfall(
    *,
    result: Mapping[str, Any],
    timing: Mapping[str, Any],
    wall_ms: float,
    command_start_unix_ms: int | None = None,
    response_received_unix_ns: int | None = None,
    run_label: str = "",
) -> WaterfallReport:
    ...

def render_waterfall(
    report: WaterfallReport,
    *,
    terminal_columns: int | None = None,
) -> str:
    ...

def waterfall_to_dict(report: WaterfallReport) -> dict[str, Any]:
    ...
```

### Update: `tools/benchmark_v2_direct.py`

Changes:

1. Import the new builder and renderer.
2. Capture `response_received_unix_ns` immediately after `execute_plan()` returns.
3. Build the report from the full merged trace and current timing extraction.
4. Store the structured report in each run artifact:
   ```python
   artifact["waterfall"] = waterfall_to_dict(report)
   ```
5. Print the ASCII report after the run JSON has been written.
6. Print a compact comparison table after all three runs.
7. Do not replace existing JSON timing fields; the waterfall is additive.
8. Do not remove existing trace output or acceptance checks.

### Update: `run_v2_single.bat`

After capturing `COMMAND_START_MS`, export it to the Python process:

```bat
set "COMFYMODAL_COMMAND_START_UNIX_MS=!COMMAND_START_MS!"
```

`benchmark_v2_direct.py` reads this value.

### Update: `deploy_and_run_v2_single.bat`

When acceptance is not skipped, capture a benchmark-specific start immediately before the benchmark invocation. Deployment duration must not appear as request latency.

```bat
for /f %%a in ('powershell -NoProfile -Command "[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()"') do set "COMFYMODAL_COMMAND_START_UNIX_MS=%%a"
python tools\benchmark_v2_direct.py --acceptance
```

## Boundary extraction rules

Use monotonic time only within one process. Use wall-clock time across local/remote process boundaries.

### Local boundaries

Preferred events/fields:

```text
command_start
local_receive
worker_start
normalize_production_options_start/end
runtime_trace_construct_start/end
build_execution_plan_call_start
execute_plan_call_start
transport_entry
modal_handle_lookup_start/end
modal_payload_serialize_start/end
modal_submission_attempt
modal_first_remote_event
final_result_received
response_received
```

### Remote lifecycle boundaries

Preferred fields/events:

```text
remote_python_resume_wall_unix_ns
restore_method_start_wall_unix_ns
restore_method_end_wall_unix_ns
remote_method_entry
prompt_executor_invoke_start
graph_execution_start
prompt_executor_milestones
pre_sampler_stages
sampling_start/end
vae_decode_start/end
output_encode_start/end
output_persist_start/end
```

### Fallback rules

For each stage:

1. Prefer exact event boundaries.
2. Otherwise use authoritative metadata already emitted in:
   - `v2.restoration_identity`
   - `v2.method_entry_gap`
   - `v2.pre_sampler_stages`
   - `v2.critical_path`
   - `v2.remote_request_origin.remote`
   - `local_timing`
3. Mark the source as `metadata` rather than `event`.
4. Never silently synthesize a zero.
5. Display unavailable data as `—`.
6. If a negative or impossible duration occurs, display `INVALID` and add a warning.
7. Do not add overlapping child durations to the parent total.

## Required non-overlapping top-level stages

The top-level waterfall should use these rows when boundaries exist:

```text
LOCAL PRE-SUBMISSION
1. Command/bootstrap before local request receipt
2. Local plan/profile/restore-plan preparation
3. Modal handle lookup
4. Payload serialization and submission

PLATFORM / RESTORE
5. Modal dispatch, scheduling, and host snapshot resume before Python
6. Application restore
7. Restore end to remote method entry

REMOTE PRE-SAMPLER
8. Remote method setup to PromptExecutor invocation
9. PromptExecutor start to cache resolution
10. Cached state to first executing node
11. First node to CLIP demand
12. CLIP/conditioning segment to sampler-node entry
13. Sampler-node entry to actual sampling start

GENERATION / OUTPUT
14. Sampling
15. Sampling end to VAE decode start
16. VAE decode
17. Output encode
18. Output persist/commit
19. Remote result to local result receipt
20. Local response finalization
```

Nested diagnostic rows may appear under a top-level row, but must be indented and labeled `detail`; they are not included again in the top-level total.

Examples:

```text
CLIP/conditioning segment
  ├─ CLIP loader wait
  ├─ exact conditioning encode
  ├─ conditioning cache publication
  └─ graph residual
```

```text
Sampler-node startup
  ├─ mutation-lane wait
  ├─ ModelPatcher work
  ├─ GPU activation wait
  ├─ CacheDiT binding
  └─ remaining residual
```

## Algorithmic spacing and bar construction

Use:

```python
terminal_width = shutil.get_terminal_size(fallback=(132, 40)).columns
terminal_width = max(110, min(180, terminal_width))
```

Column widths:

```text
index_width      = 3
label_width      = clamp(max label length + indentation, 28, 46)
duration_width   = 10
cumulative_width = 10
percent_width    = 7
source_width     = 10
bar_width        = remaining terminal width
minimum bar width = 24
```

If the terminal is narrower than the full layout:

1. Remove the `source` column first.
2. Then shorten labels with an ellipsis.
3. Never remove duration or the bar.
4. Never wrap one stage across multiple lines.

Bar scaling:

```python
bar_units = max(1, round(stage.duration_ms / total_ms * bar_width))
```

Characters:

```text
# measured application work
= Modal/platform time
+ local work
. unaccounted/reconciliation gap
! invalid or warning
```

The display should use plain ASCII only. Do not rely on Unicode box drawing or terminal color.

## Required waterfall output example

```text
V2 COLD WATERFALL — run 1
Commit: 75d78dc1dbd  Request: v2-benchmark-0-...  Instance: 999cb705...
Image: im-...  GPU: RTX-PRO-6000  Workflow: 4c765a6a4729  Fresh: YES

+----+------------------------------------------+----------+----------+-------+----------------------------------+
| #  | Stage                                    | Duration | Cum.     |   %   | Relative wall time               |
+----+------------------------------------------+----------+----------+-------+----------------------------------+
|  1 | Local plan/profile preparation           |   0.075s |   0.075s |  0.5% | +                                |
|  2 | Modal handle lookup                      |   0.042s |   0.117s |  0.3% | +                                |
|  3 | Payload submit                           |   0.018s |   0.135s |  0.1% | +                                |
|  4 | Modal scheduling + host snapshot resume  |   4.920s |   5.055s | 35.7% | ============                     |
|  5 | Application restore                      |   1.640s |   6.695s | 11.9% | ####                             |
|  6 | Restore end -> method entry              |   0.322s |   7.017s |  2.3% | #                                |
|  7 | Remote method setup                      |   0.244s |   7.261s |  1.8% | #                                |
|  8 | Executor -> cached                       |   1.350s |   8.611s |  9.8% | ###                              |
|  9 | Cached -> first node                     |   0.125s |   8.736s |  0.9% | #                                |
| 10 | First node -> CLIP                       |   0.153s |   8.889s |  1.1% | #                                |
| 11 | CLIP -> sampler node                     |   0.941s |   9.830s |  6.8% | ##                               |
| 12 | Sampler node -> sampling                 |   0.535s |  10.365s |  3.9% | #                                |
| 13 | Sampling                                 |   3.693s |  14.058s | 26.8% | #########                        |
| 14 | VAE + output                             |   0.650s |  14.708s |  4.7% | ##                               |
| 15 | Remote/local return                      |   0.410s |  15.118s |  3.0% | +                                |
+----+------------------------------------------+----------+----------+-------+----------------------------------+
|    | ACCOUNTED                                |  15.118s |          | 99.6% |                                  |
|    | UNATTRIBUTED                             |   0.061s |          |  0.4% | .                                |
|    | COMMAND -> RESPONSE                      |  15.179s |          |100.0% |                                  |
+----+------------------------------------------+----------+----------+-------+----------------------------------+

Targets:
  App-controlled path:  8.57s  [target <= 8.50s]
  Pre-sampler:          2.86s  [target <= 2.30s]
  Sampler:              3.69s  [PASS]
  Total:               15.18s  [MISS by 0.18s]

Largest controllable stages:
  1. Executor -> cached                  1.350s
  2. CLIP -> sampler node               0.941s
  3. Sampler node -> sampling           0.535s

Warnings:
  none
```

## Three-run comparison output

At the end:

```text
THREE-RUN COLD COMPARISON
+-----+--------+----------+---------+------------+---------+--------+---------+
| Run | Total  | Platform | Restore | PreSampler | Sampler | Output | Instance|
+-----+--------+----------+---------+------------+---------+--------+---------+
|  1  | 14.82s |    4.91s |   1.61s |      2.18s |   3.72s |  0.71s | a91... |
|  2  | 13.94s |    4.35s |   1.58s |      2.09s |   3.70s |  0.69s | c42... |
|  3  | 14.37s |    4.66s |   1.55s |      2.12s |   3.71s |  0.68s | f18... |
+-----+--------+----------+---------+------------+---------+--------+---------+
Median: 14.37s   Worst: 14.82s   3/3 below 15s
```

## Tests

Add `tests/test_v2_waterfall.py`.

Required cases:

- Exact complete trace.
- Missing command-start boundary.
- Missing restore boundary.
- Cross-process wall-clock stage.
- Same-process monotonic stage.
- Negative duration detection.
- Overlap detection.
- Reconciliation within tolerance.
- Reconciliation failure.
- Terminal widths: 90, 110, 132, 180, 220.
- Long labels.
- Missing values.
- Fresh and reused identity labels.
- Three-run comparison.
- Ensure formatter does not mutate result data.
- Ensure formatting occurs after the measured response boundary.
- Ensure no imports of remote ComfyUI or Modal runtime are needed.

Local commands:

```powershell
python -m pytest -q tests/test_v2_waterfall.py tests/test_v2_benchmark_trace_handoff.py tests/test_v2_observability_instrumentation.py
python -m py_compile tools\v2_waterfall.py tools\benchmark_v2_direct.py
git diff --check
```

## Success checklist

- [ ] A waterfall appears after every run.
- [ ] Three-run comparison appears at the end.
- [ ] Top-level rows do not overlap.
- [ ] Nested detail rows are visibly excluded from totals.
- [ ] Reconciliation error is no more than `max(50ms, 0.5% of total)`.
- [ ] Platform time and app-controlled time are separated.
- [ ] Missing data is shown as `—`, never silently zero.
- [ ] Terminal width is handled algorithmically.
- [ ] Output remains readable at 110 columns.
- [ ] Waterfall generation occurs after response receipt.
- [ ] No remote-path timing regression is attributable to formatting.
- [ ] Structured waterfall data is saved in each run JSON.
- [ ] No paid runs were started automatically.

Suggested commit:

```powershell
git add tools/v2_waterfall.py tools/benchmark_v2_direct.py run_v2_single.bat deploy_and_run_v2_single.bat tests/test_v2_waterfall.py
git commit -m "Add reconciled V2 cold-run waterfall"
```

Stop after the commit.

---

# STEP 3 — Cold-first-request cache parity

## Objective

Make the first request in a freshly restored container reach the sampler with approximately the same graph/cache preparation time as the immediate second request, **without moving the same time into restore, local submission, or another hidden future wait**.

Measured opportunity:

```text
cold pre-sampler: approximately 7.229s
warm-equivalent pre-sampler: approximately 1.755s
cold-only delta: approximately 5.474s
```

The main target is the first request’s `exec_start_to_cached` and related graph setup.

## Existing structures to extend

### `comfymodal_runtime/contracts.py`

Existing:

```python
@dataclass(frozen=True)
class SnapshotExecutionSeed:
```

It currently contains deterministic identity and loader/sampler signature fields. It explicitly avoids outputs, latents, random state, and request IDs.

### `comfymodal_runtime/runtime_bootstrap.py`

Existing state:

```python
BootstrapState.snapshot_execution_seed
BootstrapState.snapshot_loader_outputs
BootstrapState.snapshot_model_identities
BootstrapState.snapshot_seed_built
```

Existing builder:

```python
BootstrapState.build_snapshot_execution_seed(...)
```

The current restore path builds seed metadata from model identities. That is not yet enough to provide full first-request graph-cache parity.

### `comfymodal_runtime/runtime_executor.py`

Existing:

```python
class PreSamplerCache
```

It already caches request-scoped:

- Graph cache key.
- Prepared node inputs.
- Published model patches.
- Futures.
- Conditioning.
- Timing.

Do not replace it. Add an immutable snapshot-derived structural seed that initializes only deterministic reusable pieces.

### `comfymodal_runtime/modal_app.py`

The remote entrypoint owns the snapshotted bootstrap and passes execution state into request handling. It must provide the validated seed and snapshot loader outputs to the executor.

### `tests/test_v2_executor_seeding.py`

Already enforces fresh-request loader-seed evidence and timing presence. Extend behavioral coverage rather than replacing these tests.

## Required design

### A. Define schema version 2 of `SnapshotExecutionSeed`

Add only deterministic structural data:

```python
schema_version: int = 2
workflow_hash: str
source_workflow_hash: str
output_node_ids: tuple[str, ...]
reachable_node_ids: tuple[str, ...]
execution_order_hint: tuple[str, ...]
loader_node_ids: tuple[str, ...]
loader_cache_signatures: tuple[dict[str, Any], ...]
static_node_signatures: tuple[dict[str, Any], ...]
dynamic_input_map: tuple[dict[str, Any], ...]
sampler_node_ids: tuple[str, ...]
sampler_static_inputs: tuple[dict[str, Any], ...]
custom_node_generation: str
deployment_combined_hash: str
```

Never store:

- Output images.
- Conditioning tensors.
- Latents.
- Seed-dependent node outputs.
- Request IDs.
- Client IDs.
- Cancellation state.
- Progress state.
- Random state.
- Mutable ComfyUI cache objects that cannot survive snapshot identity validation.
- GPU objects or CUDA handles.

### B. Build the structural seed at snapshot startup

The structural seed should be created when:

- The canonical warmup workflow is known.
- Output nodes are known.
- Custom-node generation is frozen.
- Deployment identity is known.
- Loader signatures are known.

Do not wait until the first request to discover the graph topology.

Recommended changes:

- Add a pure graph-analysis helper, preferably in a new local/runtime-neutral module:
  `comfymodal_runtime/execution_seed.py`.
- Input: canonical workflow plus identity.
- Output: `SnapshotExecutionSeed`.
- Call it from the snapshot-startup path in `modal_app.py` after the startup certificate/warmup profile is established.
- Store the result on `RuntimeBootstrap.state`.

Keep `RuntimeBootstrap.build_snapshot_execution_seed()` as the authoritative storage method, but extend its arguments or allow it to accept a prebuilt seed.

### C. Compute static versus dynamic inputs

For each reachable node input, classify it:

```text
STATIC
- class_type
- fixed model filenames
- fixed loader options
- fixed sampler algorithm
- fixed scheduler
- fixed links between nodes
- fixed output routing

DYNAMIC
- positive/negative prompt text
- seed
- width/height when user-controlled
- input images
- masks
- denoise when user-controlled
- LoRA strength when user-controlled
- any request_metadata value
```

The seed should store a hash of static values and an explicit list of dynamic keys. It must not guess that an unknown input is static.

Default unknown classification: dynamic.

### D. Seed ComfyUI’s executor carefully

At request start:

1. Validate:
   - Workflow hash.
   - Source workflow hash where applicable.
   - Custom-node generation.
   - Deployment combined hash.
   - Loader identities.
2. Instantiate the normal PromptExecutor and normal caches.
3. Seed only deterministic structural/cache-key state.
4. Seed loader outputs only when exact object identity matches.
5. Invalidate all nodes downstream of changed dynamic inputs.
6. Run the normal ComfyUI cache validation against the seeded state.
7. Fall back to the existing cold path on any mismatch.

Do not bypass ComfyUI’s correctness checks. The goal is to give them prepared deterministic information, not disable them.

### E. Integrate with `PreSamplerCache`

Add an optional constructor parameter:

```python
snapshot_seed: SnapshotExecutionSeed | None = None
```

Possible new methods:

```python
def apply_snapshot_seed(self, seed: SnapshotExecutionSeed, plan: ExecutionPlan) -> SnapshotSeedDecision:
    ...

def invalidate_dynamic_inputs(self, plan: ExecutionPlan) -> set[str]:
    ...
```

Return structured diagnostics:

```text
seed_version
identity_match
static_nodes_seeded
loader_nodes_seeded
dynamic_nodes_invalidated
downstream_nodes_invalidated
fallback_reason
apply_ms
```

### F. Emit authoritative markers

Add trace events:

```text
snapshot_graph_seed_validate_start/end
snapshot_graph_seed_apply_start/end
snapshot_graph_seed_fallback
prompt_executor_seed_summary
```

The summary should include:

```text
decision=seeded|partial|fallback
seed_apply_ms
seeded_static_nodes
seeded_loader_nodes
invalidated_dynamic_nodes
invalidated_downstream_nodes
workflow_match
generation_match
deployment_match
```

### G. Do not move time into restore

The seed is built at deployment/snapshot creation, not reconstructed during every restore.

At restore, only identity validation and object binding are allowed.

Target:

```text
seed validation + binding <= 25ms
```

If app restore rises materially, the candidate fails even if pre-sampler improves.

## Files expected to change

```text
comfymodal_runtime/contracts.py
comfymodal_runtime/execution_seed.py              # new
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/runtime_executor.py
comfymodal_runtime/modal_app.py
tools/benchmark_v2_direct.py                      # acceptance/waterfall fields only
tests/test_v2_executor_seeding.py
tests/test_v2_pre_sampler_attribution.py
tests/test_v2_cold_warm_parity.py                 # new
```

`canonical_execution.py` may change only if the exact static/dynamic plan metadata is not currently available in `ExecutionPlan`.

## Required tests

- Exact seed identity applies.
- Workflow mismatch falls back.
- Custom-node generation mismatch falls back.
- Deployment hash mismatch falls back.
- Changed prompt invalidates CLIP conditioning path.
- Changed seed invalidates sampler-dependent nodes.
- Changed input image invalidates dependent path.
- Unchanged loader nodes reuse exact objects.
- No output/latent/random state appears in seed serialization.
- First request and immediate second request produce equivalent cache decisions.
- No duplicate loader object is created.
- Seed application time is emitted.
- A fallback produces the same result as the original cold path.
- Reused request behavior remains correct.

Suggested local command:

```powershell
python -m pytest -q tests/test_v2_executor_seeding.py tests/test_v2_pre_sampler_attribution.py tests/test_v2_cold_warm_parity.py
python -m py_compile comfymodal_runtime\execution_seed.py comfymodal_runtime\runtime_bootstrap.py comfymodal_runtime\runtime_executor.py comfymodal_runtime\modal_app.py
git diff --check
```

## Three-run success checklist

For each cold run:

- [ ] Fresh remote instance.
- [ ] `prompt_executor_seed_summary decision=seeded`.
- [ ] Exact workflow, generation, and deployment identity match.
- [ ] No duplicate CLIP or UNET physical load caused by seeding.
- [ ] `exec_start_to_cached_ms` is no more than warm median + 100ms.
- [ ] Cold pre-sampler is within 10% of warm pre-sampler or within +250ms, whichever is more permissive.
- [ ] `restore + pre-sampler` falls by approximately the same amount as pre-sampler.
- [ ] App restore does not increase by more than 100ms median.
- [ ] Local submission does not increase by more than 50ms median.
- [ ] No background future continues hidden work beyond its reported stage.
- [ ] Output hash/asset identity remains correct.
- [ ] Sampler remains 3.7–4.0 seconds.
- [ ] All three waterfalls reconcile.

Hard rejection:

```text
If pre-sampler improves by X but restore, method setup, or a later wait increases by approximately X,
the step has only moved time and must not be committed.
```

Suggested commit:

```powershell
git add comfymodal_runtime/contracts.py comfymodal_runtime/execution_seed.py comfymodal_runtime/runtime_bootstrap.py comfymodal_runtime/runtime_executor.py comfymodal_runtime/modal_app.py tools/benchmark_v2_direct.py tests/test_v2_executor_seeding.py tests/test_v2_pre_sampler_attribution.py tests/test_v2_cold_warm_parity.py
git commit -m "Seed cold V2 execution cache from snapshot"
```

Stop after the commit.

---

# STEP 4 — Persistent local Modal handle reuse

## Objective

Reduce local submission overhead by reusing the Modal client, class lookup, class instance handle, active-profile state, and restore-plan publication state inside the persistent ComfyUI process.

This step does not reduce Modal scheduling. It removes repeated local work.

## Existing structures

### `comfymodal_runtime/modal_transport.py`

Existing:

```python
class HandleCacheKey
class HandleCache
_SHARED_HANDLE_CACHE = HandleCache()
class ModalTransport
```

Existing `_v2_handle()`:

- Computes a key from workspace, app, class, environment, cloud, GPU, and factory identity.
- Checks the shared handle cache.
- On miss, calls:
  - `modal.Client.from_credentials`
  - `modal.Cls.from_name`
  - `cls_handle()`
- Stores the handle.

The main remaining concerns are:

- Synchronous client/class construction inside async request handling.
- A new local process naturally has an empty cache.
- Some call paths may create new transport/publisher objects per request.
- Restore-plan and active-profile caches must use stable identity and avoid unnecessary remote publication.

## Required implementation

### A. Add a client cache separate from the handle cache

Add:

```python
@dataclass(frozen=True)
class ClientCacheKey:
    workspace_id: str
    token_id_hash: str
    environment: str

class ClientCache:
    ...
```

Never store or log the raw token secret in the key. Use an in-memory non-reversible identity derived from safe credential identity components.

### B. Add an async-safe handle resolver

Recommended API:

```python
async def _v2_handle_async(
    self,
    *,
    workspace: dict[str, Any] | None,
    gpu: Any = None,
    runtime_trace: RuntimeTrace | None = None,
) -> Any:
```

Behavior:

1. Fast synchronous dictionary lookup.
2. On cache hit, return immediately.
3. On miss, use one single-flight future per `HandleCacheKey`.
4. Resolve credentials/client/class/instance once.
5. If the Modal SDK lacks a fully async lookup API, use `asyncio.to_thread()` only on the miss.
6. Publish the result to the shared cache.
7. Other requests await the same future.
8. Failure removes the pending future and does not poison the cache.

Update `run_plan_stream()` to call the async resolver.

Keep `_v2_handle()` for synchronous/test compatibility where needed, but do not call it directly from the async production hot path.

### C. Ensure one long-lived transport in the plugin process

Inspect:

```text
canonical_execution.py
__init__.py
modal_client.py
```

The persistent ComfyUI server process should own or reuse one `ModalTransport`.

Do not instantiate a fresh transport for each UI request unless it shares the same caches and single-flight state.

### D. Persist active-profile and restore-plan decisions

Use exact keys:

```text
workspace
app
class
environment
GPU
workflow hash
model restore key
prefill key
restore-plan generation
```

Do not republish an unchanged plan.

Required markers:

```text
profile_cache_hit
profile_remote_call_performed
restore_publish_cache_hit
restore_remote_call_performed
handle_cache_hit
client_cache_hit
class_cache_hit
instance_cache_hit
```

### E. Preserve benchmark validity

The standard three-run procedure uses one Python process with 20-second remote gaps. This allows local handle reuse while still producing three cold remote containers.

The first local request may miss. Requests two and three must hit.

## Files expected to change

```text
comfymodal_runtime/modal_transport.py
comfymodal_runtime/restore_plan.py
canonical_execution.py
modal_client.py
tools/benchmark_v2_direct.py
tests/test_local_submission_critical_path.py
tests/test_v2_local_submission_timing.py
tests/test_v2_local_pre_submit_optimization.py
tests/test_modal_transport_handle_cache.py            # new if needed
```

## Tests

- One client creation per key.
- One class lookup per key.
- One instance construction per key.
- Concurrent misses join one future.
- Credential identity change creates a new client.
- Environment/app/class/GPU change creates a new handle.
- Failure clears pending single-flight state.
- No raw secrets in logs or cache diagnostics.
- Async hot path produces no `AsyncUsageWarning`.
- Unchanged restore plan is not republished.
- Changed restore plan is published.

## Three-run success checklist

- [ ] Run 1 may miss the local handle cache.
- [ ] Runs 2 and 3 show `handle_cache_hit=True`.
- [ ] Runs 2 and 3 show no new Modal client.
- [ ] Runs 2 and 3 show no `Cls.from_name`.
- [ ] Runs 2 and 3 show no new class instance construction.
- [ ] `local_receive_to_modal_call_ms <= 75ms` on runs 2 and 3.
- [ ] Active-profile lookup remains local on all unchanged runs.
- [ ] Restore-plan publication remains local on all unchanged runs.
- [ ] Remote containers are still cold and distinct.
- [ ] No timing is moved into an earlier unmeasured local initialization.
- [ ] No credentials are logged.
- [ ] No change to remote output.

Suggested commit:

```powershell
git add comfymodal_runtime/modal_transport.py comfymodal_runtime/restore_plan.py canonical_execution.py modal_client.py tools/benchmark_v2_direct.py tests/test_local_submission_critical_path.py tests/test_v2_local_submission_timing.py tests/test_v2_local_pre_submit_optimization.py tests/test_modal_transport_handle_cache.py
git commit -m "Persist V2 local Modal transport identity"
```

Stop after the commit.

---

# STEP 5 — Preserve the 3.7–4.0-second BF16 + CacheDiT sampler

## Objective

Turn the known good sampler path into an enforced invariant before making CLIP/UNET preparation changes.

This step is primarily hardening and regression detection. Do not redesign the sampler unless the known path is missing.

## Required invariants

UNET:

```text
effective_snapshot_weight_dtype=bfloat16
effective_snapshot_compute_dtype=bfloat16
effective_snapshot_manual_cast_dtype=none
first_parameter_dtype=torch.bfloat16
manual_cast_dtype absent/None
```

CacheDiT:

```text
cache_dit import succeeds
expected dependency family is loaded
exact UNET object is patched
patch occurs once
graph consumes the patched object
sampler uses that same object
```

RES4LYF/Sage:

```text
restore exact-match path remains active
no duplicate patch discovery
sampler algorithm and step count remain unchanged
```

## Files to inspect and possibly change

```text
comfymodal_runtime/cpu_snapshot_models.py
comfymodal_runtime/model_preload.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/unet_forward_probe.py
comfyapp.py
tests/test_cachedit_dependency_family.py
tests/test_v2_unet_runtime_ab.py
tests/test_cpu_snapshot_models.py
```

## Required implementation

### A. Add a sampler-path identity summary

Emit once per request before sampling:

```text
[v2.sampler_identity]
unet_object_id=
patcher_object_id=
diffusion_model_object_id=
weight_dtype=
compute_dtype=
manual_cast_dtype=
cachedit_version=
cachedit_patched=
cachedit_patch_count=
res4lyf_prepared=
sage_decision=
steps=
sampler_name=
scheduler=
```

No tensor values.

### B. Add benchmark acceptance checks

The waterfall/benchmark should flag:

- Sampler above 4.0 seconds.
- Missing CacheDiT.
- Wrong dtype.
- Non-null manual cast.
- Duplicate CacheDiT patch.
- Different UNET object between activation and sampler.
- Wrong step count.

### C. Do not change the algorithm

This step may fix identity propagation or missing patch reuse. It must not change:

- Sampler.
- Scheduler.
- Steps.
- CFG.
- Denoise.
- Model precision.
- Image dimensions.
- Workflow.

## Success checklist

- [ ] Three samplers are each <= 4.0 seconds.
- [ ] Median sampler <= 3.9 seconds.
- [ ] CacheDiT is active on all three.
- [ ] One CacheDiT patch per UNET object.
- [ ] Sampler UNET identity equals the prepared/snapshotted UNET identity.
- [ ] BF16 weight and compute dtype.
- [ ] `manual_cast_dtype` absent/None.
- [ ] Eight steps.
- [ ] No quality change.
- [ ] No added restore or pre-sampler cost above 50ms median.

Suggested commit:

```powershell
git add comfymodal_runtime/cpu_snapshot_models.py comfymodal_runtime/model_preload.py comfymodal_runtime/runtime_bootstrap.py comfymodal_runtime/modal_app.py comfymodal_runtime/unet_forward_probe.py tools/benchmark_v2_direct.py tests/test_cachedit_dependency_family.py tests/test_v2_unet_runtime_ab.py tests/test_cpu_snapshot_models.py
git commit -m "Enforce V2 BF16 CacheDiT sampler identity"
```

Stop after the commit.

---

# STEP 6 — Prepare exact prompt conditioning before graph CLIP demand

## Objective

Encode the actual positive and negative prompt as early as safely possible so graph `CLIPTextEncode` consumes a completed or nearly completed exact result.

Do not use dummy warmup text. Do not reuse conditioning across mismatched prompts.

## Existing structures

### `comfymodal_runtime/contracts.py`

Existing:

```python
ModelRestoreKey
PrefillKey
RestorePlan
ExecutionPlan.prompt_bundle
```

### `comfymodal_runtime/model_preload.py`

Existing:

```python
class V2LoaderBridge
class ModelPreloadCoordinator
schedule_execution_prefill(...)
COMFYMODAL_V2_PREFILL_LANES
COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET
```

The current system already has execution-phase prefill and single-flight concepts. Extend these rather than creating a new cache.

### `comfymodal_runtime/restore_plan.py`

Responsible for deriving and publishing the exact restore/prefill plan.

## Required implementation

### A. Build exact encode entries from graph topology

For each `CLIPTextEncode` that feeds a sampler conditioning input:

```text
node_id
exact text
role=positive|negative
upstream CLIP loader node
CLIP identity
CLIP type
prompt bundle hash
workflow hash
custom-node generation
```

Role inference must be based on explicit graph edges to sampler positive/negative inputs.

Ambiguous encode nodes remain ineligible.

Do not globally set `lane=all` in production.

### B. Strengthen the conditioning key

The single-flight/cache key must include:

```text
exact text hash
role
CLIP object identity
CLIP model identity
CLIP type
workflow hash
prompt bundle hash
custom-node generation
deployment hash
encode options
```

### C. Start at the earliest safe request boundary

Preferred sequence:

```text
restore plan already published
remote method receives exact request
    ↓
validate request plan against published plan
    ↓
bind exact snapshotted CLIP object
    ↓
schedule exact conditioning future
    ↓
continue PromptExecutor setup in parallel
    ↓
graph CLIPTextEncode joins the same future
```

Do not start encoding during generic snapshot restore unless the exact request identity is already bound and proven current.

### D. Single-flight behavior

- One future per exact key.
- Graph joins the future.
- No second encode.
- Failure is terminal before fallback.
- Exactly one fallback caller may execute original `CLIPTextEncode`.
- Late background success cannot overwrite fallback.
- Request cancellation does not leak a running encode.

### E. Output equivalence

Compare the normal encode output and prefetched output structurally:

- Same conditioning shape.
- Same pooled output presence.
- Same metadata.
- Same final image/output hash under deterministic settings where exact binary output is expected.

## Files expected to change

```text
comfymodal_runtime/contracts.py
comfymodal_runtime/restore_plan.py
comfymodal_runtime/model_preload.py
comfymodal_runtime/runtime_executor.py
production_workflow.py
comfymodal_runtime/modal_app.py
tests/test_model_preload_prefill_overlap.py
tests/test_v2_prompt_executor.py
tests/test_v2_preload_bridge.py
tests/test_v2_exact_prompt_prefill.py             # new
```

## Required markers

```text
execution_prefill_eligible
execution_prefill_scheduled
execution_prefill_started
execution_prefill_completed
execution_prefill_consumed
execution_prefill_fallback
```

Metadata:

```text
node_id
role
text_hash
clip_object_id
single_flight_hit
schedule_to_start_ms
encode_ms
completion_to_graph_demand_ms
graph_wait_ms
fallback_reason
```

## Success checklist

- [ ] Exactly one positive/negative encode per required text.
- [ ] No dummy text.
- [ ] No stale prompt reuse.
- [ ] Graph CLIP node consumes the same future/result.
- [ ] No duplicate encode.
- [ ] Graph-visible conditioning wait <= 200ms.
- [ ] `restore + pre-sampler` decreases; time is not merely moved into restore.
- [ ] App restore increase <= 100ms median.
- [ ] Prompt change causes a new key.
- [ ] Model/generation/workflow mismatch falls back.
- [ ] Output equivalence passes.
- [ ] Memory cache remains bounded/request-scoped.
- [ ] Sampler remains <= 4.0 seconds.

Suggested commit:

```powershell
git add comfymodal_runtime/contracts.py comfymodal_runtime/restore_plan.py comfymodal_runtime/model_preload.py comfymodal_runtime/runtime_executor.py production_workflow.py comfymodal_runtime/modal_app.py tests/test_model_preload_prefill_overlap.py tests/test_v2_prompt_executor.py tests/test_v2_preload_bridge.py tests/test_v2_exact_prompt_prefill.py
git commit -m "Prefill exact V2 prompt conditioning"
```

Stop after the commit.

---

# STEP 7 — Start exact UNET activation earlier

## Objective

Begin preparing the exact snapshotted BF16 UNET for GPU use immediately after CUDA restoration and exact identity validation, so the graph does not perform the same activation late at sampler demand.

## Existing structures

```text
comfymodal_runtime/model_preload.py
    ModelPreloadCoordinator
    V2LoaderBridge
    GPU mutation lane
    UNET future
    graph cache bridge

comfymodal_runtime/cpu_snapshot_models.py
    canonical CPU snapshot model ownership
    UNET runtime state

comfymodal_runtime/unet_forward_probe.py
    demand and first-forward instrumentation

comfymodal_runtime/runtime_bootstrap.py
    CUDA initialization and restore sequence

comfymodal_runtime/modal_app.py
    entrypoint restore and request binding
```

## Required implementation

### A. Create one activation state machine

Suggested states:

```text
PENDING
CPU_OBJECT_BOUND
WAITING_FOR_CUDA
WAITING_FOR_MUTATION_LANE
GPU_ACTIVATING
CACHE_COMMITTING
READY
FAILED
CANCELLED
```

Exact activation key:

```text
UNET path/identity
diffusion model identity
ModelPatcher identity
weight dtype
compute dtype
manual cast dtype
load/offload device
model options
patch/adaptor identity
CacheDiT identity
custom-node generation
deployment hash
```

### B. Start only after CUDA is valid

In `runtime_bootstrap.py` or the entrypoint restore orchestration:

1. Finish `initialize_cuda`.
2. Verify the snapshot UNET identity.
3. Verify no conflicting active activation.
4. Submit one activation future.
5. Return control without waiting for full completion unless correctness requires a short bind barrier.

### C. Use the existing mutation lane

Do not create a second GPU lock.

The activation future must acquire the same coordinator-owned mutation lane used by normal model GPU/cache mutations.

### D. Make graph demand join

When graph loader or sampler demands the UNET:

- Find exact activation key.
- If `READY`, use it.
- If pending, await the same future.
- If failed, elect exactly one fallback.
- Never start a duplicate foreground GPU activation.
- Never publish a late object over a fallback result.

### E. Preserve object identity

The exact `ModelPatcher` and underlying diffusion model used by activation must be the ones consumed by CacheDiT and the sampler.

Do not reconstruct an “equivalent” patcher unless exact fallback rules require it.

## Files expected to change

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/cpu_snapshot_models.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/unet_forward_probe.py
comfymodal_runtime/runtime_executor.py
tests/test_v2_unet_activation.py                 # new
tests/test_v2_unet_runtime_ab.py
tests/test_v2_preload_bridge.py
tests/test_model_preload_critical_path.py
```

## Required markers

```text
unet_activation_submitted
unet_activation_started
unet_activation_lane_acquired
unet_activation_gpu_ready
unet_activation_published
unet_activation_graph_join
unet_activation_fallback
```

Include:

```text
activation_key_hash
patcher_object_id
diffusion_model_object_id
schedule_to_start_ms
lane_wait_ms
gpu_activation_ms
cache_publish_ms
graph_wait_ms
single_flight_hit
```

## Success checklist

- [ ] One UNET activation future.
- [ ] No duplicate CPU load.
- [ ] No duplicate GPU transfer.
- [ ] No duplicate ModelPatcher.
- [ ] No duplicate CacheDiT patch.
- [ ] Graph demand joins the same future.
- [ ] `sampler_node_to_sampler_start_ms <= 500ms` median.
- [ ] Combined restore-to-sampling-start decreases.
- [ ] Restore is not inflated by the same saved duration.
- [ ] Peak VRAM remains within safe limits.
- [ ] No OOM, deadlock, offload race, or stale object.
- [ ] Sampler remains <= 4.0 seconds.
- [ ] Output unchanged.

Suggested commit:

```powershell
git add comfymodal_runtime/model_preload.py comfymodal_runtime/cpu_snapshot_models.py comfymodal_runtime/runtime_bootstrap.py comfymodal_runtime/modal_app.py comfymodal_runtime/unet_forward_probe.py comfymodal_runtime/runtime_executor.py tests/test_v2_unet_activation.py tests/test_v2_unet_runtime_ab.py tests/test_v2_preload_bridge.py tests/test_model_preload_critical_path.py
git commit -m "Activate snapshotted V2 UNET before graph demand"
```

Stop after the commit.

---

# STEP 8 — Compare deterministic sequential CLIP/UNET preparation orders

## Objective

Determine the fastest safe sequential order before enabling concurrency.

This step adds an explicit, measurable scheduling policy. It is not permission to overlap the operations yet.

## Required scheduling modes

Add:

```text
COMFYMODAL_V2_PREP_SCHEDULE=clip_then_unet
COMFYMODAL_V2_PREP_SCHEDULE=unet_then_clip
```

Optional safe default:

```text
auto
```

`auto` must resolve to the currently proven production order, not dynamically guess during a request.

## Implementation

In `model_preload.py`, centralize scheduling decisions in one function:

```python
def resolve_preparation_schedule(...) -> PreparationSchedule:
    ...
```

Use one explicit coordinator. Do not let CLIP and UNET independently self-schedule.

For `clip_then_unet`:

```text
bind CLIP
start/finish exact conditioning as allowed
then acquire UNET activation path
```

For `unet_then_clip`:

```text
start/finish UNET activation
then run exact conditioning
```

Record:

```text
schedule mode
CLIP start/end
UNET start/end
combined interval
mutation-lane occupancy
graph wait
peak CPU
peak RAM
peak VRAM
```

## Files expected to change

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/contracts.py                 # only if schedule metadata belongs in plan
tools/benchmark_v2_direct.py
tools/v2_waterfall.py
tests/test_v2_preparation_schedule.py           # new
```

## Benchmark protocol

Deploy and test one mode at a time.

Mode A:

```powershell
$env:COMFYMODAL_V2_PREP_SCHEDULE = "clip_then_unet"
```

Three cold runs.

Mode B:

```powershell
$env:COMFYMODAL_V2_PREP_SCHEDULE = "unet_then_clip"
```

Redeploy with the batch file, then three cold runs.

Do not compare runs from different commits or images.

## Decision rule

Choose the winner by:

1. Median command-to-response.
2. Median app-controlled path.
3. Worst of three command-to-response.
4. Pre-sampler.
5. Variance.
6. Correctness and resource safety.

A mode that improves median but causes one severe contention/outlier may lose.

## Success checklist

- [ ] Both modes use identical workflow and deployment code.
- [ ] Both modes are sequential with zero overlap.
- [ ] Six total runs are visible.
- [ ] No duplicate work.
- [ ] No stage-time relocation.
- [ ] One mode is clearly faster or the result is declared inconclusive.
- [ ] Production default changes only if the winner is supported.
- [ ] If tied within noise, retain the simpler current order.
- [ ] No next step begins automatically.

Suggested commit for the scheduling framework and proven default:

```powershell
git add comfymodal_runtime/model_preload.py comfymodal_runtime/modal_app.py comfymodal_runtime/contracts.py tools/benchmark_v2_direct.py tools/v2_waterfall.py tests/test_v2_preparation_schedule.py
git commit -m "Add deterministic V2 preparation scheduling"
```

Stop after the commit.

---

# STEP 9 — Bounded CLIP/UNET concurrency, only if it wins

## Objective

Overlap exact CLIP preparation and UNET activation only when Step 8 proves that enough independent work exists to reduce total wall time.

If Step 8 shows no useful opportunity, skip this step and create no commit.

## Required concurrency model

Exactly two top-level tasks:

```text
one exact CLIP conditioning task
one exact UNET activation task
```

No general worker pool expansion. No recursive futures. No speculative third task.

Add mode:

```text
COMFYMODAL_V2_PREP_SCHEDULE=bounded_parallel
```

Keep it disabled by default until proven.

## Resource rules

May overlap:

- Independent CPU bookkeeping.
- Exact prompt tokenization.
- Independent CPU-side preparation.
- Non-conflicting metadata work.

Must remain serialized by the existing mutation lane:

- Global ComfyUI loaded-model cache mutation.
- GPU placement and offload.
- ModelPatcher mutation.
- CacheDiT attachment.
- CLIP GPU encode if it conflicts with model mutation.
- Sampler start.

## Implementation

In `model_preload.py`:

- Reuse coordinator and existing executor.
- Cap concurrent top-level preparation tasks at two.
- Record both task intervals and actual overlap.
- Track CPU process time and effective cores.
- Track mutation-lane owner and wait.
- Ensure graph demand joins existing futures.
- Ensure cancellation terminates both or reaches safe terminal states.
- Ensure request completion does not leave request-owned tasks running.

## Files expected to change

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_executor.py
tools/v2_waterfall.py
tools/benchmark_v2_direct.py
tests/test_model_preload_prefill_overlap.py
tests/test_model_preload_critical_path.py
tests/test_v2_bounded_preparation.py            # new
```

## Required output

```text
clip_interval_ms
unet_interval_ms
overlap_ms
combined_interval_ms
sequential_equivalent_ms
overlap_efficiency
peak_effective_cores
mutation_lane_wait_ms
peak_rss_mib
peak_vram_mib
```

Calculate:

```text
sequential_equivalent = clip_duration + unet_duration
overlap_efficiency = (sequential_equivalent - combined_interval) / min(clip_duration, unet_duration)
```

Do not claim a concurrency win based only on positive overlap. End-to-end must improve.

## Success checklist

- [ ] Exactly two top-level tasks.
- [ ] One CLIP future.
- [ ] One UNET future.
- [ ] Existing mutation lane remains exclusive.
- [ ] No deadlock in three cold runs.
- [ ] No duplicate model load, encode, patch, or transfer.
- [ ] Combined preparation interval beats Step 8’s sequential winner.
- [ ] Median total improves by at least 250ms.
- [ ] Worst-of-three does not regress by more than 250ms.
- [ ] Peak RAM and VRAM remain safe.
- [ ] CPU contention does not produce a longer pre-sampler path.
- [ ] No request-owned background task survives result completion.
- [ ] Output unchanged.
- [ ] If any required item fails, leave bounded parallel disabled and do not commit it as production behavior.

Suggested commit only after a real win:

```powershell
git add comfymodal_runtime/model_preload.py comfymodal_runtime/modal_app.py comfymodal_runtime/runtime_executor.py tools/v2_waterfall.py tools/benchmark_v2_direct.py tests/test_model_preload_prefill_overlap.py tests/test_model_preload_critical_path.py tests/test_v2_bounded_preparation.py
git commit -m "Overlap bounded V2 CLIP and UNET preparation"
```

Stop after the commit.

---

# STEP 10 — Trim duplicate snapshot ownership while retaining both models

## Objective

Reduce the amount of snapshotted memory and restore CPU pressure without removing CLIP or UNET and without forcing any model reload.

This is a cleanup/ownership step, not a model-ablation step.

## Evidence guiding this step

The isolated snapshot experiment showed:

```text
model-free restored RSS: approximately 1.39 GiB
CLIP-only restored RSS: approximately 11.3 GiB
UNET-only restored RSS: approximately 14.8 GiB
```

UNET-only repeatedly caused 32–37-core host restore bursts, while model-free did not. The production requirement nevertheless favors retaining both models because full snapshots have reached approximately 18 seconds and the model-free diagnostic path was much slower after forced cold loads.

The correct goal is therefore:

```text
retain one canonical CLIP
retain one canonical UNET
remove only proven duplicate ownership and temporary construction state
```

## Existing files

```text
comfymodal_runtime/cpu_snapshot_models.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/model_preload.py
comfymodal_runtime/contracts.py
tests/test_cpu_snapshot_models.py
tests/test_v2_cpu_snapshot_lifecycle.py
tests/test_v2_snapshot_model_bridge.py
```

## Required feature flag

Add:

```text
COMFYMODAL_V2_SNAPSHOT_TRIM=0|1
```

Default `0` until proven.

Add it to `_runtime_env()` in `modal_app.py`.

Do not reuse the model-eviction flag; trimming and eviction are different behaviors.

## Ownership census

Before cleanup, record object ownership without touching tensor contents:

```text
canonical CLIP object ID
canonical UNET ModelPatcher ID
underlying diffusion model ID
loader output object IDs
bridge preparation references
coordinator references
completed future results
snapshot loader output references
snapshot execution seed references
known ModelPatcher clone IDs
state-dict container IDs
```

Avoid walking every tensor value or reading storage pages merely to count them.

Use weak references to prove whether a candidate object remains alive after clearing a temporary owner.

## Safe cleanup candidates

Only clear an item when canonical ownership and later consumers are proven:

- Completed temporary state-dict dictionaries after weights are loaded.
- Temporary loader return tuples after canonical outputs are stored.
- Completed future/task metadata that retains a duplicate result.
- Diagnostic registries when their flags are disabled.
- Full-trace buffers when full trace is disabled.
- Residency samples when residency diagnostics are disabled.
- Temporary model-construction references.
- Proven duplicate ModelPatcher clones with identical underlying object and no unique patches.
- Stale bridge preparation from a completed snapshot build.

Do not clear:

- Canonical CLIP.
- Canonical UNET patcher.
- Underlying diffusion model.
- Tokenizer needed at runtime.
- CacheDiT state.
- ModelPatcher patches.
- Loader output required to seed the executor.
- Exact conditioning required for the active request.
- VAE.
- Any object whose later use has not been proven.

## Cleanup order

```text
1. Establish canonical ownership.
2. Record object identities and weak references.
3. Clear one category of proven temporary references.
4. Run `gc.collect()`.
5. Optionally run `malloc_trim(0)`.
6. Verify canonical weak references remain alive.
7. Verify temporary weak references die where expected.
8. Capture RSS and unique ownership metadata.
9. Create snapshot.
10. Verify first and second request identity and performance.
```

Do not touch mmap policy in the first version. File-backed tensor storage is a separate, higher-risk experiment.

## Required markers

```text
snapshot_trim_start
snapshot_trim_candidate
snapshot_trim_released
snapshot_trim_retained
snapshot_trim_summary
```

Summary:

```text
enabled
canonical_clip_alive
canonical_unet_alive
patcher_identity_unchanged
diffusion_model_identity_unchanged
temporary_objects_released
completed_futures_cleared
diagnostic_buffers_cleared
rss_before_mib
rss_after_gc_mib
rss_after_trim_mib
rss_drop_mib
```

## Files expected to change

```text
comfymodal_runtime/cpu_snapshot_models.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/model_preload.py
comfymodal_runtime/contracts.py
tools/v2_waterfall.py
tools/benchmark_v2_direct.py
tests/test_cpu_snapshot_models.py
tests/test_v2_cpu_snapshot_lifecycle.py
tests/test_v2_snapshot_model_bridge.py
tests/test_v2_snapshot_trim.py                  # new
```

## Success checklist

- [ ] Both CLIP and UNET remain in the snapshot.
- [ ] Canonical object identities remain unchanged.
- [ ] CacheDiT remains attached.
- [ ] No model file reload appears on the first request.
- [ ] No model reconstruction appears on the first request.
- [ ] No duplicate ModelPatcher appears.
- [ ] Snapshot/restored RSS decreases meaningfully or platform restore consistency improves.
- [ ] App restore does not regress.
- [ ] Pre-sampler does not regress.
- [ ] Sampler remains <= 4.0 seconds.
- [ ] Total median improves or variance meaningfully decreases.
- [ ] No second-request regression.
- [ ] No output change.
- [ ] Diagnostic and experiment code still exists and can be re-enabled.
- [ ] If cleanup forces any reload, revert that cleanup category.

Suggested commit:

```powershell
git add comfymodal_runtime/cpu_snapshot_models.py comfymodal_runtime/modal_app.py comfymodal_runtime/runtime_bootstrap.py comfymodal_runtime/model_preload.py comfymodal_runtime/contracts.py tools/v2_waterfall.py tools/benchmark_v2_direct.py tests/test_cpu_snapshot_models.py tests/test_v2_cpu_snapshot_lifecycle.py tests/test_v2_snapshot_model_bridge.py tests/test_v2_snapshot_trim.py
git commit -m "Trim duplicate V2 snapshot ownership"
```

Stop after the commit.

---

# 5. Per-step approval card

After the three runs for any step, present this concise card to the user:

```text
STEP <N> APPROVAL

Correctness
[ ] Same workflow hash
[ ] Same model identities
[ ] Same sampler/steps/settings
[ ] Same output behavior
[ ] No duplicate work
[ ] No fallback race

Timing
[ ] All three waterfalls reconcile
[ ] Median total improved
[ ] Worst-of-three acceptable
[ ] App-controlled path improved
[ ] No time shifted into restore/local/hidden future
[ ] Sampler <= 4.0s

Identity and safety
[ ] Three fresh remote instances
[ ] Expected feature marker active
[ ] No unexpected diagnostic/experiment marker
[ ] No OOM/deadlock/live background task
[ ] min_containers=0 and scaledown_window=4

Decision
[ ] APPROVE AND COMMIT
[ ] REJECT — FIX SAME STEP
[ ] REVERT STEP
```

Do not infer approval. The user must explicitly choose.

---

# 6. Required implementation report after each selected step

Before asking the user to deploy, return:

```text
Step implemented:
Starting commit:
Changed files:
Functions/classes changed:
New flags:
Default behavior:
Fallback behavior:
Local checks run:
Local check results:
Expected deploy markers:
Expected waterfall change:
Known risks:
Paid Modal actions performed: NONE
Commit created: NO
Next action: user deploys and runs three cold requests
```

After the user provides the three runs, analyze:

- Each waterfall.
- Median and worst-of-three.
- App-controlled versus platform time.
- Stage deltas versus the immediately previous committed step.
- Correctness markers.
- Whether time moved.
- Whether the checklist passes.

Only then create the step commit if explicitly approved.

---

# 7. Sub-15 target waterfall

The final intended production range is:

```text
Local plan + cached Modal handle          0.05–0.10s
Modal scheduling / host restore           4.0–5.5s typical
Application restore                       1.3–1.8s
Restore-to-method and method setup         0.4–0.8s
Cold pre-sampler                           1.7–2.3s
Sampler                                    3.6–3.9s
VAE + output                               0.5–0.8s
Return/finalization                        0.3–0.6s
---------------------------------------------------
Expected typical total                    11.9–15.8s
Desired median                            <= 13.5s
Desired worst of three                    < 15.0s
```

The largest measured controllable opportunity remains cold-first-request parity. The warm-equivalent request already demonstrated that much of the cold pre-sampler work can disappear. Steps 3, 6, and 7 are the main path to sub-15. Steps 4, 5, 8, 9, and 10 protect or compound that gain.

Because Modal scheduling is external, severe platform outliers may still occur. They must remain visible and separate. The application target is to make the controllable path fast enough that ordinary platform variation still leaves most true-cold runs below 15 seconds.

---

# 8. Final reminder

This file must never be treated as permission to run the entire roadmap.

For every step:

```text
Implement one
Stop
User deploys
User runs three
Review
Approve
Commit one
Stop
```

No automatic chain execution.
