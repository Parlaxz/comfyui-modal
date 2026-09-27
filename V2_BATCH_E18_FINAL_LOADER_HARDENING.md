# V2 Batch E18 - Final Loader Hardening

Date: 2026-08-17
Status: local implementation and offline validation complete; remote validation intentionally not run
Scope: absolute source fencing, scoped CUDA readiness, and preservation of the E17/D15 cold-loader assembly

## Decision

E18 keeps the E17 composition layer and existing fastsafetensors transport as
the primary loader. It adds two correctness boundaries:

1. A prewarm reader must be physically retired before a demand loader may read
   the same source.
2. CUDA readiness may use request-local events and stream waits when explicitly
   enabled; the historical device-wide synchronization remains the off-path
   behavior.

The new behavior is production-off unless the explicit gates are enabled.

## Source Fence

`comfymodal_runtime/checkpoint_prewarm.py` now tracks every active reader-owned
file handle and every inner worker. At a demand boundary it:

1. Sets the stop event, preventing new chunks from starting.
2. Performs the bounded primary join.
3. Closes active reader handles when a worker remains in source I/O.
4. Performs a separate bounded retirement join over the outer and inner
   workers.
5. Allows demand only when the physical worker set is empty.

Normal retirement is reported as `joined_primary` or
`retired_after_fd_close`. An unretireable reader is reported as
`retirement_failed`, `source_fence_valid=false`, and a missing
`demand_loader_start_at`; demand does not begin on that path.

This supersedes the E17 behavior that permitted demand after an abandoned
reader join. The source-fence failure is structural, not a performance
fallback. CLIP and UNET wiring re-raises `SourceFenceFailure`, and UNET native
fallback is not silently entered for this failure class.

## CUDA Readiness

`comfymodal_runtime/gpu_lane_coordination.py` adds the default-off
`COMFYMODAL_V2_SCOPED_CUDA_READINESS` gate and request-local helpers for:

- recording a CUDA event on the producer stream;
- enqueueing `consumer_stream.wait_event(event)`;
- synchronizing one event for CPU-side compatibility paths;
- recording targeted-event versus device-wide synchronization telemetry.

CLIP and UNET fastsafetensors paths record readiness events after their copy
stage and wait on the consumer stream before bind/final use. With the scoped
gate off, the existing `torch.cuda.synchronize()` path remains active.

The D15 `CLIP_GPU_CRITICAL_ACTIVE` exclusion remains the owner of the UNET GPU
commit gate. Scoped readiness does not change the four-worker E17 overlap
geometry or introduce a global stream wait.

## Telemetry

The orchestration record now includes:

- per-role source-fence validity;
- workers alive at stop, after primary join, and at demand start;
- retirement result, retirement duration, and closed-handle count;
- demand-start timestamps only after a valid fence;
- copy-event record/wait timestamps;
- targeted event-sync counts and device-wide sync counts;
- explicit structural source-fence fallback reasons.

## Future Validation Profile

The future validation must use a deployed Modal App and the following explicit
profile. It must not use `modal run` or `app.run()`.

```text
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION=1
COMFYMODAL_V2_CHECKPOINT_PREWARM=1
COMFYMODAL_V2_CLIP_FAST_HYDRATION=1
COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1
COMFYMODAL_V2_UNET_FASTSAFETENSORS=1
COMFYMODAL_V2_CRITICAL_GPU_COORDINATION=1
COMFYMODAL_V2_SCOPED_CUDA_READINESS=1
COMFYMODAL_V2_STAGED_SAFETENSORS=0
COMFYMODAL_V2_C9QD_EXTRAS=0
COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS=4
COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB=8
```

E11 source-order transport remains disabled. Fastsafetensors remains the
primary transport. The existing 4-reader, 8 MiB E17 geometry is unchanged.

## Files

- `comfymodal_runtime/checkpoint_prewarm.py`: active-handle retirement and absolute source fence.
- `comfymodal_runtime/fast_cold_orchestration.py`: source-fence failure state, ownership protection, and telemetry.
- `comfymodal_runtime/gpu_lane_coordination.py`: scoped CUDA event record/wait helpers.
- `comfymodal_runtime/clip_fast_hydration.py`: generic CLIP event path and fence failure propagation.
- `comfymodal_runtime/clip_fast_hydration_wiring.py`: production CLIP event path and structural-failure handling.
- `comfymodal_runtime/unet_fastsafetensors.py`: UNET event path, demand fence, and compatibility gate helper.
- `comfymodal_runtime/model_preload.py`: structural source-fence propagation at the UNET fallback boundary.
- `comfymodal_runtime/staged_safetensors.py`: no successful-path timing-only device sync.
- `comfymodal_runtime/modal_app.py`: deployed runtime environment passthrough.
- `tests/test_v2_e18_final_loader_hardening.py`: focused E18 contracts.

## Validation

```text
E18 focused tests: 10 passed
E12 checkpoint prewarm: 27 passed
E17 final cold-loader contracts: 6 passed
D15 critical GPU coordination: 8 passed
C9 fastsafetensors integration + QD probe: 59 passed
E11 source-order regression: 8 passed
Consolidated E18/E12/E17/D15/C9/E11/CLIP/staged suite: 194 passed, 1 skipped
Additional CLIP lifecycle/cache/forensics suites: 76 passed, 1 skipped; 78 passed, 2 warnings
Python compilation of affected modules and E18 tests: PASS
Targeted diff check: PASS; only existing LF/CRLF warnings were emitted for modal_app.py and model_preload.py
Local CUDA availability: PASS, NVIDIA GeForce RTX 3070
Local CUDA event record/wait synthetic test: CUDA_EXECUTION_TEST=PASS
Modal deploys: 0
Modal requests: 0
Paid workloads: 0
Commit: none
```

The local CUDA test proves event record/wait ordering and a dependent tensor
result on the RTX 3070. It does not prove Modal provider page residency,
remote-volume throughput, or end-to-end CLIP/UNET wall-clock savings.

## Completion Matrix

```text
E18_COMPLETE = YES (local/offline implementation)
MASTER_DEFAULT_OFF = YES
SCOPED_CUDA_READINESS_DEFAULT_OFF = YES
ABSOLUTE_SOURCE_FENCE = YES
ACTIVE_READER_HANDLES_CLOSED = YES
DEMAND_BLOCKED_ON_RETIREMENT_FAILURE = YES
STRUCTURAL_FENCE_FAILURE_PROPAGATED = YES
D15_GPU_COMMIT_GATE_PRESERVED = YES
E17_PREFETCH_OVERLAP_GEOMETRY_PRESERVED = YES
FASTSAFE_REMAINS_PRIMARY_TRANSPORT = YES
E11_SERIAL_TRANSPORT_USED = NO
PINNED_MEMORY_BUDGET_CHANGED = NO
LOCAL_TESTS = PASS
PYCOMPILE = PASS
CUDA_EXECUTION_TEST = PASS
REMOTE_VALIDATION = NOT_RUN_BY_REQUEST
PAGE_RESIDENCY_SAVINGS = NOT_PROVEN
```

## Residual Risks

- No real Modal request was allowed, so provider storage behavior and deployed
  cold-path timing remain open evidence gates.
- The shared worktree contains extensive unrelated modifications and generated
  artifacts. They were preserved and not staged, reverted, or committed.
- Existing editor diagnostics for ComfyUI runtime-only imports remain separate
  from this change; affected modules compile and focused tests pass.
