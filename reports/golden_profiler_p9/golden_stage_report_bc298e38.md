# Golden stage decision report

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **853,823**

Tree floor: **1 ms**   Function rollup floor: **1 ms** total inclusive

## 1. Critical path and stage overlap

Sum of stage walls: **15,957.803 ms**   Timeline union: **12,055.722 ms**   Span: **12,065.868 ms**

Sum exceeds the union by **3,902.081 ms** -- that gap is the overlap the schedule is buying.

| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |
|:--|---:|---:|---:|:--|:--|
| `golden_restore` | 0.4 | 0.0 | 0.4 | 0.0% | `#` |
| `golden_request_setup` | 2.3 | 0.0 | 2.3 | 0.0% | `#` |
| `golden_clip_load` | 1,918.4 | 1,918.5 | -0.1 | 100.0% | `###########` |
| `golden_clip_forward` | 4,081.8 | 995.4 | 3,086.4 | 24.4% | `            ########################` |
| `golden_unet_load` | 3,082.9 | 0.0 | 3,082.9 | 0.0% | `           ##################` |
| `golden_sampler_prepare` | 55.6 | 48.3 | 7.4 | 86.7% | `                                    #` |
| `golden_vae_load` | 819.9 | 0.0 | 819.9 | 0.0% | `                                    #####` |
| `golden_sampling` | 4,786.9 | 3,957.6 | 829.3 | 82.7% | `                                    #############################` |
| `golden_sampler_tail` | 0.0 | 0.0 | 0.0 | 0.0% | `                                                                 #` |
| `golden_vae_decode` | 958.1 | 953.2 | 4.9 | 99.5% | `                                                                 ######` |
| `golden_output` | 251.3 | 247.4 | 4.0 | 98.4% | `                                                                       #` |

_Uncontended_ is the time during a stage when no other stage was running. That portion is protected: nothing else could absorb it. Overlapped time may be hidden by a longer sibling, so reducing it may not move root wall.

## 2. Function rollup across the whole request

`total incl ms` sums each call's wall, so a function called 24 times at 3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall contains its callees, so **totals are not additive down a call tree** -- `total self ms` is the non-overlapping part.

| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |
|---:|---:|---:|---:|---:|:--|:--|:--|
| 22,310.034 | 59 | 378.136 | 4,316.406 | 1.798 | `WrapperExecutor.execute` | `patcher_extension.py:108` | 2 |
| 15,227.310 | 526 | 28.949 | 3,593.019 | 1.677 | `Module._wrapped_call_impl` | `module.py:1779` | 3 |
| 15,225.631 | 526 | 28.946 | 3,593.006 | 3.955 | `Module._call_impl` | `module.py:1787` | 3 |
| 9,715.339 | 32 | 303.604 | 4,630.040 | 1.327 | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` | 6 |
| 9,714.692 | 5 | 1,942.938 | 4,630.356 | 0.220 | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` | 5 |
| 9,696.685 | 32 | 303.021 | 4,629.065 | 1.752 | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` | 6 |
| 5,257.245 | 3 | 1,752.415 | 2,789.109 | 0.064 | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` | 3 |
| 5,257.181 | 3 | 1,752.394 | 2,789.086 | 0.127 | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` | 3 |
| 5,257.053 | 3 | 1,752.351 | 2,789.025 | 2.083 | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` | 3 |
| 4,786.855 | 1 | 4,786.855 | 4,786.855 | 0.238 | `golden_sampling` | `golden_serial.py:13704` | 1 |
| 4,687.495 | 3 | 1,562.498 | 2,661.170 | 11.448 | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` | 3 |
| 4,628.708 | 1 | 4,628.708 | 4,628.708 | 0.547 | `ClownsharKSampler_Beta.main` | `samplers.py:1745` | 1 |
| 4,624.824 | 1 | 4,624.824 | 4,624.824 | 16.890 | `SharkSampler.main` | `samplers.py:153` | 1 |
| 4,536.859 | 2 | 2,268.429 | 4,316.677 | 0.194 | `CFGGuider.sample` | `samplers.py:1276` | 2 |
| 4,536.203 | 2 | 2,268.102 | 4,316.398 | 0.160 | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` | 2 |
| 4,534.408 | 2 | 2,267.204 | 4,315.960 | 0.016 | `WrapperExecutor.__call__` | `patcher_extension.py:103` | 2 |
| 4,534.327 | 2 | 2,267.163 | 4,315.936 | 4.065 | `CFGGuider.outer_sample` | `samplers.py:1240` | 2 |
| 4,322.454 | 309 | 13.989 | 262.920 | 5.340 | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` | 3 |
| 4,160.768 | 2 | 2,080.384 | 4,086.738 | 72.038 | `CFGGuider.inner_sample` | `samplers.py:1220` | 2 |
| 4,098.922 | 3 | 1,366.307 | 2,789.420 | 10.677 | `_WorkItem.run` | `thread.py:53` | 3 |
| 4,085.824 | 2 | 2,042.912 | 4,083.940 | 0.303 | `KSAMPLER.sample` | `samplers.py:983` | 2 |
| 4,083.656 | 74 | 55.185 | 4,081.467 | 1.155 | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` | 2 |
| 4,081.742 | 1 | 4,081.742 | 4,081.742 | 0.202 | `golden_clip_forward` | `golden_serial.py:12420` | 1 |
| 4,081.188 | 2 | 2,040.594 | 4,081.187 | 58.998 | `sample_rk_beta` | `rk_sampler_beta.py:110` | 2 |
| 4,068.691 | 1 | 4,068.691 | 4,068.691 | 0.046 | `CLIPTextEncode.encode` | `nodes.py:73` | 1 |
| 3,948.730 | 313 | 12.616 | 250.113 | 3,939.085 | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` | 3 |
| 3,856.380 | 1 | 3,856.380 | 3,856.380 | 0.026 | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` | 1 |
| 3,856.354 | 1 | 3,856.354 | 3,856.354 | 0.048 | `CLIP.encode_from_tokens` | `sd.py:396` | 1 |
| 3,684.234 | 14 | 263.160 | 2,585.875 | 7.866 | `BaseEventLoop._run_once` | `base_events.py:1845` | 5 |
| 3,596.212 | 1 | 3,596.212 | 3,596.212 | 0.063 | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` | 1 |
| 3,596.148 | 1 | 3,596.148 | 3,596.148 | 3.070 | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` | 1 |
| 3,593.024 | 1 | 3,593.024 | 3,593.024 | 0.005 | `SDClipModel.encode` | `sd1_clip.py:305` | 1 |
| 3,592.962 | 1 | 3,592.962 | 3,592.962 | 0.131 | `SDClipModel.forward` | `sd1_clip.py:260` | 1 |
| 3,492.611 | 1 | 3,492.611 | 3,492.611 | 0.011 | `BaseLlama.forward` | `llama.py:998` | 1 |
| 3,492.251 | 1 | 3,492.251 | 3,492.251 | 449.634 | `Llama2_.forward` | `llama.py:824` | 1 |
| 3,472.250 | 17 | 204.250 | 683.779 | 4.245 | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` | 1 |
| 3,466.936 | 17 | 203.937 | 682.628 | 1.652 | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` | 1 |
| 3,464.636 | 17 | 203.802 | 681.807 | 0.115 | `KSamplerX0Inpaint.__call__` | `samplers.py:634` | 1 |
| 3,464.524 | 17 | 203.796 | 681.796 | 0.092 | `CFGGuider.__call__` | `samplers.py:1207` | 1 |
| 3,464.433 | 17 | 203.790 | 681.787 | 0.214 | `CFGGuider.outer_predict_noise` | `samplers.py:1210` | 1 |
| 3,463.923 | 17 | 203.760 | 681.746 | 0.402 | `SharkGuider.predict_noise` | `samplers.py:99` | 1 |
| 3,463.523 | 17 | 203.737 | 681.722 | 0.418 | `sampling_function` | `samplers.py:609` | 1 |
| 3,456.729 | 2 | 1,728.364 | 2,789.156 | 0.068 | `thread_traced.<locals>._run` | `full_execution_trace.py:276` | 2 |
| 3,255.114 | 16 | 203.445 | 2,585.587 | 3,255.104 | `EpollSelector.select` | `selectors.py:451` | 5 |
| 2,687.259 | 17 | 158.074 | 669.643 | 0.071 | `calc_cond_batch` | `samplers.py:208` | 1 |
| 2,687.187 | 17 | 158.070 | 669.637 | 0.114 | `_calc_cond_batch_outer` | `samplers.py:214` | 1 |
| 2,685.807 | 17 | 157.989 | 669.503 | 12.222 | `_calc_cond_batch` | `samplers.py:221` | 1 |
| 2,643.285 | 2 | 1,321.642 | 1,816.705 | 0.025 | `Thread.run` | `threading.py:964` | 2 |
| 2,643.260 | 2 | 1,321.630 | 1,816.691 | 1,333.731 | `_worker` | `thread.py:69` | 2 |
| 2,633.914 | 17 | 154.936 | 660.388 | 0.199 | `BaseModel.apply_model` | `model_base.py:204` | 1 |
| 2,633.194 | 17 | 154.894 | 660.329 | 5.560 | `BaseModel._apply_model` | `model_base.py:211` | 1 |
| 2,616.276 | 17 | 153.899 | 656.586 | 2,616.276 | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` | 1 |
| 2,586.212 | 1 | 2,586.212 | 2,586.212 | 0.181 | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` | 1 |
| 2,185.861 | 1 | 2,185.861 | 2,185.861 | 0.220 | `Llama2_.compute_freqs_cis` | `llama.py:815` | 1 |
| 2,185.641 | 1 | 2,185.641 | 2,185.641 | 203.190 | `precompute_freqs_cis` | `llama.py:445` | 1 |
| 1,912.499 | 2 | 956.250 | 1,810.088 | 0.703 | `golden_clip_load` | `golden_serial.py:11497` | 1 |
| 1,800.715 | 1 | 1,800.715 | 1,800.715 | 1,800.715 | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` | 1 |
| 1,800.652 | 1 | 1,800.652 | 1,800.652 | 0.042 | `_read_golden_m2_clip` | `golden_serial.py:11462` | 1 |
| 1,800.606 | 1 | 1,800.606 | 1,800.606 | 0.022 | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1001` | 1 |
| 1,700.980 | 1017 | 1.673 | 1,595.408 | 95.716 | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` | 2 |

## 3. Per-stage call trees

Depth is uncapped; the wall floor limits it. Breadth is capped at 8 children plus any child at or above 10% of its parent.

### `golden_restore`

- Stage wall: **0.424 ms**

_Nothing below the stage body reached the threshold._

### `golden_request_setup`

- Stage wall: **2.327 ms**

- `golden_request_setup` 
  wall **2.327 ms**  self **2.327 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **2.303 ms**  self **0.068 ms**  `golden_serial.py:9977`

### `golden_clip_load`

- Stage wall: **1,918.406 ms**

- `golden_clip_load` 
  wall **1,918.406 ms**  self **15.566 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **1,816.705 ms**  self **0.014 ms**  `threading.py:964`
    - `_worker` 
      wall **1,816.691 ms**  self **1,174.951 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **641.725 ms**  self **10.640 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **631.054 ms**  self **0.211 ms**  `golden_serial.py:2341`
          - `load_text_encoder_state_dicts` 
            wall **565.389 ms**  self **0.187 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **564.682 ms**  self **0.230 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **474.370 ms**  self **0.023 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **474.347 ms**  self **0.032 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **474.315 ms**  self **2.001 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **472.314 ms**  self **0.263 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **450.802 ms**  self **2.556 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **443.113 ms**  self **8.864 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **433.974 ms**  self **273.152 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **113.580 ms**  self **15.361 ms**  `__init__.py:274`
                              - `loads` 
                                wall **98.218 ms**  self **0.007 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **98.211 ms**  self **0.025 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **98.187 ms**  self **98.187 ms**  `decoder.py:343`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **18.134 ms**  self **18.134 ms**  `tokenization_qwen2.py:174`
                            - `PreTrainedTokenizer.__init__` 
                              wall **16.827 ms**  self **0.955 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **15.142 ms**  self **3.849 ms**  `tokenization_utils.py:512`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **8.384 ms**  self **8.328 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **2.665 ms**  self **0.820 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **1.818 ms**  self **1.784 ms**  `tokenization_qwen2.py:215`
                            - `compile` 
                              wall **11.827 ms**  self **0.072 ms**  `_main.py:359`
                              - `_compile` 
                                wall **11.753 ms**  self **0.439 ms**  `_main.py:460`
                                - `Flag.__and__` 
                                  wall **5.857 ms**  self **0.236 ms**  `enum.py:1509`
                                  - `EnumType.__call__` 
                                    wall **5.621 ms**  self **0.006 ms**  `enum.py:686`
                                    - `Enum.__new__` 
                                      wall **5.615 ms**  self **5.615 ms**  `enum.py:1091`
                                - `Branch.pack_characters` 
                                  wall **2.331 ms**  self **0.005 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **2.326 ms**  self **0.010 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **2.270 ms**  self **0.017 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **2.137 ms**  self **0.035 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **2.054 ms**  self **0.007 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **2.048 ms**  self **2.048 ms**  `_regex_core.py:362`
                                - `_parse_pattern` 
                                  wall **1.382 ms**  self **0.027 ms**  `_regex_core.py:452`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **18.978 ms**  self **18.978 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **1.856 ms**  self **1.824 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **46.269 ms**  self **0.007 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **46.263 ms**  self **0.037 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **46.225 ms**  self **0.106 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **45.989 ms**  self **0.039 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **45.950 ms**  self **0.368 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **37.391 ms**  self **0.051 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **37.286 ms**  self **0.254 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **30.367 ms**  self **0.125 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **1.522 ms**  self **0.088 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.422 ms**  self **0.012 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.294 ms**  self **0.016 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.138 ms**  self **0.017 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.049 ms**  self **0.015 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.012 ms**  self **0.016 ms**  `llama.py:654`
                            - `disable_weight_init.Embedding.__init__` 
                              wall **6.288 ms**  self **0.108 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **6.025 ms**  self **6.025 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **8.040 ms**  self **0.125 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **4.825 ms**  self **0.004 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **4.821 ms**  self **0.017 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **4.788 ms**  self **0.011 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **4.742 ms**  self **0.033 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **33.377 ms**  self **0.445 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **27.963 ms**  self **0.020 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **27.941 ms**  self **0.034 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **27.906 ms**  self **0.137 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **27.768 ms**  self **0.049 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **26.881 ms**  self **0.036 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **25.606 ms**  self **0.154 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.272 ms**  self **0.016 ms**  `module.py:2589`
              - `archive_model_dtypes` 
                wall **6.755 ms**  self **1.230 ms**  `model_management.py:1045`
              - `ModelPatcherDynamic.__init__` 
                wall **2.856 ms**  self **0.063 ms**  `model_patcher.py:1757`
                - `ModelPatcher.__init__` 
                  wall **1.882 ms**  self **0.155 ms**  `model_patcher.py:341`
          - `_clip_meta_state_dict_from_header` 
            wall **65.317 ms**  self **58.695 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **6.353 ms**  self **4.944 ms**  `clip_qd_reader.py:300`
  - `golden_clip_load` 
    wall **1,810.088 ms**  self **0.282 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **1,800.652 ms**  self **0.042 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **1,800.606 ms**  self **0.022 ms**  `golden_model_transport.py:1001`
        - `GoldenModelTransport._load_sync` 
          wall **1,800.584 ms**  self **0.029 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **1,800.555 ms**  self **0.058 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **1,800.496 ms**  self **0.755 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **1,719.828 ms**  self **4.114 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **126.906 ms**  self **0.016 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **113.075 ms**  self **113.040 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **13.256 ms**  self **0.039 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **13.093 ms**  self **13.093 ms**  `golden_source_threads.py:486`
                - `GoldenQDTransport.publish` 
                  wall **69.011 ms**  self **0.017 ms**  `golden_qd_transport.py:3099`
                  - `TransportDispatcher.publish` 
                    wall **68.957 ms**  self **68.890 ms**  `golden_qd_transport.py:2153`
                - `SourceThreadProcess.wait_ready` 
                  wall **63.883 ms**  self **0.030 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **62.148 ms**  self **62.082 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **1.514 ms**  self **0.087 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **1.018 ms**  self **1.018 ms**  `golden_source_threads.py:486`
                - `SourceThreadProcess.wait_ready` 
                  wall **36.518 ms**  self **0.018 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **35.942 ms**  self **35.907 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **33.715 ms**  self **0.013 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **32.823 ms**  self **32.781 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **32.816 ms**  self **0.019 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **32.065 ms**  self **32.029 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **29.207 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **28.571 ms**  self **28.532 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **27.912 ms**  self **0.018 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **27.305 ms**  self **27.272 ms**  `golden_source_threads.py:892`
                _... 137 more children >= 1 ms omitted_
              - `GoldenModelTransport.inspect` 
                wall **44.665 ms**  self **0.048 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **44.342 ms**  self **43.768 ms**  `golden_model_transport.py:304`
              - `GpuDestinationPool.acquire` 
                wall **8.486 ms**  self **0.059 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **8.419 ms**  self **8.267 ms**  `golden_model_transport.py:156`
              - `SourceThreadProcess.snapshot` 
                wall **7.624 ms**  self **0.923 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **5.083 ms**  self **0.818 ms**  `golden_source_threads.py:589`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **6.800 ms**  self **0.146 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **4.249 ms**  self **0.032 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **4.203 ms**  self **0.010 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **4.187 ms**  self **0.007 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **4.177 ms**  self **4.174 ms**  `threading.py:288`
              - `GoldenModelTransport._views` 
                wall **6.691 ms**  self **6.691 ms**  `golden_model_transport.py:1910`
              - `SourceThreadProcess.snapshot` 
                wall **4.349 ms**  self **0.525 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **3.238 ms**  self **0.369 ms**  `golden_source_threads.py:589`
    - `GoldenTelemetryRecorder.event` 
      wall **5.364 ms**  self **0.013 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **5.351 ms**  self **0.018 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **5.333 ms**  self **0.013 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **5.318 ms**  self **0.055 ms**  `copy.py:227`
            - `deepcopy` 
              wall **5.144 ms**  self **0.003 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **5.140 ms**  self **0.011 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **3.885 ms**  self **0.002 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **3.883 ms**  self **0.183 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **1.780 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **1.777 ms**  self **0.503 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.002 ms**  self **0.002 ms**  `copy.py:128`
    - `_start_clip_skeleton_overlap` 
      wall **1.146 ms**  self **0.040 ms**  `golden_serial.py:2336`
      - `ThreadPoolExecutor.submit` 
        wall **1.034 ms**  self **0.020 ms**  `thread.py:161`
        - `ThreadPoolExecutor._adjust_thread_count` 
          wall **1.002 ms**  self **0.028 ms**  `thread.py:180`
  - `golden.clip_load.source_open_read` 
    wall **1,800.715 ms**  self **1,800.715 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **102.411 ms**  self **0.421 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **70.267 ms**  self **1.561 ms**  `golden_serial.py:13011`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **8.545 ms**  self **0.261 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **3.473 ms**  self **0.004 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **3.470 ms**  self **0.547 ms**  `module.py:2650`
      - `validate_qd_adoption` 
        wall **8.024 ms**  self **1.580 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **3.081 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **3.079 ms**  self **0.618 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **7.310 ms**  self **0.223 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.171 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.169 ms**  self **0.392 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.832 ms**  self **0.259 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **1.976 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.973 ms**  self **0.428 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.713 ms**  self **0.204 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.368 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.365 ms**  self **0.433 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.007 ms**  self **0.222 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.066 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.062 ms**  self **0.420 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.424 ms**  self **0.199 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **1.750 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.748 ms**  self **0.430 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **21.127 ms**  self **0.387 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **16.735 ms**  self **0.011 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **16.722 ms**  self **0.021 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **16.700 ms**  self **0.126 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **16.574 ms**  self **0.013 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **16.132 ms**  self **0.024 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **14.813 ms**  self **0.088 ms**  `module.py:2589`
    - `_clip_compute_identity` 
      wall **8.462 ms**  self **0.033 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **8.272 ms**  self **2.378 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **1.730 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.727 ms**  self **0.391 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **70.306 ms**  self **70.306 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **21.160 ms**  self **21.160 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.compute_ready_proof` 
    wall **8.479 ms**  self **8.479 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_patcher_construction` 
    wall **2.168 ms**  self **0.946 ms**  `full_execution_trace.py:330`

### `golden_clip_forward`

- Stage wall: **4,081.834 ms**

- `golden_clip_forward` 
  wall **4,081.834 ms**  self **4,081.834 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **4,081.742 ms**  self **0.202 ms**  `golden_serial.py:12420`
    - `GoldenSerialRunner.run_closure` 
      wall **4,071.964 ms**  self **0.057 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,069.163 ms**  self **0.052 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,068.875 ms**  self **0.033 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **4,068.691 ms**  self **0.046 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **3,856.380 ms**  self **0.026 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **3,856.354 ms**  self **0.048 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **3,596.212 ms**  self **0.063 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **3,596.148 ms**  self **3.070 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **3,593.024 ms**  self **0.005 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **3,593.019 ms**  self **0.013 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **3,593.006 ms**  self **0.044 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **3,592.962 ms**  self **0.131 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **3,492.645 ms**  self **0.009 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **3,492.636 ms**  self **0.025 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **3,492.611 ms**  self **0.011 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **3,492.598 ms**  self **0.009 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **3,492.589 ms**  self **0.338 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **3,492.251 ms**  self **449.634 ms**  `llama.py:824`
                                        - `prefetch_queue_pop` 
                                          wall **657.139 ms**  self **0.012 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **657.127 ms**  self **0.012 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **657.115 ms**  self **0.008 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **657.107 ms**  self **0.027 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **657.079 ms**  self **0.539 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **562.604 ms**  self **0.008 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **562.596 ms**  self **0.190 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **562.406 ms**  self **116.848 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **340.208 ms**  self **0.010 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **340.198 ms**  self **0.021 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **340.176 ms**  self **0.023 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **340.131 ms**  self **338.036 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **2.073 ms**  self **0.012 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **2.062 ms**  self **1.984 ms**  `ops.py:337`
                                                        - `apply_rope` 
                                                          wall **78.767 ms**  self **78.767 ms**  `llama.py:492`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **25.219 ms**  self **0.006 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **25.213 ms**  self **0.011 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **25.202 ms**  self **0.041 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **25.142 ms**  self **0.351 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **24.770 ms**  self **0.013 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **24.757 ms**  self **24.729 ms**  `ops.py:337`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **48.843 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **48.836 ms**  self **0.008 ms**  `module.py:1787`
                                                      - `RMSNorm.forward` 
                                                        wall **48.828 ms**  self **0.012 ms**  `llama.py:436`
                                                        - `rms_norm` 
                                                          wall **48.814 ms**  self **0.052 ms**  `rmsnorm.py:7`
                                                          - `rms_norm` 
                                                            wall **48.686 ms**  self **48.686 ms**  `functional.py:2998`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **44.654 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **44.649 ms**  self **0.016 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **44.633 ms**  self **0.259 ms**  `llama.py:644`
                                                        - `silu` 
                                                          wall **30.558 ms**  self **30.558 ms**  `functional.py:2429`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **13.144 ms**  self **0.010 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **13.134 ms**  self **0.006 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **13.128 ms**  self **0.010 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **13.096 ms**  self **0.295 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **12.787 ms**  self **0.010 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **12.777 ms**  self **12.743 ms**  `ops.py:337`
                                        - `prefetch_queue_pop` 
                                          wall **6.625 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **6.623 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **6.618 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **6.614 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **6.602 ms**  self **0.107 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **4.535 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **4.529 ms**  self **0.043 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **4.486 ms**  self **1.508 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.426 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.422 ms**  self **0.008 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.413 ms**  self **0.148 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **4.884 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.882 ms**  self **0.007 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.874 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.869 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.857 ms**  self **0.137 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.658 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.652 ms**  self **0.063 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.590 ms**  self **1.681 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.744 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.742 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.738 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.734 ms**  self **0.009 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.726 ms**  self **0.159 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.374 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.368 ms**  self **0.024 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.344 ms**  self **1.370 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.576 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.574 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.568 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.563 ms**  self **0.014 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.548 ms**  self **0.142 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.318 ms**  self **0.009 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.309 ms**  self **0.018 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.291 ms**  self **1.258 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.424 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.423 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.419 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.415 ms**  self **0.006 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.409 ms**  self **0.097 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.198 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.195 ms**  self **0.016 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.179 ms**  self **1.608 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.378 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.376 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.370 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.365 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.353 ms**  self **0.196 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.758 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.754 ms**  self **0.055 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.699 ms**  self **1.122 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.262 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.259 ms**  self **0.007 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.252 ms**  self **0.007 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.245 ms**  self **0.011 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.234 ms**  self **0.204 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.681 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.677 ms**  self **0.017 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.660 ms**  self **1.202 ms**  `llama.py:540`
                                        _... 21 more children >= 1 ms omitted_
  - `BaseEventLoop._run_once` 
    wall **61.651 ms**  self **0.010 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **61.551 ms**  self **13.975 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **61.493 ms**  self **0.010 ms**  `golden_serial.py:15543`

### `golden_unet_load`

- Stage wall: **3,082.906 ms**

- `golden_unet_load` 
  wall **3,082.906 ms**  self **289.734 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **2,789.420 ms**  self **0.022 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **2,789.156 ms**  self **0.047 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **2,789.109 ms**  self **0.023 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **2,789.086 ms**  self **0.061 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **2,789.025 ms**  self **1.055 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **2,661.170 ms**  self **7.145 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **249.958 ms**  self **0.030 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **249.440 ms**  self **249.362 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **48.284 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **48.074 ms**  self **48.033 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **45.925 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **44.887 ms**  self **44.859 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **45.315 ms**  self **0.012 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **32.745 ms**  self **32.719 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **12.158 ms**  self **0.034 ms**  `golden_source_threads.py:1036`
                  - `_FileLock.__exit__` 
                    wall **6.745 ms**  self **6.745 ms**  `golden_source_threads.py:493`
                  - `_FileLock.__enter__` 
                    wall **5.354 ms**  self **5.354 ms**  `golden_source_threads.py:486`
              - `SourceThreadProcess.wait_ready` 
                wall **39.391 ms**  self **0.011 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **29.035 ms**  self **29.018 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **9.861 ms**  self **0.036 ms**  `golden_source_threads.py:1036`
                  - `_FileLock.__enter__` 
                    wall **5.176 ms**  self **5.176 ms**  `golden_source_threads.py:486`
                  - `_FileLock.__exit__` 
                    wall **4.628 ms**  self **4.628 ms**  `golden_source_threads.py:493`
              - `SourceThreadProcess.wait_ready` 
                wall **38.906 ms**  self **0.054 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **36.738 ms**  self **36.633 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **1.677 ms**  self **0.089 ms**  `golden_source_threads.py:1036`
                  - `_FileLock.__enter__` 
                    wall **1.059 ms**  self **1.059 ms**  `golden_source_threads.py:486`
              - `SourceThreadProcess.wait_ready` 
                wall **38.725 ms**  self **0.011 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **38.388 ms**  self **38.360 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **37.300 ms**  self **0.018 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **36.393 ms**  self **36.353 ms**  `golden_source_threads.py:892`
              _... 179 more children >= 1 ms omitted_
            - `GoldenModelTransport._views` 
              wall **64.494 ms**  self **64.494 ms**  `golden_model_transport.py:1910`
            - `SourceThreadProcess.snapshot` 
              wall **16.216 ms**  self **3.332 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **10.747 ms**  self **0.965 ms**  `golden_source_threads.py:589`
            - `GpuDestinationPool.acquire` 
              wall **14.593 ms**  self **0.050 ms**  `golden_model_transport.py:183`
              - `GpuDestinationPool._allocate` 
                wall **14.532 ms**  self **14.285 ms**  `golden_model_transport.py:156`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **14.104 ms**  self **0.205 ms**  `golden_qd_transport.py:3130`
              - `_Telemetry.snapshot` 
                wall **8.835 ms**  self **0.011 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **8.825 ms**  self **0.190 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **8.592 ms**  self **0.010 ms**  `golden_qd_transport.py:2016`
                    - `_json_safe.<locals>.<dictcomp>` 
                      wall **8.572 ms**  self **0.238 ms**  `golden_qd_transport.py:2022`
                      - `_json_safe` 
                        wall **7.301 ms**  self **0.010 ms**  `golden_qd_transport.py:2016`
                        - `_BaseGenericAlias.__instancecheck__` 
                          wall **7.285 ms**  self **0.001 ms**  `typing.py:1304`
                          - `_SpecialGenericAlias.__subclasscheck__` 
                            wall **7.283 ms**  self **7.283 ms**  `typing.py:1579`
              - `GoldenQDTransport.drain` 
                wall **3.472 ms**  self **0.017 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **3.447 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **3.434 ms**  self **0.008 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **3.423 ms**  self **3.419 ms**  `threading.py:288`
              - `GoldenQDTransport._record_ranges` 
                wall **1.086 ms**  self **0.860 ms**  `golden_qd_transport.py:3261`
            - `SourceThreadProcess.snapshot` 
              wall **13.469 ms**  self **1.448 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **10.442 ms**  self **1.243 ms**  `golden_source_threads.py:589`
            - `GoldenModelTransport.inspect` 
              wall **1.776 ms**  self **0.016 ms**  `golden_model_transport.py:973`
              - `_file_identity` 
                wall **1.760 ms**  self **1.760 ms**  `golden_model_transport.py:274`
  - `golden.unet.source_h2d_transport` 
    wall **2,586.212 ms**  self **0.181 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop._run_once` 
    wall **2,585.875 ms**  self **0.040 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **2,585.587 ms**  self **2,585.583 ms**  `selectors.py:451`
  - `Llama2_.compute_freqs_cis` 
    wall **2,185.861 ms**  self **0.220 ms**  `llama.py:815`
    - `precompute_freqs_cis` 
      wall **2,185.641 ms**  self **203.190 ms**  `llama.py:445`
      - `_register_overrides_from_graph.<locals>.eager_router` 
        wall **1,595.408 ms**  self **0.027 ms**  `registry.py:938`
        - `_register_overrides_from_graph.<locals>._dispatch` 
          wall **1,595.376 ms**  self **0.062 ms**  `registry.py:926`
          - `OpOverloadPacket.__call__` 
            wall **1,594.032 ms**  self **0.145 ms**  `_ops.py:1338`
            - `_bmm_outer_product_impl` 
              wall **1,593.887 ms**  self **40.944 ms**  `triton_impl.py:18`
              - `bmm_outer_product` 
                wall **1,552.844 ms**  self **0.552 ms**  `triton_kernels.py:77`
                - `_make_wrapper.<locals>.wrapper` 
                  wall **1,552.136 ms**  self **0.008 ms**  `instrumentation.py:202`
                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                    wall **1,552.047 ms**  self **0.040 ms**  `jit.py:374`
                    - `JITFunction.run` 
                      wall **1,552.008 ms**  self **0.153 ms**  `jit.py:726`
                      - `DriverConfig.active` 
                        wall **845.760 ms**  self **0.006 ms**  `driver.py:36`
                        - `DriverConfig.default` 
                          wall **845.754 ms**  self **0.011 ms**  `driver.py:30`
                          - `_create_driver` 
                            wall **845.743 ms**  self **0.041 ms**  `driver.py:8`
                            - `CudaDriver.__init__` 
                              wall **845.620 ms**  self **0.031 ms**  `driver.py:341`
                              - `CudaUtils.__init__` 
                                wall **845.569 ms**  self **0.049 ms**  `driver.py:100`
                                - `compile_module_from_file` 
                                  wall **817.738 ms**  self **0.011 ms**  `build.py:193`
                                  - `_compile_so_from_file` 
                                    wall **817.728 ms**  self **2.353 ms**  `build.py:157`
                                    - `_compile_so` 
                                      wall **815.300 ms**  self **1.070 ms**  `build.py:132`
                                      - `_build` 
                                        wall **796.786 ms**  self **0.061 ms**  `build.py:60`
                                        - `check_call` 
                                          wall **791.417 ms**  self **0.013 ms**  `subprocess.py:398`
                                          - `call` 
                                            wall **791.402 ms**  self **0.018 ms**  `subprocess.py:381`
                                            - `Popen.wait` 
                                              wall **785.812 ms**  self **0.002 ms**  `subprocess.py:1259`
                                              - `Popen._wait` 
                                                wall **785.810 ms**  self **0.013 ms**  `subprocess.py:2014`
                                                - `Popen._try_wait` 
                                                  wall **785.795 ms**  self **785.795 ms**  `subprocess.py:2001`
                                            - `Popen.__init__` 
                                              wall **5.562 ms**  self **0.024 ms**  `subprocess.py:807`
                                              - `Popen._execute_child` 
                                                wall **5.327 ms**  self **5.058 ms**  `subprocess.py:1789`
                                        - `_find_compiler` 
                                          wall **4.121 ms**  self **0.040 ms**  `build.py:21`
                                          - `which` 
                                            wall **2.129 ms**  self **0.090 ms**  `shutil.py:1452`
                                          - `which` 
                                            wall **1.952 ms**  self **0.105 ms**  `shutil.py:1452`
                                      - `_get_cache_manager` 
                                        wall **14.704 ms**  self **1.484 ms**  `build.py:117`
                                        - `platform_key` 
                                          wall **11.519 ms**  self **0.027 ms**  `build.py:94`
                                          - `architecture` 
                                            wall **11.477 ms**  self **0.042 ms**  `platform.py:646`
                                            - `_syscmd_file` 
                                              wall **11.435 ms**  self **0.834 ms**  `platform.py:602`
                                              - `check_output` 
                                                wall **9.933 ms**  self **0.009 ms**  `subprocess.py:417`
                                                - `run` 
                                                  wall **9.924 ms**  self **0.010 ms**  `subprocess.py:506`
                                                  - `Popen.__init__` 
                                                    wall **9.914 ms**  self **0.496 ms**  `subprocess.py:807`
                                                    - `Popen._execute_child` 
                                                      wall **9.019 ms**  self **8.369 ms**  `subprocess.py:1789`
                                        - `get_cache_manager` 
                                          wall **1.701 ms**  self **0.035 ms**  `cache.py:258`
                                          - `FileCacheManager.__init__` 
                                            wall **1.366 ms**  self **1.353 ms**  `cache.py:38`
                                - `library_dirs` 
                                  wall **27.782 ms**  self **0.021 ms**  `driver.py:49`
                                  - `libcuda_dirs` 
                                    wall **27.761 ms**  self **0.263 ms**  `driver.py:25`
                                    - `check_output` 
                                      wall **27.211 ms**  self **0.022 ms**  `subprocess.py:417`
                                      - `run` 
                                        wall **27.186 ms**  self **0.073 ms**  `subprocess.py:506`
                                        - `Popen.communicate` 
                                          wall **15.555 ms**  self **15.435 ms**  `subprocess.py:1165`
                                        - `Popen.__init__` 
                                          wall **11.548 ms**  self **1.374 ms**  `subprocess.py:807`
                                          - `Popen._execute_child` 
                                            wall **9.846 ms**  self **9.270 ms**  `subprocess.py:1789`
                      - `JITFunction._do_compile` 
                        wall **374.918 ms**  self **0.065 ms**  `jit.py:877`
                        - `compile` 
                          wall **374.827 ms**  self **24.240 ms**  `compiler.py:226`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **80.800 ms**  self **0.108 ms**  `compiler.py:605`
                            - `CUDABackend.make_llir` 
                              wall **80.692 ms**  self **80.556 ms**  `compiler.py:367`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **68.775 ms**  self **0.011 ms**  `compiler.py:606`
                            - `CUDABackend.make_ptx` 
                              wall **68.764 ms**  self **67.338 ms**  `compiler.py:480`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **55.438 ms**  self **0.041 ms**  `compiler.py:607`
                            - `CUDABackend.make_cubin` 
                              wall **55.394 ms**  self **1.330 ms**  `compiler.py:513`
                              - `run` 
                                wall **52.774 ms**  self **0.029 ms**  `subprocess.py:506`
                                - `Popen.communicate` 
                                  wall **48.114 ms**  self **0.007 ms**  `subprocess.py:1165`
                                  - `Popen.wait` 
                                    wall **48.107 ms**  self **0.003 ms**  `subprocess.py:1259`
                                    - `Popen._wait` 
                                      wall **48.103 ms**  self **0.019 ms**  `subprocess.py:2014`
                                      - `Popen._try_wait` 
                                        wall **48.081 ms**  self **48.081 ms**  `subprocess.py:2001`
                                - `Popen.__init__` 
                                  wall **4.616 ms**  self **0.025 ms**  `subprocess.py:807`
                                  - `Popen._execute_child` 
                                    wall **4.534 ms**  self **0.037 ms**  `subprocess.py:1789`
                                    - `Popen._posix_spawn` 
                                      wall **4.498 ms**  self **4.469 ms**  `subprocess.py:1750`
                          - `get_cache_key` 
                            wall **39.027 ms**  self **0.026 ms**  `cache.py:319`
                            - `CUDABackend.hash` 
                              wall **34.566 ms**  self **0.013 ms**  `compiler.py:611`
                              - `get_ptxas_version` 
                                wall **34.553 ms**  self **0.012 ms**  `compiler.py:42`
                                - `get_ptxas` 
                                  wall **24.214 ms**  self **0.004 ms**  `compiler.py:38`
                                  - `env_base.__get__` 
                                    wall **24.210 ms**  self **0.003 ms**  `knobs.py:76`
                                    - `env_nvidia_tool.get` 
                                      wall **24.207 ms**  self **0.004 ms**  `knobs.py:203`
                                      - `env_nvidia_tool.transform` 
                                        wall **24.203 ms**  self **0.010 ms**  `knobs.py:206`
                                        - `NvidiaTool.from_path` 
                                          wall **24.193 ms**  self **0.017 ms**  `knobs.py:181`
                                          - `check_output` 
                                            wall **23.799 ms**  self **0.013 ms**  `subprocess.py:417`
                                            - `run` 
                                              wall **23.784 ms**  self **0.023 ms**  `subprocess.py:506`
                                              - `Popen.__init__` 
                                                wall **12.717 ms**  self **0.639 ms**  `subprocess.py:807`
                                                - `Popen._execute_child` 
                                                  wall **11.874 ms**  self **11.529 ms**  `subprocess.py:1789`
                                              - `Popen.communicate` 
                                                wall **11.036 ms**  self **10.995 ms**  `subprocess.py:1165`
                                - `check_output` 
                                  wall **10.321 ms**  self **0.011 ms**  `subprocess.py:417`
                                  - `run` 
                                    wall **10.308 ms**  self **0.018 ms**  `subprocess.py:506`
                                    - `Popen.communicate` 
                                      wall **7.135 ms**  self **6.961 ms**  `subprocess.py:1165`
                                    - `Popen.__init__` 
                                      wall **3.146 ms**  self **0.156 ms**  `subprocess.py:807`
                                      - `Popen._execute_child` 
                                        wall **2.860 ms**  self **2.730 ms**  `subprocess.py:1789`
                            - `CUDAOptions.hash` 
                              wall **2.361 ms**  self **0.046 ms**  `compiler.py:153`
                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                wall **2.286 ms**  self **0.010 ms**  `compiler.py:155`
                                - `file_hash` 
                                  wall **2.276 ms**  self **2.276 ms**  `compiler.py:97`
                            - `ASTSource.hash` 
                              wall **2.075 ms**  self **0.040 ms**  `compiler.py:71`
                              - `JITCallable.cache_key` 
                                wall **2.024 ms**  self **0.072 ms**  `jit.py:515`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **36.658 ms**  self **0.100 ms**  `compiler.py:602`
                            - `CUDABackend.make_ttgir` 
                              wall **36.559 ms**  self **36.559 ms**  `compiler.py:260`
                          - `ASTSource.make_ir` 
                            wall **33.181 ms**  self **0.031 ms**  `compiler.py:78`
                            - `ast_to_ttir` 
                              wall **33.150 ms**  self **2.328 ms**  `code_generator.py:1662`
                              - `CodeGenerator.visit` 
                                wall **27.629 ms**  self **0.047 ms**  `code_generator.py:1581`
                                - `NodeVisitor.visit` 
                                  wall **27.583 ms**  self **0.007 ms**  `ast.py:414`
                                  - `CodeGenerator.visit_Module` 
                                    wall **27.575 ms**  self **0.004 ms**  `code_generator.py:519`
                                    - `NodeVisitor.generic_visit` 
                                      wall **27.572 ms**  self **0.010 ms**  `ast.py:420`
                                      - `CodeGenerator.visit` 
                                        wall **27.558 ms**  self **0.062 ms**  `code_generator.py:1581`
                                        - `NodeVisitor.visit` 
                                          wall **27.496 ms**  self **0.015 ms**  `ast.py:414`
                                          - `CodeGenerator.visit_FunctionDef` 
                                            wall **27.481 ms**  self **0.198 ms**  `code_generator.py:628`
                                            - `CodeGenerator.visit_compound_statement` 
                                              wall **25.947 ms**  self **0.040 ms**  `code_generator.py:508`
                                              - `CodeGenerator.visit` 
                                                wall **6.102 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **6.096 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **6.094 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **6.046 ms**  self **0.021 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **6.024 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **6.022 ms**  self **0.012 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **5.555 ms**  self **0.016 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **5.539 ms**  self **0.113 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **5.168 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **5.164 ms**  self **0.002 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **5.162 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **5.160 ms**  self **0.008 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **5.150 ms**  self **5.150 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **4.772 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **4.765 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **4.762 ms**  self **0.012 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **4.716 ms**  self **0.016 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **4.700 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **4.697 ms**  self **0.017 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **4.576 ms**  self **0.008 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **4.567 ms**  self **0.063 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **4.257 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **4.252 ms**  self **0.003 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **4.249 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **4.247 ms**  self **0.008 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **4.235 ms**  self **4.235 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **3.346 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **3.337 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Expr` 
                                                    wall **3.334 ms**  self **0.006 ms**  `code_generator.py:1556`
                                                    - `NodeVisitor.generic_visit` 
                                                      wall **3.328 ms**  self **0.008 ms**  `ast.py:420`
                                                      - `CodeGenerator.visit` 
                                                        wall **3.318 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                        - `NodeVisitor.visit` 
                                                          wall **3.311 ms**  self **0.003 ms**  `ast.py:414`
                                                          - `CodeGenerator.visit_Call` 
                                                            wall **3.308 ms**  self **0.015 ms**  `code_generator.py:1455`
                                                            - `CodeGenerator.visit` 
                                                              wall **3.000 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                              - `NodeVisitor.visit` 
                                                                wall **2.993 ms**  self **0.005 ms**  `ast.py:414`
                                                                - `CodeGenerator.visit_BinOp` 
                                                                  wall **2.988 ms**  self **0.011 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **1.734 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **1.726 ms**  self **0.005 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **1.721 ms**  self **1.721 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **1.124 ms**  self **0.033 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **1.090 ms**  self **0.008 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **1.082 ms**  self **1.082 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **2.582 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.574 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.571 ms**  self **0.012 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.522 ms**  self **0.035 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.488 ms**  self **0.014 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.473 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.592 ms**  self **0.190 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.402 ms**  self **0.007 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.395 ms**  self **0.009 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **2.088 ms**  self **0.012 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.076 ms**  self **0.004 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.072 ms**  self **0.026 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.969 ms**  self **0.237 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.732 ms**  self **0.010 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.722 ms**  self **0.005 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.191 ms**  self **0.003 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.188 ms**  self **0.003 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.186 ms**  self **0.002 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.184 ms**  self **0.004 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.180 ms**  self **0.005 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.173 ms**  self **0.037 ms**  `semantic.py:230`
                                                                      - `TritonSemantic.binary_op_sanitize_overflow_impl` 
                                                                        wall **1.071 ms**  self **1.071 ms**  `semantic.py:212`
                                              - `CodeGenerator.visit` 
                                                wall **2.039 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.032 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.030 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.971 ms**  self **0.025 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.946 ms**  self **0.005 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **1.941 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.230 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.222 ms**  self **0.003 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.220 ms**  self **0.006 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.930 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.923 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.921 ms**  self **0.014 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.824 ms**  self **0.029 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.795 ms**  self **0.006 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.789 ms**  self **0.004 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.326 ms**  self **0.003 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.323 ms**  self **0.002 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.321 ms**  self **0.002 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.319 ms**  self **0.004 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.315 ms**  self **0.006 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.308 ms**  self **0.039 ms**  `semantic.py:230`
                                                                      - `TritonSemantic.binary_op_sanitize_overflow_impl` 
                                                                        wall **1.174 ms**  self **1.174 ms**  `semantic.py:212`
                              - `JITCallable.parse` 
                                wall **2.037 ms**  self **0.014 ms**  `jit.py:546`
                                - `parse` 
                                  wall **2.023 ms**  self **2.023 ms**  `ast.py:33`
                          - `FileCacheManager.put` 
                            wall **11.268 ms**  self **10.597 ms**  `cache.py:103`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **8.892 ms**  self **0.061 ms**  `compiler.py:601`
                            - `CUDABackend.make_ttir` 
                              wall **8.831 ms**  self **8.831 ms**  `compiler.py:244`
                          _... 6 more children >= 1 ms omitted_
                      - `dynamic_func` 
                        wall **309.050 ms**  self **309.019 ms**  `<string>:2`
                      - `CompiledKernel.launch_metadata` 
                        wall **19.443 ms**  self **0.027 ms**  `compiler.py:493`
                        - `CompiledKernel._init_handles` 
                          wall **19.414 ms**  self **0.351 ms**  `compiler.py:448`
                          - `max_shared_mem` 
                            wall **18.671 ms**  self **18.670 ms**  `compiler.py:133`
                      - `JITFunction._pack_args` 
                        wall **1.348 ms**  self **0.034 ms**  `jit.py:702`
                        - `CUDABackend.parse_options` 
                          wall **1.082 ms**  self **0.053 ms**  `compiler.py:186`
          - `_OpNamespace.__getattr__` 
            wall **1.105 ms**  self **0.037 ms**  `_ops.py:1448`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **249.007 ms**  self **0.020 ms**  `_tensor.py:32`
        - `Tensor.__rpow__` 
          wall **248.987 ms**  self **248.987 ms**  `_tensor.py:1155`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **138.036 ms**  self **0.020 ms**  `_tensor.py:32`
        - `Tensor.__rdiv__` 
          wall **138.016 ms**  self **138.016 ms**  `_tensor.py:1120`
  - `CLIP.load_model` 
    wall **259.884 ms**  self **0.039 ms**  `sd.py:459`
    - `load_models_gpu` 
      wall **259.839 ms**  self **0.340 ms**  `model_management.py:909`
      - `LoadedModel.model_load` 
        wall **202.522 ms**  self **0.051 ms**  `model_management.py:782`
        - `LoadedModel.model_use_more_vram` 
          wall **202.408 ms**  self **0.022 ms**  `model_management.py:817`
          - `ModelPatcherDynamic.partially_load` 
            wall **202.384 ms**  self **0.320 ms**  `model_patcher.py:2141`
            - `ModelPatcherDynamic.load` 
              wall **201.918 ms**  self **12.809 ms**  `model_patcher.py:1853`
              - `ModelPatcher._load_list` 
                wall **131.696 ms**  self **52.329 ms**  `model_patcher.py:945`
                - `module_size` 
                  wall **6.122 ms**  self **0.008 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **6.114 ms**  self **0.012 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **6.102 ms**  self **6.102 ms**  `module.py:2148`
                - `module_size` 
                  wall **6.078 ms**  self **0.007 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **6.072 ms**  self **0.019 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **6.053 ms**  self **6.053 ms**  `module.py:2148`
                - `module_size` 
                  wall **5.915 ms**  self **0.008 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **5.907 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **5.898 ms**  self **5.898 ms**  `module.py:2148`
                - `module_size` 
                  wall **3.067 ms**  self **0.005 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **3.062 ms**  self **0.011 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **3.051 ms**  self **3.051 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.701 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.698 ms**  self **0.006 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.692 ms**  self **1.692 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.596 ms**  self **0.004 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.592 ms**  self **0.006 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.586 ms**  self **1.586 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.318 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.315 ms**  self **0.006 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.309 ms**  self **1.309 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.197 ms**  self **0.005 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.192 ms**  self **0.008 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.184 ms**  self **1.184 ms**  `module.py:2148`
                _... 3 more children >= 1 ms omitted_
              - `Module.named_buffers` 
                wall **3.048 ms**  self **0.008 ms**  `module.py:2754`
                - `Module._named_members` 
                  wall **3.040 ms**  self **0.504 ms**  `module.py:2650`
              - `ModelPatcherDynamic._vbar_get` 
                wall **3.025 ms**  self **0.043 ms**  `model_patcher.py:1797`
                - `ModelVBAR.__init__` 
                  wall **2.981 ms**  self **2.851 ms**  `model_vbar.py:50`
              - `set_attr_param` 
                wall **1.348 ms**  self **0.004 ms**  `utils.py:973`
                - `set_attr` 
                  wall **1.339 ms**  self **0.007 ms**  `utils.py:964`
                  - `resolve_attr` 
                    wall **1.311 ms**  self **1.301 ms**  `utils.py:958`
      - `LoadedModel.model_memory_required` 
        wall **54.791 ms**  self **0.013 ms**  `model_management.py:776`
        - `LoadedModel.model_memory` 
          wall **54.775 ms**  self **0.012 ms**  `model_management.py:767`
          - `ModelPatcher.model_size` 
            wall **54.763 ms**  self **7.322 ms**  `model_patcher.py:405`
            - `module_size` 
              wall **47.441 ms**  self **0.388 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **47.053 ms**  self **0.029 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **47.019 ms**  self **0.029 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **46.700 ms**  self **0.030 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **46.664 ms**  self **0.036 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **46.286 ms**  self **0.131 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **15.165 ms**  self **0.027 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **13.596 ms**  self **0.035 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **10.242 ms**  self **0.013 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **10.230 ms**  self **10.230 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **3.279 ms**  self **0.020 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.260 ms**  self **3.260 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **9.322 ms**  self **0.036 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **8.659 ms**  self **0.070 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **3.430 ms**  self **0.372 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.058 ms**  self **3.058 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **1.639 ms**  self **0.029 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.610 ms**  self **1.610 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **1.358 ms**  self **0.013 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.345 ms**  self **1.345 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **2.698 ms**  self **0.027 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.891 ms**  self **0.012 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.811 ms**  self **0.007 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.804 ms**  self **1.804 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **1.818 ms**  self **0.025 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.650 ms**  self **0.040 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.222 ms**  self **0.036 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.452 ms**  self **0.015 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.019 ms**  self **0.020 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.037 ms**  self **0.016 ms**  `module.py:2199`
      - `get_free_memory` 
        wall **1.468 ms**  self **0.043 ms**  `model_management.py:1748`
  - `_unet_load_with_worker_stage` 
    wall **228.249 ms**  self **0.052 ms**  `golden_parallel.py:517`
    - `golden_unet_load` 
      wall **228.193 ms**  self **0.075 ms**  `golden_serial.py:13225`
      - `GoldenModelTransport.inspect` 
        wall **227.975 ms**  self **0.040 ms**  `golden_model_transport.py:973`
        - `_parse_layout` 
          wall **213.928 ms**  self **212.913 ms**  `golden_model_transport.py:304`
        - `_file_identity` 
          wall **14.007 ms**  self **14.007 ms**  `golden_model_transport.py:274`
  - `CLIP.tokenize` 
    wall **212.266 ms**  self **0.014 ms**  `sd.py:322`
    - `ZImageTokenizer.tokenize_with_weights` 
      wall **212.252 ms**  self **0.018 ms**  `z_image.py:17`
      - `SD1Tokenizer.tokenize_with_weights` 
        wall **212.233 ms**  self **0.049 ms**  `sd1_clip.py:698`
        - `SDTokenizer.tokenize_with_weights` 
          wall **212.184 ms**  self **0.091 ms**  `sd1_clip.py:572`
          - `PreTrainedTokenizerBase.__call__` 
            wall **211.436 ms**  self **0.027 ms**  `tokenization_utils_base.py:2827`
            - `PreTrainedTokenizerBase._call_one` 
              wall **211.408 ms**  self **0.015 ms**  `tokenization_utils_base.py:2925`
              - `PreTrainedTokenizerBase.encode_plus` 
                wall **211.392 ms**  self **0.018 ms**  `tokenization_utils_base.py:3043`
                - `PreTrainedTokenizer._encode_plus` 
                  wall **211.365 ms**  self **0.021 ms**  `tokenization_utils.py:743`
                  - `PreTrainedTokenizerBase.prepare_for_model` 
                    wall **190.626 ms**  self **0.040 ms**  `tokenization_utils_base.py:3475`
                    - `PreTrainedTokenizerBase.create_token_type_ids_from_sequences` 
                      wall **190.414 ms**  self **0.076 ms**  `tokenization_utils_base.py:3431`
                      - `SpecialTokensMixin.__getattr__` 
                        wall **190.288 ms**  self **0.064 ms**  `tokenization_utils_base.py:1077`
                        - `SpecialTokensMixin.__getattr__` 
                          wall **190.223 ms**  self **190.217 ms**  `tokenization_utils_base.py:1077`
                  - `PreTrainedTokenizer._encode_plus.<locals>.get_input_ids` 
                    wall **20.709 ms**  self **0.008 ms**  `tokenization_utils.py:765`
                    - `PreTrainedTokenizer.tokenize` 
                      wall **19.117 ms**  self **0.067 ms**  `tokenization_utils.py:621`
                      - `Qwen2Tokenizer._tokenize` 
                        wall **17.102 ms**  self **1.523 ms**  `tokenization_qwen2.py:262`
                        - `findall` 
                          wall **2.190 ms**  self **2.157 ms**  `_main.py:341`
                      - `Trie.split` 
                        wall **1.074 ms**  self **1.067 ms**  `tokenization_utils.py:105`
                    - `PreTrainedTokenizer.convert_tokens_to_ids` 
                      wall **1.584 ms**  self **0.205 ms**  `tokenization_utils.py:710`
  - `BaseEventLoop._run_once` 
    wall **206.972 ms**  self **0.045 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **203.237 ms**  self **2.817 ms**  `events.py:78`
      - `golden.unet.skeleton_patcher_construction` 
        wall **134.477 ms**  self **134.477 ms**  `full_execution_trace.py:330`
      - `golden.unet.header_config_preflight` 
        wall **65.943 ms**  self **65.943 ms**  `full_execution_trace.py:330`
    - `Handle._run` 
      wall **2.810 ms**  self **2.810 ms**  `events.py:78`
  _... 9 more children >= 1 ms omitted_

### `golden_sampler_prepare`

- Stage wall: **55.646 ms**

- `golden_sampler_prepare` 
  wall **55.646 ms**  self **0.733 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **55.627 ms**  self **0.083 ms**  `golden_serial.py:13553`
    - `GoldenSerialRunner.run_closure` 
      wall **54.250 ms**  self **0.067 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **33.733 ms**  self **0.128 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **33.292 ms**  self **0.033 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **32.008 ms**  self **0.019 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **31.319 ms**  self **0.027 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **26.230 ms**  self **0.025 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **21.602 ms**  self **0.035 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **21.333 ms**  self **1.026 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **20.176 ms**  self **20.171 ms**  `nodes.py:1992`
                - `GoldenSerialRunner._ensure` 
                  wall **2.826 ms**  self **0.021 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._ensure` 
                  wall **1.747 ms**  self **0.020 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **3.808 ms**  self **0.049 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **2.924 ms**  self **0.017 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **2.792 ms**  self **0.041 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **2.020 ms**  self **0.015 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **1.624 ms**  self **0.001 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **1.623 ms**  self **0.007 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **1.616 ms**  self **1.615 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **1.223 ms**  self **0.013 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **8.795 ms**  self **0.017 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **7.980 ms**  self **0.021 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **7.437 ms**  self **0.033 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **6.234 ms**  self **0.021 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **6.191 ms**  self **0.033 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **5.670 ms**  self **0.010 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **5.464 ms**  self **0.010 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **5.454 ms**  self **0.074 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **5.028 ms**  self **0.060 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **4.429 ms**  self **0.127 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **4.301 ms**  self **0.114 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **4.188 ms**  self **0.024 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **4.143 ms**  self **0.030 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **3.436 ms**  self **0.039 ms**  `module.py:2199`
            - `GoldenSerialRunner._execute_one` 
              wall **1.125 ms**  self **0.047 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **6.449 ms**  self **0.033 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **5.795 ms**  self **0.017 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **5.767 ms**  self **0.031 ms**  `golden_serial.py:8902`
            - `GoldenSerialRunner._call_node` 
              wall **5.412 ms**  self **0.021 ms**  `golden_serial.py:9035`
              - `ConditioningZeroOut.zero_out` 
                wall **5.263 ms**  self **5.263 ms**  `nodes.py:283`
      - `GoldenSerialRunner._ensure` 
        wall **2.116 ms**  self **0.020 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.357 ms**  self **0.041 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.104 ms**  self **0.023 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.080 ms**  self **0.045 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.084 ms**  self **0.012 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.011 ms**  self **0.023 ms**  `golden_serial.py:8902`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **54.281 ms**  self **54.281 ms**  `full_execution_trace.py:330`

### `golden_vae_load`

- Stage wall: **819.897 ms**

- `golden_vae_load` 
  wall **819.897 ms**  self **152.352 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **667.777 ms**  self **0.015 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **667.573 ms**  self **0.021 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **667.552 ms**  self **0.012 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **667.540 ms**  self **0.008 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **667.532 ms**  self **0.273 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **306.497 ms**  self **0.189 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **262.920 ms**  self **0.040 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **250.113 ms**  self **250.113 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **11.948 ms**  self **11.918 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **19.836 ms**  self **0.010 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **18.383 ms**  self **18.366 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **1.335 ms**  self **0.020 ms**  `golden_source_threads.py:1036`
                  - `_FileLock.__enter__` 
                    wall **1.143 ms**  self **1.143 ms**  `golden_source_threads.py:486`
              - `SourceThreadProcess.wait_ready` 
                wall **8.198 ms**  self **0.021 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **7.500 ms**  self **7.472 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **7.506 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **7.005 ms**  self **6.982 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.plan_once` 
                wall **4.370 ms**  self **0.248 ms**  `golden_source_threads.py:910`
                - `SourceThreadProcess._read_message` 
                  wall **3.287 ms**  self **3.261 ms**  `golden_source_threads.py:892`
            - `GoldenModelTransport._views` 
              wall **201.898 ms**  self **201.898 ms**  `golden_model_transport.py:1910`
            - `GoldenModelTransport.inspect` 
              wall **128.500 ms**  self **0.037 ms**  `golden_model_transport.py:973`
              - `_parse_layout` 
                wall **127.967 ms**  self **127.507 ms**  `golden_model_transport.py:304`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **24.755 ms**  self **0.062 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **24.418 ms**  self **0.009 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **24.404 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **24.393 ms**  self **0.005 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **24.385 ms**  self **24.381 ms**  `threading.py:288`
            - `SourceThreadProcess.wait_quiescent` 
              wall **1.994 ms**  self **0.011 ms**  `golden_source_threads.py:1220`
              - `SourceThreadProcess._check_child` 
                wall **1.756 ms**  self **0.026 ms**  `golden_source_threads.py:1026`
            - `GpuDestinationPool.acquire` 
              wall **1.692 ms**  self **0.040 ms**  `golden_model_transport.py:183`
              - `GpuDestinationPool._allocate` 
                wall **1.637 ms**  self **1.463 ms**  `golden_model_transport.py:156`
  - `BaseEventLoop._run_once` 
    wall **667.545 ms**  self **0.017 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **667.334 ms**  self **667.331 ms**  `selectors.py:451`
  - `prepare_sampling` 
    wall **226.839 ms**  self **0.009 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **226.825 ms**  self **0.005 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **226.820 ms**  self **0.023 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **226.692 ms**  self **0.110 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **224.857 ms**  self **0.024 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **224.805 ms**  self **0.003 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **224.802 ms**  self **0.215 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **224.499 ms**  self **5.288 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **65.116 ms**  self **20.689 ms**  `model_patcher.py:945`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **7.303 ms**  self **2.020 ms**  `model_patcher.py:1842`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **3.911 ms**  self **0.032 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **3.821 ms**  self **0.663 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **2.796 ms**  self **2.795 ms**  `__init__.py:350`
                  - `Module.named_buffers` 
                    wall **2.892 ms**  self **0.004 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **2.888 ms**  self **0.537 ms**  `module.py:2650`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.183 ms**  self **0.057 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.054 ms**  self **0.150 ms**  `model_patcher.py:899`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.088 ms**  self **0.505 ms**  `model_patcher.py:1947`
  - `sample_custom` 
    wall **224.430 ms**  self **3.815 ms**  `sample.py:86`
    - `sample` 
      wall **220.607 ms**  self **0.045 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **220.182 ms**  self **0.122 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **219.827 ms**  self **0.022 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **219.805 ms**  self **0.099 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **218.448 ms**  self **0.010 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **218.424 ms**  self **0.033 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **218.391 ms**  self **1.963 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **142.172 ms**  self **0.012 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **142.153 ms**  self **0.016 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **142.137 ms**  self **0.047 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **141.959 ms**  self **0.095 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **140.420 ms**  self **0.026 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **140.367 ms**  self **0.003 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **140.364 ms**  self **0.249 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **140.053 ms**  self **5.040 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **43.247 ms**  self **4.891 ms**  `model_patcher.py:945`
                                  - `Module.named_buffers` 
                                    wall **4.391 ms**  self **0.003 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **4.388 ms**  self **1.519 ms**  `module.py:2650`
                                  - `ModelPatcherDynamic.load.<locals>.<genexpr>` 
                                    wall **2.527 ms**  self **2.527 ms**  `model_patcher.py:1907`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **1.104 ms**  self **0.079 ms**  `model_patcher.py:1947`
                  - `CFGGuider.inner_sample` 
                    wall **74.030 ms**  self **71.221 ms**  `samplers.py:1220`
                    - `WrapperExecutor.execute` 
                      wall **1.912 ms**  self **0.028 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.884 ms**  self **0.120 ms**  `samplers.py:983`
  - `_vae_load_with_worker_stage` 
    wall **149.155 ms**  self **0.011 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **149.138 ms**  self **0.379 ms**  `golden_serial.py:14229`
      - `VAE.__init__` 
        wall **140.498 ms**  self **80.156 ms**  `sd.py:487`
        - `Module.load_state_dict` 
          wall **28.662 ms**  self **0.305 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **28.357 ms**  self **0.029 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **16.129 ms**  self **0.031 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **12.328 ms**  self **0.032 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.903 ms**  self **0.017 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.611 ms**  self **0.020 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.311 ms**  self **0.029 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.130 ms**  self **0.025 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.087 ms**  self **0.027 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.757 ms**  self **0.029 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.369 ms**  self **0.021 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.233 ms**  self **0.031 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.045 ms**  self **0.025 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.002 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.493 ms**  self **0.018 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.168 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.884 ms**  self **0.012 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.813 ms**  self **0.016 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **2.968 ms**  self **0.019 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.063 ms**  self **0.041 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **11.572 ms**  self **0.033 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **8.206 ms**  self **0.019 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.078 ms**  self **0.014 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.705 ms**  self **0.013 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.064 ms**  self **0.011 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.004 ms**  self **0.014 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.071 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.047 ms**  self **0.010 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.858 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.061 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.855 ms**  self **0.011 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.669 ms**  self **0.014 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **2.333 ms**  self **0.023 ms**  `module.py:2589`
        - `Module.to` 
          wall **13.593 ms**  self **0.198 ms**  `module.py:1259`
          - `Module._apply` 
            wall **13.395 ms**  self **0.019 ms**  `module.py:930`
            - `Module._apply` 
              wall **6.871 ms**  self **0.020 ms**  `module.py:930`
              - `Module._apply` 
                wall **4.650 ms**  self **0.008 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.483 ms**  self **0.006 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.460 ms**  self **0.010 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.287 ms**  self **0.006 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.216 ms**  self **0.010 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.004 ms**  self **0.006 ms**  `module.py:930`
              - `Module._apply` 
                wall **1.394 ms**  self **0.012 ms**  `module.py:930`
            - `Module._apply` 
              wall **6.480 ms**  self **0.021 ms**  `module.py:930`
              - `Module._apply` 
                wall **4.644 ms**  self **0.014 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.214 ms**  self **0.008 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.194 ms**  self **0.011 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.155 ms**  self **0.013 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.153 ms**  self **0.016 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.043 ms**  self **0.011 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.091 ms**  self **0.010 ms**  `module.py:930`
        - `archive_model_dtypes` 
          wall **8.899 ms**  self **1.135 ms**  `model_management.py:1045`
        - `VAE.model_size` 
          wall **5.916 ms**  self **0.620 ms**  `sd.py:1095`
          - `module_size` 
            wall **5.296 ms**  self **0.168 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **5.128 ms**  self **0.021 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **2.901 ms**  self **0.023 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **2.194 ms**  self **0.016 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **2.194 ms**  self **0.020 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.520 ms**  self **0.017 ms**  `module.py:2199`
        - `Module.eval` 
          wall **1.993 ms**  self **0.002 ms**  `module.py:2916`
          - `Module.train` 
            wall **1.991 ms**  self **0.007 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.059 ms**  self **0.005 ms**  `module.py:2894`
        - `ModelPatcherDynamic.__init__` 
          wall **1.245 ms**  self **0.026 ms**  `model_patcher.py:1757`
      - `validate_qd_adoption` 
        wall **5.467 ms**  self **1.171 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **1.387 ms**  self **0.005 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.382 ms**  self **0.259 ms**  `module.py:2650`
  - `RK_NoiseSampler.get_sde_step` 
    wall **49.651 ms**  self **2.345 ms**  `rk_noise_sampler_beta.py:318`
    - `RK_NoiseSampler.get_sde_coeff` 
      wall **47.306 ms**  self **4.130 ms**  `rk_noise_sampler_beta.py:180`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **41.985 ms**  self **41.985 ms**  `_tensor.py:32`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **31.378 ms**  self **31.378 ms**  `rk_noise_sampler_beta.py:785`
  - `generate_init_noise` 
    wall **21.318 ms**  self **3.103 ms**  `samplers.py:61`
    - `GaussianNoiseGenerator.__call__` 
      wall **16.161 ms**  self **16.156 ms**  `noise_classes.py:386`
    - `normalize_zscore` 
      wall **1.441 ms**  self **1.441 ms**  `latents.py:246`
  _... 16 more children >= 1 ms omitted_

### `golden_sampling`

- Stage wall: **4,786.919 ms**

- `golden_sampling` 
  wall **4,786.919 ms**  self **4,786.919 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **4,786.855 ms**  self **0.238 ms**  `golden_serial.py:13704`
    - `GoldenSerialRunner.run_closure` 
      wall **4,630.356 ms**  self **0.051 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,630.040 ms**  self **0.075 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,629.065 ms**  self **0.198 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **4,628.708 ms**  self **0.547 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **4,624.824 ms**  self **16.890 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **4,316.677 ms**  self **0.072 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **4,316.406 ms**  self **0.008 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **4,316.398 ms**  self **0.061 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **4,315.960 ms**  self **0.006 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **4,315.949 ms**  self **0.013 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **4,315.936 ms**  self **2.102 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **4,086.738 ms**  self **0.817 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **4,083.955 ms**  self **0.015 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **4,083.940 ms**  self **0.183 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **4,081.467 ms**  self **0.236 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **4,081.187 ms**  self **58.997 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **683.779 ms**  self **0.624 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **682.628 ms**  self **0.377 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **681.807 ms**  self **0.011 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **681.796 ms**  self **0.009 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **681.787 ms**  self **0.019 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **681.755 ms**  self **0.008 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **681.746 ms**  self **0.024 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **681.722 ms**  self **0.032 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **669.643 ms**  self **0.006 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **669.637 ms**  self **0.008 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **669.623 ms**  self **0.120 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **669.503 ms**  self **1.891 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **660.388 ms**  self **0.014 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **660.363 ms**  self **0.034 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **660.329 ms**  self **2.751 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **656.628 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **656.618 ms**  self **0.032 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **656.586 ms**  self **656.586 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **5.662 ms**  self **0.024 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **5.636 ms**  self **5.636 ms**  `conds.py:44`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.031 ms**  self **0.054 ms**  `model_patcher.py:417`
                                                    - `cfg_function` 
                                                      wall **12.047 ms**  self **0.212 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **11.835 ms**  self **11.531 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **313.550 ms**  self **0.196 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **313.316 ms**  self **0.158 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **313.131 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **313.124 ms**  self **0.007 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **313.117 ms**  self **0.016 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **313.089 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **313.083 ms**  self **0.021 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **313.063 ms**  self **0.028 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **216.028 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **216.023 ms**  self **0.010 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **216.008 ms**  self **0.211 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **215.796 ms**  self **0.883 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **213.376 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **213.355 ms**  self **0.016 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **213.339 ms**  self **0.232 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **212.492 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **212.484 ms**  self **0.017 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **212.468 ms**  self **212.468 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **97.007 ms**  self **0.476 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **96.531 ms**  self **96.130 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **312.650 ms**  self **0.149 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **312.437 ms**  self **0.058 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **312.369 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **312.362 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **312.356 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **312.334 ms**  self **0.007 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **312.327 ms**  self **0.019 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **312.308 ms**  self **0.019 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **228.184 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **228.180 ms**  self **0.008 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **228.167 ms**  self **0.031 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **228.137 ms**  self **0.458 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **226.063 ms**  self **0.014 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **226.039 ms**  self **0.018 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **226.022 ms**  self **0.169 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **225.212 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **225.205 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **225.190 ms**  self **225.190 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **84.105 ms**  self **0.835 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **83.270 ms**  self **83.270 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **311.433 ms**  self **0.714 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **310.675 ms**  self **0.074 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **310.592 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **310.584 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **310.579 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **310.557 ms**  self **0.010 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **310.547 ms**  self **0.098 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **310.449 ms**  self **0.015 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **208.076 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **208.071 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **208.060 ms**  self **0.027 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **208.032 ms**  self **0.405 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **204.536 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **204.516 ms**  self **0.018 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **204.498 ms**  self **0.177 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **203.760 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **203.752 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **203.739 ms**  self **203.739 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **2.224 ms**  self **0.033 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **2.118 ms**  self **0.038 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.709 ms**  self **1.702 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **102.358 ms**  self **0.048 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **102.310 ms**  self **102.310 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **310.431 ms**  self **0.145 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **310.259 ms**  self **0.155 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **310.078 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **310.071 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **310.065 ms**  self **0.012 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **310.042 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **310.037 ms**  self **0.020 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **310.018 ms**  self **0.020 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **225.668 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **225.663 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **225.651 ms**  self **0.158 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **225.493 ms**  self **0.983 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **222.819 ms**  self **0.010 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **222.802 ms**  self **0.016 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **222.786 ms**  self **0.264 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **221.682 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **221.674 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **221.661 ms**  self **221.661 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.000 ms**  self **0.027 ms**  `model_patcher.py:417`
                                                    - `cfg_function` 
                                                      wall **84.330 ms**  self **0.123 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **84.207 ms**  self **84.207 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **308.215 ms**  self **0.207 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **307.964 ms**  self **0.064 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **307.890 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **307.883 ms**  self **0.007 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **307.876 ms**  self **0.016 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **307.848 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **307.842 ms**  self **0.022 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **307.820 ms**  self **0.035 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **229.778 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **229.773 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **229.761 ms**  self **0.034 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **229.727 ms**  self **0.531 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **226.057 ms**  self **0.013 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **226.034 ms**  self **0.019 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **226.016 ms**  self **0.170 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **225.186 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **225.179 ms**  self **0.017 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **225.162 ms**  self **225.162 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.889 ms**  self **0.029 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.859 ms**  self **1.859 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **78.007 ms**  self **0.153 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **77.855 ms**  self **77.417 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **301.916 ms**  self **0.162 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **301.720 ms**  self **0.056 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **301.652 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **301.645 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **301.639 ms**  self **0.012 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **301.620 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **301.614 ms**  self **0.018 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **301.597 ms**  self **0.020 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **222.298 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **222.293 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **222.283 ms**  self **0.034 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **222.249 ms**  self **0.448 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **220.302 ms**  self **0.013 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **220.279 ms**  self **0.018 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **220.261 ms**  self **0.161 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **219.526 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **219.517 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **219.502 ms**  self **219.502 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **79.279 ms**  self **0.084 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **79.195 ms**  self **79.195 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **300.584 ms**  self **0.138 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **300.415 ms**  self **0.057 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **300.349 ms**  self **0.005 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **300.344 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **300.339 ms**  self **0.012 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **300.319 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **300.313 ms**  self **0.019 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **300.294 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **221.267 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **221.264 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **221.254 ms**  self **0.027 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **221.227 ms**  self **0.381 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **219.548 ms**  self **0.009 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **219.531 ms**  self **0.015 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **219.516 ms**  self **0.120 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **218.840 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **218.832 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **218.819 ms**  self **218.819 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **79.010 ms**  self **0.078 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **78.932 ms**  self **78.932 ms**  `noise_injection.py:285`
                                    _... 36 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **13.160 ms**  self **0.012 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **13.148 ms**  self **0.037 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **5.321 ms**  self **0.008 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **5.312 ms**  self **0.085 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **5.169 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **5.153 ms**  self **0.008 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **5.137 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **5.129 ms**  self **5.128 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **2.402 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.396 ms**  self **0.213 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **2.150 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **2.128 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **2.113 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **2.105 ms**  self **2.104 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.777 ms**  self **0.003 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.772 ms**  self **0.065 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.679 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.660 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.645 ms**  self **0.007 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.638 ms**  self **1.636 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.416 ms**  self **0.003 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.412 ms**  self **0.090 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.297 ms**  self **0.002 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.279 ms**  self **0.005 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.265 ms**  self **0.004 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.261 ms**  self **1.260 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.346 ms**  self **0.002 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.343 ms**  self **0.062 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.264 ms**  self **0.002 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.256 ms**  self **0.004 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.248 ms**  self **0.003 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.245 ms**  self **1.244 ms**  `storage.py:262`
              - `_disable_dynamo.<locals>.inner` 
                wall **1.956 ms**  self **0.006 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **1.950 ms**  self **0.010 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **1.939 ms**  self **0.003 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **1.936 ms**  self **0.052 ms**  `random.py:62`
                      - `manual_seed_all` 
                        wall **1.096 ms**  self **0.006 ms**  `random.py:97`
                        - `_lazy_call` 
                          wall **1.090 ms**  self **0.014 ms**  `__init__.py:319`
                          - `format_stack` 
                            wall **1.066 ms**  self **0.017 ms**  `traceback.py:213`
              - `BaseModel.process_latent_out` 
                wall **1.908 ms**  self **0.004 ms**  `model_base.py:378`
                - `Flux.process_out` 
                  wall **1.903 ms**  self **1.903 ms**  `latent_formats.py:193`
    - `import_module` 
      wall **134.617 ms**  self **134.617 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **15.284 ms**  self **0.015 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **15.270 ms**  self **0.003 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **15.266 ms**  self **0.038 ms**  `copy.py:201`
          - `deepcopy` 
            wall **7.024 ms**  self **0.009 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **7.015 ms**  self **0.008 ms**  `copy.py:227`
              - `deepcopy` 
                wall **6.999 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **6.995 ms**  self **0.038 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **6.872 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **6.870 ms**  self **0.009 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **6.445 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **6.442 ms**  self **0.175 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **2.739 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **2.736 ms**  self **0.325 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **2.635 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **2.632 ms**  self **0.764 ms**  `copy.py:201`
          - `deepcopy` 
            wall **5.002 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **5.000 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **4.986 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **4.983 ms**  self **0.053 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **4.856 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **4.854 ms**  self **0.008 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **4.409 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **4.407 ms**  self **0.169 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **2.282 ms**  self **0.004 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **2.276 ms**  self **0.515 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.196 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.193 ms**  self **0.167 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **2.332 ms**  self **0.069 ms**  `golden_serial.py:9742`
      - `GoldenTelemetryRecorder.event` 
        wall **1.220 ms**  self **0.007 ms**  `golden_serial.py:1672`
        - `GoldenTelemetryRecorder.event_at` 
          wall **1.214 ms**  self **0.005 ms**  `golden_serial.py:1675`
          - `deepcopy` 
            wall **1.209 ms**  self **0.005 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **1.204 ms**  self **0.005 ms**  `copy.py:227`
              - `deepcopy` 
                wall **1.193 ms**  self **0.003 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **1.190 ms**  self **0.017 ms**  `copy.py:227`
      - `_build_golden_sampling_decomposition` 
        wall **1.042 ms**  self **0.121 ms**  `golden_serial.py:9370`
  - `BaseEventLoop.run_until_complete` 
    wall **828.014 ms**  self **0.014 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **827.990 ms**  self **0.128 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **156.863 ms**  self **7.558 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **149.237 ms**  self **149.215 ms**  `events.py:78`
      - `BaseEventLoop._run_once` 
        wall **3.281 ms**  self **0.022 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **3.147 ms**  self **3.147 ms**  `events.py:78`
  - `Thread.run` 
    wall **826.580 ms**  self **0.011 ms**  `threading.py:964`
    - `_worker` 
      wall **826.569 ms**  self **158.780 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **819.897 ms**  self **152.352 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **667.777 ms**  self **0.015 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **667.573 ms**  self **0.021 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **667.552 ms**  self **0.012 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **667.540 ms**  self **0.008 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **667.532 ms**  self **0.273 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **306.497 ms**  self **0.189 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **262.920 ms**  self **0.040 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **250.113 ms**  self **250.113 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **11.948 ms**  self **11.918 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **19.836 ms**  self **0.010 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **18.383 ms**  self **18.366 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **1.335 ms**  self **0.020 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **1.143 ms**  self **1.143 ms**  `golden_source_threads.py:486`
                - `SourceThreadProcess.wait_ready` 
                  wall **8.198 ms**  self **0.021 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **7.500 ms**  self **7.472 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **7.506 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **7.005 ms**  self **6.982 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.plan_once` 
                  wall **4.370 ms**  self **0.248 ms**  `golden_source_threads.py:910`
                  - `SourceThreadProcess._read_message` 
                    wall **3.287 ms**  self **3.261 ms**  `golden_source_threads.py:892`
              - `GoldenModelTransport._views` 
                wall **201.898 ms**  self **201.898 ms**  `golden_model_transport.py:1910`
              - `GoldenModelTransport.inspect` 
                wall **128.500 ms**  self **0.037 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **127.967 ms**  self **127.507 ms**  `golden_model_transport.py:304`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **24.755 ms**  self **0.062 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **24.418 ms**  self **0.009 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **24.404 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **24.393 ms**  self **0.005 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **24.385 ms**  self **24.381 ms**  `threading.py:288`
              - `SourceThreadProcess.wait_quiescent` 
                wall **1.994 ms**  self **0.011 ms**  `golden_source_threads.py:1220`
                - `SourceThreadProcess._check_child` 
                  wall **1.756 ms**  self **0.026 ms**  `golden_source_threads.py:1026`
              - `GpuDestinationPool.acquire` 
                wall **1.692 ms**  self **0.040 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **1.637 ms**  self **1.463 ms**  `golden_model_transport.py:156`
    - `BaseEventLoop._run_once` 
      wall **667.545 ms**  self **0.017 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **667.334 ms**  self **667.331 ms**  `selectors.py:451`
    - `prepare_sampling` 
      wall **226.839 ms**  self **0.009 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **226.825 ms**  self **0.005 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **226.820 ms**  self **0.023 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **226.692 ms**  self **0.110 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **224.857 ms**  self **0.024 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **224.805 ms**  self **0.003 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **224.802 ms**  self **0.215 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **224.499 ms**  self **5.288 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **65.116 ms**  self **20.689 ms**  `model_patcher.py:945`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **7.303 ms**  self **2.020 ms**  `model_patcher.py:1842`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **3.911 ms**  self **0.032 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **3.821 ms**  self **0.663 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **2.796 ms**  self **2.795 ms**  `__init__.py:350`
                    - `Module.named_buffers` 
                      wall **2.892 ms**  self **0.004 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **2.888 ms**  self **0.537 ms**  `module.py:2650`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.183 ms**  self **0.057 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.054 ms**  self **0.150 ms**  `model_patcher.py:899`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.088 ms**  self **0.505 ms**  `model_patcher.py:1947`
    - `sample_custom` 
      wall **224.430 ms**  self **3.815 ms**  `sample.py:86`
      - `sample` 
        wall **220.607 ms**  self **0.045 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **220.182 ms**  self **0.122 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **219.827 ms**  self **0.022 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **219.805 ms**  self **0.099 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **218.448 ms**  self **0.010 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **218.424 ms**  self **0.033 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **218.391 ms**  self **1.963 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **142.172 ms**  self **0.012 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **142.153 ms**  self **0.016 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **142.137 ms**  self **0.047 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **141.959 ms**  self **0.095 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **140.420 ms**  self **0.026 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **140.367 ms**  self **0.003 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **140.364 ms**  self **0.249 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **140.053 ms**  self **5.040 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **43.247 ms**  self **4.891 ms**  `model_patcher.py:945`
                                    - `Module.named_buffers` 
                                      wall **4.391 ms**  self **0.003 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **4.388 ms**  self **1.519 ms**  `module.py:2650`
                                    - `ModelPatcherDynamic.load.<locals>.<genexpr>` 
                                      wall **2.527 ms**  self **2.527 ms**  `model_patcher.py:1907`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **1.104 ms**  self **0.079 ms**  `model_patcher.py:1947`
                    - `CFGGuider.inner_sample` 
                      wall **74.030 ms**  self **71.221 ms**  `samplers.py:1220`
                      - `WrapperExecutor.execute` 
                        wall **1.912 ms**  self **0.028 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.884 ms**  self **0.120 ms**  `samplers.py:983`
    - `_vae_load_with_worker_stage` 
      wall **149.155 ms**  self **0.011 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **149.138 ms**  self **0.379 ms**  `golden_serial.py:14229`
        - `VAE.__init__` 
          wall **140.498 ms**  self **80.156 ms**  `sd.py:487`
          - `Module.load_state_dict` 
            wall **28.662 ms**  self **0.305 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **28.357 ms**  self **0.029 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **16.129 ms**  self **0.031 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **12.328 ms**  self **0.032 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.903 ms**  self **0.017 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.611 ms**  self **0.020 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.311 ms**  self **0.029 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.130 ms**  self **0.025 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.087 ms**  self **0.027 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.757 ms**  self **0.029 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.369 ms**  self **0.021 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.233 ms**  self **0.031 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.045 ms**  self **0.025 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.002 ms**  self **0.028 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.493 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.168 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.884 ms**  self **0.012 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.813 ms**  self **0.016 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.968 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.063 ms**  self **0.041 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **11.572 ms**  self **0.033 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **8.206 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.078 ms**  self **0.014 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.705 ms**  self **0.013 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.064 ms**  self **0.011 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.004 ms**  self **0.014 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.071 ms**  self **0.028 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.047 ms**  self **0.010 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.858 ms**  self **0.015 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.061 ms**  self **0.028 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.855 ms**  self **0.011 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.669 ms**  self **0.014 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.333 ms**  self **0.023 ms**  `module.py:2589`
          - `Module.to` 
            wall **13.593 ms**  self **0.198 ms**  `module.py:1259`
            - `Module._apply` 
              wall **13.395 ms**  self **0.019 ms**  `module.py:930`
              - `Module._apply` 
                wall **6.871 ms**  self **0.020 ms**  `module.py:930`
                - `Module._apply` 
                  wall **4.650 ms**  self **0.008 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.483 ms**  self **0.006 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.460 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.287 ms**  self **0.006 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.216 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.004 ms**  self **0.006 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.394 ms**  self **0.012 ms**  `module.py:930`
              - `Module._apply` 
                wall **6.480 ms**  self **0.021 ms**  `module.py:930`
                - `Module._apply` 
                  wall **4.644 ms**  self **0.014 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.214 ms**  self **0.008 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.194 ms**  self **0.011 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.155 ms**  self **0.013 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.153 ms**  self **0.016 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.043 ms**  self **0.011 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.091 ms**  self **0.010 ms**  `module.py:930`
          - `archive_model_dtypes` 
            wall **8.899 ms**  self **1.135 ms**  `model_management.py:1045`
          - `VAE.model_size` 
            wall **5.916 ms**  self **0.620 ms**  `sd.py:1095`
            - `module_size` 
              wall **5.296 ms**  self **0.168 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **5.128 ms**  self **0.021 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **2.901 ms**  self **0.023 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **2.194 ms**  self **0.016 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **2.194 ms**  self **0.020 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.520 ms**  self **0.017 ms**  `module.py:2199`
          - `Module.eval` 
            wall **1.993 ms**  self **0.002 ms**  `module.py:2916`
            - `Module.train` 
              wall **1.991 ms**  self **0.007 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.059 ms**  self **0.005 ms**  `module.py:2894`
          - `ModelPatcherDynamic.__init__` 
            wall **1.245 ms**  self **0.026 ms**  `model_patcher.py:1757`
        - `validate_qd_adoption` 
          wall **5.467 ms**  self **1.171 ms**  `golden_serial.py:12922`
          - `Module.named_buffers` 
            wall **1.387 ms**  self **0.005 ms**  `module.py:2754`
            - `Module._named_members` 
              wall **1.382 ms**  self **0.259 ms**  `module.py:2650`
    - `RK_NoiseSampler.get_sde_step` 
      wall **49.651 ms**  self **2.345 ms**  `rk_noise_sampler_beta.py:318`
      - `RK_NoiseSampler.get_sde_coeff` 
        wall **47.306 ms**  self **4.130 ms**  `rk_noise_sampler_beta.py:180`
        - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
          wall **41.985 ms**  self **41.985 ms**  `_tensor.py:32`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **31.378 ms**  self **31.378 ms**  `rk_noise_sampler_beta.py:785`
    - `generate_init_noise` 
      wall **21.318 ms**  self **3.103 ms**  `samplers.py:61`
      - `GaussianNoiseGenerator.__call__` 
        wall **16.161 ms**  self **16.156 ms**  `noise_classes.py:386`
      - `normalize_zscore` 
        wall **1.441 ms**  self **1.441 ms**  `latents.py:246`
    _... 16 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **149.189 ms**  self **0.009 ms**  `golden_serial.py:15533`
  - `_overlap_stage_call` 
    wall **3.130 ms**  self **0.011 ms**  `golden_serial.py:15533`
  - `BaseSelectorEventLoop._make_self_pipe` 
    wall **1.106 ms**  self **0.476 ms**  `selector_events.py:105`

### `golden_sampler_tail`

- Stage wall: **0.041 ms**

_Nothing below the stage body reached the threshold._

### `golden_vae_decode`

- Stage wall: **958.073 ms**

- `golden_vae_decode` 
  wall **958.073 ms**  self **0.338 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **958.055 ms**  self **0.077 ms**  `golden_serial.py:14442`
    - `GoldenSerialRunner.run_closure` 
      wall **957.515 ms**  self **0.026 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **957.429 ms**  self **0.055 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **956.898 ms**  self **0.021 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **956.606 ms**  self **0.027 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **956.579 ms**  self **848.854 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **99.997 ms**  self **0.095 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **91.213 ms**  self **0.025 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **91.153 ms**  self **0.004 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **91.149 ms**  self **0.090 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **91.020 ms**  self **2.080 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **17.482 ms**  self **1.722 ms**  `model_patcher.py:945`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.873 ms**  self **0.068 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.727 ms**  self **0.146 ms**  `model_patcher.py:899`
                            - `namedtuple` 
                              wall **1.326 ms**  self **1.325 ms**  `__init__.py:350`
                        - `Module.named_buffers` 
                          wall **1.336 ms**  self **0.004 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.332 ms**  self **0.227 ms**  `module.py:2650`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.001 ms**  self **0.058 ms**  `model_patcher.py:1947`
                - `LoadedModel.model_memory_required` 
                  wall **6.747 ms**  self **0.003 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **6.742 ms**  self **0.003 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **6.740 ms**  self **0.637 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **6.103 ms**  self **0.153 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **5.950 ms**  self **0.028 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **3.246 ms**  self **0.027 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.347 ms**  self **0.017 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.664 ms**  self **0.030 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.063 ms**  self **0.017 ms**  `module.py:2199`
                - `free_memory` 
                  wall **1.355 ms**  self **0.079 ms**  `model_management.py:863`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **6.037 ms**  self **6.037 ms**  `sd.py:506`
              - `ModelPatcher.get_free_memory` 
                wall **1.619 ms**  self **0.025 ms**  `model_patcher.py:417`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **957.548 ms**  self **957.548 ms**  `full_execution_trace.py:330`

### `golden_output`

- Stage wall: **251.330 ms**

- `golden_output` 
  wall **251.330 ms**  self **251.330 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **251.256 ms**  self **19.213 ms**  `golden_serial.py:14589`
    - `Image.save` 
      wall **202.510 ms**  self **0.102 ms**  `Image.py:2592`
      - `_save` 
        wall **190.035 ms**  self **0.058 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **189.938 ms**  self **0.024 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **189.909 ms**  self **185.518 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **12.286 ms**  self **12.286 ms**  `Image.py:429`
    - `fromarray` 
      wall **13.330 ms**  self **7.434 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **5.896 ms**  self **0.034 ms**  `Image.py:3288`
        - `frombytes` 
          wall **5.853 ms**  self **0.060 ms**  `Image.py:3242`
          - `new` 
            wall **4.061 ms**  self **4.011 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.726 ms**  self **1.685 ms**  `Image.py:925`
    - `clip` 
      wall **11.435 ms**  self **0.034 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **11.401 ms**  self **0.029 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **11.373 ms**  self **11.373 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **3.165 ms**  self **0.021 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **3.145 ms**  self **3.145 ms**  `output_durability.py:73`
