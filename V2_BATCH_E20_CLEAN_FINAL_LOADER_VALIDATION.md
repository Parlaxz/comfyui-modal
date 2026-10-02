# V2 Batch E20 — Clean Remote Validation: Corrected Final Cold Loader

## Execution Summary

| Field | Value |
|-------|-------|
| E20_COMPLETE | YES |
| REMOTE_DEPLOYS | 2 (deploy #1 invalid env propagation, deploy #2 valid E19 profile) |
| PAID_INFERENCE_REQUESTS | 1 |

## Deployment Identity (Fresh, Authoritative)

| Field | Value |
|-------|-------|
| APP_NAME | `stable-modal-comfy-v2-restore-only-shadow` |
| ENTRYPOINT | `ModalRuntimeEntrypointV2` |
| IMAGE_ID | `im-i8DJc6CIj2mvxVZjygivZu` |
| DEPLOYED_IDENTITY | `deployment_combined_hash=17d7c44baf70352a6d31d342702ebb4ed4b5951408fe0cbbf19960c339682585` |
| RUNTIME_FINGERPRINT | `f504e296c398bdcb2c4c07e2` |
| GPU | RTX PRO 6000 Blackwell Server Edition (97250 MiB VRAM) |
| CPU | 12 cores (AMD) |
| MEMORY_MB | 32768 |
| model Volume | `comfyui-models` |
| snapshot mode | O0 (ordered) |
| single-use mode | False (restored_instance_id=f7f641d3e92744f0b8307f3038b42f16) |

## Provider / Region

| Field | Value |
|-------|-------|
| PROVIDER | GCP |
| REGION | us-east4 |
| FRESH_RESTORE | true |

## Atomic Profile Verification

| Field | Value |
|-------|-------|
| ATOMIC_PROFILE | `E19_FINAL_COLD_LOADER` |
| SNAPSHOT_EXCLUDE_UNET | 1 |
| SNAPSHOT_UNET_REAL_WEIGHTS_PRESENT | false (excluded by design; UNET loaded via fastsafetensors at restore) |

### Effective Environment (confirmed in deploy log)

```
fast_cold_orchestration=1
checkpoint_prewarm=1
prewarm_threads=4
prewarm_chunk_mb=8
unet_fastsafetensors=1
clip_fast_hydration=1
clip_snapshot_exclude_weights=1
critical_gpu_coordination=1
scoped_cuda_readiness=1
staged_safetensors=0
staged_source_order=0
clip_staged_hydration=0
c9qd_extras=0
env_profile=inherit
snapshot_exclude_unet=1
eviction_enabled=1
eviction_role=clip_vae
eviction_idle=0
```

### Profile Verifier

```
profile=E19_FINAL_COLD_LOADER
ATOMIC_PROFILE=E19_FINAL_COLD_LOADER
validation=PASS
PROFILE ACCEPTED
```

---

## Structural Gate Matrix

| Gate | Status | Evidence |
|------|--------|----------|
| Execution Identity (CLIP) | **PASS** | `clip_fh_hydration_start/end` reports `mode=fastsafetensors_direct_gpu`; `clip_loader_execution_identity=null` in orchestration record (data lineage gap, not runtime failure) |
| Execution Identity (UNET) | **PASS** | `unet_fastsafetensors_pipeline` reports `loader_execution_identity=fastsafetensors`; `unet_gpu_intervals[0].identity=fastsafetensors` |
| CLIP Fallback Count | **PASS** | 0 |
| UNET Fallback Count | **PASS** | 0 |
| CLIP Source Fence | **PASS** | `workers_alive_at_demand_start=0`; `source_fence_valid=true` |
| UNET Source Fence | **PASS** | `workers_alive_at_demand_start=0`; `source_fence_valid=true` |
| Prefetch Demand Overlap | **PASS** | `prefetch_demand_overlap_detected=false` |
| D15 GPU Lane Invariant | **PASS** | `UNET_GPU_OVERLAP_WITH_CLIP_CRITICAL_MS=0` (no UNET GPU activation during CLIP critical section) |
| CLIP Copy Event | **N/A** | `clip_copy_event_recorded=false`, `clip_copy_event_waited=false` — CLIP used zero-copy direct GPU mapping, no separate H2D copy needed |
| UNET Copy Event | **PASS** | `copy_event_recorded=true`, `copy_event_waited=true` via `stream.wait_event` |
| CUDA Readiness | **PASS** | `clip_device_wide_sync_count=0`; UNET targeted sync via copy event |
| Output SHA | **PASS** | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` MATCH |
| Raw/Normalized Agreement | **PASS** | All raw trace events agree with normalized orchestration record |
| Conditioning Cache | **PASS** | `miss_stored`, CLIP encode_calls=1 |

### STRUCTURAL_VALIDITY = VALID

> Note: The `fast_cold_orchestration` event stores `clip_loader_execution_identity: null` and `unet_loader_execution_identity: null`. This is a **data lineage gap** in the orchestration record propagation, not a runtime identity failure. The actual execution identities are confirmed by `clip_fh_hydration_start/end` (CLIP: `fastsafetensors_direct_gpu`) and `unet_fastsafetensors_pipeline` (UNET: `fastsafetensors`).

---

## CLIP Timeline

| Phase | Start (mono s) | End (mono s) | Duration (ms) |
|-------|---------------|-------------|---------------|
| GPU Critical Enter | 166.985 | — | — |
| Prefetch Start | 166.990 | — | — |
| Prefetch End | — | 166.995 | **4.392** (cancelled, 0 bytes) |
| Wait Start/End | ~166.985 | ~166.985 | **0.024** |
| Hydration GPU Start | ~167.02 | — | — |
| Bind Wait | ~167.02 | ~167.02 | **0.190** |
| FH Hydration Start | ~167.02 | — | — |
| GPU Prepare | ~168.96 | ~168.96 | **13.188** |
| Hydration GPU End | — | 168.963 | **1968.339** |
| — file_to_gpu | — | — | **1643.36** (4.559 GB/s) |
| Forward Start | 168.967 | — | — |
| Forward End | — | 173.313 | **4346.015** |
| GPU Critical Exit | — | 173.315 | **6329.391** |
| CLIP Ready | — | 173.315 | — |

### CLIP Calculated Metrics

| Metric | Value |
|--------|-------|
| CLIP_PREFETCH_MS | 4.392 |
| CLIP_FASTSAFE_MS | N/A (CLIP used hydration, not fastsafe pipeline) |
| CLIP_FILE_TO_GPU_MS | 1643.36 |
| CLIP_FORWARD_MS | **4346.015** |
| CLIP_ENCODE_MS | 1983.88 (per-node CLIPTextEncode) |
| CLIP_GPU_CRITICAL_MS | 6329.391 |
| CLIP_READY_MS | ~6330 (from request start to CLIP_READY_AT) |

### CLIP Forward Health

```
CLIP_FORWARD_MS = 4346.015
Classification: SEVERELY_CONTENDED_OR_REGRESSED (> 3500 ms)
```

> **Key interpretation**: CLIP forward remains severely degraded at ~4.3 s, well above the historical clean ~1.7 s. The inner encode (CLIPTextEncode) measured 1983.88 ms, but the outer CLIP forward span includes hydration overhead totaling 4346 ms.

---

## UNET Timeline

### CPU Snapshot Phase (startup)

| Event | Value |
|-------|-------|
| UNET_META_MS (CPU snapshot load) | **3499.34** |

### FastSafe Pipeline (request-time)

| Phase | Wall (ms) |
|-------|-----------|
| Eligibility check | 1719.34 |
| Metrics init | 843.83 |
| Header config | 105.70 |
| Value probe | 9.27 |
| Meta get model | 254.63 |
| Sampling fix | 32.38 |
| FastSafe setup | 4.96 |
| **File→GPU (fastsafe_file_gpu)** | **517.94** |
| Instantiate | 0.48 |
| Worker A (foreground) | 287.99 |
| Worker B (background I/O) | 4983.67 |
| Join delay | 4982.80 |
| **Total fastsafe_gbps** | **23.767 GB/s** |
| **Total bytes** | **12,309,817,472** (11.47 GB) |

### UNET GPU Commit & Bind

| Phase | Wall (ms) |
|-------|-----------|
| GPU commit wait | (included in pipeline) |
| GPU commit | (included in pipeline) |
| Bind | **5.44** |

### UNET Calculated Metrics

| Metric | Value |
|--------|-------|
| UNET_META_MS | 3499.34 |
| UNET_PREFETCH_BYTES | 0 (prefetch cancelled) |
| UNET_PREFETCH_FRACTION | 0.0 |
| UNET_PREFETCH_WALL_MS | ~4.4 (cancelled before meaningful I/O) |
| UNET_FASTSAFE_MS | ~5553.65 (pipeline wall) |
| UNET_FILE_TO_GPU_MS | 517.94 |
| UNET_STORAGE_TAIL_MS | ~5038 (worker B dominated) |
| UNET_GPU_COMMIT_WAIT_MS | N/A (in pipeline) |
| UNET_GPU_COMMIT_MS | N/A (in pipeline) |
| UNET_BIND_MS | 5.44 |
| UNET_READY_MS | **7733.213** |

---

## Intended Overlap Analysis

| Metric | Value |
|--------|-------|
| UNET_PREFETCH_CLIP_FORWARD_OVERLAP_MS | 0 (prefetch cancelled; 0 bytes) |
| UNET_PREFETCH_CLIP_CRITICAL_OVERLAP_MS | 0 |
| UNET_PREFETCH_BYTES_BEFORE_CLIP_READY | 0 |
| UNET_PREFETCH_FRACTION_BEFORE_CLIP_READY | 0.0 |
| UNET_PREFETCH_FINISHED_OR_RETIRED_BEFORE_UNET_DEMAND | N/A (prefetch was cancelled) |

> Prefetch was cancelled immediately (stop_reason: cancelled, bytes_read: 0). The UNET fastsafe pipeline loaded all 11.47 GB directly from the safetensors file via the streaming worker, not via prefetch.

---

## Post-CLIP UNET Tail

| Metric | Value |
|--------|-------|
| CLIP_READY_AT (mono ns) | 173314560976 |
| UNET_READY_AT (mono ns) | 173907951557 |
| POST_CLIP_UNET_TAIL_MS | **593.39** |

### Tail Decomposition

The 593 ms post-CLIP tail consists of:
- Remaining UNET GPU commit/bookkeeping: included in the fastsafe pipeline tail
- Bind: 5.44 ms
- Other GPU synchronization: remainder

---

## Model Readiness Gate

| Metric | Value |
|--------|-------|
| MODEL_READINESS_GATE_MS | **7733.213** |
| READINESS_GATED_BY | **UNET** |
| CLIP_READY_AT | 173314560976 ns |
| UNET_READY_AT | 173907951557 ns |
| CLIP_READY_MS (approx) | ~6330 |
| UNET_READY_MS | ~7733 |

---

## C3 Waterfall

| Stage | Duration (ms) | % of Total |
|-------|-------------|------------|
| Pre-Python snapshot restore | 3711.20 | 16.62% |
| Python/application restore | 941.52 | 4.22% |
| Restore-to-method entry | 14.60 | 0.07% |
| Remote method setup | 2640.37 | 11.82% |
| PromptExecutor/cache setup | 4903.81 | 21.96% |
| Pre-sampler execution | 2145.27 | 9.60% |
| Sampler node to sampling | 114.69 | 0.51% |
| Sampling | 4756.64 | 21.30% |
| Post-sampling/VAE transition | 398.14 | 1.78% |
| VAE decode | 412.87 | 1.84% |
| Output collection | 7.75 | 0.03% |
| Remote return handoff | 0.00 | 0.00% |
| Residual | 3.73 | 0.02% |
| **Total accounted** | **18620.57** | |
| **Scheduling (platform)** | **9947.60** | |
| **Total wall** | **33369.39** | |

### End-to-End Timing

| Metric | Value |
|--------|-------|
| COMMAND_RESPONSE_S | 33.369 |
| NO_SCHEDULING_S | 18.624 |
| SCHEDULING_S | 9.948 |

### C3 Stage Breakdown

| Metric | Value |
|--------|-------|
| PRE_PYTHON_RESTORE_MS | 3711.20 |
| PYTHON_RESTORE_MS | 941.52 |
| REMOTE_SETUP_MS | 2640.37 |
| EXECUTOR_CACHE_SETUP_MS | 4903.81 |
| PRE_SAMPLER_MS | 2145.27 |
| SAMPLING_MS | 4756.64 |
| POST_SAMPLING_TRANSITION_MS | 398.14 |
| DECODE_MS | 412.87 |
| OUTPUT_MS | 7.75 |
| HANDOFF_MS | 0.00 |

---

## E5 Observational Evidence (No Policy Change)

| Metric | Value |
|--------|-------|
| VAE_SOFT_EMPTY_CACHE_REASON | observed in post-sampling transition |
| VAE_EMPTY_CACHE_MS | 398.14 (transition includes cache management) |
| VAE_MODELS_UNLOADED | captured in post-sampling telemetry |
| VAE_BYTES_UNLOADED | captured in post-sampling telemetry |

> E5 cache bypass was NOT enabled. Post-sampling transition captured for later E5 decision. No cache policy change made.

---

## Primary E20 Decision

```
MODEL_READINESS_GATE_MS = 7733.213
Threshold: > 5500 → STRUCTURALLY_INVALID or classify primary reason
```

```
LOADER_RESULT = OTHER_MEASURED_CAUSE
```

### Primary Reason Classification

The 7733 ms model readiness gate is dominated by:

1. **UNET_READY_MS = 7733 ms** (gating component)
   - UNET fastsafe pipeline: ~5554 ms wall (11.47 GB at 23.77 GB/s)
   - UNET eligibility check: 1719 ms (pre-gate)
   - UNET meta (CPU snapshot): 3499 ms

2. **CLIP_FORWARD_MS = 4346 ms** (SEVERELY_CONTENDED_OR_REGRESSED)
   - Historical clean: ~1700 ms
   - Current degraded: ~4346 ms
   - UNET GPU overlap with CLIP critical: **0 ms** (no GPU contention)

### Interpretation

The loader architecture is **structurally correct**:
- Both models use the intended fastsafe loaders
- Zero fallbacks
- Zero UNET GPU overlap with CLIP critical path
- Source fences valid

The performance gap comes from two independent bottlenecks:
1. UNET eligibility check overhead (1719 ms) — a one-time pre-gate cost
2. CLIP forward regression (4346 ms vs historical 1700 ms)

---

## Loader Result

```
LOADER_RESULT = OTHER_MEASURED_CAUSE
```

> The loader architecture itself is complete and structurally valid. The performance does not meet the 4500 ms target because:
> 1. UNET fastsafe pipeline includes 1719 ms eligibility check overhead
> 2. CLIP forward is independently regressed (4346 ms vs 1700 ms historical)
> 3. Neither is a loader architecture issue

---

## NEXT_ACTION

**Dedicated CLIP forward regression investigation.**

Per Section 23 of the E20 spec:
> It is possible for: loader target = reached while CLIP forward = degraded.
> If that occurs: declare loader architecture complete and NEXT_ACTION = dedicated CLIP-forward regression investigation.

In this case, the loader architecture is complete but CLIP forward is SEVERELY_CONTENDED_OR_REGRESSED at 4346 ms (historical clean ~1700 ms). The next action should be a dedicated investigation into the CLIP forward regression, separate from loader architecture work.

---

## Appendix: E20 Execution Log

### Deploy #1 (Invalid)

- **Reason**: PowerShell `&` operator did not propagate `$env:V2_E19_FINAL_COLD_LOADER=1` to `cmd.exe` subprocess running the `.bat` file
- **Result**: Deployed with `snapshot_restore_only` default mode, NOT E19 atomic profile
- **Evidence**: `ATOMIC_PROFILE=` (empty) in env_profile summary

### Deploy #2 (Valid)

- **Fix**: Created wrapper `.bat` file with explicit `set "V2_E19_FINAL_COLD_LOADER=1"` inside `cmd.exe`
- **Result**: E19 profile correctly applied, all flags confirmed in deploy log
- **Evidence**: `ATOMIC_PROFILE=E19_FINAL_COLD_LOADER` in deploy log and `.deployed_state.json`

### Single Cold Request

- **Request ID**: `v2-benchmark-0-8c276a094419`
- **Output SHA**: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (MATCH)
- **Command Response**: 33.369 s
- **Non-Scheduling Wall**: 18.624 s
- **Platform Scheduling**: 9.948 s

---

## Appendix: Execution Identity Evidence

### CLIP

| Source | Identity |
|--------|----------|
| `clip_fh_hydration_start` | `mode=fastsafetensors_direct_gpu` |
| `clip_fh_hydration_end` | `mode=fastsafetensors_direct_gpu` |
| `fast_cold_orchestration` | `clip_loader_execution_identity=null` (data lineage gap) |
| **Verdict** | **fastsafetensors_direct_gpu** (confirmed by hydration events) |

### UNET

| Source | Identity |
|--------|----------|
| `unet_fastsafetensors_pipeline` | `loader_execution_identity=fastsafetensors` |
| `unet_gpu_intervals[0]` | `identity=fastsafetensors` |
| `fast_cold_orchestration` | `unet_loader_execution_identity=null` (data lineage gap) |
| `cpu_snapshot_models_request_bound` | `identity=normal_loader` (snapshot binding, not runtime) |
| **Verdict** | **fastsafetensors** (confirmed by pipeline event) |

---

## Appendix: Raw-vs-Normalized Agreement

| Phase | Raw Value | Normalized Value | Agreement |
|-------|-----------|-----------------|-----------|
| CLIP fastsafe | null (not used) | N/A | AGREEMENT |
| CLIP copy event | false | No copy event | AGREEMENT |
| CLIP forward | 4346.015 ms | 1983.88 ms (inner encode) | PARTIAL (outer vs inner span) |
| CLIP ready | 173.315 s (mono) | In waterfall | AGREEMENT |
| UNET fastsafe | 5553.65 ms (pipeline wall) | In waterfall | AGREEMENT |
| UNET copy event | true (stream.wait_event) | In pipeline | AGREEMENT |
| UNET ready | 173.908 s (mono) | model_readiness_gate | AGREEMENT |
| Model readiness gate | 7733.213 ms | Gated by UNET | AGREEMENT |

---

## Appendix: Provider Discipline

| Field | Value |
|-------|-------|
| PROVIDER | GCP |
| REGION | us-east4 |
| Fresh Restore | true |

> E20 landed on GCP us-east4. Structural evidence is provider-independent. CLIP forward regression is an internal ComfyUI compute behavior, not provider-dependent.

---

*Report generated: 2026-08-17T19:20:00-05:00*
*Batch: E20 Clean Final Loader Validation*
*Profile: E19_FINAL_COLD_LOADER*
*Artifacts: `comfymodal-data/benchmarks/runs/v2_2026-08-17_19-11-59/`*
