# Production 7 baseline

Frozen and pushed. `production-006` was **not** moved.

## Identities

| identity | value |
|---|---|
| branch | `promotion/production-007` |
| tag | `production-007` (annotated) |
| tag object | `dd6f91c7f3a287b008fff9855d2f2fe3a7f016dc` |
| commit | `f37dcc78b2d4b438fea83ef0b31cd3d98ec0cac5` |
| parent (runtime baseline) | `c19e61c11b743069a81a4f3f16f3908f199e792d` = `promotion/production-006` |
| profile | `golden_p1_parallel_c0_p7_h100` |
| app | `batch-c0-p7-h100` |
| class / method | `ModalRuntimeEntrypointV2` / `run_golden_parallel_stream` |
| deploy fingerprint | `6928364e1bd2fd45f6c897baf32d7caa683e01ebc92d1d624ab47b3fd3d85242` |
| destination | Testing 9 / `ws_ee7221847f7d` |
| resources | H100!, CPU=12, 24576 MiB, min_containers=0 |
| expected output SHA | `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` |
| source-probe | `verdict=MATCH`, `diagnostics_verdict=PASS` |

## Ancestry (verified)

Base is the **clean healthy live-control lineage**, not the `production-006`
tag. All three required commits are ancestors of `c19e61c1`:

| commit | subject | status |
|---|---|---|
| `ce0a765e` | recover READY ownership from the slot table instead of aborting on a stale doorbell | **RETAINED** |
| `ec76b64c` | minimal post-request GPU teardown on single-use containers | present |
| `5ac6f704` | stop duplicating the output image in the terminal result | present |

`ec76b64c` and `5ac6f704` were **already ancestors** of the live-control head, so
no cherry-pick was required or performed. This promotion records them explicitly
rather than re-applying them.

`production-006` remains `42cf4d048a8dbc66535753a857cc5cd99135f074`, untouched.
It was deliberately **not** used as the base: it predates `ce0a765e`.

## Mechanical parity with the healthy control

Resolved-config diff of `golden_p1_parallel_c0_p7_h100` against
`golden_p1_parallel_c0_source_h100`: **154 keys each, 7 differences**, all of
them per-invocation bookkeeping (`COMFYMODAL_V2CTL_*`) or app/profile identity.

Confirmed for Production 7:
- `COMFYMODAL_GOLDEN_C0_MMAP_LIFECYCLE = whole`
- `COMFYMODAL_GOLDEN_C0_SOURCE_WORKER_KIND = thread`
- `COMFYMODAL_GOLDEN_C0_TRANSPORT_GEOMETRY = qd4_64`
- `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN = 1`
- arena `536870912` B = 512 MiB = 8 x 64 MiB

## Excluded by design

No M1B/M1C copy probes, diagnostic profiles, arena globals, bounded-runner or
hang tooling. Verified absent from `c19e61c1` before promotion:
`m1_copy_probe.py`, `run_golden_bounded.ps1`, `golden_evidence_gate.py`, and all
four diagnostic profiles.

## Acceptance: 10/10

All ten counted runs passed every criterion:

`valid=true`, exact expected SHA, fallback none, H100!, CPU=12,
min_containers=0 (single-use), whole mmap, thread source owner, qd4_64,
512 MiB arena, `MINIMAL_GPU_TEARDOWN=1`, no stale-READY failure, no protocol
error, no model-load gate failure, no `failures` entries.

### Source throughput

| | min | p50 | p90 | max | mean | CV |
|---|---|---|---|---|---|---|
| CLIP GB/s | 1.43 | 3.35 | 4.78 | 4.95 | 3.31 | 33.5% |
| UNET GB/s | 1.54 | 3.46 | 5.90 | 6.07 | 3.73 | 41.3% |

**Runs at or above 6.5 GB/s: CLIP 0/10, UNET 0/10.** Best UNET 6.07.

### Stage walls (ms)

| stage | min | p50 | p90 | max | mean | CV |
|---|---|---|---|---|---|---|
| clip load | 1626 | 2403 | 4162 | 5609 | 2809 | 42.8% |
| unet load | 2028 | 3603 | 6126 | 7976 | 4019 | 46.2% |
| clip forward | 2429 | 2991 | 3500 | 5285 | 3200 | 24.8% |
| vae decode | 497 | 540 | 632 | 783 | 569 | 14.6% |
| sampler tail | 0.02 | 0.02 | 0.03 | 0.03 | 0.02 | 12.8% |
| output | 206 | 240 | 257 | 257 | 236 | 7.6% |
| teardown | 0.59 | 0.77 | 1.05 | 1.13 | 0.80 | 22.4% |
| backend elapsed (s) | 15.3 | 25.1 | 54.5 | 57.9 | 29.6 | 47.3% |

Regions observed: ca, eu-north, eu-south, us-central, us-east.

`restore_count` / `request_count` are **not emitted per attempt** by this build
(summary attempts carry `None`); they are therefore not reported rather than
guessed. Single-use semantics are proven instead by `min_containers=0` plus
`true_cold` / fresh-container evidence in the run gate.

## Optimization verification

**1. Minimal teardown (`ec76b64c`) — proven active.**
Teardown stage completes in **0.59-1.13 ms** across all ten runs, and **0/10**
runs contain any unload / model-eviction / `empty_cache` evidence. The
heavyweight post-request `unload_all_models` path is definitively not executing
on the counted single-use runs.

**2. Duplicate PNG removal (`5ac6f704`) — proven active.**
**0/10** runs carry `image_data`, and **0** occurrences of `"image_data"` across
all ten terminal results. The duplicate payload is gone; the image is carried
exactly once.

## Regression assessment: none detected

No correctness regression: 10/10 valid, 10/10 exact SHA, zero failures, zero
fallbacks, zero protocol errors.

No performance regression attributable to either optimization:
- P7 CLIP p50 3.35 GB/s vs the fresh healthy-control cohort (10 runs,
  identical window) p50 4.61 GB/s; UNET 3.46 vs 4.40. P7 CVs (33.5% / 41.3%)
  are **wider** than the control's (32.3% / 25.0%), and at n=10 with CV ~33-41%
  the ~1.2 GB/s median difference is **within noise**. The distributions overlap
  heavily (control CLIP 0.89-5.34, P7 1.43-4.95). This is not evidence of a
  regression and is not claimed as one; it is also not evidence of an
  improvement.
- Both promoted optimizations are *tail* measures and neither touches the source
  read path, which is consistent with the observed overlap.

The dominant variance is placement-driven (unpinned `COMFYMODAL_V2_REGION` /
`COMFYMODAL_V2_CLOUD`), and that is unchanged from the control baseline.

## Honest caveats

- The `test_v2ctl_profiles::test_golden_p1_resolves_canonical_memory_and_keeps_golden_environment`
  failure is **pre-existing**; it reproduces identically on pristine `c19e61c1`
  and is not introduced by this promotion. Targeted suite: 150 passed, 5 skipped.
- Acceptance here means "identical correctness and mechanical shape to the
  healthy control", not "meets the 6.5 GB/s target". **0/10 runs met 6.5 GB/s.**
  That target remains open and, per the M1C findings, is a placement-dependent
  tail problem rather than a pipeline limit.