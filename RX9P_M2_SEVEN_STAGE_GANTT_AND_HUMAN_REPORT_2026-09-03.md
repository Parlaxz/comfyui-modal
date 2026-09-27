# RX9P-M2 Seven-Stage Gantt and Human Report — 2026-09-03

## Scope and execution boundary

This is a local validation report. No Modal deployment, remote request, GPU
run, or HEAVY_LOCAL test was performed in this lane.

The implementation under review is:

- `comfymodal_runtime/full_trace_report.py`
- `comfymodal_runtime/golden_human_report.py`
- `comfymodal_runtime/golden_serial.py`
- `comfymodal_runtime/modal_app.py`
- `comfymodal_runtime/sampling_deep_profile.py`

## Required stage contract

The human renderer has explicit entries for all seven required Golden stages,
in order:

1. `golden_clip_load`
2. `golden_clip_forward`
3. `golden_unet_load`
4. `golden_sampler_prepare`
5. `golden_vae_load`
6. `golden_sampling`
7. `golden_vae_decode`

`generate_full_trace_report()` writes one overall console, one combined stage
Gantt, one per-stage file under `derived/gantts/`, a sampling breakdown, an
E27 transport breakdown, and the machine-facing `report_data.json`. Modal
projects the persisted `golden_profiler_console.txt` rather than rebuilding a
second human report.

## Local renderer validation

The existing offline fixture was copied to a temporary directory and passed
through `generate_full_trace_report()`. The run generated 33 derived files,
including:

- `golden_profiler_console.txt`
- `golden_stage_gantts.txt`
- `golden_profile_gantt.txt`
- `golden_sampling_breakdown.txt`
- `e27_transport_breakdown.txt`
- all seven files in `derived/gantts/`
- `golden_profile_summary.json`
- `golden_profile_report.md`
- `report_data.json`
- `manifest.json`

The fixture intentionally lacks a real `golden_serial_execute` root and real
sampling/E27 evidence. The renderer therefore emitted explicit
`measurement unavailable` / `unavailable` values and marked the Golden profile
incomplete; it did not fabricate timings, occupancy, or transport intervals.

## Existing run envelope

The retained local evidence envelope at
`artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_15-28-03_80e7ee/`
records a ready remote full-trace descriptor with:

- `report_status=ok`
- `viztracer_status=ok`
- `trace_truncated=false`
- `trace_entry_count=8629`
- bundle SHA-256
  `931aa634b34e740cd38b08aa8f84766a02f624365e42e89f943c76a80294bf46`

Only the descriptor is present locally; the referenced remote bundle was not
downloaded. Consequently, real seven-stage timing, sampling temporal rows,
QD occupancy, and physical E27 source/H2D evidence remain unverified in this
lane.

## Verification

- Python compilation: **PASS**.
- `git diff --check`: **PASS**.
- Golden profile and cohort-envelope tests: **18 passed**.
- Sampling and E27 projection tests: **9 passed**.
- The two isolated sampling tests that require ComfyUI imports fail in this
  environment with missing `comfy` / `comfy_api` modules; this is an import
  prerequisite failure, not a renderer assertion failure.
- The broader focused invocation collected 270 tests but hit the configured
  FAST budget at 15.084 seconds after 162 calls (`exit 124`). The timeout stack
  showed fixture hashing in `_sha256_file` during
  `test_no_timestamps_in_output`; it was not rerun with a larger budget.

## Acceptance state

```text
LOCAL_RENDERER_IMPLEMENTED=YES
LOCAL_RENDERER_FIXTURE_VALIDATION=PASS
SEVEN_STAGE_REAL_RUN_VALIDATION=UNPROVEN
SAMPLING_TEMPORAL_ALIGNMENT=UNPROVEN
E27_PHYSICAL_SOURCE_H2D=UNPROVEN
MODAL_PERSISTED_CONSOLE_IDENTITY=SOURCE_IMPLEMENTED_NOT_REMOTELY_RECHECKED
GOLDEN_END_TO_END_ACCEPTANCE=PENDING_EXISTING_BUNDLE_MATERIALIZATION_OR_FUTURE_AUTHORIZED_RUN
```
