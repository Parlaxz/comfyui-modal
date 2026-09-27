# C8 Complete Benchmark Run Log

> Generated from every `v2_*` artifact directory under the benchmark artifact root. This is an inventory and handoff log, not a new benchmark result.

## Scope and completeness

- Artifact root: `C:\Users\parla\.config\superpowers\worktrees\comfymodal-data\benchmarks\runs`
- Artifact directories indexed: **188**
- Run records indexed: **182**
- Incomplete/failed artifact directories indexed: **11**
- Report generated: `2026-08-05T12:14:08`
- Every artifact directory is listed below, including directories without `summary.json`.
- Every available run record is listed below, including excluded and provisional runs.

## Final trimmed conclusion

The decision metric is application wall time excluding platform variance, recorded as `t3b_to_t8_ms`. The final comparison removes the first valid run from each seven-run set and averages runs 2-7.

| Rank | Experiment | App wall excl. platform ms | Total wall ms | Platform scheduling ms |
|---:|---|---:|---:|---:|
| 1 | **TBASE/O0** | **9,147.0** | 15,365.6 | 4,569.6 |
| 2 | Memory-40960 | 9,493.2 | 20,807.3 | 9,562.6 |
| 3 | T1/O0 | 10,709.9 | 21,813.1 | 7,778.0 |
| 4 | TBASE/O3 | 10,733.1 | 17,204.8 | 4,335.7 |
| 5 | CPU-8 | 10,945.8 | 19,693.0 | 6,114.9 |
| 6 | TBASE/O2 | 12,038.9 | 23,436.9 | 8,725.4 |
| 7 | T3/O0 | 12,147.8 | 26,037.5 | 11,549.1 |
| 8 | TBASE/O1 | 12,844.3 | 20,072.2 | 5,054.5 |
| 9 | T2/O0 | 15,628.9 | 31,039.2 | 13,063.6 |

## Validity protocol

- Required deployment wrapper: `deploy_and_run_v2_single.bat`.
- Required execution wrapper: `run_v2_single.bat`.
- `V2_BENCHMARK_RUNS=1` and `V2_BENCHMARK_GAP_SECONDS=0` were used for individual invocations.
- A manual Windows PowerShell `Start-Sleep -Seconds 25` was used between invocations in the corrected runs.
- Snapshot records were excluded when `snapshot_callback_to_command_start_ms` was null.
- Immediate post-snapshot records were excluded.
- Records with zero or missing restore time were excluded.
- Earlier bulk/single-run records made without the required manual delay remain indexed but are not final evidence.
- Final experiment sets contain seven selected valid runs; trimmed summaries use runs 2-7.

## Classification counts

| Classification | Count |
|---|---:|
| `EXCLUDED_SNAPSHOT_OR_RECAPTURE` | 61 |
| `FINAL_SELECTED_TRIMMED` | 54 |
| `FINAL_SELECTED_VALID` | 9 |
| `INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN` | 11 |
| `UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT` | 58 |

## Policy counts among run records

| Policy | Run records |
|---|---:|
| `T1` | 23 |
| `T2` | 38 |
| `T3` | 18 |
| `TBASE` | 76 |

## Selected final artifact sets

| Experiment | Seven selected artifacts |
|---|---|
| TBASE/O0 | `v2_2026-08-05_10-09-00`, `v2_2026-08-05_10-09-53`, `v2_2026-08-05_10-10-41`, `v2_2026-08-05_10-53-31`, `v2_2026-08-05_10-54-25`, `v2_2026-08-05_10-57-26`, `v2_2026-08-05_10-58-23` |
| T1/O0 | `v2_2026-08-05_10-20-06`, `v2_2026-08-05_10-21-12`, `v2_2026-08-05_10-22-16`, `v2_2026-08-05_11-04-18`, `v2_2026-08-05_11-05-31`, `v2_2026-08-05_11-09-10`, `v2_2026-08-05_11-10-11` |
| T2/O0 | `v2_2026-08-05_10-26-34`, `v2_2026-08-05_10-27-34`, `v2_2026-08-05_10-28-56`, `v2_2026-08-05_11-17-18`, `v2_2026-08-05_11-18-17`, `v2_2026-08-05_11-19-54`, `v2_2026-08-05_11-20-51` |
| T3/O0 | `v2_2026-08-05_10-39-22`, `v2_2026-08-05_10-40-22`, `v2_2026-08-05_10-41-20`, `v2_2026-08-05_10-42-44`, `v2_2026-08-05_10-43-39`, `v2_2026-08-05_10-45-05`, `v2_2026-08-05_10-46-35` |
| TBASE/O1 | `v2_2026-08-05_11-27-28`, `v2_2026-08-05_11-28-35`, `v2_2026-08-05_11-31-47`, `v2_2026-08-05_11-32-44`, `v2_2026-08-05_11-33-38`, `v2_2026-08-05_11-34-35`, `v2_2026-08-05_11-35-48` |
| TBASE/O2 | `v2_2026-08-05_11-41-04`, `v2_2026-08-05_11-42-21`, `v2_2026-08-05_11-43-17`, `v2_2026-08-05_11-44-16`, `v2_2026-08-05_11-45-14`, `v2_2026-08-05_11-46-38`, `v2_2026-08-05_11-47-32` |
| TBASE/O3 | `v2_2026-08-05_11-53-15`, `v2_2026-08-05_11-54-23`, `v2_2026-08-05_11-55-17`, `v2_2026-08-05_11-56-11`, `v2_2026-08-05_11-57-17`, `v2_2026-08-05_11-58-11`, `v2_2026-08-05_11-59-07` |
| CPU-8 | `v2_2026-08-05_12-05-23`, `v2_2026-08-05_12-06-33`, `v2_2026-08-05_12-07-34`, `v2_2026-08-05_12-08-29`, `v2_2026-08-05_12-09-28`, `v2_2026-08-05_12-10-25`, `v2_2026-08-05_12-11-22` |
| Memory-40960 | `v2_2026-08-05_12-19-55`, `v2_2026-08-05_12-21-04`, `v2_2026-08-05_12-22-01`, `v2_2026-08-05_12-23-13`, `v2_2026-08-05_12-24-09`, `v2_2026-08-05_12-25-32`, `v2_2026-08-05_12-27-01` |

## Per-artifact inventory

The following section includes every artifact directory. For complete raw structured data, open the referenced `summary.json` and `run_N.json` files in the artifact directory.

### `v2_2026-08-04_02-19-58` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-04_02-24-49` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `ede3035886ef43cc`
- Modal task: `ta-01KZ59D3EKK9G0XATZC5RHS8YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-w7da1aJx9zi28pBZHjfs0Q`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":131455.658,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":131284.645,"generator_create_ms":0.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":360.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":375.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":375.0,"local_receive_to_generator_create_start_ms":374.3,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":374.115,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.359,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.359,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.921,"pre_sampler_ms":7406.502,"restore_total_ms":1171.78,"sampler_ms":3742.667,"snapshot_callback_age_at_restore_ms":53318.271,"snapshot_callback_to_command_start_ms":null,"submit2entry_ms":132272.967,"t3b_to_t8_ms":12895.737,"vae_decode_ms":783.678,"wall_ms":147788.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.156ms unaccounted"]`
- Waterfall stages: `{"application_restore":1171.794173,"captured_timeline_gap":1.1558850000146776,"clip_to_sampler_node":3339.198,"first_node_to_clip":493.763,"local_preparation":369.358656,"modal_handle_submission":374.300544,"modal_scheduling":130711.999104,"output_persistence":252.655717,"post_sampling_transition":698.525142,"prompt_executor_cache_setup":182.382,"remote_local_return":13.9589,"remote_method_setup":374.154043,"remote_return_handoff":2228.493834,"restore_to_method_entry":24.372114,"sampler_node_to_sampling":2153.468817,"sampling":4989.054092,"vae":783.677979}`

### `v2_2026-08-04_02-33-28` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `02b3de9c15fb4ea3`
- Modal task: `ta-01KZ59WY8JK6W0KBP44PH9RGJR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-1bW3HT4Sr4kiCqVKm2rQjU`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":98698.237,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":98563.25,"generator_create_ms":0.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":406.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":406.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":406.0,"local_receive_to_generator_create_start_ms":407.15,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":325.688,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.731,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.731,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.457,"pre_sampler_ms":8140.232,"restore_total_ms":1261.178,"sampler_ms":3710.993,"snapshot_callback_age_at_restore_ms":40482.981,"snapshot_callback_to_command_start_ms":null,"submit2entry_ms":99583.854,"t3b_to_t8_ms":13708.613,"vae_decode_ms":1025.017,"wall_ms":113859.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.628ms unaccounted"]`
- Waterfall stages: `{"application_restore":1261.194521,"captured_timeline_gap":0.6280439999827649,"clip_to_sampler_node":3443.185,"first_node_to_clip":642.066,"local_preparation":394.731008,"modal_handle_submission":407.150292,"modal_scheduling":97896.355372,"output_persistence":252.910515,"post_sampling_transition":569.461477,"prompt_executor_cache_setup":178.588,"remote_local_return":12.515096,"remote_method_setup":325.726674,"remote_return_handoff":228.828858,"restore_to_method_entry":29.142357,"sampler_node_to_sampling":2578.333992,"sampling":5014.829408,"vae":1025.016682}`

### `v2_2026-08-04_02-36-05` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `02b3de9c15fb4ea3`
- Modal task: `ta-01KZ59WY8JK6W0KBP44PH9RGJR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-1bW3HT4Sr4kiCqVKm2rQjU`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7495.352,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6998.542,"generator_create_ms":0.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":375.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":391.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":391.0,"local_receive_to_generator_create_start_ms":397.582,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":174.631,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":16.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.571,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.571,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.931,"pre_sampler_ms":7422.461,"restore_total_ms":1017.197,"sampler_ms":3707.374,"snapshot_callback_age_at_restore_ms":106762.041,"snapshot_callback_to_command_start_ms":99319.374,"submit2entry_ms":8052.137,"t3b_to_t8_ms":12510.523,"vae_decode_ms":513.578,"wall_ms":20204.5}`
- Waterfall warnings: `["reconciliation exceeds tolerance: -548.844ms > 103.436ms"]`
- Waterfall stages: `{"application_restore":1017.210863,"clip_to_sampler_node":3393.938,"first_node_to_clip":289.895,"local_preparation":478.5712,"modal_handle_submission":397.5822,"modal_scheduling":6619.1986,"output_persistence":247.896758,"post_sampling_transition":608.40523,"prompt_executor_cache_setup":275.058,"remote_local_return":13.478648,"remote_method_setup":174.655516,"remote_return_handoff":null,"restore_to_method_entry":27.132634,"sampler_node_to_sampling":2233.246233,"sampling":4946.287275,"vae":513.577546}`

### `v2_2026-08-04_02-36-55` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `02b3de9c15fb4ea3`
- Modal task: `ta-01KZ59WY8JK6W0KBP44PH9RGJR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-1bW3HT4Sr4kiCqVKm2rQjU`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7178.331,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6477.36,"generator_create_ms":0.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":391.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":407.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":407.0,"local_receive_to_generator_create_start_ms":395.86,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":330.113,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.573,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.573,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.274,"pre_sampler_ms":7542.937,"restore_total_ms":821.942,"sampler_ms":3705.773,"snapshot_callback_age_at_restore_ms":156412.422,"snapshot_callback_to_command_start_ms":149243.374,"submit2entry_ms":7496.393,"t3b_to_t8_ms":12459.4,"vae_decode_ms":433.076,"wall_ms":19742.5}`
- Waterfall warnings: `["reconciliation exceeds tolerance: -552.225ms > 101.456ms"]`
- Waterfall stages: `{"application_restore":821.957115,"clip_to_sampler_node":3043.491,"first_node_to_clip":258.638,"local_preparation":543.57344,"modal_handle_submission":396.85966,"modal_scheduling":6237.897972,"output_persistence":221.543325,"post_sampling_transition":545.71797,"prompt_executor_cache_setup":797.415,"remote_local_return":12.999496,"remote_method_setup":330.154095,"remote_return_handoff":null,"restore_to_method_entry":49.667798,"sampler_node_to_sampling":2250.021604,"sampling":4900.47961,"vae":433.075171}`

### `v2_2026-08-04_03-17-02` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-04_03-21-06` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `86792bf4b56f402e`
- Modal task: `ta-01KZ5CM55KM7VD93917ASAE9NR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-y10415SDOLo1gnUEmXmP5M`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":106993.934,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":106662.007,"generator_create_ms":0.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":360.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":360.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":360.0,"local_receive_to_generator_create_start_ms":364.465,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":387.584,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.849,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.849,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.573,"pre_sampler_ms":7739.454,"restore_total_ms":1070.645,"sampler_ms":3732.619,"snapshot_callback_age_at_restore_ms":47868.668,"snapshot_callback_to_command_start_ms":null,"submit2entry_ms":107698.981,"t3b_to_t8_ms":12957.766,"vae_decode_ms":559.832,"wall_ms":121169.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.695ms unaccounted"]`
- Waterfall stages: `{"application_restore":1070.656231,"captured_timeline_gap":0.6952140000212239,"clip_to_sampler_node":3447.933,"first_node_to_clip":372.411,"local_preparation":382.849216,"modal_handle_submission":364.464684,"modal_scheduling":106246.620116,"output_persistence":247.769911,"post_sampling_transition":668.415793,"prompt_executor_cache_setup":166.258,"remote_local_return":10.998288,"remote_method_setup":387.602158,"remote_return_handoff":114.816211,"restore_to_method_entry":24.226817,"sampler_node_to_sampling":2421.45049,"sampling":5069.319066,"vae":559.831693}`

### `v2_2026-08-04_03-26-18` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-04_03-30-11` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `df340c3f29d64331`
- Modal task: `ta-01KZ5D4RXG84T576Q8Y8WABHWR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-2TJxDl5DXQ8b1hC29YsUFF`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":113104.393,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":112660.708,"generator_create_ms":1.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":390.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":390.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":390.0,"local_receive_to_generator_create_start_ms":395.73,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":301.084,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.383,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.383,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.075,"pre_sampler_ms":7875.718,"restore_total_ms":1036.161,"sampler_ms":3777.928,"snapshot_callback_age_at_restore_ms":58507.569,"snapshot_callback_to_command_start_ms":null,"submit2entry_ms":113744.059,"t3b_to_t8_ms":13057.594,"vae_decode_ms":486.409,"wall_ms":127339.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.704ms unaccounted"]`
- Waterfall stages: `{"application_restore":1036.179645,"captured_timeline_gap":0.7043940000003204,"clip_to_sampler_node":3610.647,"first_node_to_clip":666.277,"local_preparation":422.38272,"modal_handle_submission":396.72988,"modal_scheduling":112285.281,"output_persistence":246.108335,"post_sampling_transition":660.170354,"prompt_executor_cache_setup":167.687,"remote_local_return":11.501196,"remote_method_setup":301.112545,"remote_return_handoff":222.074038,"restore_to_method_entry":36.393912,"sampler_node_to_sampling":2152.327367,"sampling":5065.516117,"vae":486.409193}`

### `v2_2026-08-04_03-36-34` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `32a9e35f654c42bd`
- Modal task: `ta-01KZ5DGFNMZHRYR5962JY07N6R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6Scm4USUZJgRSYThDMazIF`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":96479.303,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":95830.733,"generator_create_ms":1.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":594.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":594.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":594.0,"local_receive_to_generator_create_start_ms":598.41,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":300.185,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.119,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.119,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.58,"pre_sampler_ms":8253.193,"restore_total_ms":1254.625,"sampler_ms":3739.4,"snapshot_callback_age_at_restore_ms":42458.308,"snapshot_callback_to_command_start_ms":null,"submit2entry_ms":97125.408,"t3b_to_t8_ms":13420.485,"vae_decode_ms":494.213,"wall_ms":111018.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.669ms unaccounted"]`
- Waterfall stages: `{"application_restore":1254.637694,"captured_timeline_gap":0.6692959999927552,"clip_to_sampler_node":3517.698,"first_node_to_clip":1175.343,"local_preparation":637.118976,"modal_handle_submission":599.410824,"modal_scheduling":95242.773624,"output_persistence":249.517647,"post_sampling_transition":673.017647,"prompt_executor_cache_setup":165.356,"remote_local_return":11.999732,"remote_method_setup":300.244276,"remote_return_handoff":158.48045,"restore_to_method_entry":37.576373,"sampler_node_to_sampling":2121.314559,"sampling":5021.376454,"vae":494.21348}`

### `v2_2026-08-04_03-39-16` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `32a9e35f654c42bd`
- Modal task: `ta-01KZ5DGFNMZHRYR5962JY07N6R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6Scm4USUZJgRSYThDMazIF`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":16364.27,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":17094.553,"generator_create_ms":0.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":359.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":375.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":375.0,"local_receive_to_generator_create_start_ms":373.903,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":468.08,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.421,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.421,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.382,"pre_sampler_ms":16637.971,"restore_total_ms":2389.515,"sampler_ms":3730.396,"snapshot_callback_age_at_restore_ms":124147.324,"snapshot_callback_to_command_start_ms":108004.176,"submit2entry_ms":18195.136,"t3b_to_t8_ms":22064.849,"vae_decode_ms":776.266,"wall_ms":40116.9}`
- Waterfall warnings: `["reconciliation exceeds tolerance: -621.175ms > 203.485ms"]`
- Waterfall stages: `{"application_restore":2389.529214,"clip_to_sampler_node":11586.957,"first_node_to_clip":957.219,"local_preparation":575.420928,"modal_handle_submission":374.901372,"modal_scheduling":15413.947268,"output_persistence":249.279802,"post_sampling_transition":660.990154,"prompt_executor_cache_setup":336.117,"remote_local_return":12.99782,"remote_method_setup":468.10172,"remote_return_handoff":null,"restore_to_method_entry":23.737641,"sampler_node_to_sampling":2529.639018,"sampling":4963.081368,"vae":776.265654}`

### `v2_2026-08-04_03-40-42` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: ``
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `32a9e35f654c42bd`
- Modal task: `ta-01KZ5DGFNMZHRYR5962JY07N6R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6Scm4USUZJgRSYThDMazIF`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":8534.092,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7533.171,"generator_create_ms":0.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":422.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":422.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":422.0,"local_receive_to_generator_create_start_ms":420.858,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":191.798,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.475,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.475,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.499,"pre_sampler_ms":8778.307,"restore_total_ms":587.876,"sampler_ms":3737.887,"snapshot_callback_age_at_restore_ms":203163.389,"snapshot_callback_to_command_start_ms":194640.176,"submit2entry_ms":8676.624,"t3b_to_t8_ms":13682.412,"vae_decode_ms":384.105,"wall_ms":21942.1}`
- Waterfall warnings: `["reconciliation exceeds tolerance: -620.938ms > 112.059ms"]`
- Waterfall stages: `{"application_restore":587.908199,"clip_to_sampler_node":3458.585,"first_node_to_clip":1682.876,"local_preparation":464.47488,"modal_handle_submission":420.85792,"modal_scheduling":7648.759232,"output_persistence":225.566685,"post_sampling_transition":545.716927,"prompt_executor_cache_setup":255.252,"remote_local_return":11.999308,"remote_method_setup":191.86656,"remote_return_handoff":null,"restore_to_method_entry":27.075304,"sampler_node_to_sampling":2148.565184,"sampling":4979.040802,"vae":384.104659}`

### `v2_2026-08-04_19-47-17` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-04_20-04-19` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e7ea2a80dc2f`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `3729a4480eb34f21`
- Modal task: `ta-01KZ7612DQ92HNACD031AFZDCR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-vDgxeHSXHCgp7Dk04vjKdX`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":95633.868,"command_to_response_ms":118328.4,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":15.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":99373.3,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.509,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":439.274,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.895,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.895,"unexplained_pre_remote_ms":98934.025,"worker_unattributed_ms":null},"output_collection_ms":8.929,"pre_sampler_ms":11758.484,"restore_total_ms":3644.955,"sampler_ms":3650.966,"snapshot_callback_age_at_restore_ms":34194.291,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":99373.3,"submit2entry_ms":98933.149,"t3b_to_t8_ms":17112.526,"vae_decode_ms":750.574,"wall_ms":117973.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.501ms unaccounted"]`
- Waterfall stages: `{"application_restore":3644.965025,"captured_timeline_gap":0.5005820000078529,"clip_to_sampler_node":9399.842,"first_node_to_clip":74.399,"local_preparation":350.895232,"modal_handle_submission":9.509368,"modal_scheduling":95273.462792,"output_persistence":208.040943,"post_sampling_transition":739.563641,"prompt_executor_cache_setup":225.721,"remote_local_return":15.510948,"remote_method_setup":439.33274,"remote_return_handoff":1472.39595,"restore_to_method_entry":11.710645,"sampler_node_to_sampling":911.123883,"sampling":4800.847608,"vae":750.574291}`

### `v2_2026-08-04_20-17-54` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-57df8879a1ea`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `87b5459e10184413`
- Modal task: `ta-01KZ76SXXQEVFTABNWGMCV7VKR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":214456.548,"command_to_response_ms":232836.6,"handle_lookup_ms":3.011,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":216413.858,"generator_create_ms":3.011,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.509,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":761.619,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.359,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.359,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.515,"pre_sampler_ms":8547.859,"restore_total_ms":1611.509,"sampler_ms":3711.747,"snapshot_callback_age_at_restore_ms":52918.627,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":216413.858,"submit2entry_ms":215766.133,"t3b_to_t8_ms":13620.867,"vae_decode_ms":603.412,"wall_ms":232437.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.996ms unaccounted"]`
- Waterfall stages: `{"application_restore":1611.521987,"captured_timeline_gap":0.9958650000626221,"clip_to_sampler_node":5396.111,"first_node_to_clip":4.313,"local_preparation":395.358976,"modal_handle_submission":10.519524,"modal_scheduling":214050.66934,"output_persistence":239.799216,"post_sampling_transition":508.047982,"prompt_executor_cache_setup":138.842,"remote_local_return":11.997688,"remote_method_setup":761.642511,"remote_return_handoff":2275.960141,"restore_to_method_entry":100.91489,"sampler_node_to_sampling":1751.496827,"sampling":4975.003549,"vae":603.412992}`

### `v2_2026-08-04_20-24-02` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1acfaeae428c`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `a322297c7e11457a`
- Modal task: `ta-01KZ7754T9M93H9H1N74W6EB9R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":78126.833,"command_to_response_ms":90558.6,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":81738.08,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":45.563,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.782,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.782,"unexplained_pre_remote_ms":81692.517,"worker_unattributed_ms":null},"output_collection_ms":8.86,"pre_sampler_ms":2926.395,"restore_total_ms":3589.929,"sampler_ms":3692.059,"snapshot_callback_age_at_restore_ms":37052.464,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":81738.08,"submit2entry_ms":81332.454,"t3b_to_t8_ms":8279.306,"vae_decode_ms":558.118,"wall_ms":90163.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.584ms unaccounted"]`
- Waterfall stages: `{"application_restore":3589.936765,"captured_timeline_gap":0.5835730000108015,"clip_to_sampler_node":357.896,"first_node_to_clip":44.007,"local_preparation":390.781632,"modal_handle_submission":11.000768,"modal_scheduling":77725.050176,"output_persistence":207.306971,"post_sampling_transition":890.150683,"prompt_executor_cache_setup":175.683,"remote_local_return":12.99998,"remote_method_setup":45.582795,"remote_return_handoff":491.012351,"restore_to_method_entry":14.456955,"sampler_node_to_sampling":967.879133,"sampling":5076.179612,"vae":558.116286}`

### `v2_2026-08-04_20-28-35` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-025030414367`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `57da2ea597114570`
- Modal task: `ta-01KZ77DFJGTT0M9A0GN83EA78R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":98950.102,"command_to_response_ms":110629.4,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":100861.651,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.516,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":55.984,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.429,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.429,"unexplained_pre_remote_ms":100805.668,"worker_unattributed_ms":null},"output_collection_ms":9.146,"pre_sampler_ms":4043.723,"restore_total_ms":1544.98,"sampler_ms":3704.645,"snapshot_callback_age_at_restore_ms":45148.082,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":100861.651,"submit2entry_ms":100228.312,"t3b_to_t8_ms":9235.497,"vae_decode_ms":681.505,"wall_ms":110262.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.245ms unaccounted"]`
- Waterfall stages: `{"application_restore":1544.993138,"captured_timeline_gap":1.2450349999999162,"clip_to_sampler_node":529.029,"first_node_to_clip":1.574,"local_preparation":363.428544,"modal_handle_submission":11.517056,"modal_scheduling":98575.156608,"output_persistence":244.464718,"post_sampling_transition":550.620419,"prompt_executor_cache_setup":214.953,"remote_local_return":12.999408,"remote_method_setup":56.000786,"remote_return_handoff":727.548781,"restore_to_method_entry":104.148863,"sampler_node_to_sampling":1728.059136,"sampling":5282.19881,"vae":681.505706}`

### `v2_2026-08-04_20-42-48` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b04aa483b0d3`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `2bd1141c979e4f2f`
- Modal task: `ta-01KZ787GWT5JDF2SMD6E2A02TR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":76782.478,"command_to_response_ms":89134.1,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":80420.889,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":46.579,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.63,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.63,"unexplained_pre_remote_ms":80374.31,"worker_unattributed_ms":null},"output_collection_ms":9.021,"pre_sampler_ms":2744.809,"restore_total_ms":3675.435,"sampler_ms":3676.972,"snapshot_callback_age_at_restore_ms":37340.254,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":80420.889,"submit2entry_ms":80047.429,"t3b_to_t8_ms":8125.77,"vae_decode_ms":562.007,"wall_ms":88714.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.324ms unaccounted"]`
- Waterfall stages: `{"application_restore":3675.444354,"captured_timeline_gap":1.3243559999973513,"clip_to_sampler_node":206.687,"first_node_to_clip":114.152,"local_preparation":415.630464,"modal_handle_submission":10.999436,"modal_scheduling":76355.847796,"output_persistence":206.980379,"post_sampling_transition":929.488787,"prompt_executor_cache_setup":178.848,"remote_local_return":14.027324,"remote_method_setup":46.645299,"remote_return_handoff":479.277479,"restore_to_method_entry":12.128525,"sampler_node_to_sampling":885.038492,"sampling":5039.525599,"vae":562.006934}`

### `v2_2026-08-04_20-48-42` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2f08292093b5`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `3b65d24ffb0d4053`
- Modal task: `ta-01KZ78JA8K8KT4SNYCGK4VZ1WR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":122666.993,"command_to_response_ms":135020.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":124531.606,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":57.001,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.74,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.74,"unexplained_pre_remote_ms":124474.604,"worker_unattributed_ms":null},"output_collection_ms":10.653,"pre_sampler_ms":4723.627,"restore_total_ms":1543.258,"sampler_ms":3699.851,"snapshot_callback_age_at_restore_ms":63243.19,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":124531.606,"submit2entry_ms":123943.671,"t3b_to_t8_ms":9939.578,"vae_decode_ms":668.872,"wall_ms":134651.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 3.990ms unaccounted"]`
- Waterfall stages: `{"application_restore":1543.34944,"captured_timeline_gap":3.989962999970885,"clip_to_sampler_node":1094.728,"first_node_to_clip":1.774,"local_preparation":364.740288,"modal_handle_submission":11.000412,"modal_scheduling":122291.252132,"output_persistence":257.499629,"post_sampling_transition":579.472374,"prompt_executor_cache_setup":216.378,"remote_local_return":21.028816,"remote_method_setup":57.022878,"remote_return_handoff":689.132489,"restore_to_method_entry":102.585107,"sampler_node_to_sampling":1813.182128,"sampling":5304.884162,"vae":668.870998}`

### `v2_2026-08-04_20-52-32` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-7a90e22cce52`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `538fa8eda0a04a38`
- Modal task: `ta-01KZ78SANR7JZGZTR19J1TTFSR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-Z8DEqj57lKkQ03U4d9nxAc`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":80708.485,"command_to_response_ms":89982.4,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":81211.202,"generator_create_ms":3.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":55.578,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.575,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.575,"unexplained_pre_remote_ms":81155.625,"worker_unattributed_ms":null},"output_collection_ms":9.55,"pre_sampler_ms":2894.81,"restore_total_ms":503.942,"sampler_ms":3674.328,"snapshot_callback_age_at_restore_ms":38079.485,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":81211.202,"submit2entry_ms":80853.216,"t3b_to_t8_ms":8242.348,"vae_decode_ms":569.194,"wall_ms":89613.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.493ms unaccounted"]`
- Waterfall stages: `{"application_restore":503.957228,"captured_timeline_gap":0.49333900000783615,"clip_to_sampler_node":219.002,"first_node_to_clip":28.798,"local_preparation":364.574528,"modal_handle_submission":12.000072,"modal_scheduling":80331.910584,"output_persistence":213.950851,"post_sampling_transition":884.473923,"prompt_executor_cache_setup":328.052,"remote_local_return":23.000508,"remote_method_setup":55.647439,"remote_return_handoff":447.733684,"restore_to_method_entry":13.336953,"sampler_node_to_sampling":934.862313,"sampling":5051.405642,"vae":569.194344}`

### `v2_2026-08-04_21-19-35` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-04_21-22-39` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `summary.json`
- Request ID: `v2-benchmark-0-0ebc52c29380`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `0c4f7d0e8723471d`
- Modal task: `ta-01KZ7AGFHTSMV58WN3NK28SS7R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":93691.799,"command_to_response_ms":143061.7,"handle_lookup_ms":5.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":129009.532,"generator_create_ms":4.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":9.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":441.993,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.141,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.141,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":8.183,"pre_sampler_ms":6533.326,"restore_total_ms":4087.335,"sampler_ms":3723.793,"snapshot_callback_age_at_restore_ms":48972.254,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":129009.532,"submit2entry_ms":128703.105,"t3b_to_t8_ms":11941.171,"vae_decode_ms":534.692,"wall_ms":142636.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.527ms unaccounted"]`
- Waterfall stages: `{"application_restore":4087.361877,"captured_timeline_gap":0.5270180000225082,"clip_to_sampler_node":3687.972,"first_node_to_clip":104.883,"local_preparation":421.14144,"modal_handle_submission":13.00076,"modal_scheduling":93257.65652,"output_persistence":214.484501,"post_sampling_transition":929.618149,"prompt_executor_cache_setup":288.06,"remote_local_return":12.001428,"remote_method_setup":442.051052,"remote_return_handoff":1536.573839,"restore_to_method_entry":31353.067421,"sampler_node_to_sampling":1307.31144,"sampling":4871.341382,"vae":534.690701}`

### `v2_2026-08-04_21-22-39` / run `1`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `summary.json`
- Request ID: `v2-benchmark-1-f5a122cffc86`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `0c4f7d0e8723471d`
- Modal task: `ta-01KZ7AGFHTSMV58WN3NK28SS7R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":93691.799,"command_to_response_ms":168997.9,"handle_lookup_ms":1.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":154.108,"generator_create_ms":1.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":5.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":27.1,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.82,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.82,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":7.152,"pre_sampler_ms":732.52,"restore_total_ms":4087.335,"sampler_ms":3710.554,"snapshot_callback_age_at_restore_ms":48972.254,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":154.108,"submit2entry_ms":-229.053,"t3b_to_t8_ms":5750.14,"vae_decode_ms":335.578,"wall_ms":5891.2}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -4316.915ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":4087.361877,"clip_to_sampler_node":35.584,"first_node_to_clip":54.126,"local_preparation":0.819904,"modal_handle_submission":6.000896,"modal_scheduling":null,"output_persistence":146.855108,"post_sampling_transition":822.744444,"prompt_executor_cache_setup":114.481,"remote_local_return":9.997208,"remote_method_setup":27.122335,"remote_return_handoff":332.974976,"restore_to_method_entry":65101.587606,"sampler_node_to_sampling":41.181166,"sampling":4196.030519,"vae":335.577502}`

### `v2_2026-08-04_21-31-22` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-07df1cd43e1e`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `c1d62fef4a49405b`
- Modal task: `ta-01KZ7B0EQ0P4Z3GS0S77YCRHTR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":98564.487,"command_to_response_ms":118747.9,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":100116.719,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":732.625,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.487,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.487,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":821.065,"pre_sampler_ms":8504.654,"restore_total_ms":1360.154,"sampler_ms":3703.571,"snapshot_callback_age_at_restore_ms":44536.288,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":100116.719,"submit2entry_ms":99590.605,"t3b_to_t8_ms":14406.416,"vae_decode_ms":599.752,"wall_ms":118312.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 808.585ms unaccounted","reconciliation exceeds tolerance: 808.585ms > 593.740ms"]`
- Waterfall stages: `{"application_restore":1360.162364,"captured_timeline_gap":808.5853839999909,"clip_to_sampler_node":5131.616,"first_node_to_clip":35.095,"local_preparation":430.486592,"modal_handle_submission":11.002508,"modal_scheduling":98122.998388,"output_persistence":242.05654,"post_sampling_transition":540.45705,"prompt_executor_cache_setup":156.912,"remote_local_return":11.99858,"remote_method_setup":732.646367,"remote_return_handoff":3772.610995,"restore_to_method_entry":104.43345,"sampler_node_to_sampling":1751.133743,"sampling":4935.953294,"vae":599.752225}`

### `v2_2026-08-04_21-33-49` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-36f43654ed4e`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `c1d62fef4a49405b`
- Modal task: `ta-01KZ7B0EQ0P4Z3GS0S77YCRHTR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6028.919,"command_to_response_ms":42644.6,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":8032.633,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.55,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":775.236,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.651,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.651,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.112,"pre_sampler_ms":28326.411,"restore_total_ms":1963.865,"sampler_ms":3689.321,"snapshot_callback_age_at_restore_ms":98840.09,"snapshot_callback_to_command_start_ms":92845.519,"submission_to_first_remote_event_ms":8032.633,"submit2entry_ms":7694.983,"t3b_to_t8_ms":33389.169,"vae_decode_ms":630.366,"wall_ms":42246.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 57.985ms unaccounted"]`
- Waterfall stages: `{"application_restore":1963.872791,"captured_timeline_gap":57.98477400000411,"clip_to_sampler_node":5498.017,"first_node_to_clip":1340.166,"local_preparation":394.650688,"modal_handle_submission":10.550812,"modal_scheduling":5623.717348,"output_persistence":236.122355,"post_sampling_transition":495.264465,"prompt_executor_cache_setup":2274.61,"remote_local_return":13.507856,"remote_method_setup":775.281064,"remote_return_handoff":554.850143,"restore_to_method_entry":103.383378,"sampler_node_to_sampling":17438.547538,"sampling":5233.659379,"vae":630.366665}`

### `v2_2026-08-04_21-36-49` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8d619f67577a`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `c1d62fef4a49405b`
- Modal task: `ta-01KZ7B0EQ0P4Z3GS0S77YCRHTR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6253.734,"command_to_response_ms":17929.9,"handle_lookup_ms":10.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7670.859,"generator_create_ms":9.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":13.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":652.563,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":16.0,"payload_size_measurement_ms":16.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.728,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.728,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.645,"pre_sampler_ms":4194.525,"restore_total_ms":1430.903,"sampler_ms":3689.248,"snapshot_callback_age_at_restore_ms":278602.267,"snapshot_callback_to_command_start_ms":272406.519,"submission_to_first_remote_event_ms":7670.859,"submit2entry_ms":7345.288,"t3b_to_t8_ms":9036.881,"vae_decode_ms":541.73,"wall_ms":17453.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.591ms unaccounted"]`
- Waterfall stages: `{"application_restore":1430.913558,"captured_timeline_gap":0.5914319999974396,"clip_to_sampler_node":102.268,"first_node_to_clip":170.532,"local_preparation":470.727936,"modal_handle_submission":22.001564,"modal_scheduling":5761.0049,"output_persistence":207.392032,"post_sampling_transition":396.368284,"prompt_executor_cache_setup":878.895,"remote_local_return":17.021272,"remote_method_setup":652.594465,"remote_return_handoff":613.233368,"restore_to_method_entry":143.354869,"sampler_node_to_sampling":1518.796131,"sampling":5002.498495,"vae":541.729766}`

### `v2_2026-08-04_21-43-45` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8ea920536c7c`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `6e22c6fda5de4d23`
- Modal task: `ta-01KZ7BQ3ZBXY77JMX98NYMKF5R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":73271.26,"command_to_response_ms":82923.9,"handle_lookup_ms":4.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":74718.95,"generator_create_ms":4.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":38.829,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.214,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.214,"unexplained_pre_remote_ms":74680.122,"worker_unattributed_ms":null},"output_collection_ms":7.023,"pre_sampler_ms":2447.805,"restore_total_ms":1627.338,"sampler_ms":3671.463,"snapshot_callback_age_at_restore_ms":35491.831,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":74718.95,"submit2entry_ms":74453.539,"t3b_to_t8_ms":7619.523,"vae_decode_ms":495.596,"wall_ms":82472.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.488ms unaccounted"]`
- Waterfall stages: `{"application_restore":1627.350039,"captured_timeline_gap":0.48787099999026395,"clip_to_sampler_node":133.314,"first_node_to_clip":69.888,"local_preparation":447.214016,"modal_handle_submission":12.999184,"modal_scheduling":72811.046896,"output_persistence":185.770094,"post_sampling_transition":812.987196,"prompt_executor_cache_setup":157.957,"remote_local_return":11.998028,"remote_method_setup":38.860466,"remote_return_handoff":345.588498,"restore_to_method_entry":11.126633,"sampler_node_to_sampling":872.834833,"sampling":4888.9127,"vae":495.595874}`

### `v2_2026-08-04_21-45-39` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0a14f6b1ae04`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `6e22c6fda5de4d23`
- Modal task: `ta-01KZ7BQ3ZBXY77JMX98NYMKF5R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4171.278,"command_to_response_ms":24804.2,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6199.326,"generator_create_ms":3.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.797,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.809,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.809,"unexplained_pre_remote_ms":6148.53,"worker_unattributed_ms":null},"output_collection_ms":8.589,"pre_sampler_ms":12832.879,"restore_total_ms":2213.348,"sampler_ms":3719.912,"snapshot_callback_age_at_restore_ms":80394.554,"snapshot_callback_to_command_start_ms":76225.38,"submission_to_first_remote_event_ms":6199.327,"submit2entry_ms":5943.46,"t3b_to_t8_ms":18040.316,"vae_decode_ms":515.715,"wall_ms":24344.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 330.989ms unaccounted","reconciliation exceeds tolerance: 330.989ms > 124.021ms"]`
- Waterfall stages: `{"application_restore":2213.383439,"captured_timeline_gap":330.9889710000025,"clip_to_sampler_node":132.614,"first_node_to_clip":115.445,"local_preparation":454.808768,"modal_handle_submission":13.000332,"modal_scheduling":3703.469172,"output_persistence":204.022278,"post_sampling_transition":762.702967,"prompt_executor_cache_setup":353.902,"remote_local_return":15.258692,"remote_method_setup":50.824598,"remote_return_handoff":294.684489,"restore_to_method_entry":22.599371,"sampler_node_to_sampling":10599.775168,"sampling":5020.966576,"vae":515.714371}`

### `v2_2026-08-04_21-46-25` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-219d821da731`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `6e22c6fda5de4d23`
- Modal task: `ta-01KZ7BQ3ZBXY77JMX98NYMKF5R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6856.5,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":159.728,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.511,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":32.97,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.387,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.387,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":424.832,"pre_sampler_ms":718.951,"restore_total_ms":2213.348,"sampler_ms":3734.992,"snapshot_callback_age_at_restore_ms":80394.554,"snapshot_callback_to_command_start_ms":122113.38,"submission_to_first_remote_event_ms":159.727,"submit2entry_ms":-168.982,"t3b_to_t8_ms":6226.451,"vae_decode_ms":354.006,"wall_ms":6385.7}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1971.457ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2213.383439,"clip_to_sampler_node":63.85,"first_node_to_clip":55.318,"local_preparation":466.387136,"modal_handle_submission":11.512064,"modal_scheduling":null,"output_persistence":151.03569,"post_sampling_transition":850.75345,"prompt_executor_cache_setup":90.625,"remote_local_return":10.121292,"remote_method_setup":33.019267,"remote_return_handoff":285.26934,"restore_to_method_entry":39808.246021,"sampler_node_to_sampling":25.85993,"sampling":4216.841957,"vae":354.005529}`

### `v2_2026-08-04_21-48-20` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-67637b40f2f3`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `6e22c6fda5de4d23`
- Modal task: `ta-01KZ7BQ3ZBXY77JMX98NYMKF5R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7146.18,"command_to_response_ms":19240.4,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10828.981,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":39.409,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.636,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.636,"unexplained_pre_remote_ms":10789.572,"worker_unattributed_ms":null},"output_collection_ms":8.075,"pre_sampler_ms":2522.85,"restore_total_ms":3931.337,"sampler_ms":3703.997,"snapshot_callback_age_at_restore_ms":243911.27,"snapshot_callback_to_command_start_ms":236768.38,"submission_to_first_remote_event_ms":10828.981,"submit2entry_ms":10561.121,"t3b_to_t8_ms":7737.525,"vae_decode_ms":489.357,"wall_ms":18715.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.644ms unaccounted"]`
- Waterfall stages: `{"application_restore":3931.363867,"captured_timeline_gap":0.6435320000018692,"clip_to_sampler_node":84.587,"first_node_to_clip":94.331,"local_preparation":520.636416,"modal_handle_submission":13.001584,"modal_scheduling":6612.54184,"output_persistence":196.563953,"post_sampling_transition":819.018717,"prompt_executor_cache_setup":212.832,"remote_local_return":12.998784,"remote_method_setup":39.441234,"remote_return_handoff":361.119715,"restore_to_method_entry":13.202505,"sampler_node_to_sampling":924.871931,"sampling":4913.914943,"vae":489.356963}`

### `v2_2026-08-04_21-49-29` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-326eb7d70de0`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `6e22c6fda5de4d23`
- Modal task: `ta-01KZ7BQ3ZBXY77JMX98NYMKF5R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7820.104,"command_to_response_ms":17509.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9256.611,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":36.599,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.924,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.924,"unexplained_pre_remote_ms":9220.013,"worker_unattributed_ms":null},"output_collection_ms":8.83,"pre_sampler_ms":2474.793,"restore_total_ms":1649.187,"sampler_ms":3685.62,"snapshot_callback_age_at_restore_ms":313945.95,"snapshot_callback_to_command_start_ms":306217.38,"submission_to_first_remote_event_ms":9256.611,"submit2entry_ms":8990.937,"t3b_to_t8_ms":7685.502,"vae_decode_ms":479.839,"wall_ms":17024.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.600ms unaccounted"]`
- Waterfall stages: `{"application_restore":1649.196862,"captured_timeline_gap":0.6003880000062054,"clip_to_sampler_node":133.335,"first_node_to_clip":169.37,"local_preparation":480.924352,"modal_handle_submission":11.001348,"modal_scheduling":7328.177916,"output_persistence":193.406892,"post_sampling_transition":846.77351,"prompt_executor_cache_setup":140.449,"remote_local_return":11.999092,"remote_method_setup":36.625961,"remote_return_handoff":298.326962,"restore_to_method_entry":10.554614,"sampler_node_to_sampling":837.1106,"sampling":4882.203013,"vae":479.839082}`

### `v2_2026-08-04_21-50-59` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e522e9e41521`
- Policy/order: `None` / `None`
- CPU/memory: `None` / `None MiB`
- Runtime fingerprint: ``
- Container session: `c1d62fef4a49405b`
- Modal task: `ta-01KZ7B0EQ0P4Z3GS0S77YCRHTR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-ee8KUjf2hMd10bjwP54shC`
- Observed runtime status: ``; requested-vs-actual match: ``
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":78302.518,"command_to_response_ms":89182.4,"handle_lookup_ms":5.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":78984.97,"generator_create_ms":4.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":308.325,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.648,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.648,"unexplained_pre_remote_ms":78676.645,"worker_unattributed_ms":null},"output_collection_ms":8.992,"pre_sampler_ms":3657.26,"restore_total_ms":1313.172,"sampler_ms":3706.475,"snapshot_callback_age_at_restore_ms":1200235.86,"snapshot_callback_to_command_start_ms":1121939.519,"submission_to_first_remote_event_ms":78984.97,"submit2entry_ms":78672.335,"t3b_to_t8_ms":8608.958,"vae_decode_ms":563.671,"wall_ms":88140.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.493ms unaccounted"]`
- Waterfall stages: `{"application_restore":1313.179502,"captured_timeline_gap":0.49286600001505576,"clip_to_sampler_node":48.339,"first_node_to_clip":33.446,"local_preparation":1037.64832,"modal_handle_submission":13.00018,"modal_scheduling":77251.869452,"output_persistence":214.442652,"post_sampling_transition":457.846842,"prompt_executor_cache_setup":612.882,"remote_local_return":17.99992,"remote_method_setup":308.344177,"remote_return_handoff":530.310156,"restore_to_method_entry":102.279476,"sampler_node_to_sampling":1641.091552,"sampling":5035.567294,"vae":563.670531}`

### `v2_2026-08-05_04-10-08` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_04-14-16` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e3a589bbb5d6`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4ec127bf98384056`
- Modal task: `ta-01KZ8223YAWB84X25D0712H7TR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":101073.232,"command_to_response_ms":118333.4,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":103008.356,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":11.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":386.522,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.098,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.098,"unexplained_pre_remote_ms":102621.834,"worker_unattributed_ms":null},"output_collection_ms":11.017,"pre_sampler_ms":8206.593,"restore_total_ms":886.834,"sampler_ms":3736.528,"snapshot_callback_age_at_restore_ms":42143.355,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":103008.356,"submit2entry_ms":101500.46,"t3b_to_t8_ms":13569.08,"vae_decode_ms":655.66,"wall_ms":117854.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.761ms unaccounted"]`
- Waterfall stages: `{"application_restore":886.842343,"captured_timeline_gap":1.7609800000209361,"clip_to_sampler_node":4514.635,"first_node_to_clip":47.811,"local_preparation":474.097792,"modal_handle_submission":14.000108,"modal_scheduling":100585.133588,"output_persistence":258.051226,"post_sampling_transition":699.257562,"prompt_executor_cache_setup":185.07,"remote_local_return":11.999576,"remote_method_setup":386.56129,"remote_return_handoff":2383.192749,"restore_to_method_entry":24.474306,"sampler_node_to_sampling":2197.577951,"sampling":5007.284065,"vae":655.66064}`

### `v2_2026-08-05_04-17-44` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a76e57dff8a7`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `ac805169c5b24402`
- Modal task: `ta-01KZ828FMN3XDG2KEJPWKSHDSR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":77645.096,"command_to_response_ms":91134.9,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":79189.577,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":257.956,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.489,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.489,"unexplained_pre_remote_ms":78931.621,"worker_unattributed_ms":null},"output_collection_ms":9.979,"pre_sampler_ms":5023.31,"restore_total_ms":464.902,"sampler_ms":3662.458,"snapshot_callback_age_at_restore_ms":37978.464,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":79189.577,"submit2entry_ms":77671.942,"t3b_to_t8_ms":10289.595,"vae_decode_ms":509.57,"wall_ms":90687.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.882ms unaccounted"]`
- Waterfall stages: `{"application_restore":464.918597,"captured_timeline_gap":0.882062999997288,"clip_to_sampler_node":2707.607,"first_node_to_clip":40.63,"local_preparation":443.489216,"modal_handle_submission":10.998484,"modal_scheduling":77190.608428,"output_persistence":211.262192,"post_sampling_transition":877.849233,"prompt_executor_cache_setup":183.398,"remote_local_return":11.520412,"remote_method_setup":258.017034,"remote_return_handoff":2518.292798,"restore_to_method_entry":13.400405,"sampler_node_to_sampling":898.848532,"sampling":4793.618843,"vae":509.569675}`

### `v2_2026-08-05_04-20-36` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9cd018817983`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `f247f9bd8ddd4b6a`
- Modal task: `ta-01KZ82DQMBBJ2QFW61DCZPWWPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":93974.892,"command_to_response_ms":111883.9,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":96610.301,"generator_create_ms":4.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":561.883,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.461,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.461,"unexplained_pre_remote_ms":96048.418,"worker_unattributed_ms":null},"output_collection_ms":10.567,"pre_sampler_ms":7756.927,"restore_total_ms":1256.313,"sampler_ms":3699.142,"snapshot_callback_age_at_restore_ms":42991.168,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":96610.301,"submit2entry_ms":94894.005,"t3b_to_t8_ms":12800.772,"vae_decode_ms":590.453,"wall_ms":111448.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.545ms unaccounted"]`
- Waterfall stages: `{"application_restore":1256.322805,"captured_timeline_gap":1.5453730000153882,"clip_to_sampler_node":4496.034,"first_node_to_clip":3.407,"local_preparation":431.461376,"modal_handle_submission":12.999024,"modal_scheduling":93530.43112,"output_persistence":247.587426,"post_sampling_transition":497.258442,"prompt_executor_cache_setup":151.65,"remote_local_return":12.00028,"remote_method_setup":561.925299,"remote_return_handoff":3319.926896,"restore_to_method_entry":103.238336,"sampler_node_to_sampling":1726.266472,"sampling":4941.405206,"vae":590.452625}`

### `v2_2026-08-05_04-24-02` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-150e690b1b85`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `8df7a5b0e74b4206`
- Modal task: `ta-01KZ82M0J0T3NPN7B6KV0CGPGR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `asia-south1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":98051.348,"command_to_response_ms":121785.4,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":103973.369,"generator_create_ms":4.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.986,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":719.006,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.047,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.047,"unexplained_pre_remote_ms":103254.362,"worker_unattributed_ms":null},"output_collection_ms":9.719,"pre_sampler_ms":8492.711,"restore_total_ms":4027.493,"sampler_ms":3711.919,"snapshot_callback_age_at_restore_ms":49899.416,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":103973.369,"submit2entry_ms":101910.871,"t3b_to_t8_ms":13827.964,"vae_decode_ms":548.481,"wall_ms":121355.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.420ms unaccounted"]`
- Waterfall stages: `{"application_restore":4027.501938,"captured_timeline_gap":1.4201690000336384,"clip_to_sampler_node":6247.646,"first_node_to_clip":25.193,"local_preparation":426.047424,"modal_handle_submission":11.986276,"modal_scheduling":97613.314716,"output_persistence":212.740077,"post_sampling_transition":855.873201,"prompt_executor_cache_setup":108.89,"remote_local_return":12.998636,"remote_method_setup":719.052573,"remote_return_handoff":4881.981359,"restore_to_method_entry":266.045068,"sampler_node_to_sampling":971.392929,"sampling":4854.818416,"vae":548.480554}`

### `v2_2026-08-05_04-30-34` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9f7d7e6ea209`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `9856a7e378b449a7`
- Modal task: `ta-01KZ82ZZQ1ENWZYFVGMA0ECW2R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":78849.954,"command_to_response_ms":88947.3,"handle_lookup_ms":26.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":80429.345,"generator_create_ms":26.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":31.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":47.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.582,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.116,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.116,"unexplained_pre_remote_ms":80378.762,"worker_unattributed_ms":null},"output_collection_ms":9.016,"pre_sampler_ms":2769.958,"restore_total_ms":458.115,"sampler_ms":3691.838,"snapshot_callback_age_at_restore_ms":38911.542,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":80429.344,"submit2entry_ms":78951.527,"t3b_to_t8_ms":7991.533,"vae_decode_ms":572.046,"wall_ms":88584.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.890ms unaccounted"]`
- Waterfall stages: `{"application_restore":458.128501,"captured_timeline_gap":0.8903669999999693,"clip_to_sampler_node":96.906,"first_node_to_clip":166.949,"local_preparation":358.115904,"modal_handle_submission":36.998996,"modal_scheduling":78454.8387,"output_persistence":204.958752,"post_sampling_transition":746.911539,"prompt_executor_cache_setup":286.451,"remote_local_return":13.000052,"remote_method_setup":50.641631,"remote_return_handoff":1580.519907,"restore_to_method_entry":11.549734,"sampler_node_to_sampling":874.511927,"sampling":5033.878547,"vae":572.044995}`

### `v2_2026-08-05_04-32-56` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-663f632c7af9`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `24bb4319b0c743d0`
- Modal task: `ta-01KZ834A0CNY583KX3XEQ50JHR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":95435.517,"command_to_response_ms":108325.5,"handle_lookup_ms":4.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":98314.942,"generator_create_ms":3.997,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":64.44,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":16.0,"payload_size_measurement_ms":16.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.757,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.757,"unexplained_pre_remote_ms":98250.502,"worker_unattributed_ms":null},"output_collection_ms":10.566,"pre_sampler_ms":4350.533,"restore_total_ms":1441.344,"sampler_ms":3697.987,"snapshot_callback_age_at_restore_ms":41783.066,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":98314.942,"submit2entry_ms":96593.464,"t3b_to_t8_ms":9510.274,"vae_decode_ms":678.462,"wall_ms":107944.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.599ms unaccounted"]`
- Waterfall stages: `{"application_restore":1441.353706,"captured_timeline_gap":1.5989320000080625,"clip_to_sampler_node":703.078,"first_node_to_clip":36.6,"local_preparation":375.757376,"modal_handle_submission":14.000524,"modal_scheduling":95045.759348,"output_persistence":247.552776,"post_sampling_transition":525.616817,"prompt_executor_cache_setup":248.68,"remote_local_return":13.57782,"remote_method_setup":64.468725,"remote_return_handoff":1769.143573,"restore_to_method_entry":101.333137,"sampler_node_to_sampling":1757.100625,"sampling":5301.45297,"vae":678.461991}`

### `v2_2026-08-05_04-36-54` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-7f19ef287b33`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `9671f4549aa34073`
- Modal task: `ta-01KZ83BJVFQPREWB613G951KFR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":99113.921,"command_to_response_ms":111437.5,"handle_lookup_ms":2.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":101612.647,"generator_create_ms":3.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":9.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":67.621,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.039,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.039,"unexplained_pre_remote_ms":101545.026,"worker_unattributed_ms":null},"output_collection_ms":10.79,"pre_sampler_ms":4174.847,"restore_total_ms":1032.421,"sampler_ms":3693.455,"snapshot_callback_age_at_restore_ms":44137.242,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":101612.647,"submit2entry_ms":99880.511,"t3b_to_t8_ms":9298.455,"vae_decode_ms":663.083,"wall_ms":111074.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.326ms unaccounted"]`
- Waterfall stages: `{"application_restore":1032.432644,"captured_timeline_gap":1.3261469999706605,"clip_to_sampler_node":572.1,"first_node_to_clip":35.452,"local_preparation":358.038528,"modal_handle_submission":13.001172,"modal_scheduling":98742.881324,"output_persistence":247.780276,"post_sampling_transition":509.052859,"prompt_executor_cache_setup":221.047,"remote_local_return":12.999836,"remote_method_setup":67.842917,"remote_return_handoff":1823.71746,"restore_to_method_entry":101.190536,"sampler_node_to_sampling":1780.955272,"sampling":5254.591313,"vae":663.083452}`

### `v2_2026-08-05_04-39-20` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d8ec5e75802b`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `9671f4549aa34073`
- Modal task: `ta-01KZ83BJVFQPREWB613G951KFR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6456.198,"command_to_response_ms":18379.5,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":8869.315,"generator_create_ms":4.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":58.544,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.193,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.193,"unexplained_pre_remote_ms":8810.771,"worker_unattributed_ms":null},"output_collection_ms":9.534,"pre_sampler_ms":3672.683,"restore_total_ms":1198.504,"sampler_ms":3696.907,"snapshot_callback_age_at_restore_ms":97794.798,"snapshot_callback_to_command_start_ms":91435.935,"submission_to_first_remote_event_ms":8869.315,"submit2entry_ms":7314.404,"t3b_to_t8_ms":8774.713,"vae_decode_ms":651.262,"wall_ms":17941.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.027ms unaccounted"]`
- Waterfall stages: `{"application_restore":1198.518104,"captured_timeline_gap":1.0266650000012305,"clip_to_sampler_node":130.123,"first_node_to_clip":39.883,"local_preparation":434.19264,"modal_handle_submission":13.00136,"modal_scheduling":6009.004144,"output_persistence":245.189654,"post_sampling_transition":499.076753,"prompt_executor_cache_setup":222.817,"remote_local_return":12.529956,"remote_method_setup":58.565497,"remote_return_handoff":1778.19937,"restore_to_method_entry":102.834745,"sampler_node_to_sampling":1758.497613,"sampling":5224.759656,"vae":651.262699}`

### `v2_2026-08-05_04-40-09` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-6127de073442`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `9671f4549aa34073`
- Modal task: `ta-01KZ83BJVFQPREWB613G951KFR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3136.805,"command_to_response_ms":33766.2,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":12491.533,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":57.819,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.285,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.285,"unexplained_pre_remote_ms":12433.714,"worker_unattributed_ms":null},"output_collection_ms":9.641,"pre_sampler_ms":15499.673,"restore_total_ms":8254.857,"sampler_ms":3713.383,"snapshot_callback_age_at_restore_ms":142917.873,"snapshot_callback_to_command_start_ms":139782.935,"submission_to_first_remote_event_ms":12491.533,"submit2entry_ms":10948.123,"t3b_to_t8_ms":20429.925,"vae_decode_ms":574.406,"wall_ms":33222.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.267ms unaccounted"]`
- Waterfall stages: `{"application_restore":8254.871148,"captured_timeline_gap":1.2673999999897205,"clip_to_sampler_node":376.74,"first_node_to_clip":35.823,"local_preparation":539.285312,"modal_handle_submission":11.999088,"modal_scheduling":2585.52104,"output_persistence":205.641058,"post_sampling_transition":425.276569,"prompt_executor_cache_setup":242.438,"remote_local_return":12.001696,"remote_method_setup":57.839646,"remote_return_handoff":1775.575956,"restore_to_method_entry":103.725202,"sampler_node_to_sampling":13514.914339,"sampling":5048.862248,"vae":574.406394}`

### `v2_2026-08-05_04-41-45` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a3a6c0559a11`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `957a1fcc004b4d2c`
- Modal task: `ta-01KZ83MEZKCZZPRV1TMYP5V3YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":94192.336,"command_to_response_ms":107127.9,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":97430.844,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":57.629,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.896,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.896,"unexplained_pre_remote_ms":97373.216,"worker_unattributed_ms":null},"output_collection_ms":11.189,"pre_sampler_ms":3996.784,"restore_total_ms":1762.59,"sampler_ms":3735.825,"snapshot_callback_age_at_restore_ms":41027.543,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":97430.844,"submit2entry_ms":95697.461,"t3b_to_t8_ms":9223.147,"vae_decode_ms":691.431,"wall_ms":106771.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.799ms unaccounted"]`
- Waterfall stages: `{"application_restore":1762.600628,"captured_timeline_gap":2.798758999982965,"clip_to_sampler_node":365.918,"first_node_to_clip":38.618,"local_preparation":350.896192,"modal_handle_submission":13.001808,"modal_scheduling":93828.438448,"output_persistence":254.39202,"post_sampling_transition":532.13354,"prompt_executor_cache_setup":225.318,"remote_local_return":12.999188,"remote_method_setup":57.650481,"remote_return_handoff":1778.402758,"restore_to_method_entry":102.399665,"sampler_node_to_sampling":1786.969413,"sampling":5323.937262,"vae":691.430926}`

### `v2_2026-08-05_04-44-02` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b9b3fe133688`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `957a1fcc004b4d2c`
- Modal task: `ta-01KZ83MEZKCZZPRV1TMYP5V3YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7428.519,"command_to_response_ms":19183.7,"handle_lookup_ms":4.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9570.133,"generator_create_ms":4.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":54.55,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.097,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.097,"unexplained_pre_remote_ms":9515.583,"worker_unattributed_ms":null},"output_collection_ms":10.201,"pre_sampler_ms":3703.799,"restore_total_ms":933.852,"sampler_ms":3738.552,"snapshot_callback_age_at_restore_ms":90575.421,"snapshot_callback_to_command_start_ms":83823.632,"submission_to_first_remote_event_ms":9570.133,"submit2entry_ms":8025.019,"t3b_to_t8_ms":8873.589,"vae_decode_ms":665.094,"wall_ms":18748.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.369ms unaccounted"]`
- Waterfall stages: `{"application_restore":933.859185,"captured_timeline_gap":1.3692040000023553,"clip_to_sampler_node":113.972,"first_node_to_clip":38.013,"local_preparation":430.09696,"modal_handle_submission":13.00014,"modal_scheduling":6985.42162,"output_persistence":250.883718,"post_sampling_transition":505.257123,"prompt_executor_cache_setup":235.916,"remote_local_return":12.001016,"remote_method_setup":54.578222,"remote_return_handoff":1780.804856,"restore_to_method_entry":101.720872,"sampler_node_to_sampling":1765.666166,"sampling":5296.074664,"vae":665.09447}`

### `v2_2026-08-05_04-44-54` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4fdc789f0fc5`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `957a1fcc004b4d2c`
- Modal task: `ta-01KZ83MEZKCZZPRV1TMYP5V3YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3968.207,"command_to_response_ms":15590.1,"handle_lookup_ms":4.552,"local_timing":{"active_profile_ms":16.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6364.24,"generator_create_ms":3.55,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":11.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":46.179,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.993,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.993,"unexplained_pre_remote_ms":6318.061,"worker_unattributed_ms":null},"output_collection_ms":12.404,"pre_sampler_ms":3449.325,"restore_total_ms":1252.908,"sampler_ms":3725.81,"snapshot_callback_age_at_restore_ms":139079.042,"snapshot_callback_to_command_start_ms":135209.632,"submission_to_first_remote_event_ms":6364.24,"submit2entry_ms":4817.614,"t3b_to_t8_ms":8432.617,"vae_decode_ms":579.75,"wall_ms":15089.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.898ms unaccounted"]`
- Waterfall stages: `{"application_restore":1252.963591,"captured_timeline_gap":0.8983189999999013,"clip_to_sampler_node":135.495,"first_node_to_clip":38.877,"local_preparation":494.992576,"modal_handle_submission":14.552824,"modal_scheduling":3458.66164,"output_persistence":215.863162,"post_sampling_transition":452.127698,"prompt_executor_cache_setup":209.625,"remote_local_return":11.999808,"remote_method_setup":46.232782,"remote_return_handoff":1778.237824,"restore_to_method_entry":101.368679,"sampler_node_to_sampling":1717.668884,"sampling":5080.755719,"vae":579.749702}`

### `v2_2026-08-05_04-49-28` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-f6ffb7cf9cf1`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `6a0c138bde784f9b`
- Modal task: `ta-01KZ842JXJCJSRH8J01GXZENGR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":170626.752,"command_to_response_ms":183084.2,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":172568.866,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":67.618,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.034,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.034,"unexplained_pre_remote_ms":172501.249,"worker_unattributed_ms":null},"output_collection_ms":11.581,"pre_sampler_ms":4448.556,"restore_total_ms":740.802,"sampler_ms":3717.658,"snapshot_callback_age_at_restore_ms":55884.644,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":172568.867,"submit2entry_ms":171027.324,"t3b_to_t8_ms":9982.092,"vae_decode_ms":770.785,"wall_ms":182727.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.637ms unaccounted"]`
- Waterfall stages: `{"application_restore":740.813026,"captured_timeline_gap":1.6372060000430793,"clip_to_sampler_node":194.712,"first_node_to_clip":3.046,"local_preparation":352.033856,"modal_handle_submission":11.999644,"modal_scheduling":170262.718308,"output_persistence":244.750611,"post_sampling_transition":787.628639,"prompt_executor_cache_setup":556.125,"remote_local_return":14.747508,"remote_method_setup":67.646187,"remote_return_handoff":1634.785848,"restore_to_method_entry":20.784625,"sampler_node_to_sampling":2063.020161,"sampling":5356.989904,"vae":770.785285}`

### `v2_2026-08-05_04-53-08` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d408cc278d6c`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `6a0c138bde784f9b`
- Modal task: `ta-01KZ842JXJCJSRH8J01GXZENGR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4584.232,"command_to_response_ms":16447.8,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6486.21,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":10.238,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":56.741,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.375,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.375,"unexplained_pre_remote_ms":6429.468,"worker_unattributed_ms":null},"output_collection_ms":10.798,"pre_sampler_ms":3997.075,"restore_total_ms":940.044,"sampler_ms":3707.272,"snapshot_callback_age_at_restore_ms":109530.872,"snapshot_callback_to_command_start_ms":105010.769,"submission_to_first_remote_event_ms":6486.21,"submit2entry_ms":4974.213,"t3b_to_t8_ms":9234.936,"vae_decode_ms":679.102,"wall_ms":15881.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.073ms unaccounted"]`
- Waterfall stages: `{"application_restore":940.052431,"captured_timeline_gap":1.073488999998517,"clip_to_sampler_node":88.216,"first_node_to_clip":3.442,"local_preparation":561.374656,"modal_handle_submission":13.236644,"modal_scheduling":4009.620316,"output_persistence":256.165686,"post_sampling_transition":584.726847,"prompt_executor_cache_setup":360.667,"remote_local_return":12.997852,"remote_method_setup":56.758834,"remote_return_handoff":1598.873809,"restore_to_method_entry":21.531024,"sampler_node_to_sampling":1944.919862,"sampling":5315.051975,"vae":679.102327}`

### `v2_2026-08-05_04-53-56` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-578e32745049`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `6a0c138bde784f9b`
- Modal task: `ta-01KZ842JXJCJSRH8J01GXZENGR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3406.225,"command_to_response_ms":47982.3,"handle_lookup_ms":3.6,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":11098.604,"generator_create_ms":3.6,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":58.906,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.527,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.527,"unexplained_pre_remote_ms":11039.698,"worker_unattributed_ms":null},"output_collection_ms":10.113,"pre_sampler_ms":31208.452,"restore_total_ms":6498.885,"sampler_ms":3687.882,"snapshot_callback_age_at_restore_ms":156442.128,"snapshot_callback_to_command_start_ms":153037.769,"submission_to_first_remote_event_ms":11098.604,"submit2entry_ms":9538.859,"t3b_to_t8_ms":36113.827,"vae_decode_ms":575.258,"wall_ms":47514.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.930ms unaccounted"]`
- Waterfall stages: `{"application_restore":6498.892975,"captured_timeline_gap":0.9301259999992908,"clip_to_sampler_node":7421.47,"first_node_to_clip":2.135,"local_preparation":463.527424,"modal_handle_submission":11.599076,"modal_scheduling":2931.098652,"output_persistence":222.981044,"post_sampling_transition":409.615186,"prompt_executor_cache_setup":227.031,"remote_local_return":12.999188,"remote_method_setup":58.926118,"remote_return_handoff":1787.76403,"restore_to_method_entry":105.260484,"sampler_node_to_sampling":22221.510475,"sampling":5031.272345,"vae":575.258365}`

### `v2_2026-08-05_04-55-42` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5f63122abebb`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `36a2c921d70847ec`
- Modal task: `ta-01KZ84DZRMHEFXWCAW5R42TGFR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":96050.369,"command_to_response_ms":108512.4,"handle_lookup_ms":5.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":98191.16,"generator_create_ms":3.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":10.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":60.517,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.818,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.818,"unexplained_pre_remote_ms":98130.643,"worker_unattributed_ms":null},"output_collection_ms":11.211,"pre_sampler_ms":4456.817,"restore_total_ms":967.133,"sampler_ms":3715.946,"snapshot_callback_age_at_restore_ms":40397.807,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":98191.16,"submit2entry_ms":96639.68,"t3b_to_t8_ms":9798.307,"vae_decode_ms":718.702,"wall_ms":108116.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.755ms unaccounted"]`
- Waterfall stages: `{"application_restore":967.164188,"captured_timeline_gap":1.7545469999749912,"clip_to_sampler_node":136.938,"first_node_to_clip":80.883,"local_preparation":389.818112,"modal_handle_submission":14.001088,"modal_scheduling":95646.55008,"output_persistence":254.532114,"post_sampling_transition":641.006575,"prompt_executor_cache_setup":473.232,"remote_local_return":14.000008,"remote_method_setup":60.571953,"remote_return_handoff":1603.407338,"restore_to_method_entry":20.94951,"sampler_node_to_sampling":2118.144046,"sampling":5370.727135,"vae":718.702514}`

### `v2_2026-08-05_04-58-03` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1500617c1c1c`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `d6f03b3986ee483b`
- Modal task: `ta-01KZ84J9MYS9Q041FBT9247S7R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":91222.519,"command_to_response_ms":102795.9,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":93418.542,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.539,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":171.078,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.307,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.307,"unexplained_pre_remote_ms":93247.464,"worker_unattributed_ms":null},"output_collection_ms":8.718,"pre_sampler_ms":3191.493,"restore_total_ms":918.611,"sampler_ms":3687.325,"snapshot_callback_age_at_restore_ms":49550.804,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":93418.542,"submit2entry_ms":91731.416,"t3b_to_t8_ms":8820.669,"vae_decode_ms":973.202,"wall_ms":102316.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.866ms unaccounted"]`
- Waterfall stages: `{"application_restore":918.619968,"captured_timeline_gap":0.8662509999703616,"clip_to_sampler_node":624.734,"first_node_to_clip":25.566,"local_preparation":473.307008,"modal_handle_submission":13.538592,"modal_scheduling":90735.673568,"output_persistence":207.198629,"post_sampling_transition":756.195353,"prompt_executor_cache_setup":174.803,"remote_local_return":13.997944,"remote_method_setup":171.112929,"remote_return_handoff":1703.713306,"restore_to_method_entry":73.114807,"sampler_node_to_sampling":890.981446,"sampling":5039.313706,"vae":973.202437}`

### `v2_2026-08-05_05-00-20` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1c9038d89891`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `d6f03b3986ee483b`
- Modal task: `ta-01KZ84J9MYS9Q041FBT9247S7R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":10789.914,"command_to_response_ms":21201.9,"handle_lookup_ms":4.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":12650.231,"generator_create_ms":4.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":9.03,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":46.19,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.941,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.941,"unexplained_pre_remote_ms":12604.041,"worker_unattributed_ms":null},"output_collection_ms":8.577,"pre_sampler_ms":2625.632,"restore_total_ms":724.231,"sampler_ms":3698.587,"snapshot_callback_age_at_restore_ms":106657.637,"snapshot_callback_to_command_start_ms":95879.589,"submission_to_first_remote_event_ms":12650.231,"submit2entry_ms":11107.754,"t3b_to_t8_ms":7843.231,"vae_decode_ms":540.739,"wall_ms":20723.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.894ms unaccounted"]`
- Waterfall stages: `{"application_restore":724.247919,"captured_timeline_gap":0.89384599999903,"clip_to_sampler_node":227.381,"first_node_to_clip":19.582,"local_preparation":473.940736,"modal_handle_submission":13.030964,"modal_scheduling":10302.9419,"output_persistence":204.366319,"post_sampling_transition":768.346374,"prompt_executor_cache_setup":159.022,"remote_local_return":15.9331,"remote_method_setup":46.238804,"remote_return_handoff":1708.453364,"restore_to_method_entry":75.551899,"sampler_node_to_sampling":905.849327,"sampling":5015.408092,"vae":540.738756}`

### `v2_2026-08-05_05-02-20` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_05-06-18` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `run_2.json`, `run_3.json`, `run_4.json`, `summary.json`
- Request ID: `v2-benchmark-0-77381c538474`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `ed7705a4ec3e4891`
- Modal task: `ta-01KZ851CT3G3ST3BMK63N2PHBR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":115073.348,"command_to_response_ms":127483.8,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":117201.21,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":10.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":66.682,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.461,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.461,"unexplained_pre_remote_ms":117134.528,"worker_unattributed_ms":null},"output_collection_ms":11.371,"pre_sampler_ms":4406.351,"restore_total_ms":944.334,"sampler_ms":3700.694,"snapshot_callback_age_at_restore_ms":55311.935,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":117201.21,"submit2entry_ms":115638.592,"t3b_to_t8_ms":9713.63,"vae_decode_ms":714.275,"wall_ms":127088.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.367ms unaccounted"]`
- Waterfall stages: `{"application_restore":944.344453,"captured_timeline_gap":1.3674690000189003,"clip_to_sampler_node":134.347,"first_node_to_clip":155.258,"local_preparation":391.46112,"modal_handle_submission":13.00038,"modal_scheduling":114668.88634,"output_persistence":262.183896,"post_sampling_transition":618.801868,"prompt_executor_cache_setup":284.46,"remote_local_return":12.000036,"remote_method_setup":66.750571,"remote_return_handoff":1654.593207,"restore_to_method_entry":21.348079,"sampler_node_to_sampling":2170.786626,"sampling":5369.919902,"vae":714.274989}`

### `v2_2026-08-05_05-06-18` / run `1`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `run_2.json`, `run_3.json`, `run_4.json`, `summary.json`
- Request ID: `v2-benchmark-1-377e221e2319`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4a4a88d746374e99`
- Modal task: `ta-01KZ855WSF4TC5Z1KXAA6SRJDR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":236534.581,"command_to_response_ms":250340.2,"handle_lookup_ms":2.995,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":94110.287,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.536,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":52.75,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":15.0,"payload_size_measurement_ms":15.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.997,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.997,"unexplained_pre_remote_ms":94057.536,"worker_unattributed_ms":null},"output_collection_ms":9.556,"pre_sampler_ms":3302.834,"restore_total_ms":3343.699,"sampler_ms":3718.318,"snapshot_callback_age_at_restore_ms":47918.442,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":94110.287,"submit2entry_ms":92422.477,"t3b_to_t8_ms":8610.73,"vae_decode_ms":566.555,"wall_ms":102815.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.917ms unaccounted"]`
- Waterfall stages: `{"application_restore":3343.719734,"captured_timeline_gap":0.9173330000194255,"clip_to_sampler_node":158.002,"first_node_to_clip":507.71,"local_preparation":0.997312,"modal_handle_submission":10.535988,"modal_scheduling":89002.047692,"output_persistence":212.667739,"post_sampling_transition":804.037107,"prompt_executor_cache_setup":267.108,"remote_local_return":13.000056,"remote_method_setup":52.807123,"remote_return_handoff":1714.788345,"restore_to_method_entry":72.6938,"sampler_node_to_sampling":1001.600617,"sampling":5089.979212,"vae":566.554598}`

### `v2_2026-08-05_05-06-18` / run `2`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `run_2.json`, `run_3.json`, `run_4.json`, `summary.json`
- Request ID: `v2-benchmark-2-258fcc2ac98c`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4a4a88d746374e99`
- Modal task: `ta-01KZ855WSF4TC5Z1KXAA6SRJDR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":236534.581,"command_to_response_ms":277200.3,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":167.833,"generator_create_ms":1.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":24.452,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.502,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.502,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":757.4,"pre_sampler_ms":782.296,"restore_total_ms":3343.699,"sampler_ms":3739.588,"snapshot_callback_age_at_restore_ms":47918.442,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":167.833,"submit2entry_ms":-1408.444,"t3b_to_t8_ms":6582.361,"vae_decode_ms":354.543,"wall_ms":6802.1}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -4005.421ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":3343.719734,"clip_to_sampler_node":53.411,"first_node_to_clip":53.146,"local_preparation":0.501696,"modal_handle_submission":10.002504,"modal_scheduling":null,"output_persistence":148.82692,"post_sampling_transition":806.825994,"prompt_executor_cache_setup":138.99,"remote_local_return":14.258552,"remote_method_setup":24.465936,"remote_return_handoff":1587.249249,"restore_to_method_entry":29114.737626,"sampler_node_to_sampling":50.725212,"sampling":4226.053042,"vae":354.543473}`

### `v2_2026-08-05_05-06-18` / run `3`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `run_2.json`, `run_3.json`, `run_4.json`, `summary.json`
- Request ID: `v2-benchmark-3-a37b55fc8832`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `ed7705a4ec3e4891`
- Modal task: `ta-01KZ851CT3G3ST3BMK63N2PHBR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":274594.362,"command_to_response_ms":307317.9,"handle_lookup_ms":1.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":158.54,"generator_create_ms":1.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":5.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":65.989,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.317,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.317,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.662,"pre_sampler_ms":4438.751,"restore_total_ms":938.993,"sampler_ms":3707.266,"snapshot_callback_age_at_restore_ms":214778.285,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":158.54,"submit2entry_ms":-1428.729,"t3b_to_t8_ms":9796.95,"vae_decode_ms":717.1,"wall_ms":10058.5}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2368.757ms > 50.310ms"]`
- Waterfall stages: `{"application_restore":939.027139,"clip_to_sampler_node":155.096,"first_node_to_clip":168.465,"local_preparation":0.316672,"modal_handle_submission":6.999728,"modal_scheduling":null,"output_persistence":259.067383,"post_sampling_transition":664.853834,"prompt_executor_cache_setup":295.242,"remote_local_return":15.000988,"remote_method_setup":66.028609,"remote_return_handoff":1609.639772,"restore_to_method_entry":20299.165889,"sampler_node_to_sampling":2194.044537,"sampling":5339.787514,"vae":717.100643}`

### `v2_2026-08-05_05-06-18` / run `4`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `run_1.json`, `run_2.json`, `run_3.json`, `run_4.json`, `summary.json`
- Request ID: `v2-benchmark-4-f24529e5e971`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `ed7705a4ec3e4891`
- Modal task: `ta-01KZ851CT3G3ST3BMK63N2PHBR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":330259.678,"command_to_response_ms":342201.6,"handle_lookup_ms":1.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5677.135,"generator_create_ms":1.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":65.936,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.456,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.456,"unexplained_pre_remote_ms":5611.199,"worker_unattributed_ms":null},"output_collection_ms":11.744,"pre_sampler_ms":3904.281,"restore_total_ms":1216.557,"sampler_ms":3709.172,"snapshot_callback_age_at_restore_ms":270521.362,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":5677.135,"submit2entry_ms":4145.447,"t3b_to_t8_ms":9002.717,"vae_decode_ms":623.324,"wall_ms":14836.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.146ms unaccounted"]`
- Waterfall stages: `{"application_restore":1216.567088,"captured_timeline_gap":2.1459190000005037,"clip_to_sampler_node":63.609,"first_node_to_clip":46.539,"local_preparation":0.455808,"modal_handle_submission":7.000592,"modal_scheduling":2890.222064,"output_persistence":222.657237,"post_sampling_transition":531.392956,"prompt_executor_cache_setup":384.351,"remote_local_return":15.313536,"remote_method_setup":65.978661,"remote_return_handoff":1605.556124,"restore_to_method_entry":37.64902,"sampler_node_to_sampling":2016.053773,"sampling":5110.816715,"vae":623.325043}`

### `v2_2026-08-05_05-12-59` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: `run_0.json`
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_05-18-37` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-413788af6fa3`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4c5c6b0a1220439b`
- Modal task: `ta-01KZ85R1HVD3EEWB0XVWMVE3QR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":80157.158,"command_to_response_ms":91472.4,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":81802.763,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":42.613,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.781,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.781,"unexplained_pre_remote_ms":81760.15,"worker_unattributed_ms":null},"output_collection_ms":9.178,"pre_sampler_ms":3980.417,"restore_total_ms":476.852,"sampler_ms":3677.016,"snapshot_callback_age_at_restore_ms":39505.39,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":81802.763,"submit2entry_ms":80254.522,"t3b_to_t8_ms":9154.702,"vae_decode_ms":543.929,"wall_ms":91083.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.975ms unaccounted"]`
- Waterfall stages: `{"application_restore":476.863864,"captured_timeline_gap":0.9750450000283308,"clip_to_sampler_node":1581.466,"first_node_to_clip":22.288,"local_preparation":384.78112,"modal_handle_submission":10.99998,"modal_scheduling":79761.376852,"output_persistence":200.894366,"post_sampling_transition":747.040903,"prompt_executor_cache_setup":155.257,"remote_local_return":11.999852,"remote_method_setup":42.662034,"remote_return_handoff":1618.012817,"restore_to_method_entry":13.268655,"sampler_node_to_sampling":867.772309,"sampling":5032.795625,"vae":543.92913}`

### `v2_2026-08-05_05-20-43` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-36a2f658f6fb`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4c5c6b0a1220439b`
- Modal task: `ta-01KZ85R1HVD3EEWB0XVWMVE3QR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":9221.98,"command_to_response_ms":22498.9,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":13445.194,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.997,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":70.629,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.604,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.604,"unexplained_pre_remote_ms":13374.565,"worker_unattributed_ms":null},"output_collection_ms":9.137,"pre_sampler_ms":3217.003,"restore_total_ms":3090.184,"sampler_ms":3720.707,"snapshot_callback_age_at_restore_ms":95107.663,"snapshot_callback_to_command_start_ms":85971.495,"submission_to_first_remote_event_ms":13445.194,"submit2entry_ms":11915.741,"t3b_to_t8_ms":8501.967,"vae_decode_ms":569.133,"wall_ms":22073.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.995ms unaccounted"]`
- Waterfall stages: `{"application_restore":3090.209001,"captured_timeline_gap":0.9947590000010678,"clip_to_sampler_node":129.622,"first_node_to_clip":105.279,"local_preparation":421.60384,"modal_handle_submission":11.99846,"modal_scheduling":8788.378116,"output_persistence":202.951567,"post_sampling_transition":786.706368,"prompt_executor_cache_setup":258.443,"remote_local_return":11.998872,"remote_method_setup":70.648405,"remote_return_handoff":1570.860686,"restore_to_method_entry":33.141847,"sampler_node_to_sampling":1363.197393,"sampling":5083.735707,"vae":569.133251}`

### `v2_2026-08-05_05-21-40` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0e302177c890`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4c5c6b0a1220439b`
- Modal task: `ta-01KZ85R1HVD3EEWB0XVWMVE3QR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":2620.03,"command_to_response_ms":27033.0,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5738.473,"generator_create_ms":4.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":45.088,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.744,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.744,"unexplained_pre_remote_ms":5693.385,"worker_unattributed_ms":null},"output_collection_ms":8.902,"pre_sampler_ms":15472.403,"restore_total_ms":1987.521,"sampler_ms":3690.951,"snapshot_callback_age_at_restore_ms":144903.757,"snapshot_callback_to_command_start_ms":142285.495,"submission_to_first_remote_event_ms":5739.48,"submit2entry_ms":4199.959,"t3b_to_t8_ms":20718.298,"vae_decode_ms":509.462,"wall_ms":26596.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.979ms unaccounted"]`
- Waterfall stages: `{"application_restore":1987.552168,"captured_timeline_gap":0.9785069999961706,"clip_to_sampler_node":2693.162,"first_node_to_clip":143.347,"local_preparation":432.74432,"modal_handle_submission":12.00138,"modal_scheduling":2175.284124,"output_persistence":190.924712,"post_sampling_transition":849.335705,"prompt_executor_cache_setup":197.645,"remote_local_return":12.999316,"remote_method_setup":45.110328,"remote_return_handoff":1618.551919,"restore_to_method_entry":33.109139,"sampler_node_to_sampling":11227.651789,"sampling":4903.158171,"vae":509.461638}`

### `v2_2026-08-05_05-22-41` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c788dae6cbd7`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `40ab7302ad3c482a`
- Modal task: `ta-01KZ85ZCTHH4542ZF23WV39RPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":104707.446,"command_to_response_ms":116217.5,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":106862.793,"generator_create_ms":3.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":43.588,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.509,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.509,"unexplained_pre_remote_ms":106819.206,"worker_unattributed_ms":null},"output_collection_ms":11.48,"pre_sampler_ms":3871.5,"restore_total_ms":738.612,"sampler_ms":3691.607,"snapshot_callback_age_at_restore_ms":55891.041,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":106862.794,"submit2entry_ms":105104.351,"t3b_to_t8_ms":8804.931,"vae_decode_ms":585.623,"wall_ms":115777.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.849ms unaccounted"]`
- Waterfall stages: `{"application_restore":738.620553,"captured_timeline_gap":0.8490940000046976,"clip_to_sampler_node":507.814,"first_node_to_clip":33.068,"local_preparation":435.50912,"modal_handle_submission":13.00018,"modal_scheduling":104258.936844,"output_persistence":218.396161,"post_sampling_transition":428.050076,"prompt_executor_cache_setup":211.798,"remote_local_return":11.9976,"remote_method_setup":43.615722,"remote_return_handoff":1811.009093,"restore_to_method_entry":102.785399,"sampler_node_to_sampling":1776.377079,"sampling":5040.076471,"vae":585.623008}`

### `v2_2026-08-05_05-25-11` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-10e09b0df799`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `40ab7302ad3c482a`
- Modal task: `ta-01KZ85ZCTHH4542ZF23WV39RPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4439.085,"command_to_response_ms":38284.9,"handle_lookup_ms":4.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10896.971,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.515,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.052,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.24,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.24,"unexplained_pre_remote_ms":10846.919,"worker_unattributed_ms":null},"output_collection_ms":9.739,"pre_sampler_ms":21815.001,"restore_total_ms":5193.438,"sampler_ms":3683.702,"snapshot_callback_age_at_restore_ms":106564.351,"snapshot_callback_to_command_start_ms":102131.778,"submission_to_first_remote_event_ms":10896.971,"submit2entry_ms":9321.22,"t3b_to_t8_ms":26683.174,"vae_decode_ms":556.843,"wall_ms":37873.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 110.686ms unaccounted"]`
- Waterfall stages: `{"application_restore":5193.441796,"captured_timeline_gap":110.68648799999937,"clip_to_sampler_node":4741.224,"first_node_to_clip":32.746,"local_preparation":408.23968,"modal_handle_submission":11.51602,"modal_scheduling":4019.329164,"output_persistence":203.217837,"post_sampling_transition":415.648669,"prompt_executor_cache_setup":181.667,"remote_local_return":12.000028,"remote_method_setup":50.082366,"remote_return_handoff":1811.822059,"restore_to_method_entry":104.445955,"sampler_node_to_sampling":15429.720493,"sampling":5002.315025,"vae":556.843148}`

### `v2_2026-08-05_05-26-28` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-31d6cf6b31c7`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `40ab7302ad3c482a`
- Modal task: `ta-01KZ85ZCTHH4542ZF23WV39RPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3188.285,"command_to_response_ms":14589.4,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5726.083,"generator_create_ms":3.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":40.343,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.263,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.263,"unexplained_pre_remote_ms":5685.74,"worker_unattributed_ms":null},"output_collection_ms":8.975,"pre_sampler_ms":3324.979,"restore_total_ms":1274.631,"sampler_ms":3673.72,"snapshot_callback_age_at_restore_ms":182080.231,"snapshot_callback_to_command_start_ms":178948.778,"submission_to_first_remote_event_ms":5726.083,"submit2entry_ms":4150.368,"t3b_to_t8_ms":8160.695,"vae_decode_ms":550.95,"wall_ms":14178.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.093ms unaccounted"]`
- Waterfall stages: `{"application_restore":1274.638824,"captured_timeline_gap":1.093366999999489,"clip_to_sampler_node":126.095,"first_node_to_clip":37.237,"local_preparation":406.26304,"modal_handle_submission":12.00096,"modal_scheduling":2770.020928,"output_persistence":200.378171,"post_sampling_transition":401.315684,"prompt_executor_cache_setup":188.62,"remote_local_return":13.001636,"remote_method_setup":40.367636,"remote_return_handoff":1812.441798,"restore_to_method_entry":101.699291,"sampler_node_to_sampling":1681.798197,"sampling":4971.525987,"vae":550.950417}`

### `v2_2026-08-05_05-27-18` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5a62e2190734`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `40ab7302ad3c482a`
- Modal task: `ta-01KZ85ZCTHH4542ZF23WV39RPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3879.332,"command_to_response_ms":16029.2,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6180.607,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":1.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.997,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":84.754,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.766,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.766,"unexplained_pre_remote_ms":6095.853,"worker_unattributed_ms":null},"output_collection_ms":12.472,"pre_sampler_ms":4130.223,"restore_total_ms":992.431,"sampler_ms":3733.02,"snapshot_callback_age_at_restore_ms":232998.896,"snapshot_callback_to_command_start_ms":229188.778,"submission_to_first_remote_event_ms":6180.607,"submit2entry_ms":4588.08,"t3b_to_t8_ms":9110.71,"vae_decode_ms":578.01,"wall_ms":15617.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.253ms unaccounted"]`
- Waterfall stages: `{"application_restore":992.508008,"captured_timeline_gap":0.2527490000029502,"clip_to_sampler_node":326.699,"first_node_to_clip":111.177,"local_preparation":408.766464,"modal_handle_submission":12.998936,"modal_scheduling":3457.566696,"output_persistence":211.551176,"post_sampling_transition":445.919445,"prompt_executor_cache_setup":575.566,"remote_local_return":16.999916,"remote_method_setup":86.01198,"remote_return_handoff":1814.440061,"restore_to_method_entry":133.968631,"sampler_node_to_sampling":1770.264742,"sampling":5086.473075,"vae":578.010137}`

### `v2_2026-08-05_05-28-07` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8f9b9abb7650`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4c5c6b0a1220439b`
- Modal task: `ta-01KZ85R1HVD3EEWB0XVWMVE3QR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5355.745,"command_to_response_ms":17972.4,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9483.764,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":89.811,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.347,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.347,"unexplained_pre_remote_ms":9393.953,"worker_unattributed_ms":null},"output_collection_ms":9.887,"pre_sampler_ms":2748.374,"restore_total_ms":2896.334,"sampler_ms":3654.144,"snapshot_callback_age_at_restore_ms":535202.445,"snapshot_callback_to_command_start_ms":529852.495,"submission_to_first_remote_event_ms":9483.764,"submit2entry_ms":7932.838,"t3b_to_t8_ms":7939.391,"vae_decode_ms":514.184,"wall_ms":17566.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.918ms unaccounted"]`
- Waterfall stages: `{"application_restore":2896.35556,"captured_timeline_gap":0.91795099999581,"clip_to_sampler_node":123.583,"first_node_to_clip":202.346,"local_preparation":401.347008,"modal_handle_submission":10.999092,"modal_scheduling":4943.399116,"output_persistence":200.841854,"post_sampling_transition":816.518661,"prompt_executor_cache_setup":187.362,"remote_local_return":16.999672,"remote_method_setup":89.838846,"remote_return_handoff":1587.243381,"restore_to_method_entry":89.068756,"sampler_node_to_sampling":920.421325,"sampling":4970.971643,"vae":514.184407}`

### `v2_2026-08-05_05-34-42` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_05-37-14` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a1a45bf078a4`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `333c94b246bb414e`
- Modal task: `ta-01KZ86T3N1YQE2XVXZT549697R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":80594.13,"command_to_response_ms":92009.0,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":83526.4,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":9.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":43.577,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.468,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.468,"unexplained_pre_remote_ms":83482.823,"worker_unattributed_ms":null},"output_collection_ms":9.045,"pre_sampler_ms":2664.452,"restore_total_ms":3143.046,"sampler_ms":3700.999,"snapshot_callback_age_at_restore_ms":39990.891,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":83526.4,"submit2entry_ms":83401.308,"t3b_to_t8_ms":8007.75,"vae_decode_ms":549.683,"wall_ms":91647.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.807ms unaccounted"]`
- Waterfall stages: `{"application_restore":3143.054648,"captured_timeline_gap":0.8070750000042608,"clip_to_sampler_node":114.081,"first_node_to_clip":129.632,"local_preparation":357.467648,"modal_handle_submission":12.000652,"modal_scheduling":80224.661364,"output_persistence":203.476,"post_sampling_transition":883.205865,"prompt_executor_cache_setup":172.973,"remote_local_return":12.000068,"remote_method_setup":43.603829,"remote_return_handoff":179.450947,"restore_to_method_entry":30.584338,"sampler_node_to_sampling":924.64379,"sampling":5027.667962,"vae":549.682582}`

### `v2_2026-08-05_05-38-55` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c30d81727aa9`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `333c94b246bb414e`
- Modal task: `ta-01KZ86T3N1YQE2XVXZT549697R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6489.2,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":151.132,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":30.051,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.847,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.847,"unexplained_pre_remote_ms":121.081,"worker_unattributed_ms":null},"output_collection_ms":7.366,"pre_sampler_ms":779.527,"restore_total_ms":3143.046,"sampler_ms":3747.801,"snapshot_callback_age_at_restore_ms":39990.891,"snapshot_callback_to_command_start_ms":60271.847,"submission_to_first_remote_event_ms":151.132,"submit2entry_ms":48.101,"t3b_to_t8_ms":5881.465,"vae_decode_ms":356.967,"wall_ms":6065.4}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -3146.128ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":3143.054648,"clip_to_sampler_node":127.047,"first_node_to_clip":25.925,"local_preparation":419.847232,"modal_handle_submission":11.998768,"modal_scheduling":48.101,"output_persistence":147.083693,"post_sampling_transition":847.282556,"prompt_executor_cache_setup":92.682,"remote_local_return":11.996452,"remote_method_setup":30.071629,"remote_return_handoff":92.268471,"restore_to_method_entry":17597.755448,"sampler_node_to_sampling":50.970417,"sampling":4230.008901,"vae":356.967012}`

### `v2_2026-08-05_05-39-21` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-496609568c15`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `333c94b246bb414e`
- Modal task: `ta-01KZ86T3N1YQE2XVXZT549697R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":9784.951,"command_to_response_ms":18378.5,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10006.94,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":42.01,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.779,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.779,"unexplained_pre_remote_ms":9964.93,"worker_unattributed_ms":null},"output_collection_ms":8.979,"pre_sampler_ms":2547.633,"restore_total_ms":571.354,"sampler_ms":3688.892,"snapshot_callback_age_at_restore_ms":95990.256,"snapshot_callback_to_command_start_ms":86216.847,"submission_to_first_remote_event_ms":10006.94,"submit2entry_ms":9955.957,"t3b_to_t8_ms":7805.519,"vae_decode_ms":546.027,"wall_ms":17950.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.913ms unaccounted"]`
- Waterfall stages: `{"application_restore":571.361695,"captured_timeline_gap":0.9132620000018505,"clip_to_sampler_node":85.345,"first_node_to_clip":83.104,"local_preparation":424.779264,"modal_handle_submission":9.998836,"modal_scheduling":9350.173196,"output_persistence":205.686261,"post_sampling_transition":811.804311,"prompt_executor_cache_setup":213.957,"remote_local_return":11.999112,"remote_method_setup":42.033917,"remote_return_handoff":132.587764,"restore_to_method_entry":31.415607,"sampler_node_to_sampling":858.278084,"sampling":4999.058157,"vae":546.026646}`

### `v2_2026-08-05_05-39-51` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b443c416eda9`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `333c94b246bb414e`
- Modal task: `ta-01KZ86T3N1YQE2XVXZT549697R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6388.9,"handle_lookup_ms":4.005,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":153.903,"generator_create_ms":4.005,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":23.901,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.035,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.035,"unexplained_pre_remote_ms":130.002,"worker_unattributed_ms":null},"output_collection_ms":11.308,"pre_sampler_ms":751.146,"restore_total_ms":571.354,"sampler_ms":3757.209,"snapshot_callback_age_at_restore_ms":95990.256,"snapshot_callback_to_command_start_ms":115706.847,"submission_to_first_remote_event_ms":153.903,"submit2entry_ms":46.443,"t3b_to_t8_ms":5779.362,"vae_decode_ms":355.864,"wall_ms":5961.4}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -572.747ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":571.361695,"clip_to_sampler_node":40.752,"first_node_to_clip":44.187,"local_preparation":424.0352,"modal_handle_submission":11.0068,"modal_scheduling":46.443,"output_persistence":156.593113,"post_sampling_transition":754.514239,"prompt_executor_cache_setup":144.437,"remote_local_return":11.99982,"remote_method_setup":23.941959,"remote_return_handoff":97.498076,"restore_to_method_entry":19611.16044,"sampler_node_to_sampling":39.149658,"sampling":4239.89116,"vae":355.866164}`

### `v2_2026-08-05_05-40-10` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a5d103386cc8`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `333c94b246bb414e`
- Modal task: `ta-01KZ86T3N1YQE2XVXZT549697R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":8383.2,"handle_lookup_ms":4.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":147.625,"generator_create_ms":4.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":40.482,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.396,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.396,"unexplained_pre_remote_ms":107.143,"worker_unattributed_ms":null},"output_collection_ms":9.417,"pre_sampler_ms":2513.97,"restore_total_ms":603.172,"sampler_ms":3710.807,"snapshot_callback_age_at_restore_ms":125848.407,"snapshot_callback_to_command_start_ms":135467.847,"submission_to_first_remote_event_ms":147.625,"submit2entry_ms":48.272,"t3b_to_t8_ms":7707.35,"vae_decode_ms":505.683,"wall_ms":7950.1}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -605.685ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":603.17607,"clip_to_sampler_node":77.504,"first_node_to_clip":82.751,"local_preparation":428.396096,"modal_handle_submission":12.001704,"modal_scheduling":48.272,"output_persistence":192.631381,"post_sampling_transition":777.932945,"prompt_executor_cache_setup":231.654,"remote_local_return":14.999272,"remote_method_setup":40.532838,"remote_return_handoff":137.142833,"restore_to_method_entry":9497.874164,"sampler_node_to_sampling":912.760431,"sampling":4923.432041,"vae":505.683387}`

### `v2_2026-08-05_05-41-11` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9b36361c140d`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `e6166de140194d6c`
- Modal task: `ta-01KZ871AY5B2KJ0Q2A7YBT5CZR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":87769.074,"command_to_response_ms":100006.3,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":91296.396,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":54.075,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.865,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.865,"unexplained_pre_remote_ms":91242.321,"worker_unattributed_ms":null},"output_collection_ms":9.16,"pre_sampler_ms":2947.152,"restore_total_ms":2670.918,"sampler_ms":3674.138,"snapshot_callback_age_at_restore_ms":47655.217,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":91296.396,"submit2entry_ms":91076.016,"t3b_to_t8_ms":8289.035,"vae_decode_ms":558.252,"wall_ms":99672.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.973ms unaccounted"]`
- Waterfall stages: `{"application_restore":2670.941834,"captured_timeline_gap":0.9730859999981476,"clip_to_sampler_node":498.822,"first_node_to_clip":3.114,"local_preparation":330.865408,"modal_handle_submission":9.000392,"modal_scheduling":87429.207864,"output_persistence":202.240135,"post_sampling_transition":901.638622,"prompt_executor_cache_setup":218.516,"remote_local_return":12.000024,"remote_method_setup":54.114474,"remote_return_handoff":239.441582,"restore_to_method_entry":973.856587,"sampler_node_to_sampling":856.593303,"sampling":5046.727538,"vae":558.252175}`

### `v2_2026-08-05_05-43-05` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-6d7de2ea84c6`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `e6166de140194d6c`
- Modal task: `ta-01KZ871AY5B2KJ0Q2A7YBT5CZR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6270.3,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":160.085,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":26.484,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.189,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.189,"unexplained_pre_remote_ms":133.601,"worker_unattributed_ms":null},"output_collection_ms":8.029,"pre_sampler_ms":722.295,"restore_total_ms":2670.918,"sampler_ms":3674.363,"snapshot_callback_age_at_restore_ms":47655.217,"snapshot_callback_to_command_start_ms":73726.687,"submission_to_first_remote_event_ms":160.085,"submit2entry_ms":64.296,"t3b_to_t8_ms":5663.536,"vae_decode_ms":358.799,"wall_ms":5879.0}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2673.061ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2670.941834,"clip_to_sampler_node":79.028,"first_node_to_clip":2.438,"local_preparation":388.188928,"modal_handle_submission":9.000372,"modal_scheduling":64.296,"output_persistence":146.251942,"post_sampling_transition":759.642655,"prompt_executor_cache_setup":121.405,"remote_local_return":10.998956,"remote_method_setup":26.529727,"remote_return_handoff":113.531395,"restore_to_method_entry":23842.460685,"sampler_node_to_sampling":37.370575,"sampling":4154.904734,"vae":358.798835}`

### `v2_2026-08-05_05-43-24` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d85e6888bcf7`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `e6166de140194d6c`
- Modal task: `ta-01KZ871AY5B2KJ0Q2A7YBT5CZR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6795.0,"handle_lookup_ms":2.004,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":149.315,"generator_create_ms":2.004,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":29.762,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.945,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.945,"unexplained_pre_remote_ms":119.553,"worker_unattributed_ms":null},"output_collection_ms":1168.978,"pre_sampler_ms":701.879,"restore_total_ms":2670.918,"sampler_ms":3234.003,"snapshot_callback_age_at_restore_ms":47655.217,"snapshot_callback_to_command_start_ms":92526.687,"submission_to_first_remote_event_ms":149.315,"submit2entry_ms":62.99,"t3b_to_t8_ms":6192.877,"vae_decode_ms":354.506,"wall_ms":6414.3}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1512.379ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2670.941834,"clip_to_sampler_node":117.24,"first_node_to_clip":1.505,"local_preparation":376.945408,"modal_handle_submission":9.001892,"modal_scheduling":62.99,"output_persistence":148.450432,"post_sampling_transition":592.086656,"prompt_executor_cache_setup":72.362,"remote_local_return":11.997924,"remote_method_setup":29.785076,"remote_return_handoff":115.84806,"restore_to_method_entry":42630.910487,"sampler_node_to_sampling":33.896465,"sampling":3709.81761,"vae":354.506465}`

### `v2_2026-08-05_05-43-41` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8978708d472c`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `e6166de140194d6c`
- Modal task: `ta-01KZ871AY5B2KJ0Q2A7YBT5CZR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6066.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":162.192,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.508,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":26.399,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.809,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.809,"unexplained_pre_remote_ms":135.792,"worker_unattributed_ms":null},"output_collection_ms":7.73,"pre_sampler_ms":713.295,"restore_total_ms":2670.918,"sampler_ms":3675.512,"snapshot_callback_age_at_restore_ms":47655.217,"snapshot_callback_to_command_start_ms":109683.687,"submission_to_first_remote_event_ms":162.192,"submit2entry_ms":63.661,"t3b_to_t8_ms":5469.085,"vae_decode_ms":353.625,"wall_ms":5684.7}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2673.210ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2670.941834,"clip_to_sampler_node":107.662,"first_node_to_clip":1.305,"local_preparation":378.808768,"modal_handle_submission":9.508332,"modal_scheduling":63.661,"output_persistence":146.738352,"post_sampling_transition":577.687059,"prompt_executor_cache_setup":81.786,"remote_local_return":11.000416,"remote_method_setup":26.420966,"remote_return_handoff":113.232065,"restore_to_method_entry":59789.954262,"sampler_node_to_sampling":46.643845,"sampling":4151.108252,"vae":353.625296}`

### `v2_2026-08-05_05-43-59` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4ed85217cab7`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `e6166de140194d6c`
- Modal task: `ta-01KZ871AY5B2KJ0Q2A7YBT5CZR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-west1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5873.3,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":153.63,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":25.991,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.87,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.87,"unexplained_pre_remote_ms":127.638,"worker_unattributed_ms":null},"output_collection_ms":6.944,"pre_sampler_ms":943.307,"restore_total_ms":2670.918,"sampler_ms":3228.949,"snapshot_callback_age_at_restore_ms":47655.217,"snapshot_callback_to_command_start_ms":127200.688,"submission_to_first_remote_event_ms":153.63,"submit2entry_ms":63.198,"t3b_to_t8_ms":5258.581,"vae_decode_ms":351.244,"wall_ms":5477.3}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2672.136ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2670.941834,"clip_to_sampler_node":342.598,"first_node_to_clip":1.203,"local_preparation":391.870336,"modal_handle_submission":8.999664,"modal_scheduling":63.198,"output_persistence":147.104162,"post_sampling_transition":585.883077,"prompt_executor_cache_setup":86.894,"remote_local_return":13.99996,"remote_method_setup":26.013157,"remote_return_handoff":114.19275,"restore_to_method_entry":77320.043541,"sampler_node_to_sampling":37.736576,"sampling":3703.524011,"vae":351.244166}`

### `v2_2026-08-05_05-44-58` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4235eebbe324`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `07ecace94b85490f`
- Modal task: `ta-01KZ8788N0WAEACMPW7D8BDWWR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":102073.931,"command_to_response_ms":113038.3,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":103414.066,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":55.553,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.245,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.245,"unexplained_pre_remote_ms":103358.513,"worker_unattributed_ms":null},"output_collection_ms":10.3,"pre_sampler_ms":4061.652,"restore_total_ms":1281.187,"sampler_ms":3691.281,"snapshot_callback_age_at_restore_ms":46447.884,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":103414.066,"submit2entry_ms":103129.871,"t3b_to_t8_ms":9184.785,"vae_decode_ms":672.56,"wall_ms":112713.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.386ms unaccounted"]`
- Waterfall stages: `{"application_restore":1281.194445,"captured_timeline_gap":2.385910999990301,"clip_to_sampler_node":486.795,"first_node_to_clip":38.66,"local_preparation":321.244864,"modal_handle_submission":9.000436,"modal_scheduling":101743.685388,"output_persistence":243.339171,"post_sampling_transition":504.597043,"prompt_executor_cache_setup":234.094,"remote_local_return":12.999232,"remote_method_setup":55.571229,"remote_return_handoff":328.613639,"restore_to_method_entry":102.983061,"sampler_node_to_sampling":1721.675979,"sampling":5278.870396,"vae":672.559838}`

### `v2_2026-08-05_05-47-05` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-db1c278e456d`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `07ecace94b85490f`
- Modal task: `ta-01KZ8788N0WAEACMPW7D8BDWWR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5997.3,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":177.119,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":30.854,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.849,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.849,"unexplained_pre_remote_ms":146.265,"worker_unattributed_ms":null},"output_collection_ms":8.332,"pre_sampler_ms":776.78,"restore_total_ms":1281.187,"sampler_ms":3709.732,"snapshot_callback_age_at_restore_ms":46447.884,"snapshot_callback_to_command_start_ms":71202.07,"submission_to_first_remote_event_ms":177.119,"submit2entry_ms":80.292,"t3b_to_t8_ms":5329.612,"vae_decode_ms":356.815,"wall_ms":5592.2}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1281.444ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1281.194445,"clip_to_sampler_node":62.296,"first_node_to_clip":47.728,"local_preparation":400.84864,"modal_handle_submission":10.00026,"modal_scheduling":80.292,"output_persistence":146.631783,"post_sampling_transition":335.841879,"prompt_executor_cache_setup":131.886,"remote_local_return":10.999352,"remote_method_setup":30.869597,"remote_return_handoff":139.382115,"restore_to_method_entry":23640.005789,"sampler_node_to_sampling":46.332676,"sampling":4197.603213,"vae":356.815823}`

### `v2_2026-08-05_05-47-22` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-eee4e1596645`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `07ecace94b85490f`
- Modal task: `ta-01KZ8788N0WAEACMPW7D8BDWWR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5589.5,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":177.595,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":33.145,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.91,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.91,"unexplained_pre_remote_ms":144.45,"worker_unattributed_ms":null},"output_collection_ms":9.368,"pre_sampler_ms":806.937,"restore_total_ms":1281.187,"sampler_ms":3259.506,"snapshot_callback_age_at_restore_ms":46447.884,"snapshot_callback_to_command_start_ms":88159.07,"submission_to_first_remote_event_ms":177.595,"submit2entry_ms":79.152,"t3b_to_t8_ms":4925.848,"vae_decode_ms":350.72,"wall_ms":5190.9}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1282.370ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1281.194445,"clip_to_sampler_node":112.01,"first_node_to_clip":36.916,"local_preparation":394.909632,"modal_handle_submission":10.000968,"modal_scheduling":79.152,"output_persistence":154.89813,"post_sampling_transition":350.585371,"prompt_executor_cache_setup":124.429,"remote_local_return":9.998408,"remote_method_setup":33.158968,"remote_return_handoff":141.189182,"restore_to_method_entry":40589.929469,"sampler_node_to_sampling":46.134102,"sampling":3746.593891,"vae":350.719551}`

### `v2_2026-08-05_05-47-38` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-732994e13766`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `a295e68602ee48e6`
- Modal task: `ta-01KZ87CMNBWJ4DAJGH6BTC78FR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":58191.816,"command_to_response_ms":67221.4,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":58576.601,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":45.141,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.679,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.679,"unexplained_pre_remote_ms":58531.459,"worker_unattributed_ms":null},"output_collection_ms":9.013,"pre_sampler_ms":2834.883,"restore_total_ms":715.484,"sampler_ms":3684.001,"snapshot_callback_age_at_restore_ms":36450.019,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":58576.601,"submit2entry_ms":58528.558,"t3b_to_t8_ms":8146.763,"vae_decode_ms":564.774,"wall_ms":66830.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.036ms unaccounted"]`
- Waterfall stages: `{"application_restore":715.504286,"captured_timeline_gap":1.0362349999631988,"clip_to_sampler_node":394.134,"first_node_to_clip":20.514,"local_preparation":386.678592,"modal_handle_submission":9.001008,"modal_scheduling":57796.136656,"output_persistence":203.665974,"post_sampling_transition":854.075197,"prompt_executor_cache_setup":186.209,"remote_local_return":14.998268,"remote_method_setup":45.186343,"remote_return_handoff":93.668411,"restore_to_method_entry":14.900774,"sampler_node_to_sampling":884.516105,"sampling":5036.366268,"vae":564.774451}`

### `v2_2026-08-05_05-49-01` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2c352fff5ec8`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `a295e68602ee48e6`
- Modal task: `ta-01KZ87CMNBWJ4DAJGH6BTC78FR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6045.1,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":158.274,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":5.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":25.844,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.707,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.707,"unexplained_pre_remote_ms":132.43,"worker_unattributed_ms":null},"output_collection_ms":7.436,"pre_sampler_ms":714.085,"restore_total_ms":715.484,"sampler_ms":3690.938,"snapshot_callback_age_at_restore_ms":36450.019,"snapshot_callback_to_command_start_ms":61377.858,"submission_to_first_remote_event_ms":158.274,"submit2entry_ms":32.804,"t3b_to_t8_ms":5505.7,"vae_decode_ms":351.853,"wall_ms":5662.4}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -717.707ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":715.504286,"clip_to_sampler_node":30.211,"first_node_to_clip":29.022,"local_preparation":379.707072,"modal_handle_submission":8.999328,"modal_scheduling":32.804,"output_persistence":145.783566,"post_sampling_transition":600.561755,"prompt_executor_cache_setup":126.445,"remote_local_return":11.99938,"remote_method_setup":25.86936,"remote_return_handoff":85.444479,"restore_to_method_entry":24613.176786,"sampler_node_to_sampling":48.800122,"sampling":4169.841884,"vae":351.85276}`

### `v2_2026-08-05_05-51-22` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8bd5e583d066`
- Policy/order: `T2` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `c4f9c4160d347317475987f4`
- Container session: `c6b0fc655ed5450d`
- Modal task: `ta-01KZ87KZ1NY2P9SN2C5CV8RJCR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-zVohSc0b6eWE6rcjB9nrwf`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":108536.431,"command_to_response_ms":126242.5,"handle_lookup_ms":2.005,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":110047.575,"generator_create_ms":2.005,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":606.976,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.646,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.646,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.192,"pre_sampler_ms":8057.089,"restore_total_ms":1434.977,"sampler_ms":3716.769,"snapshot_callback_age_at_restore_ms":55426.422,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":110047.575,"submit2entry_ms":109732.924,"t3b_to_t8_ms":13165.075,"vae_decode_ms":602.524,"wall_ms":125902.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.565ms unaccounted"]`
- Waterfall stages: `{"application_restore":1434.991453,"captured_timeline_gap":2.5647940000199014,"clip_to_sampler_node":4727.36,"first_node_to_clip":4.207,"local_preparation":336.646144,"modal_handle_submission":9.004756,"modal_scheduling":108190.78046,"output_persistence":246.175709,"post_sampling_transition":535.473089,"prompt_executor_cache_setup":158.128,"remote_local_return":18.000628,"remote_method_setup":607.145305,"remote_return_handoff":2561.062559,"restore_to_method_entry":104.136572,"sampler_node_to_sampling":1799.370511,"sampling":4904.921457,"vae":602.524491}`

### `v2_2026-08-05_05-53-41` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0caafebac514`
- Policy/order: `T2` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `c4f9c4160d347317475987f4`
- Container session: `c6b0fc655ed5450d`
- Modal task: `ta-01KZ87KZ1NY2P9SN2C5CV8RJCR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-zVohSc0b6eWE6rcjB9nrwf`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6069.4,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":191.704,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":30.672,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.892,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.892,"unexplained_pre_remote_ms":161.032,"worker_unattributed_ms":null},"output_collection_ms":9.131,"pre_sampler_ms":781.576,"restore_total_ms":1434.977,"sampler_ms":3743.386,"snapshot_callback_age_at_restore_ms":55426.422,"snapshot_callback_to_command_start_ms":86031.431,"submission_to_first_remote_event_ms":191.704,"submit2entry_ms":82.537,"t3b_to_t8_ms":5392.13,"vae_decode_ms":358.467,"wall_ms":5675.3}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1434.910ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1434.991453,"clip_to_sampler_node":125.125,"first_node_to_clip":3.377,"local_preparation":389.89248,"modal_handle_submission":9.00132,"modal_scheduling":82.537,"output_persistence":148.624388,"post_sampling_transition":354.235034,"prompt_executor_cache_setup":118.522,"remote_local_return":14.000044,"remote_method_setup":30.685697,"remote_return_handoff":154.540733,"restore_to_method_entry":29569.996032,"sampler_node_to_sampling":45.205349,"sampling":4235.084215,"vae":358.467051}`

### `v2_2026-08-05_05-54-00` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1deaed184546`
- Policy/order: `T2` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `c4f9c4160d347317475987f4`
- Container session: `c6b0fc655ed5450d`
- Modal task: `ta-01KZ87KZ1NY2P9SN2C5CV8RJCR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-1`
- Image: `im-zVohSc0b6eWE6rcjB9nrwf`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":9602.089,"command_to_response_ms":31001.3,"handle_lookup_ms":2.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":12040.42,"generator_create_ms":1.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":417.761,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.607,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.607,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":15.303,"pre_sampler_ms":12760.85,"restore_total_ms":2760.656,"sampler_ms":3752.58,"snapshot_callback_age_at_restore_ms":114654.272,"snapshot_callback_to_command_start_ms":105077.431,"submission_to_first_remote_event_ms":12040.42,"submit2entry_ms":11959.579,"t3b_to_t8_ms":18058.583,"vae_decode_ms":663.638,"wall_ms":30574.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 4.443ms unaccounted"]`
- Waterfall stages: `{"application_restore":2760.661725,"captured_timeline_gap":4.442504999999073,"clip_to_sampler_node":2623.28,"first_node_to_clip":478.069,"local_preparation":423.606784,"modal_handle_submission":9.000616,"modal_scheduling":9169.48156,"output_persistence":252.823707,"post_sampling_transition":621.218987,"prompt_executor_cache_setup":606.403,"remote_local_return":17.001272,"remote_method_setup":417.808668,"remote_return_handoff":124.713324,"restore_to_method_entry":26.43034,"sampler_node_to_sampling":7615.38809,"sampling":5187.321883,"vae":663.638011}`

### `v2_2026-08-05_05-54-43` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4bdffe0c7fa6`
- Policy/order: `T2` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `c4f9c4160d347317475987f4`
- Container session: `c6b0fc655ed5450d`
- Modal task: `ta-01KZ87KZ1NY2P9SN2C5CV8RJCR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-1`
- Image: `im-zVohSc0b6eWE6rcjB9nrwf`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5942.2,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":180.325,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":33.046,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.146,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.146,"unexplained_pre_remote_ms":147.279,"worker_unattributed_ms":null},"output_collection_ms":9.932,"pre_sampler_ms":767.321,"restore_total_ms":2760.656,"sampler_ms":3745.072,"snapshot_callback_age_at_restore_ms":114654.272,"snapshot_callback_to_command_start_ms":148365.431,"submission_to_first_remote_event_ms":180.325,"submit2entry_ms":39.674,"t3b_to_t8_ms":5357.568,"vae_decode_ms":353.398,"wall_ms":5555.0}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2760.370ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2760.661725,"clip_to_sampler_node":82.44,"first_node_to_clip":2.711,"local_preparation":383.145728,"modal_handle_submission":9.001972,"modal_scheduling":39.674,"output_persistence":150.404321,"post_sampling_transition":336.547703,"prompt_executor_cache_setup":142.381,"remote_local_return":11.999348,"remote_method_setup":33.067401,"remote_return_handoff":110.804656,"restore_to_method_entry":31355.066789,"sampler_node_to_sampling":47.247415,"sampling":4239.070352,"vae":353.397458}`

### `v2_2026-08-05_05-55-01` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9f2b280ebb50`
- Policy/order: `T2` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `c4f9c4160d347317475987f4`
- Container session: `c6b0fc655ed5450d`
- Modal task: `ta-01KZ87KZ1NY2P9SN2C5CV8RJCR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-1`
- Image: `im-zVohSc0b6eWE6rcjB9nrwf`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5527.2,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":179.544,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":33.178,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.063,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.063,"unexplained_pre_remote_ms":146.365,"worker_unattributed_ms":null},"output_collection_ms":9.241,"pre_sampler_ms":755.855,"restore_total_ms":2760.656,"sampler_ms":3297.268,"snapshot_callback_age_at_restore_ms":114654.272,"snapshot_callback_to_command_start_ms":165894.43,"submission_to_first_remote_event_ms":179.544,"submit2entry_ms":30.729,"t3b_to_t8_ms":4953.842,"vae_decode_ms":359.75,"wall_ms":5148.4}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -2760.363ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":2760.661725,"clip_to_sampler_node":80.4,"first_node_to_clip":5.01,"local_preparation":376.062912,"modal_handle_submission":9.000688,"modal_scheduling":30.729,"output_persistence":153.868942,"post_sampling_transition":382.974058,"prompt_executor_cache_setup":137.64,"remote_local_return":13.998936,"remote_method_setup":33.192974,"remote_return_handoff":115.00607,"restore_to_method_entry":48867.037856,"sampler_node_to_sampling":47.031704,"sampling":3782.22319,"vae":359.74963}`

### `v2_2026-08-05_05-56-19` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e263848afebb`
- Policy/order: `T2` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `08fca4633e71b0b90b5fc37e`
- Container session: `8d7b31d6b10c4415`
- Modal task: `ta-01KZ87X1GF5T488CMKH8JPMN3R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-uJcN9toROFW5ZZLkRK3a2S`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":103360.307,"command_to_response_ms":120161.3,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":104893.782,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":675.657,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.498,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.498,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.411,"pre_sampler_ms":7836.092,"restore_total_ms":1465.184,"sampler_ms":3678.547,"snapshot_callback_age_at_restore_ms":53540.081,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":104893.782,"submit2entry_ms":104594.631,"t3b_to_t8_ms":12809.025,"vae_decode_ms":581.387,"wall_ms":119831.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.358ms unaccounted"]`
- Waterfall stages: `{"application_restore":1465.286155,"captured_timeline_gap":1.357964999973774,"clip_to_sampler_node":4818.13,"first_node_to_clip":33.544,"local_preparation":326.4976,"modal_handle_submission":9.9997,"modal_scheduling":103023.809708,"output_persistence":224.477265,"post_sampling_transition":484.517382,"prompt_executor_cache_setup":130.193,"remote_local_return":12.001608,"remote_method_setup":675.675092,"remote_return_handoff":1737.771632,"restore_to_method_entry":102.516202,"sampler_node_to_sampling":1706.293197,"sampling":4827.860008,"vae":581.387694}`

### `v2_2026-08-05_05-58-33` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5c799786e5e5`
- Policy/order: `T2` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `08fca4633e71b0b90b5fc37e`
- Container session: `8d7b31d6b10c4415`
- Modal task: `ta-01KZ87X1GF5T488CMKH8JPMN3R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-uJcN9toROFW5ZZLkRK3a2S`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6631.72,"command_to_response_ms":31056.1,"handle_lookup_ms":3.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":11256.978,"generator_create_ms":3.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":723.917,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.211,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.211,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.422,"pre_sampler_ms":13005.64,"restore_total_ms":5118.715,"sampler_ms":3699.046,"snapshot_callback_age_at_restore_ms":90461.069,"snapshot_callback_to_command_start_ms":83859.181,"submission_to_first_remote_event_ms":11256.978,"submit2entry_ms":11145.607,"t3b_to_t8_ms":18118.647,"vae_decode_ms":625.055,"wall_ms":30351.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 3.105ms unaccounted"]`
- Waterfall stages: `{"application_restore":5118.723784,"captured_timeline_gap":3.104605000000447,"clip_to_sampler_node":330.357,"first_node_to_clip":461.439,"local_preparation":699.211328,"modal_handle_submission":14.000972,"modal_scheduling":5918.508212,"output_persistence":232.439134,"post_sampling_transition":549.690462,"prompt_executor_cache_setup":2960.338,"remote_local_return":15.00128,"remote_method_setup":723.936964,"remote_return_handoff":346.971408,"restore_to_method_entry":104.372447,"sampler_node_to_sampling":7776.90446,"sampling":5176.089792,"vae":625.054832}`

### `v2_2026-08-05_05-59-15` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-76f16828ecdd`
- Policy/order: `T2` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `08fca4633e71b0b90b5fc37e`
- Container session: `8d7b31d6b10c4415`
- Modal task: `ta-01KZ87X1GF5T488CMKH8JPMN3R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-uJcN9toROFW5ZZLkRK3a2S`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5949.2,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":191.005,"generator_create_ms":3.003,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":28.545,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.642,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.642,"unexplained_pre_remote_ms":162.46,"worker_unattributed_ms":null},"output_collection_ms":9.307,"pre_sampler_ms":744.598,"restore_total_ms":5118.715,"sampler_ms":3706.818,"snapshot_callback_age_at_restore_ms":90461.069,"snapshot_callback_to_command_start_ms":126178.181,"submission_to_first_remote_event_ms":191.005,"submit2entry_ms":79.675,"t3b_to_t8_ms":5283.348,"vae_decode_ms":351.524,"wall_ms":5563.3}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -5120.492ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":5118.723784,"clip_to_sampler_node":76.383,"first_node_to_clip":34.711,"local_preparation":382.641536,"modal_handle_submission":10.001064,"modal_scheduling":79.675,"output_persistence":140.971547,"post_sampling_transition":334.784783,"prompt_executor_cache_setup":110.588,"remote_local_return":10.996976,"remote_method_setup":28.568242,"remote_return_handoff":158.800808,"restore_to_method_entry":31036.866392,"sampler_node_to_sampling":41.057096,"sampling":4190.250942,"vae":351.524522}`

### `v2_2026-08-05_05-59-35` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8bf21cad789f`
- Policy/order: `T2` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `08fca4633e71b0b90b5fc37e`
- Container session: `8d7b31d6b10c4415`
- Modal task: `ta-01KZ87X1GF5T488CMKH8JPMN3R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-uJcN9toROFW5ZZLkRK3a2S`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4413.242,"command_to_response_ms":14561.2,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5276.263,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":406.429,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.932,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.932,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.697,"pre_sampler_ms":3311.31,"restore_total_ms":1138.698,"sampler_ms":3678.873,"snapshot_callback_age_at_restore_ms":150193.545,"snapshot_callback_to_command_start_ms":145813.181,"submission_to_first_remote_event_ms":5276.263,"submit2entry_ms":5153.809,"t3b_to_t8_ms":8139.181,"vae_decode_ms":542.467,"wall_ms":14051.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.507ms unaccounted"]`
- Waterfall stages: `{"application_restore":1138.738854,"captured_timeline_gap":1.5066040000037901,"clip_to_sampler_node":40.607,"first_node_to_clip":34.132,"local_preparation":504.932032,"modal_handle_submission":10.000468,"modal_scheduling":3898.309036,"output_persistence":206.61329,"post_sampling_transition":396.057669,"prompt_executor_cache_setup":554.838,"remote_local_return":14.999084,"remote_method_setup":406.453458,"remote_return_handoff":341.369588,"restore_to_method_entry":114.029589,"sampler_node_to_sampling":1488.010138,"sampling":4868.122586,"vae":542.466588}`

### `v2_2026-08-05_06-00-02` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c039d39a1590`
- Policy/order: `T2` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `08fca4633e71b0b90b5fc37e`
- Container session: `8d7b31d6b10c4415`
- Modal task: `ta-01KZ87X1GF5T488CMKH8JPMN3R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-uJcN9toROFW5ZZLkRK3a2S`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5915.5,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":193.708,"generator_create_ms":3.003,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":5.997,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":28.769,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.47,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.47,"unexplained_pre_remote_ms":164.939,"worker_unattributed_ms":null},"output_collection_ms":9.467,"pre_sampler_ms":718.839,"restore_total_ms":1138.698,"sampler_ms":3684.029,"snapshot_callback_age_at_restore_ms":150193.545,"snapshot_callback_to_command_start_ms":173207.181,"submission_to_first_remote_event_ms":193.708,"submit2entry_ms":75.388,"t3b_to_t8_ms":5239.932,"vae_decode_ms":354.719,"wall_ms":5513.7}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1141.085ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1138.738854,"clip_to_sampler_node":57.811,"first_node_to_clip":33.997,"local_preparation":398.470464,"modal_handle_submission":8.999136,"modal_scheduling":75.388,"output_persistence":145.050107,"post_sampling_transition":333.341233,"prompt_executor_cache_setup":103.153,"remote_local_return":10.998924,"remote_method_setup":28.790257,"remote_return_handoff":157.926294,"restore_to_method_entry":22321.144179,"sampler_node_to_sampling":40.105509,"sampling":4169.14459,"vae":354.718591}`

### `v2_2026-08-05_06-01-28` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-cbde6ebada6c`
- Policy/order: `T2` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5a0cfbabed36ea2a9327da69`
- Container session: `effe440f59b34c46`
- Modal task: `ta-01KZ886ETPB4MJX1YQ59D7ABDR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-A4DxJmLsSB9Vv1xCy2afkI`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":190980.288,"command_to_response_ms":209382.8,"handle_lookup_ms":2.588,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":191734.821,"generator_create_ms":2.589,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":1995.631,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.78,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.78,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.065,"pre_sampler_ms":8741.639,"restore_total_ms":954.545,"sampler_ms":3733.425,"snapshot_callback_age_at_restore_ms":38933.709,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":191734.821,"submit2entry_ms":191628.066,"t3b_to_t8_ms":14203.24,"vae_decode_ms":660.555,"wall_ms":209053.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.123ms unaccounted"]`
- Waterfall stages: `{"application_restore":954.553232,"captured_timeline_gap":2.1225760000234004,"clip_to_sampler_node":4850.387,"first_node_to_clip":71.579,"local_preparation":326.78048,"modal_handle_submission":9.58842,"modal_scheduling":190643.91942,"output_persistence":251.708746,"post_sampling_transition":804.156476,"prompt_executor_cache_setup":138.725,"remote_local_return":11.998296,"remote_method_setup":1995.662102,"remote_return_handoff":1213.98872,"restore_to_method_entry":25.9964,"sampler_node_to_sampling":2374.829817,"sampling":5046.232448,"vae":660.555163}`

### `v2_2026-08-05_06-05-09` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-03c57bf6d41d`
- Policy/order: `T2` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5a0cfbabed36ea2a9327da69`
- Container session: `effe440f59b34c46`
- Modal task: `ta-01KZ886ETPB4MJX1YQ59D7ABDR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-A4DxJmLsSB9Vv1xCy2afkI`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6826.0,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":197.0,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":36.525,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.225,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.225,"unexplained_pre_remote_ms":160.475,"worker_unattributed_ms":null},"output_collection_ms":9.193,"pre_sampler_ms":783.786,"restore_total_ms":954.545,"sampler_ms":3732.48,"snapshot_callback_age_at_restore_ms":38933.709,"snapshot_callback_to_command_start_ms":68976.157,"submission_to_first_remote_event_ms":197.0,"submit2entry_ms":40.444,"t3b_to_t8_ms":5574.867,"vae_decode_ms":360.038,"wall_ms":5791.1}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -955.499ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":954.553232,"clip_to_sampler_node":53.048,"first_node_to_clip":49.699,"local_preparation":1031.225152,"modal_handle_submission":10.000148,"modal_scheduling":40.444,"output_persistence":151.17513,"post_sampling_transition":543.320809,"prompt_executor_cache_setup":140.463,"remote_local_return":13.000076,"remote_method_setup":36.540192,"remote_return_handoff":124.821156,"restore_to_method_entry":29855.819566,"sampler_node_to_sampling":50.40164,"sampling":4222.721863,"vae":360.038096}`

### `v2_2026-08-05_06-05-27` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2d9fdc60408e`
- Policy/order: `T2` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5a0cfbabed36ea2a9327da69`
- Container session: `effe440f59b34c46`
- Modal task: `ta-01KZ886ETPB4MJX1YQ59D7ABDR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-A4DxJmLsSB9Vv1xCy2afkI`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":5530.1,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":194.558,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":34.957,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":16.0,"payload_size_measurement_ms":16.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.627,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.627,"unexplained_pre_remote_ms":159.6,"worker_unattributed_ms":null},"output_collection_ms":9.264,"pre_sampler_ms":756.046,"restore_total_ms":954.545,"sampler_ms":3274.284,"snapshot_callback_age_at_restore_ms":38933.709,"snapshot_callback_to_command_start_ms":87237.157,"submission_to_first_remote_event_ms":194.558,"submit2entry_ms":32.83,"t3b_to_t8_ms":4938.913,"vae_decode_ms":359.54,"wall_ms":5146.2}`
- Waterfall warnings: `["Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -956.610ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":954.553232,"clip_to_sampler_node":41.996,"first_node_to_clip":55.247,"local_preparation":380.626688,"modal_handle_submission":9.000312,"modal_scheduling":32.83,"output_persistence":151.042378,"post_sampling_transition":395.345487,"prompt_executor_cache_setup":126.237,"remote_local_return":11.000032,"remote_method_setup":34.97153,"remote_return_handoff":127.24093,"restore_to_method_entry":47457.607804,"sampler_node_to_sampling":49.146054,"sampling":3757.925259,"vae":359.53979}`

### `v2_2026-08-05_06-05-43` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a305b7c437f2`
- Policy/order: `T2` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5a0cfbabed36ea2a9327da69`
- Container session: `effe440f59b34c46`
- Modal task: `ta-01KZ886ETPB4MJX1YQ59D7ABDR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-A4DxJmLsSB9Vv1xCy2afkI`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":16538.3,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":180.902,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":333.914,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.299,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.299,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.64,"pre_sampler_ms":10209.434,"restore_total_ms":1047.742,"sampler_ms":3711.264,"snapshot_callback_age_at_restore_ms":97700.674,"snapshot_callback_to_command_start_ms":103729.157,"submission_to_first_remote_event_ms":180.902,"submit2entry_ms":33.368,"t3b_to_t8_ms":15591.437,"vae_decode_ms":700.901,"wall_ms":16150.8}`
- Waterfall warnings: `["reconciliation exceeds tolerance: -5656.558ms > 82.691ms"]`
- Waterfall stages: `{"application_restore":1047.749811,"clip_to_sampler_node":801.084,"first_node_to_clip":47.635,"local_preparation":383.298816,"modal_handle_submission":10.000984,"modal_scheduling":33.368,"output_persistence":257.529022,"post_sampling_transition":701.311478,"prompt_executor_cache_setup":1319.059,"remote_local_return":12.998536,"remote_method_setup":333.938965,"remote_return_handoff":178.455459,"restore_to_method_entry":5383.135269,"sampler_node_to_sampling":5459.231211,"sampling":5525.14183,"vae":700.900687}`

### `v2_2026-08-05_09-54-00` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-284e079804de`
- Policy/order: `T2` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `8e9bee52d545d8677799723f`
- Container session: `49ec7ba381744326`
- Modal task: `ta-01KZ8NG85P11GHF4WK76A0YCZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-AQRjy82DGdPm5V8YzHN7BQ`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":145046.264,"command_to_response_ms":161729.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":146624.031,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":590.762,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.086,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.086,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.259,"pre_sampler_ms":7775.383,"restore_total_ms":1328.675,"sampler_ms":3698.149,"snapshot_callback_age_at_restore_ms":42176.334,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":146624.031,"submit2entry_ms":146126.817,"t3b_to_t8_ms":12864.243,"vae_decode_ms":626.231,"wall_ms":161379.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.913ms unaccounted"]`
- Waterfall stages: `{"application_restore":1328.686904,"captured_timeline_gap":2.9128839999902993,"clip_to_sampler_node":4379.078,"first_node_to_clip":37.231,"local_preparation":346.0864,"modal_handle_submission":10.9981,"modal_scheduling":144689.179308,"output_persistence":249.490246,"post_sampling_transition":503.893878,"prompt_executor_cache_setup":162.56,"remote_local_return":10.999984,"remote_method_setup":590.781465,"remote_return_handoff":1952.564977,"restore_to_method_entry":105.937361,"sampler_node_to_sampling":1792.291102,"sampling":4940.994536,"vae":626.231039}`

### `v2_2026-08-05_09-56-54` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-019f38c012f5`
- Policy/order: `T2` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `8e9bee52d545d8677799723f`
- Container session: `49ec7ba381744326`
- Modal task: `ta-01KZ8NG85P11GHF4WK76A0YCZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-AQRjy82DGdPm5V8YzHN7BQ`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6045.8,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":194.774,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":32.87,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.272,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.272,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.521,"pre_sampler_ms":776.584,"restore_total_ms":1328.675,"sampler_ms":3711.629,"snapshot_callback_age_at_restore_ms":42176.334,"snapshot_callback_to_command_start_ms":71179.616,"submission_to_first_remote_event_ms":194.773,"submit2entry_ms":-116.345,"t3b_to_t8_ms":5340.928,"vae_decode_ms":354.998,"wall_ms":5627.3}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1445.971ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1328.686904,"clip_to_sampler_node":68.706,"first_node_to_clip":40.114,"local_preparation":414.271936,"modal_handle_submission":11.000664,"modal_scheduling":null,"output_persistence":151.460453,"post_sampling_transition":341.395028,"prompt_executor_cache_setup":124.752,"remote_local_return":11.000304,"remote_method_setup":32.886807,"remote_return_handoff":356.148296,"restore_to_method_entry":27935.963062,"sampler_node_to_sampling":51.791191,"sampling":4204.545822,"vae":354.998248}`

### `v2_2026-08-05_09-57-13` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-162668248689`
- Policy/order: `T2` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `8e9bee52d545d8677799723f`
- Container session: `49ec7ba381744326`
- Modal task: `ta-01KZ8NG85P11GHF4WK76A0YCZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-AQRjy82DGdPm5V8YzHN7BQ`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":8832.662,"command_to_response_ms":19517.1,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9860.833,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":296.945,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.472,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.472,"unexplained_pre_remote_ms":9563.887,"worker_unattributed_ms":null},"output_collection_ms":11.486,"pre_sampler_ms":3583.273,"restore_total_ms":1053.879,"sampler_ms":3691.178,"snapshot_callback_age_at_restore_ms":98318.338,"snapshot_callback_to_command_start_ms":89768.616,"submission_to_first_remote_event_ms":9860.833,"submit2entry_ms":9552.609,"t3b_to_t8_ms":8679.162,"vae_decode_ms":664.64,"wall_ms":19082.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.863ms unaccounted"]`
- Waterfall stages: `{"application_restore":1053.888075,"captured_timeline_gap":0.8632610000022396,"clip_to_sampler_node":55.325,"first_node_to_clip":35.871,"local_preparation":430.472064,"modal_handle_submission":9.999536,"modal_scheduling":8392.190032,"output_persistence":233.451782,"post_sampling_transition":497.730668,"prompt_executor_cache_setup":307.58,"remote_local_return":13.99848,"remote_method_setup":296.967291,"remote_return_handoff":538.303382,"restore_to_method_entry":103.52288,"sampler_node_to_sampling":1640.704147,"sampling":5241.603686,"vae":664.640396}`

### `v2_2026-08-05_09-57-45` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8085c77bd768`
- Policy/order: `T2` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `8e9bee52d545d8677799723f`
- Container session: `49ec7ba381744326`
- Modal task: `ta-01KZ8NG85P11GHF4WK76A0YCZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-AQRjy82DGdPm5V8YzHN7BQ`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5033.992,"command_to_response_ms":16078.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6399.234,"generator_create_ms":1.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":399.123,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.879,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.879,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.551,"pre_sampler_ms":3152.741,"restore_total_ms":1368.973,"sampler_ms":3710.867,"snapshot_callback_age_at_restore_ms":126449.668,"snapshot_callback_to_command_start_ms":121695.616,"submission_to_first_remote_event_ms":6399.234,"submit2entry_ms":6086.632,"t3b_to_t8_ms":8601.02,"vae_decode_ms":652.564,"wall_ms":15663.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.459ms unaccounted"]`
- Waterfall stages: `{"application_restore":1369.006905,"captured_timeline_gap":1.4593740000000253,"clip_to_sampler_node":46.802,"first_node_to_clip":36.894,"local_preparation":411.879104,"modal_handle_submission":10.001196,"modal_scheduling":4612.111572,"output_persistence":256.677171,"post_sampling_transition":815.675052,"prompt_executor_cache_setup":231.489,"remote_local_return":13.004712,"remote_method_setup":399.141246,"remote_return_handoff":564.23273,"restore_to_method_entry":102.480878,"sampler_node_to_sampling":1500.712136,"sampling":5054.748599,"vae":652.563237}`

### `v2_2026-08-05_09-58-16` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-6053280bc87d`
- Policy/order: `T2` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `8e9bee52d545d8677799723f`
- Container session: `49ec7ba381744326`
- Modal task: `ta-01KZ8NG85P11GHF4WK76A0YCZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-AQRjy82DGdPm5V8YzHN7BQ`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":null,"command_to_response_ms":6480.0,"handle_lookup_ms":2.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":191.299,"generator_create_ms":2.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":32.595,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.667,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.667,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":7.542,"pre_sampler_ms":1169.015,"restore_total_ms":1368.973,"sampler_ms":3707.98,"snapshot_callback_age_at_restore_ms":126449.668,"snapshot_callback_to_command_start_ms":152976.616,"submission_to_first_remote_event_ms":191.299,"submit2entry_ms":-116.842,"t3b_to_t8_ms":5759.726,"vae_decode_ms":354.857,"wall_ms":6046.4}`
- Waterfall warnings: `["Modal scheduling/host snapshot restoration: negative duration","Restore-to-method entry: duration exceeds command-to-response total","reconciliation exceeds tolerance: -1488.800ms > 50.000ms"]`
- Waterfall stages: `{"application_restore":1369.006905,"clip_to_sampler_node":488.935,"first_node_to_clip":33.93,"local_preparation":429.666944,"modal_handle_submission":11.000756,"modal_scheduling":null,"output_persistence":147.85789,"post_sampling_transition":377.38271,"prompt_executor_cache_setup":110.798,"remote_local_return":11.999772,"remote_method_setup":32.608602,"remote_return_handoff":357.462532,"restore_to_method_entry":25197.795196,"sampler_node_to_sampling":47.250522,"sampling":4196.075248,"vae":354.857055}`

### `v2_2026-08-05_10-00-49` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-10270cb3202c`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `5b4d69db73d2494a`
- Modal task: `ta-01KZ8NWPTHBHJT5Y2K81BZ31TR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":111278.995,"command_to_response_ms":120674.0,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":112030.56,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":48.94,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.275,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.275,"unexplained_pre_remote_ms":111981.62,"worker_unattributed_ms":null},"output_collection_ms":8.175,"pre_sampler_ms":2803.012,"restore_total_ms":893.014,"sampler_ms":3696.624,"snapshot_callback_age_at_restore_ms":43755.573,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":112030.56,"submit2entry_ms":111746.552,"t3b_to_t8_ms":8081.427,"vae_decode_ms":563.615,"wall_ms":120239.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.846ms unaccounted"]`
- Waterfall stages: `{"application_restore":893.022772,"captured_timeline_gap":0.8462489999947138,"clip_to_sampler_node":143.06,"first_node_to_clip":140.188,"local_preparation":430.274688,"modal_handle_submission":11.000812,"modal_scheduling":110837.719828,"output_persistence":201.117067,"post_sampling_transition":811.218628,"prompt_executor_cache_setup":211.016,"remote_local_return":11.998012,"remote_method_setup":48.987364,"remote_return_handoff":348.934086,"restore_to_method_entry":12.792728,"sampler_node_to_sampling":975.433533,"sampling":5032.782401,"vae":563.614744}`

### `v2_2026-08-05_10-03-23` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-249732cd3905`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `5b4d69db73d2494a`
- Modal task: `ta-01KZ8NWPTHBHJT5Y2K81BZ31TR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":9540.019,"command_to_response_ms":18412.1,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9876.09,"generator_create_ms":1.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":10.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":47.006,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.915,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.915,"unexplained_pre_remote_ms":9829.084,"worker_unattributed_ms":null},"output_collection_ms":8.273,"pre_sampler_ms":2655.387,"restore_total_ms":493.693,"sampler_ms":3680.171,"snapshot_callback_age_at_restore_ms":96709.752,"snapshot_callback_to_command_start_ms":87183.359,"submission_to_first_remote_event_ms":9876.09,"submit2entry_ms":9620.246,"t3b_to_t8_ms":7999.344,"vae_decode_ms":561.39,"wall_ms":17986.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.976ms unaccounted"]`
- Waterfall stages: `{"application_restore":493.709966,"captured_timeline_gap":0.9758059999985562,"clip_to_sampler_node":69.265,"first_node_to_clip":70.701,"local_preparation":419.915392,"modal_handle_submission":12.000808,"modal_scheduling":9108.103128,"output_persistence":216.400446,"post_sampling_transition":879.560387,"prompt_executor_cache_setup":283.276,"remote_local_return":12.999476,"remote_method_setup":47.069934,"remote_return_handoff":305.223583,"restore_to_method_entry":15.419429,"sampler_node_to_sampling":903.327245,"sampling":5012.77896,"vae":561.390816}`

### `v2_2026-08-05_10-04-20` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-da07b24c8ebd`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `609cb8f320be4499`
- Modal task: `ta-01KZ8P34V2S2DK88CX4Z551QPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":170940.094,"command_to_response_ms":181552.1,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":171319.491,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.78,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.626,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.626,"unexplained_pre_remote_ms":171268.71,"worker_unattributed_ms":null},"output_collection_ms":10.214,"pre_sampler_ms":4364.365,"restore_total_ms":541.665,"sampler_ms":3757.093,"snapshot_callback_age_at_restore_ms":52863.231,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":171319.491,"submit2entry_ms":171016.3,"t3b_to_t8_ms":9628.781,"vae_decode_ms":624.389,"wall_ms":181062.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.983ms unaccounted"]`
- Waterfall stages: `{"application_restore":541.675797,"captured_timeline_gap":2.9833870000147726,"clip_to_sampler_node":139.973,"first_node_to_clip":91.813,"local_preparation":485.625856,"modal_handle_submission":10.999244,"modal_scheduling":170443.469108,"output_persistence":221.717861,"post_sampling_transition":647.211281,"prompt_executor_cache_setup":260.755,"remote_local_return":14.002544,"remote_method_setup":50.813362,"remote_return_handoff":351.638562,"restore_to_method_entry":28.144299,"sampler_node_to_sampling":2445.997427,"sampling":5190.906215,"vae":624.389001}`

### `v2_2026-08-05_10-07-57` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2a5a2229ce28`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `609cb8f320be4499`
- Modal task: `ta-01KZ8P34V2S2DK88CX4Z551QPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6566.892,"command_to_response_ms":29768.5,"handle_lookup_ms":3.003,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7882.099,"generator_create_ms":3.003,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":82.732,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.198,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.198,"unexplained_pre_remote_ms":7799.368,"worker_unattributed_ms":null},"output_collection_ms":12.147,"pre_sampler_ms":16185.017,"restore_total_ms":1451.431,"sampler_ms":3729.965,"snapshot_callback_age_at_restore_ms":106179.45,"snapshot_callback_to_command_start_ms":99615.757,"submission_to_first_remote_event_ms":7882.099,"submit2entry_ms":7608.112,"t3b_to_t8_ms":21297.822,"vae_decode_ms":602.442,"wall_ms":29324.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 42.962ms unaccounted"]`
- Waterfall stages: `{"application_restore":1451.440547,"captured_timeline_gap":42.96237300000212,"clip_to_sampler_node":2045.354,"first_node_to_clip":1201.877,"local_preparation":439.19808,"modal_handle_submission":11.00312,"modal_scheduling":6116.690448,"output_persistence":232.121944,"post_sampling_transition":537.517352,"prompt_executor_cache_setup":776.587,"remote_local_return":12.5093,"remote_method_setup":82.793338,"remote_return_handoff":347.068588,"restore_to_method_entry":36.970796,"sampler_node_to_sampling":10727.628369,"sampling":5104.287374,"vae":602.441571}`

### `v2_2026-08-05_10-09-00` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c2dc537f49ef`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `609cb8f320be4499`
- Modal task: `ta-01KZ8P34V2S2DK88CX4Z551QPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5981.927,"command_to_response_ms":17374.7,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7154.133,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":116.099,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.169,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.169,"unexplained_pre_remote_ms":7038.034,"worker_unattributed_ms":null},"output_collection_ms":12.284,"pre_sampler_ms":4402.56,"restore_total_ms":1279.178,"sampler_ms":3743.533,"snapshot_callback_age_at_restore_ms":168683.635,"snapshot_callback_to_command_start_ms":162715.757,"submission_to_first_remote_event_ms":7154.133,"submit2entry_ms":6870.843,"t3b_to_t8_ms":9593.013,"vae_decode_ms":614.167,"wall_ms":16937.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.727ms unaccounted"]`
- Waterfall stages: `{"application_restore":1279.197761,"captured_timeline_gap":0.7271880000007513,"clip_to_sampler_node":74.464,"first_node_to_clip":50.941,"local_preparation":433.168768,"modal_handle_submission":11.001632,"modal_scheduling":5537.756384,"output_persistence":236.141413,"post_sampling_transition":585.237696,"prompt_executor_cache_setup":719.711,"remote_local_return":12.999408,"remote_method_setup":116.457622,"remote_return_handoff":343.889266,"restore_to_method_entry":50.876814,"sampler_node_to_sampling":2134.292959,"sampling":5173.678871,"vae":614.166826}`

### `v2_2026-08-05_10-09-53` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5284ce2e1eab`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `609cb8f320be4499`
- Modal task: `ta-01KZ8P34V2S2DK88CX4Z551QPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4756.545,"command_to_response_ms":15323.4,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5631.034,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":140.215,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.739,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.739,"unexplained_pre_remote_ms":5490.819,"worker_unattributed_ms":null},"output_collection_ms":11.487,"pre_sampler_ms":3946.105,"restore_total_ms":950.931,"sampler_ms":3714.979,"snapshot_callback_age_at_restore_ms":220366.88,"snapshot_callback_to_command_start_ms":215623.757,"submission_to_first_remote_event_ms":5631.034,"submit2entry_ms":5333.613,"t3b_to_t8_ms":9067.807,"vae_decode_ms":611.004,"wall_ms":14911.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.672ms unaccounted"]`
- Waterfall stages: `{"application_restore":950.943439,"captured_timeline_gap":1.6722259999987727,"clip_to_sampler_node":52.735,"first_node_to_clip":45.971,"local_preparation":407.739008,"modal_handle_submission":10.000292,"modal_scheduling":4338.80534,"output_persistence":228.440162,"post_sampling_transition":556.340485,"prompt_executor_cache_setup":471.263,"remote_local_return":16.002604,"remote_method_setup":140.23922,"remote_return_handoff":354.506611,"restore_to_method_entry":40.857164,"sampler_node_to_sampling":1993.887008,"sampling":5103.009348,"vae":611.004797}`

### `v2_2026-08-05_10-10-41` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e55c3cb80561`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `609cb8f320be4499`
- Modal task: `ta-01KZ8P34V2S2DK88CX4Z551QPR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5293.863,"command_to_response_ms":16360.6,"handle_lookup_ms":2.677,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6438.381,"generator_create_ms":2.677,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":54.211,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.332,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.332,"unexplained_pre_remote_ms":6384.17,"worker_unattributed_ms":null},"output_collection_ms":11.863,"pre_sampler_ms":4214.882,"restore_total_ms":1278.233,"sampler_ms":3728.495,"snapshot_callback_age_at_restore_ms":269397.188,"snapshot_callback_to_command_start_ms":264133.757,"submission_to_first_remote_event_ms":6438.381,"submit2entry_ms":6165.523,"t3b_to_t8_ms":9341.501,"vae_decode_ms":616.62,"wall_ms":15925.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.569ms unaccounted"]`
- Waterfall stages: `{"application_restore":1278.247257,"captured_timeline_gap":2.568540000002031,"clip_to_sampler_node":68.635,"first_node_to_clip":36.179,"local_preparation":430.33216,"modal_handle_submission":10.67714,"modal_scheduling":4852.854124,"output_persistence":225.748848,"post_sampling_transition":542.306313,"prompt_executor_cache_setup":469.503,"remote_local_return":15.00068,"remote_method_setup":54.251663,"remote_return_handoff":348.802546,"restore_to_method_entry":31.734119,"sampler_node_to_sampling":2219.360918,"sampling":5157.794507,"vae":616.619865}`

### `v2_2026-08-05_10-12-33` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4a93bcc404c6`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `db2834283cd14e00`
- Modal task: `ta-01KZ8PJ6KMXKKW1H288H3KFDJR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":99651.805,"command_to_response_ms":111214.7,"handle_lookup_ms":4.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":101645.711,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.998,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.099,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.764,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.764,"unexplained_pre_remote_ms":101595.612,"worker_unattributed_ms":null},"output_collection_ms":8.482,"pre_sampler_ms":4024.337,"restore_total_ms":1755.212,"sampler_ms":3705.943,"snapshot_callback_age_at_restore_ms":48888.736,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":101645.711,"submit2entry_ms":101153.064,"t3b_to_t8_ms":9059.511,"vae_decode_ms":639.03,"wall_ms":110861.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.081ms unaccounted"]`
- Waterfall stages: `{"application_restore":1756.039934,"captured_timeline_gap":1.0808369999867864,"clip_to_sampler_node":661.252,"first_node_to_clip":34.683,"local_preparation":348.764224,"modal_handle_submission":11.999676,"modal_scheduling":99291.041092,"output_persistence":217.314731,"post_sampling_transition":464.095476,"prompt_executor_cache_setup":193.629,"remote_local_return":12.999268,"remote_method_setup":50.119284,"remote_return_handoff":583.628867,"restore_to_method_entry":101.743131,"sampler_node_to_sampling":1643.936891,"sampling":5203.383985,"vae":639.030172}`

### `v2_2026-08-05_10-15-05` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9f9773d1ce3c`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `366f4833cc5846f8`
- Modal task: `ta-01KZ8PPWJ269GE4F9CY8HSCW8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `asia-south1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":102207.967,"command_to_response_ms":117899.7,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":106813.819,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":45.907,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.766,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.766,"unexplained_pre_remote_ms":106767.912,"worker_unattributed_ms":null},"output_collection_ms":9.707,"pre_sampler_ms":5296.097,"restore_total_ms":3711.782,"sampler_ms":3648.644,"snapshot_callback_age_at_restore_ms":50957.533,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":106813.819,"submit2entry_ms":105926.489,"t3b_to_t8_ms":10554.413,"vae_decode_ms":553.934,"wall_ms":117465.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.961ms unaccounted"]`
- Waterfall stages: `{"application_restore":3711.791493,"captured_timeline_gap":0.961278000017046,"clip_to_sampler_node":2746.039,"first_node_to_clip":29.812,"local_preparation":430.76608,"modal_handle_submission":10.00142,"modal_scheduling":101767.199476,"output_persistence":222.111111,"post_sampling_transition":827.991816,"prompt_executor_cache_setup":243.937,"remote_local_return":14.999256,"remote_method_setup":45.932424,"remote_return_handoff":922.02583,"restore_to_method_entry":444.488768,"sampler_node_to_sampling":914.625865,"sampling":5013.083867,"vae":553.932772}`

### `v2_2026-08-05_10-17-43` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-35205c5a5986`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `366f4833cc5846f8`
- Modal task: `ta-01KZ8PPWJ269GE4F9CY8HSCW8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5082.507,"command_to_response_ms":24527.7,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":8834.97,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":9.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":49.406,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.546,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.546,"unexplained_pre_remote_ms":8785.564,"worker_unattributed_ms":null},"output_collection_ms":9.332,"pre_sampler_ms":9800.501,"restore_total_ms":3899.715,"sampler_ms":3701.658,"snapshot_callback_age_at_restore_ms":111500.731,"snapshot_callback_to_command_start_ms":106434.186,"submission_to_first_remote_event_ms":8834.97,"submit2entry_ms":8568.393,"t3b_to_t8_ms":15154.828,"vae_decode_ms":557.045,"wall_ms":24104.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.991ms unaccounted"]`
- Waterfall stages: `{"application_restore":3899.724724,"captured_timeline_gap":0.9914239999961865,"clip_to_sampler_node":584.818,"first_node_to_clip":119.455,"local_preparation":418.54592,"modal_handle_submission":12.00198,"modal_scheduling":4651.959108,"output_persistence":210.99478,"post_sampling_transition":878.884298,"prompt_executor_cache_setup":343.955,"remote_local_return":13.999272,"remote_method_setup":49.432003,"remote_return_handoff":316.108847,"restore_to_method_entry":12.69476,"sampler_node_to_sampling":7374.119266,"sampling":5082.972645,"vae":557.045245}`

### `v2_2026-08-05_10-20-06` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8d655280116c`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `db2834283cd14e00`
- Modal task: `ta-01KZ8PJ6KMXKKW1H288H3KFDJR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4891.644,"command_to_response_ms":18234.0,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5998.169,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.997,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":60.642,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.995,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.995,"unexplained_pre_remote_ms":5937.528,"worker_unattributed_ms":null},"output_collection_ms":11.99,"pre_sampler_ms":6437.386,"restore_total_ms":1217.588,"sampler_ms":3688.57,"snapshot_callback_age_at_restore_ms":407476.837,"snapshot_callback_to_command_start_ms":402612.755,"submission_to_first_remote_event_ms":5998.169,"submit2entry_ms":5706.063,"t3b_to_t8_ms":11594.57,"vae_decode_ms":621.774,"wall_ms":17806.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 187.250ms unaccounted","reconciliation exceeds tolerance: 187.250ms > 91.170ms"]`
- Waterfall stages: `{"application_restore":1217.6031,"captured_timeline_gap":187.2503289999986,"clip_to_sampler_node":134.696,"first_node_to_clip":200.724,"local_preparation":423.995136,"modal_handle_submission":9.997164,"modal_scheduling":4457.651348,"output_persistence":225.510671,"post_sampling_transition":609.253891,"prompt_executor_cache_setup":246.033,"remote_local_return":11.999148,"remote_method_setup":60.669363,"remote_return_handoff":432.349479,"restore_to_method_entry":27.799393,"sampler_node_to_sampling":4254.254567,"sampling":5112.469859,"vae":621.7744}`

### `v2_2026-08-05_10-21-12` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-090c714da962`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `366f4833cc5846f8`
- Modal task: `ta-01KZ8PPWJ269GE4F9CY8HSCW8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":12416.48,"command_to_response_ms":25353.4,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":15496.699,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.997,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":39.691,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.297,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.297,"unexplained_pre_remote_ms":15457.008,"worker_unattributed_ms":null},"output_collection_ms":9.089,"pre_sampler_ms":4086.488,"restore_total_ms":3214.197,"sampler_ms":3691.742,"snapshot_callback_age_at_restore_ms":328094.047,"snapshot_callback_to_command_start_ms":315799.186,"submission_to_first_remote_event_ms":15496.699,"submit2entry_ms":15204.998,"t3b_to_t8_ms":9333.623,"vae_decode_ms":514.723,"wall_ms":24917.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.849ms unaccounted"]`
- Waterfall stages: `{"application_restore":3214.201515,"captured_timeline_gap":0.8494249999966996,"clip_to_sampler_node":891.83,"first_node_to_clip":263.987,"local_preparation":432.296896,"modal_handle_submission":9.997804,"modal_scheduling":11974.185236,"output_persistence":192.418677,"post_sampling_transition":842.956696,"prompt_executor_cache_setup":422.634,"remote_local_return":16.001316,"remote_method_setup":39.719991,"remote_return_handoff":321.669034,"restore_to_method_entry":13.607359,"sampler_node_to_sampling":1278.155938,"sampling":4924.194922,"vae":514.722607}`

### `v2_2026-08-05_10-22-16` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d666b1d6ed97`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `366f4833cc5846f8`
- Modal task: `ta-01KZ8PPWJ269GE4F9CY8HSCW8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6862.217,"command_to_response_ms":17915.9,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9479.942,"generator_create_ms":2.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":34.004,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.802,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.802,"unexplained_pre_remote_ms":9445.937,"worker_unattributed_ms":null},"output_collection_ms":9.223,"pre_sampler_ms":2564.179,"restore_total_ms":2751.329,"sampler_ms":3729.909,"snapshot_callback_age_at_restore_ms":386293.15,"snapshot_callback_to_command_start_ms":379435.186,"submission_to_first_remote_event_ms":9479.942,"submit2entry_ms":9194.586,"t3b_to_t8_ms":7910.757,"vae_decode_ms":514.813,"wall_ms":17484.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.918ms unaccounted"]`
- Waterfall stages: `{"application_restore":2751.337806,"captured_timeline_gap":0.9183840000005148,"clip_to_sampler_node":73.008,"first_node_to_clip":81.614,"local_preparation":426.802112,"modal_handle_submission":10.001588,"modal_scheduling":6425.413452,"output_persistence":195.489033,"post_sampling_transition":900.792354,"prompt_executor_cache_setup":213.149,"remote_local_return":17.001784,"remote_method_setup":34.025194,"remote_return_handoff":326.433822,"restore_to_method_entry":15.802438,"sampler_node_to_sampling":972.959603,"sampling":4956.371375,"vae":514.811639}`

### `v2_2026-08-05_10-24-10` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5559e829031c`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `855c7a94cfa94cb6`
- Modal task: `ta-01KZ8Q7FPA4AHJJYBRNH7XSYRR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":93329.053,"command_to_response_ms":104649.0,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":94960.311,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":58.993,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.374,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.374,"unexplained_pre_remote_ms":94901.318,"worker_unattributed_ms":null},"output_collection_ms":10.637,"pre_sampler_ms":4054.112,"restore_total_ms":1216.121,"sampler_ms":3705.578,"snapshot_callback_age_at_restore_ms":41150.995,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":94960.311,"submit2entry_ms":94453.126,"t3b_to_t8_ms":9178.11,"vae_decode_ms":671.293,"wall_ms":104299.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.292ms unaccounted"]`
- Waterfall stages: `{"application_restore":1216.129626,"captured_timeline_gap":2.2919659999461146,"clip_to_sampler_node":603.263,"first_node_to_clip":1.922,"local_preparation":345.37376,"modal_handle_submission":10.00104,"modal_scheduling":92973.678704,"output_persistence":238.49598,"post_sampling_transition":498.105538,"prompt_executor_cache_setup":225.229,"remote_local_return":12.996808,"remote_method_setup":59.016807,"remote_return_handoff":595.690478,"restore_to_method_entry":260.3056,"sampler_node_to_sampling":1673.489044,"sampling":5261.766923,"vae":671.293134}`

### `v2_2026-08-05_10-26-34` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-80fc7a8763f1`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `855c7a94cfa94cb6`
- Modal task: `ta-01KZ8Q7FPA4AHJJYBRNH7XSYRR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7901.715,"command_to_response_ms":18907.1,"handle_lookup_ms":3.254,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9488.365,"generator_create_ms":3.254,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":6.454,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":55.079,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.627,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.627,"unexplained_pre_remote_ms":9433.286,"worker_unattributed_ms":null},"output_collection_ms":10.401,"pre_sampler_ms":3628.189,"restore_total_ms":1395.172,"sampler_ms":3699.547,"snapshot_callback_age_at_restore_ms":99877.17,"snapshot_callback_to_command_start_ms":92016.606,"submission_to_first_remote_event_ms":9488.364,"submit2entry_ms":9163.147,"t3b_to_t8_ms":8732.74,"vae_decode_ms":655.497,"wall_ms":18516.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.190ms unaccounted"]`
- Waterfall stages: `{"application_restore":1395.180808,"captured_timeline_gap":1.1902249999948253,"clip_to_sampler_node":182.884,"first_node_to_clip":2.382,"local_preparation":386.6272,"modal_handle_submission":9.7081,"modal_scheduling":7505.379516,"output_persistence":243.209384,"post_sampling_transition":495.600364,"prompt_executor_cache_setup":226.653,"remote_local_return":12.99912,"remote_method_setup":55.114811,"remote_return_handoff":552.224756,"restore_to_method_entry":259.321033,"sampler_node_to_sampling":1677.851462,"sampling":5245.296033,"vae":655.496908}`

### `v2_2026-08-05_10-27-34` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-f36f9bded405`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `855c7a94cfa94cb6`
- Modal task: `ta-01KZ8Q7FPA4AHJJYBRNH7XSYRR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":19121.97,"command_to_response_ms":42846.4,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":20195.631,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":50.637,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.012,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.012,"unexplained_pre_remote_ms":20144.994,"worker_unattributed_ms":null},"output_collection_ms":11.171,"pre_sampler_ms":16990.855,"restore_total_ms":1153.079,"sampler_ms":3723.086,"snapshot_callback_age_at_restore_ms":170390.689,"snapshot_callback_to_command_start_ms":151270.606,"submission_to_first_remote_event_ms":20195.631,"submit2entry_ms":19909.718,"t3b_to_t8_ms":22120.759,"vae_decode_ms":603.331,"wall_ms":42457.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.024ms unaccounted"]`
- Waterfall stages: `{"application_restore":1153.087448,"captured_timeline_gap":1.0243229999978212,"clip_to_sampler_node":2663.56,"first_node_to_clip":1112.28,"local_preparation":385.012224,"modal_handle_submission":9.000676,"modal_scheduling":18727.95702,"output_persistence":231.940437,"post_sampling_transition":561.991177,"prompt_executor_cache_setup":421.886,"remote_local_return":12.999812,"remote_method_setup":50.668191,"remote_return_handoff":363.472378,"restore_to_method_entry":25.664885,"sampler_node_to_sampling":11407.217227,"sampling":5115.262869,"vae":603.331045}`

### `v2_2026-08-05_10-28-56` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-886cae9f0c76`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `855c7a94cfa94cb6`
- Modal task: `ta-01KZ8Q7FPA4AHJJYBRNH7XSYRR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5107.53,"command_to_response_ms":32825.6,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7365.624,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":52.336,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.982,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.982,"unexplained_pre_remote_ms":7313.289,"worker_unattributed_ms":null},"output_collection_ms":10.418,"pre_sampler_ms":19890.639,"restore_total_ms":2215.228,"sampler_ms":3715.227,"snapshot_callback_age_at_restore_ms":239049.856,"snapshot_callback_to_command_start_ms":233944.606,"submission_to_first_remote_event_ms":7365.624,"submit2entry_ms":7036.884,"t3b_to_t8_ms":24777.531,"vae_decode_ms":559.954,"wall_ms":32440.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 975.961ms unaccounted","reconciliation exceeds tolerance: 975.961ms > 164.128ms"]`
- Waterfall stages: `{"application_restore":2215.23998,"captured_timeline_gap":975.9612089999973,"clip_to_sampler_node":4000.599,"first_node_to_clip":2.509,"local_preparation":380.981632,"modal_handle_submission":9.000668,"modal_scheduling":4717.548068,"output_persistence":203.31332,"post_sampling_transition":397.837087,"prompt_executor_cache_setup":214.992,"remote_local_return":11.998828,"remote_method_setup":52.35495,"remote_return_handoff":560.659443,"restore_to_method_entry":102.089318,"sampler_node_to_sampling":13381.940406,"sampling":5038.620628,"vae":559.954591}`

### `v2_2026-08-05_10-31-02` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-4560db134085`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":117461.007,"command_to_response_ms":128395.2,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":118221.965,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":60.27,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.027,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.027,"unexplained_pre_remote_ms":118161.694,"worker_unattributed_ms":null},"output_collection_ms":10.603,"pre_sampler_ms":4320.79,"restore_total_ms":752.587,"sampler_ms":3720.277,"snapshot_callback_age_at_restore_ms":55387.674,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":118221.965,"submit2entry_ms":117905.054,"t3b_to_t8_ms":9668.627,"vae_decode_ms":727.327,"wall_ms":128066.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.173ms unaccounted"]`
- Waterfall stages: `{"application_restore":752.594272,"captured_timeline_gap":1.1726740000012796,"clip_to_sampler_node":64.374,"first_node_to_clip":47.037,"local_preparation":325.026752,"modal_handle_submission":9.000548,"modal_scheduling":117126.97974,"output_persistence":256.083582,"post_sampling_transition":632.99125,"prompt_executor_cache_setup":505.113,"remote_local_return":13.999104,"remote_method_setup":60.287607,"remote_return_handoff":416.976193,"restore_to_method_entry":23.471183,"sampler_node_to_sampling":2057.779023,"sampling":5374.949226,"vae":727.32715}`

### `v2_2026-08-05_10-33-49` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_10-35-45` / run `none`

- Classification: **INCOMPLETE_OR_FAILED_NO_SUMMARY_RUN**
- Files: 
- No parsed run record was available. This directory is retained in the inventory as incomplete/failed.

### `v2_2026-08-05_10-38-06` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1d0d5a8c9bbd`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5706.152,"command_to_response_ms":35762.9,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10690.111,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":62.986,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.603,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.603,"unexplained_pre_remote_ms":10627.125,"worker_unattributed_ms":null},"output_collection_ms":10.967,"pre_sampler_ms":19411.206,"restore_total_ms":4952.155,"sampler_ms":3687.441,"snapshot_callback_age_at_restore_ms":367714.554,"snapshot_callback_to_command_start_ms":362010.204,"submission_to_first_remote_event_ms":10690.111,"submit2entry_ms":10351.375,"t3b_to_t8_ms":24324.176,"vae_decode_ms":589.185,"wall_ms":35355.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 484.830ms unaccounted","reconciliation exceeds tolerance: 484.830ms > 178.814ms"]`
- Waterfall stages: `{"application_restore":4952.163982,"captured_timeline_gap":484.8300820000004,"clip_to_sampler_node":916.751,"first_node_to_clip":39.739,"local_preparation":402.60288,"modal_handle_submission":11.00112,"modal_scheduling":5292.547808,"output_persistence":216.444122,"post_sampling_transition":411.466284,"prompt_executor_cache_setup":221.847,"remote_local_return":11.999888,"remote_method_setup":63.037023,"remote_return_handoff":614.398185,"restore_to_method_entry":103.653934,"sampler_node_to_sampling":16413.43769,"sampling":5017.764293,"vae":589.185597}`

### `v2_2026-08-05_10-39-22` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-79c415e1ea44`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5230.841,"command_to_response_ms":20159.6,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":16.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6915.69,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":444.416,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.624,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.624,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.028,"pre_sampler_ms":7712.451,"restore_total_ms":1754.335,"sampler_ms":3704.192,"snapshot_callback_age_at_restore_ms":442862.375,"snapshot_callback_to_command_start_ms":437636.204,"submission_to_first_remote_event_ms":6915.69,"submit2entry_ms":6617.499,"t3b_to_t8_ms":12696.733,"vae_decode_ms":598.625,"wall_ms":19754.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 386.029ms unaccounted","reconciliation exceeds tolerance: 386.029ms > 100.798ms"]`
- Waterfall stages: `{"application_restore":1754.348952,"captured_timeline_gap":386.0286030000025,"clip_to_sampler_node":241.198,"first_node_to_clip":251.944,"local_preparation":401.62432,"modal_handle_submission":9.00108,"modal_scheduling":4820.215176,"output_persistence":219.962763,"post_sampling_transition":451.650812,"prompt_executor_cache_setup":243.721,"remote_local_return":12.999412,"remote_method_setup":444.58942,"remote_return_handoff":363.636362,"restore_to_method_entry":39.926277,"sampler_node_to_sampling":4820.497249,"sampling":5099.628706,"vae":598.62518}`

### `v2_2026-08-05_10-40-22` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b821bf2a7b1d`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5101.02,"command_to_response_ms":19972.2,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6628.537,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":128.707,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.282,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.282,"unexplained_pre_remote_ms":6499.83,"worker_unattributed_ms":null},"output_collection_ms":9.9,"pre_sampler_ms":7458.495,"restore_total_ms":1425.26,"sampler_ms":3704.09,"snapshot_callback_age_at_restore_ms":503068.95,"snapshot_callback_to_command_start_ms":497973.204,"submission_to_first_remote_event_ms":6628.537,"submit2entry_ms":6264.113,"t3b_to_t8_ms":12335.751,"vae_decode_ms":556.605,"wall_ms":19587.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.847ms unaccounted"]`
- Waterfall stages: `{"application_restore":1425.269547,"captured_timeline_gap":0.8469789999981003,"clip_to_sampler_node":526.517,"first_node_to_clip":92.773,"local_preparation":381.281984,"modal_handle_submission":9.001316,"modal_scheduling":4710.736796,"output_persistence":200.146116,"post_sampling_transition":407.457851,"prompt_executor_cache_setup":431.341,"remote_local_return":11.99892,"remote_method_setup":128.724341,"remote_return_handoff":850.257413,"restore_to_method_entry":125.083177,"sampler_node_to_sampling":5089.121539,"sampling":5025.033097,"vae":556.605444}`

### `v2_2026-08-05_10-41-20` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-ae09393f9813`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `80ae429b85ed44f3`
- Modal task: `ta-01KZ8QWPHZQZ1TA2V7QJT4SMTR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":15832.298,"command_to_response_ms":27809.4,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":18640.907,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":44.82,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.695,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.695,"unexplained_pre_remote_ms":18596.086,"worker_unattributed_ms":null},"output_collection_ms":9.436,"pre_sampler_ms":3448.421,"restore_total_ms":2850.644,"sampler_ms":3697.873,"snapshot_callback_age_at_restore_ms":283270.303,"snapshot_callback_to_command_start_ms":267539.526,"submission_to_first_remote_event_ms":18640.907,"submit2entry_ms":18352.622,"t3b_to_t8_ms":8673.674,"vae_decode_ms":504.274,"wall_ms":27423.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.848ms unaccounted"]`
- Waterfall stages: `{"application_restore":2850.648837,"captured_timeline_gap":0.8479019999940647,"clip_to_sampler_node":88.062,"first_node_to_clip":60.184,"local_preparation":381.69504,"modal_handle_submission":10.99906,"modal_scheduling":15439.603692,"output_persistence":196.585618,"post_sampling_transition":820.986407,"prompt_executor_cache_setup":926.407,"remote_local_return":16.000008,"remote_method_setup":44.903714,"remote_return_handoff":334.582941,"restore_to_method_entry":59.365409,"sampler_node_to_sampling":1146.98594,"sampling":4927.295266,"vae":504.274174}`

### `v2_2026-08-05_10-42-44` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-14543d655318`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4259.68,"command_to_response_ms":15511.1,"handle_lookup_ms":1.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5168.701,"generator_create_ms":1.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":184.396,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.56,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.56,"unexplained_pre_remote_ms":4984.305,"worker_unattributed_ms":null},"output_collection_ms":10.447,"pre_sampler_ms":4491.377,"restore_total_ms":922.411,"sampler_ms":3742.18,"snapshot_callback_age_at_restore_ms":644575.465,"snapshot_callback_to_command_start_ms":640326.204,"submission_to_first_remote_event_ms":5168.701,"submit2entry_ms":4828.387,"t3b_to_t8_ms":9745.568,"vae_decode_ms":603.008,"wall_ms":15121.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.711ms unaccounted"]`
- Waterfall stages: `{"application_restore":922.47985,"captured_timeline_gap":1.7106799999965006,"clip_to_sampler_node":76.077,"first_node_to_clip":47.439,"local_preparation":386.559616,"modal_handle_submission":9.001684,"modal_scheduling":3864.118316,"output_persistence":230.771564,"post_sampling_transition":666.284143,"prompt_executor_cache_setup":814.93,"remote_local_return":12.998452,"remote_method_setup":184.464962,"remote_return_handoff":378.880749,"restore_to_method_entry":39.720165,"sampler_node_to_sampling":2135.346576,"sampling":5137.352681,"vae":603.008114}`

### `v2_2026-08-05_10-43-39` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d5bdcd59f8d4`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `80ae429b85ed44f3`
- Modal task: `ta-01KZ8QWPHZQZ1TA2V7QJT4SMTR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":36234.173,"command_to_response_ms":47299.6,"handle_lookup_ms":3.004,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":37534.929,"generator_create_ms":3.004,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.273,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":39.858,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.036,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.036,"unexplained_pre_remote_ms":37495.071,"worker_unattributed_ms":null},"output_collection_ms":8.874,"pre_sampler_ms":3989.248,"restore_total_ms":1406.362,"sampler_ms":3722.306,"snapshot_callback_age_at_restore_ms":441842.921,"snapshot_callback_to_command_start_ms":405917.526,"submission_to_first_remote_event_ms":37534.929,"submit2entry_ms":37245.021,"t3b_to_t8_ms":9258.097,"vae_decode_ms":499.69,"wall_ms":46894.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.954ms unaccounted"]`
- Waterfall stages: `{"application_restore":1406.368685,"captured_timeline_gap":0.9536470000093686,"clip_to_sampler_node":795.422,"first_node_to_clip":250.453,"local_preparation":401.035968,"modal_handle_submission":10.277532,"modal_scheduling":35822.859876,"output_persistence":186.711363,"post_sampling_transition":854.332011,"prompt_executor_cache_setup":573.681,"remote_local_return":12.99972,"remote_method_setup":39.882415,"remote_return_handoff":336.810049,"restore_to_method_entry":12.780476,"sampler_node_to_sampling":1147.876588,"sampling":4947.453027,"vae":499.690163}`

### `v2_2026-08-05_10-45-05` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-307ee3598b1e`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `1b717d136f944734`
- Modal task: `ta-01KZ8QM1J4XZDF9AHJQHG094YR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5919.566,"command_to_response_ms":20615.2,"handle_lookup_ms":2.182,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6673.752,"generator_create_ms":2.182,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":83.353,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.665,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.665,"unexplained_pre_remote_ms":6590.399,"worker_unattributed_ms":null},"output_collection_ms":11.291,"pre_sampler_ms":8240.449,"restore_total_ms":804.462,"sampler_ms":3732.099,"snapshot_callback_age_at_restore_ms":786698.782,"snapshot_callback_to_command_start_ms":780781.204,"submission_to_first_remote_event_ms":6673.752,"submit2entry_ms":6369.422,"t3b_to_t8_ms":13414.682,"vae_decode_ms":613.428,"wall_ms":20234.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.425ms unaccounted"]`
- Waterfall stages: `{"application_restore":804.477929,"captured_timeline_gap":1.4248920000027283,"clip_to_sampler_node":1831.159,"first_node_to_clip":102.885,"local_preparation":376.66528,"modal_handle_submission":9.18182,"modal_scheduling":5533.71866,"output_persistence":236.112412,"post_sampling_transition":583.122871,"prompt_executor_cache_setup":419.32,"remote_local_return":11.999092,"remote_method_setup":83.377943,"remote_return_handoff":382.775553,"restore_to_method_entry":29.032011,"sampler_node_to_sampling":4474.178893,"sampling":5122.334361,"vae":613.428075}`

### `v2_2026-08-05_10-46-35` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-67fcb12dee62`
- Policy/order: `T3` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `5fcccfbfafc0f0f573ef9861`
- Container session: `80ae429b85ed44f3`
- Modal task: `ta-01KZ8QWPHZQZ1TA2V7QJT4SMTR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-j69Q9kH2yl0WI4DxxbujvB`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4353.164,"command_to_response_ms":27387.6,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7401.562,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":43.334,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.622,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.622,"unexplained_pre_remote_ms":7358.228,"worker_unattributed_ms":null},"output_collection_ms":9.958,"pre_sampler_ms":14245.081,"restore_total_ms":3165.838,"sampler_ms":3709.345,"snapshot_callback_age_at_restore_ms":586474.256,"snapshot_callback_to_command_start_ms":582122.526,"submission_to_first_remote_event_ms":7401.562,"submit2entry_ms":7107.797,"t3b_to_t8_ms":19458.873,"vae_decode_ms":533.216,"wall_ms":26963.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.014ms unaccounted"]`
- Waterfall stages: `{"application_restore":3165.844503,"captured_timeline_gap":1.013557000002038,"clip_to_sampler_node":261.489,"first_node_to_clip":1355.82,"local_preparation":419.622272,"modal_handle_submission":9.999528,"modal_scheduling":3923.542104,"output_persistence":197.498179,"post_sampling_transition":768.008811,"prompt_executor_cache_setup":491.903,"remote_local_return":12.997608,"remote_method_setup":43.358408,"remote_return_handoff":340.350249,"restore_to_method_entry":15.405549,"sampler_node_to_sampling":10895.709249,"sampling":4951.832969,"vae":533.216022}`

### `v2_2026-08-05_10-49-48` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-10593c015e9f`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":101479.822,"command_to_response_ms":113316.6,"handle_lookup_ms":4.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":102722.494,"generator_create_ms":3.003,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":89.634,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.068,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.068,"unexplained_pre_remote_ms":102632.859,"worker_unattributed_ms":null},"output_collection_ms":11.656,"pre_sampler_ms":4592.502,"restore_total_ms":1225.697,"sampler_ms":3729.349,"snapshot_callback_age_at_restore_ms":40892.53,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":102722.494,"submit2entry_ms":102392.446,"t3b_to_t8_ms":10088.045,"vae_decode_ms":736.985,"wall_ms":112980.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.365ms unaccounted"]`
- Waterfall stages: `{"application_restore":1225.706923,"captured_timeline_gap":2.364549999954761,"clip_to_sampler_node":92.964,"first_node_to_clip":94.652,"local_preparation":332.068288,"modal_handle_submission":11.003412,"modal_scheduling":101136.750572,"output_persistence":269.646012,"post_sampling_transition":747.631703,"prompt_executor_cache_setup":559.71,"remote_local_return":11.998216,"remote_method_setup":89.685275,"remote_return_handoff":429.437768,"restore_to_method_entry":25.975523,"sampler_node_to_sampling":2195.55756,"sampling":5354.465666,"vae":736.985348}`

### `v2_2026-08-05_10-52-22` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-bd7ece522e82`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5486.502,"command_to_response_ms":29931.6,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7830.818,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":61.018,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.773,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.773,"unexplained_pre_remote_ms":7769.799,"worker_unattributed_ms":null},"output_collection_ms":11.372,"pre_sampler_ms":16131.069,"restore_total_ms":2404.867,"sampler_ms":3737.118,"snapshot_callback_age_at_restore_ms":98321.516,"snapshot_callback_to_command_start_ms":92861.068,"submission_to_first_remote_event_ms":7830.818,"submit2entry_ms":7521.446,"t3b_to_t8_ms":21538.729,"vae_decode_ms":713.279,"wall_ms":29539.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.719ms unaccounted"]`
- Waterfall stages: `{"application_restore":2404.874726,"captured_timeline_gap":2.718780000006518,"clip_to_sampler_node":997.449,"first_node_to_clip":1773.121,"local_preparation":387.772992,"modal_handle_submission":10.000908,"modal_scheduling":5088.728308,"output_persistence":273.089517,"post_sampling_transition":672.09785,"prompt_executor_cache_setup":866.074,"remote_local_return":20.000148,"remote_method_setup":61.051752,"remote_return_handoff":398.364339,"restore_to_method_entry":24.835342,"sampler_node_to_sampling":10852.319212,"sampling":5385.778925,"vae":713.278849}`

### `v2_2026-08-05_10-53-31` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e4d5d433a7e7`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4560.298,"command_to_response_ms":15578.6,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5969.657,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":91.368,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.457,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.457,"unexplained_pre_remote_ms":5878.289,"worker_unattributed_ms":null},"output_collection_ms":10.798,"pre_sampler_ms":3923.571,"restore_total_ms":1444.039,"sampler_ms":3726.696,"snapshot_callback_age_at_restore_ms":166055.178,"snapshot_callback_to_command_start_ms":161511.068,"submission_to_first_remote_event_ms":5969.657,"submit2entry_ms":5639.193,"t3b_to_t8_ms":9054.325,"vae_decode_ms":614.05,"wall_ms":15182.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.878ms unaccounted"]`
- Waterfall stages: `{"application_restore":1444.048439,"captured_timeline_gap":2.877684999999474,"clip_to_sampler_node":62.735,"first_node_to_clip":49.248,"local_preparation":392.457408,"modal_handle_submission":10.000792,"modal_scheduling":4157.83972,"output_persistence":227.576274,"post_sampling_transition":550.58673,"prompt_executor_cache_setup":392.193,"remote_local_return":12.999944,"remote_method_setup":91.507748,"remote_return_handoff":387.106989,"restore_to_method_entry":35.295723,"sampler_node_to_sampling":2019.205541,"sampling":5128.91174,"vae":614.050611}`

### `v2_2026-08-05_10-54-25` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-3c9910b069bd`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5011.507,"command_to_response_ms":15559.7,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6136.917,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":53.046,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.277,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.277,"unexplained_pre_remote_ms":6083.871,"worker_unattributed_ms":null},"output_collection_ms":9.842,"pre_sampler_ms":3806.181,"restore_total_ms":1178.653,"sampler_ms":3723.421,"snapshot_callback_age_at_restore_ms":220327.464,"snapshot_callback_to_command_start_ms":215404.068,"submission_to_first_remote_event_ms":6136.917,"submit2entry_ms":5828.388,"t3b_to_t8_ms":8874.82,"vae_decode_ms":585.101,"wall_ms":15156.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.222ms unaccounted"]`
- Waterfall stages: `{"application_restore":1178.664838,"captured_timeline_gap":2.222300000003088,"clip_to_sampler_node":67.857,"first_node_to_clip":46.452,"local_preparation":400.277376,"modal_handle_submission":10.001324,"modal_scheduling":4601.228628,"output_persistence":224.749751,"post_sampling_transition":521.062181,"prompt_executor_cache_setup":359.433,"remote_local_return":12.999972,"remote_method_setup":53.084886,"remote_return_handoff":385.31892,"restore_to_method_entry":45.478144,"sampler_node_to_sampling":1937.350351,"sampling":5128.372844,"vae":585.100757}`

### `v2_2026-08-05_10-55-18` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-3380c3872b30`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `4d721a3ad8d14963`
- Modal task: `ta-01KZ8S0FNYJQC66XDCKQ9632ER`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":74669.363,"command_to_response_ms":86801.2,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":78345.457,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":44.936,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.333,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.333,"unexplained_pre_remote_ms":78300.521,"worker_unattributed_ms":null},"output_collection_ms":9.332,"pre_sampler_ms":2759.134,"restore_total_ms":3726.937,"sampler_ms":3690.151,"snapshot_callback_age_at_restore_ms":35939.303,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":78345.457,"submit2entry_ms":78030.683,"t3b_to_t8_ms":7983.757,"vae_decode_ms":507.53,"wall_ms":86421.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.891ms unaccounted"]`
- Waterfall stages: `{"application_restore":3726.94331,"captured_timeline_gap":0.8914809999987483,"clip_to_sampler_node":83.717,"first_node_to_clip":77.381,"local_preparation":376.332608,"modal_handle_submission":10.000792,"modal_scheduling":74283.029608,"output_persistence":197.595589,"post_sampling_transition":823.580005,"prompt_executor_cache_setup":425.63,"remote_local_return":12.998408,"remote_method_setup":44.961787,"remote_return_handoff":347.329808,"restore_to_method_entry":17.702517,"sampler_node_to_sampling":919.217688,"sampling":4946.316564,"vae":507.530043}`

### `v2_2026-08-05_10-57-26` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d4b3d243014b`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5123.333,"command_to_response_ms":15905.3,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6107.423,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":102.893,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.613,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.613,"unexplained_pre_remote_ms":6004.529,"worker_unattributed_ms":null},"output_collection_ms":11.354,"pre_sampler_ms":4114.962,"restore_total_ms":1001.327,"sampler_ms":3731.261,"snapshot_callback_age_at_restore_ms":402386.425,"snapshot_callback_to_command_start_ms":397289.068,"submission_to_first_remote_event_ms":6107.423,"submit2entry_ms":5782.639,"t3b_to_t8_ms":9231.986,"vae_decode_ms":614.441,"wall_ms":15514.0}`
- Waterfall warnings: `[]`
- Waterfall stages: `{"application_restore":1001.413929,"clip_to_sampler_node":59.19,"first_node_to_clip":46.832,"local_preparation":387.613248,"modal_handle_submission":9.999452,"modal_scheduling":4725.72074,"output_persistence":224.801549,"post_sampling_transition":535.732443,"prompt_executor_cache_setup":584.875,"remote_local_return":11.998224,"remote_method_setup":105.569716,"remote_return_handoff":385.278542,"restore_to_method_entry":52.457394,"sampler_node_to_sampling":2035.894098,"sampling":5125.179283,"vae":614.440717}`

### `v2_2026-08-05_10-58-23` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-776e1b6f25fe`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7a4753e1082be2c398cbd109`
- Container session: `b681737048874f36`
- Modal task: `ta-01KZ8RPDX3VKBFGHBEZMMMRPYR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-sC6OnZ3hBAEU2wYYQsI2nj`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5141.279,"command_to_response_ms":15898.6,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5977.257,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":155.946,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.4,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.4,"unexplained_pre_remote_ms":5821.312,"worker_unattributed_ms":null},"output_collection_ms":11.43,"pre_sampler_ms":4188.255,"restore_total_ms":852.389,"sampler_ms":3721.31,"snapshot_callback_age_at_restore_ms":458924.603,"snapshot_callback_to_command_start_ms":453796.068,"submission_to_first_remote_event_ms":5977.257,"submit2entry_ms":5646.905,"t3b_to_t8_ms":9311.789,"vae_decode_ms":604.242,"wall_ms":15504.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.194ms unaccounted"]`
- Waterfall stages: `{"application_restore":852.410938,"captured_timeline_gap":2.1942870000020775,"clip_to_sampler_node":64.451,"first_node_to_clip":55.259,"local_preparation":391.40032,"modal_handle_submission":9.00158,"modal_scheduling":4740.87746,"output_persistence":232.823035,"post_sampling_transition":553.108668,"prompt_executor_cache_setup":618.656,"remote_local_return":10.999208,"remote_method_setup":156.01904,"remote_return_handoff":385.52401,"restore_to_method_entry":50.606322,"sampler_node_to_sampling":2033.123824,"sampling":5137.915538,"vae":604.242378}`

### `v2_2026-08-05_11-00-30` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-283e8dbc9fe8`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `afc7bd9fb54b432b`
- Modal task: `ta-01KZ8SAW2K0RGMQX5R6Q9NMQ2R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":122769.651,"command_to_response_ms":133855.5,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":123707.36,"generator_create_ms":1.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":58.984,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.897,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.897,"unexplained_pre_remote_ms":123648.376,"worker_unattributed_ms":null},"output_collection_ms":11.468,"pre_sampler_ms":4328.748,"restore_total_ms":918.619,"sampler_ms":3710.399,"snapshot_callback_age_at_restore_ms":37931.997,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":123707.36,"submit2entry_ms":123361.573,"t3b_to_t8_ms":9634.869,"vae_decode_ms":698.26,"wall_ms":133507.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.952ms unaccounted"]`
- Waterfall stages: `{"application_restore":918.638606,"captured_timeline_gap":0.9517230000055861,"clip_to_sampler_node":72.207,"first_node_to_clip":44.07,"local_preparation":343.897408,"modal_handle_submission":10.001192,"modal_scheduling":122415.752152,"output_persistence":257.678931,"post_sampling_transition":630.384422,"prompt_executor_cache_setup":633.142,"remote_local_return":12.998908,"remote_method_setup":59.001894,"remote_return_handoff":438.01012,"restore_to_method_entry":24.161952,"sampler_node_to_sampling":1967.799483,"sampling":5328.506288,"vae":698.260129}`

### `v2_2026-08-05_11-03-22` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-74059173f159`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `afc7bd9fb54b432b`
- Modal task: `ta-01KZ8SAW2K0RGMQX5R6Q9NMQ2R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5495.779,"command_to_response_ms":16688.6,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6607.124,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":61.069,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.426,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.426,"unexplained_pre_remote_ms":6546.055,"worker_unattributed_ms":null},"output_collection_ms":10.707,"pre_sampler_ms":4195.26,"restore_total_ms":1156.764,"sampler_ms":3719.844,"snapshot_callback_age_at_restore_ms":92557.363,"snapshot_callback_to_command_start_ms":87116.928,"submission_to_first_remote_event_ms":6607.124,"submit2entry_ms":6290.295,"t3b_to_t8_ms":9547.461,"vae_decode_ms":712.305,"wall_ms":16306.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.672ms unaccounted"]`
- Waterfall stages: `{"application_restore":1156.776265,"captured_timeline_gap":2.672097999999096,"clip_to_sampler_node":71.937,"first_node_to_clip":48.19,"local_preparation":379.4256,"modal_handle_submission":9.0003,"modal_scheduling":5107.353492,"output_persistence":278.737024,"post_sampling_transition":628.624578,"prompt_executor_cache_setup":395.91,"remote_local_return":15.99872,"remote_method_setup":61.094221,"remote_return_handoff":390.420236,"restore_to_method_entry":23.154519,"sampler_node_to_sampling":2015.078382,"sampling":5391.917286,"vae":712.305799}`

### `v2_2026-08-05_11-04-18` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-10f1ec4f241c`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `afc7bd9fb54b432b`
- Modal task: `ta-01KZ8SAW2K0RGMQX5R6Q9NMQ2R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5199.149,"command_to_response_ms":35089.0,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":12446.659,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":53.477,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.953,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.953,"unexplained_pre_remote_ms":12393.182,"worker_unattributed_ms":null},"output_collection_ms":9.802,"pre_sampler_ms":17076.765,"restore_total_ms":7011.923,"sampler_ms":3712.802,"snapshot_callback_age_at_restore_ms":147811.2,"snapshot_callback_to_command_start_ms":142613.928,"submission_to_first_remote_event_ms":12446.659,"submit2entry_ms":12070.037,"t3b_to_t8_ms":21963.243,"vae_decode_ms":565.543,"wall_ms":34697.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.815ms unaccounted"]`
- Waterfall stages: `{"application_restore":7011.933056,"captured_timeline_gap":0.8148529999962193,"clip_to_sampler_node":7084.547,"first_node_to_clip":30.42,"local_preparation":386.953216,"modal_handle_submission":10.000484,"modal_scheduling":4802.194844,"output_persistence":201.103261,"post_sampling_transition":397.713193,"prompt_executor_cache_setup":220.483,"remote_local_return":18.006708,"remote_method_setup":53.498446,"remote_return_handoff":591.973011,"restore_to_method_entry":252.891447,"sampler_node_to_sampling":8449.804743,"sampling":5011.084206,"vae":565.54314}`

### `v2_2026-08-05_11-05-31` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-568de724b986`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `afc7bd9fb54b432b`
- Modal task: `ta-01KZ8SAW2K0RGMQX5R6Q9NMQ2R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4879.489,"command_to_response_ms":15598.1,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5943.021,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":107.83,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.581,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.581,"unexplained_pre_remote_ms":5835.191,"worker_unattributed_ms":null},"output_collection_ms":10.44,"pre_sampler_ms":3937.104,"restore_total_ms":1083.847,"sampler_ms":3725.267,"snapshot_callback_age_at_restore_ms":220848.592,"snapshot_callback_to_command_start_ms":216026.928,"submission_to_first_remote_event_ms":5943.02,"submit2entry_ms":5611.638,"t3b_to_t8_ms":9087.415,"vae_decode_ms":613.484,"wall_ms":15213.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.344ms unaccounted"]`
- Waterfall stages: `{"application_restore":1083.895538,"captured_timeline_gap":1.3435830000016722,"clip_to_sampler_node":64.897,"first_node_to_clip":38.593,"local_preparation":380.581312,"modal_handle_submission":9.000388,"modal_scheduling":4489.907516,"output_persistence":234.146594,"post_sampling_transition":566.893395,"prompt_executor_cache_setup":491.881,"remote_local_return":14.0021,"remote_method_setup":107.872628,"remote_return_handoff":400.559534,"restore_to_method_entry":34.763568,"sampler_node_to_sampling":1940.954249,"sampling":5125.366876,"vae":613.484119}`

### `v2_2026-08-05_11-06-25` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-171c06c2dbac`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `3845417547004973`
- Modal task: `ta-01KZ8SMV1THBC83VDS7GXN7HER`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":115883.108,"command_to_response_ms":124628.3,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":116436.354,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":38.041,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.243,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.243,"unexplained_pre_remote_ms":116398.313,"worker_unattributed_ms":null},"output_collection_ms":9.228,"pre_sampler_ms":2505.204,"restore_total_ms":615.842,"sampler_ms":3667.601,"snapshot_callback_age_at_restore_ms":39670.759,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":116436.354,"submit2entry_ms":116115.526,"t3b_to_t8_ms":7701.935,"vae_decode_ms":502.939,"wall_ms":124228.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.013ms unaccounted"]`
- Waterfall stages: `{"application_restore":615.859128,"captured_timeline_gap":1.0133219999988796,"clip_to_sampler_node":115.449,"first_node_to_clip":124.525,"local_preparation":395.242624,"modal_handle_submission":10.000576,"modal_scheduling":115477.865024,"output_persistence":201.382727,"post_sampling_transition":819.382524,"prompt_executor_cache_setup":174.111,"remote_local_return":14.00058,"remote_method_setup":38.103435,"remote_return_handoff":358.114467,"restore_to_method_entry":18.784508,"sampler_node_to_sampling":863.99687,"sampling":4897.573554,"vae":502.939341}`

### `v2_2026-08-05_11-09-10` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c2caedbfe9c8`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `3845417547004973`
- Modal task: `ta-01KZ8SMV1THBC83VDS7GXN7HER`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":11077.909,"command_to_response_ms":20794.4,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":12509.849,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":36.487,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.683,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.683,"unexplained_pre_remote_ms":12473.362,"worker_unattributed_ms":null},"output_collection_ms":9.135,"pre_sampler_ms":2516.981,"restore_total_ms":1493.522,"sampler_ms":3663.447,"snapshot_callback_age_at_restore_ms":99711.988,"snapshot_callback_to_command_start_ms":88636.02,"submission_to_first_remote_event_ms":12509.849,"submit2entry_ms":12199.207,"t3b_to_t8_ms":7804.163,"vae_decode_ms":512.605,"wall_ms":20412.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.881ms unaccounted"]`
- Waterfall stages: `{"application_restore":1493.529571,"captured_timeline_gap":0.8811450000030163,"clip_to_sampler_node":81.926,"first_node_to_clip":79.583,"local_preparation":378.682624,"modal_handle_submission":8.999976,"modal_scheduling":10690.226392,"output_persistence":201.75924,"post_sampling_transition":903.938829,"prompt_executor_cache_setup":261.86,"remote_local_return":12.000068,"remote_method_setup":36.533288,"remote_return_handoff":357.923643,"restore_to_method_entry":13.442729,"sampler_node_to_sampling":887.336122,"sampling":4873.17953,"vae":512.605011}`

### `v2_2026-08-05_11-10-11` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-d86a5af549e3`
- Policy/order: `T1` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `707621f21f4e5bb748258fae`
- Container session: `3845417547004973`
- Modal task: `ta-01KZ8SMV1THBC83VDS7GXN7HER`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-5NKRDUTm1zFJdC9gCb9RsL`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":8669.934,"command_to_response_ms":18531.2,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9880.656,"generator_create_ms":2.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":45.818,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.811,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.811,"unexplained_pre_remote_ms":9834.837,"worker_unattributed_ms":null},"output_collection_ms":9.738,"pre_sampler_ms":2938.596,"restore_total_ms":1259.872,"sampler_ms":3732.696,"snapshot_callback_age_at_restore_ms":157982.586,"snapshot_callback_to_command_start_ms":149824.02,"submission_to_first_remote_event_ms":9880.656,"submit2entry_ms":9566.548,"t3b_to_t8_ms":8160.056,"vae_decode_ms":512.003,"wall_ms":18153.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.929ms unaccounted"]`
- Waterfall stages: `{"application_restore":1259.881482,"captured_timeline_gap":0.9287299999996321,"clip_to_sampler_node":71.898,"first_node_to_clip":122.704,"local_preparation":374.811136,"modal_handle_submission":9.002064,"modal_scheduling":8286.120624,"output_persistence":198.939616,"post_sampling_transition":771.789371,"prompt_executor_cache_setup":321.704,"remote_local_return":19.000348,"remote_method_setup":45.838625,"remote_return_handoff":359.586531,"restore_to_method_entry":18.532028,"sampler_node_to_sampling":1157.066228,"sampling":5001.351284,"vae":512.003181}`

### `v2_2026-08-05_11-12-18` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0b684ca566c8`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `565de0b9bedd4b14`
- Modal task: `ta-01KZ8SZKDKA7RD4K7A795BR63R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":117329.25,"command_to_response_ms":129218.7,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":119504.404,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":53.214,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.756,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.756,"unexplained_pre_remote_ms":119451.189,"worker_unattributed_ms":null},"output_collection_ms":10.019,"pre_sampler_ms":4095.401,"restore_total_ms":1479.212,"sampler_ms":3690.752,"snapshot_callback_age_at_restore_ms":46990.991,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":119504.404,"submit2entry_ms":118942.466,"t3b_to_t8_ms":9211.824,"vae_decode_ms":665.982,"wall_ms":128895.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.683ms unaccounted"]`
- Waterfall stages: `{"application_restore":1479.219374,"captured_timeline_gap":2.6831719999900088,"clip_to_sampler_node":610.35,"first_node_to_clip":4.52,"local_preparation":319.75552,"modal_handle_submission":10.00118,"modal_scheduling":116999.493604,"output_persistence":247.37415,"post_sampling_transition":500.417743,"prompt_executor_cache_setup":228.001,"remote_local_return":11.996788,"remote_method_setup":53.232363,"remote_return_handoff":674.142714,"restore_to_method_entry":460.742619,"sampler_node_to_sampling":1693.889262,"sampling":5256.872332,"vae":665.982867}`

### `v2_2026-08-05_11-15-05` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b457fc623914`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `dd45d5cd192d4048`
- Modal task: `ta-01KZ8T4PQFD31ZZJEJE533BN8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":71222.312,"command_to_response_ms":92185.2,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":72385.327,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":6.768,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":44.046,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.503,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.503,"unexplained_pre_remote_ms":72341.281,"worker_unattributed_ms":null},"output_collection_ms":9.263,"pre_sampler_ms":14033.487,"restore_total_ms":1203.413,"sampler_ms":3674.8,"snapshot_callback_age_at_restore_ms":35726.667,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":72385.327,"submit2entry_ms":72056.606,"t3b_to_t8_ms":19313.393,"vae_decode_ms":586.031,"wall_ms":91808.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.906ms unaccounted"]`
- Waterfall stages: `{"application_restore":1203.420621,"captured_timeline_gap":0.9059190000407398,"clip_to_sampler_node":1937.64,"first_node_to_clip":3.219,"local_preparation":373.503104,"modal_handle_submission":9.769596,"modal_scheduling":70839.039108,"output_persistence":204.180507,"post_sampling_transition":809.700433,"prompt_executor_cache_setup":390.425,"remote_local_return":14.996416,"remote_method_setup":44.068779,"remote_return_handoff":377.08797,"restore_to_method_entry":11.137362,"sampler_node_to_sampling":10371.684543,"sampling":5008.349586,"vae":586.030072}`

### `v2_2026-08-05_11-17-18` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-fdb0f06576dc`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `dd45d5cd192d4048`
- Modal task: `ta-01KZ8T4PQFD31ZZJEJE533BN8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6507.414,"command_to_response_ms":18619.2,"handle_lookup_ms":2.895,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10557.223,"generator_create_ms":2.895,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":42.08,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":16.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.038,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.038,"unexplained_pre_remote_ms":10515.143,"worker_unattributed_ms":null},"output_collection_ms":9.215,"pre_sampler_ms":2439.949,"restore_total_ms":4094.805,"sampler_ms":3672.298,"snapshot_callback_age_at_restore_ms":104479.625,"snapshot_callback_to_command_start_ms":97975.805,"submission_to_first_remote_event_ms":10557.223,"submit2entry_ms":10225.963,"t3b_to_t8_ms":7577.276,"vae_decode_ms":499.238,"wall_ms":18231.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.912ms unaccounted"]`
- Waterfall stages: `{"application_restore":4094.811881,"captured_timeline_gap":0.9116370000010647,"clip_to_sampler_node":163.187,"first_node_to_clip":1.998,"local_preparation":384.037632,"modal_handle_submission":9.894568,"modal_scheduling":6113.482072,"output_persistence":197.085725,"post_sampling_transition":763.088063,"prompt_executor_cache_setup":205.324,"remote_local_return":12.000672,"remote_method_setup":42.173029,"remote_return_handoff":372.419564,"restore_to_method_entry":14.765929,"sampler_node_to_sampling":857.431656,"sampling":4887.386806,"vae":499.236838}`

### `v2_2026-08-05_11-18-17` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9dcab198a9a3`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `dd45d5cd192d4048`
- Modal task: `ta-01KZ8T4PQFD31ZZJEJE533BN8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":37773.433,"command_to_response_ms":58587.7,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":39333.084,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":43.604,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.519,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.519,"unexplained_pre_remote_ms":39289.48,"worker_unattributed_ms":null},"output_collection_ms":10.274,"pre_sampler_ms":13340.484,"restore_total_ms":1615.714,"sampler_ms":3702.551,"snapshot_callback_age_at_restore_ms":193915.383,"snapshot_callback_to_command_start_ms":156143.805,"submission_to_first_remote_event_ms":39333.084,"submit2entry_ms":39000.923,"t3b_to_t8_ms":18673.019,"vae_decode_ms":553.455,"wall_ms":58189.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.036ms unaccounted"]`
- Waterfall stages: `{"application_restore":1615.72306,"captured_timeline_gap":1.0355270000000019,"clip_to_sampler_node":2445.803,"first_node_to_clip":2.399,"local_preparation":395.519232,"modal_handle_submission":9.000568,"modal_scheduling":37368.913544,"output_persistence":220.075469,"post_sampling_transition":850.40237,"prompt_executor_cache_setup":224.143,"remote_local_return":11.998512,"remote_method_setup":43.647955,"remote_return_handoff":458.896211,"restore_to_method_entry":13.276859,"sampler_node_to_sampling":9456.086263,"sampling":4917.362782,"vae":553.45476}`

### `v2_2026-08-05_11-19-54` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-3c553658cacd`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `dd45d5cd192d4048`
- Modal task: `ta-01KZ8T4PQFD31ZZJEJE533BN8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6703.008,"command_to_response_ms":15948.3,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7542.111,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":155.176,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.131,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.131,"unexplained_pre_remote_ms":7386.935,"worker_unattributed_ms":null},"output_collection_ms":10.002,"pre_sampler_ms":2578.4,"restore_total_ms":811.82,"sampler_ms":3708.011,"snapshot_callback_age_at_restore_ms":260361.016,"snapshot_callback_to_command_start_ms":253661.806,"submission_to_first_remote_event_ms":7542.111,"submit2entry_ms":7171.095,"t3b_to_t8_ms":7867.537,"vae_decode_ms":509.643,"wall_ms":15564.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.462ms unaccounted"]`
- Waterfall stages: `{"application_restore":811.834884,"captured_timeline_gap":1.46192499999961,"clip_to_sampler_node":192.356,"first_node_to_clip":2.973,"local_preparation":380.130944,"modal_handle_submission":9.000856,"modal_scheduling":6313.876584,"output_persistence":198.842773,"post_sampling_transition":867.309424,"prompt_executor_cache_setup":246.998,"remote_local_return":17.998604,"remote_method_setup":155.294283,"remote_return_handoff":390.852388,"restore_to_method_entry":43.368936,"sampler_node_to_sampling":889.796435,"sampling":4916.606152,"vae":509.643516}`

### `v2_2026-08-05_11-20-51` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5cafc128d265`
- Policy/order: `T2` / `O0`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `b4550f29e703295eec1f905a`
- Container session: `dd45d5cd192d4048`
- Modal task: `ta-01KZ8T4PQFD31ZZJEJE533BN8R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-4YdlBanqJGQThEmagiTI29`
- Observed runtime status: `validated`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5526.863,"command_to_response_ms":19733.7,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6465.185,"generator_create_ms":2.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":88.786,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.913,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.913,"unexplained_pre_remote_ms":6376.399,"worker_unattributed_ms":null},"output_collection_ms":7.461,"pre_sampler_ms":7628.745,"restore_total_ms":948.818,"sampler_ms":3670.84,"snapshot_callback_age_at_restore_ms":316039.29,"snapshot_callback_to_command_start_ms":310513.805,"submission_to_first_remote_event_ms":6465.185,"submit2entry_ms":6114.138,"t3b_to_t8_ms":12757.132,"vae_decode_ms":503.347,"wall_ms":19351.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.944ms unaccounted"]`
- Waterfall stages: `{"application_restore":948.824358,"captured_timeline_gap":0.9439069999934873,"clip_to_sampler_node":823.147,"first_node_to_clip":9.04,"local_preparation":377.912704,"modal_handle_submission":9.002796,"modal_scheduling":5139.94722,"output_persistence":191.391885,"post_sampling_transition":757.465384,"prompt_executor_cache_setup":471.311,"remote_local_return":14.999992,"remote_method_setup":88.823348,"remote_return_handoff":375.78363,"restore_to_method_entry":23.357036,"sampler_node_to_sampling":5122.739292,"sampling":4875.677405,"vae":503.346835}`

### `v2_2026-08-05_11-23-35` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c0c96376c52e`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":109180.508,"command_to_response_ms":129269.1,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":110996.847,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":737.424,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.666,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.666,"unexplained_pre_remote_ms":110259.423,"worker_unattributed_ms":null},"output_collection_ms":9.996,"pre_sampler_ms":10466.531,"restore_total_ms":1006.254,"sampler_ms":3712.834,"snapshot_callback_age_at_restore_ms":52306.924,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":110996.847,"submit2entry_ms":110118.06,"t3b_to_t8_ms":15656.74,"vae_decode_ms":608.848,"wall_ms":128947.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.702ms unaccounted"]`
- Waterfall stages: `{"application_restore":1006.261951,"captured_timeline_gap":1.7021740000054706,"clip_to_sampler_node":6077.636,"first_node_to_clip":34.96,"local_preparation":318.66624,"modal_handle_submission":9.00176,"modal_scheduling":108852.839648,"output_persistence":242.381197,"post_sampling_transition":621.773136,"prompt_executor_cache_setup":148.863,"remote_local_return":17.99934,"remote_method_setup":737.453422,"remote_return_handoff":2415.568553,"restore_to_method_entry":256.948084,"sampler_node_to_sampling":2888.210048,"sampling":5029.972625,"vae":608.848262}`

### `v2_2026-08-05_11-26-23` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-422ffa9b3e7c`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":8748.079,"command_to_response_ms":22840.6,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10315.948,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":404.025,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.959,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.959,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.839,"pre_sampler_ms":5907.462,"restore_total_ms":1350.944,"sampler_ms":3713.888,"snapshot_callback_age_at_restore_ms":119717.345,"snapshot_callback_to_command_start_ms":111202.612,"submission_to_first_remote_event_ms":10315.948,"submit2entry_ms":9943.973,"t3b_to_t8_ms":11426.221,"vae_decode_ms":722.719,"wall_ms":22429.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.928ms unaccounted"]`
- Waterfall stages: `{"application_restore":1350.954264,"captured_timeline_gap":2.9278569999987667,"clip_to_sampler_node":2355.949,"first_node_to_clip":41.151,"local_preparation":406.959168,"modal_handle_submission":10.001232,"modal_scheduling":8331.118512,"output_persistence":303.183131,"post_sampling_transition":770.57715,"prompt_executor_cache_setup":223.609,"remote_local_return":13.99896,"remote_method_setup":404.043726,"remote_return_handoff":639.126051,"restore_to_method_entry":259.885589,"sampler_node_to_sampling":1872.617663,"sampling":5131.777503,"vae":722.719554}`

### `v2_2026-08-05_11-27-28` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c29a5e9bebbb`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5904.866,"command_to_response_ms":26375.5,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7175.793,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":5.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":255.901,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.669,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.669,"unexplained_pre_remote_ms":6919.892,"worker_unattributed_ms":null},"output_collection_ms":12.357,"pre_sampler_ms":13357.101,"restore_total_ms":1298.013,"sampler_ms":3721.233,"snapshot_callback_age_at_restore_ms":182615.861,"snapshot_callback_to_command_start_ms":176720.612,"submission_to_first_remote_event_ms":7175.793,"submit2entry_ms":6836.38,"t3b_to_t8_ms":18467.724,"vae_decode_ms":604.682,"wall_ms":25991.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 425.932ms unaccounted","reconciliation exceeds tolerance: 425.932ms > 131.877ms"]`
- Waterfall stages: `{"application_restore":1298.016792,"captured_timeline_gap":425.93189099999654,"clip_to_sampler_node":492.276,"first_node_to_clip":143.018,"local_preparation":381.6688,"modal_handle_submission":8.9994,"modal_scheduling":5514.197272,"output_persistence":238.713635,"post_sampling_transition":540.069791,"prompt_executor_cache_setup":1637.593,"remote_local_return":12.998388,"remote_method_setup":255.921183,"remote_return_handoff":417.068719,"restore_to_method_entry":21.162311,"sampler_node_to_sampling":9348.445757,"sampling":5034.704338,"vae":604.681411}`

### `v2_2026-08-05_11-28-35` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2d18a3275a6e`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5144.554,"command_to_response_ms":17255.1,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5497.636,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":9.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":213.208,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.983,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.983,"unexplained_pre_remote_ms":5284.428,"worker_unattributed_ms":null},"output_collection_ms":11.331,"pre_sampler_ms":5758.178,"restore_total_ms":502.011,"sampler_ms":3725.427,"snapshot_callback_age_at_restore_ms":248253.683,"snapshot_callback_to_command_start_ms":243231.612,"submission_to_first_remote_event_ms":5497.636,"submit2entry_ms":5154.355,"t3b_to_t8_ms":10936.205,"vae_decode_ms":591.256,"wall_ms":16738.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 54.188ms unaccounted"]`
- Waterfall stages: `{"application_restore":502.027344,"captured_timeline_gap":54.18827799999781,"clip_to_sampler_node":1177.281,"first_node_to_clip":376.82,"local_preparation":511.982592,"modal_handle_submission":12.001108,"modal_scheduling":4620.570284,"output_persistence":231.26252,"post_sampling_transition":624.532904,"prompt_executor_cache_setup":569.813,"remote_local_return":13.000172,"remote_method_setup":213.272778,"remote_return_handoff":421.833599,"restore_to_method_entry":28.720877,"sampler_node_to_sampling":2320.848011,"sampling":4985.696957,"vae":591.255648}`

### `v2_2026-08-05_11-29-32` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-731bba7198aa`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `e42ff7d78c2d4b6c`
- Modal task: `ta-01KZ8TZ5CFG3508YR2CY1VWSDR`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":81259.621,"command_to_response_ms":93127.4,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":84880.785,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.312,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":49.52,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.145,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.145,"unexplained_pre_remote_ms":84831.265,"worker_unattributed_ms":null},"output_collection_ms":8.118,"pre_sampler_ms":2573.262,"restore_total_ms":3643.892,"sampler_ms":3698.241,"snapshot_callback_age_at_restore_ms":42711.207,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":84880.785,"submit2entry_ms":84536.594,"t3b_to_t8_ms":7771.947,"vae_decode_ms":502.217,"wall_ms":92744.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.905ms unaccounted"]`
- Waterfall stages: `{"application_restore":3643.917243,"captured_timeline_gap":0.9048530000000028,"clip_to_sampler_node":136.017,"first_node_to_clip":39.528,"local_preparation":379.14464,"modal_handle_submission":9.31366,"modal_scheduling":80871.163012,"output_persistence":198.806497,"post_sampling_transition":796.439709,"prompt_executor_cache_setup":239.405,"remote_local_return":12.99852,"remote_method_setup":49.564415,"remote_return_handoff":372.806098,"restore_to_method_entry":18.504108,"sampler_node_to_sampling":1023.785046,"sampling":4832.880618,"vae":502.217101}`

### `v2_2026-08-05_11-31-47` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0b389bcd96f0`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5282.84,"command_to_response_ms":15938.2,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6416.354,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":340.145,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.404,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.404,"unexplained_pre_remote_ms":6076.208,"worker_unattributed_ms":null},"output_collection_ms":12.022,"pre_sampler_ms":3582.055,"restore_total_ms":1148.991,"sampler_ms":3724.998,"snapshot_callback_age_at_restore_ms":440842.683,"snapshot_callback_to_command_start_ms":435745.612,"submission_to_first_remote_event_ms":6416.354,"submit2entry_ms":6075.12,"t3b_to_t8_ms":8708.775,"vae_decode_ms":606.005,"wall_ms":15551.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.720ms unaccounted"]`
- Waterfall stages: `{"application_restore":1149.006748,"captured_timeline_gap":2.72048900000118,"clip_to_sampler_node":60.408,"first_node_to_clip":48.597,"local_preparation":383.403904,"modal_handle_submission":9.000796,"modal_scheduling":4890.43498,"output_persistence":226.029223,"post_sampling_transition":562.406267,"prompt_executor_cache_setup":347.982,"remote_local_return":13.00066,"remote_method_setup":340.191086,"remote_return_handoff":413.987115,"restore_to_method_entry":33.661996,"sampler_node_to_sampling":1867.133965,"sampling":4984.193583,"vae":606.004748}`

### `v2_2026-08-05_11-32-44` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c8d7c3a365cd`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3835.16,"command_to_response_ms":15412.1,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5029.674,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":323.378,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.92,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.92,"unexplained_pre_remote_ms":4706.296,"worker_unattributed_ms":null},"output_collection_ms":10.839,"pre_sampler_ms":4434.97,"restore_total_ms":1178.057,"sampler_ms":3723.578,"snapshot_callback_age_at_restore_ms":496578.397,"snapshot_callback_to_command_start_ms":492751.612,"submission_to_first_remote_event_ms":5029.674,"submit2entry_ms":4672.677,"t3b_to_t8_ms":9615.13,"vae_decode_ms":603.237,"wall_ms":15036.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.225ms unaccounted"]`
- Waterfall stages: `{"application_restore":1178.072516,"captured_timeline_gap":1.22504299999855,"clip_to_sampler_node":133.791,"first_node_to_clip":66.724,"local_preparation":371.920384,"modal_handle_submission":9.000916,"modal_scheduling":3454.23902,"output_persistence":228.057731,"post_sampling_transition":617.835224,"prompt_executor_cache_setup":1041.314,"remote_local_return":11.999808,"remote_method_setup":323.407947,"remote_return_handoff":417.787636,"restore_to_method_entry":38.353139,"sampler_node_to_sampling":1927.685049,"sampling":4987.469161,"vae":603.237234}`

### `v2_2026-08-05_11-33-38` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a2611651183e`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5301.226,"command_to_response_ms":16255.5,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6364.002,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.993,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":305.226,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.678,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.678,"unexplained_pre_remote_ms":6058.776,"worker_unattributed_ms":null},"output_collection_ms":11.633,"pre_sampler_ms":3933.562,"restore_total_ms":1031.008,"sampler_ms":3733.505,"snapshot_callback_age_at_restore_ms":552314.154,"snapshot_callback_to_command_start_ms":547026.612,"submission_to_first_remote_event_ms":6364.002,"submit2entry_ms":6000.291,"t3b_to_t8_ms":9135.009,"vae_decode_ms":605.081,"wall_ms":15874.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.506ms unaccounted"]`
- Waterfall stages: `{"application_restore":1031.04047,"captured_timeline_gap":1.5058129999997618,"clip_to_sampler_node":61.748,"first_node_to_clip":52.07,"local_preparation":377.677888,"modal_handle_submission":8.994212,"modal_scheduling":4914.553692,"output_persistence":237.99155,"post_sampling_transition":618.975811,"prompt_executor_cache_setup":648.533,"remote_local_return":13.0001,"remote_method_setup":305.250327,"remote_return_handoff":420.0222,"restore_to_method_entry":52.663345,"sampler_node_to_sampling":1914.09859,"sampling":4992.296264,"vae":605.081138}`

### `v2_2026-08-05_11-34-35` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8b6da1e22dcd`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6946.364,"command_to_response_ms":33093.6,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10103.99,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":303.941,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.246,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.246,"unexplained_pre_remote_ms":9800.048,"worker_unattributed_ms":null},"output_collection_ms":10.803,"pre_sampler_ms":16810.733,"restore_total_ms":3168.196,"sampler_ms":3681.545,"snapshot_callback_age_at_restore_ms":610595.481,"snapshot_callback_to_command_start_ms":603650.612,"submission_to_first_remote_event_ms":10103.989,"submit2entry_ms":9727.572,"t3b_to_t8_ms":21648.65,"vae_decode_ms":545.611,"wall_ms":32608.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 518.586ms unaccounted","reconciliation exceeds tolerance: 518.586ms > 165.468ms"]`
- Waterfall stages: `{"application_restore":3168.209017,"captured_timeline_gap":518.5864150000016,"clip_to_sampler_node":2308.387,"first_node_to_clip":90.723,"local_preparation":481.24576,"modal_handle_submission":9.99974,"modal_scheduling":6455.11898,"output_persistence":203.751436,"post_sampling_transition":402.849616,"prompt_executor_cache_setup":598.313,"remote_local_return":11.998756,"remote_method_setup":304.042981,"remote_return_handoff":915.742314,"restore_to_method_entry":101.241269,"sampler_node_to_sampling":12033.924879,"sampling":4943.856717,"vae":545.610976}`

### `v2_2026-08-05_11-35-48` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-1b3c1f7f901a`
- Policy/order: `TBASE` / `O1`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `7b0217a5f094cab6557c88f8`
- Container session: `77ad74d4782d47a5`
- Modal task: `ta-01KZ8TM8PB6ZHW7QHBWZZVSBZR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-HoQuvpdO3XwJ7Gnk8GcotS`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6396.126,"command_to_response_ms":25023.8,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7345.571,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":168.543,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.887,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.887,"unexplained_pre_remote_ms":7177.028,"worker_unattributed_ms":null},"output_collection_ms":11.67,"pre_sampler_ms":10893.499,"restore_total_ms":981.498,"sampler_ms":3733.599,"snapshot_callback_age_at_restore_ms":683020.449,"snapshot_callback_to_command_start_ms":676827.612,"submission_to_first_remote_event_ms":7345.57,"submit2entry_ms":6998.994,"t3b_to_t8_ms":17021.832,"vae_decode_ms":1725.873,"wall_ms":24625.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.985ms unaccounted"]`
- Waterfall stages: `{"application_restore":981.506644,"captured_timeline_gap":0.9852570000002743,"clip_to_sampler_node":1927.701,"first_node_to_clip":111.02,"local_preparation":394.886912,"modal_handle_submission":9.001588,"modal_scheduling":5992.237708,"output_persistence":225.610698,"post_sampling_transition":437.744637,"prompt_executor_cache_setup":563.862,"remote_local_return":11.997764,"remote_method_setup":168.569455,"remote_return_handoff":422.709209,"restore_to_method_entry":23.239631,"sampler_node_to_sampling":7015.018662,"sampling":5011.816393,"vae":1725.873306}`

### `v2_2026-08-05_11-38-19` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b73db14c06d4`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":107057.551,"command_to_response_ms":124876.4,"handle_lookup_ms":2.998,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":108776.121,"generator_create_ms":1.998,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.559,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":425.055,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.21,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.21,"unexplained_pre_remote_ms":108351.066,"worker_unattributed_ms":null},"output_collection_ms":10.342,"pre_sampler_ms":8407.977,"restore_total_ms":1205.513,"sampler_ms":3687.257,"snapshot_callback_age_at_restore_ms":51590.478,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":108776.121,"submit2entry_ms":108186.643,"t3b_to_t8_ms":13455.897,"vae_decode_ms":599.872,"wall_ms":124546.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.404ms unaccounted"]`
- Waterfall stages: `{"application_restore":1205.524717,"captured_timeline_gap":2.4035570000269217,"clip_to_sampler_node":4970.912,"first_node_to_clip":220.54,"local_preparation":327.209728,"modal_handle_submission":9.557772,"modal_scheduling":106720.783092,"output_persistence":252.830706,"post_sampling_transition":502.138507,"prompt_executor_cache_setup":149.119,"remote_local_return":12.000492,"remote_method_setup":425.081286,"remote_return_handoff":2468.742772,"restore_to_method_entry":257.327007,"sampler_node_to_sampling":1888.885435,"sampling":4863.502847,"vae":599.871674}`

### `v2_2026-08-05_11-41-04` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0645e5e79e30`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":21812.984,"command_to_response_ms":37871.1,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":24307.071,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":557.551,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.583,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.583,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.453,"pre_sampler_ms":6136.211,"restore_total_ms":2493.898,"sampler_ms":3786.459,"snapshot_callback_age_at_restore_ms":130642.673,"snapshot_callback_to_command_start_ms":109997.836,"submission_to_first_remote_event_ms":24307.071,"submit2entry_ms":23954.093,"t3b_to_t8_ms":12535.703,"vae_decode_ms":1000.328,"wall_ms":37484.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.112ms unaccounted"]`
- Waterfall stages: `{"application_restore":2493.910481,"captured_timeline_gap":1.1123679999946035,"clip_to_sampler_node":192.939,"first_node_to_clip":38.826,"local_preparation":383.583488,"modal_handle_submission":9.001312,"modal_scheduling":21420.399008,"output_persistence":266.075766,"post_sampling_transition":1342.150387,"prompt_executor_cache_setup":486.327,"remote_local_return":10.999504,"remote_method_setup":557.596539,"remote_return_handoff":443.292693,"restore_to_method_entry":37.778138,"sampler_node_to_sampling":3130.092315,"sampling":6056.713448,"vae":1000.328057}`

### `v2_2026-08-05_11-42-21` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-fa5f08b8dc69`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5142.508,"command_to_response_ms":15724.8,"handle_lookup_ms":3.177,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6292.342,"generator_create_ms":3.177,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":239.337,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.522,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.522,"unexplained_pre_remote_ms":6053.005,"worker_unattributed_ms":null},"output_collection_ms":11.538,"pre_sampler_ms":3641.714,"restore_total_ms":1133.118,"sampler_ms":3706.112,"snapshot_callback_age_at_restore_ms":192045.028,"snapshot_callback_to_command_start_ms":186908.836,"submission_to_first_remote_event_ms":6292.342,"submit2entry_ms":5924.229,"t3b_to_t8_ms":8734.683,"vae_decode_ms":597.835,"wall_ms":15345.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.042ms unaccounted"]`
- Waterfall stages: `{"application_restore":1133.186045,"captured_timeline_gap":2.041887000001225,"clip_to_sampler_node":83.977,"first_node_to_clip":3.039,"local_preparation":375.5216,"modal_handle_submission":10.1768,"modal_scheduling":4756.809184,"output_persistence":225.388786,"post_sampling_transition":558.353177,"prompt_executor_cache_setup":411.365,"remote_local_return":19.00036,"remote_method_setup":239.359429,"remote_return_handoff":426.669227,"restore_to_method_entry":30.656558,"sampler_node_to_sampling":1892.882993,"sampling":4958.555521,"vae":597.834393}`

### `v2_2026-08-05_11-43-17` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-71925556d432`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5226.295,"command_to_response_ms":16914.0,"handle_lookup_ms":2.004,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6425.557,"generator_create_ms":2.004,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.007,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":285.89,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.312,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.312,"unexplained_pre_remote_ms":6139.667,"worker_unattributed_ms":null},"output_collection_ms":18.765,"pre_sampler_ms":4389.795,"restore_total_ms":1172.624,"sampler_ms":3729.888,"snapshot_callback_age_at_restore_ms":248654.554,"snapshot_callback_to_command_start_ms":243447.836,"submission_to_first_remote_event_ms":6425.557,"submit2entry_ms":6047.834,"t3b_to_t8_ms":9732.497,"vae_decode_ms":606.355,"wall_ms":16529.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.488ms unaccounted"]`
- Waterfall stages: `{"application_restore":1172.643323,"captured_timeline_gap":1.488031000000774,"clip_to_sampler_node":109.578,"first_node_to_clip":2.9,"local_preparation":380.311936,"modal_handle_submission":9.011164,"modal_scheduling":4836.971812,"output_persistence":254.13907,"post_sampling_transition":747.227419,"prompt_executor_cache_setup":420.66,"remote_local_return":17.00058,"remote_method_setup":285.942726,"remote_return_handoff":448.869196,"restore_to_method_entry":35.207901,"sampler_node_to_sampling":2525.515266,"sampling":5060.155038,"vae":606.354218}`

### `v2_2026-08-05_11-44-16` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2b16cffc243e`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4614.788,"command_to_response_ms":16922.9,"handle_lookup_ms":1.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5613.685,"generator_create_ms":1.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.003,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":173.859,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.128,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.128,"unexplained_pre_remote_ms":5439.826,"worker_unattributed_ms":null},"output_collection_ms":10.563,"pre_sampler_ms":5549.34,"restore_total_ms":886.369,"sampler_ms":3722.445,"snapshot_callback_age_at_restore_ms":306687.706,"snapshot_callback_to_command_start_ms":302074.836,"submission_to_first_remote_event_ms":5613.685,"submit2entry_ms":5243.306,"t3b_to_t8_ms":10658.637,"vae_decode_ms":593.121,"wall_ms":16539.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.043ms unaccounted"]`
- Waterfall stages: `{"application_restore":886.383941,"captured_timeline_gap":1.0433009999978822,"clip_to_sampler_node":161.685,"first_node_to_clip":7.56,"local_preparation":380.127936,"modal_handle_submission":9.001364,"modal_scheduling":4225.658988,"output_persistence":234.681575,"post_sampling_transition":554.541793,"prompt_executor_cache_setup":717.457,"remote_local_return":12.999596,"remote_method_setup":173.910602,"remote_return_handoff":448.937981,"restore_to_method_entry":129.25627,"sampler_node_to_sampling":3352.979497,"sampling":5033.574247,"vae":593.121805}`

### `v2_2026-08-05_11-45-14` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-fda4f7b0e91c`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":28952.982,"command_to_response_ms":45483.0,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":30657.954,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":348.58,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":15.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.621,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.621,"unexplained_pre_remote_ms":30309.374,"worker_unattributed_ms":null},"output_collection_ms":11.776,"pre_sampler_ms":8411.522,"restore_total_ms":1687.707,"sampler_ms":3748.312,"snapshot_callback_age_at_restore_ms":388510.68,"snapshot_callback_to_command_start_ms":359561.836,"submission_to_first_remote_event_ms":30657.954,"submit2entry_ms":30293.523,"t3b_to_t8_ms":13995.149,"vae_decode_ms":662.842,"wall_ms":45094.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.736ms unaccounted"]`
- Waterfall stages: `{"application_restore":1687.725203,"captured_timeline_gap":1.7361239999954705,"clip_to_sampler_node":2038.194,"first_node_to_clip":522.417,"local_preparation":384.6208,"modal_handle_submission":9.0008,"modal_scheduling":28559.360672,"output_persistence":242.282027,"post_sampling_transition":925.855595,"prompt_executor_cache_setup":2016.039,"remote_local_return":12.9993,"remote_method_setup":348.598335,"remote_return_handoff":443.432028,"restore_to_method_entry":44.427162,"sampler_node_to_sampling":2546.299288,"sampling":5037.172104,"vae":662.842162}`

### `v2_2026-08-05_11-46-38` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-44bbd89d1178`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4684.966,"command_to_response_ms":15917.7,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5759.164,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":465.778,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.394,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.394,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":13.919,"pre_sampler_ms":3988.939,"restore_total_ms":1079.846,"sampler_ms":3750.693,"snapshot_callback_age_at_restore_ms":448245.644,"snapshot_callback_to_command_start_ms":443578.836,"submission_to_first_remote_event_ms":5759.164,"submit2entry_ms":5387.88,"t3b_to_t8_ms":9220.701,"vae_decode_ms":605.773,"wall_ms":15503.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.963ms unaccounted"]`
- Waterfall stages: `{"application_restore":1080.110742,"captured_timeline_gap":1.9631499999995867,"clip_to_sampler_node":93.855,"first_node_to_clip":3.285,"local_preparation":410.393792,"modal_handle_submission":11.002308,"modal_scheduling":4263.56998,"output_persistence":224.664583,"post_sampling_transition":644.290521,"prompt_executor_cache_setup":713.569,"remote_local_return":11.997524,"remote_method_setup":466.086293,"remote_return_handoff":434.602653,"restore_to_method_entry":40.122515,"sampler_node_to_sampling":1837.856375,"sampling":5074.540227,"vae":605.772961}`

### `v2_2026-08-05_11-47-32` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-aa8d3cad8cfa`
- Policy/order: `TBASE` / `O2`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `ef1a34d45a452ab8cca3ca18`
- Container session: `2e1d59c8ad7f4730`
- Modal task: `ta-01KZ8VF7XD3210XKQFJPZ7HT8R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-bDVuofTIAVxuk0XIpwvr7n`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6120.27,"command_to_response_ms":32012.6,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":11188.632,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":15.0,"generator_created_to_first_iteration_ms":1.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":295.517,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.519,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.519,"unexplained_pre_remote_ms":10893.114,"worker_unattributed_ms":null},"output_collection_ms":9.485,"pre_sampler_ms":15078.534,"restore_total_ms":4961.856,"sampler_ms":3671.921,"snapshot_callback_age_at_restore_ms":504533.075,"snapshot_callback_to_command_start_ms":498417.836,"submission_to_first_remote_event_ms":11188.632,"submit2entry_ms":10778.392,"t3b_to_t8_ms":19891.633,"vae_decode_ms":539.43,"wall_ms":31609.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 7.499ms unaccounted"]`
- Waterfall stages: `{"application_restore":4961.863273,"captured_timeline_gap":7.499337999997806,"clip_to_sampler_node":1972.571,"first_node_to_clip":482.985,"local_preparation":399.51872,"modal_handle_submission":11.00168,"modal_scheduling":5709.749168,"output_persistence":192.059859,"post_sampling_transition":405.593959,"prompt_executor_cache_setup":485.994,"remote_local_return":12.99754,"remote_method_setup":295.552911,"remote_return_handoff":629.566923,"restore_to_method_entry":103.777319,"sampler_node_to_sampling":10845.000651,"sampling":4957.463535,"vae":539.429764}`

### `v2_2026-08-05_11-50-38` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-2963f7702a39`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":99733.725,"command_to_response_ms":116570.4,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":101282.562,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":466.058,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.014,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.014,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.04,"pre_sampler_ms":8015.22,"restore_total_ms":1467.352,"sampler_ms":3726.341,"snapshot_callback_age_at_restore_ms":40738.938,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":101282.562,"submit2entry_ms":100891.606,"t3b_to_t8_ms":13258.172,"vae_decode_ms":649.887,"wall_ms":116238.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.277ms unaccounted"]`
- Waterfall stages: `{"application_restore":1467.39818,"captured_timeline_gap":1.277232999986154,"clip_to_sampler_node":4477.191,"first_node_to_clip":39.564,"local_preparation":328.013824,"modal_handle_submission":9.000676,"modal_scheduling":99396.710428,"output_persistence":251.734299,"post_sampling_transition":604.399486,"prompt_executor_cache_setup":144.388,"remote_local_return":23.99938,"remote_method_setup":466.078553,"remote_return_handoff":1597.12305,"restore_to_method_entry":25.483605,"sampler_node_to_sampling":2126.210308,"sampling":4961.987034,"vae":649.887024}`

### `v2_2026-08-05_11-53-15` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-ff148e3e7933`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5941.149,"command_to_response_ms":28049.4,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6893.165,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":426.43,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.13,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.13,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":12.238,"pre_sampler_ms":14890.976,"restore_total_ms":961.723,"sampler_ms":3732.289,"snapshot_callback_age_at_restore_ms":103619.238,"snapshot_callback_to_command_start_ms":97708.388,"submission_to_first_remote_event_ms":6893.165,"submit2entry_ms":6530.111,"t3b_to_t8_ms":20247.024,"vae_decode_ms":727.835,"wall_ms":27655.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.037ms unaccounted"]`
- Waterfall stages: `{"application_restore":961.809229,"captured_timeline_gap":1.0370179999990796,"clip_to_sampler_node":878.466,"first_node_to_clip":1506.258,"local_preparation":390.130048,"modal_handle_submission":9.001252,"modal_scheduling":5542.0175,"output_persistence":265.985099,"post_sampling_transition":619.924639,"prompt_executor_cache_setup":3773.818,"remote_local_return":13.000144,"remote_method_setup":426.465873,"remote_return_handoff":442.96078,"restore_to_method_entry":24.280138,"sampler_node_to_sampling":7044.432408,"sampling":5421.951451,"vae":727.834965}`

### `v2_2026-08-05_11-54-23` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-311007623de6`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5090.554,"command_to_response_ms":15745.7,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6167.861,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":152.509,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.74,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.74,"unexplained_pre_remote_ms":6015.351,"worker_unattributed_ms":null},"output_collection_ms":10.772,"pre_sampler_ms":3868.851,"restore_total_ms":1082.214,"sampler_ms":3719.462,"snapshot_callback_age_at_restore_ms":170827.816,"snapshot_callback_to_command_start_ms":165976.387,"submission_to_first_remote_event_ms":6167.861,"submit2entry_ms":5799.246,"t3b_to_t8_ms":8944.218,"vae_decode_ms":605.703,"wall_ms":15349.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.990ms unaccounted"]`
- Waterfall stages: `{"application_restore":1082.330583,"captured_timeline_gap":0.9902060000003985,"clip_to_sampler_node":56.2,"first_node_to_clip":41.255,"local_preparation":391.739776,"modal_handle_submission":10.001724,"modal_scheduling":4688.812484,"output_persistence":217.531415,"post_sampling_transition":523.130465,"prompt_executor_cache_setup":286.397,"remote_local_return":12.998792,"remote_method_setup":152.527446,"remote_return_handoff":439.111128,"restore_to_method_entry":25.067861,"sampler_node_to_sampling":2105.418788,"sampling":5106.478747,"vae":605.703177}`

### `v2_2026-08-05_11-55-17` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-5b0a3e12929b`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4476.222,"command_to_response_ms":15400.6,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5399.156,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":1.001,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":384.826,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.377,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.377,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.794,"pre_sampler_ms":3938.613,"restore_total_ms":899.119,"sampler_ms":3751.746,"snapshot_callback_age_at_restore_ms":224576.282,"snapshot_callback_to_command_start_ms":220105.388,"submission_to_first_remote_event_ms":5399.156,"submit2entry_ms":5017.791,"t3b_to_t8_ms":9135.611,"vae_decode_ms":621.815,"wall_ms":15008.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 3.338ms unaccounted"]`
- Waterfall stages: `{"application_restore":899.166595,"captured_timeline_gap":3.3381759999974747,"clip_to_sampler_node":62.509,"first_node_to_clip":42.126,"local_preparation":389.377088,"modal_handle_submission":10.000512,"modal_scheduling":4076.844416,"output_persistence":243.914026,"post_sampling_transition":567.002629,"prompt_executor_cache_setup":490.912,"remote_local_return":12.000088,"remote_method_setup":384.853954,"remote_return_handoff":461.057482,"restore_to_method_entry":38.768371,"sampler_node_to_sampling":1915.055199,"sampling":5181.89324,"vae":621.815912}`

### `v2_2026-08-05_11-56-11` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-8bc7e8824fc2`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4417.955,"command_to_response_ms":24539.5,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5483.779,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":499.474,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.82,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.82,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.848,"pre_sampler_ms":13040.299,"restore_total_ms":944.458,"sampler_ms":3704.593,"snapshot_callback_age_at_restore_ms":278560.991,"snapshot_callback_to_command_start_ms":274145.388,"submission_to_first_remote_event_ms":5483.779,"submit2entry_ms":5078.535,"t3b_to_t8_ms":17919.123,"vae_decode_ms":563.571,"wall_ms":24152.4}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.123ms unaccounted"]`
- Waterfall stages: `{"application_restore":944.487257,"captured_timeline_gap":1.123461999999563,"clip_to_sampler_node":339.356,"first_node_to_clip":131.708,"local_preparation":382.82016,"modal_handle_submission":8.99954,"modal_scheduling":4026.135436,"output_persistence":204.614737,"post_sampling_transition":397.131563,"prompt_executor_cache_setup":5795.486,"remote_local_return":18.991912,"remote_method_setup":499.493422,"remote_return_handoff":637.864369,"restore_to_method_entry":105.905036,"sampler_node_to_sampling":5476.62179,"sampling":5005.174024,"vae":563.571004}`

### `v2_2026-08-05_11-57-17` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-db37add1934e`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4899.801,"command_to_response_ms":15348.5,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6226.274,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":284.544,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.942,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.942,"unexplained_pre_remote_ms":5941.731,"worker_unattributed_ms":null},"output_collection_ms":10.274,"pre_sampler_ms":3257.758,"restore_total_ms":1254.89,"sampler_ms":3706.287,"snapshot_callback_age_at_restore_ms":344237.033,"snapshot_callback_to_command_start_ms":339358.387,"submission_to_first_remote_event_ms":6226.274,"submit2entry_ms":5817.457,"t3b_to_t8_ms":8143.434,"vae_decode_ms":564.512,"wall_ms":14909.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.753ms unaccounted"]`
- Waterfall stages: `{"application_restore":1254.965832,"captured_timeline_gap":0.7530839999999444,"clip_to_sampler_node":42.473,"first_node_to_clip":37.798,"local_preparation":435.941888,"modal_handle_submission":8.999312,"modal_scheduling":4454.860144,"output_persistence":201.848458,"post_sampling_transition":403.327689,"prompt_executor_cache_setup":270.504,"remote_local_return":15.00156,"remote_method_setup":284.561355,"remote_return_handoff":647.51645,"restore_to_method_entry":104.601586,"sampler_node_to_sampling":1609.128194,"sampling":5011.722245,"vae":564.511763}`

### `v2_2026-08-05_11-58-11` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-45f265a649e6`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4047.072,"command_to_response_ms":17187.1,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":4620.31,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.938,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":260.267,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.198,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.198,"unexplained_pre_remote_ms":4360.043,"worker_unattributed_ms":null},"output_collection_ms":12.44,"pre_sampler_ms":6749.83,"restore_total_ms":558.642,"sampler_ms":3706.953,"snapshot_callback_age_at_restore_ms":397881.403,"snapshot_callback_to_command_start_ms":393836.388,"submission_to_first_remote_event_ms":4620.31,"submit2entry_ms":4248.557,"t3b_to_t8_ms":11837.459,"vae_decode_ms":603.211,"wall_ms":16806.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.654ms unaccounted"]`
- Waterfall stages: `{"application_restore":558.678326,"captured_timeline_gap":2.653818999999203,"clip_to_sampler_node":573.179,"first_node_to_clip":483.884,"local_preparation":377.198208,"modal_handle_submission":9.937592,"modal_scheduling":3659.936584,"output_persistence":214.638813,"post_sampling_transition":550.464317,"prompt_executor_cache_setup":483.157,"remote_local_return":11.999276,"remote_method_setup":260.357085,"remote_return_handoff":447.165407,"restore_to_method_entry":26.932051,"sampler_node_to_sampling":3853.305699,"sampling":5070.445642,"vae":603.211757}`

### `v2_2026-08-05_11-59-07` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-52f34cf4ac17`
- Policy/order: `TBASE` / `O3`
- CPU/memory: `16` / `49152 MiB`
- Runtime fingerprint: `1e26a5be0a82c8d3558e53e9`
- Container session: `e2a20eb7828e4f68`
- Modal task: `ta-01KZ8W5SYNW1HY3V15T8NP153R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `eu-central-1`
- Image: `im-0kxt53oVkZD5QpcUjy3o1b`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5500.977,"command_to_response_ms":17390.5,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":7401.034,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":670.775,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.366,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.366,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":9.276,"pre_sampler_ms":3573.988,"restore_total_ms":1743.607,"sampler_ms":3670.316,"snapshot_callback_age_at_restore_ms":455455.006,"snapshot_callback_to_command_start_ms":449971.387,"submission_to_first_remote_event_ms":7401.034,"submit2entry_ms":6969.376,"t3b_to_t8_ms":8418.872,"vae_decode_ms":569.137,"wall_ms":17003.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.693ms unaccounted"]`
- Waterfall stages: `{"application_restore":1743.665794,"captured_timeline_gap":0.6927040000045963,"clip_to_sampler_node":41.845,"first_node_to_clip":37.01,"local_preparation":384.366272,"modal_handle_submission":9.000628,"modal_scheduling":5107.610444,"output_persistence":199.233626,"post_sampling_transition":397.025305,"prompt_executor_cache_setup":734.956,"remote_local_return":10.998352,"remote_method_setup":670.875778,"remote_return_handoff":936.54853,"restore_to_method_entry":116.09101,"sampler_node_to_sampling":1468.05446,"sampling":4963.394276,"vae":569.136973}`

### `v2_2026-08-05_12-01-40` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-a7dbc2ba0b57`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":166231.396,"command_to_response_ms":183203.6,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":167408.916,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":438.361,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.461,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.461,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.736,"pre_sampler_ms":8282.723,"restore_total_ms":1090.539,"sampler_ms":3682.237,"snapshot_callback_age_at_restore_ms":37872.733,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":167408.916,"submit2entry_ms":167013.026,"t3b_to_t8_ms":13499.646,"vae_decode_ms":639.143,"wall_ms":182872.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.278ms unaccounted"]`
- Waterfall stages: `{"application_restore":1090.546955,"captured_timeline_gap":1.278338999953121,"clip_to_sampler_node":4756.67,"first_node_to_clip":43.988,"local_preparation":327.461376,"modal_handle_submission":10.000624,"modal_scheduling":165893.93384,"output_persistence":248.333561,"post_sampling_transition":636.171802,"prompt_executor_cache_setup":157.348,"remote_local_return":11.999068,"remote_method_setup":438.38906,"remote_return_handoff":1908.067747,"restore_to_method_entry":25.535454,"sampler_node_to_sampling":2082.811568,"sampling":4931.900303,"vae":639.142671}`

### `v2_2026-08-05_12-05-23` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-17591d46791a`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7566.044,"command_to_response_ms":30867.6,"handle_lookup_ms":4.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":11528.687,"generator_create_ms":4.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":650.035,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.611,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.611,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.983,"pre_sampler_ms":12858.105,"restore_total_ms":3976.774,"sampler_ms":3696.091,"snapshot_callback_age_at_restore_ms":102389.725,"snapshot_callback_to_command_start_ms":94881.205,"submission_to_first_remote_event_ms":11529.629,"submit2entry_ms":11155.135,"t3b_to_t8_ms":18185.627,"vae_decode_ms":700.417,"wall_ms":30458.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.721ms unaccounted"]`
- Waterfall stages: `{"application_restore":3976.781509,"captured_timeline_gap":1.721428000000742,"clip_to_sampler_node":445.133,"first_node_to_clip":670.116,"local_preparation":405.610624,"modal_handle_submission":12.001476,"modal_scheduling":7148.431676,"output_persistence":259.0148,"post_sampling_transition":661.883003,"prompt_executor_cache_setup":3943.066,"remote_local_return":15.99938,"remote_method_setup":650.05505,"remote_return_handoff":449.779271,"restore_to_method_entry":25.913752,"sampler_node_to_sampling":6199.567998,"sampling":5302.102793,"vae":700.41712}`

### `v2_2026-08-05_12-06-33` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-3dd3ed388486`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4273.614,"command_to_response_ms":19860.1,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5659.544,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":15.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":172.645,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.051,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.051,"unexplained_pre_remote_ms":5486.899,"worker_unattributed_ms":null},"output_collection_ms":11.473,"pre_sampler_ms":8277.325,"restore_total_ms":1368.473,"sampler_ms":3716.683,"snapshot_callback_age_at_restore_ms":168958.058,"snapshot_callback_to_command_start_ms":164686.205,"submission_to_first_remote_event_ms":5659.544,"submit2entry_ms":5278.78,"t3b_to_t8_ms":13552.628,"vae_decode_ms":626.622,"wall_ms":19468.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.032ms unaccounted"]`
- Waterfall stages: `{"application_restore":1368.483551,"captured_timeline_gap":1.0323519999983546,"clip_to_sampler_node":275.372,"first_node_to_clip":175.727,"local_preparation":388.051008,"modal_handle_submission":9.000892,"modal_scheduling":3876.561988,"output_persistence":237.986055,"post_sampling_transition":682.360476,"prompt_executor_cache_setup":550.059,"remote_local_return":15.999436,"remote_method_setup":172.674568,"remote_return_handoff":447.913023,"restore_to_method_entry":30.726543,"sampler_node_to_sampling":5868.247718,"sampling":5133.326014,"vae":626.622312}`

### `v2_2026-08-05_12-07-34` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-53dd63816919`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":5168.712,"command_to_response_ms":16035.2,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":16.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6318.272,"generator_create_ms":2.999,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":8.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":249.68,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.679,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.679,"unexplained_pre_remote_ms":6068.592,"worker_unattributed_ms":null},"output_collection_ms":9.779,"pre_sampler_ms":3642.96,"restore_total_ms":1296.458,"sampler_ms":3722.16,"snapshot_callback_age_at_restore_ms":231304.237,"snapshot_callback_to_command_start_ms":226139.205,"submission_to_first_remote_event_ms":6318.272,"submit2entry_ms":5898.962,"t3b_to_t8_ms":8822.574,"vae_decode_ms":607.303,"wall_ms":15436.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.945ms unaccounted"]`
- Waterfall stages: `{"application_restore":1296.757709,"captured_timeline_gap":0.9451529999987542,"clip_to_sampler_node":55.049,"first_node_to_clip":45.214,"local_preparation":594.678528,"modal_handle_submission":10.999372,"modal_scheduling":4563.03378,"output_persistence":212.674208,"post_sampling_transition":626.98401,"prompt_executor_cache_setup":356.537,"remote_local_return":12.997676,"remote_method_setup":249.708663,"remote_return_handoff":451.625675,"restore_to_method_entry":36.09277,"sampler_node_to_sampling":1789.241803,"sampling":5125.401807,"vae":607.302622}`

### `v2_2026-08-05_12-08-29` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-422012c4c60c`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":7658.918,"command_to_response_ms":20539.1,"handle_lookup_ms":3.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10114.246,"generator_create_ms":3.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":148.374,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.351,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.351,"unexplained_pre_remote_ms":9965.873,"worker_unattributed_ms":null},"output_collection_ms":11.541,"pre_sampler_ms":4518.381,"restore_total_ms":2451.061,"sampler_ms":3725.122,"snapshot_callback_age_at_restore_ms":287601.077,"snapshot_callback_to_command_start_ms":280866.205,"submission_to_first_remote_event_ms":10114.246,"submit2entry_ms":9737.459,"t3b_to_t8_ms":9791.368,"vae_decode_ms":625.384,"wall_ms":20148.8}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.130ms unaccounted"]`
- Waterfall stages: `{"application_restore":2451.064732,"captured_timeline_gap":1.1295459999964805,"clip_to_sampler_node":60.942,"first_node_to_clip":47.522,"local_preparation":386.351424,"modal_handle_submission":10.002176,"modal_scheduling":7262.564608,"output_persistence":223.493275,"post_sampling_transition":688.300747,"prompt_executor_cache_setup":400.413,"remote_local_return":11.9981,"remote_method_setup":148.393605,"remote_return_handoff":458.264662,"restore_to_method_entry":20.823802,"sampler_node_to_sampling":2597.428085,"sampling":5145.067827,"vae":625.384411}`

### `v2_2026-08-05_12-09-28` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-dcba423c6946`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4327.033,"command_to_response_ms":15669.6,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5619.286,"generator_create_ms":2.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":187.547,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.22,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.22,"unexplained_pre_remote_ms":5431.739,"worker_unattributed_ms":null},"output_collection_ms":11.238,"pre_sampler_ms":4315.579,"restore_total_ms":1232.957,"sampler_ms":3713.936,"snapshot_callback_age_at_restore_ms":344121.338,"snapshot_callback_to_command_start_ms":339811.205,"submission_to_first_remote_event_ms":5619.286,"submit2entry_ms":5206.765,"t3b_to_t8_ms":9407.231,"vae_decode_ms":612.504,"wall_ms":15267.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.905ms unaccounted"]`
- Waterfall stages: `{"application_restore":1232.970769,"captured_timeline_gap":2.9054529999993974,"clip_to_sampler_node":116.512,"first_node_to_clip":280.095,"local_preparation":399.22048,"modal_handle_submission":9.00262,"modal_scheduling":3918.809732,"output_persistence":240.849829,"post_sampling_transition":512.185341,"prompt_executor_cache_setup":270.582,"remote_local_return":12.999816,"remote_method_setup":187.571784,"remote_return_handoff":450.78001,"restore_to_method_entry":52.970549,"sampler_node_to_sampling":2277.919914,"sampling":5091.717134,"vae":612.503985}`

### `v2_2026-08-05_12-10-25` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-90adfdb6e3fb`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4125.326,"command_to_response_ms":16126.1,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5285.12,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":462.54,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.383,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.383,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":11.003,"pre_sampler_ms":4761.506,"restore_total_ms":1105.321,"sampler_ms":3749.703,"snapshot_callback_age_at_restore_ms":401057.346,"snapshot_callback_to_command_start_ms":396980.205,"submission_to_first_remote_event_ms":5285.12,"submit2entry_ms":4898.592,"t3b_to_t8_ms":9927.523,"vae_decode_ms":603.147,"wall_ms":15747.3}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.694ms unaccounted"]`
- Waterfall stages: `{"application_restore":1105.36215,"captured_timeline_gap":0.6941179999994347,"clip_to_sampler_node":55.827,"first_node_to_clip":36.764,"local_preparation":375.38272,"modal_handle_submission":8.99978,"modal_scheduling":3740.94326,"output_persistence":212.658987,"post_sampling_transition":587.965662,"prompt_executor_cache_setup":936.735,"remote_local_return":11.997084,"remote_method_setup":463.385993,"remote_return_handoff":453.447313,"restore_to_method_entry":50.248559,"sampler_node_to_sampling":2320.421329,"sampling":5162.159162,"vae":603.147467}`

### `v2_2026-08-05_12-11-22` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-b969d33d2dad`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `8` / `49152 MiB`
- Runtime fingerprint: `3408caf7f144020208d5f2d0`
- Container session: `3ea27242a5a34c6c`
- Modal task: `ta-01KZ8WTG7GP9GSGT49KXNYX51R`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-6mDOvfs76IgPoc3my6BGql`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":13725.131,"command_to_response_ms":32481.6,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":16824.037,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":1770.158,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.771,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.771,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":10.828,"pre_sampler_ms":8937.552,"restore_total_ms":2992.962,"sampler_ms":3732.006,"snapshot_callback_age_at_restore_ms":466795.499,"snapshot_callback_to_command_start_ms":453831.205,"submission_to_first_remote_event_ms":16824.037,"submit2entry_ms":16406.758,"t3b_to_t8_ms":14173.32,"vae_decode_ms":626.161,"wall_ms":32089.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.348ms unaccounted"]`
- Waterfall stages: `{"application_restore":2992.970995,"captured_timeline_gap":1.3476209999971616,"clip_to_sampler_node":77.395,"first_node_to_clip":75.264,"local_preparation":387.771392,"modal_handle_submission":10.000108,"modal_scheduling":13327.359764,"output_persistence":239.995818,"post_sampling_transition":625.670592,"prompt_executor_cache_setup":4080.131,"remote_local_return":12.000216,"remote_method_setup":1770.207639,"remote_return_handoff":461.447102,"restore_to_method_entry":83.422533,"sampler_node_to_sampling":2529.725308,"sampling":5180.687223,"vae":626.161705}`

### `v2_2026-08-05_12-15-06` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-3805ff4f93da`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `3a633540a54d49e4`
- Modal task: `ta-01KZ8XJKM7MM2AWFQY8WS4EF4R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":82576.186,"command_to_response_ms":98705.4,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":84639.974,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":15.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":15.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":1451.612,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":15.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.623,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.623,"unexplained_pre_remote_ms":"absent","worker_unattributed_ms":null},"output_collection_ms":8.353,"pre_sampler_ms":5920.369,"restore_total_ms":1992.308,"sampler_ms":3675.548,"snapshot_callback_age_at_restore_ms":37757.533,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":84639.974,"submit2entry_ms":84261.101,"t3b_to_t8_ms":11210.793,"vae_decode_ms":534.567,"wall_ms":98384.9}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.949ms unaccounted"]`
- Waterfall stages: `{"application_restore":1992.318153,"captured_timeline_gap":0.9490970000188099,"clip_to_sampler_node":3377.522,"first_node_to_clip":261.912,"local_preparation":316.622976,"modal_handle_submission":9.999924,"modal_scheduling":82249.563596,"output_persistence":215.260967,"post_sampling_transition":859.963391,"prompt_executor_cache_setup":189.905,"remote_local_return":10.999596,"remote_method_setup":1451.676498,"remote_return_handoff":1449.588507,"restore_to_method_entry":16.207108,"sampler_node_to_sampling":960.421049,"sampling":4807.964369,"vae":534.566665}`

### `v2_2026-08-05_12-17-23` / run `0`

- Classification: **EXCLUDED_SNAPSHOT_OR_RECAPTURE**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-125fd7a6e049`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":99698.083,"command_to_response_ms":111665.1,"handle_lookup_ms":2.002,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":100526.374,"generator_create_ms":2.002,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":67.179,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.773,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.773,"unexplained_pre_remote_ms":100459.195,"worker_unattributed_ms":null},"output_collection_ms":13.165,"pre_sampler_ms":5018.779,"restore_total_ms":797.169,"sampler_ms":3749.439,"snapshot_callback_age_at_restore_ms":46593.066,"snapshot_callback_to_command_start_ms":null,"submission_to_first_remote_event_ms":100526.374,"submit2entry_ms":100118.236,"t3b_to_t8_ms":10613.333,"vae_decode_ms":728.34,"wall_ms":111266.5}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.547ms unaccounted"]`
- Waterfall stages: `{"application_restore":797.176742,"captured_timeline_gap":2.547416000001249,"clip_to_sampler_node":72.721,"first_node_to_clip":49.078,"local_preparation":394.77344,"modal_handle_submission":9.00156,"modal_scheduling":99294.308008,"output_persistence":265.805039,"post_sampling_transition":839.011179,"prompt_executor_cache_setup":768.558,"remote_local_return":11.99944,"remote_method_setup":67.204759,"remote_return_handoff":454.701874,"restore_to_method_entry":24.739794,"sampler_node_to_sampling":2459.495634,"sampling":5425.660131,"vae":728.340224}`

### `v2_2026-08-05_12-19-55` / run `0`

- Classification: **FINAL_SELECTED_VALID**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-6bf8554b91a1`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4780.802,"command_to_response_ms":30457.6,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":6798.853,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":72.743,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.145,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.145,"unexplained_pre_remote_ms":6726.11,"worker_unattributed_ms":null},"output_collection_ms":11.91,"pre_sampler_ms":17562.224,"restore_total_ms":1998.51,"sampler_ms":3718.428,"snapshot_callback_age_at_restore_ms":103775.425,"snapshot_callback_to_command_start_ms":99025.785,"submission_to_first_remote_event_ms":6798.853,"submit2entry_ms":6420.952,"t3b_to_t8_ms":23103.177,"vae_decode_ms":755.237,"wall_ms":30072.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.411ms unaccounted"]`
- Waterfall stages: `{"application_restore":1998.521263,"captured_timeline_gap":2.4105059999965306,"clip_to_sampler_node":3393.654,"first_node_to_clip":131.327,"local_preparation":380.145472,"modal_handle_submission":10.999828,"modal_scheduling":4389.657068,"output_persistence":264.302847,"post_sampling_transition":790.48129,"prompt_executor_cache_setup":313.401,"remote_local_return":15.001472,"remote_method_setup":72.769517,"remote_return_handoff":460.485742,"restore_to_method_entry":29.761289,"sampler_node_to_sampling":12069.849089,"sampling":5379.606863,"vae":755.236826}`

### `v2_2026-08-05_12-21-04` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-c0297e7d0fe0`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4811.969,"command_to_response_ms":16755.9,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5980.605,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":6.999,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":142.942,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.994,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.994,"unexplained_pre_remote_ms":5837.663,"worker_unattributed_ms":null},"output_collection_ms":10.863,"pre_sampler_ms":4939.82,"restore_total_ms":1121.176,"sampler_ms":3823.396,"snapshot_callback_age_at_restore_ms":173087.318,"snapshot_callback_to_command_start_ms":168383.785,"submission_to_first_remote_event_ms":5980.605,"submit2entry_ms":5573.507,"t3b_to_t8_ms":10198.568,"vae_decode_ms":634.334,"wall_ms":16366.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.454ms unaccounted"]`
- Waterfall stages: `{"application_restore":1121.250433,"captured_timeline_gap":1.4544199999982084,"clip_to_sampler_node":111.234,"first_node_to_clip":76.732,"local_preparation":385.994432,"modal_handle_submission":8.999168,"modal_scheduling":4416.975104,"output_persistence":222.508586,"post_sampling_transition":566.76754,"prompt_executor_cache_setup":814.583,"remote_local_return":12.0004,"remote_method_setup":142.979044,"remote_return_handoff":451.606506,"restore_to_method_entry":33.246812,"sampler_node_to_sampling":2464.09687,"sampling":5291.095649,"vae":634.333636}`

### `v2_2026-08-05_12-22-01` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-e0739c6ae05e`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `3a633540a54d49e4`
- Modal task: `ta-01KZ8XJKM7MM2AWFQY8WS4EF4R`
- Cloud/region: `CLOUD_PROVIDER_GCP` / `us-east4`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":6972.768,"command_to_response_ms":16978.1,"handle_lookup_ms":3.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":8475.995,"generator_create_ms":3.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":16.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":206.847,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.604,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.604,"unexplained_pre_remote_ms":8269.148,"worker_unattributed_ms":null},"output_collection_ms":9.126,"pre_sampler_ms":2539.85,"restore_total_ms":1511.459,"sampler_ms":3702.539,"snapshot_callback_age_at_restore_ms":376723.759,"snapshot_callback_to_command_start_ms":369890.799,"submission_to_first_remote_event_ms":8475.995,"submit2entry_ms":8104.418,"t3b_to_t8_ms":7848.423,"vae_decode_ms":512.228,"wall_ms":16589.0}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.079ms unaccounted"]`
- Waterfall stages: `{"application_restore":1511.467103,"captured_timeline_gap":1.079236999994464,"clip_to_sampler_node":91.305,"first_node_to_clip":80.958,"local_preparation":385.603584,"modal_handle_submission":10.000416,"modal_scheduling":6577.164,"output_persistence":197.77099,"post_sampling_transition":890.43893,"prompt_executor_cache_setup":402.928,"remote_local_return":12.998768,"remote_method_setup":206.885564,"remote_return_handoff":414.506313,"restore_to_method_entry":12.775691,"sampler_node_to_sampling":734.918877,"sampling":4935.115893,"vae":512.228402}`

### `v2_2026-08-05_12-23-13` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-91a21b3ff699`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":3905.057,"command_to_response_ms":16710.2,"handle_lookup_ms":2.0,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":4742.578,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":49.943,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.258,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.258,"unexplained_pre_remote_ms":4692.635,"worker_unattributed_ms":null},"output_collection_ms":10.949,"pre_sampler_ms":6196.867,"restore_total_ms":872.301,"sampler_ms":3719.976,"snapshot_callback_age_at_restore_ms":300864.083,"snapshot_callback_to_command_start_ms":296960.785,"submission_to_first_remote_event_ms":4742.578,"submit2entry_ms":4359.492,"t3b_to_t8_ms":11389.532,"vae_decode_ms":612.59,"wall_ms":16273.1}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.714ms unaccounted"]`
- Waterfall stages: `{"application_restore":872.321035,"captured_timeline_gap":1.7138860000013665,"clip_to_sampler_node":199.762,"first_node_to_clip":480.405,"local_preparation":433.258112,"modal_handle_submission":9.000388,"modal_scheduling":3462.79814,"output_persistence":255.184359,"post_sampling_transition":591.039366,"prompt_executor_cache_setup":530.406,"remote_local_return":12.998212,"remote_method_setup":49.965033,"remote_return_handoff":459.584193,"restore_to_method_entry":22.361977,"sampler_node_to_sampling":3618.496252,"sampling":5098.34596,"vae":612.590999}`

### `v2_2026-08-05_12-24-09` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-f98c5c2d8b86`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":30611.282,"command_to_response_ms":41888.8,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":31708.465,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":6.584,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":123.361,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.857,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.857,"unexplained_pre_remote_ms":31585.104,"worker_unattributed_ms":null},"output_collection_ms":12.555,"pre_sampler_ms":4434.488,"restore_total_ms":1048.634,"sampler_ms":3702.433,"snapshot_callback_age_at_restore_ms":383560.655,"snapshot_callback_to_command_start_ms":352969.785,"submission_to_first_remote_event_ms":31708.465,"submit2entry_ms":31315.393,"t3b_to_t8_ms":9589.961,"vae_decode_ms":615.909,"wall_ms":41500.6}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.051ms unaccounted"]`
- Waterfall stages: `{"application_restore":1048.675752,"captured_timeline_gap":2.0510360000043875,"clip_to_sampler_node":60.164,"first_node_to_clip":49.922,"local_preparation":384.857152,"modal_handle_submission":8.584748,"modal_scheduling":30217.840084,"output_persistence":233.128423,"post_sampling_transition":592.452019,"prompt_executor_cache_setup":753.205,"remote_local_return":16.001048,"remote_method_setup":123.568781,"remote_return_handoff":459.783715,"restore_to_method_entry":46.843823,"sampler_node_to_sampling":2155.629969,"sampling":5120.231594,"vae":615.909304}`

### `v2_2026-08-05_12-25-32` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-0c97bcd44272`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":8638.369,"command_to_response_ms":19606.0,"handle_lookup_ms":2.999,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":9920.399,"generator_create_ms":2.0,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.002,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":97.39,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.445,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.445,"unexplained_pre_remote_ms":9823.01,"worker_unattributed_ms":null},"output_collection_ms":12.196,"pre_sampler_ms":3981.353,"restore_total_ms":1226.582,"sampler_ms":3729.551,"snapshot_callback_age_at_restore_ms":444462.343,"snapshot_callback_to_command_start_ms":435843.785,"submission_to_first_remote_event_ms":9920.399,"submit2entry_ms":9522.837,"t3b_to_t8_ms":9112.513,"vae_decode_ms":606.059,"wall_ms":19212.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 2.269ms unaccounted"]`
- Waterfall stages: `{"application_restore":1226.599555,"captured_timeline_gap":2.2687970000006317,"clip_to_sampler_node":69.281,"first_node_to_clip":43.462,"local_preparation":390.444992,"modal_handle_submission":9.001508,"modal_scheduling":8238.92246,"output_persistence":226.31272,"post_sampling_transition":555.691281,"prompt_executor_cache_setup":535.089,"remote_local_return":12.998356,"remote_method_setup":97.437918,"remote_return_handoff":465.77448,"restore_to_method_entry":54.305329,"sampler_node_to_sampling":1956.656108,"sampling":5115.672634,"vae":606.058118}`

### `v2_2026-08-05_12-27-01` / run `0`

- Classification: **FINAL_SELECTED_TRIMMED**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-afa32022fa3d`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":4857.59,"command_to_response_ms":15291.9,"handle_lookup_ms":2.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":5809.382,"generator_create_ms":2.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":0.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":0.0,"local_receive_to_generator_create_start_ms":7.0,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":190.611,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":0.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.801,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.801,"unexplained_pre_remote_ms":5618.771,"worker_unattributed_ms":null},"output_collection_ms":10.739,"pre_sampler_ms":3729.963,"restore_total_ms":902.789,"sampler_ms":3725.145,"snapshot_callback_age_at_restore_ms":530181.08,"snapshot_callback_to_command_start_ms":525333.785,"submission_to_first_remote_event_ms":5809.382,"submit2entry_ms":5406.921,"t3b_to_t8_ms":8820.121,"vae_decode_ms":596.809,"wall_ms":14901.7}`
- Waterfall warnings: `["captured residual excluded from accounted: 1.454ms unaccounted"]`
- Waterfall stages: `{"application_restore":902.797616,"captured_timeline_gap":1.4536260000022594,"clip_to_sampler_node":64.389,"first_node_to_clip":54.855,"local_preparation":386.801216,"modal_handle_submission":9.000684,"modal_scheduling":4461.788436,"output_persistence":229.518391,"post_sampling_transition":528.52134,"prompt_executor_cache_setup":460.698,"remote_local_return":18.084148,"remote_method_setup":190.688952,"remote_return_handoff":468.341018,"restore_to_method_entry":40.325589,"sampler_node_to_sampling":1779.779593,"sampling":5098.075726,"vae":596.808513}`

### `v2_2026-08-05_12-28-00` / run `0`

- Classification: **UNSELECTED_NON_SNAPSHOT_PROVISIONAL_OR_POST_SNAPSHOT**
- Files: `run_0.json`, `summary.json`
- Request ID: `v2-benchmark-0-9fdfe8fb9b06`
- Policy/order: `TBASE` / `O0`
- CPU/memory: `16` / `40960 MiB`
- Runtime fingerprint: `d3d147928a093a3a1451c142`
- Container session: `8d677b3c51bc4dd9`
- Modal task: `ta-01KZ8XPSBCP5AJ191TR97B14RR`
- Cloud/region: `CLOUD_PROVIDER_AWS` / `us-east-2`
- Image: `im-0RiJLogpG7DqZ6TWcCiNwT`
- Observed runtime status: `baseline_passthrough`; requested-vs-actual match: `True`
- Event types: ``
- Timing JSON: `{"command_start_to_restore_start_ms":9559.326,"command_to_response_ms":20105.7,"handle_lookup_ms":3.001,"local_timing":{"active_profile_ms":0.0,"clock_reconciliation_residual_ms":0.0,"first_iteration_to_first_remote_event_ms":10482.008,"generator_create_ms":3.001,"generator_create_to_first_iteration_ms":0.0,"generator_created_to_first_iteration_ms":0.0,"handle_lookup_ms":0.0,"local_body_read_ms":null,"local_json_parse_ms":null,"local_preflight_ms":null,"local_queue_enqueue_ms":null,"local_queue_lock_wait_ms":null,"local_receive_to_actual_submission_ms":16.0,"local_receive_to_enqueue_ms":null,"local_receive_to_generator_create_ms":16.0,"local_receive_to_generator_create_start_ms":7.001,"local_residual_ms":0.0,"missing_stages":["local_receive_to_enqueue_ms"],"modal_method_entry_to_executor_ms":51.732,"overlap_error":"","payload_materialization_ms":0.0,"payload_serialize_ms":0.0,"payload_size_measurement_ms":0.0,"plan_build_ms":16.0,"queue_wait_before_worker_ms":null,"reconciliation_status":"incomplete","remote_python_resume_to_restore_start_ms":"absent","restore_end_to_modal_method_entry_ms":"absent","restore_method_ms":"absent","restore_plan_build_ms":0.0,"restore_publish_ms":0.0,"route_unattributed_ms":null,"stage_attribution_residual_ms":{"missing_stages":["local_receive_to_enqueue_ms"],"overlap_error":"","reconciliation_status":"incomplete","route_unattributed_ms":null,"worker_unattributed_ms":null},"submission_to_remote_python_resume_ms":"absent","t0_to_t1_ms":0.603,"t1_to_queue_enqueue_ms":null,"trigger_to_local_receive_ms":0.603,"unexplained_pre_remote_ms":10430.276,"worker_unattributed_ms":null},"output_collection_ms":11.071,"pre_sampler_ms":4020.356,"restore_total_ms":894.046,"sampler_ms":3712.472,"snapshot_callback_age_at_restore_ms":593166.683,"snapshot_callback_to_command_start_ms":583720.785,"submission_to_first_remote_event_ms":10482.008,"submit2entry_ms":10097.517,"t3b_to_t8_ms":9090.612,"vae_decode_ms":606.703,"wall_ms":19716.2}`
- Waterfall warnings: `["captured residual excluded from accounted: 0.694ms unaccounted"]`
- Waterfall stages: `{"application_restore":894.118684,"captured_timeline_gap":0.6937550000002375,"clip_to_sampler_node":68.217,"first_node_to_clip":43.907,"local_preparation":385.6032,"modal_handle_submission":10.0012,"modal_scheduling":9163.721936,"output_persistence":225.900678,"post_sampling_transition":515.155149,"prompt_executor_cache_setup":519.174,"remote_local_return":15.997928,"remote_method_setup":52.01368,"remote_return_handoff":459.276981,"restore_to_method_entry":36.64126,"sampler_node_to_sampling":2024.258633,"sampling":5084.280786,"vae":606.702258}`

## Reproduction notes for the next agent

1. Use only the artifact sets explicitly marked `FINAL_SELECTED_VALID` or `FINAL_SELECTED_TRIMMED` when reproducing the reported result.
2. Do not mix historical gap-zero artifacts into the final comparison.
3. If a new snapshot is captured, discard that run and its immediate post-snapshot run before counting valid runs.
4. Keep the manual Windows 25-second sleep between every invocation.
5. Preserve both `modal_scheduling` and `t3b_to_t8_ms`; the latter is the deciding metric for this report.

## Raw artifact authority

This report is generated from structured JSON artifacts. The raw `summary.json` and `run_N.json` files remain the authoritative logs for fields not reproduced inline here. No raw stdout was fabricated or silently omitted; unavailable fields are represented as missing in the per-artifact record.
