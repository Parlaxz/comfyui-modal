# V2 Batch D6 — CLIP Restore-Lifecycle Root Cause (Find the First Re-Materialization)

- **Date:** 2026-08-16
- **Branch:** current main only · no branch · no worktree · **commit: none**
- **C4:** untouched (not executed)
- **Modal deploys = 0 · Modal requests = 0** (this batch is local-only)
- **Evidence base:** corrected D6 run `v2-benchmark-0-06813ab11164` artifacts
  (`comfymodal-data/benchmarks/runs/v2_2026-08-16_03-11-06/run_0.json`, 513 trace
  events), deploy log `d6_deploy3.log` (eviction_enabled=1, eviction_role=clip_vae),
  run log `d6_run4.log`, plus a full read of the current tree (three read-only
  audit lanes + first-hand artifact mining; no agent report was taken as
  authoritative).

---

## 0. Executive answer

> **CLIP first materialization point = the capture-phase eviction fresh
> reload — `modal_app.py:6718-6724` (native `_cpu_load_clip` reload) →
> `modal_app.py:6778` (`_container_retained.clip = _reloaded_model`) — which
> runs AFTER the D3 strip (trace event 54: `clip_fh_capture status=excluded
> params_replaced=399 payload_bytes_removed=8,044,936,196`) and BEFORE the
> Modal memory-snapshot fork (event 68).**

The 399 / 8.04 GB CPU CLIP parameters were never "re-materialized between
capture exclusion and first encode demand" — they were **freshly reloaded
from the checkpoint file during snapshot capture, by the eviction retain
role, after the exclusion had already stripped the original object**. The
fork then serialized the full-weight object, and restore served it natively.

---

## 1. The exact mechanism (proven, ordered)

| # | Step | File:line / trace event | Effect on CLIP |
|---|------|--------------------------|----------------|
| 1 | Deploy pins eviction retain role | `deploy_and_run_v2_single.bat:61-63` — `EVICT_MODELS_BEFORE_SNAPSHOT=1`, `EVICT_RETAIN_ROLE=clip_vae`; deploy log `eviction_enabled=1 eviction_role=clip_vae` | — |
| 2 | Native CLIP load into snapshot container | trace 39-42 `cpu_snapshot_clip_load_start/end` (3059 ms) → `_cpu_snapshot_models.clip` | Full 399-param CPU CLIP (8.04 GB) |
| 3 | **D3 exclusion** | trace 54 `clip_fh_capture status=excluded`; `maybe_prepare_clip_snapshot_exclusion` → `strip_clip_weights` (`clip_fast_hydration.py:855-883`) | All 399 params replaced with meta; frozen manifest + excluded marker attached to THIS object |
| 4 | **D3 demand wrapper** | trace 55 `clip_fh_install status=installed`; `maybe_install_clip_fh_demand` (`modal_app.py:8901`) | Wrapper installed on the STRIPPED object |
| 5 | Snapshot pools closed | trace 60 `snapshot_pools_closed` | — |
| 6 | **EVICTION FRESH RELOAD (FIRST RE-MATERIALIZATION)** | trace 61-62 `v2_startup_clip_snapshot_load_start/end` (1548 ms); `_evict_snapshot_models` nulls `cpu_models.clip` (`modal_app.py:6469-6470`, stripped object discarded) then `reload_clip_fn(_clip_name, _clip_type_str, "default")` (`6718-6724`) → `_container_retained.clip = _reloaded_model` (`6778`) | **Fresh full-weight 399-param CPU CLIP — NO manifest, NO wrapper** |
| 7 | Modal memory snapshot fork | `enable_memory_snapshot=True` (`comfyapp.py:24291`); fork after `startup()` return (event 68) | Serializes the FULL 8.04 GB object (the excluded object is gone) |
| 8 | Restore + request-time bind | trace 204 `cpu_snapshot_models_retargeted stage=request_time_clip_vae_only unet_present=0`; 225-226 `cpu_snapshot_clip_vae_bind clip_source=cpu_snapshot cpu_snapshot_clip_reused=1` | Serves the full-weight object |
| 9 | First patcher-load boundary | trace 305-307 `clip_cold_detach` / `clip_cold_patcher_partial_load_start/end` patcher `46955215872272`, `device_distribution={cpu:399}`, `loaded_mem_bytes=8,044,936,196` | Observed state |
| 10 | Encode | trace 313/361 `clip_cold_forward` 5278 ms; `encode_calls=1`; cache `miss_stored` | Native path, exact output SHA |

**Root cause (one sentence):** the canonical launcher's eviction retain-role
experiment (`clip_vae`) discards the D3-excluded CLIP and reloads a fresh
full-weight CLIP into the snapshot container AFTER the strip and BEFORE the
fork, so the snapshot carries the full 8.04 GB object and restore serves it
with no manifest and no demand wrapper — the D3 fast path never engages.

---

## 2. Capture exclusion physically effective locally — YES (proven)

- `strip_clip_weights` performs **in-place `setattr`** of every parameter on
  its owning submodule with a new `meta` tensor (`clip_fast_hydration.py:871-876`);
  the old `Parameter` refcount drops and the storage is freed when no alias
  exists. `patcher.model is cond_stage_model` (comfy/sd.py), so the patcher
  observes the same stripped module.
- Empirical (synthetic, no comfy import, 34-param and 30-param fixtures):
  after strip, `gc` sweep found **0 live tensors on the original storages**;
  `patch_weight_to_device`/`ModelPatcher.load` on CPU→CPU make no copies.
- `payload_bytes_removed` is a **logical** pre-computed sum
  (`numel×element_size`, `clip_fast_hydration.py:870`) — it does not itself
  prove physical freedom, but the storage-identity scan does.
- New regression test: `TestCaptureExclusionFlow.test_exclusion_frees_original_storages`.

## 3. Storage aliases remaining after exclusion — NONE in the capture path

Per-owner audit (exp-2, all verified against current code):

| Owner | Verdict |
|---|---|
| CLIP instance / cond_stage_model submodules | FREE (single object, stripped in place) |
| ModelPatcher (backup/patches/pinned) | FREE (empty at capture; same module identity) |
| `current_loaded_models` | FREE (weakrefs only) |
| `cached_patcher_init` args | FREE (paths only, not tensors) |
| `CpuSnapshotModels` container / storage registries | FREE (same object; registry stores int addresses) |
| Preload bridge | FREE at capture |
| state_dict temporaries in `comfy.sd.load_clip` | FREE (transient locals, not retained) |
| **Eviction re-reload path (THE bug)** | **RETAINS — by design**: fresh full-weight reload at `modal_app.py:6718-6724 → 6778` |

The D6 observation was **not** a retained alias of the original storages — it
was a **second, independent full load** created by the eviction path.

## 4. Restore state immediately before demand

`CPU_NATIVE_MATERIALIZED` — the fresh full-weight object (399 CPU params,
8.04 GB), `get_clip_manifest(clip) is None`, demand wrapper absent. The
restore-site install (`modal_app.py:9434-9440`) returned `no_manifest`
(restore-time events would in any case have been dropped — see §6).

## 5. Why `clip_fh_hydration_start/end` were absent

Object-state driven, not a telemetry bug:
1. The demand wrapper existed only on the **discarded** stripped object
   (install at event 55; discard at step 6).
2. The served object had **no manifest** → even if a hydrator had existed,
   `_hydrate_clip_on_demand` branch D1 (`no_manifest`) records silently and
   returns — native path.
3. The `already_hydrated` predicate was **NOT** the cause (see §6).

## 6. `already_hydrated` predicate result — NOT the cause, but hardened

- `clip_hydrated()` is **marker-only** (`_comfymodal_clip_fh_hydrated`
  instance attr, set only by `mark_clip_hydrated()` in the three hydration
  paths). A full-CPU model does NOT satisfy it — CPU residency alone can
  never silently classify as hydrated. Proven by
  `test_cpu_materialized_before_demand_is_never_called_already_fast_hydrated`.
- Per the task, the ambiguous "already_hydrated" condition is now replaced by
  an explicit taxonomy: `STATE_EXCLUDED_PLACEHOLDER`,
  `STATE_CPU_NATIVE_MATERIALIZED`, `STATE_GPU_FAST_HYDRATED`,
  `STATE_GPU_NATIVE_LOADED`, `STATE_INVALID` + `clip_hydration_state(clip)`
  (pure, JSON-safe, never raises), and `clip_fh_hydration_decision` events on
  EVERY demand branch with `state_before`/`state_after` — the future
  telemetry distinguishes `already_gpu_fast_hydrated` /
  `already_gpu_native_resident` / `cpu_materialized_requires_hydration` /
  `excluded_requires_hydration`.

## 7. Wrapper-install ordering — the bug, and the fix

- Capture install (event 55) ran BEFORE the eviction reload (events 61-62),
  so the wrapper was lost with the discarded object. Not "too late" — **on
  the wrong object's lifetime**.
- **Fix (F-A):** `_evict_snapshot_models` now freezes the frozen manifest
  (deepcopy) before nulling the clip, and in the `clip_vae` retain block
  **re-applies attach-manifest → strip → install-demand-wrapper on the
  reloaded CLIP BEFORE the snapshot fork**, threading the startup trace into
  the wrapper closure so demand events land in the persisted lifecycle trace.
  Emits `clip_fh_eviction_reconcile status=excluded_after_eviction_reload`.

## 8. Trace routing — one real hole, now fixed

- Startup `clip_fh_*` events ride the startup trace → `_lifecycle_trace` →
  merged into the artifact (`modal_app.py:17216-17261`); no host-side event
  filtering; `RuntimeTrace` has no bounded-event truncation. The startup
  `clip_fh_capture`/`clip_fh_install` events ARE visible in the artifact —
  proving the routing works when the trace is real.
- **Hole:** the restore-site install passed `trace=getattr(self, "_trace",
  None)` — `self._trace` is never assigned anywhere in `modal_app.py`, so
  every event from a restore-installed hydrator was dropped by the wiring
  `_emit` None-guard. **Fixed:** now `self._lifecycle_trace`.
- Verdict: telemetry loss alone could not explain the observation; the
  object-state evidence (full CPU object served with no wrapper) does.

## 9. Snapshot mechanism (Task 5)

- The deployment uses **Modal Memory Snapshot** (`enable_memory_snapshot=True`,
  fork-based whole-process capture after `startup()` returns) — NOT
  cloudpickle. Any object live in the address space at the fork is serialized;
  the exclusion only helps if no other reference holds the payload.
- Local tests use cloudpickle/pickle for object round-trip simulation —
  that is a **different mechanism** (explicitly documented; only
  serialization-correctness and object-graph correctness are proven locally;
  Modal snapshot semantics remain remote-only, now observable via the 14
  `clip_state_checkpoint` sites).

## 10. Fixes landed (all default-OFF, fail-closed, generic capability-based)

| Lane | Files | Change |
|---|---|---|
| F-A | `comfymodal_runtime/modal_app.py` | Eviction×D3 reconcile: manifest freeze (deepcopy) before eviction; re-apply attach+strip+demand-wrapper to the reloaded clip pre-fork; post-strip storage-registry recompute; `clip_fh_eviction_reconcile` event; startup trace threaded into `_evict_snapshot_models`; restore-install trace hole fixed (`_lifecycle_trace`) |
| F-B | `comfymodal_runtime/clip_fast_hydration.py`, `clip_fast_hydration_wiring.py` | Explicit hydration-state taxonomy + `clip_hydration_state()`; `clip_fh_hydration_decision` on every demand branch; `clip_state_checkpoint` helper (default-OFF); summary carries state; `clip_hydrated()` semantics unchanged and documented |
| F-C | `modal_app.py`, `model_preload.py`, `clip_cold_path_forensics.py` | 8 restore-side `clip_state_checkpoint` sites: `capture_pre_snapshot_return`, `restore_first_instruction`, `restore_after_retained_model_handling`, `restore_after_gpu_state`, `restore_after_snapshot_model_validation`, `restore_after_cpu_snapshot_bridge`, `conditioning_prefetch_worker_start`, `modelpatcher_load_entry` (14 sites total incl. wiring-side) |
| F-D | `tests/test_v2_clip_restore_lifecycle.py` (new) | 16 tests reproducing the real lifecycle: capture→exclusion (storages freed), eviction-reload bug fixture, reconcile fix flow, cache MISS one-hydration, cache HIT zero-hydration, CPU-materialized never already-hydrated, encode parity, fail-closed, fallback exactly once, summary states |

## 11. Task 11 — full affected matrix (sequential)

| Batch | Command | Result |
|---|---|---|
| 1 | clip_cold_forensics + clip_fast_hydration_production + phase_d_telemetry_integration + clip_hydration_states + clip_eviction_reconcile + clip_restore_lifecycle | **118 OK (2 skips)** |
| 2 | cpu_snapshot_lifecycle + cpu_snapshot_models + snapshot_restore_only + preload_bridge | **450 OK** |
| 3 | d1_dispatch_hash + batch_d1_registry_proof_store + batch_d1_local_dispatch + plan_validation_proof + deployment_proof + conditioning_cache_nonce + d6_deploy_profile + unique_prompt_suffix | **106 OK** |
| 4 | runtime_playground_v2 + local_submission_timing + local_pre_submit_optimization + final_observability + host_submission_breakdown | **251 OK** |
| — | py_compile (71 files) | OK |
| — | `_test_clip_fast_hydration.py` harness | **9/9 ALL PASS** |

Total: **925 tests OK + 2 skips, 0 unexplained failures**. The two skips are
`cloudpickle not installed` (environment-gated, pre-existing convention).

## 12. Position on the corrected-run metrics (evidence-discipline corrections)

- **META_LOCATION** = explained: `meta_get_model` ~2979 ms accounts for almost
  all ~2981 ms Worker-A execution; thread CPU 410 ms → effective cores ~0.14;
  non-thread-CPU wall ~2571 ms.
- **META_ROOT_CAUSE** = still unresolved: `wall − thread_time` is NOT proof of
  scheduler wait and NOT proof native model construction ran elsewhere — it
  may contain blocking, descheduling, native child-thread work,
  synchronization, or uncharged wall. The future `INPUT_TYPES_WARM=0` A/B is
  the causal test.
- **INPUT_TYPES_WARM_STATUS** = contention SUPPORTED (3593 ms / 31 classes;
  overlap meta 2974 ms + fastsafe 2875 ms, scope=complete) as *evidence of
  concurrence*, NOT causal proof of contention.

## 13. Next remote validation (definition only — NOT executed)

READY_FOR_ANOTHER_REMOTE_CLIP_VALIDATION = **YES**

One canonical deploy + one true-cold request would validate that the
eviction×D3 reconcile produces the intended lifecycle:

1. Deploy with `V2_D6_FASTPATH_VALIDATION=1` (atomic profile, eviction
   retain role still pinned by the launcher) → expect in the persisted
   lifecycle trace: `clip_fh_eviction_reconcile status=excluded_after_eviction_reload
   wrapper_installed=installed`, `clip_state_checkpoint
   capture_pre_snapshot_return` with `state=EXCLUDED_PLACEHOLDER`
   (0 full CPU checkpoint bytes).
2. One true-cold request, fresh semantic-neutral nonce, `V2_BENCHMARK_RUNS=1`
   → expect: request-time bind `clip_source=cpu_snapshot` serving the
   STRIPPED object; `clip_state_checkpoint` sequence through
   `restore_first_instruction → restore_after_gpu_state →
   restore_after_cpu_snapshot_bridge → clip_load_model_entry →
   clip_hydration_decision`; `decision=fast_path` (or cpu_assign_fallback on
   capability failure) with `state_before=EXCLUDED_PLACEHOLDER`;
   `clip_fh_hydration_start/end` present; D2 patcher boundary shows
   `device_distribution={cuda:399}` and `transfer_ops=0` (no duplicate
   CPU→GPU full transfer); `encode_calls=1`; cache `miss_stored`;
   output SHA EXACT `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`.

Do not execute until authorized.
