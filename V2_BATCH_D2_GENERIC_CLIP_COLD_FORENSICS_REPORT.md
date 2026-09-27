# V2 Batch D2 — Generic CLIP Cold-Path Forensics (Load, H2D, Encode)

Date: 2026-08-15 · Branch: current main (no branch, no worktree) · Commit: **none**
Modal requests: **0** · Deploys: **0** · Paid runs: **0**

## Problem this closes

Current fast benchmark runs take conditioning-cache exact hits, so
`clip_encode_calls = 0` and the true cold cache-miss text-encoder critical
path is unmeasured. This batch adds generic (model-family-independent)
telemetry that decomposes the cold path into **(A) becoming GPU-ready** and
**(B) actual text encoding**, so that a single intentional cache-MISS run is
sufficient to answer: how long did CLIP GPU activation take, how many bytes
moved, where the time went, how long was actual encode, was the encoder
loaded more than once, and what stayed resident until the last encode.

Constraints honored: no Qwen/ZImage/T5/CLIP-L-specific logic, no
model-name branches; capability-based behavior only; JSON-safe events;
zero overhead when disabled; tests use synthetic torch modules / mocked
ModelPatcher paths only.

---

## 1. Generic call chain (verified against current parent ComfyUI, v0.24.0, commit f49bdb6)

```
CLIPLoader / DualCLIPLoader (nodes.py:968 / 995)
 └─ comfy.sd.load_clip (sd.py:1310)
     └─ load_text_encoder_state_dicts (sd.py:1460)          # family dispatch, then:
         └─ CLIP(...) (sd.py:1715)                          # generic CLIP abstraction
             CLIP.__init__ (sd.py:221)
               • cond_stage_model = clip(params)            # model instance
               • ModelPatcher (or CoreModelPatcher) (sd.py:253)
               • set_model_compute_dtype(torch.float32)     # generic capability
               • hook_mode = MinVram; patcher.is_clip = True
               • EAGER load_models_gpu at init iff initial_device == load_device (sd.py:281)
               • patcher.cached_patcher_init = (factory, (ckpt_paths, ...)) (sd.py:1318)
                 → re-creatable from CPU snapshot (capability)
CLIP.load_model (sd.py:444)                                  # GPU-ready wait boundary
 └─ model_management.load_models_gpu([patcher], memory_required) (model_management.py:843)
     • dedup; current_loaded_models cache-hit short-circuit (872–879)  → no transfer loop
     • free_memory eviction of other models (903–908)
     • LoadedModel.model_load (718–734)
         └─ ModelPatcher.load (model_patcher.py:928) / partially_load (1202)
             • _load_list (891) → load_completely / offloaded split
             • per-param: patch_weight_to_device(key, device_to) (845 / 1021)
             • torch.cuda.synchronize() per module (1023)
             • module .to(device_to) (1029) / full-load model.to (1045)
             • state: model.device, model_loaded_weight_memory,
               model_offload_buffer_memory, model_lowvram (1040–1052)
CLIP.tokenize (sd.py:307) → tokenizer.tokenize_with_weights   # CPU-only, cheap
CLIP.encode_from_tokens (sd.py:381)
 ├─ self.load_model(tokens) (390)                            # re-enters GPU-ready path
 ├─ cuda_device_context(device)
 ├─ cond_stage_model.encode_token_weights(tokens) (395)      # THE model forward
 └─ returns raw [[cond, {"pooled_output": pooled}]]          # conditioning value
CLIP.encode_from_tokens_scheduled (sd.py:320)                # hook-keyframe variant
consumed by comfy/conds.py (CONDRegular)                     # no wrapper class
```

**Residency / repeated movement in one request:** confirmed — `load_models_gpu`
is called more than once per request whenever more than one encode node runs
(positive + negative) and/or `sampler_helpers._prepare_sampling`
(sampler_helpers.py:188–204) evicts the CLIP before sampling. On repeat calls
the `current_loaded_models` short-circuit (model_management.py:872–879) skips
the transfer loop, so an encoder CAN move more than once per request, and
`load_models_gpu` can be re-entered with zero re-transfer. Unload paths:
`free_memory` (799), `soft_empty_cache` (1944), `cleanup_models_gc` (956),
OOM `unload_all_models` (execution.py:632), `reset_cast_buffers` per-node in
aimdo mode (execution.py:541).

**Conditioning cache:** ComfyUI has no CLIP-encode cache in `comfy/`; the
relevant hit/miss boundaries are (a) `comfy_execution/caching.py`
`BasicCache._get_immediate/_set_immediate` (per-node result cache) and (b)
this repo's `ExactConditioningCache.lookup_many`
(comfymodal_runtime/clip_conditioning_cache.py:1446) — the one used by the
next paid run.

---

## 2. Instrumentation points

New self-contained module `comfymodal_runtime/clip_cold_path_forensics.py`
(no comfy/torch import at module top; testable with injected targets).
Wrappers are installed idempotently (sentinel + lock pattern, matching
`model_preload.py` conventions) and uninstall restores originals exactly.

| Boundary | Hook | Events emitted |
|---|---|---|
| GPU-ready entry/exit | `comfy.model_management.load_models_gpu` | `clip_cold_load_models_gpu_start/end` (model_count, clip_patcher_count, memory_required, wall/thread/process cpu) |
| Transfer loop | `ModelPatcher.load` + `partially_load` (shared depth ContextVar, outermost-only) | `clip_cold_patcher_load_start/end`, `clip_cold_patcher_partial_load_start/end` — wall, thread/process CPU, bytes_transferred (`model_loaded_weight_memory`), offload_buffer_bytes, total_model_bytes, lowvram, full_load, transfer_ops, size histogram, pinned/pageable counts, sync_count/sync_ms, `cuda_event_ms` (+realized flag) when sync flag on, model_ready_wall_unix_ns, resident_before / already_resident_bytes |
| Per-op bytes (sub-flag `..._CAST`) | `ModelPatcher.patch_weight_to_device` (only inside active load) | accumulates op count, bytes, histogram (tiny <1MiB / small 1–16MiB / medium 16–128MiB / large ≥128MiB), pinned vs pageable via `weight.is_pinned()` |
| Sync (sub-flag `..._SYNC_CUDA`) | `torch.cuda.synchronize` | count + cumulative wall, attributed to the active patcher load |
| Unload / teardown | `partially_unload`, `detach`, `free_memory`, `soft_empty_cache` | `clip_cold_unload` (kind=partial_unload, device_to, memory_to_free), `clip_cold_detach`, `clip_cold_free_memory`, `clip_cold_soft_empty_cache` |
| Encode | `CLIP.tokenize`, `CLIP.load_model`, `CLIP.encode_from_tokens`, `CLIP.encode_from_tokens_scheduled` | `clip_cold_tokenize_start/end`, `clip_cold_gpu_wait_start/end`, `clip_cold_encode_start/end`, `clip_cold_scheduled_encode_start/end` |
| Model forward (broadest generic wrapper) | lazy class-level wrapper on `cond_stage_model.encode_token_weights` (installed at first outermost encode) | `clip_cold_forward_start/end` (wall, thread/process cpu, status) |
| Encode decomposition | computed from encode + forward + gpu_wait spans | `forward_wall_ms`, `post_forward_ms`, token_count, batch_count, encode_index/call count |
| Conditioning cache | `ExactConditioningCache.lookup_many` | `clip_cold_cache_lookup` (hit_count, miss_count, decision hit/miss/partial, wall_ms) |
| Identity (per load/encode) | generic getattr only | patcher_id, model_id, clip_role, model_class, load_device, offload_device, current_device, patcher_dynamic, stored_dtypes, device_distribution (single guarded scan), source_files (basenames), checkpoint_bytes, recreatable_from_cpu_snapshot, capabilities {manual_cast_dtype, force_cast_weights, model_lowvram, loaded_mem_bytes, weight_dtype} |

**Output:** internal JSON-safe events (bounded 512) + optional bridge to the
project `RuntimeTrace.emit_at` convention + one bounded
`[v2.clip_cold_forensics] key=value` line on flush. `request_summary()`
aggregates: encode_calls, load_calls, cache_hits/misses/decisions,
multi_load_patchers, moved_more_than_once, total_h2d_bytes,
total_transfer_ops, histogram, pinned/pageable counts, total_sync_count/ms,
load/forward/encode/tokenize wall totals, resident_at_last_encode.

**Gating:** `COMFYMODAL_V2_CLIP_COLD_FORENSICS=1` via
`observability_gate(flag, "clip_cold_forensics")` (feature not in the
production-blocked set, so it fires under production mode when the flag is
set). Sub-flags: `..._CAST` (per-op accounting), `..._SYNC_CUDA`
(sync wrapper + CUDA-event realize). Disabled → install() returns
`{"status": "disabled"}`, zero patching, wrappers short-circuit.

**Wiring (the only edit to existing code):** additive block inside
`model_preload._ensure_core_wrappers` immediately after
`result.update(_install_clip_span_wrappers(trace=trace))`; guarded
try/except; imports the module lazily inside the function; registers
`clip_cold_forensics.<component>=<status>` into the wrapper-install result
dict. Inert unless the flag is set.

---

## 3. Files changed

| File | Change |
|---|---|
| `comfymodal_runtime/clip_cold_path_forensics.py` | **NEW** — generic telemetry module (identity, GPU readiness, encode decomposition, residency, cache hit/miss, JSON-safe events, gating, install/uninstall) |
| `tests/test_v2_clip_cold_forensics.py` | **NEW** — 22 unittest tests on synthetic torch modules / mocked patcher paths |
| `comfymodal_runtime/model_preload.py` | **EDIT (additive only)** — flag-gated wiring block in `_ensure_core_wrappers` |

No other files touched; no unrelated changes disturbed.

## 4. Local tests

```
python run_tests.py tests.test_v2_clip_cold_forensics
Ran 22 tests — OK
```
Coverage: identity capture; transfer bytes/ops/histogram/pinned (sub-flag);
per-op gated off by default; JSON-serializability of every event + summary;
disabled instance = zero overhead; encode decomposition walls + token/batch
counts + call count; cache hit (no load) vs miss (load + encode) vs partial;
residency load→partial-unload→reload→detach + multi-move detection +
already-resident bytes on a consecutive re-load; sync count + wall under
sub-flag; sync wrapper gated off by default; idempotent install + exact
uninstall restore; env-flag gating; install with no usable targets never
raises; wrapper emits end events with status=error on exceptions.

Adjacent suites: `tests.test_exact_cache_telemetry` (3 TestCase classes,
imports fine; the runner collects it as 0 tests — pre-existing loader
behavior unrelated to this batch's files) and
`tests.test_v2_cold_path_instrumentation` (1 pre-existing failure in the
concurrent SAMPLER_SAMPLE dedupe region — that test and the sampler code are
modified by concurrent agents; this batch's `model_preload.py` diff is only
the inert additive block, and the forensics module is never imported in that
test path because the flag is unset).

---

## 5. Final

```
generic call chain =
  loader nodes → comfy.sd.load_clip → CLIP.__init__ (ModelPatcher, is_clip, cached_patcher_init)
  → CLIP.load_model → model_management.load_models_gpu → LoadedModel.model_load
  → ModelPatcher.load/partially_load → patch_weight_to_device + torch.cuda.synchronize
  + module.to → model.device / model_loaded_weight_memory → GPU-ready
  → CLIP.tokenize → CLIP.encode_from_tokens → cond_stage_model.encode_token_weights
  → raw conditioning [[cond, {pooled_output}]] → comfy/conds.py
  → cache boundary: ExactConditioningCache.lookup_many + comfy_execution BasicCache
  → residency: free_memory / soft_empty_cache / partially_unload / detach / reload

instrumentation points =
  load_models_gpu (entry/exit, clip count, memory_required)
  ModelPatcher.load / partially_load (transfer wall, bytes, histogram, pinned/pageable,
    sync count/wall, cuda_event_ms, resident_before, model_ready timestamp)
  patch_weight_to_device (per-op, sub-flag) | torch.cuda.synchronize (sub-flag)
  partially_unload / detach / free_memory / soft_empty_cache (residency marks)
  CLIP.tokenize / load_model / encode_from_tokens / encode_from_tokens_scheduled
  cond_stage_model.encode_token_weights (broadest generic forward wrapper)
  ExactConditioningCache.lookup_many (hit/miss/partial)
  identity: patcher_id, model_id, clip_role, model_class, load/offload device,
    dtype + device distributions, source files + checkpoint bytes,
    capabilities (manual_cast / force_cast / weight_dtype / lowvram), dynamic flag,
    recreatable_from_cpu_snapshot

files changed =
  NEW  comfymodal_runtime/clip_cold_path_forensics.py
  NEW  tests/test_v2_clip_cold_forensics.py
  EDIT comfymodal_runtime/model_preload.py (additive flag-gated wiring only)

local tests =
  python run_tests.py tests.test_v2_clip_cold_forensics → 22/22 OK
  import sanity: module imports with neither comfy nor torch required

commit = none
Modal requests = 0
deploys = 0

next cold cache-miss run will measure =
  - CLIP GPU activation wall (clip_cold_patcher_load) with per-request totals,
    plus device-time (cuda_event_ms) when COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=1
  - bytes moved: bytes_transferred (loaded-weight memory) + offload buffer;
    per-op bytes/histogram/pinned-vs-pageable when ..._CAST=1
  - where time went: wall vs thread_cpu vs process_cpu deltas; sync_count/sync_ms;
    load_models_gpu entry/exit window; pageable-vs-pinned split
  - actual encode: tokenize wall, gpu-wait wall, encode total, forward wall,
    post-forward conversion wall, token/batch counts, encode call count
  - cache decision per lookup (hit/miss/partial) and whether the miss drove a
    real transfer loop vs the current_loaded_models short-circuit
  - residency: load→partial-unload→full-unload→reload sequence, multi-load
    patchers (moved_more_than_once), resident_at_last_encode

remaining unobservable pieces =
  - storage-read vs mmap page-fault decomposition inside the load wall:
    requires the separately-gated deep-model-diag wrappers / pagefault_tracking
    feature; this module stays dependency-free
  - RSS before/after and major/minor fault deltas: intentionally omitted
    (OS-dependent rusage/psutil); existing host-hardware telemetry covers it
  - true PCIe-bus H2D vs pinned staging: approximated via transfer-op histogram
    and pinned counts; exact PCIe duration needs CUDA events (sub-flag) and
    NVIDIA-specific tools
  - lowvram compute-time per-op casting (ops.py cast_bias_weight soft-weight
    path) is not per-op accounted — only the transfer-loop path
  - execution-graph queueing latency before the first load_models_gpu is out
    of scope (covered by existing trace stages)
```
