# RX9P-C — E27 Source Mechanism Proof Instrumentation

Date: 2026-09-01  
Worktree: canonical `TESTING2` main  
Scope: instrumentation, persisted source/H2D evidence, fail-closed evaluator, and offline synthetic tests.

## Result

RX9P-C adds the evidence path required for a future experiment to truthfully
evaluate `E27_SOURCE_MECHANISM_PROVEN=YES`. No remote or paid run was used;
the implementation and evaluator are proven with synthetic local reads.

The evaluator emits `YES` only when all required raw evidence and predicates
are independently validated. Missing, malformed, contradictory, fallback, or
non-quiescent evidence emits `E27_SOURCE_MECHANISM_PROVEN=NO` with explicit
failed predicates. A performance result cannot promote `NO` to `YES`.

## Actual source syscall telemetry

`ActualSourceTelemetry` persists one event per physical positioned
`preadv`/`pread`/`read` syscall:

- producer and fixed region identity;
- source and destination offsets;
- requested and returned bytes;
- retry number and short-read state;
- syscall-enter and syscall-exit monotonic timestamps;
- physical-syscall provenance.

The actual source inflight counter transitions at syscall entry/exit under a
lock, with every transition timestamp persisted. Derived evidence includes
maximum actual inflight, QD0–QD4 occupancy, time-weighted mean QD, QD4 source
wall percentage, starvation gaps, and syscall interval-union busy time.

`SOURCE_TOTAL_WALL` is explicitly:

```text
first required source syscall enter -> last required source syscall exit
```

It excludes CUDA readiness, H2D completion, tensor transforms, model
construction, adoption, bind, and forward execution.

Per-producer reports include region bounds, bytes, read count, first/last
syscall, producer wall, syscall busy total, and throughput. The evaluator
reconstructs topology, ownership, monotonicity, exact source/destination
coverage, gaps, overlaps, duplicate identities, and short-read continuation
from raw evidence rather than trusting summaries.

## H2D separation

H2D submission evidence is recorded immediately before the backend submit call
and completed only when the corresponding event is reaped. The persisted
report contains per-copy bytes, submit/completion timestamps, first/last
submit, final required completion, H2D wall, source/H2D overlap, and the
post-source GPU-ready tail.

Persisted fields:

```text
SOURCE_TOTAL_WALL_MS
SOURCE_SYSCALL_UNION_BUSY_MS
H2D_TOTAL_WALL_MS
SOURCE_TO_GPU_READY_MS
SOURCE_H2D_OVERLAP_MS
POST_SOURCE_H2D_TAIL_MS
```

These are explicitly overlapping/non-additive intervals where applicable.
Dispatcher-control byte/event reconciliation is retained separately and must
agree with the raw H2D reconstruction.

## Quiescence

Bind, source-completion, and final-completion checkpoints are deep-copied and
persisted. Each records live source workers/readers, dispatcher and slot
ownership, actual syscalls in flight, queued ready blocks, free buffers, H2Ds
in flight, unreaped events, outstanding futures, fallback, poison,
reconciliation state, and ownership quiescence.

Successful transport return is fail-closed: final actual source telemetry,
H2D events, source workers/readers, dispatcher, queues, slots, and ownership
must all be reconciled and quiescent. The evaluator independently validates
the final checkpoint and requires the checkpoint history.

## Evaluator contract

`evaluate_e27_source_mechanism` independently validates these predicates:

```text
arm=static_e27
producer_count=4
fixed_contiguous_regions=true
fixed_ownership=true
monotonic_reads=true
coverage_exact=true
gaps=0
overlaps=0
unexpected_duplicates=0
actual_syscall_qd_telemetry_complete=true
max_actual_source_inflight>=4
source_total_wall_present=true
qd_occupancy_present=true
h2d_reconciliation_complete=true
fallback=0
poison=0
quiescence=true
required_evidence_persisted=true
```

The complete evaluator result, exact emitted line, and failed-predicate list
are exposed at the Golden QD result boundary. Generic callable-reader timing
does not qualify as physical E27 proof; only the explicit positioned syscall
provenance path does.

## Offline verification

- E27 source mechanism, physical integration, legacy-path, and Golden QD
  transport tests: **78 passed**.
- Golden wiring/serial/core/QD integration regressions: **180 passed, 1
  skipped, 0 failed**.
- `py_compile` for all RX9P-C Python files: passed.
- `git diff --check`: passed.
- Synthetic coverage includes QD1, concurrent QD4, serialized fake workers,
  uneven/non-divisible regions, boundaries, short reads, retries, duplicate,
  overlap, gap, source/H2D overlap and tail, leaked worker/event, fallback,
  poison, missing/contradictory evaluator evidence, provenance, and
  checkpoint-history failures.
- No Modal call and no paid run.

## Files

- `comfymodal_runtime/e27_source_mechanism.py`
- `comfymodal_runtime/golden_qd_transport.py`
- `comfymodal_runtime/golden_serial.py`
- `tests/test_e27_source_mechanism.py`
- `tests/test_e27_source_integration.py`
- `tests/test_e27_legacy_read_path.py`
- this report

No deploy/publisher/lock control plane, `tools/v2ctl.py`, production profile,
evidence finalization, `comfyapp.py`, or RX8 publication policy files were
changed by RX9P-C.

ACTUAL_SOURCE_SYSCALL_TELEMETRY=YES
ACTUAL_SOURCE_QD_OCCUPANCY=YES
SOURCE_TOTAL_WALL=YES
H2D_SEPARATION=YES
QUIESCENCE_PROOF=YES
E27_MECHANISM_EVALUATOR=YES
PERFORMANCE_BEHAVIOR_CHANGED=NO
REMOTE_CALLS=0
PAID_RUNS=0
READY_FOR_RX9=YES
