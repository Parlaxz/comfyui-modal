# PHASE H11 — DEAD EXECUTION-MODE HELPER RETIREMENT (2026-08-24)

**Batch type:** H-Wave B implementation lane (small). Dead-code deletion only.
**Authority:** `PHASE_H5_CONSOLIDATION_CONTRACT_FREEZE_2026-08-23.md` §6 ("`is_v2()`/`is_shadow()` dead helpers are removed in Wave B (zero callers, H1-verified); their removal does not change resolver behavior") and §20 Wave-B safe retirement set. Inputs read: H5 freeze (complete), H1 audit (`is_v2`/`is_shadow` = RETIRE dead code, zero consumers, H1 §10 table + §96 dispatch finding), H2 audit (no is_v2/is_shadow references; resolver authority unchanged).
**Scope discipline:** V1 NOT retired; shadow runtime behavior NOT retired; `resolve_execution_mode`, aliases, `COMFYMODAL_RUNTIME`, `/config`, dispatch, Settings, execution selectors, Comparison — all untouched (Wave C/E ownership).

---

## 1. CALLER SEARCH (re-proof of zero callers)

Repo-wide search for `is_v2` / `is_shadow` (covers direct calls, imported aliases, module-qualified use):

| Match | Classification |
|---|---|
| `execution_runtime.py:149` `def is_v2(...)` | definition |
| `execution_runtime.py:155` `def is_shadow(...)` | definition |
| `comfymodal_runtime/gpu_snapshot_shadow.py:1655–1780` | documentation/dict-keys only (`"is_shadow_unet"` etc.) — unrelated snapshot payload keys |
| `tests/test_phase8_execution_mode.py:68` `test_default_is_v2` | test method NAME (asserts default resolution is v2 via `resolve_execution_mode`) — does not call the helper |
| `tests/test_image_packaging_refactor.py:379`, `tests/test_v2_execution_seed.py:91` | unrelated test method names (`schema_version_is_v2`) |
| `PHASE_H1/H5*.md` | documentation |

Import-site audit (all importers of `execution_runtime`):
- `__init__.py:143` imports MODE_V1/MODE_V2/MODE_SHADOW/resolve_execution_mode/normalize_mode/capture_execution_mode/validate_config_payload/AVAILABLE_EXECUTION_MODES — **no helper**
- `studio_run_adapter.py:78,1908,2533,3934` — resolve_execution_mode/MODE_V2 only
- `studio_workflow_run.py:1677` — MODE_V2/resolve_execution_mode only
- `tests/test_phase8_execution_mode.py:31` — no helper

**Verdict: zero production callers, zero test callers, zero alias imports for both helpers.** Matches H1/H5 exactly. Both removals proceed.

## 2. DELETED DEFINITIONS

`execution_runtime.py` — removed both convenience wrappers verbatim (12 lines):

```diff
-def is_v2(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> bool:
-    """Convenience: return True if resolved mode is v2 or shadow."""
-    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
-    return resolved["mode"] in (MODE_V2, MODE_SHADOW)
-
-
-def is_shadow(modal_options: dict | None = None, *, extra: dict | None = None, modal_settings: dict | None = None) -> bool:
-    """Convenience: return True if resolved mode is shadow."""
-    resolved = resolve_execution_mode(modal_options=modal_options, extra=extra, modal_settings=modal_settings)
-    return resolved["mode"] == MODE_SHADOW
-
-
 def validate_config_payload(payload: dict) -> str | None:
```

`git diff --stat`: `execution_runtime.py | 12 ------------` — the ONLY change by this lane.

## 3. EXPORT SURFACE

Module has **no `__all__`** and no explicit export list → nothing to change. No reordering performed.

## 4. TESTS CHANGED

**None.** No test called or imported either helper (proven in §1); all live-behavior tests (v1/v2/shadow resolution, env precedence, persisted mode, request-captured mode, invalid mode, config rejection) remain intact and passing. Nothing weakened, nothing deleted.

## 5. STRUCTURAL PROOF (post-edit)

- Repo-wide grep `def is_v2|def is_shadow`: **zero matches** (excluding phase-doc prose).
- Runtime attribute check: `import execution_runtime; hasattr(...,'is_v2'/'is_shadow')` → both absent; module imports cleanly.
- Resolver semantics intact in `execution_runtime.py`: `normalize_mode` (:48), `_get_os_env_mode` reading `COMFYMODAL_RUNTIME` with logged-and-ignored unrecognized values (:59–68), `_get_persisted_mode` (:71), `_get_request_mode` (:79), `resolve_execution_mode` precedence request > env(locked) > persisted > default-v2 (:94–146), `_LEGACY_ALIASES` {legacy,v1,v2,shadow} (:31–36), `MODE_V1/MODE_V2/MODE_SHADOW` constants, `validate_config_payload` shadow-rejection (:161), `capture_execution_mode`. Zero edits to any of these (diff touches only the two deleted functions).
- Env-lock behavior unchanged: env override still wins over persisted/request-less resolution and still sets `locked=True`.

## 6. FOCUSED TESTS

- `python -m pytest tests/test_phase8_execution_mode.py -q` → **30 passed** (semantic count unchanged; suite never referenced the dead helpers).
- Adjacent execution-path suites: `test_workflow_run_integration.py` + `test_studio_workflow_run_plan_identity.py` → 30 passed, 1 failed.
  - The single failure (`test_production_preserves_validation_and_all_canonical_fields`: `meta["selected_gpu"] '' != 'gpu_test'`) is **concurrent-ownership territory**: `studio_workflow_run.py` (+47), `studio_workflow_routes.py` (+232), and that test file (+66) carry large uncommitted modifications from concurrently running H9/H10 lanes; `execution_runtime.py` contains zero `selected_gpu` references and this lane's diff cannot reach plan metadata. Not caused by H11; left to owning lanes.

## 7. FULL GATE

`python tests/run_studio_tests.py --fake`:

```
STUDIO GATE SUMMARY
  python             run=1991  fail=0    error=0    skip=0
  node-unit          run=21    fail=0    error=0    skip=0
  fake-playwright    run=1     fail=0    error=0    skip=0
ALL STUDIO LANES GREEN
```

Python 1991 = baseline exactly; Node 21 = baseline exactly; fake lane green (runner reports the Playwright invocation as a single aggregate run; zero failures — no frontend/fake deltas from this lane).

## 8. VERDICT

`H11 COMPLETE — DEAD EXECUTION HELPERS RETIRED, RESOLVER SEMANTICS UNCHANGED.`

Files modified by THIS lane: `execution_runtime.py` (−12 lines), this document.

Deploy / Modal / GPU / live generation / commit / push / branch / worktree / reset / stash / clean: **NONE**.
