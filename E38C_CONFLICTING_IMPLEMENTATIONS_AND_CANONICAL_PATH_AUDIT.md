# E38C — Conflicting Implementations, Reachability, and Canonical Runtime Path Audit

Batch: E38C · Date: 2026-08-21 · Branch: `TESTING2` (dirty; E31–E37 uncommitted, +11,558/−1,489 across 55 tracked files vs HEAD `8e49d75`)
Authority rule applied: **current local worktree is authoritative**. Git history used only for origin. Every CONFIRMED claim was re-read in native source. No production source, tests, profiles, or git state were modified. This report is the only file created.

Evidence labels: **CONFIRMED** (file:line re-read) · **SUPPORTED INFERENCE** (multiple consistent sources, not directly asserted) · **HYPOTHESIS** · **UNKNOWN** (not establishable from current source) · **UNOBSERVABLE** (outside this checkout, e.g. Comfy core internals).

---

## 1. Executive verdict

The runtime is a **composite of five optimization generations stacked without retirement** (baseline → conditioning-cache era → E28 critical-path era → E29 tracer era → E30/E31 QD/cast era → dirty E32–E37 control-plane era). New fast paths were added beside old demand paths; fallbacks became permanent arms; instrumentation became functional control flow.

**CONFIRMED headline facts:**

1. **CLIP has 5 implementations** of "produce a ready CLIP" (native Comfy demand, FastSafe direct-GPU hydration, QD reader, speculative lane, CPU-snapshot restore + meta/assign bind). QD and FastSafe are **alternative arms for one load, not stacked layers** (`clip_qd_reader.py:1886-1901` drop-in contract; exclusive branches `clip_fast_hydration_wiring.py:1319-1435` vs `1632-1688`). They still compose at boundaries: the speculative lane may run either arm and a rejected speculative result falls into the FastSafe loop (`wiring:1621-1688`); in clean lane a QD failure is fail-closed with no FastSafe fallback (`wiring:1430-1442`).
2. **E37 clean lane is one understandable algorithm at dispatch level** (synchronous QD4, quiescence-proven, fail-closed), but it is single-algorithm **by runtime suppression, not by removal**: the inherited profile still arms `COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1` (`e29-tracer.toml:35`, inherited by `e37-clean-lane-qd4.toml:5 extends = "e29-tracer"`), suppressed only because `clean_lane.enabled()` short-circuits launch (`speculative_clip_hydration.py:1094-1104`). `clean_lane.enabled()` also gates real dispatch branches (`wiring:1319,1437,1482`) — a measurement module is part of functional control flow.
3. **Production is a branch composite**: CPU-snapshot restore + native fast-disk UNET + late VAE + native Comfy CLIP demand + conditioning cache, with the generic `load_models_gpu` bookkeeping path always reachable behind every custom loader (`model_preload.py:4142+` documents that it "re-runs ComfyUI's ModelPatcher.load bookkeeping"; boundary at `:4347`).
4. **The reported owner-key mismatch is CONFIRMED and live**: producer maps role `"clip"` → owner `"restore_clip_loader"` (`comfyapp.py:11858`) while request preflight only waits when `inflight.get("owner") == "restore_preload"` (`comfyapp.py:12323`). A CLIP restore-preload read is therefore never awaited by `_wait_for_restore_preload_before_request`. Scope note (oracle-verified): other wait mechanisms (`_load_one` duplicate adoption, `ModelPreloadCoordinator.wait_clip()`) can still wait; the defect is specific to this preflight consumer.
5. **Two truth systems exist for configuration** (deploy-baked container env vs registry/profile projection) with ~20 legacy direct-read env families bypassing `flag_registry.toml`; **four-plus non-equivalent identity systems** can each say "same deployment" over different source sets; **one acceptance authority** exists (`tools/v2_control/validation.py` StructuralValidator, fail-closed) amid ~15 timing/telemetry systems that are representation only.
6. **Monkey-patch stacking is real but conditional**: two separate `load_models_gpu` wrapper layers exist (`comfyapp.py:15854-15899` generic profiler loop; `:16898-16982` separate profiled assignment saving `_orig_lmg`, no uninstall shown). They *can* nest around one physical call; there is no cross-layer idempotence guarantee. `ModelPatcher.clone` is wrapped twice (`:15791-15815`, `:21997-21998`).

**Verdict:** E39 must canonicalize by **gating and unifying authorities**, not by deleting old code blindly. The smallest safe canonical core already exists in pieces: `ResolvedConfig` (config), `deployment_spec.build_deployment_identity` (source identity), `QdGpuOwner` (storage ownership), clean-lane synchronous QD4 (CLIP algorithm), CPU snapshot + native fast-disk + late VAE (production model route), `StructuralValidator` (acceptance), `critical_path_ledger` (timing representation), `CommitCoordinator` (persistence).

---

## 2. How many competing implementations actually matter

| Responsibility | Implementations found | Materially competing today | Why |
|---|---:|---:|---|
| A Control plane | ~20 launch families | 3 | v2ctl+BAT canonical; benchmark_v2_direct; legacy benchmark_modal* harnesses |
| B Configuration | 1 resolver + ~20 direct-env families + aliases | 2 truth systems | Deploy-baked env vs ResolvedConfig projection |
| C Identity | 8+ systems | 4 | deployment_spec / v2ctl fingerprints / source_probe(8 files) / runtime_shape+generation (+registry anchor) |
| D Snapshot state | 3 classes | 2 | Actual model objects (CpuSnapshotModels/GPU shadow) vs metadata/diagnostics |
| E CLIP loading | 5 | 3–4 | native / FastSafe / QD (+speculative orchestration, +snapshot bind) |
| F CLIP ownership | 7 registries | 4 authorities | _ACTIVE_MODEL_READS, _LANES/_STATES, coordinator, QD/FastSafe owners |
| G UNET loading | 7+ | 3 | CPU snapshot / native fast-disk / fastsafe (+generic Comfy always reachable) |
| H VAE | 5 paths | 2 | snapshot retention+late activation vs native loader transition |
| I Comfy integration | 10 wrapper sites | 3 risky | dual load_models_gpu layers, dual clone wraps, forensics stack |
| J Workflow prep | ExecutionPlan + seed + caches | 2 | plan reuse vs seed/signature recomputation on rebuild |
| K Conditioning cache | 1 cache, 2 modes | 1 (+nonce switch) | fail-closed design is sound |
| L Timing | ~15 systems | 1 acceptance + 1 representation | validation.py decides; ledger represents |
| M Artifacts | 4 collectors + selector | 1 canonical + legacy mtime scans | DirectOutputSink/structured selector vs history/mtime |
| N Cleanup | 6 authorities | 3 overlapping GPU-release authorities | Comfy free_memory/soft_empty_cache + teardown diagnostics + single-use exit |

---

## 3. Canonical responsibility inventory

### A. Control plane / invocation
- **v2ctl CLI** `tools/v2_control/cli.py` (+backend/config/profiles/fingerprints/provenance/validation) — canonical deploy/run/config/doctor/gates.
- **Canonical execution** `canonical_execution.py` — shared plan-build/dispatch implementation.
- **Modal app** `comfymodal_runtime/modal_app.py` — class `ModalRuntimeEntrypointV2`; endpoints `run_plan_stream` (`:17762`), `run_prompt_stream` (`:19866`), `run_checkpoint_stream` (`:19897`).
- **BAT wrappers** `deploy_and_run_v2_single.bat`, `run_v2_single.bat` (production-adjacent); `deploy_v2_full_trace_only.bat`, `deploy_and_benchmark_v2_shadow.bat`, `deploy_v2_transfer_ab.bat` (diagnostic).
- **Benchmark launchers** `tools/benchmark_v2_direct.py` (canonical client, `--verify-e28-profile` gate), `tools/batch_c_acceptance.py`, `tools/e30_ab.py`.
- **Legacy harnesses** `benchmark_modal.py` (route `legacy` default), `benchmark_modal_e2e.py` (mutates child env `:1556-1570`), `benchmark_modal_parallel_matrix.py`, `benchmark_modal_scheduler_test.py`.
- **Experiment A/B wrappers** `deploy_and_run_backing_ab.py`, `deploy_and_run_provider_ab.py`, `deploy_and_run_region_ab.py`, `deploy_and_run_ownership_rehoming.py`.
- **Warmup** `deploy_warmup.py`, `warmup_profile.py` (reachability from source UNKNOWN).
- **Compatibility runner** `comfymodal_runtime/compatibility.py` (SUPPORTED INFERENCE only).
- **Bootstrap/executor** `runtime_bootstrap.py` (`:1240,1295,1942`), `runtime_executor.py`, `execution_runtime.py`.

### B. Configuration
- **Profile inheritance** single-parent chain `tools/v2_control/profiles.py:162-202`; current chains: `production` (root), `e29-tracer → production`, `e37-clean-lane-qd4 → e29-tracer`; arm profiles under `config/v2/profiles/`.
- **ResolvedConfig** built once by `ConfigResolver.resolve()` `tools/v2_control/config.py:295-305`; precedence defaults→profile→CLI→`--inherit`→`--set`→alias canonicalization (`:217-239`); ambient shell env never merges (`:5-10`).
- **flag_registry.toml** — metadata incl. deploy-baked classification (`:196-205`); does not itself force runtime behavior.
- **Direct os.environ readers** — `canonical_execution.py` (app name + legacy alias `:375-377`, combined hash `:1243,2151`, env profile `:1803,2003`, snapshot flags `:2006-2009`, environment `:2245`, region/cloud `:3555-3556`); `comfyapp.py` (~40 readers incl. preload/warmup/stall/safetensors/manager `:357-1673`, dynamic `COMFYMODAL_<name>` alias lookup `:3455,3478`, return mode `:3568`); `comfymodal_runtime/*` (env.py `:49-51`, runtime_bootstrap `:1203-1213,1863,1978,2002-2005`, runtime_executor `:2412-2425`, cpu_snapshot_models `:521-530,2493`, clip_qd_reader `:95-99`, checkpoint_prewarm `:71-80`, contracts `:35-36`, local_handle_client `:361-668`, gantt_telemetry `:35`, host_hardware_telemetry `:244-249`, clip_cold_path_forensics `:57-59`, clip_fast_hydration_wiring `:55-57`, clean_lane `:17-43`).
- **Legacy aliases** — registry aliasing pre-resolution (`config.py:233-239`); dynamic legacy lookup bypassing registry (`comfyapp.py:3455,3478`); conditioning-cache legacy names (`clip_conditioning_cache.py:59-61`).
- **Deleted profile** `config/v2/profiles/e31-clip-fp32.toml` absent from worktree; no current scoped reference found (repo-wide absence not provable due to ignored artifacts).

### C. Deployment/source identity
| System | File | Hashes |
|---|---|---|
| DeploymentIdentity (canonical source) | `deployment_spec.py:_iter_source_files:156, compute_file_hashes:189, build_deployment_identity:232` | all `.py/.js/.mjs` under runtime root + custom-node dirs; hardcoded exclusions `:27-94`; path+SHA-256 |
| v2ctl deploy fingerprint | `tools/v2_control/fingerprints.py:62-97,192-199` | git HEAD + dirty flag + dirty_hashes + target/resources/profile/flags JSON — **no source walk** |
| Source probe | `tools/v2_control/source_probe.py:33-43,76-119,282-303` | exactly 8 module files (modal_app, critical_path_ledger, runtime_bootstrap, runtime_executor, gantt_telemetry, model_preload, clip_fast_hydration_wiring, registry_proof_store), SHA+size+mtime+realpath |
| Runtime-shape fingerprint | `runtime_shape.py:144-146,149-239` | thread policy, torch threads, snapshot order, CPU/mem request |
| Runtime generation | `runtime_generation.py:76-83,95-129,214-247` | prescan_custom_nodes.json + gpu_capacity_frozen.json contents; Volume.reload skip gate |
| Dependency manifest identity | `dependency_manifest.py:44-59,262-284` | schema + supplied combined_hash + dependency hash + custom-node generation (inherits upstream hash) |
| Registry proof / store | `registry_proof.py:118-212,233-301,422-503`; `registry_proof_store.py:101-114,215-247` | workflow-class module bytes (LF-normalized SHA); store keyed to `.deployed_state.json` anchor |
| Execution/snapshot seed | `execution_seed.py:375-447,484-586` | topology, static signatures, workflow/source hashes, deployment hash (no tensors) |
| Provenance sibling | `tools/v2_control/provenance.py:55-102,203-228` | resolved config + fingerprints + artifact SHA (records, does not validate) |

`.modalignore` (upload policy, `:1-41`) is parsed by **none** of the above — CONFIRMED.

### D. Snapshot representation
- **CpuSnapshotModels** `cpu_snapshot_models.py:78-104` (retained CLIP/UNET/optional VAE + file facts + policy), loader `:2447-2673`, retarget `:2960-3010`, validator tolerates exclusion marker `_comfymodal_clip_fh_excluded_weights` `:1287`.
- **CLIP weight exclusion** `clip_fast_hydration_wiring.py:197,384-393,754-775` (gate `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS`); excluded weights CAN re-enter via any later hydration/loader path (SUPPORTED INFERENCE).
- **RestorePlan model identity** `restore_plan.py:226-245,270-334` (model-only key; atomic publication `:443-560`).
- **Runtime-state volume** `runtime_state.py:96-195,314-559` (atomic JSON + `CommitCoordinator` `:314`).
- **Snapshot seed** `execution_seed.py:464-724` (structural only; forbidden-state docstring `:589-595`).
- **GPU snapshot shadow** `gpu_snapshot_shadow.py:883-896,1011-1188` (isolated experimental app; GPU-resident models; original loaders bypassed).
- **Diagnostics-only**: `snapshot_build_manifest.py:381-453`, `snapshot_capture_hygiene.py:136-204`, `modal_restore_boundary.py:173-298` (timestamp evidence, "never guesses" `:11-15`).
- **CheckpointPrewarmer** `checkpoint_prewarm.py:205-212,232-484` (byte/page prewarm; retains no payload).

### E/F/G/H/I/J/K/L/M/N inventories are embedded in the Conflict Matrix (§4) and domain sections (§5–§15).

---

## 4. Conflict Matrix

Legend: Reach columns — E37 = reachable in `e37-clean-lane-qd4` effective env; Prod = `production.toml` effective env; FB = reachable only as fallback; BENCH = benchmark/diagnostic-only. "After" = can execute after another implementation already did work in the same request. Status ∈ {AUTHORITATIVE CANDIDATE (AC), REQUIRED FALLBACK (RF), COMPATIBILITY ONLY (CO), BENCHMARK/DIAGNOSTIC ONLY (BO), MERGE INTO CANONICAL (MC), QUARANTINE (Q), DELETE AFTER PROOF (DAP), UNKNOWN (U)}.

### 4A. Control plane + configuration (A, B)

| Implementation | Source | Gate/default | E37 | Prod | FB | BENCH | After | Concurrent | Owner/state | Src I/O | GPU | Sync | Cleanup authority | Fallback→ | Telemetry proof | Tests | Exact-output | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| v2ctl CLI | tools/v2_control/cli.py | explicit invocation | Y | Y | N | N | N | N | ResolvedConfig | local reads | N | N | n/a | n/a | provenance sibling | test_v2ctl_* | artifact SHA recorded | AC |
| ConfigResolver/ResolvedConfig | config.py:295-305 | always | Y | Y | N | N | N | N | ResolvedConfig | none | N | N | n/a | n/a | config proof in validator | test_v2ctl_config | config proof | AC |
| Profile loader | profiles.py:162-202 | resolve() | Y | Y | N | N | N | N | merged dict | reads TOMLs | N | N | n/a | n/a | resolved env dump | test_v2ctl_profiles | via config proof | AC |
| run_plan_stream endpoint | modal_app.py:17762 | remote call | Y | Y | N | N | Y | per-request | request lifecycle | model I/O | Y | Y | request teardown | error path | ledger/trace | test_modal_app_identity | expected-SHA runs | AC |
| run_prompt_stream endpoint | modal_app.py:19866 | UI/compat callers | cond | cond | Y | N | Y | per-request | request lifecycle | model I/O | Y | Y | request teardown | error | trace | partial | unk | CO |
| run_checkpoint_stream | modal_app.py:19897 | checkpoint callers | N | cond | Y | Y | Y | per-request | request lifecycle | model I/O | Y | Y | request teardown | error | trace | unk | unk | BO |
| deploy_and_run_v2_single.bat | BAT:1-554 | manual | Y | Y | N | N | N | N | process env | none | N | N | n/a | probe path w/o V2_E28_VALIDATION (e29-tracer.toml:24-27) | verifier gate output | manual | via artifacts | MC (merge w/ run bat) |
| run_v2_single.bat | BAT:308-543 | manual | Y | Y | N | Y | N | N | process env | none | N | N | n/a | probe path | verifier gate | manual | via artifacts | MC |
| deploy_v2_full_trace_only.bat | BAT:19-96 | manual diag | diag | N | N | Y | N | N | process env | none | N | N | n/a | n/a | full trace | none | unk | BO |
| shadow/transfer AB BATs | BATs | manual | N | N | N | Y | N | N | own apps | none | N | N | n/a | n/a | experiment stores | none | unk | DAP-candidate |
| benchmark_v2_direct.py | tools/:56,116,2087 | BAT/direct | Y | Y | N | Y | N | N | child env | artifact fetch | N | N | n/a | n/a | --verify-e28-profile | test_benchmark_v2_proof_collection | expected SHA compare | AC (bench lane) |
| batch_c_acceptance.py | tools/ | campaign | N | N | N | Y | N | N | campaign state | artifacts | N | N | n/a | n/a | acceptance report | itself | campaign | BO |
| e30_ab.py | tools/ | experiment | N | N | N | Y | N | N | arms | artifacts | N | N | n/a | n/a | E30 store | test_e30_ab_prep | A/B | BO |
| benchmark_modal.py | :1254-1258 | direct | N | N | N | Y | N | N | child env | artifacts | N | N | n/a | legacy route | restore_timing fields | none | unk | DAP-candidate |
| benchmark_modal_e2e.py | :385-391,:1556-1570 | direct | N | N | N | Y | N | N | mutates child env | artifacts | N | N | n/a | n/a | own logs | none | unk | DAP-candidate |
| parallel-matrix / scheduler-test benchmarks | root scripts | direct | N | N | N | Y | N | N | env | none | N | N | n/a | n/a | logs | none | unk | DAP-candidate |
| region/provider/backing/rehoming AB wrappers | root scripts | direct | N | N | N | Y | N | N | env | artifacts | N | N | n/a | n/a | experiment stores | none | unk | DAP-candidate |
| deploy_warmup.py / warmup_profile.py | root | unknown | unk | unk | unk | Y | N | N | warmup state | model files | N | N | own workers | skip | warmup logs | none | unk | U |
| compatibility runner | comfymodal_runtime/compatibility.py | compat callers | cond | cond | Y | N | Y | per-request | request | model I/O | Y | Y | request | native | trace | unk | unk | U |
| Direct legacy env readers (~20 families) | comfyapp.py:357-1673 etc. | env presence | varies | varies | — | — | Y | Y | module globals | none | indirect | indirect | n/a | hardcoded defaults | some log lines | sparse | n/a | MC behind ResolvedConfig |
| Dynamic COMFYMODAL_<name> alias | comfyapp.py:3455,3478 | name-based | Y | Y | — | — | Y | Y | env | none | N | N | n/a | n/a | none | none | n/a | Q (bypasses registry) |
| runtime_overrides channel | comfymodal_runtime/runtime_overrides.py:33,103-121 | policy=forbid default | off | off | — | — | Y | N | override file | file read | N | N | n/a | forbid | policy events | test coverage unk | n/a | CO |

### 4B. Identity + snapshots (C, D)

| Implementation | Source | Gate/default | E37 | Prod | FB | BENCH | After | Concurrent | Owner/state | Src I/O | GPU | Sync | Cleanup | Fallback→ | Telemetry | Tests | Exact-output | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deployment_spec identity | deployment_spec.py:156-283 | build call | Y | Y | N | N | N | N | identity record | hashes tree | N | N | n/a | n/a | combined_hash in metadata | test_deployment_proof | hash equality | AC |
| v2ctl fingerprints | fingerprints.py:62-97 | deploy/run/config | Y | Y | N | N | N | N | fingerprint dict | git commands | N | N | n/a | n/a | deploy_fingerprint | test_v2ctl_fingerprints | recorded | MC (projection only) |
| source probe (8 files) | source_probe.py:33-303 | stop-gate run | Y | Y | N | N | N | N | probe report | remote SHA fetch | N | N | n/a | fail exit≠0 | MATCH/MISMATCH line | test_v2ctl_validation(partial) | byte equality (8 files) | MC behind canonical identity |
| runtime_shape | runtime_shape.py:144-239 | runtime env | Y | Y | N | N | N | N | shape payload | none | N | N | n/a | n/a | shape label | unk | n/a | KEEP (separate domain) |
| runtime_generation | runtime_generation.py:95-247 | volume state | Y | Y | N | N | N | N | generation manifest | volume reads | N | N | n/a | reload fail-closed | reload decisions | test coverage unk | manifest equality | KEEP |
| dependency_manifest | dependency_manifest.py:35-285 | preflight | Y | Y | N | N | N | N | persisted manifest | none (inherits) | N | N | n/a | full revalidation | identity mismatch logs | test_cachedit_dependency_family | check_identity | MC |
| registry_proof + store | registry_proof.py/store | plan validation | Y | Y | N | N | N | N | store JSON | import on miss | N | N | n/a | live registry proof | parity gates | test_v2_d1_stale_identity | class identity equality | AC (scoped) |
| execution seed | execution_seed.py:375-724 | publisher/runtime | Y | Y | N | N | N | N | seed payload | none | N | N | n/a | rebuild | schema markers | test_v2_seed_publication | structural | AC |
| CpuSnapshotModels | cpu_snapshot_models.py:78-104,2447-3010 | CPU_MODEL_SNAPSHOT=1 | Y(inh) | Y | N | N | Y(then hydrate) | capture-time | snapshot registry | volume read | retarget H2D | validation syncs | snapshot mgr | demand load | validator events | test_e28/e30 suites | shape/device validation | AC |
| CLIP weight exclusion | wiring:197,384-393,754-775 | EXCLUDE_WEIGHTS | cond | cond(off unless FH) | N | N | Y(re-entry) | N | marker :1287 | none | N | N | n/a | hydration required | exclusion marker | unk | unk | MC w/ lean-payload work |
| RestorePlan | restore_plan.py:226-560 | publisher | Y | Y | N | N | N | N | volume JSON | none | N | N | CommitCoordinator | no-plan path | generation bump | test_restore_plan_publication | key stability | AC |
| GPU snapshot shadow | gpu_snapshot_shadow.py:1011-1188 | isolated app | N | N | N | Y | Y(bypass loaders) | N | retained GPU objs | none extra | Y(resident) | internal | app lifecycle | n/a | own traces | unk | unk | BO/Q |
| snapshot diagnostics trio | build_manifest/hygiene/boundary | env gates, off for measured runs | diag | diag | N | Y | N | N | reports | proc/fs reads | N | N | n/a | n/a | reports | unk | n/a | BO |

### 4C. CLIP loading + ownership (E, F)

| Implementation | Source | Gate/default | E37 | Prod | FB | BENCH | After | Concurrent | Owner/state | Src I/O | GPU | Sync | Cleanup authority | Fallback→ | Telemetry proof | Tests | Exact-output | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Native Comfy demand load | wiring:2042-2048 → Comfy core | FH off or custom failure | N(dispatch) | **Y(default arm)** | Y | N | Y(after custom failure) | Comfy-managed | ModelPatcher/current_loaded_models | safetensors read | Comfy H2D | Comfy-internal | Comfy patcher | none (final) | mode:native result | Comfy-side | via expected SHA | RF (fail-closed final) |
| FastSafe direct-GPU hydration | clip_fast_hydration.py + wiring:1632-1688 | CLIP_FAST_HYDRATION=1 (prod OFF) | armed but superseded by QD branch | N | Y | Y(E37 fastsafe profile) | Y(after rejected speculative) | owners attached post-bind | _FastsafeOwner + patcher attrs (:653,:865-870) | external fastsafetensors read | CUDA tensors | event wait/scoped sync :1716-1726 | _close_source_owners :2004-2024 | native :2042-2048 | loader_arm=fastsafe :1740-1745 | test_e28 suite | expected SHA (e37-clip-fastsafe profile) | RF |
| QD reader (QD4) | clip_qd_reader.py:1556-1833; wiring:1319-1435 | CLIP_QD_READER=1 (+clean-lane QD=4 + quiescence) | **Y(synchronous, fail-closed)** | N(flag off) | Y(ordinary mode) | Y(A/B) | alt-arm only | pinned blocks qd*2 async H2D | QdGpuOwner :1344-1399 (facade :1853-1879 = 2nd close authority) | raw pread header+blocks | contiguous uint8 CUDA buf + async H2D + events | waits ALL events before publish | owner.close/release_storage; failure cleanup :1824-1839 | ordinary: FastSafe/native; clean lane: FAIL :1430-1442 | loader_arm=qd_demand/qd_speculative; clean_lane.mark_qd_ready | test_e30_clip_qd_io | 240/240 blocks, QD4 concurrency, E37 SHA | AC |
| Speculative hydration lane | speculative_clip_hydration.py:64,504-560; wiring:1260-1317 | SPECULATIVE=1 AND fast-hydration enabled AND not clean_lane | armed, launch-suppressed :1094-1104 | self-skips (FH off) :428-430 | Y | Y(E26/E28 era) | Y(precedes demand; join ≤20s :1290-1304) | background lane during restore | _LANES :64; reserved _RESTORE_TIME_KEY | early source read (fastsafe or QD arm :614,802) | same as chosen arm | join timeout | lane cleanup :973-1020; rejected owners closed wiring:1621-1631 | demand FastSafe loop | clip_fh_speculative_skip reasons | test_v2_e25/e26 | via downstream arm | Q (superseded by clean-lane policy; keep gated) |
| E31 cast-once transform | clip_fp32_cast_once.py:197,486-976; wiring:1661-1683,1789-1857 | CLIP_FP32_CAST_ONCE=1 (off both profiles) | N | N | Y(within FH/spec lanes) | Y(E31 arms) | after source tensors, before bind | within owning lane | cast marker/generation | none extra | FP32 allocs | verify residency | retire owners after proof :1851-1862; reset :1872-1884 | outer cleanup→native | cast evidence | test_e31_clip_forward_fp32 | E31 forward profile | BO (diagnostic transform) |
| Staged safetensors (CLIP) | wiring:2490-2700; staged_safetensors.py | STAGED_HYDRATION=1 | N | N | Y | Y(C12 era) | after meta/CPU recon | staged buffers | _comfymodal_clip_fh_staged_owner :1818-1870 | staged prepare/commit | staged H2D | commit sync | staged owner close | native/fastsafe | staged metrics | unk | unk | Q |
| Source-order transport | source_order_safetensors.py | STAGED_SOURCE_ORDER=1 | N | N | Y | Y | ordering policy only | — | staged owner | ordering | N | N | staged owner | staged/native | order metrics | unk | unk | Q |
| CPU snapshot CLIP restore | cpu_snapshot_models.py (see 4B) | CPU_MODEL_SNAPSHOT=1 | Y | Y | N | N | precedes hydration | capture-time | snapshot registry | volume read | retarget | validator | snapshot mgr | hydration/native | validator events | e28/e30 tests | shape/device | AC (stage 1) |
| Meta/assign bind mechanism | wiring:1696-1705,1789-1800 | when meta placeholders present | Y | Y | Y | N | after structure restore | N | hydration owner | none | assign=True CUDA storage | post-bind checks | owning loader | native if bind fails | meta-reject guards | e30 tests | residency checks | MC (mechanism, not algorithm) |
| ModelPreloadCoordinator preload | model_preload.py (CLIP ref :4022); observed modal_app.py:6751-6766 | MODEL_PRELOAD/prefill (prod: not explicitly enabled; E37: 0) | N | cond | Y | Y | precedes demand | worker pool | coordinator._active | file reads | none proven | future join | coordinator join | demand path | active-read telemetry | unk | unk | MC behind lease |
| _ACTIVE_MODEL_READS registry | comfyapp.py:4961-4964,5024-5226 | always (when reads registered) | Y | Y | — | — | dedup/coalesce | lock-guarded | global dict + RLock + fuse cond | none | N | cond var | entry removal | duplicate adoption | [preload_model_read_*] logs | unk | n/a | MC behind lease |
| _LANES | speculative_clip_hydration.py:64,504-525 | speculative enabled | suppressed | self-skipped | Y | Y | lane lifetime | background | lane dict | none | N | joins | remove/cancel :973-1020 | n/a | skip/join events | e25/e26 tests | n/a | Q with speculative |
| _STATES (gpu_lane_coordination) | gpu_lane_coordination.py:85,244-264,339-374,702-717 | CRITICAL_GPU_COORDINATION=1 (e29-tracer:21 → E37 inherits) | Y | Y(inh? see §11) | — | — | request-scoped | yes | _RequestState (clip_owner_tid, depth) | none | N | critical section | pop/clear + bounded eviction :252-263 | n/a | coordination events | unk | n/a | MC (single critical-section authority) |
| local_handle caches | local_handle_owner.py:145-202 | persistent transport | Y | Y | — | — | cross-request | N | _client/_handle/_queue caches | remote calls | N | N | stale invalidation :182-202 | re-resolve | retry logs | unk | n/a | MC behind request lifecycle |

### 4D. UNET + VAE (G, H)

| Implementation | Source | Gate/default | E37 | Prod | FB | BENCH | After | Concurrent | Owner/state | Src I/O | GPU | Sync | Cleanup authority | Fallback→ | Telemetry | Tests | Exact-output | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CPU snapshot UNET restore | cpu_snapshot_models.py:1234-1266 | CPU_MODEL_SNAPSHOT=1 | Y(inh) | Y | N | N | stage 1 | capture-time | snapshot registry | volume read | later activation | validator | snapshot mgr | demand load | validator | e28/e30 | shape/device | AC (stage 1) |
| Native fast-disk UNET | flag_registry:319-325; comfyapp.py:1282-1291; model_preload replay | NATIVE_FAST_DISK_UNET=1 (prod) ; E37 inherits | Y(inh) | **Y(selected)** | N | N | after snapshot miss | internal workers | patcher/model-mgmt | file-backed reads | native transfer | internal | Comfy patcher | generic demand | loader logs | e19/e28 gates | expected SHA | AC |
| UNET fastsafetensors | unet_fastsafetensors.py:27,531-631 | UNET_FASTSAFETENSORS=1 (prod+E37 OFF) | N | N | Y | Y(C9-E28 era) | alt-arm | direct file→CUDA | _comfymodal_fastsafe_owner | fastsafe reads | meta + assign=True | internal | owner close then caller | normal/native :531-571 | fastsafe states | e28 suite | A/B era | Q (keep as capability) |
| Staged transport (UNET) | unet_fastsafetensors.py:163-367; staged_safetensors.py | STAGED_SAFETENSORS=1 | unk | unk | Y | Y | after plan | staged bufs | _StagedOwner | staged IO | commit | commit sync | staged close | fastsafe/native | staged metrics | unk | unk | Q |
| Pinned staging (UNET) | unet_pinned_staging.py:43-215; model_preload._fast_disk_replay_to | caller-selected | component | component | Y(fallback transport) | Y | after direct unsupported | stream+events | staging buffers | pinned CPU | stream H2D | events+synchronize | local bufs | cuda_unavailable/non_contiguous/exception paths | probe metrics | unk | unk | RF (transport fallback) |
| Meta-direct (UNET) | model_preload.py:329-452; unet_meta_direct.py | header/meta derivation | component | component | Y | Y | before transfer | N | patcher/native | header read | to_empty/meta | internal | native owner | native loader | unk | unk | unk | MC (mechanism) |
| Checkpoint prewarm | checkpoint_prewarm.py:345-488,606-768 | CHECKPOINT_PREWARM (E37:0; prod:0; e29-tracer:1 overridden) | N | N | Y | Y | before demand; fenced | reader workers | telemetry only | bounded reads | none | stop/join before demand :before_demand_load | workers joined | non-blocking failure | prewarm telemetry | e12-era tests | n/a | BO (page prewarm) |
| Generic Comfy demand (UNET) | comfyapp.py:15854-15867,16312,16898-16982; model_preload.py:4142-4946 | graph-driven; ALWAYS reachable | Y | Y | Y | N | **Y after custom success** | Comfy-managed | current_loaded_models | possible reread (unk) | patcher H2D | Comfy-internal | Comfy machinery | Comfy internal | profiler wrappers | Comfy-side | expected SHA | RF (guarded activation boundary) |
| Cold UNET early-load | comfyapp.py:1282-1289 | COLD_UNET_EARLY_LOAD_MODE | N | cond | Y | Y | speculative reads NOT joined by graph loader (docstring) | early workers | early-load budget | independent reads | none direct | budget ms | early workers | graph loader | early-load logs | unk | unk | Q (unjoined double-pay) |
| UNET probes (qd/salvage/forward/backing) | unet_*_probe.py, unet_backing.py | explicit probes | N | N | N | Y | N | probe-local | probe objs | probe reads | probe H2D | probe sync | probe-local | named skips | probe outputs | probe tests | measurements | BO |
| VAE snapshot retention | cpu_snapshot_models.py:86-104,1080-1090,1306+ | CPU_MODEL_SNAPSHOT+VAE_SNAPSHOT | Y(inh) | Y | N | N | stage 1 | capture-time | snapshot registry | volume read | late activation | validator | snapshot mgr | native VAELoader | spec validation | e28/e30 | shape/device | AC |
| VAE page prefetch | cpu_snapshot_models.py:768-812 | prefetch policy | cond | cond | N | N | before activation | madvise | registry-local | page hints | none | none | registry | n/a | prefetch metrics | unk | n/a | KEEP (prep, not load) |
| Native VAELoader transition | cpu_snapshot_models.py:1080-1090; gpu_snapshot_shadow.py:1203 ref | VAE use / late mode | Y | Y | Y(on snapshot miss) | N | after UNET event | model-mgmt | patcher | file read | H2D | model-mgmt | Comfy | n/a | stage timings | Comfy-side | expected SHA | RF |
| Late activation + UNET wait | comfyapp.py:1458-1484; wait body :1595-1654 | VAE_ACTIVATION_MODE=late | Y(inh) | Y | N | N | after UNET completion event | event-gated | event owner = UNET load | none | activation H2D | event wait — **fail-open on timeout** (oracle-verified) | UNET-load owner | proceed on timeout | wait logs | unk | n/a | MC (make fail-closed decision explicit) |
| Early VAE read/pre-copy | comfyapp.py:1458-1484 defer path | restore-background flags | cond | cond | Y | Y | before late activation | background | coord owner | early reads | none | coord events | coord owner | deferred native | defer logs | unk | unk | SUPPORTED RISK → Q candidate |

### 4E. Comfy integration, prep, cache, timing, artifacts, cleanup (I–N)

| Implementation | Source | Gate/default | E37 | Prod | FB | BENCH | After | Concurrent | Owner/state | Emits into | Duplicate-bookkeeping risk | Cleanup/uninstall | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| model-management profiler loop | comfyapp.py:15854-15899 | profiling setup; sentinel _model_management_profile_patched | cond | cond | — | diag | wraps others | N | module flag | _log_profile(model_mgmt) | HIGH (layer 1 of 2) | none shown | Q (merge into one boundary) |
| separate profiled load_models_gpu | comfyapp.py:16898-16982 | profile/diag conditions; saves _orig_lmg locally | cond | cond | — | diag | wraps layer 1 or original | N | local _orig_lmg | loader diagnostics | HIGH (layer 2 of 2; no cross-layer idempotence) | none shown | Q |
| ModelPatcher profiler | comfyapp.py:15791-15815 | profiling setup | cond | cond | — | diag | wraps clone/patch/unpatch | N | sentinel | model_clone timings | MED (stacks w/ :21997) | none | Q |
| clone cache tracing | comfyapp.py:21997-21998 | diag/cache flags | cond | cond | — | diag | second clone wrap | N | tracing ctx | cache diagnostics | MED | none | Q |
| high-VRAM offload patch | comfyapp.py:15903-15931 | _offload_devices_patched; HIGH_VRAM only | cond | cond | — | diag | device fns | N | sentinel | none | LOW | none | CO |
| cold-path forensics stack | clip_cold_path_forensics.py:868-1083 | install(); per-target sentinels; skips model-preload core targets :881-905 | off (not enabled in E37 profile) | off | — | diag | designed anti-nesting | N | sentinels | clip_cold_* + runtime trace | LOW (disciplined) | **uninstall() restores originals reverse order :1072-1083** | BO (reference discipline) |
| CLIP demand hydration wrapper | clip_fast_hydration.py:1629-1660; wiring:2917+ | flags+frozen manifest | Y(armed) | N(FH off) | Y | Y | instance-level; resolves method at call time | N | hydration state | hydration records | MED (can nest encode/prefetch wrappers) | documented idempotent install | MC behind ClipLoader |
| cast forensics | clip_forward_forensics.py:673-1078 | E31 flags (off) | N | N | — | diag | cast ops | N | evidence guard | cast evidence | unk coexistence | evidence reset only | BO |
| scheduler/encode prefetch patch | comfyapp.py:14298+ | prefetch config | cond | cond | — | diag | encode path | N | prefetch state | prefetch timing | MED (same physical encode) | none identified | Q-candidate review |
| VAE/UNET/CLIP loader cache patches | comfyapp.py:19404+,19811+,20151+ | cache flags | cond | cond | — | diag | loader nodes | N | caches | cache diagnostics | unk | none identified | U |
| ExecutionPlan build/consume | canonical_execution.py:1466-1718; contracts.py:1003-1074,1267-1364 | always | Y | Y | N | N | once per build; runtime deserializes | N | frozen plan | plan hashes | LOW (immutable) | n/a | AC |
| Seed topology/signatures | execution_seed.py:375-447 | seed build | Y | Y | N | N | recomputed on rebuild | N | seed payload | schema markers | SUPPORTED RISK (rebuild repeats) | n/a | MC (reuse-first) |
| INPUT_TYPES warm | production.toml:55; comfyapp.py:827,946; modal_app refs | prod=1; E37=0 | N | Y | N | N | warm + execution introspection | N | warm state | warm timings | SUPPORTED RISK (warm+exec dup) | n/a | MC |
| pre_graph_cache / prompt_signature_cache | pre_graph_cache.py; prompt_signature_cache.py; runtime_executor.py:2412-2425 | PROMPT_SIGNATURE_CACHE env | cond | cond | N | N | memoize prep | N | caches | hit/miss logs | intended dedup | n/a | MC |
| registry proof consumption | canonical_execution.py:1315-1368; registry_proof.py:233+ | plan validation | Y | Y | N | N | store-hit avoids manifests; miss rebuilds | N | proof store | parity gates | CONFIRMED conditional reread | n/a | AC |
| conditioning cache | clip_conditioning_cache.py (key :260-317; lookup :1847-1896; queue :2097-2144; worker :2250-2292) | flag; forced_miss in E37 workload (e29-tracer:9) | forced-miss | Y | miss=fail-closed | N | after encode | persistence worker | manifest+blob LRU | none | checksummed reuse | worker drain :2250-2287 | AC |
| critical_path_ledger | critical_path_ledger.py | LEDGER=1 (E37 via tracer) | Y | cond | — | — | seam emission | N | ledger intervals | waterfall/gantt | representation only | n/a | AC (representation) |
| v2_waterfall / gantt_canonical / gantt_telemetry | respective modules | env gates | Y(E37) | cond | — | — | reconcile/render | N | derived docs | reports | visualization only | n/a | KEEP as renderers |
| full_execution_trace(+report) | full_execution_trace.py; full_trace_report.py | trace gates | diag | diag | — | Y | event capture | N | trace files | CSV/MD reports | forensic only | n/a | BO |
| resource/host/stage13/thread/wait/variance/opt/sampling/teardown diagnostics | respective modules | env gates | diag | diag | — | Y | sampling/counters | N | samples | reports | diagnostic only | n/a | BO |
| validation.py StructuralValidator | tools/v2_control/validation.py:6-20,165-260 | v2ctl gates | Y | Y | N | N | gate→confirm | N | GateResult | verdict | **sole acceptance authority** | n/a | AC |
| DirectOutputSink | output_delivery.py:1-9 | production delivery | Y | Y | N | N | in-request | N | memory registry | asset descriptors | canonical | request end | AC |
| structured selector | result_delivery.py:183-234,245-286 | materialization | Y | Y | N | N | deterministic | N | selection | artifact write | preference order documented | unique_path :87-108 | AC |
| history/mtime scans | comfyapp.py:3179,16598,17214-17226 | legacy/history paths | legacy | legacy | Y | Y | scan-time | N | fs order | reads | older-artifact risk | n/a | Q (never production authority) |
| CommitCoordinator | runtime_state.py:314; users modal_app.py:20257,20345; restore_plan.py:53-59 | volume commits | Y | Y | N | N | serialized | N | volume lock | none | single commit authority | drain semantics | AC |
| conditioning persistence worker | clip_conditioning_cache.py:2250-2292 | cache enabled | off(E37 persist=0) | Y | N | N | background | N | queue+manifest | volume writes | coalesced commit | drain on close | AC |
| GPU release set | Comfy free_memory/soft_empty_cache + teardown_diagnostics + single-use exit + CUDA syncs (clip_cold_path_forensics.py:763; comfyapp.py:15365) | mode-dependent | Y | Y | — | — | post-request | overlaps | distributed | teardown timings | **3 overlapping authorities** | mode-specific | MC (single teardown policy) |

---

## 5. CLIP exact dispatch tree (entry → ready publication)

```text
request/plan execution
  -> restore/snapshot reconstruction
       CPU_MODEL_SNAPSHOT?
         yes -> CpuSnapshotModels restore (structure+CPU values)
                  CLIP weights excluded (EXCLUDE_WEIGHTS)? -> CLIP left weightless; marker tolerated (cpu_snapshot_models.py:1287)
         no  -> continue
       ModelPreloadCoordinator active? -> background preload/read (join later)          [model_preload.py]
       SPECULATIVE launch at restore?
         clean_lane.enabled()? -> SUPPRESSED, emit clean_lane_restore_launch_suppressed  [speculative_clip_hydration.py:1094-1104]
         else SPECULATIVE=1 and clip_fast_hydration_enabled()?
           yes -> start lane (_LANES[_RESTORE_TIME_KEY]); early read via FastSafe-or-QD arm
           no  -> skip("clip_fast_hydration_disabled")                                  [:428-430]
  -> CLIP demand hydration (_try_fast_hydrate)
       try take speculative result [wiring:1260-1317]
         completed+valid  -> use its (sd, owners); NO second source read
         in-flight        -> join <=20s; valid->use; failed/timeout->close its owners [1621-1631], continue
       CLEAN_LANE and no speculative taken? [wiring:1319-1435]
         QD enabled AND QD==4 AND manifest/files valid
           -> synchronous clip_qd_load per file (header pread, qd workers, pinned qd*2 blocks,
              contiguous CUDA buffer, async H2D, completion events)
           -> transform + manifest verify + quiescence REQUIRED (clean_lane.mark_qd_ready)
           -> ANY failure => CLEAN_LANE FAILURE (no FastSafe fallback)                 [:1430-1442]
       ordinary demand (no accepted speculative/QD) [wiring:1632-1688]
         CLIP_FAST_HYDRATION? yes -> _fastsafe_load per file (+optional E31 cast-once)
                              no  -> return {mode:"native", ok:false}                   [:2042-2048]
                                -> NATIVE Comfy CLIP load (production default arm)
       bind [wiring:1695-1726]
         hydrate_clip_bind(assign=True) onto meta/weightless structure
         scoped copy-event wait OR device-wide torch.cuda.synchronize()
         -> device-ready publication
       E31 enabled? -> verify resident FP32 non-meta; forward hook; mark generation;
                       retire source owners only after proof [:1851-1862]
       else -> attach owners to CLIP/patcher (_comfymodal_clip_fh_owner / QdGpuOwner views)
       any outer FastSafe failure -> reset markers; _close_source_owners [:2004-2024];
                                     torch.cuda.empty_cache(); mode=native -> native Comfy load
  -> final ready proof: loader_arm published exclusively qd_demand | qd_speculative | fastsafe
     [:1740-1745]; clean lane additionally requires 240/240 block reconciliation + QD4 quiescence
```

**QD vs FastSafe composition verdict — CONFIRMED:** alternatives for one load (drop-in contract `clip_qd_reader.py:1886-1901`; mutually exclusive branches; exclusive loader_arm publication). They compose only at orchestration boundaries: speculative lane may execute either arm (`mode: "QD4" if clean_lane.enabled() else MODE_FASTSAFE`, `speculative_clip_hydration.py:614,802`); rejected speculative → FastSafe loop; clean-lane QD failure → fail-closed.

## 6. UNET exact dispatch tree

```text
request
  -> CPU_MODEL_SNAPSHOT?
       valid UNET snapshot -> publish CPU-resident UNET/patcher -> await activation
       missing/invalid     -> file/native loading continues
  -> CHECKPOINT_PREWARM? (bounded byte reads; fenced; stops/joins workers before demand)
  -> activation (late mode)
       UNET_FASTSAFETENSORS?
         yes -> meta model + direct file-to-CUDA + assign; retain _comfymodal_fastsafe_owner
                failure -> release fastsafe resources -> normal/native path            [:531-571]
         no  (prod+E37)
       STAGED_SAFETENSORS? -> plan/prepare/commit; _StagedOwner; failure -> fallback
       NATIVE_FAST_DISK_UNET (prod selected)
         -> native fast-disk replay; internals may use pinned staging (events+synchronize)
            and/or meta-direct construction (exact internal ordering: UNKNOWN from audited files;
            dispatcher lives in model_preload/_fast_disk_replay_to)
       -> generic Comfy demand path (ALWAYS reachable)
            load_models_gpu wrapper boundary (model_preload.py:4347 "Authoritative ... entry")
            -> current_loaded_models walk; ModelPatcher.load bookkeeping RE-RUNS after
               custom success (docstring :4142+); quota/free-memory logic
            -> publish model-ready
  -> ready proof: patcher loaded state + stage timings
```

**Key confirmed behavior:** custom-loader success does NOT prove the generic path is skipped; at minimum a second bookkeeping/repatch phase occurs. Whether a full second payload read happens depends on `current_loaded_models` identity at runtime (SUPPORTED INFERENCE, not proven per-request). Cold UNET early-load reads are explicitly "NOT joined by the graph loader" (`comfyapp.py:1282-1289`) — a confirmed independent-read path when enabled.

## 7. VAE exact dispatch tree

```text
request
  -> CPU_MODEL_SNAPSHOT + VAE_SNAPSHOT?
       valid retained VAE -> retain CPU representation; validator checks shapes/devices
       no valid retained  -> native VAELoader file path
  -> optional CPU page prefetch (madvise; no Torch/CUDA)
  -> VAE_ACTIVATION_MODE=late (prod)
       UNET background load active? -> wait on UNET completion event (comfyapp.py:1458-1484)
          WAIT IS FAIL-OPEN ON TIMEOUT (comfyapp.py:1595-1654): proceeding is allowed,
          so "waited" != "serialized safely"   [oracle-verified correction]
       -> native model-management transition (load_models_gpu([vae.patcher]))
       -> VAE ready for decode
  -> decode via normal Comfy node execution (no confirmed decode monkey-patch found)
  -> cleanup via shared GPU-release set (see §15/N)
```

The V2_BATCH_D18 "VAE soft-empty-cache gate" symbol was **not located** in current source (UNKNOWN whether implemented/renamed).

## 8. Ownership/lifecycle conflict graph

Registries (claim/publish/bind/release):

```text
_ACTIVE_MODEL_READS (comfyapp.py:4961)      claim: any registered model read (dedup/coalesce)
  └─ keys: canonical model cache key -> {owner: "restore_clip_loader"|"restore_preload"|...}
_LANES (speculative_clip_hydration.py:64)   claim: speculative early read; release: cancel/cleanup :973-1020
_STATES (gpu_lane_coordination.py:85)       claim: request CLIP critical section (owner_tid, depth);
                                            release: end_clip_critical/pop :702-717; eviction :252-263
ModelPreloadCoordinator._active             claim: preload futures; observe: modal_app.py:6751-6766
QdGpuOwner (clip_qd_reader.py:1344-1399)    claim: QD GPU storage; release: close/release_storage;
                                            SECOND AUTHORITY: facade close :1853-1879 (idempotent, but dual)
FastSafe owners (clip_fast_hydration.py:653,865-870,1689-1870)
                                            claim: source loader + patcher-attached lists; retire :1851-1862 wiring
current_loaded_models (Comfy core)          UNOBSERVABLE here; native residency/bookkeeping authority
local_handle_owner caches (:145-202)        Modal handles (not tensors); stale-invalidation :182-202
```

Per-model lifecycle highlights:
- **CLIP**: claimants = snapshot manager, preload coordinator, speculative lane, demand hydrator; ready-publishers = bind seam (`wiring:1695-1726`) or native Comfy; binders = `hydrate_clip_bind(assign=True)`; releasers = owner close + facade + patcher attr deletion (`:1796,1870`) — **three release surfaces**; fallback trigger = any arm failure → native.
- **UNET**: claimants = snapshot, native fast-disk replay, fastsafe, early-load; publishers = load_models_gpu boundary; releasers = Comfy machinery (+early workers); risk = generic path re-running bookkeeping after custom success.
- **VAE**: claimants = snapshot/native loader; publisher = late activation after UNET event (fail-open); releasers = shared GPU-release set.

Owner-key literal census (all found literals):
| Literal | Produced at | Consumed at | Verdict |
|---|---|---|---|
| `restore_clip_loader` | comfyapp.py:11858 (role map "clip") | — no matching consumer check found | **MISMATCHED PRODUCER KEY** |
| `restore_preload` | comfyapp.py:11861 (default role), :11934,:11945 registrations | comfyapp.py:12323 preflight equality check | consumer matches only non-CLIP roles → **CONFIRMED mismatch for CLIP** (scope: this preflight waiter; `_load_one` adoption and `ModelPreloadCoordinator.wait_clip()` provide other wait paths — oracle nuance) |
| `CLIP` | model_preload.py:4022 | preload telemetry | distinct namespace; potential mismatch with restore keys |
| `clip_qd_reader` | clean_lane.py:140,178 | clean-lane proof | consistent |
| `graph_loader` | seen in logs; producer not found in targeted grep | active-read telemetry | UNKNOWN producer |
| `fastsafetensors_buf` | wiring:1936 | descriptive owner_mode | not an active-read key |
| `_clip_fh_fastsafe_owner` / `_comfymodal_clip_fh_owner` / `_comfymodal_clip_fh_staged_owner` | clip_fast_hydration.py:80,653,865-866 | patcher attrs | internally consistent |
| `CLIP_GPU_CRITICAL_ACTIVE` | gpu_lane_coordination.py:16,237,366 | coordination label | not storage ownership |

Stale-global risks: `_ACTIVE_MODEL_READS`, `_LANES`, `_STATES`, handle caches are process globals surviving across requests in warm containers; bounded cleanup exists (`gpu_lane_coordination.py:252-263,702-717`; speculative `:973-1020`) but global impossibility of staleness is not proven.

## 9. Monkey-patch stack

Inventory with install order/guards is in Matrix 4E. Effective stacks:

**E37 clean lane (effective env = production ← e29-tracer ← e37 overrides):**
```text
import-time: module-level env reads bake behavior
restore:    clean_lane.begin_request; speculative launch SUPPRESSED (:1094)
request:    PromptExecutor -> loader node
              [maybe] comfyapp model-management profiler layer(s) IF profiling setup ran
              -> model_preload authoritative load_models_gpu boundary (:4347)
              -> Comfy model_management.load_models_gpu (native)
            CLIP load_model -> demand hydration wrapper -> CLEAN-LANE synchronous QD4 branch
            CLIP encode -> normal encode (+prefetch wrapper if installed)
            sampler -> normal Comfy sampler (no confirmed patch)
            VAE decode -> normal node (no confirmed patch)
            output -> normal
teardown:   minimal (BACKGROUND_*/ALLOCATOR_PURGE=0); single-use container exit
UNKNOWN: whether both comfyapp load_models_gpu profiler layers were installed in the E37
run — they are conditionally installed at runtime setup; nesting would make telemetry show
nested spans around ONE physical call.
```

**Production:**
```text
request: plan consumed (from_dict) -> INPUT_TYPES warm (prod=1) -> restore/snapshot activation
         -> PromptExecutor -> loader node
            -> native fast-disk UNET route (snapshot first)
            -> load_models_gpu [profiler layer(s)?] -> GPU-fast-return branch where eligible
         -> CLIP: snapshot-restored structure -> native Comfy demand load (FH off)
            -> conditioning cache lookup (hit: reuse CPU conditioning; miss: encode+store-enqueue)
         -> sampler -> VAE late activation (UNET event wait, fail-open) -> decode -> output
         -> release-GPU-after-request (free_memory/soft_empty_cache + teardown diagnostics)
```

Negative finding (bounded): no independently verified direct patches of sampler, VAE `decode`, or output-node methods in inspected locations (UNKNOWN beyond inspected range).

## 10. Double-pay / half-integration findings

| # | Candidate | Classification | Evidence |
|---|---|---|---|
| 1 | Cold UNET early-load reads vs graph loader | **CONFIRMED DOUBLE PAY** (when mode enabled) | comfyapp.py:1282-1289 docstring: reads "are NOT joined by the graph loader" |
| 2 | Generic `load_models_gpu` after custom UNET success | **CONFIRMED (bookkeeping level)**; full byte reread = SUPPORTED INFERENCE | model_preload.py docstring "re-runs ComfyUI's ModelPatcher.load bookkeeping" (:4142+); boundary :4347 |
| 3 | Producer `restore_clip_loader` vs consumer `restore_preload` | **CONFIRMED MISMATCH**; duplicate-read outcome = SUPPORTED RISK | comfyapp.py:11858 vs :12323; other wait paths partially compensate |
| 4 | Rejected speculative read → FastSafe reread | NECESSARY SECOND STAGE | owners closed first (wiring:1621-1631); manifest validation requires authoritative retry |
| 5 | Speculative join consuming in-flight read | NOT DUPLICATE | wiring:1290-1304 |
| 6 | QD vs FastSafe same load | NOT DUPLICATE (exclusive arms) | §5 verdict |
| 7 | QD owner + facade dual close | SUPPORTED RISK (two release authorities; idempotent) | clip_qd_reader.py:1344-1399 vs :1853-1879 |
| 8 | E31 FP32 cast after BF16 hydration | NECESSARY SECOND STAGE (intentional transform) | wiring:1661-1683; retire-after-proof :1851-1862 |
| 9 | Zero-copy QD views retained until bind+attach | NECESSARY SECOND STAGE (lifetime requirement) | clip_qd_reader.py:1347-1350 |
| 10 | Snapshot CPU CLIP values + later hydration | NECESSARY SECOND STAGE when weights retained; NOT DUPLICATE otherwise; with EXCLUDE_WEIGHTS the hydration is the intended completion | cpu_snapshot_models.py:1287 marker tolerance |
| 11 | Preload-coordinator read + demand read | SUPPORTED RISK (separate lifecycles; dedup incomplete for CLIP per #3) | model_preload.py; comfyapp.py:12309-12342 |
| 12 | Early VAE read/pre-copy + late activation | SUPPORTED RISK | comfyapp.py:1458-1484 defer path |
| 13 | Warm INPUT_TYPES + execution introspection | SUPPORTED RISK | prod enables warm; normal nodes still introspect |
| 14 | Seed/topology/signature recompute on runtime rebuild | SUPPORTED RISK | execution_seed.py:392-430 computed per build |
| 15 | Registry-proof miss rebuilding manifests | CONFIRMED conditional reread (by design on stale anchor) | canonical_execution.py:1315-1368 |
| 16 | Cache-hit proof recomputing cached value | NOT ESTABLISHED — key includes identities, not tensor recompute | clip_conditioning_cache.py:260-317 |
| 17 | Custom owner ready + Comfy walking/repatching anyway | CONFIRMED at bookkeeping level (#2) | model_preload.py:4142+ |
| 18 | Post-durable persistence duplicated by another finalizer | NOT FOUND as duplication; CommitCoordinator is single Volume authority; cache worker has own coalesced commit (separate volume/domain) | runtime_state.py:314; clip_conditioning_cache.py:2250-2292 |
| 19 | Filler/warmup polluting conditioning cache | UNKNOWN (nonce isolates benchmarks; filler exclusion unproven) | cache nonce :269-312 |
| 20 | Deployment identity known but manifests reread to prove | CONFIRMED conditional (#15) | registry_proof_store anchor semantics |

## 11. Configuration truth-system conflicts

Chain (per important flag): `profile value → inheritance → selector projection (--inherit/--set) → ResolvedConfig → deploy flags → baked container env → runtime direct os.environ read → actual branch → artifact-observed value`.

**CONFIRMED two-truth-system cases (direct runtime read without full registry mediation):** `COMFYMODAL_APP_NAME` (legacy fallback :377), `COMFYMODAL_REQUIREMENTS_REPAIR_MODE`, `COMFYMODAL_LOCAL_CUSTOM_NODES`, `COMFYMODAL_EXECUTION_BACKEND` (default `in_process` :357), `COMFYMODAL_CUSTOM_NODE_*`, `COMFYMODAL_PRELOAD_*` (:1220-1273), `COMFYMODAL_WARMUP_*` (:1246-1253), `PROMPT_PRELOAD_WORKERS`, `ACTUAL_LOAD_MODE` fallback (:1334-1336), `COMFYMODAL_SAGE_RUNTIME_MODE`, `COMFYMODAL_RESTORE_DIRECT_CLIP_POLICY`, `COMFYMODAL_SAFETENSORS_*`, `COMFYMODAL_FUSE_LARGE_READ_*`, `COMFYMODAL_VOLUME_STALL_*`, `COMFYMODAL_PLATFORM_OUTLIER_THRESHOLD_MS`, `COMFYUI_MANAGER_MODE/NETWORK_MODE` (:6129-6130), `COMFYMODAL_MODEL_DOWNLOAD_MODE`, `COMFYMODAL_LOCAL_HANDLE_*`, dynamic `COMFYMODAL_<name>` alias (:3455,3478).

**Flag-by-flag effective values (E37-clean-lane vs production vs registry default):**

| Flag | E37 clean lane | Production | Registry default |
|---|---|---|---|
| ENV_PROFILE | inherit-chain value | production | production |
| CLIP_CONDITIONING_CACHE | inherited (workload forces miss) | 1 | 1 |
| GPU_FAST_RETURN | 0 | 1 | 1 |
| INPUT_TYPES_WARM | 0 | 1 | 1 |
| CLIP_FAST_HYDRATION | 1 | 0 | 0 |
| CLIP_QD_READER | 1 | absent→0 | 0 |
| CLIP_QD_LAUNCH_POLICY | clean_lane_post_restore | restore_earliest | restore_earliest |
| CLIP_FP32_CAST_ONCE | 0 | 0 | 0 |
| E31_FORENSICS | 0 | 0 | 0 |
| E37_STRICT_PROOF / E37_CLEAN_LANE / CLEAN_LANE | 1 | absent→0 | 0 |
| BATCH_C_EXPECT_PLAN_FAST_PATH | 1 | absent→0 | 0 |
| MINIMAL_RESTORE | 1 | absent→1 | 1 |
| CHECKPOINT_PREWARM | 0 (overrides tracer's 1) | 0 | 0 |
| SPECULATIVE_CLIP_HYDRATION | **1 (inherited from e29-tracer:35; suppressed at runtime)** | absent → **read-site default "1"** (modal_app.py:3257; speculative:435) but self-skips since FH=0 | (read-site default 1) |
| CRITICAL_GPU_COORDINATION | 1 (tracer:21) | absent | — |
| SINGLE_USE_CONTAINERS | 1 (tracer:65) | absent | — |
| UNET_FASTSAFETENSORS | 0 (explicit :30) | 0 | 0 |
| NATIVE_FAST_DISK_UNET | inherited 1 (via production) | 1 | — |
| CPU_MODEL_SNAPSHOT / VAE snapshot | inherited 1 | 1 | — |
| VAE_ACTIVATION_MODE | late (tracer:37) | late | — |
| MODEL_PRELOAD / GRAPH_PRELOAD / EXECUTION_PREFILL / PREFILL_LANES | 0/none | absent | — |
| EXACT_CACHE_PERSIST / BACKGROUND_PERSISTENCE / BACKGROUND_DIAGNOSTICS / ALLOCATOR_PURGE | 0 | absent | — |

**Ultimate authority (CONFIRMED):** the **container process environment**, populated at deploy time (registry classifies these as deploy-baked, `flag_registry.toml:196-205`); `ResolvedConfig`/profiles only project into it. Post-resolution rewrite of `ResolvedConfig` itself: none found; projection/supersede happens via backend env emission, runtime-overrides file channel (policy `forbid` default), and benchmark harness child-env mutation (`benchmark_modal_e2e.py:1556-1570`).

**Armed-but-suppressed pattern (E39-critical):** `SPECULATIVE_CLIP_HYDRATION` is inherited `1` in the clean lane and defaults to `1` at read sites; correctness depends on runtime gates (`clean_lane.enabled()` at launch :1094; `clip_fast_hydration_enabled()` hard gate :428). Any change to those gates silently re-activates the lane inside "clean" runs.

## 12. Deployment/source identity conflicts

Four explicit answers (evidence in §3C):
1. **Can two systems say "same deployment" hashing different sets? YES** — source_probe (8 files) vs deployment_spec (all allowed sources) vs registry proof (workflow classes only) vs v2ctl fingerprints (git+config, no source).
2. **Can one change without another? YES** — resource/profile/thread changes move fingerprints/runtime_shape without source change; a change to a non-probed module moves deployment_spec but not source_probe.
3. **Can generated files affect one but not another? YES** — dirty-state hashes and artifact SHAs include generated content; deployment_spec excludes generated prefixes by hard-coded policy; `.modalignore` excludes even more (upload scope) and is read by **none** of the validators.
4. **Can a cache accept data a validator would reject? YES in principle** — registry_proof_store accepts on its deploy-frozen anchor + class proof while canonical source/probe could reject the current tree; D1 tests prove stale-anchor rejection only for that store (`test_v2_d1_stale_identity.py:179-240`), not cross-identity agreement.

Nuance (oracle): multiple hashes are not inherently wrong — the defect is **treating them as interchangeable deployment identity**.

## 13. Timing/validation truth-system conflicts

- **Acceptance authority (CONFIRMED):** `tools/v2_control/validation.py` `StructuralValidator` — fail-closed on missing artifacts/IDs/provenance/fresh identity/output SHA/config proof (`:165-260`); protocol = one gate run + confirmation only after gate validity (`:6-20`).
- **Authoritative timing representation:** `critical_path_ledger` (+ canonical Gantt as renderer). Not an acceptance decider.
- **Independent PASS/FAIL emitters:** `batch_c_acceptance.py` (campaign-scoped) can report pass/fail independently of the v2ctl gate; individual telemetry modules do not share a universal PASS/FAIL field.
- **Field overwrite risk:** UNKNOWN whether any result-assembly path overwrites summary timing fields after validation (would require exhaustive result-path tracing).
- **Should survive canonicalization:** ledger + canonical Gantt (representation), StructuralValidator (decision), restore-boundary parser (evidence, never guesses). Everything else is diagnostic/visualization.

## 14. Control-plane conflicts

Canonical target (CONFIRMED): app `stable-modal-comfy-v2-restore-only-shadow`, class `ModalRuntimeEntrypointV2`, method `run_plan_stream` (`production.toml:8-11`; `modal_app.py:17762`). ~20 launch families exist (§4A); only v2ctl+BAT pair and `benchmark_v2_direct.py` are production-adjacent; the rest are benchmark/experiment variants duplicating deploy+run logic. The BAT probe-path fallback (without `V2_E28_VALIDATION=1` the run BAT uses `run_snapshot_restore_only_probe`, which never invokes `run_plan_stream` — `e29-tracer.toml:24-27`) is a silent-mode hazard.

## 15. Artifact-selection conflicts

- Canonical: `DirectOutputSink` (production registry strategy, `output_delivery.py:1-9`) + deterministic structured selector (`result_delivery.py:183-234`: side-b → b_images → primary → images → side-a → first; full-result `:245-286` structured-first with flat fallback).
- Fallback collectors: HistoryOutputCollector, RequestBoundFilesystemCollector, SubprocessOutputCollector.
- **mtime-based selection remains in legacy/history/certificate paths** (`comfyapp.py:3179,16598,17214-17226`) — an older artifact can win wherever scans are not invocation-bound (CONFIRMED presence; production exposure limited to those paths).
- `unique_path` UUID suffix prevents local overwrite collisions (`result_delivery.py:87-108`).

## 16. Dead vs legacy vs fallback vs benchmark-only reachability

- **Dead/no current reference found:** deleted `e31-clip-fp32.toml` (no scoped references); `graph_loader` owner-key producer (unlocated).
- **Legacy (present, production-adjacent but superseded):** `benchmark_modal*.py` harness family; mtime artifact scans; `run_prompt_stream`/compatibility prompt path; dynamic `COMFYMODAL_<name>` alias lookup.
- **Fallback-only:** native Comfy CLIP demand (behind custom arms), FastSafe loop (behind speculative/QD in clean contexts; default arm in production), staged transports, pinned staging, native VAELoader on snapshot miss, generic Comfy UNET demand.
- **Benchmark/diagnostic-only:** E30/E31 AB tooling, probes (unet_qd/salvage/forward/backing), forensics stacks, GPU snapshot shadow, warmup tooling, matrix/scheduler benchmarks, snapshot diagnostics trio.
- **Reachability caveats:** several "disabled by profile" modules are still imported/initialized at deploy (registry notes deploy-baked import lifecycle, `flag_registry.toml:198-205`); reachability claims above are dispatch-level, verified against effective env chains.

## 17. Exact E37 resolved path (one selected implementation per step)

```text
1. Host:    v2ctl deploy/run --profile e37-clean-lane-qd4
            (ConfigResolver.resolve: defaults <- production <- e29-tracer <- e37 overrides)
2. Wrapper: deploy_and_run_v2_single.bat / run_v2_single.bat
            -> benchmark_v2_direct.py --verify-e28-profile hard gate (loader-profile match)
3. Modal:   app stable-modal-comfy-v2-restore-only-shadow / ModalRuntimeEntrypointV2.run_plan_stream
            single-use container (tracer:65); source identity via v2ctl source-probe (8-file SHA match)
4. Restore: MINIMAL_RESTORE=1; CpuSnapshotModels restore (CPU_MODEL_SNAPSHOT inherited 1)
            clean_lane.begin_request; speculative launch SUPPRESSED (speculative:1094)
5. Plan:    ExecutionPlan consumed (plan fast-path expected: BATCH_C_EXPECT_PLAN_FAST_PATH=1);
            plan identity marked (clean_lane.mark_plan_identity_complete)
6. CLIP:    synchronous QD4 (wiring:1319-1435): header pread -> 4 workers -> 240/240 blocks ->
            pinned qd*2 blocks -> contiguous CUDA buffer -> async H2D -> ALL events complete ->
            quiescence proof (mark_qd_ready) -> bind (mark_bind) -> real forward (mark_forward)
            [two implementations involved BY DESIGN: snapshot restore provides structure;
             QD provides weights — sequential stages, not competing arms]
7. UNET:    snapshot-restored structure -> native fast-disk route (inherited) ->
            load_models_gpu boundary -> Comfy publication
8. Sampling: normal Comfy sampler
9. VAE:     snapshot retention -> late activation (UNET event wait) -> decode
10. Result: DirectOutputSink + structured selector -> durable artifact; expected SHA
            20b10e1f... (tracer:10) checked by StructuralValidator (gate -> confirm)
11. Exit:   single-use container exit; BACKGROUND_*/PERSIST=0 so no background drains
Telemetry:  critical_path_ledger + gantt (tracer:19-20); E37 strict proof published from seams
            (clean_lane.proof()); validator rejects missing evidence rather than inferring
            (clean_lane.py:262-264)
Residual hidden participation (why not 100% "single"): speculative flag armed (suppressed only
at runtime); comfyapp profiler wrapper layers conditionally installable; Comfy native
model-management remains the publication authority; non-seam operations unobservable by proof
design.
```

## 18. Exact current production resolved path

```text
1. Host:    v2ctl deploy/run --profile production (or BATs)
2. Modal:   same app/class/run_plan_stream; warm-capable container (single-use flag absent)
3. Restore: MINIMAL_RESTORE(registry 1); CpuSnapshotModels restore incl. VAE retention
4. Plan:    ExecutionPlan.from_dict; INPUT_TYPES_WARM=1 warm path; prompt-signature cache
            available (env-gated); registry proof via store (anchor .deployed_state.json)
5. CLIP:    snapshot structure (weights retained unless EXCLUDE set; FH off so exclusion not
            expected) -> native Comfy demand load if needed -> conditioning cache:
            hit -> reuse CPU conditioning; miss -> encode + enqueue persistence
            (worker writes + coalesced Volume commit via drain)
6. UNET:    snapshot -> NATIVE_FAST_DISK_UNET=1 route -> load_models_gpu boundary ->
            Comfy bookkeeping/publication (second bookkeeping phase after custom success:
            CONFIRMED at bookkeeping level)
7. Sampling: normal Comfy sampler
8. VAE:     late activation; UNET completion-event wait (FAIL-OPEN on timeout) -> decode
9. Result:  DirectOutputSink + structured selector; validator gate -> confirm
10. Teardown: GPU-fast-return eligible paths + free_memory/soft_empty_cache +
            teardown diagnostics (three overlapping release authorities)
Composite points (branch/fallback, not one deterministic algorithm):
  - CLIP arm selection depends on FH/QD/speculative flags (all off/self-skipped today ->
    native), i.e., production CLIP = snapshot + native demand + cache
  - UNET: snapshot-miss falls to file loading; generic demand always reachable
  - VAE: snapshot-miss falls to native VAELoader; wait gate can time out open
  - ~20 legacy env vars can alter branches without registry knowledge
  - mtime scans remain selectable in legacy delivery paths
```

## 19. Minimal canonical architecture using existing code

(Design only; nothing implemented. Mapping: KEEP = become the interface's concrete core; MOVE = keep behavior, put behind interface; QUARANTINE = diagnostics-only, no authority; REMOVE = after behavior tests.)

| Interface | KEEP | MOVE behind it | QUARANTINE | REMOVE after tests | Hardest migration risk |
|---|---|---|---|---|---|
| ResolvedConfig | ConfigResolver/ResolvedConfig; flag_registry as metadata | all comfyapp/canonical direct env reads + dynamic alias lookup | runtime_overrides channel (policy-forbid) | duplicate alias lookups | silent divergence between baked env, inherited values, consumers |
| DeploymentIdentity | contracts.DeploymentIdentity + build_deployment_identity | FingerprintEngine as config/deploy projection; dependency_manifest | source_probe (redundant 8-file gate), registry-store anchor as independent authority | none (probe retired after equivalence proof) | existing snapshots/proofs/handles stale when semantics unify |
| WorkflowCapsule | ExecutionPlan + execution seed (structural, forbidden-state) | prompt bundle/prefill key; signature caches | pre_graph_cache duplicates | ad-hoc seed rebuilds | reuse-vs-rebuild boundary for topology/signatures |
| ModelRegistry/ModelLease | QdGpuOwner semantics generalized | _ACTIVE_MODEL_READS + ModelPreloadCoordinator behind lease API | _LANES/_STATES as scheduling-only; FastSafe patcher attrs; handle caches | duplicate owner namespaces ("CLIP"/"restore_*"/"graph_loader") | collapsing async-read dedup, GPU ownership, bind completion, release without premature free |
| ClipLoader | clean-lane synchronous QD4 + quiescence proof | clip_fast_hydration_wiring dispatch | speculative lane; FastSafe arm (kept as REQUIRED FALLBACK behind interface); staged transports | hidden clean-lane fallback edges after proof | preserving QdGpuOwner lifetime through bind+forward; preventing alternate reloads |
| UnetLoader | CPU snapshot + native fast-disk route | model_preload coordinator integration; pinned/meta as internal transports | UNET FastSafe; cold early-load unjoined reads | second bookkeeping pass (guard generic path against lease) | generic Comfy path repeating bookkeeping after custom success |
| VaeActivation | late-activation policy + snapshot retention | UNET-wait helper (decide fail-closed vs explicit-proceed-on-timeout) | early VAE read/pre-copy lane | fail-open acceptance ambiguity | timeout semantics: "waited" must equal "serialized safely" or be explicit |
| RuntimeStatus | StructuralValidator/GateResult | lifecycle/status fields projected into one record | UI/telemetry statuses; batch_c independent verdicts | duplicate PASS/FAIL emitters | missing-proof must fail closed everywhere |
| Snapshot lifecycle | cpu_snapshot_models retention/validation/retarget | preload/activation workers; exclusion marker handling | gpu_snapshot_shadow; independent state machines | none | one request-bound quiescent snapshot boundary across workers |
| Request lifecycle | run_plan_stream state machine | LocalHandleOwner/transport; cache behavior | parallel lifecycle authorities | stale global survivors | cross-request leakage across deployment/generation/request identities |
| Canonical timing contract | critical_path_ledger endpoints | RuntimeTrace/full-trace as emitters; Gantt as renderer | ~12 diagnostic samplers | nested profiler wrapper layers | clock domains, async overlap, no double-counted spans; timing never decides PASS/FAIL |

Retain the **native Comfy path as fail-closed fallback** at every model boundary.

## 20. Implementation dispositions

- **AUTHORITATIVE CANDIDATE:** v2ctl+ResolvedConfig; deployment_spec identity; execution seed; CpuSnapshotModels; clean-lane synchronous QD4 (+QdGpuOwner); CPU snapshot + native fast-disk UNET; VAE snapshot+late activation; ExecutionPlan; conditioning cache; StructuralValidator; critical_path_ledger (+canonical Gantt); DirectOutputSink + structured selector; CommitCoordinator; run_plan_stream.
- **REQUIRED FALLBACK:** native Comfy CLIP demand; FastSafe CLIP arm; generic Comfy UNET demand (lease-guarded); pinned staging; native VAELoader on snapshot miss; probe-path BAT mode (documented).
- **COMPATIBILITY ONLY:** run_prompt_stream/checkpoint endpoints; runtime_overrides channel; high-VRAM offload patch; legacy alias resolution (pre-registry).
- **BENCHMARK/DIAGNOSTIC ONLY:** benchmark_v2_direct/batch_c/e30_ab; all probes; forensics stacks; E31 cast-once; full-trace/resource/host/stage13/thread/wait/variance/opt/sampling/teardown diagnostics; GPU snapshot shadow; warmup tooling; checkpoint prewarm; snapshot diagnostics trio.
- **MERGE INTO CANONICAL:** the two load_models_gpu profiler layers → one boundary; ModelPatcher clone wraps → one; ModelPreloadCoordinator+_ACTIVE_MODEL_READS → lease; INPUT_TYPES warm → prep interface; seed/signature caches → WorkflowCapsule; BAT pair → single wrapper; teardown set → one policy.
- **QUARANTINE:** speculative hydration lane (armed-but-suppressed hazard); dynamic `COMFYMODAL_<name>` alias lookup; cold UNET early-load unjoined reads; early VAE pre-copy lane; staged transports (both); mtime artifact scans; second clone wrap.
- **DELETE AFTER PROOF:** legacy benchmark_modal* harness family; region/provider/backing/rehoming AB wrappers; e27/e30 probe scripts; shadow/transfer BATs; duplicate warmup tooling — each only after behavior tests prove no remaining caller.
- **UNKNOWN:** compatibility runner reachability; warmup tooling callers; `graph_loader` producer; D18 VAE gate existence; exact native-fast-disk internal ordering; filler-path cache nonce coverage.

## 21. E39 collision-warning table

| Action | Items |
|---|---|
| **MUST INTERCEPT** | every deploy/run-affecting direct env read + dynamic alias lookup; every speculative launch entry; every CLIP/UNET demand path that can bypass/duplicate a lease; every `load_models_gpu` call after custom success; snapshot bind/forward until reads+futures+CUDA copies+owners reconciled; cache returns when identity/generation/request/lease differs; legacy mtime selection when deterministic delivery active |
| **MUST DISABLE** | clean-lane FastSafe fallback edge + restore-time speculative launch (already suppressed — keep suppressed explicitly); production UNET_FASTSAFETENSORS; one of the two load_models_gpu wrapper layers (behavior-changing profiler fastpaths off during proof); independent owner registries as authorities (diagnostics only); mtime scans as production authority. Do NOT disable generic Comfy load_models_gpu globally — gate it against the canonical lease. For inherited profiles record `requested=1, effective=0, suppressed=true, reason=clean_lane` — never silently rewrite the inherited flag. |
| **MUST LEAVE UNCHANGED** | E37 synchronous QD4 algorithm + quiescence/bind proof; production CPU snapshot + native fast-disk UNET + late VAE policy; StructuralValidator gate/confirm protocol; QdGpuOwner close/release semantics; CommitCoordinator; conditioning-cache drain; DirectOutputSink + deterministic selector; canonical ledger endpoint semantics |
| **MUST PROVE** | all consumers observe same ResolvedConfig incl. inherited-but-suppressed flags; identity agreement across deployment_spec/fingerprints/registry-proof/runtime metadata; producer+consumer share lease token (preflight waits for `restore_clip_loader`); exactly one effective load_models_gpu wrapper, idempotent install, no duplicated patcher bookkeeping; no duplicate CLIP/UNET physical reads (cold UNET reads joined); QD workers/H2D events/futures/owners quiescent before bind/forward; VAE timeout cannot yield accepted "serialized" claim; PASS/FAIL only from structural validation; release/drain covers all registries + cached owners |
| **LATER CLEANUP** | legacy harness deletion; AB-wrapper deletion; probe-script deletion; warmup-tool dedup; identity-domain documentation; sampler/VAE timing unification; handle-cache consolidation |

Specific collision examples requested: selector projection rewriting post-ResolvedConfig — not found (projection only), but backend env emission is the intercept point; legacy env reader bypass — CONFIRMED list §11; compatibility validator marking pass — batch_c independence §13; another snapshot path reattaching excluded CLIP weights — exclusion marker tolerance `cpu_snapshot_models.py:1287` + any loader can hydrate; generic Comfy loader reconstructing excluded CPU state — native demand arm; speculative/prewarm worker holding strong reference past quiescence — `_LANES`/prewarm workers (fence exists for prewarm; lanes cleaned :973-1020; residual risk SUPPORTED); old owner key bypassing new lifecycle proof — `restore_clip_loader`/`restore_preload` mismatch is exactly this.

## 22. Highest-risk conflicting implementations to fix before G1

1. **CLIP owner-key mismatch** (`comfyapp.py:11858` vs `:12323`) — lifecycle proofs can declare readiness while the preflight waiter never sees the read; unify the owner-token namespace.
2. **Stacked `load_models_gpu` wrapper layers** (`comfyapp.py:15854-15899` + `:16898-16982`) — nested spans around one physical call distort behavior and timing; collapse to one idempotent boundary.
3. **Competing CLIP arms with inherited flags** — QD4/speculative/FastSafe/native selection spread across three flags plus read-site defaults; centralize arm selection in one ClipLoader policy.
4. **Multiple ownership registries as simultaneous authorities** (`_ACTIVE_MODEL_READS`, `_LANES`, `_STATES`, coordinator, patcher attrs, handle caches) — make exactly one lease authority; rest become diagnostics.
5. **Split identity/config authorities** — deployment_spec vs 8-file probe vs git-config fingerprints vs direct env reads; make deployment_spec the sole source identity and ResolvedConfig the sole env projector.

## 23. Things safe to defer until after G1

Deletion of legacy benchmark harnesses and AB wrappers; warmup tooling dedup; staged-transport removal; sampler/VAE timing unification; handle-cache consolidation; identity-domain documentation; `run_prompt_stream`/compat path consolidation; probe-script retirement; `graph_loader` producer hunt (unless E39 touches active-read keys).

## 24. Final direct answers

1. **Materially different CLIP loading algorithms reachable today:** **5** — native Comfy demand; FastSafe direct-GPU hydration; QD reader (QD4); speculative lane (orchestrates FastSafe-or-QD early); CPU-snapshot restore + meta/assign bind. Of pure source/H2D algorithms: **3** (native, FastSafe, QD).
2. **How many can perform work during one request:** up to **3 sequential source reads** are reachable in a single request (speculative early read → rejected → FastSafe → failure → native), plus snapshot reconstruction as a prior stage; in clean lane exactly **1** (QD) after snapshot; in production normally **1** (native) after snapshot, **2 stages** counting snapshot restore.
3. **Materially different UNET loading algorithms reachable today:** **4** — CPU-snapshot restore; native fast-disk route (with pinned-staging/meta-direct internals); UNET FastSafe direct-GPU; staged transport — plus the always-reachable generic Comfy demand path and byte-only checkpoint prewarm (not a loader).
4. **Which old path still executes after the new fast path succeeds:** the generic Comfy `load_models_gpu` demand path — it re-runs `ModelPatcher.load` bookkeeping after custom-loader success (CONFIRMED at bookkeeping level; full payload reread not proven per-request). Also both profiler wrapper layers can wrap the same underlying call.
5. **Where can a model be loaded/read twice:** CLIP — speculative read rejected → demand reread; snapshot-excluded weights rehydrated by any loader; preload-coordinator read vs demand read (dedup broken for CLIP by the owner-key mismatch). UNET — cold early-load reads explicitly not joined by the graph loader; possible reread if `current_loaded_models` fails to recognize the custom-loaded model (unproven).
6. **Where can two ownership systems disagree:** `_ACTIVE_MODEL_READS` producer key `restore_clip_loader` vs consumer check `restore_preload` (CONFIRMED); QdGpuOwner vs its facade (dual close authorities, idempotent); patcher-attached FastSafe/QD owners vs native `current_loaded_models` residency; `ModelPreloadCoordinator._active` vs demand registration; stale `_STATES`/`_LANES` across requests.
7. **Which configuration system actually controls runtime behavior:** the **deploy-baked container process environment** read directly at runtime; `ResolvedConfig`/profiles/registry only project into it; ~20 legacy env families + dynamic aliases bypass the registry entirely.
8. **Which deployment identity actually protects cache correctness:** none universally. The registry-proof store protects only its own cache via the `.deployed_state.json` anchor (fail-closed to its anchor, proven by D1 tests); `deployment_spec.build_deployment_identity` is the canonical source hash consumed downstream; the 8-file source probe is a stop-gate, not full proof.
9. **Which timing/validation system actually decides acceptance:** `tools/v2_control/validation.py` `StructuralValidator` (fail-closed gate → confirmation). The ledger/Gantt decide nothing; `batch_c_acceptance.py` is campaign-local.
10. **Five greatest-risk conflicts:** owner-key mismatch; stacked load_models_gpu wrappers; competing CLIP arms with inherited/default-on flags; multiple ownership registries; split identity/config authorities (ranking per §22, oracle-concurred).
11. **What E39 should canonicalize immediately:** single env projection through ResolvedConfig (intercept direct reads); single load_models_gpu boundary; unified owner/lease token namespace; deployment_spec as sole source identity; StructuralValidator as sole acceptance; explicit recorded suppression for inherited flags.
12. **What E39 should deliberately leave alone:** E37 QD4 algorithm + quiescence proof; production snapshot/native-fast-disk/late-VAE route; CommitCoordinator; conditioning-cache fail-closed persistence; DirectOutputSink/selector; ledger endpoint semantics; QdGpuOwner semantics; native Comfy path as fail-closed fallback.
13. **Eventually deletable once behavior tests exist:** benchmark_modal* family; region/provider/backing/rehoming AB wrappers; e27/e30 probe scripts; shadow/transfer BATs; duplicate warmup tooling; speculative lane (if QD canonical and clean-lane policy permanent); staged transports (if unused); the second load_models_gpu profiler layer; second clone wrap.
14. **Is E37 clean lane actually a single understandable algorithm now?** **At dispatch level, yes** — one selected implementation per stage, fail-closed, quiescence-proven, exact-output-checked. **At environment level, no** — hidden machinery still structurally participates: the speculative flag is inherited-armed and suppressed only by a runtime gate; comfyapp profiler wrapper layers are conditionally installable; Comfy native model-management remains the publication authority; the clean-lane proof itself declares non-seam operations unobservable (`clean_lane.py:262-264`); and the whole composite remains one inherited-flag flip away from reactivation. E39 should convert "suppressed" into "absent."

---

### Method note
Six parallel read-only audit lanes (control plane/config; identity/snapshots; UNET/VAE; monkey patches/scheduler; cache/timing/artifacts/lifecycle; CLIP/ownership) plus orchestrator verification of decisive claims (owner-key mismatch `comfyapp.py:11858/:12323`; speculative suppression `speculative_clip_hydration.py:1094-1104`; `CommitCoordinator` `runtime_state.py:314`; profile chain `e37-clean-lane-qd4 → e29-tracer → production`; `_ACTIVE_MODEL_READS` `comfyapp.py:4961`; clean_lane control-flow gating) plus an independent architecture/risk review pass. Git archaeology: implementation-introduction timeline shows the stacking pattern — E28 (`0ba7000`) introduced most fast-path modules beside existing demand paths; E29 (`79cc994`) added the tracer that later became dispatch-controlling; E30 (`8e49d75`) added the QD reader; E31–E37 arrived as the current uncommitted diff (+11,558/−1,489, 55 files) including `clean_lane.py` (new, instrumentation-as-control-flow), `clip_fp32_cast_once.py`, E37 profiles, and the deleted `e31-clip-fp32.toml`. No experiment retired its predecessor; disabled-by-profile modules remain imported/deploy-baked.
