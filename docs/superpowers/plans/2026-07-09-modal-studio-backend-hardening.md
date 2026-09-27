# Modal Studio Backend Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Workflow Snapshots and Backend Presets the canonical Studio runtime model, move storage/routes out of `__init__.py`, and switch new Studio selectors to presets-only without breaking legacy screens.

**Architecture:** Extract server logic into focused Python modules for models, store, and routes; derive snapshot/preset status server-side with conservative per-feature blocking rules; split `web/studio-backend.js` into page/api/capture/snapshots/presets/shared UI modules and make Playground/Experiment consume presets only.

**Tech Stack:** Python, aiohttp routes, JSON file persistence, vanilla JavaScript modules, pytest

---

## File map

**Create:**
- `studio_models.py`
- `studio_store.py`
- `studio_routes.py`
- `web/studio-backend-api.js`
- `web/studio-backend-capture.js`
- `web/studio-backend-snapshots.js`
- `web/studio-backend-presets.js`
- `web/studio-ui.js`

**Modify:**
- `__init__.py`
- `web/studio-backend.js`
- `web/studio-playground.js`
- `web/studio-experiment-mode.js`
- `tests/test_studio_backend.py`
- `tests/test_routes_registered.py`
- `tests/test_testing_shell_integration.py` (only if import/export shell expectations change)

## Task 1: Lock server behavior with failing tests

- [ ] Add route/model tests for atomic store-backed snapshots/presets, archived filtering, stable error messages, missing snapshot handling, and conservative per-feature status.
- [ ] Add frontend structural tests that assert Playground/Experiment consume presets-only helpers and that `web/studio-backend.js` is composition glue.
- [ ] Run the targeted tests and confirm they fail for the expected reasons.

## Task 2: Extract Python store/models/routes

- [ ] Create `studio_store.py` with reusable `StudioJsonStore`, locking, atomic write, and explicit exceptions.
- [ ] Create `studio_models.py` with feature requirement mirror, normalizers, per-feature status derivation, aggregate status derivation, and stable validation errors.
- [ ] Create `studio_routes.py` with snapshot/preset handlers and registration helpers.
- [ ] Update `__init__.py` to import/register the new Studio routes and remove the inlined implementation block.
- [ ] Run targeted route/model tests and make them pass.

## Task 3: Switch Studio runtime selectors to presets-only

- [ ] Update API surface so Playground/Experiment request Backend Presets only for runtime selection.
- [ ] Preserve legacy/import discovery separately from runtime selectors.
- [ ] Add or update tests proving `.studio_backends.json` is not the source for new Studio selectors.
- [ ] Run targeted selector tests and make them pass.

## Task 4: Split Studio backend frontend modules

- [ ] Extract shared DOM/status/chip helpers into `web/studio-ui.js`.
- [ ] Extract fetch helpers into `web/studio-backend-api.js`.
- [ ] Extract graph capture adapter into `web/studio-backend-capture.js`.
- [ ] Extract snapshots rendering into `web/studio-backend-snapshots.js`.
- [ ] Extract presets rendering into `web/studio-backend-presets.js`.
- [ ] Reduce `web/studio-backend.js` to composition/export glue.
- [ ] Run targeted frontend structural tests and make them pass.

## Task 5: Verify regression envelope

- [ ] Run focused backend/frontend Studio tests.
- [ ] Run route registration tests.
- [ ] Check for syntax/runtime regressions in split JS modules using existing tests.
- [ ] Report remaining risk areas, if any, from verification output only.
