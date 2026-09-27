# V2 Batch A — Position Per-Node Timing Rows on the Real Timeline

Date: 2026-08-14
Scope: G3 minimal observability fix from `V2_GENERIC_FIRST_NODE_PRESAMPLER_DELAY_RESEARCH.md` §12/§13 (item 3). No deployment, no Modal runs, no commits.
Files changed (write-ownership respected):
- `comfymodal_runtime/runtime_executor.py`
- `comfymodal_runtime/v2_waterfall.py`
- `tests/test_v2_per_node_timeline.py` (new)

---

## 1. Old record schema

`state["_pre_sampler_node_timings"]` entries (previously `runtime_executor.py:2624-2628`), carried into
`pre_sampler_structured_report.per_node_timings` verbatim:

```json
{
  "node_id": "935:929",
  "class_type": "ImpactSwitch",
  "duration_ms": 624.564
}
```

No timeline position — the waterfall rendered `Node: <class>` detail rows with `start_ns=None, end_ns=None`, so
an overlapping ~600 ms ImpactSwitch/PENDING interval could not be distinguished from unique node cost.

## 2. New schema

```json
{
  "node_id": "935:929",
  "class_type": "ImpactSwitch",
  "duration_ms": 624.564,
  "start_perf_ns": 2778287500000000,
  "end_perf_ns": 2778288124564000,
  "pass_outcome": "PENDING"
}
```

- `start_perf_ns` / `end_perf_ns` — `time.perf_counter_ns()` integers bounding the same window `duration_ms` measures.
  When the sampling-start cutoff truncates a node mid-window, `end_perf_ns` **is the cutoff timestamp** (see §3/§5),
  so `end − start` reconciles with `duration_ms` exactly (≤ rounding, 0.002 ms in tests).
- `pass_outcome` — `"COMPLETE" | "PENDING" | "ERROR" | "UNKNOWN"`, derived only from existing execution
  return/state (§4). Always present on new records.
- Old keys unchanged (`node_id`, `class_type`, `duration_ms`), additive only.

## 3. Timer boundary

Unchanged timer placement, now fully captured:

- **Start:** `runtime_executor.py:2644` — `_t0 = time.perf_counter_ns()` inside `_patched_exec_node`, immediately before delegating to ComfyUI's per-node `execution.execute`.
- **End:** `runtime_executor.py:2678` — `_t_end = time.perf_counter_ns()` in the `finally` around `await _orig_exec_node(...)`, at the same boundary the old `_ns_ms(_t0)` read.
- **Clip:** the existing hard cutoff at authoritative `sampling_start` (`_sampling_cutoff_perf_ns`, perf-counter domain) is applied via the new pure helper `_clip_node_interval(start, end, cutoff)`:
  - no cutoff → `(round((end−start)/1e6, 3), end)`
  - cutoff mid-window → duration clipped, effective end = cutoff (sampler row ends exactly at sampling_start)
  - cutoff before start (post-sampler node) → `(0.0, start)`; the existing `_elapsed > 0` guard still skips the record
  - cutoff after end → never inflates (fixes a latent edge in the old block; unreachable in practice)
- `_clipped` flag: `end_perf < t_end` (exact truncation test; the old 1 ms hysteresis is gone — behavior-equivalent for all reachable cases).
- No deep timing added: no function internals, no GIL, no per-cache/per-input/per-hook timing, no thread profiler. Two perf-counter reads + a dict append per node.

## 4. Pass/outcome derivation

`_derive_pass_outcome(result, *, raised, cancelled)` — **never guessed**; uses the existing return of `_orig_exec_node`.

ComfyUI `execution.execute` returns `(ExecutionResult, error_details, exception)`; `ExecutionResult` is an IntEnum:
`SUCCESS = 0`, `FAILURE = 1`, `PENDING = 2`. Mapping (robust to enum or raw int, plus `.name` fallback):

| Source signal | Outcome |
|---|---|
| return tuple first element == 0 (SUCCESS) | `COMPLETE` |
| return tuple first element == 2 (PENDING — lazy discovery pass, pending async tasks, subgraph expansion) | `PENDING` |
| return tuple first element == 1 (FAILURE) | `ERROR` |
| wrapper raised (non-cancellation exception escaped `execute`) | `ERROR` |
| `asyncio.CancelledError` (state unknowable) | `UNKNOWN` |
| non-tuple / empty / unrecognized status | `UNKNOWN` |

Accuracy > completeness: `PENDING` is recorded only when ComfyUI's own return value says the pass was pending —
the ImpactSwitch pass-1 vs pass-2 lazy double-execution becomes directly visible.

## 5. Clock-domain handling

- Node timestamps are `time.perf_counter_ns()` (same clock as `_sampling_cutoff_perf_ns` and `_ns_ms`).
- Artifacts are produced on Linux (Modal containers), where CPython implements both `perf_counter_ns()` and
  `monotonic_ns()` on `CLOCK_MONOTONIC` — same clock, same epoch → values are directly comparable with the
  mono fields already carried by `pre_sampler_stages` (`first_sampler_node_monotonic_ns`), `sampling_start`
  events, and `active_read_records` (`start_monotonic_ns`).
- Following the existing clock normalization, the waterfall places `start_perf_ns`/`end_perf_ns` into the same
  `"monotonic:remote"` scope (`clock_scope="monotonic:remote"`, `process="remote"` semantics) used for those
  other remote same-process mono intervals. No wall ns / mono ns / perf ns mixing: a record whose `end < start`
  (cross-domain or corrupt) is simply not positioned and falls back to duration-only.
- Node rows are non-accounting overlap detail, so even a hypothetical platform-level clock divergence could
  only misposition a diagnostic row — it can never affect reconciliation totals.
- Documented in a module comment in `v2_waterfall.py` near the node-timing loop.

## 6. Waterfall rendering

`_detail_stages` per_node_timings loop (`v2_waterfall.py:1441-1479`):

- New records → detail `WaterfallStage` with real `start_ns`/`end_ns`, `status=MEASURED`,
  `clock_scope="monotonic:remote"`, `source_fields=("pass_outcome:<value>",)`.
- Rows remain `included_in_total=False`, `accounting_role="child"`, `group="detail"`,
  `parent_key="pre_sampler_execution"` — NON-ACCOUNTING overlap detail, exactly as before. They may visually
  overlap checkpoint read / get_model / bind / H2D / other nodes; that is the point.
- Label stays exactly `Node: <class_type>` (outcome rides in `source_fields`) so the existing >= 25 ms +
  strategic-class console filter and duplicative-node curation are untouched. Sub-ms nodes are still not dumped
  to console; structured artifacts retain all records.
- No changes to top-level stages, `_intervals_overlap` usage, accounting, or rendering code.

## 7. Accounting proof

- Reconciliation sums only `accounting_role == "top_level"` stages; detail rows are structurally excluded
  (`included_in_total=False`) — this was already true and is unchanged.
- Detail rows are not overlap-checked, so positioned node rows can never mark a top-level stage INVALID or add
  warnings.
- Proven by test `test_node_rows_do_not_change_reconciliation`: reports built with and without
  `per_node_timings` have byte-identical top-level stage durations, `accounted_ms`, and `reconciliation_ms`.
- `test_positioned_node_row_may_overlap_top_level_stage`: an intentionally overlapping node row adds no
  warnings and flips no stage status.

## 8. Backward compatibility

- Old records (no `start_perf_ns`/`end_perf_ns`) → `positioned=False` → identical to today: `start_ns=None`,
  `end_ns=None`, `status=DERIVED`, `clock_scope="metadata"`, duration-only detail row.
- `duration_ms` and all prior keys unchanged; the ≥ 25 ms/strategic filter applies to old and new alike.
- `_attach_structured_report` / `attach_pre_sampler_critical_path` pass records through by value — no schema
  gate anywhere. Historical reports parse and render unchanged (covered by the existing 67-test waterfall
  contract suite, still green).

## 9. Tests

New `tests/test_v2_per_node_timeline.py` (12 tests, all passing) — no Modal runs, no deploy:

| Test | Requirement covered |
|---|---|
| `test_new_record_has_start_end_and_outcome` | new record has start/end/outcome |
| `test_duration_reconciles_with_end_minus_start` | duration ≈ end−start (≤ 0.002 ms) |
| `test_pending_outcome_marked` | PENDING from `(2, None, None)` return |
| `test_derive_pass_outcome` | COMPLETE/PENDING/ERROR/UNKNOWN table incl. enum-like, bool, non-tuple, cancelled |
| `test_error_and_cancelled_and_non_tuple_outcomes` | ERROR (raise), UNKNOWN (cancel), UNKNOWN (non-tuple) |
| `test_clip_node_interval_pure` | cutoff before/mid/after start/end incl. no-inflation edge |
| `test_cutoff_clips_sampler_node_record_end` | sampler node record ends exactly at sampling-start cutoff |
| `test_sampler_cutoff_row_end_aligns_with_sampling_start` | waterfall row end == sampling stage start |
| `test_structured_report_carries_new_fields` | structured report propagation |
| `test_waterfall_node_rows_positioned_and_non_accounting` | positioned rows non-accounting; old-style row fallback |
| `test_node_rows_do_not_change_reconciliation` | no cumulative double-count; reconciliation unchanged |
| `test_positioned_node_row_may_overlap_top_level_stage` | overlap allowed |

Regression suites re-run green (all from repo root):
- `tests/test_v2_per_node_timeline.py` — 12 passed
- `tests/test_v2_waterfall.py tests/test_v2_waterfall_contract.py` — 67 passed
- `tests/test_pre_sampler_critical_path_integration.py` — 82 passed (executor harness incl. cutoff semantics)
- `tests/test_v2_final_observability.py tests/test_waterfall_reconciliation.py` — 52 passed
- `tests/test_v2_pre_sampler_attribution.py` — 37 passed

## 10. Overhead estimate

Per executed pre-sampler node: 2 `time.perf_counter_ns()` reads (one already existed) + a small dict append
with 3 extra scalar fields + one outcome derivation (tuple indexing / int compare). ≤ ~1 µs per node,
< 0.001% of a 15 s run. No new timers, no threads, no hooks, no per-input/cache instrumentation.

---

## Completion output

```
report path      = V2_BATCH_A_PER_NODE_TIMELINE_REPORT.md
changed files    = comfymodal_runtime/runtime_executor.py,
                   comfymodal_runtime/v2_waterfall.py,
                   tests/test_v2_per_node_timeline.py (new)
commit           = none
deploy count     = 0
Modal runs       = 0

start timestamp added     = YES
end timestamp added       = YES
pass/outcome added        = YES
rows positioned           = YES
rows remain non-accounting = YES
historical artifacts supported = YES
expected overhead         = < 1 µs per node (2 perf_counter reads + dict append); < 0.001% of a 15 s run
ready for integration     = YES
```
