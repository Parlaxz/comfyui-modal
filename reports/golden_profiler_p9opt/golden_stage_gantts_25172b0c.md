# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **877,779**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.373 | 301 | 0 |
| `golden_request_setup` | 1.742 | 77 | 2 |
| `golden_clip_load` | 1,734.025 | 185,178 | 148 |
| `golden_clip_forward` | 3,061.859 | 9,432 | 34 |
| `golden_unet_load` | 2,414.227 | 149,164 | 280 |
| `golden_sampler_prepare` | 55.993 | 9,847 | 31 |
| `golden_vae_load` | 554.772 | 156,043 | 157 |
| `golden_sampling` | 4,267.430 | 83,787 | 123 |
| `golden_sampler_tail` | 0.045 | 7 | 0 |
| `golden_vae_decode` | 719.073 | 26,542 | 42 |
| `golden_output` | 243.623 | 854 | 17 |

## `golden_restore`

- Stage wall: **0.373 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **1.742 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1.146 | 0.014 | 3 | `######################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 1.132 | 1.127 | 3 | `######################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **1,734.025 ms**
- Calls attributed: **185,178**
- Distinct functions >= 1 ms: **148**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,659.970 | 0.026 | 2 | `#################################` | `Thread.run` | `threading.py:964` |
| 1,640.235 | 1,066.991 | 1 | `################################` | `_worker` | `thread.py:69` |
| 1,625.644 | 1,625.644 | 1 | `################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 1,625.589 | 0.030 | 1 | `################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 1,625.555 | 0.018 | 1 | `################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` |
| 1,625.537 | 0.025 | 1 | `################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 1,625.512 | 0.087 | 1 | `################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 1,625.424 | 0.570 | 1 | `################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 1,527.512 | 3.814 | 1 | `##############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 1,375.666 | 1.850 | 120 | `###########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 1,212.367 | 1,209.146 | 121 | `########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 573.232 | 8.147 | 1 | `###########` | `_WorkItem.run` | `thread.py:53` |
| 565.063 | 0.163 | 1 | `###########` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 518.444 | 0.161 | 1 | `##########` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 517.836 | 0.254 | 1 | `##########` | `CLIP.__init__` | `sd.py:237` |
| 428.669 | 0.015 | 1 | `########` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 428.654 | 0.255 | 1 | `########` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 428.400 | 2.795 | 1 | `########` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 425.604 | 0.116 | 1 | `########` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 406.341 | 0.929 | 1 | `########` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 400.987 | 6.336 | 1 | `########` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 394.214 | 239.758 | 1 | `########` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 205.380 | 9.067 | 1018 | `####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 155.762 | 17.293 | 81958 | `###` | `Module.named_modules` | `module.py:2845` |
| 118.224 | 13.888 | 3 | `##` | `load` | `__init__.py:274` |
| 109.151 | 0.826 | 127 | `##` | `loads` | `__init__.py:299` |
| 108.331 | 1.281 | 127 | `##` | `JSONDecoder.decode` | `decoder.py:332` |
| 107.041 | 107.041 | 127 | `##` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 102.267 | 102.267 | 244 | `##` | `_FileLock.__enter__` | `golden_source_threads.py:494` |
| 97.597 | 3.341 | 120 | `##` | `SourceThreadProcess._resolve_ready_block` | `golden_source_threads.py:1044` |
| 89.190 | 2.911 | 120 | `##` | `SourceThreadProcess.claim_ready` | `golden_source_threads.py:1175` |
| 73.832 | 73.832 | 244 | `#` | `_FileLock.__exit__` | `golden_source_threads.py:501` |
| 65.555 | 0.512 | 120 | `#` | `SourceThreadProcess._poll_child` | `golden_source_threads.py:1009` |
| 65.075 | 0.352 | 121 | `#` | `Popen.poll` | `subprocess.py:1233` |
| 64.728 | 64.728 | 121 | `#` | `Popen._internal_poll` | `subprocess.py:1966` |
| 59.866 | 0.936 | 2 | `#` | `CLIP.load_sd` | `sd.py:429` |
| 58.728 | 58.728 | 1 | `#` | `golden.clip_load.storage_adoption` | `full_execution_trace.py:330` |
| 58.678 | 1.369 | 1 | `#` | `select_and_validate_qd_adoption_scope` | `golden_serial.py:13060` |
| 57.224 | 18.447 | 6647 | `#` | `Module._named_members` | `module.py:2650` |
| 50.599 | 0.075 | 2 | `#` | `GoldenModelTransport.inspect` | `golden_model_transport.py:999` |

_108 more functions omitted._

## `golden_clip_forward`

- Stage wall: **3,061.859 ms**
- Calls attributed: **9,432**
- Distinct functions >= 1 ms: **34**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 9,485.805 | 1.227 | 508 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 9,484.603 | 2.567 | 508 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 3,052.678 | 0.035 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 3,050.556 | 0.053 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 3,050.237 | 0.025 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 3,050.072 | 0.022 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 3,024.719 | 0.021 | 1 | `##################################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 3,024.698 | 0.038 | 1 | `##################################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 2,850.638 | 0.037 | 1 | `################################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 2,850.601 | 27.347 | 1 | `################################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 2,823.211 | 0.003 | 1 | `###############################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 2,823.170 | 0.074 | 1 | `###############################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 2,687.752 | 0.009 | 1 | `##############################` | `BaseLlama.forward` | `llama.py:998` |
| 2,687.618 | 261.547 | 1 | `##############################` | `Llama2_.forward` | `llama.py:824` |
| 504.765 | 0.053 | 36 | `######` | `prefetch_queue_pop` | `model_prefetch.py:62` |
| 504.716 | 0.109 | 36 | `######` | `Llama2_.forward.<locals>.core` | `llama.py:912` |
| 504.312 | 2.194 | 36 | `######` | `TransformerBlock.forward` | `llama.py:661` |
| 427.484 | 95.718 | 36 | `#####` | `Attention.forward` | `llama.py:540` |
| 274.370 | 1.314 | 252 | `###` | `disable_weight_init.Linear.forward` | `ops.py:570` |
| 271.994 | 258.713 | 252 | `###` | `disable_weight_init.Linear.forward_comfy_cast_weights` | `ops.py:566` |
| 75.093 | 36.575 | 290 | `#` | `rms_norm` | `rmsnorm.py:7` |
| 62.983 | 62.983 | 36 | `#` | `apply_rope` | `llama.py:492` |
| 58.246 | 0.041 | 4 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 57.981 | 14.171 | 5 | `#` | `Handle._run` | `events.py:78` |
| 57.778 | 0.006 | 1 | `#` | `_overlap_owner_call` | `golden_serial.py:15624` |
| 39.870 | 0.421 | 145 | `#` | `RMSNorm.forward` | `llama.py:436` |
| 37.450 | 1.406 | 36 | `#` | `MLP.forward` | `llama.py:644` |
| 23.915 | 23.915 | 36 | `#` | `silu` | `functional.py:2429` |
| 12.476 | 0.509 | 252 | `#` | `CastBiasWeightContext.__init__` | `ops.py:464` |
| 11.955 | 9.978 | 252 | `#` | `cast_bias_weight` | `ops.py:337` |
| 2.813 | 2.813 | 397 | `#` | `cast_to` | `model_management.py:1527` |
| 1.221 | 0.379 | 355 | `#` | `deepcopy` | `copy.py:128` |
| 1.183 | 0.395 | 252 | `#` | `device_supports_non_blocking` | `model_management.py:1319` |
| 1.058 | 0.473 | 252 | `#` | `run_every_op` | `ops.py:34` |

## `golden_unet_load`

- Stage wall: **2,414.227 ms**
- Calls attributed: **149,164**
- Distinct functions >= 1 ms: **280**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 2,355.777 | 0.066 | 3 | `#################################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 2,349.100 | 0.014 | 1 | `#################################` | `_WorkItem.run` | `thread.py:53` |
| 2,348.841 | 0.020 | 1 | `#################################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 2,348.821 | 0.004 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 2,348.816 | 0.100 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 2,348.716 | 0.653 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 2,262.136 | 5.944 | 1 | `################################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 2,217.585 | 2,217.583 | 5 | `###############################` | `EpollSelector.select` | `selectors.py:451` |
| 2,217.288 | 0.116 | 1 | `###############################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 2,123.190 | 2.880 | 184 | `##############################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 1,995.836 | 1,990.923 | 185 | `############################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 1,850.894 | 0.287 | 1 | `##########################` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 1,850.607 | 201.031 | 1 | `##########################` | `precompute_freqs_cis` | `llama.py:445` |
| 1,362.983 | 0.024 | 1 | `###################` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,362.948 | 0.083 | 1 | `###################` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,361.531 | 0.073 | 1 | `###################` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,361.459 | 34.971 | 1 | `###################` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,326.445 | 0.716 | 1 | `###################` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,325.333 | 0.007 | 1 | `###################` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,325.258 | 0.033 | 1 | `###################` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,325.224 | 0.122 | 1 | `###################` | `JITFunction.run` | `jit.py:726` |
| 732.205 | 0.034 | 10 | `##########` | `Popen.wait` | `subprocess.py:1259` |
| 732.172 | 0.053 | 10 | `##########` | `Popen._wait` | `subprocess.py:2014` |
| 732.109 | 732.109 | 5 | `##########` | `Popen._try_wait` | `subprocess.py:2001` |
| 724.029 | 0.012 | 11 | `##########` | `DriverConfig.active` | `driver.py:36` |
| 724.017 | 0.009 | 1 | `##########` | `DriverConfig.default` | `driver.py:30` |
| 724.008 | 0.041 | 1 | `##########` | `_create_driver` | `driver.py:8` |
| 723.910 | 0.025 | 1 | `##########` | `CudaDriver.__init__` | `driver.py:341` |
| 723.848 | 0.049 | 1 | `##########` | `CudaUtils.__init__` | `driver.py:100` |
| 708.548 | 0.017 | 1 | `##########` | `compile_module_from_file` | `build.py:193` |
| 708.531 | 1.267 | 1 | `##########` | `_compile_so_from_file` | `build.py:157` |
| 707.198 | 0.382 | 1 | `##########` | `_compile_so` | `build.py:132` |
| 695.814 | 0.047 | 1 | `##########` | `_build` | `build.py:60` |
| 693.808 | 0.010 | 1 | `##########` | `check_call` | `subprocess.py:398` |
| 693.796 | 0.018 | 1 | `##########` | `call` | `subprocess.py:381` |
| 356.955 | 0.044 | 3 | `#####` | `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` | `_tensor.py:32` |
| 317.190 | 27.268 | 10 | `####` | `compile` | `_compiler.py:738` |
| 315.212 | 0.045 | 1 | `####` | `JITFunction._do_compile` | `jit.py:877` |
| 280.773 | 280.750 | 1 | `####` | `dynamic_func` | `<string>:2` |
| 272.760 | 4.799 | 909 | `####` | `Module.state_dict` | `module.py:2199` |

_240 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **55.993 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **31**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 227.143 | 0.349 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 59.542 | 0.638 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 54.179 | 54.179 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 54.149 | 0.057 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 52.796 | 3.063 | 562 | `################################` | `Module.state_dict` | `module.py:2199` |
| 45.222 | 1.172 | 26 | `###########################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 18.453 | 18.449 | 1 | `###########` | `EmptyImage.generate` | `nodes.py:1992` |
| 13.308 | 0.011 | 1 | `########` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 13.297 | 0.076 | 1 | `########` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 13.019 | 0.132 | 4 | `########` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 11.891 | 1.721 | 4 | `#######` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 10.170 | 0.402 | 1 | `######` | `module_size` | `model_management.py:631` |
| 6.707 | 6.707 | 562 | `####` | `Module._save_to_state_dict` | `module.py:2148` |
| 6.130 | 0.020 | 13 | `####` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 6.110 | 0.055 | 13 | `####` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 5.772 | 5.770 | 1 | `####` | `ImageRotate.execute` | `nodes_images.py:764` |
| 3.955 | 0.286 | 105 | `##` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 3.084 | 1.247 | 105 | `##` | `all_tasks` | `tasks.py:42` |
| 2.934 | 0.257 | 60 | `##` | `golden_input_types` | `golden_serial.py:973` |
| 2.898 | 0.908 | 326 | `##` | `_recurse_add_to_result` | `memory.py:232` |
| 2.292 | 0.100 | 52 | `#` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 2.213 | 0.050 | 34 | `#` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 1.794 | 0.278 | 29 | `#` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.396 | 0.039 | 56 | `#` | `classproperty.__get__` | `__init__.py:95` |
| 1.358 | 0.031 | 2 | `#` | `memory_allocated` | `memory.py:525` |
| 1.327 | 0.107 | 2 | `#` | `memory_stats` | `memory.py:242` |
| 1.305 | 0.355 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.225 | 0.022 | 13 | `#` | `_ComfyNodeBaseInternal.INPUT_IS_LIST` | `_io.py:2111` |
| 1.203 | 0.084 | 5 | `#` | `_ComfyNodeBaseInternal.GET_SCHEMA` | `_io.py:2181` |
| 1.073 | 1.073 | 1 | `#` | `golden.sampler_prepare.prepare_validation` | `full_execution_trace.py:330` |
| 1.030 | 1.024 | 5 | `#` | `Schema.validate` | `_io.py:1710` |

## `golden_vae_load`

- Stage wall: **554.772 ms**
- Calls attributed: **156,043**
- Distinct functions >= 1 ms: **157**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 636.239 | 0.072 | 5 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 458.153 | 0.014 | 1 | `############################` | `_WorkItem.run` | `thread.py:53` |
| 457.856 | 0.014 | 1 | `############################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 457.821 | 0.021 | 1 | `############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 457.800 | 0.011 | 1 | `############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 457.789 | 0.011 | 1 | `############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 457.778 | 0.331 | 1 | `############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 457.747 | 457.745 | 2 | `############################` | `EpollSelector.select` | `selectors.py:451` |
| 344.521 | 0.199 | 1 | `#####################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 329.898 | 0.090 | 5 | `####################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 324.355 | 324.223 | 7 | `####################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 293.027 | 0.014 | 2 | `##################` | `prepare_sampling` | `sampler_helpers.py:181` |
| 292.995 | 0.056 | 2 | `##################` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 292.767 | 0.139 | 2 | `##################` | `load_models_gpu` | `model_management.py:909` |
| 290.461 | 0.033 | 2 | `##################` | `LoadedModel.model_load` | `model_management.py:782` |
| 290.392 | 0.006 | 2 | `##################` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 290.386 | 0.404 | 2 | `##################` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 289.876 | 9.392 | 2 | `##################` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 173.928 | 2.116 | 1 | `###########` | `sample_custom` | `sample.py:86` |
| 171.806 | 0.037 | 1 | `###########` | `sample` | `samplers.py:1349` |
| 171.679 | 0.076 | 1 | `###########` | `CFGGuider.sample` | `samplers.py:1276` |
| 171.408 | 0.071 | 1 | `###########` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 170.689 | 0.005 | 1 | `##########` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 170.657 | 1.676 | 1 | `##########` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 160.385 | 9.637 | 824 | `##########` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 124.824 | 26.904 | 410 | `########` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 97.287 | 6.074 | 234 | `######` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 96.772 | 0.038 | 2 | `######` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 89.580 | 59.419 | 1 | `#####` | `VAE.__init__` | `sd.py:487` |
| 76.698 | 76.698 | 1 | `#####` | `GoldenModelTransport._views` | `golden_model_transport.py:2042` |
| 69.777 | 7.979 | 2 | `####` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 68.830 | 23.436 | 4132 | `####` | `get_key_weight` | `model_patcher.py:216` |
| 49.594 | 47.950 | 1 | `###` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 44.644 | 6.891 | 24286 | `###` | `Module.named_modules` | `module.py:2845` |
| 36.729 | 36.286 | 410 | `##` | `namedtuple` | `__init__.py:350` |
| 36.494 | 25.024 | 4133 | `##` | `get_attr` | `utils.py:995` |
| 32.348 | 32.348 | 1 | `##` | `RK_NoiseSampler.prepare_sigmas` | `rk_noise_sampler_beta.py:785` |
| 31.922 | 0.918 | 410 | `##` | `cast_to_device` | `model_management.py:1555` |
| 30.353 | 30.353 | 35468 | `##` | `Module.__getattr__` | `module.py:1959` |
| 28.342 | 28.342 | 410 | `##` | `cast_to` | `model_management.py:1527` |

_117 more functions omitted._

## `golden_sampling`

- Stage wall: **4,267.430 ms**
- Calls attributed: **83,787**
- Distinct functions >= 1 ms: **123**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 18,621.735 | 1.850 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 4,220.136 | 0.033 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,219.909 | 0.060 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,218.983 | 0.058 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,218.801 | 0.444 | 1 | `##################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 4,215.273 | 22.657 | 1 | `##################################` | `SharkSampler.main` | `samplers.py:153` |
| 3,967.539 | 0.045 | 1 | `################################` | `CFGGuider.sample` | `samplers.py:1276` |
| 3,967.343 | 0.044 | 1 | `################################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 3,967.048 | 0.005 | 1 | `################################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 3,967.016 | 1.236 | 1 | `################################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 3,791.834 | 0.593 | 1 | `##############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 3,789.289 | 0.467 | 1 | `##############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 3,788.823 | 1.388 | 73 | `##############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 3,786.354 | 47.737 | 1 | `##############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,260.890 | 3.818 | 17 | `##########################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,256.224 | 1.532 | 17 | `##########################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,254.104 | 0.098 | 17 | `##########################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,254.009 | 0.072 | 17 | `##########################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,253.937 | 0.174 | 17 | `##########################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,253.526 | 0.349 | 17 | `##########################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,253.175 | 0.382 | 17 | `##########################` | `sampling_function` | `samplers.py:609` |
| 1,843.572 | 0.055 | 17 | `###############` | `calc_cond_batch` | `samplers.py:208` |
| 1,843.520 | 0.094 | 17 | `###############` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 1,842.168 | 7.889 | 17 | `###############` | `_calc_cond_batch` | `samplers.py:221` |
| 1,801.351 | 0.151 | 17 | `##############` | `BaseModel.apply_model` | `model_base.py:204` |
| 1,800.546 | 2.761 | 17 | `##############` | `BaseModel._apply_model` | `model_base.py:211` |
| 1,788.085 | 0.092 | 17 | `##############` | `Module._wrapped_call_impl` | `module.py:1779` |
| 1,787.994 | 0.175 | 17 | `##############` | `Module._call_impl` | `module.py:1787` |
| 1,787.818 | 1,787.818 | 17 | `##############` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 1,409.216 | 1.398 | 17 | `###########` | `cfg_function` | `samplers.py:592` |
| 1,407.819 | 1,407.116 | 17 | `###########` | `LGNoiseInjectionLatent.apply.<locals>.cfg_function` | `noise_injection.py:285` |
| 556.189 | 0.028 | 2 | `####` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 556.114 | 0.103 | 2 | `####` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 555.517 | 0.008 | 1 | `####` | `Thread.run` | `threading.py:964` |
| 555.508 | 97.345 | 1 | `####` | `_worker` | `thread.py:69` |
| 232.669 | 60.240 | 10 | `##` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 137.136 | 18.646 | 1016 | `#` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |
| 122.065 | 9.440 | 8366 | `#` | `deepcopy` | `copy.py:128` |
| 116.720 | 8.136 | 1008 | `#` | `RK_Method_Beta.a_k_einsum` | `rk_method_beta.py:394` |
| 110.030 | 36.978 | 1016 | `#` | `einsum` | `functional.py:175` |

_83 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.045 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **719.073 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **42**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 718.779 | 718.779 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 718.754 | 0.023 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 718.679 | 0.038 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 718.403 | 0.016 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 718.246 | 0.027 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 718.219 | 635.965 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 73.028 | 0.082 | 1 | `###` | `load_models_gpu` | `model_management.py:909` |
| 65.595 | 0.017 | 1 | `###` | `LoadedModel.model_load` | `model_management.py:782` |
| 65.545 | 0.003 | 1 | `###` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 65.542 | 0.079 | 1 | `###` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 65.433 | 1.733 | 1 | `###` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 40.096 | 2.218 | 108 | `##` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 32.311 | 8.202 | 108 | `##` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 29.483 | 2.022 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 13.617 | 1.325 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 13.328 | 4.570 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 9.954 | 9.837 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 8.319 | 8.317 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 7.997 | 1.269 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 7.585 | 0.325 | 123 | `#` | `module_size` | `model_management.py:631` |
| 7.040 | 4.806 | 704 | `#` | `get_attr` | `utils.py:995` |
| 6.259 | 6.259 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 6.174 | 0.255 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 5.963 | 1.043 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 5.894 | 3.527 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 5.451 | 0.004 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 5.448 | 0.005 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 5.445 | 0.804 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 5.238 | 5.238 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 5.144 | 5.144 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 4.978 | 0.495 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 4.757 | 0.795 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 4.337 | 0.572 | 108 | `#` | `set_attr` | `utils.py:964` |
| 3.716 | 1.567 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 3.167 | 1.026 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 3.139 | 0.642 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 2.142 | 1.383 | 108 | `#` | `resolve_attr` | `utils.py:958` |
| 2.071 | 0.079 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 1.547 | 0.197 | 4 | `#` | `memory_stats` | `memory.py:242` |
| 1.389 | 0.157 | 234 | `#` | `ModelPatcher._load_list.<locals>.<dictcomp>` | `model_patcher.py:949` |

_2 more functions omitted._

## `golden_output`

- Stage wall: **243.623 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **17**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 390.408 | 0.072 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 203.977 | 0.055 | 1 | `############################` | `Image.save` | `Image.py:2592` |
| 195.139 | 191.120 | 1 | `###########################` | `_encode_tile` | `ImageFile.py:672` |
| 12.822 | 8.118 | 1 | `##` | `fromarray` | `Image.py:3378` |
| 8.624 | 8.624 | 1 | `#` | `preinit` | `Image.py:429` |
| 7.532 | 0.011 | 1 | `#` | `clip` | `fromnumeric.py:2207` |
| 7.520 | 0.025 | 1 | `#` | `_wrapfunc` | `fromnumeric.py:48` |
| 7.495 | 7.495 | 1 | `#` | `_clip` | `_methods.py:96` |
| 4.704 | 0.012 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 4.688 | 0.035 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 3.993 | 0.055 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 3.967 | 0.427 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 3.481 | 3.481 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 3.141 | 3.105 | 1 | `#` | `new` | `Image.py:3193` |
| 2.378 | 0.015 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 2.362 | 2.362 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.508 | 1.474 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
