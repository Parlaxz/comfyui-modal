# V2 Full Execution Trace Report

## Trace identity

- **Schema version**: v2-full-trace/1
- **Status**: ready
- **Trace entry count**: 8
- **Trace entry capacity**: 5000
- **Trace truncated**: False
- **Request ID**: test-req-123
- **Session ID**: test-session-456

## Trace completeness

- Total trace events parsed: 7
- Timeline entries: 17
- Function summary entries: 7
- Duplicate groups found: 0
- Semantic duplicate groups: 0
- Wrapper snapshots: 4
- Background survivors: 7
- Overlap intervals: 13

## Runtime configuration

- **duplicate_window_us**: 2000
- **experiment_id**: exp-001
- **request_id**: test-req-123
- **restore_session_id**: restore-789
- **session_id**: test-session-456
- **snapshot_active**: False
- **snapshot_enabled**: True

## Critical timeline

| Start (ms) | End (ms) | Duration (ms) | Owner | Type | PID | TID | Evidence |
|---|---|---|---|---|---|---|---|
| 100.0 | 600.0 | 500.0 | volume_reload:models | semantic_operation | 1 | 1 | session_events |
| 100.0 | 600.0 | 500.0 | volume_reload:models | python_call | 1 | 1 | viztracer |
| 500.0 | 6000.0 | 5500.0 | long_async_init | python_call | 1 | 2 | viztracer |
| 800.0 | 2000.0 | 1200.0 | clip_graph_encode | semantic_operation | 1 | 1 | session_events |
| 800.0 | 2000.0 | 1200.0 | clip_graph_encode | python_call | 1 | 1 | viztracer |
| 1000.0 | 1000.0 | 0.0 | restore_complete | milestone | 1 | 1 | milestones |
| 2000.0 | 2000.0 | 0.0 | request_entry | milestone | 1 | 1 | milestones |
| 2100.0 | 2400.0 | 300.0 | clip_prefill_encode | semantic_operation | 1 | 1 | session_events |
| 3000.0 | 3000.0 | 0.0 | prompt_executor_invoke | milestone | 1 | 1 | milestones |
| 3200.0 | 3250.0 | 50.0 | executor_seed | python_call | 1 | 1 | viztracer |
| 4000.0 | 4300.0 | 300.0 | cachedit_restore_prepare | python_call | 1 | 1 | viztracer |
| 5000.0 | 5000.0 | 0.0 | sampling_start | milestone | 1 | 2 | milestones |
| 5000.0 | 5200.0 | 200.0 | unet_gpu_activation | semantic_operation | 1 | 2 | session_events |
| 5000.0 | 5200.0 | 200.0 | unet_gpu_activation | python_call | 1 | 1 | viztracer |
| 9000.0 | 9050.0 | 50.0 | runtime_state_commit | semantic_operation | 1 | 1 | session_events |
| 9000.0 | 9150.0 | 150.0 | output_encode | python_call | 1 | 1 | viztracer |
| 10000.0 | 10000.0 | 0.0 | trace_stop | milestone | 1 | 2 | milestones |

## Top functions by inclusive time

| Function | Source file | Calls | Inclusive (ms) | Exclusive (ms) | Mean (ms) |
|---|---|---|---|---|---|
| long_async_init | None | 1 | 5500.0 | 5500.0 | 5500.0 |
| clip_graph_encode | None | 1 | 1200.0 | 1200.0 | 1200.0 |
| volume_reload:models | None | 1 | 500.0 | 500.0 | 500.0 |
| cachedit_restore_prepare | None | 1 | 300.0 | 300.0 | 300.0 |
| unet_gpu_activation | None | 1 | 200.0 | 200.0 | 200.0 |
| output_encode | None | 1 | 150.0 | 150.0 | 150.0 |
| executor_seed | None | 1 | 50.0 | 50.0 | 50.0 |

## Top functions by exclusive time

| Function | Source file | Exclusive (ms) | Inclusive (ms) | Calls |
|---|---|---|---|---|
| long_async_init | None | 5500.0 | 5500.0 | 1 |
| clip_graph_encode | None | 1200.0 | 1200.0 | 1 |
| volume_reload:models | None | 500.0 | 500.0 | 1 |
| cachedit_restore_prepare | None | 300.0 | 300.0 | 1 |
| unet_gpu_activation | None | 200.0 | 200.0 | 1 |
| output_encode | None | 150.0 | 150.0 | 1 |
| executor_seed | None | 50.0 | 50.0 | 1 |

## Highest call counts

| Function | Source file | Calls | Inclusive (ms) |
|---|---|---|---|
| long_async_init | None | 1 | 5500.0 |
| clip_graph_encode | None | 1 | 1200.0 |
| volume_reload:models | None | 1 | 500.0 |
| cachedit_restore_prepare | None | 1 | 300.0 |
| unet_gpu_activation | None | 1 | 200.0 |
| output_encode | None | 1 | 150.0 |
| executor_seed | None | 1 | 50.0 |

## Concurrent operations

- Total overlapping intervals detected: 13

| Left | Right | Overlap (ms) | Same thread | Same process |
|---|---|---|---|---|
| long_async_init (L5,0,0,.,0) | clip_graph_encode (L8,0,0,.,0) | 1200.0 | False | True |
| long_async_init (L5,0,0,.,0) | clip_graph_encode (L8,0,0,.,0) | 1200.0 | False | True |
| clip_graph_encode (L8,0,0,.,0) | clip_graph_encode (L8,0,0,.,0) | 1200.0 | True | True |
| volume_reload:models (L1,0,0,.,0) | volume_reload:models (L1,0,0,.,0) | 500.0 | True | True |
| long_async_init (L5,0,0,.,0) | clip_prefill_encode (L2,1,0,0,.,0) | 300.0 | False | True |
| long_async_init (L5,0,0,.,0) | cachedit_restore_prepare (L4,0,0,0,.,0) | 300.0 | False | True |
| long_async_init (L5,0,0,.,0) | unet_gpu_activation (L5,0,0,0,.,0) | 200.0 | True | True |
| long_async_init (L5,0,0,.,0) | unet_gpu_activation (L5,0,0,0,.,0) | 200.0 | False | True |
| unet_gpu_activation (L5,0,0,0,.,0) | unet_gpu_activation (L5,0,0,0,.,0) | 200.0 | False | True |
| volume_reload:models (L1,0,0,.,0) | long_async_init (L5,0,0,.,0) | 100.0 | False | True |
| volume_reload:models (L1,0,0,.,0) | long_async_init (L5,0,0,.,0) | 100.0 | False | True |
| long_async_init (L5,0,0,.,0) | executor_seed (L3,2,0,0,.,0) | 50.0 | False | True |
| runtime_state_commit (L9,0,0,0,.,0) | output_encode (L9,0,0,0,.,0) | 50.0 | True | True |

## CPU ownership by process

| PID | First call (ms) | Last call (ms) | Call count | Threads |
|---|---|---|---|---|
| 1 | 100.0 | 9150.0 | 7 | 2 |

## CPU ownership by native thread

| PID:TID | First call (ms) | Last call (ms) | Call count |
|---|---|---|---|
| 1:1 | 100.0 | 9150.0 | 6 |
| 1:2 | 500.0 | 6000.0 | 1 |

## Background work crossing restore completion

| Name | Type | ID | Started (ms) | Ended (ms) | Duration (ms) | Thread/Task | Evidence |
|---|---|---|---|---|---|---|---|
| long_async_init | python_call |  | 500.0 | 6000.0 | 5500.0 | 2 | viztracer |
| long_async_init | python_call | 6 | 500.0 | 6000.0 | 5500.0 | 2 | viztracer |
| clip_graph_encode | semantic_operation |  | 800.0 | 2000.0 | 1200.0 | 1 | session_events |
| clip_graph_encode | python_call | 1 | 800.0 | 2000.0 | 1200.0 | 1 | viztracer |

## Background work crossing request entry

| Name | Type | ID | Started (ms) | Ended (ms) | Duration (ms) | Thread/Task | Evidence |
|---|---|---|---|---|---|---|---|
| long_async_init | python_call | 6 | 500.0 | 6000.0 | 5500.0 | 2 | viztracer |

## Background work crossing PromptExecutor invoke

| Name | Type | ID | Started (ms) | Ended (ms) | Duration (ms) | Thread/Task | Evidence |
|---|---|---|---|---|---|---|---|
| long_async_init | python_call | 6 | 500.0 | 6000.0 | 5500.0 | 2 | viztracer |

## Background work crossing sampling start

| Name | Type | ID | Started (ms) | Ended (ms) | Duration (ms) | Thread/Task | Evidence |
|---|---|---|---|---|---|---|---|
| long_async_init | python_call | 6 | 500.0 | 6000.0 | 5500.0 | 2 | viztracer |

## Background work crossing trace stop

No background work crossing this boundary.

## Background work crossing trace_stop_boundary

No background work crossing this boundary.

## Duplicate semantic work

No duplicate semantic operations detected.

## Repeated wrapper layers

| Target | Milestone | Depth | Cycles | Multiple origins |
|---|---|---|---|---|
| sample | restore_complete | 2 | False | True |
| model_patcher | restore_complete | 1 | False | False |
| sample | request_entry | 3 | False | True |
| model_patcher | request_entry | 1 | False | False |

## Wrapper changes during the lifecycle

| From | To | Target | Change | Prev depth | Cur depth |
|---|---|---|---|---|---|
| restore_complete | request_entry | sample | identity_change | 2 | 3 |

## Expected versus observed operation counts

| Operation | Expected | Observed | Classification |
|---|---|---|---|
| volume_reload:models | 1 | 2 | above_expected |
| volume_reload:runtime_state | 1 | 0 | expected |
| clip_graph_encode | 1 | 2 | above_expected |
| clip_prefill_encode | not_observed | 1 | above_expected |
| unet_gpu_activation | 1 | 2 | above_expected |
| vae_file_load | 1 | 0 | below_expected |
| cachedit_restore_prepare | 1 | 1 | expected |
| cachedit_request_attach | 0 | 0 | expected |
| res4lyf_restore_prepare | 1 | 0 | below_expected |
| res4lyf_request_parse | 0 | 0 | expected |
| cache_seed | 0 | 0 | expected |
| executor_cache_initialize | 1 | 0 | below_expected |
| output_encode | 1 | 1 | expected |
| certificate_read | 1 | 0 | expected |
| restore_plan_read | 1 | 0 | expected |
| runtime_state_commit | 1 | 1 | expected |
| wrapper_installation_per_target | not_observed | 0 | not_observed |

## PyTorch CPU operator summary

| Operator | Calls | Total (ms) | Self (ms) | Mean (ms) | Max (ms) |
|---|---|---|---|---|---|
| aten::mm | 1 | 5.0 | 5.0 | 5.0 | 5.0 |
| aten::relu | 1 | 2.0 | 2.0 | 2.0 | 2.0 |

## CUDA kernel and memory-copy summary

| Kernel | Category | Calls | Total (ms) | Mean (ms) | Max (ms) | Streams |
|---|---|---|---|---|---|---|
| cudaLaunchKernel | cuda_kernel | 1 | 10.0 | 10.0 | 10.0 | 0 |
| aten::mm | cpu_op | 1 | 5.0 | 5.0 | 5.0 | 0 |
| cudaMemcpyH2D | memory_copy | 1 | 5.0 | 5.0 | 5.0 | 0 |
| cudaMemcpyD2H | memory_copy | 1 | 4.0 | 4.0 | 4.0 | 0 |
| cudaDeviceSynchronize | synchronization | 1 | 3.0 | 3.0 | 3.0 | 0 |
| aten::relu | cpu_op | 1 | 2.0 | 2.0 | 2.0 | 0 |

## Unattributed container CPU

| Timestamp (ms) | Container cores | Process cores | Unattributed cores |
|---|---|---|---|
| 1000.0 | measurement_unavailable | measurement_unavailable | measurement_unavailable |
| 2000.0 | 1.0 | 150.0 | -149.0 |

## Potential optimization artifacts

No structural patterns detected beyond baseline.

## Raw and derived file inventory

| Path | Category | Size (bytes) | SHA-256 |
|---|---|---|---|
| raw/milestones.jsonl | raw | 405 | c4080337db11bda27e11d5356632ba48b2e91fa6c2f5b8f06eb54c36dab98f28 |
| raw/resource_samples.jsonl.gz | raw | 238 | de4cec7c2c4f61d31a95f40da82783a2779e09a0c54355cb06d676923bf2b495 |
| raw/runtime_result_summary.json | raw | 104 | ea14f71dcb1958857a39d74086cfd01de0920c3ac291da23aed883433c1d956c |
| raw/session_events.jsonl | raw | 472 | 6ce39c7bdc4ef63654c008dbfe1a431dbc1ea9181ed97c5eebfc8af56889e1b2 |
| raw/torch_trace.json.gz | raw | 207 | 1ea431c315cc0db80588a8060a524e0c2749e61537c7e345d1533e9c12e66370 |
| raw/trace_config.json | raw | 197 | 0ab92fd2eb8e3e8908fdbac70887abf33e15950e80304013d89f141143ea1c18 |
| raw/viztracer.json.gz | raw | 290 | f17eb1d3135da661854092370806788c2cad57b467dd75149c4045652fd7f768 |
| raw/wrapper_snapshots.json | raw | 405 | 2b1aa123cb9fb8d7b2caee9e06abcd803c44035e06ee79585e5f260b8c6a8968 |
| derived/async_tasks.csv | derived | 161 | 44d52f41e11947e65ed496e966fb0632b1802887d80dba40c55cab4ac41317d9 |
| derived/background_survivors.csv | derived | 695 | 81af4b9159fae54b22351f491582af482a9280790d866d47f6145f1fcd871cf8 |
| derived/calls.csv.gz | derived | 297 | 84b426911580c3903d1ea1251345b19c29eae079810f2c877e1c61fd387e683e |
| derived/critical_timeline.csv | derived | 1308 | a70f01722aefc69264fa26b527a0b8491de50cdd4ca11387f3a4d6f1e5566e01 |
| derived/duplicate_calls.csv | derived | 109 | 1bda1f54f1b791390bdca3b2813c6f0fdc5a7c264b1f7985753c88b6c8049d67 |
| derived/expected_vs_observed.csv | derived | 708 | 1591da09200b65300763f0a1dafdca9133dbbd6b644b89c9e31b1d185334c94d |
| derived/functions_summary.csv | derived | 709 | 6abba02adfc6106dcfcbdbf3e33026fdaaa5d9297d64986f881971073dd8a15d |
| derived/overlap_intervals.csv | derived | 1253 | fa6a27e0b07c9faf3f33013208ce150f20169b8d7aedf1753bffc28fca7f59b7 |
| derived/process_timeline.csv | derived | 91 | ae44038bdb9ef2987d0062db970a600585aba6e6aaf7f38cd646b0cdcdfb63d5 |
| derived/resource_owners.csv | derived | 173 | b086bba772240349bcc8992d52ec4a3360cf1e6c6cf62d55da906b3fdeacff6b |
| derived/semantic_duplicates.csv | derived | 152 | 9508ac1c68755153bc68daf05c2b6c9ec600e3d0e162edf6d3a171a71e028cf4 |
| derived/thread_timeline.csv | derived | 109 | 6944aed00e0180d46c0b25de58d6e77c842b6282725ef16ee8eee54ab7654a29 |
| derived/torch_cpu_ops.csv | derived | 130 | 2210450a87728041989dfca5a93f33f33b087c729cf96191ea1fdcc7d7129da9 |
| derived/torch_cuda_ops.csv | derived | 351 | ad47f70cb6283c11ddf8aed85e0ff578f2f092d4a56e9f45b47c34d745d56e39 |
| derived/wrapper_chains.json | derived | 1086 | 97722c92e2c1e184fe5f54b1f57f23298f19996cb9b26196fa27a145c3ab7d21 |
| derived/wrapper_changes.csv | derived | 131 | b9d5aa9f5a2e96556784ad6c5264aad3fe2543c239a3318499858ba6a7ae29d9 |
