# PROPOSED / UNAPPLIED: CLIP load + forward boundary instrumentation

Status: **proposed, not applied**. Nothing in the running tree, no deployment,
no Modal invocation, and no request execution was performed to produce this.
The patch was generated and validated against a throwaway copy only.

- Patch: `proposed_clip_and_load_boundaries.patch` (this directory)
- Supersedes concept: `reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch`
- Target commit: `d1fffd2f5da108f0a718ea80da56152ae29f9c57` (H100 deployed source)
- Target worktree: `.slim/worktrees/authoritative-golden-core-sep14` (HEAD = d1fffd2)
- Validation owner: orchestrator
- Application is deliberately out of scope here.

## What this fixes relative to the earlier proposal

The earlier patch only instrumented `golden_clip_forward`. The H100 vs RTX
audit left the CLIP **load** path and several forward boundaries unobserved.
This patch adds them while keeping the same rules: gate-off no-op, no added
synchronization, no reordering, no general tracing.

Two request-local, best-effort payloads are emitted (one per Golden stage):

| event | stage | source |
|---|---|---|
| `clip_load_boundaries` | `golden_clip_load` | `golden_serial.golden_clip_load` success/failure return |
| `clip_forward_boundaries` | `golden_clip_forward` | `golden_serial.golden_clip_forward` success/failure return |

They are separate events because load and forward are distinct Golden stages
and are not merged into a single fabricated timeline. Ordering across the two
is derivable from the recorder's own monotonic clock and from the existing
per-stage `begin_stage`/`end_stage` intervals.

### `clip_load_boundaries` marks (12 expected)

| mark | boundary | existing boundary reused |
|---|---|---|
| `load_entry` | `golden_clip_load` entered | immediately after `rec.begin_stage("golden_clip_load")` |
| `source_open_read_begin` / `_end` | per-checkpoint QD source read + H2D | existing `clip_timing.span("source_open_read")` |
| `skeleton_patcher_construction_begin` / `_end` | native constructor | existing `clip_timing.span("skeleton_patcher_construction")` |
| `owner_publish_handoff_begin` / `_end` | owner attach + `session.clip` publish | existing `clip_timing.span("owner_publish_handoff")` |
| `storage_adoption_begin` / `_end` | generic adoption proof | existing `clip_timing.span("storage_adoption")` |
| `compute_ready_proof_begin` / `_end` | compute-ready identity proof | existing `clip_timing.span("compute_ready_proof")` |
| `load_return` | immediately before `return clip` | — |

### `clip_forward_boundaries` marks (15 expected)

| mark | boundary | existing boundary reused |
|---|---|---|
| `forward_entry` | `golden_clip_forward` entered | after `CLIP_FORWARD_START` |
| `tokenization_begin` / `_end` | `clip.tokenize` call | existing `_clip_forward_wrappers` span `clip_tokenization_input_prep` |
| `graph_node_wrapper_begin` / `_end` | encode node closure | existing `clip_timing.span("clip_graph_node_wrapper")` |
| `cpu_setup_end` | clip entry setup done | existing `clip_timing.span("clip_forward_entry_setup")` |
| `first_cuda_submit_proxy` | first observed CUDA-touching op (**PROXY**) | first RA9H `cast_to` call, or encoder begin fallback |
| `first_cuda_complete_proxy` | first observed completion (**PROXY**) | first real conversion, or encoder end fallback |
| `encoder_begin` / `_end` | first Qwen transformer forward | existing `_clip_qwen_forward_hooks` pre/post |
| `host_quiescence_begin` / `_end` | existing post-forward quiescence | existing `clip_timing.span("clip_post_forward_sync_wait")` + `_assert_runner_quiescence` |
| `conditioning_packaging_begin` / `_end` | output packaging | existing `clip_timing.span("clip_conditioning_packaging")` |
| `forward_return` | immediately before `return conditioning` | — |

Each payload contains `expected_marks`, `observed_marks`, `missing_marks`,
`marks`, per-adjacent-interval `wall_ms` / `process_cpu_ms` / `thread_cpu_ms`,
and (forward only) a `cuda_event_pair` block. Each mark carries
`perf_counter_ns`, `monotonic_ns`, and process/thread CPU clocks when the
platform provides them. `missing_marks` is the intended consumer hook for the
orchestrator: an empty list means every requested boundary fired; any name
present is an honestly unobserved boundary, never a fabricated zero.

## Constraints honored

- **No added synchronization.** The CUDA-completion proxy event is recorded on
  the live stream and `elapsed_time` is read by `clip_forward_boundary_resolve`
  only after the already-required `_assert_runner_quiescence`; the value is
  discarded when the current stream differs. No `torch.cuda.synchronize`, no
  per-op event reads.
- **No ordering changes.** Every hunk is pure insertion between existing
  statements. The generated diff contains 0 deletions.
- **No behavior change when the gate is off.** All entry points sync the
  existing `COMFYMODAL_V2_E31_FORENSICS` gate; when off, `begin` returns
  `False`, no recorder is created, `mark`/`note_*` are no-ops, and `finish`
  returns `None`. `_clip_boundary` never raises into the Golden path.
- **Only the two d1fffd2 files change.** `comfymodal_runtime/golden_serial.py`
  (+80 lines) and `comfymodal_runtime/clip_forward_forensics.py` (+339 lines,
  append-only). No new env flag, no config-authority change, no test change,
  no QD/block/model/workflow/backend change, no CUDA warm-up.
- **No general tracing.** `_clip_boundary(op, *args)` is a narrow adapter that
  dispatches only to the named boundary functions; it does not wrap arbitrary
  calls and adds no span/trace framework.

## Exact target symbols / baseline line context (d1fffd2)

`comfymodal_runtime/golden_serial.py`
- `_clip_qwen_forward_hooks` → `pre_hook` (baseline ~L10451) and `post_hook`
  (~L10478)
- `_clip_forward_wrappers` → `wrapped` (~L10848)
- `_ra9h_forward_conversion_instrumentation` → `wrapped` (~L11143) and the
  first-real-conversion `if` body (~L11147)
- new module-level `_clip_boundary(op, *args)` immediately before
  `async def golden_clip_forward` (baseline L12043)
- `golden_clip_load` (baseline L11275): entry (~L11308), `source_open_read`
  (~L11386), `skeleton_patcher_construction` (~L11664),
  `owner_publish_handoff` (~L11691), `storage_adoption` (~L11762),
  `compute_ready_proof` (~L11773), success emission before `return clip`
  (~L11968), failure emission in `except BaseException as exc` (~L11969)
- `golden_clip_forward` (baseline L12044): entry (~L12055),
  `clip_forward_entry_setup` close (~L12082), `clip_graph_node_wrapper`
  (~L12156), `clip_post_forward_sync_wait` (~L12169),
  `clip_conditioning_packaging` (~L12290), success emission before
  `return conditioning` (~L12364), failure emission (~L12365)

`comfymodal_runtime/clip_forward_forensics.py`
- Append-only block after `functools_wraps` (file ends baseline L1338),
  reusing existing `_ENABLED`, `sync_e31_gates`, `_current_stream`, and
  `_make_event`. Adds the per-stage `_ClipBoundaryRecorder` plus
  `clip_load_boundaries_begin/_mark/_finish` and
  `clip_forward_boundaries_begin`, `clip_forward_boundary_mark`,
  `clip_forward_boundary_note_cuda_submit/_complete`,
  `clip_forward_boundary_note_encoder_begin/_end`,
  `clip_forward_boundary_resolve`, `clip_forward_boundaries_finish`.

## Known measurement limits (exact)

1. **Tokenization / graph-wrapper / encoder / CUDA-proxy forward marks depend
   on Golden stage diagnostics.** `tokenization_begin/_end` come from the
   existing `_clip_forward_wrappers`, `encoder_begin/_end` from
   `_clip_qwen_forward_hooks`, and the `cast_to`-based CUDA proxy pair from
   `_ra9h_forward_conversion_instrumentation`. All three are installed only
   when `stage_diagnostics_enabled()` (`COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS`)
   is on. With the E31 gate on but stage diagnostics off, those marks appear in
   `missing_marks`; `forward_entry`, `cpu_setup_end`, `graph_node_wrapper_*`,
   `host_quiescence_*`, `conditioning_packaging_*`, and `forward_return` still
   fire because they are on the unconditional Golden path.
2. **The CUDA pair is a proxy, not a per-kernel decomposition.**
   `first_cuda_submit_proxy` is recorded immediately before the first observed
   `cast_to`; `first_cuda_complete_proxy` immediately after the first real
   (dtype/device-changing) conversion, or at the end of the first encoder
   forward when no conversion cast is observed. `gpu_elapsed_ms` is the stream
   interval between those two host-observed boundaries. It therefore bounds
   first-CUDA-work region latency; it is not the sum of kernel times.
3. **No new synchronization means the resolved value is only as trustworthy as
   the existing quiescence.** `resolve()` reads `elapsed_time` after
   `_assert_runner_quiescence` and discards the value if the current stream
   differs from the recording stream or the value is negative. It never
   synchronizes to make a number available, so a missing
   `first_cuda_elapsed_proxy` is expected on stream-mismatch / no-CUDA runs.
4. **Encoder fallback for the pair.** If no `cast_to` is observed before the
   encoder forward, `note_encoder_begin` / `note_encoder_end` seed the pair and
   `submit_source` is recorded as `encoder_forward_proxy`, distinguishing it
   from a real `cast_to` observation.
5. **Multi-checkpoint load.** `source_open_read_begin/_end` are emitted once
   per checkpoint with the same names (no per-index suffix). `intervals` still
   orders them correctly; a multi-checkpoint run shows repeated names by
   design.
6. **Failure paths.** On a load/forward exception the recorder is finished and
   emitted (best-effort) before the existing `fail_stage`/`raise`, so a failed
   stage yields a partial payload with a populated `missing_marks` list rather
   than nothing. Emission is wrapped so diagnostics can never mask the original
   exception.
7. **Gate-off overhead.** Even when the E31 gate is off, each boundary call
   performs one module-import lookup and a `None` recorder check. This is a
   cheap no-op but is not literally zero work; it is the same trade-off as the
   earlier proposal.

## Validation performed (offline; no GPU runtime test)

Performed against a throwaway copy (`git init` + baseline commit of the two
d1fffd2 files), never against the deployed worktree:

```text
git apply --check reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch
    -> Checking patch comfymodal_runtime/golden_serial.py...
       Checking patch comfymodal_runtime/clip_forward_forensics.py...
       APPLY_CHECK_OK   (run in .slim/worktrees/authoritative-golden-core-sep14, HEAD d1fffd2)

# fresh throwaway copy of the two d1fffd2 files, then:
git apply proposed_clip_and_load_boundaries.patch   -> PATCH_APPLIED
python -m py_compile comfymodal_runtime/golden_serial.py \
                       comfymodal_runtime/clip_forward_forensics.py
    -> PY_COMPILE_OK
```

Diff statistics: `golden_serial.py` +80, `clip_forward_forensics.py` +339,
**0 deletions**. The files produced by applying the patch are byte-identical
(modulo CRLF normalization) to the build-tree files.

CPU smoke of the appended recorder (isolated package copy; no CUDA used):

```text
GATE_OFF_NOOP_OK
GATE_ON_LOAD_OK 12 marks
GATE_ON_FORWARD_OK 13 marks, missing: first_cuda_submit_proxy,first_cuda_complete_proxy
SMOKE_OK
```

The gate-on forward smoke forced the no-stream branch, so the two CUDA proxy
marks are reported missing rather than fabricated. No deployment, `v2ctl`, or
Modal invocation was performed.

## Apply / rollback (for the orchestrator)

```text
# from the d1fffd2 worktree
git apply --check reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch
git apply        reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch
# rollback
git apply -R     reports/h100_golden_path_audit_2026-09-17/proposed_clip_and_load_boundaries.patch
```

Enable with `COMFYMODAL_V2_E31_FORENSICS=1`; for the full mark set also enable
Golden stage diagnostics (`COMFYMODAL_GOLDEN_STAGE_DIAGNOSTICS=1`). New events:
`clip_load_boundaries` and `clip_forward_boundaries`.
