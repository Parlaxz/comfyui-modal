# V1/V2 Performance Findings

Status: fact-only record of the controlled runs and code changes completed in this session.

No causal explanations are asserted below unless directly established by an artifact or test.

## Scope and run identity

The benchmark root is:

```text
C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs
```

### Corrected identity record

The runs from `2026-07-18_23-30-35`, `2026-07-18_23-31-31`, and `2026-07-18_23-33-39` were executed through the V1 bridge. Their artifacts record `class_name: "ComfyAPI_RTX_PRO_6000"`. They are not V2 results and are excluded from all V2 comparisons.

The actual V2 runs record the deployed diagnosis app and V2 class in execution events:

```text
app_name:  stable-modal-comfy-v2-diagnosis
class_name: ModalRuntimeEntrypointV2
```

Lifecycle records also contain `stable-modal-comfy-v2-shadow` / `ModalRuntimeEntrypoint` entries. The execution method records the diagnosis app / V2 class above.

## V1 baseline

Four cold runs are used. The fifth collected V1 run, `2026-07-18_21-06-55`, is excluded because its `submit2entry_ms` was `137,544 ms`.

| Run | Wall | Submit to entry | Restore | Pre-sampler | Sampler | Post-sampler | VAE decode | UNET wait | Materialization |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `21-05-52` | 21,789 | 10,764 | 5,412 | 3,964 | 3,443 | 1,781 | 472 | 319 | 16 |
| `21-09-58` | 20,673 | 9,952 | 5,357 | 3,852 | 3,399 | 1,707 | 347 | 291 | 24 |
| `21-10-57` | 22,822 | 11,871 | 6,784 | 3,882 | 3,410 | 1,698 | 408 | 296 | 20 |
| `21-11-54` | 19,772 | 9,136 | 4,910 | 3,939 | 3,407 | 1,668 | 349 | 443 | 18 |
| **Median** | **21,231** | **10,358** | **5,385** | **3,910** | **3,403** | **1,703** | **378** | **307** | **18.9** |

V1 artifacts used:

- `2026-07-18_21-05-52\compiled_raw_results.json`
- `2026-07-18_21-09-58\compiled_raw_results.json`
- `2026-07-18_21-10-57\compiled_raw_results.json`
- `2026-07-18_21-11-54\compiled_raw_results.json`

V1 timing source: `wall_trace`.

## Actual Testing 2 V2 baseline

Five cold runs are used. One warm-like run is excluded.

| Run | Wall | Restore | Sampler | VAE decode | CLIP encode | UNET wait | Materialization |
|---|---:|---:|---:|---:|---:|---:|---:|
| `00-15-41` | 130,596 | 1,446 | 3,696 | 532 | 2,121 | 0.31 | 22.2 |
| `00-19-08` r0 | 49,585 | 6,097 | 3,718 | 825 | 2,098 | 0.33 | 14.2 |
| `00-19-08` r1 | 39,152 | 1,080 | 3,738 | 388 | 2,739 | 0.36 | 13.0 |
| `00-19-08` r2 | 37,611 | 1,083 | 3,703 | 365 | 2,479 | 0.32 | 13.6 |
| `00-22-51` | 34,186 | 749 | 3,690 | 359 | 2,130 | 0.31 | 13.9 |
| **Median** | **39,152** | **1,083** | **3,703** | **388** | **2,130** | **0.32** | **13.9** |

Excluded:

- `2026-07-19_00-19-08` r3: `warm_like_unproven`, wall `13,230 ms`, CLIP encode `0.19 ms`.

Testing 2 V2 artifacts:

- `2026-07-19_00-15-41\compiled_raw_results.json`
- `2026-07-19_00-19-08\compiled_raw_results.json`
- `2026-07-19_00-22-51\compiled_raw_results.json`

Testing 2 V2 timing source: `timing_trace_fallback`.

The following fields were null or unavailable in all five baseline V2 runs:

- `submit2entry_ms`
- `pre_sampler_ms`
- `post_sampler_ms`
- `output_collection_total_ms`
- `remote_visible_ms`
- `exec_model_load_io_ms`
- populated `trace_id`

## Optimized V2 runs

The optimized deployment included RestorePlan deduplication, V2 validation certificates, and V2 prefill mode `none`.

| Run | Classification | Wall | Restore | Sampler | VAE decode | Materialization |
|---|---|---:|---:|---:|---:|---:|
| `09-57-08` | Cold, first process | 130,126 | 1,315 | 3,743 | 466 | 15.6 |
| `09-59-59` | Cold, cache/certificate repeat | 36,310 | 2,041 | 3,698 | 490 | 17.0 |
| `10-02-16` | Cold, snapshot-established | 30,841 | 1,224 | 3,696 | 392 | 20.8 |
| `10-09-30` r0 | Cold | 32,923 | — | 3,718 | — | — |
| **Median of four cold runs** |  | **34,617** | — | **3,706** | — | — |

Excluded:

- `2026-07-19_10-09-30` r1: `warm_like_unproven`, wall `11,415 ms`.

Optimized artifacts:

- `2026-07-19_09-57-08\compiled_raw_results.json`
- `2026-07-19_09-59-59\compiled_raw_results.json`
- `2026-07-19_10-02-16\compiled_raw_results.json`
- `2026-07-19_10-09-30\compiled_raw_results.json`

## Directly verified optimization markers

### RestorePlan publication deduplication

In the optimized repeat artifacts:

- Event: `restore_publish_cache_skip`
- `restore_publish`: `0.65–0.69 ms`
- Cache key included workspace `ws_228aedb01781`, app `stable-modal-comfy-v2-diagnosis`, and environment `main`.

The first optimized process run did not have a cache hit and recorded `restore_publish: 7,507.78 ms`.

### Validation certificate

The optimized repeat and snapshot-established artifacts contain:

- `cert_hit: true`
- `prompt_validation: 0.02 ms`

The first optimized process run contained `cert_hit: false` and `prompt_validation: 39.45 ms`.

### Prefill reduction

The optimized artifacts contain:

- `prefill_lane_mode: "none"`
- `prefill_skipped_encodes: 1`
- skip reason: `lane_mode=none`

UNET and CLIP model loading remained configured separately from the prefill lane.

## Code changes

The following changes were implemented and deployed:

- `canonical_execution.py`
  - Added an in-process, thread-safe RestorePlan publication cache.
  - Cache identity includes workspace, app, environment, and canonical plan identity.
  - Failed publication does not populate the cache.
- `comfymodal_runtime/model_preload.py`
  - Added `COMFYMODAL_V2_PREFILL_LANES` modes: `none`, `critical`, and `all`.
  - Default is `none`.
- `comfymodal_runtime/modal_app.py`
  - Added V2 validation certificate read/write and exact identity validation.
  - Certificate use is controlled by `COMFYMODAL_V2_VALIDATION_CERT`.
- `comfymodal_runtime/modal_transport.py`
  - Added explicit V2 environment lookup support and environment-aware handle caching.
- `benchmark_modal_e2e.py`
  - Preserves top-level `modal_options` and `_production_trace` when loading wrapped prompt files.

## Verification

Passed:

- `python -m unittest tests.test_runtime_canonical_v2 tests.test_v2_prompt_executor -q`
- Result: `59` tests passed.
- Python compilation passed for changed runtime files.
- `git diff --check` passed.
- Testing 2 deployment completed successfully:
  `https://modal.com/apps/testing2/main/deployed/stable-modal-comfy-v2-diagnosis`

An adjacent legacy preload suite currently reports five failures/errors in `comfyapp.py` expectations/signatures. That suite is outside the three V2 optimizations and was not changed by them.

## Observations established by the artifacts

1. The V1 sampler median was `3,403 ms` across the four included V1 cold runs.
2. The Testing 2 V2 sampler median was `3,703 ms` across five included V2 cold runs.
3. The optimized V2 sampler values remained between `3,696 ms` and `3,743 ms`.
4. V2 UNET wait was approximately `0.32 ms` in the baseline V2 artifacts.
5. RestorePlan publication and validation certificate markers show that the corresponding optimizations executed.
6. The optimized V2 wall values included `30,841 ms`, `32,923 ms`, `36,310 ms`, and `130,126 ms` across four cold runs.
7. V2 `submit2entry_ms` remained unavailable in the baseline and optimized Testing 2 artifacts.
8. V2 `pre_sampler_ms` and `post_sampler_ms` remained unavailable in the baseline and optimized Testing 2 artifacts.

## Findings not established

The artifacts do not establish:

- The cause of the approximately `300 ms` V2 sampler difference from V1.
- The exact split of V2 wall time between Modal queueing, lifecycle, and execution.
- The exact wall-time saving from the validation certificate.
- The exact wall-time saving from skipping prefill.
- A causal wall-time improvement from the optimized V2 runs, because V2 queue timing fields are unavailable and the optimized workflow hash differs from the baseline V2 workflow hash.
- V2/V1 parity, because the V1 and V2 workflow hashes differ and V2 critical-path fields are incomplete.
