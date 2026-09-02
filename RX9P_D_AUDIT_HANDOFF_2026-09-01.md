# RX9P-D Audit Handoff — 2026-09-01

## Scope and isolation

- Branch: `rx9p-d-golden-profiler`
- Base: `TESTING2`
- Worktree: `.slim/worktrees/rx9p-d`
- Integration: not performed (`CAN_INTEGRATE=NO`)
- Remote/paid execution: none

## Primary implementation paths

| Area | Path |
|---|---|
| Full-trace session and Torch lifecycle | `comfymodal_runtime/full_execution_trace.py` |
| Direct Golden adapter and artifact finalization | `comfymodal_runtime/modal_app.py` |
| CLIP/UNET semantic spans | `comfymodal_runtime/golden_serial.py` |
| Recursive offline report/Gantt | `comfymodal_runtime/full_trace_report.py` |
| Bundle extraction/surfacing | `tools/download_v2_full_trace.py` |
| Lifecycle tests | `tests/test_v2_full_execution_trace.py`, `tests/test_v2_full_trace_lifecycle.py` |
| Report tests | `tests/test_v2_full_trace_report.py` |
| Download tests | `tests/test_v2_full_trace_download.py` |

## Audit checks

1. Verify `golden_request_entry` and the single
   `golden_request_execution` operation occur only after request-id
   containment validation.
2. Verify `golden_request_return` / `golden_request_error`, operation closure,
   and `trace_stop_boundary` precede `_safe_full_trace_artifact`.
3. Verify Torch start and stop surround only the awaited direct Golden call and
   remain on the same adapter thread.
4. Verify `golden_profile_summary.json`, `golden_profile_report.md`, and
   `golden_profile_gantt.txt` are included in the normal manifest/bundle and
   are surfaced by the downloader.
5. Verify the profiler block contains both delimiters and does not emit when
   full trace is disabled.
6. Verify raw evidence remains authoritative: one root, >50 ms threshold,
   union accounting, residual flags, explicit completeness reasons, and no
   inferred cross-thread ownership.

## Validation and limitation

`py_compile`, `git diff --check`, the 82-test full-trace downloader suite, 12
isolated Golden report tests, and 13 focused execution-trace tests passed.
The full execution-trace suite had four existing Torch/Kineto environment
failures. Standard report/lifecycle collection is also blocked by the existing
missing `comfymodal_runtime.custom_node_root` import and local custom-node-root
setup. This handoff therefore does not claim a Modal/GPU run, deployment
validity, or measured performance improvement.
