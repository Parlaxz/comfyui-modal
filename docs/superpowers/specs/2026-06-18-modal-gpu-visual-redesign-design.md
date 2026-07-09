# Modal GPU Visual Redesign Design

## Goal

Upgrade the unified **Modal GPU** frontend from functional scaffolding into a fit, efficient, minimalist, complete, and professional ComfyUI-native tool without changing its core behavior.

## Canonical product naming

- Primary product/sidebar/header title: **Modal GPU**
- Experiment area label: **Experiments**
- Optional supporting subtitle: **Cloud execution and testing**

Do not mix the product name with older labels such as “Modal Testing” or “Testing Suite” in the visible UI.

## Product framing

This interface is a cloud GPU experimentation and operations surface inside ComfyUI. It must feel precise, reliable, and fast. The redesign should communicate:

- deployment readiness at a glance
- clear action hierarchy
- compact but readable operational density
- professional dark-mode quality aligned with ComfyUI

The approved direction is **Enhanced Dark Tooling — restrained polish**.

## Operating principles

1. **Same structure, better system**
   - Keep the current modal shell and tab structure.
   - Improve visual quality primarily through a tokenized style system, targeted markup hooks, and removal of inline-style entropy.

2. **One accent, semantic status colors**
   - Use a single cool blue accent for interaction.
   - Reserve green / amber / red for status, success, warning, and error only.

3. **Elevation over decoration**
   - Differentiate surfaces by luminance steps, borders, and subtle shadow.
   - Avoid glass, heavy gradients, neon, or decorative motion.

4. **Data hierarchy is visual hierarchy**
   - The most important object on each screen gets the strongest visual weight.
   - Secondary and tertiary information recede through spacing, scale, muted text, and surface treatment.

5. **ComfyUI-native fit**
   - Respect the host app’s dark theme and practical tooling feel.
   - The redesign should feel built-in rather than imported from another product.

## Non-goals

This pass does **not** include:

- route or response-schema changes
- experiment-state semantic changes
- new backend work
- new polling or new persistent state
- control behavior rewrites
- deeper legacy settings panel redesign
- A/B interaction redesign

Only restore already-existing visible data if styling or wrapper changes make it necessary.

## Design system

### Color tokens

- `--color-bg-base: #181822`
- `--color-bg-toolbar: #1b1b27`
- `--color-bg-surface: #20202c`
- `--color-bg-raised: #252532`
- `--color-bg-overlay: rgba(0, 0, 0, 0.72)`
- `--color-bg-input: #171723`
- `--color-bg-hover: #2a2a38`
- `--color-bg-selected: #242c3d`

- `--color-border-default: #2d2d3a`
- `--color-border-strong: #353545`
- `--color-border-interactive: #454559`
- `--color-border-focus: #5a7fdb`
- `--color-border-danger: #ef4444`

- `--color-text-primary: #e1e4ea`
- `--color-text-secondary: #9aa3b2`
- `--color-text-muted: #6f7785`

- `--color-accent: #5a7fdb`
- `--color-accent-hover: #6a8ceb`
- `--color-accent-active: #4d6fbe`
- `--color-accent-muted: rgba(90, 127, 219, 0.18)`
- `--color-focus-ring: rgba(90, 127, 219, 0.24)`
- `--color-selection: rgba(90, 127, 219, 0.14)`

- `--color-success: #4ade80`
- `--color-success-bg: rgba(74, 222, 128, 0.12)`
- `--color-warning: #f59e0b`
- `--color-warning-bg: rgba(245, 158, 11, 0.12)`
- `--color-danger: #ef4444`
- `--color-danger-bg: rgba(239, 68, 68, 0.12)`
- `--color-info-bg: rgba(90, 127, 219, 0.12)`

- `--color-disabled-bg: #1c1c28`
- `--color-disabled-text: #616877`

### Spacing tokens

- `--space-xs: 4px`
- `--space-sm: 8px`
- `--space-md: 12px`
- `--space-lg: 16px`
- `--space-xl: 20px`
- `--space-2xl: 24px`

### Radius tokens

- `--radius-sm: 4px`
- `--radius-md: 6px`
- `--radius-lg: 8px`

### Typography tokens

- `--font-size-xs: 11px`
- `--font-size-sm: 12px`
- `--font-size-base: 13px`
- `--font-size-lg: 14px`
- `--font-size-xl: 16px`

- `--font-weight-normal: 400`
- `--font-weight-medium: 500`
- `--font-weight-semibold: 600`

- `--line-height-tight: 1.25`
- `--line-height-base: 1.45`

Typography rules:

- system sans for UI
- monospace only for IDs, hashes, file paths, seeds, timings
- no decorative fonts
- uppercase labels only for compact metadata headings, not all form labels

### Dimension tokens

- `--control-height-sm: 28px`
- `--control-height-md: 36px`
- `--header-height: 52px`
- `--tab-height: 40px`
- `--sidebar-width: 188px`
- `--modal-max-width: 1240px`
- `--modal-height: 90vh`

### Motion tokens

- `--duration-fast: 120ms`
- `--duration-normal: 180ms`
- `--ease-standard: cubic-bezier(0.2, 0, 0, 1)`

Only animate hover, focus, opening, selection, and small progress/state changes.

## Shell redesign

The popup remains the main application shell.

### Header

- visible title: **Modal GPU**
- optional subtitle: **Cloud execution and testing**
- slightly darker header background than body
- compact header status slot is allowed if needed for deployment/connection/worker summaries

### Modal body

- body background one step darker than cards to create inset depth
- subtle large shadow separates modal from overlay
- styled thin scrollbar
- no browser-default visible controls inside redesigned areas

### Tab navigation

- keep horizontal tab row
- stronger active state: color + weight + underline
- subdued inactive tabs
- subtle hover background
- keyboard navigable

## Dashboard redesign

Dashboard should make the right next action obvious.

### Blocked / unhealthy state hierarchy

When deployment is unwarmed, deploying, failed, or out of date:

1. **Deployment / warmup hero**
2. required action
3. experiments / workers / recent runs

### Healthy state hierarchy

When deployment is healthy and ready:

1. **New Experiment** primary CTA
2. Resume active/draft experiment
3. Open Results
4. compact deployment status strip
5. utility toolbar: Comparison Profiles / Quick Comparison / Settings
6. compact metric cards for Experiments / Workers / Last Run

### Tier definitions

- **Hero card** only when action is required
- **Utility toolbar** for secondary tools, not primary CTA
- **Metric cards** for scan-only operational stats

### Empty states

Use compact, helpful empty states with guidance and action language instead of plain gray text.

## Setup redesign

Setup is a **single-page section editor with navigational step rail**, not a forced Next/Back wizard.

### Exact 8 steps

1. Experiment
2. Workflows & Models
3. LoRAs
4. Prompts
5. Images
6. Axes
7. Execution
8. Review & Run

### Step rail behavior

- sticky at the top of the content panel
- horizontal on wide layouts
- compact or horizontally scrollable on narrower layouts
- current step label always visible
- clicking a step scrolls to its section
- completed steps clickable
- invalid steps show error badges
- scroll position updates the active step

### Section cards

- proper elevated cards with header bar and padded body
- consistent spacing and visual boundaries
- optional collapse allowed if it improves density

### Form fields

Inputs, selects, and textareas must receive:

- dark control background
- consistent border treatment
- visible focus ring in accent color
- clear error border and inline error text
- real labels

### Action buttons

Three button levels:

- primary: accent filled
- secondary: subtle dark surface
- destructive: red outlined / emphasized

### Profile actions

The profile management row becomes a compact operational toolbar rather than a cluster of default buttons.

### Review / run behavior

- review summary remains easy to reach
- validation errors link to the affected section
- run action remains accessible without hunting through the full page

## Results redesign

Keep the current functionality and structure, but make hierarchy explicit.

### Three visual layers

1. **Experiment controls + totals**
2. **Active workers / checkpoint progress**
3. **Completed result grid**

These layers must be visually distinct so progress and finished results do not blend together.

### Control semantics

- Pause: secondary with amber accent
- Resume: primary accent
- Stop after current: amber outlined
- Stop now: red destructive and visually separated

### Progress area

- real visual progress bars
- checkpoint cards with better grouping and spacing
- subtle live indicator for active polling/monitoring

### Result card density

Visible on card only:

- thumbnail
- status
- prompt truncated to two lines
- seed
- model short name
- runtime
- attempt badge

All deeper metadata belongs in the details drawer or drill-down, not on the card face.

### Comparison section

Keep current A/B logic and structure.
Only align spacing, heading, and action styling with the rest of the suite.

## History redesign

History becomes a compact operational run list.

Each row should show:

- thumbnail or type icon
- short run ID/name
- kind
- status dot + status label
- date/time
- duration
- model/profile short label

Rows should feel like selectable records instead of plain stacked divs.
On narrower widths, metadata may stack vertically while keeping the row stable.

## Settings redesign

Do not deeply restyle the embedded legacy settings panel in this pass.
Only improve the wrapper:

- stronger left navigation styling
- active section indicator
- polished fallback buttons
- spacing that visually integrates the legacy content into the unified shell

## Responsive behavior

The primary target is laptop-sized ComfyUI usage, especially **1280×720**.

Rules:

- dashboard cards: 3 columns wide / 2 columns medium / 1 column narrow
- result grid uses responsive minimum card width
- setup rail compacts or scrolls horizontally on narrower layouts
- settings left nav may collapse into dropdown/compact mode when needed
- header utility actions may collapse
- no horizontal overflow at 1280×720

## Accessibility requirements

- visible keyboard focus
- tabs keyboard navigable
- real labels on controls
- semantic statuses use text plus color/dot, never color alone
- useful contrast at small sizes
- reduced-motion respected
- field errors associated with fields

## Shell markup rule

Do not change registration, lifecycle, routing, or state ownership in `web/modal-testing.js`.
Limited markup and class-hook changes are allowed for:

- header status area
- scroll regions
- tab wrappers
- responsive controls
- status badges

## File scope

### Must redesign

- `web/testing-styles.js`
- `web/testing-dashboard.js`
- `web/testing-setup.js`
- `web/testing-history.js`

### Polish pass

- `web/testing-results.js`
- `web/testing-settings.js`

### Avoid in this pass

- `web/modal-testing.js` except for limited markup hooks
- `web/modal-settings.js` for deep visual restyling
- `web/testing-ab-slider.js` for interaction-heavy restyling
- `web/testing-api.js`

## Pre-implementation verification

Before styling, confirm:

- `testing-dashboard.js` exists and is mounted
- `testing-history.js` exists and is mounted
- current navigation reaches each redesigned renderer
- new classes target real markup, not dead code

## Success criteria

- modal visibly differs from current scaffolding on first open
- no browser-default buttons, inputs, selects, or textareas remain in redesigned areas
- all redesigned screens use shared tokens
- healthy dashboard makes **New Experiment** the primary action
- blocked dashboard makes deployment/warmup the hero
- setup rail shows 8 real steps
- results layers are visually distinct
- result grid uses consistent card dimensions
- history rows are stable and aligned
- settings wrapper looks integrated
- no horizontal overflow at 1280×720
- keyboard focus is visible
- semantic statuses include text, not color alone
- existing interactions still work
- before/after screenshots are captured for each affected tab
