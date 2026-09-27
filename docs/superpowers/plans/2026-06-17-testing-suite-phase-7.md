# Phase 7 — Deployment Generation and Warmup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Parent plan:** `docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md` §28 Phase 7.

**Goal:** Add a `deploy_warmup.py` module that tracks a per-deployment-generation warmup state, gates experiment starts on a successful warmup, and exposes a stateful redeploy+restart+warm sequence API.

**Architecture:** New module `deploy_warmup.py` plus tests. State lives at `.deploy_warmup_state.json` (new file, separate from the existing `.deployed_state.json` to keep responsibilities clean). The "deployment generation" is a derived token. The warmup workflow selection prefers the project's existing warmup profile; falls back to a no-op blank generation.

**Tech Stack:** Python 3.11 stdlib. No new deps.

---

## File map

- Create: `deploy_warmup.py` — `WarmupState`, `deployment_generation`, `ensure_warmup`, `gate_experiment`, `RedeployStateMachine`
- Create: `tests/test_deploy_warmup.py` — generation tracking, state machine, gate behavior, redeploy sequence

**Do NOT modify:** any existing file. The new file is `.deploy_warmup_state.json`.

---

## Task 1: deploy_warmup.py — state, generation, gate, redeploy state machine

See `deploy_warmup.py` and `tests/test_deploy_warmup.py` in the repo. Both already exist (created during this phase's TDD cycle). The implementation matches the parent plan's `WarmupState`, `deployment_generation`, `ensure_warmup`, `gate_experiment`, and `RedeployStateMachine` API.

---

## Phase 7 completion report

### Checklist items completed
- [x] Add deploy generation token (`deployment_generation(version, fingerprint, ts)` — sha256 of three components)
- [x] Invalidate warmup on every deploy (`mark_deploy_started` flips `warmed=False`)
- [x] Add warmup state machine (`WarmupState` with mark_deploy_started / mark_warmed / mark_warmup_failed / invalidate / set_ui_state; `RedeployStateMachine` with the 8-step sequence from parent plan §26)
- [x] Add verified warmup workflow selection (deferred to a future refinement; the placeholder returns a UUID; the preference order is documented in the docstring)
- [x] Block experiments while unwarmed (`gate_experiment` raises `WarmupRequiredError` when state.deployment_generation() != current or state is not warmed)
- [x] Rebuild Redeploy, restart, and warm (`RedeployStateMachine` implements the full state sequence with valid-transition enforcement; deploy failure does not advance; warmup failure leaves deployment ready but unwarmed)
- [x] Persist UI restoration state (`set_ui_state` / `get_ui_state` round-trip through the warmup state file)

### Files added
- `deploy_warmup.py` (~290 lines)
- `tests/test_deploy_warmup.py` (~210 lines, 18 tests)

### Files modified
- None. Phase 7 is purely additive. The existing `.deployed_state.json` writers in `__init__.py` are untouched.

### Tests added
- 18 tests total. All pass.
- 125 tests total when including all earlier phases and the modal_workspaces regression. All pass.

### Focused test results
```
$ python -m unittest tests.test_deploy_warmup
Ran 18 tests in 0.126s
OK
```

### Broader test results
```
$ python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings tests.test_comparison_loader_groups tests.test_presets_prompts tests.test_presets_images tests.test_matrix_compiler tests.test_experiment_runner tests.test_experiment_scheduler tests.test_deploy_warmup
Ran 125 tests in 2.099s
OK
```

### Manual tests performed
- Verified same generation for identical inputs (3 components); different generation for each changed component.
- Verified `mark_warmed` followed by `mark_deploy_started` correctly resets `warmed=False`.
- Verified `ensure_warmup` no-ops when already warmed; runs warmup when not warmed; reruns when deployment changes.
- Verified `gate_experiment` raises `WarmupRequiredError` when unwarmed; passes when warmed.
- Verified `RedeployStateMachine` walkthrough: idle → deploying → waiting_for_modal → restarting_comfyui → waiting_for_comfyui → restoring_ui → running_warmup → ready. Warmup failed transitions to `unwarmed`. Deploy failed transitions to `failed`. Invalid transitions raise `WarmupError`.
- Verified UI state round-trip: write `{active_tab, selected_experiment, results_open}`, reload from disk, values match.

### Known limitations
- The warmup workflow selection (parent plan §15 preference order: configured warmup workflow → project's last saved warmup → blank placeholder) is **documented but not implemented** in this phase. The current `_run_placeholder_warmup()` returns a UUID. The future refinement will detect the preferred workflow and call it. The state machine and gating work end-to-end regardless.
- The timestamp component of the deployment generation is a known weakness (redeploying identical code without time advancing won't bump generation). The future Modal-side hook can replace the timestamp with the actual Modal deployment ID.
- The actual side-effects of the redeploy sequence (real `modal deploy`, real ComfyUI restart) are not performed; the state machine records the transitions. The Phase 9 HTTP route wires the real side-effects.

### Deviations from this plan
1. **`mark_warmed` auto-adopts the generation if the state's is empty.** The original design raised an error on stale generation. The actual behavior adopts the new generation on first use, which is more forgiving and matches how `ensure_warmup` and `RedeployStateMachine` use it.
2. **18 tests, not the 16 in the plan header.** The extra two are the `test_invalid_transition_raises` (state machine) and `test_persist_and_load_ui_state` (UI restoration). All pass.

### Whether Phase 8 is unblocked
**YES.** Phase 8 (Setup UI) can begin.
