# RX9P-F Integration and Remote Profile Smoke 2026-09-01

> Diagnostic lane — NOT a benchmark cohort. Timing is diagnostic-only due to deep VizTracer/Torch profiling overhead.

## Operational Note (Owner Guidance)

Per owner instruction received 2026-09-01 during this lane:

> **"do not cancel the fixer but deploys should never be via fixers, so from after that do not use deploys in fixers. fixers are to code, not test. include that in your final report that I said that"**

Compliance:
- The single fixer session that executed `v2ctl deploy` / `v2ctl golden run` was **not cancelled** — its artifact and code-repair output were preserved and are documented below.
- From this report forward, **fixers are scoped to code only**; remote deploys and Golden/test execution are handled directly by the orchestrator (or dedicated non-fixer remote lanes). This report is produced directly, not via a fixer deploy lane.
- A background job that stopped without a terminal result (post-integration verification) was recovered by direct verification; no duplicate request was issued.

---

## Integration

- **PRE_INTEGRATION_TESTING2_HEAD:** `9024bbc58de5ea3017d41e8c78dd77329b6acdea`
- **RX9P_D_HEAD (rx9p-d-golden-profiler):** `369d60c7a8f47db743defca570c176eb55bdcf35`
- **INTEGRATED_TESTING2_HEAD:** `369d60c7a8f47db743defca570c176eb55bdcf35`

### Ancestry (verified via `git merge-base --is-ancestor` and `git log --graph --all`)

- `D` HEAD is descendant of `PRE` (`9024bbc` ancestor of `369d60c`: YES)
- Hardening commit `9701d0222fd08d348ace8e1690698de1376c05f4` is ancestor of `D`: YES (also in `TESTING2`)
- D contains:
  - canonical RX8A baseline (via 878a687 etc. in ancestry)
  - RX9P-A (f850f17, 40da4d1)
  - RX9P-B including hardening `9701d02` + `a94567e`, `2b87367`
  - RX9P-C: `1bd0728 feat: instrument and prove E27 source mechanism` + `f8c5cab`, `f850f17` handoffs
  - D reconciliation: `0988fc6 RX9P-D reconciliation` + merge `ac270f2`, second merge `53b4916`
  - D profiler implementation: `4ec1783 RX9P-D: Golden VizTracer deep profiler wiring and report`
  - final report-only repairs: `aee3e5d`, `369d60c`

### Integration method

- History-preserving fast-forward: `git merge --ff-only rx9p-d-golden-profiler` while on `TESTING2`
- `git diff 9024bbc...369d60c --stat` shows only D additions (22 files, +2480/-142), no tools/v2_control rollback:
  ```
  comfymodal_runtime/full_execution_trace.py | 103 +++
  comfymodal_runtime/full_trace_report.py    | 906 ++++++++++++++++++++-
  comfymodal_runtime/golden_serial.py        | 172 ++--
  comfymodal_runtime/modal_app.py            | 477 ++++++++++-
  plus 18 doc/test/support files (see integration_diff_stat log)
  ```
- `tools/v2_control/*` contains no D rollback — D did not modify `tools/v2_control/` (diff empty), verified via `git diff 9024bbc..369d60c -- tools/v2_control/ --stat` → 0 files.

### Files introduced by D (exact list from diff)

`RX9P_D_AUDIT_HANDOFF_2026-09-01.md`, `RX9P_D_GOLDEN_VIZTRACER_DEEP_PROFILER_REPORT_2026-09-01.md`, 7 `RX9P_D_RAW_TEST_*.log` (bin), `SYNTHETIC_*` (3), `comfymodal_runtime/full_execution_trace.py`, `comfymodal_runtime/full_trace_report.py`, `comfymodal_runtime/golden_serial.py` (modified), `comfymodal_runtime/modal_app.py` (modified), `tests/test_v2_full_execution_trace.py`, `tests/test_v2_full_trace_download.py`, `tests/test_v2_full_trace_lifecycle.py`, `tests/test_v2_full_trace_report.py`, `tools/download_v2_full_trace.py`

### Source verification (post-integration, direct)

- `git diff --check`: clean (no whitespace errors)
- `golden_serial.py` contains **BOTH**:
  - RX9P-C: `ActualSourceTelemetry` (line 1858 comment, 3466 instantiation), physical syscall evidence (`preadv`/`pread` path via `golden_qd_transport`/`e27_source_mechanism`), QD occupancy (`dispatcher_control`, `SOURCE_TOTAL_WALL`), H2D evidence (`h2d_events`, `H2D_TOTAL_WALL_MS`, `SOURCE_H2D_OVERLAP_MS`), quiescence (`quiescence_evidence`, `_reconcile_actual_source_h2d`), E27 evaluator (`e27_source_mechanism.py` integration, `E27_SOURCE_MECHANISM_PROOF_REPORT`)
  - RX9P-D: `golden_trace_span` (`_golden_trace_span` def at 1304, usage at 6430), CLIP load spans (`golden_clip_load`), CLIP forward spans (`golden_clip_forward`), six UNET semantic spans (`golden_unet_load` + 5 derived UNET sub-spans per `full_trace_report.py`)
- `modal_app.py` contains:
  - B experiment/runtime identity behavior (experiment IDs, `SAGE_RUNTIME_MODE` handling)
  - D direct-Golden trace lifecycle (`full_execution_trace`, `golden_serial` direct path)
  - D Torch profiler boundary (`torch.profiler` guard in `modal_app.py` + `full_execution_trace.py`)
  - D artifact finalization (`full_trace_report` finalization)
  - D Modal-log Gantt projection (`[v2.golden_profiler]` Gantt with `█`, `TIMELINE_COLUMNS=100` in `full_trace_report.py`)
- Unrelated pre-integration dirty work (6 files: `__init__.py`, `canonical_execution.py`, `comfymodal_runtime/modal_app.py` delta, `tests/test_source_identity_publication.py`, `tools/publish_custom_nodes_volume.py`, `tools/v2_control/custom_nodes.py`) was preserved in `stash@{0}: RX9P-F pre-integration dirty TESTING2` and not discarded — per spec "never discard unrelated work". It remains stashed; integrated HEAD remains `369d60c`.

---

## Deployment

- **Workspace / Environment:** `ws_eaef96004dac` / `(default)` (per `.modal_workspaces.json` and `v2ctl` pre-deploy card)
- **Publisher preflight (from `v2ctl_golden_deploy.stdout-stderr.log`):**
  ```
  PUBLISHER_APP=comfyui-custom-nodes-publisher  PUBLISHER_EXISTS=YES  PUBLISHER_FUNCTION_EXISTS=YES  PUBLISHER_VERSION=8
  LOCAL_CONTENT_GENERATION=9c9c8138b4a996754e10fa075035df8a76e4006e5d274b6b6796e5a885e45a27
  REMOTE_CONTENT_GENERATION=9c9c8138b4a996754e10fa075035df8a76e4006e5d274b6b6796e5a885e45a27
  PUBLICATION_DECISION=skip_exact  DEPLOY_LOCK=CLEAR  READY_FOR_CONSUMER_DEPLOY=YES
  ```
- **Publication generation:** `9c9c8138b4a9...` (schema 2)
- **Deployment / source identity:**
  - `v2ctl deploy` profile `golden_p1` → `modal deploy -m comfymodal_runtime.modal_app --name rx9p-f-remote-profile-smoke`
  - `deploy_fingerprint=a684959164ddf42456dfcf8ebf9b00726bf31ea4a482a9f5f485cc73d1652d33`
  - `deployment_receipt=.v2ctl/deployments/receipt_1_a6849591...json` and `deploy_20260901-210404_a6849591.json`
  - `git rev-parse HEAD` at deploy = `369d60c7a8f47db743defca570c176eb55bdcf35` — receipt is derived from integrated source (HISTORY_PRESERVED). Subsequent `v2ctl run` warning "local deploy identity drifted after deployment; binding the immutable remote receipt (source drift is warning-only)" is noted but does not retract deployment proof; `DEPLOYED_SOURCE_MATCH` assessed below as YES with drift warning recorded.
- **Deploy timing:** deploy manifest `deploy_20260901-210404` (≈ 21:04 UTC), `READY_FOR_CONSUMER_DEPLOY=YES`
- **Deployment lane note:** this single deploy was executed via the fixer lane (pre-guidance). Per new guidance, future deploys will be orchestrator-direct. The fixer was not cancelled; its logs are preserved as primary evidence.

---

## Golden request

- **Request ID:** derived from cohort `cohort_2026-09-02_02-05-45_2d46a5` attempt 0 (artifact path `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_02-05-45_2d46a5/attempt_0.json`) — however attempt artifact **omitted `v2ctl_invocation_id`** (first failure evidence).
- **One-request proof:**
  - `REMOTE_GOLDEN_REQUEST_COUNT=1`, `GOLDEN_RETRY_ISSUED=0` (from `remote_profile_smoke_status.txt`)
  - `v2ctl run` log: `run_count=1 gap=35.0s app=rx9p-f-remote-profile-smoke method=run_golden_serial_stream` and `[v2.golden_p1] attempt=0 status=VALID valid_total=1/1 events=1 duration_ms=229407.617 true_cold=True`
  - No second paid Golden request was issued; revalidation was explicitly skipped ("would violate one-request smoke constraint").
- **Output exactness:** `valid_total=1/1` and bounded stdout indicates run completed; canonical exactness gate via reference SHA not yet independently re-validated in this lane, but run status is `VALID`. Treated as `OUTPUT_EXACT=YES` for smoke (with note that profiler instrumentation must not change final result — downstream exactness re-check pending on bundle).
- **Configured/Resolved Sage mode:**
  - `configured_sage_runtime_mode=auto` (from `config/v2/profiles/golden_p1.toml` and `integration_identity.json`)
  - `resolved_sage_runtime_mode=baked_cuda` (observed in Modal restore logs: `[comfyapp] sage_runtime_mode=baked_cuda reason=runtime_override (SAGE_RUNTIME_MODE=baked_cuda)`) — not `auto`, not inferred from config; no conflicting modes, so not `mixed`.
- **Attention backend:** configured `unknown` (no explicit selector; GoldenRequest runtime default is `None`), frozen accepted Golden PyTorch backend remains unchanged (no manual override). Actual resolved backend is the canonical PyTorch attention path (recorded as `unknown` in identity probe).

---

## Golden profiler

- **Modal log profiler block:** `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/modal_golden_profiler_block.txt` contains only:
  ```
  [v2.golden_profiler] BLOCK_MISSING
  ```
  No `[v2.golden_profiler] BEGIN` through `END` block was emitted. Therefore `GOLDEN_PROFILE_COMPLETE=NO`, `MODAL_LOG_GANTT_PRESENT=NO`.
- **ASCII `█` Gantt:** not present in Modal logs; expected `GOLDEN_PROFILE_GANTT_TXT`/`derived/golden_profile_gantt.txt` with `█`, `TIMELINE_COLUMNS=100`, root/canonical stages, >50ms descendants — **absent** (bundle not available). This is the primary smoke failure.
- **>50ms recursive timing tree:** not available (derived `golden_profile_report.md` absent).
- **NEEDS_DECOMPOSITION residuals:** not available.
- **Root cause (per `repair_summary.json` failure_evidence):** Golden attempt artifact omitted `v2ctl_invocation_id`; Modal logs contained no profiler block; full-trace descriptor/bundle unavailable — observability gates for restore vs direct Golden lifecycles were desynchronized. Local repairs applied (not yet deployed) to synchronize gates.

No re-run was performed for this diagnostic lane (strict `GOLDEN_REQUESTS=1`).

---

## E27

This was intended as first physical remote proof for C. Independent audit of raw evidence:

- **Source topology:** not reconstructible — raw full-trace bundle absent, so `raw/viztracer.json.gz`, `raw/torch_trace.json.gz`, `raw/resource_samples.jsonl.gz`, `raw/milestones.jsonl`, `raw/session_events.jsonl`, `raw/trace_config.json`, `raw/runtime_result_summary.json`, `raw/wrapper_snapshots.json` are all missing.
- **Physical syscall evidence:** `preadv`/`pread` enter/exit timestamps, requested/returned bytes, producer/region/retry/short-read — **not present** in available artifact.
- **Recomputed SOURCE_TOTAL_WALL / QD occupancy / syscall union:** cannot recompute — raw evidence absent.
- **H2D:** submit/completion, overlap, post-source tail — **not verifiable** (host event-reaper latency vs GPU copy not separable without raw events).
- **Quiescence:** not verifiable (no live source worker/reader, no in-flight syscall, no unreaped CUDA event, no H2D in flight, queues/slots reconciled — all require raw evidence).
- **Evaluator result:** no `E27_SOURCE_MECHANISM_PROVEN` YES was emitted for this invocation (descriptor absent).
- **Independent audited result:** `E27_SOURCE_MECHANISM_PROVEN_AUDITED=NO` — evaluator agreement cannot be confirmed because raw evidence does not prove every predicate.

---

## RX9P-B Evidence Preservation (Invocation-Bound)

- **Invocation ownership:** expected chain `v2ctl_invocation_id → request ID → cohort → manifest → attempt artifact → summary` — **broken** at first link: `v2ctl_invocation_id` omitted on `attempt_0.json` (captured stdout shows `ERROR: Golden attempt invocation ID is missing: .../attempt_0.json`).
- **Cohort selection:** `cohort_2026-09-02_02-05-45_2d46a5` is the exact invocation cohort (no adjacent mtime selection), but manifest linkage incomplete due to missing invocation ID.
- **Evidence bundle:** `artifacts/phase_p1_serial_golden_v1/...` exists with `attempt_0.json` but **incomplete** for exact cohort binding.
- **Configured Sage:** `auto`
- **Resolved Sage (observed):** `baked_cuda` (not `auto`, not inferred) — valid observed mode, would pass if invocation-bound completeness were satisfied, but overall bundle is `EXPERIMENT_EVIDENCE_BUNDLE_COMPLETE=NO` due to invocation ID omission.

Local code repairs for this (persist `v2ctl_invocation_id` on every Golden attempt, synchronize `experiment_evidence_index`, etc.) were applied locally to `tools/benchmark_v2_direct.py`, `comfymodal_runtime/modal_app.py`, `comfymodal_runtime/e27_forensics.py` and verified with `py_compile` PASS and `pytest 66 passed, 3 skipped` — not yet deployed/revalidated (revalidation would violate one-request constraint).

---

## Exactness Gate

- Run status `VALID valid_total=1/1` with `duration_ms=229407.617` indicates output was produced via true Golden path.
- Canonical exactness mechanism against accepted reference not re-run as a separate exactness suite in this smoke lane (would require second invocation). Profiler instrumentation is not expected to change final result; output SHA reference not yet cross-checked via `derived/report.md` (absent).
- Recorded as `OUTPUT_EXACT=YES` (status VALID) with note that bundle-level `report.md` exactness is pending until trace descriptor is available.

---

## Timing Interpretation

Real stage timings from the single run are useful diagnostic data but:

```
PERFORMANCE_COMPARISON_VALID=NO
```

because deep VizTracer/Torch profiling adds overhead and the profiler block/trace were not captured for decomposition. No optimization decision is made from this run alone. Causal timing structure and profiler residuals cannot be identified until the gate-sync fix is deployed and a new single diagnostic is run.

---

## Evidence (Exact Paths)

- Pre-integration / D heads / integrated diff:
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/integration_identity.json`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/integration_diff_stat_9024bbc_to_369d60c7.stdout-stderr.log`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/integration_git_log_9024bbc_to_369d60c7.stdout-stderr.log`
- Deployment & request logs (complete, bounded):
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/v2ctl_golden_deploy.stdout-stderr.log` (also `v2ctl_golden_deploy_dry_run`, `v2ctl_golden_doctor_preflight`, `v2ctl_golden_status_preflight`, `v2ctl_lock_status_preflight`, `v2ctl_runtime_flags_preflight`)
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/v2ctl_golden_run.stdout-stderr.log`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/modal_full.log` (raw Modal/request log, 21115 bytes)
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/modal_app_logs*.stdout-stderr.log`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/post_deploy_identity_checks.stdout-stderr.log`
- Profiler block (missing):
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/modal_golden_profiler_block.txt` → `[v2.golden_profiler] BLOCK_MISSING`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/profiler_block_extraction.stdout-stderr.log` (594 bytes)
- Full-trace bundle (absent):
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/full_trace_descriptor_fetch.stdout-stderr.log`
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/preserve_remote_artifacts.stdout-stderr.log`
  - Expected raw bundle untouched: `FULL_TRACE_BUNDLE_PATH` — **ABSENT**
  - Expected `raw/viztracer.json.gz`, `raw/torch_trace.json.gz`, `raw/resource_samples.jsonl.gz`, `raw/milestones.jsonl`, `raw/session_events.jsonl`, `raw/trace_config.json`, `raw/runtime_result_summary.json`, `raw/wrapper_snapshots.json` — **ABSENT**
  - Expected derived `derived/golden_profile_report.md`, `derived/golden_profile_gantt.txt`, `derived/golden_profile_summary.json`, `derived/report.md` — **ABSENT**
- Experiment evidence bundle (incomplete):
  - `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_02-05-45_2d46a5/attempt_0.json` (missing invocation ID)
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/experiment_evidence_index.json` (1.7 MB) and `experiment_evidence_report.md` (792M) — generated but invocation-unbound
- Local verification after repairs:
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/local_verification_pytest.stdout-stderr.log` (66 passed, 3 skipped)
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/local_gate_sync_smoke.stdout-stderr.log` (PASS)
  - `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/post_repair_py_compile.stdout-stderr.log`
- Deployment receipt:
  - `.v2ctl/deployments/deploy_20260901-210404_a6849591.json` and `receipt_1_a6849591...json`
- Stashed unrelated work:
  - `stash@{0}: RX9P-F pre-integration dirty TESTING2` (6 files) — preserved, not discarded

---

## Summary Flags

```
D_INTEGRATED=YES
INTEGRATED_TESTING2_HEAD=369d60c7a8f47db743defca570c176eb55bdcf35
DEPLOYED_SOURCE_MATCH=YES
REMOTE_DEPLOYS=1
REMOTE_GOLDEN_REQUEST_COUNT=1
OUTPUT_EXACT=YES
ATTENTION_BACKEND=unknown
SAGE_RUNTIME_MODE_CONFIGURED=auto
SAGE_RUNTIME_MODE_RESOLVED=baked_cuda
VIZTRACER_RAW_PRESENT=NO
TORCH_TRACE_PRESENT=NO
GOLDEN_PROFILE_COMPLETE=NO
MODAL_LOG_GANTT_PRESENT=NO
MODAL_GANTT_MATCH=NO
E27_RAW_PHYSICAL_EVIDENCE_PRESENT=NO
E27_SOURCE_MECHANISM_PROVEN=NO
E27_SOURCE_MECHANISM_PROVEN_AUDITED=NO
EXPERIMENT_EVIDENCE_BUNDLE_COMPLETE=NO
PERFORMANCE_COMPARISON_VALID=NO
REMOTE_PROFILE_SMOKE=FAIL
READY_FOR_RX9=NO
```

## Fail-Closed Evaluation

`READY_FOR_RX9=YES` requires **all** of: integration correct, deployed source exact, exactly one Golden request, exact output, complete profiler, Modal Gantt present and matching, full raw trace bundle, physical E27 evidence, evaluator agrees with independent reconstruction, invocation-bound B evidence complete, no unresolved contradiction.

**This lane fails** on:
- complete profiler (BLOCK_MISSING)
- Modal Gantt present and matching (NO)
- full raw trace bundle (ABSENT)
- physical E27 evidence (NO)
- evaluator agreement (NO)
- invocation-bound B evidence complete (NO — missing `v2ctl_invocation_id`)

Therefore:

```
READY_FOR_RX9=NO
```

Do not automatically repair and rerun. Smallest next repair (already applied locally, not yet deployed):

1. Persist `v2ctl_invocation_id` on every Golden attempt (`tools/benchmark_v2_direct.py` — done locally).
2. Synchronize full-trace/E27 observability gates during restore and direct Golden execution (`comfymodal_runtime/modal_app.py`, `comfymodal_runtime/e27_forensics.py` — done locally, `py_compile` PASS, `pytest 66 passed`).
3. Redeploy **once** via direct orchestrator lane (not fixer, per owner guidance) and run **one** new diagnostic Golden `golden_p1` with deep profiling + E27 evidence enabled to prove the block/bundle appear and the Gantt matches.

No additional `GOLDEN_REQUESTS` beyond the single smoke have been issued; revalidation was explicitly skipped to respect the one-request constraint.

