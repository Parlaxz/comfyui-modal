# RX6 — Golden Log Cleanup and Post-Result Tail Report

Date: 2026-08-31  
Implementation commit: `fdcb1be`  
Integration: `INTEGRATED=NO`

## Scope

RX6 investigated the output after the authoritative Golden execution report
and removed only duplicate or unnecessary Golden-path logging. The runtime
changes are in `fdcb1be`; this document records the source trace and evidence
without changing runtime behavior.

The completed implementation does not alter QD transport, sampler behavior,
CLIP residency, model loading, performance algorithms, stage timing
boundaries, `FIRST_RESULT_READY`, or output durability.

## Output sequence and ownership

### 1. Authoritative Golden waterfall

The first banner in the supplied run, `V2 GOLDEN WATERFALL - REMOTE`, is the
authoritative Golden report format produced by
`comfymodal_runtime/modal_app.py:_format_golden_waterfall()` (the banner is
constructed at line 1459 in the RX6 worktree). Before RX6, the Golden adapter
emitted it through `_emit_golden_telemetry()` together with the detailed
console dump. The Golden adapter
`run_golden_serial_stream()` owns the direct Golden request and deliberately
bypasses the generic `ExecutionPlan` and prompt-executor path.

`golden_serial_execute()` records the serial stage intervals and calls the
recorder's final persistence path after Golden teardown. The persisted
document contains the schema, restore metadata, stage intervals, events,
identity, seriality evidence, diagnostics, and persistence status.

### 2. The large `[v2.golden_telemetry]` block

Before RX6, `run_golden_serial_stream()` reread the already-persisted Golden
telemetry and called `_emit_golden_telemetry()` on both success and error
paths. `_emit_golden_telemetry()` first reprinted the Golden waterfall and then
printed one summary line plus the stage and event records. Its output was
flushed, readable, sanitized, and bounded by the formatter, but it was still a
console rendering of the persisted document.

Classification:

- **Required forensic raw telemetry:** yes, the underlying persisted document
  and its complete stage/event data remain required evidence.
- **Redundant console duplication:** yes, the large console block was a
  duplicate reread, not the telemetry source of truth.
- **Diagnostic/evidence data:** yes, the telemetry is used to inspect,
  validate, reconcile, and project Golden runs.
- **Correctness-critical console output:** no. Golden execution and result
  correctness do not depend on printing this block.

The Golden recorder still atomically writes the telemetry JSON. The adapter
still places the same mapping under `golden_telemetry` on the terminal result
or error event. Benchmark artifact extraction and Golden observability tools
still consume that terminal/artifact surface, and the known telemetry path
still exists. RX6 removed the adapter's `_emit_golden_telemetry()` calls, not
the persisted telemetry or its payload propagation. The formatter and emitter
remain available for direct diagnostic/unit use.

Because `_emit_golden_telemetry()` printed both the formatted banner and the
detailed block, the exact `fdcb1be` diff suppresses the adapter's console
rendering of the first banner as well as the duplicate detail lines. The
authoritative Golden waterfall remains available through the persisted
telemetry document and terminal/artifact payload; the direct formatter tests
still cover its format. This report records that distinction explicitly: the
first report is authoritative data, while its old console rendering was
coupled to the redundant dump in the removed emitter.

## Second `V2 COLD WATERFALL - REMOTE/PARTIAL`

### Exact source and call path

The banner is emitted by:

1. `comfymodal_runtime/v2_waterfall.py:_render_partial()` — banner at line
   2646;
2. `render_waterfall()` — selects `_render_partial()` when
   `partial_waterfall` is true;
3. `attach_waterfall()` — attaches the structured report and, by default,
   prints it;
4. `__init__.py:_on_remote_event()` — the experiment-cell materialization
   fallback calls `attach_waterfall(result_data,
   run_label="experiment cell materialize")` around lines 5759–5769.

That fallback exists for an upstream client that bypasses the normal wrapper:
it ensures a graph-like result retains a waterfall in durable experiment
history. A Golden terminal payload is graph-like to the generic predicate
because the adapter projects its in-memory output into `images` and carries
other result data. The fallback therefore tried to build a generic V2
waterfall for a Golden result that was already fully described by the
authoritative Golden telemetry.

The generic waterfall builder needs host-side boundary stamps such as
submission, Modal restore-begin, and local result receipt. The Golden result
does not carry those generic host/transport boundaries, so the builder marked
the report partial with:

```text
missing_submission,missing_modal_restore_begin,missing_local_result_receipt
```

That produced an empty/PENDING remote table: the report was a host
reconciliation placeholder, not a second execution or a second Golden
measurement.

RX6 keeps the fallback's structured report attachment and its copy into the
durable payload/history, but passes `print_render=False` when the result has a
Golden telemetry or Golden identity marker. Generic and non-Golden fallback
calls remain print-enabled. The generic cold-start diagnostic infrastructure,
including legitimate `V2 COLD WATERFALL - REMOTE/PARTIAL` reports, remains
unchanged.

## Final conditioning-cache mode line

### Exact source and old caller

The line

```text
[v2.clip_conditioning_cache] event=mode flag=COMFYMODAL_V2_CLIP_CONDITIONING_CACHE enabled=1 ...
```

is printed by `comfymodal_runtime/clip_conditioning_cache.py:_log_once()` at
the `print(..., flush=True)` call around line 205. The enabled mode line is
reached in `get_exact_conditioning_cache()` after constructing the singleton,
registering its commit hook, and calling `_log_once()` around line 2926.

The late caller was `ModalRuntimeEntrypoint.exit()` in
`comfymodal_runtime/modal_app.py`. Its `conditioning_cache_flush` teardown
stage previously called `get_exact_conditioning_cache()` before flushing the
service. On a Golden request that never used the generic conditioning-cache
path, this shutdown-only call resolved environment settings, constructed the
cache, registered the hook, and emitted the first mode line merely because
exit wanted to flush a cache that did not exist.

RX6 adds `peek_exact_conditioning_cache()`. It returns the already-resolved
singleton, or `None`, without environment resolution, construction,
commit-hook registration, or logging. The exit hook now uses this accessor.
If a generic request has already resolved and used the cache, its existing
service is still flushed with the same bounded timeout. The conditioning cache
itself remains enabled and functional.

## The approximately 1.7-second post-result tail

The final cache line was not the source of the full gap. The lifecycle is:

1. Golden finishes its own serial stages, teardown, telemetry persistence, and
   adapter result assembly.
2. Before RX6, the adapter emitted the first Golden waterfall and the large
   persisted-telemetry console duplicate from the same emitter. In the
   `fdcb1be` implementation, neither console rendering is emitted by the
   adapter; the report and telemetry remain in the result/artifact surfaces.
3. The experiment-cell materializer can run its generic fallback, which before
   RX6 printed the second partial waterfall while retaining the structured
   report.
4. The Modal container reaches the `@modal.exit` lifecycle event after the
   result has been delivered.
5. The exit hook runs its teardown stages:
   - request sampler stops;
   - preload-worker close/join;
   - lingering non-daemon preload-thread sweep;
   - full-trace service shutdown;
   - legacy request-worker joins;
   - the old conditioning-cache flush stage.
6. In the old path, that final stage lazily initialized the unused cache and
   printed the mode line.

The teardown stages are real shutdown/finalizer work, including bounded
background-thread joins. They are not hidden model execution, sampler work,
QD work, or a moved timing boundary. The mode line itself uses flushed output,
so the line is not explained by ordinary buffered logging. The cache
initialization was unnecessary for a Golden request that never resolved the
cache; the underlying teardown wall was not necessarily unnecessary.

RX6 removes the late cache construction/logging and the duplicate output
renders. It does **not** claim that removing the final line eliminates the
entire teardown wall. The wall occurs after `FIRST_RESULT_READY` and therefore
does not change the Golden result-ready measurement, but it can still matter
for billable container lifetime and shutdown cost. Teardown diagnostics retain
`exit_hook_start` and per-stage `cleanup_stage_start`/`cleanup_stage_end`
boundaries for a run where those diagnostics are enabled; those are the
appropriate evidence for assigning exact milliseconds among the shutdown
stages rather than treating the final log timestamp as the tail duration.

## RX6 changes

- Removed Golden adapter calls that printed the persisted telemetry document
  on success and error.
- Suppressed only the Golden duplicate render in the experiment-cell
  materialization fallback; preserved its internal waterfall payload.
- Replaced exit-time cache initialization with a non-initializing cache peek.
- Added focused tests for telemetry preservation, output suppression, Golden
  waterfall routing, cache peeking, and existing-cache flushing.

## Validation

Results recorded for the RX6 implementation commit:

- Golden adapter tests: **28 passed**.
- Golden acceptance/observability tests: **45 passed**.
- Waterfall/cold tests: **95 passed**.
- Conditioning nonce tests: **23 passed**.
- Conditioning prefetch tests: **45 passed**.
- Python compile checks: **passed**.
- `git diff --check`: **passed**.

Known unrelated validation limitations:

- The broader legacy wiring suite had two failures in pre-existing
  `studio_run_adapter` source assertions; they were unrelated to RX6.
- The broader cache telemetry suite timed out during local validation; no RX6
  failure was reported from it.

The report commit is docs-only. `INTEGRATED=NO`.
