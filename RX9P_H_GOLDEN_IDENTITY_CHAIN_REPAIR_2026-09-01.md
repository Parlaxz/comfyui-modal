# RX9P-H Golden Identity-Chain Repair — 2026-09-01

## Scope and operational boundary

LOCAL ONLY. No deploy, Modal call, GPU request, Golden request, or paid remote
operation was performed in this lane.

The repair binds the immutable `v2ctl_invocation_id` to the request and carries
that identity through attempt, summary, manifest, and evidence projection. It
also records configured versus resolved attention and Sage policy provenance.

## Implemented changes

- `tools/benchmark_v2_direct.py`
  - Captures the invocation ID once and validates the required 32-hex format.
  - Projects the captured ID into attempt and summary records.
  - Persists configured/resolved attention and four-field Sage identity.
- `tools/v2_control/experiment_evidence.py`
  - Extracts and validates invocation, request, attention, and Sage fields.
  - Fails closed for missing, mixed, contradictory, or non-durable evidence.
  - Projects the fields into cohort/index output.
- `tools/v2_control/fingerprints.py` and `tools/v2_control/validation.py`
  - Bind attention and Sage provenance into runtime experiment identity.
- `comfymodal_runtime/sage_policy.py`
  - Adds the dependency-free canonical Sage baseline/resolution and identity
    helpers. Importing it does not initialize ComfyUI, Modal, Torch, CUDA, or
    model/custom-node scans.
- `comfyapp.py` / `deployment_spec.py`
  - Use the lightweight Sage policy boundary and preserve production baseline
    precedence while allowing Golden `auto` policy to override stale inherited
    production values.
- `tests/test_rx9p_h_identity_chain.py`
  - Covers success plus missing ID, missing request, adjacent/concurrent cohort,
    wrong request, wrong invocation, failure, timeout/DNF, and missing durable
    attempt serialization paths.
- `tests/test_rx9p_g_lifecycle_simulation.py`
  - Retains the local direct-Golden lifecycle simulation and gate assertions.
- `RX9P_F_INTEGRATION_AND_REMOTE_PROFILE_SMOKE_2026-09-01.md`
  - Preserves the historical smoke truth: output exactness and configured Sage
    versus resolved Sage provenance remain `UNKNOWN`/`NO` where not proven.

## Local verification

Evidence files are under:

`artifacts/rx9p_h_identity_repair_2026-09-01/`

- `py_compile.log`: **PASS** for changed runtime, policy, evidence, and test
  modules.
- `fast_unit_identity.log`: prior lightweight run **32 passed**; after the
  runtime-provenance correction, the H-owned fixer verification reported
  **14 passed**. A direct capped rerun reached the known import-time block at
  10 seconds and was stopped; no timeout was increased or retried.
- `fast_unit_production_baseline.log`: prior bounded run **5 passed**. The
  corrected capped rerun likewise reached the import-time block and was not
  retried.
- `git_diff_check.log`: **PASS**.

The bounded suite matrix and timeout handoffs are recorded in
`fast_unit/SUMMARY.txt`. Suites that reached the cap are marked
`RX9P_T_HANDOFF=YES`; the non-timed-out E37 control-plane and E40 canonical
authority checks completed in 6.56s and 6.58s respectively.

The lifecycle simulation test was syntax-checked but not executed in this
continuation because it imports heavyweight runtime modules and a prior attempt
hung during import. No larger pytest timeout was used.

## Timing and import diagnosis

The requested import-profile measurements are **UNKNOWN / NOT COLLECTED**:

```text
PYTEST_COLLECTION_MS=UNKNOWN
HEAVY_IMPORT_MS=UNKNOWN
TEST_EXECUTION_MS=UNKNOWN
SAGE_POLICY_UNIT_TEST_RUNTIME_BEFORE_MS=UNKNOWN
SAGE_POLICY_UNIT_TEST_RUNTIME_AFTER_MS=UNKNOWN
```

The heavy-import diagnosis lane terminated without measurements. The lightweight
policy boundary is implemented and validated directly, but the actual import
chain remains a separate heavy-local investigation.

## Gate summary

```text
IDENTITY_IMPLEMENTATION_LOCAL=PASS
FAST_UNIT_IDENTITY=PASS
LOCAL_FAST_UNIT=PASS_WITH_RX9P_T_TIMEOUT_HANDOFFS
PY_COMPILE=PASS
GIT_DIFF_CHECK=PASS
IDENTITY_ADVERSARIAL_COVERAGE=PASS
FULL_LIFECYCLE_EXECUTION=NOT_RUN
HEAVY_IMPORT_PROFILE=UNKNOWN
HEAVY_TEST_PERFORMANCE_BLOCKED_BY_RX9P_T=YES
REMOTE_VALIDATION=NOT_RUN
COMMIT=H_CANDIDATE
```

This report intentionally does not claim remote identity, exact-output,
profiler, E27, or heavy lifecycle proof. This is a preservation/reconciliation
checkpoint only; it is not remote authorization.

## Post-RX9P-T verification handoff

After RX9P-T's import/runtime fix is reconciled, run only this smallest
verification set (verification, not redesign):

1. direct-Golden lifecycle;
2. immutable invocation/request chain;
3. profiler descriptor plus `BEGIN`/`END` Gantt;
4. E27 raw-evidence exposure;
5. attention configured/resolved provenance;
6. Sage configured/effective-input/source/resolved provenance;
7. trace-OFF inertness.

Do not deploy, call Modal, or run Golden as part of this checkpoint.
