# Golden stage decision report

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **877,779**

Tree floor: **1 ms**   Function rollup floor: **1 ms** total inclusive

## 1. Critical path and stage overlap

Sum of stage walls: **13,053.162 ms**   Timeline union: **10,085.543 ms**   Span: **10,094.393 ms**

Sum exceeds the union by **2,967.619 ms** -- that gap is the overlap the schedule is buying.

| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |
|:--|---:|---:|---:|:--|:--|
| `golden_restore` | 0.4 | 0.0 | 0.4 | 0.0% | `#` |
| `golden_request_setup` | 1.7 | 0.0 | 1.7 | 0.0% | `#` |
| `golden_clip_load` | 1,734.0 | 1,731.2 | 2.8 | 99.8% | `############` |
| `golden_clip_forward` | 3,061.9 | 646.0 | 2,415.8 | 21.1% | `            ######################` |
| `golden_unet_load` | 2,414.2 | 0.0 | 2,414.2 | 0.0% | `            #################` |
| `golden_sampler_prepare` | 56.0 | 55.5 | 0.5 | 99.2% | `                                  #` |
| `golden_vae_load` | 554.8 | 0.0 | 554.8 | 0.0% | `                                   ####` |
| `golden_sampling` | 4,267.4 | 3,709.7 | 557.7 | 86.9% | `                                   ##############################` |
| `golden_sampler_tail` | 0.0 | 0.0 | 0.0 | 0.0% | `                                                                 #` |
| `golden_vae_decode` | 719.1 | 711.7 | 7.4 | 99.0% | `                                                                 #####` |
| `golden_output` | 243.6 | 242.3 | 1.4 | 99.4% | `                                                                      ##` |

_Uncontended_ is the time during a stage when no other stage was running. That portion is protected: nothing else could absorb it. Overlapped time may be hidden by a longer sibling, so reducing it may not move root wall.

## 2. Function rollup across the whole request

`total incl ms` sums each call's wall, so a function called 24 times at 3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall contains its callees, so **totals are not additive down a call tree** -- `total self ms` is the non-overlapping part.

| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |
|---:|---:|---:|---:|---:|:--|:--|:--|
| 19,257.974 | 59 | 326.406 | 3,967.350 | 1.922 | `WrapperExecutor.execute` | `patcher_extension.py:108` | 2 |
| 11,407.133 | 526 | 21.687 | 2,823.208 | 1.333 | `Module._wrapped_call_impl` | `module.py:1779` | 3 |
| 11,405.826 | 526 | 21.684 | 2,823.197 | 2.764 | `Module._call_impl` | `module.py:1787` | 3 |
| 8,050.897 | 32 | 251.591 | 4,219.909 | 0.984 | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` | 6 |
| 8,046.020 | 5 | 1,609.204 | 4,220.136 | 0.163 | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` | 5 |
| 8,033.502 | 32 | 251.047 | 4,218.983 | 1.332 | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` | 6 |
| 4,432.158 | 3 | 1,477.386 | 2,348.821 | 0.040 | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` | 3 |
| 4,432.117 | 3 | 1,477.372 | 2,348.816 | 0.198 | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` | 3 |
| 4,431.918 | 3 | 1,477.306 | 2,348.716 | 1.554 | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` | 3 |
| 4,267.373 | 1 | 4,267.373 | 4,267.373 | 0.286 | `golden_sampling` | `golden_serial.py:13785` | 1 |
| 4,218.801 | 1 | 4,218.801 | 4,218.801 | 0.444 | `ClownsharKSampler_Beta.main` | `samplers.py:1745` | 1 |
| 4,215.273 | 1 | 4,215.273 | 4,215.273 | 22.657 | `SharkSampler.main` | `samplers.py:153` | 1 |
| 4,139.218 | 2 | 2,069.609 | 3,967.539 | 0.121 | `CFGGuider.sample` | `samplers.py:1276` | 2 |
| 4,138.751 | 2 | 2,069.376 | 3,967.343 | 0.115 | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` | 2 |
| 4,137.737 | 2 | 2,068.869 | 3,967.048 | 0.010 | `WrapperExecutor.__call__` | `patcher_extension.py:103` | 2 |
| 4,137.673 | 2 | 2,068.836 | 3,967.016 | 2.912 | `CFGGuider.outer_sample` | `samplers.py:1240` | 2 |
| 4,134.169 | 3 | 1,378.056 | 2,262.136 | 9.957 | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` | 3 |
| 3,841.428 | 2 | 1,920.714 | 3,791.834 | 48.543 | `CFGGuider.inner_sample` | `samplers.py:1220` | 2 |
| 3,828.754 | 309 | 12.391 | 302.359 | 4.820 | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` | 3 |
| 3,790.397 | 2 | 1,895.199 | 3,789.289 | 0.569 | `KSAMPLER.sample` | `samplers.py:983` | 2 |
| 3,789.270 | 74 | 51.206 | 3,787.387 | 1.790 | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` | 2 |
| 3,786.356 | 2 | 1,893.178 | 3,786.354 | 47.739 | `sample_rk_beta` | `rk_sampler_beta.py:110` | 2 |
| 3,532.558 | 313 | 11.286 | 250.183 | 3,524.292 | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` | 3 |
| 3,380.485 | 3 | 1,126.828 | 2,349.100 | 8.175 | `_WorkItem.run` | `thread.py:53` | 3 |
| 3,260.890 | 17 | 191.817 | 487.311 | 3.818 | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` | 1 |
| 3,256.224 | 17 | 191.543 | 486.081 | 1.532 | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` | 1 |
| 3,254.104 | 17 | 191.418 | 485.413 | 0.098 | `KSamplerX0Inpaint.__call__` | `samplers.py:634` | 1 |
| 3,254.009 | 17 | 191.412 | 485.404 | 0.072 | `CFGGuider.__call__` | `samplers.py:1207` | 1 |
| 3,253.937 | 17 | 191.408 | 485.396 | 0.174 | `CFGGuider.outer_predict_noise` | `samplers.py:1210` | 1 |
| 3,253.526 | 17 | 191.384 | 485.357 | 0.349 | `SharkGuider.predict_noise` | `samplers.py:99` | 1 |
| 3,253.175 | 17 | 191.363 | 485.334 | 0.382 | `sampling_function` | `samplers.py:609` | 1 |
| 3,061.809 | 1 | 3,061.809 | 3,061.809 | 0.260 | `golden_clip_forward` | `golden_serial.py:12452` | 1 |
| 3,050.072 | 1 | 3,050.072 | 3,050.072 | 0.022 | `CLIPTextEncode.encode` | `nodes.py:73` | 1 |
| 3,024.719 | 1 | 3,024.719 | 3,024.719 | 0.021 | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` | 1 |
| 3,024.698 | 1 | 3,024.698 | 3,024.698 | 0.038 | `CLIP.encode_from_tokens` | `sd.py:396` | 1 |
| 2,970.246 | 14 | 212.160 | 2,216.959 | 1.018 | `BaseEventLoop._run_once` | `base_events.py:1845` | 5 |
| 2,850.638 | 1 | 2,850.638 | 2,850.638 | 0.037 | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` | 1 |
| 2,850.601 | 1 | 2,850.601 | 2,850.601 | 27.347 | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` | 1 |
| 2,823.211 | 1 | 2,823.211 | 2,823.211 | 0.003 | `SDClipModel.encode` | `sd1_clip.py:305` | 1 |
| 2,823.170 | 1 | 2,823.170 | 2,823.170 | 0.074 | `SDClipModel.forward` | `sd1_clip.py:260` | 1 |
| 2,806.662 | 2 | 1,403.331 | 2,348.841 | 0.041 | `thread_traced.<locals>._run` | `full_execution_trace.py:276` | 2 |
| 2,687.752 | 1 | 2,687.752 | 2,687.752 | 0.009 | `BaseLlama.forward` | `llama.py:998` | 1 |
| 2,687.618 | 1 | 2,687.618 | 2,687.618 | 261.547 | `Llama2_.forward` | `llama.py:824` | 1 |
| 2,675.837 | 16 | 167.240 | 2,216.681 | 2,675.831 | `EpollSelector.select` | `selectors.py:451` | 5 |
| 2,217.288 | 1 | 2,217.288 | 2,217.288 | 0.116 | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` | 1 |
| 2,215.487 | 3 | 738.496 | 1,640.248 | 0.034 | `Thread.run` | `threading.py:964` | 2 |
| 2,195.743 | 2 | 1,097.871 | 1,640.235 | 1,164.336 | `_worker` | `thread.py:69` | 2 |
| 1,850.894 | 1 | 1,850.894 | 1,850.894 | 0.287 | `Llama2_.compute_freqs_cis` | `llama.py:815` | 1 |
| 1,850.607 | 1 | 1,850.607 | 1,850.607 | 201.031 | `precompute_freqs_cis` | `llama.py:445` | 1 |
| 1,843.572 | 17 | 108.445 | 475.477 | 0.055 | `calc_cond_batch` | `samplers.py:208` | 1 |
| 1,843.520 | 17 | 108.442 | 475.472 | 0.094 | `_calc_cond_batch_outer` | `samplers.py:214` | 1 |
| 1,842.168 | 17 | 108.363 | 475.305 | 7.889 | `_calc_cond_batch` | `samplers.py:221` | 1 |
| 1,801.351 | 17 | 105.962 | 471.904 | 0.151 | `BaseModel.apply_model` | `model_base.py:204` | 1 |
| 1,800.546 | 17 | 105.914 | 471.805 | 2.761 | `BaseModel._apply_model` | `model_base.py:211` | 1 |
| 1,787.818 | 17 | 105.166 | 470.158 | 1,787.818 | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` | 1 |
| 1,728.407 | 2 | 864.204 | 1,635.152 | 0.619 | `golden_clip_load` | `golden_serial.py:11497` | 1 |
| 1,625.644 | 1 | 1,625.644 | 1,625.644 | 1,625.644 | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` | 1 |
| 1,625.589 | 1 | 1,625.589 | 1,625.589 | 0.030 | `_read_golden_m2_clip` | `golden_serial.py:11462` | 1 |
| 1,625.555 | 1 | 1,625.555 | 1,625.555 | 0.018 | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` | 1 |
| 1,435.492 | 1017 | 1.411 | 1,362.983 | 65.445 | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` | 2 |

## 3. Per-stage call trees

Depth is uncapped; the wall floor limits it. Breadth is capped at 8 children plus any child at or above 10% of its parent.

### `golden_restore`

- Stage wall: **0.373 ms**

_Nothing below the stage body reached the threshold._

### `golden_request_setup`

- Stage wall: **1.742 ms**

- `golden_request_setup` 
  wall **1.742 ms**  self **1.742 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **1.717 ms**  self **0.074 ms**  `golden_serial.py:9977`

### `golden_clip_load`

- Stage wall: **1,734.025 ms**

- `golden_clip_load` 
  wall **1,734.025 ms**  self **16.036 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **1,640.248 ms**  self **0.013 ms**  `threading.py:964`
    - `_worker` 
      wall **1,640.235 ms**  self **1,066.991 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **573.232 ms**  self **8.147 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **565.063 ms**  self **0.163 ms**  `golden_serial.py:2341`
          - `load_text_encoder_state_dicts` 
            wall **518.444 ms**  self **0.161 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **517.836 ms**  self **0.254 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **428.669 ms**  self **0.015 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **428.654 ms**  self **0.255 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **428.400 ms**  self **2.795 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **425.604 ms**  self **0.116 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **406.341 ms**  self **0.929 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **400.987 ms**  self **6.336 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **394.214 ms**  self **239.758 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **117.358 ms**  self **13.235 ms**  `__init__.py:274`
                              - `loads` 
                                wall **104.123 ms**  self **0.006 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **104.117 ms**  self **0.015 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **104.102 ms**  self **104.102 ms**  `decoder.py:343`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **16.473 ms**  self **16.473 ms**  `tokenization_qwen2.py:174`
                            - `PreTrainedTokenizer.__init__` 
                              wall **14.762 ms**  self **0.918 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **13.057 ms**  self **5.637 ms**  `tokenization_utils.py:512`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **4.246 ms**  self **4.213 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **2.965 ms**  self **0.974 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **1.970 ms**  self **1.942 ms**  `tokenization_qwen2.py:215`
                            - `compile` 
                              wall **4.903 ms**  self **0.043 ms**  `_main.py:359`
                              - `_compile` 
                                wall **4.860 ms**  self **0.245 ms**  `_main.py:460`
                                - `Branch.pack_characters` 
                                  wall **2.377 ms**  self **0.003 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **2.374 ms**  self **0.008 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **2.333 ms**  self **0.014 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **2.227 ms**  self **0.029 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **2.161 ms**  self **0.005 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **2.156 ms**  self **2.156 ms**  `_regex_core.py:362`
                                - `_parse_pattern` 
                                  wall **1.267 ms**  self **0.020 ms**  `_regex_core.py:452`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **16.473 ms**  self **16.473 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **2.252 ms**  self **2.213 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **45.963 ms**  self **0.005 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **45.958 ms**  self **0.016 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **45.942 ms**  self **0.051 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **45.786 ms**  self **0.023 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **45.763 ms**  self **0.389 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **37.654 ms**  self **0.041 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **37.571 ms**  self **0.228 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **28.671 ms**  self **0.171 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **1.751 ms**  self **0.055 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.080 ms**  self **0.189 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **1.723 ms**  self **0.008 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.454 ms**  self **0.020 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **1.453 ms**  self **0.022 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.412 ms**  self **0.019 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.233 ms**  self **0.034 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.175 ms**  self **0.013 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.114 ms**  self **0.022 ms**  `llama.py:654`
                            - `disable_weight_init.Embedding.__init__` 
                              wall **8.382 ms**  self **0.174 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **8.071 ms**  self **8.071 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **7.540 ms**  self **0.102 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **4.412 ms**  self **0.003 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **4.409 ms**  self **0.006 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **4.389 ms**  self **0.007 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **4.353 ms**  self **0.031 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **34.036 ms**  self **0.496 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **27.961 ms**  self **0.011 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **27.948 ms**  self **0.033 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **27.914 ms**  self **6.405 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **21.509 ms**  self **0.050 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **20.945 ms**  self **0.018 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **20.084 ms**  self **0.107 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.877 ms**  self **0.019 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.221 ms**  self **0.018 ms**  `module.py:2589`
                                - `Module.load_state_dict.<locals>.load` 
                                  wall **1.021 ms**  self **0.994 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.028 ms**  self **0.018 ms**  `module.py:2589`
              - `archive_model_dtypes` 
                wall **6.255 ms**  self **1.345 ms**  `model_management.py:1045`
              - `ModelPatcherDynamic.__init__` 
                wall **1.990 ms**  self **0.066 ms**  `model_patcher.py:1757`
                - `ModelPatcher.__init__` 
                  wall **1.036 ms**  self **0.098 ms**  `model_patcher.py:341`
          - `_clip_meta_state_dict_from_header` 
            wall **46.378 ms**  self **41.811 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **4.322 ms**  self **3.151 ms**  `clip_qd_reader.py:300`
  - `golden_clip_load` 
    wall **1,635.152 ms**  self **0.261 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **1,625.589 ms**  self **0.030 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **1,625.555 ms**  self **0.018 ms**  `golden_model_transport.py:1087`
        - `GoldenModelTransport._load_sync` 
          wall **1,625.537 ms**  self **0.025 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **1,625.512 ms**  self **0.087 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **1,625.424 ms**  self **0.570 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **1,527.512 ms**  self **3.814 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **135.241 ms**  self **0.020 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **123.172 ms**  self **123.145 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **11.457 ms**  self **0.037 ms**  `golden_source_threads.py:1044`
                    - `_FileLock.__exit__` 
                      wall **11.063 ms**  self **11.063 ms**  `golden_source_threads.py:501`
                - `SourceThreadProcess.wait_ready` 
                  wall **86.562 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **57.304 ms**  self **57.273 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **28.030 ms**  self **0.037 ms**  `golden_source_threads.py:1044`
                    - `_FileLock.__enter__` 
                      wall **20.387 ms**  self **20.387 ms**  `golden_source_threads.py:494`
                    - `_FileLock.__exit__` 
                      wall **7.578 ms**  self **7.578 ms**  `golden_source_threads.py:501`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.214 ms**  self **0.003 ms**  `golden_source_threads.py:1009`
                    - `Popen.poll` 
                      wall **1.211 ms**  self **0.002 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.209 ms**  self **1.209 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **62.817 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **62.435 ms**  self **62.412 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **24.175 ms**  self **0.009 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **23.942 ms**  self **23.910 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **23.050 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **22.693 ms**  self **22.663 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **21.200 ms**  self **0.020 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **20.639 ms**  self **20.593 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **20.803 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **20.300 ms**  self **20.268 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **20.029 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **19.724 ms**  self **19.700 ms**  `golden_source_threads.py:900`
                _... 138 more children >= 1 ms omitted_
              - `collect_placement_telemetry` 
                wall **40.408 ms**  self **0.009 ms**  `source_latency_telemetry.py:512`
                - `_collect_placement_telemetry_uncached` 
                  wall **40.398 ms**  self **18.763 ms**  `source_latency_telemetry.py:424`
                  - `_gpu_telemetry` 
                    wall **19.550 ms**  self **0.135 ms**  `source_latency_telemetry.py:359`
                    - `nvmlDeviceGetClockInfo` 
                      wall **7.767 ms**  self **7.760 ms**  `pynvml.py:3674`
                    - `nvmlDeviceGetPerformanceState` 
                      wall **4.672 ms**  self **4.651 ms**  `pynvml.py:3914`
                    - `nvmlDeviceGetPowerUsage` 
                      wall **3.328 ms**  self **3.290 ms**  `pynvml.py:3962`
                    - `nvmlDeviceGetCurrPcieLinkGeneration` 
                      wall **2.372 ms**  self **2.329 ms**  `pynvml.py:4609`
                  - `_reader_threads` 
                    wall **1.361 ms**  self **0.949 ms**  `source_latency_telemetry.py:290`
              - `GoldenModelTransport.inspect` 
                wall **30.908 ms**  self **0.036 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **30.596 ms**  self **29.985 ms**  `golden_model_transport.py:327`
              - `GpuDestinationPool.acquire` 
                wall **5.631 ms**  self **0.046 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **5.578 ms**  self **5.469 ms**  `golden_model_transport.py:161`
              - `SourceThreadProcess.snapshot` 
                wall **5.330 ms**  self **0.622 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **3.721 ms**  self **0.410 ms**  `golden_source_threads.py:597`
              - `SourceThreadProcess.snapshot` 
                wall **4.859 ms**  self **0.526 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **3.740 ms**  self **0.411 ms**  `golden_source_threads.py:597`
              - `GoldenModelTransport._views` 
                wall **4.607 ms**  self **4.607 ms**  `golden_model_transport.py:2042`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **2.696 ms**  self **0.144 ms**  `golden_qd_transport.py:3130`
              _... 1 more children >= 1 ms omitted_
    - `GoldenTelemetryRecorder.event` 
      wall **5.318 ms**  self **0.009 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **5.310 ms**  self **0.005 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **5.304 ms**  self **0.002 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **5.301 ms**  self **0.037 ms**  `copy.py:227`
            - `deepcopy` 
              wall **5.188 ms**  self **0.002 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **5.186 ms**  self **0.012 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **3.999 ms**  self **0.002 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **3.996 ms**  self **0.173 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **1.507 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **1.505 ms**  self **0.441 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.092 ms**  self **0.001 ms**  `copy.py:128`
                      - `_deepcopy_dict` 
                        wall **1.090 ms**  self **0.150 ms**  `copy.py:227`
  - `golden.clip_load.source_open_read` 
    wall **1,625.644 ms**  self **1,625.644 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **93.255 ms**  self **0.358 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **58.678 ms**  self **1.369 ms**  `golden_serial.py:13060`
      - `validate_qd_adoption` 
        wall **7.432 ms**  self **1.420 ms**  `golden_serial.py:12971`
        - `Module.named_buffers` 
          wall **2.445 ms**  self **0.004 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.441 ms**  self **0.462 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.743 ms**  self **0.234 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.452 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.448 ms**  self **0.435 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.313 ms**  self **0.215 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.617 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.614 ms**  self **0.446 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.081 ms**  self **0.201 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.881 ms**  self **0.009 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.872 ms**  self **0.669 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.549 ms**  self **0.207 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.165 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.163 ms**  self **0.431 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.235 ms**  self **0.215 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.061 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.057 ms**  self **0.465 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **4.563 ms**  self **0.204 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **1.679 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.678 ms**  self **0.415 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **25.830 ms**  self **0.440 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **21.394 ms**  self **0.008 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **21.384 ms**  self **0.034 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **21.349 ms**  self **0.092 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **21.256 ms**  self **0.011 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **20.792 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **19.071 ms**  self **0.089 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.450 ms**  self **0.028 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.925 ms**  self **0.050 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **2.286 ms**  self **0.015 ms**  `module.py:2589`
                        - `disable_weight_init.Linear._load_from_state_dict` 
                          wall **2.265 ms**  self **0.006 ms**  `ops.py:544`
                          - `disable_weight_init._lazy_load_from_state_dict` 
                            wall **2.259 ms**  self **0.029 ms**  `ops.py:494`
                            - `Module.__setattr__` 
                              wall **2.224 ms**  self **0.004 ms**  `module.py:1976`
                              - `Module.register_parameter` 
                                wall **2.219 ms**  self **2.219 ms**  `module.py:592`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.598 ms**  self **0.010 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.440 ms**  self **0.147 ms**  `module.py:2589`
    - `_clip_compute_identity` 
      wall **6.891 ms**  self **0.038 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **6.737 ms**  self **1.651 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **2.068 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.066 ms**  self **0.440 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **58.728 ms**  self **58.728 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **25.851 ms**  self **25.851 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **19.722 ms**  self **0.013 ms**  `threading.py:964`
    - `GoldenModelTransport.begin_layout_preresolve.<locals>.resolve` 
      wall **19.709 ms**  self **0.008 ms**  `golden_model_transport.py:1030`
      - `GoldenModelTransport.inspect` 
        wall **19.691 ms**  self **0.039 ms**  `golden_model_transport.py:999`
        - `_parse_layout` 
          wall **13.536 ms**  self **12.683 ms**  `golden_model_transport.py:327`
        - `_file_identity` 
          wall **6.117 ms**  self **6.117 ms**  `golden_model_transport.py:297`
  - `golden.clip_load.compute_ready_proof` 
    wall **6.908 ms**  self **6.908 ms**  `full_execution_trace.py:330`

### `golden_clip_forward`

- Stage wall: **3,061.859 ms**

- `golden_clip_forward` 
  wall **3,061.859 ms**  self **3,061.859 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **3,061.809 ms**  self **0.260 ms**  `golden_serial.py:12452`
    - `GoldenSerialRunner.run_closure` 
      wall **3,052.678 ms**  self **0.035 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **3,050.556 ms**  self **0.053 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **3,050.237 ms**  self **0.025 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **3,050.072 ms**  self **0.022 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **3,024.719 ms**  self **0.021 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **3,024.698 ms**  self **0.038 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **2,850.638 ms**  self **0.037 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **2,850.601 ms**  self **27.347 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **2,823.211 ms**  self **0.003 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **2,823.208 ms**  self **0.011 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **2,823.197 ms**  self **0.027 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **2,823.170 ms**  self **0.074 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **2,687.778 ms**  self **0.007 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **2,687.771 ms**  self **0.019 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **2,687.752 ms**  self **0.009 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **2,687.741 ms**  self **0.007 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **2,687.734 ms**  self **0.116 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **2,687.618 ms**  self **261.547 ms**  `llama.py:824`
                                        - `prefetch_queue_pop` 
                                          wall **443.053 ms**  self **0.004 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **443.049 ms**  self **0.011 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **443.038 ms**  self **0.007 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **443.031 ms**  self **0.021 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **443.009 ms**  self **0.205 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **386.130 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **386.123 ms**  self **0.090 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **386.033 ms**  self **77.587 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **248.667 ms**  self **0.006 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **248.661 ms**  self **0.013 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **248.648 ms**  self **0.020 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **248.607 ms**  self **247.716 ms**  `ops.py:566`
                                                        - `apply_rope` 
                                                          wall **57.309 ms**  self **57.309 ms**  `llama.py:492`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.418 ms**  self **0.005 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.413 ms**  self **0.013 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **1.400 ms**  self **0.009 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **1.374 ms**  self **0.254 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **1.110 ms**  self **0.008 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **1.102 ms**  self **1.080 ms**  `ops.py:337`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **31.575 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **31.569 ms**  self **0.008 ms**  `module.py:1787`
                                                      - `RMSNorm.forward` 
                                                        wall **31.561 ms**  self **0.010 ms**  `llama.py:436`
                                                        - `rms_norm` 
                                                          wall **31.550 ms**  self **0.025 ms**  `rmsnorm.py:7`
                                                          - `rms_norm` 
                                                            wall **31.453 ms**  self **31.453 ms**  `functional.py:2998`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **24.947 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **24.943 ms**  self **0.018 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **24.926 ms**  self **0.190 ms**  `llama.py:644`
                                                        - `silu` 
                                                          wall **23.245 ms**  self **23.245 ms**  `functional.py:2429`
                                        - `prefetch_queue_pop` 
                                          wall **4.042 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.041 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.037 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.034 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.026 ms**  self **0.141 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.683 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.678 ms**  self **0.085 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.594 ms**  self **1.186 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.973 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.971 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.967 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.963 ms**  self **0.009 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.954 ms**  self **0.178 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.766 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.761 ms**  self **0.022 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.739 ms**  self **1.306 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.956 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.954 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.950 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.946 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.939 ms**  self **0.171 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.766 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.763 ms**  self **0.012 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.751 ms**  self **1.418 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.603 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.600 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.595 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.590 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.582 ms**  self **0.063 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.672 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.667 ms**  self **0.018 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.649 ms**  self **1.392 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.536 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.535 ms**  self **0.003 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.531 ms**  self **0.003 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.528 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.520 ms**  self **0.151 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.517 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.513 ms**  self **0.040 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.473 ms**  self **1.266 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.443 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.441 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.435 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.430 ms**  self **0.011 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.419 ms**  self **0.135 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.821 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.816 ms**  self **0.013 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **1.803 ms**  self **1.078 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.113 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.109 ms**  self **0.010 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.099 ms**  self **0.087 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **3.411 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.410 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.405 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.400 ms**  self **0.007 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.393 ms**  self **0.103 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.349 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.344 ms**  self **0.049 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.295 ms**  self **0.896 ms**  `llama.py:540`
                                        _... 6 more children >= 1 ms omitted_
  - `BaseEventLoop._run_once` 
    wall **57.873 ms**  self **0.008 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **57.805 ms**  self **14.028 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **57.778 ms**  self **0.006 ms**  `golden_serial.py:15624`

### `golden_unet_load`

- Stage wall: **2,414.227 ms**

- `golden_unet_load` 
  wall **2,414.227 ms**  self **58.341 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **2,349.100 ms**  self **0.014 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **2,348.841 ms**  self **0.020 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **2,348.821 ms**  self **0.004 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **2,348.816 ms**  self **0.100 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **2,348.716 ms**  self **0.653 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **2,262.136 ms**  self **5.944 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **219.914 ms**  self **0.012 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **219.660 ms**  self **219.621 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **42.883 ms**  self **0.018 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **29.924 ms**  self **29.888 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **12.488 ms**  self **0.029 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__enter__` 
                    wall **7.084 ms**  self **7.084 ms**  `golden_source_threads.py:494`
                  - `_FileLock.__exit__` 
                    wall **5.348 ms**  self **5.348 ms**  `golden_source_threads.py:501`
              - `SourceThreadProcess.wait_ready` 
                wall **28.696 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **27.600 ms**  self **27.579 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **28.399 ms**  self **0.018 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **27.513 ms**  self **27.479 ms**  `golden_source_threads.py:900`
              - `GoldenQDTransport.publish` 
                wall **26.876 ms**  self **0.011 ms**  `golden_qd_transport.py:3099`
                - `TransportDispatcher.publish` 
                  wall **26.842 ms**  self **26.803 ms**  `golden_qd_transport.py:2153`
              - `SourceThreadProcess.wait_ready` 
                wall **23.532 ms**  self **0.020 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **23.253 ms**  self **23.221 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **23.270 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **22.861 ms**  self **22.832 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **23.186 ms**  self **0.010 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **22.982 ms**  self **22.949 ms**  `golden_source_threads.py:900`
              _... 176 more children >= 1 ms omitted_
            - `GoldenModelTransport._views` 
              wall **40.756 ms**  self **40.756 ms**  `golden_model_transport.py:2042`
            - `SourceThreadProcess.snapshot` 
              wall **11.296 ms**  self **0.928 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **9.285 ms**  self **0.881 ms**  `golden_source_threads.py:597`
            - `SourceThreadProcess.snapshot` 
              wall **10.112 ms**  self **0.808 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **8.384 ms**  self **0.645 ms**  `golden_source_threads.py:597`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **9.522 ms**  self **0.152 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **6.539 ms**  self **0.013 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **6.518 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **6.505 ms**  self **0.008 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **6.495 ms**  self **6.491 ms**  `threading.py:288`
              - `_Telemetry.snapshot` 
                wall **1.364 ms**  self **0.005 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **1.359 ms**  self **0.130 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **1.192 ms**  self **0.009 ms**  `golden_qd_transport.py:2016`
                    - `_json_safe.<locals>.<dictcomp>` 
                      wall **1.175 ms**  self **0.162 ms**  `golden_qd_transport.py:2022`
              - `GoldenQDTransport._record_ranges` 
                wall **1.066 ms**  self **0.832 ms**  `golden_qd_transport.py:3261`
            - `GoldenModelTransport.inspect` 
              wall **6.920 ms**  self **0.012 ms**  `golden_model_transport.py:999`
              - `_file_identity` 
                wall **6.908 ms**  self **6.908 ms**  `golden_model_transport.py:297`
            - `summarize_source_operations` 
              wall **3.148 ms**  self **1.220 ms**  `source_latency_telemetry.py:68`
            - `GpuDestinationPool.acquire` 
              wall **2.077 ms**  self **0.022 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **2.049 ms**  self **1.923 ms**  `golden_model_transport.py:161`
  - `golden.unet.source_h2d_transport` 
    wall **2,217.288 ms**  self **0.116 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop._run_once` 
    wall **2,216.959 ms**  self **0.027 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **2,216.681 ms**  self **2,216.679 ms**  `selectors.py:451`
  - `Llama2_.compute_freqs_cis` 
    wall **1,850.894 ms**  self **0.287 ms**  `llama.py:815`
    - `precompute_freqs_cis` 
      wall **1,850.607 ms**  self **201.031 ms**  `llama.py:445`
      - `_register_overrides_from_graph.<locals>.eager_router` 
        wall **1,362.983 ms**  self **0.024 ms**  `registry.py:938`
        - `_register_overrides_from_graph.<locals>._dispatch` 
          wall **1,362.948 ms**  self **0.083 ms**  `registry.py:926`
          - `OpOverloadPacket.__call__` 
            wall **1,361.531 ms**  self **0.073 ms**  `_ops.py:1338`
            - `_bmm_outer_product_impl` 
              wall **1,361.459 ms**  self **34.971 ms**  `triton_impl.py:18`
              - `bmm_outer_product` 
                wall **1,326.445 ms**  self **0.716 ms**  `triton_kernels.py:77`
                - `_make_wrapper.<locals>.wrapper` 
                  wall **1,325.333 ms**  self **0.007 ms**  `instrumentation.py:202`
                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                    wall **1,325.258 ms**  self **0.033 ms**  `jit.py:374`
                    - `JITFunction.run` 
                      wall **1,325.224 ms**  self **0.122 ms**  `jit.py:726`
                      - `DriverConfig.active` 
                        wall **724.028 ms**  self **0.011 ms**  `driver.py:36`
                        - `DriverConfig.default` 
                          wall **724.017 ms**  self **0.009 ms**  `driver.py:30`
                          - `_create_driver` 
                            wall **724.008 ms**  self **0.041 ms**  `driver.py:8`
                            - `CudaDriver.__init__` 
                              wall **723.910 ms**  self **0.025 ms**  `driver.py:341`
                              - `CudaUtils.__init__` 
                                wall **723.848 ms**  self **0.049 ms**  `driver.py:100`
                                - `compile_module_from_file` 
                                  wall **708.548 ms**  self **0.017 ms**  `build.py:193`
                                  - `_compile_so_from_file` 
                                    wall **708.531 ms**  self **1.267 ms**  `build.py:157`
                                    - `_compile_so` 
                                      wall **707.198 ms**  self **0.382 ms**  `build.py:132`
                                      - `_build` 
                                        wall **695.814 ms**  self **0.047 ms**  `build.py:60`
                                        - `check_call` 
                                          wall **693.808 ms**  self **0.010 ms**  `subprocess.py:398`
                                          - `call` 
                                            wall **693.796 ms**  self **0.018 ms**  `subprocess.py:381`
                                            - `Popen.wait` 
                                              wall **690.571 ms**  self **0.003 ms**  `subprocess.py:1259`
                                              - `Popen._wait` 
                                                wall **690.568 ms**  self **0.018 ms**  `subprocess.py:2014`
                                                - `Popen._try_wait` 
                                                  wall **690.548 ms**  self **690.548 ms**  `subprocess.py:2001`
                                            - `Popen.__init__` 
                                              wall **3.197 ms**  self **0.017 ms**  `subprocess.py:807`
                                              - `Popen._execute_child` 
                                                wall **3.119 ms**  self **3.017 ms**  `subprocess.py:1789`
                                        - `_find_compiler` 
                                          wall **1.202 ms**  self **0.034 ms**  `build.py:21`
                                      - `_get_cache_manager` 
                                        wall **7.171 ms**  self **0.201 ms**  `build.py:117`
                                        - `platform_key` 
                                          wall **6.572 ms**  self **0.033 ms**  `build.py:94`
                                          - `architecture` 
                                            wall **6.526 ms**  self **0.042 ms**  `platform.py:646`
                                            - `_syscmd_file` 
                                              wall **6.485 ms**  self **0.772 ms**  `platform.py:602`
                                              - `check_output` 
                                                wall **5.177 ms**  self **0.007 ms**  `subprocess.py:417`
                                                - `run` 
                                                  wall **5.171 ms**  self **0.008 ms**  `subprocess.py:506`
                                                  - `Popen.__init__` 
                                                    wall **5.162 ms**  self **0.169 ms**  `subprocess.py:807`
                                                    - `Popen._execute_child` 
                                                      wall **4.891 ms**  self **4.674 ms**  `subprocess.py:1789`
                                      - `_load_module_from_path` 
                                        wall **1.733 ms**  self **1.733 ms**  `build.py:108`
                                      - `FileCacheManager.put` 
                                        wall **1.057 ms**  self **0.900 ms**  `cache.py:103`
                                - `library_dirs` 
                                  wall **15.251 ms**  self **0.009 ms**  `driver.py:49`
                                  - `libcuda_dirs` 
                                    wall **15.243 ms**  self **0.176 ms**  `driver.py:25`
                                    - `check_output` 
                                      wall **14.912 ms**  self **0.018 ms**  `subprocess.py:417`
                                      - `run` 
                                        wall **14.891 ms**  self **0.060 ms**  `subprocess.py:506`
                                        - `Popen.communicate` 
                                          wall **8.210 ms**  self **8.108 ms**  `subprocess.py:1165`
                                        - `Popen.__init__` 
                                          wall **6.613 ms**  self **0.310 ms**  `subprocess.py:807`
                                          - `Popen._execute_child` 
                                            wall **6.112 ms**  self **5.856 ms**  `subprocess.py:1789`
                      - `JITFunction._do_compile` 
                        wall **315.212 ms**  self **0.045 ms**  `jit.py:877`
                        - `compile` 
                          wall **315.152 ms**  self **27.168 ms**  `compiler.py:226`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **61.882 ms**  self **0.009 ms**  `compiler.py:606`
                            - `CUDABackend.make_ptx` 
                              wall **61.873 ms**  self **60.468 ms**  `compiler.py:480`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **60.712 ms**  self **0.094 ms**  `compiler.py:605`
                            - `CUDABackend.make_llir` 
                              wall **60.618 ms**  self **60.519 ms**  `compiler.py:367`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **46.102 ms**  self **0.031 ms**  `compiler.py:607`
                            - `CUDABackend.make_cubin` 
                              wall **46.069 ms**  self **0.281 ms**  `compiler.py:513`
                              - `run` 
                                wall **44.578 ms**  self **0.018 ms**  `subprocess.py:506`
                                - `Popen.communicate` 
                                  wall **41.450 ms**  self **0.005 ms**  `subprocess.py:1165`
                                  - `Popen.wait` 
                                    wall **41.445 ms**  self **0.003 ms**  `subprocess.py:1259`
                                    - `Popen._wait` 
                                      wall **41.442 ms**  self **0.011 ms**  `subprocess.py:2014`
                                      - `Popen._try_wait` 
                                        wall **41.429 ms**  self **41.429 ms**  `subprocess.py:2001`
                                - `Popen.__init__` 
                                  wall **3.101 ms**  self **0.017 ms**  `subprocess.py:807`
                                  - `Popen._execute_child` 
                                    wall **3.043 ms**  self **0.028 ms**  `subprocess.py:1789`
                                    - `Popen._posix_spawn` 
                                      wall **3.015 ms**  self **2.996 ms**  `subprocess.py:1750`
                          - `get_cache_key` 
                            wall **34.125 ms**  self **0.030 ms**  `cache.py:319`
                            - `CUDABackend.hash` 
                              wall **30.276 ms**  self **0.010 ms**  `compiler.py:611`
                              - `get_ptxas_version` 
                                wall **30.266 ms**  self **0.011 ms**  `compiler.py:42`
                                - `get_ptxas` 
                                  wall **19.997 ms**  self **0.003 ms**  `compiler.py:38`
                                  - `env_base.__get__` 
                                    wall **19.994 ms**  self **0.003 ms**  `knobs.py:76`
                                    - `env_nvidia_tool.get` 
                                      wall **19.992 ms**  self **0.004 ms**  `knobs.py:203`
                                      - `env_nvidia_tool.transform` 
                                        wall **19.988 ms**  self **0.011 ms**  `knobs.py:206`
                                        - `NvidiaTool.from_path` 
                                          wall **19.977 ms**  self **0.014 ms**  `knobs.py:181`
                                          - `check_output` 
                                            wall **19.538 ms**  self **0.010 ms**  `subprocess.py:417`
                                            - `run` 
                                              wall **19.526 ms**  self **0.018 ms**  `subprocess.py:506`
                                              - `Popen.__init__` 
                                                wall **10.522 ms**  self **0.070 ms**  `subprocess.py:807`
                                                - `Popen._execute_child` 
                                                  wall **10.323 ms**  self **10.118 ms**  `subprocess.py:1789`
                                              - `Popen.communicate` 
                                                wall **8.979 ms**  self **8.937 ms**  `subprocess.py:1165`
                                - `check_output` 
                                  wall **10.251 ms**  self **0.009 ms**  `subprocess.py:417`
                                  - `run` 
                                    wall **10.240 ms**  self **0.013 ms**  `subprocess.py:506`
                                    - `Popen.communicate` 
                                      wall **6.998 ms**  self **6.961 ms**  `subprocess.py:1165`
                                    - `Popen.__init__` 
                                      wall **3.221 ms**  self **0.175 ms**  `subprocess.py:807`
                                      - `Popen._execute_child` 
                                        wall **2.978 ms**  self **2.883 ms**  `subprocess.py:1789`
                            - `CUDAOptions.hash` 
                              wall **2.059 ms**  self **0.036 ms**  `compiler.py:153`
                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                wall **1.997 ms**  self **0.009 ms**  `compiler.py:155`
                                - `file_hash` 
                                  wall **1.988 ms**  self **1.988 ms**  `compiler.py:97`
                            - `ASTSource.hash` 
                              wall **1.760 ms**  self **0.039 ms**  `compiler.py:71`
                              - `JITCallable.cache_key` 
                                wall **1.709 ms**  self **0.065 ms**  `jit.py:515`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **29.646 ms**  self **0.080 ms**  `compiler.py:602`
                            - `CUDABackend.make_ttgir` 
                              wall **29.567 ms**  self **29.567 ms**  `compiler.py:260`
                          - `ASTSource.make_ir` 
                            wall **26.999 ms**  self **0.032 ms**  `compiler.py:78`
                            - `ast_to_ttir` 
                              wall **26.968 ms**  self **0.672 ms**  `code_generator.py:1662`
                              - `CodeGenerator.visit` 
                                wall **23.937 ms**  self **0.044 ms**  `code_generator.py:1581`
                                - `NodeVisitor.visit` 
                                  wall **23.893 ms**  self **0.007 ms**  `ast.py:414`
                                  - `CodeGenerator.visit_Module` 
                                    wall **23.885 ms**  self **0.003 ms**  `code_generator.py:519`
                                    - `NodeVisitor.generic_visit` 
                                      wall **23.882 ms**  self **0.008 ms**  `ast.py:420`
                                      - `CodeGenerator.visit` 
                                        wall **23.871 ms**  self **0.030 ms**  `code_generator.py:1581`
                                        - `NodeVisitor.visit` 
                                          wall **23.841 ms**  self **0.011 ms**  `ast.py:414`
                                          - `CodeGenerator.visit_FunctionDef` 
                                            wall **23.830 ms**  self **0.140 ms**  `code_generator.py:628`
                                            - `CodeGenerator.visit_compound_statement` 
                                              wall **22.561 ms**  self **0.035 ms**  `code_generator.py:508`
                                              - `CodeGenerator.visit` 
                                                wall **7.623 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **7.617 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **7.616 ms**  self **0.008 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **7.577 ms**  self **0.013 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **7.564 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **7.562 ms**  self **0.261 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **6.773 ms**  self **0.018 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **6.753 ms**  self **0.096 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **6.363 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **6.359 ms**  self **0.003 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **6.356 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **6.354 ms**  self **0.008 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **6.344 ms**  self **6.344 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **3.267 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **3.261 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Expr` 
                                                    wall **3.258 ms**  self **0.004 ms**  `code_generator.py:1556`
                                                    - `NodeVisitor.generic_visit` 
                                                      wall **3.255 ms**  self **0.005 ms**  `ast.py:420`
                                                      - `CodeGenerator.visit` 
                                                        wall **3.248 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                        - `NodeVisitor.visit` 
                                                          wall **3.243 ms**  self **0.003 ms**  `ast.py:414`
                                                          - `CodeGenerator.visit_Call` 
                                                            wall **3.240 ms**  self **0.025 ms**  `code_generator.py:1455`
                                                            - `CodeGenerator.visit` 
                                                              wall **2.979 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                              - `NodeVisitor.visit` 
                                                                wall **2.973 ms**  self **0.006 ms**  `ast.py:414`
                                                                - `CodeGenerator.visit_BinOp` 
                                                                  wall **2.967 ms**  self **0.005 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **2.284 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **2.279 ms**  self **0.004 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **2.275 ms**  self **2.275 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **2.522 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.515 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.513 ms**  self **0.009 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.481 ms**  self **0.024 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.457 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.455 ms**  self **0.014 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **2.355 ms**  self **0.005 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **2.349 ms**  self **0.043 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **2.067 ms**  self **0.003 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **2.064 ms**  self **0.002 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **2.062 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **2.060 ms**  self **0.005 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **2.054 ms**  self **2.054 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **2.095 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.090 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.088 ms**  self **0.009 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.037 ms**  self **0.016 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.021 ms**  self **0.005 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **2.015 ms**  self **0.003 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.626 ms**  self **0.002 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.623 ms**  self **0.002 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.622 ms**  self **0.001 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.620 ms**  self **0.002 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.618 ms**  self **0.003 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.615 ms**  self **0.019 ms**  `semantic.py:230`
                                                                      - `TritonSemantic.binary_op_sanitize_overflow_impl` 
                                                                        wall **1.510 ms**  self **1.510 ms**  `semantic.py:212`
                                              - `CodeGenerator.visit` 
                                                wall **2.010 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.003 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.001 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.954 ms**  self **0.040 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.914 ms**  self **0.004 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **1.910 ms**  self **0.017 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.581 ms**  self **0.222 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.359 ms**  self **0.006 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.353 ms**  self **0.008 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.534 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.529 ms**  self **0.001 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.527 ms**  self **0.009 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.480 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.465 ms**  self **0.005 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **1.460 ms**  self **0.010 ms**  `code_generator.py:1455`
                                              - `CodeGenerator.visit` 
                                                wall **1.165 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.159 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.156 ms**  self **0.012 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.104 ms**  self **0.074 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.030 ms**  self **0.005 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.026 ms**  self **0.004 ms**  `code_generator.py:810`
                              - `JITCallable.parse` 
                                wall **1.037 ms**  self **0.013 ms**  `jit.py:546`
                                - `parse` 
                                  wall **1.024 ms**  self **1.024 ms**  `ast.py:33`
                          - `FileCacheManager.put` 
                            wall **8.988 ms**  self **8.575 ms**  `cache.py:103`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **6.812 ms**  self **0.062 ms**  `compiler.py:601`
                            - `CUDABackend.make_ttir` 
                              wall **6.751 ms**  self **6.751 ms**  `compiler.py:244`
                          _... 5 more children >= 1 ms omitted_
                      - `dynamic_func` 
                        wall **280.773 ms**  self **280.750 ms**  `<string>:2`
                      - `CompiledKernel.launch_metadata` 
                        wall **3.148 ms**  self **0.017 ms**  `compiler.py:493`
                        - `CompiledKernel._init_handles` 
                          wall **3.129 ms**  self **0.275 ms**  `compiler.py:448`
                          - `max_shared_mem` 
                            wall **2.591 ms**  self **2.591 ms**  `compiler.py:133`
          - `_OpNamespace.__getattr__` 
            wall **1.048 ms**  self **0.032 ms**  `_ops.py:1448`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **181.230 ms**  self **0.019 ms**  `_tensor.py:32`
        - `Tensor.__rpow__` 
          wall **181.211 ms**  self **181.211 ms**  `_tensor.py:1155`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **105.363 ms**  self **0.014 ms**  `_tensor.py:32`
        - `Tensor.__rdiv__` 
          wall **105.349 ms**  self **105.349 ms**  `_tensor.py:1120`
  - `CLIP.load_model` 
    wall **173.902 ms**  self **0.031 ms**  `sd.py:459`
    - `load_models_gpu` 
      wall **173.868 ms**  self **0.129 ms**  `model_management.py:909`
      - `LoadedModel.model_load` 
        wall **117.680 ms**  self **0.037 ms**  `model_management.py:782`
        - `LoadedModel.model_use_more_vram` 
          wall **117.611 ms**  self **0.016 ms**  `model_management.py:817`
          - `ModelPatcherDynamic.partially_load` 
            wall **117.595 ms**  self **0.163 ms**  `model_patcher.py:2141`
            - `ModelPatcherDynamic.load` 
              wall **117.344 ms**  self **6.705 ms**  `model_patcher.py:1853`
              - `ModelPatcher._load_list` 
                wall **45.985 ms**  self **14.807 ms**  `model_patcher.py:945`
                - `module_size` 
                  wall **1.238 ms**  self **0.002 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **1.236 ms**  self **0.004 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **1.233 ms**  self **1.233 ms**  `module.py:2148`
              - `HostBuffer.__del__` 
                wall **8.899 ms**  self **8.868 ms**  `host_buffer.py:125`
              - `HostBuffer.__init__` 
                wall **5.715 ms**  self **5.704 ms**  `host_buffer.py:79`
              - `ModelPatcherDynamic._vbar_get` 
                wall **2.605 ms**  self **0.027 ms**  `model_patcher.py:1797`
                - `ModelVBAR.__init__` 
                  wall **2.577 ms**  self **2.498 ms**  `model_vbar.py:50`
              - `Module.named_buffers` 
                wall **2.563 ms**  self **0.003 ms**  `module.py:2754`
                - `Module._named_members` 
                  wall **2.560 ms**  self **0.435 ms**  `module.py:2650`
              - `HostBuffer.__del__` 
                wall **1.064 ms**  self **1.037 ms**  `host_buffer.py:125`
      - `LoadedModel.model_memory_required` 
        wall **55.330 ms**  self **0.007 ms**  `model_management.py:776`
        - `LoadedModel.model_memory` 
          wall **55.322 ms**  self **0.010 ms**  `model_management.py:767`
          - `ModelPatcher.model_size` 
            wall **55.312 ms**  self **21.320 ms**  `model_patcher.py:405`
            - `module_size` 
              wall **33.993 ms**  self **0.170 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **33.823 ms**  self **0.020 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **33.799 ms**  self **0.013 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **33.668 ms**  self **0.013 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **33.653 ms**  self **0.015 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **33.568 ms**  self **0.084 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **8.883 ms**  self **0.021 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **8.605 ms**  self **0.015 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **8.537 ms**  self **0.007 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **8.530 ms**  self **8.530 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **5.999 ms**  self **0.017 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **4.835 ms**  self **0.012 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **3.702 ms**  self **0.004 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.697 ms**  self **3.697 ms**  `module.py:2148`
                            - `Module.state_dict` 
                              wall **1.099 ms**  self **0.008 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.090 ms**  self **1.090 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **5.127 ms**  self **0.011 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **4.236 ms**  self **0.018 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **3.639 ms**  self **0.005 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.635 ms**  self **3.635 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **1.623 ms**  self **0.012 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.530 ms**  self **0.013 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.042 ms**  self **0.004 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.038 ms**  self **1.038 ms**  `module.py:2148`
  - `BaseEventLoop._run_once` 
    wall **138.605 ms**  self **0.016 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **126.211 ms**  self **2.827 ms**  `events.py:78`
      - `golden.unet.skeleton_patcher_construction` 
        wall **70.349 ms**  self **70.349 ms**  `full_execution_trace.py:330`
      - `golden.unet.header_config_preflight` 
        wall **53.035 ms**  self **53.035 ms**  `full_execution_trace.py:330`
    - `Handle._run` 
      wall **12.204 ms**  self **12.204 ms**  `events.py:78`
  - `SDClipModel.process_tokens` 
    wall **135.313 ms**  self **2.051 ms**  `sd1_clip.py:172`
    - `Module._wrapped_call_impl` 
      wall **133.243 ms**  self **0.014 ms**  `module.py:1779`
      - `Module._call_impl` 
        wall **133.229 ms**  self **0.022 ms**  `module.py:1787`
        - `disable_weight_init.Embedding.forward` 
          wall **133.207 ms**  self **0.011 ms**  `ops.py:798`
          - `disable_weight_init.Embedding.forward_comfy_cast_weights` 
            wall **133.174 ms**  self **93.766 ms**  `ops.py:790`
            - `embedding` 
              wall **39.308 ms**  self **39.308 ms**  `functional.py:2509`
  - `_overlap_owner_call` 
    wall **126.188 ms**  self **0.002 ms**  `golden_serial.py:15624`
    - `_unet_load_with_worker_stage` 
      wall **126.186 ms**  self **0.002 ms**  `golden_parallel.py:517`
      - `golden_unet_load` 
        wall **126.185 ms**  self **0.251 ms**  `golden_serial.py:13274`
        - `Lumina2.get_model` 
          wall **65.573 ms**  self **0.036 ms**  `supported_models.py:1193`
          - `Lumina2.__init__` 
            wall **65.536 ms**  self **0.031 ms**  `model_base.py:1504`
            - `BaseModel.__init__` 
              wall **65.502 ms**  self **29.485 ms**  `model_base.py:164`
              - `model_sampling` 
                wall **21.519 ms**  self **0.060 ms**  `model_base.py:110`
                - `ModelSamplingDiscreteFlow.__init__` 
                  wall **21.457 ms**  self **0.011 ms**  `model_sampling.py:285`
                  - `ModelSamplingDiscreteFlow.set_parameters` 
                    wall **21.421 ms**  self **14.258 ms**  `model_sampling.py:298`
                    - `ModelSamplingDiscreteFlow.sigma` 
                      wall **7.143 ms**  self **1.595 ms**  `model_sampling.py:318`
                      - `time_snr_shift` 
                        wall **5.548 ms**  self **5.548 ms**  `model_sampling.py:279`
              - `archive_model_dtypes` 
                wall **6.497 ms**  self **1.253 ms**  `model_management.py:1045`
              - `Module.eval` 
                wall **4.591 ms**  self **0.002 ms**  `module.py:2916`
                - `Module.train` 
                  wall **4.589 ms**  self **0.015 ms**  `module.py:2894`
                  - `Module.train` 
                    wall **3.939 ms**  self **0.025 ms**  `module.py:2894`
              - `Module.requires_grad_` 
                wall **3.084 ms**  self **0.207 ms**  `module.py:2934`
        - `golden_unet_load.<locals>.<dictcomp>` 
          wall **35.195 ms**  self **35.195 ms**  `golden_serial.py:13361`
        - `model_config_from_unet` 
          wall **16.055 ms**  self **0.119 ms**  `model_detection.py:1283`
          - `detect_unet_config` 
            wall **15.544 ms**  self **10.055 ms**  `model_detection.py:44`
            - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
              wall **3.031 ms**  self **0.038 ms**  `wrappers.py:291`
              - `std` 
                wall **2.992 ms**  self **0.508 ms**  `__init__.py:2620`
                - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
                  wall **1.234 ms**  self **0.023 ms**  `wrappers.py:291`
                  - `elementwise_unary_scalar_wrapper.<locals>._fn` 
                    wall **1.209 ms**  self **0.015 ms**  `wrappers.py:491`
                    - `_disable_dynamo.<locals>.inner` 
                      wall **1.194 ms**  self **0.059 ms**  `_compile.py:42`
            - `count_blocks` 
              wall **2.443 ms**  self **2.443 ms**  `model_detection.py:10`
        - `ModelPatcherDynamic.__init__` 
          wall **4.693 ms**  self **0.015 ms**  `model_patcher.py:1757`
          - `ModelPatcher.__init__` 
            wall **3.478 ms**  self **0.055 ms**  `model_patcher.py:341`
            - `uuid4` 
              wall **2.147 ms**  self **2.131 ms**  `uuid.py:721`
            - `uuid4` 
              wall **1.239 ms**  self **1.225 ms**  `uuid.py:721`
          - `ModelPatcherDynamic.register_load_device` 
            wall **1.183 ms**  self **0.021 ms**  `model_patcher.py:1770`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.523 ms**  self **0.015 ms**  `golden_serial.py:13404`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.048 ms**  self **0.015 ms**  `golden_serial.py:13404`
  _... 8 more children >= 1 ms omitted_

### `golden_sampler_prepare`

- Stage wall: **55.993 ms**

- `golden_sampler_prepare` 
  wall **55.993 ms**  self **0.674 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **55.974 ms**  self **0.077 ms**  `golden_serial.py:13634`
    - `GoldenSerialRunner.run_closure` 
      wall **54.149 ms**  self **0.057 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **32.314 ms**  self **0.017 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **31.998 ms**  self **0.020 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **30.916 ms**  self **0.013 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **30.681 ms**  self **0.027 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **22.257 ms**  self **0.018 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **19.680 ms**  self **0.036 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **19.423 ms**  self **0.844 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **18.453 ms**  self **18.449 ms**  `nodes.py:1992`
                - `GoldenSerialRunner._ensure` 
                  wall **1.618 ms**  self **0.013 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **6.904 ms**  self **0.033 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **6.427 ms**  self **0.017 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **6.298 ms**  self **0.026 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **6.025 ms**  self **0.016 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **5.781 ms**  self **0.002 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **5.779 ms**  self **0.007 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **5.772 ms**  self **5.770 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **1.466 ms**  self **0.021 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **15.855 ms**  self **0.022 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **14.897 ms**  self **0.015 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **14.274 ms**  self **0.016 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **13.596 ms**  self **0.012 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **13.574 ms**  self **0.020 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **13.397 ms**  self **0.008 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **13.308 ms**  self **0.011 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **13.297 ms**  self **0.076 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **12.263 ms**  self **0.041 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **11.889 ms**  self **1.719 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **10.170 ms**  self **0.402 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **9.769 ms**  self **0.027 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **9.704 ms**  self **0.028 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **8.338 ms**  self **0.061 ms**  `module.py:2199`
      - `GoldenSerialRunner._ensure` 
        wall **1.833 ms**  self **0.013 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.819 ms**  self **0.041 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.287 ms**  self **0.016 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **1.038 ms**  self **0.009 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **1.010 ms**  self **0.018 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.240 ms**  self **0.012 ms**  `golden_serial.py:9122`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **54.179 ms**  self **54.179 ms**  `full_execution_trace.py:330`
  - `golden.sampler_prepare.prepare_validation` 
    wall **1.073 ms**  self **1.073 ms**  `full_execution_trace.py:330`

### `golden_vae_load`

- Stage wall: **554.772 ms**

- `golden_vae_load` 
  wall **554.772 ms**  self **96.916 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **458.153 ms**  self **0.014 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **457.821 ms**  self **0.021 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **457.800 ms**  self **0.011 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **457.789 ms**  self **0.011 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **457.778 ms**  self **0.331 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **344.521 ms**  self **0.199 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **302.359 ms**  self **0.032 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **250.183 ms**  self **250.183 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._read_message` 
                  wall **51.092 ms**  self **51.061 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **11.718 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **10.442 ms**  self **10.424 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **10.894 ms**  self **0.020 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **8.590 ms**  self **8.564 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **1.583 ms**  self **0.028 ms**  `golden_source_threads.py:1044`
              - `GoldenQDTransport.publish` 
                wall **3.847 ms**  self **0.009 ms**  `golden_qd_transport.py:3099`
                - `TransportDispatcher.publish` 
                  wall **3.819 ms**  self **3.774 ms**  `golden_qd_transport.py:2153`
              - `SourceThreadProcess.claim_ready` 
                wall **3.020 ms**  self **0.020 ms**  `golden_source_threads.py:1175`
                - `_FileLock.__enter__` 
                  wall **2.817 ms**  self **2.817 ms**  `golden_source_threads.py:494`
              - `SourceThreadProcess.wait_ready` 
                wall **2.642 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **1.250 ms**  self **1.230 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.plan_once` 
                wall **2.642 ms**  self **0.200 ms**  `golden_source_threads.py:918`
                - `SourceThreadProcess._read_message` 
                  wall **1.988 ms**  self **1.974 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **2.285 ms**  self **0.012 ms**  `golden_source_threads.py:1129`
              _... 2 more children >= 1 ms omitted_
            - `GoldenModelTransport._views` 
              wall **76.698 ms**  self **76.698 ms**  `golden_model_transport.py:2042`
            - `GoldenModelTransport.inspect` 
              wall **26.702 ms**  self **0.024 ms**  `golden_model_transport.py:999`
              - `_parse_layout` 
                wall **26.335 ms**  self **25.857 ms**  `golden_model_transport.py:327`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **3.220 ms**  self **0.068 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **2.868 ms**  self **0.011 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **2.847 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **2.835 ms**  self **0.005 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **2.827 ms**  self **2.824 ms**  `threading.py:288`
            - `GpuDestinationPool.acquire` 
              wall **2.163 ms**  self **0.022 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **2.134 ms**  self **2.054 ms**  `golden_model_transport.py:161`
            - `SourceThreadProcess.wait_quiescent` 
              wall **1.406 ms**  self **0.013 ms**  `golden_source_threads.py:1228`
            - `SourceThreadProcess.snapshot` 
              wall **1.015 ms**  self **0.087 ms**  `golden_source_threads.py:1240`
  - `BaseEventLoop._run_once` 
    wall **457.856 ms**  self **0.014 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **457.662 ms**  self **457.660 ms**  `selectors.py:451`
  - `sample_custom` 
    wall **173.928 ms**  self **2.116 ms**  `sample.py:86`
    - `sample` 
      wall **171.806 ms**  self **0.037 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **171.679 ms**  self **0.076 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **171.425 ms**  self **0.018 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **171.408 ms**  self **0.071 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **170.689 ms**  self **0.005 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **170.679 ms**  self **0.022 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **170.657 ms**  self **1.676 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **119.220 ms**  self **0.007 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **119.210 ms**  self **0.007 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **119.203 ms**  self **0.040 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **119.067 ms**  self **0.080 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **117.868 ms**  self **0.015 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **117.835 ms**  self **0.003 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **117.832 ms**  self **0.171 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **117.611 ms**  self **4.288 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **33.739 ms**  self **3.024 ms**  `model_patcher.py:945`
                                  - `Module.named_buffers` 
                                    wall **2.397 ms**  self **0.003 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **2.394 ms**  self **0.481 ms**  `module.py:2650`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **1.475 ms**  self **0.010 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **1.414 ms**  self **1.146 ms**  `model_patcher.py:899`
                  - `CFGGuider.inner_sample` 
                    wall **49.594 ms**  self **47.950 ms**  `samplers.py:1220`
                    - `WrapperExecutor.execute` 
                      wall **1.129 ms**  self **0.021 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.108 ms**  self **0.102 ms**  `samplers.py:983`
  - `prepare_sampling` 
    wall **173.807 ms**  self **0.007 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **173.796 ms**  self **0.004 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **173.792 ms**  self **0.016 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **173.700 ms**  self **0.059 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **172.593 ms**  self **0.018 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **172.557 ms**  self **0.003 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **172.554 ms**  self **0.233 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **172.265 ms**  self **5.104 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **36.038 ms**  self **4.955 ms**  `model_patcher.py:945`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **5.773 ms**  self **1.445 ms**  `model_patcher.py:1842`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **2.667 ms**  self **0.180 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **2.413 ms**  self **0.061 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **1.968 ms**  self **1.966 ms**  `__init__.py:350`
                  - `Module.named_buffers` 
                    wall **2.667 ms**  self **0.004 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **2.663 ms**  self **0.491 ms**  `module.py:2650`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.581 ms**  self **0.051 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.474 ms**  self **0.033 ms**  `model_patcher.py:899`
                      - `cast_to_device` 
                        wall **1.219 ms**  self **0.003 ms**  `model_management.py:1555`
                        - `cast_to` 
                          wall **1.206 ms**  self **1.206 ms**  `model_management.py:1527`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.453 ms**  self **0.160 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.234 ms**  self **0.504 ms**  `model_patcher.py:899`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.365 ms**  self **0.183 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.090 ms**  self **0.506 ms**  `model_patcher.py:899`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.343 ms**  self **0.410 ms**  `model_patcher.py:1947`
                  _... 4 more children >= 1 ms omitted_
  - `_vae_load_with_worker_stage` 
    wall **95.536 ms**  self **0.005 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **95.527 ms**  self **0.236 ms**  `golden_serial.py:14310`
      - `VAE.__init__` 
        wall **89.580 ms**  self **59.419 ms**  `sd.py:487`
        - `Module.load_state_dict` 
          wall **17.590 ms**  self **0.104 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **17.486 ms**  self **0.022 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **9.279 ms**  self **0.027 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **7.008 ms**  self **0.028 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.595 ms**  self **0.018 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.041 ms**  self **0.019 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.093 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.523 ms**  self **0.016 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.076 ms**  self **0.018 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **1.666 ms**  self **0.018 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **7.666 ms**  self **0.027 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **4.880 ms**  self **0.021 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.878 ms**  self **0.022 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.519 ms**  self **0.012 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.507 ms**  self **0.013 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.437 ms**  self **0.014 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **1.764 ms**  self **0.019 ms**  `module.py:2589`
        - `Module.to` 
          wall **4.555 ms**  self **0.042 ms**  `module.py:1259`
          - `Module._apply` 
            wall **4.513 ms**  self **0.009 ms**  `module.py:930`
            - `Module._apply` 
              wall **2.247 ms**  self **0.014 ms**  `module.py:930`
              - `Module._apply` 
                wall **1.530 ms**  self **0.014 ms**  `module.py:930`
            - `Module._apply` 
              wall **2.246 ms**  self **0.009 ms**  `module.py:930`
              - `Module._apply` 
                wall **1.745 ms**  self **0.007 ms**  `module.py:930`
        - `archive_model_dtypes` 
          wall **4.003 ms**  self **0.732 ms**  `model_management.py:1045`
        - `VAE.model_size` 
          wall **1.897 ms**  self **0.047 ms**  `sd.py:1095`
          - `module_size` 
            wall **1.850 ms**  self **0.049 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **1.801 ms**  self **0.014 ms**  `module.py:2199`
        - `Module.eval` 
          wall **1.831 ms**  self **0.002 ms**  `module.py:2916`
          - `Module.train` 
            wall **1.830 ms**  self **0.007 ms**  `module.py:2894`
      - `validate_qd_adoption` 
        wall **3.420 ms**  self **0.740 ms**  `golden_serial.py:12971`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **32.348 ms**  self **32.348 ms**  `rk_noise_sampler_beta.py:785`
  - `generate_init_noise` 
    wall **19.268 ms**  self **1.738 ms**  `samplers.py:61`
    - `GaussianNoiseGenerator.__call__` 
      wall **16.016 ms**  self **16.014 ms**  `noise_classes.py:386`
  - `LatentGuide.init_guides` 
    wall **12.007 ms**  self **2.696 ms**  `rk_guide_func_beta.py:125`
    - `pad` 
      wall **4.939 ms**  self **4.937 ms**  `functional.py:5761`
  _... 13 more children >= 1 ms omitted_

### `golden_sampling`

- Stage wall: **4,267.430 ms**

- `golden_sampling` 
  wall **4,267.430 ms**  self **4,267.430 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **4,267.373 ms**  self **0.286 ms**  `golden_serial.py:13785`
    - `GoldenSerialRunner.run_closure` 
      wall **4,220.136 ms**  self **0.033 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,219.909 ms**  self **0.060 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,218.983 ms**  self **0.058 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **4,218.801 ms**  self **0.444 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **4,215.273 ms**  self **22.657 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **3,967.539 ms**  self **0.045 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **3,967.350 ms**  self **0.007 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **3,967.343 ms**  self **0.044 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **3,967.048 ms**  self **0.005 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **3,967.038 ms**  self **0.022 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **3,967.016 ms**  self **1.236 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **3,791.834 ms**  self **0.593 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **3,789.311 ms**  self **0.022 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **3,789.289 ms**  self **0.467 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **3,787.387 ms**  self **0.991 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **3,786.354 ms**  self **47.737 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **487.311 ms**  self **0.774 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **486.081 ms**  self **0.282 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **485.413 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **485.404 ms**  self **0.008 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **485.396 ms**  self **0.014 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **485.368 ms**  self **0.011 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **485.357 ms**  self **0.023 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **485.334 ms**  self **0.116 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **475.477 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **475.472 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **475.459 ms**  self **0.155 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **475.305 ms**  self **0.966 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **471.904 ms**  self **0.016 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **471.883 ms**  self **0.078 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **471.805 ms**  self **0.691 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **470.185 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **470.178 ms**  self **0.020 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **470.158 ms**  self **470.158 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.375 ms**  self **0.015 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.359 ms**  self **1.359 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **9.741 ms**  self **0.168 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **9.574 ms**  self **9.342 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **318.180 ms**  self **0.315 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **317.832 ms**  self **0.054 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **317.767 ms**  self **0.005 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **317.762 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **317.758 ms**  self **0.011 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **317.738 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **317.733 ms**  self **0.064 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **317.669 ms**  self **0.015 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **165.030 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **165.027 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **165.016 ms**  self **0.022 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **164.993 ms**  self **0.353 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **156.500 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **156.485 ms**  self **0.012 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **156.473 ms**  self **0.224 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **155.702 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **155.697 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **155.686 ms**  self **155.686 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **7.601 ms**  self **0.029 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **7.506 ms**  self **0.027 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **6.578 ms**  self **6.559 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **152.624 ms**  self **0.230 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **152.394 ms**  self **152.394 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **308.650 ms**  self **0.150 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **308.475 ms**  self **0.072 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **308.392 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **308.386 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **308.382 ms**  self **0.010 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **308.361 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **308.356 ms**  self **0.017 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **308.338 ms**  self **0.016 ms**  `samplers.py:609`
                                                    - `cfg_function` 
                                                      wall **167.730 ms**  self **0.125 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **167.605 ms**  self **167.605 ms**  `noise_injection.py:285`
                                                    - `calc_cond_batch` 
                                                      wall **140.591 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **140.588 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **140.578 ms**  self **0.219 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **140.359 ms**  self **0.667 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **138.567 ms**  self **0.010 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **138.551 ms**  self **0.055 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **138.496 ms**  self **0.173 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **137.651 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **137.643 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **137.632 ms**  self **137.632 ms**  `nodes.py:215`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **307.825 ms**  self **0.138 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **307.660 ms**  self **0.164 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **307.475 ms**  self **0.005 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **307.470 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **307.466 ms**  self **0.007 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **307.451 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **307.446 ms**  self **0.013 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **307.432 ms**  self **0.015 ms**  `samplers.py:609`
                                                    - `cfg_function` 
                                                      wall **175.219 ms**  self **0.087 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **175.131 ms**  self **175.131 ms**  `noise_injection.py:285`
                                                    - `calc_cond_batch` 
                                                      wall **132.198 ms**  self **0.002 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **132.196 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **132.188 ms**  self **0.139 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **132.049 ms**  self **0.630 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **130.161 ms**  self **0.009 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **130.144 ms**  self **0.017 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **130.128 ms**  self **0.153 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **129.392 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **129.385 ms**  self **0.010 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **129.374 ms**  self **129.374 ms**  `nodes.py:215`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **307.763 ms**  self **0.129 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **307.607 ms**  self **0.199 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **307.387 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **307.382 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **307.378 ms**  self **0.007 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **307.364 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **307.359 ms**  self **0.013 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **307.346 ms**  self **0.010 ms**  `samplers.py:609`
                                                    - `cfg_function` 
                                                      wall **175.285 ms**  self **0.038 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **175.247 ms**  self **175.247 ms**  `noise_injection.py:285`
                                                    - `calc_cond_batch` 
                                                      wall **132.051 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **132.048 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **132.040 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **132.017 ms**  self **0.458 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **129.922 ms**  self **0.007 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **129.909 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **129.895 ms**  self **0.100 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **129.225 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **129.221 ms**  self **0.008 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **129.212 ms**  self **129.212 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.103 ms**  self **0.044 ms**  `model_patcher.py:417`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **306.582 ms**  self **0.143 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **306.413 ms**  self **0.106 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **306.290 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **306.283 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **306.279 ms**  self **0.011 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **306.260 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **306.255 ms**  self **0.017 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **306.238 ms**  self **0.021 ms**  `samplers.py:609`
                                                    - `cfg_function` 
                                                      wall **166.596 ms**  self **0.126 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **166.469 ms**  self **166.469 ms**  `noise_injection.py:285`
                                                    - `calc_cond_batch` 
                                                      wall **139.622 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **139.617 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **139.606 ms**  self **0.171 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **139.435 ms**  self **0.591 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **137.715 ms**  self **0.009 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **137.699 ms**  self **0.080 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **137.619 ms**  self **0.127 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **136.905 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **136.899 ms**  self **0.009 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **136.890 ms**  self **136.890 ms**  `nodes.py:215`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **302.508 ms**  self **0.106 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **302.378 ms**  self **0.054 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **302.316 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **302.309 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **302.304 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **302.282 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **302.277 ms**  self **0.017 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **302.260 ms**  self **0.014 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **167.487 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **167.484 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **167.473 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **167.449 ms**  self **0.299 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **164.491 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **164.471 ms**  self **0.012 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **164.458 ms**  self **0.109 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **163.821 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **163.816 ms**  self **0.012 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **163.804 ms**  self **163.804 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.650 ms**  self **0.014 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.635 ms**  self **1.635 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **134.759 ms**  self **0.041 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **134.718 ms**  self **134.525 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **302.230 ms**  self **0.626 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **301.574 ms**  self **0.035 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **301.530 ms**  self **0.005 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **301.525 ms**  self **0.003 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **301.523 ms**  self **0.006 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **301.511 ms**  self **0.004 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **301.508 ms**  self **0.042 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **301.466 ms**  self **0.025 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **151.148 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **151.145 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **151.138 ms**  self **0.022 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **151.116 ms**  self **0.232 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **149.244 ms**  self **0.009 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **149.228 ms**  self **0.013 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **149.215 ms**  self **0.086 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **148.630 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **148.624 ms**  self **0.010 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **148.614 ms**  self **148.614 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.281 ms**  self **0.039 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.191 ms**  self **0.015 ms**  `model_management.py:1748`
                                                    - `cfg_function` 
                                                      wall **150.292 ms**  self **0.076 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **150.216 ms**  self **150.216 ms**  `noise_injection.py:285`
                                    _... 37 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **10.285 ms**  self **0.009 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **10.276 ms**  self **0.038 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **3.408 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **3.402 ms**  self **0.141 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **3.228 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **3.207 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **3.193 ms**  self **0.007 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **3.186 ms**  self **3.186 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.705 ms**  self **0.009 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.695 ms**  self **0.160 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.468 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.458 ms**  self **0.006 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.446 ms**  self **0.006 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.440 ms**  self **1.440 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.605 ms**  self **0.003 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.600 ms**  self **0.116 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.463 ms**  self **0.002 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.448 ms**  self **0.006 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.436 ms**  self **0.004 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.432 ms**  self **1.432 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.599 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.593 ms**  self **0.114 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.430 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.410 ms**  self **0.009 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.395 ms**  self **0.009 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.386 ms**  self **1.386 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.454 ms**  self **0.002 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.451 ms**  self **0.039 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.399 ms**  self **0.001 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.394 ms**  self **0.003 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.389 ms**  self **0.002 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.388 ms**  self **1.387 ms**  `storage.py:262`
              - `_disable_dynamo.<locals>.inner` 
                wall **1.748 ms**  self **0.004 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **1.744 ms**  self **0.009 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **1.733 ms**  self **0.002 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **1.731 ms**  self **0.039 ms**  `random.py:62`
    - `import_module` 
      wall **26.520 ms**  self **26.520 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **14.969 ms**  self **0.046 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **14.923 ms**  self **0.003 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **14.919 ms**  self **0.041 ms**  `copy.py:201`
          - `deepcopy` 
            wall **6.312 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **6.309 ms**  self **0.007 ms**  `copy.py:227`
              - `deepcopy` 
                wall **6.294 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **6.290 ms**  self **0.035 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **6.181 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **6.179 ms**  self **0.011 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **5.022 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **5.020 ms**  self **0.158 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **2.199 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **2.197 ms**  self **0.635 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.803 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.800 ms**  self **0.234 ms**  `copy.py:227`
          - `deepcopy` 
            wall **4.798 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **4.796 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **4.781 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **4.779 ms**  self **0.038 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **4.666 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **4.664 ms**  self **0.010 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **3.512 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **3.509 ms**  self **0.164 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **1.488 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **1.486 ms**  self **0.424 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.103 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.100 ms**  self **0.149 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **1.796 ms**  self **0.044 ms**  `golden_serial.py:9742`
  - `BaseEventLoop.run_until_complete` 
    wall **555.826 ms**  self **0.013 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **555.805 ms**  self **0.045 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **96.481 ms**  self **0.794 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **95.599 ms**  self **95.582 ms**  `events.py:78`
      - `BaseEventLoop._run_once` 
        wall **1.334 ms**  self **0.014 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **1.291 ms**  self **1.291 ms**  `events.py:78`
  - `Thread.run` 
    wall **555.517 ms**  self **0.008 ms**  `threading.py:964`
    - `_worker` 
      wall **555.508 ms**  self **97.345 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **554.772 ms**  self **96.916 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **458.153 ms**  self **0.014 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **457.821 ms**  self **0.021 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **457.800 ms**  self **0.011 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **457.789 ms**  self **0.011 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **457.778 ms**  self **0.331 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **344.521 ms**  self **0.199 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **302.359 ms**  self **0.032 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **250.183 ms**  self **250.183 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._read_message` 
                    wall **51.092 ms**  self **51.061 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **11.718 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **10.442 ms**  self **10.424 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **10.894 ms**  self **0.020 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **8.590 ms**  self **8.564 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **1.583 ms**  self **0.028 ms**  `golden_source_threads.py:1044`
                - `GoldenQDTransport.publish` 
                  wall **3.847 ms**  self **0.009 ms**  `golden_qd_transport.py:3099`
                  - `TransportDispatcher.publish` 
                    wall **3.819 ms**  self **3.774 ms**  `golden_qd_transport.py:2153`
                - `SourceThreadProcess.claim_ready` 
                  wall **3.020 ms**  self **0.020 ms**  `golden_source_threads.py:1175`
                  - `_FileLock.__enter__` 
                    wall **2.817 ms**  self **2.817 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess.wait_ready` 
                  wall **2.642 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **1.250 ms**  self **1.230 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.plan_once` 
                  wall **2.642 ms**  self **0.200 ms**  `golden_source_threads.py:918`
                  - `SourceThreadProcess._read_message` 
                    wall **1.988 ms**  self **1.974 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **2.285 ms**  self **0.012 ms**  `golden_source_threads.py:1129`
                _... 2 more children >= 1 ms omitted_
              - `GoldenModelTransport._views` 
                wall **76.698 ms**  self **76.698 ms**  `golden_model_transport.py:2042`
              - `GoldenModelTransport.inspect` 
                wall **26.702 ms**  self **0.024 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **26.335 ms**  self **25.857 ms**  `golden_model_transport.py:327`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **3.220 ms**  self **0.068 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **2.868 ms**  self **0.011 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **2.847 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **2.835 ms**  self **0.005 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **2.827 ms**  self **2.824 ms**  `threading.py:288`
              - `GpuDestinationPool.acquire` 
                wall **2.163 ms**  self **0.022 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **2.134 ms**  self **2.054 ms**  `golden_model_transport.py:161`
              - `SourceThreadProcess.wait_quiescent` 
                wall **1.406 ms**  self **0.013 ms**  `golden_source_threads.py:1228`
              - `SourceThreadProcess.snapshot` 
                wall **1.015 ms**  self **0.087 ms**  `golden_source_threads.py:1240`
    - `BaseEventLoop._run_once` 
      wall **457.856 ms**  self **0.014 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **457.662 ms**  self **457.660 ms**  `selectors.py:451`
    - `sample_custom` 
      wall **173.928 ms**  self **2.116 ms**  `sample.py:86`
      - `sample` 
        wall **171.806 ms**  self **0.037 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **171.679 ms**  self **0.076 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **171.425 ms**  self **0.018 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **171.408 ms**  self **0.071 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **170.689 ms**  self **0.005 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **170.679 ms**  self **0.022 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **170.657 ms**  self **1.676 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **119.220 ms**  self **0.007 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **119.210 ms**  self **0.007 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **119.203 ms**  self **0.040 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **119.067 ms**  self **0.080 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **117.868 ms**  self **0.015 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **117.835 ms**  self **0.003 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **117.832 ms**  self **0.171 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **117.611 ms**  self **4.288 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **33.739 ms**  self **3.024 ms**  `model_patcher.py:945`
                                    - `Module.named_buffers` 
                                      wall **2.397 ms**  self **0.003 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **2.394 ms**  self **0.481 ms**  `module.py:2650`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **1.475 ms**  self **0.010 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **1.414 ms**  self **1.146 ms**  `model_patcher.py:899`
                    - `CFGGuider.inner_sample` 
                      wall **49.594 ms**  self **47.950 ms**  `samplers.py:1220`
                      - `WrapperExecutor.execute` 
                        wall **1.129 ms**  self **0.021 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.108 ms**  self **0.102 ms**  `samplers.py:983`
    - `prepare_sampling` 
      wall **173.807 ms**  self **0.007 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **173.796 ms**  self **0.004 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **173.792 ms**  self **0.016 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **173.700 ms**  self **0.059 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **172.593 ms**  self **0.018 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **172.557 ms**  self **0.003 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **172.554 ms**  self **0.233 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **172.265 ms**  self **5.104 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **36.038 ms**  self **4.955 ms**  `model_patcher.py:945`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **5.773 ms**  self **1.445 ms**  `model_patcher.py:1842`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **2.667 ms**  self **0.180 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **2.413 ms**  self **0.061 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **1.968 ms**  self **1.966 ms**  `__init__.py:350`
                    - `Module.named_buffers` 
                      wall **2.667 ms**  self **0.004 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **2.663 ms**  self **0.491 ms**  `module.py:2650`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.581 ms**  self **0.051 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.474 ms**  self **0.033 ms**  `model_patcher.py:899`
                        - `cast_to_device` 
                          wall **1.219 ms**  self **0.003 ms**  `model_management.py:1555`
                          - `cast_to` 
                            wall **1.206 ms**  self **1.206 ms**  `model_management.py:1527`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.453 ms**  self **0.160 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.234 ms**  self **0.504 ms**  `model_patcher.py:899`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.365 ms**  self **0.183 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.090 ms**  self **0.506 ms**  `model_patcher.py:899`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.343 ms**  self **0.410 ms**  `model_patcher.py:1947`
                    _... 4 more children >= 1 ms omitted_
    - `_vae_load_with_worker_stage` 
      wall **95.536 ms**  self **0.005 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **95.527 ms**  self **0.236 ms**  `golden_serial.py:14310`
        - `VAE.__init__` 
          wall **89.580 ms**  self **59.419 ms**  `sd.py:487`
          - `Module.load_state_dict` 
            wall **17.590 ms**  self **0.104 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **17.486 ms**  self **0.022 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **9.279 ms**  self **0.027 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **7.008 ms**  self **0.028 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.595 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.041 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.093 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.523 ms**  self **0.016 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.076 ms**  self **0.018 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.666 ms**  self **0.018 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **7.666 ms**  self **0.027 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.880 ms**  self **0.021 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.878 ms**  self **0.022 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.519 ms**  self **0.012 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.507 ms**  self **0.013 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.437 ms**  self **0.014 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.764 ms**  self **0.019 ms**  `module.py:2589`
          - `Module.to` 
            wall **4.555 ms**  self **0.042 ms**  `module.py:1259`
            - `Module._apply` 
              wall **4.513 ms**  self **0.009 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.247 ms**  self **0.014 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.530 ms**  self **0.014 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.246 ms**  self **0.009 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.745 ms**  self **0.007 ms**  `module.py:930`
          - `archive_model_dtypes` 
            wall **4.003 ms**  self **0.732 ms**  `model_management.py:1045`
          - `VAE.model_size` 
            wall **1.897 ms**  self **0.047 ms**  `sd.py:1095`
            - `module_size` 
              wall **1.850 ms**  self **0.049 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **1.801 ms**  self **0.014 ms**  `module.py:2199`
          - `Module.eval` 
            wall **1.831 ms**  self **0.002 ms**  `module.py:2916`
            - `Module.train` 
              wall **1.830 ms**  self **0.007 ms**  `module.py:2894`
        - `validate_qd_adoption` 
          wall **3.420 ms**  self **0.740 ms**  `golden_serial.py:12971`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **32.348 ms**  self **32.348 ms**  `rk_noise_sampler_beta.py:785`
    - `generate_init_noise` 
      wall **19.268 ms**  self **1.738 ms**  `samplers.py:61`
      - `GaussianNoiseGenerator.__call__` 
        wall **16.016 ms**  self **16.014 ms**  `noise_classes.py:386`
    - `LatentGuide.init_guides` 
      wall **12.007 ms**  self **2.696 ms**  `rk_guide_func_beta.py:125`
      - `pad` 
        wall **4.939 ms**  self **4.937 ms**  `functional.py:5761`
    _... 13 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **95.556 ms**  self **0.006 ms**  `golden_serial.py:15614`
  - `_overlap_stage_call` 
    wall **1.278 ms**  self **0.007 ms**  `golden_serial.py:15614`

### `golden_sampler_tail`

- Stage wall: **0.045 ms**

_Nothing below the stage body reached the threshold._

### `golden_vae_decode`

- Stage wall: **719.073 ms**

- `golden_vae_decode` 
  wall **719.073 ms**  self **0.214 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **719.054 ms**  self **0.053 ms**  `golden_serial.py:14523`
    - `GoldenSerialRunner.run_closure` 
      wall **718.754 ms**  self **0.023 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **718.679 ms**  self **0.038 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **718.403 ms**  self **0.016 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **718.246 ms**  self **0.027 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **718.219 ms**  self **635.965 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **73.028 ms**  self **0.082 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **65.595 ms**  self **0.017 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **65.545 ms**  self **0.003 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **65.542 ms**  self **0.079 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **65.433 ms**  self **1.733 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **13.617 ms**  self **1.325 ms**  `model_patcher.py:945`
                        - `Module.named_buffers` 
                          wall **1.184 ms**  self **0.003 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.181 ms**  self **0.212 ms**  `module.py:2650`
                - `LoadedModel.model_memory_required` 
                  wall **5.451 ms**  self **0.004 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **5.446 ms**  self **0.003 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **5.443 ms**  self **0.802 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **4.641 ms**  self **0.139 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **4.502 ms**  self **0.027 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.236 ms**  self **0.022 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.468 ms**  self **0.017 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.227 ms**  self **0.024 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.837 ms**  self **0.016 ms**  `module.py:2199`
                - `free_memory` 
                  wall **1.304 ms**  self **0.122 ms**  `model_management.py:863`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **8.313 ms**  self **8.313 ms**  `sd.py:506`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **718.779 ms**  self **718.779 ms**  `full_execution_trace.py:330`

### `golden_output`

- Stage wall: **243.623 ms**

- `golden_output` 
  wall **243.623 ms**  self **243.623 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **243.557 ms**  self **15.963 ms**  `golden_serial.py:14670`
    - `Image.save` 
      wall **203.977 ms**  self **0.055 ms**  `Image.py:2592`
      - `_save` 
        wall **195.244 ms**  self **0.050 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **195.164 ms**  self **0.022 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **195.139 ms**  self **191.120 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **8.624 ms**  self **8.624 ms**  `Image.py:429`
    - `fromarray` 
      wall **12.822 ms**  self **8.118 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **4.704 ms**  self **0.012 ms**  `Image.py:3288`
        - `frombytes` 
          wall **4.688 ms**  self **0.035 ms**  `Image.py:3242`
          - `new` 
            wall **3.141 ms**  self **3.105 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.508 ms**  self **1.474 ms**  `Image.py:925`
    - `clip` 
      wall **7.532 ms**  self **0.011 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **7.520 ms**  self **0.025 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **7.495 ms**  self **7.495 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **2.375 ms**  self **0.012 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **2.362 ms**  self **2.362 ms**  `output_durability.py:73`
