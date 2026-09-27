# Studio QA Defect Repairs Design

## Goal

Repair every major failure found in the Playwright Studio QA pass while preserving persisted runs, snapshots, presets, and annotations.

## Scope

### Preset and Playground contracts

- Resolve a preset's snapshot, API prompt, bindings, control schemas, and defaults before the Playground renders controls.
- Include every supported Txt2Img control in the feature registry, including width and height.
- Derive defaults from the referenced snapshot when a preset has no explicit default, preserving scalar values and enum selections.
- Persist the selected preset and its last successful run independently per browser origin and restore the selected preset, controls, image, and metadata after reload.
- When a selected preset is deleted, select a remaining runnable preset or show the empty state without retaining a dangling selection.

### Execution and validation

- Normalize values only through the declared control schema before workflow injection. Reject list-valued scalar controls with a field-specific validation error.
- Reject empty required bindings, including prompt, before a run is accepted.
- Keep `0`, `false`, and other valid zero-like values intact through request normalization, workflow injection, resolved controls, UI rendering, and history storage.
- Emit progress that is scoped by Studio run or experiment ID and distinguishes queue/startup, workflow-node, sampler-step, and terminal states.

### Timing and metadata

- Preserve known timing values with their source and quality labels.
- Render unavailable canonical timing stages as unavailable rather than deriving or relabelling them.
- Keep scheduler wall-clock timing distinct from sampler timing.

### Experiments

- Calculate axis eligibility from the selected runnable presets and their normalized control bindings.
- Enable an axis when every selected runnable preset supports that control; otherwise show the explicit reason.
- Preserve experiment-scoped progress and terminal state when unrelated ComfyUI or Playground work is active.

### History and annotations

- Make history type, search, preset, feature, date, image, favorite, and status filters map exactly to the API contract.
- Use backend-provided totals for pagination and bound next/previous navigation to valid offsets.
- Treat a selected date's end boundary as inclusive through the end of that date.
- Update the shared selected-run record after a successful History annotation save so Playground and History show the same note and favorite state.
- Leave persisted annotation data unchanged and show `Save failed` if its request fails.

## Architecture

The backend remains the source of truth for snapshots, presets, runs, histories, annotations, validation, and execution progress. `studio_run_adapter.py` supplies one normalized preset and execution contract to the browser. The browser keeps an origin-scoped UI draft/cache but must rehydrate it from the normalized backend contract before rendering controls.

`studio-playground.js` owns selected-preset hydration, control rendering, run state, and result restoration. `studio-history.js` owns query construction, valid pagination, and annotation mutation. `studio-experiment-mode.js` owns selected-preset compatibility and experiment UI only; it receives normalized capability data rather than recreating binding rules.

## Error handling

- Validation failures are returned before queueing, identify the affected control or required binding, and create a truthful failed run only after the backend has accepted execution.
- Failed annotation saves retain the local edit in the editor, display failure state, and do not alter shared persisted metadata.
- Missing snapshot, schema, binding, or deleted-preset references result in a stable empty/disabled state with an explicit reason; no generic control values are substituted.

## Testing

- Add Python regression tests for scalar control normalization, required prompt validation, preset default derivation, history filtering/pagination/date behavior, and progress/timing payloads.
- Add deterministic browser tests for the saved-workflow initial controls, width/height controls, zero-like runs, reload restoration, history annotation synchronization, filter/pagination behavior, and experiment-axis eligibility.
- Each behavior follows red-green-refactor: add one failing test, run it to confirm the expected failure, make the minimal repair, then run its focused suite and the relevant regression suite.

## Non-goals

- No Studio rewrite or new state-management framework.
- No guessed timing stages or changes to legacy record format beyond backward-compatible normalization.
- No changes to unrelated ComfyUI execution behavior.
