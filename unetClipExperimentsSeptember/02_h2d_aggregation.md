# September UNET/CLIP Experiment 02 - H2D Aggregation

PERFORMANCE_COMPARISON=NOT_PERFORMED

PERFORMANCE_VERDICT=NOT_PROVIDED

STATUS=COMPLETE

## Identity

* **worktree:** `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal`
* **branch:** `TESTING2`
* **head:** `f21b3ae29685abbc429813fadc32c8f41264c03e`
* **git_dirty:** `true`
* **tracked_diff_files:**
  * `.opencode/skills/comfymodal-golden-ops/SKILL.md`
  * `comfymodal_runtime/golden_qd_transport.py`
  * `comfymodal_runtime/golden_serial.py`
  * `tools/v2_control/cli.py`
* **tracked_diff_bytes:** `75249`
* **tracked_diff_sha256:** `42a3ac5936befa41815d35d0bf3810ab61cc606d762856c9f2849f8082238aec`
* **untracked_inventory:**
  * `EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md`
  * `RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md`
  * `RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md`
  * `unetClipExperimentsSeptember/`
* **experiment_id:** `sept-unetclip-02-h2d-aggregation`
* **app:** `sept-unetclip-02-h2d-aggregation`
* **profile:** `golden_p1`
* **class_name:** `ModalRuntimeEntrypointV2`
* **method:** `run_golden_serial_stream`
* **gpu:** `rtx-pro-6000`
* **deploy_fingerprint:** `e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003`
* **profile_config_fingerprint:** `1eede998372ead45dc188a02ba54703fdb6935cc4ba2c1d89e7cc8d348792192`
* **run_fingerprint:** `9b88f8f1b4664798d71a5b63f77150d2f1e4d2e239ea0e47b18a07cfcf55f639`
* **content_generation:** `b348b054f13097e01ccf32338a109beed3831695f1340b46fe20cf8de57cb2f9`
* **deployment_manifest:** `.v2ctl/deployments/deploy_20260903-192325_e5d2e9dd.json`
* **deployment_receipt:** `.v2ctl/deployments/receipt_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json`
* **raw_evidence_root:** `artifacts/phase_p1_serial_golden_v1`

### Effective environment

* `COMFYMODAL_GOLDEN_QD_TRANSPORT=static_e27`
* `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`
* `COMFYMODAL_V2_FULL_TRACE=1`
* `COMFYMODAL_V2_E27_FORENSICS=1`
* `COMFYMODAL_SAGE_RUNTIME_MODE=auto`
* `COMFYMODAL_OUTPUT_DURABILITY=off`
* `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1`
* `COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1`
* `COMFYMODAL_MINIMAL_RESTORE=1`
* `GPU=rtx-pro-6000 CPU=4 MEM=8192MiB min_containers=0 scaledown=4s`
* `attention_backend=pytorch`
* `runtime_overrides=0 (policy forbid)`

### SHA policies

* expected output SHA (profile/workload): `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
* skill-identity SHA: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`
* Current-bundle semantics retained; no new SHA gate was applied.

## Attempt ledger

All attempts are retained in manifest order; counted membership is taken from the manifest.

| attempt | role | classification | invocation ID | request ID | counted |
|---|---|---|---|---|---|
| attempt_0_gate_baseline | GATE_BASELINE_NOT_COUNTED | VALID_GATE_BASELINE_NOT_COUNTED | 0eb9fbaf1549419a835fdd689eac4c71 | golden-p1-0-d69ea315cdff | false |
| attempt_1_R1 | R1 | ELIGIBLE | b9a8c1e1bff24b0c92824ada2f63602e | golden-p1-0-73dce11b8837 | true |
| attempt_2_R2 | R2 | ELIGIBLE | 312ef85d8182403ca24771728c07bc7d | golden-p1-0-2fdfc8482ab9 | true |
| attempt_3_R3 | R3 | ELIGIBLE | 4aedca80ba2f43c9a9a24335bca6d02a | golden-p1-0-1076a5a3d7b1 | true |
| attempt_4_R4 | R4 | ELIGIBLE | 623420a8e42a48c6b16fc949450ee168 | golden-p1-0-f43d2cf4f96a | true |
| attempt_5_R5 | R5 | ELIGIBLE | 010460edcc47476fa4716becf9856678 | golden-p1-0-78c70a67ceef | true |

## Five-run performance schema

The counted cohort is `R1,R2,R3,R4,R5`.

## Consistency audit

These checks join only the explicit manifest rows and their explicitly named artifacts.

| check | result |
|---|---|
| declared counted cohort matches artifact rows | PASS |
| five counted artifacts loaded | PASS |
| request IDs match manifest bindings | PASS |
| authoritative summary deployment fingerprints match manifest | PASS |
| true_cold is true for every counted artifact | PASS |
| output SHA match is true for every counted artifact | PASS |
| authoritative summaries report valid=1 and invalid=0 | PASS |
| CLIP submitted/completed bytes reconcile | PASS |
| UNET submitted/completed bytes reconcile | PASS |
| VAE submitted/completed bytes reconcile | PASS |

The VAE R3 record is retained as `E27_SOURCE_MECHANISM_PROVEN=NO` with failed predicate `max_actual_source_inflight`; this is reported separately from the artifact validity/SHA checks.
The per-request `attempt_0.json` runtime identity hash is distinct from the authoritative deployment binding. Deployment identity checks use each explicit request `manifest.json`/`summary.json` binding, which matches the primary manifest; the raw distinction is not normalized away.

| stage | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| external_restore | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| request_setup | 1.399 | 1.733 | 1.900 | 2.134 | 2.518 | 1.399 | 2.518 | 1.119 | 1.937 | 1.900 | 0.421 | 0.217 |
| clip_load | 5228.279 | 5775.922 | 5297.842 | 5576.791 | 5541.903 | 5228.279 | 5775.922 | 547.644 | 5484.147 | 5541.903 | 222.053 | 0.040 |
| clip_forward | 1445.764 | 1449.110 | 1400.061 | 1467.976 | 1387.347 | 1387.347 | 1467.976 | 80.629 | 1430.052 | 1445.764 | 34.538 | 0.024 |
| unet_load | 7948.347 | 7967.142 | 7835.972 | 7736.126 | 7774.696 | 7736.126 | 7967.142 | 231.016 | 7852.457 | 7835.972 | 102.712 | 0.013 |
| sampler_prepare | 329.672 | 343.891 | 315.323 | 354.973 | 277.375 | 277.375 | 354.973 | 77.597 | 324.247 | 329.672 | 30.149 | 0.093 |
| vae_load | 119.683 | 111.634 | 107.737 | 110.536 | 111.752 | 107.737 | 119.683 | 11.947 | 112.268 | 111.634 | 4.449 | 0.040 |
| sampling | 5975.854 | 6172.790 | 6028.462 | 6079.811 | 5886.344 | 5886.344 | 6172.790 | 286.446 | 6028.652 | 6028.462 | 107.741 | 0.018 |
| sampler_tail | 0.011 | 0.012 | 0.012 | 0.013 | 0.012 | 0.011 | 0.013 | 0.002 | 0.012 | 0.012 | 0.001 | 0.048 |
| vae_decode | 530.724 | 515.152 | 529.002 | 533.639 | 528.797 | 515.152 | 533.639 | 18.488 | 527.463 | 529.002 | 7.150 | 0.014 |
| output | 162.576 | 161.874 | 163.368 | 162.832 | 168.664 | 161.874 | 168.664 | 6.790 | 163.863 | 162.832 | 2.737 | 0.017 |
| teardown | 0.323 | 0.518 | 0.315 | 0.300 | 0.303 | 0.300 | 0.518 | 0.218 | 0.352 | 0.315 | 0.093 | 0.266 |
| request_wall | 44846.518 | 45343.249 | 42786.811 | 45734.715 | 43102.912 | 42786.811 | 45734.715 | 2947.904 | 44362.841 | 44846.518 | 1336.831 | 0.030 |

### Combined loader wall

Derived per-request sum of the authoritative `clip_load + unet_load + vae_load` stage walls; it is not an end-to-end wall.

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| combined loader wall (ms) | 13296.309 | 13854.698 | 13241.550 | 13423.453 | 13428.351 | 13241.550 | 13854.698 | 613.148 | 13448.872 | 13423.453 | 240.842 | 0.018 |

## CLIP / UNET / VAE decomposition

Nested transport intervals explain the enclosing stage and are not added as independent walls.

### CLIP

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 4460.341 | 5006.080 | 4473.485 | 4769.510 | 4786.527 | 4460.341 | 5006.080 | 545.738 | 4699.189 | 4769.510 | 231.703 | 0.049 |
| syscall union | 2114.155 | 2150.730 | 2054.572 | 2250.617 | 2154.953 | 2054.572 | 2250.617 | 196.044 | 2145.006 | 2150.730 | 71.441 | 0.033 |
| source -> GPU ready | 4468.872 | 5014.740 | 4483.054 | 4777.225 | 4805.946 | 4468.872 | 5014.740 | 545.868 | 4709.967 | 4777.225 | 232.507 | 0.049 |
| H2D wall | 4403.938 | 4967.612 | 4413.454 | 4717.630 | 4751.622 | 4403.938 | 4967.612 | 563.674 | 4650.851 | 4717.630 | 240.975 | 0.052 |
| source/H2D overlap | 220.983 | 206.434 | 201.258 | 257.383 | 200.230 | 200.230 | 257.383 | 57.153 | 217.258 | 206.434 | 23.911 | 0.110 |
| post-source H2D tail | 8.531 | 8.660 | 9.568 | 7.714 | 19.419 | 7.714 | 19.419 | 11.705 | 10.779 | 8.660 | 4.875 | 0.452 |
| load-wall residual after source -> GPU ready | 759.407 | 761.183 | 814.788 | 799.566 | 735.956 | 735.956 | 814.788 | 78.832 | 774.180 | 761.183 | 32.178 | 0.042 |
| GPU active union | 190.086 | 178.187 | 174.214 | 199.133 | 175.616 | 174.214 | 199.133 | 24.919 | 183.447 | 178.187 | 10.775 | 0.059 |
| GPU stream span | 4403.926 | 4967.668 | 4413.281 | 4717.469 | 4751.077 | 4403.926 | 4967.668 | 563.742 | 4650.684 | 4717.469 | 240.971 | 0.052 |
| GPU idle inside span | 4213.840 | 4789.481 | 4239.067 | 4518.336 | 4575.460 | 4213.840 | 4789.481 | 575.641 | 4467.237 | 4518.336 | 242.093 | 0.054 |
| GPU active share (%) | 4.316 | 3.587 | 3.947 | 4.221 | 3.696 | 3.587 | 4.316 | 0.729 | 3.954 | 3.947 | 0.318 | 0.080 |
| GPU idle share (%) | 95.684 | 96.413 | 96.053 | 95.779 | 96.304 | 95.684 | 96.413 | 0.729 | 96.046 | 96.053 | 0.318 | 0.003 |
| H2D submissions | 237 | 237 | 239 | 238 | 237 | 237.000 | 239.000 | 2.000 | 237.600 | 237.000 | 0.894 | 0.004 |
| H2D completions | 237 | 237 | 239 | 238 | 237 | 237.000 | 239.000 | 2.000 | 237.600 | 237.000 | 0.894 | 0.004 |
| aggregated submissions | 6 | 6 | 4 | 5 | 6 | 4.000 | 6.000 | 2.000 | 5.400 | 6.000 | 0.894 | 0.166 |
| non-aggregated submissions | 231 | 231 | 235 | 233 | 231 | 231.000 | 235.000 | 4.000 | 232.200 | 231.000 | 1.789 | 0.008 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 227 | 227 | 231 | 229 | 227 | 227.000 | 231.000 | 4.000 | 228.200 | 227.000 | 1.789 | 0.008 |
| source reads | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192.000 | 8044936192.000 | 0.000 | 8044936192.000 | 8044936192.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |

### UNET

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 7566.240 | 7574.287 | 7456.924 | 7327.175 | 7403.950 | 7327.175 | 7574.287 | 247.112 | 7465.715 | 7456.924 | 106.041 | 0.014 |
| syscall union | 3130.915 | 3062.508 | 3099.858 | 3196.999 | 3157.694 | 3062.508 | 3196.999 | 134.491 | 3129.595 | 3130.915 | 51.768 | 0.017 |
| source -> GPU ready | 7574.795 | 7588.248 | 7464.357 | 7357.552 | 7407.175 | 7357.552 | 7588.248 | 230.696 | 7478.426 | 7464.357 | 101.529 | 0.014 |
| H2D wall | 7537.171 | 7540.271 | 7454.292 | 7303.449 | 7345.502 | 7303.449 | 7540.271 | 236.822 | 7436.137 | 7454.292 | 108.630 | 0.015 |
| source/H2D overlap | 365.941 | 368.241 | 351.251 | 354.576 | 329.827 | 329.827 | 368.241 | 38.415 | 353.967 | 354.576 | 15.310 | 0.043 |
| post-source H2D tail | 8.556 | 13.961 | 7.433 | 30.377 | 3.225 | 3.225 | 30.377 | 27.152 | 12.710 | 8.556 | 10.592 | 0.833 |
| load-wall residual after source -> GPU ready | 373.552 | 378.894 | 371.615 | 378.573 | 367.521 | 367.521 | 378.894 | 11.373 | 374.031 | 373.552 | 4.815 | 0.013 |
| GPU active union | 297.927 | 302.832 | 309.041 | 304.931 | 286.889 | 286.889 | 309.041 | 22.152 | 300.324 | 302.832 | 8.511 | 0.028 |
| GPU stream span | 7537.246 | 7540.267 | 7454.303 | 7303.430 | 7345.567 | 7303.430 | 7540.267 | 236.837 | 7436.162 | 7454.303 | 108.639 | 0.015 |
| GPU idle inside span | 7239.318 | 7237.434 | 7145.261 | 6998.499 | 7058.678 | 6998.499 | 7239.318 | 240.820 | 7135.838 | 7145.261 | 107.162 | 0.015 |
| GPU active share (%) | 3.953 | 4.016 | 4.146 | 4.175 | 3.906 | 3.906 | 4.175 | 0.270 | 4.039 | 4.016 | 0.118 | 0.029 |
| GPU idle share (%) | 96.047 | 95.984 | 95.854 | 95.825 | 96.094 | 95.825 | 96.094 | 0.270 | 95.961 | 95.984 | 0.118 | 0.001 |
| H2D submissions | 367 | 361 | 364 | 360 | 365 | 360.000 | 367.000 | 7.000 | 363.400 | 364.000 | 2.881 | 0.008 |
| H2D completions | 367 | 361 | 364 | 360 | 365 | 360.000 | 367.000 | 7.000 | 363.400 | 364.000 | 2.881 | 0.008 |
| aggregated submissions | 3 | 8 | 6 | 10 | 5 | 3.000 | 10.000 | 7.000 | 6.400 | 6.000 | 2.702 | 0.422 |
| non-aggregated submissions | 364 | 353 | 358 | 350 | 360 | 350.000 | 364.000 | 14.000 | 357.000 | 358.000 | 5.568 | 0.016 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 360 | 349 | 353 | 346 | 356 | 346.000 | 360.000 | 14.000 | 352.800 | 353.000 | 5.541 | 0.016 |
| source reads | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472.000 | 12309817472.000 | 0.000 | 12309817472.000 | 12309817472.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |

### VAE

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 69.792 | 57.537 | 58.943 | 48.135 | 58.083 | 48.135 | 69.792 | 21.657 | 58.498 | 58.083 | 7.685 | 0.131 |
| syscall union | 67.303 | 55.846 | 56.733 | 47.130 | 54.408 | 47.130 | 67.303 | 20.173 | 56.284 | 55.846 | 7.230 | 0.128 |
| source -> GPU ready | 72.297 | 60.826 | 61.743 | 50.377 | 58.891 | 50.377 | 72.297 | 21.921 | 60.827 | 60.826 | 7.832 | 0.129 |
| H2D wall | 62.315 | 46.510 | 52.874 | 43.654 | 49.338 | 43.654 | 62.315 | 18.661 | 50.938 | 49.338 | 7.218 | 0.142 |
| source/H2D overlap | 30.049 | 33.536 | 41.887 | 16.108 | 20.363 | 16.108 | 41.887 | 25.778 | 28.389 | 30.049 | 10.328 | 0.364 |
| post-source H2D tail | 2.505 | 3.289 | 2.801 | 2.242 | 0.808 | 0.808 | 3.289 | 2.481 | 2.329 | 2.505 | 0.935 | 0.401 |
| load-wall residual after source -> GPU ready | 47.386 | 50.808 | 45.993 | 60.159 | 52.862 | 45.993 | 60.159 | 14.166 | 51.442 | 50.808 | 5.580 | 0.108 |
| GPU active union | 27.823 | 21.581 | 26.413 | 7.644 | 15.646 | 7.644 | 27.823 | 20.180 | 19.822 | 21.581 | 8.311 | 0.419 |
| GPU stream span | 62.435 | 46.517 | 52.717 | 43.674 | 49.336 | 43.674 | 62.435 | 18.761 | 50.936 | 49.336 | 7.250 | 0.142 |
| GPU idle inside span | 34.612 | 24.936 | 26.304 | 36.030 | 33.689 | 24.936 | 36.030 | 11.095 | 31.114 | 33.689 | 5.107 | 0.164 |
| GPU active share (%) | 44.564 | 46.394 | 50.103 | 17.502 | 31.714 | 17.502 | 50.103 | 32.601 | 38.055 | 44.564 | 13.414 | 0.352 |
| GPU idle share (%) | 55.436 | 53.606 | 49.897 | 82.498 | 68.286 | 49.897 | 82.498 | 32.601 | 61.945 | 55.436 | 13.414 | 0.217 |
| H2D submissions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| H2D completions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| aggregated submissions | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| non-aggregated submissions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 0 | 0 | 2 | 0 | 0 | 0.000 | 2.000 | 2.000 | 0.400 | 0.000 | 0.894 | 2.236 |
| source reads | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 335278732 | 335278732 | 335278732 | 335278732 | 335278732 | 335278732.000 | 335278732.000 | 0.000 | 335278732.000 | 335278732.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 2 | 4 | 4 | 2.000 | 4.000 | 2.000 | 3.600 | 4.000 | 0.894 | 0.248 |

### CLIP header, staging, and proof

| metric | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| header parse count | 1 | 1 | 1 | 1 | 1 |
| source block count | 243 | 243 | 243 | 243 | 243 |
| source block bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| arena bytes | 268435456 | 268435456 | 268435456 | 268435456 | 268435456 |
| logical slot count | 8 | 8 | 8 | 8 | 8 |
| logical slot bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| request pinned allocation count | 1 | 1 | 1 | 1 | 1 |
| transport pinned allocation count | 1 | 1 | 1 | 1 | 1 |
| adoption result | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption |
| post-transport construction adoption | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} |
| E27 source mechanism proven | YES | YES | YES | YES | YES |
| E27 failed predicates | [] | [] | [] | [] | [] |

Future transport fields not emitted by the authoritative artifacts remain `UNAVAILABLE`.

### UNET header, staging, and proof

| metric | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| header parse count | 1 | 1 | 1 | 1 | 1 |
| source block count | 370 | 370 | 370 | 370 | 370 |
| source block bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| arena bytes | 268435456 | 268435456 | 268435456 | 268435456 | 268435456 |
| logical slot count | 8 | 8 | 8 | 8 | 8 |
| logical slot bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| request pinned allocation count | 1 | 1 | 1 | 1 | 1 |
| transport pinned allocation count | 0 | 0 | 0 | 0 | 0 |
| adoption result | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption |
| post-transport construction adoption | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} |
| E27 source mechanism proven | YES | YES | YES | YES | YES |
| E27 failed predicates | [] | [] | [] | [] | [] |

Future transport fields not emitted by the authoritative artifacts remain `UNAVAILABLE`.

### VAE header, staging, and proof

| metric | R1 | R2 | R3 | R4 | R5 |
|---|---|---|---|---|---|
| header parse count | 1 | 1 | 1 | 1 | 1 |
| source block count | 13 | 13 | 13 | 13 | 13 |
| source block bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| arena bytes | 268435456 | 268435456 | 268435456 | 268435456 | 268435456 |
| logical slot count | 8 | 8 | 8 | 8 | 8 |
| logical slot bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 |
| request pinned allocation count | 1 | 1 | 1 | 1 | 1 |
| transport pinned allocation count | 0 | 0 | 0 | 0 | 0 |
| adoption result | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption | backing_owner_retained_for_adoption |
| post-transport construction adoption | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} | {"reason":"outside the dispatcher transport/read boundary","status":"NOT RUN"} |
| E27 source mechanism proven | YES | YES | NO | YES | YES |
| E27 failed predicates | [] | [] | ["max_actual_source_inflight"] | [] | [] |

Future transport fields not emitted by the authoritative artifacts remain `UNAVAILABLE`.

## Resource and correctness invariants

| role | arena alloc count | arena bytes | logical slots | slot bytes | event objects | event rerecords | fresh event/copy | duplicate reads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 459.200 | 0.000 | 0.000 |
| UNET | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 1186.000 | 0.000 | 0.000 |
| VAE | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 1212.000 | 0.000 | 0.000 |

Correctness and identity observations are per-request, not means:

* `R1`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R2`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R3`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R4`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R5`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
## Transport evidence by request

These rows preserve the raw per-request distinctions that are lost in cohort means.

### R1

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {"canonical_extent_not_ready_queue_full":75,"canonical_slot_assignment_failed":15,"partial_extent":6,"physical_slots_not_consecutive":131} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {"canonical_extent_not_ready_queue_full":138,"canonical_slot_assignment_failed":8,"partial_extent":6,"physical_slots_not_consecutive":208} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation fallback detail

| role | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---:|
| CLIP | {"canonical_extent_not_ready_queue_full":75,"canonical_slot_assignment_failed":15,"partial_extent":6,"physical_slots_not_consecutive":131} | UNAVAILABLE | 0.698 | 2.207 | 4 |
| UNET | {"canonical_extent_not_ready_queue_full":138,"canonical_slot_assignment_failed":8,"partial_extent":6,"physical_slots_not_consecutive":208} | UNAVAILABLE | 0.613 | 2.232 | 4 |
| VAE | {} | UNAVAILABLE | 2.177 | 30.237 | 4 |

### R2

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {"canonical_extent_not_ready_queue_full":86,"canonical_slot_assignment_failed":16,"partial_extent":6,"physical_slots_not_consecutive":119} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {"canonical_extent_not_ready_queue_full":128,"canonical_slot_assignment_failed":21,"partial_extent":6,"physical_slots_not_consecutive":194} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation fallback detail

| role | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---:|
| CLIP | {"canonical_extent_not_ready_queue_full":86,"canonical_slot_assignment_failed":16,"partial_extent":6,"physical_slots_not_consecutive":119} | UNAVAILABLE | 0.635 | 2.149 | 4 |
| UNET | {"canonical_extent_not_ready_queue_full":128,"canonical_slot_assignment_failed":21,"partial_extent":6,"physical_slots_not_consecutive":194} | UNAVAILABLE | 0.586 | 2.325 | 4 |
| VAE | {} | UNAVAILABLE | 2.136 | 2.262 | 4 |

### R3

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {"canonical_extent_not_ready_queue_full":80,"canonical_slot_assignment_failed":13,"partial_extent":6,"physical_slots_not_consecutive":132} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {"canonical_extent_not_ready_queue_full":126,"canonical_slot_assignment_failed":17,"partial_extent":6,"physical_slots_not_consecutive":204} | backing_owner_retained_for_adoption | true | true |
| VAE | NO | {"partial_extent":2} | backing_owner_retained_for_adoption | true | true |

#### Aggregation fallback detail

| role | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---:|
| CLIP | {"canonical_extent_not_ready_queue_full":80,"canonical_slot_assignment_failed":13,"partial_extent":6,"physical_slots_not_consecutive":132} | UNAVAILABLE | 0.655 | 2.109 | 4 |
| UNET | {"canonical_extent_not_ready_queue_full":126,"canonical_slot_assignment_failed":17,"partial_extent":6,"physical_slots_not_consecutive":204} | UNAVAILABLE | 0.604 | 2.252 | 4 |
| VAE | {"partial_extent":2} | UNAVAILABLE | 1.426 | 0.000 | 4 |

### R4

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {"canonical_extent_not_ready_queue_full":81,"canonical_slot_assignment_failed":8,"partial_extent":6,"physical_slots_not_consecutive":134} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {"canonical_extent_not_ready_queue_full":127,"canonical_slot_assignment_failed":13,"partial_extent":5,"physical_slots_not_consecutive":201} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation fallback detail

| role | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---:|
| CLIP | {"canonical_extent_not_ready_queue_full":81,"canonical_slot_assignment_failed":8,"partial_extent":6,"physical_slots_not_consecutive":134} | UNAVAILABLE | 0.699 | 3.102 | 4 |
| UNET | {"canonical_extent_not_ready_queue_full":127,"canonical_slot_assignment_failed":13,"partial_extent":5,"physical_slots_not_consecutive":201} | UNAVAILABLE | 0.611 | 1.831 | 4 |
| VAE | {} | UNAVAILABLE | 3.245 | 66.919 | 4 |

### R5

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {"canonical_extent_not_ready_queue_full":81,"canonical_slot_assignment_failed":16,"partial_extent":7,"physical_slots_not_consecutive":123} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {"canonical_extent_not_ready_queue_full":129,"canonical_slot_assignment_failed":20,"partial_extent":5,"physical_slots_not_consecutive":202} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation fallback detail

| role | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---:|
| CLIP | {"canonical_extent_not_ready_queue_full":81,"canonical_slot_assignment_failed":16,"partial_extent":7,"physical_slots_not_consecutive":123} | UNAVAILABLE | 0.641 | 1.533 | 4 |
| UNET | {"canonical_extent_not_ready_queue_full":129,"canonical_slot_assignment_failed":20,"partial_extent":5,"physical_slots_not_consecutive":202} | UNAVAILABLE | 0.625 | 2.123 | 4 |
| VAE | {} | UNAVAILABLE | 2.328 | 29.223 | 4 |

## Experiment 01 reference

This is a descriptive reference comparison only. The required top-level performance flags remain NOT_PERFORMED/NOT_PROVIDED.

Reference manifest: `unetClipExperimentsSeptember/exp01_manifest.json`
Reference counted cohort: `R1,R3,R4,R7,R8`

| cohort | n | loader wall mean (ms) | loader wall median (ms) | request wall mean (ms) | request wall median (ms) |
|---|---:|---:|---:|---:|---:|
| Experiment 01 | 5 | 3976.932 | 3898.792 | 71601.178 | 43586.186 |
| Experiment 02 | 5 | 13448.872 | 13423.453 | 44362.841 | 44846.518 |

### Stage mean reference

| stage | Experiment 01 mean (ms) | Experiment 02 mean (ms) | descriptive delta (ms) |
|---|---:|---:|---:|
| external_restore | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| request_setup | 1.676 | 1.937 | 0.261 |
| clip_load | 1832.673 | 5484.147 | 3651.474 |
| clip_forward | 1456.403 | 1430.052 | -26.352 |
| unet_load | 2017.092 | 7852.457 | 5835.364 |
| sampler_prepare | 342.132 | 324.247 | -17.885 |
| vae_load | 127.167 | 112.268 | -14.898 |
| sampling | 5956.381 | 6028.652 | 72.271 |
| sampler_tail | 0.012 | 0.012 | -0.000 |
| vae_decode | 523.651 | 527.463 | 3.812 |
| output | 161.992 | 163.863 | 1.871 |
| teardown | 0.293 | 0.352 | 0.059 |
| request_wall | 71601.178 | 44362.841 | -27238.337 |

### Transport reference

Only fields present in both explicit artifact cohorts are shown; missing Experiment 01 aggregation counters remain `UNAVAILABLE`.

| role | metric | Experiment 01 mean | Experiment 02 mean | descriptive delta (%) |
|---|---|---:|---:|---:|
| CLIP | source wall | 1047.619 | 4699.189 | 348.559 |
| CLIP | syscall union | 1039.290 | 2145.006 | 106.391 |
| CLIP | source -> GPU ready | 1049.571 | 4709.967 | 348.751 |
| CLIP | H2D wall | 1038.608 | 4650.851 | 347.797 |
| CLIP | source/H2D overlap | 454.859 | 217.258 | -52.236 |
| CLIP | post-source H2D tail | 1.952 | 10.779 | 452.071 |
| CLIP | H2D submissions | 243.000 | 237.600 | -2.222 |
| UNET | source wall | 1644.716 | 7465.715 | 353.921 |
| UNET | syscall union | 1623.352 | 3129.595 | 92.786 |
| UNET | source -> GPU ready | 1646.433 | 7478.426 | 354.220 |
| UNET | H2D wall | 1634.149 | 7436.137 | 355.046 |
| UNET | source/H2D overlap | 752.514 | 353.967 | -52.962 |
| UNET | post-source H2D tail | 1.718 | 12.710 | 640.021 |
| UNET | H2D submissions | 613.000 | 363.400 | -40.718 |
| VAE | source wall | 67.007 | 58.498 | -12.698 |
| VAE | syscall union | 64.694 | 56.284 | -13.000 |
| VAE | source -> GPU ready | 70.611 | 60.827 | -13.856 |
| VAE | H2D wall | 56.737 | 50.938 | -10.221 |
| VAE | source/H2D overlap | 35.284 | 28.389 | -19.542 |
| VAE | post-source H2D tail | 3.604 | 2.329 | -35.382 |
| VAE | H2D submissions | 626.000 | 13.000 | -97.923 |

## Per-attempt appendices

### attempt_0_gate_baseline

role=`GATE_BASELINE_NOT_COUNTED` classification=`VALID_GATE_BASELINE_NOT_COUNTED`
invocation_id=`0eb9fbaf1549419a835fdd689eac4c71` request_id=`golden-p1-0-d69ea315cdff`

#### Available stage/invariant values

* `duration_ms`: `45384.526`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `10.247`
* stage `request_setup` wall ms: `1.173`
* stage `clip_load` wall ms: `5824.685`
* stage `clip_forward` wall ms: `1706.811`
* stage `unet_load` wall ms: `8078.362`
* stage `sampler_prepare` wall ms: `321.964`
* stage `vae_load` wall ms: `146.232`
* stage `sampling` wall ms: `6162.511`
* stage `sampler_tail` wall ms: `0.013`
* stage `vae_decode` wall ms: `570.682`
* stage `output` wall ms: `164.677`
* stage `teardown` wall ms: `0.299`

#### attempt_0_gate_baseline / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_0_gate_baseline / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_0_gate_baseline / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-24-41_1c6414/manifest.json` — 20643104 bytes, sha256 `08fd921cb078c494cf4dd6c5aa88a926a9bf98ff552437db0df7b19196323d18`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20643104 sha256=08fd921cb078c494cf4dd6c5aa88a926a9bf98ff552437db0df7b19196323d18

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_0_gate_baseline / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-24-41_1c6414/attempt_0.json` — 18738157 bytes, sha256 `3eacc88ceb85c9a9b1e57029c72d939de823b3f4fe4f77e909c62d995717ef87`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18738157 sha256=3eacc88ceb85c9a9b1e57029c72d939de823b3f4fe4f77e909c62d995717ef87

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MWVC7756E398TYQJT6NECR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MWVC7756E398TYQJT6NECR",
      "pid": "2",
      "post_restore_nonce": "d093db505e2b4f1ca028abd01c651ab7",
      "restore_session_id": "9cdbb5f742b540c286991e2081d9d765",
      "restored_instance_id": "8edf3ac4c11c429bafc7efe69ebb24af"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MWVC7756E398TYQJT6NECR",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MWVBS34T4WPCBAVRN4B1MQ:1788481482531-0",
    "modal_task_id": "ta-01M1MWVC7756E398TYQJT6NECR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "d093db505e2b4f1ca028abd01c651ab7",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-d69ea315cdff",
    "restore_count": 1,
    "restore_session_id": "9cdbb5f742b540c286991e2081d9d765",
    "restored_instance_id": "8edf3ac4c11c429bafc7efe69ebb24af",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_0_gate_baseline / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-24-41_1c6414/summary.json` — 20642792 bytes, sha256 `45dffd936a311371b5bb55ee012aa558d88fdc6c2350393568a412edcd763db4`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20642792 sha256=45dffd936a311371b5bb55ee012aa558d88fdc6c2350393568a412edcd763db4

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_0_gate_baseline / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-24-41_1c6414/attempt_0_events.json` — 29532338 bytes, sha256 `78a383a9855dc1e781182814dbbb776d5400aea447c8eab39722a2634db0ebf9`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29532338 sha256=78a383a9855dc1e781182814dbbb776d5400aea447c8eab39722a2634db0ebf9
text_omitted=true]
```

#### attempt_0_gate_baseline / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_gate_baseline / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

### attempt_1_R1

role=`R1` classification=`ELIGIBLE`
invocation_id=`b9a8c1e1bff24b0c92824ada2f63602e` request_id=`golden-p1-0-73dce11b8837`

#### Available stage/invariant values

* `duration_ms`: `44846.518`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `10.082`
* stage `request_setup` wall ms: `1.399`
* stage `clip_load` wall ms: `5228.279`
* stage `clip_forward` wall ms: `1445.764`
* stage `unet_load` wall ms: `7948.347`
* stage `sampler_prepare` wall ms: `329.672`
* stage `vae_load` wall ms: `119.683`
* stage `sampling` wall ms: `5975.854`
* stage `sampler_tail` wall ms: `0.011`
* stage `vae_decode` wall ms: `530.724`
* stage `output` wall ms: `162.576`
* stage `teardown` wall ms: `0.323`

#### attempt_1_R1 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_1_R1 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_1_R1 / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-29-33_a6dbd3/manifest.json` — 20725164 bytes, sha256 `f1a18d5cc5fca6b5973057a52135ca7d80c745c3c1a5d077d1ff398e7cc6bb43`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20725164 sha256=f1a18d5cc5fca6b5973057a52135ca7d80c745c3c1a5d077d1ff398e7cc6bb43

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_1_R1 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-29-33_a6dbd3/attempt_0.json` — 18818969 bytes, sha256 `3274c0423b55b780a9737e0b4442a687b98b1ac0d559b23359817f8a0af8aaec`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18818969 sha256=3274c0423b55b780a9737e0b4442a687b98b1ac0d559b23359817f8a0af8aaec

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MX4A97WZFTHQD6CQT9RBSR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MX4A97WZFTHQD6CQT9RBSR",
      "pid": "2",
      "post_restore_nonce": "9c312d90132440118eece1e07527deb1",
      "restore_session_id": "920873158111496e9faf0f4a1583b497",
      "restored_instance_id": "a650207a860645cda5043050e290e507"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MX4A97WZFTHQD6CQT9RBSR",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MX48QB8YP2ZHKHPS6F4VQ8:1788481774316-0",
    "modal_task_id": "ta-01M1MX4A97WZFTHQD6CQT9RBSR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "9c312d90132440118eece1e07527deb1",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-73dce11b8837",
    "restore_count": 1,
    "restore_session_id": "920873158111496e9faf0f4a1583b497",
    "restored_instance_id": "a650207a860645cda5043050e290e507",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_1_R1 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-29-33_a6dbd3/summary.json` — 20724852 bytes, sha256 `39d2b05edcf9c177f61a4c31e3fae882ff33c1c427257825c5ee6b6f34d2101f`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20724852 sha256=39d2b05edcf9c177f61a4c31e3fae882ff33c1c427257825c5ee6b6f34d2101f

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_1_R1 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-29-33_a6dbd3/attempt_0_events.json` — 29614410 bytes, sha256 `7b32b125e02d1f13f652275c2365e88f0d232e8a6c147071f190f5cf11708bc7`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29614410 sha256=7b32b125e02d1f13f652275c2365e88f0d232e8a6c147071f190f5cf11708bc7
text_omitted=true]
```

#### attempt_1_R1 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_R1 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

### attempt_2_R2

role=`R2` classification=`ELIGIBLE`
invocation_id=`312ef85d8182403ca24771728c07bc7d` request_id=`golden-p1-0-2fdfc8482ab9`

#### Available stage/invariant values

* `duration_ms`: `45343.249`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `10.695`
* stage `request_setup` wall ms: `1.733`
* stage `clip_load` wall ms: `5775.922`
* stage `clip_forward` wall ms: `1449.110`
* stage `unet_load` wall ms: `7967.142`
* stage `sampler_prepare` wall ms: `343.891`
* stage `vae_load` wall ms: `111.634`
* stage `sampling` wall ms: `6172.790`
* stage `sampler_tail` wall ms: `0.012`
* stage `vae_decode` wall ms: `515.152`
* stage `output` wall ms: `161.874`
* stage `teardown` wall ms: `0.518`

#### attempt_2_R2 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_2_R2 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_2_R2 / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-30-28_28d69a/manifest.json` — 20712571 bytes, sha256 `dd5d401fa2ab991e870372bde37478efe9d228d5b52dc470f33f3df5e64fa952`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20712571 sha256=dd5d401fa2ab991e870372bde37478efe9d228d5b52dc470f33f3df5e64fa952

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_2_R2 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-30-28_28d69a/attempt_0.json` — 18807744 bytes, sha256 `40f36af9863efce9eab0710cecd1bbb74751ba50c9116908e4486f31ecc406b1`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18807744 sha256=40f36af9863efce9eab0710cecd1bbb74751ba50c9116908e4486f31ecc406b1

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MX5Z317WNWXKQ8XEPVFB5R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MX5Z317WNWXKQ8XEPVFB5R",
      "pid": "2",
      "post_restore_nonce": "b0817c4b3caa4ecb846bdc352b534de4",
      "restore_session_id": "bcda823af3b241d993a5a78d963c1ae9",
      "restored_instance_id": "1a85533c1a964af28719a10d8f66f531"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MX5Z317WNWXKQ8XEPVFB5R",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MX5YP3E4CB0VWNQT13T1SZ:1788481829571-0",
    "modal_task_id": "ta-01M1MX5Z317WNWXKQ8XEPVFB5R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "b0817c4b3caa4ecb846bdc352b534de4",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-2fdfc8482ab9",
    "restore_count": 1,
    "restore_session_id": "bcda823af3b241d993a5a78d963c1ae9",
    "restored_instance_id": "1a85533c1a964af28719a10d8f66f531",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_2_R2 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-30-28_28d69a/summary.json` — 20712259 bytes, sha256 `9c42049d90d53c5c5d87ca869d68f0521a9d5b0d40879a4f845bbb620be8ee49`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20712259 sha256=9c42049d90d53c5c5d87ca869d68f0521a9d5b0d40879a4f845bbb620be8ee49

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_2_R2 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-30-28_28d69a/attempt_0_events.json` — 29601816 bytes, sha256 `daca1c23b1a6722d3eb6a20f3faa2519f3d13460c0891c3358339e7403f6e316`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29601816 sha256=daca1c23b1a6722d3eb6a20f3faa2519f3d13460c0891c3358339e7403f6e316
text_omitted=true]
```

#### attempt_2_R2 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R2 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

### attempt_3_R3

role=`R3` classification=`ELIGIBLE`
invocation_id=`4aedca80ba2f43c9a9a24335bca6d02a` request_id=`golden-p1-0-1076a5a3d7b1`

#### Available stage/invariant values

* `duration_ms`: `42786.811`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `10.714`
* stage `request_setup` wall ms: `1.900`
* stage `clip_load` wall ms: `5297.842`
* stage `clip_forward` wall ms: `1400.061`
* stage `unet_load` wall ms: `7835.972`
* stage `sampler_prepare` wall ms: `315.323`
* stage `vae_load` wall ms: `107.737`
* stage `sampling` wall ms: `6028.462`
* stage `sampler_tail` wall ms: `0.012`
* stage `vae_decode` wall ms: `529.002`
* stage `output` wall ms: `163.368`
* stage `teardown` wall ms: `0.315`

#### attempt_3_R3 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_3_R3 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_3_R3 / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-31-23_0e05c7/manifest.json` — 20705733 bytes, sha256 `730b61121af974f1abcbda49d52a624af8f0fe3e83c094637052ffd563c84f24`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20705733 sha256=730b61121af974f1abcbda49d52a624af8f0fe3e83c094637052ffd563c84f24

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_3_R3 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-31-23_0e05c7/attempt_0.json` — 18801474 bytes, sha256 `207dbfc02a8672908fc5599285c2749c195a5b3ab8d8a1662701cbdf5c43790b`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18801474 sha256=207dbfc02a8672908fc5599285c2749c195a5b3ab8d8a1662701cbdf5c43790b

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MX7MSZWF73H6GCXF8QEQ2R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MX7MSZWF73H6GCXF8QEQ2R",
      "pid": "2",
      "post_restore_nonce": "81bf58eb4d954007b339a731fec03a65",
      "restore_session_id": "131522d625cc4aeda4b69b2194ad158a",
      "restored_instance_id": "baa20f062640453395470a30b1ea564b"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MX7MSZWF73H6GCXF8QEQ2R",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MX7MBNXKFP3XEGVE474V02:1788481884534-0",
    "modal_task_id": "ta-01M1MX7MSZWF73H6GCXF8QEQ2R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "81bf58eb4d954007b339a731fec03a65",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-1076a5a3d7b1",
    "restore_count": 1,
    "restore_session_id": "131522d625cc4aeda4b69b2194ad158a",
    "restored_instance_id": "baa20f062640453395470a30b1ea564b",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_3_R3 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-31-23_0e05c7/summary.json` — 20705421 bytes, sha256 `a3a9e44502c81830c9858319ceb491e55c0fa4f04d01036a0c45b7ded75dc32d`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20705421 sha256=a3a9e44502c81830c9858319ceb491e55c0fa4f04d01036a0c45b7ded75dc32d

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_3_R3 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-31-23_0e05c7/attempt_0_events.json` — 29594982 bytes, sha256 `7577bc4a9ba371971912f26613eeacd59da962fe753c82484cad2293377ac1f1`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29594982 sha256=7577bc4a9ba371971912f26613eeacd59da962fe753c82484cad2293377ac1f1
text_omitted=true]
```

#### attempt_3_R3 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R3 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

### attempt_4_R4

role=`R4` classification=`ELIGIBLE`
invocation_id=`623420a8e42a48c6b16fc949450ee168` request_id=`golden-p1-0-f43d2cf4f96a`

#### Available stage/invariant values

* `duration_ms`: `45734.715`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `12.143`
* stage `request_setup` wall ms: `2.134`
* stage `clip_load` wall ms: `5576.791`
* stage `clip_forward` wall ms: `1467.976`
* stage `unet_load` wall ms: `7736.126`
* stage `sampler_prepare` wall ms: `354.973`
* stage `vae_load` wall ms: `110.536`
* stage `sampling` wall ms: `6079.811`
* stage `sampler_tail` wall ms: `0.013`
* stage `vae_decode` wall ms: `533.639`
* stage `output` wall ms: `162.832`
* stage `teardown` wall ms: `0.300`

#### attempt_4_R4 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_4_R4 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_4_R4 / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-32-15_68dc46/manifest.json` — 20700504 bytes, sha256 `b0e22643abb4353d08ec906370bfcac3a6f5f50df3f5368bd70e2a92de8a2a29`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20700504 sha256=b0e22643abb4353d08ec906370bfcac3a6f5f50df3f5368bd70e2a92de8a2a29

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_4_R4 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-32-15_68dc46/attempt_0.json` — 18796829 bytes, sha256 `471b4f02dd5d7e5f26f97cc9afc561db2660422096d0a9c5377c536b7a232742`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18796829 sha256=471b4f02dd5d7e5f26f97cc9afc561db2660422096d0a9c5377c536b7a232742

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MX98YFQAYHA19WZYKQ53FR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MX98YFQAYHA19WZYKQ53FR",
      "pid": "2",
      "post_restore_nonce": "53e5d669535b429091a8146aaea602a6",
      "restore_session_id": "4eba4a79415c415fbc907219538c8c8e",
      "restored_instance_id": "6b686b6efe8e4d00be3be1651115d1f8"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MX98YFQAYHA19WZYKQ53FR",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MX97A27SDY7BRDF1TKH5JE:1788481936706-0",
    "modal_task_id": "ta-01M1MX98YFQAYHA19WZYKQ53FR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "53e5d669535b429091a8146aaea602a6",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-f43d2cf4f96a",
    "restore_count": 1,
    "restore_session_id": "4eba4a79415c415fbc907219538c8c8e",
    "restored_instance_id": "6b686b6efe8e4d00be3be1651115d1f8",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_4_R4 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-32-15_68dc46/summary.json` — 20700192 bytes, sha256 `705d63a8c9848fc2c3608f73f9fa712dc72fc21023931bf85d2c0df23b31a614`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20700192 sha256=705d63a8c9848fc2c3608f73f9fa712dc72fc21023931bf85d2c0df23b31a614

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_4_R4 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-32-15_68dc46/attempt_0_events.json` — 29589750 bytes, sha256 `7e2ef4f54d90645beaba6799a0990be12e5ab25345cebda01718a15170d512d4`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29589750 sha256=7e2ef4f54d90645beaba6799a0990be12e5ab25345cebda01718a15170d512d4
text_omitted=true]
```

#### attempt_4_R4 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R4 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

### attempt_5_R5

role=`R5` classification=`ELIGIBLE`
invocation_id=`010460edcc47476fa4716becf9856678` request_id=`golden-p1-0-78c70a67ceef`

#### Available stage/invariant values

* `duration_ms`: `43102.912`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `10.400`
* stage `request_setup` wall ms: `2.518`
* stage `clip_load` wall ms: `5541.903`
* stage `clip_forward` wall ms: `1387.347`
* stage `unet_load` wall ms: `7774.696`
* stage `sampler_prepare` wall ms: `277.375`
* stage `vae_load` wall ms: `111.752`
* stage `sampling` wall ms: `5886.344`
* stage `sampler_tail` wall ms: `0.012`
* stage `vae_decode` wall ms: `528.797`
* stage `output` wall ms: `168.664`
* stage `teardown` wall ms: `0.303`

#### attempt_5_R5 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / source-probe stdout

Path: `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes, sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`.

```text
{"classification":{"ledger_enabled":true,"ledger_flag":"COMFYMODAL_V2_CRITICAL_PATH_LEDGER","ledger_record_event":true,"modules":[{"expected_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","module":"comfymodal_runtime/modal_app.py","remote_path":"/root/comfymodal_runtime/modal_app.py","remote_sha":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","verdict":"MATCH"},{"expected_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","module":"comfymodal_runtime/critical_path_ledger.py","remote_path":"/root/comfymodal_runtime/critical_path_ledger.py","remote_sha":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","verdict":"MATCH"},{"expected_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","module":"comfymodal_runtime/runtime_bootstrap.py","remote_path":"/root/comfymodal_runtime/runtime_bootstrap.py","remote_sha":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","verdict":"MATCH"},{"expected_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","module":"comfymodal_runtime/runtime_executor.py","remote_path":"/root/comfymodal_runtime/runtime_executor.py","remote_sha":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","verdict":"MATCH"},{"expected_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","module":"comfymodal_runtime/gantt_telemetry.py","remote_path":"/root/comfymodal_runtime/gantt_telemetry.py","remote_sha":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","verdict":"MATCH"},{"expected_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","module":"comfymodal_runtime/model_preload.py","remote_path":"/root/comfymodal_runtime/model_preload.py","remote_sha":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","verdict":"MATCH"},{"expected_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","module":"comfymodal_runtime/clip_fast_hydration_wiring.py","remote_path":"/root/comfymodal_runtime/clip_fast_hydration_wiring.py","remote_sha":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","verdict":"MATCH"},{"expected_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","module":"comfymodal_runtime/registry_proof_store.py","remote_path":"/root/comfymodal_runtime/registry_proof_store.py","remote_sha":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","verdict":"MATCH"},{"expected_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","module":"comfymodal_runtime/golden_serial.py","remote_path":"/root/comfymodal_runtime/golden_serial.py","remote_sha":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","verdict":"MATCH"},{"expected_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","module":"comfymodal_runtime/golden_qd_transport.py","remote_path":"/root/comfymodal_runtime/golden_qd_transport.py","remote_sha":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","verdict":"MATCH"},{"expected_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","module":"comfymodal_runtime/output_durability.py","remote_path":"/root/comfymodal_runtime/output_durability.py","remote_sha":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","verdict":"MATCH"}],"verdict":"MATCH"},"deploy_fingerprint":"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003","deployment_version":1,"expected":{"git_dirty":"M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/","git_head":"f21b3ae29685abbc429813fadc32c8f41264c03e","modules":{"comfymodal_runtime/clip_fast_hydration_wiring.py":{"mtime_ns":1788228829344488900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py","sha256":"a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85","size":139597},"comfymodal_runtime/critical_path_ledger.py":{"mtime_ns":1788187764270223900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py","sha256":"d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08","size":36804},"comfymodal_runtime/gantt_telemetry.py":{"mtime_ns":1787098762319903900,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py","sha256":"bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71","size":31387},"comfymodal_runtime/golden_qd_transport.py":{"mtime_ns":1788480592902234600,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py","sha256":"106d60a4800b4fb853f8aa7d2741401c6744fda06cb9d3ef68c106d9c4c27c80","size":172844},"comfymodal_runtime/golden_serial.py":{"mtime_ns":1788480582996633400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py","sha256":"96cef3cd8e43a978c16ccb437bd25a189b6866e6fe853d30986cc0d1173c64c8","size":538448},"comfymodal_runtime/modal_app.py":{"mtime_ns":1788449574842652400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py","sha256":"c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a","size":1204830},"comfymodal_runtime/model_preload.py":{"mtime_ns":1787351071293359800,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py","sha256":"4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed","size":1018301},"comfymodal_runtime/output_durability.py":{"mtime_ns":1788152549107099700,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py","sha256":"f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3","size":3350},"comfymodal_runtime/registry_proof_store.py":{"mtime_ns":1787279621108674500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py","sha256":"9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d","size":15738},"comfymodal_runtime/runtime_bootstrap.py":{"mtime_ns":1788102151291569400,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py","sha256":"624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4","size":135622},"comfymodal_runtime/runtime_executor.py":{"mtime_ns":1787981255324777500,"realpath":"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py","sha256":"ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd","size":243303}}},"integrity_digest":"23e3ca82a34da8e984cf71aab61d0f2ee8b0230482ab50ec0e3c17f9068eab76","profile":"golden_p1","receipt_integrity_digest":"f51f6f77349cf6c5b33aae27973f06fc3fbe3dcaccc250ca3b9e470837dcaa4b","remote_summary":{"app_name":"sept-unetclip-02-h2d-aggregation","class_name":"ModalRuntimeEntrypointV2","comfymodal_runtime_file":"/root/comfymodal_runtime/modal_app.py","comfymodal_runtime_path":[],"container_session_id":"bf43ce4e8e884c44","cwd":"/root/comfy/ComfyUI","deployment_combined_hash":"1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328","image_id":"im-BPPmnm0cOJT9z6adSJZCo5","pid":2,"probe_name":"source_identity_probe","python_executable":"/usr/local/bin/python","python_version":"3.11.5 (main, Aug 26 2023, 07:22:50) [Clang 16.0.3 ]","safe_env":{"COMFYMODAL_V2_APP_NAME":"sept-unetclip-02-h2d-aggregation","COMFYMODAL_V2_BENCHMARK_MODE":"","COMFYMODAL_V2_CLASS_NAME":"","COMFYMODAL_V2_CRITICAL_PATH_LEDGER":"","COMFYMODAL_V2_DEPLOYMENT_COMBINED_HASH":"","COMFYMODAL_V2_FULL_TRACE":"1"},"sys_path":["/root/comfy/ComfyUI/custom_nodes/comfyui-levelpixel/nodes/io/comfy","/root/comfy/ComfyUI/custom_nodes/RES4LYF/legacy/comfy","/root/comfy/ComfyUI/custom_nodes/comfyui-custom-scripts","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/custom_nodes/comfyui-modal","/root/comfy/ComfyUI/comfy","/root/comfy/ComfyUI","/root","/pkg","/root","/usr/local/lib/python311.zip","/usr/local/lib/python3.11","/usr/local/lib/python3.11/lib-dynload","/usr/local/lib/python3.11/site-packages","/__modal/deps","/root/comfy/ComfyUI/custom_nodes/ComfyUI_LayerStyle/py","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_controlnet_aux","/root/comfy/ComfyUI/custom_nodes/comfyui_controlnet_aux/src/custom_mmpkg","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","/root/comfy/ComfyUI/custom_nodes/comfyui-manager/glob","../..","/root/comfy/ComfyUI/custom_nodes/comfyui-impact-pack/modules"]},"schema_version":1,"target":{"app":"sept-unetclip-02-h2d-aggregation","class":"ModalRuntimeEntrypointV2","method":"run_golden_serial_stream"}}

```

#### attempt_5_R5 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / post-deploy status/doctor

Path: `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes, sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`.

```text
﻿[v2ctl.doctor]
git.head=f21b3ae29685abbc429813fadc32c8f41264c03e
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=sept-unetclip-02-h2d-aggregation
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=121
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.current=e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK

```

#### attempt_5_R5 / run stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / run manifest

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-33-10_657961/manifest.json` — 20688579 bytes, sha256 `ce532e5432ad7aec2b5f74d63058d1bcc625a36abd59f9669cba7a0e60403391`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20688579 sha256=ce532e5432ad7aec2b5f74d63058d1bcc625a36abd59f9669cba7a0e60403391

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_5_R5 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-33-10_657961/attempt_0.json` — 18786080 bytes, sha256 `7885fc2d9e6d2a5a5d3238ceab53e27bd063a8f68ad9ae5512914c2842c65968`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18786080 sha256=7885fc2d9e6d2a5a5d3238ceab53e27bd063a8f68ad9ae5512914c2842c65968

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
      "guard_armed_by_request_id": "",
      "last_guard_consumed_at": "",
      "last_guard_consumed_by_request_id": "",
      "last_snapshot_capture_at": "",
      "last_snapshot_capture_request_id": "",
      "last_transition_reason": "initial",
      "post_capture_guard_pending": false,
      "schema_version": 2,
      "state": "idle"
    },
    "transition": "none",
    "valid": true
  },
  "cold_evidence": {
    "basis": "restore_count==1 AND request_count==1 AND post_restore_nonce present AND min_containers==0 AND single_use_containers enabled AND frozen deployment/snapshot/config identities present",
    "frozen_identities": {
      "config": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
      "deployment": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
      "snapshot": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
    },
    "identity_tokens": {
      "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
      "container_id": "",
      "container_session_id": "bf43ce4e8e884c44",
      "container_task_id": "ta-01M1MXAXN245BP7A75T2AVE82R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MXAXN245BP7A75T2AVE82R",
      "pid": "2",
      "post_restore_nonce": "d0b41677947a45f4b593d18456e4445e",
      "restore_session_id": "bc89d7d14216417387e424c09a441492",
      "restored_instance_id": "a86620d6a68d4ee7ae7e983b2c94082e"
    },
    "identity_tokens_present": true,
    "min_containers": 0,
    "missing_requirements": [],
    "reason_not_cold": "",
    "request_count": 1,
    "requirements": {
      "frozen_config_identity_present": true,
      "frozen_deployment_identity_present": true,
      "frozen_snapshot_identity_present": true,
      "min_containers_is_zero": true,
      "post_restore_nonce_present": true,
      "request_count_is_one": true,
      "restore_count_is_one": true,
      "restored_instance_id_present": true,
      "single_use_containers_enabled": true
    },
    "restore_count": 1,
    "single_use_containers": true,
    "true_cold": true
  },
  "identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "boot_id": "aa415a1e-3474-4257-8fdf-5e588e79339c",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "95178395b31018114719e509647cef25afd057dbcbf612c8455df9a7846b8905",
    "container_id": "",
    "container_session_id": "bf43ce4e8e884c44",
    "container_task_id": "ta-01M1MXAXN245BP7A75T2AVE82R",
    "deployment_combined_hash": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_fingerprint": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "deployment_identity": "1d1425fa59850c6f3caebdfe67f80f48f862efd17625fe44e9afa3fb1d9fa328",
    "durability_requested": false,
    "image_id": "im-BPPmnm0cOJT9z6adSJZCo5",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MXAX11JGS6Y84Q1FRTT3BS:1788481991714-0",
    "modal_task_id": "ta-01M1MXAXN245BP7A75T2AVE82R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "d0b41677947a45f4b593d18456e4445e",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-78c70a67ceef",
    "restore_count": 1,
    "restore_session_id": "bc89d7d14216417387e424c09a441492",
    "restored_instance_id": "a86620d6a68d4ee7ae7e983b2c94082e",
    "runtime_shape": {
      "cpu_request": 4,
      "malloc_arena_max": null,
      "memory_request": 8192,
      "mkl_num_threads": null,
      "numexpr_num_threads": null,
      "omp_num_threads": null,
      "openblas_num_threads": null,
      "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
      "runtime_shape_label": null,
      "snapshot_model_order": "O0",
      "thread_policy": "TBASE",
      "torch_interop_threads": null,
      "torch_intraop_threads": null
    },
    "runtime_shape_fingerprint": "d6b79ec682e572bcac5c4171",
    "sage_runtime_mode_configured": "baked_cuda",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "single_use_containers": true,
    "single_use_enabled": true,
    "snapshot_identity": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386",
    "snapshot_target_fingerprint": "1db22c0ed3e86b496b6f8613139a72154e8c8647c7675e2a8e744870eee32386"
  },
  "validation": {
    "durability": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "durability_status": "NOT RUN",
    "durability_waterfall": {
      "asset_write_ms": null,
      "commit_ms": null,
      "fsync_ms": null,
      "reopen_ms": null,
      "status": "NOT RUN",
      "true_durable_ms": null
    },
    "observed_flags": {
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": true,
      "core_model_patcher_is_dynamic": true
    },
    "observed_output_byte_count": 3118036,
    "observed_output_shas": [
      "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"
    ],
    "output_durability_mode": "off",
    "output_endpoint": "result_ready",
    "output_sha_match": true
  }
}
```

#### attempt_5_R5 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-33-10_657961/summary.json` — 20688267 bytes, sha256 `b35124d9f8276fe955d612e7ba062dacad301308ac3beb43ad1f635312fac55d`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20688267 sha256=b35124d9f8276fe955d612e7ba062dacad301308ac3beb43ad1f635312fac55d

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "cold_evidence": "UNAVAILABLE",
  "identity": "UNAVAILABLE",
  "validation": "UNAVAILABLE"
}
```

#### attempt_5_R5 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-33-10_657961/attempt_0_events.json` — 29577825 bytes, sha256 `9142999dacedc0d504925303524941f8782896d780103e79913997be865b03e4`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29577825 sha256=9142999dacedc0d504925303524941f8782896d780103e79913997be865b03e4
text_omitted=true]
```

#### attempt_5_R5 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R5 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02-h2d-aggregation\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"deployment_combined_hash\":\"e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003\",\"gpu\":\"rtx-pro-6000\"}",
    "guard_armed_by_request_id": "",
    "last_guard_consumed_at": "",
    "last_guard_consumed_by_request_id": "",
    "last_snapshot_capture_at": "",
    "last_snapshot_capture_request_id": "",
    "last_transition_reason": "initial",
    "post_capture_guard_pending": false,
    "schema_version": 2,
    "state": "idle"
  },
  "transition": "none",
  "valid": true
}
```

## Disposition

Experiment 02 proves that aggregation was exercised, but the observed groups were small and transport placement fallback dominated the attempted grouping. The evidence does not establish a performance win for this configuration.

The report retains the aggregation evidence for diagnosis. Do not promote this aggregation configuration as an Experiment 03 optimization without a separately designed change that addresses canonical slot ordering and demonstrates a valid end-to-end result. If Experiment 03 does not explicitly test that redesign, use the Experiment 01 transport-core behavior as the revert boundary.

## Evidence integrity note

The v2ctl confirmation renderer labels the first four confirmation rows MISMATCH and the last EXACT. The authoritative per-request summaries remain valid, SHA-matching, and bound to the same deployment; the renderer identity mismatch is retained as a control-plane evidence defect, not hidden.

## Audit path inventory

The primary manifest is the authority for the audit inventory; every listed path is rendered or marked ABSENT.

* `.v2ctl/deployments/deploy_20260903-192325_e5d2e9dd.json` — 17254 bytes — sha256 `59ec3891d0036a942dadd04095f70235ff3e32e4a75d4c8ac705a9980eafbbd7`
* `.v2ctl/deployments/receipt_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 18767 bytes — sha256 `3c7db14e83c6a4362488f809007904f7ea1b10520e234c2bf1cfe68168938e92`
* `.v2ctl/source-probes/probe_1_e5d2e9ddbb852e6c8ec70e59eaf85fc07ffc4015fb471b961a63daf85801b003.json` — 11706 bytes — sha256 `a7a253e80ed1cc4e8fe40e73733eea176ab4c7610f326818fa464e38b2382b74`
* `.v2ctl/gates/gate_20260904-002855_9b88f8f1.json` — 22483 bytes — sha256 `08f38465c2fc8fd3b7e3a68afb9dfea703bfbb098722663e2373fa99d5a2792f`
* `.v2ctl/confirmations/confirm_20260904-003402_9b88f8f1.json` — 22578 bytes — sha256 `155fe45b123b4fd32149e4c02cb6ac21ad47eeb8f47a127c69264c02b68be6ec`
* `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_status.txt` — 1779 bytes — sha256 `23f414805800bdbb1f4d44c14bce5e650ebe052e75b2b07b3b888e6c4a11afc1`
* `unetClipExperimentsSeptember/evidence_text/exp02_post_confirm_doctor.txt` — 1056 bytes — sha256 `ec49420e56976c9ba1b11774ce8468ab06e10a0700d684114aa6d0b222c89046`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-29-33_a6dbd3/summary.json` — 20724852 bytes — sha256 `39d2b05edcf9c177f61a4c31e3fae882ff33c1c427257825c5ee6b6f34d2101f`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-30-28_28d69a/summary.json` — 20712259 bytes — sha256 `9c42049d90d53c5c5d87ca869d68f0521a9d5b0d40879a4f845bbb620be8ee49`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-31-23_0e05c7/summary.json` — 20705421 bytes — sha256 `a3a9e44502c81830c9858319ceb491e55c0fa4f04d01036a0c45b7ded75dc32d`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-32-15_68dc46/summary.json` — 20700192 bytes — sha256 `705d63a8c9848fc2c3608f73f9fa712dc72fc21023931bf85d2c0df23b31a614`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_00-33-10_657961/summary.json` — 20688267 bytes — sha256 `b35124d9f8276fe955d612e7ba062dacad301308ac3beb43ad1f635312fac55d`

* reference manifest `unetClipExperimentsSeptember/exp01_manifest.json` — 81319 bytes — sha256 `3f871047697315ab0cf29bdd6849165581767bde5774238d9a44a0b03b8c9562`
