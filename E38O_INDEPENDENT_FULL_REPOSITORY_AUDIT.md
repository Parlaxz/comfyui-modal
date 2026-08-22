# E38O Independent Full Repository Audit — comfyui-modal

**Audit type:** READ-ONLY (no source/test/deploy/git mutation; dirty worktree and concurrent E37 clean-lane experiment preserved).
**Auditor:** E38O (orchestrated subagent lanes A–F + independent raw-artifact forensics + oracle synthesis).
**Date:** 2026-08-21.
**Scope:** Entire `comfyui-modal` repository, with emphasis on the production cold path, model-loading stack, measurement trust, and architecture debt.
**Evidence taxonomy used throughout:**
- `VERIFIED AGAINST CURRENT SOURCE` — traced in `comfymodal_runtime`/`comfyapp.py` at HEAD+worktree.
- `VERIFIED AGAINST RAW ARTIFACT` — traced in `.v2ctl/gates/*` and `comfymodal-data/benchmarks/runs/*`.
- `HISTORICAL CLAIM ONLY` — from prior E27–E37 reports; not re-proven here.
- `CONTRADICTED` / `SUPERSEDED` / `UNPROVEN` — as noted.
- Confidence labels: `CONFIRMED`, `HIGH-CONFIDENCE`, `SUPPORTED HYPOTHESIS`, `SPECULATIVE`, `UNKNOWN`.

---

## Executive verdict

| Dimension | Health | One-line |
|---|---|---|
| Architecture | **POOR** | Three 20k+ line god files; 8 overlapping CLIP loaders; no clean snapshot/scheduler/request separation. |
| Correctness | **AT RISK** | Owner-string mismatch, non-quiescent snapshot, config identity that does not describe the run. |
| Measurement trust | **BROKEN** | Canonical run artifact self-reports `validation_status=FAILED` while the gate reports `valid=1`. |
| Performance | **NOT RECOVERABLE AS-IS** | Best 16.7s, typical 20–70s, worst 146s; variance dominates, not a single slow stage. |
| Maintainability | **POOR** | 100+ ambient env flags, duplicated identity implementations, dead experiment modules reachable from production. |

**Is ~12.5s scale-to-zero cold non-scheduling recoverable?** *Plausible but not demonstrated.* The healthy application-side path (Python resume → first durable) is ~10.6s in the clean-lane run, which meets the target. But (a) the platform pre-Python segment (~12–16s) is outside application control under `min_containers=0`, and (b) the application path is wildly unstable (16.7s → 146s), so the target is not *reliably* met. Recovering the missing seconds requires fixing measurement validity and loader determinism first; tuning QD block sizes will not.

**Five most important discoveries:**
1. The benchmark gate (`valid=1`) and the run artifact's own timing reconciliation (`validation_status=FAILED`, residual −7741 ms, a negative-duration stage) **disagree**, and the gate does not consume the run artifact's validation status. (P0)
2. The deployment fingerprint records `FAST_COLD_ORCHESTRATION=1`/`UNET_FASTSAFETENSORS=1` while the runtime `effective_env` shows `0`/`0` — **deployment identity does not describe the run**, and the gate passes anyway. (P0)
3. UNET loading still runs through generic Comfy `load_models_gpu` on the critical path between CLIP forward and sampling (841 ms healthy, **18.5 s** in a bad run) — a half-integrated optimization. (P1)
4. CLIP forward variance (1.1 s → 4.5 s) and UNET load variance (0.8 s → 18.5 s) are the entire tail; QD source read is stable (~1.15 s). The E37 clean-lane hypothesis (startup concurrency poisons QD) is **partially supported but not sufficient** — bad runs occur even inside clean lane. (P1/P2)
5. Snapshot capture is **not quiescent** (only `gc.collect()` + `malloc_trim()`), yet the manifest inventories live threads/executors. (P0/P2)

---

## 1. Architecture map (what the system actually does)

### 1.1 Production execution path (verified against source)

| # | Stage | Owner (file:line) | Context |
|---|---|---|---|
| 1 | Local request build | `tools/v2_control/backend.py`, `run_v2_single.bat` | local CLI |
| 2 | Profile/deploy resolution | `tools/v2_control/config.py:187-418` | local control plane |
| 3 | Deployment identity + preflight | `deploy_and_run_v2_single.bat:554-1076`, `tools/v2_control/fingerprints.py` | local subprocess |
| 4 | Handle acquire | `modal_transport.py:884`, `local_handle_owner.py`, `local_handle_client.py` | local |
| 5 | Modal submission | `modal_app.py:17762` `run_plan_stream` | local→remote |
| 6 | Container restore | `modal_app.py:10118`, `runtime_bootstrap.py:1942` | Modal restore phase |
| 7 | Request setup | `modal_app.py:17931-19632` | request coroutine |
| 8 | Plan validation / seed consume | `runtime_executor.py:101-199`, `modal_app.py:17527-17683` | request |
| 9 | Cache/conditioning decision | `clip_conditioning_cache.py`, `runtime_executor.py:50-86` | request |
| 10 | Model-load dispatch | `model_preload.py`, `fast_cold_orchestration.py` | request + preload futures |
| 11 | CLIP load + encode | `runtime_executor.py:2656-2885`, `model_preload.py` | request |
| 12 | UNET load | `model_preload.py:14031-14161`, `unet_*` | request (inside graph exec) |
| 13 | Sampling | `runtime_executor.py:4337-4668` | serialized sampler lane |
| 14 | VAE decode | `model_preload.py:14477+`, Comfy path | request |
| 15 | Output delivery | `output_delivery.py:1094+`, `modal_transport.py` | request/stream |
| 16 | First durable | `critical_path_ledger.py`, `v2_waterfall.py` | request |
| 17 | Post-durable / teardown | `modal_app.py:17685-17739` | request finalize |

### 1.2 Subsystem ownership

| Concern | Owner |
|---|---|
| Deployment identity | `tools/v2_control/fingerprints.py`, `deploy_and_run_v2_single.bat` |
| Profile resolution | `tools/v2_control/config.py`, `profiles.py` |
| Plan validation | `contracts.py`, `runtime_executor.py` |
| Model-load dispatch | `model_preload.py`, `fast_cold_orchestration.py` |
| Conditioning cache | `clip_conditioning_cache.py` |
| Output delivery | `output_delivery.py`, `modal_transport.py` |
| Measurement spine | `critical_path_ledger.py`, `v2_waterfall.py`, `gantt_canonical.py` |

### 1.3 State persistence boundaries

- **Across snapshot/container:** imported modules, deployed env, snapshot-retained model wrappers (`cpu_snapshot_models.py:78-105`), registries, caches, pinned buffers reachable from globals.
- **Across requests (warm):** module globals, `HandleCache`, retained model objects, executors, conditioning/signature caches.
- **Must NOT persist:** request outputs, request tensors, sampler state, live CUDA events, prefetch workers, request caches.
- **Cleared per request:** trace context, critical-path recorder, cleanup guards, terminal-release flags.

### 1.4 Current concurrency / resource schedule

- **Serialized:** profile resolution, deploy verify, submission, plan validation, seed decision, request setup.
- **Potentially concurrent:** CLIP preload/speculative futures vs UNET staging (profile-dependent).
- **Serialized sampler:** sampling begins only after retained-UNET identity check; a sampler mutation lane is acquired at `sampling_start`.
- **Observed thread count:** **51 native threads** at request entry on a 12-CPU container (`summary.json` of `v2_2026-08-21_22-35-45`: `torch_intraop_threads=12`, `torch_interop_threads=14`, `OMP/MKL/OPENBLAS_NUM_THREADS=12` each, plus QD workers, preload/persistence/telemetry threads). This is the single largest CPU-oversubscription risk.

### 1.5 God files (VERIFIED)

| File | Lines | Distinct responsibilities |
|---|---:|---|
| `modal_app.py` | 20,475 | Modal app, env, snapshot/restore, request lifecycle, streaming, cleanup, observability |
| `model_preload.py` | 21,900 | model path resolution, CPU/GPU snapshot models, staged/pinned loaders, CLIP/UNET/VAE dispatch, teardown |
| `comfyapp.py` | 24,450 | ComfyUI integration/patches, execution wrappers, runtime state, history/result, critical-path recording |
| `runtime_executor.py` | 5,161 | plan execution, cache orchestration, CLIP/UNET/VAE instrumentation, sampling wrapper |

---

## 2. Model-loading stack (reconstructed precisely)

### 2.1 Terminology (VERIFIED AGAINST CURRENT SOURCE)

- **fastsafetensors** = external optional package (`fastsafetensors==0.3.3`, `e16_source_io_modal.py:36`), imported dynamically (`clip_fast_hydration.py:585-615`; `unet_fastsafetensors.py:179-188`). Performs file→GPU direct load via `SafeTensorsFileLoader`.
- **FASTSAFE** = a *profile label* only (`e37-clip-fastsafe.toml`), not a different library. It means "use the fastsafetensors branch, QD reader OFF."
- **QD** = the custom **queue-depth source reader** (`clip_qd_reader.py`), not fastsafetensors. It replaces source-read + H2D + publication for CLIP with `qd` workers (default 4), 32 MiB blocks, two pinned slots per worker, CUDA completion events, and a `QdGpuOwner` retaining one contiguous GPU buffer (`clip_qd_reader.py:1195-1575, 1846-1934`).
- **QD4** = `COMFYMODAL_V2_CLIP_QD_QD=4` (four readers).
- **speculative hydration** = a background CLIP read lane that may be re-consumed or re-read by the demand path (`speculative_clip_hydration.py:441-563`).
- **native loader** = Comfy's `safetensors.load_file` / `VAELoader`.
- **staged transport** = `staged_safetensors.py` plan/prepare/commit with owner extraction.
- **CPU snapshot model** = `cpu_snapshot_models.py` retains model wrappers/identities in the snapshot.
- **preload** = restore-time model reads (`comfyapp.py:11215-11989`).
- **demand loading** = graph-execution-time `load_models_gpu` (generic Comfy path).

### 2.2 Answers to the required questions

1. **Can fastsafetensors and QD work together?** Per load, **no** — dispatch is `if CLIP_QD_READER: clip_qd_load() else _fastsafe_load()` (`speculative_clip_hydration.py:696-751`). QD replaces the fastsafetensors read/H2D implementation for that file. QD failure falls back to fastsafetensors in the *general* path (`speculative_clip_hydration.py:720-742`), but in **clean lane** the fallback is prohibited and raises instead (`speculative_clip_hydration.py:736-741`). *(Oracle correction: the "always falls back" claim is too broad; clean lane is fail-closed.)*
2. **Which layer does QD replace/modify?** Source read (parallel `pread`), H2D (bounded pinned staging + async copies), and publication (zero-copy tensor views over the GPU buffer). It does **not** modify Comfy model management.
3. **Exact differences between FASTSAFE and QD4 profiles?** `e37-clip-fastsafe.toml` vs `e37-clip-qd4.toml` differ **only** in `CLIP_QD_READER` (0 vs 1); scheduling/resource/launch-policy settings are held constant. The QD4 profile therefore changes reader + H2D + owner + telemetry, nothing else.
4. **Does an A/B change anything besides queue-depth/reader behavior?** In the profile definitions, **no** — only the reader branch. (But the *runtime* env can drift; see §12.)
5. **Duplicate implementations solving the same problem?** **Yes** — at least 8 distinct CLIP loading paths (native CPU, native CUDA safetensors, external fastsafetensors, custom QD, pinned staging, staged transport, meta-assign, speculative) and a 4-deep UNET chain (pinned-ring → meta-direct → fastsafetensors/staged → native). Several are reachable in production today.
6. **Old experimental paths still reachable?** **Yes** — `unet_qd_probe.py` and `unet_salvage_probe.py` are imported by `unet_fastsafetensors.py:78-83`; `unet_pinned_staging.py`, `unet_meta_direct.py`, `staged_safetensors.py` are all live dispatch branches.
7. **Which path is production-worthy?** **HIGH-CONFIDENCE:** native Comfy CPU load (exact, simplest) and external fastsafetensors (integrated for CLIP+UNET, ownership contract). QD4 is structurally capable for CLIP but newer and more complex; staged/pinned/meta-direct are more experimental.

### 2.3 Fallbacks (VERIFIED)

- CLIP generic hydration failure → `hydrate_cpu_standard()` (re-reads/re-allocates; not zero-copy) (`clip_fast_hydration.py:777-792`).
- QD failure → `clip_qd_fallback` + fastsafetensors (re-reads bytes) in general path; **raises** in clean lane.
- Speculative failure → demand path re-runs authoritative hydration (double-read possible).
- UNET chain: each `None`/failure falls to next branch; fastsafetensors avoids native re-read on success, but on failure native load is fresh (duplicate work possible) (`model_preload.py:14085-14160`).
- VAE: **native `VAELoader` only** — no fast/QD branch (`model_preload.py:14265-14273`).

### 2.4 Owner strings (VERIFIED — P0-class mismatch)

- Producer registers restore-time CLIP reads as `owner="restore_clip_loader"` (`comfyapp.py:11857-11876`).
- Request preflight only treats a read as active when `inflight.get("owner") == "restore_preload"` (`comfyapp.py:12323`).
- The coordinator `acquire()` inside the same function uses `owner="restore_preload"` (`comfyapp.py:11934,11945`).
- **Result:** a restore-time CLIP read owned `restore_clip_loader` is invisible to the request preflight → latent duplicate-read/race. Latent today because clean lane disables restore preload (`restore:preload` span = 0.9 ms).

---

## 3. CPU audit

### 3.1 Thread inventory (VERIFIED)

| Source | Classification | Risk |
|---|---|---|
| Torch intra/inter-op (`runtime_shape.py:346-355`) | deployment-static | 12 + 14 on 12 CPUs |
| OMP/MKL/OpenBLAS (`runtime_shape.py:135-191`) | deployment-static | each "12" if set |
| CLIP QD workers (`clip_qd_reader.py:1248-1686`) | request-dynamic | 4 workers × 2 slots |
| CLIP hydration executors (`clip_fast_hydration.py:707,845`) | request-dynamic | |
| Staged-safetensors executor (`staged_safetensors.py:1481`) | request-dynamic | |
| Persistent preload pool (`model_preload.py:11833`) | request-static | |
| Checkpoint prewarm (`checkpoint_prewarm.py:393,727`) | deployment/request | |
| Conditioning cache workers (`clip_conditioning_cache.py:1993,2236`) | deployment-static | |
| Telemetry/trace/sampler threads (`runtime_executor.py`, `thread_cpu_sampler.py`) | deployment-static | always-on |
| App/background threads (`modal_app.py:4424,4796,10540,18366,18747`) | deployment/request | |
| Comfy registry/`INPUT_TYPES`/hashing (`comfyapp.py:1746-4880`) | snapshot/workflow-static | expensive on cold |

**Oversubscription:** 12 intraop + 14 interop + OMP/MKL/OpenBLAS (12 each) + QD + preload + persistence + telemetry ≈ **51 native threads** on a 12-CPU container. Burst windows: CLIP QD + restore/setup/preload; UNET worker A/B overlap.

### 3.2 Per-request CPU work (classification)

- **Snapshot/workflow-static but recomputed:** workflow/options/context hashing (`comfyapp.py:2660-2738,7126-7176`), SHA/MD5 source + dependency hashing (`comfyapp.py:2286-4159`), `stat`/existence/custom-node fingerprint scans (`comfyapp.py:3680-4880`).
- **Accidental/redundant:** repeated validation when identity/cache certificates are valid; `print(..., flush=True)` waterfall logging (`comfyapp.py:2198-2204`).
- **Unavoidable:** tensor decode/encode, safetensors parse, sampling.

---

## 4. GPU / CUDA audit

### 4.1 CLIP QD (VERIFIED)

- GPU allocation `clip_qd_reader.py:1632`; **two pinned slots per worker** (`:1636-1656`); each slot has CUDA completion/event; worker threads joined at `:1682-1686`; publication only after worker completion + validation.
- **Slot reuse is gated on prior H2D CUDA event completion** (`:1472-1533`). This is *correct* but couples source-read progress to DMA completion — source reads are not fully decoupled read-ahead.
- "H2D host issue" (127.4 ms in E37 run) measures host-side enqueue; "H2D CUDA event" (27.3 ms) measures GPU stream elapsed. **Not comparable as CPU wall.**

### 4.2 UNET (VERIFIED)

- `unet_pinned_staging.py:144-184` is **not a pipelined ring**: one pinned host buffer; pageable→pinned copy synchronous; pinned→device nonblocking but `stream.synchronize()` after **every chunk** (`:166-172`); final `torch.cuda.synchronize()` (`:180-184`) → globally blocking before publication.
- `unet_fastsafetensors.py` overlaps metadata worker A with file/H2D worker B, but `empty_cache()` at `:560` is a major allocator disruption when reached.

### 4.3 CLIP forward / FP32 (VERIFIED)

- `clip_fp32_cast_once.py` + Comfy patch perform dtype/device conversion + one-time FP32 cast. E31 report: Qwen CLIP runs FP32 compute on BF16-resident weights → **252 real BF16→FP32 conversions (14.53 GB/forward)**; cast-once ON makes them disappear. **REMOTE end-to-end win UNPROVEN** at report time; later E36 declared the cast-once ON arm authoritative. Clean lane *disables* cast-once (`COMFYMODAL_V2_CLIP_FP32_CAST_ONCE=0`).
- No broad explicit `torch.cuda.synchronize()` in the CLIP forward patch; synchronization induced by allocator queries, model-management waits, CUDA event waits.

### 4.4 VAE transition (VERIFIED)

- `VAE_ACTIVATION_MODE=late`, soft-empty-cache gate in `modal_app.py`/`runtime_executor.py`; `empty_cache()` present in fastsafetensors path; model-management calls force device transitions. Historical ~70 ms physical copy vs current ~0.8 s transition is explained by generic model-management `load_models_gpu` wrapping (see §16).

---

## 5. Modal Volume / storage / locality audit

### 5.1 Reads during a cold request (VERIFIED)

- **Deployment-static (should be cacheable):** models generation record (`comfyapp.py:1746-1804`), custom-node generation record (`:1810-1890`), dependency/cache manifests (`:2241-4497`), custom-node identity/requirements hashes (`:3680-4204`), runtime identity/cache metadata (`:2741-3181`).
- **Safetensors reads:** CLIP QD parses header once (`clip_qd_reader.py:1212-1217`), `os.stat` (`:1229-1237,1605-1613`), plans blocks across `qd` workers; optional verification re-reads ranges (`:1287-1294`). UNET fastsafetensors overlaps metadata worker A + file/H2D worker B.
- **During CLIP QD:** header parse, tensor-map planning, stat, FD opens, source reads, pinned alloc, H2D events.
- **During CLIP forward:** model-management/device reads + conditioning persistence.
- **During UNET loading:** discovery/stat, metadata/header parse, fastsafetensors source reads, H2D, generic `load_models_gpu` gate.

### 5.2 Redundancy risk

Repeated generation/manifest/stat/hash validation when deployment-static identities are already known is **accidental-redundant** and a primary storage-contention source during the cold window.

### 5.3 Modal platform facts (Lane F, current docs)

- Volume documented throughput ceiling **2.5 GB/s** (not guaranteed; network-dependent) — `modal.com/docs/guide/volumes.md`. Historical "40+ GB/s" probes measured a *different* cache/FUSE layer, not the integrated Volume path. **Do not treat 2.5 GB/s as a physical ceiling for all layers.**
- `volume.reload()` makes latest committed state visible; fails if files open; container Volume appears empty during reload.
- CPU snapshots capture process tree, memory mappings, FD tables, env, PIDs; GPU snapshots (Alpha) additionally capture VRAM/streams/contexts.
- `cpu` requests **physical cores**; soft limit is request + 16; `scaledown_window` default 60 s (configurable 2 s–20 min). `min_containers=0` ⇒ true scale-to-zero.

---

## 6. Snapshot / restore audit

### 6.1 Retained in snapshot (VERIFIED)

- `CpuSnapshotModels` retains CLIP/UNET/VAE wrappers + identities + storage registries (`cpu_snapshot_models.py:78-105`).
- Module globals, registries, caches, telemetry dicts, runtime-state globals are ordinary process state → snapshot candidates.
- Pinned buffers/CUDA objects: not explicitly modeled; reachable globals/owners may serialize indirectly. **Manifest inventories threads/executors but does not stop/drain them** (`snapshot_build_manifest.py:318-342`).

### 6.2 Quiescence — **NOT demonstrably quiescent** (P0/P2)

Capture hygiene performs only `gc.collect()` + guarded `malloc_trim(0)` (`snapshot_capture_hygiene.py:136-204`). No universal "stop workers, join futures, drain queues, synchronize CUDA, then capture" protocol found. Live QD/preload/restore/telemetry threads can overlap capture.

### 6.3 Minimal restore (VERIFIED)

- `COMFYMODAL_MINIMAL_RESTORE` default `"1"` (`modal_app.py:3051-3055`); active in `e37-clean-lane-qd4` per effective_env. Intended to skip optional warmups/diagnostics. Exact skip set is distributed across `comfyapp.py.restore` + env gates, not one isolated function.
- Restore now small: ledger total ≈ **660 ms** (eviction 344 + bootstrap 251 + preamble 44 + rest ~20) in clean-lane run. Bootstrap varies 180–1403 ms across runs.

### 6.4 Retry / fixed sleeps

- Restore-boundary sleep is env/profile-controlled (`modal_app.py:7700-7717`), not fixed in source. Most waits are `Event.wait`/future joins, not fixed sleeps.

### 6.5 Restore classification

| Class | Examples |
|---|---|
| MUST_BE_IN_RESTORE | Modal boundary, retained-model release, required runtime-state load |
| SNAPSHOT_STATIC | imported modules, model wrappers, registries, caches |
| DEPLOYMENT_STATIC | image/class/GPU/cloud/region, propagated env |
| MOVE_AFTER_RESTORE | optional GPU hydration, request binding, preload completion |
| REDUNDANT | rebuilding info already in `CpuSnapshotModels`; repeated model/file reads |
| DIAGNOSTIC_ONLY | manifests, hygiene, RSS floors |
| LEGACY | non-minimal restore branches gated by env |

### 6.6 Drift risks

`MINIMAL_RESTORE`, `E37_CLEAN_LANE`/`CLEAN_LANE`, `ENV_PROFILE`, CPU/GPU snapshot gates, preload/restore-background gates, VAE/CLIP policy, single-use/release-GPU flags. A local profile can report clean-lane/minimal while the container silently uses defaults.

---

## 7. Scheduler / ExecutionPlan / combined-cache audit

### 7.1 What the scheduler knows (VERIFIED)

`canonical_execution.py:1414-1778` deep-copies/normalizes workflow → deterministic node IDs, edges, reachable nodes, execution order, static signatures, loader/sampler signatures, plan hash. `execution_seed.py:375-454` does similar for bootstrap. **It does NOT prove** the remote container's loaded registry, custom-node source identity, or `INPUT_TYPES()` results.

### 7.2 What remote recomputes (VERIFIED)

Workflow/signature normalization + hash; topology traversal/order; `INPUT_TYPES()` introspection (`execution_warm.py`); registry checks; custom-node/source identity checks; workflow JSON serialization; deepcopy (`canonical_execution.py:1414,1466`); model metadata parsing. `BATCH_C_EXPECT_PLAN_FAST_PATH` removes *some* work only when a valid plan proof is consumed; startup-minimal seed payloads (`execution_seed.py:562-582`) omit topology and cannot prove graph equivalence alone.

### 7.3 Combined startup-capsule design (recommended)

- **DEPLOYMENT/SNAPSHOT CAPSULE:** node/class registry, class fingerprint, `INPUT_TYPES` where deployment-static, custom-node identity, safetensors metadata, tensor offset maps, tokenizer/model configs, loader signatures, model immutable identities, static proof data.
- **SCHEDULER/WORKFLOW CAPSULE:** accepted `ExecutionPlan`, workflow identity, topology, reachable set, node roles, loader/sampler/output IDs, deterministic static signature keys, selected model identities, plan-validation proof.
- Canonical cache key = deployment fingerprint × workflow identity × runtime-shape fingerprint. Fail-closed on any mismatch. Keep conditioning/result caches logically separate from immutable startup caches.

---

## 8. Cache audit

| Cache | Key | Scope | Contamination risk |
|---|---|---|---|
| `clip_conditioning_cache.py` | model/CLIP id + prompt/input id | process/container | **HIGH** — warm/filler requests populate it |
| `prompt_signature_cache.py` | normalized prompt/signature | process-local | Medium-high |
| `pre_graph_cache.py` | graph/topology | process/container | **HIGH** if key omits workload-affecting field |
| `registry_proof_store.py` | registry/custom-node proof | runtime/disk | Medium |
| `experiment_result_store.py` | prior results | artifact storage | **HIGH** if selection lacks exact run/config fingerprint |
| `canonical_execution.py` disk cache | profile/restore | disk + mirror | **HIGH** cross-process |
| `HandleCache` (`modal_transport.py`) | deploy/app/profile | process-local | Medium |
| Model manifests | model identity | Volume/runtime | Medium-high |
| `.runtime_state`/`snapshot_seed` | restore state | disk/Volume | **HIGH** — stale state converts cold→warm |
| Volume model/CPU/GPU snapshots | weights | Volume/container | **VERY HIGH** — changes cold/warm workload |

General behavior is fail-open-to-miss. Principal risk is **scope/identity completeness**, not corruption safety. Any cache keyed only by workflow/prompt (not deployment/source/profile/model identity) can silently change the measured workload.

---

## 9. Concurrency / ownership / race audit

### 9.1 Inventory (VERIFIED)

- `CommitCoordinator` (`runtime_state.py:337-547`): lock, one in-flight commit, follow-up commit — comparatively well serialized.
- `comfyapp.py` PNG/restore/telemetry locks (`:197-206`); production UNET gate lock + per-load `Event` (`:1486-1649`).
- Checkpoint prewarm stop/finished events + worker threads (`checkpoint_prewarm.py:339-756`).
- Multiple `ThreadPoolExecutor` in hydration/read paths.
- Global owner lists on patchers (`clip_fast_hydration.py:1682-1822`).

### 9.2 Race/deadlock findings

- **Snapshot-time race (HIGH):** capture does not stop threads/executors; model mutation/file reads/CUDA work can overlap capture.
- **Source-reader lifetime (HIGH):** async reader ownership can survive into forward start unless explicitly retired.
- **Partial publication (HIGH):** global owner/future/event registries; publication can precede full readiness.
- **Stale global state (HIGH):** singletons, caches, gates, owner lists survive requests/restores.
- **Producer/consumer key mismatch (MEDIUM/HIGH):** `restore_clip_loader` vs `restore_preload` (§2.4).
- **Future attribution (MEDIUM):** generic `.result()`/event waits can block without producer/phase identity.
- **Shutdown race (HIGH):** daemon/background threads/executors may outlive request/restore; no global shutdown barrier found.
- **Double reads (MEDIUM/HIGH):** restore/preload/manifest/storage-registry/eviction paths independently inspect/read model data; fallbacks can repeat reads.

---

## 10. Fallback audit

### 10.1 Census (VERIFIED, truncated search)

Top concentrations: `clip_conditioning_cache.py`, `comfyapp.py` (optional-import/telemetry/compat suppression; no-op stubs at `:136-142`), `clip_fp32_cast_once.py`, `clip_fast_hydration_wiring.py` (repeated `pass`), `cpu_snapshot_models.py` (per-tensor inspection suppressed `:163-181,348-374`), `snapshot_*` (expected nonfatal procfs/libc fallbacks).

### 10.2 Performance-sensitive fallbacks

- CLIP hydration failure → native CPU materialization (re-reads large files, reallocates, invalidates fast-profile claim).
- Preload/restore fallback → `asyncio.to_thread` sync; failed preload moves work onto critical path.
- VAE/UNET gate timeout → logs diagnostic, proceeds; latency attribution misleading.
- Commit fallback → async Volume API → sync thread; cleanup/fsync failures suppressed (weakens durability telemetry).
- No-op compat stubs → profile label appears active while measurements absent.

### 10.3 Unified runtime status model (recommended)

`NOMINAL` / `DEGRADED` / `FAILED` with exact reason codes. A benchmark that executes a degraded fallback **must never** enter the nominal cohort. Gate must record `fallback_status=nominal` as a hard requirement.

---

## 11. Measurement / telemetry / accounting audit (P0)

### 11.1 Canonical run artifact self-contradicts the gate (VERIFIED AGAINST RAW ARTIFACT)

Run `v2_2026-08-21_22-35-45` (`e37-clean-lane-qd4`):
- `final_reconciled_waterfall.validation_status = "FAILED"`, `reconciliation_status = "EXCEEDS_TOLERANCE"`.
- `residual_ms = -7741.042` (`residual_pct = -271.4%`) — negative residual **masked** (comfyapp.py clamps `max(0.0, …)`).
- Stage `pre_python_snapshot_restore` has **negative duration** (`start_ns > end_ns`, `status="invalid"`); warning "Modal pre-Python snapshot restoration: negative duration".
- `total_wall_ms = 7212.9` **<** `accounted_ms = 10593.2`.
- Stage percentages up to **166%** (computed against wrong denominator).
- `sampler_graph_join_wait` and `remote_return_handoff` `status="unavailable"` yet `included_in_total=true` with null durations.
- Yet `.v2ctl/gates/gate_20260821-223621_f76e3da7.json` reports `gate_valid=true`, `provenance_validation_status="validated"`. **The gate does not consume the run artifact's own `validation_status`.** (Oracle: this is intentional gate design — SHA/plan/conditioning/ledger/clean-lane proof — but it means `valid=1` is an algorithm/provenance proof, NOT a latency acceptance. The coexistence with `FAILED` timing is still a measurement-trust defect.)

### 11.2 Field disagreements across artifacts (VERIFIED)

- `sampler_ms = 3651` (summary) vs `sampling = 4748` (ledger) vs `sampling = 4748` (waterfall).
- `pre_sampler_ms = 4646` (summary) vs `pre_sampler_execution = 2357` (waterfall-derived).
- `scheduling_ms = 0` (summary) vs `18702` (waterfall `modal_scheduling`).
- `backend_startup_ms` inside `restore_breakdown` = **18963.620** in `c4_armA_deploy2.log` AND `c4_armA_retry8.log` (different runs!), **22133.180** in retry4/5/6 — millisecond-identical across runs ⇒ **stale/cached field**, non-additive with `restore_total_ms` (300–2400 ms). Producer: `runtime_bootstrap.py:1378-1386` `variance_stage("backend_startup")` wrapping `start_backend()`.
- Local `reconciliation_status = "incomplete"` (missing `local_receive_to_enqueue`) even in the canonical run.

### 11.3 Executor budget does not sum (VERIFIED, Oracle)

Listed executor leaves sum to **8.456 s** while `executor-run` = **9.746 s** (≈1.29 s unaccounted even in the healthy case). Wall decomposition `4.25+0.11+18.7+0.678+0.126+9.746+0.093 ≈ 33.7 s` ≠ reported 21.56 s. **Treat the current waterfall as a measurement defect, not a performance model.**

### 11.4 Fail-closed acceptance invariant (recommended)

`successful process/container exit` AND `freshness satisfied` AND `source/deployment/profile fingerprints exact` AND `canonical ledger valid` AND `waterfall complete/reconciled (validation_status==COMPLETE, residual within tolerance)` AND `validation_status success` AND `output exact` AND `intended path proven` AND `fallback_status==nominal`. Current `v2ctl` enforces only a subset.

---

## 12. Configuration / flags / profiles audit (P0)

### 12.1 Identity drift (VERIFIED AGAINST RAW ARTIFACT)

Gate `gate_20260821-223621_f76e3da7.json` `deploy_inputs.deploy_flags`:
- `COMFYMODAL_V2_FAST_COLD_ORCHESTRATION = "1"`
- `COMFYMODAL_V2_UNET_FASTSAFETENSORS = "1"`

But profile `e37-clean-lane-qd4.toml` sets both `"0"`, and run artifact `effective_env` shows both `"0"`. Mechanism: `tools/v2_control/fingerprints.py:37-44` `_POST_SELECTOR_EFFECTIVE_FLAGS` forces these ON when `V2_E19_FINAL_COLD_LOADER=1` (which the profile inherits from `e29-tracer`); the BAT hard-aborts if E19 selected but FCO=0 (`deploy_and_run_v2_single.bat:531-532`), yet `ENV_PROFILE=inherit` lets the runtime see the profile's `0`. **Three layers disagree; the gate passes anyway.** Deployment identity therefore does not faithfully describe runtime behavior.

### 12.2 Flag sprawl (VERIFIED)

- Typed `ResolvedConfig` exists in `tools/v2_control/config.py:187-418` (v2ctl only).
- Runtime reads **~92 direct `os.environ` accesses** under `comfymodal_runtime` (Oracle: many are identity/value reads, not all boolean flags). `env.py` provides a shared boolean parser, but configuration remains ambient and distributed.
- `flag_registry.toml` is **metadata, not a whitelist**; unknown flags flow through as untrusted.
- Duplicates/aliases: `COMFYMODAL_V2_*` vs legacy `COMFYMODAL_*`; selector-projected values in `fingerprints.py:28-43`.
- Contradictory defaults: e.g., `contracts.py:61-62` defaults VAE prefetch `off` while other paths inject explicit policy.

### 12.3 Proposed typed canonical config

`loader.clip.source_reader = qd`, `loader.clip.qd = 4`, `loader.clip.block_mib = 32`, `restore.mode = minimal`, `cache.conditioning = benchmark_forced_miss`, `diagnostics.level = benchmark`. Every authoritative artifact carries the resolved config + fingerprint.

---

## 13. Deployment / source identity audit

- Implementations: `tools/v2_control/fingerprints.py:62-97,192-199` (git dirty paths), `modal_app.py` source/build probe, `dependency_manifest.py`, `deploy_and_run_v2_single.bat`. **They hash different file sets** (git-deploy-relevant vs Modal packaging context vs dependency-relevant).
- **Split-brain risk (VERIFIED):** v2ctl identity unchanged while Modal packaging context changes unless excluded by `.modalignore`.
- **`.modalignore` does NOT exclude** `*.log`, `*.txt`, `*.json`, `.v2ctl/`, `.cache/` (it excludes `*.md`, `*.tmp`, `.deploy_log`, `tests/`, `docs/`, `.comfymodal_experiments/`, etc.). Hundreds of root-level `.log`/`.txt`/`.json` artifacts (e.g., `c4_armA_*.log`, `_e27_*.txt`, `temp_result.json`) **ship into the Modal build context** on every deploy, inflating build/upload and potentially affecting any runtime directory walk (registry proof, custom-node identity).

---

## 14. ComfyUI integration audit

- `comfyapp.py` patches ComfyUI execution, `INPUT_TYPES`, model management, history/result.
- `_mm_load_models_gpu` wrapper (`model_preload.py:16028-16053`) bridges every request-scoped `load_models_gpu` into the canonical ledger — proving UNET/VAE loads run through **generic Comfy model management** during graph execution, not the custom fast paths.
- **Half-integrated optimization (VERIFIED):** UNET source/H2D happens inside `load_models_gpu` between CLIP forward and sampling (841 ms healthy, 18.5 s bad). The custom UNET loader machinery exists but the generic path still wraps it.
- `load_models_gpu()` likely still executes on proven-ready models (the ledger shows `load_models_gpu(clip)=0.8 ms`, `load_models_gpu(vae)=57.8 ms` — small but present), indicating the custom ready-state does not fully bypass generic management.
- Narrow upstream patches (e.g., a direct-to-GPU UNET loader hook) would simplify more than layering wrappers.

---

## 15. Exactness / correctness audit

- Output SHA `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` is the authoritative gate for the current workflow; E36/E37 runs reproduce it.
- Risks to exactness: weight/dtype/cast-timing changes (FP32 cast-once ON/OFF across profiles), compute backend, tensor layout, seed, CacheDiT/Sage, VAE, image encoding, output order.
- **Do not** introduce perceptual equivalence as a replacement for bitwise validation without explicit authorization. The gate's SHA check is the correct exactness gate; it must remain fail-closed.

---

## 16. Sampling / VAE / output audit

- Sampling: ledger `sampling = 4748 ms` stable across runs (3651–4846 ms in summaries) — **healthy, low priority**. CacheDiT/Sage attach once; no hidden sync found.
- VAE: `VAE_ACTIVATION_MODE=late`, snapshot retained (`VAE_SNAPSHOT=1`); transition `load_models_gpu(vae)=57.8 ms` + `VAE decode=381 ms` + `graph-tail=167 ms`. The ~0.8 s transition (vs historical ~70 ms physical copy) is explained by generic model-management `load_models_gpu` wrapping, not a new physical copy.
- Output: `output_collection=8.5 ms`, `result:assembly=93 ms` — small; PNG encode/descriptor/base64 fallback paths exist but are not the bottleneck. First durable boundary is correct; post-durable persistence is excluded from critical path (good).

---

## 17. Imports / module structure / code quality

- **God files** (§1.5) cause real bugs: ownership/dispatch logic is spread across `modal_app.py` + `model_preload.py` + `comfymodal_runtime/*`, so a change in one loader branch is easy to miss in another.
- **Cyclic/ambient config:** 100+ flags read at module import and method entry; no single source of truth at runtime.
- **Duplicated logic:** owner-string maps (`__init__.py:3635-3647` vs `comfyapp.py:11857-11861`), deployment-identity hashing (multiple implementations), safetensors parsing (QD custom header parser vs library).
- **Expensive import-time work:** `tools/v2_control/config.py` runs `subprocess.run()` for git state; BATs run local preflight subprocesses.
- **Broad exception handling:** `except Exception`/`pass` suppressions in caches, compat stubs, snapshot fallbacks — fail-soft but mask fast-path exits.
- **Magic constants:** `O0` snapshot order, `524288 KB` fastsafe buffer, `268435456 B` UNET block — scattered, undocumented.
- **Proposed module boundaries:** lifecycle/snapshot, loader source I/O, GPU publication, ownership, scheduler capsule, model metadata, runtime config, performance telemetry, benchmark-only diagnostics.

---

## 18. Dead code / experimental archaeology

- **DEFINITELY/ LIKELY DEAD but reachable:** `unet_qd_probe.py`, `unet_salvage_probe.py` imported by `unet_fastsafetensors.py:78-83`; `staged_safetensors.py`, `unet_pinned_staging.py`, `unet_meta_direct.py` are live dispatch branches but more experimental than fastsafetensors/native.
- **Benchmark-only:** `tools/benchmark_*.py`, `tools/*_ab.py`, `e16_source_io_modal.py`, `e27_*` probes.
- **Root experiment artifacts:** hundreds of `.log`/`.txt`/`.json` (e.g., `c4_armA_*.log`, `_e27_*.txt`, `FULL_RUN_LOGS.md`) — affect build context (§13) and clutter source identity.
- **Legacy but reachable:** non-minimal restore branches; `speculative_clip_hydration` still active (`COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1` in gate deploy flags) though clean lane bypasses it.
- **UNKNOWN:** exact reachability of every probe helper without a full call-graph pass (graph index available; not exhaustively traced here).

---

## 19. Test-quality audit

- 392 test files; 177 reference `mock`/`Mock`, 97 reference `cuda`. Many tests inspect **source text or mocked concurrency**, not real CUDA/ownership handoff/snapshot quiescence.
- **Gaps (P0/P1):**
  - No test asserts producer/consumer owner-string agreement (`restore_clip_loader` vs `restore_preload`).
  - No test exercises the run artifact's `validation_status=FAILED` path or negative-duration stage.
  - No test covers non-zero process/container exit or fallback-status nominal requirement.
  - No test for config identity drift (deploy fingerprint `1` vs runtime `0`).
  - No test for snapshot non-quiescence (threads alive at capture).
  - No deterministic test for the 18.5 s UNET tail or 4.5 s CLIP-forward variance.
- If a test failure is caused by the active E37 deployment lock, that must be stated rather than altering the lock.

---

## 20. Security / reliability / operational review

- **Unbounded queues / cache growth:** conditioning/signature/pre-graph caches keyed by workflow/prompt can grow across filler runs; no eviction bound observed in `clip_conditioning_cache.py`.
- **Memory overcommit:** `maxRSS 35.02 GiB` > `memory_request 32768 MiB` (32 GiB) in the clean-lane run — unflagged; snapshot of full CPU weights by default is questionable at this memory class.
- **Stale locks / partial writes:** `CommitCoordinator` follow-up commits + suppressed fsync failures (`runtime_state.py:228-294,496-525`) weaken durability telemetry.
- **Failed request state:** generic fallbacks can leave the next request/container in a different state (stale globals, partial publication) — no global reset between requests observed.
- **Corrupted manifests:** fail-open-to-miss generally safe, but stale `.runtime_state`/`snapshot_seed` can convert cold→warm silently.

---

## 21. Current E37 clean-lane experiment (independent assessment)

Purpose: isolate CLIP QD from competing startup work to distinguish (A) QD implementation slow vs (B) startup concurrency poisons QD.

**Evidence:**
- E36 QD4 ARM-B (full normal path, `v2_2026-08-21_16-00-22`): CLIP hydration 1593 ms, **CLIP forward 5985 ms**, **UNET lane 9474 ms**, wall 31.4 s.
- E37 clean-lane QD4 (`v2_2026-08-21_22-35-45`): CLIP hydration 1150 ms, **CLIP forward 1110 ms**, **UNET load 841 ms**, wall 21.6 s.
- Bad clean-lane run (`v2_2026-08-21_22-34-15`, same profile): CLIP forward **4414 ms**, UNET load **18543 ms**.

**Interpretation:**
- Clean lane *improves* CLIP forward (5985→1110) and UNET (9474→841) vs the full normal path → **supports hypothesis B** (startup concurrency poisons CLIP/UNET).
- But bad runs *persist inside clean lane* (forward 4414, UNET 18543) → **B is necessary but not sufficient**. Residual GPU/driver/region state or non-excluded competing work remains. The E37 report itself notes **no confirmation runs were performed**.
- QD source read is stable (~1.15 s) in all clean-lane runs → **QD implementation itself is not the slow component** (contradicts a naive "QD is slow" reading).

**Implication under either case:** fixing measurement validity + loader/ownership determinism is prerequisite; the E37 isolation is a useful diagnostic, not a proven root-cause fix.

---

## 22. External Modal/platform research (Lane F)

See §5.3. Key citations: `modal.com/docs/guide/volumes.md`, `modal.com/docs/guide/memory-snapshots.md`, `modal.com/docs/guide/scale.md`, `modal.com/docs/guide/resources.md`, GPU snapshots blog (2025-07-30). **Do not** propose `min_containers>0` as the primary solution — the project targets scale-to-zero cold. Warm capacity is a comparison only.

---

## 23. Historical experiment forensics

**Chronology (HISTORICAL CLAIM ONLY unless noted):**
- `a2286dd` baseline single-invocation seed path, publish_restore_plan removal, clip_vae snapshot/eviction.
- `e5483d5` removed per-boot custom-node content re-hashing (snapshot startup win).
- `0ba7000` E29 ground-truth tracer WIP — **gate does NOT observe E29 ledger** (commit message: "NOT WORKING — remote gate does not observe E29 ledger").
- `8e49d75` E30 QD A/B "complete — QD=4 decisive win (37.9% CLIP source, 11.6% restore)" — **HISTORICAL CLAIM**; not reproduced cleanly here (fastsafe run showed CLIP hydration 617 ms vs QD4 1150 ms under different launch policies — not a controlled A/B).
- E31 FP32 cast-once: eliminates 252 real conversions (14.53 GB/forward); REMOTE win UNPROVEN at report time; later E36 declared cast-once-ON arm authoritative.
- E36: proof/diagnostic repairs; snapshot-creation run excluded as invalid; QD4 ARM-B declared authoritative.
- E37: clean-lane algorithm recovery; QD4 sync after restore; no confirmation runs.

**Process risk (VERIFIED):** E31–E37 work exists **only as uncommitted worktree changes** on the E30 commit (`git_dirty=true`, HEAD `8e49d75`). Seven generations of experimental code are uncommitted — a severe regression/review hazard.

**Half-integrated optimizations (high-value smells):**
1. UNET custom loader exists but generic `load_models_gpu` still wraps it on the critical path (§14).
2. Consumed plan proof exists but `setup-schedule` still 91–1023 ms; `input-types-warm` 575 ms in E36 run.
3. Speculative CLIP hydration flag ON in gate deploy flags but clean lane bypasses it.
4. Early VAE snapshot (`VAE_SNAPSHOT=1`) but post-sampling transition still via generic model management (§16).
5. Snapshot-cached model identity but source re-read possible via fallback (§2.3).

---

## 24. Performance reconstruction (present-day critical-path budget)

**Only the Python/application axis is coherent; the wall waterfall is not currently reconcilable (§11.3).**

| Component | Healthy/canonical | Bad observed | Evidence |
|---|---:|---:|---|
| CLIP hydration / QD source | 1.15 s | 1.15 s | clean-lane ledger |
| CLIP forward | 1.11 s | 4.41 s | clean-lane vs bad run |
| UNET load/activation | 0.84 s | 18.54 s | clean-lane vs bad run |
| Sampling | 4.75 s | 4.75 s | stable |
| VAE load+decode+tail | 0.61 s | — | ledger |
| Listed executor leaves | 8.46 s | ~26.2 s | sum of ledger spans |
| Reported executor-run | 9.75 s | ~30.8 s derived | ~1.29 s unaccounted |
| Python restore+setup+result | 0.90 s | — | ledger |
| **App-side total** | **~10.6 s** | **~31.7 s derived** | meets 12.5 s only when healthy |

**Reported wall observations (same-day):** best **16.7 s**, canonical **21.6 s**, typical-bad **62.9–68.2 s**, bad **95.7 s**, worst **146.3 s**. These cannot be decomposed from stage values (measurement defect, not model).

**Plausible recovered floor (evidence-backed):**
- If UNET load returns to healthy 0.84 s and CLIP forward to 1.11 s deterministically, app-side ≈ 10.6 s (already meets 12.5 s non-scheduling).
- The ~12–16 s pre-Python platform segment is **outside application control** under `min_containers=0`; it is not recoverable by loader tuning.

---

## 25. Target architecture (what I would build now)

**Snapshot owns:** imported modules; model identities/manifests/tokenizers/skeletons; immutable source-volume + deployment identity; fixed runtime shape (CPU, Torch threads, BLAS, GPU, dtype). **No** request ID, workflow plan, live CUDA event, pinned buffer, prefetch worker, executor, or daemon thread. Do not snapshot full CPU weight payloads by default at 32 GiB class.

**Scheduler owns:** scale-to-zero vs warm policy; placement/queueing; container/session identity; one-request-at-a-time admission. If wall latency matters, `min_containers=1` or small warm pool — no Python loader tuning removes provider boot latency.

**Request owns:** resolve immutable `RequestPlan` (model SHA/path, dtype, loader arm, expected SHA, runtime-shape fingerprint) → acquire one lease per model → hydrate CLIP once → load UNET once → sample → decode → assemble → release leases only after all CUDA events + owners complete.

**Model ownership/loaders:** one `ModelRegistry` + one `ModelLease`. CLIP: one authoritative arm (QD4 or fastsafe) chosen before run. UNET: one authoritative direct-to-GPU loader after a controlled A/B — **not** a 4-deep experimental chain. VAE: retain native unless measurable. Every loader returns `(tensor_bundle, owner)` with explicit lifetime. Fallback allowed **only before** the physical source read begins; after bytes are read, fail the arm and record — never silently reread via another path.

**Config/telemetry:** resolve `ResolvedConfig` once in v2ctl; serialize single immutable runtime config + fingerprint; runtime reads that object, not 100 ambient env vars; echo effective config + actual loader identity at request entry; reject fingerprint/runtime mismatch before graph execution; one monotonic clock, one exclusive-span ledger; persist separate `command→response`, `scheduling`, `non-scheduling application`, and nested detail; performance gate fails unless `validation_status==COMPLETE`, residual within tolerance, all boundaries present, `fallback_status==nominal`.

**Resource-oriented schedule:** static CPU work → precompute/scheduler/snapshot; CLIP source read → clean storage lane; CLIP H2D → scoped transfer; CLIP forward → GPU compute critical section; UNET pure source read may overlap CLIP compute **only if measurements prove no harm**; UNET GPU publication → scoped dependency; sampling; VAE pre-copy during sampling slack; decode; first durable; post-durable persistence.

---

## 26. Required final report

### P0 — Correctness / invalid-measurement bugs

1. **Gate vs run-artifact disagreement** (§11.1). `gate_valid=true` while run `validation_status=FAILED`, residual −7741 ms, negative-duration stage. *CONFIRMED (raw artifact).* Changes output acceptance trust. Fix: gate must consume run `validation_status`.
2. **Config identity drift** (§12.1). Deploy fingerprint `FCO=1`/`UNET_FASTSAFE=1` vs runtime `0`/`0`. *CONFIRMED (gate JSON + effective_env + fingerprints.py:37-44).* Invalidates loader A/B attribution. Fix: single resolved config; reject mismatch.
3. **Owner-string mismatch** (§2.4). Producer `restore_clip_loader` vs consumer `restore_preload`. *CONFIRMED (source).* Latent duplicate-read/race. Fix: unify owner keys.
4. **Non-quiescent snapshot** (§6.2). Capture only `gc`+`malloc_trim`. *HIGH-CONFIDENCE.* Risk to restore/scheduling variance + memory pressure. Fix: explicit stop/drain protocol.
5. **Stale `backend_startup_ms`** (§11.2). Identical values across different runs nested in `restore_breakdown`. *CONFIRMED (artifacts).* Misleading non-additive breakdown. Fix: derive fresh or remove.
6. **Memory overcommit** (§20). `maxRSS 35.02 GiB` > 32 GiB request, unflagged. *CONFIRMED.* Fix: raise class or stop snapshotting full weights.
7. **class_name mismatch** (§1.3/§11.2). `ModalRuntimeEntrypoint` (identity) vs `ModalRuntimeEntrypointV2` (target). *CONFIRMED.* Identity inconsistency. Fix: single canonical class name.

### P1 — Multi-second structural performance problems

1. **UNET via generic `load_models_gpu`** (§14). 0.84 s healthy → 18.5 s bad. *CONFIRMED (ledger).* Fix: deterministic direct-to-GPU UNET loader; remove generic wrap on proven-ready model.
2. **CLIP forward variance** (§3/§24). 1.11 s → 4.41 s. *CONFIRMED.* Cause unproven (thread shape / CUDA state / competing work). Fix: record actual Torch/BLAS/native thread state per run; isolate before tuning.
3. **Pre-Python platform segment** (§5.3/§24). ~12–16 s under scale-to-zero. *CONFIRMED.* Not app-recoverable; decide warm-capacity policy explicitly.
4. **Restore bootstrap variance** (§6.3). 180–1403 ms. *CONFIRMED.* Investigate custom-node copy/sync under contention.
5. **QD4 vs FASTSAFE A/B uncontrolled** (§2.2/§21). Not a clean comparison. *CONTRADICTED-BY-ARTIFACT nuance.* Fix: controlled A/B before claiming a winner.
6. **E31 cast-once adoption conflict** (§4.3). Enabled in E36 authoritative arm, disabled in clean lane. *VERIFIED.* Decide one policy; prove exact-SHA parity.

### P2 — Variance / consistency problems

- CLIP forward + UNET load concentration (§24).
- Region drift: runs span `us-south1`/`us-east4`/`us-east1` (artifacts) — provider/region variance unisolated.
- Snapshot age varies 173 s–3488 s across runs (`snapshot_callback_age_at_restore_ms`) — freshness not controlled.
- `setup-schedule` 91–1023 ms, `input-types-warm` 575 ms — recomputation not eliminated by plan proof.

### P3 — Smaller performance opportunities

- Output collection 8.5 ms, result assembly 93 ms, graph-tail 167 ms, VAE transition 58 ms — stable, low priority.
- Sampling 4.75 s stable — do not tune.
- `print(..., flush=True)` waterfall logging — minor CPU sync.

### Architecture debt

God files (§1.5); 8 CLIP loaders + 4-deep UNET chain (§2.2); 100+ ambient flags (§12.2); duplicated identity implementations (§13); dead experiment modules reachable (§18); root artifacts in build context (§13).

### Concurrency and ownership findings

See §9. Top: snapshot-time race, source-reader lifetime, partial publication, stale globals, owner-key mismatch, shutdown race, double reads.

### CPU findings

51 native threads on 12 CPUs (§3.1); Torch 12+14 + OMP/MKL/OpenBLAS 12 each; QD/preload/persistence/telemetry; accidental-redundant hashing/stat/validation.

### GPU/CUDA findings

QD slot-reuse gated on H2D event (correct but couples source to DMA); UNET single-buffer + per-chunk + final `cuda.synchronize` (blocking); `empty_cache()` in fastsafe path; CLIP forward FP32 cast-once eliminates 252 conversions but end-to-end win unproven.

### Storage/Volume findings

Deployment-static reads recomputed on cold (§5.2); Volume 2.5 GB/s documented ceiling is a different layer than historical 40+ GB/s probes (§5.3); `.modalignore` ships root artifacts into build context (§13).

### Snapshot/restore findings

Non-quiescent (§6.2); minimal restore active but distributed (§6.3); restore now small (~660 ms) but bootstrap varies (§6.3); drift via many env gates (§6.6).

### Scheduler/cache findings

Scheduler knows topology but remote recomputes INPUT_TYPES/registry/hash (§7.2); caches keyed too narrowly can silently change workload (§8); conditioning/pre-graph/experiment caches highest contamination risk.

### Configuration/profile findings

Identity drift (§12.1, P0); typed v2ctl config exists but runtime ambient (§12.2); `flag_registry.toml` metadata not whitelist; contradictory defaults.

### Measurement/gating findings

Gate ignores run `validation_status` (§11.1); field disagreements (§11.2); executor budget non-additive (§11.3); negative residual masked (§11.1); `scheduling_ms=0` in summary vs 18702 waterfall.

### Code structure / maintainability findings

God files; ambient config; duplicated owner maps/identity hashing/safetensors parsing; expensive import-time subprocess; broad `except/pass`; magic constants; no runtime single-source-of-truth config.

### Dead/legacy code findings

`unet_qd_probe`/`unet_salvage_probe` imported by production; `staged_safetensors`/`unet_pinned_staging`/`unet_meta_direct` live but experimental; hundreds of root `.log`/`.txt`/`.json` artifacts; speculative hydration flag ON but bypassed in clean lane.

### Test gaps

No owner-key agreement test; no `validation_status=FAILED` test; no non-zero exit / fallback-nominal test; no config-drift test; no snapshot-quiescence test; no variance/UNET-tail deterministic test; many tests mock concurrency rather than exercise it.

### Recommended target architecture

See §25.

### Prioritized recovery order

1. **Repair measurement validity** (§11): gate consumes run `validation_status`; one monotonic clock; exclusive-span ledger; fail-closed acceptance invariant. *Unblocks all other claims.*
2. **Make config/identity deterministic** (§12): single resolved config; reject deploy/runtime mismatch; fix `.modalignore` to exclude root artifacts.
3. **Make UNET execution identity deterministic** (§14): one direct-to-GPU loader; remove generic `load_models_gpu` wrap on proven-ready model; controlled A/B.
4. **Diagnose CLIP-forward variance** (§3/§24): record actual thread/CUDA state per run; isolate cause before tuning.
5. **Quiesce snapshot** (§6.2): explicit stop/drain.
6. **Decide warm-capacity policy** (§5.3): explicit scale-to-zero vs `min_containers=1` trade-off.
7. **Only then** tune loader microarchitecture (QD block/worker, pinned buffers, cast-once).

---

### Things I would fix even if performance did not matter

- Unify owner-string keys (`restore_clip_loader` vs `restore_preload`) — correctness hazard.
- Make the gate consume the run artifact's `validation_status` — trustworthiness hazard.
- Remove stale `backend_startup_ms` from `restore_breakdown` — misleading telemetry.
- Fix `.modalignore` to exclude `*.log`/`*.txt`/`*.json`/`.v2ctl`/`.cache` — build-context hygiene + identity safety.
- Commit the E31–E37 worktree (or split into reviewed commits) — seven uncommitted generations is an unacceptable regression hazard.
- Add a single runtime config object instead of 100 ambient env reads.
- Quiesce snapshot capture explicitly.

### Things most likely to recover the missing seconds

- **UNET loader determinism** (0.84 s → 18.5 s swing) — largest app-side recoverable tail.
- **CLIP-forward variance elimination** (1.11 s → 4.41 s) — second largest.
- **Pre-Python platform segment** — only recoverable via warm-capacity policy, not app code.
- **Restore bootstrap variance** (180–1403 ms) — secondary.
- QD source read, sampling, VAE, output are **already healthy** — do not spend effort there.

---

### Final question

> If you inherited this repository tomorrow and were personally accountable for making it correct, maintainable, deterministic, and consistently ≤12.5 s non-scheduling while preserving scale-to-zero and exact output, what would you change first, what would you delete/simplify, and what would you refuse to optimize until the architecture was cleaned up?

**Change first:**
1. Fix the measurement gate so a run with `validation_status=FAILED` can never be called `valid` — without this, every optimization claim is untrustworthy.
2. Collapse the 100+ ambient env flags into one resolved runtime config object and reject deploy/runtime identity drift.
3. Replace the 4-deep UNET loader chain + generic `load_models_gpu` wrap with one deterministic direct-to-GPU UNET loader, proven by a controlled A/B.

**Delete/simplify:**
- Delete or quarantine `unet_qd_probe.py`, `unet_salvage_probe.py`, `staged_safetensors.py`, `unet_pinned_staging.py`, `unet_meta_direct.py` unless a controlled A/B proves one is needed; keep fastsafetensors + native as the two supported CLIP/UNET arms.
- Remove the stale `backend_startup_ms` field from `restore_breakdown`.
- Fix `.modalignore` and delete root-level experiment `.log`/`.txt`/`.json` artifacts from the build context.
- Commit the E31–E37 worktree into reviewed commits.
- Split `modal_app.py` / `model_preload.py` / `comfyapp.py` along the boundaries in §17 (prerequisite for safely fixing the above, not itself a second-saver).

**Refuse to optimize until cleaned up:**
- Any further QD block-size / worker-count / pinned-buffer tuning.
- Any QD-vs-fastsafe claim from the existing uncontrolled runs.
- Sampler / VAE / PNG / graph-tail micro-optimization (stable, small).
- More speculative hydration / prefetch overlap (fix ownership + fallback first).
- Allocator purges / `malloc_trim` / CUDA micro-sync (cannot explain the 18.5 s UNET tail).
- Broad thread-policy sweeps before recording actual per-run thread state.
- Any optimization that changes the execution path before exact-SHA parity is re-established.
- Treating a single 16.7 s / 21.6 s run (or `gate_valid=true`) as evidence the ≤12.5 s target is reliably met.

**Opinion vs evidence:** The measurement, identity, and ownership findings are *evidence-backed* (raw artifacts + source). The "UNET/CLIP variance is the missing seconds" conclusion is *supported hypothesis* from ledger decomposition, not yet a controlled causal proof — which is exactly why step 3 requires a controlled A/B before any further loader tuning. The ≤12.5 s target is *plausible* on the healthy app-side path but *not reliably achieved* today because the application path is unstable and the platform pre-Python segment is outside application control under scale-to-zero.
