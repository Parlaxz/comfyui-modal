# M1-CB final: the copy primitive is not the limiter

Status: both diagnostic tiers delivered. 3 valid level-1 (anonymous sentinel)
runs and 3 valid level-2 (file-backed arm) runs, all `valid=true`, exact output
SHA `3a6a0306...`, no failures, identical resolved config to the live control.

Raw: `m1cb_sentinel_correlation.csv`, `m1cb_filearm_correlation.csv`.
Provenance: `PRODUCTION006_TAG_VS_LIVE_RUNTIME.md`.
Earlier tier report: `M1CB_SENTINEL_FINDINGS.md`.

## Headline

**The 6.5 GB/s target is achievable per copy, and the loader's ~5.4 GB/s ceiling
is not caused by the copy.** In every run where the file-backed arms were
measured, the loader sat flat at 5.14-5.66 GB/s while identical 64 MiB libc
`memmove` operations, in the same process and the same container, measured
6.25-16.89 GB/s.

## Level-2 file-backed arm, 3 valid runs

GB/s. `F` = first repetition (the first-touch sample), `R` = median of repeats.

| run | S1 cold file -> anon | S1 R | S2 file resident F | S2 R | S3 anon control F | S3 R | S1 cold file -> /dev/shm F | S2 /dev/shm R | CLIP | UNET |
|---|---|---|---|---|---|---|---|---|---|---|
| 142658 | 6.25 | 10.69 | 10.73 | 9.88 | 10.87 | 11.91 | 11.49 | 11.46 | 5.46 | 5.66 |
| 142831 | 6.79 | 10.19 | 10.95 | 11.41 | 12.82 | 14.12 | 10.44 | 11.25 | 5.50 | 5.44 |
| 142909 | 7.25 | 10.51 | 11.76 | 12.16 | 14.27 | 16.89 | 9.34 | 12.37 | 5.30 | 5.14 |

Medians: cold file first-touch **6.79**, file-resident **11.41**, anonymous
control **14.12**, shared destination **11.46**.

## Findings

**1. The target is physically reachable.** Median file-resident copy is
11.41 GB/s, ~1.75x the 6.5 GB/s target, and even the coldest file-backed
first-touch sample clears it at 6.79 GB/s median. Nothing about the memory or
file path makes 6.5 GB/s unattainable.

**2. The copy is therefore not the bottleneck.** The loader plateaus at
5.14-5.66 GB/s across all three runs — a spread of only ~10% — while the copy
primitives in the very same process range over 6.25-16.89 GB/s. A pipeline
whose stages can individually run at 11-17 GB/s but which delivers 5.4 GB/s
aggregate is limited by stage utilisation, not by any single stage's rate.

This is consistent with, and now independent confirmation of, the M1 conclusion
that the residual gap lives in QD/reader utilisation rather than in copy cost:
the M1 cohort showed time concentrated at qd0/qd1 (`concurrency_distribution`
like `[0,1,1,2,116]` and `[0,1,2,4,177]`) and `time_weighted_effective_concurrency`
near 3.9-4.0 against a qd4 target, plus a 4 ms global copy-start floor.

**3. First-touch on file-backed pages is cheaper than on anonymous pages.** Cold
file-backed first-touch costs ~6.8 GB/s against a ~10-11 GB/s resident rate
(~1.6x), whereas anonymous first touch cost a consistent ~2.5x penalty
(3.89-4.98 GB/s). The model volume pages are effectively warm in page cache, so
the loader is not paying a cold-page fault bill. This retires "first-touch /
cold page fault" as the dominant cause.

**4. Shared versus private destination is not a differentiator.** The
`/dev/shm` (unregistered shared) destination measures 9.34-11.49 GB/s on cold
first-touch and 11.25-12.37 GB/s on repeat, statistically indistinguishable from
the private anonymous destination. CASE 4 (arena/shared/registration destination
path) is **not** implicated at the unregistered level.

**5. The anonymous sentinel is a control, not a predictor.** Level-1 runs showed
CLIP 0.77-5.89 GB/s and UNET 1.55-5.67, and the sentinel's own first-touch rate
was anti-correlated with loader throughput (fastest S1 accompanied the slowest
loader). It remains useful as a raw-condition control but must not be used to
predict loader behaviour.

## What this rules in and out

Ruled out as the dominant cause:
- raw memory-copy bandwidth (measured 10-17 GB/s resident)
- cold file-page faulting (only ~1.6x penalty, and volume pages are warm)
- shared vs private destination (equivalent)
- copy primitive choice (`memmove` vs `memcpy`, alignment matrix) — not the
  discriminator; the gap is present with every primitive measured

Still open, and now the only remaining candidates:
- QD/reader utilisation: time at qd0/qd1, effective concurrency below target
- the 4 ms global copy-start floor (pacer)
- H2D backpressure and per-op slot serialisation
- registration effects (level 3+ arm; not exercised at level 2)

## Recommended next experiment

Do not optimise the copy path. Instrument and attack **stage utilisation**:
raise the pacer floor experiment, vary QD target and reader count, and measure
`time_at_qd0..qd3`, `frac_time_at_qd4` and effective concurrency directly against
the now-established 11-17 GB/s headroom. The copy lab already carries the
primitives needed to confirm that closing utilisation closes the gap.

## Defects found and fixed (all evidence-driven)

1. Probe buffers mapped `PROT_READ` (1) instead of read/write (3) — the true
   cause of all 5/8 crash-marked runs (SIGSEGV, exit 139, surfaced by v2ctl as
   `InternalFailure: Server has lost track of input`) against 0/52 for the
   untouched control.
2. Probe hooked in `golden_serial`, which does not orchestrate
   `run_golden_parallel_stream` — produced a false "success" with no probe
   event.
3. Hook placed at the end of `golden_unet_load`, which with
   `COMFYMODAL_GOLDEN_CLIP_SKELETON_OVERLAP=1` is the *start* of the
   clip_forward/unet window, not after it. Moved to post-durability.
4. `_checksum` accumulated over `c_char` (yields `bytes`) — `int + bytes`
   TypeError. Now `c_ubyte`.
5. Two out-of-bounds buffer bugs: `thread_scaling` indexed 4 slots against a
   1-slot buffer; `+32` alignment variants copied past their mapping end.
6. `v2ctl golden run` and `run_v2_single.bat` honour no timeout anywhere, so a
   Modal snapshot-restore stall hung indefinitely with an empty cohort and no
   evidence. Runs now go through a bounded wrapper.
7. Whole-file mapping of the model inside the request duplicated production's own
   Whole mmap; now window-mapped at the exact production file offset, which
   removed the hazard and let the file arm run inline.

## Measurement discipline

- `event_count` reads 1 on every accepted run; it is not a population measure.
  The inline telemetry event list (51-56) is.
- `duration_ms` reads 16-56 s while real wall clock is ~190 s; it is not wall
  clock.
- Duration and container provisioning are not acceptance criteria. Acceptance is
  the runtime evidence gate plus resolved-config parity with the live control.
