---
name: benchmark-modal
description: Run comfyui-modal benchmarks. Use when benchmarking or measuring Modal performance.
---

# Benchmark Modal

## Control-plane authority

This repository's authoritative deployment and benchmark entry point is the
newer `tools/v2ctl.py`. There is no `v2cli.py` file in this repository. Before
remote work, inspect `python tools/v2ctl.py --help` and resolve the requested
profile through v2ctl.

Use only the v2ctl path for new non-Golden work:

1. `python tools/v2ctl.py deploy-run --profile <profile>` to deploy.
2. `python tools/v2ctl.py run --profile <profile>` to run.
3. `python tools/v2ctl.py gate --profile <profile>` to validate acceptance and provenance.

For Golden work, load `.opencode/skills/comfymodal-golden-ops/SKILL.md` and use
its public `golden status`, `golden deploy`, and `golden run` commands with an
isolated app. Do not use the generic `deploy-run` or generic `run` commands for
Golden. Golden output durability is governed by
`docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`: generated-output durability is
off by default; use `COMFYMODAL_OUTPUT_DURABILITY=strict` only as an explicit,
resolved opt-in and never weaken S4/source publication durability.

## Benchmarking and profiling are different questions

Benchmarking answers *how long* and *did it get better*. Profiling answers *where
the time went*. When the question is why a number is what it is, do not infer it
from the benchmark summary.

For a Golden run, one command does the whole profiling loop:

```text
python tools/v2ctl.py golden profile --app <experimental-app>
```

It deploys with tracing, verifies the deployment landed via source-probe, runs
one request, then downloads and SHA-verifies the bundle, analyzes it and writes
the decision report, printing the final path. It performs a real deploy and run,
so it costs GPU time; `--dry-run` prints the plan without invoking anything. It
aborts if source-probe does not report `RESULT=PASS`, so a stale deployment is
never profiled.

To analyse an already-downloaded trace without spending GPU time:

```text
python tools/golden_profile_pipeline.py latest                # recent trace ids + bundle sha
python tools/golden_profile_pipeline.py report <trace_id> --skip-analyze   # re-render only
```

Final artifact:

```text
artifacts/golden_exhaustive_runs/<trace_id>/<trace_id>/session/derived/golden_stage_report.md
```

Read it in this order:

1. **Critical path and stage overlap.** Sum of stage walls exceeds the request
   wall because stages overlap, so the biggest stage is often the wrong target.
   A stage at 0% on the critical path is fully hidden behind a longer sibling;
   optimising it moves nothing.
2. **Function rollup.** Totals, not means: 318 calls at 22 ms is 7 seconds.
   Inclusive wall contains callees, so totals are not additive down a tree.
3. **Per-stage call trees.** Recursive, expanded at a wall floor.

Before acting on a profile:

- The tracer sees **Python frames only**. GPU kernel time is invisible, so a
  GPU-bound stage reads as waiting.
- Large self time in a worker, `select` or `EpollSelector` is **blocking wait**,
  not CPU burn.
- A profile is **observational**. It localises cost; it does not prove a change
  helps. Confirm with an A/B run before claiming a win.

Full procedure and report format: `.opencode/skills/comfymodal-golden-ops/SKILL.md`.

Record the deployment, run, and gate manifest paths plus the resolved profile
and flags. For Golden work, fail closed if the resolved target is a different
app or restore-only/default profile.

`deploy_and_run_v2_single.bat` and `run_v2_single.bat` are legacy compatibility
wrappers only. Do not invoke them directly for new work or treat them as the
source of truth; use them only when v2ctl invokes them or when the user
explicitly requests a legacy reproduction.
