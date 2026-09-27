# V2 Batch E1: Generic Staged Safetensors Core

## Contract

`comfymodal_runtime.staged_safetensors` is a generic safetensors-only backend:

```text
plan(checkpoint, ...) -> StagePlan
prepare(StagePlan)   -> PreparedStage
commit(PreparedStage) -> StageResult
result(StageResult)   -> StageResult
```

`StageResult.tensors` is a transferred, unbound state dictionary. A caller
must bind it only after `success` is true. A failed result has a precise
`fallback_reason`; the caller keeps its existing loader and invokes it.
`plan` accepts one checkpoint path or a list of safetensors paths and rejects
duplicate tensor keys.

## Resource Model

- Four producer workers by default.
- Four reusable 256 MiB pinned slabs by default, for a 1 GiB pinned maximum.
- When ComfyUI is present, native pin-budget and registerability checks guard
  the pool and the native pinned total reserves the pool until release.
- One CUDA copy stream per commit.
- Native ComfyUI non-blocking capability and offload-stream seams are reused
  when available; standalone use falls back to the CUDA capability itself.
- Each slab is associated with a CUDA event after enqueue and cannot be
  reacquired until that event reports completion.
- Host-to-device copies use `non_blocking` according to configuration.
- No per-tensor `pin_memory()` and no device-wide synchronization.
- The GPU destination is allocated per tensor, while the pinned host pool is
  reused and bounded.
- With `COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS=1`, dense ordinary tensors
  use one aligned packed GPU byte owner and typed tensor views. The result
  retains that owner until `StageResult.close()`; invalid geometry fails with
  `E1_CONTIGUOUS_BUCKETS_DEFERRED`.

The prepared object owns producer futures, the bounded queue, and the pinned
pool. It can be retained by a future caller for pre-staging, but this module
does not schedule work for another load.

## Dtype Rules

Same-dtype transfers copy the source bytes exactly. The only generic CPU cast
is source FP32 to requested BF16 or FP16, when CPU casting is enabled. Integer,
FP8, quantized, and unknown/custom dtypes are never generically cast and fail
closed when unsupported.

## Configuration

| Variable | Default | Meaning |
| --- | ---: | --- |
| `COMFYMODAL_V2_STAGED_SAFETENSORS` | `off` | Feature gate |
| `COMFYMODAL_V2_STAGED_PRODUCERS` | `4` | Producer workers |
| `COMFYMODAL_V2_STAGED_POOL_MB` | `1024` | Total pinned pool budget |
| `COMFYMODAL_V2_STAGED_BUCKET_MB` | `256` | Size of each reusable slab |
| `COMFYMODAL_V2_STAGED_CPU_CAST` | `on` | Permit FP32 to BF16/FP16 CPU conversion |
| `COMFYMODAL_V2_STAGED_ASYNC_H2D` | `on` | Request non-blocking H2D copies |
| `COMFYMODAL_V2_STAGED_CONTIGUOUS_GPU_BUCKETS` | `off` | Enable aligned dense packed GPU views |

## Telemetry

Results expose `checkpoint_bytes`, `disk_to_stage_ms`, `cpu_cast_ms`,
`cpu_cast_bytes`, `exact_copy_bytes`, `h2d_enqueue_ms`, optional event-only
`h2d_device_ms`, `bind_independent_transfer`, `peak_pinned_bytes`,
`producer_wait_ms`, `consumer_wait_ms`, `effective_h2d_gbps`, and
`fallback_reason`. No binding operation is included in these transfer timings;
`cpu_cast_bytes` and `exact_copy_bytes` partition transferred tensor bytes.

## Failure Safety

Preparation failures stop producer work and release temporary CPU staging. A
commit failure first waits only on the owned copy stream, drains queued slabs,
releases temporary GPU tensors, and closes the pinned pool. The result never
contains a partially bound caller model.
