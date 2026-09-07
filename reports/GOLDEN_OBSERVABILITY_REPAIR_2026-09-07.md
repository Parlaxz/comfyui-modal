# Golden observability repair — 2026-09-07

## Scope

This repair changes reporting, event snapshots, strict output classification,
and request-scoped trace finalization only. True-QD2 source geometry,
ownership, H2D scheduling, loaders, attention selection, sampling, and output
encoding were not changed.

## Deployment

- Worktree: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
- HEAD before uncommitted repair: `9a2bae7bc9e86d06b42076f9c053ee1a78146709`
- Workspace: `ws_175a616152c5`
- App: `batch-cpuqd2-p1`
- Deployment version: `2`
- Deployment fingerprint: `47cc1a513e1faba6a6443abc1964dad3efdac38b45ccd0365a31444397267433`
- Receipt: `.v2ctl/deployments/receipt_2_47cc1a51....json`
- Manifest: `.v2ctl/deployments/deploy_20260906-224757_47cc1a51.json`
- Source probe: PASS/MATCH

## Percentiles

Canonical implementation: `comfymodal_runtime/statistics.py`.

All relevant report callers use `linear_interpolation`, with
`position=(n-1)*p`. The previous nearest-rank P90 returned the maximum for
n=5. No-deep source cohort corrected values are:

| Arm | Median ms | Linear P90 ms |
|---|---:|---:|
| Control | 11833.130 | 11986.170 |
| True-QD2 | 10976.371 | 11153.120 |

P90 throughput is reported separately from P90 wall; it is not paired with the
same run as P90 latency.

## Immutable source snapshots

Implementation: `comfymodal_runtime/golden_serial.py` (`CpuRawPrefetchTicket.event`).
Tests: `tests/test_cpu_qd2_prefetch.py`.

Each event now stores event-time `ready_bytes_total`,
`contiguous_prefix_bytes`, ready extent count, per-worker bytes/extents,
completion state, and completion timestamps. The old contradiction was a
semantic conflation: all extents could be ready while `_complete` remained
false until worker join and final coverage validation. New snapshots preserve
that distinction instead of reading final mutable state later.

In the first new deep run:

- DynamicVRAM: ready-total `5,502,926,848`, prefix `3,087,007,744`, 41 extents,
  complete `false`.
- CLIP demand: ready-total `5,637,144,576`, prefix `3,087,007,744`, 42 extents,
  complete `false`.
- H2D start: ready-total/prefix `8,044,936,192`, 60 extents, complete `false`.
- Source complete: ready-total/prefix `8,044,936,192`, 60 extents, complete
  `true`.

`source_complete` is the post-join/lifecycle proof; the raw snapshots make the
data-ready versus lifecycle-complete distinction explicit.

Workers own contiguous halves: worker 0 owns extents 0–29 and worker 1 owns
extents 30–59. `read_range()` waits for the exact requested interval union, so
the consumer can use any ready extent whose exact range is ready; it does not
require the global prefix. A future H2D-at-DynamicVRAM experiment should keep
exact destination offsets and issue ready-range work opportunistically, with
per-range readiness scheduling; that change is not implemented here.

## Output SHA

The last known matching artifact is the 2026-09-07 00:02:26 candidate under
deployment identity `9604c857...`, with the expected `8a924...` SHA. The first
observed `62837...` artifact is the 2026-09-07 02:10:23 control request under
the subsequent deployment identity `2d5e7498...`.

Both artifacts have the same workflow hash, sampler, CLIP name/type, PyTorch
attention identity, and baked-CUDA Sage mode. The changed deployment/source
identity is the first proven transition boundary; raw artifacts do not prove
pixel/model equivalence beyond those fields. The observed output is therefore
an unresolved behavior/fixture transition, not a legitimate exact match.

Future strict validation now requires `output_sha_match=True`; a warning no
longer permits `EXACT`. Historical artifacts retain their original raw
classifications.

## Sage fallback

`sage_restore decision=fallback_full_discovery reason=verify_failed` is
restore-time Sage identity/discovery fallback after snapshot verification. It
does not mean Golden sampling switched attention backends. The new deep traces
record configured/resolved sampling attention as `pytorch`; their dispatch
records show `pytorch_override`, `attention_pytorch`, and `pytorch_sdpa`.
Sage runtime is installed/resolved as `baked_cuda`, but SageAttention was not
the selected Golden sampling backend in this experiment.

## Deep finalizer

The request path no longer calls `generate_full_trace_report()` or performs a
full named-Volume readback. It stops/saves/gzips raw traces, writes a minimal
descriptor, uploads/commits, and defers rich report generation offline.

Three deep requests completed on the same deployment fingerprint. Remote raw
bundles and descriptor metadata:

1. `v2-full-trace/2026-09-07/957650d888884dbf97deaea0feef82c2/bundle.tar.gz`
   — 3,345,040 bytes; 291,442 VizTracer entries; finalize 2,720.652 ms.
2. `v2-full-trace/2026-09-07/cde0d02fd4ef4e91a94bf55462bdb684/bundle.tar.gz`
   — 3,318,972 bytes; 291,500 VizTracer entries; finalize 2,761.914 ms.
3. `v2-full-trace/2026-09-07/be00eaa9c227411caabfaa04c4665714/bundle.tar.gz`
   — 3,351,618 bytes; 291,480 VizTracer entries; finalize 2,830.970 ms.

Local downloaded verification copies are under
`C:\Users\parla\AppData\Local\Temp\opencode\deep-{1,2,3}-bundle.tar.gz`.

The optional console renderer still logs `FileNotFoundError` for deferred
`derived/golden_profiler_console.txt`; this does not prevent raw artifact
success and is intentionally not treated as trace loss.

## Request artifacts

- No-deep smoke: `EXPERIMENT_EVIDENCE_golden_p1_1fe16cd6f9924714_2026-09-07.md`
  — normal execution completed, strict SHA verdict `REJECT/MISMATCH`.
- Deep 1: `EXPERIMENT_EVIDENCE_golden_p1_c4834199316549b9_2026-09-07.md`
- Deep 2: `EXPERIMENT_EVIDENCE_golden_p1_187e1dcd3e2b43d6_2026-09-07.md`
- Deep 3: `EXPERIMENT_EVIDENCE_golden_p1_7777c580129343eb_2026-09-07.md`
- Corresponding raw attempt/cohort manifests are under
  `artifacts/phase_p1_serial_golden_v1/`.

## Validation

- 28 snapshot-hygiene tests passed.
- 17 Golden acceptance tests passed.
- 15 QD2/control tests passed.
- Python compilation passed for changed modules.
- `git diff --check` passed.
