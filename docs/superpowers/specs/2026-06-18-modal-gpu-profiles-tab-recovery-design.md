# Modal GPU Profiles Tab Recovery Design

## Goal

Restore the old workflow profile authoring system as a first-class **Profiles** tab inside the unified Modal GPU modal, without losing any profile-management capability that previously lived in `web/modal-comparison.js`.

## User-approved direction

- Add a new top-level **Profiles** tab
- Keep **all** old profile-management features
- Modernize the UI to match the shared Modal GPU shell and styling
- Make **Profiles** the canonical place to create, edit, map, validate, duplicate, and delete workflow profiles
- Reduce **Setup** so it only selects and configures saved profiles for an experiment

## Current problem

The current Setup rewrite preserved only a thin profile picker surface.

What was lost from the old system:

- dedicated profile authoring flow
- save-current-canvas-as-profile flow
- dedicated saved-profiles workspace
- mapping assistant UI
- profile-oriented editing workflow
- a clear canonical page for profile maintenance

This leaves users with no complete place to:

- create workflow profiles
- repair mappings
- browse profile readiness
- manage profile lifecycle
- edit model triple / profile-facing model configuration in a coherent workspace

## Source of truth

`web/modal-comparison.js` is the functional source of truth for the old profile system and must be treated as the compatibility baseline.

Profile-management capabilities confirmed there:

- save current workflow as profile
- list profiles with readiness status
- display warnings/errors/capabilities
- rename profile
- duplicate profile
- delete profile
- auto-detect slots
- mapping assistant with slot save flow
- context-menu slot assignment integration
- profile dropdown refresh and inline operational feedback

## Scope

### In scope

- add top-level **Profiles** tab to unified modal shell
- create a dedicated `web/testing-profiles.js` module
- migrate/adapt old profile-management behavior from `web/modal-comparison.js`
- preserve old profile APIs and stored data compatibility
- restore profile creation, browsing, validation, duplication, deletion, mapping, and status display
- restore a clear place to edit profile-facing model configuration
- simplify Setup so it is no longer the primary authoring surface for profiles
- add/update structural tests for the new Profiles tab and reduced Setup responsibility

### Out of scope

- changing backend comparison/profile API contracts unless a bug forces it
- changing experiment execution semantics
- redesigning runner/results logic from `modal-comparison.js`
- changing saved profile schema as part of this recovery
- removing legacy `modal-comparison.js` wholesale in the same pass unless safe after migration

## Design principles

1. **Nothing lost**
   - old profile-management capabilities must remain available

2. **Single authoritative home**
   - profile authoring belongs in Profiles, not in Setup

3. **Compatibility first, modernization second**
   - preserve behavior and APIs first, then adapt layout/styling to the new shell

4. **Clear responsibility split**
   - Profiles authors saved workflow profiles
   - Setup composes experiments from saved profiles

5. **Progressive disclosure**
   - list/browse/manage on the left or top level, detailed editing/mapping on selection

## Information architecture

Top-level tabs become:

- Dashboard
- Setup
- Profiles
- Results
- History
- Settings

## Responsibility split

### Profiles tab owns

- create from current canvas
- saved profile browsing
- profile validation state visibility
- profile lifecycle actions
- profile mapping assistant
- profile-facing model configuration editing
- any advanced profile maintenance tasks

### Setup tab owns

- choosing which saved profiles are included in an experiment
- per-experiment overrides only
- prompts, LoRAs, images, axes, execution, review/run
- linking users to Profiles when profile authoring or repair is required

## Profiles tab layout

### 1. Create-from-canvas action card

Top action block with:

- profile name input
- primary **Create from Canvas** action
- inline save status
- helper copy explaining that the current ComfyUI workflow becomes a reusable saved profile

This restores the old top-level authoring entry point.

### 2. Saved profiles workspace

The main area becomes a dedicated workspace.

#### Left pane: saved profiles list

Each row shows:

- profile name
- readiness badge (`ready`, `needs_mapping`, `invalid`)
- compact model stack / triple summary
- warnings/errors preview where useful

Primary actions per row:

- Edit
- Validate
- Duplicate
- Delete

Optional secondary actions:

- Rename
- Open Mapping

#### Right pane: selected profile editor

When a profile is selected, show:

- profile name / id
- readiness status + warnings/errors
- saved workflow summary
- editable model triple / model configuration section
- mapping summary and mapping assistant area
- capability summary
- action footer / toolbar

This is the missing “there is a place to actually work on a profile” surface.

### 3. Mapping assistant

The mapping assistant remains part of the profile system and is not dropped.

It should be integrated into the selected-profile workspace rather than feeling like a disconnected standalone block.

Required slot coverage remains:

- prompt
- negative_prompt
- seed
- steps
- guidance
- width
- height
- input_image

The existing detect-slots flow and slot-save API remain intact.

### 4. Empty states

If there are no saved profiles:

- explain what profiles are for
- show Create from Canvas as the obvious next action
- avoid dead-end wording

## Model configuration recovery

The user explicitly called out missing ability to edit model triples.

The new Profiles tab must expose a dedicated model configuration area that is coherent and profile-centric.

Design requirement:

- model triple editing must not live as a half-hidden side concern in Setup
- it belongs to the selected profile editor in Profiles

Implementation note:

- `modal-comparison.js` clearly displays model stack summaries but does not currently provide full in-place model editing UI
- this recovery pass should use the new Profiles tab to provide a dedicated editing surface for the profile-facing model triple/configuration that Setup attempted to rehome
- if backend persistence is already supported through existing profile payload/update APIs, use that path
- if persistence is not yet supported, the recovery must at minimum preserve old behavior and reintroduce an explicit UI location for model configuration work rather than leaving it stranded in Setup

## Compatibility requirements

- existing `/comfymodal/comparison/profiles*` APIs remain the primary contract
- existing saved profiles remain usable without migration
- old context-menu slot assignment integration must remain functional
- legacy dashboard entry points that open the old comparison profiles UI should either:
  - redirect to the new Profiles tab, or
  - remain temporarily available while the new tab is verified

## File strategy

### New primary file

- `web/testing-profiles.js`
  - dedicated Profiles tab renderer
  - absorbs/adapts profile-authoring behavior from `web/modal-comparison.js`

### Existing files to modify

- `web/modal-testing.js`
  - add `TAB_PROFILES`
  - wire nav button and lazy module mount

- `web/testing-setup.js`
  - remove profile-authoring responsibility
  - keep only profile selection / experiment usage behavior
  - add clear link/CTA to Profiles when authoring is needed

- `web/testing-styles.js`
  - add Profiles workspace styling
  - keep visual consistency with shared modal shell

- `web/modal-comparison.js`
  - may stay as legacy implementation source / compatibility surface during migration
  - optionally expose reusable helpers if extraction is cleaner than duplication

## Testing strategy

### Structural tests

Add coverage for:

- new Profiles tab registration in `modal-testing.js`
- `testing-profiles.js` public renderer export
- create-from-canvas controls
- saved profile list markers
- selected profile editor markers
- mapping assistant markers
- Setup no longer being the primary profile authoring surface

### Focused behavior verification

- open modal and confirm Profiles tab appears
- save current canvas as profile
- select saved profile
- validate / duplicate / delete profile
- open mapping assistant and save mappings
- confirm Setup can still select saved profiles after the refactor

## Risks

1. **Hidden behavior in `modal-comparison.js`**
   - mitigation: inventory old profile features first and implement against that checklist

2. **Setup/Profile responsibility overlap**
   - mitigation: explicitly strip authoring concerns from Setup once Profiles exists

3. **Model editing persistence uncertainty**
   - mitigation: verify existing API support before implementation and avoid inventing incompatible payloads

4. **Legacy entry-point duplication**
   - mitigation: keep temporary compatibility until the new Profiles tab is verified

## Success criteria

- Profiles exists as a first-class top-level modal tab
- users can again create workflow profiles from canvas
- users have a dedicated place to browse and manage profiles
- users can again access mapping assistant behavior
- Setup is no longer the only or primary place trying to manage profiles
- no old profile-management capability is lost in the transition
