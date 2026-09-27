# RA6R Remote Sampling OFF vs BLOCKS Raw Log

## Lane disposition

```text
RA6_REMOTE_BLOCKED_EXACT_SOURCE_REPRODUCTION
Remote deployment contact: NO
Remote Golden request contact: NO
Reason: selector is deployment-only and exact immutable RV2B-source
        reproduction for a blocks deployment cannot be proven safely.
```

No RA6R remote attempt was hidden or discarded. There are no RA6R BLOCKS
payloads, invalid requests, failed requests, or profiler errors because the
lane stopped before deployment/request execution.

## Commands actually run

### Read-only source/worktree checks

```text
COMMAND: rtk git status --short --branch
OUTPUT:
* TESTING2...origin/TESTING2 [ahead 1]
 M RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z/campaign.log
 M tests/test_v2ctl_cli.py
 M tools/v2_control/cli.py
 M tools/v2_control/config.py
 M tools/v2_control/source_probe.py
 M tools/v2_control/validation.py
?? RA11C_EXACT_GOLDEN_EXECUTION_CLOSURE_AUDIT.md
?? RA11E_GOLDEN_OFF_MODE_IMPORT_REACHABILITY_AUDIT.md
?? RA9B_QD4_COMPUTE_READY_RESIDENCY_ARCHAEOLOGY_REPORT.md
?? RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md
?? RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md
?? RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT2/
?? RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT3/
?? comfymodal_runtime/golden_qd_transport.py
?? tests/test_golden_qd_transport.py
?? tests/test_v2ctl_deployment_receipt.py
?? tools/v2_control/deployment_receipt.py
```

```text
COMMAND: git cat-file -t aaba80156dc559e591fc7379836991059f7ecc31b107875b0635de94e8ac9a48
OUTPUT: fatal: Not a valid object name aaba80156dc559e591fc7379836991059f7ecc31b107875b0635de94e8ac9a48
INTERPRETATION: Modal deployment/version identity is not a local Git object.
```

### Existing deployment status

```text
COMMAND: python tools/v2ctl.py golden status --app batch-rv2b-golden-measurement
OUTPUT:
profile=golden_p1
target={'app': 'batch-rv2b-golden-measurement', 'class': 'ModalRuntimeEntrypointV2', 'method': 'run_golden_serial_stream'}
deployment_manifest=.v2ctl/deployments/deploy_20260830-215842_3afb957b.json
deployment_fingerprint_current=ff22453aa4dd1567ad0b414259ce8c63b2d3a82c2fb73f21dc314e1cc46c5117
deployment_fingerprint_stored=3afb957ba2e1275eddca2be82b9dfe54fcf0b80c77f66d8fdab1478436d765d9
deployment_fingerprint_match=False
deployment_target_match=True
deployed_state_present=True
deployed_state_target_match=False
deployed_state_app=batch-ra2-active-patcher
runtime_health_status=unverified
source_identity_status=unverified
runtime_overrides_present=0
deploy_lock_active=False
next_request_guarded=False
remote_checks=not_performed
ready=False
```

```text
COMMAND: python tools/v2ctl.py doctor --profile golden_p1 --app batch-rv2b-golden-measurement
OUTPUT:
git.head=7f9a19ef9bf88c1424340897cdf723748b1341dc
git.branch=TESTING2
git.dirty=1
profile=golden_p1
target.app=batch-rv2b-golden-measurement
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
runtime_override_policy=forbid
runtime_overrides.present=0
deploy.lock=none
deployment.fingerprint.stored=3afb957ba2e1275eddca2be82b9dfe54fcf0b80c77f66d8fdab1478436d765d9
deployment.fingerprint.current=ff22453aa4dd1567ad0b414259ce8c63b2d3a82c2fb73f21dc314e1cc46c5117
deployment.fingerprint.match=0
[v2ctl.doctor] PROBLEMS:
  - deployment fingerprint mismatch: deploy-required state changed since last deploy
```

No `golden deploy`, `source-probe`, `golden run`, `confirm`, direct Modal
command, legacy BAT command, or production-app command was run by RA6R.

## Frozen manifest evidence

Source: `.v2ctl/deployments/deploy_20260830-215842_3afb957b.json`

```text
deploy_fingerprint=3afb957ba2e1275eddca2be82b9dfe54fcf0b80c77f66d8fdab1478436d765d9
modal deployment/version identity=aaba80156dc559e591fc7379836991059f7ecc31b107875b0635de94e8ac9a48
target.app=batch-rv2b-golden-measurement
target.class=ModalRuntimeEntrypointV2
target.method=run_golden_serial_stream
image=im-kgisSW1st7TzVVWiuyOwvJ
gpu=rtx-pro-6000
cpu=12
memory_mb=32768
COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1
COMFYMODAL_SAMPLING_DEEP_PROFILE=off
runtime_override_policy=forbid
git_dirty=true
git_head=7f9a19ef9bf88c1424340897cdf723748b1341dc
custom_nodes_generation=e4671089280ad6cc1558b1859baec58f6fa5f22e1ba74bdb6b8e55c208b7fa58
runtime_health_status=verified
source_identity_status=verified
```

## Existing OFF evidence retained, not rerun

The five eligible true-cold RV2B observations remain at the following
invocation-bound cohort paths and are fully described by
`RV2B_REMOTE_GOLDEN_BASELINE_RAW_LOG.md` and
`RV2B_REMOTE_GOLDEN_BASELINE_TRUTH_REPORT.md`:

```text
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-03-36_41efe9/
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-05-53_a835fa/
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-07-06_a774f5/
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-08-20_450e13/
artifacts/phase_p1_serial_golden_v1/cohort_2026-08-31_03-09-19_ea74e7/
```

Authoritative OFF walls, in ms:

```text
5689.258
5253.376
5619.835
5463.582
5585.380
median=5585.380
```

Retained raw campaign roots:

```text
RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z/
RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT2/
RV2B_REMOTE_MEASUREMENT_RAW_EVIDENCE_20260830T000000Z_REPLACEMENT3/
```

These existing artifacts are the raw evidence authority for OFF. No RA6R
BLOCKS artifact exists. The historical RA6H profiler payload references are
not promoted to current RA6R evidence.

```text
RA6R_COMPLETE=NO
RAW_LOG_COMPLETE=YES
SOURCE_CODE_CHANGED=NO
CONFIG_SOURCE_CHANGED=NO
EXISTING_RV2B_DEPLOYMENT_REUSED=NO
SELECTOR_SCOPE=DEPLOYMENT_ONLY
DEPLOYMENTS_PERFORMED=0
OFF_VALID_RUNS=5
BLOCKS_VALID_RUNS=0
STEPS_RUNS=0
SAME_SOURCE_AB=NO
CACHE_DIT_EVALS=17 (existing OFF baseline; no BLOCKS run)
CACHE_DIT_COMPUTE=10 (existing OFF baseline; no BLOCKS run)
CACHE_DIT_SKIP=7 (existing OFF baseline; no BLOCKS run)
PROFILER_TAX=UNPROVEN
AUTHORITATIVE_OFF_MEDIAN_MS=5585.380
AUTHORITATIVE_BLOCKS_MEDIAN_MS=UNPROVEN
CURRENT_FIRST_EVAL_PREMIUM_MS=UNPROVEN
CURRENT_FIRST_COMPUTE_PREMIUM_MS=UNPROVEN
ATTENTION_FRACTION_OF_SAMPLING=UNPROVEN
NON_ATTENTION_FRACTION_OF_SAMPLING=UNPROVEN
SAMPLER_RESIDUAL_MS=UNPROVEN
NEXT_SAMPLING_OPTIMIZATION_TARGET=UNPROVEN_PENDING_CLEAN_PINNED_BLOCKS_AB
MODAL_CONTACTED=NO
```
