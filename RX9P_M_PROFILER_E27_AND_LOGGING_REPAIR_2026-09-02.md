# RX9P-M — Profiler, E27, and Logging Repair Audit — 2026-09-02

## Executive verdict

The profiler/E27 repair was deployed, but the first authorized Golden smoke
did not reach a valid generation. The request entered the intended direct
Golden adapter and proved restore/request identity, then failed during
`golden_clip_load` because `golden_serial.py` called
`golden_qd_transport.evaluate_e27_source_mechanism` while the transport module
did not expose that canonical evaluator.

That API mismatch is repaired locally. No second remote request was launched.
Remote end-to-end acceptance therefore remains **PENDING REDEPLOYMENT AND ONE
FUTURE AUTHORIZED SMOKE**.

## 1. Repair state

- Repair commit already deployed: `fb5b656` — `RX9P-M repair profiler E27 diagnostics`.
- Experimental app: `rx9p-m-profiler-e27`.
- Deployment manifest:
  `.v2ctl/deployments/deploy_20260902-133142_18f63321.json`.
- Deployment transport exit code: `0`.
- Deployment fingerprint: `18f63321ce7ff7271514a5ee3bb488918954041f0e9fa6b005b3716ed25aaf9d`.
- Current worktree additionally contains the narrow, not-yet-deployed API fix:
  - `comfymodal_runtime/golden_qd_transport.py`
  - `tests/test_e27_source_mechanism.py`
- Pre-existing untracked reports were not modified.

## 2. What the deployed repair established

The deployed change in `fb5b656` established the intended diagnostic path:

- `COMFYMODAL_V2_FULL_TRACE=1` is applied at restore time.
- `COMFYMODAL_V2_E27_FORENSICS=1` is applied for measurement.
- `COMFYMODAL_GOLDEN_QD_TRANSPORT=static_e27` selects the canonical static
  transport arm.
- Direct Golden request entry claims the restore-created full-trace session
  before model work.
- Profiler lifecycle, E27 summary, Sage, attention, and waterfall blocks are
  emitted without fabricating missing evidence.

Local validation before and after the API fix covered the focused profiler,
E27, Sage, CLI, backend, and Golden transport paths. The focused suite after
the fix passed:

```
168 passed, 0 failed, 2 skipped
```

Additional checks after the fix:

- canonical evaluator identity import: **PASS**;
- Python compilation: **PASS**;
- `git diff --check`: **PASS**.

## 3. Authorized remote smoke evidence

Run manifest:
`.v2ctl/runs/run_20260902-133449_eb332bc5.json`

Cohort:
`artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_18-33-36_0d4d79/`

Invocation and request:

- v2ctl invocation: `752f1e78d0dd4172877ea1775433d236`;
- request: `golden-p1-0-8dbf6b4778d2`;
- method: `run_golden_serial_stream`;
- cohort attempts: `1` requested, `0` valid, `1` invalid;
- backend elapsed: `74.297` seconds;
- run exit code: `1`.

The request artifact proves:

- `restore_count=1`;
- `request_count=1`;
- `single_use_containers=true`;
- a distinct restore session, instance, nonce, task, boot, image, cloud, and
  region identity;
- DynamicVRAM activation succeeded;
- output durability mode was `off`.

The request did **not** prove:

- a terminal result;
- output SHA;
- resolved attention backend;
- resolved Sage mode;
- E27 physical source evidence;
- a completed full-trace profiler artifact.

Raw event evidence:
`.../attempt_0_events.json:3-5,6-28,30-82`

Failure:

```
RuntimeError: golden_qd_transport_failed[clip]:
AttributeError: module 'comfymodal_runtime.golden_qd_transport' has no
attribute 'evaluate_e27_source_mechanism'
```

The remote waterfall independently classifies `golden_clip_load` as
`FAILED`, followed by successful `golden_teardown`. The remote log also shows:

- `request_claim ... status=claimed`;
- `request_trace_start ... status=ok`;
- Torch profiler start skipped because `torch_disabled`;
- `request_trace_stop ... status=error reason=RuntimeError`;
- full-trace artifact status `absent`;
- E27 `EVIDENCE_AVAILABLE=NO` with
  `E27_FAILURE_REASON=physical_actual_source_report_unavailable`.

This is a failed smoke, not a valid Golden observation and not evidence of a
successful E27 transport.

## 4. Root cause and narrow fix

`golden_serial.py:3692-3700` uses the transport module as the integration
surface for the canonical E27 evaluator:

```python
transport_module.evaluate_e27_source_mechanism(actual_source_report)
```

Before the fix, `golden_qd_transport.py` imported only
`ActualSourceTelemetry`; the evaluator remained defined solely in
`e27_source_mechanism.py`. Therefore the first static-E27 CLIP transport call
failed after physical transport setup and before the report could be emitted.

The fix:

- imports `evaluate_e27_source_mechanism` alongside
  `ActualSourceTelemetry` in both normal and direct-file import paths;
- exports it from `golden_qd_transport.__all__`;
- adds `test_transport_exposes_canonical_e27_evaluator` to prevent this
  integration-surface regression.

No fallback, reread, second H2D, or relaxed E27 predicate was added.

## 5. Profiler interpretation

The request did successfully claim the restore-created full-trace session, so
the original stale-import-gate problem was not reproduced on this request.
However, the request failed before normal Golden completion and full-trace
finalization returned an error/absent artifact. The missing profiler artifact
cannot be treated as proof that the repaired profiler path works or fails in a
successful request.

`torch_disabled` refers to the independent Torch-profiler gate; it does not
invalidate the Python full-trace claim, but it means no Torch profiler output
was expected from this configuration.

## 6. Acceptance boundary and next action

Current status:

```
LOCAL_API_FIX=PASS
DEPLOYED_REMOTE_SMOKE=FAILED_API_MISMATCH
PROFILER_SUCCESSFULLY_FINALIZED=UNPROVEN
E27_PHYSICAL_EVIDENCE=UNPROVEN
GOLDEN_END_TO_END_ACCEPTANCE=PENDING
```

Because `golden_qd_transport.py` is deploy-relevant, the next remote operation
must first redeploy the exact current source to the same isolated app, rerun
`source-probe`/status checks, and only then use one explicitly authorized
Golden smoke. The failed request remains retained and must not be overwritten
or counted as a valid observation.
