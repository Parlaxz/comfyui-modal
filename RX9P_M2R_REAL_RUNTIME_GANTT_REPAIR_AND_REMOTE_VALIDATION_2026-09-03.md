# RX9P-M2R Real Runtime Gantt Repair and Remote Validation — 2026-09-03

## Verdict

```text
M2R_REMOTE_ACCEPTANCE=PASS
REMOTE_REQUESTS_RUN_IN_THIS_LANE=0
DEPLOYS_IN_THIS_LANE=0
```

The single supplied remote request is structurally acceptable: its cohort
verdict is `ACCEPT`, its output classification is `EXACT`, and the rendered
human block satisfies every condition below.  The report was generated from
the real persisted `attempt_0.json`; no second request was made.

## Exact remote evidence

| Field | Value |
|---|---|
| Base M2R commit | `511bebae73c17b2d46bd2cd52a271b7c85a71fb9` |
| Remote request | `golden-p1-0-3ee88e782dcd` |
| Application | `batch-m2r-gantt-repair` |
| Target | `ModalRuntimeEntrypointV2.run_golden_serial_stream` |
| Deployment fingerprint | `56f043a83463539206d96332ea8a062913cf20ed494cf5ba095a13a35e1b6e47` |
| Cohort | `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-03_19-21-50_657c29/` |
| Attempt artifact | `attempt_0.json` (18,050,253 bytes) |
| Cohort result | `ACCEPT / EXACT` |
| Requests / restores | `1 / 1` |
| True cold / strict serial | `true / true` |
| Output SHA | expected = observed = `8a92446890bebaecdc10eb5f207766a4b05af40ca3137108e25bfe88d9c1c44e` |
| Full-trace descriptor | trace `86e4e7016b49466898e3b83d81d83464`, 8,636 entries, not locally materialized |

The provenance sidecar identifies the deployed source as git head
`c4bee234b871ac24592d3a4bb81980bb8cb36053` (the later transport-core cleanup
on top of the M2R base).  The M2R report changes themselves are the committed
changes being assessed here; this lane did not alter source.

## Real serialize → persist → ingest render

The real cohort envelope was adapted into this temporary session directory:

```text
C:\Users\parla\AppData\Local\Temp\opencode\rx9p_m2r_real_render_20260903\
```

The layout exercised the production report path:

- `raw/golden_telemetry.json` — complete Golden telemetry copied from the
  attempt and treated as authoritative;
- `raw/runtime_result_summary.json` — scalar summary without rich telemetry;
- session-root `attempt_0.json` — cohort-envelope fallback source;
- `raw/session_events.jsonl` — persisted `sampling_deep_profile` event;
- `raw/viztracer.json.gz` — root-relative report-parser envelope made from the
  attempt's explicit stage/node bounds (not a fabricated timing measurement);
- `derived/report_data.json` and `derived/golden_profiler_console.txt` — the
  generated machine projection and the persisted human projection.

`generate_full_trace_report()` completed with `status=ready` and
`golden_profile_complete=YES`.  The persisted console was then read and scored
as a human-facing artifact, rather than scoring only JSON fields.

### Full verdict table

`YES`/`NO` in the result column is the required observed value unless noted.
For negative requirements, `NO` is a pass.

| Acceptance condition | Observed result | Verdict | Evidence in persisted human block |
|---|---:|---:|---|
| `OVERALL_GANTT_HAS_CANONICAL_STAGES` | `YES` | PASS | All seven canonical names appear in the overall timeline. |
| `CLIP_LOAD_TRANSPORT_PRESENT` | `YES` | PASS | `CLIP TRANSPORT (nested)` with four producer lanes, source union, H2D union, and reconciliation. |
| `CLIP_FORWARD_TRANSPORT_PRESENT==NO` | `NO` | PASS | No transport section is rendered under CLIP FORWARD. |
| `UNET_LOAD_TRANSPORT_PRESENT` | `YES` | PASS | `UNET TRANSPORT (nested)` is present. |
| `VAE_LOAD_PARENT_PRESENT` | `YES` | PASS | `VAE LOAD — 116.2ms parent`. |
| `VAE_LOAD_TRANSPORT_PRESENT` | `YES` | PASS | `VAE TRANSPORT (nested)` is present. |
| `SAMPLING_PARENT_PRESENT` | `YES` | PASS | Sampling parent wall is `6104.1ms`. |
| `SAMPLING_WINDOW_ALIGNMENT` | `YES` | PASS | `A. STEP/EVAL TIMELINE (aligned sampling_window)`; no `sampling_window alignment unavailable`. |
| `SAMPLING_STEP_ROWS_PRESENT` | `YES` (8) | PASS | Step rows `step 0` through `step 7` are rendered. |
| `SAMPLING_EVAL_ROWS_PRESENT` | `YES` (17) | PASS | Explicit `eval step=...` rows are rendered from persisted intervals. |
| `CLIP_MODULE_ROWS` | `PRODUCER_PROVEN_ABSENT` | PASS | `module detail unavailable` is an intentional producer absence: `clip_module_records_status=producer_absent`, `producer_present=false`, ingest error count `0`; this is not an ingest failure. |
| `VAEDECODE_NODE_ROWS` | `YES` | PASS | `VAEDecode node row: persisted`, with explicit inclusive rows. |
| `E27_PARENT_FALSE_UNRESOLVED==NO` | `NO` | PASS | No CLIP/UNET/VAE E27 parent appears in `UNRESOLVED >50ms`. |
| `SAMPLING_PARENT_FALSE_UNRESOLVED==NO` | `NO` | PASS | `golden_sampling` is not falsely listed as unresolved; its residual is represented by child accounting. |
| `MACHINE_KEY_VALUE_WALL_PRESENT==NO` | `NO` | PASS | No machine `KEY=value` wall projection is present in the human block. |
| `RAW_PER_READ_SPAM_PRESENT==NO` | `NO` | PASS | Only aggregate producer lanes are rendered; no per-read rows are emitted. |
| Overall residual is not 100% | `YES` | PASS | `residual_pct 0.2%` (`25.2ms` of `14463.4ms`). |
| `DUPLICATED_TRANSPORT_PROJECTION==NO` | `NO` | PASS | Exactly one nested transport projection per load stage; none for forward, sampling, or decode. |

The top-level transport mini-Gantt says its aggregate intervals are
unavailable because three distinct load-stage identities are present.  That is
the intended fail-closed aggregate behavior.  The stage-specific projections
are independently identified and available, which is the acceptance contract.

## Human-block excerpt

```text
OVERALL GOLDEN TIMELINE
parent                           |████████████████████████████████████████████████████████████████████████████████████████████████████| 14463.4ms 100.0% [host_monotonic]
golden_clip_load                 |████████████████████████                                                                            | 3399.7ms 23.5% [viztracer]
golden_clip_forward              |                       ████████████                                                                 | 1563.2ms 10.8% [viztracer]
golden_unet_load                 |                                  ████████████                                                  | 2200.6ms 15.2% [viztracer]
golden_sampler_prepare           |                                                 ███                                                | 314.6ms 2.2% [viztracer]
golden_vae_load                  |                                                   ██                                               | 116.2ms 0.8% [viztracer]
golden_sampling                  |                                                    ███████████████████████████████████████████     | 6104.1ms 42.2% [viztracer]
golden_vae_decode                |                                                                                              █████ | 575.5ms 4.0% [viztracer]
ACCOUNTING wall 14463.4ms canonical_stage_union 14438.2ms overlap 0.0ms subthreshold_union 0.0ms true_gaps 25.2ms residual 25.2ms residual_pct 0.2%

VAE LOAD — 116.2ms parent
SAMPLING DETAIL
A. STEP/EVAL TIMELINE (aligned sampling_window)
``` 

## Root causes of the six remote failures and repairs

These are the six integration failures named by the M2R commit message.

| Failure | Root cause | M2R repair | Why the earlier local M2 validation missed it |
|---|---|---|---|
| Overall Gantt had no canonical stages | The overall renderer fell back to the root-child view and did not project canonical spans as the authoritative stage union. | `golden_human_report._OVERALL_CANONICAL_STAGES`, `_canonical_interval`, `_render_canonical_overall`, and `render_overall_timeline` now render the canonical seven-stage union and residual. | The fixture asserted canonical spans in structured data, but did not run the real absolute-boundary/envelope shape through the persisted console. |
| Load transport was absent or duplicated on non-load stages | Transport was selected too broadly by role/position, so a transport record could be attached to forward, sampling, or decode rather than only to its owning load stage. | `golden_human_report._TRANSPORT_LOAD_STAGES`, `_stage_transport`, and `render_stage_artifact` enforce stage+role identity and load-only nested projection. | Local coverage used a small synthetic transport payload and did not score the final real console's three independent remote stage identities. |
| Sampling envelope was not ingested | Rich Golden telemetry can be nested in `golden_telemetry.json` or a cohort `attempt_*.json`; the old parser primarily consumed the scalar summary. Nested sampling events and interval forms were therefore invisible. | `full_trace_report._parse_runtime_result_summary`, `_sampling_profile_payload`, `_sampling_profile_event_records`, `_sampling_interval_bounds`, `_sampling_window_endpoint`, and `_sampling_temporal_rows` preserve and discover the rich envelope. | The local sampling test supplied an already-normalized `session_events.jsonl` payload, bypassing raw telemetry authority and cohort fallback. |
| VAE parent wall disappeared | The stage renderer only showed a child-phase Gantt; a stage with a valid parent wall but no phase children was rendered as unavailable. | `golden_human_report.render_stage_gantt` now keeps the VAE parent wall visible (`VAE LOAD — ... parent`). | The local test checked the structured VAE span/classification, not the human stage artifact when phase children are absent. |
| Sampling/E27 parents were falsely unresolved | Unresolved classification considered VizTracer residuals without promoting independently reconciled sampling and transport evidence into cross-evidence classifications. | `full_trace_report._augment_golden_profile` now classifies cross-evidence parents, emits only explicit residual rows, and preserves the evidence source. | The synthetic residual test checked a narrow JSON classification and did not inspect the real unresolved section for false parent rows. |
| CLIP/VAE node rows were missing | Nested module/node records were not normalized into the report contract; the runtime recorder also lacked the CLIP forward envelope and VAE decode closure record needed for persistence. | `full_trace_report._normalize_clip_module_records`, `_normalize_node_timing_records`, `_build_report_data`; `golden_human_report._clip_module_rows`, `_persisted_node_rows`; `golden_serial.GoldenTelemetryRecorder` and `golden_vae_decode`. | The local positive fixture injected module/node records directly in a convenient summary shape. It did not exercise real producer absence (`NOT RUN`/disabled CLIP instrumentation) versus ingest failure, or the nested cohort envelope. |

## Files and functions changed by M2R

The M2R commit changed only these four tracked paths:

- `comfymodal_runtime/full_trace_report.py`
  - Rich runtime-result/cohort-envelope parsing;
  - sampling payload discovery, interval extraction, alignment, and temporal
    rows;
  - CLIP module and node-timing normalization;
  - cross-evidence classification and unresolved projection;
  - final persisted-console refresh in `generate_full_trace_report`.
- `comfymodal_runtime/golden_human_report.py`
  - canonical overall timeline;
  - stage-specific load transport selection;
  - VAE parent fallback;
  - CLIP module/VAE node rows;
  - aligned sampling detail and subthreshold row rendering.
- `comfymodal_runtime/golden_serial.py`
  - `GoldenTelemetryRecorder.clip_forward_timing` persistence;
  - full-trace VAE decode closure node timing.
- `tests/test_m2r_local_regression.py`
  - six focused serialize/persist/ingest and renderer regression tests.

## Regression verification

The canonical FAST_UNIT command completed successfully:

```text
python tools/test_perf.py --fast -- tests/test_m2r_local_regression.py -m fast_unit
6 passed in 0.80s
```

The six tests cover canonical-stage union/residual, load-only transport and
ambiguous identity, sampling timestamp/alignment/row round-trip, VAE and
cross-evidence classification, nested-envelope CLIP/VAEDecode records, and
persisted-console identity/width/clock contracts.  The real render above adds
the missing evidence shape: complete raw Golden telemetry plus scalar summary
plus cohort-envelope fallback, followed by report generation and a read of the
persisted `derived/golden_profiler_console.txt`.

## Remaining gaps and limits

1. The cohort contains a ready full-trace descriptor, but the referenced remote
   bundle is not locally materialized.  The temporary VizTracer envelope used
   for this report contains the real attempt's explicit stage/node bounds; it
   is not presented as the original 8,636-entry remote bundle.  A future
   bundle-materialization audit could independently compare the full trace,
   but that is not required for this one-request acceptance and was not run.
2. CLIP module detail is honestly absent in this request because the producer
   was disabled (`producer_absent`, not `ingest_failure`).  The acceptance
   contract permits this explicitly; a positive module-row request would need a
   separately instrumented request.
3. The top-level aggregate E27 mini-Gantt remains unavailable when multiple
   stage/role records are present.  The three stage-specific nested projections
   are available and identity-safe; collapsing them into one aggregate would
   reintroduce ambiguity.
4. The unresolved section contains duplicate-looking rows for some canonical
   subthreshold/opaque nodes because canonical and root-derived views remain
   separately auditable.  No E27 or sampling parent is falsely unresolved, and
   no transport projection is duplicated; deduplicating those residual display
   rows is outside this validation.

No source files were modified, no deployment was performed, no request was
run, and no commit was created in this lane.
