# V2 Batch C4 — Snapshot Hygiene OFF/ON Causal A/B: Lane Recovery Report

Status: **RECOVERED — AWAITING QUIET-VOLUME EXECUTION.** The accidentally-closed
Batch C4 lane is recreated with the C4 identifier retained. This report
reconstructs the experiment's exact current state, verifies the previously-fixed
C4 semantics survived all later Phase C/D edits, incorporates the latest
C8/C9/C10/C12 restore-tail evidence (including the pathological
AWS/ap-northeast-1 cold restore), extends the analyzer to record host/region/
B1/restore-tail stratification fields, and pins the exact future A/B execution
procedure. **NO paid Modal work was performed: no deploy, no Modal request, no
snapshot construction, no benchmark, no remote probe.** Local/read-only
inspection and local offline tests only. No commit. CURRENT main only. No
worktree.

---

## 1. C4 state (reconstructed)

| artifact | state |
|---|---|
| `V2_BATCH_C4_HYGIENE_OPERATIONAL_PREFLIGHT.md` | PREFLIGHT COMPLETE — READ-ONLY; operational readiness = READY (no launcher/runtime change required) |
| `V2_BATCH_C4_SNAPSHOT_HYGIENE_AB_PREP_REPORT.md` | PREPARED — NOT EXECUTED (harness/parser/tests built) |
| `V2_BATCH_C4_HYGIENE_AB_REPORT.md` | EXECUTED UP TO BLOCKER — **NO VALID RUNS OBTAINED** (0 valid A / 0 valid B) |
| `V2_BATCH_C4_HYGIENE_ANALYZER_SEMANTIC_FIX_REPORT.md` | COMPLETE — TOOLS/TESTS ONLY (analyzer semantic fix v2 shipped, 24 tests) |
| this report | RECOVERED — AWAITING QUIET-VOLUME EXECUTION |

**Run ledger (all Arm A, hygiene=0, all structurally invalid on B1):** 9 Modal
requests across 2 deploys (deploy 1 `im-cbQAbT653BRROc27Cm4fKu`, deploy 2
`im-a2IIJylwwXvbZWobiJofec`, both `stable-modal-comfy-v2-variance-shadow`,
C1 triple identical `f4cda0ff…/0fa72e8f…/be68be19…`); 7 completed runs + 2
operator-aborted mid-flight. Every completed run was cold
(`restore_count=1, request_count=1`), `retained=True`, hygiene event absent
(correct for Arm A), `effective_env` flag "0", and **B1-invalid**: the
`runtime_state_reload_decision=reloaded_generation_mismatch` guard forced a
fail-closed volume reload of 68–327 ms (`c4_armA_console.log:750`,
`c4_armA_deploy2.log:728`, `c4_armA_retry1.log:434`, `c4_armA_retry4.log:442`,
`c4_armA_retry5.log:413`, `c4_armA_retry6.log:419`, `c4_armA_retry7.log:424`,
`c4_armA_retry8.log:422`). Arm B never deployed. Region was unpinned: runs 1–7
landed GCP/us-east4, runs 7–8 landed GCP/us-east1 (a second host-variance
confound, `V2_BATCH_C4_HYGIENE_AB_REPORT.md:58-60`). Valid counts: **A = 0,
B = 0.**

## 2. Prior blocker (confirmed, unchanged)

**B1 runtime-state guard never converges.** Every restore returned
`runtime_state_reload_decision decision=reloaded_generation_mismatch
reason=generation_mismatch check_ms=1.47` → fail-closed Volume reload
(68–327 ms), far above the validity gate (invoked=False, reload ≤ 10 ms).

Mechanism (AB report §3, corroborated by `V2_BATCH_B_RUNTIME_STATE_RELOAD_GUARD_REPORT.md:88-101,175-187` and `V2_BATCH_C11_MODAL_STORAGE_AUDIT.md:40,59`): the runtime-config volume (`comfymodal-runtime-config`) is **shared across all shadow apps**; every snapshot construction (C4's deploys, Modal's ~20-min platform re-constructions, the concurrent C6 lane's app) rewrites the `runtime_config_generation.json` generation marker with a **15+ minute propagation lag**. Restores therefore never see a marker matching the snapshot's frozen `runtime_state_generation_baseline`, and each construction resets the race. 7 sequential retries over ~110 minutes never landed in a matching window. Batch-C only converged (run 3, 20:01) after construction activity subsided. The STOP condition applied; no redeploy was performed; the deployment remains in place.

**Notable current evidence:** the two newest artifacts in the run store
(`v2_2026-08-15_19-05-48\run_0.json` and the pathological
`v2_2026-08-15_19-02-50\run_0.json`) both show
`runtime_state_reload_decision=skipped_generation_match` with
`reload_runtime_state_ms=0.0` — i.e., the guard is currently **converging** in
the quiet window. This is encouraging but must be re-verified at execution
time; the future procedure below still gates on B1 before any capture.

## 3. Hygiene implementation intact (verified against CURRENT main)

- `comfymodal_runtime/snapshot_capture_hygiene.py` (208 lines) — unchanged,
  intact: flag gate `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`
  (`HYGIENE_GATE_KEY`, truthy set `{"1","true","yes","on"}`), `run_capture_hygiene`
  performs the bounded pre-capture pass: measure before (VmRSS/RssAnon/RssFile/
  VmSize/VmData + cgroup memory.current) → `gc.collect()` →
  **guarded** `malloc_trim(0)` (`_malloc_trim`, `ctypes.CDLL("libc.so.6")`,
  nonfatal/unavailable on non-Linux) → measure after → event dict stashed under
  `_LATEST_HYGIENE` and printed as `[v2.snapshot_capture_hygiene]`. Never
  raises; unavailable measurements are `None`/`unavailable`, never 0.
- Invocation intact in `comfymodal_runtime/modal_app.py`:
  - `:3048-3049` — flag read into `_runtime_env` (`"0"` default, `"1"` enabled)
  - `:9074-9083` — capture-boundary gate: when flag truthy, imports
    `run_capture_hygiene` and stashes the event at
    `_restore_timing["snapshot_capture_hygiene"]` (verified in real artifact:
    `_restore_timing` carries `restore_gpu_state_ms`, `restore_total_ms`,
    `container_session_id`, `runtime_state_generation_baseline`, etc.)
- No later Phase C/D edit touched either file (read-only verification; both
  files match their documented semantics; hygiene local tests pass — §8).

## 4. Analyzer semantics intact (verified against CURRENT main, with line refs)

`tools/benchmark_v2_snapshot_hygiene_ab.py` (now 1925 lines) preserves every
previously-fixed semantic:

1. **Freshness authority** = per-construction `container_session_id`
   (`result._restore_timing.container_session_id`, `_container_session_id` at
   `:422-430`) **corroborated** by `runtime_state_generation_baseline`
   (`:433-442`); fail-closed NOT READY when missing/inconsistent
   (`_freshness_ready` `:1076-1098`, protocol `:1100-1127`). Runtime source
   verified: `modal_app.py:343` fixes `_V2_CONTAINER_SESSION_ID` per
   construction; `runtime_state_generation_baseline` frozen at construction.
2. **`restore_session_id` is correlation only** — per-restore uuid
   (`modal_app.py:9529`, `uuid.uuid4().hex`), extracted/reported but never a
   freshness input (`:410-419`, `:676-679`, render note `:1361-1368`).
3. **`snapshot_identity` is lineage, NOT freshness** — stable model hash,
   arm-invariant (`:397-407`); freshness verdict proven insensitive to it
   (test F).
4. **Primary metric** = authoritative C3
   `final_reconciled_waterfall.non_scheduling_ms` (`_c3_scheduling` `:294-338`;
   reconciled source preferred `:321-324`; real artifact confirmed the
   reconciled waterfall carries `non_scheduling_ms`, `command_to_enqueue_ms`,
   `scheduling_time_ms`).
5. **Fallback** = `command_response_ms − command_to_enqueue_ms − placement`
   only when the reconciled field is absent (`:325-334`, source tagged
   `"fallback_arithmetic"`; C3 reference check: 35168/19158/854.266 →
   non_scheduling 15155.734, tests G–J).
6. **Legacy placement-only subtraction** is never mixed: exposed separately as
   clearly-labelled `legacy_placement_excluded_ms` informational
   (`:724-726`, `:1049-1052`, render `:1518-1540`); if either arm lacks C3
   sources the report says so explicitly (`c3_primary_available_a/b`,
   render `:1462-1477`).
7. `modal_startup_ms` scheduling-inclusive, excluded from the causal verdict;
   RSS drop alone never a startup win (`rss_drop_without_startup_win`); cold
   gating `restore_count==1 && request_count==1`; 1–5 run policy; median
   n≥2/p90 n≥5; flag verification 0/1 with absent=UNVERIFIED-not-invalid.

No later Phase C/D edit broke the analyzer or the hygiene flag: the entire
hygiene analyzer suite (24 pre-existing + 3 new) and the C3 contract suites
pass on CURRENT main (§8).

## 5. Latest restore-tail evidence incorporated (C8/C9/C10/C11/C12 + cold logs)

### 5.1 The pathological AWS/ap-northeast-1 example — located and dimensioned

The cited example is real and was located in the run store:
`..\..\comfymodal-data\benchmarks\runs\v2_2026-08-15_19-02-50\run_0.json`
(app `stable-modal-comfy-v2-c9qd-shadow`; the task-brief numbers were rounded
from this artifact + its console `[v2.restore_deep]` line, which is not
persisted in the JSON):

| dimension | value (artifact-verified) |
|---|---|
| provider | `CLOUD_PROVIDER_AWS` |
| region | **ap-northeast-1** |
| host fingerprint | `62c4820040bbbf…` (`identity.fingerprint`); CPU Intel/6/207 (`host_telemetry`), GPU RTX PRO 6000 Blackwell Server Edition, 12 CPU |
| pre-Python restore | `pre_python_interval_ms=40422.823` — classified `"scheduling + pre-Python restore (unresolved platform interval)"`; ~13.46 s "before Python resumed" figure is log-native (restore-begin→Python-resume segment), not persisted in the artifact |
| Python restore | `restore_total_ms=16080.582` (~16080.6) |
| restore bootstrap | `snapshot_restore_ms=7852.46` (~7853); `v2_bootstrap_restore_start/end` trace events present (no duration metadata persisted) |
| restore gpu-state | `restore_gpu_state_ms=7704.483` (~7704), invoked |
| restore residual | ≈8219 ms per the log-native `[v2.restore_deep]` residual (total − deep-leaf sum ≈ 16080.6 − ~7861.6); not persisted in the artifact |
| non-scheduling request wall | `non_scheduling_ms=30598.36` (reconciled); scheduling `18195.24`; `command_response_ms=71021.18` |

**Attribution discipline:** per the brief, no dimension is collapsed into
another. Provider, region, host fingerprint, pre-Python restore, Python
restore, `restore_gpu_state`/bootstrap, and restore residual are treated as
**separate dimensions**. The hygiene experiment must not attribute host/region
variance to the flag. Supporting evidence:

- `V2_BATCH_C9_FASTSAFETENSORS_INTEGRATION_REPORT.md:273,288,293-301` —
  ap-northeast-1 run 2 (same region family): host restore 29.5 s vs 3.4 s on
  us-east-2; the report attributes it to **host/region variance**, not a code
  path, and keeps internal loader-stage comparisons authoritative.
- `V2_CACHED_FIRST_NODE_PRODUCTION_DEFAULTS_AND_RESTORE_CHARACTERIZATION.md:219` —
  R3 (us-east4) is the only non-us-east1 run and the only extreme outlier on
  every axis; consistent with region/host variance; valid evidence, not
  discarded.
- `V2_RTX6000_12CPU_32G_6_COLD_RUN_REPORT.md:12-19,41` — "cross-region spread
  dominates variance" (eu-west-2 17.4 s CPU→GPU @0.71 GB/s vs us-south1 1.3 s
  @9.32 GB/s); ap-northeast-1 run 6 row (restore 2503 ms, scheduling 91126 ms).
- `V2_SNAPSHOT_ARCHITECTURE_AND_WORKING_SET_RESEARCH.md:183-191` — pre-Python
  restore typically 0.8–6.5 s (median ~3.5 s) but host/scheduling variance
  dominates; pre-Python gap is Modal scheduling (10.7–203 s), not restore
  (`V2_REMAINING_OPTIMIZATION_DIAGNOSTICS.md:173,185`).
- `V2_RUN4_BAD_HOST_FORENSICS.md:97,146,173,199` — per-host variance within a
  batch; pre-Python restore does NOT predict H2D (rho −0.22).
- `v2_pcc_deploy8_construction.log:93-99` — closest numeric analog
  (restore_total_ms=16364.625, bootstrap 16332.3 ms, residual 26.7 ms,
  eu-south-2): a construction-adjacent restore, unattributed in any report;
  do NOT reuse as C4 evidence.
- `V2_RESULT_HANDOFF_RESTORE_AND_SETUP_RESEARCH.md:146-197` — Python-restore
  decomposition: `restore_gpu_state` 183–1317 ms, `cuda_init` 2.6–5.1 ms,
  `reload_runtime_state` 71.5–263.8 ms RPC, `reload_models` 68.7–388.2 ms RPC;
  10-run median restore_total 610 ms, range 385–1535 ms.

### 5.2 Restore-tail fields available in artifacts (verified on real JSON)

`result._restore_timing` (persisted) carries: `restore_total_ms`,
`restore_gpu_state_ms` + `_invoked` + `_reason`, `reload_runtime_state_ms` +
`_invoked` + `_reason`, `reload_models_ms`, `initialize_cuda_ms`, `cuda_init_ms`,
`snapshot_identity_checks_ms`, `cpu_snapshot_retargeting_ms`,
`synchronized/snapshot_restore_ms`, `backend_startup_ms`, `sync_custom_nodes_ms`,
`observe_generations_ms`, `v2_startup_snapshot_execution_seed_ms`,
`container_session_id`, `restore_session_id`,
`runtime_state_generation_baseline`. The reconciled waterfall carries
`non_scheduling_ms`, `command_to_enqueue_ms`, `scheduling_time_ms`,
`pre_python_interval_ms` + `_classification`, `residual_ms`, and
`host_telemetry` (gpu_name, gpu_vram_mib, cuda_version, compute_capability,
cloud, region, cpu_vendor/family/model). Trace events carry
`host_hardware_fingerprint` (metadata incl. `cpuinfo_fingerprint_hash`),
`runtime_state_reload_decision` (decision/reason/check_ms/invoked),
`v2_bootstrap_restore_start/end`, `models_reload_decision`. `[v2.restore_breakdown]`
and `[v2.restore_deep]` (incl. `bootstrap_restore_ms`, log-native `residual_ms`)
are console-only and are NOT persisted in artifacts.

## 6. Analyzer/reporting plan updated for stratification

`tools/benchmark_v2_snapshot_hygiene_ab.py` extended (by @fixer lane, additive;
semantics untouched — §4 suite proves it):

- New per-run record fields: `host_fingerprint` (trace
  `cpuinfo_fingerprint_hash` → `host_telemetry` cpu triple), `host_cpu_model`,
  `gpu_name`, `runtime_state_reload_decision` (B1 result),
  `runtime_state_reload_check_ms`, `runtime_state_reload_invoked`,
  `reload_runtime_state_ms`, `restore_bootstrap_ms` (`_restore_timing`
  `bootstrap_ms`/`bootstrap_restore_ms` → `v2_bootstrap_restore_end/start`
  event durations — only when available, never fabricated),
  `restore_gpu_state_ms` (when available), `restore_residual_ms` (derived:
  `restore_total_ms − Σ present standard stage ms`, informational).
  Provider, region, `container_session_id`, snapshot/construction identity,
  pre-Python restore, Python restore, and C3 `non_scheduling_ms` were already
  recorded.
- New protocol fields: `host_fingerprints_a/b`, `b1_reload_invoked_any_a/b`.
- New report section **"Host / region stratification"**: per-run table
  (run_id | arm | provider | region | host fingerprint | cpu model |
  non_scheduling_ms | application_restore_ms | B1 decision) for ALL records,
  per-arm region/fingerprint sets, and explicit WARNINGs when an arm spans
  multiple regions or multiple host fingerprints ("observed differences must
  NOT be attributed to the hygiene flag without stratification") or when any
  valid run shows a B1 volume reload (operator B1 gate must be checked).
- Real-artifact smoke (staged copies only): fields populated correctly
  (`host_fingerprint=9d2619e118e52b9e…`, gpu `NVIDIA RTX PRO 6000 Blackwell
  Server Edition`, B1 `skipped_generation_match` check 10.5/4.6 ms,
  `restore_gpu_state_ms=238.256/7704.483`); `restore_bootstrap_ms` correctly
  `unavailable` (no persisted duration on these artifacts).

Caveats: derived `restore_residual_ms` can go negative on artifacts whose
children (e.g. `backend_startup_ms` ≈ 22 s) exceed `restore_total_ms` — it is
informational stratification, and the log-native `[v2.restore_deep]` residual
remains authoritative for the pathological case. B1 WARNING rendering was
reviewed but not exercised against a real `reloaded_generation_mismatch`
artifact (none exists in the current store).

## 7. Future execution procedure (NOT executed — prepared exactly)

Repeated from the AB report with the stratification plan folded in. **Do not
execute while other Phase D deployments/snapshot constructions are active.**

1. **Quiet window:** wait until all Phase D deployments/snapshot constructions
   are finished, then a ~30-minute quiet period (no other app writing
   `comfymodal-runtime-config`).
2. **Arm A (existing deployment, NO redeploy):** retry **ONE** existing Arm-A
   request (`deploy_and_run_v2_single.bat` via
   `cmd /c "call \"<repo>\deploy_and_run_v2_single.bat\" > log 2>&1"`; full-path
   invocation, per AB report §5). Verify the artifact: B1 must be
   `skipped_generation_match` with `runtime_state_reload_invoked=False` and
   `reload_runtime_state_ms ≤ 10 ms` (exact-match/skipped-generation-match). If
   B1 is not exact-match/skipped-generation-match: **STOP** — report and wait
   for a quieter window; never redeploy to force it.
3. **Capture A:** if valid, that run is Arm A (`container_session_id` recorded,
   hygiene event absent, flag "0"). Stage into `staging_hygiene_ab\A`.
4. **Arm B:** deploy hygiene=1 **once** (same shadow app; new construction —
   require `container_session_id` ≠ Arm A's, hygiene event present with
   `enabled=1`, C1 triple equal). Settle; same B1 quiet-window verification;
   capture ONE Arm B. Stage into `staging_hygiene_ab\B`.
5. **Compare:** run the extended analyzer:
   `python tools\benchmark_v2_snapshot_hygiene_ab.py --arm-a staging_hygiene_ab\A --arm-b staging_hygiene_ab\B --out V2_BATCH_C4_HYGIENE_AB_REPORT.md --json V2_BATCH_C4_HYGIENE_AB_ANALYSIS.json`.
   Read `## Host / region stratification` before the verdict; treat any arm
   region/host-fingerprint mismatch per §5 discipline (never as an arm effect).
   RSS/hygiene evidence never alone constitutes a startup win.
6. **No cohort unless ambiguity requires it:** if the A/B difference is clear →
   STOP. Expand toward max 5 valid runs/arm only when consistency or variance
   genuinely requires it.

## 8. Local/offline tests run (this session)

```
python -m pytest tests/test_benchmark_v2_snapshot_hygiene_ab.py tests/test_v2_snapshot_capture_hygiene.py tests/test_v2_snapshot_manifest_hygiene_extensions.py tests/test_v2_waterfall_scheduling_contract.py tests/test_waterfall_scheduling_denominator.py -q
62 passed in 10.42s
```
Breakdown: hygiene A/B analyzer **27 passed** (24 pre-existing + 3 new:
B1-decision/reload extraction, host-fingerprint extraction + `host_telemetry`
fallback, restore-tail gpu-state/bootstrap/residual extraction) ·
`test_v2_snapshot_capture_hygiene.py` **passed** (incl. real hygiene-event
emission, malloc_trim unavailable path) · `test_v2_snapshot_manifest_hygiene_extensions.py`
**passed** · C3 scheduling-contract suites **18 passed** (12 + 6, unchanged).
`python -m py_compile tools/benchmark_v2_snapshot_hygiene_ab.py` → OK.
Real-artifact smoke: analyzer CLI ran over two staged `run_0.json` artifacts
(v2_2026-08-15_19-05-48 vs v2_2026-08-15_19-02-50) — exit 0, new columns
populated (see §6).

## 9. Files changed (this session)

- `tools/benchmark_v2_snapshot_hygiene_ab.py` — additive stratification
  extension (host fingerprint/CPU/GPU, B1 result + reload ms, restore
  bootstrap/gpu-state/residual fields; protocol fields; run-records columns;
  `## Host / region stratification` section + WARNINGs).
- `tests/test_benchmark_v2_snapshot_hygiene_ab.py` — +3 additive tests.
- `V2_BATCH_C4_SNAPSHOT_HYGIENE_RECOVERY_REPORT.md` — this report.
- NOT modified: runtime, `modal_app.py`, `snapshot_capture_hygiene.py`,
  deploy scripts, C3/C5/C6/Batch-C files, experiment store, waterfall.
- **commit = none.**

## 10. Final response fields (this session)

- C4 state = **RECOVERED — AWAITING QUIET-VOLUME EXECUTION** (lane recreated
  with C4 identifier; experiment unchanged: hygiene OFF/ON causal A/B,
  `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`)
- prior blocker = B1 runtime-state guard `reloaded_generation_mismatch`
  (shared runtime-config volume generation marker rewritten by concurrent
  constructions; 15+ min propagation lag; fail-closed reload 68–327 ms; 0
  valid A / 0 valid B)
- hygiene implementation intact = **YES** (`snapshot_capture_hygiene.py`
  unchanged; gate + invocation at `modal_app.py:3048-3049`, `:9074-9083`;
  gc.collect + guarded malloc_trim(0) verified)
- analyzer semantics intact = **YES** (freshness = container_session_id +
  baseline corroboration; restore_session_id correlation-only; snapshot_identity
  lineage-only; primary = reconciled C3 `non_scheduling_ms`; fallback =
  cmd_resp − enqueue − placement; legacy placement-only labelled, never mixed —
  all verified with line refs, §4)
- latest restore-tail evidence incorporated = **YES** (pathological run located:
  `v2_2026-08-15_19-02-50`, AWS/ap-northeast-1, restore_total_ms=16080.582,
  gpu_state 7704.483, bootstrap/snapshot_restore 7852.46, pre-Python interval
  40422.823 unresolved, residual ≈8219 log-native; C9/C8/C10/C11/C12 digests
  incorporated, §5)
- region/host confound handling = **EXPLICIT** (separate dimensions; analyzer
  records provider/region/host fingerprint/CPU/GPU per run; new stratification
  section + WARNINGs; attribution discipline per §5)
- files changed = `tools/benchmark_v2_snapshot_hygiene_ab.py`,
  `tests/test_benchmark_v2_snapshot_hygiene_ab.py`,
  `V2_BATCH_C4_SNAPSHOT_HYGIENE_RECOVERY_REPORT.md`
- local tests = **62 passed** (27 hygiene analyzer incl. 3 new, capture
  hygiene, manifest hygiene extensions, 18 C3 contract)
- commit = **none**

REMOTE_READY = **YES** (preflight-ready; recent artifacts already show
`skipped_generation_match`; B1 gate must be re-verified at execution time)
REMOTE_RUNS_PERFORMED = **0**
DEPLOYS_PERFORMED = **0**

- exact future A/B procedure = §7 (quiet window → one Arm-A retry on existing
  deployment → B1 gate: STOP unless skipped-generation-match → capture A →
  deploy hygiene=1 once → settle → capture B → stage → extended analyzer →
  stratify host/region before verdict → no cohort unless ambiguity requires)
- anything blocking later execution = **Only** (a) concurrent Phase D
  deployment/snapshot-construction activity on the shared
  `comfymodal-runtime-config` volume (B1 convergence requires ~30 min quiet),
  and (b) the operator-side B1 gate at capture time. No code/runtime blocker
  remains; region is unpinned (mitigated by stratification, not by control).
