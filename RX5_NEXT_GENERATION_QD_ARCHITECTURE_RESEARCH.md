# RX5 — Next-Generation QD Architecture Research

## Scope

Contingency research for the case where the planned Python QD4 work still
leaves a meaningful model-loader wall. This report does not replace or modify
QD4.

## Conclusion

Do not build native QD yet. A native scheduler would primarily reduce Python
coordination overhead; it would not make the Modal Volume itself faster. It is
justified only if the current Python dispatcher proves an endpoint improvement
and profiling shows that Python dispatch is materially contributing to the
remaining wall.

## Current evidence

- Legacy CLIP QD4 uses four source workers, two pinned slots per worker, async
  H2D, one contiguous GPU buffer, and zero-copy tensor views
  (`comfymodal_runtime/clip_qd_reader.py:1571-1760`).
- `QdGpuOwner` and the existing adoption/lifetime machinery are correctness
  critical.
- The current opt-in Golden dispatcher already centralizes H2D submission,
  CUDA-event polling, reaping, and slot return
  (`comfymodal_runtime/golden_qd_transport.py:762-886`).
- Its Golden adapter preserves typed-view construction, adoption proofs, and
  owner retention (`comfymodal_runtime/golden_serial.py:2776-2865`).
- Historical results show large physical variance. E37 recorded 1,043.5 ms
  QD source wall and 7.7095 GB/s aggregate; E36 recorded 2,885.5 ms source
  wall, 2.788 GB/s aggregate, and 3,202.2 ms H2D host issue.
- These results do not isolate Python scheduling overhead. R41 identified
  legacy source/H2D slot-reuse coupling, but post-decoupling Modal throughput
  remains unproven.

## Applicability by environment

| Technique | Modal Volume path | Local NVMe/RDMA/GDS environment |
|---|---|---|
| Native POSIX `pread`/`preadv` workers | Applicable | Applicable |
| Bounded native producer/consumer ring | Applicable | Applicable |
| Pinned host staging plus Torch H2D | Applicable if allocation succeeds | Applicable |
| Run:ai Model Streamer | Good conceptual fit; CPU staging only | Also applicable |
| fastsafetensors `nogds` | Plausible; retain explicit lifetime | Applicable |
| InstantTensor buffered mode | Potentially applicable; measure | Stronger fit |
| `io_uring` | Probe the actual mounted Volume; benefit unknown | More plausible |
| POSIX AIO | Technically possible, but adds complexity and often uses helper threads | Sometimes useful |
| `O_DIRECT` | Unknown; probe actual mount and alignment path | Useful only when supported by filesystem/storage |
| GDS/cuFile | Not established or implied by a Modal Volume; requires host support | Plausible with supported filesystem/NVMe/kernel stack |
| RDMA/NIXL/P2P | Not applicable to one isolated Comfy container | Requires cluster topology and peer workers |
| vLLM/vLLM-Omni, Dynamo, ModelExpress | Architectural references, not drop-in Comfy loaders | Mainly relevant to serving/disaggregated deployments |

Modal-compatible techniques are buffered range reads, native thread pools,
bounded rings, pinned staging where available, Torch H2D, and exact
safetensors range planning. A native scheduler cannot manufacture NVMe
bandwidth, RDMA, or GPU-direct storage. On Modal, plausible gains are bounded
staging, better application-level overlap, batching, and less Python
bookkeeping.

## Architecture blueprint

### 1. Complete Python QD4 validation first

Compare legacy QD4 with the existing Python dispatcher on the same Modal path.
Record source wall, H2D host issue, CUDA event time, queue waits, slot waits,
effective QD, and Python dispatcher CPU time.

### 2. Nativeize only the transport control plane

If the gate passes, prefer a small C++/PyTorch extension initially. CUDA/Torch
storage and event integration are more direct than in Rust. Keep the public
contract equivalent to the existing lease, ready-record, and backend
interfaces.

Start with buffered `pread`/`preadv`. Treat `io_uring`, `O_DIRECT`, and cuFile
as independent capability-probed backends. Never label compatibility-mode or
fallback execution as direct I/O or GDS.

### 3. Ownership

- Producers own source reads into leased bounded slots.
- Producers never inspect or wait on CUDA events.
- One dispatcher owns H2D submission, event registration, polling, reaping,
  and slot return.
- Keep reaping in that dispatcher initially; split it only if profiling proves
  event polling itself material.
- Python retains model-preload, Comfy graph scheduling, GPU admission,
  adoption, and teardown policy.

The native scheduler must not absorb model-preload or Comfy graph scheduling.

### 4. Safe Python/Comfy handoff

Native code should return Torch tensors sharing the exact contiguous CUDA
allocation together with an explicit owner object. The owner must remain held
by the load result or model registry until all adopted views are released.

Use `at::Tensor`/intrusive ownership or an explicit custom deleter; do not
expose borrowed raw pointers. DLPack is possible but unnecessary unless its
lifetime contract is made equally explicit.

Python should continue to perform dtype, shape, byte-count, data-pointer or
storage-identity, model-object, and no-duplicate-read/H2D proofs. The native
operation must be joined before device-ready publication unless an explicit
async handle has an equivalent lifecycle contract.

## QD4 machinery to retain

- Safetensors header and exact range planning.
- Bounded pinned Torch slabs.
- Contiguous GPU backing storage and typed views.
- Coverage and byte reconciliation.
- `QdGpuOwner`-style lifetime ownership.
- Claim/join/adopt/already-ready coordination.
- Fail-closed fallback classification and telemetry.

## Complexity and likely payoff

Implementation complexity is medium-high: native build and packaging, Torch
and CUDA ABI compatibility, cancellation, event/error handling, buffer
lifetime, telemetry parity, and safe tensor ownership all need coverage.

Likely payoff is low when the remaining wall is Modal Volume behavior, H2D host
issue time, provider variance, or downstream stage work. Payoff becomes
credible only when the Python dispatcher is nominal and the measured Python
control-plane share is material.

## Decision gate

Proceed only when all conditions hold:

1. Python dispatcher execution is nominal, exact, repeatable, and leak-free.
2. Same-environment legacy-versus-dispatcher A/B shows a repeatable full-stage
   or first-result improvement beyond cohort noise.
3. Telemetry demonstrates that Python queue transitions, locking, event
   polling, or dispatch bookkeeping materially contribute to the wall.
4. A native prototype improves the real Modal endpoint, not merely a local I/O
   microbenchmark.
5. It preserves identical storage/adoption proofs and produces no duplicate
   reads or H2D transfers.

A threshold such as 5% median endpoint improvement or twice measured cohort
noise may be precommitted as the promotion rule; it is not an observed RX5
result.

If the gate fails, retain Python QD4 and classify the remaining wall as Modal
source/H2D/provider behavior rather than adding native complexity.

## Research references

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
