# Plan: Studio Workflow & Experiment Friction Reduction

Scope: studio-workflow-experiment-friction-reduction
Depth: tree 3
Mode: orchestrated

## Contract

- Interfaces: code-owned bindable-input dictionary; one bindable input to one exact ComfyUI widget/field; separate required output binding; T2I required roles are Prompt, Seed, Model UNET, VAE, CLIP, and Output; optional inputs include Step count, CFG scale, and Sampler; Workflow comparison uses common canonical inputs as axes and hides unique inputs in per-Workflow sections; Workflow content/layout autosave durably; experiment state autosaves as local draft; file/link import creates a new static Workflow; export excludes output/history/experiment drafts.
- Ownership: each leaf owns a disjoint repository-relative path set listed in its ledger; the parent owns `.unlazy/**` and docs/spec artifacts; no concurrent leaf may write another leaf’s paths.
- Dependencies: bindable-input and Workflow-domain foundations launch first; Workflow creation/picker waits for both; Shelf Playground/Experiment waits for creation/picker; legacy cleanup waits for the full user flow.
- Host launch mode: Claude background Agents through the native task dispatcher.
- Wave policy: wave 1 launches foundation leaves 1.1.1 and 1.1.2 together; later waves roll forward as dependencies become VERIFIED; maximum 2 concurrent writers.
- Toolchain: Node/npm from `package.json`, Python project environment, Windows PowerShell, repository root as CWD. FAST verification uses `python tools/test_perf.py --fast -- tests -m fast_unit`; focused browser checks use the existing Playwright configs and mocked project; real graph evidence uses the existing ComfyUI capture path.
- Conventions: preserve existing experiment/History contracts; remove Backend/Preset only after replacement proof; no old-data migration; use explicit failure states; do not add a second executor, result store, or compatibility authority.
- Manual review: parent orchestrator reviews the Shelf UI, Workflow picker, binding affordances, accessibility, output placement, and real graph evidence; user-facing behavior is not certified from unit tests alone.

## Current contract inventory

Contract revision: 1

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Code-owned bindable-input catalog and reusable blocks | 1.1.1 | leaf-1.1.1:G1, G2 | ACTIVE | 1 |
| C2 | Fixed canonical names and one-to-one exact widget bindings | 1.1.1 | leaf-1.1.1:G3 | ACTIVE | 1 |
| C3 | Integer/float/text/dropdown/model behavior with fixed rules | 1.1.1 | leaf-1.1.1:G1, G3 | ACTIVE | 1 |
| C4 | Durable Workflow authority and autosave | 1.1.2 | leaf-1.1.2:G1, G3 | ACTIVE | 1 |
| C5 | Static graph import, file/link wizard entry, bundle round-trip | 1.2.1 | leaf-1.2.1:G1, G3 | ACTIVE | 1 |
| C6 | Required T2I role binding and save gate | 1.2.1 | leaf-1.2.1:G1, G3 | ACTIVE | 1 |
| C7 | Shared folder/search Workflow picker and mode-specific actions | 1.2.1 | leaf-1.2.1:G1, G3 | ACTIVE | 1 |
| C8 | Shelf single-run switching and stale-output behavior | 1.2.2 | leaf-1.2.2:G1, G3 | ACTIVE | 1 |
| C9 | Drag/group/autosave field layout and right-side output | 1.2.2 | leaf-1.2.2:G1, G3 | ACTIVE | 1 |
| C10 | Experiment toggle, Workflow comparison, common axes, unique fields | 1.2.2 | leaf-1.2.2:G1, G3 | ACTIVE | 1 |
| C11 | Typed value pills and generic number operations | 1.2.2 | leaf-1.2.2:G1, G2 | ACTIVE | 1 |
| C12 | Existing matrix/History/output behavior remains canonical | 1.2.2 | node-1.2:N3, N4 | ACTIVE | 1 |
| C13 | Legacy cleanup only after caller/test proof, no migration | 1.3.1 | leaf-1.3.1:G1, G3 | ACTIVE | 1 |
| C14 | Spec sheet and implementation checklist | parent | root:G3 | ACTIVE | 1 |
| C15 | Unlazy gates and FAST_UNIT/Playwright/real-graph evidence | parent | root:G1, G2, G3 | ACTIVE | 1 |

## State vocabulary

Leaf states: WAITING, READY, IN-FLIGHT, VERIFIED, or ABANDONED. Branch states: OPEN, VERIFIED, or ABANDONED.

## Tree

- 1 Studio Workflow & Experiment Friction Reduction .............. GATES.md
  - 1.1 Foundations .............................................. gates/node-1.1.md
    - 1.1.1 Bindable inputs and blocks ........................... gates/leaf-1.1.1.md
    - 1.1.2 Workflow domain and persistence ...................... gates/leaf-1.1.2.md
  - 1.2 User flows ............................................... gates/node-1.2.md
    - 1.2.1 Workflow creation and picker ........................ gates/leaf-1.2.1.md
    - 1.2.2 Shelf Playground and Experiment ...................... gates/leaf-1.2.2.md
  - 1.3 Cleanup and evidence .................................... gates/leaf-1.3.1.md

## Leaf dispatch table

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| 1.1.1 | `web/studio-bindable-inputs.js`, `web/studio-field-blocks.js`, `tests/studio_bindable_inputs_unit.mjs` | - | judgment | 1 | VERIFIED |
| 1.1.2 | `studio_domain/store.py`, `studio_domain/services.py`, `studio_workflow_routes.py`, `tests/test_studio_workflow_manifest.py`, `tests/test_studio_workflow_run_plan_identity.py` | - | judgment | 1 | VERIFIED |
| 1.2.1 | `web/studio-workflows.js`, `web/studio-preset-wizard.js`, `web/studio-workflow-picker.js`, `tests/browser/studio-workflows.spec.mjs`, `tests/browser/fake/fake-server.mjs`, `tests/browser/studio-workflows-mock.mjs`, `tests/browser/studio-mock-api.mjs` | 1.1.1, 1.1.2 | judgment | 2 | VERIFIED |
| 1.2.2 | `web/studio-playground.js`, `web/studio-experiment-mode.js`, `web/studio-playground-state.js`, `web/studio-styles.js`, `tests/browser/studio-playground.spec.mjs`, `tests/browser/studio-experiment.spec.mjs` | 1.2.1 | judgment | 3 | VERIFIED |
| 1.3.1 | `studio_routes.py`, `studio_run_adapter.py`, `studio_backend.py`, `comfymodal_runtime/publication_policy.py`, `tests/test_routes_registered.py`, `tests/test_studio_backend.py` | 1.2.2 | judgment | 4 | VERIFIED |

## Status log

Append lifecycle events with `node C:\Users\parla\.config\opencode\skills\unlazy\scripts\gate-check.mjs --scope studio-workflow-experiment-friction-reduction --log "event"`.
