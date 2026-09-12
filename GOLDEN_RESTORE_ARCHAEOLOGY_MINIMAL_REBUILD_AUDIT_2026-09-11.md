# Golden Restore Archaeology + Minimal Rebuild Audit

**Status:** READ-ONLY forensic audit. No source edits, no commits, no deploys, no paid Modal calls.
**Date:** 2026-09-11
**Worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
**HEAD SHA:** `b81510606894bb4d03e8af7c243dd85b76f61f3b` (branch `TESTING2`, subject: `fix: trust verified custom-node publication generation in Golden deploy`)
**Working tree state:** dirty — modified `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/golden_parallel.py`, `comfymodal_runtime/golden_serial.py`, `config/v2/flag_registry.toml`; mass deletion of `EXPERIMENT_EVIDENCE_*` files; untracked 2026-09-11 evidence/reports.
**Report path:** `GOLDEN_RESTORE_ARCHAEOLOGY_MINIMAL_REBUILD_AUDIT_2026-09-11.md` (repo root)

---

## 0. Scope resolution (critical fork) — which restore is authoritative?

The repo contains **two** `restore()` implementations. This audit resolves them before anything else:

| File | Role | Deploy target | Evidence |
|---|---|---|---|
| `comfymodal_runtime/modal_app.py` | **Authoritative Golden Parallel runtime** | `modal deploy -m comfymodal_runtime.modal_app` | `tools/v2_control/backend.py:304`; class `ModalRuntimeEntrypointV2`; `startup` bound `@modal.enter(snap=True)` at `modal_app.py:23765`; `restore` bound `@modal.enter(snap=False)` at `modal_app.py:23767`; registered via `app.cls()` at `modal_app.py:23910` |
| `comfyapp.py` | Legacy monolith imported as `_legacy_module` **and** the "shared custom-node publisher app" | `modal deploy -m comfyapp` | `tools/v2_control/backend.py:315-321`; `modal_app.py:5581` `importlib.import_module("comfyapp")`; `modal_app.py:10331` `self._legacy_module or importlib.import_module("comfyapp")` |

**Consequence:** the Golden Parallel snapshot lifecycle is `modal_app.py:11258 startup()` → `modal_app.py:12583 restore()` → `runtime_bootstrap.py:1984 RuntimeBootstrap.restore()`. `comfyapp.py` supplies the heavy legacy helpers (`_restore_in_process_gpu_state`, `_initialize_cuda_context`, `_apply_sage_attention_policy`) through delegation closures at `modal_app.py:10668-10717`, and is separately deployed only as the publisher.

**Important corollary (answers a key open question):** `comfyapp.py` already has an **E37 minimal restore that defaults ON** (`MINIMAL_RESTORE_DEFAULT = True`, `comfyapp.py:426`; branch `comfyapp.py:20411-20537`) which does only identity reset + barrier reset + backend-if-deferred + `_restore_in_process_gpu_state()` + `_initialize_cuda_context()` + telemetry. `modal_app.py` **allowlists and forwards** `COMFYMODAL_MINIMAL_RESTORE` (`modal_app.py:834-835`, `:4914-4915`; `config_authority.py:136` default `True`) but its own `restore()` **never branches on it** (no `_minimal_restore_effective` in `modal_app.py`). Therefore the proven minimal path currently applies only to the **publisher app**, not to Golden. This is itself the strongest proof that a minimal Golden restore is viable.

---

## 1. Executive verdict

**How much is genuinely essential?** Very little. Of the ~1,290-line `modal_app.restore()` body plus the ~800-line `RuntimeBootstrap.restore()`, the operations that satisfy a *current* correctness or safety invariant are:

1. Reset container-local mutable state (nonces/session ids, UNET barrier events, dedup sets, prepared-state flags, counts) — the P1 cross-restore bug fix.
2. Reconnect the GPU and **eagerly** create/synchronize the CUDA context and re-assert the logical GPU state (`_restore_in_process_gpu_state` + `_initialize_cuda_context`).
3. Three **cheap O(1) generation compares** (runtime-state, models, custom-node) with fail-closed mismatch behavior, plus Sage cached-mode verification.
4. Minimal restore telemetry.

Everything else is one of: diagnostic/experimental observability, CPU-snapshot activation and preload orchestration, host/resource sampling, folder warming, full-trace lifecycle, ledger/Gantt, eviction-boundary RSS handling, seed reconstruction, host fingerprint, teardown setup, clean-lane proof, or automatic custom-node publication/sync/reconciliation.

**Proportion (runtime cost, not LOC).** From the real 2026-09-11 artifact (`EXPERIMENT_EVIDENCE_golden_p1_parallel_1796a2b8de1a42a0_2026-09-11.md`, `restore_breakdown`):

```text
restore_total_ms                1288.389
  restore_gpu_state_ms           599.188   <-- the "~600 ms residual"
  sync_custom_nodes_ms           236.670
  reload_runtime_state_ms        184.658
  cuda_init_ms                    69.430
  snapshot_execution_seed_ms       2.990
  observe_generations_ms           0.740
  folder_warm_ms                1029.428   (background thread; overlaps restore)
restore_method_ms               1318.049   (whole restore() call, incl. wrapper)
```

So ~600 ms of the ~1.3 s restore is a **single named operation**: `restore_gpu_state()` (i.e. `comfyapp._restore_in_process_gpu_state`, `comfyapp.py:20197`). The next largest are the automatic **custom-node sync (237 ms)** and **runtime-state volume reload (185 ms)**. The genuinely-essential kernel (context sync + resets + compares) is on the order of **tens of milliseconds** by code reading; the rest is collateral.

**Largest likely sources of unnecessary latency (ranked):**
1. `restore_gpu_state` 599 ms — must be decomposed; Oracle expected "tens of ms", the artifact shows ~600 ms, so something heavier (VRAM/allocator/`get_total_memory` round-trip, model-management re-init) is inside it.
2. `sync_custom_nodes` 237 ms + `reload_runtime_state` 185 ms — automatic publication/volume reconciliation that the new manual-only policy removes from normal paths.
3. Pre-marker + preload/finalize + CPU-snapshot activation/eviction/host-sampling/folder-warm/`_rd_deep` — hundreds of lines of diagnostic/experimental machinery, largely not on the measured critical path but pure attack surface and complexity.

**Architectural drift from Tolga's original idea.** Tolga's design has **zero** post-snapshot recovery: the only snapshot-specific mechanism is monkeypatching `torch.cuda.is_available`/`current_device` to CPU during initialization (`comfyapp.py`-equivalent `force_cpu_during_snapshot`), and GPU behavior initializes lazily on first `execute()`. We built a second startup system after restore — a canonical critical-path ledger, Gantt telemetry, opt-in full execution trace, cgroup/process CPU samplers, host-memory probes, snapshot-manifest diffs, CPU-snapshot activation/retarget, production UNET defer/preload, a speculative CLIP hydration lane, execution-seed reconstruction, host fingerprinting, teardown diagnostics, clean-lane proof, and an automatic custom-node publication/sync/reconciliation stack that currently gates deploys. The burden of proof has been inverted: post-snapshot work is treated as default-on and must be justified to remove, whereas it should be default-off and justified to keep.

**Distinguish LOC from cost.** Most of the LOC is not on the measured hot path, but the hot path (`restore_gpu_state`, `sync_custom_nodes`, `reload_runtime_state`) is exactly the collar of automatic reconciliation and GPU-state machinery the snapshot was supposed to make unnecessary. Deleting the telemetry/experiment LOC removes complexity and risk; optimizing the three hot blocks removes the actual milliseconds.

---

## 2. Exact current lifecycle

```text
Modal resumes the snapshotted container
│
├─ ModalRuntimeEntrypointV2.restore()                       modal_app.py:12583
│   │
│   ├─ PRE-MARKER REGION                                   modal_app.py:12583–12781
│   │   ├─ reset full-trace locals (all disabled at restore)        12588–12594
│   │   ├─ capture true resume wall/mono/perf timestamps            12600–12604
│   │   ├─ _resolve_restore_clip_probe_source(...) [always runs]    12605
│   │   ├─ build _restore_clip_probe_state; maybe start QD2 thread  12608–12633
│   │   ├─ sync_observability_gates()                               12639
│   │   ├─ _emit_golden_diagnostics_config("restore", api=self)     12640
│   │   ├─ ledger begin_restore/set_request_identity/record_event   12648–12664 (imported)
│   │   ├─ span holders + import begin_span + create restore:early  12665–12718
│   │   ├─ set_authoritative_endpoints(...)                         12724–12730
│   │   ├─ gantt_enabled() + register 2 point spans (gated)         12737–12756
│   │   └─ optional snapshot manifest capture (env-gated, off)      12762–12780
│   │
│   ├─ post_snapshot_restore stage start                    modal_app.py:12781
│   │   ├─ snapshot-callback age print                              12782–12805
│   │   ├─ close restore:early; _assert_golden_restore_model_free   12818–12822
│   │   ├─ _restore_eviction_boundary()  (smaps RSS + optional GC)  12826 / 9528
│   │   ├─ clip_state_checkpoint x2 (D6 diagnostics, guarded)       12830–12838, 12887–12895
│   │   ├─ _lazy_init_snapshot_state()                              12839 / 8363
│   │   ├─ frozen-manifest gantt marker (gated)                     12855–12883
│   │   ├─ maybe_install_clip_fh_demand(); production_snapshot_inv  12899–12917
│   │   ├─ _CgroupCpuSampler() start; _report_host_memory(...)      12938–12944
│   │   ├─ init restore status + _rd_deep + reset counters/timers   12946–12969
│   │   ├─ _capture_remote_identity(); _configure_runtime(); Trace  12973–12993
│   │   ├─ warm_registered_folders() background thread              13003–13043
│   │   ├─ _apply_torch_thread_limit()                              13045–13052
│   │   ├─ restore/session/instance identities; set_model_load_id    13053–13079
│   │   ├─ teardown diagnostics identity; full-trace identity/milest.13080–13175
│   │   ├─ clean_lane.begin_request()  [diagnostic-only no-op]      13176–13180
│   │   │
│   │   ├─ RuntimeBootstrap.restore()               runtime_bootstrap.py:1984
│   │   │   ├─ ledger event + optional native fast-disk wrapper     1992–2035
│   │   │   ├─ restore metadata/telemetry                           2042–2066
│   │   │   ├─ [1] restore_gpu_state() -> comfyapp:20197            2068–2088   ~599 ms
│   │   │   ├─ [2] initialize_cuda()  -> comfyapp:18544             2090–2119    ~69 ms
│   │   │   ├─ [3] sage_policy (exact-skip OR select+apply)         2121–2263
│   │   │   ├─ [4] runtime_state Volume reconcile (+reload)         2265–2352   ~185 ms
│   │   │   ├─ [5] models Volume reconcile (+reload)                2353–2427     ~0 ms
│   │   │   ├─ prescan identity restore                             2428–2440
│   │   │   ├─ [6] custom-node reconcile (+sync/observe)            2442–2609   ~237 ms
│   │   │   ├─ [7] snapshot execution-seed hydrate/reconstruct      2610–2684     ~3 ms
│   │   │   ├─ host hardware fingerprint                            2687–2697
│   │   │   └─ final restore telemetry / decomposition               2699–2785
│   │   ├─ bootstrap generation diagnostics                         13223–13262
│   │   ├─ bootstrap/method error handlers                          13263–13431
│   │   ├─ CPU-snapshot activation block                            13432–14188
│   │   │   ├─ validate_cpu_snapshot_models() (cpu_snapshot_models:2708)
│   │   │   ├─ retarget_cpu_snapshot_models()  (…:2960)
│   │   │   ├─ bridge activation / identity probes / residency
│   │   │   └─ _CACHEDIT_PREPARED / _RES4LYF_PREPARED prepare
│   │   ├─ preload / defer path                                     14190–14442
│   │   │   ├─ _load_legacy_runtime(); _check_unet_deferral_eligible()
│   │   │   ├─ bridge prepare/extend/clear; _start_production_restore_unet()
│   │   │   └─ optional wait on CLIP/UNET workers
│   │   ├─ restore finalization (_do_restore_finalization)          14444–14574
│   │   ├─ ledger exit + speculative CLIP lane                      14580–14620
│   │   ├─ build result dict                                        14621–14647
│   │   ├─ emit _rd_deep / residual breakdown                       14649–14739
│   │   ├─ host info + host-memory completion                       14741–14778
│   │   ├─ full-trace completion/reset                             14779–14800
│   │   ├─ _detect_gpu_allocation(); return marker; result trace    14802–14820
│   │   └─ finally cleanup: stage timers, identity scope/cache      14821–14875
│   │
│   └─ request-ready (first Golden Parallel request may execute)
```

Key helper delegation (`modal_app.py` closures → legacy `comfyapp` module):

```text
restore_gpu_state()          modal_app.py:10668 -> api._restore_in_process_gpu_state()   comfyapp.py:20197
initialize_cuda()            modal_app.py:10671 -> api._initialize_cuda_context()        comfyapp.py:18544
select_sage_runtime_mode()   modal_app.py:10685 -> api._select_sage_runtime_mode()
apply_sage_policy()          modal_app.py:10713 -> api._apply_sage_attention_policy()    comfyapp.py:15290
sync_custom_nodes()          modal_app.py:10440
read_current_custom_node_identity() modal_app.py:10727  (does a Volume.reload())
```

---

## 3. Restore archaeology table

Dates are commit author dates. "Introducer" = first commit returning a hit for the symbol/block in `git log -S/-G` on the current tree.

| Block | Location | Introduced | Original reason | Still used? | Current consumer | Classification | Recommended fate |
|---|---|---|---|---|---|---|---|
| Typed `RuntimeBootstrap.restore()` | `runtime_bootstrap.py:1984` | `e1e4749` 2026-07-17 (187 lines) | Establish typed V2 restore boundary | Yes | Golden restore | KEEP (skeleton) | Rebuild minimal; keep identity/volume/sage stages only |
| Modal snap=False `restore()` | `modal_app.py:12583` | `88a2dd1` 2026-07-17 | Wire V2 Modal lifecycle | Yes | Golden restore | KEEP (skeleton) | Replace body with minimal contract |
| GPU state + CUDA callbacks | `modal_app.py:10668/10671` | `0f1d5bd` 2026-07-26 | Finish V2 cold-path restore | Yes | correctness | **KEEP — essential** | Keep `_restore_in_process_gpu_state`+`_initialize_cuda_context`; **decompose the 599 ms** |
| Sage policy/reconciliation | `sage_policy.py`, `runtime_bootstrap.py:2121-2263` | `88a2dd1`/`e1e4749`; variance `8faa106` 2026-08-05 | Reapply Sage policy across restore | Yes | request execution | KEEP (verify only) | Keep identity verify + cached-mode assert; never re-discover/re-hash on match |
| Runtime-state volume reconcile | `runtime_bootstrap.py:1696-1774,2265-2352` | `b829b15` 2026-08-02 | Production snapshot restore semantics | Yes | correctness/safety | KEEP CHEAPLY | Keep O(1) generation compare + fail-closed; move manifest hash-walk to background/mismatch-only |
| Models volume reconcile | `runtime_bootstrap.py:1552-1597,2353-2427` | `b829b15` 2026-08-02 | Same | Yes | correctness/safety | KEEP CHEAPLY | Keep O(1) generation compare |
| Custom-node generation/publication | `f8f2da5` 2026-08-09; `e5483d5` removed per-boot rehash | Generation-aware, reproducible publication | Partly | deploy/restore decisions | MANUAL-ONLY (see §11) | Strip auto publish/sync/reconcile; keep cheap mismatch detection |
| CacheDiT/RES4LYF restore prep | `1a1d54d` 2026-07-25 (`cacheDiT fix`) | Custom-node/model restore compatibility | Only via activation block | golden_serial/full_trace | DEFER / diagnostic | Move to first actual use; keep only availability reporting |
| Restore deep profiling `_rd_deep` | `modal_app.py:14649-14739` | `34b8beb` 2026-07-29 | Isolate opaque restore CPU interval | Yes (write only) | **No external reader** | DIAGNOSTIC-ONLY | Delete from normal path |
| CPU snapshot warm/evict | `_restore_eviction_boundary` `:9528`; activation `13432-14188` | `a6725d1` 2026-07-29; `7ca422d` 2026-08-06 | Test/lean snapshot retention | Partly | internal | EXPERIMENT-ONLY | Keep model-free assert; move eviction/activation off critical path |
| Full execution trace | `modal_app.py:3071-3559` | `1a07ffa` 2026-07-28 | Opt-in full timing | Yes (opt-in) | reports | DIAGNOSTIC-ONLY | Already request-only; ensure zero restore cost |
| Gantt telemetry | `gantt_telemetry.py`, `gantt_canonical.py` | `a7e7de4` 2026-07-28; canonical `79cc994` 2026-08-19 | Visualize timing | Yes | report renderers only | DIAGNOSTIC-ONLY | Opt-in only |
| `sync_observability_gates` | `modal_app.py:770,12639` | `248d605` 2026-08-05 | Strict telemetry gates | Yes | model_preload flags (real) | KEEP CHEAPLY | Move to snap=True/first-use; keep flags, drop restore-time sync |
| `CriticalPathLedger` | introduced `79cc994` 2026-08-19 (E29) | Ground-truth canonical tracing | Yes | `gantt_canonical.py:118`, reports | DIAGNOSTIC-ONLY | Opt-in; no request-path reader |
| `sync_custom_nodes` | `runtime_bootstrap.py:1355-1363`; `modal_app.py:10440` | `f8f2da5`; simplified `e5483d5` 2026-08-11 | Generation-aware sync | Yes | restore/startup | MANUAL-ONLY | Remove auto-sync; keep detection only |
| Snapshot manifest | `snapshot_build_manifest.py`; `modal_app.py:12762-12780` | `7ca422d` 2026-08-06 | Explicit snapshot identity | Env-gated | registry_proof/dependency_manifest | DIAGNOSTIC-ONLY at restore | Leave producer; never capture at restore |
| Execution seed | `runtime_bootstrap.py:2610-2684` | `b829b15` 2026-08-02 | Deterministic state across snapshot | Yes | `runtime_executor.py:4141` | DEFER (fail-closed) | Freeze inputs at snap=True or keep ~1 ms build; never Volume read |
| Host memory / cgroup sampling | `_CgroupCpuSampler`, `_report_host_memory` | `bd5aa2f` 2026-08-09 | Telemetry resilience | Yes | diagnostics | DIAGNOSTIC-ONLY | Delete from normal restore |
| Thread policy | `apply_torch_thread_policy`, `_apply_torch_thread_limit` | `a2286dd` 2026-08-11 | Reproducible baseline | Yes | request execution | KEEP CHEAPLY | Move to snap=True (already applied there) |
| Folder warming | `warm_registered_folders` | ~`9bf15b0`/`9a428fdb` 2026-08-06 | Reduce first-touch latency | Yes (background) | self | BACKGROUND-RISK | Fully detach from restore; background after ready only |
| E28 speculative CLIP lane | `start_restore_time_clip_lane` | `a6a755e` 2026-08-13 | Overlap CLIP I/O with restore | Yes (optional) | clip wiring | EXPERIMENT-ONLY | Off critical path; first-use |
| Teardown diagnostics | `teardown_diagnostics.py` | `314c0ea`/`5552a54` 2026-08-04 | Bound teardown cost | Yes | diagnostics | KEEP CHEAPLY | Keep identity set (~µs); nothing else in restore |
| Clean lane | `clean_lane.py` | E37 (`36b895d`) | E37 proof + gate | **No-op unless flagged** | proof only | DIAGNOSTIC-ONLY | Delete calls |
| E37 minimal restore (precedent) | `comfyapp.py:426,20411-20537` | `36b895d` | Collapse restore to backend+CUDA | Yes (publisher app) | publisher restore | **Precedent** | Reuse as the model for Golden |

**History summary:** the earliest typed restore (`e1e4749`, 2026-07-17) was ~187 lines of callback orchestration. It grew through: cold-path expansion (`0f1d5bd`, 2026-07-26) → full execution trace + `_rd_deep` (`1a07ffa`, `34b8beb`, 2026-07-28/29) → CPU snapshot + volume/seed guards (`b829b15`, `a6725d1`, `7ca422d`, 2026-08-02–06) → host/thread telemetry (`bd5aa2f`, `a2286dd`, 2026-08-09) → E28/E29/E30 critical-path ledger+Gantt (`0ba7000`, `79cc994`, `8e49d758`, 2026-08-18–19) → Golden identity/parity/eviction (`7446f006`, `9a428fdb`, 2026-09`). The E29 ground-truth report (`V2_BATCH_E29_GROUND_TRUTH_CRITICAL_PATH_AND_RESTORE_MAP.md`) recorded a 4,191.9 ms restore of which `restore:bootstrap` was ~4,161.5 ms (~99%); it contains **no** 600 ms pre-bootstrap region (its `restore:preamble` was ~42.1 ms), so the "~600 ms pre-marker" hypothesis is not supported by that report.

---

## 4. Dependency proof (current consumers)

Proof that a block is dead/cosmetic must come from reference evidence, not "looks unused." Findings (source: full-tree grep of the working tree, `.slim/worktrees` excluded):

**Restore timing dict / telemetry — REAL external consumers**
- `canonical_execution.py:2718-2724,3096` read the remote result `_restore_timing`.
- `benchmark_modal.py:659,726,1080-1081,1384,1419`; `benchmark_modal_e2e.py:603-652,752,788-794,2314,2464,2593,2756`; `diagnosis_collector.py:516-524,825-855`.
- **Raw `_rd_deep` has no external reader** — created and self-read only at `modal_app.py:14679-14706`. → delete-able.

**CriticalPathLedger / Gantt / restore spans — DIAGNOSTIC-ONLY consumers**
- `critical_path_ledger.py:721-787` `get_restore_spans()`; `gantt_canonical.py:118`; `full_trace_report.py:4887,5485,6387-6464`; `golden_human_report.py:225,344,565,872,1012,1135-1257`.
- **No request executor branches on ledger/Gantt content.** All restore ledger calls are `try/except pass` writes.

**Observability gates — REAL consumers (keep the flags, not the restore-time sync)**
- Producers: `modal_app.py:770,12639,20794,22733`.
- Consumers: `model_preload.py:3989,4387,4994-5017,5420,5487,8889,9855,10059,10107,10261,10291,11063,11252` (`_PAGEFAULT_TRACKING`, `_DIAGNOSTIC_FLAG`); `modal_app.py:13100,13336,14043,14061,14920,15963,16042,17208,18355,21803,23865`.

**Execution seed — REAL request-path consumer**
- Built/hydrated `runtime_bootstrap.py:2610-2684`; attached `modal_app.py:20218-20252`; consumed **fail-closed** `runtime_executor.py:4133-4180` (`if seed is None: return`). Pure warm-start enrichment, not correctness. Existing lazy escape: `_derive_request_snapshot_seed()` (`modal_app.py:20254-20400`) under `COMFYMODAL_V2_PUBLISH_RESTORE_PLAN=0` (default).

**Sage — REAL consumer**
- `runtime_bootstrap.py:2204-2235`; `modal_app.py:3570-3606,10685-10825,23061,23376`; `golden_serial.py:7946-7949`; `deployment_spec.py:37,52-53`.

**Custom-node generation identity — REAL consumers (parity/cache)**
- `modal_app.py:10088-10089,10395-10473,10522`; `contracts.py:897-1003`; `dependency_manifest.py:341-364,590-614`; `clip_conditioning_cache.py:292`.

**CacheDiT / RES4LYF prep — REAL (telemetry/report + CLIP wiring) consumers**
- `golden_serial.py:2826-2830,9171,9181,12703,12854-12881`; `full_trace_report.py:1706-1715`; `clip_fast_hydration_wiring.py:3230-3282`.

**Diagnostic-only (no real consumer):** `_rd_deep`; clean-lane (`clean_lane.py:39-43` early-returns unless `COMFYMODAL_V2_E37_CLEAN_LANE`/`COMFYMODAL_V2_CLEAN_LANE` set — its three restore calls are production no-ops); Gantt point spans (gated); snapshot manifest at restore (env-gated off); full-trace identity update (opt-in); `_report_host_memory`/cgroup sampler (diagnostics); `clip_state_checkpoint` (D6 diagnostics).

**Tests:** many `tests/test_restore_*`, `test_minimal_restore.py`, `test_e37_control_plane.py`, `test_v2_snapshot_*`, `test_audit_round*` assert source structure (AST/`assertIn`) rather than exercising the request path. These protect **historical machinery**, not current product correctness. The tests that assert genuine current contracts are `test_v2_snapshot_seed_request_metadata.py`, `test_restore_timing_data_flow.py`, `test_modal_restore_boundary.py`, `test_runtime_restore_plan.py`, `test_sageattention_restore_policy.py`, `test_v2_clip_restore_lifecycle.py`.

---

## 5. Essential safety contract

Only these invariants must survive; each with its minimum mechanism and best lifecycle home.

| Invariant | Failure prevented | Current mechanism | Minimum mechanism required | Best location |
|---|---|---|---|---|
| No stale cross-restore request state | Second-restore inherits a set barrier → workers wake early; duplicate dedup; stale nonce/prepared flags | `comfyapp.py:20312-20341`; `modal_app.py:12946-12969,13188-13189,14452` | Clear UNET barrier events + anchor; reset dedup sets/counters; clear `_RES4LYF/_CACHEDIT_PREPARED`; new nonce/session ids | **Restore** (unavoidable) |
| GPU is logical-CUDA and context is real | Model placement stays CPU; CUDA-only attention paths fail | `_restore_in_process_gpu_state` (`comfyapp.py:20197`), `_initialize_cuda_context` (`comfyapp.py:18544`) | Flip `cpu_state=GPU`/`vram_state`; `current_device()` + `synchronize()` | **Restore** (eager; lazy adds request latency + race) |
| Volumes not silently mutated between capture and restore | Fail-open serving of wrong model/state | Generation compares: models `runtime_bootstrap.py:1552-1597`; runtime-state `1696-1774`; custom-node `2442-2526` | Keep the three **O(1) generation-string compares** with fail-closed mismatch; reject `snapshot_memory`/`prescan` as authorizers | **Restore** (cheap) |
| Sage mode matches baked runtime | Silent Triton/fallback drift | Identity verify `runtime_bootstrap.py:2128-2163` + exact-skip | Verify identity + assert cached `sage_mode == baked_cuda`; never re-hash/reprobe | **Restore** (cheap) |
| Seed never breaks execution | Wrong loader cache signature | `runtime_bootstrap.py:2610-2684`; fail-closed consumer | Freeze seed inputs at snap=True, or keep ~1 ms build; consumer stays fail-closed | snap=True / first request |
| Missing custom node is reported, not auto-published | Silent dependency drift / destructive auto-publication | (new policy) | Cheap generation mismatch **detection + clear error**; manual publisher only | **Restore detects, never acts** |

---

## 6. Minimal post-snapshot contract

Reconstructed from scratch — **not** a trimmed copy of today's function:

```python
def restore(self):
    # 1. Repair only state that fundamentally cannot survive the CPU snapshot.
    reset_container_local_mutable_state()   # barriers, nonce/session ids, dedup sets, prepared flags

    # 2. Reconnect GPU eagerly and assert logical-CUDA + real context.
    reconnect_gpu_and_assert_cuda()         # _restore_in_process_gpu_state + _initialize_cuda_context
    assert get_torch_device().type == "cuda"

    # 3. Cheap, fail-closed identity checks. Detect; do not auto-act on custom nodes.
    verify_generation("runtime_state")      # O(1) generation string compare
    verify_generation("models")             # O(1) generation string compare
    verify_or_report_custom_node_generation()   # detect mismatch -> raise clear missing-dependency error
    verify_sage_cached_mode()               # assert cached baked mode; no discovery

    # 4. Minimal telemetry.
    emit_restore_telemetry()                # restore_start, restore_end, restore_total_ms, status
    return ready
```

**Is even less sufficient?** The four groups above are the empirical floor. Steps 1–2 are mandatory (Oracle-verified: lazy CUDA is unsafe because `_restore_in_process_gpu_state` must flip ComfyUI's logical device before first request). Step 3's compares are sub-millisecond and are the only fail-closed proof that the mounted Volumes match the snapshot. Step 4 is trivial. Everything below in §7 is movable. The E37 minimal path in `comfyapp.py` already proves backend+CUDA+telemetry alone boots — but it is only safe because the publisher app does not carry Golden's model/sage/volume invariants.

---

## 7. Move / defer / delete plan

### MOVE BEFORE SNAPSHOT (`snap=True` in `startup()`)
- `apply_torch_thread_policy` (already at `modal_app.py:11270`; drop the restore duplicate `_apply_torch_thread_limit`).
- `sync_observability_gates()` — resolve flags before capture so restore only reads already-synced values.
- Freeze execution-seed inputs (cert workflow hash + loader identities + deployment hash + custom-node generation) into the snapshot so the restore-time build/hydrate can be deleted.
- Freeze/emit the custom-node generation record and deployment identity (already largely done in `startup()` via `freeze_custom_node_identity` + baseline capture).

### MOVE TO DEPLOYMENT / MANUAL PUBLISHER
- Custom-node publication, generation scanning/hashing (`publication_policy.compute_publication_generation:419-429`), packaging, destructive guard, readback verification (`tools/v2_control/custom_nodes.py:804-965`) — all stay **only** in the manual publisher, entirely off deploy/restore/request paths.
- Remove the deploy-time publication **gate** from the normal Golden deploy (`tools/v2_control/cli.py:2808-2822,2887-2913,2959-2962`).
- Source/deployment identity computation (`deployment_spec.py`) stays deploy-time; restore only compares a frozen token.

### DEFER UNTIL FIRST USE
- CacheDiT / RES4LYF preparation (`modal_app.py:13432-14188` prep segments) — initialize on first use of those nodes.
- CPU-snapshot model validation/retarget (`cpu_snapshot_models.py:2708,2960`) — validate on first model use, not restore.
- Preload / UNET defer / speculative CLIP lane (`modal_app.py:14190-14420`) — start on first request.
- Snapshot execution-seed attach — derive from the request plan if the frozen snapshot seed is absent (existing `_derive_request_snapshot_seed`).
- Sage `apply_sage_policy` — only if a request observes the cached mode invalid.

### DELETE FROM NORMAL RUNTIME
- Pre-marker ledger/Gantt/manifest machinery: `modal_app.py:12605-12780` (clip-probe resolve that runs even when disabled, ledger begin/span/endpoints, Gantt point spans, snapshot-manifest capture).
- `_rd_deep` + residual computation (`14649-14739`) and `_RESTORE_STAGE_TIMERS` bookkeeping.
- `_CgroupCpuSampler`, `_ProcessCpuSampler`, `_report_host_memory` calls in restore (`12938-12944,14741-14778`).
- `_restore_eviction_boundary` work beyond a cheap model-free assertion (`9528`).
- Host fingerprint (`2687-2697`), folder-warm thread from restore (`13003-13043`), full-trace identity/milestone block (`13100-13122`).
- `clean_lane.begin_request/mark_restore_return/restore_child_classifications` (`13177,13207,14809`) — production no-ops.
- `_detect_gpu_allocation` (`14802`), `resource_identity()` duplicate compute (`13125,13162`), `_capture_host_info().hostname` (`14752`).
- All clip_state_checkpoint D6 calls (`12830,12887,13215`).
- Automatic custom-node sync/observe (`runtime_bootstrap.py:2442-2609` sync path; `modal_app.py:10440` sync on non-construction).

### BACKGROUND AFTER READY
- Runtime-state manifest **file-hash verify** (`runtime_bootstrap.py:1750`) — run only on mismatch, or async after ready.
- Folder warming — daemon thread started after restore returns.
- Host telemetry / resource sampling — background.

### MUST REMAIN IN RESTORE (small)
1. `reset_container_local_mutable_state()`.
2. `reconnect_gpu_and_assert_cuda()` (eager `_restore_in_process_gpu_state` + `_initialize_cuda_context`).
3. O(1) generation compares: runtime-state, models, custom-node (detect only).
4. Sage cached-mode verify.
5. Minimal restore telemetry.

---

## 8. Modern telemetry contract

**Normal restore emits only:**

```text
restore_start            (wall + mono)
restore_end              (wall + mono)
restore_total_ms
restore_method_status    (success | degraded)
failure_reason           (only on failure)
optional: 2-4 tiny stage timings for the operations that truly remain
          (gpu_reconnect_ms, cuda_init_ms, generation_check_ms)
```

When diagnostics are off, normal restore must:
- import **no** ledger/Gantt/full-trace/profiler/sampler modules;
- create no spans, no ledger, no Gantt objects, no `_rd_deep`, no resource sampler;
- run no `smaps`/cgroup/host-memory scans;
- capture no snapshot manifest.

Deep profiling becomes an **opt-in attachment** to the runtime (existing `COMFYMODAL_V2_FULL_TRACE`, `COMFYMODAL_V2_OPTIMIZATION_DIAGNOSTICS`, ledger/Gantt flags) — never a mandatory import graph in `restore()`.

The only telemetry keys with real external consumers to preserve are the ones `canonical_execution.py`, `benchmark_modal*.py`, and `diagnosis_collector.py` read (`restore_total_ms`, lifecycle identity fields, `restore_method_*`). Raw `_rd_deep` and raw stage timestamps may be dropped.

---

## 9. Proposed new architecture

```text
snap=True (startup):
    - thread policy
    - resolve observability flags
    - (deploy/manual) custom-node source already frozen; baked generation recorded
    - initialize ComfyUI backend under force_cpu_during_snapshot (hide CUDA)
    - freeze execution-seed inputs + deployment/custom-node identity tokens
    - freeze model loader outputs / CPU snapshot state

────────── SNAPSHOT (CPU memory captured) ──────────

snap=False (restore):
    - reset container-local mutable state (barriers/nonces/dedup/prepared flags)
    - _restore_in_process_gpu_state()  -> logical CUDA
    - _initialize_cuda_context()       -> real context + synchronize
    - O(1) generation compares (runtime-state, models, custom-node):
          match -> proceed; mismatch -> raise clear error (NO auto-publish/sync)
    - assert cached Sage mode == baked
    - emit restore_start/end/total_ms/status
    return ready

first request:
    - attach execution seed (frozen snapshot seed or derived from request plan)
    - install CLIP FH demand / preload only if this request needs it
    - start folder warming in background if beneficial

first GPU/model use:
    - CPU-snapshot model validation/retarget
    - CacheDiT / RES4LYF preparation
    - Sage re-patch only if cached mode was proven invalid
```

**Why each post-snapshot op exists:** state resets close the P1 cross-restore bug; GPU reconnect flips ComfyUI's logical device so model placement is correct before any request; the generation compares are the only fail-closed proof that Volumes were not mutated under the snapshot; the Sage assert prevents silent fallback drift; telemetry is the minimal modern contract. Nothing else has a proven current invariant.

---

## 10. Implementation handoff (do not implement here)

**Exact files/functions to replace:** `modal_app.py:12583 restore()` (replace body); `runtime_bootstrap.py:1984 restore()` (reduce to the 5-stage contract, delete stages 3–8 bulk); `modal_app.py:10440 sync_custom_nodes()` (delete auto-sync; keep detection); `modal_app.py:10727 read_current_custom_node_identity()` (keep only if the cheap compare needs the mount token; drop `Volume.reload()` from hot path); deploy gate in `tools/v2_control/cli.py:2808-2822,2887-2913,2959-2962`.

**Exact blocks to delete/move:** see §7. Highest-value deletions: entire pre-marker region `modal_app.py:12605-12780`; `_rd_deep`/residual `14649-14739`; cgroup/host-memory calls `12938-12944,14741-14778`; full-trace identity `13100-13122`; folder-warm spawn `13003-13043`; clean-lane calls; clip checkpoints; CPU-snapshot activation `13432-14188`; preload/defer `14190-14420`.

**Essential invariants to preserve:** §5 (all six).

**Risky assumptions needing a tiny validation (no new deploy unless noted):**
1. **Decompose `restore_gpu_state` (599 ms).** Oracle expected tens of ms; the artifact shows 599 ms. Read the existing `restore_breakdown`/`_RESTORE_STAGE_TIMERS` for 3 restores to see what dominates (likely `get_total_memory`/VRAM allocator/model-management re-init). *This is the single biggest latency win and is currently misattributed.*
2. **Volumes are not in the memory snapshot.** Bump a generation on the Volume, restore an old snapshot, confirm mismatch still forces behavior (do **not** auto-reload under manual-only policy — confirm it *detects*).
3. **Logical GPU is restored** after `_restore_in_process_gpu_state` (assert `get_torch_device().type == "cuda"` once); lazy CUDA would leave `cpu_state=CPU`.
4. **Sage exact-skip never carries `triton_fallback`** into Golden (`runtime_bootstrap.py:2200-2203`).
5. **Manual publication + snapshot:** confirm a fresh `snap=True` is required (see §11).

**Expected latency wins by major removed block** (based on the 2026-09-11 breakdown):
- `restore_gpu_state` decomposition/optimization: up to ~0.5 s.
- Remove auto custom-node sync: ~0.24 s.
- Remove auto runtime-state reload/verify: ~0.18 s (when a reload is currently triggered; the compare itself is sub-ms).
- Remove diagnostic/sampler/ledger/Gantt/pre-marker machinery: low single-digit to tens of ms plus large complexity/risk reduction.

**Recommended incremental order (avoid dragging old baggage):**
1. Build the new minimal `RuntimeBootstrap.restore()` beside the current one behind a default-on flag; keep `comfyapp.py` E37 path as reference.
2. Delete auto custom-node publication/sync/reconciliation from deploy/restore; add the detect-and-report invariant.
3. Decompose and right-size `restore_gpu_state`.
4. Strip pre-marker + `_rd_deep` + samplers + host/folder-warm from restore; make telemetry opt-in.
5. Move CPU-snapshot activation, CacheDiT/RES4LYF, preload to first use.
6. Delete the legacy pipeline only after the minimal path passes the §5 invariants on real restores.

---

## 11. Custom-node publishing: MANUAL-ONLY (new constraint)

**Policy:** normal deploy, preflight, snapshot startup, restore, and request setup must not scan custom-node contents, compute prospective publication generations, package/publish/sync, auto-reconcile publication, or block on publication state. The normal path uses currently available custom-node state and proceeds. Missing nodes must fail clearly and report the missing dependency; never auto-publish.

**Current violations (evidence):**
- Deploy-time publication gate: `tools/v2_control/cli.py:2808-2822` `_publish_golden_custom_nodes()`, invoked from Golden deploy control flow; blocks on `GateError` at `cli.py:2887-2913` and `2959-2962`.
- Startup auto-sync: `RuntimeBootstrap.startup()` → `sync_custom_nodes()` at `runtime_bootstrap.py:1355-1363`; construction branch scans/hashes and may write+commit a generation record (`modal_app.py:10574-10625`); non-construction branch may `_sync_custom_nodes_from_volume()` (`modal_app.py:10652-10653`).
- Restore auto-reconcile: `runtime_bootstrap.py:2442-2609` falls back to full sync + observe on any identity mismatch.
- Restore-time Volume read: `read_current_custom_node_identity()` intentionally reloads the mount (`modal_app.py:10727-10758`).
- Generation scanning: `publication_policy.compute_publication_generation` walks and hashes every publication file (`publication_policy.py:419-429`); `custom_node_root.resolve_custom_nodes_root_details` inspects directory structure (`custom_node_root.py:50-181`).

**Classification:**

| Machinery | Classification | Fate |
|---|---|---|
| Manual publisher (`sync_custom_nodes_to_volume`, `run_publish_or_skip`, destructive guard, readback verify) | KEEP (off normal paths) | Preserve strong verification inside the explicit publisher only |
| Golden deploy publication gate | OBSOLETE on normal path | Remove from `modal deploy -m comfymodal_runtime.modal_app` |
| `compute_publication_generation` content scan/hash | MOVE TO MANUAL PUBLISHER | Only in explicit publish |
| `sync_custom_nodes` auto-sync + generation-record write/commit | OBSOLETE | Delete from startup/restore |
| `observe_generations` / parity report | DIAGNOSTIC-ONLY | Manual/audit only |
| Cheap generation mismatch detect + clear missing-dependency error | KEEP CHEAPLY | Only truly necessary runtime identity invariant |

**Minimum sequence after a manual publication for nodes to be usable:**
1. Run the manual publisher (writes the generation record + commits the `comfyui-custom-nodes` Volume).
2. **Fresh Golden deploy** (`modal deploy -m comfymodal_runtime.modal_app`) so the deployment identity reflects the new custom-node hash.
3. **Fresh `snap=True` container / new CPU snapshot**, because custom-node Python modules are imported and registered during backend startup (`comfyapp.py:18074 nodes.init_extra_nodes()`, `:11052`, `:15883`, `:21099-21109`) and captured in the CPU snapshot; class resolution reads the already-loaded `nodes.NODE_CLASS_MAPPINGS` (`contracts.py:865`, `execution_warm.py:65-92`).
4. Requests against that fresh snapshot.

**Why a fresh snapshot is technically required:** restore deliberately skips sync and registry re-import on identity match (`runtime_bootstrap.py:2442-2446,2491-2495,2540-2549,2584-2608`); a Volume reload makes files visible but does **not** import new Python node modules into the already-running process. No supported request-time import/publish path exists. *Uncertainty:* the repo contains no definitive test proving `init_extra_nodes()` can safely mutate an already-restored registry in every ComfyUI configuration; treat "restore then dynamically import new nodes" as unsupported and require a fresh snapshot.

---

## Appendix — exact reference metadata

**Worktree:** `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\custom_nodes\comfyui-modal`
**HEAD SHA:** `b81510606894bb4d03e8af7c243dd85b76f61f3b` (branch `TESTING2`)
**Report path:** `GOLDEN_RESTORE_ARCHAEOLOGY_MINIMAL_REBUILD_AUDIT_2026-09-11.md`

**Relevant source paths inspected:**
- `comfymodal_runtime/modal_app.py` (24,140 lines) — `restore()` 12583; `startup()` 11258; closures 10440–10825; class 7501; lifecycle wiring 23580–24140
- `comfymodal_runtime/runtime_bootstrap.py` (2,790 lines) — `startup()` 1307; `restore()` 1984–2785
- `comfyapp.py` (24,115 lines) — legacy helpers `_initialize_cuda_context` 18544; `_restore_in_process_gpu_state` 20197; `_apply_sage_attention_policy` 15290; E37 minimal restore 426/20306–20537; `force_cpu_during_snapshot`
- `comfymodal_runtime/gpu_snapshot_shadow.py` — `restore()` 771; `restore_snapshot()` 1323; `restore_cpu()` 1995
- `comfymodal_runtime/critical_path_ledger.py`, `gantt_telemetry.py`, `gantt_canonical.py`, `full_execution_trace.py`, `full_trace_report.py`, `golden_human_report.py`
- `comfymodal_runtime/cpu_snapshot_models.py`, `execution_seed.py`, `sage_policy.py`, `clean_lane.py`, `teardown_diagnostics.py`, `host_hardware_telemetry.py`, `snapshot_build_manifest.py`
- `comfymodal_runtime/publication_policy.py`, `custom_node_parity.py`, `custom_node_root.py`, `registry_proof.py`, `registry_proof_store.py`, `deployment_spec.py`, `dependency_manifest.py`, `contracts.py`, `runtime_executor.py`
- `comfymodal_runtime/clip_fast_hydration.py`, `clip_fast_hydration_wiring.py`, `model_preload.py`
- `tools/v2_control/backend.py` (304 Golden deploy; 315-321 publisher), `cli.py`, `custom_nodes.py`, `source_probe.py`, `config.py`, `custom_nodes.py`
- `canonical_execution.py`, `benchmark_modal.py`, `benchmark_modal_e2e.py`, `diagnosis_collector.py`

**Historical commits inspected:** `e1e4749` 2026-07-17; `88a2dd1` 2026-07-17; `1a1d54d` 2026-07-25; `0f1d5bd` 2026-07-26; `1a07ffa` 2026-07-28; `a7e7de4` 2026-07-28; `34b8beb` 2026-07-29; `eb28534` 2026-07-29; `a6725d1` 2026-07-29; `b829b15` 2026-08-02; `314c0ea` 2026-08-04; `248d605` 2026-08-05; `7ca422d` 2026-08-06; `bd5aa2f` 2026-08-09; `f8f2da5` 2026-08-09; `a2286dd` 2026-08-11; `e5483d5` 2026-08-11; `a6a755e` 2026-08-13; `0ba7000` 2026-08-18; `79cc994` 2026-08-19; `8e49d758` (E30); `7446f006` 2026-08-27; `9a428fdb` 2026-08-24; `36b895d` (E37/E38); `eebea83`; `b815106` (HEAD).

**Evidence artifacts used:** `EXPERIMENT_EVIDENCE_golden_p1_parallel_1796a2b8de1a42a0_2026-09-11.md` (restore_breakdown), `V2_BATCH_E29_GROUND_TRUTH_CRITICAL_PATH_AND_RESTORE_MAP.md`, `SYNTHETIC_GOLDEN_PROFILE_*`, `REPORT_GOLDEN_LOADER_PROCESS_AB_2026-09-11.md`, `CAMPAIGN_REPORT_CLIP_FORWARD_CONTENTION.md`.
