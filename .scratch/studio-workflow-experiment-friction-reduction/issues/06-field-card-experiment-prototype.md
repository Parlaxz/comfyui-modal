# Field Card Experiment Prototype

Status: claimed
Type: prototype
Blocked by: 04-role-binding-wizard-contract.md, 05-workflow-wrapper-contract.md

## Question

What cheap concrete interaction artifact best demonstrates the Playground’s experiment mode: saved required/advanced field cards, axis selection, non-axis treatment, typed value entry, value pills, matrix summary, and saved layout behavior, without mixing in workflow-creation binding?

## Prototype notes — not approved

The current prototype draft uses the existing Studio Playground structure as its baseline, not Compact/Focus/Matrix product modes. The Playground remains a horizontal split with a resizable, independently scrolling control sidebar on the left and the output workspace on the right. Output, progress, metadata, and recent results stay in the workspace.

Experiment mode is an explicit sidebar toggle: `Experiment` when off and `Exit Experiment` when on. Enabling it inserts the experiment surface above the ordinary backend/workflow/preset controls. That surface contains compare-preset selection, matrix summary, run readiness, and reset behavior. Disabling it removes the experiment surface while preserving normal Playground controls and output state.

Only experiment mode shows axis selectors beside eligible saved workflow controls. Selecting an axis replaces that control with an inline typed editor; non-axis controls remain visible and are visually secondary. Editors retain one initial value, allow additional values, and support removal. Numeric fields expose generic operations such as random, increment, decrement, and empty; prompt fields use textareas; schema-backed fields use dropdowns.

Pressing Enter in an axis editor creates a value pill below that field. Prompt pills preserve the full prompt in a title/hover affordance and can be removed. Pills represent axis values, not compared presets. Matrix summary and run gating remain in the sidebar; the two valid run paths are multiple unique presets or one preset with an axis containing at least two values.

Workflow binding remains exclusively in workflow creation. This prototype does not define binding controls or wizard states. The three exploratory variants are not product modes. These are working notes only and are not an approved decision.
