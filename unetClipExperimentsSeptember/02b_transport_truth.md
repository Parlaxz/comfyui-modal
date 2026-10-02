# September UNET/CLIP Experiment 02B - Transport Truth

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
  * `tests/test_golden_qd_transport.py`
  * `tools/v2_control/cli.py`
* **tracked_diff_bytes:** `UNAVAILABLE`
* **tracked_diff_sha256:** `691412a9ed06211f9c08f131626414e3e3e00ebf`
* **untracked_inventory:**
  * `EXPERIMENT_EVIDENCE_golden_p1_*.md`
  * `RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md`
  * `RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md`
  * `unetClipExperimentsSeptember/`
* **experiment_id:** `sept-unetclip-02b-transport-truth`
* **app:** `sept-unetclip-02b-transport-truth`
* **profile:** `golden_p1`
* **class_name:** `ModalRuntimeEntrypointV2`
* **method:** `run_golden_serial_stream`
* **gpu:** `rtx-pro-6000`
* **deploy_fingerprint:** `9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6`
* **profile_config_fingerprint:** `a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec`
* **run_fingerprint:** `f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1`
* **content_generation:** `68e544aeb04298b47a0d573d042841b751e7f7e216941967298e76c9c8fc3325`
* **deployment_manifest:** `.v2ctl/deployments/deploy_20260903-212927_92318499.json`
* **deployment_receipt:** `.v2ctl/deployments/receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json`
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
* `transport_source_block_bytes=33554432`
* `transport_h2d_target_bytes=33554432`
* `transport_aggregation_enabled=false`

### SHA policies

* expected output SHA (profile/workload): `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
* skill-identity SHA: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`
* Current-bundle semantics retained; no new SHA gate was applied.

## Attempt ledger

All attempts are retained in manifest order; counted membership is taken from the manifest.

| attempt | role | classification | invocation ID | request ID | counted |
|---|---|---|---|---|---|
| attempt_0_S | S | S_SNAPSHOT_BOUNDARY_UNCOUNTED | 51d13171451b4e2e8908454aa6c6957b | golden-p1-0-0848088d079a | false |
| attempt_1_P | P | P_DIRECT_FOLLOWER_UNCOUNTED | f9fa8563ed404cafa4e3659c7c0df4ef | golden-p1-0-56ed8282f114 | false |
| attempt_2_R1 | R1 | ELIGIBLE | c076bb821eb54b8e8f3e75c52b222903 | golden-p1-0-63908b1dfd2f | true |
| attempt_3_R2 | R2 | ELIGIBLE | d9cd5fea7a2d4d148344126030a9bc57 | golden-p1-0-abce622d7157 | true |
| attempt_4_R3 | R3 | ELIGIBLE | b979d4dd3e654ae49e5fd1c8d79849f1 | golden-p1-0-5c975a9e546b | true |
| attempt_5_R4 | R4 | ELIGIBLE | 449fd89615e34fd99b686e7f500960f4 | golden-p1-0-40539ac103c5 | true |
| attempt_6_R5 | R5 | ELIGIBLE | da944d649a1144a0813d4eb8b2e0cd3a | golden-p1-0-8eafcee15fd4 | true |

## Capture boundary

S is the operator-designated snapshot-boundary observation and P is its directly following retained observation. The authoritative guard remained idle and emitted no capture transition, so S/P are excluded by explicit cohort role rather than by inferred timestamps.

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
| CLIP aggregation is disabled | PASS |
| CLIP aggregation counters are zero | PASS |
| CLIP uses 32 MiB H2D targets with explicit partial tails | PASS |
| CLIP has four source producers | PASS |
| CLIP has one 256 MiB arena and eight 32 MiB slots | PASS |
| UNET submitted/completed bytes reconcile | PASS |
| UNET aggregation is disabled | PASS |
| UNET aggregation counters are zero | PASS |
| UNET uses 32 MiB H2D targets with explicit partial tails | PASS |
| UNET has four source producers | PASS |
| UNET has one 256 MiB arena and eight 32 MiB slots | PASS |
| VAE submitted/completed bytes reconcile | PASS |
| VAE aggregation is disabled | PASS |
| VAE aggregation counters are zero | PASS |
| VAE uses 32 MiB H2D targets with explicit partial tails | PASS |
| VAE has four source producers | PASS |
| VAE has one 256 MiB arena and eight 32 MiB slots | PASS |

The VAE R3 record is retained as `E27_SOURCE_MECHANISM_PROVEN=NO` with failed predicate `max_actual_source_inflight`; this is reported separately from the artifact validity/SHA checks.
The per-request `attempt_0.json` runtime identity hash is distinct from the authoritative deployment binding. Deployment identity checks use each explicit request `manifest.json`/`summary.json` binding, which matches the primary manifest; the raw distinction is not normalized away.

| stage | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| external_restore | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| request_setup | 1.289 | 4.350 | 2.461 | 1.900 | 1.685 | 1.289 | 4.350 | 3.060 | 2.337 | 1.900 | 1.202 | 0.514 |
| clip_load | 1839.004 | 2361.811 | 1986.171 | 2535.322 | 2394.649 | 1839.004 | 2535.322 | 696.318 | 2223.391 | 2361.811 | 295.727 | 0.133 |
| clip_forward | 1324.405 | 1881.294 | 1357.652 | 1964.826 | 1457.375 | 1324.405 | 1964.826 | 640.421 | 1597.111 | 1457.375 | 302.989 | 0.190 |
| unet_load | 1910.195 | 2695.521 | 1714.200 | 2450.743 | 1956.342 | 1714.200 | 2695.521 | 981.321 | 2145.400 | 1956.342 | 410.142 | 0.191 |
| sampler_prepare | 295.104 | 508.046 | 308.775 | 492.702 | 358.606 | 295.104 | 508.046 | 212.942 | 392.647 | 358.606 | 101.287 | 0.258 |
| vae_load | 122.934 | 201.403 | 130.383 | 216.928 | 123.972 | 122.934 | 216.928 | 93.994 | 159.124 | 130.383 | 46.098 | 0.290 |
| sampling | 6100.565 | 6252.040 | 6484.391 | 6092.758 | 5887.424 | 5887.424 | 6484.391 | 596.967 | 6163.436 | 6100.565 | 221.356 | 0.036 |
| sampler_tail | 0.015 | 0.013 | 0.019 | 0.012 | 0.011 | 0.011 | 0.019 | 0.008 | 0.014 | 0.013 | 0.003 | 0.214 |
| vae_decode | 530.741 | 602.904 | 607.054 | 604.025 | 537.317 | 530.741 | 607.054 | 76.313 | 576.408 | 602.904 | 38.786 | 0.067 |
| output | 164.890 | 195.664 | 178.959 | 185.605 | 162.828 | 162.828 | 195.664 | 32.835 | 177.589 | 178.959 | 13.892 | 0.078 |
| teardown | 0.342 | 0.629 | 0.854 | 0.972 | 0.330 | 0.330 | 0.972 | 0.642 | 0.625 | 0.629 | 0.292 | 0.466 |
| request_wall | 144106.680 | 44264.539 | 35395.851 | 98024.234 | 37464.619 | 35395.851 | 144106.680 | 108710.829 | 71851.185 | 44264.539 | 47901.815 | 0.667 |
## Timeline / Gantt evidence

Exact monotonic stage boundaries are retained here; nested transport intervals are not added to stage walls.

| request | stage | entry monotonic ns | end monotonic ns | wall ms |
|---|---|---:|---:|---:|
| R1 | golden_restore | 367508818086 | 367518342370 | 9.524 |
| R1 | golden_request_setup | 367518386680 | 367519675729 | 1.289 |
| R1 | golden_clip_load | 367519764989 | 369358768919 | 1839.004 |
| R1 | golden_clip_forward | 369362692256 | 370687097149 | 1324.405 |
| R1 | golden_unet_load | 370687229499 | 372597424701 | 1910.195 |
| R1 | golden_sampler_prepare | 372601783598 | 372896887846 | 295.104 |
| R1 | golden_vae_load | 372896920096 | 373019853981 | 122.934 |
| R1 | golden_sampling | 373022037770 | 379122602602 | 6100.565 |
| R1 | golden_sampler_tail | 379124536561 | 379124551651 | 0.015 |
| R1 | golden_vae_decode | 379124576431 | 379655317708 | 530.741 |
| R1 | golden_output | 379655359718 | 379820250026 | 164.890 |
| R1 | golden_teardown | 379823383324 | 379823725214 | 0.342 |
| R2 | golden_restore | 564653989708 | 564665317731 | 11.328 |
| R2 | golden_request_setup | 564665359110 | 564669708656 | 4.350 |
| R2 | golden_clip_load | 564669816150 | 567031626812 | 2361.811 |
| R2 | golden_clip_forward | 567035928252 | 568917222530 | 1881.294 |
| R2 | golden_unet_load | 568917393842 | 571612914371 | 2695.521 |
| R2 | golden_sampler_prepare | 571615127198 | 572123173523 | 508.046 |
| R2 | golden_vae_load | 572123214099 | 572324617376 | 201.403 |
| R2 | golden_sampling | 572326328766 | 578578369063 | 6252.040 |
| R2 | golden_sampler_tail | 578580904832 | 578580917667 | 0.013 |
| R2 | golden_vae_decode | 578580948492 | 579183852618 | 602.904 |
| R2 | golden_output | 579183914490 | 579379578393 | 195.664 |
| R2 | golden_teardown | 579383871867 | 579384500946 | 0.629 |
| R3 | golden_restore | 547247662011 | 547257308066 | 9.646 |
| R3 | golden_request_setup | 547257359466 | 547259820704 | 2.461 |
| R3 | golden_clip_load | 547259991164 | 549246162221 | 1986.171 |
| R3 | golden_clip_forward | 549247436020 | 550605088060 | 1357.652 |
| R3 | golden_unet_load | 550605215740 | 552319415747 | 1714.200 |
| R3 | golden_sampler_prepare | 552322334985 | 552631109705 | 308.775 |
| R3 | golden_vae_load | 552631144655 | 552761527608 | 130.383 |
| R3 | golden_sampling | 552762993807 | 559247385082 | 6484.391 |
| R3 | golden_sampler_tail | 559249593901 | 559249612611 | 0.019 |
| R3 | golden_vae_decode | 559249640571 | 559856694421 | 607.054 |
| R3 | golden_output | 559856745491 | 560035704952 | 178.959 |
| R3 | golden_teardown | 560038615411 | 560039469150 | 0.854 |
| R4 | golden_restore | 793793727509 | 793810011943 | 16.284 |
| R4 | golden_request_setup | 793810103936 | 793812003876 | 1.900 |
| R4 | golden_clip_load | 793812172467 | 796347494839 | 2535.322 |
| R4 | golden_clip_forward | 796350874415 | 798315700633 | 1964.826 |
| R4 | golden_unet_load | 798315868825 | 800766611867 | 2450.743 |
| R4 | golden_sampler_prepare | 800769451141 | 801262153641 | 492.702 |
| R4 | golden_vae_load | 801262193876 | 801479121785 | 216.928 |
| R4 | golden_sampling | 801481016479 | 807573774450 | 6092.758 |
| R4 | golden_sampler_tail | 807576095705 | 807576108080 | 0.012 |
| R4 | golden_vae_decode | 807576137057 | 808180161643 | 604.025 |
| R4 | golden_output | 808180208263 | 808365813580 | 185.605 |
| R4 | golden_teardown | 808369682611 | 808370654615 | 0.972 |
| R5 | golden_restore | 829954774967 | 829964217127 | 9.442 |
| R5 | golden_request_setup | 829964256067 | 829965941027 | 1.685 |
| R5 | golden_clip_load | 829966077027 | 832360725763 | 2394.649 |
| R5 | golden_clip_forward | 832365590232 | 833822965439 | 1457.375 |
| R5 | golden_unet_load | 833823089959 | 835779431506 | 1956.342 |
| R5 | golden_sampler_prepare | 835785579365 | 836144185387 | 358.606 |
| R5 | golden_vae_load | 836144219667 | 836268192124 | 123.972 |
| R5 | golden_sampling | 836270226884 | 842157650822 | 5887.424 |
| R5 | golden_sampler_tail | 842159475832 | 842159486902 | 0.011 |
| R5 | golden_vae_decode | 842159511362 | 842696827930 | 537.317 |
| R5 | golden_output | 842696873180 | 842859701627 | 162.828 |
| R5 | golden_teardown | 842862637366 | 842862966946 | 0.330 |

## Output and durability

Output correctness and durability are reported as observed; durability mode `off` ends at `FIRST_RESULT_READY`.

| request | output endpoint | output SHA match | output bytes | durability mode | durability status | true durable |
|---|---|---|---:|---|---|---|
| R1 | result_ready | true | 3118036 | off | NOT RUN | UNAVAILABLE |
| R2 | result_ready | true | 3118036 | off | NOT RUN | UNAVAILABLE |
| R3 | result_ready | true | 3118036 | off | NOT RUN | UNAVAILABLE |
| R4 | result_ready | true | 3118036 | off | NOT RUN | UNAVAILABLE |
| R5 | result_ready | true | 3118036 | off | NOT RUN | UNAVAILABLE |

## Counter scope note

`GPU_COPY_COUNT`/`GPU_COPY_BYTES` are model-local. `REQUEST_CUMULATIVE_GPU_COPY_COUNT`/`REQUEST_CUMULATIVE_GPU_COPY_BYTES` are cumulative across the request's CLIP, UNET, and VAE loads.
The captured `REQUEST_CUMULATIVE_H2D_SUBMIT_COUNT` is zero because the deployed CUDA submission path increments the model-local H2D submit counter without mirroring that increment into the cumulative counter. `H2D_SUBMISSION_COUNT` and GPU-copy cumulative counters remain the authoritative observed counts; the zero cumulative H2D submit field must not be interpreted as zero H2D submissions.


### Combined loader wall

Derived per-request sum of the authoritative `clip_load + unet_load + vae_load` stage walls; it is not an end-to-end wall.

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| combined loader wall (ms) | 3872.133 | 5258.734 | 3830.754 | 5202.993 | 4474.963 | 3830.754 | 5258.734 | 1427.980 | 4527.916 | 4474.963 | 690.781 | 0.153 |

## CLIP / UNET / VAE decomposition

Nested transport intervals explain the enclosing stage and are not added as independent walls.

### CLIP

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 1079.030 | 1288.967 | 1178.371 | 1379.405 | 1615.294 | 1079.030 | 1615.294 | 536.264 | 1308.213 | 1288.967 | 205.622 | 0.157 |
| syscall union | 1071.401 | 1283.835 | 1167.347 | 1371.000 | 1541.676 | 1071.401 | 1541.676 | 470.276 | 1287.052 | 1283.835 | 182.158 | 0.142 |
| source -> GPU ready | 1081.484 | 1292.420 | 1180.871 | 1382.396 | 1618.211 | 1081.484 | 1618.211 | 536.727 | 1311.076 | 1292.420 | 205.811 | 0.157 |
| H2D wall | 1066.578 | 1265.539 | 1165.255 | 1358.278 | 1606.245 | 1066.578 | 1606.245 | 539.667 | 1292.379 | 1265.539 | 206.592 | 0.160 |
| source/H2D overlap | 418.010 | 513.927 | 415.473 | 526.477 | 496.905 | 415.473 | 526.477 | 111.005 | 474.158 | 496.905 | 53.462 | 0.113 |
| post-source H2D tail | 2.455 | 3.452 | 2.501 | 2.991 | 2.917 | 2.455 | 3.452 | 0.998 | 2.863 | 2.917 | 0.408 | 0.142 |
| load-wall residual after source -> GPU ready | 757.520 | 1069.391 | 805.300 | 1152.926 | 776.437 | 757.520 | 1152.926 | 395.407 | 912.315 | 805.300 | 184.691 | 0.202 |
| GPU active union | 187.251 | 280.350 | 219.122 | 252.033 | 284.278 | 187.251 | 284.278 | 97.027 | 244.607 | 252.033 | 41.369 | 0.169 |
| GPU stream span | 1066.579 | 1265.934 | 1165.147 | 1358.640 | 1606.260 | 1066.579 | 1606.260 | 539.680 | 1292.512 | 1265.934 | 206.630 | 0.160 |
| GPU idle inside span | 879.329 | 985.584 | 946.024 | 1106.607 | 1321.982 | 879.329 | 1321.982 | 442.654 | 1047.905 | 985.584 | 174.102 | 0.166 |
| GPU active share (%) | 17.556 | 22.146 | 18.806 | 18.550 | 17.698 | 17.556 | 22.146 | 4.590 | 18.951 | 18.550 | 1.864 | 0.098 |
| GPU idle share (%) | 82.444 | 77.854 | 81.194 | 81.450 | 82.302 | 77.854 | 82.444 | 4.590 | 81.049 | 81.450 | 1.864 | 0.023 |
| H2D target bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D minimum submission bytes | 2031872 | 2031872 | 2031872 | 2031872 | 2031872 | 2031872.000 | 2031872.000 | 0.000 | 2031872.000 | 2031872.000 | 0.000 | 0.000 |
| H2D maximum submission bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D mean submission bytes | 33106733.300 | 33106733.300 | 33106733.300 | 33106733.300 | 33106733.300 | 33106733.300 | 33106733.300 | 0.000 | 33106733.300 | 33106733.300 | 0.000 | 0.000 |
| H2D submissions | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| GPU copy count | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| GPU copy bytes | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192.000 | 8044936192.000 | 0.000 | 8044936192.000 | 8044936192.000 | 0.000 | 0.000 |
| request-cumulative H2D submits | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| request-cumulative H2D completions | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| request-cumulative GPU copy count | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| request-cumulative GPU copy bytes | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192.000 | 8044936192.000 | 0.000 | 8044936192.000 | 8044936192.000 | 0.000 | 0.000 |
| H2D completions | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| aggregation enabled | false | false | false | false | false | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| aggregation scheduler entries | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregation wait count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregated submissions | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| non-aggregated submissions | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| source reads | 243 | 243 | 243 | 243 | 243 | 243.000 | 243.000 | 0.000 | 243.000 | 243.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192 | 8044936192.000 | 8044936192.000 | 0.000 | 8044936192.000 | 8044936192.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |

### UNET

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 1549.605 | 2163.603 | 1344.077 | 1897.379 | 1583.456 | 1344.077 | 2163.603 | 819.526 | 1707.624 | 1583.456 | 322.676 | 0.189 |
| syscall union | 1541.336 | 2152.743 | 1334.561 | 1889.844 | 1575.596 | 1334.561 | 2152.743 | 818.182 | 1698.816 | 1575.596 | 322.182 | 0.190 |
| source -> GPU ready | 1553.008 | 2166.365 | 1346.911 | 1900.262 | 1586.428 | 1346.911 | 2166.365 | 819.454 | 1710.595 | 1586.428 | 322.574 | 0.189 |
| H2D wall | 1541.129 | 2144.152 | 1328.242 | 1878.283 | 1576.428 | 1328.242 | 2144.152 | 815.910 | 1693.647 | 1576.428 | 319.205 | 0.188 |
| source/H2D overlap | 696.133 | 889.772 | 654.049 | 872.450 | 660.350 | 654.049 | 889.772 | 235.723 | 754.551 | 696.133 | 116.803 | 0.155 |
| post-source H2D tail | 3.403 | 2.762 | 2.834 | 2.883 | 2.972 | 2.762 | 3.403 | 0.641 | 2.971 | 2.883 | 0.254 | 0.085 |
| load-wall residual after source -> GPU ready | 357.187 | 529.156 | 367.289 | 550.481 | 369.914 | 357.187 | 550.481 | 193.294 | 434.805 | 369.914 | 96.277 | 0.221 |
| GPU active union | 370.510 | 504.819 | 362.912 | 418.866 | 375.391 | 362.912 | 504.819 | 141.907 | 406.500 | 375.391 | 59.124 | 0.145 |
| GPU stream span | 1541.133 | 2144.321 | 1328.231 | 1878.353 | 1576.503 | 1328.231 | 2144.321 | 816.090 | 1693.708 | 1576.503 | 319.271 | 0.189 |
| GPU idle inside span | 1170.623 | 1639.502 | 965.319 | 1459.487 | 1201.113 | 965.319 | 1639.502 | 674.184 | 1287.209 | 1201.113 | 263.822 | 0.205 |
| GPU active share (%) | 24.041 | 23.542 | 27.323 | 22.300 | 23.812 | 22.300 | 27.323 | 5.023 | 24.204 | 23.812 | 1.869 | 0.077 |
| GPU idle share (%) | 75.959 | 76.458 | 72.677 | 77.700 | 76.188 | 72.677 | 77.700 | 5.023 | 75.796 | 76.188 | 1.869 | 0.025 |
| H2D target bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D minimum submission bytes | 4894304 | 4894304 | 4894304 | 4894304 | 4894304 | 4894304.000 | 4894304.000 | 0.000 | 4894304.000 | 4894304.000 | 0.000 | 0.000 |
| H2D maximum submission bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D mean submission bytes | 33269776.951 | 33269776.951 | 33269776.951 | 33269776.951 | 33269776.951 | 33269776.951 | 33269776.951 | 0.000 | 33269776.951 | 33269776.951 | 0.000 | 0.000 |
| H2D submissions | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| GPU copy count | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| GPU copy bytes | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472.000 | 12309817472.000 | 0.000 | 12309817472.000 | 12309817472.000 | 0.000 | 0.000 |
| request-cumulative H2D submits | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| request-cumulative H2D completions | 613 | 613 | 613 | 613 | 613 | 613.000 | 613.000 | 0.000 | 613.000 | 613.000 | 0.000 | 0.000 |
| request-cumulative GPU copy count | 613 | 613 | 613 | 613 | 613 | 613.000 | 613.000 | 0.000 | 613.000 | 613.000 | 0.000 | 0.000 |
| request-cumulative GPU copy bytes | 20354753664 | 20354753664 | 20354753664 | 20354753664 | 20354753664 | 20354753664.000 | 20354753664.000 | 0.000 | 20354753664.000 | 20354753664.000 | 0.000 | 0.000 |
| H2D completions | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| aggregation enabled | false | false | false | false | false | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| aggregation scheduler entries | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregation wait count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregated submissions | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| non-aggregated submissions | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| source reads | 370 | 370 | 370 | 370 | 370 | 370.000 | 370.000 | 0.000 | 370.000 | 370.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472 | 12309817472.000 | 12309817472.000 | 0.000 | 12309817472.000 | 12309817472.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |

### VAE

| metric | R1 | R2 | R3 | R4 | R5 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| source wall | 59.868 | 118.404 | 78.681 | 131.345 | 59.125 | 59.125 | 131.345 | 72.220 | 89.485 | 78.681 | 33.557 | 0.375 |
| syscall union | 57.101 | 111.335 | 75.935 | 127.567 | 57.241 | 57.101 | 127.567 | 70.466 | 85.836 | 75.935 | 32.145 | 0.374 |
| source -> GPU ready | 62.182 | 121.205 | 81.033 | 134.239 | 61.160 | 61.160 | 134.239 | 73.079 | 91.964 | 81.033 | 33.903 | 0.369 |
| H2D wall | 45.317 | 96.252 | 70.055 | 112.552 | 44.054 | 44.054 | 112.552 | 68.498 | 73.646 | 70.055 | 30.479 | 0.414 |
| source/H2D overlap | 22.565 | 19.169 | 46.474 | 81.838 | 19.276 | 19.169 | 81.838 | 62.669 | 37.864 | 22.565 | 27.097 | 0.716 |
| post-source H2D tail | 2.314 | 2.801 | 2.352 | 2.894 | 2.035 | 2.035 | 2.894 | 0.859 | 2.479 | 2.352 | 0.360 | 0.145 |
| load-wall residual after source -> GPU ready | 60.752 | 80.198 | 49.350 | 82.689 | 62.812 | 49.350 | 82.689 | 33.339 | 67.160 | 62.812 | 14.038 | 0.209 |
| GPU active union | 8.702 | 9.587 | 41.024 | 43.433 | 8.819 | 8.702 | 43.433 | 34.731 | 22.313 | 9.587 | 18.203 | 0.816 |
| GPU stream span | 45.256 | 96.419 | 70.098 | 112.779 | 44.148 | 44.148 | 112.779 | 68.631 | 73.740 | 70.098 | 30.572 | 0.415 |
| GPU idle inside span | 36.555 | 86.832 | 29.075 | 69.346 | 35.329 | 29.075 | 86.832 | 57.758 | 51.427 | 36.555 | 25.271 | 0.491 |
| GPU active share (%) | 19.228 | 9.943 | 58.523 | 38.512 | 19.976 | 9.943 | 58.523 | 48.580 | 29.236 | 19.976 | 19.377 | 0.663 |
| GPU idle share (%) | 80.772 | 90.057 | 41.477 | 61.488 | 80.024 | 41.477 | 90.057 | 48.580 | 70.764 | 80.024 | 19.377 | 0.274 |
| H2D target bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D minimum submission bytes | 132794 | 132794 | 132794 | 132794 | 132794 | 132794.000 | 132794.000 | 0.000 | 132794.000 | 132794.000 | 0.000 | 0.000 |
| H2D maximum submission bytes | 33554432 | 33554432 | 33554432 | 33554432 | 33554432 | 33554432.000 | 33554432.000 | 0.000 | 33554432.000 | 33554432.000 | 0.000 | 0.000 |
| H2D mean submission bytes | 25790671.692 | 25790671.692 | 25790671.692 | 25790671.692 | 25790671.692 | 25790671.692 | 25790671.692 | 0.000 | 25790671.692 | 25790671.692 | 0.000 | 0.000 |
| H2D submissions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| GPU copy count | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| GPU copy bytes | 335278732 | 335278732 | 335278732 | 335278732 | 335278732 | 335278732.000 | 335278732.000 | 0.000 | 335278732.000 | 335278732.000 | 0.000 | 0.000 |
| request-cumulative H2D submits | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| request-cumulative H2D completions | 626 | 626 | 626 | 626 | 626 | 626.000 | 626.000 | 0.000 | 626.000 | 626.000 | 0.000 | 0.000 |
| request-cumulative GPU copy count | 626 | 626 | 626 | 626 | 626 | 626.000 | 626.000 | 0.000 | 626.000 | 626.000 | 0.000 | 0.000 |
| request-cumulative GPU copy bytes | 20690032396 | 20690032396 | 20690032396 | 20690032396 | 20690032396 | 20690032396.000 | 20690032396.000 | 0.000 | 20690032396.000 | 20690032396.000 | 0.000 | 0.000 |
| H2D completions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| aggregation enabled | false | false | false | false | false | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE | UNAVAILABLE |
| aggregation scheduler entries | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregation wait count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| aggregated submissions | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| non-aggregated submissions | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| tail submissions | 7 | 7 | 7 | 7 | 7 | 7.000 | 7.000 | 0.000 | 7.000 | 7.000 | 0.000 | 0.000 |
| aggregation fallback count | 0 | 0 | 0 | 0 | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| source reads | 13 | 13 | 13 | 13 | 13 | 13.000 | 13.000 | 0.000 | 13.000 | 13.000 | 0.000 | 0.000 |
| source opens | 4 | 4 | 4 | 4 | 4 | 4.000 | 4.000 | 0.000 | 4.000 | 4.000 | 0.000 | 0.000 |
| source bytes | 335278732 | 335278732 | 335278732 | 335278732 | 335278732 | 335278732.000 | 335278732.000 | 0.000 | 335278732.000 | 335278732.000 | 0.000 | 0.000 |
| max actual source inflight | 4 | 4 | 3 | 3 | 4 | 3.000 | 4.000 | 1.000 | 3.600 | 4.000 | 0.548 | 0.152 |

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
| E27 source mechanism proven | NO | YES | YES | YES | YES |
| E27 failed predicates | ["fixed_contiguous_regions","fixed_ownership","monotonic_reads","coverage_exact","gaps","actual_syscall_qd_telemetry_complete","max_actual_source_inflight","source_total_wall_present","qd_occupancy_present","h2d_reconciliation_complete","quiescence_checkpoint_history","checkpoint_fields","bind_checkpoint","source_completion_checkpoint","final_completion_checkpoint","checkpoint_order","quiescence","required_evidence_persisted"] | [] | [] | [] | [] |

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
| E27 source mechanism proven | YES | YES | NO | NO | YES |
| E27 failed predicates | [] | [] | ["max_actual_source_inflight"] | ["max_actual_source_inflight"] | [] |

Future transport fields not emitted by the authoritative artifacts remain `UNAVAILABLE`.

## Resource and correctness invariants

| role | arena alloc count | arena bytes | logical slots | slot bytes | event objects | event rerecords | fresh event/copy | duplicate reads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 470.000 | 0.000 | 0.000 |
| UNET | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 1210.000 | 0.000 | 0.000 |
| VAE | 1.000 | 268435456.000 | 8.000 | 33554432.000 | 18.000 | 1236.000 | 0.000 | 0.000 |

Correctness and identity observations are per-request, not means:

* `R1`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R2`: provider=`CLOUD_PROVIDER_AWS` region=`eu-south-2` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R3`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R4`: provider=`CLOUD_PROVIDER_AWS` region=`eu-south-2` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
* `R5`: provider=`CLOUD_PROVIDER_GCP` region=`us-east1` true_cold=`True` restore_count=`1` request_count=`1` output_sha_match=`True`
## Transport evidence by request

These rows preserve the raw per-request distinctions that are lost in cohort means.

### R1

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {} | backing_owner_retained_for_adoption | true | true |
| UNET | NO | {} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation state detail

| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| CLIP | false | 0 | 0 | 0 | {} | 4 | 3.655 | 73.889 | 4 |
| UNET | false | 0 | 0 | 0 | {} | 4 | 3.545 | 62.455 | 4 |
| VAE | false | 0 | 0 | 0 | {} | 4 | 2.262 | 22.580 | 4 |

### R2

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation state detail

| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| CLIP | false | 0 | 0 | 0 | {} | 4 | 3.556 | 67.441 | 4 |
| UNET | false | 0 | 0 | 0 | {} | 4 | 3.562 | 64.851 | 4 |
| VAE | false | 0 | 0 | 0 | {} | 4 | 1.907 | 2.747 | 4 |

### R3

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {} | backing_owner_retained_for_adoption | true | true |
| VAE | NO | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation state detail

| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| CLIP | false | 0 | 0 | 0 | {} | 4 | 3.569 | 70.212 | 4 |
| UNET | false | 0 | 0 | 0 | {} | 4 | 3.463 | 58.334 | 4 |
| VAE | false | 0 | 0 | 0 | {} | 4 | 1.528 | 0.000 | 4 |

### R4

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {} | backing_owner_retained_for_adoption | true | true |
| VAE | NO | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation state detail

| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| CLIP | false | 0 | 0 | 0 | {} | 4 | 3.574 | 69.179 | 4 |
| UNET | false | 0 | 0 | 0 | {} | 4 | 3.586 | 64.957 | 4 |
| VAE | false | 0 | 0 | 0 | {} | 4 | 1.596 | 0.000 | 4 |

### R5

| role | E27 source proven | fallback reasons | adoption | H2D reconciliation | GPU timing proven |
|---|---|---|---|---|---|
| CLIP | YES | {} | backing_owner_retained_for_adoption | true | true |
| UNET | YES | {} | backing_owner_retained_for_adoption | true | true |
| VAE | YES | {} | backing_owner_retained_for_adoption | true | true |

#### Aggregation state detail

| role | aggregation enabled | scheduler entries | wait count | aggregated submissions | fallback reasons | source QD target | mean QD | QD4 wall share (%) | producer count |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| CLIP | false | 0 | 0 | 0 | {} | 4 | 2.615 | 45.457 | 4 |
| UNET | false | 0 | 0 | 0 | {} | 4 | 3.555 | 66.198 | 4 |
| VAE | false | 0 | 0 | 0 | {} | 4 | 2.002 | 3.296 | 4 |

## Reference comparison

NOT_PERFORMED: this report contains no Experiment 01 or Experiment 02 comparison.

## Per-attempt appendices

### attempt_0_S

role=`S` classification=`S_SNAPSHOT_BOUNDARY_UNCOUNTED`
invocation_id=`51d13171451b4e2e8908454aa6c6957b` request_id=`golden-p1-0-0848088d079a`

#### Available stage/invariant values

* `duration_ms`: `68184.583`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `9.695`
* stage `request_setup` wall ms: `1.447`
* stage `clip_load` wall ms: `1904.444`
* stage `clip_forward` wall ms: `1772.938`
* stage `unet_load` wall ms: `2204.478`
* stage `sampler_prepare` wall ms: `351.706`
* stage `vae_load` wall ms: `143.963`
* stage `sampling` wall ms: `5915.266`
* stage `sampler_tail` wall ms: `0.011`
* stage `vae_decode` wall ms: `581.807`
* stage `output` wall ms: `163.422`
* stage `teardown` wall ms: `0.289`

#### attempt_0_S / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_51d13171451b4e2e_2026-09-04.md` — 23352311 bytes, sha256 `bae8593f1e0312e138bb1f052c78d73cbe872cf89af259c5642bb89ab398e10f`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23352311 sha256=bae8593f1e0312e138bb1f052c78d73cbe872cf89af259c5642bb89ab398e10f
text_omitted=true]
```

#### attempt_0_S / run manifest

Path: `.v2ctl/runs/run_20260903-213300_f13eebc0.json` — 53107 bytes, sha256 `c294c968cc83cbd04861e6ddc041be2768adc1caa4e9d40acbb671e2110ffc61`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-31-44_3b239a\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-0848088d079a",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "51d13171451b4e2e8908454aa6c6957b"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-31-44_3b239a",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-0848088d079a",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-31-44_3b239a\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-31-44_3b239a\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-31-44_3b239a\\summary.json",
    "v2ctl_invocation_id": "51d13171451b4e2e8908454aa6c6957b"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 73.85899999999674,
    "ended_at": "2026-09-04T02:32:56+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:31:42+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:33:00+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "51d13171451b4e2e8908454aa6c6957b",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-0848088d079a",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "51d13171451b4e2e8908454aa6c6957b"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "51d13171451b4e2e8908454aa6c6957b",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-0848088d079a",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "51d13171451b4e2e8908454aa6c6957b",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "51d13171451b4e2e8908454aa6c6957b",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-0848088d079a",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "51d13171451b4e2e8908454aa6c6957b",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_0_S / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-31-44_3b239a/attempt_0.json` — 18208104 bytes, sha256 `ddcca53cf9b0948899d144d83b9bd9edaabb2772f149ac3ee602b318c3920782`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18208104 sha256=ddcca53cf9b0948899d144d83b9bd9edaabb2772f149ac3ee602b318c3920782

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
      "container_id": "",
      "container_session_id": "85ba1ce7aa1e4bf6",
      "container_task_id": "ta-01M1N440SZBN62071MXAXNMWKR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N440SZBN62071MXAXNMWKR",
      "pid": "2",
      "post_restore_nonce": "c77b32a4a757467a97ed4006b7a19561",
      "restore_session_id": "ef48da7069204042b92877bb4a1d000c",
      "restored_instance_id": "c09589f3c9614a5f94c6d65908e0e941"
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
    "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "85ba1ce7aa1e4bf6",
    "container_task_id": "ta-01M1N440SZBN62071MXAXNMWKR",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N440APC2X018B57JX01PXC:1788489105751-0",
    "modal_task_id": "ta-01M1N440SZBN62071MXAXNMWKR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "c77b32a4a757467a97ed4006b7a19561",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-0848088d079a",
    "restore_count": 1,
    "restore_session_id": "ef48da7069204042b92877bb4a1d000c",
    "restored_instance_id": "c09589f3c9614a5f94c6d65908e0e941",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_0_S / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-31-44_3b239a/summary.json` — 20053466 bytes, sha256 `bd0cee73bb9132f7a06f22738fa05809ef1bbc7ca73821be5eab13aafade5d81`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20053466 sha256=bd0cee73bb9132f7a06f22738fa05809ef1bbc7ca73821be5eab13aafade5d81

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_0_S / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-31-44_3b239a/attempt_0_events.json` — 28943130 bytes, sha256 `41f24fd2dd5e4cc9f319c684e5f0b9adfcba83fa2b70ea9dc4a878b8fde7d193`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=28943130 sha256=41f24fd2dd5e4cc9f319c684e5f0b9adfcba83fa2b70ea9dc4a878b8fde7d193
text_omitted=true]
```

#### attempt_0_S / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_0_S / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_1_P

role=`P` classification=`P_DIRECT_FOLLOWER_UNCOUNTED`
invocation_id=`f9fa8563ed404cafa4e3659c7c0df4ef` request_id=`golden-p1-0-56ed8282f114`

#### Available stage/invariant values

* `duration_ms`: `41975.031`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `8.101`
* stage `request_setup` wall ms: `1.075`
* stage `clip_load` wall ms: `4305.778`
* stage `clip_forward` wall ms: `1648.717`
* stage `unet_load` wall ms: `5121.876`
* stage `sampler_prepare` wall ms: `389.693`
* stage `vae_load` wall ms: `493.260`
* stage `sampling` wall ms: `6162.687`
* stage `sampler_tail` wall ms: `0.013`
* stage `vae_decode` wall ms: `557.329`
* stage `output` wall ms: `164.096`
* stage `teardown` wall ms: `0.326`

#### attempt_1_P / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_f9fa8563ed404caf_2026-09-04.md` — 23408626 bytes, sha256 `be04c0beda554aad0d888b3e606c3628ac777f4b3aca73a89f2fce6fc9b0513c`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23408626 sha256=be04c0beda554aad0d888b3e606c3628ac777f4b3aca73a89f2fce6fc9b0513c
text_omitted=true]
```

#### attempt_1_P / run manifest

Path: `.v2ctl/runs/run_20260903-213516_f13eebc0.json` — 53094 bytes, sha256 `1435039abf3090f99dff32dfb790147e64fdddddbe61a8d43138f51380784ef9`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-34-27_e6820d\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-56ed8282f114",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "f9fa8563ed404cafa4e3659c7c0df4ef"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-34-27_e6820d",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-56ed8282f114",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-34-27_e6820d\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-34-27_e6820d\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-34-27_e6820d\\summary.json",
    "v2ctl_invocation_id": "f9fa8563ed404cafa4e3659c7c0df4ef"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 47.0,
    "ended_at": "2026-09-04T02:35:12+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:34:25+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:35:16+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "f9fa8563ed404cafa4e3659c7c0df4ef",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-56ed8282f114",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "f9fa8563ed404cafa4e3659c7c0df4ef"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "f9fa8563ed404cafa4e3659c7c0df4ef",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-56ed8282f114",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "f9fa8563ed404cafa4e3659c7c0df4ef",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "f9fa8563ed404cafa4e3659c7c0df4ef",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-56ed8282f114",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "f9fa8563ed404cafa4e3659c7c0df4ef",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_1_P / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-34-27_e6820d/attempt_0.json` — 18300843 bytes, sha256 `becdac00bcd3777cbe3216fa50a9a571eb2f4d1df2696b068cf71d59b2b4ef96`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18300843 sha256=becdac00bcd3777cbe3216fa50a9a571eb2f4d1df2696b068cf71d59b2b4ef96

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
      "container_id": "",
      "container_session_id": "85ba1ce7aa1e4bf6",
      "container_task_id": "ta-01M1N491E2FCE9VB447ZSVDZ5R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N491E2FCE9VB447ZSVDZ5R",
      "pid": "2",
      "post_restore_nonce": "62768e05754543e0b68168b234754fec",
      "restore_session_id": "b14cac3651a940a2b542da5a0f4e5668",
      "restored_instance_id": "5c08a7f0528c47098e276c162045802d"
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
    "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "85ba1ce7aa1e4bf6",
    "container_task_id": "ta-01M1N491E2FCE9VB447ZSVDZ5R",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N48ZZVY0QQ8XH9KCZV2CZ0:1788489269244-0",
    "modal_task_id": "ta-01M1N491E2FCE9VB447ZSVDZ5R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "62768e05754543e0b68168b234754fec",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-56ed8282f114",
    "restore_count": 1,
    "restore_session_id": "b14cac3651a940a2b542da5a0f4e5668",
    "restored_instance_id": "5c08a7f0528c47098e276c162045802d",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_1_P / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-34-27_e6820d/summary.json` — 20149357 bytes, sha256 `f87d43694ae951c8f95944abb22889f409cde17260779e3f0df7ea6ad76dad5f`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20149357 sha256=f87d43694ae951c8f95944abb22889f409cde17260779e3f0df7ea6ad76dad5f

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_1_P / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-34-27_e6820d/attempt_0_events.json` — 29039034 bytes, sha256 `40a74daa02679ded0d6f4660b4bd9aa8b8d92cce45e9f2583dcd657b9b131aa6`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29039034 sha256=40a74daa02679ded0d6f4660b4bd9aa8b8d92cce45e9f2583dcd657b9b131aa6
text_omitted=true]
```

#### attempt_1_P / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_1_P / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_2_R1

role=`R1` classification=`ELIGIBLE`
invocation_id=`c076bb821eb54b8e8f3e75c52b222903` request_id=`golden-p1-0-63908b1dfd2f`

#### Available stage/invariant values

* `duration_ms`: `144106.680`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `9.524`
* stage `request_setup` wall ms: `1.289`
* stage `clip_load` wall ms: `1839.004`
* stage `clip_forward` wall ms: `1324.405`
* stage `unet_load` wall ms: `1910.195`
* stage `sampler_prepare` wall ms: `295.104`
* stage `vae_load` wall ms: `122.934`
* stage `sampling` wall ms: `6100.565`
* stage `sampler_tail` wall ms: `0.015`
* stage `vae_decode` wall ms: `530.741`
* stage `output` wall ms: `164.890`
* stage `teardown` wall ms: `0.342`

#### attempt_2_R1 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_c076bb821eb54b8e_2026-09-04.md` — 23464955 bytes, sha256 `26ac0a8ab0ec2823c876c65b18c36272c314c6cd877e4c6b9be6bbf71b071a51`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23464955 sha256=26ac0a8ab0ec2823c876c65b18c36272c314c6cd877e4c6b9be6bbf71b071a51
text_omitted=true]
```

#### attempt_2_R1 / run manifest

Path: `.v2ctl/runs/run_20260903-213829_f13eebc0.json` — 53108 bytes, sha256 `c4f1b6f4920c998ffa58169d4bbb6fcad133d210963962e63561e7cbb5b3e1b8`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-35-59_a9dbf8\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-63908b1dfd2f",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "c076bb821eb54b8e8f3e75c52b222903"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-35-59_a9dbf8",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-63908b1dfd2f",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-35-59_a9dbf8\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-35-59_a9dbf8\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-35-59_a9dbf8\\summary.json",
    "v2ctl_invocation_id": "c076bb821eb54b8e8f3e75c52b222903"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 148.76600000000326,
    "ended_at": "2026-09-04T02:38:26+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:35:57+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:38:29+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "c076bb821eb54b8e8f3e75c52b222903",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-63908b1dfd2f",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "c076bb821eb54b8e8f3e75c52b222903"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "c076bb821eb54b8e8f3e75c52b222903",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-63908b1dfd2f",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "c076bb821eb54b8e8f3e75c52b222903",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "c076bb821eb54b8e8f3e75c52b222903",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-63908b1dfd2f",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "c076bb821eb54b8e8f3e75c52b222903",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_2_R1 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-35-59_a9dbf8/attempt_0.json` — 18274468 bytes, sha256 `96f91a13f937e70d496fb223aa7d65cad3b0559f496806b5f5661b5efaa58ce3`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18274468 sha256=96f91a13f937e70d496fb223aa7d65cad3b0559f496806b5f5661b5efaa58ce3

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
      "container_id": "",
      "container_session_id": "85ba1ce7aa1e4bf6",
      "container_task_id": "ta-01M1N4F4JZNKAB0FZCFJFRDDRR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N4F4JZNKAB0FZCFJFRDDRR",
      "pid": "2",
      "post_restore_nonce": "c6e85b5a8e584ce9b23dee0039914d34",
      "restore_session_id": "a3465dda2aed4fdfb5becd93d3cb2dbf",
      "restored_instance_id": "f80f789bfa3a4262a5122a42e7bedfcf"
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
    "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "85ba1ce7aa1e4bf6",
    "container_task_id": "ta-01M1N4F4JZNKAB0FZCFJFRDDRR",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N4BSPH0QMSSHWENVDV9JXX:1788489361106-0",
    "modal_task_id": "ta-01M1N4F4JZNKAB0FZCFJFRDDRR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "c6e85b5a8e584ce9b23dee0039914d34",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-63908b1dfd2f",
    "restore_count": 1,
    "restore_session_id": "a3465dda2aed4fdfb5becd93d3cb2dbf",
    "restored_instance_id": "f80f789bfa3a4262a5122a42e7bedfcf",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_2_R1 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-35-59_a9dbf8/summary.json` — 20120014 bytes, sha256 `45caa5181f5f2b9b551ab553c4c8d600f19267012b71eb1d8ece5ae92fefcec4`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20120014 sha256=45caa5181f5f2b9b551ab553c4c8d600f19267012b71eb1d8ece5ae92fefcec4

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_2_R1 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-35-59_a9dbf8/attempt_0_events.json` — 29009683 bytes, sha256 `6263a495a5378155ed26d181af57330c50d81892729d0a15b7041ade1d53010e`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29009683 sha256=6263a495a5378155ed26d181af57330c50d81892729d0a15b7041ade1d53010e
text_omitted=true]
```

#### attempt_2_R1 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_2_R1 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_3_R2

role=`R2` classification=`ELIGIBLE`
invocation_id=`d9cd5fea7a2d4d148344126030a9bc57` request_id=`golden-p1-0-abce622d7157`

#### Available stage/invariant values

* `duration_ms`: `44264.539`
* `provider`: `CLOUD_PROVIDER_AWS`
* `region`: `eu-south-2`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `11.328`
* stage `request_setup` wall ms: `4.350`
* stage `clip_load` wall ms: `2361.811`
* stage `clip_forward` wall ms: `1881.294`
* stage `unet_load` wall ms: `2695.521`
* stage `sampler_prepare` wall ms: `508.046`
* stage `vae_load` wall ms: `201.403`
* stage `sampling` wall ms: `6252.040`
* stage `sampler_tail` wall ms: `0.013`
* stage `vae_decode` wall ms: `602.904`
* stage `output` wall ms: `195.664`
* stage `teardown` wall ms: `0.629`

#### attempt_3_R2 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_d9cd5fea7a2d4d14_2026-09-04.md` — 23521284 bytes, sha256 `b1e059cecc516b1c5c49249ac6ae8b8886aca241d6a17613e01e78c1093e5209`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23521284 sha256=b1e059cecc516b1c5c49249ac6ae8b8886aca241d6a17613e01e78c1093e5209
text_omitted=true]
```

#### attempt_3_R2 / run manifest

Path: `.v2ctl/runs/run_20260903-214006_f13eebc0.json` — 53108 bytes, sha256 `3fb658d675c4f3d56cda3381d153529c5c6991c96dcc4d644b0a72eacbf8a0d6`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-39-15_958299\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-abce622d7157",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "d9cd5fea7a2d4d148344126030a9bc57"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-39-15_958299",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-abce622d7157",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-39-15_958299\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-39-15_958299\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-39-15_958299\\summary.json",
    "v2ctl_invocation_id": "d9cd5fea7a2d4d148344126030a9bc57"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 48.703000000008615,
    "ended_at": "2026-09-04T02:40:03+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:39:14+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:40:06+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "d9cd5fea7a2d4d148344126030a9bc57",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-abce622d7157",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "d9cd5fea7a2d4d148344126030a9bc57"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "d9cd5fea7a2d4d148344126030a9bc57",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-abce622d7157",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "d9cd5fea7a2d4d148344126030a9bc57",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "d9cd5fea7a2d4d148344126030a9bc57",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-abce622d7157",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "d9cd5fea7a2d4d148344126030a9bc57",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_3_R2 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-39-15_958299/attempt_0.json` — 18272182 bytes, sha256 `6651f9cbff9c7ac1b3b7b13e86c6eb274ff9cdc258ed426f8bb7c2fc6eaaa3bb`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18272182 sha256=6651f9cbff9c7ac1b3b7b13e86c6eb274ff9cdc258ed426f8bb7c2fc6eaaa3bb

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "e11b9c0a-e86f-4fda-b83a-d4e23646de3b",
      "container_id": "",
      "container_session_id": "6e072b2d6d8f429d",
      "container_task_id": "ta-01M1N4HW9Z2FR6KD868DKX18ZR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N4HW9Z2FR6KD868DKX18ZR",
      "pid": "2",
      "post_restore_nonce": "df475257d7d9479ca29befd1d3f17810",
      "restore_session_id": "975ce767fcee4299abc8f0c5a67ff169",
      "restored_instance_id": "251bebc369dc43eba8b9be2ad7cd86e4"
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
    "boot_id": "e11b9c0a-e86f-4fda-b83a-d4e23646de3b",
    "cloud": "CLOUD_PROVIDER_AWS",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "6e072b2d6d8f429d",
    "container_task_id": "ta-01M1N4HW9Z2FR6KD868DKX18ZR",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N4HSA90PZHG7S3JTS7HXR0:1788489557321-0",
    "modal_task_id": "ta-01M1N4HW9Z2FR6KD868DKX18ZR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "df475257d7d9479ca29befd1d3f17810",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "eu-south-2",
    "request_count": 1,
    "request_id": "golden-p1-0-abce622d7157",
    "restore_count": 1,
    "restore_session_id": "975ce767fcee4299abc8f0c5a67ff169",
    "restored_instance_id": "251bebc369dc43eba8b9be2ad7cd86e4",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_3_R2 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-39-15_958299/summary.json` — 20117544 bytes, sha256 `3ea3469de640fc846477c49eb47c62ebad1e3d935a5768373a8af9ffe9e0b653`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20117544 sha256=3ea3469de640fc846477c49eb47c62ebad1e3d935a5768373a8af9ffe9e0b653

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_3_R2 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-39-15_958299/attempt_0_events.json` — 29007121 bytes, sha256 `4ba8d472f99a296fd10e2800c6b098f1d08a6efa4da369192d4415d70ad01674`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29007121 sha256=4ba8d472f99a296fd10e2800c6b098f1d08a6efa4da369192d4415d70ad01674
text_omitted=true]
```

#### attempt_3_R2 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_3_R2 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_4_R3

role=`R3` classification=`ELIGIBLE`
invocation_id=`b979d4dd3e654ae49e5fd1c8d79849f1` request_id=`golden-p1-0-5c975a9e546b`

#### Available stage/invariant values

* `duration_ms`: `35395.851`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `9.646`
* stage `request_setup` wall ms: `2.461`
* stage `clip_load` wall ms: `1986.171`
* stage `clip_forward` wall ms: `1357.652`
* stage `unet_load` wall ms: `1714.200`
* stage `sampler_prepare` wall ms: `308.775`
* stage `vae_load` wall ms: `130.383`
* stage `sampling` wall ms: `6484.391`
* stage `sampler_tail` wall ms: `0.019`
* stage `vae_decode` wall ms: `607.054`
* stage `output` wall ms: `178.959`
* stage `teardown` wall ms: `0.854`

#### attempt_4_R3 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_b979d4dd3e654ae4_2026-09-04.md` — 23577613 bytes, sha256 `238602fb141d644090989566db9c3e6dbd916bc1ca1b5aea1ac0ccb6a50716f0`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23577613 sha256=238602fb141d644090989566db9c3e6dbd916bc1ca1b5aea1ac0ccb6a50716f0
text_omitted=true]
```

#### attempt_4_R3 / run manifest

Path: `.v2ctl/runs/run_20260903-214130_f13eebc0.json` — 53108 bytes, sha256 `97c4ec60daf8101b1c10de3cebfa3a78147ea0e5c648f9b1610966608d363014`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-40-49_ed8ad1\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-5c975a9e546b",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "b979d4dd3e654ae49e5fd1c8d79849f1"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-40-49_ed8ad1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-5c975a9e546b",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-40-49_ed8ad1\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-40-49_ed8ad1\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-40-49_ed8ad1\\summary.json",
    "v2ctl_invocation_id": "b979d4dd3e654ae49e5fd1c8d79849f1"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 39.780999999988126,
    "ended_at": "2026-09-04T02:41:27+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:40:47+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:41:30+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "b979d4dd3e654ae49e5fd1c8d79849f1",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-5c975a9e546b",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "b979d4dd3e654ae49e5fd1c8d79849f1"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "b979d4dd3e654ae49e5fd1c8d79849f1",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-5c975a9e546b",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "b979d4dd3e654ae49e5fd1c8d79849f1",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "b979d4dd3e654ae49e5fd1c8d79849f1",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-5c975a9e546b",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "b979d4dd3e654ae49e5fd1c8d79849f1",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_4_R3 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-40-49_ed8ad1/attempt_0.json` — 18276005 bytes, sha256 `893995f709f2ab296bcc754db1e48a680f8cd81efdaadd3275e2f86d58e30d68`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18276005 sha256=893995f709f2ab296bcc754db1e48a680f8cd81efdaadd3275e2f86d58e30d68

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
      "container_id": "",
      "container_session_id": "85ba1ce7aa1e4bf6",
      "container_task_id": "ta-01M1N4MMXZMGCC6W2YM332P5TR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N4MMXZMGCC6W2YM332P5TR",
      "pid": "2",
      "post_restore_nonce": "46b5c492e2dc49d7b4dc43e40c3c2b5f",
      "restore_session_id": "613ac7175613493d8da102aab27b3bb2",
      "restored_instance_id": "52ca730e575745428c80379e0a8aec7a"
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
    "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "85ba1ce7aa1e4bf6",
    "container_task_id": "ta-01M1N4MMXZMGCC6W2YM332P5TR",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N4MMFH5XXKX48FAZNTV5A5:1788489650673-0",
    "modal_task_id": "ta-01M1N4MMXZMGCC6W2YM332P5TR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "46b5c492e2dc49d7b4dc43e40c3c2b5f",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-5c975a9e546b",
    "restore_count": 1,
    "restore_session_id": "613ac7175613493d8da102aab27b3bb2",
    "restored_instance_id": "52ca730e575745428c80379e0a8aec7a",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_4_R3 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-40-49_ed8ad1/summary.json` — 20121759 bytes, sha256 `c2b9e5156b880758de0956327e2715a6e5549288887dda4902cc4997510c392d`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20121759 sha256=c2b9e5156b880758de0956327e2715a6e5549288887dda4902cc4997510c392d

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_4_R3 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-40-49_ed8ad1/attempt_0_events.json` — 29011432 bytes, sha256 `d26104ed1e436400a6aa2e3d336b446facf9505efa6b071013700a148a37899c`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29011432 sha256=d26104ed1e436400a6aa2e3d336b446facf9505efa6b071013700a148a37899c
text_omitted=true]
```

#### attempt_4_R3 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_4_R3 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_5_R4

role=`R4` classification=`ELIGIBLE`
invocation_id=`449fd89615e34fd99b686e7f500960f4` request_id=`golden-p1-0-40539ac103c5`

#### Available stage/invariant values

* `duration_ms`: `98024.234`
* `provider`: `CLOUD_PROVIDER_AWS`
* `region`: `eu-south-2`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `16.284`
* stage `request_setup` wall ms: `1.900`
* stage `clip_load` wall ms: `2535.322`
* stage `clip_forward` wall ms: `1964.826`
* stage `unet_load` wall ms: `2450.743`
* stage `sampler_prepare` wall ms: `492.702`
* stage `vae_load` wall ms: `216.928`
* stage `sampling` wall ms: `6092.758`
* stage `sampler_tail` wall ms: `0.012`
* stage `vae_decode` wall ms: `604.025`
* stage `output` wall ms: `185.605`
* stage `teardown` wall ms: `0.972`

#### attempt_5_R4 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_449fd89615e34fd9_2026-09-04.md` — 23633941 bytes, sha256 `68f5159a2c3cec90c2e783bdbb2e160a29d8b8703d9c9f93a30651a7c150aa49`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23633941 sha256=68f5159a2c3cec90c2e783bdbb2e160a29d8b8703d9c9f93a30651a7c150aa49
text_omitted=true]
```

#### attempt_5_R4 / run manifest

Path: `.v2ctl/runs/run_20260903-214406_f13eebc0.json` — 53107 bytes, sha256 `930d23c108e4cde71c065ec112086e37e47c2cddffb41bfc5b35e3d2c34da027`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-42-16_41cb12\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-40539ac103c5",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "449fd89615e34fd99b686e7f500960f4"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-42-16_41cb12",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-40539ac103c5",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-42-16_41cb12\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-42-16_41cb12\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-42-16_41cb12\\summary.json",
    "v2ctl_invocation_id": "449fd89615e34fd99b686e7f500960f4"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 105.5789999999979,
    "ended_at": "2026-09-04T02:44:00+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:42:14+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:44:06+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "449fd89615e34fd99b686e7f500960f4",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-40539ac103c5",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "449fd89615e34fd99b686e7f500960f4"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "449fd89615e34fd99b686e7f500960f4",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-40539ac103c5",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "449fd89615e34fd99b686e7f500960f4",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "449fd89615e34fd99b686e7f500960f4",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-40539ac103c5",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "449fd89615e34fd99b686e7f500960f4",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_5_R4 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-42-16_41cb12/attempt_0.json` — 18275666 bytes, sha256 `33b3c38846b25649e4629ba330309a63c027577c957355fa7c13a6f04b150135`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18275666 sha256=33b3c38846b25649e4629ba330309a63c027577c957355fa7c13a6f04b150135

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "e11b9c0a-e86f-4fda-b83a-d4e23646de3b",
      "container_id": "",
      "container_session_id": "6e072b2d6d8f429d",
      "container_task_id": "ta-01M1N4RV011CF99SRC24VHDQNR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N4RV011CF99SRC24VHDQNR",
      "pid": "2",
      "post_restore_nonce": "ffaf45b7771c445f81faf8cf1156f37c",
      "restore_session_id": "6e68caa6a48f4911b6f7ec9cfa9aa19d",
      "restored_instance_id": "d7d8ff57b7da42648428fe9665108e27"
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
    "boot_id": "e11b9c0a-e86f-4fda-b83a-d4e23646de3b",
    "cloud": "CLOUD_PROVIDER_AWS",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "6e072b2d6d8f429d",
    "container_task_id": "ta-01M1N4RV011CF99SRC24VHDQNR",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N4Q9JFKAMXKY2YXEESD1A5:1788489737808-0",
    "modal_task_id": "ta-01M1N4RV011CF99SRC24VHDQNR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "ffaf45b7771c445f81faf8cf1156f37c",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "eu-south-2",
    "request_count": 1,
    "request_id": "golden-p1-0-40539ac103c5",
    "restore_count": 1,
    "restore_session_id": "6e68caa6a48f4911b6f7ec9cfa9aa19d",
    "restored_instance_id": "d7d8ff57b7da42648428fe9665108e27",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_5_R4 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-42-16_41cb12/summary.json` — 20121420 bytes, sha256 `c6b9f994cdb882e88ec37a8b477072b2d6e25a286834841a0d2505958073e37f`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20121420 sha256=c6b9f994cdb882e88ec37a8b477072b2d6e25a286834841a0d2505958073e37f

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_5_R4 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-42-16_41cb12/attempt_0_events.json` — 29011000 bytes, sha256 `d0dd1a66247861eb2b30f922312fd163d5126ef53be2ebb9f35a81cd715d20b3`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29011000 sha256=d0dd1a66247861eb2b30f922312fd163d5126ef53be2ebb9f35a81cd715d20b3
text_omitted=true]
```

#### attempt_5_R4 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_5_R4 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_6_R5

role=`R5` classification=`ELIGIBLE`
invocation_id=`da944d649a1144a0813d4eb8b2e0cd3a` request_id=`golden-p1-0-8eafcee15fd4`

#### Available stage/invariant values

* `duration_ms`: `37464.619`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `output_sha_match`: `true`
* `output_sha`: `["8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e"]`
* `true_cold`: `true`
* `restore_count`: `1`
* `request_count`: `1`
* stage `restore` wall ms: `9.442`
* stage `request_setup` wall ms: `1.685`
* stage `clip_load` wall ms: `2394.649`
* stage `clip_forward` wall ms: `1457.375`
* stage `unet_load` wall ms: `1956.342`
* stage `sampler_prepare` wall ms: `358.606`
* stage `vae_load` wall ms: `123.972`
* stage `sampling` wall ms: `5887.424`
* stage `sampler_tail` wall ms: `0.011`
* stage `vae_decode` wall ms: `537.317`
* stage `output` wall ms: `162.828`
* stage `teardown` wall ms: `0.330`

#### attempt_6_R5 / deployment stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / source-probe stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / pre-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / post-deploy status/doctor

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / run stdout

Path: `EXPERIMENT_EVIDENCE_golden_p1_da944d649a1144a0_2026-09-04.md` — 23690270 bytes, sha256 `7702430f448d8676a5c23763321fc10cc5e25e6c4a4eaeedbf9fd5e2a2416023`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=23690270 sha256=7702430f448d8676a5c23763321fc10cc5e25e6c4a4eaeedbf9fd5e2a2416023
text_omitted=true]
```

#### attempt_6_R5 / run manifest

Path: `.v2ctl/runs/run_20260903-214618_f13eebc0.json` — 53108 bytes, sha256 `3a3b3b95c1c4d0b248f855bbd72638b11065ac4fad4589963af90d1f76872e33`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-45-31_89da69\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
      "request_id": "golden-p1-0-8eafcee15fd4",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "da944d649a1144a0813d4eb8b2e0cd3a"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-45-31_89da69",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-8eafcee15fd4",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-45-31_89da69\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-45-31_89da69\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-04_02-45-31_89da69\\summary.json",
    "v2ctl_invocation_id": "da944d649a1144a0813d4eb8b2e0cd3a"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 45.046999999991385,
    "ended_at": "2026-09-04T02:46:13+00:00",
    "exit_code": 0,
    "started_at": "2026-09-04T02:45:28+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-04T02:46:18+00:00",
  "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "847d0dd999636ca753bd1b6b585332b10a8bc6683bbf3abbf7ee510665164b13",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "da944d649a1144a0813d4eb8b2e0cd3a",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
    "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
    "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
    "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
    "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
    "COMFYMODAL_V2_C9QD_EXTRAS": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
    "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
    "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
    "COMFYMODAL_V2_CLEAN_LANE": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
    "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
    "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
    "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
    "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
    "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
    "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
    "COMFYMODAL_V2_CLIP_QD_QD": "4",
    "COMFYMODAL_V2_CLIP_QD_READER": "0",
    "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
    "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
    "COMFYMODAL_V2_CLOUD": "",
    "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
    "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
    "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
    "COMFYMODAL_V2_CPU_REQUEST": "4",
    "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
    "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
    "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
    "COMFYMODAL_V2_E27_FORENSICS": "1",
    "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
    "COMFYMODAL_V2_E31_FORENSICS": "0",
    "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
    "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
    "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
    "COMFYMODAL_V2_ENV_PROFILE": "inherit",
    "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
    "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
    "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
    "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
    "COMFYMODAL_V2_FULL_TRACE": "1",
    "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
    "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
    "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
    "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
    "COMFYMODAL_V2_GPU": "rtx-pro-6000",
    "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
    "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
    "COMFYMODAL_V2_MEMORY_MB": "8192",
    "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
    "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
    "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
    "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
    "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
    "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
    "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
    "COMFYMODAL_V2_PREFILL_LANES": "critical",
    "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
    "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
    "COMFYMODAL_V2_REGION": "",
    "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
    "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
    "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
    "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
    "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
    "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
    "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
    "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
    "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
    "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
    "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
    "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
    "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
    "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
    "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
    "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
    "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
    "COMFYMODAL_V2_UNET_FORENSICS": "0",
    "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
    "COMFYMODAL_V2_UNET_PRETOUCH": "0",
    "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
    "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
    "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
    "COMFYMODAL_V2_VAE_POLICY": "v1",
    "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
    "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
    "COMPUTERNAME": "DESKTOP-IK4CEAD",
    "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
    "HOMEDRIVE": "C:",
    "HOMEPATH": "\\Users\\parla",
    "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
    "MODAL_TOKEN_ID": "<redacted>",
    "MODAL_TOKEN_SECRET": "<redacted>",
    "NUMBER_OF_PROCESSORS": "12",
    "OS": "Windows_NT",
    "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
    "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
    "PROCESSOR_ARCHITECTURE": "AMD64",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
    "SYSTEMROOT": "C:\\Windows",
    "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
    "USERNAME": "parla",
    "USERPROFILE": "C:\\Users\\parla",
    "V2_BENCHMARK_GAP_SECONDS": "35.0",
    "V2_BENCHMARK_MODE": "golden_p1_serial",
    "V2_BENCHMARK_RUNS": "1",
    "V2_D10_INTEGRATION_VALIDATION": "0",
    "V2_D6_FASTPATH_VALIDATION": "0",
    "V2_E10_BUCKET_FIRST_VALIDATION": "0",
    "V2_E19_FINAL_COLD_LOADER": "0",
    "V2_E22_CONDITIONING_NONCE": "",
    "V2_E22_PREFETCH_OFF": "0",
    "V2_E22_PREFETCH_ON": "0",
    "V2_E25_CONDITIONING_NONCE": "",
    "V2_E25_VALIDATION": "0",
    "V2_E26_CONDITIONING_NONCE": "",
    "V2_E26_VALIDATION": "0",
    "V2_E28_CONDITIONING_NONCE": "",
    "V2_E28_VALIDATION": "0",
    "V2_IS_VARIANCE": "0",
    "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
    "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
    "V2_RESTORE_ONLY_RUN_COUNT": "6",
    "V2_VARIANCE_COLD_GAP_SECONDS": "25",
    "V2_VARIANCE_PRETOUCH": "0",
    "V2_VARIANCE_RUN_COUNT": "6",
    "V2_VOLUME_READ_GAP_SECONDS": "25.0",
    "V2_VOLUME_READ_RUN_COUNT": "3",
    "WINDIR": "C:\\Windows"
  },
  "experiment_identity": {
    "attention_backend": "pytorch",
    "attention_backend_configured": "pytorch",
    "attention_backend_resolved": "pytorch",
    "configured_sage_runtime_mode": "auto",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-8eafcee15fd4",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "da944d649a1144a0813d4eb8b2e0cd3a"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "da944d649a1144a0813d4eb8b2e0cd3a",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "flag_sources": {
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "profile:golden_p1",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "profile:golden_p1",
      "COMFYMODAL_MINIMAL_RESTORE": "default",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "profile:golden_p1",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "default",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "default",
      "COMFYMODAL_V2_C9QD_EXTRAS": "profile:golden_p1",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "default",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "default",
      "COMFYMODAL_V2_CLEAN_LANE": "default",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "default",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "default",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "default",
      "COMFYMODAL_V2_CLIP_QD_QD": "default",
      "COMFYMODAL_V2_CLIP_QD_READER": "default",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "profile:golden_p1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "default",
      "COMFYMODAL_V2_CLOUD": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "default",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "default",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_CPU_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "default",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "default",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "default",
      "COMFYMODAL_V2_E27_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "default",
      "COMFYMODAL_V2_E31_FORENSICS": "default",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "default",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "default",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "default",
      "COMFYMODAL_V2_ENV_PROFILE": "profile:golden_p1",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "default",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "default",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "default",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "default",
      "COMFYMODAL_V2_FULL_TRACE": "profile:golden_p1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "default",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "default",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "profile:golden_p1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "profile:golden_p1",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "profile:golden_p1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "profile:golden_p1",
      "COMFYMODAL_V2_MEMORY_MB": "profile:golden_p1",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "default",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "profile:golden_p1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "default",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "profile:golden_p1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "default",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "default",
      "COMFYMODAL_V2_PREFILL_LANES": "default",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "default",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "default",
      "COMFYMODAL_V2_REGION": "default",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "profile:golden_p1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "default",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "default",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "default",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "default",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "profile:golden_p1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "profile:golden_p1",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "default",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "default",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "default",
      "COMFYMODAL_V2_THREAD_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "default",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "default",
      "COMFYMODAL_V2_UNET_FORENSICS": "profile:golden_p1",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "default",
      "COMFYMODAL_V2_UNET_PRETOUCH": "default",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "default",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "default",
      "COMFYMODAL_V2_VAE_POLICY": "profile:golden_p1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "profile:golden_p1",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "default",
      "V2_BENCHMARK_GAP_SECONDS": "default",
      "V2_BENCHMARK_MODE": "default",
      "V2_BENCHMARK_RUNS": "default",
      "V2_D10_INTEGRATION_VALIDATION": "default",
      "V2_D6_FASTPATH_VALIDATION": "default",
      "V2_E10_BUCKET_FIRST_VALIDATION": "default",
      "V2_E19_FINAL_COLD_LOADER": "default",
      "V2_E22_CONDITIONING_NONCE": "default",
      "V2_E22_PREFETCH_OFF": "default",
      "V2_E22_PREFETCH_ON": "default",
      "V2_E25_CONDITIONING_NONCE": "default",
      "V2_E25_VALIDATION": "default",
      "V2_E26_CONDITIONING_NONCE": "default",
      "V2_E26_VALIDATION": "default",
      "V2_E28_CONDITIONING_NONCE": "default",
      "V2_E28_VALIDATION": "default",
      "V2_IS_VARIANCE": "default",
      "V2_RESTORE_ONLY_GAP_SECONDS": "default",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "default",
      "V2_RESTORE_ONLY_RUN_COUNT": "default",
      "V2_VARIANCE_COLD_GAP_SECONDS": "default",
      "V2_VARIANCE_PRETOUCH": "default",
      "V2_VARIANCE_RUN_COUNT": "default",
      "V2_VOLUME_READ_GAP_SECONDS": "default",
      "V2_VOLUME_READ_RUN_COUNT": "default"
    },
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "a9fdc89b2ff115f9876c432025c62f14bc90405ce8bc75c2d6ce758df14acbec",
    "request_id": "golden-p1-0-8eafcee15fd4",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "da944d649a1144a0813d4eb8b2e0cd3a",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-02b-transport-truth",
      "COMFYMODAL_V2_ATOMIC_PROFILE": "0",
      "COMFYMODAL_V2_BASELINE_CPU_REQUEST": "4",
      "COMFYMODAL_V2_BASELINE_MEMORY_REQUEST": "8192",
      "COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH": "0",
      "COMFYMODAL_V2_C9QD_EXTRAS": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM": "0",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_CHUNK_MB": "64",
      "COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS": "4",
      "COMFYMODAL_V2_CLASS_NAME": "ModalRuntimeEntrypointV2",
      "COMFYMODAL_V2_CLEAN_LANE": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST": "0",
      "COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA": "0",
      "COMFYMODAL_V2_CLIP_CONDITIONING_CACHE": "1",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_CLIP_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_CLIP_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_CLIP_FAST_HYDRATION": "0",
      "COMFYMODAL_V2_CLIP_FP32_CAST_ONCE": "0",
      "COMFYMODAL_V2_CLIP_QD_ARTIFACT": "",
      "COMFYMODAL_V2_CLIP_QD_BLOCK_MIB": "32",
      "COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY": "restore_earliest",
      "COMFYMODAL_V2_CLIP_QD_QD": "4",
      "COMFYMODAL_V2_CLIP_QD_READER": "0",
      "COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS": "1",
      "COMFYMODAL_V2_CLIP_STAGED_HYDRATION": "0",
      "COMFYMODAL_V2_CLOUD": "",
      "COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU": "0",
      "COMFYMODAL_V2_CONDITIONING_CACHE_PREFETCH": "0",
      "COMFYMODAL_V2_CPU_MODEL_SNAPSHOT": "0",
      "COMFYMODAL_V2_CPU_REQUEST": "4",
      "COMFYMODAL_V2_CRITICAL_GPU_COORDINATION": "0",
      "COMFYMODAL_V2_CRITICAL_PATH_LEDGER": "1",
      "COMFYMODAL_V2_DEEP_MODEL_DIAG": "0",
      "COMFYMODAL_V2_E27_FORENSICS": "1",
      "COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT": "1024",
      "COMFYMODAL_V2_E31_FORENSICS": "0",
      "COMFYMODAL_V2_E31_FORWARD_PROFILE": "0",
      "COMFYMODAL_V2_E37_CLEAN_LANE": "0",
      "COMFYMODAL_V2_E37_STRICT_PROOF": "0",
      "COMFYMODAL_V2_ENV_PROFILE": "inherit",
      "COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT": "0",
      "COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS": "0",
      "COMFYMODAL_V2_EVICT_RETAIN_ROLE": "none",
      "COMFYMODAL_V2_FAST_COLD_ORCHESTRATION": "0",
      "COMFYMODAL_V2_FULL_TRACE": "1",
      "COMFYMODAL_V2_GANTT_TELEMETRY": "0",
      "COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND": "pytorch",
      "COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM": "1",
      "COMFYMODAL_V2_GOLDEN_WORKFLOW_HASH_CHECK": "1",
      "COMFYMODAL_V2_GPU": "rtx-pro-6000",
      "COMFYMODAL_V2_GPU_FAST_RETURN": "1",
      "COMFYMODAL_V2_INPUT_TYPES_WARM": "1",
      "COMFYMODAL_V2_MEMORY_MB": "8192",
      "COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN": "0",
      "COMFYMODAL_V2_NATIVE_FAST_DISK_UNET": "1",
      "COMFYMODAL_V2_OBSERVABILITY_MODE": "full",
      "COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_PAGEFAULT_TRACKING": "0",
      "COMFYMODAL_V2_PERSISTENT_LOCAL_HANDLE": "1",
      "COMFYMODAL_V2_PIN_UNET_TRANSFER": "0",
      "COMFYMODAL_V2_PNG_COMPRESS_LEVEL": "3",
      "COMFYMODAL_V2_PREFILL_LANES": "critical",
      "COMFYMODAL_V2_PREFILL_WAIT_FOR_UNET": "0",
      "COMFYMODAL_V2_PROMPT_SIGNATURE_CACHE": "0",
      "COMFYMODAL_V2_REGION": "",
      "COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST": "1",
      "COMFYMODAL_V2_RESIDENCY_DIAGNOSTICS": "0",
      "COMFYMODAL_V2_SCOPED_CUDA_READINESS": "0",
      "COMFYMODAL_V2_SINGLE_USE_CONTAINERS": "1",
      "COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE": "0",
      "COMFYMODAL_V2_SNAPSHOT_CONSTRUCTION": "0",
      "COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET": "0",
      "COMFYMODAL_V2_SNAPSHOT_MANIFEST": "1",
      "COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER": "O0",
      "COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION": "0",
      "COMFYMODAL_V2_STAGED_SAFETENSORS": "0",
      "COMFYMODAL_V2_STAGED_SOURCE_ORDER": "0",
      "COMFYMODAL_V2_THREAD_POLICY": "TBASE",
      "COMFYMODAL_V2_UNET_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_UNET_FASTSAFETENSORS": "0",
      "COMFYMODAL_V2_UNET_FASTSAFE_BBUF_KB": "256",
      "COMFYMODAL_V2_UNET_FASTSAFE_BLOCK_BYTES": "16777216",
      "COMFYMODAL_V2_UNET_FASTSAFE_THREADS": "4",
      "COMFYMODAL_V2_UNET_FORENSICS": "0",
      "COMFYMODAL_V2_UNET_PINNED_STAGING": "0",
      "COMFYMODAL_V2_UNET_PRETOUCH": "0",
      "COMFYMODAL_V2_UNET_QUIESCED_TRANSFER": "0",
      "COMFYMODAL_V2_VAE_ACTIVATION_MODE": "late",
      "COMFYMODAL_V2_VAE_EARLY_START_MS": "0",
      "COMFYMODAL_V2_VAE_POLICY": "v1",
      "COMFYMODAL_V2_VAE_SNAPSHOT": "0",
      "COMFYMODAL_V2_VARIANCE_DIAGNOSTICS": "0",
      "COMPUTERNAME": "DESKTOP-IK4CEAD",
      "COMSPEC": "C:\\Windows\\system32\\cmd.exe",
      "HOMEDRIVE": "C:",
      "HOMEPATH": "\\Users\\parla",
      "LOCALAPPDATA": "C:\\Users\\parla\\AppData\\Local",
      "MODAL_TOKEN_ID": "<redacted>",
      "MODAL_TOKEN_SECRET": "<redacted>",
      "NUMBER_OF_PROCESSORS": "12",
      "OS": "Windows_NT",
      "PATH": "C:\\Users\\parla\\AppData\\Local\\Programs\\Paseo\\resources\\app.asar\\node_modules\\sherpa-onnx-win-x64;C:\\Program Files\\Common Files\\Oracle\\Java\\javapath;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.8\\libnvvp;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\bin;C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v12.9\\libnvvp;C:\\Program Files\\Oculus\\Support\\oculus-runtime;C:\\Program Files\\Python311\\Scripts\\;C:\\Program Files\\Python311\\;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\Git\\cmd;C:\\Program Files\\Python311;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Program Files\\Microsoft SQL Server\\150\\Tools\\Binn\\;C:\\Program Files\\Microsoft SQL Server\\Client SDK\\ODBC\\170\\Tools\\Binn\\;C:\\Program Files\\Calibre2\\;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Program Files\\NVIDIA Corporation\\NVIDIA app\\NvDLISR;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Program Files\\NVIDIA Corporation\\Nsight Compute 2025.1.0\\;C:\\Users\\parla\\AppData\\Roaming\\Python\\Python311\\Scripts;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Program Files\\Docker\\Docker\\resources\\bin;C:\\Program Files\\CMake\\bin;C:\\Program Files\\PuTTY\\;C:\\Program Files\\nodejs\\;C:\\Users\\parla\\.local\\bin;C:\\Program Files\\PowerToys\\DSCModules\\;C:\\Program Files\\Sniffnet\\;C:\\Program Files\\GitHub CLI\\;C:\\Program Files\\AppControl\\bin;C:\\Users\\parla\\.opencode\\bin;C:\\Users\\parla\\.bun\\bin;C:\\Ruby32-x64\\bin;C:\\Program Files\\Eclipse Adoptium\\jre-8.0.352.8-hotspot\\bin;C:\\Windows\\system32;C:\\Windows;C:\\Windows\\System32\\Wbem;C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\;C:\\Windows\\System32\\OpenSSH\\;C:\\Program Files\\Microsoft VS Code\\bin;C:\\Program Files\\dotnet\\;C:\\Program Files\\NVIDIA Corporation\\NVIDIA NvDLISR;C:\\Program Files (x86)\\NVIDIA Corporation\\PhysX\\Common;C:\\ProgramData\\chocolatey\\bin;C:\\Program Files\\nodejs\\;C:\\Program Files\\Git\\cmd;C:\\Users\\parla\\AppData\\Local\\Microsoft\\WindowsApps;C:\\Users\\parla\\AppData\\Local\\Programs\\mongosh\\;C:\\Program Files\\Python311\\Scripts;C:\\Program Files\\PostgreSQL\\9.5\\bin;C:\\Users\\parla\\.dotnet\\tools;C:\\Users\\parla\\.fly\\bin;C:\\Program Files\\ffmpeg\\bin\\;C:\\Program Files (x86)\\yt-dlp;C:\\Users\\parla\\AppData\\Local\\GitHubDesktop\\bin;C:\\Users\\parla\\flutter\\flutter\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\cursor\\resources\\app\\bin;C:\\Users\\parla\\AppData\\Local\\Google\\Cloud SDK\\google-cloud-sdk\\bin;C:\\Users\\parla\\AppData\\Local\\Programs\\Ollama;C:\\Users\\parla\\.lmstudio\\bin;C:\\Users\\parla\\AppData\\Roaming\\npm;C:\\Users\\parla\\AppData\\Local\\Programs\\Windsurf\\bin;C:\\Users\\parla\\.local\\bin;C:\\Users\\parla\\.bun\\bin",
      "PATHEXT": ".COM;.EXE;.BAT;.CMD;.VBS;.VBE;.JS;.JSE;.WSF;.WSH;.MSC;.PY;.PYW;.RB;.RBW;.CPL",
      "PROCESSOR_ARCHITECTURE": "AMD64",
      "PYTHONIOENCODING": "utf-8",
      "PYTHONUTF8": "1",
      "SYSTEMROOT": "C:\\Windows",
      "TEMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "TMP": "C:\\Users\\parla\\AppData\\Local\\Temp",
      "USERNAME": "parla",
      "USERPROFILE": "C:\\Users\\parla",
      "V2_BENCHMARK_GAP_SECONDS": "35.0",
      "V2_BENCHMARK_MODE": "golden_p1_serial",
      "V2_BENCHMARK_RUNS": "1",
      "V2_D10_INTEGRATION_VALIDATION": "0",
      "V2_D6_FASTPATH_VALIDATION": "0",
      "V2_E10_BUCKET_FIRST_VALIDATION": "0",
      "V2_E19_FINAL_COLD_LOADER": "0",
      "V2_E22_CONDITIONING_NONCE": "",
      "V2_E22_PREFETCH_OFF": "0",
      "V2_E22_PREFETCH_ON": "0",
      "V2_E25_CONDITIONING_NONCE": "",
      "V2_E25_VALIDATION": "0",
      "V2_E26_CONDITIONING_NONCE": "",
      "V2_E26_VALIDATION": "0",
      "V2_E28_CONDITIONING_NONCE": "",
      "V2_E28_VALIDATION": "0",
      "V2_IS_VARIANCE": "0",
      "V2_RESTORE_ONLY_GAP_SECONDS": "30.0",
      "V2_RESTORE_ONLY_MAX_ATTEMPTS": "40",
      "V2_RESTORE_ONLY_RUN_COUNT": "6",
      "V2_VARIANCE_COLD_GAP_SECONDS": "25",
      "V2_VARIANCE_PRETOUCH": "0",
      "V2_VARIANCE_RUN_COUNT": "6",
      "V2_VOLUME_READ_GAP_SECONDS": "25.0",
      "V2_VOLUME_READ_RUN_COUNT": "3",
      "WINDIR": "C:\\Windows"
    },
    "resources": {
      "cpu": 4,
      "gpu": "rtx-pro-6000",
      "memory_mb": 8192,
      "min_containers": 0,
      "scaledown_window": 4
    },
    "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-02b-transport-truth",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "da944d649a1144a0813d4eb8b2e0cd3a",
    "workload": {
      "conditioning_cache": "forced_miss",
      "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
      "fresh_required": true,
      "gap_seconds": 35.0,
      "nonce": "",
      "run_count": 1
    }
  },
  "provenance_validation_status": "validated",
  "receipt_deploy_fingerprint": "9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6",
  "receipt_manifest_digest": "9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-212927_92318499.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M comfymodal_runtime/golden_qd_transport.py\n M comfymodal_runtime/golden_serial.py\n M tests/test_golden_qd_transport.py\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0d497a3f87f8b3d7_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0eb9fbaf1549419a_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_1d7995dfe58844ed_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_31ad35aa48ca4203_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3c17f4adc157429c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_6662e3d7b4a6470c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_71cdfa0824d545e5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7e22e9e1eb934dcf_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_916b7f8cfb5f4a35_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_9e28609607dd02a0_2026-09-04.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_e83c25a4db6b4dd6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "f21b3ae29685abbc429813fadc32c8f41264c03e",
    "modules": {
      "comfymodal_runtime/clip_fast_hydration_wiring.py": {
        "mtime_ns": 1788228829344488900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\clip_fast_hydration_wiring.py",
        "sha256": "a84bae8030a79dab99518819e6e156d801556f61b9167822bf98a40c1bc72f85",
        "size": 139597
      },
      "comfymodal_runtime/critical_path_ledger.py": {
        "mtime_ns": 1788187764270223900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\critical_path_ledger.py",
        "sha256": "d001f24678843afc549b878ee30cf9494e44a4ebd890b0daa7ef9dae2f11aa08",
        "size": 36804
      },
      "comfymodal_runtime/gantt_telemetry.py": {
        "mtime_ns": 1787098762319903900,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\gantt_telemetry.py",
        "sha256": "bf61c7db3a931120432852d9732f333366c18390a285655ab925fa888ef60e71",
        "size": 31387
      },
      "comfymodal_runtime/golden_qd_transport.py": {
        "mtime_ns": 1788488350539493100,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "2f4787f11a0f1c46dc589cbd34d42eda5d9dad4f3a8a9db2588ea25a5da90303",
        "size": 175363
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788488050731421200,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "3fcd48b75c2419f3a5d4e7136832d3e3214d425c7b6cbf0202ac4598aa23b7c6",
        "size": 539057
      },
      "comfymodal_runtime/modal_app.py": {
        "mtime_ns": 1788449574842652400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\modal_app.py",
        "sha256": "c156c662172d08031ae2a33da5566626e528ba15ac36eda6f90f6289abaa869a",
        "size": 1204830
      },
      "comfymodal_runtime/model_preload.py": {
        "mtime_ns": 1787351071293359800,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\model_preload.py",
        "sha256": "4affe1e06a3acc240418584d4e08a2210243b7de3f50e3ffe73c177c8eceeeed",
        "size": 1018301
      },
      "comfymodal_runtime/output_durability.py": {
        "mtime_ns": 1788152549107099700,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\output_durability.py",
        "sha256": "f4a95d4e0348df271728f0bec4baa96f67ad89f3070a2f1b4c13244d8d94cfd3",
        "size": 3350
      },
      "comfymodal_runtime/registry_proof_store.py": {
        "mtime_ns": 1787279621108674500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\registry_proof_store.py",
        "sha256": "9e4692fddc14ad91ab4d5abf255e53b33f28448aba46b1c403c071aa2d5d929d",
        "size": 15738
      },
      "comfymodal_runtime/runtime_bootstrap.py": {
        "mtime_ns": 1788102151291569400,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_bootstrap.py",
        "sha256": "624dcd50c26f55b5ca97d57b98fcc035c3af72c670b81017470fe1a5402214f4",
        "size": 135622
      },
      "comfymodal_runtime/runtime_executor.py": {
        "mtime_ns": 1787981255324777500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\runtime_executor.py",
        "sha256": "ab0651bf2de41e7d77f601175481a3dc09723b1a36d734b5441cfd53085ad9fd",
        "size": 243303
      }
    }
  },
  "receipt_target": {
    "app": "sept-unetclip-02b-transport-truth",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-8eafcee15fd4",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "f13eebc06aa7910503d4261470aedc7d6b16c9d5e8df3dcf452538d78c6d51f1",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json",
  "v2ctl_invocation_id": "da944d649a1144a0813d4eb8b2e0cd3a",
  "workload": {
    "conditioning_cache": "forced_miss",
    "expected_output_sha": "8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e",
    "fresh_required": true,
    "gap_seconds": 35.0,
    "nonce": "",
    "run_count": 1
  }
}
```

#### attempt_6_R5 / attempt artifact

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-45-31_89da69/attempt_0.json` — 18356689 bytes, sha256 `ffd09c84c73f93f675fa3f251bd43af1ddecd82f3792576390c5a7bc748847bb`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=18356689 sha256=ffd09c84c73f93f675fa3f251bd43af1ddecd82f3792576390c5a7bc748847bb

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
      "deployment": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
      "snapshot": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
    },
    "identity_tokens": {
      "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
      "container_id": "",
      "container_session_id": "85ba1ce7aa1e4bf6",
      "container_task_id": "ta-01M1N4X8FTZZE622DJJWS2HM7R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1N4X8FTZZE622DJJWS2HM7R",
      "pid": "2",
      "post_restore_nonce": "fa5353657ddb4b4a954d9db86d975495",
      "restore_session_id": "fe997157ce6a478db33f29d3896fad0f",
      "restored_instance_id": "c45c56daa26f4e8ca0b777a2c592f34f"
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
    "boot_id": "ca7cbc15-bd72-4f95-952e-8ea3e7f98a47",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "80663b7ffebd34e1f2830df7c16fd72d96133dcd89fd2a0dff369bd5df08d564",
    "container_id": "",
    "container_session_id": "85ba1ce7aa1e4bf6",
    "container_task_id": "ta-01M1N4X8FTZZE622DJJWS2HM7R",
    "deployment_combined_hash": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_fingerprint": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "deployment_identity": "bf61e62bac39030578cd3c7755b13e3beef52e96b9d58e14fdc3db36b8c9a01f",
    "durability_requested": false,
    "image_id": "im-d9xUB7Owdkri4AaE1Uj34V",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1N4X854P581NAX3A0WJBETH:1788489932965-0",
    "modal_task_id": "ta-01M1N4X8FTZZE622DJJWS2HM7R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "fa5353657ddb4b4a954d9db86d975495",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-8eafcee15fd4",
    "restore_count": 1,
    "restore_session_id": "fe997157ce6a478db33f29d3896fad0f",
    "restored_instance_id": "c45c56daa26f4e8ca0b777a2c592f34f",
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
    "snapshot_identity": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8",
    "snapshot_target_fingerprint": "5a1c41c82aadbc7a7785e5170acc7eaca7a9deecc21c0003bd05767267e161d8"
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

#### attempt_6_R5 / derived report

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / derived gantt

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / derived summary

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-45-31_89da69/summary.json` — 20211291 bytes, sha256 `e1d1e7ab5666c1d9471a6f3840339eb075a50f0c8119617e141e085bb93a0d0c`.

```json
[JSON exceeds 200000 bytes; selected sections embedded.
byte_size=20211291 sha256=e1d1e7ab5666c1d9471a6f3840339eb075a50f0c8119617e141e085bb93a0d0c

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_6_R5 / raw session events

Path: `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-45-31_89da69/attempt_0_events.json` — 29100963 bytes, sha256 `e9aae3a80da2bd720f97210d54b382594f1e1014b3a9449f324b94c0b0da7e6a`.

```text
[Text exceeds 200000 bytes; full file remains at the audited path.
byte_size=29100963 sha256=e9aae3a80da2bd720f97210d54b382594f1e1014b3a9449f324b94c0b0da7e6a
text_omitted=true]
```

#### attempt_6_R5 / raw milestones

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / blocked stdout

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / post-block doctor/status

ABSENT — checked explicit path: UNAVAILABLE

#### attempt_6_R5 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-02b-transport-truth\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"deployment_combined_hash\":\"9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6\",\"gpu\":\"rtx-pro-6000\"}",
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

This report records the non-aggregating 32 MiB transport behavior and its observed stage, source-QD, H2D, GPU-copy, resource, correctness, and teardown evidence. It makes no performance comparison or performance verdict.

## Audit path inventory

The primary manifest is the authority for the audit inventory; every listed path is rendered or marked ABSENT.

* `.v2ctl/deployments/deploy_20260903-212927_92318499.json` — 17281 bytes — sha256 `9313dc208a8fac0045d5fb3ec696a2ecae2fb6dd08310a27486a10ce69a578c4`
* `.v2ctl/deployments/receipt_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json` — 19006 bytes — sha256 `3448387f165c7f9b499be439f1a8adc684e63b16b54a3c84157271c6b5af1263`
* `.v2ctl/source-probes/probe_1_9231849958984f02aa48472df594abcde5e35065b3b0735770c31064dcdafbe6.json` — 11942 bytes — sha256 `5fba8283a85657184fe6aa47c6cdc886a2b6b8b15cbe47dde801236b03f959a4`
* `unetClipExperimentsSeptember/evidence_text/02b_post_status.txt` — 3558 bytes — sha256 `99b21050ae724785394cad842d45c08495048c56500c56132f3b45439c89b71d`
* `unetClipExperimentsSeptember/evidence_text/02b_post_doctor.txt` — 2110 bytes — sha256 `311622bdbce30404aad712a651d55680e3630e3dce99a9ff9945efb760446831`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-31-44_3b239a/summary.json` — 20053466 bytes — sha256 `bd0cee73bb9132f7a06f22738fa05809ef1bbc7ca73821be5eab13aafade5d81`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-34-27_e6820d/summary.json` — 20149357 bytes — sha256 `f87d43694ae951c8f95944abb22889f409cde17260779e3f0df7ea6ad76dad5f`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-35-59_a9dbf8/summary.json` — 20120014 bytes — sha256 `45caa5181f5f2b9b551ab553c4c8d600f19267012b71eb1d8ece5ae92fefcec4`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-39-15_958299/summary.json` — 20117544 bytes — sha256 `3ea3469de640fc846477c49eb47c62ebad1e3d935a5768373a8af9ffe9e0b653`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-40-49_ed8ad1/summary.json` — 20121759 bytes — sha256 `c2b9e5156b880758de0956327e2715a6e5549288887dda4902cc4997510c392d`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-42-16_41cb12/summary.json` — 20121420 bytes — sha256 `c6b9f994cdb882e88ec37a8b477072b2d6e25a286834841a0d2505958073e37f`
* `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-04_02-45-31_89da69/summary.json` — 20211291 bytes — sha256 `e1d1e7ab5666c1d9471a6f3840339eb075a50f0c8119617e141e085bb93a0d0c`
* `unetClipExperimentsSeptember/EXPERIMENT_PROTOCOL.md` — 5180 bytes — sha256 `a734c4e2aae508f2ac8e9a184a58ae4a4ec6c8631e5d538f980de749686d952a`
* `unetClipExperimentsSeptember/build_experiment_report.py` — 41968 bytes — sha256 `029e5a8b5058976b0d9c90f19d4fb2f0973a235c4931dc02dae790628ee5647b`
* `unetClipExperimentsSeptember/02_h2d_aggregation.md` — 188713 bytes — sha256 `b382ac1752c5a6ed1d97f2c5aca3cc9af9661eb5c543115e3441ac15f9bfcf33`
