# C9 Bare-Loop Isolation

## Identity

| item | value |
|---|---|
| worktree | `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal` |
| branch | `TESTING2` |
| HEAD | `34827734defec0c0b5f46f20cd166d5ed32e4416` |
| dirty status | dirty; experiment artifacts and pre-existing untracked `07c_c9_torch_pinned_recovery/ALL_SAMPLES_REPORT.md` retained |
| app/deployment | `sept-unetclip-c9-recovery-source-only` on Testing 7 |
| workspace | Testing 7 only; runner rejects any other active workspace |
| CPU | requested and observed 12 |
| GPU | RTX PRO 6000 Blackwell Server Edition; requested `rtx-pro-6000` |
| Torch | `2.14.0+cu130`, CUDA build 13.0 |
| volume/file | read-only `comfyui-models`; `z_image_turbo_bf16.safetensors` |
| geometry | QD8, 8 static disjoint contiguous ranges, one shared FD, 32 MiB reads |

Provider and region are recorded metadata only: all final A/B rows reported
`CLOUD_PROVIDER_GCP` and `us-east1`. They were not used for selection,
stratification, reruns, or interpretation.

Changed files in this lane:

- `c9_recovery_modal.py`
- `comfymodal_runtime/source_ceiling_oracle.py`
- `tools/run_c9_recovery.py`
- `tools/run_c9_isolation.py`
- `tests/test_c9_recovery.py`
- `unetClipExperimentsSeptember/07d_c9_bare_loop_isolation_final/REPORT.md`
- generated raw artifacts under `unetClipExperimentsSeptember/07d_c9_bare_loop_isolation_final/`
- generated raw artifacts under `unetClipExperimentsSeptember/07d_c9_bare_loop_isolation_final_refresh/`
- generated raw artifacts under `unetClipExperimentsSeptember/07d_qd_scaling/`

## Implementation Locations

- Bare Arm A: `comfymodal_runtime/source_ceiling_oracle.py:_run_bare_loop` (line 876).
- Current corrected Arm B: `comfymodal_runtime/source_ceiling_oracle.py:_run_source_only` (line 384), through `_read_source_worker` (line 353), `_read_source_region` (line 245), and `_physical_source_read` (line 169).
- Same-deployment wrapper: `c9_recovery_modal.py:run_c9_recovery` (line 350).
- A/B runner: `tools/run_c9_isolation.py`.
- QD scaling runner: `tools/run_c9_recovery.py`.

## Timing

Both arms allocate all eight pinned Torch buffers and open the shared FD before
one enclosing `time.perf_counter_ns()` call. The timer starts immediately
before the first worker launch and ends after the last worker join. No hashing,
JSON, telemetry, or validation is inside the timed Arm A loop. Exact returned
byte-count validation occurs after the timer. Physical span is derived from
worker-local `first_read_begin_ns` and `last_read_end_ns`; there is no
`physical_span_lock` or shared span lock in the physical read path.

## A/B Raw Runs

The rows below are the original decision-grade 4+4 cohort. After a final
deploy-relevant source edit, the same-deployment test was repeated against the
refreshed Testing 7 deployment. That final-code cohort is recorded separately
below and is the authoritative result for the current worktree.

Artifacts are under `bare_loop/` and `source_only/`. All eight final rows were
structurally eligible.

| arm | run | `THREAD_START_TO_JOIN_WALL_MS` | `PHYSICAL_READ_SPAN_MS` | effective GB/s | provider | region |
|---|---:|---:|---:|---:|---|---|
| bare_loop | 1 | 2354.096527 | 2352.534778 | 5.229105 | CLOUD_PROVIDER_GCP | us-east1 |
| bare_loop | 2 | 2571.320424 | 2569.972304 | 4.787353 | CLOUD_PROVIDER_GCP | us-east1 |
| bare_loop | 3 | 2058.152386 | 2056.053267 | 5.981004 | CLOUD_PROVIDER_GCP | us-east1 |
| bare_loop | 4 | 2301.292115 | 2300.132906 | 5.349089 | CLOUD_PROVIDER_GCP | us-east1 |
| source_only | 1 | 2129.604821 | 2128.051293 | 5.780329 | CLOUD_PROVIDER_GCP | us-east1 |
| source_only | 2 | 1814.745190 | 1813.215781 | 6.783221 | CLOUD_PROVIDER_GCP | us-east1 |
| source_only | 3 | 2354.792915 | 2353.329306 | 5.227558 | CLOUD_PROVIDER_GCP | us-east1 |
| source_only | 4 | 2092.353405 | 2090.928046 | 5.883240 | CLOUD_PROVIDER_GCP | us-east1 |

| arm | median wall ms | median effective GB/s |
|---|---:|---:|
| bare_loop | 2327.694321 | 5.289097 |
| source_only | 2110.979113 | 5.831785 |

Arm A is not materially faster. It is 216.715208 ms slower by median, so the
feature ladder was not run.

## Final-Code Refresh

The refreshed deployment was tested at
`https://modal.com/apps/testing7/main/deployed/sept-unetclip-c9-recovery-source-only`.
Raw artifacts are under
`unetClipExperimentsSeptember/07d_c9_bare_loop_isolation_final_refresh/`.
All eight rows were structurally eligible, with the same Testing 7, CPU12,
RTX PRO 6000, QD8, shared-FD, 32 MiB geometry.

| arm | raw wall ms | median wall ms | median effective GB/s |
|---|---|---:|---:|
| bare_loop | 3337.481271, 2251.286409, 2379.267456, 2447.475041 | 2413.371249 | 5.101692 |
| source_only | 2038.052013, 2349.620396, 2169.475577, 2188.266579 | 2178.871078 | 5.649736 |

The bare loop was 234.500171 ms slower by median. The original conclusion is
unchanged: no feature ladder was justified.

## QD Scaling

The fastest correct implementation from the A/B was the current corrected
oracle (`source_only`). Six valid serial runs were collected for each QD in
`unetClipExperimentsSeptember/07d_qd_scaling/`.

| QD | raw `C9_TOTAL_WALL_MS` values | median ms | median effective GB/s |
|---:|---|---:|---:|
| 2 | 1819.749482, 1638.826213, 1710.896514, 1611.020466, 1692.850695, 4875.586690 | 1701.873605 | 7.2333 |
| 4 | 1921.319841, 1660.864842, 1928.765089, 6824.097759, 1544.012855, 1622.764825 | 1791.092342 | 6.9093 |
| 8 | 2521.462524, 2163.783248, 2234.241396, 2220.947092, 2308.829963, 2076.132426 | 2227.594244 | 5.5261 |

Best observed absolute wall was QD2 run 4 at `1611.020466 ms`; the cohort
median did not beat 1.6 s. QD4 did not beat QD2 and QD8 did not beat QD4.

## Code-Level Arm Difference

Arm A performs only the direct worker loop: compute remaining bytes, choose
`min(32 MiB, remaining)`, call positioned `os.preadv` into the reusable pinned
buffer, advance the offset, and join. It does not call the current read helper,
telemetry object, bounded read-evidence tuples, deque, source mechanism
tracker, or current worker abstraction.

Arm B uses `_read_source_worker` and `_read_source_region`, which call
`_physical_source_read`, maintain bounded read evidence and counters, and
populate worker/result evidence. Those differences did not improve the
measured wall. Both arms use the same FD, ranges, buffer size, pinned Torch
allocation, worker count, syscall, and timer boundary.

Historical `unet_qd_probe.py:406-506` was also checked. Its static path uses
the same positioned `preadv` and static range geometry. Its run timer and
allocation placement are not identical enough to claim a causal parity result,
and no authoritative code/artifact evidence isolates a modern feature as the
source of the remaining loss.

## Answers

1. No. The true bare QD8 loop was not materially faster; the corrected oracle median was lower.
2. Not applicable. No feature ladder was justified because Arm A did not win.
3. The bare QD8 path achieved `2058.152386 ms` minimum and `2327.694321 ms` median in the final A/B.
4. No cohort median beat approximately 1.6 s. The best individual QD2 observation was `1611.020466 ms`.
5. QD4/QD8 did not scale as expected relative to QD2; QD2 was the fastest median.
6. The next single bottleneck is physical source-read completion under the static multi-range `preadv` workload. The measured C9 wall is nearly identical to the physical-read span, so the A/B does not support blaming the current Python oracle abstraction.

## Non-Decision Attempts

The earlier final A/B directory `07d_c9_bare_loop_isolation/` contains one
boundary-invalid cohort: Arm A had buffer allocation outside the timer while
the then-current Arm B allocated in workers. It is retained as non-decision
evidence. The final directory above is the decision-grade 4+4 cohort.
