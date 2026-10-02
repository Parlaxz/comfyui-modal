# RX3 CLIP Forward Deep Decomposition

Date: 2026-08-31  
Implementation commit: `85dc140bb5c839b919f92bf87c7ecc3e9daa4436`  
Integration: `INTEGRATED=NO`

## Scope

RX3 adds diagnostic-only decomposition to the authoritative Golden Serial
`golden_clip_forward` path. It does not alter CLIP execution semantics, QD,
sampler behavior, Modal cohorts, or optimization policy. No cast-once conclusion
was made.

## Authoritative TOTAL wall

The authoritative boundary remains the `GoldenTelemetryRecorder` interval:

```text
actual golden_clip_forward entry (begin_stage)
  -> runner setup and conditioning/token preparation
  -> actual Qwen encode/forward
  -> output extraction and readiness/storage rechecks
  -> return or raise (end_stage/fail_stage)
```

The decomposition is attached after the stage is closed and reads the exact
recorder interval's entry and end monotonic timestamps. Its
`authoritative_total.status` is `TOTAL`, and `duration_ns` is that complete
stage wall. Attachment and event publication are outside the measured stage
and cannot replace or extend that TOTAL boundary.

## Decomposition map

### Inclusive host spans

`_ClipTiming` records `perf_counter_ns` host spans for the named phases:

- `clip_forward_entry_setup`
- `clip_tokenization_input_prep`
- `clip_graph_node_wrapper`
- `clip_qwen_transformer_encode`
- `clip_qwen_transformer_forward`
- `clip_post_forward_sync_wait`
- `clip_conditioning_packaging`

These values are exposed as `phase_host_inclusive_durations_ns`. They retain
their original phase names and are explicitly `host_observed_inclusive`, not
exclusive category totals. In particular, graph-wrapper and encode spans can
contain nested work and must not be summed as independent portions of TOTAL.

### Qwen module classification

During one diagnostic forward, bounded pre/post hooks classify structurally
named modules into:

- Qwen transformer root;
- embedding;
- transformer layer or other repeated block;
- attention;
- MLP/feed-forward;
- normalization/RMSNorm/LayerNorm;
- projection/output head.

Each bounded record includes the qualified module name, class, category,
optional layer index/group, host start/end, duration, and inclusive boundary
kind. The catalog and records are capped at 256 entries each and report
truncation rather than silently presenting an incomplete account.

### First layer versus steady state

Layer indices are classified as `first_layer` for index 0 and
`steady_state_layers` for later indices. The payload reports record counts and
inclusive host duration for both groups, in addition to the individual module
records. This distinguishes first-layer behavior without treating nested module
durations as additive transformer time.

### Actual transformer and conversion

The existing Qwen-forward evidence remains the authoritative signal that a real
transformer forward was observed. RX3 reports its forward count, aggregate host
duration, and host-observed-only completion status. Existing forward conversion
instrumentation is passed through as
`parameter_materialization_conversion`; when active it is `PARTIAL` evidence,
not a complete wall attribution or a cast-once result.

### Readiness, storage, and page faults

The existing readiness snapshots are preserved at `before_forward`,
`after_tokenization`, and `after_encode`. The decomposition reports these as
`readiness_storage_rechecks` with `PARTIAL` status. Storage/materialization is
left `UNPROVEN` unless the existing snapshots establish it.

Process page-fault deltas remain emitted through the existing
`clip_page_faults` diagnostic event and stage data. They are evidence for host
page activity only; they are not direct proof of GPU memory pressure.

### Synchronization, postprocessing, and residual

The existing required runner quiescence check is represented by the
`clip_post_forward_sync_wait` host span. Conditioning extraction/packaging is
represented by `clip_conditioning_packaging`.

Reconciliation computes the union of observed `level=parent` spans and reports
`unaccounted_after_parent_spans_ns` as:

```text
authoritative TOTAL - observed parent-span union
```

This reconciliation is `PARTIAL`; inner module and phase spans are inclusive,
overlapping, and non-additive. The unaccounted value is not a complete causal
residual. It can include nested setup, unhooked work, manager/patcher activity,
waits, and any other work not directly observed by the selected spans.

## Diagnostic safety

- The decomposition is enabled only when the existing stage diagnostics gate is
  enabled.
- The disabled path does not inspect module structure, install hooks, create
  CUDA events, or emit decomposition telemetry.
- Hooks are installed only around the one diagnostic forward and removed in a
  `finally` block, including exception paths. Removal errors are recorded as
  diagnostic errors without changing the original result.
- RX3 introduced no device-wide synchronization and no per-layer or per-call
  synchronization. It adds no per-module CUDA timing. Existing required
  post-forward completion/quiescence behavior is unchanged.

## Unresolved seams

The following remain explicitly unproven:

- dedicated model-manager/patcher activity timing;
- first-use CUDA/kernel/library initialization;
- CUDA-complete timing for individual modules;
- full parameter/storage materialization proof beyond existing snapshots;
- direct GPU-memory-pressure attribution;
- a definitive slow-run dominance conclusion among transformer compute,
  conversion/casting, first-use setup, hidden synchronization/backlog,
  memory pressure, instrumentation, or another deterministic residual.

Those seams require appropriate runtime evidence. RX3 instrumentation alone does
not turn an unobserved category into a conclusion.

## Validation

- RX3 tests: **9 passed**
- CLIP/Golden regression subset: **213 passed**
- Python compilation: **passed**
- `git diff --check`: **passed**

The sparse RX3 worktree retains an unrelated unstaged `__init__.py` deletion
artifact. It was not staged or committed.
