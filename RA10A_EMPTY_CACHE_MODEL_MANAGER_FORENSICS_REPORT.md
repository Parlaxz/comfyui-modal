# RA10A — `empty_cache` / Model-Manager / Unload Forensics Report

> **SUPERSESSION NOTICE (2026-08-30):** Historical Golden lifecycle forensics;
> preserve its evidence, but use
> `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current generated-output
> semantics. Output durability is off by default; strict commit/reopen/hash
> proof is opt-in. S4 source publication durability remains mandatory.

## 1. Scope, method, and evidence limits

This is a read-only forensic report for the current Golden lifecycle.  It
covers `torch.cuda.empty_cache`, allocator cleanup, model unload/offload,
ComfyUI model-management hooks, QD owner lifetime, and the ordering of those
operations relative to output durability and return.  S4/publication code is
out of scope.  No Modal deployment, Modal request, or deployment mutation was
performed.

The strict reference is `comfymodal_runtime/golden_serial.py:6673-6868`.
Exact source reads were used for the material boundaries and the supplied
historical reports were treated as evidence, not as implementation claims.
The existing dirty worktree was preserved.  The sole permitted write is this
new report.

Evidence limits:

* The code index was full-mode, generation `2026-08-20`, but requested files
  are reported as `metadata_changed`/`not_tracked`; the E28 report was skipped
  at parse time because of a timeout.  Native source reads are therefore the
  ground truth for this report.  Graph results must not be treated as a
  completeness proof.
* The authoritative count below is a search count of invocation-like Python
  lines.  It includes definitions, tests, diagnostic wrappers, related
  `soft_empty_cache` matches, and non-canonical runtime paths.  It is not a
  count of unique native CUDA calls.
* Physical free VRAM, Torch `allocated`, Torch `reserved`, model-manager
  loaded-model state, and QD staging are different measurements.  A statement
  about one is not silently promoted to a statement about another.
* Historical timing is reported only where the supplied artifacts give a
  timing.  D18/E27, D14, RA8, and the four-thread artifact do not establish a
  universal causal model for every current path.

### Terminology and strict `empty_cache` semantics

`torch.cuda.empty_cache()` does not free live tensors.  It returns unused
cached allocator blocks/segments to the CUDA allocator/driver; it can reduce
Torch `memory_reserved()` while leaving `memory_allocated()` unchanged.  It
does not, by itself, unload a `ModelPatcher`, detach a model, release a QD
backing owner, or move weights between CPU and GPU.  Python references and
storage ownership determine whether model-sized allocations remain live.

On the pinned ComfyUI path, `soft_empty_cache` is a heavier generic wrapper:

```text
torch.cuda.synchronize()
torch.cuda.empty_cache()
torch.cuda.ipc_collect()
```

The wrapper has no VAE-specific or nonblocking variant; its `force` parameter
is unused by the CUDA body.  `free_memory` may first unload eligible models,
then call `soft_empty_cache`, or may soft-empty based on an allocator/free
portion threshold even when no model is unloaded.

The relevant state classes are:

| State | Meaning | What can reclaim it |
|---|---|---|
| `allocated` | Bytes held by live Torch tensors | Tensor/reference/storage lifetime; not `empty_cache` alone |
| `reserved` | Allocator segments held for reuse, including inactive blocks | `empty_cache`/soft-empty may return unused portions |
| Model storage | Live CLIP/UNET/VAE parameters and adopted backing buffers | Detach/unload and owner release, only after all views are dead |
| Temporary staging | QD pinned slots and transient host/device transport resources | Owner `release_staging`/close after transport quiescence |
| Reusable cached blocks | Unused allocator capacity retained for later allocations | Reuse is cheap; flush returns it but can impose allocator work |

## 2. Executive conclusion

The strict canonical Golden executor reaches zero `empty_cache` calls and zero
model-manager unloads on its reachable path.  Its teardown intentionally
releases only QD staging, checks worker quiescence/seriality, and leaves model
and CUDA reclamation to process exit.  Its explicit contract forbids full
unload, model-sized CPU/GPU transfer, broad GC, `empty_cache`, and allocator
purge (`golden_serial.py:6683-6687`); the forbidden-call test is at
`tests/test_p1_golden_serial.py:199-210`.

The optional V2 request release path is materially different.  When
`COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST` is enabled and teardown is full, it
can scan and unload all models, temporarily force patcher offload devices to
CPU, fall back to `free_memory(1e30, device, keep_loaded=[])`, call
`cleanup_models`, reset the legacy executor, run `gc.collect`, synchronize,
and call `empty_cache` (`modal_app.py:6801-6937`).  Full teardown is a
reusable-container policy, not the strict single-use Golden contract.

The strongest waste signal is not “`empty_cache` is always unnecessary.”  It
is narrower: historical D18 runs paid 739.241–950.460 ms for allocator cache
reclamation while allocated bytes and model-unload count stayed unchanged,
despite approximately 80 GB physical free and a VAE requirement of about
1.46 GB.  D18 also says redundancy of sync, empty-cache, and IPC remains
unknown without the missing sampling-end snapshot.  E28 is a different path
and reports 0.3–2.2 ms with exactness passing.  The evidence therefore
supports seven bounded experiments, not an unconditional removal.

The only identified pre-durable ordering defect is in the legacy stream:
output write starts an asynchronous commit, terminal cleanup/unload runs, and
the result is yielded before the deferred commit is finalized.  Strict Golden
awaits commit, reopen/stat/read/hash verification, true-durable marking, and
result assembly before teardown.

## 3. Exact strict-Golden timeline

The top-level call sequence is literal at `golden_serial.py:6811-6829` and
the success return is after teardown and final telemetry persistence at
`golden_serial.py:6840-6868`.

| # | Stage and source | Allocator mutation | Unload/offload | `empty_cache` / GC | Synchronization | Model-manager scan | Memory-stat query | Reachable in strict Golden? | Likely block state on return |
|---:|---|---|---|---|---|---|---|---|---|
| 1 | Restore; host/restore paths `canonical_execution.py:1741-2527`, `model_preload.py:11489-12000`, `12070-12295` | May schedule/perform CLIP, UNET, and policy-dependent VAE construction/activation; mutation lane serializes GPU/cache mutations | No generic unload; bridge returns matching prepared objects or falls back to native loader methods on mismatch | No canonical cleanup | Restore/loader-local waits; no canonical device-wide cleanup sync | No canonical manager scan | Restore diagnostics may query CUDA stats | Yes, as restore stage; zero canonical `empty_cache` | Model buffers and any retained QD-backed storage required for the next stage remain live; unused allocator blocks may remain reserved |
| 2 | Request setup | Workflow/request bookkeeping; no declared model-sized allocation | None | None | No cleanup sync | None | Instrumentation only if a setup helper asks | Yes | Same as restore, plus request-local references |
| 3 | CLIP load | Loader allocates/adopts CLIP storage; direct paths use `assign=True`/QD ownership where proven | No unload; failed loader paths may close owners | Failure cleanup only in non-canonical helper paths | Loader may use scoped QD event or loader-local CUDA sync | Native fallback may invoke manager indirectly; not canonical executor-owned cleanup | Loader diagnostics can reset/read peak stats | Yes | CLIP model storage live; unused staging/cache may be retained |
| 4 | CLIP forward | Temporary activations/workspace may allocate and later become reusable cache | None | No canonical flush | Forward's own framework synchronization only as required | None | No canonical manager scan | Yes | Live output/conditioning tensors remain; dead forward workspace can become cached reserved blocks |
| 5 | UNET load | Direct GPU/QD load adopts views over a GPU buffer; allocation checkpoints read allocated/reserved | No unload | No canonical flush | `golden_serial.py:5252-5277` checkpoint helper can synchronize before instrumentation; this is not cleanup | None | `memory_allocated`, `memory_reserved`, and peak stats are instrumentation | Yes | UNET backing storage is live; QD pinned staging remains owner-held until teardown |
| 6 | Sampler prepare | Small graph/sampler state and possible temporary buffers | None | None | Stage-local preparation only | None | No cleanup stats | Yes | Reusable allocator blocks may accumulate; model storage remains live |
| 7 | VAE load | VAE storage/activation may allocate; QD owner can hold a further staging allocation | No generic unload | No canonical flush | Stage-local loader/event waits only | None | No canonical manager scan | Yes | VAE model and adopted storage live; earlier blocks may be reserved for reuse |
| 8 | Sampling | Sampling workspaces/attention scratch allocate; dead scratch can become inactive reserved blocks | None | No `empty_cache`; no model unload | QD/event joins are stage-local. There is no explicit device-wide sync in the strict Golden stage boundary | None | Runtime V2 sampler diagnostics may read allocated/reserved at `runtime_executor.py:4469-4477`, but that is observation | Yes | UNET/VAE/CLIP live as needed; sampling scratch is potentially cached, not live |
| 9 | Sampler tail; `golden_serial.py:5809-5832` | Bounded bookkeeping only | None | Explicitly no full GC, model unload, `torch.cuda.empty_cache`, or allocator purge | No broad sync | None | None | Yes | Same live model state; temporary tail objects are only ordinary references |
| 10 | VAE decode | Decode activations/output tensors allocate; scratch becomes reusable when dead | None | No canonical flush | Decode-local waits only | None | No canonical cleanup stats | Yes | Decode output remains live until output handling; dead decode scratch may be reserved |
| 11 | Output | Encoding/descriptor/host output work; output tensors may be copied/serialized | None | None | No cleanup sync | None | No canonical manager scan | Yes | Output bytes and durability record remain live/host-owned; allocator cache is unchanged by policy |
| 12 | Durable commit; `golden_serial.py:6822-6827` | No model allocator mutation expected | None | None | Blocking/awaited Volume commit and reopen verification, not CUDA cleanup | None | No allocator flush | Yes | Model/cache state is still intact while durability is proven |
| 13 | `mark_true_durable`; line 6828 | Recorder event only | None | None | None | None | None | Yes | No allocator change; durable marker is now justified |
| 14 | Result assembly; lines 6829-6830 | Result metadata only | None | None | None | None | None | Yes | No allocator change; result is assembled before teardown |
| 15 | Teardown; `golden_serial.py:6673-6736` | Releases `release_staging()` for session owners and all CLIP owners; does not release adopted backing storage | No full unload, no model-sized transfer; UNET QD CUDA buffer remains backing live weights | No broad GC, no `empty_cache`, no allocator purge | Worker/runner quiescence and seriality checks; QD joins are not a device-wide cleanup sync | None | Substage timing only | Yes | Model-sized live storage and reserved blocks remain until process exit; QD staging slots are released |
| 16 | `TEARDOWN_COMPLETE`; line 6848 | Recorder event only | None | None | None | None | None | Yes | Same process-lifetime model/cache state |
| 17 | Final telemetry persistence; lines 6742-6758, 6850-6859 | File/volume telemetry write only | None | None | No CUDA cleanup | None | None | Yes | Process still owns model/CUDA state until exit; result return follows at 6868 |

**Instrumentation distinction.**  Golden uses allocator statistics and peak
reset/read helpers at `golden_serial.py:2540-2554`, `5247`, `5281`, `5818`,
`6684`, and memory stats at `984-986`.  These are observations or measurement
bookkeeping, not allocator purges.  The `5818` occurrence is an explicit
negative contract in a docstring; it is not a call.  No strict canonical
device-wide sync is introduced merely to make teardown safe.

## 4. Complete occurrence inventory

The requested labels are used below.  Some source lanes have historically
used different letter names; they are normalized to A–G here.  A direct
`empty_cache` occurrence in an error/fallback helper is not evidence that the
helper is reachable from the strict Golden executor.

### A. Canonical

* `comfymodal_runtime/golden_serial.py:6673-6736`: `golden_teardown`; only
  releases QD staging and checks runner/thread quiescence and seriality.
  Lines `6683-6687` explicitly forbid full unload, model-sized transfer,
  broad GC, `empty_cache`, and allocator purge.
* `comfymodal_runtime/golden_serial.py:6764-6868`: the strict executor's
  order is restore, setup, CLIP load/forward, UNET load, sampler prepare,
  VAE load, sampling, tail, decode, output, durable commit, durable marker,
  result assembly, teardown, `TEARDOWN_COMPLETE`, final telemetry.
* `tests/test_p1_golden_serial.py:199-210`: AST contract forbids `collect`,
  `empty_cache`, `unload_all_models`, `purge_allocator`,
  `empty_cuda_cache`, and `release_storage` inside `golden_teardown`.
* `golden_serial.py:2540-2554`, `5247`, `5281`, `5818`, `6684`, and
  `984-986`: allocation/peak/stat instrumentation or negative text only.
  No canonical `torch.cuda.empty_cache()` call is reachable: **0**.

### B. Restore

These are restore/loader cleanup or readiness seams, not calls made by the
strict executor's teardown:

* `comfymodal_runtime/canonical_execution.py:1741-2527`: host restore,
  restore publication/submission, and result receipt boundary; no direct
  canonical `empty_cache` call.
* `comfymodal_runtime/model_preload.py:11489-12000`: restore coordinator
  submits physical reads/CPU construction and serializes GPU/cache mutation
  through `mutation_lane`.
* `model_preload.py:12070-12295`: `V2LoaderBridge` wraps real UNET/CLIP/VAE
  loader and encode/decode methods; mismatch/failure falls back to native
  methods.
* `model_preload.py:1066-1075` (call `1073`): C6 ring cleanup deletes
  destination/pinned-buffer references and defensively empties the cache.
* `model_preload.py:1741-1771` (calls `1753`, `1769`): ring final cleanup
  drops pin slots/destinations; fallback helper empties the cache.
* `model_preload.py:5228-5237` (call `5235`): C6 micro-finalizer drops a
  destination reference and empties the cache.
* `clip_fast_hydration.py:465`: resets peak stats for a CUDA baseline;
  this is not `empty_cache`.
* `clip_fast_hydration.py:528`, `562`, `651`, `715`: loader-local
  synchronization/readiness and peak/stat measurement; no cache flush.
* `clip_fast_hydration_wiring.py:167`: owner cleanup requests
  `purge_allocator=False`, preferring storage release without a purge.
* `clip_fast_hydration_wiring.py:503`: peak/stat baseline, not a flush.
* `clip_fast_hydration_wiring.py:1725`: non-scoped CLIP bind completion uses
  a device-wide sync; it is a loader readiness boundary, not cache cleanup.
* `clip_fast_hydration_wiring.py:2020-2024` (call `2022`): error cleanup
  closes source owners and defensively empties the cache.
* `clip_qd_reader.py:1380-1414` (call `1408`): `purge_allocator()` first
  releases backing storage, then calls `torch.cuda.empty_cache()` unless the
  clean lane forbids allocator purge.
* `clip_qd_reader.py:1889-1894`: wrapper delegates `release_storage` and
  explicit `purge_allocator` to its owner; this is an API seam, not proof of
  use in Golden.

### C. Teardown

* `comfymodal_runtime/modal_app.py:6571-6959`: optional request GPU release.
  Reference/bookkeeping stages always run when enabled.  Full mode can run
  model-manager unload, fallback device freeing, manager cleanup, executor
  reset, GC, and CUDA cleanup; minimal mode skips those heavy stages.
* `modal_app.py:6801-6852`: dynamically obtains
  `getattr(model_management, "unload_all_models", None)`, temporarily changes
  each loaded patcher's `offload_device` to CPU, calls unload, and restores
  the original value.  This avoids detach moving weights back to CUDA.
* `modal_app.py:6857-6878`: dynamic `free_memory`/device fallback with
  `free_memory(1e30, device, keep_loaded=[])` when unload is unavailable or
  fails.
* `modal_app.py:6885-6894`: dynamic `cleanup_models()` after the unload/fallback
  branch.
* `modal_app.py:6896-6913`: optional legacy executor reset and `gc.collect()`.
* `modal_app.py:6915-6937`: if CUDA was initialized, `cuda.synchronize()`
  followed by `cuda.empty_cache()`; no `ipc_collect` is added by this V2
  release helper.
* `modal_app.py:7388-7390`: shutdown/legacy cleanup obtains and calls
  `cleanup_models` after CPU-device `free_memory` handling at `7387`.
* `comfymodal_runtime/clip_qd_reader.py:1401-1410`: explicit owner purge
  seam; successful strict Golden teardown uses `release_staging`, not this
  backing-storage purge.

### D. Fallback/error

* `clip_fast_hydration.py:677-683` (call `682`): failed fast-safetensors
  hydration closes the loader and empties the cache before re-raising.
* `clip_fast_hydration_wiring.py:2004-2024` (call `2022`): failed bind path
  closes source owners and empties the cache.
* `model_preload.py:1066-1075`, `1741-1771`, `5228-5237`: ring/micro
  finalizers use best-effort cache cleanup after releasing temporary
  destinations/pinned buffers.
* `speculative_clip_hydration.py:838-854` (call `852`): failed speculative
  read closes loader owners and empties the cache unless the clean lane is
  enabled.
* `speculative_clip_hydration.py:995-1011` (call `1008`): closing an
  unconsumed speculative CLIP lane closes owners and empties the cache.
* `comfymodal_runtime/unet_salvage_probe.py:413-417`: helper wraps
  `torch_module.cuda.empty_cache`; calls at `641`, `652`, `707`, `721`,
  `749`, `1277`, and `1350` are salvage-probe cleanup branches.
* `comfymodal_runtime/unet_meta_direct.py:206`, `394`: direct-loader
  failure/cleanup cache operations.
* `comfymodal_runtime/unet_backing.py:352`, `653`, `873`: backing-owner
  failure/retirement cleanup; their storage/reference behavior must not be
  confused with freeing live adopted weights.

### E. Legacy/non-Golden

* `comfymodal_runtime/modal_app.py:16608-16640`: output asset write starts a
  deferred commit and records it as pending (`16680-16683`) rather than
  awaiting it before producing the result descriptor.
* `modal_app.py:19017-19047`: on result/error/cancelled identification,
  `_run_terminal_cleanup_sync` runs before yielding the terminal event.
* `modal_app.py:19102-19116`: production cleanup and optional GPU release
  happen in the fallback-finally path, then `_finalize_deferred_commit` is
  awaited later.  This is the legacy ordering:

  ```text
  output write -> start async commit -> cleanup/unload -> yield result -> await commit
  ```

  It is not the strict Golden ordering.
* `comfyapp.py:15747-15764`: wraps dynamically discovered
  `load_models_gpu`, `load_model_gpu`, `cleanup_models_gc`,
  `soft_empty_cache`, and `free_memory` to record loaded-model and CUDA
  allocated/reserved deltas.  Wrapping does not itself alter the manager
  behavior.
* `runtime_executor.py:3302-3311`: documents/patches the
  `cleanup_models_gc` boundary immediately before `execution_cached`.
* `runtime_executor.py:4469-4477`: sampler-boundary memory query reads
  `memory_allocated` and `memory_reserved`; it does not purge them.

### F. Diagnostics

* `comfymodal_runtime/empty_cache_bypass.py:12-21`, `42-127`: fail-closed
  decision policy.  Bypass requires the feature flag, known inputs,
  `soft_cache_reason == "free_memory_defensive_no_unload"`, zero unloaded
  models, native allocator, no CUDA capture/custom allocator/custom pool,
  and physical free at least twice the required bytes (`86-96`).
* `empty_cache_bypass.py:157-192`: always synchronizes, then either skips
  native `empty_cache` for an eligible known decision or calls it, and always
  calls `ipc_collect` on the normal path.  Errors are re-raised and a decision
  event is emitted.
* `comfymodal_runtime/clip_cold_path_forensics.py:499-1425`: diagnostic
  wrappers for manager `free_memory` and `soft_empty_cache`; they record
  before/after allocated/reserved, free-memory predicate context, operation
  walls, model counts, and caller/reason without adding CUDA operations.
* `clip_cold_path_forensics.py:1171-1293`: exact wrapper locations for
  `free_memory` and `soft_empty_cache`, including the neutral event sequence
  `start`, `sync_end`, `empty_cache_end`, `ipc_collect_end`, `end`.
* `comfymodal_runtime/e27_forensics.py:398`, `456-650`: E27 wrapper and
  per-operation decomposition; it records sync, `empty_cache`, IPC, total,
  allocator state, and the exact free-memory predicate.
* `e27_forensics.py:655-775`: diagnostic `free_memory` predicate wrapper;
  `e27_forensics.py:781-782` consumes the recorded predicate.
* `comfyapp.py:15747-15764`: model-management profiling hook, including
  dynamic `getattr` discovery of all five manager functions.
* `comfymodal_runtime/gantt_telemetry.py:209-210`: maps measured soft-cache
  start/end events to the `empty_cache` display lane; it is telemetry only.
* Tests are contracts/diagnostics, not production reachability:
  `tests/test_v2_batch_e5_empty_cache_bypass.py:12-219`,
  `tests/test_e27_forensics.py:1-114`,
  `tests/test_v2_clip_cold_forensics.py:17-709`,
  `tests/test_e29_critical_path_ledger.py:205-223,613-623`,
  `tests/test_v2_teardown_diagnostics.py:118,147-190`,
  `tests/test_v2_16_20_patch.py:384-385`,
  `tests/test_e31_clip_forward_fp32.py:879-901`,
  `tests/test_e30_clip_qd_io.py:174`, and
  `tests/test_c6_read_h2d_probe.py:1076-1153,1360,1467-1582,2501-2505`.

### G. Experimental/other

* `comfymodal_runtime/numa_experiment.py:819,1083`: NUMA experiment
  cleanup calls.
* `comfymodal_runtime/rehoming_experiment.py:297`: rehoming experiment
  cleanup call.
* `comfymodal_runtime/unet_qd_probe.py:1077`: UNET QD probe cleanup.
* `comfymodal_runtime/unet_fastsafetensors.py:560`: fast-safetensors probe
  cleanup.
* `tools/benchmark_staged_safetensors_local.py:462`: local benchmark cleanup.
* `tools/v2_d8_get_model_forensics.py:969,974`: model-forensics diagnostic
  synchronization/empty-cache branch.
* `comfymodal_runtime/clip_fast_hydration.py:1874` and
  `clip_fast_hydration_wiring.py:2022` are loader experiment/error seams,
  not strict Golden reachability.

### Counting convention

The authoritative graph/search result is:

```text
EMPTY_CACHE_CALLS_TOTAL=57
runtime/non-test subset=33
strict canonical Golden reachable=0
```

The 57 value is the number of invocation-like Python search lines across the
repository, not unique native CUDA calls.  It includes test doubles, wrapper
definitions/related `soft_empty_cache` matches, diagnostics, and experiments.
Broader literal `empty_cache` text matching is 219 Python matches and is not
the required call count.

### External pinned ComfyUI limitation

The pinned external model manager (`V2_BATCH_D18_VAE_SOFT_EMPTY_CACHE_GATE.md:60-84`)
does not expose a VAE-specific, cache-only, or nonblocking soft-empty call.
`free_memory` can unload first and soft-empty afterward, or soft-empty when
its allocator threshold is met without unloading.  The CUDA order is fixed as
sync -> empty-cache -> IPC.  The local `force` argument is not a usable way to
select a lighter operation.

## 5. Current teardown ordering and lifecycle ownership

### Strict Golden

Strict Golden proves durability before teardown:

```text
restore
 -> request setup and model stages
 -> output
 -> awaited commit
 -> reopen/stat/read/hash verification
 -> TRUE_FIRST_DURABLE_RESULT
 -> RESULT_ASSEMBLED
 -> golden_teardown
 -> TEARDOWN_COMPLETE
 -> final telemetry persistence
 -> return
```

`golden_teardown` releases QD staging only.  It deliberately does not unload
models or flush the allocator.  This is safe for the selected single-use
process lifecycle because process exit owns final model/CUDA reclamation, and
because `release_storage()` would be unsafe while adopted tensors remain live.

### Legacy/V2 stream

The legacy stream has a different terminal boundary.  It starts a deferred
commit, marks the commit pending, identifies a terminal result, performs
synchronous terminal cleanup, yields the result, and only later finalizes the
deferred commit.  Thus cleanup/unload can precede the durable commit proof.
RA7 evidence says the commit/reopen proof must precede a true-durable marker;
the strict path obeys that contract, while the legacy stream's pending event
must not be called a true durable result.

### Minimal versus full optional V2 release

Both modes retain sampler stopping, preload-worker close, legacy-worker join,
activation-reference clearing, bridge/reference clearing, and request-state
bookkeeping (`modal_app.py:6690-6797`).

* **Minimal:** skips model-manager unload, device fallback,
  `cleanup_models`, legacy executor reset, `gc.collect`, CUDA synchronize, and
  `empty_cache` (`modal_app.py:6854-6939`).  The diagnostics test proves
  those stages and calls are absent and that `cuda_after` remains empty
  (`tests/test_v2_teardown_diagnostics.py:147-190`).
* **Full:** runs unload; if unload did not succeed, runs the device fallback;
  then manager cleanup, executor reset, GC, and synchronized `empty_cache`.
  It records before/after allocated/reserved state and each stage result
  (`modal_app.py:6801-6971`).

The default mode is derived from single-use versus reusable containers, with
an explicit `COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN` override
(`modal_app.py:6582-6588`).

### What can be deferred to process termination

For a single-use strict Golden container, full model unload, model-sized
offload, broad GC, allocator flush, and final CUDA reclamation can be deferred
to process exit.  QD transport staging cannot be treated the same way when
worker quiescence or owner lifetime is still needed; strict teardown releases
staging slots but retains live CUDA backing storage.  In a reusable interactive
process, deferring all cleanup risks retained model references, manager cache
state, allocator pressure, and cross-request contamination, so the minimal
single-use rule cannot be generalized without a lifecycle proof.

## 6. Semantics and impact answers

### Serial-stage reuse

The strict schedule is serial at the heavy-stage boundary.  It intentionally
retains live model storage and allocator cache between stages so later stages
can reuse the same models and cached blocks.  Internal QD concurrency is
allowed only inside a stage and is joined at that stage boundary.  A cache
flush would remove reusable inactive blocks, not live models, and can make the
next allocation acquire/return segments again.

### Invalidation and forced future allocations

`empty_cache` can invalidate allocator reuse by returning inactive blocks to
the driver.  It does not invalidate tensor values or model objects.  Future
allocations may therefore need new driver segments, but no forced model reload
follows from `empty_cache` alone.  A model unload/detach is different: it
invalidates the model's GPU residency and can force a later manager reload or
H2D transfer.

### Synchronization

The native soft wrapper synchronizes before cache reclamation because generic
ComfyUI cannot assume all device work relevant to its manager state is done.
The strict Golden stage contracts use local waits/joins where needed and do
not add a device-wide teardown sync.  D18 measured sync itself at only
0.028–0.044 ms in three runs, but explicitly says the missing sampling-end
snapshot leaves the redundancy decision unknown.  A local event wait is not
automatically equivalent to a global manager contract.

### Cached-block flush

The D18/E27 measurements show the meaningful allocator mutation was a reserved
drop of approximately 2.1 GB while allocated stayed unchanged.  That is
consistent with transient sampler workspace becoming inactive cached blocks;
it is not evidence that a live model was released.  Whether those blocks must
be returned before VAE decode is unproven.

### Reloads and unexpected tensor moves

Model-manager unload can detach patchers and cause later reloads.  In full V2
release, the code temporarily sets every loaded patcher's `offload_device` to
CPU because the container otherwise resolves offload to CUDA and detach would
move weights back onto CUDA, defeating cache reclamation (`modal_app.py:6809-6816`).
Original values are restored at `6845-6852`, preserving subsequent warm-path
state.  This temporary mutation is a correctness-sensitive seam, not a free
optimization.

### QD destination and owner lifetime

Canonical QD buffers can back live model weights through `assign=True` storage
sharing.  `release_staging()` drops pinned staging slots after transport
quiescence; `release_storage()` must wait until adopted tensor views are dead.
The strict Golden teardown therefore releases staging, not the model-sized
CUDA backing buffer.  Cross-owner staging reuse is not implemented or proven.

### VAE and first-forward variance

D14 observed VAE join waits of 28.4/31.1/66.1 ms, while settle plus deliberate
CLIP cold reload dominated at approximately 885–1034 ms.  It concluded that
the decode gate was not simply VAE load.  RA8 confirms earlier CLIP/UNET QD
staging ownership statically, but its causal effect is unproven.  The
four-thread artifact reports first-forward values of 1958.226, 15.934, and
2129.476 ms with acceptance failures; it does not prove allocator causality.
No `empty_cache` change should be credited with a first-forward improvement
without a valid exact cohort and boundary reconciliation.

### Billing and request wall

Full post-request release runs before the reusable V2 terminal event/return
path and can therefore consume billed container/request wall.  Deferring it
can reduce the request-visible tail only if process lifetime and result
delivery semantics permit the deferral; it does not prove lower total compute
or lower Modal billing after platform/container-exit costs.  No Modal run was
performed for this report, so no billing saving is claimed.

## 7. Historical experiment evidence

### D18/E27 allocator decomposition

`V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md:459-481` reports three
valid D18 runs:

| Run | Sync (ms) | `empty_cache` (ms) | IPC (ms) | Soft-cache total (ms) |
|---:|---:|---:|---:|---:|
| 1 | 0.044 | 950.460 | 0.010 | 951.320 |
| 2 | 0.038 | 739.241 | 0.010 | 740.226 |
| 3 | 0.028 | 934.173 | 0.014 | 935.051 |

The cache call was 99.87–99.91% of the soft-cache total.  Allocated stayed at
`20,427,641,856`; reserved changed from `22,594,715,648` to
`20,449,329,152` (about 2.1 GB returned).  Models unloaded: zero; bytes
unloaded: zero.  Physical free was about 80 GB, the VAE requirement was
`1,462,827,161.8` bytes, transfer was `167,639,366` bytes, and decode demand
was `9,099,509,760` bytes.  The report attributes the long wall to allocator
reclamation, not the short sync, but does not prove the reclamation is
removable before decode.

D18 states `SYNC_REDUNDANT = UNKNOWN`, `EMPTY_CACHE_REDUNDANT = UNKNOWN`,
and `IPC_COLLECT_REDUNDANT = UNKNOWN` because the sampling-end allocator
snapshot was missing.  It also finds no CUDA-tensor IPC handoff in the local
request path; conservative IPC collection remains unproven removable
globally.

### E28 and path/configuration distinction

`V2_BATCH_E28_CRITICAL_PATH_IMPLEMENTATION_AND_VALIDATION.md:15-25,52-65`
reports unchanged low-cost `empty_cache` at 0.3–2.2 ms and exactness passing
on the final runs.  E28 uses a different path/configuration from the D18
vehicle and therefore cannot erase D18's high-cost observation or establish a
universal cost.

### D14 post-sampling evidence

`V2_BATCH_D14_POST_SAMPLING_FORENSICS.md:37-61,79-105` reports VAE join waits
of 28.4/31.1/66.1 ms and a settle plus CLIP cold reload window of roughly
885–1034 ms.  VAE was already substantially overlapped; earlier VAE
activation alone did not open the decode gate.  This supports measuring the
manager/allocator seam, not labeling all post-sampling time as VAE load.

### RA8, first-forward, and durability evidence

`RA8_VAE_LOAD_VARIANCE_REPORT.md:88-122` confirms 4 workers × 2 slots ×
32 MiB = 256 MiB pinned staging per owner and that CLIP/UNET staging may still
be retained at VAE start; causal variance remains unproven.  The
`four_thread_variant_run_1.txt:424-567` first-forward values are acceptance
failures/context, not allocator proof.  `RA7_DURABLE_COMMIT_VARIANCE_AND_DECOMPOSITION_REPORT.md:26-52`
proves that commit/reopen/hash verification precedes the true durable marker
in strict Golden, while timing variance cause remains unproven.

## 8. Generic interactive-ComfyUI manager waste assessment

Interactive ComfyUI is not the strict single-use Golden lifecycle.  Its model
manager exists to retain/reuse models, unload eligible models under pressure,
and clean bookkeeping across requests.  Five explicit waste seams are
currently plausible candidates, but “plausible” is not “safe to remove”:

1. **High-headroom soft cache:** `free_memory` can invoke soft-empty even when
   no model unload occurs because the allocator free-portion threshold is met.
   D18 shows the worst form: zero unloaded models, very high physical headroom,
   and a long cache-return wall.
2. **Unload scan/offload-device mutation:** full release scans
   `current_loaded_models` and mutates each patcher's `offload_device` so
   detach moves weights to CPU.  The scan and mutation are overhead when the
   loaded set is already empty or the process is single-use, but skipping them
   can retain GPU models or move storage incorrectly.
3. **Fallback `free_memory`:** when `unload_all_models` is missing or fails,
   `free_memory(1e30, device, keep_loaded=[])` is a broad second cleanup path.
   It is useful defensive behavior in reusable processes, but potentially
   redundant after a proven successful unload.
4. **`cleanup_models` / legacy executor reset:** manager bookkeeping and
   executor reset can be repeated after request-local references were already
   cleared.  Their necessity for future interactive requests is not equivalent
   to their necessity in single-use containers.
5. **Post-request full release before return:** the full release sequence can
   run after terminal identification and before the caller receives the event,
   making reclaim cost part of the request tail.  This is a lifecycle choice,
   not evidence that the work is semantically unnecessary.

The manager's generic contract remains the reason not to make a global change:
it may protect subsequent model admission when allocator free portion is low,
and native soft-empty includes synchronization and IPC cleanup not locally
proven redundant.

## 9. Proposed candidate experiment matrix

All rows below are **proposed experiments, not implemented changes**.  They
must preserve exact output and the existing durability evidence.  No row is a
recommendation to edit code in this report.

| Candidate | Exact seam | Expected effect | Correctness risk | VRAM risk | Fallback | Telemetry required | Exactness concern | Rank |
|---|---|---|---|---|---|---|---|---|
| **baseline** | Keep current strict Golden and current native V2/ComfyUI manager behavior; record stage-local and manager boundaries | Establish same-path control for allocated/reserved, loaded models, cleanup walls, durability, and return | Lowest; existing contract | Existing cache/residency behavior | Native behavior unchanged | Full raw call order; allocated/reserved; model counts/bytes; offload devices; QD owner state; commit/reopen proof | Baseline exactness and output hash are gates | HIGH |
| **suppress one specific `empty_cache`** | Only the identified `soft_empty_cache` call whose reason is `free_memory_defensive_no_unload`, using the existing fail-closed predicate; do not suppress after unload/dead-model/unknown reasons | May retain reusable reserved blocks and avoid cache-return work; effect is unknown on the current path | Could violate generic manager completion/allocator policy; sync/IPC assumptions remain | Reserved VRAM may stay high and reduce admission headroom | Re-run native call on unknown inputs, model unload, capture/custom allocator/pool, or insufficient headroom | Decision reason, predicate operands, before/after allocated/reserved, physical free, model count, sync/empty/IPC components | Must compare reopened exact output and all acceptance gates | MEDIUM |
| **defer generic unload until teardown** | Move the legacy/V2 generic `unload_all_models`/manager release after the durable-result boundary, only for a single-use lifecycle | Preserves models through decode/output and may avoid mid-pipeline reload/offload interference | Could expose result to live background work; terminal cancellation/error cleanup becomes harder | Models remain resident longer; peak VRAM can rise | Keep bounded error/cancel cleanup and process-exit reclaim; abort experiment on residency or worker violation | Model identity/device at every stage; peak allocated/reserved; worker joins; durable marker ordering; teardown status | Exactness must pass with no hidden model-move/reload path | UNKNOWN |
| **disable redundant manager scan** | Skip `current_loaded_models` scan/offload-device mutation only when a proven empty/single-use manager state receipt exists; not a global `unload_all_models` removal | Avoids scan and temporary patcher mutation when no loaded model can be detached | Stale receipt can leave a model on CUDA or make detach use the wrong device | Retained model storage if the predicate is wrong | Fail closed to the current scan when state is missing, stale, or non-single-use | Loaded-record identity/count, offload devices before/after, unload result, allocated/reserved deltas | Exact output and no hidden reload must be proven | MEDIUM |
| **preserve allocator cache through VAE/decode** | Do not flush inactive sampler blocks at the sampling-end -> VAE transition; retain native sync/IPC unless separately proven | Could avoid expensive segment return and permit allocator reuse; may have no effect on live model bytes | VAE admission may rely on allocator free portion, not physical free alone; fragmentation risk | Highest candidate VRAM/reservation risk; VAE allocation can fail | Native soft-empty or bounded `free_memory` retry on an observed allocation failure, with no exactness relaxation | Sampling-end snapshot, allocator inactive/active/reserved, VAE requirement/demand, decode peak, manager predicate, failure/retry reason | Exactness and no OOM/retry path are mandatory | UNKNOWN |
| **move cleanup after durable** | Relocate request cleanup that currently occurs before deferred commit finalization so commit/reopen proof is complete first; strict Golden already has this order | Removes pre-durable cleanup/commit race and makes result durability authoritative before release | Holding resources until commit completes can increase tail/VRAM; legacy cancellation semantics can change | Small-to-moderate retention during commit; exact amount unknown | On commit failure, run existing cleanup/error path and preserve primary error | Commit task start/end, reopen/hash proof, cleanup start/end, terminal event order, cancellation state | True durable marker must never precede proof; output bytes/hash must match | HIGH |
| **no-op cleanup in single-use mode** | Keep reference/bookkeeping release and make generic unload/fallback/manager cleanup/reset/GC/CUDA flush no-ops in a proven single-use container; equivalent to strict Golden's lifecycle policy | Avoids post-durable model-manager and allocator work; process exit reclaims remaining live storage | If the process is reused unexpectedly, references/models leak across requests; teardown worker checks must still hold | Resident model/cache persists until exit; safe only with real single-use isolation | Resolve lifecycle conservatively; fall back to full cleanup if reuse/uncertainty is detected | Container single-use identity, request count, worker quiescence, owner refs, process-exit status, allocated/reserved | Exact output unaffected in principle but must run full exactness/durability suite | HIGH |

## 10. Ranked candidate savings

These are confidence tiers for *candidate savings*, not claims of measured
milliseconds and not implementation instructions.

### HIGH CONFIDENCE

1. **No-op cleanup in single-use mode** — strict Golden already proves the
   architecture can complete with reference/staging release and process-exit
   reclamation.  The savings are the full-mode unload/fallback/cleanup/reset/
   GC/CUDA-cleanup work when those stages are otherwise enabled.  Exact amount
   is unmeasured in the current report.
2. **Move cleanup after durable** — high correctness value for the legacy
   deferred-commit ordering because it removes cleanup-before-commit-proof.
   It is a correctness/order saving opportunity, not a measured time saving;
   the strict path already awaits durability before teardown.

### MEDIUM CONFIDENCE

3. **Suppress one specific high-headroom defensive `empty_cache`** — D18 gives
   strong evidence of a zero-unload, high-headroom case where cache flush was
   the dominant wall, and the existing bypass predicate is fail-closed.  The
   D18 missing snapshot leaves VAE/allocator safety uncertain.
4. **Disable redundant manager scan** — likely useful only when a trustworthy
   empty/single-use state receipt exists.  The current source proves the scan
   and offload mutation, not that every invocation is redundant.

### LOW CONFIDENCE

5. **Defer generic unload until teardown** — it may remove interference and
   preserve reuse, but it moves residency and error-cleanup risk later and can
   increase peak VRAM.  No saving is proven.

### UNKNOWN

6. **Preserve allocator cache through VAE/decode** — D18 measured a large
   reserved-block return, but D18 explicitly leaves the required-before-VAE
   question unknown.  Physical headroom alone is insufficient.

The ranking is intentionally not a timing ranking.  Only D18/E27 supply the
reported high-cost `empty_cache` timings, and E28 demonstrates that path and
configuration can change the observed cost substantially.

## 11. Machine-readable completion block

```text
RA10A_COMPLETE=YES
EMPTY_CACHE_CALLS_TOTAL=57
EMPTY_CACHE_GOLDEN_REACHABLE=0
MODEL_MANAGER_WASTE_CANDIDATES=5
PRE_DURABLE_CLEANUP_CANDIDATES=1
POST_DURABLE_WASTE_CANDIDATES=1
SAFE_EXPERIMENTS_IDENTIFIED=7
IMPLEMENTATION_PERMITTED=NO
REPORT=RA10A_EMPTY_CACHE_MODEL_MANAGER_FORENSICS_REPORT.md
```
