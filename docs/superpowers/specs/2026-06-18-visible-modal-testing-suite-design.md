# Visible Modal Testing Suite Design

## Goal

Make the Modal Testing Suite visibly usable inside a normal ComfyUI browser session after refresh, with one obvious entry point, one persistent modal application shell, and organized screens for Dashboard, Setup, Results, History, and Settings.

## Current problem

- `web/modal-testing.js` uses `app.extensionMenu` instead of the supported ComfyUI extension lifecycle.
- The testing suite may silently disappear because registration returns early when that API is unavailable.
- Existing testing modules contain real functionality, but they are not mounted through a reliable visible shell.
- Settings currently route users back out to the old panel instead of embedding the existing logic inside the suite.

## Design decisions

### Registration and entry points

- Register the suite via `app.registerExtension({ name: "comfymodal.testing-suite", async setup() { ... } })`.
- Inside `setup()`, prefer `app.extensionManager.registerSidebarTab(...)`.
- The sidebar tab renders a compact launch/status panel instead of assuming the tab itself can act like a click-only launcher.
- Add a secondary `Testing Suite` action inside the existing Modal GPU panel.
- If sidebar registration is unavailable or fails, show one fixed fallback launcher and record the failure in diagnostics.
- Keep `window.open_testing_modal()` as a compatibility/debug helper only.

### Persistent host and state

- Mount one host once during extension setup.
- Opening/closing toggles visibility instead of destroying and recreating the whole shell.
- Persist state for active tab, sidebar bootstrap summary, draft setup state, active experiment context, history selection, and A/B comparison selection.
- Prevent duplicate polling/subscriptions by owning refresh/subscription lifecycle in the suite controller.

### Styling

- Use one namespaced style loader with a fixed style element id.
- Use a root namespace `.comfymodal-testing` and related prefixed classes.
- Keep all major shell, card, nav, dialog, form, grid, status, and error styles in one place.

### Module boundaries

- `web/modal-testing.js`: extension registration, diagnostics, persistent shell, nav state, launcher integration, modal open/close, shared state.
- `web/testing-api.js`: route helpers, fetch wrappers, asset URLs, bootstrap loading, event polling, history loaders, error normalization.
- `web/testing-dashboard.js`: deployment card, active experiments, drafts, recent results, last run.
- `web/testing-setup.js`: existing structured experiment builder plus integrated profile management hooks and draft persistence.
- `web/testing-results.js`: existing results workspace adapted to shared API/state.
- `web/testing-history.js`: run history list/detail/logs/timing.
- `web/testing-settings.js`: embedded settings screen using reusable legacy settings mounts.
- `web/testing-ab-slider.js`: compact and fullscreen A/B comparison.

### Legacy settings reuse

- Reuse `modal-settings.js` logic instead of duplicating settings API code.
- Add explicit mount helpers on `window` so the unified suite can render the same settings content into an embedded host.
- Keep the legacy Modal GPU tab during stabilization.

### Compatibility strategy

- Keep existing Modal GPU and comparison tabs working.
- Do not remove legacy entries in this pass.
- Add a unified visible entry without breaking the current progress bar, Modal generation path, comparison routes, or settings save behavior.

### Failure behavior

- Registration failures: console error with `[comfymodal.testing]`, diagnostics update, fallback launcher activation.
- Lazy module load failures: styled error panel in the modal with failing module name and retry action.
- Screen fetch failures: visible inline error + retry, never blank panels.

### Verification strategy

- Structural/source tests verify supported registration, diagnostics, fallback behavior, new module presence, and legacy integration hooks.
- Optional browser smoke harness can target a live ComfyUI URL via environment variable.
- Final manual acceptance will be performed by the user in their already-running ComfyUI instance.

## Scope constraints

- Do not change backend scheduling or `scaledown_window`.
- Only touch backend if a visible frontend integration requires missing summary data or route behavior.
- Preserve existing progress bar, settings logic, comparison profile logic, comparison runner, model/workspace/token/deploy controls, and experiment routes.

## Known trade-offs

- This pass prioritizes reliable visibility and unified frontend integration over deep backend redesign.
- Legacy comparison/settings tabs remain visible until parity is stable.
- Optional browser automation may be added but cannot be claimed as executed unless actually run against a reachable local URL.
