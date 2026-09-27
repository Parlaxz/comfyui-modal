# Implementation Acceptance Contract

Status: resolved
Type: grilling
Blocked by: 01-legacy-studio-audit.md, 04-role-binding-wizard-contract.md, 05-workflow-wrapper-contract.md, 06-field-card-experiment-prototype.md, 07-durable-save-import-export-contract.md

## Question

What is the final implementation acceptance contract for the core end-to-end flow, spec-sheet and checklist artifacts, focused Playwright E2E, real graph capture/import evidence, the existing experiment/history contract, and Unlazy gates?

## Answer

The primary acceptance journey is: import a file or link; enter workflow creation; manually bind Prompt, Seed, Model UNET, VAE, CLIP, and Output; autosave the new Workflow; select it through the folder/search Workflow picker; run it in the Shelf Playground with output on the right; switch Workflows through the picker; enable Experiment mode; select multiple Workflows; expose common fields as axes and keep unique fields hidden in per-Workflow sections; enter axis values as removable pills; run the matrix; and inspect results through the existing matrix, output, and History surfaces. The existing matrix presentation is the base to improve, not replace.

Focused Playwright coverage must exercise import into the wizard, mandatory binding and save blocking, Workflow picker folders/search and switching, autosave/reload recovery, single-run output, Experiment toggle, Workflow comparison, common versus unique fields, axis values/pills, matrix run gating, and existing result/history behavior. UI tests may use deterministic fake APIs, but at least one path must use a real serialized ComfyUI graph/API prompt through graph capture, binding, persistence, and execution validation.

The implementation must ship a product spec sheet, feature checklist, and Unlazy gates. Gates must cover the role-binding/save boundary, bindable-input rendering, Workflow autosave and bundle round-trip, Shelf single-run switching, Experiment workflow comparison and matrix behavior, right-side output/history, legacy cleanup, keyboard/focus/responsive behavior, and the FAST_UNIT path. The gate ledger must distinguish fake-browser evidence from real graph evidence and must not claim completion from a successful process exit alone.

Legacy Backend/Preset UI and the obsolete legacy run/preset authority are removal targets. Remove them only after the new Workflow path and focused tests prove their callers are replaced; do not add old-data migration. Keep the existing experiment/history contract and improve its UI rather than creating a second result system.
