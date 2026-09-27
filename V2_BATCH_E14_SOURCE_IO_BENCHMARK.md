# V2 Batch E14 Source-I/O Benchmark

Date: 2026-08-16
Scope: source-only local harness implementation and fixture validation. No production loader behavior changed. No Modal deploys or requests.

## Harness

Implemented `tools/benchmark_source_io_e14.py` with deterministic multi-file
safetensors header parsing, absolute tensor-data extents, full-file SHA-256
identity, exact payload digest checks, and JSON/Markdown output.

The arms are:

- `CURRENT_RANGE`: range-shaped reads, using `os.pread` when available and a
  Windows-safe `seek/read` fallback.
- `SEQUENTIAL`: contiguous tensor-data regions in physical file order using
  256 MiB logical blocks by default.
- `TMP_STAGE`: full sequential source-to-temp copy, exact local reread, and
  combined timing with separate leg rates.
- `MMAP`: sequential exact tensor-data extent touches through read-only mmap.
- `PREAD`: only a clearly public top-level safetensors pread API; otherwise
  `UNSUPPORTED` without monkeypatching.

The optional pinned subtest is separate from primary source-I/O results. It
requires CUDA-backed PyTorch pinned allocation, uses bounded pageable and
pinned slabs, and does not perform H2D.

## Local Evidence

No production checkpoint files were found in the custom node, ComfyUI model,
or parent ComfyUI trees. Tests generated two valid same-basename shards with a
gapped tensor extent, an adjacent tensor extent, and trailing bytes.

The fixture smoke run processed 20 payload bytes across 2 files totaling 268
physical file bytes. All direct arms reported `status=ok`, exact payload byte
counts, and `digest_match=True`. `TMP_STAGE` reported 268 source-copy bytes
and 20 local reread bytes. The installed safetensors package exposed no
supported public pread API, so `PREAD=UNSUPPORTED`.

The 20-byte fixture is too small for throughput conclusions; rounded rates are
shown only to document execution:

```text
LOCAL_CURRENT_RANGE_GBPS = 0.000 (synthetic smoke fixture; not decision-useful)
LOCAL_SEQUENTIAL_GBPS = 0.000 (synthetic smoke fixture; not decision-useful)
LOCAL_TMP_COPY_GBPS = 0.000 (synthetic smoke fixture; not decision-useful)
LOCAL_TMP_REREAD_GBPS = 0.000 (synthetic smoke fixture; not decision-useful)
LOCAL_MMAP_GBPS = 0.000 (synthetic smoke fixture; not decision-useful)
LOCAL_PREAD_GBPS = UNSUPPORTED (no public installed safetensors pread API)
PINNED_FILL_OVERHEAD = 1.543x in one 20-byte CUDA fixture smoke run; not decision-useful
```

Cache labels are explicit: `cold_unknown`, `process_cold`, and
`page_cache_warm`. The harness never claims disk-cold behavior. Cache dropping
is opt-in, attempted per arm where supported, and reports Windows/root or
provider-side caching limitations. Fresh Modal containers may still have
distributed-filesystem/provider caching.

## Verification

```text
LOCAL_FILES_AVAILABLE = NO (production checkpoints unavailable)
LOCAL_BYTES_TESTED = 20 payload bytes; 268 physical fixture bytes
LOCAL_TESTS = python run_tests.py tests.test_benchmark_source_io_e14 (27 passed)
PYCOMPILE = python -m py_compile tools\benchmark_source_io_e14.py tests\test_benchmark_source_io_e14.py (passed)
REMOTE_WRAPPER_READY = YES (run_e14_source_io.bat; source-only, no Modal invocation)
MODAL_RUNS=0
COMMIT=none
READY_FOR_REMOTE_SOURCE_BENCHMARK = YES
```

The dedicated wrapper pins the 256 MiB sequential block, 32 MiB range shape,
and `cold_unknown` cache label by default. It launches only the standalone
benchmark and does not deploy or invoke Modal.

## Decision Boundary

The harness is ready to run against actual checkpoint shards later. These
local fixture results do not establish a remote storage conclusion. A remote
run should preserve the file identity, payload byte, digest, cache-label, and
per-arm physical-read fields before comparing source strategies.

E14_COMPLETE

HARNESS_IMPLEMENTED = YES

ARMS = CURRENT_RANGE / SEQUENTIAL / TMP_STAGE / MMAP / PREAD

LOCAL_FILES_AVAILABLE = NO
LOCAL_BYTES_TESTED = 20 payload bytes; 268 physical fixture bytes

LOCAL_CURRENT_RANGE_GBPS = 0.000 (synthetic smoke only)
LOCAL_SEQUENTIAL_GBPS = 0.000 (synthetic smoke only)
LOCAL_TMP_COPY_GBPS = 0.000 (synthetic smoke only)
LOCAL_TMP_REREAD_GBPS = 0.000 (synthetic smoke only)
LOCAL_MMAP_GBPS = 0.000 (synthetic smoke only)
LOCAL_PREAD_GBPS = UNSUPPORTED

PINNED_FILL_OVERHEAD = 1.543x synthetic smoke only

REMOTE_WRAPPER_READY = YES

LOCAL_TESTS = 27 passed
PYCOMPILE = PASSED

MODAL_RUNS=0
COMMIT=none

READY_FOR_REMOTE_SOURCE_BENCHMARK = YES
