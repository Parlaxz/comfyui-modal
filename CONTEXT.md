# Studio Workflow Domain

## Glossary

- **ComfyUI workflow**: The underlying node graph that describes an image-generation process.
- **Studio workflow wrapper**: The single user-facing workflow representation that makes one ComfyUI workflow usable by exposing only meaningful controls and experiment choices.
- **Role binding**: An explicit association between a Studio semantic role and the exact node field or output that fulfills it in the underlying workflow.
- **Mandatory T2I role**: A role that must have a confirmed, valid binding before a T2I Studio workflow can be saved or run: positive prompt, primary image output, seed, UNet/diffusion model, VAE, and CLIP/text encoder.
- **Optional T2I role**: A role that may be exposed when present but is not required for the initial T2I contract, including sampler and negative prompt.
- **Primary output**: The one image output selected as the result of a Studio workflow when the underlying graph exposes multiple outputs.
- **Model set**: A coherent group of model components presented together when the workflow explicitly declares their relationship; component choices remain individually understandable.
- **Workflow draft**: Unfinished wrapper configuration that may be recovered while being edited but is not a saved or runnable Studio workflow.
- **Experiment axis**: A field selected for variation while other workflow fields remain fixed for an experiment matrix.
- **Advanced field**: A reusable typed field card for a bound role or input, with shared value and experiment behavior rather than node-specific UI.
- **Role profile**: The workflow-type definition of mandatory and optional roles, field types, and output rules used by the agnostic wrapper wizard.
- **Static graph copy**: The immutable ComfyUI graph captured into one Studio workflow wrapper; changing the graph creates a new wrapper rather than mutating the existing one.
- **Workflow creation wizard**: The workflow-authoring surface where graph roles are bound and the wrapper’s field surface is defined; binding does not happen in the Playground.
- **Playground**: The saved-wrapper runtime surface where users edit exposed fields, run the workflow, and enter experiment mode.
- **Experiment mode**: The Playground state where users select axes, enter typed values, create value pills, and preview or run the resulting matrix.
- **Value pill**: A removable, visible value in an axis field’s collection; prompt pills expose their full text on hover without replacing the field editor.
- **Bound field**: A field card made available to the Playground because the workflow-creation wizard bound it; the Playground does not create new fields.
- **Workflow-type layout profile**: The saved arrangement rules for a workflow type, including field order, Advanced membership, and row grouping. Layout changes autosave through the workflow configuration.
- **Workflow comparison set**: The workflows selected together in Experiment mode for comparative runs; this is distinct from the removed preset concept.
- **Output panel**: The unique Playground result surface on the right; it is not a movable field card.
- **Prompt anchor**: The fixed, top-positioned Prompt field card in the Playground.
- **Movable bound field**: Any bound field other than the Output panel and Prompt anchor; it can be placed in Advanced, reordered, or grouped into a row.
- **Workflow settings**: The wrapper-level settings surface where each field’s allowed options are filtered, such as limiting a workflow to selected UNets; these filters do not prevent the field from being an experiment axis.
- **Allowed-options filter**: A workflow-specific restriction that limits a field to one or more values from the available set. It is a compatibility/choice filter, not an experiment lock.
- **Advanced field**: An extra control that was already set up for a workflow in workflow creation; the Playground displays and arranges it but does not invent it.
- **Number field**: A reusable numeric control whose value is either an integer or a float; experiment actions such as random, increment, and decrement apply to both kinds.
- **Workflow picker**: The folder/search UI for selecting saved Studio workflows in the Playground or managing them in the Workflows tab.
- **Field building block**: A coded, reusable control implementation tied one-to-one to a basic workflow input kind, such as integer, float, dropdown, or model. Its allowed parameters are defined by the product, not customized per field by users.
- **Field parameters**: Fixed rules supplied by a building block for a specific field instance, such as allowing negative integers for Seed or requiring non-negative integers for Width and Height.
- **Canonical input dictionary**: The code-owned mapping from a supported workflow input name to its building block and fixed rules; the wizard exposes these supported inputs rather than choosing or customizing their types.
- **Common experiment variable**: A canonical field present and compatible in every workflow selected for an experiment; only common variables can be axes.
- **Workflow-specific experiment variable**: A field present in only some selected workflows; it appears in a separate area and can be set, but cannot be an axis.
