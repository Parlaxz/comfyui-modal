# RX4 — Final Parallelization Architecture Audit

**Status:** design only; no runtime code changed.

Golden Serial must remain deliberately serial. The later parallelization work
belongs in an explicit Golden Overlapped orchestrator and should reuse the
existing stage functions and evidence mechanisms rather than hiding scheduling
inside individual stages.

## Executive ordering

1. Move CLIP source loading and preparation as far left as safely possible.
2. Prepare VAE during sampling using CPU/source/pinned work only.
3. Add VAE H2D overlap only after lifecycle fixes and measurement.
4. Attempt CLIP-forward || UNET-load last, initially overlapping UNET source
   I/O only.
5. Test UNET H2D overlap separately, only if source-only overlap is positive.

## 1. CLIP forward || UNET load

### Ordering

- **Earliest CLIP forward:** after CLIP bind and input preparation, at the
  actual `clip_encode_start`/forward boundary, not worker submission.
- **Earliest UNET work:** source read after request/plan identity is known, or
  through an explicitly validated post-restore prewarm future.
- **Latest UNET completion:** `unet_device_ready` and patcher adoption before
  graph UNET demand/first UNET forward.
- **Safest first overlap:** CLIP GPU compute with UNET source read only.
- **Initially defer:** UNET H2D, GPU commit, patcher mutation, and `.data`
  rebinding until CLIP forward completes.

### Work and ownership

- **CPU:** worker submission, metadata, source-reader coordination, and model
  manager bookkeeping.
- **Source I/O:** UNET checkpoint read; measure separately from H2D and commit.
- **Pinned memory:** bounded UNET staging/bounce buffers; budget them together
  with CLIP QD staging.
- **H2D:** UNET copy stream, initially after source read and CLIP forward.
- **GPU compute:** CLIP forward owns the compute stream. UNET loading should
  not run compute kernels.

### Required events and fences

```text
clip_encode_start
clip_forward_start
clip_forward_end
unet_lane_submitted
unet_source_io_start/end
unet_gpu_transfer_start/end
unet_device_ready
source_fence_valid
mutation_lane_acquired/released
copy_event_recorded/waited
```

The UNET consumer stream must wait on its producer CUDA event. Avoid a
device-wide synchronize except as an explicitly measured fallback. The
mutation lane must cover only the GPU commit/bind section, not the cold read.

### Constraints

- Readers and file handles remain alive until the source fence retires all
  workers.
- Pinned buffers remain alive until H2D completion.
- CUDA-backed storage remains alive after bind when tensors are zero-copy
  views.
- `ModelPatcher`/model-manager mutation remains single-owner.
- No concurrent `load_models_gpu`, patcher rebinding, or cache publication.
- Source-fence failure blocks demand loading; it must not silently enter a
  native fallback.
- CLIP currently performs approximately 14.53 GB of BF16→FP32 destination
  writes per forward. Concurrent UNET allocation/H2D may increase VRAM and
  allocator pressure.
- `empty_cache()` is not a material optimization on this path; measured calls
  are approximately sub-millisecond to 2 ms.

### Expected saving

Theoretical upper bound is the hidden UNET source-read wall, approximately
477 ms in the corrected E28 configuration. No accepted net saving exists;
source, CPU, and memory contention can make CLIP slower than the hidden work is
worth.

## 2. VAE load || sampling

### Ordering

- **Earliest safe start:** sampling start, after VAE identity and CPU state are
  fixed.
- **First implementation:** VAE source read, CPU preparation, and bounded
  pinned staging during sampling.
- **Latest completion:** H2D/bind after `sampling_end`, before VAE decode.
- **Decode:** only after VAE readiness and mutation ownership are proven.

The existing experimental path attempts side-stream VAE pre-copy during
sampling, followed by a narrow post-sampling bind.

### Work and ownership

- **CPU:** VAE resolution, source read, state preparation, and pinned staging.
- **Source I/O:** may overlap sampling only with validated source identity and
  reader ownership.
- **Pinned memory:** bounded staging retained until copy completion or cancel.
- **H2D:** optional side-stream pre-copy.
- **GPU compute:** sampling owns compute; VAE decode remains after sampling.

### Blockers before concurrency

The current mechanism is not yet concurrency-safe:

- `_VAE_SAMPLING_END_EVENT` is process-global and sticky.
- The worker ignores the event-wait result.
- Mutation-lane acquisition success is not enforced.
- `MutationLane` timeout handling is broken and `notify_all()` does not provide
  FIFO ordering despite the class contract.
- The VAE worker is a raw daemon thread and finalization does not join it.
- Some runtime sampler paths swallow activation failures.

These are correctness blockers, not just telemetry issues.

### Required events and fences

Use request-scoped state and record:

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

Before binding, confirm request liveness, copy completion, stream visibility,
successful mutation-lane acquisition, exact VAE identity, and release the lane
in `finally`. Finalization must cancel and join the worker.

### Constraints

- VAE CPU tensors, pinned buffers, GPU tensors, and patcher identity must live
  through decode.
- Snapshot capture must contain no VAE worker, future, CUDA owner, active
  reader, or request state.
- Restore must not inherit sampling events from an earlier request.
- Do not rebind while the sampler owns the mutation lane.

### Expected saving

E29 measured approximately 34 ms of VAE model management and 430.7 ms of VAE
decode. Only the approximately 34 ms load/management portion is plausibly
hideable. Decode is not hidden by sampling in this design.

## 3. Push CLIP load/preparation left

### Ordering

1. Keep the snapshot model-free and quiescent.
2. After Python resumes and `modal_restore_exit` occurs, obtain the frozen
   manifest.
3. Start CLIP source loading before method entry or plan arrival.
4. Complete source read, pipeline preparation, and optional H2D.
5. Record CUDA readiness.
6. At demand, verify identity and bind exactly once.
7. Retain the source owner until all adopted tensor views are dead.

The current proven application-level start is post-restore. Python cannot run
before Python resume, and E29 corrected an earlier invalid timestamp claim;
CLIP-versus-restore contention remains unproven without the raw artifact.

### Work and ownership

- **CPU:** manifest validation, header parsing, worker submission, and pipeline
  selection.
- **Source I/O:** QD or fastsafetensors read.
- **Pinned memory:** E30 QD4 × 32 MiB is approximately 128 MiB bounded staging.
- **H2D:** one contiguous GPU destination buffer with asynchronous copy.
- **GPU compute:** no CLIP forward during preparation; forward follows bind.

E30’s QD reader uses disjoint tensor-aligned `preadv` ranges and zero-copy GPU
views. Remote proof of its queue depth and throughput is still incomplete.

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

### Constraints

- `QdGpuOwner` owns the contiguous GPU buffer and pinned slots.
- Owner release is legal only after all tensor views are dead.
- Manifest mismatch releases speculative owners and uses an explicitly
  classified fallback.
- Bind only after shape, dtype, storage, identity, and patcher proofs.
- Cancellation and close must be idempotent.
- FP32 cast-once adds approximately 8.04 GB resident VRAM and should remain
  off by default.
- No CLIP weights, owners, readers, or futures belong in the CPU snapshot.

### Expected saving

E29 reports approximately 122 ms of CLIP hydration; E28’s final Gantt reports
approximately 319 ms of request-side CLIP GPU hydration. The speculative source
read was approximately 4.43 s, but hiding it is useful only if it does not
stretch restore or contend with other work.

## Why naive CLIP-forward || UNET-load regressed

The failure did not prove that CUDA overlap is inherently harmful:

1. E28 held `CLIP_GPU_CRITICAL_ACTIVE` across the complete UNET cold read.
   CLIP waited approximately 11.6 s. Narrowing the gate to UNET’s GPU commit
   reduced wait to approximately 0.1 ms.
2. A 16 MiB UNET bounce buffer limited the cold read to approximately 1.2
   GB/s. A 512 MiB buffer reduced the loader wall from 2,014 ms to 477 ms.
3. Multi-threaded 12.31 GB UNET prefetch competed with CLIP for storage,
   page/cache bandwidth, CPU scheduling, and host memory bandwidth.
4. Concurrent H2D can interfere with compute through copy-engine/PCIe pressure,
   allocator pressure, or stream synchronization.
5. The apparently fast ~2 s CLIP values were invalid counter regions or runs
   where the forward did not execute. Valid full-overlap runs were generally
   3.4–5.6 s.
6. UNET loading had no UNET compute phase in these runs, so the strongest
   evidence concerns source I/O and CPU contention, not compute/compute
   contention.

Separate the effects:

- **Source-I/O overlap:** can hide read time, but shares bandwidth.
- **CPU overlap:** can harm launch/preparation through scheduling and memory
  contention.
- **H2D overlap:** must be measured independently from source read.
- **Compute/H2D overlap:** asynchronous copies can still reduce compute
  throughput.
- **Compute/compute overlap:** not observed for UNET load itself.

Historical evidence: E12 allowed prewarm only beside unrelated setup; E18
added a hard source fence; E28 fixed the broad D15 gate and reader geometry;
E29 corrected the critical-path ledger and left CLIP/restore overlap unknown;
E30 added bounded QD CLIP staging and ownership proof; E31 corrected CLIP
forward timing and identified host/prewarm contention as the leading variance
hypothesis. Exact output SHA passed in valid E28 runs, but correctness does not
prove endpoint improvement.

## Implementation-ready experiment sequence

### Experiment 0 — serial reference

Capture exact output identity, Python-resume → first-result endpoint, stage
walls, raw events, CPU time, source throughput, pinned bytes, GPU allocated/
reserved/peak memory, fallbacks, and cleanup status.

### Experiment 1 — recommended first

Run a CLIP frozen-manifest source/preparation launch-policy A/B with no new
GPU-stage overlap:

- immediately post-restore;
- after CUDA restore;
- at method entry.

Keep UNET prefetch and VAE overlap disabled. Require exact output, valid source
fence, owner retention, no duplicate read/H2D, and no restore-wall regression.

This is the safest first overlap experiment because the CLIP owner/fence path
has the strongest structural and exact-output evidence, while avoiding VAE
lifecycle blockers and simultaneous CLIP/UNET GPU work.

### Experiment 2

VAE CPU/source/pinned preparation during sampling with H2D disabled. First fix
request-scoped events, wait/acquire enforcement, and worker joining.

### Experiment 3

Enable VAE H2D during sampling. Accept only if sampling GPU time, allocator
peaks, and endpoint latency do not regress.

### Experiment 4

Overlap CLIP forward with UNET source read only. Defer UNET H2D and mutation
until CLIP forward completion. Use same-host alternating A/B runs and raw
interval arithmetic.

### Experiment 5

Only if Experiment 4 is positive, test UNET H2D overlap separately. Do not
combine source-read, H2D, and compute overlap in the first arm.

## Evidence limitations

- No remote validation was run for this audit.
- E30 remote QD acceptance metrics remain unproven.
- E29’s raw artifact needed to establish CLIP/restore overlap was absent from
  the working tree.
- Existing graph metadata was older than some working-tree report content;
  direct source/report evidence was preferred.
