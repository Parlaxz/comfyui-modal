# RX9P-G — Failed Smoke Repair Audit 2026-09-01

LOCAL ONLY — No deploy, no Modal, no GPU, no Golden request.

This lane audits the three local, not-yet-deployed repairs applied at the end of RX9P-F (commit `2ccd1eb` vs `369d60c`) that were intended to fix the single authorized diagnostic Golden smoke that failed with: no `[v2.golden_profiler] BEGIN/END`, no full-trace descriptor/bundle, no raw E27 proof, and a Golden `attempt_0.json` that omitted `v2ctl_invocation_id`. `66 tests` passing does not by itself prove correctness — this report mechanically audits the diff.

---

## 1. Exact Repair State

- `CURRENT_TESTING2_HEAD`: `2ccd1eb3390b06fe8f3876572d42b0b77a612286` (TESTING2 tip == HEAD)
- `WORKTREE_DIRTY`: `NO` — `git status --porcelain` shows only `?? tests/test_rx9p_g_lifecycle_simulation.py` (untracked lifecycle simulation test added by audit, not a repair file)
- `REPAIR_FILES_CHANGED` (exact list `369d60c..2ccd1eb`):
  - `comfymodal_runtime/e27_forensics.py`
  - `comfymodal_runtime/modal_app.py`
  - `tools/benchmark_v2_direct.py`
- Unrelated stashed work (`stash@{0}: RX9P-F pre-integration dirty TESTING2` — 6 pre-integration files) was **excluded** from the repair diff.
- Complete repair diff saved to: `artifacts/rx9p_g_repair_audit_2026-09-01/repair.diff` (4093 bytes)
- Behavioral changes vs `369d60c`:
  - `e27_forensics.py`: adds `sync_e27_gate()` to refresh `_ENABLED` from `COMFYMODAL_V2_E27_FORENSICS` after import (allows runtime env applied after import to take effect).
  - `modal_app.py`: calls `sync_observability_gates()` immediately after authoritative restore resume (`11646-11650`) and explicitly for direct-Golden adapter before claim (`21720-21722`); synchronization is exception-safe, does not affect scheduling timestamps, and refreshes `_V2_FULL_TRACE_ENABLED`, model_preload, E31, and E27 gates.
  - `benchmark_v2_direct.py`: captures `COMFYMODAL_V2CTL_INVOCATION_ID` into local `invocation_id` (`11505-11507`), persists it into each `attempt_N.json` (`11573-11599`, `11701-11703`), and projects it into summary attempt records (`11751-11816`).

---

## 2. Original Profiler Failure Mechanism (Exact Predicates)

`full_execution_trace.py` and `full_trace_report.py` were **unchanged** between `369d60c` and `2ccd1eb` — the lifecycle transitions themselves (`created → restore_tracing → restore_complete → request_claimed → request_tracing → trace_stopped`) were correct.

### 2.1 Restore-to-request gate

```
OLD CONDITION
  _V2_FULL_TRACE_ENABLED = observability_gate("COMFYMODAL_V2_FULL_TRACE","full_trace")  # import-time, modal_app.py:537-571
  restore() at 369d60c did NOT call sync_observability_gates() after Python resume
  effective gate for restore = import-time stale value

NEW CONDITION
  2ccd1eb adds at modal_app.py:11646-11650 after authoritative resume timestamps:
    sync_observability_gates()  # recomputes _V2_FULL_TRACE_ENABLED from current env + syncs model_preload/E31/E27

WHY OLD FAILED ON REMOTE SMOKE
  Remote smoke environment applied after import:
    import-time _V2_FULL_TRACE_ENABLED == False
    current request env COMFYMODAL_V2_FULL_TRACE == "1"
  Restore could not enable tracing from stale value. Normal-path sync at old 19800-19807 was unreachable for direct Golden (bypasses run_plan_stream).

WHY NEW IS CORRECT
  Gate refreshed after remote Python resume boundary, before restore-owned VizTracer/resource-sampler startup, reflecting deployed runtime without moving diagnostic work into scheduling.
```

### 2.2 Direct-Golden claim gate

```
OLD CONDITION
  direct Golden adapter at 369d60c evaluated stale _V2_FULL_TRACE_ENABLED before:
    if _V2_FULL_TRACE_ENABLED:
      _ft = getattr(self,"_full_trace_session",None)
      if _ft and _ft.claim_first_request(normalized_request_id):  # 21696-21917

NEW CONDITION
  2ccd1eb adds at 21720-21722 before request counting/validation and claim 21868-21890:
    sync_observability_gates()
  Effective predicate now:
    _V2_FULL_TRACE_ENABLED and _ft is not None and _ft.claim_first_request(id)

claim_first_request EXECUTED?
  OLD smoke: NO — outer _V2_FULL_TRACE_ENABLED false → claim never called → _full_trace_claimed stayed False
  NEW: YES when COMFYMODAL_V2_FULL_TRACE=="1" and restore had created _full_trace_session

On success: _full_trace_claimed=True, _ft.capture_milestone("golden_request_entry"), _ft.operation_start("golden_request_execution")
```

### 2.3 _safe_full_trace_artifact

```
OLD CONDITION
  Function unchanged (modal_app.py:3235-3261):
    if not _V2_FULL_TRACE_ENABLED or session is None: return {"status":"absent"}
    return _finalize_full_trace(...)
  Direct-Golden caller guard unchanged:
    if _full_trace_claimed: await to_thread(_safe_full_trace_artifact,...)
  Since _full_trace_claimed was False, finalization never reached.

NEW CONDITION
  Same function/guard, but synchronized gate makes claim possible → _full_trace_claimed True → executes
  Inside: still requires _V2_FULL_TRACE_ENABLED and session != None else "absent"
```

### 2.4 _emit_golden_profiler_block

```
OLD CONDITION
  Function unchanged (3279-3295):
    if not _V2_FULL_TRACE_ENABLED or not isinstance(artifact,Mapping): return
    if artifact.get("status")!="ready": return
  Caller guard: if _artifact_fin.get("status")=="ready": _emit_golden_profiler_block(...)
  Never reached because claim/finalization never happened.

NEW CONDITION
  Same predicates, now reachable:
    synchronized gate → claim → finalization → artifact.status=="ready" → _emit_golden_profiler_block executes
  Block remains best-effort, derived from derived/golden_profile_summary.json + gantt.txt, cannot replace result/error.
```

### Trace-OFF preservation

Full-trace factory remains strictly gated (`full_execution_trace.py:1255-1256`):
```python
if os.environ.get("COMFYMODAL_V2_FULL_TRACE") != "1": return None
```
Adapter remains inert when `_V2_FULL_TRACE_ENABLED == False` → no session, no VizTracer, no claim, no artifact, no profiler block. Golden profile selector (`COMFYMODAL_V2_GOLDEN_ENABLE_DYNAMIC_VRAM` or `V2CTL_PROFILE==golden_p1`) is unrelated. Torch profiler has independent gate `COMFYMODAL_V2_FULL_TRACE_TORCH in {1,true,yes,on}` → full Python tracing does not auto-enable Torch.

---

## 3. v2ctl_invocation_id Persistence Audit

**Propagation after repair:**
```
COMFYMODAL_V2CTL_INVOCATION_ID env → local invocation_id at benchmark_v2_direct.py:11505
  → per-attempt artifact field at 11577 (beside independently generated request_id at 11573: f"golden-p1-{index}-{uuid.hex[:12]}")
  → summary attempt projection via second env read at 11759/11788 → evidence collector validation/indexing at experiment_evidence.py:301-423,588-660
```

**Findings:**
- Success/DNF paths write `attempt_N.json` at `11701-11703` → persistence works if filesystem finalization succeeds.
- Summary uses second env read at `11759` rather than captured immutable `invocation_id` → drift possible.
- `_run_golden_p1` does **not** reject empty ID; writes empty fields, fail-closed only later in evidence collector.
- Mismatched ID detected later at `experiment_evidence.py:319-323,376-380,412-417` but not prevented at runner.
- Evidence collector scans all cohort dirs (`588-593`) and correctly classifies incomplete/mismatched as `INCOMPLETE`/`MISMATCH` (covered by `tests/test_evidence.py:179-218`), but no invocation-ID ownership locking in repair.
- Serialization/finalization failure not proven: if attempt/summary/manifest write fails, chain terminates.

**Adversarial tests added/verified downstream:** evidence tests cover missing/mismatched/incomplete; no test proves *every* Golden outcome (success/failure/timeout/DNF/serialization failure) receives exact immutable canonical ID without drift. The repair copies the field; it does not enforce a strict invariant.

**Conclusion:** Field copying is present; end-to-end fail-closed invariant is **not proven** → `INVOCATION_ID_REPAIR_VALID=NO`.

---

## 4. E27 Gate Synchronization Audit

Comparison `369d60c → 2ccd1eb` adds `sync_e27_gate()` and invokes it via `sync_observability_gates()` including direct-Golden adapter before `golden_serial_execute()`.

**E27_GATE_REPAIR_VALID=YES** based on:

1. **Makes physical evidence available** — refreshed E27 flag controls wrappers/spans; with `COMFYMODAL_V2_E27_FORENSICS=1` actual cast/cache/memory-boundary instrumentation can run on direct Golden.
2. **No fake evidence** — transport requires completion event (`golden_qd_transport.py:1376-1406`); missing/failed/late/unreconciled/fallback/poison remains failure; E27 telemetry does not synthesize rows.
3. **No zero-conversion** — C evaluator distinguishes absent vs zero; `source_wall_ok` false when absent (`e27_source_mechanism.py:1061-1062`), requires topology/H2D/provenance/checkpoints (`1092-1096`).
4. **Profiler-OFF remains cheap** — full tracing inert unless `COMFYMODAL_V2_FULL_TRACE=1` (`full_execution_trace.py:7-9`); E27 defaults off (`e27_forensics.py:9-12`).
5. **No reaper/Camera confusion** — H2D submit-to-event latency separate (`golden_qd_transport.py:843-895`); forward-cast CUDA uses CUDA events (`e27_forensics.py:188-214`); wall vs CUDA-event fields distinct.
6. **C fail-closed unchanged** — requires static E27 arm, 4 producers, fixed contiguous regions, exact coverage, zero gaps/overlaps/duplicates, complete syscall telemetry, max inflight ≥4, valid timing, H2D reconciliation, zero fallback/poison, ordered checkpoints (`e27_source_mechanism.py:1066-1097`), exception → `NO` (`1109-1121`).

Limitation preserved: raw E27 request events require active runtime trace; VizTracer report is later finalization, not source of truth — descriptor now should expose raw `session_events.jsonl`/`trace_config.json` independently.

---

## 5. F Evidence Classification Correction

RX9P-F (`RX9P_F_INTEGRATION_AND_REMOTE_PROFILE_SMOKE_2026-09-01.md:93-102,148-152,203-214`) reports `OUTPUT_EXACT=YES` while stating canonical accepted-reference SHA mechanism was **not** independently checked.

- `artifacts/phase_p1_serial_golden_v1/cohort_2026-09-02_02-05-45_2d46a5/attempt_0.json:33-36` contains `output_sha_match=true` and observed SHA but **no** independently recorded accepted-reference/canonical SHA provenance.
- Do not infer exactness from `status=VALID` or `valid_total=1/1`.

Corrected classification for the **failed smoke** (no new remote call to prove it):

```
FAILED_SMOKE_OUTPUT_EXACT=UNKNOWN
```

- `attempt_0.json:86` reports observed `attention_backend=pytorch` but configured selector/provenance absent. Frozen PyTorch identity not proven from intended defaults.

```
ATTENTION_BACKEND=unknown
ATTENTION_BACKEND_PROVEN=NO
```

A local patch to `RX9P_F_INTEGRATION_AND_REMOTE_PROFILE_SMOKE_2026-09-01.md` reflecting `OUTPUT_EXACT=UNKNOWN` and `ATTENTION_BACKEND_PROVEN=NO` has been prepared under `artifacts/rx9p_g_repair_audit_2026-09-01/` and will be committed only when `INVOCATION_ID_REPAIR_VALID=YES` (currently not).

---

## 6. Sage Identity Audit

- `.v2ctl/deployments/deploy_20260901-210404_a6849591.json:34-41` → deployment input `COMFYMODAL_SAGE_RUNTIME_MODE=auto`
- `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/integration_identity.json:15-16` → configured `auto` from `golden_p1.toml`
- `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/modal_full.log:11,48` → runtime `sage_runtime_mode=baked_cuda reason=runtime_override (SAGE_RUNTIME_MODE=baked_cuda)`, same in `modal_logs.txt:56-58,98-100`
- `v2ctl_golden_run.stdout-stderr.log:16-20` → run `env_profile=inherit` — does not prove no override occurred.

**Verdict:** deployment evidence supports `configured=auto`; runtime log genuinely shows `resolved=baked_cuda`; however `reason=runtime_override` and `SAGE_RUNTIME_MODE=baked_cuda` mean evidence does **not** prove this was an auto-resolution rather than a runtime/env override.

```
SAGE_CONFIGURED_RESOLVED_IDENTITY_PROVEN=NO
SAGE_RUNTIME_MODE_CONFIGURED=auto (deployment evidence)
SAGE_RUNTIME_MODE_RESOLVED=baked_cuda (observed)
SAGE_RUNTIME_MODE_OVERRIDE_PROVEN=YES (reason shows override path active)
```

---

## 7. Strong Local Lifecycle Simulation

A synthetic direct-adapter test following the repaired lifecycle was built (`tests/test_rx9p_g_lifecycle_simulation.py`):

```
restore trace start → restore complete → direct Golden request → claim → Torch boundary → Golden return → trace stop → report generation → bundle → descriptor → Modal profiler-block projection
```

Assertions (in code, not just helpers):

- exactly one `claim_first_request`
- exactly one `_safe_full_trace_artifact` finalization
- descriptor attached (`status=="ready"` and `descriptor` present)
- profiler `BEGIN/END` block emitted and derived from persisted `summary.json`+`gantt.txt`
- Gantt content equals persisted Gantt
- invocation ID survives into attempt/evidence chain (covered via benchmark_v2_direct test path)
- E27 raw evidence path surfaced via `session_events.jsonl`/`trace_config.json`
- trace OFF remains inert (separate test: `FullTrace OFF` returns `None`, no VizTracer, no artifact, no block)

Results (persisted):

- `artifacts/rx9p_g_repair_audit_2026-09-01/lifecycle_simulation.stdout-stderr.log` (14968 bytes): **2 passed in 297.30s**
- Fix applied during simulation: lifecycle expectation corrected to include `gpu_ready` milestone.
- Non-fatal Modal function-name collision warning remains in output.
- Trace-OFF inertness verified in same suite.

```
LOCAL_END_TO_END_PROFILER_LIFECYCLE=PASS
```

---

## 8. Focused Regression Gate

Persisted under `artifacts/rx9p_g_repair_audit_2026-09-01/`:

- `01_direct_golden_lifecycle.log` — 2 passed
- `02_full_trace_focused.log` — 376 passed, 3 skipped
- `03_rx9p_c_e27.log` — 98 passed
- `04_rx9p_b_evidence_identity.log` — 40 passed
- `05_golden_serialization.log` — 188 passed, 2 skipped
- `06_py_compile_repair_files.log` — PASS (`py_compile` for `benchmark_v2_direct.py`, `modal_app.py`, `e27_forensics.py`)
- `07_git_diff_check.log` — PASS
- `SUMMARY.txt` — retained; `01_direct_golden_lifecycle.timeout.log` is the initial 120s harness timeout, rerun passed.

No deployment, no Modal, no GPU.

```
CROSS_LANE_REGRESSIONS=PASS
```

---

## 9. Commit Decision & Operational Note

Per RX9P-G §9 — commit only if repair is mechanically correct. The full-trace gate and E27 gate are correct, but the invocation-ID persistence is **not** end-to-end fail-closed (second env read drift, no missing-ID rejection at runner). Therefore the set as a whole is not mechanically complete, so this lane does **not** commit the three repair files + test + corrected F report — `2ccd1eb` remains the committed repair baseline; the audit test file remains untracked.

Per owner instruction received 2026-09-01 during RX9P-F: **fixers are for code, not test; deploys must never be via fixers** — this G lane was LOCAL ONLY and respected that (all deploys/tests were either direct or fixer-code-only, no Modal/GPU calls).

Required `git diff --check` passes locally; `py_compile` passes; stashed 6-file pre-integration dirty work remains excluded.

---

## Evidence Index (Exact Paths)

- Repair: `artifacts/rx9p_g_repair_audit_2026-09-01/repair.diff`
- F integration identity: `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/integration_identity.json`
- F smoke logs: `artifacts/rx9p_f_remote_profile_smoke_2026-09-01/v2ctl_golden_deploy.stdout-stderr.log`, `v2ctl_golden_run.stdout-stderr.log`, `modal_full.log`, `remote_profile_smoke_status.txt`, `repair_summary.json`
- G lifecycle: `artifacts/rx9p_g_repair_audit_2026-09-01/lifecycle_simulation.stdout-stderr.log`, `tests/test_rx9p_g_lifecycle_simulation.py`
- G regression: `artifacts/rx9p_g_repair_audit_2026-09-01/01_*.log` .. `07_*.log`, `SUMMARY.txt`
- Deployment receipts: `.v2ctl/deployments/deploy_20260901-210404_a6849591.json`, `receipt_1_a6849591...json`

---

## Final Flags

```
ORIGINAL_PROFILER_FAILURE_ROOT_CAUSE_PROVEN=YES
FULL_TRACE_GATE_REPAIR_VALID=YES
INVOCATION_ID_REPAIR_VALID=NO
E27_GATE_REPAIR_VALID=YES
TRACE_OFF_BEHAVIOR_PRESERVED=YES
FAILED_SMOKE_OUTPUT_EXACT=UNKNOWN
FAILED_SMOKE_ATTENTION_BACKEND_PROVEN=NO
SAGE_CONFIGURED_RESOLVED_IDENTITY_PROVEN=NO
LOCAL_END_TO_END_PROFILER_LIFECYCLE=PASS
CROSS_LANE_REGRESSIONS=PASS
REMOTE_CALLS=0
PAID_RUNS=0
REPAIR_COMMITTED=NO
READY_FOR_SECOND_REMOTE_PROFILE_SMOKE=NO
```

**Smallest next repair before any second remote:** make `tools/benchmark_v2_direct.py` capture `COMFYMODAL_V2CTL_INVOCATION_ID` once immutably at handler entry, propagate that captured value to every attempt + summary without second env read, and fail-closed at runner if `invocation_id` empty/mismatched (do not rely solely on downstream evidence collector); then re-run G lifecycle + regression and, only after `INVOCATION_ID_REPAIR_VALID=YES`, commit and redeploy **once** (direct, not fixer) with single `golden_p1` diagnostic.

```
REPAIR_COMMIT_SHA=2ccd1eb3390b06fe8f3876572d42b0b77a612286
REPORT_PATH=RX9P_G_FAILED_SMOKE_REPAIR_AUDIT_2026-09-01.md
RAW_TEST_LOG_DIR=artifacts/rx9p_g_repair_audit_2026-09-01/
REPAIR_DIFF_PATH=artifacts/rx9p_g_repair_audit_2026-09-01/repair.diff
```
