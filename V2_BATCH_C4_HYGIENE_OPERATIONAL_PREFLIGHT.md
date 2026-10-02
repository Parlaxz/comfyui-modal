# V2 Batch C4 — Hygiene OFF/ON Operational Preflight (Read-Only)

Status: **PREFLIGHT COMPLETE — READ-ONLY.** No source modified, no deploy, no
Modal run, no commit. Prepared against CURRENT main while the C5 lane runs.
Subagent-driven inspection (3 explorer lanes) reconciled against the sources
cited below.

---

## 1. Executive summary

| item | result |
|---|---|
| operational readiness | **READY** — no launcher or runtime change required |
| code changes required before experiment | **NONE mandatory** (one analyzer gap exists; handled procedurally — smallest fix in §12.1) |
| Arm A exact procedure | §6 |
| Arm B exact procedure | §7 |
| fresh-snapshot proof | §8 (per-deploy construction session + capture-time event + effective_env) |
| C1 identity interaction | §9 (valid under both arms; arm-invariant; lineage proof only) |
| B1 convergence handling | §10 (first post-snapshot run + ~25–30 min re-construction window) |
| primary metrics | §11 (scheduling-free primaries; modal_startup excluded from verdict) |
| analyzer semantic issues | §12 (5 items; 1 blocks a clean report, rest are guardrails) |
| minimum useful run count | §13 (1 valid A + 1 valid B; tool labels n=1 as INSUFFICIENT DATA — read raw deltas) |

## 2. Semantic requirement (verified)

Hygiene runs at snapshot **capture**: gate `COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE`
is read inside `startup()` immediately before the capture boundary
(`modal_app.py:9023–9041`), and the event is stored in
`_restore_timing["snapshot_capture_hygiene"]`. The flag is **baked into the
deployed class env at deploy time** (`_runtime_env`, `modal_app.py:3043–3045` →
class `env=` at `modal_app.py:17383`); the per-request override allowlist in
`benchmark_v2_direct.py:126–134` does NOT include it. Therefore a per-request
flag flip on an existing snapshot is impossible and invalid: **one deploy per
arm, flag set in the calling shell before deploy.**

## 3. Launcher facts (deploy_and_run_v2_single.bat)

- Deploy: `modal deploy -m comfymodal_runtime.modal_app --name "!COMFYMODAL_V2_APP_NAME!"`
  (bat:263); pure process-env passthrough, no `--env` flags.
- Defaults are guarded (`if not defined VAR set ...`, e.g. bat:92) so
  caller-shell values survive; forced sets are limited to
  `CLASS_NAME`/`V2_IS_VARIANCE`/`V2_PROFILE_PRETOUCH` (bat:8,14,19) and the
  restore-only profile block (bat:56–74). **The hygiene key is never set by any
  .bat** (all 6 root .bat searched).
- C1 identity recorded right after deploy: `python tools\record_deployment_identity.py`
  (bat:295, :439) → `.deployed_state.json` at repo root
  (deployment_combined_hash / custom_nodes_generation / overall_dependency_hash /
  comfyui_version / comfyui_core_match / app_name / deployed_at ...).
- Benchmark modes are explicit opt-ins via `V2_BENCHMARK_MODE` (bat:475–534).
  `snapshot_restore_only` (default) exits **without probes** (bat:516–525).
  `variance_cold` = one request at a time, 25 s gap, strict cold-identity proof
  (bat:483–491) — **recommended for C4**. `acceptance` = A fresh / B reused /
  C fresh (bat:492–499) — **B-reused runs are warm and NOT AB-eligible**.

## 4. Snapshot identity fields persisted per run

Per-run record (`experiment_result_store.py:379–421`; artifacts in
`comfymodal-data/benchmarks/runs/v2_<ts>/run_<i>.json`,
`benchmark_v2_direct.py:8110`):

- `snapshot_identity` — primary = remote `cpu_snapshot_models.model_key.stable_hash`
  (`modal_app.py:15431–15432`) — **arm-invariant**; fallback (only when primary
  missing) = `image_id|restore_session_id` (`experiment_result_store.py:347–355`).
- `_restore_timing` (inside artifact `result`) carries `restore_session_id`
  (`modal_app.py:8864/8880` — **per-construction session uuid**, the freshness
  discriminator), `snapshot_manifest` (`modal_app.py:8992`, captured
  pre-hygiene), `runtime_state_generation_baseline` (`modal_app.py:9019`),
  `snapshot_capture_hygiene` (arm B only; `modal_app.py:9039`).
- `effective_env` includes every `COMFYMODAL_*`/`V2_BENCHMARK` key
  (`experiment_result_store.py:398–402`), so the baked flag value is persisted
  per run.
- `source_identity` (runtime/dependency/custom_node/combined hash) is
  source-file-only, env-independent — identical across arms.
- B1 marker (Volume side): `runtime_config_generation.json` `generation`
  (`runtime_generation.py:155–160`), frozen into the snapshot at construction
  via `RuntimeBootstrap.finalize_runtime_state_generation`
  (`modal_app.py:9014–9021`).

## 5. Proof of "different snapshot construction per arm" (what differs / does not)

**Differs (the proof):**
1. `_restore_timing.restore_session_id` — new `uuid4` per construction session;
   disjoint across arms, constant within an arm.
2. `_restore_timing.snapshot_capture_hygiene` — **present iff hygiene=1 at
   capture** (`enabled:1`, `gc_collected`, before/after/Δ RSS + anon/file/vm,
   cgroup bytes, `hygiene_wall_ms`); absent on arm A. Definitive capture-time
   marker.
3. `effective_env["COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"]` = `"1"` vs `"0"`.
4. Snapshot bytes/page-file content (fewer live anon pages after hygiene) —
   not directly persisted; no snapshot content hash exists.

**Does NOT differ (identity stability, must be held equal):** `snapshot_identity`
(model hash), `source_identity`/`combined_hash`, C1 triple, `image_id`,
`worker_fingerprint`, workflow hash, runtime-generation uuid. The protocol
checks `snapshot_per_arm_fresh` / `snapshot_consistent_within_arm`
(`benchmark_v2_snapshot_hygiene_ab.py:842–851`) therefore **cannot pass on the
persisted `snapshot_identity`** — see §12.1.

## 6. Arm A exact procedure (hygiene OFF)

Fresh PowerShell shell (cmd equivalent in parentheses):

```powershell
# 1. C4-specific shadow app — zero overlap with the C5 lane's app
$env:COMFYMODAL_V2_APP_NAME = 'stable-modal-comfy-v2-c4-hygiene-shadow'
# 2. Arm A: explicit "0" (absent would persist as default 0 but read UNVERIFIED
#    by the analyzer -> always set explicitly)
$env:COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE = '0'
# 3. Opt-in benchmark mode: strict cold identity, one request at a time, 25 s gap
$env:V2_BENCHMARK_MODE = 'variance_cold'
# 4. Deploy (env baked at deploy) -> C1 identity recorded -> benchmark runs
.\deploy_and_run_v2_single.bat
```

After the bat finishes (deploy + first runs):

1. **Record the arm-A construction session**: read
   `result._restore_timing.restore_session_id` from the first run artifact
   (also visible in the deploy log). This is the arm-A session id.
2. **Wait for B1 convergence** (see §10): retain runs only after the runtime-
   state guard shows `skipped_generation_match / exact_match`, `invoked=False`,
   `reload 0.0` — historically ~25–30 min after deploy (C integrated
   validation: runs at 19:36 and 19:55 blocked, 20:01 converged).
3. **Discard the first post-snapshot run** (run_role `validation_discard`,
   `retained=False`, `discard_reason="first_post_snapshot_run"` —
   `benchmark_v2_direct.py:2565–2584, 8621–8624`). If a measurement run was
   persisted as `sample`, exclude it from the staged set manually.
4. **Validate every candidate run** (checklist §14) with the Batch-C offline
   validator on the run JSON (`validate_batch_c_file`, `batch_c_acceptance.py:744–768`).
5. **Stage accepted runs only**: copy the accepted `run_<i>.json` files into
   `staging_hygiene_ab/A/` (do NOT copy experiment-store `run_<i>_<role>.json`
   duplicates — analyzer globs `run_*.json`, `benchmark_v2_snapshot_hygiene_ab.py:602–641`).

## 7. Arm B exact procedure (hygiene ON)

Same shell discipline, fresh deploy (this is what creates the second,
hygiene-ON snapshot):

```powershell
$env:COMFYMODAL_V2_APP_NAME = 'stable-modal-comfy-v2-c4-hygiene-shadow'   # same name, same lineage
$env:COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE = '1'
$env:V2_BENCHMARK_MODE = 'variance_cold'
.\deploy_and_run_v2_single.bat
```

After the bat:

1. Record the **arm-B construction session** (`restore_session_id`) — MUST be
   different from arm A's (fresh deploy = fresh construction).
2. Wait for B1 convergence (§10); discard the first post-snapshot run.
3. Validate each candidate (checklist §14) — arm B must show the
   `snapshot_capture_hygiene` event with `enabled=1`.
4. Verify the C1 triple in `.deployed_state.json` **matches arm A's** exactly.
5. Stage accepted runs into `staging_hygiene_ab/B/`.

Analysis (after both arms staged):

```powershell
python tools\benchmark_v2_snapshot_hygiene_ab.py `
  --arm-a staging_hygiene_ab\A --arm-b staging_hygiene_ab\B `
  --out V2_BATCH_C4_HYGIENE_AB_REPORT.md `
  --json V2_BATCH_C4_HYGIENE_AB_ANALYSIS.json
```

(Prep-report usage `python -m benchmark_v2_snapshot_hygiene_ab ...` is
equivalent when tools/ is importable.)

## 8. Fresh-snapshot proof (how we prove distinct constructions)

1. **Construction session**: `_restore_timing.restore_session_id` disjoint
   across arms (each deploy constructs a new snapshot; new uuid per
   construction). This is the load-bearing proof.
2. **Capture-time event**: `snapshot_capture_hygiene` present with `enabled=1`
   in every B run; absent in every A run — proves which env built the snapshot.
3. **Baked env**: `effective_env["COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"]`
   = "1" / "0" in the persisted records.
4. **Lineage held equal**: single `image_id` + identical C1 triple across arms
   (`lineage_consistent`, `workflow_consistent` protocol checks) — the arms
   differ ONLY in the baked flag.

Note: `snapshot_identity` (model hash) is arm-invariant and CANNOT prove
freshness; do not use it for the per-arm separation (§12.1).

## 9. C1 identity interaction

- C1 = deploy-frozen source/image lineage triple in `.deployed_state.json`
  (recorded via container readback, `record_deployment_identity.py`).
- `deployment_combined_hash` folds in `runtime_shape` env knobs
  (`runtime_shape.py:103–118`) but NOT the hygiene flag — two hygiene-0/1
  deploys with identical source + runtime shape yield the **same** triple.
- Therefore C1 **remains valid under both arms and must be identical across
  arms**: it proves one deployment lineage (a required protocol invariant),
  and a C1 mismatch would itself invalidate a run pair. It cannot and must not
  serve as the arm discriminator (that is §8).
- The flag is observable only via the baked class env, `effective_env`, and
  the capture-time event — all persisted per run (§4).

## 10. B1 generation convergence handling

B1 = Batch-B runtime-state generation guard
(`runtime_bootstrap.py:1687–1760`): compares the `runtime_config_generation.json`
marker currently on the shared runtime-state Volume against the generation
frozen into the snapshot at construction; mismatch → fail-closed Volume reload.

- After deploy, Modal re-constructs the snapshot ~20 min later; the new marker
  write races the restored containers. During the window the guard emits
  `reloaded_generation_mismatch` / `generation_mismatch` with `invoked=True`
  and reload > 0 — failing the Batch-C runtime-state gate (expects
  `skipped_generation_match`, `invoked=False`, reload ≤ 10 ms).
- Evidence: C integrated validation — runs at 19:36 (FAIL, mismatch, reload
  165 ms) and 19:55 (second construction, still churning) were structurally
  blocked; run at 20:01 converged (`exact_match`, reload 0.0). Convergence
  took ~25–30 min and can be re-triggered by a further platform
  re-construction.
- **Invalid first post-deploy runs:** (1) the harness's own first post-snapshot
  run (discard by design); (2) any run inside the re-construction window whose
  B1 event shows `reloaded_generation_mismatch` / `invoked=True` / reload > 0.
  Rule: a run is B1-valid only when its guard decision is
  `skipped_generation_match` with `invoked=False`, reload ≤ 10 ms (0.0
  expected).

## 11. Primary metrics (comparable without scheduling contamination)

| metric | source | role |
|---|---|---|
| command without scheduling → response | `command_response_ms − scheduling_ms` (placement only) | **primary** |
| pre-Python snapshot restore | waterfall stage `pre_python_snapshot_restore` (fallback key) | **primary** |
| Python/application restore | waterfall stage `application_restore` (fallback `restore_total_ms`) | **primary** |
| capture-time RSS / gc / hygiene_wall_ms | `snapshot_capture_hygiene` event (A absent → unavailable, never 0) | proof + informational; RSS alone never upgrades a verdict |
| H2D / sampling / process CPU / provider / region | trace + timing | secondary, informational |
| Modal startup | `submission_to_remote_python_resume_ms` (fallbacks) | **scheduling-inclusive, EXCLUDED from verdict** (`benchmark_v2_snapshot_hygiene_ab.py:359–368, 732`) |
| total wall | `total_wall_ms` | informational only (acceptance: TOTAL WALL NOT AN ACCEPTANCE GATE) |

Scheduling contamination is measured and reported
(`scheduling_contamination`: median scheduling delta vs primary deltas) but
never subtracted — scheduling is excluded by construction, not by correction
(`benchmark_v2_snapshot_hygiene_ab.py:101–104` prep report; tool lines
842–851).

## 12. Analyzer semantic issues (before spending a Modal run)

1. **`snapshot_per_arm_fresh` / `snapshot_consistent_within_arm` are
   unsatisfiable as-is** — persisted `snapshot_identity` is the arm-invariant
   model hash; the `restore_session_id` fallback
   (`experiment_result_store.py:349–353`) only applies when the primary is
   missing; `lineage_consistent` forces one `image_id` across arms. The tool
   will flag "not fresh" even for two genuinely separate constructions.
   **Smallest later change (tools-only):** extract
   `result._restore_timing.restore_session_id` for the freshness check.
   **For now: procedural** — operator records the per-arm construction session
   (§8.1) and asserts disjointness; treat the tool's freshness flag as
   operator-verified.
2. **Scheduling subtraction is placement-only** (`scheduling_ms` = modal
   scheduling stage, `v2_waterfall.py:2987–2992`), while C3's `Scheduling
   time` = enqueue + placement. `command_without_scheduling_ms` therefore still
   contains `local_preparation + modal_handle_submission` (small, symmetric,
   local-only). Valid for symmetric A/B comparison; label accordingly, do not
   equate it with C3's `non_scheduling_ms`.
3. **Glob double-count risk:** `load_arm_runs` matches `run_*.json`, which
   matches both harness `run_<i>.json` and experiment-store
   `run_<i>_<role>.json` in the same dir → stage only the intended files per
   arm dir (§6.5).
4. **Flag absent = UNVERIFIED, not invalid** — always set the flag explicitly
   ("0" for A, "1" for B) so `effective_env` records it and `flag_verified`
   passes.
5. **Manifest RSS is pre-hygiene** (`snapshot_manifest` captured at
   `modal_app.py:8984–8992` before the hygiene pass at 9030–9041) — use only
   the hygiene event's before/after/Δ RSS as capture evidence; the manifest's
   "before_capture" numbers are identical in both arms.
6. **Acceptance needs fast-path events**: `batch_c_acceptance.py` reads
   `result.trace.events` `plan_snapshot_parity` / `plan_proof_decision` /
   `certificate_read_outcome` — verify the first candidate artifact carries
   them before trusting `OVERALL: PASS` (else REPORT_ONLY/FAIL).
7. **Cold runs only:** `_cold` requires `restore_count == 1 AND request_count
   == 1` (`benchmark_v2_snapshot_hygiene_ab.py:329–356`); use `variance_cold`
   mode; exclude acceptance-mode "B reused" runs.

## 13. Minimum useful run count

**Yes — 1 valid A + 1 valid B after validation** is the minimum useful
experiment, per the prep report's own policy (V2_BATCH_C4 prep §3: one cold
validation + one valid measurement per arm; expand only when variance prevents
a conclusion; cap 5 valid runs/arm; stop when the difference is clear).

Caveat: at n=1/arm the analyzer's classification is **INSUFFICIENT DATA**
(median/mean require n≥2; p90 requires n≥5; CONFIRMED requires ≥3 per arm with
fully separated ranges — tool lines 662–760). At 1+1 the "clear difference"
read is: raw delta on a scheduling-free primary exceeding the noise floor
(default `--noise-floor-ms 1.0`) with all protocol checks passing. Expand to
2/arm only for a SUPPORTED INFERENCE label, 3/arm for CONFIRMED — only when
variance actually blocks a conclusion.

## 14. Per-run acceptance checklist (record before accepting a run)

1. `retained == true`, `discard_reason` empty (not the first post-snapshot run).
2. Cold: `restore_count == 1` AND `request_count == 1`.
3. `effective_env["COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE"]` matches arm.
4. B: `_restore_timing.snapshot_capture_hygiene` present, `enabled == 1`, valid
   before/after RSS + `hygiene_wall_ms`; A: key absent.
5. `_restore_timing.restore_session_id` == that arm's construction session;
   arm A vs B sessions disjoint.
6. B1: runtime-state guard decision `skipped_generation_match`, `invoked ==
   false`, reload ≤ 10 ms (0.0 expected).
7. `image_id` single across both arms; `workflow_hash_prefix` single.
8. C1 triple (`.deployed_state.json`: deployment_combined_hash /
   custom_nodes_generation / overall_dependency_hash) identical across arms.
9. Batch-C offline validator verdict PASS (with the C-integrated
   `expect_plan_fast_path` expectation; TOTAL WALL informational only).
10. Artifact carries `result.trace.events` fast-path observables (§12.6).

## 15. Recommended next execution prompt

```
Run the C4 hygiene OFF/ON experiment per V2_BATCH_C4_HYGIENE_OPERATIONAL_PREFLIGHT.md
(READ the preflight + V2_BATCH_C4_SNAPSHOT_HYGIENE_AB_PREP_REPORT.md first).

READ-ONLY discipline for all of this execution:
- CURRENT main only; no source edits, no commits.
- Do not touch the C5 lane's app/worktree; use COMFYMODAL_V2_APP_NAME=stable-modal-comfy-v2-c4-hygiene-shadow.

Arm A (hygiene OFF):  $env:COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE='0'
Arm B (hygiene ON):   $env:COMFYMODAL_V2_SNAPSHOT_ALLOCATOR_HYGIENE='1'
Each arm: fresh PowerShell shell, set the arm env + V2_BENCHMARK_MODE=variance_cold,
run .\deploy_and_run_v2_single.bat, wait for B1 convergence (~25-30 min;
skipped_generation_match, invoked=False, reload 0.0), discard the first
post-snapshot run, validate each candidate with the Batch-C offline validator
+ the preflight §14 checklist (restore_session_id per arm, hygiene event
presence, effective_env flag, cold markers, C1 triple equal across arms),
stage only accepted runs, then run tools/benchmark_v2_snapshot_hygiene_ab.py
--arm-a <stagingA> --arm-b <stagingB> --out ... --json ....

Cohort rule: obtain 1 valid A + 1 valid B; if the scheduling-free primary
delta is clear (> 1 ms noise floor), stop; expand only when variance prevents
a conclusion; max 5 valid runs/arm. Treat the analyzer's snapshot_per_arm_fresh
flag as operator-verified via restore_session_id (see preflight §12.1).
Write V2_BATCH_C4_HYGIENE_AB_REPORT.md + V2_BATCH_C4_HYGIENE_AB_ANALYSIS.json
and summarize the verdict.
```

---

Sources: `deploy_and_run_v2_single.bat`; `modal_app.py` (env passthrough 3043–3045,
capture gate 9023–9041, session ids 8864/8880, snapshot_identity 15431–15432,
class env 17372–17402); `snapshot_capture_hygiene.py`; `experiment_result_store.py`;
`record_deployment_identity.py`; `benchmark_v2_direct.py` (126–134, 2565–2584,
8110, 8621–8624); `benchmark_v2_snapshot_hygiene_ab.py`; `batch_c_acceptance.py`;
`batch_b_acceptance.py`; `v2_waterfall.py`; `runtime_generation.py`;
`runtime_bootstrap.py`; `V2_BATCH_C4_SNAPSHOT_HYGIENE_AB_PREP_REPORT.md`;
`V2_BATCH_C1_IMMUTABLE_PLAN_IDENTITY_REPORT.md`;
`V2_BATCH_C3_WATERFALL_CONTRACT_REPORT.md`;
`V2_BATCH_C_INTEGRATED_VALIDATION_REPORT.md`;
`V2_BATCH_B_INTEGRATED_ACCEPTANCE_AND_COHORT.md`.
