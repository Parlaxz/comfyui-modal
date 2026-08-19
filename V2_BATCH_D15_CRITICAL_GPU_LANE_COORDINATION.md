# V2 Batch D15 - Critical GPU-Lane Coordination

Date: 2026-08-16

Scope: prevent request-scoped UNET direct-GPU fastsafetensors activity from
overlapping the generic CLIP GPU hydration/bind/forward interval while keeping
UNET CPU/meta preparation concurrent.

This batch does not implement D13 request-entry/setup changes or D14
post-sampling changes. No Modal deploy or request was made.

## Result

`READY_FOR_D15_REMOTE_VALIDATION`

The implementation is opt-in with:

`COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1`

The default-off behavior is unchanged when the flag is absent or false.

## Root Cause

D12's Run 2 bind wall contained the existing `torch.cuda.synchronize()` in
`comfymodal_runtime/clip_fast_hydration_wiring.py:_try_fast_hydrate` while the
UNET fastsafetensors GPU copy was outstanding. Runs 5 and 6 showed the same
UNET lane overlapping the CLIP transformer forward. The contention is therefore
GPU-lane contention, not CLIP-only work.

## Current Call Graph Audit

### UNET

1. `V2LoaderBridge.schedule_execution_unet` submits `_execution_unet` to the
   coordinator pool in `comfymodal_runtime/model_preload.py:12755`.
2. `_execution_unet` calls `self._load_unet(_key)` at
   `comfymodal_runtime/model_preload.py:12821-12832`.
3. The `_load_unet` branch lazy-imports `unet_fastsafetensors` and calls
   `_fs_try_pipeline` at `model_preload.py:13424-13432`.
4. `_fs_try_pipeline` resolves the path, parses the header, derives config,
   and validates eligibility before creating the workers.
5. Worker A starts at `unet_fastsafetensors.py:935` and runs
   `_fs_meta_construct`, including meta model construction and sampling repair.
6. Worker B starts at `unet_fastsafetensors.py:1026`. Its first
   GPU-materializing operation is `_fs_fastsafe_load` at line 1045, which
   creates `SafeTensorsFileLoader`, calls `copy_files_to_device`, and obtains
   device-backed tensor views.
7. After both workers join, the caller performs assign bind, residual-meta
   sweep, final `.to`, the existing final CUDA sync, validation, and patcher
   owner attachment at `unet_fastsafetensors.py:1195-1331`.
8. The successful pipeline returns the patcher at line 1448; the existing
   coordinator future is the readiness future consumed by the graph-side
   `wait_unet` path.

The source therefore has a clean Worker A/Worker B split. No CPU-only
preparation was moved behind the GPU gate.

### CLIP

1. `maybe_install_clip_fh_demand` installs the existing demand hydrator around
   the generic CLIP object.
2. The D15 wrapper in `clip_fast_hydration.py:1373` wraps generic
   `load_model`, `encode_from_tokens_scheduled`, and `encode_from_tokens`.
3. Parent ComfyUI `comfy/sd.py` confirms `encode_from_tokens` calls
   `self.load_model(tokens)` before `cond_stage_model.encode_token_weights`.
   The scheduled path has the same load boundary.
4. The existing fast hydration path is
   `_hydrate_clip_on_demand` -> `_try_fast_hydrate` -> `_fastsafe_load` ->
   `hydrate_clip_bind` -> owner attach -> synchronization.
5. The current synchronization is directly verified at
   `clip_fast_hydration_wiring.py:696`:

   `torch.cuda.synchronize()`

## Implemented Coordination

`comfymodal_runtime/gpu_lane_coordination.py` provides the generic,
request-keyed capability state `CLIP_GPU_CRITICAL_ACTIVE`.

- CLIP encode/load and UNET GPU phases use the same request ID.
- The state is exclusive: CLIP waits for an already active UNET GPU phase, and
  UNET waits for an active CLIP critical section.
- Nested scheduled/direct encode calls are re-entrant for the owning thread.
- Critical state is released in `finally` paths in the wrappers and the UNET
  gate is released after success or failure in the outer pipeline `finally`.
- `request_end` removes the state after worker shutdown; bounded trimming also
  prevents abandoned diagnostics from growing without bound.
- The cache-hit path records CLIP readiness without entering a critical
  section, so UNET does not wait for an encode that will not happen.

## UNET Boundary

The gate is acquired in Worker B immediately before
`_fs_fastsafe_load`. Worker A is already independent and continues while
Worker B waits. The gate remains held through Worker B's direct-GPU load and
the post-join UNET GPU commit/final synchronization, and is released only
after the pipeline reaches its terminal return or fallback.

Therefore:

- path resolution, header parsing, manifest/config derivation, and CPU-only
  bookkeeping are not gated;
- Worker A meta/model construction still overlaps CLIP;
- direct file-to-GPU loading cannot overlap CLIP hydration/bind or forward;
- final UNET GPU readiness cannot race the end of the CLIP critical section.

## CLIP Boundary

The protected interval is:

`clip_gpu_critical_enter` -> generic CLIP `load_model`/hydration/bind ->
`clip_forward_start` -> transformer forward -> `clip_forward_end` ->
`clip_gpu_critical_exit`.

Direct `load_model` calls without an enclosing encode are also protected for
hydration and released on success or exception. Exact conditioning cache hits
do not call these wrappers.

## Synchronization Decision

`OLD_CLIP_SYNC = torch.cuda.synchronize()` after CLIP owner attachment and
zero-copy bind.

`NEW_CLIP_SYNC = torch.cuda.synchronize()` unchanged.

`GLOBAL_DEVICE_SYNC_REMOVED = NO`

The current fastsafetensors path does not expose a verified CLIP-owned CUDA
stream/event contract. The global sync still proves all CLIP tensors and
zero-copy owner-backed storage are complete before forward. Removing it or
substituting an unverified event would risk incomplete weights or a storage
lifetime race. D15 instead prevents the unrelated UNET transfer from being
outstanding when this required sync executes.

## Telemetry

When coordination is enabled, the trace receives:

- CLIP: `clip_gpu_critical_enter`, `clip_hydration_gpu_start`,
  `clip_hydration_gpu_end`, `clip_bind_wait_start`, `clip_bind_wait_end`,
  `clip_forward_start`, `clip_forward_end`, `clip_gpu_critical_exit`.
- UNET: `unet_cpu_prepare_start`, `unet_cpu_prepare_ready`,
  `unet_gpu_gate_wait_start`, `unet_gpu_gate_wait_end`,
  `unet_gpu_transfer_start`, `unet_gpu_transfer_end`, `unet_ready`.
- Derived: `model_readiness_gate` with `CLIP_READY_AT`, `UNET_READY_AT`,
  `MODEL_READINESS_GATE_AT`, `SAMPLER_GATED_BY`, and
  `EXPOSED_MODEL_READINESS_MS`.

Events include `request_id`, `reason`, `wait_ms` or duration fields, and
`cache_state` when meaningful. No CUDA synchronization is added for
diagnostics.

## Exception, Cache, and Reuse Behavior

- CLIP exception: the encode/load wrapper releases the critical state in its
  `finally` path; a waiting UNET phase proceeds.
- UNET exception: the outer `_fs_try_pipeline` `finally` releases its gate;
  existing fastsafetensors fallback behavior remains unchanged.
- Cache hit: no CLIP encode, no CLIP critical section, no hydration; UNET
  proceeds immediately and readiness telemetry records `cache_hit`.
- Request N/N+1: state keys are request IDs, and request-end cleanup removes
  request N state before the next request.
- Native fallback: the wrapper only coordinates timing; native loader,
  fallback count, owner lifetime, and data-binding behavior remain unchanged.

## Correctness Invariants

The existing production tests continue to cover the fast hydration invariants:

- `EXCLUDED_PLACEHOLDER` handling;
- manifest eligibility;
- parameter counts and zero-copy file binding;
- fallback behavior and owner retention;
- no duplicate native H2D on the healthy path.

No model-family, filename, architecture, or workflow-name branch was added.

## Static Critical-Path Model

D11 observed pre-sampler execution/model-readiness baselines:

`D11_MODEL_GATE_BASELINE_MS = 6253 (GCP Run 2), 6272 (GCP Run 5), 7746
(AWS Run 6); mean 6757.`

The D11 sampler-node-to-sampling spans were another 124-155 ms and are not
claimed as CLIP savings here.

### Predicted sequence

| Phase | Best | Expected | Worst reasonable |
|---|---:|---:|---:|
| CLIP hydration + uncontended bind + clean forward + small overhead | 3260 | 3300 | 3400 |
| UNET CPU/meta preparation, overlapped | 2780-3020 | 2900-3020 | 3020 |
| Gated UNET GPU tail after CLIP critical exit | 2400 | 2650 | 3100 |
| `max(CLIP_READY, UNET_READY)` | **5660** | **5950** | **6500** |

Inputs:

- GCP intrinsic CLIP hydration file-to-GPU: 1400-1470 ms;
- uncontended bind: 100-120 ms;
- clean forward: about 1730 ms;
- current D11/D12 UNET component observations: meta about 2780-3020 ms and
  direct-GPU activity about 2690-3060 ms;
- historical healthy fastsafe UNET total/tail: about 2400-2700 ms.

The expected model-readiness path is approximately:

`UNET CPU/meta starts with CLIP -> CLIP ready ~3300 ms -> gated UNET GPU tail
~2650 ms -> UNET ready ~5950 ms -> max readiness ~5950 ms.`

The expected critical-path saving is approximately 250-350 ms against the
GCP D11 pre-sampler baselines, not 2.8-3.6 seconds of CLIP-only wall. The
large D12 CLIP wall inflation is converted into a serialized UNET tail, so
the correct claim is a time-to-sampler improvement only when that tail and
the CLIP completion remain below the old gate. The expected 5950 ms is below
the three D11 observed pre-sampler values, making this worthwhile for remote
validation. The AWS-specific approximately 700 ms residual remains unknown
and is not solved or attributed to D15.

## Verification

- `tests/test_v2_batch_d15_critical_gpu_lane_coordination.py`: 7 passed.
- `tests/test_v2_clip_fast_hydration_production.py`,
  `test_v2_clip_hydration_states.py`, and
  `test_v2_clip_restore_lifecycle.py`: 74 passed, 1 skipped (CUDA-gated).
- `test_c9_fastsafetensors_integration.py`,
  `test_native_fast_disk_unet_loader.py`, and
  `test_v2_unet_runtime_ab.py`: 88 passed.
- Conditioning cache and prefill attribution suite: 47 passed.
- `py_compile` passed for all changed Python modules and the D15 test.

`MODAL_DEPLOYS = 0`

`MODAL_REQUESTS = 0`

`COMMIT = none`
