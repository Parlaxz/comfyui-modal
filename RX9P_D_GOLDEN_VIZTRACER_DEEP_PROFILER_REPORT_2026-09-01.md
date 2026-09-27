# RX9P-D — Golden VizTracer Deep Profiler (Reconciled 2026-09-01)

## Status

Implemented on the isolated `rx9p-d-golden-profiler` branch from `TESTING2`.
Reconciled onto current canonical `TESTING2` without integration, deployment, or Modal/GPU/paid execution.

- Reconciliation commit: `53b4916713c62b78c02c728d56268baec0728d0a` (Merge canonical TESTING2 — RX9P-B identity — into rx9p-d)
- Final D branch code/audit-fix HEAD before this report-only commit: `af177b0fc113c4f564fac8964884bb96b6ea3901`
- Canonical base reconciled: `9024bbc58de5ea3017d41e8c78dd77329b6acdea` (TESTING2 HEAD after RX8A, RX9P-A/B/C)

## Runtime wiring

- The direct `run_golden_serial_stream` adapter claims the existing full-trace session only after request-id containment validation and before GPU readiness or Golden model work.
- The Golden operation is opened once and closed once on both success and error paths. Final milestones and artifact finalization occur before the terminal event; finalization itself is outside the VizTracer interval.
- VizTracer and optional Torch profiler start/stop boundaries remain on the adapter's execution thread. Full-trace OFF remains inert.
- CLIP timing mirrors the existing stage diagnostics into full-trace spans. UNET adds only the requested semantic seams: header/preflight, patcher construction, source/H2D transport, assignment/adoption, validation, and transport quiescence.

## Derived Golden artifacts

Offline report generation reuses normalized raw evidence and writes:

- `derived/golden_profile_summary.json` — machine-readable status, one selected `golden_serial_execute` root, recursive spans, canonical stages, residuals, and Torch CPU/CUDA summaries.
- `derived/golden_profile_report.md` — bounded human-readable profiler report.
- `derived/golden_profile_gantt.txt` — deterministic 100-column timeline with Python, semantic, and Torch evidence rows.

Only spans strictly over 50 ms are included as profiling nodes. Direct child sum and interval union are reported separately; overlap is never double-counted. Unparented or cross-context intervals are not assigned ownership. Residuals over 25 ms or 2% are marked `NEEDS_DECOMPOSITION`. Missing roots, incomplete calls, truncated VizTracer input, ambiguous roots, missing required canonical stages, and enabled-empty Torch evidence fail closed with explicit reasons.

The normal bundle manifest and downloader surface the three Golden files while remaining compatible with older bundles that do not contain them.

## Request-log projection

Ready Golden requests emit one bounded block delimited by:

```text
[v2.golden_profiler] BEGIN
...
[v2.golden_profiler] END
```

The block is derived from persisted summary/Gantt files and the artifact descriptor. It is best-effort and cannot replace a Golden result or error.

## Local evidence — reconciled

Reconciliation consumed canonical `comfymodal_runtime/custom_node_root.py` (RX8A) verbatim; no D-local substitute. `custom_node_root.py` is now supplied by canonical RX8A and `comfymodal_runtime.modal_app` imports successfully (first import ~293s due to 60GB custom-node scan, `expected_hit` cache).

Normal pytest collection is no longer blocked. Persisted successful suites:

- `RX9P_D_RAW_TEST_report.log` — 94 passed
- `RX9P_D_RAW_TEST_execution.log` — 167 passed, 2 subtests
- `RX9P_D_RAW_TEST_download.log` — 82 passed
- `RX9P_D_RAW_TEST_e27.log` — 31 passed
- `RX9P_D_RAW_TEST_lifecycle.log` / `RX9P_D_RAW_TEST_lifecycle_fixed.log` — final state 33 passed, 3 skipped

The previous four Torch/Kineto failures reported pre-reconciliation are no longer present after reconciliation; `test_v2_full_execution_trace` now passes 167/167.

`python -m py_compile` on changed D files passes; `git diff --check` clean; `tools/v2_control/cli.py` compiles cleanly on canonical TESTING2 and the reconciled D branch. The earlier apparent null-byte/BadGzipFile/syntax failure was an audit-harness artifact caused by PowerShell UTF-16LE output redirection, not a repository syntax defect.

## Independent reconciled-branch audit (RX9P-E)

RX9P-E independently audited the reconciled branch and found:

```text
CONTROL_PLANE_RECONCILED=YES
EXPERIMENT_IDENTITY_RECONCILED=YES
E27_INSTRUMENTATION_RECONCILED=YES
PROFILER_RECONCILED=YES
D_RAW_SYNTHETIC_PROOF_VALID=YES
UNEXPECTED_D_DIFFS=0
CLI_SYNTAX_CLEAN=YES
```

RX9P-E correction also recorded:

`RX9P-C PERFORMANCE_BEHAVIOR_CHANGED=YES` — because RX9P-C introduced new intentional fail-closed telemetry/reconciliation/quiescence requirements. No C code was changed in this D lane.

## Synthetic evidence — preserved

Stdlib-only synthetic proof remains valid and is referenced by path:

- `SYNTHETIC_TRACE.json.gz` — gzip'd Chrome trace (12 events, 1 `golden_serial_execute` root + 11 canonical stages)
- `SYNTHETIC_GOLDEN_PROFILE_GANTT_TXT` — 100-column deterministic gantt
- `SYNTHETIC_GOLDEN_PROFILE_REPORT_MD` — bounded report
- `SYNTHETIC_GOLDEN_PROFILE_SUMMARY_JSON` — machine-readable summary with `golden_profile_complete=YES`

No regeneration was necessary; paths are factual as persisted.

## What remains

No integration into `TESTING2` performed; work stays isolated on `rx9p-d-golden-profiler`. No Modal/GPU/paid execution. This report establishes implementation and reconciled offline evidence only — not a physical Golden performance result.
