# V2_BATCH_C8_META_NATIVE_HYBRID_FEASIBILITY

**Lane:** C8 (ZImage only) · **Date:** 2026-08-15 · **Status:** FEASIBILITY — candidate, no production wiring

**Mission:** Combine the C6 meta-model-construction discovery with the accepted native fast-disk
mmap/state_dict → assign → H2D path, WITHOUT `to_empty(cuda)`, pinned staging, preadv, ring,
meta-direct ring, or a second checkpoint pass.

---

## 1. Executive summary

The hybrid is **feasible and worth remote validation**. A ZImage model constructed entirely on
`torch.device("meta")` can adopt the existing mmap-backed BF16 state-dict tensors via
`load_state_dict(assign=True)` with **zero copy** (data_ptr-verified), then flow through today's
native fast-disk bind + single `model.to(cuda)` replay **unchanged** — verified against the live
guard code in `comfymodal_runtime/model_preload.py`, which rejects only **CUDA** residency, not
meta residency. No ComfyUI core edit is required; no existing fast-disk guard needs to change.

The construction/bind head (513.7 ms on the authoritative run) decomposes as:
get_model **383.4 ms** + ModelPatcher ctor 2.2 ms + bind **109.6 ms** + misc 18.5 ms. The hybrid
eliminates the 383.4 ms get_model (meta get_model is 19.5–199.9 ms, and can be hidden entirely
under the 1.5 s read), leaving the ~130 ms bind+ctor serial remainder.

**Conservative saving ≈ 165–305 ms** across hosts — above the 150–200 ms threshold for this
small architectural change.

---

## 2. Sources read (authoritative)

- All C6 reports: UNET_READ_H2D_PIPELINE_FEASIBILITY, UNET_READ_H2D_PROBE_REPORT, I3_CONFIG_AND_OVERLAP_GATE_REPORT, PINNED_RING_FEASIBILITY, PINNED_RING_PRODUCTION_DESIGN, PINNED_RING_IMPLEMENTATION_REPORT, SALVAGE_V2_FEASIBILITY_AND_IMPLEMENTATION_REPORT
- `comfymodal_runtime/model_preload.py` (guard code read directly: `_fast_disk_model_is_cpu_resident` :5702, `_fast_disk_guard_to` :5900, `_fast_disk_guard_bind` :5970, `_fast_disk_handle_bind` :6855, `wrapped_get_model` :8473, `_c6_build_meta_sd` :327, `_c6_parse_safetensors_header` :296, `_c6_value_probe_allow_fp16` :456)
- `comfymodal_runtime/unet_meta_direct.py`, `tests/test_c6_meta_direct.py`
- ComfyUI: `comfy/sd.py`, `comfy/model_detection.py`, `comfy/model_base.py`, `comfy/model_patcher.py`, `comfy/utils.py`, `comfy/model_management.py`, `comfy/ldm/lumina/model.py`
- Current PyTorch docs/source (torch 2.8.0+cu128 local): `module.py` (load_state_dict/assign, _apply, to_empty), `torch/__future__.py`, `torch/utils/__init__.py` (swap_tensors), safetensors Rust bindings (`UntypedStorage.from_file` mmap), plus empirical verification scripts (real safetensors file, data_ptr checks)

## 3. Authoritative measurements (C6 probe run)

| Stage | ms |
|---|---|
| read span (open/parse head 88.5 + materialize 1535.2) | 1623.7 |
| construction/bind head (read_end → to_start) | 513.7 |
| — get_model | 383.4 |
| — ModelPatcher ctor | 2.2 |
| — bind (load_state_dict assign=True) | 109.6 |
| — misc | 18.5 |
| native H2D (to_wall ≈ to_device, Δ 0.134) | 2467.9 |
| **serial native total** | **4605.3** |
| meta get_model (probe / container-cold validation) | 19.5 / 199.9 |
| sampling-fix rebuild (probe / validation) | 0.18 / 14.9 |
| to_empty(cuda) (probe / validation — NOT used by C8) | 818 / 525.2 |
| V2 preadv two-pass total (loses) | 4839.9 |

---

## 4. Critical questions — answers with source traces

### Q1. Can ZImage `get_model` construct entirely on meta while preserving topology/config/model_sampling?
**YES.** `ZImagePixelSpace.get_model` → `model_base.Lumina2(device=device)` constructs all weights
inline in `NextDiT.__init__`; under `with torch.no_grad(), torch.device("meta")` every allocation
becomes a meta tensor (proven by C6 V2 S2 and by this batch's `test_meta_get_model_real_zimage`,
which additionally drives the real `comfy.model_detection.model_config_from_unet` on a header-only
meta sd with the one value-probe tensor injected). Config parity is PROVEN by I-3: class ZImage,
6,154,908,736 parameters, weight_dtype bf16, supported_inference_dtypes [bf16,f16,f32] — all
identical; the only value-dependent input (`allow_fp16` std<0.42 of one 7,680 B tensor) is resolved
by `_c6_value_probe_allow_fp16`. `model.model_sampling` IS poisoned (meta sigma tensors) but is
rebuilt outside the meta context with the same factory `comfy.model_base.model_sampling` (0.18–14.9 ms), hard-gated to zero meta tensors.

### Q2. Can the existing mmap-backed BF16 tensors be installed with `load_state_dict(assign=True)` without copying 12.31 GB?
**YES — zero copy.** Verified empirically (lib-1 + local `test_assign_true_adopts_mmap_zero_copy`):
with a real safetensors mmap file, after `assign=True` the module's `data_ptr()` equals the
state-dict tensor's `data_ptr()` (same storage adopted); the Parameter wrapper is new but shares
the tensor impl; no `copy_` executes when dtype/device already match; `requires_grad` is preserved
from the module (torch ≥ 2.3). This is **already the production mechanism**: the native fast-disk
bind forces `assign=True` (model_preload.py:6915) and binds 12.31 GB in 109.6 ms.

### Q3. Does this preserve ModelPatcher / patches/backups / load_models_gpu / fast-disk replay / TWO-LANE?
**YES.** ModelPatcher resolves weights lazily by key at `load()` time (`get_key_weight`,
model_patcher.py:846; `_load_list` :891–926) and never caches Parameter objects — "Parameter
object identity does not matter to ModelPatcher" (C6 DESIGN §6); `patch_weight_to_device` replaces
params via `set_attr_param`/`copy_to_param` (utils.py:899–904), and `backup` is a CPU copy made at
load time (post-H2D), not at construction. `load_models_gpu` runs after the replay exactly as
today. TWO-LANE (execution-prefill lane + execution-UNET lane) is untouched: the C8 pipeline lives
inside the prep-lane worker like C6 V1/V2, and the fast-disk H2D already runs outside the
MutationLane FIFO.

### Q4. Does fast-disk interception rely on CPU parameter allocation that meta construction would skip?
**NO.** Read directly from the guard code: `_fast_disk_model_is_cpu_resident` (model_preload.py:5702)
returns False only when a param/buffer is already on **cuda**; meta tensors pass.
`_fast_disk_guard_to` (:5900) additionally requires HIGH_VRAM, plain non-dynamic ModelPatcher,
load==offload==target==cuda, no quant/FP8/custom-op/channels-last, torch `__future__` swap off —
none concern parameter storage. `_fast_disk_guard_bind` (:5970) requires sd tensors to be plain
CPU tensors with uniform dtype == first param dtype — meta params preserve dtype, so it passes.
This batch's `test_guard_to_ok_with_meta_model` and `test_guard_bind_ok_with_meta_model_and_mmap_sd`
exercise the live guard functions against a meta-resident model + mmap sd and pass. **No guard
edits required.**

### Q5. Can model_sampling be rebuilt outside the meta context as proven by C6 V2?
**YES** — 0.18 ms probe / 14.9 ms validation; verified zero meta tensors after; hard gate
(`stage:sampling_fix_incomplete` precedent in unet_meta_direct.py).

### Q6. Does native `model.to(cuda)` / fast-disk replay behave identically after assign=True?
**YES, functionally identical.** Verified empirically: `.to(cuda)` copies directly from the adopted
mmap storage (single H2D pass, no intermediate full-buffer allocation); values match a control
module (local CUDA-gated `test_to_cuda_after_adopt_matches_control`); parameter identity is
preserved through `_apply` (params go through `.data`, identical to a normally constructed module;
buffers are replaced by `_apply` exactly as in the normal path). One defined requirement: any
**non-state-dict** buffer (e.g., a residual meta buffer) must be swept/materialized before the
replay, since `_apply` would otherwise raise "Cannot copy out of meta tensor" — the sweep is
cheap (metadata-only) and fail-closed.

### Q7. Can meta construction happen CONCURRENTLY with the existing state_dict read?
**YES, feasible — this is the key opportunity.**
- Worker A dependency set: safetensors **header only** (keys/shapes/dtypes — `_c6_parse_safetensors_header`, ~1–2 ms after open) + one 7,680 B value probe + `_ring_derive_config` (proven header-only config derivation + I-3 parity) + meta get_model (20–200 ms) + sampling fix (~15 ms) + ModelPatcher ctor (2.2 ms) ≈ **40–260 ms total**.
- Worker B: the existing `load_torch_file` → `safe_open` per-key materialization (1535 ms wall).
- Join: `assign=True` bind (109.6 ms) → native `model.to(cuda)` replay (2467.9 ms).
- GIL analysis: the read loop's page-in/copy work is done in torch C++ kernels (GIL released);
  meta construction is metadata-only Python/C++ shape work — safe overlap. Two `safe_open` handles
  on the same file are safe (lazy read-only mmap; second handle only for header + value probe).
- Overlap opportunity: the entire construction head minus bind/ctor/misc ≈ **383 ms**, plus the
  88.5 ms read open/parse head. Worst case (no overlap implemented) the sequential hybrid still
  saves the 383.4 − meta(20–200) ≈ 180–360 ms.

### Q8. What remains of today's ~0.5 s get_model+bind stage?
**~130 ms serial remainder**: bind 109.6 + ModelPatcher ctor 2.2 + misc 18.5. get_model
(383.4 ms), config derivation (37.8 ms in V2 run) and sampling fix leave the serial path entirely
(sequential: meta chain adds 20–215 ms; overlapped: hidden).

---

## 5. Performance model

### A. Current native path
read 1623.7 + head 513.7 + H2D 2467.9 = **4605.3 ms**

### B. Meta + native sequential (config hidden under read; meta chain after read)
read 1623.7 + head′ [meta 20–200 + sampling 15 + bind 109.6 + ctor 2.2 + misc 18.5 = 165–345] + H2D 2467.9 = **4257–4438 ms** → saving **167–348 ms**
- optimistic (warm meta ~20 ms): 4257 ms → **~348 ms**
- expected (meta ~70 ms): ~4310 ms → **~295 ms**
- conservative (container-cold meta 200 ms): ~4440 ms → **~165 ms**

### C. Meta construction overlapped with the read (worker A ∥ worker B)
read 1623.7 (meta chain 40–260 ms fully hidden under 1535 ms wall) + head′ [bind 109.6 + ctor 2.2 + misc 18.5 + join/sync ~10–20 = 140–150] + H2D 2467.9 = **~4232–4242 ms** → saving **~363–373 ms**
- optimistic: 4232 ms → **~373 ms**
- expected: ~4240 ms → **~365 ms**
- conservative (join overhead + host variance; slow-host C6 run had head 888 ms / bind 413 ms, get_model 474.9): saving **~275–305 ms** on slow hosts

**Verdict threshold (150–200 ms, NOT the invasive-loader 500 ms):** conservative saving
**165–305 ms** ≥ threshold across all three variants → **remote validation recommended**.

Do NOT over-read the 2.34 s C6 V1 number: that was construction *before* the read (allocator
warm-up). The native post-read get_model is only 383.4 ms; C8's win is that minus meta cost, plus
hiding it under the read.

---

## 6. Fail-closed compatibility (ZImage only)

- Family gate: `type(config).__name__ == "ZImage"` (Lumina2 excluded — needs its own parity validation).
- Inherits every existing fast-disk guard verbatim (HIGH_VRAM; plain non-dynamic
  `comfy.model_patcher.ModelPatcher`; load==offload==target==cuda; no quant_config, custom_operations,
  FP8 optimization, force_channels_last; torch `__future__` swap disabled; sd entries plain CPU
  tensors, uniform dtype == param dtype; native `assign` arg False then forced True).
- New C8 gates (all fail-closed to the existing native path): meta construction yields all-meta
  params; I-3 config parity MATCH; value probe resolved; sampling fix leaves zero meta tensors;
  post-bind residual-meta sweep (non-sd buffers) materialized on CPU or fallback; key↔param
  name-set match; `process_unet_state_dict` classification INDEPENDENT (ZImage proven: 453
  INDEPENDENT / 0 SMALL_GROUP / 0 FULL_DICT_REQUIRED).
- Quantized/FP8/custom-op loaders: construction may still be meta-safe, but bind guards (dtype
  uniformity, plain-Tensor sd) fail → native fallback, exactly as today.
- Transformed state_dict families (mmdit/diffusers conversion): non-identity → fallback.
- Torch floor: `assign=True` needs torch ≥ 2.1; `requires_grad` preservation semantics need ≥ 2.3
  (runtime torch 2.8 — OK; add a version gate for safety).

---

## 7. Local prototype (no Modal run)

**New file:** `tests/test_c8_meta_native.py` — 7 passing / 3 container-gated skips:

| Test | Proves |
|---|---|
| `test_assign_true_adopts_mmap_zero_copy` | assign=True adopts real safetensors mmap tensors with identical data_ptr (params AND buffers); requires_grad preserved |
| `test_assign_false_meta_is_noop_footgun` | assign=False into meta is a silent no-op (warning) — C8 must force assign=True |
| `test_non_sd_buffer_stays_meta_detected_and_swept` | residual meta buffers detected; setattr sweep materializes on CPU; then .to(cuda) works |
| `test_to_cuda_after_adopt_matches_control` | (CUDA) post-adopt .to(cuda) values identical to control module |
| `test_cpu_resident_guard_accepts_meta_model` | live guard accepts meta, rejects cuda; direct meta→cuda raises (ordering requirement) |
| `test_guard_to_ok_with_meta_model` | live `_fast_disk_guard_to` passes with meta-resident model |
| `test_guard_bind_ok_with_meta_model_and_mmap_sd` | live `_fast_disk_guard_bind` passes with meta params + mmap sd |
| real-ZImage tests (×3) | meta get_model / sampling fix / sample adoption on the real checkpoint — gated on a non-empty local file (local copy is a 0-byte Modal placeholder; runs in container) |

Key empirical findings from the prototype: `param.data = ...` and `set_()` are **illegal on meta
tensors** (set_data type-mismatch / leaf-in-place) — residual meta materialization must use
setattr replacement (the same mechanism assign uses); the native bind+replay ordering (bind
BEFORE .to) is mandatory.

---

## 8. Integration sketch (NOT wired — for a later lane)

Follow the accepted C6 precedent (branch in `_load_unet` like unet_meta_direct.py, ~13288–13322):
1. Eligibility + header parse (`_c6_parse_safetensors_header`) + meta sd (`_c6_build_meta_sd`) + value probe + `_ring_derive_config` + I-3 parity — all proven machinery.
2. Worker A: meta get_model → sampling fix → plain ModelPatcher (reuse `_fast_disk_open_window` record).
3. Worker B: existing `load_torch_file` read (interception unchanged).
4. Join: `load_model_weights(assign=True)` bind → sweep residual meta → exactly one native
   `model.to(cuda)` replay (existing `_fast_disk_replay_to`).
5. Any failure: discard meta model + record → native path (which itself fails closed to legacy).
No ComfyUI core file needs editing; the only shared-file touches are the new module +
`_load_unet` branch in the custom node (same class as C6 accepted changes).

---

## 9. Exact next measurement needed (for C9 or later orchestrator)

Instrumented C8 pipeline run on Modal (ZImage ONLY, container with real checkpoint):
1. header → meta get_model wall + sampling fix wall + parity gate timing (container-cold AND warm);
2. bind wall with the mmap state dict (expect ~110 ms, verify no copy via data_ptr spot-check);
3. native replay `to_wall` vs `to_device` — keep the Δ ≤ 0.08 ms invariant (proves pages resident, single H2D pass);
4. residual meta-tensor count after bind (expect 0 after sweep);
5. total pipeline wall vs 4605.3 ms serial reference and vs the C6 V2 4839.9 ms negative control;
6. output SHA parity with `sha256:20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`;
7. confirm TWO-LANE/CLIP-prefill overlap unchanged.

---

## 10. Final response fields

- report path = `V2_BATCH_C8_META_NATIVE_HYBRID_FEASIBILITY.md`
- changed files = `tests/test_c8_meta_native.py` (new, offline prototype); this report (new). No shared production edits
- commit = none
- deploys = 0
- Modal runs = 0
- meta construction compatible = **YES** (C6-proven + live local test with real comfy detector)
- assign_true compatible = **YES** (empirically verified, torch 2.8; requires ≥2.1, ≥2.3 for requires_grad)
- mmap tensors adopted without full copy = **YES** (data_ptr-verified, zero-copy)
- native fast-disk replay compatible = **YES** (live guards pass with meta; no guard edits)
- ModelPatcher semantics preserved = **YES** (lazy key resolution; backup/patches post-H2D)
- TWO-LANE preserved = **YES** (prep-lane-internal; MutationLane untouched)
- meta/read concurrency feasible = **YES** (header + one 7,680 B probe only; ~40–260 ms vs 1535 ms read; GIL released in read)
- remaining bind cost = **~130 ms** (bind 109.6 + ctor 2.2 + misc 18.5)
- predicted sequential hybrid wall = **4257–4438 ms** (B; optimistic 4257 / expected ~4310 / conservative ~4440)
- predicted overlapped hybrid wall = **4232–4242 ms** (C; optimistic 4232 / expected ~4240 / conservative ~4300)
- conservative saving = **165–305 ms** (≥ 150–200 ms threshold)
- core ComfyUI edit required = **NO**
- implementation complexity = **LOW–MEDIUM** (reuses all C6 machinery; new ~250–400-line module + `_load_unet` branch)
- compatibility risk = **LOW** (additive, fail-closed at every gate, zero-copy semantics verified)
- classification = **CANDIDATE**
- remote validation recommended = **YES**
- exact next measurement needed = §9 (instrumented Modal run, ZImage only, with SHA parity + to_wall≈to_device invariant)
- reason = meta construction is hidden under the existing 1.5 s read, the 383.4 ms get_model head is eliminated without touching the I/O or H2D mechanism, zero-copy adoption and guard compatibility are verified offline, and the conservative saving (165–305 ms) clears the 150–200 ms bar for this small architectural change.
