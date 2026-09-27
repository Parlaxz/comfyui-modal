# PHASE H12 — V2-ONLY EXECUTION CONSOLIDATION, V1/SHADOW RETIREMENT & SETTINGS CLEANUP (2026-08-24)

**Batch type:** H-Wave C implementation. No deploy, no Modal/GPU/live generation, no commit/push/branch/worktree/reset. Shared tree intentionally dirty (H13 Wave D ran concurrently; disjoint file sets respected — zero H13-owned files touched).
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` (§3/§4/§5/§6/§11/§12/§13/§25 C/E sequencing rule + Follow-Ups A/B), `PHASE_H2_RUN_MODE_SETTINGS_AUTHORITY_AUDIT_2026-08-23.md` (Option C, §12 migration design, §16 seams), `PHASE_H5B_WAVE_B_CONVERGENCE_2026-08-24.md` (FB-6 ownership map, FB-7 baseline 1941/21/199).

## VERDICT

`H12 COMPLETE — MODERN STUDIO EXECUTION IS MODAL V2 ONLY.`

Final executable-mode vocabulary: **`{v2}`** — the only mode any resolver path can produce and the only engine any NEW modern request can execute.

---

## 1. PRE-CHANGE EXECUTION CALL GRAPH (verified before edits)

```
POST /comfymodal/studio/run            → handle_studio_run_async
    resolved v2      → playground_adapter_direct_run → PlaygroundService → ExecutionPlan → ModalTransport (V2)
    resolved v1      → _prepare_studio_run_context → direct_studio_run_completion → execute_modal_prompt → run_prompt_stream (V1)
    resolved shadow  → same V1 executor + _record_shadow_plan_comparison (V2 plan built for comparison only)
POST /comfymodal/studio/run (workflow) → handle_workflow_run_async
    MODE_V2          → _workflow_v2_run → PlaygroundService (V2)
    otherwise        → _workflow_legacy_run → submission-time history ("execution_mode":"v1" @ studio_workflow_run.py:1556) → direct_studio_run_completion (V1)
POST /comfymodal/studio/experiment     → handle_studio_experiment → _schedule_and_start
    resolved v2      → V2ExperimentInvoker
    otherwise        → LocalRemoteInvoker → modal_client.run_prompt_stream (V1)
POST /comfymodal/prompt (canvas Cloud) → capture_execution_mode → queue → _execute_job
    v2/shadow        → build_execution_plan → execute_plan (V2; shadow printed a comparison line)
    v1               → execute_modal_prompt (V1)
POST /comfymodal/config                → validate_config_payload accepted {v1,v2}, rejected shadow
COMFYMODAL_RUNTIME env                 → accepted {v1,legacy,v2,shadow} via _LEGACY_ALIASES
Persisted .modal_settings.json         → normalize_mode kept v1/v2 in memory; no rewrite, no notice
AVAILABLE_EXECUTION_MODES              → [{v2},{v1}] advertised to both Settings surfaces
Settings S1 Run mode                   → wrote/reset comfymodal_enabled (zero modern consumers)
Settings S2 Engine select + legacy twin→ POST execution_mode to /config
Comparison /comfymodal/comparison/run  → run_prompt_stream directly (V1) — FROZEN seam
Warmup /deploy-warmup/run              → run_prompt_stream directly (V1-bound; FA-3 RETIRE verdict, untouched lane)
```

## 2. POST-CHANGE EXECUTION CALL GRAPH

```
POST /comfymodal/studio/run            → handle_studio_run_async
    retired request   → 400 EXECUTION_MODE_RETIRED (before GPU capture/history/acceptance)
    else (always v2)  → playground_adapter_direct_run → PlaygroundService → immutable ExecutionPlan → ModalTransport
    direct=False only → scheduler path (legacy flow, now unconditionally V2 invoker)
POST /comfymodal/studio/run (workflow) → handle_workflow_run_async
    retired request   → 400-shaped error dict EXECUTION_MODE_RETIRED (bundle gate still precedes mode guard)
    else (always v2)  → _workflow_v2_run → PlaygroundService (immutable plan)
POST /comfymodal/studio/experiment     → handle_studio_experiment
    retired request   → error EXECUTION_MODE_RETIRED before preset load/scheduler
    else              → _schedule_and_start → V2ExperimentInvoker (unconditional)
POST /comfymodal/prompt (canvas Cloud) → retired_request_mode guard at acceptance (400) → capture (v2) → build_execution_plan → execute_plan (V2 ONLY)
GET  /comfymodal/config                → execution_mode=v2 (+source/locked) · engine_migration_notice · NO available_execution_modes · NO execution_readiness
POST /comfymodal/config                → accepts v2 only; rejects v1/legacy/shadow with 400; env-lock 409 only for literal COMFYMODAL_RUNTIME=v2
COMFYMODAL_RUNTIME env                 → vocabulary collapsed to {v2}; v1/legacy/shadow logged-and-refused → fall through (only v2 reachable)
Persisted settings                     → _migrate_persisted_execution_mode rewrites retired/garbage → "v2" ONCE + notice; _save_modal_settings can never persist non-v2
Comparison /comfymodal/comparison/run  → run_prompt_stream directly (UNCHANGED frozen seam)
Modern Settings                        → no Run mode, no engine selector; GPU sole execution preference; Reset All POSTs {gpu} only
Legacy overlay                         → canvas Cloud/Local toggle preserved; engine subsection = non-interactive "V2 - the only execution engine"
```

## 3. V1 BRANCH DELETION LEDGER

| Removed | Location (pre-edit) | Evidence |
|---|---|---|
| Single non-V2 branch (`direct_studio_run_completion` call + shadow comparison hooks) | `studio_run_adapter.py:3968–3994` | handler source contains neither call form; `handle_studio_run_async` always routes `playground_adapter_direct_run` |
| `_record_shadow_plan_comparison` | `studio_run_adapter.py:1913–1952` | function deleted; zero callers |
| Mode-selected `LocalRemoteInvoker` registration in `_schedule_and_start` | `studio_run_adapter.py:2586–2621` | scheduler source registers `V2ExperimentInvoker(` only; `LocalRemoteInvoker(` absent; `from experiment_runner import LocalRemoteInvoker` import removed |
| `_workflow_legacy_run` + `_async_noop_profile_preparer` + hardcoded `"execution_mode": "v1"` metadata pair | `studio_workflow_run.py:1407–1626` (incl. :1556) | 8,604 chars removed in one block; `def _workflow_legacy_run` absent; dispatch is unconditional `_workflow_v2_run` |
| Canvas v1/shadow dispatch (`if _mode in {"v2","shadow"}` + `else: execute_modal_prompt`) | `__init__.py:2494–2581` | unconditional plan build + `execute_plan`; `result = await execute_modal_prompt(` absent from file; `execute_modal_prompt` removed from `__init__.py` imports |
| Shadow branch in canvas metadata extraction | `__init__.py:2598` | `elif _v2_plan is not None:` |
| `AVAILABLE_EXECUTION_MODES` constant + `/config` fields `available_execution_modes`, `execution_readiness` | `execution_runtime.py:42–45`, `__init__.py:4640–4668` | constant gone from module; GET payload asserts absence (tests 11/16) |
| `/config` acceptance of v1 | `validate_config_payload` | v1/legacy/shadow all rejected 400 |
| Modern Settings S1 Run mode control + `comfymodal_enabled` in `MODERN_SETTINGS_KEYS`/resets | `web/studio-settings.js:45–46,274,409–438` | testids `settings-run-mode*` absent from source; key string absent from file |
| Modern Settings S2 engine selector/status/readiness + "V1 engine remains available" copy | `web/studio-settings.js:448–466,484,722–809` | testids absent; `refreshEngineConfig` deleted; `_executionModeListener` deleted |
| Legacy overlay V1/V2 `<select>` + readiness line + engine POST | `web/modal-settings.js:1548–1623` | replaced by non-interactive truthful status; no select element, no POST |
| Reset All / Generation reset engine forcing (`execution_mode:"v2"` POST) | `web/studio-settings.js:287,345` | reset POSTs are `{gpu}` only; disclosure copy updated in the same change |

## 4. EXACT RETAINED COMPARISON LEGACY-EXECUTOR SEAM (frozen C/E sequencing)

- `POST /comfymodal/comparison/run` → `_execute_comparison_profile` → `async for _msg in run_prompt_stream(...)` (`__init__.py`, comparison route family). **Unchanged.**
- `direct_studio_run_completion` + `execute_modal_prompt` remain defined (canonical_execution/studio_run_adapter) but have **zero production callers** after H12 (proven by `test_19`; they are Wave-G dead-code residue kept because registered suites `test_studio_direct_run` still exercise them).
- `experiment_runner.LocalRemoteInvoker` class retained as dead production code (Wave G deletes); its last production registration was removed. Import of `LocalRemoteInvoker` dropped from `__init__.py:5775`.
- Warmup `run_prompt_stream` use untouched (FA-3 separate verdict, not an execution MODE).

## 5. SHADOW RETIREMENT PROOF

- No dispatch branch selects shadow anywhere: `"shadow"` appears in production code only as (a) recognition constants/aliases in `execution_runtime.py`, (b) the default V2 app-name string `stable-modal-comfy-v2-shadow` (deployment identity label, unrelated), (c) rejection messages.
- `COMFYMODAL_RUNTIME=shadow` → logged refused → resolves v2 (test: `test_env_shadow_refused`).
- Explicit request `shadow` → surfaced `retired=True` → rejected at every dispatch site (tests 15/16/17 + workflow test_11).
- Persisted `shadow` → migrated to v2 on disk (migration test_5). No shadow UI/config path exists.

## 6. COMFYMODAL_RUNTIME FINAL SEMANTICS

Mechanism preserved (precedence request-captured > env > persisted > default; locked=True when env resolves):
- `v2` → locked V2.
- `v1` / `legacy` / `shadow` → warning log "retired and refused" → falls through → v2 (never returns a retired engine).
- garbage → existing warn-and-ignore → default v2.
- Env can never lock or activate a retired engine; a captured request still wins over env for its own immutability (unchanged Phase-8 semantics).

## 7. EXPLICIT REQUEST-CAPTURED RETIRED MODES

Every public carrier audited: `modal_options.execution_mode` on `/studio/run` (Single+Workflow), `/studio/experiment`, `/comfymodal/prompt`, plus `extra`/trace-captured values. Behavior:
- Resolver surfaces explicit retired requests with `mode=<v1|shadow>, retired=true` — never silently relabeled V2.
- Dispatchers reject BEFORE acceptance/GPU-freeze/history: Single & Experiment return `{"status":"error","error_code":"EXECUTION_MODE_RETIRED"}` (route → HTTP 400); Workflow returns the same error dict; canvas returns HTTP 400 JSON `{"error":"execution_mode_retired"}` pre-enqueue.
- `capture_execution_mode` raises as a defensive backstop if ever called on a retired request.
- Persisted old configuration is a DIFFERENT case → §8 migration (no 400 for stale settings; they migrate).

## 8. PERSISTED MIGRATION DESIGN + EVIDENCE

`_migrate_persisted_execution_mode(merged)` runs inside `_load_modal_settings` (first load per process):
- Recognizes via `normalize_mode` (v1/legacy/shadow/garbage); rewrites merged value AND the `.modal_settings.json` file atomically (tmp+os.replace) in the same call — no recursion into `_save_modal_settings`.
- Idempotent: exact `"v2"` early-returns; second startup finds clean value → no notice (test_6).
- One-time notice: module global `_EXECUTION_MODE_MIGRATION_NOTICE = "Engine V1 retired; future runs use V2."`, logged via print, surfaced on GET `/config` as `engine_migration_notice`, rendered in modern Settings Generation section (`settings-engine-migration-notice`). Process-lifetime; disappears after restart (truthful — nothing left to disclose).
- Unknown invalid values safely normalize to v2 with the same surfacing (test_4).
- In-flight/accepted objects never rewritten (capture-at-acceptance untouched); `comfymodal_enabled` never mapped (test_10); env-lock precedence truthful (test_8); `_save_modal_settings` hard-coerces any non-v2 to v2 so retirement is write-proof (test_9).
- History records untouched: migration applies only to CURRENT persisted Settings; no historical `execution_mode` metadata rewritten.

## 9. SETTINGS CLEANUP

- Modern Settings: General section keeps nav info row only (Run mode removed; no reset button — nothing resettable). Generation keeps GPU + Preview default (+ conditional migration notice); engine selector/status/readiness and "V1 fallback" copy deleted. `MODERN_SETTINGS_KEYS` no longer contains the canvas run-mode key; no writer/resetter remains in the file (F4 unit 1b pins this while pinning `window._comfyModalEnabled` survival in `modal-node.js`).
- Legacy overlay (`modal-settings.js`, scoped edit): canvas Cloud/Local toggle PRESERVED (still drives the compatibility key + `updateModalSections`); engine subsection is now a truthful non-interactive "V2 - the only execution engine" status (locked variant: "Managed by COMFYMODAL_RUNTIME (V2)"). No broad refactor; outputs/GPU/workspace sections untouched.
- No portability target (`local/modal/runpod/runcomfy/comfy_cloud/baseten`) appears as selectable execution anything anywhere (naming guards intact).

## 10. RESET ALL CLEANUP

- KEEP: GPU reset to canonical catalog default via server POST; output defaults via shared module; Preview reset; History columns; interface keys; tracing → off (F4A persisted-vs-effective rules); durable namespaces preserved.
- REMOVE: engine forcing — POST body is exactly `{gpu: <default>}`; confirmation + footer disclosure updated in the SAME change (no sentence claims an engine reset anymore).
- NOT reset: workspace/deployment/credentials/portability/History durable records (never were; unchanged).

## 11. CANVAS COMPATIBILITY PRESERVATION

`/prompt` interception, Local pass-through gate (`comfymodal_enabled` / `window._comfyModalEnabled` — consumer intact in `modal-node.js`), output-options chain, Production-mode marking, and canvas compatibility data are untouched. Only the Cloud-side ENGINE dispatch changed: Cloud Modal execution is now V2-only with a 400 guard for retired selections. Local was never a Studio mode and remains canvas-only.

## 12. GPU INVARIANT EVIDENCE (F8 — no regression)

- `resolve_request_gpu` precedence and plan freezing untouched; replay/resume/retry paths unchanged (zero edits in that chain).
- `tests.test_f8_gpu_authority`: 41/41 green, including partial-save preservation (now pinned with v2 since v1 POSTs are rejected) and a new retired-engine-rejection test proving GPU semantics survive alongside the 400s.
- `studio_phase_f8_gpu_reset_unit.mjs`: ALL sections PASS (GPU-only reset POSTs, truthful disclosure, legacy panel single-POST contract).

## 13. HISTORY INVARIANT EVIDENCE

- No changes to replay semantics, `execution_plan_json` authority, replay-capability projection, workspace fallback, or legacy-row irreproducibility.
- Migration touches only current Settings; historical rows keep their original `execution_mode` metadata (nothing in the diff writes to history stores).
- New modern runs cannot produce V1-style irreproducible records: every entry surface rejects retired engines pre-acceptance (workflow tests 06/11 prove zero history records are created for rejected requests; phase8/h12 adapter proofs prove no executor is reached).

## 14. TEST EVIDENCE (exact counts)

Focused (this lane):
- `tests/test_phase8_execution_mode.py` (rewritten): included below.
- `tests/test_h12_v2_only_consolidation.py` (new): included below.
- Combined run: **62/62 OK** (phase8 + h12).
- `tests.test_f8_gpu_authority`: **41/41 OK**.
- `tests.test_workflow_run_integration`: **25/25 OK** (gate order; includes rewritten test_06 retired-v1 rejection and new test_11 retired-shadow rejection).
- `tests.test_f8_gpu_authority + tests.test_workflow_run_integration` (gate order): **66/66 OK**.
- `tests.test_studio_backend + tests.test_studio_direct_run + tests.test_studio_runtime`: **557/557 OK**.
- Node: `studio_phase_f4_settings_authority_unit.mjs` (15 sections incl. new 1b/9b/9c) and `studio_phase_f8_gpu_reset_unit.mjs` — **PASS**.

Full gate (`python tests/run_studio_tests.py --fake`, measured on the converged shared tree with H13's concurrent edits present):

```
python             run=1945  fail=0    error=0    skip=0
node-unit          run=21    fail=0    error=0    skip=0
fake-playwright    PASS      211 passed / 211 (npm wrapper aggregate; direct npx count)
```

Baseline was 1941/21/199; deltas (+4 python, +12 fake) originate from this lane's in-gate additions (+2: f8 retired-rejection, backend GPU/preview-remain) plus concurrent H13/shared-tree additions — all green either way. NOTE: running `test_f8_gpu_authority` BEFORE `test_workflow_run_integration` (reverse of gate registration order) trips a pre-existing cross-module isolation artifact (`history_v2_writer` singleton leaking a real DB into the fake-service finalization check). Not an H12 regression; flagged for Wave-G L-TST.

Out-of-gate debt (Wave G L-TST): `tests/test_phase8_execution_mode.py` and `tests/test_h12_v2_only_consolidation.py` are focused-run only — `tests/run_studio_tests.py` was off-limits to H12 (registration prohibited by batch constraints).

## 15. REMAINING WAVE-E LEGACY EXECUTOR RESIDUE

Until Wave E retires Comparison UI: `/comparison/run` → `run_prompt_stream` stays. Dead-but-defined residue for Wave G: `direct_studio_run_completion`, `execute_modal_prompt` (canonical_execution export), `experiment_runner.LocalRemoteInvoker` (+ its dedicated test files), `_prepare_studio_run_context`/`_handle_studio_run_scheduler` (reachable only via `direct=False`, which no production caller passes), `_playground_runtime_mode`. None is reachable by any NEW modern request.

## FILES MODIFIED BY THIS LANE

Production: `execution_runtime.py`, `__init__.py`, `studio_run_adapter.py`, `studio_workflow_run.py`, `web/studio-settings.js`, `web/modal-settings.js`.
Tests: `tests/test_phase8_execution_mode.py` (rewritten), `tests/test_h12_v2_only_consolidation.py` (new), `tests/test_f8_gpu_authority.py`, `tests/test_workflow_run_integration.py`, `tests/test_studio_backend.py`, `tests/studio_phase_f4_settings_authority_unit.mjs`, `tests/studio_phase_f8_gpu_reset_unit.mjs`.
Report: this document. H13-owned files touched: NONE. Shared fakes edited: NONE.

Deploy / live / GPU / generation / commit / push by this batch: **NONE**.
