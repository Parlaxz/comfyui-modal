# Phase 0 Step 3 Baseline

Date: 2026-08-03

## Result

Phase 0 Step 3 was deployed and exercised against the production-profile shadow app. The measured cold sample set contains three distinct fresh containers. All three produced one output image and completed with zero trace-handoff errors.

The scheduled third request in the first three-run batch was excluded from cold statistics because it reported `Fresh: NO` and reused the second container. A replacement request was run after a 60-second idle interval and reported `Fresh: YES`.

## Target and constraints

| Setting | Value |
|---|---|
| App | `stable-modal-comfy-v2-shadow` |
| Class | `ModalRuntimeEntrypointV2` |
| GPU | RTX PRO 6000 (`rtx-pro-6000`) |
| Profile | production |
| CPU model snapshot | enabled |
| `min_containers` | 0 |
| `scaledown_window` | 4 seconds |
| UNET | native/BF16 path retained |
| Snapshot model policy | CPU snapshots retained; no GPU eviction change |
| Base commit | `7b31ccb53a7a57bf940731caead3fec76fe40bd8` |

The deployment log confirmed the production profile, RTX PRO 6000 target, CPU model snapshots, and the shadow app/class identifiers. No production deployment settings were changed by this work.

## Code changes included

- `comfymodal_runtime/restore_plan.py`: sync and async plan-only publication preserve an existing snapshot seed when the incoming plan omits it.
- `canonical_execution.py`: restore publication cache reset/isolation, publication lifecycle markers, generation metadata, timing attribution, and honest no-publisher metadata.
- `comfymodal_runtime/unet_forward_probe.py`: observer-safe probe hooks and bounded request/object maps.
- Tests were updated or added for seed publication, cache/wiring behavior, local timing, and UNET probe behavior.
- Removed the unreferenced duplicate `tests/V2_CONSISTENT_SUB13_OPTIMIZATION_PLAN.md`.

## Warm/cache/profile run

Artifact directory: `../../comfymodal-data/benchmarks/runs/v2_2026-08-03_12-03-22/`

| Metric | Value |
|---|---:|
| `t3b_to_t8` | 11,214.687 ms |
| `wall_ms` | 206,236.8 ms |
| `restore_total_ms` | 1,460.219 ms |
| `pre_sampler_ms` | 6,303.921 ms |
| `sampler_ms` | 3,687.817 ms |
| `vae_decode_ms` | 481.795 ms |
| Trace handoff errors | 0 |

This run was used to establish the active profile and cache state and is not included in the cold median. Its local wall-clock and local publication fields contain large cross-boundary attribution values; the remote `t3b_to_t8` and stage fields are the meaningful timing values.

## Selected cold runs

Artifacts are under `../../comfymodal-data/benchmarks/runs/`.

| Run | Artifact | Fresh instance | `t3b_to_t8` | Wall | Restore | Pre-sampler | Sampler | VAE |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Cold 1 | `v2_2026-08-03_12-06-58/run_0.json` | yes | 5,899.466 ms | 7,470.1 ms | 1,460.219 ms | 1,449.196 ms | 3,703.695 ms | 267.909 ms |
| Cold 2 | `v2_2026-08-03_12-06-58/run_1.json` | yes | 20,169.181 ms | 26,262.5 ms | 1,127.567 ms | 15,095.142 ms | 3,708.902 ms | 507.245 ms |
| Cold 3 replacement | `v2_2026-08-03_12-10-09/run_0.json` | yes | 12,366.140 ms | 19,244.6 ms | 773.377 ms | 7,442.635 ms | 3,717.706 ms | 415.196 ms |

### Cold medians

| Metric | Median | Range |
|---|---:|---:|
| Primary `t3b_to_t8` | **12,366.140 ms** | 5,899.466–20,169.181 ms |
| User-facing wall | 19,244.6 ms | 7,470.1–26,262.5 ms |
| Restore | 1,127.567 ms | 773.377–1,460.219 ms |
| Pre-sampler | 7,442.635 ms | 1,449.196–15,095.142 ms |
| Sampler | 3,708.902 ms | 3,703.695–3,717.706 ms |
| VAE decode | 415.196 ms | 267.909–507.245 ms |

The large pre-sampler spread is consistent with cold model/file-cache variance. The sampler stage is stable across all three samples.

## Cache and freshness observations

- Cold 1 performed restore publication; subsequent requests reported `restore_publish_cache_hit=True` and did not perform another remote restore-plan publication.
- The first three-run batch used a 20-second gap. Its third request reported `Fresh: NO` and reused the second instance, so it is retained as an artifact but excluded from the cold table.
- The replacement request used a 60-second idle interval and reported `Fresh: YES`.
- The benchmark metadata reported `environment=(default)` because `COMFYMODAL_V2_ENVIRONMENT` was not set. The cache key still includes app/workspace/plan/seed identity; setting an explicit environment remains recommended for future deployments.

## Verification

- Focused changed-module suite: `299 passed in 10.79s`.
- `python -m py_compile canonical_execution.py comfymodal_runtime/restore_plan.py comfymodal_runtime/unet_forward_probe.py`: passed.
- `git diff --check`: passed.
- Read-only deployment review: approved.
- Broad `python -m pytest -q tests` was attempted but exceeded 600 seconds with unrelated environment-dependent failures; it was not used as the release gate.

## Artifact index

- Warm/profile: `../../comfymodal-data/benchmarks/runs/v2_2026-08-03_12-03-22/summary.json`
- Cold batch: `../../comfymodal-data/benchmarks/runs/v2_2026-08-03_12-06-58/summary.json`
- Cold replacement: `../../comfymodal-data/benchmarks/runs/v2_2026-08-03_12-10-09/summary.json`
