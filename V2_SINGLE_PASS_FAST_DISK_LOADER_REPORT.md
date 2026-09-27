# V2 Single-Pass Native Fast-Disk UNET Loader — Implementation and Verification Report

**Date:** 2026-08-11
**Basis:** `V2_CPU_STAGES_DEEP_DECOMPOSITION_REPORT.md`
**Environment:** RTX PRO 6000, 12 CPU, 32768 MiB, provider/region UNPINNED (GCP us-east1 / us-east4 observed), production cold/single-use semantics (`release_gpu_after_request=1`). Two measurement contexts: (1) the n=3 loader benchmark ran under the **diagnostic** profile with `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0` (production profile requires `CPU_MODEL_SNAPSHOT=1`, and the snapshot-bypass path is the pure disk-load case); (2) the **integrated production acceptance** ran under `COMFYMODAL_V2_ENV_PROFILE=inherit` with `CPU_MODEL_SNAPSHOT=1` + UNET-absent clip_vae eviction (the intended production configuration; inherit is mandatory because the production profile raises on UNET-absent and the deploy bat's production branch wipes the eviction vars). Extra diagnostic instrumentation is active in all numbers.

---

# Executive conclusion

- **Was the ~1.4s stage the redundant empty `model.to(cuda)`?** **Yes, confirmed as the dominant cause, with one qualification.** The optimized path removes the empty-parameter placement pass entirely; measured empirical saving is **~1.20s median (~26%)** on the UNETLoader node wall (3.35s vs 4.55s legacy same-shape). The ~1.4s figure remains the **analytic estimate** of the removed zero-page H2D + allocation pass (the fast path never performs one, so it cannot be measured directly); the measured delta is *consistent with* that estimate, not a direct measurement of it.
- **Literal ModelPatcher construction cost:** **negligible — 0.136 / 0.143 / 0.446 ms** across the three runs (was previously contaminated by two post-constructor helpers; timing now closes immediately after native `__init__`). The old "~1.4s ModelPatcher creation" was never the constructor.
- **Was the single-pass path (`assign=True` → one real `model.to(cuda)`) correct?** **Yes.** All guards held (plain `comfy.model_patcher.ModelPatcher`, HIGH_VRAM, `load==offload==target=cuda:0`, uniform BF16 checkpoint dtype == constructed dtype, exact plain `torch.Tensor` values, no quant/custom-ops/fp8/channels-last). Bind with `assign=True` was ~17–47 ms (pure rebinding), followed by exactly one synchronized real transfer.
- **Measured loader before/after** (UNETLoader node wall, same workflow/shape/profile class):
  - Before (legacy, no fast path, run 21-04-13): **4550.28 ms**
  - After (fast path, medians of 3): **3353.93 ms** (range 3158.17–3607.62)
- **Measured savings:** **~1196 ms median (~26%)**, range ~0.94–1.39s (21–31%). Single legacy reference sample, no loader instrumentation in that run (delta is conservative: fast-path node walls *include* instrumentation overhead).
- **Integrated production acceptance (UNET-absent snapshot): PASS.** Under the intended production configuration (CPU_MODEL_SNAPSHOT=1 with UNET evicted pre-capture via the clip_vae retain role, CLIP+VAE retained), the graph-time UNETLoader **does** engage the native fast-disk path: `unet_fast_disk_defer`+`complete` fired (453 BF16 params → CUDA, 0 CPU params), post-restore `unet_present=0` with `clip_present=1`/`vae_present=1`, CacheDiT and SageAttention nodes executed, and output was **bit-exact** (`202f0f75…`). Sampling `[v2.sampler_boundary] duration_ms=4773.012`. Details in the "Integrated production acceptance" section below.

---

# Implementation

## Changed files

| File | Change |
|---|---|
| `comfymodal_runtime/model_preload.py` | Fast-disk section: flag read, per-model deferral registry, guard suite, bind/replay, event emitter, CUDA-event synchronized timing; corrected literal-constructor timing ownership (helpers moved outside the span); `nn.Module.to` deferral hook; `get_model` window-open; `load_model_weights` bind/replay; graph-time wrapper `_install_graph_unet_loader_wrapper` + lazy helper + belt-and-braces call in `_ensure_core_wrappers` |
| `comfymodal_runtime/runtime_bootstrap.py` | Additive (+22 lines): flag-gated lazy install of the graph wrapper at top of `restore()`; inert when flag off |
| `comfyapp.py` | `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` deploy-baked into `_V2_RUNTIME_ENV` from caller env, default `0` |
| `deploy_and_run_v2_single.bat`, `run_v2_single.bat` | Env pin (default off) + profile summary echo |
| `tools/benchmark_v2_direct.py` | Snapshots-off runtime-shape validation accepts `stored_snapshot_model_order=None` only when `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`; exact validation unchanged otherwise |
| `tests/test_native_fast_disk_unet_loader.py` (45), `tests/test_v2_graph_unet_loader_wrapper.py` (17), `tests/test_native_fast_disk_benchmark_harness.py` (17) | Focused suites; 79 combined tests + related suites green |

## Fast-path behavior (exact order)

1. Normal native model construction (`model_config.get_model`).
2. Normal plain `ModelPatcher` construction.
3. The first eligible native `model.to(cuda)` call between patcher construction and `load_model_weights` is **deferred** (recorded, not executed).
4. `load_model_weights(..., assign=True)` — binds the checkpoint tensors (no copy, no dtype/device conversion).
5. Exactly **one** real original `model.to(cuda)` — single fused alloc + page-in + H2D.
6. Normal ComfyUI path continues (patching, CacheDiT, SageAttention, sampling untouched).

## Guards (all must hold; else legacy path)

- Explicit flag `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` on (default off).
- Original call would use `assign=False` (plain patcher); exact plain `comfy.model_patcher.ModelPatcher`, `is_dynamic()==False`.
- `load_device == offload_device == deferred target`, CUDA/non-CPU, `HIGH_VRAM`.
- State-dict values are exact plain `torch.Tensor`, CPU-backed, uniform dtype equal to the constructed diffusion-model parameter dtype.
- No `quant_config`, no `custom_operations`, no fp8 optimization, no `force_channels_last`, torch swap-module-params future disabled.
- A live request trace exists (else direct legacy call, no lane binding).

## Fallback behavior

Any failed guard replays the deferred real `model.to(target)` **before** invoking the original `load_model_weights` with its **original** `assign` value — legacy ordering and exceptions preserved. Flag off = byte-identical legacy (no wrapper, no state-dict scan). ModelPatcher fields/bookkeeping never mutated; deferral records are weakref-keyed, bounded, identity-verified, and dropped on every path.

## Deployment history (no extra generations)

1. Production profile + snapshot-bypass: rejected at startup by design (`production requires CPU_MODEL_SNAPSHOT=1`) — 0 generations.
2. Diagnostic deploy: image build pycache race — 0 generations.
3. Diagnostic deploy (success): gate run failed fast-path engagement (wrappers not installed when snapshots off) → diagnosed, remediated with graph-time wrapper, re-gated. The failed-gate run (21-04-13) is used as the legacy same-shape reference.

---

# Timing attribution

Corrected ownership (fast path, all wall unless noted; three runs):

| Stage | Run A | Run B | Run C | Notes |
|---|---|---|---|---|
| Model construction (`get_model` span) | 39.971 ms | 37.444 ms | 47.275 ms | Python wall |
| Literal `ModelPatcher.__init__` | **0.136 ms** | **0.143 ms** | **0.446 ms** | Helpers excluded; previously contaminated |
| Assign/bind (`assign=True`) | 17.466 ms | 19.151 ms | 46.545 ms | Rebind only, no copy |
| Real `model.to(cuda)` — Python wall | 2320.929 ms | 2150.082 ms | 2396.620 ms | Enqueue + drain (sync inside span) |
| Real `model.to(cuda)` — synchronized device | **2320.896 ms** | **2150.026 ms** | **2396.542 ms** | CUDA events; wall ≈ device ⇒ no CPU-side stall; page-in already done in read span |
| Loader residual (SD span minus children) | 3.489 ms | 3.478 ms | 21.344 ms | Python |
| `load_torch_file` (mmap open + page-in) | 962.92 ms | 938.66 ms | 1086.23 ms | Not part of construction span |
| First CUDA op after demand | 101.851 ms | 120.108 ms | 110.234 ms | cuda:0, bf16 |
| Loader-return → first forward | 222.687 ms | 218.313 ms | 201.741 ms | Derived from existing events |

Attribution corrections: the deferred `model.to` emits **no** `unet_model_to_*` span (was previously mis-labeled as ModelPatcher construction); `load_model_weights` span (bind+replay) now correctly owns the bind and the synchronized drain. The post-transfer `cuda.synchronize()` moves the H2D drain into loader ownership — attribution movement, not latency change.

---

# Correctness proof

| Proof item | Result |
|---|---|
| Native fast-disk proof (`[v2.native_fast_disk_unet]` + `unet_fast_disk_complete` event) | decision=complete, reason=ok, native_assign=false, bind_assign=true, HIGH_VRAM, patcher `comfy.model_patcher.ModelPatcher` non-dynamic — all 3 runs |
| Parameter count | **453** (all 3 runs) |
| Parameter bytes | **12,309,817,472** (all 3 runs) |
| dtype | **{torch.bfloat16: 453}** (all 3 runs) |
| Device after placement | **{cuda: 453}**; cpu_params=**0**, cpu_buffers=**0** (all 3 runs; defer-stage proof shows the pre-transfer CPU state 453/1) |
| ModelPatcher | Plain `ModelPatcher` preserved; no dynamic subclass; patcher fields untouched by loader |
| CacheDiT | `CacheDiT_Model_Optimizer` node executed on the same patcher/diffusion model; sampling graph identical |
| SageAttention | `PathchSageAttentionKJ` node executed; sampling ran with same node graph |
| Output parity | **Bit-exact sha256** `202f0f75113c31bdc927bbc1d0148754077c4951081c9fe6d15025c861657579` (2873003 B, 1088×1920) on all 3 runs vs legacy baseline (workflow `14f815f1…`, seed 1006800347249813) — this workflow/model only; no weight-level hashing was performed |
| Scope limitation | LoRA/hooks/clone/backups/unload-reload verified **only at unit-test level on fakes** (45 + 17 tests). Remote verification of patching/hook/unload-reload behavior is outstanding — a follow-up gate item, not evidence in this report. |

---

# Run results

| Run | Cloud | Region | Construct (get_model ms) | ModelPatcher init (ms) | Assign/bind (ms) | Real model.to(cuda) sync (ms) | Loader total (UNETLoader node, ms) | First forward (demand→first cuda op, ms) | Full Sampling `[v2.sampler_boundary] duration_ms` | Command→response (ms) |
|---|---|---|---|---|---|---|---|---|---|---|
| A (21-40-24, gate) | GCP | us-east1 | 39.971 | 0.136 | 17.466 | 2320.896 | 3353.93 | 101.851 | **4882.88** | 66421.4* |
| B (21-44-20) | GCP | us-east4 | 37.444 | 0.143 | 19.151 | 2150.026 | 3158.17 | 120.108 | **4873.716** | 26981.6 |
| C (21-45-13) | GCP | us-east4 | 47.275 | 0.446 | 46.545 | 2396.542 | 3607.62 | 110.234 | **5459.246** | 31540.6 |

\* Run A is the only canonical cold c2r (snapshot callback null); runs B/C restored from an older retained snapshot (callback 201s/254s), so restore-phase metrics (c2r, callback gaps) are **not comparable across runs** — only loader-local metrics are. All runs: restore_count=1, request_count=1, fresh=true; exact output parity on all three.

Sampling uses the authoritative `[v2.sampler_boundary] event=sampling_end duration_ms=...` (Modal logs), matching artifact `sampling_end.duration_ms` and waterfall `sampling`.

---

# Integrated production acceptance (UNET-absent snapshot)

One bounded production-style correctness gate, run 2026-08-11 23:01 UTC, exactly one generation (no additional runs). Artifact: `comfymodal-data\benchmarks\runs\v2_2026-08-11_23-01-37\run_0.json` — request `v2-benchmark-0-78bf21ff254e`, image `im-KpT2PtlB5YDG82RHAifdlh`, GCP us-east4 (unpinned), RTX PRO 6000 / 12 CPU / 32768 MiB.

## Exact configuration used

```
COMFYMODAL_V2_ENV_PROFILE=inherit            # mandatory: production profile raises on UNET-absent
                                             # and the deploy bat's production branch wipes eviction vars
COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1           # full CLIP/UNET/VAE snapshot build (then evict)
COMFYMODAL_V2_VAE_SNAPSHOT=1
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1        # identity/reporting gate (restore agent's config)
COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1 # actual UNET-absence mechanism
COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae
COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0
COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1
COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1    # production single-use (inherit skips the bat default)
COMFYMODAL_V2_GPU=rtx-pro-6000, CPU_REQUEST=12, MEMORY_MB=32768, BASELINE 12/32768
V2_BENCHMARK_RUNS=1, V2_BENCHMARK_MODE unset (default mode)
deploy_and_run_v2_single.bat
```

Restore/eviction architecture was **not modified** (owned by the concurrent restore agent); this run only configures it and adds the fast-disk flag.

## Gate evidence (all PASS)

| Requirement | Evidence |
|---|---|
| Post-restore UNET absent | `snapshot_activation_invariant`: `unet_present=0, clip_present=1, models_container_present=1, status=pass`; logs `[v2.snapshot_model_eviction] stage=restore_observed marker=1 ... unet_present=0 retained_role=clip_vae` and `stage=restore_release_retained ... clip_present=1 vae_present=1 unet_present=0` |
| CLIP/VAE retained | `clip_present=1`, `vae_present=1`, `container_retained=1` (both eviction log stages) |
| Fast-disk defer+complete fired | `defer`: reason=ok, HIGH_VRAM, target cuda:0, `comfy.model_patcher.ModelPatcher` dyn=false; `complete`: decision=complete, param_count=**453**, parameter_bytes=**12309817472**, dtype `{torch.bfloat16:453}`, device `{cuda:453}`, cpu_params=**0**, cpu_buffers=**0**, native_assign=false, bind_assign=true, get_model_ms=35.751, ctor_ms=0.14, bind_ms=17.594, to_wall_ms=2256.574, to_device_ms=2256.501 (synchronized_device) |
| 453 BF16 / CUDA residency | complete-event accounting above; SD breakdown: model_config_get_model 35.751 / model_patcher_constructor 0.14 / load_model_weights 2277.524 / residual 3.415 (total 2318.922) |
| Normal ModelPatcher | plain `comfy.model_patcher.ModelPatcher`, non-dynamic; literal ctor 0.14 ms; patcher fields untouched |
| CacheDiT | `CacheDiT_Model_Optimizer` node executed (0.345 ms) on the same patcher; sampling graph identical |
| SageAttention | `PathchSageAttentionKJ` node executed (0.17 ms) |
| Bit-exact output parity | asset sha256 `202f0f75113c31bdc927bbc1d0148754077c4951081c9fe6d15025c861657579`, 2873003 B, 1088×1920 — exact vs baseline (workflow `14f815f1…`) |
| Authoritative Sampling | `[v2.sampler_boundary] event=sampling_end duration_ms=4773.012`; artifact event-pair 4772.988 ms; waterfall `sampling` 4772.988 (exact match) |
| Loader total | UNETLoader node wall **3334.807 ms**; first CUDA op 84.023 ms after demand |

Run identity: `restore_count=1, request_count=1, fresh=true`, `snapshot_callback_to_command_start_ms=null`, `stored_snapshot_model_order="O0"` (runtime-shape validation passed), `command_to_response_ms=95690.9` (platform-dominated: submit2entry 73.6 s; app-stage `t3b_to_t8` 13.67 s unaffected). No errors.

Observations (not failures): `cpu_snapshot_models_created.unet_object_type="ModelPatcher"` reflects the current eviction architecture (full build → clip_vae eviction pre-capture), and the restore agent's pre-capture eviction log recorded a non-fatal floor check miss (`final_reduction_from_full_mib=-1762.2`) — capture proceeded and all post-restore invariants hold; that mechanism is the restore agent's domain.

---

# Before vs after

Metric: UNETLoader node wall, same workflow (`14f815f1…`), same shape (RTX PRO 6000 / 12 CPU / 32768 MiB, diagnostic profile, snapshot-bypass), same model stack.

| | Before (legacy, 21-04-13) | After (fast path, n=3) |
|---|---|---|
| UNETLoader node wall | 4550.28 ms | median **3353.93** (3158.17–3607.62) |
| Delta | — | **−1196 ms median (−26%)**, range −943…−1392 ms (−21…−31%) |
| Placement passes | empty `model.to(cuda)` + `load_state_dict(assign=False)` copy (two full-model passes) | one bind (`assign=True`) + one real `model.to(cuda)` |
| Sampling | — | no systematic shift (see below) |
| Output | sha `202f0f75…` | sha `202f0f75…` (identical) |

Caveats: the legacy reference carried no loader instrumentation (fast-path numbers include instrumentation overhead — delta conservative); its region is unstated/assumed same-shape; the ~1.4s empty-to attribution is the analytic estimate the delta is consistent with, not a directly measured quantity. The previously cited AWS "real H2D ~5.9s" figure is a different platform/bus context and is **not** used as a baseline.

Sampling: baseline legacy event-pair 4978.2 ms (17-19-55). Fast runs: 4882.9 (−1.9%), 4873.7 (−2.1%), 5459.2 (+9.7%). No systematic shift; within ±10% with one single-run outlier (n=3).

---

# Remaining loader decomposition

(medians of A/B/C; separated as far as measurements allow)

- **Volume/page servicing:** `load_torch_file` 962.9 ms — mmap open/header/lazy construction + faulting of the 12.31 GB checkpoint from the mounted volume (0/0 minor/major faults reported by the diagnostic counter; read records show ~12.31 GB at ~12 GB/s).
- **CPU→GPU transfer:** synchronized single H2D **2320.9 ms** (2150.0–2396.5) — includes caching-allocator work, the real-weight H2D, and the explicit drain. `to_wall ≈ to_device` (Δ ≤ 0.08 ms) proves the mmap pages were resident before H2D (no CPU stall inside `to`).
- **Python bookkeeping:** get_model 39.97 + literal ctor 0.136 + bind 17.47 + SD residual 3.49 ≈ **61 ms**; plus pre-span detection/config scans (~0.1–0.2s in graph_loader read records).
- **Synchronization/allocator:** inside the 2320.9 ms synchronized span (cannot be separated further without side-stream events); legacy paid the same class of cost at first `copy_` after the empty-`to` allocation.
- **First-use work:** demand→first CUDA op 101.9–120.1 ms; loader-return→first-forward 201.7–222.7 ms (includes first-op, weight residency checks).
- **Residual:** SD-span residual 3.5–21.3 ms; pre-sampler residual ~19–22 ms; waterfall residual is platform scheduling (`captured_timeline_gap`), not loader.

---

# Deferred optimizations

Listed only — **not implemented** (per task scope):

- Known-size `ModelPatcher` construction (`size=` pass-through) — removes the first `model_size()` → `module_size()` full `state_dict()` traversal.
- Repeated traversal caching (`_load_list`/`patch_weight_to_device` per-module state-dict walks, keyed by `patches_uuid`).
- CLIP↔UNET overlap optimization (owned by a separate concurrent agent).
- Sampling optimization (owned by a separate concurrent agent; no changes made here).

---

# Recommended next action

**One action:** complete the single outstanding remote evidence gap — LoRA/hook/unload-reload parity on the fast path in the integrated UNET-absent production configuration (the same gate configuration above, with a LoRA applied and one unload/reload cycle) — and on pass, enable `COMFYMODAL_V2_NATIVE_FAST_DISK_UNET` by default for HIGH_VRAM + uniform-dtype UNET file loads, guard set unchanged. Rationale: the integrated production acceptance already proves the intended production behavior (CPU_MODEL_SNAPSHOT=1 → CLIP/VAE restore → UNET absent → graph-time UNETLoader → fast path engages → defer+complete proof → bit-exact generation), so the flag is ready for promotion pending only patching-semantics parity. Restore/eviction architecture remains the restore agent's domain; no further loader benchmarks are warranted by the measured result.

---

**Artifacts:** `comfymodal-data\benchmarks\runs\v2_2026-08-11_21-40-24`, `...\21-44-20`, `...\21-45-13` (fast path); `...\v2_2026-08-11_21-04-13` (legacy same-shape reference); `...\v2_2026-08-11_17-19-55` (output-parity baseline).
