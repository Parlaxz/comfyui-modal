# RX9P-L Remote Profile Smoke #2

Date: 2026-09-02
Branch: TESTING2
App: `rx9p-l-remote-profile-smoke-2`

## Result

`REMOTE_PROFILE_SMOKE_2=FAIL`.

The reconciled H/T/G/J/K stack was committed before remote work. The one
authorized deploy command exceeded the 120-second local tool bound before it
returned. No deployment receipt, deployment manifest, or deploy log was
produced. Post-deploy Golden status remained `ready=false` with no matching
deployment. The source-match gate therefore failed closed and no Golden
request was issued. No retry was made.

## Repository preservation and commit

`PRE_RECONCILIATION_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9`

`RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5`

The complete pre-change working-tree diff was saved outside the repository at
`C:\Users\parla\AppData\Local\Temp\opencode\rx9p-l-full-working-tree-3bb02cafc077bab4c8878ad4558fdb42d09f42e9.diff`.

The pre-existing unrelated dirty file
`RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md` was not changed or staged.
After the reconciliation commit it remained the only Git-visible dirty path
until this report and evidence index were added.

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
Older operational text contains a different historical SHA; no remote result
was accepted from either value because the request never ran.

Preflight config, dry-run command, lock state, committed SHA, and post-deploy
status are listed in the evidence index. Preflight proved the intended local
source SHA, workspace-bound control-plane configuration, environment profile,
publisher/deployment identity inputs, and diagnostic flags. It did not prove
remote publication because deploy did not complete.

## Remote budget and stop condition

```text
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=0
DEPLOY_TIMEOUT_MS=120000
```

The deployment attempt was the only deploy. No Golden request, confirmation,
retry, or alternate remote path was attempted. Because no receipt or matching
manifest exists, `DEPLOYED_SOURCE_MATCH=NO` and the stop condition prevented
request execution.

No caller or Modal request log exists for this lane. The required raw profiler
bundle, persisted Gantt, raw E27 evidence, invocation/request chain, resolved
attention identity, resolved Sage identity, and output exactness were not
observed. Historical cohorts were not substituted. No
`NEEDS_DECOMPOSITION=YES` span can be reported without a trace.

Required raw paths were not produced: `raw/viztracer.json.gz`,
`raw/resource_samples.jsonl.gz`, `raw/milestones.jsonl`,
`raw/session_events.jsonl`, `raw/trace_config.json`,
`raw/runtime_result_summary.json`, `raw/wrapper_snapshots.json`,
`derived/golden_profile_summary.json`, `derived/golden_profile_report.md`,
`derived/golden_profile_gantt.txt`, and `derived/report.md`.

`WINDOWS_HEAVY_LOCAL_LIFECYCLE_ISSUE=OPEN` remains separate from this remote
failure. The remote smoke stopped at deployment identity and did not exercise
the corresponding runtime path, so the local issue is not reclassified as a
Modal runtime blocker.

RECONCILED_TESTING2_HEAD=cc8907d1cb2dfffe5bf324b5d090c78ce1b4b5c5
DEPLOYED_SOURCE_MATCH=NO

REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=0

OUTPUT_EXACT=UNKNOWN

ATTENTION_BACKEND_CONFIGURED=pytorch
ATTENTION_BACKEND_RESOLVED=unknown
ATTENTION_IDENTITY_PROVEN=NO

SAGE_RUNTIME_MODE_CONFIGURED=auto
SAGE_RUNTIME_MODE_EFFECTIVE_INPUT=unknown
SAGE_RUNTIME_MODE_RESOLUTION_SOURCE=unknown
SAGE_RUNTIME_MODE_RESOLVED=unknown
SAGE_IDENTITY_PROVEN=NO

INVOCATION_ID_CHAIN_PROVEN=NO
EXPERIMENT_EVIDENCE_BUNDLE_COMPLETE=NO

VIZTRACER_RAW_PRESENT=NO
TORCH_TRACE_PRESENT=DISABLED
GOLDEN_PROFILE_COMPLETE=NO

MODAL_LOG_GANTT_PRESENT=NO
MODAL_GANTT_MATCH=NO

E27_RAW_PHYSICAL_EVIDENCE_PRESENT=NO
E27_SOURCE_MECHANISM_PROVEN=NO
E27_SOURCE_MECHANISM_PROVEN_AUDITED=NO

PERFORMANCE_COMPARISON_VALID=NO

WINDOWS_HEAVY_LOCAL_LIFECYCLE_ISSUE=OPEN

REMOTE_PROFILE_SMOKE_2=FAIL
READY_FOR_RX9=NO
