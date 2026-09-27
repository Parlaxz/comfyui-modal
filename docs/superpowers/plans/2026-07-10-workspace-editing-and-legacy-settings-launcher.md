# Workspace Editing and Legacy Settings Launcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `Open Legacy Settings` button to the Modal GPU sidebar launcher and let users edit existing workspace labels and credentials from the legacy Workspace section without creating duplicate workspaces.

**Architecture:** Keep `web/modal-testing.js` as the sidebar launcher owner, reuse the existing global legacy-settings opener from `web/modal-settings.js`, extend the existing workspace modal patterns for edit mode, and make `modal_workspaces.py` preserve saved tokens when edit submissions leave credential fields blank.

**Tech Stack:** Python, vanilla JavaScript, unittest/pytest

---

## File map

**Modify:**
- `web/modal-testing.js`
- `web/modal-settings.js`
- `modal_workspaces.py`
- `tests/test_modal_workspaces.py`
- `tests/test_modal_workspace_ui_ast.py`

## Task 1: Lock the workspace-edit backend behavior with failing tests

- [ ] Add a failing test to `tests/test_modal_workspaces.py` proving an existing workspace can be renamed while blank `token_id` and `token_secret` inputs preserve the saved credentials.
- [ ] Add a failing test to `tests/test_modal_workspaces.py` proving workspace updates by `workspace_id` do not create a second workspace entry.
- [ ] Run `pytest tests/test_modal_workspaces.py -q` and confirm the new test fails for the expected validation reason before changing `modal_workspaces.py`.

## Task 2: Implement backend token-preservation update behavior

- [ ] Update `modal_workspaces.py` so edit updates with a matching `workspace_id` preserve existing `token_id` and `token_secret` when the submitted values are blank strings.
- [ ] Keep creation behavior unchanged: new workspaces still require valid `ak-` and `as-` tokens.
- [ ] Re-run `pytest tests/test_modal_workspaces.py -q` and make the backend tests pass.

## Task 3: Lock the launcher and workspace-edit UI hooks with failing tests

- [ ] Add a failing assertion to `tests/test_modal_workspace_ui_ast.py` for the `Open Legacy Settings` button text in `web/modal-testing.js`.
- [ ] Add a failing assertion to `tests/test_modal_workspace_ui_ast.py` for an `Edit Workspace` action in `web/modal-settings.js`.
- [ ] Add a failing assertion to `tests/test_modal_workspace_ui_ast.py` for edit-mode guidance like `Leave blank to keep current`.
- [ ] Run `pytest tests/test_modal_workspace_ui_ast.py -q` and confirm the new assertions fail before changing the JS files.

## Task 4: Add the sidebar legacy-settings launcher button

- [ ] Update `web/modal-testing.js` `buildSidebarPanel()` to add an `Open Legacy Settings` button next to the existing launcher controls.
- [ ] Wire the new button to `window.open_comfymodal_settings()` when available.
- [ ] Add visible failure handling when the global opener is unavailable instead of silently failing.
- [ ] Re-run `pytest tests/test_modal_workspace_ui_ast.py -q` and keep the new launcher assertion green.

## Task 5: Add workspace edit mode to the legacy settings panel

- [ ] Update `web/modal-settings.js` to add an `Edit Workspace` button near `+ Add Workspace`.
- [ ] Keep the button disabled or inert when no workspace is selected.
- [ ] Add an `openEditWorkspaceModal()` flow based on the existing add modal, but prefill only the label and present token placeholders that explain blank values keep current credentials.
- [ ] Submit edits through the existing `POST ${MODAL_PREFIX}/workspaces` route with `workspace_id` and without changing active-workspace state.
- [ ] Reload the workspace list after save and restore the updated workspace selection.
- [ ] Re-run `pytest tests/test_modal_workspace_ui_ast.py -q` and keep the new edit assertions green.

## Task 6: Verify the regression envelope

- [ ] Run `pytest tests/test_modal_workspaces.py tests/test_modal_workspace_ui_ast.py -q`.
- [ ] If those pass, run `pytest tests/test_testing_ui_wired.py -q` to catch broader launcher/settings regressions.
- [ ] Report any remaining risk only from observed test output.
