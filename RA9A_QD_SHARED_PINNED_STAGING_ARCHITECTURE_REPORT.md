# RA9A — QD Shared Pinned-Staging Architecture Report

## 1. Scope and verdict

This is a read-only architecture investigation. No production source was
modified, no branch/worktree was created, no Modal operation was invoked, and
no publication/S4 code was investigated. The report is based on the current
Golden Serial source, the required RA2B/RA3/RA8 reports, and historical QD4
reports and commits.

### Verdict

The preferred design is **B: a request-scoped lease-based pinned-slot pool,
initially operated in serial-exclusive mode**.

That gives Golden Serial the simple behavior of A while preserving an explicit
capacity and ownership contract for future Golden Overlapped. A pool alone is
not a QD-throughput fix: the current worker still waits on its previous CUDA
event before its next source read. The R41 source/transfer dispatcher is a
separate historical design that must not be revived blindly.

The pool owns only page-locked host staging. Each model transport retains its
own CUDA destination/backing storage owner. Releasing a staging lease must
never release adopted model storage.

## 2. Evidence basis

### Current source

The requested Golden Serial path is self-contained in
`comfymodal_runtime/golden_serial.py`; it does not use the regular
`comfymodal_runtime/clip_qd_reader.py` path.

* `GoldenQDOwner` at `golden_serial.py:1795-1835` owns `_gpu_buf` and
  `_slots`. `release_staging()` clears slots only; `release_storage()` clears
  both.
* `_qd_gpu_worker` at `golden_serial.py:2043-2138` reads into two slots per
  worker, enqueues nonblocking H2D, records a completion event, and waits for
  that slot's previous event before overwriting it.
* Golden `read_file_qd_gpu` at `golden_serial.py:2184-2584` allocates
  `qd * 2` pinned slots, starts workers, joins them, waits completion events,
  reconciles all records, creates typed zero-copy views, and returns a retained
  owner.
* `_require_transport_quiescence` at `golden_serial.py:2587-2603` requires
  joined workers, waited H2D events, complete copies, no live operation, and no
  live registered Golden QD thread.
* `GoldenSession` at `golden_serial.py:3051-3072` retains CLIP owners,
  `unet_owner`, and `vae_owner`.
* `golden_clip_load` at `golden_serial.py:4338-4619` retains one owner per
  checkpoint and proves adoption by pointer identity.
* `golden_unet_load` at `golden_serial.py:5175-5371` uses a meta skeleton and
  `assign=True`, then validates same-storage adoption.
* `golden_vae_load` at `golden_serial.py:5836-6019` constructs VAE from the
  transported views and validates device/dtype/storage identity.
* `golden_teardown` at `golden_serial.py:6673-6739` releases staging only;
  process exit owns final model/CUDA reclamation.
* `golden_serial_execute` at `golden_serial.py:6764-6868` calls CLIP, UNET,
  and VAE serially and runs teardown on success and primary failure.

The current regular CLIP QD implementation has the same function name but a
different contract: `clip_qd_reader.py:1359-1413,1571-1854` has no separate
`release_staging`, permits pin/alignment fallback, and releases its owner as a
whole on failure. It is not the first RA9A integration target.

### Required reports

* RA8 confirms `4 * 2 * 32 MiB = 256 MiB` pinned staging per transport owner,
  and confirms that cross-owner reuse does not currently exist
  (`RA8_VAE_LOAD_VARIANCE_REPORT.md:86-108`).
* RA8 explicitly leaves the healthy-host variance and any latency causality
  unproven (`RA8_VAE_LOAD_VARIANCE_REPORT.md:110-127`).
* RA3 confirms the CLIP sequence of QD transport, worker/event completion,
  owner publication, adoption, forward, and post-forward quiescence
  (`RA3_CLIP_LOAD_FORWARD_TRUTH_AND_RECOVERY_REPORT.md:13-78`).
* RA2B establishes that snapshot serialized bytes and opaque serializer
  composition are unavailable; RSS and mappings are not snapshot-size proof
  (`RA2B_SNAPSHOT_RESTORE_CONTENT_TRUTH_REPORT.md:3-29,92-126`). A request
  staging pool must therefore not be allowed to enter a snapshot capture
  boundary.

## 3. Current ownership and lifetime model

### Ownership matrix

| Resource | Current owner | Safe release boundary | Must survive staging release? |
|---|---|---|---|
| Model CUDA backing buffer | `GoldenQDOwner._gpu_buf`, retained by session/model/patcher | After all adopted views and model parameters are dead | Yes |
| Pinned host staging slots | `GoldenQDOwner._slots` | After transport quiescence | No |
| Source worker threads | `read_file_qd_gpu` local thread list and module registry | Every worker joined | No |
| CUDA completion events | Transport-local event arrays | Event completion has been proven; event references can then be dropped | No, but they protect staging reuse |
| Source file descriptors | `read_file_qd_gpu` local `fds` | After workers stop using them | No |
| Read memoryviews | Worker-local `memoryview(slot.numpy())` | Worker has finished the read | No |
| Typed tensor views | Returned `sd` plus model objects | While model/forward consumers use them | Yes, through backing storage |

### Per-role lifetime

#### CLIP

```text
checkpoint/header
    -> CLIP source workers
    -> pinned slot lease
    -> async H2D + completion events
    -> one contiguous CUDA backing buffer
    -> typed zero-copy views
    -> load_text_encoder_state_dicts / assign=True adoption
    -> session.clip_owners + clip._golden_qd_owner
    -> clip forward
    -> transport quiescent proof
    -> staging lease return
    -> CUDA backing owner remains through forward and model lifetime
```

Canonical CLIP has one checkpoint. The code supports multiple checkpoints. A
material failure exists in that path: `golden_clip_load` accumulates successful
transports locally at `golden_serial.py:4379-4439` and assigns
`session.clip_owners` only after all checkpoints succeed. If a later
checkpoint, construction, or adoption step fails, an earlier owner may not be
session-owned and `golden_teardown` cannot release its staging. RA9A must add a
request transaction registry and register every successful owner immediately.

#### UNET

```text
header/meta config
    -> pinned slot lease
    -> source workers
    -> async H2D + completion events
    -> one contiguous CUDA backing buffer
    -> zero-copy typed views
    -> meta model + CoreModelPatcher
    -> load_model_weights(..., assign=True)
    -> strict same-storage/pointer identity proof
    -> patcher._golden_qd_owner + session.unet_owner
    -> staging lease return after quiescence
    -> live UNET parameters continue using the same CUDA backing storage
```

`release_storage()` is not safe after successful adoption. `assign=True` is
the reason staging and storage must be independently owned.

#### VAE

```text
ae.safetensors/header metadata
    -> pinned slot lease
    -> source workers
    -> async H2D + completion events
    -> one contiguous CUDA backing buffer
    -> VAE views / dynamic patcher construction
    -> CUDA/dtype/storage adoption proof
    -> vae._golden_qd_owner + session.vae_owner
    -> staging lease return after quiescence
    -> VAE decode from the still-live CUDA backing storage
```

VAE should use the same pool only when it uses this same Golden QD transport
contract. A one-block VAE may use fewer slots in a generalized dispatcher, but
the current fixed worker implementation allocates the configured `qd * 2`
slots even for a small file.

## 4. Exact safe staging-reuse boundary

`copy_(..., non_blocking=True)` returning means only that the H2D operation was
enqueued. The CUDA engine may still be reading the pinned host pages. Reusing
or overwriting the slot at that point can corrupt the destination.

### Slot-generation rule

A slot generation may be overwritten or returned to a pool only when all of
the following are true:

1. The producer that can write that generation has finished, or has explicitly
   relinquished the slot generation.
2. The completion event recorded after the H2D copy exists.
3. `event.query()` is true, or `event.synchronize()` returns and a follow-up
   query is true.
4. No worker closure, dispatcher queue item, source-reader object, or pending
   callback can read or write that slot generation.
5. The lease state transition to `RETURNED` occurs under the pool lock.

### Current Golden batch proof

For the current implementation the conservative, externally observable
boundary is after:

```text
all workers joined
    AND every submitted H2D completion event waited
    AND every submitted copy marked complete
    AND exact byte/record reconciliation passed
    AND operation_live == false
    AND no Golden QD worker/operation remains registered
```

This is exactly the combination enforced by
`read_file_qd_gpu` and `_require_transport_quiescence`. Worker join alone is
insufficient: a worker can exit after enqueue while its copy is still pending.
Event completion alone is insufficient: another live producer could still
write the slot. Both are required, plus queue/closure retirement.

The current `GoldenQDOwner.release_staging()` does not enforce this proof; it
only clears Python references. It is safe because current callers invoke it
after the transport has returned and because Golden Serial has no cross-stage
transport overlap, not because the method itself checks safety.

Also, releasing Python references does not prove that the pinned allocator
immediately returns physical page-lock memory to the operating system. The
RA9A bound is an allocation/ownership bound; actual OS memlock behavior must be
measured separately.

## 5. Candidate architectures

### A. One request-scoped shared pool, sequentially reused

```text
request pool owns 8 x 32 MiB pinned slots
    -> exclusive lease to CLIP
    -> quiescence -> return
    -> exclusive lease to UNET
    -> quiescence -> return
    -> exclusive lease to VAE
    -> quiescence -> return
    -> pool close
```

**Correctness:** Strong if the entire pool is exclusively leased to one
transport and the return boundary above is mandatory. The current worker shape
can be adapted by assigning two pool slots to each worker, but the worker must
hold a lease token rather than bare slot references.

**Lifetime:** One request pool owns pinned slots. Each role retains only its
own CUDA owner. Stage completion returns slots without affecting model views.

**Complexity:** Lowest pooling complexity. No cross-transport contention in
Golden Serial. It still requires transaction cleanup and a pool-aware worker
contract.

**Failure recovery:** Abort joins workers, drains all provable events, and
returns only proven-idle slots. An uncertain slot poisons the pool for the
request rather than being recycled.

**Memory:** At the canonical setting, at most 8 x 32 MiB = 268,435,456 bytes
of allocated pinned staging for the request, instead of approximately three
retained owners / 805,306,368 bytes. A smaller pool is correct but may reduce
available concurrency; a larger pool is not justified before RA8 evidence.

**Future overlap:** Weak without an explicit partition or pool expansion.
One full exclusive lease deliberately denies CLIP/UNET source overlap. That is
safe for Golden Serial and cannot accidentally race, but it is not a complete
Overlapped design.

**Performance classification:** Allocation is paid once per request rather
than once per transport. No latency win is claimed. The current
worker-before-next-read event coupling remains unless separately redesigned.

### B. Lease-based pinned-slot pool

```text
RequestScopedStagingPool
    owns capacity-classed pinned slots
    acquire(transport, required_capacity) -> StageLease
    StageLease owns slot generations and worker references
    completion proof -> lease.release()
```

**Correctness:** Strongest when every slot has an explicit state such as
`FREE`, `LEASED`, `DMA_PENDING`, `RETURNABLE`, `RETURNED`, or `POISONED`.
Bare tensors must never be shared without a lease/generation token.

**Lifetime:** Pool lifetime is request-scoped and excluded from snapshot
capture. Lease lifetime covers the source workers, queue entries, H2D events,
and slot references. Model owner lifetime remains independent.

**Complexity:** Higher than A: condition-variable/free-list metadata, lease
identity, double-return checks, wrong-pool checks, failure poisoning, and
admission policy are required. The lock protects metadata only; it must not
wrap file I/O or H2D.

**Failure recovery:** A failed transport drains workers and all events whose
completion is known. If event recording, enqueue, event wait, or worker
retirement leaves copy state uncertain, the affected slot is poisoned. For
initial serial mode, poisoning the whole request pool is simpler and safer.
No fallback may recycle a slot whose previous CUDA read is unproven.

**Memory:** Initial capacity is 8 x 32 MiB = 268,435,456 bytes. Future
overlap must be admitted against a hard bound: two concurrent full QD4
transports require 16 slots / 536,870,912 bytes; three require 24 slots /
805,306,368 bytes. The scheduler must deny/defer overlap when capacity is not
available rather than silently degrading each transport while reporting the
same QD target.

**Future overlap:** Best fit. Golden Serial takes an exclusive whole-pool
lease. Golden Overlapped can use separate quotas or a larger explicitly
configured pool, with overlap decisions in the orchestration/scheduler layer.
Pool contention becomes visible backpressure, not an accidental CUDA race.

**Block sizes:** Key capacity classes by at least
`(block_bytes, pin_policy, device/NUMA placement)`. Do not silently use a 32 MiB
slot for a 64 MiB block. A larger block requires a larger class, multiple
contiguous slots with an explicit guarantee, or a failed admission. Canonical
CLIP/UNET/VAE all use the 32 MiB class initially.

**Performance classification:** Page-locked allocation is paid once per
request pool, not once per role. A persistent process-global pool could pay
less often, but it complicates snapshot cleanliness, cross-request ownership,
and concurrent requests; it is not the initial design. Pool reuse may reduce
allocation/page-lock churn, but latency benefit remains unproven until remote
RA8 data.

### C. Owner-local staging with explicit early release

After each successful transport and quiescence proof, call
`owner.release_staging()` immediately; retain the owner only for CUDA backing
storage and views.

**Correctness:** Correct for current Golden Serial if the release is after the
full quiescence proof. The current method itself should be guarded by a
transport proof or only be reachable through a transaction object.

**Lifetime:** Each owner still owns both resources during transport. After
release, it owns only model-backed CUDA storage.

**Complexity:** Lowest implementation change. It directly fixes retention but
does not create a reusable resource contract.

**Failure recovery:** Easier than pooling for successful stages. A failed
stage still needs explicit cleanup of any owner created before publication.
The current multi-checkpoint CLIP local-owner gap remains unless fixed.

**Memory:** Peak concurrent pinned staging is one owner, approximately
268,435,456 bytes in the serial path. Allocation/page-lock cost is paid again
for every role, so this is not an allocation-reuse design.

**Future overlap:** Unsafe as a general memory-bound strategy. Two overlapped
owners can each allocate their own 256 MiB and the peak is not centrally
admitted. It can be made correct with an external budget, but that becomes a
pool/scheduler in disguise.

## 6. Preferred architecture and request lifecycle

### Preferred name

**RequestScopedLeasedPinnedPool — B with serial-exclusive admission**

This is deliberately a constrained first mode:

* one pool per request;
* maximum canonical capacity: eight 32 MiB slots;
* one transport owns the pool exclusively in Golden Serial;
* each role gets a lease and returns it only after quiescence;
* CUDA backing owners are never placed in the pool;
* future overlap requires an explicit scheduler decision and enough capacity.

The serial-exclusive mode is the safe operational default. It is equivalent
to A at runtime, but exposes B's ownership and admission contract so a future
overlapped path cannot accidentally share busy slots.

```text
Golden request
    |
    +-- create request-scoped staging pool (lazy, bounded, not snapshot state)
    |
    +-- CLIP transport lease
    |       +-- source workers / read memoryviews
    |       +-- H2D completion events
    |       +-- join + event drain + exact reconciliation
    |       +-- return lease
    |       +-- retain CLIP CUDA owner(s)
    |
    +-- CLIP forward (no staging lease)
    |
    +-- UNET transport lease
    |       +-- join + event drain + exact reconciliation
    |       +-- assign=True adoption proof
    |       +-- return lease
    |       +-- retain UNET CUDA owner
    |
    +-- sampling
    |
    +-- VAE transport lease
    |       +-- join + event drain + exact reconciliation
    |       +-- adoption proof
    |       +-- return lease
    |       +-- retain VAE CUDA owner
    |
    +-- decode/output/durable commit
    |
    +-- teardown: assert no leases, close pool, retain model storage for
                process/session lifetime; process exit reclaims CUDA storage
```

### Common-pool worker rule

Workers may use common slots only through a lease API. A worker receives a
slot-generation handle containing pool identity, lease identity, slot index,
and generation. It cannot retain a raw slot past its generation. The transfer
side records the completion event against that generation. In a future
dispatcher design, a ready-queue item owns the generation until the dispatcher
reaps the event and returns it.

The pool lock protects state transitions and free-slot notification. It must
not serialize source reads, CPU-to-pinned writes, or H2D enqueue. In Golden
Serial there is no meaningful contention. In Overlapped Golden, waits must be
classified as pool backpressure and admission must preserve a hard bound.

### Pinning, allocation, NUMA

Pinned memory is required for the intended asynchronous H2D behavior, but it
does not need to remain permanently registered after its lease is returned.
The initial pool allocates page-locked tensors once per request and reuses them
across CLIP, UNET, and VAE. A process-global pool is deferred because it would
create cross-request and snapshot-lifetime state.

The initial implementation should not add CPU thread pinning or NUMA policy.
On multi-socket hosts, the allocation node and the GPU's PCIe/NUMA locality can
affect host-to-device traffic and page-lock behavior; this is a diagnostic
dimension for RA8/remote evidence, not a reason to add hidden placement logic.
If later evidence shows a material effect, make NUMA placement part of the
pool capacity class and admission identity.

## 7. Failure and exception contract

### Successful transport

1. Allocate/acquire a lease before starting workers.
2. Register the lease and any created model owner immediately in the request
   transaction registry.
3. Run source reads and H2D.
4. Join workers.
5. Wait every submitted completion event.
6. Validate exact records and bytes.
7. Publish typed views and perform adoption proof.
8. Return the staging lease; retain the model storage owner.

### Failure

* Allocation failure before lease activation releases partial allocations.
* Short read before H2D is a failed transport; the worker must still retire
  before its slot is reused.
* Worker, enqueue, event-record, or event-wait failure aborts the transport.
* `finally` must join every started worker before closing source descriptors or
  returning/poisoning slots.
* All completion events whose existence is known are drained.
* If completion state is uncertain, poison the slot; in initial serial mode,
  poison the entire request pool and fail closed.
* A lease is returned exactly once. Double return, wrong pool, stale
  generation, or return while DMA is pending is an error.
* Teardown errors must not replace the primary load exception.

The current Golden `read_file_qd_gpu` has strong normal-path cleanup and joins
workers in its `finally` (`golden_serial.py:2556-2584`), but its normal event
wait loop is not itself a separate failure-drain phase. RA9A must make event
draining explicit before any lease can be recycled.

The current regular CLIP QD reader has a weaker, separate failure shape:
`clip_qd_reader.py:1839-1854` closes file descriptors in `finally`, while the
normal path joins workers earlier. A shared RA9 pool must not be exposed to
that path without first giving it the same worker-retirement and lease
contract. This is a follow-up boundary, not a reason to broaden RA9A now.

## 8. Historical QD findings

### E27/E30 and C6

E27/E30 established four source workers, 32 MiB blocks, bounded staging, one
contiguous GPU destination, and zero-copy views. C6's feasibility report
explicitly did not enter production. Its local probe found one buffer
serialized, two buffers best in that probe, and three regressed
(`V2_BATCH_C6_PINNED_RING_FEASIBILITY_REPORT.md:16-45,70-99`). Those are local
mechanics/design inputs, not a remote RA9 latency result.

### R41

Historical commit `2187c5e` introduced a separate `golden/qd_engine.py`,
`golden/model_owner.py`, scheduler, and tests. The R41 report describes:

* source workers decoupled from H2D completion waits;
* a dedicated transfer dispatcher;
* a bounded eight-slot ring;
* event-driven slot return;
* join/adopt ownership and explicit failure/timeout states.

The relevant historical source locations were `_StagingRing` around
`qd_engine.py:307-339`, `CudaTransferBackend` around `158-180`, and the
completion/cleanup paths around `473-705` in commit `2187c5e`. The report's
ownership state machine and ring are useful evidence, but that package was
never the current Golden Serial implementation.

R41 also identified a concrete historical mistake: each worker waiting on its
previous CUDA event before the next source read collapses effective steady
state even when peak QD reports four. The current Golden worker retains this
coupling at `golden_serial.py:2060-2075`. RA9A must not claim that shared
staging fixes it. If future transport throughput work is needed, port the
dispatcher/backpressure contract deliberately and independently.

### E38 audits

E38 identified bounded QD buffers/events and owner-retained GPU storage, but
also flagged source-reader lifetime and post-bind CPU-owner retention as risks
(`E38O_INDEPENDENT_FULL_REPOSITORY_AUDIT.md:100-136`,
`E38A_SNAPSHOT_REACHABILITY_AND_CLIP_EXCLUSION_AUDIT.md:386-405,482-504`).
The RA9 transaction registry and snapshot exclusion rules directly address
those lifetime concerns without assuming a particular serializer behavior.

## 9. RA9A source change map (design only)

No changes are made here. Dependency order is the order in which a future
implementation should proceed.

| Order | File | Function/class | Current responsibility | Desired responsibility |
|---:|---|---|---|---|
| 1 | `comfymodal_runtime/golden_serial.py` | New request pool/lease types near `GoldenQDOwner` | No shared staging owner; owner combines storage and slots | Separate `StagingPool`/`StageLease` from `GoldenQDOwner`; define state, generation, capacity, poison, and idempotent close |
| 2 | `comfymodal_runtime/golden_serial.py` | `GoldenQDOwner` | Holds CUDA buffer and pinned slots | Hold model storage plus optional lease provenance; `release_staging` returns a proven lease, never raw shared tensors; `release_storage` is guarded by adoption lifetime |
| 3 | `comfymodal_runtime/golden_serial.py` | `_qd_gpu_worker` | Owns per-worker slots/events and waits prior event | Use lease generation handles; preserve completion proof; later dispatcher work must be a separate change |
| 4 | `comfymodal_runtime/golden_serial.py` | `read_file_qd_gpu` | Allocates owner-local slots and normal-path cleanup | Acquire pool capacity, register lease, join/drain in success and failure paths, and return/poison only after proof |
| 5 | `comfymodal_runtime/golden_serial.py` | `_require_transport_quiescence` | Checks transport stats and Golden registries | Become the required release gate, including no queued producer references and lease generation state |
| 6 | `comfymodal_runtime/golden_serial.py` | `GoldenSession` | Retains role model owners | Retain request pool and transaction registry; track every owner/lease from creation, including unpublished CLIP checkpoints |
| 7 | `comfymodal_runtime/golden_serial.py` | `golden_clip_load` | Publishes all CLIP owners after all checkpoints | Register each owner immediately; release/poison all local owners on any later checkpoint, constructor, or adoption failure; return each transport lease after quiescence |
| 8 | `comfymodal_runtime/golden_serial.py` | `golden_unet_load` | QD load, assign adoption, owner retention | Acquire/return lease transactionally; preserve same-storage proof and retain CUDA owner |
| 9 | `comfymodal_runtime/golden_serial.py` | `golden_vae_load` | QD load, VAE adoption, owner retention | Acquire/return lease transactionally; use same 32 MiB class initially |
| 10 | `comfymodal_runtime/golden_serial.py` | `golden_serial_execute` | Constructs session and runs strict stages | Establish request pool before first transport and guarantee pool close after teardown on every path |
| 11 | `comfymodal_runtime/golden_serial.py` | `golden_teardown` | Drops owner slot references and checks workers | Assert no active leases/queued slot generations, return/close pool, then retain model storage; do not call `release_storage` for adopted models |
| 12 | `tests/test_p1_golden_serial.py` | Existing owner/transport tests | Tests local owner release/idempotence and roundtrip | Add pool, quiescence, adoption, and serial reuse contract tests |
| 13 | New focused test module | Pool/lease state machine | No current shared-pool tests | Test lease ownership, poison, failure, exception cleanup, and future-overlap admission without CUDA |
| 14 | `comfymodal_runtime/clip_qd_reader.py` | `QdGpuOwner` / regular `read_file_qd_gpu` | Separate regular CLIP QD/fallback path | **Do not change in RA9A initial scope.** Adapt only in a separately reviewed integration after its fallback and thread cleanup contract is reconciled |

## 10. Required proof tests

### Local deterministic tests

1. Enqueue returns while a fake completion event is pending: lease return must
   fail and slot contents must not be overwritten.
2. Worker join without event completion: lease return must fail.
3. Event completion without producer retirement: lease return must fail.
4. Join plus event query/synchronize plus no queued generation: lease return
   succeeds.
5. Reuse the same slot with a new generation and reject stale-generation use.
6. Verify slot bytes from CLIP, UNET, and VAE synthetic transports cannot
   cross-contaminate after sequential reuse.
7. Verify eight canonical 32 MiB slots are the hard maximum and no third
   owner allocation occurs.
8. Verify CLIP, UNET, and VAE storage pointers remain unchanged after staging
   lease return.
9. Verify `release_staging()` leaves `_gpu_buf` live and `release_storage()`
   is not callable through the staging-return path.
10. Verify `assign=True` adoption remains same-storage for UNET and VAE, and
    CLIP's selected compute scope remains pointer-identical.
11. Fail during pin allocation, source read, H2D enqueue, event record, event
    wait, validation, constructor, and adoption; assert no live lease.
12. Fail on a later CLIP checkpoint; assert every earlier local owner and
    lease is cleaned up or deliberately poisoned.
13. Raise from stage code and teardown independently; assert the primary
    exception remains authoritative and the pool is closed.
14. Simulate uncertain event state; assert the slot/pool is poisoned and never
    handed to the next transport.
15. Assert `golden_teardown` cannot pass with a live lease, worker, operation,
    queue item, or pending event.

### Serial and future-overlap contract tests

16. Run synthetic CLIP -> UNET -> VAE and assert one pool allocation, three
    sequential lease intervals, and no overlap.
17. Run a one-block VAE case and assert its admitted slot count is explicit;
    no implicit 8-slot allocation is treated as a latency claim.
18. Use different block sizes and assert capacity-class mismatch is rejected
    or routed to an explicitly allocated class.
19. Attempt two full QD4 leases with an eight-slot pool and assert explicit
    admission denial/defer, not unsafe sharing.
20. Admit two transports with a 16-slot test pool and assert distinct slot
    generations and no corruption.
21. Inject slow H2D and assert the pool never recycles a busy slot. This proves
    safety only; it must not be reported as a throughput improvement.
22. Assert pool metadata locks do not cover source reads or H2D enqueue.
23. Assert active pool/leases are rejected by snapshot quiescence and absent
    from the snapshot state contract.

### Physical/remote evidence still required

The tests prove ownership and correctness contracts, not host performance.
After RA8 remote data arrives, use separate structurally valid Golden requests
and compare equivalent stage boundaries for:

* pinned allocation/page-lock time;
* retained versus allocated staging visibility;
* host memlock/RSS behavior;
* source I/O and H2D event evidence;
* adoption and constructor time;
* page faults as supporting evidence only;
* any actual VAE/sampling perturbation.

No latency result should be claimed from the architecture or local C6/R41
evidence.

## 11. Expected benefits classification

### PROVEN MEMORY/LIFETIME BENEFIT

Under the stated serial-exclusive pool contract, three simultaneously retained
256 MiB staging owners become one bounded request pool of at most
268,435,456 allocated bytes. Model CUDA backing storage remains separately
owned and live. This is a static ownership/lifetime result, not a remote
performance result.

### LIKELY ALLOCATION/PAGELOCK BENEFIT

The pool should pay page-locked allocation setup once per request rather than
once for CLIP, once for UNET, and once for VAE. Actual allocator caching,
memlock accounting, and OS page-unlock behavior are not proven here.

### POSSIBLE LATENCY BENEFIT

Less allocation/page-lock churn and less host-memory pressure could reduce
some request work. The size and consistency of any effect require RA8 remote
measurements.

### UNPROVEN LATENCY BENEFIT

No source-throughput, H2D-throughput, VAE-stage, forward, sampling, or
end-to-end latency improvement is established. The pool does not by itself fix
the current worker/event coupling or prove lower remote variance.

## 12. Final status

RA9A_COMPLETE=YES
CURRENT_PER_OWNER_STAGING_CONFIRMED=YES
SAFE_REUSE_BOUNDARY_IDENTIFIED=YES
PREFERRED_ARCHITECTURE=RequestScopedLeasedPinnedPool_B_serial_exclusive
MODEL_STORAGE_SEPARATE_FROM_STAGING=YES
EXPECTED_PINNED_MEMORY_BOUND=268435456
RA8_REMOTE_DATA_REQUIRED_FOR_LATENCY_CLAIM=YES
IMPLEMENTATION_READY_AFTER_RA8=YES
REPORT=RA9A_QD_SHARED_PINNED_STAGING_ARCHITECTURE_REPORT.md
