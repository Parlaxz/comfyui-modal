# RA8 VAE load variance report

## Scope and status

RA8 is a narrow, measurement-only decomposition of `golden_vae_load` and its
QD transport. It does not change VAE ownership, add prewarming, alter snapshot
behavior, or implement the reusable shared pinned pool reserved for RA9. No
remote deployment or Golden request was made; remote validation remains
deferred until RA2B is complete and the user resumes the lane.

## Before/after path

Before, the VAE stage exposed one enclosing stage wall and a few aggregate QD
counters:

```text
golden_vae_load
  -> read_file_qd_gpu
     -> parse header / allocate CUDA destination and pinned slots
     -> source worker reads and async H2D
     -> join workers / wait completion events
  -> comfy.sd.VAE construction
  -> pointer adoption proof
  -> ready
```

After, the same path emits bounded diagnostics at these semantic boundaries:

```text
golden_vae_load (authoritative entry -> return/raise wall)
  -> source open, header/layout timing
  -> QD staging allocation, allocation count/bytes, reuse count, retained bytes
  -> source reads and CPU -> pinned-staging intervals
  -> H2D enqueue intervals and CUDA event durations when available
  -> worker join, event waits, and quiescence proof
  -> skeleton / dynamic patcher construction
  -> dtype/device finalization
  -> storage adoption pointer proof
  -> compute-ready return boundary
  -> process major/minor page-fault delta (supporting evidence only)
```

The implementation remains one physical source read and one H2D transport.
The QD worker/event lifecycle is unchanged; event timing is observed at the
existing required completion waits and does not add a device-wide
`synchronize()`.

## What is now visible

`golden_vae_load` emits `vae_load_decomposition` with schema
`vae_load_decomposition_v1`, plus the same decomposition in the successful
stage details. The nested `golden_qd_transport_diagnostics_v1` data reports:

* source bytes and reconciled read bytes;
* source-open/header/layout timing;
* pinned staging allocation count, bytes, allocation time, reuse count, and
  retained bytes;
* source-read and CPU-to-pinned-staging timing intervals;
* H2D enqueue intervals;
* CUDA event duration/count and effective H2D GB/s when CUDA event timing is
  available;
* host RSS/memlock visibility and cheap CUDA allocator counters when exposed;
* worker join, event-wait, copy-complete, and operation-live state;
* effective source GB/s from reconciled source bytes and observed source span.

The VAE stage separately records construction, dtype/device checks, storage
adoption, and compute-ready boundaries. Page faults use
`resource.getrusage(RUSAGE_SELF)` when available and record before/after values
plus major/minor deltas. They are explicitly marked
`supporting_evidence_only`; they are not a causal diagnosis and are not added
to stage timing.

## Non-additivity and timing interpretation

QD workers overlap source reads, CPU-to-pinned copies, and H2D enqueue. CUDA
event values are the sum of per-copy device-event durations, not a wall-clock
stage contribution. The decomposition reports interval sum, union, overlap,
and residual relative to the authoritative stage wall. It explicitly marks
nested timings non-additive and must not be interpreted as a sum of all listed
components.

The authoritative boundary remains actual `golden_vae_load` entry through its
successful return or raise. Child events explain that wall; they do not
replace it or move work outside the timer.

## QD owner/staging audit

Static source audit confirms that each `read_file_qd_gpu` owner allocates:

```text
qd workers × 2 slots × block_bytes
4 × 2 × 32 MiB = 256 MiB pinned staging (canonical settings)
```

The allocation is per transport/owner. CLIP owners are retained in
`session.clip_owners`, UNET in `session.unet_owner`, and VAE in
`session.vae_owner`; staging is released during teardown. Therefore CLIP and
UNET staging can remain live when VAE starts, plausibly leaving approximately
512 MiB of earlier pinned staging before VAE allocates its additional 256 MiB.
This is confirmed ownership behavior, not proof that it caused the observed
healthy-host variance.

`GoldenQDOwner.release_staging()` is documented and implemented as safe after
transport quiescence because it drops only pinned-slot references while
retaining the CUDA backing storage. However, current ownership has no lease or
pool contract that permits another owner to reuse those slots. RA8 therefore
does not release VAE staging early or introduce reuse. `release_storage()` is
not safe while adopted tensors remain live.

## Hypothesis assessment

| Candidate | Locally visible now | Current conclusion |
|---|---:|---|
| Pinned staging allocation / page-lock cost | Yes: allocation timing, bytes, RSS/memlock, allocator visibility | Unproven until remote cohort data exists |
| Pinned staging reuse | Yes: QD slot reuse count and retained bytes | Reuse occurs within each owner; cross-owner reuse is not implemented |
| Earlier CLIP/UNET staging retained | Yes: static owner lifetime audit | Confirmed statically; causal effect unproven |
| Host-memory pressure / fragmentation | Partial: RSS, max RSS, memlock limits, allocator counters | Supporting visibility only; causal effect unproven |
| Source I/O | Yes: reconciled bytes, source interval, effective source GB/s | Requires remote comparison |
| Actual H2D | Yes when CUDA events expose elapsed time; enqueue/wait always visible | Requires remote comparison; event value is non-additive |
| Adoption / patcher construction | Yes: separate construction, dtype/device, adoption, ready spans | Requires remote comparison |
| Major/minor page faults | Yes where `resource.getrusage` is available | Supporting evidence only |
| Pathological ~2.85 s host | Not targeted by local change | Context only; not treated as the healthy-host root cause |

The healthy-host ~3x variance remains **UNPROVEN**. The instrumentation is the
smallest next evidence path for distinguishing allocation/page-lock pressure,
source I/O, H2D, and adoption work without pretending overlapped timings are
additive. No obvious safe VAE-local optimization is proven by source alone.

## Changed files owned by RA8

* `comfymodal_runtime/golden_serial.py` — reusable QD timing/visibility
  helpers and VAE load decomposition, including optional page-fault deltas.
* `tests/test_p1_golden_serial.py` — offline aggregation and schema tests.
* `RA8_VAE_LOAD_VARIANCE_REPORT.md` — this report.

The worktree also contains unrelated concurrent RA2B/RA3/RA6/RA7 changes. They
were not reset, reverted, or folded into the RA8 report.

## Local validation

* `pytest tests/test_p1_golden_serial.py -q -k "ra8 or aggregation or page_fault"` — **2 passed**.
* `pytest tests/test_p1_golden_serial.py -q` — **101 passed, 2 failed**. The
  failures are existing/concurrent durability-event-order expectations caused
  by `DURABLE_COMMIT_SUBSPANS` events outside RA8 ownership; they are not
  modified here.
* `python -m py_compile comfymodal_runtime/golden_serial.py` — passed.
* `git diff --check` — passed.

## Deferred remote validation

After RA2B is complete and the user resumes, use the existing Golden public
control plane and a new isolated experimental app. Deploy the frozen source,
run source-probe and doctor/status checks, then make one Golden request per
invocation. Apply the snapshot-capture rule: a capture and its directly
following request are invalid. Compare only structurally valid, equivalent
deployment observations and retain failures and slow outliers.

The first RA8 cohort should compare the authoritative VAE stage wall with:
`vae_load_decomposition.stage_wall_ms`, staging allocation time/bytes,
prior-owner staging state, source effective GB/s, H2D event GB/s and waits,
construction/adoption durations, memory visibility, and page-fault deltas.
Do not sum child spans into the stage wall or treat page faults as proof of
causality.

RA8_IMPLEMENTATION_COMPLETE=YES
VAE_LOAD_DECOMPOSED=YES
PINNED_STAGING_ALLOC_TIME_VISIBLE=YES
SOURCE_IO_TIME_VISIBLE=YES
H2D_EVENT_TIME_VISIBLE=YES
ADOPTION_TIME_VISIBLE=YES
PRIOR_QD_OWNER_STAGING_RETAINED=YES
HEALTHY_3X_VARIANCE_ROOT_CAUSE=UNPROVEN
RA9_SHARED_POOL_PREEMPTED=NO
READY_FOR_REMOTE_VALIDATION=YES
REPORT=RA8_VAE_LOAD_VARIANCE_REPORT.md
