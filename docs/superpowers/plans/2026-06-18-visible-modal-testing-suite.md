# Visible Modal Testing Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Modal Testing Suite visibly accessible and usable in ComfyUI through a real sidebar entry, persistent unified modal shell, embedded settings reuse, and supporting dashboard/history/frontend API layers.

**Architecture:** Rebuild `web/modal-testing.js` as the single registration/state owner, add shared frontend infrastructure (`testing-api`, styles, dashboard, history), minimally refactor legacy settings to expose reusable mount helpers, and preserve existing setup/results/A-B behavior by integrating rather than replacing it.

**Tech Stack:** ComfyUI frontend extensions, plain ES modules, DOM APIs, Python structural tests, optional Playwright smoke harness.

---

### Task 1: Add failing source tests for visible frontend integration

**Files:**
- Modify: `tests/test_testing_ui_wired.py`
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_settings_js.py`
- Create: `tests/test_testing_shell_integration.py`

- [ ] Add failing structural tests for `app.registerExtension`, `comfymodal.testing-suite`, no `app.extensionMenu` dependency, diagnostics keys, persistent host hooks, dashboard/history/api module references, fallback launcher logic, and embedded settings mount hooks.
- [ ] Run focused tests and confirm they fail for the expected missing integration reasons.
- [ ] Keep test scope structural/source-level only; do not add fake passing assertions.

### Task 2: Implement shared frontend infrastructure and persistent modal shell

**Files:**
- Modify: `web/modal-testing.js`
- Create: `web/testing-api.js`
- Create: `web/testing-dashboard.js`
- Create: `web/testing-history.js`
- Create: `web/testing-styles.js`

- [ ] Rewrite `web/modal-testing.js` to use `app.registerExtension({ name: "comfymodal.testing-suite", async setup() { ... } })`.
- [ ] Add persistent host creation, one-time style loading, sidebar status launcher panel, fallback launcher logic, diagnostics, and lazy tab mounting.
- [ ] Add `testing-api.js` for shared fetch/error/bootstrap/event helpers.
- [ ] Add `testing-dashboard.js` and `testing-history.js` wired to real `/comfymodal/*` routes.
- [ ] Re-run focused source tests to move registration/shell coverage from red to green.

### Task 3: Integrate existing setup/results/A-B modules into shared state

**Files:**
- Modify: `web/testing-setup.js`
- Modify: `web/testing-results.js`
- Modify: `web/testing-ab-slider.js`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_results_js.py`

- [ ] Adapt setup/results modules to accept shared controllers/options from `modal-testing.js` without recreating duplicate top-level state.
- [ ] Preserve existing route usage while adding draft persistence, integrated profile actions, and result selection shared with A/B.
- [ ] Ensure results uses shared API helpers and can be reopened without duplicate subscriptions.
- [ ] Add/adjust structural tests for new hooks and preserved thumbnail/original behavior.

### Task 4: Embed legacy settings and add the secondary launcher

**Files:**
- Modify: `web/modal-settings.js`
- Modify: `web/testing-settings.js`
- Modify: `tests/test_testing_settings_js.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Expose reusable legacy settings mount/open helpers from `modal-settings.js` without breaking the legacy sidebar tab.
- [ ] Add a `Testing Suite` action inside the existing Modal GPU surface.
- [ ] Update `testing-settings.js` to embed real settings content inside the unified suite using those helpers.
- [ ] Verify structural tests cover embedded settings hooks and the secondary launcher.

### Task 5: Add optional browser smoke coverage and run full relevant verification

**Files:**
- Create: `tests/browser/modal_testing_suite_smoke.mjs`
- Modify: `tests/test_testing_shell_integration.py`

- [ ] Add an optional Playwright smoke script configurable by ComfyUI URL environment variable that checks visible entry, open button, tabs, close/reopen, and refresh persistence.
- [ ] Run all relevant Python structural tests plus any safe smoke validation available in this environment.
- [ ] Record any limitations honestly if live browser execution against the user’s local instance is not possible from this session.
