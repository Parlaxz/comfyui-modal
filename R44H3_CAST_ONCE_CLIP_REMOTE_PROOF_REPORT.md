# R44H3 ? Cast-Once CLIP Remote Proof Report

## Outcome

Run 1 was the required structural gate and **failed**. The stop rule was applied immediately: Runs 2 and 3 were not executed. No code/configuration changed after the paid request began and no redeployment occurred.

- Worktree: `comfyui-modal-r42`, branch `r42-golden-reconciliation`
- Successful deployment: **1**, fingerprint `860408f3dcfdf82820344a0f061433c707ac181d44d8473a90eb774b00795087`
- Profile: `r44-request-fastsafe`
- Run 1 request: `v2-benchmark-0-476f84af0e92`
- Run 1 artifact: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_12-11-30\run_0.json`
- Dynamic Gantt: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-24_12-11-30\dynamic_gantt_run_0.txt`
- Paid requests used: **1 of 3**; two unused

## Structural gate

| Requirement | Evidence | Result |
|---|---|---|
| Canonical SHA | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` | exact match |
| RuntimeStatus | `DEGRADED`; `loader_fallback_clip:fastsafetensors_direct_gpu->native_comfy; loader_observed_mismatch_clip` | **FAIL** |
| Requested CLIP loader | `fastsafetensors_direct_gpu` | present |
| Observed CLIP loader | `native_comfy` | **FAIL** |
| Fallback | `RuntimeError: RuntimeError: missing_key:model.embed_tokens.weight` | **FAIL** |
| Cast-once validation | `missing_key:model.embed_tokens.weight` | **FAIL** |
| True sampling start | absent; proxy interval used | **FAIL** |
| UNET | FastSafe observed; control path completed | control only |

The cast-once attempt correctly failed closed because the checkpoint key `model.embed_tokens.weight` was not found in the live namespace. Native Comfy fallback completed and produced the exact SHA, but this does not satisfy the R44H3 structural gate.

## Local verification and reconciliation

- Combined pre-deploy suite: **353 passed / 0 failed**
- Focused H3/H1/H2/Gantt suite: **59 passed**
- `py_compile`: **76/76 OK**
- TOML parse: **OK**
- v2ctl dry-run: **OK**
- Final static audit: **PASS** for nominal path
- Sampler reset: installed at first statement of each production request
- Retirement failure: fail-closed before publication
- R44F report/raw log: absent from worktree; R44E/H1/H2/G reports were reconciled

## Bounded validation

Nominal validation is deterministic sampling, not a full-model scan. Default is 256 elements per comparable tensor. For 398 tensors:

- sampled elements per side: `398 ? 256 = 101,888`
- live + staged sampled elements: `203,776`
- `validation_full_model_scan = false`
- `validation_sample_bytes = 203,776` (bounded sample-element accounting used for this report)
- deep validation is diagnostic-only via `COMFYMODAL_CLIP_CAST_ONCE_DEEP_VALIDATION`

## Run 1 foundational measurements

These are fallback-run measurements and are **not** valid cast-once cohort values.

| Metric | Run 1 |
|---|---:|
| Application wall | 93285.2 ms |
| Command?response | 98742.3 ms |
| CLIPLoader node | 7926.546 ms |
| CLIP outer encode | 7424.970 ms |
| CLIP inner forward | 2607.121 ms |
| CLIP load_models_gpu | 46.000 ms (fallback observation) |
| UNET source prep | 7574.5 ms |
| UNET broad H2D | 1061.1 ms |
| progress sampling | 3744.9 ms |
| sampler tail | 502.259 ms |
| sampler GC | 470.742 ms |
| sampler deepcopy | 16.379 ms |
| sampler CPU transfer | 0.138 ms / 2,088,960 bytes |
| VAE decode | 552.406 ms |
| output encode | 284.649 ms |

Cast-once FastSafe copy, construction split, load_sd cast, validation wall, residency wall, owner release, allocation delta, duplicate bytes, and single-representation metrics are UNKNOWN because the cast-once success event was never emitted.

## H2 telemetry and closures

Nine sampler step ticks and sampler-tail subtimings were durable. Authoritative `sampling_start`, `sampler_prep_phase`, `sampler_first_eval_start`, and true first-progress boundaries were absent, so the dynamic report correctly used the proxy interval and marked the true decomposition missing.

Fallback CLIP encode closure: outer `7425.0 ms`; load_models_gpu `46.0 ms`; inner forward `2607.1 ms`; residual `4771.8 ms (64.27%)`; closure failed. This is not a cast-once measurement.

## Complete Run 1 dynamic Gantt

```text
V2 DYNAMIC CRITICAL PATH GANTT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
request: v2-benchmark-0-476f84af0e92   profile: r44-request-fastsafe   artifact: run_0.json
FALLBACK RUN — loader fallback attempted for: clip
RUNTIME STATUS: DEGRADED reasons=loader_fallback_clip:fastsafetensors_direct_gpu->native_comfy,loader_observed_mismatch_clip

── FULL APPLICATION ──────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 380.0 ms | axis 25.8 s | origin = restore
····································································

Restore (application)                  │█                                                                   │ @+0.000s
  restore bootstrap                    │▋█▉                                                                 │ 969.1 ms @+0.123s
(unregistered) restore method          │██▉                                                                 │ 1100.6 ms @+0.000s · [background]
(unregistered) restore:early           │▏                                                                   │ 69.6 ms @+0.000s · [background]
(unregistered) v2_startup_post_snapsh… │▉█▉                                                                 │ 1032.6 ms @+0.070s · [background]
(unregistered) restore:eviction        │▏                                                                   │ 25.5 ms @+0.070s · [background]
(unregistered) restore:snapshot        │▏                                                                   │ 0.04 ms @+0.095s · [background]
(unregistered) clip_manifest_available │▏                                                                   │ 0.007 ms @+0.095s · [background]
(unregistered) restore:preamble        │▏                                                                   │ 27.4 ms @+0.095s · [background]
(unregistered) v2_startup_snapshot_ex… │  ▏                                                                 │ 1.309 ms @+1.054s · [background]
(unregistered) restore:preload         │  ▏                                                                 │ 0.737 ms @+1.092s · [background]
(unregistered) restore:finalize        │  ▏                                                                 │ 7.674 ms @+1.093s · [background]
request/setup                          │   ▉█▊                                                              │ 1007.4 ms @+1.171s
  remote method setup                  │   ▉▉                                                               │ 719.7 ms @+1.171s
  prompt executor cache setup          │    ▏▊                                                              │ 287.7 ms @+1.890s
(unregistered) request:identity-captu… │   ▏                                                                │ 0.32 ms @+1.171s · [background]
(unregistered) request:plan-deseriali… │   ▏                                                                │ 0.466 ms @+1.180s · [background]
(unregistered) request:setup-schedule  │   ▉▉                                                               │ 681.8 ms @+1.198s · [background]
(unregistered) request:executor-run    │    ▏███████████████████████████████████████████████████████████████│ 23,961 ms @+1.880s · [background]
(unregistered) pre_sampler_cache_key_… │    ▏                                                               │ 0.002 ms @+1.881s · [background]
(unregistered) executor:graph-executi… │    ▏██████████████████████████████████████████████████████████████▉│ 23,902 ms @+1.882s · [background]
(unregistered) v2_startup_first_promp… │    ▏██████████████████████████████████████████████████████████████▉│ 23,883 ms @+1.890s · [background]
UNET source prep                       │                           ▌███████████████████▌                    │ 7574.5 ms @+10.464s · [background]
CLIP outer encode                      │                           ▌███████████████████▏                    │ 7425.0 ms @+10.465s
  CLIP load_models_gpu (exact)         │                           ▏                                        │ 46.0 ms @+10.465s
  CLIP inner forward                   │                                        ▊██████▏                    │ 2607.1 ms @+15.276s
(unregistered) clip_tokenize_end       │                           ▍█▏                                      │ 580.6 ms @+10.475s · [background]
(unregistered) clip_scheduled_conditi… │                             ▉█████████████████▏                    │ 6827.7 ms @+11.060s · [background]
(unregistered) clip_gpu_prepare_end    │                             ▉██████████▎                           │ 4202.1 ms @+11.073s · [background]
(unregistered) CLIP forward            │                                        ▊██████▏                    │ 2606.1 ms @+15.276s · [background]
UNET H2D (broad window)                │                                               ▌██▎                 │ 1061.1 ms @+18.041s
sampler node→first progress (PROXY — … │                                                  ▌███▌             │ 1520.5 ms @+19.170s
progress sampling                      │                                                      ▌█████████▎   │ 3744.9 ms @+20.690s
post-sampling transition               │                                                                ▊▋  │ 502.7 ms @+24.435s
  RES4LYF sampler post-loop tail       │                                                                ▊▋  │ 502.3 ms @+24.435s
  executor dispatch → VAEDecode        │                                                                 ▏  │ 0.411 ms @+24.938s
VAE decode                             │                                                                 ▍█▏│ 552.4 ms @+24.938s
(unregistered) vae_decode_end          │                                                                 ▍█▏│ 552.1 ms @+24.938s · [background]
output encode                          │                                                                   ▊│ 284.6 ms @+25.491s
result persistence                     │                                                                   ▉│ 349.7 ms @+25.491s
(unregistered) output_encode_end       │                                                                   ▊│ 284.6 ms @+25.491s · [background]
(unregistered) result:assembly         │                                                                   ▏│ 65.0 ms @+25.776s · [background]
(unregistered) output_persist_end      │                                                                   ▏│ 7.335 ms @+25.776s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── UNET DETAIL ───────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 127.0 ms | axis 8.6 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 23,961 ms @+-8.584s · [background]
(unregistered) executor:graph-executi… │████████████████████████████████████████████████████████████████████│ 23,902 ms @+-8.582s · [background]
(unregistered) v2_startup_first_promp… │████████████████████████████████████████████████████████████████████│ 23,883 ms @+-8.574s · [background]
UNET source prep                       │███████████████████████████████████████████████████████████▋        │ 7574.5 ms @+0.000s · [background]
CLIP outer encode                      │▉█████████████████████████████████████████████████████████▌         │ 7425.0 ms @+0.001s
  CLIP load_models_gpu (exact)         │▍                                                                   │ 46.0 ms @+0.001s
  CLIP inner forward                   │                                     ▏████████████████████▍         │ 2607.1 ms @+4.812s
(unregistered) clip_tokenize_end       │▉███▋                                                               │ 580.6 ms @+0.011s · [background]
(unregistered) clip_scheduled_conditi… │    ▎█████████████████████████████████████████████████████▌         │ 6827.7 ms @+0.596s · [background]
(unregistered) clip_gpu_prepare_end    │    ▎████████████████████████████████▉                              │ 4202.1 ms @+0.609s · [background]
(unregistered) CLIP forward            │                                     ▏████████████████████▍         │ 2606.1 ms @+4.812s · [background]
UNET H2D (broad window)                │                                                           ▍███████▉│ 1061.1 ms @+7.577s
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── SAMPLER DETAIL ────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 84.8 ms | axis 5.8 s | origin = mono:0
····································································

(unregistered) request:executor-run    │████████████████████████████████████████████████████████████████████│ 23,961 ms @+-17.290s · [background]
(unregistered) executor:graph-executi… │████████████████████████████████████████████████████████████████████│ 23,902 ms @+-17.287s · [background]
(unregistered) v2_startup_first_promp… │████████████████████████████████████████████████████████████████████│ 23,883 ms @+-17.279s · [background]
sampler node→first progress (PROXY — … │▉████████████████▉                                                  │ 1520.5 ms @+0.001s
progress sampling                      │                 ▏████████████████████████████████████████████▏     │ 3744.9 ms @+1.521s
post-sampling transition               │                                                              ▉█████│ 502.7 ms @+5.266s
  RES4LYF sampler post-loop tail       │                                                              ▉█████│ 502.3 ms @+5.266s
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

── AUTO-DENSE ────────────────────────────────────────────────────────────────────────────────────────────────
scale: 1 char = 117.6 ms | axis 8.0 s | origin = mono:0
····································································

Restore (application)                  │█                                                                   │ @+0.000s
  restore bootstrap                    │ ▉███████▎                                                          │ 969.1 ms @+0.123s
(unregistered) restore method          │█████████▍                                                          │ 1100.6 ms @+0.000s · [background]
(unregistered) restore:early           │▋                                                                   │ 69.6 ms @+0.000s · [background]
(unregistered) v2_startup_post_snapsh… │▍████████▍                                                          │ 1032.6 ms @+0.070s · [background]
(unregistered) restore:eviction        │▎                                                                   │ 25.5 ms @+0.070s · [background]
(unregistered) restore:snapshot        │▏                                                                   │ 0.04 ms @+0.095s · [background]
(unregistered) clip_manifest_available │▏                                                                   │ 0.007 ms @+0.095s · [background]
(unregistered) restore:preamble        │▎▏                                                                  │ 27.4 ms @+0.095s · [background]
(unregistered) v2_startup_snapshot_ex… │        ▏                                                           │ 1.309 ms @+1.054s · [background]
(unregistered) restore:preload         │         ▏                                                          │ 0.737 ms @+1.092s · [background]
(unregistered) restore:finalize        │         ▏                                                          │ 7.674 ms @+1.093s · [background]
request/setup                          │         ▏████████▌                                                 │ 1007.4 ms @+1.171s
  remote method setup                  │         ▏██████▏                                                   │ 719.7 ms @+1.171s
  prompt executor cache setup          │                ▉█▌                                                 │ 287.7 ms @+1.890s
(unregistered) request:identity-captu… │         ▏                                                          │ 0.32 ms @+1.171s · [background]
(unregistered) request:plan-deseriali… │          ▏                                                         │ 0.466 ms @+1.180s · [background]
(unregistered) request:setup-schedule  │          ▉████▉                                                    │ 681.8 ms @+1.198s · [background]
(unregistered) request:executor-run    │               ▏████████████████████████████████████████████████████│ 23,961 ms @+1.880s · [background]
(unregistered) pre_sampler_cache_key_… │               ▏                                                    │ 0.002 ms @+1.881s · [background]
(unregistered) executor:graph-executi… │               ▏████████████████████████████████████████████████████│ 23,902 ms @+1.882s · [background]
(unregistered) v2_startup_first_promp… │                ▉███████████████████████████████████████████████████│ 23,883 ms @+1.890s · [background]
legend: █ busy bar (▏▎▍▌▋▊▉ sub-char precision); [background] marks off-critical-path activity; see CRITICAL PATH SUMMARY

══ CLIP ENCODE CLOSURE ══
parent: CLIP outer encode  7425.0 ms
  component CLIP load_models_gpu (exact)               46.0 ms
  component CLIP inner forward                         2607.1 ms
  sum(components)                               2653.2 ms
  residual                                      4771.8 ms (64.27% of parent)
  ✗ does not close (residual ≥5% or ≥250 ms)

LABEL CONFLICTS: none

══ TELEMETRY COMPLETENESS ══
CLIP descriptor                    MISSING (expected: trace.events:clip_fast_load_end.descriptor_wall_ms; closest proxy: trace.events:clip_fast_load_start.descriptor_wall_ms)
CLIP exact copy                    MISSING (expected: trace.events:clip_fast_load_end.fastsafe_copy_wall_ms; closest proxy: none)
CLIP construction                  MISSING (expected: trace.events:clip_fast_load_end.bind_ms; closest proxy: none)
CLIP storage identity              MISSING (expected: trace.events:clip_fast_load_end.sampled_tensor_count; closest proxy: none)
CLIP load_models_gpu               PRESENT
CLIP inner forward                 PRESENT
CLIP outer encode                  PRESENT
UNET source prep                   PRESENT
UNET exact copy                    PRESENT
UNET broad H2D                     PRESENT
UNET storage identity              PRESENT
sampler-start decomposition        MISSING (expected: fine-grained sampler-node→sampling sub-events; closest proxy: waterfall.sampler_node_to_sampling)
post-sampling decomposition        PRESENT
VAE decode                         PRESENT
output encode                      PRESENT
restore decomposition              PRESENT
request/setup decomposition        PRESENT
sampling wrapper start (true)      MISSING (expected: trace.events:sampling_start; closest proxy: pre_sampler_stages.sampling_start_monotonic_ns[proxy_first_progress])
sampler prep phase                 MISSING (expected: trace.events:sampler_prep_phase; closest proxy: waterfall.sampler_node_to_sampling[node→first-progress proxy])
first eval start                   MISSING (expected: trace.events:sampler_first_eval_start|unet_first_cuda_op; closest proxy: none)
first progress                     MISSING (expected: run_sample.full_trace.stages:t6_sampler_start; closest proxy: waterfall.sampling stage start)
per-step ticks                     PRESENT
sampler tail                       PRESENT
tail GC split                      PRESENT
tail deepcopy split                PRESENT
tail CPU transfer split            PRESENT
VAE load_models_gpu mono timestamps PRESENT

══ CRITICAL PATH SUMMARY ══
union-based critical path total: 17,133 ms (over 16 critical rows; overlapping rows NOT summed)
UNET source-prep overlap: 7424.961 ms (98.03% of prep) — background read hidden under CLIP encode
critical rows (time order):
  restore bootstrap                                      969.1 ms
  request/setup                                          1007.4 ms
  remote method setup                                    719.7 ms
  prompt executor cache setup                            287.7 ms
  CLIP outer encode                                      7425.0 ms
  CLIP load_models_gpu (exact)                           46.0 ms
  CLIP inner forward                                     2607.1 ms
  UNET H2D (broad window)                                1061.1 ms
  sampler node→first progress (PROXY — incl. prep + f…   1520.5 ms
  progress sampling                                      3744.9 ms
  post-sampling transition                               502.7 ms
  RES4LYF sampler post-loop tail                         502.3 ms
  executor dispatch → VAEDecode                          0.411 ms
  VAE decode                                             552.4 ms
  output encode                                          284.6 ms
  result persistence                                     349.7 ms
background:
  (unregistered) v2_startup_snap_true_enter_e…   activity_wall≈2226.2 ms · critical_path_contribution≈2226.2 ms
  (unregistered) v2_startup_custom_node_sourc…   activity_wall≈889.0 ms · critical_path_contribution≈889.0 ms
  (unregistered) v2_startup_comfyui_path_star…   activity_wall≈0.1 ms · critical_path_contribution≈0.1 ms
  (unregistered) v2_startup_backend_startup_e…   activity_wall≈47,830 ms · critical_path_contribution≈47,830 ms
  (unregistered) v2_startup_certificate_snaps…   activity_wall≈0.349 ms · critical_path_contribution≈0.349 ms
  (unregistered) v2_startup_dependency_valida…   activity_wall≈776.5 ms · critical_path_contribution≈776.5 ms
  (unregistered) v2_startup_cachedit_preparat…   activity_wall≈1621.8 ms · critical_path_contribution≈1621.8 ms
  (unregistered) restore method                  activity_wall≈1100.6 ms · critical_path_contribution≈131.5 ms
  (unregistered) restore:early                   activity_wall≈69.6 ms · critical_path_contribution≈69.6 ms
  (unregistered) v2_startup_post_snapshot_res…   activity_wall≈1032.6 ms · critical_path_contribution≈63.5 ms
  (unregistered) restore:eviction                activity_wall≈25.5 ms · critical_path_contribution≈25.5 ms
  (unregistered) restore:snapshot                activity_wall≈0.04 ms · critical_path_contribution≈0.04 ms
  (unregistered) clip_manifest_available         activity_wall≈0.007 ms · critical_path_contribution≈0.007 ms
  (unregistered) restore:preamble                activity_wall≈27.4 ms · critical_path_contribution≈27.4 ms
  (unregistered) v2_startup_snapshot_executio…   activity_wall≈1.309 ms · critical_path_contribution≈0 ms
  (unregistered) restore:preload                 activity_wall≈0.737 ms · critical_path_contribution≈0.737 ms
  (unregistered) restore:finalize                activity_wall≈7.674 ms · critical_path_contribution≈7.674 ms
  (unregistered) request:identity-capture        activity_wall≈0.32 ms · critical_path_contribution≈0 ms
  (unregistered) request:plan-deserialize        activity_wall≈0.466 ms · critical_path_contribution≈0 ms
  (unregistered) request:setup-schedule          activity_wall≈681.8 ms · critical_path_contribution≈0 ms
  (unregistered) request:executor-run            activity_wall≈23,961 ms · critical_path_contribution≈8506.4 ms
  (unregistered) pre_sampler_cache_key_build     activity_wall≈0.002 ms · critical_path_contribution≈0 ms
  (unregistered) executor:graph-execution        activity_wall≈23,902 ms · critical_path_contribution≈8506.4 ms
  (unregistered) v2_startup_first_prompt_exec…   activity_wall≈23,883 ms · critical_path_contribution≈8506.4 ms
  UNET source prep                               activity_wall≈7574.5 ms · critical_path_contribution≈149.5 ms
  (unregistered) clip_tokenize_end               activity_wall≈580.6 ms · critical_path_contribution≈0 ms
  (unregistered) clip_scheduled_conditioning_…   activity_wall≈6827.7 ms · critical_path_contribution≈0 ms
  (unregistered) clip_gpu_prepare_end            activity_wall≈4202.1 ms · critical_path_contribution≈0 ms
  (unregistered) CLIP forward                    activity_wall≈2606.1 ms · critical_path_contribution≈0 ms
  (unregistered) vae_decode_end                  activity_wall≈552.1 ms · critical_path_contribution≈0 ms
  (unregistered) output_encode_end               activity_wall≈284.6 ms · critical_path_contribution≈0 ms
  (unregistered) result:assembly                 activity_wall≈65.0 ms · critical_path_contribution≈0 ms
  (unregistered) output_persist_end              activity_wall≈7.335 ms · critical_path_contribution≈0 ms
legend: critical = on the measured critical path; background = wall time largely overlapping critical coverage; contribution = wall − overlap with the critical union

══ STAGE SUMMARY (canonical boundary semantics) ══
CLIP
  model/device prepare (load_models_gpu)           46.0 ms
  inner transformer forward                        2607.1 ms
  outer encode wrapper                             7425.0 ms
UNET
  source prep activity (background read)           7574.5 ms
  broad H2D window                                 1061.1 ms
  UNET prep uncovered contribution          149.5 ms (wall 7574.5 − overlap 7425.0)
SAMPLER
  progress window (first→last progress)            3744.9 ms
  post-loop tail (last progress → node return)     502.3 ms
  node → first progress [legacy interval]          1520.5 ms  [PROXY — end boundary is FIRST PROGRESS, not sampling start]
VAE
  decode                                           552.4 ms

```

## Comparison with R44E/R44F

| Metric | R44E | R44F | R44H3 Run 1 |
|---|---:|---:|---:|
| CLIP FastSafe copy | 1934.712 ms | skipped | UNKNOWN (fallback) |
| CLIP construction | 2670.544 ms | fallback/native | UNKNOWN |
| construction ex load_sd | UNKNOWN | UNKNOWN | UNKNOWN |
| load_sd cast | UNKNOWN | UNKNOWN | UNKNOWN |
| validation | full-model H1 path | UNKNOWN | bounded implementation; cast failed before success |
| load_models_gpu | 2283.612 ms | 2299.661 ms | 46.000 ms fallback |
| duplicate bytes before forward | 8,101,709,312-class | 8,101,709,312-class | UNKNOWN |
| inner forward | 2330.498 ms | UNKNOWN | 2607.121 ms |
| outer encode | 4689.879 ms | UNKNOWN | 7424.970 ms |
| CLIPLoader node | 4825.536 ms | UNKNOWN | 7926.546 ms |
| UNET source prep | 4827.587 ms | control | 7574.5 ms |
| sampler tail | 649.777 ms | UNKNOWN | 502.259 ms |
| VAE | 494.346 ms | UNKNOWN | 552.406 ms |
| output | UNKNOWN | UNKNOWN | 284.649 ms |
| application wall | 59169.2 ms | UNKNOWN | 93285.2 ms |

R44F?s requested report/raw log were unavailable, so no unsupported R44F claims are made.

## Verdict

The next single target is **CLIP cast-once checkpoint/live key-namespace reconciliation** for `model.embed_tokens.weight`. Preserve fail-closed behavior. Do not tune transport, sampler, UNET, VAE, or BF16/FP16 policy in this batch.

R44H3_H1_H2_RECONCILED = YES
R44H3_HOT_PATH_VALIDATION_BOUNDED = YES
R44H3_VALIDATION_SAMPLE_BYTES = 203776
R44H3_FULL_MODEL_VALIDATION_ON_HOT_PATH = NO

R44H3_DEPLOY_COUNT = 1
R44H3_PAID_REQUEST_COUNT = 1
R44H3_RUN1_STRUCTURAL_GATE_VALID = NO
R44H3_RUN2_EXECUTED = NO
R44H3_RUN3_EXECUTED = NO
R44H3_VALID_RUN_COUNT = 0

R44H3_CLIP_FASTSAFE_EXECUTED_ALL_VALID = NO
R44H3_CLIP_ADOPTION_MODE = UNKNOWN
R44H3_CLIP_CAST_COUNT = UNKNOWN
R44H3_CLIP_MISSING_COUNT = UNKNOWN
R44H3_CLIP_EXTRA_COUNT = UNKNOWN

R44H3_CLIP_FASTSAFE_COPY_MS_RUN1 = UNKNOWN
R44H3_CLIP_FASTSAFE_COPY_MS_RUN2 = UNKNOWN
R44H3_CLIP_FASTSAFE_COPY_MS_RUN3 = UNKNOWN
R44H3_CLIP_FASTSAFE_COPY_MS_MEDIAN = UNKNOWN
R44H3_CLIP_CONSTRUCTION_EX_LOADSD_MS_MEDIAN = UNKNOWN
R44H3_CLIP_LOAD_SD_CAST_MS_MEDIAN = UNKNOWN
R44H3_CLIP_VALIDATION_MS_MEDIAN = UNKNOWN
R44H3_CLIP_RESIDENCY_REGISTER_MS_MEDIAN = UNKNOWN
R44H3_CLIP_SOURCE_RELEASE_MS_MEDIAN = UNKNOWN
R44H3_CLIP_LOAD_MODELS_GPU_MS_MEDIAN = UNKNOWN
R44H3_CLIP_LOAD_MODELS_GPU_ALLOC_DELTA_BYTES_MAX = UNKNOWN
R44H3_CLIP_MODEL_SIZED_SECOND_MOVEMENT = UNKNOWN
R44H3_CLIP_DUPLICATE_BYTES_BEFORE_FORWARD_MAX = UNKNOWN
R44H3_CLIP_INNER_FORWARD_MS_MEDIAN = UNKNOWN
R44H3_CLIP_OUTER_ENCODE_MS_MEDIAN = UNKNOWN
R44H3_CLIP_NODE_MS_MEDIAN = UNKNOWN

R44H3_UNET_STORAGE_MATCH_ALL_VALID = UNKNOWN
R44H3_UNET_FASTSAFE_COPY_MS_MEDIAN = UNKNOWN
R44H3_UNET_NODE_MS_MEDIAN = UNKNOWN
R44H3_UNET_D15_CLEAN_ALL_VALID = UNKNOWN

R44H3_TRUE_SAMPLING_START_DURABLE_ALL_VALID = NO
R44H3_SAMPLER_ORCHESTRATION_PREP_MS_MEDIAN = UNKNOWN
R44H3_FIRST_EVAL_STARTUP_MS_MEDIAN = UNKNOWN
R44H3_FIRST_STEP_LATENCY_MS_MEDIAN = UNKNOWN
R44H3_PROGRESS_SAMPLING_MS_MEDIAN = 3744.9
R44H3_SAMPLER_TAIL_MS_MEDIAN = UNKNOWN
R44H3_SAMPLER_GC_MS_MEDIAN = UNKNOWN
R44H3_SAMPLER_DEEPCOPY_MS_MEDIAN = UNKNOWN
R44H3_SAMPLER_CPU_TRANSFER_MS_MEDIAN = UNKNOWN

R44H3_APP_WALL_MS_RUN1 = 93285.2
R44H3_APP_WALL_MS_RUN2 = UNKNOWN
R44H3_APP_WALL_MS_RUN3 = UNKNOWN
R44H3_APP_WALL_MS_BEST = 93285.2
R44H3_APP_WALL_MS_MEDIAN = 93285.2
R44H3_APP_WALL_MS_WORST = 93285.2

R44H3_DYNAMIC_GANTT_GENERATED_ALL_VALID = NO
R44H3_GENERATION_MATCH_ALL_VALID = NO
R44H3_EXACT_SHA_ALL_VALID = NO
R44H3_RUNTIME_STATUS_NOMINAL_ALL_VALID = NO
R44H3_ALL_EXECUTED_GATES_VALID = NO
R44H3_SINGLE_FINAL_CLIP_REPRESENTATION_PROVEN = NO
R44H3_READY_FOR_CLIP_TRANSPORT_EXPERIMENT = NO
R44H3_NEXT_SINGLE_TARGET = CLIP cast-once checkpoint/live key namespace reconciliation
