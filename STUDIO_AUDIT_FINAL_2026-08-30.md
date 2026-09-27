# Modal Studio End-to-End Audit

**Date:** 2026-08-30  
**Scope:** current Studio shell, Workflows/Model Library, Backend workspace operations, History V2, Experiment V2, return paths, legacy residue, and visual/style quality.  
**Production changes:** none.  
**Live runtime:** unavailable; `http://127.0.0.1:8188` returned `ERR_CONNECTION_REFUSED`.

## Evidence and confidence

| Evidence | Use | Limitation |
|---|---|---|
| Current source and route handlers | authoritative implementation behavior | graph metadata is stale/changed, so native source was used |
| Existing unit/browser tests | deterministic contract coverage | not every requested journey has a named acceptance test |
| Fake Studio harness on port 8377 | rendered UI and interaction observations | not proof of live ComfyUI/Modal integration |
| Existing Phase H closure reports | legacy retirement and gate history | closure evidence predates this audit and the tree remains intentionally dirty |

The existing closure gate is recorded as **Python 2124/2124, Node 25/25 files, Fake Playwright 211/211**. The known fake-suite parallel-load timeout is documented as an environmental flake and was not weakened. Focused validation against the current tree additionally found one stale Python assertion and two routing-contract assertions: `tests.test_studio_backend.BackendTabOrderTests.test_default_tab_is_presets` still requires the old literal `activeTab = "overview"`, while `tests/studio_phase_i2_shell_nav_accessibility_unit.mjs` and `tests/studio_phase_i9_routing_unit.mjs` correctly flag direct routing calls in `web/studio-settings.js:616-632`. The current implementation resolves the Backend default through `resolveInitialTab()` and the Settings workspace link still performs a working navigation sequence, but its URL mutation violates the shell-owned routing contract. These findings were documented rather than changed because this audit authorized no production or test edits.

## Requested journeys

### 1. Create a new Krea2 workflow using an external safetensors link — **PARTIAL**

What works:

- Import the current ComfyUI graph or create an empty workflow: `web/studio-workflows.js:909-1087`.
- Edit workflow metadata, including source URL and compatible models: `web/studio-workflows.js:1690-1818`; server accepts `source_url` and `compatible_models` at `studio_workflow_routes.py:250-305`.
- A missing `krea_model.safetensors` dependency exposes its source URL and a **Find in library** handoff: `web/studio-model-library.js:865-894`.
- Model details allow source URL editing and an explicit approval request: `web/studio-model-library.js:621-685,696-751`.

What is missing:

- No Krea2-specific workflow creation flow.
- No direct “create workflow from external safetensors URL” action.
- The download action records approval; it explicitly does not fetch or install the file.
- No tested end-to-end path proves external link → installed model → runnable workflow.

### 2. Swap workspaces — **PASS**

Backend owns the server-authoritative workspace registry and active identity. Add/edit, activation, swap review, prompt-running confirmation, cancellation, polling, repair-required handling, and failure preservation are implemented in `web/studio-backend-workspaces.js:170-275,287-456` and `:458-530`. The browser does not invent a new active workspace after a failed mutation.

### 3. Swap workflows — **PASS**

Playground exposes Workflow, Version, and Preset selectors. Selecting a workflow resets dependent selection, loads versions/run context/presets, and resolves the default preset; selecting a version repeats the dependent reload and resets controls: `web/studio-workflow-run.js:268-388`. Workflow library/detail navigation and state preservation are in `web/studio-workflows.js:438-485`. Browser coverage exists in `tests/browser/studio-workflows.spec.mjs` and unit coverage in `tests/studio_workflow_run_unit.mjs`.

### 4. Create and use workflow folders — **PARTIAL**

Folders can be assigned as string paths during manual creation/editing and selected from the Workflows folder tree: `web/studio-workflows.js:729-755,986-1007,1690-1818`. The API exposes list-only folder discovery (`studio_workflow_routes.py:315-322`). There is no explicit folder create, rename, delete, or move operation; folders are implicit metadata paths.

### 5. View history specific to a workflow/folder — **PARTIAL**

History V2 supports workflow and preset filters, date ranges, status/kind/image filters, and persisted view state: `web/studio-history-v2.js:321-364,380-395,891-938`. Generation detail exposes workflow/preset provenance. There is no folder-aware History filter and no folder-to-history query. Folder filtering exists only on Workflows (`web/studio-workflows.js:489-503`).

### 6. View clean image metadata — **PASS**

Generation detail separates the image/asset area from readable metadata. It shows seed, steps, CFG, guidance, sampler, scheduler, denoise, dimensions, workflow, preset, model list, IDs, timestamps, attempts, errors, export state, notes, and timing: `web/studio-history-v2-detail.js:57-75,1174-1257`. Original viewing is explicit and does not eagerly fetch Original bytes (`:613-706`). Close, backdrop, layered Escape, and focus restoration are implemented at `:147-245`.

### 7. Run four workflows with the same prompt/seed/sampler — **FAIL in the current Studio UI**

The current Experiment UI compares selected backend/runtime presets and varies eligible preset-driven controls. The modern definition serializes exactly one selected Workflow/Version/Preset identity in its `workflows` list: `web/studio-experiment-mode.js:1070-1114`. It does not expose a Workflow axis or a four-workflow selector. The backend planner has workflow-axis concepts (`experiment_modern_plan.py:58-67,245-331`), but that capability is not wired to this Studio interaction. This requested flow therefore requires a product/UI addition, not merely a test.

### 8. Run one workflow with different models — **PARTIAL**

Model choices are represented in Workflow Preset controls and the Model Library/dependency system. Experiment axes can be added to preset-driven controls (`web/studio-playground.js:780-826`; `web/studio-experiment-mode.js:430-857`). However, Workflow-domain mapped controls are rendered separately and do not receive the experiment-axis checkbox enhancement (`web/studio-playground.js:1644-1657`). A one-workflow/multi-model experiment is therefore not a complete, directly discoverable flow for the selected Workflow/Version path. No dedicated acceptance test exists.

### 9. Run one workflow with different seeds — **PARTIAL**

Seed is a first-class control and has experiment-axis editing, including increment/decrement/random insertion: `web/studio-experiment-mode.js:694-799`; History records seed in its Parameters section (`web/studio-history-v2-detail.js:57-67,759-774`). The same Workflow-domain limitation applies: mapped workflow controls do not expose axis checkboxes (`web/studio-playground.js:1644-1657`). This is supported in the preset-driven experiment path, but not proven as a complete one-workflow/variable-seed Workflow-domain journey.

## Return paths and escape behavior

- **All Studio pages:** five-button top navigation plus browser Back/Forward hash routing: `web/studio-shell.js:34-40,191-215,308-321`.
- **Workflow import/create:** backdrop, Cancel, and Escape: `web/studio-workflows.js:911-1015,923-943`.
- **Manifest import:** backdrop and Close: `web/studio-workflows.js:1113-1195`.
- **Workflow detail/edit/mapping/preset:** Back to Workflows and local Cancel/Close controls: `web/studio-workflows.js:474-485,1629-1638,1825,2100,2233,2334,2701,2851`.
- **Model detail:** backdrop and Cancel; model details are not left without a close route: `web/studio-model-library.js:575-694`.
- **Workspace form:** Cancel; swap confirmation/review: Cancel; repair/install panels: Close: `web/studio-backend-workspaces.js:289-326,458-530,630-640,716-730`.
- **History generation detail:** visible Close, backdrop click, layered menu Escape, dialog Escape: `web/studio-history-v2-detail.js:195-245,252-372`.
- **History experiment detail:** Back to history and menu Escape: `web/studio-history-v2-experiment.js:523-562,637-648`.
- **Experiment mode:** Exit Experiment returns to the normal Playground controls: `web/studio-experiment-mode.js:29-48`.
- **Image compare/preview layers:** Escape closes the highest active layer: `web/studio-image-compare.js:564-614`; shared layer handling is in `web/studio-ui.js`.
- **Outer Studio modal:** existing Cancel/Escape behavior remains in `web/modal-node.js:901-907`.

The source-level return-path audit found no audited modal or subpage with no visible or keyboard escape route. Live confirmation of those paths remains blocked by the unavailable live endpoint and unstable browser daemon.

## Current-tree validation delta

- **Historical closure evidence remains useful but is not a clean current-tree sign-off.** The focused checks above expose drift between the closure-era contracts and the present source/test tree.
- **Backend default-tab test drift:** `web/studio-backend.js:184-196` returns `"overview"` through `resolveInitialTab()` and honors valid backend focus deep-links; the test only searches for a removed literal assignment.
- **Settings routing ownership defect:** `web/studio-settings.js:616-632` directly calls `history.pushState()` and falls back to `location.hash`. This should be routed through the shell/routing helper in a follow-up, rather than weakening the I2/I9 tests.
- No production or test code was changed during this audit to resolve either finding.

## Legacy and relic classification

### Already retired or unreachable

- Old Studio History page, Dashboard/Setup/Profiles/Results/Settings frontend modules, old Comparison UI, old A/B slider, and legacy experiment creator/run surface were deleted or made unreachable in H9/H13/H18.
- Legacy creation/execution routes are intentionally inert (409/410); this is compatibility behavior, not a second active product.

### Deliberately retained compatibility/transitional seams

- History/read compatibility and migration-source stores/routes, including old run-history readers.
- Protected Single-run polling/cancel seams under `/experiments/{id}` and `stop-now`.
- Canvas `/prompt` interception, Local pass-through gate, Production marking, and output-option carrier.
- Backend/Runtime Presets (`.studio_presets.json`) until a separate convergence contract.
- Workspace fallback for old snapshots and legacy irreproducible-row handling.
- Inert registered compatibility routes and old user data; UI retirement does not delete historical data.

### Remaining optional hygiene

The Phase H handoff identifies zero-caller candidates such as `handle_studio_experiment`, `build_single_run_spec`, `__init__._collect_input_images`, and `createScopedTracker`, plus display-only Settings “Runtime & Backend” rows. None blocks the current Studio product and none should be removed without a separate scoped cleanup.

## UI/style audit

### Strengths

- The current dark compact visual direction is coherent with the Studio brief: top navigation, compact control rail, card/panel grouping, and a large workspace/result area.
- The five-page IA is explicit and single-owned in `studio-shell.js`; Experiments remain a Playground mode and History remains the durable result surface.
- Accessibility foundations are materially stronger than the retired UI: semantic nav, `aria-current`, keyboard-activatable cards, focus restoration, layered Escape, explicit labels, truthful status/live regions, and no data-bearing `innerHTML` in the audited modules.
- Empty, loading, incomplete, unavailable, and failed states generally explain the next action rather than silently failing.

### Friction and QoL opportunities

1. **IA/spec drift:** the older redesign brief describes three top-level pages, while the current product intentionally has five. Update the brief or treat it as historical; do not use it as current navigation truth.
2. **Folder lifecycle:** implicit string folders are adequate for basic grouping but do not support maintenance. Add explicit create/rename/move/delete only if users need managed taxonomy.
3. **History context:** add a folder-scoped history entry point or carry folder provenance into History filters; do not make users reconstruct it manually from workflow names.
4. **Experiment discoverability:** expose the supported matrix dimensions in one place and add a first-class Workflow axis if multi-workflow comparison is a product requirement. Current controls make preset axes clearer than Workflow-domain axes.
5. **Density/responsive behavior:** the compact toolbar and nested scrolling are efficient on desktop but become dense on narrow screens. Prior visual checks identified mobile nested-scroll and technical-label friction; a responsive nav/toolbar treatment is the highest-value visual follow-up.
6. **Terminology consistency:** normalize “Backend Preset”, runtime preset, Workflow Preset, and workspace wording. These are intentionally distinct authorities, but the UI should make that distinction obvious.
7. **Live QA affordance:** restore a working live ComfyUI endpoint/browser session before treating the source/fake results as a complete release sign-off.

## Final disposition

The current Studio architecture is coherent and substantially converged: five owned surfaces, V2-only modern execution, History V2 as durable history, Workflows as model/dependency/portability owner, Backend as operational owner, and Settings as preference owner. The audit found no unhandled return-path dead end in the inspected source.

The material product gaps are not general stability failures; they are the requested advanced workflow-management features:

- no direct external-safetensors-to-runnable Krea2 onboarding;
- no managed folder lifecycle;
- no folder-scoped History;
- no Workflow axis for four-workflow experiments;
- no complete Workflow-domain axis experience for model/seed variation.

These should be treated as Phase-I/product work rather than legacy cleanup. No production code was changed by this audit.
