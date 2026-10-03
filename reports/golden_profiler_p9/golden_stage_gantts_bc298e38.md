# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **853,823**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.424 | 301 | 0 |
| `golden_request_setup` | 2.327 | 77 | 2 |
| `golden_clip_load` | 1,918.406 | 180,111 | 147 |
| `golden_clip_forward` | 4,081.834 | 9,432 | 37 |
| `golden_unet_load` | 3,082.906 | 143,509 | 304 |
| `golden_sampler_prepare` | 55.646 | 9,847 | 30 |
| `golden_vae_load` | 819.897 | 155,737 | 173 |
| `golden_sampling` | 4,786.919 | 82,635 | 139 |
| `golden_sampler_tail` | 0.041 | 7 | 0 |
| `golden_vae_decode` | 958.073 | 26,542 | 46 |
| `golden_output` | 251.330 | 854 | 17 |

## `golden_restore`

- Stage wall: **0.424 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **2.327 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1.728 | 0.015 | 3 | `#########################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 1.712 | 1.707 | 3 | `#########################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **1,918.406 ms**
- Calls attributed: **180,111**
- Distinct functions >= 1 ms: **147**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,816.705 | 0.014 | 1 | `################################` | `Thread.run` | `threading.py:964` |
| 1,816.691 | 1,174.951 | 1 | `################################` | `_worker` | `thread.py:69` |
| 1,800.715 | 1,800.715 | 1 | `################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 1,800.652 | 0.042 | 1 | `################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 1,800.606 | 0.022 | 1 | `################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1001` |
| 1,800.584 | 0.029 | 1 | `################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 1,800.555 | 0.058 | 1 | `################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 1,800.496 | 0.755 | 1 | `################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 1,719.828 | 4.114 | 1 | `##############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 1,493.352 | 2.022 | 120 | `##########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 1,319.905 | 1,316.294 | 121 | `#######################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 641.725 | 10.640 | 1 | `###########` | `_WorkItem.run` | `thread.py:53` |
| 631.054 | 0.211 | 1 | `###########` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 565.389 | 0.187 | 1 | `##########` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 564.682 | 0.230 | 1 | `##########` | `CLIP.__init__` | `sd.py:237` |
| 474.370 | 0.023 | 1 | `########` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 474.347 | 0.032 | 1 | `########` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 474.315 | 2.001 | 1 | `########` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 472.314 | 0.263 | 1 | `########` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 450.802 | 2.556 | 1 | `########` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 443.113 | 8.864 | 1 | `########` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 433.974 | 273.152 | 1 | `########` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 208.136 | 10.842 | 1018 | `####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 190.980 | 29.091 | 81958 | `###` | `Module.named_modules` | `module.py:2845` |
| 119.054 | 1.234 | 120 | `##` | `GoldenQDTransport.publish` | `golden_qd_transport.py:3099` |
| 114.707 | 16.324 | 3 | `##` | `load` | `__init__.py:274` |
| 114.442 | 108.536 | 120 | `##` | `TransportDispatcher.publish` | `golden_qd_transport.py:2153` |
| 105.032 | 105.032 | 244 | `##` | `_FileLock.__enter__` | `golden_source_threads.py:486` |
| 102.985 | 0.924 | 126 | `##` | `loads` | `__init__.py:299` |
| 102.060 | 1.605 | 126 | `##` | `JSONDecoder.decode` | `decoder.py:332` |
| 100.457 | 100.457 | 126 | `##` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 97.001 | 3.773 | 120 | `##` | `SourceThreadProcess._resolve_ready_block` | `golden_source_threads.py:1036` |
| 87.674 | 3.121 | 120 | `##` | `SourceThreadProcess.claim_ready` | `golden_source_threads.py:1167` |
| 76.835 | 0.679 | 120 | `#` | `SourceThreadProcess._poll_child` | `golden_source_threads.py:1001` |
| 76.195 | 0.497 | 121 | `#` | `Popen.poll` | `subprocess.py:1233` |
| 75.698 | 75.698 | 121 | `#` | `Popen._internal_poll` | `subprocess.py:1966` |
| 70.306 | 70.306 | 1 | `#` | `golden.clip_load.storage_adoption` | `full_execution_trace.py:330` |
| 70.267 | 1.561 | 1 | `#` | `select_and_validate_qd_adoption_scope` | `golden_serial.py:13011` |
| 68.349 | 20.226 | 6647 | `#` | `Module._named_members` | `module.py:2650` |
| 67.849 | 67.849 | 244 | `#` | `_FileLock.__exit__` | `golden_source_threads.py:493` |

_107 more functions omitted._

## `golden_clip_forward`

- Stage wall: **4,081.834 ms**
- Calls attributed: **9,432**
- Distinct functions >= 1 ms: **37**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 12,512.548 | 1.547 | 508 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 12,511.002 | 3.678 | 508 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 4,071.964 | 0.057 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,069.163 | 0.052 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,068.875 | 0.033 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,068.691 | 0.046 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 3,856.380 | 0.026 | 1 | `################################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 3,856.354 | 0.048 | 1 | `################################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 3,596.212 | 0.063 | 1 | `##############################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 3,596.148 | 3.070 | 1 | `##############################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 3,593.024 | 0.005 | 1 | `##############################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 3,592.962 | 0.131 | 1 | `##############################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 3,492.611 | 0.011 | 1 | `#############################` | `BaseLlama.forward` | `llama.py:998` |
| 3,492.251 | 449.634 | 1 | `#############################` | `Llama2_.forward` | `llama.py:824` |
| 756.602 | 0.072 | 36 | `######` | `prefetch_queue_pop` | `model_prefetch.py:62` |
| 756.534 | 0.145 | 36 | `######` | `Llama2_.forward.<locals>.core` | `llama.py:912` |
| 755.968 | 3.832 | 36 | `######` | `TransformerBlock.forward` | `llama.py:661` |
| 629.671 | 145.156 | 36 | `#####` | `Attention.forward` | `llama.py:540` |
| 416.245 | 2.186 | 252 | `###` | `disable_weight_init.Linear.forward` | `ops.py:570` |
| 412.022 | 355.015 | 252 | `###` | `disable_weight_init.Linear.forward_comfy_cast_weights` | `ops.py:566` |
| 118.882 | 57.386 | 290 | `#` | `rms_norm` | `rmsnorm.py:7` |
| 87.920 | 87.920 | 36 | `#` | `apply_rope` | `llama.py:492` |
| 63.859 | 0.574 | 145 | `#` | `RMSNorm.forward` | `llama.py:436` |
| 63.759 | 2.220 | 36 | `#` | `MLP.forward` | `llama.py:644` |
| 62.065 | 0.052 | 4 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 61.763 | 14.159 | 5 | `#` | `Handle._run` | `events.py:78` |
| 61.493 | 0.010 | 1 | `#` | `_overlap_owner_call` | `golden_serial.py:15543` |
| 55.747 | 0.748 | 252 | `#` | `CastBiasWeightContext.__init__` | `ops.py:464` |
| 55.011 | 52.338 | 252 | `#` | `cast_bias_weight` | `ops.py:337` |
| 31.586 | 31.586 | 36 | `#` | `silu` | `functional.py:2429` |
| 5.787 | 5.787 | 397 | `#` | `cast_to` | `model_management.py:1527` |
| 2.051 | 1.168 | 252 | `#` | `run_every_op` | `ops.py:34` |
| 1.669 | 0.559 | 252 | `#` | `device_supports_non_blocking` | `model_management.py:1319` |
| 1.524 | 0.409 | 355 | `#` | `deepcopy` | `copy.py:128` |
| 1.372 | 1.372 | 1447 | `#` | `Module.__getattr__` | `module.py:1959` |
| 1.077 | 0.432 | 7 | `#` | `_deepcopy_dict` | `copy.py:227` |
| 1.004 | 0.606 | 252 | `#` | `CastBiasWeightContext.__exit__` | `ops.py:475` |

## `golden_unet_load`

- Stage wall: **3,082.906 ms**
- Calls attributed: **143,509**
- Distinct functions >= 1 ms: **304**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 2,793.002 | 0.108 | 3 | `###############################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 2,789.420 | 0.022 | 1 | `###############################` | `_WorkItem.run` | `thread.py:53` |
| 2,789.156 | 0.047 | 1 | `###############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 2,789.109 | 0.023 | 1 | `###############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 2,789.086 | 0.061 | 1 | `###############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 2,789.025 | 1.055 | 1 | `###############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 2,661.170 | 7.145 | 1 | `#############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 2,586.663 | 2,586.659 | 5 | `#############################` | `EpollSelector.select` | `selectors.py:451` |
| 2,586.212 | 0.181 | 1 | `#############################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 2,529.715 | 3.219 | 184 | `############################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 2,330.212 | 2,324.320 | 185 | `##########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 2,185.861 | 0.220 | 1 | `########################` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 2,185.641 | 203.190 | 1 | `########################` | `precompute_freqs_cis` | `llama.py:445` |
| 1,595.408 | 0.027 | 1 | `##################` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,595.376 | 0.062 | 1 | `##################` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,594.032 | 0.145 | 1 | `##################` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,593.887 | 40.944 | 1 | `##################` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,552.844 | 0.552 | 1 | `#################` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,552.136 | 0.008 | 1 | `#################` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,552.047 | 0.040 | 1 | `#################` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,552.008 | 0.153 | 1 | `#################` | `JITFunction.run` | `jit.py:726` |
| 845.762 | 0.008 | 11 | `#########` | `DriverConfig.active` | `driver.py:36` |
| 845.754 | 0.011 | 1 | `#########` | `DriverConfig.default` | `driver.py:30` |
| 845.743 | 0.041 | 1 | `#########` | `_create_driver` | `driver.py:8` |
| 845.620 | 0.031 | 1 | `#########` | `CudaDriver.__init__` | `driver.py:341` |
| 845.569 | 0.049 | 1 | `#########` | `CudaUtils.__init__` | `driver.py:100` |
| 834.262 | 0.030 | 10 | `#########` | `Popen.wait` | `subprocess.py:1259` |
| 834.230 | 0.064 | 10 | `#########` | `Popen._wait` | `subprocess.py:2014` |
| 834.154 | 834.154 | 5 | `#########` | `Popen._try_wait` | `subprocess.py:2001` |
| 817.738 | 0.011 | 1 | `#########` | `compile_module_from_file` | `build.py:193` |
| 817.728 | 2.353 | 1 | `#########` | `_compile_so_from_file` | `build.py:157` |
| 815.300 | 1.070 | 1 | `#########` | `_compile_so` | `build.py:132` |
| 796.786 | 0.061 | 1 | `#########` | `_build` | `build.py:60` |
| 791.417 | 0.013 | 1 | `#########` | `check_call` | `subprocess.py:398` |
| 791.402 | 0.018 | 1 | `#########` | `call` | `subprocess.py:381` |
| 492.914 | 2.668 | 3 | `#####` | `_unet_load_with_worker_stage` | `golden_parallel.py:517` |
| 487.043 | 0.053 | 3 | `#####` | `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` | `_tensor.py:32` |
| 412.882 | 6.954 | 909 | `#####` | `Module.state_dict` | `module.py:2199` |
| 381.174 | 190.908 | 285 | `####` | `SpecialTokensMixin.__getattr__` | `tokenization_utils_base.py:1077` |
| 377.671 | 24.347 | 10 | `####` | `compile` | `_compiler.py:738` |

_264 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **55.646 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **30**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 217.675 | 0.599 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 55.708 | 0.883 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 54.281 | 54.281 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 54.250 | 0.067 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 41.039 | 1.429 | 26 | `#########################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 21.943 | 2.290 | 562 | `#############` | `Module.state_dict` | `module.py:2199` |
| 20.176 | 20.171 | 1 | `############` | `EmptyImage.generate` | `nodes.py:1992` |
| 8.181 | 0.529 | 105 | `#####` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 5.604 | 0.154 | 4 | `###` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 5.464 | 0.010 | 1 | `###` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 5.454 | 0.074 | 1 | `###` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 5.310 | 2.877 | 105 | `###` | `all_tasks` | `tasks.py:42` |
| 5.263 | 5.263 | 1 | `###` | `ConditioningZeroOut.zero_out` | `nodes.py:283` |
| 4.615 | 0.168 | 52 | `###` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 4.430 | 0.128 | 4 | `###` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 4.301 | 0.114 | 1 | `###` | `module_size` | `model_management.py:631` |
| 3.674 | 0.306 | 60 | `##` | `golden_input_types` | `golden_serial.py:973` |
| 2.785 | 0.064 | 34 | `##` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 2.343 | 2.343 | 105 | `#` | `current_task` | `tasks.py:35` |
| 2.279 | 0.359 | 29 | `#` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.963 | 0.022 | 13 | `#` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 1.939 | 0.063 | 13 | `#` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 1.892 | 1.892 | 562 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 1.646 | 0.451 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.616 | 1.615 | 1 | `#` | `ImageRotate.execute` | `nodes_images.py:764` |
| 1.475 | 0.444 | 326 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 1.140 | 0.132 | 39 | `#` | `_ComfyNodeBaseInternal.FINALIZE_SCHEMA` | `_io.py:2173` |
| 1.061 | 0.518 | 1365 | `#` | `WeakSet.__iter__` | `_weakrefset.py:63` |
| 1.058 | 0.804 | 105 | `#` | `all_tasks.<locals>.<setcomp>` | `tasks.py:61` |
| 1.045 | 0.062 | 34 | `#` | `create_input_dict_v1` | `_io.py:1861` |

## `golden_vae_load`

- Stage wall: **819.897 ms**
- Calls attributed: **155,737**
- Distinct functions >= 1 ms: **173**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 809.141 | 0.104 | 5 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 667.777 | 0.015 | 1 | `############################` | `_WorkItem.run` | `thread.py:53` |
| 667.573 | 0.021 | 1 | `############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 667.552 | 0.012 | 1 | `############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 667.545 | 0.017 | 1 | `############################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 667.540 | 0.008 | 1 | `############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 667.532 | 0.273 | 1 | `############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 667.398 | 667.395 | 2 | `############################` | `EpollSelector.select` | `selectors.py:451` |
| 369.011 | 0.021 | 2 | `###############` | `prepare_sampling` | `sampler_helpers.py:181` |
| 368.957 | 0.070 | 2 | `###############` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 368.651 | 0.205 | 2 | `###############` | `load_models_gpu` | `model_management.py:909` |
| 365.277 | 0.050 | 2 | `###############` | `LoadedModel.model_load` | `model_management.py:782` |
| 365.172 | 0.006 | 2 | `###############` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 365.166 | 0.464 | 2 | `###############` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 364.552 | 10.328 | 2 | `###############` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 306.497 | 0.189 | 1 | `#############` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 299.387 | 0.099 | 5 | `############` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 298.613 | 298.471 | 7 | `############` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 224.430 | 3.815 | 1 | `#########` | `sample_custom` | `sample.py:86` |
| 220.607 | 0.045 | 1 | `#########` | `sample` | `samplers.py:1349` |
| 220.182 | 0.122 | 1 | `#########` | `CFGGuider.sample` | `samplers.py:1276` |
| 219.805 | 0.099 | 1 | `#########` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 218.448 | 0.010 | 1 | `#########` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 218.391 | 1.963 | 1 | `#########` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 201.898 | 201.898 | 1 | `########` | `GoldenModelTransport._views` | `golden_model_transport.py:1910` |
| 183.136 | 10.023 | 824 | `########` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 167.591 | 14.449 | 234 | `#######` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 152.216 | 0.205 | 2 | `######` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 144.660 | 32.801 | 410 | `######` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 140.498 | 80.156 | 1 | `######` | `VAE.__init__` | `sd.py:487` |
| 128.500 | 0.037 | 1 | `#####` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 127.967 | 127.507 | 1 | `#####` | `_parse_layout` | `golden_model_transport.py:304` |
| 108.363 | 25.580 | 2 | `####` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 79.514 | 3.391 | 234 | `###` | `Module._apply` | `module.py:930` |
| 78.502 | 26.941 | 4132 | `###` | `get_key_weight` | `model_patcher.py:216` |
| 74.030 | 71.221 | 1 | `###` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 60.519 | 12.678 | 24286 | `###` | `Module.named_modules` | `module.py:2845` |
| 57.840 | 5.248 | 1062 | `##` | `Module.state_dict` | `module.py:2199` |
| 55.534 | 4.495 | 2 | `##` | `RK_NoiseSampler.get_sde_step` | `rk_noise_sampler_beta.py:318` |
| 51.038 | 5.836 | 2 | `##` | `RK_NoiseSampler.get_sde_coeff` | `rk_noise_sampler_beta.py:180` |

_133 more functions omitted._

## `golden_sampling`

- Stage wall: **4,786.919 ms**
- Calls attributed: **82,635**
- Distinct functions >= 1 ms: **139**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 21,500.893 | 1.694 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 4,630.356 | 0.051 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,630.040 | 0.075 | 1 | `#################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,629.065 | 0.198 | 1 | `#################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,628.708 | 0.547 | 1 | `#################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 4,624.824 | 16.890 | 1 | `#################################` | `SharkSampler.main` | `samplers.py:153` |
| 4,316.677 | 0.072 | 1 | `###############################` | `CFGGuider.sample` | `samplers.py:1276` |
| 4,316.398 | 0.061 | 1 | `###############################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 4,315.960 | 0.006 | 1 | `###############################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 4,315.936 | 2.102 | 1 | `###############################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 4,086.738 | 0.817 | 1 | `#############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 4,083.940 | 0.183 | 1 | `#############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 4,083.172 | 0.709 | 73 | `#############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 4,081.187 | 58.997 | 1 | `#############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,472.250 | 4.245 | 17 | `#########################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,466.936 | 1.652 | 17 | `#########################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,464.636 | 0.115 | 17 | `#########################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,464.524 | 0.092 | 17 | `#########################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,464.433 | 0.214 | 17 | `#########################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,463.923 | 0.402 | 17 | `#########################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,463.523 | 0.418 | 17 | `#########################` | `sampling_function` | `samplers.py:609` |
| 2,687.259 | 0.071 | 17 | `###################` | `calc_cond_batch` | `samplers.py:208` |
| 2,687.187 | 0.114 | 17 | `###################` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 2,685.807 | 12.222 | 17 | `###################` | `_calc_cond_batch` | `samplers.py:221` |
| 2,633.914 | 0.199 | 17 | `###################` | `BaseModel.apply_model` | `model_base.py:204` |
| 2,633.194 | 5.560 | 17 | `###################` | `BaseModel._apply_model` | `model_base.py:211` |
| 2,616.653 | 0.120 | 17 | `###################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 2,616.530 | 0.256 | 17 | `###################` | `Module._call_impl` | `module.py:1787` |
| 2,616.276 | 2,616.276 | 17 | `###################` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 828.721 | 0.030 | 2 | `######` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 828.630 | 0.435 | 2 | `######` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 826.580 | 0.011 | 1 | `######` | `Thread.run` | `threading.py:964` |
| 826.569 | 158.780 | 1 | `######` | `_worker` | `thread.py:69` |
| 775.847 | 2.821 | 17 | `######` | `cfg_function` | `samplers.py:592` |
| 773.031 | 771.888 | 17 | `#####` | `LGNoiseInjectionLatent.apply.<locals>.cfg_function` | `noise_injection.py:285` |
| 230.360 | 55.531 | 10 | `##` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 178.151 | 20.681 | 1016 | `#` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |
| 160.636 | 7.645 | 5 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 155.357 | 7.998 | 1008 | `#` | `RK_Method_Beta.a_k_einsum` | `rk_method_beta.py:394` |
| 152.468 | 152.412 | 5 | `#` | `Handle._run` | `events.py:78` |

_99 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.041 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **958.073 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **46**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 957.548 | 957.548 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 957.515 | 0.026 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 957.429 | 0.055 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 956.898 | 0.021 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 956.606 | 0.027 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 956.579 | 848.854 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 99.997 | 0.095 | 1 | `####` | `load_models_gpu` | `model_management.py:909` |
| 91.213 | 0.025 | 1 | `###` | `LoadedModel.model_load` | `model_management.py:782` |
| 91.153 | 0.004 | 1 | `###` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 91.149 | 0.090 | 1 | `###` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 91.020 | 2.080 | 1 | `###` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 60.329 | 4.073 | 108 | `##` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 48.860 | 13.702 | 108 | `##` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 39.936 | 2.415 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 17.482 | 1.722 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 16.398 | 5.734 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 14.690 | 14.551 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 10.445 | 0.420 | 123 | `#` | `module_size` | `model_management.py:631` |
| 10.069 | 0.334 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 9.721 | 1.867 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 8.563 | 5.724 | 704 | `#` | `get_attr` | `utils.py:995` |
| 8.533 | 8.533 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 7.880 | 1.655 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 7.619 | 7.619 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 7.530 | 7.530 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 6.747 | 0.003 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 6.744 | 0.005 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 6.742 | 0.639 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 6.094 | 3.644 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 6.042 | 6.041 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 5.908 | 0.671 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 5.429 | 0.903 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 5.175 | 0.740 | 108 | `#` | `set_attr` | `utils.py:964` |
| 4.730 | 2.311 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 4.127 | 0.717 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 3.297 | 1.022 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 2.935 | 2.036 | 108 | `#` | `resolve_attr` | `utils.py:958` |
| 2.272 | 0.094 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 1.619 | 0.025 | 1 | `#` | `ModelPatcher.get_free_memory` | `model_patcher.py:417` |
| 1.605 | 0.204 | 4 | `#` | `memory_stats` | `memory.py:242` |

_6 more functions omitted._

## `golden_output`

- Stage wall: **251.330 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **17**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 379.973 | 0.082 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 202.510 | 0.102 | 1 | `###########################` | `Image.save` | `Image.py:2592` |
| 189.909 | 185.518 | 1 | `##########################` | `_encode_tile` | `ImageFile.py:672` |
| 13.330 | 7.434 | 1 | `##` | `fromarray` | `Image.py:3378` |
| 12.286 | 12.286 | 1 | `##` | `preinit` | `Image.py:429` |
| 11.435 | 0.034 | 1 | `##` | `clip` | `fromnumeric.py:2207` |
| 11.401 | 0.029 | 1 | `##` | `_wrapfunc` | `fromnumeric.py:48` |
| 11.373 | 11.373 | 1 | `##` | `_clip` | `_methods.py:96` |
| 5.896 | 0.034 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 5.853 | 0.060 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 4.366 | 0.066 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 4.323 | 0.535 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 4.061 | 4.011 | 1 | `#` | `new` | `Image.py:3193` |
| 3.723 | 3.723 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 3.171 | 0.027 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 3.145 | 3.145 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.726 | 1.685 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
