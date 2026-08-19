# V2 Batch E4 - Staged Transport Local Microbenchmark

Date: 2026-08-16
Scope: local measurement only. No runtime modules changed. No Modal deploys or requests.

## Purpose

This benchmark answers three narrow questions before remote integration:

- Does preallocated pinned host memory produce the expected asynchronous DMA path?
- Does a CPU FP32 to BF16 cast erase that benefit?
- Does four-producer bucketing reduce launch and staging overhead?

The synthetic provider is the fallback while E1 is unfinished. It allocates one pinned byte pool and reuses views into that pool. It never calls `pin_memory()` per tensor or per copy.

## Defaults

| Setting | Value |
|---|---:|
| producers | 4 |
| bucket size | 256 MiB |
| pinned pool | 1 GiB |
| streams | 1 |
| dtype | BF16 |
| small-copy size | 4 MiB |
| measured repeats | 3, median reported |

The default payload is 4 x 256 MiB = 1 GiB. This is a fixed Phase-E point, not a sweep.

## Run

```text
python tools\benchmark_staged_safetensors_local.py --mode synthetic
```

The script prints the decision fields requested by the batch and can optionally write JSON with `--json-out`. It imports no Modal client and does not call a deployment or request path.

### E1 adapter contract

Use `--mode e1 --e1-module package.module[:factory]` when the E1 implementation is available. The module may expose `create_local_transport`, `create_staged_transport`, or `StagedTransport`. The factory receives the compatible subset of:

```text
config, producers, bucket_bytes, pool_bytes, streams=1,
stream_count=1, device
```

The returned object or module must expose `benchmark_local`, `run_local_benchmark`, `benchmark`, or `run_microbenchmark`. It receives the compatible subset of the same configuration plus `repeats` and `warmup`, and returns a mapping containing the result fields. `--mode auto --e1-module ...` falls back to synthetic mode if the provider is not importable.

## Local result

Environment: Windows, Python 3.11.9, torch 2.8.0+cu128, NVIDIA GeForce RTX 3070, CUDA available. Values are medians over three measured repeats after one warmup. Effective bandwidth is decimal GB/s from CUDA-event time.

| Measurement | Host wall / total ms | CUDA ms | Effective GB/s | Copies |
|---|---:|---:|---:|---:|
| pageable H2D | 90.037 | 89.958 | 11.936 | 1 |
| preallocated pinned H2D | 40.517 | 40.420 | 26.565 | 1 |
| pinned many-small H2D | 41.186 | 41.072 | 26.143 | 256 |
| pinned bucketed H2D | 40.788 | 40.694 | 26.386 | 4 |
| staged same-dtype, many small | 284.923 | 40.692 | 26.387 DMA | 256 |
| staged same-dtype, bucketed | 122.285 | 40.281 | 26.656 DMA | 4 |
| FP32 cast then pageable H2D | 1529.822 total | 149.202 | 7.197 DMA | 1 |

Additional measurements:

- CPU FP32 to BF16 cast: `1380.474 ms` median for the 1 GiB BF16 result.
- Pinned pool allocation: `217.132 ms` cold first allocation; `0.054 ms` steady cached allocation median across later samples.
- Initial pageable-to-pinned pool fill, outside H2D measurements: `539.270 ms`.
- `pool_is_pinned=true`; pinned H2D enqueue median was `0.207 ms` versus `40.420 ms` CUDA time.

### Decision

- `LOCAL_PINNED_FAST_PATH_CONFIRMED=YES`: pinned source, non-blocking copy, host enqueue far below device time, and 2.23x pageable CUDA bandwidth.
- `CPU_CAST_COST=1380.474 ms`: the cast output is pageable in this path, so the cast plus H2D total is dominated by CPU conversion and loses the pinned fast-path shape.
- `BUCKETING_RESULT=MATERIAL_GAIN`: four bucketed staged copies are 57.1% lower end-to-end than 256 small staged copies (`122.285 ms` versus `284.923 ms`). H2D CUDA time is nearly unchanged, so the saving is producer/staging/launch overhead rather than PCIe bandwidth.

## Recommended remote telemetry thresholds

Use p50 values over a bounded request cohort, with exact byte counts and zero fallback as correctness gates.

| Signal | Healthy / confirmed | Warning or failure interpretation |
|---|---|---|
| DMA source pinned fraction | `>= 0.95` for staged H2D bytes | lower means pageable staging is still active |
| non-blocking H2D | `true` | false cannot claim pinned-DMA fast path |
| host issue / CUDA-event time | `<= 0.25` | higher means enqueue is blocking or staging is serialized |
| pinned vs pageable effective GB/s | pinned `>= 1.25x` pageable | below this does not confirm a useful fast path |
| CPU cast output | `cast_output_pinned_fraction >= 0.95` | pageable cast output destroys the intended path |
| CPU cast cost | report separately; warn when `cast_ms > 0.25 * h2d_ms` | cast is becoming a material critical-path cost; this local run is far beyond it |
| bucketed end-to-end gain | bucketed p50 `<= 0.90x` many-small p50 | less than 10% gain means bucketing is not materially helping |
| pool allocation | report cold and steady; reuse the pool | allocation per tensor/request is a design regression |
| correctness | exact bytes/dtype, `fallback_count=0` | stop and diagnose before interpreting performance |

Remote telemetry should include: `pool_bytes`, `pool_alloc_ms_cold`, `pool_alloc_ms_steady`, `dma_source_pinned_fraction`, `cast_output_pinned_fraction`, `staged_bytes`, `bucket_bytes`, `producer_count`, `copy_count`, `non_blocking`, `stream_count`, `host_issue_ms`, `cuda_event_ms`, `cpu_stage_ms`, `cpu_cast_ms`, `effective_gbps`, `fallback_count`, and `error_reason`.

## Required result fields

```text
LOCAL_PINNED_FAST_PATH_CONFIRMED=YES
PINNED_GBPS=26.565
PAGEABLE_GBPS=11.936
CPU_CAST_COST=1380.474 ms
BUCKETING_RESULT=MATERIAL_GAIN (57.1% lower end_to_end)
FILES_CHANGED=tools/benchmark_staged_safetensors_local.py,V2_BATCH_E4_STAGED_TRANSPORT_BENCHMARK.md
MODAL_DEPLOYS=0
MODAL_REQUESTS=0
COMMIT=none
```
