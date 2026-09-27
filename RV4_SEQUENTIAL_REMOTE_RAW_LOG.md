# RV4 Sequential Remote Optimization Raw LogCampaign start HEAD: `81a29b3c7faea2a2579370796755fde4c1b6a728`Branch: `TESTING2`All command output, remote receipts, telemetry, invalid attempts, and countedruns are appended below in execution order. No run is counted from summarytext alone.## Preflight- Profile-bound expected PNG SHA: `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`- Operations-skill expected PNG SHA: `454dbda2939f4abadabd8ca6c524d3a615f384ce19873faf5adaf4693c1848da`- Current profile used as v2ctl authority; discrepancy retained for audit.## A0 legacy baseline status/doctor## A1 legacy baseline deploy (exit=)## A1 legacy baseline deploy retrypython.exe : ERROR: deploy lock exists and appears stale (pid dead on this host, or a foreign-host lock older than 6h); pass --force to replace it explicitly - v2ctl never steals locks silentlyAt line:1 char:123+ ... y retry`n"; & python tools/v2ctl.py golden deploy --app batch-rv4-leg ...+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    + CategoryInfo          : NotSpecified: (ERROR: deploy l... locks silently:String) [], RemoteException    + FullyQualifiedErrorId : NativeCommandError ## A1b supported stale-lock recovery (confirmed owner=golden-p1, pid=22580 dead, target=batch-rv4-legacy)python.exe : force release of deploy lock C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deploy.lock requested by v2ctl (previous owner=golden-p1 pid=22580 host=DESKTOP-IK4CEAD)At line:1 char:194+ ... 4-legacy)`n"; & python tools/v2ctl.py lock force-release 2>&1 | Tee-O ...+                   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    + CategoryInfo          : NotSpecified: (force release o...ESKTOP-IK4CEAD):String) [], RemoteException    + FullyQualifiedErrorId : NativeCommandError force-released## A1c legacy baseline deploy retry after supported lock release[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8f[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-legacy[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-164155_ac188fad.json[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_1_ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8f.json## A2 legacy source-probe[v2.modal_target] app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0[v2ctl.source-probe] profile=golden_p1[v2ctl.source-probe] git_head=81a29b3c7fae[v2ctl.source-probe] target app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-is35jL0nzPJHSR0sZQz0YX container=0905d3cfa2424c0e[v2ctl.source-probe] remote deployment_combined_hash=3e403015097edda1[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True[v2ctl.source-probe] verdict=MATCH[v2ctl.source-probe] RESULT=PASS source_identity=MATCH## A3 legacy post-deploy status/doctor[v2ctl.golden.status]schema_version=2profile=golden_p1target={'app': 'batch-rv4-legacy', 'class': 'ModalRuntimeEntrypointV2', 'method': 'run_golden_serial_stream'}deployment_manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-164155_ac188fad.jsondeployment_fingerprint_current=ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8fdeployment_fingerprint_stored=ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8fdeployment_fingerprint_match=Truedeployment_target_match=Truedeployed_state_present=Truedeployed_state_target_match=Falsedeployed_state_app=batch-ra2-active-patcherdeployed_state_class=ModalRuntimeEntrypointV2deployed_state_combined_hash=d25161544d2d2d7461d32a1b2f99ea381c6cf7a108d3c9b2481037192fbeac96deployed_state_error=runtime_health_status=unverifiedsource_identity_status=unverifiedruntime_overrides_present=0deploy_lock_active=Falsecapture_guard={'schema_version': 2, 'state': 'idle', 'post_capture_guard_pending': False, 'last_snapshot_capture_request_id': '', 'last_snapshot_capture_at': '', 'guard_armed_by_request_id': '', 'last_guard_consumed_by_request_id': '', 'last_guard_consumed_at': '', 'capture_identity': '', 'capture_request_id': '', 'capture_at': '', 'deployment_identity': '{"app_name":"batch-rv4-legacy","class_name":"ModalRuntimeEntrypointV2","deploy_fingerprint":"ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8f","deployment_combined_hash":"ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8f","gpu":"rtx-pro-6000"}', 'last_transition_reason': 'initial'}next_request_guarded=Falseremote_checks=not_performedready=False[v2ctl.doctor]git.head=81a29b3c7faea2a2579370796755fde4c1b6a728git.branch=TESTING2git.dirty=1python=3.11.9profile=golden_p1target.app=batch-rv4-legacytarget.class=ModalRuntimeEntrypointV2target.method=run_golden_serial_streambackend.deploy_and_run_v2_single.exists=1 kind=combinedbackend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_envbackend.run_v2_single.exists=1 kind=runregistry.flags=119profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,productionruntime_override_policy=forbidruntime_overrides.present=0deploy.lock=nonedeployment.fingerprint.stored=ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8fdeployment.fingerprint.current=ac188fad7c416c50cff06b8bba2e5b60eb6b68ae60d32443123223a6ac51ef8fdeployment.fingerprint.match=1deployment.target.match=1[v2ctl.doctor] OK## A4 legacy diagnostic deployment (stage diagnostics ON)python.exe : [v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICSAt line:1 char:146+ ... ics ON)`n"; & python tools/v2ctl.py --profile golden_p1 --set COMFYMO ...+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    + CategoryInfo          : NotSpecified: ([v2ctl.deploy] ...AGE_DIAGNOSTICS:String) [], RemoteException    + FullyQualifiedErrorId : NativeCommandError [v2ctl.deploy] profile=golden_p1 deploy_fingerprint=ebd0cc9f3e35237161f2e545b1ef2a805856eaae1fb5fca0b516b7894e72fcc5[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-legacy[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-164449_ebd0cc9f.json[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_2_ebd0cc9f3e35237161f2e545b1ef2a805856eaae1fb5fca0b516b7894e72fcc5.json## A5 legacy diagnostic source-probe/status/doctor## A5 legacy diagnostic source-probe retry
## A6 legacy diagnostic source-probe retry after active-workspace capacity check
[v2.modal_target] app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-is35jL0nzPJHSR0sZQz0YX container=00e269f8d67e4ae9
[v2ctl.source-probe] remote deployment_combined_hash=3e403015097edda1
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
source_probe_exit=0

## A7 legacy diagnostic redeploy with reduced resources (cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-legacy
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-171730_f652390b.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_3_f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2.json

## A8 reduced-resource source-probe/status/doctor

[v2.modal_target] app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=165590154c6344fb
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.golden.status]
schema_version=2
profile=golden_p1
target={'app': 'batch-rv4-legacy', 'class': 'ModalRuntimeEntrypointV2', 'method': 'run_golden_serial_stream'}
deployment_manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-171730_f652390b.json
deployment_fingerprint_current=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2
deployment_fingerprint_stored=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2
deployment_fingerprint_match=True
deployment_target_match=True
deployed_state_present=True
deployed_state_target_match=False
deployed_state_app=batch-ra2-active-patcher
deployed_state_class=ModalRuntimeEntrypointV2
deployed_state_combined_hash=d25161544d2d2d7461d32a1b2f99ea381c6cf7a108d3c9b2481037192fbeac96
deployed_state_error=
runtime_health_status=unverified
source_identity_status=unverified
runtime_overrides_present=0
deploy_lock_active=False
capture_guard={'schema_version': 2, 'state': 'idle', 'post_capture_guard_pending': False, 'last_snapshot_capture_request_id': '', 'last_snapshot_capture_at': '', 'guard_armed_by_request_id': '', 'last_guard_consumed_by_request_id': '', 'last_guard_consumed_at': '', 'capture_identity': '', 'capture_request_id': '', 'capture_at': '', 'deployment_identity': '{"app_name":"batch-rv4-legacy","class_name":"ModalRuntimeEntrypointV2","deploy_fingerprint":"f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2","deployment_combined_hash":"f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2","gpu":"rtx-pro-6000"}', 'last_transition_reason': 'initial'}
next_request_guarded=False
remote_checks=not_performed
ready=False
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-legacy
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2
deployment.fingerprint.current=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
reduced_resource_probe_exit=0

## A9 legacy diagnostic mandatory warmup (NOT COUNTED; post-probe/post-snapshot guard)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2 run_fingerprint=b389417fe60d1f5ff9924394dfeac74c775067074cc07156229387b9dc033617
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-172219_b389417f.json
warmup_exit=0; counted=NO

## A10 legacy diagnostic counted-candidate attempt 1 (stage diagnostics ON)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2 run_fingerprint=b389417fe60d1f5ff9924394dfeac74c775067074cc07156229387b9dc033617
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-172310_b389417f.json
attempt_1_v2ctl_exit=0

## A11 legacy diagnostic counted-candidate attempt 2 (stage diagnostics ON)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2 run_fingerprint=b389417fe60d1f5ff9924394dfeac74c775067074cc07156229387b9dc033617
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-172839_b389417f.json
attempt_2_v2ctl_exit=0

## A12 legacy diagnostic counted-candidate attempt 3 (stage diagnostics ON)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2 run_fingerprint=b389417fe60d1f5ff9924394dfeac74c775067074cc07156229387b9dc033617
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-173221_b389417f.json
attempt_3_v2ctl_exit=0

## A13 legacy diagnostic counted-candidate attempt 4 (stage diagnostics ON)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=f652390b9ec2f80689b2881a3ba80cb094b02b36c3a67abe4cda1c5db61019e2 run_fingerprint=b389417fe60d1f5ff9924394dfeac74c775067074cc07156229387b9dc033617
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-173254_b389417f.json
attempt_4_v2ctl_exit=0

## A14 legacy clean-timing redeploy (stage diagnostics OFF; cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-legacy
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-173546_b8902be8.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_4_b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913.json

## A15 legacy clean-timing source-probe/status/doctor

[v2.modal_target] app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-legacy class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=8778429f1fc74dda
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-legacy
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913
deployment.fingerprint.current=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
clean_timing_deploy_probe_exit=0

## A16 legacy clean timing mandatory warmup (NOT COUNTED)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-173950_82e5b26b.json
clean_warmup_exit=0; counted=NO

## A17 legacy clean timing control 1 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174027_82e5b26b.json
control_1_exit=0

## A18 legacy clean timing control 2 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174103_82e5b26b.json
control_2_exit=0

## A19 legacy clean timing control 3 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174400_82e5b26b.json
control_3_exit=0

## A20 legacy clean timing control 4 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174439_82e5b26b.json
control_4_exit=0

## A21 legacy clean timing control 5 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174511_82e5b26b.json
control_5_exit=0

## A22 legacy clean timing control 6 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=b8902be8746eaac3d711a4476081a3cec5c7e738c5197643caffb3ecc0ef8913 run_fingerprint=82e5b26b567e12483ba66460ef8f60c336443390b28ab8e9d3b1b9351319766b
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-174549_82e5b26b.json
control_6_exit=0

## B1 dispatcher diagnostic deploy (stage diagnostics ON; cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-dispatcher
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-174805_8ef665c9.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_1_8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0.json

## B2 dispatcher diagnostic source-probe/status/doctor

[v2.modal_target] app=batch-rv4-dispatcher class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-dispatcher class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=c4135872242540ea
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-dispatcher
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0
deployment.fingerprint.current=8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
dispatcher_diag_deploy_probe_exit=0

## B3 dispatcher diagnostic mandatory warmup (NOT COUNTED)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0 run_fingerprint=a47d186027bd88c6d1f06bcfd6c2a2497a341d963f8f0a47e4a656e5cbd07536
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-175009_a47d1860.json
dispatcher_warmup_exit=0; counted=NO

## B4 dispatcher diagnostic smoke (stage diagnostics ON; structural gate candidate)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=8ef665c9d128d626005891c3a218604c92f67661527407ae95f5447847bcb0f0 run_fingerprint=a47d186027bd88c6d1f06bcfd6c2a2497a341d963f8f0a47e4a656e5cbd07536
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-175046_a47d1860.json
dispatcher_smoke_exit=0

## B5 dispatcher clean-timing redeploy (stage diagnostics OFF; cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-dispatcher
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-175253_6c6a100b.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_2_6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d.json

## B6 dispatcher clean-timing source-probe/doctor

[v2.modal_target] app=batch-rv4-dispatcher class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-dispatcher class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=93ecf60487454d2e
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-dispatcher
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d
deployment.fingerprint.current=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
dispatcher_clean_deploy_probe_exit=0

## B7 dispatcher clean timing mandatory warmup (NOT COUNTED)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-175822_2d389cfa.json
dispatcher_clean_warmup_exit=0; counted=NO

## B8 dispatcher clean timing test 1 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-175920_2d389cfa.json
dispatcher_1_exit=0

## B9 dispatcher clean timing test 2 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-175954_2d389cfa.json
dispatcher_2_exit=0

## B10 dispatcher clean timing test 3 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-180040_2d389cfa.json
dispatcher_3_exit=0

## B11 dispatcher clean timing test 4 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-180113_2d389cfa.json
dispatcher_4_exit=0

## B12 dispatcher clean timing test 5 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-180238_2d389cfa.json
dispatcher_5_exit=0

## B13 dispatcher clean timing test 6 of 6 (stage diagnostics OFF)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=6c6a100bb493bd3276107e856dfe9764af81282f7630265d74c91dcd3d34c47d run_fingerprint=2d389cfaf74cceec4035aef3c4e69cd4c1c2c278748b1f6b83ba7a895df60b3a
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-180321_2d389cfa.json
dispatcher_6_exit=0

## C1 BF16 diagnostic deploy (legacy QD winner; stage diagnostics ON; E31 forensics ON; cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-cast-bf16
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-180536_5b84743f.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_1_5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5.json

## C2 BF16 diagnostic source-probe/doctor

[v2.modal_target] app=batch-rv4-cast-bf16 class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-cast-bf16 class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=a3a0e8d8b680458a
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-cast-bf16
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5
deployment.fingerprint.current=5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
bf16_diag_deploy_probe_exit=0

## C3 FP32 cast-once diagnostic deploy (legacy QD winner; stage diagnostics ON; E31 forensics ON; cpu=4, memory_mb=16384)

[v2ctl.deploy] WARNING: unregistered explicit flags are not admission metadata; they will be recorded but require exact receipt proof for later bound requests: COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=3fa61f017c6ec81813044eb5936b698056c76ad348cbd28f029c3350343d8b7c
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv4-cast-once
[custom_nodes.publish] decision=skip_exact reason=exact_match generation=b7b8506ae881 schema=2 policy=1
[v2ctl.deploy] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\deploy_20260831-180736_3fa61f01.json
[v2ctl.deploy] deployment_receipt=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\deployments\receipt_1_3fa61f017c6ec81813044eb5936b698056c76ad348cbd28f029c3350343d8b7c.json

## C4 FP32 cast-once diagnostic source-probe/doctor

[v2.modal_target] app=batch-rv4-cast-once class=ModalRuntimeEntrypointV2 environment=(default) cloud_override=absent with_options_used=0
[v2ctl.source-probe] profile=golden_p1
[v2ctl.source-probe] git_head=81a29b3c7fae
[v2ctl.source-probe] target app=batch-rv4-cast-once class=ModalRuntimeEntrypointV2 gpu=rtx-pro-6000
[v2ctl.source-probe] remote class=ModalRuntimeEntrypointV2 image=im-t5rQz9XAiUGT1WcC8GwcvO container=80b13e6db98d426e
[v2ctl.source-probe] remote deployment_combined_hash=c159d02739984135
[v2ctl.source-probe] remote cwd=/root/comfy/ComfyUI
[v2ctl.source-probe] remote comfymodal_runtime __file__=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/modal_app.py: MATCH remote_sha=6fdc28c80ae86e5b expected_sha=6fdc28c80ae86e5b path=/root/comfymodal_runtime/modal_app.py
[v2ctl.source-probe]   comfymodal_runtime/critical_path_ledger.py: MATCH remote_sha=d001f24678843afc expected_sha=d001f24678843afc path=/root/comfymodal_runtime/critical_path_ledger.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_bootstrap.py: MATCH remote_sha=624dcd50c26f55b5 expected_sha=624dcd50c26f55b5 path=/root/comfymodal_runtime/runtime_bootstrap.py
[v2ctl.source-probe]   comfymodal_runtime/runtime_executor.py: MATCH remote_sha=ab0651bf2de41e7d expected_sha=ab0651bf2de41e7d path=/root/comfymodal_runtime/runtime_executor.py
[v2ctl.source-probe]   comfymodal_runtime/gantt_telemetry.py: MATCH remote_sha=bf61c7db3a931120 expected_sha=bf61c7db3a931120 path=/root/comfymodal_runtime/gantt_telemetry.py
[v2ctl.source-probe]   comfymodal_runtime/model_preload.py: MATCH remote_sha=4affe1e06a3acc24 expected_sha=4affe1e06a3acc24 path=/root/comfymodal_runtime/model_preload.py
[v2ctl.source-probe]   comfymodal_runtime/clip_fast_hydration_wiring.py: MATCH remote_sha=7108c8bc8308010b expected_sha=7108c8bc8308010b path=/root/comfymodal_runtime/clip_fast_hydration_wiring.py
[v2ctl.source-probe]   comfymodal_runtime/registry_proof_store.py: MATCH remote_sha=9e4692fddc14ad91 expected_sha=9e4692fddc14ad91 path=/root/comfymodal_runtime/registry_proof_store.py
[v2ctl.source-probe]   comfymodal_runtime/golden_serial.py: MATCH remote_sha=02c5f8a09d5b30ca expected_sha=02c5f8a09d5b30ca path=/root/comfymodal_runtime/golden_serial.py
[v2ctl.source-probe]   comfymodal_runtime/golden_qd_transport.py: MATCH remote_sha=5819386703c00226 expected_sha=5819386703c00226 path=/root/comfymodal_runtime/golden_qd_transport.py
[v2ctl.source-probe]   comfymodal_runtime/output_durability.py: MATCH remote_sha=f4a95d4e0348df27 expected_sha=f4a95d4e0348df27 path=/root/comfymodal_runtime/output_durability.py
[v2ctl.source-probe] ledger flag=COMFYMODAL_V2_CRITICAL_PATH_LEDGER enabled=True record_event=True
[v2ctl.source-probe] verdict=MATCH
[v2ctl.source-probe] RESULT=PASS source_identity=MATCH
[v2ctl.doctor]
git.head=81a29b3c7faea2a2579370796755fde4c1b6a728
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv4-cast-once
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=119
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=3fa61f017c6ec81813044eb5936b698056c76ad348cbd28f029c3350343d8b7c
deployment.fingerprint.current=3fa61f017c6ec81813044eb5936b698056c76ad348cbd28f029c3350343d8b7c
deployment.fingerprint.match=1
deployment.target.match=1
[v2ctl.doctor] OK
fp32_diag_deploy_probe_exit=0

## C5 BF16 diagnostic mandatory warmup (NOT COUNTED)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5 run_fingerprint=2ad805cbb5e2baf566abf285382fcd723cf65351fcac263826f5349471614e76
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-180939_2ad805cb.json
bf16_warmup_exit=0; counted=NO

## C6 BF16 diagnostic smoke (stage diagnostics ON; E31 forensics ON)

[v2ctl.run] profile=golden_p1 deploy_fingerprint=5b84743faf7f385e75e8941d97913ea5be1ab7340c99af0def54166af1685ef5 run_fingerprint=2ad805cbb5e2baf566abf285382fcd723cf65351fcac263826f5349471614e76
[v2ctl.run] command="C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\run_v2_single.bat" --run-count 1 --golden-p1-expected-output-sha 8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
[v2ctl.run] exit=0 manifest=C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.v2ctl\runs\run_20260831-181018_2ad805cb.json
bf16_smoke_exit=0

## BF16 redeploy after stage-diagnostics propagation fix
$ python tools/v2ctl.py --profile golden_p1 --app batch-rv4-cast-bf16 --cpu 4 --memory-mb 16384 --set COMFYMODAL_GOLDEN_QD_TRANSPORT=legacy --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 --set COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0 --set COMFYMODAL_V2_E31_FORENSICS=1 --set COMFYMODAL_V2_E31_FORWARD_PROFILE=0 --set COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT=1024 golden deploy --app batch-rv4-cast-bf16

[ v 2 c t l . d e p l o y ]   p r o f i l e = g o l d e n _ p 1   d e p l o y _ f i n g e r p r i n t = b 2 c 3 d f 9 4 e b a 7 a 0 5 b 3 d 0 8 4 e b 7 4 9 b 8 2 5 6 5 c 6 e 0 f 1 6 8 d 6 b d b f 9 2 3 b 1 f 7 0 f 4 6 5 2 9 c d a 5  
 [ v 2 c t l . d e p l o y ]   c o m m a n d = m o d a l   d e p l o y   - m   c o m f y m o d a l _ r u n t i m e . m o d a l _ a p p   - - n a m e   b a t c h - r v 4 - c a s t - b f 1 6  
 [ c u s t o m _ n o d e s . p u b l i s h ]   d e c i s i o n = p u b l i s h e d   r e a s o n = p u b l i s h e d _ v e r i f i e d   g e n e r a t i o n = a 3 f 7 b 4 f 6 9 b 6 3   s c h e m a = 2   p o l i c y = 1  
 [ v 2 c t l . d e p l o y ]   e x i t = 0   m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 8 3 1 - 1 8 2 7 4 1 _ b 2 c 3 d f 9 4 . j s o n  
 [ v 2 c t l . d e p l o y ]   d e p l o y m e n t _ r e c e i p t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ r e c e i p t _ 2 _ b 2 c 3 d f 9 4 e b a 7 a 0 5 b 3 d 0 8 4 e b 7 4 9 b 8 2 5 6 5 c 6 e 0 f 1 6 8 d 6 b d b f 9 2 3 b 1 f 7 0 f 4 6 5 2 9 c d a 5 . j s o n  
 
$ python tools/v2ctl.py --profile golden_p1 --app batch-rv4-cast-bf16 source-probe

p y t h o n   :   [ v 2 c t l . s o u r c e - p r o b e ]   W A R N I N G :   l o c a l   d e p l o y   i d e n t i t y   d r i f t e d   a f t e r   d e p l o y m e n t ;   b i n d i n g   t h e   i m m u t a b l e   r e m o t e    
 r e c e i p t   ( s o u r c e   d r i f t   i s   w a r n i n g - o n l y )  
 A t   l i n e : 1   c h a r : 1  
 +   p y t h o n   t o o l s / v 2 c t l . p y   - - p r o f i l e   g o l d e n _ p 1   - - a p p   b a t c h - r v 4 - c a s t - b f 1 6   s   . . .  
 +   ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~ ~  
         +   C a t e g o r y I n f o                     :   N o t S p e c i f i e d :   ( [ v 2 c t l . s o u r c e - p . . . s   w a r n i n g - o n l y ) : S t r i n g )   [ ] ,   R e m o t e E x c e p t i o n  
         +   F u l l y Q u a l i f i e d E r r o r I d   :   N a t i v e C o m m a n d E r r o r  
    
 [ v 2 . m o d a l _ t a r g e t ]   a p p = b a t c h - r v 4 - c a s t - b f 1 6   c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2   e n v i r o n m e n t = ( d e f a u l t )   c l o u d _ o v e r r i d e = a b s e n t   w i t h _ o p t i o n s _ u s e d = 0  
 [ v 2 c t l . s o u r c e - p r o b e ]   p r o f i l e = g o l d e n _ p 1  
 [ v 2 c t l . s o u r c e - p r o b e ]   g i t _ h e a d = 8 1 a 2 9 b 3 c 7 f a e  
 [ v 2 c t l . s o u r c e - p r o b e ]   t a r g e t   a p p = b a t c h - r v 4 - c a s t - b f 1 6   c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2   g p u = r t x - p r o - 6 0 0 0  
 [ v 2 c t l . s o u r c e - p r o b e ]   r e m o t e   c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2   i m a g e = i m - P k 6 2 A z y N o I B t W a h P J l 6 c m x   c o n t a i n e r = e 3 0 6 c d 3 c d b 1 e 4 7 9 f  
 [ v 2 c t l . s o u r c e - p r o b e ]   r e m o t e   d e p l o y m e n t _ c o m b i n e d _ h a s h = 3 0 d 5 9 c f 6 e d 6 1 3 d c 5  
 [ v 2 c t l . s o u r c e - p r o b e ]   r e m o t e   c w d = / r o o t / c o m f y / C o m f y U I  
 [ v 2 c t l . s o u r c e - p r o b e ]   r e m o t e   c o m f y m o d a l _ r u n t i m e   _ _ f i l e _ _ = / r o o t / c o m f y m o d a l _ r u n t i m e / m o d a l _ a p p . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / m o d a l _ a p p . p y :   M A T C H   r e m o t e _ s h a = f d 3 7 e 1 7 6 1 1 e 1 2 3 4 b   e x p e c t e d _ s h a = f d 3 7 e 1 7 6 1 1 e 1 2 3 4 b   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / m o d a l _ a p p . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / c r i t i c a l _ p a t h _ l e d g e r . p y :   M A T C H   r e m o t e _ s h a = d 0 0 1 f 2 4 6 7 8 8 4 3 a f c   e x p e c t e d _ s h a = d 0 0 1 f 2 4 6 7 8 8 4 3 a f c   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / c r i t i c a l _ p a t h _ l e d g e r . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / r u n t i m e _ b o o t s t r a p . p y :   M A T C H   r e m o t e _ s h a = 6 2 4 d c d 5 0 c 2 6 f 5 5 b 5   e x p e c t e d _ s h a = 6 2 4 d c d 5 0 c 2 6 f 5 5 b 5   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / r u n t i m e _ b o o t s t r a p . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / r u n t i m e _ e x e c u t o r . p y :   M A T C H   r e m o t e _ s h a = a b 0 6 5 1 b f 2 d e 4 1 e 7 d   e x p e c t e d _ s h a = a b 0 6 5 1 b f 2 d e 4 1 e 7 d   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / r u n t i m e _ e x e c u t o r . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / g a n t t _ t e l e m e t r y . p y :   M A T C H   r e m o t e _ s h a = b f 6 1 c 7 d b 3 a 9 3 1 1 2 0   e x p e c t e d _ s h a = b f 6 1 c 7 d b 3 a 9 3 1 1 2 0   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / g a n t t _ t e l e m e t r y . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / m o d e l _ p r e l o a d . p y :   M A T C H   r e m o t e _ s h a = 4 a f f e 1 e 0 6 a 3 a c c 2 4   e x p e c t e d _ s h a = 4 a f f e 1 e 0 6 a 3 a c c 2 4   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / m o d e l _ p r e l o a d . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / c l i p _ f a s t _ h y d r a t i o n _ w i r i n g . p y :   M A T C H   r e m o t e _ s h a = 7 1 0 8 c 8 b c 8 3 0 8 0 1 0 b   e x p e c t e d _ s h a = 7 1 0 8 c 8 b c 8 3 0 8 0 1 0 b   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / c l i p _ f a s t _ h y d r a t i o n _ w i r i n g . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / r e g i s t r y _ p r o o f _ s t o r e . p y :   M A T C H   r e m o t e _ s h a = 9 e 4 6 9 2 f d d c 1 4 a d 9 1   e x p e c t e d _ s h a = 9 e 4 6 9 2 f d d c 1 4 a d 9 1   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / r e g i s t r y _ p r o o f _ s t o r e . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / g o l d e n _ s e r i a l . p y :   M A T C H   r e m o t e _ s h a = 0 2 c 5 f 8 a 0 9 d 5 b 3 0 c a   e x p e c t e d _ s h a = 0 2 c 5 f 8 a 0 9 d 5 b 3 0 c a   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / g o l d e n _ s e r i a l . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / g o l d e n _ q d _ t r a n s p o r t . p y :   M A T C H   r e m o t e _ s h a = 5 8 1 9 3 8 6 7 0 3 c 0 0 2 2 6   e x p e c t e d _ s h a = 5 8 1 9 3 8 6 7 0 3 c 0 0 2 2 6   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / g o l d e n _ q d _ t r a n s p o r t . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]       c o m f y m o d a l _ r u n t i m e / o u t p u t _ d u r a b i l i t y . p y :   M A T C H   r e m o t e _ s h a = f 4 a 9 5 d 4 e 0 3 4 8 d f 2 7   e x p e c t e d _ s h a = f 4 a 9 5 d 4 e 0 3 4 8 d f 2 7   p a t h = / r o o t / c o m f y m o d a l _ r u n t i m e / o u t p u t _ d u r a b i l i t y . p y  
 [ v 2 c t l . s o u r c e - p r o b e ]   l e d g e r   f l a g = C O M F Y M O D A L _ V 2 _ C R I T I C A L _ P A T H _ L E D G E R   e n a b l e d = T r u e   r e c o r d _ e v e n t = T r u e  
 [ v 2 c t l . s o u r c e - p r o b e ]   v e r d i c t = M A T C H  
 [ v 2 c t l . s o u r c e - p r o b e ]   R E S U L T = P A S S   s o u r c e _ i d e n t i t y = M A T C H  
 
$ python tools/v2ctl.py golden status --app batch-rv4-cast-bf16

[ v 2 c t l . g o l d e n . s t a t u s ]  
 s c h e m a _ v e r s i o n = 2  
 p r o f i l e = g o l d e n _ p 1  
 t a r g e t = { ' a p p ' :   ' b a t c h - r v 4 - c a s t - b f 1 6 ' ,   ' c l a s s ' :   ' M o d a l R u n t i m e E n t r y p o i n t V 2 ' ,   ' m e t h o d ' :   ' r u n _ g o l d e n _ s e r i a l _ s t r e a m ' }  
 d e p l o y m e n t _ m a n i f e s t = C : \ U s e r s \ p a r l a \ O n e D r i v e \ D o c u m e n t s \ A I   H U B \ C o m f y U I   J u n e   I n s t a l l \ C o m f y U I \ c u s t o m _ n o d e s \ c o m f y u i - m o d a l \ . v 2 c t l \ d e p l o y m e n t s \ d e p l o y _ 2 0 2 6 0 8 3 1 - 1 8 2 7 4 1 _ b 2 c 3 d f 9 4 . j s o n  
 d e p l o y m e n t _ f i n g e r p r i n t _ c u r r e n t = 8 4 a b 3 6 7 9 3 6 4 0 4 6 6 0 9 5 5 8 6 f 8 6 6 3 5 b f d 8 d 3 f 0 d 9 4 d 7 8 e d 9 5 1 9 d f b 7 5 5 c f 4 e 4 f d f 4 4 5  
 d e p l o y m e n t _ f i n g e r p r i n t _ s t o r e d = b 2 c 3 d f 9 4 e b a 7 a 0 5 b 3 d 0 8 4 e b 7 4 9 b 8 2 5 6 5 c 6 e 0 f 1 6 8 d 6 b d b f 9 2 3 b 1 f 7 0 f 4 6 5 2 9 c d a 5  
 d e p l o y m e n t _ f i n g e r p r i n t _ m a t c h = F a l s e  
 d e p l o y m e n t _ t a r g e t _ m a t c h = T r u e  
 d e p l o y e d _ s t a t e _ p r e s e n t = T r u e  
 d e p l o y e d _ s t a t e _ t a r g e t _ m a t c h = F a l s e  
 d e p l o y e d _ s t a t e _ a p p = b a t c h - r a 2 - a c t i v e - p a t c h e r  
 d e p l o y e d _ s t a t e _ c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2  
 d e p l o y e d _ s t a t e _ c o m b i n e d _ h a s h = d 2 5 1 6 1 5 4 4 d 2 d 2 d 7 4 6 1 d 3 2 a 1 b 2 f 9 9 e a 3 8 1 c 6 c f 7 a 1 0 8 d 3 c 9 b 2 4 8 1 0 3 7 1 9 2 f b e a c 9 6  
 d e p l o y e d _ s t a t e _ e r r o r =  
 r u n t i m e _ h e a l t h _ s t a t u s = u n v e r i f i e d  
 s o u r c e _ i d e n t i t y _ s t a t u s = u n v e r i f i e d  
 r u n t i m e _ o v e r r i d e s _ p r e s e n t = 0  
 d e p l o y _ l o c k _ a c t i v e = F a l s e  
 c a p t u r e _ g u a r d = { ' s c h e m a _ v e r s i o n ' :   2 ,   ' s t a t e ' :   ' i d l e ' ,   ' p o s t _ c a p t u r e _ g u a r d _ p e n d i n g ' :   F a l s e ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ s n a p s h o t _ c a p t u r e _ a t ' :   ' ' ,   ' g u a r d _ a r m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ b y _ r e q u e s t _ i d ' :   ' ' ,   ' l a s t _ g u a r d _ c o n s u m e d _ a t ' :   ' ' ,   ' c a p t u r e _ i d e n t i t y ' :   ' ' ,   ' c a p t u r e _ r e q u e s t _ i d ' :   ' ' ,   ' c a p t u r e _ a t ' :   ' ' ,   ' d e p l o y m e n t _ i d e n t i t y ' :   ' { " a p p _ n a m e " : " b a t c h - r v 4 - c a s t - b f 1 6 " , " c l a s s _ n a m e " : " M o d a l R u n t i m e E n t r y p o i n t V 2 " , " d e p l o y _ f i n g e r p r i n t " : " 8 4 a b 3 6 7 9 3 6 4 0 4 6 6 0 9 5 5 8 6 f 8 6 6 3 5 b f d 8 d 3 f 0 d 9 4 d 7 8 e d 9 5 1 9 d f b 7 5 5 c f 4 e 4 f d f 4 4 5 " , " d e p l o y m e n t _ c o m b i n e d _ h a s h " : " " , " g p u " : " r t x - p r o - 6 0 0 0 " } ' ,   ' l a s t _ t r a n s i t i o n _ r e a s o n ' :   ' i n i t i a l ' }  
 n e x t _ r e q u e s t _ g u a r d e d = F a l s e  
 r e m o t e _ c h e c k s = n o t _ p e r f o r m e d  
 r e a d y = F a l s e  
 
$ python tools/v2ctl.py doctor --profile golden_p1 --app batch-rv4-cast-bf16

[ v 2 c t l . d o c t o r ]  
 g i t . h e a d = 8 1 a 2 9 b 3 c 7 f a e a 2 a 2 5 7 9 3 7 0 7 9 6 7 5 5 f d e 4 c 1 b 6 a 7 2 8  
 g i t . b r a n c h = T E S T I N G 2  
 g i t . d i r t y = 1  
 p y t h o n = 3 . 1 1 . 9  
 p r o f i l e = g o l d e n _ p 1  
 t a r g e t . a p p = b a t c h - r v 4 - c a s t - b f 1 6  
 t a r g e t . c l a s s = M o d a l R u n t i m e E n t r y p o i n t V 2  
 t a r g e t . m e t h o d = r u n _ g o l d e n _ s e r i a l _ s t r e a m  
 b a c k e n d . d e p l o y _ a n d _ r u n _ v 2 _ s i n g l e . e x i s t s = 1   k i n d = c o m b i n e d  
 b a c k e n d . d e p l o y _ a n d _ r u n _ v 2 _ s i n g l e _ d e p l o y _ o n l y . e x i s t s = 1   k i n d = d e p l o y _ o n l y _ v i a _ e n v  
 b a c k e n d . r u n _ v 2 _ s i n g l e . e x i s t s = 1   k i n d = r u n  
 r e g i s t r y . f l a g s = 1 2 0  
 p r o f i l e s = e 2 9 - t r a c e r , e 3 0 - c l i p - q d , e 3 0 - c l i p - q d - a r m - a , e 3 0 - c l i p - q d - a r m - b , e 3 1 - c l i p - f p 3 2 - f a s t s a f e - a r m - a , e 3 1 - c l i p - f p 3 2 - f a s t s a f e - a r m - b , e 3 1 - c l i p - f p 3 2 - q d 4 - a r m - a , e 3 1 - c l i p - f p 3 2 - q d 4 - a r m - b , e 3 7 - c l e a n - l a n e - q d 4 , e 3 7 - c l i p - f a s t s a f e , e 3 7 - c l i p - q d 4 , g o l d e n _ p 1 , p r o d u c t i o n  
 r u n t i m e _ o v e r r i d e _ p o l i c y = f o r b i d  
 r u n t i m e _ o v e r r i d e s . p r e s e n t = 0  
 d e p l o y . l o c k = n o n e  
 d e p l o y m e n t . f i n g e r p r i n t . s t o r e d = b 2 c 3 d f 9 4 e b a 7 a 0 5 b 3 d 0 8 4 e b 7 4 9 b 8 2 5 6 5 c 6 e 0 f 1 6 8 d 6 b d b f 9 2 3 b 1 f 7 0 f 4 6 5 2 9 c d a 5  
 d e p l o y m e n t . f i n g e r p r i n t . c u r r e n t = 8 4 a b 3 6 7 9 3 6 4 0 4 6 6 0 9 5 5 8 6 f 8 6 6 3 5 b f d 8 d 3 f 0 d 9 4 d 7 8 e d 9 5 1 9 d f b 7 5 5 c f 4 e 4 f d f 4 4 5  
 d e p l o y m e n t . f i n g e r p r i n t . m a t c h = 0  
 d e p l o y m e n t . t a r g e t . m a t c h = 1  
 [ v 2 c t l . d o c t o r ]   P R O B L E M S :  
     -   d e p l o y m e n t   f i n g e r p r i n t   m i s m a t c h :   d e p l o y - r e q u i r e d   s t a t e   c h a n g e d   s i n c e   l a s t   d e p l o y  
 
## BF16 post-fix mandatory warmup (NOT COUNTED)
$ python tools/v2ctl.py --profile golden_p1 --app batch-rv4-cast-bf16 --inherit COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS --inherit COMFYMODAL_V2_E31_FORENSICS --inherit COMFYMODAL_V2_CLIP_FP32_CAST_ONCE --inherit COMFYMODAL_GOLDEN_QD_TRANSPORT golden run --app batch-rv4-cast-bf16


## FP32 cast-once redeploy after stage-diagnostics propagation fix
$ python tools/v2ctl.py --profile golden_p1 --app batch-rv4-cast-once --cpu 4 --memory-mb 16384 --set COMFYMODAL_GOLDEN_QD_TRANSPORT=legacy --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 --set COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=1 --set COMFYMODAL_V2_E31_FORENSICS=1 --set COMFYMODAL_V2_E31_FORWARD_PROFILE=0 --set COMFYMODAL_V2_E31_CAST_SAMPLE_LIMIT=1024 golden deploy --app batch-rv4-cast-once

