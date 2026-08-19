# V2 Batch C5 — Sampling-Time VAE Activation Experiment (sampling_first_step)

Status: IMPLEMENTED — flag default OFF — NOT deployed, NOT run on Modal.
Date: 2026-08-14
Owner lane: C5 (VAE activation implementation/tests/report only)

## 1. Summary

Added one experimental VAE activation mode behind a default-OFF flag:

```
COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step
```

The mode reuses the **existing** VAE early-activation machinery — it introduces
no second VAE loader.  The trigger boundary is the existing
`first_sampler_step` hook (the first completed sampler step), which starts the
existing Experiment-2 transfer-only worker (`_run_vae_early_start_worker`,
`comfymodal_runtime/model_preload.py:17252`): the worker pre-copies the VAE's
CPU params/buffers to CUDA on a dedicated side stream **during sampling** (no
mutation lane, no model mutation), then waits for the authoritative
sampling-end event and performs a narrow lane-bound `.data` rebind strictly
after the sampler released the mutation lane.

The default (`sampling_end`) is byte-for-byte unchanged.

## 2. Why first_sampler_step (trigger-boundary decision)

Two existing post-first hooks were candidates:

| Hook | Location | Assessment |
|---|---|---|
| `unet_first_cuda_op` / `mark_first_unet_forward` | `unet_forward_probe.py:523-524` (UNET forward pre-hook) | Fires on the **first UNET forward**, which can occur during prefill/warmup phases **before the sampler is genuinely committed**.  Also runs while the UNET activation path is still settling. |
| `first_sampler_step` / `mark_first_sampler_step` | `runtime_executor.py:4451-4465` (per-step callback, first invocation) | Fires **inside the sampling loop after step 1 completes**.  Proves the sampler is committed and running; UNET is resident; several seconds of sampling remain for overlap.  Already feeds the stall watchdog and emits its own trace event. |

`first_sampler_step` was chosen: it is the existing hook that most precisely
matches the task's preferred trigger ("after the first sampler step is
confirmed") and it is materially safer than the first-forward hook because it
cannot fire during pre-sampler UNET activation/prefill.

Note: the scheduling hook only fires when the sampler has a real per-step
callback (`SAMPLER_SAMPLE`'s `callback` arg).  If a sampler runs with no
callback, the VAE is simply not activated early and the unchanged graph
VAELoader fallback serves it — a safe, silent degradation (invariant 6).

## 3. Why the transfer-only worker (and not an earlier `load_models_gpu`)

The shared mutation lane (`MutationLane`, `model_preload.py:6424`) is plain
FIFO.  The sampler holds the lane from `sampling_start` until
`release_sampler_mutation_lane_at_sampling_end`; the full `load_models_gpu`
VAE worker (`_run_early_vae_activation`) acquires the lane as owner `VAE` and
therefore **cannot overlap active sampling at all** — scheduling it earlier
would just queue it behind the sampler (zero overlap).

The Experiment-2 transfer-only worker is the existing machinery that already
achieves genuine overlap:

1. **Phase 1 (during sampling, no lane)**: copies each CPU param/buffer of the
   VAE inner model to CUDA on a dedicated side stream (`_vae_side_stream`).
   The model is **never mutated** here; the lane is never touched.
2. **Phase 2**: waits for `_VAE_SAMPLING_END_EVENT` (set at the authoritative
   sampling_end boundary, before the lane release).
3. **Phase 3 (post-sampling, narrow lane bind)**: acquires the lane as owner
   `VAE` (strictly after the sampler released it), rebinds `param.data` /
   buffer `.data` in place, populates activation evidence, completes the
   future.

This is the "nearest safe equivalent" the task allows: same VAE object, same
single-flight state, same decode join, same silent fallback — only the
transfer moves under sampling.

## 4. Implementation

Files changed (C5 lane footprint only):

- `comfymodal_runtime/model_preload.py`
  - Mode constant `_VAE_ACTIVATION_MODE_SAMPLING_FIRST_STEP = "sampling_first_step"` (16407)
  - Added to `_VAE_ACTIVATION_MODE_VALID` and `_VAE_ACTIVATION_MODE_ACTIVE` (16408-16413)
  - `_resolve_vae_activation_mode` accepts `sampling_first_step`; everything else still falls back to `late` (16458-16470)
  - New state fields: `trigger_mono_ns`, `sampling_start_mono_ns`, `precopy_start_mono_ns`, `sampling_end_wait_ms`, `overlap_ms`, `precopy_wall_ms` (16520-16534)
  - New module global `_VAE_SAMPLING_END_MONO_NS` set in `release_sampler_mutation_lane_at_sampling_end` immediately before `_VAE_SAMPLING_END_EVENT.set()` (17122-17136)
  - Lane acquire/release gates broadened `== sampling_end` → `in _VAE_ACTIVATION_MODE_ACTIVE` (17120, 17145)
  - Restore/prepare gates broadened so `sampling_first_step` also skips restore-time VAE prep (exactly-one-activation invariant) (9220, 10402)
  - Decode/join gates broadened (11060, 11115, 11222) — `_join_vae_early_activation`, `_consume_vae`, `_consume_vae_decode` now treat `sampling_first_step` as active
  - `schedule_vae_early_activation_at_sampling_end` **unchanged** (still no-op in first_step mode → exactly one activation per request)
  - Worker telemetry (`_run_vae_early_start_worker`): trigger strings now read `state.get("trigger", "early_start")` (B-arm output identical); added `precopy_start_mono_ns`, `precopy_wall_ms`, `sampling_end_wait_ms`, `sampling_end_mono_ns`, `overlap_ms`, `gpu_allocated_before/after/delta_bytes` to state + reconciliation/opt-diag events (17344-17534)
  - NEW `schedule_vae_early_activation_at_first_step(bridge, *, trace, request_id, sampler_node_id, sampler_node_class, first_step_mono_ns) -> bool` (17750) — mirrors the Experiment-2 early-start scheduler; idempotent (single-flight via `_VAE_ACTIVATION_STATE` + per-request `Future`); spawns ONE daemon thread (`comfymodal-vae-first-step`) running the **existing** `_run_vae_early_start_worker` with `offset_ms=0, expected_ms=0` (immediate pre-copy)
- `comfymodal_runtime/runtime_executor.py`
  - First-step hook inside `_step_callback` (4464-4486): after `mark_first_sampler_step`, guarded try/except calls `schedule_vae_early_activation_at_first_step` with the live bridge.  No-op in every other mode; failures silent; never blocks the sampler callback (no synchronization added).
- `tests/test_v2_vae_sampling_first_step.py` (NEW, 13 unittest tests)

Not modified: `canonical_execution.py`, `contracts.py`, `tools/batch_b_acceptance.py`,
`tools/benchmark_v2_direct.py`, Batch-C acceptance files, snapshot-hygiene code,
`modal_app.py` (no changes needed — env passthrough and probe list already carry
the mode key verbatim), `.bat` launchers.

## 5. Invariants (task requirements)

| # | Invariant | Status |
|---|---|---|
| 1 | Default remains `sampling_end` | `_resolve_vae_activation_mode` default is `late` when unset; `.bat` default `sampling_end` untouched; resolver accepts `sampling_first_step` only as explicit opt-in.  Test A. |
| 2 | Experimental mode explicit | Requires `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step` verbatim; any other value → `late`. |
| 3 | Exactly one VAE activation/load | Single-flight via `_VAE_ACTIVATION_STATE` future + `RestorePreparation`; duplicate first-step notifications return early; sampling_end scheduler is a no-op in this mode.  Tests B, C, D, H. |
| 4 | `sampling_end` mode unchanged | All gates broadened are supersets (`in ACTIVE`); sampling_end-specific paths untouched; trigger strings derive from state (`early_start`/`sampling_end` output identical).  Regression suites green. |
| 5 | Decode joins/waits for readiness | `_join_vae_early_activation` runs for active modes; full wait with measured `join_wait_ms`.  Tests E, F. |
| 6 | Failure → safe fallback | Resolution failure → terminal failed; worker phase-1 exception → `precopy_failed` terminal; decode join sees non-ready terminal → `_vae_activation_fallback` → unchanged graph loader path; `_consume_vae_decode` returns `_LOADER_MISS`.  Test G. |
| 7 | Image output/params unchanged | No decode-path change; `_consume_vae_decode` still returns `_LOADER_MISS` so decode executes the original VAEDecode in graph order. |
| 8 | No UNET object/identity changes | Scheduler touches only VAE state; no UNET code path invoked.  Test I. |
| 9 | No early UNET unload/move | Nothing unloads or relocates the UNET; lane ownership stays `sampler` during sampling.  Test I. |
| 10 | No unconditional sampler synchronization | First-step hook spawns a daemon thread and returns; no waits on the sampler thread.  Test E/I timing. |

## 6. Instrumentation emitted for the experimental mode

All via the existing trace-event vocabulary (`vae_early_activation_*`) plus
additive metadata:

| Required measurement | Where emitted |
|---|---|
| trigger timestamp | `vae_early_activation_scheduled` metadata `trigger_mono_ns` (scheduler) |
| trigger type | `trigger=sampling_first_step` on scheduled/load_start/terminal/consumed/reconciliation events |
| VAE load start/end | `vae_early_activation_load_start` event; state `worker_started_mono_ns` / `terminal_mono_ns` |
| VAE transfer wall | `precopy_wall_ms` (opt-diag `vae_precopy` + reconciliation metadata) |
| sampling start/end | existing `sampling_start` / `sampling_end` trace events; `sampling_end_mono_ns` state field |
| overlap_ms | `overlap_ms = max(0, sampling_end_mono_ns − precopy_start_mono_ns)` in reconciliation metadata |
| post-sampling join_wait_ms | `vae_early_activation_consumed` metadata `join_wait_ms` |
| decode consumed prefetched VAE | `vae_early_activation_consumed` event (`status=ready`, once per request) |
| transfer_count | terminal/consumed/reconciliation metadata `transfer_count` |
| fallback/reason | `vae_early_activation_fallback` event + state `fallback_reason` / terminal `reason` |
| GPU allocation before/after | state + reconciliation `gpu_allocated_before/after/delta_bytes` (full-load worker already recorded these; the transfer worker now does too) |

The experiment answers: "did ~0.9 s of VAE load move under sampling?" →
compare `overlap_ms` vs total `precopy_wall_ms`; "did sampling get slower?" →
compare `sampling_end.duration_ms` between arms.

## 7. Tests

`tests/test_v2_vae_sampling_first_step.py` — 13 tests, unittest style
(discoverable by `python run_tests.py` and `pytest`):

| Req | Test(s) |
|---|---|
| A | resolver normalization (`""`/`banana`→late), ACTIVE set, late-mode no-op, sampling_end-mode no-op for the first-step scheduler |
| B | schedules once, trigger/owner `sampling_first_step`, `trigger_mono_ns>0`, one scheduled event, terminal ready |
| C | duplicate notifications: 1 event, 1 state entry, 1 thread start (counting `Thread` patch), single transfer |
| D | already-CUDA param skipped → `transfer_count==0`, no second load |
| E | join while background held → waits ~200 ms, `join_wait_ms>0`, valid/ready outcome, bounded completion |
| F | join after terminal → `join_wait_ms<50`, one consumed event |
| G | phase-1 exception → terminal `failed/precopy_failed`, fallback elected once, `_consume_vae_decode` → `_LOADER_MISS` |
| H | one param → `transfer_count==1`, duplicate schedule stays 1 |
| I | lane stays `sampler` during sampling (worker defers phase-3); `_UNET_ACTIVATION_STATE`/`_UNET_ACTIVATION_MODE` untouched |
| J | reconciliation event ordering + arithmetic: trigger ≤ precopy_start ≤ sampling_end, overlap_ms ≈ clock delta, all new fields present |

Results: **13 passed** (pytest, stable across 4 repeat runs) and
**13 passed** via `python run_tests.py`.  Regression: `test_v2_unet_early_activation`
(41), `test_v2_sampler_wrapper_integration` (23), `test_v2_sampler_boundary` (21),
`test_v2_ab_experiments` (10) → **95 passed, 0 failed**.

Known pre-existing failures in the working tree (not caused by this change):
`test_v2_batch_profiles` .bat-content drift (5, other workers' .bat edits) and
`test_v2_cold_path_instrumentation` sampling_start dedup mismatch (1, prior
wrapper dedup change).

## 8. Later A/B protocol (exact, NOT run)

Validation policy (standing campaign rule): **one cold validation** with the experimental mode enabled; if correct, use **only 1–5 valid runs**, always biased toward fewer — validation alone may be sufficient, and up to 5 are used only when consistency/variance actually requires it.

Arm A (baseline, unchanged production path):
- `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end` (current default via `.bat`)

Arm B (experimental):
- `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step`

Protocol:

1. **Cold validation (B only, 1 run).** Deploy fresh (no warm container), run
   one request with `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_first_step`.
   Gate criteria — all must hold:
   - exactly one `[v2.vae_early_activation] event=scheduled trigger=sampling_first_step`
     line per request;
   - event order per request: `scheduled` → `load_start` → `terminal status=ready`
     → `consumed status=ready`;
   - `transfer_count == 1`;
   - `overlap_ms > 0` (i.e., pre-copy started before `sampling_end` fired);
   - `sampling_end.duration_ms` within noise of a prior baseline (no sampler
     regression);
   - output image matches Arm A (PSNR/SSIM via existing comparison tooling).
2. **Comparison runs (if validation correct): 1–5 valid runs per arm, biased toward fewer** (standing campaign rule: validate first with one cold run; then use only 1–5 valid runs; always bias toward fewer; validation alone may be sufficient; use up to 5 when consistency/variance actually requires it).  The default after a correct validation is 1 run per arm; scale up only when consistency/variance requires it.  Same request, same region/GPU class, alternating order (A,B,A,B,A,B) to cancel drift, ≥35 s cooldown between runs (existing convention), fresh
   containers per run.
   Metrics per run:
   - `overlap_ms`, `precopy_wall_ms`, `sampling_end_wait_ms`, `join_wait_ms`
     (from `vae_early_activation_consumed` / reconciliation metadata);
   - `sampling_end.duration_ms` (sampling wall);
   - `vae_decode` wall and post-sampling→decode gap;
   - `transfer_count`, `fallback_reason` (must be absent/empty);
   - GPU allocated delta (`gpu_allocated_delta_bytes`).
3. **Decision inputs.** Report per-arm medians:
   - fraction of `precopy_wall_ms` that overlaps sampling (`overlap_ms / precopy_wall_ms`);
   - Δ sampling wall (B − A) — must be ≤ noise (no sampler slowdown);
   - Δ end-to-end (B − A) — the win condition (should be ≈ moved transfer time).
4. **Stop rules.** Any run failing the validation gates (missing/duplicate
   scheduled event, `transfer_count != 1`, fallback elected, image mismatch)
   → stop, do not scale up; treat as implementation issue.  If the first 3 B
   runs are inconsistent (>±15% overlap or sampling wall variance), add up to
   2 more B runs; beyond that, do not scale further without a new protocol
   revision.

NOT run as part of this task (per lane scope): no deploy, no Modal runs,
no commit.
