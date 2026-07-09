# Paired Cold-Run Protocol — ComfyUI x Modal

> Status: **DOCUMENTED, NOT EXECUTED**.  No paid Modal deployment is
> performed as part of this pass.  This document is a recipe the user
> can run later.  Do not infer a verdict from a single run; the
> protocol is a paired A/B design with at least 3 cold runs per
> configuration, alternating where practical.

## Purpose

Quantify the end-to-end wall-clock effect of the **exact-prompt CLIP
prefill** path on a true cold container, while holding every other
variable constant.  The output of this protocol is a comparison of
two configurations:

* **A** — Exact prefill enabled (`COMFYMODAL_EXACT_CLIP_PREFILL=1`).
* **B** — Exact prefill disabled, generic warmup preserved
  (`COMFYMODAL_EXACT_CLIP_PREFILL=0`,
  `COMFYMODAL_GENERIC_CLIP_WARMUP_FALLBACK=1`).

Both configurations must otherwise be identical.

## Non-negotiable constraints

The two configurations differ ONLY in the prefill flag.  Everything
below is held constant across A and B.

* Same source commit (one `git rev-parse HEAD` value, recorded).
* Same workflow JSON (single file, bit-for-bit).
* Same model stack: checkpoint, CLIP, UNET, VAE files (basenames and
  resolved paths identical).
* Same GPU class (e.g. `ComfyAPI_RTX_PRO_6000`).
* Same region (e.g. `us-east1`).
* Same output settings (format, dimensions, quality).
* Same image dimensions.
* Same sampler and steps.
* Same prompt (literal string, identical).
* Same seed.
* Same production options.
* Same cold-start definition.
* No warm containers.  `min_containers=0`.
* Same `scaledown_window`.
* Same `min_containers` and `scaledown_window` for all auxiliary
  services.

Recommended order: `A1, B1, A2, B2, A3, B3` to interleave cold-cache
effects across configurations.

## Cold-start definition

A "cold run" is a request that:

1. Starts a brand-new container (no prior Modal container has the
   restore session ID, no `_last_restore_timing` on the instance,
   no in-memory `clip_text_cache` state from a previous run).
2. Restores from snapshot (or builds from scratch if no snapshot
   applies) so the in-process image-snapshot path is exercised.
3. Executes the prompt and tears down.

After every cold run, **wait for the container to scale down** before
starting the next run.  Confirm via `modal app list` / `container ls`
that no in-flight container is still alive.

## Per-run measurement (mandatory fields)

For each run, record:

| Field | Source |
|---|---|
| `client_press_to_modal_entry` | client wall-clock from button press to first request byte on Modal side |
| `submit_to_remote_entry` | client submit timestamp to Modal entry timestamp |
| `restore_total` | `[comfyapp] restore sanity check done ... restore_total_ms=` |
| `exact_prefill_seed_encode` | `exact_prefill_encode_ms` in `__stages` |
| `graph_clip_encode` | `[timing] ... clip_encode` (or `clip_text_encode`) |
| `validation_total` | `graph_validate` in `[preflight.breakdown]` |
| `unet_future_submit_to_complete` | `production_unet_done_event_set` `future_total_ms` minus submit time |
| `graph_unet_wait` | `unet_future_wait_ms` |
| `prompt_start_to_sampler_start` | `[timing] prompt_start_to_sampler_start_ms` |
| `sampler` | `[timing] sampler_ms` |
| `post_sampler` | `sampler_end_to_outputs_collected_ms` |
| `remote_entry_to_return` | `modal_entry_to_modal_return_ms` |
| `complete_known_nonoverlap` | `known_nonoverlap_total` in `[waterfall]` |
| `complete_user_visible_wall_clock` | client-side observed total |

Diagnostic fields added by this pass — they are observed, not
estimates:

* `validation_unet_observed_overlap_ms` (from
  `[critical_path.observed.intervals]`)
* `exact_prefill_unet_observed_overlap_ms`
* `validation_completed_before_unet_future` (yes/no)
* `clip_ready_before_unet_future` (yes/no)
* `unet_future_completed_before_sampler` (yes/no)
* `unet_future_total_ms`
* `graph_unet_wait_duration_ms`
* `validation_duration_ms`
* `graph_clip_lookup_duration_ms`
* `exact_prefill_seed_duration_ms`

These diagnostic fields may be used as input to the comparison, but
they are observations, not causal savings.

## Comparison axes

The protocol must distinguish the following quantities; do not collapse
them:

1. **compute_removed** — wall-clock time the actual prompt execution
   no longer has to spend on CLIP encoding (only provable by running
   A and B and differencing the
   `prompt_start_to_sampler_start` minus `validation_duration`).
2. **restore_cost_moved** — wall-clock time that the restore path
   absorbed instead of the request path.  Observed as
   `exact_prefill_seed_duration_ms` in A.
3. **overlapping_work** — wall-clock time during which the request
   critical path AND the prefill encode were both active.  Observed
   as `exact_prefill_unet_observed_overlap_ms` (if the recorder is
   on; otherwise N/A).
4. **observed_sampler_start_difference** — paired difference of
   `prompt_start_to_sampler_start` between A and B.
5. **observed_end_to_end_difference** — paired difference of
   `remote_entry_to_return` (and `complete_user_visible_wall_clock`
   if available) between A and B.

## Verdict rules

A causal verdict is permitted only when all of the following hold:

* At least 3 valid cold runs per configuration.
* The two configurations' run order is interleaved.
* All non-flag variables are bit-for-bit identical.
* Each axis above is reported with mean, median, and the per-run
  paired difference (A − B).
* The verdict is framed as `observed` — e.g. "A observed
  `prompt_start_to_sampler_start` lower than B by X ms on N runs"
  — never "A saved X ms".

If any rule is not met, the protocol MUST report "verdict deferred" or
"verdict inconclusive" and must NOT emit a single-run saving number.

## What this protocol does NOT measure

* Compute time inside the UNET forward pass.
* Cost differences (Modal compute or transfer costs).
* Cold-cache effects that are not prefill-related.
* Future latency improvements from GPU warming or scale-down
  behaviour.

## Diagnostic flags for the runs

The runs should enable the new diagnostic flags so the structured
events are recorded for the comparison:

```
COMFYMODAL_CRITICAL_PATH_DIAG=1
COMFYMODAL_UNET_PHASE_DIAG=1
COMFYMODAL_VALIDATION_PHASE_DIAG=1
```

These flags are off by default.  When all are off, the new
`record()` calls short-circuit to a boolean check and emit nothing.

## Output file layout

For each configuration, save a `runs.jsonl` with one JSON object per
run, containing the per-run measurement table above plus the
diagnostic flags, commit hash, and run timestamp.

## When this protocol may be executed

* After the user manually confirms the production code path is
  stable.
* After at least one dry run on a non-production environment.
* With `min_containers=0` and explicit scale-down windows.
* With full logging to a destination the user can review.

## When this protocol must NOT be executed in this pass

* In automated CI without a human review of the JSONL.
* Without an interleaved run order.
* Without recording the source commit and config flags.

## Authors note

The exact-prefill behavior itself is not modified by this diagnostic
pass.  The protocol is designed to produce paired A/B evidence that
either supports, refutes, or refines the open hypotheses.  No
optimization should be applied as a consequence of a single
configuration's run.
