# V2 Batch-C2 Acceptance — Plan Fast-Path Verification Layer

**Status:** Implemented + unit-tested. No deploy, no Modal runs, no commit.

## Purpose

Batch-B printed `OVERALL: PASS` for a run that the campaign evidence check
later invalidated.  The invalidating evidence, read straight from the
runtime-emitted trace:

```
plan_snapshot_parity.future_fast_path_eligible        = False
future_fast_path_ineligible_reason                    = "custom_nodes_generation_mismatch,dependency_proof_mismatch"
plan_proof_decision.decision                          = "legacy_validation_fallback"
plan_proof_decision.consumed                          = False
certificate_read_outcome.cert_source                  = "volume"
certificate_read_outcome.cert_decision                = "volume_read"
```

Batch-B validates structure (identity, reconciliation, G1 single-execution,
runtime-state skip, snapshot hygiene/manifest, stage-13 decomposition, host
telemetry) and cannot see the plan fast-path lane at all — so it correctly
passed while the plan-proof fast path was never consumed and the validation
certificate was re-read from the volume.  Batch-C is the acceptance layer that
closes that gap.

## Architecture

Batch-C is a **pure, offline wrapper** — `tools/batch_c_acceptance.py`
(`tools/batch_b_acceptance.py` style: module docstring, env truthiness helper,
dataclasses, `GateCheck`, render block, offline file validator).

- Imports and reuses `tools.batch_a_acceptance` helpers (`_boolish`, `_deep_get`,
  `_events`, `_num`) and `tools.batch_b_acceptance` core
  (`GateCheck`, `_env_truthy`, `_first_value`, `batch_b_config_from_env`,
  `validate_batch_b`, `validate_batch_b_file`).
- Calls `validate_batch_b(artifact, **batch_b_kwargs)` **first**.  If
  Batch-B fails, Batch-C fails unconditionally (check key
  `batch_b_acceptance`, detail `Batch B failed: <first failing batch-b check
  keys>`).
- **No Batch-B / Batch-A code was rewritten, duplicated, or re-implemented.**
- **No edits** to `benchmark_v2_direct.py`, `canonical_execution.py`,
  `comfymodal_runtime/contracts.py`, `comfymodal_runtime/modal_app.py`, or
  `comfymodal_runtime/waterfall` (none exist as a file to edit — the runtime
  evidence is read, never modified).
- Stdlib + `tools.batch_a_acceptance` / `tools.batch_b_acceptance` imports only:
  no Modal, no network, no repo-runtime imports, no subprocesses.

## The flag

```
COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1
```

- **ON:** every fast-path observable must be present (`NOT READY` is a
  fail-closed FAIL) and must agree with the plan-validation fast-path
  contract.  Verdict `PASS` only when Batch-B passes and all eight fast-path
  gates are OK.
- **OFF (unset):** every fast-path gate is `ok=True` with detail
  `expectation OFF ... - reported only, never fails`; the observed values are
  still filled into the result.  A passing run then gets verdict
  `REPORT_ONLY` (rendered as `fast-path expectation: 0 (report-only — not a
  strict fast-path PASS)`), never a strict `PASS`.

Config resolution: `batch_c_config_from_env()` starts from
`batch_b_config_from_env()` (Batch-B flags inherited unchanged) and adds
`expect_plan_fast_path`.  `validate_batch_c_file()` resolves any
`None`/defaulted argument from the environment (same pattern as
`validate_batch_b_file`).

## The 8 gates, their runtime event/metadata sources

All evidence is resolved ONLY from real emitted evidence — event metadata
first, then record-style fallbacks at `result` /
`result._restore_timing` / `result.trace.metadata` (the same record
resolution `batch_b_acceptance._snapshot_manifest` uses).  Absence is never
inferred as success.

| # | Gate key | Required observable | Runtime source |
|---|----------|--------------------|----------------|
| 1 | `fast_path_parity_eligible` | `plan_snapshot_parity.future_fast_path_eligible == True` | `plan_snapshot_parity` event, phase="setup", metadata (modal_app.py:12242; contract contracts.py:677-742) |
| 2 | `fast_path_decision` | `plan_proof_decision.decision == "plan_validation_fast_path"` | `plan_proof_decision` event, phase="setup" (modal_app.py:12897-12901) |
| 3 | `fast_path_consumed` | `plan_proof_decision.consumed is True` (normalized via `_boolish`); a `certificate_read_outcome` with `cert_source=="plan_validation"` and `consumed=False` is a **conflict** → gate fails (primary gate vs cert contract disagree) | same + `certificate_read_outcome` phase="setup" (modal_app.py:12347-12350) |
| 4 | `no_legacy_validation_fallback` | no `plan_proof_decision` with `decision=="legacy_validation_fallback"` (ready when the decision key is present) | `plan_proof_decision` phase="setup" |
| 5 | `no_cert_volume_read_fallback` | no `certificate_read_outcome` with `cert_decision=="volume_read"` or `cert_source=="volume"`, AND no `certificate_reload_start`/`certificate_reload_end` events (ready when ≥1 cert outcome or any cert reload event exists) | `certificate_read_outcome` phase="execution" (modal_app.py:12629-12652); `certificate_reload_start/end` phase="execution" (modal_app.py:12567-12625) |
| 6 | `deployment_hash_match` | `plan_snapshot_parity.deployment_hash_match == True` | `plan_snapshot_parity` phase="setup" |
| 7 | `custom_nodes_generation_match` | `plan_snapshot_parity.custom_nodes_generation_match == True` | `plan_snapshot_parity` phase="setup" |
| 8 | `dependency_proof_match` | `plan_snapshot_parity.dependency_proof_match == True` | `plan_snapshot_parity` phase="setup" |

Informational, never gated: `prompt_validation_end` (phase="execution",
modal_app.py:12849-12872) and `plan_validation_payload` (phase="setup",
step-1 instrumentation with `consumed=False`).

## Fail-closed NOT READY semantics

With the expectation ON, a gate whose observable is missing anywhere reports:

```
NOT READY: no <observable> anywhere - fail closed, evidence must not be inferred
```

and is `ok=False`.  A run with a perfect Batch-B pass but **no fast-path
events** therefore fails Batch-C (verdict FAIL) instead of passing by
absence — this is the central anti-false-pass guarantee.

## Fallback classification (identity-transition vs mismatch)

When `plan_proof_decision.decision=="legacy_validation_fallback"` (or
`consumed` is False) the `reason` string is keyword-scanned (order matters):

1. **`identity_transition`** — any of `plan_identity_incomplete`,
   `snapshot_proof_incomplete`, `snapshot_proof_invalid_or_unsupported`,
   `deployment_hash_mismatch`, `snapshot_state_unavailable`,
   `identity_mismatch`.  A brand-new snapshot/deployment identity legitimately
   cannot reuse the previous validation — diagnosable, **not** a defect.
   Wins over mismatch even when both keyword classes appear (e.g.
   `snapshot_proof_incomplete,deployment_hash_mismatch` → `identity_transition`).
2. **`repair`** — contains `repair_changed` or `repair`.
3. **`mismatch`** — any of `custom_nodes_generation_mismatch`,
   `dependency_proof_mismatch`, `workflow_registry_mismatch`,
   `registry_fingerprint_mismatch`, `validation_hash_mismatch`,
   `workflow_hash_mismatch`.  A component parity drift — the defect class the
   motivating run fell into.
4. **`unknown`** — anything else.

`fallback_reason` and `fallback_classification` are stored and rendered; with
the expectation ON the run still fails (a legacy fallback is never a fast-path
PASS), but the classification makes the *kind* of fallback diagnosable.

## TOTAL WALL is NOT an acceptance gate

`total_wall_ms` is taken from the wrapped Batch-B result and rendered as
`TOTAL WALL: <ms> (informational only)` followed by the explicit line
`TOTAL WALL NOT AN ACCEPTANCE GATE`.  The all-pass fixture carries a 60 s
TOTAL WALL and passes — proving it never gates.

## Fixtures and how they map to tests

Two self-contained bases (no imports from `tests.test_batch_b_acceptance`):

1. **`_make_all_pass_artifact()`** — passes every Batch-A + Batch-B gate with
   the default test config (identity, waterfall/waterfall_local, runtime-state
   skip `skipped_generation_match` + `runtime_state_generation_check=True` +
   `_restore_timing` with `runtime_state_reload_invoked=False` /
   `runtime_state_ms=0.0`, `snapshot_capture_hygiene`, `snapshot_manifest`,
   `output_stage13_breakdown` 150+60+40=250, `host_telemetry_total_probe_wall_ms=10.0`,
   terminal cleanup stamps, G1 events + `_execution_unet_scheduled` /
   `_execution_unet_gate`).  No fast-path events.
2. **`_make_healthy_fast_path_artifact()`** — base + the exact runtime fast-path
   events: `plan_snapshot_parity` (phase="setup", all parity True,
   `future_fast_path_eligible=True`, `future_fast_path_ineligible_reason=""`),
   `plan_proof_decision` (phase="setup", `consumed=True`,
   `decision="plan_validation_fast_path"`, `reason=""`), `certificate_read_outcome`
   (phase="setup", `cert_source="plan_validation"`,
   `cert_decision="plan_validation_fast_path"`, `hit=True`, `preflight_skip=True`,
   `consumed=True`).

Mutation fixtures on the healthy base and the tests they drive:

| # | Fixture | Mapped tests |
|---|---------|--------------|
| 3 | Legacy fallback + volume read (`legacy_validation_fallback`, `consumed=False`, reason `custom_nodes_generation_mismatch,dependency_proof_mismatch`, cert `volume`/`volume_read`, `hit=False`, `preflight_skip=False`) | `TestBatchCLegacyFallback`, `TestBatchCExpectationOffReportOnly.test_legacy_fallback_expectation_off_report_only` |
| 4 | `consumed=False` (decision legacy) on fully-eligible parity | `TestBatchCConsumedFalse` |
| 5 | Fast-path decision consumed=True but cert outcome `volume_read` | `TestBatchCCertVolumeFallback.test_volume_read_outcome_fails` |
| 6 | `certificate_reload_start`/`certificate_reload_end` events | `TestBatchCCertVolumeFallback.test_cert_reload_events_fail` |
| 7 | Parity `custom_nodes_generation_match=False`, `future_fast_path_eligible=False`, ineligible reason `custom_nodes_generation_mismatch` | `TestBatchCGenerationMismatch` |
| 8 | Parity `dependency_proof_match=False`, ineligible reason `dependency_proof_mismatch` | `TestBatchCDependencyMismatch` |
| 9 | Healthy fast-path events on a Batch-B-failing artifact (hygiene record removed) | `TestBatchCFailureWins` |
| 10 | Legacy fallback reason `snapshot_proof_incomplete,deployment_hash_mismatch` | `TestBatchCIdentityTransitionDiagnosable` |
| 11 | Missing-evidence (base #1 with expectation ON/OFF) | `TestBatchCMissingEvidenceFailsClosed` |
| 12 | Healthy fast-path base (runtime-spelled) | `TestBatchCAllPass`, `TestBatchCRuntimeSpelledHealthy`, `TestBatchCRender`, `TestBatchCFile`, `TestBatchCExpectationOffReportOnly.test_healthy_expectation_off_report_only` |

## Test results (real run)

From repo root (`python 3.11.9`), PowerShell stderr red-noise ignored:

```
python -m unittest tests.test_batch_c_acceptance -v
    Ran 21 tests in 0.027s
    OK

python -m unittest tests.test_batch_b_acceptance        (regression)
    Ran 50 tests in 0.107s
    OK

python -m unittest tests.test_batch_a_acceptance        (sanity)
    Ran 25 tests in 0.029s
    OK
```

All 21 Batch-C tests pass; Batch-B (50) and Batch-A (25) are unaffected by the
new module's imports.

## Files changed

- `tools/batch_c_acceptance.py` (new)
- `tests/test_batch_c_acceptance.py` (new)
- `V2_BATCH_C2_ACCEPTANCE_FAST_PATH_REPORT.md` (new, this file)

No existing file was modified.  No deploy, no Modal runs, no commit.
