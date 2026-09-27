# C9 Faithful Recovery — Mechanical Parity Audit

Authority for the historical column is code, not report prose:
`comfymodal_runtime/unet_qd_probe.py:406-453,459-506,592-735`.
The old-recovery column describes the superseded implementation used by the
prior `07_c9_high_qd_recovery` bundle.  The corrected column describes the
current source-only arm after repair.

| Property | Historical C9 | Old recovery | Corrected oracle |
|---|---|---|---|
| workspace | Not recorded in the authoritative probe code/report | Testing 3 (superseded; invalid for this campaign) | Testing 7, asserted before deploy/invoke |
| CPU | 32 vCPU historical deployment | 4 | 12 exactly |
| physical block | 32 MiB `os.preadv` syscall bound | 32 MiB nominal, but worker loop read into fresh buffers | 32 MiB `os.preadv` bound, final tail only |
| FD topology | One FD opened by `run_qd_config`, shared by workers | One FD opened inside each worker | One shared FD opened before timing, closed after joins |
| worker topology | QD threads, one static contiguous range per worker | QD thread-pool workers, one range per worker | QD threads, one static contiguous range per worker |
| range assignment | Static disjoint contiguous ranges | Static disjoint contiguous ranges | Static disjoint contiguous ranges |
| buffer type | `torch.empty(..., dtype=uint8, pin_memory=True)` | New `bytearray` per physical read | One anonymous `mmap` buffer page-locked with `mlock` per worker (no GPU driver required) |
| buffer lifetime | Allocated before timed worker phase; reused | Per-read allocation | Allocated before `SOURCE_WALL`; reused for every assigned read |
| preadv helper | `_preadv_fill(fd, mv, file_off)` with short-read retry | `_physical_source_read` with telemetry and per-read target | `_physical_source_read` into reusable buffer; short-read retry |
| hashing in timed loop | None | SHA256 for every measured block | None; integrity verification not performed on primary arm |
| allocation in timed loop | None | Fresh ~32 MiB allocation per read | None |
| telemetry in timed loop | Lightweight per-block `perf_counter` timing | Full `ActualSourceTelemetry` event path per syscall | None in primary arm; optional forensic mode only |
| timing boundary | Thread start -> all worker joins (`run_qd_config:663-672`) | Telemetry-derived source interval | First worker thread start -> all worker joins; FD/buffer setup excluded |
| CUDA/H2D | Separate historical GPU phase; not part of raw source arm | Absent | Absent |
| model construction | Absent from raw QD arm | Absent | Absent |

## Corrected source path

`comfymodal_runtime/source_ceiling_oracle.py:_run_source_only` opens the
single descriptor, allocates one page-locked reusable buffer per worker,
starts the QD threads, reads positioned static ranges, joins every thread,
and only then closes the descriptor/unlocks/releases buffers.
`c9_recovery_modal.py` requests CPU 12 and 8192 MiB, with no accelerator.
`tools/run_c9_recovery.py` rejects any result whose requested or observed CPU
is not 12 and rejects any workspace whose active registry label is not exactly
`Testing 7`.

## Gate

This audit is a pre-deployment artifact.  No corrected-campaign deployment or
remote invocation is authorized until the focused offline tests pass and the
deployment command records the Testing 7 workspace identity in the new
campaign manifest.
