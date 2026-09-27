# PROPOSED / UNAPPLIED: CLIP-forward boundary instrumentation

Status: **proposed, not applied**. Nothing in the running tree, no deployment,
no Modal invocation, and no request execution was performed to produce this.

- Patch: `proposed_clip_forward_boundaries.patch` (this directory)
- Target commit: `d1fffd2f5da108f0a718ea80da56152ae29f9c57` (H100 deployed source)
- Validation owner: orchestrator
- Application is deliberately out of scope here.

## What it measures

One opt-in, request-local recorder emits a single `clip_forward_boundaries`
telemetry event for `golden_clip_forward`, capturing:

| mark | boundary |
|---|---|
| `forward_entry` | `golden_clip_forward` entered (after `CLIP_FORWARD_START`) |
| `cpu_setup_end` | `clip_forward_entry_setup` span closed |
| `first_cuda_submit` | first CUDA event recorded at the first observed op |
| `first_cuda_complete` | CUDA event recorded at the first real cast conversion (or encoder fallback) |
| `encoder_begin` | first `clip_qwen_transformer_forward` pre-hook |
| `encoder_end` | first `clip_qwen_transformer_forward` post-hook |
| `sync_begin` | existing `clip_post_forward_sync_wait` span entered |
| `sync_end` | existing `_assert_runner_quiescence` returned |
| `forward_return` | immediately before `golden_clip_forward` returns |

Each mark carries `perf_counter_ns`, `monotonic_ns`, and (when the platform
provides them) `process_cpu_ns` / `thread_time_ns`. The payload also emits
per-interval `wall_ms`, `process_cpu_ms`, and `thread_cpu_ms` deltas, plus a
`cuda_event_pair` block with `submit_source` and `gpu_elapsed_ms`.

## Constraints honored

- **No added synchronization.** The CUDA event pair is recorded on the live
  stream and read by `clip_forward_boundary_resolve` only after the
  already-required `_assert_runner_quiescence` sync. No `torch.cuda.synchronize`
  or per-op `elapsed_time` read is introduced.
- **No ordering changes.** All instrumentation is inserted between existing
  statements; no existing call is moved or reordered.
- **No behavior change when off.** Everything is gated on the existing
  `COMFYMODAL_V2_E31_FORENSICS` flag. With it off, `_clip_boundary` returns
  `None`, no recorder is created, and no CUDA call or mark is made. All calls
  are best-effort and cannot raise into the Golden path.
- **Only the two permitted files change.** `comfymodal_runtime/golden_serial.py`
  (+52 lines) and `comfymodal_runtime/clip_forward_forensics.py` (+262 lines,
  append-only). No new env flag, no config-authority change, no test change.
- **No GPU test.** Offline validation: `git apply --check` passes against the
  `d1fffd2` worktree, both patched files pass `py_compile`, and a CPU smoke of
  the recorder (gate on, no real forward) returns all expected marks.

## Exact target symbols / line context (d1fffd2)

`comfymodal_runtime/golden_serial.py`
- `_clip_qwen_forward_hooks` → `pre_hook` (~L10451) and `post_hook` (~L10478)
- `_ra9h_forward_conversion_instrumentation` → `wrapped` (~L11143) and the
  first-real-conversion `if` body (~L11147)
- New module-level `_clip_boundary(op, *args)` immediately before
  `async def golden_clip_forward` (~L12043)
- `golden_clip_forward` (~L12044): entry (~L12055), `cpu_setup_end` after the
  `clip_forward_entry_setup` span (~L12082), sync span (~L12169), success
  emission before `return conditioning` (~L12362), failure emission in
  `except BaseException as exc` (~L12365)

`comfymodal_runtime/clip_forward_forensics.py`
- Append-only block after `functools_wraps` (file ends L1338), reusing the
  existing `_ENABLED`, `sync_e31_gates`, `_current_stream`, and `_make_event`
  helpers. Adds `clip_forward_boundaries_begin`, `clip_forward_boundary_mark`,
  `clip_forward_boundary_note_cuda_submit/_complete`,
  `clip_forward_boundary_note_encoder_begin/_end`,
  `clip_forward_boundary_resolve`, and `clip_forward_boundaries_finish`.

## Known measurement limits (to be interpreted by the orchestrator)

- `first_cuda_submit` is the first observed CUDA-touching boundary in the
  forward body; if the encoder pre-hook fires first it wins, otherwise the
  first `cast_to` does. `submit_source` records which.
- `first_cuda_complete` is recorded at the first real cast conversion, or at
  the end of the first encoder forward when no conversion cast occurs. Its
  elapsed value is the GPU span between the submit and complete events, not a
  per-kernel decomposition.
- `resolve()` discards the value if the current stream at resolve time differs
  from the recording stream (never fabricates a number).

## Apply / rollback (for the orchestrator)

```text
# from the d1fffd2 worktree
git apply --check reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch
git apply        reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch
# rollback
git apply -R     reports/h100_vs_rtx_forensics_2026-09-17/proposed_clip_forward_boundaries.patch
```

Enable with `COMFYMODAL_V2_E31_FORENSICS=1`; the new event is
`clip_forward_boundaries`.
