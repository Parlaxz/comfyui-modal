# Batch C7 Acceptance Hierarchy Fix Report

## Scope

This change is limited to host-side Batch-A/Batch-B/Batch-C raise ordering.
Validator semantics, runtime code, waterfall semantics, deployment behavior,
and the separate legacy `--acceptance` path were not changed.

## Old raise ordering

After the RUN 1 artifact was produced, `tools/benchmark_v2_direct.py` executed
the enabled blocks in this order:

1. Batch A validated and rendered. Any failure raised immediately.
2. Batch B validated and rendered only if execution reached it. Any failure
   raised immediately.
3. Batch C validated and rendered only if execution reached it. Any failure
   raised immediately.

Therefore a legitimate slow-H2D forensic event could fail standalone Batch A
before Batch B applied its corrected Tier-A/Tier-B telemetry contract. A Batch-B
failure could likewise prevent Batch C from producing its authoritative wrapper
verdict.

## New raise ordering

All enabled validation and rendering calls remain in the existing A → B → C
order. Only raise authorization changed:

- Batch A raises only when it fails and resolved Batch B and Batch C are both
  disabled.
- Batch B raises only when it fails and resolved Batch C is disabled.
- Batch C remains unchanged and is the final raise authority whenever enabled.

The resolved booleans passed into `main()` are used. This includes Batch C's
automatic enablement from `COMFYMODAL_V2_BATCH_C_EXPECT_PLAN_FAST_PATH=1`.
Deferred failures remain visible in their rendered blocks.

## Authority matrix

| Enabled layers | Final raise authority |
|---|---|
| A | A |
| B | B (including Batch-A-preserved gates) |
| C | C through its Batch-B wrapper |
| A + B | B |
| A + C | C |
| B + C | C |
| A + B + C | C |

## Motivating slow-H2D fixture

The focused fixture contains:

- H2D duration at 4.1 seconds, above the slow-H2D threshold;
- a `host_forensic_slow_h2d` event;
- healthy Tier-A telemetry;
- fast-path evidence sufficient for Batch C.

Results:

- strict Batch A: FAIL because its historical forensic gate rejects the event;
- corrected Batch B: PASS because the forensic cost is legitimate Tier B;
- Batch C: PASS because Batch B and the fast-path gates pass;
- final runner result with A+B+C enabled: success, with all three blocks
  rendered.

## Structural inverse fixture

The structural fixture changes the artifact identity to `restore_count=2`.
Results:

- Batch A: FAIL on freshness;
- Batch B: FAIL through `batch_a_preserved`;
- Batch C: FAIL through its Batch-B wrapper;
- final runner result with A+B+C enabled: failure raised by Batch C.

This confirms that deferral does not swallow genuine failures.

## Exact C7-owned changes

- `tools/benchmark_v2_direct.py`
  - Added two minimal host-side raise-authority predicates.
  - Changed only the Batch-A and Batch-B RUN 1 raise guards.
  - Left Batch-C's raise, validator calls, rendering calls, runtime code, and
    legacy `--acceptance` path unchanged.
- `tests/test_batch_acceptance_ordering.py`
  - Added 17 offline focused tests covering authority, deferral, rendering,
    slow-H2D acceptance, structural failure propagation, C auto-enable state,
    and informational TOTAL WALL.
- `V2_BATCH_C7_ACCEPTANCE_HIERARCHY_FIX_REPORT.md`
  - This report.

Other uncommitted files in the working tree belong to concurrent lanes and were
not modified by this C7 lane.

## Verification

Passed:

- `python -m unittest tests.test_batch_acceptance_ordering -v` — 17 tests
- `python -m unittest tests.test_batch_a_acceptance tests.test_batch_b_acceptance tests.test_batch_c_acceptance tests.test_v2_acceptance_mode -v` — 132 tests
- `python -m unittest tests.test_benchmark_v2_proof_collection -v` — 9 tests
- `python -m py_compile tools/benchmark_v2_direct.py tests/test_batch_acceptance_ordering.py`

No deployment, Modal run, or commit was performed.
