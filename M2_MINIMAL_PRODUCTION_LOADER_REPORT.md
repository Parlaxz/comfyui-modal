# M2 Minimal Production Loader Report

## 1. Exact Implementation Summary

The Golden C0 shell now has an explicit `COMFYMODAL_GOLDEN_CLIP_LOADER=m2`
transport arm. Golden keeps its existing request lifecycle, CLIP construction,
`assign=True` adoption, storage proof, forward, and teardown. Only the CLIP
source/H2D transport is replaced by the canonical M2 mmap/process loader.

## 2. Files/Commits Changed

Primary files changed:

- `comfymodal_runtime/m2_source_core.py`
- `comfymodal_runtime/production_m2_loader.py`
- `comfymodal_runtime/golden_serial.py`
- `comfymodal_runtime/source_race_gpu.py`
- `comfymodal_runtime/source_race_oracle.py`
- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/config_authority.py`
- `config/v2/flag_registry.toml`
- `config/v2/profiles/golden_p1_parallel_m2clip_h100.toml`
- `tools/benchmark_v2_direct.py`
- `tools/v2_control/cli.py`
- `deploy_and_run_v2_single.bat`
- `run_v2_single.bat`
- `tests/test_production_m2_loader.py`

No commit was created because the worktree contains unrelated pre-existing
changes.

## 3. Proof M2 Source Mechanics Were Not Changed

The M2 source contract remains QD4, 64 MiB, four forked readers, 4 ms pacing,
fresh exact-window `MAP_PRIVATE` mappings, and shared staging. The production
adapter now passes the safetensors data-section offset and length explicitly;
header bytes are not transferred to the GPU destination.

## 4. Production Import Reduction

Production imports `m2_source_core` and `source_race_gpu`, not the oracle. Local
cold import of the production module was approximately 68 ms on the host.

## 5. CUDA-Context Lifecycle

Production uses the current PyTorch primary context and verifies driver/current
device identity. It does not call `cuCtxCreate`. The four source children remain
CUDA-sterile.

## 6. Process/Fork/Register Lifecycle

Each CLIP load forks four readers, creates four lazy 64 MiB staging lanes,
registers the staging mapping per load, runs one parent H2D consumer, joins all
readers, drains H2D, and then returns the Golden transport owner.

## 7. Production Telemetry

Production omits child per-operation payloads and transfer start-timing events.
It retains exact coverage, reader completion, H2D completion, and quiescence
state. Golden receives normalized transport stats.

## 8. H2D Correctness

The adapter verifies exact source coverage, transfer count, H2D byte count,
completion coverage, and quiescence before publishing the tensor views.

## 9. GPU Ownership

The destination is one PyTorch-owned contiguous CUDA `uint8` tensor. Raw driver
H2D borrows its pointer. No second model-sized GPU allocation or copy is used.
The owner implements Golden's `release_staging()` contract.

## 10. Safetensors Views

The loader parses the safetensors header, reads only the data section, validates
offsets/dtype/shape/byte lengths, and creates zero-copy CUDA tensor views into
the existing destination allocation.

## 11. Comfy CLIP Proof

The five Golden smoke artifacts reported valid output SHA and Golden storage
adoption proof. The M2 transport event showed exact 120-block coverage and
`h2d_completed_bytes == 8044936192`. The Golden CLIP stage reported
`compute_scope_storage_proven=true` and `compute_ready=true`.

## 12. Five-Run Smoke Table

All five runs were valid Golden artifacts on Testing5/H100 and produced the
expected output SHA. v2ctl's canonical artifact discovery printed a warning for
these runs, but the raw invocation-bound Golden artifacts were preserved.

Raw artifact cohorts:

- `cohort_2026-09-25_21-33-04_8ac0a4`
- `cohort_2026-09-25_21-39-57_dfe383`
- `cohort_2026-09-25_21-41-46_1fc571`
- `cohort_2026-09-25_21-42-50_78f639`
- `cohort_2026-09-25_21-43-53_e725ad`

| run | provider:region | source wall ms | Golden CLIP load wall ms | output |
|---:|---|---:|---:|---|
| 1 | Testing5:unreported | 3478.2 | 4708.0 | exact |
| 2 | Testing5:unreported | 2460.3 | 3203.9 | exact |
| 3 | Testing5:unreported | 3208.2 | 4224.1 | exact |
| 4 | Testing5:unreported | 2907.7 | 3819.6 | exact |
| 5 | Testing5:unreported | 1410.4 | 2318.4 | exact |

Median source wall: **2907.7 ms**.

Median Golden CLIP load wall: **3819.6 ms**.

The requested under-2-second median was **not achieved**. The frozen source
engine produced a median source wall above 2 seconds in this cohort; no source
geometry or pacing change was made to force the target.

A second five-run cohort after enabling the historical CLIP skeleton-overlap
arm produced source walls of `4012.5, 1197.4, 4303.6, 4434.9, 2600.1 ms`
(median `4012.5 ms`) and Golden CLIP stage walls of approximately
`5482.6, 1881.7, 6561.1, 5831.5, 3818.3 ms` (median `5482.6 ms`). The overlap
event was observed and the M2 bind remained correct, but source variance
dominated; overlap cannot hide the source wall.

Diagnostic follow-up on `cohort_2026-09-26_00-20-13_d0498e` showed a fast M2
case: source `1297.1 ms`, GPU-ready `1300.5 ms`, exposed H2D tail `3.4 ms`,
staging waits `0`, fork `257.7 ms`, reader-ready `40.3 ms`, CUDA/register setup
`106.8 ms`, and M2 loader wall `1839.6 ms`. This proves the expected source
capability exists, but also shows the remaining simple-path overhead is above
the 200–300 ms target in this production process topology.

## 13. Provider:Region Breakdown

The deployment was Testing5/H100. Provider and region were not exposed in the
captured Golden summary rows, so no within-region conclusion is claimed.

## 14. Pathological/Outlier Runs

The 4708 ms CLIP-load run is the slowest valid observation and was retained. No
run was removed. The 1410 ms source run demonstrates substantial source variance.

## 15. Before/After Waterfall

Historical M2 representative: function approximately 2141 ms, source 1365 ms,
above-source overhead 776 ms.

This implementation proves the Golden-compatible M2 path and exact adoption, but
the smoke median is 3819.6 ms for CLIP load. The result is not a performance
success against the original target.

## 16. Restore vs Loader Accounting

The CPU loader/configuration module is snapshot-eligible. CUDA context, stream,
events, registration, GPU storage, and source readers are request-time work.
The smoke artifacts do not provide a clean separated restore-to-CLIP median.

## 17. Remaining Unavoidable Overhead

The measured dominant cost is the M2 source span itself, followed by per-load
registration/fork and Golden stage plumbing. The current root parallel executor
also documents that its stages are sequential; the historical sibling C0 shell
had the overlap implementation and should be used for future apples-to-apples
optimization.

The Golden loader selector is read from the deploy-baked environment at
CLIP-load entry rather than copied into a session-level semantic loader
identity. That is sufficient for this arm but should be tightened before a
long-lived production selector is declared complete.

## 18. What Should NOT Be Optimized Next

Do not change M2 geometry, reader count, mmap behavior, pacing, or source
scheduling. Do not add persistent workers or registration yet. First reconcile
the current root with the historical C0 overlap implementation and isolate why
the H100 source span differs from the earlier 1906 ms C0 evidence.

M2 SOURCE ENGINE CHANGED:
NO

SOURCE MEDIAN:
2907.7 ms

GPU-READY MEDIAN:
NOT EXPOSED IN CURRENT GOLDEN SUMMARY

COMFY-USABLE LOADER MEDIAN:
3819.6 ms

ABOVE-SOURCE LOADER OVERHEAD:
911.9 ms median, using Golden CLIP wall minus source wall

RESTORE CUDA SETUP MEDIAN:
NOT SEPARATELY RECONCILED

RESTORE→CLIP-USABLE MEDIAN:
NOT SEPARATELY RECONCILED

ORACLE IMPORT REMOVED FROM PRODUCTION:
YES

SECOND RAW CUDA CONTEXT CREATED:
NO

PER-OP TELEMETRY ON PRODUCTION PATH:
NO

STAGING:
4 lanes x 64 MiB, lazy shared mmap

FORK:
per-load

REGISTRATION:
per-load

H2D EXPOSED TAIL:
not separately exposed; exact H2D completion and quiescence passed

GPU MODEL-SIZED SECOND COPY:
NO

COMFY CLIP FORWARD SUCCESSFUL:
YES, through valid Golden output and adoption proof

EXACT CORRECTNESS:
YES, expected output SHA on all five smoke artifacts

NEXT BIGGEST REMAINING OVERHEAD:
M2 source wall variance; median 2907.7 ms

WOULD PERSISTENT WORKERS/REGISTRATION NOW BE WORTH THE COMPLEXITY:
Not yet. First reconcile the source variance and restore the historical C0
overlap shell in the current root.
