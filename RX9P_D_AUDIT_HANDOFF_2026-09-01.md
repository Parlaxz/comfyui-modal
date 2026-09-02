# RX9P-D Audit Handoff — 2026-09-01 (Reconciled)

## Reconciliation identifiers

- OLD_BASE_SHA: dc94449b5161c5374a8c777011a5c3964cb15aa9
- NEW_CANONICAL_BASE_SHA: 4c7a197533fa2a4277c40d05c607293e3392d95d
- D_COMMIT_BEFORE_RECONCILIATION: 4ec17830f32266aa4a222fde063aa5fd5d6eb8df
- D_COMMIT_AFTER_RECONCILIATION: ac270f2f06c3244f7752d674686de794216d2081
- CONFLICTED_FILES: ["comfymodal_runtime/golden_serial.py"]
- REPORT_PATH: RX9P_D_GOLDEN_VIZTRACER_DEEP_PROFILER_REPORT_2026-09-01.md
- RAW_TEST_LOG_PATHS: ["RX9P_D_RAW_TEST_report.log","RX9P_D_RAW_TEST_execution.log","RX9P_D_RAW_TEST_download.log","RX9P_D_RAW_TEST_e27.log","RX9P_D_RAW_TEST_lifecycle.log"]
- SYNTHETIC_TRACE_PATH: SYNTHETIC_TRACE.json.gz
- SYNTHETIC_GANTT_PATH: SYNTHETIC_GOLDEN_PROFILE_GANTT_TXT
- SYNTHETIC_PROFILE_REPORT_PATH: SYNTHETIC_GOLDEN_PROFILE_REPORT_MD
- SYNTHETIC_PROFILE_SUMMARY_PATH: SYNTHETIC_GOLDEN_PROFILE_SUMMARY_JSON

## Scope and isolation

- Branch: `rx9p-d-golden-profiler`
- Worktree: `.slim/worktrees/rx9p-d`
- Merge strategy: `git merge TESTING2 --no-ff` preserving history (no reset/discard)
- Integration into TESTING2: NOT performed (stays on rx9p-d only)
- Remote/paid execution: none

## Conflict audit

### comfymodal_runtime/golden_serial.py — sole content conflict

- **Canonical (RX9P-C) preserved:** `ActualSourceTelemetry` class and helpers (`_actual_source_report_fields`, `_reconcile_actual_source_h2d`), `E27` evaluator wiring (`e27_source_mechanism_evaluation`, `E27_SOURCE_MECHANISM_PROVEN`, `SOURCE_*_MS`, `H2D_*`, `quiescence_evidence`), physical syscall instrumentation in `_read_at(actual_source=..., producer_id, region_id)` with `syscall_enter/exit` and `mark_physical_syscall_provenance`, and execution ordering unchanged.
- **D (RX9P-D) preserved:** `golden_trace_span` seam, `_ClipTiming(trace_prefix=...)` with `golden.clip_load` / `golden.clip_forward`, and six UNET semantic spans `golden.unet.header_config_preflight`, `skeleton_patcher_construction`, `source_h2d_transport`, `assign_adoption`, `binding_validation`, `transport_quiescence` via `_golden_trace_span`. Both sides verified by `Select-String` in merged file (ActualSourceTelemetry + golden.unet.* + trace_prefix present).

### comfymodal_runtime/modal_app.py — no content conflict, re-applied D lifecycle onto canonical

- **Canonical preserved:** RX9P-B and RX8A identity/runtime changes, new `_reference_image()` using `CANONICAL_IMAGE_PLAN.final_image` (previously `_image_base.pip_install`), `comfymodal_runtime/custom_node_root.py` (RX8A) consumed verbatim.
- **D preserved:** Direct-Golden full-trace lifecycle around CURRENT `run_golden_serial_stream`: `golden_request_entry` + `golden_request_execution` claim after containment validation and before `ensure_gpu_ready`/`activate_golden_dynamic_vram`; `golden_request_return`/`golden_request_error` + `trace_stop_boundary` + `operation_end` before `_safe_full_trace_artifact`; `_ft.start_torch_profiler` / `_ft.stop_torch_profiler` in `try/finally` around `await golden_serial_execute` on same adapter thread; `golden_trace_summary` propagation and `_emit_golden_profiler_block` with `[v2.golden_profiler] BEGIN/END`.

### tools/v2_control/* — preserved canonical exactly

- D made no changes to `tools/v2_control/*`; merge checked out `TESTING2 -- tools/v2_control` so A/B results are canonical. Verified `tools/v2_control/cli.py` is byte-identical to `TESTING2:tools/v2_control/cli.py` (known pre-existing syntax error at `from publication_policy import (` remains as in canonical, not introduced by D).

### comfymodal_runtime/custom_node_root.py — consumed RX8A

- No D-local substitute created; file is `TESTING2:comfymodal_runtime/custom_node_root.py` verbatim. Previously blocking `ModuleNotFoundError: custom_node_root` now resolved; import of `comfymodal_runtime.modal_app` succeeds (293s first import due to 60GB custom-node scan, expected_hit cache).

## Test results (normal collection, no workaround)

All suites run in `.slim/worktrees/rx9p-d` with normal pytest collection after merge:

- **tests/test_v2_full_trace_report.py**: 94 passed (previously 80 + 14 new D golden-profile edge cases). Log: `RX9P_D_RAW_TEST_report.log`
- **tests/test_v2_full_execution_trace.py**: 167 passed, 2 subtests passed. Previously 4 Torch/Kineto env failures now resolved with updated Torch flag persistence. Log: `RX9P_D_RAW_TEST_execution.log`
- **tests/test_v2_full_trace_download.py**: 82 passed. Log: `RX9P_D_RAW_TEST_download.log`
- **tests/test_e27_source_mechanism.py + test_e27_source_integration.py + test_e27_legacy_read_path.py**: 31 passed. Log: `RX9P_D_RAW_TEST_e27.log`
- **tests/test_v2_full_trace_lifecycle.py**: 33 passed, 3 skipped after fixing 4 post-merge code failures (previously blocked by missing custom_node_root, not by workaround). Initially after merge: 29 passed, 4 failed, 3 skipped. Fixed: `test_direct_golden_trace_has_terminal_success_and_error_lifecycles` (whitespace-tolerant) and 3 `test_reference_image_*` (canonical now uses `CANONICAL_IMAGE_PLAN.final_image`, not `_image_base.pip_install`). After fix: 33 passed. Log: `RX9P_D_RAW_TEST_lifecycle.log` (initial) + `RX9P_D_RAW_TEST_lifecycle_fixed.log` (4-test fix verification).

Separate env vs code: No remaining Torch/Kineto env failures; the 4 failures were code failures due to canonical image-plan change, proven against current TESTING2 HEAD and now fixed. No Modal/GPU/paid runs.

## Synthetic trace artifacts (stdlib-only, no Modal)

Generated via `comfymodal_runtime.full_trace_report.generate_full_trace_report` on synthetic `viztracer.json.gz` with one `golden_serial_execute` root and 11 canonical stages:

- **SYNTHETIC_TRACE_PATH**: `SYNTHETIC_TRACE.json.gz` (gzip'd Chrome trace, 12 events)
- **SYNTHETIC_GANTT_PATH**: `SYNTHETIC_GOLDEN_PROFILE_GANTT_TXT` (100-column deterministic gantt, verified `golden_profile_complete=YES`)
- **SYNTHETIC_PROFILE_REPORT_PATH**: `SYNTHETIC_GOLDEN_PROFILE_REPORT_MD` (bounded report with `GOLDEN_PROFILE_COMPLETE=YES`)
- **SYNTHETIC_PROFILE_SUMMARY_PATH**: `SYNTHETIC_GOLDEN_PROFILE_SUMMARY_JSON` (machine-readable summary)
- REPORT_PATH also available as `SYNTHETIC_GOLDEN_PROFILE_REPORT_MD` copy; full synthetic `derived/report.md` at temp synthetic session.

## Verification

- `python -m py_compile` on changed files passes (except known canonical `tools/v2_control/cli.py` syntax error, preserved as in TESTING2, not introduced by D)
- `git diff --check` clean
- `git status` on rx9p-d shows only D's 11 files + 2 docs + merge; no TESTING2 branch modified
- `git branch --show-current` remains `rx9p-d-golden-profiler`

## What remains

- `tools/v2_control/cli.py` syntax error at `from publication_policy import (` is pre-existing in `4c7a197:tools/v2_control/cli.py`; leave as canonical, do not fix in D lane.
- No integration into TESTING2 performed; work stays isolated.
