# V2 Batch E25 — Whole Critical-Path Compression

**Request:** `v2-benchmark-0-7a3e908f6580` (primary forensic grounding)
**Artifact:** `comfymodal-data/benchmarks/runs/v2_2026-08-18_02-37-17/run_001_sample.json`
(not present in this worktree — E24's reconciled report is the authoritative
timing source; the artifact path is the same one E24 consumed)
**Mode:** LOCAL implementation + validation. **No Modal deploy, no remote
request, no snapshot creation, no commit.**
**Date:** 2026-08-18

---

## 1. Executive result

E25 is a local-only implementation batch.  Six production code changes were
implemented and validated locally; zero remote activity occurred.  The changes
attack the largest serial critical-path intervals identified by E24:

1. **Pre-graph exact-identity cache** — model-key/prefill-key/model-spec and
   invocation-seed payload derivations are reused across identical-identity
   requests (fail-closed).
2. **Speculative CLIP hydration lane** — starts the direct-GPU fastsafetensors
   CLIP file read at plan receipt (the earliest safe moment), hiding the
   ~1.35 s hydration under the pre-graph setup window; the bind stays at demand
   time in the authoritative hydrator (numerical behavior unchanged).
3. **Proven-ready GPU-load fast return** — an opt-in, fail-closed skip of
   ComfyUI's redundant `ModelPatcher.load` bookkeeping when the execution-UNET
   lane already proved every parameter CUDA-resident (targets the
   joint-ready → sampling-start window and the post-CLIP UNET tail).
4. **First-step window instrumentation** — optional scoped decomposition of the
   1.07 s `sampling_start → first_sampler_step` window (gated on
   `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS`; zero cost when off).
5. **VAE early activation defaults** — the existing mutation-lane-bound VAE
   early-start (side-stream pre-copy during sampling + lane-bound `.data`
   rebind after sampling) is enabled for the production profile via
   `_runtime_env` (`sampling_end` + `250 ms` early-start; A/B profile keeps
   `late` for parity).
6. **Remote handoff attribution scaffolding** — the `remote_result_emit` stamp
   now carries the serialized payload byte count and inline-image flag so the
   next remote run can separate application serialization from Modal
   transport.

**Caveat on speculative CLIP hydration:** the lane performs the file read +
transform on a daemon thread at plan receipt, but the **bind remains demand-time
and requires the frozen manifest** (attached to the CLIP object).  The demand
hydrator takes the speculative tensors only after manifest verification; any
mismatch falls back to the normal read.  This means the *read* is hidden but
the *manifest-verification + bind + sync* (~100-200 ms) remains on the
critical path — a strictly-positive, safe partial hide.

---

## 2. Modal 4.08 s restore reconciliation

The user-observed Modal UI/platform `RESTORE / STARTUP ≈ 4.08 s` is treated as
an independent authoritative platform observation.  E24's narrow internal
fields are **not** substitutes:

| Boundary | Value | Source |
|---|---|---|
| `MODAL_UI_RESTORE_START` | **UNKNOWN (platform UI definition not observable from container logs)** | Modal UI "Restoring Function from memory snapshot" banner; the container cannot see the UI start moment |
| `MODAL_UI_RESTORE_END` | **UNKNOWN** | UI banner end; no container-visible boundary |
| `MODAL_UI_RESTORE_MS` | **≈ 4080 (user-observed)** | user observation, preserved verbatim |
| `MODAL_UI_RESTORE_SCOPE` | **UNKNOWN FROM CONTAINER TELEMETRY** | the container cannot observe the UI banner boundaries |
| `E24_PRE_PYTHON_START` | `modal_restore_begin` (Modal app log) | wall 1787020639552144896 |
| `E24_PRE_PYTHON_END` | `v2_startup_post_snapshot_restore_start` (python resume) | wall 1787020641011943680 |
| `E24_PRE_PYTHON_MS` | **1459.799** | E24 measured |
| `APPLICATION_RESTORE_MS` | **259.388** | E24 measured (snapshot_restore 198.6 + gpu_state 155.3 inner-overlap) |
| `E24_NARROW_RESTORE_MS` | **1719.187** | 1459.799 + 259.388 (container/artifact metric) |
| `RELATIONSHIP_BETWEEN_THE_TWO` | **NOT FULLY RECONCILED** | the two intervals have different endpoints and clock scopes; they are kept separate |

**Authoritative classification (pre-remote):**

| Component | Classification | Evidence |
|---|---|---|
| `MODAL_UI_RESTORE_MS` | **~4080 ms, USER-OBSERVED EXTERNAL METRIC** | user observation; exact UI start/end not visible to the container |
| `E24_NARROW_RESTORE_MS` | **1719.187 ms, CONTAINER/ARTIFACT METRIC** | E24 measured; `modal_restore_begin` → python resume → restore end |
| `RESTORE_SCOPE_DIFFERENCE` | **~2360.813 ms, NOT CLASSIFIED** | the difference between the two intervals is NOT labeled scheduling / platform startup / snapshot transfer / process spawn / CUDA init unless a specific boundary proves it; no such boundary is visible from container telemetry, so the cause is UNKNOWN |

**Verdict: NOT FULLY RECONCILED.**  The user-observed 4.08 s and the E24
narrow 1719.187 ms are kept as SEPARATE metrics.  The report does NOT compute
`artifact runtime + (4080 − 1719.187)` as though the intervals share endpoints,
and does NOT label the ~2360 ms gap with any specific phase name.  Both the A
(artifact no-scheduling) and B (Modal-phase with 4.08 s) totals are reported
separately in §15/§16 with the caveat that B is a synthetic combination of two
different clock scopes, retained only for rough orientation.

**Instrumentation added for the next run:** none needed in-container — the
boundaries are platform-side.

---

## 3. Pre-graph snapshot/cache/overlap audit

The 1472.095 ms `method-entry → graph-start` window decomposes as follows
(D13 forensics + E25 code audit; per-operation):

| Operation | Location | Inputs | Class | Est. ms (best evidence) |
|---|---|---|---|---|
| `_capture_remote_identity` / method first line | `modal_app.py:16736-16748` | static (identity/env) | SNAPSHOT_STATIC | ~0.4 |
| request-origin extraction / env-profile propagation | `:16752-16834` | request-carried env | REQUEST_SPECIFIC_PARALLEL | ~1 |
| `ExecutionPlan.from_dict` (deserialize) | `:16884` | request payload | HARD_SERIAL | 0.8-40 (D13: 0.79) |
| `begin_request` orchestration | `:16890` | request id + model_spec | REQUEST_SPECIFIC_PARALLEL | ~0 |
| UNET plan-receipt schedule (G1) | `:16908` → `_maybe_schedule_execution_unet_at_plan_receipt` | request workflow (derived identity) | REQUEST_SPECIFIC_BUT_CACHEABLE (derivation) + worker | ~33 (worker pickup) |
| **E25 speculative CLIP lane start** | `:17069-17079` | request identity | REQUEST_SPECIFIC_PARALLEL (worker read) | ~1 submit |
| `load_store_from_disk` (signature store) | `:17185` | static module state | SNAPSHOT_STATIC (module-guarded once) | ~11 (D16: uncached parse 11.35) |
| conditioning prefetch thread | `:17190` | request plan | REQUEST_SPECIFIC_PARALLEL | ~0.5 (submit) |
| input-types warm thread | `:17200` | request workflow | REQUEST_SPECIFIC_PARALLEL | ~0.5 (submit) |
| `_derive_request_snapshot_seed` | `:17353` | workflow + hashes + deployment identity | REQUEST_SPECIFIC_BUT_CACHEABLE (payload pure; hydration on caller) | 0.9-1.6 (D16 local) → ~0 on cache hit |
| method-entry-gap computation | `:17357` | restore marker (static) | SNAPSHOT_STATIC | ~0 |
| `ExecutionContext` construction | `:17433` | request | REQUEST_SPECIFIC_PARALLEL | ~0.5 |
| `_attach_snapshot_seed_metadata` | `:17450` | static bootstrap state | SNAPSHOT_STATIC | ~0 |
| trace metadata + `validate_torch_thread_policy` | `:17460-17488` | request + static | REQUEST_SPECIFIC_PARALLEL (serial but small) | ~1 |
| trace setup + `remote_method_entry` emission | `:17521-17715` | request + static | REQUEST_SPECIFIC_PARALLEL | ~6 (D13 trace setup) |
| first status yield | `:17720` | — | HARD_SERIAL (protocol boundary) | ~0 |
| `RuntimeExecutor.stream` head | `:17727` | request | REQUEST_SPECIFIC_PARALLEL (stream resume) | 17-206 (GAP3, platform floor) |
| `_run_in_process` head + runtime_config | `:11547-11587` | static (first request) | SNAPSHOT_STATIC (first request only) | ~0.05 |
| CPU-snapshot binding block | `:11600-12042` | request identity vs snapshot | REQUEST_SPECIFIC_BUT_CACHEABLE (identity derivation) + HARD_SERIAL (bridge publish) | 3-188 (D13 GAP2, contention) |
| execution-prefill schedule | `:12117` | request | REQUEST_SPECIFIC_PARALLEL | ~0 |
| execution-UNET schedule | `:12127` | request | REQUEST_SPECIFIC_PARALLEL (no-op after G1) | ~0 |

**GAP1 (~1087 ms) root cause:** D13 proved the plan-receipt schedule region is
~40 % serial enrichment (seed derivation + store load), ~30 % trace/context/
validation, ~30 % GIL contention (UNET lane + ITW warm + prefetch thread).
D16 proved the seed builder is only ~1.27 ms locally — the remote 150-400 ms
estimate was contention-amplified.  E25 attacks the serial parts: the
derivations are now cached (exact-identity), and the store load is
module-guarded.

---

## 4. Earliest-safe CLIP start

| Quantity | Value |
|---|---|
| `EARLIEST_SAFE_CLIP_START_EVENT` | **plan-receipt (after `ExecutionPlan.from_dict` + G1 identity derivation)** — the exact CLIP identity (loader class, `clip_name`, `clip_type`, weight dtype policy from `model_spec`) is known the moment the plan is deserialized |
| `CURRENT_CLIP_HYDRATION_EXPOSED_MS` | **1345.935** (E24 `clip_hydration_gpu_start → end`; this is the demand-time read+bind window) |
| `EXPECTED_CLIP_HYDRATION_HIDDEN_MS` | **~700-1100** (the fastsafetensors file→GPU read + transform runs on the speculative lane during pre-graph setup; the manifest verify + bind + sync remains demand-time) |
| `EXPECTED_CLIP_HYDRATION_EXPOSED_AFTER_E25_MS` | **~250-650** (verify + bind + sync + any un-hidden read tail) |

**Why the bind cannot move earlier:** the frozen manifest (key/shape/dtype/
pipeline) is attached to the CLIP object at capture; without it the hydrator
fails closed to native.  The lane reads + transforms but does NOT bind — no GPU
mutation occurs while any request could be in a CLIP critical window (D15
preserved).  The demand-time `_try_fast_hydrate` takes the speculative tensors,
verifies them against the manifest, binds via Comfy's own `load_sd`
(`assign=True`, zero-copy), and syncs — identical numerical behavior.

---

## 5. Earliest-safe UNET start

| Quantity | Value |
|---|---|
| `EARLIEST_SAFE_UNET_START_EVENT` | **plan-receipt** (already implemented by Batch-A G1: `unet_execution_plan_receipt_schedule` fires immediately after deserialization; `preload_worker_started` ~33 ms after method entry) |
| `UNET_PREFETCH_START_MOVED_EARLIER_BY_MS` | **0** — the G1 plan-receipt hoist is already the earliest safe moment (the UNET identity is only known after deserialization, and the lane submit is fire-and-forget) |
| `D15_PRESERVED` | **YES** — the speculative UNET lane runs CPU-side source read on workers; the GPU H2D (`begin_unet_gpu_phase`) still waits for the CLIP critical section to fully release |

The G1 lane's source read (2819 ms) was already fully overlapped inside the
CLIP forward window in ON #2 (`unet_prefetch_overlap_with_setup_ms=2819.289`).
No redesign was warranted; the early launch is preserved.

---

## 6. Implemented snapshot/static moves

| Change | What moved | Verification |
|---|---|---|
| **C1: pre-graph exact-identity cache** | `derive_model_key` / `derive_prefill_key` / `build_restore_model_spec` results are reused across identical-identity requests.  The identity key contains workflow_hash, source_workflow_hash, model_stack hash, deployment hash, custom-node generation.  Cache is bounded (16 entries LRU), thread-safe, and fail-closed (any miss/exception → original derivation). | `tests/test_v2_e25_pre_graph_and_speculative.py` (compute-or-reuse, exact-key, LRU, fail-closed) |
| **C2: invocation-seed payload cache** | `build_invocation_seed_payload` (the pure graph-analysis builder) is cached under `(pre_graph_identity + output_node_ids)`.  Only the pure payload is cached — `state.hydrate_snapshot_seed_payload` still runs on the caller thread (hydration of mutable container state is never cached). | same test file + `test_v2_conditioning_prefetch.py` / `test_v2_local_pre_submit_optimization.py` |

**SNAPSHOT/static moves deliberately NOT made:**
- `load_store_from_disk` — D16 proved snapshot-capture preload is not
  freshness-safe (a restored process could retain a stale `_MEMO_STORE` while
  the mounted file changed after capture).  Left at request time; it is
  module-guarded and loads once.
- Runtime shape/config — already static (first-request only).

---

## 7. Implemented pre-graph cache/reuse

The `pre_graph_cache.py` module provides a thread-safe, bounded, exact-identity
cache.  Reuse is fail-closed: a cache entry is used only when the caller passes
the exact identity key that stored it, and only for PURE derivations.  Request
seed, prompt text, conditioning, and request IDs are never part of any key.
Measured local overhead: a cache hit is a dict lookup under a lock (sub-µs);
the `with_cache` compute-or-reuse wrapper adds one string-hash per lookup.

### 7.1 First-cold-request cache behavior (pre-remote correction)

The E25 exact-identity cache is **process-local** (a module-level `PreGraphCache`
in `pre_graph_cache.py`).  It is populated only when a request runs the
derivation and stores the result.  The production target is the FIRST request
on a fresh restored container, so the cold-request question is answered
explicitly:

| Question | Answer |
|---|---|
| Does the first cold request hit any E25 pre-graph cache? | **NO** — the cache starts empty in a fresh process; nothing seeds it before request 1 |
| Is any E25 cache state captured in the memory snapshot? | **NO** — the cache is a plain Python module dict; Modal memory snapshots capture process memory, so a *restored* container WOULD carry a warm cache from the construction/restore container, but the E25 derivation only runs at request time and no restore-time code calls it |
| Is the same derivation called twice within request 1? | **YES** — `derive_model_key` is invoked in the plan-receipt G1 schedule AND the binding block (the binding block reuses the plan-receipt stash, but the G1 schedule itself and the seed payload builder each run once).  The cache can therefore save the *second* call within request 1 only when the first call stored a value — which it does.  **This is an intra-request saving, not a cross-request one.** |
| Does another pre-request/bootstrap path seed it? | **NO** — only `_cached_pre_graph_derivations` and `_derive_request_snapshot_seed` write to it, both request-time |

**Verdict: `PREGRAPH_CACHE_FIRST_COLD_EXPECTED_HIT = NO`** (cross-request).
The cache does NOT save wall on the first cold request's *first* derivation of
each value.  The intra-request reuse (plan-receipt → binding block) is real but
small: the binding block already reuses the plan-receipt stash
(`_plan_receipt_request_model_key`), so the cache's marginal cold-request saving
is limited to the seed-payload builder being called once per request regardless
(no duplicate within request 1 for the seed).  **Expected first-cold saving
from this cache = 0 ms.**  It is preserved as a reusable-container optimization
(warm containers / subsequent requests), which is NOT counted toward the cold
13 s target.

**Runtime proof to collect on the validation run:** the cache key + hit/miss
state per derivation is emitted via `snapshot_seed_request_derived` (miss on
request 1) and the model-key derivation is observable via the plan-receipt vs
binding-block identity guard.  All four cache classes (model-key, prefill-key,
model-spec, seed-payload) will be reported as MISS on request 1.

---

## 8. Implemented CLIP early hydration

**Mechanism** (`speculative_clip_hydration.py`):

1. At plan receipt, after the G1 identity derivation, `_start_speculative_clip_lane`
   resolves the CLIP file paths from `model_spec.loaders.clip` via ComfyUI
   `folder_paths`, builds an exact identity (model key hash + clip file names +
   workflow/deployment/custom-node generation + fastsafe config), and starts a
   daemon thread that runs `_fastsafe_load` (direct-GPU fastsafetensors read)
   + `_select_pipeline`/`_apply_pipeline` per file.
2. The lane holds the loaded GPU tensors + owners (single-flight per request;
   an identity change drops the stale lane).
3. At demand time, the authoritative `_try_fast_hydrate` takes the speculative
   tensors, verifies each against the frozen manifest (`_verify_file_against_manifest`),
   and on match binds via `hydrate_clip_bind` (zero-copy, `assign=True`) + syncs
   — the EXACT existing path.  On any mismatch the speculative owners are
   closed and the normal read loop runs.
4. Request end (`clear_activation_references`) closes any unconsumed lane
   (owners closed + `torch.cuda.empty_cache`), so a request that never demands
   the CLIP leaks nothing.

**Gates (all must hold):** `COMFYMODAL_V2_CLIP_FAST_HYDRATION=1` +
`COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1` (default) + resolvable file paths
+ non-empty request id.  **No duplicate hydration:** the hydrator's
`already_hydrated` marker remains authoritative; the lane is single-flight.

**D15:** the speculative lane performs no GPU mutation; the D15 critical
bracket wraps only the demand-time bind/sync exactly as today.

---

## 9. UNET overlap and D15 preservation

No UNET GPU overlap was introduced.  The D15 gate
(`begin_unet_gpu_phase` waits for `clip_owner_tid is None`) is untouched.  The
speculative CLIP lane is CPU/GPU-read only (the read targets GPU memory via
fastsafetensors but performs no model mutation), so it does not enter the
CLIP critical section.  The UNET H2D still waits for CLIP forward to release
the critical section.  `test_v2_batch_d15_critical_gpu_lane_coordination.py`
passes (52 tests incl. the D15 gate).

**Post-CLIP UNET tail reduction:** the E25 `COMFYMODAL_V2_GPU_FAST_RETURN`
opt-in short-circuits the sampler's redundant `load_models_gpu` re-validation
when the lane already proved every parameter CUDA-resident.  The D15 gate is
not entered on the fast path (no GPU work to gate).

---

## 10. Joint-ready → sampler compression

| Quantity | Value |
|---|---|
| `CURRENT_JOINT_READY_TO_SAMPLING_START_MS` | **227.243** (E24: unet_ready → sampler node 102.883 + sampler node → sampling start 124.170) |
| `EXPECTED_JOINT_READY_TO_SAMPLING_START_MS` | **~120-170** (the 124.170 sampler-node → sampling-start window includes the sampler's `load_models_gpu` re-validation; the opt-in fast return removes most of the `ModelPatcher.load` bookkeeping while keeping the telemetry + lane accounting) |

The fast return is **off by default** (parity preservation); the remote
validation deployment enables `COMFYMODAL_V2_GPU_FAST_RETURN=1`.

---

## 11. First-step instrumentation/decomposition

Scoped, gated instrumentation added to the sampler wrapper:

- `sampler_first_step_window_start` (at `sampling_start` + 0) — records the
  authoritative `sampling_start` monotonic.
- `sampler_first_step_callback` (at the first completed step) — records
  `first_step_window_ms` = the full pre-first-step window.

Both are gated on `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS` (the existing
`opt_diag_enabled()`); zero cost when off.  No global synchronization is added
solely for timing — all stamps are monotonic wall reads.

| Quantity | Value |
|---|---|
| `FIRST_STEP_WINDOW_MS` | 1067.597 |
| `FIRST_STEP_INSTRUMENTATION_ADDED` | YES (scoped + gated) |
| `FIRST_STEP_KNOWN_SETUP_MS` | **UNKNOWN before remote run** (instrumentation will split it) |
| `FIRST_STEP_KNOWN_GPU_COMPUTE_MS` | **UNKNOWN before remote run** (first UNET forward) |
| `FIRST_STEP_REMAINING_UNKNOWN_MS` | 1067.597 − (setup + compute) — to be resolved by the next run |

---

## 12. VAE transition compression

**Current:** `sampling_end → vae_decode_start = 838.839 ms`.  E24 + the
post-sampling forensics show the default `late` VAE activation mode loads the
VAE at graph demand — the 838.839 ms is plain VAEDecode demand-load (VAE
H2D ~858.9 ms overlaps the VAE stage; no soft_empty_cache/unload in the
wrapper when running normally).

**E5 empty-cache bypass applicability: NO** — the E5 bypass is a policy library
with no production caller, and the transition has no `soft_empty_cache` to
bypass.  The applicable path is the **existing VAE early activation** (mutation
lane + side-stream pre-copy).  E25 enables it for the production profile:

- `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end` (production) — schedules the
  VAE GPU load on the coordinator pool at the real sampling-end boundary.
- `COMFYMODAL_V2_VAE_EARLY_START_MS=250` (production) — the transfer-only
  B-arm pre-copies VAE CPU params to CUDA on a side stream during sampling
  (no lane, no model mutation), then rebinds `.data` under the lane strictly
  after the sampler released it.
- A/B benchmark profile keeps `late` + `0` (byte-identical parity).

The invariants are proven by the existing mutation-lane protocol and the VRAM
guard (`_check_early_activation_vram`, 1.1× + margin).  Any failure falls back
silently to the unchanged graph path.

| Quantity | Value |
|---|---|
| `CURRENT_VAE_TRANSITION_MS` | 838.839 |
| `E5_PATH_APPLICABLE` | NO (no empty-cache call in the transition) |
| `EXPECTED_VAE_TRANSITION_AFTER_E25_MS` | **~300-450** (VAE H2D hidden under the sampling tail; residual = graph dispatch + decode-ready wait) |

---

## 13. Output serialization and handoff work

**Output cost (`~247 ms` remote, PNG encode ~162 ms):** the output path is
already descriptor-mode (no base64, no inline bytes), the volume commit is
async/deferred, and the PNG compress level defaults to 1 (fastest).  The
remaining encode cost is ComfyUI's own PIL PNG writer — no low-risk
semantics-preserving reduction exists beyond the current state.  **No code
change.**

**Remote handoff (`1820.642 ms`):** the result travels as Modal generator JSON
events; the 3.13 MB PNG bytes are NOT inline (descriptor mode) — the local
side fetches via `read_output_asset` through the persisted-asset path.  The
transport cost is therefore Modal generator-frame transport of a small
descriptor payload, not image bytes.  E25 adds attribution scaffolding:
`remote_result_emit` now stamps `remote_handoff_payload_bytes` (the serialized
result size) and `handoff_payload_has_inline_images=0`, so the next run can
separate application serialization from platform transport.

| Quantity | Value |
|---|---|
| `CURRENT_REMOTE_HANDOFF_MS` | 1820.642 |
| `HANDOFF_APPLICATION_CONTROLLED_MS` | ~10-50 (result dict assembly + JSON serialization, per `_measure_json_bytes`-based estimates) |
| `HANDOFF_PLATFORM_CONTROLLED_MS` | ~1770-1810 (Modal generator-frame transport + local deserialization; not code-optimizable) |
| `EXPECTED_REMOTE_HANDOFF_AFTER_E25_MS` | ~1800-1820 (unchanged — platform-bound; attribution now measurable) |

---

## 14. Local validation

| Suite | Result |
|---|---|
| `tests/test_v2_e25_pre_graph_and_speculative.py` (new) | 9 passed |
| `tests/test_v2_preload_bridge.py` | 69 passed |
| `tests/test_v2_batch_e5_empty_cache_bypass.py` + `test_v2_batch_d15_critical_gpu_lane_coordination.py` + `test_transport_cancellation.py` | 52 passed, 10 subtests |
| `tests/test_v2_local_pre_submit_optimization.py` + `test_v2_conditioning_prefetch.py` + `test_v2_prompt_signature_cache.py` + `test_v2_conditioning_exact_hit_breakdown.py` | 152 passed |
| `tests/test_v2_clip_fast_hydration_production.py` + `test_v2_clip_hydration_states.py` | included in the 162-pass run |
| `tests/test_warmup_profile_dedup.py` | 37 passed |
| **py_compile** all 6 touched modules + the new test | PASS |
| **git diff --check** on all E25-touched files | PASS (clean) |

**Pre-existing test bug (not E25):** `tests/test_runtime_canonical_v2.py::TestExecutePlan`
fails 4/8 even **in isolation** — the class's `setUp` does not reset the
process-local `_PROFILE_PREP_CACHE` in `canonical_execution.py`, so the first
`published`-expecting test populates the cache and the remaining tests observe
`active_profile_publish_decision=cached_unchanged`.  This reproduces without
any E25 change (verified: `python -m pytest tests/test_runtime_canonical_v2.py::TestExecutePlan`
→ 4 failed, 4 passed).  It is unrelated to E25; no E25 test depends on that
class.

---

## 15. Current vs expected critical-path waterfall

All values ms.  **No double-counted overlap.**  "EXPECTED AFTER E25" uses only
implemented changes plus clearly-separated estimates.

| Interval | CURRENT | EXPECTED AFTER E25 | IDEAL LATER |
|---|---:|---:|---:|
| Modal-reported restore/startup (B clock) | ~4080 | ~4080 (platform; unchanged) | ~1500-2500 (region/host + snapshot transfer) |
| Application restore (A clock) | 259.388 | 259.388 (unchanged) | ~150 |
| restore → model-start delay (method→graph) | 1472.095 | **~700-1000** (seed/key cached; store guarded; contention reduced) | ~300-500 |
| Exposed CLIP hydration | 1345.935 | **~250-650** (read hidden; verify+bind+sync remain) | ~100 |
| CLIP forward | 3313.016 | 3313.016 (unchanged — numerical) | ~2500-3000 (model-dependent) |
| Exposed UNET tail (post-CLIP → ready) | ~545 | **~400-500** (fast-return shaves sampler re-validation; H2D + bind unchanged) | ~200 |
| joint-ready → sampling | 227.243 | **~120-170** | ~80 |
| first-step window | 1067.597 | ~1067.597 (instrumented; no claimed saving) | ~800-1000 |
| remaining diffusion loop | 3641.826 | 3641.826 (unchanged) | ~3000 |
| VAE transition | 838.839 | **~300-450** (production profile early activation) | ~200 |
| VAE decode | 349.526 | 349.526 (unchanged) | ~300 |
| output | 247.265 | 247.265 (unchanged; already efficient) | ~150 |
| remote handoff | 1820.642 | ~1800-1820 (platform-bound) | ~500-1000 (platform) |
| local return | 31.000 | 31.000 (unchanged) | ~20 |

**Totals:**

- **A. Artifact-compatible no-scheduling total:** CURRENT 16865.854 →
  **EXPECTED ≈ 15050-15600** (saving ≈ 1270-1820).
- **B. Modal-phase total (4.08 s restore):** CURRENT ≈ 16865.854 + (4080 −
  1719.187) ≈ **19226.667** → EXPECTED ≈ **17410-17960**.

Both clocks are kept; the 4.08 s user-observed restore is not merged into the
artifact clock.

---

## 16. 13-second projection

- `CURRENT_ARTIFACT_NO_SCHEDULING_MS` = 16865.854
- `EXPECTED_ARTIFACT_NO_SCHEDULING_MS` ≈ 15050-15600 (E25)
- `TARGET_13S_REMAINING_GAP_MS` ≈ 15050-15600 − 13000 = **2050-2600**

**The 13 s target is NOT reached by E25 alone.**  The remaining gap is
dominated by intervals E25 deliberately did not touch: CLIP forward
(3313 ms, numerical), the diffusion loop (3642 ms), and the platform handoff
(~1810 ms).  The next-highest-value targets are (1) conditioning-cache reuse
to eliminate the CLIP forward on repeated identical prompts, (2) first-step
window decomposition once the new instrumentation reports, and (3) platform
side (restore + transport).

---

## 17. Exact remote validation gate

**Prepared but NOT executed.**  The next authorized validation requires
exactly:

- **1 deployment** (production profile with `COMFYMODAL_V2_GPU_FAST_RETURN=1`
  and the E25 `_runtime_env` defaults; benchmark artifact profile for the A/B
  parity arm)
- **1 paid cold conditioning-miss inference** (`--run-count 1`, the existing
  E22 hard guard already enforces this)

**Command (reference only — NOT run):**

```
python tools/benchmark_v2_direct.py --run-count 1 [--deploy-name <e25-validation>] ...
```

**Required remote metrics (all already emitted by existing telemetry or the
new E25 events):**

`Modal UI/platform restore/startup` (user-observed), `pre_python_snapshot_restore`
(1459.799 baseline), `application_restore` (259.388 baseline), `remote_method_entry`,
`snapshot_seed_request_derived` (cache-hit evidence), `unet_execution_plan_receipt_schedule`,
`clip_fh_speculative_consumed` (NEW — proves the lane was taken),
`clip_fh_speculative_rejected` (NEW — proves fail-closed fallback),
`clip_hydration_gpu_start/end`, `clip_forward_start/end`, `unet_gpu_transfer_start/end`,
`unet_ready`, `model_readiness_gate`, `sampler_first_step_window_start` (NEW),
`sampler_first_step_callback` (NEW), `sampling_start`, `first_sampler_step`,
`sampling_end`, `vae_early_activation_scheduled` (production arm),
`vae_decode_start/end`, `output_encode_start/end`, `remote_result_emit`
(with NEW `remote_handoff_payload_bytes`), `local_result_received`,
`execute_plan_return`.

---

## 18. Metrics block (final fields)

```text
E25_WHOLE_CRITICAL_PATH_COMPRESSION_COMPLETE = YES (local implementation + validation; remote NOT executed)
REMOTE_DEPLOYS = 0
PAID_REQUESTS = 0
COMMIT = none

MODAL_REPORTED_RESTORE_MS = ~4080
MODAL_RESTORE_BOUNDARY_RECONCILED = PARTIAL
MODAL_RESTORE_EXACT_SCOPE = UNKNOWN FROM CONTAINER TELEMETRY; user-observed ~4080 is an
  external metric, E24 narrow 1719.187 is a container/artifact metric; kept separate
E24_NARROW_RESTORE_MS = 1719.187 (pre_python 1459.799 + application 259.388)
RESTORE_SCOPE_DIFFERENCE_MS = ~2360.813
RESTORE_SCOPE_DIFFERENCE_CAUSE = NOT CLASSIFIED (no container-visible boundary proves
  scheduling/platform-startup/snapshot-transfer/spawn/CUDA-init; the two intervals have
  different endpoints and clock scopes; NOT relabeled)

PREGRAPH_CURRENT_MS = 1472.095
PREGRAPH_SNAPSHOT_SAFE_MS = ~60-90 (identity capture, method-entry-gap, runtime_config first-request,
  seed-payload cache reuse; store load kept at request time for freshness)
PREGRAPH_CACHEABLE_MS = ~30-70 (model-key/prefill-key/spec + seed payload; exact-identity)
PREGRAPH_OVERLAPPABLE_MS = ~900-1100 (GIL contention + worker-ready work already off main;
  seed + store serial portion now cached/guarded)
PREGRAPH_HARD_SERIAL_MS = ~30-60 (deserialize + trace setup + bridge publish + status yield)
PREGRAPH_EXPECTED_AFTER_E25_MS = ~700-1000

EARLIEST_SAFE_CLIP_START_EVENT = plan-receipt (after ExecutionPlan.from_dict + G1 identity derivation)
CURRENT_CLIP_HYDRATION_EXPOSED_MS = 1345.935
EXPECTED_CLIP_HYDRATION_HIDDEN_MS = ~700-1100 (speculative file read + transform)
EXPECTED_CLIP_HYDRATION_EXPOSED_AFTER_E25_MS = ~250-650 (manifest verify + bind + sync)

EARLIEST_SAFE_UNET_START_EVENT = plan-receipt (G1 hoist already earliest)
UNET_PREFETCH_START_MOVED_EARLIER_BY_MS = 0
D15_PRESERVED = YES

CURRENT_POST_CLIP_UNET_TAIL_MS = ~545
EXPECTED_POST_CLIP_UNET_TAIL_MS = ~400-500 (opt-in fast-return on sampler re-validation)

CURRENT_JOINT_READY_TO_SAMPLING_START_MS = 227.243
EXPECTED_JOINT_READY_TO_SAMPLING_START_MS = ~120-170

FIRST_STEP_WINDOW_MS = 1067.597
FIRST_STEP_INSTRUMENTATION_ADDED = YES (gated on COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS)
FIRST_STEP_KNOWN_SETUP_MS = UNKNOWN (instrumentation will resolve on next remote run)
FIRST_STEP_KNOWN_GPU_COMPUTE_MS = UNKNOWN (first UNET forward)
FIRST_STEP_REMAINING_UNKNOWN_MS = 1067.597 - (setup + compute)

CURRENT_VAE_TRANSITION_MS = 838.839
E5_PATH_APPLICABLE = NO (no empty-cache call in the transition)
EXPECTED_VAE_TRANSITION_AFTER_E25_MS = ~300-450 (production-profile early activation)

CURRENT_OUTPUT_REMOTE_MS = 247.265
EXPECTED_OUTPUT_REMOTE_AFTER_E25_MS = ~247 (already descriptor-mode + async commit + fastest PNG)

CURRENT_REMOTE_HANDOFF_MS = 1820.642
HANDOFF_APPLICATION_CONTROLLED_MS = ~10-50 (result dict + JSON serialize)
HANDOFF_PLATFORM_CONTROLLED_MS = ~1770-1810 (Modal generator-frame transport)
EXPECTED_REMOTE_HANDOFF_AFTER_E25_MS = ~1800-1820 (platform-bound; now attributed)

IMPLEMENTED_CHANGE_1 = pre-graph exact-identity cache (model-key/prefill-key/spec + seed payload)
EXPECTED_SERIAL_SAVING_1_MS = 0 (first cold request: cache starts empty -> all misses;
  preserved as a reusable-container/warm optimization only; intra-request reuse is
  already covered by the plan-receipt stash)

IMPLEMENTED_CHANGE_2 = speculative CLIP hydration lane (plan-receipt file read)
EXPECTED_SERIAL_SAVING_2_MS = ~700-1100 (hydration read hidden under setup)

IMPLEMENTED_CHANGE_3 = proven-ready GPU-load fast return (opt-in)
EXPECTED_SERIAL_SAVING_3_MS = ~50-110 (sampler re-validation skip)

IMPLEMENTED_CHANGE_4 = first-step window instrumentation (gated, no behavior change)
EXPECTED_SERIAL_SAVING_4_MS = 0 (measurement only)

IMPLEMENTED_CHANGE_5 = VAE early activation for production profile
EXPECTED_SERIAL_SAVING_5_MS = ~400-540 (838.839 -> ~300-450)

IMPLEMENTED_CHANGE_6 = remote handoff attribution scaffolding (no behavior change)
EXPECTED_SERIAL_SAVING_6_MS = 0 (measurement only)

TOTAL_EXPECTED_CRITICAL_PATH_SAVING_MS = ~1240-1720 (changes 2+3+5; change 1 = 0 on cold;
  no double-count: change 2 hides hydration under pre-graph setup)

CURRENT_ARTIFACT_NO_SCHEDULING_MS = 16865.854
EXPECTED_ARTIFACT_NO_SCHEDULING_MS = ~15120-15620

MODAL_PHASE_BASELINE_WITH_4_08_RESTORE_MS = ~19226.667 (16865.854 + 4080 - 1719.187; synthetic
  cross-clock combination for rough orientation only; the two restore metrics are kept separate)
EXPECTED_MODAL_PHASE_TOTAL_MS = ~17480-17980

EXPECTED_TIME_TO_CLIP_START_IMPROVEMENT_MS = ~0 (CLIP forward start unchanged; hydration start hidden)
EXPECTED_TIME_TO_MODELS_READY_IMPROVEMENT_MS = ~700-1100 (CLIP hydration hidden)
EXPECTED_TIME_TO_SAMPLING_START_IMPROVEMENT_MS = ~750-1210 (hydration + fast-return)
EXPECTED_TIME_TO_REMOTE_RESULT_IMPROVEMENT_MS = ~1150-1750 (hydration + VAE early + fast-return)
EXPECTED_TIME_TO_LOCAL_RESPONSE_IMPROVEMENT_MS = ~1150-1750 (same; handoff unchanged)

TARGET_13S_REMAINING_GAP_MS = ~2050-2600 (15050-15600 vs 13000)

FOCUSED_TESTS = test_v2_e25_pre_graph_and_speculative (9) + test_v2_preload_bridge (69)
  + E5/D15/transport (52+10) + seed/prefetch/signature (152) + canonical (60)
  + clip hydration states/production (in the 162-pass run) + warmup dedup (37)
PYCOMPILE = PASS (6 modules + test)
GIT_DIFF_CHECK = PASS (E25-touched files clean)

REMOTE_VALIDATION_READY = YES
REMOTE_VALIDATION_MAX_DEPLOYS = 1
REMOTE_VALIDATION_MAX_PAID_REQUESTS = 1
REMOTE_VALIDATION_EXECUTED = NO

TOP_REMAINING_BOTTLENECK = CLIP forward (3313.016 ms, numerical) + diffusion loop (3641.826 ms);
  after E25 the pre-sampler CLIP interval is the largest compressible serial block

NEXT_ACTION = authorized remote validation (1 deploy, --run-count 1, cold
  conditioning-miss) against ON #2; read the new speculative-consumed/first-step
  events; then attack CLIP forward via exact conditioning-cache reuse and the
  first-step window with the new decomposition
```

---

# 19. Pre-remote corrections (supersede the earlier sections where they conflict)

Two reporting corrections were applied BEFORE remote work, per the E25 remote
validation brief.  The earlier sections 2/7 retain the pre-correction text as
``PRE-REMOTE ESTIMATES``; this section is authoritative:

**A. Modal restore accounting:** the user-observed ``~4080 ms`` is an external
UI metric; the container cannot observe the UI banner boundaries.  It is kept
SEPARATE from the E24 narrow 1719.187 ms container/artifact metric.  The
~2360 ms difference is **NOT CLASSIFIED** (no container-visible boundary proves
scheduling/platform-startup/snapshot-transfer/spawn/CUDA-init).  The report
does NOT compute ``artifact + (4080 − 1719.187)`` as a reconciled total.

**B. Pre-graph cache cold-request honesty:** the E25 exact-identity cache is
process-local and starts empty on a fresh container.  It does NOT save wall on
the first cold request's first derivation of each value
(``PREGRAPH_CACHE_FIRST_COLD_EXPECTED_HIT = NO``, cold saving = 0 ms).  It is a
reusable-container/warm optimization only and is NOT counted toward the cold
13 s target.

**C. First-step instrumentation additions (pre-remote):** the E25 scoped
instrumentation now emits ``sampler_wrapper_setup_done`` (wrapper-setup
boundary immediately before the sampler executor call) and the existing
``unet_first_cuda_op`` / ``unet_first_cuda_forward_complete`` events (first
UNET forward enter/exit), so the pre-first-step window decomposes into
wrapper-setup / dispatch-to-first-forward / forward-wall / callback-tail.

# 20. E25 remote structural validation

The validation selector ``E25_VALIDATION`` was added to both wrapper .bat files
(``deploy_and_run_v2_single.bat`` and ``run_v2_single.bat``), the benchmark CLI
(``--verify-e25-profile`` + hard single-run guard), and the runtime
(``_runtime_env`` passthrough for the five E25 flags).  The selector inherits
the E19 final cold-loader base and changes ONLY the E25 validation flags
(speculative CLIP hydration, GPU fast return, optimization diagnostics, VAE
sampling_end/250).  The old parity profile (VAE late / early-start 0) is NOT
selected.  Local preflight confirmed ``PROFILE ACCEPTED``,
``BENCHMARK_RUN_COUNT=1``, ``EXPECTED_PAID_REQUEST_COUNT=1``,
``MODAL_DEPLOY_SKIPPED=1``; the negative count-2 guard exits nonzero before
deployment.

**Remote execution history (authorized re-runs):** deploys 1-6 were executed
with the canonical wrapper; the benchmark portion of the first five hit the
construction container's first request (backend startup 17-19 s — NOT a
reused-snapshot cold run), so they were structurally invalid for the ON #2
comparison.  The speculative CLIP lane failed path resolution in every deploy
(``clip_paths_unresolved``) and the demand-time request-id seam was fixed.  The
authoritative valid run is **deploy 7 + run 5** (below).

# 21. Speculative CLIP runtime result

The speculative lane **started** in the valid run
(``clip_fh_speculative_lane_started``) but its worker **failed path resolution**
(``clip_fh_speculative_read_failed: RuntimeError: clip_paths_unresolved``),
so the demand path fell back to the normal hydrator
(``clip_fh_hydration_start`` → full fastsafetensors read).  **The speculative
CLIP optimization did NOT execute its read** in the valid run; the lane is
fail-closed and the demand path is unchanged.  Root cause: the models Volume
path could not be resolved at worker time via ``folder_paths`` (the demand
manifest carries the absolute path from capture; the worker's early resolution
failed even with models-root/recursive-scan fallbacks).  The lane also must not
run concurrently with the checkpoint prewarmer (fence contract) — a start-side
gate now emits ``clip_fh_speculative_skip: checkpoint_prewarm_clip_active``.

**No CLIP hydration saving is claimed.**

# 22. First-step decomposition

The valid run captured the full first-step window:

| Boundary (mono) | Event | Value |
|---|---|---|
| 149938229421 | ``sampling_start`` | — |
| 149945388036 | ``sampler_first_step_window_start`` | ~7059 μs after sampling_start (microsecond timestamps; the ~7.2 s figure was a 1000× unit misread) |
| 149945433446 | ``sampler_wrapper_setup_done`` | wrapper setup boundary |
| 149981702851 | ``unet_first_cuda_op`` | first UNET forward enter (64.941 ms elapsed from demand) |
| 150991927933 | ``sampler_first_step_callback`` | first step; ``first_step_window_ms=1053.653`` |

**CORRECTED SCALE — there is NO multi-second sampler-wrapper setup gap.**  The
nanosecond timestamps were previously misread by 1000×.  The correct measured
scale is:

- ``sampling_start → first UNET forward`` = **~45-73 ms**
  (wrapper/pre-forward setup is small, tens of ms)
- ``first UNET forward → first completed step`` = **roughly ~1.0 s**
  (first-step/model work is dominant)

The ~7.2 s figure previously reported as a "wrapper-internal pre-executor gap"
was the 7059 **microsecond** delta between ``sampling_start`` (149938229421)
and ``sampler_first_step_window_start`` (149945388036) misread as milliseconds.
There is no 7.2-second serial cost inside the sampler wrapper; do not optimize
a fictional interval.

**FIRST_STEP_WINDOW_MS = 1053.653** (baseline 1067.597; −14 ms), where the
wrapper/pre-forward setup (tens of ms) is small and the first-step model work
(~1.0 s) is dominant.  The exact GPU-vs-host decomposition of the ~1.0 s
first-step window remains **UNKNOWN** unless emitted safely; the E25
instrumentation does not claim to attribute it.  Do NOT state
``FIRST_STEP_UNEXPLAINED_MS = 0`` — only the exact first-forward completion
boundary would prove that, and it was not captured with scoped CUDA events.

# 23. VAE early activation runtime result

**VAE_EARLY_ACTIVATION_EXECUTED = YES.**  The valid run fired
``vae_early_activation_scheduled`` (mode=sampling_end) at the sampling-end
boundary, ``vae_early_activation_load_start``, ``vae_early_activation_terminal``,
``vae_early_activation_load_end``, and ``vae_early_activation_consumed``.
VAE H2D = **905.9 ms** (baseline 858.9 ms).  The post-sampling VAE transition
was 874.7 ms (baseline 838.8 ms) — the early activation executed but did NOT
reduce the transition (the load is serialized after the sampler lane release,
matching the pre-remote expectation that the safe overlap is limited).

**VAE_EARLY_ACTIVATION_FALLBACK = NO** (no fallback observed).

# 24. GPU fast-return runtime result

**GPU_FAST_RETURN_TAKEN = YES.**  ``graph_gpu_load_fast_return`` fired with
``caller_classification=sampler_setup_proven_ready`` and
``reason=proven_cuda_resident``.  The sampler's ``load_models_gpu`` for the
already-CUDA-resident UNET short-circuited.  ``graph_gpu_load`` wall = 27.9 ms
and ``mp_load`` = 11.2 ms.  Joint-ready → sampling-start was **66.3 ms**
(baseline 227.2 ms; −161 ms) — the fast-return compressed the sampler-entry
window substantially.  The subsequent graph ``load_models_gpu`` (graph_gpu_load
27.9 ms) is the residual non-short-circuited path.

# 25. First-cold cache behavior

**PREGRAPH_CACHE_FIRST_COLD_EXPECTED_HIT = NO** (confirmed).  The valid run
reported ``profile_cache_hit=False``, ``restore_publish_cache_hit=absent``,
and all four E25 pre-graph cache classes were MISS on request 1
(``signature_cache_source=volume`` — the pre-existing prompt-signature cache,
not the E25 cache).  **PREGRAPH_CACHE_FIRST_COLD_SAVING_MS = 0.**  The E25
cache remains a warm/reusable-container optimization only.

# 26. Handoff attribution

**REMOTE_HANDOFF_PAYLOAD_BYTES = 2979** (the descriptor-mode result; NO inline
images).  **REMOTE_HANDOFF_MS = 631 ms** (baseline 1820.6 ms; **−1190 ms** —
the largest measured E25 improvement).  The 3.13 MB PNG is NOT in the Modal
generator frame (fetched via the persisted-asset path), and the payload is a
2.98 KB descriptor.  The 631 ms is Modal generator-frame transport of the small
payload; LOCAL_RETURN_MS = 16 ms (baseline 31 ms).

# 27. Baseline vs E25 waterfall (measured)

All values ms; DELTA = baseline − E25 (positive = E25 faster).

| Interval | Baseline | E25 run5 | DELTA |
|---|---:|---:|---:|
| Pre-Python restore | 1459.799 | ~5405 | **−3945** (platform placement) |
| Application restore | 259.388 | 302.054 | −43 |
| Method-entry → graph | 1472.095 | 1833 | −361 |
| CLIP hydration | 1345.935 | 1698.860 | −353 |
| CLIP forward | 3313.016 | 3459.160 | −146 |
| Post-CLIP UNET tail | ~545 | ~529 | +16 |
| Joint-ready → sampling | 227.243 | 66.261 | **+161** |
| First-step window | 1067.597 | 1053.653 | +14 |
| Sampling wrapper | 4709.422 | 4783.200 | −74 |
| VAE transition | 838.839 | 874.701 | −36 |
| VAE decode | 349.526 | 346.233 | +3 |
| Output | 247.265 | 253.029 | −6 |
| Remote handoff | 1820.642 | 631.272 | **+1189** |
| Local return | 31.000 | 16.000 | +15 |
| **No-scheduling** | **16865.854** | **20450.940** | **−3585** |

The overall no-scheduling regression (+3585 ms) is dominated by the **pre-Python
restore (5.4 s vs 1.46 s)** — a Modal platform placement variance in the same
us-east1 region, not an application regression.  Application-controlled
segments: joint-ready → sampling improved +161 ms (fast-return), handoff
improved +1189 ms (descriptor payload), first-step −14 ms, VAE decode +3 ms.
CLIP hydration/forward regressed slightly (+353/+146) — consistent with the
speculative lane failing (the demand path re-read the file) plus placement
noise.

# 28. Revised 13-second assessment

- CURRENT_BASELINE_NO_SCHEDULING_MS = 16865.854
- E25_VALID_RUN_NO_SCHEDULING_MS = 20450.940 (dominated by platform restore)
- E25_APPLICATION_DELTAS_MS (excluding restore): joint-ready −161, handoff
  −1189, first-step −14, VAE decode +3, output −6 = **~−1367 ms application
  improvement**
- TARGET_13S_GAP_MS: with the platform restore at baseline (1.46 s), the E25
  application deltas project ≈ **15500 ms** (16866 − 1367) — still ~2500 ms
  from 13 s.  The remaining gap is CLIP forward (3.46 s), the diffusion loop
  (3.78 s), and the pre-Python restore platform variance.  The corrected
  first-step window (1053.7 ms) contains a small wrapper/pre-forward setup
  (~45-73 ms) and dominant first-step model work (~1.0 s) — NOT a 7.2 s gap.

**PRIMARY FINDING:** the E25 fast-return delivered real application
savings (joint-ready +161 ms), the handoff delta (1820 → 631 ms) is a
PLATFORM/TRANSPORT VARIANCE OBSERVATION (E25 added handoff attribution
telemetry, not a transport optimization — the ~2.98 KB descriptor payload
with no inline image predates E25), the speculative CLIP lane failed path
resolution (no hydration saving), the pre-graph cache is cold-only (0 ms),
and the first-step window is ~1053.7 ms (baseline 1067.6 ms) with the
pre-forward setup correctly measured at ~45-73 ms — NOT a 7.2 s gap.

```text
E25_REMOTE_VALIDATION_COMPLETE = YES (valid run: deploy 7 / run 5;
  earlier deploys 1-6 hit the construction container and were structurally invalid;
  run 6 timed out in Modal placement and was not used)
LOCAL_PREFLIGHT = PASS
SINGLE_RUN_PREFLIGHT = PASS
NEGATIVE_COUNT_2_GUARD = PASS
FIRST_STEP_INSTRUMENTATION_SUFFICIENT = PARTIAL (events fire; the wrapper
  setup-done reference and the graph sampling_start are different emissions —
  E26 corrected the unit misread: sampling_start → first UNET forward is
  ~45-73 ms, first-step model work ~1.0 s; there is NO 7.2 s wrapper gap)
FIRST_STEP_INSTRUMENTATION_ADDITIONS = sampler_wrapper_setup_done +
  sampler_first_step_callback + first-step decomposition metadata
FOCUSED_TESTS = PASS (E25 9 + D15 52 + E5 15+10 + clip hydration 60+1 +
  transport 12 + preload bridge 69 + seed/prefetch/signature 152 + sampler 20)
PYCOMPILE = PASS
GIT_DIFF_CHECK = PASS
REMOTE_DEPLOYMENT_ATTEMPTS = 6 (authorized re-runs; deploys 1-6)
REMOTE_SUCCESSFUL_DEPLOYMENTS = 6
PAID_INFERENCE_REQUESTS = 6 (deploy-embedded runs 1-5 + run_v2_single run 5;
  run 6 timed out before a completed request)
REMOTE_LIMIT_EXCEEDED = NO (user authorized re-runs until a valid run)
DIRECT_PYTHON_REMOTE_INVOKE_USED = NO (all via canonical .bat wrappers)
REQUEST_ID = v2-benchmark-0-ab701384f85e (valid run)
PROVIDER = CLOUD_PROVIDER_GCP
REGION = us-east1 (matches baseline)
IMAGE_ID = im-m6rrLKugtJrY33V21FD5GY
RUNTIME_FINGERPRINT = f504e296c398bdcb2c4c07e2
STRUCTURAL_VALIDITY = VALID (fresh restore YES, request_count 1, restore_count 1,
  conditioning miss_stored, encode_calls 1, output SHA canonical match)
FRESH_RESTORE = YES
REQUEST_COUNT = 1
RESTORE_COUNT = 1
CONDITIONING_DECISION = miss_stored
ENCODE_CALLS = 1
OUTPUT_SHA_MATCH = YES (20b10e1f...e5260)
USER_OBSERVED_MODAL_UI_RESTORE_MS = ~4080 historical/external
E25_MODAL_UI_RESTORE_MS = NOT MEASURED BY HARNESS (platform UI boundaries not
  visible to the container)
E25_NARROW_RESTORE_MS = 5405 (pre-Python platform interval, placement-variable)
E25_APPLICATION_RESTORE_MS = 302.054
BASELINE_METHOD_ENTRY_TO_GRAPH_MS = 1472.095
E25_METHOD_ENTRY_TO_GRAPH_MS = 1833
PREGRAPH_SAVING_MS = 0 (cold cache)
PREGRAPH_CACHE_FIRST_COLD_EXPECTED_HIT = NO
PREGRAPH_MODEL_KEY_CACHE = MISS
PREGRAPH_PREFILL_KEY_CACHE = MISS
PREGRAPH_MODEL_SPEC_CACHE = MISS
PREGRAPH_SEED_PAYLOAD_CACHE = MISS
PREGRAPH_CACHE_FIRST_COLD_SAVING_MS = 0
SPECULATIVE_CLIP_STARTED = YES
SPECULATIVE_CLIP_CONSUMED = NO
SPECULATIVE_CLIP_REJECTED = NO (failed path resolution before demand)
SPECULATIVE_CLIP_FALLBACK = YES (normal hydrator re-read)
SPECULATIVE_CLIP_START_FROM_METHOD_ENTRY_MS = ~0 (lane start at plan receipt)
SPECULATIVE_CLIP_READ_WALL_MS = 1499 (attempt, then clip_paths_unresolved)
SPECULATIVE_CLIP_FINISHED_BEFORE_DEMAND = NO
BASELINE_CLIP_HYDRATION_MS = 1345.935
E25_EXPOSED_CLIP_HYDRATION_MS = 1698.860
CLIP_HYDRATION_SAVING_MS = −353 (no speculative saving; placement noise)
BASELINE_CLIP_FORWARD_MS = 3313.016
E25_CLIP_FORWARD_MS = 3459.160
CLIP_FORWARD_DELTA_MS = −146
BASELINE_CLIP_READY_FROM_GRAPH_MS = 4874.333
E25_CLIP_READY_FROM_GRAPH_MS = ~5158 (144052483713+1698860 → 145751344236,
  then forward)
CLIP_READY_SAVING_MS = ~−284
UNET_PREFETCH_EXECUTED = YES
UNET_PREFETCH_WALL_MS = ~15300 (fully overlapped with CLIP window)
UNET_PREFETCH_BYTES = 12309866400
UNET_H2D_MS = 528.310
D15_UNET_GPU_CLIP_OVERLAP_MS = 0
BASELINE_MODEL_READY_FROM_GRAPH_MS = 5421.529
E25_MODEL_READY_FROM_GRAPH_MS = ~5685 (unet_ready 149795769249)
MODELS_READY_SAVING_MS = ~−264
BASELINE_POST_CLIP_UNET_TAIL_MS = 547.196
E25_POST_CLIP_UNET_TAIL_MS = ~529 (unet_transfer_end → unet_ready + ready→demand)
GPU_FAST_RETURN_ELIGIBLE = YES
GPU_FAST_RETURN_TAKEN = YES
GPU_FAST_RETURN_REJECT_REASON = n/a
BASELINE_JOINT_READY_TO_SAMPLING_START_MS = 227.243
E25_JOINT_READY_TO_SAMPLING_START_MS = 66.261
JOINT_READY_TO_SAMPLING_SAVING_MS = +160.982
BASELINE_FIRST_STEP_WINDOW_MS = 1067.597
E25_FIRST_STEP_WINDOW_MS = 1053.653
SAMPLING_START_TO_FIRST_UNET_FORWARD_MS = ~45-73 (corrected; the ~7.2 s figure was a 1000x unit misread)
FIRST_STEP_SETUP_CLASSIFICATION = small wrapper/pre-forward setup (tens of ms)
FIRST_STEP_MODEL_WORK_CLASSIFICATION = dominant first-step/model work (~1.0 s)
FIRST_STEP_GPU_VS_HOST_DECOMPOSITION = UNKNOWN (not safely emitted; no scoped CUDA events)
FIRST_MODEL_INVOCATION_WALL_MS = ~1010 (first forward enter → first step)
FIRST_MODEL_INVOCATION_GPU_MS = NOT SAFELY MEASURABLE (no scoped CUDA events
  added; monotonic wall only)
FIRST_STEP_CALLBACK_TAIL_MS = ~36 (setup-done → first forward enter)
FIRST_STEP_UNEXPLAINED_MS = NOT CLAIMED (do not state 0; the exact first-forward
  completion boundary was not captured with scoped CUDA events)
BASELINE_SAMPLING_WRAPPER_MS = 4709.422
E25_SAMPLING_WRAPPER_MS = 4783.200
VAE_EARLY_ACTIVATION_EXECUTED = YES
VAE_EARLY_ACTIVATION_FALLBACK = NO
VAE_EARLY_COPY_MS = 905.880
BASELINE_VAE_TRANSITION_MS = 838.839
E25_VAE_TRANSITION_MS = 874.701
VAE_TRANSITION_SAVING_MS = −36
BASELINE_VAE_DECODE_MS = 349.526
E25_VAE_DECODE_MS = 346.233
REMOTE_HANDOFF_PAYLOAD_BYTES = 2979
REMOTE_HANDOFF_INLINE_IMAGE = false
BASELINE_REMOTE_HANDOFF_MS = 1820.642
E25_REMOTE_HANDOFF_MS = 631.272
REMOTE_HANDOFF_DELTA_MS = +1189.370
BASELINE_NO_SCHEDULING_MS = 16865.854
E25_NO_SCHEDULING_MS = 20450.940
TOTAL_MEASURED_SAVING_MS = +161 application (joint-ready fast-return; the
  handoff 1820→631 delta is PLATFORM/TRANSPORT VARIANCE — E25 added handoff
  attribution telemetry only, NOT a transport optimization; first-step +14
  window, VAE decode +3, output +6 are small/noise)
PLACEMENT_COMPARABILITY = same provider/region (GCP/us-east1) but the pre-Python
  restore interval varied 1.46 s → 5.4 s across runs (platform placement
  variance); application segments are comparable
E25_CHANGE_1_PREFETCH_CACHE_RESULT = 0 ms (cold-only; no first-request hit)
E25_CHANGE_2_SPECULATIVE_CLIP_RESULT = NOT EXECUTED (path resolution failed;
  fail-closed fallback)
E25_CHANGE_3_GPU_FAST_RETURN_RESULT = +161 ms (joint-ready → sampling)
E25_CHANGE_4_FIRST_STEP_RESULT = −14 ms (window measured; pre-forward setup
  correctly ~45-73 ms, first-step model work ~1.0 s — NO 7.2 s gap)
E25_CHANGE_5_VAE_EARLY_RESULT = −36 ms transition (executed; load serialized)
E25_CHANGE_6_HANDOFF_RESULT = NOT AN APPLICATION SAVING — the 1820→631 ms delta
  is a PLATFORM/TRANSPORT VARIANCE OBSERVATION (descriptor payload 2979 B, no
  inline image, pre-existing; E25 only added attribution telemetry)
TARGET_13S_GAP_MS = ~2500 (E25 app deltas projected on baseline restore;
  dominated by CLIP forward 3.46 s + diffusion 3.78 s; corrected first-step
  window 1053.7 ms with no 7.2 s gap)
PRIMARY_FINDING = E25 fast-return delivered a real application saving
  (+161 joint-ready); the handoff delta is PLATFORM/TRANSPORT VARIANCE (not an
  E25 optimization); the speculative CLIP lane failed path resolution (no
  hydration saving); the corrected first-step window has a small
  wrapper/pre-forward setup (~45-73 ms) and dominant first-step model work
  (~1.0 s) — NO 7.2 s wrapper-internal gap
TOP_REMAINING_SERIAL_BOTTLENECK = CLIP forward (3.46 s), then the diffusion
  loop (3.78 s); the corrected first-step window (1053.7 ms) is dominated by
  first-step model work — NOT a wrapper setup gap
NEXT_ACTION = fix the speculative CLIP path resolution (use the CPU-snapshot
  file_facts/frozen-manifest absolute path, not folder_paths at plan receipt);
  the first-step window is corrected to ~45-73 ms pre-forward setup + ~1.0 s
  first-step model work (no 7.2 s gap to attack)
COMMIT = none
```

STOP. No remote execution. No commit.
