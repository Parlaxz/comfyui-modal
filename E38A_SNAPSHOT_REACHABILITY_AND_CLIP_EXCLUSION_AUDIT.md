# E38A — Snapshot Reachability, CLIP Weight Exclusion, and Lean-Snapshot Preflight Audit

> **SUPERSESSION NOTICE (2026-08-30):** Historical audit; preserve its
> evidence, but use `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md` for current
> generated-output guidance. Output durability is off by default; strict
> commit/reopen/hash proof is opt-in. S4 source publication durability remains
> mandatory.

Date: 2026-08-21
Scope: current local dirty checkout of `comfyui-modal` (E31–E37 uncommitted state authoritative). Read-only audit; no source, test, profile, or deployment changes were made.
Method: 6 parallel read-only forensic lanes (reachability, lifecycle, flag chain, QD4 dependencies, duplication/quiescence/artifacts, official Modal docs) + orchestrator spot-verification of every pivotal citation.
Evidence labels: CONFIRMED / SUPPORTED INFERENCE / HYPOTHESIS / UNKNOWN / UNOBSERVABLE. All file:line references are to the current working tree unless marked otherwise.

---

## 1. Executive verdict

**CONFIRMED:** The E37 CPU memory snapshot retains the **full CLIP weight value payload**, while the authoritative E37 clean-lane algorithm subsequently rereads those same values from storage via synchronous QD4 and binds them into a skeleton. The snapshot copy is dead weight for that algorithm.

The four load-bearing facts:

1. **Full CLIP values are retained at capture.** `self._cpu_snapshot_models` → `CpuSnapshotModels.clip` → Comfy CLIP wrapper → `cond_stage_model` / `clip_l` / `clip_g` / `patcher.model` → `nn.Module` parameters/buffers → tensor storages (`cpu_snapshot_models.py:78-105`, `1203-1231`, `2635-2658`; `modal_app.py:9625`). The E37 profile explicitly runs with exclusion off: `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = "0"` (`config/v2/profiles/e37-clean-lane-qd4.toml:45`). Verified directly.
2. **QD4 does not need those values.** The clean lane synchronously rereads the safetensors header, offsets, names, shapes, dtypes, and all data blocks from source files post-restore (`clip_qd_reader.py:300-384`, `468-489`; `clip_fast_hydration_wiring.py:1319-1364`, verified) and binds assign-style into an existing skeleton whose meta-parameter state is explicitly tolerated (`clip_fast_hydration.py:15-40`, `226-275`; `clip_fp32_cast_once.py:324-337`).
3. **The exclusion control is real, effective, and pre-capture — but it was OFF in E37.** `strip_clip_weights()` replaces every `cond_stage_model` parameter with a same-shape/same-dtype meta Parameter in place, keeps buffers/structure/tokenizer payloads/patcher, sets an exclusion marker, and emits pre/post checkpoints + `payload_bytes_removed` telemetry before the capture boundary (`clip_fast_hydration.py:892-921`; `clip_fast_hydration_wiring.py:745-794`, verified). This is not a half-integration.
4. **Therefore E39's minimal change is a one-flag profile flip, not new code.** The exclusion mechanism already implements exactly the lean representation this audit derives as minimal (Section 11): executable skeleton + frozen manifest + policy, minus weight values.

Residual risk that could contaminate E39: external Comfy model-management roots may independently retain CLIP storages at capture (UNKNOWN — outside this repo), and the fail-closed eligibility gate can silently skip the strip (making a "LEAN" arm identical to CONTROL). Both are addressed as required proof predicates in Section 13.

No performance savings are estimated anywhere in this report, per audit discipline.

---

## 2. Current snapshot lifecycle

Application semantics CONFIRMED from current source; Modal platform semantics are cited separately in Section 10/Appendix A and are not inferred.

### 2.1 Global-scope initialization captured by the snapshot

CONFIRMED import-time state creation (all reachable module globals are part of process state at the capture boundary):

- Modal/app identity, volume config, paths, limits: `modal_app.py:278-314`.
- Container session id, import timestamps, restore counter, startup-return record: `modal_app.py:341-364`.
- Prefetch evidence registry + lock: `modal_app.py:366-386`.
- Validation/profile/cache registries and locks (`_V2_CERT_PROCESS_CACHE`, `_RES4LYF_PREPARED`, `_CACHEDIT_PREPARED`, `_V2_WORKFLOW_HASH`): `modal_app.py:491-515`.
- Full-trace finalized-ID set + lock: `modal_app.py:525-539`.
- `comfyapp.py` registries (`_CUSTOM_NODE_IMPORT_FAILURES`, `_IN_CPU_SNAPSHOT`, retry set, production sink registry/lock, request registry): `comfyapp.py:374-439`.
- Disk-cache dicts/locks/counters, restore/profile caches: `canonical_execution.py:95-145`, `347-455`; disk caches actively loaded during import: `canonical_execution.py:514-519`.
- `model_preload.py` import-time config, Event, locks: `model_preload.py:18-30`, `134-173`. Imports of executor/future/thread primitives do not prove live workers exist at capture: `model_preload.py:28-30`.

### 2.2 Snapshot-phase hooks

CONFIRMED:

- `startup()` is dynamically decorated `_modal.enter(snap=_resolve_enable_memory_snapshot())`: `modal_app.py:20083-20091` (verified directly). A false token flips it to `snap=False` so an A/B deployment can disable snapshots entirely.
- `restore()` is `_modal.enter(snap=False)`: `modal_app.py:20092` (verified).
- Startup begins with `snap_true_enter` markers: `modal_app.py:8861-8868`; bootstrap/identity/validation init: `modal_app.py:8870-8944`.

### 2.3 Pre-snapshot model construction

CONFIRMED:

- CPU snapshot construction gated by `_cpu_model_snapshot_enabled()`: `modal_app.py:9260-9264`; live runtime + snapshot profile loaded: `modal_app.py:9267-9271`; loader callbacks built from `UNETLoader`/`CLIPLoader`/`DualCLIPLoader`/`VAELoader` mappings: `modal_app.py:9309-9319`.
- Construction runs inside `api._force_cpu_during_snapshot()` with `comfy.utils.DISABLE_MMAP=True`, no-fallback: `modal_app.py:9420-9436` (verified directly). DISABLE_MMAP matters for restore safety because mmap-into-volume survival across restore is undocumented (Appendix A §3/§6).
- Startup ALWAYS builds the full CLIP/UNET/VAE snapshot; `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET` is identity/reporting only and never skips construction: comment + code `modal_app.py:9436-9442` (verified).
- Role construction by `load_cpu_snapshot_models()` invoking the three loaders: `cpu_snapshot_models.py:2510-2550`, `2604-2614`. Model order via `COMFYMODAL_V2_SNAPSHOT_MODEL_ORDER`, batch default `O0`: `cpu_snapshot_models.py:2466-2468`; `deploy_and_run_v2_single.bat:177-178`.

### 2.4 CpuSnapshotModels population

CONFIRMED:

- Definition `cpu_snapshot_models.py:78-105`: identity fields (`model_key`, `model_spec`, `normalized_profile`, `file_facts`) plus **full live objects** `unet`, `clip`, `vae`, timings, compute policy, target GPUs, VAE policy, validation metadata, storage registry.
- Population assigns loader return objects directly: `cpu_snapshot_models.py:2607-2614`, container built `2635-2658`; retained on the app object: `modal_app.py:9625`.
- Validation requires non-None objects and valid patcher structures: `cpu_snapshot_models.py:2873-2895`; re-stats files (path/size/mtime): `2821-2871`.
- Filtering nuances: duplicate `clip2 == clip1` excluded from `file_facts` only (`2433-2442`); VAE included only if profile declares one (`2604-2607`); storage-registry diagnostics filter non-CPU/empty/meta/sparse/quantized tensors (`148-158`).

### 2.5 Snapshot manifest construction

CONFIRMED:

- Diagnostic manifest gated by `COMFYMODAL_V2_SNAPSHOT_MANIFEST`, default `"0"`: `modal_app.py:9790-9805`. Stages `"before_capture"` (startup) and `"first_restored_line"` (restore, `modal_app.py:10245-10257`).
- Manifest content: timestamps, status, cgroup, smaps, mappings, modules, threads, children, FDs, Torch threads, retained models, executors, GC state, Modal identity: `snapshot_build_manifest.py:396-418`.
- This manifest is diagnostic; it does not itself carry per-tensor shape/dtype/hash metadata. Model-level facts live in `CpuSnapshotModels.file_facts` (`ModelFileFact.size_bytes` via `os.stat`: `cpu_snapshot_models.py:37-43`, `1102-1114`) and manifests attached to the CLIP object (Section 3).

### 2.6 Capture hygiene

CONFIRMED:

- Optional hygiene after baseline finalization, before startup returns; gated by `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`, default off: `modal_app.py:9819-9853`.
- Hygiene performs `gc.collect()`/`malloc_trim()` immediately before the capture boundary: `snapshot_capture_hygiene.py:1-17`, `136-155`.
- Per-role `gc.collect()` after each model load and after VAE policy validation: `cpu_snapshot_models.py:2551-2555`, `2621-2627`.
- Hygiene does NOT drain model-management owners or workers (Section 10).

### 2.7 Preload/prefill/prewarm before capture

CONFIRMED:

- In the E37 clean-lane profile these are all OFF: `CHECKPOINT_PREWARM=0`, `MODEL_PRELOAD=0`, `PREFILL_LANES="none"`, `EXECUTION_PREFILL=0`, `GRAPH_PRELOAD=0`, `FAST_COLD_ORCHESTRATION=0`, `BACKGROUND_PERSISTENCE=0`, `BACKGROUND_DIAGNOSTICS=0`, `CONDITIONING_CACHE_PREFETCH=0` (`e37-clean-lane-qd4.toml:29,41-54`).
- Checkpoint prewarm elsewhere uses daemon threads with bounded joins and FD closure accounting: `checkpoint_prewarm.py:334-396`, `418-521`; its telemetry claims bytes-read, not residency: `checkpoint_prewarm.py:815-817`.

### 2.8 Persistent executors/threads/futures at capture

CONFIRMED: no application-owned persistent executor is created before the startup return on the inspected path; worker creation is lazy/request/restore-side; the runtime records its executor as non-persistent (`modal_app.py:5807-5810`); the diagnostic manifest can count executors/threads (`snapshot_build_manifest.py:405-411`). Whether any platform/runtime-created threads survive capture is UNKNOWN (Modal docs silent; Appendix A §3).

### 2.9 Exact point Modal is allowed to take the snapshot

CONFIRMED application boundary: return from `startup()`. The code emits `[v2.lifecycle] method=startup snap=True ... status=ready` and returns `status="ready"`: `modal_app.py:9855-9896` (verified directly), preceded by a `capture_pre_snapshot_return` clip-state checkpoint: `modal_app.py:9873-9881`. There is no explicit application capture call; actual capture timing relative to the Python return is platform-controlled and undocumented (Appendix A §2).

### 2.10 First restored Python instruction

CONFIRMED:

- `restore()`'s first instructions capture wall/monotonic timestamps and open the canonical restore ledger with `modal_restore_entry`: `modal_app.py:10118-10151`; restore-early span opens: `10153-10191`.
- First restore marker: `[v2.startup_stage] stage=post_snapshot_restore event=start`: `modal_app.py:10259-10260`.
- Eviction-marker inspection precedes lazy snapshot-state initialization: `modal_app.py:10285-10326`.

### 2.11 Restore-time model reconciliation

CONFIRMED:

- Retained `CpuSnapshotModels` available via `self._cpu_snapshot_models` during restore: `modal_app.py:10245-10256`.
- Retargeting changes patcher device-policy attributes only; it does not transfer weights: `cpu_snapshot_models.py:2960-2969`; validates UNET/CLIP/VAE shapes before assignment and updates load/offload devices: `2986-3037`.
- Full validation list (identity, spec, normalized profile, file facts, object presence, patcher shape, VAE policy, policy version, compute policy, BF16-native requirements): `cpu_snapshot_models.py:2715-2723`, `2733-2957`.
- Snapshot eviction can clear the active reference and retain/reload selected roles: `modal_app.py:6538-6561`, `6938-6955` (inactive in E37: `EVICT_MODELS_BEFORE_SNAPSHOT=0`, profile line 26).

### Lifecycle timeline

| Step | Phase | File:line | State created/consumed |
|---|---|---|---|
| Module imports | cold/snap | `modal_app.py:341-386`; `canonical_execution.py:514-519` | Registries, locks, disk caches |
| startup enters | snap | `modal_app.py:8861-8915` | Thread policy, bootstrap, identity |
| Bootstrap/config | snap | `modal_app.py:8943-9254` | Runtime state, proofs |
| Profile resolved | snap | `modal_app.py:9260-9327` | CLIP/UNET/VAE profile, GPU policy |
| Model construction | snap | `modal_app.py:9420-9471` | Full CLIP+UNET(+VAE) CPU objects |
| Exclusion prep | snap | `modal_app.py:9625-9633`; wiring `745-794` | Manifest attach (+ optional strip) |
| Role validation | snap | `cpu_snapshot_models.py:2660-2684` | Validated CpuSnapshotModels |
| Diagnostic manifest | snap | `modal_app.py:9790-9805` | Process/FD/GC snapshot |
| Optional hygiene | snap | `modal_app.py:9835-9853` | gc/malloc_trim (gated, default off) |
| Capture boundary | snap→capture | `modal_app.py:9855-9896` | Return `status=ready` |
| Restore entry | restore | `modal_app.py:10118-10151` | Timestamps, ledger |
| Lazy snapshot init | restore | `modal_app.py:10285-10326` | Eviction check, state init |
| Reconciliation | restore | `cpu_snapshot_models.py:2960-3039` | Device retargeting only |
| Clean-lane QD4 | restore/demand | wiring `1319-1364` | Sync source read → bind |

---

## 3. Exact CLIP reachability graph

Every root traced to either (A) surviving weight storage or (B) termination without weight data. Citations are current-source.

### Root 1 — `self._cpu_snapshot_models` → `.clip`

**Retains full weight values: YES (default/E37 config). CONFIRMED.**

```
self._cpu_snapshot_models            modal_app.py:9625
  -> CpuSnapshotModels               cpu_snapshot_models.py:78-105 (.clip field)
  -> clip_obj from load_clip(...)    cpu_snapshot_models.py:2482-2484, 2529-2540
  -> assigned into container         cpu_snapshot_models.py:2635-2645
  -> Comfy CLIP wrapper internals:
       cond_stage_model / clip_l / clip_g / patcher.model   cpu_snapshot_models.py:1203-1231
  -> nn.Module named_parameters()/buffers                   cpu_snapshot_models.py:285-296, 351-374
  -> torch.Tensor -> torch.Storage                          => FULL WEIGHT VALUES RETAINED
```

The repo's own resolver explicitly recognizes that weights may live in `cond_stage_model` or `patcher.model` (`cpu_snapshot_models.py:250-261`) and validates patcher device structure (`1266-1272`, invoked `2879-2890`).

### Root 2 — capture-time exclusion path (flag-gated)

**When `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1` AND eligibility passes: chain terminates at meta placeholders. CONFIRMED** (verified directly):

```
maybe_prepare_clip_snapshot_exclusion(cpu_models)        clip_fast_hydration_wiring.py:745-794
  -> builds frozen capability manifest                    :763-774
  -> cfh.attach_clip_manifest(clip, manifest)             :774
  -> strip_clip_weights(clip)                             :777
       every cond_stage_model param -> same-shape/dtype
       torch.empty(..., device="meta") Parameter          clip_fast_hydration.py:907-915
       buffers kept; structure kept                       docstring :896-898
       EXCLUDED_WEIGHTS_MARKER set                        :916
  -> telemetry: capture_pre/post_exclusion checkpoints,
     clip_fh_capture status="excluded",
     params_replaced, payload_bytes_removed               wiring:776-787
```

Invoked during snapshot construction, i.e., BEFORE capture: `modal_app.py:9625-9633`. Fail-closed: missing clip → `no_clip`; manifest build error → `error`; ineligible → `ineligible` with NO strip (`wiring:757-770`).

### Root 3 — `clip.patcher` → `patcher.model`

**Potentially retains values through the same storages (aliasing expected, not separately proven). CONFIRMED path / EXTERNAL DETAIL UNKNOWN.** Resolution reads `patcher.model` as fallback (`cpu_snapshot_models.py:1225-1231`); whether Comfy's `ModelPatcher` aliases or copies module storage cannot be proven from this repo.

### Root 4 — speculative hydration lanes (`_LANES`)

**Not a CPU-snapshot weight owner. CONFIRMED.** Module-global strong dict `speculative_clip_hydration.py:60-64`; lanes hold `per_file_sds` + `owners` (`71-85`) of **GPU** tensors read independently from files (`590-618`, `758-767`, `785-799`, GPU at `78-80`, `791`); demand-time take removes entries (`939-977`); close clears (`980-1031`). Separate storages from the CPU snapshot copy (SUPPORTED INFERENCE: constructed by independent file reads into GPU). In the E37 clean lane the restore-time lane is deliberately empty (`wiring:1319-1324`, verified).

### Root 5 — conditioning cache

**No CLIP weights. CONFIRMED.** Contract stores completed CPU conditioning only (`clip_conditioning_cache.py:1-26`); tensors detached/copied/serialized (`447-462`); pending entries are plain dicts/headers/bytes (`785-795`); mem payloads are header/data structures (`920-935`, `1201-1217`); cap 512 MiB default (`84-87`). Retains embeddings, not parameter storage.

### Root 6 — manifests / forensics / ledgers

**Metadata only. CONFIRMED.** Manifest attachment copies a dict (`clip_fast_hydration.py:1243-1250`); capture deep-copies the manifest with an explicit no-CLIP/no-tensor comment (`modal_app.py:6911-6930`); ledger stores metadata dicts (`critical_path_ledger.py:256-271`, `300-307`); forensics store JSON-safe records/counters/tensor facts, not tensors (`clip_forward_forensics.py:396-475`).

### Root 7 — Comfy model-management lists

**UNKNOWN externally.** This repo only reads `current_loaded_models` / `loaded_models()` counts (`cpu_snapshot_models.py:2492-2505`) and wraps calls for diagnostics (`clip_cold_path_forensics.py:902-949`, `1087-1147`, `1171-1276`). Whether Comfy's own lists retain the snapshot-phase CLIP (and thus a second strong root into the same storages) cannot be proven from this checkout. This is the principal residual reachability unknown for E39 (Sections 13-14).

### Root 8 — tokenizer/config objects

**Structural/config references only; no parameter storage. CONFIRMED.** Specs hold filenames/loader classes/CLIP type/policy (`cpu_snapshot_models.py:1049-1099`); manifests hold paths/sizes/dtype/keys/shapes (`speculative_clip_hydration.py:128-149`, `187-217`); cache keys hold tokenizer identity, not objects (`clip_conditioning_cache.py:90-105`, `277-305`). Tokenizer blobs (`spiece_model`, `tekken_model`, `tokenizer_json`) are structural tensors consumed by `CLIP.__init__` and excluded from bind gates (`clip_fast_hydration.py:84`; `wiring:139`, `175-186`); `strip_clip_weights` touches only `named_parameters`, so blob payloads survive stripping.

### Weakrefs vs strong refs

CONFIRMED: no `weakref`/`WeakValueDictionary`/`weakref.finalize` usage found in searched runtime sources; `_LANES` and `CpuSnapshotModels.clip` are ordinary strong references; the capture code's "weakref death checks" comment refers to external cleanup while the retained manifest is explicitly deep-copied and tensor-free (`modal_app.py:6911-6917`). Non-rooting awareness comments exist near the exclusion design (`wiring:143-150`).

---

## 4. CLIP weight-storage owners

Deduplicated by storage identity (the repo's own registry dedups by `id(untyped_storage())` and merges overlapping pointer/range pairs: `cpu_snapshot_models.py:330-385`; module identity dedup `231-247`).

| # | Owner | Reachable from | Retains values? | Lifetime | Evidence tier |
|---|---|---|---|---|---|
| O1 | `CpuSnapshotModels.clip` wrapper chain (incl. nested module params/buffers) | app instance field | **YES** (default/E37) | snapshot construction → process lifetime | CONFIRMED |
| O2 | `clip.patcher.model` | same wrapper | YES if aliasing (expected); copy would double-count | same | CONFIRMED path / aliasing SUPPORTED INFERENCE |
| O3 | External Comfy model-management entries | comfy globals | UNKNOWN | comfy-controlled | UNKNOWN |
| O4 | Speculative lane GPU tensors | `_LANES` | YES but GPU-resident, separate storages; empty in E37 clean lane | request/restore lane | CONFIRMED (not a CPU payload owner) |
| O5 | QD final GPU destination + staging buffers | QD reader owner | YES (GPU) post-restore only | read phase → bind/forward | CONFIRMED (post-restore, not snapshot payload) |

Under E37's effective configuration the unique CPU CLIP value payload is owned by O1/O2 (one storage set modulo aliasing). O3 is unproven either way.

---

## 5. Snapshot exclusion flag truth table

Control: `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS`.

| Aspect | Finding | Evidence |
|---|---|---|
| Registry definition | key defined, default `"0"`, consumed at restore, deploy-required | `config/v2/flag_registry.toml:466-472` |
| Production profile | `"0"` | `config/v2/profiles/production.toml:51` |
| E37 clean-lane profile | `"0"` explicitly; extends `e29-tracer` | `e37-clean-lane-qd4.toml:45`, `:5` |
| Selector projection | `V2_E19_FINAL_COLD_LOADER` forcibly projects `"1"` regardless of profile | `tools/v2_control/fingerprints.py:37-42` |
| Batch launcher default | `"0"` | `deploy_and_run_v2_single.bat:187`; `run_v2_single.bat:104` |
| Batch selector branches | D6/D10/E10/E19 force `"1"` | `deploy_and_run_v2_single.bat:207,233,260,301`; `run_v2_single.bat:193,220,271` |
| Deploy env passthrough | default `"0"` when env absent | `modal_app.py:3389-3391` (verified) |
| Runtime reader | `clip_snapshot_exclude_weights_enabled()` via `env_flag`; invalid tokens false | `wiring:55-57,197-198`; docstring `:16-19` |
| Branch site | inside `maybe_prepare_clip_snapshot_exclusion`, requires fast-hydration OR staged OR exclude flag enabled | `wiring:751-756` |
| Mutation | `strip_clip_weights`: ALL `cond_stage_model` params → meta (same shape/dtype/requires_grad), buffers/structure/tokenizer blobs/patcher kept, marker set | `clip_fast_hydration.py:892-921` (verified) |
| Timing | executed during snapshot construction, BEFORE capture boundary | `modal_app.py:9625-9633` vs `9855-9896` |
| Telemetry | `capture_pre_exclusion` / `capture_post_exclusion` checkpoints; `clip_fh_capture status="excluded"` with `params_replaced`, `payload_bytes_removed` | `wiring:776-787` |
| Overwriters | none found at runtime; only launcher/selector branches write the env var | exp-3 sweep |
| Related-but-distinct | `COMFYMODAL_V2_SNAPSHOT_EXCLUDE_UNET` never skips construction (identity/reporting only) | `modal_app.py:9436-9442` (verified) |
| Half-integration? | **REFUTED** — genuine runtime consumer + mutation branch | above |

What the flag does today, precisely: removes physical parameter payload only; preserves wrappers, module skeletons, buffers, tokenizer-bearing structural state, patcher, and manifest; does NOT drop the whole CLIP model; does NOT touch safetensors files on disk; does NOT prove release of arbitrary external references to old storages (it removes the normal parameter references; SUPPORTED INFERENCE that other holders would keep storages alive).

---

## 6. Requested vs projected vs deployed vs effective vs observed snapshot policy (E37)

| Stage | Value | Source | Tier |
|---|---|---|---|
| Requested (profile) | `"0"` | `e37-clean-lane-qd4.toml:45` | CONFIRMED |
| Projected (selector) | `"0"` under normal profile projection; **`"1"` if `V2_E19_FINAL_COLD_LOADER` selector applied** | `tools/v2_control/fingerprints.py:37-42` | CONFIRMED mechanism; which selector served E37 locally UNKNOWN |
| Deployed (env injection) | bat default `"0"`; passthrough default `"0"` | `deploy_and_run_v2_single.bat:187`; `modal_app.py:3389-3391` | CONFIRMED |
| Effective (runtime branch) | with `"0"`: no strip; full retention | `wiring:197-198`, `751-794` | CONFIRMED |
| Observed (artifact) | **no local raw artifact records the observed value** — `.comfymodal_experiments/` contains only scripts/state JSONs (verified by listing); `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` omits flag fields | verified | UNOBSERVABLE locally |

Drift hazards identified (mechanism CONFIRMED, E37-instance applicability UNKNOWN):

1. Selector override: deploying under `V2_E19_FINAL_COLD_LOADER` yields projected/deployed `"1"` even though the profile says `"0"` (`fingerprints.py:37-42`; launcher branches `deploy_and_run_v2_single.bat:207-301`).
2. Missing-env fallback: absent env → runtime `"0"` (`modal_app.py:3389-3391`).
3. Fail-closed eligibility: flag `"1"` still yields NO strip if clip missing, manifest build fails, or capability gates fail (`wiring:757-770`) — flag says 1, behavior is 0, telemetry says `ineligible`/`error`.
4. Historical `.v2ctl` artifacts show both states (E19-era `"1"`, E37-era `"0"`) — different selector contexts, must not be conflated (exp-3).

Consistency verdict: E37's requested/deployed expectation ("0", full retention) is consistent with its observed behavior (snapshot-retained CLIP consumed by nothing before QD reread). Direct observed-value proof is UNOBSERVABLE locally.

---

## 7. Snapshot payload accounting

Metric discipline first — these are NOT interchangeable:

- **RSS/cgroup resident memory**: process/container residency incl. allocators, runtime, buffers, models.
- **Serialized snapshot bytes**: what Modal persists; no local artifact reports it.
- **Logical tensor bytes**: sum of unique storage nbytes; not equal to either of the above.
- **Restored RSS**: post-restore residency; affected by demand-paging behavior that Modal does not document (Appendix A §7).

Best source/artifact-backed classification of retained bytes at the E37 capture boundary:

| Category | Status | Basis |
|---|---|---|
| CLIP weight values | **RETAINED** (owned by O1/O2) | Section 3/4; CONFIRMED reachability |
| UNET weight values | **RETAINED** (construction never skipped; exclude-unet is reporting-only) | `modal_app.py:9436-9442`; ~12.3 GB logical figure recorded historically in `COMFYUI_MODAL_V2_AUG9_RESOURCE_GPU_OPTIMIZATION_REPORT.md:142,235` (logical model storage, not RSS) |
| VAE weight values | RETAINED only if profile declares VAE | `cpu_snapshot_models.py:2604-2607` |
| Tokenizer/config | RETAINED (structural blobs + specs) | `clip_fast_hydration.py:84`; `wiring:139,175-186`; `cpu_snapshot_models.py:1049-1099` |
| Model skeleton/module objects | RETAINED | `cpu_snapshot_models.py:78-105`, `2635-2658` |
| Safetensors metadata/offset maps | NOT retained as such; QD rereads headers post-restore | `clip_qd_reader.py:300-384` |
| Patcher/wrapper state | RETAINED | `cpu_snapshot_models.py:1266-1272`; `clip_fast_hydration.py:1097-1213` |
| Caches | Conditioning cache ≤512 MiB serialized embeddings cap; persistence forbidden in clean lane | `clip_conditioning_cache.py:84-87`, `1937-1938`, `2116-2117` |
| Registry/INPUT_TYPES/static metadata | RETAINED (import-time registries) | Section 2.1 |
| Interpreter/import state | RETAINED (within captured process state) | Modal fact: global scope captured (Appendix A §1) |
| Diagnostic state | Metadata-only structures | Section 3 Root 6 |
| Pinned/staging allocations | Not alive at E37 capture (prewarm/preload/QD all inactive pre-capture); post-restore only | profile lines 41-54; Section 10 |
| Unknown/unattributed | External Comfy roots; allocator fragmentation; interpreter overhead | Section 16 |

Reconcilable raw numbers currently available locally:

| Metric | Value | Classification |
|---|---|---|
| Full-snapshot RAM peak | ~25.2 GB peak, p95 23.6–25.3 GB | RSS/cgroup-style residency — NOT serialized payload (`...AUG9...REPORT.md:160-162`) |
| Retained UNET | ~12.3 GB | logical resident model storage — neither RSS nor snapshot size (`:142`, `:235`) |
| E36 authoritative restore phase | 1,931.276 ms | phase timing (`E36_FULL_CRITICAL_PATH_REPORT.md`) |
| E36 authoritative first durable / wall | 18,734.476 ms / 31,381.8 ms | end-to-end timing; NOT restore-banner→first-Python |
| E36 invalid snapshot timing | 52,972.4 ms | EXCLUDED — snapshot/container failure (`E36 report:200-204`) |
| E31 cast proof | 398 NOOP_SAME_TENSOR, zero real conversions, zero allocations | conversion accounting (`E36 report:137-146`) |
| Serialized snapshot size | — | UNOBSERVABLE locally (no artifact field) |
| Unique CLIP CPU tensor bytes | — | computable at runtime via storage registry (`cpu_snapshot_models.py:387-395`) but not recorded locally |

RSS ≠ serialized snapshot ≠ logical tensor bytes ≠ restored RSS; no local artifact permits converting one into another.

---

## 8. What QD4 actually requires from the restored CLIP object

Path trace (all CONFIRMED unless noted):

1. **Plan identity** consumes workflow/model metadata only — `ExecutionPlan` carries `model_stack`/`workflow_hash`/deployment identity, no weights (`contracts.py:1002-1019`); restore identity hashes `model_key` incl. `clip_identity`, `clip_type`, loader config, volume generation (`canonical_execution.py:389-405`; `contracts.py:1077-1090`, `1111-1125`).
2. **Post-restore QD4** is strictly gated and synchronous in the clean lane: enabled required, QD must equal exactly 4, block_mib ≥ 1, launch_policy non-empty, manifest files non-empty, each path must exist (`wiring:1319-1355`, verified). Reader rereads 8-byte header length, JSON header, file size, names, shapes, dtypes, `data_offsets` (`clip_qd_reader.py:300-384`), validates dtype/shape byte sizes and contiguous coverage (`328-375`), partitions into exactly-QD static regions (`468-489`), returns GPU tensors + owner retaining loader/buffer lifetime (`wiring:1348-1368`; `clip_qd_reader.py:1843-1914`). Proof predicates require 240 planned/submitted/completed/H2D blocks and quiescence (`clean_lane.py:152-166`, `184-207`).
3. **Bind** is into an existing skeleton via Comfy dispatch with `assign=True` (`wiring:1206-1212`; design `clip_fast_hydration.py:15-40`); compatibility gated before assignment (`226-275`); destination must expose `cond_stage_model` (`clip_fp32_cast_once.py:594-597`); leaf names matched against frozen manifest (`599-640`); exact verification checks names/shapes/dtypes/device/non-meta/storage-pointer/bytes (`711-856`). Pre-bind meta parameters are explicitly expected (`324-337`). Binding is adoption/assignment, not value copy (`clip_fp32_cast_once.py:10-19`; `clip_fast_hydration.py:36-40`); E37 additionally disabled inference mode around QD GPU-buffer construction so bind receives mutable tensors without cloning full CLIP state (`E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md:48-51`).
   - No CLIP object at all → bind impossible (`clip_fp32_cast_once.py:324-353`).
   - Meta-device skeleton → sufficient (`324-337`; `clip_fast_hydration.py:523-540`).
   - Names/shapes/dtypes alone → insufficient (no executable structure/routing/encode) (`wiring:621-643`).
4. **Tokenizer/config**: blobs are structural inputs consumed at `CLIP.__init__`, excluded from bind gates (`clip_fast_hydration.py:84`; `wiring:139`, `175-186`). Post-restore filesystem provider for standalone tokenizer files is not established here (UNKNOWN); the retained skeleton carries them.
5. **Comfy integration**: patcher must be retained; hydrated owners attach to it (`clip_fast_hydration.py:1683-1700`); `model_options` checked for incompatible patch state (`291-296`, `312-339`); node identity participates in cache identity (`clip_conditioning_cache.py:294-305`, `359-377`).
6. **Forced miss**: cache key includes model/dtype/torch/workflow/node/text fields plus `cache_nonce` forcing a miss without changing inputs (`clip_conditioning_cache.py:269-312`); persistence forbidden in clean lane (`1937-1938`, `2116-2117`).
7. **Speculative hydration**: capable of instantiating/hydrating another CLIP outside the clean lane (`wiring:1256-1305`; `clip_qd_reader.py:43-47`); deliberately inactive as a restore-time source in E37 (`wiring:1319-1324`, verified); rejects non-QD publication (`1481-1484`).

### Dependency classification

| Item | Classification |
|---|---|
| Full CLIP weight values | **REDUNDANT WITH QD LOAD** |
| Parameter names | MUST RETAIN IN SNAPSHOT |
| Shapes | MUST RETAIN IN SNAPSHOT |
| Dtypes | MUST RETAIN IN SNAPSHOT |
| Safetensors offsets/header | REDUNDANT WITH QD LOAD (reread: `clip_qd_reader.py:300-384`) |
| QD block map | CAN RECONSTRUCT CHEAPLY POST-RESTORE (`468-489`) |
| Module skeleton objects (executable, routed, encode-capable) | MUST RETAIN IN SNAPSHOT |
| ModelPatcher object | MUST RETAIN IN SNAPSHOT (`clip_fast_hydration.py:1683-1700`) |
| `model_options` dict | UNSAFE TO REMOVE (`291-339`) |
| Immutable model identity / `clip_identity` | MUST RETAIN IN SNAPSHOT (`contracts.py:1077-1090`) |
| Tokenizer vocab/merges/config blobs | CHEAP TO RETAIN (small, structural); capsule relocation possible but provider unproven |
| Transform pipeline metadata | CHEAP TO RETAIN (`wiring:535-564`, `646-704`) |
| Frozen manifest (paths, key set, shapes, dtype, file index, pipeline, structural keys) | MUST RETAIN IN SNAPSHOT (`wiring:599-618`, `646-739`) |
| Device/dtype policy constants, QD policy flags | SHOULD MOVE TO DEPLOYMENT CAPSULE (already env/deploy-side: `clip_qd_reader.py:93-110`) |
| Source file path(s) | SHOULD MOVE TO WORKFLOW/SCHEDULER CAPSULE (supplied by runtime manifest: `wiring:570-576`, `1343-1355`) |
| Conditioning cache entries | REDUNDANT WITH QD LOAD (forced miss) |
| FP32 cast-once provenance | MUST RETAIN *when enabled* (`clip_fp32_cast_once.py:268-321`, `393-415`); **OFF in E37** (profile line 37) |
| Patcher owner handles/buffers | UNSAFE TO REMOVE while live (`clip_fast_hydration.py:1683-1700`) |

**Minimal snapshot-resident CLIP representation** (source-proven): an executable skeleton (`cond_stage_model`, correctly named/routed leaves, matching names/shapes, meta-compatible placeholder dtype/device, tokenizer-bearing structural state, encode methods, patcher, `model_options`, node-facing identity) + compact frozen manifest + deployment/runtime policy + source safetensors present post-restore. Full values, precomputed block maps, and conditioning entries are not required.

---

## 9. Hidden duplicate copies / half-integrations

| # | Hypothesis | Verdict | Key evidence |
|---|---|---|---|
| A1 | Snapshot restores complete CLIP values, then QD rereads them | **SUPPORTED INFERENCE (double-read)** — both consumers proven; snapshot copy has no consumer before QD replaces values | retention `cpu_snapshot_models.py:2531-2540,2635-2643`; QD source-reader design `clip_qd_reader.py:25-34`; sync call `wiring:1348-1355` |
| A2 | state_dict retained while another registry holds same storages | PARTIAL — full objects retained (not bare state_dicts); registry dedups identities/ranges but proves no second allocation | `cpu_snapshot_models.py:2635-2643`, `285-298`, `330-390` |
| A3 | Exclusion removes one owner; model-management keeps another | SUPPORTED INFERENCE risk — repo observes counts/wraps calls only; external retention unprovable here | `cpu_snapshot_models.py:2492-2505`; `clip_cold_path_forensics.py:902-986` |
| A4 | QD creates GPU owner while CPU owner stays live post-bind | PARTIAL/likely — no post-bind `del`/unload/release of the CPU snapshot owner found; QD claims single final GPU buffer | `clip_qd_reader.py:31-34`; absence-of-release finding across searched sources |
| A5 | Bind copies instead of assigning/views | **FALSIFIED for E37** — inference-mode disabled around buffer construction so bind gets mutable tensors without cloning; assign-style adoption | `E37 report:48-51`; `clip_fp32_cast_once.py:10-19`; `clip_fast_hydration.py:36-40` |
| A6 | Demand hydration can instantiate another CLIP despite snapshot copy | PROVEN capability; NOT used in E37 clean lane | `clip_qd_reader.py:43-47`; `E37 report:18-21`; `wiring:1319-1324` |
| A7 | Generic `load_models_gpu` can resurrect excluded state | SUPPORTED INFERENCE risk — wrapped/observed; direct resurrection event not captured locally | `clip_cold_path_forensics.py:902-986,1087-1120,1171-1244` |
| A8 | Identity cached but validation rereads large files | PROVEN for stat/metadata work post-construction; full-file byte reread UNKNOWN | `cpu_snapshot_models.py:2440-2444,2599-2602`, called `2660-2667` |
| A9 | Cleanup only after capture makes "excluded" telemetry misleading | FALSIFIED for allocator hygiene (runs before boundary); broader cleanup ordering UNKNOWN | `snapshot_capture_hygiene.py:1-17,136-155` |

Duplicate-copy ledger (CPU-relevant):

| Copy | Owner | Survives to snapshot? | Survives QD bind? | Used? |
|---|---|---|---|---|
| CLIP CPU values | `CpuSnapshotModels.clip` chain | YES (E37) | **no release found — likely yes** | not before QD overwrites values |
| QD pinned/block buffers | QD workers | n/a (post-restore) | workers joined pre-bind; buffer lifetime via owner | YES |
| QD GPU destination | QD owner | n/a | YES (is the bound payload) | YES |
| Storage registry ranges | `StorageRegistry` | YES | YES | diagnostics |
| Comfy management entries | comfy globals | UNKNOWN | UNKNOWN | eviction decisions |

---

## 10. Snapshot quiescence risks relevant to payload

Platform frame (OFFICIAL MODAL FACT, Appendix A): CPU snapshots capture container CPU-memory state; threads/FDs/subprocess/mmap behavior is undocumented — so anything alive and unreleased at the boundary is, at best, undefined at restore. Application answer per class:

| Class | Alive at E37 capture? | Large memory? | Can keep model storages reachable? | Must drain before lean experiment trustworthy? |
|---|---|---|---|---|
| B1 QD workers | No (post-restore only; joined before publish `clean_lane.py:184-207`) | bounded buffers | until exit | n/a at capture; YES for run-time proofs |
| B2 FASTSAFE workers | No in E37 (`UNET_FASTSAFETENSORS=0`) | potentially | potentially | YES if ever enabled at capture |
| B3 checkpoint prewarm workers | No (`CHECKPOINT_PREWARM=0`) | potentially | potentially | YES if enabled; join+FD-close paths exist (`checkpoint_prewarm.py:418-521`) |
| B4 speculative CLIP workers | Empty lane in clean lane (`wiring:1319-1324`) | YES (GPU) | YES (lane dict) | YES if enabled |
| B5 staged-safetensors producers | Not in E37 path | YES | potentially | UNKNOWN ordering; drain if used |
| B6 H2D CUDA events | Post-restore only; completed before bind (`E37 report:20-23`) | host-negligible | buffers until completion | YES for run-time proofs |
| B7 pinned staging buffers | Post-restore only | YES (bounded) | until refs/events complete | YES for run-time proofs |
| B8 model preload futures | No (`MODEL_PRELOAD=0`) | potentially | YES | YES if enabled |
| B9 cache/persistence futures | Persistence/background off in E37; flush joins workers (`clip_conditioning_cache.py:2405-2477`) | payload-dependent | cached bytes reachable | YES if enabled |
| B10 request-specific state | None at capture (pre-request) | small | potentially | keep capture pre-request (current design) |
| B11 temporary loader locals (`clip_obj/unet_obj/vae_obj`) | Released after container construction except retained fields | YES transient | YES until function exit | already scoped (`cpu_snapshot_models.py:2481-2484,2604-2643`) |
| B12 async-reader FDs | Prewarm closes on join timeout; general capture-time FD closure not proven | no large memory | no, but lifecycle risk | YES (undocumented fd survival, Appendix A §3) |

Bottom line: in the E37 configuration the capture boundary is already quiet (all background lanes off), which is precisely why it is the right CONTROL for a lean-snapshot experiment. The classes that matter for trusting a LEAN arm are the ones that would retain model storages if enabled: B2/B3/B4/B8/B9 — all provably off in the E37 profile (lines 29-54).

---

## 11. Minimal safe lean-CLIP representation

MUST RETAIN (source-proven, Section 8):
- Executable CLIP skeleton incl. `cond_stage_model`, named/routed leaves, parameter names/shapes, placeholder dtype/device (meta-compatible), tokenizer-bearing structural state (`spiece_model`/`tekken_model`/`tokenizer_json` blobs survive stripping since only `named_parameters` are replaced), encode methods, `ModelPatcher`, `model_options`, node-facing identity, immutable `clip_identity`.
- Frozen capability manifest: file paths, transformed key set, per-key shapes, source dtypes, file-index association, transform pipeline, structural destination keys, cast-once provenance when enabled.
- Deployment/runtime policy: QD=4, block size, launch policy, device/dtype policy.

CAN RECONSTRUCT CHEAPLY: QD block map (from reread header).
REDUNDANT WITH QD LOAD: full weight values; safetensors header/offsets; conditioning entries.
SHOULD MOVE TO CAPSULE: policy constants (already deploy-side); source paths (runtime-manifest-supplied).
UNSAFE TO REMOVE: `model_options`; patcher owner handles while live.
CHEAP TO RETAIN: transform pipeline metadata; tokenizer blobs.
UNKNOWN: whether every Comfy CLIP family's tokenizer needs are fully covered by retained skeleton state for families beyond recognized blob keys (`clip_fast_hydration.py:84`).

This is exactly the state produced by the existing exclusion path — hence E39 needs no new mechanism.

---

## 12. Exact E39 CONTROL vs LEAN-CLIP design

**CONTROL:** current exact E37 clean-lane algorithm and snapshot policy, unchanged: profile `e37-clean-lane-qd4` as-is (`e37-clean-lane-qd4.toml`, verified in full), including `EXCLUDE_WEIGHTS="0"`.

**LEAN-CLIP:** a NEW profile extending `e37-clean-lane-qd4` overriding exactly one semantic switch: `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = "1"`. Everything else byte-identical. Rationale: the strip happens at snapshot construction (`modal_app.py:9625-9633`), the QD4 path already binds into meta-capable skeletons (Section 8), and the pairing was designed for this (`wiring:748-750` docstring: "Path B ... strip the parameter payload in place (retaining structure/tokenizer/patcher). Fail closed.").

Isolation: CLIP-only exclusion is provably isolatable — `strip_clip_weights` mutates only `cond_stage_model` parameters (`clip_fast_hydration.py:902-915`); UNET/VAE construction and retention are untouched (`modal_app.py:9436-9442`). No need to broaden to UNET.

Mandatory preflight gates for the LEAN arm (else the arm silently degrades to CONTROL):
1. `clip_fh_capture` telemetry shows `status="excluded"` with `params_replaced>0` and `payload_bytes_removed>0` (`wiring:779-787`). If `ineligible`/`error`/`manifest_only` appears, abort the arm — fail-closed eligibility means no strip occurred.
2. `capture_post_exclusion` checkpoint shows meta/placeholder state (`clip_state_checkpoint`, `wiring:776-778`; state machine `clip_fast_hydration.py:885-889`).
3. Deploy through the normal profile path, NOT through any selector branch that overrides flags (`fingerprints.py:37-42`; launcher `:207-301`).

Frozen variables (identical both arms): QD implementation, QD=4, block size 32 MiB, `clean_lane_post_restore` launch position, thread policy, UNET loader, VAE policy, forced conditioning miss, FP32 cast-once OFF (profile line 37 — note: cast-once is already disabled in the E37 clean lane), speculative hydration inactive, scheduler capsule, CUDA synchronization, model-management behavior, snapshot model order `O0`, eviction settings, `MINIMAL_RESTORE=1`, allocator-hygiene and manifest flags at current defaults.

---

## 13. Required E39 proof predicates

**SNAPSHOT_PAYLOAD_PROOF**

| Field | Source that fills it |
|---|---|
| snapshot policy | profile fingerprint + `enable_memory_snapshot` resolution (`modal_app.py:20083-20091`) |
| unique CLIP CPU tensor bytes retained | storage registry unique-bytes report (`cpu_snapshot_models.py:387-395`) computed post-strip vs CONTROL |
| unique UNET CPU tensor bytes retained | same registry, UNET role |
| unique VAE CPU tensor bytes retained | same registry / `vae_validation_metadata.total_storage_bytes` (`modal_app.py:9463`) |
| total known model-value bytes retained | sum of role registries |
| unknown/unclassified bytes | registry filtered-out categories (`cpu_snapshot_models.py:148-158`) + RSS-minus-known delta, labeled as such |
| CLIP value payload excluded yes/no | `clip_fh_capture status="excluded"` + `payload_bytes_removed>0` (`wiring:779-787`) |
| surviving CLIP strong-reference roots | post-strip `clip_state_checkpoint` + registry scan showing zero non-meta CLIP CPU storages |
| snapshot quiescence status | capture-boundary manifest (threads/executors/FDs/GC: `snapshot_build_manifest.py:396-418`) |
| config fingerprint | v2ctl fingerprints (`tools/v2_control/fingerprints.py`) |
| deployment fingerprint | v2ctl provenance (`tools/v2_control/provenance.py`) |

**LEAN_CLIP_PROOF**

| Field | Source |
|---|---|
| CLIP model identity exact | `clip_identity` in restore identity hash (`canonical_execution.py:389-405`) |
| tokenizer/config identity exact | cache-key tokenizer identity fields (`clip_conditioning_cache.py:276-312`) |
| QD4 selected | `CLEAN_LANE_QD4_REQUIRED` gate passed (`wiring:1332-1333`) |
| 4/4 actual concurrency | clean-lane proof (`clean_lane.py:152-166`) |
| 240/240 coverage | same |
| no QD fallback | clean-lane quiescence predicates (`clean_lane.py:184-207`) |
| real conditioning miss | forced-miss nonce path taken (`clip_conditioning_cache.py:269-312`) |
| bind succeeded from lean representation | post-bind verification names/shapes/dtypes/device/non-meta/storage-pointer/bytes (`clip_fp32_cast_once.py:711-856`) |
| exact SHA | `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` vs `E37_EXPECTED_OUTPUT_SHA` gate (profile line 23) |
| no native/demand reread beyond QD | absence of `_fastsafe_load`/native-load telemetry in the lane |
| no hidden CPU-state resurrection | no speculative publication (`wiring:1481-1484` satisfied), no `load_models_gpu` CLIP resurrection events in forensics wrappers |

Additional measurement to prove leanness (answers Final Q8): delta of `capture_pre_exclusion` vs `capture_post_exclusion` checkpoint payload bytes; registry unique CLIP CPU bytes ≈ 0 post-strip while UNET/VAE unchanged; ready-return RSS/cgroup fields from the capture manifest; and, if the platform surfaces it in deploy logs, the Modal-side snapshot size (UNOBSERVABLE from app code today).

---

## 14. Risks that could change exact output

1. **Fail-closed eligibility skips the strip** → LEAN arm equals CONTROL (contaminated A/B). Mitigation: predicate 13.1.
2. **Selector/profile drift** deploys a different effective flag than intended (`fingerprints.py:37-42`; launcher branches). Mitigation: dedicated profile + fingerprint assertions.
3. **External Comfy roots retain CLIP storages** despite parameter stripping (O3, UNKNOWN) → snapshot stays fat even in LEAN arm; leanness proof must be measured, not assumed from the flag.
4. **Bind rejects meta destination on some leaf** the manifest didn't anticipate → runtime failure (loud, not silent) or verification mismatch (`clip_fp32_cast_once.py:711-856`).
5. **Tokenizer blob loss for an unrecognized family** → encode divergence; mitigated by tokenizer-identity predicate + exact SHA.
6. **Volume file mutation/deletion between capture and restore** breaks QD source reads (Modal fact: deleting Volume files used at restore can fail restore; Appendix A §6) — applies to both arms equally.
7. **Randomness repetition** after restore (Modal FAQ) — identical in both arms since the algorithm is unchanged; still part of why SHA equality is the binding predicate.
8. **Post-bind CPU-owner lifetime** (A4): no release found; affects residency accounting but not output correctness.

## 15. Things E39 must NOT change simultaneously

QD implementation; QD=4; block size; CLIP launch position (`clean_lane_post_restore`); thread policy; UNET loader; VAE policy; conditioning cache policy (forced miss); FP32 cast-once setting (currently `"0"` in this profile — preserve as-is); speculative hydration; scheduler capsule; CUDA synchronization; model-management behavior; snapshot model order (`O0`); `EVICT_MODELS_BEFORE_SNAPSHOT=0`; `MINIMAL_RESTORE=1`; `SNAPSHOT_EXCLUDE_UNET=0`; allocator-hygiene and snapshot-manifest flags; deploy path/selector choice.

## 16. Open unknowns

1. External `comfy.sd.CLIP`/`ModelPatcher`/`model_management` internals: aliasing vs copying; post-strip retention; resurrection semantics (outside this checkout).
2. Serialized snapshot byte size: no local metric; platform log surface unverified.
3. Exact unique CLIP CPU tensor bytes in E37 (computable at runtime; not recorded locally).
4. Whether restore-time validation ever hashes full model bytes vs stats only (stats PROVEN; hashing UNKNOWN).
5. Post-bind release of the CPU snapshot CLIP owner (none found).
6. Restore-banner→first-Python latency: no local raw field; E36 "first durable" is a different metric.
7. Standalone tokenizer/config filesystem provider post-restore (skeleton-carried state is the proven carrier).
8. Which selector served the historical E37 deploy (affects stage-6 drift narrative, not current-source facts).

## Appendix A — Official Modal facts used (librarian lane, docs checked 2026-08-21)

1. CPU Memory Snapshots capture container state including global-scope code/imports; not documented as heap-only; process-tree/region semantics undocumented. [https://modal.com/docs/guide/memory-snapshots]
2. Ordering: global init → `@enter(snap=True)` → snapshot creation → restore → `@enter(snap=False)` → requests; exact capture timing vs Python return undocumented. [same; https://modal.com/docs/sdk/py/latest/enter]
3. Not captured (documented): GPU state for CPU snapshots; GPU access blocked during snap=True. Undocumented: threads, FDs, sockets, subprocesses, mmap, tmpfs. [same]
4. Restore reuses captured in-memory state; ~3–10× faster init claims; no documented size↔latency model; "fewer bytes ⇒ greater speedup" is qualitative. [same; https://modal.com/docs/guide/cold-start]
5. No official max snapshot size; guidance: avoid snapshotting recreable caches; snapshots don't speed up storage-bound loading. [same]
6. Volumes: changes don't update snapshots; deleting Volume files used at restore can break restore; mounts independent of memory state; handle survival undocumented. [same; https://modal.com/docs/guide/volumes]
7. Demand paging/COW/RSS-vs-serialized distinctions: undocumented — measure, don't assume. [same]
8. CPU snapshots GA; deployed Apps only; redeploy invalidates; ~6 worker-specific snapshots may be created; worker compatibility matters. [same; https://modal.com/docs/guide/feature-maturity]

Implication labeled as inference: CPU-resident weights at capture fall within capturable state; keeping them inflates captured bytes; Modal publishes no guarantee about how much that costs restore time — hence E39 must measure (Final Q9 falsifier below), not assume.

---

## 17. Final answers

**1. Are full CLIP values actually present in the E37 CPU snapshot?**
YES — CONFIRMED by source reachability: `self._cpu_snapshot_models.clip` → wrapper → `cond_stage_model`/`clip_l`/`clip_g`/`patcher.model` → parameters/buffers → storages (`cpu_snapshot_models.py:78-105,1203-1231,2635-2658`), with exclusion explicitly `"0"` in the E37 profile (line 45, verified).

**2. Which exact strong-reference paths keep them alive?**
(a) app field → `CpuSnapshotModels.clip` → wrapper modules → parameters → storages (CONFIRMED); (b) the same wrapper's `patcher.model` (CONFIRMED path; aliasing expected, SUPPORTED INFERENCE); (c) possibly external Comfy model-management entries (UNKNOWN). Manifests, conditioning cache, forensics, and speculative lanes do NOT retain the CPU storages (CONFIRMED terminations, Section 3).

**3. Does the current exclusion control really remove those storages?**
YES when enabled and eligible — it replaces every `cond_stage_model` parameter with a same-shape/dtype meta Parameter in place before capture, keeping buffers/structure/tokenizer/patcher, with pre/post telemetry (`clip_fast_hydration.py:892-921`; `wiring:745-794`, verified). It removes the normal parameter references; it cannot prove release of arbitrary external holders. In E37 it was OFF, so E37's snapshot did NOT exclude.

**4. If not, why not?**
Not applicable as a failure: the control works; E37 simply requested `"0"` (profile line 45). The only ways flag=1 fails to exclude are fail-closed eligibility outcomes (`no_clip`/`error`/`ineligible`, `wiring:757-770`) — detectable via telemetry.

**5. Can CLIP values be safely omitted while keeping the E37 QD4 algorithm exact?**
YES, source-proven: QD4 rereads all values plus header/offsets from source files; bind is assign-style adoption into an existing skeleton; meta destinations are explicitly expected/tolerated; the exclusion feature was designed as the pairing partner for this bind (`wiring:748-750`). Exactness remains gated by the Section 13 predicates, especially exact-SHA equality.

**6. Exactly what must remain in the snapshot?**
Executable CLIP skeleton (named/routed leaves, names/shapes, meta-compatible placeholders, tokenizer-bearing structural state, encode methods) + `ModelPatcher` + `model_options` + immutable `clip_identity` + frozen manifest (paths, key set, shapes, dtypes, file index, transform pipeline, structural keys) + deployment/runtime policy (QD4/block/launch/device/dtype). Nothing else CLIP-value-related.

**7. What is the smallest source change E39 would need?**
None in production code for the experiment itself: one new profile extending `e37-clean-lane-qd4` with `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS = "1"` plus the Section 13 preflight assertions. Optional hardening (post-experiment): emit the observed flag value and post-strip unique CLIP CPU bytes into the clean-lane proof record.

**8. What measurement would prove the snapshot actually became leaner?**
(1) `payload_bytes_removed > 0` with `params_replaced` matching full parameter count (`wiring:779-787`); (2) storage-registry unique CLIP CPU bytes ≈ 0 post-strip while UNET/VAE bytes unchanged (`cpu_snapshot_models.py:387-395`); (3) reduced ready-return RSS/cgroup in the capture manifest (`snapshot_build_manifest.py:396-418`); (4) Modal-side snapshot-size delta if surfaced in deploy logs (platform metric, otherwise UNOBSERVABLE). Each metric labeled per Section 7 discipline.

**9. What result would falsify the theory that the large CLIP payload contributes materially to restore-banner→first-Python latency?**
Repeated cold restores where the LEAN arm (i) passes every LEAN_CLIP_PROOF predicate including exact SHA, (ii) demonstrably excludes the CLIP payload per SNAPSHOT_PAYLOAD_PROOF, and (iii) shows restore-banner→first-Python latency statistically indistinguishable from CONTROL. Conversely, a reproducible material reduction under (i)+(ii) supports the theory. Per official docs there is no guaranteed size↔latency relationship, so only this measured A/B decides it.
