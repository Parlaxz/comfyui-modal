# R42C — Independent Pre-Method and CLIP Pre-QD Critical-Path Forensics

- **Run audited:** `v2-benchmark-0-803bb5dc3fd3`
- **Worktree:** `../comfyui-modal-r42` @ branch `r42-golden-reconciliation` (HEAD `0c59f46` at audit start; all cited anchors re-read and re-verified immediately before finalization)
- **Mode:** READ-ONLY audit. No production/test/config/tooling files touched. No deploy, no Modal invocation, no git mutations. Only this report file created.
- **Method:** four independent read-only recon lanes; every material claim re-verified by the orchestrator against exact source.

Evidence labels: **CONFIRMED** / **SUPPORTED INFERENCE** / **HYPOTHESIS** / **UNKNOWN** / **UNOBSERVABLE**

---

## 1. Executive Verdict

Both catastrophic intervals share one root cause: **`GoldenRunContext.build_manifest()` (`golden_runtime_bridge.py:243-266`) performs a synchronous full-file SHA-256 over the entire model file, inline on whichever thread calls it**, and each interval is exactly the window in which that call runs for a multi-GB asset.

| Interval | Window | Owner | Strength |
|---|---|---|---|
| A (~9.235 s) | `early_sources=unet,vae` → `unet_manifest_prewarmed=1` | Full-file SHA-256 of the ~12 GB UNET (`golden_runtime_bridge.py:250-254`), invoked synchronously from `modal_app.py:18115` on the request thread | CONFIRMED present; SUPPORTED INFERENCE it owns essentially all of 9.2 s (12 GB ÷ ~1.3 GB/s ≈ 9.2 s) |
| B (~6 s) | `matched_role=clip` → `clip_qd_submit_start` | The same `build_manifest()` full-file SHA-256, for the CLIP file, invoked from `_golden_clip_load` (`golden_runtime_bridge.py:854`); secondary costs: destination `torch.empty` ≈ full payload, staging-ring alloc, first-time loader/backend construction | CONFIRMED present on path; SUPPORTED INFERENCE primary owner |

Key structural findings:

1. The UNET prewarm at request entry was introduced to move the 12 GB hash *out of* the CLIP forward window (`modal_app.py:18107-18109` comment). It relocated the cost into the pre-method window instead of eliminating it (**CONFIRMED**).
2. The identical flaw remains on the CLIP demand path itself — nothing prewarms the CLIP manifest, so `_golden_clip_load` hashes the whole CLIP file before QD submit (**CONFIRMED**).
3. The recomputed work is **deployment-static**: size/header-layout/SHA-256 facts of volume-pinned model artifacts are immutable per deployment, yet they are recomputed per fresh `GoldenRunContext` (per run key / per container process), with no persistence and no mtime/size validation of the path-keyed cache (**CONFIRMED** cache mechanics; SUPPORTED INFERENCE that volume artifacts are deployment-pinned).
4. CPU oversubscription (peak ~24.3 effective cores vs request=12) is plausible but **not established as the owner of either gap**; both gaps are fully explained by synchronous hashing. Thread pressure (~146–153 native threads) is a real secondary finding.
5. The actual QD transfer engine is healthy: CLIP submit→device-ready ≈ 1.13 s. Do not optimize QD internals for these gaps.

---

## 2. Interval A — 9.2 s Pre-Method Call Graph

Emission sites (**CONFIRMED**, re-verified): `modal_app.py:18104` (`early_sources=`), `modal_app.py:18116` (`unet_manifest_prewarmed=1`). Both sit in the request-handler body **before** `_run_plan_stream_impl` is entered at `modal_app.py:18173` — i.e., before remote method entry.

```
request handler (run_plan_stream body)
├─ modal_app.py:17990-18008   golden envelope: import bridge, ensure_current()
│                              (idempotent context reuse; scheduler+pipeline built
│                               eagerly "pure stdlib", loader deferred)
├─ modal_app.py:18015-18057   _ensure_core_wrappers() install + per-key prints
│                              (+ optional CLIP-forward sentinel verify/retry)
│                              [runs BEFORE early_sources print → outside interval A]
├─ modal_app.py:18077-18101   early publication:
│                              _walk_for_loader_names(plan_payload)  (pure Python walk)
│                              folder_paths.get_full_path(...)       (path resolution only)
│                              note_role_source("unet"/"vae")        (lock+dict+Event.set)
├─ modal_app.py:18104         ▶ PRINT "early_sources=unet,vae"    ← INTERVAL A START
├─ modal_app.py:18115         _gctx_early.build_manifest(_unet_path, ModelRole.UNET)
│    └─ golden_runtime_bridge.py:243-266
│       ├─ :244-247  cache lookup under self._lock (key = str(path)) → miss
│       ├─ :248      parse_safetensors_header(path)   [qd_engine.py:117-145:
│       │             8-byte len + header JSON read + os.path.getsize — ms]
│       ├─ :249      QDRangePlan.build(layout, block_bytes, "per_tensor")
│       │             [contracts.py — pure-Python immutable range decomposition]
│       ├─ :250-254  ★ hashlib.sha256() over ENTIRE file, sequential
│       │             open(path,"rb"), fh.read(1024*1024) chunks, no mmap,
│       │             no worker pool, no timing instrumentation
│       └─ :255-265  RoleManifest(file_sha256, identity_hash=sha[:32], ...)
│                    cached in _manifest_cache[str(path)]
├─ modal_app.py:18116         ▶ PRINT "unet_manifest_prewarmed=1" ← INTERVAL A END
├─ modal_app.py:18124-18131   optional ResourceTelemetry construct/start
├─ modal_app.py:18132-18142   _capture_remote_identity + diagnostics.set_identity
├─ modal_app.py:18143         _lazy_init_snapshot_state()
├─ modal_app.py:18144-18156   release-lock create + flag resets (trivial)
├─ modal_app.py:18163-18170   RemoteCancelWatcher construct + .start() (1 daemon thread)
└─ modal_app.py:18173         _run_plan_stream_impl(...)          ← METHOD ENTRY
```

**Synchronous vs threaded:** `build_manifest` runs inline on the request thread. No `.result()`, `.join()`, `Event.wait`, condition wait, future, or executor anywhere in interval A's hot path (**CONFIRMED**). The only synchronization is the short `_lock`-guarded dict access at bridge lines 244-247/264-266.

**Why this path exists before method entry:** the early-publication block (`modal_app.py:18070-18123`) deliberately walks the plan payload at request receipt so the phase-3 UNET worker (which starts at CLIP-forward start) finds a cached binding instead of "hashing 12 GB inside the CLIP forward window" (comment at `modal_app.py:18107-18109`). The cost was moved earlier, not removed (**CONFIRMED**).

**Waits found in interval A:** none beyond the trivial lock sections above (**CONFIRMED**). No CUDA work, no memory allocation beyond Python objects, no GC events observable in source, no tensor-map value reads — the only heavy operation is the byte-range read feeding SHA-256.

---

## 3. Wall-Owner Table — Interval A (~9.235 s)

| Component | Location | Est. ownership of 9.2 s | Classification | Evidence |
|---|---|---:|---|---|
| Plan-payload walk + `get_full_path` | `modal_app.py:18083-18101` | ~0 ms | request-specific | CONFIRMED (pure Python traversal, path resolution) |
| `note_role_source` ×2 | `golden_runtime_bridge.py:232-241` | ~0 ms | request-specific | CONFIRMED (lock + dict + Event.set) |
| `parse_safetensors_header` | `qd_engine.py:117-145` | ms-scale | snapshot-static metadata | CONFIRMED (header-sized read + getsize) |
| `QDRangePlan.build` | `contracts.py` (range decomposition) | ms–tens of ms | snapshot-static metadata | CONFIRMED (pure Python, immutable tuples) |
| **Full-file SHA-256 pass** | `golden_runtime_bridge.py:250-254` | **~9.2 s** | deployment-static facts; currently recomputed per context | SUPPORTED INFERENCE (12 GB ÷ ~1.3 GB/s ≈ 9.23 s; code comment says "hashing 12 GB") |
| `_ensure_core_wrappers()` | `modal_app.py:18015-18057`, `model_preload.py:9055-9144` | 0 s of this interval (runs before start marker) | container-restore-specific install | CONFIRMED placement |
| ResourceTelemetry / identity / diagnostics | `modal_app.py:18124-18142` | ~0 ms | request-specific | CONFIRMED trivial |
| `_lazy_init_snapshot_state()` | `modal_app.py:18143` | UNKNOWN (body not audited in depth; after end marker anyway) | container-restore/request init | UNKNOWN |
| Release-lock reset | `modal_app.py:18144-18156` | ~0 ms | request-specific | CONFIRMED trivial |
| RemoteCancelWatcher start | `modal_app.py:18163-18170` | ~0 ms (spawns 1 daemon thread) | request-specific | CONFIRMED |

Hashing mechanics detail (**CONFIRMED**): SHA-256, 1 MiB sequential buffered reads, single thread, no mmap, no worker pool, no internal timing instrumentation, one full pass over all bytes including header. Cache key is the bare path string; no mtime/size/inode validation (**CONFIRMED**, stale-manifest hazard noted in §11-R3).

## 4. Manifest-Prewarm Root Cause

- The prewarm call at `modal_app.py:18115` is a deliberate cache-fill for the later phase-3 UNET worker (`_role_binding("unet")` → `build_manifest` cache hit; consumed by `pipeline.unet_prepare` and validated again at phase-4 commit via `identity_hash` equality, `pipeline.py:290-299`) (**CONFIRMED**).
- Root cause of interval A is therefore *not* an accident but a design trade-off: hash cost was pushed from the CLIP-forward window to the pre-method window. Both placements are wrong because the hashed facts are immutable per deployment.
- Cache lifetime analysis (**CONFIRMED**): `_manifest_cache` lives on one `GoldenRunContext`; contexts are held in module-level `_CONTEXTS` keyed by run key (`ensure_current`, bridge:1074-1093). Same process + same run key + same path string → hit. New container/process or new run key → full re-hash. No disk/shared/persistent cache exists on this path.
- Correctness hazard (**CONFIRMED**): if bytes at the same path ever change, the stale cached manifest (and its `identity_hash`) would be served without validation.

## 5. Static / Snapshot / Request Ownership Split

Object inventory (**CONFIRMED** from source): `RoleManifest` (`contracts.py:341-353`, frozen dataclass), `SafetensorsLayout`/`TensorMapEntry`/`QDRangePlan`/`BlockPlan`/`CopySegment` (all frozen, pure ints/strs/tuples). `build_manifest` stores **no** open handle, mmap, tensor, buffer, lock, event, thread, or CUDA object — the `fh` handle is local to the `with` block (**CONFIRMED**).

### SAFE STATIC SNAPSHOT DATA
- role→normalized-path mapping constants; `file_sha256`; `identity_hash`; header length; `file_bytes`; `data_start`/`data_end`; full tensor map (name/dtype/shape/abs offsets); entire `QDRangePlan` incl. blocks+copy segments; block-size and destination-kind constants.
- Profile corroboration: `config/v2/profiles/r42-golden-qd4.toml:53-60` already declares static-metadata-only snapshot policy (`COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1`, `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET=1`, `COMFYMODAL_V2_CPU_MODEL_SNAPSHOT=0`) (**CONFIRMED**).
- Validity requirement: reusable only while volume bytes at those paths are immutable; must pair with bucket B.

### CHEAP RESTORE VALIDATION
1. `os.path.exists(path)` — ms.
2. `stat().st_size == layout.file_bytes` — ms.
3. mtime/inode comparison vs recorded values — ms (requires recording them; today's manifest does **not** store mtime/inode — **CONFIRMED** gap).
4. Header re-parse + tensor-map consistency check — ms to tens of ms.
5. Optional head/tail 1 MiB SHA spot-check — sub-second.
6. Full SHA only when strong integrity demanded (seconds; avoid on hot path).

### REQUEST-TIME DATA (must reconstruct; never snapshot)
- `DestinationPlan.buffers` (live CPU/CUDA tensors from `torch.empty`, bridge:283-288); pinned staging ring (`qd_engine.py:455-456`, `staging_slots(8) × block_bytes(32 MiB)` ≈ 256 MiB).
- CUDA streams/events/backends (`CudaTransferBackend`/`CpuCopyBackend`), loader instance.
- `RoleBinding.destination_factory` closure (captures live runtime behavior).
- All `threading.Lock/RLock/Event`s on `GoldenRunContext` (bridge:149-201), scheduler/pipeline wall-clock state, worker threads, executors/futures, telemetry dicts, timestamps.
- Model value bytes and live file descriptors/mmaps — excluded by policy and by safety (**CONFIRMED** no descriptors are retained in manifests today).

---

## 6. Interval B — CLIP Role-Match → QD Submit Ordered Call Graph

All steps verified against source; anchors re-checked at finalization.

```
 1. model_preload.py:4110      wrapped load_torch_file(ckpt, ...) entered
 2. model_preload.py:4130      _role_matches → "clip"
 3. model_preload.py:4134-4138 ▶ PRINT "[v2.golden_torch_file] ... matched_role=clip"
 4. model_preload.py:4151      _ctx.clip_golden_load(str(ckpt))            [inline, same thread]
 5. golden_runtime_bridge.py:828   → self._golden_clip_load(path)
 6. bridge:852                 note_role_source("clip", path)              (lock+Event.set)
 7. bridge:853-854             build_manifest(path, ModelRole.CLIP)
    ├─ qd_engine.py:117-145    parse_safetensors_header (header read + getsize)
    ├─ contracts.py            QDRangePlan.build
    └─ bridge:250-254          ★ FULL-FILE SHA-256 of the CLIP file        ← PRIMARY COST
 8. bridge:855                 _header_metadata(path)                      (2nd header access)
 9. bridge:856                 _role_binding("clip")                       (manifest cache hit;
    │                           returns binding + destination_factory closure)
10. bridge:859                 get_loader() — first-time GoldenQD4Loader(QD4EngineConfig(),
    │                           backend) construction; backend selection may construct
    │                           CudaTransferBackend (bridge:216-227)       [HYPOTHESIS cost]
11. bridge:860                 pipeline.run_role_load(ModelRole.CLIP, loader, binding)
    ├─ pipeline.py:190-195     scheduler grants (CLIP source + H2D resource), owner
    │                           creation + registration                    [fail-fast locks]
    ├─ bridge:275-295          destination factory invoked:
    │                           torch.empty(nbytes, uint8, device="cpu") PER TENSOR
    │                           — Σ ≈ full CLIP payload                    ← SECONDARY COST
    └─ pipeline.py:196-201     loader.load()
12. qd_engine.py:453-456       destination validation + plan; staging ring alloc
    │                           (_StagingRing(backend, staging_slots=8, block_bytes);
    │                           telemetry.pinned_bytes = 8×32 MiB ≈ 256 MiB)
13. qd_engine.py:458-495       locks, abort Event, Condition, block state, reader, telemetry
14. qd_engine.py:789-798       ▶ EMIT "submit_start"                       ← INTERVAL B END
15. qd_engine.py:799-805       spawn 1 dispatcher + queue_depth(4) source workers
16. qd_engine.py:814-826       main thread polls completion (sleep 0.002); joins workers
17. qd_engine.py:874           EMIT "device_ready"                          (~1.13 s after submit)
18. pipeline.py:210-216        owner.publish_device_ready(destination)
19. bridge:861-865             role_results[CLIP]; materialize_state_dict(destination, layout)
                                [zero-copy views over destination buffers — post-QD]
```

**Waits on this path (pre-submit):** none blocking found (**CONFIRMED**). `claim_gate` defaults to None so `ready_cv.wait` is unused (`qd_engine.py:536-545`); ring backpressure and dispatcher waits occur only post-submit; scheduler acquisition is lock-based fail-fast with no semaphore (`resource_scheduler.py:247-265`). No `Queue.get`, `Future.result`, or thread-pool waits pre-submit.

**Smells searched and results:**
- Repeated safetensors parsing: **CONFIRMED ×2** (step 7 header parse + step 8 `_header_metadata`; metadata-sized only).
- `load_file`/`load_torch_file` recursion / double legacy load: **NOT FOUND** on success path (fallback only on exception, `bridge:837-844`).
- State-dict materialization before submit: **NOT FOUND** (`materialize_state_dict` runs post-QD, zero-copy views).
- Model construction / model-patcher work / CLIP class instantiation in window: **NOT FOUND**.
- Zero-filled large tensors (`torch.zeros`): **NOT FOUND**; allocations are `torch.empty` (**CONFIRMED**, step 11).
- Per-tensor CPU allocation loop: **CONFIRMED** (destination factory loops tensor entries).
- Python copy loops over state dicts pre-submit: **NOT FOUND**.
- Resource semaphore waits: **NOT FOUND** (fail-fast grants).
- CUDA init/sync explicit calls pre-submit: **NOT FOUND** in inspected path; backend construction may implicitly initialize CUDA — **HYPOTHESIS/UNOBSERVABLE**.
- Wrapper chains: single wrapper layer around `load_torch_file` (reentrancy-guarded); **CONFIRMED benign**.
- Fallback probing: exception-gated only; not on success path.
- Hashes over large files pre-QD: **CONFIRMED — the full-file SHA-256 at step 7 IS the finding.**
- Full-file reads before QD: **CONFIRMED — same SHA pass reads every byte before submit_start.**
- Thread-pool starvation: **NOT FOUND** on this path (no shared pool dependency pre-submit).

## 7. Likely Owners of the ~6 s Pre-QD Gap (Ranked)

| Rank | Owner | Evidence | Notes |
|---|---|---|---|
| 1 | Full-file SHA-256 of CLIP file inside `build_manifest` (`bridge:250-254` via `bridge:854`) | **CONFIRMED present; SUPPORTED INFERENCE primary owner** | Size-dependent; e.g. ~8 GB @ ~1.3 GB/s ≈ 6 s. Runs entirely between role-match print and submit_start. |
| 2 | Destination allocation: per-tensor `torch.empty(uint8, cpu)` summing to full payload (`bridge:285-288`) | SUPPORTED INFERENCE secondary | Page-commit/allocator cost scales with payload; hundreds of MB to GBs for text encoders. |
| 3 | First-time loader/backend construction incl. possible CUDA context touch (`bridge:216-227`, `859`) | HYPOTHESIS | One-time per process; would also inflate the *first* request only. |
| 4 | Staging ring alloc/pinning ≈ 256 MiB (`qd_engine.py:455-456`) | SUPPORTED INFERENCE minor | Bounded, one-time per load. |
| 5 | Double header parse (steps 7-8) | CONFIRMED present, minor | Metadata-sized I/O; opportunistic fix only. |
| 6 | Scheduler grant acquisition | HYPOTHESIS negligible | Fail-fast locks; no blocking primitive found. |
| 7 | CPU contention from overlapping UNET worker/prewarm activity | HYPOTHESIS | Not required to explain the gap; UNET manifest was prewarmed so no second 12 GB hash should run here unless cache missed. UNKNOWN whether the bad run hit a cache miss. |

The measured post-submit transfer (~1.13 s) confirms the QD engine itself is not the problem; the gap is everything staged *before* line `qd_engine.py:790`.

---

## 8. Thread-Budget Map (current source)

Python-visible thread sites (**CONFIRMED** by source search):

| Subsystem | Count formula / worst case | Lifetime | Daemon | CPU behavior |
|---|---:|---|---|---|
| Request/main execution thread | 1 | request | No | orchestration; **runs the SHA passes inline** |
| Golden UNET bridge worker | 1 | CLIP-forward → UNET done | Yes | orchestration + QD staging |
| Golden QD dispatcher | 1 per active load | transient | Yes | mostly waiting |
| Golden QD source workers | queue_depth = 4 per load (`qd_engine.py:92,799-805`) | transient | Yes | file reads + validation |
| Golden QD `prepare_source` workers | 4 per prepare | transient | Yes | file reads / page-cache warming |
| Golden CPU H2D executor | 8 (`qd_engine.py:1028-1033`) | loader lifetime | executor-managed | CPU tensor copies |
| Golden VAE worker (+demand fallback) | 1 (guarded) | sampler step → VAE done | Yes | staging/orchestration |
| Model-restore `ThreadPoolExecutor` | `_max_workers` configured (`model_preload.py:12118-12125`) | restore/request | executor-managed | model reads/deserialization |
| Staged-safetensors producers | `config.producers` (`staged_safetensors.py:1481-1484`) | transient | executor-managed | reads/copies |
| UNET rehome memcpy pool | 8 (`unet_backing.py:983-1003`) | transient | executor-managed | **CPU-heavy memmove** |
| CLIP hydration pools | sized by `qd`/`workers` (`clip_fast_hydration.py:707,845`) | transient | executor-managed | reads/copies |
| ComfyUI model-resolution pool | ≤4 (`comfyapp.py`) | transient | executor-managed | filesystem lookups |
| Resource telemetry sampler | 1 @50 ms (`resource_telemetry.py:213-265`) | container/request | Yes | I/O polling |
| Samplers/watchers/traces (thread_cpu_sampler, full_execution_trace, RemoteCancelWatcher, output watchers) | ~3-10 when enabled | request/container | mostly Yes | waiting/I-O |
| Cache persistence/LRU workers, checkpoint-prewarm, clip_qd_reader, speculative hydration, unet_qd_probe | 1-2 per active feature | lazy/transient | mostly daemon | mixed |

Torch native pools: `torch.set_num_threads()` / `set_num_interop_threads()` applied via `runtime_shape.py:346-354`; OMP/MKL/OPENBLAS env configurable (`runtime_shape.py:135-137,188-190,254-256`) — actual native worker counts **UNOBSERVABLE from this repo's source**. CUDA driver internal threads likewise **UNOBSERVABLE**.

Reachability of ~146-153 native threads (**SUPPORTED INFERENCE**): Python/runtime subtotal ≈ 18 + M(restore lanes) + P(staging producers) + Q/W(hydration) ≈ 30-45 with typical settings; the remainder is attributable to Torch intra-op/interop native pools and CUDA driver internals. Source alone cannot prove the exact 146-153 composition — **UNKNOWN** without a runtime thread dump.

## 9. CPU Oversubscription Evidence

- Observed: cgroup peak_effective_cores ~24.3, mean ~19.0 over ~1.05 s, vs CPU request=12.
- Concurrent CPU-capable subsystems during graph execution (**CONFIRMED to exist**): synchronous SHA-256 hashing on invoking threads (request thread for prewarm; demand thread for CLIP; also `comfyapp.py:2413-2466,4031-4114,6653-6673,7291-7385`, `dependency_manifest.py:371-416,566-604` — all synchronous, **no dedicated hashing pool exists**), QD source/staging workers reading files, 8-thread H2D copy executor, rehome-memcpy pool (8), restore executor lanes, Torch intra-op kernels.
- Assessment: oversubscription is **plausible (SUPPORTED INFERENCE)** but the ~1.05 s spike window is far too short to be the owner of the 9.2 s or ~6 s intervals; those are fully explained by single-threaded SHA passes. The spike more likely corresponds to a burst where QD copies + torch ops + staging readers overlapped.
- **Do not automatically blame oversubscription for the 6 s gap** — no wait-time evidence ties scheduler/CPU contention to that window; the primary owner is confirmed synchronous hashing. Re-evaluate only after §11-R1/R2 land.

---

## 10. Missing Telemetry (Blind Spots)

Currently missing spans/events for these two intervals (**CONFIRMED absent** in inspected code):

1. Nothing inside `build_manifest`: no header-parse/range-plan/SHA sub-stamps, no bytes-hashed counter, no throughput. The 9.2 s and most of the 6 s windows are telemetry-black boxes between two prints.
2. No monotonic `restore_exit` publication paired with a `method_entry` stamp at `_run_plan_stream_impl` entry — interval A is only reconstructable from stdout prints.
3. No span for `_ensure_core_wrappers()` cost (runs before interval A start marker).
4. No destination-allocation span (bytes allocated, wall time) at `bridge:283-288`.
5. No loader/backend construction span (first-call CUDA init cost) at `bridge:216-227/859`.
6. No scheduler-grant wait measurement on the CLIP path (`pipeline.py:190-195`).
7. No pre-submit QD setup span (ring alloc, worker spawn) before `qd_engine.py:790`.
8. No storage-activity attribution during hashing (page-cache hit/miss, read syscall time).
9. No per-interval CPU-busy vs waiting attribution (the 50 ms cgroup sampler is not correlated into these spans).
10. No explicit negative markers (e.g., "no model construction occurred pre-submit") that would let a gate rule out whole classes remotely.

Minimum additional monotonic events a future gate needs (recommendation only — not implemented here):

```
manifest_build_start/end            {role, path, file_bytes}
  ├─ manifest_header_parse_ms
  ├─ manifest_range_plan_ms
  └─ manifest_sha_ms, sha_gbps      (or sha_skipped=cache_hit)
restore_exit_mono_ns / method_entry_mono_ns   (pair; delta = interval A)
wrapper_install_start/end
dest_alloc_start/end                {total_bytes, tensor_count}
loader_construct_start/end          {backend_kind, cuda_init_ms}
sched_grant_wait_ms                 {role}
qd_presubmit_setup_start/end        {ring_bytes, workers}
cgroup_cpu_sample                   {mono_ns, effective_cores}   ← correlate into spans
storage_read_bytes/read_ms          per manifest_build and qd window
negative_marker_pre_submit_clean    {role}   (asserts no construction/materialization)
```

With these, the gate can answer: what consumed restore-exit→method-entry (1); what consumed role-match→QD-submit (2); CPU busy vs waiting (3+9); storage active (8); scheduler blocking (6); model construction occurring (11-negative marker); large allocation occurring (4).

---

## 11. Exact Recommendations to R42A

**R1 — Split `build_manifest` into cheap layout vs expensive identity (highest leverage).**
In `golden_runtime_bridge.py:243-266`, separate:
- `build_layout(path, role)` → header parse + `QDRangePlan` + manifest with `file_sha256=None, identity_hash=""` (ms-scale);
- `compute_identity(path)` → the full-file SHA pass, callable later/off-thread.
Then:
- `_golden_clip_load` (`bridge:854`) calls **layout-only** before QD submit. Verified consumers: pre-submit code needs only layout/range plan; `identity_hash` equality is consumed at UNET phase-4 commit (`pipeline.py:290-299`) and in diag strings — schedule `compute_identity` on a background thread or make it lazy/on-demand for roles that require it.
- The request-entry UNET prewarm (`modal_app.py:18115`) becomes ms-cheap automatically.

**R2 — Persist manifests at deploy/snapshot time; validate at restore.**
Compute SHA once per artifact during snapshot build (extend `snapshot_build_manifest.py`), store content-addressed JSON keyed by path+size (+mtime/inode). At restore exit: stat size + mtime/inode compare + optional head/tail 1 MiB spot-hash (§5 bucket B). Never full-hash multi-GB files on any request-thread path. This converts both intervals from ~9.2 s / ~6 s to milliseconds.

**R3 — Harden the manifest cache key (correctness, independent of perf).**
`_manifest_cache[str(path)]` currently serves stale identity after byte changes (**CONFIRMED**). Key by `(path, st_size, st_mtime_ns)` or store stat facts in the manifest and revalidate on hit.

**R4 — Add the §10 minimum telemetry events** so the next gate can attribute, not infer.

**R5 — Re-measure before touching thread pools.** Only if cgroup spikes persist after R1/R2: revisit H2D executor size (8), rehome-memcpy pool (8), restore-executor lanes vs the 12-core budget; consider `torch.set_num_threads` alignment.

**R6 — Opportunistic micro-fix:** parse the safetensors header once per load and pass the layout through `build_manifest` → `_header_metadata` → QD engine (removes the ×2 parse).

## 12. What NOT to Optimize Yet

| Area | Why not |
|---|---|
| QD engine submit→device-ready internals | Healthy (~1.13 s CLIP); not an owner of either gap (**CONFIRMED**) |
| Resource scheduler design | No blocking evidence on these paths; fail-fast locks (**CONFIRMED**) |
| `materialize_state_dict` | Zero-copy views over destination buffers, post-QD (**CONFIRMED**) |
| Staging-ring sizing (8×32 MiB ≈ 256 MiB) | Bounded, one-time, minor contributor |
| Thread-count reduction / oversubscription tuning | No causal evidence yet tying it to either interval; measure after R1/R2 |
| Wrapper chain around `load_torch_file` | Single layer, reentrancy-guarded, negligible cost |
| Header double-parse beyond R6 | Metadata-sized; micro-cost |
| Fallback paths (`clip_golden_load` shim) | Exception-gated only; not on success path |

---

## Appendix — Verification Ledger

| Claim | Label | Primary anchor |
|---|---|---|
| Interval A markers bracket synchronous `build_manifest(UNET)` | CONFIRMED | `modal_app.py:18104,18115,18116` |
| Full-file SHA-256, 1 MiB chunks, single-thread, no mmap/pool/instrumentation | CONFIRMED | `golden_runtime_bridge.py:250-254` |
| Manifest cache per-context, path-keyed, no stat validation, no persistence | CONFIRMED | `bridge:179,244-247,264-266`; `_CONTEXTS` registry |
| CLIP demand path fully hashes file pre-submit | CONFIRMED | `bridge:852-854`; `model_preload.py:4151` |
| Destination = per-tensor `torch.empty` ≈ full payload | CONFIRMED | `bridge:283-288` |
| Staging ring 8 slots × block_bytes; pinned_bytes telemetry | CONFIRMED | `qd_engine.py:93,455-456,790,797` |
| submit_start→device_ready ≈ 1.13 s (healthy) | given (run data) | `qd_engine.py:790,874` |
| SHA owns ~9.2 s / primary share of ~6 s | SUPPORTED INFERENCE | throughput arithmetic + code comment "hashing 12 GB" |
| Loader/CUDA first-init contributes to interval B | HYPOTHESIS | `bridge:216-227,859` |
| Native thread composition 146-153 | UNKNOWN (source cannot count native pools) | §8 |
| CUDA driver threads | UNOBSERVABLE | §8 |

*Report generated read-only; no other files created or modified. All anchors valid as of finalization against branch `r42-golden-reconciliation`.*
