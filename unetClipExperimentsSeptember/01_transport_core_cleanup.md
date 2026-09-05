# September UNET/CLIP Experiment 01 - Transport Core

PERFORMANCE_COMPARISON=NOT_PERFORMED

PERFORMANCE_VERDICT=NOT_PROVIDED

STATUS=COMPLETE

COHORT=FINAL

COUNTED_COHORT=R1,R3,R4,R7,R8 (n=5)

PENDING_REPLACEMENTS=0
REPLACEMENT_ATTEMPTS=R7,R8 (both counted as canonical-valid despite independent VAE E27 anomalies)

## Identity

* **worktree:** `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal`
* **branch:** `TESTING2`
* **head:** `9f2ce64cfe93b1ae74567b802b30da4c3533e594`
* **git_dirty:** `True`
* **tracked_diff_files:**
  * `.opencode/skills/comfymodal-golden-ops/SKILL.md`
  * `tools/v2_control/cli.py`
* **tracked_diff_bytes:** `4094`
* **tracked_diff_sha256:** `6f633e0493a065d49a7019ef6d0306559c7be2bdaa6236e2621d8950d127965f`
* **untracked_inventory:**
  * `EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_54844b3521364f78_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md`
  * `EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md`
  * `RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md`
  * `RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md`
  * `unetClipExperimentsSeptember/00_current_bundle_baseline.md`
  * `unetClipExperimentsSeptember/01_transport_core_cleanup.md`
  * `unetClipExperimentsSeptember/EXPERIMENT_PROTOCOL.md`
  * `unetClipExperimentsSeptember/build_experiment_report.py`
  * `unetClipExperimentsSeptember/evidence_text/exp00_deploy_stdout.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_dirty_diff_stat.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_doctor_post_deploy.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_doctor_preflight.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_git_freeze_and_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_run1_stdout.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_run2_blocked_stdout.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_source_probe_stdout.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp00_status_preflight.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_00_pre_status_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_02_pre_doctor_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_03_pre_deploy_doctor.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_04_pre_deploy_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_06_pre_source_probe_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe_utf8.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_08_final_drift_after_stop.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_09_drift_before_source_probe_no_flag.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_10_source_probe_no_flag.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_11_drift_before_source_probe_flag.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_12_source_probe_flag.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_13_drift_before_source_probe_flag_position.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_14_source_probe_flag_position.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_15_final_drift_after_source_probe_stop.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_16_pre_run_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_17_run_S.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_18_final_stop_drift.txt`
  * `unetClipExperimentsSeptember/evidence_text/exp01_deployment_manifest.json`
  * `unetClipExperimentsSeptember/evidence_text/exp01_deployment_receipt.json`
  * `unetClipExperimentsSeptember/exp00_manifest.json`
  * `unetClipExperimentsSeptember/exp01_manifest.json`
* **experiment_id:** `sept-unetclip-01-transport-core`
* **app:** `sept-unetclip-01-transport-core`
* **profile:** `golden_p1`
* **class_name:** `ModalRuntimeEntrypointV2`
* **method:** `run_golden_serial_stream`
* **gpu:** `rtx-pro-6000`
* **deploy_fingerprint:** `f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919`
* **profile_config_fingerprint:** `58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db`
* **run_fingerprint:** `1ed4c4448a74c28cbe5d30687b9b8d2eafb54548d2d810d61e061cd45b4c2b73`
* **content_generation:** `006b85813917fce36ab5a9f68b3dad56b7610508c569cd90ac8dd42eccdd76d1`
* **deployment_manifest:** `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/deployments/deploy_20260903-140910_f6b59e42.json`
* **deployment_receipt:** `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/deployments/receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json`
* **raw_evidence_root:** `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text`

### Effective environment

* `COMFYMODAL_GOLDEN_QD_TRANSPORT=static_e27`
* `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=0`
* `COMFYMODAL_V2_FULL_TRACE=1`
* `COMFYMODAL_V2_E27_FORENSICS=1`
* `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`
* `COMFYMODAL_SAGE_RUNTIME_MODE=auto`
* `COMFYMODAL_OUTPUT_DURABILITY=off`
* `COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1 (flagged golden-run invocation; no run manifest emitted)`
* `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1`
* `COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0`
* `COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM=1`
* `COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1`
* `COMFYMODAL_MINIMAL_RESTORE=1`
* `GPU=rtx-pro-6000 CPU=4 MEM=8192MiB min_containers=0 scaledown=4s`
* `conditioning_cache=forced_miss fresh_required=true gap_seconds=35.0 run_count=1`
* `attention_backend=pytorch`
* `runtime_overrides=0 (policy forbid)`
* tracing flags are recorded explicitly above; no cross-experiment comparison is performed

### SHA policies

* expected output SHA (profile/workload): `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
* skill-identity SHA: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`
* Current-bundle semantics retained; no new SHA gate was applied.

## Attempt ledger

All attempts are retained in manifest order; no attempt is selected by appearance or mtime.

| attempt | role | classification | invocation ID | request ID | counted |
|---|---|---|---|---|---|
| attempt_0_source_probe_blocked | INVALID_UNCOUNTED | BLOCKED_PREFLIGHT | UNAVAILABLE | UNAVAILABLE | False |
| attempt_1_source_probe_no_flag_retry | INVALID_UNCOUNTED | BLOCKED_PREFLIGHT | UNAVAILABLE | UNAVAILABLE | False |
| attempt_2_source_probe_flag_suffix | INVALID_UNCOUNTED | SOURCE_PROBE_INTERFACE_REJECTED_FLAG | UNAVAILABLE | UNAVAILABLE | False |
| attempt_3_source_probe_flag_global | INVALID_UNCOUNTED | SOURCE_PROBE_INTERFACE_REJECTED_FLAG | UNAVAILABLE | UNAVAILABLE | False |
| attempt_4_flagged_golden_run_S | PRE_CAPTURE_UNCOUNTED | BLOCKED_SOURCE_PROBE_REQUIRED | UNAVAILABLE | UNAVAILABLE | False |
| attempt_5_source_probe_direct_operator_retry | INVALID_UNCOUNTED | BLOCKED_PREFLIGHT | UNAVAILABLE | UNAVAILABLE | False |
| attempt_6_S_first_live_request | OPERATOR_ASSERTED_SNAPSHOT_CAPTURE | ACCEPT_EXACT_VALID | ecb67ccb2cdb42dbbf6b983566e68ab2 | golden-p1-0-0d8fa65c47f6 | False |
| attempt_7_P_direct_follower | P_DIRECT_FOLLOWER | ACCEPT_EXACT_VALID_E27_VAE_FAILED | e83c25a4db6b4dd692f1af1e380579ac | golden-p1-0-52ac9eb4ad3a | False |
| attempt_8_R1 | R1 | ELIGIBLE | 1d7995dfe58844ed906d4d4c423ff0a3 | golden-p1-0-5563949c90ad | True |
| attempt_9_R2 | R2 | EXCLUDED_E27_CLIP_VAE_FAILED | 31ad35aa48ca42038bdcda1225b3033e | golden-p1-0-7a23d7251359 | False |
| attempt_10_R3 | R3 | ELIGIBLE | 7e22e9e1eb934dcf804b6f55a43c8a10 | golden-p1-0-bedd2c24af6e | True |
| attempt_11_R4 | R4 | ELIGIBLE | 71cdfa0824d545e5ad5bd77edcfd5ae2 | golden-p1-0-320e378e38ab | True |
| attempt_12_R5 | R5 | QUARANTINED_PROVIDER_REGION_TRANSITION_BOUNDARY_CANDIDATE | 3c17f4adc157429ca68be0a56f05e1b4 | golden-p1-0-df455320d250 | False |
| attempt_13_R6 | R6 | EXCLUDED_IMMEDIATE_FOLLOWER_AND_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT | 916b7f8cfb5f4a358ad8340bbe013548 | golden-p1-0-a8687cc077ab | False |
| attempt_14_R7 | R7 | ELIGIBLE_CANONICAL_VALID_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT | 2d87a69c7a6f4fb6ba27ce188f8bd543 | golden-p1-0-48d498cafa08 | True |
| attempt_15_R8 | R8 | ELIGIBLE_CANONICAL_VALID_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT | 9b5ce81f587745f6b4bd5949a5604a81 | golden-p1-0-96631c1bf371 | True |

## Five-run performance schema


The final counted cohort is exactly `R1`, `R3`, `R4`, `R7`, `R8` (n=5).
`S` is the operator-asserted snapshot capture and is excluded; `P` is its direct
follower and is excluded for VAE E27 NO/max_actual_source_inflight. `R2` is
excluded for CLIP E27 NO and VAE E27 NO/max_actual_source_inflight. `R5` is
preserved as `QUARANTINED_PROVIDER_REGION_TRANSITION_BOUNDARY_CANDIDATE` and
`R6` is excluded as its immediate follower, with its independent VAE E27 NO /
max_actual_source_inflight anomaly. `R7` and `R8` are canonical-valid eligible
requests and are counted despite their independent VAE E27 NO /
max_actual_source_inflight anomalies. All five counted artifacts are valid,
true-cold, SHA-matching, serial, poison-free, fallback-free, and quiescence-proven.

### Derived stage statistics (milliseconds)

| stage | R1 | R3 | R4 | R7 | R8 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| external_restore | 464.633 | 338.276 | 466.243 | 899.753 | 688.852 | 338.276 | 899.753 | 561.477 | 571.551 | 466.243 | 222.719 | 0.3897 |
| golden_restore | 9.264 | 9.247 | 10.350 | 9.717 | 8.850 | 8.850 | 10.350 | 1.500 | 9.486 | 9.264 | 0.572 | 0.0604 |
| request_setup | 2.457 | 1.280 | 1.923 | 1.240 | 1.480 | 1.240 | 2.457 | 1.217 | 1.676 | 1.480 | 0.514 | 0.3066 |
| clip_load | 2083.314 | 1524.003 | 1938.043 | 1716.929 | 1901.078 | 1524.003 | 2083.314 | 559.311 | 1832.673 | 1901.078 | 216.377 | 0.1181 |
| clip_forward | 1523.225 | 1394.863 | 1498.111 | 1425.489 | 1440.330 | 1394.863 | 1523.225 | 128.362 | 1456.403 | 1440.330 | 52.929 | 0.0363 |
| unet_load | 2746.388 | 1637.969 | 1970.840 | 1845.139 | 1885.125 | 1637.969 | 2746.388 | 1108.419 | 2017.092 | 1885.125 | 425.655 | 0.2110 |
| sampler_prepare | 418.266 | 338.133 | 338.094 | 294.464 | 321.702 | 294.464 | 418.266 | 123.802 | 342.132 | 338.094 | 46.147 | 0.1349 |
| vae_load | 132.040 | 144.054 | 129.854 | 117.297 | 112.588 | 112.588 | 144.054 | 31.466 | 127.167 | 129.854 | 12.511 | 0.0984 |
| sampling | 6083.058 | 5811.946 | 5984.489 | 5998.909 | 5903.502 | 5811.946 | 6083.058 | 271.113 | 5956.381 | 5984.489 | 102.839 | 0.0173 |
| sampler_tail | 0.011 | 0.012 | 0.016 | 0.010 | 0.014 | 0.010 | 0.016 | 0.006 | 0.012 | 0.012 | 0.002 | 0.1911 |
| vae_decode | 515.677 | 509.672 | 524.717 | 539.203 | 528.986 | 509.672 | 539.203 | 29.530 | 523.651 | 524.717 | 11.516 | 0.0220 |
| output | 158.722 | 159.698 | 161.627 | 161.928 | 167.983 | 158.722 | 167.983 | 9.260 | 161.992 | 161.627 | 3.605 | 0.0223 |
| teardown | 0.269 | 0.273 | 0.283 | 0.305 | 0.336 | 0.269 | 0.336 | 0.066 | 0.293 | 0.283 | 0.028 | 0.0945 |
| request_wall | 37058.298 | 34616.894 | 95756.551 | 146987.959 | 43586.186 | 34616.894 | 146987.959 | 112371.065 | 71601.178 | 43586.186 | 49021.772 | 0.6847 |

The stage rows use authoritative recorder walls from the five counted raw
artifacts. `external_restore` is the artifact `restore_total_ms`; `request_wall`
is artifact `duration_ms`. Excluded attempts remain available in the appendices
and are not aggregated.

### Chronological R4 → R8 boundary evidence

| role | dispatch | provider / region | container session / task | image | snapshot identity | capture generation | guard |
|---|---|---|---|---|---|---|---|
| R4 | 2026-09-03T20:52:43.901Z | GCP / us-east1 | `d0a119fd473d4a70` / `ta-01M1MGS448VWM4H6BFR1QJG77R` | `im-ePFELJ6kupZheff9gMDgEC` | `b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37` | `642ee9db1d6104ccbd60a7af118025a047dd5a31e4039e5165ac7ad5029e2eb5` | ELIGIBLE/idle/transition none |
| R5 | 2026-09-03T20:55:46.153Z | AWS / eu-south-2 | `e208413610144ca2` / `ta-01M1MGWTCG8KEYMHVEV8YMAAMR` | `im-ePFELJ6kupZheff9gMDgEC` | same snapshot identity | `b7a7a4cf3a4a22c3464b3c9bf81b385d8edb390daa6b14e7d5154ee66e436b04` | ELIGIBLE/idle/transition none |
| R6 | 2026-09-03T21:05:48.190Z | AWS / eu-south-2 | `e208413610144ca2` / `ta-01M1MHF642SJ7939BVATZVPXPR` | `im-ePFELJ6kupZheff9gMDgEC` | same snapshot identity | same R5 generation | ELIGIBLE/idle/transition none |
| R7 | 2026-09-03T22:11:53.237Z | GCP / us-east4 | `d0a119fd473d4a70` / `ta-01M1MNBKSAVYKRE336H1BN9N8R` | `im-ePFELJ6kupZheff9gMDgEC` | same snapshot identity | `642ee9db1d6104ccbd60a7af118025a047dd5a31e4039e5165ac7ad5029e2eb5` | ELIGIBLE/idle/transition none |
| R8 | 2026-09-03T22:15:49.088Z | GCP / us-east1 | `d0a119fd473d4a70` / `ta-01M1MNFMT8PEQZ9YSMY8G9N85R` | `im-ePFELJ6kupZheff9gMDgEC` | same snapshot identity | same R7 generation | ELIGIBLE/idle/transition none |

Deterministic boundary rule: R5/R6 are the one operator-established provider/
region boundary candidate and its immediate follower. Provider change alone is
not proof: R5 has no direct capture ID or capture timestamp, and its guard is
preserved as idle/no-transition. R7's AWS→GCP transition alone does not create
another exclusion because no explicit capture evidence or operator override
exists and its guard is ELIGIBLE/idle/transition none. R8 is a subsequent
eligible request. The shared image, snapshot identity, container-session change,
and capture-generation values above are retained as evidence, not inferred
capture proof.

### Eligibility and E27 result matrix

| role | counted | CLIP E27 | UNET E27 | VAE E27 | raw artifact result |
|---|---:|---|---|---|---|
| S | no | YES | YES | YES | operator-asserted snapshot capture; excluded despite ELIGIBLE/idle guard |
| P | no | YES | YES | NO | direct follower after S; excluded: `max_actual_source_inflight` |
| R1 | yes | YES | YES | YES | valid; SHA match |
| R2 | no | NO | YES | NO | excluded: CLIP/VAE E27 predicates |
| R3 | yes | YES | YES | YES | valid; SHA match |
| R4 | yes | YES | YES | YES | valid; SHA match |
| R5 | no | YES | YES | YES | quarantined: provider/region transition-boundary candidate; raw artifact retained |
| R6 | no | YES | YES | NO | excluded: immediate follower and `max_actual_source_inflight`; raw artifact retained |
| R7 | yes | YES | YES | NO | canonical-valid; counted; independent VAE anomaly: `max_actual_source_inflight` |
| R8 | yes | YES | YES | NO | canonical-valid; counted; independent VAE anomaly: `max_actual_source_inflight` |

Each preserved live artifact request is `true_cold=true`, `valid=true`, and has
`output_sha_match=true` where observed. Provider/region observations and
snapshot eligibility are:

| role | request ID | provider | region | snapshot eligibility |
|---|---|---|---|---|
| R1 | `golden-p1-0-5563949c90ad` | `CLOUD_PROVIDER_GCP` | `us-east4` | counted |
| R2 | `golden-p1-0-7a23d7251359` | `CLOUD_PROVIDER_GCP` | `us-east1` | excluded: CLIP/VAE E27 failure |
| R3 | `golden-p1-0-bedd2c24af6e` | `CLOUD_PROVIDER_GCP` | `us-east4` | counted |
| R4 | `golden-p1-0-320e378e38ab` | `CLOUD_PROVIDER_GCP` | `us-east1` | counted |
| R5 | `golden-p1-0-df455320d250` | `CLOUD_PROVIDER_AWS` | `eu-south-2` | quarantined: transition-boundary candidate |
| R6 | `golden-p1-0-a8687cc077ab` | `CLOUD_PROVIDER_AWS` | `eu-south-2` | excluded: immediate follower and VAE E27 NO/max_actual_source_inflight |
| R7 | `golden-p1-0-48d498cafa08` | `CLOUD_PROVIDER_GCP` | `us-east4` | counted: canonical-valid despite VAE E27 NO/max_actual_source_inflight |
| R8 | `golden-p1-0-96631c1bf371` | `CLOUD_PROVIDER_GCP` | `us-east1` | counted: canonical-valid despite VAE E27 NO/max_actual_source_inflight |

### Stage rows

The complete five-run stage table and min/max/range/mean/median/sample-SD/CV
statistics are above. Values are calculated only from `R1,R3,R4,R7,R8`.

## CLIP / UNET / VAE decomposition

The following transport rows are aggregated from the raw artifact fields; nested
intervals are explanatory and non-additive to their enclosing stage walls.

| metric | R1 | R3 | R4 | R7 | R8 | min | max | range | mean | median | sample SD | CV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLIP source wall | 1198.495 | 792.250 | 1142.908 | 964.662 | 1139.780 | 792.250 | 1198.495 | 406.245 | 1047.619 | 1139.780 | 167.655 | 0.1600 |
| CLIP syscall union | 1174.532 | 786.999 | 1138.768 | 960.617 | 1135.535 | 786.999 | 1174.532 | 387.533 | 1039.290 | 1135.535 | 163.775 | 0.1576 |
| CLIP H2D wall | 1183.600 | 783.122 | 1141.740 | 952.872 | 1131.706 | 783.122 | 1183.600 | 400.478 | 1038.608 | 1131.706 | 168.040 | 0.1618 |
| CLIP source → GPU ready | 1199.840 | 795.218 | 1143.972 | 966.648 | 1142.180 | 795.218 | 1199.840 | 404.622 | 1049.571 | 1142.180 | 167.063 | 0.1592 |
| CLIP source/H2D overlap | 516.074 | 476.558 | 472.343 | 389.868 | 419.450 | 389.868 | 516.074 | 126.207 | 454.859 | 472.343 | 50.004 | 0.1099 |
| CLIP post-source H2D tail | 1.345 | 2.968 | 1.064 | 1.985 | 2.400 | 1.064 | 2.968 | 1.905 | 1.952 | 1.985 | 0.773 | 0.3961 |
| UNET source wall | 2373.912 | 1277.215 | 1593.963 | 1475.792 | 1502.697 | 1277.215 | 2373.912 | 1096.697 | 1644.716 | 1502.697 | 423.693 | 0.2576 |
| UNET syscall union | 2302.659 | 1264.439 | 1588.629 | 1461.676 | 1499.355 | 1264.439 | 2302.659 | 1038.220 | 1623.352 | 1499.355 | 397.805 | 0.2451 |
| UNET H2D wall | 2360.601 | 1269.206 | 1582.762 | 1465.313 | 1492.863 | 1269.206 | 2360.601 | 1091.395 | 1634.149 | 1492.863 | 421.908 | 0.2582 |
| UNET source → GPU ready | 2375.006 | 1279.481 | 1596.180 | 1477.875 | 1503.624 | 1279.481 | 2375.006 | 1095.525 | 1646.433 | 1503.624 | 423.321 | 0.2571 |
| UNET source/H2D overlap | 1017.335 | 781.255 | 656.131 | 657.437 | 650.411 | 650.411 | 1017.335 | 366.924 | 752.514 | 657.437 | 157.885 | 0.2098 |
| UNET post-source H2D tail | 1.094 | 2.266 | 2.217 | 2.082 | 0.927 | 0.927 | 2.266 | 1.339 | 1.718 | 2.082 | 0.651 | 0.3793 |
| VAE source wall | 66.565 | 69.563 | 80.645 | 55.886 | 62.374 | 55.886 | 80.645 | 24.759 | 67.007 | 66.565 | 9.191 | 0.1372 |
| VAE syscall union | 64.251 | 68.190 | 77.122 | 53.586 | 60.321 | 53.586 | 77.122 | 23.536 | 64.694 | 64.251 | 8.795 | 0.1359 |
| VAE H2D wall | 55.685 | 60.848 | 71.404 | 41.564 | 54.184 | 41.564 | 71.404 | 29.841 | 56.737 | 55.685 | 10.838 | 0.1910 |
| VAE source → GPU ready | 68.466 | 78.075 | 82.628 | 59.130 | 64.754 | 59.130 | 82.628 | 23.498 | 70.611 | 68.466 | 9.628 | 0.1364 |
| VAE source/H2D overlap | 23.253 | 46.517 | 45.019 | 16.380 | 45.251 | 16.380 | 46.517 | 30.137 | 35.284 | 45.019 | 14.339 | 0.4064 |
| VAE post-source H2D tail | 1.901 | 8.511 | 1.983 | 3.244 | 2.381 | 1.901 | 8.511 | 6.610 | 3.604 | 2.381 | 2.794 | 0.7753 |

CLIP transport: 243 reads/4 opens, 8044936192 source bytes, 243 submits and
243 completions per counted artifact; header parse, staging, adoption, and
compute-ready evidence are present. UNET transport: 370 reads/4 opens,
12309817472 source bytes, 613 submits and 613 completions per run, 453/453
same-storage adoption, and zero fallback. VAE transport: 13 reads/4 opens,
335278732 source bytes, 626 submits and 626 completions per run; R7 and R8
retain VAE E27=NO/max_actual_source_inflight despite otherwise canonical validity.
All counted artifacts are poison=false, fallback_count=0, and quiescence-proven.
Any raw null transport field is rendered `UNAVAILABLE`; no value is inferred.

## Invariants

Per-attempt invariant values are printed from the explicit artifact below.

* `restore_count=1`, `request_count=1`, `true_cold=true`, and output SHA match are not cohort statistics.
* Teardown and seriality are reported only when the artifact proves them.

## Per-attempt appendices

### attempt_0_source_probe_blocked

role=`INVALID_UNCOUNTED` classification=`BLOCKED_PREFLIGHT`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_0_source_probe_blocked / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_0_source_probe_blocked / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe_utf8.txt` — 948 bytes, sha256 `516cdd27692dc4c52f061fd8f305108109be10d2e7a6a104326ea9c7d720c26b`.

```text
��p y t h o n . e x e   :   E R R O R :   p u b l i s h e r   p r e f l i g h t   i s   n o t   r e a d y   f o r   c o n s u m e r   d e p l o y :   d e c i s i o n = p u b l i s h _ r e q u i r e d   
 
 b o o t s t r a p _ r e q u i r e d = F a l s e 
 
 A t   l i n e : 1   c h a r : 4 1 0 
 
 +   . . .   r i f t . t x t ' ) ;   &   p y t h o n   t o o l s / v 2 c t l . p y   - - p r o f i l e   g o l d e n _ p 1   - - a p p   s e p t - u n   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( E R R O R :   p u b l i s h e . . . _ r e q u i r e d = F a l s e : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 
```

#### attempt_0_source_probe_blocked / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_0_source_probe_blocked / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / blocked stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe_utf8.txt` — 948 bytes, sha256 `516cdd27692dc4c52f061fd8f305108109be10d2e7a6a104326ea9c7d720c26b`.

```text
��p y t h o n . e x e   :   E R R O R :   p u b l i s h e r   p r e f l i g h t   i s   n o t   r e a d y   f o r   c o n s u m e r   d e p l o y :   d e c i s i o n = p u b l i s h _ r e q u i r e d   
 
 b o o t s t r a p _ r e q u i r e d = F a l s e 
 
 A t   l i n e : 1   c h a r : 4 1 0 
 
 +   . . .   r i f t . t x t ' ) ;   &   p y t h o n   t o o l s / v 2 c t l . p y   - - p r o f i l e   g o l d e n _ p 1   - - a p p   s e p t - u n   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( E R R O R :   p u b l i s h e . . . _ r e q u i r e d = F a l s e : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 
```

#### attempt_0_source_probe_blocked / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_0_source_probe_blocked / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "No Golden request was issued; no authoritative request-time capture guard record exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_1_source_probe_no_flag_retry

role=`INVALID_UNCOUNTED` classification=`BLOCKED_PREFLIGHT`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_1_source_probe_no_flag_retry / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_10_source_probe_no_flag.txt` — 609 bytes, sha256 `1d10958306a8ca8c7fe0a33fbac092c95bba4f10dab546afcdd755d472bb04a1`.

```text
python : [v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote

receipt (source drift is warning-only)

At line:1 char:1

+ python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-tran ...

+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    + CategoryInfo          : NotSpecified: ([v2ctl.source-p...s warning-only):String) [], RemoteException

    + FullyQualifiedErrorId : NativeCommandError


ERROR: publisher preflight is not ready for consumer deploy: decision=publish_required bootstrap_required=False


```

#### attempt_1_source_probe_no_flag_retry / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_1_source_probe_no_flag_retry / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "Source-probe failed before any Golden request; no authoritative request-time capture guard record exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_2_source_probe_flag_suffix

role=`INVALID_UNCOUNTED` classification=`SOURCE_PROBE_INTERFACE_REJECTED_FLAG`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_2_source_probe_flag_suffix / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_12_source_probe_flag.txt` — 882 bytes, sha256 `18dfea1bb2a717d58ec215f45a854928c7029b737de7078e71e740386f5d43a2`.

```text
python : usage: v2ctl [-h] [--profile PROFILE] [--set NAME=VALUE] [--inherit NAME]

At line:1 char:1

+ python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-tran ...

+ ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    + CategoryInfo          : NotSpecified: (usage: v2ctl [-...--inherit NAME]:String) [], RemoteException

    + FullyQualifiedErrorId : NativeCommandError


             [--owner OWNER] [--dry-run] [--json] [--app APP]

             [--workspace WORKSPACE_ID] [--environment ENVIRONMENT]

             [--gpu GPU] [--memory-mb MEMORY_MB] [--cpu CPU]

             [--run-count RUN_COUNT] [--allow-production]

             {version,doctor,config,flags,deploy,deploy-run,run,gate,confirm,golden,source-probe,runtime-flags,lock}

             ...

v2ctl: error: unrecognized arguments: --acknowledge-volume-drift


```

#### attempt_2_source_probe_flag_suffix / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_2_source_probe_flag_suffix / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "Source-probe argument parsing failed before any Golden request; no authoritative request-time capture guard record exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_3_source_probe_flag_global

role=`INVALID_UNCOUNTED` classification=`SOURCE_PROBE_INTERFACE_REJECTED_FLAG`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_3_source_probe_flag_global / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_14_source_probe_flag_position.txt` — 892 bytes, sha256 `4d5ff59f9b6491a34cd857b6ece79fbb44f234acde80b1de39cea9b26430c3f8`.

```text
python : usage: v2ctl [-h] [--profile PROFILE] [--set NAME=VALUE] [--inherit NAME]

At line:1 char:677

+ ... ='utf-8')"; python tools/v2ctl.py --profile golden_p1 --app sept-unet ...

+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    + CategoryInfo          : NotSpecified: (usage: v2ctl [-...--inherit NAME]:String) [], RemoteException

    + FullyQualifiedErrorId : NativeCommandError


             [--owner OWNER] [--dry-run] [--json] [--app APP]

             [--workspace WORKSPACE_ID] [--environment ENVIRONMENT]

             [--gpu GPU] [--memory-mb MEMORY_MB] [--cpu CPU]

             [--run-count RUN_COUNT] [--allow-production]

             {version,doctor,config,flags,deploy,deploy-run,run,gate,confirm,golden,source-probe,runtime-flags,lock}

             ...

v2ctl: error: unrecognized arguments: --acknowledge-volume-drift


```

#### attempt_3_source_probe_flag_global / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_3_source_probe_flag_global / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "Source-probe argument parsing failed before any Golden request; no authoritative request-time capture guard record exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_4_flagged_golden_run_S

role=`PRE_CAPTURE_UNCOUNTED` classification=`BLOCKED_SOURCE_PROBE_REQUIRED`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_4_flagged_golden_run_S / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / source-probe stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / blocked stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_17_run_S.txt` — 1043 bytes, sha256 `7bca7f7b026ee99b76f8ab658ac732e24e37c33e74f65970309b6166a089f1ec`.

```text
ATTEMPT=S
COMMAND=python tools/v2ctl.py golden run --app sept-unetclip-01-transport-core --acknowledge-volume-drift
EXIT_CODE=1
FLAG_USED=true
COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT=1
DEPLOYMENT_REUSE_REQUESTED=f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919
REMOTE_REQUEST_ISSUED=false
AUTHORITATIVE_CAPTURE_GUARD=NOT_OBSERVED
python.exe : [v2ctl.run] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt
(source drift is warning-only)

At line:1 char:71

+ ... run_S.txt'; & python tools/v2ctl.py golden run --app sept-unetclip-01 ...

+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    + CategoryInfo          : NotSpecified: ([v2ctl.run] WAR...s warning-only):String) [], RemoteException

    + FullyQualifiedErrorId : NativeCommandError


[v2ctl.run] WARNING: operator acknowledged volume drift; skipping exact-content publisher preflight gate

ERROR: Golden requires successful source-probe evidence bound to the deployment receipt


```

#### attempt_4_flagged_golden_run_S / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_4_flagged_golden_run_S / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "The flagged golden run was rejected before a remote Golden request was issued; no authoritative request-time capture guard/event exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_5_source_probe_direct_operator_retry

role=`INVALID_UNCOUNTED` classification=`BLOCKED_PREFLIGHT`
invocation_id=`UNAVAILABLE` request_id=`UNAVAILABLE`

#### attempt_5_source_probe_direct_operator_retry / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_19_source_probe_retry.txt` — 1210 bytes, sha256 `c31bba3cfdf124ceacae5fb8a7dee3cbdfdcf79eb5b482d0c36ae674cc8a5a42`.

```text
��p y t h o n . e x e   :   [ v 2 c t l . s o u r c e - p r o b e ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   
 
 r e m o t e   r e c e i p t   ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 1 
 
 +   &   p y t h o n   t o o l s / v 2 c t l . p y   - - p r o f i l e   g o l d e n _ p 1   - - a p p   s e p t - u n e t c l i p - 0 1 - t r   . . . 
 
 +   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . s o u r c e - p . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 E R R O R :   p u b l i s h e r   p r e f l i g h t   i s   n o t   r e a d y   f o r   c o n s u m e r   d e p l o y :   d e c i s i o n = p u b l i s h _ r e q u i r e d   b o o t s t r a p _ r e q u i r e d = F a l s e 
 
 
```

#### attempt_5_source_probe_direct_operator_retry / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / run stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / run manifest

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / attempt artifact

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / blocked stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_19_source_probe_retry.txt` — 1210 bytes, sha256 `c31bba3cfdf124ceacae5fb8a7dee3cbdfdcf79eb5b482d0c36ae674cc8a5a42`.

```text
��p y t h o n . e x e   :   [ v 2 c t l . s o u r c e - p r o b e ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   
 
 r e m o t e   r e c e i p t   ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 1 
 
 +   &   p y t h o n   t o o l s / v 2 c t l . p y   - - p r o f i l e   g o l d e n _ p 1   - - a p p   s e p t - u n e t c l i p - 0 1 - t r   . . . 
 
 +   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . s o u r c e - p . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 E R R O R :   p u b l i s h e r   p r e f l i g h t   i s   n o t   r e a d y   f o r   c o n s u m e r   d e p l o y :   d e c i s i o n = p u b l i s h _ r e q u i r e d   b o o t s t r a p _ r e q u i r e d = F a l s e 
 
 
```

#### attempt_5_source_probe_direct_operator_retry / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_5_source_probe_direct_operator_retry / capture-guard record

```json
{
  "classification": "NOT_OBSERVED",
  "counted": false,
  "note": "Source-probe refused before any Golden request; no authoritative request-time capture guard record exists.",
  "transition": "none",
  "valid": false
}
```

### attempt_6_S_first_live_request

role=`OPERATOR_ASSERTED_SNAPSHOT_CAPTURE` classification=`ACCEPT_EXACT_VALID`
invocation_id=`ecb67ccb2cdb42dbbf6b983566e68ab2` request_id=`golden-p1-0-0d8fa65c47f6`

#### Available stage/invariant values

* `duration_ms`: `199035.417`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east4`
* `clip_forward_ms`: `1649.767334`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `9.436`
* stage `golden_request_setup` wall ms: `1.302`
* stage `golden_clip_load` wall ms: `3046.065`
* stage `golden_clip_forward` wall ms: `1649.767`
* stage `golden_unet_load` wall ms: `3461.089`
* stage `golden_sampler_prepare` wall ms: `323.561`
* stage `golden_vae_load` wall ms: `378.826`
* stage `golden_sampling` wall ms: `6156.627`
* stage `golden_sampler_tail` wall ms: `0.015`
* stage `golden_vae_decode` wall ms: `551.534`
* stage `golden_output` wall ms: `171.046`
* stage `golden_teardown` wall ms: `0.333`

#### attempt_6_S_first_live_request / deployment stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_6_S_first_live_request / pre-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_24_run_S.txt` — 2840 bytes, sha256 `639b4c109e599412da66e923100d246ec4efc1428999ea5cdcdf59d7edf5a1bb`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 1 
 
 +   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r   . . . 
 
 +   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 3 5 2 1 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ e c b 6 7 c c b 2 c d b 4 2 d b _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_6_S_first_live_request / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-153521_4f0dff04.json` — 52171 bytes, sha256 `ec76ba324c26503e009be8d0b633bdecea78fc1547a8a249bbb4bf313c9823fc`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-31-55_a61b6e\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-0d8fa65c47f6",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "ecb67ccb2cdb42dbbf6b983566e68ab2"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-31-55_a61b6e",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-0d8fa65c47f6",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-31-55_a61b6e\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-31-55_a61b6e\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-31-55_a61b6e\\summary.json",
    "v2ctl_invocation_id": "ecb67ccb2cdb42dbbf6b983566e68ab2"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 203.35899999999674,
    "ended_at": "2026-09-03T20:35:18+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:31:54+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:35:21+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "ecb67ccb2cdb42dbbf6b983566e68ab2",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-0d8fa65c47f6",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "ecb67ccb2cdb42dbbf6b983566e68ab2"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "ecb67ccb2cdb42dbbf6b983566e68ab2",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-0d8fa65c47f6",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "ecb67ccb2cdb42dbbf6b983566e68ab2",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "ecb67ccb2cdb42dbbf6b983566e68ab2",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-0d8fa65c47f6",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "ecb67ccb2cdb42dbbf6b983566e68ab2",
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

#### attempt_6_S_first_live_request / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-31-55_a61b6e/attempt_0.json` — 18128504 bytes, sha256 `a7c5f831ce6449e18cc0c83a22cb1d534aa7d8bed47a950490cd897685692e6f`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18128504 sha256=a7c5f831ce6449e18cc0c83a22cb1d534aa7d8bed47a950490cd897685692e6f

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MFP0FG2GQDQ4P07QP8TB3R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MFP0FG2GQDQ4P07QP8TB3R",
      "pid": "2",
      "post_restore_nonce": "812bf2ebc7d04a5d81a17f506bee6805",
      "restore_session_id": "f244ca3d72f24b669393292067624b4d",
      "restored_instance_id": "17dd52e4c36a4050b20801875cb1e804"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MFP0FG2GQDQ4P07QP8TB3R",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MFH5KFY3X6631WRXJT8CF0:1788467517039-0",
    "modal_task_id": "ta-01M1MFP0FG2GQDQ4P07QP8TB3R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "812bf2ebc7d04a5d81a17f506bee6805",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east4",
    "request_count": 1,
    "request_id": "golden-p1-0-0d8fa65c47f6",
    "restore_count": 1,
    "restore_session_id": "f244ca3d72f24b669393292067624b4d",
    "restored_instance_id": "17dd52e4c36a4050b20801875cb1e804",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_6_S_first_live_request / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / derived golden profile summary

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_6_S_first_live_request / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_7_P_direct_follower

role=`P_DIRECT_FOLLOWER` classification=`ACCEPT_EXACT_VALID_E27_VAE_FAILED`
invocation_id=`e83c25a4db6b4dd692f1af1e380579ac` request_id=`golden-p1-0-52ac9eb4ad3a`

#### Available stage/invariant values

* `duration_ms`: `193194.641`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east4`
* `clip_forward_ms`: `1524.605038`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `9.535`
* stage `golden_request_setup` wall ms: `2.697`
* stage `golden_clip_load` wall ms: `1753.407`
* stage `golden_clip_forward` wall ms: `1524.605`
* stage `golden_unet_load` wall ms: `2016.488`
* stage `golden_sampler_prepare` wall ms: `489.140`
* stage `golden_vae_load` wall ms: `125.127`
* stage `golden_sampling` wall ms: `6014.287`
* stage `golden_sampler_tail` wall ms: `0.014`
* stage `golden_vae_decode` wall ms: `512.273`
* stage `golden_output` wall ms: `161.848`
* stage `golden_teardown` wall ms: `0.260`

#### attempt_7_P_direct_follower / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_7_P_direct_follower / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_7_P_direct_follower / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_7_P_direct_follower / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_25_run_P.txt` — 2840 bytes, sha256 `d3a9fa744b18fbdaea97a8ef03fb36caf8cd074511d95fe561aa7473582e0a95`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 1 
 
 +   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r   . . . 
 
 +   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 4 4 3 1 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ e 8 3 c 2 5 a 4 d b 6 b 4 d d 6 _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_7_P_direct_follower / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-154431_4f0dff04.json` — 52171 bytes, sha256 `c3ecd3fb94fcf8cc6fcda032d5463d8433f13fa732e7245458f912c8c01e7657`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-41-11_9bce66\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-52ac9eb4ad3a",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "e83c25a4db6b4dd692f1af1e380579ac"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-41-11_9bce66",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-52ac9eb4ad3a",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-41-11_9bce66\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-41-11_9bce66\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-41-11_9bce66\\summary.json",
    "v2ctl_invocation_id": "e83c25a4db6b4dd692f1af1e380579ac"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 196.89100000000326,
    "ended_at": "2026-09-03T20:44:27+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:41:10+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:44:31+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "e83c25a4db6b4dd692f1af1e380579ac",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-52ac9eb4ad3a",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "e83c25a4db6b4dd692f1af1e380579ac"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "e83c25a4db6b4dd692f1af1e380579ac",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-52ac9eb4ad3a",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "e83c25a4db6b4dd692f1af1e380579ac",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "e83c25a4db6b4dd692f1af1e380579ac",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-52ac9eb4ad3a",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "e83c25a4db6b4dd692f1af1e380579ac",
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

#### attempt_7_P_direct_follower / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-41-11_9bce66/attempt_0.json` — 18101408 bytes, sha256 `4f9f35de8b67f87c066f5aac13e37107f8be3cf468c1498385357979755f12f9`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18101408 sha256=4f9f35de8b67f87c066f5aac13e37107f8be3cf468c1498385357979755f12f9

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MG6ZXD4FAT9B9AK004BFSR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MG6ZXD4FAT9B9AK004BFSR",
      "pid": "2",
      "post_restore_nonce": "d3f16ea628e24bf0a318e0fe71b56cbc",
      "restore_session_id": "ee8f8d68e12846adbba67f5ad79fe1fa",
      "restored_instance_id": "39aa376226ad40ed9c3e9f3a669e9110"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MG6ZXD4FAT9B9AK004BFSR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MG247PVDHEWGQS4N9HH8FT:1788468072698-0",
    "modal_task_id": "ta-01M1MG6ZXD4FAT9B9AK004BFSR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "d3f16ea628e24bf0a318e0fe71b56cbc",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east4",
    "request_count": 1,
    "request_id": "golden-p1-0-52ac9eb4ad3a",
    "restore_count": 1,
    "restore_session_id": "ee8f8d68e12846adbba67f5ad79fe1fa",
    "restored_instance_id": "39aa376226ad40ed9c3e9f3a669e9110",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_7_P_direct_follower / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-41-11_9bce66/summary.json` — 19923476 bytes, sha256 `2834c07dfef186a64327b32823bfc8444b8453f6b9e9b644534e4d36b02211b2`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19923476 sha256=2834c07dfef186a64327b32823bfc8444b8453f6b9e9b644534e4d36b02211b2

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_7_P_direct_follower / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_7_P_direct_follower / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_8_R1

role=`R1` classification=`ELIGIBLE`
invocation_id=`1d7995dfe58844ed906d4d4c423ff0a3` request_id=`golden-p1-0-5563949c90ad`

#### Available stage/invariant values

* `duration_ms`: `37058.298`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east4`
* `clip_forward_ms`: `1523.224657`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `9.264`
* stage `golden_request_setup` wall ms: `2.457`
* stage `golden_clip_load` wall ms: `2083.314`
* stage `golden_clip_forward` wall ms: `1523.225`
* stage `golden_unet_load` wall ms: `2746.388`
* stage `golden_sampler_prepare` wall ms: `418.266`
* stage `golden_vae_load` wall ms: `132.040`
* stage `golden_sampling` wall ms: `6083.058`
* stage `golden_sampler_tail` wall ms: `0.011`
* stage `golden_vae_decode` wall ms: `515.677`
* stage `golden_output` wall ms: `158.722`
* stage `golden_teardown` wall ms: `0.269`

#### attempt_8_R1 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_8_R1 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_8_R1 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_8_R1 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_26_run_R1.txt` — 2858 bytes, sha256 `ecf4fa7c9064196ec8bdcf4301d6baafb3e6de1fd895b175d3be98751d233195`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 4 6 4 0 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 1 d 7 9 9 5 d f e 5 8 8 4 4 e d _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_8_R1 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-154640_4f0dff04.json` — 52170 bytes, sha256 `39a41ab0602f5b6393d054f31da7a94ecf2fbff574ea8a04c29eb78952701e2a`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-45-56_b63a19\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-5563949c90ad",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "1d7995dfe58844ed906d4d4c423ff0a3"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-45-56_b63a19",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-5563949c90ad",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-45-56_b63a19\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-45-56_b63a19\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-45-56_b63a19\\summary.json",
    "v2ctl_invocation_id": "1d7995dfe58844ed906d4d4c423ff0a3"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 41.04700000000594,
    "ended_at": "2026-09-03T20:46:36+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:45:55+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:46:40+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "1d7995dfe58844ed906d4d4c423ff0a3",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-5563949c90ad",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "1d7995dfe58844ed906d4d4c423ff0a3"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "1d7995dfe58844ed906d4d4c423ff0a3",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-5563949c90ad",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "1d7995dfe58844ed906d4d4c423ff0a3",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "1d7995dfe58844ed906d4d4c423ff0a3",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-5563949c90ad",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "1d7995dfe58844ed906d4d4c423ff0a3",
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

#### attempt_8_R1 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-45-56_b63a19/attempt_0.json` — 18155332 bytes, sha256 `f2934387a0930e862ece1a1d3c3ddc7dfd80c09c46ee5c0256e93d8f98330893`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18155332 sha256=f2934387a0930e862ece1a1d3c3ddc7dfd80c09c46ee5c0256e93d8f98330893

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MGAWJA3K4QCY0WX0NV3VKR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MGAWJA3K4QCY0WX0NV3VKR",
      "pid": "2",
      "post_restore_nonce": "81b0173f1b4a41e2ae164ac24f44f5a0",
      "restore_session_id": "02090519bd774e0382ed6c5f74159087",
      "restored_instance_id": "31f5fd7f4be74c07b26e992adde48240"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MGAWJA3K4QCY0WX0NV3VKR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MGATP8XK6JVNK1ZB7CA820:1788468357832-0",
    "modal_task_id": "ta-01M1MGAWJA3K4QCY0WX0NV3VKR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "81b0173f1b4a41e2ae164ac24f44f5a0",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east4",
    "request_count": 1,
    "request_id": "golden-p1-0-5563949c90ad",
    "restore_count": 1,
    "restore_session_id": "02090519bd774e0382ed6c5f74159087",
    "restored_instance_id": "31f5fd7f4be74c07b26e992adde48240",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_8_R1 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-45-56_b63a19/summary.json` — 19983368 bytes, sha256 `9de7bd94c2407716b0c417c3b4b97babc1f6e8f372bce65fb2dfdc0486a35360`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19983368 sha256=9de7bd94c2407716b0c417c3b4b97babc1f6e8f372bce65fb2dfdc0486a35360

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_8_R1 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_8_R1 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_9_R2

role=`R2` classification=`EXCLUDED_E27_CLIP_VAE_FAILED`
invocation_id=`31ad35aa48ca42038bdcda1225b3033e` request_id=`golden-p1-0-7a23d7251359`

#### Available stage/invariant values

* `duration_ms`: `49234.997`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `clip_forward_ms`: `1400.382529`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `9.038`
* stage `golden_request_setup` wall ms: `1.186`
* stage `golden_clip_load` wall ms: `1785.903`
* stage `golden_clip_forward` wall ms: `1400.383`
* stage `golden_unet_load` wall ms: `4096.286`
* stage `golden_sampler_prepare` wall ms: `304.059`
* stage `golden_vae_load` wall ms: `183.764`
* stage `golden_sampling` wall ms: `6016.289`
* stage `golden_sampler_tail` wall ms: `0.013`
* stage `golden_vae_decode` wall ms: `514.823`
* stage `golden_output` wall ms: `182.642`
* stage `golden_teardown` wall ms: `0.310`

#### attempt_9_R2 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_9_R2 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_9_R2 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_9_R2 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_27_run_R2.txt` — 2858 bytes, sha256 `f394dc6a84304d09b09eaf59d708bed38312fc987c2b5c29f11e767b04848d22`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 4 9 0 2 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 3 1 a d 3 5 a a 4 8 c a 4 2 0 3 _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_9_R2 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-154902_4f0dff04.json` — 52171 bytes, sha256 `3eda303bf1b482563f7cb0322c89213c137178fe542f1470ecc309acc3851be2`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-48-06_c151bf\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-7a23d7251359",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "31ad35aa48ca42038bdcda1225b3033e"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-48-06_c151bf",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-7a23d7251359",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-48-06_c151bf\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-48-06_c151bf\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-48-06_c151bf\\summary.json",
    "v2ctl_invocation_id": "31ad35aa48ca42038bdcda1225b3033e"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 53.062999999994645,
    "ended_at": "2026-09-03T20:48:58+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:48:05+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:49:02+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "31ad35aa48ca42038bdcda1225b3033e",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-7a23d7251359",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "31ad35aa48ca42038bdcda1225b3033e"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "31ad35aa48ca42038bdcda1225b3033e",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-7a23d7251359",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "31ad35aa48ca42038bdcda1225b3033e",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "31ad35aa48ca42038bdcda1225b3033e",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-7a23d7251359",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "31ad35aa48ca42038bdcda1225b3033e",
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

#### attempt_9_R2 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-48-06_c151bf/attempt_0.json` — 18265061 bytes, sha256 `4780246192309cd7df1aaa58e4e37ae4a9febeb0f45d2cda5212b6e7be6bbee8`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18265061 sha256=4780246192309cd7df1aaa58e4e37ae4a9febeb0f45d2cda5212b6e7be6bbee8

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MGF792YP08V1V5WBQZ1QNR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MGF792YP08V1V5WBQZ1QNR",
      "pid": "2",
      "post_restore_nonce": "9406a69a4c194dee816f4e937d8c765e",
      "restore_session_id": "82d467dc0ccf4e42916a1ee63ad5c71b",
      "restored_instance_id": "633272b667de4c70aeb5904abb0cc36b"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MGF792YP08V1V5WBQZ1QNR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MGES7DK3QQC5V04MGFA905:1788468487406-0",
    "modal_task_id": "ta-01M1MGF792YP08V1V5WBQZ1QNR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "9406a69a4c194dee816f4e937d8c765e",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-7a23d7251359",
    "restore_count": 1,
    "restore_session_id": "82d467dc0ccf4e42916a1ee63ad5c71b",
    "restored_instance_id": "633272b667de4c70aeb5904abb0cc36b",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_9_R2 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-48-06_c151bf/summary.json` — 20098177 bytes, sha256 `51ac6371996163337a4fc788c33fe7fa005141f57a933306c25f2d3e4eca78b5`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=20098177 sha256=51ac6371996163337a4fc788c33fe7fa005141f57a933306c25f2d3e4eca78b5

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_9_R2 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_9_R2 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_10_R3

role=`R3` classification=`ELIGIBLE`
invocation_id=`7e22e9e1eb934dcf804b6f55a43c8a10` request_id=`golden-p1-0-bedd2c24af6e`

#### Available stage/invariant values

* `duration_ms`: `34616.894`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east4`
* `clip_forward_ms`: `1394.86287`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `9.247`
* stage `golden_request_setup` wall ms: `1.280`
* stage `golden_clip_load` wall ms: `1524.003`
* stage `golden_clip_forward` wall ms: `1394.863`
* stage `golden_unet_load` wall ms: `1637.969`
* stage `golden_sampler_prepare` wall ms: `338.133`
* stage `golden_vae_load` wall ms: `144.054`
* stage `golden_sampling` wall ms: `5811.946`
* stage `golden_sampler_tail` wall ms: `0.012`
* stage `golden_vae_decode` wall ms: `509.672`
* stage `golden_output` wall ms: `159.698`
* stage `golden_teardown` wall ms: `0.273`

#### attempt_10_R3 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_10_R3 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_10_R3 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_10_R3 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_28_run_R3.txt` — 2858 bytes, sha256 `773e21afe10473dd855463a203ee4dbb02f94c70c7271de99be1fc06a97eea2c`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 5 1 2 4 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 7 e 2 2 e 9 e 1 e b 9 3 4 d c f _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_10_R3 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-155124_4f0dff04.json` — 52171 bytes, sha256 `17a93f43e669988d95d069818a4da5d9244a089e2a3e70f90540a08a8acb1234`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-50-43_5ec35a\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-bedd2c24af6e",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "7e22e9e1eb934dcf804b6f55a43c8a10"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-50-43_5ec35a",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-bedd2c24af6e",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-50-43_5ec35a\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-50-43_5ec35a\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-50-43_5ec35a\\summary.json",
    "v2ctl_invocation_id": "7e22e9e1eb934dcf804b6f55a43c8a10"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 38.437999999994645,
    "ended_at": "2026-09-03T20:51:21+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:50:42+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:51:24+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "7e22e9e1eb934dcf804b6f55a43c8a10",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-bedd2c24af6e",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "7e22e9e1eb934dcf804b6f55a43c8a10"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "7e22e9e1eb934dcf804b6f55a43c8a10",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-bedd2c24af6e",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "7e22e9e1eb934dcf804b6f55a43c8a10",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "7e22e9e1eb934dcf804b6f55a43c8a10",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-bedd2c24af6e",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "7e22e9e1eb934dcf804b6f55a43c8a10",
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

#### attempt_10_R3 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-50-43_5ec35a/attempt_0.json` — 18167422 bytes, sha256 `914247a0c472e1eecf8d063d479c5e30ce859782f58ffbfea7d0fb9657e726ba`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18167422 sha256=914247a0c472e1eecf8d063d479c5e30ce859782f58ffbfea7d0fb9657e726ba

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MGKKBZYDPP0T86Y4MDJAHR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MGKKBZYDPP0T86Y4MDJAHR",
      "pid": "2",
      "post_restore_nonce": "4916c4bcf8344d4581d6081267619dc7",
      "restore_session_id": "e6b4ac4ca8e542e5805dab2c3f7d2e4a",
      "restored_instance_id": "4016ad06f5ad4d40b68081ac6ecd10cc"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MGKKBZYDPP0T86Y4MDJAHR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MGKJRN2C50QM3WG4CZ0S8Z:1788468644630-0",
    "modal_task_id": "ta-01M1MGKKBZYDPP0T86Y4MDJAHR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "4916c4bcf8344d4581d6081267619dc7",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east4",
    "request_count": 1,
    "request_id": "golden-p1-0-bedd2c24af6e",
    "restore_count": 1,
    "restore_session_id": "e6b4ac4ca8e542e5805dab2c3f7d2e4a",
    "restored_instance_id": "4016ad06f5ad4d40b68081ac6ecd10cc",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_10_R3 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-50-43_5ec35a/summary.json` — 19989698 bytes, sha256 `9ddf42bf6208e44a2b2b65b7869936287e7998a4fbfeb14a6871d9de6e73e044`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19989698 sha256=9ddf42bf6208e44a2b2b65b7869936287e7998a4fbfeb14a6871d9de6e73e044

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_10_R3 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_10_R3 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_11_R4

role=`R4` classification=`ELIGIBLE`
invocation_id=`71cdfa0824d545e5ad5bd77edcfd5ae2` request_id=`golden-p1-0-320e378e38ab`

#### Available stage/invariant values

* `duration_ms`: `95756.551`
* `provider`: `CLOUD_PROVIDER_GCP`
* `region`: `us-east1`
* `clip_forward_ms`: `1498.110733`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `10.350`
* stage `golden_request_setup` wall ms: `1.923`
* stage `golden_clip_load` wall ms: `1938.043`
* stage `golden_clip_forward` wall ms: `1498.111`
* stage `golden_unet_load` wall ms: `1970.840`
* stage `golden_sampler_prepare` wall ms: `338.094`
* stage `golden_vae_load` wall ms: `129.854`
* stage `golden_sampling` wall ms: `5984.489`
* stage `golden_sampler_tail` wall ms: `0.016`
* stage `golden_vae_decode` wall ms: `524.717`
* stage `golden_output` wall ms: `161.627`
* stage `golden_teardown` wall ms: `0.283`

#### attempt_11_R4 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_11_R4 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_11_R4 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_11_R4 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_29_run_R4.txt` — 2858 bytes, sha256 `3c54e300568175b1a844d5bfd56fe912a52a6a97fb6c3a76da6028cfa304b405`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 5 5 4 2 6 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 7 1 c d f a 0 8 2 4 d 5 4 5 e 5 _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_11_R4 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-155426_4f0dff04.json` — 52170 bytes, sha256 `66811a0635c61e8071af33db001a09f0611cc78d517546b42cb7208234b77316`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-52-43_965dac\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-320e378e38ab",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "71cdfa0824d545e5ad5bd77edcfd5ae2"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-52-43_965dac",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-320e378e38ab",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-52-43_965dac\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-52-43_965dac\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-52-43_965dac\\summary.json",
    "v2ctl_invocation_id": "71cdfa0824d545e5ad5bd77edcfd5ae2"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 99.79699999999139,
    "ended_at": "2026-09-03T20:54:22+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:52:42+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T20:54:26+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "71cdfa0824d545e5ad5bd77edcfd5ae2",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-320e378e38ab",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "71cdfa0824d545e5ad5bd77edcfd5ae2"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "71cdfa0824d545e5ad5bd77edcfd5ae2",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-320e378e38ab",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "71cdfa0824d545e5ad5bd77edcfd5ae2",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "71cdfa0824d545e5ad5bd77edcfd5ae2",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-320e378e38ab",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "71cdfa0824d545e5ad5bd77edcfd5ae2",
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

#### attempt_11_R4 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-52-43_965dac/attempt_0.json` — 18165390 bytes, sha256 `f4281074673f87493c75889b40cec76495b5b8fbc32bc32d62026f43ec26ca7b`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18165390 sha256=f4281074673f87493c75889b40cec76495b5b8fbc32bc32d62026f43ec26ca7b

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
      "container_id": "",
      "container_session_id": "d0a119fd473d4a70",
      "container_task_id": "ta-01M1MGS448VWM4H6BFR1QJG77R",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MGS448VWM4H6BFR1QJG77R",
      "pid": "2",
      "post_restore_nonce": "779a55b2c97049bba4e11913103612ef",
      "restore_session_id": "f0f674727b4a4f6caf1b8068d0720e4f",
      "restored_instance_id": "89c30c39046f492f98bb740e3aefc939"
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
    "boot_id": "968cc3f7-2a68-4c46-b08e-588be718f891",
    "cloud": "CLOUD_PROVIDER_GCP",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "d0a119fd473d4a70",
    "container_task_id": "ta-01M1MGS448VWM4H6BFR1QJG77R",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MGQ7VB2H5TYWAPGEXYFG1K:1788468764524-0",
    "modal_task_id": "ta-01M1MGS448VWM4H6BFR1QJG77R",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "779a55b2c97049bba4e11913103612ef",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "us-east1",
    "request_count": 1,
    "request_id": "golden-p1-0-320e378e38ab",
    "restore_count": 1,
    "restore_session_id": "f0f674727b4a4f6caf1b8068d0720e4f",
    "restored_instance_id": "89c30c39046f492f98bb740e3aefc939",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_11_R4 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-52-43_965dac/summary.json` — 19987426 bytes, sha256 `1e35db8a0f5953dbf6eac4b58714ef2d199e29ac6e1baaa1ae949bb3411a6240`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19987426 sha256=1e35db8a0f5953dbf6eac4b58714ef2d199e29ac6e1baaa1ae949bb3411a6240

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_11_R4 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_11_R4 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_12_R5

role=`R5` classification=`QUARANTINED_PROVIDER_REGION_TRANSITION_BOUNDARY_CANDIDATE`
invocation_id=`3c17f4adc157429ca68be0a56f05e1b4` request_id=`golden-p1-0-df455320d250`

#### Available stage/invariant values

* `duration_ms`: `415728.486`
* `provider`: `CLOUD_PROVIDER_AWS`
* `region`: `eu-south-2`
* `clip_forward_ms`: `1877.936007`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `14.218`
* stage `golden_request_setup` wall ms: `3.555`
* stage `golden_clip_load` wall ms: `2515.153`
* stage `golden_clip_forward` wall ms: `1877.936`
* stage `golden_unet_load` wall ms: `2571.070`
* stage `golden_sampler_prepare` wall ms: `544.639`
* stage `golden_vae_load` wall ms: `218.685`
* stage `golden_sampling` wall ms: `6290.903`
* stage `golden_sampler_tail` wall ms: `0.011`
* stage `golden_vae_decode` wall ms: `617.291`
* stage `golden_output` wall ms: `195.330`
* stage `golden_teardown` wall ms: `0.902`

#### attempt_12_R5 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_12_R5 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_12_R5 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_12_R5 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_30_run_R5.txt` — 2858 bytes, sha256 `6ff4f52475b20acd1c2e2476f49bac64ef5c7394a816af1223591a35c6831bda`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 6 0 2 4 8 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 3 c 1 7 f 4 a d c 1 5 7 4 2 9 c _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_12_R5 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-160248_4f0dff04.json` — 52170 bytes, sha256 `b860084742c7fca11c13de32cd9d3f4d8966cbf597c76f923efa4f29699780ad`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-55-45_91aa82\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-df455320d250",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "3c17f4adc157429ca68be0a56f05e1b4"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-55-45_91aa82",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-df455320d250",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-55-45_91aa82\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-55-45_91aa82\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_20-55-45_91aa82\\summary.json",
    "v2ctl_invocation_id": "3c17f4adc157429ca68be0a56f05e1b4"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 419.6570000000065,
    "ended_at": "2026-09-03T21:02:44+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T20:55:44+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T21:02:48+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "3c17f4adc157429ca68be0a56f05e1b4",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-df455320d250",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "3c17f4adc157429ca68be0a56f05e1b4"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "3c17f4adc157429ca68be0a56f05e1b4",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-df455320d250",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "3c17f4adc157429ca68be0a56f05e1b4",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "3c17f4adc157429ca68be0a56f05e1b4",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-df455320d250",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "3c17f4adc157429ca68be0a56f05e1b4",
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

#### attempt_12_R5 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-55-45_91aa82/attempt_0.json` — 18101888 bytes, sha256 `9b206fa6037eae06b10b2281c920d5dd135dbbbc7cef21693839d153248e4516`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18101888 sha256=9b206fa6037eae06b10b2281c920d5dd135dbbbc7cef21693839d153248e4516

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "23720026-f21f-40f5-b9bf-4858a27ba5bd",
      "container_id": "",
      "container_session_id": "e208413610144ca2",
      "container_task_id": "ta-01M1MGWTCG8KEYMHVEV8YMAAMR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MGWTCG8KEYMHVEV8YMAAMR",
      "pid": "2",
      "post_restore_nonce": "db50639d582c415cad206d5089f6b200",
      "restore_session_id": "a0e309822385464e88ef8bdd79975f61",
      "restored_instance_id": "da35ec09e6204637b2c2770b00ffc8ed"
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
    "boot_id": "23720026-f21f-40f5-b9bf-4858a27ba5bd",
    "cloud": "CLOUD_PROVIDER_AWS",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "e208413610144ca2",
    "container_task_id": "ta-01M1MGWTCG8KEYMHVEV8YMAAMR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MGWSVG88D3BX589G8Q67W3:1788468946801-0",
    "modal_task_id": "ta-01M1MGWTCG8KEYMHVEV8YMAAMR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "db50639d582c415cad206d5089f6b200",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "eu-south-2",
    "request_count": 1,
    "request_id": "golden-p1-0-df455320d250",
    "restore_count": 1,
    "restore_session_id": "a0e309822385464e88ef8bdd79975f61",
    "restored_instance_id": "da35ec09e6204637b2c2770b00ffc8ed",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_12_R5 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-55-45_91aa82/summary.json` — 19923924 bytes, sha256 `8d10c518d99cdc8e7f4e119abb6f44edc4ab7c899921fa135fcaed8c9451fd9f`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19923924 sha256=8d10c518d99cdc8e7f4e119abb6f44edc4ab7c899921fa135fcaed8c9451fd9f

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_12_R5 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_12_R5 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_13_R6

role=`R6` classification=`EXCLUDED_IMMEDIATE_FOLLOWER_AND_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT`
invocation_id=`916b7f8cfb5f4a358ad8340bbe013548` request_id=`golden-p1-0-a8687cc077ab`

#### Available stage/invariant values

* `duration_ms`: `45362.772`
* `provider`: `CLOUD_PROVIDER_AWS`
* `region`: `eu-south-2`
* `clip_forward_ms`: `1892.394319`
* `output_sha_match`: `True`
* `output_sha`: `['8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e']`
* `true_cold`: `True`
* `restore_count`: `1`
* `request_count`: `1`
* stage `golden_restore` wall ms: `12.290`
* stage `golden_request_setup` wall ms: `3.487`
* stage `golden_clip_load` wall ms: `2476.126`
* stage `golden_clip_forward` wall ms: `1892.394`
* stage `golden_unet_load` wall ms: `2413.120`
* stage `golden_sampler_prepare` wall ms: `491.405`
* stage `golden_vae_load` wall ms: `207.979`
* stage `golden_sampling` wall ms: `6154.097`
* stage `golden_sampler_tail` wall ms: `0.029`
* stage `golden_vae_decode` wall ms: `605.636`
* stage `golden_output` wall ms: `196.883`
* stage `golden_teardown` wall ms: `0.913`

#### attempt_13_R6 / deployment stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes, sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`.

```text
��[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e 
 
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = 0 0 6 b 8 5 8 1 3 9 1 7   s c h e m a = 2   p o l i c y = 1 
 
 [ v 2 c t l . g o l d e n . p r e - d e p l o y ] 
 
 E X P E R I M E N T _ I D = c d 3 d 7 e 6 f 0 5 9 e 4 6 7 8 8 b d a b e c e 1 8 e 7 0 e 1 b 
 
 M O D A L _ W O R K S P A C E = w s _ e a e f 9 6 0 0 4 d a c 
 
 M O D A L _ E N V I R O N M E N T = ( d e f a u l t ) 
 
 P U B L I S H E R _ A P P = c o m f y u i - c u s t o m - n o d e s - p u b l i s h e r 
 
 P U B L I S H E R _ E X I S T S = Y E S 
 
 P U B L I S H E R _ F U N C T I O N _ E X I S T S = Y E S 
 
 P U B L I S H E R _ V E R S I O N = 8 
 
 L O C A L _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 R E M O T E _ C O N T E N T _ G E N E R A T I O N = 0 0 6 b 8 5 8 1 3 9 1 7 f c e 3 6 a b 5 a 9 f 6 8 b 3 d a d 5 6 b 7 6 1 0 5 0 8 c 5 6 9 c d 9 0 a c 8 d d 4 2 e c c d d 7 6 d 1 
 
 P U B L I C A T I O N _ D E C I S I O N = s k i p _ e x a c t 
 
 D E P L O Y _ L O C K = C L E A R 
 
 R E A D Y _ F O R _ C O N S U M E R _ D E P L O Y = Y E S 
 
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 9 0 3 - 1 4 0 9 1 0 _ f 6 b 5 9 e 4 2 . j s o n 
 
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 1 _ f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 . j s o n 
 
 
```

#### attempt_13_R6 / source-probe stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes, sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`.

```text
Exp01 source-probe after operator publication (no flag; probe has no flag interface).
Command: python tools/v2ctl.py --profile golden_p1 --app sept-unetclip-01-transport-core source-probe
Result: PASS, verdict=MATCH on all 11 modules. MATCH evidence bound to receipt f6b59e42 written.

[v2ctl.source-probe] WARNING: local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)
[v2.modal_target] app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=c4bee234b871
[v2ctl.source-probe] target app=sept-unetclip-01-transport-core class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-ePFELJ6kupZheff9gMDgEC container=d0a119fd473d4a70
[v2ctl.source-probe] remote deployment_combined_hash=efb36dc72c51590e
[v2ctl.source-probe] remote cwd=/root/comfymodal_runtime
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=c156c662172d0803 expected_sha=c156c662172d0803 path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=a84bae8030a79dab expected_sha=a84bae8030a79dab path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=89d3017ae80fbf39 expected_sha=89d3017ae80fbf39 path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=166a4ef3ce15a64b expected_sha=166a4ef3ce15a64b path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH

```

#### attempt_13_R6 / pre-deploy status/doctor

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes, sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`.

```text
��[ v 2 c t l . g o l d e n . s t a t u s ] 
 
 s c h e m a _ v e r s i o n = 2 
 
 p r o f i l e = g o l d e n _ p 1 
 
 t a r g e t = { ' a p p ' :   ' s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' } 
 
 d e p l o y m e n t _ m a n i f e s t = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = N o n e 
 
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e 
 
 d e p l o y m e n t _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e 
 
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e 
 
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r 
 
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2 
 
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6 
 
 d e p l o y e d _ s t a t e _ e r r o r = 
 
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d 
 
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d 
 
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0 
 
 d e p l o y _ l o c k _ a c t i v e = F a l s e 
 
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " s e p t - u n e t c l i p - 0 1 - t r a n s p o r t - c o r e " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' } 
 
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e 
 
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d 
 
 r e a d y = F a l s e 
 
 
```

#### attempt_13_R6 / post-deploy status/doctor

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / run stdout

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_31_run_R6.txt` — 2858 bytes, sha256 `cfa44634b3e5766721134d03215ade193455e941cc90fbf40f580688e5831054`.

```text
��p y t h o n   :   [ v 2 c t l . r u n ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e   r e c e i p t   
 
 ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y ) 
 
 A t   l i n e : 1   c h a r : 2 6 
 
 +   . . .   S e c o n d s   3 5 ;   p y t h o n   t o o l s / v 2 c t l . p y   g o l d e n   r u n   - - a p p   s e p t - u n e t c l i p - 0 1 - t   . . . 
 
 +                                   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ 
 
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . r u n ]   W A R . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n 
 
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r 
 
   
 
 [ v 2 c t l . r u n ]   W A R N I N G :   o p e r a t o r   a c k n o w l e d g e d   v o l u m e   d r i f t ;   s k i p p i n g   e x a c t - c o n t e n t   p u b l i s h e r   p r e f l i g h t   g a t e 
 
 [ v 2 c t l . r u n ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = f 6 b 5 9 e 4 2 9 1 7 5 e a a 7 6 f e c b e 6 0 6 2 a 3 3 c 3 d 2 e 2 c 3 d 7 b e d 5 3 c 3 e 4 f c 2 9 5 b e 9 3 e 6 5 7 9 1 9   r u n _ f i n g e r p r i n t = 4 f 0 d f f 0 4 a 2 7 a 1 0 6 8 f e 2 6 a 3 c 2 9 f b 1 8 d b 8 5 8 4 2 2 a 5 2 3 c 8 5 a 8 6 6 e 8 5 5 e 6 5 4 9 b 5 4 b b a 2 
 
 [ v 2 c t l . r u n ]   c o m m a n d = " C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ r u n _ v 2 _ s i n g l e . b a t "   - - r u n - c o u n t   1   - - g o l d e n - p 1 - e x p e c t e d - o u t p u t - s h a   8 a 9 2 4 4 6 8 9 0 b e b a e c d c 1 0 e b 5 f 2 0 7 7 6 6 a 4 b 0 5 a f 4 0 c a 3 1 3 7 1 0 8 e 2 5 b f e 8 8 d 9 c 1 c 4 4 e   - - a t t e n t i o n - b a c k e n d   p y t o r c h 
 
 [ v 2 c t l . r u n ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ r u n s \ r u n _ 2 0 2 6 0 9 0 3 - 1 6 0 6 3 9 _ 4 f 0 d f f 0 4 . j s o n 
 
 [ v 2 c t l . r u n ]   e v i d e n c e = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ E X P E R I M E N T _ E V I D E N C E _ g o l d e n _ p 1 _ 9 1 6 b 7 f 8 c f b 5 f 4 a 3 5 _ 2 0 2 6 - 0 9 - 0 3 . m d   s t a t u s = O K 
 
 
```

#### attempt_13_R6 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-160639_4f0dff04.json` — 52170 bytes, sha256 `d8434192a93e994d54f30de3fcec883b02980a85015b4dc998e4a1bf3c17f00b`.

```json
{
  "artifacts": {
    "attention_backend": "pytorch",
    "campaign_manifest": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_21-05-47_f6c59e\\manifest.json",
    "console_capture": null,
    "experiment_identity": {
      "attention_backend": "pytorch",
      "attention_backend_configured": "pytorch",
      "attention_backend_resolved": "pytorch",
      "configured_sage_runtime_mode": "auto",
      "profile": "golden_p1",
      "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
      "request_id": "golden-p1-0-a8687cc077ab",
      "resolved_sage_runtime_mode": "baked_cuda",
      "sage_runtime_mode_configured": "auto",
      "sage_runtime_mode_effective_input": "auto",
      "sage_runtime_mode_resolution_source": "golden_env",
      "sage_runtime_mode_resolved": "baked_cuda",
      "v2ctl_invocation_id": "916b7f8cfb5f4a358ad8340bbe013548"
    },
    "output_dir": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_21-05-47_f6c59e",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "provenance_validation_status": "validated",
    "request_id": "golden-p1-0-a8687cc077ab",
    "run_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_21-05-47_f6c59e\\attempt_0.json",
    "run_artifacts": [
      "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_21-05-47_f6c59e\\attempt_0.json"
    ],
    "summary_artifact": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\artifacts\\phase_p1_serial_golden_v1\\cohort_2026-09-03_21-05-47_f6c59e\\summary.json",
    "v2ctl_invocation_id": "916b7f8cfb5f4a358ad8340bbe013548"
  },
  "attention_backend": "pytorch",
  "attention_backend_configured": "pytorch",
  "attention_backend_resolved": "pytorch",
  "backend": {
    "command": "\"C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\run_v2_single.bat\" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e --attention-backend pytorch",
    "elapsed_seconds": 49.15600000000268,
    "ended_at": "2026-09-03T21:06:36+00:00",
    "exit_code": 0,
    "started_at": "2026-09-03T21:05:47+00:00"
  },
  "configured_sage_runtime_mode": "auto",
  "created_at": "2026-09-03T21:06:39+00:00",
  "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "deployment_hash_namespace": "comfy-modal/deployment/v2",
  "deployment_receipt_integrity_digest": "c008c2d40cc1d4814ffb512718ca7f4466ece7b75ccf333040b9481bc9d5dff6",
  "deployment_receipt_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "deployment_version": 1,
  "effective_environment": {
    "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
    "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
    "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
    "COMFYMODAL_MINIMAL_RESTORE": "1",
    "COMFYMODAL_OUTPUT_DURABILITY": "off",
    "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
    "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
    "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
    "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "COMFYMODAL_V2CTL_INVOCATION_ID": "916b7f8cfb5f4a358ad8340bbe013548",
    "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
    "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-a8687cc077ab",
    "resolved_sage_runtime_mode": "baked_cuda",
    "sage_runtime_mode_configured": "auto",
    "sage_runtime_mode_effective_input": "auto",
    "sage_runtime_mode_resolution_source": "golden_env",
    "sage_runtime_mode_resolved": "baked_cuda",
    "v2ctl_invocation_id": "916b7f8cfb5f4a358ad8340bbe013548"
  },
  "fingerprint_algorithm": "canonical-boundary-identity-v2",
  "modal_environment": "(default)",
  "modal_workspace": "ws_eaef96004dac",
  "owner": "golden-p1",
  "profile": "golden_p1",
  "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
  "provenance": {
    "artifact_path": "",
    "artifact_sha256": null,
    "deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
    "effective_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "916b7f8cfb5f4a358ad8340bbe013548",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "git_head": "9f2ce64cfe93b1ae74567b802b30da4c3533e594",
    "owner": "golden-p1",
    "profile": "golden_p1",
    "profile_config_fingerprint": "58f951dd10186474e761945563b4e293f21bc9b7b9682f2a01015f7de2bdc4db",
    "request_id": "golden-p1-0-a8687cc077ab",
    "requested_environment": {
      "APPDATA": "C:\\Users\\parla\\AppData\\Roaming",
      "COMFYMODAL_GOLDEN_QD_TRANSPORT": "static_e27",
      "COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS": "0",
      "COMFYMODAL_MINIMAL_RESTORE": "1",
      "COMFYMODAL_OUTPUT_DURABILITY": "off",
      "COMFYMODAL_SAGE_RUNTIME_MODE": "auto",
      "COMFYMODAL_SAMPLING_DEEP_PROFILE": "blocks",
      "COMFYMODAL_V2CTL_ACKNOWLEDGED_VOLUME_DRIFT": "1",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
      "COMFYMODAL_V2CTL_DEPLOYMENT_HASH_NAMESPACE": "comfy-modal/deployment/v2",
      "COMFYMODAL_V2CTL_DEPLOY_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_INVOCATION_ID": "916b7f8cfb5f4a358ad8340bbe013548",
      "COMFYMODAL_V2CTL_PROFILE": "golden_p1",
      "COMFYMODAL_V2CTL_PROFILE_CONFIG_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2CTL_RUN_FINGERPRINT": "<redacted>",
      "COMFYMODAL_V2_APP_NAME": "sept-unetclip-01-transport-core",
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
    "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
    "runtime_overrides": [],
    "schema_version": 1,
    "target": {
      "app": "sept-unetclip-01-transport-core",
      "class_name": "ModalRuntimeEntrypointV2",
      "method": "run_golden_serial_stream"
    },
    "unregistered_flags": [
      "COMFYMODAL_OUTPUT_DURABILITY"
    ],
    "v2ctl_invocation_id": "916b7f8cfb5f4a358ad8340bbe013548",
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
  "receipt_deploy_fingerprint": "f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919",
  "receipt_manifest_digest": "11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0",
  "receipt_manifest_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\deployments\\deploy_20260903-140910_f6b59e42.json",
  "receipt_profile": "golden_p1",
  "receipt_source_probe_expected": {
    "git_dirty": "M .opencode/skills/comfymodal-golden-ops/SKILL.md\n M tools/v2_control/cli.py\n?? EXPERIMENT_EVIDENCE_golden_p1_0308695d024e41d5_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0474d478ce3245d6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_0ed32930ae864850_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_25606a90ca244cf9_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_2e4d4cdeffde4b3a_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3916d2e167e94868_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_3a982925da824d2d_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_48f7057bc7e3487b_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_5fbe85f45830404f_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74364aa898644799_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_74920442013c440c_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_7bf4f53dfd404c89_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8020d1eccaeb40e2_2026-09-02.md\n?? EXPERIMENT_EVIDENCE_golden_p1_8088a8ce0adc44d0_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b062782af4884be6_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_b55885b5864a47e1_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_ce6827c491ae47be_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f2787dfec45943ae_2026-09-03.md\n?? EXPERIMENT_EVIDENCE_golden_p1_f8514ab2fa8f49ea_2026-09-03.md\n?? RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md\n?? RX9P_M_PROFILER_E27_AND_LOGGING_REPAIR_2026-09-02.md\n?? unetClipExperimentsSeptember/",
    "git_head": "c4bee234b871ac24592d3a4bb81980bb8cb36053",
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
        "mtime_ns": 1788461983223524300,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_qd_transport.py",
        "sha256": "166a4ef3ce15a64bfcd9f08f56acf13ca3dcd258512c11c567703e1d4511a178",
        "size": 149748
      },
      "comfymodal_runtime/golden_serial.py": {
        "mtime_ns": 1788462021305244500,
        "realpath": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\comfymodal_runtime\\golden_serial.py",
        "sha256": "89d3017ae80fbf39097098bf48a26fb427c6ab6f82722564f31fa1f7090f8c6d",
        "size": 526884
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
    "app": "sept-unetclip-01-transport-core",
    "class": "ModalRuntimeEntrypointV2",
    "method": "run_golden_serial_stream"
  },
  "request_id": "golden-p1-0-a8687cc077ab",
  "resolved_sage_runtime_mode": "baked_cuda",
  "run_fingerprint": "4f0dff04a27a1068fe26a3c29fb18db858422a523c85a866e855e6549b54bba2",
  "sage_runtime_mode_configured": "auto",
  "sage_runtime_mode_effective_input": "auto",
  "sage_runtime_mode_resolution_source": "golden_env",
  "sage_runtime_mode_resolved": "baked_cuda",
  "schema_version": 2,
  "source_probe_evidence_path": "C:\\Users\\parla\\OneDrive\\Documents\\AI HUB\\ComfyUI June Install\\ComfyUI\\custom_nodes\\comfyui-modal\\.v2ctl\\source-probes\\probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json",
  "v2ctl_invocation_id": "916b7f8cfb5f4a358ad8340bbe013548",
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

#### attempt_13_R6 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_21-05-47_f6c59e/attempt_0.json` — 18104162 bytes, sha256 `b30c2c5422ba7672ea6ad58fa3d73ed5681cfed4ff9157cf69c82acd7ec84e09`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=18104162 sha256=b30c2c5422ba7672ea6ad58fa3d73ed5681cfed4ff9157cf69c82acd7ec84e09

{
  "capture_guard": {
    "classification": "ELIGIBLE",
    "counted": true,
    "state": {
      "capture_at": "",
      "capture_identity": "",
      "capture_request_id": "",
      "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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
      "config": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
      "deployment": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
      "snapshot": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
    },
    "identity_tokens": {
      "boot_id": "23720026-f21f-40f5-b9bf-4858a27ba5bd",
      "container_id": "",
      "container_session_id": "e208413610144ca2",
      "container_task_id": "ta-01M1MHF642SJ7939BVATZVPXPR",
      "modal_container_id": "",
      "modal_task_id": "ta-01M1MHF642SJ7939BVATZVPXPR",
      "pid": "2",
      "post_restore_nonce": "19d4805fd1bf479cacb9d1dfb6c90288",
      "restore_session_id": "40d114f62b3f4efc9d7ab81e6490fc45",
      "restored_instance_id": "50129ec2738e4291ada4ba2b9a331af4"
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
    "boot_id": "23720026-f21f-40f5-b9bf-4858a27ba5bd",
    "cloud": "CLOUD_PROVIDER_AWS",
    "config_identity": "c684449514b8b4f95b5638613c21a3836b17d3dcff49fb1c0bdd79dcdcab20a7",
    "container_id": "",
    "container_session_id": "e208413610144ca2",
    "container_task_id": "ta-01M1MHF642SJ7939BVATZVPXPR",
    "deployment_combined_hash": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_fingerprint": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "deployment_identity": "efb36dc72c51590e25a94cb375486852fd96b941cac0d01ef56892ec5f946d97",
    "durability_requested": false,
    "image_id": "im-ePFELJ6kupZheff9gMDgEC",
    "min_containers": 0,
    "modal_container_id": "",
    "modal_input_id": "in-01M1MHF5TV24M3PHBTSZAHM5CX:1788469548892-0",
    "modal_task_id": "ta-01M1MHF642SJ7939BVATZVPXPR",
    "output_durability_mode": "off",
    "pid": 2,
    "post_restore_nonce": "19d4805fd1bf479cacb9d1dfb6c90288",
    "process_id": 2,
    "profile_config_fingerprint": "",
    "region": "eu-south-2",
    "request_count": 1,
    "request_id": "golden-p1-0-a8687cc077ab",
    "restore_count": 1,
    "restore_session_id": "40d114f62b3f4efc9d7ab81e6490fc45",
    "restored_instance_id": "50129ec2738e4291ada4ba2b9a331af4",
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
    "snapshot_identity": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37",
    "snapshot_target_fingerprint": "b17b4b9d84cd7183edbc32213e28abf6573c1a82d5edcc009793721825baea37"
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

#### attempt_13_R6 / derived golden profile report

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / derived golden profile gantt

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / derived golden profile summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_21-05-47_f6c59e/summary.json` — 19926470 bytes, sha256 `ffb46c19b0fbb46d3d2885434f9b0812edd1a2835b1eb6dcb5ce2a16cdd7702a`.

```json
[JSON exceeds 200000 bytes; selected required sections are embedded. Full file remains at the audited path.
byte_size=19926470 sha256=ffb46c19b0fbb46d3d2885434f9b0812edd1a2835b1eb6dcb5ce2a16cdd7702a

{
  "capture_guard": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

#### attempt_13_R6 / raw session events

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / raw milestones

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / blocked stdout

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / post-block doctor/status

```
ABSENT — checked explicit path: UNAVAILABLE
```

#### attempt_13_R6 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": {
    "capture_at": "",
    "capture_identity": "",
    "capture_request_id": "",
    "deployment_identity": "{\"app_name\":\"sept-unetclip-01-transport-core\",\"class_name\":\"ModalRuntimeEntrypointV2\",\"deploy_fingerprint\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"deployment_combined_hash\":\"f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919\",\"gpu\":\"rtx-pro-6000\"}",
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

### attempt_14_R7

role=`R7` classification=`ELIGIBLE_CANONICAL_VALID_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT`
invocation_id=`2d87a69c7a6f4fb6ba27ce188f8bd543` request_id=`golden-p1-0-48d498cafa08`
cohort=`cohort_2026-09-03_22-11-52_070d44`

#### Available replacement evidence

* provider/region: `CLOUD_PROVIDER_GCP` / `us-east4`
* `true_cold=true`, `restore_count=1`, `request_count=1`
* exact output SHA: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
* output SHA match: `true`
* capture guard: `ELIGIBLE`, state `idle`, transition `none`
* E27: `CLIP=YES`, `UNET=YES`, `VAE=NO`
* failed predicate: `max_actual_source_inflight`
* counted: `true`

#### attempt_14_R7 / deployment, probe, status/doctor, and stdout

```
ABSENT — no replacement-specific deployment, source-probe, status/doctor, or stdout path was supplied.
```

#### attempt_14_R7 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-171426_4f0dff04.json`

#### attempt_14_R7 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-11-52_070d44/attempt_0.json`

#### attempt_14_R7 / artifact summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-11-52_070d44/summary.json`

#### attempt_14_R7 / evidence report

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md`

#### attempt_14_R7 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": "idle",
  "transition": "none",
  "valid": true
}
```

R7 is counted as canonical-valid. Its VAE E27 result remains prominently
recorded as `NO` because of `max_actual_source_inflight`; all other validity,
guard, coldness, SHA, seriality, poison, fallback, and quiescence facts are
preserved from the raw artifact.

### attempt_15_R8

role=`R8` classification=`ELIGIBLE_CANONICAL_VALID_VAE_E27_FAILED_MAX_ACTUAL_SOURCE_INFLIGHT`
invocation_id=`9b5ce81f587745f6b4bd5949a5604a81` request_id=`golden-p1-0-96631c1bf371`
cohort=`cohort_2026-09-03_22-15-48_7dcd50`

#### Available replacement evidence

* provider/region: `CLOUD_PROVIDER_GCP` / `us-east1`
* `true_cold=true`, `restore_count=1`, `request_count=1`
* exact output SHA: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`
* output SHA match: `true`
* capture guard: `ELIGIBLE`, state `idle`, transition `none`
* E27: `CLIP=YES`, `UNET=YES`, `VAE=NO`
* failed predicate: `max_actual_source_inflight`
* counted: `true`

#### attempt_15_R8 / deployment, probe, status/doctor, and stdout

```
ABSENT — no replacement-specific deployment, source-probe, status/doctor, or stdout path was supplied.
```

#### attempt_15_R8 / run manifest

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-171638_4f0dff04.json`

#### attempt_15_R8 / attempt artifact

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-15-48_7dcd50/attempt_0.json`

#### attempt_15_R8 / artifact summary

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-15-48_7dcd50/summary.json`

#### attempt_15_R8 / evidence report

Path: `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md`

#### attempt_15_R8 / capture-guard record

```json
{
  "classification": "ELIGIBLE",
  "counted": true,
  "state": "idle",
  "transition": "none",
  "valid": true
}
```

R8 is counted as canonical-valid. Its VAE E27 result remains prominently
recorded as `NO` because of `max_actual_source_inflight`; all other validity,
guard, coldness, SHA, seriality, poison, fallback, and quiescence facts are
preserved from the raw artifact.

## Audit path inventory

The manifest is the complete path inventory; every listed path above is rendered or marked ABSENT.

* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/deployments/deploy_20260903-140910_f6b59e42.json` — 17072 bytes — sha256 `11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/deployments/receipt_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json` — 17562 bytes — sha256 `4623dd4e1da2073f8aa7138f4b8c9093eec0f29f77b82326c46c3d1ea2ae64b0`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_00_pre_status_drift.txt` — 5858 bytes — sha256 `aa0eef08803124ad16ebe9f3014ad78bedc0279efda9b7540dda931e0bc66db5`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_01_pre_deploy_status.txt` — 3010 bytes — sha256 `aa925d453f71082364ff343a077bb4b946af4b039539ebcf900f02756ed63ec0`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_02_pre_doctor_drift.txt` — 5832 bytes — sha256 `f36cbc29fdf429f5f1270ce9bbfdd4c81ab7cb19c4d6c076d9879e7950fcbdf6`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_03_pre_deploy_doctor.txt` — 1832 bytes — sha256 `57812293266d6495b91536131d3193dd44b2c5b017d3939e9b4e4a5e12046928`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_04_pre_deploy_drift.txt` — 5832 bytes — sha256 `f36cbc29fdf429f5f1270ce9bbfdd4c81ab7cb19c4d6c076d9879e7950fcbdf6`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console.txt` — 2554 bytes — sha256 `7ae9f6eef368552c91c88b59464e4809f8c326d8bd0c2190ca88cba345295941`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_05_deploy_console_utf8.txt` — 2576 bytes — sha256 `3e1a1742d7bf5ec55ead11ffedb236a2997a9aacd6b2c5488fe03ae4d3bcb3c1`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_06_pre_source_probe_drift.txt` — 5832 bytes — sha256 `f36cbc29fdf429f5f1270ce9bbfdd4c81ab7cb19c4d6c076d9879e7950fcbdf6`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe.txt` — 936 bytes — sha256 `bfd966d61df42df12aa1b6c0b58aecd42c64807a91b5bdabd4fd15238c703068`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_07_source_probe_utf8.txt` — 948 bytes — sha256 `516cdd27692dc4c52f061fd8f305108109be10d2e7a6a104326ea9c7d720c26b`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_08_final_drift_after_stop.txt` — 6013 bytes — sha256 `bfe0492c98e7a3ea3cf611101c3d05440bf8075aff27cb177e40a7403755d618`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_09_drift_before_source_probe_no_flag.txt` — 13316 bytes — sha256 `5cd0f3de6b10d842979dcda3e13bd25ff7ff02cd91cdec1426af0e55472745e5`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_10_source_probe_no_flag.txt` — 609 bytes — sha256 `1d10958306a8ca8c7fe0a33fbac092c95bba4f10dab546afcdd755d472bb04a1`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_11_drift_before_source_probe_flag.txt` — 6939 bytes — sha256 `8c88151289a60e9d4e3775fc09ff87f7c9f5f6bd0ee6a1503a2f666e19714fd8`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_12_source_probe_flag.txt` — 882 bytes — sha256 `18dfea1bb2a717d58ec215f45a854928c7029b737de7078e71e740386f5d43a2`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_13_drift_before_source_probe_flag_position.txt` — 7115 bytes — sha256 `8ea0903290ad73c56c645f05516f74c7510c98959b63c3289003f5ed79a0f2db`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_14_source_probe_flag_position.txt` — 892 bytes — sha256 `4d5ff59f9b6491a34cd857b6ece79fbb44f234acde80b1de39cea9b26430c3f8`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_15_final_drift_after_source_probe_stop.txt` — 7284 bytes — sha256 `0c90e475fe081ceafe05766e118149f20e2e611f74b30fc5b36227f4b7a35fdc`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_16_pre_run_drift.txt` — 3333 bytes — sha256 `86e4b6ff439102812eeb52a5b689366dcb8f5741c0092e3dff86cd6e0d2a5c30`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_17_run_S.txt` — 1043 bytes — sha256 `7bca7f7b026ee99b76f8ab658ac732e24e37c33e74f65970309b6166a089f1ec`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_18_final_stop_drift.txt` — 1442 bytes — sha256 `44a95fdad457eba06e8a9550fdd062efd696b921f48c8fd82996b678c6e9c9c1`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_19_source_probe_retry.txt` — 1210 bytes — sha256 `c31bba3cfdf124ceacae5fb8a7dee3cbdfdcf79eb5b482d0c36ae674cc8a5a42`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_20_direct_operator_diagnosis.txt` — 2323 bytes — sha256 `752e43f77d2bc86061f4986be1fd74a6488c68e13eb0d558b4547a6cf952a069`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_21_publish.txt` — 292 bytes — sha256 `0b2cdad06361219adb25eb6bfb6eeb71739df70f94f0a6d483f37460bec27090`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_22_publish.txt` — 809 bytes — sha256 `b30bece650af07368fc5adaa27b599426b47de5f6962c0fa76171794fac097ab`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_23_source_probe_pass.txt` — 3268 bytes — sha256 `5e7c5085e7c7378f4db1ad38231fa8b3684ff0d03cbe9056003c23ed1773db54`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_24_run_S.txt` — 2840 bytes — sha256 `639b4c109e599412da66e923100d246ec4efc1428999ea5cdcdf59d7edf5a1bb`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/source-probes/probe_1_f6b59e429175eaa76fecbe6062a33c3d2e2c3d7bed53c3e4fc295be93e657919.json` — 10887 bytes — sha256 `d7357801d4ef028709bf2932a8d35d24613f92910f106d0fc38cd2fd79a3081d`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-153521_4f0dff04.json` — 52171 bytes — sha256 `ec76ba324c26503e009be8d0b633bdecea78fc1547a8a249bbb4bf313c9823fc`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/EXPERIMENT_EVIDENCE_golden_p1_ecb67ccb2cdb42db_2026-09-03.md` — 22483750 bytes — sha256 `215f144fdb0beb275fe64778b73abe011446d413450ca1d604407cf3f88b7333`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_20-31-55_a61b6e/attempt_0.json` — 18128504 bytes — sha256 `a7c5f831ce6449e18cc0c83a22cb1d534aa7d8bed47a950490cd897685692e6f`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_deployment_manifest.json` — 17072 bytes — sha256 `11c727a4f6e2a569c27bd7d46600fdb3eef9797677443ac360c4ec58b77bd5d0`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/evidence_text/exp01_deployment_receipt.json` — 17562 bytes — sha256 `4623dd4e1da2073f8aa7138f4b8c9093eec0f29f77b82326c46c3d1ea2ae64b0`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-11-52_070d44/attempt_0.json` — 18171200 bytes — sha256 `fc2e36103925623ce8225a373d0e1f9ea1b92d320378f02f5066ffd1be00c66b`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-11-52_070d44/summary.json` — 19993988 bytes — sha256 `dd3e1245638c51683f73824c38c5034f495080f1ce002aac255e3d6511f7d945`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-171426_4f0dff04.json` — 52171 bytes — sha256 `ba08c4a60481fb0705127bdf9e40891c3daf08eae88cbcd239731847cf90d4bb`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/EXPERIMENT_EVIDENCE_golden_p1_2d87a69c7a6f4fb6_2026-09-03.md` — 23031804 bytes — sha256 `f8fdd8a45f37c879bec1e5a68815a5ef0ad124d202d6e8cca084254d295bd479`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-15-48_7dcd50/attempt_0.json` — 18163323 bytes — sha256 `cb6688939efd6b18adf245204f3f1a282b9fe069ee44f673421e8d1f56c07295`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_22-15-48_7dcd50/summary.json` — 19985151 bytes — sha256 `2e2280d44cdc272301eda1548e89a621a6b42fef1cafd27055e6f931c55415a8`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/.v2ctl/runs/run_20260903-171638_4f0dff04.json` — 52170 bytes — sha256 `240afb985ceded5ed076fe72cdedf62a6ff20a840f4c12f4dd0d111f2f505185`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/EXPERIMENT_EVIDENCE_golden_p1_9b5ce81f587745f6_2026-09-03.md` — 23087195 bytes — sha256 `cf20c787ba16a720db1a7a318cc17b3755a4cca8bd169a9bf2e81cd2809fca37`
* `C:/Users/parla/OneDrive/Documents/AI HUB/ComfyUI June Install/ComfyUI/custom_nodes/comfyui-modal/unetClipExperimentsSeptember/exp01_manifest.json` — 69802 bytes — sha256 `a729e44ce7dcd2bb5212fe96842b3dfd8c8087cbba8d0f124ebe0ffe2f1fddbf`
