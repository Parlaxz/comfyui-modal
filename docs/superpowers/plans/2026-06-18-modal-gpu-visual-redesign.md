# Modal GPU Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the unified Modal GPU frontend look professional, efficient, minimalist, and complete through a tokenized dark design system and targeted visual refactors of the mounted UI screens.

**Architecture:** Keep the current registration, routing, and state model intact. Centralize visual rules in `web/testing-styles.js`, then refactor mounted screens to use shared classes, stronger hierarchy, and minimal markup hooks where necessary. Preserve all existing frontend behavior while improving clarity, density, and polish.

**Tech Stack:** ComfyUI frontend extensions, plain ES modules, DOM APIs, shared stylesheet injection, Python structural tests, optional browser smoke harness.

---

### Task 1: Add failing visual-structure tests

**Files:**
- Modify: `tests/test_testing_shell_integration.py`
- Modify: `tests/test_testing_setup_js.py`
- Modify: `tests/test_testing_results_js.py`
- Modify: `tests/test_testing_settings_js.py`
- Modify: `tests/test_testing_ui_wired.py`

- [ ] Add failing structural tests for the visual redesign hooks: canonical `Modal GPU` naming, expanded token set in `web/testing-styles.js`, setup step rail markers, dashboard primary CTA references, compact deployment strip path, results layer markers, history row metadata markers, and settings nav active-state hooks.
- [ ] Run the focused frontend tests and verify the new tests fail for the expected reasons.
- [ ] Keep tests structural and source-based only; do not add fake assertions that can pass without real UI changes.

### Task 2: Build the tokenized design system in `web/testing-styles.js`

**Files:**
- Modify: `web/testing-styles.js`
- Test: `tests/test_testing_shell_integration.py`

- [ ] Expand the stylesheet into a real token system with surface, text, interaction, semantic, dimension, spacing, radius, typography, and motion variables.
- [ ] Add shared classes for shell surfaces, hero cards, utility toolbars, metric cards, button variants, inputs, focus states, error states, status badges, step rail, progress bars, history rows, and scrollbars.
- [ ] Run the focused tests and verify token-related failures now pass.

### Task 3: Redesign the Dashboard hierarchy

**Files:**
- Modify: `web/testing-dashboard.js`
- Test: `tests/test_testing_shell_integration.py`

- [ ] Write a failing test for `New Experiment` as the primary healthy-state CTA and for conditional deployment hero / compact deployment status treatment markers.
- [ ] Refactor the dashboard into blocked-state hero vs healthy-state primary-action hierarchy using the shared classes.
- [ ] Keep quick utilities (`Comparison Profiles`, `Quick Comparison`, `Settings`) secondary.
- [ ] Run the focused tests and verify dashboard-related assertions pass.

### Task 4: Redesign Setup as a polished single-page section editor

**Files:**
- Modify: `web/testing-setup.js`
- Test: `tests/test_testing_setup_js.py`

- [ ] Add failing tests for the exact 8-step rail, sticky step navigation hooks, completed/error step markers, and revised `Execution` / `Review & Run` naming.
- [ ] Implement the setup step rail and section-card hierarchy.
- [ ] Apply the shared button/input/error/focus classes and compact profile action toolbar styling.
- [ ] Ensure the setup editor remains a one-page scrollable editor, not a forced wizard.
- [ ] Run the focused setup tests and verify they pass.

### Task 5: Polish Results, History, and Settings wrappers

**Files:**
- Modify: `web/testing-results.js`
- Modify: `web/testing-history.js`
- Modify: `web/testing-settings.js`
- Modify: `web/modal-testing.js` (markup/class hooks only if needed)
- Test: `tests/test_testing_results_js.py`
- Test: `tests/test_testing_settings_js.py`

- [ ] Add failing tests for results hierarchy markers (controls/totals, active progress, completed grid), limited result-card metadata, history row metadata fields, settings nav active-state hooks, and responsive wrapper class hooks.
- [ ] Apply shared classes and minimal markup hooks so Results, History, and Settings visually align with the new system.
- [ ] Preserve A/B logic, embedded settings behavior, and existing interaction semantics.
- [ ] Run the focused tests and verify these screens pass.

### Task 6: Final verification and optional screenshot/smoke support

**Files:**
- Modify: `tests/browser/modal_testing_suite_smoke.mjs` (only if selectors must change)

- [ ] Run the complete focused frontend test set.
- [ ] Run `node --check` on all changed frontend files.
- [ ] If selector labels changed, update the optional browser smoke harness accordingly.
- [ ] Report exact refresh instructions, expected visible changes, and any limits not verified against the user’s live instance.
