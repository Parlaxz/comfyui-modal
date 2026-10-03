# Production 009 — Phase 4: VAE residency audit

Is the VAE work that still happens inside `VAE.decode()` after `golden_vae_load`
redundant, and can it be bypassed?

**Answer: no. It is `REQUIRED`.** It is not a repeat of anything `golden_vae_load`
did — it is the *first and only* DynamicVRAM activation of the VAE patcher, and it
moves real bytes. The recoverable cost is not removal, it is **relocation** into the
existing `sampling ‖ vae_load` overlap window. See §14–§16.

---

## 1. Audit base SHA

| item | value |
|---|---|
| `AUDIT_BASE_SHA` | `211d204b06f1246bbd2b5b591473d7d08b629030` |
| `AUDIT_BRANCH` | `audit/vae-residency` |
| `AUDIT_WORKTREE` | `.slim/worktrees/vae-residency-audit` |

`211d204b` (`docs(golden-source): report the pathological source stall mechanism`) is the
tip of `exp/source-copy-isolation` and is the shared base of the active Phase-2/3 lane:

```
main                       ccc2c531
 └─ exp/source-copy-isolation  211d204b   ← audit base (Phase-1 diagnostic complete)
     ├─ ac56539b  d4613e19              ← Phase 2A Triton audit (p8fix, detached)
     └─ .slim/worktrees/p8fix  + dirty comfymodal_runtime/modal_app.py  ← Phase 2/3 WIP
```

Verified, not guessed:

```
git merge-base exp/source-copy-isolation opt/p8-profile-cleanup-1 -> a2eca97c
git merge-base exp/source-copy-isolation main                      -> ccc2c531
git rev-list --count main..exp/source-copy-isolation               -> 11
git diff --stat 211d204b d4613e19 -> comfymodal_runtime/modal_app.py | 190 +++
                                                         reports/P9_TRITON_INSTALLED_AUDIT.md | 149 +++
git -C .slim/worktrees/p8fix status  -> M comfymodal_runtime/modal_app.py
                                       ?? reports/P9_PHASE3_DESIGN.md
```

`d4613e19` and the dirty `modal_app.py` are **excluded**. Neither the dirty root checkout
nor the `p8fix` / `source-copy-isolation` worktrees were modified by this audit.

### 1.1 Profiling provenance vs audit base

The P9 traces were captured at source `fbd81c46`. `fbd81c46` is an ancestor of `211d204b`
and the delta touches no VAE path:

```
git diff --stat fbd81c46 211d204b
  comfymodal_runtime/golden_serial.py | 5 +++++   (5 lines, inside golden_unet_load)
  ... source-probe, flag-registry, config, reports, tests
```

The 5 `golden_serial.py` lines are a telemetry field inside `golden_unet_load`
(`unet_layout_preresolve_join_completed`). `golden_vae_load` / `golden_vae_decode` /
`VAE.decode` / `load_models_gpu` are byte-identical between the profiled build and the
audit base.

### 1.2 ComfyUI identity

`comfyapp.py:8258` pins `_COMFYUI_PINNED_COMMIT = 169fcf35a2fc163fec31338b816503ddac0d3fcf`
(upstream v0.34.2), cloned fresh in the image (`comfyapp.py:8323-8330`). Every
`file:line` in the P9 artifacts resolves against pristine `169fcf35`:

| artifact reference | pristine `169fcf35` |
|---|---|
| `model_management.py:909` | `def load_models_gpu(...)` — line 909 |
| `model_management.py:863` | `def free_memory(...)` — line 863 |
| `model_management.py:782` | `def model_load(...)` — line 782 |
| `model_management.py:817` | `def model_use_more_vram(...)` — line 817 |
| `model_management.py:776` / `:767` | `model_memory_required` / `model_memory` |
| `model_management.py:631` / `:1045` | `module_size` / `archive_model_dtypes` |
| `model_management.py:1748` | `get_free_memory` |
| `model_patcher.py:405` / `:945` | `ModelPatcher.model_size` / `_load_list` |
| `model_patcher.py:899` / `:1853` / `:2141` | `patch_weight_to_device` / `ModelPatcherDynamic.load` / `partially_load` |
| `sd.py:1220` / `nodes.py:333` | `VAE.decode` / `VAEDecode.decode` |

Caveat recorded honestly: the **developer's local ComfyUI checkout carries an uncommitted
`comfy/model_management.py` patch** (a `soft_empty_cache` bypass, +144/-11) that shifts
`load_models_gpu` from 909 to 921. That patch is **not** in the container image. All
findings below were re-verified against pristine `HEAD:comfy/model_management.py`; the
patched and pristine bodies are control-flow identical on the load path (it only adds a
`minimum_memory_required=` kwarg to the two `free_memory` calls and widens the
`soft_empty_cache` signature).

---

## 2. Worktree / branch

Branch `audit/vae-residency`, worktree `.slim/worktrees/vae-residency-audit`, created from
`211d204b`, clean at start. Not merged, not cherry-picked, not promoted, not tagged.

---

## 3. Exact VAE call graph

All `file:line` are pristine `169fcf35` unless marked `comfyui-modal`.

```
run_golden_parallel_stream                              comfymodal_runtime/golden_parallel.py
└─ _golden_stage_pair_overlap(kind=sampling_vae, pair=(golden_sampling, golden_vae_load))
   │  schedule = COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE = "overlap"
   │  (config/v2/profiles/golden_p1_parallel_c0_source_h100.toml:45; inherited by
   │   golden_p1_parallel_c0_p8_h100, the profiled profile)
   ├─ golden_sampling        ────────────────┐ concurrent
   │  └─ _prepare_sampling                    │  comfy/sampler_helpers.py:188
   │     └─ load_models_gpu([unet] + extra)   │  comfy/model_management.py:909
   │        └─ LoadedModel.model_load         │
   │           └─ model_use_more_vram         │
   │              └─ ModelPatcherDynamic.partially_load   mp:2141   ← UNET, not VAE
   └─ golden_vae_load                          │
      └─ _vae_load_with_worker_stage          │  golden_parallel.py:522
         └─ golden_vae_load                   │  golden_serial.py:14315
            ├─ [worker thread] GoldenModelTransport._load_c0_source_threads_sync
            │                 → H2D of the whole ae.safetensors into QD views
            ├─ require_dynamic_core_model_patcher(tag="vae")   golden_serial.py:14387
            ├─ comfy.sd.VAE(sd=views, device=cuda:0, dtype=source, metadata=...)
            │  └─ VAE.__init__                                  sd.py:487
            │     ├─ mp = comfy.model_patcher.CoreModelPatcher  sd.py:1080
            │     │     == ModelPatcherDynamic  (rebound at import time by
            │     │        golden_aimdo_activation.py:183, mirroring ComfyUI main.py:233)
            │     ├─ self.patcher = mp(first_stage_model, load_device=cuda:0,
            │     │                       offload_device=cpu)   sd.py:1083
            │     │     └─ ModelPatcherDynamic.__init__ → register_load_device(cuda:0)
            │     │        creates dynamic_pins[cuda:0] with
            │     │        hostbufs_initialized=False, active=False   mp:1780
            │     └─ first_stage_model.load_state_dict(views, strict=False, assign=True)
            │                                                     sd.py:1085
            ├─ validate_qd_adoption("vae", [first_stage], views) golden_serial.py:12971
            │     → fail-closed 1:1 data_ptr proof: every param AND buffer is a CUDA
            │       tensor whose storage IS a QD transport view
            ├─ session.vae = vae ; session.vae_owner = owner ; register_qd_owner(owner)
            └─ rec.end_stage("golden_vae_load", ...)
                        │
                        ▼  (sampling ‖ vae_load window closes; sampler_tail is a no-op,
                           │   0.045 ms, no unload / no empty_cache / no GC)
            golden_vae_decode                                  golden_serial.py:14528
            ├─ runner.seed(node_map.vae_loader_id, [[session.vae]])   ← the SAME object
            ├─ runner.run_closure(vae_decode_id, include_target=True)
            │  └─ VAEDecode.decode                             nodes.py:333
            │     └─ VAE.decode(samples, {})                    sd.py:1220
            │        ├─ memory_used = self.memory_used_decode(shape, dtype)   sd.py:498
            │        ├─ model_management.load_models_gpu([self.patcher],
            │        │        memory_required=memory_used,
            │        │        force_full_load=self.disable_offload)  sd.py:1230
            │        │  └─ free_memory(model_size*1.1 + extra_mem, for_dynamic=True)  mm:909
            │        │  ├─ free_memory(minimum_memory_required, ...)             mm:909
            │        │  └─ LoadedModel.model_load(0)                              mm:782
            │        │     ├─ model_patches_to(device) / model_patches_to(dtype)
            │        │     └─ model_use_more_vram(1e32)                           mm:817
            │        │        └─ ModelPatcherDynamic.partially_load(cuda:0, 1e32) mp:2141
            │        │           ├─ unpatch_model(offload_device, unpatch_weights=False)
            │        │           ├─ patch_model(load_weights=False)
            │        │           └─ ModelPatcherDynamic.load(cuda:0, dirty=...)    mp:1853
            │        │              ├─ restore_loaded_backups()  → model_loaded_weight_memory = 0
            │        │              ├─ first-time AIMDO pin host buffers
            │        │              │    (pinned_hostbuf_size(model_size) ×2)
            │        │              ├─ _load_list(for_dynamic=True)                  mp:945
            │        │              ├─ per module: setup_param / force_load_param OR vbar.alloc
            │        │              ├─ named_buffers → casted_buf.to(device)
            │        │              ├─ model.device = cuda:0 ; current_weight_patches_uuid = …
            │        │              └─ ON_LOAD callbacks ; apply_hooks(forced_hooks)
            │        │           └─ current_loaded_models.insert(0, loaded_model)   mm:1026
            │        ├─ free_memory = patcher.get_free_memory(cuda:0)  (batch sizing only)
            │        └─ first_stage_model.decode(...)      ← the 636 / 784 / 895 ms
            └─ session.images = images
```

**Object identity across the whole interval is structural, not coincidental:**

| property | evidence |
|---|---|
| same `VAE` object | `golden_serial.py:14547` seeds the runner cache with `session.vae`; `run_closure`'s `visit()` returns immediately for a cached node (`golden_serial.py:9151`), so the `VAELoader` node never re-executes |
| same patcher | `comfy.sd.VAE.__init__` builds exactly one patcher (`sd.py:1083`); nothing re-patches or clones it |
| no alternate VAE | `resolve_golden_node_map` fails closed on duplicate `VAELoader`/`VAEDecode` (`golden_serial.py:9250-9262`) and requires the loader's `vae_name == contract.vae_name` |
| single request | `restore_count == 1`, `request_count == 1`, single-use containers (p9opt README §Provenance) |

---

## 4. `golden_vae_load` semantics

**Question: after `golden_vae_load`, is the VAE fully resident on GPU, partially
resident, logically registered only, resident but evictable, or patched but not fully
loaded?**

Precise answer, in two independent parts:

| aspect | state after `golden_vae_load` | why |
|---|---|---|
| **weight bytes** | **fully resident on GPU** — every parameter and buffer is a CUDA tensor whose storage is byte-identical to a QD transport view | `load_state_dict(..., assign=True)` at `sd.py:1085` + fail-closed `validate_qd_adoption` (`golden_serial.py:12971`) |
| **DynamicVRAM activation** | **not activated** — `dynamic_pins[cuda:0]` exists with `hostbufs_initialized=False`, `active=False`; no `_v` vbar block on any module; no `weight_function` / `lowvram_function` installed; no AIMDO host buffers allocated | `ModelPatcherDynamic.__init__` → `register_load_device` (`mp:1770-1789`) only *creates* the state; only `load()` sets `hostbufs_initialized` (`mp:1875-1881`) and `active=True` (`mp:1883`) |
| **model-management registry** | **absent** — the patcher is not in `model_management.current_loaded_models` | the registry insert is `mm:1026`, reachable only through `load_models_gpu` |
| **`model_loaded_weight_memory`** | `0` | `ModelPatcher.__init__` initialises it to 0 (`mp:387-388`) |
| **patcher class** | `ModelPatcherDynamic` (`is_dynamic() == True`) | `CoreModelPatcher` rebound at `golden_aimdo_activation.py:183` |

Answers to the five specific questions:

1. **Not** "fully resident" in the DynamicVRAM sense. It is *fully weight-resident and
   entirely DynamicVRAM-unregistered*. That distinction is the whole finding.
2. **No.** `ModelPatcher`, `DynamicVRAM` and `model_management` are left in exactly the
   state `VAE.decode` does **not** expect: `VAE.decode` calls `load_models_gpu` precisely
   because the patcher has never been loaded.
3. **Yes, all VAE bytes are transferred** during `golden_vae_load`
   (`h2d_completed_bytes = 335278732`, `source_read_count = 10`;
   `GOLDEN_SUITE_GATE_REPORT.md` §10, corroborated for every recorded run in
   `reports/golden_sickness_forensic_2026-09-17/per_request.json`). No second H2D occurs
   at decode.
4. **No.** It is not a lazy initiation — the full transport, the full H2D and the full
   zero-copy adoption complete before `end_stage`.
5. **No residency token exists.** There is no "preload-complete" generation counter, no
   loaded-weight amount that survives, and nothing a future bypass could consult. The only
   pre-existing discriminators are the `dynamic_pins` flags above and
   `patcher.loaded_size() == 0`.

---

## 5. State before decode

Interval audited: `golden_vae_load` end → `golden_sampling` end → `golden_sampler_tail` →
`golden_vae_decode`.

| # | question | answer | evidence |
|---|---|---|---|
| 1 | Can CLIP/UNET/sampler model-management activity evict VAE weights? | **No** | eviction only reaches models in `current_loaded_models` (`mm:871-894`); the VAE is not in it. Even if it were, `free_memory(..., for_dynamic=True)` sets `memory_to_free = 0` for dynamic models (`mm:884-888`) — "don't actually unload dynamic models … that works on-demand". `VAE.decode` calls `load_models_gpu` with only the VAE, so `free_for_dynamic` is True. |
| 2 | Does DynamicVRAM reclaim or repack VAE memory? | **No** | AIMDO operates through `dynamic_pins`/`dynamic_vbars`, both inactive for the VAE. `vbar.alloc` is never called for it. |
| 3 | Does any model patching invalidate VAE resident state? | **No** | the VAE patcher is never patched (`self.patches` empty; no LoRA node in the Golden graph). Nothing calls `unpatch_model` on it before decode. |
| 4 | Does loaded-model bookkeeping change? | **Only for other models** | UNET/CLIP `LoadedModel`s are inserted/refreshed at `mm:1026`. The VAE is untouched. |
| 5 | Does memory pressure cause a partial unload? | **No, for the VAE** | `partially_unload` is reachable only via `LoadedModel.model_unload` (`mm:805-815`), again only for registered models. |
| 6 | Is the VAE still resident immediately before decode? | **Yes — all bytes, still on GPU** | QD owner is held three ways (`session.vae_owner`, `session.register_qd_owner`, `vae._golden_qd_owner`), transport quiescence is proven (`_require_transport_quiescence`), and `soft_empty_cache()` only releases *cached* allocator blocks, never live tensors. |
| 7 | Is the exact same VAE object/patcher used? | **Yes** | §3 identity table. |
| 8 | Can a different VAE be selected dynamically before decode? | **No** | the Golden path has no dynamic VAE resolution seam (no `resolve_vae_object`, no `SelectDevice`, no bridge). `resolve_golden_node_map` fails closed on ambiguity. |

`golden_sampler_tail` is a 0.045 ms no-op by construction and by measurement: its own
docstring states it performs "NO full GC, NO model unload, NO `torch.cuda.empty_cache()`,
and NO allocator purge".

---

## 6. `load_models_gpu` semantics

Exact call: `load_models_gpu([self.patcher], memory_required=<decode estimate>,
force_full_load=self.disable_offload)` with `self.disable_offload == False`
(`sd.py:508`; no config branch in the Flux-2 path sets it), so `force_full_load=False`
and the patcher stays `ModelPatcherDynamic`.

| category | what actually happens | GOOD-fastest cost |
|---|---|---|
| dedup / order-preserving set build | `models_temp` over `[patcher] + patcher.model_patches_models()` (`mm:933-940`) | included in self |
| registry lookup | `LoadedModel(x)` then `current_loaded_models.index(...)`; miss here (`mm:948-961`) | — |
| clone eviction | `is_clone` scan over the registry (`mm:963-971`) | — |
| **memory accounting** | `LoadedModel.model_memory_required(device)` → `model_offloaded_memory()` → `model_size()` → `comfy.model_management.module_size(self.model)`; **`model_size()` is recomputed from scratch**, `VAE.__init__` already called `model_size()` at `sd.py:1093` | **5.451 ms** |
| **eviction** | two `free_memory(...)` calls (`mm:981-999`); measured 1.304 ms | **1.304 ms** |
| lowvram sizing | `lowvram_available and (LOW_VRAM or NORMAL_VRAM)` is False on this deployment (no ComfyUI CLI args are set, H100) ⇒ `lowvram_model_memory = 0` ⇒ `model_load(0)` ⇒ `use_more_vram = 1e32` | — |
| **device placement + weight transfer** | delegated entirely to `partially_load` | **65.542 ms** |
| **patching** | delegated entirely to `partially_load` | included above |
| **synchronization** | none in `load_models_gpu` itself | 0 |
| registry insert | `current_loaded_models.insert(0, loaded_model)` (`mm:1026`) | — |
| **no-op fast path** | **does not exist** for this call — `partially_load` always runs | — |

Answers:

1. **Does it actually transfer model bytes in the measured path?** **Yes**, but not the
   model. See §7.
2. **How many bytes?** See §10 — bounded, exact value pending the opt-in probe.
3. **Does it call `partially_load`?** Yes, exactly once, via
   `model_load → model_use_more_vram → partially_load`.
4. **Is `partially_load` nested completely inside it?** Yes — one occurrence each in all
   three traces, strictly nested (§9).
5. **Mostly wrapper, or real work?** ~10 % wrapper (7.486 ms of 73.028), ~90 % real
   DynamicVRAM work inside `partially_load`.
6. **CUDA synchronization?** No.
7. **Waits on outstanding work?** No — but it *serialises* behind the 636 ms decode
   forward that follows it in the same node, which is the real cost structure.
8. **Does it recalculate required free memory?** Yes, twice: `extra_mem` /
   `minimum_memory_required` from `minimum_inference_memory()` +
   `memory_required + extra_reserved_memory()` (`mm:925-930`), plus the two
   `free_memory` passes.

---

## 7. `ModelPatcherDynamic.partially_load` semantics

`partially_load(device_to, extra_memory=1e32, force_patch_weights=False)` (`mp:2141`):

1. `unpatch_model(offload_device, unpatch_weights=False)` + `patch_model(load_weights=False)`
2. `load(device_to, dirty=dirty)` (`mp:1853`)
3. returns `None` — explicitly *"nothing in core uses this and we have no data in the
   Dynamic world"* (`mp:2154-2158`). **There is no early-exit guard, and none exists
   upstream.**

`load()` then does, in order:

| step | first-time? | measured (GOOD fastest) |
|---|---|---|
| `restore_loaded_backups()` → zeroes `model_loaded_weight_memory` | no-op on a virgin patcher (empty `backup`) | 0 (not in the ≥1 ms table) |
| **allocate AIMDO pin host buffers** (`HostBuffer` ×4 sized `pinned_hostbuf_size(model_size)` = `min(size, MAX_PINNED) * 2`, `mp:1876-1881`) and set `active=True` | **YES — first and only time** | inside `load` self 1.733 ms |
| `_load_list(for_dynamic=True)` — `named_modules` + `module_size` per module + sort | **YES** | **13.617 ms** |
| per module with `comfy_cast_weights`: `setup_param` (installs `weight_function` / `lowvram_function`, sets `weight._model_dtype`) then either `force_load_param` or `m._v = vbar.alloc(...)` | **YES** | `setup_param` 4.757 ms (136 calls) |
| `force_load_param` → `patch_weight_to_device(..., force_cast=True)` | **YES** | **40.096 ms over 108 calls** |
| `named_buffers` → `casted_buf = buf.to(dtype, device)` + `set_attr_buffer` | **YES** | 1.184 ms |
| `model.device = device_to` ; `model.current_weight_patches_uuid = patches_uuid` | **YES** | — |
| `CallbacksMP.ON_LOAD` callbacks + `apply_hooks(forced_hooks)` | **YES** | — |

Answers:

1. **What state causes it to execute?** None — it executes unconditionally on every
   `load_models_gpu`. There is no "already resident" fast path.
2. **Does it move actual weights?** Yes, for the 108 force-loaded parameters.
   `patch_weight_to_device` (`mp:899`) does two real transfers per parameter:
   * `weight.to(device=self.offload_device)` — `offload_device` is **cpu** (no
     `--gpu-only`; `vae_offload_device()` → `model_management.py:1273`) ⇒ **D2H**;
   * `cast_to_device(weight, cuda:0, None, copy=True)` — `cast_to` sees
     `weight.device == device` and returns `weight.to(copy=True)` ⇒ **D2D**
     (`model_management.py:1548-1559`).
   Then `set_attr_param` rebinds the parameter to the fresh copy and
   `model_loaded_weight_memory` is incremented (`mp:1957`).
3. **Does it patch tensors?** No LoRA patches are present; the transfers are pure
   dtype/device casts with `force_cast=True`.
4. **Does it simply validate already-resident state?** **No.** This is the decisive
   answer: it *rebuilds* the weight objects, replacing the zero-copy QD-view parameters
   that `validate_qd_adoption` proved at preload with fresh D2D copies. The zero-copy
   adoption is not honoured at decode time.
5. **Does it allocate GPU memory?** Yes — the force-loaded parameter copies, plus the
   first-time AIMDO pinned host buffers (host RAM, not VRAM).
6. **Does it synchronize?** No explicit CUDA sync in the Python path.
7. / 8. **Bytes newly loaded in GOOD vs BAD:** see §10.
9. **Does it behave differently when VAE preload succeeded?** **No.** There is no
   preload-success signal it could consult; the patcher's `dynamic_pins` entry is
   indistinguishable from a never-seen model.
10. **Could it return immediately if a valid residency guard existed?** Only if that
    guard also covered the four side effects `load()` performs — vbar/pin-state
    activation, per-module weight-function installation, `model.device` /
    `current_weight_patches_uuid`, and the `current_loaded_models` insert at
    `mm:1026`. None of those are "residency"; they are DynamicVRAM registration. A
    residency guard alone is therefore insufficient, which is why the classification is
    not `REDUNDANT_WITH_GUARD`.

---

## 8. Timing tree — inclusive, self, nesting

From `reports/golden_profiler_p9opt/golden_stage_trees_*.md` (three traced Golden runs,
source `fbd81c46`, H100, `batch-p9opt1-prof`). Absolute ms are profiler-inflated
(README: "Use these reports for mechanism and ranking").

```
golden_vae_decode                                     719.073 | 1013.777 | 874.022
└─ VAEDecode.decode            nodes.py:333           718.246 | 1011.378 | 873.083
   └─ VAE.decode               sd.py:1220             718.219 | 1011.337 | 873.031
      ├─ VAE.decode self                             635.965 |  895.450 | 783.635
      ├─ VAE.__init__.<locals>.<lambda>   (×2)         8.319 |    7.996 |  ~8.3
      └─ load_models_gpu        mm:909                  73.028 |  110.675 |  78.091   ← 1 call
         ├─ load_models_gpu self                        0.082 |    0.137 |   0.085
         ├─ LoadedModel.model_memory_required            5.451 |    6.017 |   6.497
         │  └─ … → ModelPatcher.model_size → module_size 5.443 |    6.006 |   6.487
         ├─ free_memory          mm:863                  1.304 |    3.061 |   1.399
         │  └─ get_free_memory                           (—)   |    1.602 |   1.154
         └─ LoadedModel.model_load      mm:782          65.595 |  100.182 |  69.572   ← 1 call
            └─ model_use_more_vram     mm:817           65.545 |  100.130 |  69.523
               └─ ModelPatcherDynamic.partially_load
                                                   mp:2141
                                                      65.542 |  100.126 |  69.520   ← 1 call
                  └─ ModelPatcherDynamic.load  mp:1853 65.433 |  100.024 |  69.387
                     ├─ _load_list        mp:945       13.617 |   23.678 |  13.451
                     ├─ named_buffers      module.py   1.184 |    ~1.23 |   1.237
                     ├─ force_load_param   mp:1947     40.096 |     (≈)  |  43.839  ← 108 calls
                     │  └─ patch_weight_to_device       32.311 |     (≈)  |  (≈)
                     │     ├─ namedtuple   collections   9.954 |     (≈)  |   (≈)   ← 108 calls
                     │     ├─ cast_to_device mm:1555     6.174 |     (≈)  |   (≈)
                     │     └─ set_attr_param utils       5.963 |     (≈)  |   (≈)
                     ├─ setup_param        mp:1918      4.757 |     (≈)  |   5.527  ← 136 calls
                     └─ load self                           1.733 |    2.055 |   1.677
                                                                        (columns: GOOD-fastest
                                                                         / BAD / GOOD-healthy)
```

Nesting is unambiguous and identical in all three traces:

```
load_models_gpu
└── LoadedModel.model_load
    └── LoadedModel.model_use_more_vram
        └── ModelPatcherDynamic.partially_load
            └── ModelPatcherDynamic.load
```

`partially_load` is a strict descendant of `load_models_gpu`, one occurrence each. The
enclosing indentation in the artifact confirms it (GOOD-fastest indents 14 / 16 / 18 / 20
/ 22 spaces respectively), and `tests/test_vae_residency_audit.py` asserts that ordering
against the committed artifacts so it cannot silently change.

### 8.1 What dominates: transfer, or framework overhead?

GOOD-fastest, the 73.028 ms breaks down as **framework/Python overhead, not bandwidth**:

| leaf | ms | share |
|---|---:|---:|
| `collections.namedtuple` class creation, 108× | 9.954 | 13.6 % |
| `get_key_weight`, 704× | 13.328 | 18.2 % |
| `Module.__getattr__` / `get_attr`, 7258× / 704× | 6.259 + 7.040 | 18.2 % |
| `Module.__setattr__` / `set_attr_param`, 1047× / 108× | 5.894 + 5.963 | 16.2 % |
| `cast_to_device` / `cast_to` (the actual copies), 108× | 6.174 | 8.4 % |
| `_load_list` (`named_modules` 4205×, `module_size` 123×, `state_dict` 356×) | 13.617 | 18.6 % |

---

## 9. Actual bytes transferred

| question | answer |
|---|---|
| Is there a transfer at decode? | **Yes** |
| H2D of the model? | **No.** All 335,278,732 model bytes were transferred during `golden_vae_load`. |
| What is transferred at decode? | For each of the **108** force-loaded parameters: one **D2H** copy to the CPU `self.backup` (`mp:906-907`) and one **D2D** copy back to `cuda:0` (`mp:911` → `cast_to(..., copy=True)`), then `set_attr_param` rebinds the parameter to the new tensor. |
| `LOAD_MODELS_GPU_ACTUAL_TRANSFER` | **yes** (D2H + D2D, not H2D) |
| `LOAD_MODELS_GPU_TRANSFER_BYTES` | **unknown** — see bound below |

**Upper bound, and why it is a small one.** `force_load` is set at `mp:1972-1975` only
when `module_mem <= 16 * 1024`, or when a resizing LoRA forces it (`mp:1967-1973`). This
VAE has no patches, so every force-loaded module is a *small* one. With 108 such
parameters, the moved volume is on the order of a few MiB, not 335 MB — bounded above by
`108 × 16 KiB ≈ 1.7 MiB` and, trivially, by `model_size = 335,278,732 B`.

> Provenance of the 335,278,732 B / 244-parameter figures: `GOLDEN_SUITE_GATE_REPORT.md`
> §10, an RTX PRO 6000 Blackwell Golden run, not one of the three H100 p9opt traces. Both
> facts are properties of `flux2-vae.safetensors` (file size, parameter count), are
> device-independent, and the byte figure is identical for every run recorded in
> `reports/golden_sickness_forensic_2026-09-17/per_request.json`. They are cited from a
> different run than the timings above and are labelled rather than merged.

**Why the exact figure is not asserted.** The exact byte sum depends on the module layout
of `flux2-vae.safetensors`, which is not in the committed artifacts. Per the repo's own
evidence discipline (the V2 lane's `_probe_vae_activation_evidence` docstring: *"no
fabricated evidence"*), this audit reports the bound rather than a guessed number. The
opt-in probe added in §13 measures `patcher.loaded_size()`, `model_loaded_weight_memory`,
`backup` count and per-device parameter bytes directly, so one true-cold run closes this
to an exact figure.

**What the transfer costs is not bandwidth.** Per §8.1, ~70 % of the 73 ms is Python
attribute walking and `collections.namedtuple` class creation, and only ~8 % is the
copies themselves.

---

## 10. DynamicVRAM interaction

How VAE residency interacts with the rest of the DynamicVRAM machinery:

* **Activation.** `CoreModelPatcher` is rebound to `ModelPatcherDynamic` before any model
  is constructed (`golden_aimdo_activation.py:183`, mirroring upstream `main.py:233`), and
  `comfy.memory_management.aimdo_enabled = True`. Every `VAE.__init__` therefore builds a
  dynamic patcher; `disable_offload=False` keeps it dynamic.
* **AIMDO pin state.** Created at construction (`mp:1780`), *activated* at the first
  `load()` (`mp:1875-1883`). Between those two points the patcher is inert to AIMDO.
* **Offload device.** `vae_offload_device()` → `cpu` (`mm:1273`); no `--gpu-only`. This is
  what makes `patch_weight_to_device`'s backup a real D2H copy rather than a no-op.
* **Free-memory thresholds.** `load_models_gpu` computes
  `extra_mem = max(minimum_inference_memory(), memory_required + extra_reserved_memory())`
  (`mm:925-930`), where `minimum_inference_memory() = 0.8 GiB + 400 MiB`. It then makes two
  `free_memory` passes (`mm:981-999`).
* **Dynamic models are exempt from eviction.** `free_memory(..., for_dynamic=True)` sets
  `memory_to_free = 0` for every dynamic model (`mm:884-888`). Since `VAE.decode` requests
  only the (dynamic) VAE, `free_for_dynamic` is True — so the decode-time load **cannot
  evict the UNET or CLIP**, and conversely cannot be evicted once registered.
* **UNET / CLIP residency.** Independent patchers, independent `dynamic_pins`. The UNET's
  `partially_load` in the traced `golden_vae_load` window (`sampler_helpers.py:201`
  → 117.6 ms and 172.6 ms in GOOD-fastest, 824 `force_load_param` calls) is a *different
  patcher* and shares nothing with the VAE beyond the device.
* **Sampler lifecycle.** Sampler prepare/prepare_sampling only ever loads
  `[model] + additional_models` where `model` is the UNET (`sampler_helpers.py:188-201`).
  The Golden VAE is never in that list.
* **Alternate VAE / request boundaries.** Not applicable to the Golden path (§3, §5).
* **VRAM reclamation.** `soft_empty_cache()` is reached only from `free_memory`; it releases
  cached allocator blocks, never the live QD-view tensors the VAE holds.

**Guard candidates considered, and the smallest one that would actually prove safety:**

| candidate | sufficient? | why |
|---|---|---|
| same VAE object / same patcher id | **no** | identity is already guaranteed (§3) and the work still runs |
| same patcher generation / `patches_uuid` | **no** | `load()` *sets* `current_weight_patches_uuid`; it is not a precondition |
| same device | **no** | `load()` *sets* `model.device`; it is not a precondition |
| same loaded-byte count | **no** | `loaded_size()` is 0 before decode and only becomes non-zero *because of* `load()` |
| no intervening eviction | **no** | nothing can evict the VAE (§5), so this is vacuously true and proves nothing |
| preload-complete token | **does not exist** | nothing in the preload emits one (§4.5) |

There is **no existing state that both (a) proves the decode-time work is unnecessary and
(b) covers the four registration side effects `load()` performs.** Inventing one is out of
scope for this audit and would be the change, not the guard.

---

## 11. Eviction possibilities

| vector | can it hit the VAE before decode? | evidence |
|---|---|---|
| `free_memory` → `model_unload` | **no** | patcher not in `current_loaded_models` |
| `free_memory` dynamic exemption | **no** (belt and braces) | `mm:884-888` |
| clone-detach at `mm:963-971` | **no** | only same-patcher clones are detached |
| `cleanup_models_gc` | **no** | only scans registered `LoadedModel`s |
| `ModelPatcherDynamic.__del__` → `unpin_all_weights` | **no** | patcher is referenced by `session.vae` and by the runner cache |
| `soft_empty_cache` / `torch.cuda.empty_cache` | **no** | frees cached blocks; the QD views are live |
| AIMDO vbar reclaim | **no** | no `_v` block, no active pin state |
| QD owner release | **no** | held by `session.vae_owner`, `register_qd_owner`, `vae._golden_qd_owner` |
| memory-pressure OOM during sampling → partial unload | **no** | would raise, not evict; `golden_sampler_tail` does no cleanup |

**Inverse question (also relevant to §16):** once the VAE *is* registered at decode, can it
be evicted later? Post-decode the request only runs `golden_output` (PNG encode) and
teardown — no further `load_models_gpu`. And even if there were one, the dynamic exemption
at `mm:884-888` protects it.

---

## 12. Runtime identity / generation state

Available from existing ComfyUI APIs (no new state invented):

| signal | API | available before decode? |
|---|---|---|
| VAE identity | `id(vae)`, `id(vae.patcher)`, `id(vae.patcher.model)` | yes |
| patcher class / dynamicness | `type(patcher).__name__`, `patcher.is_dynamic()` | yes |
| device | `patcher.load_device`, `patcher.offload_device`, `patcher.model.device` | yes |
| model size | `patcher.model_size()` | yes |
| loaded bytes | `patcher.loaded_size()` (vbar + `model_loaded_weight_memory`) | yes — **0** before decode |
| force-loaded bytes | `model.model_loaded_weight_memory` | yes |
| AIMDO activation | `model.dynamic_pins[dev]["hostbufs_initialized"] / ["active"]` | yes — **False / False** |
| vbar staging | `model.dynamic_vbars[dev]`, `vbar.loaded_size()` | yes — absent |
| per-module staging | `hasattr(m, "_v")`, `hasattr(m, "weight_function")` | yes — absent |
| registry entry | `patcher in model_management.current_loaded_models` | yes — absent |
| patcher backups | `len(patcher.backup)`, `len(patcher.backup_buffers)` | yes — 0 |
| allocator | `torch.cuda.memory_allocated/reserved/max_memory_allocated` | yes |

**No generation/version counter exists for the patcher.** The only version-like token is
`patches_uuid`, and it is an output of `load()`, not an input to it.

This exact state is now captured automatically at three boundaries by the opt-in probe in
§13, so the missing "before/after" numbers in §9 need one run, not a new design.

---

## 13. Runtime evidence status

**Deliberately not collected in this audit, and why that is the right call.**

The static audit answered the classification question conclusively (§14). The only open
quantities are (a) the exact decode-time byte count (§9) and (b) measured
`loaded_size`/`dynamic_pins` before and after decode. Both are single-run questions, and
the instrumentation that answers them now exists:

* `comfymodal_runtime/vae_residency_audit.py` — default-OFF, read-only residency probe.
* Three gated call sites in `golden_serial.py`: `after_golden_vae_load`,
  `before_golden_vae_decode`, `after_golden_vae_decode`.
* Gate: `COMFYMODAL_VAE_RESIDENCY_AUDIT=1`. Unset ⇒ the module is never imported, nothing
  is read, nothing is emitted.

The probe reads only existing accessors and never calls `load`, `partially_load`,
`partially_unload`, `load_models_gpu`, `free_memory`, `detach`, `unpatch_model` or
`empty_cache`, so enabling it cannot perturb the measurement.

No profiler campaign was run, and no GPU request was made: the classification does not
depend on it, and Step 7 of the brief makes runtime evidence optional.

---

## 14. Final classification

# `REQUIRED`

**The decode-time VAE work is genuinely needed, and it is not redundant with
`golden_vae_load`.**

The load-bearing proof:

1. `golden_vae_load` never invokes the GPU load path on the VAE patcher — its only
   patcher operations are construction (`sd.py:1083`) and `load_state_dict(assign=True)`
   (`sd.py:1085`). `tests/test_vae_residency_audit.py` asserts this structurally so it
   cannot rot.
2. `ModelPatcherDynamic.__init__` leaves `dynamic_pins[dev]` with
   `hostbufs_initialized=False, active=False`, no `_v` on any module, no weight functions,
   no host buffers (`mp:1770-1789`).
3. Therefore the `partially_load` inside `VAE.decode` is the **first and only** DynamicVRAM
   activation of that patcher. Its cost is **deferred first-time setup**, not a repeat.
4. It moves real bytes (D2H + D2D on 108 parameters, §9) and performs four registration
   side effects that nothing else performs: AIMDO pin/vbar activation, per-module
   weight-function installation, `model.device` + `current_weight_patches_uuid`, and the
   `current_loaded_models` insert at `mm:1026`.

### Why not the other four

* **`REDUNDANT_AND_SAFE_TO_BYPASS`** — rejected. Nothing in the preload leaves the state
  decode needs: the registry entry, the AIMDO activation and the vbar staging do not exist
  until decode. Bypassing removes real work, not duplicated work.
* **`REDUNDANT_WITH_GUARD`** — rejected. Every guard candidate in §10 is either vacuous
  (identity, eviction — already guaranteed) or an *output* of `load()` rather than a
  precondition (loaded bytes, device, uuid). No small existing state proves safety, so
  there is nothing to guard with.
* **`PARTIALLY_REDUNDANT`** — considered seriously and rejected as the headline. It is
  factually true that ~7.5 ms of the 73.0 ms is wrapper bookkeeping, and that the D2D copy
  of already-CUDA weights inside `patch_weight_to_device` is pure waste that *undoes* the
  zero-copy adoption `validate_qd_adoption` proved. But that waste lives inside upstream
  `partially_load`, which this task explicitly forbids changing, and neither component can
  be bypassed on its own. Reporting `PARTIALLY_REDUNDANT` would have implied a
  bypassable slice exists; it does not.
* **`NEEDS_RUNTIME_EVIDENCE`** — rejected for the classification. Static evidence settles
  the mechanism (first-time activation, real transfers, no prior load). What remains
  unknown is a byte count, which does not change the classification.

### The finding that actually matters

`golden_vae_load` proves *byte-level* residency and then stops, leaving DynamicVRAM
completely un-engaged. The activation cost is therefore **moved** to the post-sampling
critical path rather than eliminated. Since `COMFYMODAL_GOLDEN_SAMPLING_VAE_SCHEDULE` is
already `"overlap"` on this profile (§3), the activation can be moved **back** into the
sampling window instead. That is a relocation, and it is the recommendation in §16.

---

## 15. Non-overlapping removable wall

`MAX_NON_OVERLAPPING_REMOVABLE_MS` — the ceiling if *everything* under
`load_models_gpu` were removed:

| run | `load_models_gpu` incl | `partially_load` incl (nested) | **MAX_NON_OVERLAPPING_REMOVABLE** | naive sum (**WRONG**) | overstatement |
|---|---:|---:|---:|---:|---:|
| GOOD fastest (`25172b0c`) | 73.028 | 65.542 | **73.028 ms** | 138.570 ms | +90 % |
| GOOD healthy (`ad2f1cf4`) | 78.091 | 69.520 | **78.091 ms** | 147.611 ms | +89 % |
| BAD (`ddb6c39a`) | 110.675 | 100.126 | **110.675 ms** | 210.801 ms | +90 % |

73.028 + 65.542 is a **double count**: `partially_load` is a descendant of
`load_models_gpu`, so its 65.542 ms is already inside the 73.028 ms. There is no proven
disjoint work elsewhere to add.

**The realistic ceiling is far lower than 73.028 ms**, because 65.542 ms of it is required
(§14). Only the wrapper bookkeeping is even a candidate, and it is itself load-bearing:

| run | `load_models_gpu` excl. `partially_load` | of which `model_memory_required` | of which `free_memory` | provably removable |
|---|---:|---:|---:|---:|
| GOOD fastest | 7.486 ms | 5.451 ms | 1.304 ms | **≈ 0** |
| GOOD healthy | 8.571 ms | 6.497 ms | 1.399 ms | **≈ 0** |
| BAD | 10.549 ms | 6.017 ms | 3.061 ms | **≈ 0** |

`model_memory_required` feeds `free_memory`'s eviction arithmetic and `free_memory` is the
eviction gate itself; the registry insert is mandatory. **So the answer to "how much wall
can be removed?" is: nothing.** The answer to "how much wall can be hidden?" is §16.

---

## 16. Minimal future implementation (NOT implemented here)

Because the classification is `REQUIRED`, the minimal change is **relocation, not
bypass**. `load_models_gpu` stays; only *when* it runs changes.

```
if <exact VAE is still the session VAE, still dynamic, still on the same device>:
    # moved into the existing sampling ‖ vae_load overlap window, before sampler_tail
    model_management.load_models_gpu([vae.patcher])   # the SAME canonical call
    record its completion
else:
    # unchanged canonical path
    ...
```

Reuse, do not reinvent:

* `golden_serial._golden_stage_pair_overlap` (`golden_serial.py:15556`) already owns the
  `sampling ‖ vae_load` window on the profiled schedule.
* `_stage_pair_metrics` (`golden_serial.py:15467`) already measures
  `wall_hidden_by_overlap_ms`, so the win is measurable with existing machinery.

**Prior art in this repository** — branch `opt/vae-activation-after-sampling`, commit
`418b6018` *"Add VAE activation at sampling end"*, did exactly this on the V2 (non-Golden)
path, and its shape is worth copying rather than re-deriving:

* it calls the **same** `_mm_load_models_gpu([_patcher])` — it does **not** bypass;
* gate `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end`, default `late`;
* it records `id(vae)`, `id(patcher)`, `cache_present`,
  `transfer_count = loaded_size_after > loaded_size_before`, `gpu_allocated_delta_bytes`,
  `current_device`, `load_device`, `compute_dtype`, `residency_status`;
* and it treats a failed residency proof as **`status="invalid",
  reason="residency_not_proven"`** — i.e. prior art agrees the load is required.

The Golden-path port is therefore: schedule the identical call inside the overlap window,
join it before `golden_sampler_tail`, and fall through to today's in-decode
`load_models_gpu` on any absent / failed / identity-changed outcome.

**Expected effect.** Up to 73.028 ms (GOOD-fastest) / 110.675 ms (BAD) hidden behind
sampling instead of sitting on the post-sampling critical path — bounded by the sampling
tail that remains. It is **not** a saving in total GPU work.

**Cost to weigh before implementing.** Moving the activation earlier means the VAE holds
its AIMDO pin host buffers (`pinned_hostbuf_size(model_size) × 2`, ~670 MB of pinned host
memory for a 335 MB VAE) and its registry entry *during* sampling. That is a GPU-memory and
host-memory policy change, which this task explicitly forbids and which therefore needs its
own scoped change with its own measurement.

---

## 17. Required safety guard

For the relocation in §16 (there is no bypass, so there is nothing to guard a bypass with),
the smallest sufficient guard is a **residency + identity token**, mirroring what the V2
lane already established:

```
same_vae      = id(vae) == id(session.vae)
same_patcher  = id(vae.patcher) == the id captured when the activation was scheduled
still_dynamic = type(vae.patcher).__name__ == "ModelPatcherDynamic" and vae.patcher.is_dynamic()
same_device   = str(vae.patcher.load_device) == captured_load_device
not_stale     = captured_load_device != "" and session.vae is not None

# after the relocated call
registered    = vae.patcher in model_management.current_loaded_models
resident      = vae.patcher.loaded_size() > 0
on_device     = all params of vae.first_stage_model on vae.patcher.load_device

if same_vae and same_patcher and still_dynamic and same_device and not_stale \
   and registered and resident and on_device:
    accept the relocated activation
else:
    run the unchanged in-decode model_management.load_models_gpu([vae.patcher])
```

Every field is an existing accessor (§12). `registered`, `resident` and `on_device` are
exactly the V2 lane's terminal validation, and its failure mode
(`residency_not_proven` → fall through) is the correct one here.

**A "no intervening eviction" clause is unnecessary and should not be added**: §11 shows
the VAE cannot be evicted before decode, and a vacuous condition is worse than no
condition because it reads like a guarantee.

---

## 18. Required tests for a future implementation

| # | test | asserts |
|---|---|---|
| 1 | same VAE, no eviction | relocated path taken; output SHA identical to the `late` path |
| 2 | VAE evicted between preload and decode | guard fails → canonical in-decode `load_models_gpu` runs; output SHA identical |
| 3 | alternate VAE selected before decode | `id(vae) != id(session.vae)` → fall through; no double registration in `current_loaded_models` |
| 4 | low-VRAM / partial residency | `load_device` retargeted or `loaded_size() < model_size()` → fall through |
| 5 | patcher generation change | `model.current_weight_patches_uuid != patcher.patches_uuid` at join → fall through |
| 6 | device change | `patcher.load_device != captured` → fall through |
| 7 | stale residency token | activation completes after the request finalised → future cancelled, fall through |
| 8 | normal fallback | any exception in the relocated call → canonical path, request still succeeds |
| 9 | **exact output SHA** | equals `3a6a03064c7e6e01ede339ada63daaea4cbf793f387f4faadbb101a787024577` (the p9opt cohort SHA) |
| 10 | no missing weights | `VAE.throw_exception_if_invalid()` passes; `len(missing)==0` from the adoption proof; first-stage param count still 244 |
| 11 | no stale model state | after decode: `model_loaded_weight_memory > 0`, `dynamic_pins[dev]["active"] is True`, patcher present in `current_loaded_models` exactly once |
| 12 | not double-registered | `current_loaded_models.count(patcher) == 1` after both the relocated and the in-decode call |
| 13 | A/B accounting | `sampling_vae` overlap metrics show the activation inside the window, and `golden_vae_decode` shrinks by ≈ the relocated amount — with no unexplained growth elsewhere |

Tests 9–13 are the ones that matter most: tests 1–8 can pass while the VAE silently ends up
half-registered.

---

## 19. What must NOT be changed

Explicitly out of scope for this audit, and out of scope for the §16 follow-up unless
separately justified:

* the **QD transport** or `assign=True` adoption in `golden_vae_load` — it is proven
  byte-exact by `validate_qd_adoption` and is the reason all bytes are already resident;
* `ComfyUI`'s `VAE.decode` (`sd.py:1230`) — upstream semantics, and the call is load-bearing;
* `ModelPatcherDynamic.partially_load` / `load` / `free_memory` — upstream DynamicVRAM;
* `CoreModelPatcher → ModelPatcherDynamic` rebinding or `aimdo_enabled`
  (`golden_aimdo_activation.py`);
* model-management policy: registry insert at `mm:1026`, the dynamic-eviction exemption at
  `mm:884-888`, `minimum_inference_memory`, `EXTRA_RESERVED_VRAM`;
* GPU memory policy: `pinned_hostbuf_size`, vbar sizing, `soft_empty_cache`;
* the workflow, the sampler, the model files, Modal settings;
* anything on the dirty root checkout, `.slim/worktrees/p8fix`, or
  `.slim/worktrees/source-copy-isolation`.

---

## 20. Commits on this branch

```
feat(audit): trace VAE preload and decode residency state
  comfymodal_runtime/vae_residency_audit.py     (new, default-OFF read-only probe)
  comfymodal_runtime/golden_serial.py            (3 gated probe call sites)
  tests/test_vae_residency_audit.py             (new, 37 tests)

docs(audit): report VAE residency redundancy analysis
  reports/P9_VAE_RESIDENCY_AUDIT.md              (this file)
```

Not merged. Not cherry-picked into the optimization lane. No production VAE behaviour was
changed.

### Test evidence

`tests/test_vae_residency_audit.py` — 37 passed.

Golden-path regression set (`test_p2_golden_core_contract`,
`test_golden_core_invariant_shield`, `test_golden_parallel_foundation`,
`test_ra9h_golden_clip_residency`, `test_golden_input_types_snapshot`,
`test_golden_exhaustive_profile`, `test_m2r_local_regression`):

| run | result |
|---|---|
| baseline `211d204b` (audit changes stashed) | 4 failed, 176 passed, 3 skipped |
| with audit instrumentation | 4 failed, 213 passed, 3 skipped |

Same 4 failures before and after — all `ModuleNotFoundError: No module named 'comfy_api'`
plus one source-scan assertion that needs the same import. Pre-existing and environmental
(ComfyUI is not importable on this machine), **not** caused by this change. The +37 delta
is exactly the new audit tests.

`python tools/test_perf.py --fast -- tests -m fast_unit` cannot complete on this machine:
collection alone is 13.99 s of the tool's 15 s budget (569 tests) before any test runs.
That is a pre-existing property of the budget, not of this change, so per
`AGENTS.md` the bounded per-file diagnostic form was used instead.

---

## Terminal summary

```
AUDIT_BASE_SHA=211d204b06f1246bbd2b5b591473d7d08b629030
AUDIT_BRANCH=audit/vae-residency
AUDIT_WORKTREE=.slim/worktrees/vae-residency-audit

GOLDEN_VAE_LOAD_GUARANTEE=weights fully resident on GPU (byte-exact, storage-identical to
  QD views, proven by validate_qd_adoption); DynamicVRAM NOT activated
  (hostbufs_initialized=False, active=False, no vbar, no weight functions); NOT registered
  in model_management.current_loaded_models; no residency token emitted
VAE_RESIDENT_AFTER_PRELOAD=yes   (bytes only; DynamicVRAM-unregistered)
VAE_RESIDENT_BEFORE_DECODE=yes   (unchanged; no eviction vector exists, see §11)

LOAD_MODELS_GPU_ACTUAL_TRANSFER=yes  (D2H backup + D2D recast of 108 force-loaded params;
  NOT a model H2D — all 335,278,732 model bytes moved during golden_vae_load)
LOAD_MODELS_GPU_TRANSFER_BYTES=unknown  (bounded above by 108 x 16 KiB ~ 1.7 MiB and by
  model_size 335,278,732 B; exact value needs one opt-in run of the §13 probe)

PARTIALLY_LOAD_NESTED=yes  (load_models_gpu > LoadedModel.model_load >
  LoadedModel.model_use_more_vram > partially_load > load; 1 occurrence each, all 3 traces)
PARTIALLY_LOAD_ACTUAL_TRANSFER=yes  (and it is the FIRST AND ONLY DynamicVRAM activation
  of this patcher, not a repeat of golden_vae_load)

MAX_NON_OVERLAPPING_REMOVABLE_MS=73.028   (GOOD fastest; 78.091 GOOD healthy, 110.675 BAD)
  naive-sum error avoided: 73.028 + 65.542 = 138.570 and 110.675 + 100.126 = 210.801 are
  both ~90% overstatements. Realistic removable after the REQUIRED portion: ~0.

VAE_AUDIT=REQUIRED

PROPOSED_GUARD=residency+identity token for the RELOCATION only (no bypass proposed):
  id(vae)==id(session.vae) AND id(patcher)==captured AND is_dynamic()
  AND load_device==captured, and after the call: patcher in current_loaded_models
  AND loaded_size()>0 AND all first-stage params on load_device; otherwise fall through
  to the unchanged in-decode load_models_gpu. No "no intervening eviction" clause: §11
  proves eviction is impossible, so it would be a vacuous condition.
PRODUCTION_CODE_CHANGED=no   (audit instrumentation only: default-OFF, read-only probe)
MERGED=no
```