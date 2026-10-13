# ComfyModal Studio V3 — Full Design & Implementation Runbook

**Status:** AUTHORITATIVE IMPLEMENTATION DOCUMENT  
**Repository:** `Parlaxz/comfyui-modal`  
**Accepted starting SHA:** `a4d19f24376a78d5f1c150ab495ff02883606c2b`  
**Accepted completed work:** Phase 1 — Three-mode shell and UI consolidation  
**Date:** 2026-10-13

This file is the complete design, implementation, batching, validation, and handoff contract for ComfyModal Studio V3.

It is intentionally standalone.

Older V1/V2 planning files are not required and should not be consulted. They may contain superseded assumptions and can pollute implementation decisions.

The implementation lead is a main GPT Sol agent. The lead may use read-only Explorer agents and bounded Fixer agents, but the lead owns the final design decisions, integrated code, visual validation, commit, push, and handoff for every phase.

---

# 0. Three sets of eyes

Every implementation phase must pass three distinct reviews.

## Eye 1 — Lead GPT Sol agent

The lead:

- understands the phase;
- coordinates Explorers/Fixers;
- reviews every integrated change;
- runs supplementary tests;
- launches the real Studio;
- uses **Chrome DevTools MCP itself**;
- clicks/types/uploads/draws/switches/reloads as a user would;
- visually inspects the result;
- inspects console/network;
- performs real execution when the phase changes execution behavior;
- commits;
- pushes;
- verifies the pushed SHA;
- writes a detailed handoff;
- stops.

## Eye 2 — Independent ChatGPT audit

After the lead pushes a phase:

- Ahmed provides the pushed SHA and handoff;
- ChatGPT independently audits the exact pushed diff;
- confirms the phase stayed in scope;
- checks architecture against this document;
- checks the reported DevTools acceptance evidence;
- flags missing or weak visual validation;
- accepts or rejects the phase.

## Eye 3 — Ahmed manual audit

Ahmed manually uses the resulting Studio and decides whether the product actually feels correct.

A phase is not considered trustworthy merely because tests passed.

---

# 1. Core rule: see it with your own eyes

## 1.1 Chrome DevTools MCP is mandatory

For every user-facing phase, the **lead agent itself** must operate the real running Studio through Chrome DevTools MCP.

The lead cannot outsource all acceptance to a Fixer and then merely quote the Fixer's report.

The lead must personally perform the final integrated acceptance.

The acceptance must exercise the actual UI.

Examples:

- click the visible rail;
- click the visible submenu;
- open the actual workflow picker;
- choose an actual workflow;
- upload/select an actual image;
- type an actual prompt;
- draw an actual mask;
- drag a control;
- change a method;
- trigger an actual run;
- inspect the resulting image;
- switch modes;
- switch back;
- reload;
- inspect restored state;
- inspect visible disabled/error/loading states;
- inspect console;
- inspect network;
- check that stale controls did not survive a remount.

## 1.2 Abstract tests do not satisfy visual acceptance

The following are useful **supplementary** evidence but do not replace DevTools MCP acceptance:

- unit tests;
- deterministic tests;
- mock DOM tests;
- fake-browser tests;
- Playwright;
- snapshots;
- source-code reasoning;
- direct calls to internal JS functions;
- LocalStorage mutation;
- API-only testing;
- Python script simulation;
- reading logs without operating the UI.

A phase with excellent unit tests but no real DevTools interaction is **not accepted**.

## 1.3 No hidden shortcuts

Do not claim:

> “The code path is obviously correct.”

Do not claim:

> “The Fixer tested it.”

Do not claim:

> “Playwright passed.”

Do not claim:

> “I inspected the DOM.”

Instead:

> Open Studio. Use it. Watch it behave.

---

# 2. Product architecture

ComfyModal Studio is a coherent creative application over arbitrary user-owned ComfyUI workflows.

The workflow remains the execution engine.

Studio should not become another graph editor.

The long-term structure is:

```text
USER-OWNED WORKFLOW
T2I or I2I
        ↓
WIZARD MAPPING
semantic Studio meaning → concrete graph fields
        ↓
STUDIO FEATURE
Text / Select / Expand / Sketch / References / Guidance / Post
        ↓
OPTIONAL EXPLICIT EXECUTION METHOD
small generic graph adaptation / pre-post operation
        ↓
TEMPORARY EXECUTION COPY
stored workflow stays untouched
        ↓
RUN
normally on Modal when Modal is active
```

Later:

```text
finished Studio primitives
        ↓
PLAYGROUND PRESETS
reusable user-created tasks
```

Examples:

- Outfit Change
- Logo on Product
- Character in Scene
- Pose from Picture
- Character Sheet

---

# 3. Fundamental workflow model

## 3.1 Normal workflow families

The target normal workflow families are:

- **T2I**
- **I2I**

Legacy workflow types:

- `inpaint`
- `outpaint`
- `sketch`

remain supported as compatibility/specialized paths during V3.

Do not destructively migrate existing user data.

Do not remove a specialized path simply because the generic path exists.

## 3.2 Studio feature versus workflow type

A Studio feature is not automatically a workflow type.

Examples:

- Inpaint is normally an I2I behavior.
- Expand is normally an I2I behavior.
- Sketch is local drawing → flattened I2I input.
- References are extra image-conditioning inputs around T2I/I2I.
- Layout is prompt authoring.
- Guidance is a structural conditioning extension.
- Upscale is downstream image processing.

Dedicated workflows remain valid overrides when users prefer specialized implementations.

---

# 4. Generic execution methods

Generic methods must be structural.

Do not build the normal architecture around model names.

Avoid:

```text
if model == Qwen:
...
elif model == Flux:
...
elif model == Krea:
...
```

Operate on graph contracts where practical:

- `IMAGE`
- `MASK`
- `LATENT`
- `CONDITIONING`
- `MODEL`
- `CLIP`
- `VAE`
- sampler inputs/outputs
- repeatable image-conditioning inputs

Model-specific quirks are exceptions.

## 4.1 No Auto execution method

There is **no Auto mode** for:

- Inpaint
- Expand
- References
- Upscale

The user explicitly chooses a method.

The chosen workflow-structural method is remembered per workflow.

Example:

```text
Inpaint Method   = Crop + Stitch
Expand Method    = Pad + Preserve
Reference Method = Multi-image Slots
```

This is analogous to choosing a sampler/scheduler.

---

# 5. Temporary graph mutation

Studio may:

1. read the selected stored workflow/version;
2. create an execution-only copy;
3. inject/reconnect bounded nodes/inputs;
4. run that copy;
5. discard it.

The stored workflow/version must never be silently rewritten by a Studio feature.

This must be inspectable in logs/diagnostics when execution adaptation occurs.

Do not build a graph rewriting language.

A few explicit transformation functions are preferred.

---

# 6. Execution location

Heavy GPU work should follow the configured execution backend.

When Modal is active:

- generation runs on Modal;
- temporary graph adapters run on Modal;
- Guidance preprocessors/controllers normally run on Modal;
- VOSR2 runs on Modal;
- SeedVR2 runs on Modal.

Do not make these features local-only merely because the Studio UI is local.

Local deterministic canvas operations may remain local.

Do not architect a feature as Modal-only if the same execution path can work elsewhere with compatible dependencies.

---

# 7. No-overengineering constitution

Before implementing anything, prefer:

1. reuse working code;
2. direct input transformation;
3. small deterministic pre/post operation;
4. small explicit temporary graph adaptation;
5. optional specialized workflow;
6. new abstraction only if concrete repeated code proves it necessary.

Do not create:

- generic capability frameworks;
- feature registries merely for extensibility;
- generic graph adapter frameworks;
- graph rewrite DSLs;
- plugin architectures;
- generalized execution engines;
- generalized conditioning systems;
- new state-management architecture;
- asset-management architecture;
- effect plugin systems;
- preset frameworks;
- model-family adapter class hierarchies;
- abstraction layers whose only benefit is “future-proofing.”

A direct `switch`, a short table, or three explicit functions are often correct.

Overengineering and underengineering are both failures.

---

# 8. Existing accepted Phase 1

Phase 1 is COMPLETE and ACCEPTED at:

`a4d19f24376a78d5f1c150ab495ff02883606c2b`

The visible Studio shell is:

```text
Generate
Edit
Post Processing
```

Submenus:

```text
Generate
- Text
- References
- Layout
- Sketch
- Guidance

Edit
- Text
- Select
- Expand
- Sketch

Post Processing
- Adjust
- Color
- Detail
- Effects
- Crop
- Heal
- Upscale
```

Phase 1 still contains intentional compatibility routing:

```text
Select → inpaint
Expand → outpaint
Sketch → sketch
```

V3 phases retire the requirement for those legacy workflow types without breaking compatibility.

Do not redo Phase 1.

---

# 9. Batching strategy

**Focus on batching.**

The objective is maximum useful parallel progress without creating integration chaos.

## 9.1 Batch discovery aggressively

At the start of a phase, the lead should dispatch several read-only Explorers in parallel when useful.

Good Explorer batches:

### Architecture batch
- trace current code ownership;
- find all files/functions involved;
- identify legacy assumptions;
- identify current state keys;
- identify API contracts;
- identify likely regression surfaces.

### UI batch
- inspect current DOM/render ownership;
- trace source-image UI;
- trace selection/mask UI;
- trace post engine routing;
- trace History handoff.

### Test batch
- find existing tests;
- identify stale selectors;
- identify relevant deterministic/unit tests;
- identify known pre-existing failures.

### Workflow-graph batch
- inspect concrete sample workflows;
- diff relevant graph shapes;
- identify insertion anchors;
- verify that proposed generic method is structurally real.

Explorers must return evidence, not vague summaries.

## 9.2 Batch independent implementation

The lead may use multiple bounded Fixers concurrently only when ownership is genuinely disjoint.

Good batching:

```text
Fixer A → isolated mask editor bug
Fixer B → source-image paste/drop handler
Fixer C → test selector mechanical update
```

Bad batching:

```text
Fixer A → redesign studio-playground.js
Fixer B → redesign studio-playground.js
Fixer C → redesign studio-playground-state.js around A/B
```

## 9.3 Shared choke points are serialized

One owner at a time for:

- `web/studio-playground.js`
- shared Playground state
- Wizard role definitions
- run-context contracts
- graph-adaptation execution code
- History provenance schema

The lead may still use Explorers around these files.

## 9.4 Batch tests after coherent milestones

Do not rerun the entire test suite after every tiny edit.

Preferred rhythm:

```text
implement coherent batch
→ run fast targeted checks
→ integrate next coherent batch
→ run phase-level checks
→ perform final DevTools acceptance
```

## 9.5 Batch DevTools acceptance by user journey

Do not validate one button at a time in isolation if a single realistic session can exercise ten requirements.

Example:

```text
load Studio
→ Generate/Text
→ Edit/Text
→ Select
→ draw + SAM
→ switch source
→ Text
→ Select
→ Post
→ back to Edit
→ reload
```

During that one session record:

- visual behavior;
- current selected workflow;
- source image;
- stale state;
- console;
- network;
- persistence.

## 9.6 Do not batch phase commits

Each implementation phase has its own:

- validation;
- commit;
- push;
- handoff;
- independent audit.

Never combine Phase 3 + Phase 4 into one giant commit merely because the coding was convenient.

Parallelize work **inside** a phase.

Serialize acceptance **between** phases.

---

# 10. Agent roles

## 10.1 Lead GPT Sol

The lead owns:

- interpretation of this document;
- batching;
- task decomposition;
- final architecture;
- merge/integration;
- scope control;
- DevTools acceptance;
- Git commit/push;
- handoff.

The lead is not just a project manager.

It must read code, inspect diffs, and personally verify behavior.

## 10.2 Explorer

Explorers are read-only by default.

Use them to answer bounded questions.

Good Explorer prompt:

> Trace every path that clears or preserves the current mask when source_image changes. Return file/function names, current behavior, and concrete risks. Do not modify files.

Bad Explorer prompt:

> Explore the Studio and suggest improvements.

## 10.3 Fixer

Fixers may implement bounded tasks.

Each Fixer should receive:

- exact scope;
- files likely owned;
- behavior contract;
- prohibited scope;
- tests to run;
- instruction to report changes.

The lead reviews all Fixer diffs.

A Fixer does not declare the phase complete.

---

# 11. Mandatory start-of-phase checklist

Before any implementation phase:

- [ ] Read the phase completely.
- [ ] `git status`
- [ ] Record current HEAD.
- [ ] Fetch/inspect `origin/main`.
- [ ] Confirm expected accepted base.
- [ ] Identify dirty/untracked user work.
- [ ] Preserve unrelated changes.
- [ ] Inspect the current live implementation; do not trust old line numbers.
- [ ] Batch relevant Explorers.
- [ ] Summarize current architecture before writing.
- [ ] Identify the smallest concrete implementation.
- [ ] Identify shared choke-point files.
- [ ] Decide which tasks can safely be batched.
- [ ] Decide which tasks must be serialized.
- [ ] Define the exact DevTools acceptance journey before implementation.
- [ ] Define what is explicitly out of scope.

---

# 12. Mandatory end-of-phase checklist

Before declaring COMPLETE:

## Code
- [ ] Phase scope implemented.
- [ ] No unrelated changes.
- [ ] No speculative framework added.
- [ ] No user-owned dirty work overwritten.
- [ ] Dead experimental code removed.
- [ ] Comments describe current behavior, not abandoned approaches.
- [ ] Temporary graph adaptation does not mutate stored workflow where relevant.

## Supplementary tests
- [ ] Syntax/static checks.
- [ ] Relevant deterministic tests.
- [ ] Relevant unit tests.
- [ ] Relevant backend tests where appropriate.
- [ ] Any failure compared against starting SHA when practical.

## DevTools MCP
- [ ] Lead opened real Studio.
- [ ] Lead personally clicked through the integrated phase.
- [ ] Lead tested happy path.
- [ ] Lead tested empty state.
- [ ] Lead tested disabled/gated state.
- [ ] Lead tested error/failure state where feasible.
- [ ] Lead switched away and back.
- [ ] Lead reloaded.
- [ ] Lead inspected console.
- [ ] Lead inspected network.
- [ ] Lead checked stale controls/state.
- [ ] Lead performed real run(s) if execution changed.
- [ ] Lead visually inspected actual output image(s).

## Git
- [ ] Full diff reviewed.
- [ ] Overengineering checklist answered.
- [ ] Commit created.
- [ ] Push completed.
- [ ] Remote SHA verified.
- [ ] Handoff written.
- [ ] `notify-me` used for completion.
- [ ] Lead STOPPED and did not begin next phase.

---

# 13. Required phase handoff

Every phase ends with:

```text
PHASE N — <name>

Status:
COMPLETE / BLOCKED

Starting SHA:
<sha>

Pushed SHA:
<sha>

Commit:
<message>

What changed:
- ...

What deliberately did NOT change:
- ...

Files changed:
- ...

Architecture / execution behavior:
- ...

Batching used:
- Explorers:
- Fixers:
- What was deliberately serialized:

DevTools MCP — lead personally validated:
1. ...
2. ...
3. ...

Visual observations:
- ...

Network/API observations:
- ...

Console:
- ...

Real run(s):
- ...

Supplementary tests:
- ...

Known limitations:
- ...

Overengineering check:
- frameworks/registries added:
- direct code reused:
- smallest new state:
- duplicate paths removed:
- speculative abstractions rejected:
- simplifications made before commit:

Ready for independent audit:
YES / NO
```

---

# 14. PHASE 2 — Workflow-family realignment + Edit foundation

## Objective

Stop ordinary Edit UI from fundamentally requiring legacy `inpaint/outpaint/sketch` workflow families.

Build a solid Select/source foundation over a normal I2I workflow.

Do not implement the generic Inpaint/Expand execution adapters yet.

## Design

Target:

```text
Generate/Text → T2I

Edit/Text
Edit/Select
Edit/Expand
Edit/Sketch
        ↓
normal I2I is the primary engine
```

Legacy specialized workflows remain optional compatibility paths.

## Implementation checklist

### Workflow-family realignment
- [ ] Edit/Text uses normal I2I.
- [ ] Edit/Select can stay on the normal selected I2I workflow.
- [ ] Edit/Select does not require selecting an `inpaint` workflow merely to expose selection tools.
- [ ] Edit/Expand no longer conceptually requires `outpaint` as the only possible future execution engine.
- [ ] Sketch routing is prepared to become local flatten → I2I without destructive backend migration.
- [ ] Legacy `inpaint/outpaint/sketch` workflows still load and remain available as specialized/compatibility paths.
- [ ] Existing saved workflows are not destructively migrated.

### Select
- [ ] Brush.
- [ ] Lasso.
- [ ] Rectangle.
- [ ] Object.
- [ ] Detect.
- [ ] Add.
- [ ] Subtract.
- [ ] Replace.
- [ ] Grow.
- [ ] Shrink.
- [ ] Feather.
- [ ] Invert.
- [ ] Fill Holes.
- [ ] Clear.
- [ ] Undo.
- [ ] Redo.
- [ ] Existing SAM3 infrastructure reused.
- [ ] User-facing language is Object/Detect rather than unnecessary SAM internals.
- [ ] Erase, if present, is treated as Brush + Subtract rather than a new architecture.

### Source handling
- [ ] Upload.
- [ ] Current.
- [ ] History where existing plumbing permits.
- [ ] drag/drop.
- [ ] clipboard paste.
- [ ] Replace.
- [ ] Clear.
- [ ] source replacement clears/reconciles unrelated mask state.
- [ ] source replacement does not leave stale SAM result.
- [ ] switching Text ↔ Select preserves only intended state.

## Suggested batching

### Explorer batch
- [ ] Explorer: trace workflow type routing.
- [ ] Explorer: trace Select/mask state lifecycle.
- [ ] Explorer: trace source-image lifecycle.
- [ ] Explorer: trace SAM3 UI/routes.
- [ ] Explorer: trace stale test selectors.

### Fixer batch
After lead decides ownership:
- [ ] bounded source-state fixer if isolated;
- [ ] bounded mask UI fixer if isolated;
- [ ] bounded stale-test-selector fixer.

Keep workflow-family routing integration owned by the lead or one dedicated writer.

## DevTools MCP acceptance

Lead must personally:

- [ ] Open Studio from the real UI.
- [ ] Confirm exactly 3 top-level modes still exist.
- [ ] Open Generate → Text.
- [ ] Select a real T2I workflow.
- [ ] Confirm shelf/control rendering is correct.
- [ ] Open Edit → Text.
- [ ] Select a real ordinary I2I workflow.
- [ ] Run it once with a real source image and prompt.
- [ ] Visually inspect output.
- [ ] Enter Edit → Select **without losing the ordinary I2I engine**.
- [ ] Draw with Brush.
- [ ] Use Lasso.
- [ ] Use Rectangle.
- [ ] Use Object through real SAM3.
- [ ] Use Detect through real SAM3/text path.
- [ ] Exercise Add/Subtract/Replace.
- [ ] Exercise Grow/Shrink/Feather/Invert/Fill Holes/Clear.
- [ ] Exercise Undo/Redo.
- [ ] Replace source image.
- [ ] Confirm old mask does not incorrectly survive.
- [ ] Paste/drop an image where supported.
- [ ] Switch Select → Text → Select.
- [ ] Confirm no stale controls from previous subtool.
- [ ] Switch Generate → Edit → Post → Edit.
- [ ] Reload while in Select.
- [ ] Inspect restored workflow and shell.
- [ ] Inspect console for new errors.
- [ ] Inspect network for duplicate request storms.
- [ ] Open/select a legacy dedicated inpaint workflow and confirm compatibility was not accidentally destroyed.

## Out of scope

- [ ] No Inpaint adapter execution.
- [ ] No Expand adapter execution.
- [ ] No Reference implementation.
- [ ] No Guidance.
- [ ] No Upscale.
- [ ] No Playground Presets.
- [ ] No graph-adapter framework.

## Commit gate

- [ ] DevTools evidence complete.
- [ ] Real ordinary I2I run complete.
- [ ] Commit.
- [ ] Push.
- [ ] Verify remote.
- [ ] Handoff.
- [ ] STOP.

---

# 15. PHASE 3 — I2I-derived Inpaint + Expand

## Objective

An ordinary I2I workflow should support Inpaint and Expand through explicit generic methods.

No Auto mode.

Stored workflow must remain unchanged.

---

## 15A. Inpaint design

### Method 1 — Crop + Stitch

Concept:

```text
source + mask
→ crop/prepare working region
→ normal selected I2I
→ stitch/composite back into original
```

Checklist:

- [ ] Method appears explicitly in sidebar.
- [ ] Method choice remembered per workflow.
- [ ] Working crop derives from mask.
- [ ] I2I workflow receives prepared image.
- [ ] Result returns to original coordinates.
- [ ] Feather/blending behavior is deterministic.
- [ ] Stored workflow unchanged.
- [ ] History records method.

### Method 2 — Conditioning + Crop/Stitch

Concept:

```text
source + mask
→ crop/prep
→ compatible mask-aware conditioning insertion
→ existing sampler
→ stitch
```

Checklist:

- [ ] Generic structural anchor detection.
- [ ] No normal-path Qwen/Flux/Krea model switch.
- [ ] Positive/negative/latent/VAE anchors handled explicitly.
- [ ] Ambiguous anchor fails clearly or asks for bounded confirmation.
- [ ] Stored workflow unchanged.
- [ ] Method remembered per workflow.

### Method 3 — Dedicated Workflow

- [ ] User can choose a configured specialized workflow.
- [ ] Dedicated workflow is optional.
- [ ] Selection UI remains shared.
- [ ] Dedicated workflow choice remembered.
- [ ] No new permanent top-level workflow family required.

---

## 15B. Expand design

### Method 1 — Pad Canvas

```text
source
→ expand/pad
→ normal I2I
```

- [ ] Top.
- [ ] Right.
- [ ] Bottom.
- [ ] Left.
- [ ] Existing Expand UI reused.
- [ ] Method remembered per workflow.

### Method 2 — Pad + Preserve

```text
source
→ expanded working canvas
→ normal I2I
→ restore/stitch original protected region
```

- [ ] Original region preservation works.
- [ ] Seam/blend behavior visible and inspectable.
- [ ] No stored workflow mutation.

### Method 3 — Dedicated Workflow

- [ ] Optional specialized override.
- [ ] Remembers chosen override.

---

## Batching

### Explorer batch
- [ ] inspect actual Qwen I2I/Inpaint/Outpaint graphs;
- [ ] inspect FLUX/Klein equivalents;
- [ ] inspect Krea equivalents;
- [ ] identify generic graph anchors;
- [ ] identify current run-context mutation seams;
- [ ] identify History provenance fields.

### Implementation batch
Potentially:
- [ ] Fixer A: crop/stitch helper nodes/utilities.
- [ ] Fixer B: expand preparation/stitch helper.
- [ ] Fixer C: persistence/UI method selector.

Graph execution integration must have one owner.

---

## DevTools MCP acceptance

Lead must personally:

### Inpaint Crop + Stitch
- [ ] Select normal I2I workflow.
- [ ] Load visible source image.
- [ ] Draw obvious small mask.
- [ ] Select Crop + Stitch.
- [ ] Run.
- [ ] Observe only intended region changed.
- [ ] Compare source/result.
- [ ] Switch away/back and confirm method persisted.

### Inpaint Conditioning
- [ ] Use structurally compatible normal I2I workflow.
- [ ] Select Conditioning + Crop/Stitch.
- [ ] Run.
- [ ] Observe actual result.
- [ ] Inspect network/run payload/diagnostics.
- [ ] Confirm stored workflow version unchanged.

### Dedicated Inpaint
- [ ] Choose specialized workflow.
- [ ] Run same source/mask.
- [ ] Confirm override works.

### Expand
- [ ] Use normal I2I workflow.
- [ ] Expand visibly on at least two sides.
- [ ] Run Pad Canvas.
- [ ] Inspect output size/content.
- [ ] Run Pad + Preserve.
- [ ] Inspect preservation.
- [ ] Confirm method persisted.
- [ ] Confirm source workflow untouched.

### Regression
- [ ] Normal Edit/Text I2I still runs.
- [ ] Generate/Text still runs.
- [ ] Queue/History record correct method metadata.
- [ ] Console clean.
- [ ] Network sane.

---

# 16. PHASE 4 — Post Processing first-class integration

## Objective

Make existing TinyLuma/local Post Processing feel like a native part of Studio without rewriting its engine.

Subtools:

```text
Adjust
Color
Detail
Effects
Crop
Heal
Upscale
```

Upscale remains placeholder until its phase.

## Preserve existing engine

- [ ] Light controls.
- [ ] Color controls.
- [ ] Curves.
- [ ] Mixer.
- [ ] Grading.
- [ ] Detail/sharpen/noise.
- [ ] LUT.
- [ ] Grain.
- [ ] Glow/bloom.
- [ ] Halation.
- [ ] Flare.
- [ ] Vignette.
- [ ] Crop/straighten.
- [ ] Heal.
- [ ] WB picker.
- [ ] Looks/presets already present.
- [ ] undo/redo.
- [ ] before/after.
- [ ] export.
- [ ] batch where already supported.

## Presentation
- [ ] Controls live coherently in common Studio sidebar/canvas.
- [ ] Switching Post subtools does not destroy current image.
- [ ] No duplicate post engine state.
- [ ] Crop is only Post Crop.
- [ ] Expand remains Edit Expand.

## Optional small QoL if cheap
- [ ] Color Match.
- [ ] Natural Look / de-AI finishing preset.

Do not block phase on optional QoL if it becomes architectural.

## Batching
- [ ] Explorer: map post state/UI.
- [ ] Explorer: trace export/history/current-image handoff.
- [ ] Fixer: isolated presentation migration.
- [ ] Fixer: small Color Match/Natural Look if bounded.

## DevTools MCP acceptance
- [ ] Load real generated image into Post.
- [ ] Adjust light and visibly inspect preview.
- [ ] Adjust color.
- [ ] Use curves.
- [ ] Use detail.
- [ ] Apply an effect.
- [ ] Crop.
- [ ] Heal a visible spot.
- [ ] Undo.
- [ ] Redo.
- [ ] Before/after compare.
- [ ] Export actual file.
- [ ] Switch Post categories repeatedly.
- [ ] Switch away to Edit and back.
- [ ] Reload and inspect state behavior.
- [ ] Confirm no stale workflow Shelf appears in Post.
- [ ] Console/network clean.

---

# 17. PHASE 5 — Generate Text + Visual Style Browser

## Objective

Improve text prompting without changing execution architecture.

Prompt styles are text composition, not image references.

## UI
- [ ] Search.
- [ ] Categories.
- [ ] Sort where useful.
- [ ] Favorites.
- [ ] Visual thumbnail/card.
- [ ] Selected style.
- [ ] None.
- [ ] Style details.
- [ ] Clear indication of how style modifies prompt.
- [ ] Normal Prompt remains editable.

## Licensing
- [ ] Verify catalog license.
- [ ] Verify preview-image usage rights.
- [ ] Do not silently bundle incompatible assets.

## Execution
- [ ] Final prompt composition deterministic.
- [ ] No separate workflow.
- [ ] No style engine.
- [ ] History preserves actual submitted prompt/style identity.

## Batching
- [ ] Explorer: compare style-library references.
- [ ] Explorer: current Prompt Tool/Input ownership.
- [ ] Fixer: style browser UI.
- [ ] Fixer: prompt composition/history if isolated.

## DevTools acceptance
- [ ] Open Generate/Text.
- [ ] Search style.
- [ ] Filter category.
- [ ] Select style.
- [ ] Visually inspect selected state.
- [ ] Inspect effective prompt.
- [ ] Run real generation.
- [ ] Remove style.
- [ ] Run normal prompt.
- [ ] Favorite/unfavorite.
- [ ] Reload and inspect intended persistence.
- [ ] Console/network clean.

---

# 18. PHASE 6 — Shared layered Sketch editor

## Objective

One local layered drawing editor used by both Generate and Edit.

Execution:

```text
layers
→ flatten
→ ordinary I2I
```

No dedicated Sketch engine required.

## Tools
- [ ] Brush.
- [ ] Pencil.
- [ ] Eraser.
- [ ] Line.
- [ ] Rectangle.
- [ ] Circle.
- [ ] Fill.
- [ ] Eyedropper.

## Settings
- [ ] size.
- [ ] opacity.
- [ ] hardness.
- [ ] color.
- [ ] pressure only if already practical.

## Layers
- [ ] add.
- [ ] delete.
- [ ] rename.
- [ ] visibility.
- [ ] opacity.
- [ ] reorder.
- [ ] duplicate.
- [ ] merge/flatten where simple.
- [ ] protect base where appropriate.

## Canvas
- [ ] zoom.
- [ ] pan.
- [ ] Fit.
- [ ] 100%.
- [ ] fullscreen.
- [ ] mirror.
- [ ] shortcuts.
- [ ] undo/redo.

## Execution
- [ ] Generate Sketch starts from blank/base canvas.
- [ ] Edit Sketch starts from current image.
- [ ] Flatten result becomes I2I source.
- [ ] Ordinary I2I workflow remains engine.

## Batching
- [ ] Explorer: current sketch implementation.
- [ ] Explorer: ComfySketch UX ideas/license.
- [ ] Fixer: canvas/layers.
- [ ] Fixer: tool controls.
- [ ] Lead integrates execution handoff.

## DevTools acceptance
Lead actually draws:
- [ ] several strokes.
- [ ] shapes.
- [ ] erase.
- [ ] fill.
- [ ] eyedrop.
- [ ] add layers.
- [ ] reorder.
- [ ] hide/show.
- [ ] opacity.
- [ ] undo/redo.
- [ ] zoom/pan.
- [ ] flatten.
- [ ] run ordinary I2I.
- [ ] inspect output.
- [ ] Generate/Edit Sketch share editor without wrong base image.
- [ ] reload/switch behavior sane.

---

# 19. PHASE 7 — Generate Layout

## Objective

Layout is visual prompt authoring only.

```text
visual composition
→ structured IG4-style prompt
→ ordinary Prompt Tool Input
→ normal workflow
```

## Editor
- [ ] Add object region.
- [ ] Add text region.
- [ ] Move.
- [ ] Resize.
- [ ] Delete.
- [ ] Reorder where semantically useful.
- [ ] Region description.
- [ ] Exact text.
- [ ] Color where relevant.
- [ ] Global description/background.
- [ ] Aspect ratio.
- [ ] Clear/reset.

## Serialization
- [ ] Deterministic.
- [ ] Human-inspectable.
- [ ] Raw structured text optionally viewable/editable.
- [ ] Final output lands in normal prompt control.
- [ ] No Layout workflow/backend.

## Batching
- [ ] Explorer: inspect IG4 prompt conventions.
- [ ] Explorer: current Prompt Tool Input.
- [ ] Fixer: canvas boxes.
- [ ] Fixer: serializer.

## DevTools acceptance
- [ ] Create multiple regions.
- [ ] Move/resize.
- [ ] Add exact text.
- [ ] Change color.
- [ ] Inspect generated structured prompt.
- [ ] Edit generated prompt if supported.
- [ ] Send to normal Prompt.
- [ ] Run real generation.
- [ ] Switch away/back.
- [ ] Reload.
- [ ] Confirm no separate Layout workflow required.

---

# 20. PHASE 8 — References

## Objective

Modern multi-image generation/editing should be first-class.

No Auto method.

Method remembered per workflow.

---

## Method 1 — Multi-image Conditioning Slots

Structural form:

```text
CLIP + image1 + image2 + image3 + ... + prompt
→ CONDITIONING
```

- [ ] Discover actual repeatable inputs.
- [ ] Expose real capacity.
- [ ] Add/remove references.
- [ ] Do not impose arbitrary global maximum if graph provides capacity.
- [ ] Do not assume node class names.

## Method 2 — Reference Latent Chain

Structural form:

```text
IMAGE
→ VAEEncode
→ ReferenceLatent
→ existing conditioning
```

- [ ] Clone/add compatible reference branch.
- [ ] Use temporary graph only.
- [ ] Preserve stored workflow.

## Method 3 — Dedicated Workflow

- [ ] Optional specialized identity/reference workflow.
- [ ] User explicitly chooses it.

---

## Reference card UI

Each card:

- [ ] upload.
- [ ] Current.
- [ ] History.
- [ ] replace.
- [ ] remove.
- [ ] thumbnail.
- [ ] stable numbering.
- [ ] reorder where method semantics permit.
- [ ] optional Remove Background.
- [ ] optional strength only if method truly supports it.
- [ ] optional Describe if bounded and useful.

No fake universal Reference Strength control.

## Batching
- [ ] Explorer: Qwen references.
- [ ] Explorer: Krea references.
- [ ] Explorer: FLUX reference-latent paths.
- [ ] Explorer: current Wizard image roles.
- [ ] Fixer: reference cards.
- [ ] Fixer: background-remove card action.
- [ ] Graph method integration serialized.

## DevTools acceptance

### Multi-image slots
- [ ] Use compatible ordinary workflow.
- [ ] Add at least 2 references.
- [ ] Reorder/remove.
- [ ] Run.
- [ ] Visually inspect that both references affected result.

### Reference latent
- [ ] Choose compatible workflow.
- [ ] Select Reference Latent method.
- [ ] Add reference(s).
- [ ] Run.
- [ ] Inspect result.

### Background removal
- [ ] Remove background on a reference.
- [ ] Inspect transformed reference preview.
- [ ] Run with transformed reference.

### Dedicated
- [ ] Choose a specialized reference workflow.
- [ ] Confirm override.

### Persistence
- [ ] Method persists per workflow.
- [ ] Reference image job data behaves intentionally.
- [ ] Stored workflow unchanged.
- [ ] History records method/reference provenance appropriately.
- [ ] console/network clean.

---

# 21. PHASE 9 — Guidance

## Objective

Structural guidance is keyed to the actual loaded diffusion model, not workflow identity.

Examples:

- Pose.
- Depth.
- Canny/Edge.
- Lineart.
- additional modes only when concretely supported.

---

## Model identity

Preferred evidence:

1. exact model hash / manifest;
2. architecture/base metadata;
3. filename as weaker display/fallback.

A mapping applies to the model across every workflow that loads that model.

## Discovery behavior

Guidance discovery may be smooth/automatic.

Execution method selection is not an Auto feature.

Studio should propose a compatible guidance mapping, then require user audit/confirmation before trusting it.

Example:

```text
Detected model:
FLUX.2 Klein 9B

Pose:
<verified compatible controller>

Preprocessor:
DWPose

Source:
<trusted registry/repository>

[Confirm] [Change]
```

After confirmation:

- [ ] remember by exact model identity;
- [ ] reuse across workflows;
- [ ] do not silently replace later.

If no verified match:
- [ ] offer manual selection;
- [ ] allow user to confirm and remember it.

## Mapping record

Keep small:

- [ ] model identity/hash.
- [ ] provider/controller.
- [ ] exact weight.
- [ ] expected hash where available.
- [ ] supported guidance modes.
- [ ] required preprocessor.
- [ ] source.
- [ ] license.
- [ ] dependency version if materially required.

Do not build a giant generic package manager.

## Execution
- [ ] temporary graph injection.
- [ ] Modal when Modal is active.
- [ ] no workflow-name mapping.
- [ ] distinguish soft reference guidance from real structural guidance.

## Batching
- [ ] Explorer: current Comfy Manager metadata.
- [ ] Explorer: Qwen current control support.
- [ ] Explorer: FLUX/Klein current control support.
- [ ] Explorer: Krea current control support.
- [ ] Explorer: model identity metadata in current Studio/runtime.
- [ ] Fixer: guidance mapping UI.
- [ ] Fixer: mapping persistence.
- [ ] execution integration serialized.

## DevTools acceptance
- [ ] Select workflow A using model X.
- [ ] Open Guidance.
- [ ] Observe correct detected model identity.
- [ ] Review proposed Pose mapping.
- [ ] Confirm.
- [ ] Run real Pose guidance.
- [ ] Inspect result against guide image.
- [ ] Switch to workflow B using same model X.
- [ ] Confirm mapping reused without re-auditing.
- [ ] Switch to model Y.
- [ ] Confirm different mapping/audit path.
- [ ] Exercise unknown-model/manual-selection state if feasible.
- [ ] Inspect console/network.
- [ ] Verify no mapping keyed to workflow id.

---

# 22. PHASE 10 — Compare, review, History QoL

## Objective

Make iterative image work easy across Generate/Edit/Post/Upscale.

## Compare
- [ ] reveal divider.
- [ ] synchronized pan/zoom.
- [ ] Fit.
- [ ] 1:1.
- [ ] optional hold-to-compare if useful.

## History actions
- [ ] Use as Current.
- [ ] Edit.
- [ ] Use as Reference.
- [ ] Post Process.
- [ ] Upscale.
- [ ] Download.
- [ ] Favorite.

Reuse History V2.

No Asset Library.

## Other QoL
- [ ] fixed/random seed visually obvious.
- [ ] actual execution metadata preserved.
- [ ] expensive final-processing actions distinguishable from normal draft work where appropriate.

## Batching
- [ ] Explorer: History V2 actions/schema.
- [ ] Explorer: existing compare code.
- [ ] Fixer: compare primitive.
- [ ] Fixer: bounded History actions.

## DevTools acceptance
- [ ] Generate image.
- [ ] Open History.
- [ ] Use as Current.
- [ ] Edit it.
- [ ] Use prior image as Reference.
- [ ] Send to Post.
- [ ] Compare before/after.
- [ ] Pan/zoom both views.
- [ ] Favorite.
- [ ] Download.
- [ ] switch/reload and inspect consistency.
- [ ] console/network clean.

---

# 23. PHASE 11 — Upscale

## Objective

Two explicit complementary upscale methods:

1. **VOSR2**
2. **SeedVR2**

No Auto.

Both should run on Modal when Modal is active.

---

## VOSR2

Position:

> fast/general super-resolution

Expose only meaningful controls.

Potential:
- [ ] scale.
- [ ] target resolution.
- [ ] tiling if required.
- [ ] model variant only if useful.

## SeedVR2

Position:

> heavier generative restoration/upscaling

Expose only meaningful controls.

Potential:
- [ ] scale/target.
- [ ] restoration strength if concrete implementation supports it.
- [ ] model size only where meaningful.

## Execution architecture

Upscale is downstream processing and need not live inside the user's generation workflow.

A small Studio-owned internal Comfy graph or direct execution path is acceptable.

Choose whichever is simpler.

Do not build a generic upscaler registry.

## Optional color preservation
- [ ] Preserve Source Color / Color Match if simple.
- [ ] Do not block base Upscale completion if substantial.

## Batching
- [ ] Explorer: VOSR2 current Comfy implementation/dependencies/license.
- [ ] Explorer: SeedVR2 current Comfy implementation/dependencies/license.
- [ ] Explorer: Modal dependency/install path.
- [ ] Fixer: VOSR2 execution.
- [ ] Fixer: SeedVR2 execution.
- [ ] UI/history integration serialized by lead.

## DevTools acceptance

### VOSR2
- [ ] Choose real image.
- [ ] Select VOSR2.
- [ ] Run.
- [ ] Observe real Modal execution.
- [ ] Inspect output resolution.
- [ ] Use 1:1 compare.
- [ ] Visually inspect detail.

### SeedVR2
- [ ] Same source or comparable source.
- [ ] Select SeedVR2.
- [ ] Run.
- [ ] Observe real Modal execution.
- [ ] Inspect output.
- [ ] 1:1 compare with source and VOSR2.

### Integration
- [ ] Upscaled result appears in History.
- [ ] Use as Current.
- [ ] Send to Edit.
- [ ] Send to Post.
- [ ] Download.
- [ ] console/network clean.
- [ ] no hidden local GPU dependency.

---

# 24. PHASE 12 — Playground Presets

## Objective

Only after primitives work, users can save a current Playground setup as a reusable task.

This is the sole current user-facing preset system.

Do not revive deprecated preset systems.

## Preset stores
- [ ] workflow.
- [ ] workflow version.
- [ ] mode/subtool.
- [ ] normal saved values.
- [ ] field label overrides.
- [ ] hidden Preset Prompt.
- [ ] optional default visible User Prompt.
- [ ] selected generic method(s) relevant to task.
- [ ] specialized workflow override identity if task uses one.

## Preset does not store
- [ ] source images.
- [ ] reference images.
- [ ] masks.
- [ ] sketch bitmap/job data.

Those reopen empty.

## Label override

Example:

```text
Reference 1 → Logo
Reference 2 → Product
Prompt      → Instructions
```

Semantic identity remains unchanged.

## Prompt composition

### Preset Prompt
- [ ] authored in Edit Preset.
- [ ] hidden during ordinary use.
- [ ] automatically included every run.

### User Prompt
- [ ] visible.
- [ ] editable.
- [ ] job-specific.

Backend composition is authoritative.

Concept:

```text
<preset prompt>

User request:
<user prompt>
```

Handle:
- [ ] preset-only.
- [ ] user-only.
- [ ] both.

No chat-role framework.
No templating language.

## Example tasks
- [ ] Outfit Change.
- [ ] Logo on Product.
- [ ] Character in Scene.
- [ ] Pose from Picture.
- [ ] Character Sheet.

These are examples, not hardcoded tools.

## History
Must preserve:
- [ ] preset identity.
- [ ] visible user prompt.
- [ ] preset prompt or immutable equivalent.
- [ ] final submitted prompt.
- [ ] workflow/version.
- [ ] method selections.
- [ ] execution provenance.

## Batching
- [ ] Explorer: deprecated preset remnants.
- [ ] Explorer: current shelf autosave/layout.
- [ ] Explorer: History replay/provenance.
- [ ] Fixer: preset CRUD.
- [ ] Fixer: label override UI.
- [ ] Fixer: prompt composition.
- [ ] Lead owns schema/integration.

## DevTools acceptance

Create real presets:

### Logo on Product
- [ ] save preset.
- [ ] Reference 1 label = Logo.
- [ ] Reference 2 label = Product.
- [ ] Prompt label = Instructions.
- [ ] hidden preset instruction entered.
- [ ] close/reopen.
- [ ] image fields empty.
- [ ] labels restored.
- [ ] preset prompt remains hidden in normal use.
- [ ] add actual logo/product images.
- [ ] enter user request.
- [ ] run.
- [ ] inspect result/history provenance.

### Outfit Change
- [ ] create second preset from same/general engine.
- [ ] use different labels/instructions.
- [ ] confirm no workflow duplication required.

### Persistence
- [ ] reload.
- [ ] edit preset.
- [ ] delete preset.
- [ ] confirm no old/deprecated preset UI surfaced.
- [ ] console/network clean.

---

# 25. PHASE 13 — Final integration + simplification

## Objective

No new major features.

Use Studio as a complete product and remove accidental complexity.

End-to-end journey:

```text
Generate
→ Text / Style / Layout / References / Sketch / Guidance
→ output
→ Edit
→ Text / Select / Inpaint / Remove / Expand / Sketch
→ Post
→ Adjust / Color / Detail / Effects / Crop / Heal / Upscale
→ History
→ Playground Preset
→ reuse
```

## Full integration checklist

### Generate
- [ ] Text.
- [ ] Style.
- [ ] Layout.
- [ ] References.
- [ ] Sketch.
- [ ] Guidance.

### Edit
- [ ] Text.
- [ ] Select.
- [ ] Inpaint Crop+Stitch.
- [ ] Inpaint Conditioning.
- [ ] Dedicated Inpaint.
- [ ] Remove.
- [ ] Expand Pad.
- [ ] Expand Preserve.
- [ ] Dedicated Expand.
- [ ] Sketch.

### Post
- [ ] Adjust.
- [ ] Color.
- [ ] Detail.
- [ ] Effects.
- [ ] Crop.
- [ ] Heal.
- [ ] VOSR2.
- [ ] SeedVR2.

### History/Presets
- [ ] History reuse.
- [ ] Compare.
- [ ] Preset create.
- [ ] Preset run.
- [ ] Preset edit/delete.
- [ ] prompt provenance.

### Workflow compatibility
- [ ] ordinary T2I.
- [ ] ordinary I2I.
- [ ] legacy inpaint.
- [ ] legacy outpaint.
- [ ] legacy sketch.
- [ ] specialized reference workflow.

### Operational
- [ ] Queue.
- [ ] Experiment.
- [ ] current-image chaining.
- [ ] source replacement.
- [ ] reload.
- [ ] rapid mode switching.
- [ ] narrow desktop width.
- [ ] disabled states.
- [ ] missing dependency state.
- [ ] backend error state.
- [ ] no stale controls.
- [ ] no request storms.
- [ ] console sanity.

## Final simplification audit

Search specifically for:

- [ ] Select still unnecessarily tied to `inpaint`.
- [ ] Expand still unnecessarily tied to `outpaint`.
- [ ] Sketch still unnecessarily tied to `sketch`.
- [ ] model-name branching in generic methods.
- [ ] duplicate workflow execution paths.
- [ ] duplicate source-image state.
- [ ] duplicate mask state.
- [ ] duplicate preset systems.
- [ ] unused Phase-1 compatibility helpers.
- [ ] stale test selectors.
- [ ] dead placeholders.
- [ ] redundant persistence.
- [ ] framework abstractions that can become direct functions.
- [ ] generic registries with only 2–3 concrete entries.
- [ ] hidden mutations of stored workflow.
- [ ] user-facing backend terminology that should be product language.

Delete/simplify only when behavior is proven preserved.

---

# 26. Future candidates — NOT V3 requirements

Do not expand V3 just because these are interesting.

## Smart Detailer
Potential:
- Face.
- Eyes.
- Hands.
- SAM3-driven selection.
- Detail action.

## Transparent object matting
Different from ordinary background segmentation.

## Relighting
Normal/depth/mask based.

## Prompt helper
- Enhance.
- Refine.
- Describe Source.
- Describe Reference.

Only implement if Ahmed explicitly promotes them.

---

# 27. Explicitly out of scope

Unless Ahmed changes scope:

- [ ] LoRA browser/library.
- [ ] Asset Library.
- [ ] style marketplace.
- [ ] installable Studio plugin system.
- [ ] training UI.
- [ ] dataset management.
- [ ] video.
- [ ] audio.
- [ ] 3D.
- [ ] faceswap.
- [ ] generic model manager.
- [ ] graph programming UI.
- [ ] automatic Inpaint method.
- [ ] automatic Expand method.
- [ ] automatic Reference method.
- [ ] automatic Upscale method.
- [ ] replacing user workflows with Studio-generated generation pipelines.

Specific models/LoRAs can still be concrete dependencies of a feature.

---

# 28. DevTools evidence quality standard

A good handoff says:

> Opened Edit → Select with `Qwen Image 2.1 - One Image Edit` still selected. Uploaded image A, drew a rectangle over the jacket, switched combine mode to Subtract, erased the center, clicked Grow 8px then Feather 12px. Replaced source with image B; mask cleared immediately. Object selection on “sword” returned a visible mask through `/studio/sam3/text`; network showed one request and no duplicate polling. Switched to Edit/Text and back; source B remained, mask stayed intentionally empty. Console had no new errors.

A bad handoff says:

> Selection tools tested and working.

The lead should capture enough specificity that Ahmed and ChatGPT can tell whether the behavior was actually exercised.

---

# 29. Real-run evidence quality standard

For phases that change execution, record:

- workflow name/id;
- workflow family;
- source image description;
- prompt;
- selected Studio method;
- meaningful settings;
- HTTP/result status;
- output dimensions/hash if available;
- visible qualitative result;
- History entry;
- any adaptation diagnostic.

Do not spend remote runs frivolously.

Batch acceptance so one real run validates multiple requirements where possible.

---

# 30. Batching examples by phase

## Phase 2
Parallel:
- routing explorer;
- mask explorer;
- source explorer;
- test explorer.

Then:
- source/mask isolated fixes in parallel if disjoint;
- routing integration serialized.

## Phase 3
Parallel:
- graph-shape explorers across Qwen/FLUX/Krea;
- crop/stitch helper implementation;
- method selector persistence.

Then:
- execution graph integration serialized.

## Phase 4
Parallel:
- post engine/state explorer;
- UI presentation fixer;
- optional Color Match feasibility explorer.

Then:
- integrated visual pass.

## Phase 5
Parallel:
- catalog/license explorer;
- style UI fixer;
- prompt-composition fixer.

## Phase 6
Parallel:
- canvas/layers implementation;
- controls implementation;
- workflow handoff explorer.

Then:
- lead integrates flatten/I2I.

## Phase 8
Parallel:
- Qwen reference explorer;
- FLUX reference explorer;
- Krea reference explorer;
- reference card UI;
- background removal reuse.

Then:
- graph integration serialized.

## Phase 9
Parallel:
- Qwen guidance mapping research;
- FLUX guidance mapping research;
- Krea guidance mapping research;
- model identity explorer;
- mapping UI/persistence implementation.

Then:
- graph execution integration serialized.

## Phase 11
Parallel:
- VOSR2 research/implementation;
- SeedVR2 research/implementation;
- Modal dependency investigation.

Then:
- shared Upscale UI/history integration serialized.

## Phase 12
Parallel:
- deprecated preset explorer;
- shelf persistence explorer;
- History provenance explorer;
- label UI fixer;
- prompt composition fixer.

Then:
- one owner integrates preset schema/CRUD.

---

# 31. Batching anti-patterns

Never do this:

### Mega-phase batching
> “Phase 3 and Phase 4 touch similar UI, so implement both before review.”

No.

### Multi-writer choke point
> “Three Fixers can all modify studio-playground.js and we'll reconcile later.”

No.

### Validation batching across phases
> “We'll visually test everything after five phases.”

No.

### Abstract-test shortcut
> “Playwright exercised the buttons, so DevTools isn't necessary.”

No.

### Research without decision
> “Six Explorers returned 40 pages; add an abstraction that supports all possibilities.”

No.

Exploration should reduce uncertainty and lead to a smaller implementation.

---

# 32. Final no-overengineering checklist

Before every phase push, the lead must explicitly answer:

- [ ] Did I introduce a framework where a direct function/switch would work?
- [ ] Did I introduce a registry merely because there are two methods?
- [ ] Did I make a model-specific branch the main architecture?
- [ ] Did I invent Auto behavior?
- [ ] Did I duplicate a workflow for a tiny structural delta?
- [ ] Did I remove optional specialized workflows?
- [ ] Did I modify stored workflow instead of execution copy?
- [ ] Did I add another top-level workflow type?
- [ ] Did I expose unnecessary backend jargon?
- [ ] Did I add a universal control unsupported by some methods?
- [ ] Did I duplicate SAM/Post/History functionality?
- [ ] Did I make heavy inference local-only?
- [ ] Did I create a second preset system?
- [ ] Did I add features merely because the workflow corpus contained them?
- [ ] Did I make parallelization require new architecture?
- [ ] Can any abstraction be deleted right now?
- [ ] Can any state field be removed?
- [ ] Can any duplicated code path become one existing path?

If yes, simplify before push.

---

# 33. Definition of V3 done

- [ ] Phase 1 remains intact.
- [ ] T2I/I2I are normal workflow families.
- [ ] legacy specialized workflow types remain compatible.
- [ ] Select works over ordinary I2I.
- [ ] Inpaint has explicit generic methods.
- [ ] Expand has explicit generic methods.
- [ ] no Auto execution method.
- [ ] per-workflow method persistence.
- [ ] stored workflows never silently mutated.
- [ ] Post integrated.
- [ ] Style Browser works.
- [ ] Sketch is layered UI → I2I.
- [ ] Layout is prompt authoring.
- [ ] References support multiple images and explicit generic methods.
- [ ] Guidance keyed to model identity.
- [ ] Guidance recommendation is user-audited.
- [ ] guidance mapping reused across workflows using same model.
- [ ] History/compare iteration works.
- [ ] VOSR2 works.
- [ ] SeedVR2 works.
- [ ] Playground Presets work.
- [ ] Preset labels editable.
- [ ] hidden Preset Prompt + visible User Prompt.
- [ ] preset images reopen empty.
- [ ] History preserves provenance.
- [ ] no Asset Library.
- [ ] no LoRA browser.
- [ ] no model-family adapter architecture.
- [ ] no generic adapter framework.
- [ ] every phase has lead-owned DevTools MCP evidence.
- [ ] every phase has its own pushed SHA.
- [ ] every phase stops for independent audit.
- [ ] final simplification pass completed.

---

# 34. One-line rule

> **Batch discovery and independent implementation aggressively, serialize shared integration and phase acceptance, keep arbitrary T2I/I2I workflows as the engines, add only small explicit generic methods around them, and never call a phase complete until the lead has personally watched the real Studio work through Chrome DevTools MCP.**
