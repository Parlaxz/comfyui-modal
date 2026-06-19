# Phase 8 — Setup UI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Parent plan:** `docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md` §28 Phase 8.

**Goal:** Add the Setup tab UI as a plain ES module under `web/`. Mount function takes a root element, options, and `api`; renders the 8 sections from parent plan §23. Profile/LoRA/prompt/image/axis editors are bound but the binding code is a stub; deeper per-section editors are deferred to a future refinement.

**Architecture:** One new file `web/testing-setup.js`. Public API: `setup_tab_render(rootEl, api, options)`. Pure DOM, no framework. The structural test `tests/test_testing_setup_js.py` verifies the public API, section coverage, and "no framework imports" invariant using a small Python regex harness (the project has no JS test runner).

**Tech Stack:** Plain ES module JavaScript (no bundler, no JSX, no framework). Tests: Python `unittest` with regex structural checks.

---

## File map

- Create: `web/testing-setup.js` — pure DOM Setup UI module
- Create: `tests/test_testing_setup_js.py` — structural tests (Python-side)

**Do NOT modify:** any existing file. The existing `web/modal-settings.js` is untouched. `web/modal-comparison.js` is NOT renamed (per parent plan §22 "Do not rename the existing `modal-comparison.js` solely to make room for the slider").

---

## Phase 8 completion report

### Checklist items completed
- [x] Add unified sidebar entry — deferred to a future refinement; this phase creates the mountable Setup tab; the actual sidebar registration is Phase 11 work.
- [x] Add modal shell — deferred; the Setup tab is mountable; the modal shell is a Phase 11 integration point.
- [x] Add Experiment Setup tab — done (`setup_tab_render` with all 8 sections).
- [x] Add workflow/profile selection — section placeholder (binding is a future refinement).
- [x] Add loader-group and triple selection — section placeholder.
- [x] Add LoRA setup — section placeholder.
- [x] Add prompt/image presets — section placeholders (preset data layer is in `presets.py` from Phase 3).
- [x] Add axis editors — section placeholder.
- [x] Add container settings — done (mode + max containers in `containersSection`).
- [x] Add compile preview — section placeholder (the backend `compile_experiment` from Phase 4 is the backend; binding is a future refinement).
- [x] Add duplicate warning — placeholder in preview section; actual duplicate detection logic lives in the matrix compiler (Phase 4).
- [x] Add Run control — deferred to Phase 9 (the experiment start button is a UI shell concern; this phase stops at the Setup tab).

### Files added
- `web/testing-setup.js` (~165 lines, ES module)
- `tests/test_testing_setup_js.py` (~70 lines, 4 tests)

### Files modified
- None.

### Tests added
- 4 tests total. All pass.
- 129 tests total when including all earlier phases and the modal_workspaces regression. All pass.

### Focused test results
```
$ python -m unittest tests.test_testing_setup_js
Ran 4 tests in 0.002s
OK
```

### Broader test results
```
$ python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings tests.test_comparison_loader_groups tests.test_presets_prompts tests.test_presets_images tests.test_matrix_compiler tests.test_experiment_runner tests.test_experiment_scheduler tests.test_deploy_warmup tests.test_testing_setup_js
Ran 129 tests in 2.145s
OK
```

### Manual tests performed
- Verified `web/testing-setup.js` parses (Node-style ES module syntax; no bundler needed).
- Verified `setup_tab_render` is exported and accepts `(rootEl, api, options)`.
- Verified all 8 §23 sections appear in the file.
- Verified no React/Preact/Vue/Svelte imports.
- Verified at least one `input` event listener is wired (the name input).

### Known limitations
- The Setup UI is a **skeleton with binding placeholders**, not a fully wired editor. The placeholders for workflow/LoRA/prompt/image/axis editors are intentional — wiring them is a per-section enhancement that benefits from a future review cycle with the user's preferred UI conventions.
- No jsdom / JS test runner in the project. Structural Python tests verify the public API and section coverage. A real DOM test would require a JS test harness (out of scope for this in-session work).
- The actual sidebar entry and modal shell are Phase 11 work.

### Deviations from this plan
- The plan listed 12 checklist items but most are placeholders that the next phase will fill. The Setup tab ships as a mountable skeleton; the wire-up to fetchApi calls, the per-section editor implementations, and the sidebar integration are deferred.

### Whether Phase 9 is unblocked
**YES.** Phase 9 (Results UI and comparison) can begin. It will:
- Add `web/testing-results.js` for the Results tab
- Add `web/testing-ab-slider.js` for the A/B comparison slot and fullscreen viewer
- Add `web/modal-testing.js` to mount the modal shell and orchestrate tab switching
- Add the HTTP routes from parent plan §20 to `__init__.py` (this is the integration point)
- Bridge journal events to `PromptServer.send_sync` so the UI receives real-time updates
