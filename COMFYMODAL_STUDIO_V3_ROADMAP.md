# ComfyModal Studio — V3 Authoritative Roadmap

**Status:** AUTHORITATIVE  
**Repository:** `Parlaxz/comfyui-modal`  
**Accepted starting point:** `a4d19f24376a78d5f1c150ab495ff02883606c2b`  
**Accepted completed work:** Phase 1 — Three-mode shell and UI consolidation  
**Date:** 2026-10-13

This document is complete and standalone. It is the only roadmap required for this effort.

The agent must not depend on earlier roadmap documents, prior architectural plans, or remembered assumptions. Historical repo docs may describe deprecated systems and should not overrule this file. Always inspect the live checkout before implementing a phase.

---

# 0. Product vision

ComfyModal Studio should feel like a coherent creative image application powered by arbitrary ComfyUI workflows.

The user should not have to maintain many almost-identical workflows merely because Studio exposes different creative actions.

The long-term model is:

```text
USER-OWNED WORKFLOW
T2I or I2I
        ↓
WIZARD MAPPING
maps concrete graph fields to Studio meaning
        ↓
STUDIO
Prompt / References / Select / Expand / Sketch / Guidance / Post
        ↓
OPTIONAL GENERIC EXECUTION METHOD
temporary graph adaptation or local preparation
        ↓
RUN
normally on Modal when Modal is the active execution backend
```

Later:

```text
finished Studio primitives
        ↓
PLAYGROUND PRESETS
user-defined reusable tasks such as:
- Outfit Change
- Logo on Product
- Character in Scene
- Pose from Picture
- Character Sheet
```

The workflow remains the engine. Studio should not become another graph editor.

---

# 1. Phase 1 is accepted

Phase 1 was completed and independently accepted at:

`a4d19f24376a78d5f1c150ab495ff02883606c2b`

It established:

```text
Generate
Edit
Post Processing
```

with the desired submenus and honest placeholders.

Do not rewrite or redo Phase 1.

One intentional compatibility carryover must be retired during V3:

```text
Select       → legacy inpaint workflow type
Expand       → legacy outpaint workflow type
Sketch       → legacy sketch workflow type
```

That mapping was correct for Phase 1's scope. V3 moves toward T2I/I2I as the fundamental workflow families.

---

# 2. Non-negotiable design principles

## 2.1 Occam's razor

Prefer, in order:

1. existing working code;
2. direct input transformation;
3. a small deterministic pre/post operation;
4. a small temporary graph adaptation;
5. an optional specialized workflow;
6. new framework/architecture only when concrete evidence proves it necessary.

Never introduce architecture merely because a future feature might need it.

## 2.2 No speculative frameworks

Do not create:

- a generic workflow engine registry;
- a generic feature/capability framework;
- a graph-rewriting DSL;
- a plugin architecture;
- an artifact/document graph;
- a new global state architecture;
- a generalized conditioning framework;
- a generalized effect framework;
- a generic "adapter framework" with abstractions beyond the few concrete methods required now.

A handful of explicit functions/switches is preferred.

## 2.3 Studio is workflow-agnostic and model-agnostic

Studio must not be architected as:

```text
if model == Qwen:
...
elif model == Flux:
...
elif model == Krea:
...
```

Generic feature methods should operate on graph structure and Comfy contracts such as:

- `IMAGE`
- `MASK`
- `LATENT`
- `CONDITIONING`
- `MODEL`
- `CLIP`
- `VAE`
- sampler inputs/outputs
- repeatable image-conditioning inputs

Model-specific quirks are exceptions, not the primary architecture.

## 2.4 T2I and I2I are the fundamental workflow families

The target user-facing workflow model is eventually:

- T2I
- I2I

Legacy types such as:

- inpaint
- outpaint
- sketch

must remain readable/usable for compatibility while V3 transitions away from requiring them.

Do not perform a destructive migration of existing user data.

## 2.5 Specialized workflows remain allowed

Generic I2I-derived features are the normal convenience path.

However, a user may deliberately choose a dedicated specialized workflow for:

- Inpaint
- Expand/Outpaint
- References
- Guidance
- other future cases

when that workflow produces better results.

Do not eliminate expert workflows merely to achieve conceptual purity.

## 2.6 Temporary graph mutation is allowed

Studio may:

1. load the selected stored workflow;
2. clone its executable graph for a run;
3. inject/reconnect bounded nodes or inputs;
4. execute the temporary graph;
5. discard the temporary graph.

The stored workflow/version must remain unchanged.

Temporary adaptation must be deterministic and inspectable.

## 2.7 No automatic execution-method selection

There is **no `Auto` method** for Inpaint, Expand, References, or Upscale.

The user explicitly chooses a method.

The choice is remembered per workflow where the choice is workflow-structural.

Example:

```text
This workflow:
Inpaint Method   = Crop + Stitch
Expand Method    = Pad + Preserve
Reference Method = Multi-image Slots
```

This is similar in spirit to selecting sampler/scheduler behavior.

## 2.8 Modal is the preferred heavy execution environment, not a product restriction

Heavy generation/inference should execute through the configured execution backend.

When Modal is the active backend:

- generated temporary graph adaptations run on Modal;
- Guidance preprocessors/controllers run on Modal;
- Upscale runs on Modal;
- required GPU inference does not move to the browser/local UI.

Do not make Studio features conceptually "Modal-only." If the same execution path can run on another configured backend with its dependencies available, it should not be artificially forbidden.

Local deterministic canvas operations may remain local where appropriate.

## 2.9 Preserve arbitrary workflow internals

Many real workflows contain:

- multi-pass sampling;
- latent upscale/refinement;
- model optimizers;
- LoRAs;
- custom schedulers;
- unusual samplers;
- detailers.

Studio must not reconstruct or normalize these internals.

The user's workflow owns them.

Studio adapts around the workflow only where needed for a Studio feature.

---

# 3. Evidence from the workflow corpus

A supplied workflow corpus was structurally audited across many workflows including:

- Qwen Image 2.1
- FLUX.2 Klein
- Krea 2
- Z-Image
- Ideogram
- utility workflows
- multiple independent workflow authors

Important recurring patterns:

## 3.1 Inpaint

### Method A — Crop + Stitch

Observed strongly in modern Qwen-style editing:

```text
source + mask
→ crop/preparation
→ ordinary I2I core
→ stitch/composite back into original
```

### Method B — Conditioning + Crop/Stitch

Observed in FLUX-style inpaint:

```text
source + mask
→ crop/preparation
→ mask-aware conditioning insertion
→ existing sampler path
→ stitch/composite
```

### Method C — Dedicated Workflow

Useful for specialized systems such as AnyPaint-style implementations.

## 3.2 Expand / Outpaint

### Method A — Pad Canvas

```text
source
→ pad/expand to target canvas
→ ordinary I2I
```

### Method B — Pad + Preserve/Stitch

```text
source
→ expanded working canvas
→ ordinary I2I
→ restore/stitch protected original region
```

Useful when a model tends to shift/redraw the original region.

### Method C — Dedicated Workflow

Useful for specialized preservation LoRAs, AnyPaint-like systems, or expert graphs.

## 3.3 References

### Method A — Multi-image Conditioning Slots

Observed across multiple modern architectures.

Examples differ in node class but share the structural idea:

```text
CLIP + image1 + image2 + image3 + prompt
→ CONDITIONING
```

Qwen and Krea provide examples of this pattern.

### Method B — Reference Latent Chain

Observed in FLUX-style workflows:

```text
reference IMAGE
→ VAEEncode
→ ReferenceLatent
→ existing conditioning
```

Additional references repeat the branch.

### Method C — Dedicated Workflow

Useful for specialized identity/reference systems with custom model patches or tuned behavior.

## 3.4 Presets are real product value

Many apparently specialized workflows are mostly:

- generic I2I;
- fixed task instruction;
- named image roles;
- ordinary controls.

Examples include:

- Outfit Change
- Character + Background
- Logo on Product
- Character in Scene
- Pose from Picture

This strongly supports Playground Presets, but Presets come near the end of V3 after the underlying primitives work.

---

# 4. Wizard responsibility

The Wizard maps a concrete workflow to Studio semantics.

Do not turn the Wizard into a generic graph-programming UI.

The Wizard should eventually center on T2I and I2I.

Existing semantic roles such as:

- Prompt
- Seed
- Steps
- CFG
- Sampler
- Width
- Height
- Model/UNET
- VAE
- CLIP
- Source Image
- Mask
- Output

remain useful.

## 4.1 Repeatable references

The existing single-source-image vocabulary is insufficient for modern multi-image I2I.

V3 must support repeatable reference inputs at the Studio/adaptation layer.

Do not globally hardcode an arbitrary `reference_1 ... reference_10` contract if the selected Reference Method can report/derive its real capacity.

## 4.2 Internal adapter anchors

Generic execution methods may require anchors such as:

- sampler node/input;
- positive conditioning;
- negative conditioning;
- latent;
- source-image branch;
- output image;
- model path;
- VAE.

Prefer structural discovery.

If multiple valid targets make the choice ambiguous, the Wizard may ask the user to confirm the concrete anchor.

Do not expose these as normal creative sidebar controls.

---

# 5. Shared acceptance contract for every phase

The lead agent owns the phase.

Explorers may perform read-only research.

Fixers may perform bounded implementation.

The lead personally reviews and integrates everything.

## 5.1 Chrome DevTools MCP is primary UI acceptance

For user-facing phases, the lead must operate the real running Studio using Chrome DevTools MCP.

As applicable:

- navigate;
- click;
- type;
- upload/select images;
- drag;
- draw;
- change controls;
- switch modes/subtools;
- reload;
- inspect persistence;
- inspect console;
- inspect network;
- perform a real representative run;
- inspect resulting image;
- switch away/back;
- ensure no stale controls remain.

Playwright/tests may supplement but never replace real DevTools operation.

## 5.2 Real execution

When execution behavior changes, perform at least one real representative run if the environment supports it.

If an external dependency genuinely prevents the run, report:

`BLOCKED`

Do not substitute a mock and call it equivalent.

## 5.3 Every phase ends separately

For every phase:

1. inspect current Git state;
2. preserve unrelated dirty work;
3. implement only that phase;
4. validate;
5. run supplementary tests;
6. review diff;
7. run overengineering review;
8. commit;
9. push;
10. verify pushed SHA;
11. write handoff;
12. stop for independent audit.

Do not continue into the next phase without Ahmed's approval.

---

# 6. Required phase handoff

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

Execution behavior:
- ...

Method(s) implemented:
- ...

DevTools MCP validation:
1. ...
2. ...

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
- new frameworks/registries:
- existing code reused:
- smallest new state:
- duplicated paths removed:
- simplifications before commit:

Ready for independent audit:
YES / NO
```

---

# PHASE 2 — Workflow-family realignment + Edit foundation

## Goal

Make the Phase-1 shell conform to the V3 execution model before deeper features are built.

The visible product remains:

```text
Generate
Edit
Post Processing
```

But Edit should stop requiring separate legacy workflow families for ordinary behavior.

## 2.1 T2I/I2I realignment

Begin moving normal Studio operation toward:

```text
Generate/Text → T2I
Edit/Text     → I2I
Edit/Select   → I2I + selection/action
Edit/Expand   → I2I + Expand Method
Generate/Edit Sketch → I2I after flatten
References    → selected T2I/I2I engine + Reference Method where applicable
```

Do not destructively remove support for legacy:

- `inpaint`
- `outpaint`
- `sketch`

They remain compatibility/specialized workflow options.

## 2.2 Edit → Select

Consolidate the existing working selection system.

Visible selection methods:

- Brush
- Lasso
- Rectangle
- Object
- Detect

Reuse:

- existing manual mask canvas;
- SAM3;
- text detection;
- point/object selection;
- mask combine behavior.

Visible mask controls should include existing useful operations:

- Add
- Subtract
- Replace
- Grow
- Shrink
- Feather
- Invert
- Fill Holes
- Clear
- Undo
- Redo

Erase is Brush + Subtract, not a separate architecture.

SAM3 is implementation detail. User-facing names are Object / Detect.

## 2.3 Source-image QoL

Where already supported or small:

- Upload
- Current
- History
- drag/drop
- clipboard paste
- Replace
- Clear

Changing source must not leave an unrelated stale mask.

## 2.4 Do not implement Inpaint execution yet

Phase 2 builds the selection/input foundation and workflow-family realignment.

Do not prematurely implement the Phase 3 execution methods.

## Acceptance

Prove:

- ordinary I2I can remain selected while using Edit/Select UI;
- Select no longer fundamentally depends on owning a separate `inpaint` workflow;
- mask creation works;
- SAM Object/Detect works;
- source changes clear/reconcile masks correctly;
- legacy dedicated inpaint workflow remains usable as compatibility path;
- no regressions to T2I/I2I runs.

---

# PHASE 3 — I2I-derived Inpaint and Expand

## Goal

Make ordinary I2I workflows useful for Inpaint and Expand without forcing duplicate workflows.

No automatic method selection.

Method selection is explicit and remembered per workflow.

---

## 3A. Inpaint

### Method 1 — Crop + Stitch

Implement a generic path conceptually equivalent to:

```text
source + mask
→ prepare/crop working region
→ execute selected I2I workflow
→ stitch/composite result into original
```

The selected stored workflow must remain unchanged.

Prefer using a temporary graph and Studio-owned small helper nodes when that keeps execution on the configured backend cleanly.

A small deterministic Python pre/post helper is also acceptable if it is simpler and preserves execution semantics.

Do not choose architecture for elegance; choose the smallest reliable path.

### Method 2 — Conditioning + Crop/Stitch

For workflows with compatible conditioning/latent anchors, support a method conceptually equivalent to:

```text
source + mask
→ crop/prep
→ insert compatible mask-aware conditioning
→ existing selected I2I sampler path
→ stitch/composite
```

Use graph contracts/structure, not model-name branches.

### Method 3 — Dedicated Workflow

Allow the user to choose a configured specialized workflow as the Inpaint execution method.

This is an override, not the normal requirement.

### UI

Example:

```text
Inpaint Method
[ Crop + Stitch ▼ ]

Crop + Stitch
Conditioning + Crop/Stitch
Dedicated Workflow
```

No Auto.

### Remember choice

Persist the chosen method for that workflow.

If Dedicated Workflow is selected, persist the selected override workflow.

---

## 3B. Expand

### Method 1 — Pad Canvas

```text
source
→ pad/expand to requested canvas
→ selected I2I
```

### Method 2 — Pad + Preserve

```text
source
→ expanded working canvas
→ selected I2I
→ restore/stitch original protected region
```

### Method 3 — Dedicated Workflow

Optional specialized override.

### UI

```text
Expand Method
[ Pad + Preserve ▼ ]

Pad Canvas
Pad + Preserve
Dedicated Workflow
```

No Auto.

Reuse the existing Phase-1 Expand controls for:

- Top
- Right
- Bottom
- Left

Do not invent another expansion editor.

## Real-run acceptance

Use at least one normal I2I workflow, not only a dedicated inpaint/outpaint workflow.

Demonstrate:

- actual selection;
- actual inpaint;
- actual expand;
- stored workflow JSON/version unchanged;
- temporary execution adaptation visible in diagnostics/logging;
- result returned through normal Studio run/history pipeline.

---

# PHASE 4 — Post Processing integration

## Goal

Make the existing local Post engine feel native to Studio.

Do not rewrite its processing engine.

Use existing `studio-postprocess.js` behavior and state.

Visible categories:

```text
Adjust
Color
Detail
Effects
Crop
Heal
Upscale
```

Upscale remains unavailable until Phase 11.

Preserve:

- current processing order;
- full-resolution export;
- preview behavior;
- presets/looks;
- curves;
- mixer;
- grading;
- detail/sharpen/noise;
- LUT;
- grain/glow/halation/flare/vignette;
- crop/straighten;
- spot heal;
- WB picker;
- undo/redo;
- before/after where currently available;
- export formats/quality.

Move presentation into the shared Studio sidebar/canvas pattern.

Do not create a plugin/effects system.

## Add only small proven QoL where cheap

The workflow corpus repeatedly suggests:

- Color Match
- Natural Look / de-AI finishing preset

If these can be expressed cleanly using the existing post engine without architectural expansion, they may be added.

Otherwise record as later follow-up.

---

# PHASE 5 — Generate Text + Visual Style Browser

## Goal

Improve prompt authoring without changing execution architecture.

Add a visual textual-style browser under Generate → Text.

Useful behavior:

- searchable style cards;
- categories;
- favorites;
- preview image;
- selected style;
- None;
- style details;
- prompt integration.

Prompt Style is textual prompt composition.

Do not conflate this with image References.

Do not create style packs/marketplace architecture.

Check licenses before bundling catalogs/assets.

---

# PHASE 6 — Shared layered Sketch editor

## Goal

One useful local layered drawing component used by both Generate and Edit.

Execution is ordinary I2I.

```text
Generate Sketch:
blank/base canvas + layers
→ flatten
→ I2I source image

Edit Sketch:
current image as base + layers
→ flatten
→ I2I source image
```

Useful tools:

- Brush
- Pencil
- Eraser
- Line
- Rectangle
- Circle
- Fill
- Eyedropper

Settings:

- size
- opacity
- hardness
- color
- pressure only if already feasible

Layers:

- add
- delete
- rename
- visibility
- opacity
- reorder
- duplicate
- merge/flatten where simple
- protect base image where appropriate

Canvas:

- zoom
- pan
- Fit
- 100%
- fullscreen
- mirror
- practical shortcuts
- undo/redo

Do not introduce a dedicated Sketch workflow requirement.

Do not copy ComfySketch's floating/draggable-panel architecture.

---

# PHASE 7 — Generate Layout: visual prompt authoring

## Goal

Layout is a visual prompt builder, not an execution backend.

User manipulates:

- Object regions
- Text regions
- position
- size
- descriptions
- exact text
- colors where supported
- global description/background
- aspect ratio

Then Studio serializes the composition into the desired IG4-style structured prompt/string and places it into the normal Prompt Tool Input.

```text
visual editor
→ structured prompt string
→ ordinary selected generation workflow
```

Advanced raw JSON/text may be inspectable/editable, but should not dominate the UI.

No Layout workflow type.
No Layout engine.
No generic schema framework.

---

# PHASE 8 — References

## Goal

Make modern multi-image generation/editing first-class without forcing users to create a different workflow for every reference use case.

No Auto method.

Remember method per workflow.

## Reference Method 1 — Multi-image Conditioning Slots

Use when the selected workflow exposes/accepts repeatable image-conditioning slots.

Structural concept:

```text
CLIP + image1 + image2 + ... + prompt
→ CONDITIONING
```

The exact node class is irrelevant.

Support the real capacity exposed by the selected graph/method.

## Reference Method 2 — Reference Latent Chain

For compatible workflows, temporarily add/clone a branch conceptually like:

```text
reference IMAGE
→ VAE Encode
→ Reference Latent
→ existing conditioning
```

Additional references repeat the branch.

## Reference Method 3 — Dedicated Workflow

Allow a configured specialized reference/identity workflow as an override.

## UI

Reference cards should support:

- Upload
- Current
- History
- replace
- remove
- reorder where semantics permit
- stable numbering/identity
- thumbnail

Optional, only when real method supports it:

- strength/boost
- role-specific settings

Do not expose a fake universal strength slider.

## Reference-card QoL

The workflow corpus strongly supports optional per-reference:

```text
Remove Background
```

Reuse existing segmentation/removal infrastructure where possible.

Do not turn it into a new workflow category.

## Prompt helper — optional if bounded

A small `Describe` action for Source/Reference using a VLM may be useful.

This is optional and must not derail the phase.

## Terminology

Do not use "Moodboard" as a synonym for References.

In the audited Krea workflows, Moodboard often means a visual prompt/style browser.

---

# PHASE 9 — Guidance

## Goal

Add real structural guidance while keeping compatibility keyed to the **actual loaded diffusion model**, not the workflow.

Examples:

- Pose
- Depth
- Edge/Canny
- Lineart
- other modes only when concretely supported

## 9.1 Model identity

Guidance mapping belongs to model identity.

Concept:

```text
workflow A ─┐
workflow B ─┼→ same diffusion model identity
workflow C ─┘
                  ↓
           same audited guidance mapping
```

Never key guidance compatibility to workflow name/id.

Prefer strong identity:

1. exact known model hash/manifest identity;
2. architecture/base metadata;
3. filename only as weaker evidence/display.

## 9.2 Smooth automatic discovery + user audit

The user does **not** manually research every ControlNet.

Studio should propose a verified compatible mapping.

However, Studio must not silently trust a guess.

First use:

```text
Detected model:
<exact identity>

Pose guidance:
<recommended compatible provider/weight>

Required preprocessor:
<...>

Source:
<trusted catalog/source>

[Confirm] [Change]
```

After confirmation, remember the mapping for that exact model identity across all workflows.

Do not silently change an already-audited mapping if an online recommendation later changes.

## 9.3 Mapping registry

Keep the implementation small.

A guidance mapping record may contain:

- exact model identity/hash;
- controller/provider;
- exact weight filename;
- expected hash when available;
- supported guidance modes;
- required preprocessor;
- source;
- license;
- dependency version where relevant.

Use trusted current sources such as official ComfyUI/Manager metadata and authoritative model repositories when proposing mappings.

Do not scrape arbitrary filenames and guess.

If no trustworthy match exists:

```text
No verified guidance mapping found.
[Choose manually]
```

Allow the user to confirm and remember a manual mapping for that model.

## 9.4 Execution

Guidance should execute with the generation backend.

When using Modal, preprocessing/controller inference belongs on Modal unless a tiny local preprocessor is clearly more sensible and does not undermine the execution flow.

Temporary graph injection is allowed.

## 9.5 Soft reference guidance vs structural guidance

Do not conflate:

- "use this pose image as a normal multimodal reference"
- real Pose/ControlNet structural guidance

Both may be useful, but they are not the same guarantee.

---

# PHASE 10 — Compare, review, History QoL

## Goal

Make iterative image work comfortable across Generate/Edit/Post/Upscale.

Shared comparison:

- before/after reveal divider;
- synchronized pan/zoom;
- Fit;
- 1:1;
- hold-to-compare if already useful.

History actions:

- Use as Current
- Edit
- Use as Reference
- Post Process
- Upscale
- Download
- Favorite

Reuse History V2.

Do not create an Asset Library.

## Additional small QoL from the workflow corpus

If simple and coherent:

- make fixed vs random seed state obvious;
- preserve source/result metadata in History;
- make expensive final-processing actions visually distinct from normal draft iteration.

Do not create a new candidate/revision database.

---

# PHASE 11 — Upscale

## Goal

Add two explicit, complementary Upscale methods under Post Processing.

No Auto.

Initial methods:

1. **VOSR2**
2. **SeedVR2**

These are deliberately different.

## 11.1 VOSR2

Position as the faster/general super-resolution option.

Expose only meaningful controls required by the concrete implementation, such as:

- scale/target resolution;
- tiling where necessary;
- model variant only if useful.

## 11.2 SeedVR2

Position as heavier generative restoration/upscaling.

Expose only meaningful controls required by the concrete implementation.

Avoid dumping every backend knob into the normal sidebar.

## 11.3 Execution

Both should run on Modal when Modal is the active execution backend.

Do not require the user's T2I/I2I workflow to contain the upscaler.

A small Studio-owned execution path is appropriate because Upscale is downstream image processing independent of the generation graph.

This may be:

- a small internal Comfy graph;
- direct implementation;

choose whichever is simpler and integrates cleanly with existing execution/history.

No generic upscaler engine registry.

## 11.4 Color preservation

The workflow corpus repeatedly shows color drift after refinement/upscaling.

If cleanly implementable, offer:

```text
Preserve Source Color
```

or a post-upscale Color Match action.

Do not block the base phase on this if it becomes substantial.

## Acceptance

Real VOSR2 run.
Real SeedVR2 run.
1:1 comparison.
History integration.
Result can become Current and flow back into Edit/Post.

---

# PHASE 12 — Playground Presets

## Goal

After the underlying primitives work, let users save the current Playground setup as a reusable task.

This is the sole current user-facing preset concept.

Do not revive historical/deprecated preset implementations merely because they use the same word.

Use **Playground Preset** in code where disambiguation is needed.

## 12.1 What a Playground Preset is

A preset references:

- workflow;
- workflow version;
- mode/subtool;
- saved sidebar values;
- field display-label overrides;
- hidden preset prompt;
- optional default visible user prompt;
- chosen execution methods where relevant if they belong to the intended task.

It does not copy/fork the workflow.

## 12.2 Field relabeling

The preset may change presentation:

```text
Reference 1 → Logo
Reference 2 → Product
Prompt      → Instructions
```

Internal semantic identity does not change.

## 12.3 Preset Prompt + User Prompt

### Preset Prompt

- authored while creating/editing the preset;
- hidden during normal use;
- reusable task instruction;
- automatically included on every run.

### User Prompt

- visible in normal Playground;
- job-specific;
- editable;
- may start blank or from an optional saved default.

Backend composition is authoritative and deterministic.

Conceptually:

```text
<preset prompt>

User request:
<user prompt>
```

Handle:
- preset only;
- user only;
- both.

Do not create chat roles, a templating language, or an LLM-prompt framework.

## 12.4 Images are not saved

Per product decision:

- reference images reopen empty;
- source/job images reopen empty;
- masks reopen empty;
- sketch image data is not stored as part of the preset.

Save:
- prompts;
- labels;
- settings;
- workflow/method identity.

## 12.5 Preset examples

The corpus validates use cases such as:

- Outfit Change
- Logo on Product
- Character in Scene
- Pose from Picture
- Character Sheet

These should not become hardcoded Studio tools.

They are user-created recipes over generic engines/features.

## 12.6 History/reproducibility

History must preserve:

- visible user prompt;
- preset identity;
- preset prompt or immutable equivalent needed for replay;
- final submitted prompt;
- workflow/version;
- selected generic method(s);
- actual execution metadata needed for faithful replay.

The normal Playground may hide preset instructions, but History must remain auditable/reproducible.

---

# PHASE 13 — Full integration and simplification

No new architecture.

No large new features.

Run the whole Studio as a user:

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

Exercise:

- T2I
- I2I
- legacy specialized workflow compatibility
- generic Inpaint methods
- generic Expand methods
- generic Reference methods
- Guidance model mapping
- VOSR2
- SeedVR2
- Playground Presets
- Queue
- Experiment
- reload
- current-image chaining
- source replacement
- stale mask behavior
- disabled/error states
- dependency failures
- narrow desktop layout
- console/network cleanliness

## Final simplification pass

Look specifically for:

- leftover Phase-1 assumptions tying Select/Expand/Sketch to legacy types;
- duplicated execution paths;
- old labels;
- unnecessary compatibility shims that are now provably dead;
- stale test selectors;
- redundant state;
- duplicated sidebar concepts;
- accidental model-name branching in generic methods;
- duplicate "preset" concepts;
- generic abstractions introduced during implementation that can now be deleted.

Do not delete compatibility merely because it looks old; prove it is unused first.

---

# 7. Future candidates discovered by workflow audit

These are valuable but **not required for V3 completion** unless Ahmed explicitly promotes them.

## Smart Detailer

Using existing SAM3 infrastructure:

```text
Select → Detect
Face
Eyes
Hands
→ Detail
```

Potential controls:
- threshold
- grow
- feather
- padding
- inpaint resolution
- denoise

## Transparent-object matting

Glass/transparent-object background removal is different from ordinary segmentation.

Potential future removal methods:
- Subject
- Selected Object
- Transparent Object

## Relighting

Some advanced workflows use normal/depth/mask-based relighting.

Powerful, but out of current scope.

## Prompt enhancement / Image-to-Prompt

Could become small Prompt actions:
- Enhance
- Refine
- Describe Source
- Describe Reference

Do not create a separate mode.

---

# 8. Explicitly out of scope

Unless Ahmed later changes scope:

- LoRA browser/library feature;
- Asset Library;
- style marketplace/packs architecture;
- arbitrary installable Studio tools/plugins;
- video/audio/3D;
- faceswap;
- training/dataset UI;
- generic model-download manager;
- PWA/mobile architecture;
- generic graph-patching language;
- automatic method selection for Inpaint/Expand/References/Upscale;
- replacing Comfy workflow internals with Studio-generated pipelines.

Specific LoRAs/models may still be dependencies of a concrete feature.

---

# 9. Parallelization policy

## Aggressively parallelize

- read-only workflow research;
- source/license research;
- compatibility investigation;
- test failure investigation;
- graph diff analysis.

## Moderately parallelize

At most two bounded implementation writers by default.

Prefer disjoint files/components.

## Serialize

One owner integrates shared choke points such as:

- `studio-playground.js`
- common sidebar state;
- Wizard semantic-role definitions;
- workflow run-context contracts;
- execution mutation code.

Do not create abstractions merely to reduce merge conflicts.

## Acceptance is serialized

Even if implementation was developed concurrently:

```text
integrate one phase
→ DevTools validate
→ commit
→ push
→ handoff
→ audit
```

before the next dependent phase becomes authoritative.

---

# 10. Source-of-truth files to inspect

Always inspect the current repo rather than relying on line numbers in this document.

Likely relevant areas:

- `web/studio-playground.js`
- `web/studio-playground-state.js`
- `web/studio-bindable-inputs.js`
- `web/studio-workflow-setup-wizard.js`
- `web/studio-workflow-run.js`
- `studio_workflow_run.py`
- `studio_domain/*`
- `studio_sam.py`
- `web/studio-postprocess.js`
- History V2 implementation
- queue/experiment implementation
- Comfy execution/runtime bridge

Do not touch Golden/loader/performance code unless a Studio feature concretely requires it.

---

# 11. Git discipline

Before work:

- `git status`
- record HEAD
- inspect `origin/main`
- identify dirty/untracked user work
- preserve it

Never:

- force push;
- reset away user work;
- delete unrelated changes;
- rewrite history;
- create separate worktrees unless Ahmed explicitly asks.

At phase end:

- inspect diff;
- verify only intended scope;
- validate;
- commit;
- push;
- verify remote SHA;
- report;
- stop.

---

# 12. Notify-me rule

Use the `notify-me` skill when the **full assigned phase/task is complete**.

Before completion, use it only for genuinely urgent matters that require Ahmed to return to his PC.

Ordinary bugs, failed tests, transient deployment problems, missing dependencies the agent can resolve, implementation inconvenience, or debugging work are **not urgent**.

Keep working through those without notifying.

---

# 13. Anti-overengineering checklist

Before every commit, answer:

- Did I build a framework where an explicit function/switch would work?
- Did I hardcode model names where graph structure could work?
- Did I invent Auto behavior even though the product requires explicit methods?
- Did I duplicate a workflow merely because Studio needed one or two extra operations?
- Did I remove the ability to use a dedicated specialized workflow?
- Did I modify the stored workflow rather than a temporary execution copy?
- Did I add another top-level workflow type?
- Did I expose backend internals unnecessarily to users?
- Did I add a universal slider that the selected method does not actually support?
- Did I rebuild functionality that already exists in Post/SAM3/History?
- Did I make a GPU feature local-only when it should follow the configured backend?
- Did I create another preset concept?
- Did I broaden scope because a workflow corpus contained a cool feature?
- Can any new abstraction be deleted without losing behavior?

If yes, simplify before pushing.

---

# 14. Final definition of done

V3 is complete when:

- [ ] Phase-1 three-mode shell remains coherent.
- [ ] T2I/I2I are the fundamental normal workflow families.
- [ ] legacy inpaint/outpaint/sketch workflows remain compatible as specialized paths.
- [ ] Edit Select is coherent and independent of a required dedicated inpaint workflow.
- [ ] ordinary I2I can perform Inpaint through explicit generic methods.
- [ ] ordinary I2I can perform Expand through explicit generic methods.
- [ ] method choice is manual, never Auto.
- [ ] method choice is remembered per workflow.
- [ ] temporary graph adaptations never modify stored workflow versions.
- [ ] Post Processing is integrated into normal Studio presentation.
- [ ] Visual Style Browser works.
- [ ] Sketch is layered UI → flatten → I2I.
- [ ] Layout is visual prompt authoring → ordinary Prompt.
- [ ] References support explicit generic methods and multiple images.
- [ ] Guidance compatibility is keyed to exact model identity, not workflow identity.
- [ ] Guidance recommendation is smooth but user-audited before trust.
- [ ] confirmed guidance mapping is reused across workflows with the same model.
- [ ] Compare/History QoL supports iterative use.
- [ ] VOSR2 works under Post → Upscale.
- [ ] SeedVR2 works under Post → Upscale.
- [ ] Playground Presets are implemented after the primitives.
- [ ] Presets support editable field labels.
- [ ] Presets support hidden preset prompt + visible user prompt.
- [ ] preset images reopen empty.
- [ ] History preserves prompt/method/workflow provenance.
- [ ] no LoRA browser or Asset Library was introduced.
- [ ] no model-family adapter architecture replaced generic structural methods.
- [ ] no giant generic feature/adapter framework was introduced.
- [ ] every implementation phase has DevTools evidence, pushed SHA, handoff, and independent audit.

---

# 15. One-line architecture rule

> **Keep arbitrary T2I/I2I workflows as the engines; add a small menu of explicit generic structural methods around them, preserve specialized workflows as optional overrides, map Guidance to actual model identity, and only after all primitives work let Playground Presets turn them into reusable user-defined tools.**
