# C9 Torch-Pinned Recovery — Smoke Report

## Smoke 0

**PASS.** In Testing 7/main with CPU12, 8192 MiB, and RTX PRO-6000:

- Torch: `2.14.0+cu130`;
- CUDA available: `true`;
- device: `NVIDIA RTX PRO 6000 Blackwell Server Edition`;
- 8/8 required 32 MiB worker tensors: `is_pinned == true`;
- model read: `false`;
- H2D pipeline initialized: `false`.

Receipt: `pinning_capability_receipt.json`.

## Smoke A

UNET/QD8, two serial fresh eligible observations, shared FD, 32 MiB reads,
no H2D:

| observation | C9_TOTAL_WALL_MS | PHYSICAL_READ_SPAN_MS | classification |
|---:|---:|---:|---|
| 1 | 4255.091605 | 1833.648988 | structurally valid |
| 2 | 4603.728789 | 2691.038048 | structurally valid |

All worker buffers were proven pinned and the raw result reports exactly one
shared FD, static disjoint ranges, QD8 achieved, and no hot-loop hashing,
allocation, or profiler telemetry. The C9 total includes the one-time Torch
buffer allocation; the physical-read span is diagnostic only.

## Gate decision

**STOP.** Both Smoke A C9 totals exceed the required 3-second ceiling. Smoke B
and the final 36-observation cohort were not run. The corrected combined path
has proven Torch pinning capability, but has not recovered the target fast
path or beaten the historical approximately 1.6 s UNET source class.

An audit is required before another deployment. Do not infer an individual
component win from this combined change. Preserve this run and the prior
`07b_c9_faithful_recovery` mlock run as non-decision evidence for their
respective mechanisms.

## Worker-local allocation / pre-import follow-up

The worker-local allocation candidate was redeployed after moving Torch
import outside the C9 timer. Smoke 0 again passed 8/8 pinned buffers. A fresh
UNET/QD8 Smoke A produced:

| observation | C9_TOTAL_WALL_MS | PHYSICAL_READ_SPAN_MS | classification |
|---:|---:|---:|---|
| 1 | 5745.413492 | 2257.287294 | structurally valid, stopped |
| 2 | 5431.591480 | 2419.829326 | structurally valid, stopped |

These runs isolated the remaining Torch-import setup cost, so they are
retained as non-decision evidence for the pre-import delta.

## Pre-import candidate follow-up

The pre-import candidate was redeployed without further source changes. Smoke
0 passed again with the same 8/8 pinned-buffer and RTX PRO-6000 evidence. A
fresh UNET/QD8 Smoke A produced:

| observation | C9_TOTAL_WALL_MS | PHYSICAL_READ_SPAN_MS | classification |
|---:|---:|---:|---|
| 1 | 2208.007169 | 1960.468954 | structurally valid, audit-needed |
| 2 | 2676.590596 | 2414.925844 | structurally valid, audit-needed |

The import-placement delta removed the multi-second setup regression. The
remaining totals are in the required roughly 2–3 second audit band, not a
fast-path pass: they do not yet establish recovery to the approximately 1.6 s
UNET source class. Smoke B and the final cohort remain unrun pending the
mechanics/provider audit.
