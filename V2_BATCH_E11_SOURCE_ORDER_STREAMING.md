# Batch E11 Source-Ordered Safetensors Streaming

```text
E11_COMPLETE
SOURCE_ORDER_CORE_IMPLEMENTED = YES
DIRECT_SOURCE_TO_PINNED_IMPLEMENTED = YES

SOURCE_LAYOUT = ordered per-file data-region segments in one CUDA uint8 owner; each file base is 512-byte aligned and each tensor view uses file_base + source data offset
ALIGNMENT_GATE = per-tensor output element alignment, byte count, dtype, bounds, shape density, and CUDA owner-base alignment; ineligible files use the existing staged producer

CLIP_ELIGIBLE_PERCENT = NOT_AVAILABLE (no local CLIP safetensors manifest)
UNET_ELIGIBLE_PERCENT = NOT_AVAILABLE (no local UNET safetensors manifest)

SOURCE_READ_CALL_SHAPE = configured bucket size (256 MiB default), contiguous per-file extents, final partial block; local fixture used 8 MiB blocks
SOURCE_REPACK_BYTES = 0 on the eligible source-order exact-copy path

LOCAL_CURRENT_SOURCE_WALL_MS = 10.7432
LOCAL_SOURCE_ORDER_WALL_MS = 7.6793
LOCAL_DELTA_MS = -3.0639

LOCAL_CURRENT_PREPARE_PLUS_COMMIT_MS = 181.468
LOCAL_SOURCE_ORDER_PREPARE_PLUS_COMMIT_MS = 31.405
LOCAL_PREPARE_PLUS_COMMIT_DELTA_MS = -150.063

H2D_REGRESSION = NO
CORRECTNESS = PASS

LOCAL_TESTS = 42 E11/core tests passed; 11 E2/E3 tests passed; 26 D6/D15 tests passed
PYCOMPILE = PASS

REMOTE_RUNS=0
COMMIT=none

READY_FOR_INTEGRATION = YES
TOP_REMAINING_RISK = the local Windows run exercised the portable readinto path, not Linux preadv; actual CLIP/UNET manifest eligibility and remote storage behavior remain unmeasured
```

## Implementation

`comfymodal_runtime/source_order_safetensors.py` provides the generic source
layout, per-tensor eligibility gate, contiguous source-block iterator, and
direct `preadv`/portable `readinto` primitive. The latter writes into a
writable view backed by the supplied PyTorch CPU storage, so the exact-copy
path does not materialize an ordinary temporary tensor before the pinned slab.

`staged_safetensors.py` parses the existing safetensors header metadata and
builds source file records from the authoritative `data_offsets`, dtype, shape,
file identity, and data-region bounds. With
`COMFYMODAL_V2_STAGED_SOURCE_ORDER=1`, exact alignment-safe files use source
blocks and a source-order GPU owner. Tensor views are created after that owner
geometry is known. Converted tensors, dtype mismatches, invalid ranges, and
alignment failures remain on the existing staged path without invented model
specific padding.

The existing four-slab pool, pinned-budget accounting, event-safe slab reuse,
single CUDA copy stream, owner lifetime, and fallback behavior are unchanged.
The new source telemetry is exposed through `StageResult.metrics` and is
forwarded by the existing CLIP and UNET telemetry bridges. The new flag is
default off and is included in the existing deployment environment passthrough.

## Local Evidence

The physical A/B used one generated 32 MiB safetensors file, four producers,
four reusable slabs, one CUDA stream, and 8 MiB blocks to keep the local run
bounded. A was the existing destination-oriented packed producer. B was the
source-order direct reader. It was a single local sample, not a performance
claim for Modal storage.

| Metric | A current | B source-order |
|---|---:|---:|
| source-read wall ms | 10.7432 | 7.6793 |
| source-read worker accumulated ms | 23.5498 | 9.6905 |
| source-to-pinned copy bytes | 33,554,432 | 0 |
| source-to-pinned copy ms | 14.4665 | 0.0 |
| source repack bytes | 33,554,432 | 0 |
| prepare + commit wall ms | 181.468 | 31.405 |
| H2D DMA busy ms | 1.609 | 1.391 |
| H2D stream span ms | 22.170 | 19.984 |
| H2D bucket count | 4 | 4 |

The existing local CUDA synthetic benchmark also completed with status `OK`,
one stream, four producers, and zero Modal deploys/requests.

## Verification Limits

No local CLIP or UNET safetensors manifests were present, so percentages are
reported as unavailable rather than inferred from the E10 remote bucket
counts. The local host is Windows; the direct Linux `preadv` branch should be
checked on a future Linux runtime. No Modal deployment or remote run was made.
