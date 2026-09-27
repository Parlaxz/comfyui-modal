# Working source harness — M2 (window) validation record

Supersedes the `lifecycle="fresh"` baseline for the GPU/H2D program. The
operator selected the M2 engine (`mmap_src="window"` / `run_mmap_source_probe`)
as the working source harness after the fresh engine's cohorts landed ~1 GB/s
lower.

## Exact source state

- Harness commit: `b9196ac50897430af690d570242157f80bbc1100`
  (`source-race: working pure-CPU mmap source-read harness (Sept 2026)`).
- Engine: `comfymodal_runtime/source_race_oracle.py` → `run_mmap_source_probe`
  with `mmap_mode="window"`, `consume_mode="memcpy"` (child `_mm2_child`).
  Exact 64 MiB `PROT_READ|MAP_PRIVATE` window per block, persistent FD per
  reader, eager workers, self-service scheduler, native libc memcpy, synchronous
  munmap, 4 ms global launch floor.
- App/function: `sept-clip-source-race-oracle` / `run_worker_model_h100`
  (`worker_model="mmap_source"`), workspace Testing5 (`ws_c1487d319820`),
  `h100!`, no provider/region pinning.

## M2 baseline — 10 fresh H100 runs (uncapped, nothing discarded)

| run | provider:region | source GB/s | source wall ms | function wall ms |
|---|---|---:|---:|---:|
| m2-01 | gcp:ap-south | 5.852 | 1374.7 | 1827.0 |
| m2-02 | gcp:us-west | 4.823 | 1668.1 | 2148.3 |
| m2-03 | unspecified:us-central | 7.535 | 1067.7 | 1414.0 |
| m2-04 | unspecified:eu-south | 5.848 | 1375.6 | 1789.1 |
| m2-05 | unspecified:us-central | 7.549 | 1065.7 | 1427.1 |
| m2-06 | unspecified:uk | 5.904 | 1362.7 | 1737.2 |
| m2-07 | unspecified:us-central | 7.616 | 1056.3 | 1387.0 |
| m2-08 | unspecified:eu-south | 5.137 | 1566.2 | 1930.8 |
| m2-09 | unspecified:us-central | 7.671 | 1048.8 | 1377.1 |
| m2-10 | unspecified:us-central | 8.555 | 940.4 | 1248.5 |

Distribution (all 10):

| metric | value |
|---|---:|
| source GB/s median | **6.720** |
| source GB/s mean | 6.649 |
| source GB/s p10 / p90 | 5.137 / 7.671 |
| source GB/s min / max | 4.823 / 8.555 |
| source wall median | 1215 ms |
| function (execution) wall median | 1582 ms |
| end-to-end GB/s median (file ÷ function wall) | 5.08 |
| coverage | exact 120/120 on all 10 |
| max simultaneous in-flight | 4 on all 10 |

Gate: median source throughput **6.720 ≥ 5.5 GB/s → PASS**, and it matches the
historical M2 value (6.503 interleaved / 6.513 RTX).

Function/execution wall is now reported alongside the source wall. Note the
source wall is a partial sub-span (first reader op → last reader exit); the
execution wall additionally includes import, model stat, 512 MiB staging
allocation, CUDA setup, fork/join and teardown.

## Why M2 over the fresh engine

A same-window interleaved A/B (5 pairs, `engine_runs/`) gave fresh median 6.909
vs window 5.127 — placement-confounded (fresh drew uk/london, window drew
ap-northeast/OCI). The decisive evidence is the historical M2 figure and the
10-run M2 baseline above (6.72 median). `mode="private"` in the GPU probe calls
this exact M2 engine with `staging=None`.

Tag: `working-source-harness-m2`.
