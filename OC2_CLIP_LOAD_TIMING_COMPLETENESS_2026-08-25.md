# OC2 — Batch CLIP-Load Candidate Timing-Completeness Audit

Phase OC lane OC2 · Date: 2026-08-25 · Mode: READ-ONLY EVIDENCE AUDIT.
No deploy, no paid Modal runs, no source changes, no architecture recommendation, no `GoldenClipLoad_v1` selection.
Repo observed at HEAD `0c59f46e3238f421378e8852ebc548da815b70af` ("e39: prune superseded comfyapp paths…"), branch TESTING2, dirty worktree untouched. Sibling lane `custom_nodes\comfyui-modal-r42` inspected read-only where cited.

Companion file (same directory): **`OC2_CLIP_LOAD_TIMING_CLAIMS_2026-08-25.csv`** — one row per historical timing claim.

---

## 1. Evidence inventory

### Governing Phase-O/OB material (read)
| Artifact | Location | Status |
|---|---|---|
| O7 TIMING & TELEMETRY TRUTH CONTRACT | `%TEMP%\opencode\PhaseO\O7\O7_TIMING_TELEMETRY_TRUTH_CONTRACT.md` | Read in full. Clock domains CD1–CD13, canonical-metric table, SoT challenges |
| Reconciled Phase-O SoT (`COMFYUI_MODAL_V2_GOLDEN_PIPELINE_SOT_PHASE_O_RECONCILED_V2.md`) | searched repo root + temp | **ABSENT locally** (also confirmed absent by OB1 §0). Governing facts taken from O-lane outputs instead |
| Phase-O Revalidation Amendment v2.1 (`COMFYUI_MODAL_V2_PHASE_O_REVALIDATION_AMENDMENT_V2_1.md`) | searched repo root + temp | **ABSENT locally**. Its known correction (five-concepts separation) re-derived from OB1 §1 primary evidence |
| O3 CLIP code/provenance | `PhaseO\O3\O3_CLIP_COMPLETE_CODE_AND_PROVENANCE_REPORT.md`, `O3_CLIP_RUN_PROVENANCE.csv`, `O3_CLIP_IMPLEMENTATIONS.csv`, `O3_FACTS.jsonl` | Read (provenance CSV + F026/F033 verbatim) |
| O6 hash chronology / worktree hashes | `PhaseO\O6\O6_WORKTREE_NOW_FUNCTION_HASHES.csv`, `O6_HISTORICAL_DEPLOYED_CODE_PROVENANCE.md` | Symbol body hashes extracted for cited symbols |
| O8 activation authority | `PhaseO\O8\O8_RUNTIME_AUTHORITY_AND_ACTIVATION_REPORT.md`, `O8_PROFILE_EFFECTIVE_ENV_MATRIX.csv` | Via OB8 claims S/R cross-references (era flag truth) |
| OB2 CLIP-load candidates | `%TEMP%\opencode\PhaseOB\OB2\OB2_CLIP_LOAD_GOLDEN_STAGE_EVIDENCE.md`, `OB2_CLIP_LOAD_CANDIDATES.csv`, `OB2_CLIP_INTERFACE_CONTRACTS.csv` | Read in full |
| OB4 forward contract | `%TEMP%\opencode\PhaseOB\OB4\OB4_CLIP_FORWARD_GOLDEN_STAGE_EVIDENCE.md` | Read in full (defines what the NEXT serialized part consumes) |
| OB7 interface/composability | `%TEMP%\opencode\PhaseOB\OB7\OB7_SERIAL_COMPOSABILITY_PROOF.md`, `OB7_STAGE_INTERFACE_MATRIX.csv`, `OB7_HIDDEN_WORK_AND_DEBT_MATRIX.csv` | Read in full |
| OB8 challenges | `%TEMP%\opencode\PhaseOB\OB8\OB8_SOT_RED_TEAM.md`, `OB8_NUMERIC_BOUNDARY_AUDIT.csv`, `OB8_PRECONDITION_DEBT_AUDIT.csv`, `OB8_CHALLENGE_LEDGER.csv` | Read in full |

### Raw artifacts / source (outrank reports; opened directly)
| Artifact | Path |
|---|---|
| E37 canonical run record | `ComfyUI\comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\run_001_sample.json` (events L120–430, L16000–16660; ledger spans L641–704, L1150–1240); sibling `run_0.json`; `summary.json` (restore_total_ms 303.653, GCP/us-south1) |
| E37 gate/report | `.v2ctl/gates/gate_20260821-223621_f76e3da7.json` (via E37 report); root `E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md` (sha256 `a8a93bb47077c4a5…`, full text read) |
| D12 ARM-A forensics | root `V2_BATCH_D12_CLIP_CRITICAL_PATH_FORENSICS.md` (L1–120 read; underlying raw = `runs/v2_2026-08-16_18-{26-58,29-25,30-19}` event arrays) |
| Modern request-FastSafe raw runs | `runs\v2_2026-08-24_21-{37-12,38-23,39-59}\run_001_sample.json` (R44I3 ARM A gates, req `v2-benchmark-0-22f1972f43f3` et al.), `runs\v2_2026-08-25_02-55-12\…` (K1 reference-bad), `runs\v2_2026-08-25_16-04-15\…` — `clip_fast_load_end` field blocks read directly (L~7245–7345 each) |
| E26 speculative | root `V2_BATCH_E26_CONCRETE_COLD_WINS.md` L85–159, L378–457, L578–620. Raw run artifacts for cycles 1–2: **NOT_FOUND_LOCALLY** (O3 provenance rows 2–3) |
| Native/cache-miss report | root `REAL_CLIP_CACHE_MISS_REPORT.md` L1–80 (raw sources: `runs/v2_2026-08-12_{00-38-13,00-43-08,00-45-21}/run_0.json`) |
| Current production source (worktree @0c59f46 dirty) | `comfymodal_runtime/clip_fast_hydration_wiring.py` (`_try_fast_hydrate` L1206+, clean-lane branch L1319–1442 verified, bind/wait/publication L1689–1774 verified, `_fastsafe_load` L800–842 verified, fallback L2051+/L2174+); `comfymodal_runtime/clip_fast_hydration.py` (`hydrate_clip_bind` L1476–1531, `_zero_copy_evidence_clip` L1440–1473 verified); `comfymodal_runtime/clean_lane.py` (`mark_qd_start/mark_qd_ready/mark_bind/proof`); `comfymodal_runtime/speculative_clip_hydration.py` (`join_speculative_clip_lane` L924, `take_speculative_read` L944, lane threads daemon L557/L1209/L1333) |
| Modern request-FastSafe implementation | **exists only in sibling**: `..\comfyui-modal-r42\comfymodal_runtime\request_clip_fastsafe.py` (3013 lines; `_make_load_wrapper` L225, `_produce_clip_fastsafe_native` L2180, transport call site L2433–2435, success telemetry L2690–2760, `_register_residency` L1703–1780 read; **no `torch.cuda.synchronize()` / scoped-event wait anywhere in module** — grep verified) |
| Naming traps checked | root `rtx_region_ab_armA.log` = Aug-10 region-A/B deploy harness log (unrelated to hydration “ARM A”); root `arm_a_config.txt`/`arm_b_config.txt` empty (OB2 §6 concurrence) |

Raw artifacts outrank reports throughout; every accepted timing below was re-read at its primary artifact unless explicitly labeled REPORT_ONLY.

---

## 2. Candidate list

Exactly the candidates O/OB established as executed and potentially reusable (no new candidates added; no dead-loader inventory):

| ID | Implementation (exact) | Historical executions with numbers | Status in this audit |
|---|---|---|---|
| **CAND-QD-E37** | Production `clip_qd_reader.read_file_qd_gpu` via `clip_qd_load`, synchronous clean-lane demand branch (`loader_arm="qd_demand"`), shared assign-bind consumer | E37 run `v2-benchmark-0-c9ac6e750942` (profile `e37-clean-lane-qd4`, fp `9ea14a71…`, image `im-QypPckt7SwaTFzJSG8AgXs`, GCP/us-south1, restore_total 303.653 ms) | Primary; raw-anchored n=1 |
| **CAND-FS-D12** | `_fastsafe_load` (fastsafetensors `SafeTensorsFileLoader` nogds T8/B64MiB/bbuf512MiB) inside `_try_fast_hydrate` demand loop + same-storage assign bind + explicit post-bind `torch.cuda.synchronize()` (“Hydration path A”) | D11/D12 runs 2/5/6 (`v2_2026-08-16_*`, us-east4 ×2, AWS us-east-1 ×1) | Primary historical ARM-A(sense-1) class |
| **CAND-FS-REQ** | Sibling-lane `request_clip_fastsafe._produce_clip_fastsafe_native`: request-entry `CLIPLoader.load_clip` interception → header gates → same `_fastsafe_load` transport → scoped construction seams (meta skeleton + assign `load_sd`) → fail-closed validation → publication + early residency registration. No in-module device sync | R44I3 ARM A gates ×3 (Aug-24 21:37/21:38/21:39), K1 cohort + reference-bad (Aug-25), plus K4/R44E/J1-era raw fields (O3 F026) | Primary modern class; raw-anchored |
| **CAND-SPEC-E26** | `speculative_clip_hydration` producer started at plan receipt (FastSafe arm, frozen-manifest paths), demand joins (bounded wait) then takes + verifies/binds | E26 cycle 1 (unconsumed → duplicate read) + cycle 2 ×2 consumed runs (Aug-18). Raw run dirs absent locally | Secondary; REPORT_ONLY numbers |
| **CAND-NATIVE** | Comfy-native CLIP reconstruction (`_hydrate_cpu_assign` → `_invoke_native_clip_loader` → `_hydrate_native_copy` chain; also the plain native node path) | No valid historical *cold CLIP-weight* native-load measurement found (see §5.4 — OB2’s cited numbers belong to the UNET fast-disk load) | Retained as fallback contract only |

Rejected evidence (kept out, with reason):
- **REJ-R41R42** `golden/qd_engine.py GoldenQD4Loader` — never integrated into any root production request path; different API/ownership; the “R42 4.4916 s collapse” headline was FALSIFIED by OB8 (unit error: value is milliseconds, per-block probe timing; SUPERSEDE).
- **REJ-E27PROBE** `_e27_direct_probe.py` QD matrix — source-only by construction (H2D/header/allocation excluded); page-cache-warm suspicion recorded (E38/O3); geometry-selection evidence only.
- **R44F CLIP leg** — INVALID: BF16-vs-FP16 expectation mismatch skipped FastSafe entirely (gate INVALID; O3 row 10).

---

## 3. GoldenClipLoad completion contract — DERIVED FROM CODE (not telemetry names)

Derived from the actual implementations and from OB4’s observed `GoldenClipForward` input requirements (§6 there): forward began only after (a) CLIP bound on `cuda:0`, (b) hydration/load phases complete, (c) owner-retained storage, (d) `load_models_gpu` pass done, (e) no candidate background work concurrent. Therefore a serial CLIP-load stage would have to guarantee, before returning:

1. **Required input state** — resolved absolute source path(s) present (`os.path.exists` guard, wiring L1345); a CLIP object/skeleton exists to bind into (excluded-weights placeholder `EXCLUDED_PLACEHOLDER`, or meta-skeleton under request-native seams, or live CPU object); eligibility gates passed (dtype/device/manifest freshness; `qd_config()` requires enabled + QD==4 exactly + block_mib ≥1 + launch policy non-empty — wiring L1326–1341).
2. **Expected output object(s)** — a structural CLIP whose `cond_stage_model` parameters ARE the transported tensors: `can_assign_sd=True` forced on all leaves, Comfy `load_sd` assign dispatch (clip_fast_hydration.py L1500–1504; request-native seams serve tensors through `load_torch_file` override + `text_encoder_initial_device` yielding meta). Tokenizer blob keys are constructor-consumed, never bound (proof excludes them, cfh L1450–1454).
3. **CUDA residency requirement** — every file-covered parameter resident on `cuda:<current>` and verified (`expect_device` off-list check cfh L1521–1530; request-native `_validate_native_bind` fails closed on meta residuals/storage mismatch/shape-dtype divergence). Note: E37’s own residency proof stamped `state="INVALID/PARTIAL"` (params cpu=1, cuda=398 — one ctor-owned CPU leftover, e.g. constant-init param) yet forward proceeded; a strict contract must decide whether that residual is acceptable (observed-historically: yes).
4. **Model construction/bind state** — bind is a semantic storage-replacement boundary: `reset_clip_hydration_for_bind` before replace (cfh L1493–1499; wiring L1698); zero-copy identity proof passed (data_ptr + untyped_storage().data_ptr() + shape + dtype equality per covered key, cfh L1440–1473; E37: 398/398, non_same_storage=0; request path: `same_storage_count=398`, `non_same_storage_count=0`).
5. **Owner lifetime** — producer owners `(loader, fb)` MUST outlive every view; appended to `owners` and attached to the patcher (`owner_attach` → `_FastsafeOwner` list on `_comfymodal_clip_fh_owner`, cfh L1682–1693; request-native OWNER_ATTR + ON_DETACH safety hook); retirement only via non-destructive `release_storage(purge_allocator=False)` after proven cast-once; close is idempotent, views-dead-only.
6. **Validation/publication state** — proofs precede publication; publication = `mark_clip_hydrated` + canonical endpoint `clip_device_ready` (+ `loader_interval{start,ready,loader_arm,wall_ms}`, wiring L1746–1774) + `clean_lane.mark_bind`; request-native adds sticky `record_observed`, `publish_result`, early residency registration via `comfy_mm.load_models_gpu([patcher], force_full_load=True)` bookkeeping-only call (`clip_fastsafe_residency_register`, measured 40.799 ms in run 21-37-12).
7. **Worker/future completion requirement** — all candidate-owned readers joined and H2D complete BEFORE bind: clean-lane quiescence proof requires ALL of `source_reads_complete, submitted_blocks_reconciled, futures_joined, no_qd_worker_runnable, pinned_ownership_safe, h2d_events_complete, device_ready_published` true, else raise `CLEAN_LANE_QD_NOT_QUIESCENT_BEFORE_BIND` (wiring L1370–1382; E37 run record shows all seven true at L16211–16219).
8. **Nothing candidate-owned pending at return** — the stage may not leave source reads, H2D copies, worker threads, or bind/sync work running past its return. QD path proves this positively (event sweep + joins before bind; bind_wait 0.142 ms). The wiring-FastSafe path closes it with an explicit `torch.cuda.synchronize()` INSIDE the window (bind+sync sub-span). The request-native path contains NO explicit synchronize/event-wait (module-wide grep negative) — pending-H2D-at-publication is therefore UNPROVEN there (bounded below).
9. **Allowed/visible fallback** — fallback is never nominal: QD failure → outer cleanup + `fallback_count=1 MODE_NATIVE` chain (`_hydrate_cpu_assign` second read → `_hydrate_native_copy` fresh construction + clone) surfaced DEGRADED by `loader_selection`; clean lane converts mid-stage failure to hard raise; request-native fail-closes to original node method with sticky terminal reason + canonical native observation. A compliant stage must return either the proven-complete fast result or a marked-fallback result — never silently.

**Consequence for timing:** `TOTAL` for GoldenClipLoad = interval covering [first candidate-owned prerequisite work that is NOT already paid outside the stage] through [publication + proof + last H2D/worker completion]. Any metric stopping at source-read end, device-buffer-fill end, or copy-call return is `PARTIAL`.

---

## 4. Bespoke execution narratives (per candidate, from exact code/artifacts)

### 4.1 CAND-QD-E37 — integrated QD production path

Execution shape (worktree bodies byte-identical to E37 checkpoint per OB2 §5 symbol-hash matrix): demand wrapper → `_try_fast_hydrate` → speculative take attempt (none; lane empty) → clean-lane gate → `clip_qd_load` → header parse → static block planner (240×32 MiB) → ONE contiguous `torch.empty(8044936192, uint8, cuda)` → 4 workers × 2 pinned slots (256 MiB) + paired events → async preadv + `copy_(non_blocking)` per block → join workers → sweep ALL slot events → validate records (240/240 reconciliation) → alignment-checked zero-copy views (398) → `QdGpuOwner` → take/bind/owner-retained events → quiescence proof (all 7 keys) → `hydrate_clip_bind` assign-bind → bind_wait (scoped/global) 0.142 ms → `clip_device_ready` publication → `clean_lane.mark_bind` → residency-proof scan → hydration-record emission.

Boundary arithmetic from the raw record (all monotonic ns, one process):
| Question | Answer |
|---|---|
| What has completed at ~1043.514 ms? | ONLY the source-read submit window: first worker start → last source end (`total_source_wall_ms=1043.5138`; first_completion 9.9985, tail spread 1033.5153). H2D mostly still in flight; no views; no bind. **Transport operation complete; model nowhere ready.** |
| What has completed at ~1080.424 ms? | submit_start(217557211917; OB8 derives 217557183787 from run_0.json twin) → `clip_qd_device_ready`(218637617228/218637607918): all 240 blocks read AND all slot H2D events complete (`h2d_events_complete=true`), stats finalized. Views/owner not yet built; bind not started. **Device-buffer ready; still PARTIAL for GoldenClipLoad.** |
| What has completed at ~1149.953 ms? | The full ledger span s15 (217540345940→218690303521, `duration_ms=residual_ms=1149.953`, source `_try_fast_hydrate`): planning (~15.7 ms pre-QD), entire QD phase (qd_start 217556019937 → qd_ready 218637635118 = 1081.615 ms), take/bind events, assign-bind + bind_wait 0.142 ms, `clip_device_ready` (218685180002), `clean_lane_bind` (218685272102), residency-proof scan (218689529801), hydration record emission (end 218690303521). **This is the only measured interval whose end coincides with model-ready publication.** |
| Usable-by-next-part boundary | First satisfied at bind+wait completion ~218685181000 ns class (= qd_ready + 47.545 ms publication tail). Forward span s17 starts 218695575911 — after everything above. |
| Are all source workers joined? | YES — `no_qd_worker_runnable=true`, `futures_joined=true` (L16215–16214). |
| All H2D events complete? | YES — `h2d_events_complete=true`; host issue total 127.39898799983962 ms; max CUDA event 27.3155 ms. |
| Views/binding/ownership published? | YES — 398 views, `same-storage` assign (non_same_storage=0), `clip_qd_owner_retained` (demand side, owners=1), patcher attachment per §3.5. |
| Anything candidate-owned still running later? | NO in-project work; owner retention is deliberate lifetime (not pending work). Forbidden-overlap list EMPTY during the window; five earlier `forbidden_activity_attempts` were blocked OUTSIDE it (background diagnostics ×3, plan-time UNET H2D attempt, execution_prefill). |
| Required CLIP work before the measured interval? | Restore carried a FULL CLIP CPU payload (snapshot double-read redundancy, disclosed by E38A/OB2) — dead weight, not consumed by the stage; no required load work preceded the span. Plan identity completed pre-span (217125351191). |
| Restored/cache state assumed | Post-restore volume read; page-cache state NOT recorded (no field exists); conditioning forced miss (`clean_lane_forced_miss`). |

Completeness classes: source-wall 1043.514 = TOTAL_FOR_MEASURED_OPERATION(source window) / PARTIAL_FOR_GOLDEN_PART. 1080.424 = TOTAL_FOR_MEASURED_OPERATION(submit→device-ready) / PARTIAL_FOR_GOLDEN_PART. 1081.615 = same class (phase-interval variant). **1149.953 = TOTAL for the measured hydration span AND the closest historical proxy to GoldenClipLoad-TOTAL** (its tail ≈52.7 ms is publication/bookkeeping, which the contract REQUIRES; its head ≈15.7 ms is planning, also candidate-owned). Caveat: n=1; span overhead split 15.674 ms pre / 52.668 ms post is arithmetic, not separately metered.

Contamination: NONE_PROVEN in-window (forbidden_overlap=[], gpu_operation_overlap=[]; forward later verified uncontended). Cache state: PARTIAL-known. Fallback: none (fallback=false, fallback_count=0).

### 4.2 CAND-FS-D12 — FastSafe + ARM-A (sense 1) demand path

Shape: `EXCLUDED_PLACEHOLDER` CLIP (weights stripped by snapshot exclusion prep) → demand wrapper → `_try_fast_hydrate` FastSafe loop → `_fastsafe_load` (library threads; 512 MiB bounce pool) → dict of GPU views → optional cast-once hook → scoped copy event OR `torch.cuda.synchronize()` → assign bind → `clip_fh_hydration_decision/start/end` telemetry (start/end emitted back-to-back at COMPLETION — D12 finding #2).

Per-run decomposition (report tables over raw event arrays):
| Run | Hydration decision→end | file→GPU | bind+sync | Classification |
|---|---|---|---|---|
| Run2 us-east4 | 4362.2 (4358.7 alt accounting) | 1401.9 / 1468.5 | **2889.7** | bind window WAIT-dominated: UNET meta/H2D lane overlapped 2850/2890 ms (cuda_delta fingerprint) |
| Run5 us-east4 | 1533.5 | 1401.9 | 120.8 | uncontended |
| Run6 AWS us-east-1 | 1952.9 | 1850.5 | 93.8 | slower AWS volume |

Answers: file_to_cuda alone is NOT the complete load — construction/adoption happens after it and is included in these totals; the explicit sync IS inside the claimed window (so pending-H2D-at-return is closed HERE, unlike the request-native path); source/prefetch work earlier: exclusion prep happened at capture (manifest), not a prior read; same-storage proof occurs INSIDE the claimed window (zero-copy 398/398 emitted at end); hidden native rereads: none on healthy runs (`fallback_count=0`).

Completeness: hydration totals are TOTAL_FOR_GOLDEN_PART-equivalent boundaries (decision→end covers entry through publication-class end) BUT Run2 is CONTAMINATED (EXTERNAL_BLOCKING proven — its 4362.2 measures shared-GPU contention, not candidate cost). Run5/Run6 are cleaner but carry UNKNOWN per-run backend/page-cache state (never recorded). n=3 mixed-placement single samples.

### 4.3 CAND-FS-REQ — modern request-FastSafe / ARM-A sense-2 same-storage native path

Shape (sibling `request_clip_fastsafe.py`): request-entry context engages wrapper → duplicate-load claim → header descriptors (freshness-checked) → pre-transport dtype/device gates → `_fastsafe_load` transport (setup → `copy_files_to_device` → get_keys → get_tensor loop) → allocator snapshots → SEAM-LOCKed scoped construction (meta skeleton + served-tensor `load_torch_file` + assign `load_sd`) → fail-closed full-mapping validation (398/398 same-storage, meta-residual hard-fatal with ctor-leftover exception) → publication (sticky observed-arm, `publish_result`, `clip_fast_load_end` telemetry) → `_register_residency` (`load_models_gpu` bookkeeping, ~40 ms).

Raw decompositions (all `cuda_allocated_before_bytes=0` ⇒ CLIP NOT resident; full fresh transport each run):
| Run / request | setup | copy wall | descriptor | file_to_gpu_wall | construction(bind) | notes |
|---|---|---|---|---|---|---|
| 08-24_21-37-12 / `22f1972f43f3` | 8.987 | 1448.965 | 18.756 | **1566.653** | 255.707 | residency_register 40.799; NOMINAL SHA_OK |
| 08-24_21-38-23 | 11.509 | 2369.602 | 29.184 | **2433.150** | 310.889 | |
| 08-24_21-39-59 | 10.738 | 2226.318 | 28.532 | **2283.353** | 295.955 | |
| 08-25_02-55-12 (K1 ref-bad) | 9.602 | 1366.646 | 21.753 | **1497.197** | 368.265 | reference-bad era for RESTORE, not CLIP |
| 08-25_16-04-15 | 15.549 | **26295.783** | 23.132 | **26390.147** | 384.932 | pathological outlier, cause uninstrumented |
| O3 F026 band (K4/R44E/J1 eras) | 7.318 (K4) | 1359.126 / 1934.712 / 1517.928 / 1366.646 | — | 1429.867 (K4) | 396.53 (K4; fast_load total 1967.930) | mixed RAW/NARRATIVE confidence |

Answers: `file_to_cuda` (file_to_gpu_wall_ms) is TRANSPORT-ONLY — model construction/bind/adoption happen AFTER it in `construction_wall_ms` and are EXCLUDED; so file_to_gpu alone is PARTIAL for GoldenClipLoad. A GoldenPart-total would be ≈ descriptor + file_to_gpu + construction (+validation) — e.g. 21-37-12 ≈ 18.756 + 1566.653 + 255.707 ≈ 1841 ms class — but this sum is ARITHMETIC, never measured as one interval. Earlier source/prefetch work: none required (works without earlier background prep); early-staging variant exists (`stage_early_clip`, bounded 30 s wait) but no consumed-staging run with numbers is in the audited set. Same-storage proof: INSIDE the producer window (validation before publication). Hidden rereads/fallbacks: none on these runs (`ok:true`; R44F-style skip is the negative control). **Critical completeness gap: the module contains NO `torch.cuda.synchronize()` and NO scoped copy-event wait (grep-verified). Whether FastSafe H2D is device-complete at publication is NOT proven by in-module instrumentation; the D12-era sibling path needed an explicit sync precisely because copies could lag (Run2). Pending-completion at return = UNKNOWN for this class.**

### 4.4 CAND-SPEC-E26 — speculative producer considered synchronously

ALL candidate-owned work before demand: lane armed at restore/plan-receipt (daemon thread), paths resolved from frozen manifest, freshness pre-check, FULL FastSafe source read + H2D executed during setup (before checkpoint prewarm; CLIP-first graph means demand arrives only ~0.7–0.85 s after producer start while the 8 GB read takes ~2.1–2.6 s).

Cycle 1 (`85d5e64941a9`, us-east1): producer read completed 2.59 s UNCONSUMED (`take_speculative_read` returned None — no join existed); demand performed a SECOND full 8 GB read (2.61 s). Inclusive candidate work = 2.59 + 2.61 ≈ 5.2 s of reads for one load; exposed demand cost 2.61 s.
Cycle 2 (`5b75574863e7`, `8cff03a70fb4`, us-east4): bounded join added (`join_speculative_clip_lane`, then take); `joined_lane_ms=2119.9–2432.8`; spec CONSUMED, duplicate read NO; exposed hydration **2429.8 / 2075.5**; forward 8132.5 (contended) / 3160.0.

Do-not-call-demand-join-"total" rule applied: the demand-side exposed 2429.8/2075.5 measures join-wait + verify + bind only. Producer read time (≈2.1–2.4 s class) ran EARLIER under setup — hidden share NOT separately metered (UNKNOWN split; OB8 P6 debt=YES, inclusive UNKNOWN). Historical critical-path exposure = the exposed portion; inclusive candidate work = exposed + hidden producer share. Verify/bind at demand: yes (`PARTIAL(bind/verify only at demand)` per OB2 serial table). Producer failure edge releases UNET prefetch immediately (release-once guard) — no deadlock, but a failed/rejected lane duplicates the read (cycle-1 materialized).

Evidence tier: numbers are REPORT_ONLY locally (raw run dirs absent; O3 provenance rows 2–3 mark NARRATIVE_ONLY with UNKNOWN deployment binding).

### 4.5 CAND-NATIVE — native/current fallback

Contract (code): `_hydrate_cpu_assign` materializes a full CPU state_dict (mmap) + assign bind at CPU → `_invoke_native_clip_loader` → `_hydrate_native_copy` fresh native construction + per-parameter clone; plain native path performs its own H2D inside `load_model`. It IS the terminal fallback; model-sized CPU materialization + native H2D guaranteed.

**Finding (misattribution corrected):** OB2’s CLIP-C4 row cites 2225.089/2230.805/2279.842 ms as “native fast-disk load”. Those exact values are `to_wall_ms` of the **native fast-disk UNET** load in `REAL_CLIP_CACHE_MISS_REPORT.md:40-43` (bind + `to` cuda:0), NOT a CLIP load. Moreover, in those three runs the CLIP weights were NEVER cold-loaded natively: `clip_present=1`, `cpu_snapshot_clip_vae_bind status=ok` published the snapshot-RETAINED CLIP; only the *conditioning* cache missed (hit_count=0/miss_count=1). The genuinely CLIP-side numbers there are: CLIPTextEncode node wall 1271.832/1385.929/1454.204 ms (includes tokenize+schedule+encode of a retained model), cache lookup 162.962/213.84/472.854, cache store 928.605/1668.254/932.587, prefill totals 2380.969/2812.933/3359.881. **No historical TOTAL (or partial) measurement of a true-cold native CLIP weight reconstruction exists in this evidence set.** Serial executability of the fallback chain is code-proven; its cost is UNKNOWN.

---

## 5. Timing completeness findings (classification per claim)

Classes: MOC = MEASURED_OPERATION_COMPLETENESS; GPC = GOLDEN_PART_COMPLETENESS. Full per-claim rows with raw anchors: `OC2_CLIP_LOAD_TIMING_CLAIMS_2026-08-25.csv`.

### 5.1 CAND-QD-E37
| Claim (ms) | Boundary | MOC | GPC | Contamination |
|---|---|---|---|---|
| 1043.514 | source wall (worker-start→last source-end) | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN |
| 1080.424 | submit_start→device_ready (OB8-F derivation) | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN |
| 1052.528 | `device_ready.wall_ms` field (earliest-source-start base) | PARTIAL_FOR_MEASURED_OPERATION (different base than 1080.424; do not merge) | PARTIAL | NONE_PROVEN |
| 1081.615 | clean-lane qd_start_ns→qd_ready_ns phase interval | TOTAL_FOR_MEASURED_OPERATION | PARTIAL | NONE_PROVEN |
| 127.399 / 27.3155 | H2D host-issue total / max CUDA event | TOTAL (sub-metrics) | PARTIAL | NONE_PROVEN |
| 47.545 | qd_ready→clip_device_ready publication tail | TOTAL (arithmetic) | component-of-TOTAL | NONE_PROVEN |
| 0.142 | bind_wait | TOTAL (sub-metric) | component-of-TOTAL | NONE_PROVEN |
| **1149.953** | ledger span `_try_fast_hydrate` open→close | **TOTAL_FOR_MEASURED_OPERATION** | **TOTAL-equivalent boundary (closest historical proxy; n=1)** | NONE_PROVEN |
| 1144.902/.903 | `loader_interval.wall_ms` (clip_loader_start→clip_device_ready) | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (ends at endpoint emit; excludes residency scan + record emission ≈5 ms tail) | NONE_PROVEN |
| 1085.319 | `file_to_gpu_wall_ms` field of `clip_fh_hydration_end` (wraps `clip_qd_load` call only) | TOTAL_FOR_MEASURED_OPERATION(call) | PARTIAL | NONE_PROVEN |

Work before interval owned by candidate: none required (planning inside span head). Work after: none pending; owner retention is lifetime, not work. Precondition debt: restored redundant CPU payload (disclosed, not charged). CACHE_STATE: post-restore volume read; page-cache UNKNOWN. FALLBACK_STATE: none.

### 5.2 CAND-FS-D12
| Claim | MOC | GPC | Contamination |
|---|---|---|---|
| 4362.2 (run2 hydration total) | TOTAL_FOR_MEASURED_OPERATION | PARTIAL (wait-dominated; not candidate cost) | **EXTERNAL_BLOCKING (proven)** |
| 1533.5 (run5) | TOTAL_FOR_MEASURED_OPERATION | TOTAL-equivalent boundary | MIXED/UNKNOWN (backend cache unrecorded) |
| 1952.9 (run6) | TOTAL_FOR_MEASURED_OPERATION | TOTAL-equivalent boundary | MIXED/UNKNOWN + placement variance |
| 1468.5/1401.9/1850.5 file→GPU | TOTAL (transport) | PARTIAL | — |
| 2889.7/120.8/93.8 bind+sync | TOTAL (window) | component (REQUIRED by contract) | run2: EXTERNAL_BLOCKING |

Pre-work: exclusion-manifest capture prep (prerequisite so hydration is mandatory). After-interval: none pending (explicit sync inside window). FALLBACK_STATE: none (fallback_count=0). n=1 per configuration; placements differ.

### 5.3 CAND-FS-REQ
| Claim | MOC | GPC | Contamination |
|---|---|---|---|
| file_to_gpu_wall 1497.197–2433.150 (4 healthy) | TOTAL_FOR_MEASURED_OPERATION (transport-only) | PARTIAL (construction excluded) | UNKNOWN per-run (no overlap telemetry audited) |
| fastsafe_copy_wall 1366.646–2369.602 (healthy) | TOTAL (library copy window) | PARTIAL | UNKNOWN |
| construction_wall 255.707–384.932 | TOTAL (construct+validate window) | REQUIRED component, measured separately | UNKNOWN |
| 26390.147 (16-04-15) | TOTAL_FOR_MEASURED_OPERATION (raw) | UNKNOWN — outlier cause uninstrumented | UNKNOWN (suspect EXTERNAL_BLOCKING/stall; UNPROVEN) |
| ≈1841 ms arithmetic total (21-37-12: desc+file_to_gpu+construction) | DERIVED — NOT a measurement | closest this class offers; still missing pending-H2D proof | — |
| 398/398 same-storage, copied_count=0, owner_retained=true | count metrics (OB8-J CONFIRMED) | validation-state components | — |

**Class-level finding: pending-H2D-at-publication UNKNOWN (no in-module sync).** Golden-part TOTAL: UNKNOWN (never measured as one interval). Prerequisite debt: none required. CACHE_STATE: fresh transport each run (`allocated_before=0`); volume page-cache UNKNOWN per run.

### 5.4 CAND-SPEC-E26
| Claim | MOC | GPC | Contamination |
|---|---|---|---|
| 2429.8 / 2075.5 exposed hydration | TOTAL_FOR_MEASURED_OPERATION(demand join+verify+bind) | **PARTIAL** (producer read predemand, hidden share UNKNOWN) | MIXED (overlap-with-setup is the mechanism) |
| joined_lane_ms 2119.9–2432.8 | TOTAL (join window) | PARTIAL | MIXED |
| cycle-1 2.59 s producer + 2.61 s demand re-read | TOTAL each (REPORT_ONLY) | inclusive ≈5.2 s reads per load | UNRELATED_WORK duplicated by design gap |

All rows REPORT_ONLY (raw artifacts absent locally).

### 5.5 CAND-NATIVE
OB2-cited 2225.089/2230.805/2279.842 as “native CLIP”: **INVALID — wrong model (native fast-disk UNET `to_wall_ms`)**; also the runs’ CLIP was snapshot-retained (`cpu_snapshot_clip_vae_bind ok`), so no native CLIP reconstruction was measured at all. True-cold native CLIP-load timing: UNKNOWN (no artifact). The seriality fact (CLIP encode ↔ UNET load overlap = 0.0 ms, three runs) applies to UNET, not CLIP load.

---

## 6. Equivalent / non-equivalent timing matrix

Equivalence requires: semantic completion condition + model + dtype + implementation-or-semantic-equivalence + cache/snapshot input state + provider/resource class where material + fallback state.

| A vs B | Verdict | Reason (proven differences) |
|---|---|---|
| E37 1043.514 / 1080.424 / 1081.615 / 1149.953 (mutual) | **PARTIAL-comparable** (same run, same implementation, deliberately different boundaries) | Same draw, same clock domain, same model/dtype; completion conditions differ by construction (documented siblings — do not merge, may be co-presented) |
| E37 1149.953 ↔ D12 1533.5/1952.9 | **INVALID** | Different implementation (own QD engine vs fastsafetensors library), different span composition (ledger span incl. planning/publish tail vs decision→end outer), different era flags, cache states differ (post-restore reread vs unrecorded backend), n=1 each, placements differ (us-south1 vs us-east4/AWS) |
| E37 1149.953 ↔ D12 4362.2 | **INVALID (+contaminated)** | All of the above PLUS proven external blocking in B |
| D12 1533.5 ↔ D12 1952.9 | **PARTIAL** | Same implementation/boundary/dtype/model; cache backend unrecorded per-run; providers differ (GCP vs AWS) |
| FS-REQ file_to_gpu family (1497.197/1566.653/2283.353/2433.150) mutual | **PARTIAL** | Same emitter fields, same implementation lineage, same fresh-transport input state (`allocated_before=0`); placements/profile drift across dates; 26390.147 excluded (outlier) |
| FS-REQ file_to_gpu ↔ FS-REQ construction_wall | **NON-equivalent components** (summing allowed only as labeled arithmetic, never as a measurement) | Different windows by emitter design |
| E37 QD ↔ FS-REQ (any) | **INVALID** | Different engines, different publication guarantees (QD: proven H2D-complete pre-bind; REQ: unproven sync), different bind machinery |
| E26 exposed ↔ E37/D12/FS-REQ any | **INVALID** | Demand-side partial vs whole-stage semantics; producer share UNKNOWN; REPORT_ONLY tier |
| C9 UNET FastSafe 2172.92 ↔ anything-CLIP | **INVALID (wrong model)** | UNET analog; additionally warm/cross-state comparison already condemned (OB8-M) |
| OB2 “CLIP-C4 2225–2280 native CLIP” ↔ any CLIP claim | **INVALID (wrong model — UNET to_wall_ms)** | This audit’s correction of OB2 §2/§3 |

---

## 7. Candidate result matrix

| Field | CAND-QD-E37 | CAND-FS-D12 | CAND-FS-REQ | CAND-SPEC-E26 | CAND-NATIVE |
|---|---|---|---|---|---|
| CAN_SATISFY_GOLDEN_PART (per §3 contract) | YES (positively proven: all 7 quiescence keys + proofs + publication) | YES (sync closed inside window; proofs inside) | YES structurally, with ONE unproven clause (pending-H2D at publication UNKNOWN) | YES at consume; violates nothing-pending-before-return only if producer treated as outside stage | YES (is the contract’s designated fallback) |
| HISTORICAL_TOTAL_KNOWN | YES — 1149.953 ms span (n=1) | PARTIAL — 1533.5 / 1952.9 clean-ish; 4362.2 contaminated (n=1 each) | NO whole-stage total; transport+construction separately (arithmetic ≈1.84–3.09 s healthy class) | NO (exposed-only; hidden producer share UNKNOWN) | NO |
| TOTAL timing/range | 1149.953 ms (single validated draw) | 1533.5 / 1952.9 ms (single draws, boundary-equivalent pair) | UNKNOWN (derived-only ≈1841 ms best-case class, 21-37-12) | UNKNOWN | UNKNOWN |
| Known partial timings | 1043.514 src; 1080.424/1081.615/1052.528 device-ready variants; 1085.319 call-wrap; 1144.903 loader_interval; H2D 127.399/27.3155; tails 47.545/0.142 | file→GPU 1401.9/1468.5/1850.5; bind+sync 2889.7(contam)/120.8/93.8 | copy 1366.646–26295.783; file_to_gpu 1497.197–26390.147; construction 255.707–384.932; descriptor 18.756–29.184; residency 40.799 | exposed 2429.8/2075.5; join 2119.9–2432.8; cycle-1 dup reads 2.59 s+2.61 s | lookup 162.962–472.854; encode-node 1271.832–1454.204 (retained-model encode, NOT load); store 928.605–1668.254 |
| Prerequisite debt | restored redundant CLIP CPU payload (dead weight; disclosed); page-cache state unrecorded | capture-time exclusion-manifest prep (mandatory so hydration triggers) | none mandatory; early-staging variant exists unconsumed-in-audit | producer thread + manifest + ownership hold from plan receipt | full native reconstruction stack |
| Work outside timer | none pending (owner lifetime ≠ work) | none pending (sync inside) | possible in-flight H2D at publication (UNPROVEN) | ENTIRE producer read outside demand timer (hidden share UNKNOWN) | native H2D inside node call; CPU mmap inside |
| Contamination | NONE_PROVEN | run2 EXTERNAL_BLOCKING proven; run5/6 UNKNOWN-cache | UNKNOWN per-run; one 26.39 s pathological outlier unexplained | MIXED by design (setup overlap) | n/a |
| Serial executability (as-is, synchronous stage) | PROVEN by the E37 execution itself | PROVEN historically (D12 runs) | PROVEN historically (R44I3/K1 runs) — modulo unproven H2D-quiescence clause | NO as pure serial stage (mechanism REQUIRES earlier start); viable only counting producer as separate earlier stage | YES (code-proven chain) |

---

## 8. Evidence gaps

1. **Reconciled Phase-O SoT + v2.1 amendment ABSENT locally** — governing corrections were re-derived from O-lane primaries (OB1 §0 method reused); any quotation of those documents remains impossible here.
2. E26 raw run directories for both cycles ABSENT locally — all speculative numbers REPORT_ONLY; deployment binding UNKNOWN (O3 provenance).
3. No whole-stage interval was ever emitted for the request-FastSafe class; `file_to_gpu` + `construction` are adjacent but unjoined; no arithmetic field exists.
4. Pending-H2D-at-publication for `request_clip_fastsafe` unproven (no sync/event-wait instrumentation); fastsafetensors internal completion semantics not established from artifacts.
5. Per-run backend/page-cache state absent for EVERY candidate except native-cache-miss runs (which measured the wrong model for this audit) — cache_state columns remain PARTIAL/UNKNOWN.
6. E37 n=1: no second clean-lane-qd4 draw exists in the corpus (OB4 §8 corpus scan concurrence); capability proof, not a band.
7. The 26390.147 ms outlier (16-04-15) has no causal instrumentation.
8. E37 residency proof labels the bound object `INVALID/PARTIAL` (cpu=1 ctor leftover) — whether a strict GoldenClipLoad must fail or tolerate this is undecidable from evidence (historically tolerated).
9. `clip_loader_start`-anchored `loader_interval` (1144.903) vs ledger span (1149.953) differ by design (~5 µs head start, ~5 ms longer tail); no artifact reconciles them into one preferred number — both reported, neither canonized.
10. D12-era raw event arrays were consumed via the D12 report’s tables (report re-verified against embedded raw citations); direct re-parse of `v2_2026-08-16_*` event arrays was not repeated in this lane.

---

## 9. Raw evidence appendix (verbatim anchors)

E37 (`comfymodal-data\benchmarks\runs\v2_2026-08-21_22-35-45\run_001_sample.json` unless noted):
- `clip_qd_source_submit_start` mono 217557211917 (L137–138); metadata qd=4, block_bytes 33554432, n_ranges 240, file_bytes 8044936192, preadv, launch_policy clean_lane_post_restore (L127–136)
- `clip_qd_source_first_completion` latency_ms 9.9985 (L167–171); `clip_qd_source_last_completion` latency 1033.5153, wall 1043.5138 (L183–188); `clip_qd_source_submit_end` wall 1043.5138 (L200–204)
- `clip_qd_copy_to_device_end` h2d_device 27.3155, host_issue_total 127.39898799983962 (L216–221); `clip_qd_stats` 240/240, bytes 8044936192, aggregate 7.7095 GB/s (L233–249)
- `clip_qd_device_ready` wall_ms 1052.5283 mono 218637617228 (L261–267; trace-array twin 218637607918 L16016–16017)
- `clip_qd_owner_created` gpu_bytes 8044936192 tensor_count 398 (L279–285); source_side take/bind/owner_retained (L306–358); demand_side take/bind/owner_retained (L360–417)
- Clean-lane proof: ordering qd_start 217556019937 / qd_ready 218637635118 / restore_return 217042924663 / plan_identity_complete 217125351191; forbidden_overlap=[] ; quiescence all-true; reconciliation_240_240 (L16024–16219); forbidden_activity_attempts ×5 (L16029–16052)
- `clip_bind_wait_start/end` wait_ms 0.142 success (L16447–16483); `clip_device_ready` loader_arm=qd_demand mono 218685180002 (L16486–16512); `clean_lane_bind` (L16514–16532)
- `clip_fh_bind_residency_proof` state INVALID/PARTIAL params cpu1/cuda398/meta0 (L16534–16564)
- `clip_fh_hydration_start/end`: mode fastsafetensors_direct_gpu label, bind_wall 45.724, file_to_gpu_wall_ms 1085.319, wall_ms 1144.902, gbps 6.903, rss_delta −7045.906 MB, zero_copy 398/398, fallback_count 0, canonical.loader_interval start 217540276720 → ready 218685180002 = 1144.903 (L16566–16657)
- Ledger spans: “CLIP hydration” s15 217540345940→218690303521 dur/residual 1149.953 (L649–656, L1152–1178); “CLIP forward” s17 1110.221 (L665–672, L1206–1231); model-mgmt 0.803 (L657–664)
- OB8-F derivation: `run_0.json` submit_start 217557183787 → device_ready 218637607918 = 1,080,424,131 ns (OB8 §2.F)
- `summary.json`: restore_total_ms 303.653; GCP/us-south1; image im-QypPckt7SwaTFzJSG8AgXs; request_count 1 (L68–76, L172)

Request-FastSafe runs (`clip_fast_load_end` blocks):
- `v2_2026-08-24_21-37-12\run_001_sample.json` L7258–7346: adoption_mode same_storage_assign, non_same_storage_count 0, checkpoint BF16 398, cuda_allocated_before 0, fastsafe_setup 8.987, fastsafe_copy 1448.965, get_tensor_loop 0.211, descriptor 18.756, construction/bind 255.707, load_sd 0.0, file_to_gpu 1566.653, owner_retained true, release_point on_detach_after, expected bf16 via same_dtype_residency_override; `clip_fastsafe_residency_register` wall 40.799 (L7248–7256)
- `v2_2026-08-24_21-38-23` L7278–7305: copy 2369.602, file_to_gpu 2433.15, construction 310.889, descriptor 29.184
- `v2_2026-08-24_21-39-59` L7278–7305: copy 2226.318, file_to_gpu 2283.353, construction 295.955
- `v2_2026-08-25_02-55-12` L7284–7311: copy 1366.646, file_to_gpu 1497.197, construction 368.265
- `v2_2026-08-25_16-04-15` L7285–7312: copy 26295.783, file_to_gpu 26390.147, construction 384.932
- O3 F026 (RAW/NARRATIVE_MIXED): K4 copy 1359.126/setup 7.318/file_to_gpu 1429.867/fast_load total 1967.930 incl bind 396.53 (r42 K4 report :106); R44E 1934.712 (:204); J1 1517.928/1366.646 (cohort log :105,:793)
- Module structure: `request_clip_fastsafe.py` transport call L2433–2435 wraps ONLY `_fastsafe_load`; telemetry L2690–2760; `_register_residency` L1703–1780; **zero `synchronize()`/event-wait sites module-wide (grep)**

D12/E26/Native anchors as cited in §4.2/§4.4/§4.5 (report line numbers against named raw run dirs; E26 raw dirs absent).

Code verification anchors (current worktree): wiring L1319–1442 (clean-lane QD demand + quiescence gate + take/bind events), L1689–1737 (scoped event or global sync around bind), L1746–1774 (endpoint + loader_interval), L800–842 (`_fastsafe_load`), L2051+/L2174+ (fallback tails); cfh L1440–1531 (proof + bind); speculative L924/L944 (join/take), daemon threads L557/L1209/L1333.

---

## 10. Exact code/body hashes

Whole-file sha256 (computed this lane, worktree @0c59f46 dirty):
```
719d7de9c3edf12da8125b1cadb47da2389b604ce3aa3e845e2f61e92b4e55c3  comfymodal_runtime/clip_qd_reader.py   (== OB2's worktree hash; sole delta vs E37 commit 2f2d3f63…fa99 = +15-line uncommitted observation block, no semantic change)
4285c5a25fce5726bfeb26df036a850ae29db6d8ae07024dd2fad9fd1fdb0abd  comfymodal_runtime/clip_fast_hydration_wiring.py
9cd49dc9595e520a91f052452e903ca095837cc7f9352c723f24fb811d6c4b7e  comfymodal_runtime/clip_fast_hydration.py
67d758be9e2b1ad6043f42001a15aa8167508040c908b8c10bf63a5bd75658e2  comfymodal_runtime/speculative_clip_hydration.py
6d0e4c858f8c0bbdeeb2bf6df8b56d7fd1148f3b15ef9b1062ec986ebfaa4e64  comfymodal_runtime/clean_lane.py
a8a93bb47077c4a5ea5d8d4dc5eea0397d95381ce8e13e0a3a0962ed15918687  E37_CLEAN_LANE_ALGORITHM_RECOVERY_REPORT.md
```

Symbol body sha256 (O6_WORKTREE_NOW_FUNCTION_HASHES.csv, full values):
```
clip_qd_load                e6a4e4e1e3fa498081b6535bbf4bb8a0fb3d6a59176713d256636730aac71db5  (50 lines; == E37-era norm/raw per OB2 §5)
_try_fast_hydrate           23cf9643f017da819fa065d3fd654753bb9bfcb6ae5cebead9b27e1da1d69791  (843 lines)
hydrate_clip_bind           cb88796251c27cb46d647ba0c1a4f1348ed870943bb264b871e68fb379e1e5a3  (56 lines)
_zero_copy_evidence_clip    38b47114b5e3d371d1a9dbf09fc3c2b8fb77f840de6052068f1563e67d29bddb  (34 lines)
mark_bind                   0af5416eee07f9f1e08252453b419a090bd639b92ea3a12b3d88e2cfe86873ca
join_speculative_clip_lane  a35b5e584d65e9fcb296fd19d2912f7607b2646689cd20ee0f823a3c1f06075f
start_restore_time_clip_lane e8d8bcb620f6b9f13070337073994dfb49d187beccd848930aeb1bfc1305a5ef
_fastsafe_load              d6a240d4df575ebb3fe11a0ffb7c3a98d814425763a5d2619daa0be0fb54efe7
```
E37-checkpoint symbol hashes (OB2 §5, raw/norm prefixes; worktree IDENTICAL_RAW): `read_file_qd_gpu` ff1eacaf0d90ed55 / 4eb6f039c4d363b2 (284 lines), `_static_gpu_worker` e47128d16eaa3eb5, `QdGpuOwner` d857fe4ec9f92968, `_QdLoaderFacade` 5101919019248c4c, `parse_safetensors_header` 0df361d01e7eb96f, `plan_raw_source_regions` 3f9306348933423e.
Historical file identities: `clip_qd_reader.py @36b895d` == `@0c59f46` == `2f2d3f63e79f3cf0982ba6a0214471332e3e927a4420b55f31ea64209b76fa99`; `golden/qd_engine.py @2187c5e` 0ec5b34b0ed56837…, `@9a428fd` a4dbbf28de48f629… (rejected-evidence lineage).
Modern-path module: `..\comfyui-modal-r42\comfymodal_runtime\request_clip_fastsafe.py` — 3013 lines; exists ONLY in sibling lane (absent from HEAD tree); per-function hashes for it are NOT in O6 worktree CSV (file not part of repo-A worktree) — identity anchored by path+line reads this lane.

STOP — audit complete. No recommendation expressed; no architecture opinion; no stage selected.
