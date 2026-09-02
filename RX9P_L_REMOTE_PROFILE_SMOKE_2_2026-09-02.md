# RX9P-L Remote Profile Smoke #2

Date: 2026-09-02
Branch: TESTING2
App: `rx9p-l-remote-profile-smoke-2`

## Result

`REMOTE_PROFILE_SMOKE_2=FAIL`.

The reconciled H/T/G/J/K stack was committed before remote work. The first
deploy command was killed by the local 120000 ms tool cutoff; that is an
inconclusive local attempt, not a Modal result. The replacement canonical
deploy used the 900000 ms tool bound, completed with exit 0 in 200.469 s, and is the sole terminal-successful
remote deployment. Its receipt reports a deployed Git SHA that does not match
the reconciled TESTING2 head, so `DEPLOYED_SOURCE_MATCH=NO`. The sole Golden
request exited 1; its exact output and several runtime identities were
verified, but the Sage identity and complete evidence bundle gates failed. No
confirmation or retry was made.

## Repository preservation and commit

`PRE_RECONCILIATION_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9`

`RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5`

The complete pre-change working-tree diff was saved outside the repository at
`C:\Users\parla\AppData\Local\Temp\opencode\rx9p-l-full-working-tree-3bb02cafc077bab4c8878ad4558fdb42d09f42e9.diff`.

The pre-existing unrelated dirty file
`RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md` was not changed or staged.

The committed source preserves G full-trace and E27 gate synchronization, H
immutable invocation/request identity and attention identity, H four-field
Sage provenance, K fail-closed contradictory Sage handling, T FAST_UNIT /
HEAVY_LOCAL separation and `tools/test_perf.py`, the permanent `AGENTS.md`
test-performance policy, and J deferred import-time build diagnostics.

Cheap final checks passed before commit: 246 focused identity/evidence/E27
tests, `py_compile`, and `git diff --check`. The selected cheap command
emitted a faulthandler diagnostic during an E27 test but completed
successfully. The Windows heavy-local lifecycle test was not run in this lane;
its known status is `LOCAL_HEAVY_TEST_INFRASTRUCTURE_BLOCKER`.

## Deployment preflight

The canonical public `v2ctl` path was used with:

```text
profile=golden_p1
class=ModalRuntimeEntrypointV2
method=run_golden_serial_stream
gpu=rtx-pro-6000
provider=CLOUD_PROVIDER_GCP
region=us-east1
cpu=4
memory=16384 MiB
app=rx9p-l-remote-profile-smoke-2
```

The frozen diagnostic inputs were:

```text
COMFYMODAL_V2_GOLDEN_ATTENTION_BACKEND=pytorch
COMFYMODAL_SAGE_RUNTIME_MODE=auto
COMFYMODAL_V2_FULL_TRACE=1
COMFYMODAL_V2_E27_FORENSICS=1
```

Sampler, QD, CLIP algorithm, UNET algorithm, workflow, tolerance, and ordering
were not changed. The active `golden_p1` profile resolved its current
accepted-reference SHA as
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`.

The replacement deployment artifacts are:

```text
manifest=.v2ctl/deployments/deploy_20260902-114702_09e9fb7b.json
receipt=.v2ctl/deployments/receipt_1_09e9fb7be530a8768b67bbd70c9dde323d0a4b09b84d40b117f71f9da1559d64.json
receipt_deploy_fingerprint=09e9fb7be530a8768b67bbd70c9dde323d0a4b09b84d40b117f71f9da1559d64
receipt_deployed_git_sha=ca3236ba52d2e7a6bd666cffa2a49c7ccdc620cc
runtime_deployment_identity=51d08c6d58767188b697679c814671b740114881192f96d4e1bfaf1feccc483a
```

The receipt deployed SHA does not equal `RECONCILED_TESTING2_HEAD`, therefore
`DEPLOYED_SOURCE_MATCH=NO`. The runtime deployment identity also differs from
the receipt fingerprint; that discrepancy remains unreconciled.

## Remote budget and stop condition

```text
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=1
DEPLOY_TIMEOUT_MS=120000
```

`REMOTE_DEPLOYS=1` counts only the replacement terminal-successful deployment.
The first local-cutoff attempt is recorded separately as inconclusive and is
not counted as a second completed deploy. There was exactly one Golden request
with no confirmation or retry.

## Sole Golden request and current cohort

```text
v2ctl_invocation=133afac7c9004337aee7687200c76ce6
request=golden-p1-0-c9ff4f9c6fa8
run_manifest=.v2ctl/runs/run_20260902-115014_767e0862.json
cohort=artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525
run_exit=1
control_plane_seconds=29.187
attempt_ms=27.500
```

The run was true-cold under the explicit identity criteria:
`restore_count=1`, `request_count=1`, `min_containers=0`, single-use enabled,
and nonce, instance, and frozen identities present. The snapshot guard was
idle with no capture, armed, or consumed request.

Expected and observed output SHA256 are both
`8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e`, with
3118036 observed output bytes, so output exactness is proven. Output mode was
`off/result_ready`; `true_durable=false` and `reopen=false` are expected for
off mode.

Attention identity resolved as `pytorch`, matching its configured value. Sage
was configured and received as `auto`, with resolution source
`auto_resolution`, but the run manifest has an empty resolved value and the
cohort normalizes it to `missing`. This is the sole invalidation:
`sage_runtime_mode_resolved_missing`.

The invocation chain is proven through
`v2ctl invocation -> request -> exact cohort -> manifest -> attempt_0.json ->
attempt_0_events.json -> summary.json`; the cohort records
`provenance_consistent=true`. The attempt provenance sidecar is absent, so
evidence bundle completeness is not proven.

## Evidence and profiler audit

Current evidence includes:

```text
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/deploy_attempt_2.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/source_probe.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/golden_run_attempt_1.log
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/verified_status.json
artifacts/rx9p_l_remote_profile_smoke_2_2026-09-02/verified_doctor.log
.v2ctl/deployments/deploy_20260902-114702_09e9fb7b.json
.v2ctl/deployments/receipt_1_09e9fb7be530a8768b67bbd70c9dde323d0a4b09b84d40b117f71f9da1559d64.json
.v2ctl/runs/run_20260902-115014_767e0862.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/manifest.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/attempt_0.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/attempt_0_events.json
artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_16-49-46_bbf525/summary.json
EXPERIMENT_EVIDENCE_golden_p1_133afac7c9004337_2026-09-02.md
artifacts/golden_p1_133afac7c9004337_evidence_2026-09-02
```

The raw bundle is an evidence inventory retaining many historical files plus
current invocation records; it is not a clean standalone profiler bundle. No
complete invocation-bound standalone
`raw/viztracer.json.gz`, `raw/resource_samples.jsonl.gz`,
`raw/milestones.jsonl`, `raw/session_events.jsonl`, `raw/trace_config.json`,
`raw/runtime_result_summary.json`, `raw/wrapper_snapshots.json`,
`derived/golden_profile_summary.json`, `derived/golden_profile_report.md`, or
`derived/golden_profile_gantt.txt` exists. Runtime telemetry is embedded in
`attempt_0.json` and `attempt_0_events.json`, not those standalone paths.

`FULL_TRACE=1`, but `GANTT_TELEMETRY=0`. Accordingly, VizTracer and Torch
Trace raw presence are unknown, the Golden profile is incomplete, and no Modal
log Gantt or Gantt match is present. E27 flags were enabled in the effective
environment, but raw physical evidence and the source mechanism are unknown
unless directly proven by current attempt files; neither is proven here.

`WINDOWS_HEAVY_LOCAL_LIFECYCLE_ISSUE=OPEN` remains separate from this remote
result. Performance comparison is invalid because the deployed source does
not match the reconciled head and the profiler evidence is incomplete.

RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5
DEPLOYED_SOURCE_MATCH=NO
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=1
OUTPUT_EXACT=YES
ATTENTION_BACKEND_CONFIGURED=pytorch
ATTENTION_BACKEND_RESOLVED=pytorch
ATTENTION_IDENTITY_PROVEN=YES
SAGE_RUNTIME_MODE_CONFIGURED=auto
SAGE_RUNTIME_MODE_EFFECTIVE_INPUT=auto
SAGE_RUNTIME_MODE_RESOLUTION_SOURCE=auto_resolution
SAGE_RUNTIME_MODE_RESOLVED=missing
SAGE_IDENTITY_PROVEN=NO
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
PERFORMANCE_COMPARISON_VALID=NO
WINDOWS_HEAVY_LOCAL_LIFECYCLE_ISSUE=OPEN
REMOTE_PROFILE_SMOKE_2=FAIL
READY_FOR_RX9=NO
