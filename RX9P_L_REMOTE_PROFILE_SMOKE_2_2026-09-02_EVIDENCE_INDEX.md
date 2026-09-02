# RX9P-L Remote Profile Smoke #2 Evidence Index

Git-visible pointers to the ignored runtime evidence for the current
invocation.

## Identity

```text
PRE_RECONCILIATION_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9
RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5
APP=rx9p-l-remote-profile-smoke-2
PROFILE=golden_p1
CLASS=ModalRuntimeEntrypointV2
METHOD=run_golden_serial_stream
GPU=rtx-pro-6000
PROVIDER=CLOUD_PROVIDER_GCP
REGION=us-east1
CPU=4
MEMORY_MIB=16384
```

## Budget and deployment

```text
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=1
DEPLOY_TIMEOUT_MS=120000
FIRST_DEPLOY=INCONCLUSIVE_LOCAL_TOOL_CUTOFF
REPLACEMENT_DEPLOY_TOOL_TIMEOUT_MS=900000
REPLACEMENT_DEPLOY_EXIT=0
REPLACEMENT_DEPLOY_DURATION_SECONDS=200.469
DEPLOYED_SOURCE_MATCH=NO
```

The first deploy command was killed by the local 120000 ms tool cutoff. It is
not a Modal result and is not counted as a second completed deployment. The
replacement is the sole terminal-successful deployment:

```text
.v2ctl/deployments/deploy_20260902-114702_09e9fb7b.json
.v2ctl/deployments/receipt_1_09e9fb7be530a8768b67bbd70c9dde323d0a4b09b84d40b117f71f9da1559d64.json
receipt_deploy_fingerprint=09e9fb7be530a8768b67bbd70c9dde323d0a4b09b84d40b117f71f9da1559d64
receipt_deployed_git_sha=ca3236ba52d2e7a6bd666cffa2a49c7ccdc620cc
runtime_deployment_identity=51d08c6d58767188b697679c814671b740114881192f96d4e1bfaf1feccc483a
```

The receipt Git SHA differs from `RECONCILED_TESTING2_HEAD`; the runtime
deployment identity also differs from the receipt fingerprint. Both remain
unreconciled.

## Sole Golden request and current cohort

```text
V2CTL_INVOCATION=133afac7c9004337aee7687200c76ce6
REQUEST=golden-p1-0-c9ff4f9c6fa8
.v2ctl/runs/run_20260902-115014_767e0862.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525
RUN_EXIT=1
CONTROL_PLANE_SECONDS=29.187
ATTEMPT_MS=27.500
TRUE_COLD=YES
OUTPUT_EXACT=YES
OUTPUT_SHA256=8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e
OUTPUT_BYTES=3118036
```

True-cold evidence: `restore_count=1`, `request_count=1`,
`min_containers=0`, single-use enabled, and nonce/instance/frozen identities
present. Snapshot guard was idle with no capture, armed, or consumed request.
Output mode was `off/result_ready`; `true_durable=false` and `reopen=false`
are expected for off mode.

Attention resolved as configured: `pytorch` / `pytorch`, identity proven. Sage
was configured/effective as `auto`, with source `auto_resolution`, but the run
manifest resolved value is empty and the cohort normalizes it to `missing`.
The sole invalidation is `sage_runtime_mode_resolved_missing`.

## Evidence files and gaps

```text
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/deploy_attempt_2.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/source_probe.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/golden_run_attempt_1.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/verified_status.json
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/verified_doctor.log
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/manifest.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/attempt_0.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/attempt_0_events.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/summary.json
EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md
artifacts/golden_p1_133afac7c9004337_evidence_2026-09-02
```

The invocation chain is proven through invocation, request, exact cohort,
manifest, `attempt_0.json`, `attempt_0_events.json`, and `summary.json`;
`provenance_consistent=true` is recorded in the cohort. The attempt provenance
sidecar is absent, so `EXPERIMENT_EVIDENCE_BUNDLE_COMPLETE=NO`.

The raw bundle is retained as an inventory containing historical files plus
current invocation records, not a complete standalone profiler bundle. No
complete invocation-bound standalone files exist at these paths:

```text
raw/viztracer.json.gz
raw/resource_samples.jsonl.gz
raw/milestones.jsonl
raw/session_events.jsonl
raw/trace_config.json
raw/runtime_result_summary.json
raw/wrapper_snapshots.json
derived/golden_profile_summary.json
derived/golden_profile_report.md
derived/golden_profile_gantt.txt
```

Runtime telemetry is embedded in the attempt JSON/events. `FULL_TRACE=1` and
`GANTT_TELEMETRY=0`; therefore raw VizTracer and Torch Trace presence are
unknown, profile completeness is `NO`, and Modal log Gantt/match are `NO`.
E27 flags were enabled in the effective environment, but raw E27 evidence and
the source mechanism are `UNKNOWN`.

```text
REMOTE_PROFILE_SMOKE_2=FAIL
INVOCATION_ID_CHAIN_PROVEN=YES
EXPERIMENT_EVIDENCE_BUNDLE_COMPLETE=NO
VIZTRACER_RAW_PRESENT=UNKNOWN
TORCH_TRACE_PRESENT=UNKNOWN
GOLDEN_PROFILE_COMPLETE=NO
MODAL_LOG_GANTT_PRESENT=NO
MODAL_GANTT_MATCH=NO
E27_RAW_PHYSICAL_EVIDENCE_PRESENT=UNKNOWN
E27_SOURCE_MECHANISM_PROVEN=UNKNOWN
E27_SOURCE_MECHANISM_PROVEN_AUDITED=NO
```
