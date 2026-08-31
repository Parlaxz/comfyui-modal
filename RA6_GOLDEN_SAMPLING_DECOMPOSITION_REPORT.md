# RA6 Golden sampling decomposition status

## Scope and gate

RA6 is implemented as a gated, measurement-only decomposition of the existing
Golden sampling path.  The selector is `COMFYMODAL_SAMPLING_DEEP_PROFILE` and
accepts `off`, `steps`, or `blocks` (case-insensitive).  Missing and invalid
values resolve to `off`.  `off` is the canonical production default, and
`config/v2/profiles/golden_p1.toml` now explicitly selects `off`; diagnostics
must be enabled deliberately for a diagnostic run.

The existing legacy `COMFYMODAL_GOLDEN_SAMPLING_DIAGNOSTICS` path remains a
separate low-overhead compatibility diagnostic.  The deep-profile bridge is
fail-open and measurement-only: an existing production-owned profile is reused
and is never finalized a second time by Golden.

**Deployment and remote A/B are explicitly deferred until RA2B is finished and
the user resumes this lane.**  No remote execution, deployment, profiler
overhead claim, or performance result is asserted by this report.

## RA6 steering amendment: process-residency observation

### Hypothesis

The sampling decomposition should retain a cheap process-level observation of
whether host RSS and cumulative page-fault counters change between sampling
entry and actual NextDiT computation. This can indicate a possible host
residency/page-fault correlation for later investigation, but it cannot by
itself establish allocation ownership, residency causality, or GPU activity.

### Artifact fields and semantics

The gated profiler adds a separate `process_residency` section; it is not part
of the existing `allocator` snapshots:

* `entry.snapshot` is captured at `begin_sampling_profile` entry.
* `first_compute.snapshot` and `first_compute.delta_from_entry` are captured
  by the first actual NextDiT inner-block compute marker. A CacheDiT
  whole-forward skip bypasses that hook, so eval index 0 is not assumed to be
  the first compute.
* `later_compute` contains bounded records with `ordinal`, `eval_index`,
  `snapshot`, `delta_from_entry`, and `delta_from_previous_compute`.
* Each `snapshot` has `rss_bytes`, `minor_page_faults`, and
  `major_page_faults`, plus `source` and per-field `availability`. RSS uses
  `/proc/self/statm`; cumulative faults use
  `resource.getrusage(RUSAGE_SELF)`. Unsupported or failed fields remain
  `null` rather than being inferred.
* `compute_records` reports `expected_for_pinned_workflow`, `observed_count`,
  `stored_count`, `max_records`, and `overflow_count`. The bound is defensive;
  it does not redefine the explicit 17-eval / 10-compute / 7-skip contract.

The counters are observational and use no psutil, artificial page touching,
prewarming, CUDA synchronization, or per-call heavy logging. The same entry
and forward-compute observations are allowed in `steps` mode; no block/category
expansion is added there. Magnitude and causality remain unproven until a
deferred remote A/B after RA2B and explicit user resume. This amendment makes
no profiler-tax claim.

## Current implementation evidence

| Item | Current status | Evidence classification |
|---|---|---|
| Golden sampling wall | `authoritative_sampling_window_ms` is the supplied `sampling_start` to `sampling_end` monotonic interval; the enclosing Golden stage remains authoritative. | Measured when an artifact exists; boundary contract is source-derived. |
| Setup / sampler invocation | `sampler_invocation` and reconciliation `setup_ms` identify the interval to the first evaluation; `sampler_invocation_ms` aliases the enclosing wall, not a child to add to it. | Source-derived; magnitude unmeasured locally. |
| Solver/controller gaps | Each step has `pre_model_ms`, row-0-to-row-1 `gap_ms`, `post_model_ms`, and a named `solver_controller_gaps_ms` view. | Source-derived decomposition; exact ownership is bounded by callback/eval marks. |
| First and later evaluations | Every stored eval has phase, step/row, `is_first_eval`, and `is_final_post_loop_eval`. | Measured in a populated artifact. |
| Pinned cadence | Expected 17 evaluations: 16 row evaluations across 8 steps plus a distinct final post-loop evaluation. | Expected from the pinned sampler path; runtime-verifiable. |
| CacheDiT | Scalar counters are read after sampling, preferring an already loaded module. Inner block markers classify computed forwards; bypassed forwards remain skip/unknown rather than fabricated compute. | Measured when counters/hooks are available; 17/10/7 is expected, not a remote result. |
| NextDiT categories | Blocks mode aggregates attention, MLP, norm, refiner, embeddings, and output. `nextdit.non_attention_ms` is derived from compute-forward wall minus attention, not another span. | Measured for hooked modules; unhookable work is residual/derived. |
| Callback/progress bookkeeping | Callback indices and bounded monotonic timestamps are emitted. Callback-to-next-evaluation bookkeeping belongs to the next step's pre-model gap. | Measured when callbacks are present; absent callbacks are explicit. |
| Allocator/synchronization metadata | Cheap allocator snapshots are marked unsynchronized. CUDA events are optional in blocks mode; one realization sync is counted and placed after `sampling_end`. | Measured per artifact; no device-wide sync occurs inside sampling. |
| Process residency | `process_residency` records entry, first actual compute, and bounded later-compute RSS/page-fault snapshots and deltas, with source/availability and overflow metadata. | Measured when process counters are available; magnitude/causality unproven. |
| First-use/native leaf evidence | Eval 0 and first compute eval are identified. The bounded public-call observation and one-shot native profiler marker list are retained separately. | Native leaf use is measured only when markers exist; absence is unproven, not zero. |
| Cleanup | Artifact records patch, hook, backend-patch, and overall cleanup completion after restoration. | Measured by the local lifecycle. |

## Historical reuse

`SAMPLING_DEEP_DECOMPOSITION.md` is retained as historical/source-derived
design, not as a replacement implementation.  RA6 reuses its conclusions about
the `SAMPLER_SAMPLE` boundary, the RES4LYF `res_2s` two-row cadence, the
CacheDiT lightweight whole-forward skip, and the SageAttention dispatch scope.
The implementation lives in the existing
`comfymodal_runtime/sampling_deep_profile.py` lifecycle and is mirrored into
the existing Golden recorder by `golden_serial.py`; no new transport or generic
profiler system was added.

## Attention count-layer explanation

The counts are intentionally separate:

1. **Override dispatch** counts the `transformer_options` override selected by
   the active model patcher.  This says which Python dispatch route was seen.
2. **Public calls** count observable Python entry points such as SageAttention,
   Comfy Kitchen, Comfy attention, or SDPA seams.  A copied alias can be
   unobservable; that fact is emitted rather than guessed.
3. **Native first-leaf evidence** is the bounded one-shot profiler observation
   around the first requested public call.  It is evidence of native leaf names,
   not an additive call counter and not proof that missing markers did not run.

The implementation never sums these layers as if they were independent kernel
invocations.  A Sage override and an observed SDPA seam are reported as
non-correlated observations unless a trustworthy per-call relationship exists.

## Non-double-counting table

| Artifact field | Boundary/meaning | Do not add it to |
|---|---|---|
| `authoritative_sampling_window_ms` / `golden_sampling` wall | Enclosing sampling wall | `sampler_invocation_ms`, progress intervals, or child spans |
| `sampler_invocation.setup_to_first_eval_ms` | Sampling start to first eval | First-eval duration or step 0 children |
| `steps_ms[*].total_ms` | Callback/eval-derived step partition | Its `eval0`, `gap`, and `post_model` children as another total |
| `evals.per_eval[*].ms` | One eval, with final eval explicitly teardown | CacheDiT counters or block category totals |
| `nextdit.attention_ms` | Directly hooked attention category | `nextdit.non_attention_ms`; the latter is derived |
| `blocks[*].norm_ms` | Direct norm/adaLN module hooks | `norm_gate_residual_ms`; the latter is derived residual |
| `cachedit.compute_count` / `skip_count` | Scalar/cache classification counts | Any duration total |
| CUDA event totals | GPU event durations by span key | Host wall or sibling categories; event sums are not wall |
| callback timestamps | Boundary marks and bookkeeping ownership | A synthetic callback duration unless one is directly measured |
| allocator snapshots | Point observations | Allocation causality or stage duration |

Negative derived residuals remain visible as errors; they are not clamped into
an apparently valid decomposition.

## Exact future remote A/B plan (deferred)

Only after RA2B is finished and the user explicitly resumes this lane:

1. Use the existing public Golden/v2ctl control plane and an experimental app
   identity; do not use stable production.  Record the deployed source/config
   identity, provider, region, image, snapshot/container identity, workflow
   hash, model identity, seed, and requested profile level.
2. **A (canonical baseline):** `COMFYMODAL_SAMPLING_DEEP_PROFILE=off`.
   **B (diagnostic decomposition):** same deployment contract and workflow with
   `COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`.  `steps` is a local lower-detail
   calibration mode, not a substitute for B.
3. Run one request per experiment invocation, with the same fresh/single-use
   contract and the same output SHA gate.  Collect five valid A requests and
   five valid B requests only after structural validity is confirmed; retain
   failures, invalid attempts, and outliers rather than selecting by file mtime.
4. Compare the authoritative `golden_sampling` wall and durable-result wall.
   Treat B's post-`sampling_end` diagnostic cleanup and its one optional CUDA
   realization as diagnostic cost outside the sampling wall.  Do not infer or
   claim profiler overhead from this plan before measuring it.
5. Reconcile B artifacts: 17 evals, final post-loop eval distinct, CacheDiT
   counters when discoverable, callback coverage, category/residual arithmetic,
   native-leaf evidence status, and complete cleanup.  A/B is not accepted on a
   successful process exit alone; output/hash/durability and artifact identity
   must all be valid.

This plan is intentionally a future operating procedure, not evidence that the
remote A/B has happened.

RA6_IMPLEMENTATION_COMPLETE=YES
PROFILER_OFF_STEPS_BLOCKS_SELECTABLE=YES
PROFILER_TAX=UNPROVEN
FIRST_EVAL_SEPARATE=YES
CACHE_DIT_COMPUTE_SKIP_SEPARATE=YES
ATTENTION_VS_NON_ATTENTION_SEPARATE=YES
SOLVER_OVERHEAD_SEPARATE=YES
POST_LOOP_WORK_SEPARATE=YES
NO_DEVICE_WIDE_SYNC_ADDED=YES
READY_FOR_REMOTE_VALIDATION=YES
REPORT=RA6_GOLDEN_SAMPLING_DECOMPOSITION_REPORT.md
