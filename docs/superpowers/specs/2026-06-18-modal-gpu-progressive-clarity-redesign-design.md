# Modal GPU Progressive Clarity Redesign

## Goal

Redesign the Modal GPU popup so it feels calm, deliberate, readable, and high-quality for new users while preserving the existing core behavior.

This pass prioritizes:

- fixed and stable popup sizing
- stronger action hierarchy
- reduced clutter
- progressive disclosure of complexity
- better visual grouping
- lower first-glance overwhelm

## Approved direction

Use **Selective Emphasis + Progressive Collapse**.

This means:

- make the next important action visually obvious
- reduce the amount of simultaneously visible complexity
- hide secondary/advanced controls until needed
- use layout, grouping, and collapse behavior instead of text-heavy onboarding

## User priorities

1. Setup must be dramatically less overwhelming
2. Styling must feel intentional and visibly improved
3. QoL and scanability matter more than raw density
4. The popup must stay one constant size
5. Auxiliary controls should recede visually
6. Users should immediately know where to look next

## Confirmed problems in current UI

### Shell

- popup size shifts visually based on tab content
- header subtitle adds noise without utility
- the shell does not feel compositionally stable

### Dashboard

- healthy-state deployment strip is useless noise
- metric cards are equal-weight clones
- primary CTA is not visually dominant enough
- utility actions compete with primary actions
- page does not clearly communicate “what should I do next?”

### Setup

- section cards are too visually uniform
- 8-step rail reads as a wall of obligations
- too much complexity is visible at once
- profile actions are visually noisy
- LoRA and Axes sections feel like technical dumps
- Review & Run does not feel like a distinct finish zone

### Results

- operational zones exist structurally but still read too flat
- command hierarchy is not strong enough
- summary data lacks dominance and scan clarity
- gallery and comparison areas still need stronger visual separation

### History

- rows are still too dense to skim quickly
- metadata grouping is weak

## Scope

### In scope

- popup shell sizing and header cleanup
- dashboard redesign
- setup redesign
- results redesign
- history redesign
- hover help where useful
- continued use of existing routes and behaviors

### Out of scope

- backend API changes
- experiment schema changes
- rewriting results/history logic beyond presentation and minor QoL structure
- onboarding flows or tutorial overlays
- modal registration/state ownership changes unless tiny hook changes are necessary

## Core design principles

1. **Stable frame**
   - the popup should feel like one application surface, not a container reacting to page length

2. **Primary action dominance**
   - the most useful next action on each page must be visually dominant

3. **Progressive disclosure**
   - default views show essentials first; advanced or secondary tools appear only when needed

4. **Visual quietness**
   - remove nonessential labels, repeated chrome, and dead status boxes

5. **New-user readability**
   - if a new user opens the popup, their eye should land on the important action or current state, not on miscellaneous controls

## Shell redesign

### Fixed popup size

The popup becomes a stable desktop application window.

- target size: approximately **1200 × 780** on desktop
- use a constant height and width envelope rather than content-driven visual changes
- internal regions scroll independently where needed
- changing tabs must not make the shell appear to grow or shrink

### Header

- keep only **Modal GPU** at the left
- remove **Cloud execution and testing**
- keep close button at right
- cleaner horizontal balance and less noise

### Body behavior

- the shell remains constant
- content areas scroll inside the body
- tab transitions should feel stable and aligned, not like a new-size dialog each time

## Dashboard redesign

### Healthy state

When deployment is healthy:

- remove the compact deploy strip entirely
- center the page around **New Experiment** as the dominant CTA
- keep **Resume** and **Open Results** secondary and quieter
- utility actions like comparison/settings become visually subordinate and no longer compete with the main flow

### Unhealthy / blocked state

When deployment is actually blocked or unhealthy:

- keep a hero card
- make it larger and more visually commanding
- put the action to resolve the problem directly inside the hero

### Metrics hierarchy

- stop treating all dashboard cards equally
- **Experiments** becomes the strongest card or data point
- **Workers** and **Last Run** become supporting cards
- supporting information should help orientation, not steal focus

### Intended first glance

Dashboard should answer:

1. start a new experiment?
2. resume something already active?
3. check results?

Everything else is secondary.

## Setup redesign

Setup is the primary complexity-reduction target.

### Intended feeling

Setup should feel like a guided workspace, not a technical wall.

The user should read it as:

1. define the experiment
2. choose workflow/model
3. add optional modifiers
4. adjust essentials
5. review and run

### Progressive collapse

The default state should not show all complexity at once.

- section cards collapse by default or remain visually compact until opened
- current/active section expands clearly
- completed sections can collapse back into small summaries
- secondary content only appears when a section is engaged

### Rail simplification

The current 8-step rail is too noun-heavy and overwhelming.

Replace it with a calmer phase-oriented rail or compact progress model.

Approved direction:

- reduce visual noise in the rail
- use fewer, broader phases rather than shouting every detailed step equally
- keep reliable navigation behavior in the popup
- current phase must be obvious

Exact internal section coverage can still map to existing data structure, but the visible rail should feel lighter.

### Workflows & profile actions

- **Create from Canvas** becomes the obvious primary action within workflow setup
- other profile actions become lower-emphasis utility actions
- duplicate/destructive actions should not sit at the same visual priority as the primary workflow-building action
- repeated toolbar clutter must be reduced

### LoRAs

- do not render a giant editor wall by default
- show a compact starting state with a clear **Add LoRA** action
- only reveal detailed entry editing once the user opts into it
- nested structure should be readable without looking like raw configuration data

### Prompts / Images

- keep them compact and readable
- empty states should feel guided and intentional
- preset selection should not look like dead form output

### Axes

- show essential fields first
- advanced controls should be tucked into a lower-emphasis expandable area
- avoid treating every parameter as equally important for first-time use

Default emphasis should favor the smallest set of controls necessary to get moving.

### Execution

- keep compact
- group the few controls tightly and clearly
- do not give it the same visual presence as more important sections

### Review & Run

- visually distinct finish zone
- stronger surface separation than normal cards
- compile summary and run action grouped clearly
- the final action must feel like the real end of the flow

### Hover help

Tooltip-style help is allowed where it reduces ambiguity without cluttering the interface.

Best candidates:

- advanced axis fields
- LoRA controls
- execution controls
- destructive profile actions

## Results redesign

### Structure

Results should read as a clear operations surface with distinct layers:

1. command bar
2. run summary
3. active progress / checkpoint activity
4. results gallery
5. comparison workspace

### Visual hierarchy

- command bar gets a distinct surface from the main page
- summary should visually dominate before the detailed activity list
- checkpoint activity should be clearly separate from completed outputs
- comparison workspace should feel intentional, not appended

### Command hierarchy

- routine controls should be quieter and smaller
- destructive controls should be more spatially separated and visually distinct
- the user should not have to parse a flat line of equal buttons

### Summary zone

- the most important positive/primary run state should dominate
- failures should still be clearly visible, but not equal-weight to everything else
- status should be immediately glanceable

### Gallery

- give result cards more breathing room
- keep card information curated and scannable
- support fast visual comparison by rhythm and consistency

## History redesign

### Row model

History becomes a skim-first run list.

- use a two-line row structure rather than cramming all metadata into one line
- top line: thumbnail/icon + run name
- second line: status, time, duration, supporting metadata
- supporting model/profile detail can become tooltip or low-emphasis secondary text

### Goal

The user should be able to scan many runs quickly without reading six equally weighted columns per row.

## Styling adjustments required

This pass requires more than token tweaks. It needs stronger page-level styling:

- stronger fixed shell dimensions
- less inline-style entropy
- stronger page-specific surface hierarchy
- compact quiet cards for collapsed setup sections
- stronger finish-zone styling
- calmer utility actions
- larger contrast between primary and secondary CTAs
- better empty-state styling
- more controlled spacing rhythm throughout setup/results/history/dashboard

## File scope

### Primary

- `web/testing-styles.js`
- `web/modal-testing.js`
- `web/testing-dashboard.js`
- `web/testing-setup.js`
- `web/testing-results.js`
- `web/testing-history.js`

### Likely test updates

- `tests/test_testing_shell_integration.py`
- `tests/test_testing_ui_wired.py`
- `tests/test_testing_setup_js.py`
- `tests/test_testing_results_js.py`

## Testing strategy

Add or update structural tests for:

- fixed shell sizing/header changes
- removal of subtitle/deploy-strip healthy-state assumptions
- new dashboard hierarchy hooks
- setup collapse / phase-rail / reduced-clutter structure markers
- results visual zone markers if structure changes
- history skim-layout markers

Manual verification must confirm:

- popup remains visually constant across tabs
- Setup feels dramatically less overwhelming on first open
- Dashboard makes next actions obvious immediately
- Results and History are easier to scan than before

## Acceptance criteria

### Shell

- popup appears constant in size across tabs
- header is quieter and cleaner

### Dashboard

- New Experiment is visually dominant
- healthy deployment strip is gone
- utility controls do not compete with the main flow

### Setup

- first-glance overwhelm is substantially reduced
- not all complexity is visible by default
- most useful actions are visually obvious
- advanced controls are tucked away appropriately
- Review & Run feels distinct and final

### Results

- operational zones feel clearly separated
- summary is more glanceable
- controls are easier to parse

### History

- rows are easier to skim quickly
- metadata grouping is improved

### Overall

- the popup looks intentionally designed, not merely functional
- visual clutter is materially reduced
- the eye is drawn toward the next important task and away from auxiliary controls
