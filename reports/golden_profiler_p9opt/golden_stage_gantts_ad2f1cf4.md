# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **889,192**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.441 | 301 | 0 |
| `golden_request_setup` | 1.888 | 77 | 2 |
| `golden_clip_load` | 2,015.766 | 185,635 | 150 |
| `golden_clip_forward` | 3,308.169 | 9,386 | 35 |
| `golden_unet_load` | 2,795.145 | 149,672 | 297 |
| `golden_sampler_prepare` | 55.120 | 9,847 | 26 |
| `golden_vae_load` | 878.879 | 163,957 | 166 |
| `golden_sampling` | 4,413.640 | 76,865 | 121 |
| `golden_sampler_tail` | 0.060 | 7 | 0 |
| `golden_vae_decode` | 874.022 | 26,542 | 43 |
| `golden_output` | 256.510 | 854 | 17 |

## `golden_restore`

- Stage wall: **0.441 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **1.888 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1.178 | 0.017 | 3 | `#####################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 1.161 | 1.154 | 3 | `#####################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **2,015.766 ms**
- Calls attributed: **185,635**
- Distinct functions >= 1 ms: **150**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,944.536 | 0.021 | 2 | `#################################` | `Thread.run` | `threading.py:964` |
| 1,924.383 | 1,320.623 | 1 | `################################` | `_worker` | `thread.py:69` |
| 1,907.651 | 1,907.651 | 1 | `################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 1,907.589 | 0.033 | 1 | `################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 1,907.551 | 0.023 | 1 | `################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` |
| 1,907.528 | 0.030 | 1 | `################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 1,907.498 | 0.109 | 1 | `################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 1,907.389 | 0.600 | 1 | `################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 1,816.448 | 3.909 | 1 | `###############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 1,585.384 | 1.643 | 120 | `###########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 1,434.886 | 1,431.764 | 121 | `########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 603.746 | 4.132 | 1 | `##########` | `_WorkItem.run` | `thread.py:53` |
| 599.578 | 0.219 | 1 | `##########` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 543.729 | 0.216 | 1 | `#########` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 542.976 | 0.240 | 1 | `#########` | `CLIP.__init__` | `sd.py:237` |
| 454.285 | 0.025 | 1 | `########` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 454.260 | 0.028 | 1 | `########` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 454.232 | 2.605 | 1 | `########` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 451.627 | 0.138 | 1 | `########` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 429.508 | 0.969 | 1 | `#######` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 426.128 | 5.902 | 1 | `#######` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 419.958 | 259.350 | 1 | `#######` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 209.572 | 9.322 | 1018 | `####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 161.892 | 161.892 | 244 | `###` | `_FileLock.__enter__` | `golden_source_threads.py:494` |
| 157.035 | 2.911 | 120 | `###` | `SourceThreadProcess.claim_ready` | `golden_source_threads.py:1175` |
| 153.384 | 16.364 | 81958 | `###` | `Module.named_modules` | `module.py:2845` |
| 121.248 | 15.374 | 3 | `##` | `load` | `__init__.py:274` |
| 111.575 | 0.903 | 127 | `##` | `loads` | `__init__.py:299` |
| 110.673 | 1.272 | 127 | `##` | `JSONDecoder.decode` | `decoder.py:332` |
| 109.398 | 109.398 | 127 | `##` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 84.843 | 3.288 | 120 | `#` | `SourceThreadProcess._resolve_ready_block` | `golden_source_threads.py:1044` |
| 69.017 | 69.017 | 244 | `#` | `_FileLock.__exit__` | `golden_source_threads.py:501` |
| 66.254 | 0.567 | 120 | `#` | `SourceThreadProcess._poll_child` | `golden_source_threads.py:1009` |
| 65.729 | 0.338 | 121 | `#` | `Popen.poll` | `subprocess.py:1233` |
| 65.386 | 65.386 | 121 | `#` | `Popen._internal_poll` | `subprocess.py:1966` |
| 59.892 | 0.918 | 2 | `#` | `CLIP.load_sd` | `sd.py:429` |
| 57.246 | 0.076 | 2 | `#` | `GoldenModelTransport.inspect` | `golden_model_transport.py:999` |
| 56.944 | 56.944 | 1 | `#` | `golden.clip_load.storage_adoption` | `full_execution_trace.py:330` |
| 56.890 | 1.165 | 1 | `#` | `select_and_validate_qd_adoption_scope` | `golden_serial.py:13060` |
| 56.298 | 1.188 | 120 | `#` | `GoldenQDTransport.publish` | `golden_qd_transport.py:3099` |

_110 more functions omitted._

## `golden_clip_forward`

- Stage wall: **3,308.169 ms**
- Calls attributed: **9,386**
- Distinct functions >= 1 ms: **35**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 10,467.821 | 1.435 | 507 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 10,466.414 | 3.089 | 507 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 3,298.096 | 0.057 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 3,295.796 | 0.049 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 3,295.542 | 0.035 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 3,295.379 | 0.027 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 3,262.465 | 0.019 | 1 | `##################################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 3,262.446 | 0.038 | 1 | `##################################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 3,089.690 | 0.131 | 1 | `################################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 3,089.558 | 1.946 | 1 | `################################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 3,087.567 | 0.005 | 1 | `################################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 3,087.446 | 0.089 | 1 | `################################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 2,974.533 | 0.011 | 1 | `###############################` | `BaseLlama.forward` | `llama.py:998` |
| 2,974.337 | 390.736 | 1 | `###############################` | `Llama2_.forward` | `llama.py:824` |
| 579.934 | 0.056 | 36 | `######` | `prefetch_queue_pop` | `model_prefetch.py:62` |
| 579.880 | 0.131 | 36 | `######` | `Llama2_.forward.<locals>.core` | `llama.py:912` |
| 579.379 | 2.919 | 36 | `######` | `TransformerBlock.forward` | `llama.py:661` |
| 489.672 | 115.147 | 36 | `#####` | `Attention.forward` | `llama.py:540` |
| 303.973 | 2.078 | 252 | `###` | `disable_weight_init.Linear.forward` | `ops.py:570` |
| 300.828 | 280.956 | 252 | `###` | `disable_weight_init.Linear.forward_comfy_cast_weights` | `ops.py:566` |
| 76.559 | 76.559 | 36 | `#` | `apply_rope` | `llama.py:492` |
| 47.207 | 0.039 | 4 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 46.982 | 12.885 | 5 | `#` | `Handle._run` | `events.py:78` |
| 46.784 | 0.008 | 1 | `#` | `_overlap_owner_call` | `golden_serial.py:15624` |
| 43.955 | 1.820 | 36 | `#` | `MLP.forward` | `llama.py:644` |
| 28.506 | 28.506 | 36 | `#` | `silu` | `functional.py:2429` |
| 14.210 | 5.857 | 288 | `#` | `rms_norm` | `rmsnorm.py:7` |
| 12.809 | 0.577 | 251 | `#` | `CastBiasWeightContext.__init__` | `ops.py:464` |
| 12.214 | 10.182 | 251 | `#` | `cast_bias_weight` | `ops.py:337` |
| 10.015 | 0.486 | 144 | `#` | `RMSNorm.forward` | `llama.py:436` |
| 3.570 | 3.570 | 395 | `#` | `cast_to` | `model_management.py:1527` |
| 1.219 | 0.390 | 355 | `#` | `deepcopy` | `copy.py:128` |
| 1.183 | 0.414 | 251 | `#` | `device_supports_non_blocking` | `model_management.py:1319` |
| 1.136 | 1.136 | 1436 | `#` | `Module.__getattr__` | `module.py:1959` |
| 1.048 | 0.485 | 251 | `#` | `run_every_op` | `ops.py:34` |

## `golden_unet_load`

- Stage wall: **2,795.145 ms**
- Calls attributed: **149,672**
- Distinct functions >= 1 ms: **297**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 2,747.633 | 0.089 | 3 | `#################################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 2,734.786 | 0.011 | 1 | `#################################` | `_WorkItem.run` | `thread.py:53` |
| 2,734.674 | 0.020 | 1 | `#################################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 2,734.654 | 0.006 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 2,734.648 | 0.122 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 2,734.526 | 0.760 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 2,660.787 | 6.311 | 1 | `################################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 2,616.570 | 2,616.567 | 5 | `################################` | `EpollSelector.select` | `selectors.py:451` |
| 2,611.038 | 0.065 | 1 | `################################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 2,550.871 | 2.606 | 184 | `###############################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 2,320.221 | 2,315.196 | 186 | `############################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 1,914.577 | 0.192 | 1 | `#######################` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 1,914.385 | 204.433 | 1 | `#######################` | `precompute_freqs_cis` | `llama.py:445` |
| 1,448.014 | 0.019 | 1 | `##################` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,447.990 | 0.049 | 1 | `##################` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,447.233 | 0.105 | 1 | `##################` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,447.127 | 35.823 | 1 | `##################` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,411.267 | 0.263 | 1 | `#################` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,410.888 | 0.007 | 1 | `#################` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,410.829 | 0.021 | 1 | `#################` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,410.808 | 0.101 | 1 | `#################` | `JITFunction.run` | `jit.py:726` |
| 780.097 | 0.029 | 10 | `#########` | `Popen.wait` | `subprocess.py:1259` |
| 780.067 | 0.062 | 10 | `#########` | `Popen._wait` | `subprocess.py:2014` |
| 779.995 | 779.995 | 5 | `#########` | `Popen._try_wait` | `subprocess.py:2001` |
| 771.744 | 0.008 | 11 | `#########` | `DriverConfig.active` | `driver.py:36` |
| 771.737 | 0.016 | 1 | `#########` | `DriverConfig.default` | `driver.py:30` |
| 771.721 | 0.028 | 1 | `#########` | `_create_driver` | `driver.py:8` |
| 771.650 | 0.030 | 1 | `#########` | `CudaDriver.__init__` | `driver.py:341` |
| 771.590 | 0.040 | 1 | `#########` | `CudaUtils.__init__` | `driver.py:100` |
| 749.621 | 0.019 | 1 | `#########` | `compile_module_from_file` | `build.py:193` |
| 749.602 | 1.192 | 1 | `#########` | `_compile_so_from_file` | `build.py:157` |
| 748.356 | 0.194 | 1 | `#########` | `_compile_so` | `build.py:132` |
| 739.788 | 0.041 | 1 | `#########` | `_build` | `build.py:60` |
| 737.734 | 0.011 | 1 | `#########` | `check_call` | `subprocess.py:398` |
| 737.720 | 0.019 | 1 | `#########` | `call` | `subprocess.py:381` |
| 354.958 | 24.629 | 10 | `####` | `compile` | `_compiler.py:738` |
| 352.951 | 0.055 | 1 | `####` | `JITFunction._do_compile` | `jit.py:877` |
| 350.874 | 0.044 | 3 | `####` | `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` | `_tensor.py:32` |
| 281.404 | 281.369 | 1 | `###` | `dynamic_func` | `<string>:2` |
| 235.713 | 5.305 | 909 | `###` | `Module.state_dict` | `module.py:2199` |

_257 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **55.120 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **26**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 229.124 | 0.423 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 58.396 | 0.743 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 53.778 | 53.778 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 53.738 | 0.068 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 44.006 | 1.306 | 26 | `###########################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 25.549 | 25.544 | 1 | `################` | `EmptyImage.generate` | `nodes.py:1992` |
| 20.459 | 2.214 | 562 | `#############` | `Module.state_dict` | `module.py:2199` |
| 5.459 | 0.019 | 13 | `###` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 5.440 | 0.058 | 13 | `###` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 5.172 | 5.170 | 1 | `###` | `ImageRotate.execute` | `nodes_images.py:764` |
| 5.043 | 0.132 | 4 | `###` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 5.038 | 0.010 | 1 | `###` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 5.027 | 0.075 | 1 | `###` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 4.426 | 0.339 | 105 | `###` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 4.166 | 0.104 | 4 | `###` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 4.062 | 0.105 | 1 | `###` | `module_size` | `model_management.py:631` |
| 3.710 | 0.292 | 60 | `##` | `golden_input_types` | `golden_serial.py:973` |
| 3.352 | 1.441 | 105 | `##` | `all_tasks` | `tasks.py:42` |
| 2.828 | 0.056 | 34 | `##` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 2.564 | 0.114 | 52 | `##` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 2.464 | 0.312 | 29 | `##` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.741 | 1.741 | 562 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 1.502 | 0.095 | 39 | `#` | `_ComfyNodeBaseInternal.FINALIZE_SCHEMA` | `_io.py:2173` |
| 1.411 | 0.430 | 326 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 1.325 | 0.363 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.324 | 1.324 | 1 | `#` | `ConditioningZeroOut.zero_out` | `nodes.py:283` |

## `golden_vae_load`

- Stage wall: **878.879 ms**
- Calls attributed: **163,957**
- Distinct functions >= 1 ms: **166**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 695.149 | 0.016 | 1 | `###########################` | `_WorkItem.run` | `thread.py:53` |
| 694.965 | 0.025 | 1 | `###########################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 694.940 | 0.011 | 1 | `###########################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` |
| 694.930 | 0.012 | 1 | `###########################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` |
| 694.927 | 0.020 | 1 | `###########################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 694.918 | 0.339 | 1 | `###########################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` |
| 694.797 | 694.795 | 2 | `###########################` | `EpollSelector.select` | `selectors.py:451` |
| 627.562 | 0.162 | 1 | `########################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` |
| 621.996 | 0.102 | 5 | `########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` |
| 619.362 | 619.201 | 8 | `########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` |
| 576.190 | 0.075 | 5 | `######################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 324.158 | 5.289 | 234 | `#############` | `Module._apply` | `module.py:930` |
| 227.446 | 0.021 | 2 | `#########` | `prepare_sampling` | `sampler_helpers.py:181` |
| 227.402 | 0.067 | 2 | `#########` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 227.118 | 0.145 | 2 | `#########` | `load_models_gpu` | `model_management.py:909` |
| 224.680 | 0.038 | 2 | `#########` | `LoadedModel.model_load` | `model_management.py:782` |
| 224.594 | 0.007 | 2 | `#########` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 224.587 | 0.498 | 2 | `#########` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 223.951 | 8.544 | 2 | `#########` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 203.077 | 21.403 | 234 | `########` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 183.797 | 0.043 | 2 | `#######` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 177.310 | 2.623 | 1 | `#######` | `sample_custom` | `sample.py:86` |
| 175.391 | 66.215 | 1 | `#######` | `VAE.__init__` | `sd.py:487` |
| 174.684 | 0.035 | 1 | `#######` | `sample` | `samplers.py:1349` |
| 174.438 | 0.092 | 1 | `#######` | `CFGGuider.sample` | `samplers.py:1276` |
| 174.118 | 0.082 | 1 | `#######` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 173.405 | 0.006 | 1 | `#######` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 173.371 | 1.643 | 1 | `#######` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 98.608 | 4.807 | 1062 | `####` | `Module.state_dict` | `module.py:2199` |
| 91.047 | 2.889 | 824 | `####` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 73.128 | 9.201 | 2 | `###` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 68.035 | 22.144 | 4132 | `###` | `get_key_weight` | `model_patcher.py:216` |
| 64.837 | 5.893 | 410 | `###` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 58.823 | 56.991 | 1 | `##` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 51.547 | 0.103 | 1 | `##` | `RK_NoiseSampler.set_sde_step` | `rk_noise_sampler_beta.py:216` |
| 51.214 | 0.054 | 1 | `##` | `Module.to` | `module.py:1259` |
| 48.523 | 8.243 | 24286 | `##` | `Module.named_modules` | `module.py:2845` |
| 38.049 | 0.565 | 4 | `#` | `RK_NoiseSampler.get_sde_step` | `rk_noise_sampler_beta.py:318` |
| 37.482 | 0.512 | 4 | `#` | `RK_NoiseSampler.get_sde_coeff` | `rk_noise_sampler_beta.py:180` |
| 37.304 | 36.877 | 20 | `#` | `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` | `_tensor.py:32` |

_126 more functions omitted._

## `golden_sampling`

- Stage wall: **4,413.640 ms**
- Calls attributed: **76,865**
- Distinct functions >= 1 ms: **121**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 19,923.454 | 1.513 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 4,359.377 | 0.046 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 4,359.055 | 0.065 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 4,358.211 | 0.086 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 4,357.993 | 0.802 | 1 | `##################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 4,354.263 | 18.759 | 1 | `##################################` | `SharkSampler.main` | `samplers.py:153` |
| 4,105.404 | 0.053 | 1 | `################################` | `CFGGuider.sample` | `samplers.py:1276` |
| 4,105.184 | 0.064 | 1 | `################################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 4,104.755 | 0.008 | 1 | `################################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 4,104.721 | 1.076 | 1 | `################################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 3,989.211 | 0.609 | 71 | `###############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 3,988.780 | 0.282 | 1 | `###############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 3,988.188 | 0.077 | 1 | `###############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 3,987.415 | 45.253 | 1 | `###############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,432.395 | 4.287 | 17 | `##########################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,427.064 | 1.459 | 17 | `##########################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,425.138 | 0.116 | 17 | `##########################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,425.023 | 0.082 | 17 | `##########################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,424.941 | 0.227 | 17 | `##########################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,424.438 | 0.372 | 17 | `##########################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,424.067 | 0.474 | 17 | `##########################` | `sampling_function` | `samplers.py:609` |
| 2,170.351 | 0.059 | 17 | `#################` | `calc_cond_batch` | `samplers.py:208` |
| 2,170.290 | 0.093 | 17 | `#################` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 2,169.135 | 8.207 | 17 | `#################` | `_calc_cond_batch` | `samplers.py:221` |
| 2,130.973 | 0.175 | 17 | `################` | `BaseModel.apply_model` | `model_base.py:204` |
| 2,130.270 | 3.231 | 17 | `################` | `BaseModel._apply_model` | `model_base.py:211` |
| 2,117.677 | 0.109 | 17 | `################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 2,117.572 | 0.205 | 17 | `################` | `Module._call_impl` | `module.py:1787` |
| 2,117.368 | 2,117.368 | 17 | `################` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 1,253.244 | 1.658 | 17 | `##########` | `cfg_function` | `samplers.py:592` |
| 1,251.584 | 1,250.649 | 17 | `##########` | `LGNoiseInjectionLatent.apply.<locals>.cfg_function` | `noise_injection.py:285` |
| 881.470 | 0.024 | 2 | `#######` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 881.385 | 0.084 | 2 | `#######` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 880.447 | 0.008 | 1 | `#######` | `Thread.run` | `threading.py:964` |
| 880.440 | 185.281 | 1 | `#######` | `_worker` | `thread.py:69` |
| 272.630 | 71.784 | 10 | `##` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 186.362 | 1.812 | 5 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 184.054 | 184.011 | 5 | `#` | `Handle._run` | `events.py:78` |
| 183.912 | 0.022 | 2 | `#` | `_overlap_stage_call` | `golden_serial.py:15614` |
| 159.009 | 22.235 | 1016 | `#` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |

_81 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.060 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **874.022 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **43**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 873.678 | 873.678 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 873.647 | 0.026 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 873.561 | 0.045 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 873.272 | 0.023 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 873.083 | 0.051 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 873.031 | 783.635 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 78.091 | 0.085 | 1 | `###` | `load_models_gpu` | `model_management.py:909` |
| 69.572 | 0.017 | 1 | `###` | `LoadedModel.model_load` | `model_management.py:782` |
| 69.523 | 0.003 | 1 | `###` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 69.520 | 0.101 | 1 | `###` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 69.387 | 1.677 | 1 | `###` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 43.839 | 2.523 | 108 | `##` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 35.801 | 8.922 | 108 | `#` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 33.627 | 2.081 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 14.058 | 4.538 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 13.451 | 1.311 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 12.164 | 12.052 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 10.070 | 10.068 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 8.273 | 1.334 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 8.262 | 0.406 | 123 | `#` | `module_size` | `model_management.py:631` |
| 7.651 | 5.341 | 704 | `#` | `get_attr` | `utils.py:995` |
| 7.005 | 7.005 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 6.908 | 0.251 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 6.497 | 0.004 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 6.492 | 0.005 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 6.490 | 1.171 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 5.861 | 5.861 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 5.775 | 5.775 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 5.769 | 1.131 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 5.527 | 0.795 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 4.994 | 2.931 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 4.890 | 0.484 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 4.071 | 0.552 | 108 | `#` | `set_attr` | `utils.py:964` |
| 3.767 | 1.552 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 3.097 | 0.949 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 3.091 | 0.621 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 2.237 | 1.463 | 108 | `#` | `resolve_attr` | `utils.py:958` |
| 2.154 | 0.070 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 1.550 | 0.219 | 4 | `#` | `memory_stats` | `memory.py:242` |
| 1.399 | 0.093 | 1 | `#` | `free_memory` | `model_management.py:863` |

_3 more functions omitted._

## `golden_output`

- Stage wall: **256.510 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **17**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 396.877 | 0.075 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 210.126 | 0.066 | 1 | `############################` | `Image.save` | `Image.py:2592` |
| 198.369 | 193.924 | 1 | `##########################` | `_encode_tile` | `ImageFile.py:672` |
| 13.421 | 8.365 | 1 | `##` | `fromarray` | `Image.py:3378` |
| 11.510 | 11.510 | 1 | `##` | `preinit` | `Image.py:429` |
| 10.022 | 0.014 | 1 | `#` | `clip` | `fromnumeric.py:2207` |
| 10.008 | 0.025 | 1 | `#` | `_wrapfunc` | `fromnumeric.py:48` |
| 9.983 | 9.983 | 1 | `#` | `_clip` | `_methods.py:96` |
| 5.056 | 0.015 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 5.036 | 0.028 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 4.420 | 0.063 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 4.389 | 0.647 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 3.668 | 3.668 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 3.352 | 3.313 | 1 | `#` | `new` | `Image.py:3193` |
| 2.257 | 0.017 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 2.240 | 2.240 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.651 | 1.615 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
