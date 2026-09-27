# RV2 Remote Golden Baseline — Complete Raw Log

This is the invocation-bound raw console record for RV2. The campaign stopped at the pre-deployment S4 publication gate. No source-probe or Golden request was run after that stop.

## Campaign configuration

Experimental app: `batch-rv2-golden-baseline`
Profile: `golden_p1`
Diagnostic deployment selector: `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1`
Sampling selector: `COMFYMODAL_SAMPLING_DEEP_PROFILE=off`

## Preflight

### Command

```text
python tools/v2ctl.py --profile golden_p1 --app batch-rv2-golden-baseline --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 golden status
```

### Complete output

```text
[v2ctl.golden.status]
schema_version=2
profile=golden_p1
target={'app': 'batch-rv2-golden-baseline', 'class': 'ModalRuntimeEntrypointV2', 'method': 'run_golden_serial_stream'}
deployment_manifest=None
deployment_fingerprint_current=f3d14d161578fecc66f5c39d6de9ac3095dba546f74d69ded6ff09d8d8020190
deployment_fingerprint_stored=None
deployment_fingerprint_match=False
deployment_target_match=False
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
capture_guard={'schema_version': 2, 'state': 'idle', 'post_capture_guard_pending': False, 'last_snapshot_capture_request_id': '', 'last_snapshot_capture_at': '', 'guard_armed_by_request_id': '', 'last_guard_consumed_by_request_id': '', 'last_guard_consumed_at': '', 'capture_identity': '', 'capture_request_id': '', 'capture_at': '', 'deployment_identity': '{"app_name":"batch-rv2-golden-baseline","class_name":"ModalRuntimeEntrypointV2","deploy_fingerprint":"f3d14d161578fecc66f5c39d6de9ac3095dba546f74d69ded6ff09d8d8020190","deployment_combined_hash":"","gpu":"rtx-pro-6000"}', 'last_transition_reason': 'initial'}
next_request_guarded=False
remote_checks=not_performed
ready=False
EXIT_CODE=0
```

### Command

```text
python tools/v2ctl.py --profile golden_p1 --app batch-rv2-golden-baseline --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 doctor
```

### Complete output

```text
[v2ctl.doctor]
git.head=02f1845a37c7c602bb598afb7e33cab938044e99
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv2-golden-baseline
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=118
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.manifest=none
[v2ctl.doctor] PROBLEMS:
  - no deployment manifest found; run `v2ctl deploy-run` or `v2ctl deploy` first
EXIT_CODE=1
```

## Deployment attempt 1

### Command

```text
python tools/v2ctl.py --profile golden_p1 --set COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1 golden deploy --app batch-rv2-golden-baseline
```

### Complete output

```text
[v2ctl.deploy] profile=golden_p1 deploy_fingerprint=f3d14d161578fecc66f5c39d6de9ac3095dba546f74d69ded6ff09d8d8020190
[v2ctl.deploy] command=modal deploy -m comfymodal_runtime.modal_app --name batch-rv2-golden-baseline
python.exe : ERROR: Golden deploy requires verified custom-node publication: publication_incomplete result={"comfyapp_version":"2.16.31","error":null,"expected_generation":"e9c604ad4d43e95a","readback_generation":null,"reason":null,"result_generation":"7fc71a1f6e08ad80","status":"ok"}
At line:1 char:250
+ ... eline`r`n"; & python tools/v2ctl.py --profile golden_p1 --set COMFYMO ...
+                 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    + CategoryInfo          : NotSpecified: (ERROR: Golden deploy requires verified custom-node publication: publication_incomplete result={"comfyapp_version":"2.16.31","error":null,"expected_generation":"e9c604ad4d43e95a","readback_generation":null,"reason":null,"result_generation":"7fc71a1f6e08ad80","status":"ok"}:String) [], RemoteException
    + FullyQualifiedErrorId : NativeCommandError
EXIT_CODE=1
```

Deployment stopped here. The native Modal deploy was not reached as a usable deployment because the canonical Golden precondition rejected the publication result.

## Post-failure non-mutating state check

### Command

```text
python tools/v2ctl.py --profile golden_p1 --app batch-rv2-golden-baseline golden status
```

### Complete output

```text
[v2ctl.golden.status]
schema_version=2
profile=golden_p1
target={'app': 'batch-rv2-golden-baseline', 'class': 'ModalRuntimeEntrypointV2', 'method': 'run_golden_serial_stream'}
deployment_manifest=None
deployment_fingerprint_current=143541108027272efcbc7e2dde2dc1b970067933c93f285b202faae105055257
deployment_fingerprint_stored=None
deployment_fingerprint_match=False
deployment_target_match=False
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
capture_guard={'schema_version': 2, 'state': 'idle', 'post_capture_guard_pending': False, 'last_snapshot_capture_request_id': '', 'last_snapshot_capture_at': '', 'guard_armed_by_request_id': '', 'last_guard_consumed_by_request_id': '', 'last_guard_consumed_at': '', 'capture_identity': '', 'capture_request_id': '', 'capture_at': '', 'deployment_identity': '{"app_name":"batch-rv2-golden-baseline","class_name":"ModalRuntimeEntrypointV2","deploy_fingerprint":"143541108027272efcbc7e2dde2dc1b970067933c93f285b202faae105055257","deployment_combined_hash":"","gpu":"rtx-pro-6000"}', 'last_transition_reason': 'initial'}
next_request_guarded=False
remote_checks=not_performed
ready=False
EXIT_CODE=0
```

### Command

```text
python tools/v2ctl.py --profile golden_p1 --app batch-rv2-golden-baseline doctor
```

### Complete output

```text
[v2ctl.doctor]
git.head=02f1845a37c7c602bb598afb7e33cab938044e99
git.branch=TESTING2
git.dirty=1
python=3.11.9
profile=golden_p1
target.app=batch-rv2-golden-baseline
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
backend.deploy_and_run_v2_single.exists=1 kind=combined
backend.deploy_and_run_v2_single_deploy_only.exists=1 kind=deploy_only_via_env
backend.run_v2_single.exists=1 kind=run
registry.flags=118
profiles=e29-tracer,e30-clip-qd,e30-clip-qd-arm-a,e30-clip-qd-arm-b,e31-clip-fp32-fastsafe-arm-a,e31-clip-fp32-fastsafe-arm-b,e31-clip-fp32-qd4-arm-a,e31-clip-fp32-qd4-arm-b,e37-clean-lane-qd4,e37-clip-fastsafe,e37-clip-qd4,golden_p1,production
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.manifest=none
[v2ctl.doctor] PROBLEMS:
  - no deployment manifest found; run `v2ctl deploy-run` or `v2ctl deploy` first
EXIT_CODE=1
```

## Requests not run

No `source-probe`, `golden run`, `gate`, or `confirm` command was run. There were no snapshot captures, invalid request attempts, failed Golden requests, or eligible observations.
