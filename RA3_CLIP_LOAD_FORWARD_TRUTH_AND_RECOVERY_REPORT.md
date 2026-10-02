# RA3 CLIP load/forward truth and recovery report

## Current status

RA3 is implemented locally and is ready for parent-owned remote validation. No
Modal deploys and no remote Golden requests were made. Golden Serial remains
serial; this change is CLIP-only and does not add a pinned pool, UNET overlap,
or cast-once residency design. The queued amendment adds measurement-only
process page-fault counters around CLIP load/forward and reversible selected
Qwen-scope forward hooks; it does not page-touch, prewarm, synchronize CUDA, or
change execution behavior.

## Before/after call graph

Before:

```text
golden_serial_execute
  -> golden_clip_load
     -> read_file_qd_gpu (one transport per checkpoint)
     -> comfy.sd.load_text_encoder_state_dicts
     -> select_and_validate_qd_adoption_scope
     -> clip_published(device_ready=cond_model.parameters()[0].device)
  -> golden_clip_forward
     -> GoldenSerialRunner.run_closure
     -> CLIPTextEncode.tokenize + clip.encode_from_tokens_scheduled
     -> completion only
```

After:

```text
golden_serial_execute
  -> golden_clip_load
     -> source_open_read / read_file_qd_gpu
        -> header/layout parse, pinned QD staging, source reads, H2D,
           worker joins and completion-event waits
     -> skeleton_patcher_construction /
        comfy.sd.load_text_encoder_state_dicts
     -> storage_adoption /
        select_and_validate_qd_adoption_scope
     -> compute_ready_proof / selected compute-scope identity
     -> owner_publish_handoff
  -> golden_clip_forward
     -> clip_graph_node_wrapper / GoldenSerialRunner.run_closure
        -> clip_tokenization_input_prep / CLIPTextEncode.tokenize
        -> clip_qwen_transformer_forward (first/later host hook boundaries)
        -> clip_qwen_transformer_encode /
           clip.encode_from_tokens_scheduled
        -> conditioning packaging / later-forward residual
     -> post-forward quiescence check
```

The selected adoption scope, rather than the wrapper's first generic
parameter, is now the readiness authority. Device, dtype, storage identity,
and a bounded outer-extra accounting are retained on the session for the
forward recheck. CPU scalar extras therefore do not invalidate a valid
compute scope.

## Timing taxonomy

`golden_clip_load` emits JSON-safe `golden_clip_timing_v1` data with required
phase records for `source_open_read`, `header_layout_parse`,
`qd_staging_allocation`, `h2d_transport`,
`skeleton_patcher_construction`, `storage_adoption`,
`owner_publish_handoff`, and `compute_ready_proof`. Every record has a name,
start/end/duration fields, boundary kind, and level. Absolute host spans use
`perf_counter_ns`. Transport details preserve source-read-to-pinned staging,
H2D enqueue, aggregate CUDA-event evidence when available, worker join/event
wait, quiescence, and overlap/non-additivity metadata from the existing QD
transport diagnostics.

The QD helper exposes some transport durations without an absolute boundary;
those records are explicitly `unproven` with null start/end rather than being
placed synthetically on the stage wall. Nested transport spans are marked
nested/overlap and are not added as independent parent work. No extra global
CUDA synchronize is introduced for timing. The authoritative recorder stage
wall remains the actual function entry-to-return interval.

`golden_clip_forward` emits graph/node wrapper, tokenization/input prep,
aggregate Qwen encode, selected-scope `clip_qwen_transformer_forward` hook
spans, projection/final-layer `unproven`, conditioning packaging, later-work
residual `UNPROVEN`, post-forward wait, and cache status. The first selected
scope hook is labelled `first_qwen_compute`; subsequent hooks are retained as
`later_forward_work`. Hook spans are `host_observed`, not fabricated device
compute. The runner's execution cache is not a conditioning cache, so cache
status is explicitly `not_used`.

Both CLIP stages emit `clip_page_faults` with stage, start/end counters,
minor/major deltas, availability, and source, and repeat the summary in stage
end details on success (or failure details on failure). The helper uses lazy
stdlib `resource.getrusage(RUSAGE_SELF)` and a Linux `/proc/self/stat`
fallback; unavailable counters remain `None`, never zero. The first selected
scope hook also retains before/after page-fault checkpoints and snapshots.
These counters are diagnostic only: they do not prove lazy page repopulation,
snapshot materialization, or causation, and no `torch.cuda.synchronize()` is
used solely for this measurement.

## Readiness and materialization truth

Load telemetry now reports `compute_scope_device`, `compute_scope_dtype`,
`compute_scope_storage_proven`, `compute_ready`,
`outer_extra_count`, `outer_extra_bytes`, `outer_extra_devices`, and useful
outer names. Forward captures compute-scope device/dtype/data-pointer/storage
identity before execution, after tokenization, and after encode, plus
observable patcher state. `deferred_forward_materialization` is `YES`, `NO`,
or `UNPROVEN` from those direct before/after snapshots. Repeated casts remain
`UNPROVEN`; no historical forensics import was added.

The temporary wrappers restore the original CLIP methods in a `finally` block
and instrumentation failures are recorded as unproven diagnostics without
changing the real result or exception. Selected-scope hooks are likewise
installed only for the forward stage and removed in `finally`; a scope that
cannot register them produces an explicit `UNPROVEN` phase.

## RA2B RSS distinction

RA2B reported capture RSS near 5.03 GB versus approximately 1.23 GB at the
first restored line while mappings remained essentially intact. RSS is a
resident-set observation, not Modal serialized snapshot size. The new process
page-fault counters add a low-overhead host diagnostic dimension around CLIP;
they do not convert that RSS contrast into proof of lazy page repopulation or
identify a causal mechanism. Remote runs remain required.

## Proven versus suspected work

Proven locally by source and focused tests:

* readiness is scoped to the strict pointer-identity adoption result;
* bounded outer extras are reported independently;
* timing records are JSON-safe and parent spans reconcile without overlap;
* tokenization and encode wrappers classify their calls and restore methods;
* page-fault helper availability/source shape and load/forward delta arithmetic;
* selected-scope first-forward hook timing, checkpoints, and restoration;
* repeated cast work is not claimed.

Not proven locally or remotely:

* current-model CUDA device timings for inner transformer/projection work;
* a separate projection/final-layer boundary inside the upstream encode call;
* whether the real current forward materializes anything deferred (the runtime
  result will report this from direct snapshots);
* whether page faults coincide with the first Qwen host boundary in a remote
  run, or whether they cause any observed timing/RSS behavior;
* lazy page repopulation, Modal snapshot serialized size, and any causal
  relationship among RSS, mappings, and page faults;
* a remote end-to-end timing or regression recovery.

## Regression from the old fast-CLIP era

The old sub-2.4-second rows did not contain a valid whole-forward measurement;
the E28 2.03-second row used a broken pre-fix counter span. E31's historical
manual-cast observation is 252 BF16-to-FP32 Linear casts per forward, but that
is not a current Golden Serial proof and is intentionally reported
`UNPROVEN` here. R44F's skipped BF16/FP16 zero-copy adoption is not cited as
success. Current CLIP uses one synchronous QD4 transport with 32 MiB blocks
and four workers; E37 measured a historical 1043.5 ms source wall with joins
and event waits. H1/H2 remain hypotheses about UNET overlap/host contention,
not evidence for this serial CLIP path.

RA3 therefore improves truth and attribution first. It does not claim that
the old fast-CLIP number is recovered, nor does it preempt RA9 architecture.

## Changed files

* `comfymodal_runtime/golden_serial.py` — CLIP compute-scope readiness,
  load/forward timing ledgers, safe CLIP wrappers/hooks, page-fault
  measurement, and session evidence.
* `tests/test_ra3_clip_truth_telemetry.py` — focused offline readiness,
  timing, wrapper-restoration, page-fault, and hook-checkpoint tests.
* `RA3_CLIP_LOAD_FORWARD_TRUTH_AND_RECOVERY_REPORT.md` — this report.

## Local validation

* `pytest -q tests/test_ra3_clip_truth_telemetry.py` — **6 passed**.
* `python -m py_compile comfymodal_runtime/golden_serial.py tests/test_ra3_clip_truth_telemetry.py` — **passed**.
* `git diff --check -- comfymodal_runtime/golden_serial.py tests/test_ra3_clip_truth_telemetry.py` — **passed**.
* Direct offline helper exercise for CPU selected scope plus CPU outer scalar,
  and wrapper restoration — **passed**.

## Minimal later remote cohort and exact commands

Parent validation should use a new isolated experimental app, not the
protected production app. Following Golden ops, the minimal cohort is doctor
and status before/after deployment, one source probe, one eligible Golden run,
then only the additional separate observations required by the cohort. Apply
the snapshot-capture rule: a capture and its directly following request are
invalid. Use the exact public commands below from repository root (replace
`<experimental-app>` and `<gate-manifest>`):

```powershell
python tools/v2ctl.py golden status --app <experimental-app>
python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py golden deploy --app <experimental-app>
python tools/v2ctl.py --profile golden_p1 --app <experimental-app> source-probe
python tools/v2ctl.py golden status --app <experimental-app>
python tools/v2ctl.py doctor --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py golden run --app <experimental-app>
python tools/v2ctl.py gate --profile golden_p1 --app <experimental-app>
python tools/v2ctl.py --profile golden_p1 --app <experimental-app> confirm --from <gate-manifest> --runs 5
```

Stop here at `READY_FOR_REMOTE_VALIDATION=YES`. This implementation made zero
deploys and zero remote requests. The minimal remote cohort should retain the
new page-fault event/checkpoint fields alongside the existing raw timing and
RSS evidence; it must not treat them as readiness or causation proof.

RA3_IMPLEMENTATION_COMPLETE=YES
CLIP_LOAD_DECOMPOSED=YES
CLIP_FORWARD_DECOMPOSED=YES
COMPUTE_SCOPE_READINESS_TELEMETRY=YES
GENERIC_FIRST_PARAMETER_DEVICE_READY_REMOVED=YES
DEFERRED_FORWARD_MATERIALIZATION_FOUND=UNPROVEN
REPEATED_CAST_WORK_FOUND=UNPROVEN
RA9_ARCHITECTURE_PREEMPTED=NO
READY_FOR_REMOTE_VALIDATION=YES
REPORT=RA3_CLIP_LOAD_FORWARD_TRUTH_AND_RECOVERY_REPORT.md
