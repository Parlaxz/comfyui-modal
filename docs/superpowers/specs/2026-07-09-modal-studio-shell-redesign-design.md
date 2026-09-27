# Modal Studio Shell Redesign Design

**Source of truth:** `modal_studio_playground_redesign_agent_plan.md`

## Goal

Replace the old testing-suite primary shell with a new Modal Studio shell centered on Playground, History, and Settings, while preserving the existing backend experiment/history infrastructure and keeping all old testing modules reachable through Settings > Legacy.

## Scope

In scope:

- Replace the old primary 6-tab shell with a 3-page Studio shell.
- Keep `web/modal-testing.js` as the single ComfyUI extension entrypoint and modal lifecycle owner.
- Add new Studio modules for shell, Playground, History, Settings, feature registry, experiment mode, legacy wrapper, and Studio styles.
- Keep old `web/testing-*.js` modules intact and reachable only through Settings > Legacy.
- Add thin backend adapters only where the new Studio pages need real bootstrap/history/preset data.
- Use real history/backend data or truthful empty/disabled states.

Out of scope:

- Full redesign of legacy pages.
- Second Studio entrypoint or second launcher.
- Backend experiment/history rewrites.
- Real SAM, mask, or image-edit tooling.
- Fake runs, fake outputs, fake backends, fake logs, or fake experiment records.

## Architecture

### `web/modal-testing.js`

`web/modal-testing.js` remains the only ComfyUI extension entrypoint and owns only:

- modal open/close lifecycle
- modal host/container creation
- launcher/sidebar/fallback registration
- diagnostics globals and compatibility globals
- mount/unmount of the Studio shell
- stable shell context passed into the shell, such as `apiBase`, close handler, diagnostics hooks, and legacy compatibility helpers

It no longer owns deep page state for Playground, History, or Settings and no longer renders the old 6-tab UI as the primary shell.

### `web/studio-shell.js`

`web/studio-shell.js` owns Studio app state and page switching:

- `activePage`
- Playground state
- History state
- Settings state
- local Studio render/update lifecycle

It renders the top nav:

- Playground
- History
- Settings

It mounts the selected page into the Studio body and receives only stable context from `web/modal-testing.js`.

### New Studio modules

- `web/studio-shell.js`
- `web/studio-playground.js`
- `web/studio-history.js`
- `web/studio-settings.js`
- `web/studio-feature-registry.js`
- `web/studio-experiment-mode.js`
- `web/studio-legacy.js`
- `web/studio-styles.js`
- `web/studio-api.js` only if helper separation is cleaner than extending existing helpers

### Legacy modules

These remain intact and are not modernized in this change:

- `web/testing-dashboard.js`
- `web/testing-setup.js`
- `web/testing-profiles.js`
- `web/testing-results.js`
- `web/testing-history.js`
- `web/testing-settings.js`

They are loaded only through Settings > Legacy.

### Backend

Preserve the current backend experiment/history infrastructure, including the existing `experiment_*`, `matrix_compiler`, `run_history`, and route registration layers. Only add thin adapter routes if the new Studio pages need cleaner real data access.

## Studio State Model

Studio state lives in `web/studio-shell.js` and includes:

- `activePage`: `playground | history | settings`
- `playground.featureId`
- `playground.experimentMode`
- `playground.selectedBackendId`
- `playground.compareBackendIds`
- `playground.controls`
- `playground.experimentAxes`
- `history.selectedRunId`
- `history.filters`
- `settings.activeSection`
- `settings.activeLegacyTab`

Only harmless UI preferences may persist in `localStorage`, such as active page, selected feature, experiment mode, and selected backend. No secrets are stored in localStorage.

## Playground Design

Playground is the default page and occupies the full body area under the top nav.

### Layout

- Left fixed-width control panel, compact and vertically dense.
- Right flexible workspace for feature mode cards, preview/canvas area, and a bottom recent-runs strip if real history is available.

### Left control panel

Normal mode includes:

- Experiment button at the top
- feature selector
- backend selector
- prompt/instruction textarea
- negative prompt textarea if needed by current generation flows
- control set driven by the feature registry
- Run button

Core controls include:

- Prompt / instruction
- Steps
- Guidance
- Denoise
- Seed
- LoRA
- LoRA strength
- Mask blur
- Mask expand

### Right workspace

- feature cards/tabs near the top for `txt2img`, `object_remove`, and `object_replace`
- a large workspace/canvas region
- a recent runs filmstrip/strip if real run history exists

For `object_remove` and `object_replace`, image-edit interactions are honest disabled future-work placeholders only.

## Feature Registry

`web/studio-feature-registry.js` defines Studio features and controls. Initial features:

- `txt2img`
- `object_remove`
- `object_replace`

Each control definition includes:

- `id`
- `label`
- `type`
- `defaultValue`
- numeric constraints where relevant
- `experimentEligible`
- feature applicability
- help text

The registry drives Playground rendering instead of hardcoded per-control markup only.

## Experiment Mode

Experiment is a mode inside Playground, not a separate page.

When enabled:

- the top button becomes Exit Experiment
- a Compare Backends block appears
- a matrix summary block appears
- existing eligible controls gain experiment-axis checkboxes beside their labels

There is no separate top-level or master “Test Axes” list.

Axis editing is attached to each knob/control and supports:

- default value visibility
- adding prompt variants
- adding numeric/select values
- choosing comparison mode
- add/update/remove axis actions

If experiment execution cannot be safely adapted to existing systems yet, Run Experiment is disabled with a precise reason and a route to Legacy Setup.

## Backend Preset Abstraction

Studio normalizes backend options into a small frontend abstraction:

- `id`
- `label`
- feature compatibility
- source
- disabled reason if unavailable

Preferred sources are existing profiles, presets, bootstrap data, or other current backend inventory endpoints. If no reliable inventory exists, Studio shows a truthful empty state and points users to Settings > Legacy.

## History Page

History is a real top-level page backed by existing run/experiment data or thin real adapters.

It provides at least:

- search/filter input
- simple kind/status filtering if easy
- card/list view
- selected detail pane
- metadata display for prompt, workflow, model stack, LoRAs, seed, steps, guidance, denoise, status, timings, and output path where available

If no history exists, it shows a useful empty state. It must not be a decorative coming-soon page.

If full matrix visualization is not yet feasible, experiment-related runs are at least grouped by `experiment_id` when available.

## Settings Page

Settings is a real top-level page with sections:

- Studio
- Backends / Presets
- Modal / Runtime
- Features
- Legacy

It may start with compact cards/panels, but Legacy must actually load the old screens.

Legacy entries:

- Legacy Dashboard
- Legacy Setup
- Legacy Profiles
- Legacy Results
- Legacy History
- Legacy Settings

## Legacy Loading Contract

`web/studio-legacy.js` must preserve the old module contract carefully.

### Shared contract

Every old module exports `*_tab_render(rootEl, api, options = {})` and expects:

- `rootEl`
- optional `api`
- `options.apiBase` defaulting to `/comfymodal`

### Module-specific legacy dependencies

#### `testing-dashboard.js`

Depends on:

- `window.open_testing_modal(tab)` for Setup, Results, and Profiles navigation
- `window.open_comfymodal_settings()`
- optional legacy comparison globals
- `bootstrapLoader()` and existing history/deploy/experiments APIs

#### `testing-setup.js`

Depends on:

- `options.draft`
- `options.onDraftChange(draft)`
- `options.onRun(experimentId)`
- `options.previewState`
- behavior from `testing-setup-adapter.js`

This is the most sensitive legacy contract and must keep persisted draft/setup state and preview-state behavior intact.

#### `testing-profiles.js`

Depends mainly on `options.apiBase` and its own profile CRUD flow.

#### `testing-results.js`

Depends on:

- `options.experimentId`
- `window.__comfymodal_worker_progress`
- polling lifecycle cleanup when the view is unmounted

#### `testing-history.js`

Depends on existing history APIs and `bootstrapLoader()`.

#### `testing-settings.js`

Depends on:

- `window.mountSettingsPanel(container)` as primary embedded render path
- `window.open_comfymodal_settings()` as fallback
- `comfymodal.open-section` event behavior

### Legacy wrapper behavior

`web/studio-legacy.js` should:

- lazy-load the same old module render functions
- pass through `apiBase`
- preserve draft/setup state, preview state, experiment id, and callbacks needed by old modules
- ensure required old globals/helpers remain available
- mount legacy screens inside the Studio body where safe
- surface visible inline errors if a legacy module fails to load
- provide a Back to Settings path

Preferred behavior is embedded legacy rendering inside Studio, not a second modal, unless embedding is found to be too risky during implementation.

## Styling

Add Studio-specific styles without breaking old testing styles. Preserve existing legacy styles for the old modules.

Required class structure includes:

- `.comfymodal-studio-overlay`
- `.comfymodal-studio-modal`
- `.comfymodal-studio-header`
- `.comfymodal-studio-topnav`
- `.comfymodal-studio-body`
- `.comfymodal-studio-playground`
- `.comfymodal-studio-control-panel`
- `.comfymodal-studio-workspace`
- `.comfymodal-studio-canvas`
- `.comfymodal-studio-filmstrip`
- `.comfymodal-studio-card`
- `.comfymodal-studio-axis-popover`
- `.comfymodal-studio-history`
- `.comfymodal-studio-settings`
- `.comfymodal-studio-legacy`

Design goals:

- dark, compact, professional Studio feel
- top nav around 48-60px high
- left control panel around 300-380px wide
- right workspace fills remaining space
- avoid full-modal scrolling where possible
- clear disabled states and honest empty states

## Error Handling

- If backend presets are unavailable, show a truthful empty state and route users to Settings / Legacy.
- If single-run wiring is not safe, disable Run with a precise reason.
- If experiment execution wiring is not safe, disable Run Experiment with a precise reason and route users to Legacy Setup.
- Disabled future-work image-edit controls must be visibly non-functional and honest.
- Legacy loading failures must appear inline in the Studio body.
- History fetch failures must show visible errors and retry affordances where practical.

## Testing Strategy

Update existing shell tests that currently assume the old 6-tab shell.

Add or update tests for:

- new top-nav shell with only Playground, History, Settings in the main nav
- explicit absence of old top-level Dashboard / Setup / Profiles / Results tabs from the new main nav
- default page = Playground
- feature registry entries for `txt2img`, `object_remove`, and `object_replace`
- experiment mode axis-checkbox behavior on existing knobs
- absence of a separate Test Axes list
- real History wiring or a truthful empty state
- Settings > Legacy reachability for all old screens
- legacy screens rendering through the new Legacy wrapper
- disabled placeholder behavior for unfinished image-edit tools
- any new Studio adapter routes added in backend route registration

Run existing backend/history/experiment tests after the frontend changes to verify preserved infrastructure remains intact.
