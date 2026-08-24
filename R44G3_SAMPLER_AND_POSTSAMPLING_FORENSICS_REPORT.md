# R44G3 — Sampler Startup & Post-Sampling Transition Critical-Path Forensics

Batch: R44G3 · Lane: READ-ONLY forensics · Worktree `../comfyui-modal-r42` · Branch `r42-golden-reconciliation` · HEAD `0c59f46`
Target artifact: request `v2-benchmark-0-d5df02fd8dba` · run dir `v2_2026-08-24_02-49-32` · gate `.v2ctl/gates/gate_20260824-025048_2da1a436.json`
Runtime code changed: **NO** · Remote/paid runs performed: **NO**

---

## 0. Executive answer

| Interval | Value | What it actually is |
|---|---:|---|
| `sampler_node_to_sampling` | 1461.501 ms | **Sampler-node entry → FIRST progress callback.** It is *not* "setup before sampling": it contains all RES4LYF/CacheDiT/sigma/noise prep **plus the first denoise evaluation(s)** including one-time cold-GPU initialization. The waterfall stage name is misleading; its end boundary resolved to `t6_sampler_start` (= first progress), because the authoritative wrapper `sampling_start` event was **not persisted** in this run (`pre_sampler_stages.sampling_start_monotonic_ns = null`, `sampler_stage_status = "unavailable"`). |
| `post_sampling_transition` | 649.850 ms | **RES4LYF post-loop teardown *inside* the sampler node** (after last progress callback → node function return ≈ 649.777 ms by exact arithmetic), plus ~0.07–0.33 ms of executor dispatch to VAEDecode. It is **not** model management, **not** VAE prep, **not** single-use teardown, **not** an explicit CUDA sync. |

Both intervals are **within their historical distributions** (§5). Neither is a new regression; both are structural costs that were previously hidden inside differently-named boundaries.

---

## 1. Exact R44E timeline (reconstructed, monotonic-consistent)

Clock anchor (raw log §K): `wall_unix_ns − monotonic_ns = 1787539597004418566`. Container-local console time = UTC−05:00; epoch …823.286 ⇔ console `21:50:23.286`. ✔ matches operator console notes.

| Epoch (s) | mono (s) | Event / boundary | Source |
|---|---|---|---|
| 822.479 | 225.475 | `unet_gpu_transfer_start` (UNET H2D 741.786 ms) | trace event |
| 823.2208 | 226.216 | `unet_gpu_transfer_end` / `unet_ready`; `unet_fastsafe_pipeline` ok | trace event |
| 823.2214 | — | `t4b_unet_load_end` | trace stages |
| 823.2214→823.2238 | — | node 1484 `ModelSamplingAuraFlow` 2.276 ms | per-node timings |
| 823.2238→823.2241 | — | node 137 `CacheDiT_Model_Optimizer` **0.272 ms** (registers only; real patching is lazy) | per-node timings |
| 823.2241→823.2848 | — | node 1499 `PathchSageAttentionKJ` 0.217 ms; misc combo nodes | per-node timings |
| 823.2848→823.2867 | — | node 1262 `LGNoiseInjectionLatent` (FeatureInjLatent) **1.443 ms** | per-node timings |
| **823.286334** | 226.281915 | **`first_sampler_node_monotonic_ns` — ClownsharKSampler_Beta (1242) NODE ENTRY** | pre_sampler_stages |
| 823.286588 | — | `sampler_lane_wait_start` (console 21:50:23.286) | trace event |
| 823.286652 | — | `sampler_lane_wait_end` — wait **0.26 ms**, `blocking_owner=""` | trace event |
| ~823.335 | — | console: `CacheDiT Transformer class: NextDiT` (lazy patch application inside sampler path) | operator console (not archived) |
| ~823.385 | — | console: `load_models_gpu role=other 48.366 ms` returns (allocated Δ +4096 B, reserved Δ **−205,520,896 B**) | CPU-owner record (durably persisted) |
| ~823.427 | — | console: `RES4LYF rk_type: res_2s` | operator console (not archived) |
| 823.427…824.748 | — | **UNMEASURED ~1321 ms**: sigma prep (bong_tangent), noise gen, latent cast (`x.clone().to(default_dtype)`), conditioning transforms, wrapper identity/residency checks, watchdog arm, VAE early-schedule, **first denoise eval(s) + cold GPU init** | — |
| **824.748089** | 227.743659 | **`t6_sampler_start` = FIRST progress callback** (`first_sampler_stage_event="progress"`, `first_sampler_stage_monotonic_ns=227743658870`) | trace stages / pre_sampler_stages |
| 828.475485 | — | `t6_sampler_end` = LAST progress callback → `sampling = 3727.396 ms` (8-step cohort) | trace stages |
| **829.125336** | — | `vae_decode_start` (node 175 VAEDecode executing-event observed) → **`post_sampling_transition = 649.850 ms`** | trace event |
| 829.125008* | — | *sampler node 1242 function RETURN (derived: entry 823.286334 + node duration 5838.674 ms) | per-node timings (derived) |
| 829.125→829.620 | — | `t7` VAE decode 494.346 ms — contains `load_models_gpu role=other 61.369 ms` (allocated Δ +173,819,392 B = VAE to GPU; reserved Δ **−1,990,197,248 B** = allocator/free_memory trim) | CPU-owner record |
| 829.620→829.934 | — | output encode/persist (363.472 ms stage) | trace events |

Node 1242 total duration **5838.674 ms** = 1461.501 (entry→first progress) + 3727.396 (progress window) + **649.777 (post-last-progress tail)**. The last two figures reconcile with the waterfall to <0.3 ms.

### What boundary does `t6_sampler_start` represent? (exact)

- Written by `_commit_stage_windows_to_trace` (`comfyapp.py:14953-14955`) from `windows["sampler"]`.
- `_begin_profiled_node` deliberately **excludes** the sampler stage (`comfyapp.py:14899`, `stage != "sampler"`), so t6 is **not** node-entry.
- On node finish, `_finish_profiled_node` sets `windows["sampler"]["start"] = first_progress`, `end = last_progress`, `source="progress"` (`comfyapp.py:15054-15064`). Empirically confirmed: `t6_sampler_start == first_sampler_stage_monotonic_ns` (progress), and the waterfall's `sampling` stage = `event("sampling_start")→event("sampling_end")` resolved to the same instants (`v2_waterfall.py:1093-1099`).
- The **authoritative wrapper** `sampling_start` event (`runtime_executor.py:4748-4755`, emitted after identity/residency checks, watchdog arm, lane acquire, VAE scheduling, *before* deep-profile begin and the underlying sampler call) did **not** reach the durable trace this run. Therefore `sampler_node_to_sampling` (`v2_waterfall.py:1075-1080`) fell back to `[sampler_lane_wait_start → t6_sampler_start]`.
- Consequence: **t6 is a first-progress boundary LATER than the actual start of sampling work.** Everything between node entry and the first callback — including the first UNET forward and one-time GPU initialization — is booked into `sampler_node_to_sampling`, and the true "sampling" window excludes the first step(s).

---

## 2. Source map: node entry → first sampling iteration

Path (all verified in source):

1. ComfyUI `executing` event for node 1242 → `modal_app.py:14602-14673`: exclusive-UNET ownership join (no-op here), mutation-lane request/acquire (console lines; wait 0.26 ms).
2. `ClownsharKSampler_Beta.main` (`RES4LYF/beta/samplers.py:1746`, FUNCTION=`main`):
   - `OptionsManager(options, **kwargs)` + `extra_options` merge (`samplers.py:1844-1845`) — CPU. Console `rk_type: res_2s` originates here.
   - chained `latent_image` model/conditioning resolution (1866-1874); guider/patcher acquisition (1876-1879) — CPU.
   - option overrides parse: noise/eta/overshoot/scheduler/sampler (1887-1978) — CPU.
   - `SharkSampler().main(...)` call (2079-2101).
3. `SharkSampler.main` (`samplers.py:153`):
   - `default_dtype = EO("default_dtype", torch.float64)` (211) — **latent buffers are upcast toward FP64 unless overridden**; `x = latent.clone().to(default_dtype)` (810) — allocation + possible GPU cast kernel.
   - sigma construction (scheduler `bong_tangent`), noise generation (`torch.manual_seed`/`randn`), `torch.cuda.manual_seed` (804-805) — GPU allocation/kernels.
   - comfy `load_models_gpu([diffusion model])` — the measured `role=other 48.366 ms` (allocated +4096 B ⇒ UNET already resident via FastSafe adoption; reserved −205 MB ⇒ allocator trim). Classification: model-management + allocator trim, no transfer.
   - CacheDiT lazy patching — console `CacheDiT Transformer class: NextDiT` (the 0.27 ms CacheDiT node only registered; wrapper application is deferred to first use). Classification: Python module surgery + first-forward hooks.
   - `guider.sample(noise, x.clone(), sampler, sigmas, ..., callback=...)` (659) → comfy `sample_custom`/RK loop (`rk_sampler_beta.py`): per step `preview_callback(...)` (1986/2124) and step callback with `denoised_callback.to(torch.float32)` (2239) — GPU kernels; **first invocation carries CUDA module loads / attention-backend (Sage/RES4LYF path) / cuDNN/cuBLAS lazy init**.
   - First callback fires → runtime wrapper emits `first_sampler_step` (`runtime_executor.py:4923-4929`) and comfyapp records first progress → **this instant is `t6_sampler_start`**.
4. Wrapper (`runtime_executor.py:4406-4997`), executed *inside* the above: identity/metadata (4440-4528), retained-UNET identity check (4600-4621), GPU-residency verification (4623-4663), watchdog arm anchored at sampling start (4665-4692), lane acquire (4719-4724), VAE early-scheduling, `sampling_start` emit (4748-4755), deep-profile begin (4813-4829), callback wrapping (4872-4997). No `torch.cuda.synchronize`, no `empty_cache`, no `gc.collect` before the sampler call.

Classification summary for the 1461.501 ms window: Python orchestration (majority of prep), one measured model-management call (48.366 ms), allocations + first-step GPU kernels (unmeasured share), **zero explicit synchronization**, zero cache clears.

## 3. Closure attempt — SAMPLER STARTUP = 1461.501 ms

| Component | Value | Status |
|---|---:|---|
| Lane wait + acquire | 0.26 / 0.284 ms | DIRECTLY MEASURED (`sampler_lane_wait_ms`, `sampler_node_to_lane_acquired_ms`) |
| Pre-sampler graph nodes (ModelSampling 2.276, CacheDiT reg 0.272, Sage patch 0.217, FeatureInjLatent 1.443) | ≈ 4.2 ms | DIRECTLY MEASURED (per-node timings; precede node entry, listed for completeness) |
| Node entry → `rk_type` log segment (option parse + CacheDiT NextDiT print + `load_models_gpu`) | ≈ 141 ms | CONSOLE-BOUNDED (operator console; not archived) |
| ─ of which `load_models_gpu role=other` | **48.366 ms** | DIRECTLY MEASURED (CPU-owner record) |
| RES4LYF prep after `rk_type` (sigmas, noise, latent cast, conds) | unknown | UNMEASURED |
| Wrapper checks + watchdog + VAE scheduling | unknown (historically small) | UNMEASURED |
| First denoise evaluation(s) + cold GPU init (attention backend, CacheDiT first-use, cuDNN/cuBLAS module load) | unknown | UNMEASURED |
| **Directly attributed total** | **≈ 145 ms (~10 %)** | |
| Residual (prep + first-step, indivisible this run) | ≈ 1316 ms | UNMEASURED |

Historical derivation (DERIVED, not measured here): E24 measured `sampling_start → first_sampler_step = 1067.597 ms` on a healthy run; E23 measured node→`sampling_start` = 112–124 ms. Their sum (~1180–1192 ms) matches the structure of this interval; R44E's +270–280 ms excess is consistent with a **cold-container first request** (fresh CUDA context/module loads). This supports: **most of the residual is first-step work, not removable "setup" overhead.**

Missing boundaries to close fully: (a) persisted wrapper `sampling_start` event; (b) per-step callback timestamps; (c) archived console lines.

## 4. First-step cost vs startup — DISTINGUISHED

The 1461.501 ms interval **includes** first-step initialization by construction: `t6_sampler_start` *is* the first progress callback, so compile/JIT-class costs (CUDA module load, Sage/RES4LYF attention-path init, CacheDiT first-use wrapping, cuDNN/cuBLAS lazy init, first big allocations) and the first denoiser evaluation all occur **before** it. They are inside this stage, not after it.

Per-step timing for *this* run: **not available** (no per-step events persisted; `full_trace.metadata.gpu_observation_clas.sampler_setup_observed=True` only). Historical anchor: E24 `sampling_start→first_sampler_step = 1067.597 ms` vs later-step cadence implied by `3727.396 ms / 8 steps ≈ 466 ms` average — i.e., the first step historically costs ≈ 2–3× a subsequent step. The operator console observation ("first visible iteration substantially slower") is consistent with this.

## 5. Historical comparison

| Cohort / report | Metric | Value | Assessment |
|---|---|---:|---|
| E23 (`V2_BATCH_E23_CRITICAL_PATH_FORENSICS.md:104-127`) | node → actual sampling start | **124.170 / 112.532 ms** | same definition family, wrapper event working |
| E24 (`V2_BATCH_E24_CRITICAL_PATH_CLOSURE.md:37-41,169-173`) | sampling_start → first step | **1067.597 ms** | wrapper-internal pre-first-step window |
| E23+E24 sum | node → first progress (equiv.) | ≈ **1180–1192 ms** | R44E structure match |
| C8 archive (`C8_BENCHMARK_COMPLETE_RUN_LOG.md`, 60+ runs) | `sampler_node_to_sampling` | clusters **~850–980 ms** and **~1500–1800 ms** cold; **26–51 ms** warm re-exec; outliers to 22 s | **1461.501 ms is inside the historical cold distribution** |
| E24 | post_sampling_transition | **838.839 ms** | |
| D14 (`V2_BATCH_D14_POST_SAMPLING_FORENSICS.md:19-104`) | VAE transition decomposition | settle+gate ≈ 885–1034 ms era; exposed VAE join 28.4/31.1/66.1 ms | older architecture |
| C8 archive | `post_sampling_transition` | **~334–930 ms** across dozens of runs | **649.850 ms is mid-range — normal** |
| R43 healthy cohort (25–29 s walls) | sampling / VAE | 3683–3738 / 388–463 ms | R44E sampling 3727.396 identical; VAE 494.346 slightly high but in-family |

Verdict: **neither interval is a recent regression.** The 1461.501 ms figure is largely a *boundary-definition artifact* (stage now ends at first progress) **plus** genuinely persistent first-step initialization that has always existed (~1.07 s warm). Do not "optimize" it as if it were newly introduced overhead.

Note: `COMFYUI_MODAL_V2_PERFORMANCE_HISTORY_AND_RECOVERY_HANDOFF_2026-08-23.md` was **not found** in either custom-node directory at analysis time (possibly owned by a concurrent R44 lane); comparison above uses the primary artifacts directly.

## 6. Post-sampling transition timeline (exact)

```
828.475485  last progress callback          (= t6_sampler_end, "sampling_end")
   │  ~649.78 ms INSIDE node 1242 (RES4LYF SharkSampler.main post-loop):
   │    - final RK bookkeeping; denoised float32 casts (rk_sampler_beta.py:2239)
   │    - batch/output packaging: out_samples stack, squeeze (samplers.py:1142-1185)
   │    - copy.deepcopy(state_info_out) (samplers.py:1187)  ← suspect
   │    - x0_output["x0"].cpu() GPU→CPU copies (samplers.py:755/1138) ← implicit-sync suspects
   │    - gc.collect() (samplers.py:1165)                   ← prime suspect
   │    - return through SharkSampler.main → ClownsharKSampler_Beta.main (2103)
   │    - comfy pbar finalize; node output wrap
829.125008  node 1242 function return        (derived: 823.286334 + 5838.674 ms)
   │  ~0.33 ms ComfyUI executor: UI wrap, cache update, finish_progress,
   │    mark-executed, next-node "executing" send (execution.py:535-647)
829.125336  vae_decode_start observed (node 175)  → transition ends
```

The later `load_models_gpu role=other 61.369 ms` sits **inside** the VAE-decode stage (t7), invoked by native `VAE.decode → model_management.load_models_gpu([self.patcher])` (`comfy/sd.py:1054-1056`): allocated Δ +173.8 MB = VAE decoder placed on GPU; reserved Δ −1.99 GB = `free_memory`/allocator release of unused reserved segments. It is **VAE preparation, not post-sampling cleanup**, and it is not part of the 649.850 ms.

## 7. Closure — POST-SAMPLING TRANSITION = 649.850 ms

| Component | Value | Status |
|---|---:|---|
| Sampler post-last-callback teardown inside node 1242 | **649.777 ms** | DERIVED **exactly** (node duration 5838.674 − 1461.501 − 3727.396) |
| Executor bookkeeping + dispatch to VAEDecode event | ≈ 0.07–0.33 ms | DERIVED (stage-timestamp delta) |
| Model management / unload / offload in transition | 0 ms | DIRECTLY MEASURED ABSENT (no CPU-owner record between sampling_end and vae_decode_start) |
| `torch.cuda.empty_cache` / explicit sync in transition | none found | SOURCE-VERIFIED ABSENT (runtime_executor inserts none; `sampling_deep_profile` sync is post-boundary diagnostic only) |
| Internal split of the 649.777 ms tail (gc vs deepcopy vs .cpu() vs packaging) | unknown | UNMEASURED |

Interval-level closure: **100 %** (every millisecond is attributed to the sampler node's own tail). Composition-level closure: **open** — three concrete source-verified suspects named above; ranking among them requires the telemetry in §10.

## 8. Is GPU-memory policy causing it?

**No.** With ~97 GB VRAM and single-use residency: no UNET unload, no model move, and no cache clear occurs between sampling end and VAE decode (CPU-owner records show zero `load_models_gpu` in the transition; runtime code inserts none). The only memory actions adjacent to the transition are (a) the pre-sampling 48.366 ms call's −205 MB reserved trim and (b) the VAE call's −1.99 GB reserved trim inside t7 — both are cheap allocator hygiene inside measured calls, together ≪ the transition itself. The 649.85 ms is CPU-side Python/tensor work inside RES4LYF, not VRAM policy.

## 9. Single-use / end-of-request interaction

**None reaches the critical path.** Production cleanup is explicitly deferred to the stream-generator finalizer after terminal handoff (`modal_app.py:15929-15933`, `15948-15954`: "do NOT run them before the terminal handoff"). AIMDO hooks in the executor are gated on `comfy.memory_management.aimdo_enabled`; `cleanup_models_gc()`/`soft_empty_cache` fire only inside native `load_models_gpu` under dead-model/memory-pressure conditions (`comfy/model_management.py:855-856, 979-990`). Traced source shows no end-of-request cleanup executing between sampling and VAE decode.

## 10. RECOMMENDED DURABLE EVENTS (for R44G1 reconciliation)

| # | Proposed event | Exact boundary (function) | Start / End | Fields | GPU sync needed? |
|---|---|---|---|---|---|
| 1 | `sampler_wrapper_sampling_start` | persist the EXISTING `trace.emit("sampling_start", …)` (`runtime_executor.py:4748`) durably; backfill `pre_sampler_stages.sampling_start_monotonic_ns` (currently `null`) | emit point → n/a | mono_ns, node_id, steps | No |
| 2 | `sampler_prep_phase` | entry of `SharkSampler.main` → immediately before `guider.sample(...)` (`samplers.py:659`) | function entry / pre-sample line | mono_ns pair, dtype(default_dtype), sigmas_len | No |
| 3 | `sampler_first_eval_start` | first invocation of wrapped step executor / first `preview_callback`-preceding forward (`runtime_executor.py:4872-4997` wrapper) | before first model call | mono_ns | No |
| 4 | `sampler_step_tick` | every KSampler callback (`rk_sampler_beta.py:2239` path) | per callback | `i`, mono_ns (array or per-step deltas) | No |
| 5 | `sampler_tail` | last callback → node function return (bracket `SharkSampler.main` post-loop: stack/deepcopy/`gc.collect()`/return) | last callback / return at 2103 | mono_ns pair, `gc_counts_before/after`, `cpu_transferred_bytes` | Only if `.cpu()` occurs (report bytes; do not force sync) |
| 6 | `vae_load_models_gpu_ts` | add mono start/end to the existing CPU-owner `load_models_gpu` record (`role=other`) | call entry/exit | wall_ms (exists), mono_ns pair, caller=`vae_decode` | No |
| 7 | `console_ring_persist` | fix `console_capture: null` in gate manifest: ship container stdout ring for [T5→t8] window to run dir | request scope | captured line count, byte size | No |

All proposals are timestamp-only (host clocks already correlated via §K anchor); none requires forced synchronization. Items 1–5 alone would have closed §3 to ≥95 % and ranked the §7 suspects in one run.

## 11. Ranked optimization opportunities (proven/strongly-supported only)

| Rank | Target | Evidence | Max recoverable wall (evidence-bounded) |
|---|---|---|---|
| 1 | **Pre-first-step initialization** (CUDA module/attention-backend init + first eval) occurring once per cold container inside the startup interval | E24 1067.597 ms recurring; R44E residual ≈1316 ms unmeasured but structurally matching | **~0.8–1.2 s** if a restore-time/idle priming forward hides it; requires items 2–4 telemetry to prove split before implementation |
| 2 | **RES4LYF sampler tail** (`gc.collect()` `samplers.py:1165`; `copy.deepcopy(state_info_out)` :1187; `.cpu()` transfers :755/:1138) | Tail proven = 649.777 ms inside node; suspects source-verified; dominance unranked | **≤ ~0.5 s** (if gc dominates; measure first — gc on restored large heap is plausible but unproven) |
| 3 | Pre-sampling `load_models_gpu role=other` trim | 48.366 ms measured, allocated Δ ≈ 0 (pure bookkeeping/trim while model resident) | ≤ ~40 ms |
| 4 | VAE-transition `load_models_gpu` reserved-memory trim | 61.369 ms measured incl. VAE H2D; trim portion unquantified | ≤ ~30 ms |
| 5 | Executor dispatch between nodes | 0.07–0.33 ms derived | negligible — do not pursue |

Not ranked (insufficient evidence): CacheDiT lazy-patch cost (console print only), FP64 default-dtype latent casting (source-visible, unmeasured).

## 12. Next implementation recommendation

**Gate on telemetry first (one cheap remote run with §10 items 1–5 enabled, no behavior change):**
1. If `sampler_first_eval_start − sampler_wrapper_sampling_start` ≫ `first_step_tick − sampler_first_eval_start`, implement restore-time/idle **single priming forward** (target Rank 1, ~1 s).
2. Else implement **tail reduction**: replace unconditional `gc.collect()` with guarded/collect(0)-style policy or move it behind an env flag; skip `state_info` deepcopy when downstream consumers absent; keep latents on device until VAEDecode (target Rank 2, ~0.3–0.5 s).

Either way, land §10 events durably in the same change so R44 reconciliation gets closure for free.

---

## Evidence table (direct / derived / missing)

| Claim | Type | Artifact |
|---|---|---|
| Waterfall stage values (1461.501 / 3727.396 / 649.850 / 494.346) | DIRECT | `run_0.json` waterfall stages (start_ns/end_ns, src=event) |
| Stage boundary semantics (lane_wait_start → first progress) | DIRECT | `v2_waterfall.py:1075-1080` + `pre_sampler_stages` metadata + `comfyapp.py:14896-14902, 15050-15068` |
| Node 1242 duration 5838.674 ms; per-node table | DIRECT | `run_0.json` `pre_sampler_structured_report.per_node_timings` |
| Tail = 649.777 ms inside node | DERIVED (exact arithmetic) | §6 |
| `load_models_gpu` 48.366 / 61.369 ms + CUDA deltas | DIRECT | raw log §H (run_0.json CPU-owner records) |
| Wrapper `sampling_start` event missing this run | DIRECT | `pre_sampler_stages.sampling_start_monotonic_ns=null`, `sampler_stage_status="unavailable"` |
| Console lines 21:50:23.x–24.x | OPERATOR-PROVIDED, NOT ARCHIVED | gate `"console_capture": null` (telemetry gap) |
| First-step ≈ 1067.597 ms historical | DIRECT (prior batch) | E24 report |
| node→sampling-start 112–124 ms historical | DIRECT (prior batch) | E23 report |
| Historical distributions (both intervals) | DIRECT (archive) | C8 archive waterfalls; D14; R43 cohort |
| Internal split of 1316 ms residual; internal split of 649.777 ms tail | MISSING | requires §10 telemetry |
| Handoff doc 2026-08-23 | MISSING FILE | not found in either repo dir |

## Final flags

```
R44G3_SAMPLER_STARTUP_1462MS_EXPLAINED = YES
R44G3_SAMPLER_STARTUP_CLOSURE_PCT = 10
R44G3_FIRST_STEP_DISTINGUISHED = YES
R44G3_POSTSAMPLING_650MS_EXPLAINED = YES
R44G3_POSTSAMPLING_CLOSURE_PCT = 100
R44G3_MODEL_MANAGEMENT_ROLE_PROVEN = YES
R44G3_CUDA_SYNC_ROLE_PROVEN = NO
R44G3_HISTORICAL_COMPARISON_COMPLETE = YES
R44G3_TELEMETRY_GAPS_SPECIFIED = YES
R44G3_NEXT_TARGET_IDENTIFIED = YES
R44G3_RUNTIME_CODE_CHANGED = NO
R44G3_REMOTE_RUN_PERFORMED = NO
```

Closure notes: sampler-startup 10 % = *directly measured* attribution (≈145 ms of 1461.501 ms); the remaining ≈1316 ms is structurally explained (prep + first-step, historically ~1180 ms equivalent) but not component-measured — closing it requires §10 items 1–5. Post-sampling closure is 100 % at interval level (tail located inside node 1242 by exact arithmetic); its internal composition remains open and is the top telemetry ask.
