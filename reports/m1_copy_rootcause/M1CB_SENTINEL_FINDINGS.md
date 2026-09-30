# M1-CB interim: inline copy sentinel vs real loader throughput

Status: inline sentinel tier established and validated (3/3 valid instrumented
runs, exact SHA, exact memcmp). Standalone copy lab not yet built.

App `batch-c0-copy-rootcause-h100`, profile
`golden_p1_parallel_c0_copy_rootcause_h100`, deploy fingerprint
`5f2351b2580b2762d700c7b436f6fdae6f84ab6ec3839c00f8f138318091b9fa`, Testing 9.

## Runs

| run | valid | exact SHA | memcmp | S1 GB/s | S2 GB/s | S3 GB/s | S1/S2 | clip GB/s | unet GB/s | clip ms | unet ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| run_20260930-134721 | yes | yes | pass | 4.98 | 12.43 | 11.97 | 2.50 | 0.77 | 1.55 | 10503 | 7962 |
| run_20260930-134828 | yes | yes | pass | 3.89 | 10.88 | 11.68 | 2.80 | 4.59 | 4.90 | 1752 | 2513 |
| run_20260930-140105 | yes | yes | pass | 4.70 | 11.16 | 12.13 | 2.38 | 5.89 | 5.67 | 1366 | 2172 |

Raw: `m1cb_sentinel_correlation.csv`.

Sentinel = 64 MiB `memmove` under libc, measured after generation completes and
the result is durable. S1 is the first touch of a never-written anonymous
source; S2 repeats the same range into an independent destination; S3 repeats
into the first destination.

## Findings

**1. The 6.5 GB/s target is achievable on the raw copy path.** Resident 64 MiB
`memmove` sustains 10.9-12.4 GB/s in every run, ~1.7-1.9x the target. Raw
memory-copy bandwidth is not the constraint.

**2. First-touch is the dominant cost, and it is consistently ~2.5x.** S1/S2 is
2.38-2.80 (median 2.50) purely on anonymous memory, i.e. with page-fault and
zero-page cost alone and no file service at all. Anonymous first touch never
reaches the target (3.89-4.98 GB/s).

**3. The anonymous sentinel does NOT predict real loader throughput.** This is
the decisive negative result. Run `134721` had the *fastest* S1 of the three
(4.98 GB/s) and simultaneously the *catastrophically slowest* loader: CLIP at
0.77 GB/s taking 10.5 s, UNET at 1.55 GB/s. Runs `134828` and `140105` had
*slower* S1 (3.89, 4.70) and 6-7x faster loaders (4.59/4.90 and 5.89/5.67).
The relationship is anti-correlated across this sample.

Interpretation: the loader's variance lives in the **file-backed** source path,
and an anonymous-memory sentinel does not observe it. In the CASE taxonomy this
is CASE 3 — the minimal sentinel is stable and simply missing the dimension that
matters — despite the first-touch/repeat contrast itself being CASE 1/2 shaped.

**4. The real variance is large and unresolved.** CLIP source throughput spans
0.77-5.89 GB/s (7.7x) and UNET 1.55-5.67 GB/s (3.7x) across three valid runs.
Neither reaches the 6.5 GB/s target in any run. The target is comfortably
reachable for resident copies, so the gap is first-touch cost on file-backed
pages, not bandwidth.

## Consequences for the plan

- The file-backed arm must come back, but **not inline**. Whole-file mapping of
  the 8 GB CLIP / 12 GB UNET safetensors is unsafe inside the Golden request
  because the production loader already holds its own Whole mmap of the same
  file in the same process; the inline file arm is the reason levels 2-4 were
  moved out.
- Next: build the standalone copy lab (tier B) on its own entrypoint, same
  image / H100 / CPU=12 / 24 GiB / gVisor / model mount, no Golden generation,
  running levels 2-4 with per-phase checkpoint emission. It must measure
  file-backed first-touch vs resident, private vs shared vs registered
  destinations, 1/2/3/4-thread scaling, alignment, memmove vs memcpy, remap, and
  direct file-mmap to H2D.
- The inline sentinel stays as the correlation anchor, but it must be read as a
  *control* on raw copy condition, not as a predictor of loader throughput.

## Defects found and fixed while establishing this tier

All were found by evidence, not guesswork, and each is recorded in git history:

1. **Probe buffers mapped `PROT_READ`.** `_anon` passed `prot=1` while its own
   comment claimed read/write. Every probe buffer is a copy destination, so the
   first write was a guaranteed SIGSEGV (exit 139, surfaced by v2ctl as
   `InternalFailure: Server has lost track of input`). This caused 5/8
   crash-marked diagnostic runs against 0/52 for the untouched control, and it
   reproduced identically at every level, size and placement because `_anon` is
   called unconditionally. `PROT_READ|PROT_WRITE` is 3.
2. **Probe hooked in the wrong module.** `run_golden_parallel_stream` is
   orchestrated by `golden_parallel`, not `golden_serial`. A hook placed in the
   serial runner's post-result path never executed and silently produced no
   probe event — a false "success".
3. **Hook placement inside the overlap window.** Running the probe at the end of
   `golden_unet_load` is not "after the loads": with
   `COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP=1` that function completes at the
   *start* of the clip_forward/unet window. It now runs after
   `build_final_result()`, with the source owner idle.
4. **`_checksum` accumulated over `c_char`.** Indexing a `c_char` array yields
   one-byte `bytes`, so `acc * 31 + buf[off]` raised
   `TypeError: unsupported operand type(s) for +: 'int' and 'bytes'`. Now
   `c_ubyte`.
5. **Two out-of-bounds buffer bugs** in the wide matrix: `thread_scaling`
   indexed 4 disjoint slots against a single-slot buffer, and the `+32`
   alignment variants copied a full `SLOT_BYTES` past the end of theirs.
6. **No timeout anywhere.** `v2ctl golden run` has no timeout knob and
   `run_v2_single.bat` honours none, so a container stalling in Modal snapshot
   restore blocks indefinitely with an empty cohort directory and no recorded
   evidence. Runs are now issued through a bounded wrapper (900 s) that kills
   the client on expiry and preserves the empty cohort as failure evidence.

## Measurement discipline notes

Two fields that look like anomalies are not, and were previously misread:

- `run_artifact["event_count"]` reads **1 on every accepted run** (51-55 events
  are present inline). It is not a population measure.
- `run_artifact["duration_ms"]` reads 16-56 s across valid runs while
  `backend.elapsed_seconds` is ~190 s. It is not wall clock.

Neither is used for acceptance. Duration and container provisioning are not
acceptance criteria; acceptance is the runtime evidence gate
(`valid`, `dnf=false`, exact SHA, expected method/profile, H100, CPU=12, Whole
mmap, thread source-owner mode, no fallback, no stale READY, no InternalFailure,
normal event population, exact transport coverage, QD quiesced, reader pool
persistent) plus resolved-config parity with the live control.
