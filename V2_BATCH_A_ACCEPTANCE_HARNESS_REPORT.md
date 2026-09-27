# V2 Batch-A Acceptance Harness Report

Status: HARNESS READY FOR INTEGRATION (pending concurrent runtime-lane field emission)
Date: 2026-08-14
Mode: fixture/mock validation only — **no Modal execution, no deploy, no commit**

## 1. Purpose

Prepare the benchmark harness so Batch A can be validated in ONE strict cold
RUN 1 after integration. The harness adds no optimization and does not alter
any benchmark timing semantics.

## 2. Deliverables

| File | Role |
|---|---|
| `tools/batch_a_acceptance.py` (NEW) | Pure, offline Batch-A validator: run-artifact dict in → `BatchAAcceptanceResult` out. Stdlib only; never imports repo runtime, never contacts Modal. |
| `tools/benchmark_v2_direct.py` (EDITED, additive) | `--batch-a-acceptance` flag + `COMFYMODAL_V2_BATCH_A_ACCEPTANCE=1` env alias; validates the RUN-1 artifact, prints the acceptance block, raises (non-zero exit) on FAIL. |
| `tests/test_batch_a_acceptance.py` (NEW) | 23 unittest cases: all-pass + every required failure mode, fixture-driven, no Modal. |
| `V2_BATCH_A_ACCEPTANCE_HARNESS_REPORT.md` (this file) | Required report. |

Runtime production files were NOT modified: `modal_app.py`, `model_preload.py`,
`runtime_bootstrap.py`, `comfyapp.py`, `runtime_executor.py`, `v2_waterfall.py`,
`host_hardware_telemetry.py`, `__init__.py`, `*.bat`, `comfymodal_runtime/*`.

## 3. Run-1 gates and their data sources

RUN 1 validation requires: **Fresh:YES**, **STATUS OK**, **waterfall
reconciliation <= 50 ms**. Every gate below prefers the Batch-A exact field
name (emitted by the concurrent runtime lanes) and falls back to the
authoritative current-checkout observables. **A gate never fakes a pass**:
when neither the exact field nor any fallback exists it FAILS with an explicit
"not observable" detail.

| Gate | Exact field (lane-emitted) | Fallback (current checkout) | Strict rule |
|---|---|---|---|
| Fresh | `identity.restored_instance_id`, `restore_count`, `request_count` | — | non-empty instance id AND restore_count==1 AND request_count==1 |
| Status | `waterfall_local.reconciliation_status` / `validation_status` | — | `"OK"` or `"COMPLETE"` |
| Reconciliation | `waterfall_local.reconciliation_ms` (else `waterfall`) | — | `abs(ms) <= 50.0`; None → FAIL (not resolved) |
| G1 plan→schedule order | plan marker (`run_plan_first_status_yield` / `plan_received`) before `unet_early_activation_scheduled` | event-order comparison when mono ns missing | plan < schedule (mono ns, else index) |
| G1 early schedule | `unet_early_activation_scheduled` / `unet_activation_scheduled` event | `trace.metadata._execution_unet_scheduled` | present/truthy |
| G1 snapshot UNET absent | `_execution_unet_gate` | schedule-event `snapshot_unet_absent`, result `snapshot_unet_absent` | truthy |
| G1 read count | `unet_active_read_count` / `unet_read_count` | `active_read_records` unet-filtered | == 1 |
| G1 bind count | `unet_bind_count` | `unet_fast_disk_bind_start`/`_end` events (min of start/end ops) | == 1 |
| G1 H2D count | `unet_h2d_count` / `unet_h2d_ops` | `unet_h2d` events with `duration_ms > 0` | == 1 |
| G1 no duplicate | `later_schedule_noop` (truthy required) | inferred: read==1 AND bind==1 AND h2d==1 AND schedule-events<=1 | strict, no retry |
| G1 identity match | `_identity_matches` (all True, no mismatch reasons) | event `run_plan_method_entry_gap` metadata → trace metadata | all values True |
| Models reload decision | `models_reload_decision == "skipped_generation_match"` | `models_volume_reload_reason`/`_needed` reported but does NOT pass | strict equality required |
| Models reload remote calls | `reload_models_count` / `reload_models_calls` / `models_reload_remote_calls` | `_restore_timing.reload_models_invoked==False` → `reload_models_reason=='not_invoked'` | == 0 |
| Node timestamps | `per_node_timings` rows with `start`, `end`, `duration` | `duration_ms` accepted as duration | >= 1 row, `end >= start`; per-record only, non-accounting (no cross-row reconciliation required or performed) |
| Terminal stamps | `terminal_cleanup_start` / `terminal_cleanup_end` | teardown events informational only (never pass) | both numeric, `end >= start`; `remote_cleanup_ms = end - start` |
| Transport-after-cleanup | explicit `transport_after_cleanup_ms` field only | — | never claimed when absent: printed `n/a` ("clocks not host-reconciled") |
| Host telemetry overhead | `host_telemetry_total_probe_wall_ms` | sum of `probe_wall_ms` over host probe events | `<= 20.0 ms` |
| Slow forensic trigger | `host_forensic_slow_h2d` event absent | — | absent required on healthy run; H2D duration < 4000 ms informational |
| Subprocess forensics | `host_telemetry_subprocess_calls` / `forensic_subprocess_calls` | — | == 0 when observable; informational skip when no counter exposed |

## 4. Strict RUN 1 behavior preserved — YES

No scheduling-exclusion change, no TOTAL WALL definition change, no cold/fresh
logic change, no 35 s protocol change (`V2_BENCHMARK_GAP_SECONDS` untouched),
no provider/region placement change, no retries that could turn a failed
RUN 1 into hidden extra samples. The hook validates only `index == 0`
artifacts, prints the block, and raises immediately on FAIL (aborting the
remaining runs — no silent continuation). With the flag off, the hook
short-circuits and normal benchmark behavior is byte-identical. The acceptance
block prints ONLY in validation mode.

## 5. Output block (exact)

```
BATCH A ACCEPTANCE
Fresh: YES
Status: OK
Reconciliation: 12.3 ms

G1 early schedule: YES
UNET read count: 1
UNET bind count: 1
UNET H2D count: 1
Identity match: YES

Models reload decision: skipped_generation_match
Models reload remote calls: 0

Node timestamps: YES

Terminal cleanup ms: 15.5
Transport-after-cleanup ms: n/a

Host telemetry overhead: 10.0 ms
Slow forensic trigger: NO

OVERALL: PASS
```

On FAIL a compact `FAILED CHECKS:` list follows with one detail line per
failing gate.

## 6. Test evidence (fixture/mock run JSON, no Modal execution)

`python -m unittest tests.test_batch_a_acceptance -v` → **Ran 23 tests … OK**.
Required cases, all proven:

- all-pass fixture → OVERALL PASS
- duplicate UNET event → FAIL (H2D/bind/read count gate)
- missing reload skip → FAIL (models reload decision gate)
- missing node timestamp → FAIL (node timestamps gate)
- telemetry > 20 ms → FAIL (host telemetry overhead gate)
- slow-trigger event on healthy run → FAIL (host slow forensic gate)
- reconciliation > 50 ms → FAIL (reconciliation gate)

Extras also proven: not-fresh, wrong reload decision, nonzero reload remote
calls, missing plan marker, missing identity marker, identity mismatch
reasons, end-before-start node/terminal rows, missing `per_node_timings`
list, missing reconciliation value, probe-sum fallback, slow-H2D informational
flag, render-block pass/fail layout, `validate_batch_a_file` roundtrip.

## 7. Integration dependency (must be stated honestly)

The gates read Batch-A field names that the concurrent runtime lanes are
implementing (`models_reload_decision == "skipped_generation_match"`,
`terminal_cleanup_start/end`, `host_telemetry_total_probe_wall_ms`, per-node
`start`/`end`, optional `later_schedule_noop`). Until those fields land in the
runtime result payload, a real RUN 1 fails those gates with explicit
"not observable" details — by design (strict, never faked). Fallback chains
cover the rest of the current checkout (`_execution_unet_gate`,
`active_read_records`, `unet_h2d` events, `reload_models_invoked`,
`_identity_matches`, `reconciliation_ms`).

## 8. Completion summary

```
report path = V2_BATCH_A_ACCEPTANCE_HARNESS_REPORT.md
changed files = tools/batch_a_acceptance.py (new), tools/benchmark_v2_direct.py (additive), tests/test_batch_a_acceptance.py (new), V2_BATCH_A_ACCEPTANCE_HARNESS_REPORT.md (new)
commit = none
deploy count = 0
Modal runs = 0
G1 gate = READY
models reload gate = READY
node timestamp gate = READY
terminal stamp gate = READY
host telemetry gate = READY
strict RUN1 behavior preserved = YES
ready for integration = YES
```
