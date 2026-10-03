# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **929,408**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.386 | 301 | 0 |
| `golden_request_setup` | 1.727 | 77 | 2 |
| `golden_clip_load` | 3,762.129 | 183,377 | 137 |
| `golden_clip_forward` | 4,324.751 | 113,226 | 275 |
| `golden_unet_load` | 5,501.703 | 43,043 | 78 |
| `golden_sampler_prepare` | 37.941 | 9,847 | 30 |
| `golden_vae_load` | 628.023 | 155,732 | 166 |
| `golden_sampling` | 4,582.540 | 88,948 | 134 |
| `golden_sampler_tail` | 0.073 | 7 | 0 |
| `golden_vae_decode` | 919.729 | 26,542 | 45 |
| `golden_output` | 228.576 | 854 | 20 |

## `golden_restore`

- Stage wall: **0.386 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **1.727 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1.158 | 0.009 | 3 | `#######################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 1.148 | 1.142 | 3 | `#######################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **3,762.129 ms**
- Calls attributed: **183,377**
- Distinct functions >= 1 ms: **137**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 3,667.647 | 0.019 | 1 | `#################################` | `Thread.run` | `threading.py:964` |
| 3,667.628 | 2,915.352 | 1 | `#################################` | `_worker` | `thread.py:69` |
| 3,652.165 | 3,652.165 | 1 | `#################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 3,652.102 | 0.035 | 1 | `#################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 3,652.063 | 0.019 | 1 | `#################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1001` |
| 3,652.044 | 0.034 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 3,652.010 | 0.044 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 3,651.966 | 0.554 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 3,391.289 | 3.319 | 1 | `###############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 3,351.875 | 1.786 | 120 | `##############################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 3,301.033 | 3,297.666 | 125 | `##############################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 752.264 | 0.623 | 1 | `#######` | `_WorkItem.run` | `thread.py:53` |
| 751.604 | 0.273 | 1 | `#######` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 508.747 | 0.273 | 1 | `#####` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 507.847 | 0.276 | 1 | `#####` | `CLIP.__init__` | `sd.py:237` |
| 420.308 | 0.027 | 1 | `####` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 420.282 | 0.262 | 1 | `####` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 420.019 | 2.318 | 1 | `####` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 417.701 | 0.143 | 1 | `####` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 399.663 | 0.808 | 1 | `####` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 394.989 | 9.636 | 1 | `####` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 385.030 | 221.140 | 1 | `###` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 242.532 | 234.511 | 1 | `##` | `_clip_meta_state_dict_from_header` | `golden_serial.py:2217` |
| 223.874 | 0.042 | 1 | `##` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 223.389 | 222.734 | 1 | `##` | `_parse_layout` | `golden_model_transport.py:304` |
| 213.412 | 8.883 | 1018 | `##` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 166.541 | 18.618 | 81958 | `##` | `Module.named_modules` | `module.py:2845` |
| 119.384 | 16.014 | 3 | `#` | `load` | `__init__.py:274` |
| 107.708 | 0.868 | 126 | `#` | `loads` | `__init__.py:299` |
| 106.841 | 1.502 | 126 | `#` | `JSONDecoder.decode` | `decoder.py:332` |
| 105.346 | 105.346 | 126 | `#` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 58.620 | 58.620 | 1 | `#` | `golden.clip_load.storage_adoption` | `full_execution_trace.py:330` |
| 58.579 | 1.150 | 1 | `#` | `select_and_validate_qd_adoption_scope` | `golden_serial.py:13011` |
| 57.949 | 18.304 | 6647 | `#` | `Module._named_members` | `module.py:2650` |
| 53.449 | 0.776 | 2 | `#` | `CLIP.load_sd` | `sd.py:429` |
| 52.829 | 0.014 | 1 | `#` | `te.<locals>.ZImageTEModel_.__init__` | `z_image.py:39` |
| 52.816 | 0.034 | 1 | `#` | `ZImageTEModel.__init__` | `z_image.py:33` |
| 52.782 | 0.117 | 1 | `#` | `SD1ClipModel.__init__` | `sd1_clip.py:717` |
| 52.525 | 0.038 | 1 | `#` | `Qwen3_4BModel.__init__` | `z_image.py:28` |
| 52.487 | 0.568 | 1 | `#` | `SDClipModel.__init__` | `sd1_clip.py:88` |

_97 more functions omitted._

## `golden_clip_forward`

- Stage wall: **4,324.751 ms**
- Calls attributed: **113,226**
- Distinct functions >= 1 ms: **275**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 11,215.052 | 1.421 | 509 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 11,213.630 | 3.981 | 509 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 4,310.536 | 0.055 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,310.209 | 0.159 | 3 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,309.057 | 0.080 | 3 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,308.380 | 0.022 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 3,410.801 | 0.021 | 1 | `###########################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 3,410.780 | 0.057 | 1 | `###########################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 3,338.892 | 1.473 | 85 | `##########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 3,267.877 | 3,264.922 | 89 | `##########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 3,174.053 | 0.040 | 1 | `#########################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 3,174.012 | 4.117 | 1 | `#########################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 3,169.843 | 0.004 | 1 | `#########################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 3,169.783 | 0.075 | 1 | `#########################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 3,080.086 | 0.008 | 1 | `########################` | `BaseLlama.forward` | `llama.py:998` |
| 3,079.963 | 333.808 | 1 | `########################` | `Llama2_.forward` | `llama.py:824` |
| 1,958.262 | 0.201 | 1 | `###############` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 1,958.062 | 158.885 | 1 | `###############` | `precompute_freqs_cis` | `llama.py:445` |
| 1,760.169 | 880.373 | 285 | `##############` | `SpecialTokensMixin.__getattr__` | `tokenization_utils_base.py:1077` |
| 1,555.023 | 0.021 | 1 | `############` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,554.997 | 0.087 | 1 | `############` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,554.149 | 0.088 | 1 | `############` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,554.060 | 42.954 | 1 | `############` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,511.058 | 0.369 | 1 | `############` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,510.578 | 0.016 | 1 | `############` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,510.503 | 0.026 | 1 | `############` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,510.477 | 0.108 | 1 | `############` | `JITFunction.run` | `jit.py:726` |
| 959.935 | 0.012 | 11 | `########` | `DriverConfig.active` | `driver.py:36` |
| 959.924 | 0.011 | 1 | `########` | `DriverConfig.default` | `driver.py:30` |
| 959.913 | 0.028 | 1 | `########` | `_create_driver` | `driver.py:8` |
| 959.839 | 0.040 | 1 | `########` | `CudaDriver.__init__` | `driver.py:341` |
| 959.771 | 0.038 | 1 | `########` | `CudaUtils.__init__` | `driver.py:100` |
| 950.300 | 0.032 | 10 | `#######` | `Popen.wait` | `subprocess.py:1259` |
| 950.267 | 0.079 | 10 | `#######` | `Popen._wait` | `subprocess.py:2014` |
| 950.174 | 950.174 | 5 | `#######` | `Popen._try_wait` | `subprocess.py:2001` |
| 930.083 | 0.023 | 1 | `#######` | `compile_module_from_file` | `build.py:193` |
| 930.059 | 2.167 | 1 | `#######` | `_compile_so_from_file` | `build.py:157` |
| 927.780 | 0.394 | 1 | `#######` | `_compile_so` | `build.py:132` |
| 917.801 | 0.062 | 1 | `#######` | `_build` | `build.py:60` |
| 913.361 | 0.013 | 1 | `#######` | `check_call` | `subprocess.py:398` |

_235 more functions omitted._

## `golden_unet_load`

- Stage wall: **5,501.703 ms**
- Calls attributed: **43,043**
- Distinct functions >= 1 ms: **78**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 8,709.692 | 0.136 | 9 | `##################################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 4,535.905 | 0.011 | 1 | `############################` | `_WorkItem.run` | `thread.py:53` |
| 4,535.670 | 0.022 | 1 | `############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 4,535.648 | 0.009 | 1 | `############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 4,535.639 | 0.029 | 1 | `############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 4,535.610 | 0.633 | 1 | `############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 4,458.703 | 5.383 | 1 | `############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 4,384.497 | 0.083 | 1 | `###########################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 4,383.401 | 4,383.398 | 10 | `###########################` | `EpollSelector.select` | `selectors.py:451` |
| 4,326.162 | 0.199 | 14 | `###########################` | `Handle._run` | `events.py:78` |
| 4,325.453 | 0.024 | 2 | `###########################` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 4,325.379 | 0.093 | 2 | `###########################` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 4,324.811 | 0.087 | 1 | `###########################` | `_overlap_stage_call` | `golden_serial.py:15533` |
| 1,052.426 | 1.188 | 99 | `#######` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 1,013.024 | 1,010.931 | 99 | `######` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 963.500 | 2.141 | 2 | `######` | `_unet_load_with_worker_stage` | `golden_parallel.py:517` |
| 918.123 | 0.035 | 1 | `######` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 917.662 | 916.720 | 1 | `######` | `_parse_layout` | `golden_model_transport.py:304` |
| 82.808 | 5.242 | 560 | `#` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 41.014 | 5.278 | 4928 | `#` | `deepcopy` | `copy.py:128` |
| 29.538 | 1.012 | 216 | `#` | `_deepcopy_dict` | `copy.py:227` |
| 26.867 | 0.353 | 98 | `#` | `SourceThreadProcess._poll_child` | `golden_source_threads.py:1001` |
| 26.548 | 0.244 | 99 | `#` | `Popen.poll` | `subprocess.py:1233` |
| 26.301 | 26.301 | 99 | `#` | `Popen._internal_poll` | `subprocess.py:1966` |
| 24.945 | 3.084 | 2 | `#` | `SourceThreadProcess.snapshot` | `golden_source_threads.py:1232` |
| 22.998 | 22.998 | 1 | `#` | `golden.unet.assign_adoption` | `full_execution_trace.py:330` |
| 22.967 | 0.250 | 1 | `#` | `BaseModel.load_model_weights` | `model_base.py:358` |
| 22.907 | 22.907 | 1 | `#` | `GoldenModelTransport._views` | `golden_model_transport.py:1910` |
| 22.713 | 0.092 | 1 | `#` | `Module.load_state_dict` | `module.py:2535` |
| 19.416 | 1.819 | 2 | `#` | `_time_weighted_concurrency` | `golden_source_threads.py:589` |
| 17.148 | 17.148 | 736 | `#` | `_time_weighted_concurrency.<locals>.<setcomp>` | `golden_source_threads.py:609` |
| 11.126 | 1.827 | 6022 | `#` | `Module.named_modules` | `module.py:2845` |
| 11.090 | 2.066 | 99 | `#` | `SourceThreadProcess._resolve_ready_block` | `golden_source_threads.py:1036` |
| 9.118 | 0.030 | 7 | `#` | `GoldenTelemetryRecorder.event` | `golden_serial.py:1672` |
| 9.089 | 0.022 | 7 | `#` | `GoldenTelemetryRecorder.event_at` | `golden_serial.py:1675` |
| 8.803 | 5.693 | 352 | `#` | `Module._load_from_state_dict` | `module.py:2350` |
| 8.451 | 1.861 | 99 | `#` | `SourceThreadProcess.claim_ready` | `golden_source_threads.py:1167` |
| 8.262 | 8.262 | 1 | `#` | `golden.unet.binding_validation` | `full_execution_trace.py:330` |
| 8.199 | 1.440 | 1 | `#` | `validate_unet_binding` | `golden_serial.py:12867` |
| 8.026 | 0.754 | 99 | `#` | `GoldenQDTransport.publish` | `golden_qd_transport.py:3099` |

_38 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **37.941 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **30**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 144.738 | 0.404 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 37.989 | 0.685 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 36.593 | 36.593 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 36.567 | 0.067 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 25.935 | 1.124 | 26 | `#######################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 18.869 | 2.079 | 562 | `#################` | `Module.state_dict` | `module.py:2199` |
| 12.038 | 12.024 | 1 | `###########` | `EmptyImage.generate` | `nodes.py:1992` |
| 4.975 | 0.330 | 105 | `####` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 4.596 | 0.014 | 1 | `####` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 4.582 | 0.067 | 1 | `####` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 4.499 | 0.098 | 4 | `####` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 3.818 | 0.100 | 4 | `###` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 3.718 | 0.114 | 1 | `###` | `module_size` | `model_management.py:631` |
| 3.590 | 1.654 | 105 | `###` | `all_tasks` | `tasks.py:42` |
| 3.308 | 0.282 | 60 | `###` | `golden_input_types` | `golden_serial.py:973` |
| 2.815 | 0.122 | 52 | `###` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 2.403 | 0.050 | 34 | `##` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 2.341 | 0.017 | 13 | `##` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 2.321 | 0.048 | 13 | `##` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 2.045 | 2.045 | 1 | `##` | `ImageRotate.execute` | `nodes_images.py:764` |
| 1.854 | 0.291 | 29 | `##` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.675 | 0.052 | 56 | `##` | `classproperty.__get__` | `__init__.py:95` |
| 1.494 | 0.021 | 13 | `#` | `_ComfyNodeBaseInternal.INPUT_IS_LIST` | `_io.py:2111` |
| 1.478 | 1.478 | 562 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 1.472 | 0.083 | 5 | `#` | `_ComfyNodeBaseInternal.GET_SCHEMA` | `_io.py:2181` |
| 1.383 | 0.380 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.301 | 0.366 | 326 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 1.296 | 1.289 | 5 | `#` | `Schema.validate` | `_io.py:1710` |
| 1.046 | 1.046 | 105 | `#` | `current_task` | `tasks.py:35` |
| 1.027 | 0.108 | 39 | `#` | `_ComfyNodeBaseInternal.FINALIZE_SCHEMA` | `_io.py:2173` |

## `golden_vae_load`

- Stage wall: **628.023 ms**
- Calls attributed: **155,732**
- Distinct functions >= 1 ms: **166**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 617.190 | 0.099 | 5 | `#################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 527.798 | 0.013 | 1 | `#############################` | `_WorkItem.run` | `thread.py:53` |
| 527.600 | 0.011 | 1 | `#############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 527.589 | 0.006 | 1 | `#############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 527.583 | 0.007 | 1 | `#############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 527.576 | 0.230 | 1 | `#############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 503.143 | 0.020 | 1 | `###########################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 502.636 | 502.634 | 2 | `###########################` | `EpollSelector.select` | `selectors.py:451` |
| 381.796 | 0.149 | 1 | `#####################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 373.472 | 0.076 | 5 | `####################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 365.054 | 364.929 | 7 | `####################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 261.144 | 0.021 | 2 | `##############` | `prepare_sampling` | `sampler_helpers.py:181` |
| 261.101 | 0.065 | 2 | `##############` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 260.818 | 0.159 | 2 | `##############` | `load_models_gpu` | `model_management.py:909` |
| 257.340 | 0.596 | 2 | `##############` | `LoadedModel.model_load` | `model_management.py:782` |
| 256.692 | 0.006 | 2 | `##############` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 256.686 | 0.234 | 2 | `##############` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 256.312 | 9.949 | 2 | `##############` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 181.759 | 3.153 | 1 | `##########` | `sample_custom` | `sample.py:86` |
| 178.598 | 0.032 | 1 | `##########` | `sample` | `samplers.py:1349` |
| 178.350 | 0.093 | 1 | `##########` | `CFGGuider.sample` | `samplers.py:1276` |
| 178.034 | 0.103 | 1 | `##########` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 176.800 | 0.005 | 1 | `##########` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 176.747 | 1.728 | 1 | `##########` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 124.733 | 0.077 | 2 | `#######` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 118.798 | 0.023 | 1 | `######` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 114.530 | 4.494 | 824 | `######` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 100.879 | 6.876 | 234 | `#####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 93.576 | 93.136 | 1 | `#####` | `_parse_layout` | `golden_model_transport.py:304` |
| 91.621 | 56.691 | 1 | `#####` | `VAE.__init__` | `sd.py:487` |
| 84.728 | 10.650 | 410 | `#####` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 78.596 | 11.579 | 2 | `####` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 71.877 | 24.883 | 4132 | `####` | `get_key_weight` | `model_patcher.py:216` |
| 50.925 | 2.758 | 234 | `###` | `Module._apply` | `module.py:930` |
| 49.590 | 47.629 | 1 | `###` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 49.565 | 8.490 | 24286 | `###` | `Module.named_modules` | `module.py:2845` |
| 36.905 | 24.351 | 4133 | `##` | `get_attr` | `utils.py:995` |
| 33.990 | 33.990 | 1 | `##` | `RK_NoiseSampler.prepare_sigmas` | `rk_noise_sampler_beta.py:785` |
| 33.117 | 32.660 | 410 | `##` | `namedtuple` | `__init__.py:350` |
| 32.764 | 32.764 | 35468 | `##` | `Module.__getattr__` | `module.py:1959` |

_126 more functions omitted._

## `golden_sampling`

- Stage wall: **4,582.540 ms**
- Calls attributed: **88,948**
- Distinct functions >= 1 ms: **134**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 20,307.829 | 1.409 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 4,436.904 | 0.043 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,436.639 | 0.060 | 1 | `#################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,435.799 | 0.069 | 1 | `#################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,435.583 | 0.301 | 1 | `#################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 4,432.789 | 14.632 | 1 | `#################################` | `SharkSampler.main` | `samplers.py:153` |
| 4,187.818 | 0.060 | 1 | `###############################` | `CFGGuider.sample` | `samplers.py:1276` |
| 4,187.603 | 0.052 | 1 | `###############################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 4,187.200 | 0.005 | 1 | `###############################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 4,187.156 | 2.006 | 1 | `###############################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 4,049.069 | 0.845 | 1 | `##############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 4,046.367 | 0.125 | 1 | `##############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 4,046.360 | 1.263 | 73 | `##############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 4,043.950 | 56.151 | 1 | `##############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,436.162 | 5.395 | 17 | `#########################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,429.825 | 1.253 | 17 | `#########################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,427.953 | 0.121 | 17 | `#########################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,427.831 | 0.089 | 17 | `#########################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,427.744 | 0.190 | 17 | `#########################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,427.311 | 0.577 | 17 | `#########################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,426.736 | 0.714 | 17 | `#########################` | `sampling_function` | `samplers.py:609` |
| 2,249.828 | 0.059 | 17 | `#################` | `calc_cond_batch` | `samplers.py:208` |
| 2,249.770 | 0.090 | 17 | `#################` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 2,248.670 | 8.914 | 17 | `#################` | `_calc_cond_batch` | `samplers.py:221` |
| 2,209.909 | 0.154 | 17 | `################` | `BaseModel.apply_model` | `model_base.py:204` |
| 2,209.309 | 3.229 | 17 | `################` | `BaseModel._apply_model` | `model_base.py:211` |
| 2,196.835 | 0.090 | 17 | `################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 2,196.745 | 0.210 | 17 | `################` | `Module._call_impl` | `module.py:1787` |
| 2,196.538 | 2,196.538 | 17 | `################` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 1,176.192 | 2.445 | 17 | `#########` | `cfg_function` | `samplers.py:592` |
| 1,173.750 | 1,172.988 | 17 | `#########` | `LGNoiseInjectionLatent.apply.<locals>.cfg_function` | `noise_injection.py:285` |
| 632.322 | 0.020 | 1 | `#####` | `_WorkItem.run` | `thread.py:53` |
| 632.049 | 0.018 | 1 | `#####` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 632.031 | 0.028 | 1 | `#####` | `_run_overlap_stage_offloaded.<locals>.run` | `golden_serial.py:15424` |
| 630.540 | 0.032 | 2 | `#####` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 630.455 | 0.107 | 2 | `#####` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 629.566 | 0.007 | 1 | `#####` | `Thread.run` | `threading.py:964` |
| 629.559 | 101.751 | 1 | `#####` | `_worker` | `thread.py:69` |
| 281.394 | 72.751 | 10 | `##` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 164.606 | 24.750 | 1016 | `#` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |

_94 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.073 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **919.729 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **45**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 919.388 | 919.388 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 919.359 | 0.034 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 919.273 | 0.042 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 918.925 | 0.022 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 918.732 | 0.031 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 918.701 | 837.815 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 76.663 | 0.093 | 1 | `###` | `load_models_gpu` | `model_management.py:909` |
| 72.188 | 0.019 | 1 | `###` | `LoadedModel.model_load` | `model_management.py:782` |
| 72.135 | 0.003 | 1 | `###` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 72.132 | 0.051 | 1 | `###` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 72.047 | 2.157 | 1 | `###` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 46.985 | 2.700 | 108 | `##` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 38.468 | 10.278 | 108 | `#` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 13.680 | 1.461 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 13.634 | 4.680 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 13.517 | 1.598 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 11.935 | 11.814 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 8.550 | 1.428 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 8.201 | 0.264 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 7.188 | 4.864 | 704 | `#` | `get_attr` | `utils.py:995` |
| 6.837 | 6.837 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 6.309 | 6.309 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 6.120 | 1.068 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 5.334 | 0.530 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 5.057 | 3.061 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 4.629 | 0.774 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 4.206 | 0.255 | 123 | `#` | `module_size` | `model_management.py:631` |
| 4.166 | 0.679 | 108 | `#` | `set_attr` | `utils.py:964` |
| 3.835 | 1.667 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 3.410 | 0.709 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 2.901 | 2.898 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 2.494 | 0.725 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 2.406 | 0.085 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 2.353 | 2.353 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 2.287 | 1.544 | 108 | `#` | `resolve_attr` | `utils.py:958` |
| 2.112 | 0.004 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 2.109 | 0.005 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 2.106 | 0.055 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 1.511 | 0.233 | 234 | `#` | `ModelPatcher._load_list.<locals>.<dictcomp>` | `model_patcher.py:949` |
| 1.285 | 0.081 | 1 | `#` | `free_memory` | `model_management.py:863` |

_5 more functions omitted._

## `golden_output`

- Stage wall: **228.576 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **20**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 352.182 | 0.070 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 188.281 | 0.060 | 1 | `############################` | `Image.save` | `Image.py:2592` |
| 176.024 | 171.970 | 1 | `##########################` | `_encode_tile` | `ImageFile.py:672` |
| 13.303 | 8.298 | 1 | `##` | `fromarray` | `Image.py:3378` |
| 12.002 | 12.002 | 1 | `##` | `preinit` | `Image.py:429` |
| 8.315 | 0.016 | 1 | `#` | `clip` | `fromnumeric.py:2207` |
| 8.299 | 0.029 | 1 | `#` | `_wrapfunc` | `fromnumeric.py:48` |
| 8.270 | 8.270 | 1 | `#` | `_clip` | `_methods.py:96` |
| 5.005 | 0.014 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 4.985 | 0.042 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 4.019 | 0.061 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 3.987 | 0.491 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 3.858 | 3.811 | 1 | `#` | `new` | `Image.py:3193` |
| 3.443 | 3.443 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 2.287 | 0.018 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 2.269 | 2.269 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.311 | 0.008 | 1 | `#` | `_ComfyAPIMixin._start_in_process_backend.<locals>._patched_logger_warning` | `comfyapp.py:18431` |
| 1.303 | 0.013 | 1 | `#` | `Logger.warning` | `__init__.py:1491` |
| 1.261 | 0.011 | 1 | `#` | `Logger._log` | `__init__.py:1610` |
| 1.081 | 1.021 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
