# Golden per-stage call trees

Source: `derived/golden_exhaustive_calls.csv.gz`

Calls in trace: **929,408**

Expanded at wall >= **1 ms**

Depth is not capped; the floor is. Breadth is capped at 8 children plus any child at or above 10% of its parent.

Stage bodies run on executor threads, so children are attached to the stage they fall inside by time containment, then re-rooted onto the nearest same-stage ancestor.

## `golden_restore`

- Stage wall: **0.386 ms**

_Nothing below the stage body reached the threshold._

## `golden_request_setup`

- Stage wall: **1.727 ms**

- `golden_request_setup` 
  wall **1.727 ms**  self **1.727 ms**  `full_execution_trace.py:330`
  - `golden_request_setup` 
    wall **1.706 ms**  self **0.070 ms**  `golden_serial.py:9977`

## `golden_clip_load`

- Stage wall: **3,762.129 ms**

- `golden_clip_load` 
  wall **3,762.129 ms**  self **15.566 ms**  `full_execution_trace.py:330`
  - `Thread.run` 
    wall **3,667.647 ms**  self **0.019 ms**  `threading.py:964`
    - `_worker` 
      wall **3,667.628 ms**  self **2,915.352 ms**  `thread.py:69`
      - `_WorkItem.run` 
        wall **752.264 ms**  self **0.623 ms**  `thread.py:53`
        - `_start_clip_skeleton_overlap.<locals>.build` 
          wall **751.604 ms**  self **0.273 ms**  `golden_serial.py:2341`
          - `load_text_encoder_state_dicts` 
            wall **508.747 ms**  self **0.273 ms**  `sd.py:1720`
            - `CLIP.__init__` 
              wall **507.847 ms**  self **0.276 ms**  `sd.py:237`
              - `ZImageTokenizer.__init__` 
                wall **420.308 ms**  self **0.027 ms**  `z_image.py:13`
                - `SD1Tokenizer.__init__` 
                  wall **420.282 ms**  self **0.262 ms**  `sd1_clip.py:687`
                  - `Qwen3Tokenizer.__init__` 
                    wall **420.019 ms**  self **2.318 ms**  `z_image.py:7`
                    - `SDTokenizer.__init__` 
                      wall **417.701 ms**  self **0.143 ms**  `sd1_clip.py:487`
                      - `PreTrainedTokenizerBase.from_pretrained` 
                        wall **399.663 ms**  self **0.808 ms**  `tokenization_utils_base.py:1807`
                        - `PreTrainedTokenizerBase._from_pretrained` 
                          wall **394.989 ms**  self **9.636 ms**  `tokenization_utils_base.py:2083`
                          - `Qwen2Tokenizer.__init__` 
                            wall **385.030 ms**  self **221.140 ms**  `tokenization_qwen2.py:137`
                            - `load` 
                              wall **118.437 ms**  self **15.200 ms**  `__init__.py:274`
                              - `loads` 
                                wall **103.236 ms**  self **0.015 ms**  `__init__.py:299`
                                - `JSONDecoder.decode` 
                                  wall **103.222 ms**  self **0.039 ms**  `decoder.py:332`
                                  - `JSONDecoder.raw_decode` 
                                    wall **103.183 ms**  self **103.183 ms**  `decoder.py:343`
                            - `PreTrainedTokenizer.__init__` 
                              wall **21.646 ms**  self **0.916 ms**  `tokenization_utils.py:420`
                              - `PreTrainedTokenizer._add_tokens` 
                                wall **20.236 ms**  self **4.490 ms**  `tokenization_utils.py:512`
                                - `PreTrainedTokenizer._update_trie` 
                                  wall **6.736 ms**  self **0.053 ms**  `tokenization_utils.py:590`
                                  - `Trie.add` 
                                    wall **6.539 ms**  self **6.539 ms**  `tokenization_utils.py:74`
                                - `Qwen2Tokenizer.get_vocab` 
                                  wall **6.049 ms**  self **6.023 ms**  `tokenization_qwen2.py:215`
                                - `PreTrainedTokenizer._update_total_vocab_size` 
                                  wall **2.907 ms**  self **0.964 ms**  `tokenization_utils.py:504`
                                  - `Qwen2Tokenizer.get_vocab` 
                                    wall **1.909 ms**  self **1.868 ms**  `tokenization_qwen2.py:215`
                            - `Qwen2Tokenizer.__init__.<locals>.<dictcomp>` 
                              wall **18.229 ms**  self **18.229 ms**  `tokenization_qwen2.py:174`
                            - `compile` 
                              wall **5.122 ms**  self **0.062 ms**  `_main.py:359`
                              - `_compile` 
                                wall **5.059 ms**  self **0.259 ms**  `_main.py:460`
                                - `Branch.pack_characters` 
                                  wall **2.433 ms**  self **0.003 ms**  `_regex_core.py:2193`
                                  - `Branch.pack_characters.<locals>.<listcomp>` 
                                    wall **2.430 ms**  self **0.009 ms**  `_regex_core.py:2194`
                                    - `Sequence.pack_characters` 
                                      wall **2.385 ms**  self **0.018 ms**  `_regex_core.py:3525`
                                      - `Sequence._flush_characters` 
                                        wall **2.281 ms**  self **0.022 ms**  `_regex_core.py:3607`
                                        - `Sequence._flush_characters.<locals>.<genexpr>` 
                                          wall **2.227 ms**  self **0.004 ms**  `_regex_core.py:3614`
                                          - `is_cased_i` 
                                            wall **2.223 ms**  self **2.223 ms**  `_regex_core.py:362`
                                - `_parse_pattern` 
                                  wall **1.260 ms**  self **0.022 ms**  `_regex_core.py:452`
                      - `SDTokenizer.__init__.<locals>.<dictcomp>` 
                        wall **15.762 ms**  self **15.762 ms**  `sd1_clip.py:534`
                      - `Qwen2Tokenizer.get_vocab` 
                        wall **1.442 ms**  self **1.407 ms**  `tokenization_qwen2.py:215`
              - `te.<locals>.ZImageTEModel_.__init__` 
                wall **52.829 ms**  self **0.014 ms**  `z_image.py:39`
                - `ZImageTEModel.__init__` 
                  wall **52.816 ms**  self **0.034 ms**  `z_image.py:33`
                  - `SD1ClipModel.__init__` 
                    wall **52.782 ms**  self **0.117 ms**  `sd1_clip.py:717`
                    - `Qwen3_4BModel.__init__` 
                      wall **52.525 ms**  self **0.038 ms**  `z_image.py:28`
                      - `SDClipModel.__init__` 
                        wall **52.487 ms**  self **0.568 ms**  `sd1_clip.py:88`
                        - `Qwen3_4B.__init__` 
                          wall **43.564 ms**  self **0.064 ms**  `llama.py:1215`
                          - `Llama2_.__init__` 
                            wall **43.439 ms**  self **0.228 ms**  `llama.py:766`
                            - `Llama2_.__init__.<locals>.<listcomp>` 
                              wall **25.821 ms**  self **0.107 ms**  `llama.py:780`
                              - `TransformerBlock.__init__` 
                                wall **1.376 ms**  self **0.011 ms**  `llama.py:654`
                              - `TransformerBlock.__init__` 
                                wall **1.140 ms**  self **0.060 ms**  `llama.py:654`
                            - `disable_weight_init.Embedding.__init__` 
                              wall **17.063 ms**  self **0.103 ms**  `ops.py:741`
                              - `Parameter.__new__` 
                                wall **16.811 ms**  self **16.811 ms**  `parameter.py:51`
                        - `SDClipModel.freeze` 
                          wall **8.182 ms**  self **0.109 ms**  `sd1_clip.py:146`
                          - `Module.eval` 
                            wall **4.883 ms**  self **0.004 ms**  `module.py:2916`
                            - `Module.train` 
                              wall **4.879 ms**  self **0.006 ms**  `module.py:2894`
                              - `Module.train` 
                                wall **4.859 ms**  self **0.008 ms**  `module.py:2894`
                                - `Module.train` 
                                  wall **4.808 ms**  self **0.033 ms**  `module.py:2894`
              - `CLIP.load_sd` 
                wall **25.833 ms**  self **0.438 ms**  `sd.py:429`
                - `SD1ClipModel.load_sd` 
                  wall **20.977 ms**  self **0.014 ms**  `sd1_clip.py:746`
                  - `SDClipModel.load_sd` 
                    wall **20.961 ms**  self **0.022 ms**  `sd1_clip.py:308`
                    - `Module.load_state_dict` 
                      wall **20.938 ms**  self **0.132 ms**  `module.py:2535`
                      - `Module.load_state_dict.<locals>.load` 
                        wall **20.805 ms**  self **0.028 ms**  `module.py:2589`
                        - `Module.load_state_dict.<locals>.load` 
                          wall **20.056 ms**  self **0.019 ms**  `module.py:2589`
                          - `Module.load_state_dict.<locals>.load` 
                            wall **19.151 ms**  self **0.102 ms**  `module.py:2589`
                            - `Module.load_state_dict.<locals>.load` 
                              wall **1.380 ms**  self **0.016 ms**  `module.py:2589`
                              - `Module.load_state_dict.<locals>.load` 
                                wall **1.118 ms**  self **0.022 ms**  `module.py:2589`
              - `archive_model_dtypes` 
                wall **6.936 ms**  self **1.172 ms**  `model_management.py:1045`
              - `ModelPatcherDynamic.__init__` 
                wall **1.034 ms**  self **0.059 ms**  `model_patcher.py:1757`
          - `_clip_meta_state_dict_from_header` 
            wall **242.532 ms**  self **234.511 ms**  `golden_serial.py:2217`
            - `parse_safetensors_header` 
              wall **7.705 ms**  self **6.438 ms**  `clip_qd_reader.py:300`
  - `golden_clip_load` 
    wall **3,662.699 ms**  self **0.201 ms**  `golden_serial.py:11497`
    - `_read_golden_m2_clip` 
      wall **3,652.102 ms**  self **0.035 ms**  `golden_serial.py:11462`
      - `GoldenModelTransport.load_sync` 
        wall **3,652.063 ms**  self **0.019 ms**  `golden_model_transport.py:1001`
        - `GoldenModelTransport._load_sync` 
          wall **3,652.044 ms**  self **0.034 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **3,652.010 ms**  self **0.044 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **3,651.966 ms**  self **0.554 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **3,391.289 ms**  self **3.319 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **1,064.014 ms**  self **0.106 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **263.192 ms**  self **263.192 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **250.783 ms**  self **250.783 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **250.601 ms**  self **250.601 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **250.046 ms**  self **250.046 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **44.840 ms**  self **44.797 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._recover_ready_from_table` 
                    wall **2.043 ms**  self **0.048 ms**  `golden_source_threads.py:1092`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.326 ms**  self **0.010 ms**  `golden_source_threads.py:1001`
                    - `Popen.poll` 
                      wall **1.316 ms**  self **0.004 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.311 ms**  self **1.311 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **156.160 ms**  self **0.022 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **155.760 ms**  self **155.725 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **102.833 ms**  self **0.021 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **102.296 ms**  self **102.254 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **78.396 ms**  self **0.016 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **77.706 ms**  self **77.678 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **78.254 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **77.739 ms**  self **77.708 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **70.248 ms**  self **0.018 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **69.795 ms**  self **69.767 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **51.882 ms**  self **0.010 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **51.626 ms**  self **51.586 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.wait_ready` 
                  wall **50.445 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **49.981 ms**  self **49.941 ms**  `golden_source_threads.py:892`
                _... 113 more children >= 1 ms omitted_
              - `GoldenModelTransport.inspect` 
                wall **223.874 ms**  self **0.042 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **223.389 ms**  self **222.734 ms**  `golden_model_transport.py:304`
              - `GoldenModelTransport._views` 
                wall **19.866 ms**  self **19.866 ms**  `golden_model_transport.py:1910`
              - `SourceThreadProcess.snapshot` 
                wall **5.139 ms**  self **0.627 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **3.699 ms**  self **0.456 ms**  `golden_source_threads.py:589`
              - `SourceThreadProcess.snapshot` 
                wall **4.986 ms**  self **0.552 ms**  `golden_source_threads.py:1232`
                - `_time_weighted_concurrency` 
                  wall **3.811 ms**  self **0.448 ms**  `golden_source_threads.py:589`
              - `GpuDestinationPool.acquire` 
                wall **2.640 ms**  self **0.060 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **2.572 ms**  self **2.411 ms**  `golden_model_transport.py:156`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **2.531 ms**  self **0.132 ms**  `golden_qd_transport.py:3130`
    - `GoldenTelemetryRecorder.event` 
      wall **7.559 ms**  self **0.009 ms**  `golden_serial.py:1672`
      - `GoldenTelemetryRecorder.event_at` 
        wall **7.550 ms**  self **0.007 ms**  `golden_serial.py:1675`
        - `deepcopy` 
          wall **7.542 ms**  self **0.006 ms**  `copy.py:128`
          - `_deepcopy_dict` 
            wall **7.535 ms**  self **0.034 ms**  `copy.py:227`
            - `deepcopy` 
              wall **7.422 ms**  self **0.002 ms**  `copy.py:128`
              - `_deepcopy_dict` 
                wall **7.419 ms**  self **0.007 ms**  `copy.py:227`
                - `deepcopy` 
                  wall **6.978 ms**  self **0.002 ms**  `copy.py:128`
                  - `_deepcopy_dict` 
                    wall **6.976 ms**  self **0.145 ms**  `copy.py:227`
                    - `deepcopy` 
                      wall **4.980 ms**  self **0.003 ms**  `copy.py:128`
                      - `_deepcopy_list` 
                        wall **4.974 ms**  self **1.709 ms**  `copy.py:201`
                    - `deepcopy` 
                      wall **1.088 ms**  self **0.002 ms**  `copy.py:128`
                      - `_deepcopy_dict` 
                        wall **1.077 ms**  self **0.144 ms**  `copy.py:227`
  - `golden.clip_load.source_open_read` 
    wall **3,652.165 ms**  self **3,652.165 ms**  `full_execution_trace.py:330`
  - `golden_clip_load` 
    wall **95.279 ms**  self **0.381 ms**  `golden_serial.py:11497`
    - `select_and_validate_qd_adoption_scope` 
      wall **58.579 ms**  self **1.150 ms**  `golden_serial.py:13011`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **7.318 ms**  self **0.218 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.670 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.667 ms**  self **0.555 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.661 ms**  self **0.180 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.789 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.786 ms**  self **0.459 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.554 ms**  self **0.221 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.660 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.657 ms**  self **0.450 ms**  `module.py:2650`
      - `validate_qd_adoption` 
        wall **6.474 ms**  self **1.388 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **2.068 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.066 ms**  self **0.445 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **6.304 ms**  self **0.387 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **2.563 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.561 ms**  self **0.408 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **4.638 ms**  self **0.164 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **1.575 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.572 ms**  self **0.347 ms**  `module.py:2650`
      - `select_and_validate_qd_adoption_scope.<locals>._collect` 
        wall **4.134 ms**  self **0.153 ms**  `golden_serial.py:13063`
        - `Module.named_buffers` 
          wall **1.763 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.761 ms**  self **0.373 ms**  `module.py:2650`
    - `CLIP.load_sd` 
      wall **27.616 ms**  self **0.338 ms**  `sd.py:429`
      - `SD1ClipModel.load_sd` 
        wall **23.686 ms**  self **0.008 ms**  `sd1_clip.py:746`
        - `SDClipModel.load_sd` 
          wall **23.677 ms**  self **0.017 ms**  `sd1_clip.py:308`
          - `Module.load_state_dict` 
            wall **23.658 ms**  self **0.111 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **23.547 ms**  self **0.010 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **23.180 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **21.895 ms**  self **0.119 ms**  `module.py:2589`
    - `_clip_compute_identity` 
      wall **7.096 ms**  self **0.022 ms**  `golden_serial.py:10815`
      - `_clip_scope_snapshot` 
        wall **6.968 ms**  self **1.569 ms**  `golden_serial.py:10774`
        - `Module.named_buffers` 
          wall **2.186 ms**  self **0.002 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.184 ms**  self **0.441 ms**  `module.py:2650`
  - `golden.clip_load.storage_adoption` 
    wall **58.620 ms**  self **58.620 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_bind_assign` 
    wall **27.646 ms**  self **27.646 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.compute_ready_proof` 
    wall **7.110 ms**  self **7.110 ms**  `full_execution_trace.py:330`
  - `golden.clip_load.skeleton_patcher_construction` 
    wall **1.012 ms**  self **0.568 ms**  `full_execution_trace.py:330`

## `golden_clip_forward`

- Stage wall: **4,324.751 ms**

- `golden_clip_forward` 
  wall **4,324.751 ms**  self **4,324.751 ms**  `full_execution_trace.py:330`
  - `golden_clip_forward` 
    wall **4,324.656 ms**  self **0.193 ms**  `golden_serial.py:12420`
    - `GoldenSerialRunner.run_closure` 
      wall **4,310.536 ms**  self **0.055 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,308.817 ms**  self **0.043 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,308.558 ms**  self **0.026 ms**  `golden_serial.py:9035`
          - `CLIPTextEncode.encode` 
            wall **4,308.380 ms**  self **0.022 ms**  `nodes.py:73`
            - `CLIP.encode_from_tokens_scheduled` 
              wall **3,410.801 ms**  self **0.021 ms**  `sd.py:335`
              - `CLIP.encode_from_tokens` 
                wall **3,410.780 ms**  self **0.057 ms**  `sd.py:396`
                - `SD1ClipModel.encode_token_weights` 
                  wall **3,174.053 ms**  self **0.040 ms**  `sd1_clip.py:741`
                  - `ClipTokenWeightEncoder.encode_token_weights` 
                    wall **3,174.012 ms**  self **4.117 ms**  `sd1_clip.py:28`
                    - `SDClipModel.encode` 
                      wall **3,169.843 ms**  self **0.004 ms**  `sd1_clip.py:305`
                      - `Module._wrapped_call_impl` 
                        wall **3,169.838 ms**  self **0.018 ms**  `module.py:1779`
                        - `Module._call_impl` 
                          wall **3,169.820 ms**  self **0.037 ms**  `module.py:1787`
                          - `SDClipModel.forward` 
                            wall **3,169.783 ms**  self **0.075 ms**  `sd1_clip.py:260`
                            - `Module._wrapped_call_impl` 
                              wall **3,080.120 ms**  self **0.010 ms**  `module.py:1779`
                              - `Module._call_impl` 
                                wall **3,080.110 ms**  self **0.024 ms**  `module.py:1787`
                                - `BaseLlama.forward` 
                                  wall **3,080.086 ms**  self **0.008 ms**  `llama.py:998`
                                  - `Module._wrapped_call_impl` 
                                    wall **3,080.076 ms**  self **0.006 ms**  `module.py:1779`
                                    - `Module._call_impl` 
                                      wall **3,080.070 ms**  self **0.107 ms**  `module.py:1787`
                                      - `Llama2_.forward` 
                                        wall **3,079.963 ms**  self **333.808 ms**  `llama.py:824`
                                        - `Llama2_.compute_freqs_cis` 
                                          wall **1,958.262 ms**  self **0.201 ms**  `llama.py:815`
                                          - `precompute_freqs_cis` 
                                            wall **1,958.062 ms**  self **158.885 ms**  `llama.py:445`
                                            - `_register_overrides_from_graph.<locals>.eager_router` 
                                              wall **1,555.023 ms**  self **0.021 ms**  `registry.py:938`
                                              - `_register_overrides_from_graph.<locals>._dispatch` 
                                                wall **1,554.997 ms**  self **0.087 ms**  `registry.py:926`
                                                - `OpOverloadPacket.__call__` 
                                                  wall **1,554.149 ms**  self **0.088 ms**  `_ops.py:1338`
                                                  - `_bmm_outer_product_impl` 
                                                    wall **1,554.060 ms**  self **42.954 ms**  `triton_impl.py:18`
                                                    - `bmm_outer_product` 
                                                      wall **1,511.058 ms**  self **0.369 ms**  `triton_kernels.py:77`
                                                      - `_make_wrapper.<locals>.wrapper` 
                                                        wall **1,510.578 ms**  self **0.016 ms**  `instrumentation.py:202`
                                                        - `KernelInterface.__getitem__.<locals>.<lambda>` 
                                                          wall **1,510.503 ms**  self **0.026 ms**  `jit.py:374`
                                                          - `JITFunction.run` 
                                                            wall **1,510.477 ms**  self **0.108 ms**  `jit.py:726`
                                                            - `DriverConfig.active` 
                                                              wall **959.932 ms**  self **0.009 ms**  `driver.py:36`
                                                              - `DriverConfig.default` 
                                                                wall **959.924 ms**  self **0.011 ms**  `driver.py:30`
                                                                - `_create_driver` 
                                                                  wall **959.913 ms**  self **0.028 ms**  `driver.py:8`
                                                                  - `CudaDriver.__init__` 
                                                                    wall **959.839 ms**  self **0.040 ms**  `driver.py:341`
                                                                    - `CudaUtils.__init__` 
                                                                      wall **959.771 ms**  self **0.038 ms**  `driver.py:100`
                                                                      - `compile_module_from_file` 
                                                                        wall **930.083 ms**  self **0.023 ms**  `build.py:193`
                                                                        - `_compile_so_from_file` 
                                                                          wall **930.059 ms**  self **2.167 ms**  `build.py:157`
                                                                          - `_compile_so` 
                                                                            wall **927.780 ms**  self **0.394 ms**  `build.py:132`
                                                                            - `_build` 
                                                                              wall **917.801 ms**  self **0.062 ms**  `build.py:60`
                                                                              - `check_call` 
                                                                                wall **913.361 ms**  self **0.013 ms**  `subprocess.py:398`
                                                                                - `call` 
                                                                                  wall **913.344 ms**  self **0.013 ms**  `subprocess.py:381`
                                                                                  - `Popen.wait` 
                                                                                    wall **904.038 ms**  self **0.003 ms**  `subprocess.py:1259`
                                                                                    - `Popen._wait` 
                                                                                      wall **904.035 ms**  self **0.018 ms**  `subprocess.py:2014`
                                                                                      - `Popen._try_wait` 
                                                                                        wall **904.013 ms**  self **904.013 ms**  `subprocess.py:2001`
                                                                                  - `Popen.__init__` 
                                                                                    wall **9.283 ms**  self **0.016 ms**  `subprocess.py:807`
                                                                                    - `Popen._execute_child` 
                                                                                      wall **9.170 ms**  self **9.081 ms**  `subprocess.py:1789`
                                                                              - `_find_compiler` 
                                                                                wall **3.435 ms**  self **0.036 ms**  `build.py:21`
                                                                                - `which` 
                                                                                  wall **2.555 ms**  self **0.091 ms**  `shutil.py:1452`
                                                                                  - `_access_check` 
                                                                                    wall **2.123 ms**  self **2.123 ms**  `shutil.py:1447`
                                                                            - `_get_cache_manager` 
                                                                              wall **7.401 ms**  self **0.180 ms**  `build.py:117`
                                                                              - `platform_key` 
                                                                                wall **6.686 ms**  self **0.026 ms**  `build.py:94`
                                                                                - `architecture` 
                                                                                  wall **6.648 ms**  self **0.044 ms**  `platform.py:646`
                                                                                  - `_syscmd_file` 
                                                                                    wall **6.605 ms**  self **0.839 ms**  `platform.py:602`
                                                                                    - `check_output` 
                                                                                      wall **5.576 ms**  self **0.009 ms**  `subprocess.py:417`
                                                                                      - `run` 
                                                                                        wall **5.567 ms**  self **0.007 ms**  `subprocess.py:506`
                                                                                        - `Popen.__init__` 
                                                                                          wall **5.560 ms**  self **0.170 ms**  `subprocess.py:807`
                                                                                          - `Popen._execute_child` 
                                                                                            wall **5.200 ms**  self **5.100 ms**  `subprocess.py:1789`
                                                                            - `_load_module_from_path` 
                                                                              wall **1.094 ms**  self **1.094 ms**  `build.py:108`
                                                                      - `library_dirs` 
                                                                        wall **29.650 ms**  self **0.017 ms**  `driver.py:49`
                                                                        - `libcuda_dirs` 
                                                                          wall **29.633 ms**  self **0.184 ms**  `driver.py:25`
                                                                          - `check_output` 
                                                                            wall **29.241 ms**  self **0.017 ms**  `subprocess.py:417`
                                                                            - `run` 
                                                                              wall **29.221 ms**  self **0.065 ms**  `subprocess.py:506`
                                                                              - `Popen.communicate` 
                                                                                wall **22.872 ms**  self **22.797 ms**  `subprocess.py:1165`
                                                                              - `Popen.__init__` 
                                                                                wall **6.277 ms**  self **0.404 ms**  `subprocess.py:807`
                                                                                - `Popen._execute_child` 
                                                                                  wall **5.783 ms**  self **5.659 ms**  `subprocess.py:1789`
                                                            - `JITFunction._do_compile` 
                                                              wall **324.549 ms**  self **0.049 ms**  `jit.py:877`
                                                              - `compile` 
                                                                wall **324.483 ms**  self **28.201 ms**  `compiler.py:226`
                                                                - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                  wall **63.403 ms**  self **0.086 ms**  `compiler.py:605`
                                                                  - `CUDABackend.make_llir` 
                                                                    wall **63.317 ms**  self **63.182 ms**  `compiler.py:367`
                                                                - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                  wall **58.424 ms**  self **0.011 ms**  `compiler.py:606`
                                                                  - `CUDABackend.make_ptx` 
                                                                    wall **58.412 ms**  self **57.097 ms**  `compiler.py:480`
                                                                - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                  wall **50.943 ms**  self **0.035 ms**  `compiler.py:607`
                                                                  - `CUDABackend.make_cubin` 
                                                                    wall **50.906 ms**  self **0.556 ms**  `compiler.py:513`
                                                                    - `run` 
                                                                      wall **49.637 ms**  self **0.025 ms**  `subprocess.py:506`
                                                                      - `Popen.communicate` 
                                                                        wall **46.017 ms**  self **0.005 ms**  `subprocess.py:1165`
                                                                        - `Popen.wait` 
                                                                          wall **46.012 ms**  self **0.003 ms**  `subprocess.py:1259`
                                                                          - `Popen._wait` 
                                                                            wall **46.009 ms**  self **0.020 ms**  `subprocess.py:2014`
                                                                            - `Popen._try_wait` 
                                                                              wall **45.986 ms**  self **45.986 ms**  `subprocess.py:2001`
                                                                      - `Popen.__init__` 
                                                                        wall **3.581 ms**  self **0.015 ms**  `subprocess.py:807`
                                                                        - `Popen._execute_child` 
                                                                          wall **3.530 ms**  self **0.024 ms**  `subprocess.py:1789`
                                                                          - `Popen._posix_spawn` 
                                                                            wall **3.506 ms**  self **3.486 ms**  `subprocess.py:1750`
                                                                - `get_cache_key` 
                                                                  wall **40.451 ms**  self **0.026 ms**  `cache.py:319`
                                                                  - `CUDABackend.hash` 
                                                                    wall **36.469 ms**  self **0.012 ms**  `compiler.py:611`
                                                                    - `get_ptxas_version` 
                                                                      wall **36.456 ms**  self **0.014 ms**  `compiler.py:42`
                                                                      - `get_ptxas` 
                                                                        wall **28.168 ms**  self **0.005 ms**  `compiler.py:38`
                                                                        - `env_base.__get__` 
                                                                          wall **28.163 ms**  self **0.003 ms**  `knobs.py:76`
                                                                          - `env_nvidia_tool.get` 
                                                                            wall **28.160 ms**  self **0.004 ms**  `knobs.py:203`
                                                                            - `env_nvidia_tool.transform` 
                                                                              wall **28.156 ms**  self **0.010 ms**  `knobs.py:206`
                                                                              - `NvidiaTool.from_path` 
                                                                                wall **28.147 ms**  self **0.021 ms**  `knobs.py:181`
                                                                                - `check_output` 
                                                                                  wall **27.674 ms**  self **0.018 ms**  `subprocess.py:417`
                                                                                  - `run` 
                                                                                    wall **27.652 ms**  self **0.037 ms**  `subprocess.py:506`
                                                                                    - `Popen.communicate` 
                                                                                      wall **15.618 ms**  self **15.504 ms**  `subprocess.py:1165`
                                                                                    - `Popen.__init__` 
                                                                                      wall **11.983 ms**  self **0.061 ms**  `subprocess.py:807`
                                                                                      - `Popen._execute_child` 
                                                                                        wall **11.760 ms**  self **11.634 ms**  `subprocess.py:1789`
                                                                      - `check_output` 
                                                                        wall **8.268 ms**  self **0.012 ms**  `subprocess.py:417`
                                                                        - `run` 
                                                                          wall **8.254 ms**  self **0.017 ms**  `subprocess.py:506`
                                                                          - `Popen.communicate` 
                                                                            wall **4.990 ms**  self **4.940 ms**  `subprocess.py:1165`
                                                                          - `Popen.__init__` 
                                                                            wall **3.240 ms**  self **0.146 ms**  `subprocess.py:807`
                                                                            - `Popen._execute_child` 
                                                                              wall **2.816 ms**  self **2.771 ms**  `subprocess.py:1789`
                                                                  - `CUDAOptions.hash` 
                                                                    wall **2.059 ms**  self **0.049 ms**  `compiler.py:153`
                                                                    - `CUDAOptions.hash.<locals>.<genexpr>` 
                                                                      wall **1.976 ms**  self **0.012 ms**  `compiler.py:155`
                                                                      - `file_hash` 
                                                                        wall **1.964 ms**  self **1.964 ms**  `compiler.py:97`
                                                                  - `ASTSource.hash` 
                                                                    wall **1.897 ms**  self **0.042 ms**  `compiler.py:71`
                                                                    - `JITCallable.cache_key` 
                                                                      wall **1.842 ms**  self **0.070 ms**  `jit.py:515`
                                                                - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                  wall **30.680 ms**  self **0.121 ms**  `compiler.py:602`
                                                                  - `CUDABackend.make_ttgir` 
                                                                    wall **30.559 ms**  self **30.559 ms**  `compiler.py:260`
                                                                - `ASTSource.make_ir` 
                                                                  wall **21.979 ms**  self **0.035 ms**  `compiler.py:78`
                                                                  - `ast_to_ttir` 
                                                                    wall **21.944 ms**  self **0.763 ms**  `code_generator.py:1662`
                                                                    - `CodeGenerator.visit` 
                                                                      wall **19.237 ms**  self **0.026 ms**  `code_generator.py:1581`
                                                                      - `NodeVisitor.visit` 
                                                                        wall **19.211 ms**  self **0.006 ms**  `ast.py:414`
                                                                        - `CodeGenerator.visit_Module` 
                                                                          wall **19.206 ms**  self **0.003 ms**  `code_generator.py:519`
                                                                          - `NodeVisitor.generic_visit` 
                                                                            wall **19.203 ms**  self **0.009 ms**  `ast.py:420`
                                                                            - `CodeGenerator.visit` 
                                                                              wall **19.191 ms**  self **0.017 ms**  `code_generator.py:1581`
                                                                              - `NodeVisitor.visit` 
                                                                                wall **19.173 ms**  self **0.011 ms**  `ast.py:414`
                                                                                - `CodeGenerator.visit_FunctionDef` 
                                                                                  wall **19.162 ms**  self **0.148 ms**  `code_generator.py:628`
                                                                                  - `CodeGenerator.visit_compound_statement` 
                                                                                    wall **17.463 ms**  self **0.033 ms**  `code_generator.py:508`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **3.763 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **3.756 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **3.754 ms**  self **0.011 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **3.710 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                                                            - `NodeVisitor.visit` 
                                                                                              wall **3.695 ms**  self **0.002 ms**  `ast.py:414`
                                                                                              - `CodeGenerator.visit_Call` 
                                                                                                wall **3.693 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                                                                - `CodeGenerator.call_Function` 
                                                                                                  wall **3.318 ms**  self **0.014 ms**  `code_generator.py:1398`
                                                                                                  - `CodeGenerator.call_JitFunction` 
                                                                                                    wall **3.303 ms**  self **0.083 ms**  `code_generator.py:1358`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **2.958 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **2.953 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Module` 
                                                                                                          wall **2.951 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                                                          - `NodeVisitor.generic_visit` 
                                                                                                            wall **2.949 ms**  self **0.012 ms**  `ast.py:420`
                                                                                                            - `CodeGenerator.visit` 
                                                                                                              wall **2.935 ms**  self **2.935 ms**  `code_generator.py:1581`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **3.035 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **3.028 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **3.026 ms**  self **0.011 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **2.985 ms**  self **0.014 ms**  `code_generator.py:1581`
                                                                                            - `NodeVisitor.visit` 
                                                                                              wall **2.970 ms**  self **0.003 ms**  `ast.py:414`
                                                                                              - `CodeGenerator.visit_Call` 
                                                                                                wall **2.968 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                                                                - `CodeGenerator.call_Function` 
                                                                                                  wall **2.877 ms**  self **0.005 ms**  `code_generator.py:1398`
                                                                                                  - `CodeGenerator.call_JitFunction` 
                                                                                                    wall **2.871 ms**  self **0.056 ms**  `code_generator.py:1358`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **2.607 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **2.603 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Module` 
                                                                                                          wall **2.601 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                                                          - `NodeVisitor.generic_visit` 
                                                                                                            wall **2.599 ms**  self **0.009 ms**  `ast.py:420`
                                                                                                            - `CodeGenerator.visit` 
                                                                                                              wall **2.588 ms**  self **2.588 ms**  `code_generator.py:1581`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **2.033 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **2.027 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Expr` 
                                                                                          wall **2.025 ms**  self **0.004 ms**  `code_generator.py:1556`
                                                                                          - `NodeVisitor.generic_visit` 
                                                                                            wall **2.021 ms**  self **0.006 ms**  `ast.py:420`
                                                                                            - `CodeGenerator.visit` 
                                                                                              wall **2.014 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                              - `NodeVisitor.visit` 
                                                                                                wall **2.008 ms**  self **0.003 ms**  `ast.py:414`
                                                                                                - `CodeGenerator.visit_Call` 
                                                                                                  wall **2.005 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                                                                  - `CodeGenerator.visit` 
                                                                                                    wall **1.687 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                                                    - `NodeVisitor.visit` 
                                                                                                      wall **1.682 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                      - `CodeGenerator.visit_BinOp` 
                                                                                                        wall **1.679 ms**  self **0.004 ms**  `code_generator.py:810`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **1.820 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **1.813 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **1.810 ms**  self **0.009 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **1.767 ms**  self **0.014 ms**  `code_generator.py:1581`
                                                                                            - `NodeVisitor.visit` 
                                                                                              wall **1.753 ms**  self **0.003 ms**  `ast.py:414`
                                                                                              - `CodeGenerator.visit_Call` 
                                                                                                wall **1.750 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                                                                - `CodeGenerator.visit` 
                                                                                                  wall **1.463 ms**  self **0.069 ms**  `code_generator.py:1581`
                                                                                                  - `NodeVisitor.visit` 
                                                                                                    wall **1.394 ms**  self **0.004 ms**  `ast.py:414`
                                                                                                    - `CodeGenerator.visit_BinOp` 
                                                                                                      wall **1.390 ms**  self **0.007 ms**  `code_generator.py:810`
                                                                                                      - `CodeGenerator.visit` 
                                                                                                        wall **1.004 ms**  self **0.012 ms**  `code_generator.py:1581`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **1.426 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **1.421 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **1.419 ms**  self **0.007 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **1.388 ms**  self **0.011 ms**  `code_generator.py:1581`
                                                                                            - `NodeVisitor.visit` 
                                                                                              wall **1.376 ms**  self **0.003 ms**  `ast.py:414`
                                                                                              - `CodeGenerator.visit_Call` 
                                                                                                wall **1.374 ms**  self **0.008 ms**  `code_generator.py:1455`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **1.314 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **1.308 ms**  self **0.001 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **1.306 ms**  self **0.009 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **1.263 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                                                            - `NodeVisitor.visit` 
                                                                                              wall **1.248 ms**  self **0.005 ms**  `ast.py:414`
                                                                                              - `CodeGenerator.visit_BinOp` 
                                                                                                wall **1.242 ms**  self **0.004 ms**  `code_generator.py:810`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **1.089 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                      - `NodeVisitor.visit` 
                                                                                        wall **1.082 ms**  self **0.002 ms**  `ast.py:414`
                                                                                        - `CodeGenerator.visit_Assign` 
                                                                                          wall **1.080 ms**  self **0.010 ms**  `code_generator.py:727`
                                                                                          - `CodeGenerator.visit` 
                                                                                            wall **1.042 ms**  self **0.094 ms**  `code_generator.py:1581`
                                                                                    - `CodeGenerator.visit` 
                                                                                      wall **1.001 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                - `FileCacheManager.put` 
                                                                  wall **10.807 ms**  self **10.585 ms**  `cache.py:103`
                                                                - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                  wall **6.338 ms**  self **0.045 ms**  `compiler.py:601`
                                                                  - `CUDABackend.make_ttir` 
                                                                    wall **6.293 ms**  self **6.293 ms**  `compiler.py:244`
                                                                _... 5 more children >= 1 ms omitted_
                                                            - `dynamic_func` 
                                                              wall **215.201 ms**  self **215.165 ms**  `<string>:2`
                                                            - `CompiledKernel.launch_metadata` 
                                                              wall **8.603 ms**  self **0.021 ms**  `compiler.py:493`
                                                              - `CompiledKernel._init_handles` 
                                                                wall **8.581 ms**  self **1.422 ms**  `compiler.py:448`
                                                                - `max_shared_mem` 
                                                                  wall **6.798 ms**  self **6.798 ms**  `compiler.py:133`
                                            - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                              wall **144.471 ms**  self **0.021 ms**  `_tensor.py:32`
                                              - `Tensor.__rpow__` 
                                                wall **144.450 ms**  self **144.450 ms**  `_tensor.py:1155`
                                            - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                              wall **99.683 ms**  self **0.016 ms**  `_tensor.py:32`
                                              - `Tensor.__rdiv__` 
                                                wall **99.666 ms**  self **99.666 ms**  `_tensor.py:1120`
                                        - `prefetch_queue_pop` 
                                          wall **563.827 ms**  self **0.005 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **563.823 ms**  self **0.010 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **563.813 ms**  self **0.008 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **563.805 ms**  self **0.026 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **563.779 ms**  self **0.303 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **488.625 ms**  self **0.007 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **488.618 ms**  self **0.249 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **488.369 ms**  self **100.437 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **323.148 ms**  self **0.006 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **323.142 ms**  self **0.011 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **323.131 ms**  self **0.030 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **323.082 ms**  self **322.121 ms**  `ops.py:566`
                                                        - `apply_rope` 
                                                          wall **61.023 ms**  self **61.023 ms**  `llama.py:492`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.467 ms**  self **0.005 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.463 ms**  self **0.015 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **1.447 ms**  self **0.011 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **1.418 ms**  self **0.277 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **1.133 ms**  self **0.007 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **1.126 ms**  self **1.097 ms**  `ops.py:337`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.135 ms**  self **0.004 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.130 ms**  self **0.020 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **1.110 ms**  self **0.035 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **1.049 ms**  self **0.820 ms**  `ops.py:566`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **44.711 ms**  self **0.005 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **44.706 ms**  self **0.008 ms**  `module.py:1787`
                                                      - `RMSNorm.forward` 
                                                        wall **44.698 ms**  self **0.011 ms**  `llama.py:436`
                                                        - `rms_norm` 
                                                          wall **44.685 ms**  self **0.028 ms**  `rmsnorm.py:7`
                                                          - `rms_norm` 
                                                            wall **44.572 ms**  self **44.572 ms**  `functional.py:2998`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **29.964 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **29.960 ms**  self **0.021 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **29.939 ms**  self **0.227 ms**  `llama.py:644`
                                                        - `silu` 
                                                          wall **26.781 ms**  self **26.781 ms**  `functional.py:2429`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **2.156 ms**  self **0.003 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **2.153 ms**  self **0.005 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **2.148 ms**  self **0.039 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **2.099 ms**  self **0.202 ms**  `ops.py:566`
                                                                - `CastBiasWeightContext.__init__` 
                                                                  wall **1.888 ms**  self **0.006 ms**  `ops.py:464`
                                                                  - `cast_bias_weight` 
                                                                    wall **1.883 ms**  self **1.865 ms**  `ops.py:337`
                                        - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                          wall **81.602 ms**  self **0.012 ms**  `_tensor.py:32`
                                          - `Tensor.__rsub__` 
                                            wall **81.590 ms**  self **81.590 ms**  `_tensor.py:1116`
                                        - `prefetch_queue_pop` 
                                          wall **13.845 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **13.843 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **13.837 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **13.833 ms**  self **0.006 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **13.828 ms**  self **0.209 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **11.902 ms**  self **0.006 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **11.895 ms**  self **0.212 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **11.683 ms**  self **10.260 ms**  `llama.py:540`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.369 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.366 ms**  self **0.014 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.352 ms**  self **0.154 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **8.206 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **8.204 ms**  self **0.005 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **8.199 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **8.195 ms**  self **0.009 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **8.186 ms**  self **0.156 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **6.213 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **6.209 ms**  self **0.019 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **6.190 ms**  self **1.659 ms**  `llama.py:540`
                                                        - `apply_rope` 
                                                          wall **2.365 ms**  self **2.365 ms**  `llama.py:492`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.359 ms**  self **0.002 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.357 ms**  self **0.005 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.352 ms**  self **0.127 ms**  `llama.py:644`
                                        - `prefetch_queue_pop` 
                                          wall **7.381 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **7.379 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **7.375 ms**  self **0.003 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **7.371 ms**  self **0.006 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **7.365 ms**  self **0.059 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **5.549 ms**  self **0.003 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **5.546 ms**  self **0.011 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **5.535 ms**  self **0.904 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.900 ms**  self **0.002 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.898 ms**  self **0.005 ms**  `module.py:1787`
                                                            - `RMSNorm.forward` 
                                                              wall **1.892 ms**  self **0.005 ms**  `llama.py:436`
                                                              - `rms_norm` 
                                                                wall **1.887 ms**  self **0.009 ms**  `rmsnorm.py:7`
                                                                - `cast_to` 
                                                                  wall **1.762 ms**  self **1.762 ms**  `model_management.py:1527`
                                                        - `apply_rope` 
                                                          wall **1.807 ms**  self **1.807 ms**  `llama.py:492`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **1.527 ms**  self **0.002 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **1.524 ms**  self **0.005 ms**  `module.py:1787`
                                                      - `MLP.forward` 
                                                        wall **1.520 ms**  self **0.124 ms**  `llama.py:644`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.081 ms**  self **0.005 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.076 ms**  self **0.013 ms**  `module.py:1787`
                                                            - `disable_weight_init.Linear.forward` 
                                                              wall **1.064 ms**  self **0.032 ms**  `ops.py:570`
                                                              - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                wall **1.021 ms**  self **0.880 ms**  `ops.py:566`
                                        - `prefetch_queue_pop` 
                                          wall **6.616 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **6.614 ms**  self **0.004 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **6.610 ms**  self **0.004 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **6.606 ms**  self **0.008 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **6.599 ms**  self **0.055 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **5.708 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **5.704 ms**  self **0.012 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **5.692 ms**  self **2.988 ms**  `llama.py:540`
                                                        - `Module._wrapped_call_impl` 
                                                          wall **1.107 ms**  self **0.004 ms**  `module.py:1779`
                                                          - `Module._call_impl` 
                                                            wall **1.103 ms**  self **0.009 ms**  `module.py:1787`
                                                            - `RMSNorm.forward` 
                                                              wall **1.094 ms**  self **0.005 ms**  `llama.py:436`
                                                              - `rms_norm` 
                                                                wall **1.088 ms**  self **0.018 ms**  `rmsnorm.py:7`
                                        - `prefetch_queue_pop` 
                                          wall **6.452 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                          - `Llama2_.forward.<locals>.core` 
                                            wall **6.450 ms**  self **0.006 ms**  `llama.py:912`
                                            - `Module._wrapped_call_impl` 
                                              wall **6.444 ms**  self **0.005 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **6.439 ms**  self **0.085 ms**  `module.py:1787`
                                                - `TransformerBlock.forward` 
                                                  wall **6.354 ms**  self **0.279 ms**  `llama.py:661`
                                                  - `Module._wrapped_call_impl` 
                                                    wall **4.622 ms**  self **0.004 ms**  `module.py:1779`
                                                    - `Module._call_impl` 
                                                      wall **4.618 ms**  self **0.021 ms**  `module.py:1787`
                                                      - `Attention.forward` 
                                                        wall **4.597 ms**  self **2.523 ms**  `llama.py:540`
                                        _... 30 more children >= 1 ms omitted_
                            - `SDClipModel.process_tokens` 
                              wall **89.582 ms**  self **1.419 ms**  `sd1_clip.py:172`
                              - `Module._wrapped_call_impl` 
                                wall **88.150 ms**  self **0.009 ms**  `module.py:1779`
                                - `Module._call_impl` 
                                  wall **88.141 ms**  self **0.019 ms**  `module.py:1787`
                                  - `disable_weight_init.Embedding.forward` 
                                    wall **88.121 ms**  self **0.013 ms**  `ops.py:798`
                                    - `disable_weight_init.Embedding.forward_comfy_cast_weights` 
                                      wall **88.078 ms**  self **36.363 ms**  `ops.py:790`
                                      - `embedding` 
                                        wall **51.365 ms**  self **51.365 ms**  `functional.py:2509`
                - `CLIP.load_model` 
                  wall **236.515 ms**  self **0.025 ms**  `sd.py:459`
                  - `load_models_gpu` 
                    wall **236.487 ms**  self **0.181 ms**  `model_management.py:909`
                    - `LoadedModel.model_load` 
                      wall **198.323 ms**  self **0.044 ms**  `model_management.py:782`
                      - `LoadedModel.model_use_more_vram` 
                        wall **198.235 ms**  self **0.007 ms**  `model_management.py:817`
                        - `ModelPatcherDynamic.partially_load` 
                          wall **198.227 ms**  self **0.276 ms**  `model_patcher.py:2141`
                          - `ModelPatcherDynamic.load` 
                            wall **197.819 ms**  self **9.898 ms**  `model_patcher.py:1853`
                            - `ModelPatcher._load_list` 
                              wall **110.661 ms**  self **67.564 ms**  `model_patcher.py:945`
                              - `module_size` 
                                wall **3.270 ms**  self **0.006 ms**  `model_management.py:631`
                                - `Module.state_dict` 
                                  wall **3.264 ms**  self **0.014 ms**  `module.py:2199`
                                  - `Module._save_to_state_dict` 
                                    wall **3.250 ms**  self **3.250 ms**  `module.py:2148`
                            - `HostBuffer.__del__` 
                              wall **16.190 ms**  self **16.130 ms**  `host_buffer.py:125`
                            - `Module.named_buffers` 
                              wall **6.075 ms**  self **0.006 ms**  `module.py:2754`
                              - `Module._named_members` 
                                wall **6.068 ms**  self **3.695 ms**  `module.py:2650`
                            - `ModelVBAR.prioritize` 
                              wall **3.459 ms**  self **3.451 ms**  `model_vbar.py:60`
                            - `ModelPatcherDynamic._vbar_get` 
                              wall **2.377 ms**  self **0.031 ms**  `model_patcher.py:1797`
                              - `ModelVBAR.__init__` 
                                wall **2.345 ms**  self **2.243 ms**  `model_vbar.py:50`
                            - `HostBuffer.__init__` 
                              wall **1.336 ms**  self **1.322 ms**  `host_buffer.py:79`
                    - `LoadedModel.model_memory_required` 
                      wall **31.568 ms**  self **0.008 ms**  `model_management.py:776`
                      - `LoadedModel.model_memory` 
                        wall **31.558 ms**  self **0.009 ms**  `model_management.py:767`
                        - `ModelPatcher.model_size` 
                          wall **31.549 ms**  self **6.169 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **25.380 ms**  self **0.134 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **25.246 ms**  self **0.022 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **25.220 ms**  self **0.023 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **24.724 ms**  self **0.021 ms**  `module.py:2199`
                                  - `Module.state_dict` 
                                    wall **24.700 ms**  self **0.029 ms**  `module.py:2199`
                                    - `Module.state_dict` 
                                      wall **24.519 ms**  self **0.100 ms**  `module.py:2199`
                                      - `Module.state_dict` 
                                        wall **4.827 ms**  self **0.024 ms**  `module.py:2199`
                                        - `Module.state_dict` 
                                          wall **4.153 ms**  self **0.029 ms**  `module.py:2199`
                                          - `Module.state_dict` 
                                            wall **2.876 ms**  self **0.013 ms**  `module.py:2199`
                                            - `Module._save_to_state_dict` 
                                              wall **2.863 ms**  self **2.863 ms**  `module.py:2148`
                                          - `Module.state_dict` 
                                            wall **1.206 ms**  self **0.010 ms**  `module.py:2199`
                                            - `Module._save_to_state_dict` 
                                              wall **1.196 ms**  self **1.196 ms**  `module.py:2148`
                                      - `Module.state_dict` 
                                        wall **1.857 ms**  self **0.012 ms**  `module.py:2199`
                                        - `Module.state_dict` 
                                          wall **1.358 ms**  self **0.022 ms**  `module.py:2199`
                                      - `Module.state_dict` 
                                        wall **1.663 ms**  self **0.012 ms**  `module.py:2199`
                                        - `Module.state_dict` 
                                          wall **1.378 ms**  self **0.015 ms**  `module.py:2199`
                                          - `Module.state_dict` 
                                            wall **1.149 ms**  self **0.010 ms**  `module.py:2199`
                                            - `Module._save_to_state_dict` 
                                              wall **1.140 ms**  self **1.140 ms**  `module.py:2148`
                    - `get_free_memory` 
                      wall **6.212 ms**  self **0.039 ms**  `model_management.py:1748`
                      - `mem_get_info` 
                        wall **5.785 ms**  self **5.777 ms**  `memory.py:847`
            - `CLIP.tokenize` 
              wall **897.558 ms**  self **0.012 ms**  `sd.py:322`
              - `ZImageTokenizer.tokenize_with_weights` 
                wall **897.546 ms**  self **0.013 ms**  `z_image.py:17`
                - `SD1Tokenizer.tokenize_with_weights` 
                  wall **897.533 ms**  self **0.031 ms**  `sd1_clip.py:698`
                  - `SDTokenizer.tokenize_with_weights` 
                    wall **897.503 ms**  self **0.057 ms**  `sd1_clip.py:572`
                    - `PreTrainedTokenizerBase.__call__` 
                      wall **897.002 ms**  self **0.021 ms**  `tokenization_utils_base.py:2827`
                      - `PreTrainedTokenizerBase._call_one` 
                        wall **896.981 ms**  self **0.010 ms**  `tokenization_utils_base.py:2925`
                        - `PreTrainedTokenizerBase.encode_plus` 
                          wall **896.970 ms**  self **0.011 ms**  `tokenization_utils_base.py:3043`
                          - `PreTrainedTokenizer._encode_plus` 
                            wall **896.953 ms**  self **0.015 ms**  `tokenization_utils.py:743`
                            - `PreTrainedTokenizerBase.prepare_for_model` 
                              wall **879.986 ms**  self **0.032 ms**  `tokenization_utils_base.py:3475`
                              - `PreTrainedTokenizerBase.create_token_type_ids_from_sequences` 
                                wall **879.826 ms**  self **0.032 ms**  `tokenization_utils_base.py:3431`
                                - `SpecialTokensMixin.__getattr__` 
                                  wall **879.780 ms**  self **0.009 ms**  `tokenization_utils_base.py:1077`
                                  - `SpecialTokensMixin.__getattr__` 
                                    wall **879.770 ms**  self **879.765 ms**  `tokenization_utils_base.py:1077`
                            - `PreTrainedTokenizer._encode_plus.<locals>.get_input_ids` 
                              wall **16.946 ms**  self **0.006 ms**  `tokenization_utils.py:765`
                              - `PreTrainedTokenizer.tokenize` 
                                wall **15.432 ms**  self **0.049 ms**  `tokenization_utils.py:621`
                                - `Qwen2Tokenizer._tokenize` 
                                  wall **14.191 ms**  self **1.429 ms**  `tokenization_qwen2.py:262`
                                  - `findall` 
                                    wall **1.052 ms**  self **1.024 ms**  `_main.py:341`
                              - `PreTrainedTokenizer.convert_tokens_to_ids` 
                                wall **1.508 ms**  self **0.183 ms**  `tokenization_utils.py:710`
      - `GoldenSerialRunner._ensure` 
        wall **1.488 ms**  self **0.013 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **1.197 ms**  self **0.027 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._execute_one` 
            wall **1.170 ms**  self **0.098 ms**  `golden_serial.py:8902`
    - `_clip_scope_snapshot` 
      wall **12.687 ms**  self **6.402 ms**  `golden_serial.py:10774`
      - `Module.named_buffers` 
        wall **2.243 ms**  self **0.002 ms**  `module.py:2754`
        - `Module._named_members` 
          wall **2.241 ms**  self **0.446 ms**  `module.py:2650`
  - `SourceThreadProcess.wait_ready` 
    wall **427.417 ms**  self **0.040 ms**  `golden_source_threads.py:1121`
    - `SourceThreadProcess._read_message` 
      wall **250.107 ms**  self **250.107 ms**  `golden_source_threads.py:892`
    - `SourceThreadProcess._read_message` 
      wall **176.420 ms**  self **176.390 ms**  `golden_source_threads.py:892`
  - `SourceThreadProcess.wait_ready` 
    wall **381.920 ms**  self **0.054 ms**  `golden_source_threads.py:1121`
    - `SourceThreadProcess._read_message` 
      wall **261.314 ms**  self **261.314 ms**  `golden_source_threads.py:892`
    - `SourceThreadProcess._read_message` 
      wall **85.660 ms**  self **85.618 ms**  `golden_source_threads.py:892`
    - `SourceThreadProcess._recover_ready_from_table` 
      wall **20.514 ms**  self **0.060 ms**  `golden_source_threads.py:1092`
      - `_FileLock.__enter__` 
        wall **14.994 ms**  self **14.994 ms**  `golden_source_threads.py:486`
      - `_FileLock.__exit__` 
        wall **5.423 ms**  self **5.423 ms**  `golden_source_threads.py:493`
    - `SourceThreadProcess._poll_child` 
      wall **13.903 ms**  self **0.010 ms**  `golden_source_threads.py:1001`
      - `Popen.poll` 
        wall **13.892 ms**  self **0.004 ms**  `subprocess.py:1233`
        - `Popen._internal_poll` 
          wall **13.888 ms**  self **13.888 ms**  `subprocess.py:1966`
  - `SourceThreadProcess.wait_ready` 
    wall **305.931 ms**  self **0.041 ms**  `golden_source_threads.py:1121`
    - `SourceThreadProcess._read_message` 
      wall **250.141 ms**  self **250.141 ms**  `golden_source_threads.py:892`
    - `SourceThreadProcess._read_message` 
      wall **55.074 ms**  self **55.023 ms**  `golden_source_threads.py:892`
  - `BaseEventLoop._run_once` 
    wall **153.701 ms**  self **0.040 ms**  `base_events.py:1845`
    - `Handle._run` 
      wall **151.316 ms**  self **2.428 ms**  `events.py:78`
      - `golden.unet.skeleton_patcher_construction` 
        wall **96.033 ms**  self **96.033 ms**  `full_execution_trace.py:330`
      - `golden.unet.header_config_preflight` 
        wall **52.856 ms**  self **52.856 ms**  `full_execution_trace.py:330`
    - `Handle._run` 
      wall **2.074 ms**  self **2.074 ms**  `events.py:78`
  - `_overlap_owner_call` 
    wall **151.294 ms**  self **0.003 ms**  `golden_serial.py:15543`
    - `_unet_load_with_worker_stage` 
      wall **151.291 ms**  self **0.001 ms**  `golden_parallel.py:517`
      - `golden_unet_load` 
        wall **151.290 ms**  self **0.292 ms**  `golden_serial.py:13225`
        - `Lumina2.get_model` 
          wall **94.395 ms**  self **0.024 ms**  `supported_models.py:1193`
          - `Lumina2.__init__` 
            wall **94.371 ms**  self **0.024 ms**  `model_base.py:1504`
            - `BaseModel.__init__` 
              wall **94.343 ms**  self **58.754 ms**  `model_base.py:164`
              - `model_sampling` 
                wall **19.089 ms**  self **0.099 ms**  `model_base.py:110`
                - `ModelSamplingDiscreteFlow.__init__` 
                  wall **18.989 ms**  self **0.021 ms**  `model_sampling.py:285`
                  - `ModelSamplingDiscreteFlow.set_parameters` 
                    wall **18.936 ms**  self **17.427 ms**  `model_sampling.py:298`
                    - `ModelSamplingDiscreteFlow.sigma` 
                      wall **1.477 ms**  self **0.432 ms**  `model_sampling.py:318`
                      - `time_snr_shift` 
                        wall **1.045 ms**  self **1.045 ms**  `model_sampling.py:279`
              - `archive_model_dtypes` 
                wall **7.866 ms**  self **1.870 ms**  `model_management.py:1045`
              - `Module.eval` 
                wall **4.935 ms**  self **0.002 ms**  `module.py:2916`
                - `Module.train` 
                  wall **4.933 ms**  self **0.014 ms**  `module.py:2894`
                  - `Module.train` 
                    wall **4.248 ms**  self **0.028 ms**  `module.py:2894`
              - `Module.requires_grad_` 
                wall **3.413 ms**  self **0.258 ms**  `module.py:2934`
        - `model_config_from_unet` 
          wall **25.517 ms**  self **0.127 ms**  `model_detection.py:1283`
          - `detect_unet_config` 
            wall **24.951 ms**  self **18.216 ms**  `model_detection.py:44`
            - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
              wall **3.927 ms**  self **0.261 ms**  `wrappers.py:291`
              - `std` 
                wall **3.663 ms**  self **0.641 ms**  `__init__.py:2620`
                - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
                  wall **1.381 ms**  self **0.070 ms**  `wrappers.py:291`
                  - `elementwise_unary_scalar_wrapper.<locals>._fn` 
                    wall **1.310 ms**  self **0.013 ms**  `wrappers.py:491`
                    - `_disable_dynamo.<locals>.inner` 
                      wall **1.297 ms**  self **0.089 ms**  `_compile.py:42`
            - `count_blocks` 
              wall **2.791 ms**  self **2.791 ms**  `model_detection.py:10`
        - `golden_unet_load.<locals>.<dictcomp>` 
          wall **25.448 ms**  self **25.448 ms**  `golden_serial.py:13284`
        - `ModelPatcherDynamic.__init__` 
          wall **1.517 ms**  self **0.014 ms**  `model_patcher.py:1757`
          - `ModelPatcher.__init__` 
            wall **1.234 ms**  self **0.049 ms**  `model_patcher.py:341`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.081 ms**  self **0.017 ms**  `golden_serial.py:13327`
        - `golden_unet_load.<locals>.checkpoint` 
          wall **1.029 ms**  self **0.019 ms**  `golden_serial.py:13327`
  - `SourceThreadProcess.wait_ready` 
    wall **118.779 ms**  self **0.012 ms**  `golden_source_threads.py:1121`
    - `SourceThreadProcess._read_message` 
      wall **118.605 ms**  self **118.571 ms**  `golden_source_threads.py:892`
  - `SourceThreadProcess.wait_ready` 
    wall **100.153 ms**  self **0.015 ms**  `golden_source_threads.py:1121`
    - `SourceThreadProcess._read_message` 
      wall **99.716 ms**  self **99.683 ms**  `golden_source_threads.py:892`
  _... 84 more children >= 1 ms omitted_

## `golden_unet_load`

- Stage wall: **5,501.703 ms**

- `golden_unet_load` 
  wall **5,501.703 ms**  self **963.513 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **4,535.905 ms**  self **0.011 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **4,535.670 ms**  self **0.022 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **4,535.648 ms**  self **0.009 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **4,535.639 ms**  self **0.029 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **4,535.610 ms**  self **0.633 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **4,458.703 ms**  self **5.383 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **49.455 ms**  self **0.018 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **48.957 ms**  self **48.917 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **32.389 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **31.933 ms**  self **31.895 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **29.549 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **28.987 ms**  self **28.943 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **27.677 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **27.255 ms**  self **27.221 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **23.147 ms**  self **0.017 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **22.640 ms**  self **22.605 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **21.746 ms**  self **0.019 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **21.275 ms**  self **21.244 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **21.227 ms**  self **0.010 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **20.857 ms**  self **20.834 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.wait_ready` 
                wall **20.335 ms**  self **0.023 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **19.767 ms**  self **19.739 ms**  `golden_source_threads.py:892`
              _... 87 more children >= 1 ms omitted_
            - `GoldenModelTransport._views` 
              wall **22.907 ms**  self **22.907 ms**  `golden_model_transport.py:1910`
            - `SourceThreadProcess.snapshot` 
              wall **13.557 ms**  self **2.224 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **10.120 ms**  self **0.928 ms**  `golden_source_threads.py:589`
            - `SourceThreadProcess.snapshot` 
              wall **11.388 ms**  self **0.860 ms**  `golden_source_threads.py:1232`
              - `_time_weighted_concurrency` 
                wall **9.296 ms**  self **0.891 ms**  `golden_source_threads.py:589`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **6.742 ms**  self **0.144 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **3.471 ms**  self **0.012 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **3.448 ms**  self **0.007 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **3.438 ms**  self **0.005 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **3.431 ms**  self **3.428 ms**  `threading.py:288`
              - `GoldenQDTransport._record_ranges` 
                wall **1.715 ms**  self **1.444 ms**  `golden_qd_transport.py:3261`
              - `_Telemetry.snapshot` 
                wall **1.140 ms**  self **0.004 ms**  `golden_qd_transport.py:1690`
                - `_Telemetry._snapshot_locked` 
                  wall **1.136 ms**  self **0.098 ms**  `golden_qd_transport.py:1698`
                  - `_json_safe` 
                    wall **1.002 ms**  self **0.006 ms**  `golden_qd_transport.py:2016`
  - `golden.unet.source_h2d_transport` 
    wall **4,384.497 ms**  self **0.083 ms**  `full_execution_trace.py:330`
  - `BaseEventLoop.run_until_complete` 
    wall **4,325.323 ms**  self **0.015 ms**  `base_events.py:617`
    - `BaseEventLoop.run_forever` 
      wall **4,325.300 ms**  self **0.059 ms**  `base_events.py:593`
      - `BaseEventLoop._run_once` 
        wall **4,325.057 ms**  self **0.022 ms**  `base_events.py:1845`
        - `Handle._run` 
          wall **4,324.863 ms**  self **0.089 ms**  `events.py:78`
          - `golden_clip_forward` 
            wall **4,324.751 ms**  self **4,324.751 ms**  `full_execution_trace.py:330`
            - `golden_clip_forward` 
              wall **4,324.656 ms**  self **0.193 ms**  `golden_serial.py:12420`
              - `GoldenSerialRunner.run_closure` 
                wall **4,310.536 ms**  self **0.055 ms**  `golden_serial.py:9143`
                - `GoldenSerialRunner._execute_one` 
                  wall **4,308.817 ms**  self **0.043 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **4,308.558 ms**  self **0.026 ms**  `golden_serial.py:9035`
                    - `CLIPTextEncode.encode` 
                      wall **4,308.380 ms**  self **0.022 ms**  `nodes.py:73`
                      - `CLIP.encode_from_tokens_scheduled` 
                        wall **3,410.801 ms**  self **0.021 ms**  `sd.py:335`
                        - `CLIP.encode_from_tokens` 
                          wall **3,410.780 ms**  self **0.057 ms**  `sd.py:396`
                          - `SD1ClipModel.encode_token_weights` 
                            wall **3,174.053 ms**  self **0.040 ms**  `sd1_clip.py:741`
                            - `ClipTokenWeightEncoder.encode_token_weights` 
                              wall **3,174.012 ms**  self **4.117 ms**  `sd1_clip.py:28`
                              - `SDClipModel.encode` 
                                wall **3,169.843 ms**  self **0.004 ms**  `sd1_clip.py:305`
                                - `Module._wrapped_call_impl` 
                                  wall **3,169.838 ms**  self **0.018 ms**  `module.py:1779`
                                  - `Module._call_impl` 
                                    wall **3,169.820 ms**  self **0.037 ms**  `module.py:1787`
                                    - `SDClipModel.forward` 
                                      wall **3,169.783 ms**  self **0.075 ms**  `sd1_clip.py:260`
                                      - `Module._wrapped_call_impl` 
                                        wall **3,080.120 ms**  self **0.010 ms**  `module.py:1779`
                                        - `Module._call_impl` 
                                          wall **3,080.110 ms**  self **0.024 ms**  `module.py:1787`
                                          - `BaseLlama.forward` 
                                            wall **3,080.086 ms**  self **0.008 ms**  `llama.py:998`
                                            - `Module._wrapped_call_impl` 
                                              wall **3,080.076 ms**  self **0.006 ms**  `module.py:1779`
                                              - `Module._call_impl` 
                                                wall **3,080.070 ms**  self **0.107 ms**  `module.py:1787`
                                                - `Llama2_.forward` 
                                                  wall **3,079.963 ms**  self **333.808 ms**  `llama.py:824`
                                                  - `Llama2_.compute_freqs_cis` 
                                                    wall **1,958.262 ms**  self **0.201 ms**  `llama.py:815`
                                                    - `precompute_freqs_cis` 
                                                      wall **1,958.062 ms**  self **158.885 ms**  `llama.py:445`
                                                      - `_register_overrides_from_graph.<locals>.eager_router` 
                                                        wall **1,555.023 ms**  self **0.021 ms**  `registry.py:938`
                                                        - `_register_overrides_from_graph.<locals>._dispatch` 
                                                          wall **1,554.997 ms**  self **0.087 ms**  `registry.py:926`
                                                          - `OpOverloadPacket.__call__` 
                                                            wall **1,554.149 ms**  self **0.088 ms**  `_ops.py:1338`
                                                            - `_bmm_outer_product_impl` 
                                                              wall **1,554.060 ms**  self **42.954 ms**  `triton_impl.py:18`
                                                              - `bmm_outer_product` 
                                                                wall **1,511.058 ms**  self **0.369 ms**  `triton_kernels.py:77`
                                                                - `_make_wrapper.<locals>.wrapper` 
                                                                  wall **1,510.578 ms**  self **0.016 ms**  `instrumentation.py:202`
                                                                  - `KernelInterface.__getitem__.<locals>.<lambda>` 
                                                                    wall **1,510.503 ms**  self **0.026 ms**  `jit.py:374`
                                                                    - `JITFunction.run` 
                                                                      wall **1,510.477 ms**  self **0.108 ms**  `jit.py:726`
                                                                      - `DriverConfig.active` 
                                                                        wall **959.932 ms**  self **0.009 ms**  `driver.py:36`
                                                                        - `DriverConfig.default` 
                                                                          wall **959.924 ms**  self **0.011 ms**  `driver.py:30`
                                                                          - `_create_driver` 
                                                                            wall **959.913 ms**  self **0.028 ms**  `driver.py:8`
                                                                            - `CudaDriver.__init__` 
                                                                              wall **959.839 ms**  self **0.040 ms**  `driver.py:341`
                                                                              - `CudaUtils.__init__` 
                                                                                wall **959.771 ms**  self **0.038 ms**  `driver.py:100`
                                                                                - `compile_module_from_file` 
                                                                                  wall **930.083 ms**  self **0.023 ms**  `build.py:193`
                                                                                  - `_compile_so_from_file` 
                                                                                    wall **930.059 ms**  self **2.167 ms**  `build.py:157`
                                                                                    - `_compile_so` 
                                                                                      wall **927.780 ms**  self **0.394 ms**  `build.py:132`
                                                                                      - `_build` 
                                                                                        wall **917.801 ms**  self **0.062 ms**  `build.py:60`
                                                                                        - `check_call` 
                                                                                          wall **913.361 ms**  self **0.013 ms**  `subprocess.py:398`
                                                                                          - `call` 
                                                                                            wall **913.344 ms**  self **0.013 ms**  `subprocess.py:381`
                                                                                            - `Popen.wait` 
                                                                                              wall **904.038 ms**  self **0.003 ms**  `subprocess.py:1259`
                                                                                              - `Popen._wait` 
                                                                                                wall **904.035 ms**  self **0.018 ms**  `subprocess.py:2014`
                                                                                                - `Popen._try_wait` 
                                                                                                  wall **904.013 ms**  self **904.013 ms**  `subprocess.py:2001`
                                                                                            - `Popen.__init__` 
                                                                                              wall **9.283 ms**  self **0.016 ms**  `subprocess.py:807`
                                                                                              - `Popen._execute_child` 
                                                                                                wall **9.170 ms**  self **9.081 ms**  `subprocess.py:1789`
                                                                                        - `_find_compiler` 
                                                                                          wall **3.435 ms**  self **0.036 ms**  `build.py:21`
                                                                                          - `which` 
                                                                                            wall **2.555 ms**  self **0.091 ms**  `shutil.py:1452`
                                                                                            - `_access_check` 
                                                                                              wall **2.123 ms**  self **2.123 ms**  `shutil.py:1447`
                                                                                      - `_get_cache_manager` 
                                                                                        wall **7.401 ms**  self **0.180 ms**  `build.py:117`
                                                                                        - `platform_key` 
                                                                                          wall **6.686 ms**  self **0.026 ms**  `build.py:94`
                                                                                          - `architecture` 
                                                                                            wall **6.648 ms**  self **0.044 ms**  `platform.py:646`
                                                                                            - `_syscmd_file` 
                                                                                              wall **6.605 ms**  self **0.839 ms**  `platform.py:602`
                                                                                              - `check_output` 
                                                                                                wall **5.576 ms**  self **0.009 ms**  `subprocess.py:417`
                                                                                                - `run` 
                                                                                                  wall **5.567 ms**  self **0.007 ms**  `subprocess.py:506`
                                                                                                  - `Popen.__init__` 
                                                                                                    wall **5.560 ms**  self **0.170 ms**  `subprocess.py:807`
                                                                                                    - `Popen._execute_child` 
                                                                                                      wall **5.200 ms**  self **5.100 ms**  `subprocess.py:1789`
                                                                                      - `_load_module_from_path` 
                                                                                        wall **1.094 ms**  self **1.094 ms**  `build.py:108`
                                                                                - `library_dirs` 
                                                                                  wall **29.650 ms**  self **0.017 ms**  `driver.py:49`
                                                                                  - `libcuda_dirs` 
                                                                                    wall **29.633 ms**  self **0.184 ms**  `driver.py:25`
                                                                                    - `check_output` 
                                                                                      wall **29.241 ms**  self **0.017 ms**  `subprocess.py:417`
                                                                                      - `run` 
                                                                                        wall **29.221 ms**  self **0.065 ms**  `subprocess.py:506`
                                                                                        - `Popen.communicate` 
                                                                                          wall **22.872 ms**  self **22.797 ms**  `subprocess.py:1165`
                                                                                        - `Popen.__init__` 
                                                                                          wall **6.277 ms**  self **0.404 ms**  `subprocess.py:807`
                                                                                          - `Popen._execute_child` 
                                                                                            wall **5.783 ms**  self **5.659 ms**  `subprocess.py:1789`
                                                                      - `JITFunction._do_compile` 
                                                                        wall **324.549 ms**  self **0.049 ms**  `jit.py:877`
                                                                        - `compile` 
                                                                          wall **324.483 ms**  self **28.201 ms**  `compiler.py:226`
                                                                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                            wall **63.403 ms**  self **0.086 ms**  `compiler.py:605`
                                                                            - `CUDABackend.make_llir` 
                                                                              wall **63.317 ms**  self **63.182 ms**  `compiler.py:367`
                                                                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                            wall **58.424 ms**  self **0.011 ms**  `compiler.py:606`
                                                                            - `CUDABackend.make_ptx` 
                                                                              wall **58.412 ms**  self **57.097 ms**  `compiler.py:480`
                                                                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                            wall **50.943 ms**  self **0.035 ms**  `compiler.py:607`
                                                                            - `CUDABackend.make_cubin` 
                                                                              wall **50.906 ms**  self **0.556 ms**  `compiler.py:513`
                                                                              - `run` 
                                                                                wall **49.637 ms**  self **0.025 ms**  `subprocess.py:506`
                                                                                - `Popen.communicate` 
                                                                                  wall **46.017 ms**  self **0.005 ms**  `subprocess.py:1165`
                                                                                  - `Popen.wait` 
                                                                                    wall **46.012 ms**  self **0.003 ms**  `subprocess.py:1259`
                                                                                    - `Popen._wait` 
                                                                                      wall **46.009 ms**  self **0.020 ms**  `subprocess.py:2014`
                                                                                      - `Popen._try_wait` 
                                                                                        wall **45.986 ms**  self **45.986 ms**  `subprocess.py:2001`
                                                                                - `Popen.__init__` 
                                                                                  wall **3.581 ms**  self **0.015 ms**  `subprocess.py:807`
                                                                                  - `Popen._execute_child` 
                                                                                    wall **3.530 ms**  self **0.024 ms**  `subprocess.py:1789`
                                                                                    - `Popen._posix_spawn` 
                                                                                      wall **3.506 ms**  self **3.486 ms**  `subprocess.py:1750`
                                                                          - `get_cache_key` 
                                                                            wall **40.451 ms**  self **0.026 ms**  `cache.py:319`
                                                                            - `CUDABackend.hash` 
                                                                              wall **36.469 ms**  self **0.012 ms**  `compiler.py:611`
                                                                              - `get_ptxas_version` 
                                                                                wall **36.456 ms**  self **0.014 ms**  `compiler.py:42`
                                                                                - `get_ptxas` 
                                                                                  wall **28.168 ms**  self **0.005 ms**  `compiler.py:38`
                                                                                  - `env_base.__get__` 
                                                                                    wall **28.163 ms**  self **0.003 ms**  `knobs.py:76`
                                                                                    - `env_nvidia_tool.get` 
                                                                                      wall **28.160 ms**  self **0.004 ms**  `knobs.py:203`
                                                                                      - `env_nvidia_tool.transform` 
                                                                                        wall **28.156 ms**  self **0.010 ms**  `knobs.py:206`
                                                                                        - `NvidiaTool.from_path` 
                                                                                          wall **28.147 ms**  self **0.021 ms**  `knobs.py:181`
                                                                                          - `check_output` 
                                                                                            wall **27.674 ms**  self **0.018 ms**  `subprocess.py:417`
                                                                                            - `run` 
                                                                                              wall **27.652 ms**  self **0.037 ms**  `subprocess.py:506`
                                                                                              - `Popen.communicate` 
                                                                                                wall **15.618 ms**  self **15.504 ms**  `subprocess.py:1165`
                                                                                              - `Popen.__init__` 
                                                                                                wall **11.983 ms**  self **0.061 ms**  `subprocess.py:807`
                                                                                                - `Popen._execute_child` 
                                                                                                  wall **11.760 ms**  self **11.634 ms**  `subprocess.py:1789`
                                                                                - `check_output` 
                                                                                  wall **8.268 ms**  self **0.012 ms**  `subprocess.py:417`
                                                                                  - `run` 
                                                                                    wall **8.254 ms**  self **0.017 ms**  `subprocess.py:506`
                                                                                    - `Popen.communicate` 
                                                                                      wall **4.990 ms**  self **4.940 ms**  `subprocess.py:1165`
                                                                                    - `Popen.__init__` 
                                                                                      wall **3.240 ms**  self **0.146 ms**  `subprocess.py:807`
                                                                                      - `Popen._execute_child` 
                                                                                        wall **2.816 ms**  self **2.771 ms**  `subprocess.py:1789`
                                                                            - `CUDAOptions.hash` 
                                                                              wall **2.059 ms**  self **0.049 ms**  `compiler.py:153`
                                                                              - `CUDAOptions.hash.<locals>.<genexpr>` 
                                                                                wall **1.976 ms**  self **0.012 ms**  `compiler.py:155`
                                                                                - `file_hash` 
                                                                                  wall **1.964 ms**  self **1.964 ms**  `compiler.py:97`
                                                                            - `ASTSource.hash` 
                                                                              wall **1.897 ms**  self **0.042 ms**  `compiler.py:71`
                                                                              - `JITCallable.cache_key` 
                                                                                wall **1.842 ms**  self **0.070 ms**  `jit.py:515`
                                                                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                            wall **30.680 ms**  self **0.121 ms**  `compiler.py:602`
                                                                            - `CUDABackend.make_ttgir` 
                                                                              wall **30.559 ms**  self **30.559 ms**  `compiler.py:260`
                                                                          - `ASTSource.make_ir` 
                                                                            wall **21.979 ms**  self **0.035 ms**  `compiler.py:78`
                                                                            - `ast_to_ttir` 
                                                                              wall **21.944 ms**  self **0.763 ms**  `code_generator.py:1662`
                                                                              - `CodeGenerator.visit` 
                                                                                wall **19.237 ms**  self **0.026 ms**  `code_generator.py:1581`
                                                                                - `NodeVisitor.visit` 
                                                                                  wall **19.211 ms**  self **0.006 ms**  `ast.py:414`
                                                                                  - `CodeGenerator.visit_Module` 
                                                                                    wall **19.206 ms**  self **0.003 ms**  `code_generator.py:519`
                                                                                    - `NodeVisitor.generic_visit` 
                                                                                      wall **19.203 ms**  self **0.009 ms**  `ast.py:420`
                                                                                      - `CodeGenerator.visit` 
                                                                                        wall **19.191 ms**  self **0.017 ms**  `code_generator.py:1581`
                                                                                        - `NodeVisitor.visit` 
                                                                                          wall **19.173 ms**  self **0.011 ms**  `ast.py:414`
                                                                                          - `CodeGenerator.visit_FunctionDef` 
                                                                                            wall **19.162 ms**  self **0.148 ms**  `code_generator.py:628`
                                                                                            - `CodeGenerator.visit_compound_statement` 
                                                                                              wall **17.463 ms**  self **0.033 ms**  `code_generator.py:508`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **3.763 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **3.756 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **3.754 ms**  self **0.011 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **3.710 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **3.695 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Call` 
                                                                                                          wall **3.693 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                                                                          - `CodeGenerator.call_Function` 
                                                                                                            wall **3.318 ms**  self **0.014 ms**  `code_generator.py:1398`
                                                                                                            - `CodeGenerator.call_JitFunction` 
                                                                                                              wall **3.303 ms**  self **0.083 ms**  `code_generator.py:1358`
                                                                                                              - `CodeGenerator.visit` 
                                                                                                                wall **2.958 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                                                                - `NodeVisitor.visit` 
                                                                                                                  wall **2.953 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                                  - `CodeGenerator.visit_Module` 
                                                                                                                    wall **2.951 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                                                                    - `NodeVisitor.generic_visit` 
                                                                                                                      wall **2.949 ms**  self **0.012 ms**  `ast.py:420`
                                                                                                                      - `CodeGenerator.visit` 
                                                                                                                        wall **2.935 ms**  self **2.935 ms**  `code_generator.py:1581`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **3.035 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **3.028 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **3.026 ms**  self **0.011 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **2.985 ms**  self **0.014 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **2.970 ms**  self **0.003 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Call` 
                                                                                                          wall **2.968 ms**  self **0.013 ms**  `code_generator.py:1455`
                                                                                                          - `CodeGenerator.call_Function` 
                                                                                                            wall **2.877 ms**  self **0.005 ms**  `code_generator.py:1398`
                                                                                                            - `CodeGenerator.call_JitFunction` 
                                                                                                              wall **2.871 ms**  self **0.056 ms**  `code_generator.py:1358`
                                                                                                              - `CodeGenerator.visit` 
                                                                                                                wall **2.607 ms**  self **0.004 ms**  `code_generator.py:1581`
                                                                                                                - `NodeVisitor.visit` 
                                                                                                                  wall **2.603 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                                  - `CodeGenerator.visit_Module` 
                                                                                                                    wall **2.601 ms**  self **0.002 ms**  `code_generator.py:519`
                                                                                                                    - `NodeVisitor.generic_visit` 
                                                                                                                      wall **2.599 ms**  self **0.009 ms**  `ast.py:420`
                                                                                                                      - `CodeGenerator.visit` 
                                                                                                                        wall **2.588 ms**  self **2.588 ms**  `code_generator.py:1581`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **2.033 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **2.027 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Expr` 
                                                                                                    wall **2.025 ms**  self **0.004 ms**  `code_generator.py:1556`
                                                                                                    - `NodeVisitor.generic_visit` 
                                                                                                      wall **2.021 ms**  self **0.006 ms**  `ast.py:420`
                                                                                                      - `CodeGenerator.visit` 
                                                                                                        wall **2.014 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                                        - `NodeVisitor.visit` 
                                                                                                          wall **2.008 ms**  self **0.003 ms**  `ast.py:414`
                                                                                                          - `CodeGenerator.visit_Call` 
                                                                                                            wall **2.005 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                                                                            - `CodeGenerator.visit` 
                                                                                                              wall **1.687 ms**  self **0.005 ms**  `code_generator.py:1581`
                                                                                                              - `NodeVisitor.visit` 
                                                                                                                wall **1.682 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                                - `CodeGenerator.visit_BinOp` 
                                                                                                                  wall **1.679 ms**  self **0.004 ms**  `code_generator.py:810`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **1.820 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **1.813 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **1.810 ms**  self **0.009 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **1.767 ms**  self **0.014 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **1.753 ms**  self **0.003 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Call` 
                                                                                                          wall **1.750 ms**  self **0.010 ms**  `code_generator.py:1455`
                                                                                                          - `CodeGenerator.visit` 
                                                                                                            wall **1.463 ms**  self **0.069 ms**  `code_generator.py:1581`
                                                                                                            - `NodeVisitor.visit` 
                                                                                                              wall **1.394 ms**  self **0.004 ms**  `ast.py:414`
                                                                                                              - `CodeGenerator.visit_BinOp` 
                                                                                                                wall **1.390 ms**  self **0.007 ms**  `code_generator.py:810`
                                                                                                                - `CodeGenerator.visit` 
                                                                                                                  wall **1.004 ms**  self **0.012 ms**  `code_generator.py:1581`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **1.426 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **1.421 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **1.419 ms**  self **0.007 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **1.388 ms**  self **0.011 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **1.376 ms**  self **0.003 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_Call` 
                                                                                                          wall **1.374 ms**  self **0.008 ms**  `code_generator.py:1455`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **1.314 ms**  self **0.006 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **1.308 ms**  self **0.001 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **1.306 ms**  self **0.009 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **1.263 ms**  self **0.015 ms**  `code_generator.py:1581`
                                                                                                      - `NodeVisitor.visit` 
                                                                                                        wall **1.248 ms**  self **0.005 ms**  `ast.py:414`
                                                                                                        - `CodeGenerator.visit_BinOp` 
                                                                                                          wall **1.242 ms**  self **0.004 ms**  `code_generator.py:810`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **1.089 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                                                - `NodeVisitor.visit` 
                                                                                                  wall **1.082 ms**  self **0.002 ms**  `ast.py:414`
                                                                                                  - `CodeGenerator.visit_Assign` 
                                                                                                    wall **1.080 ms**  self **0.010 ms**  `code_generator.py:727`
                                                                                                    - `CodeGenerator.visit` 
                                                                                                      wall **1.042 ms**  self **0.094 ms**  `code_generator.py:1581`
                                                                                              - `CodeGenerator.visit` 
                                                                                                wall **1.001 ms**  self **0.007 ms**  `code_generator.py:1581`
                                                                          - `FileCacheManager.put` 
                                                                            wall **10.807 ms**  self **10.585 ms**  `cache.py:103`
                                                                          - `CUDABackend.add_stages.<locals>.<lambda>` 
                                                                            wall **6.338 ms**  self **0.045 ms**  `compiler.py:601`
                                                                            - `CUDABackend.make_ttir` 
                                                                              wall **6.293 ms**  self **6.293 ms**  `compiler.py:244`
                                                                          _... 5 more children >= 1 ms omitted_
                                                                      - `dynamic_func` 
                                                                        wall **215.201 ms**  self **215.165 ms**  `<string>:2`
                                                                      - `CompiledKernel.launch_metadata` 
                                                                        wall **8.603 ms**  self **0.021 ms**  `compiler.py:493`
                                                                        - `CompiledKernel._init_handles` 
                                                                          wall **8.581 ms**  self **1.422 ms**  `compiler.py:448`
                                                                          - `max_shared_mem` 
                                                                            wall **6.798 ms**  self **6.798 ms**  `compiler.py:133`
                                                      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                                        wall **144.471 ms**  self **0.021 ms**  `_tensor.py:32`
                                                        - `Tensor.__rpow__` 
                                                          wall **144.450 ms**  self **144.450 ms**  `_tensor.py:1155`
                                                      - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                                        wall **99.683 ms**  self **0.016 ms**  `_tensor.py:32`
                                                        - `Tensor.__rdiv__` 
                                                          wall **99.666 ms**  self **99.666 ms**  `_tensor.py:1120`
                                                  - `prefetch_queue_pop` 
                                                    wall **563.827 ms**  self **0.005 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **563.823 ms**  self **0.010 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **563.813 ms**  self **0.008 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **563.805 ms**  self **0.026 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **563.779 ms**  self **0.303 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **488.625 ms**  self **0.007 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **488.618 ms**  self **0.249 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **488.369 ms**  self **100.437 ms**  `llama.py:540`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **323.148 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **323.142 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `disable_weight_init.Linear.forward` 
                                                                        wall **323.131 ms**  self **0.030 ms**  `ops.py:570`
                                                                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                          wall **323.082 ms**  self **322.121 ms**  `ops.py:566`
                                                                  - `apply_rope` 
                                                                    wall **61.023 ms**  self **61.023 ms**  `llama.py:492`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **1.467 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **1.463 ms**  self **0.015 ms**  `module.py:1787`
                                                                      - `disable_weight_init.Linear.forward` 
                                                                        wall **1.447 ms**  self **0.011 ms**  `ops.py:570`
                                                                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                          wall **1.418 ms**  self **0.277 ms**  `ops.py:566`
                                                                          - `CastBiasWeightContext.__init__` 
                                                                            wall **1.133 ms**  self **0.007 ms**  `ops.py:464`
                                                                            - `cast_bias_weight` 
                                                                              wall **1.126 ms**  self **1.097 ms**  `ops.py:337`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **1.135 ms**  self **0.004 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **1.130 ms**  self **0.020 ms**  `module.py:1787`
                                                                      - `disable_weight_init.Linear.forward` 
                                                                        wall **1.110 ms**  self **0.035 ms**  `ops.py:570`
                                                                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                          wall **1.049 ms**  self **0.820 ms**  `ops.py:566`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **44.711 ms**  self **0.005 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **44.706 ms**  self **0.008 ms**  `module.py:1787`
                                                                - `RMSNorm.forward` 
                                                                  wall **44.698 ms**  self **0.011 ms**  `llama.py:436`
                                                                  - `rms_norm` 
                                                                    wall **44.685 ms**  self **0.028 ms**  `rmsnorm.py:7`
                                                                    - `rms_norm` 
                                                                      wall **44.572 ms**  self **44.572 ms**  `functional.py:2998`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **29.964 ms**  self **0.004 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **29.960 ms**  self **0.021 ms**  `module.py:1787`
                                                                - `MLP.forward` 
                                                                  wall **29.939 ms**  self **0.227 ms**  `llama.py:644`
                                                                  - `silu` 
                                                                    wall **26.781 ms**  self **26.781 ms**  `functional.py:2429`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **2.156 ms**  self **0.003 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **2.153 ms**  self **0.005 ms**  `module.py:1787`
                                                                      - `disable_weight_init.Linear.forward` 
                                                                        wall **2.148 ms**  self **0.039 ms**  `ops.py:570`
                                                                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                          wall **2.099 ms**  self **0.202 ms**  `ops.py:566`
                                                                          - `CastBiasWeightContext.__init__` 
                                                                            wall **1.888 ms**  self **0.006 ms**  `ops.py:464`
                                                                            - `cast_bias_weight` 
                                                                              wall **1.883 ms**  self **1.865 ms**  `ops.py:337`
                                                  - `_handle_torch_function_and_wrap_type_error_to_not_implemented.<locals>.wrapped` 
                                                    wall **81.602 ms**  self **0.012 ms**  `_tensor.py:32`
                                                    - `Tensor.__rsub__` 
                                                      wall **81.590 ms**  self **81.590 ms**  `_tensor.py:1116`
                                                  - `prefetch_queue_pop` 
                                                    wall **13.845 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **13.843 ms**  self **0.005 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **13.837 ms**  self **0.004 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **13.833 ms**  self **0.006 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **13.828 ms**  self **0.209 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **11.902 ms**  self **0.006 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **11.895 ms**  self **0.212 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **11.683 ms**  self **10.260 ms**  `llama.py:540`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **1.369 ms**  self **0.003 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **1.366 ms**  self **0.014 ms**  `module.py:1787`
                                                                - `MLP.forward` 
                                                                  wall **1.352 ms**  self **0.154 ms**  `llama.py:644`
                                                  - `prefetch_queue_pop` 
                                                    wall **8.206 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **8.204 ms**  self **0.005 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **8.199 ms**  self **0.004 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **8.195 ms**  self **0.009 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **8.186 ms**  self **0.156 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **6.213 ms**  self **0.004 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **6.209 ms**  self **0.019 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **6.190 ms**  self **1.659 ms**  `llama.py:540`
                                                                  - `apply_rope` 
                                                                    wall **2.365 ms**  self **2.365 ms**  `llama.py:492`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **1.359 ms**  self **0.002 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **1.357 ms**  self **0.005 ms**  `module.py:1787`
                                                                - `MLP.forward` 
                                                                  wall **1.352 ms**  self **0.127 ms**  `llama.py:644`
                                                  - `prefetch_queue_pop` 
                                                    wall **7.381 ms**  self **0.003 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **7.379 ms**  self **0.004 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **7.375 ms**  self **0.003 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **7.371 ms**  self **0.006 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **7.365 ms**  self **0.059 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **5.549 ms**  self **0.003 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **5.546 ms**  self **0.011 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **5.535 ms**  self **0.904 ms**  `llama.py:540`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **1.900 ms**  self **0.002 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **1.898 ms**  self **0.005 ms**  `module.py:1787`
                                                                      - `RMSNorm.forward` 
                                                                        wall **1.892 ms**  self **0.005 ms**  `llama.py:436`
                                                                        - `rms_norm` 
                                                                          wall **1.887 ms**  self **0.009 ms**  `rmsnorm.py:7`
                                                                          - `cast_to` 
                                                                            wall **1.762 ms**  self **1.762 ms**  `model_management.py:1527`
                                                                  - `apply_rope` 
                                                                    wall **1.807 ms**  self **1.807 ms**  `llama.py:492`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **1.527 ms**  self **0.002 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **1.524 ms**  self **0.005 ms**  `module.py:1787`
                                                                - `MLP.forward` 
                                                                  wall **1.520 ms**  self **0.124 ms**  `llama.py:644`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **1.081 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **1.076 ms**  self **0.013 ms**  `module.py:1787`
                                                                      - `disable_weight_init.Linear.forward` 
                                                                        wall **1.064 ms**  self **0.032 ms**  `ops.py:570`
                                                                        - `disable_weight_init.Linear.forward_comfy_cast_weights` 
                                                                          wall **1.021 ms**  self **0.880 ms**  `ops.py:566`
                                                  - `prefetch_queue_pop` 
                                                    wall **6.616 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **6.614 ms**  self **0.004 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **6.610 ms**  self **0.004 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **6.606 ms**  self **0.008 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **6.599 ms**  self **0.055 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **5.708 ms**  self **0.004 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **5.704 ms**  self **0.012 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **5.692 ms**  self **2.988 ms**  `llama.py:540`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **1.107 ms**  self **0.004 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **1.103 ms**  self **0.009 ms**  `module.py:1787`
                                                                      - `RMSNorm.forward` 
                                                                        wall **1.094 ms**  self **0.005 ms**  `llama.py:436`
                                                                        - `rms_norm` 
                                                                          wall **1.088 ms**  self **0.018 ms**  `rmsnorm.py:7`
                                                  - `prefetch_queue_pop` 
                                                    wall **6.452 ms**  self **0.002 ms**  `model_prefetch.py:62`
                                                    - `Llama2_.forward.<locals>.core` 
                                                      wall **6.450 ms**  self **0.006 ms**  `llama.py:912`
                                                      - `Module._wrapped_call_impl` 
                                                        wall **6.444 ms**  self **0.005 ms**  `module.py:1779`
                                                        - `Module._call_impl` 
                                                          wall **6.439 ms**  self **0.085 ms**  `module.py:1787`
                                                          - `TransformerBlock.forward` 
                                                            wall **6.354 ms**  self **0.279 ms**  `llama.py:661`
                                                            - `Module._wrapped_call_impl` 
                                                              wall **4.622 ms**  self **0.004 ms**  `module.py:1779`
                                                              - `Module._call_impl` 
                                                                wall **4.618 ms**  self **0.021 ms**  `module.py:1787`
                                                                - `Attention.forward` 
                                                                  wall **4.597 ms**  self **2.523 ms**  `llama.py:540`
                                                  _... 30 more children >= 1 ms omitted_
                                      - `SDClipModel.process_tokens` 
                                        wall **89.582 ms**  self **1.419 ms**  `sd1_clip.py:172`
                                        - `Module._wrapped_call_impl` 
                                          wall **88.150 ms**  self **0.009 ms**  `module.py:1779`
                                          - `Module._call_impl` 
                                            wall **88.141 ms**  self **0.019 ms**  `module.py:1787`
                                            - `disable_weight_init.Embedding.forward` 
                                              wall **88.121 ms**  self **0.013 ms**  `ops.py:798`
                                              - `disable_weight_init.Embedding.forward_comfy_cast_weights` 
                                                wall **88.078 ms**  self **36.363 ms**  `ops.py:790`
                                                - `embedding` 
                                                  wall **51.365 ms**  self **51.365 ms**  `functional.py:2509`
                          - `CLIP.load_model` 
                            wall **236.515 ms**  self **0.025 ms**  `sd.py:459`
                            - `load_models_gpu` 
                              wall **236.487 ms**  self **0.181 ms**  `model_management.py:909`
                              - `LoadedModel.model_load` 
                                wall **198.323 ms**  self **0.044 ms**  `model_management.py:782`
                                - `LoadedModel.model_use_more_vram` 
                                  wall **198.235 ms**  self **0.007 ms**  `model_management.py:817`
                                  - `ModelPatcherDynamic.partially_load` 
                                    wall **198.227 ms**  self **0.276 ms**  `model_patcher.py:2141`
                                    - `ModelPatcherDynamic.load` 
                                      wall **197.819 ms**  self **9.898 ms**  `model_patcher.py:1853`
                                      - `ModelPatcher._load_list` 
                                        wall **110.661 ms**  self **67.564 ms**  `model_patcher.py:945`
                                        - `module_size` 
                                          wall **3.270 ms**  self **0.006 ms**  `model_management.py:631`
                                          - `Module.state_dict` 
                                            wall **3.264 ms**  self **0.014 ms**  `module.py:2199`
                                            - `Module._save_to_state_dict` 
                                              wall **3.250 ms**  self **3.250 ms**  `module.py:2148`
                                      - `HostBuffer.__del__` 
                                        wall **16.190 ms**  self **16.130 ms**  `host_buffer.py:125`
                                      - `Module.named_buffers` 
                                        wall **6.075 ms**  self **0.006 ms**  `module.py:2754`
                                        - `Module._named_members` 
                                          wall **6.068 ms**  self **3.695 ms**  `module.py:2650`
                                      - `ModelVBAR.prioritize` 
                                        wall **3.459 ms**  self **3.451 ms**  `model_vbar.py:60`
                                      - `ModelPatcherDynamic._vbar_get` 
                                        wall **2.377 ms**  self **0.031 ms**  `model_patcher.py:1797`
                                        - `ModelVBAR.__init__` 
                                          wall **2.345 ms**  self **2.243 ms**  `model_vbar.py:50`
                                      - `HostBuffer.__init__` 
                                        wall **1.336 ms**  self **1.322 ms**  `host_buffer.py:79`
                              - `LoadedModel.model_memory_required` 
                                wall **31.568 ms**  self **0.008 ms**  `model_management.py:776`
                                - `LoadedModel.model_memory` 
                                  wall **31.558 ms**  self **0.009 ms**  `model_management.py:767`
                                  - `ModelPatcher.model_size` 
                                    wall **31.549 ms**  self **6.169 ms**  `model_patcher.py:405`
                                    - `module_size` 
                                      wall **25.380 ms**  self **0.134 ms**  `model_management.py:631`
                                      - `Module.state_dict` 
                                        wall **25.246 ms**  self **0.022 ms**  `module.py:2199`
                                        - `Module.state_dict` 
                                          wall **25.220 ms**  self **0.023 ms**  `module.py:2199`
                                          - `Module.state_dict` 
                                            wall **24.724 ms**  self **0.021 ms**  `module.py:2199`
                                            - `Module.state_dict` 
                                              wall **24.700 ms**  self **0.029 ms**  `module.py:2199`
                                              - `Module.state_dict` 
                                                wall **24.519 ms**  self **0.100 ms**  `module.py:2199`
                                                - `Module.state_dict` 
                                                  wall **4.827 ms**  self **0.024 ms**  `module.py:2199`
                                                  - `Module.state_dict` 
                                                    wall **4.153 ms**  self **0.029 ms**  `module.py:2199`
                                                    - `Module.state_dict` 
                                                      wall **2.876 ms**  self **0.013 ms**  `module.py:2199`
                                                      - `Module._save_to_state_dict` 
                                                        wall **2.863 ms**  self **2.863 ms**  `module.py:2148`
                                                    - `Module.state_dict` 
                                                      wall **1.206 ms**  self **0.010 ms**  `module.py:2199`
                                                      - `Module._save_to_state_dict` 
                                                        wall **1.196 ms**  self **1.196 ms**  `module.py:2148`
                                                - `Module.state_dict` 
                                                  wall **1.857 ms**  self **0.012 ms**  `module.py:2199`
                                                  - `Module.state_dict` 
                                                    wall **1.358 ms**  self **0.022 ms**  `module.py:2199`
                                                - `Module.state_dict` 
                                                  wall **1.663 ms**  self **0.012 ms**  `module.py:2199`
                                                  - `Module.state_dict` 
                                                    wall **1.378 ms**  self **0.015 ms**  `module.py:2199`
                                                    - `Module.state_dict` 
                                                      wall **1.149 ms**  self **0.010 ms**  `module.py:2199`
                                                      - `Module._save_to_state_dict` 
                                                        wall **1.140 ms**  self **1.140 ms**  `module.py:2148`
                              - `get_free_memory` 
                                wall **6.212 ms**  self **0.039 ms**  `model_management.py:1748`
                                - `mem_get_info` 
                                  wall **5.785 ms**  self **5.777 ms**  `memory.py:847`
                      - `CLIP.tokenize` 
                        wall **897.558 ms**  self **0.012 ms**  `sd.py:322`
                        - `ZImageTokenizer.tokenize_with_weights` 
                          wall **897.546 ms**  self **0.013 ms**  `z_image.py:17`
                          - `SD1Tokenizer.tokenize_with_weights` 
                            wall **897.533 ms**  self **0.031 ms**  `sd1_clip.py:698`
                            - `SDTokenizer.tokenize_with_weights` 
                              wall **897.503 ms**  self **0.057 ms**  `sd1_clip.py:572`
                              - `PreTrainedTokenizerBase.__call__` 
                                wall **897.002 ms**  self **0.021 ms**  `tokenization_utils_base.py:2827`
                                - `PreTrainedTokenizerBase._call_one` 
                                  wall **896.981 ms**  self **0.010 ms**  `tokenization_utils_base.py:2925`
                                  - `PreTrainedTokenizerBase.encode_plus` 
                                    wall **896.970 ms**  self **0.011 ms**  `tokenization_utils_base.py:3043`
                                    - `PreTrainedTokenizer._encode_plus` 
                                      wall **896.953 ms**  self **0.015 ms**  `tokenization_utils.py:743`
                                      - `PreTrainedTokenizerBase.prepare_for_model` 
                                        wall **879.986 ms**  self **0.032 ms**  `tokenization_utils_base.py:3475`
                                        - `PreTrainedTokenizerBase.create_token_type_ids_from_sequences` 
                                          wall **879.826 ms**  self **0.032 ms**  `tokenization_utils_base.py:3431`
                                          - `SpecialTokensMixin.__getattr__` 
                                            wall **879.780 ms**  self **0.009 ms**  `tokenization_utils_base.py:1077`
                                            - `SpecialTokensMixin.__getattr__` 
                                              wall **879.770 ms**  self **879.765 ms**  `tokenization_utils_base.py:1077`
                                      - `PreTrainedTokenizer._encode_plus.<locals>.get_input_ids` 
                                        wall **16.946 ms**  self **0.006 ms**  `tokenization_utils.py:765`
                                        - `PreTrainedTokenizer.tokenize` 
                                          wall **15.432 ms**  self **0.049 ms**  `tokenization_utils.py:621`
                                          - `Qwen2Tokenizer._tokenize` 
                                            wall **14.191 ms**  self **1.429 ms**  `tokenization_qwen2.py:262`
                                            - `findall` 
                                              wall **1.052 ms**  self **1.024 ms**  `_main.py:341`
                                        - `PreTrainedTokenizer.convert_tokens_to_ids` 
                                          wall **1.508 ms**  self **0.183 ms**  `tokenization_utils.py:710`
                - `GoldenSerialRunner._ensure` 
                  wall **1.488 ms**  self **0.013 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._ensure` 
                    wall **1.197 ms**  self **0.027 ms**  `golden_serial.py:9122`
                    - `GoldenSerialRunner._execute_one` 
                      wall **1.170 ms**  self **0.098 ms**  `golden_serial.py:8902`
              - `_clip_scope_snapshot` 
                wall **12.687 ms**  self **6.402 ms**  `golden_serial.py:10774`
                - `Module.named_buffers` 
                  wall **2.243 ms**  self **0.002 ms**  `module.py:2754`
                  - `Module._named_members` 
                    wall **2.241 ms**  self **0.446 ms**  `module.py:2650`
            - `SourceThreadProcess.wait_ready` 
              wall **427.417 ms**  self **0.040 ms**  `golden_source_threads.py:1121`
              - `SourceThreadProcess._read_message` 
                wall **250.107 ms**  self **250.107 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess._read_message` 
                wall **176.420 ms**  self **176.390 ms**  `golden_source_threads.py:892`
            - `SourceThreadProcess.wait_ready` 
              wall **381.920 ms**  self **0.054 ms**  `golden_source_threads.py:1121`
              - `SourceThreadProcess._read_message` 
                wall **261.314 ms**  self **261.314 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess._read_message` 
                wall **85.660 ms**  self **85.618 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess._recover_ready_from_table` 
                wall **20.514 ms**  self **0.060 ms**  `golden_source_threads.py:1092`
                - `_FileLock.__enter__` 
                  wall **14.994 ms**  self **14.994 ms**  `golden_source_threads.py:486`
                - `_FileLock.__exit__` 
                  wall **5.423 ms**  self **5.423 ms**  `golden_source_threads.py:493`
              - `SourceThreadProcess._poll_child` 
                wall **13.903 ms**  self **0.010 ms**  `golden_source_threads.py:1001`
                - `Popen.poll` 
                  wall **13.892 ms**  self **0.004 ms**  `subprocess.py:1233`
                  - `Popen._internal_poll` 
                    wall **13.888 ms**  self **13.888 ms**  `subprocess.py:1966`
            - `SourceThreadProcess.wait_ready` 
              wall **305.931 ms**  self **0.041 ms**  `golden_source_threads.py:1121`
              - `SourceThreadProcess._read_message` 
                wall **250.141 ms**  self **250.141 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess._read_message` 
                wall **55.074 ms**  self **55.023 ms**  `golden_source_threads.py:892`
            - `BaseEventLoop._run_once` 
              wall **153.701 ms**  self **0.040 ms**  `base_events.py:1845`
              - `Handle._run` 
                wall **151.316 ms**  self **2.428 ms**  `events.py:78`
                - `golden.unet.skeleton_patcher_construction` 
                  wall **96.033 ms**  self **96.033 ms**  `full_execution_trace.py:330`
                - `golden.unet.header_config_preflight` 
                  wall **52.856 ms**  self **52.856 ms**  `full_execution_trace.py:330`
              - `Handle._run` 
                wall **2.074 ms**  self **2.074 ms**  `events.py:78`
            - `_overlap_owner_call` 
              wall **151.294 ms**  self **0.003 ms**  `golden_serial.py:15543`
              - `_unet_load_with_worker_stage` 
                wall **151.291 ms**  self **0.001 ms**  `golden_parallel.py:517`
                - `golden_unet_load` 
                  wall **151.290 ms**  self **0.292 ms**  `golden_serial.py:13225`
                  - `Lumina2.get_model` 
                    wall **94.395 ms**  self **0.024 ms**  `supported_models.py:1193`
                    - `Lumina2.__init__` 
                      wall **94.371 ms**  self **0.024 ms**  `model_base.py:1504`
                      - `BaseModel.__init__` 
                        wall **94.343 ms**  self **58.754 ms**  `model_base.py:164`
                        - `model_sampling` 
                          wall **19.089 ms**  self **0.099 ms**  `model_base.py:110`
                          - `ModelSamplingDiscreteFlow.__init__` 
                            wall **18.989 ms**  self **0.021 ms**  `model_sampling.py:285`
                            - `ModelSamplingDiscreteFlow.set_parameters` 
                              wall **18.936 ms**  self **17.427 ms**  `model_sampling.py:298`
                              - `ModelSamplingDiscreteFlow.sigma` 
                                wall **1.477 ms**  self **0.432 ms**  `model_sampling.py:318`
                                - `time_snr_shift` 
                                  wall **1.045 ms**  self **1.045 ms**  `model_sampling.py:279`
                        - `archive_model_dtypes` 
                          wall **7.866 ms**  self **1.870 ms**  `model_management.py:1045`
                        - `Module.eval` 
                          wall **4.935 ms**  self **0.002 ms**  `module.py:2916`
                          - `Module.train` 
                            wall **4.933 ms**  self **0.014 ms**  `module.py:2894`
                            - `Module.train` 
                              wall **4.248 ms**  self **0.028 ms**  `module.py:2894`
                        - `Module.requires_grad_` 
                          wall **3.413 ms**  self **0.258 ms**  `module.py:2934`
                  - `model_config_from_unet` 
                    wall **25.517 ms**  self **0.127 ms**  `model_detection.py:1283`
                    - `detect_unet_config` 
                      wall **24.951 ms**  self **18.216 ms**  `model_detection.py:44`
                      - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
                        wall **3.927 ms**  self **0.261 ms**  `wrappers.py:291`
                        - `std` 
                          wall **3.663 ms**  self **0.641 ms**  `__init__.py:2620`
                          - `out_wrapper.<locals>._out_wrapper.<locals>._fn` 
                            wall **1.381 ms**  self **0.070 ms**  `wrappers.py:291`
                            - `elementwise_unary_scalar_wrapper.<locals>._fn` 
                              wall **1.310 ms**  self **0.013 ms**  `wrappers.py:491`
                              - `_disable_dynamo.<locals>.inner` 
                                wall **1.297 ms**  self **0.089 ms**  `_compile.py:42`
                      - `count_blocks` 
                        wall **2.791 ms**  self **2.791 ms**  `model_detection.py:10`
                  - `golden_unet_load.<locals>.<dictcomp>` 
                    wall **25.448 ms**  self **25.448 ms**  `golden_serial.py:13284`
                  - `ModelPatcherDynamic.__init__` 
                    wall **1.517 ms**  self **0.014 ms**  `model_patcher.py:1757`
                    - `ModelPatcher.__init__` 
                      wall **1.234 ms**  self **0.049 ms**  `model_patcher.py:341`
                  - `golden_unet_load.<locals>.checkpoint` 
                    wall **1.081 ms**  self **0.017 ms**  `golden_serial.py:13327`
                  - `golden_unet_load.<locals>.checkpoint` 
                    wall **1.029 ms**  self **0.019 ms**  `golden_serial.py:13327`
            - `SourceThreadProcess.wait_ready` 
              wall **118.779 ms**  self **0.012 ms**  `golden_source_threads.py:1121`
              - `SourceThreadProcess._read_message` 
                wall **118.605 ms**  self **118.571 ms**  `golden_source_threads.py:892`
            - `SourceThreadProcess.wait_ready` 
              wall **100.153 ms**  self **0.015 ms**  `golden_source_threads.py:1121`
              - `SourceThreadProcess._read_message` 
                wall **99.716 ms**  self **99.683 ms**  `golden_source_threads.py:892`
            _... 84 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **4,324.811 ms**  self **0.087 ms**  `golden_serial.py:15533`
  - `BaseEventLoop._run_once` 
    wall **3,255.093 ms**  self **0.021 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **3,254.074 ms**  self **3,254.073 ms**  `selectors.py:451`
  - `BaseEventLoop._run_once` 
    wall **1,128.955 ms**  self **0.017 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **1,128.772 ms**  self **1,128.770 ms**  `selectors.py:451`
  - `_unet_load_with_worker_stage` 
    wall **918.361 ms**  self **0.036 ms**  `golden_parallel.py:517`
    - `golden_unet_load` 
      wall **918.321 ms**  self **0.049 ms**  `golden_serial.py:13225`
      - `GoldenModelTransport.inspect` 
        wall **918.123 ms**  self **0.035 ms**  `golden_model_transport.py:973`
        - `_parse_layout` 
          wall **917.662 ms**  self **916.720 ms**  `golden_model_transport.py:304`
  - `_unet_load_with_worker_stage` 
    wall **45.139 ms**  self **2.105 ms**  `golden_parallel.py:517`
    - `golden_unet_load` 
      wall **43.030 ms**  self **0.194 ms**  `golden_serial.py:13225`
      - `BaseModel.load_model_weights` 
        wall **22.967 ms**  self **0.250 ms**  `model_base.py:358`
        - `Module.load_state_dict` 
          wall **22.713 ms**  self **0.092 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **22.621 ms**  self **0.123 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **17.951 ms**  self **0.081 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **1.167 ms**  self **0.012 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **1.006 ms**  self **0.009 ms**  `module.py:2589`
      - `GoldenTelemetryRecorder.event` 
        wall **8.909 ms**  self **0.011 ms**  `golden_serial.py:1672`
        - `GoldenTelemetryRecorder.event_at` 
          wall **8.899 ms**  self **0.009 ms**  `golden_serial.py:1675`
          - `deepcopy` 
            wall **8.889 ms**  self **0.007 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **8.882 ms**  self **0.035 ms**  `copy.py:227`
              - `deepcopy` 
                wall **8.766 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **8.763 ms**  self **0.007 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **8.308 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **8.306 ms**  self **0.152 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **5.568 ms**  self **0.004 ms**  `copy.py:128`
                        - `_deepcopy_list` 
                          wall **5.562 ms**  self **1.480 ms**  `copy.py:201`
                      - `deepcopy` 
                        wall **1.700 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **1.697 ms**  self **0.197 ms**  `copy.py:227`
      - `validate_unet_binding` 
        wall **8.199 ms**  self **1.440 ms**  `golden_serial.py:12867`
        - `Module.named_buffers` 
          wall **2.580 ms**  self **0.003 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **2.577 ms**  self **0.496 ms**  `module.py:2650`
      - `golden_unet_load.<locals>.checkpoint` 
        wall **1.051 ms**  self **0.015 ms**  `golden_serial.py:13327`
      - `golden_unet_load.<locals>.checkpoint` 
        wall **1.043 ms**  self **0.017 ms**  `golden_serial.py:13327`
  _... 2 more children >= 1 ms omitted_

## `golden_sampler_prepare`

- Stage wall: **37.941 ms**

- `golden_sampler_prepare` 
  wall **37.941 ms**  self **0.782 ms**  `full_execution_trace.py:330`
  - `golden_sampler_prepare` 
    wall **37.798 ms**  self **0.071 ms**  `golden_serial.py:13553`
    - `GoldenSerialRunner.run_closure` 
      wall **36.567 ms**  self **0.067 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._ensure` 
        wall **22.366 ms**  self **0.014 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **22.021 ms**  self **0.021 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **20.998 ms**  self **0.020 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **20.702 ms**  self **0.031 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._ensure` 
                wall **16.141 ms**  self **0.025 ms**  `golden_serial.py:9122`
                - `GoldenSerialRunner._execute_one` 
                  wall **13.125 ms**  self **0.032 ms**  `golden_serial.py:8902`
                  - `GoldenSerialRunner._call_node` 
                    wall **12.922 ms**  self **0.795 ms**  `golden_serial.py:9035`
                    - `EmptyImage.generate` 
                      wall **12.038 ms**  self **12.024 ms**  `nodes.py:1992`
                - `GoldenSerialRunner._ensure` 
                  wall **2.005 ms**  self **0.013 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **3.338 ms**  self **0.042 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._ensure` 
                  wall **2.799 ms**  self **0.013 ms**  `golden_serial.py:9122`
                  - `GoldenSerialRunner._execute_one` 
                    wall **2.640 ms**  self **0.026 ms**  `golden_serial.py:8902`
                    - `GoldenSerialRunner._call_node` 
                      wall **2.350 ms**  self **0.016 ms**  `golden_serial.py:9035`
                      - `make_locked_method_func.<locals>.wrapped_func` 
                        wall **2.053 ms**  self **0.002 ms**  `__init__.py:148`
                        - `_ComfyNodeBaseInternal.EXECUTE_NORMALIZED` 
                          wall **2.051 ms**  self **0.006 ms**  `_io.py:1987`
                          - `ImageRotate.execute` 
                            wall **2.045 ms**  self **2.045 ms**  `nodes_images.py:764`
              - `GoldenSerialRunner._ensure` 
                wall **1.157 ms**  self **0.014 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **7.178 ms**  self **0.018 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._ensure` 
          wall **6.392 ms**  self **0.013 ms**  `golden_serial.py:9122`
          - `GoldenSerialRunner._ensure` 
            wall **5.984 ms**  self **0.027 ms**  `golden_serial.py:9122`
            - `GoldenSerialRunner._ensure` 
              wall **5.190 ms**  self **0.017 ms**  `golden_serial.py:9122`
              - `GoldenSerialRunner._execute_one` 
                wall **5.154 ms**  self **0.029 ms**  `golden_serial.py:8902`
                - `GoldenSerialRunner._call_node` 
                  wall **4.750 ms**  self **0.009 ms**  `golden_serial.py:9035`
                  - `ModelSamplingAuraFlow.patch_aura` 
                    wall **4.596 ms**  self **0.014 ms**  `nodes_model_advanced.py:158`
                    - `ModelSamplingSD3.patch` 
                      wall **4.582 ms**  self **0.067 ms**  `nodes_model_advanced.py:131`
                      - `ModelPatcher.clone` 
                        wall **4.194 ms**  self **0.045 ms**  `model_patcher.py:430`
                        - `ModelPatcher.model_size` 
                          wall **3.818 ms**  self **0.100 ms**  `model_patcher.py:405`
                          - `module_size` 
                            wall **3.718 ms**  self **0.114 ms**  `model_management.py:631`
                            - `Module.state_dict` 
                              wall **3.605 ms**  self **0.020 ms**  `module.py:2199`
                              - `Module.state_dict` 
                                wall **3.569 ms**  self **0.022 ms**  `module.py:2199`
                                - `Module.state_dict` 
                                  wall **3.011 ms**  self **0.031 ms**  `module.py:2199`
      - `GoldenSerialRunner._ensure` 
        wall **2.453 ms**  self **0.020 ms**  `golden_serial.py:9122`
        - `GoldenSerialRunner._execute_one` 
          wall **2.432 ms**  self **0.064 ms**  `golden_serial.py:8902`
          - `classproperty.__get__` 
            wall **1.241 ms**  self **0.002 ms**  `__init__.py:95`
            - `_ComfyNodeBaseInternal.INPUT_IS_LIST` 
              wall **1.239 ms**  self **0.008 ms**  `_io.py:2111`
              - `_ComfyNodeBaseInternal.GET_SCHEMA` 
                wall **1.230 ms**  self **0.033 ms**  `_io.py:2181`
                - `Schema.validate` 
                  wall **1.176 ms**  self **1.173 ms**  `_io.py:1710`
      - `GoldenSerialRunner._ensure` 
        wall **1.374 ms**  self **0.019 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **1.291 ms**  self **0.020 ms**  `golden_serial.py:9122`
      - `GoldenSerialRunner._ensure` 
        wall **1.032 ms**  self **0.011 ms**  `golden_serial.py:9122`
  - `golden.sampler_prepare.prepare_dependency_closure` 
    wall **36.593 ms**  self **36.593 ms**  `full_execution_trace.py:330`

## `golden_vae_load`

- Stage wall: **628.023 ms**

- `golden_vae_load` 
  wall **628.023 ms**  self **124.880 ms**  `full_execution_trace.py:330`
  - `_WorkItem.run` 
    wall **527.798 ms**  self **0.013 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **527.600 ms**  self **0.011 ms**  `full_execution_trace.py:276`
      - `GoldenModelTransport._load_sync` 
        wall **527.589 ms**  self **0.006 ms**  `golden_model_transport.py:1004`
        - `GoldenModelTransport._load_c0_sync` 
          wall **527.583 ms**  self **0.007 ms**  `golden_model_transport.py:1449`
          - `GoldenModelTransport._load_c0_source_threads_sync` 
            wall **527.576 ms**  self **0.230 ms**  `golden_model_transport.py:1159`
            - `SourcePlanBridge.publish_all` 
              wall **381.796 ms**  self **0.149 ms**  `golden_source_threads.py:1343`
              - `SourceThreadProcess.wait_ready` 
                wall **338.276 ms**  self **0.030 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **250.349 ms**  self **250.349 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._read_message` 
                  wall **84.769 ms**  self **84.739 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._recover_ready_from_table` 
                  wall **1.532 ms**  self **0.039 ms**  `golden_source_threads.py:1092`
                  - `_FileLock.__exit__` 
                    wall **1.162 ms**  self **1.162 ms**  `golden_source_threads.py:493`
                - `SourceThreadProcess._poll_child` 
                  wall **1.251 ms**  self **0.006 ms**  `golden_source_threads.py:1001`
                  - `Popen.poll` 
                    wall **1.245 ms**  self **0.002 ms**  `subprocess.py:1233`
                    - `Popen._internal_poll` 
                      wall **1.243 ms**  self **1.243 ms**  `subprocess.py:1966`
              - `SourceThreadProcess.wait_ready` 
                wall **22.498 ms**  self **0.013 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **16.572 ms**  self **16.550 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess._resolve_ready_block` 
                  wall **5.480 ms**  self **0.030 ms**  `golden_source_threads.py:1036`
                  - `_FileLock.__enter__` 
                    wall **3.327 ms**  self **3.327 ms**  `golden_source_threads.py:486`
                  - `_FileLock.__exit__` 
                    wall **2.103 ms**  self **2.103 ms**  `golden_source_threads.py:493`
              - `SourceThreadProcess.wait_ready` 
                wall **10.982 ms**  self **0.011 ms**  `golden_source_threads.py:1121`
                - `SourceThreadProcess._read_message` 
                  wall **10.466 ms**  self **10.445 ms**  `golden_source_threads.py:892`
              - `SourceThreadProcess.plan_once` 
                wall **4.993 ms**  self **0.267 ms**  `golden_source_threads.py:910`
                - `_validate_identity` 
                  wall **2.302 ms**  self **0.018 ms**  `golden_source_threads.py:192`
                  - `_identity` 
                    wall **2.281 ms**  self **2.281 ms**  `golden_source_threads.py:187`
                - `SourceThreadProcess._read_message` 
                  wall **2.086 ms**  self **2.065 ms**  `golden_source_threads.py:892`
            - `GoldenModelTransport.inspect` 
              wall **118.798 ms**  self **0.023 ms**  `golden_model_transport.py:973`
              - `_parse_layout` 
                wall **93.576 ms**  self **93.136 ms**  `golden_model_transport.py:304`
              - `_file_identity` 
                wall **25.199 ms**  self **25.199 ms**  `golden_model_transport.py:274`
            - `GoldenModelTransport._views` 
              wall **19.165 ms**  self **19.165 ms**  `golden_model_transport.py:1910`
            - `GoldenQDTransport.finalize_external_ready` 
              wall **4.345 ms**  self **0.057 ms**  `golden_qd_transport.py:3130`
              - `GoldenQDTransport.drain` 
                wall **4.014 ms**  self **0.011 ms**  `golden_qd_transport.py:3115`
                - `TransportDispatcher.drain` 
                  wall **3.993 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                  - `Event.wait` 
                    wall **3.981 ms**  self **0.007 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **3.971 ms**  self **3.968 ms**  `threading.py:288`
            - `GpuDestinationPool.acquire` 
              wall **1.356 ms**  self **0.027 ms**  `golden_model_transport.py:183`
              - `GpuDestinationPool._allocate` 
                wall **1.321 ms**  self **1.152 ms**  `golden_model_transport.py:156`
  - `BaseEventLoop._run_once` 
    wall **503.143 ms**  self **0.020 ms**  `base_events.py:1845`
    - `EpollSelector.select` 
      wall **502.607 ms**  self **502.605 ms**  `selectors.py:451`
  - `sample_custom` 
    wall **181.759 ms**  self **3.153 ms**  `sample.py:86`
    - `sample` 
      wall **178.598 ms**  self **0.032 ms**  `samplers.py:1349`
      - `CFGGuider.sample` 
        wall **178.350 ms**  self **0.093 ms**  `samplers.py:1276`
        - `WrapperExecutor.execute` 
          wall **178.059 ms**  self **0.025 ms**  `patcher_extension.py:108`
          - `_cache_dit_outer_sample_wrapper` 
            wall **178.034 ms**  self **0.103 ms**  `nodes.py:438`
            - `WrapperExecutor.__call__` 
              wall **176.800 ms**  self **0.005 ms**  `patcher_extension.py:103`
              - `WrapperExecutor.execute` 
                wall **176.790 ms**  self **0.043 ms**  `patcher_extension.py:108`
                - `CFGGuider.outer_sample` 
                  wall **176.747 ms**  self **1.728 ms**  `samplers.py:1240`
                  - `prepare_sampling` 
                    wall **125.253 ms**  self **0.012 ms**  `sampler_helpers.py:181`
                    - `WrapperExecutor.execute` 
                      wall **125.237 ms**  self **0.007 ms**  `patcher_extension.py:108`
                      - `_prepare_sampling` 
                        wall **125.230 ms**  self **0.044 ms**  `sampler_helpers.py:188`
                        - `load_models_gpu` 
                          wall **125.070 ms**  self **0.078 ms**  `model_management.py:909`
                          - `LoadedModel.model_load` 
                            wall **123.020 ms**  self **0.020 ms**  `model_management.py:782`
                            - `LoadedModel.model_use_more_vram` 
                              wall **122.976 ms**  self **0.003 ms**  `model_management.py:817`
                              - `ModelPatcherDynamic.partially_load` 
                                wall **122.973 ms**  self **0.095 ms**  `model_patcher.py:2141`
                                - `ModelPatcherDynamic.load` 
                                  wall **122.814 ms**  self **4.809 ms**  `model_patcher.py:1853`
                                  - `ModelPatcher._load_list` 
                                    wall **41.463 ms**  self **6.918 ms**  `model_patcher.py:945`
                                  - `Module.named_buffers` 
                                    wall **2.764 ms**  self **0.004 ms**  `module.py:2754`
                                    - `Module._named_members` 
                                      wall **2.760 ms**  self **0.735 ms**  `module.py:2650`
                                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                    wall **1.313 ms**  self **0.007 ms**  `model_patcher.py:1947`
                                    - `ModelPatcher.patch_weight_to_device` 
                                      wall **1.260 ms**  self **0.056 ms**  `model_patcher.py:899`
                          - `free_memory` 
                            wall **1.385 ms**  self **0.039 ms**  `model_management.py:863`
                            - `get_free_memory` 
                              wall **1.250 ms**  self **0.034 ms**  `model_management.py:1748`
                  - `CFGGuider.inner_sample` 
                    wall **49.590 ms**  self **47.629 ms**  `samplers.py:1220`
                    - `WrapperExecutor.execute` 
                      wall **1.227 ms**  self **0.018 ms**  `patcher_extension.py:108`
                      - `KSAMPLER.sample` 
                        wall **1.210 ms**  self **0.106 ms**  `samplers.py:983`
  - `prepare_sampling` 
    wall **135.891 ms**  self **0.009 ms**  `sampler_helpers.py:181`
    - `WrapperExecutor.execute` 
      wall **135.877 ms**  self **0.006 ms**  `patcher_extension.py:108`
      - `_prepare_sampling` 
        wall **135.871 ms**  self **0.021 ms**  `sampler_helpers.py:188`
        - `load_models_gpu` 
          wall **135.748 ms**  self **0.081 ms**  `model_management.py:909`
          - `LoadedModel.model_load` 
            wall **134.320 ms**  self **0.576 ms**  `model_management.py:782`
            - `LoadedModel.model_use_more_vram` 
              wall **133.716 ms**  self **0.003 ms**  `model_management.py:817`
              - `ModelPatcherDynamic.partially_load` 
                wall **133.713 ms**  self **0.139 ms**  `model_patcher.py:2141`
                - `ModelPatcherDynamic.load` 
                  wall **133.498 ms**  self **5.140 ms**  `model_patcher.py:1853`
                  - `ModelPatcher._load_list` 
                    wall **37.133 ms**  self **4.661 ms**  `model_patcher.py:945`
                  - `ModelPatcherDynamic.restore_loaded_backups` 
                    wall **5.763 ms**  self **1.411 ms**  `model_patcher.py:1842`
                  - `Module.named_buffers` 
                    wall **2.600 ms**  self **0.005 ms**  `module.py:2754`
                    - `Module._named_members` 
                      wall **2.595 ms**  self **0.505 ms**  `module.py:2650`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.720 ms**  self **0.023 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.644 ms**  self **0.070 ms**  `model_patcher.py:899`
                      - `namedtuple` 
                        wall **1.326 ms**  self **1.325 ms**  `__init__.py:350`
                  - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                    wall **1.109 ms**  self **0.019 ms**  `model_patcher.py:1947`
                    - `ModelPatcher.patch_weight_to_device` 
                      wall **1.040 ms**  self **0.551 ms**  `model_patcher.py:899`
  - `_vae_load_with_worker_stage` 
    wall **98.129 ms**  self **0.008 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **98.115 ms**  self **0.261 ms**  `golden_serial.py:14229`
      - `VAE.__init__` 
        wall **91.621 ms**  self **56.691 ms**  `sd.py:487`
        - `Module.load_state_dict` 
          wall **17.803 ms**  self **0.105 ms**  `module.py:2535`
          - `Module.load_state_dict.<locals>.load` 
            wall **17.698 ms**  self **0.023 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **9.905 ms**  self **0.023 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **7.564 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.768 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.940 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **2.531 ms**  self **0.016 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.181 ms**  self **0.020 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.029 ms**  self **0.007 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.023 ms**  self **0.009 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **1.752 ms**  self **0.016 ms**  `module.py:2589`
            - `Module.load_state_dict.<locals>.load` 
              wall **7.324 ms**  self **0.025 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **4.825 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.714 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.636 ms**  self **0.015 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.632 ms**  self **0.019 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.295 ms**  self **0.012 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **1.976 ms**  self **0.018 ms**  `module.py:2589`
        - `Module.to` 
          wall **8.247 ms**  self **0.045 ms**  `module.py:1259`
          - `Module._apply` 
            wall **8.202 ms**  self **0.011 ms**  `module.py:930`
            - `Module._apply` 
              wall **5.636 ms**  self **0.016 ms**  `module.py:930`
              - `Module._apply` 
                wall **4.466 ms**  self **0.013 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.682 ms**  self **0.018 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.483 ms**  self **0.010 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.087 ms**  self **0.029 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.381 ms**  self **0.010 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.293 ms**  self **0.009 ms**  `module.py:930`
            - `Module._apply` 
              wall **2.542 ms**  self **0.010 ms**  `module.py:930`
              - `Module._apply` 
                wall **1.989 ms**  self **0.008 ms**  `module.py:930`
        - `archive_model_dtypes` 
          wall **4.548 ms**  self **0.801 ms**  `model_management.py:1045`
        - `Module.eval` 
          wall **2.050 ms**  self **0.002 ms**  `module.py:2916`
          - `Module.train` 
            wall **2.049 ms**  self **0.008 ms**  `module.py:2894`
            - `Module.train` 
              wall **1.123 ms**  self **0.005 ms**  `module.py:2894`
        - `VAE.model_size` 
          wall **1.927 ms**  self **0.049 ms**  `sd.py:1095`
          - `module_size` 
            wall **1.878 ms**  self **0.056 ms**  `model_management.py:631`
            - `Module.state_dict` 
              wall **1.821 ms**  self **0.018 ms**  `module.py:2199`
      - `validate_qd_adoption` 
        wall **3.770 ms**  self **0.833 ms**  `golden_serial.py:12922`
        - `Module.named_buffers` 
          wall **1.081 ms**  self **0.001 ms**  `module.py:2754`
          - `Module._named_members` 
            wall **1.080 ms**  self **0.210 ms**  `module.py:2650`
  - `RK_NoiseSampler.prepare_sigmas` 
    wall **33.990 ms**  self **33.990 ms**  `rk_noise_sampler_beta.py:785`
  - `_vae_load_with_worker_stage` 
    wall **26.604 ms**  self **0.069 ms**  `golden_parallel.py:522`
    - `golden_vae_load` 
      wall **26.531 ms**  self **0.025 ms**  `golden_serial.py:14229`
      - `GoldenModelTransport.load` 
        wall **26.471 ms**  self **0.009 ms**  `golden_model_transport.py:987`
        - `to_thread` 
          wall **26.284 ms**  self **0.027 ms**  `threads.py:12`
          - `BaseEventLoop.run_in_executor` 
            wall **26.257 ms**  self **0.011 ms**  `base_events.py:815`
            - `ThreadPoolExecutor.submit` 
              wall **26.149 ms**  self **0.008 ms**  `thread.py:161`
              - `ThreadPoolExecutor._adjust_thread_count` 
                wall **26.135 ms**  self **0.018 ms**  `thread.py:180`
                - `Thread.start` 
                  wall **26.077 ms**  self **0.178 ms**  `threading.py:938`
                  - `Event.wait` 
                    wall **25.898 ms**  self **0.009 ms**  `threading.py:604`
                    - `Condition.wait` 
                      wall **25.885 ms**  self **25.880 ms**  `threading.py:288`
  - `LatentGuide.init_guides` 
    wall **24.573 ms**  self **3.892 ms**  `rk_guide_func_beta.py:125`
    - `pad` 
      wall **16.307 ms**  self **16.306 ms**  `functional.py:5761`
  _... 11 more children >= 1 ms omitted_

## `golden_sampling`

- Stage wall: **4,582.540 ms**

- `golden_sampling` 
  wall **4,582.540 ms**  self **4,582.540 ms**  `full_execution_trace.py:330`
  - `golden_sampling` 
    wall **4,582.477 ms**  self **0.241 ms**  `golden_serial.py:13704`
    - `GoldenSerialRunner.run_closure` 
      wall **4,436.904 ms**  self **0.043 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **4,436.639 ms**  self **0.060 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **4,435.799 ms**  self **0.069 ms**  `golden_serial.py:9035`
          - `ClownsharKSampler_Beta.main` 
            wall **4,435.583 ms**  self **0.301 ms**  `samplers.py:1745`
            - `SharkSampler.main` 
              wall **4,432.789 ms**  self **14.632 ms**  `samplers.py:153`
              - `CFGGuider.sample` 
                wall **4,187.818 ms**  self **0.060 ms**  `samplers.py:1276`
                - `WrapperExecutor.execute` 
                  wall **4,187.610 ms**  self **0.006 ms**  `patcher_extension.py:108`
                  - `_cache_dit_outer_sample_wrapper` 
                    wall **4,187.603 ms**  self **0.052 ms**  `nodes.py:438`
                    - `WrapperExecutor.__call__` 
                      wall **4,187.200 ms**  self **0.005 ms**  `patcher_extension.py:103`
                      - `WrapperExecutor.execute` 
                        wall **4,187.186 ms**  self **0.030 ms**  `patcher_extension.py:108`
                        - `CFGGuider.outer_sample` 
                          wall **4,187.156 ms**  self **2.006 ms**  `samplers.py:1240`
                          - `CFGGuider.inner_sample` 
                            wall **4,049.069 ms**  self **0.845 ms**  `samplers.py:1220`
                            - `WrapperExecutor.execute` 
                              wall **4,046.398 ms**  self **0.030 ms**  `patcher_extension.py:108`
                              - `KSAMPLER.sample` 
                                wall **4,046.367 ms**  self **0.125 ms**  `samplers.py:983`
                                - `context_decorator.<locals>.decorate_context` 
                                  wall **4,044.825 ms**  self **0.825 ms**  `_contextlib.py:120`
                                  - `sample_rk_beta` 
                                    wall **4,043.950 ms**  self **56.151 ms**  `rk_sampler_beta.py:110`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **664.485 ms**  self **1.054 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **662.958 ms**  self **0.261 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **662.273 ms**  self **0.011 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **662.263 ms**  self **0.008 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **662.255 ms**  self **0.018 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **662.225 ms**  self **0.011 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **662.215 ms**  self **0.079 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **662.136 ms**  self **0.026 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **651.527 ms**  self **0.007 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **651.520 ms**  self **0.007 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **651.509 ms**  self **0.046 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **651.463 ms**  self **0.904 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **648.331 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **648.313 ms**  self **0.023 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **648.290 ms**  self **1.032 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **646.414 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **646.407 ms**  self **0.032 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **646.375 ms**  self **646.375 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **10.583 ms**  self **0.254 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **10.330 ms**  self **10.081 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **321.960 ms**  self **0.162 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **321.752 ms**  self **0.061 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **321.683 ms**  self **0.009 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **321.674 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **321.669 ms**  self **0.017 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **321.641 ms**  self **0.004 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **321.637 ms**  self **0.018 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **321.619 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **202.197 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **202.194 ms**  self **0.011 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **202.178 ms**  self **0.025 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **202.152 ms**  self **0.342 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **197.165 ms**  self **0.007 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **197.150 ms**  self **0.013 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **197.137 ms**  self **0.128 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **196.567 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **196.562 ms**  self **0.014 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **196.549 ms**  self **196.549 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **2.948 ms**  self **0.020 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **2.852 ms**  self **0.017 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **2.499 ms**  self **2.490 ms**  `memory.py:847`
                                                            - `cond_cat` 
                                                              wall **1.338 ms**  self **0.016 ms**  `samplers.py:148`
                                                              - `CONDRegular.concat` 
                                                                wall **1.321 ms**  self **1.321 ms**  `conds.py:44`
                                                    - `cfg_function` 
                                                      wall **119.404 ms**  self **0.087 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **119.318 ms**  self **119.044 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **311.310 ms**  self **0.188 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **311.094 ms**  self **0.085 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **310.991 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **310.984 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **310.980 ms**  self **0.007 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **310.964 ms**  self **0.005 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **310.959 ms**  self **0.023 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **310.935 ms**  self **0.018 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **168.897 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **168.894 ms**  self **0.006 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **168.884 ms**  self **0.084 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **168.799 ms**  self **0.851 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **165.171 ms**  self **0.009 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **165.155 ms**  self **0.040 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **165.115 ms**  self **0.134 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **164.423 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **164.417 ms**  self **0.011 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **164.406 ms**  self **164.406 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **2.174 ms**  self **0.035 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **2.009 ms**  self **0.019 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.612 ms**  self **1.604 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **142.021 ms**  self **0.095 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **141.925 ms**  self **141.925 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **309.342 ms**  self **0.137 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **309.178 ms**  self **0.097 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **309.059 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **309.052 ms**  self **0.005 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **309.048 ms**  self **0.008 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **309.031 ms**  self **0.004 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **309.027 ms**  self **0.014 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **309.013 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **159.556 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **159.553 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **159.543 ms**  self **0.175 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **159.368 ms**  self **0.597 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **156.519 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **156.505 ms**  self **0.015 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **156.490 ms**  self **0.219 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **155.773 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **155.768 ms**  self **0.012 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **155.756 ms**  self **155.756 ms**  `nodes.py:215`
                                                            - `ModelPatcher.get_free_memory` 
                                                              wall **1.773 ms**  self **0.036 ms**  `model_patcher.py:417`
                                                              - `get_free_memory` 
                                                                wall **1.616 ms**  self **0.017 ms**  `model_management.py:1748`
                                                                - `mem_get_info` 
                                                                  wall **1.233 ms**  self **1.225 ms**  `memory.py:847`
                                                    - `cfg_function` 
                                                      wall **149.440 ms**  self **0.142 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **149.298 ms**  self **149.298 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **307.713 ms**  self **0.155 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **307.521 ms**  self **0.049 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **307.461 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **307.454 ms**  self **0.003 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **307.451 ms**  self **0.007 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **307.439 ms**  self **0.004 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **307.434 ms**  self **0.013 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **307.422 ms**  self **0.016 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **182.943 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **182.940 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **182.932 ms**  self **0.024 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **182.908 ms**  self **0.344 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **181.284 ms**  self **0.007 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **181.271 ms**  self **0.012 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **181.259 ms**  self **0.102 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **180.715 ms**  self **0.005 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **180.710 ms**  self **0.010 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **180.701 ms**  self **180.701 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **124.462 ms**  self **0.074 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **124.389 ms**  self **124.389 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **301.959 ms**  self **0.742 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **301.186 ms**  self **0.058 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **301.118 ms**  self **0.007 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **301.111 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **301.107 ms**  self **0.009 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **301.091 ms**  self **0.007 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **301.084 ms**  self **0.222 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **300.862 ms**  self **0.266 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **179.172 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **179.169 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **179.160 ms**  self **0.077 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **179.083 ms**  self **0.522 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **177.277 ms**  self **0.008 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **177.261 ms**  self **0.017 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **177.245 ms**  self **0.177 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **176.554 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **176.548 ms**  self **0.012 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **176.536 ms**  self **176.536 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **121.424 ms**  self **0.373 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **121.051 ms**  self **121.051 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **299.787 ms**  self **0.570 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **299.187 ms**  self **0.048 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **299.131 ms**  self **0.006 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **299.125 ms**  self **0.007 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **299.118 ms**  self **0.009 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **299.102 ms**  self **0.006 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **299.095 ms**  self **0.058 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **299.037 ms**  self **0.217 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **172.780 ms**  self **0.003 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **172.777 ms**  self **0.004 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **172.768 ms**  self **0.073 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **172.695 ms**  self **0.556 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **170.833 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **170.814 ms**  self **0.046 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **170.768 ms**  self **0.180 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **169.981 ms**  self **0.007 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **169.974 ms**  self **0.012 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **169.963 ms**  self **169.963 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **126.040 ms**  self **0.602 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **125.438 ms**  self **125.438 ms**  `noise_injection.py:285`
                                    - `RK_Method_Exponential.__call__` 
                                      wall **299.779 ms**  self **0.520 ms**  `rk_method_beta.py:887`
                                      - `RK_Method_Beta.model_denoised` 
                                        wall **299.220 ms**  self **0.062 ms**  `rk_method_beta.py:137`
                                        - `KSamplerX0Inpaint.__call__` 
                                          wall **299.148 ms**  self **0.008 ms**  `samplers.py:634`
                                          - `CFGGuider.__call__` 
                                            wall **299.140 ms**  self **0.004 ms**  `samplers.py:1207`
                                            - `CFGGuider.outer_predict_noise` 
                                              wall **299.136 ms**  self **0.014 ms**  `samplers.py:1210`
                                              - `WrapperExecutor.execute` 
                                                wall **299.112 ms**  self **0.004 ms**  `patcher_extension.py:108`
                                                - `SharkGuider.predict_noise` 
                                                  wall **299.108 ms**  self **0.016 ms**  `samplers.py:99`
                                                  - `sampling_function` 
                                                    wall **299.092 ms**  self **0.017 ms**  `samplers.py:609`
                                                    - `calc_cond_batch` 
                                                      wall **178.682 ms**  self **0.004 ms**  `samplers.py:208`
                                                      - `_calc_cond_batch_outer` 
                                                        wall **178.678 ms**  self **0.005 ms**  `samplers.py:214`
                                                        - `WrapperExecutor.execute` 
                                                          wall **178.669 ms**  self **0.025 ms**  `patcher_extension.py:108`
                                                          - `_calc_cond_batch` 
                                                            wall **178.644 ms**  self **0.423 ms**  `samplers.py:221`
                                                            - `BaseModel.apply_model` 
                                                              wall **176.979 ms**  self **0.011 ms**  `model_base.py:204`
                                                              - `WrapperExecutor.execute` 
                                                                wall **176.958 ms**  self **0.015 ms**  `patcher_extension.py:108`
                                                                - `BaseModel._apply_model` 
                                                                  wall **176.943 ms**  self **0.132 ms**  `model_base.py:211`
                                                                  - `Module._wrapped_call_impl` 
                                                                    wall **176.309 ms**  self **0.006 ms**  `module.py:1779`
                                                                    - `Module._call_impl` 
                                                                      wall **176.303 ms**  self **0.012 ms**  `module.py:1787`
                                                                      - `_enable_lightweight_cache.<locals>.cached_forward` 
                                                                        wall **176.291 ms**  self **176.291 ms**  `nodes.py:215`
                                                    - `cfg_function` 
                                                      wall **120.393 ms**  self **0.143 ms**  `samplers.py:592`
                                                      - `LGNoiseInjectionLatent.apply.<locals>.cfg_function` 
                                                        wall **120.249 ms**  self **120.010 ms**  `noise_injection.py:285`
                                    _... 35 more children >= 1 ms omitted_
              - `deepcopy` 
                wall **8.309 ms**  self **0.012 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **8.296 ms**  self **0.039 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **2.283 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **2.278 ms**  self **0.066 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **2.182 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **2.162 ms**  self **0.006 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **2.150 ms**  self **0.007 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **2.142 ms**  self **2.141 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.485 ms**  self **0.008 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.477 ms**  self **0.087 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.333 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.308 ms**  self **0.010 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.289 ms**  self **0.009 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.280 ms**  self **1.279 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.431 ms**  self **0.006 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.424 ms**  self **0.089 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.300 ms**  self **0.004 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.280 ms**  self **0.008 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.264 ms**  self **0.007 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.258 ms**  self **1.257 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.392 ms**  self **0.005 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.386 ms**  self **0.075 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.277 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.259 ms**  self **0.006 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.246 ms**  self **0.006 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.240 ms**  self **1.239 ms**  `storage.py:262`
                  - `deepcopy` 
                    wall **1.269 ms**  self **0.004 ms**  `copy.py:128`
                    - `Tensor.__deepcopy__` 
                      wall **1.264 ms**  self **0.067 ms**  `_tensor.py:134`
                      - `TypedStorage._deepcopy` 
                        wall **1.167 ms**  self **0.003 ms**  `storage.py:1155`
                        - `deepcopy` 
                          wall **1.143 ms**  self **0.006 ms**  `copy.py:128`
                          - `_StorageBase.__deepcopy__` 
                            wall **1.125 ms**  self **0.008 ms**  `storage.py:246`
                            - `_StorageBase.clone` 
                              wall **1.117 ms**  self **1.117 ms**  `storage.py:262`
              - `_disable_dynamo.<locals>.inner` 
                wall **2.046 ms**  self **0.009 ms**  `_compile.py:42`
                - `DisableContext.__call__.<locals>._fn` 
                  wall **2.037 ms**  self **0.008 ms**  `eval_frame.py:1523`
                  - `manual_seed` 
                    wall **2.027 ms**  self **0.002 ms**  `random.py:49`
                    - `_manual_seed_impl` 
                      wall **2.025 ms**  self **0.039 ms**  `random.py:62`
                      - `manual_seed_all` 
                        wall **1.244 ms**  self **0.004 ms**  `random.py:97`
                        - `_lazy_call` 
                          wall **1.240 ms**  self **0.012 ms**  `__init__.py:319`
                          - `format_stack` 
                            wall **1.221 ms**  self **0.012 ms**  `traceback.py:213`
                            - `extract_stack` 
                              wall **1.043 ms**  self **0.008 ms**  `traceback.py:220`
                              - `StackSummary.extract` 
                                wall **1.034 ms**  self **0.006 ms**  `traceback.py:375`
                                - `StackSummary._extract_from_extended_frame_gen` 
                                  wall **1.029 ms**  self **0.137 ms**  `traceback.py:397`
              - `BaseModel.process_latent_out` 
                wall **1.623 ms**  self **0.005 ms**  `model_base.py:378`
                - `Flux.process_out` 
                  wall **1.617 ms**  self **1.617 ms**  `latent_formats.py:193`
    - `import_module` 
      wall **119.556 ms**  self **119.556 ms**  `__init__.py:108`
    - `GoldenTelemetryRecorder.events` 
      wall **19.190 ms**  self **0.022 ms**  `golden_serial.py:1838`
      - `deepcopy` 
        wall **19.168 ms**  self **0.003 ms**  `copy.py:128`
        - `_deepcopy_list` 
          wall **19.165 ms**  self **0.034 ms**  `copy.py:201`
          - `deepcopy` 
            wall **9.034 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **9.031 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **9.017 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **9.014 ms**  self **0.038 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **8.898 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **8.895 ms**  self **0.009 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **8.469 ms**  self **0.004 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **8.463 ms**  self **0.157 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **5.218 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **5.215 ms**  self **1.438 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.677 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.675 ms**  self **0.204 ms**  `copy.py:227`
          - `deepcopy` 
            wall **7.101 ms**  self **0.002 ms**  `copy.py:128`
            - `_deepcopy_dict` 
              wall **7.098 ms**  self **0.006 ms**  `copy.py:227`
              - `deepcopy` 
                wall **7.083 ms**  self **0.002 ms**  `copy.py:128`
                - `_deepcopy_dict` 
                  wall **7.081 ms**  self **0.041 ms**  `copy.py:227`
                  - `deepcopy` 
                    wall **6.962 ms**  self **0.002 ms**  `copy.py:128`
                    - `_deepcopy_dict` 
                      wall **6.960 ms**  self **0.006 ms**  `copy.py:227`
                      - `deepcopy` 
                        wall **6.508 ms**  self **0.002 ms**  `copy.py:128`
                        - `_deepcopy_dict` 
                          wall **6.506 ms**  self **0.159 ms**  `copy.py:227`
                          - `deepcopy` 
                            wall **4.470 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_list` 
                              wall **4.467 ms**  self **1.263 ms**  `copy.py:201`
                          - `deepcopy` 
                            wall **1.076 ms**  self **0.002 ms**  `copy.py:128`
                            - `_deepcopy_dict` 
                              wall **1.074 ms**  self **0.129 ms**  `copy.py:227`
    - `_attach_golden_sampling_decomposition` 
      wall **1.667 ms**  self **0.038 ms**  `golden_serial.py:9742`
  - `_WorkItem.run` 
    wall **632.322 ms**  self **0.020 ms**  `thread.py:53`
    - `thread_traced.<locals>._run` 
      wall **632.049 ms**  self **0.018 ms**  `full_execution_trace.py:276`
      - `_run_overlap_stage_offloaded.<locals>.run` 
        wall **632.031 ms**  self **0.028 ms**  `golden_serial.py:15424`
        - `BaseEventLoop.run_until_complete` 
          wall **629.983 ms**  self **0.012 ms**  `base_events.py:617`
          - `BaseEventLoop.run_forever` 
            wall **629.963 ms**  self **0.057 ms**  `base_events.py:593`
            - `BaseEventLoop._run_once` 
              wall **99.944 ms**  self **1.658 ms**  `base_events.py:1845`
              - `Handle._run` 
                wall **98.252 ms**  self **98.235 ms**  `events.py:78`
            - `BaseEventLoop._run_once` 
              wall **26.691 ms**  self **0.010 ms**  `base_events.py:1845`
              - `Handle._run` 
                wall **26.646 ms**  self **26.646 ms**  `events.py:78`
  - `Thread.run` 
    wall **629.566 ms**  self **0.007 ms**  `threading.py:964`
    - `_worker` 
      wall **629.559 ms**  self **101.751 ms**  `thread.py:69`
  - `golden_vae_load` 
    wall **628.023 ms**  self **124.880 ms**  `full_execution_trace.py:330`
    - `_WorkItem.run` 
      wall **527.798 ms**  self **0.013 ms**  `thread.py:53`
      - `thread_traced.<locals>._run` 
        wall **527.600 ms**  self **0.011 ms**  `full_execution_trace.py:276`
        - `GoldenModelTransport._load_sync` 
          wall **527.589 ms**  self **0.006 ms**  `golden_model_transport.py:1004`
          - `GoldenModelTransport._load_c0_sync` 
            wall **527.583 ms**  self **0.007 ms**  `golden_model_transport.py:1449`
            - `GoldenModelTransport._load_c0_source_threads_sync` 
              wall **527.576 ms**  self **0.230 ms**  `golden_model_transport.py:1159`
              - `SourcePlanBridge.publish_all` 
                wall **381.796 ms**  self **0.149 ms**  `golden_source_threads.py:1343`
                - `SourceThreadProcess.wait_ready` 
                  wall **338.276 ms**  self **0.030 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **250.349 ms**  self **250.349 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._read_message` 
                    wall **84.769 ms**  self **84.739 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._recover_ready_from_table` 
                    wall **1.532 ms**  self **0.039 ms**  `golden_source_threads.py:1092`
                    - `_FileLock.__exit__` 
                      wall **1.162 ms**  self **1.162 ms**  `golden_source_threads.py:493`
                  - `SourceThreadProcess._poll_child` 
                    wall **1.251 ms**  self **0.006 ms**  `golden_source_threads.py:1001`
                    - `Popen.poll` 
                      wall **1.245 ms**  self **0.002 ms**  `subprocess.py:1233`
                      - `Popen._internal_poll` 
                        wall **1.243 ms**  self **1.243 ms**  `subprocess.py:1966`
                - `SourceThreadProcess.wait_ready` 
                  wall **22.498 ms**  self **0.013 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **16.572 ms**  self **16.550 ms**  `golden_source_threads.py:892`
                  - `SourceThreadProcess._resolve_ready_block` 
                    wall **5.480 ms**  self **0.030 ms**  `golden_source_threads.py:1036`
                    - `_FileLock.__enter__` 
                      wall **3.327 ms**  self **3.327 ms**  `golden_source_threads.py:486`
                    - `_FileLock.__exit__` 
                      wall **2.103 ms**  self **2.103 ms**  `golden_source_threads.py:493`
                - `SourceThreadProcess.wait_ready` 
                  wall **10.982 ms**  self **0.011 ms**  `golden_source_threads.py:1121`
                  - `SourceThreadProcess._read_message` 
                    wall **10.466 ms**  self **10.445 ms**  `golden_source_threads.py:892`
                - `SourceThreadProcess.plan_once` 
                  wall **4.993 ms**  self **0.267 ms**  `golden_source_threads.py:910`
                  - `_validate_identity` 
                    wall **2.302 ms**  self **0.018 ms**  `golden_source_threads.py:192`
                    - `_identity` 
                      wall **2.281 ms**  self **2.281 ms**  `golden_source_threads.py:187`
                  - `SourceThreadProcess._read_message` 
                    wall **2.086 ms**  self **2.065 ms**  `golden_source_threads.py:892`
              - `GoldenModelTransport.inspect` 
                wall **118.798 ms**  self **0.023 ms**  `golden_model_transport.py:973`
                - `_parse_layout` 
                  wall **93.576 ms**  self **93.136 ms**  `golden_model_transport.py:304`
                - `_file_identity` 
                  wall **25.199 ms**  self **25.199 ms**  `golden_model_transport.py:274`
              - `GoldenModelTransport._views` 
                wall **19.165 ms**  self **19.165 ms**  `golden_model_transport.py:1910`
              - `GoldenQDTransport.finalize_external_ready` 
                wall **4.345 ms**  self **0.057 ms**  `golden_qd_transport.py:3130`
                - `GoldenQDTransport.drain` 
                  wall **4.014 ms**  self **0.011 ms**  `golden_qd_transport.py:3115`
                  - `TransportDispatcher.drain` 
                    wall **3.993 ms**  self **0.009 ms**  `golden_qd_transport.py:2821`
                    - `Event.wait` 
                      wall **3.981 ms**  self **0.007 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **3.971 ms**  self **3.968 ms**  `threading.py:288`
              - `GpuDestinationPool.acquire` 
                wall **1.356 ms**  self **0.027 ms**  `golden_model_transport.py:183`
                - `GpuDestinationPool._allocate` 
                  wall **1.321 ms**  self **1.152 ms**  `golden_model_transport.py:156`
    - `BaseEventLoop._run_once` 
      wall **503.143 ms**  self **0.020 ms**  `base_events.py:1845`
      - `EpollSelector.select` 
        wall **502.607 ms**  self **502.605 ms**  `selectors.py:451`
    - `sample_custom` 
      wall **181.759 ms**  self **3.153 ms**  `sample.py:86`
      - `sample` 
        wall **178.598 ms**  self **0.032 ms**  `samplers.py:1349`
        - `CFGGuider.sample` 
          wall **178.350 ms**  self **0.093 ms**  `samplers.py:1276`
          - `WrapperExecutor.execute` 
            wall **178.059 ms**  self **0.025 ms**  `patcher_extension.py:108`
            - `_cache_dit_outer_sample_wrapper` 
              wall **178.034 ms**  self **0.103 ms**  `nodes.py:438`
              - `WrapperExecutor.__call__` 
                wall **176.800 ms**  self **0.005 ms**  `patcher_extension.py:103`
                - `WrapperExecutor.execute` 
                  wall **176.790 ms**  self **0.043 ms**  `patcher_extension.py:108`
                  - `CFGGuider.outer_sample` 
                    wall **176.747 ms**  self **1.728 ms**  `samplers.py:1240`
                    - `prepare_sampling` 
                      wall **125.253 ms**  self **0.012 ms**  `sampler_helpers.py:181`
                      - `WrapperExecutor.execute` 
                        wall **125.237 ms**  self **0.007 ms**  `patcher_extension.py:108`
                        - `_prepare_sampling` 
                          wall **125.230 ms**  self **0.044 ms**  `sampler_helpers.py:188`
                          - `load_models_gpu` 
                            wall **125.070 ms**  self **0.078 ms**  `model_management.py:909`
                            - `LoadedModel.model_load` 
                              wall **123.020 ms**  self **0.020 ms**  `model_management.py:782`
                              - `LoadedModel.model_use_more_vram` 
                                wall **122.976 ms**  self **0.003 ms**  `model_management.py:817`
                                - `ModelPatcherDynamic.partially_load` 
                                  wall **122.973 ms**  self **0.095 ms**  `model_patcher.py:2141`
                                  - `ModelPatcherDynamic.load` 
                                    wall **122.814 ms**  self **4.809 ms**  `model_patcher.py:1853`
                                    - `ModelPatcher._load_list` 
                                      wall **41.463 ms**  self **6.918 ms**  `model_patcher.py:945`
                                    - `Module.named_buffers` 
                                      wall **2.764 ms**  self **0.004 ms**  `module.py:2754`
                                      - `Module._named_members` 
                                        wall **2.760 ms**  self **0.735 ms**  `module.py:2650`
                                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                                      wall **1.313 ms**  self **0.007 ms**  `model_patcher.py:1947`
                                      - `ModelPatcher.patch_weight_to_device` 
                                        wall **1.260 ms**  self **0.056 ms**  `model_patcher.py:899`
                            - `free_memory` 
                              wall **1.385 ms**  self **0.039 ms**  `model_management.py:863`
                              - `get_free_memory` 
                                wall **1.250 ms**  self **0.034 ms**  `model_management.py:1748`
                    - `CFGGuider.inner_sample` 
                      wall **49.590 ms**  self **47.629 ms**  `samplers.py:1220`
                      - `WrapperExecutor.execute` 
                        wall **1.227 ms**  self **0.018 ms**  `patcher_extension.py:108`
                        - `KSAMPLER.sample` 
                          wall **1.210 ms**  self **0.106 ms**  `samplers.py:983`
    - `prepare_sampling` 
      wall **135.891 ms**  self **0.009 ms**  `sampler_helpers.py:181`
      - `WrapperExecutor.execute` 
        wall **135.877 ms**  self **0.006 ms**  `patcher_extension.py:108`
        - `_prepare_sampling` 
          wall **135.871 ms**  self **0.021 ms**  `sampler_helpers.py:188`
          - `load_models_gpu` 
            wall **135.748 ms**  self **0.081 ms**  `model_management.py:909`
            - `LoadedModel.model_load` 
              wall **134.320 ms**  self **0.576 ms**  `model_management.py:782`
              - `LoadedModel.model_use_more_vram` 
                wall **133.716 ms**  self **0.003 ms**  `model_management.py:817`
                - `ModelPatcherDynamic.partially_load` 
                  wall **133.713 ms**  self **0.139 ms**  `model_patcher.py:2141`
                  - `ModelPatcherDynamic.load` 
                    wall **133.498 ms**  self **5.140 ms**  `model_patcher.py:1853`
                    - `ModelPatcher._load_list` 
                      wall **37.133 ms**  self **4.661 ms**  `model_patcher.py:945`
                    - `ModelPatcherDynamic.restore_loaded_backups` 
                      wall **5.763 ms**  self **1.411 ms**  `model_patcher.py:1842`
                    - `Module.named_buffers` 
                      wall **2.600 ms**  self **0.005 ms**  `module.py:2754`
                      - `Module._named_members` 
                        wall **2.595 ms**  self **0.505 ms**  `module.py:2650`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.720 ms**  self **0.023 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.644 ms**  self **0.070 ms**  `model_patcher.py:899`
                        - `namedtuple` 
                          wall **1.326 ms**  self **1.325 ms**  `__init__.py:350`
                    - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                      wall **1.109 ms**  self **0.019 ms**  `model_patcher.py:1947`
                      - `ModelPatcher.patch_weight_to_device` 
                        wall **1.040 ms**  self **0.551 ms**  `model_patcher.py:899`
    - `_vae_load_with_worker_stage` 
      wall **98.129 ms**  self **0.008 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **98.115 ms**  self **0.261 ms**  `golden_serial.py:14229`
        - `VAE.__init__` 
          wall **91.621 ms**  self **56.691 ms**  `sd.py:487`
          - `Module.load_state_dict` 
            wall **17.803 ms**  self **0.105 ms**  `module.py:2535`
            - `Module.load_state_dict.<locals>.load` 
              wall **17.698 ms**  self **0.023 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **9.905 ms**  self **0.023 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **7.564 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.768 ms**  self **0.019 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.940 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **2.531 ms**  self **0.016 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **2.181 ms**  self **0.020 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.029 ms**  self **0.007 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.023 ms**  self **0.009 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.752 ms**  self **0.016 ms**  `module.py:2589`
              - `Module.load_state_dict.<locals>.load` 
                wall **7.324 ms**  self **0.025 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **4.825 ms**  self **0.025 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.714 ms**  self **0.015 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.636 ms**  self **0.015 ms**  `module.py:2589`
                  - `Module.load_state_dict.<locals>.load` 
                    wall **1.632 ms**  self **0.019 ms**  `module.py:2589`
                    - `Module.load_state_dict.<locals>.load` 
                      wall **1.295 ms**  self **0.012 ms**  `module.py:2589`
                - `Module.load_state_dict.<locals>.load` 
                  wall **1.976 ms**  self **0.018 ms**  `module.py:2589`
          - `Module.to` 
            wall **8.247 ms**  self **0.045 ms**  `module.py:1259`
            - `Module._apply` 
              wall **8.202 ms**  self **0.011 ms**  `module.py:930`
              - `Module._apply` 
                wall **5.636 ms**  self **0.016 ms**  `module.py:930`
                - `Module._apply` 
                  wall **4.466 ms**  self **0.013 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.682 ms**  self **0.018 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.483 ms**  self **0.010 ms**  `module.py:930`
                      - `Module._apply` 
                        wall **1.087 ms**  self **0.029 ms**  `module.py:930`
                  - `Module._apply` 
                    wall **1.381 ms**  self **0.010 ms**  `module.py:930`
                    - `Module._apply` 
                      wall **1.293 ms**  self **0.009 ms**  `module.py:930`
              - `Module._apply` 
                wall **2.542 ms**  self **0.010 ms**  `module.py:930`
                - `Module._apply` 
                  wall **1.989 ms**  self **0.008 ms**  `module.py:930`
          - `archive_model_dtypes` 
            wall **4.548 ms**  self **0.801 ms**  `model_management.py:1045`
          - `Module.eval` 
            wall **2.050 ms**  self **0.002 ms**  `module.py:2916`
            - `Module.train` 
              wall **2.049 ms**  self **0.008 ms**  `module.py:2894`
              - `Module.train` 
                wall **1.123 ms**  self **0.005 ms**  `module.py:2894`
          - `VAE.model_size` 
            wall **1.927 ms**  self **0.049 ms**  `sd.py:1095`
            - `module_size` 
              wall **1.878 ms**  self **0.056 ms**  `model_management.py:631`
              - `Module.state_dict` 
                wall **1.821 ms**  self **0.018 ms**  `module.py:2199`
        - `validate_qd_adoption` 
          wall **3.770 ms**  self **0.833 ms**  `golden_serial.py:12922`
          - `Module.named_buffers` 
            wall **1.081 ms**  self **0.001 ms**  `module.py:2754`
            - `Module._named_members` 
              wall **1.080 ms**  self **0.210 ms**  `module.py:2650`
    - `RK_NoiseSampler.prepare_sigmas` 
      wall **33.990 ms**  self **33.990 ms**  `rk_noise_sampler_beta.py:785`
    - `_vae_load_with_worker_stage` 
      wall **26.604 ms**  self **0.069 ms**  `golden_parallel.py:522`
      - `golden_vae_load` 
        wall **26.531 ms**  self **0.025 ms**  `golden_serial.py:14229`
        - `GoldenModelTransport.load` 
          wall **26.471 ms**  self **0.009 ms**  `golden_model_transport.py:987`
          - `to_thread` 
            wall **26.284 ms**  self **0.027 ms**  `threads.py:12`
            - `BaseEventLoop.run_in_executor` 
              wall **26.257 ms**  self **0.011 ms**  `base_events.py:815`
              - `ThreadPoolExecutor.submit` 
                wall **26.149 ms**  self **0.008 ms**  `thread.py:161`
                - `ThreadPoolExecutor._adjust_thread_count` 
                  wall **26.135 ms**  self **0.018 ms**  `thread.py:180`
                  - `Thread.start` 
                    wall **26.077 ms**  self **0.178 ms**  `threading.py:938`
                    - `Event.wait` 
                      wall **25.898 ms**  self **0.009 ms**  `threading.py:604`
                      - `Condition.wait` 
                        wall **25.885 ms**  self **25.880 ms**  `threading.py:288`
    - `LatentGuide.init_guides` 
      wall **24.573 ms**  self **3.892 ms**  `rk_guide_func_beta.py:125`
      - `pad` 
        wall **16.307 ms**  self **16.306 ms**  `functional.py:5761`
    _... 11 more children >= 1 ms omitted_
  - `_overlap_stage_call` 
    wall **98.154 ms**  self **0.009 ms**  `golden_serial.py:15533`
  - `_overlap_stage_call` 
    wall **26.637 ms**  self **0.006 ms**  `golden_serial.py:15533`

## `golden_sampler_tail`

- Stage wall: **0.073 ms**

_Nothing below the stage body reached the threshold._

## `golden_vae_decode`

- Stage wall: **919.729 ms**

- `golden_vae_decode` 
  wall **919.729 ms**  self **0.253 ms**  `full_execution_trace.py:330`
  - `golden_vae_decode` 
    wall **919.711 ms**  self **0.065 ms**  `golden_serial.py:14442`
    - `GoldenSerialRunner.run_closure` 
      wall **919.359 ms**  self **0.034 ms**  `golden_serial.py:9143`
      - `GoldenSerialRunner._execute_one` 
        wall **919.273 ms**  self **0.042 ms**  `golden_serial.py:8902`
        - `GoldenSerialRunner._call_node` 
          wall **918.925 ms**  self **0.022 ms**  `golden_serial.py:9035`
          - `VAEDecode.decode` 
            wall **918.732 ms**  self **0.031 ms**  `nodes.py:333`
            - `VAE.decode` 
              wall **918.701 ms**  self **837.815 ms**  `sd.py:1220`
              - `load_models_gpu` 
                wall **76.663 ms**  self **0.093 ms**  `model_management.py:909`
                - `LoadedModel.model_load` 
                  wall **72.188 ms**  self **0.019 ms**  `model_management.py:782`
                  - `LoadedModel.model_use_more_vram` 
                    wall **72.135 ms**  self **0.003 ms**  `model_management.py:817`
                    - `ModelPatcherDynamic.partially_load` 
                      wall **72.132 ms**  self **0.051 ms**  `model_patcher.py:2141`
                      - `ModelPatcherDynamic.load` 
                        wall **72.047 ms**  self **2.157 ms**  `model_patcher.py:1853`
                        - `ModelPatcher._load_list` 
                          wall **13.680 ms**  self **1.461 ms**  `model_patcher.py:945`
                        - `ModelPatcherDynamic.load.<locals>.force_load_param` 
                          wall **1.901 ms**  self **0.058 ms**  `model_patcher.py:1947`
                          - `ModelPatcher.patch_weight_to_device` 
                            wall **1.771 ms**  self **0.104 ms**  `model_patcher.py:899`
                            - `namedtuple` 
                              wall **1.397 ms**  self **1.395 ms**  `__init__.py:350`
                        - `Module.named_buffers` 
                          wall **1.132 ms**  self **0.004 ms**  `module.py:2754`
                          - `Module._named_members` 
                            wall **1.129 ms**  self **0.207 ms**  `module.py:2650`
                - `LoadedModel.model_memory_required` 
                  wall **2.112 ms**  self **0.004 ms**  `model_management.py:776`
                  - `LoadedModel.model_memory` 
                    wall **2.107 ms**  self **0.003 ms**  `model_management.py:767`
                    - `ModelPatcher.model_size` 
                      wall **2.104 ms**  self **0.053 ms**  `model_patcher.py:405`
                      - `module_size` 
                        wall **2.051 ms**  self **0.047 ms**  `model_management.py:631`
                        - `Module.state_dict` 
                          wall **2.005 ms**  self **0.022 ms**  `module.py:2199`
                - `free_memory` 
                  wall **1.285 ms**  self **0.081 ms**  `model_management.py:863`
              - `VAE.__init__.<locals>.<lambda>` 
                wall **2.893 ms**  self **2.893 ms**  `sd.py:506`
              - `ModelPatcher.get_free_memory` 
                wall **1.263 ms**  self **0.026 ms**  `model_patcher.py:417`
  - `golden.vae_decode.vae_decode_dependency_closure` 
    wall **919.388 ms**  self **919.388 ms**  `full_execution_trace.py:330`

## `golden_output`

- Stage wall: **228.576 ms**

- `golden_output` 
  wall **228.576 ms**  self **228.576 ms**  `full_execution_trace.py:330`
  - `golden_output` 
    wall **228.522 ms**  self **14.193 ms**  `golden_serial.py:14589`
    - `Image.save` 
      wall **188.281 ms**  self **0.060 ms**  `Image.py:2592`
      - `_save` 
        wall **176.133 ms**  self **0.049 ms**  `PngImagePlugin.py:1328`
        - `_save` 
          wall **176.049 ms**  self **0.021 ms**  `ImageFile.py:644`
          - `_encode_tile` 
            wall **176.024 ms**  self **171.970 ms**  `ImageFile.py:672`
      - `preinit` 
        wall **12.002 ms**  self **12.002 ms**  `Image.py:429`
    - `fromarray` 
      wall **13.303 ms**  self **8.298 ms**  `Image.py:3378`
      - `frombuffer` 
        wall **5.005 ms**  self **0.014 ms**  `Image.py:3288`
        - `frombytes` 
          wall **4.985 ms**  self **0.042 ms**  `Image.py:3242`
          - `new` 
            wall **3.858 ms**  self **3.811 ms**  `Image.py:3193`
          - `Image.frombytes` 
            wall **1.081 ms**  self **1.021 ms**  `Image.py:925`
    - `clip` 
      wall **8.315 ms**  self **0.016 ms**  `fromnumeric.py:2207`
      - `_wrapfunc` 
        wall **8.299 ms**  self **0.029 ms**  `fromnumeric.py:48`
        - `_clip` 
          wall **8.270 ms**  self **8.270 ms**  `_methods.py:96`
    - `__create_fn__.<locals>.__init__` 
      wall **2.283 ms**  self **0.014 ms**  `<string>:2`
      - `ReadyOutputArtifact.__post_init__` 
        wall **2.269 ms**  self **2.269 ms**  `output_durability.py:73`
    - `_ComfyAPIMixin._start_in_process_backend.<locals>._patched_logger_warning` 
      wall **1.311 ms**  self **0.008 ms**  `comfyapp.py:18431`
      - `Logger.warning` 
        wall **1.303 ms**  self **0.013 ms**  `__init__.py:1491`
        - `Logger._log` 
          wall **1.261 ms**  self **0.011 ms**  `__init__.py:1610`
