# RX9P-J Heavy Import Fix and Final Local Gate

Date: 2026-09-02
Branch: TESTING2
Remote operations: none

## Result

`READY_FOR_SECOND_REMOTE_PROFILE_SMOKE=NO`.

The legacy import-time diagnostic publication scan was proven and removed from
the normal import path. The required single post-fix heavy lifecycle attempt
entered collection and executed both tests, but failed one H adversarial Sage
identity assertion. Per instruction, it was not rerun. No commit was made.

## Exact Blocker

The clean bounded reproduction used a cold `python -c` import with a five
second periodic faulthandler dump and a twelve-second process bound. The
persisted stack is:

```text
genericpath.getsize
comfyapp.py:7772 in <genexpr>
comfyapp.py:7772 in _diagnose_custom_node_requirements_context
comfyapp.py:8498 in <module>
importlib.import_module("comfyapp")
modal_app.py:4634 in build_modal_resources
modal_app.py:22838 in <module>
```

The exact filesystem operation was `os.walk(_p)` followed by
`os.path.getsize(os.path.join(_dp, f))` for every non-pyc file. The path was:

```text
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes
```

Evidence: `artifacts/rx9p_j_heavy_import_fix_2026-09-02/IMPORT_BLOCKER_STACK.txt`
and `IMPORT_BLOCKER_EVIDENCE.txt`.

This was `DEPLOY_BUILD_REQUIRED`, `DIAGNOSTIC_ONLY`, and a legacy import-time
side effect. It was not required to define runtime behavior, restore state, or
serve a request. The diagnostic also wrote only diagnostic context state.

## Fix

`comfyapp.py` now exposes `run_custom_node_build_diagnostics()` as the explicit
build diagnostic entry point. The module-level call is guarded by the opt-in
`COMFYMODAL_BUILD_CONTEXT_DIAGNOSTICS` flag, which defaults off. The complete
diagnostic implementation remains available for an explicit build diagnostic;
runtime custom-node synchronization, publication identity, and dependency/image
identity construction were not disabled.

The import-time call path is now:

```text
modal_app module body -> build_modal_resources -> comfyapp import
-> image/source/dependency identity construction
-> no Requirements Context Diagnostics
```

The post-fix cold import completed successfully in `5098.522 ms`. The remaining
time is the current local Modal image-plan/source/dependency definition work;
the diagnostic recursive size walk is absent. Full timing evidence is in
`artifacts/rx9p_j_heavy_import_fix_2026-09-02/IMPORT_TIMINGS.txt` and
`modal_app_import_after.log`.

## Verification

Broad FAST gate:

```text
python tools/test_perf.py --fast -- tests -m fast_unit
65 passed, 9865 deselected
COLLECTION=3634.103 ms
TOTAL_WALL=6594.105 ms
MEASURED_MAX_TEST_WALL=510.401 ms
```

Additional required local checks passed:

```text
H identity tests: 16 passed
Production baseline FAST tests: 49 passed, 1 deselected
Golden wiring FAST tests: 31 passed
Lightweight import proof: PASS; heavy modules absent
FAST_COLLECTION_IGNORED: count=153
py_compile: PASS
git diff --check: PASS
```

The required single heavy command was:

```text
python tools/test_perf.py --timeout 30 -m heavy_local -- tests/test_rx9p_g_lifecycle_simulation.py
```

It executed two tests:

```text
COLLECTION=6836.443 ms
SETUP=101.950 ms
CALL=552.288 ms
TEARDOWN=0.776 ms
TOTAL_WALL=9139.097 ms
TESTS_EXECUTED=2
1 failed, 1 passed
```

The first lifecycle test reached the repaired G path and passed the restore,
direct Golden trace claim, Torch boundary, Golden result, trace finalization,
descriptor, profiler BEGIN/END, persisted Gantt, and E27 evidence assertions.
It then failed at `tests/test_rx9p_g_lifecycle_simulation.py:578` during the
H adversarial `sage_resolved` mutation. The mutated top-level Sage resolved
field was `auto`, but nested persisted profiler evidence still contained
`baked_cuda`; `resolved_sage_runtime_mode()` ignored the invalid `auto` value
and retained the nested valid value, so `_compact_cohort()` returned `EXACT`.
This is the smallest remaining issue and is preserved in
`heavy_lifecycle_post_fix.log`. The second trace-OFF test passed.

No heavy rerun was performed. No deployment, Modal call, GPU request, or
Golden request was performed.

## Reconciliation

The canonical Sage resolver remains solely in
`comfymodal_runtime/sage_policy.py`; `comfyapp.py` only reexports its aliases.
The H invocation/request and attention identity tests passed. Because the
single lifecycle attempt exposed the Sage adversarial identity failure,
`SAGE_IDENTITY_VALID` is conservatively reported as `NO` and the reconciliation
cannot be committed under the requested gate rule.

The worktree preserves the RX9P-I H/T/G changes. Unrelated pre-existing dirty
and untracked files remain untouched. No commit SHA exists for RX9P-J.

Raw evidence directory:
`artifacts/rx9p_j_heavy_import_fix_2026-09-02/`

IMPORT_BLOCKER_PROVEN=YES
IMPORT_TIME_PUBLICATION_SCAN_REMOVED=YES

MODAL_APP_IMPORT_BEFORE_MS=>=30000 (cold probe timed out)
MODAL_APP_IMPORT_AFTER_MS=5098.522

FAST_TEST_BOUNDARY_VALID=YES
FAST_GATE=PASS
FAST_SUITE_TOTAL_MS=6594.105

HEAVY_LIFECYCLE_TESTS_EXECUTED=2
HEAVY_LIFECYCLE_COLLECTION_MS=6836.443
HEAVY_LIFECYCLE_WALL_MS=9139.097
HEAVY_LIFECYCLE_GATE=FAIL

INVOCATION_ID_IMMUTABLE=YES
REQUEST_INVOCATION_BINDING=YES
ATTENTION_IDENTITY_VALID=YES
SAGE_IDENTITY_VALID=NO

G_PROFILER_REPAIR_PRESERVED=YES
G_E27_REPAIR_PRESERVED=YES

AGENTS_TEST_PERFORMANCE_POLICY_ADDED=YES

REMOTE_CALLS=0
PAID_RUNS=0

RECONCILED_COMMIT_SHA=NONE
READY_FOR_SECOND_REMOTE_PROFILE_SMOKE=NO
