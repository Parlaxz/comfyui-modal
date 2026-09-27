# Modal GPU Setup + Results Clarity Rebuild

## Goal

Rebuild the **Setup** and **Results** pages in Modal GPU so they feel calm, legible, guided, and operationally clear.

This pass is specifically about:

- reducing overwhelm
- improving grouping and spacing
- making navigation reliable
- improving QoL and action hierarchy
- making the popup feel intentionally designed rather than stacked

## User-approved direction

Use **Balanced Clarity**:

- better grouping
- better styling
- more breathing room
- easier navigation
- stronger tabs and organization
- never feeling “what does all this do?”

## Current problems found

### Setup

- too many blocks have equal visual weight
- duplicated “Profile Actions” treatment makes the flow feel noisy
- section spacing is inconsistent and visually cramped
- controls read as a long stack instead of a guided sequence
- LoRA and Axes sections feel like raw form dumps
- the sticky step rail is present, but interaction is unreliable

### Results

- controls, picker, progress, grid, and comparison feel like one flat column
- dangerous actions are not separated strongly enough from routine controls
- progress hierarchy is weak
- result grid lacks enough visual rhythm and calm structure
- empty states are functional but not helpful enough

### Navigation bug confirmed

The Setup step rail does not reliably navigate to the intended section inside the popup.

Root cause area:

- `web/testing-setup.js`
- click behavior currently uses `scrollIntoView()` against a nested modal scroll context
- active-step tracking is not properly tied to the popup scroll container

Main modal top tabs were functional in live repro. Settings left-nav was also functional in live repro. The confirmed broken navigation target in this pass is the **Setup step rail / section navigation inside the popup**.

## Scope

### In scope

- full visual and structural cleanup of `Setup`
- full visual and structural cleanup of `Results`
- fix Setup rail navigation behavior
- improve spacing, hierarchy, and button semantics in both pages
- improve empty states, grouping, and reading order
- add/adjust tests for the new structure and navigation hooks

### Out of scope

- backend API changes
- experiment schema changes
- comparison engine logic changes
- deep settings-page redesign outside wrapper-level polish
- history-page redesign in this pass
- modal registration/state ownership rewrites

## Design principles

1. **One primary action per zone**
   - each area should make the next action obvious

2. **Breathing room without waste**
   - use larger section spacing and calmer grouping, but avoid empty decorative space

3. **Progressive complexity**
   - simple things visible first, deeper controls grouped and visually contained

4. **Structural clarity over ornament**
   - solve the feeling of mess through layout, grouping, and type hierarchy, not decoration

5. **Reliable navigation**
   - if a rail, tab, or control suggests movement, it must work correctly inside the popup scroll model

## Setup redesign

### Intended mental model

The Setup page should read as:

1. define the experiment
2. choose workflows/models
3. add optional modifiers
4. tune axes / execution
5. review and run

It should feel like a guided editor, not a giant form wall.

### Layout model

Setup will use three layers:

#### 1. Sticky step rail

- remains at the top of the scrollable Setup content
- uses larger spacing and clearer state differentiation
- current step is obvious
- completed steps are visually lighter than current but clearly valid
- error state is text + visual marker, not color-only
- rail clicks scroll the popup body to the correct section anchor
- active step updates based on the popup’s actual scroll container

#### 2. Section canvas

- each section becomes a calmer card with clearer internal spacing
- stronger vertical rhythm between sections
- section headers get small helper text or action context only where useful
- internal groups use field rows/grids instead of endless stacked controls

#### 3. Review & Run finish zone

- feels like a final stage, not just another card
- compile output, validation, and run CTA grouped together
- validation errors are readable and point back to the right area
- run action visually stands alone as the final commitment action

### Section-by-section behavior

#### Experiment

- simple, quiet first step
- name is primary
- notes is secondary
- no extra noise

#### Workflows & Models

- becomes the main place for profile/workflow selection
- profile rows get better spacing and clearer model metadata treatment
- helper text becomes smaller and less intrusive

#### Profile Actions

- no longer reads like a duplicate standalone step
- folds into contextual toolbar treatment attached to workflow/profile management
- actions ordered by frequency and safety:
  - Refresh
  - Create from Canvas
  - Validate
  - Duplicate
  - Delete
- destructive action visually separated from routine actions

#### LoRAs

- group each LoRA selection as a contained block
- entry rows become more readable and less cramped
- add/remove controls align consistently
- nested structure should be obvious at a glance

#### Prompts / Images

- cleaner preset list styling
- stronger empty-state treatment
- less dead gray text, more guided language

#### Axes

- convert from raw stacked field list into grouped field grid
- related numeric fields align visually
- labels and helper tone become clearer
- reduce the “parameter dump” feeling

#### Execution

- compact, clear, low-noise
- mode and max-containers belong in a small grouped layout

#### Review & Run

- compile summary area appears intentional and readable
- results of compilation summarized cleanly
- final Run action clearly separated and prominent

## Results redesign

### Intended mental model

The Results page should answer, in order:

1. what run am I looking at?
2. what can I do right now?
3. is it healthy / progressing?
4. what is actively running?
5. where are finished outputs?
6. how do I compare outputs?

### Layout model

Results will use five zones:

#### 1. Run command bar

- experiment picker and reload belong together
- routine actions grouped together
- dangerous actions visually separated
- controls should scan as command groups, not one flat button strip

#### 2. Run status summary

- compact summary card or band for completion / failures / skipped / status
- stronger visual hierarchy than current text-only counters
- overall run state should be readable in one glance

#### 3. Checkpoint activity

- active checkpoint cards grouped and spaced consistently
- progress bars and checkpoint metadata clearer
- “no active checkpoints” idle state should feel intentional

#### 4. Results gallery

- cleaner grid spacing and card rhythm
- prompt/title first, metadata second
- better failure-state styling
- card information should feel curated, not crammed

#### 5. Comparison workspace

- comparison area visually distinct from the result grid
- reads like a dedicated tool area rather than a leftover section

### Controls hierarchy

- **Resume** remains primary
- **Pause** secondary with warning tint
- **Stop after current** warning outlined
- **Stop now** destructive and spatially separated
- **Run missing** secondary utility action

### Card-face content

Card face keeps:

- thumbnail
- prompt/title
- seed
- short model label
- runtime
- attempt badge
- failure message when relevant

The card must still feel light and scannable.

## Navigation fix design

### Required changes

- replace unreliable `scrollIntoView()` behavior for Setup sections with popup-scroll-aware navigation
- compute section offsets relative to the popup body / local scroll container
- ensure clicking a rail item scrolls the correct container
- ensure active-step tracking uses the correct root and thresholds for the popup
- avoid stale current-step highlighting after rail navigation

### Expected behavior

- clicking a step should bring that section near the top of the Setup viewport
- active state should update immediately and remain correct during manual scroll
- sticky rail should remain usable throughout long forms

## Visual system adjustments needed

These pages need a second-pass refinement in `web/testing-styles.js`:

- larger inter-section gaps for Setup and Results
- cleaner field/grid utilities
- clearer toolbar grouping utilities
- calmer helper-text styling
- better empty-state block styling
- better command-bar grouping for Results
- stronger separation utilities for destructive vs routine controls
- improved result-card and checkpoint-card spacing

## Files in scope

### Primary

- `web/testing-setup.js`
- `web/testing-results.js`
- `web/testing-styles.js`

### Possible hook-level support

- `web/modal-testing.js` only if minimal wrapper/class hooks are needed

### Tests

- `tests/test_testing_setup_js.py`
- `tests/test_testing_results_js.py`
- `tests/test_testing_shell_integration.py`
- `tests/test_testing_ui_wired.py`

## Testing strategy

Add or update source-structure tests for:

- setup rail hook changes
- scroll-container-aware navigation hooks
- clearer grouped Results structure markers
- control-group hierarchy hooks
- empty-state and summary-zone markers where appropriate

Manual verification must confirm:

- Setup rail click navigation works in the popup
- current step tracking stays correct during scroll
- Setup feels less overwhelming and more guided
- Results reads in a clear operational order
- destructive controls are easier to distinguish
- no horizontal overflow at laptop width

## Acceptance criteria

### Setup

- no longer feels like a stacked wall of equally weighted blocks
- rail navigation works reliably inside the popup
- current/completed/error step states are clearer
- workflow/profile management feels consolidated rather than duplicated
- Axes and LoRAs read as organized systems instead of raw form dumps
- Review & Run feels like a deliberate final stage

### Results

- controls no longer read as one flat strip
- run summary is glanceable
- checkpoint activity is easier to parse
- grid has better rhythm and card calmness
- comparison area feels intentional
- empty states feel guided, not abandoned

### Overall

- both pages feel calmer, clearer, and easier to use
- reduced cognitive load is obvious on first open
- no backend behavior changes required
