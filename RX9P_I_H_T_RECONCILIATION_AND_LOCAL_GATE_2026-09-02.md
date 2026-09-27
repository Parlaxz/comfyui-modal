# RX9P-I H/T Reconciliation and Local Gate

Date: 2026-09-02

## Decision

`READY_FOR_REMOTE=NO`

The canonical reconciliation is not committed. The required single explicit
heavy-local lifecycle verification timed out during collection/import before
executing a lifecycle assertion. The instruction was to investigate that run
and not immediately retry it with a larger timeout; that rule was followed.

## Identity and Source State

```text
CANONICAL_TESTING2_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9
H_HEAD=3bb02cafc077bab4c8878ad4558fdb42d09f42e9
T_SOURCE_COMMIT=7fedbf48ad940b5d037ece3f810fca49c63efc7f
T_FINAL_SHA=7c8d3ce7aab944e1f8f22b5aa02212dfd25288a3
T_FINAL_SHA_IS_COMMIT=YES
H_COMMIT_PRESENT=YES
RECONCILIATION_COMMIT_SHA=NONE
AGENTS_TEST_PERFORMANCE_POLICY_ADDED=YES
REMOTE_ACTIONS=NONE
```

The T durable report tip is report-only and is not treated as a source commit.
H was already committed at the canonical TESTING2 head. The reconciliation
source changes remain in the current worktree pending a passing heavy gate.

## Reconciliation

- `comfymodal_runtime/baseline_resolvers.py` is the dependency-light baseline
  resolver module used by production and profiling paths.
- `comfymodal_runtime/sage_policy.py` retains Sage-specific policy, provenance,
  and the four-field runtime identity semantics.
- `__init__.py` uses the T lazy/bootstrap boundary to avoid heavyweight imports
  during ordinary lightweight resolver/test collection.
- `comfyapp.py` retains the compatibility boundary and production runtime
  behavior while consuming the canonical resolver layer.
- H identity and provenance fields were merged into
  `tools/benchmark_v2_direct.py` and `tools/v2_control/experiment_evidence.py`.
- G profiler/E27 repair code and evidence paths were preserved.
- `pytest.ini`, `tools/test_perf.py`, and the T probe tools were retained.
- Mixed fast/heavy test markers were corrected in
  `tests/test_production_baseline.py`.
- The explicit `pytorch` attention identity was preserved; no alias was used.

## Local Verification

All commands were LOCAL ONLY. No Modal, deployment, GPU, Golden, remote, or
paid execution was performed.

### Passed

| Gate | Result | Evidence |
| --- | --- | --- |
| Broad FAST suite | 65 passed, 9865 deselected; wall 6135.342 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/fast_suite_final.log` |
| Focused marked FAST suite | 65 passed; wall 3325.455 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/focused_fast_marked.log` |
| Supporting suite | 185 passed; wall 14381.031 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/supporting_fast_final.log` |
| H identity tests | 16 passed | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/focused_fast_marked.log` |
| Production baseline tests | 44 passed | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/supporting_fast_final.log` |
| Lightweight import proof | Passed; heavyweight modules absent | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/lightweight_import_proof.log` |
| Exclusion self-check | Passed; explicit heavy node preserved and H identity test retained | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/test_perf_self_check.log` |
| Python compilation | Passed | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/py_compile.log` |
| Diff whitespace check | Passed | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/git_diff_check.log` |

### Representative Post-Reconciliation Measurements

| Scenario | Result | Wall | Max test wall | Evidence |
| --- | --- | ---: | ---: | --- |
| Sage baseline overrides stale file | 1 passed | 1621.756 ms | 43.271 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/perf_stale_file.log` |
| Sage baseline overrides Triton fallback | 1 passed | 1640.743 ms | 44.228 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/perf_triton.log` |
| Golden Sage policy ignores production baseline | 1 passed | 1606.502 ms | 44.994 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/perf_golden_mode.log` |
| Fast control | 1 passed | 1635.004 ms | 42.568 ms | `artifacts/rx9p_i_h_t_reconciliation_2026-09-02/perf_fast_control.log` |

The T reference fast selection was 42 passed, 9845 deselected, wall
7630.840 ms, with 4859.952 ms collection. Its evidence is retained in
`artifacts/rx9p_i_h_t_reconciliation_2026-09-02/t_reference_fast_suite.log`.

## Required Heavy Gate

Exactly one explicit attempt was made:

```text
python tools/test_perf.py --timeout 60 -m heavy_local -- tests/test_rx9p_g_lifecycle_simulation.py
```

Result:

```text
TOTAL_WALL: 60027.059 ms
MEASURED_MAX_TEST_WALL: 0.000 ms (tests=0)
FAILURE: hard timeout exceeded (60.027s)
EXIT_CODE: 124
```

The captured diagnostic evidence shows that the process was still in
collection/import and never reached the lifecycle assertion. The lifecycle
module imports `comfymodal_runtime.modal_app` at module scope; the runtime then
reaches the legacy `comfyapp` import path, whose import-time publication scan
is the observed blocker. This is a collection/import problem, not evidence of
a lifecycle assertion failure. Full raw evidence is in
`artifacts/rx9p_i_h_t_reconciliation_2026-09-02/heavy_lifecycle.log`.

No larger-timeout retry was performed.

## Worktree and Artifacts

The source reconciliation and required support files are intentionally
uncommitted because the heavy gate did not pass. The evidence directory is:

`artifacts/rx9p_i_h_t_reconciliation_2026-09-02/`

The pre-existing untracked file
`RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md` was not modified.

## Next Required Action

Repair or isolate the `modal_app` to legacy `comfyapp` collection/import path,
then run the required explicit heavy-local lifecycle verification once under a
new evidence run. Only after that gate passes should the reconciliation be
committed and remote readiness reconsidered.
