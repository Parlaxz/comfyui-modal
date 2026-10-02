# RX2 Golden Sampling Full-Wall Decomposition Report

**Basis:** implementation commit `97cb9cb` (`feat: decompose Golden sampling wall`).

## Authority and boundary

The authoritative `golden_sampling` **TOTAL** is the interval from
`GoldenTelemetryRecorder.begin_stage("golden_sampling")` through its
`end_stage("golden_sampling", ...)` mark (`comfymodal_runtime/golden_serial.py:8485-8490,
8870`).  The decomposition is attached and the
`golden_sampling_decomposition` event is emitted only after that mark, and is
therefore outside TOTAL (`golden_serial.py:5189-5234, 5561-5600`).  No partial
diagnostic or historical interval is substituted for this wall.

The narrow sampler child is the actual target function call measured by
`GoldenSerialRunner.sampler_call`: entry is recorded immediately before the
sampler function, and exit after its synchronous result or awaited result
completes (`golden_serial.py:4580-4586, 4906-4945`).  Dependency resolution,
input assembly, cache insertion, and surrounding closure work are deliberately
excluded from that child.

Historical ~3.7 s intervals may be partial.  Other runs contained complete
boundaries represented in the ~4.9-5.6 s range.  These observations do not
impose a threshold and do not relabel a partial interval as complete.

## Schema and evidence

The emitted schema is `golden_sampling_decomposition_v1` (see
`golden_serial.py:5493-5534`).  Its fields are:

- **`total`** — the enclosing recorder-stage TOTAL, with monotonic clock and
  explicit outside-TOTAL attachment semantics.
- **`children`** — `pre_sampler_wrapper_setup`,
  `actual_sampler_invocation`, and
  `post_sampler_return_materialization`.  They are PARTIAL named boundaries;
  the latter two are unavailable unless the corresponding runner boundary is
  observed.
- **`partition`** — verifies the three children as a disjoint partition of
  TOTAL only when all three intervals validate inside TOTAL and their durations
  reconcile exactly.
- **`components`** — nested evidence for wrapper/setup; scheduler/sigma
  preparation; model-patcher preparation; first-step/first-use; per-step wall;
  repeated block work; attention/backend; CacheDiT; FeatureInjLatent;
  RES4LYF; CUDA waits/synchronization; and final return/materialization.
- **`host_evidence`** — derived, non-additive process/thread and memory
  observations over the deep-profile window.
- **`residual`** — the explicit unexplained remainder,
  `golden_sampling TOTAL - known verified child durations`; negative arithmetic
  is retained as invalid diagnostic evidence, never as an observed duration.
- **`semantics`** — the scope, overlap, partition, total-boundary, and
  historical-boundary rules.

When enabled, nested evidence now includes:

- actual sampler function wall (`GoldenSerialRunner.sampler_call`), wrapper and
  setup, return/materialization tail, and explicit residuals;
- per-step and per-evaluation timing, including the distinct final post-loop
  evaluation, first evaluation/first use, and later/repeated block work;
- attention dispatch/backend observations, bounded callable/native evidence,
  and CacheDiT compute/skip counters with the pinned cadence cross-check;
- allocator point counters; RSS and page-fault deltas; process and thread CPU
  time deltas; and CUDA-event elapsed evidence plus current-stream readiness.

The profile distinguishes **TOTAL**, **PARTIAL**, **DERIVED**, and
**RESIDUAL** explicitly.  Child and nested measurements are non-additive unless
the top-level three-child partition is verified.  Nested model, block,
attention, backend, allocator, host, and device evidence overlaps its parent;
it explains the wall but must not be summed with sibling spans or used to
replace TOTAL (`golden_serial.py:5509-5529`; `sampling_deep_profile.py:2569-2641`).

FeatureInjLatent is **unavailable** because there is no safe attribution seam
inside the Golden sampler boundary.  RES4LYF is **unavailable** because there
is no safe internal seam.  Both remain retained inside
`actual_sampler_invocation`; neither is fabricated as a separate duration
(`golden_serial.py:5431-5439`).

## CUDA and interpretation

CUDA event recording and `stream.query()` readiness observation are
non-synchronizing.  Span markers are recorded without realizing device work;
the terminal boundary marker is recorded after `sampling_end`.  Exactly one
`torch.cuda.synchronize()` is deferred to post-`sampling_end` diagnostic
finalization, where event `elapsed_time` values are realized
(`sampling_deep_profile.py:1240-1337, 1986-2030, 3076-3090`).  There is no
synchronization inside the sampling window.  Device elapsed and readiness are
supporting, DERIVED evidence, not host TOTAL or causal proof.

For a future slow run, distinguish real sampler slowdown from inherited CLIP or
UNET backlog by comparing, in one invocation: the authoritative TOTAL and the
actual sampler-function child; per-step/evaluation/block compute-versus-skip
and first-use evidence; attention/backend observations and CacheDiT counters;
host wall against process/thread CPU deltas; RSS, page-fault, and allocator
deltas; and CUDA marker elapsed time against current-stream readiness.  A
larger TOTAL with a correspondingly larger actual sampler child and compute
evidence supports sampler-local work; host-only gaps, first-use changes, or
CPU/memory/fault deltas point to host/setup effects; device-marker/readiness
patterns can expose queued device work.  These comparisons remain
observational: readiness covers only work visible on the current stream,
multi-stream work may be missed, and none of these fields establishes inherited
backlog or causality (`sampling_deep_profile.py:2142-2196, 2103-2140`).

## Scope and validation

No optimization behavior changed.  There were no QD, CLIP, or loader changes,
and no remote deployment or cohort was performed.  The collection is gated,
measurement-only, reversible, and preserves cleanup/restoration behavior.

Validation, exactly:

- 211 focused tests passed.
- 95 sampler contract tests passed.
- `py_compile` passed.
- `git diff --check` passed.
- Cold-path collection was blocked for this exact reason while importing
  `modal_app.py`/`comfyapp.py`:

  `RuntimeError: Local custom-node root has no syncable nodes: C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\.slim\worktrees`
