# E39 — comfyapp.py Golden-Path Reachability, Deconfliction, and Aggressive Phase-G Pruning Report

> **SUPERSESSION NOTICE (2026-08-30):** Historical E39 report; preserve its
> pruning and run evidence, but use `docs/COMFYMODAL_OUTPUT_DURABILITY_POLICY.md`
> for current generated-output semantics. Output durability is off by default;
> strict commit/reopen/hash proof is opt-in. S4 source publication durability
> remains mandatory.

Batch: E39 · Date: 2026-08-22 · Branch: `TESTING2`
Baseline checkpoint commit: **`36b895d`** ("e37/e38: checkpoint pre-E39 worktree") — created at batch start so every E39 change is cleanly separable from E31–E37 uncommitted work.
Post-prune state: uncommitted working-tree changes to `comfyapp.py` + `tests/test_production_plan_fix.py` only.

Evidence labels: **CONFIRMED** (file:line or artifact verified) · **SUPPORTED INFERENCE** · **HYPOTHESIS** · **UNKNOWN** · **UNOBSERVABLE**.

---

## 1. Executive verdict

E39 executed a 14-lane parallel forensic audit of `comfyapp.py` (24,450 LOC) and then pruned every block that could be **proven** outside Golden Path / Phase G / fail-closed fallback / supported-caller scope. The result:

- **1,359 LOC deleted (−5.56%)**, concentrated in five generations of superseded experiments: the scheduler benchmark harness, the speculative cold-UNET early-load path, the duplicate `load_models_gpu` profiler layer (with its behavior-changing fastpath bypass), the second `ModelPatcher.clone` wrap (lineage tracer), the `LoadedModel.__eq__` diagnostic patch, and the `modelpatcher_cache` experiment.
- **Zero regressions**: local test failure sets are byte-identical to the pre-prune HEAD baseline across all focused suites; pruning additionally **fixed** one pre-existing failure.
- **One remote cold validation gate passed on the first post-prune attempt** (`gate_valid=1`) with exact output SHA, QD 4/4, 240/240 blocks, zero source errors, no fallback, canonical ledger zero-gap, and first-durable-result proof.

The audit's central finding matches E38C §1: this file stacks five optimization generations *without retirement*, but almost everything stacked is either Golden-required, Phase-G-required, a required fallback, or has a proven supported caller. **No symbol qualified as PROVEN_DEAD except the `__eq__` diagnostic patch**; Modal endpoint registration, dynamic runtime-flag lookup, test imports, and legacy-benchmark callers keep everything else reachable. The honest safe-reduction bound was ~1.36k LOC, not tens of thousands. Converting "suppressed" into "absent" beyond this requires the caller-retirement work explicitly deferred to E40/later Phase G (§22–23 here).

---

## 2–7. Size accounting

| Metric | Before | After | Delta |
|---|---:|---:|---|
| 2. Original `comfyapp.py` LOC | 24,450 | — | — |
| 3. Final `comfyapp.py` LOC | — | 23,091 | −1,359 |
| 4. LOC deleted | — | — | **1,359 (−5.56%)** |
| 5. LOC moved/extracted | — | — | 0 (extraction deferred — see §17) |
| 6. LOC retained | — | — | 23,091 |
| 7. Percentage reduction | — | — | **5.56%** |

## 8–14. Structural counters (before → after)

| Metric | Before | After | Note |
|---|---:|---:|---|
| 8. Symbol count (top-level defs/classes/methods) | 233 + 10 + 193 = 436 | 233 + 10 + 187 = 430 | −6 methods |
| 9. Module globals (top-level assignments incl. constants) | ~190 tracked entries | ~183 | −7 (`COLD_UNET_*` family ×6, `_GENERIC_SPECULATIVE_LOAD_ALLOWED`, minus net) |
| 10. Environment-read sites (`os.environ`/`getenv`) | 71 | 68 | −3 (cold-UNET env family); `env_flag()` reads additionally −7 |
| 11. Monkey-patch install sites | 37 | 34 | −3 installs (`__eq__` patch, deep-profile lmg layer-2, modelpatcher_trace/cache) |
| 12. Owner/registry systems | 12 | 12 | No ownership registry removed (L9: none provably dead) |
| 13. Thread/executor creation sites | 38 | 18 | −20 (scheduler harness worker threads ×~16, cold-UNET worker ×2, finalize timer machinery) |
| 14. Diagnostic blocks | 22 inventoried | 21 embedded | 0 extracted; deep-profile emission removed |

## 15. Classification counts (reconciled manifest)

Every significant block was reconciled into exactly one category:

| Category | Blocks (approx.) | Disposition |
|---|---:|---|
| GOLDEN_REQUIRED | 118 | Kept |
| PHASE_G_REQUIRED | 64 | Kept |
| FAIL_CLOSED_FALLBACK | 41 | Kept |
| MOVE_TO_DIAGNOSTICS | 22 | Kept this batch; extraction deferred (§17, §37) |
| LEGACY_COMPAT_SUPPORTED | 31 | Kept |
| SUPERSEDED_EXPERIMENT | 9 | **Deleted (this is the 1,359 LOC)** |
| PROVEN_DEAD | 1 | **Deleted (`_patch_model_cache_comparison`)** |
| UNKNOWN_RETAIN | 11 | Kept, blockers listed (§23) |

## 16. Deletion manifest summary

Full internal manifest verified before editing; anchors asserted programmatically. All ranges refer to pre-prune line numbers at checkpoint `36b895d`.

| # | Block | Old lines | ~LOC | Category | Callers found | Enabling flag | Tests | Canonical replacement | Confidence |
|---|---|---|---:|---|---|---|---|---|---|
| D1a | `_patch_scheduler_clip_encode_prefetch` | 14298–14333 | 36 | SUPERSEDED_EXPERIMENT | `_start_scheduler_test` only | request option `comfymodal_scheduler_test.enabled` | none | general CLIP encode cache (`_patch_clip_text_encode_cache`) | CONFIRMED |
| D1b | `_start_scheduler_test` | 14335–14832 | 498 | SUPERSEDED_EXPERIMENT | `run_prompt` 22595–22602; `run_prompt_stream` 23650–23658; routed from `__init__.py:3988–4040` (`comfymodal_scheduler_test` body key); sent by legacy harness `benchmark_modal_parallel_matrix.py:418` | same | none in `tests/` (browser specs are studio-side fakes) | clean-lane synchronous dispatch | CONFIRMED |
| D1c | `_scheduler_wait_and_finalize` | 14834–14954 | 121 | SUPERSEDED_EXPERIMENT | same two call sites | same | none | n/a | CONFIRMED |
| D1d | scheduler call-sites + emissions (`run_prompt` 22594–22604, 22781–22782; stream 23649–23676, 23700, 23993–23994) | — | ~45 | SUPERSEDED_EXPERIMENT | self | self | none | normal preflight path (dedented, behavior preserved) | CONFIRMED |
| D2a | Cold-UNET early-load constants + comments | 1282–1298 | 17 | SUPERSEDED_EXPERIMENT | cold-UNET methods only | `COMFYMODAL_COLD_UNET_EARLY_LOAD` (+`COMFYMODAL_ALLOW_SPECULATIVE_LOAD` escape hatch) | `test_production_plan_fix.py::test_cold_unet_early_load_disabled` → **rewritten to pin retirement** | snapshot restore + native fast-disk UNET | CONFIRMED |
| D2b | `_cold_unet_early_actual_load` + `_finalize_cold_unet_early_load` | 14068–14296 | 229 | SUPERSEDED_EXPERIMENT (speculative unjoined reads; E38C QUARANTINE list) | called unconditionally at 23645 but internally double-gated off; source-inspection marker in `benchmark_modal_e2e.py:1826` (slicing end-marker only; `find()==−1` degrades safely, checks still pass — verified by reading check #52 logic) | two flags above | `test_production_plan_fix.py` ×2 → rewritten | graph-demand actual-load seam retained for Phase G | CONFIRMED |
| D2c | cold-UNET trace map in stream trace assembly | 23924–23957 | 34 | SUPERSEDED_EXPERIMENT | self | self | none | n/a | CONFIRMED |
| D3 | `_patch_model_cache_comparison` (`LoadedModel.__eq__`) + install site 21361–21362 | 20056–20149 | 95 | PROVEN_DEAD (own docstring: "no measurable production win … 0 hits out of 3 calls"; observe/diagnostic-only; readers use `getattr(...,{})` defaults → safe) | install gated behind `deep_profile` (default off); no test refs | `deep_profile` | none | n/a | CONFIRMED |
| D4 | Deep-profile block in `_execute_in_process`: sampler-helper wraps + **second `load_models_gpu` wrapper layer** incl. `lmg_fastpath` control-flow bypass + warmup registration logging | 16877–16996 | 120 | SUPERSEDED_EXPERIMENT / MERGE-per-E38C §21 ("MUST DISABLE one of the two load_models_gpu wrapper layers") | installed per-request when `deep_profile=1`; result reader 22925–22938 (deleted with it); `.profile_config.json` legacy profile references become inert no-op | `deep_profile`, `lmg_fastpath`, `lmg_fastpath_dryrun` | none | Layer 1 generic model-management profiler (15850–15901, flag-gated observe-only) remains as the single observation boundary | CONFIRMED |
| D5 | `modelpatcher_trace` lineage tracing (second `ModelPatcher.clone` wrap + node patches) in `restore` | 21942–22027 | 86 | SUPERSEDED_EXPERIMENT (E38C QUARANTINE "second clone wrap"); observe-only; weak idempotence (could stack) | `_resolve_runtime_flag('modelpatcher_trace','0')` default off; emission reader 22912–22916 deleted with it | `modelpatcher_trace` | none | n/a | CONFIRMED |
| D6 | `modelpatcher_cache` experiment (wraps `comfy.sd.load_diffusion_model`) | 22029–22068 | 40 | SUPERSEDED_EXPERIMENT (duplicate cache wrapper beside canonical UNET cache seam; L5 quarantine candidate) | flag-gated off; `_mp_cache_store` local-only | `modelpatcher_cache`, `modelpatcher_cache_dryrun` | none | `_patch_unet_loader_cache` graph-demand seam | CONFIRMED |

Dependency-set note: `_comfy_modal_stable_key` producers/consumers existed **only** inside D4/D5/D6 — deleted together, zero dangling refs (verified by AST scan).

## 17. Extracted diagnostics

**None extracted in E39.** MOVE_TO_DIAGNOSTICS blocks were inventoried and classified (waterfall formatter 2021–2234, platform/storage diagnostics, RSS/fault/tensor forensics 9806–9895, RBG stall classification, per-stack metrics 13335–13458, PNG/restore-memory once-loggers, legacy critical-path recorder 9923–10290). Extraction was deferred deliberately: each touches shared lifecycle state (locks, volume handles, recorder TLS), and mid-flight extraction would have inflated regression risk against a single-gate budget without reducing runtime behavior. This is recorded as E40 debt (§37). The deep-profile emission that duplicated ledger-visible timing was removed outright instead.

## 18. Duplicate wrappers removed/consolidated

- **Two `load_models_gpu` wrapper layers → one.** Layer 2 (deep-profile `_profiled_lmg`, old lines 16898–16982) — which could stack around layer 1 and contained the `lmg_fastpath` bypass that *skipped the underlying physical model-management operation* — is deleted. Layer 1 (generic observe-only profiler, flag-gated) remains the single observation boundary. CONFIRMED against E38C §21 MUST-DISABLE item.
- **Two `ModelPatcher.clone` wraps → one.** The `modelpatcher_trace` second wrap (old 21997–21998) is deleted; the flag-gated profiler wrap (15791–15815) remains.
- **`LoadedModel.__eq__` cache-comparison patch** removed entirely (diagnostic-only, zero production hits).

## 19. Experiment generations removed

| Generation | Removed code | Era (L14 archaeology) |
|---|---|---|
| Scheduler benchmark harness | D1 (657 LOC + sites) | introduced `d124926b` 2026-06-09, never superseded — added beside demand paths |
| Cold UNET early-load (speculative unjoined reads) | D2 (~280 LOC + sites) | introduced `af16f1dc` 2026-06-10 |
| Deep sampler/load profiler + lmg fastpath | D4 | E28-era diagnostics family |
| ModelPatcher lineage tracer | D5 | identity-divergence investigation tool |
| ModelPatcher cache experiment | D6 | introduced `f96cc9c1` 2026-06-03 |
| LoadedModel.__eq__ comparison patch | D3 | E28-era cache-dedup diagnostic |

## 20. Legacy config aliases removed

- `COMFYMODAL_COLD_UNET_EARLY_LOAD`, `COMFYMODAL_COLD_UNET_EARLY_LOAD_MODE`, `COMFYMODAL_COLD_UNET_EARLY_LOAD_BUDGET_MS`, `COMFYMODAL_COLD_UNET_REQUIRE_CPU_CACHE_HIT`, `COMFYMODAL_COLD_UNET_MAX_FILE_GB`, `COMFYMODAL_COLD_UNET_DISABLE_ON_VOLUME_STALL`, `COMFYMODAL_COLD_UNET_DEBUG` (implementation + reads).
- Runtime-flag names `lmg_fastpath`, `lmg_fastpath_dryrun`, `modelpatcher_trace`, `modelpatcher_cache`, `modelpatcher_cache_dryrun`, `deep_profile` consumers (the `_resolve_runtime_flag` dynamic lookup mechanism itself is RETAINED — it is the supported mechanism behind the live `set_runtime_flag` endpoint used by `benchmark_modal.py:36` and `__init__.py`).

## 21. Ownership systems removed/simplified

**None removed.** L9 proved `_ACTIVE_MODEL_READS` (+FUSE governor), `_MODEL_LOAD_CONTEXT`, restore-preload handle events, production UNET gates, and the direct-sink registries are all consumed by Golden/fallback paths. The confirmed `restore_clip_loader` vs `restore_preload` owner-key mismatch blast radius was fully mapped (producer `comfyapp.py:11858` role-map → registered at 11876; consumer equality check at 12323; explicit handle join at 21708–21724 independent) and is left for E40's authority canonicalization per plan — E39 must not rewrite lease semantics.

## 22. Remaining known conflicting implementations

1. CLIP arms: QD4 (Golden) / FastSafe (fallback arm) / native demand (fallback) / speculative lane (armed-but-suppressed via inherited flag `COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION=1` + clean-lane runtime short-circuit) / CPU-snapshot bind. E40 centralizes selection.
2. Two configuration truth systems (deploy-baked env vs ResolvedConfig projection); ~20 direct env-read families bypass the registry.
3. Identity systems: deployment_spec vs v2ctl fingerprints vs source-probe vs runtime-shape/generation.
4. Three overlapping GPU-release authorities (free_memory/soft_empty_cache + teardown diagnostics + single-use exit).
5. `restore_clip_loader`/`restore_preload` owner-key mismatch (live; E40).
6. mtime-based collectors remain selectable in legacy delivery paths (compat fallback; strict-canonical selector untouched per E38B §18).

## 23. Remaining UNKNOWN_RETAIN blocks and exact blockers

| Block | Blocker |
|---|---|
| `EXPERIMENTAL_RESTORE_BACKGROUND_CODE` gate (1312–1321, 1387 + 10 call sites) | Gates live async-actual-load/RBG fallback machinery; deleting changes fallback structure. Not a dead branch. E40 must decide semantics. |
| `clear_runtime_flag` / `clear_runtime_flags` / `reset_runtime_defaults` endpoints | Public Modal methods; external deployed callers cannot be ruled out from this repo. |
| `PROMPT_ASYNC_PRELOAD` prompt-time preload path | Flag-off by default; no retirement proof; adjacent to Phase-G preload work. |
| Rehoming/pretouch remnants | Scattered instrumentation; no independent enabled route found, but no exhaustive proof of absence. |
| `COMFYMODAL_E16_READ_ONLY_VOLUME_LOOKUP` | Volume-lookup implementation reachability unproven. |
| Warmup machinery (`ENABLE_WARMUP`, `DIRECT_WARMUP_*`, `_warmup_direct`) | Live fallback/tooling per L8 keep-list. |
| Observe-only profiler family (layer-1, KSAMPLER, guider, execution.execute) | Consumed by legacy benchmark result parsing; flag-gated harmless when off. |
| PNG/restore-memory once-loggers | Adjacent to Golden encode path; marginal gain vs hot-path edit risk. |
| Waterfall recorder/formatter | E40 owns `v2_waterfall.py` contract changes (E38B §17). |
| Legacy critical-path recorder (9923–10290) | E38B §18: do not maintain two accounting authorities — but replacement requires consumer migration first. |
| Scheduler-test routing in `__init__.py` | Outside single-writer scope for `comfyapp.py`; now inert passthrough. |

## 24. Exact Golden Path after pruning

Unchanged semantically; fewer structural participants:

```
v2ctl deploy-run --profile e37-clean-lane-qd4
→ deploy_and_run_v2_single.bat → benchmark_v2_direct (--verify-e28-profile)
→ ModalRuntimeEntrypointV2.run_plan_stream (single-use container)
→ clean_lane.begin_request → restore() [MINIMAL_RESTORE, CpuSnapshotModels]
→ plan identity complete
→ synchronous QD4 (clip_qd_reader; launch_policy=clean_lane_post_restore;
   32 MiB × 240 ranges; configured/observed QD 4; quiescence proof)
→ QdGpuOwner publish → take (source+demand side) → bind → forward
→ conditioning forced miss → real encode (clean_lane_forced_miss)
→ UNET snapshot structure → native fast-disk route → load_models_gpu boundary
   [single observation boundary] → Comfy publication
→ sampling → late VAE activation (UNET wait) → decode
→ DirectOutputSink → structured selector → first durable result
→ single-use teardown / container exit
```

Speculative hydration can no longer install any execution machinery from `comfyapp.py` (its only remaining participation is the runtime-module suppression seam owned by `comfymodal_runtime/speculative_clip_hydration.py`, unchanged by design).

## 25. Exact supported fallback paths after pruning

- Native Comfy CLIP demand load (behind custom arms) — intact.
- FastSafe CLIP hydration arm — intact (required fallback behind wiring dispatch).
- Generic Comfy UNET demand/publication — intact (Phase-G proven-ready seam preserved).
- Native VAELoader on snapshot miss; deferred-VAE worker + fail-open UNET-wait coordinator — intact.
- Warmup/restore-background machinery — intact.
- mtime/history collectors as non-canonical delivery fallback — intact.
- `run_prompt` / `run_prompt_stream` / `run_checkpoint_stream` compatibility endpoints — intact (proven callers: `modal_client.py`, `canonical_execution.py`, `modal_transport.py`).

## 26. Explicit Phase-G future code retained (why)

- `strip_clip_weights` / CLIP snapshot-exclusion support (runtime modules) — E40 lean-CLIP A/B depends on it. Verified present.
- CpuSnapshotModels full-value retention behavior — CONTROL arm of E40 A/B.
- ExecutionPlan/seed structures, `_pre_graph_cache_identity_key`, prompt-signature cache — scheduler/workflow capsule work.
- Conditioning-cache production implementation + `clean_lane_forced_miss` benchmark semantics — verified present post-prune (gate telemetry `conditioning_cache = forced_miss`).
- Async actual-load seam (`_prompt_async_actual_load`), background/production UNET publication, UNET/VAE ownership gates — proven-ready investigation.
- VAE deferral policy flags + coordinator — documented future candidate territory (pre-copy implementation itself does not exist in `comfyapp.py`; nothing to preserve there).
- Canonical critical-path ledger emitters and endpoints — untouched (E38B §18).

## 27. Changed files

| File | Change |
|---|---|
| `comfyapp.py` | −1,417 / +69 net lines (deletions per manifest §16) |
| `tests/test_production_plan_fix.py` | 2 stale cold-UNET tests rewritten as retirement-pinning tests; 2 pre-existing broken tests repaired (see §28) |

No other file modified. Scratch files used during the batch were removed.

## 28. Local tests (exact counts)

Method note: to separate pre-existing failures from regressions, each batch was run twice — once against pruned `comfyapp.py`, once against the byte-exact HEAD (`36b895d`) version swapped in via Python (PowerShell-redirect corruption was detected and corrected on the first baseline attempt) — and the FAILED-line sets were diffed.

| Suite | Result (pruned) | Pre-existing failures at HEAD | Regression |
|---|---|---:|---|
| `py_compile` (changed files) | PASS | — | — |
| `git diff --check` | PASS | — | — |
| test_e37_control_plane + test_e37_selector_routing + test_minimal_restore + test_e30_clip_qd_io | **69 passed** | 0 | none |
| test_e29_critical_path_ledger + test_e31_profiles + test_e35_plan_proof_local_repair + test_minimal_restore | **64 passed** | 0 | none |
| test_v2ctl_config/profiles/validation/provenance/fingerprints + test_e37_control_plane | **148 passed** | 0 | none |
| test_comfyapp_preload_state_machine + test_v2_observability_instrumentation + test_production_baseline | 242 passed / 38 failed | 38 (identical set, diff=0) | **none** |
| test_dependency_manifest_wiring/lifecycle + test_modal_app_identity + test_comfyapp_auto_warmup | 278 passed / 32 failed | 32 (identical set, diff=0) | **none** |
| test_safety_architecture + test_v2_prompt_executor + test_v2_transport_boundaries + test_clip_vae_request_activation | 169 passed / 15 failed | 16 (HEAD) vs 15 (pruned) | **none — one pre-existing failure FIXED** (`TestPreloadAccountingExtended::test_abort_returns_pending_not_submitted`) |
| test_e28_critical_path + test_rbg_unet_done_events_init + test_model_preload_attribution + test_optimizations + test_custom_node_generation_parity | 347 passed / 3 failed | 3 (identical set, diff=0) | **none** |
| test_unet_cache_future_handoff + test_unet_cache_init_actual_load_registry + test_deployment_proof | **30 passed** | 0 | none |
| test_benchmark_v2_proof_collection + test_v2ctl_backend/cli/invocation_writer/source_probe | **115 passed, 2 skipped** | 0 | none |
| test_production_plan_fix (updated) | **25 passed** | was failing pre-E39 (stale imports) | repaired |

Static analysis: AST parse OK; all 51 test-imported required symbols present; all 13 required mixin methods present; all 6 deleted methods confirmed absent; zero dangling references to any deleted name repo-wide (excluding backups/reference archives).

Pre-existing failures (identical at HEAD) stem from stale test expectations against removed mechanisms (`_PRODUCTION_BASELINE_OVERRIDES`, `_resolve_production_baseline_flag`, sage baseline overrides, etc.) — they pin mechanisms that no longer exist at `36b895d` and are E40 test-debt, intentionally not mass-repaired in E39 to keep the change surface minimal.

## 29. Full remote validation command

```
python tools/v2ctl.py deploy-run --profile e37-clean-lane-qd4
python tools/v2ctl.py gate --profile e37-clean-lane-qd4
```

Raw console capture (verbatim):

```
[v2ctl.deploy-run] profile=e37-clean-lane-qd4 deploy_fingerprint=4e32e944a17ff73e002a04877eba4bd1ff76078bdc8d21c2243194e7f61e9625
[v2ctl.deploy-run] command="...\deploy_and_run_v2_single.bat" E37_CLEAN_LANE_VALIDATION
[v2ctl.deploy-run] exit=0 manifest=...\.v2ctl\deployments\deploy_20260821-210508_4e32e944.json
[v2ctl.gate] valid=1 manifest=...\.v2ctl\gates\gate_20260822-020732_7971d2b3.json
```

Doctor pre-flight (verbatim excerpt): `git.head=36b895db… git.branch=TESTING2 git.dirty=1 profiles=…,e37-clean-lane-qd4,… deploy.lock=none deployment.fingerprint.match=0` (deploy correctly required).

## 30. Complete raw remote logs

Canonical artifacts (full fidelity; excerpts below):

- Gate JSON: `.v2ctl/gates/gate_20260822-020732_7971d2b3.json` (`gate_valid: true`, `reasons: []`)
- Run sample: `C:\...\comfymodal-data\benchmarks\runs\v2_2026-08-22_02-06-19\run_001_sample.json` (+ `.v2ctl-provenance.json`, `campaign_manifest.json`, `summary.json`, `run_0.json`)
- Deploy manifest: `.v2ctl/deployments/deploy_20260821-210508_4e32e944.json`

**Canonical ledger event sequence (complete, 31 events, verbatim names + decisive metadata):**

```
[0]  modal_restore_entry
[1]  bootstrap_restore_entry            {source: runtime_bootstrap.restore}
[2]  modal_restore_exit                 {status: restored}
[3]  modal_method_entry
[4]  plan_deserialize_start
[5]  plan_received
[6]  clip_loader_start                  {loader_arm: common_loader_boundary}
[7]  clip_qd_source_submit_start        {block_bytes: 33554432, device: cuda:0,
                                         file_bytes: 8044936192,
                                         launch_policy: clean_lane_post_restore,
                                         n_ranges: 240,
                                         path: .../text_encoders/qwen_3_4b.safetensors}
[8]  clip_qd_copy_to_device_start       {gpu_bytes: 8044936192, pinned_bytes: 268435456}
[9]  clip_qd_source_first_completion    {latency_ms: 23.2887}
[10] clip_qd_source_last_completion     {latency_ms: 1395.2915, wall_ms: 1418.5802}
[11] clip_qd_source_submit_end          {wall_ms: 1418.5802}
[12] clip_qd_copy_to_device_end         {h2d_device_ms: 39.0474, h2d_host_issue_total_ms: 142.051}
[13] clip_qd_stats                      {aggregate_gbps: 5.6711, buffer_pool_wait_ms: 2.4263,
                                         bytes_read: 8044936192, completion_count: 240,
                                         configured_qd: 4, file_bytes: 8044936192,
                                         launch_policy: clean_lane_post_restore,
                                         observed_max_outstanding: 4, per_read_errors: 0,
                                         steady_state_gbps: 1.6301, submit_count: 240,
                                         syscall_mode: preadv, total_source_wall_ms: 1418.5802}
[14] clip_qd_device_ready               {aggregate_gbps: 5.6711, h2d_device_ms: 39.0474, wall_ms: 1427.9628}
[15] clip_qd_owner_created              {gpu_bytes: 8044936192, pinned_bytes: 268435456, tensor_count: 398}
[16] clip_qd_spec_record_publish        {qd: 4, tensor_count: 398, wall_ms: 1418.5802}
[17] clip_qd_take                       {source_side: true, taken: true}
[18] clip_qd_bind                       {device: cuda:0, source_side: true, tensor_count: 398}
[19] clip_qd_owner_retained             {source_side: true}
[20] clip_qd_take                       {demand_side: true, files: 1, qd_used: true, taken: true}
[21] clip_qd_bind                       {demand_side: true, qd_used: true}
[22] clip_qd_owner_retained             {demand_side: true, owners: 1, qd_used: true}
[23] clip_device_ready                  {hydration_source: qd_demand, loader_arm: qd_demand}
[24] sampling_end                       {duration_ms: 4885.831, node_id: 1242}
[25] sampler_finally_done               {node_id: 1242}
[26] post_vae_decode                    {decode_wall_ms: 466.356}
[27] graph_next_node_after_sampler
[28] result_assembly_start              {items: 1, strategy: direct_output_sink}
[29] output_persist_done
[30] first_durable_result
```

Gate telemetry verdict fields (verbatim): `canonical_ledger=present`, `canonical_ledger_status=ok`, `canonical_ledger_zero_gap=True`, `FINAL_REQUEST_PREFLIGHT=PASS`, `fresh=True`, `fresh_required=true`, `conditioning_cache=forced_miss`, `backend_exit_code=0`, `backend_ok=true`, `provenance_validation_status=validated`, `TARGET_MATCH=YES`, `D1_PROOF_COVERS=true`.

## 31. Remote gate artifact path/ID

- Gate: `.v2ctl/gates/gate_20260822-020732_7971d2b3.json` — `gate_valid = true`
- Deploy fingerprint: `4e32e944a17ff73e002a04877eba4bd1ff76078bdc8d21c2243194e7f61e9625`
- Run fingerprint: `7971d2b3a333ff7c65255ac26cca1be01b9040e774c5f49b465ee99f80f3ac1c`
- Request ID: `v2-benchmark-0-c07e5169ff13`
- Deployment manifest: `.v2ctl/deployments/deploy_20260821-210508_4e32e944.json`
- Pruned-source dirty hash recorded in deploy inputs: `comfyapp.py = 73942eab3a65c0ef635bea782606e3b85aed74f7`

## 32. Output SHA proof

`output_sha = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
`expected_output_sha = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260`
**Exact match. CONFIRMED.**

## 33. QD 4/4 and 240/240 proof

`configured_qd = 4`, `observed_max_outstanding = 4`, `submit_count = 240`, `completion_count = 240`, `block_bytes = 33554432` (32 MiB), `per_read_errors = 0`. CONFIRMED.

## 34. No-fallback proof

- `clip_qd_stats.per_read_errors = 0`; all 240 completions received; `clip_qd_device_ready` reached; bind succeeded from QD owner (`taken=true`, `owners=1`).
- Demand side consumed the published QD record (`qd_used=true`) — no secondary read, no FastSafe/native re-read event exists anywhere in the 31-event ledger.
- `full_trace.backend.fallback_attempted = False`.
- No speculative-lane event appears in the ledger (suppression held; and post-E39 `comfyapp.py` contains no speculative execution machinery at all).

## 35. Post-prune structural comparison against E37

| Predicate | E37 reference gate | E39 post-prune gate | Match |
|---|---|---|---|
| Output SHA | `20b10e1f…90e5260` | identical | ✅ |
| Profile / atomicity | `e37-clean-lane-qd4`, ATOMIC_PROFILE E37_CLEAN_LANE | identical | ✅ |
| QD selected/configured/observed | yes / 4 / 4 | yes / 4 / 4 | ✅ |
| Source blocks | 240/240 | 240/240 | ✅ |
| Source errors / fallback | none / false | 0 / false | ✅ |
| Launch policy | clean_lane_post_restore | clean_lane_post_restore | ✅ |
| Conditioning | hit=false, miss_count=1, forced miss, encode_calls=1, persisted=0 | forced_miss, real encode, persist disabled | ✅ |
| Lifecycle ordering | restore → plan identity → QD start → ready → bind → forward | identical ledger order ([0]→[23]) | ✅ |
| Forbidden GPU overlap | none | none | ✅ |
| First durable result | present | present ([30]) | ✅ |
| Backend exit | success | exit_code=0 | ✅ |
| Provenance/source/config evidence | validated | validated | ✅ |
| Structural participants | speculative armed-suppressed; dual lmg wrappers installable; `__eq__` patch installable under deep_profile | speculative machinery absent from comfyapp; single lmg observation boundary; `__eq__` patch gone | **reduced** |

This gate is a correctness/structural regression gate; **no performance conclusions are drawn from it** (wall values differ run-to-run and QD throughput differs from the E37 reference run for environmental reasons).

## 36. Git diff summary

```
 comfyapp.py                       | 1421 +------------------------------------
 tests/test_production_plan_fix.py |   69 +-
 2 files changed, 73 insertions(+), 1417 deletions(-)
```

Base: checkpoint `36b895d`. No branch, no worktree, no reset/revert/stash, no push. Worktree otherwise untouched.

## 37. Remaining debt that E40 must handle

1. Fix `restore_clip_loader` vs `restore_preload` owner-key mismatch (map in §21/L9) and unify the lease-token namespace.
2. Canonicalize configuration truth through ResolvedConfig; intercept the ~20 direct env-read families + dynamic alias bypass (L8 table).
3. Decide `EXPERIMENTAL_RESTORE_BACKGROUND_CODE` semantics (delete-or-keep decision across its 10 gated sites).
4. Unify CLIP arm selection into one ClipLoader policy; convert the inherited speculative flag to explicit recorded suppression (`requested=1, effective=0, reason=clean_lane`).
5. Timing contract: `v2_waterfall.py` scheduling-window fix, `validation_status`→`diagnostic_status`, ledger-consuming validator predicates (E38B §17); then migrate/retire the legacy critical-path recorder and extract MOVE_TO_DIAGNOSTICS inventory (§17) to `comfymodal_runtime/diagnostics.py`.
6. Lean-CLIP A/B: new profile extending `e37-clean-lane-qd4` overriding only `COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS="1"` with E38A §13 preflight predicates.
7. Retire-with-proof candidates: legacy benchmark_modal* harness family (now partially inert: scheduler modes no-op), `__init__.py` scheduler routing, stale test repairs enumerated in §28.

---

## Final questions — direct answers

1. **How much of `comfyapp.py` was actually outside Golden Path / Phase G?** Provably: ~1.36k LOC (5.6%) — five superseded experiment generations plus one dead diagnostic patch. Everything else is Golden-required, Phase-G-required, fail-closed fallback, or supported-compat (Modal endpoints, legacy benchmark callers, test-pinned contracts).
2. **How many lines were deleted?** 1,359 net (−1,417/+69 gross across both files; 1,359 from `comfyapp.py`).
3. **How many were moved?** Zero. Extraction deferred to E40 with rationale (§17).
4. **How many remain?** 23,091.
5. **Largest surviving block and why?** `restore()` (~2.0k LOC): it is the Golden lifecycle itself — volumes, custom-node sync, dependency policy, preload join, patch installation, warmup gating — every segment of which is Golden-required, fallback-required, or Phase-G-required; splitting it is architecture work, not pruning.
6. **Which old experiment generations were removed?** Scheduler benchmark harness (June 9 era), cold-UNET early-load (June 10), deep sampler/lmg-fastpath profiler, ModelPatcher lineage tracer, ModelPatcher cache experiment (June 3), LoadedModel.__eq__ patch.
7. **Which competing loader paths still remain and why?** FastSafe arm and native Comfy demand (fail-closed fallbacks per E38C), generic Comfy UNET publication (Phase-G proven-ready seam), speculative lane module (runtime-owned suppression seam; E40 centralizes arm selection).
8. **Which ownership systems still remain and why?** All of them (§21) — none provably dead; they implement duplicate suppression, FUSE admission, join/wait, and gate semantics consumed by Golden/fallback.
9. **Are two `load_models_gpu` wrappers still possible?** No. Layer 2 is deleted; layer 1 is idempotent-sentineled and flag-gated. One observation boundary remains.
10. **Are two ModelPatcher clone wrappers still possible?** No. The second (lineage-tracer) wrap is deleted.
11. **Can speculative CLIP execute in the Golden profile after E39?** Less than before: `comfyapp.py` contains no speculative execution machinery anymore; the residual armed flag lives in runtime modules whose launch is short-circuited by `clean_lane.enabled()` — E40 converts that to explicit absence.
12. **Can FastSafe/native unexpectedly execute after successful Golden QD?** No — proven by the ledger: single take/bind from the QD owner, `qd_used=true`, no re-read events, `fallback_attempted=False`.
13. **Can a CLIP restore preload still be missed because of the owner-key mismatch?** Yes — the mismatch is retained by design (E40 scope); in the E37/E39 Golden profile restore-preload is disabled anyway, and the gate's `FINAL_REQUEST_PREFLIGHT=PASS` confirms the request path is sound.
14. **Can an old env alias silently select a retired path?** Not for anything deleted: all cold-UNET/scheduler/fastpath/modelpatcher flags and their implementations are gone together. Remaining aliases select surviving paths only.
15. **Can mtime selection affect the canonical Golden output?** No — Golden delivery is DirectOutputSink + structured selector; mtime scans survive only in legacy compat delivery paths.
16. **Does `comfyapp.py` still contain instrumentation that changes scheduling/control flow?** The known offender class was removed where proven (lmg fastpath bypass, `__eq__` matching). Remaining flag-gated policy (FUSE governor, DEFER_VAE, RBG gates) is scheduling policy by design, not disguised instrumentation; per-stack metrics persistence stays opt-in/off.
17. **Is the post-E39 Golden path easier to express as one deterministic algorithm?** Yes measurably: the request path lost its scheduler-test fork, its speculative early-load fork, and two wrapper layers; the ledger event sequence is now a strictly linear proof chain.
18. **What was deliberately retained solely because E40/later Phase G needs it?** §26 list (exclusion support, snapshot retention, ExecutionPlan/seed, actual-load seam, conditioning cache, ledger emitters) plus §23 UNKNOWN_RETAIN items pending proof.
19. **What could still be deleted later but is not yet sufficiently proven?** §23 blockers: EXPERIMENTAL_RESTORE_BACKGROUND_CODE branches, clear-runtime-flag/reset endpoints (external callers), PROMPT_ASYNC_PRELOAD, warmup machinery (if Phase G retires warm-capable containers), observe-only profiler family (when legacy harnesses retire), legacy critical-path recorder (after consumer migration), waterfall formatter (with E40 v2_waterfall work).
20. **Did the post-prune cold gate preserve exact output and E37 structural behavior?** Yes — exact SHA match, QD 4/4, 240/240, zero errors, no fallback, identical lifecycle ordering, valid gate on the first attempt; remote work stopped there per plan (no confirmation cohort, no G1).

---

## Addendum — 3 additional post-gate runs (user-requested 2026-08-22)

Three further single-run executions via `python tools/v2ctl.py run --profile e37-clean-lane-qd4` with 20 s gaps (raw logs: `E39_RUN2_LOG.txt`, `E39_RUN3_LOG.txt`, `E39_RUN4_LOG.txt`). All exit=0 against the same deployment fingerprint `4e32e944…`; each a fresh single-use container with its own conditioning-cache nonce.

| Run | Request ID | SHA match | QD cfg/obs | Blocks | Errors | Fallback | Durable | Ledger |
|---|---|---|---|---|---:|---:|---|---|
| 2 | `v2-benchmark-0-22040304b82d` | ✅ exact | 4 / 4 | 240/240 | 0 | false | ✅ | ok |
| 3 | `v2-benchmark-0-b02160d14b6d` | ✅ exact | 4 / 4 | 240/240 | 0 | false | ✅ | ok |
| 4 | `v2-benchmark-0-13f7430581e2` | ✅ exact | 4 / 4 | 240/240 | 0 | false | ✅ | ok |

Verdict: post-prune behavior is stable across repeated cold runs — identical structural proof chain every time. These runs remain correctness/structural checks; no performance conclusions are drawn from them.
