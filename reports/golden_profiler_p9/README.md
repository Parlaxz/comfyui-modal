# Production-009 profiler artifacts (derived reports)

Three traced Golden runs taken at `6b32025a` (production-009 + the four latent-defect
fixes, the report addendum and the two control-plane fixes) on app `batch-p9prof`,
workspace Testing 9.

| file suffix | trace id |
|---|---|
| `_b94149a5` | `b94149a5efb9484dbdf4a61947a64693` |
| `_bc298e38` | `bc298e38a0894136b21615e0c4493bd4` |
| `_4d2d4d5a` | `4d2d4d5a9f1b48efaf004fbbe7766ffd` |

Per trace: `golden_stage_report.md` (critical path, function rollup, per-stage call
trees), `golden_stage_gantts.md`, `golden_stage_trees.md`, and
`golden_process_manifest.json`.

## Reading these numbers

**The absolute milliseconds are inflated and are NOT comparable to unprofiled runs.**
Run `4d2d4d5a` shows a 17.6 s traced timeline against roughly 10.4 s untraced for the
same build. VizTracer adds overhead to precisely the stages it measures. Use these
reports for *ranking*, not for magnitudes; take magnitudes from an unprofiled cohort.

**n=3.** Report raw values with mean/median/min/max/SD/CV. Do not quote a p90.

**Python frames only** (`ignore_c_function=True`). GPU kernel time is invisible, so a
GPU-bound stage reads as waiting. Large "exclusive self time" in a thread worker or in
`select`/`EpollSelector` is blocking wait, not CPU burn.

## What they showed

Critical-path (uncontended fraction) from `4d2d4d5a`:

| stage | wall ms | on critical path |
|---|---:|---:|
| `golden_clip_load` | 3506.7 | 100.0% |
| `golden_sampling` | 5804.6 | 81.4% |
| `golden_vae_decode` | 1591.1 | 99.4% |
| `golden_output` | 301.5 | 99.6% |
| `golden_sampler_prepare` | 67.4 | 91.7% |
| `golden_clip_forward` | 6376.6 | 1.9% |
| `golden_unet_load` | 6249.0 | 0.0% |

Two things worth carrying forward:

- `golden_sampler_prepare` is 67 ms. The Triton pre-snapshot warm is working.
- `golden_unet_load` is **0% on the critical path**, fully hidden behind
  `golden_clip_forward`. The 223 ms UNET-load gap against production-006 is real in
  isolation but is not currently costing wall time. `golden_clip_forward` at 1.9% is
  likewise not a target. The protected stages are `golden_clip_load`,
  `golden_vae_decode`, `golden_output` and `golden_sampling`.

## Not included

The per-run bulk (~711 MB total: `golden_exhaustive_summary.json` at ~191 MB each,
`bundle.tar.gz`, raw viztracer JSONs) stays out of git. It lives under
`.slim/worktrees/p8fix/artifacts/golden_exhaustive_runs/` and is gitignored. Re-fetch
any of it without spending GPU time with:

```
python tools/golden_profile_pipeline.py report <trace_id>
```

## Provenance

All three runs are structurally valid: `valid`, exact output SHA, true-cold,
`restore_count == 1`, `request_count == 1`, method `run_golden_parallel_stream`,
no fallback. Source-probe `RESULT=PASS source_identity=MATCH` at `6b32025a`.