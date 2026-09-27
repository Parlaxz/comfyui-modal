# Implementation Sequence and Ownership

Status: resolved
Type: grilling
Blocked by: none

## Question

What is the implementation order and ownership for the approved Workflow contract: bindable-input blocks, workflow creation and binding, durable autosave/import/export, the shared Workflow picker, Shelf Playground single runs and switching, Experiment comparison and matrix behavior, legacy cleanup, and the spec/checklist/Unlazy evidence?

## Answer

Implementation proceeds in these waves:

1. Write the spec sheet, feature checklist, and Unlazy acceptance ledgers before code changes.
2. Implement and test the code-owned bindable-input dictionary and reusable blocks. This owns the fixed canonical names, one-to-one widget bindings, integer/float rules, and Workflow-type required/optional role profiles.
3. Implement Workflow creation/import and exact binding. File and link imports enter the wizard, copy a static graph, require the T2I save gate, and autosave the resulting Workflow configuration.
4. Implement the durable Workflow store/API contract, bundle import/export, Workflow Settings allowed-options filters, and the shared folder/search Workflow picker. Playground selection and Workflows-tab editing use the same picker code with mode-specific actions.
5. Rebuild the Shelf Playground single-run path: Prompt anchor, bound fields, type blocks, drag-to-Advanced and same-row layout, workflow switching confirmation, autosave, and right-side output.
6. Integrate Experiment mode: Workflow comparison, common-field axes, hidden per-Workflow unique fields, typed value pills, generic number operations, matrix run readiness, and the existing matrix/History/output surfaces.
7. Run the full Playwright and real-graph evidence gates, then remove obsolete Backend/Preset UI, legacy `/studio/run`, legacy preset authority, and unreachable branches after caller/test proof.

Implementation ownership is separated by contract: bindable-input/block owner, Workflow creation/domain owner, picker/autosave owner, Shelf Playground owner, Experiment integration owner, and cleanup owner. The parent integration owner owns cross-lane interfaces, the end-to-end journey, spec/checklist updates, and final Unlazy verification. Independent bindable-input and domain/storage work may proceed in parallel; UI integration waits for their contracts. No lane adds migration or a second experiment/history system.
