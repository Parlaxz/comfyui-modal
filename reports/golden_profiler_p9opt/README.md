# Production-009 easy-optimization profiler artifacts (derived reports)

Three traced Golden runs for the P9 easy-optimization pass, taken at source
`fbd81c46` on app `batch-p9opt1-prof`, deploy fingerprint
`9eb93a2bff26c92bfb85a8946eeb4bd73bbb28ac33bbe3e7b4c7cb1553f83aec`,
workspace Testing 9, profile `golden_p1_parallel_c0_p8_h100`.

The candidate carries three changes relative to the P9 baseline: a 16 x 64 MiB
C0 source arena, compact per-block source-latency plus CPU/NUMA/GPU placement
telemetry, and a pre-resolved dynamic UNET safetensors layout.

| file suffix | trace id | role | traced timeline |
|---|---|---|---:|
| `_ad2f1cf4` | `ad2f1cf4b36046c2a797cb60243d445a` | GOOD (healthy) | 14590.0 ms |
| `_25172b0c` | `25172b0c43f04a22a48878732ad07d10` | GOOD (fastest) | 13041.8 ms |
| `_ddb6c39a` | `ddb6c39a7fdc4c4890a4724bd617038a` | BAD | 19222.3 ms |

Per trace: `golden_stage_report.md` (critical path, function rollup, per-stage
call trees), `golden_stage_gantts.md`, `golden_stage_trees.md`, and
`golden_process_manifest.json` (saved here as `manifest_<suffix>.json`).

The third run was captured deliberately. The first two came in under 16 s, so
capture continued until a run exceeded that threshold, which is where P9's
WORST run sat (17.6 s). That is the only reason `_ddb6c39a` is in this set.

## Reading these numbers

**Absolute milliseconds are inflated and are NOT comparable to the ten
unprofiled normal runs.** The three request walls were 87487 ms, 42604 ms and
86464 ms; the stage walls below sum to roughly a sixth of that. VizTracer plus
the C0 child VizTracer add overhead to precisely the stages they measure. Use
these reports for mechanism and ranking; take magnitudes from the ten-run
normal cohort.

The traced timeline (the sum of observed stage walls) is the figure quoted in
the table above, and it is the metric compared against P9's 17.6 s.

**n=3.** Report raw values with mean/median/min/max/SD/CV. Do not quote a p90.

**Python frames only** (`ignore_c_function=True`). GPU kernel time is invisible,
so a GPU-bound stage reads as waiting. Large exclusive self time in a thread
worker or in `select`/`EpollSelector` is blocking wait, not CPU burn.

**Coverage.** All three traces report `GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE = NO`
with reason `no_root_corrupting_incomplete_calls: incomplete_calls=16`, plus
`report_artifact_written`. Clock alignment is clean: one traced process,
max skew 0 ns. `c_function_tracing` is false by design. The `NO` is the
profiler's fail-closed coverage flag and is expected for this configuration.

## What they showed

Critical path (uncontended fraction of each stage):

| stage | GOOD healthy | GOOD fastest | BAD |
|---|---:|---:|---:|
| `golden_clip_load` | 99.8% | 99.8% | 99.9% |
| `golden_sampling` | 80.0% | 86.9% | 84.1% |
| `golden_vae_decode` | 99.5% | 99.0% | 99.2% |
| `golden_output` | 98.1% | 99.4% | 98.1% |
| `golden_sampler_prepare` | 89.3% | 99.2% | 96.1% |
| `golden_clip_forward` | 15.4% | 21.1% | 25.9% |
| `golden_unet_load` | 0.0% | 0.0% | 0.0% |

`golden_unet_load` is still fully hidden behind `golden_clip_forward` in all
three, exactly as in P9. The UNET layout parse no longer runs there: the
pre-resolve completed before CLIP forward in 3 of 3, and the request-time UNET
`layout_resolve_ms` was 0.93 / 6.93 / 1.07 ms. The P9 lockstep pairing of a
918-1419 ms `_parse_layout` against an 898-1399 ms CLIP tokenize is gone.

The protected stages remain `golden_clip_load`, `golden_sampling`,
`golden_vae_decode` and `golden_output`.

## Not included

The per-run bulk stays out of git, as it did for P9. Per trace that is
`golden_exhaustive_summary.json` (187-191 MB), `golden_exhaustive_calls.csv.gz`
(~10 MB), `viztracer_merged.json.gz` (~13 MB) and `bundle.tar.gz`. It lives
under `artifacts/golden_exhaustive_runs/<trace_id>/<trace_id>/session/` and is
gitignored. Re-fetch any of it without spending GPU time with:

```
python tools/golden_profile_pipeline.py report <trace_id>
```

## Provenance

All three runs are structurally valid: `valid`, exact output SHA
`3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577`,
true-cold, `restore_count == 1`, `request_count == 1`, single-use containers,
method `run_golden_parallel_stream`, no fallback. Source-probe
`RESULT=PASS source_identity=MATCH` before each run.

These three ran on a **separate profiling deployment** (`batch-p9opt1-prof`,
fingerprint `9eb93a2b`, which adds the tracing flags) from the ten normal runs,
which ran on `batch-p9opt1-h100` at fingerprint `3f8d103d`. Same source
`fbd81c46`, same profile, same workflow and models. The ten normal runs were
never re-measured against the traced deployment and the profiled deployment was
never used for a counted run, so no cohort mixes the two identities.