# Golden stage decision report

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **909,895**

Tree floor: **1 ms**   Function rollup floor: **1 ms** total inclusive

## 1. Critical path and stage overlap

Sum of stage walls: **19,229.742 ms**   Timeline union: **15,347.814 ms**   Span: **15,360.032 ms**

Sum exceeds the union by **3,881.928 ms** -- that gap is the overlap the schedule is buying.

| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |
|:--|---:|---:|---:|:--|:--|
| `golden_restore` | 0.4 | 0.0 | 0.4 | 0.0% | `#` |
| `golden_request_setup` | 2.9 | 0.0 | 2.9 | 0.0% | `#` |
| `golden_clip_load` | 4,605.2 | 4,600.3 | 4.9 | 99.9% | `######################` |
| `golden_clip_forward` | 4,122.7 | 1,067.5 | 3,055.1 | 25.9% | `                      ###################` |
| `golden_unet_load` | 3,056.9 | 0.0 | 3,056.9 | 0.0% | `                      ##############` |
| `golden_sampler_prepare` | 79.9 | 76.8 | 3.1 | 96.1% | `                                         #` |
| `golden_vae_load` | 826.0 | 0.0 | 826.0 | 0.0% | `                                         ####` |
| `golden_sampling` | 5,247.8 | 4,416.0 | 831.8 | 84.1% | `                                         #########################` |
| `golden_sampler_tail` | 0.1 | 0.0 | 0.1 | 0.0% | `                                                                  #` |
| `golden_vae_decode` | 1,013.8 | 1,006.1 | 7.7 | 99.2% | `                                                                  #####` |
| `golden_output` | 274.0 | 268.8 | 5.2 | 98.1% | `                                                                       #` |

_Uncontended_ is the time during a stage when no other stage was running. That portion is protected: nothing else could absorb it. Overlapped time may be hidden by a longer sibling, so reducing it may not move root wall.

## 2. Function rollup across the whole request

`total incl ms` sums each call's wall, so a function called 24 times at 3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall contains its callees, so **totals are not additive down a call tree** -- `total self ms` is the non-overlapping part.

| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |
|---:|---:|---:|---:|---:|:--|:--|:--|
| 25,600.952 | 59 | 433.914 | 4,746.637 | 1.393 | `WrapperExecutor.execute` | `patcher_extension.py:108` | 2 |
| 16,366.308 | 526 | 31.115 | 3,826.104 | 1.109 | `Module._wrapped_call_impl` | `module.py:1779` | 3 |
| 16,365.202 | 526 | 31.113 | 3,826.093 | 2.366 | `Module._call_impl` | `module.py:1787` | 3 |
| 10,398.358 | 32 | 324.949 | 5,191.038 | 1.236 | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` | 6 |
| 10,396.195 | 5 | 2,079.239 | 5,191.297 | 0.221 | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` | 5 |
| 10,374.793 | 32 | 324.212 | 5,189.998 | 1.461 | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` | 6 |
| 8,108.983 | 3 | 2,702.994 | 4,481.081 | 0.053 | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` | 3 |
| 8,108.929 | 3 | 2,702.976 | 4,481.053 | 0.246 | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` | 3 |
| 8,108.683 | 3 | 2,702.894 | 4,480.940 | 1.877 | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` | 3 |
| 6,070.528 | 3 | 2,023.509 | 2,858.671 | 9.676 | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` | 3 |
| 5,889.029 | 3 | 1,963.010 | 2,968.070 | 0.309 | `_WorkItem.run` | `thread.py:53` | 3 |
| 5,810.978 | 309 | 18.806 | 481.868 | 4.214 | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` | 3 |
| 5,497.819 | 316 | 17.398 | 253.565 | 5,490.968 | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` | 3 |
| 5,357.018 | 3 | 1,785.673 | 4,501.895 | 0.034 | `Thread.run` | `threading.py:964` | 2 |
| 5,330.631 | 2 | 2,665.316 | 4,501.880 | 2,409.649 | `_worker` | `thread.py:69` | 2 |
| 5,247.769 | 1 | 5,247.769 | 5,247.769 | 0.198 | `golden_sampling` | `golden_serial.py:13785` | 1 |
| 5,189.764 | 1 | 5,189.764 | 5,189.764 | 0.267 | `ClownsharKSampler_Beta.main` | `samplers.py:1745` | 1 |
| 5,184.886 | 1 | 5,184.886 | 5,184.886 | 39.299 | `SharkSampler.main` | `samplers.py:153` | 1 |
| 5,017.503 | 2 | 2,508.751 | 4,746.889 | 0.212 | `CFGGuider.sample` | `samplers.py:1276` | 2 |
| 5,016.920 | 2 | 2,508.460 | 4,746.630 | 0.126 | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` | 2 |
| 5,015.037 | 2 | 2,507.518 | 4,746.195 | 0.011 | `WrapperExecutor.__call__` | `patcher_extension.py:103` | 2 |
| 5,014.957 | 2 | 2,507.479 | 4,746.176 | 8.547 | `CFGGuider.outer_sample` | `samplers.py:1240` | 2 |
| 4,601.363 | 2 | 2,300.681 | 4,496.409 | 0.720 | `golden_clip_load` | `golden_serial.py:11497` | 1 |
| 4,481.199 | 1 | 4,481.199 | 4,481.199 | 4,481.199 | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` | 1 |
| 4,481.139 | 1 | 4,481.139 | 4,481.139 | 0.035 | `_read_golden_m2_clip` | `golden_serial.py:11462` | 1 |
| 4,481.099 | 1 | 4,481.099 | 4,481.099 | 0.019 | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` | 1 |
| 4,472.445 | 2 | 2,236.222 | 4,411.133 | 59.829 | `CFGGuider.inner_sample` | `samplers.py:1220` | 2 |
| 4,408.519 | 2 | 2,204.260 | 4,407.319 | 0.191 | `KSAMPLER.sample` | `samplers.py:983` | 2 |
| 4,407.136 | 74 | 59.556 | 4,404.869 | 1.142 | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` | 2 |
| 4,404.620 | 2 | 2,202.310 | 4,404.619 | 56.831 | `sample_rk_beta` | `rk_sampler_beta.py:110` | 2 |
| 4,122.601 | 1 | 4,122.601 | 4,122.601 | 0.222 | `golden_clip_forward` | `golden_serial.py:12452` | 1 |
| 4,109.563 | 1 | 4,109.563 | 4,109.563 | 0.024 | `CLIPTextEncode.encode` | `nodes.py:73` | 1 |
| 4,085.208 | 1 | 4,085.208 | 4,085.208 | 0.026 | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` | 1 |
| 4,085.183 | 1 | 4,085.183 | 4,085.183 | 0.045 | `CLIP.encode_from_tokens` | `sd.py:396` | 1 |
| 3,886.607 | 14 | 277.615 | 2,841.814 | 3.309 | `BaseEventLoop._run_once` | `base_events.py:1845` | 5 |
| 3,854.003 | 1 | 3,854.003 | 3,854.003 | 0.028 | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` | 1 |
| 3,853.974 | 1 | 3,853.974 | 3,853.974 | 27.806 | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` | 1 |
| 3,826.109 | 1 | 3,826.109 | 3,826.109 | 0.004 | `SDClipModel.encode` | `sd1_clip.py:305` | 1 |
| 3,826.062 | 1 | 3,826.062 | 3,826.062 | 0.073 | `SDClipModel.forward` | `sd1_clip.py:260` | 1 |
| 3,667.950 | 1 | 3,667.950 | 3,667.950 | 0.009 | `BaseLlama.forward` | `llama.py:998` | 1 |
| 3,667.880 | 1 | 3,667.880 | 3,667.880 | 441.484 | `Llama2_.forward` | `llama.py:824` | 1 |
| 3,657.002 | 17 | 215.118 | 550.548 | 5.374 | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` | 1 |
| 3,650.628 | 17 | 214.743 | 549.263 | 2.566 | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` | 1 |
| 3,646.539 | 17 | 214.502 | 547.163 | 0.125 | `KSamplerX0Inpaint.__call__` | `samplers.py:634` | 1 |
| 3,646.415 | 17 | 214.495 | 547.146 | 0.098 | `CFGGuider.__call__` | `samplers.py:1207` | 1 |
| 3,646.316 | 17 | 214.489 | 547.137 | 0.237 | `CFGGuider.outer_predict_noise` | `samplers.py:1210` | 1 |
| 3,645.788 | 17 | 214.458 | 547.093 | 0.392 | `SharkGuider.predict_noise` | `samplers.py:99` | 1 |
| 3,645.396 | 17 | 214.435 | 547.059 | 0.319 | `sampling_function` | `samplers.py:609` | 1 |
| 3,627.936 | 2 | 1,813.968 | 2,967.684 | 0.034 | `thread_traced.<locals>._run` | `full_execution_trace.py:276` | 2 |
| 3,533.744 | 17 | 207.867 | 532.830 | 0.069 | `calc_cond_batch` | `samplers.py:208` | 1 |
| 3,533.677 | 17 | 207.863 | 532.824 | 0.103 | `_calc_cond_batch_outer` | `samplers.py:214` | 1 |
| 3,531.681 | 17 | 207.746 | 532.760 | 18.200 | `_calc_cond_batch` | `samplers.py:221` | 1 |
| 3,509.437 | 16 | 219.340 | 2,841.538 | 3,509.430 | `EpollSelector.select` | `selectors.py:451` | 5 |
| 3,448.752 | 17 | 202.868 | 523.569 | 0.174 | `BaseModel.apply_model` | `model_base.py:204` | 1 |
| 3,448.137 | 17 | 202.832 | 523.525 | 11.732 | `BaseModel._apply_model` | `model_base.py:211` | 1 |
| 3,425.780 | 17 | 201.516 | 519.349 | 3,425.780 | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` | 1 |
| 2,842.360 | 1 | 2,842.360 | 2,842.360 | 0.371 | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` | 1 |
| 2,469.671 | 1 | 2,469.671 | 2,469.671 | 0.878 | `Llama2_.compute_freqs_cis` | `llama.py:815` | 1 |
| 2,468.793 | 1 | 2,468.793 | 2,468.793 | 218.562 | `precompute_freqs_cis` | `llama.py:445` | 1 |
| 2,259.646 | 1 | 2,259.646 | 2,259.646 | 0.289 | `_start_clip_skeleton_overlap.<locals>.build` | `golden_serial.py:2341` | 1 |

## 3. Per-stage call trees

Depth is uncapped; the wall floor limits it. Breadth is capped at 8 children plus any child at or above 10% of its parent.

### `golden_restore`

- Stage wall: **0.437 ms**

_Nothing below the stage body reached the threshold._

### `golden_request_setup`

- Stage wall: **2.898 ms**

- `golden_request_setup` 
  wall **2.898 ms**  self **2.898 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **2.874 ms**  self **0.082 ms**  `golden_serial.py:9977`

### `golden_clip_load`

- Stage wall: **4,605.187 ms**

- `golden_clip_load` 
  wall **4,605.187 ms**  self **19.827 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **4,501.895 ms**  self **0.015 ms**  `threading.py:964`
    - `_worker` 
      wall **4,501.880 ms**  self **2,241.909 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **2,259.960 ms**  self **0.275 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **2,259.646 ms**  self **0.289 ms**  `golden_serial.py:2341`
          - `_clip_meta_state_dict_from_header` 
            wall **1,632.070 ms**  self **1,621.078 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **10.689 ms**  self **8.342 ms**  `clip_qd_reader.py:300`
              - `loads` 
                wall **1.525 ms**  self **0.006 ms**  `__init__.py:299`
                - `JSONDecoder.decode` 
                  wall **1.518 ms**  self **0.012 ms**  `decoder.py:332`
                  - `JSONDecoder.raw_decode` 
                    wall **1.506 ms**  self **1.506 ms**  `decoder.py:343`
          - `load_text_encoder_state_dicts` 
            wall **627.241 ms**  self **0.379 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **626.157 ms**  self **0.214 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **519.879 ms**  self **0.014 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **519.865 ms**  self **0.071 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **519.794 ms**  self **4.124 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **515.670 ms**  self **0.733 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **494.824 ms**  self **1.046 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **452.608 ms**  self **7.860 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **444.076 ms**  self **298.102 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **97.945 ms**  self **19.962 ms**  `__init__.py:274`
                              - `loads` 
                                wall **77.983 ms**  self **0.009 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **77.974 ms**  self **0.022 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **77.953 ms**  self **77.953 ms**  `decoder.py:343`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **19.398 ms**  self **19.398 ms**  `tokenization_qwen2.py:174`
                            - `PreTrainedTokenizer.__init__` 
                              wall **16.705 ms**  self **1.126 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **14.993 ms**  self **4.881 ms**  `tokenization_utils.py:512`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **6.805 ms**  self **6.770 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **2.932 ms**  self **1.206 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **1.702 ms**  self **1.670 ms**  `tokenization_qwen2.py:215`
                            - `compile` 
                              wall **11.491 ms**  self **0.049 ms**  `_main.py:359`
                              - `_compile` 
                                wall **11.441 ms**  self **0.247 ms**  `_main.py:460`
                                - `_parse_pattern` 
                                  wall **5.755 ms**  self **0.035 ms**  `_regex_core.py:452`
                                  - `parse_sequence` 
                                    wall **4.810 ms**  self **0.035 ms**  `_regex_core.py:462`
                                    - `parse_paren` 
                                      wall **4.761 ms**  self **0.013 ms**  `_regex_core.py:850`
                                      - `parse_flags_subpattern` 
                                        wall **4.748 ms**  self **0.022 ms**  `_regex_core.py:1185`
                                        - `parse_subpattern` 
                                          wall **4.669 ms**  self **0.012 ms**  `_regex_core.py:1166`
                                          - `_parse_pattern` 
                                            wall **4.636 ms**  self **0.025 ms**  `_regex_core.py:452`
                                            - `parse_sequence` 
                                              wall **4.416 ms**  self **0.018 ms**  `_regex_core.py:462`
                                              - `Character.__init__` 
                                                wall **4.380 ms**  self **0.008 ms**  `_regex_core.py:2588`
                                                - `Flag.__and__` 
                                                  wall **4.372 ms**  self **0.003 ms**  `enum.py:1509`
                                                  - `EnumType.__call__` 
                                                    wall **4.370 ms**  self **0.002 ms**  `enum.py:686`
                                                    - `Enum.__new__` 
                                                      wall **4.368 ms**  self **4.368 ms**  `enum.py:1091`
                                - `Branch.pack_characters` 
                                  wall **4.443 ms**  self **0.003 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **4.440 ms**  self **0.010 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **4.391 ms**  self **0.020 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **4.275 ms**  self **0.023 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **4.224 ms**  self **0.005 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **4.220 ms**  self **4.220 ms**  `_regex_core.py:362`
                        - `load` 
                          wall **35.192 ms**  self **35.140 ms**  `__init__.py:274`
                        - `cached_file` 
                          wall **1.708 ms**  self **0.007 ms**  `hub.py:263`
                          - `cached_files` 
                            wall **1.701 ms**  self **1.693 ms**  `hub.py:326`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **17.853 ms**  self **17.853 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **1.759 ms**  self **1.729 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **58.368 ms**  self **0.007 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **58.362 ms**  self **0.218 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **58.144 ms**  self **0.072 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **57.959 ms**  self **0.034 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **57.925 ms**  self **0.543 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **48.440 ms**  self **0.042 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **48.346 ms**  self **1.096 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **38.447 ms**  self **0.137 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **2.351 ms**  self **0.012 ms**  `llama.py:654`
                                - `RMSNorm.__init__` 
                                  wall **1.644 ms**  self **1.596 ms**  `llama.py:430`
                              - `TransformerBlock.__init__` 
                                wall **2.333 ms**  self **0.015 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.986 ms**  self **0.066 ms**  `llama.py:512`
                                  - `RMSNorm.__init__` 
                                    wall **1.480 ms**  self **1.416 ms**  `llama.py:430`
                              - `TransformerBlock.__init__` 
                                wall **2.045 ms**  self **0.024 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.970 ms**  self **0.027 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.059 ms**  self **0.031 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **1.597 ms**  self **0.015 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.056 ms**  self **0.021 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **1.487 ms**  self **0.054 ms**  `llama.py:654`
                                - `Attention.__init__` 
                                  wall **1.010 ms**  self **0.092 ms**  `llama.py:512`
                              - `TransformerBlock.__init__` 
                                wall **1.434 ms**  self **0.014 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.367 ms**  self **0.013 ms**  `llama.py:654`
                              _... 5 more children >= 1 ms omitted_
                            - `disable_weight_init.Embedding.__init__` 
                              wall **8.325 ms**  self **0.151 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **8.012 ms**  self **8.012 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **8.778 ms**  self **0.109 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **5.600 ms**  self **0.004 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **5.596 ms**  self **0.009 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **5.573 ms**  self **0.008 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **5.432 ms**  self **0.035 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **39.043 ms**  self **1.547 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **32.852 ms**  self **0.030 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **32.820 ms**  self **0.032 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **32.786 ms**  self **0.122 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **32.664 ms**  self **0.039 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **32.126 ms**  self **0.025 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **30.484 ms**  self **0.180 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.244 ms**  self **0.022 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.231 ms**  self **0.037 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.216 ms**  self **0.021 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.122 ms**  self **0.018 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.114 ms**  self **0.019 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.066 ms**  self **0.020 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.034 ms**  self **0.017 ms**  `module.py:2589`
              - `archive_model_dtypes` 
                wall **6.650 ms**  self **1.158 ms**  `model_management.py:1045`
              - `ModelPatcherDynamic.__init__` 
                wall **1.354 ms**  self **0.048 ms**  `model_patcher.py:1757`
  - `golden_clip_load` 
    wall **4,496.409 ms**  self **0.296 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **4,481.139 ms**  self **0.035 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **4,481.099 ms**  self **0.019 ms**  `golden_model_transport.py:1087`
        - `GoldenModelTransport._load_sync` 
          wall **4,481.081 ms**  self **0.027 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **4,481.053 ms**  self **0.113 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **4,480.940 ms**  self **0.611 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **2,802.519 ms**  self **3.379 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **481.868 ms**  self **0.038 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **253.565 ms**  self **253.565 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._read_message` 
                    wall **220.520 ms**  self **220.488 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._recover_ready_from_table` 
                    wall **4.994 ms**  self **0.052 ms**  `golden_source_threads.py:1100`
                    - `_FileLock.__exit__` 
                      wall **2.569 ms**  self **2.569 ms**  `golden_source_threads.py:501`
                    - `_FileLock.__enter__` 
                      wall **2.344 ms**  self **2.344 ms**  `golden_source_threads.py:494`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.352 ms**  self **0.003 ms**  `golden_source_threads.py:1009`
                    - `Popen.poll` 
                      wall **1.349 ms**  self **0.003 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.346 ms**  self **1.346 ms**  `subprocess.py:1966`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.251 ms**  self **0.007 ms**  `golden_source_threads.py:1009`
                    - `Popen.poll` 
                      wall **1.244 ms**  self **0.003 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.241 ms**  self **1.241 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **252.574 ms**  self **0.040 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **250.381 ms**  self **250.381 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **218.585 ms**  self **0.019 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **217.936 ms**  self **217.912 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **97.811 ms**  self **0.016 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **96.476 ms**  self **96.449 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **75.907 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **72.599 ms**  self **72.575 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **2.582 ms**  self **0.044 ms**  `golden_source_threads.py:1044`
                    - `_FileLock.__exit__` 
                      wall **1.283 ms**  self **1.283 ms**  `golden_source_threads.py:501`
                    - `_FileLock.__enter__` 
                      wall **1.229 ms**  self **1.229 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess.wait_ready` 
                  wall **75.251 ms**  self **0.021 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **72.817 ms**  self **72.794 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **2.005 ms**  self **0.036 ms**  `golden_source_threads.py:1044`
                    - `_FileLock.__enter__` 
                      wall **1.831 ms**  self **1.831 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess.wait_ready` 
                  wall **71.715 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **70.891 ms**  self **70.862 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **42.437 ms**  self **0.014 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **41.994 ms**  self **41.934 ms**  `golden_source_threads.py:900`
                _... 113 more children >= 1 ms omitted_
              - `GoldenModelTransport.inspect` 
                wall **1,609.583 ms**  self **0.043 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **1,608.957 ms**  self **1,608.381 ms**  `golden_model_transport.py:327`
              - `collect_placement_telemetry` 
                wall **29.725 ms**  self **0.011 ms**  `source_latency_telemetry.py:512`
                - `_collect_placement_telemetry_uncached` 
                  wall **29.714 ms**  self **14.431 ms**  `source_latency_telemetry.py:424`
                  - `_gpu_telemetry` 
                    wall **11.484 ms**  self **0.142 ms**  `source_latency_telemetry.py:359`
                    - `nvmlDeviceGetClockInfo` 
                      wall **5.555 ms**  self **5.544 ms**  `pynvml.py:3674`
                    - `nvmlDeviceGetPowerUsage` 
                      wall **1.984 ms**  self **1.967 ms**  `pynvml.py:3962`
                    - `nvmlDeviceGetPerformanceState` 
                      wall **1.222 ms**  self **1.198 ms**  `pynvml.py:3914`
                    - `nvmlDeviceGetCurrPcieLinkGeneration` 
                      wall **1.123 ms**  self **1.096 ms**  `pynvml.py:4609`
                  - `_reader_threads` 
                    wall **2.570 ms**  self **1.608 ms**  `source_latency_telemetry.py:290`
              - `GoldenModelTransport._views` 
                wall **16.622 ms**  self **16.622 ms**  `golden_model_transport.py:2042`
              - `SourceThreadProcess.snapshot` 
                wall **5.746 ms**  self **0.641 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **4.114 ms**  self **0.458 ms**  `golden_source_threads.py:597`
              - `SourceThreadProcess.snapshot` 
                wall **5.276 ms**  self **0.556 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **4.043 ms**  self **0.428 ms**  `golden_source_threads.py:597`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **3.931 ms**  self **0.134 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **2.079 ms**  self **0.021 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **2.047 ms**  self **0.006 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **2.038 ms**  self **0.005 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **2.031 ms**  self **2.028 ms**  `threading.py:288`
              - `GpuDestinationPool.acquire` 
                wall **2.861 ms**  self **0.050 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **2.803 ms**  self **2.659 ms**  `golden_model_transport.py:161`
              _... 1 more children >= 1 ms omitted_
    - `GoldenTelemetryRecorder.event` 
      wall **9.425 ms**  self **0.007 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **9.418 ms**  self **0.010 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **9.408 ms**  self **0.003 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **9.405 ms**  self **0.036 ms**  `copy.py:227`
            - `deepcopy` 
              wall **9.277 ms**  self **0.002 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **9.274 ms**  self **0.012 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **7.987 ms**  self **0.003 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **7.983 ms**  self **0.271 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **4.212 ms**  self **0.004 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **4.207 ms**  self **1.042 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.469 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_dict` 
                        wall **1.467 ms**  self **0.154 ms**  `copy.py:227`
    - `_start_clip_skeleton_overlap` 
      wall **2.184 ms**  self **0.050 ms**  `golden_serial.py:2336`
      - `ThreadPoolExecutor.submit` 
        wall **2.039 ms**  self **0.019 ms**  `thread.py:161`
        - `ThreadPoolExecutor._adjust_thread_count` 
          wall **2.007 ms**  self **0.024 ms**  `thread.py:180`
          - `Thread.start` 
            wall **1.933 ms**  self **0.415 ms**  `threading.py:938`
            - `Event.wait` 
              wall **1.518 ms**  self **0.007 ms**  `threading.py:604`
              - `Condition.wait` 
                wall **1.507 ms**  self **1.503 ms**  `threading.py:288`
  - `golden.clip_load.source_open_read` 
    wall **4,481.199 ms**  self **4,481.199 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **104.954 ms**  self **0.424 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **66.098 ms**  self **1.335 ms**  `golden_serial.py:13060`
      - `validate_qd_adoption` 
        wall **7.990 ms**  self **1.594 ms**  `golden_serial.py:12971`
        - `Module.named_buffers` 
          wall **3.088 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **3.085 ms**  self **0.487 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **7.479 ms**  self **0.239 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.682 ms**  self **0.004 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.678 ms**  self **0.468 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **7.267 ms**  self **0.312 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.694 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.691 ms**  self **0.484 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.802 ms**  self **0.239 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.530 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.527 ms**  self **0.474 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.634 ms**  self **0.224 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.806 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.804 ms**  self **0.472 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.617 ms**  self **0.221 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.266 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.264 ms**  self **0.463 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.243 ms**  self **0.229 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.052 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.051 ms**  self **0.445 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **28.623 ms**  self **0.468 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **23.525 ms**  self **0.009 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **23.514 ms**  self **0.016 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **23.497 ms**  self **0.111 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **23.386 ms**  self **0.021 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **22.578 ms**  self **0.022 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **21.192 ms**  self **0.095 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.384 ms**  self **0.014 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.175 ms**  self **0.027 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **2.728 ms**  self **0.007 ms**  `module.py:2589`
                        - `disable_weight_init.Linear._load_from_state_dict` 
                          wall **2.719 ms**  self **0.002 ms**  `ops.py:544`
                          - `disable_weight_init._lazy_load_from_state_dict` 
                            wall **2.717 ms**  self **0.023 ms**  `ops.py:494`
                            - `Module.__setattr__` 
                              wall **2.689 ms**  self **0.004 ms**  `module.py:1976`
                              - `Module.register_parameter` 
                                wall **2.684 ms**  self **2.683 ms**  `module.py:592`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.307 ms**  self **0.017 ms**  `module.py:2589`
    - `_clip_compute_identity` 
      wall **8.065 ms**  self **0.026 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **7.932 ms**  self **1.710 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **2.591 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.588 ms**  self **0.483 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **66.153 ms**  self **66.153 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **28.654 ms**  self **28.654 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **26.364 ms**  self **0.011 ms**  `threading.py:964`
    - `GoldenModelTransport.begin_layout_preresolve.<locals>.resolve` 
      wall **26.353 ms**  self **0.011 ms**  `golden_model_transport.py:1030`
      - `GoldenModelTransport.inspect` 
        wall **26.327 ms**  self **0.049 ms**  `golden_model_transport.py:999`
        - `_parse_layout` 
          wall **19.630 ms**  self **18.558 ms**  `golden_model_transport.py:327`
        - `_file_identity` 
          wall **6.648 ms**  self **6.648 ms**  `golden_model_transport.py:297`
  - `golden.clip_load.compute_ready_proof` 
    wall **8.082 ms**  self **8.082 ms**  `full_execution_trace.py:330`
  _... 1 more children >= 1 ms omitted_

### `golden_clip_forward`

- Stage wall: **4,122.662 ms**

- `golden_clip_forward` 
  wall **4,122.662 ms**  self **4,122.662 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **4,122.601 ms**  self **0.222 ms**  `golden_serial.py:12452`
    - `GoldenSerialRunner.run_closure` 
      wall **4,112.443 ms**  self **0.049 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,110.442 ms**  self **0.054 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,109.814 ms**  self **0.033 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **4,109.563 ms**  self **0.024 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **4,085.208 ms**  self **0.026 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **4,085.183 ms**  self **0.045 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **3,854.003 ms**  self **0.028 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **3,853.974 ms**  self **27.806 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **3,826.109 ms**  self **0.004 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **3,826.104 ms**  self **0.011 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **3,826.093 ms**  self **0.031 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **3,826.062 ms**  self **0.073 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **3,667.976 ms**  self **0.007 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **3,667.968 ms**  self **0.019 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **3,667.950 ms**  self **0.009 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **3,667.939 ms**  self **0.013 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **3,667.926 ms**  self **0.046 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **3,667.880 ms**  self **441.484 ms**  `llama.py:824`
                                        - `prefetch_queue_pop` 
                                          wall **586.649 ms**  self **0.004 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **586.645 ms**  self **0.013 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **586.633 ms**  self **0.009 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **586.623 ms**  self **0.025 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **586.598 ms**  self **0.383 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **509.190 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **509.183 ms**  self **0.233 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **508.950 ms**  self **95.020 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **332.802 ms**  self **0.017 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **332.785 ms**  self **0.022 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **332.764 ms**  self **0.027 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **332.717 ms**  self **330.297 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **2.400 ms**  self **0.011 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **2.388 ms**  self **2.315 ms**  `ops.py:337`
                                                        - `apply_rope` 
                                                          wall **76.382 ms**  self **76.382 ms**  `llama.py:492`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **2.465 ms**  self **0.005 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **2.460 ms**  self **0.014 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **2.445 ms**  self **0.011 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **2.416 ms**  self **0.240 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **2.162 ms**  self **0.011 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **2.151 ms**  self **2.107 ms**  `ops.py:337`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **40.475 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **40.470 ms**  self **0.013 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **40.457 ms**  self **0.189 ms**  `llama.py:644`
                                                        - `silu` 
                                                          wall **38.670 ms**  self **38.670 ms**  `functional.py:2429`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **36.363 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **36.357 ms**  self **0.009 ms**  `module.py:1787`
                                                      - `RMSNorm.forward` 
                                                        wall **36.348 ms**  self **0.011 ms**  `llama.py:436`
                                                        - `rms_norm` 
                                                          wall **36.336 ms**  self **0.038 ms**  `rmsnorm.py:7`
                                                          - `rms_norm` 
                                                            wall **36.111 ms**  self **36.111 ms**  `functional.py:2998`
                                        - `prefetch_queue_pop` 
                                          wall **3.094 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.091 ms**  self **0.007 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.084 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.078 ms**  self **0.016 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.063 ms**  self **0.069 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.441 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.438 ms**  self **0.015 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.423 ms**  self **1.045 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **1.527 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.526 ms**  self **0.003 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.523 ms**  self **0.003 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.520 ms**  self **0.004 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.516 ms**  self **0.044 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.089 ms**  self **0.002 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.087 ms**  self **0.009 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **1.078 ms**  self **0.527 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **1.446 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.445 ms**  self **0.003 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.441 ms**  self **0.002 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.439 ms**  self **0.005 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.434 ms**  self **0.040 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.005 ms**  self **0.002 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.002 ms**  self **0.009 ms**  `module.py:1787`
                                        - `prefetch_queue_pop` 
                                          wall **1.321 ms**  self **0.007 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.314 ms**  self **0.003 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.311 ms**  self **0.002 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.309 ms**  self **0.004 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.305 ms**  self **0.041 ms**  `llama.py:661`
                                        - `prefetch_queue_pop` 
                                          wall **1.301 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.300 ms**  self **0.002 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.297 ms**  self **0.002 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.295 ms**  self **0.004 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.290 ms**  self **0.039 ms**  `llama.py:661`
                                        - `prefetch_queue_pop` 
                                          wall **1.264 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.263 ms**  self **0.003 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.260 ms**  self **0.002 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.258 ms**  self **0.004 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.254 ms**  self **0.037 ms**  `llama.py:661`
                                        - `prefetch_queue_pop` 
                                          wall **1.247 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **1.246 ms**  self **0.002 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **1.243 ms**  self **0.002 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **1.241 ms**  self **0.004 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **1.238 ms**  self **0.051 ms**  `llama.py:661`
                                        _... 28 more children >= 1 ms omitted_
  - `BaseEventLoop._run_once` 
    wall **74.938 ms**  self **0.010 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **74.606 ms**  self **15.742 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **74.571 ms**  self **0.008 ms**  `golden_serial.py:15624`

### `golden_unet_load`

- Stage wall: **3,056.939 ms**

- `golden_unet_load` 
  wall **3,056.939 ms**  self **75.465 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **2,968.070 ms**  self **0.013 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **2,967.684 ms**  self **0.017 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **2,967.667 ms**  self **0.016 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **2,967.651 ms**  self **0.118 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **2,967.533 ms**  self **0.676 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **2,858.671 ms**  self **6.115 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **363.196 ms**  self **0.045 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **250.948 ms**  self **250.948 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._read_message` 
                  wall **110.573 ms**  self **110.540 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **1.122 ms**  self **0.037 ms**  `golden_source_threads.py:1044`
              - `SourceThreadProcess.wait_ready` 
                wall **45.617 ms**  self **0.019 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **44.948 ms**  self **44.927 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **43.863 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **43.115 ms**  self **43.086 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **41.226 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **40.670 ms**  self **40.642 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **40.537 ms**  self **0.008 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **40.392 ms**  self **40.372 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **39.332 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **38.525 ms**  self **38.496 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **38.035 ms**  self **0.009 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **37.629 ms**  self **37.607 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **37.205 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **30.761 ms**  self **30.739 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **6.049 ms**  self **0.029 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__exit__` 
                    wall **5.579 ms**  self **5.579 ms**  `golden_source_threads.py:501`
              _... 180 more children >= 1 ms omitted_
            - `GoldenQDTransport.finalize_external_ready` 
              wall **37.558 ms**  self **0.160 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **34.581 ms**  self **0.010 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **34.558 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **34.547 ms**  self **0.006 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **34.539 ms**  self **34.536 ms**  `threading.py:288`
              - `_Telemetry.snapshot` 
                wall **1.293 ms**  self **0.004 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **1.289 ms**  self **0.109 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **1.143 ms**  self **0.014 ms**  `golden_qd_transport.py:2016`
                    - `_json_safe.<locals>.<dictcomp>` 
                      wall **1.121 ms**  self **0.169 ms**  `golden_qd_transport.py:2022`
              - `GoldenQDTransport._record_ranges` 
                wall **1.154 ms**  self **0.892 ms**  `golden_qd_transport.py:3261`
            - `GoldenModelTransport._views` 
              wall **30.705 ms**  self **30.705 ms**  `golden_model_transport.py:2042`
            - `SourceThreadProcess.snapshot` 
              wall **11.844 ms**  self **0.946 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **9.606 ms**  self **0.741 ms**  `golden_source_threads.py:597`
            - `SourceThreadProcess.snapshot` 
              wall **11.589 ms**  self **0.993 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **9.507 ms**  self **0.841 ms**  `golden_source_threads.py:597`
            - `GpuDestinationPool.acquire` 
              wall **7.935 ms**  self **0.027 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **7.899 ms**  self **7.725 ms**  `golden_model_transport.py:161`
            - `summarize_source_operations` 
              wall **4.757 ms**  self **2.215 ms**  `source_latency_telemetry.py:68`
            - `GoldenModelTransport.inspect` 
              wall **1.069 ms**  self **0.018 ms**  `golden_model_transport.py:999`
              - `_file_identity` 
                wall **1.051 ms**  self **1.051 ms**  `golden_model_transport.py:297`
  - `golden.unet.source_h2d_transport` 
    wall **2,842.360 ms**  self **0.371 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop._run_once` 
    wall **2,841.814 ms**  self **0.033 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **2,841.538 ms**  self **2,841.535 ms**  `selectors.py:451`
  - `Llama2_.compute_freqs_cis` 
    wall **2,469.671 ms**  self **0.878 ms**  `llama.py:815`
    - `precompute_freqs_cis` 
      wall **2,468.793 ms**  self **218.562 ms**  `llama.py:445`
      - `_register_overrides_from_graph.<locals>.eager_router` 
        wall **1,938.148 ms**  self **0.025 ms**  `registry.py:938`
        - `_register_overrides_from_graph.<locals>._dispatch` 
          wall **1,938.118 ms**  self **0.045 ms**  `registry.py:926`
          - `OpOverloadPacket.__call__` 
            wall **1,937.408 ms**  self **0.087 ms**  `_ops.py:1338`
            - `_bmm_outer_product_impl` 
              wall **1,937.321 ms**  self **38.275 ms**  `triton_impl.py:18`
              - `bmm_outer_product` 
                wall **1,898.988 ms**  self **0.788 ms**  `triton_kernels.py:77`
                - `_make_wrapper.<locals>.wrapper` 
                  wall **1,898.081 ms**  self **0.007 ms**  `instrumentation.py:202`
                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                    wall **1,898.022 ms**  self **0.022 ms**  `jit.py:374`
                    - `JITFunction.run` 
                      wall **1,898.000 ms**  self **0.124 ms**  `jit.py:726`
                      - `DriverConfig.active` 
                        wall **1,009.245 ms**  self **0.006 ms**  `driver.py:36`
                        - `DriverConfig.default` 
                          wall **1,009.239 ms**  self **0.014 ms**  `driver.py:30`
                          - `_create_driver` 
                            wall **1,009.225 ms**  self **0.026 ms**  `driver.py:8`
                            - `CudaDriver.__init__` 
                              wall **1,009.151 ms**  self **0.032 ms**  `driver.py:341`
                              - `CudaUtils.__init__` 
                                wall **1,009.099 ms**  self **0.036 ms**  `driver.py:100`
                                - `compile_module_from_file` 
                                  wall **986.859 ms**  self **0.017 ms**  `build.py:193`
                                  - `_compile_so_from_file` 
                                    wall **986.842 ms**  self **1.976 ms**  `build.py:157`
                                    - `_compile_so` 
                                      wall **984.816 ms**  self **0.341 ms**  `build.py:132`
                                      - `_build` 
                                        wall **967.619 ms**  self **0.063 ms**  `build.py:60`
                                        - `check_call` 
                                          wall **963.786 ms**  self **0.010 ms**  `subprocess.py:398`
                                          - `call` 
                                            wall **963.773 ms**  self **0.015 ms**  `subprocess.py:381`
                                            - `Popen.wait` 
                                              wall **956.507 ms**  self **0.003 ms**  `subprocess.py:1259`
                                              - `Popen._wait` 
                                                wall **956.504 ms**  self **0.011 ms**  `subprocess.py:2014`
                                                - `Popen._try_wait` 
                                                  wall **956.491 ms**  self **956.491 ms**  `subprocess.py:2001`
                                            - `Popen.__init__` 
                                              wall **7.243 ms**  self **0.021 ms**  `subprocess.py:807`
                                              - `Popen._execute_child` 
                                                wall **7.042 ms**  self **6.866 ms**  `subprocess.py:1789`
                                        - `_find_compiler` 
                                          wall **2.824 ms**  self **0.046 ms**  `build.py:21`
                                          - `which` 
                                            wall **1.466 ms**  self **0.056 ms**  `shutil.py:1452`
                                            - `_access_check` 
                                              wall **1.078 ms**  self **1.078 ms**  `shutil.py:1447`
                                          - `which` 
                                            wall **1.311 ms**  self **0.104 ms**  `shutil.py:1452`
                                      - `_get_cache_manager` 
                                        wall **11.257 ms**  self **0.119 ms**  `build.py:117`
                                        - `platform_key` 
                                          wall **10.412 ms**  self **0.038 ms**  `build.py:94`
                                          - `architecture` 
                                            wall **10.363 ms**  self **0.038 ms**  `platform.py:646`
                                            - `_syscmd_file` 
                                              wall **10.325 ms**  self **1.492 ms**  `platform.py:602`
                                              - `check_output` 
                                                wall **8.455 ms**  self **0.009 ms**  `subprocess.py:417`
                                                - `run` 
                                                  wall **8.446 ms**  self **0.008 ms**  `subprocess.py:506`
                                                  - `Popen.__init__` 
                                                    wall **8.438 ms**  self **0.232 ms**  `subprocess.py:807`
                                                    - `Popen._execute_child` 
                                                      wall **7.683 ms**  self **7.479 ms**  `subprocess.py:1789`
                                      - `FileCacheManager.put` 
                                        wall **2.976 ms**  self **2.686 ms**  `cache.py:103`
                                      - `_load_module_from_path` 
                                        wall **1.345 ms**  self **1.345 ms**  `build.py:108`
                                - `library_dirs` 
                                  wall **22.204 ms**  self **0.015 ms**  `driver.py:49`
                                  - `libcuda_dirs` 
                                    wall **22.188 ms**  self **0.211 ms**  `driver.py:25`
                                    - `check_output` 
                                      wall **21.366 ms**  self **0.018 ms**  `subprocess.py:417`
                                      - `run` 
                                        wall **21.346 ms**  self **0.061 ms**  `subprocess.py:506`
                                        - `Popen.communicate` 
                                          wall **12.787 ms**  self **12.518 ms**  `subprocess.py:1165`
                                        - `Popen.__init__` 
                                          wall **8.488 ms**  self **0.089 ms**  `subprocess.py:807`
                                          - `Popen._execute_child` 
                                            wall **8.194 ms**  self **8.007 ms**  `subprocess.py:1789`
                      - `dynamic_func` 
                        wall **441.214 ms**  self **441.169 ms**  `<string>:2`
                      - `JITFunction._do_compile` 
                        wall **441.167 ms**  self **0.054 ms**  `jit.py:877`
                        - `compile` 
                          wall **441.094 ms**  self **24.385 ms**  `compiler.py:226`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **94.309 ms**  self **0.012 ms**  `compiler.py:606`
                            - `CUDABackend.make_ptx` 
                              wall **94.297 ms**  self **92.926 ms**  `compiler.py:480`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **81.470 ms**  self **0.077 ms**  `compiler.py:605`
                            - `CUDABackend.make_llir` 
                              wall **81.394 ms**  self **81.275 ms**  `compiler.py:367`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **58.303 ms**  self **0.037 ms**  `compiler.py:607`
                            - `CUDABackend.make_cubin` 
                              wall **58.264 ms**  self **1.030 ms**  `compiler.py:513`
                              - `run` 
                                wall **54.606 ms**  self **0.026 ms**  `subprocess.py:506`
                                - `Popen.communicate` 
                                  wall **50.544 ms**  self **0.005 ms**  `subprocess.py:1165`
                                  - `Popen.wait` 
                                    wall **50.539 ms**  self **0.003 ms**  `subprocess.py:1259`
                                    - `Popen._wait` 
                                      wall **50.536 ms**  self **0.015 ms**  `subprocess.py:2014`
                                      - `Popen._try_wait` 
                                        wall **50.519 ms**  self **50.519 ms**  `subprocess.py:2001`
                                - `Popen.__init__` 
                                  wall **4.026 ms**  self **0.019 ms**  `subprocess.py:807`
                                  - `Popen._execute_child` 
                                    wall **3.966 ms**  self **0.029 ms**  `subprocess.py:1789`
                                    - `Popen._posix_spawn` 
                                      wall **3.937 ms**  self **3.909 ms**  `subprocess.py:1750`
                              - `NamedTemporaryFile` 
                                wall **1.412 ms**  self **0.065 ms**  `tempfile.py:522`
                                - `NamedTemporaryFile.<locals>.opener` 
                                  wall **1.329 ms**  self **0.003 ms**  `tempfile.py:558`
                                  - `_mkstemp_inner` 
                                    wall **1.326 ms**  self **1.235 ms**  `tempfile.py:243`
                          - `get_cache_key` 
                            wall **56.648 ms**  self **0.034 ms**  `cache.py:319`
                            - `CUDABackend.hash` 
                              wall **51.720 ms**  self **0.013 ms**  `compiler.py:611`
                              - `get_ptxas_version` 
                                wall **51.707 ms**  self **0.016 ms**  `compiler.py:42`
                                - `get_ptxas` 
                                  wall **38.735 ms**  self **0.005 ms**  `compiler.py:38`
                                  - `env_base.__get__` 
                                    wall **38.730 ms**  self **0.003 ms**  `knobs.py:76`
                                    - `env_nvidia_tool.get` 
                                      wall **38.726 ms**  self **0.004 ms**  `knobs.py:203`
                                      - `env_nvidia_tool.transform` 
                                        wall **38.722 ms**  self **0.011 ms**  `knobs.py:206`
                                        - `NvidiaTool.from_path` 
                                          wall **38.711 ms**  self **0.018 ms**  `knobs.py:181`
                                          - `check_output` 
                                            wall **38.293 ms**  self **0.014 ms**  `subprocess.py:417`
                                            - `run` 
                                              wall **38.277 ms**  self **0.031 ms**  `subprocess.py:506`
                                              - `Popen.communicate` 
                                                wall **22.850 ms**  self **22.797 ms**  `subprocess.py:1165`
                                              - `Popen.__init__` 
                                                wall **15.386 ms**  self **0.700 ms**  `subprocess.py:807`
                                                - `Popen._execute_child` 
                                                  wall **14.564 ms**  self **14.274 ms**  `subprocess.py:1789`
                                - `check_output` 
                                  wall **12.946 ms**  self **0.012 ms**  `subprocess.py:417`
                                  - `run` 
                                    wall **12.932 ms**  self **0.018 ms**  `subprocess.py:506`
                                    - `Popen.communicate` 
                                      wall **9.248 ms**  self **9.211 ms**  `subprocess.py:1165`
                                    - `Popen.__init__` 
                                      wall **3.660 ms**  self **0.121 ms**  `subprocess.py:807`
                                      - `Popen._execute_child` 
                                        wall **3.470 ms**  self **3.339 ms**  `subprocess.py:1789`
                            - `CUDAOptions.hash` 
                              wall **2.587 ms**  self **0.050 ms**  `compiler.py:153`
                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                wall **2.506 ms**  self **0.012 ms**  `compiler.py:155`
                                - `file_hash` 
                                  wall **2.494 ms**  self **2.494 ms**  `compiler.py:97`
                            - `ASTSource.hash` 
                              wall **2.307 ms**  self **0.059 ms**  `compiler.py:71`
                              - `JITCallable.cache_key` 
                                wall **2.233 ms**  self **0.082 ms**  `jit.py:515`
                                - `JITCallable.parse` 
                                  wall **1.037 ms**  self **0.015 ms**  `jit.py:546`
                                  - `parse` 
                                    wall **1.022 ms**  self **1.022 ms**  `ast.py:33`
                                - `NodeVisitor.visit` 
                                  wall **1.028 ms**  self **0.010 ms**  `ast.py:414`
                                  - `NodeVisitor.generic_visit` 
                                    wall **1.018 ms**  self **0.008 ms**  `ast.py:420`
                                    - `NodeVisitor.visit` 
                                      wall **1.008 ms**  self **0.004 ms**  `ast.py:414`
                                      - `DependenciesFinder.visit_FunctionDef` 
                                        wall **1.004 ms**  self **0.004 ms**  `jit.py:196`
                          - `ASTSource.make_ir` 
                            wall **46.676 ms**  self **0.030 ms**  `compiler.py:78`
                            - `ast_to_ttir` 
                              wall **46.646 ms**  self **1.315 ms**  `code_generator.py:1662`
                              - `CodeGenerator.visit` 
                                wall **37.579 ms**  self **0.042 ms**  `code_generator.py:1581`
                                - `NodeVisitor.visit` 
                                  wall **37.536 ms**  self **0.007 ms**  `ast.py:414`
                                  - `CodeGenerator.visit_Module` 
                                    wall **37.529 ms**  self **0.004 ms**  `code_generator.py:519`
                                    - `NodeVisitor.generic_visit` 
                                      wall **37.526 ms**  self **0.012 ms**  `ast.py:420`
                                      - `CodeGenerator.visit` 
                                        wall **37.509 ms**  self **0.032 ms**  `code_generator.py:1581`
                                        - `NodeVisitor.visit` 
                                          wall **37.477 ms**  self **0.014 ms**  `ast.py:414`
                                          - `CodeGenerator.visit_FunctionDef` 
                                            wall **37.464 ms**  self **0.167 ms**  `code_generator.py:628`
                                            - `CodeGenerator.visit_compound_statement` 
                                              wall **35.870 ms**  self **0.044 ms**  `code_generator.py:508`
                                              - `CodeGenerator.visit` 
                                                wall **9.584 ms**  self **0.031 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **9.552 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **9.550 ms**  self **0.010 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **9.505 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **9.491 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **9.488 ms**  self **0.020 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **9.149 ms**  self **0.014 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **9.134 ms**  self **0.084 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **8.801 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **8.797 ms**  self **0.002 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **8.795 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **8.794 ms**  self **0.008 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **8.782 ms**  self **8.782 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **8.817 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **8.811 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **8.808 ms**  self **0.012 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **8.760 ms**  self **0.027 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **8.733 ms**  self **0.003 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **8.730 ms**  self **0.014 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **8.625 ms**  self **0.007 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **8.617 ms**  self **0.062 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **7.085 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **7.076 ms**  self **0.004 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **7.072 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **7.069 ms**  self **0.009 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **7.057 ms**  self **7.057 ms**  `code_generator.py:1581`
                                                              - `CodeGenerator.__init__` 
                                                                wall **1.329 ms**  self **1.324 ms**  `code_generator.py:288`
                                              - `CodeGenerator.visit` 
                                                wall **3.228 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **3.219 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Expr` 
                                                    wall **3.217 ms**  self **0.005 ms**  `code_generator.py:1556`
                                                    - `NodeVisitor.generic_visit` 
                                                      wall **3.212 ms**  self **0.008 ms**  `ast.py:420`
                                                      - `CodeGenerator.visit` 
                                                        wall **3.202 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                        - `NodeVisitor.visit` 
                                                          wall **3.196 ms**  self **0.004 ms**  `ast.py:414`
                                                          - `CodeGenerator.visit_Call` 
                                                            wall **3.192 ms**  self **0.023 ms**  `code_generator.py:1455`
                                                            - `CodeGenerator.visit` 
                                                              wall **2.842 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                              - `NodeVisitor.visit` 
                                                                wall **2.834 ms**  self **0.009 ms**  `ast.py:414`
                                                                - `CodeGenerator.visit_BinOp` 
                                                                  wall **2.825 ms**  self **0.013 ms**  `code_generator.py:810`
                                                                  - `CodeGenerator.visit` 
                                                                    wall **1.805 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                    - `NodeVisitor.visit` 
                                                                      wall **1.800 ms**  self **0.003 ms**  `ast.py:414`
                                                                      - `CodeGenerator.visit_BinOp` 
                                                                        wall **1.797 ms**  self **1.797 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **3.035 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **3.027 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **3.025 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.984 ms**  self **2.352 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **2.652 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.643 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.641 ms**  self **0.016 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.543 ms**  self **0.224 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.319 ms**  self **0.007 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **2.312 ms**  self **0.008 ms**  `code_generator.py:810`
                                                          - `CodeGenerator._apply_binary_method` 
                                                            wall **1.405 ms**  self **0.003 ms**  `code_generator.py:795`
                                                            - `builtin.<locals>.wrapper` 
                                                              wall **1.402 ms**  self **0.002 ms**  `core.py:38`
                                                              - `tensor.__add__` 
                                                                wall **1.400 ms**  self **0.003 ms**  `core.py:901`
                                                                - `builtin.<locals>.wrapper` 
                                                                  wall **1.397 ms**  self **0.003 ms**  `core.py:38`
                                                                  - `add` 
                                                                    wall **1.394 ms**  self **0.004 ms**  `core.py:2890`
                                                                    - `TritonSemantic.add` 
                                                                      wall **1.389 ms**  self **0.029 ms**  `semantic.py:230`
                                                                      - `TritonSemantic.binary_op_sanitize_overflow_impl` 
                                                                        wall **1.293 ms**  self **1.293 ms**  `semantic.py:212`
                                              - `CodeGenerator.visit` 
                                                wall **2.417 ms**  self **0.008 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.409 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.407 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.353 ms**  self **0.019 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.334 ms**  self **0.006 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.328 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.613 ms**  self **0.021 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.592 ms**  self **0.004 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.588 ms**  self **0.010 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **2.230 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.221 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.219 ms**  self **0.013 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.164 ms**  self **0.032 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.132 ms**  self **0.004 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.128 ms**  self **0.012 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.771 ms**  self **0.244 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.527 ms**  self **0.009 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.518 ms**  self **0.010 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.525 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.520 ms**  self **0.001 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.518 ms**  self **0.009 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.466 ms**  self **0.017 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.450 ms**  self **0.004 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.445 ms**  self **0.004 ms**  `code_generator.py:810`
                              - `JITCallable.parse` 
                                wall **6.519 ms**  self **0.010 ms**  `jit.py:546`
                                - `parse` 
                                  wall **6.509 ms**  self **6.509 ms**  `ast.py:33`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **37.911 ms**  self **0.102 ms**  `compiler.py:602`
                            - `CUDABackend.make_ttgir` 
                              wall **37.809 ms**  self **37.809 ms**  `compiler.py:260`
                          - `FileCacheManager.put` 
                            wall **15.207 ms**  self **14.597 ms**  `cache.py:103`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **9.770 ms**  self **0.056 ms**  `compiler.py:601`
                            - `CUDABackend.make_ttir` 
                              wall **9.714 ms**  self **9.714 ms**  `compiler.py:244`
                          _... 8 more children >= 1 ms omitted_
                      - `CompiledKernel.launch_metadata` 
                        wall **3.815 ms**  self **0.030 ms**  `compiler.py:493`
                        - `CompiledKernel._init_handles` 
                          wall **3.782 ms**  self **0.377 ms**  `compiler.py:448`
                          - `max_shared_mem` 
                            wall **3.066 ms**  self **3.066 ms**  `compiler.py:133`
                      - `JITFunction.create_binder` 
                        wall **1.158 ms**  self **0.065 ms**  `jit.py:689`
                        - `create_function_from_signature` 
                          wall **1.008 ms**  self **0.865 ms**  `jit.py:396`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **166.023 ms**  self **0.024 ms**  `_tensor.py:32`
        - `Tensor.__rpow__` 
          wall **165.999 ms**  self **165.999 ms**  `_tensor.py:1155`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **146.061 ms**  self **0.019 ms**  `_tensor.py:32`
        - `Tensor.__rdiv__` 
          wall **146.042 ms**  self **146.042 ms**  `_tensor.py:1120`
  - `CLIP.load_model` 
    wall **230.987 ms**  self **0.027 ms**  `sd.py:459`
    - `load_models_gpu` 
      wall **230.957 ms**  self **0.158 ms**  `model_management.py:909`
      - `LoadedModel.model_load` 
        wall **191.009 ms**  self **0.035 ms**  `model_management.py:782`
        - `LoadedModel.model_use_more_vram` 
          wall **190.939 ms**  self **0.007 ms**  `model_management.py:817`
          - `ModelPatcherDynamic.partially_load` 
            wall **190.932 ms**  self **0.168 ms**  `model_patcher.py:2141`
            - `ModelPatcherDynamic.load` 
              wall **190.657 ms**  self **15.708 ms**  `model_patcher.py:1853`
              - `ModelPatcher._load_list` 
                wall **71.075 ms**  self **32.011 ms**  `model_patcher.py:945`
                - `module_size` 
                  wall **2.203 ms**  self **0.006 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **2.197 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **2.188 ms**  self **2.188 ms**  `module.py:2148`
              - `HostBuffer.__del__` 
                wall **8.333 ms**  self **8.288 ms**  `host_buffer.py:125`
              - `HostBuffer.__del__` 
                wall **3.882 ms**  self **3.855 ms**  `host_buffer.py:125`
              - `Module.named_buffers` 
                wall **3.739 ms**  self **0.004 ms**  `module.py:2754`
                - `Module._named_members` 
                  wall **3.735 ms**  self **0.668 ms**  `module.py:2650`
              - `HostBuffer.__del__` 
                wall **2.076 ms**  self **2.050 ms**  `host_buffer.py:125`
              - `ModelPatcherDynamic._vbar_get` 
                wall **1.366 ms**  self **0.029 ms**  `model_patcher.py:1797`
                - `ModelVBAR.__init__` 
                  wall **1.336 ms**  self **1.279 ms**  `model_vbar.py:50`
              - `Module.__setattr__` 
                wall **1.352 ms**  self **1.351 ms**  `module.py:1976`
              - `HostBuffer.__init__` 
                wall **1.331 ms**  self **1.324 ms**  `host_buffer.py:79`
              _... 1 more children >= 1 ms omitted_
      - `LoadedModel.model_memory_required` 
        wall **38.003 ms**  self **0.007 ms**  `model_management.py:776`
        - `LoadedModel.model_memory` 
          wall **37.994 ms**  self **0.008 ms**  `model_management.py:767`
          - `ModelPatcher.model_size` 
            wall **37.986 ms**  self **0.146 ms**  `model_patcher.py:405`
            - `module_size` 
              wall **37.839 ms**  self **0.117 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **37.722 ms**  self **0.019 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **37.699 ms**  self **0.015 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **37.400 ms**  self **0.015 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **37.383 ms**  self **0.014 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **37.315 ms**  self **0.087 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **8.983 ms**  self **0.018 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **8.679 ms**  self **0.005 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **8.673 ms**  self **8.673 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **6.925 ms**  self **0.013 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **5.403 ms**  self **0.016 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **4.510 ms**  self **0.006 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **4.503 ms**  self **4.503 ms**  `module.py:2148`
                          - `Module.state_dict` 
                            wall **1.489 ms**  self **0.020 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **3.260 ms**  self **0.012 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.884 ms**  self **0.009 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.854 ms**  self **0.006 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **2.849 ms**  self **2.849 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **2.100 ms**  self **0.026 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.027 ms**  self **0.027 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **2.021 ms**  self **0.013 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.788 ms**  self **0.017 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.695 ms**  self **0.006 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.689 ms**  self **1.689 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **1.920 ms**  self **0.018 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.450 ms**  self **0.030 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.213 ms**  self **0.007 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.206 ms**  self **1.206 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **1.907 ms**  self **0.019 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.265 ms**  self **0.037 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.184 ms**  self **0.010 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.097 ms**  self **0.005 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **1.092 ms**  self **1.092 ms**  `module.py:2148`
                        _... 2 more children >= 1 ms omitted_
      - `get_free_memory` 
        wall **1.535 ms**  self **0.023 ms**  `model_management.py:1748`
        - `mem_get_info` 
          wall **1.187 ms**  self **1.179 ms**  `memory.py:847`
  - `SDClipModel.process_tokens` 
    wall **158.007 ms**  self **1.871 ms**  `sd1_clip.py:172`
    - `Module._wrapped_call_impl` 
      wall **156.129 ms**  self **0.010 ms**  `module.py:1779`
      - `Module._call_impl` 
        wall **156.119 ms**  self **0.009 ms**  `module.py:1787`
        - `disable_weight_init.Embedding.forward` 
          wall **156.110 ms**  self **0.012 ms**  `ops.py:798`
          - `disable_weight_init.Embedding.forward_comfy_cast_weights` 
            wall **156.061 ms**  self **111.752 ms**  `ops.py:790`
            - `embedding` 
              wall **44.223 ms**  self **44.223 ms**  `functional.py:2509`
  - `BaseEventLoop._run_once` 
    wall **139.122 ms**  self **0.021 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **124.868 ms**  self **2.369 ms**  `events.py:78`
      - `golden.unet.skeleton_patcher_construction` 
        wall **66.654 ms**  self **66.654 ms**  `full_execution_trace.py:330`
      - `golden.unet.header_config_preflight` 
        wall **55.844 ms**  self **55.844 ms**  `full_execution_trace.py:330`
    - `Handle._run` 
      wall **8.395 ms**  self **8.395 ms**  `events.py:78`
    - `EpollSelector.select` 
      wall **5.837 ms**  self **5.837 ms**  `selectors.py:451`
  - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
    wall **125.233 ms**  self **0.011 ms**  `_tensor.py:32`
    - `Tensor.__rsub__` 
      wall **125.222 ms**  self **125.222 ms**  `_tensor.py:1116`
  _... 8 more children >= 1 ms omitted_

### `golden_sampler_prepare`

- Stage wall: **79.943 ms**

- `golden_sampler_prepare` 
  wall **79.943 ms**  self **0.768 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **79.920 ms**  self **0.100 ms**  `golden_serial.py:13634`
    - `GoldenSerialRunner.run_closure` 
      wall **78.460 ms**  self **0.085 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **47.918 ms**  self **0.024 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **47.304 ms**  self **0.027 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **38.319 ms**  self **0.014 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **37.892 ms**  self **0.028 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **32.203 ms**  self **0.024 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **28.185 ms**  self **0.044 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **24.577 ms**  self **0.776 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **23.680 ms**  self **23.676 ms**  `nodes.py:1992`
                  - `GoldenSerialRunner._resolve` 
                    wall **2.607 ms**  self **0.004 ms**  `golden_serial.py:9010`
                    - `GoldenSerialRunner._observe_tasks` 
                      wall **2.598 ms**  self **0.006 ms**  `golden_serial.py:8621`
                      - `all_tasks` 
                        wall **2.554 ms**  self **2.518 ms**  `tasks.py:42`
                - `GoldenSerialRunner._ensure` 
                  wall **2.822 ms**  self **0.020 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._ensure` 
                  wall **1.147 ms**  self **0.013 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **4.381 ms**  self **0.038 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **3.766 ms**  self **0.014 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **3.625 ms**  self **0.028 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **3.225 ms**  self **0.017 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **2.919 ms**  self **0.002 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **2.917 ms**  self **0.022 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **2.895 ms**  self **2.893 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **1.253 ms**  self **0.023 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **8.716 ms**  self **0.045 ms**  `golden_serial.py:8902`
            - `GoldenSerialRunner._call_node` 
              wall **8.204 ms**  self **0.018 ms**  `golden_serial.py:9035`
              - `make_locked_method_func.<locals>.wrapped_func` 
                wall **7.871 ms**  self **0.003 ms**  `__init__.py:148`
                - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                  wall **7.868 ms**  self **0.019 ms**  `_io.py:1987`
                  - `EmptySD3LatentImage.execute` 
                    wall **7.849 ms**  self **7.841 ms**  `nodes_sd3.py:56`
      - `GoldenSerialRunner._ensure` 
        wall **17.415 ms**  self **0.032 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **15.307 ms**  self **0.018 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **14.791 ms**  self **0.020 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **13.923 ms**  self **0.016 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **13.881 ms**  self **0.027 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **13.605 ms**  self **0.012 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **13.497 ms**  self **0.015 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **13.482 ms**  self **0.079 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **12.535 ms**  self **0.044 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **12.260 ms**  self **0.282 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **11.978 ms**  self **0.253 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **11.725 ms**  self **0.028 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **11.677 ms**  self **0.034 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **10.651 ms**  self **0.068 ms**  `module.py:2199`
                                  - `Module.state_dict` 
                                    wall **1.143 ms**  self **0.021 ms**  `module.py:2199`
        - `GoldenSerialRunner._execute_one` 
          wall **2.042 ms**  self **0.036 ms**  `golden_serial.py:8902`
          - `GoldenSerialRunner._call_node` 
            wall **1.693 ms**  self **0.015 ms**  `golden_serial.py:9035`
            - `LGNoiseInjectionLatent.apply` 
              wall **1.483 ms**  self **0.042 ms**  `noise_injection.py:266`
      - `GoldenSerialRunner._ensure` 
        wall **6.861 ms**  self **0.033 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **5.768 ms**  self **0.016 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **5.723 ms**  self **0.031 ms**  `golden_serial.py:8902`
            - `GoldenSerialRunner._call_node` 
              wall **5.304 ms**  self **0.109 ms**  `golden_serial.py:9035`
              - `ConditioningZeroOut.zero_out` 
                wall **4.044 ms**  self **4.044 ms**  `nodes.py:283`
              - `GoldenSerialRunner._resolve` 
                wall **1.139 ms**  self **0.008 ms**  `golden_serial.py:9010`
                - `GoldenSerialRunner._observe_tasks` 
                  wall **1.126 ms**  self **0.013 ms**  `golden_serial.py:8621`
                  - `current_task` 
                    wall **1.005 ms**  self **1.005 ms**  `tasks.py:35`
        - `GoldenSerialRunner._execute_one` 
          wall **1.028 ms**  self **0.043 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **2.490 ms**  self **0.022 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.859 ms**  self **0.043 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.396 ms**  self **0.017 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.377 ms**  self **0.056 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.287 ms**  self **0.018 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.171 ms**  self **0.035 ms**  `golden_serial.py:8902`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **78.495 ms**  self **78.495 ms**  `full_execution_trace.py:330`

### `golden_vae_load`

- Stage wall: **825.990 ms**

- `golden_vae_load` 
  wall **825.990 ms**  self **165.528 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **660.999 ms**  self **0.021 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **660.252 ms**  self **0.017 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **660.235 ms**  self **0.010 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **660.225 ms**  self **0.015 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **660.210 ms**  self **0.590 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **409.338 ms**  self **0.182 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **363.571 ms**  self **0.033 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **250.655 ms**  self **250.655 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._read_message` 
                  wall **111.160 ms**  self **111.136 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **12.863 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **11.292 ms**  self **11.274 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._poll_child` 
                  wall **1.157 ms**  self **0.004 ms**  `golden_source_threads.py:1009`
                  - `Popen.poll` 
                    wall **1.153 ms**  self **0.002 ms**  `subprocess.py:1233`
                    - `Popen._internal_poll` 
                      wall **1.150 ms**  self **1.150 ms**  `subprocess.py:1966`
              - `SourceThreadProcess.wait_ready` 
                wall **9.998 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **8.699 ms**  self **8.671 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **8.210 ms**  self **0.010 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **7.394 ms**  self **7.373 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **6.326 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **5.426 ms**  self **5.409 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.plan_once` 
                wall **5.055 ms**  self **0.204 ms**  `golden_source_threads.py:918`
                - `SourceThreadProcess._read_message` 
                  wall **2.460 ms**  self **2.443 ms**  `golden_source_threads.py:900`
                - `_FileLock.__enter__` 
                  wall **1.239 ms**  self **1.239 ms**  `golden_source_threads.py:494`
            - `GoldenModelTransport._views` 
              wall **190.000 ms**  self **190.000 ms**  `golden_model_transport.py:2042`
            - `GoldenModelTransport.inspect` 
              wall **35.135 ms**  self **0.024 ms**  `golden_model_transport.py:999`
              - `_parse_layout` 
                wall **34.462 ms**  self **33.977 ms**  `golden_model_transport.py:327`
            - `GpuDestinationPool.acquire` 
              wall **18.269 ms**  self **0.026 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **18.235 ms**  self **18.144 ms**  `golden_model_transport.py:161`
            - `SourceThreadProcess.wait_quiescent` 
              wall **2.214 ms**  self **0.019 ms**  `golden_source_threads.py:1228`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **2.161 ms**  self **0.071 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **1.810 ms**  self **0.009 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **1.791 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **1.778 ms**  self **0.005 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **1.772 ms**  self **1.769 ms**  `threading.py:288`
            - `SourceThreadProcess.snapshot` 
              wall **1.118 ms**  self **0.112 ms**  `golden_source_threads.py:1240`
  - `BaseEventLoop._run_once` 
    wall **660.462 ms**  self **0.017 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **660.191 ms**  self **660.189 ms**  `selectors.py:451`
  - `prepare_sampling` 
    wall **328.357 ms**  self **0.007 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **328.345 ms**  self **0.004 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **328.341 ms**  self **0.021 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **328.225 ms**  self **0.071 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **326.745 ms**  self **0.021 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **326.704 ms**  self **0.003 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **326.701 ms**  self **0.167 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **326.461 ms**  self **5.980 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **111.917 ms**  self **44.164 ms**  `model_patcher.py:945`
                    - `module_size` 
                      wall **1.099 ms**  self **0.006 ms**  `model_management.py:631`
                      - `Module.state_dict` 
                        wall **1.093 ms**  self **0.013 ms**  `module.py:2199`
                        - `Module._save_to_state_dict` 
                          wall **1.080 ms**  self **1.080 ms**  `module.py:2148`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **28.824 ms**  self **15.291 ms**  `model_patcher.py:1842`
                    - `set_attr_param` 
                      wall **1.793 ms**  self **0.002 ms**  `utils.py:973`
                      - `set_attr` 
                        wall **1.789 ms**  self **0.009 ms**  `utils.py:964`
                        - `resolve_attr` 
                          wall **1.767 ms**  self **0.010 ms**  `utils.py:958`
                          - `Module.__getattr__` 
                            wall **1.753 ms**  self **1.753 ms**  `module.py:1959`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **6.448 ms**  self **0.048 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **6.326 ms**  self **0.168 ms**  `model_patcher.py:899`
                      - `cast_to_device` 
                        wall **5.848 ms**  self **0.006 ms**  `model_management.py:1555`
                        - `cast_to` 
                          wall **5.828 ms**  self **5.828 ms**  `model_management.py:1527`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **3.609 ms**  self **0.041 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **3.511 ms**  self **0.096 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **2.771 ms**  self **2.769 ms**  `__init__.py:350`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **3.290 ms**  self **0.079 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **3.076 ms**  self **0.467 ms**  `model_patcher.py:899`
                      - `cast_to_device` 
                        wall **2.320 ms**  self **0.005 ms**  `model_management.py:1555`
                        - `cast_to` 
                          wall **2.302 ms**  self **2.302 ms**  `model_management.py:1527`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **3.131 ms**  self **0.016 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **3.064 ms**  self **0.046 ms**  `model_patcher.py:899`
                      - `cast_to_device` 
                        wall **2.814 ms**  self **0.003 ms**  `model_management.py:1555`
                        - `cast_to` 
                          wall **2.800 ms**  self **2.800 ms**  `model_management.py:1527`
                  - `Module.named_buffers` 
                    wall **2.720 ms**  self **0.003 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **2.717 ms**  self **0.529 ms**  `module.py:2650`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **2.049 ms**  self **0.051 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.946 ms**  self **0.191 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **1.221 ms**  self **1.219 ms**  `__init__.py:350`
                  _... 29 more children >= 1 ms omitted_
  - `sample_custom` 
    wall **275.917 ms**  self **3.255 ms**  `sample.py:86`
    - `sample` 
      wall **272.656 ms**  self **0.036 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **270.614 ms**  self **0.124 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **270.310 ms**  self **0.020 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **270.290 ms**  self **0.068 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **268.842 ms**  self **0.006 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **268.828 ms**  self **0.047 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **268.781 ms**  self **2.018 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **205.254 ms**  self **0.019 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **205.229 ms**  self **0.012 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **205.217 ms**  self **0.049 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **205.063 ms**  self **0.112 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **200.663 ms**  self **0.025 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **200.604 ms**  self **0.003 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **200.601 ms**  self **0.178 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **200.345 ms**  self **5.916 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **61.294 ms**  self **10.202 ms**  `model_patcher.py:945`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **3.199 ms**  self **0.047 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **3.080 ms**  self **0.318 ms**  `model_patcher.py:899`
                                      - `namedtuple` 
                                        wall **2.477 ms**  self **2.475 ms**  `__init__.py:350`
                                  - `Module.named_buffers` 
                                    wall **2.798 ms**  self **0.004 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **2.794 ms**  self **0.541 ms**  `module.py:2650`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **2.741 ms**  self **0.037 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **2.644 ms**  self **0.051 ms**  `model_patcher.py:899`
                                      - `cast_to_device` 
                                        wall **2.379 ms**  self **0.004 ms**  `model_management.py:1555`
                                        - `cast_to` 
                                          wall **2.345 ms**  self **2.345 ms**  `model_management.py:1527`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **1.708 ms**  self **0.052 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **1.600 ms**  self **1.240 ms**  `model_patcher.py:899`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **1.083 ms**  self **0.147 ms**  `model_patcher.py:1947`
                          - `get_free_memory` 
                            wall **2.265 ms**  self **0.023 ms**  `model_management.py:1748`
                            - `mem_get_info` 
                              wall **1.866 ms**  self **1.858 ms**  `memory.py:847`
                          - `free_memory` 
                            wall **1.859 ms**  self **0.044 ms**  `model_management.py:863`
                            - `get_free_memory` 
                              wall **1.191 ms**  self **0.041 ms**  `model_management.py:1748`
                  - `CFGGuider.inner_sample` 
                    wall **61.312 ms**  self **58.394 ms**  `samplers.py:1220`
                    - `process_conds` 
                      wall **1.402 ms**  self **0.134 ms**  `samplers.py:1038`
                    - `WrapperExecutor.execute` 
                      wall **1.218 ms**  self **0.019 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.200 ms**  self **0.090 ms**  `samplers.py:983`
      - `CFGGuider.set_conds` 
        wall **2.001 ms**  self **0.007 ms**  `samplers.py:1195`
        - `CFGGuider.inner_set_conds` 
          wall **1.995 ms**  self **0.065 ms**  `samplers.py:1201`
          - `convert_cond` 
            wall **1.622 ms**  self **0.010 ms**  `sampler_helpers.py:59`
            - `uuid4` 
              wall **1.612 ms**  self **1.591 ms**  `uuid.py:721`
  - `_vae_load_with_worker_stage` 
    wall **162.671 ms**  self **0.006 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **162.659 ms**  self **0.315 ms**  `golden_serial.py:14310`
      - `VAE.__init__` 
        wall **155.610 ms**  self **109.605 ms**  `sd.py:487`
        - `Module.load_state_dict` 
          wall **20.801 ms**  self **0.107 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **20.693 ms**  self **0.021 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **10.154 ms**  self **0.030 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **8.503 ms**  self **0.021 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.168 ms**  self **0.011 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.938 ms**  self **0.009 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.356 ms**  self **0.028 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.227 ms**  self **1.096 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.032 ms**  self **0.012 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.497 ms**  self **0.018 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.470 ms**  self **0.008 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.452 ms**  self **1.397 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.082 ms**  self **0.011 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.036 ms**  self **0.008 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **9.849 ms**  self **0.018 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **8.427 ms**  self **0.019 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.505 ms**  self **0.012 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.030 ms**  self **0.016 ms**  `module.py:2589`
                    - `Module._load_from_state_dict` 
                      wall **1.157 ms**  self **1.157 ms**  `module.py:2350`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.367 ms**  self **0.014 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.068 ms**  self **0.014 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.298 ms**  self **0.012 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.124 ms**  self **0.010 ms**  `module.py:2589`
        - `VAE.model_size` 
          wall **10.409 ms**  self **1.523 ms**  `sd.py:1095`
          - `module_size` 
            wall **8.886 ms**  self **0.082 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **8.805 ms**  self **0.016 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **6.925 ms**  self **0.016 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **4.973 ms**  self **0.014 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.666 ms**  self **0.008 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.617 ms**  self **0.008 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.266 ms**  self **0.015 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.059 ms**  self **0.005 ms**  `module.py:2199`
                          - `Module._save_to_state_dict` 
                            wall **1.053 ms**  self **1.053 ms**  `module.py:2148`
                  - `Module.state_dict` 
                    wall **1.490 ms**  self **0.010 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.278 ms**  self **0.008 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.001 ms**  self **0.021 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.404 ms**  self **0.006 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.391 ms**  self **0.008 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.728 ms**  self **0.012 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **1.854 ms**  self **0.016 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.001 ms**  self **0.013 ms**  `module.py:2199`
        - `Module.to` 
          wall **6.733 ms**  self **0.041 ms**  `module.py:1259`
          - `Module._apply` 
            wall **6.692 ms**  self **0.035 ms**  `module.py:930`
            - `Module._apply` 
              wall **3.508 ms**  self **0.013 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.732 ms**  self **0.010 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.253 ms**  self **0.007 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.201 ms**  self **0.008 ms**  `module.py:930`
            - `Module._apply` 
              wall **3.134 ms**  self **0.009 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.582 ms**  self **0.007 ms**  `module.py:930`
        - `archive_model_dtypes` 
          wall **4.585 ms**  self **0.818 ms**  `model_management.py:1045`
        - `Module.eval` 
          wall **2.046 ms**  self **0.002 ms**  `module.py:2916`
          - `Module.train` 
            wall **2.044 ms**  self **0.008 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.087 ms**  self **0.006 ms**  `module.py:2894`
        - `ModelPatcherDynamic.__init__` 
          wall **1.398 ms**  self **0.034 ms**  `model_patcher.py:1757`
      - `validate_qd_adoption` 
        wall **4.168 ms**  self **1.173 ms**  `golden_serial.py:12971`
        - `Module.named_buffers` 
          wall **1.079 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.077 ms**  self **0.219 ms**  `module.py:2650`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **43.337 ms**  self **43.337 ms**  `rk_noise_sampler_beta.py:785`
  - `generate_init_noise` 
    wall **31.709 ms**  self **3.574 ms**  `samplers.py:61`
    - `GaussianNoiseGenerator.__call__` 
      wall **24.162 ms**  self **24.159 ms**  `noise_classes.py:386`
    - `normalize_zscore` 
      wall **3.376 ms**  self **3.376 ms**  `latents.py:246`
  - `deepcopy` 
    wall **16.882 ms**  self **0.034 ms**  `copy.py:128`
    - `_reconstruct` 
      wall **16.837 ms**  self **0.016 ms**  `copy.py:259`
      - `deepcopy` 
        wall **16.813 ms**  self **0.003 ms**  `copy.py:128`
        - `_deepcopy_dict` 
          wall **16.809 ms**  self **0.008 ms**  `copy.py:227`
          - `deepcopy` 
            wall **16.791 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **16.788 ms**  self **0.098 ms**  `copy.py:227`
              - `deepcopy` 
                wall **8.707 ms**  self **0.017 ms**  `copy.py:128`
                - `Tensor.__deepcopy__` 
                  wall **8.689 ms**  self **0.183 ms**  `_tensor.py:134`
                  - `TypedStorage._deepcopy` 
                    wall **8.418 ms**  self **0.006 ms**  `storage.py:1155`
                    - `deepcopy` 
                      wall **8.393 ms**  self **2.864 ms**  `copy.py:128`
                      - `_StorageBase.__deepcopy__` 
                        wall **5.517 ms**  self **0.014 ms**  `storage.py:246`
                        - `_StorageBase.clone` 
                          wall **5.503 ms**  self **5.502 ms**  `storage.py:262`
              - `deepcopy` 
                wall **3.081 ms**  self **0.004 ms**  `copy.py:128`
                - `Tensor.__deepcopy__` 
                  wall **3.077 ms**  self **0.383 ms**  `_tensor.py:134`
                  - `TypedStorage._deepcopy` 
                    wall **2.652 ms**  self **0.003 ms**  `storage.py:1155`
                    - `deepcopy` 
                      wall **2.612 ms**  self **0.011 ms**  `copy.py:128`
                      - `_StorageBase.__deepcopy__` 
                        wall **2.592 ms**  self **0.009 ms**  `storage.py:246`
                        - `_StorageBase.clone` 
                          wall **2.583 ms**  self **2.582 ms**  `storage.py:262`
              - `deepcopy` 
                wall **2.738 ms**  self **0.004 ms**  `copy.py:128`
                - `Tensor.__deepcopy__` 
                  wall **2.733 ms**  self **0.115 ms**  `_tensor.py:134`
                  - `TypedStorage._deepcopy` 
                    wall **2.586 ms**  self **0.002 ms**  `storage.py:1155`
                    - `deepcopy` 
                      wall **2.571 ms**  self **0.005 ms**  `copy.py:128`
                      - `_StorageBase.__deepcopy__` 
                        wall **2.563 ms**  self **0.006 ms**  `storage.py:246`
                        - `_StorageBase.clone` 
                          wall **2.558 ms**  self **2.556 ms**  `storage.py:262`
              - `deepcopy` 
                wall **1.983 ms**  self **0.003 ms**  `copy.py:128`
                - `Tensor.__deepcopy__` 
                  wall **1.979 ms**  self **0.076 ms**  `_tensor.py:134`
                  - `TypedStorage._deepcopy` 
                    wall **1.881 ms**  self **0.002 ms**  `storage.py:1155`
                    - `deepcopy` 
                      wall **1.867 ms**  self **0.004 ms**  `copy.py:128`
                      - `_StorageBase.__deepcopy__` 
                        wall **1.860 ms**  self **0.003 ms**  `storage.py:246`
                        - `_StorageBase.clone` 
                          wall **1.858 ms**  self **1.857 ms**  `storage.py:262`
  _... 15 more children >= 1 ms omitted_

### `golden_sampling`

- Stage wall: **5,247.829 ms**

- `golden_sampling` 
  wall **5,247.829 ms**  self **5,247.829 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **5,247.769 ms**  self **0.198 ms**  `golden_serial.py:13785`
    - `GoldenSerialRunner.run_closure` 
      wall **5,191.297 ms**  self **0.038 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **5,191.038 ms**  self **0.065 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **5,189.998 ms**  self **0.066 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **5,189.764 ms**  self **0.267 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **5,184.886 ms**  self **39.299 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **4,746.889 ms**  self **0.088 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **4,746.637 ms**  self **0.007 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **4,746.630 ms**  self **0.058 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **4,746.195 ms**  self **0.005 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **4,746.185 ms**  self **0.009 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **4,746.176 ms**  self **6.529 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **4,411.133 ms**  self **1.435 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **4,407.331 ms**  self **0.012 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **4,407.319 ms**  self **0.101 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **4,404.869 ms**  self **0.182 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **4,404.619 ms**  self **56.830 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **550.548 ms**  self **0.789 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **549.263 ms**  self **0.812 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **547.163 ms**  self **0.018 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **547.146 ms**  self **0.009 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **547.137 ms**  self **0.017 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **547.105 ms**  self **0.012 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **547.093 ms**  self **0.034 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **547.059 ms**  self **0.027 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **532.830 ms**  self **0.007 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **532.824 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **532.813 ms**  self **0.053 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **532.760 ms**  self **1.187 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **523.569 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **523.549 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **523.525 ms**  self **3.185 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **519.379 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **519.372 ms**  self **0.023 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **519.349 ms**  self **519.349 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **6.632 ms**  self **0.026 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **6.604 ms**  self **6.604 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **14.202 ms**  self **0.496 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **13.706 ms**  self **13.130 ms**  `noise_injection.py:285`
                                        - `ExtraOptions.__call__` 
                                          wall **1.286 ms**  self **0.009 ms**  `helper.py:26`
                                          - `search` 
                                            wall **1.270 ms**  self **0.003 ms**  `__init__.py:173`
                                            - `_compile` 
                                              wall **1.267 ms**  self **0.037 ms**  `__init__.py:272`
                                              - `compile` 
                                                wall **1.211 ms**  self **0.012 ms**  `_compiler.py:738`
                                                - `parse` 
                                                  wall **1.069 ms**  self **0.009 ms**  `_parser.py:972`
                                                  - `_parse_sub` 
                                                    wall **1.053 ms**  self **0.007 ms**  `_parser.py:449`
                                                    - `_parse` 
                                                      wall **1.045 ms**  self **0.020 ms**  `_parser.py:509`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **365.119 ms**  self **0.644 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **364.430 ms**  self **0.071 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **364.350 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **364.343 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **364.339 ms**  self **0.011 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **364.318 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **364.312 ms**  self **0.096 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **364.216 ms**  self **0.019 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **363.671 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **363.667 ms**  self **0.008 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **363.654 ms**  self **0.138 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **363.516 ms**  self **0.535 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **355.211 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **355.191 ms**  self **0.016 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **355.175 ms**  self **0.146 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **354.482 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **354.476 ms**  self **0.014 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **354.462 ms**  self **354.462 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **4.241 ms**  self **0.016 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **4.225 ms**  self **4.225 ms**  `conds.py:44`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **3.159 ms**  self **0.026 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **3.056 ms**  self **0.018 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **2.629 ms**  self **2.621 ms**  `memory.py:847`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **357.910 ms**  self **0.420 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **357.453 ms**  self **0.268 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **357.158 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **357.149 ms**  self **0.008 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **357.141 ms**  self **0.020 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **357.106 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **357.100 ms**  self **0.033 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **357.067 ms**  self **0.070 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **337.455 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **337.451 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **337.439 ms**  self **0.153 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **337.287 ms**  self **1.278 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **327.947 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **327.926 ms**  self **0.015 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **327.910 ms**  self **0.169 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **327.048 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **327.040 ms**  self **0.023 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **327.017 ms**  self **327.017 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **5.477 ms**  self **0.027 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **5.449 ms**  self **5.449 ms**  `conds.py:44`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **2.105 ms**  self **0.034 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.960 ms**  self **0.021 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.516 ms**  self **1.506 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **19.543 ms**  self **0.320 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **19.222 ms**  self **18.682 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **345.982 ms**  self **0.141 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **345.802 ms**  self **0.066 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **345.727 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **345.719 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **345.713 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **345.688 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **345.683 ms**  self **0.016 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **345.666 ms**  self **0.014 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **345.521 ms**  self **0.005 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **345.517 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **345.504 ms**  self **0.032 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **345.473 ms**  self **2.534 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **339.697 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **339.675 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **339.653 ms**  self **0.186 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **338.914 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **338.906 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **338.892 ms**  self **338.892 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.896 ms**  self **0.018 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.877 ms**  self **1.877 ms**  `conds.py:44`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **344.871 ms**  self **0.157 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **344.680 ms**  self **0.051 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **344.620 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **344.614 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **344.609 ms**  self **0.010 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **344.592 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **344.586 ms**  self **0.014 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **344.572 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **325.583 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **325.579 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **325.570 ms**  self **0.032 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **325.538 ms**  self **0.458 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **323.975 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **323.961 ms**  self **0.022 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **323.939 ms**  self **1.370 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **322.036 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **322.031 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **322.020 ms**  self **322.020 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **18.972 ms**  self **0.135 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **18.837 ms**  self **18.837 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **340.779 ms**  self **0.130 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **340.617 ms**  self **0.047 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **340.561 ms**  self **0.005 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **340.556 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **340.552 ms**  self **0.009 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **340.536 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **340.531 ms**  self **0.028 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **340.503 ms**  self **0.012 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **335.158 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **335.155 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **335.145 ms**  self **0.027 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **335.118 ms**  self **0.365 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **333.517 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **333.501 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **333.488 ms**  self **0.126 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **332.789 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **332.784 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **332.773 ms**  self **332.773 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **5.332 ms**  self **0.040 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **5.293 ms**  self **5.293 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **338.086 ms**  self **0.492 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **337.549 ms**  self **0.251 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **337.272 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **337.265 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **337.261 ms**  self **0.010 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **337.241 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **337.236 ms**  self **0.016 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **337.219 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **333.644 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **333.640 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **333.631 ms**  self **0.026 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **333.605 ms**  self **0.990 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **328.792 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **328.779 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **328.765 ms**  self **0.764 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **327.336 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **327.328 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **327.315 ms**  self **327.315 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **2.228 ms**  self **0.011 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **2.217 ms**  self **2.217 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **3.558 ms**  self **0.091 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **3.468 ms**  self **3.468 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **331.669 ms**  self **0.161 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **331.478 ms**  self **0.253 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **331.212 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **331.204 ms**  self **0.006 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **331.198 ms**  self **0.015 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **331.168 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **331.162 ms**  self **0.018 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **331.145 ms**  self **0.016 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **324.497 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **324.493 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **324.482 ms**  self **0.109 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **324.373 ms**  self **3.727 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **318.173 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **318.150 ms**  self **0.038 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **318.112 ms**  self **0.191 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **317.297 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **317.289 ms**  self **0.014 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **317.275 ms**  self **317.275 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **1.057 ms**  self **0.012 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.045 ms**  self **1.045 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **6.632 ms**  self **0.101 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **6.531 ms**  self **6.297 ms**  `noise_injection.py:285`
                                    _... 43 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **28.628 ms**  self **0.013 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **28.614 ms**  self **0.063 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **7.040 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **7.034 ms**  self **0.201 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **6.788 ms**  self **0.005 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **6.762 ms**  self **0.008 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **6.744 ms**  self **0.011 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **6.733 ms**  self **6.732 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **6.366 ms**  self **0.009 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **6.356 ms**  self **0.358 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **5.931 ms**  self **0.009 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **5.899 ms**  self **0.011 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **5.876 ms**  self **0.011 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **5.865 ms**  self **5.864 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **5.767 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **5.762 ms**  self **0.238 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **5.489 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **5.469 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **5.452 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **5.444 ms**  self **5.443 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **4.508 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **4.501 ms**  self **0.264 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **4.198 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **4.168 ms**  self **0.008 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **4.152 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **4.145 ms**  self **4.144 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **3.670 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **3.663 ms**  self **0.318 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **3.292 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **3.273 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **3.248 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **3.240 ms**  self **3.240 ms**  `storage.py:262`
              - `BaseModel.process_latent_out` 
                wall **5.859 ms**  self **0.005 ms**  `model_base.py:378`
                - `Flux.process_out` 
                  wall **5.853 ms**  self **5.853 ms**  `latent_formats.py:193`
              - `_disable_dynamo.<locals>.inner` 
                wall **3.914 ms**  self **0.006 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **3.908 ms**  self **0.009 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **3.898 ms**  self **0.002 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **3.895 ms**  self **0.044 ms**  `random.py:62`
                      - `manual_seed_all` 
                        wall **2.824 ms**  self **0.004 ms**  `random.py:97`
                        - `_lazy_call` 
                          wall **2.820 ms**  self **0.013 ms**  `__init__.py:319`
                          - `format_stack` 
                            wall **2.801 ms**  self **0.012 ms**  `traceback.py:213`
                            - `extract_stack` 
                              wall **2.613 ms**  self **0.010 ms**  `traceback.py:220`
                              - `StackSummary.extract` 
                                wall **2.603 ms**  self **0.005 ms**  `traceback.py:375`
                                - `StackSummary._extract_from_extended_frame_gen` 
                                  wall **2.597 ms**  self **0.160 ms**  `traceback.py:397`
                                  - `checkcache` 
                                    wall **1.092 ms**  self **1.092 ms**  `linecache.py:52`
    - `import_module` 
      wall **32.096 ms**  self **32.096 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **18.424 ms**  self **0.016 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **18.408 ms**  self **0.002 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **18.405 ms**  self **0.035 ms**  `copy.py:201`
          - `deepcopy` 
            wall **7.902 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **7.899 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **7.885 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **7.882 ms**  self **0.037 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **7.765 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **7.763 ms**  self **0.011 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **6.511 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **6.508 ms**  self **0.162 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **3.691 ms**  self **0.004 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **3.685 ms**  self **1.054 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.751 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.748 ms**  self **0.224 ms**  `copy.py:227`
          - `deepcopy` 
            wall **7.160 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **7.158 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **7.143 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **7.140 ms**  self **0.042 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **7.018 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **7.015 ms**  self **0.012 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **5.663 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **5.660 ms**  self **0.169 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **3.380 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **3.377 ms**  self **0.951 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.268 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.266 ms**  self **0.135 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **1.807 ms**  self **0.036 ms**  `golden_serial.py:9742`
    - `_GeneratorContextManager.__exit__` 
      wall **1.369 ms**  self **0.005 ms**  `contextlib.py:141`
      - `res4lyf_gc_suppression_scope` 
        wall **1.364 ms**  self **1.260 ms**  `golden_serial.py:592`
  - `BaseEventLoop.run_until_complete` 
    wall **829.443 ms**  self **0.011 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **829.424 ms**  self **0.056 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **166.309 ms**  self **3.086 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **162.747 ms**  self **162.732 ms**  `events.py:78`
      - `BaseEventLoop._run_once` 
        wall **2.471 ms**  self **0.011 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **2.340 ms**  self **2.340 ms**  `events.py:78`
  - `Thread.run` 
    wall **828.759 ms**  self **0.008 ms**  `threading.py:964`
    - `_worker` 
      wall **828.751 ms**  self **167.740 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **825.990 ms**  self **165.528 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **660.999 ms**  self **0.021 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **660.252 ms**  self **0.017 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **660.235 ms**  self **0.010 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **660.225 ms**  self **0.015 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **660.210 ms**  self **0.590 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **409.338 ms**  self **0.182 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **363.571 ms**  self **0.033 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **250.655 ms**  self **250.655 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._read_message` 
                    wall **111.160 ms**  self **111.136 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **12.863 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **11.292 ms**  self **11.274 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.157 ms**  self **0.004 ms**  `golden_source_threads.py:1009`
                    - `Popen.poll` 
                      wall **1.153 ms**  self **0.002 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.150 ms**  self **1.150 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **9.998 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **8.699 ms**  self **8.671 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **8.210 ms**  self **0.010 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **7.394 ms**  self **7.373 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **6.326 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **5.426 ms**  self **5.409 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.plan_once` 
                  wall **5.055 ms**  self **0.204 ms**  `golden_source_threads.py:918`
                  - `SourceThreadProcess._read_message` 
                    wall **2.460 ms**  self **2.443 ms**  `golden_source_threads.py:900`
                  - `_FileLock.__enter__` 
                    wall **1.239 ms**  self **1.239 ms**  `golden_source_threads.py:494`
              - `GoldenModelTransport._views` 
                wall **190.000 ms**  self **190.000 ms**  `golden_model_transport.py:2042`
              - `GoldenModelTransport.inspect` 
                wall **35.135 ms**  self **0.024 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **34.462 ms**  self **33.977 ms**  `golden_model_transport.py:327`
              - `GpuDestinationPool.acquire` 
                wall **18.269 ms**  self **0.026 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **18.235 ms**  self **18.144 ms**  `golden_model_transport.py:161`
              - `SourceThreadProcess.wait_quiescent` 
                wall **2.214 ms**  self **0.019 ms**  `golden_source_threads.py:1228`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **2.161 ms**  self **0.071 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **1.810 ms**  self **0.009 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **1.791 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **1.778 ms**  self **0.005 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **1.772 ms**  self **1.769 ms**  `threading.py:288`
              - `SourceThreadProcess.snapshot` 
                wall **1.118 ms**  self **0.112 ms**  `golden_source_threads.py:1240`
    - `BaseEventLoop._run_once` 
      wall **660.462 ms**  self **0.017 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **660.191 ms**  self **660.189 ms**  `selectors.py:451`
    - `prepare_sampling` 
      wall **328.357 ms**  self **0.007 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **328.345 ms**  self **0.004 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **328.341 ms**  self **0.021 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **328.225 ms**  self **0.071 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **326.745 ms**  self **0.021 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **326.704 ms**  self **0.003 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **326.701 ms**  self **0.167 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **326.461 ms**  self **5.980 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **111.917 ms**  self **44.164 ms**  `model_patcher.py:945`
                      - `module_size` 
                        wall **1.099 ms**  self **0.006 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **1.093 ms**  self **0.013 ms**  `module.py:2199`
                          - `Module._save_to_state_dict` 
                            wall **1.080 ms**  self **1.080 ms**  `module.py:2148`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **28.824 ms**  self **15.291 ms**  `model_patcher.py:1842`
                      - `set_attr_param` 
                        wall **1.793 ms**  self **0.002 ms**  `utils.py:973`
                        - `set_attr` 
                          wall **1.789 ms**  self **0.009 ms**  `utils.py:964`
                          - `resolve_attr` 
                            wall **1.767 ms**  self **0.010 ms**  `utils.py:958`
                            - `Module.__getattr__` 
                              wall **1.753 ms**  self **1.753 ms**  `module.py:1959`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **6.448 ms**  self **0.048 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **6.326 ms**  self **0.168 ms**  `model_patcher.py:899`
                        - `cast_to_device` 
                          wall **5.848 ms**  self **0.006 ms**  `model_management.py:1555`
                          - `cast_to` 
                            wall **5.828 ms**  self **5.828 ms**  `model_management.py:1527`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **3.609 ms**  self **0.041 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **3.511 ms**  self **0.096 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **2.771 ms**  self **2.769 ms**  `__init__.py:350`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **3.290 ms**  self **0.079 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **3.076 ms**  self **0.467 ms**  `model_patcher.py:899`
                        - `cast_to_device` 
                          wall **2.320 ms**  self **0.005 ms**  `model_management.py:1555`
                          - `cast_to` 
                            wall **2.302 ms**  self **2.302 ms**  `model_management.py:1527`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **3.131 ms**  self **0.016 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **3.064 ms**  self **0.046 ms**  `model_patcher.py:899`
                        - `cast_to_device` 
                          wall **2.814 ms**  self **0.003 ms**  `model_management.py:1555`
                          - `cast_to` 
                            wall **2.800 ms**  self **2.800 ms**  `model_management.py:1527`
                    - `Module.named_buffers` 
                      wall **2.720 ms**  self **0.003 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **2.717 ms**  self **0.529 ms**  `module.py:2650`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **2.049 ms**  self **0.051 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.946 ms**  self **0.191 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **1.221 ms**  self **1.219 ms**  `__init__.py:350`
                    _... 29 more children >= 1 ms omitted_
    - `sample_custom` 
      wall **275.917 ms**  self **3.255 ms**  `sample.py:86`
      - `sample` 
        wall **272.656 ms**  self **0.036 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **270.614 ms**  self **0.124 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **270.310 ms**  self **0.020 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **270.290 ms**  self **0.068 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **268.842 ms**  self **0.006 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **268.828 ms**  self **0.047 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **268.781 ms**  self **2.018 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **205.254 ms**  self **0.019 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **205.229 ms**  self **0.012 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **205.217 ms**  self **0.049 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **205.063 ms**  self **0.112 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **200.663 ms**  self **0.025 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **200.604 ms**  self **0.003 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **200.601 ms**  self **0.178 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **200.345 ms**  self **5.916 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **61.294 ms**  self **10.202 ms**  `model_patcher.py:945`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **3.199 ms**  self **0.047 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **3.080 ms**  self **0.318 ms**  `model_patcher.py:899`
                                        - `namedtuple` 
                                          wall **2.477 ms**  self **2.475 ms**  `__init__.py:350`
                                    - `Module.named_buffers` 
                                      wall **2.798 ms**  self **0.004 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **2.794 ms**  self **0.541 ms**  `module.py:2650`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **2.741 ms**  self **0.037 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **2.644 ms**  self **0.051 ms**  `model_patcher.py:899`
                                        - `cast_to_device` 
                                          wall **2.379 ms**  self **0.004 ms**  `model_management.py:1555`
                                          - `cast_to` 
                                            wall **2.345 ms**  self **2.345 ms**  `model_management.py:1527`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **1.708 ms**  self **0.052 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **1.600 ms**  self **1.240 ms**  `model_patcher.py:899`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **1.083 ms**  self **0.147 ms**  `model_patcher.py:1947`
                            - `get_free_memory` 
                              wall **2.265 ms**  self **0.023 ms**  `model_management.py:1748`
                              - `mem_get_info` 
                                wall **1.866 ms**  self **1.858 ms**  `memory.py:847`
                            - `free_memory` 
                              wall **1.859 ms**  self **0.044 ms**  `model_management.py:863`
                              - `get_free_memory` 
                                wall **1.191 ms**  self **0.041 ms**  `model_management.py:1748`
                    - `CFGGuider.inner_sample` 
                      wall **61.312 ms**  self **58.394 ms**  `samplers.py:1220`
                      - `process_conds` 
                        wall **1.402 ms**  self **0.134 ms**  `samplers.py:1038`
                      - `WrapperExecutor.execute` 
                        wall **1.218 ms**  self **0.019 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.200 ms**  self **0.090 ms**  `samplers.py:983`
        - `CFGGuider.set_conds` 
          wall **2.001 ms**  self **0.007 ms**  `samplers.py:1195`
          - `CFGGuider.inner_set_conds` 
            wall **1.995 ms**  self **0.065 ms**  `samplers.py:1201`
            - `convert_cond` 
              wall **1.622 ms**  self **0.010 ms**  `sampler_helpers.py:59`
              - `uuid4` 
                wall **1.612 ms**  self **1.591 ms**  `uuid.py:721`
    - `_vae_load_with_worker_stage` 
      wall **162.671 ms**  self **0.006 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **162.659 ms**  self **0.315 ms**  `golden_serial.py:14310`
        - `VAE.__init__` 
          wall **155.610 ms**  self **109.605 ms**  `sd.py:487`
          - `Module.load_state_dict` 
            wall **20.801 ms**  self **0.107 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **20.693 ms**  self **0.021 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **10.154 ms**  self **0.030 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **8.503 ms**  self **0.021 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.168 ms**  self **0.011 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.938 ms**  self **0.009 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **2.356 ms**  self **0.028 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **1.227 ms**  self **1.096 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.032 ms**  self **0.012 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.497 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.470 ms**  self **0.008 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.452 ms**  self **1.397 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.082 ms**  self **0.011 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.036 ms**  self **0.008 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **9.849 ms**  self **0.018 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **8.427 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.505 ms**  self **0.012 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.030 ms**  self **0.016 ms**  `module.py:2589`
                      - `Module._load_from_state_dict` 
                        wall **1.157 ms**  self **1.157 ms**  `module.py:2350`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.367 ms**  self **0.014 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.068 ms**  self **0.014 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.298 ms**  self **0.012 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.124 ms**  self **0.010 ms**  `module.py:2589`
          - `VAE.model_size` 
            wall **10.409 ms**  self **1.523 ms**  `sd.py:1095`
            - `module_size` 
              wall **8.886 ms**  self **0.082 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **8.805 ms**  self **0.016 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **6.925 ms**  self **0.016 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **4.973 ms**  self **0.014 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.666 ms**  self **0.008 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.617 ms**  self **0.008 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.266 ms**  self **0.015 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.059 ms**  self **0.005 ms**  `module.py:2199`
                            - `Module._save_to_state_dict` 
                              wall **1.053 ms**  self **1.053 ms**  `module.py:2148`
                    - `Module.state_dict` 
                      wall **1.490 ms**  self **0.010 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.278 ms**  self **0.008 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **1.001 ms**  self **0.021 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.404 ms**  self **0.006 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.391 ms**  self **0.008 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.728 ms**  self **0.012 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.854 ms**  self **0.016 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.001 ms**  self **0.013 ms**  `module.py:2199`
          - `Module.to` 
            wall **6.733 ms**  self **0.041 ms**  `module.py:1259`
            - `Module._apply` 
              wall **6.692 ms**  self **0.035 ms**  `module.py:930`
              - `Module._apply` 
                wall **3.508 ms**  self **0.013 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.732 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.253 ms**  self **0.007 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.201 ms**  self **0.008 ms**  `module.py:930`
              - `Module._apply` 
                wall **3.134 ms**  self **0.009 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.582 ms**  self **0.007 ms**  `module.py:930`
          - `archive_model_dtypes` 
            wall **4.585 ms**  self **0.818 ms**  `model_management.py:1045`
          - `Module.eval` 
            wall **2.046 ms**  self **0.002 ms**  `module.py:2916`
            - `Module.train` 
              wall **2.044 ms**  self **0.008 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.087 ms**  self **0.006 ms**  `module.py:2894`
          - `ModelPatcherDynamic.__init__` 
            wall **1.398 ms**  self **0.034 ms**  `model_patcher.py:1757`
        - `validate_qd_adoption` 
          wall **4.168 ms**  self **1.173 ms**  `golden_serial.py:12971`
          - `Module.named_buffers` 
            wall **1.079 ms**  self **0.002 ms**  `module.py:2754`
            - `Module._named_members` 
              wall **1.077 ms**  self **0.219 ms**  `module.py:2650`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **43.337 ms**  self **43.337 ms**  `rk_noise_sampler_beta.py:785`
    - `generate_init_noise` 
      wall **31.709 ms**  self **3.574 ms**  `samplers.py:61`
      - `GaussianNoiseGenerator.__call__` 
        wall **24.162 ms**  self **24.159 ms**  `noise_classes.py:386`
      - `normalize_zscore` 
        wall **3.376 ms**  self **3.376 ms**  `latents.py:246`
    - `deepcopy` 
      wall **16.882 ms**  self **0.034 ms**  `copy.py:128`
      - `_reconstruct` 
        wall **16.837 ms**  self **0.016 ms**  `copy.py:259`
        - `deepcopy` 
          wall **16.813 ms**  self **0.003 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **16.809 ms**  self **0.008 ms**  `copy.py:227`
            - `deepcopy` 
              wall **16.791 ms**  self **0.002 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **16.788 ms**  self **0.098 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **8.707 ms**  self **0.017 ms**  `copy.py:128`
                  - `Tensor.__deepcopy__` 
                    wall **8.689 ms**  self **0.183 ms**  `_tensor.py:134`
                    - `TypedStorage._deepcopy` 
                      wall **8.418 ms**  self **0.006 ms**  `storage.py:1155`
                      - `deepcopy` 
                        wall **8.393 ms**  self **2.864 ms**  `copy.py:128`
                        - `_StorageBase.__deepcopy__` 
                          wall **5.517 ms**  self **0.014 ms**  `storage.py:246`
                          - `_StorageBase.clone` 
                            wall **5.503 ms**  self **5.502 ms**  `storage.py:262`
                - `deepcopy` 
                  wall **3.081 ms**  self **0.004 ms**  `copy.py:128`
                  - `Tensor.__deepcopy__` 
                    wall **3.077 ms**  self **0.383 ms**  `_tensor.py:134`
                    - `TypedStorage._deepcopy` 
                      wall **2.652 ms**  self **0.003 ms**  `storage.py:1155`
                      - `deepcopy` 
                        wall **2.612 ms**  self **0.011 ms**  `copy.py:128`
                        - `_StorageBase.__deepcopy__` 
                          wall **2.592 ms**  self **0.009 ms**  `storage.py:246`
                          - `_StorageBase.clone` 
                            wall **2.583 ms**  self **2.582 ms**  `storage.py:262`
                - `deepcopy` 
                  wall **2.738 ms**  self **0.004 ms**  `copy.py:128`
                  - `Tensor.__deepcopy__` 
                    wall **2.733 ms**  self **0.115 ms**  `_tensor.py:134`
                    - `TypedStorage._deepcopy` 
                      wall **2.586 ms**  self **0.002 ms**  `storage.py:1155`
                      - `deepcopy` 
                        wall **2.571 ms**  self **0.005 ms**  `copy.py:128`
                        - `_StorageBase.__deepcopy__` 
                          wall **2.563 ms**  self **0.006 ms**  `storage.py:246`
                          - `_StorageBase.clone` 
                            wall **2.558 ms**  self **2.556 ms**  `storage.py:262`
                - `deepcopy` 
                  wall **1.983 ms**  self **0.003 ms**  `copy.py:128`
                  - `Tensor.__deepcopy__` 
                    wall **1.979 ms**  self **0.076 ms**  `_tensor.py:134`
                    - `TypedStorage._deepcopy` 
                      wall **1.881 ms**  self **0.002 ms**  `storage.py:1155`
                      - `deepcopy` 
                        wall **1.867 ms**  self **0.004 ms**  `copy.py:128`
                        - `_StorageBase.__deepcopy__` 
                          wall **1.860 ms**  self **0.003 ms**  `storage.py:246`
                          - `_StorageBase.clone` 
                            wall **1.858 ms**  self **1.857 ms**  `storage.py:262`
    _... 15 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **162.694 ms**  self **0.008 ms**  `golden_serial.py:15614`
  - `_overlap_stage_call` 
    wall **2.331 ms**  self **0.007 ms**  `golden_serial.py:15614`

### `golden_sampler_tail`

- Stage wall: **0.051 ms**

_Nothing below the stage body reached the threshold._

### `golden_vae_decode`

- Stage wall: **1,013.777 ms**

- `golden_vae_decode` 
  wall **1,013.777 ms**  self **0.277 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **1,013.754 ms**  self **0.065 ms**  `golden_serial.py:14523`
    - `GoldenSerialRunner.run_closure` 
      wall **1,013.365 ms**  self **0.026 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **1,013.282 ms**  self **0.051 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **1,011.668 ms**  self **0.023 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **1,011.378 ms**  self **0.042 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **1,011.337 ms**  self **895.450 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **110.675 ms**  self **0.137 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **100.182 ms**  self **0.021 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **100.130 ms**  self **0.003 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **100.126 ms**  self **0.058 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **100.024 ms**  self **2.055 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **23.678 ms**  self **3.020 ms**  `model_patcher.py:945`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **2.272 ms**  self **0.046 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **2.156 ms**  self **0.245 ms**  `model_patcher.py:899`
                            - `namedtuple` 
                              wall **1.526 ms**  self **1.524 ms**  `__init__.py:350`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.627 ms**  self **0.045 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.520 ms**  self **0.080 ms**  `model_patcher.py:899`
                            - `cast_to_device` 
                              wall **1.232 ms**  self **0.003 ms**  `model_management.py:1555`
                              - `cast_to` 
                                wall **1.218 ms**  self **1.218 ms**  `model_management.py:1527`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.337 ms**  self **0.014 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.250 ms**  self **0.303 ms**  `model_patcher.py:899`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.270 ms**  self **0.047 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.157 ms**  self **0.145 ms**  `model_patcher.py:899`
                        - `Module.named_buffers` 
                          wall **1.230 ms**  self **0.004 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.227 ms**  self **0.216 ms**  `module.py:2650`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.197 ms**  self **0.027 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.089 ms**  self **0.069 ms**  `model_patcher.py:899`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.145 ms**  self **0.045 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.043 ms**  self **0.213 ms**  `model_patcher.py:899`
                        _... 3 more children >= 1 ms omitted_
                - `LoadedModel.model_memory_required` 
                  wall **6.017 ms**  self **0.005 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **6.011 ms**  self **0.005 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **6.006 ms**  self **0.343 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **5.663 ms**  self **0.154 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **5.509 ms**  self **0.027 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **3.239 ms**  self **0.017 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.460 ms**  self **0.013 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **1.069 ms**  self **0.010 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.225 ms**  self **0.029 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.004 ms**  self **0.015 ms**  `module.py:2199`
                - `free_memory` 
                  wall **3.061 ms**  self **0.171 ms**  `model_management.py:863`
                  - `get_free_memory` 
                    wall **1.602 ms**  self **0.031 ms**  `model_management.py:1748`
                    - `memory_stats` 
                      wall **1.315 ms**  self **0.967 ms**  `memory.py:242`
                - `get_free_memory` 
                  wall **1.107 ms**  self **0.028 ms**  `model_management.py:1748`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **3.996 ms**  self **3.996 ms**  `sd.py:506`
              - `ModelPatcher.get_free_memory` 
                wall **1.142 ms**  self **0.038 ms**  `model_patcher.py:417`
        - `GoldenSerialRunner._observe_tasks` 
          wall **1.161 ms**  self **0.007 ms**  `golden_serial.py:8621`
          - `all_tasks` 
            wall **1.126 ms**  self **1.084 ms**  `tasks.py:42`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **1,013.394 ms**  self **1,013.394 ms**  `full_execution_trace.py:330`

### `golden_output`

- Stage wall: **274.028 ms**

- `golden_output` 
  wall **274.028 ms**  self **274.028 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **273.951 ms**  self **16.777 ms**  `golden_serial.py:14670`
    - `Image.save` 
      wall **229.223 ms**  self **0.065 ms**  `Image.py:2592`
      - `_save` 
        wall **206.669 ms**  self **0.066 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **206.569 ms**  self **0.022 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **206.543 ms**  self **201.196 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **22.406 ms**  self **22.406 ms**  `Image.py:429`
    - `fromarray` 
      wall **14.090 ms**  self **8.702 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **5.389 ms**  self **0.016 ms**  `Image.py:3288`
        - `frombytes` 
          wall **5.364 ms**  self **0.027 ms**  `Image.py:3242`
          - `new` 
            wall **3.746 ms**  self **3.705 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.587 ms**  self **1.550 ms**  `Image.py:925`
    - `clip` 
      wall **10.118 ms**  self **0.011 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **10.108 ms**  self **0.023 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **10.084 ms**  self **10.084 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **2.280 ms**  self **0.016 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **2.264 ms**  self **2.264 ms**  `output_durability.py:73`
