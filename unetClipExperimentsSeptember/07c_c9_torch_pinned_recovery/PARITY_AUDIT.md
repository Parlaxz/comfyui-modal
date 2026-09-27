# C9 Torch-Pinned Recovery Parity Audit

## Decision scope

This is the corrected recovery candidate. The earlier
`07b_c9_faithful_recovery` mlock smoke and the prior C9 cohorts are retained
as **NON_DECISION / WRONG_MECHANISM** evidence; they are not overwritten or
combined with this campaign.

## Authoritative mechanics

The historical C9 implementation in
`comfymodal_runtime/unet_qd_probe.py:406-506` uses:

- `torch.empty(nbytes, dtype=torch.uint8, pin_memory=True)`;
- one reusable pinned tensor per worker;
- `memoryview(buffer.numpy())` as the `os.preadv` destination;
- one shared read-only file descriptor;
- positioned `os.preadv` calls over static, disjoint contiguous ranges;
- no H2D copy in the source-only measurement.

The corrected candidate uses those same mechanisms. It does not call
`mlock`, `munlock`, `mmap` for pinning, or ctypes page-lock APIs, and it does
not silently fall back to pageable memory. Each worker records
`tensor.is_pinned() == True`; allocation failure is a failed capability/result,
not a valid performance observation.

## Timing boundaries

- `C9_TOTAL_WALL_MS`: immediately before per-worker buffer allocation through
  worker thread startup, all physical reads, and all worker joins.
- `PHYSICAL_READ_SPAN_MS`: first physical `preadv` begin through final
  physical `preadv` end; diagnostic only.

Normal performance runs retain bounded read-size evidence and do not enable
per-read forensic telemetry, hashing, JSON serialization, or profiling in the
hot loop. Forensic mode is separate and excluded from performance medians.

## Runtime shape

- Workspace: Testing 7 only, asserted programmatically before deploy and run.
- CPU: exactly 12.
- Memory: 8192 MiB.
- GPU: RTX PRO 6000.
- H2D: not initialized or performed.
- Model construction: not performed.
