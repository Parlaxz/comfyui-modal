# Executive conclusion

All claims are code-derived unless explicitly labeled **measured** (from run artifacts) or **expected** (derived prediction pending runtime counter verification).

1. **Authoritative boundary.** The only currently-correct, always-on sampling boundary is the `SAMPLER_SAMPLE` wrapper `comfymodal_v2_sampling_timing` (`comfymodal_runtime\runtime_executor.py:2947-3434`). The `sampling_start`→`sampling_end` event pair includes: the post-start bookkeeping before the executor — VAE-prefetch scheduling, the pre-sampler hard-cutoff set, and callback-wrapper installation (`runtime_executor.py:3266-3340`) — then the full `KSAMPLER.sample` executor (`comfy\samplers.py:982-1001`), and the wrapper-`finally` work up to the `sampling_end` emit (`runtime_executor.py:3353-3362`). Loader/pre-sampler work and post-event diagnostic cleanup are excluded. **Measured** on two valid runs in `V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md`: attempt_0001 = 5004.6 ms, attempt_0000 = 5039.7 ms; the report's aggregate `sampling` row is min/median/max = 5004.6 / 5022.2 / 5039.7 (the "median" is the mean of the two valid values). This ~5.0 s interval is the reconciliation total for any per-step decomposition.
2. **Workflow identity discrepancy — resolved.** The pinned production workflow (`latest_benchmark_workflow.json`, also `c5_latest_benchmark_workflow.json`) uses `ClownsharKSampler_Beta` (node 1242) → sampler name `exponential/res_2s` → scheduler `bong_tangent` → 8 steps (node 937), CFG 1. This is **not** the upstream `sample_dpmpp_2m` path. The sampler is dispatched through the RES4LYF-registered `rk_beta` sampler function (`RES4LYF\beta\__init__.py:108` → `rk_sampler_beta.sample_rk_beta`), and `res_2s` has a 2-row RK tableau (`rk_coefficients_beta.py:1529-1545`): **expected** two model evaluations per sampling step. The code prediction is firm: 8 steps × 2 evals = **16 in-loop evaluations plus one final post-loop teardown evaluation = 17 model calls total** (see `# Per-step decomposition`). Still runtime-counter-verifiable, but there is no 14/15 uncertainty in the pinned configuration.
3. **CacheDiT.** The `CacheDiT_Model_Optimizer` node (137, model_type `Z-Image-Turbo`, warmup_steps=3, skip_interval=2) installs the **lightweight cache** which swaps the whole `NextDiT.forward` with `cached_forward` (`ComfyUI-CacheDiT\nodes.py:69-283`). **Expected** 17 calls → computes at calls {1,2,3,4,6,8,10,12,14,16} (10) and skips at {5,7,9,11,13,15,17} (7). Labeled **expected** pending runtime counter verification (`compute_count`/`skip_count` from `_get_lightweight_cache_stats`, `nodes.py:292-317`).
4. **SageAttention.** `PathchSageAttentionKJ` (node 1499, `auto`) only replaces the **attention kernel dispatch**. `optimized_attention_masked` is the module-level alias (`comfy\ldm\modules\attention.py:761`) of the selected `@wrap_attn`-decorated backend; the decorator definition (`attention.py:127-143`) routes to `transformer_options["optimized_attention_override"]` → KJNodes `attention_sage` (`model_optimization_nodes.py:59-...`) → `sageattn(...)` (line 32). QKV projection, Q/K RMSNorm, rope, reshape/repeat, output projection, block modulation/norms/gates, and the MLP are all outside the Sage kernel.
5. **Current metrics are not additive.** Progress-sourced `t6_sampler_start/end` + `sampler_ms` (`comfyapp.py:15236-15245`, `timing_trace.py:307-315`) measure the nested first-progress→last-progress sub-interval and exclude step-0 model work and the loop tail. `first_sampler_step` and `unet_first_cuda_op` are one-shot **markers**, not durations. `sampler_profile`/`guider_profile`/`deep_profile` accumulators (`comfyapp.py:16412-16593`) are gated-off nested segments that double-count by construction. The `sampling_end` `duration_ms` metadata is computed from a `t0` captured **before** `sampling_start` is emitted and **before** VAE-prefetch/cutoff bookkeeping (`runtime_executor.py:3248, 3266, 3275-3313`), so it is not equal to the event-pair duration; use event-pair monotonic deltas for reconciliation.
6. **Action.** Recommend **one** next step: implement one gated, non-overlapping diagnostic instrumentation pass (design in `# Proposed instrumentation`). Not optimization, not deployment, not loader work.

---

# Exact runtime call path

Reference paths used throughout (pinned current checkout):

| Path | Role |
|---|---|
| `comfyui-modal\comfyapp.py` | Modal container app; in-process executor, progress profiler, trace assembly |
| `comfyui-modal\comfymodal_runtime\runtime_executor.py` | Authoritative `SAMPLER_SAMPLE` timing wrapper |
| `comfyui-modal\comfymodal_runtime\unet_forward_probe.py` | `unet_first_cuda_op` / `unet_first_cuda_forward_complete` |
| `comfyui-modal\comfymodal_runtime\trace.py` | `RuntimeTrace` event recorder |
| `comfyui-modal\comfymodal_runtime\v2_waterfall.py` | Waterfall stage derivation (including `sampling`) |
| `comfyui-modal\timing_trace.py` | Legacy `Trace` / `TraceV4`, `sampler_ms` derivation |
| `comfyui-modal\production_workflow.py` | Production compile; RES4LYF dummy-init disable injection |
| `custom_nodes\RES4LYF\beta\samplers.py` | `ClownsharKSampler_Beta`, `SharkSampler`, `SharkGuider` |
| `custom_nodes\RES4LYF\beta\rk_sampler_beta.py` | `sample_rk_beta` loop (the `rk_beta` sampler) |
| `custom_nodes\RES4LYF\beta\rk_method_beta.py` | `RK_Method_Beta` / `RK_Method_Exponential`, model-call entry |
| `custom_nodes\RES4LYF\beta\rk_coefficients_beta.py` | `res_2s` tableau, `process_sampler_name` |
| `custom_nodes\RES4LYF\beta\rk_noise_sampler_beta.py` | `RK_NoiseSampler.prepare_sigmas` (`SIGMA_MIN` insertion) |
| `custom_nodes\RES4LYF\beta\__init__.py` | `extra_samplers["rk_beta"]` registration |
| `custom_nodes\RES4LYF\sigmas.py` | `bong_tangent_scheduler` |
| `custom_nodes\RES4LYF\__init__.py` | `bong_tangent` `SchedulerHandler` registration |
| `custom_nodes\ComfyUI-CacheDiT\nodes.py` | `CacheDiT_Model_Optimizer`, lightweight `cached_forward` |
| `custom_nodes\ComfyUI-KJNodes\nodes\model_optimization_nodes.py` | `PathchSageAttentionKJ`, `get_sage_func` |
| `custom_nodes\comfyui_lg_samplingutils\py\noise_injection.py` | `LGNoiseInjectionLatent` cfg-function patch |
| `comfy\samplers.py` | `KSAMPLER.sample`, `KSamplerX0Inpaint`, `sampling_function`, `calc_cond_batch`, `CFGGuider` |
| `comfy\model_base.py` | `BaseModel.apply_model` / `_apply_model` |
| `comfy\ldm\lumina\model.py` | `NextDiT.forward/_forward`, `JointTransformerBlock`, `JointAttention`, `FinalLayer` |
| `comfy\ldm\modules\attention.py` | `wrap_attn` decorator, `optimized_attention_masked` alias |
| `comfy\patcher_extension.py` | `WrappersMP.OUTER_SAMPLE / SAMPLER_SAMPLE / DIFFUSION_MODEL` |

Pinned workflow node chain (from `latest_benchmark_workflow.json`):

```
node 66   UNETLoader                z_image_turbo_bf16.safetensors
node 1484 ModelSamplingAuraFlow     shift=3
node 137  CacheDiT_Model_Optimizer  model_type=Z-Image-Turbo, warmup_steps=3, skip_interval=2, enable=True, print_summary=True
node 1499 PathchSageAttentionKJ     sage_attention=auto, allow_compile=False
node 1262 LGNoiseInjectionLatent    strength=0.25, start_percent=0, end_percent=0.1
node 1242 ClownsharKSampler_Beta    sampler_name=exponential/res_2s, scheduler=bong_tangent, steps=8 (node 937), cfg=1,
                                    eta=0.6 (node 1402), bongmath=True, seed=1006800347249813, sampler_mode=standard
```

Execution call path (remote container; the local entry is `__init__.py:_execute_job`, line 2243):

1. `ComfyAPI.run_prompt` → `_execute_in_process` (`comfyapp.py:15891`) → `self._executor.execute(...)` (`comfyapp.py:16713`) → `PromptExecutor` runs the sampler node.
2. `ClownsharKSampler_Beta.main` (`RES4LYF\beta\samplers.py:1746`) → builds the KSAMPLER object via `comfy.samplers.ksampler("rk_beta", {...})` (`samplers.py:1603`; `sampler_name`/`rk_type` = `exponential/res_2s` → `process_sampler_name` → `res_2s`, `rk_coefficients_beta.py:312-329`) → `SharkSampler.main` (`samplers.py:2079`).
3. `SharkSampler.main` (`samplers.py:153-...`) computes `sigmas = get_sigmas(work_model, "bong_tangent", steps=8, denoise=1.0)` (`samplers.py:344`; `RES4LYF\sigmas.py:1397-1429`). `bong_tangent` is registered as a ComfyUI `SchedulerHandler(handler=sigmas.bong_tangent_scheduler, use_ms=True)` (`RES4LYF\__init__.py:21-24`); the handler returns 9 sigmas for 8 steps (steps+2 internal adjustment minus one, `sigmas.py:4076-4098`), the last sigma is 0.0. `RK_NoiseSampler.prepare_sigmas` (`rk_noise_sampler_beta.py:785-834`) then inserts `SIGMA_MIN` immediately before the trailing zero (lines 817-827, insertion branch 820-824), producing **10 sigmas** for the pinned configuration. The RES4LYF dummy-sampler-init warm-up (`samplers.py:314-327`) is disabled in production by the injected `disable_dummy_sampler_init` option (`production_workflow.py:_apply_res4lyf_dummy_sampler_transform`, lines 1061-1166).
4. `guider = SharkGuider(work_model)` (`samplers.py:559`; class at `samplers.py:87-110`) → `guider.sample(noise, x.clone(), sampler, sigmas, ...)` (`samplers.py:657-659`).
5. `CFGGuider.sample` (`comfy\samplers.py:1268`) → `OUTER_SAMPLE` wrapper dispatch (`comfy\samplers.py:1311-1316`) → CacheDiT `_cache_dit_outer_sample_wrapper` (`ComfyUI-CacheDiT\nodes.py:438-567`): clones/resets config, auto-detects `num_inference_steps = len(sigmas)-1 = 8` (`nodes.py:480-483`), and enables the lightweight cache on the NextDiT transformer (`_enable_cache_dit` `nodes.py:625` → `_enable_lightweight_cache` `nodes.py:69-289`, replacing `transformer.forward` with `cached_forward` `nodes.py:215`).
6. → `outer_sample` (`comfy\samplers.py:1232`) → `prepare_sampling` (`comfy\samplers.py:1233`) → `inner_sample` (`comfy\samplers.py:1214`) → `SAMPLER_SAMPLE` wrapper dispatch (`comfy\samplers.py:1224-1229`) → comfyui-modal `_COMFYMODAL_V2_SAMPLING_WRAPPER` (`comfymodal_runtime\runtime_executor.py:3078`): emits `sampling_start` (line 3266), arms the one-shot stall watchdog (line 3218), sets the pre-sampler hard cutoff `_sampling_cutoff_perf_ns` (line 3309-3313), and wraps the per-step callback to emit `first_sampler_step` (lines 3321-3340).
7. → `KSAMPLER.sample` (`comfy\samplers.py:982-1001`): `noise_scaling(sigmas[0], ...)` (line 992) → `self.sampler_function(model_k, noise, sigmas, extra_args=..., callback=k_callback, ...)` (line 999) = `rk_sampler_beta.sample_rk_beta` (`RES4LYF\beta\rk_sampler_beta.py:111`; the `rk_beta` name registered at `RES4LYF\beta\__init__.py:108`; `k_callback` = per-step ComfyUI callback at `comfy\samplers.py:997`).
8. `sample_rk_beta` setup (lines 244-580) then the loop `while step < num_steps:` (line 581); per iteration the tableau loop `for row in range(RK.rows - RK.multistep_stages - RK.row_offset + 1)` (line 867) makes one model call per row. **Active RK call sites in the pinned workflow**: the standard-path call `eps_[row], data_[row] = RK(x_tmp, s_tmp, x_0, sigma, ...)` at line 1665 (once per row, so two per step), and the final post-loop call `eps, denoised = RK(x, NS.sigma_min, x, NS.sigma_min)` at line 2112 in teardown. The other `RK(...)` sites in the file (line 99 in `init_implicit_sampling`, 1191/1200/1222/1231 sync-mode, 1481-1482 flow-mode, 1631 `direct_pre_pseudo_guide`, 1640/1718 lure-mode, 1644 `protoshock`, 1656 `preshock`, 1908 `postshock`, 2084 `guide_step_cutoff`) are gated by implicit/guide/shock options and modes that are **not active** in the pinned workflow (no guides, `implicit_steps_*`=0, `res_2s` non-implicit, no shock options set). Per-step ComfyUI callback at line 1986 (`preview_callback`, callback dispatch at line 2239), progress-bar update at line 2067.
9. Each active `RK(...)` call = `RK_Method_Exponential.__call__` (`rk_method_beta.py:887-917`) → `self.model_denoised(...)` (call at line 901; def at line 137; standard-path `self.model(...)` at **line 241**). `self.model` is **not** a `ModelPatcher`; it is the `model_k = KSamplerX0Inpaint(...)` wrapper built in `KSAMPLER.sample` (`comfy\samplers.py:984`). The model chain is: `RK_Method_Exponential.__call__` (`rk_method_beta.py:887-917`) → `model_denoised` (`rk_method_beta.py:137`, `self.model` at 241) → `KSamplerX0Inpaint.__call__` (`comfy\samplers.py:633-642`, inner `self.inner_model(...)` at 639) → `CFGGuider.__call__` (`comfy\samplers.py:1201-1202`) → `CFGGuider.outer_predict_noise` (`comfy\samplers.py:1204-1209`) → `SharkGuider.predict_noise` (`RES4LYF\beta\samplers.py:99-110`) → `sampling_function` (`comfy\samplers.py:608-626`; with CFG 1 and `disable_cfg1_optimization` unset the single-cond path `calc_cond_batch` at line 619) → `calc_cond_batch` (def `comfy\samplers.py:207`; `model.apply_model` at line 334) → `BaseModel.apply_model` (`comfy\model_base.py:186-191`) → `BaseModel._apply_model` (`comfy\model_base.py:193-235`) → `self.diffusion_model(xc, t, context=..., transformer_options=...)` (line 231) = `NextDiT.forward` (`comfy\ldm\lumina\model.py:802-807`), which dispatches through `DIFFUSION_MODEL` wrappers (lines 803-807) — including CacheDiT `_cache_dit_diffusion_model_wrapper` (`ComfyUI-CacheDiT\nodes.py:570-618`) — then `_forward` (`model.py:810-859`).
10. The `unet_first_cuda_op` marker fires on the first CUDA forward entry from the NextDiT forward pre-hook (`unet_forward_probe.py:413-589`; hook installed by `install_nextdit_forward_pre_hook`, line 633-664).
11. `NextDiT._forward` (`model.py:810-859`): `t_embedder` (826), `patchify_and_embed` (840; `embed_cap`/`embed_all` 639-699, `context_refiner` loop 759-760, `noise_refiner` loop 784-790, `x_embedder` 691) → main block loop over `self.layers` (846-855, 32 `JointTransformerBlock`s) → `final_layer` (857) → `unpatchify` (858).
12. Inside each `JointTransformerBlock.forward` (`model.py:298-351`): modulation `adaLN_modulation` (321), `attention_norm1`+`modulate` → `JointAttention.forward` (`model.py:122-165`) → `attention_norm2`+gate+residual (323-330); `ffn_norm1`+`modulate` → `FeedForward.forward` (`model.py:168-222`) → `ffn_norm2`+gate+residual (331-335).
13. `JointAttention.forward` (`model.py:122-165`): `qkv` Linear (142), split/reshape (141-152), `q_norm`/`k_norm` (154-155), `apply_rope` (157), KV repeat (160-162), `optimized_attention_masked(...)` (163), `out` Linear (165). `optimized_attention_masked` is a module-level **alias** (`comfy\ldm\modules\attention.py:761`) bound to the selected `@wrap_attn`-decorated backend (`wrap_attn` definition at `attention.py:127-143`; backend selection at 739-761). When `transformer_options["optimized_attention_override"]` exists (set by `PathchSageAttentionKJ.patch`, `KJNodes ...\model_optimization_nodes.py:129`) the decorator dispatches to the override (lines 137-138) → KJNodes `attention_sage` (`model_optimization_nodes.py:59-...`) → `sage_func` = `sageattn(...)` (`model_optimization_nodes.py:32`). This `sageattn` call is the **only** code owned by SageAttention.
14. `sampling_end` is emitted in the wrapper `finally` (`runtime_executor.py:3353-3428`) with `duration_ms` (line 3361) and the waterfall `sampling` stage is derived from the event pair (`v2_waterfall.py:513-519`).

---

# Current known timing model

Existing timing artifacts that touch the sampling path, with what each actually measures (all host wall-clock; sync-free):

| Artifact | Emitter | Interval measured | Classification |
|---|---|---|---|
| `sampling_start`/`sampling_end` events | `runtime_executor.py:3266, 3362` | `SAMPLER_SAMPLE` wrapper: VAE-prefetch bookkeeping + `executor()` + emit overhead (see t0 caveat) | **authoritative** (~5.0 s, **measured** on two valid runs: attempt_0001 = 5004.6 ms, attempt_0000 = 5039.7 ms; aggregate min/median/max = 5004.6 / 5022.2 / 5039.7 per `V2_EXCLUSIVE_OWNER_TOTAL_WALL_6_RUN_REPORT.md`) |
| `sampling_end.duration_ms` metadata | `runtime_executor.py:3361-3362` | `monotonic_ns() - t0` where `t0` is captured at line 3248, **before** `sampling_start` is emitted (3266) and before VAE-prefetch (3275) and cutoff bookkeeping (3309) | overlapping/mismatched with the event pair; the event-pair delta and this metadata differ by the pre-start gap + VAE-prefetch + emit overhead. **Confirmed mismatch** — for reconciliation always use event-pair monotonic deltas |
| waterfall `sampling` stage | `v2_waterfall.py:513-519` | `sampling_start`→`sampling_end` event-pair delta (falls back to `sampler_ms`/`sampling_ms`, then to `sampling_end.duration_ms`) | same as authoritative when events present |
| `t6_sampler_start`/`t6_sampler_end` + `sampler_ms` | `comfyapp.py:15236-15245` (progress-sourced at 15337-15347); `timing_trace.py:285, 307-315, 348-350` | first progress callback → last progress callback (tqdm `progress_bar.update(1)` per RK loop iteration, `rk_sampler_beta.py:2067`) | **misleading**: nested sub-interval; excludes step-0 model work (the first progress fires only after step 0's two evals), the pre-loop setup, and the post-loop tail |
| `sampler_prep_ms`/`denoise_ms`/`teardown_ms` | `comfyapp.py:15320-15332` | derived from sampler-node start → first progress → last progress → node end | overlapping with the above; node-start is the graph `executing` event, not the sampling boundary |
| `first_sampler_step` event | `runtime_executor.py:3321-3340` | none — marker at the first per-step ComfyUI callback (= end of step 0 after both evals) | **marker, not a duration** |
| `unet_first_cuda_op` event | `unet_forward_probe.py:447-517` | none — marker at first CUDA forward entry; carries `elapsed_ms` = distance from `load_models_gpu` demand start (`set_unet_gpu_demand_start`, line 134), not a duration of the event | **marker, not a duration** |
| `unet_first_cuda_forward_complete` | `unet_forward_probe.py:306-411` | `wall_ms` = host wall time of the **first** forward (pre-hook→post-hook) | first-forward duration, one-shot |
| `sampler_first_progress` critical-path event | `comfyapp.py:15251-15265` | marker at first progress callback (uses `first_progress_ns`) | marker |
| `sampler_profile` (`_profiled_ksampler_sample`) | `comfyapp.py:16418-16442` | `setup_ms` (t0→first callback), `step_N_ms` (callback gaps), `teardown_ms`, `total_ms`; gates `KSAMPLER.sample` | **overlapping** with authoritative; `total_ms` ≈ wrapper interval minus outer bookkeeping; gated off by default |
| `guider_profile` (`_gwrap` segments) | `comfyapp.py:16454-16472` | accumulators over `CFGGuider.sample`/`outer_sample`/`inner_sample`/`prepare_sampling`/`cleanup_models` | **nested/overlapping**: `guider_sample` ⊇ `guider_outer_sample` ⊇ (`prepare_sampling`, `guider_inner_sample` ⊇ SAMPLER_SAMPLE ⊇ sampler_profile); summing any two pairs double-counts |
| `deep_profile` (`_dp_wrap`) | `comfyapp.py:16480-16593` | `get_additional_models`, `estimate_memory`, `load_models_gpu` | pre-sampler, non-sampling (gated off) |
| `pre_sampler_critical_path_ms` | `timing_trace.py:174-246` | pre-sampler node walls clipped at `_sampling_cutoff_perf_ns` (`runtime_executor.py:3309-3313`) | pre-sampler, disjoint from sampling |

Key structural facts:

- The authoritative ~5.0 s interval starts at the `SAMPLER_SAMPLE` wrapper entry (after graph-join/CLIP/loader work) and ends when `KSAMPLER.sample` returns. It encloses: VAE-prefetch scheduling (CPU-only, `runtime_executor.py:3275-3303`), noise scaling, the entire RK loop (expected 16 in-loop model evals across 8 steps), the final post-loop teardown eval (expected, `rk_sampler_beta.py:2112`), and the final `inverse_noise_scaling` (`comfy\samplers.py:1000`).
- `sampler_ms` (progress-sourced) sits strictly inside the authoritative interval: `[first_progress, last_progress]` ≈ `[end of step 0, end of last loop iteration]`. It therefore cannot reconcile to ~5 s on its own and must never be summed with the authoritative interval.
- All current host timers are sync-free (`time.monotonic_ns`/`time.perf_counter_ns`/`time.time`); no `torch.cuda.synchronize()` exists in the sampling path.

---

# Per-step decomposition

### res_2s cadence (expected)

- `res_2s` tableau: `a = [[0,0],[a2_1,0]]`, `b = [[b1,b2]]`, `ci = [0, c2]` (`rk_coefficients_beta.py:1529-1545`) → `RK.rows = 2`, `row_offset = 1` (explicit, non-implicit; `rk_method_beta.py:309`).
- Loop bound: `for row in range(RK.rows - RK.multistep_stages - RK.row_offset + 1)` = `range(2)` for `res_2s` with `multistep_stages=0` (`rk_sampler_beta.py:867`). Each row issues exactly one model call via `RK(x_tmp, s_tmp, x_0, sigma, ...)` (line 1665) unless `s_tmp == 0` (early break, lines 1088-1089).
- **Expected per-step cadence: 2 model evaluations per sampling step.**
- **Sigma schedule and loop count (firm, code-derived):** `bong_tangent(8)` initially yields 9 sigmas ending in 0.0 (`sigmas.py:4076-4098`); `RK_NoiseSampler.prepare_sigmas` (`rk_noise_sampler_beta.py:785-834`) inserts `SIGMA_MIN` immediately before the trailing zero (lines 817-827, insertion at 820-824), yielding **10 sigmas** `[s0..s7, SIGMA_MIN, 0]`. Then `num_steps = len(sigmas)-2 = 8` (`rk_sampler_beta.py:407`) → the loop `while step < num_steps` (line 581) runs **8 iterations** (steps 0..7), each with 2 row evals = **16 in-loop model evaluations**, one per user-visible sampling step.
- **Final teardown evaluation (firm, code-derived):** after the loop, step == 8 == `len(sigmas)-2`, `sigmas[-1] == 0`, `sigmas[-2] == SIGMA_MIN == NS.sigma_min`, and `INIT_SAMPLE_LOOP` is False, so the conditional final call at `rk_sampler_beta.py:2106-2114` fires by construction; `EO("skip_final_model_call")` is unset (no extra options in the pinned workflow), so the else branch executes `eps, denoised = RK(x, NS.sigma_min, x, NS.sigma_min)` (line 2112). This is the **17th model call**, a post-loop evaluation distinct from the 8 user-visible sampling steps.
- **Expected total: 17 model evaluations** (16 in-loop + 1 final teardown). This is what CacheDiT's `call_count` is expected to observe. Still runtime-counter-verifiable, but the prediction is firm for the pinned configuration; there is no 14/15 alternative path here (the `s_tmp == 0` break at line 1088 cannot trigger because every row's substep sigma is non-zero in this schedule).

### Step lifecycle (per loop iteration)

```
step {s} start
├── pre-model: NS.set_sde_step / RK.set_coeff(rk_type,h,c1,c2,c3,step,sigmas) / NS.set_substep_list
│             (rk_sampler_beta.py:695-697) + guide/option bookkeeping (688-693)
├── model_eval {s,0}  (row 0)   RK(x_tmp, s_tmp, x_0, sigma)  line 1665
│     └── (see UNET forward decomposition)
├── gap {s,0→1}: solver math between rows (newton_iter "pre" line 1090, noise_scaling lying factors
│             1724-1734, guide substep processing 1737-1740, RK.update_substep 1763)
├── model_eval {s,1}  (row 1)   RK(x_tmp, s_tmp, x_0, sigma)  line 1665
├── post-model / solver:
│     x_next = x_[rows - multistep_stages - row_offset + 1]          line 1897
│     rebound_overshoot_step                                          line 1898
│     eps/denoised recompute                                          lines 1904-1905
│     optional bong_iter (BONGMATH=True default; up to 100 tensor iterations,
│       gated by NS.s_[row] > sigma_min and NS.h < sigma_max/2)       lines 1874-1889
│     noise swap NS.swap_noise_step                                    line 1936
│     per-step ComfyUI callback via preview_callback                   lines 1985-1986 (dispatch 2239)
│     data_prev_ recycle / rk swap check / state updates               lines 2017-2059
│     progress_bar.update(1)                                          line 2067
└── step += 1                                                         line 2068
```

### Step-1 / first-forward one-time work (expected, code-derived)

1. `KSAMPLER.sample` entry: `model_k = KSamplerX0Inpaint(...)` and `noise_scaling(sigmas[0], ...)` (`comfy\samplers.py:984-992`).
2. `SharkSampler.main`: conditioning copy (`samplers.py:377-378`), `process_conds` (via `inner_sample`, `comfy\samplers.py:1218`), initial noise generation `generate_init_noise(...)` (`samplers.py:550-556`).
3. `sample_rk_beta` setup: `RK_Method_Beta.create` (`rk_sampler_beta.py:323`, `rk_method_beta.py:110-125`), `RK.init_cfg_channelwise` (line 324), `RK_NoiseSampler.prepare_sigmas`/`init_noise_samplers` (lines 335, 368-370), `LatentGuide` construction + `init_guides` (lines 428-433), first-iteration buffer allocation `x_, data_, eps_, eps_prev_` (line 727-729) and `data_prev_` zeros (line 746).
4. First loop iteration: `INIT_SAMPLE_LOOP` allocations (line 727-748), first `RK.set_coeff` (line 696), first `NS.set_sde_step` (line 695).
5. First model evaluation → first `NextDiT` forward with CUDA input: triggers `unet_first_cuda_op` (pre-hook, `unet_forward_probe.py:447-517`), first-time torch kernel launches / lazy compilation, and the first CacheDiT `cached_forward` compute (stores `last_result`).
6. First `progress` and per-step callback events fire only **after** step 0's two evals (lines 1986/2067), so neither `first_sampler_step` nor `t6_sampler_progress_start` can bound the first-step cost.

### Final teardown evaluation (post-loop, expected)

After the loop exits (step == 8), the final call at `rk_sampler_beta.py:2106-2114` runs the 17th evaluation in the **teardown** segment — it is **not** one of the 8 user-visible sampling steps and produces no `progress_bar.update(1)` (line 2114 is commented out). It is followed by `progress_bar.close()` (line 2120), the final per-step ComfyUI callback (line 2122-2124), and the `.to(model_device)` moves (lines 2116-2118). Instrumentation must place this eval under `sampling_teardown`, keyed distinctly from the step evals (see `# Proposed instrumentation`).

---

# UNET forward decomposition

`NextDiT._forward` (`comfy\ldm\lumina\model.py:810-859`) per model evaluation:

| Segment | Code | Notes |
|---|---|---|
| embeddings | `t_embedder` (826), `clip_text_pooled_proj`+`time_text_embed` (829-836), `patchify_and_embed` (840) → `cap_embedder` (641), `x_embedder` (691), `rope_embedder`/`EmbedND` (652, 698, 610) | per-eval |
| context refiner | `for layer in self.context_refiner` (759-760) | `n_refiner_layers` = 2, no modulation |
| noise refiner | `for layer in self.noise_refiner` (784-790) | 2 blocks, modulation=True |
| main blocks | `for i, layer in enumerate(self.layers)` (846-855) | `n_layers` = 32 `JointTransformerBlock`s; `total_blocks`/`block_type` set in `transformer_options` (843-844) |
| output | `final_layer` (857) + `unpatchify` (858) | `FinalLayer` at `model.py:354-...`: LayerNorm + Linear |

Per `JointTransformerBlock.forward` (`model.py:298-351`) the work splits into:

- **attention path**: `adaLN_modulation` (321) → `attention_norm1` RMSNorm + `modulate` (325) → `JointAttention` (324) → `attention_norm2` + `gate.tanh()` + residual add (323-330).
- **MLP path**: `ffn_norm1` + `modulate` (333) → `FeedForward` (`w1`,`w3` → SiLU gate → `w2`, `model.py:168-222`) → `ffn_norm2` + `gate.tanh()` + residual add (331-335).

Per `JointAttention.forward` (`model.py:122-165`):

- QKV projection: `self.qkv(x)` Linear (142), then split/reshape (141-152).
- `q_norm`/`k_norm` RMSNorm (154-155).
- `apply_rope` (157), KV repeat for GQA (160-162).
- **kernel**: `optimized_attention_masked(...)` (163) — the only call SageAttention can own (see below).
- Output projection `self.out(...)` (165).

First-forward one-time work: first CUDA kernel launches per op, CacheDiT warm-up compute (calls 1-3), `unet_first_cuda_op`/`unet_first_cuda_forward_complete` bookkeeping (`unet_forward_probe.py`).

---

# CacheDiT behavior

Source: `ComfyUI-CacheDiT\nodes.py`.

- `CacheDiT_Model_Optimizer.optimize` (`nodes.py:897-1046`) builds a `CacheDiTConfig` with `user_warmup_steps=3`, `user_skip_interval=2` (from the workflow), stores it in `model_options["transformer_options"]["cache_dit_turbo"]`, and installs an `OUTER_SAMPLE` wrapper (`nodes.py:1035-1039`) plus a `DIFFUSION_MODEL` wrapper (`nodes.py:1040-1044`).
- At sampling start, `_cache_dit_outer_sample_wrapper` (`nodes.py:438-567`) resets the global `_lightweight_cache_state` (lines 466-475), detects `num_inference_steps = len(sigmas)-1` = 8 (lines 480-483), and calls `_enable_cache_dit` (line 510) → for `NextDiT` the **lightweight path** `_enable_lightweight_cache` (line 689-697, 691-696) replaces `transformer.forward = cached_forward` (line 283), saving the original as `_original_forward` (line 96).
- `cached_forward` (`nodes.py:215-283`): increments `call_count`; `if call_id <= warmup_steps` → compute; else `steps_after_warmup = call_id - warmup_steps; should_skip = (steps_after_warmup % skip_interval == 0)` (lines 241-242); if skip and `last_result` is not None → return cached result (lines 244-260), else compute (lines 262-280). Noise injection is 0.0 for Z-Image (`nodes.py:169`, 249).
- **Expected call schedule for 17 calls, warmup=3, skip_interval=2** (code-derived from lines 215-283):

| call | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| steps_after_warmup | — | — | — | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
| action | C | C | C | C | S | C | S | C | S | C | S | C | S | C | S | C | S |

  → **Expected 10 computes (1,2,3,4,6,8,10,12,14,16) and 7 skips (5,7,9,11,13,15,17).** The 17th call is the final teardown evaluation (`rk_sampler_beta.py:2112`); `steps_after_warmup = 14`, `14 % 2 == 0` → skip. This is **expected pending runtime counter verification**: the `_get_lightweight_cache_stats` counters (`total_steps`/`computed_steps`/`cached_steps`, `nodes.py:292-317`) are logged after sampling (`nodes.py:531-543`) and are the authoritative check on the firm 17-call prediction above.
- **Skip semantics**: a skipped call returns the cached output tensor (`.detach()` copy stored at lines 229-237) from the previous compute, **bypassing the entire `NextDiT._forward`** — embeddings, refiners, all 32 blocks, attention, MLP, and finalization — while ComfyUI/sampler harness code around it still runs. CacheDiT therefore does not profile the UNET internals on skip calls; instrumentation must record `compute-or-skip` explicitly.
- The `DIFFUSION_MODEL` wrapper `_cache_dit_diffusion_model_wrapper` (`nodes.py:570-618`) only tracks `current_step` and applies noise injection when `noise_scale > 0` (0 for this workflow); it adds negligible overhead.

---

# SageAttention behavior

Source: `comfy\ldm\modules\attention.py`, `ComfyUI-KJNodes\nodes\model_optimization_nodes.py`.

- `PathchSageAttentionKJ.patch` (`model_optimization_nodes.py:118-131`) sets `model_options["transformer_options"]["optimized_attention_override"] = attention_override_sage` (line 129). No global monkeypatch.
- `optimized_attention_masked` is a module-level alias (`attention.py:761`) of the selected `@wrap_attn`-decorated backend; the decorator definition is `attention.py:127-143`. When `optimized_attention_override` is in `transformer_options`, control transfers to the override (lines 137-138) — this is the dispatch for every `JointAttention` kernel call.
- KJNodes `attention_sage` (`model_optimization_nodes.py:59-...`, itself `@wrap_attn` but invoked via `.__wrapped__`): dtype guard/cast fp32→fp16 (63-65), reshape to `HND`/`NHD` layouts (66-75), then `sage_func` = `sageattn(q, k, v, is_causal=False, attn_mask=..., tensor_layout=...)` (line 32 for `auto`), then output reshape (76-...).
- **Scope**: SageAttention owns **only** the fused attention kernel (QKᵀ, scaling/softmax, PV). Everything around it is outside Sage and inside the same forward:
  - QKV projection `self.qkv` (`model.py:142`), split/reshape (`141-152`);
  - `q_norm`/`k_norm` RMSNorm (`154-155`), `apply_rope` (`157`), KV repeat (`160-162`);
  - output projection `self.out` (`165`);
  - block modulation `adaLN_modulation`, norms, gates, residual adds (`model.py:321-335`);
  - the entire `FeedForward` MLP (`model.py:168-222`);
  - embeddings, refiners, final layer, unpatchify (`model.py:826-858`).
- Consequence: an "attention kernel" timer around the Sage call measures only the fused kernel; attributing block time to Sage would misattribute QKV/norm/rope/out/MLP work.

---

# CPU / Python / synchronization overhead

Code-derived (no measurement needed for existence; magnitudes must be measured by the proposed pass):

1. **Per-step GPU→CPU synchronizations**: `c2 = (-h_prev1_no_eta / h_no_eta).item()` etc. in `rk_coefficients_beta.py:1404, 1422-1423, 1441-1442`, plus `calculate_res_2m_step` (`rk_method_beta.py:454`, `.item()` at 472) and `calculate_res_3m_step` (`rk_method_beta.py:493`, `.item()` at 513-514) — each `.item()` forces a device sync once per step; the tableaus are rebuilt per step (`RK.set_coeff`, `rk_method_beta.py:263-312`, called from `rk_sampler_beta.py:696`) with `.to(dtype/device)` allocations.
2. **Per-step Python-heavy bookkeeping**: `NS.set_sde_step`/`NS.set_substep_list` (`rk_sampler_beta.py:695-697`), guide mask/slice extraction with `.item()` calls (e.g., lines 1184, 1874), option lookups `EO(...)` per row (string-parsed, `RES4LYF\helper.py:26`).
3. **Per-step callback + progress**: the per-step ComfyUI callback (`preview_callback` → `callback(...)`, `rk_sampler_beta.py:2239`) builds a dict and **converts `denoised` to `torch.float32`** (`denoised_callback.to(torch.float32)`, line 2239); `latent_preview.prepare_callback` (`samplers.py:593-596`) may encode preview images; `progress_bar.update(1)` (`rk_sampler_beta.py:2067`) drives tqdm → ComfyUI global progress hook (`comfyapp.py:17880-17895`) → `send_sync("progress")` → `_on_sync` (`comfyapp.py:17842-17873`) → `_note_progress_event` (`comfyapp.py:15290`) and a queue put to the streaming forwarder. Python + websocket per step. (Production `progress_min_interval_ms: 500` throttles the sink, `comfyapp.py:16641`, not the local recorder.)
4. **Allocations**: per step, `RK.set_coeff` allocates `A/B/C/U/V` tensors (`rk_method_beta.py:299-304`); `x_`, `data_`, `eps_`, `eps_prev_` are step-stable buffers (allocated once, line 729). `bong_iter` (`rk_method_beta.py:607-648`) loops up to 100 iterations of tensor math when active (`rk_sampler_beta.py:1874-1889`).
5. **Sync-free host timers**: the current production timers never call `torch.cuda.synchronize`; all durations are host-clock deltas, so they measure wall time including any device idle, not GPU busy time. The proposed CUDA-event layer (below) adds exactly **one** outer `torch.cuda.synchronize()` and must be labeled diagnostic.
6. **Watched worker/GC**: `x`, `eps`, `denoised` are moved to `model_device` and back at the loop end (`rk_sampler_beta.py:2116-2118`); `RK_Method_Exponential.__call__` moves `x`/`sub_sigma` `.to(self.model_device)` per call (`rk_method_beta.py:901`).

---

# Proposed instrumentation

Goal: a single gated diagnostic pass that produces a **strictly nested, non-overlapping** decomposition of the authoritative ~5.0 s `sampling_start`→`sampling_end` interval, with host `perf_counter_ns` boundaries as the reconciliation truth and optional CUDA-event GPU intervals with no inner synchronization.

### Gate

- One flag: `COMFYMODAL_SAMPLING_DEEP_PROFILE` with levels `off|steps|blocks` (file `runtime_config/sampling_deep_profile.txt` or env var), read via the existing `_resolve_runtime_flag`/`_resolve_runtime_string` mechanism (`comfyapp.py:3162-3191`) so it can be toggled per run without code edits. Default `off`. Alternatively reuse `COMFYMODAL_PROFILE_LEVEL` (`timing_trace.py:683-704`); prefer a dedicated flag so existing levels are untouched.
- All events go through the existing `RuntimeTrace.emit`/`emit_at` (`comfymodal_runtime\trace.py:78-194`) with `monotonic_ns` + `wall_unix_ns`, plus a per-request diagnostic buffer written to the run artifact — no new transport.

### Boundaries (Level A — per sampling step)

Placed inside `sample_rk_beta` (`RES4LYF\beta\rk_sampler_beta.py`) around the loop at line 581, the active standard-path per-row model call at line 1665, the final teardown model call at line 2112, and the RK call boundary (`rk_method_beta.py:887-917` / `model_denoised` 137-251, `self.model` at 241). All boundaries are `time.perf_counter_ns()` on the sampler thread — **no synchronization required** because they are host-clock deltas on one thread and nest exactly.

Metric names (start/end pairs; `{s}` = step index 0..7, `{r}` = evaluation/row index 0..1; `final` = the post-loop teardown evaluation):

```
sampling_start / sampling_end                          (exists; authoritative total)
sampling_setup_start / sampling_setup_end              (sampling_start → step_0 start)
sampling_step_{s}_start / sampling_step_{s}_end
sampling_step_{s}_pre_model_start / _end               (step start → eval {s,0} start)
sampling_step_{s}_eval_{r}_start / sampling_step_{s}_eval_{r}_end
sampling_step_{s}_gap_{r-1→r}_start / _end             (eval end → next eval start; row solver math)
sampling_step_{s}_post_model_start / _end              (last eval end → step end: solver update,
                                                        bong_iter, noise swap, callback, progress_bar)
sampling_teardown_start / sampling_teardown_end        (last step end → sampling_end)
sampling_teardown_eval_final_start / _end              (the 17th model call at rk_sampler_beta.py:2112,
                                                        nested in sampling_teardown)
```

Per-step reconciliation (must equal, within tolerance):

```
step_total = pre_model + eval_{r=0} + gap_{0→1} + eval_{r=1} + post_model + step_residual_ms
sampling_total ≈ sampling_setup + Σ step_total + sampling_teardown + sampling_residual_ms
teardown_eval_final ⊆ sampling_teardown
```

`step_residual_ms` and `sampling_residual_ms` are **derived arithmetic values, not spans** (gaps can be discontiguous; see the residual naming rule in Level B). A negative value signals overlap/error in the span hierarchy and is reported as such, never clamped.

Because `res_2s` has **two** model calls per step, the design keys every child span to an explicit evaluation index `{r}` — a single contiguous pre/model/post triple per step is not sufficient; the `gap_{0→1}` span is defined so no wall time is double-attributed between the two evals. The final teardown evaluation is a distinct span (`{r}=final`) outside the step loop.

**Absent-span semantics**: any row/eval that does not fire — e.g., the `s_tmp == 0` break at `rk_sampler_beta.py:1088-1089` dropping row 1, or the final call at 2106-2114 not firing — must be recorded explicitly as an absent span (`eval_present=false` metadata on the parent `eval`/`teardown_eval_final` span), never silently merged into `gap`/`post_model`/`teardown`/`residual`. For the pinned configuration the code prediction is that all 17 evals fire (16 in-loop + 1 final); the absent-span rule exists so any deviation is visible rather than absorbed into residuals.

### Boundaries (Level B — inside a model evaluation)

Placed inside `RK_Method_Exponential.__call__`/`model_denoised` (`rk_method_beta.py:887-917` / def 137-251, `self.model` at 241) and `NextDiT._forward` (`comfy\ldm\lumina\model.py:810-859`). Default mode (`steps`) records only the prep/forward/tail triples; `blocks` mode adds the per-block hierarchy below.

```
sampling_step_{s}_eval_{r}_prep_start / _end           (RK call entry → NextDiT forward entry: dtype/device
                                                        .to(), cfg-channelwise, model_options assembly)
sampling_step_{s}_eval_{r}_forward_start / _end        (NextDiT.forward entry → exit)
sampling_step_{s}_eval_{r}_tail_start / _end           (forward exit → RK call exit: eps anchoring,
                                                        denoised recompute, return)
sampling_teardown_eval_final_*                        (same triple, with {r}=final)
```

Inside forward (`blocks` level only; nested in `forward`):

```
..._forward_embeddings_start / _end                   (826-840: t_embedder, cap/x embedder, rope)
..._forward_refiners_start / _end                     (759-760 context_refiner + 784-790 noise_refiner)
..._forward_blocks_start / _end                       (846-855 main layer loop; PARENT of all block_i spans)
..._forward_blocks_block_{i}_start / _end             (i = 0..31; strictly nested in _forward_blocks)
..._forward_blocks_block_{i}_pre_attention_start / _end     (model.py:321 adaLN_modulation + 325 attention_norm1
                                                              + modulate; before the JointAttention call)
..._forward_blocks_block_{i}_attention_start / _end         (model.py:324 JointAttention incl. QKV, q/k norm,
                                                              rope, kernel, out)
..._forward_blocks_block_{i}_between_attention_mlp_start / _end  (model.py:323/329-330 attention_norm2 +
                                                              gate_msa.tanh() + residual add; then 333 ffn_norm1 +
                                                              modulate; between attention and FeedForward)
..._forward_blocks_block_{i}_mlp_start / _end               (model.py:332 FeedForward)
..._forward_blocks_block_{i}_post_mlp_start / _end          (model.py:331/334-335 ffn_norm2 + gate_mlp.tanh() +
                                                              residual add)
..._forward_output_start / _end                       (857-858 final_layer + unpatchify)
```

The norm/modulation/gate/residual work is **not** one contiguous span: it is split around the attention and MLP calls into three explicitly non-overlapping contiguous spans per block — `pre_attention`, `between_attention_mlp`, `post_mlp` — with the exact code regions above (modulated path, which is the pinned workflow's main-block configuration; the non-modulated refiner variant at `model.py:336-350` splits identically around its attention/FFN calls). These three spans, plus `attention` and `mlp`, form a strict contiguous partition of `block_{i}`.

All residuals are **derived arithmetic values, not spans** (gaps can be discontiguous, so no `_start/_end` naming is used):

```
block_{i}_residual_ms   = block_{i} total − (pre_attention + attention + between_attention_mlp + mlp + post_mlp)
blocks_residual_ms      = blocks total − Σ_i block_{i} total
forward_residual_ms     = forward total − (embeddings + refiners + blocks + output)
step_residual_ms        = step_total − (pre_model + eval_{r=0} + gap + eval_{r=1} + post_model)
sampling_residual_ms    = sampling total − (setup + Σ step_total + teardown)
```

A negative derived residual signals overlap/error in the span hierarchy and is reported as such, never clamped.

Category totals are **derived sums over the interleaved per-block spans**, reported as computed values in the artifact, **not** recorded as contiguous spans:

```
..._forward_blocks_attention_total = Σ_i block_{i}.attention                     (derived)
..._forward_blocks_mlp_total       = Σ_i block_{i}.mlp                           (derived)
..._forward_blocks_norm_gate_total = Σ_i (block_{i}.pre_attention
                                          + block_{i}.between_attention_mlp
                                          + block_{i}.post_mlp)                  (derived)
```

Reason: per-block spans are strictly sequential inside the block loop (block 0 pre_attention→attention→between→mlp→post, then block 1, ...); a contiguous aggregate "attention" or "norm" span would interleave with sibling spans and cannot be nested. The block-loop parent `_forward_blocks` owns the derived `blocks_residual_ms`, and each block's `block_{i}_residual_ms` absorbs launch/other gaps — no gap span is synthesized between blocks.

Inside attention (`blocks` mode only, per block `{i}`):

```
..._forward_blocks_block_{i}_attention_qkv_start / _end         (model.py:142 qkv Linear)
..._forward_blocks_block_{i}_attention_qknorm_rope_start / _end (154-162 q/k norm, rope, repeat)
..._forward_blocks_block_{i}_attention_kernel_start / _end      (163 optimized_attention_masked — the only span
                                                                  that may be Sage-owned; boundary placed inside
                                                                  KJNodes attention_sage around sageattn,
                                                                  model_optimization_nodes.py:60-...)
..._forward_blocks_block_{i}_attention_out_start / _end         (165 out Linear)
```

- **Noise-control rule**: no per-block or per-tensor spans at `steps` level (default), so default runs carry no per-tensor/per-kernel noise. `blocks` mode records all 32 per-block spans per compute eval (a compute eval is the only kind with block children; skip evals have none).
- **CacheDiT interaction**: `cached_forward` (`ComfyUI-CacheDiT\nodes.py:215-283`) must expose two extra marker pairs — `..._cachedit_decision_start/_end` (call_count increment + warmup/skip arithmetic, sub-µs) and `..._compute_or_skip` = `compute` (the `_original_forward` call) or `skip` (the cached return). On `skip`, no Level-B children are emitted; the eval span is just `decision + skip`. This makes skip evals explicitly distinguishable from compute evals in the report.
- **SageAttention instrumentation**: place the kernel span inside the KJNodes `attention_sage` function (or measure `optimized_attention_masked` call duration at `model.py:163` and label it `kernel+dispatch`). Do not add instrumentation inside the `sageattn` library itself.

### Sync requirements and CUDA-event realization

- **Host layer (authoritative)**: all Level A/B spans use `time.perf_counter_ns()` on the sampler thread; zero synchronization, zero CUDA API calls. These deltas are the reconciliation truth.
- **CUDA-event layer (optional, gated with `blocks` mode)**: events are recorded **only for GPU-bearing spans** — the eval/forward and per-block/attention spans that enclose CUDA work. CPU-only spans (`sampling_setup`, `pre_model`, `post_model`, `cachedit_decision`, all `gap` spans, and teardown bookkeeping) get **no** CUDA events. One `torch.cuda.Event(enable_timing=True)` pair per GPU-bearing span, recorded on the current stream around the span. **No `torch.cuda.synchronize()` and no `.synchronize()`/`.elapsed_time()` calls between spans.**
- **Realization order (preserves the authoritative measurement)**: the terminal end-event of the last GPU-bearing span is recorded on the current stream **before the executor returns**, so the recorded intervals bracket all sampler GPU work. `sampling_end` is then emitted at its existing location (`runtime_executor.py:3362`) **without any wait**. Only **after** the `sampling_end` emit — in the wrapper's post-boundary diagnostic cleanup (still inside the wrapper `finally`, after line 3362) — does the single realization pass run: one `torch.cuda.synchronize()` followed by `elapsed_time()` for every recorded pair. **No synchronization is placed at `sampling_teardown_end` or anywhere within `sampling_start`→`sampling_end`.**
- **Cost placement**: this post-boundary sync is instrumentation overhead **outside** the reconciliation total (`sampling_end − sampling_start`) and may delay the next stage (VAE decode / graph continuation); therefore it is used only on gated diagnostic runs (`COMFYMODAL_SAMPLING_DEEP_PROFILE=blocks`), never in production timing.
- **Host-GPU delta attribution**: for any GPU-bearing span, the delta between its host duration and its CUDA-event duration is a **derived arithmetic value** reported as that span's enclosing parent **residual** (documented as launch/idle/residency) — never assigned to a gap span, never silently absorbed, and never emitted as a span. A negative host−GPU delta signals overlap/error.
- **Event volume (bounded)**: in `blocks` mode, one compute eval records the top-level GPU-bearing spans — forward(1) + embeddings(1) + refiners(1) + blocks(1) + 32×(block + pre_attention + attention + between_attention_mlp + mlp + post_mlp)(192) + output(1) ≈ **197 event pairs**; if the four attention sub-spans (qkv / qknorm_rope / kernel / out) also record events, the per-block count rises to 10, giving up to ≈ **325 event pairs per compute eval**. At the expected 17 calls / 10 computes that is ≈ 1,970-3,250 event pairs (≈ 3,940-6,500 `Event.record()` calls) per run, bounded and independent of tensor size. Skip evals add zero events. `Event.record()` is **not free** — each record has small nonzero CPU overhead (stream marker + bookkeeping) that lands inside the enclosing host span deltas; it does not perturb GPU stream execution order, and the single post-boundary sync is the only added synchronization.

### Nesting and reconciliation summary

- All children are strictly nested inside their declared parent (verified by a post-pass that sorts spans by `monotonic_ns`, checks containment, and rejects overlapping siblings). No span is shared between two parents; `sampler_profile`/`guider_profile`/`deep_profile` (`comfyapp.py:16412-16593`) remain disabled during diagnostic runs so they cannot double-attribute. Residuals (block/forward/step/sampling and host−GPU deltas) are **never emitted as spans** — they are derived arithmetic values, and a negative value signals overlap/error.
- Reconciliation targets: `sampling` total = 5004.6-5039.7 ms (**measured** on two valid runs; aggregate min/median/max = 5004.6 / 5022.2 / 5039.7); expected composition = `sampling_setup` + 8 × `step_total` + `sampling_teardown` (containing the final teardown eval) + residuals. Expected 17 evals (16 in-loop + 1 final), 10 computes / 7 skips per the CacheDiT counters. Report per-eval mean/median/max and compute-vs-skip totals; all residuals explicit.
- Output: the diagnostic buffer is serialized into the run artifact alongside the existing trace (e.g., `_sampling_deep_profile` block in the result dict, merged into meta by the existing `_finish_job` path, `__init__.py:2019+`) so the parent orchestrator can consume it without new transport.

---

# Optimization candidates

Ranked by **expected potential, confidence, risk** (qualitative; no speculative numeric savings).

| Rank | Candidate | Expected potential | Confidence | Risk | Basis |
|---|---|---|---|---|---|
| 1 | Verify CacheDiT skip cadence with runtime counters, then validate skip evals actually avoid block/attention/MLP work (compute-vs-skip eval timing from Level A/B) | High (7 of 17 expected forwards skipped) | Medium (counters must still verify the firm 17-call prediction) | Low (measurement only before any tuning) | `ComfyUI-CacheDiT\nodes.py:215-283, 292-317` |
| 2 | Remove or amortize per-step GPU→CPU `.item()` syncs in tableau construction (`rk_coefficients_beta.py:1404,1422-1423,1441-1442`; `rk_method_beta.py:472, 513-514`) | Medium | Medium (numerical-equivalence care required; fp math on device must match host) | Low-Medium (requires output-diff testing per step) | `# CPU / Python / synchronization overhead` |
| 3 | Reduce per-step callback/preview/progress forwarding cost (fp32 denoised conversion `rk_sampler_beta.py:2239`, tqdm→websocket chain `comfyapp.py:17880-17895, 17842-17873`) | Medium | High (code-visible per-step work) | Low (progress cadence is user-visible; keep semantics under production `progress_min_interval_ms`) | `# CPU / Python / synchronization overhead` |
| 4 | Confine future attention tuning to the Sage kernel scope (QKV/norm/rope/out/MLP are outside) and validate `auto` mode choice against block-category attention-vs-MLP split | Medium | Medium | Low | `# SageAttention behavior`, `# UNET forward decomposition` |
| 5 | Precompute/reuse per-step coefficients and guide masks that are invariant across evals of the same step (e.g., `RK.set_coeff` allocations `rk_method_beta.py:299-304`) | Low-Medium | Low (needs measured step-residual first) | Low | `# Per-step decomposition` |

No candidate is actionable before the instrumentation pass produces the per-step, per-eval, and block-category numbers; ranking reflects structural expectations only.

---

# Recommended next action

**Implement exactly one gated diagnostic instrumentation pass** — the Level A + Level B design in `# Proposed instrumentation` — gated by `COMFYMODAL_SAMPLING_DEEP_PROFILE` (`off` default), emitting strictly nested host `perf_counter_ns` spans into the existing `RuntimeTrace` and a serialized `_sampling_deep_profile` artifact block, with the optional CUDA-event layer recording terminal events before executor return and realizing all event pairs in the wrapper's post-boundary diagnostic cleanup — a single labeled `torch.cuda.synchronize()` executed **after** the authoritative `sampling_end` emit, outside the reconciliation total, and used only on gated diagnostic runs.

**Implementation ownership (no direct parent/third-party edits).** The pass must be owned entirely inside comfyui-modal and use only reversible, gated observation mechanisms — no source edits to `comfy/`, `RES4LYF/`, `ComfyUI-CacheDiT/`, or `KJNodes/`:
- Install the pass from the existing comfyui-modal boundary hooks: the `SAMPLER_SAMPLE` timing wrapper already registered on the patcher (`runtime_executor.py:3437-3476`) and/or a gated key on the same wrapper type; the per-step callback is observed via a callback wrapper identical in shape to `_step_callback` (`runtime_executor.py:3321-3340`).
- Per-eval and per-block spans use `nn.Module` forward pre/post hooks registered from comfyui-modal on the diffusion model (`NextDiT`), its `layers` (`JointTransformerBlock`), and `JointAttention` — the same hook mechanism comfyui-modal already uses (`register_unet_forward_probe` / `install_nextdit_forward_pre_hook`, `unet_forward_probe.py:184-244, 633-664`). Hook handles are stored at install and **removed in the same `finally`** at `sampling_teardown_end`.
- The RK-loop boundaries (step/eval spans around `rk_sampler_beta.py` line 1665 and 2112) are attached only if an instrumentation seam is unavoidable; prefer driving them from the hook-installed callback/count observation so no RES4LYF source change is required. If a seam is required, it must be a gated hook registered and unregistered around the invocation, never an unconditional edit.
- Net effect with the flag off: zero behavior change (bit-identical sampling); with the flag on: only added observation.

Scope constraints for this pass: measurement only. No changes to sampler behavior, RK coefficients, CacheDiT settings, SageAttention modes, dtypes, steps, or the loader; no deployment or paid Modal generation; no modification of `comfyapp.py` production paths beyond the gated hook registration; the pass must produce the ~5.0 s reconciliation (sampling total vs setup + Σ steps + teardown + residuals) and the CacheDiT compute/skip counters (expected 17 calls, 10 computes / 7 skips) as its acceptance criteria.

---

Report file: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal\SAMPLING_DEEP_DECOMPOSITION.md`
