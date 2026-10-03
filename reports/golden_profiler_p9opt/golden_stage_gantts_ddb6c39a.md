# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **909,895**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.437 | 301 | 0 |
| `golden_request_setup` | 2.898 | 77 | 2 |
| `golden_clip_load` | 4,605.187 | 187,230 | 164 |
| `golden_clip_forward` | 4,122.662 | 9,432 | 34 |
| `golden_unet_load` | 3,056.939 | 149,924 | 295 |
| `golden_sampler_prepare` | 79.943 | 9,847 | 34 |
| `golden_vae_load` | 825.990 | 153,194 | 177 |
| `golden_sampling` | 5,247.829 | 89,300 | 146 |
| `golden_sampler_tail` | 0.051 | 7 | 0 |
| `golden_vae_decode` | 1,013.777 | 26,542 | 48 |
| `golden_output` | 274.028 | 854 | 17 |

## `golden_restore`

- Stage wall: **0.437 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **2.898 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 2.231 | 0.014 | 3 | `##########################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 2.216 | 2.209 | 3 | `##########################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **4,605.187 ms**
- Calls attributed: **187,230**
- Distinct functions >= 1 ms: **164**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 4,528.259 | 0.026 | 2 | `#################################` | `Thread.run` | `threading.py:964` |
| 4,501.880 | 2,241.909 | 1 | `#################################` | `_worker` | `thread.py:69` |
| 4,481.199 | 4,481.199 | 1 | `#################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 4,481.139 | 0.035 | 1 | `#################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 4,481.099 | 0.019 | 1 | `#################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` |
| 4,481.081 | 0.027 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 4,481.053 | 0.113 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 4,480.940 | 0.611 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 2,802.519 | 3.379 | 1 | `#####################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 2,719.910 | 1.436 | 120 | `####################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 2,634.744 | 2,632.365 | 123 | `###################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 2,259.960 | 0.275 | 1 | `#################` | `_WorkItem.run` | `thread.py:53` |
| 2,259.646 | 0.289 | 1 | `#################` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 1,635.910 | 0.092 | 2 | `############` | `GoldenModelTransport.inspect` | `golden_model_transport.py:999` |
| 1,632.070 | 1,621.078 | 1 | `############` | `_clip_meta_state_dict_from_header` | `golden_serial.py:2217` |
| 1,628.587 | 1,626.939 | 2 | `############` | `_parse_layout` | `golden_model_transport.py:327` |
| 627.241 | 0.379 | 1 | `#####` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 626.157 | 0.214 | 1 | `#####` | `CLIP.__init__` | `sd.py:237` |
| 519.879 | 0.014 | 1 | `####` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 519.865 | 0.071 | 1 | `####` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 519.794 | 4.124 | 1 | `####` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 515.670 | 0.733 | 1 | `####` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 494.824 | 1.046 | 1 | `####` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 452.608 | 7.860 | 1 | `###` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 444.076 | 298.102 | 1 | `###` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 272.366 | 14.573 | 1018 | `##` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 178.494 | 20.559 | 81958 | `#` | `Module.named_modules` | `module.py:2845` |
| 133.706 | 55.611 | 3 | `#` | `load` | `__init__.py:274` |
| 83.289 | 0.647 | 127 | `#` | `loads` | `__init__.py:299` |
| 82.661 | 1.049 | 127 | `#` | `JSONDecoder.decode` | `decoder.py:332` |
| 81.612 | 81.612 | 127 | `#` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 67.666 | 2.015 | 2 | `#` | `CLIP.load_sd` | `sd.py:429` |
| 66.153 | 66.153 | 1 | `#` | `golden.clip_load.storage_adoption` | `full_execution_trace.py:330` |
| 66.098 | 1.335 | 1 | `#` | `select_and_validate_qd_adoption_scope` | `golden_serial.py:13060` |
| 64.301 | 19.400 | 6647 | `#` | `Module._named_members` | `module.py:2650` |
| 58.368 | 0.007 | 1 | `#` | `te.<locals>.ZImageTEModel_.__init__` | `z_image.py:39` |
| 58.362 | 0.218 | 1 | `#` | `ZImageTEModel.__init__` | `z_image.py:33` |
| 58.144 | 0.072 | 1 | `#` | `SD1ClipModel.__init__` | `sd1_clip.py:717` |
| 57.959 | 0.034 | 1 | `#` | `Qwen3_4BModel.__init__` | `z_image.py:28` |
| 57.925 | 0.543 | 1 | `#` | `SDClipModel.__init__` | `sd1_clip.py:88` |

_124 more functions omitted._

## `golden_clip_forward`

- Stage wall: **4,122.662 ms**
- Calls attributed: **9,432**
- Distinct functions >= 1 ms: **34**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 12,784.075 | 1.000 | 508 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 12,783.081 | 2.133 | 508 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 4,112.443 | 0.049 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,110.442 | 0.054 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,109.814 | 0.033 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,109.563 | 0.024 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 4,085.208 | 0.026 | 1 | `##################################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 4,085.183 | 0.045 | 1 | `##################################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 3,854.003 | 0.028 | 1 | `################################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 3,853.974 | 27.806 | 1 | `################################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 3,826.109 | 0.004 | 1 | `################################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 3,826.062 | 0.073 | 1 | `################################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 3,667.950 | 0.009 | 1 | `##############################` | `BaseLlama.forward` | `llama.py:998` |
| 3,667.880 | 441.484 | 1 | `##############################` | `Llama2_.forward` | `llama.py:824` |
| 631.429 | 0.048 | 36 | `#####` | `prefetch_queue_pop` | `model_prefetch.py:62` |
| 631.374 | 0.095 | 36 | `#####` | `Llama2_.forward.<locals>.core` | `llama.py:912` |
| 630.991 | 1.698 | 36 | `#####` | `TransformerBlock.forward` | `llama.py:661` |
| 539.248 | 106.701 | 36 | `####` | `Attention.forward` | `llama.py:540` |
| 355.464 | 0.644 | 252 | `###` | `disable_weight_init.Linear.forward` | `ops.py:570` |
| 353.860 | 339.538 | 252 | `###` | `disable_weight_init.Linear.forward_comfy_cast_weights` | `ops.py:566` |
| 84.083 | 41.271 | 290 | `#` | `rms_norm` | `rmsnorm.py:7` |
| 79.786 | 79.786 | 36 | `#` | `apply_rope` | `llama.py:492` |
| 75.349 | 0.041 | 4 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 74.799 | 15.908 | 5 | `#` | `Handle._run` | `events.py:78` |
| 74.571 | 0.008 | 1 | `#` | `_overlap_owner_call` | `golden_serial.py:15624` |
| 49.478 | 0.973 | 36 | `#` | `MLP.forward` | `llama.py:644` |
| 43.880 | 0.383 | 145 | `#` | `RMSNorm.forward` | `llama.py:436` |
| 39.217 | 39.217 | 36 | `#` | `silu` | `functional.py:2429` |
| 13.555 | 0.451 | 252 | `#` | `CastBiasWeightContext.__init__` | `ops.py:464` |
| 13.085 | 11.063 | 252 | `#` | `cast_bias_weight` | `ops.py:337` |
| 2.121 | 2.121 | 397 | `#` | `cast_to` | `model_management.py:1527` |
| 1.471 | 0.439 | 355 | `#` | `deepcopy` | `copy.py:128` |
| 1.110 | 0.368 | 252 | `#` | `device_supports_non_blocking` | `model_management.py:1319` |
| 1.061 | 1.061 | 1447 | `#` | `Module.__getattr__` | `module.py:1959` |

## `golden_unet_load`

- Stage wall: **3,056.939 ms**
- Calls attributed: **149,924**
- Distinct functions >= 1 ms: **295**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 2,981.111 | 0.070 | 3 | `#################################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 2,968.070 | 0.013 | 1 | `#################################` | `_WorkItem.run` | `thread.py:53` |
| 2,967.684 | 0.017 | 1 | `#################################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 2,967.667 | 0.016 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 2,967.651 | 0.118 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 2,967.533 | 0.676 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 2,858.671 | 6.115 | 1 | `################################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 2,847.971 | 2,847.968 | 5 | `################################` | `EpollSelector.select` | `selectors.py:451` |
| 2,842.360 | 0.371 | 1 | `################################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 2,690.100 | 2.696 | 184 | `##############################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 2,469.671 | 0.878 | 1 | `###########################` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 2,468.793 | 218.562 | 1 | `###########################` | `precompute_freqs_cis` | `llama.py:445` |
| 2,465.989 | 2,461.642 | 186 | `###########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 1,938.148 | 0.025 | 1 | `######################` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,938.118 | 0.045 | 1 | `######################` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,937.408 | 0.087 | 1 | `######################` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,937.321 | 38.275 | 1 | `######################` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,898.988 | 0.788 | 1 | `#####################` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,898.081 | 0.007 | 1 | `#####################` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,898.022 | 0.022 | 1 | `#####################` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,898.000 | 0.124 | 1 | `#####################` | `JITFunction.run` | `jit.py:726` |
| 1,009.249 | 0.010 | 11 | `###########` | `DriverConfig.active` | `driver.py:36` |
| 1,009.239 | 0.014 | 1 | `###########` | `DriverConfig.default` | `driver.py:30` |
| 1,009.225 | 0.026 | 1 | `###########` | `_create_driver` | `driver.py:8` |
| 1,009.151 | 0.032 | 1 | `###########` | `CudaDriver.__init__` | `driver.py:341` |
| 1,009.099 | 0.036 | 1 | `###########` | `CudaUtils.__init__` | `driver.py:100` |
| 1,007.412 | 0.118 | 10 | `###########` | `Popen.wait` | `subprocess.py:1259` |
| 1,007.292 | 0.059 | 10 | `###########` | `Popen._wait` | `subprocess.py:2014` |
| 1,007.225 | 1,007.225 | 5 | `###########` | `Popen._try_wait` | `subprocess.py:2001` |
| 986.859 | 0.017 | 1 | `###########` | `compile_module_from_file` | `build.py:193` |
| 986.842 | 1.976 | 1 | `###########` | `_compile_so_from_file` | `build.py:157` |
| 984.816 | 0.341 | 1 | `###########` | `_compile_so` | `build.py:132` |
| 967.619 | 0.063 | 1 | `###########` | `_build` | `build.py:60` |
| 963.786 | 0.010 | 1 | `###########` | `check_call` | `subprocess.py:398` |
| 963.773 | 0.015 | 1 | `###########` | `call` | `subprocess.py:381` |
| 443.190 | 24.486 | 10 | `#####` | `compile` | `_compiler.py:738` |
| 441.214 | 441.169 | 1 | `#####` | `dynamic_func` | `<string>:2` |
| 441.167 | 0.054 | 1 | `#####` | `JITFunction._do_compile` | `jit.py:877` |
| 437.317 | 0.054 | 3 | `#####` | `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` | `_tensor.py:32` |
| 296.352 | 5.862 | 909 | `###` | `Module.state_dict` | `module.py:2199` |

_255 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **79.943 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **34**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 297.288 | 0.494 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 81.199 | 0.880 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 78.495 | 78.495 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 78.460 | 0.085 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 64.158 | 3.725 | 562 | `###########################` | `Module.state_dict` | `module.py:2199` |
| 62.662 | 1.267 | 26 | `###########################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 23.680 | 23.676 | 1 | `##########` | `EmptyImage.generate` | `nodes.py:1992` |
| 13.728 | 0.121 | 4 | `######` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 13.497 | 0.015 | 1 | `######` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 13.482 | 0.079 | 1 | `######` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 12.566 | 0.486 | 105 | `#####` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 12.261 | 0.283 | 4 | `#####` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 11.978 | 0.253 | 1 | `#####` | `module_size` | `model_management.py:631` |
| 10.949 | 0.021 | 13 | `#####` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 10.929 | 0.089 | 13 | `#####` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 8.419 | 0.146 | 52 | `####` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 8.371 | 5.974 | 105 | `####` | `all_tasks` | `tasks.py:42` |
| 7.974 | 7.974 | 562 | `###` | `Module._save_to_state_dict` | `module.py:2148` |
| 7.849 | 7.841 | 1 | `###` | `EmptySD3LatentImage.execute` | `nodes_sd3.py:56` |
| 4.044 | 4.044 | 1 | `##` | `ConditioningZeroOut.zero_out` | `nodes.py:283` |
| 3.706 | 3.706 | 105 | `##` | `current_task` | `tasks.py:35` |
| 3.534 | 0.308 | 60 | `##` | `golden_input_types` | `golden_serial.py:973` |
| 2.895 | 2.893 | 1 | `#` | `ImageRotate.execute` | `nodes_images.py:764` |
| 2.683 | 0.061 | 34 | `#` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 2.308 | 0.357 | 29 | `#` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.554 | 0.432 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.490 | 0.449 | 326 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 1.483 | 0.042 | 1 | `#` | `LGNoiseInjectionLatent.apply` | `noise_injection.py:266` |
| 1.229 | 0.032 | 4 | `#` | `ModelPatcherDynamic.__init__` | `model_patcher.py:1757` |
| 1.192 | 0.101 | 4 | `#` | `ModelPatcher.__init__` | `model_patcher.py:341` |
| 1.136 | 0.113 | 39 | `#` | `_ComfyNodeBaseInternal.FINALIZE_SCHEMA` | `_io.py:2173` |
| 1.087 | 1.030 | 8 | `#` | `uuid4` | `uuid.py:721` |
| 1.077 | 0.823 | 105 | `#` | `all_tasks.<locals>.<setcomp>` | `tasks.py:61` |
| 1.009 | 0.474 | 1365 | `#` | `WeakSet.__iter__` | `_weakrefset.py:63` |

## `golden_vae_load`

- Stage wall: **825.990 ms**
- Calls attributed: **153,194**
- Distinct functions >= 1 ms: **177**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,073.930 | 0.102 | 5 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 660.999 | 0.021 | 1 | `###########################` | `_WorkItem.run` | `thread.py:53` |
| 660.657 | 660.655 | 2 | `###########################` | `EpollSelector.select` | `selectors.py:451` |
| 660.462 | 0.017 | 1 | `###########################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 660.252 | 0.017 | 1 | `###########################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 660.235 | 0.010 | 1 | `###########################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 660.225 | 0.015 | 1 | `###########################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 660.210 | 0.590 | 1 | `###########################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 533.611 | 0.026 | 2 | `######################` | `prepare_sampling` | `sampler_helpers.py:181` |
| 533.558 | 0.070 | 2 | `######################` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 533.288 | 0.183 | 2 | `######################` | `load_models_gpu` | `model_management.py:909` |
| 527.408 | 0.046 | 2 | `######################` | `LoadedModel.model_load` | `model_management.py:782` |
| 527.308 | 0.006 | 2 | `######################` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 527.302 | 0.345 | 2 | `######################` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 526.806 | 11.896 | 2 | `######################` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 409.338 | 0.182 | 1 | `#################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 400.968 | 0.082 | 5 | `#################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 397.086 | 396.961 | 7 | `################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 275.917 | 3.255 | 1 | `###########` | `sample_custom` | `sample.py:86` |
| 272.656 | 0.036 | 1 | `###########` | `sample` | `samplers.py:1349` |
| 270.614 | 0.124 | 1 | `###########` | `CFGGuider.sample` | `samplers.py:1276` |
| 270.290 | 0.068 | 1 | `###########` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 268.842 | 0.006 | 1 | `###########` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 268.781 | 2.018 | 1 | `###########` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 261.221 | 16.657 | 824 | `###########` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 212.461 | 46.519 | 410 | `#########` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 190.000 | 190.000 | 1 | `########` | `GoldenModelTransport._views` | `golden_model_transport.py:2042` |
| 173.211 | 54.366 | 2 | `#######` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 164.963 | 0.048 | 2 | `#######` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 155.610 | 109.605 | 1 | `######` | `VAE.__init__` | `sd.py:487` |
| 120.524 | 7.890 | 234 | `#####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 100.991 | 6.407 | 1062 | `####` | `Module.state_dict` | `module.py:2199` |
| 88.197 | 30.289 | 4132 | `####` | `get_key_weight` | `model_patcher.py:216` |
| 86.488 | 3.364 | 299 | `####` | `deepcopy` | `copy.py:128` |
| 74.357 | 1.326 | 410 | `###` | `cast_to_device` | `model_management.py:1555` |
| 68.607 | 68.607 | 410 | `###` | `cast_to` | `model_management.py:1527` |
| 61.312 | 58.394 | 1 | `###` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 58.775 | 11.613 | 24286 | `##` | `Module.named_modules` | `module.py:2845` |
| 58.542 | 2.162 | 829 | `##` | `module_size` | `model_management.py:631` |
| 51.569 | 51.026 | 410 | `##` | `namedtuple` | `__init__.py:350` |

_137 more functions omitted._

## `golden_sampling`

- Stage wall: **5,247.829 ms**
- Calls attributed: **89,300**
- Distinct functions >= 1 ms: **146**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 24,527.022 | 1.291 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 5,191.297 | 0.038 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 5,191.038 | 0.065 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 5,189.998 | 0.066 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 5,189.764 | 0.267 | 1 | `##################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 5,184.886 | 39.299 | 1 | `##################################` | `SharkSampler.main` | `samplers.py:153` |
| 4,746.889 | 0.088 | 1 | `###############################` | `CFGGuider.sample` | `samplers.py:1276` |
| 4,746.630 | 0.058 | 1 | `###############################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 4,746.195 | 0.005 | 1 | `###############################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 4,746.176 | 6.529 | 1 | `###############################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 4,411.133 | 1.435 | 1 | `#############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 4,407.319 | 0.101 | 1 | `#############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 4,406.656 | 0.696 | 73 | `#############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 4,404.619 | 56.830 | 1 | `#############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,657.002 | 5.374 | 17 | `########################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,650.628 | 2.566 | 17 | `########################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,646.539 | 0.125 | 17 | `########################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,646.415 | 0.098 | 17 | `########################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,646.316 | 0.237 | 17 | `########################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,645.788 | 0.392 | 17 | `########################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,645.396 | 0.319 | 17 | `########################` | `sampling_function` | `samplers.py:609` |
| 3,533.744 | 0.069 | 17 | `#######################` | `calc_cond_batch` | `samplers.py:208` |
| 3,533.677 | 0.103 | 17 | `#######################` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 3,531.681 | 18.200 | 17 | `#######################` | `_calc_cond_batch` | `samplers.py:221` |
| 3,448.752 | 0.174 | 17 | `######################` | `BaseModel.apply_model` | `model_base.py:204` |
| 3,448.137 | 11.732 | 17 | `######################` | `BaseModel._apply_model` | `model_base.py:211` |
| 3,426.104 | 0.099 | 17 | `######################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 3,426.002 | 0.224 | 17 | `######################` | `Module._call_impl` | `module.py:1787` |
| 3,425.780 | 3,425.780 | 17 | `######################` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 829.876 | 0.025 | 2 | `#####` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 829.802 | 0.093 | 2 | `#####` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 828.759 | 0.008 | 1 | `#####` | `Thread.run` | `threading.py:964` |
| 828.751 | 167.740 | 1 | `#####` | `_worker` | `thread.py:69` |
| 387.955 | 94.298 | 10 | `###` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 226.200 | 37.176 | 1016 | `#` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |
| 199.455 | 11.451 | 9705 | `#` | `deepcopy` | `copy.py:128` |
| 187.054 | 12.773 | 1008 | `#` | `RK_Method_Beta.a_k_einsum` | `rk_method_beta.py:394` |
| 175.730 | 71.791 | 1016 | `#` | `einsum` | `functional.py:175` |
| 169.234 | 3.150 | 5 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 165.154 | 165.115 | 5 | `#` | `Handle._run` | `events.py:78` |

_106 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.051 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **1,013.777 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **48**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,013.394 | 1,013.394 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 1,013.365 | 0.026 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 1,013.282 | 0.051 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 1,011.668 | 0.023 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 1,011.378 | 0.042 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 1,011.337 | 895.450 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 110.675 | 0.137 | 1 | `####` | `load_models_gpu` | `model_management.py:909` |
| 100.182 | 0.021 | 1 | `###` | `LoadedModel.model_load` | `model_management.py:782` |
| 100.130 | 0.003 | 1 | `###` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 100.126 | 0.058 | 1 | `###` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 100.024 | 2.055 | 1 | `###` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 64.089 | 3.532 | 108 | `##` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 53.553 | 16.318 | 108 | `##` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 39.132 | 2.504 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 23.678 | 3.020 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 16.800 | 5.722 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 14.223 | 14.077 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 13.550 | 0.467 | 123 | `#` | `module_size` | `model_management.py:631` |
| 13.414 | 0.319 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 11.823 | 11.823 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 10.745 | 2.161 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 10.563 | 10.563 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 9.074 | 6.260 | 704 | `#` | `get_attr` | `utils.py:995` |
| 7.446 | 7.446 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 7.034 | 0.807 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 6.901 | 1.069 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 6.025 | 3.546 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 6.017 | 0.005 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 6.014 | 0.008 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 6.009 | 0.346 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 5.100 | 0.861 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 4.816 | 0.694 | 108 | `#` | `set_attr` | `utils.py:964` |
| 4.337 | 1.991 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 4.016 | 0.115 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 4.003 | 4.001 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 3.961 | 0.780 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 3.180 | 0.937 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 3.061 | 0.171 | 1 | `#` | `free_memory` | `model_management.py:863` |
| 3.025 | 1.625 | 4 | `#` | `memory_stats` | `memory.py:242` |
| 2.639 | 1.841 | 108 | `#` | `resolve_attr` | `utils.py:958` |

_8 more functions omitted._

## `golden_output`

- Stage wall: **274.028 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **17**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 413.238 | 0.088 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 229.223 | 0.065 | 1 | `############################` | `Image.save` | `Image.py:2592` |
| 206.543 | 201.196 | 1 | `##########################` | `_encode_tile` | `ImageFile.py:672` |
| 22.406 | 22.406 | 1 | `###` | `preinit` | `Image.py:429` |
| 14.090 | 8.702 | 1 | `##` | `fromarray` | `Image.py:3378` |
| 10.118 | 0.011 | 1 | `#` | `clip` | `fromnumeric.py:2207` |
| 10.108 | 0.023 | 1 | `#` | `_wrapfunc` | `fromnumeric.py:48` |
| 10.084 | 10.084 | 1 | `#` | `_clip` | `_methods.py:96` |
| 5.389 | 0.016 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 5.364 | 0.027 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 5.318 | 0.065 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 5.273 | 0.714 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 4.469 | 4.469 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 3.746 | 3.705 | 1 | `#` | `new` | `Image.py:3193` |
| 2.284 | 0.020 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 2.264 | 2.264 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.587 | 1.550 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
