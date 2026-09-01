# RX4 — Final Parallelization Architecture Audit

**Date:** 2026-08-31  
**Status:** PARKED — design only; no runtime implementation was made.  
**Runtime code:** unchanged by this report.

> **GOLDEN SERIAL REMAINS SERIAL.** No parallelization implementation should
> begin until serial performance is satisfactory and the serial reference has
> a complete, trustworthy critical-path record.

The future design belongs in an explicit Golden Overlapped orchestrator. It
must reuse independently understandable stage functions and existing evidence
mechanisms. It must not hide future-stage scheduling inside Golden Serial or
inside a function whose name says it owns only one stage.

## Parked gate

This plan is explicitly **PARKED until serial optimization is satisfactory**.
Before any overlap work is admitted:

- Golden Serial must remain the reference schedule.
- Serial endpoint and stage performance must be stable and measured.
- The serial path must have complete raw event evidence, exact output proof,
  and reconciled stage walls.
- Any later overlap must be a separately named, opt-in experiment.
- A successful output or a CUDA capability test is not evidence of an endpoint
  improvement.

## Future candidate ordering

1. Move CLIP source loading and preparation left.
2. Prepare VAE during sampling using CPU/source/pinned work only.
3. Optionally overlap VAE H2D with sampling after lifecycle repair.
4. Overlap CLIP forward with UNET source I/O only.
5. Consider UNET H2D overlap only after source-only overlap is positive.

## Shared rules for every candidate

- Separate source I/O, CPU work, pinned staging, H2D, GPU compute, and model
  mutation in telemetry and scheduling.
- A CUDA operation being asynchronous does not make it useful to overlap.
- Every producer stream must publish a completion event; every consumer must
  wait on that event before consuming the result.
- Avoid device-wide synchronization unless it is an explicitly measured
  fallback.
- Model-manager and `ModelPatcher` mutation have one owner at a time.
- A reader/source fence must retire all readers before demand loading or source
  owner release.
- Snapshot state must be quiescent and intentionally model-free.
- Cancellation must stop work, join workers, close readers, release owners, and
  leave no future or model mutation pending.
- Raw traces and the actual first-result endpoint outrank summaries or labels
  such as “prefetch,” “QD,” or “overlap.”

## 1. CLIP forward || UNET load

### Legal start and end

- **Earliest CLIP forward:** after CLIP bind and input preparation, at the
  actual `clip_encode_start`/forward boundary, not at worker submission.
- **Earliest UNET work:** source read after request/plan identity is known, or
  through an explicitly validated post-restore prewarm future.
- **Latest UNET completion:** `unet_device_ready` and patcher adoption before
  graph UNET demand/first UNET forward.
- **Safest initial overlap:** CLIP GPU compute with UNET source read only.
- **Initially defer:** UNET H2D, GPU commit, patcher mutation, and `.data`
  rebinding until CLIP forward has completed.

### Work and ownership

- **CPU:** worker submission, metadata, source-reader coordination, and model
  manager bookkeeping.
- **Source I/O:** UNET checkpoint read, measured independently from H2D and
  commit.
- **Pinned memory:** bounded UNET staging/bounce buffers, budgeted together
  with CLIP QD staging.
- **H2D:** UNET copy stream, initially after source read and CLIP forward.
- **GPU compute:** CLIP forward owns the compute stream. UNET loading must not
  add a hidden compute phase.

### Required events and fences

```text
clip_encode_start
clip_forward_start
clip_forward_end
unet_lane_submitted
unet_worker_first_instruction
unet_source_io_start
unet_source_io_end
unet_gpu_transfer_start
unet_gpu_transfer_end
unet_device_ready
source_fence_valid
mutation_lane_acquired
mutation_lane_released
copy_event_recorded
copy_event_waited
```

The UNET consumer stream must wait on its producer CUDA event. The mutation
lane must cover only the GPU commit/bind section, not the cold source read.

### Lifetime and manager constraints

- Readers and file handles remain alive until the source fence retires every
  worker.
- Pinned buffers remain alive until H2D completion.
- CUDA-backed storage remains alive after bind when tensors are zero-copy views.
- `ModelPatcher` and model-manager mutation remain single-owner.
- No concurrent `load_models_gpu`, patcher rebinding, or cache publication.
- Source-fence failure blocks demand loading; it must not silently enter a
  native loader fallback.

### Allocator and expected saving

CLIP currently performs approximately 14.53 GB of BF16→FP32 destination writes
per forward. Concurrent UNET allocation/H2D can increase VRAM pressure,
allocator work, and synchronization. `empty_cache()` is not a material
optimization here; measured calls are approximately sub-millisecond to 2 ms.

Theoretical upper bound is the hidden UNET source-read wall, approximately
477 ms in corrected E28 configuration. No accepted net saving exists: source,
CPU, and memory contention can make CLIP slower than the hidden work is worth.

## 2. VAE preparation during sampling

### Legal start and end

- **Earliest safe start:** sampling start, after VAE identity and CPU state are
  fixed.
- **First implementation:** VAE source read, CPU preparation, and bounded
  pinned staging during sampling; do not perform GPU mutation.
- **Latest completion:** H2D/bind after `sampling_end`, before VAE decode.
- **Decode:** only after VAE readiness and mutation ownership are proven.

### Work and ownership

- **CPU:** VAE resolution, source read, state preparation, and pinned staging.
- **Source I/O:** may overlap sampling only with validated source identity and
  reader ownership.
- **Pinned memory:** bounded staging retained until copy completion or cancel.
- **H2D:** not part of the first VAE preparation experiment.
- **GPU compute:** sampling owns compute; VAE decode remains after sampling.

The current experimental path attempts side-stream VAE pre-copy during
sampling, followed by a narrow post-sampling bind. That path is not yet safe
enough to admit without the repairs below.

## 3. Optional VAE H2D during sampling

### Legal start and end

- **Earliest start:** after sampling begins and the VAE CPU/pinned staging is
  complete enough to submit a bounded copy.
- **Latest completion:** copy completion and stream visibility before the
  post-sampling mutation-lane bind.
- **Required consumer point:** VAE ready before decode, never merely “copy
  submitted.”

The sampling stream owns sampling compute. A dedicated VAE copy stream may own
H2D, but the consumer stream must wait on a request-scoped completion event.

### VAE concurrency correctness blockers

The current implementation has P0/P1 blockers:

- `_VAE_SAMPLING_END_EVENT` is process-global and sticky.
- The worker ignores the sampling-end wait result.
- Mutation-lane acquisition success is not enforced.
- `MutationLane` timeout handling is broken: the remaining timeout is not used.
- `Condition.wait()` plus `notify_all()` does not guarantee the documented FIFO
  behavior.
- The early-start worker is a raw daemon thread.
- Finalization cancels state/future but does not join the worker.
- Some runtime sampler paths swallow activation failures.

These are correctness blockers, not telemetry polish. Request-scoped barrier
state, enforced wait/acquire outcomes, reliable timeout semantics, and joined
worker cleanup are prerequisites.

### Required events and fences

```text
vae_schedule
vae_source_io_start/end
vae_pinned_stage_start/end
vae_h2d_start/end
vae_copy_complete
sampling_start
sampling_end
sampler_mutation_release
vae_mutation_acquire
vae_ready_terminal
vae_decode_start/end
worker_joined
```

Before binding, confirm request liveness, successful copy completion, stream
visibility, successful mutation-lane acquisition, and exact VAE identity.
Release the lane in `finally`. Finalization must cancel and join the worker.

### Lifetime, snapshots, and allocator

- VAE CPU tensors, pinned buffers, GPU tensors, and patcher identity live
  through decode.
- No VAE worker, future, CUDA owner, active reader, or request state may enter
  the CPU snapshot.
- Restore must not inherit a sampling event from an earlier request.
- Do not rebind while the sampler owns the mutation lane.
- Sampling activations and VAE allocation share VRAM headroom; record allocated,
  reserved, and peak memory rather than assuming copy/compute overlap is free.

E29 measured approximately 34 ms of VAE model management and 430.7 ms of VAE
decode. Only the approximately 34 ms load/management portion is plausibly
hideable; decode is not hidden by sampling in this design.

## 4. Push CLIP load/preparation left

### Legal start and end

1. Keep the snapshot model-free and quiescent.
2. After Python resumes and `modal_restore_exit` occurs, obtain the frozen
   manifest.
3. Start CLIP source loading before method entry or plan arrival.
4. Complete source read, pipeline preparation, and optional H2D.
5. Record CUDA readiness.
6. At demand, verify identity and bind exactly once.
7. Retain the source owner until all adopted tensor views are dead.

The current proven application-level start is post-restore. Python cannot run
before Python resume. E29 corrected an earlier invalid timestamp claim, so
CLIP-versus-restore contention remains unknown without the missing raw artifact.

### Work and ownership

- **CPU:** manifest validation, header parsing, worker submission, and pipeline
  selection.
- **Source I/O:** QD or fastsafetensors read.
- **Pinned memory:** E30 QD4 × 32 MiB is approximately 128 MiB bounded staging.
- **H2D:** one contiguous GPU destination buffer with asynchronous copy.
- **GPU compute:** no CLIP forward during preparation; forward follows bind.

The E30 QD reader uses disjoint tensor-aligned `preadv` ranges and zero-copy GPU
views. Remote proof of queue depth and throughput remains incomplete.

### Required events and fences

```text
clip_manifest_available
clip_source_submit_start/end
clip_read_begin/end
clip_source_first_completion
clip_source_last_completion
clip_copy_to_device_start/end
clip_device_ready
clip_spec_record_publish
clip_qd_take
clip_bind
clip_owner_retained
source_fence_valid
```

After a successful speculative take, demand must not reread the checkpoint or
perform duplicate H2D.

### Lifetime and manager constraints

- `QdGpuOwner` owns the contiguous GPU buffer and pinned slots.
- Release is legal only after all tensor views are dead.
- Manifest mismatch releases speculative owners and uses an explicitly
  classified fallback.
- Bind only after shape, dtype, storage, identity, and patcher proofs.
- Cancellation and close must be idempotent.
- FP32 cast-once adds approximately 8.04 GB resident VRAM and remains off by
  default.
- No CLIP weights, owners, readers, or futures belong in the CPU snapshot.

### Expected saving

E29 reports approximately 122 ms of CLIP hydration; E28’s final Gantt reports
approximately 319 ms of request-side CLIP GPU hydration. The speculative source
read was approximately 4.43 s, but hiding it is useful only if it does not
stretch restore or contend with other work.

## Why naive CLIP-forward || UNET-load failed

The historical failure did not prove that CUDA overlap is inherently harmful.
It combined multiple effects:

1. E28 held `CLIP_GPU_CRITICAL_ACTIVE` across the entire UNET cold read. CLIP
   waited approximately 11.6 s. Narrowing the gate to UNET’s GPU commit reduced
   wait to approximately 0.1 ms.
2. A 16 MiB UNET bounce buffer limited the cold read to approximately 1.2
   GB/s. A 512 MiB buffer reduced the loader wall from 2,014 ms to 477 ms.
3. Multi-threaded 12.31 GB UNET prefetch competed with CLIP for storage,
   page/cache bandwidth, CPU scheduling, and host memory bandwidth.
4. Concurrent H2D can interfere with compute through copy-engine/PCIe pressure,
   allocator pressure, or stream synchronization.
5. The apparently fast ~2 s CLIP values were invalid counter regions or runs
   where the forward did not execute. Valid full-overlap runs were generally
   3.4–5.6 s.
6. UNET loading had no UNET compute phase in these runs. The strongest evidence
   concerns source I/O and CPU contention, not compute/compute contention.

The effects must be tested separately:

- **Source-I/O overlap:** can hide read time, but shares bandwidth.
- **CPU overlap:** can harm launch/preparation through scheduling and memory
  contention.
- **H2D overlap:** must be measured independently from source read.
- **Compute/H2D interference:** asynchronous copies can still reduce compute
  throughput.
- **Compute/compute interference:** not observed for UNET load itself.

Historical progression: E12 permitted prewarm only beside unrelated setup; E18
added a hard source fence; E28 fixed the broad D15 gate and reader geometry;
E29 corrected the critical-path ledger and left CLIP/restore overlap unknown;
E30 added bounded QD CLIP staging and ownership proof; E31 corrected CLIP
forward timing and identified host/prewarm contention as the leading variance
hypothesis. Exact output passed in valid E28 runs, but correctness does not
prove endpoint improvement.

## Eventual experiment sequence

### Experiment 0 — serial reference

Capture exact output identity, Python-resume → first-result endpoint, stage
walls, raw events, CPU time, source throughput, pinned bytes, GPU allocated /
reserved / peak memory, fallbacks, and cleanup status. Do not proceed until
serial performance is satisfactory.

### Experiment 1 — CLIP source/preparation left (recommended first)

Run a frozen-manifest CLIP source/preparation launch-policy A/B with no new
GPU-stage overlap:

- immediately post-restore;
- after CUDA restore;
- at method entry.

Keep UNET prefetch and VAE overlap disabled. Require exact output, valid source
fence, owner retention, no duplicate read/H2D, and no restore-wall regression.

This is the safest first experiment because the CLIP owner/fence path has the
strongest structural and exact-output evidence while avoiding VAE lifecycle
blockers and simultaneous CLIP/UNET GPU work.

### Experiment 2 — VAE CPU/source/pinned preparation

Prepare VAE during sampling with H2D disabled. First repair request-scoped
events, wait/acquire enforcement, timeout behavior, and worker joining.

### Experiment 3 — VAE H2D

Enable VAE H2D during sampling only after Experiment 2 is clean. Accept only if
sampling GPU time, allocator peaks, cleanup, and endpoint latency do not regress.

### Experiment 4 — CLIP forward || UNET source I/O

Overlap CLIP forward with UNET source read only. Defer UNET H2D and mutation
until CLIP forward completion. Use same-host alternating A/B runs and raw
interval arithmetic.

### Experiment 5 — UNET H2D

Only if Experiment 4 is positive, test UNET H2D overlap separately. Never
combine source-read, H2D, and compute overlap in the first arm.

## Evidence limitations

- No remote validation was run for this audit.
- E30 remote QD acceptance metrics remain unproven.
- The E29 raw artifact needed to establish CLIP/restore overlap was absent from
  the working tree.
- Existing graph metadata was older than some working-tree report content;
  direct source/report evidence was preferred.

## Final disposition

**PARKED.** This is an implementation-ready architecture and experiment plan,
not authorization to implement it. The next valid gate is satisfactory,
well-instrumented Golden Serial performance. Until that gate passes:

```text
RUNTIME_CODE_CHANGED=NO
INTEGRATED=NO
```
