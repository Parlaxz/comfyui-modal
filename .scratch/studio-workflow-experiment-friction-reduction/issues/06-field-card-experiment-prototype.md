# Field Card Experiment Prototype

Status: resolved
Type: prototype
Blocked by: 04-role-binding-wizard-contract.md, 05-workflow-wrapper-contract.md

## Question

What cheap concrete interaction artifact best demonstrates the Playground’s experiment mode: saved required/advanced field cards, axis selection, non-axis treatment, typed value entry, value pills, matrix summary, and saved layout behavior, without mixing in workflow-creation binding?

## Answer

The approved prototype uses the existing Studio Playground structure as its baseline, not Compact/Focus/Matrix product modes. The Playground remains a horizontal split with a resizable, independently scrolling control sidebar on the left and the output workspace on the right. Output, progress, metadata, and recent results stay in the workspace.

Experiment mode is an explicit sidebar toggle: `Experiment` when off and `Exit Experiment` when on. Enabling it inserts the experiment surface above the ordinary Workflow controls. That surface contains Workflow comparison, matrix summary, run readiness, and reset behavior. Disabling it removes the experiment surface while preserving normal Playground controls and output state.

Only experiment mode shows axis selectors beside eligible saved workflow controls. Selecting an axis replaces that control with an inline typed editor; non-axis controls remain visible and are visually secondary. Editors retain one initial value, allow additional values, and support removal. Numeric fields expose generic operations such as random, increment, decrement, and empty; prompt fields use textareas; schema-backed fields use dropdowns.

Pressing Enter in an axis editor creates a value pill below that field. Prompt pills preserve the full prompt in a title/hover affordance and can be removed. Pills represent axis values, not Workflows. Common fields across the selected Workflows can be axes; Workflow-specific fields appear hidden by default in each Workflow’s separate section and can be set but not made axes. Matrix summary and run gating remain in the sidebar; comparison runs multiply selected Workflows by axis values.

Workflow binding remains exclusively in workflow creation. This prototype does not define binding controls or wizard states. The three exploratory variants are not product modes; Shelf is the approved baseline. The human explicitly approved this direction after the final corrections.

The initial T2I save/run gate is confirmed as Prompt, Seed, Model UNET, VAE, CLIP, and Output binding. Step count, CFG scale, and Sampler are optional bindable inputs.
