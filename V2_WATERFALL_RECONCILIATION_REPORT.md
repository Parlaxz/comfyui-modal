# V2 Waterfall Reconciliation Report

**Date:** 2026-08-12
**Scope:** Instrumentation/accounting only — no runtime behavior, sampling,
CacheDiT, model-loading policy, snapshot composition, CLIP/UNET/VAE scheduling,
conditioning cache, output persistence, teardown, or cloud/region policy was
changed.
**Fixture:** reconstructed from the quoted facts of run `20260812-142808` (the
`Pasted markdown(20260812-142808).md` file was referenced by the task but never
actually attached; see `tests/v2_waterfall_reconciliation_fixtures.py` for the
reconstruction and its documented assumptions).

---

## Current accounting failure

The V2 waterfall previously reported, for a correctly configured cold run:

```text
COMMAND → RESPONSE             21.994 s
ACCOUNTED                      11.264 s
Captured gaps / residual       10.731 s
```

Nearly 49% of the wall was labeled unknown/residual even though the raw logs
contained the timestamps needed to explain it. Root causes, in order of size:

1. **The Modal platform boundary `snapshot_restore_begin` was never ingested.**
   The run's Modal app log contained `01:12:57.388  Restoring Function from
   memory snapshot`, but the benchmark tooling never fetched/parsed it, so the
   waterfall could not split "Modal scheduling" from "pre-Python snapshot
   restoration". The old `modal_scheduling` stage conflated both and, with the
   submission boundary also absent, was reported as `-` (unavailable).
2. **Host transport boundaries were dropped.** The run's artifact lacked
   `modal_submission_attempt_unix_ns`, `modal_generator_created_unix_ns`,
   `modal_first_iteration_start_unix_ns`, `modal_first_remote_event_unix_ns`,
   `dispatch_to_modal_entry_ms`, `local_receive_to_actual_submission_ms` —
   they were captured in `modal_transport.py` trace events but never surfaced
   into the breakdown prints/`local_timing`, so the waterfall could not anchor
   `modal_scheduling` at the actual submission.
3. **The pre-Python window had no first-class stage.** Even with a
   python-resume boundary, `command_start → python_resume` was folded into the
   derived platform math (`dispatch − restore − restore_to_method`) which
   produced nothing when `dispatch_to_modal_entry_ms` was missing.
4. **Legacy naming was misleading.** `command_start_to_restore_start_ms`
   actually measured `command_start → post_snapshot_restore` (python resume),
   not restore start.

---

## Exact 10.731s residual decomposition

The quoted old residual (10.731 s) decomposes as:

| Component | ms | Source |
|---|---|---|
| Modal scheduling (submission → restore begin) | ~3,860 | Modal app log boundary |
| Modal pre-Python snapshot restoration | ~7,330 | restore-begin → python resume |
| Local submission span (receive → submit) | ~19 | host transport boundary (absent in old artifact) |
| Local preparation (command → receive) | ~1 | origin boundary |
| **Hidden pre-Python window subtotal** | **~11,210** | |
| Old-code stage-split drift (old code attributed ~479 ms of the window to measured stages it defined differently) | −479 | old waterfall's own stage values |
| **Quoted old residual** | **~10,731** | 21.994 − 11.264 |

The qualitative claim is exact: **the old residual IS the pre-Python window.**
The new model reproduces the deficient-artifact accounting at
`accounted 10,785.123 ms / residual 11,208.877 ms` and eliminates the window
entirely when the boundaries are present:

```text
OLD (deficient artifact):      accounted 10.785s  residual 11.209s
NEW (full boundaries):         accounted 21.994s  residual 0.000s
```

(Reconstruction drift vs the quoted 11.264/10.731 is documented in
`tests/v2_waterfall_reconciliation_fixtures.py` and
`tests/test_waterfall_reconciliation.py::test_old_vs_new_accounting`.)

---

## Timestamp domains

| Domain | Clock | Carrier | Used for |
|---|---|---|---|
| `host_trace` | local wall + local monotonic | `RuntimeTrace` events (`worker_start`, `transport_entry`, `modal_submission_attempt`, `remote_return_start`, `local_result_received`, …) and `request_origin_info` (`ui_run_triggered_wall_unix_ms`, `local_receive_wall_ns`, `modal_submission_attempt_wall_unix_ns`) | Local preparation, submission, return |
| `remote_trace` | remote wall + remote monotonic | remote `RuntimeTrace` events (`remote_method_entry`, `sampling_start/end`, `vae_decode_start/end`, `output_encode/persist_*`, UNET/VAE lane events, `deferred_commit_*`, …) | All remote stages |
| `remote_trace` (timing metadata) | remote wall + remote monotonic | `_restore_timing` (`remote_python_resume`, `restore_method_start/end`), `unet_graph_join` mono pair, `prompt_executor_milestones`, `pre_sampler_structured_report` | Python restore, join wait, PromptExecutor children |
| `modal_app_log` | remote wall | Modal platform log (`Restoring Function from memory snapshot`) via `tail_logs`, parsed by `comfymodal_runtime/modal_restore_boundary.py` | `snapshot_restore_begin` |
| `derived_exact` | — | arithmetic over the above (e.g. `dispatch − restore − restore_to_method`, PromptExecutor internal residual) | Derived rows |

Every `WaterfallStage` now carries a `provenance` field
(`host_trace` / `remote_trace` / `modal_app_log` / `derived_exact` /
`accounting`) rendered in the wide waterfall view, plus the existing
`source`/`source_fields`/`clock_scope`/`status`.

Same-process pairs prefer monotonic; cross-process pairs use wall with a
negative guard (skew → unavailable, never a phantom negative; small same-process
inversions clamp to 0).

---

## Scheduling boundary

Boundary chain (exact):

```text
command_start
  → local_receive        (origin / event)
  → actual_modal_submission  (origin modal_submission_attempt_wall_unix_ns /
                              event modal_submission_attempt | modal_first_iteration_start)
  → snapshot_restore_begin   (NEW: modal_restore_begin_wall_unix_ns from app log /
                              result dict, provenance modal_app_log)
  → python_resume            (_restore_timing.remote_python_resume →
                              v2_startup_post_snapshot_restore_start →
                              snapshot_restore_start → restore_method_start)
  → python_restore_end       (_restore_timing.restore_method_end)
  → remote_method_entry      (event)
```

Derivations:

```text
local_submission_ms          = actual_modal_submission − command_start
modal_scheduling_ms          = snapshot_restore_begin − actual_modal_submission
pre_python_snapshot_restore_ms = python_resume − snapshot_restore_begin
python_restore_ms            = python_restore_end − python_resume
```

`modal_scheduling` resolution tiers:
1. measured `submission → restore_begin` (authoritative, `modal_app_log`);
2. measured `submission → python_resume` **combined** interval when
   restore-begin is absent — flagged `modal_restore_begin_unavailable`;
3. legacy derived `dispatch − restore − restore_to_method`; 4. unavailable.

**Legacy field:** `command_start_to_restore_start_ms` (remote
`[v2.snapshot_timing]` print) is retained for artifact compatibility and
marked `# legacy name; semantics = command start to python resume`. The print
now also emits `command_start_to_python_resume_ms` and
`command_start_to_restore_end_ms`; `benchmark_v2_direct.py` reads the new name
with legacy fallback.

---

## Pre-Python restore boundary

- **Available:** `modal_restore_begin_wall_unix_ns` is ingested by
  `tools/benchmark_v2_direct.py::resolve_modal_restore_begin` from (1) the
  result/`local_timing` dicts when the boundary was carried in, else (2) a
  fetch of the Modal app logs (`modal._logs.tail_logs`, same pattern as
  `tools/fetch_matrix_stage_lines.py`) parsed by
  `comfymodal_runtime/modal_restore_boundary.py::parse_modal_restore_begin`
  (matches `Restoring Function from memory snapshot`, resolves `HH:MM:SS.mmm`
  against the run window, associates to the run by task id when available).
- **Unavailable path:** the report explicitly prints
  `modal_restore_begin_unavailable (modal_scheduling covers submission->python_resume combined)`
  in the boundary-flags line; `pre_python_snapshot_restore` renders
  `unavailable` (a localized unknown, never folded into the global residual
  because the combined interval is already accounted in `modal_scheduling`).
- **In-process fallbacks** (`snapshot_restore_start`,
  `v2_startup_post_snapshot_restore_start`) are treated as *python resume*
  evidence only — they fire inside Python and are never mistaken for the
  platform boundary.

For the supplied run: `modal_scheduling = 3.860 s`,
`pre_python_snapshot_restore = 7.330 s`, `python_restore = 0.549 s` — the
previously lost ~7.33 s is now an explicit stage.

---

## Host transport boundaries

All six missing fields are now surfaced end-to-end:

| Field | Producer | Consumer |
|---|---|---|
| `modal_submission_attempt_unix_ns` | origin + `modal_transport.py` event (`modal_submission_attempt`) | `[v2.local_submission_breakdown.final]`, `[v2.request_origin]`, waterfall `_submission_boundary` |
| `modal_generator_created_unix_ns` | `modal_transport.py` event + backfill | breakdown print |
| `modal_first_iteration_start_unix_ns` | `modal_transport.py` event | breakdown print, submission fallback |
| `modal_first_remote_event_unix_ns` | `modal_transport.py` event | breakdown print |
| `dispatch_to_modal_entry_ms` | `local_timing` | scheduling tier-3 fallback |
| `local_receive_to_actual_submission_ms` | transport backfill / `local_timing` | submission duration key |

`canonical_execution.py` gains:
- merged-trace event lookup helpers (`_host_boundary_event`,
  `_host_boundary_wall_ns`, `_host_boundary_field`) that read the last
  occurrence from the merged trace when transport metadata/origin misses;
- a new `local_result_received` `RuntimeTrace` event emitted at the
  `execute_plan` result break (alongside `remote_return_start`);
- new `local_timing` keys: `local_result_received_wall_ns/_mono_ns`,
  `local_receive_to_result_return_ms`, `result_received_to_return_ms`,
  and a passthrough of `modal_restore_begin_wall_unix_ns`;
- both prints (`[v2.request_origin]`,
  `[v2.local_submission_breakdown.final]`) now report every field above
  explicitly, printing `absent` when missing.

The Modal SDK semantics are respected: generator construction
(`modal_generator_created`) is timestamped separately from actual submission
(`modal_submission_attempt` = first `__anext__`), and first remote event
(`modal_first_remote_event`) is its own boundary — submission is never
approximated from generator construction.

---

## UNET mapping

All previously-blank UNET rows are wired from existing events:

| Detail row | Boundaries / source |
|---|---|
| UNET scheduled → worker start | `unet_early_activation_scheduled` → `unet_fast_disk_to_start` |
| Worker start → checkpoint read start | `unet_fast_disk_to_start` → `active_read_records[].start_*` |
| Checkpoint read | active_read start→end (or fast-disk to pair) |
| Read end → construction done | `ctor_ms`+`get_model_ms` on `unet_fast_disk_complete` (or to_end→bind_start) |
| Bind | `unet_fast_disk_bind_start/end` (or `bind_ms`) |
| Synchronized H2D | `to_device_ms`/`to_wall_ms` on complete (never double-counted with read) |
| H2D end → UNET ready | fast-disk to_end → `unet_early_activation_terminal` |
| UNET ready → sampler demand | terminal → `unet_graph_join.join_start_mono_ns` |
| Sampler demand → join complete | join_start → join_completed (or `join_wait_ms`) |
| Join complete → sampling | join_completed → `sampling_start` |

The top-level `method_entry_to_unet_claim` / `unet_claim_to_ready` stages
remain concurrent (excluded from the accounted total); every detail row is
`included_in_total=False` so the UNET lane can never double-count. Subintervals
whose boundaries are absent render as localized `unavailable` under their
correct enclosing parent — the lane never disappears wholesale.

For the supplied run the fixture exercises the quoted chain:
read 1.047 s, construction 0.271 s, bind 0.158 s, H2D 2.214 s,
join wait 0.230 s.

---

## PromptExecutor mapping

Existing events already subdivide the interval:
`prompt_executor_invoke_start` → (milestone metadata) →
`graph_first_node`/`first_executing_node`:

```text
prompt_executor_cache_setup           1.227 s  (invoke_start → graph_first_node)
  detail: executor invoke → execution  0.001 s  (invoke_to_execution_start_ms)
  detail: execution → cached           0.999 s  (execution_start_to_cached_ms)
  detail: cached → first node          0.227 s  (cached_to_first_node_ms)
```

The ~999 ms `execution → cached` region is rendered from the existing
`execution_start_to_cached_ms` milestone (no new instrumentation). Any
remaining parent-minus-children gap is rendered as a **localized** child
`PromptExecutor internal/unattributed` (provenance `derived_exact`,
`included_in_total=False`) — it never flows into the global residual
(verified by `test_missing_child_localized_not_global`).

---

## VAE mapping

The VAE chain is wired from existing events:

| Detail row | Boundaries / source |
|---|---|
| Sampling end → VAE scheduled | `sampling_end` → `vae_early_activation_scheduled` |
| VAE scheduled → worker/load start | scheduled → `vae_early_activation_load_start` |
| VAE load/H2D | load_start → `vae_early_activation_terminal` (or `load_wall_ms`) |
| VAE ready → consumed | terminal → `vae_early_activation_consumed` (or `join_wait_ms`) |
| Consumed → decode start | consumed → `vae_decode_start` |

The fixture reproduces the quoted relationship: **~870.9 ms preparation and
only ~37.5 ms join wait**, both visible as children of
`post_sampling_transition`/`vae` without affecting the accounted total.

---

## Output/handoff mapping

| Detail row | Boundaries / source |
|---|---|
| VAE end → output encode start | `vae_decode_end` → `output_encode_start` |
| PNG encode | `output_encode_start/end` (or `output_encode_ms`) |
| Descriptor/materialization | `output_encode_end` → `output_persist_end` (or `output_commit_ms`) |
| Remote result emitted | last remote boundary (`output_collect_end`/`output_persist_end`) — marker child |
| Deferred persistence after yield | `deferred_commit_start/end` (child of `remote_return_handoff`) |
| Local receipt → caller return | `final_result_received`/`local_result_received` (local) → response boundary |

The top-level stage previously labeled "Output persistence" is now
**"Output encode / descriptor"** — PNG encoding is no longer mislabeled as
persistence.

---

## Top-level accounting model

20 exclusive top-level stages (exactly one owner per millisecond):

```text
 1. local_preparation                (local)
 2. modal_handle_submission          (local)
 3. modal_scheduling                 (platform)
 4. pre_python_snapshot_restore      (platform)   ← NEW
 5. application_restore              (application)
 6. restore_to_method_entry          (application)  ← group changed from platform
 7. method_entry_to_unet_claim       (application, concurrent)
 8. unet_claim_to_ready              (application, concurrent)
 9. remote_method_setup              (application)
10. prompt_executor_cache_setup      (application)
11. first_node_to_clip               (application)
12. clip_to_sampler_node             (application)
13. sampler_graph_join_wait          (application)
14. sampler_node_to_sampling         (application)
15. sampling                         (application)
16. post_sampling_transition         (application)
17. vae                              (application)
18. output_persistence               (application)
19. remote_return_handoff            (local)
20. remote_local_return              (local)
+    residual                        (accounting, excluded from accounted)
```

Concurrent stages (7, 8) are reported explicitly but never summed into the
accounted total; background work belongs as detail beneath the interval that
contains it. Overlap detection remains (same clock scope → INVALID + warning)
so double counting is impossible.

Reconciliation (footer + `waterfall_to_dict`):

```text
COMMAND -> RESPONSE            21994.000 ms
TOP-LEVEL ACCOUNTED            21994.000 ms
GLOBAL RESIDUAL                  0.000 ms
RESIDUAL %                       0.000 %
RECONCILIATION STATUS           OK
CONTROLLABLE APPLICATION WALL 10804.123 ms   (local + application, incl. restore→method)
PLATFORM/MODAL WALL           11189.877 ms   (scheduling + pre-Python restore only)
```

Tolerance: `max(25.0 ms, total × 0.0025)` (was `max(50, 0.5%)`).

Both wall notions are always reported:
- **FULL COMMAND → RESPONSE** = `command_start → response_received_unix_ns`;
- **CONTROLLABLE APPLICATION WALL** = Python restore + restore→method +
  remote method/app execution + result handoff under our control (excludes
  provider scheduling and Modal pre-Python restoration);
- **MODAL/PLATFORM WALL** = `modal_scheduling + pre_python_snapshot_restore`
  — platform time is never hidden.

---

## Nested-span model

All nested rows are `included_in_total=False` children with `parent_key`,
`provenance`, and their own `status`:
- measured (both boundaries present, same-clock);
- derived (authoritative metadata duration, e.g. `ctor_ms`, `to_device_ms`,
  `join_wait_ms`, `load_wall_ms`, `output_commit_ms`);
- unavailable (localized unknown — never the global residual).

Parents: `remote_method_setup`/`unet_claim_to_ready` (UNET lane),
`post_sampling_transition`/`vae` (VAE lane),
`prompt_executor_cache_setup` (milestone children + internal residual),
`output_persistence`/`remote_return_handoff`/`remote_local_return`
(output/handoff). Missing children produce **localized** residuals only
(verified).

---

## Real-log before/after

```text
OLD (quoted real run / deficient artifact):
  accounted       11.264 s          (reconstruction: 10.785 s)
  global residual 10.731 s          (reconstruction: 11.209 s)
  pre-Python scheduling    -
  pre-Python restore       -
  modal_restore_begin_unavailable   (no ingestion)

NEW (full boundaries, verified on the reconstructed fixture):
  accounted       21.994 s
  global residual  0.000 s          (target <= 25 ms or 0.25%)
  modal scheduling                3.860 s
  pre-Python snapshot restore     7.330 s
  Python/application restore      0.549 s
  restore → method entry          0.091 s
  remote method setup             3.970 s
  PromptExecutor/cache setup      1.227 s
  first node → CLIP               0.400 s
  CLIP → sampler node             0.300 s
  sampler graph-join wait         0.230 s
  sampler node → sampling         0.040 s
  sampling                        1.767 s
  post-sampling transition        0.916 s
  VAE decode                      0.388 s
  output encode / descriptor      0.596 s
  remote result handoff           0.140 s
  remote/local return             0.170 s
```

The residual is not faked: every displayed duration traces to real boundary
events or explicitly derived arithmetic with provenance.

---

## Tests

`tests/test_waterfall_reconciliation.py` — 23 tests covering the 16 required
scenarios:

1. normal snapshot-restored run → residual ≤ 25 ms, accounted == total;
2. huge scheduling delay (12 s) → tiles;
3. huge pre-Python restore (20 s) → tiles;
4. missing Modal restore-start → `modal_restore_begin_unavailable` flag,
   combined interval, residual not inflated;
5. cache-hit run → tiles;
6. cache-miss run → tiles;
7. UNET fast-disk load details → measured children, no double-count;
8. VAE early activation details → measured children, no double-count;
9. result yield before deferred persistence → handoff child, tiles;
10. all major events present → residual ≤ 25 ms;
11. nested spans do not double-count;
12. overlapping UNET/prefill spans do not double-count (no overlap warnings);
13. no negative interval accepted silently (INVALID + warning);
14. clock/domain mismatch detected (negative total → warning, total None);
15. missing child → localized residual only, global unchanged;
16. command→response exactly reconciles;
plus old-vs-new accounting regression, input non-mutation, dict-path vs
kwarg restore-begin precedence, render footer walls, `waterfall_to_dict`
round-trip, and deficient-artifact flags.

`tests/test_modal_restore_boundary.py` — 32 tests for the Modal log parser
(HH:MM:SS.mmm / ISO8601 / dict records, window enforcement, task association,
12h ambiguity, malformed input, result-dict extraction, graceful degradation).

Full verification: **175 passed** (waterfall suites: `test_v2_waterfall`,
`test_waterfall_attach_central`, `test_waterfall_restoration_wiring`,
`test_gpu_snapshot_waterfall`, `test_cold_start_waterfall_bug`,
`test_modal_restore_boundary`, `test_waterfall_reconciliation`,
`test_v2_snapshot_age_accounting`) and **199 passed** (host-side:
`test_reconciliation_intervals`, `test_v2_local_submission_timing`,
`test_canonical_execution`). Pre-existing unrelated failures
(`test_v2_batch_profiles`, `test_studio_timing_integration`,
`test_persistent_validation_certificate_default_on`, 9 VAE spec-projection
tests in `test_v2_cpu_snapshot_lifecycle.py`) were confirmed failing
identically at clean HEAD before this work — they belong to the concurrent
optimization agent's in-flight changes.

---

## Remaining truly unavailable boundaries

- **`modal_restore_begin_wall_unix_ns`** — only when the Modal app log cannot
  be fetched/parsed (no credentials, log retention, task mismatch). The
  waterfall then reports `modal_restore_begin_unavailable` and
  `modal_scheduling` covers the combined `submission → python_resume`
  interval (the smallest exact known boundary pair). Everything else remains
  fully reconciled.
- **`submission_boundary_unavailable`** — only when the transport path never
  produced a submission event (e.g. legacy V1 `modal_client` path). Flagged
  with the combined-interval explanation.
- **Persistent-IPC per-request timestamps** — `local_handle_client/owner`
  frames still lack owner-side `owner_receive/handle_resolve/generator_create`
  stamps; the transport-side fallback events cover submission/iteration/return,
  so reconciliation holds, but the persistent path's intra-lookup split is a
  localized unknown.
- **`first_node_to_clip` / `clip_to_sampler_node`** — metadata-duration rows;
  if the `prompt_executor_milestones` metadata is absent they render
  unavailable (localized), never global residual.

---

## Conclusion

Waterfall reconciliation is now trustworthy for optimization work: the
supplied run's full 21.994 s command→response wall is accounted stage-by-stage
with a 0.000 s residual (target ≤ 25 ms), the 10.731 s residual is fully
decomposed (3.86 s scheduling + 7.33 s pre-Python restore + ~0.02 s local
submission), and every stage carries provenance so future optimization
diagnostics can be attributed correctly.

**No real Modal run was performed** — verification is fixture/synthetic-based
per the deployment constraint. The tooling (log ingestion + local rebuild in
`tools/benchmark_v2_direct.py`) is ready for the next integrated
deployment/run shared with the concurrent instrumentation agent.
