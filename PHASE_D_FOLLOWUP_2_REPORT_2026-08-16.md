# Batch D1 Follow-Up 2 — Cooperative Remote Cancellation

## Batch

D1 Follow-Up 2

## Status

**BLOCKED** — implementation and deterministic proof are complete; the live
Modal/ComfyUI proof and D1 workspace reconciliation are not complete.

## Cancellation architecture

**Other precise classification: named Modal Queue + per-attempt partition +
remote watcher thread + native ComfyUI interrupt.**

The Queue is passed by handle into the generator. The watcher consumes only its
attempt partition, sets a local cancellation event, and calls the existing
ComfyUI interrupt primitive. D3 never imports Modal SDK types.

## Existing runtime callback trace

`run_plan_stream` → `_run_plan_stream_impl` → `ExecutionContext.cancelled` →
`RuntimeExecutor.stream` → `_run_in_process` → patched
`PromptExecutor.execute_async` → ComfyUI node execution/sampling.

The pre-existing `cancelled()` checks are boundary checks, not active-sampling
polls. The new watcher supplies a local predicate and native interrupt so the
sampler can stop while executing. The watcher runs outside the remote event
loop in a daemon thread and is boundedly joined.

## ComfyUI native interrupt trace

The watcher calls:

```text
comfy.model_management.interrupt_current_processing(True)
```

ComfyUI checks the process-global interrupt state in its patched torch ops and
sampling paths, raises/handles `InterruptProcessingException`, and resets the
state at `PromptExecutor.execute_async` entry. The current Modal container is
configured for one input at a time, so the process-global primitive is targeted
under the current deployment configuration; reusable-container behavior still
requires the live proof.

## Chosen control channel

One named Queue, default name `comfymodal-v2-control`, with a partition equal to
the validated attempt/request identity. Messages are primitive JSON-like data:

```json
{"type":"cancel","partition":"<attempt>","reason":"user_cancel"}
```

## Why Queue / Dict / other

Queue is preferred because Modal 1.4.3 supports named partitions and async/live
cross-container communication. `Volume.commit()` is not visible to an already
running container without reload, so it is unsuitable for active cancellation.
Dict was not selected because it adds a less direct polling/control seam and is
not needed for FIFO per-attempt signals.

## Watcher threading model

One daemon watcher thread per invocation performs blocking Queue reads with a
bounded timeout, validates the partition/attempt, sets the local event, invokes
native interrupt, records the reason, and exits on terminal/error/cleanup.

## Hot-path overhead

No Queue calls occur in graph-node, sampler-step, progress, or result handling.
The only recurring Queue operation is the watcher thread's bounded poll.

## Transport cancellation-handle API

- `RemoteCancellationHandle.cancel(reason)`
- `ModalTransport.get_cancellation_handle(request_id)`
- `ModalTransport.cancel_attempt(request_id, reason)`
- `CancelResult.confirmed`

Queue delivery is only `pending`; confirmation comes exclusively from the
remote `cancelled` event with `confirmed: true`.

## Confirmation semantics

The remote emits an explicit confirmed terminal only after the watcher received
the matching signal and execution returned/stopped. D3 persists `canceled` only
after an explicit confirmation. Pending, unavailable, local close, and Queue
put success never count as confirmation.

## Race behavior

- Completion before cancel wins and remains `completed`.
- Confirmed user cancel maps to durable `canceled`.
- Unconfirmed/channel failure leaves durable state running and returns
  `CANCELLATION_UNAVAILABLE`/`cancel_unconfirmed`.
- Late confirmed stream termination is mapped to `canceled`, not `failed`.
- Attempt bindings and handles are released after terminal handling.

## Shutdown behavior

Shutdown uses the same best-effort remote stop primitive but always persists
`interrupted`, never `canceled`.

## Phase C drain preservation

Normal result delivery still starts the existing shielded persistence drain.
Confirmed cancellation performs bounded iterator cleanup and does not treat a
normal result drain as cancellation confirmation.

## Files changed

- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/runtime_executor.py`
- `comfymodal_runtime/modal_transport.py`
- `comfymodal_runtime/local_handle_client.py`
- `comfymodal_runtime/local_handle_owner.py`
- `experiment_modern_scheduler.py`
- `experiment_modern_routes.py`
- `__init__.py` (modern scheduler registry/route wiring only)
- `tests/test_remote_cancel_bridge.py`
- `tests/test_transport_cancellation.py`
- `tests/test_experiment_modern_binding.py`
- `tests/test_modern_experiment_scheduler.py`
- `.slim/deepwork/d1-followup2-cancellation.md`

`web/studio-playground.js` and `web/studio-experiment-mode.js` were already
dirty at batch start and were not edited by this batch. They remain outside this
batch's ownership and are an unresolved D5 workspace conflict.

## Protected runtime changes

- `modal_app.py`: accepts Queue control args, starts/stops the watcher, combines
  the local cancellation predicate, emits confirmed cancellation, and preserves
  completion-first behavior.
- `runtime_executor.py`: watcher, native interrupt bridge, cancellation marker,
  reason propagation, and terminal guard.
- `modal_transport.py`: Queue resolution/partitioned puts, transport handle,
  confirmation observation, persistent drain separation.
- `local_handle_client.py` / `local_handle_owner.py`: SDK-free handle state and
  persistent IPC Queue resolution/cancel path.

No snapshot, model-loader, UNET, CLIP, VAE, cache, or GPU-teardown architecture
was changed by this batch.

## Modal SDK version

`1.4.3`; no SDK upgrade.

## Isolated Modal probe

Not run. No paid Studio generation or accepted-app deployment was used. The
control path is covered with deterministic in-process Queue/transport fakes,
but real Queue delivery remains unproven.

## ComfyUI proof

Deterministic watcher/native-interrupt stubs pass. A real mid-sampling
ComfyUI/Modal proof was not run.

## D3 real-adapter binding

Implemented and deterministically tested. The production scheduler factory
shares one `ModalTransport`, injects it into `canonical_execution.execute_plan`,
binds attempt IDs to request IDs, and requires explicit `CancelResult`
confirmation.

## D4 running-cancel readiness

- Can replace 503? **For a confirmed supported running cancel, yes.**
- Pending/unavailable channel? **No; 503 remains truthful.**
- Remaining blockers: live Modal/ComfyUI proof and the pre-existing dirty D5
  playground seam reconciliation.

## Tests

- Combined cancellation/D3 suites after final remediation: **128 passed**, in
  both collection orders.
- D3/D4/cancellation combined pytest set before the final test-loader-only
  remediation: **168 passed**.
- Workflow/domain/routes/identity regression set: **89 passed**.
- `py_compile` for all changed Python modules: **passed**.
- `python tests/run_studio_tests.py --fake`: inner lane **1471 tests,
  93.351s, OK**; the outer wrapper exceeded the 120-second command timeout, so
  this is not a clean overall gate pass.

## Studio gate

Not accepted as a clean overall pass because the wrapper timed out and the D5
playground seam is a pre-existing unreconciled dirty file.

## Live-smoke verdict

**DO NOT START D6 — CANCELLATION REMAINS BLOCKED**

No Studio generation, accepted-app deployment, or commit was performed.
