# RX9P-K Sage Identity and Final Local Gate

Date: 2026-09-02
Branch: TESTING2
Scope: local only
Remote/Modal/Golden/GPU operations: none

## Sage failure diagnosis

The initial cheap reproduction ran:

```text
python -m pytest -q tests/test_rx9p_g_lifecycle_simulation.py::test_direct_golden_repaired_lifecycle_persists_and_projects_every_gate --tb=long
```

It failed only at `tests/test_rx9p_g_lifecycle_simulation.py:578`, label
`sage_resolved`. The mutated resolved field was `auto`, but classification was
`EXACT`.

The exact mismatch was proven by direct helper invocation and persisted in
`artifacts/rx9p_k_sage_identity_final_gate_2026-09-02/sage_identity_direct_reproduction.json`:

```text
EXPECTED_SAGE_RESOLVED=baked_cuda
MUTATED_EXPLICIT_SAGE_RESOLVED=auto
PROJECTED_ACTUAL_SAGE_RESOLVED=baked_cuda
FAILING_FIELD=sage_runtime_mode_resolved
FAILING_ASSERTION=classification['exact'] in {'MISMATCH', 'INCOMPLETE'}
CLASSIFICATION=EXACT
SOURCE_OF_ACTUAL_VALUE=attempt_0.json -> full_trace_artifact -> golden_telemetry -> sage_runtime_mode_resolved=baked_cuda
```

`resolved_sage_runtime_mode()` discarded explicit `auto` resolved evidence,
allowing the nested stale `baked_cuda` value to win. The test expectation was
correct. The production fix now tracks explicit `auto` only under resolved
evidence keys and returns `mixed` for `auto` plus an observed executing mode.
Auto-only remains unknown (`""`); policy keys remain separate. Golden retains
`configured=auto`, and `resolved` can only be `baked_cuda` or
`triton_fallback`. `_golden_p1_runtime_provenance()` now reuses this canonical
projector and preserves its `missing` sentinel.

## Verification

Required offline FAST identity, Sage policy, production baseline, Golden
wiring, evidence, and validation tests passed:

```text
185 passed, 4 deselected
TOTAL_WALL=9322.256 ms
MEASURED_MAX_TEST_WALL=690.920 ms
EXIT_CODE=0
```

Focused follow-up coverage was 21 passed, 7 deselected. `py_compile` passed for
the changed Sage/evidence and resolver modules. `git diff --check` passed.

FAST evidence:
`artifacts/rx9p_k_sage_identity_final_gate_2026-09-02/fast_identity_gate_final.log`

## Final heavy attempt

Exactly one final heavy command was run, as required:

```text
python tools/test_perf.py --timeout 30 -m heavy_local -- tests/test_rx9p_g_lifecycle_simulation.py
```

It failed during collection before any test executed. The process terminated
with Windows access violation `3221225477`; the captured stack was in
`comfymodal_runtime/publication_policy.py:242` inside `is_excluded_name()`.
No retry was made. Therefore the final heavy attempt did not prove the
lifecycle assertions.

Heavy evidence:
`artifacts/rx9p_k_sage_identity_final_gate_2026-09-02/heavy_lifecycle_final.log`

The J repair remains preserved: the recursive requirements-size diagnostic is
inside the explicit `run_custom_node_build_diagnostics()` entry point, and its
module-level call is guarded by `COMFYMODAL_BUILD_CONTEXT_DIAGNOSTICS` at
`comfyapp.py:8534-8539`.

## Worktree / commit

No commit was created because the final heavy lifecycle gate failed. Existing
H/T/G/J reconciliation files remain untouched and uncommitted. The unrelated
pre-existing dirty artifact is:

```text
RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md
```

The final report itself is scoped RX9P-K evidence. No reset, stash, clean,
revert, or remote operation was performed.

SAGE_FAILURE_ROOT_CAUSE_PROVEN=YES
SAGE_IDENTITY_VALID=YES
SAGE_ADVERSARIAL_TEST=FAIL

FAST_GATE=PASS

HEAVY_LIFECYCLE_TESTS_EXECUTED=0
HEAVY_LIFECYCLE_GATE=FAIL
HEAVY_LIFECYCLE_WALL_MS=7172.589

IMPORT_TIME_PUBLICATION_SCAN_REMOVED=YES
G_PROFILER_REPAIR_PRESERVED=YES
G_E27_REPAIR_PRESERVED=YES
FAST_TEST_BOUNDARY_VALID=YES

REMOTE_CALLS=0
PAID_RUNS=0

RECONCILED_COMMIT_SHA=NONE
READY_FOR_SECOND_REMOTE_PROFILE_SMOKE=NO
