# Phase D Follow-up Reconciliation

| Field | Value |
|---|---|
| Date | 2026-08-15 |
| Parent artifact | `PHASE_D_INTERFACE_FREEZE.md` |
| Scope | C1 cancellation probe and deployment-identity propagation follow-up |
| Phase D writer status | **DO NOT START WRITERS** |
| D4 status | **BLOCKED** |

This is a read-only follow-up to the D1 freeze. It records current evidence and
does not authorize Phase D implementation, deployment, Modal execution, or real
generation.

## 1. Running-cell cancellation result

The installed Modal SDK is `1.4.3`. One isolated probe used the existing
generator path and did not use `spawn()`, Studio generation, or an accepted
deployment.

Observed sequence:

1. The invocation exposed a `function_call_id` through
   `modal.current_function_call_id()`.
2. `modal.FunctionCall.from_id(function_call_id).get_call_graph()` returned
   `PENDING`.
3. `FunctionCall.cancel(terminate_containers=False)` raised
   `modal.exception.NotFoundError: No Function Call with ID 'fc-...' found`.
4. `FunctionCall.cancel(terminate_containers=True)` raised the same error.
5. The remote generator continued yielding after both attempts.

The current transport normally retains an `in_...` input identity and its local
iterator cleanup/drain behavior is not a proven remote abort. Therefore the
truthful current result is:

**Classification: C — DIFFERENT PROTECTED ARCHITECTURE REQUIRED**

No production cancellation adapter was added. Running cells must not be marked
`canceled` merely because a local consumer stopped waiting. D3/D4 require a
supported per-invocation remote cancellation handle or a documented cooperative
remote cancellation mechanism before they can claim running-cell cancellation.

## 2. Deployment-identity propagation result

The production branch of `studio_workflow_run.build_workflow_execution_plan`
was corrected in the working tree. Its `ExecutionPlan` reconstruction now:

- preserves canonical `validation` verbatim;
- preserves canonical `deployment_identity` verbatim, including nested fields;
- preserves canonical request metadata and overlays modern Studio metadata; and
- leaves absent identity empty instead of fabricating it.

Focused regression coverage is in
`tests/test_studio_workflow_run_plan_identity.py` and covers six cases,
including non-empty identity, empty/fail-closed identity, metadata preservation,
round-trip serialization, and Phase C repair/hash preservation.

This resolves the specific propagation omission in the working tree. It is not
an accepted deployment result and does not authorize D4.

## 3. Validation evidence

- `python -m unittest tests.test_studio_workflow_run_plan_identity -v` — six
  focused tests passed.
- Modern planner/scheduler validation — `65 passed, 21 subtests passed`.
- `python tests/run_studio_tests.py --fake` — the inner Python lane reported
  `Ran 1471 tests in 82.869s` and `OK`; the outer wrapper did not complete before
  its command timeout, so this is not recorded as a clean overall gate pass.

No evidence here is a real generation or accepted-app deployment.

## 4. Current decision and next gate

1. The deployment-identity propagation issue is fixed in the working tree and
   covered by focused tests.
2. The running-cell remote cancellation blocker remains unresolved at
   classification C.
3. D4 persistence/routes/lifecycle and all Phase D writer lanes remain blocked.
4. The next owner is the protected C1/runtime seam: expose a supported remote
   cancellation handle or implement/test documented cooperative cancellation.
5. After that decision is implemented and reviewed, rerun the D1 gate before
   authorizing D2–D5 writers.

No protected runtime file was edited during this follow-up, and no commit was
created.
