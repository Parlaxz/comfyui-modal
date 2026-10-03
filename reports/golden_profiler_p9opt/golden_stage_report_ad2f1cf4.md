# Golden stage decision report

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **889,192**

Tree floor: **1 ms**   Function rollup floor: **1 ms** total inclusive

## 1. Critical path and stage overlap

Sum of stage walls: **14,599.638 ms**   Timeline union: **10,926.369 ms**   Span: **10,936.611 ms**

Sum exceeds the union by **3,673.269 ms** -- that gap is the overlap the schedule is buying.

| stage | wall ms | uncontended ms | overlapped ms | on critical path | timeline |
|:--|---:|---:|---:|:--|:--|
| `golden_restore` | 0.4 | 0.0 | 0.4 | 0.0% | `#` |
| `golden_request_setup` | 1.9 | 0.0 | 1.9 | 0.0% | `#` |
| `golden_clip_load` | 2,015.8 | 2,012.3 | 3.4 | 99.8% | `#############` |
| `golden_clip_forward` | 3,308.2 | 508.6 | 2,799.6 | 15.4% | `             ######################` |
| `golden_unet_load` | 2,795.1 | 0.0 | 2,795.1 | 0.0% | `             ##################` |
| `golden_sampler_prepare` | 55.1 | 49.2 | 5.9 | 89.3% | `                                   #` |
| `golden_vae_load` | 878.9 | 0.0 | 878.9 | 0.0% | `                                   ######` |
| `golden_sampling` | 4,413.6 | 3,532.5 | 881.1 | 80.0% | `                                   #############################` |
| `golden_sampler_tail` | 0.1 | 0.0 | 0.1 | 0.0% | `                                                                 #` |
| `golden_vae_decode` | 874.0 | 869.5 | 4.6 | 99.5% | `                                                                 ######` |
| `golden_output` | 256.5 | 251.5 | 5.0 | 98.1% | `                                                                      ##` |

_Uncontended_ is the time during a stage when no other stage was running. That portion is protected: nothing else could absorb it. Overlapped time may be hidden by a longer sibling, so reducing it may not move root wall.

## 2. Function rollup across the whole request

`total incl ms` sums each call's wall, so a function called 24 times at 3 ms reads as 72 ms instead of hiding behind a mean. Inclusive wall contains its callees, so **totals are not additive down a call tree** -- `total self ms` is the non-overlapping part.

| total incl ms | calls | avg ms | max ms | total self ms | function | source | stages |
|---:|---:|---:|---:|---:|:--|:--|:--|
| 20,499.644 | 59 | 347.452 | 4,105.192 | 1.588 | `WrapperExecutor.execute` | `patcher_extension.py:108` | 2 |
| 12,733.147 | 526 | 24.208 | 3,087.562 | 1.562 | `Module._wrapped_call_impl` | `module.py:1779` | 3 |
| 12,731.617 | 526 | 24.205 | 3,087.549 | 3.313 | `Module._call_impl` | `module.py:1787` | 3 |
| 8,589.032 | 32 | 268.407 | 4,359.055 | 1.098 | `GoldenSerialRunner._execute_one` | `golden_serial.py:8902` | 6 |
| 8,585.193 | 5 | 1,717.039 | 4,359.377 | 0.214 | `GoldenSerialRunner.run_closure` | `golden_serial.py:9143` | 5 |
| 8,571.750 | 32 | 267.867 | 4,358.211 | 1.519 | `GoldenSerialRunner._call_node` | `golden_serial.py:9035` | 6 |
| 5,337.122 | 3 | 1,779.041 | 2,734.654 | 0.047 | `GoldenModelTransport._load_sync` | `golden_model_transport.py:1090` | 3 |
| 5,337.076 | 3 | 1,779.025 | 2,734.648 | 0.243 | `GoldenModelTransport._load_c0_sync` | `golden_model_transport.py:1581` | 3 |
| 5,336.833 | 3 | 1,778.944 | 2,734.526 | 1.699 | `GoldenModelTransport._load_c0_source_threads_sync` | `golden_model_transport.py:1245` | 3 |
| 5,104.797 | 3 | 1,701.599 | 2,660.787 | 10.382 | `SourcePlanBridge.publish_all` | `golden_source_threads.py:1351` | 3 |
| 4,758.251 | 309 | 15.399 | 526.557 | 4.351 | `SourceThreadProcess.wait_ready` | `golden_source_threads.py:1129` | 3 |
| 4,413.581 | 1 | 4,413.581 | 4,413.581 | 0.290 | `golden_sampling` | `golden_serial.py:13785` | 1 |
| 4,374.469 | 315 | 13.887 | 250.212 | 4,366.161 | `SourceThreadProcess._read_message` | `golden_source_threads.py:900` | 3 |
| 4,357.993 | 1 | 4,357.993 | 4,357.993 | 0.802 | `ClownsharKSampler_Beta.main` | `samplers.py:1745` | 1 |
| 4,354.263 | 1 | 4,354.263 | 4,354.263 | 18.759 | `SharkSampler.main` | `samplers.py:153` | 1 |
| 4,279.842 | 2 | 2,139.921 | 4,105.404 | 0.145 | `CFGGuider.sample` | `samplers.py:1276` | 2 |
| 4,279.302 | 2 | 2,139.651 | 4,105.184 | 0.146 | `_cache_dit_outer_sample_wrapper` | `nodes.py:438` | 2 |
| 4,278.160 | 2 | 2,139.080 | 4,104.755 | 0.014 | `WrapperExecutor.__call__` | `patcher_extension.py:103` | 2 |
| 4,278.092 | 2 | 2,139.046 | 4,104.721 | 2.719 | `CFGGuider.outer_sample` | `samplers.py:1240` | 2 |
| 4,047.603 | 2 | 2,023.802 | 3,988.780 | 57.273 | `CFGGuider.inner_sample` | `samplers.py:1220` | 2 |
| 4,033.681 | 3 | 1,344.560 | 2,734.786 | 4.159 | `_WorkItem.run` | `thread.py:53` | 3 |
| 3,989.792 | 74 | 53.916 | 3,987.644 | 1.092 | `context_decorator.<locals>.decorate_context` | `_contextlib.py:120` | 2 |
| 3,989.413 | 2 | 1,994.707 | 3,988.188 | 0.197 | `KSAMPLER.sample` | `samplers.py:983` | 2 |
| 3,987.417 | 2 | 1,993.708 | 3,987.415 | 45.255 | `sample_rk_beta` | `rk_sampler_beta.py:110` | 2 |
| 3,676.521 | 14 | 262.609 | 2,610.828 | 1.990 | `BaseEventLoop._run_once` | `base_events.py:1845` | 5 |
| 3,432.395 | 17 | 201.906 | 643.397 | 4.287 | `RK_Method_Exponential.__call__` | `rk_method_beta.py:887` | 1 |
| 3,429.639 | 2 | 1,714.820 | 2,734.674 | 0.045 | `thread_traced.<locals>._run` | `full_execution_trace.py:276` | 2 |
| 3,427.064 | 17 | 201.592 | 642.581 | 1.459 | `RK_Method_Beta.model_denoised` | `rk_method_beta.py:137` | 1 |
| 3,425.138 | 17 | 201.479 | 642.118 | 0.116 | `KSamplerX0Inpaint.__call__` | `samplers.py:634` | 1 |
| 3,425.023 | 17 | 201.472 | 642.106 | 0.082 | `CFGGuider.__call__` | `samplers.py:1207` | 1 |
| 3,424.941 | 17 | 201.467 | 642.098 | 0.227 | `CFGGuider.outer_predict_noise` | `samplers.py:1210` | 1 |
| 3,424.438 | 17 | 201.438 | 642.056 | 0.372 | `SharkGuider.predict_noise` | `samplers.py:99` | 1 |
| 3,424.067 | 17 | 201.416 | 642.033 | 0.474 | `sampling_function` | `samplers.py:609` | 1 |
| 3,312.162 | 16 | 207.010 | 2,610.675 | 3,312.155 | `EpollSelector.select` | `selectors.py:451` | 5 |
| 3,308.104 | 1 | 3,308.104 | 3,308.104 | 0.338 | `golden_clip_forward` | `golden_serial.py:12452` | 1 |
| 3,295.379 | 1 | 3,295.379 | 3,295.379 | 0.027 | `CLIPTextEncode.encode` | `nodes.py:73` | 1 |
| 3,262.465 | 1 | 3,262.465 | 3,262.465 | 0.019 | `CLIP.encode_from_tokens_scheduled` | `sd.py:335` | 1 |
| 3,262.446 | 1 | 3,262.446 | 3,262.446 | 0.038 | `CLIP.encode_from_tokens` | `sd.py:396` | 1 |
| 3,089.690 | 1 | 3,089.690 | 3,089.690 | 0.131 | `SD1ClipModel.encode_token_weights` | `sd1_clip.py:741` | 1 |
| 3,089.558 | 1 | 3,089.558 | 3,089.558 | 1.946 | `ClipTokenWeightEncoder.encode_token_weights` | `sd1_clip.py:28` | 1 |
| 3,087.567 | 1 | 3,087.567 | 3,087.567 | 0.005 | `SDClipModel.encode` | `sd1_clip.py:305` | 1 |
| 3,087.446 | 1 | 3,087.446 | 3,087.446 | 0.089 | `SDClipModel.forward` | `sd1_clip.py:260` | 1 |
| 2,974.533 | 1 | 2,974.533 | 2,974.533 | 0.011 | `BaseLlama.forward` | `llama.py:998` | 1 |
| 2,974.337 | 1 | 2,974.337 | 2,974.337 | 390.736 | `Llama2_.forward` | `llama.py:824` | 1 |
| 2,824.983 | 3 | 941.661 | 1,924.394 | 0.029 | `Thread.run` | `threading.py:964` | 2 |
| 2,804.823 | 2 | 1,402.412 | 1,924.383 | 1,505.904 | `_worker` | `thread.py:69` | 2 |
| 2,611.038 | 1 | 2,611.038 | 2,611.038 | 0.065 | `golden.unet.source_h2d_transport` | `full_execution_trace.py:330` | 1 |
| 2,170.351 | 17 | 127.668 | 630.243 | 0.059 | `calc_cond_batch` | `samplers.py:208` | 1 |
| 2,170.290 | 17 | 127.664 | 630.237 | 0.093 | `_calc_cond_batch_outer` | `samplers.py:214` | 1 |
| 2,169.135 | 17 | 127.596 | 630.174 | 8.207 | `_calc_cond_batch` | `samplers.py:221` | 1 |
| 2,130.973 | 17 | 125.351 | 627.509 | 0.175 | `BaseModel.apply_model` | `model_base.py:204` | 1 |
| 2,130.270 | 17 | 125.310 | 627.458 | 3.231 | `BaseModel._apply_model` | `model_base.py:211` | 1 |
| 2,117.368 | 17 | 124.551 | 625.806 | 2,117.368 | `_enable_lightweight_cache.<locals>.cached_forward` | `nodes.py:215` | 1 |
| 2,010.436 | 2 | 1,005.218 | 1,917.958 | 1.021 | `golden_clip_load` | `golden_serial.py:11497` | 1 |
| 1,914.577 | 1 | 1,914.577 | 1,914.577 | 0.192 | `Llama2_.compute_freqs_cis` | `llama.py:815` | 1 |
| 1,914.385 | 1 | 1,914.385 | 1,914.385 | 204.433 | `precompute_freqs_cis` | `llama.py:445` | 1 |
| 1,907.651 | 1 | 1,907.651 | 1,907.651 | 1,907.651 | `golden.clip_load.source_open_read` | `full_execution_trace.py:330` | 1 |
| 1,907.589 | 1 | 1,907.589 | 1,907.589 | 0.033 | `_read_golden_m2_clip` | `golden_serial.py:11462` | 1 |
| 1,907.551 | 1 | 1,907.551 | 1,907.551 | 0.023 | `GoldenModelTransport.load_sync` | `golden_model_transport.py:1087` | 1 |
| 1,530.594 | 1017 | 1.505 | 1,448.014 | 74.583 | `_register_overrides_from_graph.<locals>.eager_router` | `registry.py:938` | 2 |

## 3. Per-stage call trees

Depth is uncapped; the wall floor limits it. Breadth is capped at 8 children plus any child at or above 10% of its parent.

### `golden_restore`

- Stage wall: **0.441 ms**

_Nothing below the stage body reached the threshold._

### `golden_request_setup`

- Stage wall: **1.888 ms**

- `golden_request_setup` 
  wall **1.888 ms**  self **1.888 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **1.857 ms**  self **0.083 ms**  `golden_serial.py:9977`

### `golden_clip_load`

- Stage wall: **2,015.766 ms**

- `golden_clip_load` 
  wall **2,015.766 ms**  self **16.794 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **1,924.394 ms**  self **0.011 ms**  `threading.py:964`
    - `_worker` 
      wall **1,924.383 ms**  self **1,320.623 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **603.746 ms**  self **4.132 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **599.578 ms**  self **0.219 ms**  `golden_serial.py:2341`
          - `load_text_encoder_state_dicts` 
            wall **543.729 ms**  self **0.216 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **542.976 ms**  self **0.240 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **454.285 ms**  self **0.025 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **454.260 ms**  self **0.028 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **454.232 ms**  self **2.605 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **451.627 ms**  self **0.138 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **429.508 ms**  self **0.969 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **426.128 ms**  self **5.902 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **419.958 ms**  self **259.350 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **120.652 ms**  self **14.915 ms**  `__init__.py:274`
                              - `loads` 
                                wall **105.737 ms**  self **0.005 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **105.732 ms**  self **0.034 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **105.698 ms**  self **105.698 ms**  `decoder.py:343`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **17.777 ms**  self **17.777 ms**  `tokenization_qwen2.py:174`
                            - `PreTrainedTokenizer.__init__` 
                              wall **16.929 ms**  self **0.900 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **15.546 ms**  self **6.260 ms**  `tokenization_utils.py:512`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **5.464 ms**  self **5.438 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **3.582 ms**  self **1.028 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **2.525 ms**  self **2.494 ms**  `tokenization_qwen2.py:215`
                            - `compile` 
                              wall **4.797 ms**  self **0.047 ms**  `_main.py:359`
                              - `_compile` 
                                wall **4.749 ms**  self **0.249 ms**  `_main.py:460`
                                - `Branch.pack_characters` 
                                  wall **2.288 ms**  self **0.004 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **2.284 ms**  self **0.008 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **2.236 ms**  self **0.016 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **2.102 ms**  self **0.033 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **2.016 ms**  self **0.005 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **2.012 ms**  self **2.012 ms**  `_regex_core.py:362`
                                - `_parse_pattern` 
                                  wall **1.206 ms**  self **0.024 ms**  `_regex_core.py:452`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **18.824 ms**  self **18.824 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **2.784 ms**  self **2.755 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **44.484 ms**  self **0.008 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **44.476 ms**  self **0.020 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **44.456 ms**  self **0.053 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **44.256 ms**  self **0.038 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **44.218 ms**  self **0.368 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **35.930 ms**  self **0.032 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **35.852 ms**  self **0.193 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **26.706 ms**  self **0.120 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **1.302 ms**  self **0.012 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.280 ms**  self **0.025 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.223 ms**  self **0.007 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.185 ms**  self **0.018 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.103 ms**  self **0.045 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.073 ms**  self **0.016 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.024 ms**  self **0.022 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.014 ms**  self **0.012 ms**  `llama.py:654`
                            - `disable_weight_init.Embedding.__init__` 
                              wall **8.652 ms**  self **0.110 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **8.404 ms**  self **8.404 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **7.794 ms**  self **0.419 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **4.569 ms**  self **0.003 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **4.566 ms**  self **0.013 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **4.538 ms**  self **0.007 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **4.502 ms**  self **0.034 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **33.621 ms**  self **0.459 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **28.021 ms**  self **0.012 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **28.007 ms**  self **0.039 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **27.966 ms**  self **6.344 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **21.621 ms**  self **0.038 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **21.056 ms**  self **0.020 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **20.169 ms**  self **0.126 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.480 ms**  self **0.041 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.340 ms**  self **0.029 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.066 ms**  self **0.023 ms**  `module.py:2589`
              - `archive_model_dtypes` 
                wall **5.900 ms**  self **1.102 ms**  `model_management.py:1045`
              - `ModelPatcherDynamic.__init__` 
                wall **3.401 ms**  self **0.059 ms**  `model_patcher.py:1757`
                - `ModelPatcher.__init__` 
                  wall **2.457 ms**  self **0.162 ms**  `model_patcher.py:341`
                  - `uuid4` 
                    wall **1.328 ms**  self **1.287 ms**  `uuid.py:721`
          - `_clip_meta_state_dict_from_header` 
            wall **55.582 ms**  self **49.462 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **5.851 ms**  self **3.789 ms**  `clip_qd_reader.py:300`
              - `loads` 
                wall **1.372 ms**  self **0.008 ms**  `__init__.py:299`
                - `JSONDecoder.decode` 
                  wall **1.365 ms**  self **0.012 ms**  `decoder.py:332`
                  - `JSONDecoder.raw_decode` 
                    wall **1.352 ms**  self **1.352 ms**  `decoder.py:343`
  - `golden_clip_load` 
    wall **1,917.958 ms**  self **0.573 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **1,907.589 ms**  self **0.033 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **1,907.551 ms**  self **0.023 ms**  `golden_model_transport.py:1087`
        - `GoldenModelTransport._load_sync` 
          wall **1,907.528 ms**  self **0.030 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **1,907.498 ms**  self **0.109 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **1,907.389 ms**  self **0.600 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **1,816.448 ms**  self **3.909 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **138.435 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **119.284 ms**  self **119.260 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **18.550 ms**  self **0.053 ms**  `golden_source_threads.py:1044`
                    - `_FileLock.__exit__` 
                      wall **12.598 ms**  self **12.598 ms**  `golden_source_threads.py:501`
                    - `_FileLock.__enter__` 
                      wall **5.867 ms**  self **5.867 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess.claim_ready` 
                  wall **74.532 ms**  self **0.056 ms**  `golden_source_threads.py:1175`
                  - `_FileLock.__enter__` 
                    wall **65.410 ms**  self **65.410 ms**  `golden_source_threads.py:494`
                  - `_FileLock.__exit__` 
                    wall **9.024 ms**  self **9.024 ms**  `golden_source_threads.py:501`
                - `SourceThreadProcess.wait_ready` 
                  wall **67.132 ms**  self **0.021 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **66.711 ms**  self **66.697 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **41.249 ms**  self **0.008 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **41.040 ms**  self **41.001 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **27.851 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **27.436 ms**  self **27.395 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **27.183 ms**  self **0.016 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **26.737 ms**  self **26.698 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **26.498 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **26.006 ms**  self **25.971 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **26.446 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **26.127 ms**  self **26.104 ms**  `golden_source_threads.py:900`
                _... 139 more children >= 1 ms omitted_
              - `GoldenModelTransport.inspect` 
                wall **37.129 ms**  self **0.045 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **36.875 ms**  self **36.210 ms**  `golden_model_transport.py:327`
              - `collect_placement_telemetry` 
                wall **25.958 ms**  self **0.010 ms**  `source_latency_telemetry.py:512`
                - `_collect_placement_telemetry_uncached` 
                  wall **25.948 ms**  self **13.185 ms**  `source_latency_telemetry.py:424`
                  - `_gpu_telemetry` 
                    wall **11.145 ms**  self **0.112 ms**  `source_latency_telemetry.py:359`
                    - `nvmlDeviceGetClockInfo` 
                      wall **4.810 ms**  self **4.803 ms**  `pynvml.py:3674`
                    - `nvmlDeviceGetPowerUsage` 
                      wall **2.316 ms**  self **2.295 ms**  `pynvml.py:3962`
                    - `nvmlDeviceGetPerformanceState` 
                      wall **1.544 ms**  self **1.523 ms**  `pynvml.py:3914`
                    - `nvmlDeviceGetCurrPcieLinkGeneration` 
                      wall **1.201 ms**  self **1.188 ms**  `pynvml.py:4609`
              - `GpuDestinationPool.acquire` 
                wall **6.981 ms**  self **0.042 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **6.921 ms**  self **6.783 ms**  `golden_model_transport.py:161`
              - `SourceThreadProcess.snapshot` 
                wall **5.313 ms**  self **0.621 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **3.810 ms**  self **0.414 ms**  `golden_source_threads.py:597`
              - `SourceThreadProcess.snapshot` 
                wall **4.880 ms**  self **0.551 ms**  `golden_source_threads.py:1240`
                - `_time_weighted_concurrency` 
                  wall **3.713 ms**  self **0.404 ms**  `golden_source_threads.py:597`
              - `GoldenModelTransport._views` 
                wall **4.725 ms**  self **4.725 ms**  `golden_model_transport.py:2042`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **2.349 ms**  self **0.134 ms**  `golden_qd_transport.py:3130`
              _... 1 more children >= 1 ms omitted_
    - `GoldenTelemetryRecorder.event` 
      wall **5.528 ms**  self **0.007 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **5.521 ms**  self **0.004 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **5.517 ms**  self **0.003 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **5.514 ms**  self **0.036 ms**  `copy.py:227`
            - `deepcopy` 
              wall **5.387 ms**  self **0.002 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **5.384 ms**  self **0.010 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **4.244 ms**  self **0.002 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **4.242 ms**  self **0.153 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **1.855 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **1.853 ms**  self **0.519 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.026 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_dict` 
                        wall **1.023 ms**  self **0.131 ms**  `copy.py:227`
    - `GoldenModelTransport.begin_layout_preresolve` 
      wall **1.118 ms**  self **0.022 ms**  `golden_model_transport.py:1015`
      - `Thread.start` 
        wall **1.060 ms**  self **0.648 ms**  `threading.py:938`
  - `golden.clip_load.source_open_read` 
    wall **1,907.651 ms**  self **1,907.651 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **92.478 ms**  self **0.448 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **56.890 ms**  self **1.165 ms**  `golden_serial.py:13060`
      - `validate_qd_adoption` 
        wall **7.321 ms**  self **1.513 ms**  `golden_serial.py:12971`
        - `Module.named_buffers` 
          wall **2.808 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.805 ms**  self **1.066 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.600 ms**  self **0.221 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.352 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.350 ms**  self **0.428 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.195 ms**  self **0.213 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.593 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.589 ms**  self **0.446 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.839 ms**  self **0.199 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.656 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.654 ms**  self **0.430 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **5.514 ms**  self **0.205 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **2.179 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.178 ms**  self **0.435 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **4.869 ms**  self **0.204 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **1.838 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.837 ms**  self **0.417 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **4.471 ms**  self **0.199 ms**  `golden_serial.py:13112`
        - `Module.named_buffers` 
          wall **1.665 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.664 ms**  self **0.417 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **26.271 ms**  self **0.459 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **21.869 ms**  self **0.007 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **21.861 ms**  self **0.019 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **21.841 ms**  self **0.079 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **21.762 ms**  self **0.011 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **21.308 ms**  self **0.017 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **20.317 ms**  self **0.097 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.973 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.630 ms**  self **0.029 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **2.341 ms**  self **0.011 ms**  `module.py:2589`
                        - `disable_weight_init.Linear._load_from_state_dict` 
                          wall **2.328 ms**  self **0.004 ms**  `ops.py:544`
                          - `disable_weight_init._lazy_load_from_state_dict` 
                            wall **2.324 ms**  self **0.012 ms**  `ops.py:494`
                            - `Module.__setattr__` 
                              wall **2.309 ms**  self **0.003 ms**  `module.py:1976`
                              - `Module.register_parameter` 
                                wall **2.305 ms**  self **2.304 ms**  `module.py:592`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.209 ms**  self **0.017 ms**  `module.py:2589`
    - `_clip_compute_identity` 
      wall **6.994 ms**  self **0.029 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **6.860 ms**  self **1.584 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **1.909 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.907 ms**  self **0.437 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **56.944 ms**  self **56.944 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **26.306 ms**  self **26.306 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **20.142 ms**  self **0.010 ms**  `threading.py:964`
    - `GoldenModelTransport.begin_layout_preresolve.<locals>.resolve` 
      wall **20.133 ms**  self **0.006 ms**  `golden_model_transport.py:1030`
      - `GoldenModelTransport.inspect` 
        wall **20.117 ms**  self **0.031 ms**  `golden_model_transport.py:999`
        - `_parse_layout` 
          wall **13.953 ms**  self **13.129 ms**  `golden_model_transport.py:327`
        - `_file_identity` 
          wall **6.133 ms**  self **6.133 ms**  `golden_model_transport.py:297`
  - `golden.clip_load.compute_ready_proof` 
    wall **7.012 ms**  self **7.012 ms**  `full_execution_trace.py:330`
  _... 1 more children >= 1 ms omitted_

### `golden_clip_forward`

- Stage wall: **3,308.169 ms**

- `golden_clip_forward` 
  wall **3,308.169 ms**  self **3,308.169 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **3,308.104 ms**  self **0.338 ms**  `golden_serial.py:12452`
    - `GoldenSerialRunner.run_closure` 
      wall **3,298.096 ms**  self **0.057 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **3,295.796 ms**  self **0.049 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **3,295.542 ms**  self **0.035 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **3,295.379 ms**  self **0.027 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **3,262.465 ms**  self **0.019 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **3,262.446 ms**  self **0.038 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **3,089.690 ms**  self **0.131 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **3,089.558 ms**  self **1.946 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **3,087.567 ms**  self **0.005 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **3,087.562 ms**  self **0.012 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **3,087.549 ms**  self **0.103 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **3,087.446 ms**  self **0.089 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **2,974.563 ms**  self **0.008 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **2,974.555 ms**  self **0.022 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **2,974.533 ms**  self **0.011 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **2,974.520 ms**  self **0.008 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **2,974.512 ms**  self **0.175 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **2,974.337 ms**  self **390.736 ms**  `llama.py:824`
                                        - `prefetch_queue_pop` 
                                          wall **508.497 ms**  self **0.004 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **508.492 ms**  self **0.009 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **508.483 ms**  self **0.008 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **508.476 ms**  self **0.022 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **508.454 ms**  self **0.291 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **442.637 ms**  self **0.009 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **442.628 ms**  self **0.227 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **442.401 ms**  self **94.188 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **274.466 ms**  self **0.018 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **274.448 ms**  self **0.028 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **274.420 ms**  self **0.043 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **274.358 ms**  self **268.196 ms**  `ops.py:566`
                                                        - `apply_rope` 
                                                          wall **69.936 ms**  self **69.936 ms**  `llama.py:492`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.080 ms**  self **0.008 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.071 ms**  self **0.026 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **1.045 ms**  self **0.027 ms**  `ops.py:570`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.036 ms**  self **0.016 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.020 ms**  self **0.021 ms**  `module.py:1787`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **29.291 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **29.286 ms**  self **0.010 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **29.276 ms**  self **0.142 ms**  `llama.py:644`
                                                        - `silu` 
                                                          wall **27.650 ms**  self **27.650 ms**  `functional.py:2429`
                                        - `prefetch_queue_pop` 
                                          wall **5.133 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **5.130 ms**  self **0.007 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **5.124 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **5.117 ms**  self **0.028 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **5.089 ms**  self **0.115 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **3.732 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **3.725 ms**  self **0.084 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **3.641 ms**  self **1.736 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.050 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.048 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.044 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.038 ms**  self **0.010 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.028 ms**  self **0.152 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.715 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.707 ms**  self **0.041 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.666 ms**  self **1.254 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.043 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.042 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.039 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **4.035 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **4.027 ms**  self **0.186 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.917 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.913 ms**  self **0.039 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.874 ms**  self **1.265 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **4.008 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **4.006 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **4.001 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.996 ms**  self **0.007 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.988 ms**  self **0.091 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.896 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.891 ms**  self **0.022 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.869 ms**  self **1.183 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.951 ms**  self **0.001 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.950 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.946 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.941 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.933 ms**  self **0.134 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.645 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.639 ms**  self **0.050 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.588 ms**  self **1.006 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.941 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.939 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.933 ms**  self **0.008 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.926 ms**  self **0.019 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.906 ms**  self **0.235 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.607 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.601 ms**  self **0.018 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.583 ms**  self **1.154 ms**  `llama.py:540`
                                        - `prefetch_queue_pop` 
                                          wall **3.782 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **3.781 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **3.775 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3.769 ms**  self **0.009 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **3.760 ms**  self **0.143 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **2.590 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **2.586 ms**  self **0.057 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **2.528 ms**  self **1.306 ms**  `llama.py:540`
                                        _... 11 more children >= 1 ms omitted_
  - `BaseEventLoop._run_once` 
    wall **46.840 ms**  self **0.010 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **46.821 ms**  self **12.748 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **46.784 ms**  self **0.008 ms**  `golden_serial.py:15624`

### `golden_unet_load`

- Stage wall: **2,795.145 ms**

- `golden_unet_load` 
  wall **2,795.145 ms**  self **47.458 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **2,734.786 ms**  self **0.011 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **2,734.674 ms**  self **0.020 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **2,734.654 ms**  self **0.006 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **2,734.648 ms**  self **0.122 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **2,734.526 ms**  self **0.760 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **2,660.787 ms**  self **6.311 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **355.030 ms**  self **0.041 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **250.212 ms**  self **250.212 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._recover_ready_from_table` 
                  wall **70.391 ms**  self **0.047 ms**  `golden_source_threads.py:1100`
                  - `_FileLock.__enter__` 
                    wall **70.254 ms**  self **70.254 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess._read_message` 
                  wall **33.825 ms**  self **33.797 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **45.349 ms**  self **0.014 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **31.538 ms**  self **31.509 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **13.573 ms**  self **0.053 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__enter__` 
                    wall **7.736 ms**  self **7.736 ms**  `golden_source_threads.py:494`
                  - `_FileLock.__exit__` 
                    wall **5.746 ms**  self **5.746 ms**  `golden_source_threads.py:501`
              - `SourceThreadProcess.wait_ready` 
                wall **40.493 ms**  self **0.031 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **40.223 ms**  self **40.183 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **34.091 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **32.217 ms**  self **32.177 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._poll_child` 
                  wall **1.408 ms**  self **0.009 ms**  `golden_source_threads.py:1009`
                  - `Popen.poll` 
                    wall **1.399 ms**  self **0.002 ms**  `subprocess.py:1233`
                    - `Popen._internal_poll` 
                      wall **1.397 ms**  self **1.397 ms**  `subprocess.py:1966`
              - `SourceThreadProcess.wait_ready` 
                wall **29.527 ms**  self **0.014 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **24.208 ms**  self **24.187 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **5.066 ms**  self **0.029 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__enter__` 
                    wall **4.798 ms**  self **4.798 ms**  `golden_source_threads.py:494`
              - `SourceThreadProcess.wait_ready` 
                wall **29.329 ms**  self **0.013 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **17.582 ms**  self **0.053 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__enter__` 
                    wall **17.139 ms**  self **17.139 ms**  `golden_source_threads.py:494`
                - `SourceThreadProcess._read_message` 
                  wall **11.295 ms**  self **11.269 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **29.047 ms**  self **0.011 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **24.275 ms**  self **24.254 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **4.383 ms**  self **0.019 ms**  `golden_source_threads.py:1044`
                  - `_FileLock.__enter__` 
                    wall **4.237 ms**  self **4.237 ms**  `golden_source_threads.py:494`
              - `SourceThreadProcess.wait_ready` 
                wall **28.032 ms**  self **0.015 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **27.760 ms**  self **27.732 ms**  `golden_source_threads.py:900`
              _... 178 more children >= 1 ms omitted_
            - `GoldenQDTransport.finalize_external_ready` 
              wall **32.698 ms**  self **0.170 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **29.855 ms**  self **0.014 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **29.828 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **29.817 ms**  self **0.007 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **29.808 ms**  self **29.803 ms**  `threading.py:288`
              - `_Telemetry.snapshot` 
                wall **1.194 ms**  self **0.004 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **1.189 ms**  self **0.137 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **1.017 ms**  self **0.007 ms**  `golden_qd_transport.py:2016`
                    - `_json_safe.<locals>.<dictcomp>` 
                      wall **1.003 ms**  self **0.179 ms**  `golden_qd_transport.py:2022`
              - `GoldenQDTransport._record_ranges` 
                wall **1.031 ms**  self **0.794 ms**  `golden_qd_transport.py:3261`
            - `SourceThreadProcess.snapshot` 
              wall **13.396 ms**  self **0.940 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **9.205 ms**  self **0.721 ms**  `golden_source_threads.py:597`
              - `_validate_memcpy_gaps` 
                wall **2.196 ms**  self **0.147 ms**  `golden_source_threads.py:648`
                - `_validate_memcpy_gaps.<locals>.<genexpr>` 
                  wall **1.872 ms**  self **1.872 ms**  `golden_source_threads.py:649`
            - `SourceThreadProcess.snapshot` 
              wall **10.371 ms**  self **0.917 ms**  `golden_source_threads.py:1240`
              - `_time_weighted_concurrency` 
                wall **8.536 ms**  self **0.665 ms**  `golden_source_threads.py:597`
            - `GpuDestinationPool.acquire` 
              wall **6.986 ms**  self **0.028 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **6.949 ms**  self **6.784 ms**  `golden_model_transport.py:161`
            - `GoldenModelTransport._views` 
              wall **3.805 ms**  self **3.805 ms**  `golden_model_transport.py:2042`
            - `summarize_source_operations` 
              wall **3.095 ms**  self **1.761 ms**  `source_latency_telemetry.py:68`
  - `golden.unet.source_h2d_transport` 
    wall **2,611.038 ms**  self **0.065 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop._run_once` 
    wall **2,610.828 ms**  self **0.029 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **2,610.675 ms**  self **2,610.672 ms**  `selectors.py:451`
  - `Llama2_.compute_freqs_cis` 
    wall **1,914.577 ms**  self **0.192 ms**  `llama.py:815`
    - `precompute_freqs_cis` 
      wall **1,914.385 ms**  self **204.433 ms**  `llama.py:445`
      - `_register_overrides_from_graph.<locals>.eager_router` 
        wall **1,448.014 ms**  self **0.019 ms**  `registry.py:938`
        - `_register_overrides_from_graph.<locals>._dispatch` 
          wall **1,447.990 ms**  self **0.049 ms**  `registry.py:926`
          - `OpOverloadPacket.__call__` 
            wall **1,447.233 ms**  self **0.105 ms**  `_ops.py:1338`
            - `_bmm_outer_product_impl` 
              wall **1,447.127 ms**  self **35.823 ms**  `triton_impl.py:18`
              - `bmm_outer_product` 
                wall **1,411.267 ms**  self **0.263 ms**  `triton_kernels.py:77`
                - `_make_wrapper.<locals>.wrapper` 
                  wall **1,410.888 ms**  self **0.007 ms**  `instrumentation.py:202`
                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                    wall **1,410.829 ms**  self **0.021 ms**  `jit.py:374`
                    - `JITFunction.run` 
                      wall **1,410.808 ms**  self **0.101 ms**  `jit.py:726`
                      - `DriverConfig.active` 
                        wall **771.743 ms**  self **0.007 ms**  `driver.py:36`
                        - `DriverConfig.default` 
                          wall **771.737 ms**  self **0.016 ms**  `driver.py:30`
                          - `_create_driver` 
                            wall **771.721 ms**  self **0.028 ms**  `driver.py:8`
                            - `CudaDriver.__init__` 
                              wall **771.650 ms**  self **0.030 ms**  `driver.py:341`
                              - `CudaUtils.__init__` 
                                wall **771.590 ms**  self **0.040 ms**  `driver.py:100`
                                - `compile_module_from_file` 
                                  wall **749.621 ms**  self **0.019 ms**  `build.py:193`
                                  - `_compile_so_from_file` 
                                    wall **749.602 ms**  self **1.192 ms**  `build.py:157`
                                    - `_compile_so` 
                                      wall **748.356 ms**  self **0.194 ms**  `build.py:132`
                                      - `_build` 
                                        wall **739.788 ms**  self **0.041 ms**  `build.py:60`
                                        - `check_call` 
                                          wall **737.734 ms**  self **0.011 ms**  `subprocess.py:398`
                                          - `call` 
                                            wall **737.720 ms**  self **0.019 ms**  `subprocess.py:381`
                                            - `Popen.wait` 
                                              wall **732.443 ms**  self **0.003 ms**  `subprocess.py:1259`
                                              - `Popen._wait` 
                                                wall **732.439 ms**  self **0.017 ms**  `subprocess.py:2014`
                                                - `Popen._try_wait` 
                                                  wall **732.420 ms**  self **732.420 ms**  `subprocess.py:2001`
                                            - `Popen.__init__` 
                                              wall **5.250 ms**  self **0.016 ms**  `subprocess.py:807`
                                              - `Popen._execute_child` 
                                                wall **5.107 ms**  self **5.048 ms**  `subprocess.py:1789`
                                        - `_find_compiler` 
                                          wall **1.126 ms**  self **0.023 ms**  `build.py:21`
                                      - `_get_cache_manager` 
                                        wall **5.947 ms**  self **0.207 ms**  `build.py:117`
                                        - `platform_key` 
                                          wall **5.303 ms**  self **0.025 ms**  `build.py:94`
                                          - `architecture` 
                                            wall **5.266 ms**  self **0.034 ms**  `platform.py:646`
                                            - `_syscmd_file` 
                                              wall **5.232 ms**  self **0.760 ms**  `platform.py:602`
                                              - `check_output` 
                                                wall **4.310 ms**  self **0.007 ms**  `subprocess.py:417`
                                                - `run` 
                                                  wall **4.303 ms**  self **0.007 ms**  `subprocess.py:506`
                                                  - `Popen.__init__` 
                                                    wall **4.296 ms**  self **0.166 ms**  `subprocess.py:807`
                                                    - `Popen._execute_child` 
                                                      wall **3.943 ms**  self **3.827 ms**  `subprocess.py:1789`
                                      - `_load_module_from_path` 
                                        wall **1.237 ms**  self **1.237 ms**  `build.py:108`
                                - `library_dirs` 
                                  wall **21.929 ms**  self **0.015 ms**  `driver.py:49`
                                  - `libcuda_dirs` 
                                    wall **21.914 ms**  self **0.171 ms**  `driver.py:25`
                                    - `check_output` 
                                      wall **21.405 ms**  self **0.017 ms**  `subprocess.py:417`
                                      - `run` 
                                        wall **21.385 ms**  self **0.054 ms**  `subprocess.py:506`
                                        - `Popen.communicate` 
                                          wall **14.020 ms**  self **13.834 ms**  `subprocess.py:1165`
                                        - `Popen.__init__` 
                                          wall **7.301 ms**  self **0.410 ms**  `subprocess.py:807`
                                          - `Popen._execute_child` 
                                            wall **6.734 ms**  self **6.413 ms**  `subprocess.py:1789`
                      - `JITFunction._do_compile` 
                        wall **352.951 ms**  self **0.055 ms**  `jit.py:877`
                        - `compile` 
                          wall **352.875 ms**  self **24.532 ms**  `compiler.py:226`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **73.549 ms**  self **0.012 ms**  `compiler.py:606`
                            - `CUDABackend.make_ptx` 
                              wall **73.537 ms**  self **72.225 ms**  `compiler.py:480`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **69.371 ms**  self **0.101 ms**  `compiler.py:605`
                            - `CUDABackend.make_llir` 
                              wall **69.270 ms**  self **69.135 ms**  `compiler.py:367`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **52.585 ms**  self **0.054 ms**  `compiler.py:607`
                            - `CUDABackend.make_cubin` 
                              wall **52.528 ms**  self **0.734 ms**  `compiler.py:513`
                              - `run` 
                                wall **51.096 ms**  self **0.017 ms**  `subprocess.py:506`
                                - `Popen.communicate` 
                                  wall **47.346 ms**  self **0.006 ms**  `subprocess.py:1165`
                                  - `Popen.wait` 
                                    wall **47.340 ms**  self **0.002 ms**  `subprocess.py:1259`
                                    - `Popen._wait` 
                                      wall **47.338 ms**  self **0.008 ms**  `subprocess.py:2014`
                                      - `Popen._try_wait` 
                                        wall **47.328 ms**  self **47.328 ms**  `subprocess.py:2001`
                                - `Popen.__init__` 
                                  wall **3.725 ms**  self **0.019 ms**  `subprocess.py:807`
                                  - `Popen._execute_child` 
                                    wall **3.672 ms**  self **0.020 ms**  `subprocess.py:1789`
                                    - `Popen._posix_spawn` 
                                      wall **3.652 ms**  self **3.631 ms**  `subprocess.py:1750`
                          - `get_cache_key` 
                            wall **41.001 ms**  self **0.031 ms**  `cache.py:319`
                            - `CUDABackend.hash` 
                              wall **35.039 ms**  self **0.011 ms**  `compiler.py:611`
                              - `get_ptxas_version` 
                                wall **35.028 ms**  self **0.023 ms**  `compiler.py:42`
                                - `get_ptxas` 
                                  wall **25.406 ms**  self **0.006 ms**  `compiler.py:38`
                                  - `env_base.__get__` 
                                    wall **25.401 ms**  self **0.003 ms**  `knobs.py:76`
                                    - `env_nvidia_tool.get` 
                                      wall **25.397 ms**  self **0.005 ms**  `knobs.py:203`
                                      - `env_nvidia_tool.transform` 
                                        wall **25.393 ms**  self **0.011 ms**  `knobs.py:206`
                                        - `NvidiaTool.from_path` 
                                          wall **25.382 ms**  self **0.016 ms**  `knobs.py:181`
                                          - `check_output` 
                                            wall **24.961 ms**  self **0.015 ms**  `subprocess.py:417`
                                            - `run` 
                                              wall **24.944 ms**  self **0.029 ms**  `subprocess.py:506`
                                              - `Popen.__init__` 
                                                wall **12.653 ms**  self **0.435 ms**  `subprocess.py:807`
                                                - `Popen._execute_child` 
                                                  wall **11.935 ms**  self **11.603 ms**  `subprocess.py:1789`
                                              - `Popen.communicate` 
                                                wall **12.254 ms**  self **12.213 ms**  `subprocess.py:1165`
                                - `check_output` 
                                  wall **9.578 ms**  self **0.010 ms**  `subprocess.py:417`
                                  - `run` 
                                    wall **9.566 ms**  self **0.023 ms**  `subprocess.py:506`
                                    - `Popen.communicate` 
                                      wall **6.640 ms**  self **6.560 ms**  `subprocess.py:1165`
                                    - `Popen.__init__` 
                                      wall **2.893 ms**  self **0.050 ms**  `subprocess.py:807`
                                      - `Popen._execute_child` 
                                        wall **2.800 ms**  self **2.722 ms**  `subprocess.py:1789`
                            - `CUDAOptions.hash` 
                              wall **3.217 ms**  self **0.073 ms**  `compiler.py:153`
                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                wall **3.083 ms**  self **0.015 ms**  `compiler.py:155`
                                - `file_hash` 
                                  wall **3.068 ms**  self **3.068 ms**  `compiler.py:97`
                            - `ASTSource.hash` 
                              wall **2.715 ms**  self **0.048 ms**  `compiler.py:71`
                              - `JITCallable.cache_key` 
                                wall **2.656 ms**  self **0.093 ms**  `jit.py:515`
                                - `JITCallable.parse` 
                                  wall **1.437 ms**  self **0.026 ms**  `jit.py:546`
                                  - `parse` 
                                    wall **1.411 ms**  self **1.411 ms**  `ast.py:33`
                                - `NodeVisitor.visit` 
                                  wall **1.038 ms**  self **0.013 ms**  `ast.py:414`
                                  - `NodeVisitor.generic_visit` 
                                    wall **1.025 ms**  self **0.012 ms**  `ast.py:420`
                                    - `NodeVisitor.visit` 
                                      wall **1.009 ms**  self **0.007 ms**  `ast.py:414`
                                      - `DependenciesFinder.visit_FunctionDef` 
                                        wall **1.002 ms**  self **0.007 ms**  `jit.py:196`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **29.284 ms**  self **0.095 ms**  `compiler.py:602`
                            - `CUDABackend.make_ttgir` 
                              wall **29.188 ms**  self **29.188 ms**  `compiler.py:260`
                          - `ASTSource.make_ir` 
                            wall **28.757 ms**  self **0.036 ms**  `compiler.py:78`
                            - `ast_to_ttir` 
                              wall **28.721 ms**  self **1.573 ms**  `code_generator.py:1662`
                              - `CodeGenerator.visit` 
                                wall **24.550 ms**  self **0.061 ms**  `code_generator.py:1581`
                                - `NodeVisitor.visit` 
                                  wall **24.488 ms**  self **0.012 ms**  `ast.py:414`
                                  - `CodeGenerator.visit_Module` 
                                    wall **24.477 ms**  self **0.005 ms**  `code_generator.py:519`
                                    - `NodeVisitor.generic_visit` 
                                      wall **24.471 ms**  self **0.013 ms**  `ast.py:420`
                                      - `CodeGenerator.visit` 
                                        wall **24.454 ms**  self **0.033 ms**  `code_generator.py:1581`
                                        - `NodeVisitor.visit` 
                                          wall **24.421 ms**  self **0.017 ms**  `ast.py:414`
                                          - `CodeGenerator.visit_FunctionDef` 
                                            wall **24.404 ms**  self **0.183 ms**  `code_generator.py:628`
                                            - `CodeGenerator.visit_compound_statement` 
                                              wall **21.889 ms**  self **0.036 ms**  `code_generator.py:508`
                                              - `CodeGenerator.visit` 
                                                wall **8.297 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **8.291 ms**  self **0.001 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **8.289 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **8.236 ms**  self **0.016 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **8.220 ms**  self **0.002 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **8.219 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **7.910 ms**  self **0.014 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **7.895 ms**  self **0.091 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **7.558 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **7.554 ms**  self **0.002 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **7.552 ms**  self **0.001 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **7.551 ms**  self **0.010 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **7.538 ms**  self **7.538 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **3.740 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **3.733 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **3.730 ms**  self **0.012 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **3.689 ms**  self **0.016 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **3.674 ms**  self **0.003 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **3.671 ms**  self **0.017 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.call_Function` 
                                                            wall **3.544 ms**  self **0.007 ms**  `code_generator.py:1398`
                                                            - `CodeGenerator.call_JitFunction` 
                                                              wall **3.537 ms**  self **0.054 ms**  `code_generator.py:1358`
                                                              - `CodeGenerator.visit` 
                                                                wall **3.196 ms**  self **0.003 ms**  `code_generator.py:1581`
                                                                - `NodeVisitor.visit` 
                                                                  wall **3.193 ms**  self **0.003 ms**  `ast.py:414`
                                                                  - `CodeGenerator.visit_Module` 
                                                                    wall **3.190 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                    - `NodeVisitor.generic_visit` 
                                                                      wall **3.188 ms**  self **0.005 ms**  `ast.py:420`
                                                                      - `CodeGenerator.visit` 
                                                                        wall **3.181 ms**  self **3.181 ms**  `code_generator.py:1581`
                                              - `CodeGenerator.visit` 
                                                wall **2.121 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **2.114 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **2.112 ms**  self **0.010 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **2.067 ms**  self **0.014 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **2.053 ms**  self **0.003 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **2.050 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                          - `CodeGenerator.visit` 
                                                            wall **1.594 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                            - `NodeVisitor.visit` 
                                                              wall **1.586 ms**  self **0.003 ms**  `ast.py:414`
                                                              - `CodeGenerator.visit_BinOp` 
                                                                wall **1.584 ms**  self **0.006 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.802 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.796 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Expr` 
                                                    wall **1.793 ms**  self **0.004 ms**  `code_generator.py:1556`
                                                    - `NodeVisitor.generic_visit` 
                                                      wall **1.790 ms**  self **0.005 ms**  `ast.py:420`
                                                      - `CodeGenerator.visit` 
                                                        wall **1.783 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                        - `NodeVisitor.visit` 
                                                          wall **1.776 ms**  self **0.002 ms**  `ast.py:414`
                                                          - `CodeGenerator.visit_Call` 
                                                            wall **1.774 ms**  self **0.009 ms**  `code_generator.py:1455`
                                                            - `CodeGenerator.visit` 
                                                              wall **1.544 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                              - `NodeVisitor.visit` 
                                                                wall **1.539 ms**  self **0.002 ms**  `ast.py:414`
                                                                - `CodeGenerator.visit_BinOp` 
                                                                  wall **1.537 ms**  self **0.004 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.406 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.399 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.398 ms**  self **0.013 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.323 ms**  self **0.023 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.300 ms**  self **0.008 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.292 ms**  self **0.004 ms**  `code_generator.py:810`
                                              - `CodeGenerator.visit` 
                                                wall **1.143 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.137 ms**  self **0.002 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.135 ms**  self **0.009 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.103 ms**  self **0.013 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.090 ms**  self **0.003 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_Call` 
                                                          wall **1.087 ms**  self **0.010 ms**  `code_generator.py:1455`
                                              - `CodeGenerator.visit` 
                                                wall **1.078 ms**  self **0.009 ms**  `code_generator.py:1581`
                                                - `NodeVisitor.visit` 
                                                  wall **1.069 ms**  self **0.003 ms**  `ast.py:414`
                                                  - `CodeGenerator.visit_Assign` 
                                                    wall **1.067 ms**  self **0.011 ms**  `code_generator.py:727`
                                                    - `CodeGenerator.visit` 
                                                      wall **1.028 ms**  self **0.019 ms**  `code_generator.py:1581`
                                                      - `NodeVisitor.visit` 
                                                        wall **1.010 ms**  self **0.004 ms**  `ast.py:414`
                                                        - `CodeGenerator.visit_BinOp` 
                                                          wall **1.006 ms**  self **0.004 ms**  `code_generator.py:810`
                              - `JITCallable.parse` 
                                wall **1.290 ms**  self **0.014 ms**  `jit.py:546`
                                - `parse` 
                                  wall **1.276 ms**  self **1.276 ms**  `ast.py:33`
                          - `FileCacheManager.put` 
                            wall **13.177 ms**  self **12.987 ms**  `cache.py:103`
                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                            wall **6.123 ms**  self **0.057 ms**  `compiler.py:601`
                            - `CUDABackend.make_ttir` 
                              wall **6.067 ms**  self **6.067 ms**  `compiler.py:244`
                          _... 6 more children >= 1 ms omitted_
                      - `dynamic_func` 
                        wall **281.404 ms**  self **281.369 ms**  `<string>:2`
                      - `CompiledKernel.launch_metadata` 
                        wall **2.822 ms**  self **0.020 ms**  `compiler.py:493`
                        - `CompiledKernel._init_handles` 
                          wall **2.799 ms**  self **0.290 ms**  `compiler.py:448`
                          - `max_shared_mem` 
                            wall **2.204 ms**  self **2.203 ms**  `compiler.py:133`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **161.899 ms**  self **0.019 ms**  `_tensor.py:32`
        - `Tensor.__rpow__` 
          wall **161.880 ms**  self **161.880 ms**  `_tensor.py:1155`
      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
        wall **100.039 ms**  self **0.012 ms**  `_tensor.py:32`
        - `Tensor.__rdiv__` 
          wall **100.027 ms**  self **100.027 ms**  `_tensor.py:1120`
  - `CLIP.load_model` 
    wall **172.588 ms**  self **0.027 ms**  `sd.py:459`
    - `load_models_gpu` 
      wall **172.557 ms**  self **0.142 ms**  `model_management.py:909`
      - `LoadedModel.model_load` 
        wall **126.416 ms**  self **0.033 ms**  `model_management.py:782`
        - `LoadedModel.model_use_more_vram` 
          wall **126.349 ms**  self **0.007 ms**  `model_management.py:817`
          - `ModelPatcherDynamic.partially_load` 
            wall **126.342 ms**  self **0.294 ms**  `model_patcher.py:2141`
            - `ModelPatcherDynamic.load` 
              wall **125.961 ms**  self **8.773 ms**  `model_patcher.py:1853`
              - `ModelPatcher._load_list` 
                wall **56.168 ms**  self **20.114 ms**  `model_patcher.py:945`
                - `module_size` 
                  wall **5.873 ms**  self **0.004 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **5.870 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **5.861 ms**  self **5.861 ms**  `module.py:2148`
                - `module_size` 
                  wall **2.486 ms**  self **0.002 ms**  `model_management.py:631`
                  - `Module.state_dict` 
                    wall **2.484 ms**  self **0.007 ms**  `module.py:2199`
                    - `Module._save_to_state_dict` 
                      wall **2.477 ms**  self **2.477 ms**  `module.py:2148`
              - `Module.named_buffers` 
                wall **3.063 ms**  self **0.004 ms**  `module.py:2754`
                - `Module._named_members` 
                  wall **3.059 ms**  self **0.458 ms**  `module.py:2650`
              - `ModelPatcherDynamic._vbar_get` 
                wall **2.260 ms**  self **0.024 ms**  `model_patcher.py:1797`
                - `ModelVBAR.__init__` 
                  wall **2.236 ms**  self **2.163 ms**  `model_vbar.py:50`
              - `HostBuffer.__del__` 
                wall **1.394 ms**  self **1.379 ms**  `host_buffer.py:125`
              - `HostBuffer.__init__` 
                wall **1.351 ms**  self **1.342 ms**  `host_buffer.py:79`
      - `LoadedModel.model_memory_required` 
        wall **45.124 ms**  self **0.010 ms**  `model_management.py:776`
        - `LoadedModel.model_memory` 
          wall **45.112 ms**  self **0.009 ms**  `model_management.py:767`
          - `ModelPatcher.model_size` 
            wall **45.103 ms**  self **16.180 ms**  `model_patcher.py:405`
            - `module_size` 
              wall **28.923 ms**  self **0.168 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **28.755 ms**  self **0.022 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **28.727 ms**  self **0.018 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **28.370 ms**  self **0.019 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **28.347 ms**  self **0.018 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **28.101 ms**  self **0.076 ms**  `module.py:2199`
                        - `Module.state_dict` 
                          wall **8.330 ms**  self **0.012 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **8.085 ms**  self **0.009 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **8.053 ms**  self **0.004 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **8.049 ms**  self **8.049 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **5.170 ms**  self **0.014 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **3.823 ms**  self **0.013 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **3.740 ms**  self **0.004 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **3.736 ms**  self **3.736 ms**  `module.py:2148`
                        - `Module.state_dict` 
                          wall **1.575 ms**  self **0.012 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **1.257 ms**  self **0.015 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.125 ms**  self **0.005 ms**  `module.py:2199`
                              - `Module._save_to_state_dict` 
                                wall **1.120 ms**  self **1.120 ms**  `module.py:2148`
  - `BaseEventLoop._run_once` 
    wall **136.660 ms**  self **0.022 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **122.753 ms**  self **3.122 ms**  `events.py:78`
      - `golden.unet.header_config_preflight` 
        wall **60.150 ms**  self **60.150 ms**  `full_execution_trace.py:330`
      - `golden.unet.skeleton_patcher_construction` 
        wall **59.482 ms**  self **59.482 ms**  `full_execution_trace.py:330`
    - `Handle._run` 
      wall **8.142 ms**  self **8.142 ms**  `events.py:78`
    - `EpollSelector.select` 
      wall **5.741 ms**  self **5.741 ms**  `selectors.py:451`
  - `_overlap_owner_call` 
    wall **122.660 ms**  self **0.002 ms**  `golden_serial.py:15624`
    - `_unet_load_with_worker_stage` 
      wall **122.657 ms**  self **0.002 ms**  `golden_parallel.py:517`
      - `golden_unet_load` 
        wall **122.655 ms**  self **0.260 ms**  `golden_serial.py:13274`
        - `Lumina2.get_model` 
          wall **52.502 ms**  self **0.014 ms**  `supported_models.py:1193`
          - `Lumina2.__init__` 
            wall **52.488 ms**  self **0.052 ms**  `model_base.py:1504`
            - `BaseModel.__init__` 
              wall **52.433 ms**  self **29.155 ms**  `model_base.py:164`
              - `model_sampling` 
                wall **8.027 ms**  self **0.071 ms**  `model_base.py:110`
                - `ModelSamplingDiscreteFlow.__init__` 
                  wall **7.954 ms**  self **0.012 ms**  `model_sampling.py:285`
                  - `ModelSamplingDiscreteFlow.set_parameters` 
                    wall **7.918 ms**  self **6.262 ms**  `model_sampling.py:298`
                    - `ModelSamplingDiscreteFlow.sigma` 
                      wall **1.637 ms**  self **0.310 ms**  `model_sampling.py:318`
                      - `time_snr_shift` 
                        wall **1.326 ms**  self **1.326 ms**  `model_sampling.py:279`
              - `archive_model_dtypes` 
                wall **7.058 ms**  self **1.238 ms**  `model_management.py:1045`
              - `Module.eval` 
                wall **4.858 ms**  self **0.002 ms**  `module.py:2916`
                - `Module.train` 
                  wall **4.857 ms**  self **0.014 ms**  `module.py:2894`
                  - `Module.train` 
                    wall **4.239 ms**  self **0.024 ms**  `module.py:2894`
              - `Module.requires_grad_` 
                wall **3.082 ms**  self **0.222 ms**  `module.py:2934`
        - `golden_unet_load.<locals>.<dictcomp>` 
          wall **34.995 ms**  self **34.995 ms**  `golden_serial.py:13361`
        - `model_config_from_unet` 
          wall **15.595 ms**  self **0.126 ms**  `model_detection.py:1283`
          - `detect_unet_config` 
            wall **15.076 ms**  self **9.435 ms**  `model_detection.py:44`
            - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
              wall **3.083 ms**  self **0.116 ms**  `wrappers.py:291`
              - `std` 
                wall **2.965 ms**  self **0.426 ms**  `__init__.py:2620`
                - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
                  wall **1.313 ms**  self **0.020 ms**  `wrappers.py:291`
                  - `elementwise_unary_scalar_wrapper.<locals>._fn` 
                    wall **1.292 ms**  self **0.013 ms**  `wrappers.py:491`
                    - `_disable_dynamo.<locals>.inner` 
                      wall **1.279 ms**  self **0.105 ms**  `_compile.py:42`
            - `count_blocks` 
              wall **2.515 ms**  self **2.515 ms**  `model_detection.py:10`
        - `golden_unet_load.<locals>.<listcomp>` 
          wall **8.071 ms**  self **8.071 ms**  `golden_serial.py:13345`
        - `ModelPatcherDynamic.__init__` 
          wall **6.904 ms**  self **0.019 ms**  `model_patcher.py:1757`
          - `ModelPatcher.__init__` 
            wall **3.632 ms**  self **0.047 ms**  `model_patcher.py:341`
            - `uuid4` 
              wall **2.253 ms**  self **2.238 ms**  `uuid.py:721`
            - `uuid4` 
              wall **1.298 ms**  self **1.288 ms**  `uuid.py:721`
          - `ModelPatcherDynamic.register_load_device` 
            wall **3.228 ms**  self **0.021 ms**  `model_patcher.py:1770`
            - `HostBuffer.__init__` 
              wall **2.289 ms**  self **2.278 ms**  `host_buffer.py:79`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.660 ms**  self **0.021 ms**  `golden_serial.py:13404`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.080 ms**  self **0.021 ms**  `golden_serial.py:13404`
  - `SDClipModel.process_tokens` 
    wall **112.788 ms**  self **1.182 ms**  `sd1_clip.py:172`
    - `Module._wrapped_call_impl` 
      wall **111.600 ms**  self **0.012 ms**  `module.py:1779`
      - `Module._call_impl` 
        wall **111.588 ms**  self **0.011 ms**  `module.py:1787`
        - `disable_weight_init.Embedding.forward` 
          wall **111.577 ms**  self **0.017 ms**  `ops.py:798`
          - `disable_weight_init.Embedding.forward_comfy_cast_weights` 
            wall **111.537 ms**  self **79.099 ms**  `ops.py:790`
            - `embedding` 
              wall **32.347 ms**  self **32.347 ms**  `functional.py:2509`
  _... 10 more children >= 1 ms omitted_

### `golden_sampler_prepare`

- Stage wall: **55.120 ms**

- `golden_sampler_prepare` 
  wall **55.120 ms**  self **0.719 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **55.100 ms**  self **0.089 ms**  `golden_serial.py:13634`
    - `GoldenSerialRunner.run_closure` 
      wall **53.738 ms**  self **0.068 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **38.395 ms**  self **0.013 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **38.153 ms**  self **0.021 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **37.197 ms**  self **0.011 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **36.966 ms**  self **0.028 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **29.364 ms**  self **0.019 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **26.868 ms**  self **0.034 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **26.647 ms**  self **0.940 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **25.549 ms**  self **25.544 ms**  `nodes.py:1992`
                - `GoldenSerialRunner._ensure` 
                  wall **1.620 ms**  self **0.014 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **6.379 ms**  self **0.036 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **5.846 ms**  self **0.022 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **5.705 ms**  self **0.027 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **5.426 ms**  self **0.017 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **5.182 ms**  self **0.002 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **5.180 ms**  self **0.008 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **5.172 ms**  self **5.170 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **1.162 ms**  self **0.022 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **8.454 ms**  self **0.023 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **7.377 ms**  self **0.023 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **6.784 ms**  self **0.029 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **5.721 ms**  self **0.020 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **5.675 ms**  self **0.032 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **5.192 ms**  self **0.011 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **5.038 ms**  self **0.010 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **5.027 ms**  self **0.075 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **4.604 ms**  self **0.055 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **4.165 ms**  self **0.103 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **4.062 ms**  self **0.105 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **3.957 ms**  self **0.030 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **3.907 ms**  self **0.028 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **3.219 ms**  self **0.031 ms**  `module.py:2199`
      - `GoldenSerialRunner._ensure` 
        wall **1.937 ms**  self **0.025 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **1.603 ms**  self **0.016 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **1.563 ms**  self **0.024 ms**  `golden_serial.py:8902`
            - `GoldenSerialRunner._call_node` 
              wall **1.405 ms**  self **0.015 ms**  `golden_serial.py:9035`
              - `ConditioningZeroOut.zero_out` 
                wall **1.324 ms**  self **1.324 ms**  `nodes.py:283`
      - `GoldenSerialRunner._ensure` 
        wall **1.606 ms**  self **0.012 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.534 ms**  self **0.025 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.465 ms**  self **0.021 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **1.050 ms**  self **0.026 ms**  `golden_serial.py:8902`
      - `GoldenSerialRunner._ensure` 
        wall **1.010 ms**  self **0.020 ms**  `golden_serial.py:9122`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **53.778 ms**  self **53.778 ms**  `full_execution_trace.py:330`

### `golden_vae_load`

- Stage wall: **878.879 ms**

- `golden_vae_load` 
  wall **878.879 ms**  self **183.952 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **695.149 ms**  self **0.016 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **694.965 ms**  self **0.025 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **694.940 ms**  self **0.011 ms**  `golden_model_transport.py:1090`
        - `GoldenModelTransport._load_c0_sync` 
          wall **694.930 ms**  self **0.012 ms**  `golden_model_transport.py:1581`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **694.918 ms**  self **0.339 ms**  `golden_model_transport.py:1245`
            - `SourcePlanBridge.publish_all` 
              wall **627.562 ms**  self **0.162 ms**  `golden_source_threads.py:1351`
              - `SourceThreadProcess.wait_ready` 
                wall **526.557 ms**  self **0.051 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **250.185 ms**  self **250.185 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._read_message` 
                  wall **250.172 ms**  self **250.172 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._read_message` 
                  wall **24.133 ms**  self **24.094 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess._recover_ready_from_table` 
                  wall **1.531 ms**  self **0.037 ms**  `golden_source_threads.py:1100`
                  - `_FileLock.__exit__` 
                    wall **1.035 ms**  self **1.035 ms**  `golden_source_threads.py:501`
              - `SourceThreadProcess.wait_ready` 
                wall **77.486 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **76.946 ms**  self **76.910 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **11.183 ms**  self **0.008 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **10.832 ms**  self **10.813 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **4.238 ms**  self **0.016 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **3.884 ms**  self **3.860 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.plan_once` 
                wall **4.080 ms**  self **0.290 ms**  `golden_source_threads.py:918`
                - `_validate_identity` 
                  wall **2.237 ms**  self **0.009 ms**  `golden_source_threads.py:200`
                  - `_identity` 
                    wall **2.226 ms**  self **2.226 ms**  `golden_source_threads.py:195`
                - `SourceThreadProcess._read_message` 
                  wall **1.245 ms**  self **1.229 ms**  `golden_source_threads.py:900`
              - `SourceThreadProcess.wait_ready` 
                wall **2.532 ms**  self **0.010 ms**  `golden_source_threads.py:1129`
                - `SourceThreadProcess._read_message` 
                  wall **1.965 ms**  self **1.938 ms**  `golden_source_threads.py:900`
            - `GoldenModelTransport._views` 
              wall **31.165 ms**  self **31.165 ms**  `golden_model_transport.py:2042`
            - `GoldenModelTransport.inspect` 
              wall **29.676 ms**  self **0.030 ms**  `golden_model_transport.py:999`
              - `_parse_layout` 
                wall **29.241 ms**  self **28.694 ms**  `golden_model_transport.py:327`
            - `GpuDestinationPool.acquire` 
              wall **2.142 ms**  self **0.032 ms**  `golden_model_transport.py:188`
              - `GpuDestinationPool._allocate` 
                wall **2.101 ms**  self **1.968 ms**  `golden_model_transport.py:161`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **2.022 ms**  self **0.059 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **1.654 ms**  self **0.010 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **1.633 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **1.621 ms**  self **0.005 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **1.613 ms**  self **1.611 ms**  `threading.py:288`
  - `BaseEventLoop._run_once` 
    wall **694.927 ms**  self **0.020 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **694.737 ms**  self **694.735 ms**  `selectors.py:451`
  - `_vae_load_with_worker_stage` 
    wall **182.175 ms**  self **0.009 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **182.159 ms**  self **0.276 ms**  `golden_serial.py:14310`
      - `VAE.__init__` 
        wall **175.391 ms**  self **66.215 ms**  `sd.py:487`
        - `Module.to` 
          wall **51.214 ms**  self **0.054 ms**  `module.py:1259`
          - `Module._apply` 
            wall **51.160 ms**  self **0.021 ms**  `module.py:930`
            - `Module._apply` 
              wall **33.328 ms**  self **0.034 ms**  `module.py:930`
              - `Module._apply` 
                wall **26.130 ms**  self **0.011 ms**  `module.py:930`
                - `Module._apply` 
                  wall **7.427 ms**  self **0.011 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **6.845 ms**  self **0.011 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.691 ms**  self **0.031 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.022 ms**  self **0.027 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.354 ms**  self **0.027 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.038 ms**  self **0.040 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.780 ms**  self **0.025 ms**  `module.py:930`
                - `Module._apply` 
                  wall **7.192 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **6.999 ms**  self **0.011 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.870 ms**  self **0.028 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.473 ms**  self **0.027 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.633 ms**  self **0.025 ms**  `module.py:930`
                - `Module._apply` 
                  wall **6.026 ms**  self **0.008 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **6.006 ms**  self **0.013 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.300 ms**  self **0.039 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.198 ms**  self **0.027 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.483 ms**  self **0.024 ms**  `module.py:930`
                - `Module._apply` 
                  wall **5.463 ms**  self **0.009 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **5.390 ms**  self **0.012 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.016 ms**  self **0.031 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.811 ms**  self **0.022 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.540 ms**  self **0.026 ms**  `module.py:930`
              - `Module._apply` 
                wall **5.910 ms**  self **0.012 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.164 ms**  self **0.018 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.080 ms**  self **0.022 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.642 ms**  self **0.025 ms**  `module.py:930`
            - `Module._apply` 
              wall **17.789 ms**  self **0.023 ms**  `module.py:930`
              - `Module._apply` 
                wall **12.975 ms**  self **0.014 ms**  `module.py:930`
                - `Module._apply` 
                  wall **3.871 ms**  self **0.016 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.217 ms**  self **0.011 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.640 ms**  self **0.038 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.553 ms**  self **0.024 ms**  `module.py:930`
                - `Module._apply` 
                  wall **3.619 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.187 ms**  self **0.009 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.896 ms**  self **0.025 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.273 ms**  self **0.025 ms**  `module.py:930`
                - `Module._apply` 
                  wall **3.229 ms**  self **0.007 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.210 ms**  self **0.009 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.815 ms**  self **0.023 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.375 ms**  self **0.019 ms**  `module.py:930`
                - `Module._apply` 
                  wall **2.226 ms**  self **0.008 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **2.156 ms**  self **0.007 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.256 ms**  self **0.029 ms**  `module.py:930`
              - `Module._apply` 
                wall **3.478 ms**  self **0.012 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.336 ms**  self **0.025 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.332 ms**  self **0.019 ms**  `module.py:930`
        - `Module.load_state_dict` 
          wall **34.464 ms**  self **0.129 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **34.335 ms**  self **0.027 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **18.118 ms**  self **0.039 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **13.181 ms**  self **0.026 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.059 ms**  self **0.018 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.673 ms**  self **0.016 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.796 ms**  self **0.029 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.011 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.298 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.846 ms**  self **0.017 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.037 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.007 ms**  self **0.010 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.941 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.517 ms**  self **0.038 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.544 ms**  self **0.016 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.193 ms**  self **0.017 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **3.851 ms**  self **0.021 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.344 ms**  self **0.032 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.242 ms**  self **0.032 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.183 ms**  self **0.024 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **15.617 ms**  self **0.035 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **10.529 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.052 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.485 ms**  self **0.012 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.681 ms**  self **0.027 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.595 ms**  self **0.013 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.526 ms**  self **0.011 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.266 ms**  self **0.030 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.216 ms**  self **0.033 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.434 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.942 ms**  self **0.013 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.016 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.240 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.046 ms**  self **0.011 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.371 ms**  self **0.025 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **4.149 ms**  self **0.023 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.752 ms**  self **0.032 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.228 ms**  self **0.024 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.077 ms**  self **0.030 ms**  `module.py:2589`
        - `VAE.model_size` 
          wall **15.356 ms**  self **1.077 ms**  `sd.py:1095`
          - `module_size` 
            wall **14.279 ms**  self **0.153 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **14.126 ms**  self **0.021 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **7.086 ms**  self **0.019 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **5.339 ms**  self **0.017 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.633 ms**  self **0.015 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.285 ms**  self **0.010 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.347 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.329 ms**  self **0.009 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.342 ms**  self **0.016 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.251 ms**  self **0.011 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **1.535 ms**  self **0.013 ms**  `module.py:2199`
              - `Module.state_dict` 
                wall **7.007 ms**  self **0.022 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **3.911 ms**  self **0.017 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.583 ms**  self **0.010 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.550 ms**  self **0.012 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.224 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.209 ms**  self **0.011 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **2.845 ms**  self **0.018 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.312 ms**  self **0.020 ms**  `module.py:2199`
        - `archive_model_dtypes` 
          wall **4.403 ms**  self **0.788 ms**  `model_management.py:1045`
        - `Module.eval` 
          wall **2.074 ms**  self **0.002 ms**  `module.py:2916`
          - `Module.train` 
            wall **2.072 ms**  self **0.009 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.097 ms**  self **0.006 ms**  `module.py:2894`
        - `ModelPatcherDynamic.__init__` 
          wall **1.633 ms**  self **0.031 ms**  `model_patcher.py:1757`
      - `validate_qd_adoption` 
        wall **3.962 ms**  self **1.276 ms**  `golden_serial.py:12971`
  - `sample_custom` 
    wall **177.310 ms**  self **2.623 ms**  `sample.py:86`
    - `sample` 
      wall **174.684 ms**  self **0.035 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **174.438 ms**  self **0.092 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **174.141 ms**  self **0.023 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **174.118 ms**  self **0.082 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **173.405 ms**  self **0.006 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **173.394 ms**  self **0.024 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **173.371 ms**  self **1.643 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **112.743 ms**  self **0.009 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **112.731 ms**  self **0.007 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **112.724 ms**  self **0.044 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **112.564 ms**  self **0.070 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **111.542 ms**  self **0.016 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **111.508 ms**  self **0.002 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **111.506 ms**  self **0.198 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **111.251 ms**  self **4.178 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **35.895 ms**  self **4.730 ms**  `model_patcher.py:945`
                                  - `ModelPatcherDynamic.load.<locals>.<genexpr>` 
                                    wall **2.567 ms**  self **2.567 ms**  `model_patcher.py:1907`
                                  - `Module.named_buffers` 
                                    wall **2.431 ms**  self **0.003 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **2.428 ms**  self **0.476 ms**  `module.py:2650`
                  - `CFGGuider.inner_sample` 
                    wall **58.823 ms**  self **56.991 ms**  `samplers.py:1220`
                    - `WrapperExecutor.execute` 
                      wall **1.241 ms**  self **0.016 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.225 ms**  self **0.120 ms**  `samplers.py:983`
  - `prepare_sampling` 
    wall **114.703 ms**  self **0.012 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **114.683 ms**  self **0.005 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **114.678 ms**  self **0.023 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **114.554 ms**  self **0.075 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **113.138 ms**  self **0.022 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **113.086 ms**  self **0.005 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **113.081 ms**  self **0.300 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **112.700 ms**  self **4.366 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **37.233 ms**  self **4.471 ms**  `model_patcher.py:945`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **5.989 ms**  self **1.562 ms**  `model_patcher.py:1842`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **2.769 ms**  self **0.007 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **2.718 ms**  self **0.041 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **2.433 ms**  self **2.432 ms**  `__init__.py:350`
                  - `Module.named_buffers` 
                    wall **2.750 ms**  self **0.004 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **2.746 ms**  self **0.491 ms**  `module.py:2650`
  - `RK_NoiseSampler.set_sde_step` 
    wall **51.547 ms**  self **0.103 ms**  `rk_noise_sampler_beta.py:216`
    - `RK_NoiseSampler.get_sde_step` 
      wall **37.295 ms**  self **0.333 ms**  `rk_noise_sampler_beta.py:318`
      - `RK_NoiseSampler.get_sde_coeff` 
        wall **36.962 ms**  self **0.195 ms**  `rk_noise_sampler_beta.py:180`
        - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
          wall **36.611 ms**  self **36.611 ms**  `_tensor.py:32`
    - `RK_Method_Exponential.h_fn` 
      wall **13.842 ms**  self **13.842 ms**  `rk_method_beta.py:882`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **25.963 ms**  self **25.963 ms**  `rk_noise_sampler_beta.py:785`
  - `generate_init_noise` 
    wall **19.569 ms**  self **1.930 ms**  `samplers.py:61`
    - `GaussianNoiseGenerator.__call__` 
      wall **16.049 ms**  self **16.047 ms**  `noise_classes.py:386`
    - `normalize_zscore` 
      wall **1.088 ms**  self **1.088 ms**  `latents.py:246`
  _... 13 more children >= 1 ms omitted_

### `golden_sampling`

- Stage wall: **4,413.640 ms**

- `golden_sampling` 
  wall **4,413.640 ms**  self **4,413.640 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **4,413.581 ms**  self **0.290 ms**  `golden_serial.py:13785`
    - `GoldenSerialRunner.run_closure` 
      wall **4,359.377 ms**  self **0.046 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,359.055 ms**  self **0.065 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,358.211 ms**  self **0.086 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **4,357.993 ms**  self **0.802 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **4,354.263 ms**  self **18.759 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **4,105.404 ms**  self **0.053 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **4,105.192 ms**  self **0.008 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **4,105.184 ms**  self **0.064 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **4,104.755 ms**  self **0.008 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **4,104.733 ms**  self **0.012 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **4,104.721 ms**  self **1.076 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **3,988.780 ms**  self **0.282 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **3,988.200 ms**  self **0.012 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **3,988.188 ms**  self **0.077 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **3,987.644 ms**  self **0.196 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **3,987.415 ms**  self **45.253 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **643.397 ms**  self **0.295 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **642.581 ms**  self **0.173 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **642.118 ms**  self **0.011 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **642.106 ms**  self **0.009 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **642.098 ms**  self **0.018 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **642.066 ms**  self **0.010 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **642.056 ms**  self **0.023 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **642.033 ms**  self **0.028 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **630.243 ms**  self **0.006 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **630.237 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **630.225 ms**  self **0.051 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **630.174 ms**  self **0.486 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **627.509 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **627.490 ms**  self **0.032 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **627.458 ms**  self **0.967 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **625.834 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **625.827 ms**  self **0.021 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **625.806 ms**  self **625.806 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **11.763 ms**  self **0.185 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **11.577 ms**  self **11.251 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **325.333 ms**  self **0.134 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **325.165 ms**  self **0.056 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **325.099 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **325.091 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **325.086 ms**  self **0.017 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **325.058 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **325.052 ms**  self **0.020 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **325.032 ms**  self **0.018 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **195.225 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **195.221 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **195.212 ms**  self **0.028 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **195.183 ms**  self **0.324 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **189.575 ms**  self **0.014 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **189.551 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **189.537 ms**  self **0.126 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **188.852 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **188.845 ms**  self **0.016 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **188.830 ms**  self **188.830 ms**  `nodes.py:215`
                                                            - `cond_cat` 
                                                              wall **3.290 ms**  self **0.016 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **3.273 ms**  self **3.273 ms**  `conds.py:44`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.591 ms**  self **0.052 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.464 ms**  self **0.020 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.066 ms**  self **1.058 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **129.790 ms**  self **0.083 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **129.707 ms**  self **129.420 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **318.075 ms**  self **0.405 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **317.629 ms**  self **0.063 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **317.558 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **317.550 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **317.546 ms**  self **0.015 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **317.519 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **317.513 ms**  self **0.033 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **317.480 ms**  self **0.081 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **167.180 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **167.177 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **167.166 ms**  self **0.029 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **167.137 ms**  self **0.536 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **164.886 ms**  self **0.013 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **164.862 ms**  self **0.017 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **164.845 ms**  self **0.162 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **164.050 ms**  self **0.009 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **164.042 ms**  self **0.019 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **164.023 ms**  self **164.023 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **150.220 ms**  self **0.111 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **150.109 ms**  self **150.109 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **304.372 ms**  self **0.514 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **303.817 ms**  self **0.059 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **303.750 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **303.742 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **303.737 ms**  self **0.013 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **303.712 ms**  self **0.007 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **303.705 ms**  self **0.064 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **303.641 ms**  self **0.076 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **177.574 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **177.570 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **177.559 ms**  self **0.120 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **177.439 ms**  self **0.599 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **173.889 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **173.870 ms**  self **0.074 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **173.796 ms**  self **0.170 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **173.063 ms**  self **0.008 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **173.056 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **173.044 ms**  self **173.044 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **2.311 ms**  self **0.044 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **2.182 ms**  self **0.020 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.763 ms**  self **1.756 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **125.990 ms**  self **0.156 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **125.834 ms**  self **125.834 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **303.804 ms**  self **0.163 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **303.602 ms**  self **0.058 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **303.536 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **303.529 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **303.524 ms**  self **0.015 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **303.498 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **303.492 ms**  self **0.020 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **303.472 ms**  self **0.015 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **167.430 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **167.427 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **167.417 ms**  self **0.025 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **167.391 ms**  self **0.337 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **165.746 ms**  self **0.010 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **165.728 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **165.714 ms**  self **0.102 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **165.108 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **165.102 ms**  self **0.010 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **165.092 ms**  self **165.092 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **136.027 ms**  self **0.115 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **135.912 ms**  self **135.590 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **302.633 ms**  self **0.149 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **302.447 ms**  self **0.050 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **302.387 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **302.381 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **302.376 ms**  self **0.009 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **302.360 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **302.355 ms**  self **0.017 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **302.338 ms**  self **0.016 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **172.733 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **172.730 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **172.721 ms**  self **0.026 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **172.695 ms**  self **0.259 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **171.339 ms**  self **0.007 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **171.326 ms**  self **0.015 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **171.311 ms**  self **0.095 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **170.758 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **170.752 ms**  self **0.010 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **170.743 ms**  self **170.743 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **129.589 ms**  self **0.061 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **129.528 ms**  self **129.528 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **302.425 ms**  self **0.155 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **302.221 ms**  self **0.059 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **302.154 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **302.148 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **302.143 ms**  self **0.009 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **302.128 ms**  self **0.007 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **302.120 ms**  self **0.017 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **302.104 ms**  self **0.014 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **167.186 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **167.182 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **167.174 ms**  self **0.029 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **167.144 ms**  self **0.362 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **165.597 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **165.575 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **165.561 ms**  self **0.133 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **164.821 ms**  self **0.010 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **164.811 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **164.796 ms**  self **164.796 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **134.904 ms**  self **0.057 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **134.847 ms**  self **134.847 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **302.154 ms**  self **0.159 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **301.945 ms**  self **0.063 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **301.870 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **301.863 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **301.859 ms**  self **0.010 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **301.842 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **301.836 ms**  self **0.019 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **301.817 ms**  self **0.014 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **155.021 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **155.017 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **155.008 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **154.985 ms**  self **0.283 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **153.459 ms**  self **0.012 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **153.438 ms**  self **0.014 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **153.424 ms**  self **0.104 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **152.765 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **152.758 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **152.747 ms**  self **152.747 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **146.783 ms**  self **0.062 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **146.720 ms**  self **146.720 ms**  `noise_injection.py:285`
                                    _... 34 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **12.263 ms**  self **0.012 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **12.250 ms**  self **0.040 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **3.638 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **3.633 ms**  self **0.085 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **3.512 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **3.486 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **3.473 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **3.465 ms**  self **3.464 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **3.572 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **3.567 ms**  self **0.292 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **3.241 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **3.223 ms**  self **0.005 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **3.212 ms**  self **0.005 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **3.207 ms**  self **3.207 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.607 ms**  self **0.003 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.603 ms**  self **0.032 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.553 ms**  self **0.002 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.540 ms**  self **0.005 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.531 ms**  self **0.003 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.529 ms**  self **1.528 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.542 ms**  self **0.008 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.533 ms**  self **0.099 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.368 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.339 ms**  self **0.011 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.317 ms**  self **0.009 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.308 ms**  self **1.308 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.432 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.427 ms**  self **0.075 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.317 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.292 ms**  self **0.007 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.278 ms**  self **0.007 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.271 ms**  self **1.271 ms**  `storage.py:262`
              - `BaseModel.process_latent_out` 
                wall **1.404 ms**  self **0.003 ms**  `model_base.py:378`
                - `Flux.process_out` 
                  wall **1.401 ms**  self **1.401 ms**  `latent_formats.py:193`
              - `_disable_dynamo.<locals>.inner` 
                wall **1.394 ms**  self **0.006 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **1.389 ms**  self **0.010 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **1.374 ms**  self **0.002 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **1.371 ms**  self **0.040 ms**  `random.py:62`
    - `import_module` 
      wall **32.785 ms**  self **32.785 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **16.081 ms**  self **0.030 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **16.051 ms**  self **0.004 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **16.046 ms**  self **0.042 ms**  `copy.py:201`
          - `deepcopy` 
            wall **7.343 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **7.340 ms**  self **0.007 ms**  `copy.py:227`
              - `deepcopy` 
                wall **7.325 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **7.322 ms**  self **0.038 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **7.210 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **7.207 ms**  self **0.011 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **6.020 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **6.017 ms**  self **0.167 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **2.812 ms**  self **0.004 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **2.806 ms**  self **0.729 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.632 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.629 ms**  self **0.229 ms**  `copy.py:227`
          - `deepcopy` 
            wall **5.515 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **5.512 ms**  self **0.007 ms**  `copy.py:227`
              - `deepcopy` 
                wall **5.496 ms**  self **0.003 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **5.493 ms**  self **0.045 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **5.371 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **5.368 ms**  self **0.015 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **3.938 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **3.936 ms**  self **0.165 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **1.913 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **1.910 ms**  self **0.555 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.120 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.118 ms**  self **0.148 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **1.695 ms**  self **0.044 ms**  `golden_serial.py:9742`
  - `BaseEventLoop.run_until_complete` 
    wall **881.090 ms**  self **0.010 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **881.074 ms**  self **0.054 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **184.068 ms**  self **1.745 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **182.254 ms**  self **182.235 ms**  `events.py:78`
      - `BaseEventLoop._run_once` 
        wall **1.950 ms**  self **0.026 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **1.738 ms**  self **1.738 ms**  `events.py:78`
  - `Thread.run` 
    wall **880.447 ms**  self **0.008 ms**  `threading.py:964`
    - `_worker` 
      wall **880.440 ms**  self **185.281 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **878.879 ms**  self **183.952 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **695.149 ms**  self **0.016 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **694.965 ms**  self **0.025 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **694.940 ms**  self **0.011 ms**  `golden_model_transport.py:1090`
          - `GoldenModelTransport._load_c0_sync` 
            wall **694.930 ms**  self **0.012 ms**  `golden_model_transport.py:1581`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **694.918 ms**  self **0.339 ms**  `golden_model_transport.py:1245`
              - `SourcePlanBridge.publish_all` 
                wall **627.562 ms**  self **0.162 ms**  `golden_source_threads.py:1351`
                - `SourceThreadProcess.wait_ready` 
                  wall **526.557 ms**  self **0.051 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **250.185 ms**  self **250.185 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._read_message` 
                    wall **250.172 ms**  self **250.172 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._read_message` 
                    wall **24.133 ms**  self **24.094 ms**  `golden_source_threads.py:900`
                  - `SourceThreadProcess._recover_ready_from_table` 
                    wall **1.531 ms**  self **0.037 ms**  `golden_source_threads.py:1100`
                    - `_FileLock.__exit__` 
                      wall **1.035 ms**  self **1.035 ms**  `golden_source_threads.py:501`
                - `SourceThreadProcess.wait_ready` 
                  wall **77.486 ms**  self **0.017 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **76.946 ms**  self **76.910 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **11.183 ms**  self **0.008 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **10.832 ms**  self **10.813 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **4.238 ms**  self **0.016 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **3.884 ms**  self **3.860 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.plan_once` 
                  wall **4.080 ms**  self **0.290 ms**  `golden_source_threads.py:918`
                  - `_validate_identity` 
                    wall **2.237 ms**  self **0.009 ms**  `golden_source_threads.py:200`
                    - `_identity` 
                      wall **2.226 ms**  self **2.226 ms**  `golden_source_threads.py:195`
                  - `SourceThreadProcess._read_message` 
                    wall **1.245 ms**  self **1.229 ms**  `golden_source_threads.py:900`
                - `SourceThreadProcess.wait_ready` 
                  wall **2.532 ms**  self **0.010 ms**  `golden_source_threads.py:1129`
                  - `SourceThreadProcess._read_message` 
                    wall **1.965 ms**  self **1.938 ms**  `golden_source_threads.py:900`
              - `GoldenModelTransport._views` 
                wall **31.165 ms**  self **31.165 ms**  `golden_model_transport.py:2042`
              - `GoldenModelTransport.inspect` 
                wall **29.676 ms**  self **0.030 ms**  `golden_model_transport.py:999`
                - `_parse_layout` 
                  wall **29.241 ms**  self **28.694 ms**  `golden_model_transport.py:327`
              - `GpuDestinationPool.acquire` 
                wall **2.142 ms**  self **0.032 ms**  `golden_model_transport.py:188`
                - `GpuDestinationPool._allocate` 
                  wall **2.101 ms**  self **1.968 ms**  `golden_model_transport.py:161`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **2.022 ms**  self **0.059 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **1.654 ms**  self **0.010 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **1.633 ms**  self **0.008 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **1.621 ms**  self **0.005 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **1.613 ms**  self **1.611 ms**  `threading.py:288`
    - `BaseEventLoop._run_once` 
      wall **694.927 ms**  self **0.020 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **694.737 ms**  self **694.735 ms**  `selectors.py:451`
    - `_vae_load_with_worker_stage` 
      wall **182.175 ms**  self **0.009 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **182.159 ms**  self **0.276 ms**  `golden_serial.py:14310`
        - `VAE.__init__` 
          wall **175.391 ms**  self **66.215 ms**  `sd.py:487`
          - `Module.to` 
            wall **51.214 ms**  self **0.054 ms**  `module.py:1259`
            - `Module._apply` 
              wall **51.160 ms**  self **0.021 ms**  `module.py:930`
              - `Module._apply` 
                wall **33.328 ms**  self **0.034 ms**  `module.py:930`
                - `Module._apply` 
                  wall **26.130 ms**  self **0.011 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **7.427 ms**  self **0.011 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **6.845 ms**  self **0.011 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.691 ms**  self **0.031 ms**  `module.py:930`
                        - `Module._apply` 
                          wall **1.022 ms**  self **0.027 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.354 ms**  self **0.027 ms**  `module.py:930`
                        - `Module._apply` 
                          wall **1.038 ms**  self **0.040 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.780 ms**  self **0.025 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **7.192 ms**  self **0.010 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **6.999 ms**  self **0.011 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.870 ms**  self **0.028 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.473 ms**  self **0.027 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.633 ms**  self **0.025 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **6.026 ms**  self **0.008 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **6.006 ms**  self **0.013 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.300 ms**  self **0.039 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.198 ms**  self **0.027 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.483 ms**  self **0.024 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **5.463 ms**  self **0.009 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **5.390 ms**  self **0.012 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **2.016 ms**  self **0.031 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.811 ms**  self **0.022 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.540 ms**  self **0.026 ms**  `module.py:930`
                - `Module._apply` 
                  wall **5.910 ms**  self **0.012 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **2.164 ms**  self **0.018 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **2.080 ms**  self **0.022 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.642 ms**  self **0.025 ms**  `module.py:930`
              - `Module._apply` 
                wall **17.789 ms**  self **0.023 ms**  `module.py:930`
                - `Module._apply` 
                  wall **12.975 ms**  self **0.014 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.871 ms**  self **0.016 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **3.217 ms**  self **0.011 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.640 ms**  self **0.038 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.553 ms**  self **0.024 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.619 ms**  self **0.010 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **3.187 ms**  self **0.009 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.896 ms**  self **0.025 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.273 ms**  self **0.025 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **3.229 ms**  self **0.007 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **3.210 ms**  self **0.009 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.815 ms**  self **0.023 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.375 ms**  self **0.019 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **2.226 ms**  self **0.008 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **2.156 ms**  self **0.007 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.256 ms**  self **0.029 ms**  `module.py:930`
                - `Module._apply` 
                  wall **3.478 ms**  self **0.012 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.336 ms**  self **0.025 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.332 ms**  self **0.019 ms**  `module.py:930`
          - `Module.load_state_dict` 
            wall **34.464 ms**  self **0.129 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **34.335 ms**  self **0.027 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **18.118 ms**  self **0.039 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **13.181 ms**  self **0.026 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **4.059 ms**  self **0.018 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **3.673 ms**  self **0.016 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.796 ms**  self **0.029 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.011 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.298 ms**  self **0.020 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.846 ms**  self **0.017 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.037 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.007 ms**  self **0.010 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.941 ms**  self **0.018 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.517 ms**  self **0.038 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.544 ms**  self **0.016 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.193 ms**  self **0.017 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **3.851 ms**  self **0.021 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.344 ms**  self **0.032 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.242 ms**  self **0.032 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.183 ms**  self **0.024 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **15.617 ms**  self **0.035 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **10.529 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **3.052 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.485 ms**  self **0.012 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.681 ms**  self **0.027 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.595 ms**  self **0.013 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.526 ms**  self **0.011 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.266 ms**  self **0.030 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.216 ms**  self **0.033 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.434 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.942 ms**  self **0.013 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.016 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.240 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.046 ms**  self **0.011 ms**  `module.py:2589`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **1.371 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.149 ms**  self **0.023 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.752 ms**  self **0.032 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.228 ms**  self **0.024 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.077 ms**  self **0.030 ms**  `module.py:2589`
          - `VAE.model_size` 
            wall **15.356 ms**  self **1.077 ms**  `sd.py:1095`
            - `module_size` 
              wall **14.279 ms**  self **0.153 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **14.126 ms**  self **0.021 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **7.086 ms**  self **0.019 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **5.339 ms**  self **0.017 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.633 ms**  self **0.015 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.285 ms**  self **0.010 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.347 ms**  self **0.009 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.329 ms**  self **0.009 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.342 ms**  self **0.016 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.251 ms**  self **0.011 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **1.535 ms**  self **0.013 ms**  `module.py:2199`
                - `Module.state_dict` 
                  wall **7.007 ms**  self **0.022 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **3.911 ms**  self **0.017 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.583 ms**  self **0.010 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.550 ms**  self **0.012 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.224 ms**  self **0.009 ms**  `module.py:2199`
                      - `Module.state_dict` 
                        wall **1.209 ms**  self **0.011 ms**  `module.py:2199`
                  - `Module.state_dict` 
                    wall **2.845 ms**  self **0.018 ms**  `module.py:2199`
                    - `Module.state_dict` 
                      wall **1.312 ms**  self **0.020 ms**  `module.py:2199`
          - `archive_model_dtypes` 
            wall **4.403 ms**  self **0.788 ms**  `model_management.py:1045`
          - `Module.eval` 
            wall **2.074 ms**  self **0.002 ms**  `module.py:2916`
            - `Module.train` 
              wall **2.072 ms**  self **0.009 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.097 ms**  self **0.006 ms**  `module.py:2894`
          - `ModelPatcherDynamic.__init__` 
            wall **1.633 ms**  self **0.031 ms**  `model_patcher.py:1757`
        - `validate_qd_adoption` 
          wall **3.962 ms**  self **1.276 ms**  `golden_serial.py:12971`
    - `sample_custom` 
      wall **177.310 ms**  self **2.623 ms**  `sample.py:86`
      - `sample` 
        wall **174.684 ms**  self **0.035 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **174.438 ms**  self **0.092 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **174.141 ms**  self **0.023 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **174.118 ms**  self **0.082 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **173.405 ms**  self **0.006 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **173.394 ms**  self **0.024 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **173.371 ms**  self **1.643 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **112.743 ms**  self **0.009 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **112.731 ms**  self **0.007 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **112.724 ms**  self **0.044 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **112.564 ms**  self **0.070 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **111.542 ms**  self **0.016 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **111.508 ms**  self **0.002 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **111.506 ms**  self **0.198 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **111.251 ms**  self **4.178 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **35.895 ms**  self **4.730 ms**  `model_patcher.py:945`
                                    - `ModelPatcherDynamic.load.<locals>.<genexpr>` 
                                      wall **2.567 ms**  self **2.567 ms**  `model_patcher.py:1907`
                                    - `Module.named_buffers` 
                                      wall **2.431 ms**  self **0.003 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **2.428 ms**  self **0.476 ms**  `module.py:2650`
                    - `CFGGuider.inner_sample` 
                      wall **58.823 ms**  self **56.991 ms**  `samplers.py:1220`
                      - `WrapperExecutor.execute` 
                        wall **1.241 ms**  self **0.016 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.225 ms**  self **0.120 ms**  `samplers.py:983`
    - `prepare_sampling` 
      wall **114.703 ms**  self **0.012 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **114.683 ms**  self **0.005 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **114.678 ms**  self **0.023 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **114.554 ms**  self **0.075 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **113.138 ms**  self **0.022 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **113.086 ms**  self **0.005 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **113.081 ms**  self **0.300 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **112.700 ms**  self **4.366 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **37.233 ms**  self **4.471 ms**  `model_patcher.py:945`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **5.989 ms**  self **1.562 ms**  `model_patcher.py:1842`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **2.769 ms**  self **0.007 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **2.718 ms**  self **0.041 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **2.433 ms**  self **2.432 ms**  `__init__.py:350`
                    - `Module.named_buffers` 
                      wall **2.750 ms**  self **0.004 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **2.746 ms**  self **0.491 ms**  `module.py:2650`
    - `RK_NoiseSampler.set_sde_step` 
      wall **51.547 ms**  self **0.103 ms**  `rk_noise_sampler_beta.py:216`
      - `RK_NoiseSampler.get_sde_step` 
        wall **37.295 ms**  self **0.333 ms**  `rk_noise_sampler_beta.py:318`
        - `RK_NoiseSampler.get_sde_coeff` 
          wall **36.962 ms**  self **0.195 ms**  `rk_noise_sampler_beta.py:180`
          - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
            wall **36.611 ms**  self **36.611 ms**  `_tensor.py:32`
      - `RK_Method_Exponential.h_fn` 
        wall **13.842 ms**  self **13.842 ms**  `rk_method_beta.py:882`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **25.963 ms**  self **25.963 ms**  `rk_noise_sampler_beta.py:785`
    - `generate_init_noise` 
      wall **19.569 ms**  self **1.930 ms**  `samplers.py:61`
      - `GaussianNoiseGenerator.__call__` 
        wall **16.049 ms**  self **16.047 ms**  `noise_classes.py:386`
      - `normalize_zscore` 
        wall **1.088 ms**  self **1.088 ms**  `latents.py:246`
    _... 13 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **182.202 ms**  self **0.010 ms**  `golden_serial.py:15614`
  - `_overlap_stage_call` 
    wall **1.710 ms**  self **0.012 ms**  `golden_serial.py:15614`

### `golden_sampler_tail`

- Stage wall: **0.060 ms**

_Nothing below the stage body reached the threshold._

### `golden_vae_decode`

- Stage wall: **874.022 ms**

- `golden_vae_decode` 
  wall **874.022 ms**  self **0.258 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **873.997 ms**  self **0.063 ms**  `golden_serial.py:14523`
    - `GoldenSerialRunner.run_closure` 
      wall **873.647 ms**  self **0.026 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **873.561 ms**  self **0.045 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **873.272 ms**  self **0.023 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **873.083 ms**  self **0.051 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **873.031 ms**  self **783.635 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **78.091 ms**  self **0.085 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **69.572 ms**  self **0.017 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **69.523 ms**  self **0.003 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **69.520 ms**  self **0.101 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **69.387 ms**  self **1.677 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **13.451 ms**  self **1.311 ms**  `model_patcher.py:945`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.741 ms**  self **0.024 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.666 ms**  self **0.104 ms**  `model_patcher.py:899`
                            - `namedtuple` 
                              wall **1.422 ms**  self **1.420 ms**  `__init__.py:350`
                        - `Module.named_buffers` 
                          wall **1.237 ms**  self **0.004 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.233 ms**  self **0.212 ms**  `module.py:2650`
                - `LoadedModel.model_memory_required` 
                  wall **6.497 ms**  self **0.004 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **6.490 ms**  self **0.003 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **6.487 ms**  self **1.168 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **5.319 ms**  self **0.218 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **5.102 ms**  self **0.032 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.750 ms**  self **0.024 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **2.235 ms**  self **0.018 ms**  `module.py:2199`
                          - `Module.state_dict` 
                            wall **2.305 ms**  self **0.024 ms**  `module.py:2199`
                            - `Module.state_dict` 
                              wall **1.646 ms**  self **0.019 ms**  `module.py:2199`
                - `free_memory` 
                  wall **1.399 ms**  self **0.093 ms**  `model_management.py:863`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **10.064 ms**  self **10.064 ms**  `sd.py:506`
              - `ModelPatcher.get_free_memory` 
                wall **1.168 ms**  self **0.034 ms**  `model_patcher.py:417`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **873.678 ms**  self **873.678 ms**  `full_execution_trace.py:330`

### `golden_output`

- Stage wall: **256.510 ms**

- `golden_output` 
  wall **256.510 ms**  self **256.510 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **256.446 ms**  self **19.528 ms**  `golden_serial.py:14670`
    - `Image.save` 
      wall **210.126 ms**  self **0.066 ms**  `Image.py:2592`
      - `_save` 
        wall **198.483 ms**  self **0.053 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **198.394 ms**  self **0.022 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **198.369 ms**  self **193.924 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **11.510 ms**  self **11.510 ms**  `Image.py:429`
    - `fromarray` 
      wall **13.421 ms**  self **8.365 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **5.056 ms**  self **0.015 ms**  `Image.py:3288`
        - `frombytes` 
          wall **5.036 ms**  self **0.028 ms**  `Image.py:3242`
          - `new` 
            wall **3.352 ms**  self **3.313 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.651 ms**  self **1.615 ms**  `Image.py:925`
    - `clip` 
      wall **10.022 ms**  self **0.014 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **10.008 ms**  self **0.025 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **9.983 ms**  self **9.983 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **2.255 ms**  self **0.015 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **2.240 ms**  self **2.240 ms**  `output_durability.py:73`
