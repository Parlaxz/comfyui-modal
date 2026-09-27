# Modal GPU Experiment Setup Workflow Redesign

## Goal

Redesign and implement the Modal GPU **Setup** experience around the user’s actual experimentation workflow:

1. decide whether the experiment is T2I or I2I
2. decide what changes, what is controlled, and what stays at workflow defaults
3. select compatible workflows
4. configure workflow-local model stacks and LoRA configurations
5. configure values only for active tested/controlled variables
6. review the exact matrix and run

The core principle is:

**If it is not relevant to the current experiment, do not show it.**

This redesign replaces the current nine-section Setup information architecture while preserving the existing backend execution path, experiment semantics, and technical checkpoint view.

## Approved direction

Use a **thin normalization layer over the current compiler and execution system**:

- the Setup UI edits one normalized user-intent draft
- a backend authoritative adapter translates that normalized draft into the current compiler input shape
- the existing compiler remains authoritative for final counts and execution
- workflow is the primary experimental container
- model stacks and LoRA configurations remain workflow-specific
- results gain a workflow-oriented presentation adapter while preserving technical checkpoint grouping

## Architecture

### Boundaries

There are two adapters with deliberately separate responsibilities.

#### Frontend adapter

Suggested file:

- `web/testing-setup-adapter.js`

Responsibilities:

- create normalized default drafts
- migrate older frontend drafts into the normalized UI shape
- normalize API responses for rendering
- perform immediate UX validation
- filter relevant controls
- calculate optional provisional display counts/badges
- serialize normalized drafts for API requests
- adapt backend preview and result responses for UI display

The frontend adapter is **not** the final authority for compiler semantics.

#### Backend authoritative adapter

Suggested file:

- `experiment_setup_adapter.py`

Responsibilities:

- validate normalized draft schema
- load and normalize workflow profiles
- normalize legacy profiles without rewriting them on load
- resolve selected model stack IDs
- resolve selected LoRA configuration IDs
- resolve stack–LoRA pairings
- translate Default / Testing / Controlled variable semantics
- translate normalized draft → current compiler input shape
- attach stable normalized dimension metadata to compiled cells
- return authoritative preview counts and compatibility errors
- support compilation of saved drafts after restart without browser-side reconstruction
- reject malformed or manually altered requests

Required flow:

Normalized Setup draft
→ backend setup adapter
→ current compiler specification
→ existing compiler
→ authoritative preview / compiled experiment

There must be exactly **one Python path** that produces the current compiler input shape.

### Existing compiler authority

The current compiler and execution system remain authoritative.

- frontend preview badges may use lightweight local multipliers for responsiveness
- final preview counts come from the backend adapter + existing compiler
- Run always performs fresh backend validation and compilation
- count mismatches between provisional UI badges and backend totals are implementation defects, not a normal warning state

### Lead/subagent split

One lead integration agent owns:

- final UX coherence
- normalized schema consistency
- backend/frontend adapter contract
- integration quality
- verification and browser signoff

Subagent lanes:

1. backend authoritative adapter and representability tests
2. profile normalization / migration / persistence
3. setup information architecture and tri-state controls
4. workflow model-stack and LoRA configuration UX
5. preview and review integration
6. results grouping adapter
7. styling and accessibility
8. tests and browser verification

## New visible Setup structure

Replace the existing Setup page with five visible sections:

1. Generation Type
2. What Changes?
3. Workflows
4. Test Values
5. Review & Run

The Setup page should feel like a compact experiment builder, not a direct exposure of backend fields.

## Normalized Setup draft schema

The normalized draft stores **user intent only**. It does not persist transient preview state.

```js
{
  schema_version: 1,
  name: "",
  notes: "",
  generation_type: "t2i" | "i2i",

  variable_modes: {
    prompt: "testing",
    negative_prompt: "default" | "controlled",
    input_image: "default" | "testing" | "controlled",
    model_stack: "default" | "testing",
    lora_configuration: "default" | "testing" | "controlled",
    seed: "default" | "testing" | "controlled",
    sampler: "default" | "testing" | "controlled",
    scheduler: "default" | "testing" | "controlled",
    steps: "default" | "testing" | "controlled",
    guidance: "default" | "testing" | "controlled",
    denoise: "default" | "testing" | "controlled",
    resolution: "default" | "testing" | "controlled"
  },

  workflows: [
    {
      profile_id: "",
      enabled: true,
      selected_profile_revision: 0,
      selected_workflow_hash: "",
      selected_model_stack_ids: ["default"],
      selected_lora_configuration_ids: ["workflow_default"],
      controlled_lora_configuration_id: null,

      stack_lora_scope: {
        mode: "all_selected_stacks" | "selected_stacks" | "per_stack_matrix",
        selected_stack_ids: [],
        unselected_stack_fallback: "no_lora" | "workflow_default" | null,
        pairings: {
          "stack_id": ["no_lora", "workflow_default", "cfg_a"]
        }
      },

      per_workflow_overrides: {
        controlled_values: {
          seed: null,
          sampler: null,
          scheduler: null,
          steps: null,
          guidance: null,
          denoise: null,
          resolution: null
        },
        tested_values: {
          samplers: null,
          schedulers: null,
          steps: null,
          guidance: null,
          denoise: null,
          resolutions: null
        }
      }
    }
  ],

  tested_values: {
    prompts: [
      { id: "p1", text: "", negative_override: null, enabled: true }
    ],
    input_images: [],
    seeds: [],
    samplers: [],
    schedulers: [],
    steps: [],
    guidance: [],
    denoise: [],
    resolutions: []
  },

  controlled_values: {
    negative_prompt: null,
    input_image_id: null,
    input_image_by_profile_id: null,
    seed: null,
    sampler: null,
    scheduler: null,
    steps: null,
    guidance: null,
    denoise: null,
    resolution: null
  },

  prompt_image_pairing: {
    mode: "cartesian" | "paired" | "fixed_image_per_workflow",
    pairs: [],
    fixed_image_by_profile_id: {}
  },

  compatibility_mode: "shared_strict" | "per_workflow",

  advanced_execution: {
    container_mode: "single" | "multi",
    max_containers: 1,
    output_override: null,
    autosave_behavior: null,
    metadata_sidecar: null,
    failure_behavior: "block"
  }
}
```

### Draft rules

- inactive controlled values are `null`
- controlled negative prompt may be `""` and that remains distinct from `null`
- prompt starts active in Testing with at least one usable item
- testing lists remain empty until their variable is active, except Prompt
- transient preview state is not persisted in the draft
- stale profile detection uses `selected_profile_revision` and `selected_workflow_hash`
- drafts stay compact and do not embed full profile payloads

### Frontend runtime state

Preview/runtime state lives separately, for example:

```js
{
  draftFingerprint: "",
  provisionalPreview: null,
  authoritativePreview: null,
  previewStatus: "idle" | "loading" | "ready" | "error",
  previewError: null,
  lastCompiledAt: null
}
```

Any cached preview must include:

- draft fingerprint
- profile revision/hash set
- adapter schema version
- compiler schema/version

Stale previews must be discarded when any fingerprint changes.

## Variable mode semantics

### Prompt

- Prompt is always present.
- Prompt starts in `testing`.
- One prompt still behaves as a one-value prompt axis.
- Prompt cannot return to Default and disappear.

### Negative prompt

For this implementation, negative prompt supports only:

- `default`
- `controlled`

Prompt items may carry `negative_override` values.

Precedence:

1. prompt item `negative_override` when explicitly present
2. controlled negative prompt when `variable_modes.negative_prompt === "controlled"`
3. workflow default negative prompt when mode is `default`

Independent Negative Prompt testing is **not exposed** in this pass.

### Input image

Visible only for I2I.

- `testing`: multiple input images form an axis
- `controlled`: one global image or one image per workflow depending on pairing mode
- `default`: allowed only when the workflow/profile explicitly supports workflow-local saved image behavior

### Model Stack

Model Stack belongs to workflows.

- `default`
- `testing`

No global Controlled mode.
No UNET × CLIP × VAE Cartesian expansion.

### LoRA Configuration

One source of truth:

- `variable_modes.lora_configuration`

Allowed modes:

- `default`
- `testing`
- `controlled`

Workflow entries store only selections and pairings, not a duplicate LoRA mode field.

### Sampling variables

Each of Seed / Sampler / Scheduler / Steps / Guidance / Denoise / Resolution supports:

- `default`
- `testing`
- `controlled`

Default must translate into workflow-owned compiler behavior, not a frontend fallback value.

## Normalized workflow profile shape

Stored profiles preserve unknown legacy fields. Normalized runtime profiles expose only setup-safe metadata.

```js
{
  profile_id: "",
  name: "",
  normalized_profile_schema_version: 1,
  stored_schema_version: 0,
  revision: 0,
  workflow_hash: "",

  workflow_mode: "t2i" | "i2i" | "both" | "needs_confirmation",
  workflow_mode_source: "legacy_default" | "explicit" | "confirmed" | "inferred",

  metadata_state: "explicit" | "legacy_default" | "needs_confirmation" | "invalid",
  migration_badge: null | "Legacy profile" | "Validated" | "Mode needs confirmation",

  model_stacks: [
    {
      id: "default",
      name: "Default",
      source: "legacy_synthesized" | "explicit",
      loader_target_group_id: "g_default",
      triple: { unet: "", clip: "", vae: "" },
      compatibility: {
        workflow_modes: ["t2i"],
        reasons: []
      }
    }
  ],
  default_model_stack_id: "default",

  lora_slots: [],
  lora_configurations: [],

  mapping_capabilities: {
    common: {},
    t2i: {},
    i2i: {}
  },

  last_validated_at: null,
  validation: {
    status: "ready" | "needs_mapping" | "invalid",
    warnings: [],
    errors: []
  }
}
```

### Legacy profile normalization

All current saved profiles are known legacy **T2I** profiles.

Legacy profile with no explicit `workflow_mode` normalizes in memory as:

- `workflow_mode: "t2i"`
- `workflow_mode_source: "legacy_default"`
- `metadata_state: "legacy_default"`

Rules:

- immediately usable in T2I Setup
- not selectable for I2I until explicitly updated/edited/validated
- not rewritten merely because it was loaded or listed
- persisted only on validate, edit/save, explicit confirm, or update-from-canvas
- no misleading “Inferred T2I” badge

Optional subtle badge text may be `Legacy profile`.

### Capability rules

Capabilities are mode-aware.

Examples:

- missing input-image mapping:
  - usable for T2I
  - incompatible for I2I
- missing LoRA slots:
  - usable normally
  - LoRA Configuration testing disabled
- missing scheduler mapping:
  - usable when Scheduler is Default
  - incompatible when Scheduler is Testing or Controlled
- missing alternate model stacks:
  - default stack usable
  - Model Stack testing warns when only one stack exists

Do not make the whole profile unusable when only one optional experimental capability is missing.

## LoRA configuration shape

LoRA configurations are workflow-local and discriminated by `kind`.

```js
{
  id: "workflow_default",
  name: "Workflow Default",
  kind: "workflow_default",
  source: "legacy_synthesized" | "explicit",
  entries: []
}
```

```js
{
  id: "no_lora",
  name: "No LoRA",
  kind: "no_lora",
  source: "system",
  entries: []
}
```

```js
{
  id: "detail_boost",
  name: "Detail Boost",
  kind: "explicit",
  source: "explicit",
  entries: [
    {
      slot_id: "slot_1",
      lora_name: "detail.safetensors",
      model_strengths: [0.6, 0.8, 1.0],
      clip_strengths: [1.0],
      enabled: true
    }
  ],
  compatible_model_stack_ids: ["default", "quality"]
}
```

Rules:

- ordered entries remain ordered
- zero strength is valid
- empty required strength lists are invalid
- `workflow_default` preserves the workflow’s saved LoRA chain
- `no_lora` explicitly clears mapped LoRA slots
- explicit configurations must fit slot capacity
- configuration IDs are unique within one profile
- compatibility with stacks is explicit or centrally validated
- strength combination expansion is deterministic

## I2I prompt-image pairing schema

```js
{
  prompt_image_pairing: {
    mode: "cartesian" | "paired" | "fixed_image_per_workflow",
    pairs: [
      { prompt_id: "p1", image_id: "img1" }
    ],
    fixed_image_by_profile_id: {
      "profile_a": "img1"
    }
  }
}
```

Rules:

### Cartesian

Every enabled prompt pairs with every enabled image.

### Paired

Requires explicit resolved pairs.

If positional pairing is supported in the UI, the backend preview must still return the final explicit resolved pairs.

### Fixed image per workflow

Requires one selected image per enabled workflow/profile.

Missing pairings block Run.

The authoritative preview must surface resolved prompt-image pairs.

## Profile persistence and migration safety

### Stored profile fields to add on persisted migration

Recommended normalized fields:

- `schema_version`
- `workflow_mode`
- `workflow_mode_source`
- `model_stacks`
- `default_model_stack_id`
- `lora_slots`
- `lora_configurations`
- `mapping_capabilities`
- `last_validated_at`
- `workflow_hash`
- `revision`

### Persistence rules

- do not rewrite profiles on ordinary load
- preserve unknown legacy fields on read-modify-write
- preserve original workflow snapshots
- write atomically
- make migration idempotent and deterministic
- write a reversible backup before first persisted migration, or preserve equivalent reversible legacy content

Stored profile responses sent to the frontend must remain reasonably sized and must not include the full unknown legacy payload unless explicitly requested by an advanced profile editor flow.

## Stale profile handling

Workflow selections store:

- `profile_id`
- `selected_profile_revision`
- `selected_workflow_hash`

At preview / Run time:

- load the latest stored profile
- compare revision/hash
- if changed, block silent acceptance
- surface: profile updated since this draft was configured
- require revalidation / accept latest / review changes
- revalidate selected stack IDs, LoRA configuration IDs, and mappings

Deleted or renamed referenced IDs must produce actionable errors.

## Translation semantics

### One resolved workflow configuration

The adapter translates explicit workflow configurations, not separate global model axes.

One resolved configuration is:

- workflow profile
- selected model stack
- selected LoRA configuration
- valid stack–LoRA pairing

### Required preservation

The adapter must preserve:

- workflow profile identity
- workflow revision/hash identity
- workflow mode
- selected model stacks
- selected LoRA configurations
- stack–LoRA pairings
- tested variables
- controlled variables
- workflow-owned defaults
- prompt/image pairing behavior
- per-workflow override precedence

### Default / Testing / Controlled

- Default → workflow-owned compiler behavior
- Testing → multi-value axis expansion
- Controlled → one injected selected value

The adapter must not flatten model stacks into independent UNET / CLIP / VAE axes.

## Representability audit requirement

Before the full workflow/LoRA UI is considered stable, prove that the current compiler path can exactly represent these cases:

1. one workflow, two stacks, no LoRA
2. one workflow, one stack, three LoRA configurations
3. one workflow, two stacks, same LoRA configurations across both
4. one workflow, two stacks, LoRA configurations on only one stack
5. one workflow, two stacks, different LoRA configurations per stack
6. two workflows with separate stack and LoRA sets
7. explicit No LoRA alongside explicit LoRA configurations
8. Workflow Default alongside explicit configurations
9. LoRA strength sweeps inside one configuration
10. Controlled LoRA configuration, one per workflow

If the current compiler input shape cannot represent them exactly:

- make the smallest necessary compiler-schema extension
- keep execution behavior intact
- do not encode pairings through naming conventions
- do not silently broaden the matrix

## Preview strategy

Preferred strategy:

- local UI may show tiny immediate multiplier badges
- after a 300–500 ms debounce, send the normalized draft to the backend preview endpoint
- backend authoritative adapter validates + translates + compiles
- UI shows authoritative totals
- stale preview responses must not replace newer ones
- Run always revalidates even if preview previously succeeded

If backend preview latency is low enough, exact backend preview may be used exclusively.

## Stable normalized dimensions on compiled cells

Each compiled cell must carry explicit presentation metadata:

```text
normalized_dimensions: {
  profile_id,
  workflow_name,
  workflow_mode,
  workflow_revision,
  workflow_hash,
  model_stack_id,
  model_stack_name,
  lora_configuration_id,
  lora_configuration_name,
  stack_lora_pairing_id,
  prompt_id,
  input_image_id,
  seed,
  sampler,
  scheduler,
  steps,
  guidance,
  denoise,
  resolution_id
}
```

Also attach:

- normalized draft schema version
- adapter translation schema version

This metadata must survive:

- compilation
- scheduler persistence
- remote execution
- terminal events
- history
- results API

Results must not reverse-engineer model-stack or LoRA identity from filenames.

## Results grouping adapter

Results grouping is presentation-only.

Keep persisted execution identity and technical checkpoint grouping intact.

Expose normalized dimensions such as:

- Workflow
- Model Stack
- LoRA Configuration
- Prompt
- Input Image
- Seed
- Sampler
- Scheduler
- Steps
- Guidance
- Denoise
- Resolution

### Default grouping rules

1. top-level group: Workflow
2. first meaningful Testing dimension: Rows
3. second meaningful Testing dimension: Columns
4. remaining Testing dimensions: filters or nested groups
5. if only Prompt is tested:
   - Rows: Prompt
   - Columns: Model Stack or LoRA Configuration only when they vary
6. if there is no meaningful second axis:
   - use a one-dimensional strip/list rather than inventing a technical axis

Controlled dimensions belong in the fairness/summary treatment.
Default dimensions belong in metadata, not tested-axis controls.
Technical checkpoint view remains explicitly selectable.

## Setup section behavior

### 1. Generation Type

- first decision: T2I vs I2I
- T2I hides input-image controls
- I2I shows input-image controls and requires valid image mapping
- legacy profiles default to T2I and do not appear in I2I compatibility lists until explicitly upgraded

### 2. What Changes?

- tri-state tiles for relevant variables
- state text is visible, not color-only
- reset all / category reset
- Prompt remains mandatory
- Model Stack supports Default/Testing only
- LoRA Configuration uses experiment-level mode + workflow-level pairings

### 3. Workflows

- show compatible workflows first
- hide incompatible workflows behind disclosure with reasons
- profile cards show workflow mode, model-stack summary, LoRA summary, compatibility, revision/hash, migration badge, actions
- actions include Confirm, Validate, Update from canvas, Edit mappings, Duplicate, Advanced editor entry

### 4. Test Values

- show only Testing and Controlled variables
- Default variables do not appear
- paired prompt-negative behavior follows the documented precedence rules
- input-image pairing controls appear only when relevant

### 5. Review & Run

- preview auto-updates from authoritative backend compile
- per-workflow multiplication summary is shown
- controlled/default/tested fairness summary is shown
- invalid combinations block Run
- advanced execution settings are secondary

## Validation boundaries

### Frontend immediate validation

- illegal tile transitions
- missing local editor values
- relevance filtering
- obvious incompatible selections
- stale response suppression

### Backend authoritative validation

- normalized draft schema
- referenced profile revision/hash
- stack/configuration ID existence
- stack–LoRA pairing legality
- mode-aware capability checks
- final compiler translation
- exact total counts

## Test strategy

Write failing tests first.

Required coverage includes:

- generation type filtering
- tri-state behavior
- relevance filtering
- profile legacy normalization and no-rewrite-on-load
- explicit persistence on validate/edit/confirm/update
- synthesized Default stack
- synthesized Workflow Default and No LoRA
- LoRA pairing representability cases
- negative prompt precedence
- prompt-image pairing modes
- stale profile detection
- authoritative preview flow
- normalized dimensions attached to cells
- workflow-oriented results grouping with technical fallback
- draft persistence and migration behavior
- browser verification of the real ComfyUI modal flow

## Out of scope

- new execution backends
- scheduler/runtime redesign
- Modal scaledown changes
- cost/time/storage estimators
- test templates
- global loose model axes
- global loose LoRA axes
- mixed T2I/I2I runs
- unrelated visual redesign outside Setup and required Results grouping

## Conclusion

This architecture keeps the current compiler and execution pipeline authoritative, moves final semantic translation to the backend, preserves legacy T2I profiles safely, models workflow-local stacks and LoRA configurations explicitly, and provides a workflow-oriented Setup and Results experience without changing underlying execution identity.
