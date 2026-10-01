# Golden Exhaustive Multiprocess Profiler

Purpose: **make wasted time inside Golden obvious**, from the actual call trace,
without adding another stopwatch to Golden.

Open one Markdown artifact after a traced request and walk

```
whole request -> canonical stage -> exact function -> child function
              -> thread/process lane -> bubble/residual
```

and know where optimization work should go.

This is an extension of the existing `FullExecutionTraceSession` profiler, not a
second profiling architecture. Capture is still owned by the full-trace session;
this adds an exhaustive *analysis and rendering* pass alongside the existing
>50 ms Golden quick view, which is preserved unchanged.

---

## 1. Files changed

| File | Change |
|---|---|
| `comfymodal_runtime/golden_exhaustive_profile.py` | **New.** Offline exhaustive analyzer + 9-section Markdown renderer + artifact writer. Imports no profiler. |
| `comfymodal_runtime/process_trace_bridge.py` | **New.** Generic cross-process trace control: trace-identity env export, dynamic process registry, `ChildTraceController` (TRACE_BEGIN/TRACE_END), clock anchors. The single process-boundary integration. |
| `comfymodal_runtime/full_execution_trace.py` | Added `GOLDEN_ROOT_CATEGORY`, `golden_root_span()`, `_resolve_bound_tracer()`, `FullExecutionTraceSession.get_instance()`. |
| `comfymodal_runtime/full_trace_report.py` | Added `_maybe_generate_golden_exhaustive_profile()` and wired it into `generate_full_trace_report`. **Fixed an O(n²) parent scan in `_reconstruct_parents`** that made a real 152k-call Golden trace take >10 minutes. |
| `comfymodal_runtime/golden_parallel.py` | Aligned to `production-007`, then **fixed the authoritative root**: `golden_parallel_execute` now spans the entire executor. |
| `comfymodal_runtime/golden_serial.py` | Added `golden_root_span()` seam and used it for the serial root (the span already wrapped the whole executor; now it is also machine-identifiable). |
| `comfymodal_runtime/golden_io_process_v2.py` | One generic process-boundary integration: export the trace identity into the C0 child env and register the child as an expected process. |
| `comfymodal_runtime/golden_loader_process.py` | TRACE_BEGIN / TRACE_END ops on the persistent worker's existing control protocol, plus parent-side `begin_trace()` / `end_trace()`. |
| `tests/test_golden_exhaustive_profile.py` | **New.** 44 synthetic tests, exact-timestamp fixtures. |
| `reports/GOLDEN_EXHAUSTIVE_MULTIPROCESS_PROFILER.md` | This document. |

No timing instrumentation was added to any Golden helper. The only Golden-side
changes are (a) one root span and (b) two process boundaries.

---

## 2. Architecture

```
                    capture (unchanged owner)
  FullExecutionTraceSession  ── VizTracer, one request
        │
        ├── parent process trace          raw/viztracer.json.gz
        ├── child processes (Case A)     raw/viztracer_<pid>.json(+.meta.json)
        ├── persistent workers (Case B)  TRACE_BEGIN / TRACE_END
        └── dynamic process registry     raw/golden_process_registry.json
        │
                    analysis (new, offline)
  golden_exhaustive_profile.analyze()
        ├── discover_process_traces()      observed processes, roles, evidence
        ├── calibrate_clocks()             PROVEN / UNPROVEN + measured skew
        ├── build_exhaustive_calls()       one row per invocation
        ├── select_authoritative_root()    exactly one Golden root
        ├── resolve_descendants()          dynamic transitive subtree
        ├── per stage: functions, bubbles, lanes, call tree, diagnosis
        └── evaluate_completeness()        fail-closed contract
        │
                    artifacts
  derived/golden_exhaustive_profile.md
  derived/golden_exhaustive_calls.csv.gz
  derived/golden_process_manifest.json
  derived/golden_exhaustive_summary.json
  derived/viztracer_merged.json.gz        (only when CLOCK_ALIGNMENT=PROVEN)
```

### Dynamic discovery — the fundamental rule

**There is no list of Golden function names in the profiler.** A test asserts
that (`assert not hasattr(gep, "GOLDEN_FUNCTION_NAMES")`). Coverage comes from
walking the reconstructed call tree out of the single authoritative root:

```
authoritative root -> every captured descendant -> every descendant of those
```

`CANONICAL_STAGE_ORDER` exists only to *label* sections and to check the
completeness contract. A helper added tomorrow underneath `golden_unet_load`
appears automatically.

---

## 3. Golden root truth

### The bug that was real

On `production-007`, `golden_parallel.py` had:

```python
with _golden_trace_span("golden_parallel_execute"):
    await golden_restore(session)
_hb("restore_done")
...  # the entire rest of Golden, outside the span
```

The span named `golden_parallel_execute` covered **only restore**. Meanwhile the
report's `_golden_named_calls()` prefers "explicit FEE" records, and in
VizTracer 1.1.1 that preference is a **no-op**, because `VizEvent.__exit__`
hardcodes `"cat": "FEE"` — byte-for-byte identical to the automatic Python-call
record of the same function. Two competing roots, and no way to tell them apart
from the artifact.

### The fix

1. `golden_parallel_execute` now opens before any request work and closes in the
   `finally` **after** teardown and after the loader worker releases its
   child-side storage. Telemetry persistence and exit-gate plumbing stay
   outside.
2. The root is emitted under a dedicated Chrome category `GOLDEN_ROOT`
   (`full_execution_trace.golden_root_span`). Same tracer, same clock, no new
   measurement — it just makes the authoritative root *identifiable offline*.
3. `select_authoritative_root()` prefers `GOLDEN_ROOT`, falls back to exactly
   one FEE root (compatibility with pre-existing artifacts), and fails closed on
   zero or multiple.
4. Records describing an **identical interval** to the root (explicit span and
   the function's own call record) are absorbed rather than nested. Without this
   the correct root could be selected and then come back with an empty subtree.

Serial already wrapped the whole executor (`_trace_golden_serial_root`); it is
now machine-identifiable, and a test proves it.

---

## 4. Process tracing design

### Case A — child spawned during an active traced request

The parent exports the trace identity into the child's environment via
`process_trace_bridge.session_trace_env()`. A child that boots with it calls
`apply_trace_env()` → `ChildTraceController.trace_begin()` / `trace_end()` and
writes:

```
<raw_dir>/viztracer_<pid>.json          its own trace
<raw_dir>/viztracer_<pid>.meta.json      trace_id, request_id, pid, parent_pid,
                                         role, started/ended monotonic + wall,
                                         include_paths, entry count, entry
                                         capacity, truncated, base_time_nanoseconds,
                                         viztracer_version
```

Wired at the C0 process-creation boundary (`golden_io_process_v2.py`). The
existing `COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER` path is untouched and its
artifacts are read too — the profiler accepts both naming conventions.

### Case B — persistent child already alive

Inheritance cannot reach it, so it is driven through its existing control
protocol:

```
TRACE_BEGIN(trace_id, request_id, metadata)
  ... normal request commands ...
TRACE_END(trace_id)
```

Implemented in `golden_loader_process.py` on the `ping`/`init`/`init_cuda`/
`load`/`stop` protocol. `trace_begin` is idempotent for a repeated
`trace_id`; a stale `trace_end` returns `mismatch` and **does not** close or
drop a newer live trace. No stopwatch was added to any load path.

### Roles

Roles come from the per-process sidecar when present; otherwise from evidence.
The process that owns the authoritative Golden root is recorded as `parent` —
derived from the trace, not from a filename. Anything unattributable becomes
`other:<module>` or `other:pid<n>`. Unknown is better than false attribution.

### Expected-process accounting

`ProcessTraceRegistry` builds the expected set from what the runtime actually
registers. Nothing hardcodes "4 workers". A topology with no children reports
`expected_processes=1`. When ownership cannot be established the coverage is
`UNKNOWN`, deliberately distinct from `COMPLETE`.

---

## 5. Clock alignment

VizTracer 1.1.1 emits timestamps relative to a machine-monotonic origin recorded
as `baseTimeNanoseconds`. Two processes that recorded the same origin are
directly comparable; the residual uncertainty is bounded by the difference
between the two origins.

```
CLOCK_ALIGNMENT=PROVEN    every observed process supplied an origin and they all
                          agree within MAX_CLOCK_SKEW_NS (1 ms)
CLOCK_ALIGNMENT=UNPROVEN  a missing origin, or origins further apart than the
                          tolerance, or no readable process trace
```

Measured on real `production-007` artifacts: parent and C0 child differ by
**4 ns**, so the merged timeline is legitimate there. On unproven clocks:

* no `derived/viztracer_merged.json.gz` is written at all;
* per-process lanes are still listed, but the chart is explicitly per-process;
* cross-process bubble attribution is refused (`other_process_traced_ms` is
  `None`, not `0`);
* the report carries an explicit `CLOCK ALIGNMENT IS UNPROVEN` banner.

A 5-second skew is a test case that must fail closed — it does.

---

## 6. Thread coverage (measured, not assumed)

Verified on the installed VizTracer 1.1.1:

| Claim | Verdict | How it is established |
|---|---|---|
| Request-owner thread | captured | `start()` traces the calling thread |
| Thread created **after** activation | captured **with no further help** | `enable_thread_tracing()` + `threading` re-applies the hook in `Thread._bootstrap_inner` |
| Thread that **already existed** | **NOT captured** | `sys.setprofile` only affects the calling thread; an already-running thread keeps its own (empty) profile |
| Already-existing thread **after explicit in-thread handoff** | captured | `sys.setprofile(tracer.threadtracefunc)` from inside that thread |
| asyncio tasks | captured | coroutines get their own `Task-*` lanes; `asyncio.to_thread` work lands on pool threads |

This is why the session's existing central handoff
(`_handoff_request_thread_tracing`) exists and why the profiler implements it
rather than trusting `register_global`. `THREAD_COVERAGE` is derived from the
artifact: `COMPLETE` when more than one lane produced traced calls (positive
proof that post-activation threads were captured), or when the trace declares a
single lane (nothing could have been missed), `PARTIAL`/`UNKNOWN` otherwise.

Two further measured facts, recorded so nobody re-derives them:

* A Python frame whose entire body is one C call (e.g. only `time.sleep`) gets
  **no FEE record** in VizTracer 1.1.1, though the C call itself is recorded.
  Leaf functions can therefore be invisible; this is a tracer property, not a
  profiler bug, and is why test leaves are pure Python.
* Under pytest, worker-thread `sys.setprofile` events are not recorded at all
  even though the hook is installed in the worker. The thread-coverage proof
  therefore runs in a subprocess rather than shipping a test whose verdict
  depends on the harness.

---

## 7. Completeness contract (fail closed)

`GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=YES` requires **all** of:

1. exactly one authoritative Golden root
2. root begin/end complete
3. all required canonical stages present (derived from the request's durability
   mode — an observed-but-not-required stage is never promoted into the contract)
4. raw trace non-empty
5. no trace truncation (per process, `overflow` or count-at-capacity)
6. no stack-depth truncation
7. no root-corrupting incomplete calls
8. expected processes accounted for
9. all process-local traces accounted for
10. process clocks align for the merged Gantt
11. thread tracing coverage proven
12. every stage section generated
13. report rendering completed and the artifact written

Any failure yields `NO` plus the exact reason, e.g.

```
INCOMPLETE BECAUSE:
  - no_root_corrupting_incomplete_calls: incomplete_calls=6
```

Checks 12 and 13 are settled *after* a trial render, so a verdict of `YES` can
never exist without an artifact behind it; a render or write failure raises
instead of leaving a "complete" claim on disk.

---

## 8. Artifacts

```
derived/golden_exhaustive_profile.md        human-first, 9 sections, ASCII Gantt
derived/golden_exhaustive_calls.csv.gz      one row per captured invocation
derived/golden_process_manifest.json        expected / traced / missing
derived/golden_exhaustive_summary.json      machine-readable form of the report
derived/viztracer_merged.json.gz            only when CLOCK_ALIGNMENT=PROVEN
```

`golden_exhaustive_calls.csv.gz` columns (deterministic order):

```
event_index, process_role, pid, parent_pid, tid, task_id,
function, qualified_function, source_file, source_line, category,
parent_event_index, parent_function, depth,
start_offset_ms, end_offset_ms, wall_ms,
direct_child_count, direct_child_sum_ms, direct_child_union_ms,
child_overlap_ms, exclusive_self_ms, complete
```

No aggregation is applied: a 20 µs call is retained exactly like a 2 s call.
`functions_summary.csv` remains as the aggregate view.

### Report structure

1. Trace health / trust
2. 30-second human summary
3. Whole Golden Gantt (ASCII, fixed width, deterministic)
4. **One waterfall per canonical stage** — wall summary, function-cost tables
   (by inclusive / exclusive / count / worst single call), exhaustive Gantt,
   bubble analysis, concurrency, repeated calls, largest self-time calls, call
   tree, diagnosis
5. Bubble / gap analysis (whole request)
6. Top offenders (50 each: calls by wall, functions by inclusive, by exclusive,
   by count, repeated setup, stage residuals, bubbles)
7. Process / thread lanes with overlap
8. Call tree
9. "Why is this stage slow?" — mechanical, arithmetic only

### Markdown folding

A 1 ms default visual threshold (`COMFYMODAL_GOLDEN_EXHAUSTIVE_VISUAL_MS`)
controls **rendering only**. Above it, calls are drawn individually; below it,
one grouped row per function with an explicit count and time total, plus a
deterministic compact tree in the JSON summary. Nothing is deleted from the CSV
or the JSON. ASCII is authoritative; no Mermaid dependency.

---

## 9. Bubble definition

A **bubble** is a time interval inside the subject frame's wall **not covered by
a traced child on that same execution context**. The subject frame (the stage,
or the root) is deliberately excluded from its own coverage — including it would
cover the whole window and report zero bubbles, hiding exactly the "400 ms
vanished between two fast calls" case the profiler exists to find.

A bubble does **not** mean idle, storage wait, or scheduling delay. What
overlapped it is measured and reported. Classification precedence, and why:

1. `OTHER_THREAD_ACTIVE` — another thread on the same process covered >= 50%
2. `OTHER_PROCESS_ACTIVE` — another process covered >= 50% **and** the clocks
   were proven comparable before the claim is made at all
3. `UNTRACED_NATIVE_OR_C` — inside a traced Python frame while C/native call
   tracing is disabled
4. `SELF_OR_NATIVE` — inside a traced Python frame with C tracing enabled
5. `ASYNC_WAIT_POSSIBLE` — the resource sampler observed the lane not
   progressing (consistent with a wait; does not prove one)
6. `UNKNOWN` — nothing covers it

Every bubble carries: stage, process, thread/task, start/end offset, duration,
previous and next traced function, same-thread / other-thread / other-process
traced milliseconds, semantic (source/H2D) evidence overlapping, CPU/resource
evidence, classification and the measured basis for it.

All bubbles are counted and summed; the 200 largest get full per-interval
evidence, and the remainder stay in the JSON as counts and totals.

---

## 10. Native / C / CUDA honesty

Python tracing does not decompose native time. The report always states:

```
Python-visible wall | Python child union | self/native/untraced residual
```

and labels untraced time inside a Python frame as `UNTRACED_NATIVE_OR_C` (or
`SELF_OR_NATIVE` when C tracing is on) — never as "CPU computation" unless
proven. Torch/CUDA evidence stays in its own domain and is not merged into host
timelines. Existing Golden semantic telemetry (source/H2D, C0 window, sampling
deep profile, resource sampler) is surfaced as *cross-evidence* on a bubble and
never overwrites raw VizTracer facts; clocks are not subtracted unless alignment
was proven.

---

## 11. Selector and overhead

```powershell
# capture (deploy-baked, already in config/v2/flag_registry.toml)
COMFYMODAL_V2_FULL_TRACE=1

# report rendering (report-only selector)
COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE=1

# optional: Markdown visual threshold, rendering only (default 1.0 ms)
COMFYMODAL_GOLDEN_EXHAUSTIVE_VISUAL_MS=1.0
```

`COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE` is a **report-rendering** selector. It
cannot enable capture, so a request without a full trace is unaffected either
way. With it OFF, `generate_full_trace_report` writes nothing extra and imports
no profiler. Both new modules import nothing heavy at module scope, and
`process_trace_bridge` imports VizTracer only inside `trace_begin`.

Overhead while enabled is diagnostic by design; correctness/completeness wins.
Report generation and final serialization run outside the measured Golden root.

---

## 12. Tests

`tests/test_golden_exhaustive_profile.py` — 44 tests, ~9 s, all `fast_unit`.
Every fixture uses exact microsecond timestamps so the expected arithmetic is
checkable by hand.

| # | Case | Test |
|---|---|---|
| 1 | single-process nested tree, exact self/inclusive math | `test_single_process_nested_tree_exact_accounting` |
| 2 | new helper appears with no registry change | `test_new_helper_under_stage_appears_without_any_registry` |
| 3 | thread created after activation, no handoff | `test_thread_created_after_activation_is_traced_without_handoff` |
| 4 | thread existing before activation is **not** traced | `test_thread_existing_before_activation_is_not_traced_without_handoff` |
| 5 | ...and is traced after the explicit handoff | `test_thread_existing_before_activation_is_traced_after_explicit_handoff` |
| 6 | asyncio tasks | `test_asyncio_tasks_are_captured` |
| 7 | concurrent thread lanes in a synthetic trace | `test_synthetic_thread_lanes_and_other_thread_overlap` |
| 8 | child spawned during traced request writes its own trace + full sidecar | `test_child_spawned_during_traced_request_records_own_trace` |
| 9 | no trace env -> child inert | `test_no_trace_env_means_child_is_inert` |
| 10 | persistent child TRACE_BEGIN/TRACE_END, idempotent, inert by default | `test_persistent_child_trace_begin_end_is_idempotent_and_inert` |
| 11 | stale TRACE_END refused without dropping the live tracer | `test_trace_end_mismatched_id_is_refused` |
| 12 | two overlapping child processes merge in the right order | `test_two_child_processes_overlapping_merge` |
| 13 | child trace missing -> PARTIAL + named missing process | `test_missing_child_trace_fails_closed` |
| 14 | child trace truncated -> fail closed | `test_truncated_child_trace_fails_closed` |
| 15 | parent trace truncated -> fail closed | `test_truncated_parent_trace_fails_closed` |
| 16 | incomplete call inside the root -> fail closed | `test_incomplete_call_inside_root_fails_closed` |
| 17 | missing root -> fail closed, report still renders | `test_missing_root_fails_closed` |
| 18 | stack-depth cap respected; contract fails closed | `test_stack_depth_overflow_is_reported` |
| 19 | explicit root category wins over the call record | `test_explicit_root_category_wins_over_python_call_record` |
| 20 | two explicit roots -> fail closed | `test_two_explicit_roots_fail_closed` |
| 21 | ambiguous duplicate root without a category -> fail closed | `test_ambiguous_duplicate_root_without_category_fails_closed` |
| 22 | Parallel source emits exactly one root span (AST proof) | `test_parallel_source_emits_exactly_one_root_span_wrapping_the_executor` |
| 23 | Parallel root contains every canonical stage | `test_parallel_root_covers_every_canonical_stage_in_a_real_trace` |
| 24 | serial root wraps the whole executor | `test_serial_root_wraps_the_whole_executor` |
| 25 | required stages follow the durability mode | `test_required_stages_follow_the_request_durability_mode` |
| 26 | bubble between child intervals, exact | `test_bubble_between_child_intervals_is_exact` |
| 27 | overlapping children do not double-count exclusive time | `test_overlapping_children_do_not_double_count_exclusive_time` |
| 28 | bubble classification uses measured overlap | `test_bubble_classification_uses_overlap_evidence` |
| 29 | a bubble with no evidence is not given an invented cause | `test_bubble_without_any_overlapping_work_is_not_invented` |
| 30 | 10,000 x 0.2 ms accumulate to 2000 ms, all retained in the CSV | `test_ten_thousand_tiny_calls_accumulate` |
| 31 | source file/line identity survives into the CSV | `test_source_file_and_line_survive_into_the_csv` |
| 32 | skewed clocks fail closed and refuse a merged Gantt | `test_skewed_clocks_fail_closed_and_refuse_a_merged_gantt` |
| 33 | missing clock origin fails closed | `test_missing_clock_origin_fails_closed` |
| 34 | proven clocks record the measured uncertainty | `test_proven_clocks_record_the_measured_uncertainty` |
| 35 | selector OFF writes nothing | `test_exhaustive_selector_off_writes_nothing` |
| 36 | selector ON still requires a Golden root | `test_exhaustive_selector_on_requires_a_golden_root` |
| 37 | full trace OFF leaves Golden execution untouched | `test_full_trace_off_leaves_golden_execution_untouched` |
| 38 | all nine sections present; rendering deterministic; ASCII only | `test_report_contains_all_nine_sections_and_is_deterministic` |
| 39 | the four-artifact contract | `test_five_artifact_contract` |
| 40 | manifest is UNKNOWN without ownership evidence | `test_manifest_is_unknown_without_ownership_evidence` |
| 41 | single-process architecture reports one process | `test_single_process_architecture_reports_one_process` |
| 42 | registry size is dynamic | `test_registry_size_is_dynamic_not_hardcoded` |
| 43 | roles are never invented | `test_roles_are_never_invented` |
| 44 | a manifest sidecar is never counted as a process | `test_manifest_sidecar_is_never_counted_as_a_process` |

Run:

```powershell
python tools/test_perf.py --fast -- tests/test_golden_exhaustive_profile.py -m fast_unit
```

### Bugs these tests found in the existing profiler

* `_reconstruct_parents` did a linear scan of the whole group per call to find a
  parent: O(n²). A real 152,044-call Golden trace took >10 minutes; it now takes
  ~1.5 s. Same behaviour, same output.
* A Python-call record and an explicit span covering the **same** interval were
  nested inside each other, which could leave the correct root with an empty
  subtree.
* A same-context call left unparented because of an overlapping sibling was
  counted as the enclosing frame's **self time**, inflating it. Fixed with a
  containment sweep in `_children_map`.

---

## 13. Validation against real artifacts

Run offline against a retained `production-007` Golden trace
(`golden_parallel_c0_qd2_viztracer_forensics/run_04`, 152,044 parent events +
23,129 C0-child events, 10 parent threads, 4 child threads):

```
python tools/v2ctl.py ...   # or directly:
python -c "from comfymodal_runtime import full_trace_report as f, golden_exhaustive_profile as g; \
           s=Path('<session>'); c=f._build_calls(f.parse_chrome_trace_events(...)); \
           f._reconstruct_parents(c); p=g.analyze(s, parent_calls=c, trace_config=f._parse_trace_config(s)); \
           print(g.write_artifacts(s,p))"
```

Observed result (~31 s total):

```
GOLDEN_EXHAUSTIVE_PROFILE_COMPLETE=NO     (6 incomplete calls — honest)
ROOT=golden_parallel_execute   ROOT_WALL_MS=17019.3
PROCESS_COVERAGE=UNKNOWN       TRACED_PROCESSES=2      MISSING_PROCESSES=none
THREAD_COVERAGE=COMPLETE       CLOCK_ALIGNMENT=PROVEN  (4 ns skew)
TRACE_ENTRY_COUNT=175173       TRACE_ENTRY_CAPACITY=16000000
```

All 11 canonical stages resolved. Largest findings:

```
golden_sampling      4964.9 ms      golden_clip_load      3471.6 ms
golden_unet_load    3443.5 ms      golden_clip_forward   1650.1 ms

273.7 ms  golden_clip_load  OTHER_PROCESS_ACTIVE
   other-thread 0.0 ms, other-process 273.7 ms (100% coverage, proven clocks)
```

That bubble is the exact question the profiler was built for: for 273.7 ms the
parent thread had **no** traced Python child while the C0 child process was
busy the whole time. Report is ~9,900 lines / 549 KB.

Old artifacts report `PROCESS_COVERAGE=UNKNOWN` because they predate
`golden_process_registry.json`; that is labelled honestly rather than papered
over.

---

## 14. Limitations

* **Python tracing cannot decompose native/CUDA time.** Untraced time inside a
  Python frame is reported as such, never attributed.
* **A Python frame whose body is a single C call produces no FEE record** in
  VizTracer 1.1.1. Leaf wrappers can be invisible; their C call is still traced.
* **A thread that already existed before activation is not captured** without
  the explicit in-thread handoff. Golden's existing source/dispatcher threads
  therefore depend on that handoff for completeness.
* **C function tracing is enabled in the session config**, so `SELF_OR_NATIVE`
  vs `UNTRACED_NATIVE_OR_C` reflects that setting, not a hardcoded choice.
* **Cross-process claims require proven clocks.** On old artifacts with no
  recorded origin, cross-process attribution is refused.
* **Coverage cannot be claimed without ownership evidence** — an unregistered
  process set yields `UNKNOWN`, not `COMPLETE`.
* The exhaustive analysis of a 174k-call request takes ~31 s and writes a
  ~549 KB report. It is a diagnostic run, not a hot path.

---

## 15. What one traced Golden request would validate

The implementation is validated offline against real `production-007` traces.
Validating the **new process-bridge wiring** (registry, roles, TRACE_BEGIN on a
persistent worker) needs one traced request on a deployed experimental app.

Exactly what is needed:

1. An isolated experimental app (never `stable-modal-comfy-v2-golden-p1`).
2. A resolved profile extending `golden_p1_parallel_c0_source_h100` with
   `COMFYMODAL_V2_FULL_TRACE=1`, `COMFYMODAL_GOLDEN_EXHAUSTIVE_PROFILE=1`, and
   `COMFYMODAL_GOLDEN_C0_CHILD_VIZTRACER=1`, registered in
   `config/v2/flag_registry.toml`.
3. `v2ctl golden deploy` → `source-probe` → `doctor`/`status` (ready=True, no
   overrides) → **exactly one** `golden run`.
4. Discard that run and the one after it if either is a `SNAPSHOT_CAPTURE`.
5. Retrieve the `full_trace_<id>` bundle and run the offline reporter.
6. Confirm in `golden_process_manifest.json`: `expected_processes` matches the
   runtime's real child count, roles are truthful, `CLOCK_ALIGNMENT=PROVEN`, and
   the C0 child appears as `raw/viztracer_<pid>.json` or
   `raw/trace_child_viztracer.json`.

What that proves that local tests cannot: that the process registry is written
by the running container, that roles resolve from live evidence, and that
TRACE_BEGIN/TRACE_END reaches a persistent worker that was already alive.

**Blocking prerequisite:** the working tree currently carries uncommitted
in-progress changes in `golden_source_threads.py` (~2,041 lines) and
`modal_app.py` that were not written for this task. Deploying publishes that
work to the shared custom-nodes Volume and runs it on a paid GPU, so the tree
must be cleaned (or that lane's owner must approve) before the capture is
responsible. That decision is not mine to make.
