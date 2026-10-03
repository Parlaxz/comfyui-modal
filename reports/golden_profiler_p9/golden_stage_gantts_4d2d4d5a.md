# Golden per-stage Gantts

Source: `golden_exhaustive_calls.csv.gz`

Calls in trace: **887,436**

Frames shown: wall >= **1 ms**

Stages: 11 of 11 observed

Attribution is by tightest time containment within a stage, because the overlap schedule runs stage bodies on executor threads where stack nesting cannot see them. Bars are scaled per stage against that stage's own wall clock.

## Stage summary

| stage | wall ms | calls attributed | functions >= threshold |
|:--|---:|---:|---:|
| `golden_restore` | 0.473 | 301 | 0 |
| `golden_request_setup` | 2.670 | 77 | 2 |
| `golden_clip_load` | 3,506.679 | 181,497 | 159 |
| `golden_clip_forward` | 6,376.576 | 9,079 | 39 |
| `golden_unet_load` | 6,249.016 | 145,268 | 343 |
| `golden_sampler_prepare` | 67.449 | 9,847 | 30 |
| `golden_vae_load` | 1,070.325 | 163,618 | 182 |
| `golden_sampling` | 5,804.560 | 77,575 | 145 |
| `golden_sampler_tail` | 0.096 | 7 | 0 |
| `golden_vae_decode` | 1,591.067 | 26,542 | 48 |
| `golden_output` | 301.508 | 854 | 17 |

## `golden_restore`

- Stage wall: **0.473 ms**
- Calls attributed: **301**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_request_setup`

- Stage wall: **2.670 ms**
- Calls attributed: **77**
- Distinct functions >= 1 ms: **2**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1.725 | 0.030 | 3 | `######################` | `get_full_path_or_raise` | `folder_paths.py:461` |
| 1.695 | 1.690 | 3 | `######################` | `get_full_path` | `folder_paths.py:441` |

## `golden_clip_load`

- Stage wall: **3,506.679 ms**
- Calls attributed: **181,497**
- Distinct functions >= 1 ms: **159**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 3,373.023 | 0.021 | 1 | `#################################` | `Thread.run` | `threading.py:964` |
| 3,373.002 | 2,080.385 | 1 | `#################################` | `_worker` | `thread.py:69` |
| 3,356.569 | 3,356.569 | 1 | `#################################` | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` |
| 3,356.495 | 0.036 | 1 | `#################################` | `_read_golden_m2_clip` | `golden_serial.py:11462` |
| 3,356.453 | 0.015 | 1 | `#################################` | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1001` |
| 3,356.439 | 0.020 | 1 | `#################################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 3,356.418 | 0.065 | 1 | `#################################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 3,356.353 | 0.841 | 1 | `#################################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 2,884.917 | 5.989 | 1 | `############################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 2,733.832 | 3.014 | 120 | `###########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 2,577.936 | 2,573.463 | 122 | `#########################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 1,292.599 | 5.078 | 1 | `#############` | `_WorkItem.run` | `thread.py:53` |
| 1,287.471 | 0.558 | 1 | `############` | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` |
| 839.976 | 0.301 | 1 | `########` | `load_text_encoder_state_dicts` | `sd.py:1720` |
| 838.797 | 0.396 | 1 | `########` | `CLIP.__init__` | `sd.py:237` |
| 690.188 | 0.030 | 1 | `#######` | `ZImageTokenizer.__init__` | `z_image.py:13` |
| 690.158 | 0.049 | 1 | `#######` | `SD1Tokenizer.__init__` | `sd1_clip.py:687` |
| 690.109 | 5.876 | 1 | `#######` | `Qwen3Tokenizer.__init__` | `z_image.py:7` |
| 684.233 | 0.161 | 1 | `#######` | `SDTokenizer.__init__` | `sd1_clip.py:487` |
| 647.278 | 1.517 | 1 | `######` | `PreTrainedTokenizerBase.from_pretrained` | `tokenization_utils_base.py:1807` |
| 598.824 | 11.133 | 1 | `######` | `PreTrainedTokenizerBase._from_pretrained` | `tokenization_utils_base.py:2083` |
| 587.264 | 348.418 | 1 | `######` | `Qwen2Tokenizer.__init__` | `tokenization_qwen2.py:137` |
| 446.873 | 359.362 | 1 | `####` | `_clip_meta_state_dict_from_header` | `golden_serial.py:2217` |
| 446.821 | 25.825 | 1018 | `####` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 425.514 | 0.052 | 1 | `####` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 424.810 | 423.916 | 1 | `####` | `_parse_layout` | `golden_model_transport.py:304` |
| 216.754 | 58.520 | 3 | `##` | `load` | `__init__.py:274` |
| 210.731 | 33.220 | 81958 | `##` | `Module.named_modules` | `module.py:2845` |
| 164.014 | 1.239 | 126 | `##` | `loads` | `__init__.py:299` |
| 162.775 | 1.946 | 126 | `##` | `JSONDecoder.decode` | `decoder.py:332` |
| 160.827 | 160.827 | 126 | `##` | `JSONDecoder.raw_decode` | `decoder.py:343` |
| 103.989 | 0.901 | 2 | `#` | `CLIP.load_sd` | `sd.py:429` |
| 90.489 | 0.019 | 2 | `#` | `SD1ClipModel.load_sd` | `sd1_clip.py:746` |
| 90.468 | 0.060 | 2 | `#` | `SDClipModel.load_sd` | `sd1_clip.py:308` |
| 90.405 | 0.332 | 2 | `#` | `Module.load_state_dict` | `module.py:2535` |
| 87.264 | 85.646 | 1 | `#` | `parse_safetensors_header` | `clip_qd_reader.py:300` |
| 83.927 | 83.927 | 245 | `#` | `_FileLock.__enter__` | `golden_source_threads.py:486` |
| 81.439 | 0.892 | 121 | `#` | `SourceThreadProcess._poll_child` | `golden_source_threads.py:1001` |
| 81.120 | 4.821 | 120 | `#` | `SourceThreadProcess._resolve_ready_block` | `golden_source_threads.py:1036` |
| 80.588 | 0.678 | 122 | `#` | `Popen.poll` | `subprocess.py:1233` |

_119 more functions omitted._

## `golden_clip_forward`

- Stage wall: **6,376.576 ms**
- Calls attributed: **9,079**
- Distinct functions >= 1 ms: **39**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 14,023.804 | 1.739 | 488 | `##################################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 14,022.065 | 4.568 | 488 | `##################################` | `Module._call_impl` | `module.py:1787` |
| 6,364.103 | 0.056 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 6,360.821 | 0.062 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 6,360.132 | 0.100 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 6,359.734 | 0.025 | 1 | `##################################` | `CLIPTextEncode.encode` | `nodes.py:73` |
| 4,960.311 | 0.028 | 1 | `##########################` | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` |
| 4,960.283 | 0.062 | 1 | `##########################` | `CLIP.encode_from_tokens` | `sd.py:396` |
| 4,672.648 | 0.050 | 1 | `#########################` | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` |
| 4,672.597 | 9.079 | 1 | `#########################` | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` |
| 4,663.398 | 0.005 | 1 | `#########################` | `SDClipModel.encode` | `sd1_clip.py:305` |
| 4,663.345 | 0.080 | 1 | `#########################` | `SDClipModel.forward` | `sd1_clip.py:260` |
| 4,534.001 | 0.011 | 1 | `########################` | `BaseLlama.forward` | `llama.py:998` |
| 4,533.074 | 657.141 | 1 | `########################` | `Llama2_.forward` | `llama.py:824` |
| 120.984 | 0.066 | 35 | `#` | `prefetch_queue_pop` | `model_prefetch.py:62` |
| 120.914 | 0.169 | 35 | `#` | `Llama2_.forward.<locals>.core` | `llama.py:912` |
| 120.253 | 4.161 | 35 | `#` | `TransformerBlock.forward` | `llama.py:661` |
| 81.658 | 31.635 | 35 | `#` | `Attention.forward` | `llama.py:540` |
| 73.758 | 0.075 | 4 | `#` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 73.365 | 23.134 | 5 | `#` | `Handle._run` | `events.py:78` |
| 73.106 | 0.011 | 1 | `#` | `_overlap_owner_call` | `golden_serial.py:15543` |
| 46.004 | 2.742 | 242 | `#` | `disable_weight_init.Linear.forward` | `ops.py:570` |
| 41.750 | 20.165 | 242 | `#` | `disable_weight_init.Linear.forward_comfy_cast_weights` | `ops.py:566` |
| 24.145 | 2.169 | 35 | `#` | `MLP.forward` | `llama.py:644` |
| 21.591 | 8.784 | 276 | `#` | `rms_norm` | `rmsnorm.py:7` |
| 19.868 | 0.992 | 242 | `#` | `CastBiasWeightContext.__init__` | `ops.py:464` |
| 18.885 | 15.687 | 242 | `#` | `cast_bias_weight` | `ops.py:337` |
| 15.015 | 0.559 | 138 | `#` | `RMSNorm.forward` | `llama.py:436` |
| 11.746 | 11.746 | 35 | `#` | `apply_rope` | `llama.py:492` |
| 5.640 | 5.640 | 380 | `#` | `cast_to` | `model_management.py:1527` |
| 2.461 | 0.881 | 355 | `#` | `deepcopy` | `copy.py:128` |
| 1.985 | 0.589 | 242 | `#` | `device_supports_non_blocking` | `model_management.py:1319` |
| 1.601 | 1.601 | 1382 | `#` | `Module.__getattr__` | `module.py:1959` |
| 1.505 | 0.638 | 242 | `#` | `run_every_op` | `ops.py:34` |
| 1.490 | 0.288 | 7 | `#` | `_deepcopy_dict` | `copy.py:227` |
| 1.394 | 0.862 | 242 | `#` | `CastBiasWeightContext.__exit__` | `ops.py:475` |
| 1.137 | 1.137 | 35 | `#` | `silu` | `functional.py:2429` |
| 1.101 | 1.101 | 484 | `#` | `is_device_type` | `model_management.py:1802` |
| 1.054 | 0.275 | 242 | `#` | `is_device_mps` | `model_management.py:1811` |

## `golden_unet_load`

- Stage wall: **6,249.016 ms**
- Calls attributed: **145,268**
- Distinct functions >= 1 ms: **343**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 4,756.252 | 0.148 | 3 | `##########################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 4,750.930 | 0.020 | 1 | `##########################` | `_WorkItem.run` | `thread.py:53` |
| 4,750.731 | 0.027 | 1 | `##########################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 4,750.704 | 0.013 | 1 | `##########################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 4,750.690 | 0.073 | 1 | `##########################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 4,750.618 | 1.019 | 1 | `##########################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 4,554.064 | 8.783 | 1 | `#########################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 4,544.407 | 0.110 | 1 | `#########################` | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` |
| 4,543.828 | 4,543.826 | 5 | `#########################` | `EpollSelector.select` | `selectors.py:451` |
| 4,376.568 | 4.056 | 184 | `########################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 4,183.553 | 4,176.658 | 187 | `#######################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 2,791.764 | 1.738 | 1 | `###############` | `Llama2_.compute_freqs_cis` | `llama.py:815` |
| 2,790.026 | 298.872 | 1 | `###############` | `precompute_freqs_cis` | `llama.py:445` |
| 2,754.056 | 1,377.182 | 285 | `###############` | `SpecialTokensMixin.__getattr__` | `tokenization_utils_base.py:1077` |
| 2,252.463 | 0.178 | 21 | `############` | `Module._wrapped_call_impl` | `module.py:1779` |
| 2,252.285 | 0.739 | 21 | `############` | `Module._call_impl` | `module.py:1787` |
| 1,903.203 | 0.018 | 1 | `##########` | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` |
| 1,903.178 | 0.045 | 1 | `##########` | `_register_overrides_from_graph.<locals>._dispatch` | `registry.py:926` |
| 1,901.991 | 0.088 | 1 | `##########` | `OpOverloadPacket.__call__` | `_ops.py:1338` |
| 1,901.903 | 95.460 | 1 | `##########` | `_bmm_outer_product_impl` | `triton_impl.py:18` |
| 1,806.378 | 0.621 | 1 | `##########` | `bmm_outer_product` | `triton_kernels.py:77` |
| 1,805.597 | 0.009 | 1 | `##########` | `_make_wrapper.<locals>.wrapper` | `instrumentation.py:202` |
| 1,805.513 | 0.041 | 1 | `##########` | `KernelInterface.__getitem__.<locals>.<lambda>` | `jit.py:374` |
| 1,805.471 | 0.159 | 1 | `##########` | `JITFunction.run` | `jit.py:726` |
| 1,698.387 | 7.057 | 3 | `#########` | `_unet_load_with_worker_stage` | `golden_parallel.py:517` |
| 1,422.548 | 0.074 | 2 | `########` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 1,418.597 | 1,417.432 | 1 | `########` | `_parse_layout` | `golden_model_transport.py:304` |
| 1,399.398 | 0.018 | 1 | `########` | `CLIP.tokenize` | `sd.py:322` |
| 1,399.380 | 0.015 | 1 | `########` | `ZImageTokenizer.tokenize_with_weights` | `z_image.py:17` |
| 1,399.365 | 0.036 | 1 | `########` | `SD1Tokenizer.tokenize_with_weights` | `sd1_clip.py:698` |
| 1,399.328 | 0.084 | 1 | `########` | `SDTokenizer.tokenize_with_weights` | `sd1_clip.py:572` |
| 1,398.688 | 0.025 | 1 | `########` | `PreTrainedTokenizerBase.__call__` | `tokenization_utils_base.py:2827` |
| 1,398.662 | 0.012 | 1 | `########` | `PreTrainedTokenizerBase._call_one` | `tokenization_utils_base.py:2925` |
| 1,398.649 | 0.015 | 1 | `########` | `PreTrainedTokenizerBase.encode_plus` | `tokenization_utils_base.py:3043` |
| 1,398.625 | 0.021 | 1 | `########` | `PreTrainedTokenizer._encode_plus` | `tokenization_utils.py:743` |
| 1,376.855 | 0.039 | 1 | `#######` | `PreTrainedTokenizerBase.prepare_for_model` | `tokenization_utils_base.py:3475` |
| 1,376.653 | 0.043 | 1 | `#######` | `PreTrainedTokenizerBase.create_token_type_ids_from_sequences` | `tokenization_utils_base.py:3431` |
| 880.330 | 0.007 | 11 | `#####` | `DriverConfig.active` | `driver.py:36` |
| 880.323 | 0.020 | 1 | `#####` | `DriverConfig.default` | `driver.py:30` |
| 880.303 | 0.058 | 1 | `#####` | `_create_driver` | `driver.py:8` |

_303 more functions omitted._

## `golden_sampler_prepare`

- Stage wall: **67.449 ms**
- Calls attributed: **9,847**
- Distinct functions >= 1 ms: **30**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 279.724 | 0.702 | 35 | `##################################` | `GoldenSerialRunner._ensure` | `golden_serial.py:9122` |
| 76.518 | 4.599 | 562 | `##################################` | `Module.state_dict` | `module.py:2199` |
| 70.406 | 0.940 | 26 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 65.823 | 65.823 | 1 | `#################################` | `golden.sampler_prepare.prepare_dependency_closure` | `full_execution_trace.py:330` |
| 65.777 | 0.065 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 53.757 | 3.962 | 26 | `###########################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 20.531 | 20.523 | 1 | `##########` | `EmptyImage.generate` | `nodes.py:1992` |
| 17.169 | 0.012 | 1 | `#########` | `ModelSamplingAuraFlow.patch_aura` | `nodes_model_advanced.py:158` |
| 17.158 | 0.077 | 1 | `#########` | `ModelSamplingSD3.patch` | `nodes_model_advanced.py:131` |
| 16.951 | 0.126 | 4 | `#########` | `ModelPatcher.clone` | `model_patcher.py:430` |
| 15.911 | 1.401 | 4 | `########` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 14.510 | 0.403 | 1 | `#######` | `module_size` | `model_management.py:631` |
| 9.513 | 9.513 | 562 | `#####` | `Module._save_to_state_dict` | `module.py:2148` |
| 5.931 | 0.475 | 105 | `###` | `GoldenSerialRunner._observe_tasks` | `golden_serial.py:8621` |
| 5.410 | 0.021 | 13 | `###` | `make_locked_method_func.<locals>.wrapped_func` | `__init__.py:148` |
| 5.384 | 0.075 | 13 | `###` | `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` | `_io.py:1987` |
| 5.036 | 5.034 | 1 | `###` | `ImageRotate.execute` | `nodes_images.py:764` |
| 4.366 | 1.906 | 105 | `##` | `all_tasks` | `tasks.py:42` |
| 3.861 | 0.390 | 60 | `##` | `golden_input_types` | `golden_serial.py:973` |
| 3.189 | 0.127 | 52 | `##` | `GoldenSerialRunner._resolve` | `golden_serial.py:9010` |
| 2.811 | 0.059 | 34 | `#` | `_ComfyNodeBaseInternal.INPUT_TYPES` | `_io.py:2166` |
| 2.558 | 0.460 | 29 | `#` | `GoldenSerialRunner._get_input_data` | `golden_serial.py:8702` |
| 1.966 | 0.608 | 326 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 1.660 | 0.458 | 34 | `#` | `Schema.get_v1_info` | `_io.py:1766` |
| 1.190 | 0.107 | 39 | `#` | `_ComfyNodeBaseInternal.FINALIZE_SCHEMA` | `_io.py:2173` |
| 1.149 | 0.853 | 105 | `#` | `all_tasks.<locals>.<setcomp>` | `tasks.py:61` |
| 1.096 | 1.096 | 105 | `#` | `current_task` | `tasks.py:35` |
| 1.094 | 0.030 | 2 | `#` | `memory_allocated` | `memory.py:525` |
| 1.064 | 0.113 | 2 | `#` | `memory_stats` | `memory.py:242` |
| 1.027 | 0.059 | 34 | `#` | `create_input_dict_v1` | `_io.py:1861` |

## `golden_vae_load`

- Stage wall: **1,070.325 ms**
- Calls attributed: **163,618**
- Distinct functions >= 1 ms: **182**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 924.489 | 0.080 | 5 | `#############################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 907.429 | 0.023 | 1 | `#############################` | `_WorkItem.run` | `thread.py:53` |
| 907.068 | 0.040 | 1 | `#############################` | `thread_traced.<locals>._run` | `full_execution_trace.py:276` |
| 907.068 | 0.023 | 1 | `#############################` | `BaseEventLoop._run_once` | `base_events.py:1845` |
| 907.029 | 0.025 | 1 | `#############################` | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` |
| 907.003 | 0.017 | 1 | `#############################` | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` |
| 906.986 | 0.514 | 1 | `#############################` | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` |
| 906.854 | 906.851 | 2 | `#############################` | `EpollSelector.select` | `selectors.py:451` |
| 640.053 | 0.240 | 1 | `####################` | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` |
| 634.097 | 633.901 | 8 | `####################` | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` |
| 633.761 | 0.235 | 5 | `####################` | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` |
| 373.801 | 0.017 | 2 | `############` | `prepare_sampling` | `sampler_helpers.py:181` |
| 373.760 | 0.055 | 2 | `############` | `_prepare_sampling` | `sampler_helpers.py:188` |
| 373.496 | 0.228 | 2 | `############` | `load_models_gpu` | `model_management.py:909` |
| 366.956 | 0.043 | 2 | `############` | `LoadedModel.model_load` | `model_management.py:782` |
| 366.861 | 0.006 | 2 | `############` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 366.854 | 0.553 | 2 | `############` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 366.140 | 12.331 | 2 | `############` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 278.367 | 2.760 | 1 | `#########` | `sample_custom` | `sample.py:86` |
| 275.599 | 0.032 | 1 | `#########` | `sample` | `samplers.py:1349` |
| 275.259 | 0.115 | 1 | `#########` | `CFGGuider.sample` | `samplers.py:1276` |
| 274.888 | 0.098 | 1 | `#########` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 273.919 | 0.009 | 1 | `#########` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 273.869 | 1.954 | 1 | `#########` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 235.199 | 19.510 | 234 | `#######` | `Module.load_state_dict.<locals>.load` | `module.py:2589` |
| 180.739 | 8.211 | 824 | `######` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 179.061 | 0.045 | 1 | `######` | `GoldenModelTransport.inspect` | `golden_model_transport.py:973` |
| 178.613 | 177.751 | 1 | `######` | `_parse_layout` | `golden_model_transport.py:304` |
| 163.012 | 0.032 | 2 | `#####` | `_vae_load_with_worker_stage` | `golden_parallel.py:522` |
| 151.915 | 76.194 | 1 | `#####` | `VAE.__init__` | `sd.py:487` |
| 135.816 | 15.729 | 410 | `####` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 103.714 | 14.155 | 2 | `###` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 98.728 | 32.656 | 4132 | `###` | `get_key_weight` | `model_patcher.py:216` |
| 89.891 | 0.909 | 1 | `###` | `RK_NoiseSampler.set_sde_step` | `rk_noise_sampler_beta.py:216` |
| 78.957 | 16.908 | 4 | `###` | `RK_NoiseSampler.get_sde_step` | `rk_noise_sampler_beta.py:318` |
| 76.641 | 6.106 | 1062 | `##` | `Module.state_dict` | `module.py:2199` |
| 69.223 | 14.972 | 24286 | `##` | `Module.named_modules` | `module.py:2845` |
| 65.414 | 62.649 | 1 | `##` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 62.211 | 62.211 | 1 | `##` | `GoldenModelTransport._views` | `golden_model_transport.py:1910` |
| 62.045 | 7.795 | 4 | `##` | `RK_NoiseSampler.get_sde_coeff` | `rk_noise_sampler_beta.py:180` |

_142 more functions omitted._

## `golden_sampling`

- Stage wall: **5,804.560 ms**
- Calls attributed: **77,575**
- Distinct functions >= 1 ms: **145**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 27,108.482 | 2.584 | 54 | `##################################` | `WrapperExecutor.execute` | `patcher_extension.py:108` |
| 5,594.385 | 0.054 | 1 | `#################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 5,594.016 | 0.073 | 1 | `#################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 5,592.908 | 0.092 | 1 | `#################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 5,592.644 | 0.316 | 1 | `#################################` | `ClownsharKSampler_Beta.main` | `samplers.py:1745` |
| 5,587.699 | 26.065 | 1 | `#################################` | `SharkSampler.main` | `samplers.py:153` |
| 5,222.189 | 0.066 | 1 | `###############################` | `CFGGuider.sample` | `samplers.py:1276` |
| 5,221.947 | 0.065 | 1 | `###############################` | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` |
| 5,221.509 | 0.006 | 1 | `###############################` | `WrapperExecutor.__call__` | `patcher_extension.py:103` |
| 5,221.486 | 1.623 | 1 | `###############################` | `CFGGuider.outer_sample` | `samplers.py:1240` |
| 5,052.758 | 0.853 | 71 | `##############################` | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` |
| 5,052.122 | 0.300 | 1 | `##############################` | `CFGGuider.inner_sample` | `samplers.py:1220` |
| 5,051.448 | 0.120 | 1 | `##############################` | `KSAMPLER.sample` | `samplers.py:983` |
| 5,050.158 | 71.731 | 1 | `##############################` | `sample_rk_beta` | `rk_sampler_beta.py:110` |
| 3,932.211 | 6.745 | 17 | `#######################` | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` |
| 3,924.344 | 2.923 | 17 | `#######################` | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` |
| 3,920.551 | 0.187 | 17 | `#######################` | `KSamplerX0Inpaint.__call__` | `samplers.py:634` |
| 3,920.360 | 0.112 | 17 | `#######################` | `CFGGuider.__call__` | `samplers.py:1207` |
| 3,920.248 | 0.250 | 17 | `#######################` | `CFGGuider.outer_predict_noise` | `samplers.py:1210` |
| 3,919.662 | 0.475 | 17 | `#######################` | `SharkGuider.predict_noise` | `samplers.py:99` |
| 3,919.187 | 0.494 | 17 | `#######################` | `sampling_function` | `samplers.py:609` |
| 3,876.150 | 0.071 | 17 | `#######################` | `calc_cond_batch` | `samplers.py:208` |
| 3,876.078 | 0.123 | 17 | `#######################` | `_calc_cond_batch_outer` | `samplers.py:214` |
| 3,874.188 | 14.995 | 17 | `#######################` | `_calc_cond_batch` | `samplers.py:221` |
| 3,818.408 | 0.255 | 17 | `######################` | `BaseModel.apply_model` | `model_base.py:204` |
| 3,817.172 | 4.667 | 17 | `######################` | `BaseModel._apply_model` | `model_base.py:211` |
| 3,801.796 | 0.135 | 17 | `######################` | `Module._wrapped_call_impl` | `module.py:1779` |
| 3,801.660 | 0.263 | 17 | `######################` | `Module._call_impl` | `module.py:1787` |
| 3,801.396 | 3,801.396 | 17 | `######################` | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` |
| 1,075.938 | 0.038 | 2 | `######` | `BaseEventLoop.run_until_complete` | `base_events.py:617` |
| 1,075.831 | 0.130 | 2 | `######` | `BaseEventLoop.run_forever` | `base_events.py:593` |
| 1,074.630 | 0.015 | 1 | `######` | `Thread.run` | `threading.py:964` |
| 1,074.616 | 167.172 | 1 | `######` | `_worker` | `thread.py:69` |
| 661.892 | 180.761 | 10 | `####` | `RK_Method_Beta.bong_iter` | `rk_method_beta.py:607` |
| 317.415 | 64.502 | 1016 | `##` | `RK_Method_Beta.zum` | `rk_method_beta.py:408` |
| 250.482 | 18.620 | 1008 | `#` | `RK_Method_Beta.a_k_einsum` | `rk_method_beta.py:394` |
| 233.615 | 99.343 | 1016 | `#` | `einsum` | `functional.py:175` |
| 204.063 | 193.442 | 500 | `#` | `RK_Method_Exponential.get_epsilon` | `rk_method_beta.py:937` |
| 179.764 | 179.764 | 3 | `#` | `import_module` | `__init__.py:108` |
| 169.838 | 14.387 | 9237 | `#` | `deepcopy` | `copy.py:128` |

_105 more functions omitted._

## `golden_sampler_tail`

- Stage wall: **0.096 ms**
- Calls attributed: **7**
- Distinct functions >= 1 ms: **0**

_No frame reached the threshold._

## `golden_vae_decode`

- Stage wall: **1,591.067 ms**
- Calls attributed: **26,542**
- Distinct functions >= 1 ms: **48**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 1,590.605 | 1,590.605 | 1 | `##################################` | `golden.vae_decode.vae_decode_dependency_closure` | `full_execution_trace.py:330` |
| 1,590.562 | 0.041 | 1 | `##################################` | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` |
| 1,590.454 | 0.055 | 1 | `##################################` | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` |
| 1,590.069 | 0.030 | 1 | `##################################` | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` |
| 1,589.852 | 0.031 | 1 | `##################################` | `VAEDecode.decode` | `nodes.py:333` |
| 1,589.821 | 1,468.457 | 1 | `##################################` | `VAE.decode` | `sd.py:1220` |
| 112.576 | 0.136 | 1 | `##` | `load_models_gpu` | `model_management.py:909` |
| 102.199 | 0.025 | 1 | `##` | `LoadedModel.model_load` | `model_management.py:782` |
| 102.137 | 0.003 | 1 | `##` | `LoadedModel.model_use_more_vram` | `model_management.py:817` |
| 102.133 | 0.090 | 1 | `##` | `ModelPatcherDynamic.partially_load` | `model_patcher.py:2141` |
| 102.003 | 2.288 | 1 | `##` | `ModelPatcherDynamic.load` | `model_patcher.py:1853` |
| 67.843 | 3.667 | 108 | `#` | `ModelPatcherDynamic.load.<locals>.force_load_param` | `model_patcher.py:1947` |
| 55.118 | 14.414 | 108 | `#` | `ModelPatcher.patch_weight_to_device` | `model_patcher.py:899` |
| 39.345 | 2.689 | 356 | `#` | `Module.state_dict` | `module.py:2199` |
| 20.275 | 6.461 | 704 | `#` | `get_key_weight` | `model_patcher.py:216` |
| 18.022 | 1.706 | 1 | `#` | `ModelPatcher._load_list` | `model_patcher.py:945` |
| 17.004 | 16.842 | 108 | `#` | `namedtuple` | `__init__.py:350` |
| 11.343 | 0.379 | 108 | `#` | `cast_to_device` | `model_management.py:1555` |
| 11.176 | 2.450 | 4205 | `#` | `Module.named_modules` | `module.py:2845` |
| 11.164 | 7.222 | 704 | `#` | `get_attr` | `utils.py:995` |
| 9.656 | 0.470 | 123 | `#` | `module_size` | `model_management.py:631` |
| 9.498 | 9.498 | 108 | `#` | `cast_to` | `model_management.py:1527` |
| 9.254 | 1.727 | 108 | `#` | `set_attr_param` | `utils.py:973` |
| 8.898 | 8.898 | 7258 | `#` | `Module.__getattr__` | `module.py:1959` |
| 7.936 | 4.717 | 1047 | `#` | `Module.__setattr__` | `module.py:1976` |
| 7.476 | 7.473 | 2 | `#` | `VAE.__init__.<locals>.<lambda>` | `sd.py:498` |
| 7.251 | 0.603 | 244 | `#` | `ModelPatcher._load_list.<locals>.check_module_offload_mem` | `model_patcher.py:961` |
| 6.778 | 0.005 | 1 | `#` | `LoadedModel.model_memory_required` | `model_management.py:776` |
| 6.774 | 0.005 | 3 | `#` | `LoadedModel.model_memory` | `model_management.py:767` |
| 6.771 | 0.595 | 7 | `#` | `ModelPatcher.model_size` | `model_patcher.py:405` |
| 6.719 | 1.077 | 136 | `#` | `ModelPatcherDynamic.load.<locals>.setup_param` | `model_patcher.py:1918` |
| 6.500 | 6.500 | 356 | `#` | `Module._save_to_state_dict` | `module.py:2148` |
| 6.342 | 0.871 | 108 | `#` | `set_attr` | `utils.py:964` |
| 4.985 | 2.227 | 1012 | `#` | `Module._named_members` | `module.py:2650` |
| 4.221 | 1.350 | 652 | `#` | `_recurse_add_to_result` | `memory.py:232` |
| 4.115 | 0.741 | 1011 | `#` | `Module.named_parameters` | `module.py:2699` |
| 3.789 | 0.120 | 4 | `#` | `get_free_memory` | `model_management.py:1748` |
| 3.645 | 2.399 | 108 | `#` | `resolve_attr` | `utils.py:958` |
| 2.072 | 0.283 | 4 | `#` | `memory_stats` | `memory.py:242` |
| 1.995 | 0.122 | 1 | `#` | `free_memory` | `model_management.py:863` |

_8 more functions omitted._

## `golden_output`

- Stage wall: **301.508 ms**
- Calls attributed: **854**
- Distinct functions >= 1 ms: **17**

| wall ms | self ms | calls | bar | function | source |
|---:|---:|---:|:--|:--|:--|
| 452.557 | 0.109 | 2 | `##################################` | `_save` | `PngImagePlugin.py:1328` |
| 240.861 | 0.077 | 1 | `###########################` | `Image.save` | `Image.py:2592` |
| 226.186 | 220.722 | 1 | `##########################` | `_encode_tile` | `ImageFile.py:672` |
| 36.964 | 32.280 | 1 | `####` | `fromarray` | `Image.py:3378` |
| 14.332 | 14.332 | 1 | `##` | `preinit` | `Image.py:429` |
| 6.945 | 0.013 | 1 | `#` | `clip` | `fromnumeric.py:2207` |
| 6.933 | 0.031 | 1 | `#` | `_wrapfunc` | `fromnumeric.py:48` |
| 6.901 | 6.901 | 1 | `#` | `_clip` | `_methods.py:96` |
| 5.427 | 0.089 | 48 | `#` | `_idat.write` | `PngImagePlugin.py:1145` |
| 5.362 | 0.876 | 50 | `#` | `putchunk` | `PngImagePlugin.py:1127` |
| 4.685 | 0.017 | 1 | `#` | `frombuffer` | `Image.py:3288` |
| 4.657 | 0.028 | 1 | `#` | `frombytes` | `Image.py:3242` |
| 4.393 | 4.393 | 100 | `#` | `_crc32` | `PngImagePlugin.py:154` |
| 3.610 | 3.560 | 1 | `#` | `new` | `Image.py:3193` |
| 1.806 | 0.021 | 3 | `#` | `__create_fn__.<locals>.__init__` | `<string>:2` |
| 1.785 | 1.785 | 1 | `#` | `ReadyOutputArtifact.__post_init__` | `output_durability.py:73` |
| 1.014 | 0.975 | 1 | `#` | `Image.frombytes` | `Image.py:925` |
