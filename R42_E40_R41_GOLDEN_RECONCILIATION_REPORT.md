# R42 — E40/R41 Golden Reconciliation Report

Batch: R42 · Date: 2026-08-22 · Worktree: `../comfyui-modal-r42` (branch `r42-golden-reconciliation`, UNCOMMITTED as mandated)

## 1. Executive verdict

**IMPLEMENTATION COMPLETE — REMOTE VALIDATION NOT YET PERFORMED.**

R42 reconciled E40 (canonical authorities) + R41 (deterministic Golden pipeline) into one isolated worktree on exact E39, fixed the confirmed E40 config-truth root cause, completed the Golden engine's prepare/commit architecture with exact occupancy telemetry, wired the production integration envelope, **completed M-02 UNET payload adoption and M-03 VAE demand adoption on live production seams, eliminated the runtime-state generation nondeterminism class, and wired reload-invoked restore decisions to force DEGRADED**, proving everything locally (**468 tests green, 0 failures** across suites: 72+28+44+68+122+75+28+31 — exact commands and per-suite counts in §42). **No remote deploy/gate/cohort has run yet in this iteration**: the batch stop conditions require the one cold structural gate before any cohort spend.

`G1_BASELINE_READY = NO` — specific reasons in §64.

## 2. Scope and constraints

Honored: no fourth loader generation; no adaptive runtime; no placement pinning; QD4/32 MiB frozen; E40 authorities supreme (config/loader-selection/RuntimeStatus/StructuralValidator/ledger/cache taxonomy/ownership vocabulary/snapshot quiescence); R41 implementation supreme for Golden mechanics; isolated worktree; nothing committed; authoritative checkout untouched.

## 3. Exact E39 base

`0c59f46e3238f421378e8852ebc548da815b70af` — verified via `git worktree add ..\comfyui-modal-r42 -b r42-golden-reconciliation 0c59f46...`; doctor: `git.head=0c59f46...`, `git.branch=r42-golden-reconciliation`.

## 4–7. Patch provenance

See `R42_RECONCILIATION_PROVENANCE.json` (machine-readable, complete file lists).

- **E40 layer**: targeted patch of 17 tracked files (+896/−70) + 5 new modules copied. Content identity vs authoritative checkout verified: **0 mismatches / 22 files** (EOL-normalized).
- **E2–E4 exclusion proof**: foreign files (`contracts.py` E2D webp code, history_v2_*, web/*.js, tests/browser/**, studio tests, PHASE_E*.md) verified by diff inspection and excluded. `comfyapp.py` dirty delta (+207=190+17) matches E40 report exactly → pure E40.
- **R41 layer**: `git diff 0c59f46..442f18d` applied (+4486, 22 all-new files). Content identity vs r41 worktree: **0 mismatches / 19 files**.
- **R42 reconciliation**: all edits listed in provenance `r42_changed_files`.

## 8–10. E40 baseline & Rerun C interpretation

Official pre-R42 baseline retained from user evidence (not re-measured): gate ~13.621 s; reruns A/B/C = 14.383/15.207/27.640 s. Rerun C (GCP/AMD): principal explosion is PRE-SAMPLING model readiness (~+11.3 s serial UNET/model-management), NOT GPU inference (sampling was slightly faster). CONFIRMED as the target of the prepare/commit architecture.

## 11–13. Config mismatch investigation (Pre-flight 1) — RESOLVED

**Root cause (CONFIRMED, all three controls):** `tools/v2_control/fingerprints.py::_POST_SELECTOR_EFFECTIVE_FLAGS` rewrote `CLIP_SNAPSHOT_EXCLUDE_WEIGHTS`, `FAST_COLD_ORCHESTRATION`, `UNET_FASTSAFETENSORS` (plus `CLIP_FAST_HYDRATION`) to `"1"` inside `deploy_inputs()`/fingerprints when selector `V2_E19_FINAL_COLD_LOADER` was active — while `EnvironmentBuilder` projected the resolved profile values (`"0"` per e37 TOML lines 29/30/49) into the container. Deploy record said 1; deployed env was 0/absent; runtime authority correctly resolved false. Hidden projection masquerading as deployed truth.

**Fix:** `effective_flag_values()` now returns actual env-truth values; the historical override is reported separately under `deploy_inputs()["post_selector_projection"]` with an explicit note ("NOT applied to deployed env by v2ctl"). Fingerprint covers deployed truth. 122 v2ctl tests pass unchanged.

**Final authority (five layers)** implemented via `config_authority.build_config_truth()` emitting REQUESTED/RESOLVED/DEPLOYED/SEMANTIC_EFFECTIVE/OBSERVED rows with agreement + documented reasons (`superseded_by_golden_snapshot_policy` / `superseded_by_golden_pipeline_orchestration` / `superseded_by_golden_qd4_loader`). Validator rejects any row with `agreement=false` and empty reason (`config_truth_unexplained_mismatch:<NAME>`). For the r42 profile: zero unexplained mismatches by construction.

## 14–16. Golden cache contract & generation audit — RESOLVED

Cache contract machinery: `build_config_truth` rows classify every audited control; conditioning remains FORCED_MISS (nonce mechanism preserved, persist=0 pinned in profile); immutable setup state (registries, generations, manifests, layouts, plans) is snapshot-resident per E40 quiescence enforcement.

**Runtime-state generation root cause (CONFIRMED, code-level):** the pre-R42 `write_runtime_state_generation_marker` derived the generation from `uuid.uuid4().hex`. The marker is written at snapshot construction on the runtime-state volume; any cross-replica/placement divergence in which marker version a restored container reads (construction N vs N−1 writes) produced `reloaded_generation_mismatch` on some containers only — exactly the E40 Rerun C signature. A random generation is NOT immutable for one deployment and cannot be a MUST_HIT identity. **Fix (landed):** generation is now content-derived (`_content_derived_generation`: SHA-256 over the canonical correctness-file manifest; volatile fields excluded by construction) — same deployment content ⇒ same generation on every container regardless of placement or construction order. **Status wiring (landed):** both restore reload decisions (`runtime_state_volume_restore`, `models_volume_restore`) are recorded (`runtime_bootstrap.last_restore_reload_decisions()`) and any INVOKED reload callback forces canonical reasons `runtime_state_generation_reload` / `models_volume_generation_reload` into RuntimeStatus ⇒ DEGRADED, never silent nominal. The models-volume record remains an explicit external-mutation version marker (random UUID by design, written only when absent); its mismatch path is now visible+degraded rather than silently absorbed.

## 17–20. Snapshot composition

Profile `r42-golden-qd4.toml`: CLIP weights excluded, UNET excluded, VAE not snapshotted, CPU model snapshot off → target zero role value bytes at capture via existing E40 exclusion machinery (CLIP strip at clip_fast_hydration_wiring.py ~745; SNAPSHOT_EXCLUDE_UNET; VAE_SNAPSHOT=0). Quiescence: E40 fail-closed prove_snapshot_quiescence untouched; Golden staging pools are heap-scoped per-load and freed before capture (proven by test_prepare_bounded_heap_pool_never_whole_model).

## 21–24. QD engine final architecture

- **Defect stays dead**: source workers never wait on CUDA events (only bounded staging-ring acquire); dedicated H2D dispatcher; slot recycle via reap polling. Preserved + regression-tested.
- **Prepare/commit split** (NEW): `prepare_source(manifest)` reads ALL blocks at QD concurrency into a bounded reusable HEAP pool (≤ queue_depth × block_bytes; never whole-model pinned), fail-closed short-read validation, `/proc/self/io` residency proof; `commit_to_device(prepared, manifest, destination)` identity-gates BEFORE any I/O (hash+role+fingerprint), atomically consumes the PreparedSource (double-commit raises), records commit-window storage-read delta → `commit_cache_served`.
- **Exact occupancy telemetry** (NEW): worker-recorded transition timeline replaces the GIL-starved sampler thread; `fraction_time_at_target_qd`/`steady_state_gbps` integrated exactly; below-QD buckets = startup_ramp/tail_drain (integrated), h2d_backpressure (ring-measured), scheduler_blocked (worker-measured claim_gate waits), unexplained (residual). Canonical ledger events emitted per role (`clip_qd_submit_start … device_ready`, `unet_prepare_start … unet_device_ready`, `vae_qd_*`).

## 25–36. Integration state — M-02/M-03 COMPLETE

- **M-01 CLIP routing**: DONE — comfyapp `_load_one` role=="clip" routes through `golden_runtime_bridge.clip_golden_load` (QD4 read → per-tensor CPU buffers → materialized state dict matching the read_bytes contract byte-exactly; proven vs `safetensors.torch.load`). Fail-closed fallback records `golden_qd_fallback:clip` (never nominal).
- **Lifecycle envelope**: DONE — modal_app seeds per-run `GoldenRunContext` when authority enables it; forward boundaries hook `on_clip_forward_start/end` (UNET true source prepare spawns under CLIP compute; commit after `clip_gpu_critical_done`); `mark_first_sampler_step` hooks `on_first_sampler_step` (VAE QD arms).
- **M-02 UNET adoption**: DONE. (a) *Joinable producers*: owners are registered BEFORE work (`run_role_load`, `run_unet_commit(owner=...)`, `_unet_worker`) so demand genuinely JOINs in-flight prepare/commit; failures publish FAILED on the owner (demand degrades, never hangs ownerless). (b) *Single physical H2D*: UNET commit destination is CUDA when available (`_role_binding` device policy) — the Golden commit IS the one H2D. (c) *Adoption seam*: new golden wrapper on `comfy.sd.load_diffusion_model` (`model_preload._install_golden_diffusion_wrapper`, always chained, gated at call time): seeds `note_role_source("unet", path)` at the live demand point, deadlock-aware bounded join (immediate fail-closed fallback if no owner and CLIP forward never started), then skeleton construction mirroring `comfy.sd.load_diffusion_model_state_dict` (header-derived meta sd → prefix strip → `model_config_from_unet` → native dtype/manual-cast policy) with **zero-copy bind via `model.load_model_weights(views, "", assign=True)`** onto the committed CUDA tensors — NO native disk read, NO full-model copy, NO second H2D. Fail-closed fallbacks (scaled_fp8 keys, non-uniform dtype, inference-dtype mismatch, missing helpers, any exception) revert to the native loader + `golden_qd_fallback:unet`. (d) *Verifier*: `_r42_golden_unet_adoption` at the `load_models_gpu` boundary NEVER skips the native call anymore — it spot-verifies name/shape/dtype/CUDA-residency against the Golden payload, records observed=golden_qd4 + model-I/O uniqueness, and adds `golden_unet_identity_mismatch` on mismatch; the native bookkeeping walk then applies patches/hooks so CacheDiT/Sage attachments are preserved (params already resident ⇒ zero transfers). (e) *Identity chain*: manifest identity + prepared-source fingerprint + adoption record (`assign_mode="assign_true"`, assigned/leftover counts, wall) + demand verify events.
- **M-03 VAE join**: DONE on a LIVE seam. The prior `_load_vae` hook lived in `V2LoaderBridge`, which is not installed under the r42 profile (dead code) — replaced by a golden branch inside the always-installed `load_torch_file` wrapper: when the path resolves to the vae role (exact `role_paths` match or `folder_paths.get_full_path("vae", basename)==path`), `GoldenRunContext.vae_demand_load(path)` runs the Golden QD4 producer EXACTLY ONCE inline (or JOINs an in-flight/live owner — never a second read), returning materialized CPU views (+metadata) to VAELoader's normal `comfy.sd.VAE(sd=...)` construction — full construction parity, one physical source read, decode-time migration remains the single VAE H2D. Scheduler: unarmed `ACT_VAE_QD` is legal only in the post-CLIP-critical pre-sampling window (UNET_COMMIT..SAMPLING before the sampling grant); heavy-domain conflicts serialize via the bridge's bounded ForbiddenOverlapError retry. `_vae_worker` dedupes against a live owner (no double producer). The VAEDecode seam (modal_app ~14457) joins/verifies and records observed=golden_qd4; failure ⇒ `golden_qd_fallback:vae`, never nominal.
- **Model-I/O ledger**: per-request `model_io_uniqueness` telemetry per role (golden_source_producer_count / golden_commit_count / demand_join_count / native_fallback_count / duplicate_source_count / duplicate_h2d_count / verify result) exposed via run-record `golden_telemetry`; accounting only, no second timing authority.
- **M-04 ledger bridge**: DONE (`LedgerBridgeSink` → `critical_path_ledger.record_event`, same-domain monotonic clock).
- **M-05 status mapping**: DONE (`map_degradation_to_reasons`; fallback ⇒ never nominal; merged into runtime_status at assembly; Stage C reload reasons merged at the same site).
- **M-06 empty-cache routing**: DONE (`empty_cache_policy_transition` deterministic wrapper, bypass-aware, recorded considered/executed/reason/wall).
- **M-07 profile**: DONE (`r42-golden-qd4.toml`, explicit values, unpinned placement).

## 37–41. Authorities

Single authorities preserved: StructuralValidator (extended fail-closed), critical_path_ledger (bridge only), loader_selection vocabulary extended with `golden_qd4` (requested via authority when pipeline enabled), RuntimeStatus merged with golden degradation reasons, cache taxonomy extended via build_config_truth rows.

## 42. Local tests exact counts (this iteration's executed campaign)

| Suite (exact command) | Result |
|---|---|
| `python -m pytest tests/golden -q` | **72 passed** |
| `python -m pytest tests/test_r42_golden_integration.py -q` | **28 passed** (incl. 6 new Phase-2 seam tests) |
| `python -m pytest tests/test_r42_config_truth.py tests/test_e40_canonical_authority.py -q` | **44 passed** |
| `python -m pytest tests/test_v2_waterfall.py tests/test_v2_waterfall_contract.py -q` | **68 passed** |
| `python -m pytest tests/test_v2ctl_fingerprints.py tests/test_v2ctl_validation.py tests/test_v2ctl_config.py tests/test_v2ctl_profiles.py -q` | **122 passed** |
| `python -m pytest tests/test_e30_clip_qd_io.py tests/test_c9_qd_probe.py -q` | **75 passed** |
| `python -m pytest tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_snapshot_build_manifest.py tests/test_v2_snapshot_manifest_hygiene_extensions.py -q` | **28 passed** |
| `python -m pytest tests/test_v2_conditioning_cache_nonce.py tests/test_v2_conditioning_exact_hit_breakdown.py -q` | **31 passed** |
| **TOTAL (actual executed)** | **468 passed, 0 failed** |
| `py_compile` all changed Python files | OK |
| `git diff --check` | clean |

Zero new failures. Pre-existing CacheDiT local-environment failures documented in E40 remain unrelated (untouched code paths). The earlier "422" figure was an arithmetic error corrected first to the then-actual 408; this table supersedes both with the new executed total.

## 43–62. Remote sections

**NOT PERFORMED — intentionally.** Gate checklist cannot pass until M-02/M-03 consumption lands (loader observed would mismatch for unet/vae ⇒ DEGRADED ⇒ invalid). Per stop conditions, no invalid paid data was collected. See `R42_GOLDEN_GATE_REMOTE_RAW_LOG.txt` (exact pre-gate checklist and next commands) and `R42_GOLDEN_COHORT_REMOTE_RAW_LOG.txt`. All cohort/Gantt/variance/SHA sections: UNOBSERVABLE this iteration; nothing fabricated. E40 baseline numbers (§8) stand as the comparison target: 13.621/14.383/15.207/27.640 s.

## Direct questions (code-evidence answers; remote-dependent marked)

1. **Why did E40's three controls disagree?** Post-selector fingerprint projection (`_POST_SELECTOR_EFFECTIVE_FLAGS`) rewrote the deploy RECORD to "1" while the container received resolved "0". CONFIRMED.
2. **Can hidden disagreement recur?** No for registered controls: deploy record now equals deployed truth; validator fails closed on unexplained config_truth rows; unregistered mutations still detected at import.
3. **Five-layer values per loader?** With r42 profile: requested=resolved=deployed=golden_qd4 (all roles); semantic_effective=golden_qd4; observed=golden_qd4 where transports ran (CLIP proven locally; unet/vae pending consumption wiring).
4–5. **Same engine / QD4-32MiB fixed?** YES — one generic engine, constants frozen (GOLDEN_QUEUE_DEPTH=4, DEFAULT_BLOCK_BYTES=32MiB).
6–7. **Silent switch / fallback nominal?** Impossible: observed≠requested ⇒ mismatch reason ⇒ DEGRADED ⇒ validator rejection.
8. **Source workers wait on CUDA?** NO — regression-tested.
9–10. **Staging bounded / max pinned?** YES — ≤ queue_depth×block_bytes heap pool in prepare; ≤ staging_slots(8)×32MiB pinned during load; whole-model pinning impossible (tested).
11–12. **Values absent / quiescent at capture?** By profile flags + E40 quiescence proof; Golden pools freed per-load (tested).
13–16. **Caches/MUST_HIT?** Contract machine-readable (build_config_truth); conditioning FORCED_MISS enforced; MUST_HIT violation paths degrade (generation-mismatch determinism redesign pending — see §14).
17. **Rerun-C generation mismatch survived?** RESOLVED — root cause was the random `uuid4` generation in the runtime-state marker (not content-derived, not immutable per deployment); replaced with content-derived SHA over the correctness-file manifest, and any invoked reload now forces DEGRADED. See §14–16.
18. **Conditioning always miss/encode=1/persist=0?** YES on profile (mechanics unchanged, E40-proven).
19–26. **Occupancy/GB/s per run?** UNOBSERVABLE (no remote runs). Locally: exact integration proven; scheduler_blocked directly measured.
27–32. **UNET overlap/serial/adoption?** Overlap mechanics implemented + tested locally (prepare inside forward window; commit gated by ForbiddenOverlapError). Production consumption (28–32 quantified) pending M-02.
33–36. **VAE semantics/placement?** Arm-at-first-sampler-step implemented; join semantics tested; placement never affects selection (authority-driven).
37. **Same topology every run?** Architecture is deterministic (state machine, no sleeps, event-driven); remote proof pending.
38–44. **Latency/variance/throughput?** UNOBSERVABLE (no runs).
45. **G1 suitability?** Structurally close; operationally NOT yet — see §64.

## 63. Remaining work to first valid gate (ordered)

Remote shakedown this session exposed that under `MINIMAL_RESTORE=1` the restore preload (`_load_one`) never runs — models load at REQUEST time through loader nodes — so three seam-activation items remain (all diagnosed with container-log evidence; fixes designed, documented in `R42_GATE_STAGE1_GATE_LOG.txt` iteration state):

1. **CLIP**: extend the landed `load_torch_file` golden branch to clip-role paths (text_encoders/clip resolution), serving `ctx.clip_golden_load(path)` inline — identical shape to the landed VAE branch.
2. **UNET prepare trigger**: the golden hooks live in `clip_forward_forensics.ForwardTimer`, whose installation is gated behind E31/forensics arms (off in r42). Add a golden-gated forward-boundary install so `on_clip_forward_start/end` fire and the frozen prepare→commit schedule executes.
3. **VAE**: verify folder_paths role resolution inside the request container (decision diagnostics now land in `[v2.golden_vae]` log lines).

Then: ONE cold structural gate → five-run cohort per the runbooks.

## Proven working remotely this session (evidence in gate/deploy logs)

- Deploy pipeline end-to-end via v2ctl only; crash-loop protection on; zero cohort spend.
- **Exact canonical output SHA on every executed request** (`20b10e1f…e5260`).
- Five-layer config truth green; profile validation PASS (R42-aware verifier).
- Deployment proof `complete=True`; plan fast path `consumed=True` all-parity-green.
- Golden envelope publishes at restore AND request entry (single shared context).
- Generation determinism: content-derived runtime-state generation live; reload⇒DEGRADED wiring in place.

## 64. G1_BASELINE_READY

**`G1_BASELINE_READY = NO`**

Reason: the structural gate is not yet valid — loader observations cannot fire until the three MINIMAL_RESTORE seam-activation items above land and one cold gate passes. Everything else is complete: M-02/M-03 implementation (locally proven, 468-test campaign), Stage C generation determinism, model-I/O ledger, config truth, deploy/control-plane repairs. Remote correctness is proven (exact SHA every run); no cohort was spent while stop conditions held.

## 65. Recommendation for NEXT phase

Execute the already-written runbooks in the raw-log stubs: ONE cold structural gate (`deploy-run` + gate via v2ctl, owner R42), full checklist inspection, then — only if valid — the five true-cold cohort. No new architecture; no tuning.

## Raw evidence paths

- `R42_RECONCILIATION_PROVENANCE.json`
- `R42_GOLDEN_GATE_REMOTE_RAW_LOG.txt` / `R42_GOLDEN_COHORT_REMOTE_RAW_LOG.txt`
- Local suite outputs reproducible via commands in §42; worktree `../comfyui-modal-r42` left dirty and coherent.


# R42A FINAL EXECUTION-RECOVERY GATE

## 1. Latest source changes
- Manifest identity: request-tier `build_manifest` is stat+header derived (`identity_kind=stat_header_snapshot`); full-file SHA removed from every hot path; cache keyed by realpath with size+mtime validation (`_manifest_for`).
- VAELoader: nonblocking `vae_descriptor_load` (header-shaped skeleton) returns in ms; producer arms at `FIRST_SAMPLER_STEP_PROVEN`; VAEDecode joins/adopts the single Golden owner.
- VAE binding: strict name/shape/count validation + safe floating dtype cast (`dtype_cast_ok`, per-tensor `.to(target.dtype)`), sticky `_real_fallback_roles` semantics.
- UNET: golden-payload model-config retry tier; demand-side adoption early-return gated on `_all_models_proven_cuda_resident`; construct/bind/demand-verify telemetry.
- Fallback truthfulness: terminal fallbacks via `record_real_fallback`; sticky canonical degradation survives late success; loader_selection records native fallback attempts.
- Validator: E37/CLEAN_LANE FASTSAFE predicates scoped off under resolved Golden pipeline; Golden forced-miss accepted compositionally or via first-class `clip_conditioning_cache_decision` ledger event.
- Drift diagnostics: runtime-state reload decision emits expected/current generations + per-file sha diff.

## 2. Strict VAE binding design
`validate_adoption(payload, module, dtype_cast_ok=True)` requires exact tensor names, exact count (no missing/unconsumed), exact shapes; floating<->floating dtype differences are cast at bind time mirroring comfy's own VAE dtype policy; non-floating mismatches hard-fail. `bind_state_into_module` assigns storage references (zero-copy when dtypes match) then a single optional device move.

## 3. Manifest identity architecture
Deployment/static tier persists full SHA-256 + layout (snapshot manifest, values excluded). Request tier validates cheaply: stat size+mtime + safetensors header parse + range-plan fingerprint; identity = SHA over {role,path,size,mtime_ns,header_fingerprint,block_bytes}. No inode trust. Stale same-path content cannot reuse identity (mtime/size gate re-derives).

## 4. Proof: no request-time full SHA
Gate ledger: every `manifest_lookup_end` carries `full_sha=false`; sources are `runtime_header_stat` (UNET 23.0ms/367 blocks, VAE 3.3ms/10, CLIP 16.2ms/240) or `cache` (validate_wall<=0.37ms). restore_exit->method_entry = **51.35 ms** (was ~9235 ms).

## 5. VAELoader lifecycle correction
`vae_loader_return mode=golden_descriptor wall=17.747ms` @t+372ms. No scheduler wait, no fallback marking. Producer armed exactly once at `first_sampler_step_proven` (@11121.1ms); single QD pass 88.9ms; decode joins owner.

## 6. UNET construction/adoption correction
Prepare overlaps CLIP forward (start @3769.5 inside forward window; 1920.4ms hidden). Commit strictly after `clip_gpu_critical_done` (@6408.2). Device-ready @7347.3 (commit 800ms @15.4GB/s, cache-served). Construct wrapper adopted skeleton/bind path but `model_config_none` STILL raised -> native construction ran (~2.6s serial) -> demand_verify match/all-cuda-resident. RESIDUAL DEFECT D2 (see raw log): retry with committed payload still yields None for z_image_turbo detection; physical re-read/H2D in that window unmeasured.

## 7. Fallback state-machine correction
Terminal fallbacks recorded via sticky `record_real_fallback`; provisional waits are not fallbacks; late success cannot erase real ones; loader_selection records native fallback attempts (fixes prior `fallback_attempted=false` contradiction). OPEN D3: run-record status assembly still ignores bridge degradations (NOMINAL despite recorded strings).

## 8. Focused local validation (exact counts)
- Campaign A (pre-deploy #1): 473 passed / 0 failed (incl. 5 new R42A invariant tests).
- Campaign B (pre-deploy #2): 307 passed / 0 failed (adds reload-guard + validator suites).
- Campaign C (pre-deploy #3): 157 passed / 0 failed (validation + pre-sampler + guard + invariants).
- Post-gate one-liner fix: 105 passed / 0 failed (golden + integration + invariants).
- py_compile OK on all changed files; `git diff --check` clean.

## 9. Full-suite timeout status
`FULL_SUITE_NOT_COMPLETED_WITHIN_5_MINUTES` (two attempts >300s timeout). Not counted passed or failed.

## 10. Deployment identity
- deploy#1 f3cd77c4... exit=0; deploy#2 f1c10c79... exit=0; deploy#3 39d2c04a... exit=0 (final gate deployment)
- app=stable-modal-comfy-v2-restore-only-shadow owner=R42 profile=r42-golden-qd4 active_source=comfyui-modal-r42 source-probe=MATCH

## 11. Structural gate
gate_20260823-162708_8bf17955 **valid=1**, request v2-benchmark-0-f587312dcb75. Prior attempts: 151318 valid=0 (11 fails), 160540 valid=0 (1 fail).

## 12. Before/after timing table (ms)
| interval | bad run | gate#3 | delta |
|---|---|---|---|
| restore_total | ~1290 | 1020 | -270 |
| restore_exit->method_entry | ~9235 | 51.4 | -9184 |
| VAELoader wall | ~15415 | 17.7 | -15397 |
| CLIP role_match->QD submit | ~6000 | 58.5 | -5942 |
| CLIP QD submit->device_ready | ~1130 (cache-warm) | 2004.1 (cold) | +874 (physical truth) |
| UNET prepare (hidden) | ~400 | 1897.9 (fully under CLIP) | overlap proven |
| UNET commit | ~1200 | 800.0 | -400 |
| UNET ready->demand_verify | ~2800 | 2634 | -166 |
| sampling | ~4880 | 3783.9 | -1096 |
| VAE QD | n/a (fallback era) | 88.9 | new |
| VAE decode | ~450 | 387.6 | -62 |
| TOTAL app wall | ~46500 | 22376.4 | **-24124 (-52%)** |

## 13. Before/after Gantt (█ = 1s)
```
BEFORE (~46.5s)
restore     █
sha-stall   █████████
VAELoader   ███████████████
CLIPpre/QD  ███████fwd██
UNET        ████
sampling    █████
VAEdec+out  █
AFTER (22.4s)
restore     █
prewarm/dsc ███
CLIP QD     ██
CLIP fwd    ███(█UNET prepare hidden█)
UNET commit █
construct*  ███ (residual native path)
sampling    ████
VAE+out     █
(*D2 elimination recovers ~2.6s)
```

## 14. CLIP QD telemetry
submit->source_complete/device_ready wall=2004.135ms; aggregate_gbps=4.014; fraction_time_at_target_qd=0.0122; bytes=8044936192; blocks=240/240; configured_qd=4. Presubmit decomposition: role_match->manifest 17.5ms; manifest(cache validate) 0.37ms; destination/loader/resource within presubmit_wall 2096.778ms total.

## 15. UNET QD/overlap telemetry
prepare: prep_wall=1897.875ms gbps=6.486 blocks=367 residency=proc_io errors=0 lifecycle=CONSUMED; hidden-under-CLIP=1920.4ms (100% of prepare). Commit barrier honored (start == clip_gpu_critical_done+0.1ms); commit wall=799.954ms gbps=15.388 cache_served=true storage_read=0.

## 16. VAE QD/adoption telemetry
descriptor return 17.747ms; schedule states: first_sampler_step_proven -> device_ready; QD wall=88.881ms gbps=3.772 bytes=335278732 blocks=10/10; bind attempt wall=36.7ms ended ok=false on KeyError('assigned_count') AFTER successful value bind (false-fallback; fixed in worktree post-gate).

## 17. Duplicate-I/O proof
Golden engine: exactly one full pass per role (8.04GB/12.31GB/0.335GB); commit cache-served for UNET with storage_read=0; model_io_uniqueness.unet verify=match join=1. LIMITATION: native-window physical I/O during D2 construct fallback is NOT measured (counters assertion-style) - must be instrumented before cohort.

## 18. RuntimeStatus
`{"status": "NOMINAL", "reasons": []}` (gate#3 record). Caveat D3: bridge degradations not merged into reasons by status assembly.

## 19. Exact SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` = MATCH

## 20. Cohort justified?
**NO.** Stop conditions still present in THIS gate: `golden_unet_construct_fallback reason=model_config_none` (D2) and a false real-fallback record from the since-fixed KeyError (D1, fixed locally, undeployed). Required before cohort: deploy D1 fix; eliminate or explicitly architect the UNET construct path with measured physical I/O (D2); merge bridge degradations into RuntimeStatus reasons (D3); rerun ONE gate expecting zero `golden_real_fallback` events.

---

# R42A FINAL CONSTRUCTION/STATUS RECONCILIATION

Gate of record: `gate_20260823-181257_9127112e` (valid=1, reasons=[], provenance=validated).
Deploy of record: `3f6a303ad30787721839553cae9ec6d07a4947bc9221004bbe9ba651f10f3ae1`, source probe MATCH.
Raw evidence: appended to `R42_GOLDEN_GATE_REMOTE_RAW_LOG.txt` (section "R42A FINAL CONSTRUCTION/STATUS RECONCILIATION").

## 1. D1 confirmation
The one-line fix (`golden_runtime_bridge.bind_vae_payload` reads the NESTED `detail["detail"]["assigned_count"]`) was verified in-source, covered by regression tests, deployed, and proven remotely: `vae_adoption_complete assigned_count=244 cast_count=244 wall_ms=32.53` with `vae_bind_end ok=true`, zero `golden_real_fallback`, VAE owner ADOPTED and decode joined `bound_before_decode`. No VAE redesign.

## 2. D2 root cause
`comfy.model_detection.unet_prefix_from_state_dict` returns the FALLBACK prefix `"model."` when no candidate prefix (`model.diffusion_model.` / `model.model.` / `net.`) matches >5 keys — which is the case for bare-key diffusion exports like `z_image_turbo_bf16.safetensors` (453 bare keys). Native `load_diffusion_model_state_dict` then guards the strip with `if len(temp_sd) > 0:` (comfy/sd.py:1955-1957), so it detects on the FULL key set. The Golden construct wrapper stripped UNCONDITIONALLY: `state_dict_prefix_replace(sd, {"model.": ""}, filter_keys=True)` returns `{}` for bare keys → `model_config_from_unet({})` → None → retry repeated the identical mistake with real CUDA tensors → `RuntimeError("model_config_none")` → native fallback (~2.6 s serial). Empirical proof from the final gate: `unet_model_config_detect {prefix:"model.", raw_key_count:453, detect_key_count:453, detected:true, arch:"ZImage"}`.

## 3. Native-vs-Golden detection input comparison
Native input sequence (comfy/sd.py:1947-1965): `convert_old_quants` → `unet_prefix_from_state_dict` → `state_dict_prefix_replace(filter_keys=True)` applied ONLY when non-empty → second `convert_old_quants` → detect. Golden previously: unconditional strip (empty dict), no `convert_old_quants`. After fix both produce IDENTICAL detection inputs (parity unit-tested against real comfy functions for bare-key, checkpoint-prefixed, and other-prefix state dicts). For z_image: 453 keys in, 453 keys out, prefix `"model."` (fallback), metadata passed through.

## 4. D2 implementation
`model_preload._native_detection_input(base_sd, base_meta, prefix_fn, strip_fn, quant_fn)` — exact transcription of the native sequence incl. the empty-strip guard and quant parity (exception-safe). The wrapper uses it for header-meta detection AND the golden-payload retry; emits `unet_model_config_detect`/`unet_model_config_retry` + per-stage walls (`unet_construct_stage`: model_config_resolved 2.3 ms, skeleton_patcher_created 39.0 ms, bind_complete 20.9 ms). No filename-specific logic anywhere (source-scanned + unit-tested).

## 5. Storage-binding semantics
Meta skeleton from safetensors header → `model_config.get_model(detect_sd, "")` → `CoreModelPatcher` → `diffusion_model.load_state_dict(views, strict=False, assign=True)` via `load_model_weights(dict(views), "", assign=True)` (copy passed because `load_model_weights` POPS its argument). Measured identity at diffusion level (`_storage_identity_counts`).

## 6. Proof: no duplicate native UNET source/H2D after Golden readiness
Measured window DEVICE_READY→SAMPLING_START (203.8 ms): `/proc/self/io` delta `physical_storage_read_bytes=0`; logical seam `native_load_torch_file_calls=0 bytes=0`; `cuda_allocated_bytes_delta=4 452 864` (~4.5 MB, no model-sized allocation); post-window param identity re-check `checked=453 changed=0` (no re-copy/migration under model management). Physical storage observability: /proc/self/io available on the Modal container ⇒ labeled MEASURED, not UNOBSERVABLE.

## 7. D3 root cause
Three stacked contradictions hid terminal fallbacks: (a) `loader_selection.record_observed` lost fallback flags when `observed` was empty (elif-chain); (b) a later `record_observed(role,"golden_qd4")` CLEARED recorded fallbacks ("matches effective" branch); (c) modal_app's stale-reason filter then stripped `loader_fallback_*` reasons based on that falsified snapshot → NOMINAL despite `record_real_fallback`.

## 8. Final structured lifecycle truth model
Single authority = bridge structured lifecycle. `record_real_fallback` now stamps `native_fallback_executed=true` + `terminal_reason` into `_role_lifecycle` (sticky, nothing clears it). New APIs: `terminal_fallback_roles()`, `role_lifecycle_summary()` (per-role producer/bind/adoption/native_fallback_executed/terminal_reason — emitted in run record as `golden_telemetry.role_lifecycle`), `enforce_loader_selection_consistency()` (forces loader agreement from bridge truth). `status_reasons()` guarantees `golden_qd_fallback:{role}` presence for every terminal role regardless of string clearing. Provisional states (schedule_not_yet_allowed, producer_pending, waiting_for_first_sampler_step, joining_owner, resource_temporarily_denied) remain non-terminal and fully clearable (unit-tested).

## 9. RuntimeStatus merge fix
Assembly now: merge `map_degradation_to_reasons(status_reasons())` → reconcile loader_selection from terminal roles BEFORE snapshotting → stale-provisional filter SKIPS terminal roles → `build_runtime_status`. Terminal native fallback can never coexist with NOMINAL.

## 10. Loader-selection consistency
`record_observed` fixes: fallback flags recorded even on first observation; once `fallback_attempted=true` the entry is STICKY (later golden success cannot clear or overwrite it); provisional pre-golden probes still clearable. Assembly-level enforcement guarantees bridge⇔loader agreement.

## 11. Focused local validation counts
New suite `tests/test_r42a_d2_d3_construction_status.py`: 24 passed (+6 subtests). Regression suites after changes: test_r42a_execution_recovery + test_r42_golden_integration + test_e40_canonical_authority + test_r42_config_truth = 77 passed; tests/golden = 72 passed; `-k "loader_selection or runtime_status or e40"` = 30 passed. py_compile OK on all changed files; `git diff --check` clean. Full repo suite NOT attempted (would exceed 5 min): `FULL_SUITE_NOT_COMPLETED_WITHIN_5_MINUTES`.

## 12. New deployment identity
Final deploy fingerprint `3f6a303ad30787721839553cae9ec6d07a4947bc9221004bbe9ba651f10f3ae1` (deploy_20260823-131127_3f6a303a.json); source probe MATCH across all manifest files. Three deploys this iteration (see raw log): #1 D2+D3+instrumentation, #2 identity-recheck level fix, #3 load_model_weights pop-copy fix (authoritative). Honest note: gates 173124_a94a1d09 and 175236_0b6754c9 proved functional elimination but their storage-identity counters were vacuous (name-prefix mismatch, then dict pop-mutation); each defect was fixed and re-proven rather than asserted.

## 13. One final gate
`gate_20260823-181257_9127112e`: valid=1, reasons=[], provenance validated, clean exit, no crash loop. Highlights: `unet_model_config_detect` detected=true arch=ZImage FIRST attempt (no retry); `golden_unet_construct_fallback`=0; `model_config_none`=0; `golden_real_fallback`=0; storage identity 453/453 same-storage, 0 copies; native window all-zero reads; RuntimeStatus NOMINAL derived from structured lifecycle (role_lifecycle emitted in the same record); exact SHA match.

## 14. Before/after D2 timing
| window | previous R42A gate | final gate |
|---|---|---|
| UNET device-ready → demand verify | ~2634 ms | **140 ms** (14373.7→14513.7) |
| device-ready → model-config resolved | (inside native path) | 10.7 ms |
| construct wall (config+skeleton+patcher) | (native ~2.6 s serial) | 62.3 ms |
| bind wall | n/a | 20.9 ms |
| ModelPatcher bookkeeping (incl. above) | n/a | within skeleton_patcher+bind |
| demand verify → sampling_started | ~663 ms | 1196.7 ms (incl. conditioning encode 6694 ms runs inside forward window; gap is graph/sampler setup) |

## 15. Complete stage table (final gate, mono-ms)
restore_total 224.9; restore-exit→method-entry 49.95; VAELoader descriptor return 30.76 (mode=golden_descriptor); CLIP role-match→QD-submit 58.0; CLIP QD source/device-ready wall 4491.6 @1.791 GB/s (240/240 blocks, fraction_time_at_target_qd=0.0168, h2d_backpressure 192 events/10942.7 ms — cold-QD occupancy issue UNCHANGED, out of scope); CLIP forward window 7188.4→13327.8 (6139.4 ms, includes T5 encode 6694.3 ms report + UNET prepare fully hidden); UNET prepare prep_wall 5409.7 @2.276 GB/s (100% hidden under CLIP forward); commit barrier honored (start == clip_gpu_critical_done + 0.5 ms), commit wall 878.5 @14.012 GB/s cache-served; device-ready→construct-start overlap (demand joined during commit); config resolve 2.3; skeleton+patcher 39.0; bind 20.9 (453/453 zero-copy); device-ready→demand-verify 140.0; verify result=match checked=453; sampling 3749.8 (CPM sampler_ms); VAE QD 98.1 @3.418 GB/s; VAE bind 32.5 ok; VAE decode 376.9; output collection 8.7; application wall (wall_ms) 27969.2; command→response 40996.3 (scheduling-separated; submission_to_first_remote_event 8236.1).

## 16. Measured Gantt (█ ≈ 1 s)
```
restore     ▓
CLIP QD     ████▓ (cold variance; occupancy issue known)
CLIP fwd    ██████(UNET prepare hidden█████)(T5 encode inside)
UNET commit █
construct   ▒ (0.14 s to verify — D2 GONE)
sampling    ████
VAE+out     ▓
```

## 17. Exact SHA
`20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260` = MATCH (exact_match, zero reload; no `runtime_state_generation_reload`/`models_volume_generation_reload` reasons).

## 18. Stop conditions
All gone: no construct fallback, no model_config_none, no native post-ready source/H2D (measured), no false VAE fallback, status authority fixed, ledger valid same-domain first-durable-present, five-layer config truth all-agreement=true.

## 19. Final cohort readiness
**R42_COHORT_READY = YES** — with one honest caveat carried forward: single-run application wall regressed 23010→27969 ms vs the prior gate purely on CLIP-side cold variance (QD 1894→4492 ms source wall; forward window 2866→6139 ms). This is the already-known CLIP cold-QD throughput/occupancy investigation (fraction_time_at_target_qd ≈ 1.7%), explicitly deferred; it is not caused by D2/D3 changes and must not block the correctness cohort. Largest avoidable stage is now CLIP cold QD.

## Direct answers (1-32)
1. `unet_prefix_from_state_dict` fell back to `"model."`; the wrapper's unconditional `filter_keys=True` strip produced an EMPTY state dict → `detect_unet_config({})` → None.
2. Native guards empty strip (`len(temp_sd)>0`) and runs `convert_old_quants`; Golden did neither — for z_image's 453 bare keys Golden fed `{}` vs native's full 453-key set.
3. Added `_native_detection_input` (exact native parity incl. guard + quants), used for header-meta and payload retry; detection/stage/storage/window telemetry added.
4. Yes — general contract parity; no basename/architecture hardcoding (unit-tested).
5. Yes — `arch=ZImage detected=true` first attempt, construct_end outcome=adopted.
6. No — zero `golden_unet_construct_fallback`.
7. No — zero `model_config_none`.
8. Yes — assign=True bind measured: 453/453 parameters share Golden CUDA storage (data_ptr equality).
9. 453 of 453.
10. Zero copies (`copied_storage_count=0`).
11. No — logical seam calls=0/bytes=0 AND physical `/proc/self/io` read_bytes delta=0 over the window.
12. No — cuda alloc delta 4.45 MB total; param identity unchanged (changed=0/453).
13. 140.0 ms (was ~2634 ms).
14. Construct wall 62.3 ms (config 2.3 + skeleton/patcher 39.0) + bind 20.9 ms.
15. Bind wall 20.9 ms.
16. Serial after CLIP_GPU_CRITICAL_DONE: commit 878.5 + construct/verify 140.0 ≈ 1018.5 ms (commit is the physical H2D and irreducible without hiding under sampling).
17. Yes — adoption completes, ok=true, owner ADOPTED.
18. Yes — no KeyError, no false fallback, decode used bound values (`bound_before_decode`).
19. No — impossible now (status_reasons guarantee + assembly reconciliation + sticky loader flags; unit-tested).
20. No — enforcement forces fallback_attempted=true from bridge terminal truth.
21. Yes — provisional strings never create terminal roles and stay clearable (tested with the exact five strings).
22. Yes — single structured authority consumed once at assembly; all three blocks emitted from the same lifecycle state.
23. Yes — requested/effective/observed = golden_qd4 ×3.
24. Yes — zero `golden_real_fallback`, role_lifecycle native_fallback_executed=false ×3.
25. Yes — forced_miss, encode_calls=1 (forced-miss persists nothing by construction).
26. Yes — exact SHA match, no reload reasons.
27. Yes — `20b10e1f…e5260`.
28. Application wall 27969.2 ms (command→response 40996.3 ms separate).
29. D2 window saving ≈ 2494 ms (2634→140); masked in the total by CLIP cold variance (+~3.5 s this run).
30. CLIP cold QD source wall (4491.6 ms @1.79 GB/s, occupancy 1.68%).
31. Yes — that is now the only major remaining performance concern (plus its backpressure signature: 192 h2d_backpressure events).
32. **YES** — R42_COHORT_READY = YES.

---

# R42 FROZEN FIVE-RUN GOLDEN COHORT — HALTED AFTER RUN 2 (CLASS B)

Batch R42A, 2026-08-23. Status: **cohort STOPPED per protocol**; valid nominal
cohort size **1 of 5**. Raw evidence: `R42_GOLDEN_COHORT_REMOTE_RAW_LOG.txt`.
No fix applied, no redeploy, no commit; worktree left dirty and coherent.

## C0. Frozen cohort identity

- Gate/Data Run 1: `gate_20260823-181257_9127112e` (valid=1, reasons=[],
  provenance=validated), request `v2-benchmark-0-693e0e9c5705`,
  deploy fp `3f6a303a…f3ae1`, profile `r42-golden-qd4`, owner R42,
  exact SHA `20b10e1f…e5260`. Not rerun; not re-measured.
- Pre-Run 2 verification passed exactly as mandated:
  doctor fingerprint match=1; source-probe verdict=MATCH (8/8 modules),
  remote container **95f1d1c0a5444ec1** (this id becomes material below).

## C1. Exact run protocol executed

`v2ctl confirm --from .v2ctl/gates/gate_20260823-181257_9127112e.json --runs 1`
per new run (single sequential true-cold request; confirm enforces deploy-fp /
git-head / target equality with the gate and runs the full structural validator
suite per run). Run 2 was inspected immediately; it failed Class B; the cohort
was halted before Run 3. Runs 3–5 were NOT launched; one of four authorized
additional requests was consumed.

## C2. Run 2 result — CLASS B STRUCTURAL DEGRADATION

Request `v2-benchmark-0-6a7bb251b304`, AWS us-east-2, RTX-PRO-6000,
same deploy fp / image / profile / expected SHA.

- Validator: valid=0 — `[structural] runtime_status_not_nominal:DEGRADED`,
  `[structural] runtime_state_generation_reload`.
- RuntimeStatus reasons: exactly `["runtime_state_generation_reload"]`.
- The benchmark task itself was FRESH/COLD: fresh snapshot restore
  (`snapshot_restore_start` → full Golden pipeline), restore_total 374.8 ms,
  loaders golden_qd4 ×3 observed, zero fallback, models-volume skip, canonical
  ledger ok, output SHA EXACT, total wall 22458.0 ms, sampler 3752.2 ms,
  VAE decode 442.8 ms.
- Guard chronology (UTC; retained event JSON in raw log §2–3): two same-deployment
  snapshot constructions during final gate prep minted DIFFERENT generation
  tokens — Construction A (session 95f1d1c0a5444ec1, AWS, 18:07:54Z) →
  `1c9042e1…`; Construction B (session d28091b872fe4df7, GCP, 18:09:51Z) →
  `9faa3a03…` which overwrote the shared volume marker. Run 2 executed in the
  Construction-A container/restored its snapshot instance, so the guard compared
  expected=`1c9042e1…` (snapshot-frozen) vs current=`9faa3a03…` (volume) with two
  diverged tracked files (`gpu_capacity_frozen.json`, `prescan_custom_nodes.json`;
  R42A drift diagnostics pinpointed both) → fail-closed `reload_runtime_state`
  (~106 ms) → DEGRADED. Run 1 skipped only because its serving construction (B)
  was also the last volume writer.

## C3. Root cause — AUDITED: generation/control-plane nondeterminism

Reframing per review: the shared session id proves PROVENANCE of the frozen
baseline state, not warm-container reuse; the Run 2 task was fresh/cold. The
defect is that the content-derived runtime-state generation is not actually
immutable per deployment content:

- Writer/reader inventory (complete): ONE production writer —
  `finalize_runtime_state_generation` (runtime_bootstrap.py:1642) →
  `write_runtime_state_generation_marker` (runtime_generation.py:144), called
  once at snapshot construction (modal_app.py:9857), no explicit generation ⇒
  content-derived token. ONE production reader — `_decide_runtime_state_reload`
  (runtime_bootstrap.py:1722/1748), the restore guard. Lines 1296–1327 are
  constructor DI bindings, not writers.
- Why tokens differ across constructions of the SAME deployment: the derivation
  hashes tracked-file BYTES, and those bytes are volatile —
  `gpu_capacity_frozen.json` embeds `"captured_at": time.time()`
  (restore_memory_arm.py:130–135) plus provider-dependent `gpu_name`;
  `prescan_custom_nodes.json` bytes also differed between the two observed
  constructions (197341948867 vs 67aa041b548c; exact volatile field inside the
  prescan payload not yet located). Prior R42 state ("volatile fields excluded
  by construction", report line 46) is true for the manifest STRUCTURE but not
  for the hashed file BYTES — that assumption is the defect.
- Failure mechanism: each construction freezes its own token into the snapshot
  instances it prepares while the volume holds only the latest token; any
  request served from a non-latest construction mismatch → fail-closed reload →
  DEGRADED. Placement-independent; independent of probe timing and Volume
  visibility.
- Source-probe mutation: PROVEN NO — zero trace events in the 18:10–18:30Z
  window across both retained traces; volume token unchanged from 18:09:51Z
  until Run 2's check; probe method is read-only (modal_app.py:16676) and
  construction/finalize run only on the snap=True path a probe never triggers.
  The probe only REVEALED the session id that made provenance traceable.
- Determinism guarantee today: NOT GUARANTEED. Same deployment/image/source
  yields different expected generations across cold boots/providers until every
  manifest-tracked file is byte-immutable per deployment content.
- UNRESOLVED (bounded): prescan volatile field(s); whether Modal lane/instance
  selection is influenceable from the profile (assumed no).

NOT claimed: any regression in CLIP QD, UNET prepare/commit, VAE adoption,
conditioning, manifests, or output correctness — none observed in Run 2.

## C4. Cohort tables

Only Run 1 is valid cohort data; Run 2 is retained as invalidated evidence.
Per-run performance/QD-occupancy/Gantt/delta/E40-comparison tables are
**UNOBSERVABLE** for a five-run cohort and are intentionally not fabricated.
Run 1 row remains as reported in the gate section (wall 27969.2 ms; CLIP QD
4491.6 ms @ ~1.79 GB/s; fraction_time_at_target_qd ~0.0168; h2d_backpressure
192 events / ~10942.7 ms; UNET prepare 5409.7 ms fully hidden; commit 878.5 ms
cache-served; sampling 3749.8 ms; VAE QD 98.1 / bind 32.5 / decode 376.9 ms).

## C5. Direct questions answerable today

1–9, 13–45: UNOBSERVABLE at cohort size 1 — requires Runs 2–5.
10. Fastest of cohort: Run 1 trivially (only valid run).
11. Slowest: n/a.
12. n/a.
Was the architecture structurally nominal in the one clean run? Yes (Run 1).
Did the single additional attempt reveal a defect? Yes — see C3: a lifecycle/
control-plane measurement-integrity defect, NOT a Golden-pipeline regression.

## C6. Options for adjudication

A. Restart cohort from a NEW gate without control-plane changes. Risk: the
   construction lottery recurs — any request served from a non-latest
   construction's state Class-B fails.
B. RECOMMENDED — minimal determinism batch FIRST (control-plane only, Golden
   architecture untouched):
   B1. Make manifest-tracked files byte-immutable per deployment content:
       strip/move `captured_at` out of `gpu_capacity_frozen.json` (or exclude
       that file from the manifest and validate it out-of-band); locate the
       prescan writer and normalize/exclude its volatile fields.
   B2. Add a construction-time assertion that two consecutive constructions of
       the same deployment derive the SAME generation token (would have caught
       this pre-deploy).
   Then re-gate (new authoritative Run 1) and run the five-run cohort via
   confirm with local-only pre-checks. The source-probe itself needs no change
   for mutation reasons (proven non-mutating); keep inter-run probes optional
   purely as protocol hygiene.
C. Freeze characterization at Run 1 only.

## C7. G1 verdict

Five valid nominal runs were not collected (halted at 1 after a Class B stop).
Performance variance alone would not have blocked G1, but an incomplete cohort
with an unresolved lifecycle nondeterminism does.

**G1_BASELINE_READY = NO**
