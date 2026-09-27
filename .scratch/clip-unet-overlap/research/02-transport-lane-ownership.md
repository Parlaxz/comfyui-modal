# Transport Lane Ownership Proof

## Finding
A request-local UNET lane qualifies only when the operation owns (or is passed) one request-local `GoldenTransferResources`, uses its dedicated `h2d_stream`, leases pinned arena slots, records and harvests the slot event pair, joins all source workers, drains every outstanding H2D event, and passes exact record reconciliation before exposing zero-copy views. The legacy arm is a valid control/reference arm, but it is not proof of a request-local shared arena or dedicated reusable stream. `dispatcher` qualifies only through its resource-backed/static-E27 path; `static_e27` qualifies with resources and the fixed QD contract. `decoupled` is rejected for this ownership proof because `read_file_qd_gpu` routes it to `_read_file_preplanned_gpu`, not the `GoldenTransferResources` lane. A CPU-prefetch ticket forces `legacy` and likewise does not establish the request-local arena/stream proof.

## Evidence
- `comfymodal_runtime/golden_serial.py:6654-6729`, `read_file_qd_gpu`: arm selection; resources force `static_e27`; `decoupled` takes a separate preplanned path; CPU ticket forces legacy.
- `golden_serial.py:5572-5603`, `_read_file_qd_gpu_dispatcher`: resources are supplied to `CudaTransferBackend`; static-E27 is restricted to QD 1/2/4/8 (the error text is stale, but the predicate is authoritative).
- `golden_qd_transport.py:93-155`, `GoldenTransferResources.__init__`: one arena, stable views, one H2D stream, per-slot `(start,end)` events, span events, active-ticket/active-transport accounting, poison and lifecycle counters.
- `golden_qd_transport.py:170-209`, `GoldenTransferResources.create`: exactly one pinned arena allocation; logical slots are slices; creates one `torch.cuda.Stream` and event pairs.
- `golden_qd_transport.py:275-321`: slot lease is exclusive (`_active_tickets`), submit records both events on `h2d_stream`, harvest marks completion/timing, and return refuses incomplete/unharvested tickets.
- `golden_qd_transport.py:250-273`: span events are recorded on the same stream; telemetry explicitly states the active-union proof is single-stream/non-overlap (`:363-367`).
- `golden_qd_transport.py:376-388`: close rejects active tickets/transports and unsurfaced poison, then drops arena/views/events/stream.
- `golden_serial.py:5253-5348`, `_QDReaderState`: authoritative submitted/completed/error ledger, per-worker counts/finalization, and `workers_joined`/`events_waited` proof flags.
- `golden_serial.py:5351-5476`, `_qd_gpu_worker`: two pinned slots per worker; reuse waits on the prior slot event; `copy_(..., non_blocking=True)` and completion event are queued; worker always finalizes in `finally`.
- `golden_serial.py:6953-6993`: joins every worker, joins CPU source owner when present, then host-waits all outstanding completion events.
- `golden_serial.py:7022-7205`: validates exact coverage/read/H2D submission/completion and rejects errors, missing finalization, or incomplete copies.
- `golden_serial.py:7206-7244`: only after proof does it create typed zero-copy views and retain `GoldenQDOwner`.
- `golden_serial.py:4915-4956`, `GoldenQDOwner`: views remain valid only while owner lives; owner retains CUDA buffer and staging slots; `release_staging` is safe while views live, while UNET storage is intentionally retained.
- `golden_serial.py:7282-7298`, `_require_transport_quiescence`: stage boundary requires joined workers, waited events, complete copies, `operation_live=False`, and no registered live threads/operations.

## Dedicated-stream proof and external authority
PyTorch’s CUDA notes state that a stream is a linear sequence, operations within one stream are serialized, while different streams may overlap unless synchronized. Therefore the resource path’s explicit `record(self.h2d_stream)` for both event endpoints and all H2D submissions proves ordering on that stream; it does not by itself prove consumer ordering on another stream—consumer use must occur after the host event wait or an explicit consumer-stream wait. Non-blocking CPU-to-GPU copies require pinned host memory, matching the arena contract. Sources: [PyTorch CUDA semantics](https://pytorch.org/docs/stable/notes/cuda.html) and [torch.cuda Streams/Events API](https://pytorch.org/docs/stable/cuda.html).

## Join/drain proof shape
The smallest credible proof is an operation handle whose `join()` is the sole boundary that: joins every producer, waits/queries every slot completion event, harvests and returns every ticket, marks the operation quiescent, and surfaces worker/transport errors. The caller then invokes `_require_transport_quiescence`-equivalent validation before adopting views. `GoldenTransferResources.close()` must happen only after `join()` and must reject any residual active ticket/transport or unacknowledged poison.

## Smallest seam
Do not alter scheduling. Add a narrow joinable transport-operation seam at the dispatcher/resource boundary (conceptually `transport = begin(...); ...; transport.join()`), exposing only `join()` plus proof/telemetry and `close()`/poison handling. It should reuse `GoldenTransferResources` and `_QDReaderState`; it must not return a view/owner before join+drain. A bare thread future, stream object, or completion event is insufficient because none proves all workers, leases, events, accounting, and operation registry are quiescent together.

## Rejected claims
Timing counters are not ownership proof; `GPU_COPY_ACTIVE_UNION_PROOF` is a consequence of one-stream ordering, not evidence that an arbitrary caller used that stream. `GoldenQDOwner` proves lifetime of returned storage/staging, not that transport work is still live. Legacy’s per-worker pinned allocations/events and the decoupled/preplanned path can be functionally correct, but reject them when the acceptance criterion specifically requires request-local arena + dedicated H2D stream identity.
