# V2 Batch D16 - Request-Entry Critical-Path Compression

Verdict: `D16_LOCAL_STOP_INSUFFICIENT_END_TO_END_GAIN`

Scope was local-only. No Modal deploy, request, remote validation, branch, or
commit was performed. D15 files and behavior were not changed.

## Root Cause Re-audit

The D13 source mapping still matches current main after D15:

| Boundary | Current source |
|---|---|
| method first line | `comfymodal_runtime/modal_app.py:16479-16483` |
| plan deserialize | `modal_app.py:16628-16629` |
| plan-receipt UNET schedule | `modal_app.py:16631-16645`, helper `:7749-7892` |
| signature-store first load | `modal_app.py:16647-16655`, implementation `prompt_signature_cache.py:365-378` |
| conditioning prefetch scheduling | `modal_app.py:16657-16712` |
| input-types-warm scheduling | `modal_app.py:16714-17077` |
| request snapshot-seed derivation | `modal_app.py:17079-17089`, helper `:16096-16221` |
| seed payload builder | `execution_seed.py:519-553` |
| seed payload hydration | `runtime_bootstrap.py:528-547` |
| ExecutionContext construction | `modal_app.py:17167-17184` |
| trace metadata and validation | `modal_app.py:17185-17214` |
| first status yield | `modal_app.py:17452-17459` |
| RuntimeExecutor stream | `modal_app.py:17460-17465`, `runtime_executor.py:4258-4270` |
| snapshot seed consumption | `runtime_executor.py:4133-4183` |
| PromptExecutor invocation | `_execute_v2_prompt_executor` at `modal_app.py:12455`, invocation path `:13607` |

The current path is therefore still:

```text
method entry
  -> deserialize
  -> plan-receipt UNET schedule
  -> store load / conditioning prefetch / input-types warm scheduling
  -> request seed build and hydration
  -> context, trace metadata, thread-policy validation
  -> plan_received yield
  -> executor stream resume
  -> snapshot_seed_consumed
  -> PromptExecutor
```

## Disjoint First-Cold Cost Model

The following model uses the D13/D11 request-clock boundaries and keeps the
residual after each boundary disjoint. It does not treat the D15 model-gate
change as a D16 saving.

| Disjoint setup component | Run 2 ms | Run 5 ms | Run 6 ms | Source/evidence |
|---|---:|---:|---:|---|
| method head through plan-receipt lane pickup | 32 | 18.1 | 20.4 | deserialize and G1 events |
| GAP1 before seed/context tail | 1212 | 1087.3 | 962.6 | schedule-region events |
| seed plus context/trace schedule tail | 57 | 34.6 | 39.1 | seed emit through `plan_received` |
| GAP3 status-yield to executor stream head | 206.4 | 126.3 | 17.1 | host consume/resume boundary |
| executor head through request-bound | 8.3 | 5.8 | 216.4 | seed consume/runtime-config head |
| GAP2 request-bound to validation checkpoint | 187.8 | 92.5 | 3.0 | checkpoint/identity diagnostic path |
| remaining pre-invoke residual | ~18.7 | ~128.1 | ~195.5 | prefill queue, proofs, legacy check, tail |
| **official remote method setup** | **1722.2** | **1492.7** | **1454.1** | **D11/D13 reconciled waterfall** |

The largest block remains GAP1. Its interior is not a set of independently
movable serial costs: the UNET lane, conditioning prefetch, and input-types warm
worker create GIL/CPU contention while the main thread performs the seed,
signature-store, context, and trace work.

## Seed Placement Assessment

### A. Background remote derivation

The builder is pure graph analysis, but hydration mutates request/container
bootstrap state. A safe design would only build the payload in a request-owned
worker, join at `snapshot_seed_consumed`, hydrate on the owner thread, and clear
the future in cancellation/failure paths. No such path was added.

Local measurement used `latest_benchmark_workflow.json` with 60 nodes and 42
reachable nodes:

| Measurement | Result |
|---|---:|
| inline builder wall | 0.94-1.61 ms over 10 samples |
| inline builder mean wall | approximately 1.27 ms over 30 samples |
| background worker plus immediate join | approximately 1.80 ms |
| immediate join wait | approximately 0.004 ms |
| payload seed parity | exact |

This establishes parity and shows no useful local overlap window. Under the
D13 contention shape, a Python thread would compete for the same GIL as the
plan-receipt UNET/meta work and input-types warm. The local experiment cannot
prove that the reported remote 150-400 ms intrinsic estimate would overlap
useful work rather than delay model preparation. Therefore the background
placement has no defensible first-cold saving projection and was not enabled.

### B. Local/plan-side precomputation

The current `ExecutionPlan` contains the request workflow but no equivalent
frozen topology/signature payload. Building the same seed before remote
submission would add the same work to command-to-response. The measured local
cost is approximately 1.27 ms, so it is not a meaningful replacement for the
remote block and was not moved locally.

### C. Snapshot/deployment precomputation

The seed contains request workflow topology and static signatures. The workflow
is not known at deployment/snapshot construction on the no-publish path. The
existing restore seed is intentionally minimal when no publisher payload exists.
No generic reusable intermediate representation was identified, so no snapshot
precomputation is valid.

## Signature Store Assessment

The old path remains `load_store_from_disk()` at plan receipt, with a lazy
fallback at `runtime_executor.py:2442-2445`. The store is advisory but mutable:
request misses update `_MEMO_STORE` and atomically persist it from
`runtime_executor.py:2471-2506`.

Local synthetic measurement for a 634 KiB memo:

| Path | Wall |
|---|---:|
| uncached parse/load | 11.35 ms |
| already-loaded memory reuse | 0.001 ms |
| read-only content check | 3.45 ms |

Snapshot-capture preload is not freshness-safe with the current contract. A
restored process could retain a parsed `_MEMO_STORE` while the mounted file was
changed after snapshot capture, including by a prior request. An `mtime`/size
check is not a content-generation proof; a full content check consumes much of
the disk-read cost and still needs a defined mutation protocol. The existing
load therefore remains at request time. No restore-time shift is counted.

`SIGNATURE_STORE_FIRST_COLD_SAVING_MS = 0`.

## GAP2, Legacy Preload, and GAP3

`clip_state_checkpoint` at
`comfymodal_runtime/clip_fast_hydration_wiring.py:218-310` is diagnostic-only.
The functional snapshot invariant remains synchronous at
`modal_app.py:11916-11924`. The checkpoint formatting and flush variance is
contention-amplified, but deferring it without a durable non-blocking telemetry
buffer would either lose D15/D12 evidence or move the same Python work into a
model-critical window. No change was made.

The legacy preload call at `modal_app.py:12621-12625` was verified as an
optional readiness observation. Actual bridge/future readiness gates remain in
the execution preload path and graph-side consumers. It is a plausible
secondary deferral, but the observed 5.4/110.9/5.9 ms is variable and not a
credible standalone D16 target. It was not changed in a stop-only batch.

The first status yield is a real async-generator protocol boundary. The
executor cannot advance until the host requests the next item. GAP3 therefore
remains unchanged; no risky transport decoupling was attempted for an expected
platform floor near 17 ms.

## D15 Model-Readiness Safety

No D16 code path was added, so there is no new overlap with:

- CLIP hydration or forward;
- UNET Worker A meta construction;
- D15-gated UNET Worker B GPU transfer;
- input-types warm;
- D15 `CLIP_GPU_CRITICAL_ACTIVE` state or telemetry.

The proposed background seed worker was rejected specifically because it would
introduce new GIL overlap with UNET Worker A and input-types warm without local
evidence that useful work would progress faster.

## Static End-to-End Accounting

| Metric | Run 2 | Run 5 | Run 6 | Mean/decision |
|---|---:|---:|---:|---:|
| D11 setup baseline | 1722.2 | 1492.7 | 1454.1 | 1556.4 ms |
| D16 projected setup | 1722.2 | 1492.7 | 1454.1 | unchanged |
| D16 setup delta | 0.0 | 0.0 | 0.0 | 0.0 ms |
| D15 expected model readiness | ~5950 | ~5950 | ~5950 | unchanged by D16 |
| D16 model-readiness delta | 0.0 | 0.0 | 0.0 | 0.0 ms |
| D16 net no-scheduling saving | 0.0 | 0.0 | 0.0 | 0.0 ms |

No time was moved into restore, local submission, Python restore, CLIP, UNET,
sampling, or post-sampling. The true first-cold saving is therefore 0 ms,
below the required approximately 300 ms threshold. Forcing a lower-priority
diagnostic or legacy-preload edit would not meet the objective.

## Verification

No D16 production code or D16 correctness tests were added because no
evidence-backed implementation was selected. Existing seed, store, prefetch,
and D15 tests were run locally; py_compile was run on the relevant runtime
modules. No Modal activity occurred.

```text
SEED_SOURCE = inline (unchanged)
SEED_PAYLOAD_PARITY = exact in local fixture measurement
SEED_JOIN_WAIT_PROJECTED_MS = 0.0 (no background path shipped)
SIGNATURE_STORE_SOURCE = disk/memory (unchanged)
SIGNATURE_STORE_FIRST_COLD_SAVING_MS = 0.0
STORE_FRESHNESS_PROOF = unavailable for snapshot copy; fail-closed by leaving disk load in place
GAP2_CHANGE = none
LEGACY_PRELOAD_CHANGE = none
GAP3_CHANGE = none
FIRST_COLD_ONLY_SAVING_MS = 0.0
WARM_CACHE_SAVING_EXCLUDED = YES
RESTORE_STAGE_SHIFT_EXCLUDED = YES
LOCAL_SUBMISSION_STAGE_SHIFT_EXCLUDED = YES
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
```
