# V2 Remaining-Optimization A/B Setup Report

**Date:** 2026-08-12
**Repo:** `comfyui-modal` custom node (working tree, current HEAD `e5483d5`)
**Task scope:** research, design, implement, and locally validate the experimental A/B framework for the five remaining V2 optimization lanes (UNET H2D, VAE overlap, PNG encoding, conditioning-cache LRU, restore memory query), plus the waterfall scheduling-denominator presentation change, remote-partial/final waterfall distinction, and deterministic benchmark result storage.
**Paid Modal runs performed: NONE. Deployments: NONE. Snapshots: NONE. Generations: NONE.**

---

# Executive readiness

| Experiment | Status | B implemented | Default OFF | Request-selectable | Deployment-selectable |
|---|---|---|---|---|---|
| 1 — UNET H2D | READY | pinned-staging chunked transfer | YES | YES | container env also works |
| 2 — VAE overlap | READY | early-start transfer-only overlap | YES | YES (offset via request env) | container env also works |
| 3 — PNG encoding | READY | compress_level=1 | YES | YES | container env also works |
| 5 — Conditioning-cache LRU | READY | async coalesced LRU touch | YES | YES | container env also works |
| 6 — Restore memory query | READY (causal saving unproven until A/B run) | snapshot-frozen total VRAM | YES | NO — deployment-level (restore precedes request selection) | YES |

All arms preserve exact output semantics, workflow, model, Sampling settings, CacheDiT behavior, snapshot composition, conditioning semantics, and output-delivery semantics. Every B path is explicitly gated and default OFF. Every applied arm emits `experiment_name`, `arm`, `effective_settings`, `implementation_version` via a `[v2.experiment]` log line and an `experiment_selection` trace event.

Local verification: **100 tests pass** across the new and existing suites (see Local verification).

---

# Current baseline

Measured evidence (unchanged by this task; reproduced in `V2_REMAINING_OPTIMIZATION_DIAGNOSTICS.md`):

- **UNET:** 12.31 GB, 454 storages, BF16, pageable source, pinned_frac 0.0, non_blocking False, default stream, `nn.Module.to(cuda)` path. H2D CPU wall 4151.3 ms / CUDA-event 4136.8 ms / 2.98 GB/s. Sampler waited ~995 ms (UNET readiness vs sampling_start −995 ms). UNET H2D overlapped ~4.14 s of degraded CLIP forward.
- **VAE:** ~167.6 MB, H2D ~554 ms, pageable, join wait ~41 ms, post-Sampling transition ~526 ms measured (historical ~837 ms). VAE GPU activation starts at/after Sampling completion.
- **PNG:** encode 620.7 ms total, PNG compression 605.8 ms (97.6%), PIL, compress_level 6, optimizer False.
- **Conditioning cache:** normal exact hit ~140–150 ms; pathological cold hit ~1.8–2.06 s. Foreground `_persist_lru_touch` performs filesystem/manifest work during a hit (manifest re-read + full atomic rewrite + 2 fsyncs). Payload read latency may dominate the pathological case (3.1 MB entry read ~1.84 s on the bad hit).
- **Restore:** decomposition coverage ~99.95%; gpu_state ~339 ms measured (incl. `get_total_memory` 236–339 ms), cuda_init ~183 ms measured, runtime_state/models variable.

---

# Step-3 coexistence

Step-3 work (plan validation proof, workflow hash recomputation, deployment identity, snapshot proof, exact parity gate, Gate-2 invalidation, fast-path certificate bypass) is **untouched**. This task did not modify `canonical_execution.py`, `contracts.py`, `runtime_bootstrap.py`, `__init__.py`, or any Step-3 test. No parity attempt was made during this task (source tree was allowed to change by design).

The trust gate continues to fail closed. The later benchmark deployment must be built from the exact final tree (see Source-tree freeze requirements) so the Step-3 deployment-identity parity can succeed on the first post-snapshot generation.

**Source-tree identity fields affected by this work** (expected):

| Identity field | Affected? | Why |
|---|---|---|
| `deployment_combined_hash` | **YES** | New modules (`v2_experiments.py`, `unet_pinned_staging.py`, `restore_memory_arm.py`, `experiment_result_store.py`) + edits to `model_preload.py`, `runtime_executor.py`, `clip_conditioning_cache.py`, `modal_app.py`, `comfyapp.py`, `v2_waterfall.py`, `tools/benchmark_v2_direct.py` |
| `custom_nodes_generation` | **YES** | Custom-node source tree changed |
| `registry_fingerprint` | likely NO (unchanged registry state; final determination at deploy time via Step-3 proof) | No registry/manifest changes made |
| `dependency_manifest_identity` | NO | No dependency/requirements changes (verified: no requirements/pyproject/setup.py diffs) |

---

# Source-tree freeze requirements

For Step-3 identity parity during the future campaign:

1. **NO SOURCE EDITS** between image build → snapshot creation → validation generation → retained benchmark generations.
2. No other agent may modify the relevant source/custom-node tree during collection.
3. The benchmark harness records a source identity/fingerprint at start and verifies it remains unchanged (existing Step-3 identity plumbing plus `effective_env` capture in the new result store).
4. The final deployment must be built from the exact tree **as of the end of this task**. `commit hash: none` — the working tree intentionally contains concurrent uncommitted work (Step 3, waterfall reconciliation, Agents 3/4, this framework); committing would capture unrelated changes.

---

# Unified experiment framework

`comfymodal_runtime/v2_experiments.py` (new, ~355 lines) provides the coherent experiment abstraction:

- `EXPERIMENT_SPECS`: five experiments with `(name, arms, selector, env_key, default_arm, implementation_version)`.
- `resolve_experiment(name)` / `resolve_all_experiments()` → frozen `ExperimentSelection` `(name, arm, effective_settings, implementation_version, selector, source)`.
- `emit_experiment_selection(trace, selection)` → `experiment_selection` trace event + `[v2.experiment] experiment=<name> arm=<arm> implementation_version=<v> selector=<s> source=<src> settings=<json>` line.
- Typed accessors used by the runtime lanes: `unet_pinned_staging_enabled()`, `unet_staging_chunk_mb()`, `vae_early_start_ms()`, `vae_expected_sampling_ms()`, `png_compress_level()`, `conditioning_async_lru_enabled()`, `restore_total_vram_frozen_enabled()`.
- **Invalid arm handling is explicit, never silent:** invalid env value → `[v2.experiment] ERROR invalid_arm ... fallback=<default>` log + documented fallback to the default arm (a result can never be ambiguous about which implementation produced it).

Request-level switching flows through the existing `__request_origin_info__` allowlist in `modal_app.py` (extended with `png_compress_level`, `vae_early_start_ms`, `unet_pinned_staging`, `conditioning_async_lru`, plus an int-range validation path for the two int keys). Deployment-level selection (`restore_memory`) is a deployment-baked env var because restore executes before ordinary request-plan selection.

Arm inventory:

```
unet_transfer     / baseline | pinned_staging
vae_overlap       / baseline | early_250 | early_500 | early_750 | early_1000
png_encode        / level6   | level1
conditioning_hit  / sync_lru | async_lru
restore_memory    / baseline | optimized
```

---

# Waterfall percentage/bar change

Implemented in `comfymodal_runtime/v2_waterfall.py`:

- `WaterfallReport` gains `scheduling_ms`, `total_wall_ms`, `command_response_ms`, `partial_waterfall`, `partial_flags` (serialized by `waterfall_to_dict`, parsed with defaults by `_report_from_value`).
- **`TOTAL WALL = COMMAND→RESPONSE − Modal scheduling`** (`total_wall_ms`). TOTAL WALL still includes pre-Python snapshot restoration, Python restore, restore→method, application execution, and result handoff/return. Only `modal_scheduling` is excluded.
- All stage/detail/residual/accounted percentages and all `#` bars use **TOTAL WALL** as denominator (fall back to command→response when scheduling is unknown). Reconciliation math is unchanged: the accounted sum still reconciles to the FULL command→response wall.
- Render header block:

```
TOTAL WALL:        12.400s   (command->response minus Modal scheduling)
SCHEDULING:      165.100s   (informational - excluded from % and bars)
COMMAND->RESPONSE:177.500s
```

- The `modal_scheduling` row renders duration only: **no %**, **no # bar**.
- New footer row `| TOTAL WALL |` (100.0% when known, full bar). All existing footer rows preserved.
- Example semantics: Sampling 5.0 s, TOTAL WALL 10.0 s, Scheduling 200.0 s → Sampling displays ≈ 50% (not ~2.4%).
- Tests with extreme scheduling values: `tests/test_waterfall_scheduling_denominator.py` (200 s / 300 s scheduling fixtures still tile the full wall; sampling ≈ 50% of TOTAL WALL; scheduling row shows `-`/blank bar).

---

# Remote partial vs final waterfall

- `build_waterfall` marks `partial_waterfall=True` when the artifact lacks any of: actual submission boundary (`missing_submission`), Modal restore-begin (`missing_modal_restore_begin`), or local result receipt (`missing_local_result_receipt`).
- Render title becomes `V2 COLD WATERFALL - REMOTE/PARTIAL (awaiting host reconciliation)` for partial artifacts, with a note listing the missing boundaries.
- When the pre-Python interval cannot be classified (no restore-begin), the scheduling stage is labeled `Modal scheduling + pre-Python restore (awaiting host reconciliation)` — never described as generic application residual.
- The host-side rebuilt waterfall remains the authoritative final artifact (existing `waterfall_local` rebuild flow).
- Result storage distinguishes `remote_partial_waterfall` (the remote-built `waterfall` when partial or differing) vs `final_reconciled_waterfall` (`waterfall_local` preferred) — see Result-storage schema.

---

# Experiment 1 — UNET H2D

**status: READY**

- **A (baseline):** exact current path — mmap safetensors → native UNET construction → assign/bind → `nn.Module.to(cuda)` (fast-disk replay `_fast_disk_replay_to`, pageable source, non_blocking=False, default stream, 454 storages, 12.31 GB). Byte-for-byte unchanged when the arm is off.
- **B (pinned_staging):** bounded pinned-staging chunked transfer. New module `comfymodal_runtime/unet_pinned_staging.py` — `transfer_module_via_pinned_staging(module, *, target_device, chunk_mb, ...)`:
  - ONE reused bounded pinned allocation of `chunk_mb` (default 512 MiB, clamp 16–8192, env `COMFYMODAL_V2_UNET_STAGING_CHUNK_MB`); no second 12.31 GB pinned model, no long-lived huge pinned allocation.
  - Per parameter/buffer: pageable → pinned (host copy) → pinned → device `copy_(non_blocking=True)` on a dedicated lazy stream, chunked by byte ranges; final GPU tensor bound via `.data` (exact parameter count, values, BF16 dtype, contiguous layout, device preserved; no quantization, no numerical conversion).
  - Per-chunk host barrier (stream sync before buffer reuse) required for byte-identical correctness with a single reused buffer — this was caught and fixed during verification.
  - Clean failure handling: any exception or ineligibility → fallback to the exact original `original_to` path with a logged `[v2.experiment] unet_transfer arm=pinned_staging effective=baseline fallback=<reason>`; mid-bind abort restores the module to its original CPU tensors (no partial mutation). Eligibility guard: cuda target, no dtype/memory_format conversion requested, contiguous tensors.
- **Selector/gate:** request-selectable via `__request_origin_info__` key `unet_pinned_staging` / env `COMFYMODAL_V2_UNET_PINNED_STAGING`; container env also works. **Default: OFF (baseline).** Chunk bound via `COMFYMODAL_V2_UNET_STAGING_CHUNK_MB` (default 512).
- **Metrics:** H2D CPU wall, CUDA-event duration, effective GB/s, source pinned fraction (0.0), staging allocation size, peak staging, chunk count, chunk size, copy API, non_blocking, CUDA stream, stream priority — all in `unet_fast_disk_to_end` metadata + `[v2.experiment]` line. CLIP-forward wall / UNET↔CLIP overlap / UNET-ready slack / Sampling duration come from existing instrumentation (waterfall + `opt_*` events).
- **Expected saving (honest):** raw H2D 4151 ms is pageable+synchronous; B removes pageable-staging stalls but historical broad pinning did not eliminate H2D bimodality (CLIP/GPU or memory-system contention also contributed). **Raw stage saving: uncertain (0–40% of H2D). Critical-path saving = min(raw saving, sampler wait ~995 ms). Expected TOTAL WALL saving: 0–1.0 s.** Primary decision metric is actual TOTAL WALL saving, not raw H2D.
- **Risk:** chunk-loop overhead; side-stream contention with CLIP forward; driver pageable-staging still involved on the host copy. **Rollback:** unset the flag → exact A.
- **Future arm:** `unet_transfer / pinned_staging` on the same deployment/snapshot as baseline (request-level switch).

**Existing `COMFYMODAL_V2_PIN_UNET_TRANSFER` semantics (traced, unchanged):** cudaHostRegister (flags=0) on every unique CPU storage of the whole UNET (params+buffers), bounded by a 20 GiB cap, deduped by `(data_ptr, nbytes)`, no pinned allocation, no duplicated model bytes; pinned only for the span of the real `_mm_load_models_gpu` call inside the early-activation worker, unregistered in `finally`; never invoked on the native fast-disk replay path. **The new UNET B does NOT reuse or replace it** — it is a distinct bounded-staging mechanism (single small pinned buffer + chunked copies on a dedicated stream) and does not pin the model storages. **Maximum pinned staging allocation: `chunk_mb` (default 512 MiB, single reused buffer).**

---

# Experiment 2 — VAE activation overlap

**status: READY**

- **A (baseline):** exact current behavior — Sampling → Sampling ends → sampler MutationLane release → VAE GPU activation → VAE ready → decode. Structurally serial; measured post-Sampling transition ~526 ms (historical ~837 ms).
- **B (early_250/500/750/1000):** transfer-only overlap with narrow lane binding:
  - At Sampling start (`runtime_executor.py` hook after `acquire_sampler_mutation_lane_at_sampling_start`), `schedule_vae_early_start_at_sampling_start` resolves the exact VAE object and spawns a daemon worker when `COMFYMODAL_V2_VAE_EARLY_START_MS` ∈ {250,500,750,1000}.
  - **Phase 1 (pre-copy, NO lane, NO model mutation):** after `expected_sampling_ms (default 4900, env COMFYMODAL_V2_VAE_EXPECTED_SAMPLING_MS) − offset`, new GPU tensors are created via `t.detach().to(cuda, non_blocking=True)` on a dedicated side stream — the VAE model object is never mutated during Sampling.
  - **Phase 2:** wait on `_VAE_SAMPLING_END_EVENT` (set in `release_sampler_mutation_lane_at_sampling_end` before the sampler lane release; bounded 60 s).
  - **Phase 3:** acquire the MutationLane as owner `"VAE"` (strictly after the sampler released), rebind `.data` to the pre-copied GPU tensors, populate the same evidence the standard worker produces, emit terminal + reconciliation events. Decode path unchanged (joins the future, validates via the existing `_validate_vae_early_activation`).
  - Any failure → `effective=baseline fallback=<reason>` log and the standard sampling-end path re-creates the activation (A behavior). No invalid concurrent model mutation is possible: the only mutation happens under the lane after Sampling.
- **Selector/gate:** request-selectable via `vae_early_start_ms` key / env `COMFYMODAL_V2_VAE_EARLY_START_MS`; requires container `COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end` (already in the future deployment preset). Offset 0 = baseline. **Default: OFF (offset 0).**
- **Metrics:** Sampling duration, VAE scheduled/worker start/H2D start/end/ready/demand/join/decode, post-Sampling transition, TOTAL WALL (via trace events + `vae_early_activation_*` + `opt_vae_*` + waterfall).
- **Expected saving:** VAE H2D ~554 ms can be hidden under the tail of Sampling; early-start is a **failure** if Sampling slowdown ≥ hidden VAE time. **Raw stage saving: up to ~554 ms of transition. Critical-path saving: same, minus any Sampling slowdown. Expected TOTAL WALL saving: 0–550 ms** (measured causally by the A/B). Rank by net TOTAL WALL saving, not transfer overlap.
- **Risk:** PCIe/GPU contention slowing Sampling (explicitly measured); resolve-at-start identity stability; daemon lifetime on aborted requests (bounded wait, request-end bail). **Rollback:** offset 0 or unset → exact A.
- **Future arm:** `vae_overlap / early_<ms>` on the same deployment/snapshot as baseline (request-level switch, requires `sampling_end` mode container).

---

# Experiment 3 — PNG encoding

**status: READY**

- **A (level6):** PIL PNG, compress_level=6, optimizer=False (PIL default; byte-identical current path).
- **B (level1):** same PIL PNG path with `compress_level=1` passed to `Image.save` (both PNG call sites in `comfyapp.encode_image_tensor_batch`), optimizer still False. PNG remains lossless PNG.
- **Selector/gate:** request-selectable via `png_compress_level` key / env `COMFYMODAL_V2_PNG_COMPRESS_LEVEL` (allowed {1,6}, default 6; invalid → explicit ERROR log + level 6). **Default: OFF (level 6).** One `[v2.experiment] png_encode arm=level1` line per process when active.
- **Metrics:** PNG compression wall, total encode wall, output byte size, hash wall, descriptor wall, TOTAL WALL; the encode decomposition diag now reports the actual level.
- **Validation:** valid PNG, same width/height/channels, decoded pixels byte-identical (verified locally at levels 6 and 1 on a deterministic gradient).
- **Expected saving:** compression 605.8 ms of 620.7 ms encode; level 1 is typically ~3–5× faster on real images → **raw stage saving ~350–500 ms; critical-path saving identical (encode is on the critical path); expected TOTAL WALL saving ~300–500 ms.** File-size increase typically ~5–30% on real images (the local gradient fixture showed level1 larger than level6 — incompressible data; the wall-vs-size tradeoff is exactly what the A/B measures).
- **Risk:** output byte-size growth (cost), none for correctness (lossless). **Rollback:** level 6 / unset → exact A.
- **Future arm:** `png_encode / level1` on the same deployment/snapshot (request-level switch).

---

# Experiment 5 — Conditioning-cache exact-hit LRU path

**status: READY** (LRU semantics proven; async design implemented)

- **LRU semantics proof (from code):** `last_access_seq` is consumed ONLY by `_enforce_bounds` (deterministic-LRU eviction). `_lookup_entry` never reads it; hits depend only on manifest membership, file existence, byte-length, header format/schema/version, canonical key equality, model identity, and payload/per-tensor checksums. Missing/regressed LRU state causes at most extra misses (fail-closed re-encode) — never a wrong hit or lost payload. **LRU is purely eviction/recency metadata, not required for cache correctness, payload durability, identity validation, or exact-hit correctness.**
- **A (sync_lru):** exact current `_persist_lru_touch` — foreground manifest re-read + full atomic rewrite (temp+flush+fsync+replace+dir-fsync = 2 fsyncs) on every hit, under the RLock.
- **B (async_lru):** foreground exact hit returns immediately after enqueueing touched digests into a bounded set queue (`COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE_MAX_LRU_QUEUE`, default 1024, clamp 16–65536); a dedicated non-daemon worker coalesces all pending digests into ONE manifest rewrite per batch (`_persist_lru_batch`); `flush()` drains the queue synchronously before teardown (`lru_async_flush_count`); duplicates merged (set); overflow → dropped counter, never raises; persistence failure → `lru_async_failed` + log, cache entry remains valid (LRU is eviction-only). Agent-3 async STORE queue is untouched and independent.
- **Selector/gate:** request-selectable via `conditioning_async_lru` key / env `COMFYMODAL_V2_CONDITIONING_CACHE_ASYNC_LRU`. **Default: OFF (sync_lru).**
- **Metrics:** foreground exact-hit total; manifest/header/payload read, deserialize, checksums, materialization, LRU touch (now `lru_touch_mode` sync|async + `lru_touch_ms` = enqueue cost); background LRU persistence (batch size, batches, persist_ms, dropped, failed, flush count); TOTAL WALL.
- **Expected saving:** on normal hits the manifest rewrite is ~ms; the pathological 1.8–2.06 s hits are **dominated by entry payload read** (3.1 MB read ~1.84 s) — **this experiment does NOT claim to fix the pathological case unless data shows LRU was responsible; if payload read dominates, the report will state that clearly.** **Raw stage saving: up to the foreground LRU-touch cost (small on normal hits). Critical-path saving: same. Expected TOTAL WALL saving: 0–50 ms on normal hits (causal measurement).**
- **Risk:** worker-batch manifest contention with the store worker (both under the same RLock — serialized, never corrupting); eviction-quality drift from delayed touches (bounded by the queue + flush). **Rollback:** unset → exact A.
- **Future arm:** `conditioning_hit / async_lru` on the same deployment/snapshot (request-level switch).

---

# Experiment 6 — Restore memory query

**status: READY** (B implemented with proven value equivalence; net wall saving is the A/B's causal question)

- **Exact current semantics (traced):** `comfyapp._restore_in_process_gpu_state` calls `comfy.model_management.get_total_memory(get_torch_device())` → internally `torch.cuda.memory_stats()` + **`torch.cuda.mem_get_info(dev)`** → returns the **second element: TOTAL physical VRAM (MiB)** (not free, not currently-available — `get_free_memory` is a separate call at execution time). Stored in the module global `comfy.model_management.total_vram`; consumed for `EXTRA_RESERVED_VRAM` → `minimum_inference_memory()` → low-VRAM offload sizing. Second identical call site in the GPU-snapshot restore path. Measured `[v2.opt.gpu_state] total_memory_ms=` 236–339 ms. The call is effectively the **first CUDA-touching call of restore** (runs before the `cuda_init` stage), so the measured cost includes lazy CUDA-context initialization — **do not equate all gpu_state_ms with removable query cost**; the A/B isolates exactly this. Value is immutable per physical GPU but can differ across restore hosts (fallback SKUs); nothing caches/freezes it today.
- **A (baseline):** exact existing restore path (query runs).
- **B (optimized):** deployment-level `COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1`; at snapshot construction (`modal_app.py` snap-build hook) `maybe_freeze_snapshot_gpu_capacity()` captures `nvidia-smi memory.total/name` (no CUDA init at build) into `gpu_capacity_frozen.json`; at restore `apply_frozen_total_vram_or_none()` sets `total_vram` from the frozen value and **skips the mem_get_info query** when the flag is on and the file is valid — otherwise the exact A path runs (`fallback=no_frozen_capacity` logged once). **Source equivalence:** nvidia-smi `memory.total` and `mem_get_info()[1]` are the same physical total VRAM of the same GPU; the value is semantically equal. No approximate substitution. If the restore host GPU differs (fallback SKUs), the deployment must NOT enable this arm (documented precondition: fixed GPU SKU deployment, as in the future protocol).
- **Selector/gate:** **deployment-level only** (restore executes before request-plan selection; no request-state plumbing invented). **Default: OFF (baseline).**
- **Metrics:** `total_memory_ms` (query) vs `frozen:` marker, `restore_gpu_state_ms`, `cuda_init_ms`, `opt_restore_decomposition`, TOTAL WALL.
- **Expected saving:** raw stage saving 0–339 ms (if the measured cost is query-only; if it is context-init, the cost relocates to the `cuda_init` stage and net saving ≈ 0 — the A/B answers this). **Critical-path saving = raw (restore is on the first-request critical path). Expected TOTAL WALL saving: 0–339 ms, unproven until measured.**
- **Risk:** stale capacity if the deployment lands on a different SKU (gated by the documented fixed-SKU precondition; missing file → exact A). **Rollback:** unset the flag → exact A.
- **Future arm:** `restore_memory / optimized` requires a **separate deployment** (cannot share with `baseline` in one deployment).

---

# Request/container/deployment selection matrix

| Experiment | Same deployment A/B | Same snapshot A/B | Request-level switch | Requires fresh deployment | Requires fresh snapshot |
|---|---|---|---|---|---|
| unet_transfer | YES | YES | YES | NO | NO |
| vae_overlap | YES | YES | YES (offset; container must be `sampling_end` mode) | NO (mode is in the preset) | NO |
| png_encode | YES | YES | YES | NO | NO |
| conditioning_hit | YES | YES | YES | NO | NO |
| restore_memory | NO | NO | NO | **YES** (flag baked at deploy) | YES (per deployment) |

All request-level arms are independently measurable on one shared deployment/snapshot (baseline, UNET-only, VAE-only, PNG-only, cache-only) before any combined winner is tested.

---

# Interaction matrix

| Interaction | Expected effect | Measurement |
|---|---|---|
| UNET H2D ↔ CLIP forward | Staged transfer on a side stream may reduce or shift contention vs pageable copy under degraded CLIP forward | `unet_clip_overlap` + sampler slack |
| UNET H2D ↔ PromptExecutor demand timing | H2D speedup shrinks only the portion of sampler wait it caused (~995 ms ceiling) | `unet_readiness` slack, sampling start delta |
| VAE H2D ↔ Sampling | Early transfer can slow Sampling kernels (PCIe/GPU contention); failure if slowdown ≥ hidden VAE time | Sampling duration + post-Sampling transition + TOTAL WALL |
| Cache-hit speed ↔ CLIP encoding | LRU-touch removal speeds hits but CLIP encoding is skipped entirely on exact hits; effect is lookup-wall only | `clip_conditioning_cache_lookup`, total_ms |
| Restore optimization ↔ CUDA initialization | Skipping the query may relocate context-init cost to `cuda_init` (net ≈ 0) or remove it (net up to 339 ms) | `restore_gpu_state_ms` + `cuda_init_ms` decomposition |

Raw savings are never added blindly: every experiment reports **raw stage saving / critical-path saving / expected TOTAL WALL saving** separately, and TOTAL WALL (excluding scheduling) is the primary ranking metric.

---

# Instrumentation

- `[v2.experiment] experiment=<name> arm=<arm> implementation_version=<v> selector=<s> source=<src> settings=<json>` on every applied arm; `[v2.experiment] ERROR invalid_arm` on misconfiguration.
- `experiment_selection` trace event (metadata: experiment_name, arm, effective_settings, implementation_version, selector, source).
- Existing opt_* diagnostics remain untouched and are consumed by the result store (`opt_diagnostics`).
- UNET B: staging metrics on `unet_fast_disk_to_end` + `unet_fast_disk_complete`-compatible fields (to_wall_ms/to_device_ms) so the waterfall keeps working.
- VAE B: `vae_early_activation_scheduled/load_start/load_end/terminal/reconciliation` + `opt_vae_*` events with the standard shapes.
- Waterfall: `scheduling_ms`, `total_wall_ms`, `command_response_ms`, `partial_waterfall`, `partial_flags` in every serialized report.

---

# Safety / rollback

- Every B path is default OFF; A paths are byte-for-byte current (verified by tests).
- Every B failure falls back to the exact A implementation with a logged, unambiguous `effective=baseline fallback=<reason>` (never silent).
- UNET staging aborts restore the module to original CPU tensors; eligibility guards prevent wrong-dtype/wrong-layout copies.
- VAE overlap mutates the model only under the MutationLane, strictly after Sampling; request-end bail prevents daemon leaks; bounded waits.
- Cache LRU async: LRU is eviction-only metadata (proven); failures never corrupt hits, stores, or payloads; bounded queue; deterministic flush.
- Restore B: value equivalence proven; missing/corrupt frozen file → exact A; fixed-SKU precondition documented.
- Rollback = unset env/flag; no migration required; no snapshot changes.

---

# Local verification

Run (all green, **100 passed**):

- `python -m pytest tests/test_v2_ab_experiments.py tests/test_waterfall_scheduling_denominator.py tests/test_v2_waterfall.py tests/test_waterfall_reconciliation.py tests/test_exact_cache_async_persistence.py tests/test_optimization_diagnostics.py -q` → 100 passed
- `python -m py_compile` on all 11 changed/new files → OK
- Integration import of all new modules + default-arm resolution → OK

Coverage: B defaults OFF; baseline reproduces current behavior; experiment metadata emitted; invalid arm fails explicitly with log; PNG level 1/6 valid + pixel-identical + same dims; UNET staging exact params/bytes/dtype/values/device, bounded pinned allocation (1 MiB in test), configured limit enforced, non-contiguous fallback clean, baseline unchanged; VAE lane safety (no mutation outside lane), offset selection exact; cache LRU bounded + coalesced + failure-independent + deterministic teardown; restore B frozen-value semantics + fallback; waterfall extreme scheduling (200 s/300 s) still reconciles, sampling ≈ 50% of TOTAL WALL, scheduling has no %/bar, remote-partial vs final labeling, dict round-trip.

---

# Result-storage schema

`comfymodal_runtime/experiment_result_store.py` (new) + harness wiring in `tools/benchmark_v2_direct.py`:

- Directory: `<base>/benchmark_runs/<UTC-YYYYMMDD-HHMMSS>/` (base default `./benchmark_runs`; the harness `--output-dir` convention still governs the existing `run_<index>.json` artifacts).
- Files: `run_<ordinal:03d>_<run_role>.json` per generation + `campaign_manifest.json` (generations_total, retained, discarded, per-record summaries).
- Record keys (30): request_id, experiment, arm, run_ordinal, run_role, retained, discard_reason, image_id, snapshot_identity, provider, region, gpu, cpu, ram, full_trace, opt_diagnostics, **final_reconciled_waterfall**, **remote_partial_waterfall**, effective_env, effective_experiment_settings, output_descriptor, output_sha, sampling_boundary_ms, critical_path_metrics, total_wall_ms, scheduling_ms, command_response_ms, wall_ms, persisted_at_utc, source_identity.
- Harness flags: `--experiment <name>`, `--arm <arm>`, `--run-role sample|validation_discard|probe` (validation_discard → `retained=false`, `discard_reason=first_post_snapshot_run`).
- No reliance on console text; every future generation persists the full raw trace.

---

# Future deployment protocol

## PHASE A — freeze source tree
No source edits between image build → snapshot creation → validation generation → retained generations. Record source identity at start; verify unchanged. `commit hash: none`.

## PHASE B — deploy once (exact preset, unchanged from the task)
```
V2_BENCHMARK_MODE=snapshot_restore_only
COMFYMODAL_V2_ENV_PROFILE=inherit
COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=1
COMFYMODAL_V2_VAE_SNAPSHOT=1
COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1
COMFYMODAL_V2_EVICT_MODELS_BEFORE_SNAPSHOT=1
COMFYMODAL_V2_EVICT_RETAIN_ROLE=clip_vae
COMFYMODAL_V2_EVICT_RESTORE_IDLE_SECONDS=0
COMFYMODAL_V2_NATIVE_FAST_DISK_UNET=1
COMFYMODAL_V2_CLIP_CONDITIONING_CACHE=1
COMFYMODAL_V2_EXECUTION_UNET_H2D_DELAY_MS=0
COMFYMODAL_V2_UNET_ACTIVATION_MODE=late
COMFYMODAL_V2_VAE_ACTIVATION_MODE=sampling_end
COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0
COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1
COMFYMODAL_V2_MINIMAL_GPU_TEARDOWN=1
COMFYMODAL_V2_RELEASE_GPU_AFTER_REQUEST=1
COMFYMODAL_V2_CPU_REQUEST=12
COMFYMODAL_V2_MEMORY_MB=32768
COMFYMODAL_V2_MEMORY_REQUEST=32768
COMFYMODAL_V2_GPU=rtx-pro-6000
COMFYMODAL_V2_THREAD_POLICY=TBASE
COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER=O0
COMFYMODAL_V2_VAE_POLICY=v1
COMFYMODAL_V2_CLOUD=
COMFYMODAL_V2_REGION=
```
Plus optimization diagnostics (`COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS=1`, and `COMFYMODAL_V2_OPT_DIAG_SYNC_CUDA` as desired). No placement pinning. The restore_memory B deployment additionally sets `COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1` (snapshot-build hook freezes `gpu_capacity_frozen.json`).

## PHASE C — snapshot construction validation
Require `effective_profile=inherit`, `cpu_snapshot_models_present=1` with CLIP=1 VAE=1 **UNET=0**, `retain_role=clip_vae`, `native_fast_disk_unet=1`, H2D delay 0, snapshot RSS ≈ 11–13 GiB. If UNET present → STOP.

## PHASE D — mandatory Step-3 snapshot proof health
Require `[v2.deployment_proof] complete=1 valid=1` and non-empty/equivalent `deployment_combined_hash`, `custom_nodes_generation`, `registry_fingerprint`, `dependency_manifest_identity`, `generation_matches_observed=1`. If incomplete/invalid → STOP; diagnose the already-created snapshot (never generate contaminated samples).

## PHASE E — validation/discard generation (exactly 1)
Command: `python tools/benchmark_v2_direct.py --experiment <name> --arm <arm> --run-role validation_discard` (V2_BENCHMARK_RUNS=1).
- Label `run_role=validation_discard`, `retained=0`, `discard_reason=first_post_snapshot_run`; full raw trace still saved.
- Require: correct output (valid image, expected output node, non-empty graph execution, correct descriptor/hash); all expected opt_* diagnostics for the selected arm; host-side **final reconciled waterfall** within tolerance; Step 3: `plan_validation_fast_path`, `consumed=1`, all identity parity fields 1, `snapshot_proof_complete/valid=1`, certificate RPC/preflight/validate_prompt/writeback counts all 0, graph setup ~20–30 ms (structural bypass criteria authoritative). If `plan_validation_consumed=0` or any parity field fails → STOP.

## PHASE F — five retained generations (exactly 5)
Command: `python tools/benchmark_v2_direct.py --experiment <name> --arm <arm> --run-role sample` (V2_BENCHMARK_RUNS=5) → `run_001_sample.json` … `run_005_sample.json`. Roles: `sample_1..sample_5` (the discarded generation is never called sample_1). Total = 1 validation/discard + 5 retained = 6 generation calls per deployment.

---

# Snapshot validation

Per PHASE C/D above; `UNET=0` is authoritative; RSS class 11–13 GiB; Step-3 snapshot proof health gates the whole sequence. Nothing in this task changes snapshot composition (eviction/retain/snapshot flags are untouched; new code is runtime-arms only).

---

# Step-3 health gate

Per PHASE D/E above. This task adds no parity weakening: no Step-3 file modified; identity impact of this work is enumerated in Source-tree freeze requirements and is expected to be repaired by deploying from the exact final tree.

---

# Validation/discard generation

Per PHASE E above: exactly one generation, `run_role=validation_discard`, full trace saved, all gates proven before any retained run.

---

# Five retained generations

Per PHASE F above: exactly `sample_1..sample_5`, the entire retained dataset (N = 5).

---

# Statistical treatment

For each metric over the 5 retained samples: min / median / mean / max / standard deviation. A/B comparison: A median, B median, absolute delta ms, relative delta %, A mean, B mean, **placement_confounded** flag (0/1 — actual provider and region always recorded; slow scheduling never discards a valid request). Primary ranking metrics: **TOTAL WALL excluding scheduling**, controllable application wall, critical stage wall. Scheduling is informational only; never rank on command→response when the difference is scheduling variance. Always show TOTAL WALL, Scheduling, Command→response separately.

---

# Minimum deployments required

**2 deployments minimum** (each with its own snapshot and 6 generations):

1. **D1 — restore A deployment** (PHASE B preset exactly): runs baseline for all five experiments; UNET/VAE/PNG/cache arms switch per request via `__request_origin_info__`.
2. **D2 — restore B deployment** (PHASE B + `COMFYMODAL_V2_RESTORE_TOTAL_VRAM_FROZEN=1`): runs `restore_memory/optimized`; the four request-level experiments can also run here for cross-deployment A/B replication.

Snapshot sharing: unet_transfer, vae_overlap, png_encode, conditioning_hit share one snapshot (D1); restore_memory baseline/optimized cannot share (deployment-level), so D1/D2 have separate snapshots. If a restore-memory replication across 2 containers in one deployment were ever desired it is still one deployment-level arm per deployment.

---

# Remaining blockers

1. **No paid run has validated any arm end-to-end on the target RTX PRO 6000 deployment** — readiness is implementation + local-test based; causal TOTAL WALL savings for all five experiments are unmeasured by design.
2. **UNET H2D bimodality** is not yet causally explained (pageable staging vs CLIP/GPU contention); the new arm is a causal A/B, not a predetermined fix.
3. **Restore B net saving** depends on whether the 236–339 ms is query cost or lazy CUDA-context init (which may relocate to `cuda_init`); resolved only by the A/B run.
4. **Pathological cache cold hits (~1.8–2.06 s)** are likely payload-read-dominated; async LRU does not claim to fix them — data from the campaign must confirm before any further cache work.
5. **Step-3 fast-path acceptance** has not yet succeeded on a real deployment (parity/source-tree issue from the degraded acceptance host); the frozen-tree protocol is required for a clean acceptance opportunity.
6. **registry_fingerprint / dependency_manifest_identity** impact of this work is only determinable at deploy time via the Step-3 proof.
7. **Modal scheduling** remains excluded from TOTAL WALL by design; the campaign must confirm scheduling variance is not masking application-stage deltas (placement_confounded reporting).

---

# Completion summary

- Report path: `V2_REMAINING_OPTIMIZATION_AB_SETUP_REPORT.md` (this file).
- Changed files (new): `comfymodal_runtime/v2_experiments.py`, `comfymodal_runtime/unet_pinned_staging.py`, `comfymodal_runtime/restore_memory_arm.py`, `comfymodal_runtime/experiment_result_store.py`, `tests/test_v2_ab_experiments.py`, `tests/test_waterfall_scheduling_denominator.py`.
- Changed files (edited): `comfymodal_runtime/model_preload.py`, `comfymodal_runtime/runtime_executor.py`, `comfymodal_runtime/clip_conditioning_cache.py`, `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/v2_waterfall.py`, `comfyapp.py`, `tools/benchmark_v2_direct.py`, `tests/test_v2_waterfall.py` (one contract key-set fix).
- Commit hash: **none** (working tree intentionally retains concurrent uncommitted work).
- Production defaults changed: **NO** (all B arms default OFF; A paths byte-identical).
- Paid Modal runs performed: **NO**.
