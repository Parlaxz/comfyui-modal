# RX5 — Next-Generation Native-QD Contingency Report

**Date:** 2026-08-31  
**Status:** Research only; no runtime implementation  
**Integration:** `NO`

## Executive conclusion

**DO NOT BUILD NATIVE QD YET.**

Native code could remove Python queueing, locking, dispatch, and event-polling
overhead. It cannot make the Modal Volume or its provider deliver more storage
bandwidth. Current evidence does not establish that Python scheduling is a
material part of the remaining loader wall.

Native QD is a contingency only after Python QD4 optimization and validation,
including the existing Python dispatcher path. It should proceed only after a
same-environment physical A/B and telemetry-based proof of a meaningful Python
control-plane contribution.

## Current QD4 architecture

The legacy CLIP QD4 path in
`comfymodal_runtime/clip_qd_reader.py:1571-1760` performs:

1. Safetensors header parsing and exact range planning.
2. Static partitioning across four source workers.
3. Two bounded staging slots per worker, normally pinned Torch memory.
4. Positioned source reads into those slots.
5. Asynchronous H2D into one contiguous CUDA byte buffer.
6. Typed, zero-copy tensor views over that buffer.
7. Validation of coverage, bytes, records, and completion.

`QdGpuOwner` retains the CUDA buffer, staging slots, and event-related lifetime
until every adopted tensor view is finished. Python also owns model-preload
coordination and join/adopt/already-ready behavior.

The legacy path has source/H2D slot-reuse coupling: a worker can wait for a
prior CUDA completion before reusing its slot. This can reduce effective
steady-state depth even when peak outstanding QD reports four.

The current opt-in Golden path already contains a separate Python
`TransportDispatcher` in
`comfymodal_runtime/golden_qd_transport.py:762-886`. It centralizes H2D
submission, event registration, polling, reaping, and slot return. Its adapter
in `golden_serial.py:2776-2865` preserves typed views, adoption proofs, and
owner retention while leaving the legacy implementation intact.

This dispatcher is the required Python baseline before considering native code.

## Historical physical variance

The historical results show physical and lifecycle variance, not a stable
Python-limited loader wall:

| Evidence | Observed result | Interpretation |
|---|---|---|
| E27 | QD8 UNET 49.6 GB/s and CLIP 45.0 GB/s in a capability probe | Snapshot/generation-path validation was blocked; not a production endpoint result |
| C6 | 9,027 ms valid two-slot pinned-ring wall | Zero hidden overlap; slower than reference; default remained off |
| E37 | 1,043.5 ms QD source wall; 7.7095 GB/s aggregate; 127.4 ms H2D host issue; 27.3 ms CUDA event | Valid clean-lane QD4 evidence |
| E36 ARM-A | 2,654.2 ms QD source; 3.031 GB/s aggregate; 1,703.0 ms H2D host issue | Valid QD4 observation |
| E36 ARM-B | 2,885.5 ms QD source; 2.788 GB/s aggregate; 3,202.2 ms H2D host issue | Valid current-source QD4 observation |

E36 also showed substantial restore and pre-sampler variation while sampler and
VAE were comparatively stable. These measurements establish that source,
H2D-host issue time, provider behavior, and lifecycle conditions vary sharply.

## Why Python scheduler overhead is not isolated

The existing measurements do not yet provide all of the following in one
controlled comparison:

- legacy versus Python-dispatcher execution on the same Modal deployment and
  storage state;
- time-weighted effective QD rather than peak outstanding QD;
- time spent blocked on staging, ready-queue capacity, H2D completion, and
  event polling;
- Python dispatcher CPU time and queue-transition cost;
- a reconciled full-stage or first-result endpoint boundary.

Therefore a slower or variable run cannot be attributed to Python scheduling.
R41 identifies a real legacy coupling defect and supplies a structurally better
dispatcher design, but it does not prove that the decoupled design improves
physical Modal throughput. A native rewrite before that proof would risk
reimplementing correctness-sensitive ownership machinery without addressing
the dominant wall.

## Applicability matrix

| Technique | Modal Volume applicability | Boundary or caveat |
|---|---|---|
| Native `pread`/`preadv` | **Applicable** | Ordinary positioned reads into bounded host buffers are the safest native transport baseline |
| Bounded native ring | **Applicable** | Useful for explicit backpressure and overlap; cannot exceed storage/provider limits |
| Pinned staging | **Applicable when allocation succeeds** | Preserve bounded Torch pinned slabs and record pageable fallback explicitly |
| Run:ai Model Streamer concepts | **Good conceptual fit** | Native reader threads and CPU producer/consumer buffering fit filesystem reads, but it is still CPU staging followed by H2D and does not guarantee pinned memory |
| fastsafetensors | **`nogds` path is plausible** | Its async pipeline and bounded memory controls are useful; GDS mode is not a Modal assumption and loader lifetime must be explicit |
| InstantTensor | **Buffered modes may fit** | `io_uring`, AIO, mmap, and cuFile backends are hardware/filesystem dependent; use capability detection and measure the actual mount |
| `io_uring` | **Conditional** | Probe kernel and mounted-filesystem behavior; queue efficiency does not imply GPU-direct I/O or a faster distributed Volume |
| POSIX AIO | **Technically possible, low priority** | Linux implementations may use helper threads; it adds lifecycle complexity without removing CPU staging |
| `O_DIRECT` | **Unknown until probed in deployment** | Requires filesystem support and aligned buffers, offsets, and lengths; bypassing cache may hurt rather than help |
| GDS/cuFile | **Not established for Modal Volume** | Requires compatible filesystem/storage plus host kernel, NVIDIA, and cuFile support; a container cannot provide missing host components |
| RDMA/NIXL/P2P | **Not applicable to the current isolated container** | Requires peer workers, compatible GPUs/NICs, topology, and a distributed control plane |

Modal Volumes are distributed filesystems mounted in the container, not known
local NVMe block devices. Local-NVMe, RDMA, NIXL, P2P, and GDS results must not
be transferred to the Modal Volume conclusion without deployment-specific
proof.

## Why native code cannot manufacture Modal bandwidth

A C++ or Rust scheduler can reduce application overhead and improve the use of
available concurrency. It cannot change:

- the Modal Volume service or network path;
- provider-side queueing and latency;
- filesystem semantics exposed by the mount;
- available PCIe/NVMe/RDMA topology;
- host kernel support for `O_DIRECT`, io_uring, or GDS;
- whether storage is directly DMA-addressable by the GPU.

The likely Modal benefit is therefore bounded application-level pipelining,
fewer Python transitions, explicit backpressure, and better measurement—not a
new storage transport class.

## Proposed architecture if later justified

Implement a narrow native C++/PyTorch extension for the transport control plane,
not a replacement for Comfy or model scheduling.

### Native responsibilities

- Consume the existing immutable safetensors range plan.
- Run bounded source producers using buffered `pread`/`preadv` first.
- Lease and fill pinned host slabs when available.
- Publish ready records to a bounded ring.
- Submit H2D copies and own CUDA-event registration, polling, reaping, and slot
  return.
- Expose explicit cancellation, error, completion, and telemetry states.

Start with one dispatcher/reaper owner. Split event reaping into another native
thread only if profiling proves dispatcher polling itself material. Treat
io_uring, `O_DIRECT`, and cuFile as independently probed backends, never as
implicit upgrades.

### Python responsibilities

Python must continue to own:

- model-preload and GPU-lane admission;
- Comfy graph scheduling and stage boundaries;
- model adoption and demand joins;
- owner registry and teardown policy;
- endpoint timing and experiment classification.

The native scheduler must not absorb Golden orchestration or become a second
generic PromptExecutor.

## Required ownership and lifetime contract

1. Producers own source reads only and never wait on CUDA events.
2. The dispatcher owns H2D submission and the event/slot state machine.
3. A lease cannot be returned until its read and corresponding H2D event have a
   proven terminal state.
4. Native errors, cancellation, uncertain events, and late completions must
   fail closed and drain within a bounded policy.
5. Native code returns Torch tensors sharing the exact CUDA allocation plus an
   explicit owner object.
6. The owner remains retained by the load result/model registry until every
   adopted tensor view is released.
7. No borrowed raw pointer may outlive its owner. Use `at::Tensor` ownership,
   an intrusive/shared owner, or an equivalent explicit custom deleter.
8. Device-ready publication occurs only after the native operation is joined,
   unless an explicit async handle has the same observable lifecycle proofs.

DLPack is possible but unnecessary unless its ownership and release semantics
are made equally explicit.

## QD4 machinery to retain

- Safetensors header parsing and exact range planning.
- Bounded pinned Torch storage and pageable fallback classification.
- Contiguous CUDA backing storage and typed tensor views.
- Coverage, byte-count, dtype, shape, and data-pointer/storage-identity proofs.
- `QdGpuOwner`-style owner lifetime.
- Model claim/release and join/adopt/already-ready coordination.
- No-duplicate-read and no-duplicate-H2D checks.
- Fail-closed fallback, cancellation, cleanup, and raw telemetry.

Native code should replace only the proven Python transport control-plane seam.
It should not replace these adoption or correctness contracts.

## Native-QD decision gate

Build native QD only if every condition is met:

1. Python QD4 is nominal, exact, repeatable, and leak-free.
2. The existing Python dispatcher is compared with legacy QD4 using the same
   Modal path, deployment conditions, model, and endpoint.
3. The A/B shows a repeatable full-stage or first-result improvement beyond
   measured cohort noise.
4. Telemetry shows that Python queue transitions, locks, event polling, or
   dispatch bookkeeping are a material fraction of the wall.
5. A native prototype improves the real Modal endpoint, not only a local NVMe
   or synthetic I/O microbenchmark.
6. The prototype preserves exact storage/adoption/lifetime proofs and performs
   no duplicate reads or H2D transfers.
7. All fallback and capability states remain observable and correctly labeled.

A threshold such as 5% median endpoint improvement or twice measured cohort
noise can be precommitted as a promotion rule. It is a proposed gate, not an
observed RX5 performance result.

If any condition fails, retain Python QD4 and classify the remaining wall as
Modal source/H2D/provider behavior or other measured downstream work.

## References

### Repository evidence

- `comfymodal_runtime/clip_qd_reader.py:1571-1760`
- `comfymodal_runtime/golden_qd_transport.py:762-886`
- `comfymodal_runtime/golden_serial.py:2776-2865`
- `comfymodal_runtime/staged_safetensors.py:1775-2019`
- `comfymodal_runtime/model_preload.py:15284-15673`
- `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md:16-50`
- `E36_FULL_CRITICAL_PATH_REPORT.md:182-228`
- `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md:47-111`

### External research

- Run:ai Model Streamer: https://github.com/run-ai/runai-model-streamer
- Modal Volumes: https://modal.com/docs/guide/volumes
- InstantTensor: https://github.com/scitix/InstantTensor
- fastsafetensors: https://github.com/foundation-model-stack/fastsafetensors
- vLLM loader integration: https://github.com/vllm-project/vllm/blob/main/vllm/model_executor/model_loader/weight_utils.py
- vLLM-Omni: https://github.com/vllm-project/vllm-omni
- NVIDIA ModelExpress: https://github.com/ai-dynamo/modelexpress
- NVIDIA Dynamo: https://docs.nvidia.com/dynamo/
- NVIDIA GPUDirect Storage: https://docs.nvidia.com/gpudirect-storage/overview-guide/index.html
- Linux `open(2)`: https://man7.org/linux/man-pages/man2/open.2.html
- Linux AIO: https://man7.org/linux/man-pages/man7/aio.7.html
- io_uring: https://kernel.org/doc/html/latest/userspace-api/io_uring.html
