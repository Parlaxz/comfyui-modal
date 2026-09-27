# Studio Workflow and Experiment Friction Reduction

## Purpose

Make ComfyUI workflows easy to configure, run, compare, and experiment with in Studio without exposing graph clutter or obsolete Backend/Preset concepts.

## Workflow creation

- Importing a file or link opens Workflow creation.
- The imported ComfyUI graph is copied into a new static Studio Workflow.
- The wizard exposes only the code-owned bindable-input catalog.
- Suggestions point to likely node widgets, but the user selects the exact widget or field.
- T2I save/run requires Prompt, Seed, Model UNET, VAE, CLIP, and Output binding.
- Step count, CFG scale, and Sampler are optional bindable inputs.
- Output is a required binding to the primary result node, not a Playground input block.
- Unsupported graph inputs remain outside the Studio wrapper.

## Bindable inputs

Each bindable input has a fixed canonical name, one exact node/widget binding, and one coded Playground block. The initial catalog is Prompt, Seed, Step count, CFG scale, Sampler, Model UNET, VAE, and CLIP.

Initial blocks are multiline prompt/text, integer, float, dropdown/set, and model picker. Rules are coded, not user-customized: Seed uses integer and permits negative values; inputs such as Width and Height can use integer with a non-negative rule. New capabilities add catalog entries, binding rules, blocks, and experiment behavior without changing existing blocks.

## Shelf Playground

- The left side contains the selected Workflow’s bound field cards.
- Prompt stays fixed at the top.
- Output is the right-side result panel, not a movable card.
- Every other bound field can be dragged into Advanced, reordered, or placed beside another field in the same row.
- Layout follows the Workflow type, supports per-Workflow overrides, and autosaves.
- Normal field content autosaves to the Workflow.
- A Workflow button opens a folder/search picker. Switching Workflows prompts whether to reuse matching current field values; the new Workflow’s fields and layout then load.
- The right output panel marks previous output stale after a Workflow switch until a new run completes.

## Experiment mode

- An `Experiment` button toggles to `Exit Experiment`.
- When enabled, the user can select multiple Workflows through the picker.
- Fields common and compatible across selected Workflows may become axes.
- Workflow-specific fields appear in hidden per-Workflow sections; they can be set but cannot become axes.
- Axis fields receive a blue active state; non-axis fields dim without disappearing.
- Entering a value creates a removable pill below that field. Prompt pills expose their full text on hover.
- Integer and float fields share generic Random, Increment, Decrement, and Empty operations.
- Runs multiply selected Workflows by axis values. Results use the existing matrix, output, and History surfaces.

## Workflow Settings and portability

- Workflow Settings contain allowed-options filters for fields such as UNet and Sampler.
- A filter may allow one or several choices, but does not prevent the field from being an experiment axis.
- Workflow content and layout autosave durably through WorkflowDomainStore/API.
- Experiment selections, axes, pills, and experiment-only values autosave as local draft state without overwriting Workflow values.
- Every file/link import creates a new Workflow and never silently replaces an existing one.
- Export includes the static graph, Workflow type, bindings, values, layout, and allowed-options filters. It excludes generated images, run history, and experiment drafts.
- No old-data migration is included.

## Cleanup boundary

After the new path is proven, remove Backend/Preset UI, legacy `/studio/run`, legacy preset authority, and unreachable legacy branches. Keep the existing experiment/history engine and improve its presentation rather than introducing a second result system.

## Evidence

Completion requires focused Playwright coverage, at least one real serialized ComfyUI graph/API-prompt capture path, FAST_UNIT verification, responsive/keyboard/focus checks, and current Unlazy gates.
