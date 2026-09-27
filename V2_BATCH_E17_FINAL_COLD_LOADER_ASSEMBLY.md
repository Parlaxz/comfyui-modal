# V2 Batch E17 - Final Cold Loader Assembly

Date: 2026-08-17
Status: local implementation and offline validation complete; remote validation intentionally not run
Scope: opt-in request-scoped orchestration around the existing fastsafetensors, D15, CLIP hydration, and UNET meta-worker seams

## Decision

E17 is implemented as a composition layer, not as a replacement loader. The
orchestrator owns request timing and source ownership. Existing fastsafetensors
and staged transport code remains responsible for tensor layout, GPU transfer,
owner retention, and Comfy binding.

The behavior gates are production-off:

```text
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION=0 (default)
COMFYMODAL_V2_CHECKPOINT_PREWARM=0 (default)
```

The existing C9/D15/CLIP gates remain independent and unchanged. Enabling E17
does not silently enable a loader or a GPU coordination policy.

## Request Timeline

1. Plan receipt calls `begin_request()` with the immutable model specification.
2. Physical paths are resolved generically from `model_spec` using existing
   `folder_paths` resolution when names are not already physical paths.
3. CLIP page-cache prewarm starts during unrelated setup when the prewarm gate
   is enabled. It reads only physical ranges and retains no model payload.
4. Immediately before CLIP demand, the prewarmer is stopped and joined with a
   hard bound. Storage ownership moves to `CLIP_DEMAND`, then the existing
   CLIP fastsafetensors path runs.
5. The outermost real CLIP forward starts UNET source prewarm. A no-forward
   exact conditioning-cache hit starts the same UNET prewarm path.
6. Existing C9 UNET Worker A constructs the meta model while Worker B prepares
   the fastsafetensors transport. The E17 controller records the meta interval
   independently from the GPU commit interval.
7. D15 continues to gate only the UNET GPU phase with
   `CLIP_GPU_CRITICAL_ACTIVE`. Before the fastsafetensors demand starts, the
   UNET prewarmer is stopped/joined and the commit wait is recorded.
8. Successful UNET completion records readiness. Request finalization retires
   any remaining prewarmer and releases storage ownership.

## Storage Contract

The request-scoped controller exposes exactly these states:

```text
NONE
CLIP_PREFETCH
CLIP_DEMAND
UNET_PREFETCH
UNET_DEMAND
```

The assembled path never takes a direct `CLIP_PREFETCH -> UNET_DEMAND`
transition. It first retires CLIP ownership, then moves through
`CLIP_DEMAND` before UNET demand. A source prewarm is always fenced before its
corresponding demand loader, except when the bounded join times out and the
reader is explicitly abandoned.

## Bounds And Ownership

- Default reader geometry remains 8 MiB to preserve the E12 volume-read contract.
- Environment-enabled orchestration defaults to 4 bounded reader workers; an
  explicitly constructed legacy/test reader remains single-worker unless its
  thread count is supplied.
- Total read work is bounded by the configured byte cap and host headroom:
  available RAM minus safety and pinned-memory reserves.
- Wall time and demand-join time are independently bounded.
- A blocked filesystem read can leave a daemon worker alive after the join
  deadline, but the prewarmer state is retired and demand proceeds.
- Reads use unbuffered binary `readinto`; no checkpoint payload is retained in
  the prewarmer object after completion.
- The prewarmer does not allocate pinned memory or change the existing C9/E11
  pinned-ring budget. Pinned staging remains owned and bounded by the existing
  staged transport implementation.
- `posix_fadvise` is advisory only. Bytes read are never reported as proof of
  page residency.

## Telemetry

The `fast_cold_orchestration` trace event includes:

- storage owner and transition history
- CLIP and UNET prewarm bytes, fractions, per-file details, wall time, join time,
  setup overlap, stop reason, and RAM bounds
- CLIP fastsafetensors interval and forward interval
- CLIP GPU-critical interval
- UNET meta start/ready interval
- UNET fastsafetensors interval and GPU commit wait
- prefetch/demand overlap and UNET overlap with the CLIP critical interval
- model readiness gate and fallback reason

The prewarmer reports actual reads, not cache hits. No cache-drop operation or
`cachestat` claim is made by E17. A real page-residency or CUDA-throughput
benefit remains a deployment measurement, not an offline assertion.

## Files

- `comfymodal_runtime/checkpoint_prewarm.py`: bounded single/parallel source reader and telemetry.
- `comfymodal_runtime/fast_cold_orchestration.py`: request controller and storage state machine.
- `comfymodal_runtime/modal_app.py`: plan receipt, request lifecycle, and remote env passthrough.
- `comfymodal_runtime/model_preload.py`: generic CLIP forward and cache-hit lifecycle hooks.
- `comfymodal_runtime/clip_fast_hydration.py`: CLIP demand fence.
- `comfymodal_runtime/clip_fast_hydration_wiring.py`: CLIP fastsafetensors timing and fallback closure.
- `comfymodal_runtime/gpu_lane_coordination.py`: D15 critical interval notifications.
- `comfymodal_runtime/unet_fastsafetensors.py`: UNET meta, demand fence, fastsafetensors, and readiness hooks.
- `tests/test_v2_e17_final_cold_loader.py`: offline E17 contracts.

## Validation

```text
E12 checkpoint prewarm: 27 passed
E17 final cold-loader contracts: 6 passed
D15 + C9 + E11 regressions: 44 passed
CLIP hydration + staged transport regressions: 69 passed, 1 skipped
Python compilation of all affected modules: PASS
Runtime env production defaults: PASS
Targeted whitespace check for E17 files: PASS
Modal deploys: 0
Modal requests: 0
Paid workloads: 0
Commit: none
```

## Completion Matrix

```text
E17_COMPLETE = YES (local/offline implementation)
MASTER_DEFAULT_OFF = YES
PREWARM_DEFAULT_OFF = YES
GENERIC_PHYSICAL_PATH_RESOLUTION = YES
BOUNDED_PAGE_CACHE_READ = YES
BOUNDED_JOIN_AND_ABANDON = YES
NO_RETAINED_PREWARM_PAYLOAD = YES
CLIP_DEMAND_FENCE = YES
UNET_META_PREPARATION_HOOK = YES (existing C9 Worker A)
UNET_STORAGE_PREPARE_HOOK = YES
D15_GPU_COMMIT_GATE = YES (existing coordination path preserved)
E11_SERIAL_SOURCE_ORDER_ADDED = NO
MODEL_FAMILY_LOGIC_ADDED_TO_ORCHESTRATOR = NO
PINNED_MEMORY_BUDGET_CHANGED = NO
LOCAL_TESTS = PASS
PYCOMPILE = PASS
TARGETED_DIFF_CHECK = PASS
REPOSITORY_DIFF_CHECK = BLOCKED_BY_PREEXISTING_WHITESPACE (tests/test_cpu_snapshot_models.py:2373)
REMOTE_VALIDATION = NOT_RUN_BY_REQUEST
CUDA_READINESS_AND_PAGE_RESIDENCY_SAVINGS = NOT_PROVEN_LOCALLY
```

## Enablement

An actual shadow/deployment experiment must explicitly select the lower-level
loader and coordination gates as appropriate for that deployment, for example:

```text
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION=1
COMFYMODAL_V2_CHECKPOINT_PREWARM=1
COMFYMODAL_V2_UNET_FASTSAFETENSORS=1
COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1
```

The existing CLIP fast-hydration/staged flags are still required for their
respective paths. E17 itself does not override an ineligible C9 loader; the
existing native fallback remains the fallback.

## Residual Risks

- The current validation host is Windows and no real Modal GPU request was
  allowed, so CUDA readiness, provider page-cache behavior, and measured
  CLIP/UNET wall-clock overlap remain deployment evidence gates.
- Existing editor diagnostics for `comfy`, `folder_paths`, `nodes`, and related
  ComfyUI runtime imports remain environment-resolution warnings; affected
  Python files compile and scoped tests pass.
- The shared worktree contains extensive unrelated existing modifications and
  generated artifacts. They were not reverted, staged, or committed.
