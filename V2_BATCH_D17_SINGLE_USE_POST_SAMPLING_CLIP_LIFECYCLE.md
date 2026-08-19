# V2 Batch D17 - Single-Use Post-Sampling Model Lifecycle Audit

Date: 2026-08-16

Scope: determine whether the post-sampling events labelled `clip_cold_*` are a
real CLIP reload, whether any work is dead on the single-use-container path,
and whether a production change is safe without changing decode semantics.

Mode: read-only source and artifact audit. No Modal deploy, no Modal request,
and no commit.

## Verdict

`DEAD_WORK_ON_SINGLE_USE_PATH=NO`

`ACTION=NONE`

The post-sampling `clip_cold_*` events do not show a CLIP reload. They are
generic wrappers installed around shared ComfyUI model-management functions.
The model actually loaded in the audited spans is the VAE
(`comfy.ldm.models.autoencoder.AutoencodingEngine`). The current trace does
not justify skipping the load, cache, or decode boundaries on single-use
containers.

## Direct Evidence

The three valid D14 artifacts were inspected:

- `comfymodal-data/benchmarks/runs/v2_2026-08-16_18-26-58/run_001_sample.json`
- `comfymodal-data/benchmarks/runs/v2_2026-08-16_18-29-25/run_001_sample.json`
- `comfymodal-data/benchmarks/runs/v2_2026-08-16_18-30-19/run_001_sample.json`

Across all three runs, the post-sampling load spans report `model_count=1`
and `clip_patcher_count=0`. The patcher-load metadata identifies
`comfy.ldm.models.autoencoder.AutoencodingEngine`, not a CLIP class.

Run 2 provides the clearest sequence:

```text
sampling_end
sampler_lane_released_at_sampling_end
vae_early_activation_scheduled
vae_early_activation_load_start
clip_cold_load_models_gpu_start
clip_cold_soft_empty_cache       wall_ms=885.345
clip_cold_soft_empty_cache       wall_ms=1.576
clip_cold_free_memory             wall_ms=3.110
clip_cold_patcher_partial_load_end
  model_class=AutoencodingEngine
  bytes_transferred=167639366
  resident_before=False
clip_cold_load_models_gpu_end
  model_count=1 clip_patcher_count=0
vae_early_activation_terminal
vae_early_activation_consumed
vae_decode_start
clip_cold_load_models_gpu_start
clip_cold_patcher_partial_load_end
  model_class=AutoencodingEngine
  bytes_transferred=167639366
  resident_before=True
clip_cold_load_models_gpu_end
  model_count=1 clip_patcher_count=0
vae_decode_end
```

No post-sampling event shows a transfer of the approximately 7.49 GiB CLIP
checkpoint. The observed approximately 167.6 MiB transfer is the VAE.

## Source Lifecycle

1. `runtime_executor.py:4883-4891` emits the authoritative `sampling_end`
   event. `runtime_executor.py:4968-4981` then releases the sampler lane and
   schedules VAE early activation.
2. `model_preload.py:19753-19756` runs the original ComfyUI
   `load_models_gpu([vae_patcher])` path in the early activation worker. The
   worker performs no decode and validates GPU residency before publishing the
   ready state.
3. `model_preload.py:13240-13277` keeps `VAEDecode` in normal graph order. Its
   demand hook only joins the VAE activation future and then falls through to
   the original node.
4. `nodes.py:310-318` calls `vae.decode(samples)`.
5. `comfy/sd.py:1045-1071` performs VAE decode. At line 1055, the native
   `VAE.decode` path explicitly calls
   `model_management.load_models_gpu([self.patcher], memory_required=...)`
   before executing `first_stage_model.decode`.

The second load boundary is therefore a native VAE decode precondition. It is
cheap when the VAE is already resident (`resident_before=True` in Run 2), but
it is not proven dead and is not CLIP work.

## The Long Interval

`comfymodal_runtime/clip_cold_path_forensics.py:742-762` labels shared
`free_memory` and `soft_empty_cache` wrappers with the `clip_cold_*` prefix.
Those wrappers do not establish that the target model is CLIP.

The underlying ComfyUI code shows:

- `comfy/model_management.py:799-841`: `free_memory` may unload models and
  calls `soft_empty_cache` after unloading.
- `comfy/model_management.py:843-918`: `load_models_gpu` computes memory
  requirements and calls `free_memory` before patcher loading.
- `comfy/model_management.py:1944-1960`: CUDA `soft_empty_cache` calls
  `torch.cuda.synchronize()`, `torch.cuda.empty_cache()`, and
  `torch.cuda.ipc_collect()`.

The trace proves that the approximately 885 ms interval is inside a
`soft_empty_cache` call. The source supports a device-wide synchronization and
cache-reclamation boundary. The current event does not split the time between
`synchronize`, allocator reclamation, and IPC collection, so a more specific
claim such as “fragmented-arena drain before cache reclamation” is not
established by this artifact.

## Single-Use Semantics

`COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1` controls Modal container disposal via
`modal_app.py:2793-2802` and `ModalRuntimeSpec.single_use_containers` at
`modal_app.py:2861-2885`. It changes container reuse and exit timing; it does
not change graph execution or make VAE loading unnecessary.

`target_inputs=1` and `max_inputs=1` only constrain input handling. The
single-use teardown documentation explicitly distinguishes those limits from
container exit behavior.

The request lifecycle also keeps response correctness ahead of teardown:

- `modal_app.py:16260-16298` performs post-stream release after the response
  stream is consumed.
- `modal_app.py:18065-18101` invokes that release from the async-generator
  boundary.
- The request release path at `modal_app.py:5605-5994` handles request cleanup
  and optional GPU release after the graph result exists.

Thus, single-use disposal cannot be used to remove work that occurs before the
VAE decode and result handoff.

## Candidate Decisions

| Candidate | Decision | Reason |
| --- | --- | --- |
| Skip post-sampling `clip_cold_*` events | No production change | They are instrumentation labels; the underlying calls are shared model-management boundaries. |
| Skip `soft_empty_cache` | Unsafe | The VAE load path relies on ComfyUI memory management and device-wide synchronization. |
| Skip the first VAE `load_models_gpu` | Unsafe | It is the explicit sampling-end VAE activation operation and establishes residency for the upcoming decode. |
| Skip the second VAE `load_models_gpu` inside decode | Unsafe/unproven | Native `VAE.decode` owns that precondition and also uses the memory demand to size decode batching. |
| Disable VAE early activation only for single-use containers | Counterproductive | It would expose the roughly 1 s VAE load at decode demand without removing the required decode load or the cache boundary. |
| Rename forensic events | Optional follow-up only | A label cleanup would improve diagnostics, but changing labels would alter existing D14 evidence and is not required for runtime correctness. |

## D15 Preservation

No D15 implementation was changed. The D15 coordinator remains responsible for
the request-scoped CLIP/UNET GPU critical section and retains its required
device-wide CLIP synchronization. This audit does not reopen D13, D15, or D16
strategy changes.

## Verification Plan

The evidence path is:

1. Reconcile event metadata against the three saved full traces.
2. Confirm the target model and call order in the source.
3. Run the focused D15 and CLIP-forensics/lifecycle tests.
4. Run Python compilation over the touched report-adjacent runtime files.

The conclusion is limited to the current instrumentation and source contract.
Separating `torch.cuda.synchronize()` from `empty_cache()` and
`ipc_collect()` would require finer-grained instrumentation and is not needed
to establish that the interval is VAE memory management rather than CLIP
reload.

## Verification Results

- Focused D15 plus CLIP-forensics/lifecycle suite: `67 passed, 2 warnings`.
- VAE sampling-first-step, CLIP restore, and CLIP hydration suite: `56 passed`.
- D15-only regression suite: `7 passed`.
- `python -m py_compile` passed for the audited runtime modules.
- `git diff --check` reports a pre-existing trailing-whitespace warning in
  `tests/test_cpu_snapshot_models.py`; the warning is outside this report.

```text
FILES_CHANGED = V2_BATCH_D17_SINGLE_USE_POST_SAMPLING_CLIP_LIFECYCLE.md only
PRODUCTION_RUNTIME_CHANGES = 0
MODAL_DEPLOYS = 0
MODAL_REQUESTS = 0
COMMIT = none
```
