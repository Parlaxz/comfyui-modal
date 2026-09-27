# V2 Batch D5 — Runtime Wait Attribution

## Scope

Instrument the remote setup window and the per-node execution window so that:

- the ~0.8 s remote-method-setup bucket is reconciled into measured children and a
  residual (no unexplained bucket),
- a node row can never again be read as "ImpactSwitch computed for 2 seconds" when
  the truth is "ImpactSwitch was the point where the executor waited 1.9 s for
  UNET",
- the UNET future ready / first-consumer wait / wait-end / duration are captured
  so the next run can quantify how much of the async loader is exposed on the
  graph critical path versus hidden under other work.

Pure instrumentation around execution ownership. No rgthree / custom-node
behavior was modified. No deploy, no Modal request, no paid run, no commit.

---

## What was built

### 1. New module: `comfymodal_runtime/wait_attribution.py` (pure, render-time)

Consumes only the already-captured trace + `pre_sampler_structured_report` data
(same inputs as `v2_waterfall.build_waterfall`). Never mutates the result; fully
synthetic-testable; imports nothing from ComfyUI.

**Wait-window extraction** — `extract_wait_windows(result)` builds disjoint,
priority-ordered windows from existing trace events (all in the remote
monotonic clock, which shares CLOCK_MONOTONIC with the node `perf_counter_ns`
timestamps on Modal/Linux):

| kind | source events |
|---|---|
| `loader_wait` | `graph_wait_start`→`graph_wait_end` (canonical), fallback `graph_unet_demand`→`graph_unet_wait_end` — brackets `future.result()` inside the graph loader call |
| `async_model_future_wait` | `unet_graph_join` metadata `join_start_mono_ns`/`join_completed_mono_ns`; `unet_quiesce_wait_start`→`unet_quiesce_wait_end` |
| `mutation_lane_wait` | `unet_gpu_lane_wait_start/end`, `gpu_lane_wait_start/end`, `unet_early_activation_lane_wait_start/end` |
| `sampler_lane_wait` | `sampler_lane_wait_start`→`sampler_lane_wait_end` |

No fabrication: a join without mono boundaries, a degenerate window (end ≤
start), or an unpaired start produces no window — even when a `*_ms` metadata
duration exists.

**Per-node classification** — `classify_node_wait(record, windows)` intersects
each wait window with the node's `[start_perf_ns, end_perf_ns]` window.
Attribution is disjoint (overlapping windows are resolved by priority, covered
sub-intervals never double-counted). Output: `total_node_wall`,
`node_non_wait_wall` (canonical: total − attributed waits; NOT proven compute —
it may contain unknown/unclassified wait and is documented as such;
`node_compute_wall` is retained only as a backward-compat alias with the
identical value), `dependency_wait_wall`, `async_model_future_wait`,
`loader_wait`, `mutation_lane_wait`, `sampler_lane_wait`, `other_wait`,
`wait_total`, `wait_kinds`, `available`.

**Task C** — `unet_first_consumer(result)` returns:
`unet_future_ready_mono_ns` (early-activation terminal → fast-disk complete →
lane `ready`), `first_consumer_wait_start_mono_ns` (first `graph_unet_demand`),
`consumer_wait_end_mono_ns` (first `graph_unet_wait_end` /
`graph_wait_end` / `prepared_result_consumed`), `consumer_wait_duration_ms`,
`unet_loader_total_ms`, `unet_exposed_on_critical_path_ms` (== the blocking wait
duration: that is exactly the graph-exposed portion), `unet_hidden_under_other_work_ms`
(= loader total − exposed, when loader total is known), plus availability flags
and `sources`. Every value is optional when the underlying events are missing —
never a fabricated zero.

**Task A** — `build_remote_setup_reconciliation(result)`:
`remote_setup_total_ms` = `remote_method_entry`→`prompt_executor_invoke_start`
(mono), represented as a NON-OVERLAPPING two-segment hierarchy:

```
remote_setup_total
├── entry_to_plan_first_status        (remote_method_entry → run_plan_first_status_yield)
│   ├── identity_capture              (run_plan_identity_capture_start/end)          [nested]
│   ├── plan_decode                   (run_plan_deserialize_start/end)               [nested]
│   ├── request_schedule              (remote_setup_schedule mono pair / schedule_ms) [nested]
│   ├── trace_setup                   (run_plan_trace_setup_start/end)               [nested]
│   └── residual_within_plan_receipt  (segment − measured nested children)           [derived]
└── plan_first_status_to_executor     (run_plan_first_status_yield → prompt_executor_invoke_start)
    ├── runtime_configuration         (runtime_config_start/end)                     [nested]
    ├── legacy_runtime_load           (legacy_runtime_load_start/end)                [nested]
    ├── execution_prefill_schedule    (execution_prefill_schedule_start/end)         [nested]
    ├── plan_proof                    (plan_proof_start→plan_proof_decision)         [nested]
    ├── graph_start_to_invoke         (graph_execution_start→prompt_executor_invoke_start) [nested]
    └── residual_after_plan_receipt   (segment − measured nested children)           [derived]
```

Top-level segments are disjoint and tile the total exactly when all boundaries
exist. ONLY the two top-level segments participate in `accounting_children_sum`
and `residual_ms` (= total − accounting_children_sum, ≈ 0 under tiling — a real
residual appears only when a segment boundary is missing). All nested stages are
explicitly NON-ACCOUNTING DETAILS (`non_accounting: True`): they may overlap
their parent AND each other (e.g. `graph_start_to_invoke` contains
`plan_proof`), are never subtracted from one another, and are never subtracted
twice. The interior residual rows (`residual_within_plan_receipt`,
`residual_after_plan_receipt`) expose the unexplained bucket inside each segment
without affecting the top-level residual. Status ladder on |residual|:
`closed` ≤ 10 ms (target), `warning` ≤ 50 ms, `open` > 50 ms, `unavailable`
when the total is unknown. Category taxonomy (waiting/CPU/lock-future-join/I/O)
is preserved via `category_summary` over the nested details. Backward-compat
keys: `children` == `top_level_segments`, `measured_children_ms` ==
`accounting_children_sum`.

**Task D** — `build_wait_reconciliation(result)`: `pre_sampler_total_ms`,
`node_wall_sum`, `node_non_wait_sum` (canonical; `node_compute_sum` is a
backward-compat alias with the identical value), `dependency_wait_sum`,
`async_model_future_sum`, `loader_wait_sum`, `mutation_lane_wait_sum`,
`sampler_lane_wait_sum`, `lane_wait_sum` (= mutation + sampler),
`future_wait_aggregate_ms`, `future_wait_outside_nodes_ms` (aggregate resolve
wait not attributed inside any node window),
`accounted_ms` = `node_wall_sum` + `future_wait_outside_nodes_ms`,
`residual_ms`, `status`. No double counting: node walls are disjoint, per-node
waits are subsets of node walls, and the outside-node future wait is disjoint
from node walls by construction.

### 2. Runtime additions (all additive, no behavior change)

- `comfymodal_runtime/runtime_executor.py`:
  - `_patched_resolve_results` now records each resolve await as a monotonic
    window (`state["_resolve_wait_windows"]`, trimmed at 1000 entries).
  - `_patched_exec_node` intersects those windows with the node's own
    `[t0, end_perf]` window and writes `dependency_wait_wall` (ms) on the
    per-node record — so an async dependency wait charged inside a node's wall
    window (e.g. a switch/control node whose input resolution awaits a future)
    is attributable per-node. Existing `future_wait_ms` aggregate untouched.
- `comfymodal_runtime/modal_app.py`:
  - `remote_setup_schedule` event emitted at trace-setup time with the measured
    request-schedule bracket (`schedule_start_mono_ns`/`schedule_end_mono_ns`/
    `schedule_ms`) covering the G1 UNET lane schedule, memo priming,
    conditioning-prefetch launch, input-types-warm launch and seed derivation,
    plus truthful `cc_prefetch_scheduled` / `input_types_warm_scheduled` /
    `seed_derived` flags.
  - `execution_prefill_schedule_start/end` brackets around
    `schedule_execution_prefill`.
  - `plan_proof_start` at the top of the plan-proof computation block
    (paired with the existing `plan_proof_decision`).

### 3. Waterfall rendering

`comfymodal_runtime/v2_waterfall.py` node rows now render, when any wait is
attributed (`wait_total > 0.5 ms`):

```
Node: ImpactSwitch — non-wait 100.0ms + wait 1900.0ms [loader_wait]
```

with the breakdown also carried in `source_fields` (`wait:...`). Rows without
waits are byte-identical to before; the 25 ms/strategic filter, row placement,
and non-accounting `child` role are unchanged, so reconciliation totals are
unaffected. Import is wrapped in `try/except ImportError` — a missing module
degrades to the previous labels. (`wait_attribution` lazily imports the
`v2_waterfall` helpers to break the module cycle in both import orders.)

---

## Task results

- **Task A — remote setup reconciliation**: implemented
  (`build_remote_setup_reconciliation`) as a NON-OVERLAPPING hierarchy:
  two disjoint top-level segments (`entry_to_plan_first_status`,
  `plan_first_status_to_executor`) tile the total; only they feed
  `accounting_children_sum` / `residual_ms` / status. Nested stages
  (identity capture, plan decode, request schedule — now actually bracketed at
  runtime, trace setup, runtime configuration, legacy runtime load,
  execution prefill schedule, plan proof — now bracketed, graph-start-to-invoke)
  are labelled NON-ACCOUNTING DETAILS and are never subtracted again; interior
  residual rows expose each segment's unexplained bucket. Status ladder:
  closed ≤ 10 ms (target), warning ≤ 50 ms, open > 50 ms.
- **Task B — node timing semantics**: implemented. Per-node
  `total_node_wall` splits into `node_non_wait_wall` (canonical; NOT proven
  compute — may contain unclassified wait; `node_compute_wall` kept only as an
  alias) + `dependency_wait_wall` + `async_model_future_wait` + `loader_wait` +
  `mutation_lane_wait` + `sampler_lane_wait` + `other_wait` (disjoint, no double
  count). The waterfall label renders "non-wait Xms + wait Yms [kind]", so
  "ImpactSwitch computed for 2 s" is no longer a possible reading. No
  rgthree/custom-node modification.
- **Task C — first consumer of UNET**: implemented
  (`unet_first_consumer`): future-ready timestamp, first graph-consumer
  waiting timestamp, wait end, wait duration, loader total,
  `unet_exposed_on_critical_path_ms`, `unet_hidden_under_other_work_ms`.
- **Task D — reconciliation**: implemented (`build_wait_reconciliation`):
  `pre_sampler_total`, `node_non_wait_sum` (+ `node_compute_sum` alias),
  `dependency_wait_sum`, `lane_wait_sum`, `residual`, `status`; outside-node
  future wait separated so the aggregate never double-counts node-attributed
  waits.

---

## Tests

`tests/test_v2_batch_d5_wait_attribution.py` — 14 synthetic tests, fake nodes /
fake futures only (no Comfy remote, no Modal, no deploy):

- window extraction for all five wait kinds; no fabrication from duration-only
  metadata; degenerate windows dropped;
- **ImpactSwitch scenario**: loader wait window inside an ImpactSwitch node
  window → attributed `loader_wait` ≈ 1900 ms, non-wait ≈ 100 ms
  (`node_non_wait_wall` canonical, `node_compute_wall` alias equality asserted);
- no-double-count priority overlap; `dependency_wait_wall` field; unavailable
  records;
- UNET first-consumer timestamps/durations incl. ready-before-demand and
  demand-before-ready variants; missing events → None, never fabricated;
- **non-overlapping remote-setup hierarchy**: disjoint top-level segments tile
  the total (600 + 500 = 1100 ms → `accounting_children_sum` 1100.0, residual
  0.0, status closed); nested stages overlapping their parent AND each other
  (e.g. `graph_start_to_invoke` containing `plan_proof`) never affect
  accounting and produce EXACT interior residuals
  (`residual_within_plan_receipt` 490.0, `residual_after_plan_receipt` 345.0);
  status ladder closed / open / unavailable (warning band documented as
  unreachable under exact tiling); residual never negative under tiling;
- wait reconciliation (Task D): exact sums, outside-node future wait, residual,
  statuses; empty result → nothing fabricated.

Verification run (final integrated state, after the D6-preflight correction):

```
45 passed  (D5 14 + test_v2_waterfall 31)
81 passed  (test_waterfall_reconciliation + test_waterfall_attach_central + test_v2_per_node_timeline)
36 passed  (test_v2_waterfall_contract)
```

plus the earlier full affected-suite run (`158 passed`) covering
`test_waterfall_scheduling_denominator.py` and
`test_v2_final_observability.py`.

---

## Final

```
remote reconciliation now non-overlapping = YES
accounting hierarchy =
    remote_setup_total
    ├── entry_to_plan_first_status        (remote_method_entry → run_plan_first_status_yield)
    └── plan_first_status_to_executor     (run_plan_first_status_yield → prompt_executor_invoke_start)
    Disjoint top-level segments tile the total exactly; ONLY they participate in
    accounting_children_sum / residual_ms / status. residual ≈ 0 under tiling; a
    real residual appears only when a segment boundary is missing (degraded
    truth, never fabricated).
nested detail treatment =
    identity_capture, plan_decode, request_schedule, trace_setup,
    runtime_configuration, legacy_runtime_load, execution_prefill_schedule,
    plan_proof, graph_start_to_invoke are NON-ACCOUNTING DETAILS
    (non_accounting: True) under their parent segment. They may overlap their
    parent AND each other (graph_start_to_invoke contains plan_proof); they are
    never subtracted from one another and never subtracted twice. Interior
    residual rows (residual_within_plan_receipt / residual_after_plan_receipt)
    expose each segment's unexplained bucket without touching top-level residual.
node compute/non-wait semantic =
    node_non_wait_wall is canonical: total_node_wall − attributed waits. It is
    NOT proven compute (may contain unknown/unclassified wait); node_compute_wall
    is retained only as a backward-compat alias. Waterfall labels render
    "non-wait Xms + wait Yms [kind]" (e.g. ImpactSwitch — non-wait 100.0ms +
    wait 1900.0ms [loader_wait]).
tests =
    14 synthetic D5 tests (non-overlap tiling, nested-overlap exact residual
    490.0/345.0, status ladder, alias equality) + existing suites: 45 (D5 +
    waterfall), 81 (reconciliation + attach + per-node timeline), 36 (waterfall
    contract) — all passing; earlier affected-suite run 158 passed.
files changed =
    comfymodal_runtime/wait_attribution.py (new; hierarchy + node_non_wait_wall)
    comfymodal_runtime/runtime_executor.py (resolve-wait windows +
        dependency_wait_wall per node)
    comfymodal_runtime/modal_app.py (remote_setup_schedule,
        execution_prefill_schedule_start/end, plan_proof_start)
    comfymodal_runtime/v2_waterfall.py (node-row non-wait/wait labels)
    tests/test_v2_batch_d5_wait_attribution.py (new)
    V2_BATCH_D5_RUNTIME_WAIT_ATTRIBUTION_REPORT.md (this file)
commit = none
Modal requests = 0
deploys = 0

READY_FOR_D6 = YES
    (accounting is disjoint; nested details cannot double-count; node "compute"
    label is truthful; all D5 wait attribution preserved — ImpactSwitch labels,
    UNET exposed/hidden metrics, resolve windows, waterfall rendering)

next remote run will determine =
    the real per-boundary remote-setup accounting (does the ~0.8 s bucket break
    out across entry_to_plan_first_status + plan_first_status_to_executor with
    their interior residuals?), whether the ImpactSwitch blob actually breaks
    out as loader_wait / async_model_future_wait / dependency_wait_wall on real
    traces, and the real UNET exposed-vs-hidden split (how much of the ~2.4 s
    loader is truly on the graph critical path).
```
