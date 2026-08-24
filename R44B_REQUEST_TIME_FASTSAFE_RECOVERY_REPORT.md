# R44B — First-Class Request-Time FastSafe CLIP + UNET Recovery

Batch: R44B · Owner: R44B · Profile: `r44-request-fastsafe` · Branch: `r42-golden-reconciliation` (existing worktree, no new branch/worktree/commit/push)
Batch start HEAD: `0c59f46e3238f421378e8852ebc548da815b70af` · No Modal deployment, no paid runs (§17).

---

## 1. Exact R43 obstruction (restated from evidence)

R43 Round 1 enabled `CLIP_FAST_HYDRATION=1`, `UNET_FASTSAFETENSORS=1`, `CHECKPOINT_PREWARM=1`, `FAST_COLD_ORCHESTRATION=1` with Golden off — and neither FastSafe transport ran. Verified root causes:

1. Snapshots are static **metadata-only** (`stored_snapshot_model_order=null`) → no model objects survive restore.
2. The CLIP demand wrapper requires a **frozen manifest attached to the CLIP object** (`cfh.get_clip_manifest(clip)`), historically created only during snapshot capture/preparation (`maybe_install_clip_fh_demand` is installed from startup/restore after capture; without a frozen manifest it is not installed at all).
3. `V2LoaderBridge` node wrappers are active for all v2 graph executions but return `_LOADER_MISS` silently without Golden context / `RestorePreparation` (`prepare()` requires a restore plan + model key; `_require_active()` raises otherwise).
4. `_load_unet`'s FastSafe pipeline is reachable only via coordinator demand of a prepared future (`ModelPreloadCoordinator.prepare()` → `RestorePreparation.unet_future` → `wait_unet()`); with no preparation there is no future, owner registration, or payload.

## 2. Exact old seams that caused the coupling

| Seam | File:line | Coupling |
|---|---|---|
| CLIP manifest gate | `clip_fast_hydration_wiring.py:2846-2866` (`_hydrate_clip_on_demand`: `manifest = cfh.get_clip_manifest(clip)`; `if manifest is None or not manifest.get("eligible")` → `no_manifest` → native) | Manifest only exists when capture ran with model objects present |
| CLIP wrapper install | `clip_fast_hydration_wiring.py:3032+` (`maybe_install_clip_fh_demand(cpu_models)` — "Called from startup (after capture) and restore"; "Without a frozen manifest the wrapper is NOT installed") | Demand hook never installed on metadata-only snapshots |
| Bridge miss | `model_preload.py:12638-12650` (`_ACTIVE_V2_LOADER_BRIDGE`, `_LOADER_MISS`), `12652-12657` ("A matching prepared result is returned; every mismatch… falls through"), `12752+` (`prepare(plan)` requires restore plan) | Node wrappers need Golden/RestorePreparation to return anything but MISS |
| UNET prepared future | `model_preload.py:12068-12309` (`RestorePreparation`, coordinator `prepare/wait_*`), fastsafe branch `~14694-14760` reached only through that chain | FastSafe selection is restore/coordinator-driven, not request-demand-driven |

## 3. New request-time architecture

```text
snapshot restore (untouched)
    ▼
request accepted → run_plan_stream (modal_app.py)
    ▼
REQUEST FAST-PATH CONTEXT CREATED  (request_fastpath.begin, after E40 loader-selection reset)
    ├── header-only immutable descriptors (path + stat + safetensors header; NO value reads, NO SHA)
    ▼
CLIPLoader.load_clip wrapper (request_clip_fastsafe)
    ├── claim single-flight latch → descriptor (fresh() stat check)
    ├── FastSafe DIRECT CUDA  T8 / B256 MiB / bbuf512 (wiring._fastsafe_load, env-tuned)
    ├── SINGLE-PHYSICAL-READ construction: guarded comfy.utils.load_torch_file override serves
    │   the CUDA dict for exactly our resolved paths → ORIGINAL node method builds CLIP natively
    ├── owner attach (cfh.owner_attach(loader, fb)) + hydration marker + bind-mode proof
    ▼
CLIPTextEncode.encode wrapper marks forward start/end (independent CLIP-forward telemetry;
    forward-start arms UNET source prep; forward-end fires the release event)
    │                              ┌── UNET source prep (CheckpointPrewarmer, CPU/page-cache only,
    │                              │    posix_fadvise + bounded readinto) overlaps CLIP forward
    ▼                              ▼
CLIP GPU critical done  →  UNETLoader.load_unet wrapper (request_unet_fastsafe)
    ├── join source prep (bounded fence) BEFORE any GPU gate
    ├── begin_unet_gpu_phase (D15 race arbiter; on unet_gpu_during_clip_critical → wait event → retry once)
    ├── unet_transfer_start → _fs_fastsafe_load (T8/B256MiB/bbuf512 direct CUDA) → unet_transfer_end
    ├── CURRENT R42 native-parity detection (_native_detection_input: convert_old_quants parity,
    │   prefix strip only-if-non-empty, bare-key ZImage preserved, model_config_none fails closed)
    ├── cheap skeleton/patcher → load_model_weights(assign=True) → same-storage data_ptr identity
    ├── owner retained (_FastsafeOwner on patcher) → _fs_validate_final demand verification
    ▼
sampling
```

No requirement on: weight-resident snapshots, Golden QD, `GoldenRunContext`, restore-time `RestorePreparation`, speculative restore workers.

## 4. Files / functions changed

| File | Change |
|---|---|
| `comfymodal_runtime/request_fastpath.py` | NEW (570→~600 lines): `FastPathRequestContext`, `begin/current/teardown`, frozen `ModelFileDescriptor`, `build_descriptor` (header-only, LRU-cached by `(normcase abspath, size, mtime_ns)`), single-flight `claim_physical_load`, lifecycle states, sticky terminal reasons, source-prep arm/join, adaptive telemetry (snapshot-suppressed on TeardownDiagnostics-style sinks) |
| `comfymodal_runtime/request_clip_fastsafe.py` | NEW (~560 lines): `install_request_clip_fastsafe` wrapping `CLIPLoader.load_clip`, `DualCLIPLoader.load_clip`, `CLIPTextEncode.encode`; producer `_produce_clip_fastsafe`; fail-closed `_fail_closed`; `uninstall_for_tests` |
| `comfymodal_runtime/request_unet_fastsafe.py` | NEW (~762 lines): `install_request_unet_fastsafe` wrapping `UNETLoader.load_unet`; ordering-safe producer (after-clip / race-retry / unet-first-serial); D15 gate usage; R42 adoption composition; `uninstall_for_tests` |
| `comfymodal_runtime/gpu_lane_coordination.py` | ADDITIVE ONLY, +36/−0: `register_clip_critical_end_callback(cb)` + `_fire_clip_critical_end_callbacks()` invoked at the end of `end_clip_critical()` after state release + `record_clip_ready()`; per-callback guarded; behavior unchanged when nothing registered |
| `comfymodal_runtime/modal_app.py` | TWO minimal hunks in `run_plan_stream`: (a) after `_remote_watcher.start()`: `_r44b_ctx = None; try: … if _r44b_fp.enabled(): _r44b_ctx = _r44b_fp.begin(request_id=request_id, trace=diagnostics)` + both installer calls (each try/except-passed); (b) in the matching `finally` after `_remote_watcher.stop_and_join()`: guarded `_r44b_fp2.teardown(_r44b_ctx)`. Local imports only; top-of-file import block untouched; zero hunks in restore/generation regions |
| `comfymodal_runtime/config_authority.py` | Four new registered env keys (`COMFYMODAL_V2_REQUEST_FASTSAFE`, `_REQUEST_CLIP_FASTSAFE`, `_REQUEST_UNET_FASTSAFE`, `_REQUEST_UNET_SOURCE_PREP`, all default "0", LOADER_SELECTION group); `requested_loader()`: Golden branch untouched, then master+role compound resolution returns CLIP `"fastsafetensors_direct_gpu"` / UNET `"fastsafetensors"` BEFORE the residency-first snapshot arms; VAE untouched |
| `config/v2/profiles/r44-request-fastsafe.toml` | NEW: derived verbatim from `r43-known-fast.toml`; `[workload]` byte-identical (forced_miss, sha `20b10e1f…`, run_count 1, gap 35.0); keeps all ten R43 zeros (Golden off, QD reader off, old restore-side fast machinery off) and adds the four REQUEST_* flags = "1" plus `CLIP_FASTSAFE_THREADS="8"`, `CLIP_FASTSAFE_BLOCK_BYTES="268435456"` (B256 MiB), `CLIP_FASTSAFE_BBUF_KB="524288"` (bbuf512) |
| `tests/test_r44b_request_fastsafe.py` | NEW: narrow reachability harness (23 tests) |

Not touched: `runtime_generation.py`, `runtime_bootstrap.py`, restore modules, snapshot composition, CPU/memory/GPU/region/scaledown, VAE path, workload/prompt/steps/sampler/Sage/CacheDiT/conditioning/output.

## 5. Request context lifecycle

`begin(request_id, trace)` sets a ContextVar (pattern of `_ACTIVE_REQUEST_TRACE`) → descriptors built lazily per role (header-only; process LRU keyed by path+stat so repeated requests skip re-parse) → role latches claimed once per context (duplicate-load prevention) → states advance `idle→loading→ready→forwarding→critical_done` (CLIP) and `idle→loading→adopted/failed/fallback` (UNET) → terminal reasons append-only/sticky → `teardown(ctx)` in the request-owner `finally` resets the ContextVar, bounded-joins any armed prewarm, emits `request_fastpath_end` summary. Fully exception-safe; any setup failure merely disables the lane for that request.

## 6. CLIP manifest construction (replaces the frozen manifest)

`build_descriptor(role, path, target_device)` reads ONLY the safetensors header (`safe_open(framework="pt")` → `get_slice(k).get_shape()/get_dtype()` + file metadata): keys/shapes/dtypes/metadata + `size_bytes`/`mtime_ns`. `fresh()` re-stats size+mtime as the cheap freshness detector. No value reads, no full-file SHA, no CPU materialization, no folder scans (single targeted `folder_paths.get_full_path("text_encoders", name)` per name, mirroring the node's own resolution). This is the request-time equivalent of the historical frozen manifest's verification data; bind-time verification still compares actual loaded tensors against the descriptor.

## 7. CLIP FastSafe call path

Wrapper (active only when ctx present + `clip_enabled()`) → latch → descriptor → `wiring._fastsafe_load(path)` per file (the E28 sequence verbatim: `SafeTensorsFileLoader(None,"cuda:N",max_threads=8,bbuf_size_kb=512*1024,nogds=True,disable_cache=True)` → `add_filenames({0:[path]})` → `copy_files_to_device(use_buf_register=False,max_copy_block_size=256MiB)` → `get_keys()` → `fb.get_tensor(k)`) → **single-read seam**: `comfy.utils.load_torch_file` overridden (normcase/abspath-matched, reentrancy-guarded, identity-restored in `finally`) to serve our CUDA dict + header metadata for exactly our paths → ORIGINAL node method runs → comfy natively detects architecture/tokenizer and constructs CLIP from the served tensors. Exactly one physical checkpoint value load; no whole-checkpoint CPU state dict; no CPU→GPU migration afterward.

## 8. CLIP owner/bind path

On success: `cfh.owner_attach(clip, loader, fb)` per file (the same mechanism `_try_fast_hydrate`'s success path uses, constructing `_FastsafeOwner`) so file buffers stay alive while tensor views require them; `cfh.mark_clip_hydrated` + MODE_FASTSAFE recording; provenance attr `clip._comfymodal_r44b_request_fastsafe`; honest bind proof via sampled `data_ptr()` equality → `bind_mode = "same_storage" | "copy_cuda"` recorded in telemetry (either way the physical transport was FastSafe single-read into CUDA). Failure: guarded `loader.close()` on all owners, partial-owner detach, `empty_cache`, sticky terminal reason, terminal-sticky `record_observed(native_comfy, fallback_attempted=True)`, then original method so the request succeeds natively. Never partial-publish.

## 9. UNET source-prep path

Armed at CLIP-forward start (and self-armed idempotently at UNET wrapper entry if CLIP has not started): `ctx.arm_unet_source_prep([path])` lazily constructs `CheckpointPrewarmer` (honoring `COMFYMODAL_V2_CHECKPOINT_PREWARM_THREADS/_CHUNK_MB` envs without requiring its global flag) and `.start(paths)` — daemon threads, bounded `readinto`, optional `posix_fadvise(WILLNEED)`. CPU/storage/page-cache only. Joined at demand via `join_unet_source_prep(timeout_s=30)` (`before_demand_load()` → `stop_and_join_before_demand()`), strictly BEFORE any GPU gate acquisition. Ownership fully request-scoped; `RestorePreparation` not involved.

## 10. UNET FastSafe call path + D15 proof

Ordering-safe by construction (sequential graph executor):
- **After clip**: forward-done event set → join prep → GPU phase inline.
- **Race**: `begin_unet_gpu_phase` raising `RuntimeError("unet_gpu_during_clip_critical")` is the arbiter → bounded wait on `clip_forward_done_event` → retry once (test-proven: gate call count == 2).
- **UNET-first serial**: clip not yet reached → GPU phase runs immediately (gate free — D15 safe); overlap sacrificed for deadlock-freedom; ordering recorded in telemetry.

GPU phase: `begin_unet_gpu_phase` → `unet_transfer_start(token, reason="request_fastsafe")` → `_fs_fastsafe_load(path, device, metrics)` (E28 T8/B256MiB/bbuf512/nogds verbatim) → `unet_transfer_end`/`end_unet_gpu_phase` in `finally`.

**D15 structural proof**: the gate is acquired only around the GPU-committing transfer. File read, page-cache prep, prep-join, and metadata parsing all occur BEFORE `begin_unet_gpu_phase` (test asserts order log `prep_join < gate_begin < transfer_start < fastsafe_load < adopt`). Holding-across-read is impossible: the read happens inside the gate window but the gate is never held across CLIP's critical section because the guard raises on overlap, and the CLIP critical holder releases via `end_clip_critical()` which now also fires the registered release callbacks. The E28 bug (gate held across cold read → CLIP waited ~11.6 s) cannot recur: nothing in the request-time path holds the gate outside the transfer window.

## 11. Current R42 adoption reuse

The adoption sequence of `_make_golden_load_diffusion_model_wrapper` is hard-coupled to the Golden ctx inside its wrapper body, so Lane C composes the identical proven sequence from its innermost reusable module-level pieces: `model_preload._native_detection_input` (convert_old_quants parity, prefix detection, strip-only-if-non-empty bare-key ZImage 453-key behavior, `model_config_none` fails closed) + `_c6_parse_safetensors_header/_c6_safetensors_dtype_map/_c6_comfy_fn` → cheap skeleton → `CoreModelPatcher` → `load_model_weights(dict(views), "", assign=True)` → diffusion-level bind validation → `_storage_identity_counts` (measured same-storage matched/total) → owner retention via `unet_fastsafetensors._FastsafeOwner` + `_FS_OWNER_ATTR` → `_fs_validate_final` demand verification. No new constructor was invented; no old slow constructor reintroduced.

## 12. Fallback semantics

Nominal: CLIP FastSafe direct-GPU; UNET FastSafe direct-GPU + R42 adoption. No QD→staged→pinned→meta→FastSafe→native chain exists in the new path. Any nominal-path failure records the exact terminal reason (`record_terminal`, sticky), records `record_observed(<native arm>, fallback_attempted=True, fallback_reason=…)`, emits `<role>_fastsafe_fallback` telemetry, and falls back ONCE to the original native loader (production-safe). Ineligibility (`_fs_eligible` False) is recorded as terminal `unet_fastsafe_ineligible:<reason>` WITHOUT fallback poisoning (ineligible ≠ fallback, mirroring `_fs_try_pipeline` semantics). Benchmark/profile truth therefore always exposes what physically ran.

## 13. Loader authority semantics

Requested: `requested_loader()` returns `fastsafetensors_direct_gpu` (CLIP) / `fastsafetensors` (UNET) when the R44B flags resolve on (Golden still wins if ever enabled). Observed: `record_observed("clip","fastsafetensors_direct_gpu")` / `record_observed("unet","fastsafetensors")` fire ONLY after physical success (owner attach / adoption respectively). Fallbacks record the normalized native arms (`native_comfy`) with `fallback_attempted=True` — terminal/sticky per existing `loader_selection` semantics. RuntimeStatus stays fail-closed: any fallback or unobserved requested arm yields DEGRADED via the existing machinery; nominal is claimed only when requested == effective == observed on the FastSafe arms.

## 14. Local reachability proof (no Modal, no paid requests)

`tests/test_r44b_request_fastsafe.py` — **23 passed, 0 failed, 0 xfailed** (verified twice: lane run + orchestrator re-run on final tree); regression suites `test_v2_waterfall.py` + `test_v2_waterfall_contract.py` — **68 passed**; `py_compile` clean on all touched modules; profile TOML parses (`tomllib`).

Coverage: context lifecycle + single-flight latches + sticky terminals + JSON-safe summary; real-safetensors header-only descriptor build + mtime freshness + LRU cache; **CLIP reachability**: one physical read, served-dict seam engaged (fake native reader never ran), payload reached binding, `record_observed("clip","fastsafetensors_direct_gpu")`, zero Golden/model_preload imports; negative descriptor failure → native fallback + terminal reason + owners closed; encode wrapper forward-window marking incl. exception path; **UNET reachability**: after-clip ordering with prep-join-before-gate order log, D15 race retry-once, unet-first serial inline, ineligible fall-through without fallback poisoning; clip-critical-end callback hook semantics; telemetry snapshot suppression. Five defects found by the test lane were fixed and re-proven (installer ValueError blocker; missing fallback observation on descriptor-unavailable; `set_descriptor` arity; `wall_ms` key mismatch; telemetry snapshot cost).

## 15. Telemetry added (low-overhead)

`request_fastpath_begin/end` (+summary); `clip_fast_load_start/end` (file_to_gpu_wall_ms, total wall, bind ms, tensor_count, source_bytes, device, bind_mode, CUDA alloc delta, owner_retained, clip_device_ready); `clip_forward_start/end` (wall_ms, allocated/reserved delta over forward, model_sized_migration_detected field); `clip_fastsafe_fallback`; `unet_fastsafe_pipeline` (status, phase="request", file_to_gpu_wall_ms, prepare_join_ms, adopt_ms, storage_identity_matched/total, owner_retained, ordering); `unet_fastsafe_fallback`; `unet_request_ordering`. Existing spans reused where present (`clip_loader_start/device_ready` endpoints via wiring; ledger CLIP-hydration span; `clip_forward_forensics` boundaries remain active). All emissions are exception-guarded; TeardownDiagnostics-style sinks get `snapshot=False` (no per-event process snapshots); no CPU sampling or full tracing added.

## 16. Shared-file conflicts with R44A

None observed. R44A owns `runtime_generation.py` / generation-state files — untouched by R44B. R44B touched `modal_app.py` (two request-lifecycle hunks only; file already carried pre-existing dirty state from R42/R43 — preserved byte-for-byte outside my hunks) and `gpu_lane_coordination.py` (+36/−0 pure insertion). R44A's landed artifacts (`R44A_RUNTIME_GENERATION_DETERMINISM_REPORT.md`, `tests/test_r44a_generation_determinism.py`) do not intersect R44B files. Integration agent should reconcile both `modal_app.py` hunk sets if R44A also edits it.

## 17. Deployment statement

**No Modal deployment occurred. No Modal request was executed. No paid spend.** All verification is local/static (pytest + py_compile + TOML parse + import audits).

## 18. Explicit answers

| Question | Answer |
|---|---|
| Can CLIP FastSafe engage with Golden disabled? | **YES** — engagement requires only the request context + flags; Golden imports absent (test-audited) |
| Can it engage with no RestorePreparation? | **YES** — no RestorePreparation/coordinator usage anywhere in the new path |
| Can it engage with metadata-only snapshot composition? | **YES** — descriptors are built from path+stat+header at request time; no snapshot objects needed |
| Is CLIP direct CUDA? | **YES** — `_fastsafe_load` targets `cuda:N`; device recorded in telemetry |
| Is whole-checkpoint CPU materialization absent? | **YES** — values go file→CUDA only; construction consumes the served CUDA dict |
| Is second model-sized H2D prevented after success? | **YES** — node output replaced; native loader never runs; params already on target device |
| Can UNET source prep start during CLIP forward without GPU ownership? | **YES** — CheckpointPrewarmer is CPU-only and armed at forward start; order-log test proves prep precedes any gate |
| Can UNET FastSafe engage after CLIP critical without RestorePreparation? | **YES** — gated on the forward-done event / guard-arbiter, not on preparation state |
| Does UNET still use current R42 453/453 zero-copy adoption? | **YES** — same detection + assign=True + same-storage identity + owner retention + verification sequence |
| Is native reread prevented after successful FastSafe? | **YES** — single-flight latch + replaced node output; duplicate claim test-proven |
| Is fallback visible/terminal rather than silently nominal? | **YES** — sticky terminal reasons + terminal-sticky observed records + DEGRADED via existing machinery |
| Are CLIP load and CLIP forward independently measurable? | **YES** — dedicated `clip_fast_load_*` and `clip_forward_*` spans on the new path |
| Exact profile/settings the integration agent deploys? | `python tools/v2ctl.py deploy --profile r44-request-fastsafe --owner R44B` — r43 base + `COMFYMODAL_V2_REQUEST_FASTSAFE/CLIP/UNet/SOURCE_PREP="1"`, `CLIP_FASTSAFE_THREADS="8"`, `CLIP_FASTSAFE_BLOCK_BYTES="268435456"`, `CLIP_FASTSAFE_BBUF_KB="524288"`; all R43 zeros kept; workload byte-identical |
| What remains UNPROVEN until the one real cold gate? | Actual Modal walls (CLIP file→GPU vs ~491 ms class; UNET vs ~477 ms class; source-prep overlap benefit; end-to-end wall vs 26.4 s R43 mean); whether comfy binds served CUDA storages same-storage vs copy (`bind_mode` will tell); whether graph node ordering hits the after-clip (overlap) or unet-first (serial) case on the real workflow; `_fs_eligible` capability outcome on the real ZImage checkpoint; remote telemetry visibility through the diagnostics sink; RuntimeStatus NOMINAL end-to-end |

## 19. Final flags

```
R44B_REQUEST_CONTEXT_IMPLEMENTED = YES
R44B_CLIP_FASTSAFE_REQUEST_REACHABLE = YES
R44B_UNET_FASTSAFE_REQUEST_REACHABLE = YES
R44B_RESTOREPREPARATION_DEPENDENCY_REMOVED = YES
R44B_GOLDEN_DEPENDENCY_REMOVED = YES
R44B_R42_UNET_ADOPTION_PRESERVED = YES
R44B_D15_SCHEDULING_PRESERVED = YES
R44B_REMOTE_VALIDATION_NEEDED = YES
R44B_READY_FOR_INTEGRATION = YES
```
