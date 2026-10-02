# V2 Batch C3 — Waterfall Scheduling Contract & Compact Telemetry Header

Status: COMPLETE · commit = none · deploys = 0 · Modal runs = 0

## Goal

Replace the ambiguous TOTAL WALL / scheduling presentation with a conclusive
timing contract, enforced by construction:

```
COMMAND -> RESPONSE
  = Scheduling time + Command (without scheduling) -> Response
Scheduling time
  = (Local command -> Modal enqueue) + (Modal scheduling / placement)
```

Everything else (Modal startup, pre-Python snapshot restoration, app restore,
execution, output, response delivery) is NON-SCHEDULING.

## Reference run (v2-benchmark-0-7d15bac54940)

| Quantity | Value |
|---|---|
| command -> response | 35.168 s |
| local command -> Modal enqueue | 19.158 s |
| Modal scheduling / placement | 0.854266 s |
| Scheduling time | 20.012266 s |
| Command (without scheduling) -> Response | 15.155734 s |
| Display check | 15.156 + 20.012 = 35.168 s |

All values are computed from authoritative stamps (command-start → submission
boundary for enqueue; submission → restore-begin for placement; command-start →
caller-return for total). Nothing is hardcoded.

## Production changes — `comfymodal_runtime/v2_waterfall.py`

1. **New report fields** (`WaterfallReport`):
   - `command_to_enqueue_ms` — command start → Modal submission boundary
     (boundary delta; fallback to `local_preparation` + `modal_handle_submission`
     stage sum).
   - `scheduling_time_ms` = enqueue + placement (`modal_scheduling` stage).
   - `non_scheduling_ms` = `total_ms − scheduling_time_ms` (**derived** — the
     three-way invariant cannot drift except display rounding).
   - `host_telemetry` (dict) — compact hardware header data.
   - `total_wall_ms` retained internally for compatibility (placement-only
     formula unchanged); it is no longer shown to users.

2. **Scheduling window is never a stage row**: `local_preparation`,
   `modal_handle_submission`, and `modal_scheduling` are now
   `accounting_role="informational"`, `included_in_total=False` — they do not
   render as numbered rows and never affect accounted/cumulative/%/bar.
   Scheduling is summarized exactly once, in the bottom footer line.

3. **Accounting denominator** for reconciliation, percentages, and bars is now
   `non_scheduling_ms` (fallback `total_wall_ms`), so "Relative wall" figures
   are explicitly non-scheduling.

4. **Final footer (bottom of every render)** — exactly these three lines:

   ```
   COMMAND -> RESPONSE:                       35.168s
   Command (without scheduling) -> Response:  15.156s
   Scheduling time:                           20.012s
   ```

   - `_render_reconciled` (final): always conclusive; never emits
     "awaiting host reconciliation" (missing values render "-" via
     `_fmt_duration`).
   - `_render_partial` (remote diagnostic): same three lines, with
     "awaiting host reconciliation" only where a value is genuinely unknown.
     The normal user-visible completed run always emits the conclusive final
     waterfall (host rebuild via `reconcile_waterfall_local` /
     `attach_waterfall(replace_partial=True)`).

5. **Top of waterfall cleaned**: `TOTAL WALL:` and `COMMAND->RESPONSE:` lines
   removed from the top; COMMAND -> RESPONSE moved to the footer. No
   user-facing "TOTAL WALL" text remains anywhere in the rendered output
   (column header renamed too).

## Compact hardware header

Both renderers now emit a compact header (labels padded to width 10,
" | " separators, ~4 lines):

```
Request:   <request> | Instance: <instance> | Fresh: YES
Platform:  GCP/us-east1 | GPU: RTX PRO 6000 Blackwell | VRAM 97,250 MiB | CUDA 13.0 | CC 12.0
CPU:       AMD Family 191 Model 2 | visible=28 | requested=12 | Torch=12/14 | native=53
Telemetry: CPU peak=7.13 cores | >16 cores=0ms | RSS 9.66 -> 23.02 -> 13.15 GiB | maxRSS=35.74 GiB
```

Sources (all from the run payload, key-grounded against the real
v2-benchmark-0-7d15bac54940 artifact):
- GPU: `gpu_allocation.{gpu_actual_name (trimmed), gpu_vram_total_mib (thousands
  sep), cuda_version, gpu_compute_capability}`
- Platform: identity `cloud` (CLOUD_PROVIDER_ prefix stripped) / `region`
- CPU: `host_hardware_fingerprint` event metadata (vendor→AMD/Intel, family,
  model, `cpu_count_proc` visible) + `runtime_shape.observed`
  (`cpu_request`, torch intra/inter-op, `native_thread_count`)
- Pressure: `trace.activation_diagnosis` (`cpu_peak_cores`, `cpu_above_16_ms`)
- Memory: `host_memory` trace events by stage (restore/peak-execution/result
  RSS) + `host_resource_snapshot` `ru_maxrss` fallback (KB→MiB)

Unavailable telemetry is omitted segment-by-segment (whole line omitted when
empty) — never fabricated zeros. A **measured** 0 (e.g. `>16 cores=0ms`) is
real data and renders; only missing measurements are omitted.

## Table cleanup

- Right-hand reference column renamed: `Relative wall (TOTAL WALL)` →
  `Relative wall (non-scheduling)`.
- Boxed `SCHEDULING` footer row removed (scheduling is summarized once in the
  bottom footer line); `RECONCILIATION` / `STATUS` / `TARGET 10MS` rows kept.
- No "overlaps parent" verbosity added; all stage/detail rows preserved.

## Tests

New file `tests/test_v2_waterfall_scheduling_contract.py` — A–J mandated
regressions plus two supplements:

| # | Test | Asserts |
|---|---|---|
| A | reference-run arithmetic exact | enqueue 19.158 + placement 0.854266 → scheduling 20.012266; non-scheduling 15.155734; footer 35.168s / 15.156s / 20.012s |
| B | startup +5 s | changes non-scheduling only; scheduling unchanged |
| C | enqueue delay +3 s | changes scheduling only; post-restore stages unchanged |
| D | placement +2 s | changes scheduling only; non-scheduling unchanged |
| E | footer reconcile | three display values reconcile within rounding tolerance (≤0.002 s) |
| F | exact outer wall | total_ms == authoritative command-start→caller-return boundary, invariant under scheduling variation |
| G | full header | all 4 lines / all segments (GPU trim, VRAM sep, CUDA/CC, CPU, Torch, native, peak, RSS chain, maxRSS); measured `>16 cores=0ms` renders |
| H | missing telemetry | no fabricated values; segments/lines omitted; GPU-only partial variant |
| I | partial → conclusive | partial render pending tokens; host rebuild emits conclusive final footer, no "awaiting host reconciliation" |
| J | no TOTAL WALL | neither reconciled nor partial output contains "TOTAL WALL" |

Migrated to the new contract (no tests deleted, intent preserved):
`test_v2_waterfall_contract.py` (golden render regenerated byte-exact),
`test_v2_waterfall.py` (33-key dict shape, pending-footer tokens, informational
scheduling window), `test_waterfall_scheduling_denominator.py`,
`test_waterfall_reconciliation.py`, `test_v2_final_observability.py`.

Fixture module extended (existing API byte-compatible): `enqueue_ms` chain
parameter, `build_reference_run_result(...)`, `attach_host_telemetry(...)`,
`chain_total_ms(enqueue_ms=...)`.

## Verification

- `python -m pytest` over the 13 focused waterfall/transport/Batch-A modules:
  **393 passed in 11.30s** (scheduling_contract 12, waterfall_contract 36,
  v2_waterfall 31, scheduling_denominator 6, reconciliation 23,
  final_observability 29, attach_central, restoration_wiring, host_breakdown,
  host_submission, local_submission_timing, transport_boundaries,
  batch_a_acceptance).
- `python run_tests.py <13 modules>`: 256 unittest-collected tests OK
  (pytest-style module functions are collected by pytest, not the name-based
  unittest loader).
- `py_compile` clean on all changed files.
- Reference-arithmetic smoke check: scheduling_time_ms == 20012.266,
  non_scheduling_ms == 15155.734, footer 35.168s / 15.156s / 20.012s.

## Scope guard

Not modified: `canonical_execution.py`, `contracts.py`, `modal_app.py`,
Batch-C acceptance files. `tools/benchmark_v2_direct.py` unchanged (host-side
reconciliation already upgrades partial → final). No deploy, no Modal runs,
no commit.

## Final response fields

- report path = `V2_BATCH_C3_WATERFALL_CONTRACT_REPORT.md`
- changed files = `comfymodal_runtime/v2_waterfall.py`,
  `tests/v2_waterfall_reconciliation_fixtures.py`,
  `tests/test_v2_waterfall_scheduling_contract.py` (new),
  `tests/test_v2_waterfall_contract.py`, `tests/test_v2_waterfall.py`,
  `tests/test_waterfall_scheduling_denominator.py`,
  `tests/test_waterfall_reconciliation.py`, `tests/test_v2_final_observability.py`
- commit = none · deploy count = 0 · Modal runs = 0
- command->response moved to footer = yes
- scheduling definition corrected = yes (enqueue + placement)
- startup excluded from scheduling = yes
- three-way arithmetic enforced = yes (non-scheduling derived from the other two)
- TOTAL WALL removed from user-facing final output = yes
- compact hardware header = yes (4 lines, telemetry-omission rules)
- reference run expected scheduling = 20.012 s
- reference run expected no-scheduling = 15.156 s
- tests = 393 passed (focused waterfall/transport/Batch-A), 256 unittest-collected OK
- ready for integration = yes
