# Runtime migration port map

Resolved against the current checkout (`fe05aa7eadd06281ca8501a19aa38065fbd5999f`).
The current checkout equals the audit anchor; no new destination module exists
yet. Caller lists are direct production/test references, with `(+N)` indicating
additional files listed in the verifier report.

| Old file/symbol | Current callers | New destination | Port/adapt/rewrite/retain | Reason | Protecting test | Status |
|---|---|---|---|---|---|---|
| comfyapp.py: Modal app, image, Volume, runtime config | Modal module + packaging tests | `deployment_spec.py`; `modal_app.py` | rewrite | one deterministic deployment source | `test_comfyapp_packaging.py`; `test_comfyapp_build_context.py` | exists; callers verified; tests mapped |
| `_add_comfymodal_local_python_sources` | `comfyapp.py`; 2 packaging tests | `deployment_spec.py` | adapt | manifest-driven source inclusion | `test_comfyapp_packaging.py`; `test_image_packaging_refactor.py` | exists; callers verified; tests mapped |
| `_register_gpu_classes` | diagnostics test | `deployment_spec.py`; `modal_app.py` | port | preserve GPU resolution | `test_audit_round8_diagnostics.py` | exists; callers verified; tests mapped |
| `_ComfyAPIMixin` | `comfyapp.py`; 7 runtime/AST tests | `modal_app.py`; runtime modules | adapt | thin Modal facade | `test_comfyapp_runtime_state.py`; `test_safety_architecture.py` (+5) | exists; callers verified; tests mapped |
| `_ensure_models_symlink` | only internal `comfyapp.py` callers | `runtime_bootstrap.py` | port | preserve model path setup | no dedicated test | exists; caller verified; test gap |
| `_sync_custom_nodes_from_volume` | internal; volume lifecycle test | `runtime_bootstrap.py` | adapt | preserve custom-node compatibility | `test_comfyapp_volume_lifecycle.py` | exists; callers verified; tests mapped |
| `_install_custom_node_requirements` | internal; 3 runtime/safety tests | deployment image; explicit diagnostics | rewrite | no normal-startup pip install | `test_comfyapp_runtime_state.py`; `test_comfyapp_volume_lifecycle.py`; `test_safety_architecture.py` | exists; callers verified; tests mapped |
| `_start_backend` | internal; auto-warmup test | `runtime_bootstrap.py` | port | preserve backend startup | `test_comfyapp_auto_warmup.py` | exists; callers verified; tests mapped |
| `_start_in_process_backend` | internal; 2 preload/production tests | `runtime_bootstrap.py`; `runtime_executor.py` | port | direct executor startup | `test_comfyapp_auto_warmup.py`; `test_production_phase3b1.py` | exists; callers verified; tests mapped |
| `startup @modal.enter(snap=True)` | Modal lifecycle only | `modal_app.py`; `runtime_bootstrap.py` | adapt | CPU snapshot lifecycle | new lifecycle AST test required | exists; caller verified; test gap |
| `restore @modal.enter(snap=False)` | Modal lifecycle only | `modal_app.py`; `runtime_bootstrap.py` | adapt | GPU restore lifecycle | new lifecycle AST test required | exists; caller verified; test gap |
| `_restore_in_process_gpu_state` | 3 runtime/restore tests | `runtime_bootstrap.py` | port | preserve GPU restore | `test_comfyapp_auto_warmup.py`; `test_comfyapp_volume_lifecycle.py`; `test_restore_ordering_root_cause.py` | exists; callers verified; tests mapped |
| `_initialize_cuda_context` | patch test | `runtime_bootstrap.py` | port | preserve CUDA initialization | `test_v2_16_20_patch.py` | exists; caller verified; tests mapped |
| `_apply_sage_attention_policy` | 2 runtime/volume tests | `model_preload.py` | adapt | measured runtime policy | `test_comfyapp_auto_warmup.py`; `test_comfyapp_volume_lifecycle.py`; `test_sageattention_restore_policy.py` | exists; callers verified; tests mapped |
| `_execute_in_process` | trace + 8 audit/runtime/production tests | `runtime_executor.py` | port | one in-process executor | `test_comfyapp_runtime_state.py`; `test_production_phase3a.py` (+7) | exists; callers verified; tests mapped |
| `_collect_outputs` | runtime + production tests | `output_delivery.py` | adapt | explicit strategy chain | `test_comfyapp_runtime_state.py`; `test_production_phase3a.py`; new active output test required | exists; callers verified; coverage gap |
| `run_prompt_stream` | `canonical_execution.py`, `comparison.py`, `experiment_runner.py`, `studio_run_adapter.py`, `__init__.py`, probes | `modal_app.py`; `modal_transport.py` | adapt | preserve central stream seam | `test_canonical_execution.py`; `test_studio_runtime.py` (+18) | exists; callers verified; tests mapped |
| checkpoint/experiment streaming entrypoint | `experiment_runner.py`, `experiment_service.py`, `__init__.py` | `modal_app.py`; `modal_transport.py` | retain/adapt | checkpoint compatibility | `test_experiment_runner.py` | exists; callers verified; tests mapped |
| `set_active_warmup_profile` (remote) | `canonical_execution.py`, `experiment_runner.py`, `modal_client.py`, Studio, `__init__.py` | `restore_plan.py`; `modal_app.py` | rewrite | authoritative RestorePlan publication | `test_warmup_profile_dedup.py`; `test_restore_timing_data_flow.py` | exists; callers verified; tests mapped |
| `_commit_runtime_config_vol_async` | runtime state + volume lifecycle tests | `runtime_state.py` | rewrite | one serialized coordinator | `test_comfyapp_runtime_state.py`; `test_comfyapp_volume_lifecycle.py`; new concurrency test required | exists; callers verified; coverage gap |
| restore-background UNET methods/futures | internal `comfyapp.py`; preload tests | `model_preload.py` | rewrite | measured two-lane coordinator | `test_comfyapp_preload_state_machine.py`; new coordinator test required | exists; caller verified; coverage gap |
| CLIP loader and CLIPTextEncode wrappers | internal `comfyapp.py` | `model_preload.py` | port/adapt | exact-prompt prefill and reuse | `test_production_baseline.py`; `test_optimizations.py` | exists; caller verified; tests mapped |
| production output sink classes | `canonical_execution.py`, `production_workflow.py`, phase/latency tests | `output_delivery.py` | port | preserve production output | `test_production_phase3b1.py`; `test_production_workflow.py` (+7) | exists; callers verified; tests mapped |
| production Image Comparer output class | `canonical_execution.py`, `production_workflow.py`, comparer tests | `output_delivery.py` | port | preserve A/B and B-primary semantics | `test_production_workflow.py`; `test_restore_ordering_root_cause.py` | exists; callers verified; tests mapped |
| output conversion/packaging helpers | `__init__.py`, `comfyapp.py`, converter/saver tests | `output_delivery.py`; `result_delivery.py` | adapt | correct MIME and byte accounting | `test_modal_output_materialization.py`; `test_output_saver_paths.py`; new active output test required | exists; callers verified; coverage gap |
| `canonical_execution.RunTrace` | `__init__.py`, `experiment_runner.py`, `studio_run_adapter.py` | `trace.py` | adapt | one event trace with serializers | `test_canonical_execution.py`; `test_studio_runtime.py` | exists; callers verified; tests mapped |
| `canonical_execution.prepare_modal_execution` | `__init__.py`, Studio, experiment runner | `contracts.py`; `canonical_execution.py` | rewrite | build one immutable plan | `test_canonical_execution.py`; `test_studio_direct_run.py` | exists; callers verified; tests mapped |
| `canonical_execution.execute_modal_prompt` | `__init__.py`, Studio, experiment runner | `canonical_execution.py` | rewrite | one execution service | `test_canonical_execution.py`; `test_studio_direct_run.py`; `test_studio_runtime.py` | exists; callers verified; tests mapped |
| `warmup_profile.prepare_active_next_profile` | `canonical_execution.py`, Studio, `__init__.py` | `restore_plan.py` | rewrite | split model/prefill identity | `test_warmup_profile_dedup.py`; `test_production_baseline.py` (+4) | exists; callers verified; tests mapped |
| `modal_client.run_prompt_stream` | canonical, experiment, Studio, `__init__.py` | `modal_transport.py` | adapt | transport only | `test_modal_client_workspaces.py`; `test_modal_client_gpu_config.py` (+many) | exists; callers verified; tests mapped |
| `modal_client.run_checkpoint_stream` | experiment runner/service; `__init__.py` | `modal_transport.py` | retain/adapt | checkpoint RPC compatibility | `test_experiment_runner.py` | exists; callers verified; tests mapped |
| `modal_client.validate_production_dispatch` | self + canonical/production tests | `contracts.py`; `canonical_execution.py` | move | validate once locally | `test_canonical_execution.py`; `test_production_dispatch_plan.py`; `test_production_plan_fix.py` | exists; callers verified; tests mapped |
| `modal_client.set_active_warmup_profile` (client wrapper) | canonical/Studio/warmup callers | `restore_plan.py`; `modal_transport.py` | adapt | keep remote lookup in transport | `test_modal_runtime_routes.py`; `test_warmup_profile_dedup.py` | exists; callers verified; tests mapped |
| `__init__.py` prompt interception/execution | `_execute_job` → `execute_modal_prompt` | `canonical_execution.py`; `result_delivery.py` | adapt | integration shell only | `test_output_contract.py`; `test_studio_direct_run.py`; `test_studio_runtime.py` | exists; callers verified; tests mapped |
| `__init__.py` local result materialization | `_materialize_modal_outputs`, `_materialize_experiment_output` | `result_delivery.py` | move | one local materializer | `test_modal_output_materialization.py`; `test_local_artifacts.py` | exists; callers verified; tests mapped |
| `__init__.py` deployment worker/routes | `_run_deploy_background`; deployment routes | `deployment_service.py`; `modal_app.py` | move | deployment separate from execution | `test_deploy_state_bookkeeping.py`; `test_deploy_no_auto_generation.py` (+3) | exists; callers verified; tests mapped |
| Studio direct Playground run | `build_single_run_spec` → `execute_modal_prompt` | `playground_service.py` | rewrite | bypass experiment machinery | `test_studio_direct_run.py`; `test_studio_runtime.py`; new service test required | exists; callers verified; coverage gap |
| Studio experiment run | adapter scheduler path | `studio_run_adapter.py` | adapt | same plan boundary, preserve scheduler | `test_studio_runtime.py`; `test_experiment_runner.py` | exists; callers verified; tests mapped |
| control-schema derivation | adapter schema helpers | `playground_service.py`; adapter | retain/adapt | preserve exposed controls | `test_studio_runtime.py` | exists; callers verified; tests mapped |
| preset/snapshot normalization/repair | `_repair_missing_clip_inputs`, `_repair_missing_vae_inputs` | `playground_service.py`; adapter | retain/adapt | compatibility repair | `test_studio_runtime.py` | exists; callers verified; tests mapped |
| adapter calls into canonical execution | direct + experiment paths | `playground_service.py`; `canonical_execution.py` | rewrite | shared execution service | `test_studio_direct_run.py`; `test_studio_runtime.py` | exists; callers verified; tests mapped |
| experiment remote invocation boundary | adapter → execution/transport | `studio_run_adapter.py`; `modal_transport.py` | adapt | preserve remote boundary | `test_studio_runtime.py` | exists; callers verified; tests mapped |
| checkpoint-level Modal RPC | experiment flow → `run_checkpoint_stream` | `modal_transport.py` | retain/adapt | distinct checkpoint semantics | `test_experiment_runner.py` | exists; callers verified; tests mapped |

## Required focused tests before integration

- Output strategy chain: MIME, raw/base64/JSON byte accounting, comparer A/B,
  multi-output, conversion failure, and constrained fallbacks.
- Remote-authoritative RestorePlan publication: unchanged no-write, prompt-only
  prefill change, model change, and serialized concurrent writes.
- Modal lifecycle decorators and runtime bootstrap ordering.
- New result materialization and direct Playground service.

## Historical comparison targets

- Audit anchor: `fe05aa7eadd06281ca8501a19aa38065fbd5999f`.
- Root backup and `before_v2_*` artifacts are archived references; their hashes
  and tracked state are in `FILE_HASHES.json`.

## Writer ownership

- Main lane only: `contracts.py`, `trace.py`, `runtime_bootstrap.py`,
  `model_preload.py`, `modal_app.py`, `comfyapp.py`, `__init__.py`,
  `canonical_execution.py`, and `modal_client.py`.
- Deployment/state lane: new `deployment_spec.py`, `runtime_state.py`, and
  `restore_plan.py` only.
- Output lane: new `output_delivery.py` and `result_delivery.py` only.
- Studio lane: new `playground_service.py`, `studio_run_adapter.py`, and
  `studio_routes.py` only.

The existing uncommitted telemetry/reference work is protected in place. No
stash, reset, clean, overwrite, or discard operation is permitted.
