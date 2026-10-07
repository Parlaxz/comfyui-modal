# Golden Lost Execution Time Audit — 2026-10-07

## Scope and identity
- Canonical source SHA: `4cbc52005909edd0f76aadf97f9adcfbe4b0490e`.
- Deployment fingerprint: `00440b6df4be388452b18566c6b198ba6865e4593b9ab692a8efd8c4c5cdf414`.
- Profile: `golden_p1_parallel_c0_p8_h100`; app: `batch-c0-p8-h100`.
- Workspace: Testing5 (`ws_c1487d319820`). Region: **us-central**. GPU: H100!.
- Expected output SHA: `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`.
- Accepted cohort: six sequential TRUE-COLD runs on deployment version 3. Smoke/retry attempts are retained below and excluded from cohort statistics.

## Lifecycle map and timer definitions
1. Modal platform container/task lifecycle is represented here by machine-readable `TaskGetInfo` (`enqueued_at`, `started_at`, `finished_at`). The dashboard labels `Startup` and `Execution` were not exposed as named fields by the v1.4.3 SDK/API path used by v2ctl; they are therefore `N/A`, not inferred.
2. The earliest application boundary is remote `restore()` first executable line (`remote_python_resume_*`), followed by application restore return (`restore_method_end_*`).
3. `remote_method_entry` and `remote_method_return` are read from Modal task stdout `[v2.golden.outer]` lines; their log-record wall timestamps are used for cross-boundary accounting, while their `t_ns` values remain remote monotonic evidence.
4. `golden_call_wall_ms` is the adapter's `golden_call_start → golden_call_end`, not the whole remote method wall. `golden_outer_ms` is the outer method-entry → method-return interval from task logs.
5. `External restore` is copied adapter restore metadata; its `restore_total_ms` is remote-process `perf_counter`/monotonic duration from `restore()` entry to return. It is not created by `golden_restore()`.
6. Caller timestamps use the host harness process's `time.time_ns` and `time.perf_counter_ns`. The client exposed only a terminal stream result, so first activity is labeled post-stream fallback where intermediate event delivery was not observable.

## Complete lifecycle/code trace
- `comfymodal_runtime/modal_app.py:24222-24254`: outer async-generator wrapper surrounds Golden method invocation, performs final release, and emits the envelope log after stream closure.
- `comfymodal_runtime/modal_app.py:22848-22907`: `run_golden_parallel_stream` marks remote method entry, pre-yield/post-yield seams, and remote method return.
- `comfymodal_runtime/modal_app.py:12328-12367`: `restore()` captures first executable remote resume timestamps and selects minimal Golden restore when enabled.
- `comfymodal_runtime/modal_app.py:12155-12326`: minimal restore performs mutable-state reset, logical GPU repair, source-thread restore setup when deploy-enabled, generation check, and restore-end timestamps.
- `comfymodal_runtime/modal_app.py:23048-23627`: Golden adapter validates request/identity/volume/isolation, ensures GPU readiness, records `golden_call_start`, awaits the Golden executor, and records `golden_call_end`.
- `comfymodal_runtime/golden_parallel.py:379-602`: Golden root and existing marks cover execute entry, restore observation, request setup, CLIP/UNET, sampling/VAE, teardown, persistence, and return arming.
- `comfymodal_runtime/golden_serial.py:10094-10182`: `golden_restore` copies adapter restore metadata and explicitly owns no restore work.
- `tools/benchmark_v2_direct.py:10685-10778,11814-11905`: caller invocation/result/stream-close timestamps and immutable attempt artifacts.
- `tools/v2_control/backend.py:654-780`: v2ctl caller subprocess wall (`started_at`, `ended_at`, `elapsed_seconds`) and identity-bound artifact discovery.

## Platform semantics limitation
`TaskGetInfo` is direct platform evidence, but this report does not relabel `finished_at − started_at` as dashboard `Execution` without a documented semantic mapping. It is reported as **Modal TaskInfo task wall**. Dashboard Startup/Execution values were not programmatically retained by v2ctl or the receipt and no screenshot values were supplied; those cells are N/A.

## Accepted raw rows
| Run | Request | SHA | Task wall ms | Remote outer ms | Exec−outer ms | Pre-method ms | Post-method ms | External restore ms | Unaccounted ms |
|---|---|---|---|---|---|---|---|---|---|
| cohort_2026-10-07_21-04-55_21fd22 | golden-p1-0-3ea7739891b4 | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 18962.957 | 11639.673 | 7323.284 | 289.780 | 7033.505 | 1496.876 | -0.000 |
| cohort_2026-10-07_21-06-04_60f737 | golden-p1-0-98299e667528 | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 23022.189 | 13454.994 | 9567.195 | 55.369 | 9511.826 | 1138.248 | -0.000 |
| cohort_2026-10-07_21-07-46_960e1b | golden-p1-0-70f37f07e7f6 | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 18794.378 | 11116.516 | 7677.862 | 80.219 | 7597.643 | 1082.738 | -0.000 |
| cohort_2026-10-07_21-08-44_f6089a | golden-p1-0-4a46d4c0bc3a | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 19818.612 | 9678.767 | 10139.845 | 139.581 | 10000.264 | 895.321 | 0.000 |
| cohort_2026-10-07_21-09-31_46ae21 | golden-p1-0-0521d7e07cc4 | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 19669.423 | 10318.239 | 9351.184 | 26.246 | 9324.939 | 994.444 | -0.000 |
| cohort_2026-10-07_21-10-35_f68d02 | golden-p1-0-c6d55b5a5cf1 | 3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577 | 16263.367 | 8117.503 | 8145.864 | 39.908 | 8105.956 | 966.749 | 0.000 |


## Excluded/retried raw rows
| Cohort | Request | Deploy fingerprint | Valid | True cold | Reason |
|---|---|---|---|---|---|
| cohort_2026-10-07_20-52-37_9a527f | golden-p1-0-77373330f14e | 0f0956c949aed02f1401faea2b61cd0386e40b06c43774a4a8971e8bed34e988 | true | true | smoke/retry before final deployment |
| cohort_2026-10-07_20-54-36_5402d2 | golden-p1-0-ca5e2d76415a | 0f0956c949aed02f1401faea2b61cd0386e40b06c43774a4a8971e8bed34e988 | true | true | smoke/retry before final deployment |
| cohort_2026-10-07_20-56-34_a26c83 | golden-p1-0-9944d78d7d5b | 4c00248c883fcf94757b818a36d22e76be0bb02e8dbe8bbccb85bcc553243e74 | true | true | smoke/retry before final deployment |
| cohort_2026-10-07_20-59-19_8ab9d3 | golden-p1-0-f88f9b179f1d | 00440b6df4be388452b18566c6b198ba6865e4593b9ab692a8efd8c4c5cdf414 | true | true | smoke after final deployment |


## Summary statistics — accepted N=6
| Metric | N | Mean | Median | SD | Min | Max | p10 | p50 | p90 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Task wall | 6 | 19421.821 | 19316.190 | 2179.976 | 16263.367 | 23022.189 | 17528.873 | 19316.190 | 21420.400 |
| Remote outer | 6 | 10720.948 | 10717.377 | 1816.688 | 8117.503 | 13454.994 | 8898.135 | 10717.377 | 12547.333 |
| Execution−outer | 6 | 8700.873 | 8748.524 | 1139.859 | 7323.284 | 10139.845 | 7500.573 | 8748.524 | 9853.520 |
| Pre-method | 6 | 105.184 | 67.794 | 98.849 | 26.246 | 289.780 | 33.077 | 67.794 | 214.680 |
| Post-method | 6 | 8595.689 | 8715.447 | 1184.930 | 7033.505 | 10000.264 | 7315.574 | 8715.447 | 9756.045 |
| External restore | 6 | 1095.729 | 1038.591 | 214.454 | 895.321 | 1496.876 | 931.035 | 1038.591 | 1317.562 |
| Unaccounted | 6 | -0.000 | -0.000 | 0.000 | -0.000 | 0.000 | -0.000 | -0.000 | 0.000 |

## Per-run reconciliation
The accounting identity is `TaskInfo task wall = pre-method + remote outer + post-method + residual`. These terms use platform task/log wall timestamps; residual is the arithmetic remainder, not a causal attribution.
| Run | Task wall | Pre-method | Remote outer | Post-method | Residual |
|---|---|---|---|---|---|
| cohort_2026-10-07_21-04-55_21fd22 | 18962.957 | 289.780 | 11639.673 | 7033.505 | -0.000 |
| cohort_2026-10-07_21-06-04_60f737 | 23022.189 | 55.369 | 13454.994 | 9511.826 | -0.000 |
| cohort_2026-10-07_21-07-46_960e1b | 18794.378 | 80.219 | 11116.516 | 7597.643 | -0.000 |
| cohort_2026-10-07_21-08-44_f6089a | 19818.612 | 139.581 | 9678.767 | 10000.264 | 0.000 |
| cohort_2026-10-07_21-09-31_46ae21 | 19669.423 | 26.246 | 10318.239 | 9324.939 | -0.000 |
| cohort_2026-10-07_21-10-35_f68d02 | 16263.367 | 39.908 | 8117.503 | 8105.956 | 0.000 |


## Master waterfall / measured boundaries
| Run | TaskInfo wall | Dashboard Startup | Dashboard Execution | Remote outer | External restore | Golden call | Golden stage span | Caller result after invoke | Caller close after result |
|---|---|---|---|---|---|---|---|---|---|
| cohort_2026-10-07_21-04-55_21fd22 | 18962.957 | N/A | N/A | 11639.673 | 1496.876 | 11569.237 | 11505.347 | 26027.279 | 0.878 |
| cohort_2026-10-07_21-06-04_60f737 | 23022.189 | N/A | N/A | 13454.994 | 1138.248 | 13370.209 | 13290.404 | 64449.546 | 0.685 |
| cohort_2026-10-07_21-07-46_960e1b | 18794.378 | N/A | N/A | 11116.516 | 1082.738 | 11049.520 | 10982.374 | 47320.833 | 0.934 |
| cohort_2026-10-07_21-08-44_f6089a | 19818.612 | N/A | N/A | 9678.767 | 895.321 | 9609.513 | 9545.648 | 15567.051 | 0.893 |
| cohort_2026-10-07_21-09-31_46ae21 | 19669.423 | N/A | N/A | 10318.239 | 994.444 | 10239.111 | 10159.865 | 54056.118 | 0.689 |
| cohort_2026-10-07_21-10-35_f68d02 | 16263.367 | N/A | N/A | 8117.503 | 966.749 | 8061.149 | 8004.534 | 14496.226 | 0.886 |


## Existing Golden boundary values
| Run | execute_enter | restore_done | request_setup_done | CLIP begin | CLIP done | CLIP stage | CLIP forward | UNET | Sampling | VAE load | VAE decode |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cohort_2026-10-07_21-04-55_21fd22 | 3.012 | 20.599 | 22.186 | 22.247 | 2755.377 | 2732.589 | 3729.535 | 3926.420 | 3812.269 | 441.930 | 731.985 |
| cohort_2026-10-07_21-06-04_60f737 | 5.383 | 23.553 | 25.893 | 26.003 | 1771.075 | 1744.335 | 5308.625 | 2653.253 | 4164.552 | 396.007 | 1750.832 |
| cohort_2026-10-07_21-07-46_960e1b | 2.906 | 20.344 | 21.768 | 21.820 | 2489.878 | 2467.454 | 3023.120 | 3921.937 | 3740.741 | 571.235 | 559.329 |
| cohort_2026-10-07_21-08-44_f6089a | 3.086 | 20.294 | 21.865 | 21.915 | 1613.420 | 1590.980 | 2333.491 | 3412.133 | 3751.804 | 544.066 | 490.889 |
| cohort_2026-10-07_21-09-31_46ae21 | 4.923 | 22.005 | 24.754 | 24.849 | 1876.532 | 1851.031 | 3314.264 | 2951.349 | 4086.475 | 436.850 | 590.176 |
| cohort_2026-10-07_21-10-35_f68d02 | 2.703 | 18.223 | 19.629 | 19.691 | 1405.622 | 1385.373 | 2150.410 | 2198.814 | 3690.509 | 463.551 | 470.196 |


## Evidence ledger
- Supported: all six accepted attempts have `valid=true`, `true_cold=true`, `restore_count=1`, `request_count=1`, exact output SHA, region `us-central`, and source controls CURRENT / 4 ms launch gap / QD mode CURRENT / QD4 geometry.
- Supported: `External restore` is remote-process restore duration and includes the measured source-thread restore setup on this profile; it is not platform snapshot time.
- Supported: task/log wall accounting bounds the platform task wall relative to remote method outer wall; residuals are explicit.
- Unresolved: Modal dashboard labels Startup and Execution are not retained in machine-readable v2ctl receipts/API fields used here; TaskInfo wall is not silently promoted to those labels.
- Unresolved: the client stream adapter does not expose intermediate first-event timing; caller result timing is direct, first activity is post-stream fallback where labeled.
- Clock limitation: remote monotonic timestamps are only subtracted within the remote process; host monotonic timestamps are only subtracted within the harness; cross-boundary rows use wall timestamps and disclose the limitation.

## Optimization candidates (not changed)
| Candidate | Measured cost | Owner | Essential? | Snapshotable/cacheable/removable? |
|---|---:|---|---|---|
| Source-thread restore setup | See `external_restore_raw.source_thread_restore_setup_ms` per row | application restore | Not established | Requires separate causal experiment; no change here |
| Pre-method interval before Golden call | See `pre_method_ms` | adapter/platform boundary | Not established | Unknown; no change here |
| Post-method interval after remote return | See `post_method_ms` | platform/result handling boundary | Not established | Unknown; no change here |

## Raw evidence
- Per-run attempt/event artifacts: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-lost-execution-audit\artifacts\phase_p1_parallel_golden_v1`.
- Platform TaskInfo and task-log capture retained at `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-lost-execution-audit\reports\GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_platform_raw.json`.
- Deployment receipt: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees\golden-lost-execution-audit\.v2ctl\deployments\receipt_3_00440b6df4be388452b18566c6b198ba6865e4593b9ab692a8efd8c4c5cdf414.json`.

No optimization or source scheduler change was made in this audit.

## Phase 2 — post-method localization

### Static trace

The post-method path is:

`remote_method_return` (`comfymodal_runtime/modal_app.py:22906`) → dynamically installed outer async-generator wrapper `finally` (`modal_app.py:24241-24254`) → `_release_after_stream_complete` (`modal_app.py:20566-20604`) → `_run_pending_production_cleanup` (`modal_app.py:18241-18282`) → `_release_gpu_after_request` (`modal_app.py:7565-7966`) → envelope emission → Modal/framework task finalization.

The release function already owns coarse stages: request samplers, preload workers, legacy workers, activation references, preload/request references, model-management unload, device fallback, model-management cleanup, legacy executor reset, garbage collection, and CUDA cleanup. The Golden profile selected `teardown_mode=minimal`, so model-management unload, device fallback, model-management cleanup, executor reset, garbage collection, and CUDA cleanup were not run in the smoke.

### Cache-clear literal ownership

The literal `[Cache] Cleared all cached merge results (0 entries removed)` was searched literally across the canonical worktree. It has no repository source owner. It appears in Modal task stdout after the application post-method record. `modal_client.clear_cache()` is a local handle-cache operation and does not emit this literal; it is not the owner.

### Instrumented smoke — one run

| Post-method segment | ms | Evidence/owner |
|---|---:|---|
| inner return → outer wrapper finally | 0.082 | `modal_app.py` structured post-method record |
| final release coordinator | 0.769 | `_release_after_stream_complete` / `_release_gpu_after_request` return |
| release sub-stages | <0.350 each | `stage_results`; minimal teardown, no model unload/CUDA cleanup |
| envelope emit | 0.007 | structured post-method record |
| remote return → latest user-code seam | 1.077 | remote log wall timestamps |
| latest user-code seam → TaskInfo finish | **8,616.668** | `TaskGetInfo.finished_at - post_method_record_wall` |
| total post-method | **8,617.745** | `TaskInfo task wall - remote outer wall` |
| observed cache-clear log after latest user seam | 1,447.335 | platform stdout only; no source owner |
| cache-clear log → TaskInfo finish | 7,169.334 | platform/task wall remainder |

Smoke identity: `valid=true`, `true_cold=true`, exact SHA `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`, region `us-central`, H100, CURRENT source policy, 4 ms source launch gap, CURRENT QD mode, and QD4 geometry.

### Causal conclusion

The measured application-owned post-method path is sub-millisecond. The several-second interval begins after the latest user-code seam and remains after the platform cache-clear message. The cache-clear message is therefore a nearby platform/framework event, not proven ownership of the delay.

**Final Phase-2 classification: PLATFORM/FRAMEWORK POST-USER-CODE GAP.** No application cleanup was removed or moved because no application function owns the measured cost. There is no safe application optimization to make in this task.

### Phase-2 before/after and validation

No fix was implemented because ownership was not application-owned. Therefore an after-fix cohort is not applicable. The Phase-1 six-run baseline remains the before reference: TaskInfo wall median 19.316 s, remote outer median 10.717 s, post-method median 8.715 s. The instrumented smoke preserved exactness and true-cold identity; no lifecycle/resource behavior was changed.

The new raw platform/task-log evidence is retained in `reports/GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_platform_raw.json` and `reports/GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_PHASE2_SMOKE_platform_raw.json` in the audit checkout, plus the instrumented smoke's invocation-bound artifacts. No optimization code change was made.

## Phase 3 — surviving-work root-cause check

### Corrected interpretation of Phase 2

The Phase-2 latest synchronous user-code seam did not by itself prove platform ownership. Phase 3 added a direct inventory at `remote_method_return` for asyncio tasks, deferred-commit state, and relevant threads, then followed the same task to `TaskInfo.finished_at`.

### Full Golden vs source-probe differential

| Behavior/resource | Full Golden | Entry/source probe |
|---|---|---|
| Generator method | Yes; `_modal.method(is_generator=True)` | No; ordinary dict method |
| Output encode/assembly | Yes | No |
| Deferred output persistence | Path exists historically, but current `output_durability=off` run had no pending task | No |
| Persistence drain | Transport supports it after early result close; no active drain was observed in this Golden smoke | No |
| Golden teardown/telemetry | Yes | No |
| Release wrapper | Yes | Ordinary method return |
| Background inventory at remote return | Empty pending/relevant set | Not applicable |

### Regression/introduction history

Git history identifies deferred result-first persistence/drain behavior in the e28 critical-path work: `0ba7000b` / equivalent `e4be44ff`, dated 2026-08-18, with later carry-forward commits `a9a05ca9`, `37b041fa`, `bb8687d5`, and `0487ecee`. That history makes persistence a valid hypothesis, but the current measured path did not activate it because output durability was `off` and the remote-return inventory showed no deferred commit task.

### Phase-3 instrumented smoke raw row

| Field | Value |
|---|---:|
| TaskInfo task wall | 17,999.564 ms |
| remote_method_entry → remote_method_return | 10,734.042 ms |
| pre-method | 295.476 ms |
| remote return → latest user seam | 0.837 ms |
| latest user seam → TaskInfo finish | **6,969.208 ms** |
| cache-clear log after latest user seam | 1,953.851 ms |
| cache-clear log → TaskInfo finish | 5,015.357 ms |
| pending asyncio tasks at remote return | `[]` |
| deferred commit pending/task | `false` / absent |
| relevant background threads | `[]` |
| release duration | 0.596 ms |
| teardown mode | minimal; model unload/CUDA cleanup not run |
| exact SHA / true-cold | PASS / PASS |

### Deferred persistence result

Deferred persistence is **rejected as the current tail owner**. Static code proves that a deferred commit/drain exists for other output-durability paths, but the accepted Golden path uses `output_durability=off`; the smoke's remote-return inventory recorded no pending commit task, no persistence drain, and no relevant background thread. No persistence A/B was run because the measured current path had no persistence work to bypass.

### Cache-clear result

The literal cache-clear message is present in platform/task stdout and absent from canonical repository source. It is not emitted by `modal_client.clear_cache()` or a discovered custom-node source file. It is temporally after the latest user seam, but the direct inventory and release result show no corresponding repo-owned work. Its framework owner remains unidentified; it is not safe to delete application code based on this message.

### Phase-3 causal classification

At `remote_method_return`, the Golden process had no pending relevant asyncio tasks, no deferred commit task, and no relevant background threads. The outer wrapper then completed its release/envelope path in under 1 ms. The remaining 6.969 s is therefore bounded after the last measured repo-owned execution/resource boundary. No application cleanup fix is justified by the evidence, and no A/B removal was performed.

**Phase-3 final classification: unresolved post-user-code/task-finalization gap, with repo-owned background work directly falsified for the measured path.** The cache-clear platform message remains an observation, not an attribution.

Raw Phase-3 evidence is retained at `reports/GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_PHASE2_SMOKE_platform_raw.json`, `reports/GOLDEN_LOST_EXECUTION_TIME_AUDIT_OCT07_PHASE3_SMOKE_platform_raw.json`, and the invocation-bound smoke artifacts. No source/model/output behavior was changed.

### Recent profiler evidence (six runs)

The existing profiler artifacts in `reports/golden_profiler_p9/` and `reports/golden_profiler_p9opt/` were inspected without new GPU calls:

| Profiler set | Trace | `modal_app._wrapper` traced wall | Relevant finding |
|---|---|---:|---|
| P9 | `4d2d4d5a` | 2,108.614 ms | outer wrapper is traced, but no 7–10 s post-task owner |
| P9 | `b94149a5` | 1,341.163 ms | same |
| P9 | `bc298e38` | 1,398.627 ms | same |
| P9opt | `ddb6c39a` | 1,630.776 ms | same |
| P9opt | `ad2f1cf4` | 1,313.539 ms | same |
| P9opt | `25172b0c` | 1,126.898 ms | same |

Across those traces, `GoldenQDTransport.finalize_external_ready`/`drain` are at most tens of milliseconds in the relevant call trees; no deferred persistence finalizer or application release function spans the measured 7–10 s tail. `EpollSelector.select` appears as blocking wait inside traced stage/worker activity, not as a post-return owner. The profiler README explicitly states that traced walls are heavily inflated, Python-frame-only, and stage-scoped; it is ranking evidence, not a measurement of the TaskInfo post-method tail.

Profiler conclusion: these six runs do not identify an application owner for the remaining tail and do not justify an optimization change. They reinforce that the expensive inner Golden stages are separate from the post-return TaskInfo interval.
