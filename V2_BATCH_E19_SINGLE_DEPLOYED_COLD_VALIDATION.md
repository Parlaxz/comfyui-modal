# Batch E19 Single Deployed Cold Validation

Date: 2026-08-17

Scope: one real deployed Modal snapshot-restored request after the E19 atomic
profile repair. This report separates deployment/request success from proof that
the complete E17/E18 loader path executed.

## Final Result

```text
REMOTE_EXECUTION = PASS
DEPLOYMENT_PROOF = PASS
REQUEST_SUCCESS = PASS
CLIP_FAST_LOADER_EXECUTION = PASS
UNET_FAST_LOADER_EXECUTION = FAIL_NOT_EXERCISED
E19_STRUCTURAL_VALIDITY = FAIL
MODEL_READINESS_GATE_MS = UNKNOWN
E19_PERFORMANCE_TARGET = NOT_EVALUATED
```

The deployment and request reached the intended fresh restored container and
produced the expected output. The request did not provide structural proof of
the complete E19 loader: the UNET fastsafetensors path was not exercised, and
the normalized orchestration record contradicts raw CLIP fast-loader events.
No readiness or performance claim is made from this run.

## Budget And Invocation Accounting

```text
FIRST_REMOTE_ATTEMPT = STOPPED_BEFORE_DEPLOYMENT
FIRST_ATTEMPT_REMOTE_DEPLOYS = 0
FIRST_ATTEMPT_PAID_REQUESTS = 0
FIRST_ATTEMPT_CAUSE = atomic profile verifier rejected unrecognized E19 combination

REPAIR = explicit fail-closed E19 atomic deployment profile
ATOMIC_PROFILE_NAME = E19_FINAL_COLD_LOADER
ATOMIC_PROFILE_SELECTOR = V2_E19_FINAL_COLD_LOADER

REMOTE_DEPLOYS_THIS_CONTINUATION = 1
PAID_REQUESTS_THIS_CONTINUATION = 1
TOTAL_REMOTE_DEPLOYS = 1
TOTAL_PAID_REQUESTS = 1
REMOTE_RETRIES_AFTER_SUCCESS = 0
REMOTE_BUDGET_REMAINING = 0

DIRECT_PYTHON_REMOTE_INVOKE_USED = NO
MODAL_RUN_OR_APP_RUN_USED = NO
COMMIT = none
```

The deployment used the canonical `deploy_and_run_v2_single.bat` path with
`V2_BENCHMARK_MODE=normal` and `COMFYMODAL_DEPLOY_ONLY=1`. The default
`snapshot_restore_only` mode is UNET-absent and would have been a no-op for this
full-snapshot validation. The request used `run_v2_single.bat`,
`V2_BENCHMARK_RUNS=1`, and one fresh cache nonce.

## Profile And Identity

The request artifact records the selected profile and the relevant effective
values:

```text
COMFYMODAL_V2_ATOMIC_PROFILE = E19_FINAL_COLD_LOADER
COMFYMODAL_V2_FAST_COLD_ORCHESTRATION = 1
COMFYMODAL_V2_CHECKPOINT_PREWARM = 1
COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS = 4
COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB = 8
COMFYMODAL_V2_UNET_FASTSAFETENSORS = 1
COMFYMODAL_V2_CLIP_FAST_HYDRATION = 1
COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = 1
COMFYMODAL_V2_CRITICAL_GPU_COORDINATION = 1
COMFYMODAL_V2_SCOPED_CUDA_READINESS = 1
COMFYMODAL_V2_STAGED_SAFETENSORS = 0
COMFYMODAL_V2_STAGED_SOURCE_ORDER = 0
COMFYMODAL_V2_CLIP_STAGED_HYDRATION = 0
COMFYMODAL_V2_C9QD_EXTRAS = 0
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET = 0
V2_BENCHMARK_RUNS = 1
```

Fresh deployment state in `.deployed_state.json`:

```text
APP = stable-modal-comfy-v2-restore-only-shadow
ATOMIC_PROFILE = E19_FINAL_COLD_LOADER
DEPLOYMENT_COMBINED_HASH = bad18de02e9141679f88165ce41c9aaf3f42fa0ce1fc3fd32cab62eeab7d1d34
RUNTIME_SHAPE_FINGERPRINT = f504e296c398bdcb2c4c07e2
IMAGE = im-EicsjQw1QNVt5IA6Htyc4N
GPU = RTX-PRO-6000
CPU = 12
MEMORY_MB = 32768
SNAPSHOT_MODEL_ORDER = O0
```

Request identity from `run_0.json` and `summary.json`:

```text
REQUEST_ID = v2-benchmark-0-bebc97ada64a
FRESH = true
RESTORE_COUNT = 1
REQUEST_COUNT = 1
RESTORED_INSTANCE_ID = 8dc0332efa0f4cb5ba653f9c4a9a4aa9
RESTORE_SESSION_ID = 34c8d6b44cc34b3fb3c6c98e73578d1e
CONTAINER_TASK_ID = ta-01M087FEYNDSDH9G5DQ8YFX0KR
CONTAINER_SESSION_ID = a0c160102577426e
REGION = us-east1
```

## Operational Evidence

```text
OUTPUT_SHA256 = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
OUTPUT_BYTES = 3129718
OUTPUT_SIZE = 1088 x 1920
CONDITIONING_CACHE_DECISION = miss_stored
CONDITIONING_CACHE_HITS = 0
CONDITIONING_CACHE_MISSES = 1
CLIP_ENCODE_CALLS = 1
```

The normalized waterfall reports `validation_status=COMPLETE`,
`reconciliation_status=OK`, target `10.0 ms`, residual `4.506265 ms`,
`command_response_ms=52256.471`, and `scheduling_ms=25365.0655`. The raw run
still has an unavailable pre-Python snapshot-restore stage and
`modal_restore_begin_wall_unix_ns=null`; therefore those arithmetic results do
not turn incomplete loader telemetry into a complete timing proof.

## Structural Gate Matrix

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact E19 selector and effective profile | PASS | `run_001_sample.json` effective environment contains the E19 selector values. |
| Fresh deployed identity and one snapshot restore | PASS | Fresh identity, `restore_count=1`, matching app/image/runtime shape, and fresh `.deployed_state.json`. |
| Canonical deployed-app path | PASS | Deployment wrapper constructed `modal deploy -m comfymodal_runtime.modal_app`; no `modal run` or `app.run()`. |
| Output delivery and hash | PASS | One output returned with the recorded SHA-256 asset identity. |
| CLIP fastsafetensors loader | PASS | Raw `clip_fh_hydration_end`: `success=true`, `mode=fastsafetensors_direct_gpu`, `checkpoint_bytes=8044982048`, `file_to_gpu_wall_ms=1855.393`, `zero_copy=true`, `fallback_count=0`. |
| CLIP event ordering | PASS in raw trace | Raw `cuda_copy_event_recorded`, `cuda_copy_event_waited`, and successful bind wait are present. |
| CLIP orchestration summary consistency | CONTRADICTORY | `fast_cold_orchestration` reports `clip_fastsafe_start_at=null`, `clip_copy_event_recorded=false`, and no targeted sync even though the raw CLIP events prove hydration and event calls. |
| UNET fastsafetensors loader | FAIL_NOT_EXERCISED | No `unet_fastsafetensors_pipeline` or UNET fast-loader interval exists; orchestration reports `unet_prefetch_stop_reason=never_started` and null UNET fastsafe fields. |
| UNET actual execution identity | FAIL_NOT_EXERCISED | `unet_runtime_state` is CPU-resident and `unet_first_cuda_op` reports `model_identity=cpu_snapshot`. The enabled flag alone is not execution proof. |
| E18 UNET source fence | NOT_PROVEN | Aggregate `source_fence_valid=true` records no fence failure, but no UNET prefetch/demand loader ran whose physical retirement could be checked. |
| D15 UNET overlap | NOT_PROVEN | `unet_gpu_overlap_with_clip_critical=false`; no UNET fastsafetensors interval exists. |
| Model readiness gate | UNKNOWN | `unet_ready_at` and `model_readiness_gate_ms` are null. Generic `ready` events are prefill/VAE worker events, not the E18 model-readiness gate. |

## Interpretation

The single paid request proves the repaired deployment identity, request path,
snapshot restore, output delivery, and CLIP fast hydration. It does not prove
the complete E19 E17/E18 loader assembly. In particular, the effective profile
left `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=0`, and the request used the CPU
snapshot UNET path instead of the enabled UNET fastsafetensors path.

The raw trace and normalized orchestration record also disagree about CLIP
fastsafe/copy-event fields. The raw trace is retained as evidence of what ran,
but the disagreement makes the structural telemetry contract fail closed.

Because the required model-readiness timestamp was not emitted, the requested
`MODEL_READINESS_GATE <= 4500 ms` test is not evaluated. Treating the 1052.334
ms `unet_first_cuda_op` value or the 47853.6 ms total wall time as the model
readiness gate would be incorrect.

## Local Verification

```text
E19 focused tests after live-state assertion repair = 16 passed
D6/deployment-proof suite = 39 passed
D1 identity suite = 14 passed
PYCOMPILE = PASS
TARGETED_DIFF_CHECK = PASS
```

The E19 test now checks deterministic stale-state fixtures instead of requiring
the live `.deployed_state.json` to remain stale after a successful deployment.
No E17/E18 loader implementation was changed in this continuation.

## Artifacts

```text
RUN_DIR = C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-17_16-04-13
RAW_RUN = ...\run_0.json
NORMALIZED_RUN = ...\run_001_sample.json
SUMMARY = ...\summary.json
DEPLOYED_STATE = .deployed_state.json
DEPLOY_LOG = C:\Users\parla\AppData\Local\Temp\opencode\e19_deploy_full_snapshot.log
INFERENCE_LOG = C:\Users\parla\AppData\Local\Temp\opencode\e19_single_inference.log
PREFLIGHT_LOG = C:\Users\parla\AppData\Local\Temp\opencode\e19_execute_preflight.log
```

No further remote operation is authorized or required for this run. A future
validation would need a new explicit budget and a profile/request that actually
exercises the UNET fast-loader path, plus a fix for the CLIP orchestration
telemetry mismatch before any performance verdict is credible.

## POST-RUN STRUCTURAL + ENCODE-CONTENTION REPAIR

The historical request remains operationally valid but structurally invalid for
the final-loader performance experiment. It proves deployment, request, output,
fresh restore, and raw CLIP fast hydration only. No model-readiness or
performance claim is made.

### Root Causes

1. The E19 request had `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=0`. Startup built
   and retained the normal CPU snapshot UNET, so request execution used
   `cpu_snapshot` rather than the intended first-demand fastsafetensors path.
   `COMFYMODAL_V2_UNET_FASTSAFETENSORS=1` was configuration evidence, not
   execution evidence.
2. The raw CLIP fastsafe/CUDA-event callbacks used the trace request ID while
   the finalized orchestration controller was keyed by the execution context
   request ID. The callback lookup silently missed, leaving false/null
   normalized fields. The normalizer was not the source of the loss.

### Encode Forensics

The raw monotonic trace provides these intervals:

```text
CLIP_FASTSAFE_FILE_TO_GPU_WALL_MS = 1855.393
CLIP_FORWARD = 200898536635 -> 203806784551 = 2908.248 ms
CPU_SNAPSHOT_UNET_DEMAND = 203981216080
CPU_SNAPSHOT_UNET_GPU_LOAD = 203991144040 -> 204954870816 = 963.632 ms
CPU_SNAPSHOT_UNET_FIRST_CUDA_OP = 205035392395
```

The CPU-snapshot UNET load began about `174.432 ms` after the recorded CLIP
forward ended. No complete UNET forward interval or H2D interval exists in the
historical trace. Therefore:

```text
UNET_GPU_OVERLAP_WITH_CLIP_FORWARD = NO (based on available monotonic stamps)
UNET_GPU_OVERLAP_WITH_CLIP_FORWARD_MS = 0.000
ENCODE_SLOWDOWN_CAUSALITY = NOT_SUPPORTED
```

The approximately `2908 ms` CLIP forward is classified as
`DEGRADED` by the project diagnostic thresholds. The trace does not support
assigning that slowdown to overlapping UNET GPU work. Future runs must record
all actual GPU intervals and report this classification without turning it into
an automatic structural failure.

### Structural Repair

The repaired E19 atomic profile now requires:

```text
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1
COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1
COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae
COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0
COMFYMODAL_V2_ENV_PROFILE=inherit
```

After restore, the retained control container may preserve CLIP/VAE and
lightweight metadata, but real UNET weights must be absent. The first UNET
demand must then prove `unet_loader_execution_identity=fastsafetensors`.
`cpu_snapshot`, `native`, `staged`, or fallback identities fail E19 regardless
of enabled flags.

D15 now guards the shared request-scoped `load_models_gpu` UNET activation
boundary in addition to the direct fastsafetensors transfer path. Meta work and
CPU page-cache preparation remain allowed during CLIP critical; all UNET GPU
activation/transfer paths must wait or fail closed.

The future structural gate requires the exact atomic profile, absent snapshot
UNET weights, fresh restore, fastsafe CLIP and UNET execution identities, zero
fallbacks, per-model source fences and retired workers, no prefetch collision,
no UNET GPU overlap with CLIP critical, both CUDA event record/wait pairs,
explicit CLIP and UNET readiness, a deterministic model-readiness gate, and a
matching canonical output SHA. Raw runtime events remain authoritative over
normalized summaries, but contradictory raw/normalized fields fail closed.

No additional remote deploy, Modal run, remote request, or paid workload was
performed for this repair.
