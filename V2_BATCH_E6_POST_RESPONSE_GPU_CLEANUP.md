# V2 Batch E6 - Post-Response GPU Cleanup and True-Exit Audit

Date: 2026-08-16

Scope: read-only lifecycle audit. No runtime edits, Modal deploys, Modal
requests, or commit. The normal V2 request path is audited; gated benchmark and
probe helpers are not treated as production lifecycle calls.

## Required Outputs

CALLER_VISIBLE_SAFE_BOUNDARY=local_result_received (strict end-to-end caller-return stamp: execute_plan_return)
EXIT_ONLY_CLEANUP_POSSIBLE=YES
CAN_KNOW_CONTAINER_WILL_EXIT_BEFORE_RESPONSE=NO
WHICH_CLEANUPS_CAN_MOVE_AFTER_RESPONSE=request GPU release cleanup, including full unload_all_models, fallback free_memory, cleanup_models, gc.collect, direct CUDA synchronize, direct empty_cache, and nested soft_empty_cache/ipc_collect; bounded request-reference and worker cleanup; production registry cleanup is already deferred post-handoff
WHICH_MUST_STAY=native VAE load/decode memory management before VAEDecode completes, including the current free_memory/soft_empty_cache contract and its synchronize/empty_cache/ipc_collect sequence; VAE OOM-retry soft_empty_cache; result assembly and remote_result_emit before the terminal event is yielded
RECOMMENDED_SINGLE_USE_POLICY=do not run GPU cache cleanup or full model unload before the terminal result is handed off; use minimal bounded reference/worker cleanup only after the result boundary when needed; for a container that is actually closing, rely on @modal.exit and process termination, and do not pay redundant full unload/cache cleanup merely to make termination happen
NEEDS_REMOTE_AB=NO

`NEEDS_REMOTE_AB=NO` means no remote A/B is needed to answer this audit or
establish the policy boundary. A later implementation change would still need
remote validation to measure its actual wall-time and exit behavior.

## Exact Lifecycle

1. `VAEDecode` calls `vae.decode(samples)` in `nodes.py:310-318`.
2. Native `VAE.decode` calls `model_management.load_models_gpu` before decode in
   `comfy/sd.py:1052-1057`. The normal path may also perform the same VAE load
   in the sampling-end early-activation worker at
   `comfymodal_runtime/model_preload.py:19721-19756`.
3. The decode produces tensors, then the output/result path collects the PNG or
   descriptor and constructs the result envelope. Output persistence and
   descriptor work occur before the remote emission stamp.
4. `remote_result_emit` is stamped immediately before the result event is
   yielded by `_run_plan_stream_impl` at `modal_app.py:17866-17897`.
5. The outer `run_plan_stream` currently identifies the terminal event and runs
   `_run_terminal_cleanup_sync` before yielding that event at
   `modal_app.py:16368-16398`. If GPU release is enabled, this is a
   pre-response release path.
6. The Modal transport receives and yields the terminal event at
   `modal_transport.py:1415-1431` or `:1453-1465`. The host captures the result,
   breaks, and closes the transport stream at `canonical_execution.py:2313-2331`.
   The `local_result_received` stamp follows at `:2335-2345`; all local merge
   work then completes before `execute_plan_return` at `:3124-3170`.
7. The decorated outer async-generator wrapper runs
   `_release_after_stream_complete` in its `finally` at
   `modal_app.py:18069-18103`. This is after the response stream has been
   consumed, but it is not proof that the container is closing.
8. Modal invokes the decorated `@modal.exit` method only when the platform is
   tearing down that container. The hook performs bounded service cleanup and,
   when the terminal response was delivered, may call GPU release at
   `modal_app.py:5442-5534`.
9. Process/container termination follows the exit hook. The operating system
   then reclaims all remaining CUDA allocations without an application-level
   `empty_cache` call.

The current successful-result path can therefore attempt GPU release before
the result event is handed to the consumer and then attempt the effective
release again after the stream closes. `_release_after_stream_complete` resets
the release guard specifically to re-execute the effective release after the
inner generator frame is gone (`modal_app.py:16263-16301`).

## Cleanup Inventory

The same function name has different semantics at different call sites. The
classification below is call-site-specific.

| Operation and location | Before result correctness | Required before response return | Reusable container | Modal teardown/billing | Redundant at process exit |
| --- | --- | --- | --- | --- | --- |
| Native `free_memory` from `load_models_gpu` at `comfy/model_management.py:799-841, :905-915`, reached by early VAE activation and `VAE.decode` | Stay in the current native load contract. It may unload models and establishes allocator headroom; independent removal is unproven. | Yes indirectly, because the VAE load/decode must complete before a result exists. It is not a result-transport requirement. | No; it is a model-load correctness/memory-management path. | No. It does not terminate a Modal container or stop billing. | No for this pre-decode call; the result cannot exist without the decode path. |
| Native `soft_empty_cache` called by `free_memory` after unload or allocator threshold at `comfy/model_management.py:834-840` | Not independently proven removable. D18 found enough physical VRAM but not enough allocator/capability proof to bypass it. | Yes on the current path because it is inside the pre-VAE load contract; not because the caller needs a clean cache to receive bytes. | No. | No. | Only a separate teardown copy would be redundant; not this pre-decode call. |
| CUDA sequence inside native `soft_empty_cache`: `torch.cuda.synchronize`, `torch.cuda.empty_cache`, `torch.cuda.ipc_collect` at `comfy/model_management.py:1944-1960` | Keep the sequence for current native semantics. D18 measured `empty_cache` as the dominant wall, but did not prove any suboperation removable. | Yes on the current VAE load path; the exact suboperations are not a caller-visible response requirement once decode has already completed. | No. | No. | Yes if invoked only as post-response teardown immediately before process exit; no if invoked by pre-decode VAE loading. |
| VAE OOM fallback `soft_empty_cache` at `comfy/sd.py:1077-1087` | Yes for the tiled-decode retry path after an OOM. | Only on the error-recovery path. | No. | No. | No before the retry; irrelevant if no OOM occurs. |
| `unload_all_models` in full request release at `modal_app.py:5826-5880`, which recursively uses `free_memory` and may invoke native `soft_empty_cache` | No. The graph result already exists. | No. | Yes when the same process/container must remain reusable and GPU memory must be made available for another request. | No. Cleanup does not cause Modal teardown or billing to stop. | Yes. Process exit releases the allocations. |
| Full-release fallback `free_memory(1e30, device, keep_loaded=[])` at `modal_app.py:5882-5908` | No. It is only a recovery path after full unload failure. | No. | Yes only for reusable-container recovery. | No. | Yes at process exit. |
| `cleanup_models` at `modal_app.py:5910-5919` | No. It removes dead model-management records after the result. | No. | Useful for reuse, not required for response correctness. | No. | Yes in the process-exit case. |
| Full-release `gc.collect` at `modal_app.py:5933-5938` | No. It helps release Python references for reuse. | No. | Useful for reuse, not required for response correctness. | No. | Yes for memory reclamation at process exit. |
| Direct teardown `cuda_api.synchronize()` and `cuda_api.empty_cache()` at `modal_app.py:5940-5962` | No. They occur after the result in the intended release path. | No. | Useful only when reusable-container memory reclamation is the goal. | No. | Yes. They are redundant immediately before process termination. |
| GPU-release wrapper `_release_gpu_after_request`, called pre-yield at `modal_app.py:16226-16261`, post-stream at `:16263-16301`, fallback at `:16438-16464`, and exit at `:5519-5528` | The wrapper itself is not required for result correctness. | No for a successful result; the pre-yield call is the policy violation when it performs full cleanup. | Full mode is for reuse; minimal mode is suitable for single-use. | No. The wrapper is not a termination primitive. | Yes for full GPU cleanup when the process is already closing. |
| Minimal bounded release selected by `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` at `modal_app.py:5619-5625` | No GPU cache operation is needed for result correctness. | It should not be paid before the result handoff. Its reference/worker parts can run after the result if needed. | Not required for reusable GPU capacity; reusable mode intentionally selects full cleanup by default. | No. | Mostly yes; only orderly worker/reference shutdown may remain useful before exit. |

## What Is and Is Not Movable

### Can move after response

- Full request teardown: `unload_all_models`, fallback `free_memory`,
  `cleanup_models`, `gc.collect`, direct `cuda.synchronize`, and direct
  `cuda.empty_cache`.
- The nested `soft_empty_cache`, `torch.cuda.synchronize`,
  `torch.cuda.empty_cache`, and `torch.cuda.ipc_collect` reached by those
  teardown-only unload paths.
- Bounded request references, preload-worker joins, sampler/activation
  reference clearing, and production registry cleanup. The production cleanup
  is already stashed in `modal_app.py:14736-14753` and is designed to run from
  the generator finalizer after the terminal event or from `exit` as fallback.
- The correct destination for cleanup that is conditional on actual teardown
  is `@modal.exit`, not the generic post-stream hook. The post-stream hook is
  after response delivery but has no platform fact that the container will
  close.

### Must stay before result

- The native VAE `load_models_gpu` and its `free_memory`/`soft_empty_cache`
  policy before `VAE.decode`.
- The `synchronize`/`empty_cache`/`ipc_collect` sequence when it is the native
  `soft_empty_cache` called by that pre-decode model-management path. D18's
  `empty_cache`-dominant timing is an optimization target, not a proof that it
  can be moved after the result.
- The VAE OOM fallback `soft_empty_cache` before tiled retry.
- Result construction, PNG/asset correctness, and `remote_result_emit` before
  the terminal event is handed to the stream consumer.

Changing the pre-decode native cache policy would require a separate,
allocator-aware correctness experiment. It is not equivalent to moving
post-request teardown.

## True-Exit Determination

`COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1` is a deployment policy. It is resolved
into `ModalRuntimeSpec.single_use_containers` at `modal_app.py:2793-2802` and
forwarded to `app.cls(single_use_containers=...)` at `:18198-18256`. It tells
Modal not to reuse the container for another input, but it is not a synchronous
"the process is now closing" signal.

`target_inputs=1` and `max_inputs=1` only constrain input handling. The prior
teardown evidence showed that without `single_use_containers=True`, the
container returned to its reusable input loop and `@modal.exit` lagged GPU
release by about 24 seconds. With single-use enabled, post-stream release and
`exit_hook_start` occurred in the same second, but the actual close was still
observed by the exit lifecycle, not known before the response.

Therefore:

- Before response return: know the configured single-use policy, not actual
  platform teardown.
- At post-stream release: know that response consumption has advanced, not that
  the container will close.
- In `@modal.exit`: know that Modal has entered the container-exit hook. This is
  the first application-visible true-exit boundary.
- After process termination: all remaining CUDA allocations are reclaimed by
  the OS; explicit cache cleanup has no billing benefit.

## Prior Single-Use Evidence

`V2_VARIANCE_CAUSAL_FIX_REPORT.md:11-39` provides the relevant controlled
single-use teardown A/B:

- Full `unload_all_models`: terminal release `2,560.334 ms`; model-management
  unload `1,929.4 ms`; garbage collection `627.3 ms`; post-stream re-release
  `633.8 ms`.
- Minimal bounded cleanup: terminal release `2.455 ms`; post-stream release
  `2.0 ms`; full unload, fallback, model cleanup, GC, and CUDA cleanup skipped.
- Full mode reclaimed CUDA in-process; minimal mode retained about `12.63 GB`
  until process exit.
- Result delivery and output correctness were identical; both containers
  disappeared after the exit hook.
- The report adopted minimal teardown for single-use and retained full unload
  for reusable-container mode.

This evidence supports not paying full GPU cleanup before the response. It also
supports not adding a second post-stream full cleanup when the container is
single-use and is going to terminate.

## Out-of-Path Calls

The repository also contains explicit CUDA synchronization/cache calls in
restore, fast-hydration, UNET transfer, NUMA, rehoming, snapshot, and benchmark
helpers. Those are gated experiments, diagnostics, or restore/setup work, not
the normal `VAEDecode -> PNG/result -> remote_result_emit` request tail. They
must not be reclassified as post-response cleanup by this audit. The normal
path's authoritative CUDA cleanup calls are the native ComfyUI VAE path and
the request-release path listed above.

## Final Decision

The preferred policy is source-compatible with the existing lifecycle if the
release decision is made at the correct boundary:

1. Do not run full request GPU release before yielding the terminal result.
2. Do not treat post-stream as proof of container closure.
3. For single-use containers, retain only minimal bounded cleanup if an
   orderly reference/worker release is needed, and defer it until after result
   handoff.
4. Put any useful full teardown behind `@modal.exit`; immediately before
   process termination, full `unload_all_models`/`empty_cache` is redundant and
   should normally be skipped.
5. Preserve native pre-decode VAE memory management until a separate
   correctness/allocator proof establishes a safe alternative.

STOP.
