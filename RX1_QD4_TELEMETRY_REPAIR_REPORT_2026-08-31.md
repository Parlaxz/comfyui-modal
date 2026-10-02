# RX1 — QD4 Telemetry Repair

Date: 2026-08-31  
Branch: `omos/rx1-qd4-telemetry-repair`  
Worktree: `.slim/worktrees/rx1`

## Objective and scope

RX1 repaired QD4 producer attribution and reduced telemetry overhead without
changing transport behavior. The scope was limited to QD4 telemetry and its
focused regression tests. QD/source scheduling, 32 MiB reads, queue and ring
sizes, dispatcher policy, CUDA stream usage, H2D behavior, cast-once behavior,
and CLIP/UNET/VAE ordering were preserved.

## Files changed by the implementation

The implementation commit changed exactly these files:

- `comfymodal_runtime/golden_qd_transport.py`
- `comfymodal_runtime/golden_serial.py`
- `tests/test_golden_qd_transport.py`
- `tests/test_ra9c_golden_qd_integration.py`

The permanent report is this file:
`RX1_QD4_TELEMETRY_REPAIR_REPORT_2026-08-31.md`.

## Producer-ID bug and fix

The legacy Golden QD path derived a producer identity from the executing
thread, including `threading.get_ident() % qd`. The dispatcher transport also
used thread identity for lease attribution. Thread identifiers are process-
and scheduling-dependent and modulo can collide or misattribute a producer.

The fix assigns producer IDs explicitly from `0..N-1` using `enumerate`/`range`
when producer threads are created. The ID is passed through the worker,
source-reader, lease, and ready-record paths. Lease and record validation now
retains that explicit ID, and no QD producer attribution depends on thread
identity.

## Always-on correctness evidence

The following remains enabled in diagnostics-OFF runs because it is required
to establish correctness and safe cleanup:

- planned/read/H2D byte reconciliation and range/record counts;
- source and H2D completion counts needed for reconciliation;
- fallback, poison, cancellation, and completion classification state;
- worker finalization, producer join, event completion, and quiescence proofs;
- staging lease generation/state checks;
- owner lifetime and adoption/ownership evidence;
- source-handle and active-operation cleanup tracking.

These paths use only the synchronization needed to protect correctness and
ownership state. They do not collect deep timing history.

## Diagnostic-only telemetry

When diagnostics are enabled, the implementation retains the forensic detail
needed to explain a QD run, including:

- entry/source/final-drain timestamps and wall durations;
- per-read latency samples and source-read intervals;
- per-worker read counters and timing detail;
- dispatcher reap, queue backpressure, lease-wait, and H2D event timing;
- H2D latency arrays and event timing data;
- dispatcher/source-QD depth samples and the source-QD timeline;
- detailed block records, allocation timing, and related forensic summaries.

Diagnostics-OFF construction does not allocate the diagnostic telemetry lock,
per-read latency arrays, per-worker diagnostic map, QD sample arrays, or QD
timeline. Diagnostic timestamp calls and diagnostic-only source-depth hooks are
also skipped. Required CUDA completion events and correctness locks/state are
not removed.

## Diagnostics-OFF semantics

Diagnostics OFF is a real low-overhead mode, not a request to fill a diagnostic
schema with defaults. Deep values that were not measured are omitted where
the enclosing detail is diagnostic-only or represented as `None`; they are
not fabricated as zero. This includes source-QD depth/timeline, depth and
latency samples, timing durations, and disabled source telemetry snapshots.
Partial diagnostic summaries likewise preserve an observed count while leaving
an unobserved duration as `None`.

Diagnostics ON initializes and records the full forensic structures. The
transport selector remains independent from the stage-diagnostics flag, so
selecting the dispatcher does not itself require enabling deep diagnostics.

## Transport behavior

Transport behavior did not change. The implementation only threaded explicit
producer identity through existing paths and gated diagnostic observation.
The existing source plan, read size, queue/ring configuration, dispatcher
handoff and event lifecycle, H2D submission/completion path, and cleanup rules
remain intact. ON/OFF tests compare transported output bytes, byte/count
evidence, and record ranges.

## Verification

- Focused RX1/QD test set: **131 passed**.
- Python compile checks: **passed** for the changed runtime and test modules.
- `git diff --check`: **passed**.
- No Modal deployment was performed.

The tests cover explicit producer IDs, diagnostics gating and unavailable
values, diagnostics-ON forensic samples, identical ON/OFF transported bytes
and correctness evidence, partial diagnostic values without fabricated timing,
and existing cleanup/quiescence behavior.

## Commits and integration

`749b6cc89e35e2896dfeef5f13502440c0021ef2` (`fix: repair QD4 telemetry
gating`) is the accepted RX1 implementation commit. It contains only the four
runtime/test changes listed above. This report is a separate docs-only commit
on the same RX1 branch.

The branch remains isolated in `.slim/worktrees/rx1` and has not been
integrated into `TESTING2`. Integration, if later requested, should preserve
the explicit diagnostics flag behavior and verify the target branch's
concurrent RX changes before applying either RX1 commit.

`TRANSPORT_BEHAVIOR_CHANGED=NO`
