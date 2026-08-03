# Phase 1A — Safely Overlap Exact UNET GPU Activation with CLIP Encoding
Save this prompt in an .md file in a prompts folder before beginning the task. Do not paraphrase. I saved it for you this time.
prompts/phase_1a_unet_overlap_candidate.md

Use Subagent driven implementation and programming.

Implement and test **one conservative UNET-activation candidate only**.

Do not perform a scheduling matrix. Do not optimize CLIP, sampling, VAE, output, local submission, page readiness, or snapshot ownership in this task.

The candidate is:

```text
Start the exact retained UNET’s normal ComfyUI GPU activation once,
at the beginning of the real execution-prefill CLIP encode.

Allow CLIP encode and UNET activation to overlap when safe.

At sampler demand, join the same activation future instead of beginning
a second physical UNET transfer.
```

This is a feature-gated shadow deployment experiment. It must not silently change the normal production default.

---

# Starting point

Repository:

```text
Parlaxz/comfyui-modal
```

Required ancestor:

```text
7b31ccb53a7a57bf940731caead3fec76fe40bd8
```

The local repository may contain newer committed or uncommitted Phase 0 corrections that are not on GitHub yet.

Do not reset to 7b31ccb.

Do not discard, restore, stash, clean, overwrite, or recommit pre-existing work.

Run:

```powershell
git status --short
git rev-parse HEAD
git log -5 --oneline
git merge-base --is-ancestor 7b31ccb53a7a57bf940731caead3fec76fe40bd8 HEAD
git diff --stat
git diff --check
```

Required:

```text
7b31ccb53a7a57bf940731caead3fec76fe40bd8 is an ancestor of the current tree
```

If it is not an ancestor, stop without modifying anything.

Save the pre-existing state:

```powershell
git diff --binary > $env:TEMP\phase1a_before.patch
git status --porcelain=v1 -uall > $env:TEMP\phase1a_before_status.txt
```

Treat all existing Phase 0 changes as baseline work.

Do not include unrelated pre-existing changes in a Phase 1 commit.

Do not commit or push in this task.

---

# Measured baseline

Use this genuine true-cold production-profile run as the reference:

```text
Request:
v2-benchmark-0-70f7d4184612

Fresh:
YES

Command to response:
18.766s

Derived Modal scheduling/host interval:
approximately 4.967s

Application restore:
0.773s

PromptExecutor/cache:
0.291s

First node to CLIP:
0.279s

CLIP to sampler node:
3.499s

Actual prefill CLIP encode:
4.127s

Sampler node to sampling:
2.171s

Exact UNET GPU activation:
2.104s

UNET GPU allocation:
12,416,794,112 bytes

Sampling:
4.927s

Pre-sampler total:
6.459s
```

Identity evidence:

```text
snapshot UNET object:
47580785541648

bridge UNET object:
47580785541648

snapshot and bridge underlying diffusion object:
47580847504272

sampler patcher object:
47580988761936

sampler underlying diffusion object:
47580847504272

identity result:
pass
```

The candidate’s maximum immediate opportunity is to hide most of the approximately `2.104s` UNET activation beneath the approximately `3.4s` graph-visible CLIP interval.

Do not claim a two-second gain merely because activation started earlier. Only non-overlapping command-to-response and pre-sampler timing count.

---

# Immutable constraints

Preserve:

```text
min_containers=0
scaledown_window=4
RTX PRO 6000
production workflow and source workflow
production profile
CPU memory snapshots
canonical retained CLIP
canonical retained UNET
native BF16 UNET
BF16 compute
manual_cast_dtype absent/None
CacheDiT behavior
SageAttention behavior
RES4LYF behavior
eight sampler steps
same sampler
same scheduler
same CFG
same denoise
same seed
same image dimensions
same output and metadata behavior
```

Never use:

```text
GPU memory snapshots
warm containers
keep-warm traffic
scheduled warmups
longer scaledown windows
dummy generations
model-file reloads
persistent conditioning caches
page pre-touching
madvise
Torch thread experiments
VAE snapshotting
new sampler warmups
torch.compile
CUDA graphs
a second model-loading framework
a second model/GPU mutation lock
unbounded workers
```

Do not change V1.

---

# Paid-run limit

Normal budget:

```text
one candidate true-cold request
```

One replacement request is allowed only when the first request is invalid because of:

```text
Fresh: NO
wrong app/class/image
wrong effective activation mode
missing required markers
request failure
instrumentation failure
```

Hard maximum:

```text
two paid image generations
```

Do not run a new baseline request.

Do not run an immediate warm request.

Do not run a second scheduling candidate.

Do not run three-run validation.

The user will review the candidate logs before authorizing further runs.

---

# Required subagents

Use bounded roles:

```text
Explorer:
Trace the exact current UNET object lifecycle, existing coordinator,
execution-prefill encode callback, model mutation lane, load_models_gpu
wrapper, sampler wrapper, and request cleanup.

Fixer:
Implement the one feature-gated clip_encode_start activation path.

Reviewer:
Verify exact identity, one physical transfer, existing-lane use,
failure fallback, no CLIP offload, no request-owned future leak,
and complete production-default isolation.
```

Only the Fixer may write shared runtime files.

There must be no concurrent writers to:

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/runtime_executor.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/unet_forward_probe.py
```

---

# Part 1 — Trace the current live path before editing

Read the current versions of:

```text
comfymodal_runtime/model_preload.py
comfymodal_runtime/runtime_executor.py
comfymodal_runtime/runtime_bootstrap.py
comfymodal_runtime/modal_app.py
comfymodal_runtime/unet_forward_probe.py
comfymodal_runtime/cpu_snapshot_models.py
comfymodal_runtime/contracts.py
comfymodal_runtime/trace.py
canonical_execution.py
production_workflow.py
comfyapp.py
```

Read the installed ComfyUI implementation currently invoked for:

```text
comfy.model_management.load_models_gpu
LoadedModel.model_load
ModelPatcher.load
ModelPatcher.load_list
model patch application
model cache insertion
model offload/eviction
CLIP GPU readiness
CLIP encode
```

Read the installed custom-node implementation for:

```text
ClownsharKSampler_Beta
CacheDiT_Model_Optimizer
PathchSageAttentionKJ
ModelSamplingAuraFlow
RES4LYF
FeatureInjLatent
```

Identify and document internally:

```text
where V2LoaderBridge.prepare creates the retained UNET future
what that existing UNET future actually completes
where execution prefill waits for CLIP
where the real prefill CLIP encode callback begins
where the sampler first invokes load_models_gpu
where the existing model/GPU mutation lane is acquired
whether load_models_gpu would offload the currently encoding CLIP
how to keep the exact CLIP patcher resident during the UNET load
how the sampler patcher relates to the retained snapshot patcher
where request-owned coordinator futures are closed or joined
```

Do not assume the existing `unet_future` means the UNET is GPU-ready. The cold log proves the model-sized GPU allocation still occurs at sampler demand.

Do not implement until those ownership and call relationships are confirmed in code.

---

# Part 2 — Add one explicit activation mode

Add one narrowly scoped environment control:

```text
COMFYMODAL_V2_UNET_ACTIVATION_MODE
```

Allowed values:

```text
late
clip_encode_start
```

Default:

```text
late
```

Semantics:

## `late`

Preserve current production behavior exactly.

Required:

```text
no early activation future
no additional worker
no early load_models_gpu call
no extra model traversal
no new graph wait
no measurable default-path overhead
```

## `clip_encode_start`

Schedule the exact retained UNET’s normal GPU activation once, immediately before the real execution-prefill CLIP transformer encode callback begins.

Do not trigger from:

```text
snapshot restore
generic request entry
graph CLIPTextEncode fallback
tokenization
certificate setup
PromptExecutor construction
a dummy encode
```

The trigger must be the real prefill encode that produced:

```text
clip_encode_prefill_calls=1
clip_encode_graph_calls=0
```

The mode must be parsed and logged once with the effective value.

Invalid values must fail safely to:

```text
late
```

---

# Part 3 — Extend the existing coordinator rather than creating a new subsystem

Use:

```text
ModelPreloadCoordinator
V2LoaderBridge
the current preparation state
the current worker pool
the current model/GPU mutation lane
the current exact retained objects
```

Do not create:

```text
a second ThreadPoolExecutor
a raw detached thread
a second semaphore or GPU lock
a second UNET registry
a new global model cache
```

Add request-scoped state equivalent to:

```text
unet_activation_future
unet_activation_key
unet_activation_trigger
unet_activation_owner
unet_activation_terminal_state
unet_activation_error
```

The exact key must include enough identity to prevent cross-request or stale reuse:

```text
underlying diffusion-model identity
retained UNET patcher identity
workflow hash
custom-node generation
deployment combined hash
weight dtype
compute dtype
device
activation mode
```

The future is request-scoped.

Do not persist it across restored containers.

Do not reuse a completed activation result after identity changes.

---

# Part 4 — Trigger at the real prefill encode boundary

The existing CLIP instrumentation already wraps the actual encode callback.

Use that established callback boundary rather than adding a second CLIP wrapper.

Immediately before the actual prefill encode callback:

1. Confirm the caller is the execution-prefill path.
2. Confirm activation mode is `clip_encode_start`.
3. Confirm CPU snapshot mode is active.
4. Confirm the exact snapshot and bridge UNET identities match.
5. Confirm an exact UNET object is available.
6. Confirm no activation future already exists for this exact request/key.
7. Confirm CUDA is valid.
8. Confirm the request has enough VRAM to retain CLIP and load the UNET.
9. Schedule one activation future.
10. Begin the real CLIP encode without waiting for the activation future.

The trigger must be idempotent.

If both positive and negative encodes are present, only the first eligible real encode may schedule the activation.

Subsequent encode calls must attach to or observe the existing future without rescheduling.

---

# Part 5 — Protect the active CLIP model

The UNET activation must not evict or invalidate the CLIP model while the CLIP transformer encode is running.

Before implementing, trace the actual ComfyUI model-manager API and exact CLIP object structure.

When invoking the original model-manager path:

* Retain the exact currently encoding CLIP model or patcher in the required-loaded set when the real API supports it.
* Load the exact retained UNET through the original ComfyUI `load_models_gpu`/`LoadedModel.model_load` path.
* Do not reproduce the transfer manually.
* Do not directly mutate ComfyUI’s loaded-model list.
* Do not suppress legitimate OOM/offload behavior by monkey-patching global memory thresholds.
* Do not assume 97 GB total VRAM means all memory is available; inspect current free/required memory through the real model-manager API.
* Use a bounded safety margin.
* If safe concurrent residency cannot be established, fail open to the late path.

The activation must not begin when ComfyUI would need to offload the active CLIP to satisfy the load.

Emit the exact skip reason.

---

# Part 6 — Use the existing mutation lane

The activation callback must acquire the current coordinator-owned model/GPU mutation lane before entering the shared ComfyUI model-manager mutation path.

Do not hold the lane while:

```text
waiting in the worker queue
validating request identity
tokenizing
running CLIP transformer compute
waiting for the sampler
formatting logs
```

The lane should cover only the shared mutation-sensitive portion equivalent to:

```text
ComfyUI model-cache inspection
model placement/offload decision
UNET GPU materialization
cache publication
terminal model-state validation
```

The CLIP encode itself does not need to hold the mutation lane once its model is fully ready, unless the current code proves it already requires it.

Do not add broad serialization that prevents any overlap.

---

# Part 7 — Perform one physical transfer

The early activation callback must use the same exact retained underlying diffusion model later consumed by the sampler.

Required identity chain:

```text
snapshot underlying diffusion object
=
bridge underlying diffusion object
=
early activation underlying diffusion object
=
sampler underlying diffusion object
=
first UNET forward underlying diffusion object
```

The patcher wrapper may differ after:

```text
ModelSamplingAuraFlow
CacheDiT
SageAttention
other graph patch nodes
```

That is acceptable only when the same underlying diffusion model remains proven.

Do not pre-apply request-dependent sampler patches during early activation.

The early operation is allowed to make the base retained weights GPU-resident. Later graph patch nodes must retain their existing semantics.

Required physical-load rule:

```text
one model-sized UNET allocation/transfer per request
```

A later `load_models_gpu` invocation may still occur through the unchanged sampler path, but it must be a fast already-resident/cache-validation path with:

```text
no second approximately 12.4GB allocation
no second model-sized CPU-to-GPU transfer
```

---

# Part 8 — Join the same future at graph/sampler demand

At the first sampler-side demand for the exact registered UNET:

1. Find the request’s exact activation future.
2. If it is pending, join it outside the mutation lane.
3. If it completed successfully, validate:

   * underlying diffusion identity;
   * all expected parameters are GPU-resident;
   * ComfyUI model-cache membership;
   * expected dtype;
   * expected device.
4. Continue through the original sampler path.
5. Allow the original later `load_models_gpu` call to perform only its normal fast validation/cache path.
6. If the future failed, was skipped, or produced an invalid state, execute the original late activation path exactly once.

Do not:

```text
wait while holding the mutation lane
launch a second fallback before the first future is terminal
allow late future success to overwrite a fallback result
swallow an activation exception and leave partial cache state
```

Only one caller may elect fallback.

---

# Part 9 — Failure and cancellation behavior

Fail open to the existing late path for:

```text
activation mode late
CPU snapshot inactive
identity mismatch
missing retained UNET
missing active CLIP identity
insufficient safe VRAM
activation scheduling failure
worker-pool rejection
ComfyUI model-manager exception
CUDA exception
future cancellation
request cancellation
terminal residency validation failure
```

Rules:

```text
failure becomes terminal before fallback
one fallback caller
no duplicate model-sized transfer
no late cache publication after fallback
request cancellation cannot leave model mutation running unowned
response cannot return with a request-owned activation future pending
```

Do not turn a candidate optimization failure into an image-generation failure unless the original late path also fails.

---

# Part 10 — Required structured markers

Add concise markers equivalent to:

```text
unet_early_activation_mode
unet_early_activation_eligible
unet_early_activation_scheduled
unet_early_activation_worker_start
unet_early_activation_lane_wait_start
unet_early_activation_lane_acquired
unet_early_activation_load_start
unet_early_activation_load_end
unet_early_activation_completed
unet_early_activation_failed
unet_early_activation_skipped
unet_early_activation_graph_demand
unet_early_activation_graph_join_start
unet_early_activation_graph_join_end
unet_early_activation_consumed
unet_early_activation_terminal
```

Every marker must include, when applicable:

```text
request_id
restored_instance_id
activation mode
trigger=clip_encode_start
activation key hash
retained patcher object ID
underlying diffusion object ID
sampler patcher object ID
CLIP object/patcher ID
schedule timestamp
worker-start timestamp
CLIP encode start timestamp
CLIP encode end timestamp
lane-wait duration
load start/end
load wall duration
process CPU duration
GPU allocated before/after
GPU allocation delta
free VRAM before
required VRAM estimate
safety margin
graph demand timestamp
graph wait duration
completion status
fallback reason
physical model-sized transfer count
```

At request completion derive and emit:

```text
clip_interval_ms
unet_activation_interval_ms
actual_clip_unet_overlap_ms
sequential_equivalent_ms
combined_interval_ms
overlap_efficiency
clip_slowdown_against_reference_ms
graph_visible_unet_wait_ms
```

Do not hardcode a claimed saving.

---

# Part 11 — Keep the existing waterfall truthful

Add the early activation as nested detail, not as another top-level additive stage when it overlaps CLIP.

Top-level rows must remain non-overlapping.

Required top-level behavior:

```text
CLIP to sampler node reflects actual graph-visible interval
sampler node to sampling reflects actual graph-visible wait
overlapped activation is excluded from top-level addition
total command-to-response remains authoritative
```

Populate the known Modal platform interval instead of leaving it in residual when the Phase 0 waterfall fix is present.

Required reconciliation:

```text
absolute error <= max(50ms, 0.5% of command-to-response)
```

Do not count overlapping CLIP and UNET durations twice.

---

# Part 12 — Focused tests

Do not run the entire test suite.

Add or extend focused tests covering:

```text
default late mode performs no early work
invalid mode falls back to late
clip_encode_start schedules exactly once
second encode does not schedule a second activation
graph demand joins the same future
graph arrives before activation completes
graph arrives after activation completes
activation failure elects one late fallback
late success cannot overwrite fallback
request cancellation reaches a terminal state
no request-owned future survives response
existing mutation lane has at most one owner
no new lock or executor is created
same underlying diffusion object through all stages
later sampler patcher may differ while diffusion identity remains exact
one model-sized physical transfer
second load_models_gpu call has zero model-sized allocation
active CLIP remains resident during activation
insufficient safe VRAM skips early activation
page-readiness mode remains off
output and metadata remain equivalent
waterfall excludes overlapping activation from additive totals
```

Run only the relevant focused tests, including current coverage around:

```text
tests/test_model_preload_prefill_overlap.py
tests/test_v2_preload_bridge.py
tests/test_clip_prefill_attribution.py
tests/test_v2_activation_diagnostics.py
tests/test_v2_cpu_snapshot_lifecycle.py
tests/test_v2_sampler_boundary.py
tests/test_v2_sampler_wrapper_integration.py
tests/test_v2_unet_forward_probe.py
tests/test_v2_pre_sampler_attribution.py
tests/test_v2_waterfall.py
```

Add one new focused file such as:

```text
tests/test_v2_unet_early_activation.py
```

Run:

```powershell
python -m pytest -q `
  tests/test_v2_unet_early_activation.py `
  tests/test_model_preload_prefill_overlap.py `
  tests/test_v2_preload_bridge.py `
  tests/test_clip_prefill_attribution.py `
  tests/test_v2_activation_diagnostics.py `
  tests/test_v2_cpu_snapshot_lifecycle.py `
  tests/test_v2_sampler_boundary.py `
  tests/test_v2_sampler_wrapper_integration.py `
  tests/test_v2_unet_forward_probe.py `
  tests/test_v2_pre_sampler_attribution.py `
  tests/test_v2_waterfall.py
```

Compile changed Python files and run:

```powershell
git diff --check
```

Do not deploy while focused tests fail.

---

# Part 13 — Read-only review before deployment

The Reviewer must inspect the final diff and answer:

```text
Does late mode preserve current behavior?
Is there exactly one early activation future?
Is there exactly one worker pool?
Is there exactly one mutation lane?
Can the active CLIP be offloaded during encode?
Can two model-sized UNET transfers occur?
Can graph fallback race the activation future?
Can the request return while activation is pending?
Can the candidate pre-apply request-dependent model patches?
Can output behavior change?
Is any Phase 1 candidate active without the explicit flag?
```

Deployment is allowed only when the answers are:

```text
late behavior preserved: yes
one future/pool/lane: yes
CLIP protected: yes
duplicate transfer possible: no
fallback race possible: no
future leak possible: no
request-dependent patches pre-applied: no
output change expected: no
candidate default-active: no
```

---

# Part 14 — Shadow deployment

Deploy only to the same production-profile shadow app used in Phase 0:

```text
App:
stable-modal-comfy-v2-shadow

Class:
ModalRuntimeEntrypointV2

Environment:
main
```

Use only the repository-supported batch deployment path.

Never call `modal deploy` directly.

Set the candidate mode before deployment so it is captured by the actual remote image/runtime:

```powershell
$env:COMFYMODAL_V2_ENV_PROFILE = "production"
$env:COMFYMODAL_V2_ENVIRONMENT = "main"
$env:COMFYMODAL_V2_UNET_ACTIVATION_MODE = "clip_encode_start"
$env:COMFYMODAL_V2_PAGE_READINESS_MODE = "off"
$env:COMFYMODAL_V2_DEEP_MODEL_DIAG = "0"
$env:COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET = "0"
$env:COMFYMODAL_DEPLOY_ONLY = "1"

cmd /c ".\deploy_and_run_v2_single.bat"
$deployExit = $LASTEXITCODE

Remove-Item Env:COMFYMODAL_DEPLOY_ONLY -ErrorAction SilentlyContinue

if ($deployExit -ne 0) {
    throw "UNET early-activation shadow deployment failed with exit code $deployExit"
}
```

If the existing Phase 0 shadow-app selector requires another established environment variable, preserve and use that existing selector. Do not deploy over the main production app.

Before generating an image, require deployment logs showing:

```text
app=stable-modal-comfy-v2-shadow
class=ModalRuntimeEntrypointV2
environment=main
profile=production
GPU=RTX PRO 6000
min_containers=0
scaledown_window=4
GPU snapshot disabled
CPU model snapshot enabled
unet_activation_mode=clip_encode_start
page_readiness_mode=off
deep_model_diag=0
```

Stop without a paid run if any value is wrong.

---

# Part 15 — One true-cold candidate request

Wait 60 seconds after deployment confirmation so no previous shadow request container remains.

Run one request using the exact same workflow, prompt, seed, dimensions, sampler, scheduler, steps, CFG, and denoise as the genuine cold reference.

```powershell
Start-Sleep -Seconds 60

$env:COMFYMODAL_V2_ENV_PROFILE = "production"
$env:COMFYMODAL_V2_ENVIRONMENT = "main"
$env:COMFYMODAL_V2_UNET_ACTIVATION_MODE = "clip_encode_start"
$env:COMFYMODAL_V2_PAGE_READINESS_MODE = "off"
$env:COMFYMODAL_V2_DEEP_MODEL_DIAG = "0"
$env:V2_BENCHMARK_RUNS = "1"

cmd /c ".\run_v2_single.bat"
$runExit = $LASTEXITCODE

Remove-Item Env:V2_BENCHMARK_RUNS -ErrorAction SilentlyContinue

if ($runExit -ne 0) {
    throw "UNET early-activation candidate request failed with exit code $runExit"
}
```

The candidate is valid only when logs prove:

```text
Fresh: YES
restore_count=1
request_count=1
effective mode=clip_encode_start
one prefill CLIP encode
zero graph duplicate encodes
one model-sized UNET transfer
same underlying diffusion identity
eight sampler steps
successful output
```

If the request reports `Fresh: NO`, preserve its artifact, wait 60 seconds, and run one replacement.

No other replacement reason is allowed beyond the invalid conditions stated earlier.

Hard stop after two paid requests.

---

# Part 16 — Candidate data gate

Do not automatically implement another scheduling mode.

Do not automatically rerun three cold requests.

Report the measured candidate against the fixed reference:

| Metric                     | Reference |
| -------------------------- | --------: |
| Command to response        | `18.766s` |
| Derived platform interval  |  `4.967s` |
| Application restore        |  `0.773s` |
| PromptExecutor/cache       |  `0.291s` |
| CLIP to sampler            |  `3.499s` |
| Actual prefill CLIP encode |  `4.127s` |
| Sampler node to sampling   |  `2.171s` |
| UNET activation            |  `2.104s` |
| Sampling                   |  `4.927s` |
| Pre-sampler total          |  `6.459s` |

A promising result should satisfy all correctness gates and approximately:

```text
actual CLIP/UNET overlap >=1.5s
sampler_node_to_sampling <=0.70s
pre_sampler_total <=5.10s
CLIP-to-sampler regression <=0.25s
sampling regression <=0.10s
application-restore regression <=0.10s
one model-sized UNET allocation
no output mismatch
no request-owned future after response
```

Preferred result:

```text
sampler_node_to_sampling <=0.40s
pre_sampler_total <=4.70s
app-controlled saving >=1.5s
```

Do not classify the candidate solely by total command-to-response because Modal platform placement varies.

Primary evaluation order:

```text
correctness
duplicate-transfer absence
CLIP slowdown
graph-visible UNET wait
non-overlapping pre-sampler improvement
sampling stability
application restore
total app-controlled path
command-to-response
```

If the candidate misses the numerical target, leave the feature flag and implementation uncommitted for review. Do not try request-entry activation or a custom CUDA stream automatically.

---

# Part 17 — Output equivalence

Compare the candidate output against the existing genuine cold baseline artifact when its exact output hash is locally available.

Require:

```text
same workflow
same prompt
same seed
same dimensions
same sampler
same scheduler
same steps
same CFG
same denoise
same output count
same image hash where deterministic binary equivalence is expected
same metadata
```

If the old output artifact is unavailable, record that exact limitation.

Do not spend another image merely to create a comparison baseline.

---

# Part 18 — Stop without commit

After the candidate request:

```powershell
git status --short
git diff --stat
git diff --check
```

Do not commit.

Do not push.

Do not merge.

Do not begin:

```text
request-entry activation
another activation boundary
custom page readiness
CLIP optimization
sampler optimization
VAE optimization
local-handle optimization
three-run validation
```

Preserve:

```text
working-tree implementation diff
focused test results
deployment identity
candidate run artifact
complete Modal logs
```

The user will provide the candidate logs for external analysis before the code is accepted, revised, or discarded.

---

# Final response format

Return only:

```text
PHASE 1A UNET OVERLAP CANDIDATE COMPLETE

Starting HEAD:
Required ancestor present: yes
Commit created: no
Push performed: no
V1 modified: no

Candidate:
- app:
- image:
- environment:
- profile:
- activation mode:
- trigger:
- page readiness:
- min_containers:
- scaledown_window:
- GPU snapshots:

Paid generations:
- used:
- valid candidate run:
- replacement reason, if any:

Identity:
- snapshot patcher:
- bridge patcher:
- activation patcher:
- sampler patcher:
- underlying diffusion identity match:
- first-forward diffusion identity match:

Single flight:
- activation futures created:
- model-sized UNET transfers:
- fallback transfers:
- mutation-lane maximum owners:
- request-owned future at response:

Timing:
| Metric | Reference | Candidate | Delta |
|---|---:|---:|---:|
| Command to response | 18.766s | | |
| Platform | 4.967s | | |
| Restore | 0.773s | | |
| CLIP to sampler | 3.499s | | |
| Actual CLIP encode | 4.127s | | |
| UNET activation | 2.104s | | |
| CLIP/UNET overlap | 0.000s | | |
| Sampler node to sampling | 2.171s | | |
| Pre-sampler total | 6.459s | | |
| Sampling | 4.927s | | |
| App-controlled total | | | |

Correctness:
- one CLIP prefill encode:
- zero graph duplicate encodes:
- one model-sized UNET transfer:
- eight sampler steps:
- output success:
- output equivalence:
- CLIP remained resident:
- late fallback preserved:
- waterfall reconciled:

Focused tests:
<commands and results>

Changed files:
<list>

Candidate artifact:
<path>

STOPPED WITHOUT COMMIT OR ADDITIONAL RUNS
```
