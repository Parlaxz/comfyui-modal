# Studio Visual Language (Phase 4.5)

Single authority for how Studio Vue looks. Tokens live in
`frontend/src/studio.css`; these are the laws behind them.

## Philosophy

Quiet workspace, not a showcase. Studio is embedded inside ComfyUI: chrome
recedes, content leads. Structure comes from type and whitespace separated
by hairlines — never from stacked panels, fills, or glow.

References: Mix Studio `2705793` (ADOPT 70% — workspace-first control/result
split, persistent rail, gallery as surface), Stimma `46f178b`
`frontend/DESIGN.md` (ADOPT — one raised container per region, hairline
discipline, matte media, radius roles), Mooshie `v2.3.20` (ADAPT 20% —
guided setup steps, presets as image-free configs). Neon/gradient
heroes and card soup are rejected outright.

## Palette

| Token | Value | Use |
|---|---|---|
| `--cmst-bg` | `#090C11` | App background |
| `--cmst-surface` | `#0F141B` | Region container |
| `--cmst-raised` | `#151B24` | Selected / popped content |
| `--cmst-hover` | `#1A222D` | Hover wash only |
| `--cmst-border` | `rgba(178,189,203,.16)` | Hairlines, control borders |
| `--cmst-fg` | `#F3F6FA` | Primary text |
| `--cmst-secondary-text` | `#B2BDCB` | Secondary text |
| `--cmst-muted` | `#7F8B9B` | Meta, placeholders, quiet icons |
| `--cmst-primary` / hover | `#4F7CFF` / `#638CFF` | Accent: active underline, primary action, focus |
| `--cmst-matte` | `#07090D` | Media wells only |
| `--cmst-ok / -warn / -danger` | `#4CA98A / #C99A4A / #D96A5F` | Status dots and badges, desaturated |

No zinc/slate, no raw hex in templates — tokens or `cmst:` utilities only.

## Type

View title 20 semibold (one per page) · section 14–15 semibold · object 14
medium · body 13 · meta 11–12 mono muted. Scoped helpers: `cmst-type-view`,
`cmst-type-section`, `cmst-type-object`, `cmst-type-body`, `cmst-type-meta`.

## Spacing

Page padding 20–24 (`studioPageClass`) · section gaps 8–12 · object rows
30–34 min-height · buttons 34–36 height (`.cmst-field` is 34).

## Depth

Flat + hairlines. One raised container per region; inside it, sections split
with 1px `cmst-border` dividers (`.cmst-hairline`). The single elevation
token (`--cmst-shadow-overlay`) belongs to overlays (dialogs, menus) only.
`StudioCard` carries no shadow.

## Separators

Hairlines never double: a bordered container holds borderless rows divided
by top-hairlines; sibling sections divide with a top border. No bordered
chips inside bordered boxes.

## Radius

Media 0–2 (`--cmst-radius-media`) · controls 6 (`--cmst-radius-control`,
fields, buttons, badges) · containers 8 (`--cmst-radius-container`, cards,
dialogs). No pills.

## Action hierarchy

One primary per region. Shell: none (nav is quiet text + 2px accent
underline; close is a ghost icon). The shell header reserves right-side room
(`pr-14`) for the host-owned preview close, which floats at the frame
top-right — the in-app close must never sit under it. Workflows detail: Setup workflow.
Wizard: Next on steps 1–3, Save mapping on Review. Everything else is
secondary / outline / ghost, descending with consequence (Delete is outline
inside overflow, ghost in rows).

## Media

Thumbnails and viewer wells sit on `--cmst-matte` with radius ≤ 2. Media
never floats on accent, gradient, or glow. History cards carry media to the
edge on a matte well (`.cmst-media-well`); title + mono meta + compact
actions sit below, contextual actions (favorite, select) hover-overlay the
well. Compare A/B is two matte wells side by side with mono captions —
never bordered boxes around the images.

## Status

State is a dot + words, never a filled pill: ok/warn/danger dots for
runnable and dependency states; Bound (ok tint) / Pending (warn tint) text
badges for wizard bindings — e.g. binding the Steps control on a KSampler
reads back as a green-dot "Bound" row.

 ## Motion

120ms micro (hover/fade), 160ms standard (dialogs, tabs). Underline and
background transitions only; nothing slides. `prefers-reduced-motion`
collapses all durations. Focus is always visible: 2px accent outline.

Opening the setup wizard hands graph interaction back to ComfyUI (Studio
modal drops `aria-modal`, background leaves `inert`); EVERY wizard exit —
explicit close AND successful save — restores the inert modal. The save path
closes inside the store, so the page re-applies the restore after
`saveWizardMapping` resolves.

## Responsive

Shell header wraps; Workflows list/detail is one column under `lg`, rail +
surface at `280px + 1fr` above. Settings is category nav + pane
(`180px + 1fr` above `lg`, stacked below). History grid honors the
Interface column preference with `minmax(0,1fr)` columns so it never
overflows. Overlay dialogs cap at `42rem / 94vw`.

## Operations + settings rows

Backend workspaces are object rows (dot + name + mono state line, active
obvious); deployment readiness is dot + words with a thin progress track,
logs secondary on matte. Models/nodes are dense hairline rows
(`.cmst-data-row`), never bulleted pills. Settings rows align
label/description left with the control right (`.cmst-setting-row`,
stacked under 640px); resets are ghost/outline, destructive-tinted only
for reset-all.

## Anti-patterns

Gradient or neon heroes · card-in-card nesting · bright-fill active tabs ·
prototype copy or debug footers in chrome · invented control libraries (style
native inputs with `.cmst-field`) · status pills · shadows on static panels.
