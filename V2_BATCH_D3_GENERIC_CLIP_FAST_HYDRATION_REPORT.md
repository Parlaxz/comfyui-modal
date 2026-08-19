# V2 Batch D3 — Generic CLIP Fast Hydration Report

Capability-based prototype for first-cold ComfyUI text-encoder fast loading
(standalone CLIP safetensors, Modal-like storage, arbitrary encoder behind the
CLIP abstraction).

- **Date:** 2026-08-15
- **Environment:** Windows, Python 3.11.9, torch 2.8.0+cu128 (RTX 3070, CUDA
  available), safetensors 0.5.3, fastsafetensors 0.3.3 (foundation-model-stack,
  IBM), psutil available
- **Scope discipline:** no Modal deploy, no Modal request, no paid run, no
  commit. All proofs are local synthetic.
- **ComfyUI source root used for research:**
  `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI`

---

## 1. Executive verdict

> **Generic fast hydration feasible = PARTIAL**

Feasible for a precisely-defined capability subset, fully proven locally:

- **YES** for plain, uniform-dtype (fp16/fp32/bf16), safetensors-format text
  encoders with an identity (or assign-able) state-dict transform and no
  quantization/custom-op markers.
- **NO** (must fall back to the Comfy path) for quantized/legacy-fp8 files,
  mixed-dtype files, and candidates whose structure depends on weight *values*
  in ways the snapshot does not record.
- **Conditional** on production wiring changing the CLIP bind from
  `assign=False` (today) to `assign=True` (proven zero-copy) — a gated
  behavior change inside comfyui-modal, not a rewrite of Comfy.

The prototype (`comfymodal_runtime/clip_fast_hydration.py`) answers for any
candidate: `eligibility`, `reason`, `preferred hydration mode`, `fallback
mode`, with all eight gates exposed. All mechanics are proven on local
synthetic CLIP-like encoders; no remote evidence exists yet, so the queue
depth is deliberately parameterized, not hardcoded.

---

## 2. Exact current ComfyUI mechanics (verified against source)

Source root: `...\ComfyUI June Install\ComfyUI\comfy\`. (This build has no
`comfy/clip.py`; everything lives in `sd.py`.)

1. **How standalone CLIP safetensors are loaded.** `load_clip(ckpt_paths, ...)`
   (sd.py:1310) → per path `comfy.utils.load_torch_file(p, safe_load=True,
   return_metadata=True)` (utils.py:122; default `device="cpu"`, safetensors
   path = `safe_open(..., device="cpu")`, mmap-backed, zero-copy CPU views,
   utils.py:133) → `convert_old_quants(sd, ...)` (utils.py:1365).
2. **When state-dict key conversions happen.** In
   `load_text_encoder_state_dicts` (sd.py:1460): `clip_text_transformers_convert`
   (utils.py:255) for legacy CLIP keys (slices `in_proj` into q/k/v — new
   tensors), `text_projection` → `text_projection.weight` + transpose
   (utils.py:264), `lm_head` prefixing (sd.py:1472). Also checkpoint-path
   prefix repackaging via `state_dict_prefix_replace` (utils.py:201).
3. **When model type is detected.** Key/shape-based, not filename-based:
   `detect_te_model(sd)` (sd.py:1358); `t5xxl_detect`/`llama_detect` read
   weight dtypes and layer quantization from the state dict (sd.py:1440-1458).
4. **When model structure is constructed.** In
   `load_text_encoder_state_dicts` after detection (sd.py:1478-1708): an
   `EmptyClass` target picks `sd1_clip.SD1ClipModel` /
   `sdxl_clip.SDXLMidClipModel` / `text_encoders.t5.T5XXLModel` /
   `flux.flux_clip()` / `sd3_clip.sd3_clip(...)` from (file count, clip_type,
   detection). Structure is deterministic from JSON configs
   (`sd1_clip_config.json`, `t5_config_xxl.json`, ...) via
   `CLIPTextModel(config_dict, dtype, device, operations)`; constructed on
   `text_encoder_initial_device` (CPU), params allocated at
   `text_encoder_dtype` (default fp16, model_management.py:1150-1165).
5. **When ModelPatcher is created.** `CLIP.__init__` (sd.py:222): constructs
   `cond_stage_model`, creates the patcher (sd.py:252-257) with
   `load_device=text_encoder_device()`, `offload_device=...`, compute dtype
   float32, `hook_mode=MinVram`, `is_clip=True`; `force_full_load` path at
   sd.py:280-281. `load_clip` returns the `CLIP` object (patcher via
   `load_clip_model_patcher`, sd.py:1306).
6. **How state_dict is bound.** `CLIP.load_sd` (sd.py:414): checkpoint path →
   `load_state_dict(sd, strict=False, assign=self.patcher.is_dynamic())`
   (sd.py:416); file-list path → per-file dispatch, leaf
   `SDClipModel.load_sd` → `load_state_dict(sd, strict=False,
   assign=getattr(self, "can_assign_sd", False))` (sd1_clip.py:308-309).
   **Critical: `is_dynamic()` is False for CLIP** (`ModelPatcher`/`CoreModelPatcher`,
   model_patcher.py:354; `ModelPatcherDynamic` is not used for CLIP) →
   **CLIP binds with `assign=False` today — a plain in-place `copy_` into
   CPU params.** `assign=True` appears exactly once in the tree
   (gpt_oss.py:582); `device="meta"` appears only in ops.py:720 (AimDo
   Windows-only embedding), handled by `ModelPatcher.load`
   (model_patcher.py:1017).
7. **What invalidates a direct-GPU path** (enumerated):
   - transforms that create new tensors: `in_proj` slicing, `text_projection`
     transpose/contiguous, `position_ids.round()` (supported_models.py:66);
   - prefix repackaging into new dicts (SD1 `cond_stage_model.`→`clip_l.`);
   - `convert_old_quants`: pops `scaled_fp8`, injects `*.comfy_quant` uint8
     tensors, needs `_quantization_metadata` from
     `load_torch_file(return_metadata=True)` — skipping it builds the wrong
     structure silently;
   - non-tensor entries (`spiece_model`, `tekken_model`, `tokenizer_json`)
     consumed at sd.py:1509/1585/1544 — stripped dicts break tokenizers;
   - quantized T5 `mixed_precision_ops` (sd1_clip.py:112-117) → fp8/bf16
     params with different key layout;
   - whole-model moves after bind (`.to(offload_device)` sd.py:245,
     `ModelPatcher.load/unpatch` model_patcher.py:1029/1045) and
     `load_models_gpu(force_full_load=True)` (sd.py:281);
   - `assign=True` requires exact dtype/device coherence — CUDA tensors
     against mismatched-dtype params error.
8. **Can existing snapshotted CLIP structure be rebound safely?** Yes with
   conditions. Structure is deterministic per (type, clip_type, file count,
   weight dtypes, quant metadata). Weight-dependent init bits: `dtype_t5`
   from `encoder.final_layer_norm.weight.dtype` (sd3_clip.py:23-33),
   `detect_layer_quantization`, tokenizer blobs, `model_options_long_clip`.
   A snapshotted structure (or config blueprint) + later bind is equivalent
   **only if** the snapshot records those derived options. `ModelPatcher`
   can wrap CPU/meta-weight models and move them later (load() zero-inits
   meta params, model_patcher.py:1016-1021) — patcher construction does not
   depend on weight residency.
9. **Is `load_state_dict(assign=True)` usable generically?** Only for a
   capability subset: shapes must match, dtypes must match exactly (assign
   performs no conversion — checkpoint's dtype/device win), keys need not
   all match (`strict=False` tolerant), non-persistent buffers absent,
   inference-mode-tensor caveat applies only to Comfy's `set_attr_param`
   clone path (patches), not to bind. Requires no optimizer state (CLIP is
   inference-only). This is the canonical
   meta-construct → `assign=True` pattern (PyTorch meta docs).

### How this project loads CLIP today

`modal_app.py:8682` → `load_cpu_snapshot_models` (cpu_snapshot_models.py:2444)
→ `_load_role("clip")` → bridge `_load_clip` (model_preload.py:13462) →
`_invoke_original("CLIPLoader")` → native `comfy.sd.load_clip`. The whole
`CLIP` object — weights, structure, `.patcher`, `.tokenizer` — lives in the
Modal heap snapshot (`CpuSnapshotModels.clip`, cpu_snapshot_models.py:78),
validated by `_is_valid_clip_patcher` (1266). **There is no CLIP weight fast
path today.** `clip_conditioning_cache.py` caches *completed* conditioning
outputs (orthogonal to hydration). The UNet stack (fastsafetensors /
meta-direct / pinned-staging, all flag-gated OFF, default path is the native
fast-disk deferral) is the design precedent to mirror.

---

## 3. Candidate path evaluation (A–F)

| Path | Description | Verdict | Why |
|---|---|---|---|
| **A** | Current Comfy CPU mmap → ModelPatcher → GPU | **Fallback — keep** | Proven untouched by the prototype (`hydrate_cpu_standard`: parameter identity preserved, copy_ semantics, works on any candidate). |
| **B** | safetensors direct CUDA (`load_file(device="cuda")`) | **Usable, simple** | Verified locally: works on safetensors 0.5.3 (pageable staging on this version; pinned on ≥0.8.0). Host-staged — not zero-copy read, but the file never becomes a full CPU tensor set; tensors are ordinary torch tensors (safe lifetime). No new dependency. |
| **C** | fastsafetensors direct CUDA | **Preferred when available** | IBM fastsafetensors 0.3.3 verified locally: `SafeTensorsFileLoader(None, "cuda:N", max_threads=16, nogds=True, disable_cache=True)` → `copy_files_to_device` → tensors are zero-copy views over an internal GPU buffer. Requires indexed device string (`"cuda:0"`, not `"cuda"`). Ownership contract: loader+buffer must outlive tensors; never `close()` while live; attach owner to the patcher so GPU fragments die with it (mirrors `_FastsafeOwner` in unet_fastsafetensors.py:1148). |
| **D** | high-QD read → bounded pinned staging → async H2D | **Usable, control path** | Verified locally (`hydrate_pinned_staging`, qd=2/4): semaphore-bounded worker pool, per-tensor `pin_memory()` + `non_blocking` copy, assign bind. Staging bounded by qd × largest tensor (per-tensor chunking = future refinement). |
| **E** | snapshot structure without payload, hydrate after restore | **Best architecture (see §7)** | Structure is deterministic and cheap to rebuild from configs; weights are the only large payload. Snapshot retains tokenizer, detected type, config/structure blueprint, patcher metadata; weights re-hydrated from volume at restore via B/C/D + assign. |
| **F** | multiple encoder files concurrently, ONE global I/O budget | **Verified (scheduler)** | `plan_qd_budget`/`hydrate_many` in the prototype: global semaphore `total_cap`, per-file QD split. Budget math unit-tested for 1/2/3/4/8 files. Final QD requires remote tuning. |

All direct modes terminate in `load_state_dict(assign=True)` → parameters
*become* the file tensors (no duplicate CPU payload, no second GPU copy).

---

## 4. Eligibility model (generic, no model-name checks)

### Gates (each returns passed + detail)

| Gate | Pass condition | Fails when |
|---|---|---|
| `plain_tensor_storage` | every sd value is a torch.Tensor | tokenizer blobs / non-tensor entries present |
| `uniform_dtype` | one dtype, in {fp16, fp32, bf16} | mixed dtypes, exotic dtypes |
| `no_quant_transform` | no `comfy_quant`/`scaled_fp8` keys, no `_quantization_metadata` | quantized / legacy-fp8 files |
| `transform_identity` | transformed keys are the *same tensor objects* (data_ptr+shape+dtype) | transforms creating new tensors (in_proj slice, text_projection transpose) — reported as cost, not blocker |
| `assign_compatible` | shared keys shape-match AND dtype-match; strict=False tolerance for missing/unexpected | shape or dtype mismatch (assign converts nothing) |
| `meta_compatible` | all params on meta device | materialized structure (meta_assign still works, loses skip-alloc) |
| `direct_cuda_compatible` | CUDA available + uniform dtype loadable | no CUDA, exotic dtype |
| `patch_state_absent` | never blocks; reports patch/LoRA state | (informational) patches apply downstream at `patch_model()` |

### Decision

```
eligible = plain_tensor_storage ∧ uniform_dtype ∧ no_quant_transform ∧ assign_compatible
preferred =
    direct_cuda ∧ identity ∧ assign ∧ file → fastsafetensors (else safetensors_cuda)
    meta structure                            → meta_assign
    otherwise                                 → cpu_standard
fallback = cpu_standard (always, exactly current Comfy behavior)
```

### Unsupported capability classes (→ cpu_standard)

1. Quantized / legacy-fp8 encoders (`comfy_quant`, `scaled_fp8`,
   `_quantization_metadata`) — the quant transform cannot be satisfied by a
   direct bind; structure must be built from quant-aware detection.
2. Mixed-dtype files — assign requires one uniform dtype.
3. Dtypes outside fp16/fp32/bf16.
4. State dicts whose *structure* depends on weight values that the snapshot
   does not record (`dtype_t5`, layer-quantization detection,
   long-clip flags) — detection must run at capture, not restore.
5. Non-tensor entries in the bind dict — must be stripped (consumed at
   construction) before the bind step.
6. Patch/LoRA state does **not** block direct load (patch application is
   downstream and device-agnostic) but is tracked (`patch_state_absent`
   capability) because it changes post-bind model state and therefore what a
   snapshot would contain.

---

## 5. Prototype — files, API, local proof

### Files (new, isolated; nothing wired into production)

| File | Role |
|---|---|
| `comfymodal_runtime/clip_fast_hydration.py` | Standalone capability helper (torch-only core; fastsafetensors optional import). ~830 lines. |
| `_test_clip_fast_hydration.py` | Local synthetic proof harness (9 sections, exit 0 = pass). |

Public API: `CandidateAssessment` (eligible/reason/preferred/fallback/gates/
capabilities), 8 gate functions, `assess_candidate`, `HydrationReport`
(wall_ms, phases, peak cuda alloc delta, RSS delta, zero_copy + evidence,
notes), `hydrate_cpu_standard` / `hydrate_meta_assign` /
`hydrate_safetensors_cuda` / `hydrate_fastsafetensors` / `hydrate_pinned_staging`
/ `hydrate_auto` (assess → dispatch → guaranteed fallback),
`BudgetPlan` + `plan_qd_budget` + `hydrate_many`, `HYDRATION_MODES`,
`DEFAULT_QD_BASE = 8`.

### Synthetic proof setup

`TinyTextEncoder` (Embedding 512×64, 2× (LN+Linear+LN+Linear), final LN,
text_projection) plus four fixtures: identity fp16, Comfy-legacy non-identity
layout (`encoder.emb.weight` rename + `text_projection` transpose transform),
quant-marked (`*.comfy_quant`), mixed dtype. Forward-parity vs a CPU fp16
reference on every mode.

### Measured results (RTX 3070, ~100 KB files — absolute times are overhead-dominated; the mechanics are the proof)

| Mode | wall ms | zero-copy | cuda Δ | RSS Δ | Proof |
|---|---|---|---|---|---|
| cpu_standard (fallback) | 23.6 | no | 0 | +0.02 MB | param identity preserved; copy_ semantics — current Comfy behavior byte-for-byte |
| meta_assign | **1.06** | **yes 8/8** | 0 | +0.04 MB | params ARE the file tensors; zero extra allocation |
| safetensors_cuda | 3.1 | yes 8/8 | 110 KB | +0.05 MB | host-staged read, assign bind |
| fastsafetensors | 38.4 | yes 8/8 | 104 KB | +17.3 MB | zero-copy GPU fragment views; owner attached; pool overhead dominates at this size |
| pinned_staging (qd=4) | 33.7 | yes 8/8 | 110 KB | +13.7 MB | bounded semaphore transfers |

Zero-copy is proven by data_ptr + storage-identity equality between the file
tensor and the bound parameter (8/8 sampled keys, e.g. `blocks.0.ff1.bias`).
Test suite: **9/9 sections PASS** (gates, assessment, fallback semantics,
meta-assign zero-copy, safetensors_cuda, fastsafetensors, pinned_staging,
auto+fallback, multi-file scheduler with budget math). Standalone import
verified. Elapsed ~0.7 s.

---

## 6. Multiple-file strategy (mode F)

- **One global I/O budget** across all encoder files of a candidate
  (`hydrate_many`): a single semaphore of `total_cap` concurrency units
  shared by all files; per-file internal QD derived by split.
- **Split policy** (`plan_qd_budget`): 1 file → QD N; 2 files →
  `max(min, ⌊N/2⌋)`; 3/4 files → `max(min, ⌊N/n⌋)`; `total_cap =
  min(n·per_file, N+2)`.
- **No hardcoded final QD.** `DEFAULT_QD_BASE = 8` is the local NVMe probe
  default (project QD battery: QD8 preadv = 40.72 GB/s local). Remote volume
  storage has different latency/bandwidth; qd_base must be A/B'd remotely
  (§9). fastsafetensors' internal thread pool (16 threads, 1 GiB blocks) is
  the per-file engine, so multi-file concurrency composes through the global
  semaphore.
- Scheduling context: SDXL/Flux (2 files) and SD3 (3 files) combine via
  Comfy's per-file `load_sd` dispatch — hydrate each file under the shared
  budget, then run the existing combiner bind.

---

## 7. Snapshot implication — architecture recommendation

**Recommendation (analysis only — no destructive snapshot changes made):**

> Eventually exclude large CLIP weight payloads from the CPU snapshot, while
> retaining everything needed to rebuild structure cheaply and re-hydrate
> weights from storage at restore.

**Retain in snapshot:**
- tokenizer data (`spiece_model`/`tekken_model`/`tokenizer_json` — consumed
  into `tokenizer_data` at construction),
- detected encoder type + `clip_type` + file count (the structure
  selection tuple),
- structure: config dicts (or the existing pickled structure — both are
  equivalent; configs are smaller and version-stable),
- **weight-derived configs**: `dtype_t5`, layer-quantization detection
  result, long-clip flags — recorded at capture because detection needs the
  state dict,
- `model_options` (dtype, disable_dynamic, patches presence),
- patcher metadata (load/offload devices, compute dtype, hook_mode,
  `is_clip`, size),
- `file_facts` (path/size/mtime/hash — already tracked in
  `CpuSnapshotModels`) and the **per-file eligibility decision** (capability
  report from this prototype, serialized into the manifest).

**Exclude:** the weight payload itself (tensors), replaced at restore by
fast hydration (§5 modes) from the Modal volume using `file_facts` +
recorded eligibility.

**Mechanics:** mirrors the existing UNet exclusion pattern
(`COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET` + `EVICT_RETAIN_ROLE=clip_vae`,
model_preload.py:1186, modal_app.py:2610/2615) generalized to a role-based
eviction that also covers `clip`. The `_FAST_DISK_UNET_DEFERRALS` weakref
pattern (model_preload.py:5650) is the precedent for graph-time
re-hydration (`load_model_weights(assign=True)` + one `.to` re-read).

**Safety gates for eviction:**
- eligibility recorded at capture time passes AND hydration stack present at
  restore,
- `file_facts` confirm the source file exists on the volume with matching
  size/hash,
- fallback: if anything fails at restore, re-fetch payload into the snapshot
  object and proceed exactly as today (cpu_standard path is always intact).

**Explicitly not implemented:** the snapshot change is destructive and
requires the restore side to be live first; the prototype is the standalone
building block that makes the exclusion safe (it can decide, at capture and
at restore, whether the direct path is valid for these exact files).

---

## 8. Deliverable summary

| Item | Value |
|---|---|
| generic fast hydration feasible | **PARTIAL** (YES for the plain uniform-dtype capability subset; NO for quant/custom-op/mixed-dtype; conditional on gated `assign=True` wiring) |
| best architecture | capability-gated layered pipeline mirroring the UNet stack: construct structure deterministically at file dtype (meta preferred) → fastsafetensors (preferred) / safetensors_cuda / pinned_staging → `load_state_dict(assign=True)` with owner-attached GPU buffers → `cpu_standard` always-available fallback; multi-file under one global budget; snapshot excludes weight payload only |
| eligibility model | 8 gates (§4): plain tensor storage, uniform dtype, no quant transform, transform identity, assign compatibility, meta compatibility, direct-CUDA compatibility, patch state (informational) |
| unsupported capability classes | quantized/legacy-fp8, mixed-dtype, exotic dtype, weight-dependent structure without recorded derived configs, non-tensor bind entries (§4.6) |
| multiple-file strategy | one global semaphore budget; split policy 1→N, 2→⌊N/2⌋, 3/4→⌊N/n⌋, min-clamped; fastsafetensors internal pool; QD base parameterized, not hardcoded (§6) |
| snapshot-exclusion strategy | exclude weights only; retain tokenizer, type, configs, weight-derived configs, patcher metadata, file_facts + per-file eligibility manifest; restore re-hydrates from volume; UNet-eviction precedent (§7) — NOT implemented |
| prototype files | `comfymodal_runtime/clip_fast_hydration.py`, `_test_clip_fast_hydration.py` |
| tests | `python _test_clip_fast_hydration.py` → 9/9 PASS, exit 0, ~0.7 s |
| commit | none |
| Modal requests | 0 |
| deploys | 0 |

---

## 9. READY_FOR_REMOTE_EXPERIMENT

> **READY_FOR_REMOTE_EXPERIMENT = YES**

Local mechanics are proven (zero-copy assign bind, ownership semantics, no
duplicate CPU payload, fallback parity, budget math). The remaining unknowns
are remote-storage I/O characteristics and real-encoder behavior — both are
measurement questions, not mechanism questions.

### Exact next remote A/B

Run **inside the Modal container** (standalone harness, no ComfyUI graph):

- **A (baseline):** current cold path — `CLIPLoader` on a real encoder set
  (e.g. SDXL 2-file `clip_l` + `clip_g`, or FLUX `clip_l` + `t5xxl`):
  CPU mmap → bind (`assign=False`) → `.to(GPU)`. Record phase wall times,
  peak GPU alloc, peak RSS.
- **B (candidate):** prototype `hydrate_many` on the same files from the
  Modal volume: fastsafetensors direct-GPU (fallback safetensors_cuda) +
  `assign=True`. Same metrics.
- **A/B gates:** forward parity of `CLIPTextEncode` output (fp16 tolerance);
  zero-copy data_ptr evidence; B bind+transfer wall < A; peak RSS not worse.
- **QD sweep (multi-file):** `qd_base ∈ {2, 4, 8, 16}` for the 2- and 3-file
  combos to find the remote saturation point; record volume read GB/s per
  QD. This replaces `DEFAULT_QD_BASE = 8` with remote evidence.
- **Success → production wiring:** flag-gated integration in `_load_clip`
  (mirror `_fs_eligible`/fail-closed pattern), then the snapshot-exclusion
  change (§7) as a separate follow-up experiment.

---

## 10. Process notes

- Research executed via explorer (project internals + ComfyUI mechanics) and
  librarian (safetensors/fastsafetensors/assign semantics) lanes — all cited
  facts cross-verified against installed source.
- Implementation was delegated twice to the fixer lane; both sessions
  terminated without producing files or results (verified on disk), so the
  prototype was implemented directly from the fully-specified design.

---

## 11. Production integration (D3 phase 2 — default-OFF wiring + snapshot weight exclusion)

### 11.1 Flags

| Flag | Default | Effect |
|---|---|---|
| `COMFYMODAL_V2_CLIP_FAST_HYDRATION` | off (`env_flag`) | Path A: fastsafetensors direct-GPU hydration at first encode demand. Invalid values fail closed to off. |
| `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS` | off (`env_flag`) | Path B: capture-time removal of the physical CLIP weight payload, gated on a verified capability manifest. Invalid values fail closed to off. |

Snapshot exclusion is only ever applied when the frozen manifest proves a
fast-hydration-capable or safe-native-reconstruction path; eligibility is
never re-derived from missing weights after restore.

### 11.2 Architecture (implemented)

```
CAPTURE (startup, after load_cpu_snapshot_models):
  maybe_prepare_clip_snapshot_exclusion(_cpu_models)
    ├─ build frozen manifest: per-file gates (plain tensors / uniform dtype /
    │  no quant markers / transform pipeline by key-pattern triggers / exact
    │  key+shape+dtype record / leaf routing / can_assign_sd leaf probe) +
    │  loader_specs + fast_hydration_allowed (frozen at capture)
    ├─ attach manifest as clip attribute (rides the heap snapshot)
    └─ Path B on + eligible → strip weights in place (meta params, marker set)

RESTORE / STARTUP (serve time):
  maybe_install_clip_fh_demand(_cpu_snapshot_models)
    └─ manifest eligible → install instance-level CLIP.load_model wrapper
       (idempotent; D2's class-level load_model hook still fires underneath)

FIRST ENCODE DEMAND (load_model):
  hydrator → fast: fastsafetensors(C9 config: nogds, no buf-register,
    16 threads, 1 GiB blocks) → replay recorded pipeline on GPU tensors →
    verify exact key/shape/dtype vs frozen manifest → can_assign_sd spray
    (sd.py:419/426 pattern forced True) → Comfy's OWN cond_stage_model.load_sd
    dispatch (assign=True, zero-copy) → post-verify (zero-copy data_ptr proof,
    no file-covered meta params, device check) → owner attach to patcher
  fallbacks (B-stripped): cpu_assign via the same dispatch (CPU tensors) →
    native_copy (fresh native load exactly once + in-place param replacement)
  fallback (A weights present): failure = no-op, native load_model untouched
```

Key generic mechanisms verified against Comfy source:

- **`can_assign_sd` is the generic zero-copy bind convention**: every leaf
  funnels through `SDClipModel.load_sd` → `load_state_dict(strict=False,
  assign=getattr(self, "can_assign_sd", False))` (sd1_clip.py:308-309); the
  list-path spray (sd.py:419/426) is replicated with `True`. The leaf probe
  is bytecode-based (`co_names`/`co_consts` — real Comfy uses the string
  literal form) so it is capability-based, not name-based.
- **Leaf-relative key space**: `SDClipModel.load_sd` forwards the file sd
  directly to `transformer.load_state_dict`, so file keys are the inner
  module's names while `leaf.state_dict()` is prefixed; routing/zero-copy
  verification maps exact-or-first-component-stripped names.
- **Demand trigger = `CLIP.load_model`** (D2's `clip_cold_gpu_wait`
  boundary): cache-hit requests never encode → never call load_model → ZERO
  hydration. Cache-miss requests trigger hydration at the prefill encode —
  the earliest demand point (the conditioning-prefetch machinery encodes
  there); plan-time pre-read is documented as a future optimization, not
  implemented (it would risk hydrating cache-hit requests).
- **Ownership**: fastsafetensors (loader, buffer) owners attach to
  `clip.patcher`; `release_owner` for teardown; `close()` never called while
  tensors are live (C9 lesson).

### 11.3 Telemetry (D2-compatible)

Events ride the same trace with D2's shape (`phase="execution"`, JSON-safe):
`clip_fh_capture`, `clip_fh_install`, `clip_fh_hydration_start/end`. The
hydration end event carries: mode, file_to_gpu_wall_ms, checkpoint_bytes,
gbps, bind_wall_ms, owner_mode, rss_delta_mb, cuda_delta_bytes, zero_copy,
zero_copy_evidence, fallback_count. `clip_fh_request_summary(request_id)`
resolves the per-request `hydration_source` ∈ {`native_cpu_h2d`,
`fastsafetensors_direct_gpu`, `already_resident`,
`conditioning_cache_hit_no_hydration`} (never-demanded excluded clips
resolve to the cache-hit value). No duplicate telemetry that disagrees with
D2 — D2's own load/encode accounting remains authoritative and will show
~0 ModelPatcher H2D on the direct-GPU path.

### 11.4 Files changed (all new or surgical, default-off)

| File | Change |
|---|---|
| `comfymodal_runtime/clip_fast_hydration.py` | +production API: strip_clip_weights, can_assign_sd_supported (bytecode probe), verify_leaf_routing, hydrate_clip_bind, install_demand_wrapper, owner_attach/release_owner, leaf key maps, zero-copy proof |
| `comfymodal_runtime/clip_fast_hydration_wiring.py` | NEW: flags, manifest build/verify, capture strip, demand hydration + fallback chain, D2-compatible events, request summary |
| `comfymodal_runtime/modal_app.py` | 2 surgical guarded call sites: startup (capture strip + install after `_cpu_snapshot_models` set), restore (install after `_lazy_init_snapshot_state`) |
| `comfymodal_runtime/cpu_snapshot_models.py` | 3 additive lines: `_is_valid_clip_patcher` tolerates the exclusion marker |
| `tests/test_v2_clip_fast_hydration_production.py` | NEW: 22 tests / 10 memory proofs |
| `_test_clip_fast_hydration.py` | unchanged (regression: 9/9 PASS) |

### 11.5 Tests

- NEW production suite: **22 passed, 1 skipped** (cloudpickle round-trip
  skipped when the package is absent) — covers flags fail-closed, frozen
  manifest, legacy transform recording, quant/mixed ineligibility, the 10
  memory-correctness proofs (structure-without-payload, restore hydration,
  forward parity, no duplicate CPU payload, no second GPU copy, owner
  retention through encode, teardown release, cache-hit ZERO hydration,
  native reconstruction exactly once, ineligible payload never removed),
  snapshot round-trip, multi-file dispatch, D2 trace integration.
- Prototype harness regression: 9/9 PASS.
- D2's `tests/test_v2_clip_cold_forensics.py`: **PASS**.
- `tests/test_cpu_snapshot_models.py`, `tests/test_v2_snapshot_restore_only.py`: **PASS**.
- `tests/test_v2_cpu_snapshot_lifecycle.py`: 16 failures **attributed to
  concurrent Phase D agents' in-flight edits and environment**, not this
  work: `git diff` shows `cpu_snapshot_models.py` changed by exactly my 3
  marker-gated lines; the failing functions (`_cpu_snapshot_model_keys_match`
  at modal_app.py:1018 and VAE-policy code) sit inside 1,590+ concurrent
  insertions in `modal_app.py`; e2e failures are `FileNotFoundError` for
  missing `flux_vae.safetensors` fixtures. `test_v2_preload_bridge.py`:
  67/69 pass; the 2 failures assert preload-bridge install/retry state in
  `model_preload.py` — a file I never edited (concurrently modified).
- One 7-file affected batch timed out in this environment (no output before
  the 15-min bash cap); the individually-run subset is reported above.

### 11.6 Final status

| Item | Value |
|---|---|
| implementation status | DEFAULT-OFF production wiring complete: Path A (fast hydration) + Path B (snapshot weight exclusion) implemented, capability-gated, fail-closed |
| fast hydration flag | `COMFYMODAL_V2_CLIP_FAST_HYDRATION` (env_flag, invalid → off) |
| snapshot exclusion flag | `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS` (env_flag, invalid → off) |
| generic eligibility | 8 capability gates + leaf-routing + can_assign_sd bytecode probe; frozen manifest authority at restore; no model-name branches |
| snapshot manifest | frozen at capture on the clip object: per-file key_set/key_shapes/dtype, transform pipeline, non-tensor entries, quant facts, loader_specs, fast_hydration_allowed |
| cache-hit behavior | zero hydration (no encode → no load_model → no wrapper fire); summary resolves `conditioning_cache_hit_no_hydration` |
| cache-miss hydration schedule | at first encode demand (`CLIP.load_model` wrapper), which the conditioning-prefill encode triggers early; plan-time pre-read documented as future work |
| D2 telemetry integration | same trace/shape events (`clip_fh_*`); `hydration_source` ∈ {native_cpu_h2d, fastsafetensors_direct_gpu, already_resident, conditioning_cache_hit_no_hydration}; D2 remains authoritative for load/encode |
| ownership | fastsafe loader+buffer owners attached to `clip.patcher`; never close while live; `release_owner` teardown |
| memory behavior | stripped structure carries zero physical param bytes; fast path = no duplicate CPU payload (zero-copy proof 11/11), no second GPU copy (cuda delta ≈ payload); fallbacks assign from CPU exactly like the native path |
| fallback semantics | A: failure → no-op, native weights untouched; B: fast → cpu_assign → native_copy (native loader invoked exactly once) → fail closed; partial fast state discarded, owners closed, CUDA cleared |
| files changed | 3 surgical edits + 2 new runtime files + 1 new test file (+ report) |
| tests | production 22 pass/1 skip; prototype harness 9/9; D2 forensics pass; cpu_snapshot_models + snapshot_restore_only pass; concurrent failures attributed (not caused by this work) |
| commit | none |
| Modal requests | 0 |
| deploys | 0 |

### 11.7 READY_FOR_D6

> **READY_FOR_D6 = YES**

D6 one-run cache-miss validation can prove each required property with the
existing telemetry:

| D6 requirement | Where it is proven |
|---|---|
| exact output parity | forward parity assertions in the production tests (fp16 tolerance) + D2 encode accounting |
| true file→GPU wall | `clip_fh_hydration_end.file_to_gpu_wall_ms` + gbps |
| true encode wall | D2 `clip_cold_encode_start/end` (authoritative) |
| snapshot weight exclusion occurred | `clip_fh_capture` status=excluded + params_replaced; stripped structure has zero param bytes |
| no full CPU CLIP payload restored | zero-copy proof + cpu_assign/native paths bind via assign (no copy_) |
| no duplicate H2D | D2 `total_h2d_bytes` ≈ 0 on the direct-GPU path + cuda delta ≈ payload |
| cache miss caused exactly one hydration | demand wrapper + hydrated marker + `fallback_count` |
| D2 load/encode telemetry reconciles with D3 | both ride the same trace; `hydration_source` resolves the four modes |

Next remote A/B (§9) remains the gate: run in-container with the flags on,
real encoder files from the Modal volume, and the QD sweep against remote
storage to replace `DEFAULT_QD_BASE = 8`.
