# RX9P-D — Golden VizTracer Deep Profiler

## Status

Implemented on the isolated `rx9p-d-golden-profiler` branch from `TESTING2`.
This lane was not integrated, deployed, or executed against Modal/GPU/paid
infrastructure.

## Runtime wiring

- The direct `run_golden_serial_stream` adapter claims the existing full-trace
  session only after request-id containment validation and before GPU readiness
  or Golden model work.
- The Golden operation is opened once and closed once on both success and
  error paths. Final milestones and artifact finalization occur before the
  terminal event; finalization itself is outside the VizTracer interval.
- VizTracer and optional Torch profiler start/stop boundaries remain on the
  adapter's execution thread. Full-trace OFF remains inert.
- CLIP timing mirrors the existing stage diagnostics into full-trace spans.
  UNET adds only the requested semantic seams: header/preflight, patcher
  construction, source/H2D transport, assignment/adoption, validation, and
  transport quiescence.

## Derived Golden artifacts

Offline report generation reuses normalized raw evidence and writes:

- `derived/golden_profile_summary.json` — machine-readable status, one selected
  `golden_serial_execute` root, recursive spans, canonical stages, residuals,
  and Torch CPU/CUDA summaries.
- `derived/golden_profile_report.md` — bounded human-readable profiler report.
- `derived/golden_profile_gantt.txt` — deterministic 100-column timeline with
  Python, semantic, and Torch evidence rows.

Only spans strictly over 50 ms are included as profiling nodes. Direct child
sum and interval union are reported separately; overlap is never double-counted.
Unparented or cross-context intervals are not assigned ownership. Residuals
over 25 ms or 2% are marked `NEEDS_DECOMPOSITION`. Missing roots, incomplete
calls, truncated VizTracer input, ambiguous roots, missing required canonical
stages, and enabled-empty Torch evidence fail closed with explicit reasons.

The normal bundle manifest and downloader surface the three Golden files while
remaining compatible with older bundles that do not contain them.

## Request-log projection

Ready Golden requests emit one bounded block delimited by:

```text
[v2.golden_profiler] BEGIN
...
[v2.golden_profiler] END
```

The block is derived from persisted summary/Gantt files and the artifact
descriptor. It is best-effort and cannot replace a Golden result or error.

## Local evidence

Passed:

```text
python -m py_compile <changed Python files>
git diff --check
python -m unittest tests.test_v2_full_trace_download
82 tests passed
```

The Golden report tests were also run through an isolated direct invocation:
12 tests passed. Standard pytest/unittest collection for report and lifecycle
modules is blocked in this worktree by the pre-existing missing
`comfymodal_runtime.custom_node_root` import / local custom-node-root setup.
The full execution-trace suite ran 166 tests with four existing Torch/Kineto
environment failures; the new Torch config subset passed (13 tests).

No remote, Modal, GPU, deployment, or paid execution was performed, so this
report establishes implementation and offline evidence only—not a physical
Golden performance result.
