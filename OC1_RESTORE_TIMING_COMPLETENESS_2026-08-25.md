# OC1 — Batch Restore-Candidate Timing-Completeness Audit (2026-08-25)

READ-ONLY EVIDENCE AUDIT. No deploy. No paid Modal runs. No source changes. No winner selected. No architecture recommendation. No implementation recommendation.

Audit scope: for every credible Restore candidate established by the strongest available prior evidence, determine whether each historical timing is (a) the TOTAL wall for that candidate fulfilling the serialized Golden-part contract, (b) only a PARTIAL interval, (c) an interval containing external/unowned blocking or unrelated work, or (d) UNKNOWN. Raw span names were granted zero semantic authority; every boundary below was re-derived from executed-source reading plus raw runtime artifacts.

---

## 1. Evidence inventory

### 1.1 Canonical Phase-O / OB documents named by the brief — **ABSENT**

The following files were searched for by exact name, case-insensitive filename pattern, and content grep across this repository, the sibling deployment lanes, `AI HUB`, `.opencode`, and `.config/opencode`:

- `COMFYUI_MODAL_V2_GOLDEN_PIPELINE_SOT_PHASE_O_RECONCILED_V2.md` — NOT FOUND
- `COMFYUI_MODAL_V2_PHASE_O_REVALIDATION_AMENDMENT_V2_1.md` — NOT FOUND
- `PHASE_O_EVIDENCE_RECONCILIATION_2026-08-25.md` — NOT FOUND
- `PHASE_O_SOT_CHALLENGE_LEDGER_2026-08-25.csv` — NOT FOUND
- Any `O2 / O6 / O7 / O8` outputs — NOT FOUND
- Any `OB1 / OB7 / OB8` outputs — NOT FOUND
- The label **`RESTORE-C5`** appears nowhere in any `.md`/`.csv` in the repository — NOT FOUND

Consequence per the brief's precedence rules: every proposition that would have rested on those documents is carried as **UNKNOWN or REPORT_ONLY** here unless an independent raw artifact or exact source re-establishes it. The candidate set was reconstructed directly from raw artifacts and deployment manifests instead (Section 2). This absence is itself recorded as evidence gap G-1 (Section 8).

### 1.2 Evidence actually used (strongest-first)

| # | Artifact | Role |
|---|---|---|
| E-01 | `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md` (2026-08-25 02:08) | Locator + experiment record for K1; exact before/after hunks, hashes, deploy/run IDs |
| E-02 | Raw run artifacts `ComfyUI\comfymodal-data\benchmarks\runs\v2_*\run_001_sample.json` (+ `run_0.json`, `summary.json`) | **Primary raw telemetry** for all 11 audited runs |
| E-03 | Run manifests `comfyui-modal-r42\.v2ctl\runs\run_*.json` | Bind request_id ↔ artifact path ↔ deploy_fingerprint ↔ profile ↔ git head |
| E-04 | Deploy manifests `comfyui-modal-r42\.v2ctl\deployments\deploy_{20260823-154303_02ab046e, 20260824-211747_32d41196, 20260825-015120_34686e38}.json` | Per-deploy dirty source hashes, git head, profile, resources |
| E-05 | Gate record `comfyui-modal-r42\.v2ctl\gates\gate_20260825-065726_44c49708.json` (`"gate_valid": true`) | Snapshot-HIT/NOMINAL gate corroboration |
| E-06 | Executed-source reconstruction: `comfymodal_runtime/modal_app.py` (orchestration checkout), `comfymodal_runtime/runtime_bootstrap.py` | Restore/startup lifecycle boundaries, emitter sites |
| E-07 | `V2_BATCH_E29_GROUND_TRUTH_CRITICAL_PATH_AND_RESTORE_MAP.md` | Locator for E29 ledger-span semantics (older era, REPORT_ONLY where uncited by raw artifacts) |
| E-08 | `E39_COMFYAPP_GOLDEN_PATH_PRUNING_REPORT.md`, `E40_CANONICAL_RUNTIME_TRUTH_AND_CLEANUP_REPORT.md`, `R41_DETERMINISTIC_GOLDEN_QD4_PIPELINE_REPORT.md`, `R44F_CLIP_ZERO_COPY_ADOPTION_REPORT.md` | Context locators only |
| E-09 | `.v2ctl/k1_manifest/*` (sha256_before.txt etc., referenced by K1 report §1) | Referenced locator; not independently re-opened byte-for-byte except where stated |

Precedence applied: raw artifacts (E-02/E-03/E-04/E-05) > executed-source reconstruction (E-06) > experiment reports (E-01) > narrative locators (E-07/E-08). No historical deploy was assumed identical to any checkout HEAD; per-deploy dirty hashes are quoted in Section 10 and none was proven byte-identical to any present worktree.

---

## 2. Candidate list and candidate-inclusion justification

### C-R43 — "R43 healthy restore class" (golden-lineage internal reference)
- **Included.** Concrete historical execution proven by raw artifacts: 6 runs owned `R43` under deploys `7417db68…` (n=1) and `02ab046e…` (n=5), profile `r43-known-fast`, branch `r42-golden-reconciliation`, HEAD `0c59f46e…` (the golden-lineage prune commit). Gate-class status NOMINAL on 5/6 (one DEGRADED draw disclosed below). Plausibly satisfies the serialized contract (did so historically: snapshot HIT era, zero-fallback NOMINAL draws, golden output SHA lineage).

### C-PREK1 — "pre-K1 / current-bad" reference (J1-dirty r42 lane)
- **Included as boundary reference.** Deploy `32d41196…`, owner `r44j1`, HEAD `6040c459…` + J1 dirty (`modal_app.py` dirty-hash `7d497ba7…`). One raw reference run (`v2_2026-08-25_02-55-12`). Defines the regression boundary that K1 removes.

### C-K1 — quiescence-seam removal on the J1 lane
- **Included.** One deployment `34686e38…`, owner `k1-quiescence-seam`, same HEAD `6040c459…` + K1 hunk (`modal_app.py` dirty-hash `3276ec4d…`). Four raw runs observed against this deploy: the report's 3-run cohort PLUS one additional R44B-owned pathological run (`v2_2026-08-25_06-55-04`, `restore_total_ms=3556.692`) that the K1 report does not mention (see §5/T-31 and gap G-4).

### Candidates considered and REJECTED
- Older restore eras (Aug-06 "consistent 11–13.5 s", Aug-11/12 `restore_only_*`, slim_ab lanes): dead/superseded implementations; several predate the E29 ledger, so their boundaries are not reconstructible at equal fidelity; the brief forbids expansion into every dead implementation. Excluded.
- `RESTORE-C5`: unverifiable label (G-1). Not included.
- **No new candidate added**: repository search found no further implementation with concrete evidence of (a) historical execution AND (b) plausible ability to satisfy the serialized Golden Restore contract that is not one of the above.

---

## 3. Derived serialized Golden Restore contract (from code, not metric names)

**Registration (executed source, orchestration checkout `comfymodal_runtime/modal_app.py`, SHA256 `55722c89…`):**

```python
# modal_app.py:20200-20209
setattr(cls, "startup", _modal.enter(snap=_resolve_enable_memory_snapshot())(cls.startup))
setattr(cls, "restore", _modal.enter(snap=False)(cls.restore))
...
setattr(cls, "run_plan_stream", _modal.method(is_generator=True)(cls.run_plan_stream))
```

`restore()` is a **Modal enter-lifecycle method** (`snap=False`); `run_plan_stream` is a Modal method. Modal guarantees the enter method completes before any request method can be invoked on the container. With `COMFYMODAL_V2_SINGLE_USE_CONTAINERS=1` (all audited profiles), every request is preceded by exactly one full `restore()` execution. Therefore the *serialized Golden Restore part* is: **one synchronous `restore()` execution per container, from Modal container start until `restore()` returns its result dict, after which the next Golden part (request execution) may begin.**

Exact contract terms derived from source order:

- **Entry condition:** Modal resumes the process from the memory snapshot (or boots it) and invokes `restore()`. First executable line stamps `remote_python_resume_wall_ns/mono_ns` (`modal_app.py:10139-10141`) and ledger event `modal_restore_entry`.
- **Return/completion condition:** success path returns `_restore_result` dict with `status="restored"`, `backend`, `cuda`, `runtime_generation`, trace, `_restore_timing` (`modal_app.py:12050-12234`); ledger event `modal_restore_exit`; `set_restore_return_marker(...)` before return.
- **Runtime/model-generation obligations inside:** bootstrap stages — `restore_gpu_state`, CUDA context init (`initialize_cuda`), Sage identity verify-or-full-discovery, runtime-state Volume reload **or** fail-closed skip on generation match, models Volume reload **or** fail-closed skip, custom-node identity check-or-sync, generation observe, snapshot execution-seed hydration (`runtime_bootstrap.py:1942-2554`).
- **Required reload/reconciliation:** conditional; on all 11 audited runs both reloads were skipped (`reload_models_ms=0.0`, `reload_runtime_state_ms=0.0`, decisions `skipped_generation_match`/not_invoked) — reconciliation obligation was satisfied by O(1) local generation checks, not network reloads.
- **Worker/cache/future state required at return:** torch intraop/interop thread policy applied; conditioning-cache worker state and prefetch executors must be in the shape captured by the snapshot (this is exactly the state K1's removed proof used to mutate); cgroup sampler and advisory folder-warm daemon threads are *started* during restore and legitimately continue past return (advisory, off-contract).
- **Model/snapshot ownership state at return:** models are NOT guaranteed GPU-resident. `COMFYMODAL_V2_CLIP_QD_LAUNCH_POLICY=clean_lane_post_restore`, `REQUEST_FASTSAFE=1`, `UNET_EARLY_SOURCE_PREP=1` place model source-read/H2D transport deliberately AFTER the restore boundary (request part owns them). Restore promises lifecycle/bootstrap readiness, not model residency.
- **Legitimately pending at return (restore-owned debt allowed by design):** advisory folder-listing warm thread completion; cgroup sampler lifetime; (when flagged) the E37 speculative CLIP lane launched at the exit boundary — flag OFF in all audited profiles (`SPECULATIVE_CLIP_HYDRATION=0`), so not exercised here.

**Three non-coincident timing domains (per brief):**
- **A. Platform banner → first Python:** submission/command start → `remote_python_resume`. Owned by Modal platform (provisioning, scheduling, snapshot materialization mechanics). Never inside `restore_total_ms`.
- **B. Python restore callback/runtime work:** first Python line → `restore()` return. Contains the emitters of `restore_total_ms` and all nested stage timers.
- **C. Snapshot composition/capture preconditions:** everything frozen into the snapshot at build time (capture-side `startup(snap=True)` callback incl. the post-R43 unconditional quiescence proof). Paid at domain A/B boundary mechanics and materialized as *state* inside domain B; not a time interval inside B's timers, but a determinant of them (snapshot age, mutated cache state).

---

## 4. Candidate-specific execution narratives

### 4.1 Current canonical restore path (shared skeleton for C-PREK1 and C-K1; R43-era equivalent verified via identical ledger spans)

Exact source order in `modal_app.py::restore()` (line numbers from checkout SHA `55722c89…`):

1. `:10139` resume stamps + ledger `modal_restore_entry` (**domain-B true start**).
2. `:10205-10258` gantt point spans (flag-gated), snapshot-manifest hook (default OFF).
3. `:10273-10297` `post_snapshot_restore` stage open; snapshot-callback-age computation (cross-process marker check).
4. `:10299-10340` `restore:early` span closes; eviction-boundary inspection + idle policy (`EVICT_RESTORE_IDLE_SECONDS=0` here ⇒ no sleep); `lazy_init_snapshot_state`; `restore:eviction` closes, `restore:snapshot` opens.
5. `:10341-10407` frozen-manifest availability marker; CLIP fast-hydration demand install attempt; production snapshot invariant.
6. `:10409-10456` full-trace session setup (OFF on measured runs); **`_restore_perf_start = time.perf_counter()`** ← start of `restore_total_ms`. Everything in steps 1–5 is EXCLUDED from `restore_total_ms`.
7. `:10464-10512` residency print, cgroup sampler start, host-memory probe, request-count/stage-timer resets, identity capture, `_configure_runtime()`, RuntimeTrace creation, advisory folder-warm daemon launch, clean-lane begin_request.
8. `:10710-10751` ledger `bootstrap_restore_start`; `restore:preamble` closes; `state = self.bootstrap.restore(trace)` (`runtime_bootstrap.py:1942`): metadata capture → `restore_gpu_state()` → CUDA init → Sage verify/skip → runtime-state reload decision (skip on match) → models reload decision (skip on match) → prescan/custom-node identity check → seed hydration → host fingerprint → `snapshot_restore_end`; stage durations merged into `state.stage_durations`.
9. `:10758-10781` `[v2.generation_identity]` diagnostic print.
10. `:11798-11906`(region) preload-bridge prep; `restore:preload` span; `restore:finalize` opens.
11. `:11998-12035` ledger `modal_restore_exit`; (flag-gated) speculative CLIP lane launch — OFF here.
12. `:11910-12048` `_do_restore_finalization()` computes **`restore_total_ms`** (= `perf_counter − _restore_perf_start`), merges `state.stage_durations` + `_RESTORE_STAGE_TIMERS` (`reload_runtime_state`, `reload_models`, `restore_gpu_state`, `initialize_cuda`, `snapshot_identity_checks`, `cpu_snapshot_retargeting`) into `_restore_timing`.
13. `:12063-12234` breakdown/deep prints, `[v2.restoration_identity]` + `[v2.lifecycle] … status=restored` prints, host-memory report, full-trace milestone, GPU allocation detect, `v2_restore_return`, `set_restore_return_marker`, **return**. Steps after the §12 stamp are INSIDE the method but OUTSIDE `restore_total_ms`.

**Emitter identities (exact):** `restore_total_ms` ← `modal_app.py:11923-11926` (success) / `:10787` (error); printed at `:12167/:12181`; surfaced host-side as `critical_path_metrics.restore_total_ms`. `snapshot_restore_ms` ← duration between trace events `snapshot_restore_start`(`runtime_bootstrap.py:2007`)/`snapshot_restore_end`(`:2478`), i.e., the whole bootstrap body. `restore_gpu_state_ms`/`cuda_init_ms` ← `variance_stage` brackets `:2032`/`:2052`. Host delta `command_start_to_restore_end` etc. derived in the benchmark harness from ledger endpoints (`wall_clock_trace_v3.py:566` maps `restore_total_ms` to `t_restore_start/t_restore_end`).

### 4.2 C-R43 specifics
Same skeleton (ledger spans `restore:early/eviction/snapshot/preamble/bootstrap/preload/finalize` present with identical names/durations-order in `v2_2026-08-23_20-55-38`), deployed from golden-lineage HEAD `0c59f46…` where the capture-side startup callback contains **no** `prove_snapshot_quiescence()` call (K1 report §2, confirmed by `git log -S` cited there; consistent with raw `snapshot_quiescence` object being absent-by-design rather than proven in R43-era artifacts — not directly re-verified here, see G-5). Profile `r43-known-fast`.

### 4.3 C-PREK1 specifics
Identical to 4.1 plus the **capture-side** (domain C) mutation: `startup(snap=True)` ends with the unconditional block (quoted verbatim in §9-A2) calling `prove_snapshot_quiescence()` which sets cache-quiescing instance state, joins/drains persistence, and forces cache-worker teardown — effects serialized INTO the snapshot and paid during every materialization (K1 report §2; mechanism-level, source-proven). Raw corroboration in the reference run artifact: the serialized `snapshot_quiescence` object (`proven: true`, checks incl. `joined_workers: 0`, `"conditioning cache was never initialized or is disabled"`) travels in `_restore_timing` (§9-A4). Its ledger shows `restore:preamble = 919.032 ms` vs 23 ms on healthy classes — the interior composition of that preamble is NOT attributed by any span (G-3).

### 4.4 C-K1 specifics
Byte-level change limited to removing the §4.3 capture-side block and defining `_snapshot_quiescence = None` (hunk in §9-A3), plus mirrored test flip. Restore-side skeleton unchanged. Deploy `34686e38…` resources 12 CPU / 32768 MB / RTX-PRO-6000, image `im-GIMsC0WZNtcZBSrLjGaaKK`, selector `E37_CLEAN_LANE_VALIDATION`, expected output SHA `20b10e1f…e5260` matched on all cohort runs.

---

## 5. Timing-by-timing completeness audit

Classification enums per brief. `MOC` = MEASURED_OPERATION_COMPLETENESS; `GPC` = GOLDEN_PART_COMPLETENESS relative to the Section-3 contract; `CONT` = CONTAMINATION. Full per-run numbers live in `OC1_RESTORE_TIMING_CLAIMS_2026-08-25.csv` (one row per claim); representative values inline below are raw-artifact values.

### T-1 `critical_path_metrics.restore_total_ms` (all candidates)
- Start: `_restore_perf_start` (`modal_app.py:10456`). End: stamp inside `_do_restore_finalization` (`:11923-11926`).
- **Excludes (proven):** (i) resume→perf-start segment — ledger `restore:early+eviction+snapshot` (≈8–17 ms) plus the unattributed front part of `restore:preamble`; (ii) final-stamp→method-return tail (marker set, prints, host report, GPU detect) — independently visible because host wall `command_start_to_restore_end − command_start_to_python_resume` exceeds `restore_total_ms` by **+57.1 to +296.9 ms across all 11 runs** (e.g. ref: 1735.619 vs 1670.909; K1 r1: 356.023 vs 300.133); (iii) domain A entirely.
- **Includes (proven):** bootstrap body (incl. any invoked Volume reloads — none invoked here), CUDA init, identity/config, finalize; plus launches (not completions) of cgroup-sampler and folder-warm background work.
- **Nested:** yes — `snapshot_restore_ms`, `restore_gpu_state_ms`, `cuda_init_ms`, reload timers are strict children.
- **Waiting:** no explicit sleep/retry/poll exists on the measured path (`EVICT_RESTORE_IDLE_SECONDS=0`; no gc.collect inside restore — `runtime_bootstrap.py:1964-1967`). `cuda_init` time is spent inside driver/platform context creation: contractual (owned dependency), cause of long draws unidentified (G-2).
- MOC **PARTIAL_FOR_MEASURED_OPERATION** (name says total; boundaries provably narrower than "all restore-owned Python"). GPC **PARTIAL** (domain A excluded by definition; resume-side front and return tail excluded by code). CONT **MIXED** — observability/advisory components inside (cgroup sampler start, host-memory probes, folder-warm launch = UNRELATED_WORK components, individually ≤ms-scale); contractual external executor inside (CUDA driver init = owned dependency); on `v2_2026-08-25_06-55-04` additionally a 2350.56 ms `cuda_init` draw of unidentified producer (UNKNOWN cause, kept inside MIXED with flag).

### T-2 `snapshot_restore_ms`
- Brackets exactly `bootstrap.restore()` between trace events `snapshot_restore_start`/`snapshot_restore_end`. Strict child of T-1. Contains gpu-state/cuda/reloads/seed.
- MOC **TOTAL_FOR_MEASURED_OPERATION**. GPC **PARTIAL**. CONT **NONE_PROVEN** on healthy draws; **MIXED** on `06-55-04` (contains the cuda_init draw).

### T-3 `restore_gpu_state_ms`; T-4 `cuda_init_ms`; T-5 `reload_runtime_state_ms` / `reload_models_ms` (both 0.0 on all runs); T-6 `initialize_cuda_ms` (second, distinct emitter)
- Leaf/nested children. MOC **TOTAL_FOR_MEASURED_OPERATION** each. GPC **PARTIAL**. CONT NONE_PROVEN except T-4 on `06-55-04`: value real, ownership of the wait contractual, producer UNKNOWN → CONT **UNKNOWN** for that row.
- Note: `cuda_init_ms` (variance_stage bracket) and `initialize_cuda_ms` (stage timer) coexist and differ slightly (ref: 3.46 vs 3.302) — two emitters, same operation, do not sum.

### T-7 Ledger spans `restore:early/eviction/snapshot/preamble/bootstrap/preload/finalize` (E29 axis)
- Tile [resume → exit] with mono stamps at exact code sites. Sum vs host wall leaves ≈52–56 ms unspanned return tail (ref: spans Σ=1679.371 vs wall 1735.619).
- MOC **TOTAL_FOR_MEASURED_OPERATION** (each brackets its named window). GPC **PARTIAL** (still excludes domain A). CONT **NONE_PROVEN** generally; `restore:preamble` on the reference run = **919.032 ms with zero interior attribution** → interior composition UNKNOWN (CONT **UNKNOWN** for that single row; G-3).

### T-8 `cpm.remote_python_resume_to_restore_start_ms` (0.0 everywhere)
- Host-derived equality of two ledger points. TOTAL by construction but semantically misleading if read as "restore starts at resume": the remote timer provably starts later (T-1 exclusions). Flagged, not classified as a defect of the underlying events.

### T-9 `cpm.restore_to_method_entry_ms` (25.864–160.147 across runs)
- Seam between restore return and `run_plan_stream` method entry. Belongs to NEITHER part's timer today. MOC TOTAL (brackets exactly the seam). GPC **UNKNOWN-ownership seam cost — counted here as REQUIRED_WORK_OUTSIDE_MEASURED_INTERVAL for every candidate**. CONT **EXTERNAL_BLOCKING** (Modal method dispatch/platform, unowned by restore code).

### T-10 `cpm.command_start_to_python_resume_ms` / `submission_to_remote_python_resume_ms` (domain A)
- Platform provisioning/scheduling/snapshot-materialization wait. MOC TOTAL. GPC PARTIAL (it is outside the restore part proper but inside end-to-end). CONT **EXTERNAL_BLOCKING** (platform-owned). Anomaly: K1 r1 = **149226.783 ms** — first run immediately after deploy (cold provisioning); unrelated to restore-code work.

### T-11 `cpm.first_remote_event_to_final_result_ms`; T-12 `method_entry_to_first_remote_event_ms`; T-13 `submission_to_first_remote_event_ms`
- Request-execution-domain metrics crossing the restore boundary. MOC TOTAL/PARTIAL as bracketed; CONT MIXED (multi-owner). Used ONLY for cross-era context; never added to restore intervals (no naive arithmetic).

### T-14 `snapshot_callback_age_at_restore_ms` (state metric, not interval)
- 13.1 s (K1 r1, fresh snapshot) → 1818 s (reference). Proves **snapshot-age state debt** differs systematically across candidates/eras and confounds naive cross-era comparison (carried as candidate state debt, per brief).

### Pathological-draw question (brief)
- K1 `restore_total` long draws: the only observed >1 s draw on deploy `34686e38…` is `06-55-04` (3556.692 ms) with `cuda_init_ms=2350.56` inside. Is Restore actively working? No candidate-owned loop/wait exists on the path (source-proven). Blocking on an owned dependency (driver/GPU allocator)? Possible. External platform interference? Unidentified. Verdict: **UNKNOWN** (G-2). Same pattern exists inside the R43 class (`20-44-03`: cuda_init 630.84 → restore 1513.022; `20-08-03` DEGRADED 912.21 with cuda_init 156.07) — long internal-restore draws are NOT unique to any candidate.

### K1-specific questions (brief)
- Does K1 `restore_total_ms` encompass all work the proposed GoldenRestore part must perform before returning? **No** (T-1 exclusions i–iii).
- Required reload/cache/runtime reconciliation before timer start or after end? Before: eviction/lazy-init/frozen-manifest/CLIP-demand-install occur pre-perf-start. After: return-tail work + seam T-9 + request-side transport lanes (owned by next part by design). None of these is hidden *inside* the name.
- Sleeps/retries/waits inside it candidate-owned? No sleeps exist on the measured path; waits inside bootstrap are contractual callbacks (none invoked here).
- Does R43 measure the same semantic boundary as K1? **Yes for T-1..T-7** (identical emitter code lineage; identical ledger span set verified in raw R43 artifacts), **with unequal snapshot-age state debt** (T-14) and unequal capture-side state (domain C) — comparable as *boundary-equivalent*, not as *state-equivalent*.

### Internal-restore vs Modal banner→Python comparability
Domain A (T-10) and domain B (T-1) share only endpoint events (`command_start`, `remote_python_resume`). Only endpoint-difference arithmetic on the shared wall axis is legal; summing A+B assumes serialization that the `06-51-50` anomaly (A=149 s with normal B=300 ms) proves fragile. UI/banner→Python and internal restore must not be averaged together.

---

## 6. Cross-era boundary-equivalence matrix

Legend: ✅ equivalent emitter semantics proven from raw artifacts/source; ⚠️ same names, unproven interior; ❌ not comparable.

| Boundary / metric | C-R43 (deploys 7417db68/02ab046e) | C-PREK1 (32d41196) | C-K1 (34686e38) |
|---|---|---|---|
| Domain-A endpoints (cmd_start→resume) | ✅ | ✅ | ✅ |
| `remote_python_resume` first-line stamp | ✅ ledger spans present | ✅ | ✅ |
| `restore_total_ms` start/end sites | ✅ same code lineage | ✅ | ✅ |
| Ledger RESTORE span set (7 spans) | ✅ verified in raw | ✅ | ✅ |
| Nested stage timers (snapshot_restore/gpu/cuda) | ✅ | ✅ | ✅ |
| Capture-side snapshot state (domain C) | no quiescence proof (source-level, G-5) | proof ON (raw object in artifact) | proof removed (raw hunk) |
| Snapshot age at restore | 192–946 s | 1818 s | 13 s–791 s |
| Pre-E29 eras (Aug≤12) | ❌ (no ledger) | ❌ | ❌ |
| Modal UI/banner wall | ❌ unknown all candidates (USER_UI_REQUIRED, K1 §8.3) | ❌ | ❌ |

## 6.b Boundary-equivalence of the numbers themselves

resume→restore_end wall minus `restore_total_ms` (positive gap = work outside the timer):

| Run | wall(resume→restore_end), ms | restore_total_ms | gap, ms |
|---|---|---|---|
| R43 20-08-03 | 1005.869 | 912.210 | +93.659 |
| R43 20-44-03 | 1809.907 | 1513.022 | +296.885 |
| R43 20-53-40 | 852.222 | 696.779 | +155.443 |
| R43 20-54-39 | 451.050 | 393.936 | +57.114 |
| R43 20-55-38 | 318.484 | 257.681 | +60.803 |
| R43 20-56-38 | 341.597 | 275.388 | +66.209 |
| PREK1 02-55-12 | 1735.619 | 1670.909 | +64.710 |
| K1 06-51-50 | 356.023 | 300.133 | +55.890 |
| K1 06-55-04 | 3626.269 | 3556.692 | +69.577 |
| K1 07-00-09 | 776.760 | 680.098 | +96.662 |
| K1 07-01-28 | 541.590 | 480.695 | +60.895 |

The gap is systematic (never negative), confirming `restore_total_ms` is a strict sub-interval of the Golden-part window on every candidate.

---

## 7. Candidate result table

| Field | C-R43 | C-PREK1 | C-K1 |
|---|---|---|---|
| CAN_SATISFY_SERIAL_GOLDEN_RESTORE_CONTRACT | **YES** (historically did: NOMINAL zero-reload draws) | **YES** (functionally satisfied contract; slower; gate NOMINAL, reloads skipped) | **YES** on cohort evidence; worst-case clouded by unreported 3556.692 ms draw |
| HISTORICAL_TOTAL_TIMING_KNOWN | YES for internal restore (n=6 raw); NO for domain A/UI | YES internally (n=1 raw); NO elsewhere | YES internally (n=4 raw incl. non-cohort); NO elsewhere |
| BEST_PROVEN_TOTAL_TIMING | **257.681 ms** (`v2_2026-08-23_20-55-38`); observed range 257.681–1513.022 | **1670.909 ms** (single sample) | **300.133 ms** (`06-51-50`); observed range 300.133–3556.692 |
| BEST_PROVEN_PARTIAL_TIMINGS | snapshot_restore 227.100; gpu_state 188.055; cuda_init 3.300 (best-case run) | 743.630 / 553.853 / 3.460 | 269.040 / 230.321 / 4.990 (cohort-best run) |
| REQUIRED_PRECONDITION_STATE | snapshot HIT; generation-match skips; cert fast-path; custom-node+sage identity exact; frozen runtime baseline | same + quiesced/cache-worker-teardown capture state baked in snapshot | same as PREK1 minus quiescence-proof capture mutation |
| REQUIRED_WORK_OUTSIDE_MEASURED_INTERVAL | resume-side front (early/eviction/snapshot + partial preamble), return tail, seam T-9 (25.9–49.5 ms), request-side model transport lanes (by design) | same (seam 81.470 ms) | same (seam 76.493–160.147 ms) |
| UNOWNED_TIME_INSIDE_MEASURED_INTERVAL | observability/advisory components (sampler/probes/warm-launch), ms-scale; cuda_init driver time (owned dependency) | same + 919.032 ms unattributed `restore:preamble` interior (UNKNOWN) | same; +2350.56 ms cuda_init draw of UNKNOWN producer (non-cohort run) |
| VARIANCE_EVIDENCE | n=6: 257.681–1513.022 (5.9×); slow draws correlate with cuda_init | n=1 | n=4 observed: 300.133–3556.692 (11.8×); cohort-of-record median 480.695 |
| WHAT SERIAL VALIDATION MUST MEASURE | resume→perf-start front segment; restore_total; return tail; seam T-9; domain A separately; snapshot age as covariate; cuda_init tail distribution; folder-warm completion; UI/banner wall (currently USER_UI_REQUIRED) | identical list (if re-measured at all) | identical list |

No winner selected.

---

## 8. Unresolved evidence gaps

- **G-1:** All named Phase-O/OB outputs and the `RESTORE-C5` label are absent from the repository (§1.1). Anything exclusively established there remains UNKNOWN here.
- **G-2:** Producer of long `cuda_init` draws (2350.56 ms on `06-55-04`; 630.84 ms on R43 `20-44-03`) unidentified; active-work vs owned-blocking vs external interference = UNKNOWN.
- **G-3:** Interior composition of the reference run's 919.032 ms `restore:preamble` — no span/leaf attribution exists in the artifact; UNKNOWN.
- **G-4:** Run `v2_2026-08-25_06-55-04` (owner R44B, invocation `2af9b771…`) against the K1 deploy is absent from the K1 report's cohort; why it was excluded (different invocation; possibly another agent's run) is not recorded anywhere found.
- **G-5:** R43-era capture-side absence of `prove_snapshot_quiescence` rests on the K1 report's `git log -S` citation (REPORT_ONLY); the R43-era `modal_app.py@1a41ee00…` blob was not independently decompiled here.
- **G-6:** Modal UI/banner→Python restore wall: no programmatic artifact on ANY candidate (K1 §8.3 USER_UI_REQUIRED stands).
- **G-7:** Console-only emitters (`[v2.lifecycle]`, `[v2.restore_deep]` stdout lines) were not captured (`console_capture: null`); their values survive only via JSON fields — console lines are therefore REPORT_ONLY.
- **G-8:** Byte-identity between any deployed dirty tree and any current worktree is UNPROVEN; the r42 lane's present `modal_app.py` (SHA `855d5f61…`) already differs from the K1 deploy input (`3276ec4d…`) due to post-deploy drift by other agents.

---

## 9. Raw evidence appendix (verbatim)

Artifact root: `C:\Users\parla\OneDrive\Documents\AI HUB\ComfyUI June Install\ComfyUI\comfymodal-data\benchmarks\runs\`

### A1. critical_path_metrics blocks (from `run_001_sample.json` of each run; field-for-field verbatim)

```
# v2_2026-08-25_02-55-12  request_id=v2-benchmark-0-61b4e2bd9f9e provider=CLOUD_PROVIDER_GCP region=us-east1 runtime_status.status=NOMINAL deploy=32d4119609eca0cc…
"cpm.command_start_to_python_resume_ms = 10159.712
"cpm.command_start_to_restore_end_ms = 11895.331
"cpm.first_remote_event_to_final_result_ms = 14494.099
"cpm.method_entry_to_first_remote_event_ms = 647.979
"cpm.remote_python_resume_to_restore_start_ms = 0.0
"cpm.restore_to_method_entry_ms = 81.47
"cpm.restore_total_ms = 1670.909
"cpm.snapshot_callback_age_at_restore_ms = 1818349.95
"cpm.submission_to_first_remote_event_ms = 6513.431
"cpm.submission_to_remote_python_resume_ms = 4048.363
```

```
# v2_2026-08-25_06-51-50  request_id=v2-benchmark-0-8e43af5eed14 GCP/us-east1 NOMINAL deploy=34686e386040dece…
command_start_to_python_resume_ms = 149226.783 ; command_start_to_restore_end_ms = 149582.806
first_remote_event_to_final_result_ms = 14313.273 ; method_entry_to_first_remote_event_ms = 1409.284
remote_python_resume_to_restore_start_ms = 0.0 ; restore_to_method_entry_ms = 76.493
restore_total_ms = 300.133 ; snapshot_callback_age_at_restore_ms = 13075.476
submission_to_first_remote_event_ms = 145950.079 ; submission_to_remote_python_resume_ms = 144108.279
```

```
# v2_2026-08-25_06-55-04  request_id=v2-benchmark-0-e67bfdd3c6e1 AWS/eu-south-2 NOMINAL deploy=34686e38… owner(R44B, provenance json)=invocation 2af9b771406a47c2b6c46e0b2ba5bd26
command_start_to_python_resume_ms = 8468.788 ; command_start_to_restore_end_ms = 12095.057
first_remote_event_to_final_result_ms = 23323.957 ; method_entry_to_first_remote_event_ms = 1477.463
remote_python_resume_to_restore_start_ms = 0.0 ; restore_to_method_entry_ms = 153.345
restore_total_ms = 3556.692 ; snapshot_callback_age_at_restore_ms = 406634.847
submission_to_first_remote_event_ms = 9230.698 ; submission_to_remote_python_resume_ms = 3973.62
```

```
# v2_2026-08-25_07-00-09  request_id=v2-benchmark-0-0cd7501c769f AWS/us-east-2 NOMINAL deploy=34686e38…
command_start_to_python_resume_ms = 14792.069 ; command_start_to_restore_end_ms = 15568.829
first_remote_event_to_final_result_ms = 28619.637 ; method_entry_to_first_remote_event_ms = 2672.255
remote_python_resume_to_restore_start_ms = 0.0 ; restore_to_method_entry_ms = 84.927
restore_total_ms = 680.098 ; snapshot_callback_age_at_restore_ms = 717230.042
submission_to_first_remote_event_ms = 12828.471 ; submission_to_remote_python_resume_ms = 9294.53
```

```
# v2_2026-08-25_07-01-28  request_id=v2-benchmark-0-518c470f4b49 AWS/eu-south-2 NOMINAL deploy=34686e38…
command_start_to_python_resume_ms = 10330.244 ; command_start_to_restore_end_ms = 10871.834
first_remote_event_to_final_result_ms = 24280.114 ; method_entry_to_first_remote_event_ms = 1348.48
remote_python_resume_to_restore_start_ms = 0.0 ; restore_to_method_entry_ms = 160.147
restore_total_ms = 480.695 ; snapshot_callback_age_at_restore_ms = 791265.923
submission_to_first_remote_event_ms = 5926.841 ; submission_to_remote_python_resume_ms = 3876.623
```

```
# v2_2026-08-23_20-08-03 req=v2-benchmark-0-dace7f4ce71d AWS/us-east-2 status=DEGRADED deploy=7417db68f7dda739…
restore_total_ms=912.21 remote_python_resume_to_restore_start_ms=0.0 restore_to_method_entry_ms=30.845
first_remote_event_to_final_result_ms=21382.192 snapshot_age_ms=323002.936
command_start_to_python_resume_ms=15096.595 command_start_to_restore_end_ms=16102.464
submission_to_remote_python_resume_ms=5564.686 submission_to_first_remote_event_ms=6012.271
# v2_2026-08-23_20-44-03 req=v2-benchmark-0-d8923df1df3e AWS/us-east-2 NOMINAL deploy=02ab046e2777f53e…
restore_total_ms=1513.022 … restore_to_method_entry_ms=25.864 first_remote_event_to_final_result_ms=22541.517
snapshot_age_ms=192356.207 cmd2resume=23128.809 cmd2restoreend=24938.716 sub2resume=5123.347 sub2first=6342.195
# v2_2026-08-23_20-53-40 req=v2-benchmark-0-563fc90ea2cd … restore_total_ms=696.779 r2me=41.99 f2f=22199.923 age=768969.515 cmd2resume=11258.536 cmd2restoreend=12110.758
# v2_2026-08-23_20-54-39 req=v2-benchmark-0-e6d57f546156 … restore_total_ms=393.936 r2me=49.546 f2f=22523.639 age=826778.633 cmd2resume=9330.292 cmd2restoreend=9781.342
# v2_2026-08-23_20-55-38 req=v2-benchmark-0-572fc2022494 … restore_total_ms=257.681 r2me=35.337 f2f=21649.384 age=886187.664 cmd2resume=8839.478 cmd2restoreend=9157.962
# v2_2026-08-23_20-56-38 req=v2-benchmark-0-c94d01d64686 … restore_total_ms=275.388 r2me=32.811 f2f=21860.766 age=945924.487 cmd2resume=8925.524 cmd2restoreend=9267.121
```

### A2. Capture-side quiescence block present pre-K1 (source, r42 lane @ deploy 32d41196; quoted by K1 report from its lane, mirrored in orchestration checkout `modal_app.py:9801-9811`)

```python
# ── Snapshot quiescence proof (fail closed) ───────────────────────
# This is unconditional: the callback must not return a snapshot-ready
# state while conditioning-cache or registered executor work is live.
from .snapshot_capture_hygiene import prove_snapshot_quiescence
_snapshot_quiescence = prove_snapshot_quiescence()
_restore_timing["snapshot_quiescence"] = _snapshot_quiescence
if not _snapshot_quiescence.get("proven", False):
    raise RuntimeError(
        "snapshot capture quiescence could not be proven: "
        f"{_snapshot_quiescence}"
    )
```

### A3. K1 removal hunk (verbatim from `K1_GOLDEN_RESTORE_QUIESCENCE_SEAM_RECOVERY_REPORT.md` §3, manifest `r42_k1_seam_hunk.patch`) — REPORT_ONLY source-level

```diff
-        # ── Snapshot quiescence proof (fail closed) ───────────────────────
… (removed block identical to A2)
+        # ── Snapshot quiescence proof: absent (K1 golden-restore seam) ────
+        _snapshot_quiescence = None
```

### A4. Serialized quiescence object inside reference-run `_restore_timing` (`v2_2026-08-25_02-55-12\run_0.json`, excerpt verbatim)

```json
"snapshot_quiescence": {
    "proven": true,
    "checks": [
      { "name": "exact_clip_conditioning_cache", "quiesced": true, "joined_workers": 0,
        "pending_dropped": 0,
        "details": ["conditioning cache was never initialized or is disabled"] },
      { "name": "torch.utils._functools._prefetch_executor", "type": "ThreadPoolExecutor",
        "pending_work": 0, "proven": true, "observations": ["work_queue"] } ] },
"runtime_state_generation_baseline": "7630854e465e294902955634582fcb45",
...
"reload_runtime_state_invoked": false, "reload_runtime_state_reason": "not_invoked",
"reload_models_invoked": false, "reload_models_reason": "not_invoked",
"restore_gpu_state_invoked": true, "initialize_cuda_invoked": true,
```

### A5. Nested stage durations (`run_0.json`, verbatim fragments)

```
# v2_2026-08-25_02-55-12:  "snapshot_restore_ms": 743.63, "restore_gpu_state_ms": 553.853, "cuda_init_ms": 3.46, "initialize_cuda_ms": 3.302
# v2_2026-08-25_06-51-50:  "snapshot_restore_ms": 269.04, "restore_gpu_state_ms": 230.321, "cuda_init_ms": 4.99
# v2_2026-08-25_06-55-04:  "snapshot_restore_ms": 3517.37, "restore_gpu_state_ms": 241.949, "cuda_init_ms": 2350.56
# v2_2026-08-25_07-00-09:  "snapshot_restore_ms": 640.71, "restore_gpu_state_ms": 288.777, "cuda_init_ms": 8.09
# v2_2026-08-25_07-01-28:  "snapshot_restore_ms": 440.47, "restore_gpu_state_ms": 326.981, "cuda_init_ms": 5.12
# v2_2026-08-23_20-08-03:  "snapshot_restore_ms": 873.2,  "restore_gpu_state_ms": 249.324, "cuda_init_ms": 156.07
# v2_2026-08-23_20-44-03:  "snapshot_restore_ms": 1479.03,"restore_gpu_state_ms": 379.183, "cuda_init_ms": 630.84
# v2_2026-08-23_20-53-40:  "snapshot_restore_ms": 583.59, "restore_gpu_state_ms": 420.307, "cuda_init_ms": 5.07
# v2_2026-08-23_20-54-39:  "snapshot_restore_ms": 347.7,  "restore_gpu_state_ms": 241.22,  "cuda_init_ms": 11.5
# v2_2026-08-23_20-55-38:  "snapshot_restore_ms": 227.1,  "restore_gpu_state_ms": 188.055, "cuda_init_ms": 3.3
# v2_2026-08-23_20-56-38:  "snapshot_restore_ms": 240.42, "restore_gpu_state_ms": 195.757, "cuda_init_ms": 4.4
```

### A6. Canonical-ledger RESTORE spans (verbatim, from `run_001_sample.json → canonical_ledger.spans`)

```
# v2_2026-08-25_02-55-12
restore:early dur=7.539 | restore:eviction dur=1.285 | restore:snapshot dur=0.041
restore:preamble dur=919.032 | restore:bootstrap dur=743.837 | restore:preload dur=0.422 | restore:finalize dur=7.215
# v2_2026-08-25_06-51-50
restore:early dur=7.161 | restore:eviction dur=1.363 | restore:snapshot dur=0.039
restore:preamble dur=23.166 | restore:bootstrap dur=269.373 | restore:preload dur=0.413 | restore:finalize dur=6.951
# v2_2026-08-23_20-55-38
restore:early dur=6.658 | restore:eviction dur=1.906 | restore:snapshot dur=0.038
restore:preamble dur=23.087 | restore:bootstrap dur=227.372 | restore:preload dur=0.584 | restore:finalize dur=6.469
```

### A7. Gate + workload corroboration

```
..\comfyui-modal-r42\.v2ctl\gates\gate_20260825-065726_44c49708.json : "gate_valid": true ; "decision": "persistent_hit"
run manifests (.v2ctl\runs\run_20260825-015448/020113/020221_44c49708.json):
  deploy_fingerprint = 34686e386040dece80db6bde2eb7aad8b8b23535fdf1c05ee07b749d82106206
  workload.expected_output_sha = 20b10e1f99831bc758d9df82f43ce0beb1cbc636a740d11a29eb2bffe90e5260
  effective_environment: COMFYMODAL_MINIMAL_RESTORE=1, CLIP_QD_LAUNCH_POLICY=clean_lane_post_restore,
                         SPECULATIVE_CLIP_HYDRATION=0, EVICT_MODELS_BEFORE_SNAPSHOT=0, SINGLE_USE_CONTAINERS=1
```

### A8. Console-print emitters — REPORT_ONLY (console_capture null on all audited runs)

`[v2.lifecycle] method=restore snap=False … status=restored` and `[v2.restore_deep] … residual_ms=…` prints exist in source (`modal_app.py:12177-12189`, `:12122`) but their stdout was not captured in any audited artifact; values quoted in this audit come exclusively from the JSON fields above.

---

## 10. Exact files / symbols / hashes relied upon

Source symbols (read in orchestration checkout unless noted):
- `ModalRuntimeEntrypointV2.restore` — `comfymodal_runtime/modal_app.py:10132-12285` (emitters `:10456`, `:10787`, `:11923-11926`, prints `:12167/:12181`)
- `ModalRuntimeEntrypointV2.startup` (capture side, snap=True path incl. quiescence block) — `modal_app.py:9801-9811`, return `:9869-9910`
- Lifecycle registration — `modal_app.py:20200-20209`
- `BootstrapState.restore` — `comfymodal_runtime/runtime_bootstrap.py:1942-2563` (stages `:2024-2053`, `:2142-2263`, seed `:2396-2462`, durations merge `:2482-2500`)
- `prove_snapshot_quiescence` — `comfymodal_runtime/snapshot_capture_hygiene.py:211` + `clip_conditioning_cache.py:2499` (locations per K1 report §2; hygiene module read indirectly via report, marked accordingly)
- Waterfall mapping — `wall_clock_trace_v3.py:177-178, 528, 566-567`

SHA256 (computed this session, lowercase):
- orchestration `comfymodal_runtime/modal_app.py` = `55722c892d7331d24e98ecde02dd88ff5ab8a341452e602ac6fafeef227f8137`
- orchestration `comfymodal_runtime/runtime_bootstrap.py` = `c7235ece376467be7603af4f639e475e3ad638e7d51f08b64b05269cb3db254c`
- orchestration `wall_clock_trace_v3.py` = `7065c8eb9c59b8257f2d7ca655c2efb616938a5812d1ce0cfe1667229a5c372e`
- r42-lane `modal_app.py` CURRENT (post-K1-deploy drift; NOT the deployed bytes) = `855d5f61bf9a83f153af4cfb0544c40038a0744fb4034668a6ed40262009f8cf`

Deployed dirty-source hashes (from deployment manifests, `deploy_inputs.dirty_hashes`):
- R43 deploy `02ab046e…` (HEAD `0c59f46e…`): `modal_app.py=1a41ee00b203fe67d5ee992c1e5f2b331461a8a2`, `snapshot_capture_hygiene.py=54185feed0629f8ad2cbb54d858538e5b95a2986`, `clip_conditioning_cache.py=3c9d19f43ee78c4035395e83a72f115837eaeadc`, `config_authority.py=c95760c0560f4b891618b3a8910957b86bf772dd`
- PREK1 deploy `32d41196…` (HEAD `6040c459…`): `modal_app.py=7d497ba72c5f9650b1ea3e494edb018a648c292d`, `config_authority.py=2ab6f6b17aaed1c13cec0a27285e5b363c3d079f`
- K1 deploy `34686e38…` (HEAD `6040c459…`): `modal_app.py=3276ec4de23c40deddb0532b71e2cd4ff6e7b37e`, `config_authority.py=2ab6f6b17aaed1c13cec0a27285e5b363c3d079f`

Run fingerprints: K1 cohort runs `run_fingerprint=44c497080deb855136c9958da8910afd864216e69f48b044f4ee695b942b0786`; profile config fingerprint `a5397f0f8d2d1efc2ea7622bd0e78b565950f85ff33997a6bb585c6e47dd4981`.

*End of OC1 audit. Evidence only; no recommendation expressed or implied.*
