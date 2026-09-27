Modal Studio Redesign: Replace Old Testing-Suite UI With Playground / History / Settings Shell

use Subagent driven implementation and programming

You are implementing a concrete redesign in the existing `Parlaxz/comfyui-modal` repo. Do not ask the user which “pass,” “phase,” or migration strategy to choose. The product direction is already decided. Your job is to inspect the current code, preserve the working backend/legacy functionality, and implement the new Studio UI shell and migration as one coherent change.

You must use OMO-Slim’s Explorer, Oracle, and Fixer subagents:

* Explorer: inspect the current codebase, trace existing UI entrypoints, old testing-suite modules, API helpers, history/results modules, settings modules, experiment runner/store/service, and browser tests. Explorer should report exact files/functions/classes to touch.
* Oracle: review the intended architecture and the implementation plan for risk, missing integration points, broken legacy access, hidden assumptions, and test coverage gaps.
* Fixer: implement the code changes, fix test failures, and keep the code simple.
  The main agent must own the product interpretation and final plan. Do not delegate product decisions to subagents. Do not ask the user to clarify choices already specified here.

Hard rule: do not create a new branch or worktree unless explicitly instructed by the user. Work in the current repo state.

Current known baseline:

* Latest intended starting point is main at commit `56aca0b` or whatever current main has advanced to after it. If HEAD differs, inspect the delta and adapt without asking unless the repo is fundamentally unrelated.
* The current visible testing suite is built around `web/modal-testing.js`.
* Existing old UI modules include files such as:

  * `web/testing-dashboard.js`
  * `web/testing-setup.js`
  * `web/testing-profiles.js`
  * `web/testing-results.js`
  * `web/testing-history.js`
  * `web/testing-settings.js`
  * `web/testing-styles.js`
  * `web/testing-api.js`
  * `web/testing-setup-adapter.js`
  * `web/testing-ab-slider.js`
* Existing backend experiment/history infrastructure should be preserved, not rewritten from scratch:

  * `experiment_service.py`
  * `experiment_scheduler.py`
  * `experiment_runner.py`
  * `experiment_store.py`
  * `experiment_models.py`
  * `matrix_compiler.py`
  * `run_history.py`
  * `presets.py`
  * route registration files and tests
* The old UI may be ugly/cluttered, but it contains working behavior. Preserve access to it under Settings > Legacy.

Product target:
Replace the old primary testing-suite UX with a new Modal Studio shell:

Top nav only:

1. Playground
2. History
3. Settings

No left sidebar inside the Studio modal/page. No permanent top-level Experiment tab. No visible old Dashboard / Setup / Profiles / Results nav in the main top nav.

The Studio should feel like a clean ComfyUI wrapper / feature-prototyping studio:

* Playground is the main surface.
* History is the unified evidence/result browser.
* Settings is the admin/config/legacy area.
* The old experiment system survives, but it is not the primary UI anymore.
* Legacy screens remain directly reachable from Settings > Legacy.

Visual/design direction:

* Main visual source of truth: Nexus BTA style.

  * Dark compact studio UI.
  * Top navigation.
  * Left vertical control panel.
  * Large right-side canvas/workspace.
  * Minimal clutter.
  * Controls packed vertically to avoid scrolling.
  * Strong contrast, cards/panels, polished modern wrapper feel.
* Secondary inspiration: SwarmUI.

  * Top tabs/nav.
  * Left parameter panel.
  * Main preview/workspace.
  * Grouped controls and compact sliders.
* Secondary inspiration: ViewComfy.

  * Feature/workflow becomes a simplified app-like interface.
  * Expose only selected inputs.
* Secondary inspiration: OutSweeper.

  * History should become fast, searchable, review-friendly, and metadata-oriented.

Critical product decisions:

1. The new app shell must have top nav only:

   * Playground
   * History
   * Settings

2. Playground must occupy the full area below the top bar.

3. Playground layout:

   * Left side: vertical knobs/control panel.
   * Right side: image canvas/workspace/results area.
   * The goal is to avoid scrolling as much as possible.
   * The Experiment button lives at the top of the left control panel.

4. Experiment is a mode inside Playground, not a separate page or sidebar item.

   * Pressing Experiment turns the same Playground into experiment mode.
   * It adds backend comparison controls.
   * It adds checkboxes next to the existing knobs.
   * It does not show a separate “Test Axes” list.
   * Existing knobs become experiment axes when checked.

5. Existing Playground knobs should include the future-relevant controls even if some are not wired for true image editing yet:

   * Prompt / instruction
   * Steps
   * Guidance
   * Denoise
   * Seed
   * LoRA
   * LoRA strength
   * Mask blur
   * Mask expansion

6. Image editing / mask interaction can be deferred.

   * It is acceptable to show clear “to be implemented” placeholder copy for actual image canvas editing, SAM selection, object remove, object replace, mask brushing, click-to-select, and type-to-select.
   * Do not fake working image-editing behavior.
   * Do not produce fake results.
   * Do not wire buttons to pretend mask/image editing works.
   * A visible placeholder is allowed only when it is honest and non-interactive or disabled.
   * The rest of the implementation must be real, not stubbed.

7. Legacy migration must be real.

   * Old Dashboard, Setup, Profiles, Results, History, and Settings screens must still be reachable after the redesign.
   * Put them under Settings > Legacy.
   * Legacy screens can render inside a legacy panel, modal subview, or embedded legacy container, but they must actually load the old modules and remain usable.
   * Do not delete old modules unless you have fully replaced their functionality and tests prove nothing broke. Preferred approach: keep old modules and wrap them.

8. The implementation should make future features easy to add.

   * Add a simple feature registry / feature spec layer.
   * Initial feature entries:

     * txt2img
     * object_remove
     * object_replace
   * `object_remove` and `object_replace` can have honest future placeholders for image-edit interactions.
   * The registry should make it easy to add later:

     * image edit
     * inpaint
     * outpaint
     * relight
     * pose library
     * multi-angle character generation
     * sketch/drawing to image
   * Adding a feature later should not require rewriting the Studio shell.

9. The implementation should make backend presets/workflow snapshots easy to add later.

   * Do not overbuild a full preset editor now unless the current repo already has enough pieces.
   * But structure the frontend around the concept that a feature has compatible backend presets.
   * Backend labels can initially be derived from existing profiles/presets where available, or fallback to safe local default options if no backend inventory endpoint exists.
   * If a backend list is not yet available, make the UI say “No backend presets configured” and point to Settings/Legacy. Do not use fake successful backend behavior.

10. History must become the top-level page.

* It should use existing run history / experiment history APIs where available.
* It should show both ordinary runs and experiment-related runs/groups when available.
* If existing APIs only expose old data shape, adapt it to a new card/list UI.
* Do not remove old history functionality; old history remains under Settings > Legacy if needed.
* New History should be functional, not a decorative placeholder.

11. Settings must become the top-level admin/config page.

* Include sections:

  * Studio
  * Backends / Presets
  * Modal / Runtime
  * Features
  * Legacy
* These can start as compact cards/panels if deep editors are not yet available.
* Settings > Legacy must actually open/render old screens.

What to implement:

A. Replace the primary shell

Inspect `web/modal-testing.js`. It currently builds the old modal shell and nav. Refactor or replace it so the primary shell is now Modal Studio with:

* Header title: “Modal Studio” or “Modal GPU Studio”
* Top nav buttons: Playground, History, Settings
* Body area that renders the selected Studio page
* No visible old tabs in the top nav
* Existing Comfy sidebar launcher can still open the Studio modal
* Existing fallback launcher can still open the Studio modal
* Existing diagnostics should remain or be updated safely

Keep the app extension registration working. Do not break the sidebar launcher registration with ComfyUI.

Preferred structure:

* Keep `web/modal-testing.js` as the extension entrypoint if that is what ComfyUI loads.
* Move old shell behavior into a legacy helper if needed.
* Add new modules under `web/studio/` or with clear names such as:

  * `web/studio-shell.js`
  * `web/studio-playground.js`
  * `web/studio-history.js`
  * `web/studio-settings.js`
  * `web/studio-feature-registry.js`
  * `web/studio-experiment-mode.js`
  * `web/studio-api.js`
  * `web/studio-styles.js`
  * `web/studio-legacy.js`
    If the repo style prefers flat `web/*.js`, that is acceptable, but keep names clear.

B. Studio state model

Create simple state, not a framework rewrite:

* activePage: playground/history/settings
* playground:

  * featureId
  * experimentMode boolean
  * selectedBackendId
  * compareBackendIds
  * controls object
  * experimentAxes object keyed by control id
* history:

  * selectedRunId or selectedExperimentId
  * filters if easy
* settings:

  * activeSection
  * activeLegacyTab

Keep state local to frontend module unless existing persistence patterns suggest localStorage. Use localStorage only for harmless UI preferences:

* active Studio page
* selected feature
* experiment mode off/on
* selected backend, if safe

Do not persist secrets in localStorage.

C. Playground page

Create a real Playground page with this layout:

Top app nav:
`Modal Studio | Playground | History | Settings`

Below nav:

* Left control rail, fixed width, compact.
* Right workspace, flexible width.

Left panel normal mode:

* Experiment button at the top.
* Feature selector.
* Backend selector.
* Prompt/instruction textarea.
* Negative prompt textarea if existing generation flows need it.
* Selection section:

  * For txt2img: hidden or disabled.
  * For object_remove/object_replace: honest placeholder text that SAM/mask tools are future work.
* Controls:

  * Steps number stepper
  * Guidance slider/number
  * Denoise slider/number
  * Seed input + randomize button
  * LoRA selector placeholder / existing list if available
  * LoRA strength slider
  * Mask blur slider/number
  * Mask expand slider/number
* Run button.

  * If a real existing single-run pathway exists and can be wired safely, wire txt2img run to it.
  * If no safe single-run pathway exists, show a disabled Run button with a clear reason, not fake behavior.
  * Do not pretend object_remove/object_replace image editing works.

Right workspace normal mode:

* Feature mode tabs/cards near the top:

  * Txt2Img
  * Object Remove
  * Object Replace
* Big canvas/workspace region:

  * txt2img: preview/results placeholder tied to real history if possible.
  * object_remove/object_replace: “Image canvas and mask tools coming next” with disabled tool chips.
* Bottom filmstrip/results strip:

  * Show recent runs from History if available.
  * If no runs, show empty state.
* Optional compact status/log drawer if existing APIs make it easy.

D. Experiment mode inside Playground

Experiment button toggles experiment mode.

Left panel experiment mode changes:

* Button becomes “Exit Experiment”.
* A Compare Backends block appears near the top.

  * Show compatible backend presets for current feature.
  * Checkboxes allow selecting multiple backends.
  * If no backend inventory exists, show a clear empty state and link/cue to Settings > Legacy / Profiles.
* Matrix summary block:

  * Backends count
  * Axes count
  * Estimated runs
  * Mode summary
* Existing controls gain an axis checkbox beside their labels.

  * Example:

    * `[✓] Prompt / Instruction`
    * `[ ] Steps`
    * `[ ] Guidance`
    * `[ ] Denoise`
    * `[ ] Seed`
    * `[ ] LoRA`
    * `[ ] LoRA Strength`
    * `[ ] Mask Blur`
    * `[ ] Mask Expand`
* There must not be a separate “Test Axes” master list.
* Clicking a checkbox or small configure button opens an axis editor popover/inline panel for that exact knob.

Axis editor behavior:

* Shows current default value.
* Allows adding values:

  * Prompt: multiline variants.
  * Numeric controls: comma-separated numbers and/or add buttons.
  * Select controls: selectable option values if available.
* Mode:

  * Test against defaults
  * Test against all selected axes
* Add/update axis button.
* Remove axis button if already configured.
* The matrix summary updates.

Run Experiment behavior:

* If current inputs can be adapted to existing experiment setup/matrix compiler safely, wire it.
* If the adapter is not safe yet, keep “Run Experiment” disabled with a precise reason.
* Do not create fake experiment records.
* The main implementation priority is the new shell + real migration; if experiment execution requires deeper backend work, leave it disabled with a real explanation and route users to Settings > Legacy for the old fully working experiment setup.

Important: disabling unavailable new buttons with clear reasons is acceptable. Fake success or fake output is not.

E. Feature registry

Implement a simple registry such as:

```
const FEATURE_SPECS = [
  {
    id: "txt2img",
    label: "Txt2Img",
    description: "...",
    supportsImageCanvas: false,
    controls: [...]
  },
  {
    id: "object_remove",
    label: "Object Remove",
    description: "...",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Brush refine"]
  },
  {
    id: "object_replace",
    label: "Object Replace",
    description: "...",
    supportsImageCanvas: true,
    futureTools: ["SAM click selection", "Text object selection", "Reference image"]
  }
]
```

Control definitions should include:

* id
* label
* type
* defaultValue
* min/max/step if numeric
* experimentEligible boolean
* feature applicability
* help text

This registry must drive the Playground controls. Do not hardcode every control only in render markup.

F. Backend preset abstraction

Implement a small frontend abstraction for backend options:

* Try to load existing profiles/presets/bootstrap data through existing `testing-api.js` helpers or related APIs.
* Normalize to:

  * id
  * label
  * feature compatibility
  * source: existing profile/preset/fallback
  * disabled reason if unavailable
* If there is no reliable inventory, provide a real empty state.

Do not invent successful backends. Labels like Qwen/Flux/Z-Image are acceptable as design placeholders only if disabled or clearly marked “not configured” unless they correspond to real repo data.

G. History page

Create new Studio History page:

* Use existing run history API or old history module data path.
* Show:

  * ordinary runs
  * experiment_cell runs
  * warmups, optionally hidden behind filter
  * experiment groups if available
* Provide at least:

  * search/filter text input
  * filter by kind/status if easy
  * card/list view
  * selected detail pane
  * metadata panel: prompt, workflow, model stack, LoRAs, seed, steps, guidance, denoise, sampler/scheduler, output path, status, timings
  * open/copy output path if safe
  * show log/timing if existing endpoint supports it
* If no history exists, show a useful empty state.
* Do not make History only say “coming soon.” It must use real existing data.

If new History cannot yet show experiment matrix pages, it should at least group experiment cells by `experiment_id` and show count/status. Full matrix visualization can be future, but the group entries must be real.

H. Settings page

Create new Studio Settings page:
Sections:

1. Studio

   * UI state / diagnostics / version info where available.
2. Backends / Presets

   * Explain current preset/profile source.
   * Link/open Legacy Profiles.
   * Show existing profile/preset count if available.
3. Modal / Runtime

   * Show deploy/status summary if existing endpoint exists.
   * Link/open Legacy Dashboard/Settings.
4. Features

   * Show enabled feature specs: Txt2Img, Object Remove, Object Replace.
   * Object Remove/Object Replace show “canvas/mask tools not implemented yet.”
5. Legacy

   * Buttons/cards to open:

     * Legacy Dashboard
     * Legacy Setup
     * Legacy Profiles
     * Legacy Results
     * Legacy History
     * Legacy Settings

The Legacy buttons must actually render old modules. This is required.

I. Legacy rendering

Do not leave legacy as dead links.

Implement one of these:
Option 1, preferred:

* `studio-legacy.js` exports a function that takes a legacy tab id and container, then lazy-loads the same old module exports used by old `modal-testing.js`.
* It passes the same `apiBase`, draft state, experiment id, callbacks, and setup adapter behavior needed by old modules.
* It wraps the old module in a “Legacy / <tab>” panel with a Back to Settings button.

Option 2:

* Keep the old shell builder under a hidden legacy modal.
* Settings > Legacy opens old shell on the requested tab.
* The old shell must not be the default entrypoint and must not show as the main Studio nav.

Preferred behavior:

* Legacy opens inside the Studio body, not as a separate modal, unless embedding old modules is too risky.

Do not duplicate old logic unnecessarily. Reuse the current `TAB_MODULES` mapping concept from `modal-testing.js`.

J. Styling

Create Studio-specific CSS/classes:

* Avoid global pollution.
* Do not break existing testing styles.
* Preserve old styles for legacy modules.
* Studio should be dark, compact, and professional.

Must-have style structure:

* `.comfymodal-studio-overlay` or reuse existing modal overlay safely.
* `.comfymodal-studio-modal`
* `.comfymodal-studio-header`
* `.comfymodal-studio-topnav`
* `.comfymodal-studio-body`
* `.comfymodal-studio-playground`
* `.comfymodal-studio-control-panel`
* `.comfymodal-studio-workspace`
* `.comfymodal-studio-canvas`
* `.comfymodal-studio-filmstrip`
* `.comfymodal-studio-card`
* `.comfymodal-studio-axis-popover`
* `.comfymodal-studio-history`
* `.comfymodal-studio-settings`
* `.comfymodal-studio-legacy`

Design:

* Top nav height around 48-60px.
* Left control panel around 300-380px wide.
* Right workspace fills remaining width.
* Avoid vertical scrolling in normal 1080p view; if necessary, make only the left panel internally scroll, not the whole modal.
* Use compact labels, sliders, number inputs, small help text.
* Use disabled states clearly.
* Use honest empty states.

K. API and backend

Do not rewrite backend infrastructure. Use existing endpoints/helpers wherever possible.

If new convenience endpoints are needed, add thin adapters only. Examples:

* `/comfymodal/studio/bootstrap`
* `/comfymodal/studio/history`
* `/comfymodal/studio/history/{run_id}`
* `/comfymodal/studio/experiments`
* `/comfymodal/studio/features`
* `/comfymodal/studio/presets`

But do not add endpoints just to return fake data. If an endpoint returns a feature registry, it can return static real registry data. If it returns presets, it must come from existing presets/profiles or clearly return empty.

Backend changes should be minimal. This is primarily a frontend migration with safe adapters.

L. Tests

Before changing tests, inspect current tests:

* `tests/test_testing_shell_integration.py`
* `tests/test_testing_ui_wired.py`
* `tests/test_testing_settings_js.py`
* `tests/test_testing_results_js.py`
* `tests/test_testing_history.py` or similarly named tests
* `tests/browser/modal_testing_suite_smoke.mjs`
* route registration tests
* experiment/history tests

Update/add tests to assert the new product contract.

Required tests:

1. Studio shell test:

   * Main nav has Playground, History, Settings.
   * Main nav does not show Dashboard, Setup, Profiles, Results.
   * Modal/launcher still opens.

2. Playground render test:

   * Playground is default.
   * It has left control panel and right workspace.
   * Experiment button appears at the top of the left panel.
   * Feature options include Txt2Img, Object Remove, Object Replace.
   * Prompt, steps, guidance, denoise, seed, LoRA, LoRA strength, mask blur, mask expansion controls exist where expected.

3. Experiment mode test:

   * Pressing Experiment toggles experiment mode.
   * Compare Backends section appears.
   * Existing knobs gain axis checkboxes.
   * There is no standalone “Test Axes” list.
   * Axis editor appears for a selected knob.
   * Matrix summary updates when axes/backends are selected.

4. History test:

   * New History page renders real data from existing history API or displays a correct empty state.
   * It can represent ordinary and experiment_cell kinds if sample data exists.

5. Settings/Legacy test:

   * Settings page has Legacy section.
   * Legacy Dashboard/Setup/Profiles/Results/History/Settings entries exist.
   * Clicking a legacy entry actually lazy-loads or opens the old module.
   * Old modules remain reachable.

6. Regression tests:

   * Existing backend tests for experiment store, matrix compiler, run history, scheduler, runner must still pass.
   * Do not weaken backend correctness tests to make frontend changes pass.

7. Browser smoke test:

   * Update browser smoke to open Modal Studio.
   * Check top nav.
   * Toggle Experiment.
   * Open Settings > Legacy > Setup or Dashboard.
   * Open History.

M. Implementation order

Follow this order exactly unless Explorer finds a hard dependency issue:

1. Explorer maps current frontend shell:

   * current modal entrypoint
   * old tab module exports
   * old draft state behavior
   * old result/history/settings data paths
   * current test expectations

2. Oracle reviews the migration plan:

   * verify old modules can be embedded
   * identify API risks
   * identify tests that need updating
   * verify no product-scope ambiguity remains

3. Implement Studio styles without removing old styles.

4. Implement feature registry and small UI helpers.

5. Implement Studio shell:

   * top nav
   * page routing
   * default Playground
   * launcher compatibility

6. Implement Playground normal mode:

   * left controls
   * right workspace
   * feature switcher
   * disabled honest placeholders for image-edit-only tools
   * run button behavior safe and honest

7. Implement Playground experiment mode:

   * compare backends
   * axis checkboxes on existing knobs
   * axis editor
   * matrix summary
   * no separate Test Axes list

8. Implement new History:

   * fetch/list real history
   * display cards/list
   * show detail metadata
   * group experiment cells minimally

9. Implement new Settings:

   * sections
   * status summaries where available
   * Legacy entries

10. Implement Legacy renderer:

* reuse old lazy module imports
* preserve old setup draft behavior as much as possible
* ensure old Setup/Results flow still works

11. Update tests.

12. Run tests and fix failures.

N. Acceptance criteria

The work is not complete until all of these are true:

* Opening the Modal GPU / Modal Studio launcher shows the new Studio shell.
* Top nav only shows Playground, History, Settings.
* Playground is default.
* Playground has the left vertical control panel and right workspace layout.
* The canvas/image-edit area honestly says future image editing tools are not implemented yet; no fake working mask tools exist.
* Experiment button is at the top of the left controls.
* Experiment mode adds Compare Backends and checkboxes next to existing knobs.
* Experiment mode does not show a standalone “Test Axes” list.
* Axis editor supports Prompt and numeric knobs at minimum.
* History page is real and uses existing history data or real empty state.
* Settings page is real.
* Settings > Legacy can open all old screens:

  * Dashboard
  * Setup
  * Profiles
  * Results
  * History
  * Settings
* Old backend experiment/history systems are not broken.
* Tests are updated to match the new UI.
* No fake successful runs, fake generated outputs, fake backend availability, or fake experiment records are introduced.
* No secrets are logged or persisted.
* The implementation remains simple and easy to extend.

O. Definition of “no stubs”

Allowed:

* Honest disabled controls that say “Not implemented yet.”
* Honest placeholder text in the canvas for future SAM/mask/image-edit tools.
* Static feature registry for real planned features.
* Empty states when no data exists.
* Thin adapter functions that return real existing data or real empty responses.

Not allowed:

* Buttons that appear to run but do nothing.
* Fake generated images.
* Fake successful backend presets.
* Fake experiment IDs.
* Fake history entries.
* Fake logs/timings.
* Dead legacy links.
* Asking the user which migration style, which pass, or whether to preserve old flows.

P. Final report required

At the end, provide:

* Starting commit SHA.
* Ending commit SHA if a commit was made, otherwise final working tree state.
* Files changed.
* Summary of architecture.
* How to add a new Playground feature.
* How to add a new control/experiment axis.
* How legacy screens are loaded.
* What is intentionally deferred.
* Exact commands/tests run and results.
* Any remaining risks or known limitations.
