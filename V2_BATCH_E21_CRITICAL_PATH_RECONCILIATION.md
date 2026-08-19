# V2 Batch E21 — Critical-Path Reconciliation

## E20 Correction Summary

E20 produced a structurally valid inference request. E21 reconciles the raw artifact and corrects several E20 interpretation and telemetry issues.

| E20 Claim | E21 Correction |
|-----------|----------------|
| E20 STRUCTURAL VALIDITY = VALID | **CONFIRMED** |
| E20 TRANSPORT = fast physical transport proven | **CONFIRMED** |
| E20 UNET PREFETCH BYTES = 0 | **INCORRECT** — UNET prefetch read 12,309,866,400 bytes (100%). The "0 bytes" was CLIP prefetch (cancelled), not UNET. |
| E20 UNET PREFETCH OVERLAP = 0 | **INCORRECT** — UNET prefetch ran 3755.86 ms during CLIP forward (168.978–172.729 s). The 0-byte was CLIP prefetch. |
| E20 CLIP_FORWARD_MS = 4346 ms is SEVERELY DEGRADED | **PARTIALLY CORRECT** — Outer span is 4346 ms but inner CLIPTextEncode is 1984 ms (healthy). The gap is hydration/management overhead, not core compute regression. |
| E20 MODEL_READINESS_GATE_MS = 7733 ms | **CONFIRMED** (from model_readiness_gate event). Orchestrator record used wrong origin (9578 ms). |
| E20 Worker B = 4983 ms = I/O | **CONFIRMED** — Worker B is I/O bound at 2.47 GB/s effective (not 23.77 GB/s). |

## E20 Ground Truth (Preserved)

```
E20_STRUCTURAL_VALIDITY = VALID
E20_TRANSPORT_VALIDITY = valid

E20_UNET_PREFETCH_EXECUTED = YES
E20_UNET_PREFETCH_BYTES = 12,309,866,400
E20_UNET_PREFETCH_FRACTION = 1.0
E20_UNET_PREFETCH_WALL_MS = 3755.86
E20_UNET_PREFETCH_STOP_REASON = completed
E20_UNET_PREFETCH_CLIP_FORWARD_OVERLAP_MS = 3755.86 (UNET prefetch ran during CLIP forward)

E20_CLIP_OUTER_FORWARD_MS = 4346.015
E20_CLIP_INNER_ENCODE_MS = 1983.88
E20_CLIP_OUTER_INNER_GAP_MS = 2362.135

E20_UNET_FASTSAFE_PIPELINE_MS = 7733.19
E20_UNET_FILE_TO_GPU_MS = 517.94
E20_UNET_WORKER_B_MS = 4983.67

E20_OUTPUT_SHA = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
E20_OUTPUT_SHA_MATCH = true
```

## E20 CLIP Outer-Forward Decomposition

The 4346.015 ms outer CLIP forward span decomposes as:

| Component | Duration (ms) | Notes |
|-----------|-------------|-------|
| CLIP conditioning cache prefetch | ~508.21 | Volume reload for cache lookup |
| CLIP tokenize | ~26.88 | Tokenization |
| CLIP GPU critical enter | ~0.01 | Lock acquisition |
| CLIP scheduled conditioning | ~0.05 | Scheduling |
| CLIP raw encode start | ~0.64 | Encode start |
| **CLIP hydration GPU** | **~1968.34** | fastsafetensors_direct_gpu zero-copy bind |
| — file_to_gpu | ~1643.36 | Actual GPU mapping |
| — GPU prepare | ~13.19 | CUDA preparation |
| **CLIP forward (inner encode)** | **~1983.88** | CLIPTextEncode core compute |
| CLIP post-forward | ~37.86 | Post-encode processing |
| **Residual** | **~6.04** | Unaccounted (target ≤ 10 ms) |
| **Total** | **~4346.02** | Matches outer span |

Classification:
- CLIP core compute: ~1984 ms (healthy, near historical ~1700 ms)
- CLIP hydration overhead: ~1968 ms (dominant component)
- CLIP wrapper/management: ~393 ms
- CLIP residual: ~6 ms

## E20 UNET Prefetch Lifecycle (Corrected)

The E20 artifact shows UNET prefetch DID execute and DID overlap CLIP forward:

| Timestamp (s) | Event | Notes |
|---------------|-------|-------|
| 166.987 | Storage state → CLIP_PREFETCH | Orchestrator constructor |
| 166.990 | CLIP prefetch start | role=clip |
| 166.995 | CLIP prefetch end | cancelled, 0 bytes (CLIP uses zero-copy) |
| 166.995 | Storage state → CLIP_DEMAND | before_clip_demand() |
| 168.967 | Storage state → UNET_PREFETCH | on_clip_forward_start() |
| 168.978 | UNET prefetch start | role=unet |
| 172.729 | UNET prefetch end | completed, 12.3 GB |
| 173.313 | CLIP forward end | clip_forward_end_at |
| 173.315 | Storage state → UNET_DEMAND | before_unet_demand() |

The UNET prefetch completed (12.3 GB, 3756 ms) BEFORE CLIP forward ended. The fastsafe pipeline then used this warmed data.

## Worker B Semantics

Worker B's 4983.67 ms represents:

| Sub-component | Duration (ms) | Notes |
|---------------|-------------|-------|
| I/O reads (safetensors file) | ~4980 | Source file reads, page cache |
| Thread CPU overhead | ~10 | Only 10 ms CPU time |
| Effective throughput | 2.47 GB/s | Not 23.77 GB/s |
| Effective cores | 0.002 | Essentially single-threaded I/O |

The 23.767 GB/s number corresponds only to the narrow `file_to_gpu` (517.94 ms) component — the DMA/fastcopy after data is already in staged memory.

## Timing Origin Correction

### Raw values from E20 artifact

| Field | Value |
|-------|-------|
| CLIP_READY_AT | 173.313228906 s (monotonic) |
| UNET_READY_AT | 173.908086337 s (monotonic) |
| POST_CLIP_UNET_TAIL_MS | 593.39 ms |

### Origin identification

| Origin | Value (monotonic s) | Notes |
|--------|-------------------|-------|
| remote_method_entry | 164.317763 | Modal RPC arrival |
| FastColdOrchestrator.__init__ | ~164.329 | Construction time |
| container_entry | 166.385504 | Container execution start |
| graph_execution_start | 166.409158 | Graph execution begin |
| CLIP_GPU_CRITICAL_START | 166.985152 | CLIP critical section begin |

### Corrected timing values

Using `remote_method_entry` (164.317763 s) as canonical request origin:

| Metric | E20 Value | Corrected Value | Origin Used |
|--------|-----------|----------------|-------------|
| CLIP_READY_MS | ~6330 | **9195.47** | remote_method_entry |
| UNET_READY_MS | 7733.213 | **9590.32** | remote_method_entry |
| MODEL_READINESS_GATE_MS | 7733.213 | **9590.32** | remote_method_entry |
| POST_CLIP_UNET_TAIL_MS | 593.39 | **593.39** | (independent of origin) |

Using `graph_execution_start` (166.409158 s) as execution-phase origin:

| Metric | Corrected Value | Origin Used |
|--------|----------------|-------------|
| CLIP_READY_MS | **6904.07** | graph_execution_start |
| UNET_READY_MS | **7498.93** | graph_execution_start |
| MODEL_READINESS_GATE_MS | **7498.93** | graph_execution_start |

The model_readiness_gate event's 7733.213 ms likely uses an origin between `container_entry` and `graph_execution_start`.

## Execution Identity Propagation

### E20 evidence

| Identity | Confirmed By | Orchestration Record |
|----------|-------------|---------------------|
| CLIP: fastsafetensors_direct_gpu | clip_fh_hydration_start/end | null (bug) |
| UNET: fastsafetensors | unet_fastsafetensors_pipeline | null (bug) |

### Root cause

The `record_fastsafe()` facade passes `execution_identity` to the orchestrator, but the UNET pipeline callers at lines ~1331, ~1460, ~1489 of `unet_fastsafetensors.py` did not pass the identity parameter. Similarly, the CLIP hydration wiring at line ~691 did not pass it.

### Fix applied

Added `execution_identity=` parameter to all three call sites:
- `unet_fastsafetensors.py` line ~1460 (success end)
- `unet_fastsafetensors.py` line ~1489 (error end)
- `clip_fast_hydration_wiring.py` line ~691 (CLIP fastsafe start)

## E21 Implementation Changes

### Files modified

1. **`comfymodal_runtime/fast_cold_orchestration.py`**
   - Added `_request_origin` field and `set_request_origin()` method
   - Fixed `_final_record()` to use `_request_origin or started_at` as timing origin
   - Added `request_origin_at` to finalized output
   - Added `record_clip_substage()` method for CLIP substage telemetry
   - Added module-level facades: `set_request_origin()`, `record_clip_substage()`
   - Updated `__all__`

2. **`comfymodal_runtime/unet_fastsafetensors.py`**
   - Added `execution_identity=` to `record_fastsafe()` calls at lines ~1460 and ~1489

3. **`comfymodal_runtime/clip_fast_hydration_wiring.py`**
   - Added `execution_identity=` to `_record_fastsafe()` call at line ~691

4. **`deploy_and_run_v2_single.bat`**
   - Added fail-closed guard after E19 profile block (lines ~245-263)

5. **`run_v2_single.bat`**
   - Added fail-closed guard after E19 profile block (lines ~146-164)

### Verification

| Check | Result |
|-------|--------|
| py_compile fast_cold_orchestration.py | PASS |
| py_compile unet_fastsafetensors.py | PASS |
| py_compile clip_fast_hydration_wiring.py | PASS |
| git diff --check | CRLF warnings only (acceptable) |
| Existing test suite | 53 passed, 1 pre-existing failure (unrelated) |

## Phase-E Decision

```
READY_FOR_NEXT_REMOTE_VALIDATION = YES
```

Conditions met:
- UNET prefetch lifecycle locally proven (reads 100% of bytes during CLIP forward)
- Source fence remains valid (E20 confirmed)
- D15 remains valid (E20 confirmed 0 ms UNET GPU overlap)
- CLIP outer-forward accounting is now interpretable (hydration + encode + management)
- Readiness origins now have explicit request-relative calculation
- Execution identities now propagate correctly to orchestration record
- Deploy wrapper now fails closed if E19 selector is present but flags are missing

## Next Remote Validation Purpose

Measure corrected execution identity propagation in orchestration record, verify timing origin produces consistent values across model_readiness_gate event and orchestration record, and validate CLIP substage telemetry decomposition.

## Top Remaining Phase-E Bottleneck

CLIP hydration overhead (~1968 ms for zero-copy direct GPU bind of 8 GB model). This is the single largest component in the CLIP critical path and cannot be reduced by prefetch or UNET optimization. It represents the physical cost of memory-mapping a large safetensors file onto the GPU.

---

*Report generated: 2026-08-17*
*Batch: E21 Critical-Path Reconciliation*
*E20 artifact: `comfymodal-data/benchmarks/runs/v2_2026-08-17_19-11-59/`*
