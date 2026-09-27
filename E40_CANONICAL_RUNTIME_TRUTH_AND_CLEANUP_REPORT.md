# E40 — Canonical Runtime Truth, Aggressive Legacy Cleanup, and Deterministic Golden-Path Foundation

Batch: E40 · Date: 2026-08-22 · Checkout: authoritative local checkout (E40 owner)
Parallel batch: R41 (isolated worktree — untouched by E40)

---

## 1. Executive verdict

**PASS.** E40 establishes one explicit control plane for the Golden runtime and proves it remotely:

- One cold gate on the cleaned architecture: **gate_valid=1, reasons=[]**
- Exact output SHA: `20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (match)
- Loader selection observed exactly as requested: CLIP=`qd4_reader`, UNET=`cpu_snapshot_native`, VAE=`policy_v1`; **zero fallbacks**
- `runtime_status=NOMINAL` with empty reasons
- `resolved_config` fingerprint over **99 controls** emitted from the runtime and persisted in the run record
- Canonical ledger: `ok`
- No inherited speculative arm (explicitly disabled at profile + default-off at code level)

E39 was committed first (`0c59f46`) after raw-evidence repair. All E40 work remains **uncommitted** as required.

## 2. E39 raw-log repair

`E39_REMOTE_GATE_RAW_LOG.txt` was 3 lines. Rebuilt to ~2,929 lines / 112 KB exclusively from exact persisted artifacts:
`.v2ctl/gates/gate_20260822-020732_7971d2b3.json` (174-key remote telemetry capture), deploy record `deploy_20260821-210508_4e32e944.json`, three post-gate stability run records + their run dirs, summary/campaign manifest/provenance sidecar of `v2_2026-08-22_02-06-19`.
Verbatim console text is marked `UNRECOVERABLE_FROM_PERSISTED_ARTIFACTS` (`artifacts.console_capture=null`) with the structured equivalent cited for every such fact. No Modal execution was performed for the repair. Secret scan clean; `git diff --check` clean.

## 3. E39 commit SHA

- Commit: **`0c59f46e3238f421378e8852ebc548da815b70af`** — `e39: prune superseded comfyapp paths and preserve golden runtime`
- Timestamp: 2026-08-22T00:11:59-05:00 · parent `36b895d`
- comfyapp.py fingerprint at commit: `1e309b35e81ff23e9b59c3bf032d32906506bdc3ce9eb804a39b2feca5c0c7f9`
- Machine-readable marker for R41: `.v2ctl/E39_BASELINE_MARKER.json`

## 4. E40 file changes

Core E40 surface (37 files changed, +1880/−133 incl. tests/config):

| File | Δ |
|---|---|
| comfyapp.py | +190/−17 |
| comfymodal_runtime/modal_app.py | +132/−19 |
| tools/v2_control/validation.py | +160 |
| comfymodal_runtime/snapshot_capture_hygiene.py | +88 |
| comfymodal_runtime/snapshot_build_manifest.py | +121/−2 |
| comfymodal_runtime/clip_conditioning_cache.py | +106/−3 |
| comfymodal_runtime/v2_waterfall.py | +10/−10 |
| comfymodal_runtime/speculative_clip_hydration.py | default-on → default-off |
| comfymodal_runtime/clip_qd_reader.py | observation hook |
| comfymodal_runtime/experiment_result_store.py | +9 sample projection |
| comfymodal_runtime/loader_selection.py | NEW |
| comfymodal_runtime/config_authority.py | NEW (99 flags) |
| comfymodal_runtime/runtime_status.py | NEW |
| comfymodal_runtime/cache_taxonomy.py | NEW |
| __init__.py | owner canonicalization |
| config/v2/profiles/e37-clean-lane-qd4.toml | speculative=0 explicit |
| tools/benchmark_v2_direct.py | artifact extraction |
| tools/v2_control/backend.py, cli.py | crash-loop accounting |
| tests/test_e40_canonical_authority.py | NEW (27 tests) |

Unrelated concurrent edits present in the working tree (E2–E4 studio/history work by another agent) were preserved untouched per parallel-safety rules.

## 5. LOC removed/added by subsystem

- Configuration authority: +~365 (new module) / −0
- Loader selection & observation: +~200 / −8
- Ownership canonicalization: +12 / −6
- RuntimeStatus + validator: +~190 / −0
- Waterfall diagnostic rename: +10 / −10
- Snapshot quiescence/payload facts: +~320 / −5
- Cache taxonomy: +~60 (new)
- Crash-loop accounting: +~45 / −0
- Tests: +~330 (new file)
- Legacy deletions this batch: minimal — see §6; E39 already removed 1,359 LOC.

## 6. Deleted legacy paths

- `restore_clip_loader` producer identity — deleted (canonicalized to `restore_preload`), zero remaining occurrences.
- Speculative CLIP hydration as an inheritable/default-on arm — retired from the Golden path (code default flipped to OFF requiring explicit opt-in; profile pins `0`). Module retained DIAGNOSTIC_ONLY.
- Transient artifact baking into the production image — `comfyui-modal/output/`, `test-results/`, `playwright-report/` added to `_COMBINED_CUSTOM_NODE_IGNORE_PATTERNS` (removes software-created image variance and a deploy-failure class).
- COLD_UNET_EARLY_LOAD: already dead (removed in E39); retirement pinned by test.

## 7. Retained compatibility/fallback paths

- `EXPERIMENTAL_RESTORE_BACKGROUND_CODE`: DIAGNOSTIC_ONLY (default off, gated, policy=forbid overrides).
- CLIP hydration `cpu_standard` fallback: PRODUCTION_FALLBACK (correctness recovery; now recorded as fallback ≠ nominal).
- UNET fastsafetensors/meta-direct native fallbacks: PRODUCTION_FALLBACK (recorded).
- Waterfall legacy JSON key `validation_status` accepted on parse only (COMPATIBILITY_ONLY); export uses `diagnostic_status`.
- Deferred-VAE-during-RBG warm-path optimization: COMPATIBILITY_ONLY (not on cold Golden path).

## 8. Remaining UNKNOWN paths

- `comfyapp.py` retains ~68 direct env reads; the authority exposes all 99 Golden-semantics controls and detects unregistered mutations, but full read-site migration was deliberately not forced (risk control). Listed as debt.
- `DEFER_VAE_ACTUAL_LOAD_DURING_RBG_UNET` family: verified off on cold path; warm-path semantics not re-audited.
- Serialized Modal snapshot bytes: UNOBSERVABLE (recorded explicitly in manifest).

## 9. Configuration authority

`comfymodal_runtime/config_authority.py` is the single runtime-side resolver:
- `GOLDEN_CONTROL_FLAGS`: 99 flags across LOADER_SELECTION / EXECUTION_POLICY / CACHE_POLICY / SNAPSHOT_POLICY / TIMING_DIAGNOSTICS / DEPRECATED_DIAGNOSTIC, each with true source-verified defaults.
- `resolve(env)` reads once → frozen `ResolvedConfig` with typed values + sources; `fingerprint()` = sha256 over canonical JSON.
- `reconcile(deployed_env, runtime_env)` → per-flag agreement rows; `detect_unregistered_mutations()` flags algorithm-changing env vars outside the authority.
- comfyapp.py imports the authority at module init (`RESOLVED_CONFIG`, `UNREGISTERED_ENV_MUTATIONS`); modal_app seeds it per request and emits `{fingerprint, controls}` into the run record.
- Chain proven remotely: requested (profile TOML) → resolved (v2ctl ConfigResolver) → deployed (env projection, fingerprint `f15874bd…`) → effective/observed (runtime `resolved_config` block, fp `3480ad93…` over 99 controls).

## 10. Loader-selection authority

`comfymodal_runtime/loader_selection.py` — one registry, one vocabulary:
- Per role: requested / effective / observed / fallback_attempted / fallback_loader / fallback_reason.
- Requested derived ONLY from config authority (`requested_loader(role)`), precedence documented.
- Observation hooks: central read tracker completion (`comfyapp._complete_active_model_read`) + QD reader finalization (`clip_qd_reader._finalize_stats`); snapshot-resident arms realized by restore itself.
- Normalization maps raw tracker strings onto the canonical vocabulary; first successful arm wins; recovery arms recorded as fallbacks, never rewritten as planned.
- Remote proof (gate run): clip qd4_reader/qd4_reader/qd4_reader, unet cpu_snapshot_native×3, vae policy_v1×3, fallback_attempted=false everywhere.

## 11. Ownership authority

- Producer/consumer mismatch fixed: `"clip": "restore_clip_loader"` → `"restore_preload"` in both role maps (`comfyapp.RESTORE_ROLE_OWNER_MAP`, mirrored in `__init__.py`); preflight/coordinator now join the same name they wait on.
- Duplicated maps unified behind one constant; fail-closed join semantics and strong-reference lifetime unchanged.

## 12. RuntimeStatus

`comfymodal_runtime/runtime_status.py`: `NOMINAL | DEGRADED(reasons[]) | FAILED(reasons[])`; `classify()` distinguishes ABSENT / UNKNOWN / UNOBSERVABLE / INVALID vs legitimate numeric ZERO. Built once per run at result assembly from loader mismatches + ledger status; emitted as `runtime_status`.

## 13. StructuralValidator contract

Single acceptance authority remains `tools/v2_control/validation.py::StructuralValidator.validate` (+ GateRunner). E40 extensions (fail-closed when present, skipped when absent):
- `runtime_status` must be NOMINAL else `runtime_status_not_nominal:<status>` + reasons.
- `loader_selection`: fallback → `loader_fallback_<role>:req->fb`; observed≠effective → `loader_observed_mismatch_<role>`; requested≠effective → `loader_effective_mismatch_<role>`.
- `resolved_config.fingerprint` compared against deployed projection when comparable → `resolved_config_fingerprint_mismatch`.
Diagnostic renderers (waterfall `diagnostic_status`) are no longer acceptance-shaped.

## 14. Timing authority

`critical_path_ledger` remains the sole application-timeline authority (untouched core). Waterfall field renamed `validation_status`→`diagnostic_status` across report/export/consumers/tests with parse tolerance; clock-domain discipline (same-domain subtraction only, cross-process wall treated unreliable, missing rendered as absent `-` not 0) verified in place.

## 15. Snapshot contents/quiescence

- Capture boundary now **proves quiescence fail-closed**: conditioning-cache workers drained/joined (`quiesce_for_snapshot`), registered executors checked for pending work; non-quiescent ⇒ RuntimeError before snapshot. Hotfixed aggregation bug found during remote validation (see §27).
- Manifest records per-role `meta_parameter_count`, unique storage count/bytes, `process_rss_bytes` (explicitly labeled NOT snapshot size), cgroup memory fields, `serialized_snapshot_bytes: "UNOBSERVABLE"`.

## 16. Cache taxonomy

`comfymodal_runtime/cache_taxonomy.py` declares: SNAPSHOT_RESIDENT_STATIC_METADATA vs CONDITIONING_CACHE vs RUNTIME_MEMO vs REPORTING_STORE, each with Golden requirement (FORCED_MISS single-encode lane / OPTIONAL / REQUIRED_HIT-or-regenerate / FORBIDDEN). Conditioning: forced miss via cache nonce, encode_calls counted, persist=0 pinned by profile.

## 17. Source/deployment identities

`deployment_spec.build_deployment_identity()` confirmed authoritative (existence pinned by test). Distinct identities preserved: app source (git head + source probe), resolved-config fingerprint (NEW, runtime-emitted), runtime-shape fingerprint, dependency/registry identity, deploy invocation id, generation identity. Gate proved source agreement: `provenance_validation_status=validated`.

## 18. Environment aliases retired

- `COMFYMODAL_V2_SPECULATIVE_CLIP_HYDRATION` unset-value semantics changed: absent ⇒ OFF (was ON). Explicit opt-in required.
- Profile override added so inherited e29-tracer value cannot silently re-enable it.
- Unregistered `COMFYMODAL_*`/`V2_*` mutations are detected at import and reported rather than silently honored.

## 19. Software-created variance paths removed

- Inherited-env speculative arm (above).
- Image-content variance from transient local artifacts (ignore patterns).
- Quiescence nondeterminism (workers could be mid-flight at capture; now proven).
- Sample-projection gaps that made remote truth invisible offline (projection extended).

## 20. Local tests exact counts

| Suite | Result |
|---|---|
| test_e40_canonical_authority.py | 27 passed |
| test_e30_clip_qd_io.py (+E40) | 71 passed |
| e37 control plane + selector routing + v2ctl validation + backend | 102 passed |
| waterfall ×2 + critical path + production plan fix | 109 passed |
| snapshot suites (capture hygiene, build manifest, manifest ext, cpu models, hygiene AB) | 202 passed |
| conditioning ×2 + output/result delivery + provenance + modal identity | 261 passed, 7 failed (pre-existing) |
| output contract + materialization + plan identity + prefetch | 84 passed, 20 skipped |
| v2ctl backend + E40 (post-crash-loop fix) | 72 passed |

The 7 failures share one pre-existing root cause: local CacheDiT preimport gate (`diffusers/huggingface_hub` version mismatch in local Python; image-only dependency). Verified unrelated to E40 (zero CacheDiT lines in diff). No new failures introduced.

## 21. Remote gate

- Command: `python tools/v2ctl.py deploy-run --profile e37-clean-lane-qd4 --owner E40` then `python tools/v2ctl.py gate --profile e37-clean-lane-qd4 --owner E40`
- Final: exit=0, manifest `deploy_20260822-070931_f15874bd.json`, run dir `v2_2026-08-22_12-07-21`, gate `gate_20260822-121609_849cb536.json` **valid=1 reasons=[]**
- ONE cold gate; no performance cohort; no G1. STOPPED after validity per mandate.
- Post-gate stability (user-requested): **3 additional cold runs** against the unchanged deployment (`f15874bd`), each exit=0:

| Run | Dir | SHA match | Ledger | RuntimeStatus | Arms ok | wall_ms |
|---|---|---|---|---|---|---|
| 1 | v2_2026-08-22_14-26-10 | ✓ | ok | NOMINAL [] | ✓ | 18908.7 |
| 2 | v2_2026-08-22_14-27-52 | ✓ | ok | NOMINAL [] | ✓ | 19669.3 |
| 3 | v2_2026-08-22_14-29-01 | ✓ | ok | NOMINAL [] | ✓ | 35372.1 |

All three: identical exact output SHA, identical resolved-config fingerprint `3480ad93…`, requested==observed on all roles, zero fallbacks, distinct conditioning nonces (forced miss held). Structural stability proven (raw log §13).

## 22. Exact SHA proof

`output_sha == expected_output_sha == 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` (gate record §2 of raw log).

## 23. Raw artifact paths

- Gate: `.v2ctl/gates/gate_20260822-121609_849cb536.json`
- Deploy: `.v2ctl/deployments/deploy_20260822-070931_f15874bd.json`
- Run dir: `comfymodal-data/benchmarks/runs/v2_2026-08-22_12-07-21/` (run_0.json, run_001_sample.json, summary.json, campaign_manifest.json)
- Local console captures: `E40_GATE_STDOUT.log`, `E40_GATE_STDERR.log`

## 24. Complete raw-log path

`E40_CONTROL_REMOTE_RAW_LOG.txt` (command, deploy record, gate verdict, E40 telemetry blocks verbatim, 174-key remote telemetry, ledger events, summary/manifest/provenance, retry history).

## 25. R41 MERGE CONTRACT

Integration points R41 should target (all narrow, all live in the cleaned tree):

1. **Post-restore Golden pipeline entry**: `modal_app.ModalRuntimeEntrypointV2.run_plan_stream` (per-run seeding block at method entry is the authority reset point).
2. **Model manifest access**: existing exact-manifest machinery (frozen CLIP manifest / CPU-snapshot file facts) — unchanged by E40.
3. **Model role identities**: literal roles `"clip" | "unet" | "vae"`; semantic arms via `config_authority.requested_loader(role)`; extend vocabularies in `loader_selection._CLIP_ARMS/_UNET_ARMS/_VAE_ARMS` when adding arms.
4. **Skeleton/meta model retrieval**: `cpu_snapshot_models` reconstruction path — unchanged.
5. **Model owner publication/take**: `comfyapp.RESTORE_ROLE_OWNER_MAP` + `_register_active_model_read`/`_wait_for_active_model_read`; canonical names `restore_preload` / `restore_background_unet` / `restore_vae_loader`.
6. **CLIP forward boundary**: existing wrapped forward (critical-path spans) — unchanged.
7. **Sampler-start boundary**: existing ledger events — unchanged.
8. **Sampling-start / first-step boundary**: existing ledger events — unchanged.
9. **VAE demand/decode boundary**: policy_v1 path — unchanged.
10. **Exact output/final durable boundary**: `first_durable_result` ledger endpoint + `set_authoritative_endpoints` — unchanged.
11. **Runtime status**: emit via `runtime_status.build_runtime_status(...)`; validator enforces NOMINAL.
12. **Canonical ledger events**: `critical_path_ledger` API — unchanged; zero-gap window intact.

New seams R41 can reuse: `config_authority.resolve()/GOLDEN_CONTROL_FLAGS` (add new flags here, never read env directly), `loader_selection.record_observed/set_requested/set_effective`, `runtime_status`, `cache_taxonomy`, snapshot quiescence API, `resolved_config` emission contract.

## 26. Expected merge-conflict areas with R41

- `comfyapp.py` flag-init region (~lines 1218–1500) if R41 touches defaults — E40 added `RESTORE_ROLE_OWNER_MAP` near line 1460.
- `modal_app.py` `run_plan_stream` entry + result-assembly region (E40 seeding/emission blocks) — R41's pipeline reconstruction will overlap.
- `tools/v2_control/validation.py` (E40 extensions at lines ~160–310) if R41 adds validators.
- `experiment_result_store.py` record dict (E40 appended keys at end).
- `speculative_clip_hydration.py` if R41 deletes it entirely — safe; update `tests/test_e40_canonical_authority.py` accordingly.
- Low risk elsewhere: E40 kept new logic in NEW modules precisely to minimize this surface.

## 27. Remaining debt

1. ~68 direct env reads in comfyapp.py not yet migrated to authority accessors (authority + mutation detection covers semantics; mechanical migration pending).
2. Pre-existing local CacheDiT test failures (environment-only).
3. `detect_crash_loop` exists in two layers (backend helper + cli usage); single-source candidate.
4. Snapshot serialized-bytes remain UNOBSERVABLE (Modal does not expose them).
5. Warm-path cache HIT lanes not exercised by this cold gate (taxonomy documents expectations; warm cohort out of scope).

### Incident note (crash loop, fixed)

First deployment crash-looped containers at snapshot construction: `prove_snapshot_quiescence` aggregated checks on key `proven` while the conditioning-cache check reports `quiesced` — aggregate always False ⇒ fail-closed RuntimeError on every container start. Fixed (key-normalized aggregation; locally proven True). Per request, v2ctl now accounts for crash loops: `BackendResult.crash_loop` populated by the existing traceback-repetition detector, `[v2ctl.crash-loop]` line on detection, and deploy-run failure path prints `ERROR: CRASH_LOOP detected … v2ctl will not auto-retry`.

---

## Direct answers

1. **Can CLIP silently become FastSafe while requested QD4?** No. Requested comes only from the authority; any divergence is recorded (`loader_observed_mismatch_clip`), fails RuntimeStatus=NOMINAL, and the validator rejects the gate. Proven remotely: observed=qd4_reader.
2. **Can UNET silently switch loaders?** No — same mechanism; observed=cpu_snapshot_native matched requested exactly.
3. **Can VAE silently switch loaders?** No — same mechanism; policy_v1 matched.
4. **Can a fallback be accepted as nominal?** No. `fallback_attempted=true` ⇒ RuntimeStatus=DEGRADED ⇒ validator reason `loader_fallback_<role>` ⇒ gate invalid.
5. **Can an inherited env flag change Golden behavior without config mismatch?** No. Every Golden-semantics flag is inside the 99-control authority; unregistered algorithm-changing vars are detected at import; the speculative default-on hole is closed (unset ⇒ OFF) and profile-pinned.
6. **Is there one acceptance authority?** Yes — StructuralValidator/GateRunner. Waterfall now reports `diagnostic_status` (diagnostic-only).
7. **Is there one timing authority?** Yes — `critical_path_ledger` (core untouched); waterfall is diagnostic.
8. **Is there one owner identity for the same semantic operation?** Yes — `RESTORE_ROLE_OWNER_MAP`; producer/coordinator/preflight all join `restore_preload` for CLIP preload reads.
9. **Are snapshot-time model workers/futures quiescent?** Proven fail-closed before capture (conditioning workers joined; executor queues empty or hard error).
10. **Are conditioning runs guaranteed miss + encode=1 + persist=0?** Yes on the Golden profile: `conditioning_cache="forced_miss"`, `EXACT_CACHE_PERSIST="0"` pinned in TOML; nonce isolation enforced in cache.
11. **Which remaining code can still alter Golden scheduling?** Only authority-exposed flags set through the resolved config chain; residual direct reads are covered by mutation detection (debt item 1); warm-path RBG deferral is inert on the cold path.
12. **What precisely must R41 integrate with?** Section 25 — twelve named integration points plus the five reusable new seams; nothing else.
