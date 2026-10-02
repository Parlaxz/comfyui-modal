# V2 Batch D4 — Meta Construction and UNET Pipeline Residual Forensics

Purpose: instrument the integrated true-cold loader path so the next remote (paid) run can
attribute the systematic ~2 s meta `get_model` cost and the unexplained pipeline residual
(0.3–1.2 s) to stable boundaries, and selectively disable the `input_types_warm` daemon
without code edits. No performance change is made. No deploy, no Modal request, no commit.

Revision 2 (D4.1): reconciliation semantics corrected (execution vs lifecycle intervals),
truthful CPU terminology, deep profiler default OFF, disjoint accounting audit, focused
test module. This revision supersedes the earlier draft's key semantics.

## 1. Evidence being explained

Four true-cold integrated runs:

| metric | runs (ms) |
|---|---|
| meta get_model | 2292.9 / 2576.2 / 1970.6 / 1932.4 |
| fastsafe file→GPU | 2172.9 / 2499.3 / 1867.7 / 1859.5 |

- ~2 s meta cost is systematic in the integrated cold path, vs the isolated C8 band
  19.5–199.9 ms.
- `input_types_warm` overlapped the meta worker: ~2.25 s (healthy run), ~4.81 s
  (pathological host). Contention remains a HYPOTHESIS until remote A/B.
- Unexplained pipeline residual: ~0.3–0.5 s (healthy), ~1.2 s (slow run).

This batch does not claim causality; it makes every boundary measurable.

## 2. Task A — meta get_model breakdown (Worker A)

Instrumented in `_fs_meta_construct` + the `_worker_a` closure
(`comfymodal_runtime/unet_fastsafetensors.py`).

### 2.1 Intervals (all ms)

| key | interval |
|---|---|
| `meta_worker_start_delay_ms` | `Thread()` construction/submission stamp → first worker instruction |
| `meta_worker_execution_wall_ms` | first worker instruction → worker end |
| `meta_lifecycle_total_ms` | `Thread()` construction/submission → worker end (start delay + execution wall) |
| `meta_import_wall_ms` | the `import torch` statement inside the worker |
| `meta_context_entry_wall_ms` | entering `no_grad/device("meta")` |
| `meta_get_model_wall_ms` | top-level model constructor `config.get_model(meta_sd, "")` (existing key, kept) |
| `meta_param_validate_wall_ms` | "all params are meta" gate |
| `meta_sampling_detect_wall_ms` | model_sampling poison detection |
| `sampling_fix_wall_ms` | model_sampling repair (existing key, kept) |
| `meta_return_prep_wall_ms` | sampling check → return |
| `meta_worker_thread_cpu_ms` | `time.thread_time()` delta over the execution interval (per-thread CPU only; guarded, None on failure) |
| `meta_non_thread_cpu_wall_ms` | max(0, execution wall − thread CPU) — wall NOT attributable to the worker thread's CPU; explicitly NOT labeled scheduler wait |
| `meta_worker_effective_cores` | `thread_cpu_ms / execution_wall_ms` (None-safe) |

### 2.2 Reconciliation (corrected — disjoint parent/child semantics)

Pure function `_fs_meta_reconcile(*, start_delay_ms, execution_wall_ms, import_ms,
context_entry_ms, get_model_ms, param_validate_ms, sampling_detect_ms, sampling_fix_ms,
return_prep_ms, lifecycle_total_ms) -> dict`:

```
meta_execution_children_ms = import + context_entry + get_model + param_validate
                             + sampling_detect + sampling_fix + return_prep
meta_execution_residual_ms = meta_worker_execution_wall_ms − meta_execution_children_ms
meta_lifecycle_children_ms = meta_worker_start_delay_ms + meta_worker_execution_wall_ms
                             (start delay counted exactly ONCE)
meta_lifecycle_residual_ms = meta_lifecycle_total_ms − meta_lifecycle_children_ms
meta_reconcile_status      = "OK" if |meta_lifecycle_residual_ms| < 5.0 else "GAP"
```

No overlapping child participates twice: the execution children are nested detail INSIDE
`meta_worker_execution_wall_ms` and are never added to `meta_lifecycle_children_ms`
separately. `_fs_meta_construct` emits the always-on + derived keys on direct calls
(lifecycle == execution when no start delay is measurable); the `_worker_a` closure
overwrites with its pipeline-scoped stamps. Superseded keys removed (verified no
consumers): `meta_worker_total_wall_ms`, `meta_total_ms`, `meta_children_ms`,
`meta_residual_ms`, `meta_wait_estimate_ms`.

Deep profile (gated, see section 5): `meta_module_construct_ms_by_class`,
`meta_module_construct_total_wall_ms`, `meta_module_construct_count`,
`meta_module_first_op_wall_ms` (first-op proxy), `meta_gc_wall_ms`, `meta_gc_count`,
`meta_forensics_error`.

## 3. Task B — input_types_warm contention switch

`comfymodal_runtime/modal_app.py`, scheduling site of the
`comfymodal-input-types-warm` daemon thread.

- **Toggle:** `COMFYMODAL_V2_INPUT_TYPES_WARM` via `env_flag(name, default=True)`.
  Env unset → warm still scheduled (current behavior preserved byte-for-byte).
  `0/false/off` → thread not spawned; one line
  `[v2.input_types_warm] request_id=… disabled reason=COMFYMODAL_V2_INPUT_TYPES_WARM=0`
  plus trace metadata `input_types_warm_enabled=False`,
  `input_types_warm_reason="COMFYMODAL_V2_INPUT_TYPES_WARM=0"`.
- **Instrumentation (enabled path, additive):**
  - `input_types_warm_scheduled_mono_ns`, `input_types_warm_scheduled_wall_unix_ns`
  - worker start / end stamps (first instruction / completion)
  - `input_types_warm_cpu_ms` (`time.thread_time()` delta, guarded),
    `input_types_warm_wall_ms` (= `input_types_warm_ms`, legacy key kept),
    `input_types_warm_cpu_affinity_count` (`len(os.sched_getaffinity(0))` fallback
    `os.cpu_count() or 0`), `input_types_warm_effective_cores`
    (`cpu_ms / wall_ms`, None-safe)
  - registry entry `input_types_warm` via `trace.register_forensic_interval(...)` with
    `request_id`, `warm_ms`, `classes`, `cpu_affinity_count`, `effective_cores`
  - overlap vs the fastsafe workers computed at warm end:
    `input_types_warm_overlap_meta_ms`, `input_types_warm_overlap_fastsafe_ms`,
    `input_types_warm_worker_started_observed`,
    `input_types_warm_overlap_scope` = `complete | partial | unavailable`
    (complete = both worker intervals finished before computation and request_id
    matched; partial = intervals present but still running; unavailable = missing /
    request mismatch)
  - evidence print extended: `…wall_ms=… cpu_ms=… eff_cores=… aff_cpus=… overlap_meta_ms=… overlap_fastsafe_ms=…`
- Cross-thread forensics registry (new, `comfymodal_runtime/trace.py`, module-level,
  thread-safe, JSON-safe): `register_forensic_interval(name, *, start_mono_ns,
  end_mono_ns, cpu_ms=None, metadata=None)`, `forensic_intervals()`,
  `forensic_overlap_ms(a_start, a_end, b_start, b_end)`. `RuntimeTrace` behavior
  untouched.
- No causality claim: remote A/B (`COMFYMODAL_V2_INPUT_TYPES_WARM=0` vs unset) is the
  only valid test.

## 4. Task C — full fastsafe pipeline reconciliation

`_fs_try_pipeline` stamps every boundary; all pre-existing keys kept. The 22 SERIAL
accounting phases (absolute monotonic offsets from t0):

`metrics_init`, `eligibility`, `header_config`, `parity_gate`, `target_and_mem`,
`worker_creation`, `worker_submit`, `join_delay`, `post_join_prep`, `post_load_gates`,
`transform_gate`, `bind`, `zero_copy_proof`, `mem2`, `sweep`, `final_to`, `final_sync`,
`validate`, `patcher`, `owner_attach`, `telemetry`, `return_gap`.

Plus always-on worker detail (parallel, NON-ACCOUNTING): `worker_a_start_delay_ms`,
`worker_b_start_delay_ms`, `worker_a_thread_cpu_ms`, `worker_b_thread_cpu_ms`,
`worker_a_effective_cores`, `worker_b_effective_cores`, `worker_ab_overlap_ms`,
`cpu_affinity_count` (process-wide, recorded once).

### 4.1 Accounting audit (disjointness)

Pure function `_fs_pipeline_reconcile(total_ms, accounting_intervals) -> dict` where
`accounting_intervals` = list of `(name, start_mono_ns, end_mono_ns)` absolute stamps:

```
pipeline_total_ms      = total_ms (= existing total_pipeline_wall_ms)
accounting_children_ms = Σ durations of accounting intervals
residual_ms            = pipeline_total_ms − accounting_children_ms
reconciliation_status  = "OK" if |residual_ms| < 10.0 else "GAP"
accounting_disjoint    = forensic_intervals_disjoint(intervals) result
accounting_overlap_detail = "<a> overlaps <b>" or None
```

- The 22 accounting intervals are required to be strictly disjoint (touching allowed);
  gaps land in residual. `forensic_intervals_disjoint` (trace.py) sorts by start and
  fails on any overlap.
- Parallel worker executions are nested detail INSIDE `join_delay` — recorded in the
  registry but NEVER added to `accounting_children_ms` (programmatically excluded; the
  test suite proves exclusion).
- `measured_children_ms` renamed to `accounting_children_ms` (verified no consumers).

Publication:
- New trace event `unet_fastsafetensors_reconcile` (phase="restore", success path only)
  carrying exactly: `pipeline_total_ms`, `accounting_children_ms`, `residual_ms`,
  `reconciliation_status`, `accounting_disjoint`, `accounting_overlap_detail`,
  `forensics_enabled`, `meta_worker_start_delay_ms`, `meta_worker_execution_wall_ms`,
  `meta_lifecycle_total_ms`, `meta_execution_children_ms`, `meta_execution_residual_ms`,
  `meta_lifecycle_children_ms`, `meta_lifecycle_residual_ms`, `meta_reconcile_status`,
  `meta_worker_thread_cpu_ms`, `meta_worker_effective_cores`,
  `meta_non_thread_cpu_wall_ms`, `worker_ab_overlap_ms`,
  `input_types_warm_overlap_meta_ms`, `input_types_warm_overlap_fastsafe_ms`,
  `input_types_warm_overlap_scope`.
- One console line per success:
  `[v2.fastsafe.reconcile] pipeline_total_ms=… accounting_children_ms=… residual_ms=… status=… disjoint=… meta_execution_wall_ms=… meta_execution_children_ms=… meta_execution_residual_ms=… meta_lifecycle_total_ms=… meta_lifecycle_residual_ms=… meta_status=… forensics=…`
- The existing `unet_fastsafetensors_pipeline` event keeps its contract (exactly one
  per run) and carries all always-on stamp keys.
- Failure path (`_fs_fail`) unchanged; no reconcile line/event there.

Known boundaries (documented, not defects):
- Reconcile keys are computed after the main emit; they travel via the reconcile event +
  console line, and all raw stamps remain in the pipeline event metadata for offline
  recompute.
- On the dev box only, `time.monotonic_ns()` has ~15.6 ms granularity (GetTickCount64);
  the direct-call span in `_fs_meta_construct` therefore uses `time.perf_counter_ns()`
  so sub-ms synthetic/direct measurements are honest. The pipeline path stays in the
  monotonic domain (all stamps same clock, deltas consistent; remote Linux is
  fine-grained and unaffected).

## 5. CPU terminology and deep profiler policy

- `cpu_affinity_count` = number of CPUs available to the process/thread
  (`os.sched_getaffinity` fallback `os.cpu_count()`). It is NOT "effective cores".
- `worker_effective_cores` = `worker_cpu_ms / worker_wall_ms` (None-safe).
- `time.thread_time()` measures only the calling thread; all such values are labeled
  `*_thread_cpu_ms`. `wall − thread_cpu` is published as `*_non_thread_cpu_wall_ms`
  and must NOT be interpreted as pure scheduler wait (no direct scheduler evidence).
- Deep profiler `COMFYMODAL_V2_UNET_FORENSICS`: DEFAULT OFF (`=0`/unset). Unset/`0`
  retains only low-overhead timestamp accounting. Explicit `=1` enables the intrusive
  instrumentation around `config.get_model`: per-class `nn.Module.__init__`
  aggregation, `gc.callbacks` wall, first-op proxy. The flag is read at call time
  (`_fs_forensics_enabled()`) and its state is reported in telemetry as
  `forensics_enabled` (pipeline event + reconcile event). The normal D6 run needs only
  the always-on stamps (start delay, import, context, get_model, validation, sampling,
  thread CPU/wall, effective cores, pipeline reconciliation). If coarse `get_model`
  remains ~2 s after D6, a second diagnostic run with `COMFYMODAL_V2_UNET_FORENSICS=1`
  is authorized.

## 6. Task D — correctness preservation

- Loader behavior unchanged; instrumentation is pass-through except timers.
- `COMFYMODAL_V2_UNET_FASTSAFETENSORS` gate untouched (`model_preload.py` not modified)
  — production fastsafe stays default OFF.
- Ownership retention (`_FastsafeOwner`), exact fallback (`_fs_fail` / native once),
  TWO-LANE, MutationLane, zero-copy bind (`assign=True`), native skip — all untouched.
- `COMFYMODAL_V2_INPUT_TYPES_WARM` default behavior unchanged (env unset = warm runs).
- Deep profile is thread-guarded, installed only around `config.get_model`, restored in
  `finally`, and fully try/except-wrapped.

## 7. Tests

New module `tests/test_d4_forensics_reconciliation.py` (11 tests, stdlib + torch only,
never imports comfy; synthetic fake-clock fixtures):

1. `test_meta_reconcile_nonzero_start_delay` — start_delay=15, exec wall=200, children
   sum=190, lifecycle total=215 → execution residual 10, lifecycle children 215,
   lifecycle residual 0, OK; start delay counted exactly once.
2. `test_meta_reconcile_execution_vs_lifecycle` — residual formulas; GAP at |residual| ≥ 5;
   None inputs → 0.0.
3. `test_cpu_affinity_count_positive`.
4. `test_effective_cores_calculation` — 150/300 → 0.5; all None/zero-wall cases → None.
5. `test_wall_minus_thread_cpu_terminology` — `*_thread_cpu_ms` / `*_non_thread_cpu_wall_ms`
   present; old names (`meta_wait_estimate_ms`, `meta_worker_cpu_ms`) absent.
6. `test_deep_profiler_default_off` — env unset/`0` → disabled; no `meta_module_construct_*`
   / `meta_gc_*` keys; always-on keys present.
7. `test_deep_profiler_explicit_on` — env `1` → enabled; all deep keys present.
8. `test_pipeline_accounting_disjoint_exact` — 22 intervals tiling 1000.0 exactly →
   children == total, residual 0.0 (< 10 mandatory), disjoint True.
9. `test_pipeline_accounting_overlap_detected` — overlapping intervals → disjoint False,
   detail names the pair, children ≠ total.
10. `test_pipeline_accounting_nested_contained_intervals` — worker intervals nested
    inside `join_delay` excluded from accounting children.
11. `test_forensic_intervals_disjoint_helper` — touching allowed, gaps allowed,
    overlap detected, unsorted input handled.

Local results (this revision):

| check | result |
|---|---|
| `python -m py_compile` on trace.py / unet_fastsafetensors.py / modal_app.py / d4 tests | OK |
| `python run_tests.py tests.test_d4_forensics_reconciliation` | 11/11 OK |
| `python run_tests.py tests.test_c9_fastsafetensors_integration` | 28 ran, 24 pass, 4 errors (environmental: `No module named 'comfy'` at committed `model_preload.py:13282`; comfy not installed in this dev env; pre-existing) |
| `python run_tests.py tests.test_c8_meta_native` | 10 ran, OK (3 skipped) |
| synthetic exact pipeline fixture | residual 0.0, disjoint True (section 4.1) |

## 8. Required fields

```
report path              = V2_BATCH_D4_META_AND_PIPELINE_FORENSICS_REPORT.md
meta reconciliation corrected =
                           parent/child intervals made consistent: execution wall
                           (first instruction → end) vs lifecycle total (thread creation →
                           end); meta_lifecycle_children_ms = start_delay + execution_wall
                           (start delay counted exactly once); execution children nested
                           inside execution wall, never double-counted;
                           meta_execution_children_ms / meta_execution_residual_ms /
                           meta_lifecycle_children_ms / meta_lifecycle_residual_ms /
                           meta_reconcile_status (OK <5 ms); old inconsistent keys
                           (meta_worker_total_wall_ms, meta_total_ms, meta_children_ms,
                           meta_residual_ms) removed after verifying no consumers
execution vs lifecycle metrics =
                           both intervals published and tested: direct calls to
                           _fs_meta_construct emit execution-scoped keys (lifecycle ==
                           execution when no measurable start delay); the _worker_a closure
                           overwrites with pipeline stamps incl. real
                           meta_worker_start_delay_ms and meta_lifecycle_total_ms;
                           nonzero-start-delay synthetic test proves lifecycle children =
                           delay + execution and residual 0
CPU terminology corrected  = affinity count is cpu_affinity_count (never "effective
                           cores"); effective_cores = cpu_ms / wall_ms (None-safe);
                           thread-CPU values labeled *_thread_cpu_ms;
                           wall − thread_cpu published as *_non_thread_cpu_wall_ms and NOT
                           claimed to be scheduler wait; input_types_warm publishes
                           input_types_warm_cpu_ms / _wall_ms / _effective_cores /
                           _cpu_affinity_count (plus registry + print); fastsafe workers
                           and meta worker use the same naming
deep profiler default      = COMFYMODAL_V2_UNET_FORENSICS DEFAULT OFF (unset/0); =1 enables
                           nn.Module per-class aggregation, gc.callbacks, first-op proxy;
                           flag read at call time and reported as forensics_enabled in
                           telemetry; D6 needs only always-on stamps
pipeline accounting disjoint =
                           22 serial accounting intervals recorded as absolute stamps and
                           verified disjoint via forensic_intervals_disjoint (touching
                           allowed; gaps → residual); parallel worker execution nested
                           inside join_delay is NON-ACCOUNTING and excluded (test-proven);
                           accounting_children_ms (renamed from measured_children_ms) +
                           residual_ms + reconciliation_status (OK <10 ms) + accounting_disjoint
                           + accounting_overlap_detail in unet_fastsafetensors_reconcile event
files changed              = comfymodal_runtime/unet_fastsafetensors.py (instrumentation +
                           semantics, 880 -> 1375 lines; untracked in git, pre-existing
                           state), comfymodal_runtime/trace.py (+124/-1: forensic interval
                           registry + cpu_affinity_count / effective_cores_from /
                           forensic_intervals_disjoint), comfymodal_runtime/modal_app.py
                           (input_types_warm toggle + corrected CPU keys; file also
                           carries concurrent lanes' unrelated edits),
                           tests/test_d4_forensics_reconciliation.py (new, 408 lines, 11 tests)
tests                      = d4 suite 11/11 OK; c9 28 ran / 24 pass / 4 pre-existing env
                           errors (comfy not installed); c8 10 OK (3 skipped); py_compile
                           clean on all changed files
commit                     = none
Modal requests             = 0
deploys                    = 0
READY_FOR_D6               = YES
reason = the D4 instrumentation was accepted but three measurement-semantics defects
         were corrected before D6: (1) meta reconciliation now uses consistent parent
         intervals (execution vs lifecycle) with no double-counted children and both
         published; (2) CPU values use truthful names (thread_cpu_ms, non_thread_cpu_wall_ms,
         effective_cores = cpu/wall, cpu_affinity_count) with no scheduler-wait claims;
         (3) the intrusive deep profiler defaults OFF behind COMFYMODAL_V2_UNET_FORENSICS=1
         while all low-overhead always-on stamps remain, and the pipeline accounting was
         proven disjoint (22 serial intervals, nested worker detail excluded) with a
         synthetic test suite (11/11). No behavior changed; input_types_warm toggle
         default preserved; fastsafe remains default OFF; next paid run answers the
         ~2 s meta attribution and the contention A/B with zero code edits.
```

## You asked for:
- Correct the meta reconciliation semantics (execution vs lifecycle intervals, no
  double-counted children, nonzero start-delay test) and rename misleading CPU metrics
  (thread_cpu / non_thread_cpu_wall / effective_cores / cpu_affinity_count).
- Flip the deep profiler to default OFF behind `COMFYMODAL_V2_UNET_FORENSICS=1`, report
  the flag state, and prove pipeline accounting intervals disjoint with nested worker
  detail excluded.
- Add the focused test suite, preserve all behavior, update this report with the new
  Final block and READY_FOR_D6.

## You should now manually check:
- Next remote run: `unet_fastsafetensors_reconcile` event shows `disjoint=True`,
  `forensics_enabled=False`, and plausible `meta_lifecycle_total_ms` ≈ start_delay +
  execution wall; reconcile line `status=OK` once boundaries are complete.
- `COMFYMODAL_V2_INPUT_TYPES_WARM=0` run: single `disabled` line, no warm thread, no
  `input_types_warm_ms` metadata; enabled run shows `eff_cores` ≠ `aff_cpus` (they were
  conflated before).
- `COMFYMODAL_V2_UNET_FORENSICS=1` diagnostic run: `meta_module_construct_ms_by_class`
  present, `torch.nn.Module.__init__` restored after `get_model` (no residual wrapper),
  `meta_forensics_error` absent.
- Re-run `python run_tests.py tests.test_c9_fastsafetensors_integration` once a comfy
  environment is available — expect 28/28.
- D6 decision rule: if coarse `get_model` remains ~2 s with always-on stamps only,
  authorize the single deep-forensics diagnostic run.
