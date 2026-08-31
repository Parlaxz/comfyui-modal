# E38L Independent Full Repository / Architecture / Performance / Correctness Audit

> **SUPERSESSION NOTICE (2026-08-30):** Historical audit; preserve its
> evidence, but use `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current
> generated-output guidance. Output durability is off by default; strict
> commit/reopen/hash proof is opt-in. S4 source publication durability remains
> mandatory.

**Date:** 2026-08-21  
**Auditor:** E38L  
**Repository:** `comfyui-modal`  
**Branch observed:** `TESTING2`  
**Audit mode:** read-only; no source/test/runtime file was modified, no deployment or generation was run, and the concurrent E37 lane was not touched.

## Audit basis and evidence policy

This audit was performed from current working-tree source, current tests and configuration, persisted E36/E37 artifacts, git state, graph structure, historical reports, and current official Modal documentation. Prior reports were treated as claims to verify, not as authority.

The worktree was already substantially dirty before this report, including E29-E37 source/test/config changes, untracked E37 files, runtime artifacts, and reports. Those changes were preserved. The only file created by this audit is this report.

The Codebase Memory index was ready at generation `2026-08-20T20:45:51Z` in full mode with 45,721 nodes and 245,576 edges. Cited source paths had no recorded parse gaps, but most were marked `metadata_changed`; native source was therefore used as the final authority. The index deliberately excludes runtime/cache/control-plane directories and 77 ignored/generated files. One JSON fixture is parse-partial and one historical Markdown report timed out during extraction. Raw benchmark artifacts outside the repository were read directly.

**Reconciliation note (2026-08-21):** This E38L report incorporates an independent senior read-only Comfy integration review. Graph metadata was stale for the relevant source, so native source was used as the authority; the review created no source changes. The oracle review ran the relevant E26/VAE/preload, E31 forward/profile, and E37/deferred-commit tests successfully (34 passed), plus persistence/transport tests (33 passed). The full suite and real CUDA/Modal execution remain unverified.

Confidence labels used below:

- **CONFIRMED** — directly established by current source or a raw artifact.
- **HIGH-CONFIDENCE** — source mechanics and supporting evidence agree; a dedicated runtime A/B is still absent.
- **SUPPORTED HYPOTHESIS** — causal explanation is strongly suggested but not isolated.
- **SPECULATIVE** — plausible, but current evidence is insufficient.
- **UNKNOWN** — the repository does not currently expose enough evidence.

Historical status labels are explicit: **VERIFIED AGAINST CURRENT SOURCE**, **VERIFIED AGAINST RAW ARTIFACT**, **HISTORICAL CLAIM ONLY**, **SUPERSEDED**, **CONTRADICTED**, **UNPROVEN**, and **UNKNOWN**.

## Executive verdict

### Overall health

| Area | Verdict | Reason |
|---|---|---|
| Architecture | **Poor, but recoverable** | The system has a real control plane and real ownership/ledger mechanisms, but production behavior is the composition of several experimental state machines, monkey patches, fallback readers, and legacy launch paths. |
| Correctness | **Conditionally healthy** | Exact output SHA, QD coverage, source identity, and canonical ledger predicates are real. Cross-request/lifecycle races and fail-open paths remain insufficiently proven. |
| Measurement trustworthiness | **Not production-grade** | Canonical ledger proof and legacy waterfall acceptance are separate contracts. E37 proves its algorithmic gate while its timing projection contains a -7,741 ms residual and `validation_status=FAILED`. A gate-valid artifact can still represent an invalid process or timing measurement. |
| Performance | **Variable and structurally over-concurrent** | Valid production first-durable observations are 17.927–18.734 s for QD4, while isolated E37 clean-lane canonical time is about 10.563 s but not an accepted end-to-end comparison. |
| Maintainability | **Poor** | `comfyapp.py`, `modal_app.py`, and `model_preload.py` are god files; runtime monkey patches, module globals, dynamic imports, broad exception handling, and many profile-era flags create hidden coupling. |
| 12.5 s non-scheduling target | **Not established as recoverable today** | The clean-lane evidence makes a sub-12.5 s request-critical path plausible, but no source-matched, timing-authoritative production run proves it. I would not promise the target until accounting and ownership are simplified. |

### Five most important discoveries

1. **The QD4 reader is not FASTSAFE with four threads.** QD is a separate SafeTensors source/staging/H2D implementation. It shares an ownership contract with FASTSAFE and can fall back to FASTSAFE, but the two are not one pipeline (`clip_qd_reader.py:1842-1850`, `clip_fast_hydration.py:604-683`).
2. **The E31 QD4/FASTSAFE A/B is not reader-only.** QD4 changes reader, QD, block size, and launch policy; FASTSAFE disables QD and uses a different launch policy (`config/v2/profiles/e31-clip-fp32-qd4-arm-b.toml:19-30`, `e31-clip-fp32-fastsafe-arm-b.toml:19-26`).
3. **E37 clean-lane proof is valid but its end-to-end timing is not authoritative.** The raw artifact has exact SHA, QD4, 240/240 reads, canonical ledger status/endpoints, and clean-lane predicates, but also `residual_ms=-7741.041552`, `EXCEEDS_TOLERANCE`, and `validation_status=FAILED` (`comfymodal-data/.../v2_2026-08-21_22-35-45/run_0.json:18736-18770`).
4. **The CPU is not governed by one resource budget.** E37 observed 28 visible CPUs, 51 native threads, Torch intra-op 12, inter-op 14, and OMP/MKL/OpenBLAS 12 while the runtime can additionally create restore, QD, prefetch, speculative, and Comfy workers (`summary.json:111-140`; `model_preload.py:11509-11518`; `clip_qd_reader.py:1664-1685`).
5. **Snapshot quiescence is instrumented, not enforced as a hard invariant.** Active-read bookkeeping is strong, but there is no single barrier proving zero source reads, H2D, QD workers, unresolved futures, persistence, or request state at snapshot capture. A timed executor close can intentionally return with live workers (`model_preload.py:11795-11831`).

## Actual architecture map

### Production request path

```text
Local ComfyUI / Studio request
  -> __init__.py request adapter
  -> canonical_execution.execute_modal_prompt()
  -> prepare_modal_execution()
       -> workflow/model extraction
       -> ExecutionPlan and stable identities
       -> profile / restore publication cache
  -> modal_client.run_prompt_stream()
  -> Modal async generator handle
  -> ModalRuntimeEntrypoint.run_prompt_stream()
  -> run_plan_stream()
  -> _run_plan_stream_impl()
       -> remote method entry and identity
       -> plan deserialize / validation / registry proof
       -> CLIP source and device-ready publication
       -> CLIP conditioning
       -> UNET model-management / sampling
       -> VAE model-management / decode
       -> output encoding and result registry
       -> first durable result event
       -> terminal cleanup / GPU release / deferred persistence
```

**Source ownership:** local dispatch and plan construction are owned by `canonical_execution.py:3389-3800`; Modal submission is owned by `modal_client.py:433-557`; remote lifecycle is owned by `comfymodal_runtime/modal_app.py:10118-10217,17762-17971`; model preparation is shared between `model_preload.py`, `clip_fast_hydration_wiring.py`, `clip_qd_reader.py`, Comfy `model_management`, and `comfyapp.py`.

### Lifecycle boundaries

1. **Modal restore-banner -> first Python:** platform/container scheduling and restore. It is not Python `restore()` time.
2. **First Python -> `restore()` exit:** `ModalRuntimeEntrypoint.restore()` records `remote_python_resume` at its first executable line and decomposes restore spans (`modal_app.py:10118-10217`).
3. **Restore exit -> method entry:** separately recorded as `restore_end_to_modal_method_entry`.
4. **Method entry -> plan receipt:** request identity, payload handling, and plan deserialization (`modal_app.py:17931-17971`).
5. **Plan -> CLIP ready:** QD or FASTSAFE, owner publication, binding, synchronization.
6. **CLIP ready -> forward:** conditioning and CLIP forward.
7. **UNET -> sampler -> VAE:** Comfy model-management and GPU mutation lane; VAE has a per-load UNET event gate.
8. **Output -> first durable:** output registry/encoding and durable result event.
9. **After first durable:** synchronous terminal cleanup, release, watcher join, and deferred Volume/cache commit (`modal_app.py:17827-17929`).

### Current concurrency/resource schedule

```text
RESTORE / SNAPSHOT
  snapshot restore, CUDA/bootstrap, identity and reload guards
  + restore ThreadPoolExecutor (up to 3 workers)
  + optional speculative CLIP daemon
  + optional checkpoint prewarm supervisor/workers
  + optional cache/persistence work
  barrier is profile-dependent, not a universal quiescence barrier

REQUEST SETUP
  method entry -> identity -> plan deserialize/validation
  + cancellation watcher when a control queue exists

CLIP LANE
  FASTSAFE: native SafeTensorsFileLoader direct-to-GPU
  OR QD: four source workers, two reusable slots per worker,
         H2D completion events, final host waits, owner publication
  speculative and demand lanes can represent duplicate work unless
  identity/take/owner-retained proof succeeds

CLIP FORWARD
  GPU critical section / scoped stream event or device-wide sync

UNET / SAMPLING
  source/preload work may overlap depending on profile
  GPU mutation is protected by CLIP/UNET coordination and Comfy gates
  generic load_models_gpu remains reachable; proven-ready fast return is opt-in

VAE / OUTPUT
  VAE waits on matching UNET Event, but timeout is fail-open
  decode -> output collection -> first durable
  persistence and cleanup continue after the durable boundary
```

The E37 clean-lane schedule is intentionally different: restore -> plan identity -> synchronous post-restore QD4 -> quiescence/device-ready -> bind -> conditioning miss -> sampling -> VAE. It disables speculative hydration, checkpoint prewarm, graph/model preloads, input-type warming, persistence, fast-cold orchestration, and most diagnostic work (`config/v2/profiles/e37-clean-lane-qd4.toml:18-55`). It is an attribution experiment, not the normal production schedule.

## P0 — Correctness / invalid-measurement bugs

### P0-1 — Gate-valid artifacts can be invalid timing or failed processes

- **Confidence:** **CONFIRMED**.
- **Source:** `tools/v2_control/validation.py:629-778`, `tools/v2_control/backend.py:433-594,780-974`; `comfymodal_runtime/experiment_result_store.py:419-571`.
- **Evidence:** E37 raw waterfall reports `residual_ms=-7741.041552`, `reconciliation_status=EXCEEDS_TOLERANCE`, and `validation_status=FAILED`, while its separate strict proof/clean-lane predicates pass. E36 documents a 52.9724 s SIGABRT/container-abort artifact that had a gate-valid marker but is excluded (`E36_FULL_CRITICAL_PATH_REPORT.md:200-204`).
- **Mechanism:** The canonical ledger validator proves explicit endpoints, status, and zero-gap; the legacy waterfall validator/projection is a separate accounting system. Backend exit code and provenance are captured, but process/container health and negative residual rejection are not one indivisible acceptance invariant.
- **Output impact:** No direct output change; it can certify a wrong execution path or make invalid timing look authoritative.
- **How to prove/falsify:** Add read-only validation requiring successful process/container terminal state, no crash/SIGABRT evidence, finite nonnegative spans, no negative residuals, and exact ledger/waterfall boundary equivalence. Re-evaluate existing E36/E37 artifacts.
- **Performance impact:** It invalidates rankings rather than saving time. Any optimization selected from rejected timing is unsafe.
- **Dependencies/conflicts:** Must precede any QD/FASTSAFE or overlap A/B; otherwise experiments are not comparable.

### P0-2 — Broad finalization/cleanup exceptions can erase evidence

- **Confidence:** **HIGH-CONFIDENCE**.
- **Source:** `critical_path_ledger.py:423-457,817-868`; `modal_app.py:10136-10152,17888-17929`; many cleanup paths in `speculative_clip_hydration.py:833-875,980-1006`.
- **Mechanism:** Ledger persistence and cleanup helpers catch broad exceptions and return `None`/continue. Some validators fail closed on missing canonical status, but other projections can retain partial or stale fields.
- **Output impact:** Usually none; measurement, owner release, and cache durability can be wrong or unproven.
- **How to prove/falsify:** Inject failures at ledger persist, terminal cleanup, owner close, deferred commit, and artifact write; require explicit `FAILED` status with reason and terminal health.
- **Performance impact:** Unknown; silent fallback and lost telemetry can hide multi-second waits.
- **Dependencies/conflicts:** Unified runtime status must distinguish `NOMINAL`, `DEGRADED`, and `FAILED` before benchmark acceptance.

### P0-3 — Cross-request owner/lifecycle assumptions are not proven safe

- **Confidence:** **SUPPORTED HYPOTHESIS** for corruption; **CONFIRMED** for the single-flight assumptions.
- **Source:** `speculative_clip_hydration.py:878-916,919-977`; `model_preload.py:11542-11605,11637-11669`; `gpu_lane_coordination.py:20-90`.
- **Mechanism:** Speculative lookup can fall back to the reserved `_RESTORE_TIME_KEY`; `active_speculative_request_id()` assumes one active lane. `ModelPreloadCoordinator._active` is overwritten by each preparation and implicit waits use it when no preparation is passed. These are safe only if the single-request container assumption is absolute and cleanup is complete.
- **Output impact:** A proven race could consume the wrong CLIP owner, bind stale tensors, or wait on the wrong future. Current source alone does not prove that concurrent requests occur.
- **How to prove/falsify:** Deterministically interleave two request IDs, delayed lane completion, take/close, and two preparations; assert owner identity, future identity, and request identity at every handoff.
- **Performance impact:** Could cause fallback rereads or deadlock-like waits; no number is defensible.
- **Dependencies/conflicts:** Must be resolved before enabling container reuse or concurrent requests.

## P1 — Multi-second structural performance problems

### P1-1 — No unified CPU/resource budget

- **Confidence:** **CONFIRMED** as a design property; **HIGH-CONFIDENCE** as a variance source.
- **Source:** `runtime_shape.py:168-239,262-298,311-378`; `model_preload.py:11509-11518`; `clip_qd_reader.py:1664-1685`; `checkpoint_prewarm.py:707-768`; `speculative_clip_hydration.py:541-557,646-655`; `clip_fast_hydration.py:699-707,843-849`.
- **Evidence:** E37 raw summary observed `cpu_visible=28`, `native_thread_count=51`, Torch intra-op 12, inter-op 14, `OMP_NUM_THREADS=12`, `MKL_NUM_THREADS=12`, and `OPENBLAS_NUM_THREADS=12` (`summary.json:111-140`). E37 QD adds four Python source workers; restore and optional prefetch/speculation add more.
- **Mechanism:** TBASE deliberately passes through environment/native settings. Python worker layers are bounded individually, not globally coordinated with Torch/native pools or Comfy execution threads.
- **Output impact:** Normally none; starvation, timing variance, and failed cleanup can affect path identity.
- **How to prove/falsify:** At restore, speculation, QD start, forward, sampling, durable, and teardown record runnable threads, native IDs, affinity, Torch pools, BLAS pools, queue waits, context switches, and CPU time.
- **Performance impact:** Current evidence supports contention/variance, not a precise savings number.
- **Dependencies/conflicts:** Resource scheduling must be designed before speculative overlap or UNET prefetch is re-enabled.

### P1-2 — Speculative read and demand read are only partially integrated

- **Confidence:** **CONFIRMED**.
- **Source:** `speculative_clip_hydration.py:760-857,939-977`; `clip_qd_reader.py:1842-1850,1886-1919`; `clip_fast_hydration_wiring.py` demand path; E30 report `V2_BATCH_E30_CLIP_QD_IO_IMPLEMENTATION.md:35-99`.
- **Mechanism:** Speculation owns GPU buffers/tensors and must be taken exactly once. A miss, identity mismatch, cancellation, failure, or E37 clean-lane policy sends demand to the normal hydrator. The normal demand fallback remains FASTSAFE, so an early QD/FASTSAFE read can be paid and then reread.
- **Output impact:** Fallback is intended to preserve exact output, but every branch requires exact SHA proof; owner lifetime mistakes could change correctness.
- **How to prove/falsify:** Require per-run `speculative_started`, `completed`, `take=true`, `bind=true`, `owner_retained=true`, `demand_read=false`, and no duplicate canonical active-read key.
- **Performance impact:** A duplicate multi-gigabyte read is a credible multi-second loss; no fixed saving or loss is assigned without a matched artifact.
- **Dependencies/conflicts:** Do not optimize source queue depth until consumption and no-reread are authoritative.

### P1-3 — Generic Comfy model-management work remains reachable after custom ownership

- **Confidence:** **HIGH-CONFIDENCE**.
- **Source:** `model_preload.py:4141-4205,4437-4458,4760-4889`; `comfyapp.py:15850-15901`; `clip_cold_path_forensics.py:1087-1168`.
- **Mechanism:** Custom wrappers instrument and sometimes short-circuit `load_models_gpu`, but the original Comfy call remains the normal path unless the opt-in proven-ready gate fires. The source explicitly describes repeated ModelPatcher bookkeeping over an already resident UNET (`model_preload.py:4156-4170`). Multiple wrappers can stack around the same function.
- **Output impact:** Fast return is fail-closed; generic bookkeeping should preserve output, but wrapper ordering and patch state are correctness-sensitive.
- **How to prove/falsify:** For a source-matched run, record every `load_models_gpu` invocation, caller, model identity, allocation delta, patch bookkeeping, and whether fast return occurred. Require one owner transition per model.
- **Performance impact:** The code identifies real serial bookkeeping, but no current isolated millisecond saving is assigned.
- **Dependencies/conflicts:** A narrow Comfy integration patch is preferable to another wrapper/flag layer.

### P1-4 — Snapshot/restore has no hard all-resources quiescence barrier

- **Confidence:** **HIGH-CONFIDENCE**.
- **Source:** `modal_app.py:10118+`; `model_preload.py:11795-11831`; `comfyapp.py:5040-5247`; `clip_qd_reader.py:1707-1726`; runtime bootstrap and cache reload paths.
- **Evidence:** Storage telemetry can show persistence enqueued but not persisted; the restore source has active-read bookkeeping but no single barrier joining every reader, H2D event, QD worker, future, and persistence queue.
- **Mechanism:** Snapshot state can contain retained models, wrappers, manifests, identity, and feature-dependent pools/queues. A timed executor close can return with `alive_thread_count > 0`; QD is not globally joined by snapshot capture.
- **Output impact:** Snapshot may restore stale/partial owner state; a failure may leave the next request in a different state.
- **How to prove/falsify:** Snapshot acceptance must assert zero active reads, zero QD/prefetch workers, zero H2D events, zero unresolved futures, zero persistence queue, zero request state, and one owner per canonical model.
- **Performance impact:** Avoiding duplicate restore/reload and invalid snapshots could recover large variance, but no savings number is assigned.
- **Dependencies/conflicts:** Must be fixed before moving more work into snapshot or enabling speculative restore-time loading.

### P1-5 — Remote scheduler knowledge does not eliminate expensive remote recomputation

- **Confidence:** **CONFIRMED**.
- **Source:** `contracts.py:1003-1170,1278-1398`; `canonical_execution.py:1446-1738`; `registry_proof.py:118-230,233-361,414-495`; `execution_warm.py:65-94`; `modal_app.py:9155-9258,18172-18472`.
- **Mechanism:** `ExecutionPlan` carries topology, reachable IDs, roles, static signatures, loader signatures, and hashes, but remote still imports/resolves registry classes, hashes files, validates parity, and can call `INPUT_TYPES()`.
- **Evidence:** Current E36 summary reports `plan_build_ms=94.0`, contradicting historical “5.5 s plan build” claims. The remaining remote registry/INPUT_TYPES path is real but not isolated in current timing.
- **Output impact:** Proof recomputation is correctness-relevant; removing it without a cheaper proof is unsafe.
- **How to prove/falsify:** Build a deployment capsule with a signed/hashed registry proof and measure cheap tuple validation against full remote recomputation; reject mismatch before execution.
- **Performance impact:** Historical registry-import costs are not a current guaranteed number; no savings is promised.
- **Dependencies/conflicts:** Do not cache F and spend the same time recomputing F to validate it.

### P1-6 — VAE synchronization is fail-open

- **Confidence:** **CONFIRMED**.
- **Source:** `comfyapp.py:1595-1654`.
- **Mechanism:** VAE waits on the matching UNET completion event, but timeout returns `True` and proceeds. The event lookup also has a fallback to the oldest active UNET when graph context is empty.
- **Output impact:** A timeout or ambiguous gate can allow VAE activation without proof of the intended UNET completion. Current exact-output evidence does not prove the timeout path is safe.
- **How to prove/falsify:** Force a blocked UNET, timeout the wait, and assert that VAE either fails closed or consumes the exact matching generation token; verify no wrong-key event is used.
- **Performance impact:** Fail-open avoids a hard wait but can trigger duplicate or contending model-management work.
- **Dependencies/conflicts:** Replace with generation-keyed fail-closed ownership for benchmark/production paths; retain an explicitly labeled diagnostic mode if needed.

### P1-7 — VAE-overlap lane timeout is ignored and ownership is assumed

- **Confidence:** **CONFIRMED** by source and a live oracle repro.
- **Scope:** **P1 when optional E31/VAE-overlap is enabled.** This review does not establish an impact on the default production path, where that overlap lane is not enabled.
- **Source:** `model_preload.py:9477-9489,21065`.
- **Evidence:** `MutationLane.acquire(timeout=...)` does not enforce timeout expiry; a live waiter remained blocked beyond 200 ms despite a 50 ms timeout. The VAE caller ignores the acquisition result and sets `_lane_acquired` true unconditionally.
- **Mechanism:** VAE can proceed without proof that it owns the mutation lane, defeating the overlap lane’s synchronization contract.
- **Output impact:** Exact-output corruption is not established, but concurrent VAE/model mutation, wrong-owner use, or a deadlock-like wait is not ruled out when the opt-in lane is active. No default-path impact is claimed.
- **How to prove/falsify:** Use a monotonic deadline, check the acquisition result, fail closed when ownership is not obtained, and add adversarial timeout/late-release/interleaving tests.
- **Performance impact:** A fail-closed timeout may expose lost overlap, but preserving unproven ownership is not an acceptable performance optimization.
- **Dependencies/conflicts:** Must be repaired before any E31/VAE-overlap performance comparison is treated as valid.

### P1-8 — Global E31 VAE sampling state is not cleaned up per request

- **Confidence:** **CONFIRMED** as a lifecycle hazard; the affected behavior is **opt-in E31/VAE-overlap scope**.
- **Scope:** Production does not clear the global `_VAE_SAMPLING_END_EVENT` and timestamp; tests do. This report does not infer that the default production path observes stale state.
- **Source:** `model_preload.py:19891-19896,20653-20656,20940,21041`.
- **Mechanism:** E31 requests can observe stale cross-request sampling-end state when a prior request leaves the global event/timestamp populated. A process-global signal is being used where request/generation ownership is required.
- **Output impact:** A later request may accept an old event or timestamp as its own synchronization evidence; output corruption is not proven, but lifecycle correctness is unproven for the opt-in path.
- **How to prove/falsify:** Key the event and timestamp by request/generation, clear them in `finally` on every terminal path, and interleave two request IDs with success, timeout, cancellation, and exception outcomes.
- **Performance impact:** Stale state can create false readiness or unnecessary waits; no timing effect is assigned.
- **Dependencies/conflicts:** Resolve with the lane ownership state machine before enabling cross-request reuse or VAE overlap.

### P1-9 — Successful E31 forward callbacks remain attached across requests

- **Confidence:** **HIGH-CONFIDENCE** from current source mechanics; **opt-in E31 scope**.
- **Source:** `clip_fast_hydration_wiring.py:1166`.
- **Mechanism:** A successful E31 forward callback remains attached. Strict request/count validation can fail on a later request when a reused hydrated CLIP skips rebind, leaving callback ownership tied to the earlier request rather than the current generation.
- **Output impact:** The later request can fail validation or observe stale callback ownership; a default-path impact is not established.
- **How to prove/falsify:** Give callbacks explicit per-request bind/unbind ownership, or make binding idempotent with generation ownership; add a two-request hydrated-CLIP reuse test that asserts callback identity, request/count validation, and cleanup.
- **Performance impact:** Failures can force fallback/rebind work; no savings or loss is assigned.
- **Dependencies/conflicts:** Must be covered before accepting E31 forward/profile reuse results.

## P2 — Variance / consistency problems

### P2-1 — Storage locality and throughput are not measured at the byte-origin layer

- **Confidence:** **CONFIRMED**.
- **Source:** `comfyapp.py:4918-5247`; `model_preload.py:9667-9800`; raw `app_logs_agents34_full.txt`.
- **Mechanism:** Active-read telemetry records mounted path, size, inode/device, wall time, queueing, and owner, but raw artifacts report `read_bytes`, `rchar`, page-fault, and block-input counters as unsupported or unobserved. It cannot distinguish remote backing, FUSE/chunk cache, kernel page cache, or resident traversal.
- **Evidence:** Integrated UNET/VAE intervals and repeated VAE reads differ materially; historical 40+ GB/s probes therefore cannot be interpreted as integrated Modal Volume throughput.
- **Output impact:** None directly; it makes causal performance claims unsafe.
- **How to prove/falsify:** Compare true cold, repeated, local/Image, and Volume reads with reliable byte/page/block counters and identical synchronization boundaries.
- **Performance impact:** Unknown; Modal’s documented “up to 2.5 GB/s” is not a universal ceiling.

### P2-2 — QD source and H2D are coupled by reusable slots

- **Confidence:** **CONFIRMED**.
- **Source:** `clip_qd_reader.py:1602-1659,1664-1726`.
- **Mechanism:** QD allocates two slots per worker and cannot reuse a slot until its prior CUDA event completes. Thus QD4 is four source workers and up to eight host slots, not an unlimited source queue.
- **Evidence:** E37 reports QD4, 240/240 blocks, source wall 1,043.5138 ms, H2D host issue 127.399 ms, and CUDA event 27.3155 ms. These are distinct boundaries, not interchangeable “H2D time.”
- **Output impact:** None if publication validation succeeds.
- **How to prove/falsify:** Correlate `buffer_pool_wait_ms`, slot event waits, source wall, host issue, device event, and final ready per block.
- **Performance impact:** Backpressure can limit source throughput under GPU contention; no tuning number is assigned.

### P2-3 — Profile defaults and selector projections drift

- **Confidence:** **CONFIRMED**.
- **Source:** `config/v2/flag_registry.toml:1-19,139-147,237-244`; `clip_fast_hydration.py:70-116`; `e29-tracer.toml:44-49`; `canonical_execution.py:1803`; `fingerprints.py:28-43,160-183`.
- **Mechanism:** The registry is metadata, not a whitelist; unknown flags are allowed. FastSafe thread documentation says 4 while runtime/profile values use 8. `COMFYMODAL_V2_ENV_PROFILE` is documented as `production` while canonical execution reads `inherit` as its environment default. Selector projection only changes flags already present in the resolved config.
- **Output impact:** A profile label may not identify the actual effective runtime; output exactness can be affected by dtype/loader flags.
- **How to prove/falsify:** Serialize requested, projected, deployed, observed, and runtime-effective config as one canonical fingerprint; test absent projected flags and all default paths.
- **Performance impact:** Explains A/B ambiguity and variance, not a measured saving.

### P2-4 — Multiple identity/hash domains are easy to confuse

- **Confidence:** **CONFIRMED**.
- **Source:** `tools/v2_control/config.py:438-544`; `tools/v2_control/fingerprints.py:1-199`; `tools/v2_control/provenance.py`; `contracts.py:1367-1398`; `registry_proof.py:118-153,296-361`.
- **Mechanism:** Git dirty hashes, deploy/run/config fingerprints, artifact SHA, `DeploymentIdentity.combined_hash`, registry fingerprints, and `ExecutionPlan.stable_hash` have different scopes. They are not one canonical identity object.
- **Output impact:** Stale cache or wrong source/profile could produce wrong output or false acceptance.
- **How to prove/falsify:** Emit all domains with explicit type/scope and test each invalidation independently.
- **Performance impact:** Cache misses and unnecessary proof/hash work; no fixed number.

### P2-5 — Registry proof persistence is atomic but not inter-process locked

- **Confidence:** **HIGH-CONFIDENCE**.
- **Source:** `registry_proof_store.py:161-184,275-329`.
- **Mechanism:** Atomic `os.replace` and a process-local thread lock protect one process. Separate processes can still read/modify/write concurrently; the bounded store may lose an update.
- **Output impact:** A lost proof should be a cache miss, not wrong output, if all callers remain fail-closed.
- **How to prove/falsify:** Concurrently write distinct entries from separate processes and verify no lost entry; validate corrupt/missing store behavior.
- **Performance impact:** Misses can re-trigger registry work.

### P2-6 — Partial waterfalls are retained beside canonical data

- **Confidence:** **CONFIRMED**.
- **Source:** `experiment_result_store.py:419-441,486-570`.
- **Mechanism:** Remote partial/different waterfalls are preserved as `remote_partial_waterfall`, while local reconciliation can become `final_reconciled_waterfall`. This is useful provenance but dangerous if consumers treat the projection as complete proof.
- **Output impact:** None; timing validity is affected.
- **How to prove/falsify:** Require consumers to state whether a field came from canonical ledger, complete remote waterfall, local projection, or partial diagnostic.
- **Performance impact:** Prevents invalid optimization decisions.

### P2-7 — Persistence and durability are distinct

- **Confidence:** **CONFIRMED**.
- **Source:** `modal_app.py:17888-17929`; conditioning/cache persistence modules; E37 clean-lane explicitly disables persistence (`e37-clean-lane-qd4.toml:41-55`).
- **Mechanism:** First durable result can be emitted while deferred commit remains pending. “Enqueued” is not “persisted” or “committed.”
- **Output impact:** Output may already be delivered while next-request cache state differs.
- **How to prove/falsify:** Require `persisted=1`, commit completion, queue depth zero, and readback before calling a cache result durable.
- **Performance impact:** Persistence must remain post-durable unless the benchmark explicitly measures it.

### P2-8 — GPU fast-return telemetry double-counts request calls

- **Confidence:** **CONFIRMED** measurement-correctness issue.
- **Source:** `model_preload.py:4193,4233-4234,4564`.
- **Mechanism:** The GPU fast-return path increments `_gpu_request_call_count_var` at line 4193 and again at lines 4233-4234 before returning at line 4564.
- **Output impact:** None established; request-count and derived fast-return telemetry are inflated.
- **How to prove/falsify:** Count exactly one increment per invocation and add a regression assertion for one fast-return call, including repeated calls and fallback/error paths.
- **Performance impact:** Measurement only; it can distort call-rate, hit-rate, and per-request analyses but no wall-time effect is assigned.
- **Dependencies/conflicts:** Correct before using GPU fast-return telemetry to compare profiles or infer redundant model-management work.

## P3 — Smaller performance opportunities

These are real but should not precede the structural work:

- Remove repeated diagnostic `print(..., flush=True)` and JSON/string formatting from nominal production paths once proof fields are persisted (`comfyapp.py:1527-1533,1553-1559`; `model_preload.py:4897-4908`). **Confidence: HIGH-CONFIDENCE; no ms estimate.**
- Stop re-reading metadata/header/identity when a deployment capsule has already proved immutable facts. **Confidence: SUPPORTED HYPOTHESIS; must retain cheap mismatch checks.**
- Eliminate synthetic file-open/mmap timing events where the live loader exposes no such boundary (`model_preload.py:9767-9782`). **Confidence: CONFIRMED; improves truth, not necessarily wall time.**
- Avoid successful-path allocator purge; current FASTSAFE only calls `empty_cache()` on error/release paths (`clip_fast_hydration.py:677-683,1704-1705`). **Confidence: HIGH-CONFIDENCE; no saving assigned.**
- Keep PNG/output cleanup after first durable unless it is demonstrably before the durability boundary. Current measured output collection is about 8–11 ms in E37/E36 summaries; this is not the missing-seconds problem.

## Architecture debt

### God files and mixed ownership

- `comfyapp.py` is approximately 24k lines and mixes Comfy patches, model-read registry, FUSE governor, output handling, model-management wrappers, and diagnostics.
- `comfymodal_runtime/modal_app.py` is approximately 20k lines and mixes Modal lifecycle, plan execution, telemetry, persistence, cancellation, validation, and cleanup.
- `comfymodal_runtime/model_preload.py` is approximately 21k lines and mixes restore workers, GPU mutation, Comfy wrappers, UNET ownership, diagnostics, and lifecycle state.
- `clip_conditioning_cache.py` contains cache policy, Volume reload/persistence, async workers, and request semantics.

These sizes matter because resource ownership, timing boundaries, and fallback semantics are distributed through methods that are difficult to reason about atomically.

### Dynamic monkey-patching

The system wraps `load_models_gpu`, `load_model_gpu`, `soft_empty_cache`, `free_memory`, and related functions in several places. The wrappers are guarded and often fail closed, but wrapper order is itself runtime state. This creates measurement nesting, duplicate bookkeeping, and a risk that a benchmark observes a wrapper path rather than the underlying operation.

### Cyclic call dependencies

The graph reports 18 circular CALLS components. Relevant runtime components include `FastColdOrchestrator` prefetch/demand methods and the GPU coordination -> orchestration copy-event path. Other cycles are intentional profile inheritance or UI/test cycles. The runtime cycles are architecture debt because telemetry callbacks call orchestration, orchestration calls lane coordination, and both participate in the same state transitions.

### Mutable globals

Examples include `_ACTIVE_MODEL_READS`, `_LANES`, `_STATES`, `_active` preparation, ledger stores, identity caches, and wrapper-installed sentinels. They are individually guarded in places, but the system has no single request/container state owner.

### Broad exception handling

The repository contains extensive `except Exception`/`except BaseException` paths in loaders, telemetry, cache, cleanup, and orchestration. Exceptions are sometimes correctly converted to a fallback; in other places they are swallowed. Every performance-sensitive fallback needs an explicit status/reason and owner cleanup record.

## Concurrency and ownership findings

### Positive controls

- `_ACTIVE_MODEL_READS_LOCK` protects duplicate canonical reads (`comfyapp.py:5040-5108`).
- QD validates complete source coverage, bytes, H2D completion, and publication before owner creation (`clip_qd_reader.py:1732-1823`).
- GPU CLIP/UNET state is request-keyed and condition-protected (`gpu_lane_coordination.py:20-90`).
- QD and FASTSAFE owners document that storage must not be closed while tensor views are live.
- Terminal cleanup and GPU release use idempotence flags and a lock (`modal_app.py:17792-17803,17888-17929`).

### Race-sensitive controls

- Speculative publication writes `owners`, `per_file_sds`, `record`, and `finished_mono_ns` outside one common lock; reads also poll some fields outside the lock (`speculative_clip_hydration.py:785-857,919-977`). CPython assignment atomicity is not a lifecycle proof.
- Reserved restore-time lane fallback assumes one active request.
- Timed executor shutdown can return with live workers.
- QD owner close and demand take are separately synchronized but need an interleaving test to rule out late worker publication.
- UNET/VAE fallback selection can return the oldest active event when graph context is empty.
- Optional E31/VAE-overlap uses a `MutationLane` timeout that is not enforced and a VAE caller that assumes acquisition succeeded; this is not evidence of a default-path defect.
- Optional E31/VAE state uses global sampling-end event/timestamp values without production cleanup, and successful forward callbacks can remain attached when a hydrated CLIP is reused.

### Required state machines

Replace independent booleans with explicit state machines:

```text
ModelOwner: ABSENT -> READING -> DEVICE_READY -> BOUND -> IN_USE -> RELEASED
                 \-> DEGRADED/FALLBACK -> FAILED

Request: RECEIVED -> PLAN_ACCEPTED -> CLIP_READY -> FORWARD_DONE
       -> SAMPLING -> VAE_DONE -> DURABLE -> TEARDOWN_COMPLETE

Snapshot: BUILDING -> QUIESCENT -> CAPTURED -> RESTORED -> VERIFIED
                 \-> INVALID/FAILED

RunStatus: NOMINAL | DEGRADED(reason_code) | FAILED(reason_code)
```

Only the owner state machine should be allowed to close a buffer, release a model, or publish device-ready.

## CPU findings

### Classification

| Work | Classification |
|---|---|
| Deployment identity, registry proof, immutable model metadata | Deployment/snapshot-static |
| Workflow topology, reachable nodes, static signatures | Workflow-static / scheduler capsule |
| QD partitioning, worker creation, source reads | Request-dynamic |
| Speculative and checkpoint prefetch | Request-dynamic, optional |
| Tensor transforms, dtype/cast, model construction | Runtime work; some can move to snapshot |
| Torch/BLAS/native pools | Runtime resource, currently not globally budgeted |
| JSON/hash/introspection/logging/flush | Accidental/redundant when repeated in nominal path |
| CUDA event waits and owner conditions | Unavoidable synchronization when ownership requires it |

### Findings

- Restore workers, QD workers, prefetch workers, speculative polling, FASTSAFE executors, Comfy workers, persistence workers, and native Torch/BLAS pools can overlap.
- `Future.result()` and event waits are synchronous from their caller’s perspective; their time must be attributed to the wait owner, not silently folded into a parent.
- The speculative CUDA readiness loop sleeps every 20 ms for up to five seconds. It is not a busy spin, but it still occupies a daemon thread and delays clean lifecycle accounting.
- No evidence supports blaming host/CPU variance until application-controlled thread count, runnable queue, queue wait, and CPU-time attribution are captured together.

## GPU/CUDA findings

### CLIP loader semantics

**FASTSAFE** constructs `SafeTensorsFileLoader`, adds files, calls `copy_files_to_device`, obtains tensor views, binds with `assign=True`, and either waits on a scoped copy event or calls a device-wide `torch.cuda.synchronize()` (`clip_fast_hydration.py:604-676`). Its owner is the native loader plus GPU buffer.

**QD** parses the SafeTensors header, computes disjoint regions, opens one descriptor per worker, reads blocks with the selected syscall mode, copies reusable host slots into one final GPU byte buffer, waits for all CUDA events, validates coverage, creates alignment-checked views, and publishes `QdGpuOwner` (`clip_qd_reader.py:1586-1823`).

**QD and FASTSAFE answer:**

1. They do not compose as one reader pipeline. They compose at the `(sd, loader, fb)` ownership contract and fallback boundary.
2. QD replaces the source-read, staging, and H2D implementation for the selected CLIP lane; it does not replace SafeTensors metadata semantics or Comfy binding.
3. QD4 means four explicit workers, normally 32 MiB blocks, two reusable slots per worker, and event-based publication.
4. The QD4/FASTSAFE A/B changes launch policy and explicit reader settings in addition to QD enablement.
5. Old staged, CPU, `safetensors_cuda`, native, and demand fallback paths remain reachable under capability/error/flag conditions.

### Synchronization

Material synchronization includes:

- FASTSAFE device-wide sync when scoped readiness is disabled (`clip_fast_hydration.py:645-652`).
- QD per-slot event waits and final host waits (`clip_qd_reader.py:1707-1726`).
- Scoped producer/consumer stream events (`gpu_lane_coordination.py:149-203`).
- CLIP forward event synchronization (`clip_forward_forensics.py:147-179,289-325`).
- Model-management `soft_empty_cache`/synchronize wrappers and E27 decomposition.

No evidence proves that a small “H2D” field always represents physical copy execution. E37’s 127 ms host-issue and 27 ms CUDA-event values demonstrate why issue, device execution, final completion, publication, and wait must remain separate.

### Exactness

- QD alignment fallback preserves values but may allocate an extra tensor and lose zero-copy.
- FP32 cast-once is an exact widening operation but can change downstream arithmetic relative to BF16; an exact output SHA is therefore required per profile.
- E36 reports 398 `NOOP_SAME_TENSOR`, zero real conversions, and zero new allocations for its residency proof. That proves that run’s cast behavior, not a remote ON/OFF speedup.
- No current evidence independently proves CacheDiT attachment exactly once or Sage path equivalence across every profile. Those must remain explicit artifact predicates.

## Storage/Volume findings

The application reads mounted paths; QD/FASTSAFE do not issue Volume RPCs. Volume reloads occur in restore/runtime-state/model-generation guards and conditioning-cache persistence paths. Active-read registration and FUSE large-read admission happen below the model loader (`comfyapp.py:5040-5247`).

Current source can prove path identity, file size, inode/device, queueing, and wall interval. It cannot prove remote bytes versus FUSE/chunk cache, kernel page cache, or resident memory traversal. Therefore historical 40+ GB/s probes and integrated 2–3 GB/s-ish model intervals are not measuring the same thing.

Modal official documentation accessed 2026-08-21:

- [Volumes](https://modal.com/docs/guide/volumes): distributed read-mostly filesystem, caching/chunking, explicit `.reload()` semantics, up to 2.5 GB/s documented performance description, not a universal ceiling, and no distributed file locking.
- [Storing model weights](https://modal.com/docs/guide/model-weights): Volumes/Image storage are recommended for model weights; load-once behavior is application-controlled.
- [Memory snapshots](https://modal.com/docs/guide/memory-snapshots): CPU snapshots restore CPU memory; GPU snapshots are alpha, cannot be assumed to remove storage loading, and CPU-only snapshot phases cannot access GPUs.
- [Lifecycle functions](https://modal.com/docs/guide/lifecycle-functions), [scaling](https://modal.com/docs/guide/scale), [cold starts](https://modal.com/docs/guide/cold-start), [preemption](https://modal.com/docs/guide/preemption), and [region selection](https://modal.com/docs/guide/region-selection): container reuse, exit grace, scale-to-zero, preemption, routing region, and execution region are separate semantics.

No application-specific latency, locality, or failure claim should be attributed to Modal without a controlled same-source/same-cache/same-region test.

## Snapshot/restore findings

### Retained state

Potential snapshot state includes CPU model tensors, patchers/wrappers, registry and identity data, manifests, runtime configuration, pinned/staged buffers, futures/thread pools, cache/persistence state, and feature-dependent request/session state. The source has no universal proof that all transient objects are removed before snapshot.

### Restore classification

| Operation | Classification |
|---|---|
| Modal restore boundary, CPU snapshot restore, required identity/generation validation | MUST_BE_IN_RESTORE |
| Immutable registry/source/model metadata and deployment identity | SNAPSHOT_STATIC / DEPLOYMENT_STATIC |
| Scheduler plan/topology/static signatures | SCHEDULER_CARRY |
| Runtime-state generation check and cheap capsule validation | MOVE_AFTER_RESTORE / scheduler |
| Re-reading unchanged manifests after exact proof | REDUNDANT |
| Active-read/QD/Gantt counters and synthetic I/O markers | DIAGNOSTIC_ONLY |
| Unconditional legacy reload callbacks and restore-only probes | LEGACY |
| FUSE/backend byte origin and exact retained wrappers | UNKNOWN |

### Timing labels are not interchangeable

E37 summary values include `submission_to_remote_python_resume_ms=12094.987`, `restore_method_ms=678.233`, and `restore_total_ms=303.653`. E36 summary includes `restore_total_ms=1931.276`, `restore_method_ms=2045.939`, and a `backend_startup_ms=22896.93` field inside restore breakdown. These are different producers/boundaries. A parent named “restore” is not an explanation.

### SIGABRT

The E36 52.9724 s artifact terminated with `terminate called without an active exception`/SIGABRT and is invalid timing. Current source has fixed sleeps, retries, and bounded termination helpers, but this audit did not prove the root cause. It must be correlated with native crash output, last active-read event, futures, and snapshot lifecycle—not explained as generic platform variance.

## Scheduler/cache findings

### Cache inventory

| Cache | Scope/key | Invalidation/failure | Risk |
|---|---|---|---|
| Deployment anchor `.deployed_state.json` | Deployment | Missing/partial anchor fails closed | Ignored by graph; direct artifact proof required |
| Registry proof store | Deployment anchor + root + workflow hash; bounded eight entries | Schema/identity/incomplete proof -> miss; atomic write | Thread lock is not inter-process lock |
| Profile/restore disk caches | Profile/restore identity; bounded roughly 100 entries | Corrupt/schema mismatch -> miss; exact-key failure removal | Eviction comments say LRU while code must be checked against timestamp behavior |
| ExecutionPlan | Immutable structural workflow/topology/signatures | Stable hash excludes request/output/conditioning | Must not key conditioning/result cache alone |
| Model/locality/owner cache | Per process/container/model identity | Fallback/release/identity mismatch | Owner lifetime and duplicate reads are critical |
| Conditioning cache | Prompt/signature + deployment/CLIP identity/policy | Hit/miss/Volume persistence; forced miss in benchmarks | Must remain separate from immutable startup capsule |
| Output/result/artifact cache | Output identity/SHA and request/result scope | Exact SHA/provenance | Must never silently replace a fresh benchmark |

### Combined startup capsule

The current system should converge on two immutable capsules and one request capsule:

```text
DeploymentCapsule:
  deployment/config/runtime/dependency/custom-node hashes
  Comfy commit and normalized roots
  registry class identities and INPUT_TYPES proof
  SafeTensors metadata/offset maps
  tokenizer/model configs and loader signatures

WorkflowCapsule:
  workflow/source hash, topology, reachable nodes, roles
  loader/sampler/output IDs and static signatures
  selected immutable model identities
  accepted ExecutionPlan proof

RequestCapsule:
  request nonce, dynamic inputs, seed/control values,
  conditioning signature, output identity and exactness policy
```

Validation must compare schema/version/hash tuples and reject mismatches in constant/linear metadata time. It must not recompute full registry/file/input signatures to validate a cache hit.

## Configuration/profile findings

The registry is 1,069 lines and explicitly metadata-only (`flag_registry.toml:1-19`). Unknown flags flow through and are fingerprinted, but are not rejected or semantically typed. Flags are consumed at build/import/restore/method/request/harness boundaries with defaults distributed across TOML, environment readers, BAT files, and Python modules.

The required replacement is a typed canonical configuration object with nested domains such as:

```text
loader.clip.source_reader = qd
loader.clip.qd = 4
loader.clip.block_mib = 32
restore.mode = minimal
cache.conditioning = benchmark_forced_miss
diagnostics.level = benchmark
```

Every authoritative artifact must include resolved config, effective projection, and one canonical configuration fingerprint.

## Measurement/gating findings

### What is sound

`CriticalPathSpan` uses a fine process-local `perf_counter_ns()` duration axis and a monotonic correlation axis, unions child intervals, and records explicit work/wait/sync (`critical_path_ledger.py:300-457`). The canonical ledger requires explicit remote-Python-resume and first-durable endpoints and zero-gap validation (`validation.py:289-341`).

### What is not sound enough

- `_persist()` clamps residuals to zero for canonical spans, while the legacy waterfall exposes negative residuals.
- `experiment_result_store.py` preserves partial remote waterfall alongside local reconciliation; consumers can mistake the local projection for remote proof.
- Zero and absent/null are not universally treated as distinct semantics in legacy records.
- Error-time finalization may swallow exceptions.
- Strict backend artifact discovery binds invocation/profile/request identity, but compatibility helpers retain mtime selection (`backend.py:638-655,899-943`).
- Backend captures subprocess exit code, but historical gate-valid SIGABRT proves process health is not fully coupled to acceptance.

### Fail-closed acceptance invariant

Accept a timing run only when all hold:

1. Backend exit code is zero and container/process lifecycle is terminally healthy.
2. Artifact is parseable and bound to invocation, request, profile, config, deployment, and source identity.
3. Output SHA exactly matches expected output.
4. Canonical ledger status and endpoint status are `ok`.
5. Serial ledger has `zero_gap=true`.
6. Every accepted span has finite nonnegative duration and known clock/boundary semantics.
7. No negative residual or incomplete waterfall is accepted as a timing verdict.
8. Parent accounting uses interval union, not child sum.
9. Missing fields remain absent/unproven, never zero.
10. Fallback status is `NOMINAL`, not merely “output succeeded.”
11. Intended loader/profile/ownership path is proven from events, not profile name.
12. First durable and post-durable tails are separately accounted.

## Fallback audit

| Fallback | Current behavior | Risk |
|---|---|---|
| FASTSAFE package/API failure | `hydrate_fastsafetensors` raises; caller can fall back (`clip_fast_hydration.py:607-615,677-683`) | Degraded reader may retain nominal profile unless status is propagated |
| `hydrate_auto` preferred-mode failure | Catches exception and returns `cpu_standard(fallback)` (`clip_fast_hydration.py:776-792`) | Exact output is not proven for every fallback; timing cohort can be contaminated |
| QD disabled/error/coverage/H2D/publication failure | Caller falls back to normal demand path | May reread after partial GPU allocation; cleanup must be proven |
| Pinned allocation failure | QD uses pageable host slots (`clip_qd_reader.py:1641-1649`) | Performance degradation; output should remain exact |
| Alignment mismatch | Extra aligned GPU tensor construction | Loses zero-copy and changes memory/latency path |
| Scoped CUDA event unavailable | FASTSAFE can use device-wide sync | Broader GPU fence and attribution change |
| Speculative lane miss/cancel | Demand hydration | Potential duplicate multi-gigabyte work |
| VAE UNET wait timeout | Proceeds fail-open (`comfyapp.py:1647-1654`) | Wrong owner/generation or duplicate load not ruled out |
| Cache/manifest corruption | Most stores become miss/reload | Safe only if status says degraded and identity is re-proven |

All fallbacks need exact reason codes, cleanup status, output exactness status, and a benchmark cohort exclusion rule.

## ComfyUI integration audit

The repository deliberately patches Comfy model-management behavior: `load_models_gpu`, `load_model_gpu`, `soft_empty_cache`, `free_memory`, offload-device selection, and high-VRAM behavior (`comfyapp.py:15850-15931`; `model_preload.py:4141-4205`). These patches are not inherently wrong, but they create a second ownership/control plane around ModelPatcher.

The narrow design should be:

1. Prove the custom owner is device-ready.
2. Teach one narrow Comfy seam to accept that ready state and skip only redundant bookkeeping.
3. Preserve Comfy’s actual mutation/load path when the proof is absent.
4. Keep one wrapper for observability, not multiple nested wrappers.

The current opt-in E25 proven-ready fast return is fail-closed and preserves the CLIP GPU gate. It is not universally active, so “model ready” does not currently mean `load_models_gpu()` was skipped.

Sampling and VAE are comparatively stable in valid artifacts: sampler 3.651–3.715 s and VAE decode 0.381–0.435 s. That does not prove all hidden model-management transition work is included in the VAE field. Output collection is about 8–11 ms and is not the multi-second priority.

## Exactness / sampling / VAE / output

- Exact image SHA remains the gate; no perceptual equivalence is recommended.
- Model dtype, cast timing, layout, scheduler, seed, CacheDiT, Sage, VAE, output order, and PNG encoding can all change SHA.
- QD source coverage and tensor shape/dtype checks are strong, but owner publication must remain before bind and forward.
- Cache conditioning is intentionally forced miss in E36/E37 benchmark profiles; result caching must remain logically separate from deployment/static metadata.
- First durable is the result boundary; persistence, release, and output transport after that point must be reported separately.
- No source evidence in this audit authorizes weakening the SHA gate.

## Dead/legacy/experimental code

| Classification | Examples / assessment |
|---|---|
| DEFINITELY DEAD | None assigned from static inspection alone; dynamic imports and profile selectors make a strong dead-code claim unsafe. |
| LIKELY DEAD | Old E27/E28 probes, duplicate BATs, experiment-specific launchers, and unused diagnostic branches not selected by canonical v2ctl. Verify invocation reachability before removal. |
| LEGACY BUT REACHABLE | Native/CPU/staged/safetensors_cuda hydration fallbacks; legacy mtime artifact discovery; restore-only probe path; Comfy generic model-management path. |
| BENCHMARK-ONLY | `clean_lane.py`, E27-E37 proof/forensics, source probes, raw artifact writers, and many profile-specific gates. |
| PRODUCTION | canonical `v2ctl` strict path, `execute_modal_prompt`, `run_plan_stream`, ordinary Comfy graph execution, exact SHA output validation. |
| UNKNOWN | Experimental GPU snapshot shadow, rehoming/NUMA/backing lanes, compatibility launchers, and code excluded from the graph. |

The mere existence of old implementations has maintenance cost when imported or included in fingerprints. `.modalignore` excludes many generated/test artifacts from deployment, but local dirty-state and control-plane identity can still be affected by deploy-relevant paths.

## Test gaps

The E38 audit itself did not run deployments or remote generations and did not modify tests. The independent oracle review did run the relevant E26/VAE/preload, E31 forward/profile, E37/deferred-commit tests (34 passed), and persistence/transport tests (33 passed). The full suite and real CUDA/Modal execution remain unverified. Source inspection and the oracle review show the highest-risk remaining gaps are deterministic integration tests for:

1. Gate-valid SIGABRT/nonzero process exit.
2. Negative residual and incomplete-waterfall rejection.
3. Strict versus legacy mtime artifact selection.
4. Fallback status propagation and nominal-cohort exclusion.
5. QD slot reuse under delayed CUDA events.
6. Speculative take/close/cancel publication races.
7. Reserved restore key and overlapping request IDs.
8. Active preparation rollover and timed executor shutdown.
9. Snapshot quiescence with blocked read, H2D, future, QD worker, and persistence queue.
10. Profile projection/default drift and observed-versus-requested thread shape.
11. Registry-proof concurrent process writers.
12. Comfy `load_models_gpu` ready-state skip versus generic bookkeeping.
13. Exact SHA across QD, FASTSAFE, staged, CPU fallback, FP32, CacheDiT, Sage, VAE, and output transport branches.
14. `MutationLane.acquire(timeout=...)` expiry, late release, checked acquisition result, and fail-closed VAE behavior under adversarial E31/VAE-overlap interleavings.
15. Two-request reuse of a hydrated CLIP with E31 forward callback bind/unbind, strict request/count validation, and generation ownership.
16. Cross-request E31/VAE sampling event/timestamp isolation, including success, timeout, cancellation, exception, and `finally` cleanup.
17. GPU fast-return telemetry asserting exactly one `_gpu_request_call_count_var` increment per invocation.

## Security / reliability / operations

- Artifact discovery scans an external sibling benchmark root; strict invocation/profile/request binding is required and should be the only production mode.
- Volume writes have documented last-writer-wins semantics and no distributed lock; manifests and cache objects require atomic writes plus generation identity.
- Temporary JSON writes are generally atomic, but best-effort persistence can silently turn failure into a cache miss.
- Model and output paths need canonicalization and bounded roots; no path derived from a request should be allowed to escape the intended model/output root.
- Thread, VRAM, owner, and persistence cleanup must be observable after failed requests. A failed request must not alter the next request’s global registries or device ownership.
- Exit handlers, deferred commits, and cancellation watchers have bounded cleanup windows. A timeout must be `FAILED`/`DEGRADED`, not silently successful.

## Historical experiment forensics

| Era | Current assessment |
|---|---|
| E27 | Instrumentation foundation confirmed; parity/complete remote baseline remained blocked. **VERIFIED AGAINST CURRENT REPORT; baseline claim UNPROVEN.** |
| E28 | Restored CPU model, FASTSAFE, speculative hydration, and cast-once paths introduced. **VERIFIED AGAINST CURRENT SOURCE; integration was partial.** |
| E29 | Canonical ledger, ownership, first-durable, and identity proof introduced. **VERIFIED AGAINST CURRENT SOURCE; only canonical ledger is authoritative.** |
| E30 | Genuine QD source reader introduced at speculative seam; demand remains FASTSAFE. **VERIFIED AGAINST CURRENT SOURCE; broad remote acceptance SUPERSEDED/UNPROVEN.** |
| E31 | FP32 cast-once and forward forensics introduced. **Residency behavior VERIFIED; isolated latency saving UNPROVEN.** |
| E32 | Canonical v2ctl control plane and provenance introduced. **Operational architecture VERIFIED; compatibility/legacy paths remain.** |
| E33-E35 | Integration, FASTSAFE, QD4, ownership, and ledger repairs. **Historical claims only unless a current artifact supports them.** |
| E36 | Valid QD4 ARM-A/ARM-B and FASTSAFE comparison; SIGABRT artifact excluded. **VERIFIED AGAINST RAW ARTIFACT; restore variance confounds reader ranking.** |
| E37 | First structurally valid clean-lane QD4 gate; G1/confirmation not started. **Algorithm proof VERIFIED; performance superiority UNPROVEN; timing projection contradicted by raw residual.** |

Superseded/contradicted claims:

- “FASTSAFE won” is superseded by the valid E36 QD4 observations, but not a universal QD4 win because restore and host variance were not matched.
- “E30 remote acceptance proven” is unsupported by the reviewed evidence.
- “E31 cast-once saved a measured X ms” is unproven; residency/conversion proof is not an ON/OFF A/B.
- “5.5 s plan build” is contradicted by current `plan_build_ms=94.0`.
- E36’s 52.9724 s snapshot-abort timing is invalid, not a slow valid run.
- E37 `validation_status=FAILED` does not refute the clean-lane algorithm proof, but it does refute treating its legacy timing aggregate as authoritative.

## Performance reconstruction

The following values are measured boundaries, not additive components. Overlap and missing fields prevent summing them.

| Evidence | First durable / canonical | Wall | Restore | Pre-sampler | Sampler | VAE | CLIP/QD evidence | Status |
|---|---:|---:|---:|---:|---:|---:|---|---|
| E36 valid QD4 ARM-A | 17,926.783 ms | 29,546.0 ms | 3,166.082 ms | 8,598.776 ms | 3,714.725 ms | 434.837 ms | QD source 2,654.184 ms; H2D host issue 1,703.038 ms | Best valid full production observation |
| E36 valid FASTSAFE control | 24,716.236 ms | 35,275.8 ms | 9,597.093 ms | 9,328.501 ms | 3,676.141 ms | 443.733 ms | loader-to-device-ready 491.372 ms | Valid control; restore confounded |
| E36 valid current QD4 ARM-B | 18,734.476 ms | 31,381.8 ms | 1,931.276 ms | 10,220.535 ms | 3,690.867 ms | 381.284 ms | QD source 2,885.518 ms; H2D host issue 3,202.154 ms | Current full production observation |
| E36 snapshot-abort | Excluded | Excluded | — | — | — | — | SIGABRT | Invalid |
| E37 clean lane | ~10,562.860 ms from raw canonical endpoints | 21,564.1 ms | 303.653 ms | 4,646.097 ms | 3,651.129 ms | 381.691 ms | QD source 1,043.514 ms; H2D host 127.399 ms; CUDA event 27.316 ms | Proof-valid algorithm; timing aggregate invalid |

The E37 canonical interval is derived from raw ledger `modal_restore_entry` at `216362289252` and ledger end `226925149733`; it is not promoted to a production performance result because the same artifact’s legacy timing is unreconciled.

### BEST HEALTHY OBSERVED

E36 QD4 ARM-A is the best valid full-production observation: 17.927 s first durable and 29.546 s wall. It is not a universal floor.

### CURRENT TYPICAL

The most defensible current-source full run is E36 QD4 ARM-B: 18.734 s first durable and 31.382 s wall. It shows stable sampler/VAE but materially variable restore, pre-sampler, QD, and H2D host issue.

### CURRENT BAD

The 52.9724 s E36 snapshot-abort is invalid and excluded. E37’s 21.564 s wall is also not a timing-authoritative point because of negative residual/reconciliation failure.

### PLAUSIBLE RECOVERED FLOOR

No end-to-end numeric floor is justified. The clean-lane 10.563 s canonical interval demonstrates that a narrower schedule can be below 12.5 s from the measured remote-Python boundary, but it excludes normal startup concurrency and has invalid legacy aggregate accounting. The recovered floor is therefore **a design hypothesis, not a budget**.

## Recommended target architecture

1. **One canonical deployment identity.** Deploy, snapshot, scheduler, remote, caches, and validators consume one typed `DeploymentCapsule`.
2. **One immutable scheduler/workflow capsule.** Scheduler computes plan/topology/roles/static signatures once. Remote validates hashes and proof tuples cheaply; it does not recompute the same expensive graph to prove the cache.
3. **One explicit model owner registry.** CLIP, UNET, and VAE each have one owner state machine and one publication/release authority. QD and FASTSAFE are implementations of one CLIP source-reader interface, not parallel lifecycle systems.
4. **Quiescent snapshot contract.** Snapshot capture fails closed unless all readers, H2D events, QD/prefetch workers, futures, persistence, and request state are idle.
5. **Resource-oriented request schedule.** Static work is precomputed; CLIP source and H2D use a scoped lane; CLIP forward owns the GPU critical section; UNET source may overlap only after measured CPU/storage proof; UNET H2D has a scoped dependency; sampling; VAE pre-copy only where slack is proven; decode; first durable; post-durable persistence.
6. **Narrow Comfy seam.** Add one proven-ready check around `load_models_gpu`/ModelPatcher bookkeeping, preserving the original path when proof is absent. Remove layers of diagnostic monkey patches from nominal execution.
7. **Typed config.** Replace loosely coordinated booleans with nested typed loader/restore/cache/diagnostic policies, range validation, explicit incompatible combinations, and resolved-config fingerprints.
8. **Canonical ledger only.** Use one clock/boundary model, child interval unions, explicit endpoint contracts, and a separate diagnostic view for partial/legacy waterfalls.
9. **Exactness proof.** Every accepted run carries deployment, model, dtype, seed, scheduler, conditioning, output SHA, and intended-path proof. Fallbacks are `DEGRADED` unless explicitly part of the cohort.
10. **Separate post-durable work.** Persistence, cleanup, and telemetry flush cannot retroactively change first-durable timing or acceptance status.

## Prioritized recovery order

1. Repair v2ctl acceptance: process health, negative residuals, complete waterfall semantics, missing/zero distinction, and fallback status.
2. Before enabling optional E31/VAE overlap, repair monotonic lane deadlines, checked acquisition, fail-closed ownership, request/generation-keyed VAE events/timestamps, and callback bind/unbind cleanup.
3. Freeze one source-matched production baseline and one clean-lane diagnostic baseline; do not compare profiles until launch policy and all non-reader settings are identical.
4. Collapse CLIP ownership to one reader interface and prove speculative take/no-reread/owner-retained behavior. Keep QD and FASTSAFE as explicit implementations.
5. Add a global CPU/native/IO resource budget and measure runnable pressure before enabling overlap.
6. Add hard snapshot quiescence and lifecycle tests for all workers/futures/owners/persistence.
7. Remove generic ready-model bookkeeping with one narrow Comfy patch, not another wrapper.
8. Move immutable registry/metadata/offset/config proof into deployment/scheduler capsules with cheap validation.
9. Repair default/selector/config identity drift, serialize effective configuration in every artifact, and correct the GPU fast-return call counter.
10. Only then run matched QD4/FASTSAFE, speculative on/off, UNET overlap, VAE early activation, and FP32 A/B experiments.
11. Optimize small output/diagnostic costs last.

## Things I would fix even if performance did not matter

- Fail-closed acceptance for SIGABRT, nonzero exit, negative residual, incomplete ledger, stale identity, and degraded fallback.
- Cross-request/lifecycle owner and future isolation.
- Hard snapshot quiescence and deterministic worker shutdown.
- VAE generation-keyed ownership instead of fail-open/oldest-event behavior.
- One canonical deployment/config identity and typed incompatible-flag validation.
- Removal of silent broad-exception paths around correctness state.
- Exact SHA proof across every reachable reader/dtype/cache/output branch.
- Atomic, observable cache persistence and inter-process registry-store coordination.
- Narrow Comfy ownership integration with one source of truth.
- Module decomposition of lifecycle, loaders, ownership, scheduler capsules, telemetry, and benchmark-only diagnostics.

## Things most likely to recover the missing seconds

- Eliminate duplicate speculative/demand model reads by proving the owner handoff.
- Remove restore-time work that is not actually required after a quiescent snapshot and immutable deployment capsule.
- Stop paying generic `load_models_gpu`/ModelPatcher bookkeeping when a model is already proven ready.
- Replace remote registry/`INPUT_TYPES()` recomputation with cheap validated deployment/workflow proof.
- Enforce a CPU/native/IO budget so QD source and H2D are not poisoned by unrelated restore/prefetch work.
- Reconsider UNET source overlap only after controlled evidence shows it does not degrade QD, CLIP forward, or GPU launch.
- Keep VAE pre-copy/early activation only when measured slack and ownership proof show real overlap.

## Final accountability answer

If I inherited this repository tomorrow, I would first make benchmark acceptance trustworthy, establish hard lifecycle/owner state machines, and remove duplicate model-management ownership. I would then collapse deployment/workflow/request identity into typed capsules and make snapshot capture fail closed on any live reader, future, H2D, persistence queue, or duplicate owner.

I would delete or quarantine obsolete BAT/probe/experiment paths from the production interface, remove stacked diagnostic monkey patches from nominal execution, and retain QD/FASTSAFE/staged/CPU implementations only behind one explicit reader contract with reason-coded fallback. I would not optimize queue depth, speculative hydration, UNET overlap, FP32, VAE timing, or output cleanup until the ledger, process-health gate, profile identity, and owner handoff were correct.

My opinion is that a consistently <=12.5 s **non-scheduling** result may be recoverable from the clean-lane evidence, but it is not proven by the current production artifacts. I would refuse to claim that target until one source-matched, exact-SHA, fallback-free, timing-authoritative run demonstrates the complete intended path and a second run establishes consistency.

## Appendix: primary evidence index

- Execution: `__init__.py:2424-2508`; `canonical_execution.py:3389-3800`; `modal_client.py:433-557`; `modal_app.py:10118-10217,17762-17971`.
- CLIP/QD/FASTSAFE: `clip_fast_hydration.py:604-853`; `clip_qd_reader.py:1580-1919`; `speculative_clip_hydration.py:760-1006`; `gpu_lane_coordination.py:149-203`.
- CPU/ownership: `model_preload.py:11499-11840`; `checkpoint_prewarm.py:707-768`; `runtime_shape.py:160-378`.
- Storage/restore: `comfyapp.py:4918-5247`; `runtime_bootstrap.py:1942-2249`; `modal_app.py:10118+`; `clip_conditioning_cache.py:999+`.
- Scheduler/identity: `contracts.py:1278-1398`; `registry_proof.py`; `registry_proof_store.py:85-329`; `tools/v2_control/{config,profiles,fingerprints,backend,validation}.py`.
- Measurement: `critical_path_ledger.py:300-457,720-867`; `experiment_result_store.py:419-571`; E37 raw artifact `v2_2026-08-21_22-35-45/run_0.json:18736-18770`.
- Historical comparison: `E36_FULL_CRITICAL_PATH_REPORT.md`; `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md`; `V2_BATCH_E27_FIVE_TARGET_CRITICAL_PATH_FORENSICS.md`; `V2_BATCH_E30_CLIP_QD_IO_IMPLEMENTATION.md`; `V2_BATCH_E31_CLIP_FORWARD_FP32.md`.
