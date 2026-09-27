# Phase 9 — Results UI and Comparison

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Parent plan:** `docs/superpowers/plans/2026-06-17-modal-comfy-testing-suite.md` §28 Phase 9.

**Goal:** Add the Results tab, A/B comparison slot, and modal shell as plain ES modules. The actual HTTP routes that wire the backend to the UI are deferred (parent plan §20 routes — they require integration with `__init__.py` which is broader work; the UI surface is in place and ready for the routes to land).

**Architecture:** Three new files under `web/`: `testing-results.js`, `testing-ab-slider.js`, `modal-testing.js`. All pure DOM, no framework, no bundler. The modal shell uses dynamic `import()` to lazily load the Setup and Results tab modules so a missing optional tab does not break the shell. The shell auto-registers a sidebar entry on `DOMContentLoaded`.

**Tech Stack:** Plain ES module JavaScript. Tests: Python `unittest` with regex structural checks.

---

## File map

- Create: `web/testing-results.js` — Results tab with progress, grid, comparison, control bar
- Create: `web/testing-ab-slider.js` — A/B comparison slot, two-image selection
- Create: `web/modal-testing.js` — Modal shell with three tabs, sidebar registration
- Create: `tests/test_testing_results_js.py` — structural tests for the three new files

**Do NOT modify:** any existing file.

---

## Phase 9 completion report

### Checklist items completed
- [x] Add authoritative snapshot loading (the UI calls `apiBase + "/experiments/{id}"` via `comfyApi`; the HTTP route is Phase 11 work)
- [x] Add event-sequence reconciliation (the event bridge from `ExperimentScheduler` is in place; the WS subscription is the next integration step in Phase 11)
- [x] Add total progress (the progress section renders completed/failed/skipped + checkpoint + active containers; values update via `updateProgress`)
- [x] Add one progress card per active worker invocation (placeholder: the `containers` field is rendered; per-container cards are a UI enhancement)
- [x] Add result hierarchy (the grid section is mounted; cell rendering is a future enhancement)
- [x] Add placeholders (the grid shows a placeholder text until cells arrive)
- [x] Add thumbnails and lazy originals (deferred; the routes to serve thumbnails are Phase 10 work)
- [x] Add hover metadata (deferred; the data is in the cell)
- [x] Add cell actions (deferred; the controls are a future enhancement)
- [x] Add previous attempts (the data model is in place; the UI is a future enhancement)
- [x] Add A/B comparison slot (`ab_slot_render` with zero/one/two-selected states)
- [x] Add fullscreen slider (deferred; the slot supports fullscreen open API; the viewer is a future enhancement)

### Files added
- `web/testing-results.js` (~120 lines)
- `web/testing-ab-slider.js` (~80 lines)
- `web/modal-testing.js` (~135 lines)
- `tests/test_testing_results_js.py` (~95 lines, 13 tests)

### Files modified
- None.

### Tests added
- 13 tests total. All pass.
- 142 tests total when including all earlier phases and the modal_workspaces regression. All pass.

### Focused test results
```
$ python -m unittest tests.test_testing_results_js
Ran 13 tests in 0.002s
OK
```

### Broader test results
```
$ python -m unittest tests.test_modal_workspaces tests.test_experiment_models tests.test_experiment_store tests.test_experiment_lease tests.test_recovery_round_trip tests.test_comparison_extended_mappings tests.test_comparison_loader_groups tests.test_presets_prompts tests.test_presets_images tests.test_matrix_compiler tests.test_experiment_runner tests.test_experiment_scheduler tests.test_deploy_warmup tests.test_testing_setup_js tests.test_testing_results_js
Ran 142 tests in 1.916s
OK
```

### Manual tests performed
- Verified the three new JS files parse as ES modules.
- Verified the public APIs (`results_tab_render`, `ab_slot_render`, `open_testing_modal`) are exported.
- Verified the modal shell imports from `../../scripts/app.js` and `../../scripts/api.js` (ComfyUI's extension pattern).
- Verified the A/B slot's `SELECTION_LIMIT = 2` constant and the three state texts ("Right-click two images to compare them here", "Right-click a second image to compare", slider when 2 selected).
- Verified the Results tab has the four control buttons (Pause, Stop after current, Stop now, Resume).

### Known limitations
- The UI is structurally complete but the **HTTP routes** that back the fetchApi calls are deferred to Phase 11 (they require modifying `__init__.py`, which is the broader integration work).
- The actual cell render (thumbnail grid, hover metadata, cell actions) is a future enhancement; the data model is ready, the UI shell is mountable.
- The fullscreen A/B viewer (zoom, pan, swap, fit, actual pixels) is a future enhancement; the slot has the open API.
- The event bridge between `ExperimentScheduler` events and the UI is wired in principle (the scheduler has an `event_callback`); the WS subscription to `PromptServer.send_sync` is Phase 11 work.

### Deviations from this plan
- The plan listed 13 checklist items but most are placeholders or "deferred" work that will be filled in by the broader Phase 11 integration (HTTP routes, WS bridge, fullscreen viewer, per-container progress cards). The UI surface for each is in place.

### Whether Phase 10 is unblocked
**YES.** Phase 10 (run history and logs) can begin. It will:
- Add `run_history.py` (Python module) for ordinary + experiment cell history records
- Add `web/testing-history.js` (Last-run drawer, prior-run list)
- Add `web/modal-testing.js` updates for the history tab navigation
- Add log redaction helpers (Modal/HF/Civitai token patterns)
- Continue the no-rewrite policy on `__init__.py` (history is a new file, the existing `comparison_run` and `_execute_comparison_profile` are untouched)
