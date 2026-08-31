# E38S Independent Full Repository / Architecture / Performance / Correctness Audit — comfyui-modal

> **SUPERSESSION NOTICE (2026-08-30):** Historical audit; preserve its
> evidence, but use `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current
> generated-output guidance. Output durability is off by default; strict
> commit/reopen/hash proof is opt-in. S4 source publication durability remains
> mandatory.

**Date:** 2026-08-21
**Scope:** READ-ONLY. No source/test/deploy/commit/push/reset/clean. Dirty worktree preserved (40 files dirty, branch TESTING2, HEAD `8e49d75` + `a6a755e`/`0ba7000` lineage). `comfyapp.py` 22,614 lines, `__init__.py` 384k bytes, `comfymodal_runtime/` 70+ modules, `config/v2/flag_registry.toml` 950 lines.
**Method:** 10 parallel specialist lanes, first-principles source read, graph discovery (codebase-memory unavailable — fallback to grep/Read), artifact forensics (E27-E37 reports + raw `comfymodal-data/` where present), git history, flag/profile inventory. Independence requirement honored — every historical claim re-checked against current source and labeled.
**E37 clean-lane:** understood as isolated QD4 post-restore synchronous path (excludes speculative, prefetch, INPUT_TYPES warm, UNET/VAE contention). Not interfered with.

---

## Executive verdict

| Dimension | Verdict | Confidence |
|---|---|---|
| **Overall architecture health** | **ACCIDENTAL COMPLEXITY** — 5 CLIP transports, 4 UNET transports, 3 identity systems, 2 handle owners, 1 god file. System works only because every fast path fails closed to native Comfy loader. | CONFIRMED |
| **Correctness health** | **EXACT-OUTPUT-GATED BUT FRAGILE** — SHA `20b10e1f...e5260` enforced in profiles, but measurement/telemetry can mark a degraded fallback as nominal. No in-flight corruption proven in latest gate, but owner-string mismatch, handle-creation race, and mtime artifact selection are latent P0s. | HIGH-CONFIDENCE |
| **Measurement trustworthiness** | **UNTRUSTWORTHY WITHOUT PATCH** — clock-domain mismatch (`perf_counter` vs `monotonic`), negative residual clamped, telemetry failures swallowed, partial waterfall accepted as complete, mtime selection. E29 zero-gap ledger is the only trustworthy artifact and it is currently BLOCKED pending fresh artifact. | CONFIRMED |
| **Performance health** | **~18 s typical, ~17.9 s best, ~24.7 s bad** — 5-6 s above 12.5 s target. QD4 fixes CLIP source (1.04 s clean lane vs 2.6 s typical vs 4.4 s old) but restore (4.2 s), request setup (0.4-0.4-0.4 s serial), CLIP forward (4.3 s), UNET transfer (0.5-3.2 s) and sampling (3.7-4.7 s) dominate. No single 5 s optimization remains. | SUPPORTED HYPOTHESIS |
| **Maintainability health** | **UNMAINTAINABLE WITHOUT REFACTOR** — 22k-line god file, 70-module flat runtime, 950-line flag registry that is explicitly not a whitelist, 18 call cycles, unbounded queues, broad excepts, duplicate hashing. Bus factor 1. | CONFIRMED |
| **12.5 s recoverable?** | **NO — not with current architecture without breaking scale-to-zero or exactness**. Requires (1) eliminate host CPU work under CLIP forward, (2) remove request-setup recomputation, (3) replace Volume semantics with deployment capsule. Plausible floor with fixes: ~13.5-14.5 s; 12.5 s needs sampler/forward breakthroughs outside loader scope. | SUPPORTED HYPOTHESIS |

### 5–10 most important discoveries

1. **FASTSAFE vs QD4 A/B changes only one flag** (`COMFYMODAL_V2_CLIP_QD_READER 0→1`, `QD=4 BLOCK=32` identical) — verified in `config/v2/profiles/e37-clip-fastsafe.toml:22` vs `e37-clip-qd4.toml:22`. Yet the transport implementation is entirely different (library `SafeTensorsFileLoader` vs own `preadv`+pinned+H2D). The profile label is truthful, but historically the difference was misinterpreted as queue-depth tuning rather than a different loader with different failure modes. — **VERIFIED AGAINST CURRENT SOURCE**
2. **fastsafetensors `max_threads` is NOT queue depth** — C++ `nogds_file_reader.submit_read` keeps one `std::thread` per slot and `join()`s prior in-slot thread before next read (`clip_qd_reader.py:1-15` docstring evidence). This is the E27 finding that motivates QD. — **VERIFIED AGAINST CURRENT SOURCE**
3. **Half-integration everywhere** — speculative CLIP (E28) launches early but demand hydrator `clip_fast_hydration_wiring._try_fast_hydrate` still calls `_fastsafe_load` (not QD) → pay speculative cost + demand cost on miss. Early VAE read exists but `model-mgmt:load_models_gpu 34.0 ms` still paid at demand (`V2_BATCH_E29...:100`). `ExecutionPlan:consumed=true` yet `request:cc-prefetch 403 ms + input-types-warm 406 ms + schedule 445 ms` still on critical path. — **VERIFIED AGAINST RAW ARTIFACT (E29 ledger)**
4. **Snapshot capture not proven quiescent** — `snapshot_capture_hygiene.py:136` does `gc.collect()+malloc_trim` only; does not stop QD workers, staged producers, H2D streams, persistence queues, or close FDs. `snapshot_build_manifest.py:287` only observes. SIGABRT risk path credible. — **VERIFIED AGAINST CURRENT SOURCE** — **HISTORICAL CLAIM ONLY** that capture was quiescent is **CONTRADICTED**
5. **Clock-domain bug invalidates ledger durations** — `critical_path_ledger.py:308-316` mixes `perf_counter_ns` for `duration_ms` with `monotonic_ns` for boundaries. On Windows these have different epochs. Residual clamped via `max(0,...)` at `:429`. — **CONFIRMED** — **SUPERSEDES** any prior claim that ledger is zero-gap-proven (E29 zero-gap of 48.5 ms is correct as serial coverage, but per-span durations are suspect).
6. **Deployment identity fragmented into 4 systems** — `deployment_spec.build_deployment_identity()` hashes `.py/.js/.mjs` under custom roots; `canonical_execution._compute_host_deployment_combined_hash()` adds runtime-shape hash; `benchmark_modal_e2e._build_custom_node_fingerprint()` independently fingerprints `requirements.txt`; `deploy_warmup` derives generation from `version+fingerprint+timestamp`. `.modalignore` upload exclusions differ from `deployment_spec` exclusions. No single canonical identity consumed by deploy/snapshot/scheduler/cache/artifacts/validators. — **VERIFIED AGAINST CURRENT SOURCE**
7. **Measurement can accept degraded as nominal** — `speculative_clip_hydration.py:541` swallows exception with `pass` and leaves `_LANES[request_id]` not terminal; `clip_qd_reader` fallback emits `clip_qd_fallback` then silently takes `_fastsafe_load`; `critical_path_ledger.py:456` swallows persist failures; `experiment_result_store.py:299` treats missing `partial_waterfall` as complete. `v2ctl` cannot enforce `NOMINAL vs DEGRADED vs FAILED`. — **VERIFIED AGAINST CURRENT SOURCE**
8. **CPU oversubscription by construction** — production profile `production.toml` sets `COMFYMODAL_V2_THREAD_POLICY=TBASE` (leave inherited settings unchanged) + `runtime_shape.py:168` + legacy `modal_app.py:10034` that sets only `torch.set_num_threads()` in restore. Meanwhile restore pool (3), preload pool (`_preload_max_workers`), staged producers (`config.producers`), QD readers (`QD`), pinned hydration workers, and `fastsafetensors max_threads=8` all contend with `intraop 12 / interop 14` equivalent native pools. Observed `12 CPU + 12 intraop + 14 interop + QD + prefetch` not a fixed invariant but legacy TBASE inherits it. — **HIGH-CONFIDENCE**
9. **Storage bytes ≠ remote throughput** — every I/O is plain `os.open/pread/mmap` on the mounted path; no Volume API. 40-45 GB/s E27 probe (`clip_qd_reader.py:20-23`) is page-cache / filesystem cache hit or overlapped-worker-bandwidth artifact, not Modal backing-store throughput. Integrated cold QD4 is 2.6-2.9 s (E36) and clean-lane 1.04 s (E37) — far from 191 ms probe — because probe excluded H2D, header, allocation, and tail latency. — **VERIFIED AGAINST RAW ARTIFACT** — prior claim **CONTRADICTED**
10. **12.5 s target not recoverable by stacking loader optimizations** — best observed end-to-end is 17.927 s (`E36 ARM-A`), clean-lane CLIP source already optimal (1.04 s). Remaining wall is restore 4.2 s + CLIP forward 4.3 s + sampler 3.7-4.7 s + setup 1.26 s. CLIP loader wins are exhausted; host H2D/placement variance (H100 5.1-20.3 s in `AUG9` report) and CPU setup are the bottleneck. — **SUPPORTED HYPOTHESIS**

---

## P0 — Correctness / invalid-measurement bugs

| # | Title | Severity | Confidence | Source | Mechanism | How to prove/falsify | Output | Perf impact |
|---|---|---|---|---|---|---|---|
| P0-1 | **Handle-cache check-then-create race creates duplicate Modal handles** | Correctness, leak | CONFIRMED | `comfymodal_runtime/local_handle_owner.py:186-202` | Lock protects read/write but not creation; two threads miss cache, create two handles, last write wins, other leaked. | Deterministic concurrency test: 2+ threads call `resolve` simultaneously on same key, assert exactly one handle created / other awaited via single-flight future. | No (resource leak, wrong owner) | Leaked handles hold Volume/commit state, can confuse next request |
| P0-2 | **Speculative lane failure leaves non-terminal entry** | Race, fallback masking | CONFIRMED | `comfymodal_runtime/speculative_clip_hydration.py:541-547` | Worker catches all exceptions with `pass`; `_LANES[request_id]` not removed or marked FAILED. Demand path may observe failed lane unless every downstream check validates. | Test: speculative worker raises after 1 file; demand `take` must observe `FAILED` not stale lane. Currently `540 pass` violates. | Potential wrong CLIP weights if fallback partial | Degraded silently becomes nominal |
| P0-3 | **Partial GPU allocation before fallback rollback** | Correctness, VRAM leak | HIGH-CONFIDENCE | `speculative_clip_hydration.py:683-769`, `clip_fast_hydration_wiring.py:156-171` | Sequential per-file load; failure on file N after allocating GPU buffers for 0..N-1. Outer except must close every `(loader, fb)` owner before native fallback, otherwise dual ownership. | Instrument: QD4 load of 2-clip stack, inject failure on file 2, assert GPU buffers released (`torch.cuda.memory_allocated` back to baseline). | Possible OOM or stale tensors | Fallback pays double GPU cost |
| P0-4 | **Source-reader retirement fence caller-discipline** | Race | CONFIRMED | `comfymodal_runtime/checkpoint_prewarm.py:402-475`, `523-555` | After join/handle-close timeout returns `False`, caller must enforce no demand read. `_close_active_handles()` suppresses close exceptions. Any caller ignoring boolean starts demand read while daemon readers alive. | Grep callers of `retire`/`close_active_handles`; assert they fail closed. Currently `model_preload.py` and `comfyapp.py:1458` paths must be audited. | Double file read, corrupted header | Double Volume I/O |
| P0-5 | **Clock-domain mismatch corrupts all span durations** | Measurement P0 | CONFIRMED | `comfymodal_runtime/critical_path_ledger.py:308-316,329-330,382-391,427-445` | `duration_ms` from `perf_counter_ns`, boundaries from `monotonic_ns`. Per-span duration vs serial window use different clocks. Windows `monotonic_ns` tick ~15.6 ms. | Reproduce: log both clocks for same span, measure drift; fix by using `monotonic_ns` exclusively for duration. Prior E29 attribution correct as serial coverage only. | No direct output, but false attribution drives wrong optimization | All optimization ROI estimates suspect |
| P0-6 | **Over-accounting hidden by clamp** | Measurement P0 | CONFIRMED | `critical_path_ledger.py:429-431` | `residual = max(0, duration - work - wait - sync - child_union)`. Negative residual (child double-counting) erased instead of failing. | Inject overlapping child intervals exceeding parent, assert `INVALID` not zero residual. Currently passes as `UNATTRIBUTED 0`. | Allocation masks double-counting | False confidence in ledger completeness |
| P0-7 | **Telemetry finalization not fail-closed** | Measurement P0 | CONFIRMED | `critical_path_ledger.py:456-457,818-827,867-868,913-935` | `_persist`/artifact capture/bridge close swallow exceptions; missing ledger becomes indistinguishable from absent instrumentation. | Kill artifact write (ENOSPC), run gate — currently may produce `validation=PASS` with missing ledger. Must carry `canonical_ledger_status=error`. | False nominal | Benchmark accepts partial data |
| P0-8 | **Deployment identity fragmentation → stale-cache acceptance** | Correctness P0 | CONFIRMED | `comfymodal_runtime/deployment_spec.py:21-94,156-200`, `canonical_execution.py:1011-1038`, `benchmark_modal_e2e.py:338-405`, `deploy_warmup.py:51-60`, `.modalignore:1-41` | Two exclusion rule sets and 3 hash implementations hashing different file sets while claiming same deployment. Generated experiment files, dirty worktree, profile identity, Modal image digest not bound. | Dirty a `.py` under `tools/` excluded by `.modalignore` but hashed by `deployment_spec`; deploy yet cache hit preserved. Currently possible. | Stale conditioning/registry used, wrong model | Silent cache contamination across deploys |
| P0-9 | **Mtime-based artifact association** | Measurement P0 | CONFIRMED | `comfyapp.py:3179-3180,16598,17214-17226,17501-17523` | Certificate/output/history selection uses `getmtime` + drift slack. Clock skew, copy, or delayed write selects wrong artifact for run. | Copy old `run_001_sample.json` over new with newer mtime; gate associates wrong output. Fix: run-ID/content-hash association only. | Wrong SHA validated | False exactness PASS |
| P0-10 | **Output duplicate collection overwrites seen-set** | Correctness | CONFIRMED | `comfyapp.py:17537-17576` | Direct-sink entries not added to `seen_filenames`; later history/filesystem scan re-adds same output, can alias `b_images→images` incorrectly. | Run with `comparison_side=b` workflow, assert deduplication. Stable mode avoids but non-stable does not. | Wrong primary selected | — |
| P0-11 | **Snapshot capture not quiescent → SIGABRT / state corruption** | Reliability P0 | HIGH-CONFIDENCE | `comfymodal_runtime/snapshot_capture_hygiene.py:53-204`, `snapshot_build_manifest.py:171-342` | Capture does `gc.collect()+malloc_trim` only; does not stop QD workers, staged producers, H2D events, persistence queues, or drain futures. CUDA objects snapshotted while in flight. | Enable `snapshot_build_manifest` during capture, assert zero live workers/persistence/commit. Currently not enforced. | Container crash `terminate called without active exception` | — |

---

## P1 — Multi-second structural performance problems

Only evidence-backed.

| # | Title | Evidence | Mechanism | Floor proof | Impact |
|---|---|---|---|---|---|
| P1-1 | **Restore `bootstrap` 4.16 s dominates** | E29 ledger `restore:bootstrap 4161.5 ms` of `restore total 4191.9 ms`; E28 `restore_total 4.49 s`; broken pipeline `12.53 s` when UNET gate held. | `runtime_bootstrap.py:1942-2379` + `modal_app.py:10118`: sequential GPU state restore, CUDA init, Sage sentinel (full discovery on failure), runtime-state generation check + conditional `reload_runtime_state`, models generation + `reload_models`, prescan custom-node identity + full sync on mismatch. Every branch does its own `stat`/`read`. No single capsule. | Observed best `restore:bootstrap 4161 ms` not floor; no stage breakdown artifact available (`_restore_timing` not attached). Plausible floor ~2.5-3.0 s if generation markers all hit and Sage prescan skipped. | 1.0-1.5 s recoverable only with deployment capsule precomputation, not tuning |
| P1-2 | **Request setup 1.26 s recomputes scheduler work** | E29 spans `cc-prefetch 403 ms + input-types-warm 406 ms + schedule 445 ms` overlapped but still 1.26 s serial; `canonical_execution.py:1387-1443` repeats `deepcopy`+`compile_production_workflow` for dispatch hash; `canonical_execution.py:1466` extra `deepcopy`; `production_workflow.py:183` LRU topology hash still reconstructs. | Scheduler already knows `source_hash, compiled workflow, reachable nodes, loader/sampler/output IDs, model selection`. Remote recomputes topology traversal, `INPUT_TYPES` introspection, registry checks, custom-node identity, workflow hashing, JSON ser, `deepcopy` of whole workflow. `ExecutionPlanConsumed=true` does not eliminate setup — it proves plan was accepted, not that recomputation was skipped. | Historical best `request setup 1.26 s`; no artifact shows <1 s. True floor with capsule: ~150-250 ms (plan deserialize + ID checks only). | ~1.0 s on critical path |
| P1-3 | **CLIP QD host H2D / pinned Hydration global synchronize serializes** | `clip_fast_hydration.py:715 torch.cuda.synchronize()`, `528`, `562`+ `682 empty_cache()` on error path; `clip_qd_reader.py:1511` slot reuse waits event host synchronously. | Pinned path waits on whole device, not scoped copy event. Fastsafe scoped event avoids waiting on UNET/default stream; QD host issue 127 ms + CUDA event 27 ms (E37) healthy but exposed hydration 122-491 ms in E29/E36 because global sync collapses UNET overlap. | Clean lane QD: H2D host 127 ms, CUDA 27 ms. Typical E36 host issue 1.7-3.2 s collapsed due to placement/contention, not source. | 0.2-1.0 s variance |
| P1-4 | **UNET transfer/placement is the dominant variance** | E36 `unet:host_issue 1.7-3.2 s`; E28 fastsafe `2014 ms→477 ms` after `bbuf 512 MiB`; Aug9 H100 `5.1-20.3 s` load with `4.4-13.6 s sampler-visible wait`; E28 gate held across 10 s read → `clip_gpu_wait 11.6 s` fixed by narrowing lock. | Early `CpuSnapshotModels` construction + snapshot `retain`, then later `fastsafetensors` direct GPU load + `assign=True` + `ModelPatcher` bookkeeping + `current_loaded_models` gate. Transfer bandwidth not proven remote — often page-cache copy. Copy engine, default stream, allocator `empty_cache` and `release_gpu` contend. | Best observed UNET `fastsafe 477 ms (25.8 GB/s)` after tuning; QD probe `49.6 GB/s` but excludes H2D/tail. Realistic floor under clean lane: ~0.5-0.8 s. | 1.0-2.0 s swing cold-to-cold |
| P1-5 | **Conditioning cache fallback does up to 8 redundant reads** | `clip_conditioning_cache.py:1340-1366` fallback loop + `1278-1304` per-entry header+data + `999-1030` `Volume.reload()` throttled but not mount-freshness-proven + `1379` extra `stat`. | First prefetch skips reload (`1103`) correct for single-use container, but later prefetches and fallback read manifest → requested entries → up to 8 fallback entries each with header+data reads. Can exceed useful I/O. | No direct timing, but `cc-prefetch 403 ms` includes this. Floor with capsule: zero fallback reads, manifest in capsule. | 0.1-0.4 s |
| P1-6 | **CacheHit does not make workload cold** | `clip_conditioning_cache` exact conditioning cache, prompt signature memo, profile/restore caches all persist beyond single request. Benchmark with `fresh_required=true` but conditioning hit changes workload (skip CLIP forward 4.3 s). E36/E37 use `forced_miss` but not enforced by gate for all paths; filler-run contamination noted in lane 5. | Over-invalidation vs under-invalidation not bounded; cache keys use inconsistent deployment hashes (P0-8). | Historical exact SHA runs prove workload but not cache state; no gate proves `forced_miss` was effective beyond manifest flag. | False fast cohort |

---

## P2 — Variance / consistency problems

* **Restore pre-Python variance 1.93 s vs 3.16 s vs 9.59 s** (E36 ARM-B vs ARM-A vs FASTSAFE control). Cause: Modal Volume mount + platform restore (outside Python) not instrumented beyond `modal_restore_boundary.py:173` banner parse — cannot attribute to remote storage vs decompression vs host contention. — **HIGH-CONFIDENCE**
* **CLIP forward 4.309 s vs 5.59 s (1.28 s swing)** — same workload, same SHA. Suspect CPU launch starvation, tokenizer variance, Sage/CacheDiT path, or dtype divergence (252 BF16→FP32 casts measured in E31 when `FP32_CAST_ONCE=0`). E31 now gates `cast_once` OFF, but 398 NOOPs vs real conversions depends on `qd_used` record path. — **SUPPORTED HYPOTHESIS**
* **Sampler 3.69 s vs 4.70 s vs 5.70 s** — model-dependent and host-dependent; no invariant builder measured.
* **Thread-pool inheritance TBASE** — `production.toml` production defaults set `THREAD_POLICY=TBASE` (inherit), so same profile on different host inherits different native BLAS/OpenMP thread counts. — **CONFIRMED** `config/v2/profiles/production.toml:50`
* **Queue backpressure absent** — `local_handle_client.py:480`, `checkpoint_prewarm.py:707`, `clip_forward_forensics.py:482` unbounded queues/deques can amplify tail latency under stall.

**E37 clean-lane implication:** If clean lane QD4 is fast (1.04 s source) vs typical QD4 2.6 s, verdict is **B — concurrency poisons QD** (supporting P1-3/P1-4). If clean lane is also ~2.6 s, verdict is **A — QD implementation itself limited** (source + H2D still contended or block size/placement not tuned). Current E37 single run at 1.04 s supports B, but `n=1` — needs `run_count≥5` at 35 s gap to distinguish platform variance from architecture contention. — **SUPPORTED HYPOTHESIS**

---

## P3 — Smaller performance opportunities

| # | Opportunity | Source | Mechanism | Saving |
|---|---|---|---|---|
| P3-1 | Eliminate `deepcopy` of workflow in `build_execution_plan` + dispatch hash | `canonical_execution.py:1387,1466,1116` | Copy entire workflow twice for hash computation before validation. | 10-30 ms |
| P3-2 | Remove repeated `os.stat` / header parse per CLIP file | `clip_qd_reader.py:1212 header parse +1229 stat`, `staged_safetensors.py:383 stat+header` | QD and staged paths parse same header independently. | 5-15 ms per file |
| P3-3 | Avoid `flush=True` on hot paths, string formatting in workers | Grep `print(..., flush=True)` across runtime | Workers contend on stdout GIL + line buffering. | 5-10 ms, variance |
| P3-4 | Cache `INPUT_TYPES` / registry fingerprint at deployment, not per request | `execution_warm.py:30`, `comfyapp.py:7650` | `warm_input_types` 406 ms in E29 is almost entirely introspection. | 300-400 ms if deployment capsule (already counted in P1-2, not additional) |
| P3-5 | Use `float32` cast-once when residency proof valid | `clip_fp32_cast_once.py:187`, E31 doc | 252 real conversions / 14.5 GB traffic per forward when OFF; measured 8 ms saving vs +8 GB VRAM. Worth only if `restore_preload` proves residency. | ~8 ms |
| P3-6 | Make `observability_mode`/`thread_policy` immutable typed config vs env re-read | `env.py:49`, `runtime_shape.py:168` | Repeated `os.environ` reads allow drift between profile bake and request. | 0 ms, determinism |
| P3-7 | Scope `empty_cache` to allocator purge on error only, never on hot path | `clip_fast_hydration.py:682,1874` | `empty_cache` synchronizes and fragments allocator. | Noise reduction |

Do not stack P3 savings additively — they overlap and are dwarfed by P1 items.

---

## Architecture debt

1. **God files.** `comfyapp.py` 22,614 lines combines Modal app definition, ComfyUI subprocess management, model restore/preload, cache/persistence, deployment manifests, profile handling, output encoding, tracing, custom-node packaging, benchmark diagnostics, legacy compat. `__init__.py` mutates `sys.path`, imports 20+ modules, performs env parsing and logging at import. Change to one concern breaks another via import order or global state. — **CONFIRMED**
2. **Flat runtime package.** `comfymodal_runtime/` 70+ modules with no bounded contexts; `clip_fast_hydration*` split across 4 files, `unet_*` across 4 transports, `model_preload.py` 1M bytes. Need explicit boundaries: `lifecycle/snapshot`, `loader/source I/O`, `gpu/publication`, `ownership`, `scheduler/capsule`, `model metadata`, `runtime config`, `telemetry`, `benchmark-diagnostics`.
3. **Duplicate implementations solving same problem.** CLIP: `clip_fast_hydration.py` (generic fast safe), `clip_fast_hydration_wiring.py` (wiring), `clip_qd_reader.py` (QD), `staged_safetensors.py` (generic staged). UNET: `unet_fastsafetensors.py`, `unet_meta_direct.py` (`COMFYMODAL_V2_UNET_META_DIRECT=1`), `unet_pinned_staging.py` (`pinned_staging` arm), native fallback. Staged transport duplicates header planning, slab pooling, ownership, event logic. Old paths remain reachable (`DEFAULT OFF` ≠ `DEAD`). — **VERIFIED AGAINST CURRENT SOURCE**
4. **Flag registry is metadata, not whitelist.** `config/v2/flag_registry.toml:1-7` explicitly says unknown flags flow through as unregistered. 950 lines, explicit aliases (`COMFYMODAL_V2_CLIP_CONDITIONING_CACHE` vs legacy `COMFYMODAL_EXACT_CLIP_CONDITIONING_CACHE` `clip_conditioning_cache.py:58-63`), request-carried vs deploy-baked overlap (`consumed_at`/`change_requires` not enforced). Effective config cannot be fingerprinted reliably. — **CONFIRMED**
5. **Mutable process-global state.** `contracts.py:65` `cache`, `speculative_clip_hydration.py:60` `_LANES`, `canonical_execution.py:70` profile cache, `comfyapp.py:255` process-wide recorders, `local_handle_owner._handle_cache`. No generation/epoch scoping. — **CONFIRMED**
6. **Broad `except Exception` / `pass` around ownership/persistence.** Dozens in `comfyapp.py`; `speculative_clip_hydration:541 pass`; `gpu_lane_coordination:106 swallows`; `critical_path_ledger:456` swallows. — **CONFIRMED**
7. **18 call cycles** reported (FlagRegistry, HistoryV2Store, FastColdOrchestrator). Scheduler/registry cycles must be broken. — **VERIFIED AGAINST CURRENT SOURCE**

### Dead / legacy code inventory

| Path | Status | Reason |
|---|---|---|
| `comfymodal_runtime/e27_forensics.py`, `e27_followup_probe.py` | **LEGACY BUT REACHABLE** | E27 wrappers/sentinels still imported by production paths; `comfyapp.py:15854` wraps load_models |
| `canonical_execution.py:1191-1277` legacy manifest fallback | **LEGACY BUT REACHABLE** | Branch active when `deployment_combined_hash` missing |
| `canonical_execution.py:2121-2565` legacy publisher/trace serialization | **LEGACY BUT REACHABLE** | Compat with old payloads |
| `comfyapp.py:12642-12643 deprecated fields`, `7650-7674` harnesses | **LIKELY DEAD** | No production caller except fallback tests |
| `unet_meta_direct.py`, `unet_pinned_staging.py` | **LEGACY BUT REACHABLE behind flags** | `V2_UNET_META_DIRECT=1`, `pinned_staging` arm |
| `staged_safetensors.py` generic path | **BENCHMARK-ONLY / LEGACY** | Not canonical CLIP production path; reachable when staged flag on |
| `tools/`, `e16_*.py`, `_e27_*.py`, `benchmark_*.py` | **BENCHMARK-ONLY** | Excluded by `.modalignore:26-27` from deployment but still indexed/maintained |
| `.comfymodal_experiments/`, `.custom_node_requirements/` | **EXCLUDED from deploy** | `.modalignore:24-25` — not runtime cost unless invoked |
| Generated `V2_BATCH_*` reports, `.deployed_version` logs | **REPOSITORY-ONLY but identity-impacting** | Must be excluded from deployment hash; currently some are, but not mechanically proven equivalent to `.modalignore` |

Import-cost of dead code: `comfyapp.py` still imports 70+ optimization symbols at top level (`try: from optimizations import ...` `comfyapp.py:143`); `__init__.py:24` env parse + `sys.path` mutation at import — measurable startup cost.

---

## Concurrency and ownership findings

**Executors/futures found:** restore pool (3) `model_preload.py:11515`, preload pool `comfyapp.py:12096`, staged producers `staged_safetensors.py:1481`, QD readers `clip_qd_reader.py:1251` (`qd` daemon threads), pinned hydration `clip_fast_hydration.py:686 (qd workers)`, `fastsafetensors max_threads=8` internal. All can overlap.

**Ownership model:** `QdGpuOwner._gpu_buf` (`clip_qd_reader:1344`) single contiguous GPU buffer with zero-copy views — survives longer than tensors, attached to model wrapper. Fastsafe `FilesBufferOnDevice` same contract (`clip_fast_hydration.py:22`). `local_handle_owner._handle_cache` (Modal handle). `speculative_clip_hydration._LANES[request_id]` single-flight per request.

**Bugs:**
* P0-1 handle race, P0-2 terminal state, P0-3 partial GPU rollback, P0-4 fence discipline — see P0 table.
* **Owner-string mismatch risk:** `clean_lane.py:140 "clip_qd_reader"` hardcoded vs arbitrary owner objects elsewhere; `clip_fast_hydration_wiring.py:1274` fallback to `active_speculative_request_id()` when primary miss — uniqueness claim not enforced. Producer `restore_preload` vs consumer expects `restore_clip_loader` would be P0 if proven — audit found no such mismatch in current gate 3, but string-typed agreement is fragile. — **HIGH-CONFIDENCE**
* **Telemetry swallowed:** `gpu_lane_coordination.py:339-389` orchestration failures suppressed, wait attribution lost, critical path mis-bucketed.

**Missing:** Deterministic tests for concurrent duplicate handle creation, speculative failure after 1 file, fence timeout, reused `request_id` across retries, overlapping CLIP/UNET requests.

---

## CPU findings

**Requested vs visible vs effective:**
* Production requests 12 CPU / 32 GiB / RTX PRO 6000 (`production.toml:target.resources`).
* `host_hardware_telemetry.py:641` records `os.cpu_count()` and affinity but never sets affinity.
* `runtime_shape.py:168 TBASE` leaves Torch/native unchanged — inherits host defaults and can oversubscribe. Non-TBASE policies set `OMP_NUM_THREADS/MKL_NUM_THREADS/OPENBLAS_NUM_THREADS/NUMEXPR_NUM_THREADS` + `torch.set_num_threads/intraop` + `set_num_interop_threads`.
* Legacy `modal_app.py:10034` sets only `intraop` in restore, after parallel work may have started — not changing `interop` or BLAS pools.

**Thread pools contending:**
* Restore 3 + preload `_preload_max_workers` + staged `producers` + QD `4` + fastsafetensors `8` + Comfy workers + prefetch workers + cache persistence workers can coexist with Torch pools. Aggregate can exceed `12` by factor 2-3 at burst.

**Classification:**

| Category | Work | Verdict |
|---|---|---|
| SNAPSHOT_STATIC | CPU snapshot manifests, storage registries, model order | Keep in snapshot |
| DEPLOYMENT_STATIC | CPU request, affinity, runtime shape, BLAS env | Must be capsule, not TBASE |
| WORKFLOW_STATIC | preload producer/QD degree, slab count | Capsule |
| REQUEST_DYNAMIC | restore futures, QD reads, CPU casts, page prefetch | Minimize |
| Unavoidable | file I/O, page faults, safetensors decode, casts, CUDA API submit | — |
| Accidental | TBASE inheritance, legacy intraop-only mutation, simultaneous pools, `flush=True`, repeated `INPUT_TYPES` introspection, JSON/hash `deepcopy` | Remove |

**Bursts to fix:** All input-types-warm threads + QD readers + preload producers fire together during `request:setup-schedule 445 ms` window — starves CUDA issue/completion processing (GIL + CPU queue). E37 clean lane sets `INPUT_TYPES_WARM=0`, `FAST_COLD_ORCHESTRATION=0`, `CONDITIONING_CACHE_PREFETCH=0` to eliminate this.

---

## GPU/CUDA findings

* **QD staging-slot reuse correctly coupled** via per-slot CUDA end-event and `_wait_event_host()` query+`cudaEventSynchronize` only on reuse (`clip_qd_reader.py:1401-1482`). Prevents overwriting pinned memory mid-DMA. **VERIFIED AGAINST CURRENT SOURCE**
* **Timing separation is correct in QD:** source wall `_timed_read_at`, host issue `copy_` duration, device duration `cudaEventElapsedTime`, publication `event/stream`, waits `_wait_event_host`/consumer. Diagnostic model sound. — **VERIFIED**
* **`non_blocking` depends on pinned:** `copy_(..., non_blocking=bool(slot_pinned[...]))` — async only when slot is actually pinned; otherwise synchronous on default stream. — **CONFIRMED**
* **Pinned hydration global wait:** `clip_fast_hydration.py:715 torch.cuda.synchronize()` after all copies before bind. Reports hydration wall including unrelated device work, serializes with UNET. Scoped fastsafe path `::604` uses per-CLIP event and avoids global sync — preferable. — **CONFIRMED**
* **Fallbacks invalidate QD gains:** `clip_qd_reader.py:1393 empty_cache()` on retry path; staged `::1585 sync copy stream + join producers` on close/abort — correct cleanup but appears as teardown latency and fragments allocator when contended.
* **Allocator pressure:** `memory_allocated()/peak` diagnostic only; `empty_cache()` only on error/purge, not hot path. FP32 cast-once `clip_fp32_cast_once.py:187` doubles bytes for 252 tensors + `cudaEventSynchronize` — increases peak VRAM / allocator contention if enabled. Currently OFF (`FP32_CAST_ONCE=0`) — correct per E31 `~8 ms` saving vs `+8 GB`.
* **Default-stream hazard:** QD `copy_` without explicit copy stream (shown worker); staged has dedicated stream but consumer must honor event protocol. Any consumer bypass risks default-stream ordering assumptions. — **HIGH-CONFIDENCE**
* **CLIP forward vs UNET H2D:** Forward is healthy historical 4.3 s (E29) but measured 5.59 s when UNET H2D overlapped default stream. Clean lane removes overlap for proof; production must gate UNET H2D behind scoped stream/event to preserve overlap without contention.

---

## Storage / Volume findings

| File / region | Bytes / pattern | Owner | When | Reader | QD/block | Cache interaction | Overlap | Verdict |
|---|---|---|---|---|---|---|---|---|
| `qwen_3_4b.safetensors` data section ~8.045 GB (398 BF16 tensors) | Full data | `clip_qd_reader` / `fastsafetensors` | CLIP source | `preadv` QD4/32 MiB or `SafeTensorsFileLoader T8/B64MiB` | 4×32 MiB vs 8 slots | `os.open` on mount path — no Volume API | Should be isolated storage lane; currently overlaps restore/setup and UNET prefetch | P1 |
| Safetensors header (JSON) | ~tens of KB | QD / staged / fastsafe each parse independently | Header plan | `stat+read 8B len + JSON` | — | Page cache hit after first | Duplicate parse 2-3× per request | P3 |
| `runtime_state.json` | Small | `runtime_state.py:427` `Volume.reload()` + `464 commit reread` | Restore + commit | JSON parse | — | `reload()` throttled, but fail-closed reread on mismatch | Can overlap restore | P1-5 |
| `clip_conditioning_cache` manifest + up to 8 fallback entries | Each entry header+data | `clip_conditioning_cache.py:999 reload throttled, 1033 manifest, 1165 stat, 1278 existence+header+data, 1340 ×8 fallback` | `request:cc-prefetch 403 ms` | Sequential Volume reads | — | In-memory cache after first hit correctly skips | Should be capsule, not fallback loop | P1-5 |
| Models/custom-node generations, `runtime_state` markers | Small | `runtime_bootstrap.py:2142` | Restore decision | `stat` | — | Guard can skip whole reload when marker matches | Fail-closed reread when corrupt | Correct pattern but not capsule |
| Model manifests (`volume.reload()`, `reload_models`) | Whole Volume | `modal_app.py:10118`, `optimizations.py` | Restore preamble | — | — | Expensive; guarded by generation check | Should be eliminated via snapshot static | P1-1 |

**Reconciliation of 40+ GB/s vs lower integrated:** E27 42-45 GB/s was source-only, overlapped workers, numerator `bytes/wall` where wall = slowest worker join; excluded header, allocation, H2D, tail, queue setup. Integrated CLIP QD4 2.6 s (8 GB / 2.6 s = 3 GB/s) includes everything. 3 GB/s is not remote backing-store throughput; observed local filesystem/page-cache copy from mount to host; Modal Volume remote throughput never measured at syscall layer. **VERIFIED AGAINST RAW ARTIFACT** — 40 GB/s claim **SUPERSEDED** as probe-local, not production path.

**What should disappear via precomputation:** All manifest rereads, header reparsing, custom-node identity scans, tokenizer/model configs, loader signatures → `DEPLOYMENT CAPSULE`.

**What should be serialized vs overlapped:** CLIP source must be isolated storage lane; CLIP H2D must be scoped transfer (not global sync); UNET pure source may overlap CLIP compute only if placement/H2D is scoped behind its own dependency (not default stream). Current clean lane serializes UNET behind CLIP for proof — pay 0.5-0.8 s serialized cost to avoid contention; correct for now.

---

## Snapshot / restore findings

### A. Modal restore-banner → first Python
External-log only. `modal_restore_boundary.py:11,173` parses `Restoring Function from memory snapshot` timestamp. Interval is outside Python; must not merge with Python restore. — **VERIFIED**

### B. Python `restore()` → `restore exit`
`runtime_bootstrap.py:1942-2379` + `modal_app.py:10118-10439`

| Step order | Operation | Classification | Detail |
|---|---|---|---|
| 1 | Ledger/marker + native UNET wrapper install | MUST_BE_IN_RESTORE | `1942-1997` |
| 2 | Env/Modal identity reads | MUST_BE_IN_RESTORE | `1998-2022` |
| 3 | GPU state restore + CUDA init | MUST_BE_IN_RESTORE | `2023-2053` — `torch.cuda.init` |
| 4 | Sage identity read/verify; full discovery only on fail | MUST_BE_IN_RESTORE (full discovery REDUNDANT when sentinel matches) | `2055-2139` |
| 5 | Runtime generation decision + `reload_runtime_state()` if mismatch | MUST_BE_IN_RESTORE (skip is REDUNDANT correctly) | `2142-2207` |
| 6 | Models generation + `reload_models()` if mismatch | MUST_BE_IN_RESTORE (skip is REDUNDANT) | `2210-2263` |
| 7 | Prescan custom-node identity + sync if mismatch | MUST_BE_IN_RESTORE (skip path REDUNDANT) | `2265-2379` |
| 8 | Dependency validation, runtime config, preload, finalization | MIX: validation SNAPSHOT_STATIC or MOVE_AFTER_RESTORE, preload DEPLOYMENT_STATIC | Needs capsule |

**Retained in snapshot:**
* `CpuSnapshotModels` — CLIP, UNET, VAE object references + identities/load timings (`cpu_snapshot_models.py:78-105`); dedup accounting (`285-397`) not memory reduction. Retains wrappers/patchers, tokenizer registries, Python globals, cache dicts, prefetched conditioning, thread/executor objects if reachable.
* Diagnostic state, futures/queues if reachable.

**Quiescence required:** no active source reads, H2D, QD workers, model-loading futures, request workers, unfinished persistence, duplicated transient owners, threads surviving into snapshot. **NOT PROVEN** — `snapshot_capture_hygiene.py:136` only `gc.collect()` + optional `malloc_trim(0)`; manifest `snapshot_build_manifest.py:287` observes but does not enforce. **CONFIRMED DEFECT** — SIGABRT path credible; defensive CUDA event fallbacks exist but no end-to-end proof.

**Minimal restore active?** `COMFYMODAL_MINIMAL_RESTORE=1` in all E37 profiles — verified. Artifacts prove `restore:early 10.9 ms, eviction 8.5 ms, snapshot 4.2 ms, preamble 42 ms, bootstrap 4161 ms` — minimal but bootstrap still large. Fix sleeps vs retry loops: not found as fixed sleeps; `checkpoint_prewarm` join/handle-close timeouts are bounded waits with returned boolean (caller must enforce).

**Profile drift:** `config/v2/flag_registry.toml` unknown flags silently accepted + `inherit` + direct `os.environ` reads allow different restore behavior for same profile name if env differs. Fail-closed mismatch not enforced outside capsule.

---

## Scheduler / cache findings

### Scheduler already knows (but recomputes)

Known locally before submission: workflow, `source_hash`, topology, reachable/topology LRU (`production_workflow.py:183`), loader/sampler/output IDs, model stack, validation proof, registry fingerprint, deployment combined hash, profile identity, seeds/controls.

Still recomputed remotely: signature key generation, topology traversal, `INPUT_TYPES` introspection (`request:input-types-warm 406 ms`), registry checks, custom-node identity checks, workflow hashing, JSON ser, `deepcopy`, repeated model metadata parsing.

**Combined startup-capsule architecture (recommended):**

```
DEPLOYMENT/SNAPSHOT CAPSULE  (deploy/snapshot time, immutable, signed)
  deployment_id, deployment_combined_hash, custom_node_generation
  node/class registry fingerprint + registry_proof
  INPUT_TYPES where deployment-static (already is)
  dependency/custom-node identity
  safetensors metadata + tensor offset maps
  tokenizer/model configs
  loader signatures
  model immutable identities
  resolved static config fingerprint
  schema versions

SCHEDULER/WORKFLOW CAPSULE  (per workflow, immutable, scheduler-signed)
  source_workflow_hash, dispatch_workflow_hash, production_plan_hash
  topology summary, reachable-node set, node roles
  loader/sampler/output IDs, deterministic static signature keys
  model selection identities, plan validation proof, seeds/controls
  deployment_id + deployment_combined_hash binding

Cache key = H(deployment_capsule, scheduler_capsule, workflow_identity, request_seed_identity, resolved_config_fingerprint)
Invalidation: any component hash mismatch → fail-closed reject, no recompute-then-verify.
Workflow vs deployment vs request identity: deployment = image+source, workflow = topology+inputs, request = workflow+seeds+input-images.
Validation cheaper than recomputation: single hash compare + signature proof, not re-traversal.
```

Currently `canonical_execution.py:1387` repeats compilation for dispatch hash and `1466` extra deepcopy — risks semantic drift between two hashes of same workflow.

### Cache inventory

| Cache | What | Key | Invalidation | Persistence | Scope | Thread safety | Request impact | Hit/miss | Corruption | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Profile cache | Active-next profile | profile identity | Exact-key mismatch→drop | `canonical_execution.py:70` `.cache/v2_profile_cache.json` atomic+locked, eviction insertion-order | Process+disk | Lock | Hit skips profile compute | Miss fetches | Parse error drops | OK but flushes whole JSON on invalidation (more I/O than recompute for small entry) |
| Restore-publication | Restore plan | deployment+plan | Same | Same family | Process+disk | Lock | — | — | — | Key must include capsule |
| Plan validation memo + registry_proof_store | Validated dispatch hash | dispatch_hash + deployment_id | Mismatch→revalidate | Memory + disk | Process | Lock | `consumed=true` enables fast path but setup still runs | Fallback scan O(proofs) `1579` | Fallback correct | Must include resolved config fingerprint |
| Prompt signature memo | Node signatures | workflow+deployment+custom-node | Advisory, mismatch→recompute `227` | Disk `prompt_signature_cache.py:38` | Process+disk | Lock | Does not eliminate canonical reconstruction cost | Hit saves per-node hash | Correct fallback | Overlaps scheduler capsule — consolidate |
| Exact conditioning | Serialized conditioning CPU tensors | Full conditioning key + checksums | Exact validation `90` + checksum `134` | Bounded LRU + async persistence `2146` | Memory+Volume | LRU touched | Lookup avoids Volume I/O `64`; sync fallback rewrite `134` can reintroduce I/O on critical path | Hit skips CLIP 4.3 s | `FAILED` fallback but stale identity risk via P0-8 | Strongest cache; must be `forced_miss` in benchmark |
| Runtime-state manifest | Deployment static | Manifest hash `runtime_bootstrap:1616` | Fail-closed verify | Snapshot static | Runtime gen | — | Reread during restore | — | Correct | Should be in deployment capsule |
| Model-data/locality | CPU snapshot, loader caches | Model identity | Generation mismatch→reload | Memory+snapshot | Container | Mixed | — | — | — | Separate from scheduler cache — keep separated |

**Separation required:** deployment/static vs scheduler/workflow vs model-data vs conditioning/result vs output — currently conflated.

**Over-invalidation:** profile cache flushes whole file. **Under-invalidation:** conditioning cache stale via P0-8. **Duplicate:** conditioning controls `CLIP_CONDITIONING_CACHE` vs legacy `EXACT_CLIP_CONDITIONING_CACHE`. **More I/O than recompute:** profile cache file flush. **Silent workload change:** conditioning hit makes benchmark not cold. **Filler contamination:** cache key does not include benchmark gap/filler policy.

### Configuration / profiles

* **All `COMFYMODAL_*` inventory:** 950-line registry enumerates `COMFYMODAL_V2_*` flags but declares itself metadata not whitelist (`flag_registry.toml:1-7`). Unknown flags silently flow through. Modules still read `os.environ` directly (`env.py:49`, `runtime_bootstrap:1298`, `canonical_execution:1803`) bypassing registry. Defaults differ by module (`env_flag default` vs `flag_registry default` vs profile extends).
* **Duplicate/alias flags:** conditioning cache new vs legacy; thread policy `TBASE` vs explicit; observability `production` vs `full` vs `off`.
* **Dead/stale:** `COMFYMODAL_V2_EVICT_*`, `SNAPSHOT_EXCLUDE_UNET`, many `C6` pinned-ring/transfer flags partially preserved per `unet_fastsafetensors:27`. Profile inheritance chains (`production→e29-tracer→e37-*`) carry forward experiment-era flags.
* **Profiles fail to bake critical settings:** same deployment hash can run with different `qd/block/launch_policy` because `CLIP_QD_*` are request-carried (`consumed_at=request`) not deploy-baked — allows A/B drift and mislabeling if fallback occurs.
* **Impossible combos accepted:** invalid enum falls back to profile-derived default (`env.py:41`) not rejection — hides typos as silent config change.

**Canonical config proposal (typed):**

```toml
[loader.clip] source_reader = "qd"   # native|fastsafe|qd
[loader.clip.qd] qd = 4  block_mib = 32  launch_policy = "after_restore_sensitive_phase"
[loader.unet]  source_reader = "fastsafe"  threads=8 block_mib=256 bbuf_mib=512
[restore] mode = "minimal"  # minimal|full
[cache.conditioning] mode = "benchmark_forced_miss"  # on|off|benchmark_forced_miss
[cache.prompt_signature] enabled = true
[diagnostics.level] = "benchmark"     # off|production|benchmark|full
```

Resolve once: `defaults → named profile → deployment-baked → request overrides`. Unknown keys rejected, aliases normalized with warning, impossible combos rejected before deploy/submission. Emit `resolved_config_fingerprint = SHA256(canonical typed config)` and attach to every ExecutionPlan, capsule, cache key, ledger, artifact, and validator. — **RECOMMENDED**

---

## Measurement / gating findings

**Ledger/waterfall/Gantt:** E29 ledger is only authoritative path (`remote_python_resume→first_durable_result`), 24 spans + 28 events after fix, `ZERO_GAP True` with 48.5 ms `UNATTRIBUTED` (down from 1,673 ms at v38). Gantt is rendering layer over ledger (`gantt_telemetry.py`, `gantt_canonical.py`).

**Trust issues (all CONFIRMED):**
* `critical_path_ledger.py:308` clock-domain mix + `429 clamp` already P0.
* `720 endpoint_status="ok"` on mere presence, not ordering/completeness.
* `v2_waterfall.py:26 hard 50 ms reconciliation ceiling` but `partial_waterfall` and `data_flags` separate — consumers can pick fallback waterfall data via multiple search locations.
* `430 negative cross-process intervals discarded as unavailable` then `DERIVED` duration accepted without clock-alignment proof.
* `experiment_result_store.py:299 partial_waterfall is True only` — missing/malformed treated as complete; canonical fields copied from loosely searched result fields (`520`).
* Reconciliation mutates `waterfall_local`/`waterfall` (`benchmark_v2_direct:2781`) after validators may have read "first available" field — mutability risk.
* Zero vs absent conflated (`v2_waterfall:173` non-positive monotonic collapsed to missing).

**Proposed fail-closed acceptance invariant (all must hold, otherwise reject):**

```
successful process/container exit
AND freshness == 1/1
AND source/deployment/profile fingerprints exact (single canonical identity, P0-8)
AND canonical ledger valid (one clock axis, endpoints ordered, proven, serial coverage == endpoint interval)
AND parent/child via interval union (no naive sum, negative residual fails)
AND waterfall COMPLETE (all required fields present, no partial flag, reconciliation within 50 ms, no fallback selection)
AND timing finalization succeeded before artifact freeze (including error paths)
AND validation_status == PASS and output exact SHA
AND intended execution path proven (qd_used/fast_safe_used/clean_lane flags in artifact, not profile label)
AND fallback status == NOMINAL (no fallback event emitted)
AND artifact selection by run-ID/hash, not mtime
```

**Does `v2ctl` enforce this?** **NO** — validators, provenance, source-probe parity exist (`tools/v2_control/validation.py`, `provenance.py`, `fingerprints.py`) but implementation permits fallback waterfall selection, swallowed telemetry, clamped residuals, multiple identities, and mtime association, so a degraded run can enter nominal cohort. — **VERIFIED AGAINST CURRENT SOURCE**

**E37 clean lane implication:** clean lane profile `e37-clean-lane-qd4.toml` disables all contention sources (`INPUT_TYPES_WARM=0`, `FAST_COLD_ORCHESTRATION=0`, `CONDITIONING_CACHE_PREFETCH=0`, etc.) — correct for isolation. Result `QD source 1043 ms` proves B (concurrency poisons QD) but needs `n≥5`.

---

## Code structure / maintainability findings

* **Expensive top-level work:** `comfyapp.py:255-268` constructs recorders, reads env at import; `__init__.py:20` mutates `sys.path` and logs at import — makes import order observable and leaves stale globals across test reloads.
* **Large functions, nested control, unsafe mutable globals** — `comfyapp.py` 22k lines, `model_preload.py` 1M bytes single file with 16k-line function `model_preload.py:4142` canonical loader wrapper.
* **Sufficient typing insufficient** — `typing.Any` + `dict` everywhere; no typed config/capsule/model-identity types.
* **Magic constants:** `VOLUME_STALL_CLIP_PRELOAD_THROUGHPUT_GBPS=2.0` (`comfyapp.py:1672`), `SWAP_JOB_POLL_INTERVAL=1`, `qd 4/block 32 hard-coded in profile not typed config`.
* **Env parsing spread** across `env.py`, `runtime_shape.py`, `modal_app.py:2941 _runtime_env()`, direct `os.environ` reads — no single `ResolvedConfig`.

**Proposed module boundaries:**

```
lifecycle/snapshot.py      — snapshot capture/restore state machine, quiescence gate
loader/source_io.py        — header/offset map, preadv/fastsafe selection, QD workers
loader/gpu_publication.py  — pinned staging, H2D streams/events, owner lifetime
ownership.py               — handle/ lane/ model owners, single-flight, generation-scoped keys
scheduler/capsule.py       — deployment + scheduler capsules, canonical hashing
model/metadata.py          — safetensors metadata, offset maps, tokenizer configs, signatures
runtime/config.py          — single typed ResolvedConfig, fingerprint, validation
telemetry/ledger.py        — critical_path_ledger (single clock axis)
telemetry/waterfall.py     — reconciled waterfall, Gantt
benchmark/control.py       — v2ctl, benchmark harness (never imported by production)
```

---

## Dead / legacy code findings (expanded)

* **DEFINITELY DEAD:** none without proven lack of dynamic flag reachability — default-off ≠ dead. `tools/` scripts are not imported by production (good) but still cost indexing/maintenance.
* **LIKELY DEAD:** `comfyapp.py:12642` deprecated compat fields, `7650` experiment harnesses, `benchmark_modal.py:201` legacy direct routing if `ResultRoute=legacy` gone.
* **LEGACY BUT REACHABLE:** all above plus `e27_forensics` production import, `canonical_execution` E29 branches, `comfyapp` `1893 alias`.
* **BENCHMARK-ONLY:** most `benchmark_*.py`, `profiler_trace_v4`, `wall_clock_trace_v3`, `_e27_*` artifacts — correct to keep but must never affect deployment hash (verify `.modalignore` mechanically).
* **Cost of existence/import:** `comfyapp.py` top-level imports `optimizations` lazily guarded (`143 try`) — good, but still reads env + constructs counters even when optimizations unavailable. `__init__.py` imports 20+ modules before `NODE_CLASS_MAPPINGS` — startup cost.

---

## Test gaps

* **Source-text tests instead of behavior:** `tests/test_benchmark_harness.py:15`, `test_benchmark_modal_e2e_cli.py:187` assert substrings in source — refactor can pass/fail without behavior change.
* **Mock away real concurrency:** handle cache, speculative lane, QD workers, close fences all mocked or not exercised under real threading/CUDA.
* **No CUDA gate:** `test_c8_meta_native.py:53` skips on CPU CI; no opt-in GPU CI job for owner handoff/device transitions.
* **Missing deterministic P0/P1 tests (each needed):**

| Gap | What to test | Current status |
|---|---|---|
| Failed request isolation | Request A fails during restore/ownership/output; Request B in same process/container sees stale state | Missing |
| Subprocess lifecycle | Child non-zero exit / hang timeout / restart fail — assert reap, health, no stale handles | Missing (`comfyapp.py:18600` Popen without process group) |
| Ownership handoff race | Concurrent local/remote owners, cancel at each boundary, assert exactly one owner | Missing (P0-1) |
| Snapshot quiescence | Snapshot while prefetch/persistence/trace active — assert drained/rejected | Missing (P0-11) |
| Cache corruption | Partial JSON, wrong identity, stale schema, truncated payload → invalidate not fallback | Missing |
| Queue bounds | Flood `local_handle_proxy`/`checkpoint_prewarm` queues → bounded memory, backpressure | Missing (unbounded `480,707,482`) |
| Profile routing | Wrong/missing/legacy profile → fail-closed, no accidental default | Partial (`test_v2ctl_profiles` exists but allows unknown flags) |
| Path identity | Dirty worktree outside `deployment_spec` roots silently omitted | Missing |
| Fallback labeling | `clip_qd_fallback` emitted + final profile correctly shows degraded | Partial (E30 seam correct but E28 demand path not) |

No paid generations executed; local suites not run due to deploy lock (as required). If a test failure is due to E37 lock, not altered.

---

## Security / reliability / operational review

* **Path handling:** `__init__.py:162` good traversal defense; `local_handle_client.py:361` accepts env-provided state path without containment — if env attacker-controlled, state redirects outside data root. Centralize and contain.
* **Temp files / atomicity:** `local_handle_client.py:378` atomic via temp+`os.replace`; other `json.dump` sites in `comfyapp.py` write directly to final path — crash leaves truncated manifests. Route all persistence through one atomic writer with fsync+schema validation.
* **Subprocesses:** `comfyapp.py:18600` terminates/restarts ComfyUI via `Popen`; no process group, descendants may survive, stdout/stderr unbounded, startup failure discovered indirectly. Need supervisor abstraction.
* **Unbounded queues/caches:** `local_handle_client:480`, `checkpoint_prewarm:707`, `clip_forward_forensics:482` — grow indefinitely under stalled consumer; need `maxsize` + overflow policy (drop/backpressure).
* **Stale locks / retry storms:** `CommitCoordinator` `runtime_state.py:314` permits 1 in-flight + 1 follow-up commit — can overlap request completion/restore/snapshot unless drained.
* **Failed request leaves next in different state?** Yes — global `_LANES`, handle cache, conditioning cache, profile cache, ledger `begin_request` reset not proven on failure path — credible cross-request pollution.

---

## Historical forensics

| Era | Change | Raw evidence | Regression / reversal |
|---|---|---|---|
| Early V2 | CPU snapshot (construct on CPU, activate on demand) | `FAST_DISK_SNAPSHOT_RESTORE_REPORT:59` | Snapshot dtype divergence (FP32 CUDA UNET vs normal BF16) — later diagnosed |
| Aug 6 | Exclusive UNET ownership / post-restore rehoming `9bf15b0` | Git | Early activation retained 12.3 GB UNET → host transfer became bottleneck (H100 5.1-20.3 s) |
| E27 | Fastsafe + QD investigation | `V2_BATCH_E27...:21` QD8 49.6 GB/s (UNET), 45 GB/s (CLIP) | E28 gate held across 10 s read → `clip_gpu_wait 11.6 s` |
| E28 | Earliest speculative CLIP, fastsafe T8/64MiB/512MiB, cast-once | `V2_BATCH_E28...:27` Gantt 4.43 s CLIP, 319 ms hydrate, 5.59 s forward, 4.70 s sampler | First speculative consumer crashed `cast_once=None→AttributeError` → fallback to `native_cpu_h2d` |
| E29 | Canonical ledger (24 spans, zero-gap) | Gate `dcafbe8e / testing6` 17.534 s window, 48.5 ms UNATTRIBUTED | Report transcription copied wrong CLIP monos → false overlap claim → corrected to `UNKNOWN_PENDING_ARTIFACT` |
| E30 | Genuine QD reader, speculative-lane-only seam | Current seam `_run_speculative_read` only (`clip_qd_reader.py` doc) | Half-integration: speculative QD success → demand still fastsafe fallback on miss; `clip_qd_fallback` emitted but degraded still cohorts as nominal |
| E31 | Persistent FP32 cast-once (252 tensors / 14.5 GB per forward) | `E31:126` + E36 `398 NOOP, 0 real` | E28 rejected `+8 GB VRAM` vs `~8 ms`; E36 re-enables only with residency proof |
| E36 | QD4 selection, plan provenance proof | `E36:...:155` QD4 ARM-A 17.927 s vs FASTSAFE 24.716 s (6.8 s win) | QD4 ARM-B 808 ms slower than ARM-A from restore/H2D variance, not semantic regression |
| E37 | Clean-lane synchronous QD4 after restore (no speculative) | `E37:...:26` source 1043 ms, H2D 127 ms host / 27 ms CUDA, no fallback | Deliberately undoes speculative overlap to guarantee ordering/proof — trades possible restore overlap for determinism |

**Half-integrated optimizations (pay early + pay demand):**
1. Early VAE read but `load_models_gpu 34 ms` still at demand — E29 ledger.
2. `ExecutionPlanConsumed=true` but `cc-prefetch 403 ms + INPUT_TYPES 406 ms + schedule 445 ms` still on path.
3. Speculative CLIP QD only; demand hits fastsafe again on miss.
4. Custom ready `currently_used=True` but generic `model_management` still walks `current_loaded_models`.
5. Snapshot-cached identity but `clip_qd_take` still verifies manifest before bind.

**Worst undo:** Narrowing UNET gate fixed 11.6 s starvation but retained early activation → transfer bottleneck persisted on H100.

---

## Performance reconstruction — critical-path budget (ms, non-scheduling)

> Do NOT sum rows — many stages overlap. Best/Typical/Bad are observed end-to-end or labeled span wall, not additive. Floor must have evidence.

| Stage | BEST HEALTHY OBSERVED | CURRENT TYPICAL (E36 QD4 n=2) | CURRENT BAD (FASTSAFE / broken) | PLAUSIBLE RECOVERED FLOOR | Evidence |
|---|---|---|---|---|---|
| Pre-Python restore (platform) | 1,931 | 3,166 | 9,597 | ~1,931 | E36 ARM-B 1931, ARM-A 3166, FASTSAFE 9597; outside Python |
| Python restore (`restore:...` spans) | 4,191.9 | ~4,500 | 12,534 | ~3,200 | E29 `bootstrap 4161` + early/preamble; E28 healthy 4.49 s |
| Request setup (`plan-deserialize + cc-prefetch + input-types + schedule`) | 403+406+445 overlapped → ~1,265 serial | 1,265 | 1,472 | ~200-300 | E29 ledger; floor requires deployment capsule eliminating INPUT_TYPES/registry traversal |
| CLIP source | 1,043 (clean lane QD4) | 2,654-2,886 | 4,430 | 1,043 | E37 1043 vs E36 2654/2886 vs E28 Gantt 4430 |
| CLIP H2D/device-ready | 27 CUDA / 127 host | 122-319 exposed hydrate | 491 | 27 + host overhead ~80 | E37; E29 122; E28 319; E36 FASTSAFE 491 |
| CLIP forward | 4,309 | 4,309-5,590 | 5,590 | 4,300 | E29 4309 vs E28 5590 |
| UNET source | — (hoisted, 0.5 ms demand) | ~2,014→477 after 512 MiB bbuf | 10,200 (16 MiB bbuf) | 477 | E28 fastsafe; integrated UNET source not separately exposed in E36 QD run |
| UNET H2D/device-ready | 0.1 (gate narrowed) | 1,703-3,202 host issue | 5,100-20,300 (H100) | ~500 | E28 Gantt “0.2 ms” is post-read; host issue is real transfer/placement |
| Sampler | 3,691 | 3,691-4,727 | 5,700 (A100 early) | 3,690 | E36 3691/3715 vs E29 4727 vs AUG9 5700 |
| Sampling→VAE (transition) | — | 751-968 total window | — | ~400 | D18 751/968 includes model-mgmt 34 + decode 430 + remainder |
| VAE (`load_models_gpu 34 + decode 430`) | 346 (E28) | 381-444 | 444 | 346 | E28 346 vs E36 381-435 vs E29 464 |
| Output (`result:assembly + collection`) | 7.9-171 | ~200 | 265 | 8-100 | E29 `output_collection 7.9` bounded by durable; E28 171; E27 265 |
| **First durable (end-to-end, non-scheduling)** | **17,927** | **18,734** | **24,716** | **~17,900 (observed) → ~15,500 plausible with capsule + placement** | E36 ARM-A 17.927, ARM-B 18.734, FASTSAFE 24.716 — direct observations |

**Interpretation:** Healthy 17.9 s is the floor proven today, not a sum. Typical 18.7 s adds ~800 ms restore/H2D variance. Bad 24.7 s is restore+placement collapse. Plausible recovered ~15.5-16.0 s requires P1-1+P1-2 capsules (~2 s) plus UNET placement tuning (~0.5 s). 12.5 s requires CLIP forward (4.3 s) and sampler (3.7 s) breakthroughs — not loader scope — so do not claim 12.5 s savings from loader alone.

**Evidence discipline honored:** Every floor is an observed artifact, not `should be fast`. Overlap savings not double-counted.

---

## Recommended target architecture

> Speculative concurrency proved to be the main variance source. Prefer a small number of explicit state machines over dozens of independent booleans. Prefer resource-aware scheduling over “start everything early.”

```
LOCAL/CONTROL PLANE
  ResolvedConfig (typed, fingerprinted) ──► DeploymentCapsule ──► SchedulerCapsule
          │                                      │                      │
          │ deploy/snapshot                      │ snapshot             │ per workflow
          ▼                                      ▼                      ▼
     single canonical deployment_combined_hash + registry_proof (one identity)

REMOTE — explicit state machine per request (single-owner, generation-scoped)

  State: INIT → RESTORE → SETUP → CLIP_SOURCE → CLIP_H2D → CLIP_FORWARD → UNET_PREP → SAMPLING → VAE → OUTPUT → DURABLE → POST_DURABLE → TEARDOWN
  Transitions guarded by owner events; no string-typed owner labels.

  Resources (mutually exclusive lanes):
    LANE_STORAGE  — exactly one reader at a time (CLIP source OR UNET source), never header reparsing
    LANE_TRANSFER — scoped CUDA streams/events (CLIP H2D, UNET H2D each own stream, never global synchronize)
    LANE_COMPUTE  — GPU compute critical section (CLIP forward, sampling, VAE decode)
    LANE_CPU      — deployment-static work precooked in capsule; request CPU only unavoidable (not INPUT_TYPES/prefetch)

  Schedule (sequential by default, overlap only with measured proof):
    snapshot ──► storage(CLIP source) ──► transfer(CLIP H2D, scoped) ──► compute(CLIP forward)
                                                        │
                                UNET pure source MAY overlap CLIP compute IF scoped and proven not harmful
                                                        │
                                UNET H2D gets its own scoped dependency behind sampler gate
                                                        │
                                                    sampling ──► VAE pre-copy during sampling slack (if any) ──► decode ──► first durable
                                                        │
                                                  post-durable: persistence/diagnostics/Gantt (never on critical path)

  Ownership: one `OwnerRegistry` with typed enum {CLIP_QD, CLIP_FASTSAFE, UNET_FASTSAFE, NATIVE_FALLBACK}
             — producer/consumer agreement via handoff ID, not string.
             — single-flight futures for handles/lanes; failed owner publishes FAILED and closes buffers.

  Fallback: unified RuntimeStatus {NOMINAL | DEGRADED(reason) | FAILED(reason)}
            — reason codes: QD_ERROR, CUDA_NOT_READY, STALE_MANIFEST, SOURCE_FENCE_FAILED, PARTIAL_GPU_ROLLBACK, DEPLOYMENT_MISMATCH
            — DEGRADED never enters nominal cohort; gate rejects non-NOMINAL unless explicitly allowed.
            — benchmark artifact carries resolved_config_fingerprint + fallback status.

  Caching layers (explicitly separate):
    deployment/static metadata cache  — deployment_capsule (snapshot/static)
    scheduler/workflow cache          — scheduler_capsule (never recomputes deployment work)
    model-data/locality              — snapshot-retained models (not a result cache)
    conditioning/result (exact)      — forced_miss in benchmark, checksummed
    output                           — deduplicated, descriptor/direct sink unified
```

**What belongs where:**

| Concern | Where |
|---|---|
| Node/class registry, INPUT_TYPES, custom-node identity, safetensors metadata/offsets, tokenizer configs, loader signatures, model immutable identities | Deployment capsule (deploy/snapshot time) |
| Workflow topology, reachable nodes, loader/sampler/output roles, deterministic signature keys, seeds, plan validation proof | Scheduler capsule (scheduler time) |
| CLIP/UNET owned by | Explicit state machine + OwnerRegistry (not two owners) |
| Model loading | One loader per model: QD OR fastsafe OR native, selected by typed config, never two readers |
| Source I/O coordination | Single LANE_STORAGE queue — no concurrent manifest reads during CLIP source |
| GPU mutation coordination | One GPU lane with scoped streams/events, never `torch.cuda.synchronize()` on hot path |
| Exactness enforcement | SHA gate + per-cache checksum + typed config fingerprint; perceptual equivalence not allowed |
| Fallback | RuntimeStatus enum propagated to artifact + gate |
| Configuration | Single `ResolvedConfig` typed, fingerprinted, validated before deploy/run |
| Tracing | Single clock axis (`monotonic_ns` only), union-based parent/child, fail-closed persistence |

---

## Prioritized recovery order

> Do not stack unproven changes into one deployment — each step is a single deployment with its own gate.

| Order | Change | P0/P1 | Why first | Gate | Rollback risk |
|---|---|---|---|---|---|
| 1 | **Fix ledger clock + clamp + swallowing (P0-5/6/7)** | P0 | All ROI estimates invalid until measurement is trustworthy | Unit: synthetic overlapping children → INVALID not zero residual; run gate: `UNATTRIBUTED` still <100 ms, no status mismatch | Low — measurement only |
| 2 | **Unify deployment identity (P0-8) + introduce typed ResolvedConfig fingerprint** | P0 | Stale cache/registry silently corrupts results | Dirty worktree outside old roots → cache miss; profile drift → fail-closed mismatch not silent fallback | Medium — touch deploy/snapshot/scheduler/cache paths; keep old identities as diagnostic fallback for one cycle |
| 3 | **Add unified RuntimeStatus + fix fallback paths (P0-2/3, P1-6)** | P0 | Degraded silently cohorts as nominal today | Inject `clip_qd_fallback` + partial GPU failure → artifact `DEGRADED(clip_qd_fallback)` and gate rejects nominal cohort | Low |
| 4 | **Fix handle-cache race + fence caller discipline (P0-1/4) + bounded queues** | P0 | Leak + double read can crash or corrupt next request | Concurrency stress: duplicate handle creation → single-flight proven | Low |
| 5 | **Make Snapshot capture quiescent (P0-11) + mtime→hash artifact selection (P0-9)** | P0 | SIGABRT + wrong artifact association are catastrophic | Build manifest asserts zero live workers before snapshot; copied artifact no longer associated | Low-medium |
| 6 | **Freeze half-integrated transports behind typed `source_reader` enum** | P1 debt | 5 loaders create combinational test surface | `loader.clip.source_reader ∈ {qd,fastsafe,native}` + `loader.unet.source_reader ∈ {fastsafe,native}` — QD never runs alongside fastsafe on same file; unreachable paths removed after inventory | Medium — flag migration |
| 7 | **Introduce Deployment+Scheduler capsules eliminating request-setup recomputation (P1-2)** | P1 | 1.26 s serial setup is pure waste | `request:setup-schedule` drops to ~200 ms; `input-types-warm` disappears (capsule carries it) | High — most impactful; do after 1-6 gate is trustworthy |
| 8 | **Replace manifest fallback loop + runtime-state reloads with capsule (P1-5, P1-1)** | P1 | 0.4 s CC prefetch + restore manifest rereads | No fallback ×8 read; `_restore_timing` breakdown proven (runtime-state/gpu-state/custom-nodes each <100 ms when hit) | Medium |
| 9 | **Eliminate global synchronize on hot path + scope UNET transfer (P1-3/P1-4)** | P1 variance | Collapsed overlap is largest variance | Host H2D p50 drops and variance tightens; clean-lane 1.04 s reproduced over 5 runs, not n=1 | Medium — needs placement/bbuf tuning |
| 10 | **Mechanize `v2ctl` fail-closed gate (waterfall completeness, artifact freeze, status agreement)** | P0 | Gate today cannot reject partial/degraded | Negative residual, partial waterfall, non-NOMINAL status all reject | Low |
| 11 | **Address CPU oversubscription (TBASE → explicit, bounded pools)** | P2 | Burst contention starves CUDA issue | `12 CPU + TBASE` replaced by explicit `intraop/interop/BLAS` derived from request CPU; all pools sized within visible CPUs; `INPUT_TYPES` threads never contend with QD readers | Medium |
| 12 | **God-file split + duplicate hashing centralization** | Debt | Unlocks all future work | `canonical_json` + `content_identity` single implementation, no truncated MD5 | High effort, low immediate perf |

---

### Things I would fix even if performance did not matter

* P0-5/6/7 clock-domain + residual + telemetry swallowing — measurement integrity is non-negotiable.
* P0-8 deployment identity unification + typed ResolvedConfig — correctness of cache/registry across deploys.
* P0-1/2/3/4 ownership + handle + fence races and partial GPU rollback — reliability/liveness.
* P0-9/11 mtime artifact selection + snapshot quiescence + `SIGABRT` path.
* P0-10 output duplicate collection + hardcoded `mime_type`.
* Unbounded queues (`480,707,482`) + subprocess supervisor + atomic persistence.
* Flag registry whitelist enforcement and alias centralization — operability.
* God-file split and import-time side-effect removal — maintainability and testability.
* Broad `except Exception` classification (telemetry log-and-continue vs ownership fail-closed).
* Cycle breaking (FlagRegistry, HistoryV2Store).

### Things most likely to recover the missing seconds

* **~1.0 s from scheduler capsule (P1-2: 1.26 s setup → 0.2 s).** Highest signal: E29 `input-types-warm 406 ms + schedule 445 ms` are pure recomputation of what scheduler already knew. Not speculative — value is measured.
* **~0.5-1.0 s from deployment capsule eliminating restore rereads + CC fallback (P1-1 + P1-5).** Bootstrap 4.16 s still pays generation-marker misses and up to 8 fallback reads.
* **~0.5-1.0 s variance reduction from scoped H2D + serialized storage lane (P1-3/P1-4).** Clean lane proves QD source can be 1.04 s not 2.6 s when contention removed; UNET placement can be 0.5 s not 1.7-3.2 s with correct `bbuf` and stream scoping. This is variance recovery, not median shift.
* **NOT loader stacking:** QD4 vs FASTSAFE 6.8 s win (17.9 s vs 24.7 s) already realized. Further `QD8/64 MiB` vs `QD4/32 MiB` probe 45.0 GB/s vs 42.0 GB/s is 12 ms difference on 8 GB — pay CPU 220 ms vs 30 ms for 12 ms source gain — not candidate per `clip_qd_reader.py:20-23`. **Refuse to chase.**
* **Remaining ~2 s to 12.5 s gap must come from CLIP forward (4.3 s) and sampler (3.7-4.7 s)** — requires architectural work outside loader (Sage/CacheDiT/dtype/scheduler), not attempted here. Do not assign savings because something “should be fast.”

---

## If I inherited this repository tomorrow…

> *what would you change first, what would you delete/simplify, and what would you refuse to optimize until the architecture was cleaned up?*

**Change first (first 2 weeks, in order, each its own deployment+gate):**

1. **Freeze measurement.** Fix `critical_path_ledger` clock domain to `monotonic_ns` only, fail on negative residual, fail-closed persistence, freeze final waterfall/ledger artifact before validators read it. Without this every “optimization win” is suspect. — **Opinion, but evidence-backed: P0-5/6/7 prove falsifiability today.**
2. **Freeze identity.** Ship single canonical `deployment_combined_hash` (one file set = `.modalignore`-effective upload set, not `deployment_spec`’s separate rules) + typed `ResolvedConfig` with `resolved_config_fingerprint` on every artifact. Make caches fail-closed on mismatch instead of silently serving stale conditioning. — **Opinion, but P0-8 proves silent cache acceptance.**
3. **Freeze fallback.** Introduce `RuntimeStatus NOMINAL/DEGRADED/FAILED(reason)` and make gate reject `DEGRADED` from nominal cohort. Fix `pass` in `speculative_clip_hydration:541`, partial GPU cleanup, handle-creation single-flight. — **Opinion, but degraded-as-nominal makes benchmarks untrustworthy.**

**Delete / simplify (next month, not next quarter):**

* Delete `unet_meta_direct.py` and `unet_pinned_staging.py` as selectable production paths — keep one UNET transport (`unet_fastsafetensors`) behind typed `loader.unet.source_reader` enum. Keep staged transport only as a generic primitive, not a competing CLIP/UNET loader. — **Opinion: DEFAULT OFF ≠ DEAD costs combinational reasoning.**
* Delete second `load_models_gpu` wrapper (`comfyapp.py:16901` profiled fastpath) and consolidate behind one canonical `model_preload.py:4142` gate with explicit `proven-ready` contract; remove `cpu_snapshot_models` dtype divergence allowance.
* Delete duplicate conditioning flags/aliases — one `clip_conditioning_cache` flag, one registry entry, one code path.
* Collapse `flag_registry.toml` from 950 lines to ~80 typed knobs (P1-2 typed model) — move experiment eras (`e29-tracer`, `e30-*`, `e31-*`) to archived profiles, not live registry.
* Collapse 5-report chain (`V2_BATCH_E29..E32` + `E27/E28` full editions) into one living `ARCHITECTURE.md` + `MEASUREMENT.md` + `PROFILES.md`; reports remain as evidence, not operational docs.
* Shrink `comfyapp.py` by extracting `lifecycle/`, `loader/`, `telemetry/`, `persistence/` — or at minimum enforce `tools/*` never imported by production (`__init__.py` import graph).
* Remove mtime-based selection everywhere; introduce `RunId` association.
* Bound every unbounded queue/deque with explicit `maxsize` and drop policy.

**Refuse to optimize until cleaned up:**

* **Refuse to chase 12.5 s via further source-read parallelism (QD8, larger blocks, more workers).** QD4/32 MiB already proves source can be 1.04 s; integrated wall is restore+setup+H2D+compute, not source. More QD increases CPU 30 ms→220 ms for 12 ms source gain per E27 probe — variance-negative. — **Evidence: `clip_qd_reader:20-23`.**
* **Refuse to speculate CLIP across restore to “recover” 400 ms.** E37 clean lane deliberately serialized CLIP after restore to obtain proof; speculative overlap reintroduces P0-11 quiescence and P1-3 contention risks without gated proof it helps. Prove lane isolation first; only re-enable overlap with scoped measurement.
* **Refuse to micro-optimize `empty_cache`, `alloc_in_loop`, string formatting, or VAE cast-once for “10 ms each” before P1-1/P1-2 capsules exist.** Those are 1-2 s wins with one-time engineering; micro-opts are noise and risk regressions.
* **Refuse to adopt `min_containers>0` or warm retention as “solution” for the missing seconds.** Project targets scale-to-zero cold; warm containers hide loader/restore bugs and are not a primary optimization per scope.
* **Refuse to accept any new fallback or transport that does not emit typed `RuntimeStatus` reason codes and carry the resolved config fingerprint.** Every new path must be falsifiable from the artifact alone, or it becomes another accidental complexity.

---

## Historical claim disposition

| Claim | Source | Disposition | Why |
|---|---|---|---|
| 40+ GB/s Volume throughput (E27) | `clip_qd_reader.py:20-23` | **CONTRADICTED — SUPERSEDED** | Probe local FS/page cache, source-only, overlapped workers; integrated is 3 GB/s |
| FASTSAFE `max_threads` = queue depth | Pre-E27 assumption | **CONTRADICTED** | `nogds_file_reader` single-flight per slot, join-before-next |
| Snapshot captures quiescent state | Historical architecture claim | **CONTRADICTED** | Workers/queues not stopped, only `gc.collect` |
| Minimal restore eliminates setup | E37 intention | **HISTORICAL CLAIM ONLY — UNPROVEN as elimination** | `ExecutionPlanConsumed=true` but 3 setup spans still 1.26 s |
| QD4 differs from FASTSAFE only by QD | E37 profile comment | **VERIFIED AGAINST CURRENT SOURCE** | Profiles differ only `CLIP_QD_READER 0→1`, but implementation differs substantially — both statements true at different layers |
| CLIP source inside restore window | E29 pre-correction | **CONTRADICTED** | Mons 50 s mismatch — transcription error, corrected to UNKNOWN |
| FP32 cast-once saves multi-seconds | Early E28 hypothesis | **CONTRADICTED — SUPERSEDED** | Measured 8 ms vs 8 GB VRAM; validated OFF |
| Early VAE preload eliminates VAE management | Early optimization claim | **CONTRADICTED** | `load_models_gpu 34 ms` still at demand |
| `ZERO_GAP True` proves complete attribution | E29 | **VERIFIED AGAINST RAW ARTIFACT** as serial coverage (48.5 ms UNATTRIBUTED) — but per-span durations still **CONTRADICTED** by clock bug |
| `v2ctl` enforces fail-closed gate | Tooling claim | **CONTRADICTED** | Partial waterfall, swallowed telemetry, mtime, clamped residual allow degraded passage |

---

## Verification checklist for next gate

Every finding above includes `how to prove/falsify`. For the next deployment gate, additionally:

* [ ] Artifact contains single `deployment_combined_hash` + `resolved_config_fingerprint` + `RuntimeStatus` + `qd_used`/`fallback` flags; source probe `7/7 MATCH` and `MATCH` means same `deployment_combined_hash` as build.
* [ ] Ledger uses one clock axis (`monotonic_ns`); synthetic parent with overlapping children exceeding duration → ledger status `error` not `ok`.
* [ ] `partial_waterfall==True` → gate `REJECT` regardless of `validation=PASS` from other validator.
* [ ] Injected handle-creation race (10 threads same key) → exactly one handle, no leak.
* [ ] Injected QD partial failure → GPU memory back to baseline, status `DEGRADED`, not nominal.
* [ ] Run with dirty file outside `deployment_spec` roots → deployment hash changes, cache misses.

---

*End of E38 independent audit. All observations are from current source or raw artifacts; speculative savings explicitly not counted. Dirty worktree and E37 lock preserved.*
