# RA9C — Golden QD4 Producer/Transfer Decoupling

## Status

RA9C adds an opt-in dispatcher arm to the current Golden Serial QD transport.
The legacy transport remains the default control arm and its implementation is
not replaced.  The dispatcher is internal to one heavy-stage transport call;
Golden stage order remains CLIP load → CLIP forward → UNET load → VAE load,
with no cross-heavy-stage overlap.

## Implementation

`comfymodal_runtime/golden_qd_transport.py` owns the new transport machinery:

- `COMFYMODAL_GOLDEN_QD_TRANSPORT=legacy|dispatcher` is normalized separately
  from `COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS`; missing bookkeeping metadata does
  not prevent runtime selection.
- QD defaults are four producers, 32 MiB blocks, and an eight-slot bounded
  staging ring.  Capacity class, lease identity, slot generation, producer
  retirement, and state transitions are explicit.
- Producers read and publish only.  They never inspect or wait on H2D events.
  `TransportDispatcher` alone submits H2D work, polls/records completion, and
  returns a slot.
- Queue/ring backpressure, cancellation, bounded cleanup, uncertain event
  poisoning, worker/dispatcher primary-vs-secondary errors, exact source and
  destination coverage, short-read retry, and stale lease rejection are
  fail-closed.
- `CudaTransferBackend` accepts a caller-owned CUDA `uint8` destination and
  allocates pinned `uint8` staging.  The destination is never treated as
  staging and is not released when staging becomes reusable.  The Golden
  adapter requests H2D-only execution, so the dispatcher never materializes a
  destination back to CPU.
- Telemetry includes explicit TOTAL/PARTIAL timing scope, source bytes/read
  count, time-weighted source-QD occupancy, H2D submitted/completed bytes,
  ready depth, free-slot minimum, backpressure, event-reap and final-drain
  counters, parse/open/duplicate-read counters, fallback state, and
  owner/adoption fields.

`golden_serial.py` keeps its existing transport body for `legacy`.  The
dispatcher arm adapts into the existing `sd`, `owner`, `stats`, `tensor_map`,
and header-metadata contract, then uses the same typed-view and adoption proof
paths for CLIP, UNET, and VAE.  The selected arm is captured in request
`run_identity` and a selector event.  Each successful QD owner is registered
immediately in the request transaction registry, fixing the multi-checkpoint
CLIP cleanup visibility hole without changing backing-storage lifetime.
The dispatcher adapter uses one file descriptor per source producer on Windows,
preserves transport failure telemetry through stage errors, and scopes the
frozen request arm around each stage read so mid-request environment changes
cannot mix arms.  Dispatcher handoff state is retained until event registration
and is included in bounded cleanup.

## Local evidence

The deterministic transport suite covers source/H2D decoupling under pending
events, QD4 occupancy, bounded backpressure, stale generations, uncertain
completion poisoning, cancellation drain, primary error preservation, exact
coverage and byte reconciliation, short reads, view offsets, backing lifetime,
selector behavior, snapshot quiescence, H2D-only execution, failure telemetry,
frozen arm selection, and bounded dispatcher handoff cleanup.  Current focused
verification:

```text
python -m pytest tests/test_golden_qd_transport.py tests/test_ra9c_golden_qd_integration.py -q
36 passed

python -m py_compile comfymodal_runtime/golden_serial.py comfymodal_runtime/golden_qd_transport.py tests/test_golden_qd_transport.py tests/test_ra9c_golden_qd_integration.py
passed

python -m pytest tests/test_golden_qd_transport.py tests/test_ra9c_golden_qd_integration.py tests/test_p2_golden_core_contract.py tests/test_e30_clip_qd_io.py tests/test_v2_e2_clip_staged_hydration.py -q
109 passed, 2 failed, 1 skipped (the two failures are in concurrent durability changes outside RA9C)

python -m pytest tests/test_p1_golden_serial.py::test_vae_load_performs_single_header_and_payload_read -q
1 passed
```

The full P1 file is not a valid RA9C gate in the current shared worktree: its
durability tests are failing against concurrent durability changes outside this
lane.  No Modal deployment, source probe, or remote request was run.  Local
tests do not establish Modal-volume throughput, physical H2D timing, or a
performance win.

## Future physical A/B prescription — do not run in RA9C

1. Freeze one deploy-relevant source revision containing both arms.  Create two
   isolated experimental apps from the same `golden_p1`-equivalent deployment
   identity: CONTROL with `COMFYMODAL_GOLDEN_QD_TRANSPORT=legacy`, and TEST with
   `COMFYMODAL_GOLDEN_QD_TRANSPORT=dispatcher`.  Do not use the protected
   production app.  Record the arm in deployment and every request artifact.
2. Run the canonical public Golden procedure separately for each app: doctor,
   deploy, source-probe, post-deploy status/doctor, then exactly one Golden
   request per invocation.  Apply the capture rule: a snapshot capture and its
   directly-following request are invalid and retained, never counted.
3. Require identical workflow/model/provider policy, exact structural Golden
   validity, one request, restore count one, durability/reopen proof, zero
   seriality violations, zero nominal fallback, one source lifecycle per
   model, exact source/H2D byte reconciliation, and retained same-storage
   adoption before accepting either observation.
4. Collect at least six eligible true-cold requests per arm, serially, from
   one frozen deployment per arm with the prescribed cooldown.  Retain every
   attempt and compare equivalent full CLIP/UNET/VAE stage walls, not partial
   transport spans alone.  Report raw values plus median/mean/min/max/range,
   sample SD, and CV.
5. For every accepted request compare source bytes/read count, source aggregate
   wall and throughput, time-weighted fraction at source QD=4, source-QD depth
   timeline, ready depth, minimum free slots, producer capacity blocking,
   dispatcher reaps, H2D completion latency, final drain, parse/open counts,
   owner/adoption proof, and duplicate-read count.  Classify slow runs by
   below-QD reason before drawing a throughput conclusion.
6. Treat output SHA, durability, ownership, and seriality as correctness gates,
   not performance covariates.  A dispatcher failure may fail closed; an
   explicit fallback must be marked `DEGRADED` and excluded from the nominal
   cohort.  Do not run CLIP/UNET overlap, VAE-slack overlap, shared pools,
   FP32 casting, empty-cache changes, sampling changes, or durability changes
   in this A/B.

The physical result remains unknown until this prescription is executed by a
separate approved experiment lane.
