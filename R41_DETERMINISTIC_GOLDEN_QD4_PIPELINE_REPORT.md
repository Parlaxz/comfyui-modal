# R41 — Deterministic Golden QD4 Model Pipeline and Resource-Aware Overlap Scheduler

Batch: **R41** · Date: 2026-08-22 · Branch: `r41-deterministic-golden-pipeline` · Worktree: `../comfyui-modal-r41`
Parallel with E40 (canonical checkout untouched; zero edits to `comfyapp.py` or any E40-owned file).
No Modal deployment was performed. No push.

Evidence labels: **CONFIRMED** (command/artifact verified) · **SUPPORTED INFERENCE** · **UNOBSERVABLE** (needs physical run).

---

## 1. Executive verdict

R41 delivers the requested architecture as a self-contained runtime package plus a deterministic local proof suite:

- **ONE generic Golden QD4 loader engine** (`comfymodal_runtime/golden/qd_engine.py`) used by CLIP, UNET, and VAE through role manifests only — no model-specific hacks.
- **Structural fix for the QD collapse mechanism**: source workers are fully decoupled from H2D/CUDA events (the historical two-slot-per-worker event-wait coupling is gone). The only legitimate coupling left is bounded-ring backpressure, which is counted and classified.
- **Occupancy-first telemetry**: time-weighted fraction at target QD, per-reason below-QD accounting, free-slot minimums, completed-waiting-for-H2D depth, backpressure totals, latency percentiles, steady-state GB/s. Peak `observed_max_outstanding` alone is explicitly treated as insufficient.
- **One explicit resource scheduler** with an event-driven state machine and an encoded allow/deny overlap matrix; forbidden overlaps fail loudly (`ForbiddenOverlapError`); zero sleeps.
- **Strong ownership** with join/adopt semantics; duplicate reads per role are structurally impossible (registry rejects a second live owner).
- **Static-metadata-only snapshot composition** with quiescence assertions and weight-value exclusion enforcement.
- **Fail-closed fallback semantics**: a fallback can never be classified ACCEPTED_NOMINAL (unit-tested).
- **58/58 local tests pass**; synthetic local benchmark proves decoupling, occupancy mechanics, timeline ordering, single-read-per-role, bounded staging, and exact event ordering.

FAST + REPEATABLE + EXPLAINABLE: the "explainable" leg is now mechanically enforced locally; the "fast" leg requires physical Modal measurement after E40/R41 reconciliation (**UNOBSERVABLE** here by design).

## 2. E39 baseline commit SHA used

`0c59f46e3238f421378e8852ebc548da815b70af` — "e39: prune superseded comfyapp paths and preserve golden runtime".
Worktree created from that exact commit: `git worktree add ../comfyui-modal-r41 -b r41-deterministic-golden-pipeline 0c59f46`.

## 3. Historical loader evidence recovered

| Measurement | Value | Source |
|---|---|---|
| UNET full ~12.31 GB, 32 MiB ranges, QD1 cold | ~6.60 GB/s | batch brief / prior reports |
| QD2 | ~23.04 GB/s | batch brief |
| QD4 | ~43.45 GB/s (~283 ms source read, ~100 ms CPU) | batch brief |
| QD8 | ~49.61 GB/s (~248 ms source, ~330 ms CPU, larger tail spread) | batch brief |
| Other historical QD4 | ~30.21 GB/s | batch brief |
| E37 clean-lane gate (remote) | source wall 1043.5 ms → **7.71 GB/s aggregate**, H2D host issue 127.4 ms, H2D CUDA event 27.3 ms | `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` |
| E39 gate (remote) | aggregate 5.67 GB/s, **steady_state_gbps 1.63**, source wall 1418.6 ms, first completion 23.3 ms, h2d_device 39.0 ms, h2d_host_issue 142.1 ms, buffer_pool_wait 2.43 ms; QD 4/4, 240/240 blocks, 0 errors | `E39_COMFYAPP_GOLDEN_PATH_PRUNING_REPORT.md` §30/§33 |
| VAE pre-copy | ~70 ms physical copy hideable under sampling; negligible join at demand | C5-era evidence, reused as design input |
| `torch.cuda.empty_cache()` cost | ~739–950 ms even with nothing unloaded (historical); current path has a fail-closed bypass guard | E5 audit + `empty_cache_bypass.py` |

Prior conclusion preserved: storage ownership and GPU ownership are distinct; UNET prepare is storage-side and may overlap CLIP compute; UNET commit is GPU-side and waits for a safe CLIP GPU boundary. QD4/32 MiB remains the Golden target for all three roles.

## 4. Current QD architecture audit (at E39 baseline)

- `comfymodal_runtime/clip_qd_reader.py` (1,935 LOC): production CLIP QD4. qd=4 clamped 1–32, block 32 MiB, static partition across exactly qd workers, `qd×2` pinned slots, contiguous GPU destination, exact tensor views, transactional failure, rich-but-peak-oriented telemetry.
- **Coupling defect (CONFIRMED)**: each worker waits on its previous block's CUDA end-event before issuing its next source read (`clip_qd_reader.py:1472–1491`: `_wait_event_host(end_event)` precedes `_timed_read_at`). Two slots per worker ⇒ whenever H2D/event latency spikes, all four workers stall their next read while `observed_max_outstanding` still peaks at 4.
- UNET transports are unrelated implementations: `unet_fastsafetensors.py` (2,198 LOC, ZImage-specific external loader), `unet_meta_direct.py` (630 LOC, two-slot wave pipeline, one host loop), `unet_pinned_staging.py` (single reusable pinned chunk), `staged_safetensors.py` (2,037 LOC generic staged loader, slab pool). No shared engine.
- VAE: native Comfy load path + `prefetch_vae_storage()` CPU page-touch prefetch with bounded demand join (`model_preload.py:12370–12500`, `cpu_snapshot_models.py:797–900`).
- Ownership: `unet_ownership_claim/release`, `graph_unet_join_or_adopt` (join/adopt/already_ready, `_GRAPH_JOIN_TIMEOUT_S=120`) in `model_preload.py:15284–15659`; CLIP owner inside `clip_qd_reader` (`QdGpuOwner`).
- GPU exclusion: `gpu_lane_coordination.py` request-scoped CLIP/UNET critical-section tokens.
- Conditioning forced miss via cache nonce (`clean_lane_forced_miss`; hit=false, miss_count=1, encode_calls=1, persisted=0 proven in E37/E39 gates).
- Snapshot: `execution_seed.py` static skeleton; `cpu_snapshot_models.py` CPU-resident reconstruction; `snapshot_capture_hygiene.py` gc/malloc_trim only; **no canonical RESTORE_READY event existed**.
- Telemetry gaps: no time-weighted occupancy, no below-QD reason classification, no free-slot/completed-waiting-H2D depth, no standardized "QD dropped below configured" event.

## 5. Why recent QD4 collapses despite historical 30–43+ GB/s

1. **Application starvation via CUDA-slot reuse coupling (CONFIRMED mechanism)**: with two slots per worker and an end-event wait before slot reuse, one slow H2D/event completion stalls that worker's next source read; four independent stalls serialize the whole source plane. Peak outstanding still touches 4, so legacy telemetry shows "QD 4/4" while effective steady-state depth collapses — exactly what E39's gate recorded (peak 4, `steady_state_gbps=1.63` vs aggregate 5.67).
2. **Measurement blindness**: no time-weighted occupancy or drop-reason fields existed, so application starvation could not be distinguished from physical/source variance.
3. **Physical/source-side variance remains possible** (Modal volume service behavior): R41 does not explain it away — it isolates it. If QD stays at 4, CPU is not saturated, staging is not exhausted, and H2D is not backpressuring while source is still slow, the engine now classifies it as physical/source-side behavior rather than application starvation.

R41 fixes (1) structurally and makes (2)/(3) mechanically answerable.

## 6. Generic GoldenQD4Loader architecture

```
GoldenQD4Loader(config: QD4EngineConfig, backend: TransferBackend)
    .load(manifest: RoleManifest, destination: DestinationPlan,
          ledger_sink=None, label="golden_qd") -> LoadResult
```

- `RoleManifest` = role + path + sha256 + `SafetensorsLayout` (header/tensor map with absolute offsets) + identity hash + destination kind + immutable `QDRangePlan`.
- `QDRangePlan.build(layout, block_bytes, buffer_mode)` produces the static contiguous decomposition (complete, ordered, non-overlapping; inter-tensor padding tolerated; overlaps fatal) with per-block `CopySegment`s translating block-local offsets into destination coordinates.
- Destination strategies: `CONTIGUOUS_GPU_BUFFER` (one flat device buffer; tensor views later) and `PARAMETER_COPY_TARGET` (one exact-sized buffer per tensor, e.g. CUDA parameters). Same engine, same planes.
- Backends: `CudaTransferBackend` (pinned staging + non_blocking copy_ + cuda events) and `CpuCopyBackend` (hermetic thread-pool async copies with injectable latency) so the identical concurrency machinery is deterministically testable without CUDA.
- Transactional/fail-closed: any worker exception, short read, coverage/byte mismatch, or bind validation failure aborts, releases everything, and raises a `GoldenQDFailure` subclass with `.telemetry` attached.

## 7. Source/H2D decoupling

- SOURCE SIDE: exactly `queue_depth`(=4) worker threads pop static block indices, acquire a staging slot (the ONLY blocking point — measured as backpressure), timed-read into the slot, publish to a ready queue. **A source worker never inspects or waits on any copy completion/event.**
- TRANSFER SIDE: one dedicated dispatcher thread pops ready items, issues non-blocking copies per segment, records completions, reaps finished ones and returns slots to the ring.
- BOUND: finite ring (default 8 × block_bytes = 256 MiB at 32 MiB blocks). No whole-model pinning, no unbounded queues. When the ring exhausts, source workers wait on slot availability — counted (`h2d_backpressure_events`, `h2d_backpressure_ms_total`) and classified (`QDDropReason.H2D_BACKPRESSURE`).
- Invariant enforced and tested: except startup/tail/backpressure, if unread blocks remain and free slots exist, four source reads remain outstanding (`observed_max_outstanding == 4` under injected 20 ms/copy H2D; unexplained below-QD time ≤ max(2 ms, 5%)).

## 8. Bounded staging design

`_StagingRing`: N slots (default 8 ≥ 2·qd), each exactly `block_bytes`, allocated through the backend (pinned on CUDA). Condition-variable free list; acquire records wait time; release notifies. Telemetry: `staging_slots`, `pinned_bytes` bound, `free_slots_min`. Cleanup releases every slot and clears tensors in a `finally` (tested: no thread leaks after failure).

## 9. CLIP integration

CLIP = `GoldenQD4Loader(role=CLIP)` with contiguous-buffer destination. Pipeline phase 2 grants `ACT_CLIP_QD_SOURCE` (STORAGE_HEAVY) + `ACT_CLIP_QD_H2D` (H2D_HEAVY); cheap request/static work may proceed concurrently (matrix ALLOW). Demand JOINs/TAKES the published owner — no second CLIP reader can exist (registry-enforced, tested). At device readiness: `CLIP_DEVICE_READY` transition; clip QD grants are force-released and `unet_prepare_allowed` arms. Forward holds GPU_COMPUTE + GPU_MUTATION (`clip_gpu_critical`) until `clip_gpu_critical_done()`. Conditioning contract enforced: forced miss, encode_calls=1, persist=0 (`ConditioningContract.validate_observed`, unit-tested).

## 10. UNET integration

Phase 3 allows `ACT_UNET_METADATA_PREP` (CPU_HEAVY) during CLIP forward — layout/plan validation and destination pre-planning only, no transfer, no GPU mutation. Bulk source is denied until CLIP storage release proof AND grant absence (gated, tested). Phase 4 begins only on the `CLIP_GPU_CRITICAL_DONE` event; `ACT_UNET_GPU_COMMIT` outside PHASE4 raises. Commit runs the SAME QD4 engine into parameter-copy destinations, publishes the owner, transitions `UNET_DEVICE_READY`. Generic `load_models_gpu` at sampler demand must become validation/adoption via `registry.join_or_adopt(UNET)` — adoption seam provided (`integration.unet_demand_join`); native migration of an already-Golden-ready UNET is the forbidden behavior the seam exists to prevent.

## 11. VAE integration

VAE = same loader family, small-file case verified (n_blocks==1 still carries configured_qd semantics). `ACT_VAE_QD` (STORAGE_HEAVY+H2D_HEAVY in one grant) is gated on `vae_qd_armed`, set exclusively by `FIRST_SAMPLER_STEP_PROVEN`. Demand joins the Golden owner (`vae_decode_demand`); ADOPTED/FAILED/TIMEOUT produce typed `DegradationRecord`s — never silent nominal. The earlier VAE pre-copy evidence (~70 ms hideable) is preserved as design input; whether VAE QD4 perturbs sampling is explicitly deferred to post-reconciliation measurement ("measure rather than assume").

## 12. Snapshot design

`snapshot.py`: REQUIRED_STATIC_ENTRIES (imports/modules registry, custom-node registry, topology/reachability, ExecutionPlan facts, tokenizer/config, manifests, safetensors headers, tensor maps, QD range plans, skeletons/meta ×3, identities) vs FORBIDDEN_SNAPSHOT_ENTRIES (weight values ×3, active readers, unresolved CUDA events, request state, persistence queue, speculative future, temporary owner, stale pinned buffers). `assert_quiescent()` lists every violation and raises `QuiescenceViolationError`. `SnapshotAccounting.validate_exclusions()` enforces zero weight-value bytes for CLIP/UNET/VAE. `build_snapshot_manifest()` is deterministic (sorted canonical JSON + sha256; tested byte-identical for identical inputs). Immutable metadata absence at runtime raises `ImmutableStateAbsentError` — silent rebuild while claiming nominal is forbidden. Serialized Modal snapshot bytes remain UNOBSERVABLE until Modal exposes them.

## 13. Resource scheduler

`GoldenResourceScheduler`: explicit phase table (SNAPSHOT_CAPTURE → MINIMAL_RESTORE → CLIP_QD_LOAD → CLIP_FORWARD_UNET_PREPARE → UNET_COMMIT → SAMPLING → OUTPUT_DELIVERY → COMPLETE), entered only via `GoldenEvent`s; any illegal (phase,event) pair raises `GoldenError` loudly with history tail. Exclusive domains STORAGE_HEAVY / H2D_HEAVY / GPU_MUTATION enforced at acquire. Deterministic: identical walks produce identical phase histories (tested). Zero sleeps (AST-scanned in tests).

## 14. Overlap allow/deny matrix (encoded)

| Pair | Decision |
|---|---|
| CLIP_QD_SOURCE + CHEAP_REQUEST_SETUP | ALLOW |
| CLIP_QD_SOURCE + UNET_BULK_SOURCE | DENY (until storage release + grant absence) |
| CLIP_QD_H2D + UNET_H2D | DENY (+ exclusive domain) |
| CLIP_FORWARD + UNET_METADATA_PREP | ALLOW |
| CLIP_GPU_CRITICAL + UNET_METADATA_PREP | ALLOW (CPU-side prep under CLIP GPU-critical) |
| CLIP_FORWARD + UNET_BULK_SOURCE | ALLOW (reachable only after storage release) |
| CLIP_GPU_CRITICAL + UNET_GPU_COMMIT | DENY |
| CLIP_GPU_CRITICAL + SAMPLING | DENY |
| SAMPLING + VAE_QD | CONDITIONAL — armed only by FIRST_SAMPLER_STEP_PROVEN |
| VAE_GPU_MUTATION + SAMPLING | DENY |
| UNET_GPU_COMMIT + SAMPLING | DENY |
| CLIP_FORWARD + CLIP_QD_SOURCE | DENY (no demand race against own forward) |
| same-loader plane pairs (source+H2D) | ALLOW |
| unlisted heavy/heavy pairs | default DENY |

Conditions/events, never delays. Denials raise `ForbiddenOverlapError` with the conflicting active labels.

## 15. Event state machine

RESTORE_READY → CLIP_DEVICE_READY (arms UNET prepare, force-releases clip QD grants) → CLIP_STORAGE_RELEASED (proof marker) → CLIP_FORWARD_STARTED (marker) → CLIP_GPU_CRITICAL_DONE → [UNET_COMMIT] UNET_DEVICE_READY → SAMPLING_STARTED → FIRST_SAMPLER_STEP_PROVEN (arms VAE) → VAE_DEVICE_READY (marker) → VAE_DECODE_DEMAND → FIRST_DURABLE_RESULT → COMPLETE. All other combinations raise. Verified end-to-end in tests and benchmark scenario C.

## 16. Ownership lifecycle

PREPARING → DEVICE_READY → BIND_READY → PUBLISHED → RELEASED, with FAILED from PREPARING/DEVICE_READY. `join()` distinguishes JOINED (waited on in-flight producer) vs ALREADY_READY; FAILED/TIMEOUT propagate to consumers. `take()/release()` refcount strong lifetime (payload retained until zero retentions; extra release raises). `GoldenOwnerRegistry` permits ONE live owner per role — duplicate registration raises, making duplicate reads structurally impossible (tested).

## 17. Cache / static-state contract

Immutable expensive state materializes before snapshot capture (headers, tensor maps, range plans, skeletons, identities — all first-class manifest entries). Runtime absence → DEGRADED/FAILED classification, never silent rebuild-as-nominal. Conditioning remains the deliberate exception: forced miss, encode_calls=1, persist=0 — validated by `ConditioningContract` and wired through `GoldenPipeline.check_conditioning_observed`. Terminology: snapshot-resident static metadata (no "prompt static cache" introduced).

## 18. Fallback semantics

`classify_hard_failure(exc)` → `DegradationRecord(QD_HARD_FAILURE_FALLBACK, fallback_used=True)`. `final_status(ok, degradation)`: degradation present ⇒ DEGRADED regardless of ok; failure without recovery ⇒ FAILED; else ACCEPTED_NOMINAL. `assert_fallback_never_nominal(degradation)` raises if a fallback path attempts nominal (unit-tested both ways). VAE demand without a Golden owner yields typed degradation records (IMMUTABLE_METADATA_ABSENT / OWNER_JOIN_TIMEOUT / QD_HARD_FAILURE_FALLBACK).

## 19. Empty-cache policy

Historical cost ~739–950 ms; current repo already contains a fail-closed guard (`empty_cache_bypass.py`: bypass only for `free_memory_defensive_no_unload`, zero unload, no capture/custom pools, ≥2× headroom; env-gated, default off). R41 policy decision: Golden must not pay an opportunistic ~1 s purge at the VAE transition when VRAM is abundant, but allocator cleanup is NOT blindly removed. Because the guard lives in E40-owned integration territory, R41 defers wiring to reconciliation (manifest item M-06): route the VAE-transition empty-cache branch through the existing bypass predicate and record executed/not-executed in telemetry. No code change to `empty_cache_bypass.py` was made in R41.

## 20. Exactness preservation

Canonical expected output `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` is frozen as `contracts.EXACT_OUTPUT_SHA` and asserted equal to the profile-configured SHA (test). Exactness gates: byte-exact destination equality per tensor (tests), coverage/byte reconciliation in-engine, bind validation, and the profile-level output-SHA check at remote validation time. No Comfy patches were needed or made.

## 21. Changed/new files (all NEW; zero modifications to existing files)

| File | Lines | Purpose |
|---|---:|---|
| `comfymodal_runtime/golden/__init__.py` | 120 | public exports |
| `comfymodal_runtime/golden/contracts.py` | 498 | frozen interface: enums, plan structures, telemetry, exceptions |
| `comfymodal_runtime/golden/qd_engine.py` | 622 | QD4 engine, backends, header parser |
| `comfymodal_runtime/golden/model_owner.py` | 161 | ownership protocol + registry |
| `comfymodal_runtime/golden/resource_scheduler.py` | 295 | state machine + overlap matrix |
| `comfymodal_runtime/golden/snapshot.py` | 169 | manifest/quiescence/accounting |
| `comfymodal_runtime/golden/pipeline.py` | 261 | timeline facade + fallback semantics |
| `comfymodal_runtime/golden/integration.py` | 60 | seam adapters + enablement gate |
| `tests/golden/**` (10 files) | ~900 | deterministic suite |
| `tools/golden_local_benchmark.py` | ~250 | local evidence runner |
| `R41_LOCAL_BENCHMARK_EVIDENCE.json` | — | captured evidence |

Commits on `r41-deterministic-golden-pipeline`: `9f58629` (contracts freeze), `2187c5e` (implementation + tests + benchmark). Base `0c59f46`. Not pushed.

## 22. Local tests (exact counts)

`python -m pytest tests\golden -q` → **58 passed** (CONFIRMED; wall ≈ 9–19 s):

| File | Tests |
|---|---:|
| test_golden_qd_core.py | 12 |
| test_golden_ownership.py | 10 |
| test_golden_scheduler.py | 10 |
| test_golden_snapshot.py | 6 |
| test_golden_cache_contract.py | 5 |
| test_golden_exactness.py | 4 |
| test_golden_fallback.py | 4 |
| test_golden_genericity.py | 4 |
| test_golden_pipeline_end_to_end.py | 3 |

Coverage maps to every required bullet family: QD core (configured=4, real 4-worker concurrency, 32 MiB-class range accounting incl. partial tail, no gap/overlap/duplicate, bounded ring, safe H2D completion, decoupling under injected slow H2D, slow-source tolerance, worker exception, short read, bind exception, cleanup/thread-leak, fallback classification, occupancy instrumentation, CUDA parity skipped unless CUDA present); genericity (three roles, one engine, exact names/shapes/dtypes, immutable QD4 policy); ownership (one read/role, join/adopt/already-ready, producer failure, timeout, cancellation-via-failure, strong lifetime); scheduler (full legal walk, illegal transitions loud, matrix denials/allows/conditional, gating rules, exclusive domains, forced releases, AST no-sleep scan, determinism); snapshot (determinism+sha, required/forbidden entries, quiescence violation listing, exclusions, immutable-absence); cache contract (miss/encode/persist); fallback (never-nominal); exactness (SHA constant, profile match, env gate, seams).

## 23. Synthetic/local benchmark evidence

`python tools/golden_local_benchmark.py` (64 MiB synthetic safetensors, 64×1 MiB blocks; artifact `R41_LOCAL_BENCHMARK_EVIDENCE.json`). LOCAL/SYNTHETIC ONLY — no Modal throughput conclusions:

- **A (mechanics, I/O-like 4 ms/block source latency)**: configured_qd=4, observed_max_outstanding=4, fraction_time_at_target_qd≈0.60–0.67 across runs, below-QD fully classified {other ≤2 ms, tail ≤2 ms}, staging bound 8×1 MiB, simulated steady-state ≈10–11 GB/s-class overlap behavior, counts reconcile 64/64.
- **B (decoupling)**: injected 20 ms/copy H2D ⇒ observed_max_outstanding=4 sustained, ~26–32 backpressure events, free_slots_min=0, completed_waiting_h2d_max_depth=8, unexplained below-QD ≤3 ms against a principled max(5 ms, 10%) tolerance ⇒ `decoupling_proven=true`.
- **C (timeline)**: quiescent capture ✓; deterministic snapshot sha; early UNET commit blocked by ForbiddenOverlapError ✓; CLIP→UNET→VAE all through one engine ✓; VAE demand joins owner (already_ready) ✓; duplicate CLIP owner rejected ✓; final status accepted_nominal; complete ordered event sequence captured.

These prove scheduler topology, resource exclusivity, occupancy mechanics, no-duplicate-reads, bounded staging, and event ordering. Physical GB/s claims are deliberately absent.

## 24. Unresolved physical-runtime questions

1. Actual Modal-volume QD4 source throughput after decoupling (historical 30–43+ GB/s class vs recent 2–7.7 GB/s integrated) — requires remote cohort.
2. Whether steady-state occupancy stays ≈4 on real hardware (expected; must be confirmed by `fraction_time_at_target_qd`).
3. VAE QD4 during sampling slack: measurable perturbation or not ("measure rather than assume").
4. Real H2D device-wall semantics on RTX PRO 6000 (E37/E39 recorded suspiciously low device ms vs PCIe bounds — instrumentation semantics need physical verification).
5. Serialized Modal snapshot size/composition observability (UNOBSERVABLE until Modal exposes it).
6. Host/provider variance envelope (telemetry-only; must not affect algorithm selection).

## 25. E40 reconciliation requirements

See `R41_E40_RECONCILIATION_MANIFEST.md` (path below). Summary: R41 modified ZERO shared files; three REQUIRED comfyapp-side hunks (CLIP call-site routing, load_models_gpu adoption consult, VAEDecode demand join), optional ledger/config/empty-cache integrations, and vocabulary mappings (RuntimeStatus, ledger sink, config truth) are documented there with expected conflict notes.

## 26. Shared-file conflict list

None. R41 touched only new files (`comfymodal_runtime/golden/**`, `tests/golden/**`, `tools/golden_local_benchmark.py`, two R41 markdown/json artifacts). `comfyapp.py`, `clip_qd_reader.py`, `model_preload.py`, `empty_cache_bypass.py`, profiles, and all E40-owned files are byte-untouched on this branch (verified via `git status`/commit contents).

## 27. Reconciliation manifest

`R41_E40_RECONCILIATION_MANIFEST.md` (same directory as this report).

## 28. Next remote validation plan (DESCRIBE ONLY — DO NOT RUN)

1. After E40/R41 merge onto the canonical checkout: deploy once via the canonical control plane (`v2ctl deploy-run --profile <golden-qd4>` extending `e37-clean-lane-qd4` with `COMFYMODAL_GOLDEN_PIPELINE=1`), single-use container.
2. Gate predicates: exact output SHA match; ledger sequence RESTORE_READY→…→FIRST_DURABLE_RESULT present; `fraction_time_at_target_qd` reported; conditioning forced_miss/encode=1/persist=0; zero fallback events; single take/bind per role.
3. Cohort: ≥6 true-cold runs, 35 s cooldown; record per-run aggregate/steady-state GB/s, occupancy fraction, backpressure totals, source latency distribution; classify any slow-QD4 run by drop-reason before drawing conclusions.
4. VAE-slack probe: one arm with VAE QD enabled vs disabled comparing sampler step times (perturbation check).
5. Only after those pass: consider G1-style confirmation cohorts. R41 ran none of these.

---

## Target ASCII Gantt (scheduler-permitted overlap only)

```
Lane                    0ms      100ms     200ms     300ms     400ms     500ms     600ms
                        |---------|---------|---------|---------|---------|---------|
PHASE1 RESTORE(minimal) ██
PHASE2 CLIP_QD4          ██████████████████
  src+h2d exclusive lane (cheap setup allowed)
PHASE3 CLIP_FWD(GPU)                        █████████████
PHASE3 UNET_PREP(CPU)                        ▒▒▒▒▒▒▒▒▒▒▒▒        ← ALLOWED overlap (CPU_HEAVY)
PHASE4 UNET_QD4(commit)                                   ███████████
  starts ONLY at CLIP_GPU_CRITICAL_DONE; storage released
PHASE5 SAMPLING(GPU)                                           █████████████████████████
PHASE6 VAE_QD4                                                      ▒▒▒▒▒▒               ← only AFTER
  src+h2d in sampling slack                                            FIRST_SAMPLER_STEP_PROVEN
PHASE6/7 VAE_DECODE                                                                              ████
PHASE7 OUTPUT → first durable                                                                       ██████
```

Legend: `█` exclusive execution; `▒` overlap explicitly permitted by the matrix (UNET_PREP under CLIP forward; VAE_QD under proven sampling). No overlap is drawn where the scheduler denies it (CLIP_QD vs UNET bulk; CLIP H2D vs UNET H2D; CLIP_GPU_CRITICAL vs UNET commit; VAE decode vs unsafe sampler mutation). Timings are schematic structure, not physical claims.

---

## Direct questions — answers

1. **Exactly one Golden model-loader engine?** Yes — `GoldenQD4Loader`; all roles route through it (genericity tests).
2. **CLIP/UNET/VAE all QD4?** Yes — `GOLDEN_ROLE_LOADER_POLICY` frozen mapping, immutability tested.
3. **Steady-state QD measurable, not just peak?** Yes — time-weighted `fraction_time_at_target_qd`, per-reason below-QD ms, samples at target; peak alone rejected by design.
4. **Can source workers be stalled by CUDA slot reuse?** Not anymore — workers never touch copy events; the only stall is bounded-ring backpressure, which is counted/classified (scenario B).
5. **Pinned memory bounded?** Yes — 8 × block_bytes ring (256 MiB at 32 MiB blocks); bound surfaced in telemetry.
6. **Whole-model pinning absent?** Yes — slots only; destinations are device buffers/params, never pinned wholesale.
7. **FastSafe during nominal Golden request?** No — policy mapping is immutable QD4; FastSafe exists only as an out-of-tree production fallback which would force DEGRADED.
8. **Native reread after successful QD?** Structurally prevented — registry admits one live owner/role; demand joins/admits; adoption seam documented for `load_models_gpu`.
9. **CLIP uncontested first storage priority?** Yes — PHASE2 gate + matrix deny CLIP_QD_SOURCE×UNET_BULK_SOURCE until release.
10. **When may UNET source preparation start?** After `CLIP_DEVICE_READY` (arms prepare) AND proof marker `CLIP_STORAGE_RELEASED` with clip storage grants absent — earlier attempts raise.
11. **When may UNET GPU commit start?** Only in PHASE4, i.e., after event `CLIP_GPU_CRITICAL_DONE` — never on a timer.
12. **Can UNET H2D overlap CLIP GPU-critical work?** No — H2D_HEAVY/GPU_MUTATION exclusivity + explicit deny; commit waits for critical-done.
13. **When may VAE QD4 start?** Only after `FIRST_SAMPLER_STEP_PROVEN` arms `vae_qd_armed` during SAMPLING.
14. **Can VAE demand trigger a second read?** No — demand joins the existing owner; absence yields a typed DEGRADED record, never a silent reload-as-nominal.
15. **Value payloads absent from intended snapshot?** Enforced — `validate_exclusions` fails on any nonzero weight-value bytes for the three roles.
16. **All model workers quiescent at capture?** Enforced — `assert_quiescent` enumerates readers/events/state/queues/owners/buffers violations.
17. **Conditioning always miss + encode=1 + persist=0?** Yes — `ConditioningContract` defaults + `validate_observed` raising on any deviation.
18. **Can immutable metadata randomly miss/recompute while remaining nominal?** No — `immutable_metadata_present` raises; absence forces DEGRADED/FAILED classification.
19. **Provider/region merely telemetry?** Yes — no placement appears anywhere in selection logic; recorded as documentation/telemetry only.
20. **What software mechanism could still make two nominal requests diverge?** Only inputs that legitimately change the plan (different workflow/model identities) or undiscovered E40-side flag leakage post-reconciliation; within R41's package, role policy, matrix, transitions, and ownership are deterministic and tested identical across repeated walks.
21. **What must be reconciled with E40 before remote validation?** The three comfyapp hunks + ledger/config/status vocabulary mappings + empty-cache routing — enumerated with symbols and conflict expectations in `R41_E40_RECONCILIATION_MANIFEST.md`.
