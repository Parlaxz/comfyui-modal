# Studio Workflow and Experiment Implementation Checklist

## Before code

- [ ] Keep the approved Shelf prototype as the visual/interaction baseline.
- [ ] Create and lint the Unlazy ledgers under `.unlazy/studio-workflow-experiment-friction-reduction/`.
- [ ] Confirm leaf ownership and disjoint write scopes.

## Bindable inputs and blocks

- [ ] Add the code-owned bindable-input dictionary with fixed canonical names.
- [ ] Implement Prompt, Seed, Step count, CFG scale, Sampler, Model UNET, VAE, and CLIP entries.
- [ ] Implement reusable text, multiline, integer, float, dropdown/set, and model blocks.
- [ ] Encode fixed integer/float rules, including negative Seed and non-negative dimension values.
- [ ] Preserve one bindable input to one exact node/widget binding.
- [ ] Add focused unit coverage.

## Workflow creation and storage

- [ ] Route file import into Workflow creation.
- [ ] Route link import into the same Workflow creation path.
- [ ] Copy the source graph into a new static Workflow.
- [ ] Show suggestions without silently confirming bindings.
- [ ] Require Prompt, Seed, Model UNET, VAE, CLIP, and Output before T2I save/run.
- [ ] Keep unsupported graph inputs outside the Studio wrapper.
- [ ] Implement durable autosave through the Workflow domain authority.
- [ ] Implement Workflow bundle export/import without history, images, or experiment drafts.

## Workflow picker and settings

- [ ] Build one folder/search Workflow picker shared by Playground and Workflows tab.
- [ ] Use mode-specific actions without duplicating picker behavior.
- [ ] Add single-run Workflow switching confirmation and matching-value reuse choice.
- [ ] Load each Workflow’s own fields/layout and mark old output stale after switching.
- [ ] Add Workflow Settings allowed-options filters.
- [ ] Ensure filters limit choices without disabling experiment axes.

## Shelf Playground

- [ ] Remove Backend and Preset controls from the user-facing flow.
- [ ] Keep Prompt fixed at the top of the sidebar.
- [ ] Keep Output/progress/metadata/recent results in the right workspace.
- [ ] Render only fields bound by Workflow creation.
- [ ] Support drag handles, Advanced placement, same-row grouping, and autosave.
- [ ] Render useful controls without decorative type/description clutter.
- [ ] Autosave normal field content.

## Experiment mode

- [ ] Add `Experiment` / `Exit Experiment` toggle.
- [ ] Show axis selectors only when Experiment mode is enabled.
- [ ] Select multiple Workflows through the Workflow picker.
- [ ] Calculate common compatible fields as possible axes.
- [ ] Show unique fields in hidden per-Workflow sections.
- [ ] Dim non-axis fields and highlight active axes in blue.
- [ ] Add Enter-to-create removable value pills.
- [ ] Preserve full prompt text on pill hover.
- [ ] Apply Random/Increment/Decrement/Empty to integer and float fields.
- [ ] Preserve and improve the existing matrix, output, History, cancel, and retry contracts.
- [ ] Autosave experiment-only state as local draft.

## Cleanup and verification

- [ ] Prove new callers before removing legacy `/studio/run` and preset authority.
- [ ] Remove unreachable legacy branches and update only obsolete tests.
- [ ] Run focused Playwright coverage for the full journey.
- [ ] Run one real serialized ComfyUI graph/API-prompt capture path.
- [ ] Run the FAST_UNIT path.
- [ ] Verify keyboard navigation, focus visibility, and responsive sidebar/output behavior.
- [ ] Reverify all Unlazy leaf and integration ledgers.
- [ ] Complete the final manual Shelf and end-to-end review.
