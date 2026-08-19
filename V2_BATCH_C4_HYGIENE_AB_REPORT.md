# V2 Batch C4 — Snapshot Hygiene OFF/ON Causal A/B: Execution Report (BLOCKED)

Status: **EXECUTED UP TO BLOCKER — NO VALID RUNS OBTAINED.** No commits. No
source changes. Deploys: 2. Modal requests: 9 (7 completed runs, 2 aborted
mid-flight by operator). No analyzer A/B report was produced because the
protocol requires 1 valid A + 1 valid B and B1 convergence was never reached.

## 1. What was done

1. Preflight (V2_BATCH_C4_HYGIENE_OPERATIONAL_PREFLIGHT.md) executed.
2. Arm A deployed twice (hygiene=0 baked, verified in `effective_env`):
   - Deploy 1: 15:50–15:56 UTC−4, image `im-cbQAbT653BRROc27Cm4fKu`.
   - Deploy 2 (re-deploy on the C6-changed tree): 16:43–16:49 UTC−4, image
     `im-a2IIJylwwXvbZWobiJofec` (rebuilt — `model_preload.py` + baked custom-
     node manifest changed by the concurrent C6 lane between the deploys).
   - App: `stable-modal-comfy-v2-variance-shadow` (the launcher forces this
     name for `variance_cold` mode at bat:24–25; the requested
     `stable-modal-comfy-v2-c4-hygiene-shadow` is not settable without editing
     the launcher. Dedicated shadow app; C5's production app untouched).
   - **C1 triple (container readback, identical across both deploys):**
     `deployment_combined_hash=f4cda0ff0461beeb7bdb4402217aa2635781dcf15ebf3dcfb94e3e531bc05777`,
     `custom_nodes_generation=0fa72e8f58a71cfd2859a0b64fbc6545`,
     `overall_dependency_hash=be68be1945de2a29c5bb09360d3056d6f3d6d4e3ed8c203d2d0fa82d86d3076c`.
     Note: the identity hash set does not track `model_preload.py` (the C6
     change); the image id changed while the C1 triple stayed equal.
   - Provider/region on every run: `CLOUD_PROVIDER_GCP` / `us-east4`.
3. Analyzer correctness fix delivered mid-execution (sanctioned by proven
   runtime-artifact incompatibility):
   - `_restore_timing.restore_session_id` is a **per-restore** uuid
     (`modal_app.py:9529`), not a construction id. Proven with real artifacts:
     two runs 4 min apart share `container_session_id=74aa5717dfed4bf7` and
     baseline `ab86ef63ce1a…` but differ in restore_session_id.
   - Freshness identity is now `container_session_id` (primary) +
     `runtime_state_generation_baseline` (corroboration); `restore_session_id`
     demoted to per-restore correlation. 24 C4 tests + 18 C3 contract tests
     pass. Real-artifact smoke: same-construction pair → NOT FRESH (correct);
     different-construction pair → FRESH PASS.
   - See V2_BATCH_C4_HYGIENE_ANALYZER_SEMANTIC_FIX_REPORT.md ("Correction (v2)").

## 2. Runs obtained (all Arm A, hygiene=0; all structurally invalid on B1)

| # | time | session (per-restore) | container (construction) | baseline | B1 invoked | B1 reload ms | verdict |
|---|---|---|---|---|---|---|---|
| 1 | 15:54 | 25d00287… | (deploy1-era) | — | True | 125.5 | invalid (B1 + first-post-deploy) |
| 2 | 16:25 | 2fe2e6a9… | (re-construction) | — | True | 82.1 | invalid (B1) |
| 3 | 16:49 | 31f54a76… | 9d918f0a… | — | True | 184.7 | invalid (B1 + first-post-deploy) |
| 4 | 17:20 | 0ba88912… | 74aa5717… | ab86ef63ce1a… | True | 327.2 | invalid (B1) |
| 5 | 17:24 | 3b112f97… | 74aa5717… | ab86ef63ce1a… | True | 68.7 | invalid (B1) |
| 6 | 17:27 | (retry6) | 74aa5717… | ab86ef63ce1a… | True | 110.3 | invalid (B1) |
| 7 | 17:43 | (retry7) | 9d918f0a… | 4a6a96dd… | True | 228.8 | invalid (B1) |
| 8 | 17:46 | a15c1a93… | 9d918f0a… | 4a6a96dd… | True | 137.8 | invalid (B1) |

Every run: `restore_count=1`, `request_count=1` (cold), `retained=True`,
hygiene event ABSENT (correct for Arm A), `effective_env` flag = "0",
`reload_models_invoked=False` (models guard OK). Run 1 and run 3 were also
first-post-snapshot runs (huge scheduling: submission→resume 75–86 s).
Runs 2/3 were aborted mid-flight by the operator (no artifacts written).
NOTE: run 8 landed on **us-east1** (runs 1–7 were us-east4) — region is
unpinned and the platform scheduled this request elsewhere; another host-
variance confound in addition to the B1 blocker.

## 3. Blocker: B1 runtime-state guard never converges

- Guard decision on every restore: `runtime_state_reload_decision
  decision=reloaded_generation_mismatch reason=generation_mismatch
  check_ms=1.47` → fail-closed volume reload (68–327 ms) — far above the
  validity gate (invoked=False, reload ≤ 10 ms).
- Mechanism: the runtime-config volume (`comfymodal-runtime-config`) is
  **shared across all shadow apps**. Every snapshot construction (my deploys +
  Modal's ~20-min platform re-constructions + the concurrent C6 lane's app)
  rewrites the generation marker with a propagation lag of 15+ minutes.
  Restores therefore see a marker that never matches the snapshot's frozen
  baseline, and each construction resets the race.
- The Batch-C validation (V2_BATCH_C_INTEGRATED_VALIDATION_REPORT) converged
  on run 3 (20:01) only because construction activity on the volume had
  subsided. Today, concurrent lanes (C6 probe deploys 16:18–16:55,
  `model_preload.py` edits at 16:05/16:35/16:48, studio lane files at 17:13–
  17:15) kept the volume churning; 7 sequential retries over ~110 minutes
  never landed in a matching window.
- Per protocol this is the STOP condition ("invalid B1-transition runs do not
  count; if the comparison is ambiguous, STOP and report why"). No redeploy
  was performed for B1 (protocol forbids it); the deployment remains in place.

## 4. What remains

- Arm A needs exactly ONE run with `skipped_generation_match` / `invoked=False`
  / reload ≤ 10 ms — expected to be reachable during a quiet-volume window
  (no other app constructing for ~30+ min; mechanism identical to Batch-C
  run 3). The current deployment is unchanged and reusable.
- Then Arm B: deploy once with hygiene=1 to the same app (new construction;
  require `container_session_id` ≠ Arm A's, hygiene event present with
  enabled=1, C1 triple equal), same B1 quiet-window retry, stage both arms,
  run the corrected analyzer:
  `python tools\benchmark_v2_snapshot_hygiene_ab.py --arm-a staging_hygiene_ab\A --arm-b staging_hygiene_ab\B --out V2_BATCH_C4_HYGIENE_AB_REPORT.md --json V2_BATCH_C4_HYGIENE_AB_ANALYSIS.json`
- No `V2_BATCH_C4_HYGIENE_AB_ANALYSIS.json` was produced (no valid A/B pair).

## 5. Operator notes (for the resumption run)

- Invoke .bat files via full path: `cmd /c "call \"<repo>\deploy_and_run_v2_single.bat\" > log 2>&1"`
  (bare-name `call` inside this shell fails with "not recognized" — an
  environment quirk; full-path calls work and the bats self-chdir via %~dp0).
- The launcher forces `stable-modal-comfy-v2-variance-shadow` for variance
  modes; the C4 shadow-app name from the brief cannot be applied without a
  launcher edit (documented deviation; isolation is preserved).
- `.deployed_state.json`'s `app_name` field reads `stable-modal-comfy-v2-restore-only-shadow`
  while the container readback (run artifacts) says `variance-shadow` — a
  record-labeling quirk; the hash triple is container-readback-valid.
- C6 lane artifacts (runs at 16:56 on `c6probe-shadow`) are not part of C4.

## 6. Required final-response fields (blocked state)

- commit = none · deploy count = 2 · Modal requests = 9
- valid A runs = 0 · valid B runs = 0
- Arm A restore_session_id = per-restore uuids (demoted — not construction
  identity); construction container sessions observed: 9d918f0a… (deploy-era),
  74aa5717… (re-construction), 9d918f0a… (retry7 era)
- fresh snapshot proof = analyzer corrected (container_session_id + baseline);
  verified on real artifacts; NO valid pair to compare yet
- C1 triple equal = recorded identical across both Arm A deploys (f4cda0ff… /
  0fa72e8f… / be68be19…); Arm B not yet deployed
- performance metrics = N/A (no valid runs)
- hygiene evidence = N/A for Arm B (not deployed); Arm A hygiene event absent
  as required
- structural classification = BLOCKED (B1 convergence) · performance
  classification = NOT MEASURED
- additional runs needed = 1 valid A + 1 valid B (after a quiet-volume window)
- recommended production hygiene setting = no evidence yet — do not change
  production defaults
