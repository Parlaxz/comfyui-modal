# V2 Batch D6 — Phase-D Integration Preflight

- **Date:** 2026-08-15
- **Branch:** current main only · no branch · no worktree · **commit: none**
- **Modal requests: 0 · deploys: 0 · paid runs: 0 · C4 untouched**
- **Environment:** Windows, Python 3.11.9, torch 2.8.0+cu128 (RTX 3070, CUDA
  available), pytest 9.1.1, unittest runner (`python run_tests.py`),
  fastsafetensors 0.3.3 installed locally
- **Deployment identity (frozen):** `.deployed_state.json` — app
  `stable-modal-comfy-v2-c9qd-shadow`, ComfyUI `f49bdb655707b97952dcef40e12e5af1f08d2007`
  v0.24.0, `comfyui_core_match=1` (local ComfyUI root IS the pinned revision),
  `deployment_combined_hash=d0c3dfef…`, `custom_nodes_generation=8ed7b482…`

---

## 0. Executive verdict

> **READY_FOR_ONE_REMOTE_D6_RUN = YES**

The complete current tree is structurally safe for one canonical true-cold
cache-MISS run. All Phase-D integration defects found during this gate were
repaired locally; every known red test state was either fixed or proven
pre-existing from history and documented precisely; the only remaining red
tests are 7 environment-level failures whose mechanism is byte-identical at
HEAD (CacheDiT preimport gate on a local site-packages that cannot satisfy
it) — excluded from the Phase-D gate, documented in §11.5.

Integration status, per-task evidence, and the exact canonical D6
configuration follow.

---

## 1. Task 1 — Concurrent-edit reconciliation

Full diff audit of the nine focus files against HEAD `a6a755e` (oracle lane,
cross-checked against the tree):

| File | Verdict | Notes |
|---|---|---|
| `comfymodal_runtime/modal_app.py` (+1590) | SAFE | The 6 VAE-key/spec match helpers (`_cpu_snapshot_spec_projection`, `_cpu_snapshot_specs_match`, `_cpu_snapshot_vae_projection`, `_cpu_snapshot_model_keys_match`, mismatch-reason helpers) are byte-identical to HEAD. D-phase additions are additive (shadow-probe methods ~15551+, prompt-signature/conditioning-prefetch priming ~16354+, clip-fh wiring 8868–8873/9403–9410 — flag-gated and idempotent). Dual `_preload_bridge` init mirrors HEAD's intentional dual-init pattern. |
| `comfymodal_runtime/model_preload.py` (+4091) | SAFE after fixes | Bridge install/retry/lane functions identical to HEAD; **two genuine defects fixed** (§2, §7): cross-sentinel double-wrap risk with D2 forensics; `resolve_unet_effective_dtype`'s unconditional `import comfy.cli_args` (unit-env fail-soft added). |
| `comfymodal_runtime/trace.py` (+124) | NEEDS_FIX → FIXED | Dict key renamed `constructed_class_instance` → `constructed_instance` (trace.py:905) while the canonical field list (trace.py:459) still read the old name → printed breakdown always `=absent`, two suites red. Fixed (see §2). |
| `comfymodal_runtime/cpu_snapshot_models.py` (+3) | SAFE | Only addition: `_comfymodal_clip_fh_excluded_weights` early-True in `_is_valid_clip_patcher` (flag-gated clip-fh exemption). |
| `comfymodal_runtime/runtime_executor.py` (+851) | SAFE | `install_pre_sampler_hooks` identical to HEAD; additions (`_derive_pass_outcome`, breakdown helpers) additive; no duplicate hook install. |
| `comfymodal_runtime/v2_waterfall.py` (+1865) | SAFE | New helpers + in-place `_STAGE_SPECS` edits; no duplicate stage definitions. |
| `canonical_execution.py` (+296) | SAFE | `_read_frozen_deployed_identity` coherent replacement; fail-closed logic self-consistent. |
| `tools/benchmark_v2_direct.py` (+1692) | SAFE | Additive formatters + `_prime_registry_proof` (8307), `--prime-registry-proof` registered (9099–9107). |
| `deploy_and_run_v2_single.bat` | SAFE | Defaults/profile changes + D1 priming in both V1/V2 branches; D6 pin block added (§5). |

**No duplicate wrapper-install conflict found:** `V2LoaderBridge.install`
(11550) is the single loader-class wrapper site; `install_demand_wrapper`
operates on the CLIP *instance* with its own marker; D2 forensics wraps with
its own sentinel. The one genuine overlap (D2 forensics ↔ core GPU wrappers
on the same 5 targets) was repaired with symmetric cross-sentinel guards
(§2/§7).

---

## 2. Task 2 — Red-test state eliminated

The D3-reported 18 failures (16 lifecycle + 2 preload bridge) were rerun and
reclassified after all writers finished. Final outcome: **zero Phase-D
regressions remain; every failure is fixed or proven pre-existing.**

### Genuine Phase-D regressions (fixed)

| Failure | Root cause | Fix |
|---|---|---|
| `test_v2_local_submission_timing` (`test_handle_cache_hit_absent_when_no_cache_event`) | trace.py:905 emits `constructed_instance`, field list at :459 still read `constructed_class_instance` | `trace.py:459` aligned to `constructed_instance`; both pinned tests updated to the new name. Suites now **172 OK**. |
| `test_v2_local_pre_submit_optimization` (`test_breakdown_print_has_handle_cache_fields`) | same rename | same fix. |

### Batch-order / environment failures (fixed at source)

The 6-suite batch (`lifecycle → cpu_snapshot_models → restore_only →
preload_bridge → manifest_hygiene → capture_hygiene`, 450 tests) had 3
failures caused by **sys.modules/sys.path pollution**: running
`tests/test_v2_cpu_snapshot_lifecycle.py` first left the REAL ComfyUI
`comfy` package importable in-process, changing behavior of later suites.

- **Polluter:** `CpuSnapshotUnetStatePropagationTests.test_extract_succeeds_on_real_propagated_event`
  (lifecycle:2735) executes `from tools.benchmark_v2_direct import
  _extract_unet_runtime_state_event`; `tools/benchmark_v2_direct.py` module
  body (lines 30–54) detects the ComfyUI root and `sys.path.insert(0,
  _COMFYUI_ROOT_DIR)`. A second module-level polluter existed at
  `tests/test_v2_snapshot_restore_only.py:62` (`import tools.benchmark_v2_direct`).
- **Fixes (test-side only):** polluter test now snapshots/restores
  `sys.path` + all `comfy*` sys.modules entries in a `finally`;
  `test_v2_snapshot_restore_only.py` import made hermetic; the three affected
  tests (`aimdo_disabled…`, `test_install_partial_then_retry`,
  `test_drain_worker_events_recovers_late_events`) made deterministic in both
  comfy-present and comfy-absent environments (fake `comfy` parent with
  `__path__=[]`, fake `comfy.cli_args`, `_comfy_hidden()` context manager).
- **Result:** batch 450/450 OK; `test_cpu_snapshot_models` standalone
  **147 OK** (was 9 errors); preload bridge **69 OK**; hermeticity proven
  both directions (fresh process stays non-importable; polluted process
  stays importable).

### Proven pre-existing (documented precisely, not Phase-D)

- **Suite A** (`test_v2_cpu_snapshot_lifecycle`, 6 FAIL + 3 ERROR): all 9
  reproduce identically at pristine HEAD (`git archive` verification). Root
  causes: (a) 6 tests encode the pre-`257b677` VAE-*excluded* matching
  contract; `257b677` "fix: require exact snapshot VAE for activation"
  (2026-08-03) intentionally made matching VAE-inclusive — tests were stale;
  (b) 3 E2E errors = `FileNotFoundError` for `flux_vae.safetensors` — the
  test's own setUp never created the fixture (nothing deleted it). **Fixed
  test-side to match the committed production contract** (VAE-inclusive
  assertions + fixture creation): 150/150 OK.
- **Suite B** (`test_v2_preload_bridge`, 10 FAIL): all 10 reproduce at
  pristine HEAD. Root cause: `ec936fb` (2026-07-25) added
  `resolve_unet_effective_dtype` → `import comfy.cli_args` to `_load_unet`
  after the tests were last touched; in unit env comfy is absent → worker
  lane always failed. **Fixed via runtime fail-soft** (§7, zero production
  impact — comfy always exists in the container) + one test assertion
  aligned to drain's copy-not-move semantics: 69/69 OK.
- **`test_modal_app_identity` (7 errors)** — see §11.5 (environmental,
  byte-identical gate at HEAD, excluded).

---

## 3. Task 3 — Deployed ComfyUI compatibility for D3 (verified against f49bdb6 source)

All 11 D3 production-wiring assumptions verified against the exact pinned
source (ComfyUI root `…\ComfyUI June Install\ComfyUI`, `comfy/`):

| Assumption | Verdict | Evidence |
|---|---|---|
| CLIP.load_sd dispatch (checkpoint vs file-list) | STRUCTURALLY GUARANTEED | sd.py:414-428, 260-262; nodes.py:984-992 |
| Leaf routing into inner modules; leaf-relative keys | STRUCTURALLY GUARANTEED | sd1_clip.py:308-309; sdxl_clip.py:64-68; sd3_clip.py:152-158; clip_model.py:192-210 |
| can_assign_sd convention | CONDITIONAL — never True natively | spray sets `patcher.is_dynamic()` (sd.py:418-426) = always False for CLIP (model_patcher.py:354-355; CoreModelPatcher alias at 2051); D3 forces its own spray (clip_fast_hydration.py:1056-1058) |
| Bytecode/string-literal probe validity | CONDITIONAL — strengthened | `SDClipModel.load_sd` passes; `SDXLClipG.load_sd` (sdxl_clip.py:16-17, `super().load_sd`) was a false-negative → **super()-chain resolution + assign-forward proof added** (§7) |
| `load_state_dict(assign=...)` call shape | STRUCTURALLY GUARANTEED | sd.py:416; sd1_clip.py:309; hydrate paths match (strict=False, assign=True) |
| State-dict conversion order & tensor identity | STRUCTURALLY GUARANTEED | conversions precede CLIP construction (sd.py:1466-1473 → 1715); identity-breakers (in_proj slice, text_projection transpose) correctly flagged non-identity by D3 gates |
| Tokenizer/non-tensor extraction | STRUCTURALLY GUARANTEED (with blob-key fix) | blobs are tensors, consumed via `.get()` never popped (sd.py:1509/1585/1544), tolerated by strict=False; **tokenizer-blob keys now excluded from dtype/identity gates** (§7) |
| Quantization metadata path | STRUCTURALLY GUARANTEED | sd.py:1313-1315; utils.py:1365-1423; detect_layer_quantization (utils.py:1358-1363); all three markers gated (comfy_quant/scaled_fp8/_quantization_metadata) |
| cached_patcher_init structure | STRUCTURALLY GUARANTEED | model_patcher.py:335; sd.py:1318 (2-tuple, args[0]=paths) — matches D2 parser (clip_cold_path_forensics.py:318-326) |
| ModelPatcher/CoreModelPatcher type | STRUCTURALLY GUARANTEED | sd.py:252-253; CoreModelPatcher = ModelPatcher (2051); is_dynamic False; hook_mode MinVram; is_clip True; compute dtype float32 (255-257) |
| TE initial/load/offload device behavior | STRUCTURALLY GUARANTEED | model_management.py:1116-1148; EAGER load iff initial==load (sd.py:280-281); meta params zero-init'd only when still meta at load (model_patcher.py:1017-1018) |

**Capability-gate strengthening applied (§7, all capability-based, no
model-name branches):** super()-chain leaf resolution (bounded 4 levels, fail
closed), assign-forward proof (leaf body must mention `load_state_dict` AND
`assign`), tokenizer-blob key exclusion (`spiece_model`, `tekken_model`,
`tokenizer_json`) from dtype/identity gates and bind-verification key sets,
and D3 demand-wrapper call-time re-resolution of the class method (D2/D3
wrapper-order independence).

---

## 4. Task 4 — fastsafetensors 0.3.3 dependency (proven locally)

- **Version verified:** local wheel IS 0.3.3 and byte-identical to the
  upstream 0.3.3 tag (loader.py, file_buffer.py, copier/*). 0.3.3 is the
  current latest release.
- **Invocation semantics vs 0.3.3 API:**
  | Claimed | Verdict |
  |---|---|
  | indexed device string `cuda:0` | ✓ (torch.device parse + Device.index; bare "cuda" also tolerated) |
  | `nogds=True` | ✓ (valid param; selects pread+bounce-buffer copier on Modal hosts) |
  | `use_buf_register=False` | ✓ param exists; code passes it explicitly everywhere (0.3.3 *default* is True, but inert under nogds — only the GDS copier reads it) |
  | ownership: loader+buffer outlive tensors; never close() while live | ✓ documented contract (file_buffer.py:68-77); both runtime modules attach owners (`_comfymodal_fastsafe_owner` / `_clip_fh_fastsafe_owner`) and close only on failure |
- **All local call shapes match 0.3.3** (unet_fastsafetensors.py:596-620;
  clip_fast_hydration.py:613-634).
- **Image pin — WAS CONDITIONAL, NOW FIXED:** `fastsafetensors==0.3.3` was
  installed only under the default-off `COMFYMODAL_V2_C9QD_EXTRAS` flag
  (modal_app.py:3415-3419). Now installed unconditionally in
  `_reference_image()` (line 3443); the C9QD block retains only
  `runai-model-streamer==0.16.1`. Verified: import + `_runtime_env` passthrough
  + source-text checks + `test_runtime_playground_v2` (69 OK). **DEPENDENCY
  OK.** No remote build performed.

---

## 5. Task 5 — Flag transport through the canonical vehicle (verified + repaired)

Trace: `deploy_and_run_v2_single.bat` → deploy-time shell → `_runtime_env()`
allowlist (modal_app.py:2920+) → Modal `cls(env=…)` (baked at deploy) →
container `os.environ` → `env_flag()/observability_gate()` reads.

- **Before:** only `COMFYMODAL_V2_UNET_FASTSAFETENSORS` was in the allowlist
  (3159-3161) and neither .bat set it; the other 8 flags were shell-only,
  **never shipped** (chain broke at the `_runtime_env` allowlist).
- **After:**
  1. `_runtime_env()` now passes through all 8 missing flags with defaults
     matching container `env_flag` defaults: `CLIP_FAST_HYDRATION=0`,
     `CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=0`, `CLIP_COLD_FORENSICS=0`,
     `CLIP_COLD_FORENSICS_CAST=0`, `CLIP_COLD_FORENSICS_SYNC_CUDA=0`,
     `INPUT_TYPES_WARM=1`, `UNET_FORENSICS=0` (modal_app.py:3162-3186).
  2. Both `deploy_and_run_v2_single.bat` (114-122) and `run_v2_single.bat`
     (51-59) pin the 9 flags with the same defaults (explicit caller values
     win; defaults preserve production behavior exactly).
  3. Passthrough proven by import test: with flags set, all 9 appear in the
     `_runtime_env()` dict.
- **Defaults verified:** `COMFYMODAL_V2_INPUT_TYPES_WARM` default True
  (modal_app.py:16449-16451); `COMFYMODAL_V2_UNET_FORENSICS` default OFF
  (unet_fastsafetensors.py:108-113).

---

## 6. Task 6 — Cache-MISS vehicle (implemented, NOT executed)

`tools/benchmark_v2_direct.py` gained `--unique-prompt-suffix <token>`
(parser ~9165; helper `_apply_unique_prompt_suffix` :438-472; applied right
after `_load_workflow()` :8568-8579; emitted
`[v2.unique_prompt_suffix] suffix=… applied to N text sources`; also recorded
in request-origin metadata).

- Appends the token to `PrimitiveStringMultiline.value` and literal
  `CLIPTextEncode.text` — changes BOTH `entry.text` and `workflow_hash`
  (whole-dict sha256) in the exact-conditioning cache key
  (`build_exact_key_components`, clip_conditioning_cache.py:259-303) →
  **guaranteed digest change → deterministic MISS**.
- Same workflow/model/settings otherwise; cache feature stays ON (only the
  key differs); exactly one real encode path (canonical workflow has ONE
  `CLIPTextEncode`; the negative is `ConditioningZeroOut`).
- Telemetry proof points: `clip_conditioning_cache_decision` = `miss_stored`,
  `encode_calls=1`; `clip_cold_cache_lookup` decision=miss; stdout
  `[v2.clip_conditioning_cache] decision=miss_stored`.
- Zero behavior change without the flag (12 new tests, incl. hash/cache-key
  mutation proofs and no-op default).

---

## 7. Runtime fixes applied (all flag-gated, fail-closed, no default change)

| Fix | File(s) |
|---|---|
| trace.py field list aligned to renamed key | `comfymodal_runtime/trace.py` (+2 pinned tests) |
| `_runtime_env()` passthrough for 8 flags | `comfymodal_runtime/modal_app.py` |
| unconditional `fastsafetensors==0.3.3` image pin | `comfymodal_runtime/modal_app.py` |
| 9-flag pin blocks in both launchers | `deploy_and_run_v2_single.bat`, `run_v2_single.bat` |
| CLIP capability gates: super()-chain probe, assign-forward proof, tokenizer-blob-key exclusion | `comfymodal_runtime/clip_fast_hydration.py`, `clip_fast_hydration_wiring.py` |
| D3 demand wrapper re-resolves class method at call time (D2/D3 order-independence) | `comfymodal_runtime/clip_fast_hydration.py` |
| D2↔core cross-sentinel guard on 5 shared targets (no double instrumentation) | `comfymodal_runtime/clip_cold_path_forensics.py`, `model_preload.py` |
| `resolve_unet_effective_dtype` fail-soft on missing comfy (unit-env only) | `comfymodal_runtime/model_preload.py` |
| sys.modules/sys.path hermeticity in test suites | `tests/test_v2_cpu_snapshot_lifecycle.py`, `test_cpu_snapshot_models.py`, `test_v2_snapshot_restore_only.py`, `test_v2_preload_bridge.py` |
| Suite-A VAE-inclusive contract alignment + fixture | `tests/test_v2_cpu_snapshot_lifecycle.py` |
| Cache-MISS vehicle `--unique-prompt-suffix` | `tools/benchmark_v2_direct.py` |

---

## 8. Tasks 7–10 — Telemetry reconciliation & safety proofs (tests added)

Existing coverage was inventoried lane-by-lane; gaps were filled with a new
integration suite:

- **T7 (D2/D3 reconcile)** — covered: cache-hit → `encode_calls=0` + zero
  hydration + `hydration_source=conditioning_cache_hit_no_hydration`;
  direct-GPU → `hydration_source=fastsafetensors_direct_gpu`,
  `fallback_count=0`. **Gap-filled:** D2 must NOT count a CPU→GPU transfer
  for D3-resident params (`resident_before=True`, `transfer_ops=0`,
  `total_h2d_bytes=0` — CUDA-gated + CPU-safe mock variants); native fallback
  recorded truthfully by D2 (`encode_calls=1`, gpu_wait span, exactly-once
  native loader); no leaked owner/partial state after fast-path failure.
- **T8 (D1 proof-store)** — fully covered by existing suites (all passing):
  prime vs frozen identity, fresh-process no-registry-import, store hit
  supplies registry+validation proofs, trigger→submission accounting with
  process-start overhead separate, stale identity fail-closed, workflow
  mismatch fail-closed.
- **T9 (D4/D5 compatibility)** — covered: D4 pipeline reconcile disjoint
  (22 phases, `accounting_disjoint=True`, GAP detection), deep profiler OFF
  by default, D5 top-level segments tile parent with nested non-accounting
  details, node non-wait semantics, exposed/hidden UNET wait on the current
  fastsafetensors event schema. **Gap-filled:** cross-summary disjointness —
  one synthetic trace through D2/D3/D4/D5 layers proves D3 hydration nested
  inside D2 walls, no interval attributed to two layer summaries, per-layer
  event-name isolation.
- **T10 (snapshot exclusion safety)** — covered: payload removed with
  manifest retained, cache-hit zero hydration, cache-miss one hydration +
  encode parity, fastsafe failure → native exactly once, RSS/CUDA checks.
  **Gap-filled:** corrupt/truncated/schema-mismatch/key-set-mismatch CLIP
  manifests fail closed (no strip, native path, no exception escapes);
  explicit tokenizer/structural retention assertion through the round trip;
  explicit no-meta/empty-invalid-model-escapes assertion post-fallback.

New suite `tests/test_v2_phase_d_telemetry_integration.py`: **11 passed,
1 skipped** (cloudpickle round-trip).

---

## 9. Task 11 — Full affected local matrix (final counts)

Supported runner: `python run_tests.py <modules>` (unittest). Sequential
runs, one process per batch, after all fixes landed:

| Batch | Suites | Result |
|---|---|---|
| D1+D2+D3 | batch_d1_local_dispatch, batch_d1_registry_proof_store, plan_validation_proof, deployment_proof, benchmark_v2_proof_collection, clip_cold_forensics, clip_fast_hydration_production | **130 OK** (1 skip) |
| D4+D5+C9+new | d4_forensics_reconciliation, batch_d5_wait_attribution, c9_fastsafetensors_integration, v2_unique_prompt_suffix, v2_phase_d_telemetry_integration, v2_conditioning_exact_hit_breakdown | **63 OK** (1 skip) |
| Lifecycle/snapshot/preload | v2_cpu_snapshot_lifecycle, cpu_snapshot_models, v2_snapshot_restore_only, v2_preload_bridge, v2_snapshot_manifest_hygiene_extensions, v2_snapshot_capture_hygiene | **450 OK** |
| Waterfall/timeline/breakdown | v2_waterfall, waterfall_reconciliation, waterfall_attach_central, waterfall_scheduling_denominator, v2_waterfall_contract, v2_waterfall_scheduling_contract, v2_per_node_timeline, v2_host_submission_breakdown, v2_local_submission_timing, v2_local_pre_submit_optimization | **228 OK** |
| Canonical/observability | v2_final_observability, step3_fast_path, runtime_playground_v2, v2_host_breakdown_lines, v2_prompt_executor_breakdown, modal_app_identity | **235 OK / 7 environmental errors** (§11.5) |
| Standalone harness | `python _test_clip_fast_hydration.py` | **9/9 PASS** |
| Compile sanity | py_compile of 104 runtime/tool modules (sequential) | **104/104 OK** |

Gate criteria:

- **no unexplained relevant failures** — yes: all Phase-D suites green; the
  only remaining red (7 modal_app_identity errors) is explained,
  environmental, byte-identical at HEAD (§11.5); one known Windows timer
  flake (`test_sync_count_and_wall_attributed`, `sync_ms` 0.0 tick
  quantization) passes on rerun.
- **py_compile/import sanity clean** — 104/104 (parallel runs can exhaust
  memory on this host — always run batches sequentially).
- **no duplicate wrapper installation** — cross-sentinel guards + 3 new
  tests (`TestCrossSentinelGuard`): core-first→skip, forensics-first→skip,
  all 5 shared targets covered; forensics suite 25/25.
- **no untracked runtime file omitted from packaging** — `V2_SOURCE_MODULES`
  closure tests (`TestV2SourceModulesClosure`) pass: `comfymodal_runtime`
  ships as a package so all D-phase modules (clip_fast_hydration,
  clip_fast_hydration_wiring, clip_cold_path_forensics, registry_proof_store,
  wait_attribution, unet_fastsafetensors, …) reach the image; repo-root
  untracked modules ship via comfyapp's `add_local_dir` combined copy and
  are not imported by the V2 runtime.
- **no default behavior changed with Phase-D flags OFF** — every pin default
  equals the container `env_flag` default; all new wiring is
  flag-gated/fail-closed (proven by flag-fail-closed and disabled-instance
  tests in the D2/D3/D4 suites).

---

## 10. Task 12 — The ONE later canonical D6 validation run (NOT executed)

### 10.1 Deployment (one canonical deployment, bakes all flags)

```
# In a shell that will run deploy_and_run_v2_single.bat:
set COMFYMODAL_V2_UNET_FASTSAFETENSORS=1
set COMFYMODAL_V2_CLIP_FAST_HYDRATION=1
set COMFYMODAL_V2_CLIP_SNAPSHOT_EXCLUDE_WEIGHTS=1
set COMFYMODAL_V2_CLIP_COLD_FORENSICS=1
set COMFYMODAL_V2_CLIP_COLD_FORENSICS_CAST=1
set COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA=1
set COMFYMODAL_V2_INPUT_TYPES_WARM=1
set COMFYMODAL_V2_UNET_FORENSICS=0
deploy_and_run_v2_single.bat
```

- Default mode `snapshot_restore_only` (restore-only shadow app, UNET
  excluded from CPU snapshot, clip_vae eviction retention, snapshot
  construction marker) — deploy + publish + identity record + D1
  `--prime-registry-proof`, then exit WITHOUT probes.
- The flags reach the container because `_runtime_env()` now carries them
  (Task 5). No QD sweep, no C4 hygiene experiment flags.

### 10.2 Run (exactly one true-cold request)

```
set V2_BENCHMARK_MODE=snapshot_restore_only
set V2_RESTORE_ONLY_RUN_COUNT=1
python tools\benchmark_v2_direct.py --snapshot-restore-only --unique-prompt-suffix <fresh-uuid-or-timestamp>
```

- Fresh unique suffix per run → conditioning-cache MISS (Task 6); cache
  feature remains ON; one real CLIP encode path (single CLIPTextEncode in
  the canonical workflow).
- No second run automatically: `V2_RESTORE_ONLY_RUN_COUNT=1`.

### 10.3 What the run validates (telemetry map)

| Area | Proof |
|---|---|
| D1 proof-store prime/hit + user trigger→submission + scheduling | `[v2.local_submission_breakdown]` fields, `node_registry_preload_ms`, `[v2.trigger_to_submission]`, store-hit without registry import |
| CLIP snapshot exclusion | `clip_fh_capture` status=excluded; stripped structure has zero param bytes |
| CLIP cache miss | `clip_conditioning_cache_decision=miss_stored`, `encode_calls=1`, `clip_cold_cache_lookup` miss |
| CLIP file→GPU wall/GBps | `clip_fh_hydration_end` file_to_gpu_wall_ms, gbps |
| CLIP bind / zero-copy / no full CPU payload | `bind_wall_ms`, zero_copy + evidence; `total_h2d_bytes≈0` in D2 summary |
| D2 activation/H2D accounting | `clip_cold_patcher_load_end` resident/transfer fields; `clip_cold_gpu_wait_start/end` |
| tokenize/encode/forward/residency | D2 `clip_cold_tokenize_/encode_/forward_` spans; resident_at_last_encode |
| exactly one hydration | demand wrapper + hydrated marker + `fallback_count=0` |
| exact output parity | forward parity assertions (production suite, fp16 tolerance) |
| UNET fastsafe chain | `unet_fastsafetensors_pipeline` + `[v2.fastsafe.reconcile]` (22 phases disjoint, status=OK) |
| meta execution/lifecycle breakdown | `meta_execution_wall_ms`/`meta_lifecycle_total_ms` + residual status |
| input_types_warm overlap | `input_types_warm_*` + overlap_meta_ms/overlap_fastsafe_ms |
| pipeline residual | `[v2.fastsafe.reconcile]` residual + status |
| exposed vs hidden loader wall | `unet_exposed_on_critical_path_ms` / `unet_hidden_under_other_work_ms` |
| remote setup reconciliation | `build_remote_setup_reconciliation` top-level segments tiling + residuals |
| ImpactSwitch/non-wait vs loader wait | per-node `node_non_wait_wall` + wait breakdown (loader_wait) |
| snapshot (provider/region/fingerprint/pre-Python/Python restore/gpu-state) | snapshot manifest, `[v2.startup_stage]`, region/cloud, host fingerprint, gpu-state restore events |
| Permanent footer | `COMMAND -> RESPONSE` · `Command (without scheduling) -> Response` · `Scheduling time` · **no TOTAL WALL** |

---

## 11. Remaining red tests — precise documentation

### 11.1 `test_modal_app_identity` — 7 errors (EXCLUDED: environmental, pre-existing)

`TestStartupIdentityCapture` (4), `TestV2CpuSnapshotPhaseSeparation` (2),
`TestV2LifecycleFailureAndTimingExport` (1) all call `entrypoint.startup()`
which runs the CacheDiT snapshot preimport gate
(`preimport_cachedit_family`, modal_app.py:1329) and raises
`RuntimeError("CacheDiT snapshot preimport FAILED … (image should have passed
build gate)")` when the preimport cannot succeed.

**Proof of pre-existence:** the identical gate exists at HEAD
(HEAD:8582-8590, same message); the test file is unmodified from HEAD; the
failure is a local site-packages state: `cache-dit` is not installed
(`pip show cache-dit` → not found) and the local `diffusers 0.14.0` cannot
import against `huggingface_hub 0.33.5` (`cannot import name
'cached_download'`). This environment cannot satisfy the gate at HEAD either;
the deployed image bakes these dependencies, so the gate is satisfied in the
container. **Not a Phase-D regression; no fix applied** (installing
env-level packages was out of scope for a local integration gate).

### 11.2 Known flake (documented, passes on rerun)

`tests.test_v2_clip_cold_forensics.test_sync_count_and_wall_attributed` —
Windows `time.monotonic_ns()` tick quantization against a 5 ms sleep can
record `sync_ms=0.0`; passes on rerun (final matrix run: OK).

---

## 12. Final status

```
integration status                  = COMPLETE (all 12 tasks closed)
concurrent conflicts found/fixed    = 2 runtime (trace.py field list; forensics↔core
                                      double-wrap) + 2 test-env (sys.modules pollution
                                      source + module-level polluter) — all fixed
remaining relevant test failures    = 0 (7 environmental modal_app_identity errors:
                                      pre-existing, documented §11.1; 1 known flake)
D1 proof-store path                 = VERIFIED (prime/hit, no-registry fresh process,
                                      dual proofs, trigger→submission accounting,
                                      fail-closed stale identity + workflow mismatch)
D2/D3 telemetry reconciliation      = VERIFIED (residency-aware D2 accounting, cache-hit
                                      zero hydration, fallback truthfulness, no leaks)
D3 deployed-Comfy compatibility     = VERIFIED vs f49bdb6 (9 guaranteed, 2 conditional
                                      → gates strengthened, fail-closed preserved)
fastsafetensors dependency          = VERIFIED 0.3.3 semantics; image pin fixed
                                      (unconditional) — was C9QD-conditional
snapshot exclusion safety           = VERIFIED (capture/restore/failure paths + 5 new
                                      corrupt-manifest/meta/retention tests)
D4 reconciliation                   = VERIFIED (disjoint 22-phase tile, meta lifecycle,
                                      deep profiler OFF by default)
D5 reconciliation                   = VERIFIED (top-level tiling, nested non-accounting,
                                      node non-wait, exposed/hidden on current schema,
                                      cross-layer no-double-count)
default-OFF behavior                = VERIFIED (all pins = env_flag defaults; flag-gated
                                      wiring; fail-closed everywhere)
files changed                       = see §7 (12 runtime/launcher + 4 test suites fixed,
                                      2 new test files, 1 new tool option)
tests and exact counts              = 130 + 63 + 450 + 228 + 235 OK (+7 pre-existing
                                      environmental errors) = 1106 unittest OK / 7 env
                                      errors; harness 9/9; py_compile 104/104
commit                              = none
Modal requests                      = 0
deploys                             = 0

READY_FOR_ONE_REMOTE_D6_RUN         = YES
```

Canonical command/env configuration: see §10 (deployment env block +
one-request run with a fresh `--unique-prompt-suffix`). **Not executed.**

---

## D10 cross-reference (appended 2026-08-16, no historical evidence changed)

**Status:** D10 = STOP_CAPTURE_GATE. Full report: `V2_BATCH_D10_PHASE_D_INTEGRATION_VALIDATION.md`.

- **1 deploy executed** (v43, 68.742 s, success) with the NEW D10 integration
  profile (D6 flags minus `COMFYMODAL_V2_CLIP_COLD_FORENSICS_SYNC_CUDA`; verifier
  `profile=d10_integration_validation` PASS; 15 profile tests OK).
- **No crash loop** (single startup attempt; D6 eviction fingerprint absent).
- **Gates A/B/C/E PASS in the real Modal container**: capture exclusion
  (EXCLUDED_PLACEHOLDER, cpu_bytes=0, meta_params=399), original CLIP dies
  (`original_clip_alive_after_full_eviction=0` — the F-B weakref fix holds),
  eviction reconcile (`excluded_after_eviction_reload`,
  `wrapper_installed=installed`, params_replaced=399), `Snapshot created` +
  successful restore (restore_count=1).
- **Gate D FAIL**: `capture_pre_snapshot_return state=INVALID/PARTIAL
  cpu_bytes=0 meta_params=0 total_params=0 manifest_eligible=False` (expected
  EXCLUDED_PLACEHOLDER / meta_params=399 / manifest_eligible=true). The
  reloaded CLIP shell loses its 399 meta params + manifest between the
  reconcile event (16:01:29.809Z) and the ready-return boundary (16:01:29.853Z).
- **No request issued** (hard gate). Identity recorded = `d679332c551f0cad`
  (≠ stale e8f269ee… / 3a156e5d…); D1 prime intentionally NOT run.
- **Next experiment (D10-F, zero spend):** local reconcile-to-capture object
  audit — assert `_cpu_snapshot_models` clip attribute at the ready-return
  boundary is the reconciled object with meta_params=399 + manifest; deploy
  again only after a local Gate-D-equivalent test passes.
- Local preflight: 729 unittest OK / 3 skips / 0 failures (incl. 15 D10
  profile tests) + py_compile OK. Commit = none. C4 = not run.
