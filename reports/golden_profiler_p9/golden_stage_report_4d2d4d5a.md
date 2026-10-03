# Golden stage decision report

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **887,436**

Tree floor: **1 ms**   Function rollup floor: **1 ms** total inclusive

## 1. Critical path and stage overlap

Sum of stage walls: **24,970.419 ms**   Timeline union: **17,652.204 ms**   Span: **17,664.458 ms**

Sum exceeds the union by **7,318.215 ms** -- that gap is the overlap the schedule is buying.

| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |
|:--|---:|---:|---:|:--|:--|
| `golden_restore` | 0.5 | 0.0 | 0.5 | 0.0% | `#` |
| `golden_request_setup` | 2.7 | 0.0 | 2.7 | 0.0% | `#` |
| `golden_clip_load` | 3,506.7 | 3,506.4 | 0.3 | 100.0% | `##############` |
| `golden_clip_forward` | 6,376.6 | 123.7 | 6,252.9 | 1.9% | `              ##########################` |
| `golden_unet_load` | 6,249.0 | 0.0 | 6,249.0 | 0.0% | `              #########################` |
| `golden_sampler_prepare` | 67.4 | 61.8 | 5.6 | 91.7% | `                                        #` |
| `golden_vae_load` | 1,070.3 | 0.0 | 1,070.3 | 0.0% | `                                         ####` |
| `golden_sampling` | 5,804.6 | 4,725.2 | 1,079.3 | 81.4% | `                                         ########################` |
| `golden_sampler_tail` | 0.1 | 0.0 | 0.1 | 0.0% | `                                                                #` |
| `golden_vae_decode` | 1,591.1 | 1,581.0 | 10.1 | 99.4% | `                                                                ######` |
| `golden_output` | 301.5 | 300.3 | 1.2 | 99.6% | `                                                                       #` |

_Uncontended_ is the time during a stage when no other stage was running. That portion is protected: nothing else could absorb it. Overlapped time may be hidden by a longer sibling, so reducing it may not move root wall.

## 2. Function rollup across the whole request

`total incl ms` sums each call's wall, so a function called 24 times at 3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall contains its callees, so **totals are not additive down a call tree** -- `total self ms` is the non-overlapping part.

| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |
|---:|---:|---:|---:|---:|:--|:--|:--|
| 28,032.971 | 59 | 475.135 | 5,221.955 | 2.664 | `WrapperExecutor.execute` | `patcher_extension.py:108` | 2 |
| 20,078.063 | 526 | 38.171 | 4,663.394 | 2.052 | `Module._wrapped_call_impl` | `module.py:1779` | 3 |
| 20,076.010 | 526 | 38.167 | 4,663.383 | 5.570 | `Module._call_impl` | `module.py:1787` | 3 |
| 13,619.303 | 32 | 425.603 | 6,360.821 | 1.650 | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` | 6 |
| 13,615.456 | 5 | 2,723.091 | 6,364.103 | 0.240 | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` | 5 |
| 13,598.109 | 32 | 424.941 | 6,360.132 | 4.292 | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` | 6 |
| 9,014.172 | 3 | 3,004.724 | 4,750.704 | 0.058 | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1004` | 3 |
| 9,014.111 | 3 | 3,004.704 | 4,750.690 | 0.155 | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1449` | 3 |
| 9,013.957 | 3 | 3,004.652 | 4,750.618 | 2.374 | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1159` | 3 |
| 8,079.034 | 3 | 2,693.011 | 4,554.064 | 15.012 | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1343` | 3 |
| 7,744.161 | 309 | 25.062 | 586.296 | 7.305 | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1121` | 3 |
| 7,395.586 | 317 | 23.330 | 309.553 | 7,384.022 | `SourceThreadProcess._read_message` | `golden_source_threads.py:892` | 3 |
| 6,950.958 | 3 | 2,316.986 | 4,750.930 | 5.121 | `_WorkItem.run` | `thread.py:53` | 3 |
| 6,376.388 | 1 | 6,376.388 | 6,376.388 | 0.645 | `golden_clip_forward` | `golden_serial.py:12420` | 1 |
| 6,359.734 | 1 | 6,359.734 | 6,359.734 | 0.025 | `CLIPTextEncode.encode` | `nodes.py:73` | 1 |
| 5,906.123 | 14 | 421.866 | 4,544.088 | 4.986 | `BaseEventLoop._run_once` | `base_events.py:1845` | 5 |
| 5,804.500 | 1 | 5,804.500 | 5,804.500 | 0.345 | `golden_sampling` | `golden_serial.py:13704` | 1 |
| 5,657.799 | 2 | 2,828.899 | 4,750.731 | 0.067 | `thread_traced.<locals>._run` | `full_execution_trace.py:276` | 2 |
| 5,592.644 | 1 | 5,592.644 | 5,592.644 | 0.316 | `ClownsharKSampler_Beta.main` | `samplers.py:1745` | 1 |
| 5,587.699 | 1 | 5,587.699 | 5,587.699 | 26.065 | `SharkSampler.main` | `samplers.py:153` | 1 |
| 5,497.448 | 2 | 2,748.724 | 5,222.189 | 0.181 | `CFGGuider.sample` | `samplers.py:1276` | 2 |
| 5,496.835 | 2 | 2,748.418 | 5,221.947 | 0.163 | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` | 2 |
| 5,495.428 | 2 | 2,747.714 | 5,221.509 | 0.015 | `WrapperExecutor.__call__` | `patcher_extension.py:103` | 2 |
| 5,495.355 | 2 | 2,747.677 | 5,221.486 | 3.577 | `CFGGuider.outer_sample` | `samplers.py:1240` | 2 |
| 5,451.625 | 16 | 340.727 | 4,543.124 | 5,451.617 | `EpollSelector.select` | `selectors.py:451` | 5 |
| 5,117.536 | 2 | 2,558.768 | 5,052.122 | 62.949 | `CFGGuider.inner_sample` | `samplers.py:1220` | 2 |
| 5,053.551 | 74 | 68.291 | 5,050.515 | 1.510 | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` | 2 |
| 5,053.340 | 2 | 2,526.670 | 5,051.448 | 0.265 | `KSAMPLER.sample` | `samplers.py:983` | 2 |
| 5,050.160 | 2 | 2,525.080 | 5,050.158 | 71.733 | `sample_rk_beta` | `rk_sampler_beta.py:110` | 2 |
| 4,960.311 | 1 | 4,960.311 | 4,960.311 | 0.028 | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` | 1 |
| 4,960.283 | 1 | 4,960.283 | 4,960.283 | 0.062 | `CLIP.encode_from_tokens` | `sd.py:396` | 1 |
| 4,672.648 | 1 | 4,672.648 | 4,672.648 | 0.050 | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` | 1 |
| 4,672.597 | 1 | 4,672.597 | 4,672.597 | 9.079 | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` | 1 |
| 4,663.398 | 1 | 4,663.398 | 4,663.398 | 0.005 | `SDClipModel.encode` | `sd1_clip.py:305` | 1 |
| 4,663.345 | 1 | 4,663.345 | 4,663.345 | 0.080 | `SDClipModel.forward` | `sd1_clip.py:260` | 1 |
| 4,544.407 | 1 | 4,544.407 | 4,544.407 | 0.110 | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` | 1 |
| 4,534.001 | 1 | 4,534.001 | 4,534.001 | 0.011 | `BaseLlama.forward` | `llama.py:998` | 1 |
| 4,533.074 | 1 | 4,533.074 | 4,533.074 | 657.141 | `Llama2_.forward` | `llama.py:824` | 1 |
| 4,447.653 | 2 | 2,223.827 | 3,373.023 | 0.036 | `Thread.run` | `threading.py:964` | 2 |
| 4,447.618 | 2 | 2,223.809 | 3,373.002 | 2,247.557 | `_worker` | `thread.py:69` | 2 |
| 3,932.211 | 17 | 231.307 | 761.055 | 6.745 | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` | 1 |
| 3,924.344 | 17 | 230.844 | 759.896 | 2.923 | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` | 1 |
| 3,920.551 | 17 | 230.621 | 758.857 | 0.187 | `KSamplerX0Inpaint.__call__` | `samplers.py:634` | 1 |
| 3,920.360 | 17 | 230.609 | 758.845 | 0.112 | `CFGGuider.__call__` | `samplers.py:1207` | 1 |
| 3,920.248 | 17 | 230.603 | 758.836 | 0.250 | `CFGGuider.outer_predict_noise` | `samplers.py:1210` | 1 |
| 3,919.662 | 17 | 230.568 | 758.790 | 0.475 | `SharkGuider.predict_noise` | `samplers.py:99` | 1 |
| 3,919.187 | 17 | 230.540 | 758.766 | 0.494 | `sampling_function` | `samplers.py:609` | 1 |
| 3,876.150 | 17 | 228.009 | 747.076 | 0.071 | `calc_cond_batch` | `samplers.py:208` | 1 |
| 3,876.078 | 17 | 228.005 | 747.071 | 0.123 | `_calc_cond_batch_outer` | `samplers.py:214` | 1 |
| 3,874.188 | 17 | 227.893 | 746.861 | 14.995 | `_calc_cond_batch` | `samplers.py:221` | 1 |
| 3,818.408 | 17 | 224.612 | 740.976 | 0.255 | `BaseModel.apply_model` | `model_base.py:204` | 1 |
| 3,817.172 | 17 | 224.540 | 740.868 | 4.667 | `BaseModel._apply_model` | `model_base.py:211` | 1 |
| 3,801.396 | 17 | 223.612 | 738.582 | 3,801.396 | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` | 1 |
| 3,500.347 | 2 | 1,750.174 | 3,368.407 | 0.836 | `golden_clip_load` | `golden_serial.py:11497` | 1 |
| 3,356.569 | 1 | 3,356.569 | 3,356.569 | 3,356.569 | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` | 1 |
| 3,356.495 | 1 | 3,356.495 | 3,356.495 | 0.036 | `_read_golden_m2_clip` | `golden_serial.py:11462` | 1 |
| 3,356.453 | 1 | 3,356.453 | 3,356.453 | 0.015 | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1001` | 1 |
| 2,791.764 | 1 | 2,791.764 | 2,791.764 | 1.738 | `Llama2_.compute_freqs_cis` | `llama.py:815` | 1 |
| 2,790.026 | 1 | 2,790.026 | 2,790.026 | 298.872 | `precompute_freqs_cis` | `llama.py:445` | 1 |
| 2,754.148 | 306 | 9.000 | 1,376.591 | 1,377.256 | `SpecialTokensMixin.__getattr__` | `tokenization_utils_base.py:1077` | 2 |

## 3. Per-stage call trees

Depth is uncapped; the wall floor limits it. Breadth is capped at 8 children plus any child at or above 10% of its parent.

### `golden_restore`

- Stage wall: **0.473 ms**

_Nothing below the stage body reached the threshold._

### `golden_request_setup`

- Stage wall: **2.670 ms**

- `golden_request_setup` 
  wall **2.670 ms**  self **2.670 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **2.640 ms**  self **0.106 ms**  `golden_serial.py:9977`

### `golden_clip_load`

- Stage wall: **3,506.679 ms**

- `golden_clip_load` 
  wall **3,506.679 ms**  self **20.057 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **3,373.023 ms**  self **0.021 ms**  `threading.py:964`
    - `_worker` 
      wall **3,373.002 ms**  self **2,080.385 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **1,292.599 ms**  self **5.078 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **1,287.471 ms**  self **0.558 ms**  `golden_serial.py:2341`
          - `load_text_encoder_state_dicts` 
            wall **839.976 ms**  self **0.301 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **838.797 ms**  self **0.396 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **690.188 ms**  self **0.030 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **690.158 ms**  self **0.049 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **690.109 ms**  self **5.876 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **684.233 ms**  self **0.161 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **647.278 ms**  self **1.517 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **598.824 ms**  self **11.133 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **587.264 ms**  self **348.418 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **175.439 ms**  self **17.415 ms**  `__init__.py:274`
                              - `loads` 
                                wall **158.024 ms**  self **0.012 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **158.012 ms**  self **0.026 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **157.986 ms**  self **157.986 ms**  `decoder.py:343`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **30.051 ms**  self **30.051 ms**  `tokenization_qwen2.py:174`
                            - `PreTrainedTokenizer.__init__` 
                              wall **24.462 ms**  self **1.229 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **22.493 ms**  self **4.119 ms**  `tokenization_utils.py:512`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **9.887 ms**  self **9.845 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_trie` 
                                  wall **5.652 ms**  self **0.074 ms**  `tokenization_utils.py:590`
                                  - `Trie.add` 
                                    wall **5.387 ms**  self **5.387 ms**  `tokenization_utils.py:74`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **2.756 ms**  self **0.976 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **1.738 ms**  self **1.697 ms**  `tokenization_qwen2.py:215`
                            - `compile` 
                              wall **8.075 ms**  self **0.059 ms**  `_main.py:359`
                              - `_compile` 
                                wall **8.015 ms**  self **0.321 ms**  `_main.py:460`
                                - `_parse_pattern` 
                                  wall **3.253 ms**  self **0.021 ms**  `_regex_core.py:452`
                                  - `parse_sequence` 
                                    wall **2.222 ms**  self **0.037 ms**  `_regex_core.py:462`
                                    - `parse_paren` 
                                      wall **2.171 ms**  self **0.021 ms**  `_regex_core.py:850`
                                      - `parse_flags_subpattern` 
                                        wall **2.149 ms**  self **0.020 ms**  `_regex_core.py:1185`
                                        - `parse_subpattern` 
                                          wall **2.058 ms**  self **0.013 ms**  `_regex_core.py:1166`
                                          - `_parse_pattern` 
                                            wall **2.021 ms**  self **0.016 ms**  `_regex_core.py:452`
                                            - `parse_sequence` 
                                              wall **1.814 ms**  self **0.079 ms**  `_regex_core.py:462`
                                              - `Character.__init__` 
                                                wall **1.673 ms**  self **1.667 ms**  `_regex_core.py:2588`
                                - `Branch.pack_characters` 
                                  wall **3.247 ms**  self **0.004 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **3.243 ms**  self **0.010 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **3.191 ms**  self **0.015 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **3.059 ms**  self **0.052 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **2.973 ms**  self **0.004 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **2.969 ms**  self **2.969 ms**  `_regex_core.py:362`
                        - `load` 
                          wall **41.038 ms**  self **40.898 ms**  `__init__.py:274`
                        - `Path.is_dir` 
                          wall **1.209 ms**  self **0.015 ms**  `pathlib.py:1245`
                          - `Path.stat` 
                            wall **1.190 ms**  self **1.174 ms**  `pathlib.py:1008`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **34.332 ms**  self **34.332 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **1.930 ms**  self **1.886 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **75.026 ms**  self **0.018 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **75.008 ms**  self **0.025 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **74.983 ms**  self **0.184 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **73.933 ms**  self **0.072 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **73.862 ms**  self **1.295 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **61.841 ms**  self **0.069 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **61.689 ms**  self **0.911 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **50.225 ms**  self **0.231 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **4.996 ms**  self **0.054 ms**  `llama.py:654`
                                - `RMSNorm.__init__` 
                                  wall **4.203 ms**  self **4.083 ms**  `llama.py:430`
                              - `TransformerBlock.__init__` 
                                wall **3.450 ms**  self **0.035 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.964 ms**  self **0.036 ms**  `llama.py:512`
                                  - `RMSNorm.__init__` 
                                    wall **1.375 ms**  self **1.124 ms**  `llama.py:430`
                              - `TransformerBlock.__init__` 
                                wall **2.353 ms**  self **0.048 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **2.253 ms**  self **0.024 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.480 ms**  self **0.039 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **2.238 ms**  self **0.012 ms**  `llama.py:654`
                                - `MLP.__init__` 
                                  wall **1.413 ms**  self **0.011 ms**  `llama.py:627`
                                  - `disable_weight_init.Linear.__init__` 
                                    wall **1.276 ms**  self **0.006 ms**  `ops.py:523`
                                    - `Module.__setattr__` 
                                      wall **1.234 ms**  self **0.006 ms**  `module.py:1976`
                                      - `_ParameterMeta.__instancecheck__` 
                                        wall **1.227 ms**  self **1.227 ms**  `parameter.py:21`
                              - `TransformerBlock.__init__` 
                                wall **2.158 ms**  self **0.079 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.587 ms**  self **0.154 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **2.027 ms**  self **0.014 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.497 ms**  self **0.030 ms**  `llama.py:512`
                                  - `RMSNorm.__init__` 
                                    wall **1.105 ms**  self **1.034 ms**  `llama.py:430`
                              - `TransformerBlock.__init__` 
                                wall **1.922 ms**  self **0.019 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.277 ms**  self **0.032 ms**  `llama.py:512`
                              _... 13 more children >= 1 ms omitted_
                            - `disable_weight_init.Embedding.__init__` 
                              wall **10.076 ms**  self **0.211 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **9.686 ms**  self **9.686 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **10.431 ms**  self **0.130 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **6.782 ms**  self **0.004 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **6.778 ms**  self **0.007 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **6.754 ms**  self **0.010 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **6.709 ms**  self **0.037 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **60.586 ms**  self **0.457 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **53.757 ms**  self **0.011 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **53.745 ms**  self **0.033 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **53.710 ms**  self **0.179 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **53.531 ms**  self **0.051 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **52.780 ms**  self **0.030 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **51.485 ms**  self **0.425 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **5.762 ms**  self **0.019 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **5.438 ms**  self **0.019 ms**  `module.py:2589`
                                - `Module.load_state_dict.<locals>.load` 
                                  wall **4.887 ms**  self **0.040 ms**  `module.py:2589`
                                  - `Module._load_from_state_dict` 
                                    wall **4.845 ms**  self **0.019 ms**  `module.py:2350`
                                    - `Module.__setattr__` 
                                      wall **4.811 ms**  self **0.005 ms**  `module.py:1976`
                                      - `Module.__setattr__.<locals>.remove_from` 
                                        wall **4.798 ms**  self **4.798 ms**  `module.py:1977`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **3.214 ms**  self **0.081 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.872 ms**  self **1.827 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **2.151 ms**  self **0.058 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **2.107 ms**  self **0.038 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.012 ms**  self **0.031 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.869 ms**  self **0.024 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.459 ms**  self **0.028 ms**  `module.py:2589`
                                - `Module.load_state_dict.<locals>.load` 
                                  wall **1.018 ms**  self **0.968 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.803 ms**  self **0.022 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.491 ms**  self **0.094 ms**  `module.py:2589`
                                - `Module.load_state_dict.<locals>.load` 
                                  wall **1.011 ms**  self **0.009 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.759 ms**  self **0.027 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.202 ms**  self **0.024 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.640 ms**  self **0.054 ms**  `module.py:2589`
                            _... 7 more children >= 1 ms omitted_
              - `archive_model_dtypes` 
                wall **9.639 ms**  self **1.369 ms**  `model_management.py:1045`
                - `Module.named_parameters` 
                  wall **2.030 ms**  self **0.004 ms**  `module.py:2699`
                  - `Module._named_members` 
                    wall **2.026 ms**  self **2.006 ms**  `module.py:2650`
              - `ModelPatcherDynamic.__init__` 
                wall **2.119 ms**  self **0.042 ms**  `model_patcher.py:1757`
                - `ModelPatcher.__init__` 
                  wall **1.854 ms**  self **0.161 ms**  `model_patcher.py:341`
                  - `uuid4` 
                    wall **1.206 ms**  self **1.189 ms**  `uuid.py:721`
          - `_clip_meta_state_dict_from_header` 
            wall **446.873 ms**  self **359.362 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **87.264 ms**  self **85.646 ms**  `clip_qd_reader.py:300`
  - `golden_clip_load` 
    wall **3,368.407 ms**  self **0.256 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **3,356.495 ms**  self **0.036 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **3,356.453 ms**  self **0.015 ms**  `golden_model_transport.py:1001`
        - `GoldenModelTransport._load_sync` 
          wall **3,356.439 ms**  self **0.020 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **3,356.418 ms**  self **0.065 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **3,356.353 ms**  self **0.841 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **2,884.917 ms**  self **5.989 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **342.342 ms**  self **0.077 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **309.553 ms**  self **309.553 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **24.114 ms**  self **24.049 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._recover_ready_from_table` 
                    wall **6.121 ms**  self **0.056 ms**  `golden_source_threads.py:1092`
                    - `_FileLock.__exit__` 
                      wall **5.383 ms**  self **5.383 ms**  `golden_source_threads.py:493`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **1.988 ms**  self **0.052 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **1.724 ms**  self **1.724 ms**  `golden_source_threads.py:486`
                - `SourceThreadProcess.wait_ready` 
                  wall **197.861 ms**  self **0.023 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **194.000 ms**  self **193.969 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._poll_child` 
                    wall **2.410 ms**  self **0.006 ms**  `golden_source_threads.py:1001`
                    - `Popen.poll` 
                      wall **2.404 ms**  self **0.004 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **2.400 ms**  self **2.400 ms**  `subprocess.py:1966`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **1.428 ms**  self **0.033 ms**  `golden_source_threads.py:1036`
                - `SourceThreadProcess.wait_ready` 
                  wall **102.868 ms**  self **0.036 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **70.608 ms**  self **70.579 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **29.352 ms**  self **0.057 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **21.591 ms**  self **21.591 ms**  `golden_source_threads.py:486`
                    - `_FileLock.__exit__` 
                      wall **7.646 ms**  self **7.646 ms**  `golden_source_threads.py:493`
                  - `SourceThreadProcess._poll_child` 
                    wall **2.871 ms**  self **0.009 ms**  `golden_source_threads.py:1001`
                    - `Popen.poll` 
                      wall **2.863 ms**  self **0.008 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **2.855 ms**  self **2.855 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **48.511 ms**  self **0.022 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **47.839 ms**  self **47.800 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **47.491 ms**  self **0.070 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **46.391 ms**  self **46.346 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **45.474 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **44.895 ms**  self **44.854 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **44.865 ms**  self **0.045 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **44.185 ms**  self **44.138 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **43.761 ms**  self **0.020 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **43.212 ms**  self **43.187 ms**  `golden_source_threads.py:892`
                _... 121 more children >= 1 ms omitted_
              - `GoldenModelTransport.inspect` 
                wall **425.514 ms**  self **0.052 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **424.810 ms**  self **423.916 ms**  `golden_model_transport.py:304`
              - `GpuDestinationPool.acquire` 
                wall **16.061 ms**  self **0.076 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **15.971 ms**  self **15.808 ms**  `golden_model_transport.py:156`
              - `SourceThreadProcess.snapshot` 
                wall **9.826 ms**  self **0.938 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **7.159 ms**  self **0.586 ms**  `golden_source_threads.py:589`
              - `SourceThreadProcess.snapshot` 
                wall **8.038 ms**  self **0.755 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **6.358 ms**  self **0.533 ms**  `golden_source_threads.py:589`
              - `GoldenModelTransport._views` 
                wall **6.321 ms**  self **6.321 ms**  `golden_model_transport.py:1910`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **3.340 ms**  self **0.136 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **1.019 ms**  self **0.021 ms**  `golden_qd_transport.py:3115`
    - `GoldenTelemetryRecorder.event` 
      wall **7.439 ms**  self **0.014 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **7.425 ms**  self **0.014 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **7.411 ms**  self **0.009 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **7.401 ms**  self **0.042 ms**  `copy.py:227`
            - `deepcopy` 
              wall **7.254 ms**  self **0.003 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **7.250 ms**  self **0.010 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **6.680 ms**  self **0.003 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **6.677 ms**  self **0.188 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **3.669 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **3.666 ms**  self **0.912 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.823 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_dict` 
                        wall **1.820 ms**  self **0.158 ms**  `copy.py:227`
    - `_start_clip_skeleton_overlap` 
      wall **1.502 ms**  self **0.059 ms**  `golden_serial.py:2336`
      - `ThreadPoolExecutor.submit` 
        wall **1.326 ms**  self **0.023 ms**  `thread.py:161`
        - `ThreadPoolExecutor._adjust_thread_count` 
          wall **1.284 ms**  self **0.029 ms**  `thread.py:180`
          - `Thread.start` 
            wall **1.196 ms**  self **0.331 ms**  `threading.py:938`
  - `golden.clip_load.source_open_read` 
    wall **3,356.569 ms**  self **3,356.569 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **131.940 ms**  self **0.580 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **75.373 ms**  self **2.173 ms**  `golden_serial.py:13011`
      - `validate_qd_adoption` 
        wall **8.743 ms**  self **2.041 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **2.550 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.547 ms**  self **0.479 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **8.340 ms**  self **0.237 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **3.545 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **3.542 ms**  self **0.873 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **8.290 ms**  self **0.275 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.746 ms**  self **0.004 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.742 ms**  self **0.470 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **8.149 ms**  self **0.270 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **3.005 ms**  self **0.006 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **3.000 ms**  self **0.466 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **7.001 ms**  self **0.227 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.401 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.399 ms**  self **0.491 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.986 ms**  self **0.215 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.978 ms**  self **0.005 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.974 ms**  self **0.728 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.260 ms**  self **0.219 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.214 ms**  self **0.005 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.209 ms**  self **0.466 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **43.403 ms**  self **0.444 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **36.732 ms**  self **0.008 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **36.723 ms**  self **0.027 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **36.695 ms**  self **0.153 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **36.541 ms**  self **0.013 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **35.872 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **34.540 ms**  self **0.181 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.735 ms**  self **0.030 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.249 ms**  self **0.037 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.091 ms**  self **0.026 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.049 ms**  self **0.022 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.029 ms**  self **0.025 ms**  `module.py:2589`
      - `Module.__setattr__` 
        wall **1.297 ms**  self **0.240 ms**  `module.py:1976`
        - `_ParameterMeta.__instancecheck__` 
          wall **1.054 ms**  self **1.054 ms**  `parameter.py:21`
    - `_clip_compute_identity` 
      wall **9.813 ms**  self **0.041 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **9.578 ms**  self **2.312 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **2.257 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.255 ms**  self **0.446 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **75.473 ms**  self **75.473 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **43.444 ms**  self **43.444 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.compute_ready_proof` 
    wall **9.832 ms**  self **9.832 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_patcher_construction` 
    wall **1.296 ms**  self **0.785 ms**  `full_execution_trace.py:330`

### `golden_clip_forward`

- Stage wall: **6,376.576 ms**

- `golden_clip_forward` 
  wall **6,376.576 ms**  self **6,376.576 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **6,376.388 ms**  self **0.645 ms**  `golden_serial.py:12420`
    - `GoldenSerialRunner.run_closure` 
      wall **6,364.103 ms**  self **0.056 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **6,360.821 ms**  self **0.062 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **6,360.132 ms**  self **0.100 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **6,359.734 ms**  self **0.025 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **4,960.311 ms**  self **0.028 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **4,960.283 ms**  self **0.062 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **4,672.648 ms**  self **0.050 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **4,672.597 ms**  self **9.079 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **4,663.398 ms**  self **0.005 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **4,663.394 ms**  self **0.010 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **4,663.383 ms**  self **0.039 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **4,663.345 ms**  self **0.080 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **4,534.037 ms**  self **0.010 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **4,534.027 ms**  self **0.026 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **4,534.001 ms**  self **0.011 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **4,533.987 ms**  self **0.011 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **4,533.976 ms**  self **0.902 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **4,533.074 ms**  self **657.141 ms**  `llama.py:824`
                                        - `prefetch_queue_pop` 
                                          wall **10.002 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **9.999 ms**  self **0.008 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **9.992 ms**  self **0.010 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **9.982 ms**  self **0.040 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **9.942 ms**  self **0.270 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **7.516 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **7.509 ms**  self **0.094 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **7.414 ms**  self **2.328 ms**  `llama.py:540`
                                                        - `apply_rope` 
                                                          wall **2.650 ms**  self **2.650 ms**  `llama.py:492`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.437 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.431 ms**  self **0.014 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.418 ms**  self **0.178 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **6.594 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **6.592 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **6.586 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **6.581 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **6.569 ms**  self **0.306 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **5.050 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **5.044 ms**  self **0.027 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **5.016 ms**  self **2.240 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **6.474 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **6.472 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **6.466 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **6.460 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **6.448 ms**  self **0.176 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.977 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.973 ms**  self **0.086 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.887 ms**  self **1.635 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.635 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.629 ms**  self **0.016 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.613 ms**  self **0.073 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **5.789 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.787 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.781 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.775 ms**  self **0.015 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.760 ms**  self **0.202 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **4.049 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **4.045 ms**  self **0.019 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **4.026 ms**  self **1.460 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.201 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.197 ms**  self **0.008 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.189 ms**  self **0.114 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **5.520 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.517 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.511 ms**  self **0.007 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.505 ms**  self **0.011 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.493 ms**  self **0.145 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.692 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.686 ms**  self **0.025 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.661 ms**  self **1.498 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.121 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.115 ms**  self **0.010 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.105 ms**  self **0.088 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **5.513 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.511 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.505 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.499 ms**  self **0.013 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.486 ms**  self **0.386 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.459 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.453 ms**  self **0.024 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.429 ms**  self **1.622 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.053 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.048 ms**  self **0.010 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.037 ms**  self **0.074 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **5.370 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.367 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.361 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.356 ms**  self **0.013 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.343 ms**  self **0.329 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.482 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.476 ms**  self **0.024 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.452 ms**  self **1.306 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.166 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.161 ms**  self **0.009 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.152 ms**  self **0.130 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **5.323 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.322 ms**  self **0.007 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.315 ms**  self **0.007 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.308 ms**  self **0.012 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.296 ms**  self **0.192 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.653 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.646 ms**  self **0.027 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.619 ms**  self **1.304 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.111 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.106 ms**  self **0.011 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.096 ms**  self **0.171 ms**  `llama.py:644`
                                        _... 27 more children >= 1 ms omitted_
  - `BaseEventLoop._run_once` 
    wall **73.208 ms**  self **0.017 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **73.159 ms**  self **22.970 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **73.106 ms**  self **0.011 ms**  `golden_serial.py:15543`

### `golden_unet_load`

- Stage wall: **6,249.016 ms**

- `golden_unet_load` 
  wall **6,249.016 ms**  self **1,492.665 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **4,750.930 ms**  self **0.020 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **4,750.731 ms**  self **0.027 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **4,750.704 ms**  self **0.013 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **4,750.690 ms**  self **0.073 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **4,750.618 ms**  self **1.019 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **4,554.064 ms**  self **8.783 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **474.318 ms**  self **0.046 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **252.301 ms**  self **252.301 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **215.592 ms**  self **215.537 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._recover_ready_from_table` 
                  wall **4.779 ms**  self **0.053 ms**  `golden_source_threads.py:1092`
                  - `_FileLock.__enter__` 
                    wall **2.894 ms**  self **2.894 ms**  `golden_source_threads.py:486`
                  - `_FileLock.__exit__` 
                    wall **1.798 ms**  self **1.798 ms**  `golden_source_threads.py:493`
              - `SourceThreadProcess.wait_ready` 
                wall **317.361 ms**  self **0.063 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **250.156 ms**  self **250.156 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **66.341 ms**  self **66.303 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **95.898 ms**  self **0.020 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **94.019 ms**  self **93.984 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **1.517 ms**  self **0.454 ms**  `golden_source_threads.py:1036`
              - `SourceThreadProcess.wait_ready` 
                wall **90.435 ms**  self **0.023 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **89.650 ms**  self **89.610 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **68.639 ms**  self **0.015 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **68.456 ms**  self **68.425 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **65.354 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **64.429 ms**  self **64.390 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **59.348 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **59.028 ms**  self **58.998 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **56.942 ms**  self **0.030 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **56.163 ms**  self **56.131 ms**  `golden_source_threads.py:892`
              _... 178 more children >= 1 ms omitted_
            - `GoldenQDTransport.finalize_external_ready` 
              wall **88.811 ms**  self **0.175 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **85.302 ms**  self **0.015 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **85.275 ms**  self **0.010 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **85.261 ms**  self **0.007 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **85.252 ms**  self **85.247 ms**  `threading.py:288`
              - `_Telemetry.snapshot` 
                wall **1.491 ms**  self **0.005 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **1.486 ms**  self **0.163 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **1.206 ms**  self **0.008 ms**  `golden_qd_transport.py:2016`
                    - `_json_safe.<locals>.<dictcomp>` 
                      wall **1.184 ms**  self **0.177 ms**  `golden_qd_transport.py:2022`
              - `GoldenQDTransport._record_ranges` 
                wall **1.326 ms**  self **0.963 ms**  `golden_qd_transport.py:3261`
            - `GoldenModelTransport._views` 
              wall **48.360 ms**  self **48.360 ms**  `golden_model_transport.py:1910`
            - `SourceThreadProcess.snapshot` 
              wall **22.922 ms**  self **3.870 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **16.178 ms**  self **0.902 ms**  `golden_source_threads.py:589`
            - `SourceThreadProcess.snapshot` 
              wall **21.037 ms**  self **1.453 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **16.987 ms**  self **1.289 ms**  `golden_source_threads.py:589`
              - `_FileLock.__exit__` 
                wall **1.033 ms**  self **1.033 ms**  `golden_source_threads.py:493`
            - `GpuDestinationPool.acquire` 
              wall **8.097 ms**  self **0.052 ms**  `golden_model_transport.py:183`
              - `GpuDestinationPool._allocate` 
                wall **8.029 ms**  self **7.787 ms**  `golden_model_transport.py:156`
            - `GoldenModelTransport.inspect` 
              wall **3.230 ms**  self **0.025 ms**  `golden_model_transport.py:973`
              - `_file_identity` 
                wall **3.205 ms**  self **3.205 ms**  `golden_model_transport.py:274`
  - `golden.unet.source_h2d_transport` 
    wall **4,544.407 ms**  self **0.110 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop._run_once` 
    wall **4,544.088 ms**  self **0.034 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **4,543.124 ms**  self **4,543.122 ms**  `selectors.py:451`
  - `Llama2_.compute_freqs_cis` 
    wall **2,791.764 ms**  self **1.738 ms**  `llama.py:815`
    - `precompute_freqs_cis` 
      wall **2,790.026 ms**  self **298.872 ms**  `llama.py:445`
      - `_register_overrides_from_graph.<locals>.eager_router` 
        wall **1,903.203 ms**  self **0.018 ms**  `registry.py:938`
        - `_register_overrides_from_graph.<locals>._dispatch` 
          wall **1,903.178 ms**  self **0.045 ms**  `registry.py:926`
          - `OpOverloadPacket.__call__` 
            wall **1,901.991 ms**  self **0.088 ms**  `_ops.py:1338`
            - `_bmm_outer_product_impl` 
              wall **1,901.903 ms**  self **95.460 ms**  `triton_impl.py:18`
              - `bmm_outer_product` 
                wall **1,806.378 ms**  self **0.621 ms**  `triton_kernels.py:77`
                - `_make_wrapper.<locals>.wrapper` 
                  wall **1,805.597 ms**  self **0.009 ms**  `instrumentation.py:202`
                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                    wall **1,805.513 ms**  self **0.041 ms**  `jit.py:374`
                    - `JITFunction.run` 
                      wall **1,805.471 ms**  self **0.159 ms**  `jit.py:726`
                      - `DriverConfig.active` 
                        wall **880.328 ms**  self **0.005 ms**  `driver.py:36`
                        - `DriverConfig.default` 
                          wall **880.323 ms**  self **0.020 ms**  `driver.py:30`
                          - `_create_driver` 
                            wall **880.303 ms**  self **0.058 ms**  `driver.py:8`
                            - `CudaDriver.__init__` 
                              wall **880.177 ms**  self **0.034 ms**  `driver.py:341`
                              - `CudaUtils.__init__` 
                                wall **880.117 ms**  self **0.046 ms**  `driver.py:100`
                                - `compile_module_from_file` 
                                  wall **825.775 ms**  self **0.014 ms**  `build.py:193`
                                  - `_compile_so_from_file` 
                                    wall **825.761 ms**  self **5.707 ms**  `build.py:157`
                                    - `_compile_so` 
                                      wall **820.000 ms**  self **0.463 ms**  `build.py:132`
                                      - `_build` 
                                        wall **796.794 ms**  self **0.076 ms**  `build.py:60`
                                        - `check_call` 
                                          wall **784.739 ms**  self **0.014 ms**  `subprocess.py:398`
                                          - `call` 
                                            wall **784.721 ms**  self **0.019 ms**  `subprocess.py:381`
                                            - `Popen.wait` 
                                              wall **778.258 ms**  self **0.003 ms**  `subprocess.py:1259`
                                              - `Popen._wait` 
                                                wall **778.255 ms**  self **0.019 ms**  `subprocess.py:2014`
                                                - `Popen._try_wait` 
                                                  wall **778.232 ms**  self **778.232 ms**  `subprocess.py:2001`
                                            - `Popen.__init__` 
                                              wall **6.434 ms**  self **0.050 ms**  `subprocess.py:807`
                                              - `Popen._execute_child` 
                                                wall **6.268 ms**  self **5.754 ms**  `subprocess.py:1789`
                                        - `_find_compiler` 
                                          wall **10.044 ms**  self **0.078 ms**  `build.py:21`
                                          - `which` 
                                            wall **6.666 ms**  self **0.257 ms**  `shutil.py:1452`
                                            - `_access_check` 
                                              wall **2.416 ms**  self **2.416 ms**  `shutil.py:1447`
                                            - `_access_check` 
                                              wall **1.592 ms**  self **1.592 ms**  `shutil.py:1447`
                                          - `which` 
                                            wall **3.299 ms**  self **0.145 ms**  `shutil.py:1452`
                                            - `_access_check` 
                                              wall **2.358 ms**  self **2.358 ms**  `shutil.py:1447`
                                        - `get_paths` 
                                          wall **1.507 ms**  self **0.011 ms**  `sysconfig.py:609`
                                          - `_expand_vars` 
                                            wall **1.496 ms**  self **0.774 ms**  `sysconfig.py:261`
                                      - `_get_cache_manager` 
                                        wall **19.061 ms**  self **0.490 ms**  `build.py:117`
                                        - `platform_key` 
                                          wall **17.034 ms**  self **0.043 ms**  `build.py:94`
                                          - `architecture` 
                                            wall **16.975 ms**  self **0.057 ms**  `platform.py:646`
                                            - `_syscmd_file` 
                                              wall **16.918 ms**  self **1.307 ms**  `platform.py:602`
                                              - `check_output` 
                                                wall **15.058 ms**  self **0.019 ms**  `subprocess.py:417`
                                                - `run` 
                                                  wall **15.039 ms**  self **0.024 ms**  `subprocess.py:506`
                                                  - `Popen.__init__` 
                                                    wall **15.015 ms**  self **1.420 ms**  `subprocess.py:807`
                                                    - `Popen._execute_child` 
                                                      wall **12.466 ms**  self **11.709 ms**  `subprocess.py:1789`
                                                    - `Popen._get_handles` 
                                                      wall **1.126 ms**  self **0.788 ms**  `subprocess.py:1686`
                                        - `get_cache_manager` 
                                          wall **1.537 ms**  self **0.027 ms**  `cache.py:258`
                                          - `FileCacheManager.__init__` 
                                            wall **1.136 ms**  self **1.113 ms**  `cache.py:38`
                                      - `TemporaryDirectory.__init__` 
                                        wall **1.003 ms**  self **0.045 ms**  `tempfile.py:852`
                                - `library_dirs` 
                                  wall **54.296 ms**  self **0.018 ms**  `driver.py:49`
                                  - `libcuda_dirs` 
                                    wall **54.278 ms**  self **0.372 ms**  `driver.py:25`
                                    - `check_output` 
                                      wall **53.541 ms**  self **0.032 ms**  `subprocess.py:417`
                                      - `run` 
                                        wall **53.505 ms**  self **0.077 ms**  `subprocess.py:506`
                                        - `Popen.__init__` 
                                          wall **28.082 ms**  self **0.978 ms**  `subprocess.py:807`
                                          - `Popen._execute_child` 
                                            wall **26.626 ms**  self **25.696 ms**  `subprocess.py:1789`
                                        - `Popen.communicate` 
                                          wall **25.322 ms**  self **25.130 ms**  `subprocess.py:1165`
                      - `JITFunction._do_compile` 
                        wall **542.012 ms**  self **0.058 ms**  `jit.py:877`
                        - `compile` 
                          wall **541.925 ms**  self **29.249 ms**  `compiler.py:226`
                          - `get_cache_key` 
                            wall **168.905 ms**  self **0.033 ms**  `cache.py:319`
                            - `CUDABackend.hash` 
                              wall **164.141 ms**  self **0.010 ms**  `compiler.py:611`
                              - `get_ptxas_version` 
                                wall **164.131 ms**  self **0.015 ms**  `compiler.py:42`
                                - `get_ptxas` 
                                  wall **151.004 ms**  self **0.015 ms**  `compiler.py:38`
                                  - `env_base.__get__` 
                                    wall **150.989 ms**  self **0.003 ms**  `knobs.py:76`
                                    - `env_nvidia_tool.get` 
                                      wall **150.986 ms**  self **0.005 ms**  `knobs.py:203`
                                      - `env_nvidia_tool.transform` 
                                        wall **150.981 ms**  self **0.010 ms**  `knobs.py:206`
                                        - `NvidiaTool.from_path` 
                                          wall **150.972 ms**  self **0.018 ms**  `knobs.py:181`
                                          - `check_output` 
                                            wall **150.529 ms**  self **0.013 ms**  `subprocess.py:417`
                                            - `run` 
                                              wall **150.514 ms**  self **0.026 ms**  `subprocess.py:506`
                                              - `Popen.__init__` 
                                                wall **78.332 ms**  self **0.191 ms**  `subprocess.py:807`
                                                - `Popen._execute_child` 
                                                  wall **78.028 ms**  self **77.174 ms**  `subprocess.py:1789`
                                              - `Popen.communicate` 
                                                wall **72.149 ms**  self **72.084 ms**  `subprocess.py:1165`
                                - `check_output` 
                                  wall **13.103 ms**  self **0.012 ms**  `subprocess.py:417`
                                  - `run` 
                                    wall **13.088 ms**  self **0.021 ms**  `subprocess.py:506`
                                    - `Popen.communicate` 
                                      wall **8.310 ms**  self **8.191 ms**  `subprocess.py:1165`
                                    - `Popen.__init__` 
                                      wall **4.747 ms**  self **0.148 ms**  `subprocess.py:807`
                                      - `Popen._execute_child` 
                                        wall **4.462 ms**  self **4.156 ms**  `subprocess.py:1789`
                            - `ASTSource.hash` 
                              wall **2.829 ms**  self **0.061 ms**  `compiler.py:71`
                              - `JITCallable.cache_key` 
                                wall **2.753 ms**  self **0.103 ms**  `jit.py:515`
                                - `JITCallable.parse` 
                                  wall **1.423 ms**  self **0.013 ms**  `jit.py:546`
                                  - `parse` 
                                    wall **1.410 ms**  self **1.410 ms**  `ast.py:33`
                                - `NodeVisitor.visit` 
                                  wall **1.142 ms**  self **0.010 ms**  `ast.py:414`
                                  - `NodeVisitor.generic_visit` 
                                    wall **1.132 ms**  self **0.008 ms**  `ast.py:420`
                                    - `NodeVisitor.visit` 
                                      wall **1.122 ms**  self **0.005 ms**  `ast.py:414`
                                      - `DependenciesFinder.visit_FunctionDef` 
                                        wall **1.117 ms**  self **0.006 ms**  `jit.py:196`
                                        - `NodeVisitor.generic_visit` 
                                          wall **1.101 ms**  self **0.020 ms**  `ast.py:420`
                            - `CUDAOptions.hash` 
                              wall **1.903 ms**  self **0.045 ms**  `compiler.py:153`
                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                wall **1.825 ms**  self **0.011 ms**  `compiler.py:155`
                                - `file_hash` 
                                  wall **1.814 ms**  self **1.814 ms**  `compiler.py:97`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **89.258 ms**  self **0.012 ms**  `compiler.py:606`
                            - `CUDABackend.make_ptx` 
                              wall **89.246 ms**  self **87.679 ms**  `compiler.py:480`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **82.136 ms**  self **0.108 ms**  `compiler.py:605`
                            - `CUDABackend.make_llir` 
                              wall **82.027 ms**  self **81.833 ms**  `compiler.py:367`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **62.342 ms**  self **0.040 ms**  `compiler.py:607`
                            - `CUDABackend.make_cubin` 
                              wall **62.299 ms**  self **0.752 ms**  `compiler.py:513`
                              - `run` 
                                wall **60.582 ms**  self **0.031 ms**  `subprocess.py:506`
                                - `Popen.communicate` 
                                  wall **56.058 ms**  self **0.008 ms**  `subprocess.py:1165`
                                  - `Popen.wait` 
                                    wall **56.050 ms**  self **0.005 ms**  `subprocess.py:1259`
                                    - `Popen._wait` 
                                      wall **56.046 ms**  self **0.023 ms**  `subprocess.py:2014`
                                      - `Popen._try_wait` 
                                        wall **56.020 ms**  self **56.020 ms**  `subprocess.py:2001`
                                - `Popen.__init__` 
                                  wall **4.477 ms**  self **0.026 ms**  `subprocess.py:807`
                                  - `Popen._execute_child` 
                                    wall **4.392 ms**  self **0.052 ms**  `subprocess.py:1789`
                                    - `Popen._posix_spawn` 
                                      wall **4.340 ms**  self **4.312 ms**  `subprocess.py:1750`
                          - `ASTSource.make_ir` 
                            wall **43.246 ms**  self **0.027 ms**  `compiler.py:78`
                            - `ast_to_ttir` 
                              wall **43.219 ms**  self **1.390 ms**  `code_generator.py:1662`
                              - `CodeGenerator.visit` 
                                wall **36.250 ms**  self **0.069 ms**  `code_generator.py:1581`
                                - `NodeVisitor.visit` 
                                  wall **36.180 ms**  self **0.006 ms**  `ast.py:414`
                                  - `CodeGenerator.visit_Module` 
                                    wall **36.174 ms**  self **0.004 ms**  `code_generator.py:519`
                                    - `NodeVisitor.generic_visit` 
                                      wall **36.170 ms**  self **0.011 ms**  `ast.py:420`
                                      - `CodeGenerator.visit` 
                                        wall **36.155 ms**  self **0.054 ms**  `code_generator.py:1581`
                                        - `NodeVisitor.visit` 
                                          wall **36.101 ms**  self **0.013 ms**  `ast.py:414`
                                          - `CodeGenerator.visit_FunctionDef` 
                                            wall **36.089 ms**  self **0.725 ms**  `code_generator.py:628`
                                            - `CodeGenerator.visit_compound_statement` 
                                              wall **33.782 ms**  self **0.062 ms**  `code_generator.py:508`
                                              - `CodeGenerator.visit` 
                                                wall **6.554 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **6.546 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **6.543 ms**  self **0.016 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **6.484 ms**  self **0.018 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **6.466 ms**  self **0.003 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **6.463 ms**  self **0.014 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **6.097 ms**  self **0.015 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **6.082 ms**  self **0.104 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **5.707 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **5.702 ms**  self **0.003 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **5.699 ms**  self **0.001 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **5.698 ms**  self **0.009 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **5.685 ms**  self **5.685 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **6.543 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **6.534 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **6.531 ms**  self **0.023 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **6.447 ms**  self **0.028 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **6.419 ms**  self **0.004 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **6.415 ms**  self **0.015 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **6.310 ms**  self **0.011 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **6.298 ms**  self **0.094 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **5.936 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **5.930 ms**  self **0.003 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **5.927 ms**  self **0.004 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **5.923 ms**  self **0.012 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **5.907 ms**  self **5.907 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **5.208 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **5.201 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Expr` 
                                                    wall **5.199 ms**  self **0.004 ms**  `code_generator.py:1556`
                                                    - `NodeVisitor.generic_visit` 
                                                      wall **5.196 ms**  self **0.007 ms**  `ast.py:420`
                                                      - `CodeGenerator.visit` 
                                                        wall **5.187 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                        - `NodeVisitor.visit` 
                                                          wall **5.180 ms**  self **0.004 ms**  `ast.py:414`
                                                          - `CodeGenerator.visit_Call` 
                                                            wall **5.176 ms**  self **0.016 ms**  `code_generator.py:1455`
                                                            - `CodeGenerator.visit` 
                                                              wall **4.773 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                              - `NodeVisitor.visit` 
                                                                wall **4.765 ms**  self **0.008 ms**  `ast.py:414`
                                                                - `CodeGenerator.visit_BinOp` 
                                                                  wall **4.758 ms**  self **0.011 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **2.457 ms**  self **0.025 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **2.432 ms**  self **0.008 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **2.424 ms**  self **2.424 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **2.063 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **2.056 ms**  self **0.004 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **2.052 ms**  self **2.052 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **2.991 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.984 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.982 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.928 ms**  self **0.032 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.896 ms**  self **0.007 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.888 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **2.261 ms**  self **0.287 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.975 ms**  self **0.005 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.969 ms**  self **0.007 ms**  `code_generator.py:810`
                                                                - `CodeGenerator.visit` 
                                                                  wall **1.188 ms**  self **0.020 ms**  `code_generator.py:1581`
                                                                  - `NodeVisitor.visit` 
                                                                    wall **1.168 ms**  self **0.003 ms**  `ast.py:414`
                                                                    - `CodeGenerator.visit_BinOp` 
                                                                      wall **1.165 ms**  self **0.009 ms**  `code_generator.py:810`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **1.086 ms**  self **1.086 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **2.803 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.794 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.792 ms**  self **0.014 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.722 ms**  self **0.033 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.688 ms**  self **0.009 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.679 ms**  self **0.017 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.802 ms**  self **0.010 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.791 ms**  self **0.004 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.787 ms**  self **0.012 ms**  `code_generator.py:810`
                                                                - `CodeGenerator.visit` 
                                                                  wall **1.214 ms**  self **0.019 ms**  `code_generator.py:1581`
                                                                  - `NodeVisitor.visit` 
                                                                    wall **1.195 ms**  self **0.003 ms**  `ast.py:414`
                                                                    - `CodeGenerator.visit_BinOp` 
                                                                      wall **1.191 ms**  self **0.005 ms**  `code_generator.py:810`
                                                                      - `CodeGenerator._apply_binary_method` 
                                                                        wall **1.161 ms**  self **1.161 ms**  `code_generator.py:795`
                                              - `CodeGenerator.visit` 
                                                wall **2.767 ms**  self **0.011 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.756 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.753 ms**  self **0.024 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.592 ms**  self **0.056 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.536 ms**  self **0.019 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **2.517 ms**  self **0.008 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.820 ms**  self **0.008 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.812 ms**  self **0.005 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.807 ms**  self **0.005 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.802 ms**  self **0.007 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.795 ms**  self **0.011 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.782 ms**  self **0.081 ms**  `semantic.py:230`
                                                                      - `TritonSemantic.binary_op_sanitize_overflow_impl` 
                                                                        wall **1.570 ms**  self **1.570 ms**  `semantic.py:212`
                                              - `CodeGenerator.visit` 
                                                wall **2.577 ms**  self **0.013 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.565 ms**  self **0.004 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.560 ms**  self **0.025 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.469 ms**  self **0.052 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.417 ms**  self **0.009 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **2.408 ms**  self **0.014 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.025 ms**  self **0.005 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.019 ms**  self **0.003 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.016 ms**  self **0.003 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.013 ms**  self **0.002 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.010 ms**  self **0.005 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.003 ms**  self **0.017 ms**  `semantic.py:230`
                                              - `CodeGenerator.visit` 
                                                wall **1.069 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.061 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.059 ms**  self **0.010 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.015 ms**  self **0.275 ms**  `code_generator.py:1581`
                              - `JITCallable.parse` 
                                wall **3.889 ms**  self **0.013 ms**  `jit.py:546`
                                - `parse` 
                                  wall **3.876 ms**  self **3.876 ms**  `ast.py:33`
                              - `CodeGenerator.__init__` 
                                wall **1.140 ms**  self **0.314 ms**  `code_generator.py:288`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **35.368 ms**  self **0.097 ms**  `compiler.py:602`
                            - `CUDABackend.make_ttgir` 
                              wall **35.270 ms**  self **35.270 ms**  `compiler.py:260`
                          - `FileCacheManager.put` 
                            wall **10.797 ms**  self **10.090 ms**  `cache.py:103`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **6.045 ms**  self **0.044 ms**  `compiler.py:601`
                            - `CUDABackend.make_ttir` 
                              wall **6.001 ms**  self **6.001 ms**  `compiler.py:244`
                          _... 7 more children >= 1 ms omitted_
                      - `dynamic_func` 
                        wall **377.110 ms**  self **377.065 ms**  `<string>:2`
                      - `CompiledKernel.launch_metadata` 
                        wall **3.146 ms**  self **0.021 ms**  `compiler.py:493`
                        - `CompiledKernel._init_handles` 
                          wall **3.123 ms**  self **0.313 ms**  `compiler.py:448`
                          - `max_shared_mem` 
                            wall **2.417 ms**  self **2.417 ms**  `compiler.py:133`
                      - `JITFunction._pack_args` 
                        wall **1.574 ms**  self **0.078 ms**  `jit.py:702`
                        - `CUDABackend.parse_options` 
                          wall **1.104 ms**  self **0.092 ms**  `compiler.py:186`
          - `_OpNamespace.__getattr__` 
            wall **1.050 ms**  self **0.027 ms**  `_ops.py:1448`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **348.938 ms**  self **0.015 ms**  `_tensor.py:32`
        - `Tensor.__rpow__` 
          wall **348.924 ms**  self **348.924 ms**  `_tensor.py:1155`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **239.013 ms**  self **0.018 ms**  `_tensor.py:32`
        - `Tensor.__rdiv__` 
          wall **238.995 ms**  self **238.995 ms**  `_tensor.py:1120`
  - `_unet_load_with_worker_stage` 
    wall **1,419.573 ms**  self **0.039 ms**  `golden_parallel.py:517`
    - `golden_unet_load` 
      wall **1,419.528 ms**  self **0.066 ms**  `golden_serial.py:13225`
      - `GoldenModelTransport.inspect` 
        wall **1,419.318 ms**  self **0.049 ms**  `golden_model_transport.py:973`
        - `_parse_layout` 
          wall **1,418.597 ms**  self **1,417.432 ms**  `golden_model_transport.py:304`
  - `CLIP.tokenize` 
    wall **1,399.398 ms**  self **0.018 ms**  `sd.py:322`
    - `ZImageTokenizer.tokenize_with_weights` 
      wall **1,399.380 ms**  self **0.015 ms**  `z_image.py:17`
      - `SD1Tokenizer.tokenize_with_weights` 
        wall **1,399.365 ms**  self **0.036 ms**  `sd1_clip.py:698`
        - `SDTokenizer.tokenize_with_weights` 
          wall **1,399.328 ms**  self **0.084 ms**  `sd1_clip.py:572`
          - `PreTrainedTokenizerBase.__call__` 
            wall **1,398.688 ms**  self **0.025 ms**  `tokenization_utils_base.py:2827`
            - `PreTrainedTokenizerBase._call_one` 
              wall **1,398.662 ms**  self **0.012 ms**  `tokenization_utils_base.py:2925`
              - `PreTrainedTokenizerBase.encode_plus` 
                wall **1,398.649 ms**  self **0.015 ms**  `tokenization_utils_base.py:3043`
                - `PreTrainedTokenizer._encode_plus` 
                  wall **1,398.625 ms**  self **0.021 ms**  `tokenization_utils.py:743`
                  - `PreTrainedTokenizerBase.prepare_for_model` 
                    wall **1,376.855 ms**  self **0.039 ms**  `tokenization_utils_base.py:3475`
                    - `PreTrainedTokenizerBase.create_token_type_ids_from_sequences` 
                      wall **1,376.653 ms**  self **0.043 ms**  `tokenization_utils_base.py:3431`
                      - `SpecialTokensMixin.__getattr__` 
                        wall **1,376.591 ms**  self **0.012 ms**  `tokenization_utils_base.py:1077`
                        - `SpecialTokensMixin.__getattr__` 
                          wall **1,376.577 ms**  self **1,376.569 ms**  `tokenization_utils_base.py:1077`
                  - `PreTrainedTokenizer._encode_plus.<locals>.get_input_ids` 
                    wall **21.745 ms**  self **0.009 ms**  `tokenization_utils.py:765`
                    - `PreTrainedTokenizer.tokenize` 
                      wall **20.035 ms**  self **0.064 ms**  `tokenization_utils.py:621`
                      - `Qwen2Tokenizer._tokenize` 
                        wall **18.184 ms**  self **1.710 ms**  `tokenization_qwen2.py:262`
                        - `findall` 
                          wall **1.609 ms**  self **1.574 ms**  `_main.py:341`
                      - `Trie.split` 
                        wall **1.530 ms**  self **1.522 ms**  `tokenization_utils.py:105`
                    - `PreTrainedTokenizer.convert_tokens_to_ids` 
                      wall **1.701 ms**  self **0.210 ms**  `tokenization_utils.py:710`
  - `prefetch_queue_pop` 
    wall **842.117 ms**  self **0.004 ms**  `model_prefetch.py:62`
    - `Llama2_.forward.<locals>.core` 
      wall **842.113 ms**  self **0.011 ms**  `llama.py:912`
      - `Module._wrapped_call_impl` 
        wall **842.102 ms**  self **0.012 ms**  `module.py:1779`
        - `Module._call_impl` 
          wall **842.090 ms**  self **0.112 ms**  `module.py:1787`
          - `TransformerBlock.forward` 
            wall **841.978 ms**  self **0.788 ms**  `llama.py:661`
            - `Module._wrapped_call_impl` 
              wall **695.980 ms**  self **0.012 ms**  `module.py:1779`
              - `Module._call_impl` 
                wall **695.968 ms**  self **0.329 ms**  `module.py:1787`
                - `Attention.forward` 
                  wall **695.640 ms**  self **188.489 ms**  `llama.py:540`
                  - `Module._wrapped_call_impl` 
                    wall **372.616 ms**  self **0.009 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **372.607 ms**  self **0.012 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **372.595 ms**  self **0.048 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **372.530 ms**  self **370.715 ms**  `ops.py:566`
                          - `CastBiasWeightContext.__init__` 
                            wall **1.799 ms**  self **0.009 ms**  `ops.py:464`
                            - `cast_bias_weight` 
                              wall **1.789 ms**  self **1.714 ms**  `ops.py:337`
                  - `apply_rope` 
                    wall **111.797 ms**  self **111.797 ms**  `llama.py:492`
                  - `Module._wrapped_call_impl` 
                    wall **18.115 ms**  self **0.010 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **18.104 ms**  self **0.020 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **18.084 ms**  self **0.015 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **18.047 ms**  self **0.325 ms**  `ops.py:566`
                          - `CastBiasWeightContext.__init__` 
                            wall **17.710 ms**  self **0.009 ms**  `ops.py:464`
                            - `cast_bias_weight` 
                              wall **17.701 ms**  self **17.660 ms**  `ops.py:337`
                  - `Module._wrapped_call_impl` 
                    wall **1.710 ms**  self **0.013 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **1.697 ms**  self **0.026 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **1.671 ms**  self **0.074 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **1.577 ms**  self **1.169 ms**  `ops.py:566`
                  - `Module._wrapped_call_impl` 
                    wall **1.304 ms**  self **0.008 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **1.295 ms**  self **0.020 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **1.275 ms**  self **0.034 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **1.222 ms**  self **0.906 ms**  `ops.py:566`
            - `Module._wrapped_call_impl` 
              wall **98.398 ms**  self **0.009 ms**  `module.py:1779`
              - `Module._call_impl` 
                wall **98.389 ms**  self **0.025 ms**  `module.py:1787`
                - `MLP.forward` 
                  wall **98.364 ms**  self **6.765 ms**  `llama.py:644`
                  - `silu` 
                    wall **47.933 ms**  self **47.933 ms**  `functional.py:2429`
                  - `Module._wrapped_call_impl` 
                    wall **24.564 ms**  self **0.011 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **24.553 ms**  self **0.018 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **24.535 ms**  self **0.028 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **24.490 ms**  self **16.236 ms**  `ops.py:566`
                          - `CastBiasWeightContext.__init__` 
                            wall **8.231 ms**  self **0.020 ms**  `ops.py:464`
                            - `cast_bias_weight` 
                              wall **8.211 ms**  self **8.175 ms**  `ops.py:337`
                  - `Module._wrapped_call_impl` 
                    wall **18.366 ms**  self **0.006 ms**  `module.py:1779`
                    - `Module._call_impl` 
                      wall **18.360 ms**  self **0.011 ms**  `module.py:1787`
                      - `disable_weight_init.Linear.forward` 
                        wall **18.348 ms**  self **0.185 ms**  `ops.py:570`
                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                          wall **18.142 ms**  self **0.525 ms**  `ops.py:566`
                          - `CastBiasWeightContext.__init__` 
                            wall **17.606 ms**  self **0.012 ms**  `ops.py:464`
                            - `cast_bias_weight` 
                              wall **17.594 ms**  self **17.558 ms**  `ops.py:337`
            - `Module._wrapped_call_impl` 
              wall **46.352 ms**  self **0.006 ms**  `module.py:1779`
              - `Module._call_impl` 
                wall **46.347 ms**  self **0.009 ms**  `module.py:1787`
                - `RMSNorm.forward` 
                  wall **46.337 ms**  self **0.013 ms**  `llama.py:436`
                  - `rms_norm` 
                    wall **46.323 ms**  self **0.032 ms**  `rmsnorm.py:7`
                    - `rms_norm` 
                      wall **46.194 ms**  self **46.194 ms**  `functional.py:2998`
  - `CLIP.load_model` 
    wall **287.385 ms**  self **0.033 ms**  `sd.py:459`
    - `load_models_gpu` 
      wall **287.349 ms**  self **0.307 ms**  `model_management.py:909`
      - `LoadedModel.model_load` 
        wall **243.861 ms**  self **0.045 ms**  `model_management.py:782`
        - `LoadedModel.model_use_more_vram` 
          wall **243.761 ms**  self **0.011 ms**  `model_management.py:817`
          - `ModelPatcherDynamic.partially_load` 
            wall **243.749 ms**  self **0.325 ms**  `model_patcher.py:2141`
            - `ModelPatcherDynamic.load` 
              wall **243.285 ms**  self **12.376 ms**  `model_patcher.py:1853`
              - `ModelPatcher._load_list` 
                wall **166.007 ms**  self **93.196 ms**  `model_patcher.py:945`
                - `module_size` 
                  wall **3.931 ms**  self **0.007 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **3.924 ms**  self **0.016 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **3.908 ms**  self **3.908 ms**  `module.py:2148`
                - `module_size` 
                  wall **3.702 ms**  self **0.007 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **3.695 ms**  self **0.013 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **3.682 ms**  self **3.682 ms**  `module.py:2148`
                - `module_size` 
                  wall **3.229 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **3.226 ms**  self **0.007 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **3.219 ms**  self **3.219 ms**  `module.py:2148`
                - `module_size` 
                  wall **2.371 ms**  self **0.016 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **2.355 ms**  self **0.016 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **2.339 ms**  self **2.339 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.921 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.918 ms**  self **0.006 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.912 ms**  self **1.912 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.614 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.611 ms**  self **0.005 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.606 ms**  self **1.606 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.506 ms**  self **0.003 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.503 ms**  self **0.008 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.495 ms**  self **1.495 ms**  `module.py:2148`
                - `module_size` 
                  wall **1.327 ms**  self **0.004 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.323 ms**  self **0.008 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.315 ms**  self **1.315 ms**  `module.py:2148`
              - `Module.named_buffers` 
                wall **3.593 ms**  self **0.005 ms**  `module.py:2754`
                - `Module._named_members` 
                  wall **3.589 ms**  self **0.482 ms**  `module.py:2650`
              - `ModelPatcherDynamic.load.<locals>.setup_param` 
                wall **1.686 ms**  self **0.166 ms**  `model_patcher.py:1918`
                - `Module.__setattr__` 
                  wall **1.415 ms**  self **1.413 ms**  `module.py:1976`
              - `ModelPatcherDynamic.load.<locals>.set_dirty` 
                wall **1.115 ms**  self **0.008 ms**  `model_patcher.py:1914`
                - `Module.__getattr__` 
                  wall **1.092 ms**  self **1.092 ms**  `module.py:1959`
              - `ModelPatcherDynamic._vbar_get` 
                wall **1.079 ms**  self **0.036 ms**  `model_patcher.py:1797`
                - `ModelVBAR.__init__` 
                  wall **1.042 ms**  self **0.888 ms**  `model_vbar.py:50`
      - `LoadedModel.model_memory_required` 
        wall **42.155 ms**  self **0.009 ms**  `model_management.py:776`
        - `LoadedModel.model_memory` 
          wall **42.110 ms**  self **0.011 ms**  `model_management.py:767`
          - `ModelPatcher.model_size` 
            wall **42.099 ms**  self **0.264 ms**  `model_patcher.py:405`
            - `module_size` 
              wall **41.835 ms**  self **0.246 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **41.588 ms**  self **0.025 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **41.557 ms**  self **0.019 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **41.379 ms**  self **0.021 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **41.354 ms**  self **0.036 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **40.668 ms**  self **0.141 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **11.878 ms**  self **0.026 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **9.402 ms**  self **0.039 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **3.757 ms**  self **0.010 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.747 ms**  self **3.747 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **3.249 ms**  self **0.015 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.233 ms**  self **3.233 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **1.856 ms**  self **0.013 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.843 ms**  self **1.843 ms**  `module.py:2148`
                          - `Module.state_dict` 
                            wall **2.085 ms**  self **0.006 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **2.079 ms**  self **2.079 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **6.596 ms**  self **0.019 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.944 ms**  self **0.011 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **2.933 ms**  self **2.933 ms**  `module.py:2148`
                          - `Module.state_dict` 
                            wall **2.666 ms**  self **0.019 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.229 ms**  self **0.004 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **2.224 ms**  self **2.224 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **3.744 ms**  self **0.029 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **3.389 ms**  self **0.072 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.162 ms**  self **0.009 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **2.153 ms**  self **2.153 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **2.949 ms**  self **0.029 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.660 ms**  self **0.011 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **1.648 ms**  self **1.648 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **2.654 ms**  self **0.024 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.092 ms**  self **0.038 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.302 ms**  self **0.034 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.020 ms**  self **0.029 ms**  `module.py:2199`
  _... 10 more children >= 1 ms omitted_

### `golden_sampler_prepare`

- Stage wall: **67.449 ms**

- `golden_sampler_prepare` 
  wall **67.449 ms**  self **0.929 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **67.426 ms**  self **0.100 ms**  `golden_serial.py:13553`
    - `GoldenSerialRunner.run_closure` 
      wall **65.777 ms**  self **0.065 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **39.375 ms**  self **0.016 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **39.036 ms**  self **0.028 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **37.932 ms**  self **0.014 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **37.612 ms**  self **0.038 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **27.927 ms**  self **0.021 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **24.680 ms**  self **0.050 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **24.286 ms**  self **3.538 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **20.531 ms**  self **20.523 ms**  `nodes.py:1992`
                - `GoldenSerialRunner._ensure` 
                  wall **2.083 ms**  self **0.017 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._ensure` 
                  wall **1.114 ms**  self **0.013 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **7.540 ms**  self **0.122 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **6.260 ms**  self **0.057 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **5.938 ms**  self **0.046 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **5.434 ms**  self **0.027 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **5.049 ms**  self **0.004 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **5.045 ms**  self **0.008 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **5.036 ms**  self **5.034 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **2.075 ms**  self **0.035 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._ensure` 
                  wall **1.296 ms**  self **0.023 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **1.270 ms**  self **0.073 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **19.986 ms**  self **0.036 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **19.017 ms**  self **0.025 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **18.431 ms**  self **0.029 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **17.577 ms**  self **0.015 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **17.531 ms**  self **0.030 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **17.293 ms**  self **0.013 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **17.169 ms**  self **0.012 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **17.158 ms**  self **0.077 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **16.339 ms**  self **0.052 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **15.910 ms**  self **1.400 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **14.510 ms**  self **0.403 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **14.107 ms**  self **0.032 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **14.029 ms**  self **0.042 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **12.230 ms**  self **0.092 ms**  `module.py:2199`
      - `GoldenSerialRunner._ensure` 
        wall **1.720 ms**  self **0.178 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **1.132 ms**  self **0.041 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **1.055 ms**  self **0.044 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.570 ms**  self **0.020 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.150 ms**  self **0.030 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.161 ms**  self **0.013 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.074 ms**  self **0.025 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.066 ms**  self **0.011 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.054 ms**  self **0.054 ms**  `golden_serial.py:8902`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **65.823 ms**  self **65.823 ms**  `full_execution_trace.py:330`

### `golden_vae_load`

- Stage wall: **1,070.325 ms**

- `golden_vae_load` 
  wall **1,070.325 ms**  self **163.257 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **907.429 ms**  self **0.023 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **907.068 ms**  self **0.040 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **907.029 ms**  self **0.025 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **907.003 ms**  self **0.017 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **906.986 ms**  self **0.514 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **640.053 ms**  self **0.240 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **586.296 ms**  self **0.158 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **250.520 ms**  self **250.520 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **250.303 ms**  self **250.303 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **84.451 ms**  self **84.420 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **23.822 ms**  self **0.022 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **23.288 ms**  self **23.257 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **15.766 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **15.538 ms**  self **15.506 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **7.442 ms**  self **0.028 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **6.815 ms**  self **6.782 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.plan_once` 
                wall **4.506 ms**  self **0.398 ms**  `golden_source_threads.py:910`
                - `SourceThreadProcess._read_message` 
                  wall **2.941 ms**  self **2.909 ms**  `golden_source_threads.py:892`
            - `GoldenModelTransport.inspect` 
              wall **179.061 ms**  self **0.045 ms**  `golden_model_transport.py:973`
              - `_parse_layout` 
                wall **178.613 ms**  self **177.751 ms**  `golden_model_transport.py:304`
            - `GoldenModelTransport._views` 
              wall **62.211 ms**  self **62.211 ms**  `golden_model_transport.py:1910`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **17.456 ms**  self **0.058 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **16.983 ms**  self **0.012 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **16.961 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **16.948 ms**  self **0.006 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **16.939 ms**  self **16.934 ms**  `threading.py:288`
            - `GpuDestinationPool.acquire` 
              wall **4.917 ms**  self **0.049 ms**  `golden_model_transport.py:183`
              - `GpuDestinationPool._allocate` 
                wall **4.850 ms**  self **4.658 ms**  `golden_model_transport.py:156`
  - `BaseEventLoop._run_once` 
    wall **907.068 ms**  self **0.023 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **906.721 ms**  self **906.718 ms**  `selectors.py:451`
  - `sample_custom` 
    wall **278.367 ms**  self **2.760 ms**  `sample.py:86`
    - `sample` 
      wall **275.599 ms**  self **0.032 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **275.259 ms**  self **0.115 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **274.905 ms**  self **0.017 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **274.888 ms**  self **0.098 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **273.919 ms**  self **0.009 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **273.902 ms**  self **0.033 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **273.869 ms**  self **1.954 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **206.255 ms**  self **0.009 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **206.241 ms**  self **0.008 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **206.233 ms**  self **0.035 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **206.080 ms**  self **0.123 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **201.329 ms**  self **0.023 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **201.279 ms**  self **0.003 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **201.275 ms**  self **0.269 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **200.927 ms**  self **6.861 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **56.175 ms**  self **8.742 ms**  `model_patcher.py:945`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **2.854 ms**  self **0.045 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **2.707 ms**  self **0.030 ms**  `model_patcher.py:899`
                                      - `cast_to_device` 
                                        wall **2.475 ms**  self **0.002 ms**  `model_management.py:1555`
                                        - `cast_to` 
                                          wall **2.464 ms**  self **2.464 ms**  `model_management.py:1527`
                                  - `Module.named_buffers` 
                                    wall **2.790 ms**  self **0.004 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **2.786 ms**  self **0.499 ms**  `module.py:2650`
                          - `free_memory` 
                            wall **2.614 ms**  self **0.075 ms**  `model_management.py:863`
                            - `get_free_memory` 
                              wall **2.406 ms**  self **0.041 ms**  `model_management.py:1748`
                              - `mem_get_info` 
                                wall **1.858 ms**  self **1.842 ms**  `memory.py:847`
                          - `get_free_memory` 
                            wall **1.767 ms**  self **0.046 ms**  `model_management.py:1748`
                            - `mem_get_info` 
                              wall **1.244 ms**  self **1.232 ms**  `memory.py:847`
                  - `CFGGuider.inner_sample` 
                    wall **65.414 ms**  self **62.649 ms**  `samplers.py:1220`
                    - `WrapperExecutor.execute` 
                      wall **1.910 ms**  self **0.018 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.892 ms**  self **0.145 ms**  `samplers.py:983`
  - `prepare_sampling` 
    wall **167.546 ms**  self **0.008 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **167.531 ms**  self **0.004 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **167.527 ms**  self **0.020 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **167.416 ms**  self **0.105 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **165.627 ms**  self **0.020 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **165.582 ms**  self **0.003 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **165.579 ms**  self **0.284 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **165.213 ms**  self **5.470 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **47.539 ms**  self **5.413 ms**  `model_patcher.py:945`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **7.153 ms**  self **1.782 ms**  `model_patcher.py:1842`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **4.934 ms**  self **0.013 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **4.843 ms**  self **0.101 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **4.430 ms**  self **4.428 ms**  `__init__.py:350`
                  - `Module.named_buffers` 
                    wall **3.706 ms**  self **0.004 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **3.703 ms**  self **0.578 ms**  `module.py:2650`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.243 ms**  self **0.021 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.127 ms**  self **0.247 ms**  `model_patcher.py:899`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.111 ms**  self **0.010 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.036 ms**  self **0.111 ms**  `model_patcher.py:899`
  - `_vae_load_with_worker_stage` 
    wall **160.610 ms**  self **0.012 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **160.588 ms**  self **0.372 ms**  `golden_serial.py:14229`
      - `VAE.__init__` 
        wall **151.915 ms**  self **76.194 ms**  `sd.py:487`
        - `Module.load_state_dict` 
          wall **40.311 ms**  self **0.697 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **39.613 ms**  self **0.036 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **24.381 ms**  self **0.042 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **18.750 ms**  self **0.034 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **5.184 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.614 ms**  self **0.027 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.556 ms**  self **0.038 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.543 ms**  self **0.036 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.400 ms**  self **0.039 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.680 ms**  self **0.018 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.571 ms**  self **0.027 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.732 ms**  self **0.036 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.478 ms**  self **0.046 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.249 ms**  self **0.041 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.338 ms**  self **0.022 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.807 ms**  self **0.023 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.290 ms**  self **0.039 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.228 ms**  self **0.039 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.186 ms**  self **0.037 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.140 ms**  self **0.023 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.789 ms**  self **0.027 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.541 ms**  self **0.037 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.092 ms**  self **0.036 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.026 ms**  self **0.042 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **4.481 ms**  self **0.024 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.732 ms**  self **0.044 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.401 ms**  self **0.035 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.221 ms**  self **0.037 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **14.306 ms**  self **0.034 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **10.075 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.004 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.556 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.283 ms**  self **0.052 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.534 ms**  self **0.949 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.195 ms**  self **0.032 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.251 ms**  self **0.017 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.008 ms**  self **0.013 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.160 ms**  self **0.038 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.245 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.127 ms**  self **0.020 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.097 ms**  self **0.040 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.280 ms**  self **0.014 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.070 ms**  self **0.010 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **3.358 ms**  self **0.024 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.635 ms**  self **0.045 ms**  `module.py:2589`
        - `archive_model_dtypes` 
          wall **16.482 ms**  self **1.733 ms**  `model_management.py:1045`
        - `VAE.model_size` 
          wall **10.122 ms**  self **0.865 ms**  `sd.py:1095`
          - `module_size` 
            wall **9.256 ms**  self **0.196 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **9.060 ms**  self **0.027 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **5.754 ms**  self **0.027 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **4.308 ms**  self **0.026 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.890 ms**  self **0.013 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.659 ms**  self **0.011 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.488 ms**  self **0.035 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.064 ms**  self **0.009 ms**  `module.py:2199`
                          - `Module._save_to_state_dict` 
                            wall **1.055 ms**  self **1.055 ms**  `module.py:2148`
                  - `Module.state_dict` 
                    wall **1.618 ms**  self **0.015 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.517 ms**  self **0.015 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.017 ms**  self **0.031 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.055 ms**  self **0.017 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **3.264 ms**  self **0.023 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **2.505 ms**  self **0.021 ms**  `module.py:2199`
        - `Module.to` 
          wall **5.677 ms**  self **0.308 ms**  `module.py:1259`
          - `Module._apply` 
            wall **5.369 ms**  self **0.018 ms**  `module.py:930`
            - `Module._apply` 
              wall **2.921 ms**  self **0.012 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.218 ms**  self **0.009 ms**  `module.py:930`
            - `Module._apply` 
              wall **2.408 ms**  self **0.021 ms**  `module.py:930`
              - `Module._apply` 
                wall **1.619 ms**  self **0.010 ms**  `module.py:930`
        - `Module.eval` 
          wall **2.676 ms**  self **0.003 ms**  `module.py:2916`
          - `Module.train` 
            wall **2.674 ms**  self **0.011 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.449 ms**  self **0.006 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.168 ms**  self **0.006 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.184 ms**  self **0.010 ms**  `module.py:2894`
      - `validate_qd_adoption` 
        wall **5.361 ms**  self **2.258 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **1.106 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.104 ms**  self **0.198 ms**  `module.py:2650`
  - `RK_NoiseSampler.set_sde_step` 
    wall **89.891 ms**  self **0.909 ms**  `rk_noise_sampler_beta.py:216`
    - `RK_NoiseSampler.get_sde_step` 
      wall **66.547 ms**  self **13.970 ms**  `rk_noise_sampler_beta.py:318`
      - `RK_NoiseSampler.get_sde_coeff` 
        wall **52.577 ms**  self **1.112 ms**  `rk_noise_sampler_beta.py:180`
        - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
          wall **51.056 ms**  self **51.056 ms**  `_tensor.py:32`
    - `RK_Method_Exponential.h_fn` 
      wall **15.247 ms**  self **15.247 ms**  `rk_method_beta.py:882`
    - `RK_NoiseSampler.get_sde_step` 
      wall **6.775 ms**  self **0.804 ms**  `rk_noise_sampler_beta.py:318`
      - `RK_NoiseSampler.get_sde_coeff` 
        wall **5.970 ms**  self **4.816 ms**  `rk_noise_sampler_beta.py:180`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **34.408 ms**  self **34.408 ms**  `rk_noise_sampler_beta.py:785`
  - `generate_init_noise` 
    wall **19.794 ms**  self **2.558 ms**  `samplers.py:61`
    - `GaussianNoiseGenerator.__call__` 
      wall **15.414 ms**  self **15.410 ms**  `noise_classes.py:386`
    - `normalize_zscore` 
      wall **1.173 ms**  self **1.173 ms**  `latents.py:246`
  _... 21 more children >= 1 ms omitted_

### `golden_sampling`

- Stage wall: **5,804.560 ms**

- `golden_sampling` 
  wall **5,804.560 ms**  self **5,804.560 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **5,804.500 ms**  self **0.345 ms**  `golden_serial.py:13704`
    - `GoldenSerialRunner.run_closure` 
      wall **5,594.385 ms**  self **0.054 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **5,594.016 ms**  self **0.073 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **5,592.908 ms**  self **0.092 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **5,592.644 ms**  self **0.316 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **5,587.699 ms**  self **26.065 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **5,222.189 ms**  self **0.066 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **5,221.955 ms**  self **0.007 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **5,221.947 ms**  self **0.065 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **5,221.509 ms**  self **0.006 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **5,221.497 ms**  self **0.011 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **5,221.486 ms**  self **1.623 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **5,052.122 ms**  self **0.300 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **5,051.463 ms**  self **0.014 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **5,051.448 ms**  self **0.120 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **5,050.515 ms**  self **0.302 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **5,050.158 ms**  self **71.731 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **761.055 ms**  self **0.551 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **759.896 ms**  self **0.572 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **758.857 ms**  self **0.013 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **758.845 ms**  self **0.009 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **758.836 ms**  self **0.020 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **758.800 ms**  self **0.010 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **758.790 ms**  self **0.024 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **758.766 ms**  self **0.028 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **747.076 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **747.071 ms**  self **0.008 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **747.057 ms**  self **0.195 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **746.861 ms**  self **2.279 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **740.976 ms**  self **0.019 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **740.944 ms**  self **0.077 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **740.868 ms**  self **1.144 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **738.624 ms**  self **0.010 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **738.614 ms**  self **0.032 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **738.582 ms**  self **738.582 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **11.662 ms**  self **0.217 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **11.445 ms**  self **11.058 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **384.029 ms**  self **0.439 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **383.553 ms**  self **0.101 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **383.437 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **383.428 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **383.421 ms**  self **0.012 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **383.399 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **383.394 ms**  self **0.021 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **383.373 ms**  self **0.024 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **382.854 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **382.850 ms**  self **0.016 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **382.828 ms**  self **0.111 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **382.716 ms**  self **0.684 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **380.551 ms**  self **0.013 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **380.530 ms**  self **0.144 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **380.386 ms**  self **0.205 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **379.645 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **379.638 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **379.625 ms**  self **379.625 ms**  `nodes.py:215`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **360.358 ms**  self **0.235 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **360.088 ms**  self **0.065 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **360.008 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **359.999 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **359.994 ms**  self **0.011 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **359.974 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **359.969 ms**  self **0.021 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **359.948 ms**  self **0.022 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **359.457 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **359.452 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **359.441 ms**  self **0.132 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **359.309 ms**  self **0.801 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **356.245 ms**  self **0.016 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **356.213 ms**  self **0.059 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **356.154 ms**  self **0.242 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **355.311 ms**  self **0.011 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **355.300 ms**  self **0.024 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **355.276 ms**  self **355.276 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.551 ms**  self **0.049 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.425 ms**  self **0.024 ms**  `model_management.py:1748`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **358.122 ms**  self **0.134 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **357.961 ms**  self **0.084 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **357.861 ms**  self **0.013 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **357.848 ms**  self **0.007 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **357.842 ms**  self **0.016 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **357.812 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **357.807 ms**  self **0.020 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **357.787 ms**  self **0.019 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **356.396 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **356.391 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **356.379 ms**  self **0.038 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **356.341 ms**  self **0.398 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **353.728 ms**  self **0.015 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **353.704 ms**  self **0.017 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **353.686 ms**  self **0.146 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **353.071 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **353.063 ms**  self **0.016 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **353.047 ms**  self **353.047 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.478 ms**  self **0.048 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.347 ms**  self **0.029 ms**  `model_management.py:1748`
                                                    - `cfg_function` 
                                                      wall **1.372 ms**  self **0.046 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **1.326 ms**  self **1.326 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **348.599 ms**  self **0.138 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **348.439 ms**  self **0.083 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **348.341 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **348.331 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **348.325 ms**  self **0.018 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **348.293 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **348.288 ms**  self **0.020 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **348.268 ms**  self **0.019 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **348.100 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **348.096 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **348.085 ms**  self **0.031 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **348.054 ms**  self **0.650 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **342.051 ms**  self **0.015 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **342.025 ms**  self **0.018 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **342.007 ms**  self **0.173 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **341.365 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **341.356 ms**  self **0.021 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **341.335 ms**  self **341.335 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **4.604 ms**  self **0.052 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **4.465 ms**  self **0.029 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **3.941 ms**  self **3.931 ms**  `memory.py:847`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **347.346 ms**  self **0.407 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **346.892 ms**  self **0.231 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **346.605 ms**  self **0.014 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **346.590 ms**  self **0.008 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **346.582 ms**  self **0.021 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **346.541 ms**  self **0.008 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **346.533 ms**  self **0.026 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **346.507 ms**  self **0.028 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **344.123 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **344.118 ms**  self **0.009 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **344.102 ms**  self **0.125 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **343.977 ms**  self **1.218 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **340.809 ms**  self **0.014 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **340.785 ms**  self **0.087 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **340.699 ms**  self **0.272 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **339.797 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **339.788 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **339.773 ms**  self **339.773 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.066 ms**  self **0.028 ms**  `model_patcher.py:417`
                                                    - `cfg_function` 
                                                      wall **2.356 ms**  self **0.203 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **2.153 ms**  self **1.858 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **338.570 ms**  self **0.168 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **338.368 ms**  self **0.069 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **338.285 ms**  self **0.011 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **338.273 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **338.267 ms**  self **0.019 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **338.234 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **338.228 ms**  self **0.025 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **338.203 ms**  self **0.022 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **327.149 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **327.145 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **327.133 ms**  self **0.037 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **327.096 ms**  self **0.463 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **323.902 ms**  self **0.020 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **323.868 ms**  self **0.020 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **323.848 ms**  self **0.189 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **323.141 ms**  self **0.010 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **323.130 ms**  self **0.021 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **323.109 ms**  self **323.109 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.483 ms**  self **0.022 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.459 ms**  self **1.459 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **11.033 ms**  self **0.112 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **10.920 ms**  self **10.532 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **337.495 ms**  self **0.651 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **336.809 ms**  self **0.123 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **336.666 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **336.656 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **336.650 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **336.625 ms**  self **0.007 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **336.619 ms**  self **0.022 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **336.597 ms**  self **0.025 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **335.819 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **335.814 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **335.801 ms**  self **0.088 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **335.714 ms**  self **1.064 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **332.713 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **332.693 ms**  self **0.066 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **332.627 ms**  self **0.315 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **331.508 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **331.500 ms**  self **0.014 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **331.485 ms**  self **331.485 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.212 ms**  self **0.044 ms**  `model_patcher.py:417`
                                    _... 54 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **11.829 ms**  self **0.017 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **11.805 ms**  self **0.053 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **2.600 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.594 ms**  self **0.073 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **2.475 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **2.458 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **2.447 ms**  self **0.005 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **2.442 ms**  self **2.441 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **2.229 ms**  self **0.009 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.219 ms**  self **0.136 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **2.002 ms**  self **0.006 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.959 ms**  self **0.015 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.914 ms**  self **0.015 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.899 ms**  self **1.896 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **2.149 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.143 ms**  self **0.063 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **2.048 ms**  self **0.005 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **2.021 ms**  self **0.008 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **2.006 ms**  self **0.006 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **2.000 ms**  self **1.999 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **2.031 ms**  self **0.007 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.022 ms**  self **0.110 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.858 ms**  self **0.005 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.830 ms**  self **0.011 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.810 ms**  self **0.010 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.800 ms**  self **1.799 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.840 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.833 ms**  self **0.083 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.706 ms**  self **0.005 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.678 ms**  self **0.009 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.659 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.652 ms**  self **1.651 ms**  `storage.py:262`
              - `_disable_dynamo.<locals>.inner` 
                wall **2.564 ms**  self **0.006 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **2.558 ms**  self **0.008 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **2.548 ms**  self **0.003 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **2.546 ms**  self **0.043 ms**  `random.py:62`
                      - `manual_seed_all` 
                        wall **1.771 ms**  self **0.005 ms**  `random.py:97`
                        - `_lazy_call` 
                          wall **1.766 ms**  self **0.012 ms**  `__init__.py:319`
                          - `format_stack` 
                            wall **1.745 ms**  self **0.014 ms**  `traceback.py:213`
                            - `extract_stack` 
                              wall **1.494 ms**  self **0.008 ms**  `traceback.py:220`
                              - `StackSummary.extract` 
                                wall **1.486 ms**  self **0.007 ms**  `traceback.py:375`
                                - `StackSummary._extract_from_extended_frame_gen` 
                                  wall **1.480 ms**  self **0.176 ms**  `traceback.py:397`
              - `BaseModel.process_latent_out` 
                wall **2.086 ms**  self **0.005 ms**  `model_base.py:378`
                - `Flux.process_out` 
                  wall **2.081 ms**  self **2.081 ms**  `latent_formats.py:193`
    - `import_module` 
      wall **179.745 ms**  self **179.745 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **20.299 ms**  self **0.030 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **20.269 ms**  self **0.004 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **20.264 ms**  self **0.039 ms**  `copy.py:201`
          - `deepcopy` 
            wall **9.682 ms**  self **0.003 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **9.679 ms**  self **0.008 ms**  `copy.py:227`
              - `deepcopy` 
                wall **9.660 ms**  self **0.003 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **9.655 ms**  self **0.045 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **9.508 ms**  self **0.003 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **9.504 ms**  self **0.009 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **8.972 ms**  self **0.003 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **8.968 ms**  self **0.193 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **4.922 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **4.918 ms**  self **1.175 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **2.730 ms**  self **0.003 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **2.727 ms**  self **0.251 ms**  `copy.py:227`
          - `deepcopy` 
            wall **6.897 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **6.894 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **6.877 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **6.874 ms**  self **0.043 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **6.729 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **6.727 ms**  self **0.007 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **6.193 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **6.190 ms**  self **0.182 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **3.618 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **3.615 ms**  self **0.891 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.381 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.379 ms**  self **0.151 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **2.626 ms**  self **0.070 ms**  `golden_serial.py:9742`
      - `GoldenTelemetryRecorder.event` 
        wall **1.539 ms**  self **0.012 ms**  `golden_serial.py:1672`
        - `GoldenTelemetryRecorder.event_at` 
          wall **1.527 ms**  self **0.011 ms**  `golden_serial.py:1675`
          - `deepcopy` 
            wall **1.516 ms**  self **0.014 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **1.501 ms**  self **0.008 ms**  `copy.py:227`
              - `deepcopy` 
                wall **1.485 ms**  self **0.005 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **1.479 ms**  self **0.027 ms**  `copy.py:227`
      - `_build_golden_sampling_decomposition` 
        wall **1.015 ms**  self **0.109 ms**  `golden_serial.py:9370`
  - `BaseEventLoop.run_until_complete` 
    wall **1,075.323 ms**  self **0.018 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **1,075.291 ms**  self **0.063 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **165.468 ms**  self **4.624 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **160.698 ms**  self **160.677 ms**  `events.py:78`
      - `BaseEventLoop._run_once` 
        wall **2.555 ms**  self **0.018 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **2.481 ms**  self **2.481 ms**  `events.py:78`
  - `Thread.run` 
    wall **1,074.630 ms**  self **0.015 ms**  `threading.py:964`
    - `_worker` 
      wall **1,074.616 ms**  self **167.172 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **1,070.325 ms**  self **163.257 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **907.429 ms**  self **0.023 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **907.068 ms**  self **0.040 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **907.029 ms**  self **0.025 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **907.003 ms**  self **0.017 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **906.986 ms**  self **0.514 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **640.053 ms**  self **0.240 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **586.296 ms**  self **0.158 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **250.520 ms**  self **250.520 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **250.303 ms**  self **250.303 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **84.451 ms**  self **84.420 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **23.822 ms**  self **0.022 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **23.288 ms**  self **23.257 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **15.766 ms**  self **0.014 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **15.538 ms**  self **15.506 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **7.442 ms**  self **0.028 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **6.815 ms**  self **6.782 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.plan_once` 
                  wall **4.506 ms**  self **0.398 ms**  `golden_source_threads.py:910`
                  - `SourceThreadProcess._read_message` 
                    wall **2.941 ms**  self **2.909 ms**  `golden_source_threads.py:892`
              - `GoldenModelTransport.inspect` 
                wall **179.061 ms**  self **0.045 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **178.613 ms**  self **177.751 ms**  `golden_model_transport.py:304`
              - `GoldenModelTransport._views` 
                wall **62.211 ms**  self **62.211 ms**  `golden_model_transport.py:1910`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **17.456 ms**  self **0.058 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **16.983 ms**  self **0.012 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **16.961 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **16.948 ms**  self **0.006 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **16.939 ms**  self **16.934 ms**  `threading.py:288`
              - `GpuDestinationPool.acquire` 
                wall **4.917 ms**  self **0.049 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **4.850 ms**  self **4.658 ms**  `golden_model_transport.py:156`
    - `BaseEventLoop._run_once` 
      wall **907.068 ms**  self **0.023 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **906.721 ms**  self **906.718 ms**  `selectors.py:451`
    - `sample_custom` 
      wall **278.367 ms**  self **2.760 ms**  `sample.py:86`
      - `sample` 
        wall **275.599 ms**  self **0.032 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **275.259 ms**  self **0.115 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **274.905 ms**  self **0.017 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **274.888 ms**  self **0.098 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **273.919 ms**  self **0.009 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **273.902 ms**  self **0.033 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **273.869 ms**  self **1.954 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **206.255 ms**  self **0.009 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **206.241 ms**  self **0.008 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **206.233 ms**  self **0.035 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **206.080 ms**  self **0.123 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **201.329 ms**  self **0.023 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **201.279 ms**  self **0.003 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **201.275 ms**  self **0.269 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **200.927 ms**  self **6.861 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **56.175 ms**  self **8.742 ms**  `model_patcher.py:945`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **2.854 ms**  self **0.045 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **2.707 ms**  self **0.030 ms**  `model_patcher.py:899`
                                        - `cast_to_device` 
                                          wall **2.475 ms**  self **0.002 ms**  `model_management.py:1555`
                                          - `cast_to` 
                                            wall **2.464 ms**  self **2.464 ms**  `model_management.py:1527`
                                    - `Module.named_buffers` 
                                      wall **2.790 ms**  self **0.004 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **2.786 ms**  self **0.499 ms**  `module.py:2650`
                            - `free_memory` 
                              wall **2.614 ms**  self **0.075 ms**  `model_management.py:863`
                              - `get_free_memory` 
                                wall **2.406 ms**  self **0.041 ms**  `model_management.py:1748`
                                - `mem_get_info` 
                                  wall **1.858 ms**  self **1.842 ms**  `memory.py:847`
                            - `get_free_memory` 
                              wall **1.767 ms**  self **0.046 ms**  `model_management.py:1748`
                              - `mem_get_info` 
                                wall **1.244 ms**  self **1.232 ms**  `memory.py:847`
                    - `CFGGuider.inner_sample` 
                      wall **65.414 ms**  self **62.649 ms**  `samplers.py:1220`
                      - `WrapperExecutor.execute` 
                        wall **1.910 ms**  self **0.018 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.892 ms**  self **0.145 ms**  `samplers.py:983`
    - `prepare_sampling` 
      wall **167.546 ms**  self **0.008 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **167.531 ms**  self **0.004 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **167.527 ms**  self **0.020 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **167.416 ms**  self **0.105 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **165.627 ms**  self **0.020 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **165.582 ms**  self **0.003 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **165.579 ms**  self **0.284 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **165.213 ms**  self **5.470 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **47.539 ms**  self **5.413 ms**  `model_patcher.py:945`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **7.153 ms**  self **1.782 ms**  `model_patcher.py:1842`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **4.934 ms**  self **0.013 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **4.843 ms**  self **0.101 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **4.430 ms**  self **4.428 ms**  `__init__.py:350`
                    - `Module.named_buffers` 
                      wall **3.706 ms**  self **0.004 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **3.703 ms**  self **0.578 ms**  `module.py:2650`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.243 ms**  self **0.021 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.127 ms**  self **0.247 ms**  `model_patcher.py:899`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.111 ms**  self **0.010 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.036 ms**  self **0.111 ms**  `model_patcher.py:899`
    - `_vae_load_with_worker_stage` 
      wall **160.610 ms**  self **0.012 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **160.588 ms**  self **0.372 ms**  `golden_serial.py:14229`
        - `VAE.__init__` 
          wall **151.915 ms**  self **76.194 ms**  `sd.py:487`
          - `Module.load_state_dict` 
            wall **40.311 ms**  self **0.697 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **39.613 ms**  self **0.036 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **24.381 ms**  self **0.042 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **18.750 ms**  self **0.034 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **5.184 ms**  self **0.025 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **4.614 ms**  self **0.027 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.556 ms**  self **0.038 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.543 ms**  self **0.036 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.400 ms**  self **0.039 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.680 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **4.571 ms**  self **0.027 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.732 ms**  self **0.036 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.478 ms**  self **0.046 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.249 ms**  self **0.041 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.338 ms**  self **0.022 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.807 ms**  self **0.023 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.290 ms**  self **0.039 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.228 ms**  self **0.039 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.186 ms**  self **0.037 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.140 ms**  self **0.023 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.789 ms**  self **0.027 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.541 ms**  self **0.037 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.092 ms**  self **0.036 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.026 ms**  self **0.042 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.481 ms**  self **0.024 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.732 ms**  self **0.044 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.401 ms**  self **0.035 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.221 ms**  self **0.037 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **14.306 ms**  self **0.034 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **10.075 ms**  self **0.028 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.004 ms**  self **0.020 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.556 ms**  self **0.018 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **2.283 ms**  self **0.052 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **1.534 ms**  self **0.949 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.195 ms**  self **0.032 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.251 ms**  self **0.017 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.008 ms**  self **0.013 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.160 ms**  self **0.038 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.245 ms**  self **0.020 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.127 ms**  self **0.020 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.097 ms**  self **0.040 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.280 ms**  self **0.014 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.070 ms**  self **0.010 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.358 ms**  self **0.024 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.635 ms**  self **0.045 ms**  `module.py:2589`
          - `archive_model_dtypes` 
            wall **16.482 ms**  self **1.733 ms**  `model_management.py:1045`
          - `VAE.model_size` 
            wall **10.122 ms**  self **0.865 ms**  `sd.py:1095`
            - `module_size` 
              wall **9.256 ms**  self **0.196 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **9.060 ms**  self **0.027 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **5.754 ms**  self **0.027 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **4.308 ms**  self **0.026 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.890 ms**  self **0.013 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.659 ms**  self **0.011 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.488 ms**  self **0.035 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.064 ms**  self **0.009 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **1.055 ms**  self **1.055 ms**  `module.py:2148`
                    - `Module.state_dict` 
                      wall **1.618 ms**  self **0.015 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.517 ms**  self **0.015 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.017 ms**  self **0.031 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.055 ms**  self **0.017 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **3.264 ms**  self **0.023 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **2.505 ms**  self **0.021 ms**  `module.py:2199`
          - `Module.to` 
            wall **5.677 ms**  self **0.308 ms**  `module.py:1259`
            - `Module._apply` 
              wall **5.369 ms**  self **0.018 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.921 ms**  self **0.012 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.218 ms**  self **0.009 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.408 ms**  self **0.021 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.619 ms**  self **0.010 ms**  `module.py:930`
          - `Module.eval` 
            wall **2.676 ms**  self **0.003 ms**  `module.py:2916`
            - `Module.train` 
              wall **2.674 ms**  self **0.011 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.449 ms**  self **0.006 ms**  `module.py:2894`
                - `Module.train` 
                  wall **1.168 ms**  self **0.006 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.184 ms**  self **0.010 ms**  `module.py:2894`
        - `validate_qd_adoption` 
          wall **5.361 ms**  self **2.258 ms**  `golden_serial.py:12922`
          - `Module.named_buffers` 
            wall **1.106 ms**  self **0.002 ms**  `module.py:2754`
            - `Module._named_members` 
              wall **1.104 ms**  self **0.198 ms**  `module.py:2650`
    - `RK_NoiseSampler.set_sde_step` 
      wall **89.891 ms**  self **0.909 ms**  `rk_noise_sampler_beta.py:216`
      - `RK_NoiseSampler.get_sde_step` 
        wall **66.547 ms**  self **13.970 ms**  `rk_noise_sampler_beta.py:318`
        - `RK_NoiseSampler.get_sde_coeff` 
          wall **52.577 ms**  self **1.112 ms**  `rk_noise_sampler_beta.py:180`
          - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
            wall **51.056 ms**  self **51.056 ms**  `_tensor.py:32`
      - `RK_Method_Exponential.h_fn` 
        wall **15.247 ms**  self **15.247 ms**  `rk_method_beta.py:882`
      - `RK_NoiseSampler.get_sde_step` 
        wall **6.775 ms**  self **0.804 ms**  `rk_noise_sampler_beta.py:318`
        - `RK_NoiseSampler.get_sde_coeff` 
          wall **5.970 ms**  self **4.816 ms**  `rk_noise_sampler_beta.py:180`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **34.408 ms**  self **34.408 ms**  `rk_noise_sampler_beta.py:785`
    - `generate_init_noise` 
      wall **19.794 ms**  self **2.558 ms**  `samplers.py:61`
      - `GaussianNoiseGenerator.__call__` 
        wall **15.414 ms**  self **15.410 ms**  `noise_classes.py:386`
      - `normalize_zscore` 
        wall **1.173 ms**  self **1.173 ms**  `latents.py:246`
    _... 21 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **160.639 ms**  self **0.009 ms**  `golden_serial.py:15533`
  - `_overlap_stage_call` 
    wall **2.468 ms**  self **0.009 ms**  `golden_serial.py:15533`
  - `BaseSelectorEventLoop._make_self_pipe` 
    wall **1.196 ms**  self **0.608 ms**  `selector_events.py:105`

### `golden_sampler_tail`

- Stage wall: **0.096 ms**

_Nothing below the stage body reached the threshold._

### `golden_vae_decode`

- Stage wall: **1,591.067 ms**

- `golden_vae_decode` 
  wall **1,591.067 ms**  self **0.316 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **1,591.046 ms**  self **0.078 ms**  `golden_serial.py:14442`
    - `GoldenSerialRunner.run_closure` 
      wall **1,590.562 ms**  self **0.041 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **1,590.454 ms**  self **0.055 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **1,590.069 ms**  self **0.030 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **1,589.852 ms**  self **0.031 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **1,589.821 ms**  self **1,468.457 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **112.576 ms**  self **0.136 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **102.199 ms**  self **0.025 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **102.137 ms**  self **0.003 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **102.133 ms**  self **0.090 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **102.003 ms**  self **2.288 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **18.022 ms**  self **1.706 ms**  `model_patcher.py:945`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **3.108 ms**  self **0.074 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **2.918 ms**  self **0.292 ms**  `model_patcher.py:899`
                            - `namedtuple` 
                              wall **2.297 ms**  self **2.295 ms**  `__init__.py:350`
                        - `Module.named_buffers` 
                          wall **1.680 ms**  self **0.005 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.675 ms**  self **0.480 ms**  `module.py:2650`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.239 ms**  self **0.083 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.034 ms**  self **0.235 ms**  `model_patcher.py:899`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.079 ms**  self **0.048 ms**  `model_patcher.py:1947`
                - `LoadedModel.model_memory_required` 
                  wall **6.778 ms**  self **0.005 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **6.770 ms**  self **0.003 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **6.767 ms**  self **0.591 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **6.176 ms**  self **0.210 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **5.966 ms**  self **0.036 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **3.213 ms**  self **0.027 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.399 ms**  self **0.026 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.702 ms**  self **0.026 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.133 ms**  self **0.021 ms**  `module.py:2199`
                - `free_memory` 
                  wall **1.995 ms**  self **0.122 ms**  `model_management.py:863`
                - `get_free_memory` 
                  wall **1.294 ms**  self **0.028 ms**  `model_management.py:1748`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **7.467 ms**  self **7.467 ms**  `sd.py:506`
              - `ModelPatcher.get_free_memory` 
                wall **1.236 ms**  self **0.052 ms**  `model_patcher.py:417`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **1,590.605 ms**  self **1,590.605 ms**  `full_execution_trace.py:330`

### `golden_output`

- Stage wall: **301.508 ms**

- `golden_output` 
  wall **301.508 ms**  self **301.508 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **301.429 ms**  self **13.326 ms**  `golden_serial.py:14589`
    - `Image.save` 
      wall **240.861 ms**  self **0.077 ms**  `Image.py:2592`
      - `_save` 
        wall **226.339 ms**  self **0.083 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **226.218 ms**  self **0.026 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **226.186 ms**  self **220.722 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **14.332 ms**  self **14.332 ms**  `Image.py:429`
    - `fromarray` 
      wall **36.964 ms**  self **32.280 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **4.685 ms**  self **0.017 ms**  `Image.py:3288`
        - `frombytes` 
          wall **4.657 ms**  self **0.028 ms**  `Image.py:3242`
          - `new` 
            wall **3.610 ms**  self **3.560 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.014 ms**  self **0.975 ms**  `Image.py:925`
    - `clip` 
      wall **6.945 ms**  self **0.013 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **6.933 ms**  self **0.031 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **6.901 ms**  self **6.901 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **1.800 ms**  self **0.015 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **1.785 ms**  self **1.785 ms**  `output_durability.py:73`
