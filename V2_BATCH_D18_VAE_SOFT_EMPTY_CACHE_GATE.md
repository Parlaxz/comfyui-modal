# V2 Batch D18 - VAE Soft-Empty-Cache Gate Decomposition

Date: 2026-08-16
Scope: initial local source/artifact audit, bounded remote decomposition, and
low-overhead telemetry.
Initial local phase: no Modal deploy, no Modal request, no commit.

## Verdict

`D18_REMOTE_DECOMPOSITION_COMPLETE`

The post-sampling model is the VAE, not CLIP. D17's old `clip_cold_*` names are
shared model-management labels and are retained only for trace compatibility.
The current artifacts establish a VAE `load_models_gpu` memory-management gate,
but do not establish which of `torch.cuda.synchronize`,
`torch.cuda.empty_cache`, or `torch.cuda.ipc_collect` consumes the approximately
0.9-1.0 second wall. D18 therefore implements decomposition telemetry only.

## Source Audit

### Sampling to VAE order

Pinned source order is:

1. `comfy.sample.sample` calls `KSampler.sample` and then performs the final
   intermediate-device/dtype conversion (`comfy/sample.py:71-76`).
2. `comfy.samplers` performs sampler GPU work and waits for any configured
   multigpu worker results (`comfy/samplers.py:546-561`). The source contains
   no device-wide synchronize at sampler completion. Its non-NVIDIA note at
   `comfy/samplers.py:526-531` explicitly discusses a possible synchronize,
   but does not execute one on the current NVIDIA path.
3. The V2 sampler wrapper returns from the sampler executor and enters its
   `finally` path (`comfymodal_runtime/runtime_executor.py:4865-4867`). It emits
   `sampling_end` first (`:4883-4892`), then releases the sampler mutation lane
   and submits the VAE activation (`:4962-4981`).
4. The VAE worker runs after the boundary, waits for the CPU prefetch if any,
   and calls native `_mm_load_models_gpu([_patcher])`
   (`comfymodal_runtime/model_preload.py:19721-19756`). The worker is on a
   coordinator thread, but the audited `sampling_end` path does not create or
   use an alternate CUDA stream. The experimental first-step path's side stream
   is not part of the three D11 runs.
5. The graph remains in normal order. `VAEDecode` calls `vae.decode`
   (`nodes.py:310-318`), and native `VAE.decode` calls
   `load_models_gpu([self.patcher], memory_required=memory_used)` before the
   decode kernel (`comfy/sd.py:1045-1071`).

`SAMPLER_ALREADY_DEVICE_SYNCHRONIZED_AT_SAMPLING_END = NO` for an explicit
device-wide synchronize. Host return plus default-stream ordering is not proof
that all device work on every stream is complete. The later model-management
barrier is the first proven device-wide completion boundary on this path.

`SAMPLER_ALREADY_DEVICE_SYNCHRONIZED_AT_SAMPLING_END` does not mean sampler
work is unordered: normal CUDA operations retain stream ordering, and the
sampler waits for its worker threads. It means there is no source-proven
`torch.cuda.synchronize()`, CUDA event wait, or equivalent device-wide completion
contract at the emitted event.

### Why soft_empty_cache synchronizes

Pinned ComfyUI `load_models_gpu` calls `free_memory` before patcher loading and
may call it a second time if the free-memory check is below its minimum
requirement (`comfy/model_management.py:843-940`). `free_memory`:

- unloads eligible models when `memory_to_free > 0`;
- calls `soft_empty_cache` after an unload (`:834-835`);
- otherwise, when not in `HIGH_VRAM`, calls it if the Torch allocator's free
  portion is more than 25% of total free memory (`:836-840`).

CUDA `soft_empty_cache` unconditionally executes, in this exact order:

```text
torch.cuda.synchronize()
torch.cuda.empty_cache()
torch.cuda.ipc_collect()
```

at `comfy/model_management.py:1944-1960`. The source provides no reason
specific to VAE, no caller option for nonblocking cleanup, and no cache-only
variant. Its defensible purposes are completion before allocator/model cleanup,
global allocator policy, and conservative IPC-handle reclamation. The source
does not isolate which purpose dominates this wall.

The `force` parameter exists in the pinned signature but is unused by the CUDA
body. No lighter force/unload/nonblocking option was found.

### Redundancy decision

The first VAE call is not proven redundant in this lifecycle. `sampling_end` is
a host-side trace boundary with no explicit sampler device synchronize, and the
VAE worker is allowed to start native model management immediately after the
mutation-lane release. Skipping the global sync, replacing it with an event
wait, skipping allocator reclamation, or skipping IPC collection would each
change a generic ComfyUI contract without a local completion/capability proof.

```text
SYNC_REDUNDANT = UNKNOWN
EMPTY_CACHE_REDUNDANT = UNKNOWN
IPC_COLLECT_REDUNDANT = UNKNOWN
```

## D11 Headroom Audit

The three saved D11 traces show the same VAE facts:

- VAE model: `comfy.ldm.models.autoencoder.AutoencodingEngine`.
- VAE patcher count: one; CLIP patcher count: zero.
- VAE model bytes transferred on the cold activation: `167,639,366` bytes
  (approximately 159.9 MiB in binary units, reported as approximately 167.6
  MiB by the existing artifact accounting).
- VAE `free_memory` requirement in the long activation call:
  `1,462,827,161.8` bytes.
- Native decode demand in the subsequent graph load:
  `9,099,509,760` bytes.
- UNET resident model bytes: `12,309,817,472` bytes in all three
  `unet_fastsafetensors_pipeline` events.
- CLIP was CPU/offloaded at its final forensic detach state in all three runs,
  with `8,044,936,196` loaded model bytes and `current_device=cpu`.
- No VAE-time `clip_cold_unload` event was observed. The old trace therefore
  shows `0` observed model evictions in this window, although it cannot provide
  the authoritative unload count that D18 telemetry now adds.
- The post-sampling graph load diagnostic immediately before the already
  resident VAE decode check reported `allocated=20,599,291,392` bytes and
  `reserved=20,604,518,400` bytes. The GPU is reported as 97,250 MiB. This is
  ample physical headroom for the VAE requirement, but it is not the same as
  proving that the Torch allocator's free portion passed ComfyUI's reclamation
  threshold.
- Allocated/reserved values immediately before `sampling_end` were not emitted
  in D11. The existing post-sampling values must not be relabeled as a
  sampling-end snapshot.

Conclusion: the expensive cleanup occurs despite enough physical GPU capacity
for the observed VAE transfer. Existing source behavior can still reclaim
allocator blocks defensively based on `get_free_memory(..., torch_free_too=True)`
and `vram_state`, so headroom alone does not prove `empty_cache` or any other
operation removable.

## CUDA IPC Audit

The pinned custom-node and ComfyUI source contains no CUDA tensor
`multiprocessing`, `torch.multiprocessing`, shared CUDA storage, CUDA IPC owner,
or subprocess CUDA-tensor handoff on this request path. The local
`persistent_ipc` references are Modal/local-handle transport terminology, not
CUDA allocator IPC. The only CUDA IPC call found is the unconditional
`torch.cuda.ipc_collect()` in pinned ComfyUI `soft_empty_cache`.

This classifies IPC collection as conservative for this runtime path, not as
provably removable globally. PyTorch/runtime allocator handles or an external
caller are not ruled out by the custom-node source. No request-scoped IPC skip
was implemented.

## Implemented Telemetry

`comfymodal_runtime/clip_cold_path_forensics.py` now retains the old events and
adds authoritative neutral events:

```text
model_management_soft_empty_cache_start
model_management_cuda_sync_end
model_management_empty_cache_end
model_management_ipc_collect_end
model_management_soft_empty_cache_end
```

The implementation wraps only the existing CUDA operations. It adds no CUDA
operation or synchronization and does not alter native call order. It records
wall time for:

```text
pre_sync_ms
cuda_synchronize_ms
empty_cache_ms
ipc_collect_ms
post_cleanup_ms
soft_empty_cache_total_ms
```

Each neutral event carries the requested generic context where available:

```text
reason
caller
model_count
model_classes
required_memory
free_memory_before
allocated_before
reserved_before
allocated_after
reserved_after
models_unloaded_count
bytes_unloaded
single_use
request_id
```

When another wrapper owns `load_models_gpu`, the soft-cache wrapper performs a
single stack-local generic ComfyUI frame inspection to recover `free_memory`,
`load_models_gpu`, model, and requirement context. Missing state is emitted as
`null`, never guessed. The telemetry is enabled through the existing
`COMFYMODAL_V2_CLIP_COLD_FORENSICS` observability gate. The three low-level
operation wrappers are installed under that main gate so decomposition does not
depend on the legacy cumulative sync-accounting subflag; the legacy total sync
counter remains subflag-controlled.

## Optimization Decision

No optimization was implemented. Default native ComfyUI behavior is preserved;
there is no sampling overlap, no VAE decode change, no GPU-model branch, no
single-use special case, and no D15 interaction.

The next authorized remote decomposition should determine whether the long
wall is primarily synchronize, empty-cache, IPC collection, or distributed.
Only after that result can a fail-closed, generic, request-scoped optimization
be evaluated.

## Static Timing Scenarios

These are arithmetic scenarios, not claims about current composition:

| Observed suboperation | Arithmetic if safely removed | Likely next strategy |
| --- | ---: | --- |
| `synchronize ~= 850 ms` | theoretical tail `1631 - 850 = 781 ms` | Prove sampler/device completion first; otherwise retain native sync. |
| `empty_cache ~= 850 ms` | theoretical tail `~=781 ms` | Test allocator/headroom predicate and generic unload state; do not skip from physical headroom alone. |
| `ipc_collect ~= 850 ms` | theoretical tail `~=781 ms` | Require a runtime capability proof that no CUDA IPC ownership can exist; no global removal. |
| Distributed cost | no single saving can be claimed | Use the five neutral events and preserve native path until each boundary is understood. |

The existing `~962 ms` gate and `~1631 ms` tail are unchanged. The
provably-removable amount is zero until a remote decomposition plus lifecycle
proof identifies a safe operation.

## Verification

- `tests/test_v2_clip_cold_forensics.py`: **27 passed**.
- Combined forensics plus D15 regression command: **34 passed**.
- Local decomposition fake: `synchronize=100 ms`, `empty_cache=200 ms`,
  `ipc_collect=300 ms`; separate timings and total were asserted.
- Operation exception test: native exception and control flow preserved;
  operation and total events report `status=error`.
- Call-order test: synchronize, empty-cache, IPC collection order preserved.
- `tests/test_v2_batch_d15_critical_gpu_lane_coordination.py`: **7 passed**.
- D15-adjacent CLIP/VAE suite: **87 passed, 1 skipped** (CUDA-gated).
- `python -m py_compile comfymodal_runtime/clip_cold_path_forensics.py
  tests/test_v2_clip_cold_forensics.py`: **PASS**.
- No Modal deploys or requests.

```text
VERDICT = READY_FOR_D18_REMOTE_DECOMPOSITION

POST_SAMPLING_MODEL = VAE
OLD_CLIP_RELOAD_INTERPRETATION = FALSIFIED

SOFT_EMPTY_CACHE_CALLER = VAE native load_models_gpu -> free_memory -> soft_empty_cache
SOFT_EMPTY_CACHE_PURPOSE = device completion before generic model/allocator cleanup; global defensive ComfyUI policy; conservative IPC reclamation

SAMPLER_ALREADY_DEVICE_SYNCHRONIZED_AT_SAMPLING_END = NO
SYNC_REDUNDANT = UNKNOWN
EMPTY_CACHE_REDUNDANT = UNKNOWN
IPC_COLLECT_REDUNDANT = UNKNOWN

VRAM_HEADROOM_BEFORE_VAE = sufficient physical headroom observed after sampling; exact sampling_end allocator snapshot unavailable
VAE_REQUIRED_MEMORY = 1462827161.8 bytes free_memory requirement; 167639366 bytes VAE transfer; 9099509760 bytes decode demand
MODELS_ACTUALLY_UNLOADED = 0 observed in old D11 VAE window; authoritative count pending new telemetry

IMPLEMENTED_FINE_GRAIN_TELEMETRY = YES
IMPLEMENTED_OPTIMIZATION = NO
OPTIMIZATION = none; native ComfyUI path preserved

CURRENT_POST_SAMPLING_MS = ~1631
CURRENT_GATE_MS = ~962
PROVABLY_REMOVABLE_MS = 0
PROJECTED_POST_SAMPLING_MS = ~1631 pending remote decomposition

D15_REGRESSION = PASS

FILES_CHANGED = comfymodal_runtime/clip_cold_path_forensics.py; tests/test_v2_clip_cold_forensics.py; V2_BATCH_D18_VAE_SOFT_EMPTY_CACHE_GATE.md
TESTS = 27 D18/forensics passed; 7 D15 passed; 87 CLIP/VAE adjacent passed; 1 CUDA-gated skipped
PYCOMPILE = PASS

MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none

STOP.
```

## Remote Decomposition - 2026-08-16

This section records the bounded canonical remote validation. The local
findings above remain unchanged and are the pre-remote baseline.

### Deployment Gate

```text
DEPLOYMENT_IDENTITY = 6e57cbcfa65c6915869f95cb1123cc4be13e6702864e195418235487ed40d7d0
FINGERPRINT = b15040b25b7d339982664bb818b45f8fc7d02b5ed41a4af07ee83c2e8c5abbc2
IMAGE_ID = im-RiADu78VVWX7F7wI2JAf20
RUNTIME_SHAPE = f504e296c398bdcb2c4c07e2; CPU=12; RAM=32768 MiB; GPU=rtx-pro-6000; TBASE/O0
APP = stable-modal-comfy-v2-restore-only-shadow
CLASS = ModalRuntimeEntrypointV2
PROVIDER_PLACEMENT = unpinned; observed GCP/us-east4
PROFILE_VALID = YES
COMFYMODAL_V2_CRITICAL_GPU_COORDINATION = 1
COMFYMODAL_V2_CLIP_COLD_FORENSICS = 1
COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST = 1
COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA = 0
COMFYMODAL_V2_UNET_FASTSAFETENSORS = 1
COMFYMODAL_V2_CLIP_FAST_HYDRATION = 1
COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = 1
COMFYMODAL_V2_INPUT_TYPES_WARM = 1
COMFYMODAL_V2_UNET_FORENSICS = 0
COMFYMODAL_V2_SINGLE_USE_CONTAINERS = 1
```

The deployment wrapper passed the new-identity readback, runtime-shape, core
identity, snapshot-construction, and the matching complete D1 registry-proof
gate. The proof store also contains incomplete historical entries from failed
local proof contexts; those are not used for this deployment decision. The
first local wrapper lookup error did not invoke Modal and is not counted as a
deployment.

```text
MODAL_DEPLOYS = 1
MODAL_REQUESTS = 3
VALID_COLD_RUNS = 3
INVALID_RUNS = 0
```

All three requests used `run_v2_single.bat`, `V2_BENCHMARK_RUNS=1`, a fresh
conditioning-cache nonce, `restore_count=1`, `request_count=1`,
`decision=miss_stored`, `encode_calls=1`, `Fresh=YES`, the exact output SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`, and
waterfall reconciliation `OK`.

### D15 Readiness Results

All required D15 events were present in every run. `unet_cpu_prepare_start` to
`unet_cpu_prepare_ready` overlapped the CLIP critical interval in all runs.
`unet_gpu_transfer_start` to `unet_gpu_transfer_end` did not overlap the CLIP
GPU-critical interval in any run.

| Run | Provider | CLIP ready ms | UNET ready ms | Model gate ms | Sampling start ms | Gated by | UNET gate wait ms | CPU overlap | GPU overlap |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |
| 1 | GCP/us-east4 | 4582.715 | 7204.069 | 7204.069 | 7426.973 | UNET | 2617.738 | YES | NO |
| 2 | GCP/us-east4 | 3767.988 | 6011.228 | 6011.228 | 6201.937 | UNET | 1739.729 | YES | NO |
| 3 | GCP/us-east4 | 3811.841 | 6144.807 | 6144.807 | 6439.105 | UNET | 1849.233 | YES | NO |

Supporting interval measurements were:

| Run | CLIP hydration ms | CLIP bind wait ms | CLIP forward ms | CLIP critical ms | UNET CPU prep ms | UNET GPU transfer ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2050.055 | 0.164 | 2401.904 | 4454.444 | 268.335 | 2561.637 |
| 2 | 1659.199 | 0.151 | 1677.308 | 3338.824 | 75.726 | 2188.379 |
| 3 | 1673.398 | 0.198 | 1783.399 | 3459.674 | 86.999 | 2273.091 |

Against the settled same-provider GCP D11 baseline mean of `6262.5 ms`
(Run 2 `6253 ms`, Run 5 `6272 ms`), model-readiness deltas were `+941.6 ms`,
`-251.3 ms`, and `-117.7 ms`. The cohort mean was `+190.9 ms`; the spread is
too large to claim a stable application-path win. The intended static behavior
was structurally confirmed, but the measured D15 result is ambiguous.

### D18 Soft-Cache Decomposition

The target long invocation in every run was:

```text
native VAE load_models_gpu -> model_management.soft_empty_cache
model_class = comfy.ldm.models.autoencoder.AutoencodingEngine
caller = model_management.load_models_gpu
reason = model_management_load_models_gpu
```

The adjacent VAE `free_memory` context reported
`required_memory=1462827161.8` bytes. The target long `load_models_gpu` wrapper
reported `required_memory=0`, which is preserved as observed rather than
inferred. `free_memory_before`, allocation, and reservation fields below are
from the target long event.

| Run | Pre-sync ms | CUDA sync ms | Empty-cache ms | IPC ms | Post-cleanup ms | Total ms | Residual ms | Models unloaded | Bytes unloaded |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.548 | 0.044 | 950.460 | 0.010 | 0.047 | 951.320 | 0.211 | 0 | 0 |
| 2 | 0.688 | 0.038 | 739.241 | 0.010 | 0.040 | 740.226 | 0.209 | 0 | 0 |
| 3 | 0.509 | 0.028 | 934.173 | 0.014 | 0.051 | 935.051 | 0.276 | 0 | 0 |

The target context was stable across runs:

```text
allocated_before = 20427641856
reserved_before = 22594715648
free_memory_before = 80845794304
allocated_after = 20427641856
reserved_after = 20449329152
VAE_REQUIRED_MEMORY = 1462827161.8 bytes (adjacent free_memory context)
single_use = true
```

`empty_cache` accounted for 99.87-99.91% of the target soft-cache total. The
residual is the measured total minus pre-sync, synchronize, empty-cache, IPC,
and post-cleanup fields; it is wrapper/interval accounting residue, not a
claim of another CUDA operation.

```text
D18_DOMINANT_COMPONENT = EMPTY_CACHE
D18_MECHANISM_CLASSIFICATION = EMPTY_CACHE_DOMINANT
SYNC_REDUNDANT = UNKNOWN
EMPTY_CACHE_REDUNDANT = UNKNOWN
IPC_COLLECT_REDUNDANT = UNKNOWN
```

The dominant wall does not establish removability. The source-proven sampler
completion boundary is still absent, and no allocator or CUDA-IPC capability
proof was added by this measurement.

### Permanent Waterfall Footer

| Run | Command -> response s | Without scheduling s | Scheduling s | Pre-Python restore ms | Python restore ms | Restore->method ms | Remote setup ms | Executor/cache ms | Pre-sampler ms | Sampler->sampling ms | Sampling ms | Post-sampling ms | Decode ms | Output/PNG ms | Handoff ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 21.659 | 18.900 | 2.759 | 2680.318 | 789.140 | 22.549 | 1236.601 | 3750.947 | 3507.551 | 125.380 | 4729.542 | 968.768 | 416.269 | 265.419 / 159.436 PNG | 383.457 / 15.000 local |
| 2 | 19.685 | 16.992 | 2.694 | 2708.617 | 283.016 | 18.710 | 1644.582 | 6.349 | 5675.205 | 122.453 | 4733.987 | 751.938 | 371.031 | 265.213 / 161.803 PNG | 385.904 / 31.000 local |
| 3 | 20.449 | 17.202 | 3.248 | 2416.915 | 503.963 | 25.438 | 1473.889 | 8.099 | 5977.075 | 135.204 | 4747.805 | 949.317 | 366.573 | 263.092 / 159.977 PNG | 306.517 / 31.000 local |

`Scheduling s` is the permanent footer's scheduling interval. The separate
outer `.bat` windows were `25.841 s`, `24.121 s`, and `25.087 s`; they are not
merged into the reconciled command-to-response footer.

### Remote Decision

```text
D15_RESULT = AMBIGUOUS
D15_SAME_PROVIDER_BASELINE_MS = 6262.5 (GCP D11 mean)
D15_NEW_MODEL_GATE_MS = 7204.069 / 6011.228 / 6144.807
D15_CRITICAL_PATH_DELTA_MS = +941.6 / -251.3 / -117.7; cohort mean +190.9

D18_DOMINANT_COMPONENT = EMPTY_CACHE
D18_MECHANISM_CLASSIFICATION = EMPTY_CACHE_DOMINANT
CURRENT_POST_SAMPLING_BASELINE_MS = ~1631
OBSERVED_POST_SAMPLING_MS = 968.768 / 751.938 / 949.317
PROVABLY_REMOVABLE_MS = 0
BIGGEST_REMAINING_APP_BOTTLENECK = pre-sampler CLIP/model-readiness path; approximately 6.0-7.2 s to the readiness gate
NEXT_D18_OPTIMIZATION_CANDIDATE = generic allocator/empty-cache policy investigation with completion and capability proof; measure first

DIRECT_PYTHON_REMOTE_INVOKE_USED = NO
COMMIT = none
```

No D18 optimization, A/B, redeployment, sync removal, allocator skip, or IPC
skip was implemented after measurement. The lane remains available for a new
evidence-driven continuation.
