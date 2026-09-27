# V2 Batch C6 — Production Pinned-Ring Loader Design

Date: 2026-08-15
Mode: STRICT DESIGN / READ-ONLY. No source modified, nothing deployed, no Modal runs, no commit.
Basis: C6 feasibility audit + I-1/I-2 probe + I-3 config/overlap gate + pinned-ring feasibility microprobe (all accepted).

Decision under review: implement a **default-OFF production pipeline** (flag `COMFYMODAL_V2_UNET_PINNED_RING`) that replaces, when eligible, the UNET fast-disk read→bind→bulk-H2D sequence with an incremental read→stage→async-DMA 2-buffer pinned ring. The existing fast-disk path and the authoritative ComfyUI loader remain byte-identical when the flag is off or eligibility fails.

---

## 1. Final dataflow diagram

```
plan receipt / _load_unet(model_key)
   │
   ▼
[ELIGIBILITY GATE]  header parse + family check + pinned alloc probe + flag
   │ eligible                                  │ ineligible / flag off
   ▼                                           ▼
┌─ PIPELINE (replacement of the UNETLoader    ┌─ existing path: _invoke_original
│  invocation inside _load_unet)              │   → UNETLoader.load_unet
│                                             │   → comfy.sd.load_diffusion_model
│ 1. header parse (JSON, no payload)          │   → load_torch_file (full read)
│ 2. allow_fp16 value probe (7,680 B)         │   → load_diffusion_model_state_dict
│ 3. meta-sd config derivation                │   → fast-disk window (defer/replay)
│    (same comfy fns as authoritative)        │   → bind(assign=True) + bulk to(cuda)
│ 4. config parity vs family reference        │   → normal_loader_ready → future
│ 5. model = model_config.get_model(meta_sd)  │   (UNCHANGED — this is the fallback
│ 6. ModelPatcher(model, load, offload)       │    and the default)
│ 7. param_name_map = named_parameters        │
│ 8. exact key↔param match check              │
│ 9. per-wave loop (RING_DEPTH=2):            │
│      get_tensor(key)        ← page-in      │
│      pin_buf[slot] ← tensor (sync copy)    │
│      reuse-wait on slot DMA event          │
│      dest[key] = empty_like(cuda)          │
│      async dest[key].copy_(pin_view)       │
│      param.data = dest[key]                │
│ 10. buffers (non-sd) via model.to(target)  │
│ 11. torch.cuda.synchronize()  (final sync) │
│ 12. emit read/get_model/bind/H2D spans     │
│ 13. normal_loader_ready → future → graph   │
│ 14. sampler proceeds unchanged             │
└────────────────────────────────────────────┘
        ANY failure before (13) → discard partial state → _invoke_original (clean)
```

All of this runs inside the existing UNET lane worker thread; the future publication, `normal_loader_ready`, `graph_unet_join_or_adopt`, and sampler-lane gates are untouched.

## 2. Exact pipeline ordering (with invariants)

Entry: `V2LoaderBridge._load_unet` (model_preload.py, ~11229; current ~12560 area). Before calling `_invoke_original`, if `_ring_pipeline_enabled()` and the pre-gate passes, run the pipeline; else `_invoke_original` exactly as today.

Ordering invariants (each is a hard rule):

- **I1 Header-before-payload**: the safetensors header (8-byte length + JSON) is read before any tensor payload. Header availability is proven by the I-3 probe.
- **I2 Value-probe-before-config**: `allow_fp16` (only value-dependent input, ZImage dim==3840) is resolved from the 7,680 B `layers.{n-2}.ffn_norm1.weight` byte range before the candidate config is finalized. If the key is absent, the value probe is `None` and parity must still hold with the probe-absent derivation; else ineligible.
- **I3 Config-parity-before-construction**: the header-derived config (same comfy functions on meta-sd) must match the family reference on every correctness-relevant field (I-3 parity suite) before `get_model` runs. This is the pre-construction fail-closed gate; the runtime post-load parity probe remains as a permanent regression check on fallback/probe runs.
- **I4 Construction-needs-no-payload**: `get_model(meta_sd)` must not read tensor values. Verified for ZImage/Lumina2 (`supported_models.py:1159` returns `model_base.Lumina2(self, device=device)` without touching sd). The eligibility gate limits the family list to families so verified; any new family requires the same verification before inclusion.
- **I5 Key-set↔param-name exact match**: after construction, `set(model.named_parameters())` must exactly equal the prefix-stripped sd key set (identity transform). Any missing/extra key → ineligible/fallback. This is the decisive topology-drift check (I-3 transform classification must be INDEPENDENT; ZImage = identity, 453/453).
- **I6 Read-before-stage**: `get_tensor(key)` (page-in) precedes the mmap→pinned copy for the same key; page-in and staging are serial per key (single worker thread), and that CPU work is the pipeline's critical path — DMA hides under it via the ring.
- **I7 Stage-before-DMA**: a pinned buffer is fully written before its async DMA is enqueued; a buffer is never written while its previous DMA is pending (reuse wait).
- **I8 DMA-async-per-wave**: all per-key `copy_(..., non_blocking=True)` enqueues of one wave are bracketed by one CUDA event pair; no `torch.cuda.synchronize()` inside the wave loop (the whole point of the ring).
- **I9 Bind-after-enqueue, invisible-until-sync**: `param.data = dest[key]` occurs after the DMA enqueue for that key. The partially-bound model is never published, never joined, never sampled: the future is set only after the final sync (I10). The graph join and sampler gates are unchanged and fire post-publication; therefore partial-model visibility is impossible (same guarantee the current deferred-to window relies on).
- **I10 Final-sync-before-publication**: exactly one `torch.cuda.synchronize()` after the last wave (plus the existing per-module syncs inside `ModelPatcher.load` which run later and are unchanged). `normal_loader_ready` and future publication happen after it.
- **I11 Fallback-is-fresh**: any failure before publication discards the partial model/pipeline state entirely and invokes `_invoke_original` (authoritative loader) on a fresh call. No partial pipelined state leaks (see §10).
- **I12 TWO-LANE/mutation semantics unchanged**: the pipeline runs inside the UNET prep lane; the same single-flight future is published; the pipeline's DMA is not a `load_models_gpu` mutation and stays outside the MutationLane exactly like today's fast-disk H2D.

## 3. Page-in + staging behavior (Q2)

- **Producer stays `safe_open.get_tensor`.** Raw byte-range loading is rejected: the SafeOpen path is validated end-to-end (I-1 series, bind semantics, output SHA), and direct raw-file loading would duplicate safetensors parsing and storage-identity logic for no measured benefit. The header byte-range read is used ONLY for the 7,680 B value probe.
- **Where page-in occurs**: on first touch of each mmap-backed tensor during `get_tensor` (measured as the I-1 per-tensor materialization wall, ~4.4–5.7 GB/s effective for large tensors, bursty at the head). Pages then remain resident; the mmap→pinned copy re-reads resident pages (~60 GB/s measured).
- **Lifetime**: the sd tensors (mmap-backed views) must stay referenced until the final sync (I10). safetensors keeps the mapping alive via tensor storage (proven: today's H2D replay reads them after the file context closes). After the final sync the model owns CUDA dests; the sd references are dropped and the mmap can be released.
- **Pipeline vs probe difference (explicit)**: the ring probe staged already-resident pages post-read; production stages during the read (page-in inside get_tensor). The extrapolation accounts for this by keeping the full I-1 read wall in the CPU critical path (see §13).

## 4. Ring depth (Q4)

- **RING_DEPTH = 2**, a fixed constant, not a tuning surface initially.
- Evidence: 1 buffer serializes (eff 0.0, measured); 2 buffers measured best (wall 30.0 ms vs 47.0/41.6, eff 0.264); 3 buffers regressed (41.6 ms, eff 0.0) — likely event/alloc overhead without added overlap, since the CPU staging (the bottleneck) is already fully covered by one alternate buffer.
- The design re-verifies 2-vs-3 in the first remote validation run (telemetry includes ring reuse waits and wall); if 3 demonstrably wins there, a follow-up design decision would be required — it is NOT a runtime tuning surface.

## 5. Buffer sizing / shape handling (Q5)

- **Per-slot typed flat pinned buffers** (`torch.empty(total_bytes // itemsize, dtype, pin_memory=True)`), keyed by slot; grow-to-largest within a hard cap.
- **Why flat+typed**: avoids the probe's per-tensor shape-mismatch failure; waves are dtype-uniform (eligibility requires uniform sd dtype == param dtype — inherited from the existing bind guard), so one typed buffer per slot suffices.
- **Capacity rule**: `slot_cap = WAVE_TARGET_BYTES` (default 64 MB); a wave larger than the cap (single huge tensor) reallocates the slot to that tensor's size, bounded by `MAX_WAVE_BYTES` (128 MB). Reallocation replaces, never accumulates. **Max pinned memory = RING_DEPTH × MAX_WAVE_BYTES ≈ 256 MB** (default 128 MB).
- **Alignment**: torch pinned allocations are page-aligned; per-key views at numel offsets are dtype-aligned for contiguous tensors; eligibility requires contiguous sd tensors (the existing `force_channels_last`/contiguity guards already fail closed for non-contiguous layouts).
- **Copy/view semantics**: `pin_buf[slot][off:off+n].view(shape).copy_(tensor, non_blocking=False)` — synchronous pageable→pinned (measured ~0.8–1.6 ms per 78.6 MB ≈ 50–100 GB/s). DMA reads the same pinned view with `non_blocking=True`.
- **Cleanup**: after the final sync, pinned buffers and the (transient) sd references are freed; `torch.cuda.empty_cache()` once (guarded). No pinned memory is retained between requests.

## 6. Incremental bind semantics (Q6)

- **Mechanism chosen: `param.data = dest[key]`** (Option A-lite: bind CPU-then-replace is unnecessary). The per-key sequence is: enqueue async `dest[key].copy_(pin_view, non_blocking=True)` → `param.data = dest[key]`. `param.data` replacement:
  - preserves the **Parameter object identity** (module `_parameters` dict unchanged — more conservative than today's `model.to(cuda)`, which via `Module._apply` replaces Parameter objects with new ones);
  - preserves `requires_grad`; the forward path reads `.data`-bound storage, identical semantics;
  - is the exact mechanism `comfy.utils.copy_to_param` and `ModelPatcher.patch_weight_to_device` use for weight updates.
- **Parameter identity expectations**: ModelPatcher resolves weights **lazily by key** at `load()` time (`get_key_weight(self.model, key)` in `patch_weight_to_device`, model_patcher.py:846; `_load_list` iterates `named_modules`/`named_parameters` at load time, :891-926). It never caches Parameter objects at construction. `backup` entries are created at first patch application (post-publication), copying the then-current weight to `offload_device` — identical to today since offload==cuda and weights are already cuda. Therefore: **Parameter object identity does not matter to ModelPatcher; .data replacement fully satisfies its expectations**; the final object/patcher semantics match the fast-disk path.
- **When visible**: parameters are only visible to ModelPatcher.load (post-publication), the graph join, and the sampler — all gated after the final sync.
- **Avoiding the temporary CPU-bound state entirely**: yes — dests are created directly on cuda; the CPU sd tensors are never bound as params; they exist only as staging sources and are dropped after the final sync.
- **Non-sd parameters/buffers**: after the per-key loop, `model.to(target)` runs once (no-op for bound params; moves any remaining buffers/params) — preserving the current path's full-module device semantics.

## 7. CUDA stream/event design (Q7)

- **Stream**: the default (current) stream for all ring DMAs. Rationale: the ring microprobe measured 0.015 ms host issue on the default stream; ModelPatcher.load and all downstream ops use the current stream, so default-stream ordering makes the final state visible to them without explicit stream handshakes. A dedicated H2D stream is not selected (no measured benefit; adds a `wait_stream` publication step).
- **Events**: one event pair per **wave** (not per tensor) — 2×~193 events for the whole model vs 453+ today; reuse waits check per slot.
- **Buffer-reuse wait**: before staging into slot s, if `ev_pending[s]` exists (a wave from 2 waves ago), `ev_pending[s].synchronize()` — this waits only the DMA that read this slot's previous content; with the ring, it is usually already complete (measured reuse wait 0.007–0.54 ms).
- **Final synchronization**: one `torch.cuda.synchronize()` after the last wave, before publication. No per-tensor synchronize anywhere in the pipeline.
- **Sampler readiness**: unchanged gates — the future is published after the final sync; `graph_unet_join_or_adopt` and `_lane.acquire("sampler")` fire afterward exactly as today.

## 8. TWO-LANE / MutationLane (Q8)

- Pipeline executes inside the existing UNET prep-lane worker (`_load_unet`), replacing only the inner loader invocation. TWO-LANE file-level scheduling (UNET prep lane vs early-activation lane) is untouched.
- Same single-flight future (`prep.unet_future`), same `wait_unet` join, same `normal_loader_ready` emission point (after final sync), same `_LOADER_MISS` semantics.
- The ring DMA is not a `load_models_gpu` mutation — identical to today's fast-disk H2D, it stays **outside the MutationLane**. No new lock, no new lane, no new GPU-mutation race.

## 9. Failure and fallback (Q9)

**Fallback principle: at ANY failure before publication, discard the partial pipeline state and invoke the authoritative loader fresh (`_invoke_original`).** The partially constructed model object is NOT reused — it is dropped with the pipeline state; the fallback performs its own full read→config→get_model→bind→H2D through the existing fast-disk machinery.

| Failure point | Behavior |
|---|---|
| header parse / family unknown / pinned alloc probe fails | pre-gate → ineligible → `_invoke_original` |
| value probe fails | ineligible (allow_fp16 unresolved → config not certifiable) |
| config parity mismatch | ineligible (fail closed) |
| key↔param set mismatch | ineligible |
| `get_model` raises | ineligible |
| allocation failure (pinned or cuda) mid-pipeline | discard state (free pinned/dests, empty_cache), fallback |
| `get_tensor` raises | discard, fallback |
| staging copy / DMA enqueue raises | discard, fallback |
| unexpected tensor/key/dtype | discard, fallback |
| buffer state corruption (reuse-wait assertion) | discard, fallback |
| failure after some keys bound | **discard — do NOT reuse the partially bound model**; fresh `_invoke_original` (its own get_model creates a clean object). No partial pipelined state leaks: pinned buffers/dests freed, no param of the discarded object is referenced by anything published. |
| final sync raises | discard, fallback |

Fallback correctness note: because the fallback is a **fresh full load**, there is no need to reason about rebinding a half-moved object; the "legacy ordering preservation" machinery of `_fast_disk_handle_bind` remains intact for the normal path and is simply re-entered by `_invoke_original`.

## 10. Eligibility contract (Q10)

`pipeline_eligible` = ALL of:

1. `COMFYMODAL_V2_UNET_PINNED_RING` truthy (default OFF).
2. Fast-disk window active (record exists, status constructed; the existing `_fast_disk_guard_to` set: HIGH_VRAM, plain non-dynamic `comfy.model_patcher.ModelPatcher`, load==offload==target==cuda, no quant_config/custom_operations/fp8/force_channels_last, torch swap-module-params future disabled, model CPU-resident) — inherited verbatim.
3. Bind-guard set (uniform sd dtype == param dtype; sd entries plain CPU Tensors; prefix-matching keys; native assign==True) — inherited verbatim.
4. Model family in the verified list (initially ZImage/Lumina2) and header parse OK.
5. Value probe resolved (or provably absent without affecting supported dtypes).
6. Header-derived config parity MATCH (I-3 field set).
7. `process_unet_state_dict` classification INDEPENDENT (ZImage: identity).
8. Exact key↔param name set match after prefix strip.
9. Pinned staging availability proven by a 1 MB probe allocation.
10. CUDA available; target resolved.

Any unmet condition → `pipeline_eligible = false` → existing loader unchanged. The optimization is a narrow, guarded fast path, never a universal replacement loader.

## 11. ComfyUI-update compatibility (Q11)

- **Detection strategy**: the pipeline reuses the SAME comfy functions for config derivation (meta-sd) as the authoritative path, so detection changes are mirrored automatically; drift is caught by the hard gates: (a) config parity (I-3 suite), (b) key↔param exact match (any topology/`process_unet_state_dict` change breaks it), (c) transform INDEPENDENT classification, (d) uniform-dtype guard.
- **Fail-closed contract**: any gate failure → ineligible → authoritative loader. The pipeline can never silently produce a different model: if ComfyUI changes config derivation, model topology, `process_unet_state_dict`, ModelPatcher semantics, or cast/device behavior in a way that alters the header-derived expectation, one of the gates trips and the optimization disables itself.
- **Permanent regression tests (must remain)**: I-3 config parity suite (config_class, unet_config, supported dtypes, params, weight_dtype, unet_dtype, manual_cast, module count); transform identity/INDEPENDENT classification; key↔param exact-match; output-SHA regression (deterministic workflow); eligibility fallback-count telemetry assertion (pipeline runs only when eligible; fallback paths emit reasons).

## 12. Telemetry contract (Q12)

One lean event per load, `unet_pinned_ring_pipeline` (phase=restore), plus the existing span events (read/get_model/bind/H2D) emitted by the pipeline itself so the waterfall stays reconcilable:

- eligibility verdict + fallback reason (or `eligible`)
- header parse wall, value-probe wall, config-derivation wall
- read/page-in wall (get_tensor loop), staged bytes, staging wall
- DMA wall (event elapsed, final wave), ring reuse-wait total, per-wave reuse-wait max
- overlap evidence: CPU-stage-end vs previous-DMA-end (bounded aggregate, not per-tensor)
- final pipeline wall, serial-equivalent estimate, measured saving
- total bytes/tensors, waves, final sync wall, fallback count

No per-tensor series in production (the 453-entry I-1/I-2 traces stay behind `COMFYMODAL_V2_UNET_READ_H2D_PIPELINE=probe`, which is a separate measurement flag).

## 13. Expected performance model (Q13)

Healthy reference: current read→GPU-ready chain ≈ **4.605 s** (read 1.624 + head 0.514 + H2D 2.468).

Pipeline critical path (single worker thread):

| Segment | ms (healthy) | ms (slow host) |
|---|---|---|
| header parse + value probe + config derivation | ~8 | ~12 |
| get_model (moves before the read; no longer post-read serial) | 370–475 | 475–520 |
| page-in (I-1 read wall, unchanged — page-in is the dominant CPU cost) | 1535–1624 | 2175 |
| mmap→pinned staging copies (~12.31 GB @ ~60 GB/s) | ~205 | ~230 |
| ring/wave overhead (~193 waves × ~0.1 ms) + reuse waits | ~25 | ~40 |
| DMA (hidden under CPU; device 237 ms) | hidden | hidden |
| final sync + model.to(target) + spans | ~15 | ~20 |

- **optimistic ≈ 2.15–2.35 s → saving ≈ 2.25–2.45 s**
- **expected ≈ 2.4–2.6 s → saving ≈ 2.0–2.2 s**
- **conservative ≈ 2.9–3.2 s (slow-host basis) → saving ≈ 1.4–1.7 s vs the healthy reference; ≥ ~1.2 s even on slow hosts vs their own 5.38 s chain**

The earlier probe-era conservative 1.2–1.4 s is **improved**, not preserved blindly: the production design moves construction (get_model) off the post-read serial path (header config) and removes the entire bulk-H2D phase (2.47 s), while adding only the pinned staging copy (~0.2 s). The 300 ms threshold is exceeded with wide margin on the conservative bound.

## 14. Memory / cost impact (Q14)

- Pinned host max: RING_DEPTH × MAX_WAVE_BYTES ≈ **128 MB** (default 64 MB waves; cap 256 MB worst case).
- Temporary GPU: the per-key dest tensors **become the model parameters** (12.31 GB) — identical to today's cuda copies; no extra flat GPU staging buffer is retained.
- Duplicate CPU payload at any instant: the sd (12.31 GB, same as today — it is the staging source until bound) + ≤1 wave in pinned (≤64 MB).
- Snapshot size: none (pipeline runs at graph time; production config excludes UNET from the CPU snapshot).
- Persistent runtime memory: none (pinned freed post-load; dests become params and are released with the model).
- Cleanup: guarded `del` + `torch.cuda.empty_cache()` once after final sync / on every fallback.

## 15. Implementation surface (Q15)

**Custom-node-only: `comfymodal_runtime/model_preload.py` + `tests/test_c6_read_h2d_probe.py`.** No ComfyUI core edits. If any future requirement forces a core change, STOP and treat it as a new architectural decision.

| Function (new or changed) | Responsibility |
|---|---|
| `_ring_pipeline_enabled()` | env gate `COMFYMODAL_V2_UNET_PINNED_RING` (default off; "1" only; reject others) |
| `_ring_pre_gate(model_key, path, lane)` | header parse, family list, pinned 1 MB probe, fast-disk guard set (reuse `_fast_disk_guard_to` conditions) |
| `_ring_derive_and_verify(path, model_config_ref)` | value probe + meta-sd config derivation + parity compare (reuse `_c6_*` I-3 helpers, made flag-independent) |
| `_ring_build_model(model_config)` | `get_model(meta_sd, "")` + ModelPatcher ctor mirroring sd.py:2012-2013 |
| `_ring_key_map(model, sd)` | param-name set, exact-match check, prefix strip |
| `_ring_wave_build(keys, sd, target_bytes)` | batching policy (§5): pack ≤64 MB, single huge tensor = own wave, preserve read order |
| `_ring_stage(wave, slot)` | pinned copy_ into flat slot buffer + reuse-wait |
| `_ring_dma_and_bind(wave, slot, model)` | per-key dest alloc + async copy_ enqueue + `param.data = dest` + wave event pair |
| `_ring_finalize(record, model, target)` | `model.to(target)`, final sync, span-event emission (read/get_model/bind/H2D), normal_loader_ready, future publication (reuse existing tail of `_load_unet`) |
| `_ring_fallback(reason)` | discard state, free pinned/dests, `_invoke_original` fresh |
| `_load_unet` (changed) | branch: pre-gate → pipeline → else `_invoke_original`; telemetry emit |
| `_fast_disk_*` | unchanged |

## 16. Local test plan

1. Flag off → pipeline code never runs; byte-identical path (assert no new events, no pinned allocs).
2. Pre-gate failures → ineligible reasons (bad flag value, family unknown, header missing, pinned probe failure, non-HIGH_VRAM, dynamic patcher, quant present).
3. Config parity gate: mutated header/params → ineligible.
4. Key↔param mismatch (rename a key) → ineligible.
5. Wave batching policy: packing ≤64 MB, single-huge-tensor wave, order preservation, dtype-uniform waves.
6. Ring mechanics with fake torch: slot reuse wait ordering (no write while DMA pending), grow-to-largest realloc, bounded pinned allocs (≤2 slots), cleanup on success and failure.
7. Incremental bind: `param.data` rebinding preserves Parameter identity, requires_grad, module dict; ModelPatcher `get_key_weight` resolves final cuda tensors (mock comfy).
8. Failure injection at every stage (get_tensor, stage, dma, sync) → discard + fresh fallback; no partial state leaks (assert freed, model dropped, fallback invoked once).
9. Telemetry: one lean event, JSON-safe, no per-tensor series in production mode.
10. Regression set unchanged: C6 (81 tests), fast-disk, prefill overlap, critical path, clip prefill, local submission critical path, batch A/B/C acceptance, v2_ab_experiments.

## 17. First remote-validation plan

1. ONE deploy with `COMFYMODAL_V2_UNET_PINNED_RING=1` (probe flag OFF — production telemetry only) to the C6 shadow app.
2. ONE true-cold request (standing rule: stop after the first valid evidence-bearing run).
3. Required: Fresh YES; C1 identity healthy; B1 exact-match; one authoritative lifecycle (or one pipeline lifecycle with clean eligibility); **identical deterministic output SHA**; final model GPU-ready; zero fallbacks; waterfall local reconciliation OK.
4. Evidence: `unet_pinned_ring_pipeline` event (eligibility, walls, waves, reuse waits, overlap, saving vs serial-equivalent); verify ring depth 2 vs 3 question if telemetry suggests it.
5. No cohort.

## 18. Explicit implementation stop conditions

- Any ComfyUI core edit becomes necessary → STOP (new architectural decision).
- Fallback count > 0 on the validation run → STOP, diagnose (the pipeline must never degrade the authoritative path).
- Output SHA differs → STOP, diagnose.
- Conservative expected saving on the validation run < ~300 ms (e.g., page-in/staging contention collapses the overlap) → STOP, re-probe.
- Sampler/lane semantics change (TWO-LANE count, mutation-lane behavior, join order) → STOP.
- Eligibility rate collapses in practice (e.g., parity/guard drift) to < 20% of UNET loads → STOP and re-examine the gates.

---

## Decision

### READY TO IMPLEMENT

- Bounded entirely to the custom-node loader (`model_preload.py` + tests): no core ComfyUI changes required (verified: ZImage `get_model` reads no payload; ModelPatcher resolves weights lazily by key; bind guards inherited).
- Clean fail-closed fallback: fresh authoritative load on ANY failure before publication; no partial state leaks; existing fast-disk machinery untouched as the default and the fallback.
- Object/ModelPatcher semantics preserved: `param.data` rebinding keeps Parameter identity, satisfies lazy `get_key_weight` lookup and `backup` semantics; final sync before publication preserves all visibility gates.
- Conservative expected benefit ≈ 1.4–1.7 s (≥ 1.2 s even on slow hosts) — well above the ~300 ms threshold; the estimate is derived from measured page-in/staging/DMA rates, not the old 1.2–1.4 s assumption.

Not implemented in this task. Implementation requires a new decision point (per the standing gate) and the local-test + one-deploy/one-cold-run validation plan above.

## Remaining unknowns (all validation-time, none blocking)

1. Per-wave python overhead at 453-key scale in production (probe-measured 0.8 ms/chunk was instrumentation-inclusive; production loop is leaner — verify on the validation run).
2. Whether page-in during staged reads (vs the probe's post-read resident pages) alters the effective staging rate — accounted conservatively (full I-1 wall kept in the CPU path).
3. 2-vs-3-buffer question at production scale (3 regressed in the probe; re-check once via telemetry, not a runtime tuning surface).
4. Slow-host variance band (read 1.54–2.17 s across runs) — the conservative bound covers it.

---

## You asked for:
- An implementation-ready, read-only production design for a default-OFF pinned-ring UNET loader (dataflow, ordering, eligibility, batching, bind semantics, streams, fallback, compatibility, telemetry, performance/memory model, implementation map), plus a READY/NEEDS-MORE-PROBING/STOP classification.

## You should now manually check:
- **Classification: READY TO IMPLEMENT** — do NOT implement without a new explicit decision; the first implementation step is the local-test plan (§16) then one deploy/one cold run (§17).
- Verify the ZImage/Lumina2 `get_model` no-payload claim before writing code (supported_models.py:1159) — it is the linchpin of construction-before-read.
- Decide the initial family allow-list scope (start ZImage-only vs ZImage+Lumina2) — Lumina2 (dim 2304) has no allow_fp16 value probe; its parity path is simpler but must be verified separately.
- The `_c6_*` I-3 helpers must be refactored from probe-gated to always-available-with-call-site-gating — confirm no behavior change when both flags are off.
- Report file: `V2_BATCH_C6_PINNED_RING_PRODUCTION_DESIGN.md` (repo root). No source files were created or modified; no commit.
