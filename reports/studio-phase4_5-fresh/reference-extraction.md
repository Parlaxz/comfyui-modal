# Phase 4.5 Fresh — Reference Extraction

Date: 2026-10-16. Studied live in-browser by the implementing agent (no subagents).
Sources: Mix Studio (live DOM + computed styles + screenshots, served locally from
GitHub HEAD), Stimma `frontend/DESIGN.md` (Atelier v3), Mooshie site + app screenshot.

All pixel values are measured computed styles at 1920×897 (Mix Studio) unless noted.

---

## M1 — Mix Studio app shell

- Source: Mix Studio live `index.html`, top banner.
- Evidence: banner `1920×58`, bg near-black `rgba(0,0,0,.92)`, padding `9px 20px`.
  Left: logo + wordmark. Right: status dot + hamburger icon-btn.
- ADOPT → Studio shell topbar: 56–58px, near-black true-neutral bar, hairline
  bottom rule, brand left, ops (queue/status/menu) right.
- Consequence: Studio topbar becomes a fixed 56px chrome strip, not a card.

## M2 — Mix Studio tab grammar → SUPERSEDED by drawer decision

- Source: Mix Studio center tab bar (Create / Edit / Library pills).
- Evidence: (measured) three equal tabs `387×38`, pill track, active ink /
  inactive muted. Pattern is sound but Ahmed prefers Mix's DRAWER navigation:
  Studio drops the top tab strip entirely; Playground + History stay primary,
  everything else moves into the brand-button side drawer (see M9).
- ADOPT the pill-track pattern only for IN-PAGE segmented sub-navigation
  (history filters, workflow sub-views), not top-level chrome.
- Consequence: StudioApp loses its tab strip; drawer owns navigation.

## M3 — Mix Studio mode segmented control (Image / Region / Video)

- Source: left panel top segmented switch.
- Evidence: pill track `999px`, padding `4px`, `rgba(7,9,13,.84)`. Options `107×30`,
  12.5px/800, active ink on filled wash, inactive muted. Gap 7px with icon+label.
- ADOPT → Studio filter/sub-mode segmented controls (history filters, workflow
  sub-views, wizard step modes where segmented).
- Consequence: one segmented pattern everywhere; kill bespoke toggle-button rows.

## M4 — Mix Studio section micro-labels

- Source: left panel + drawer headings.
- Evidence: `INPUTS`, `PROMPT`, `RESOLUTION`, `LORAS`, `LOCAL CONTROLS` —
  11px/800, letter-spacing `1.65px`, uppercase, muted `#8e99b7` / `#68728d`.
  Drawer variant 9px/900, ls `1.08px`.
- ADAPT → Studio micro-label, USED SPARINGLY: 11px/700, uppercase, ls `0.12em`,
  true-neutral muted — only for tiny eyebrows over compact groups (rails, drawer
  sections). Default section headings stay sentence-case 14px/600. Overuse is a
  vibe-coded pro-tool smell.
- Consequence: single `.st-label` class with a documented "sparingly" rule.

## M5 — Mix Studio left inputs panel (the inspector prototype)

- Source: Create-mode left panel.
- Evidence: width 360px (resizable 260–520 via drag separator, double-click reset),
  padding `16px 14px`, gap 14px, sections stacked: model card → prompt field →
  resolution row → turbo switch row → upscale row → loras → advanced disclosure.
  Rows are quiet: label-left/value-right, hairline separation, no boxes except the
  model card (24px radius panel) and the prompt textarea (15px radius, 14px text,
  `15px` padding).
- ADOPT → Setup Workflow wizard inspector: 360px docked right panel, same stacked
  section grammar, compact header, scrollable body, persistent bottom action bar.
- Consequence: wizard is a right inspector, never a modal; sections use label rows
  + one hero control, not nested cards.

## M6 — Mix Studio Generate button (HERO-run-CTA ONLY)

- Source: bottom of stage, `1154×53`.
- Evidence: pill `999px`, 15.5px/900, ls `0.62px`, double-background gradient-border
  technique, 2px transparent border. Full stage width, sticky bottom.
- ADAPT → reserved for the ONE true run CTA (Playground Generate, built as a SPLIT
  button: main segment + dropdown arrow for queue/experiment). NEVER generalized:
  Continue/Save/Install/Import stay compact. Accent = custom blue `#4F7CFF`
  territory (NOT Tailwind `#3b82f6`); gradients restrained, never environmental.
- Consequence: exactly one hero CTA per product surface; no generic blue-glow
  language on ordinary buttons.

## M7 — Mix Studio stage well (focused result)

- Source: center generation stage.
- Evidence: large rounded well (radius-md 18px), near-black matte fill, centered
  placeholder glyph + muted caption. Header row above: 24px/700 title left,
  status pill + icon actions right. Caption line below well, then Generate bar.
- ADOPT → Workflows selected-workflow workspace: title row + status, big content
  well on matte, footer action bar. History viewer: large media + compact inspector.
- Consequence: media/content sits on matte wells, chrome floats above/below, never
  boxed side-by-side in cards.

## M8 — Mix Studio right Library rail (dense-row grammar)

- Source: `PREVIOUS GENERATIONS` panel, 360px (240–440 resizable).
- Evidence: search field (42px, icon left), filter pill row (All/Images/Videos +
  icon toggles), folder select row, then dense media rows/tiles. Panel is flat —
  separation by spacing + hairlines, no cards.
- ADOPT → Studio workflows library list + history queue rail: 300–360px right rail,
  search + segmented filter + dense rows, selected row = accent inset bar.
- Consequence: workflows master list and history strip become rails, not card grids.

## M9 — Mix Studio side drawer (navigation + local controls)

- Source: hamburger drawer, z-index 90, backdrop `rgba(0,0,0,.72)`.
- Evidence: left slide-over ≈330px, wordmark + X header, nav items
  (Create/Edit/Library, active = filled wash pill), then `LOCAL CONTROLS` section:
  rows = icon + semibold label + muted hint right (`54px` tall, `18px` radius hover).
- ADOPT → Studio drawer/menu (if needed) + Manage Modal ops rows: icon + label +
  muted hint, 48–54px rows, wash hover.
- Consequence: Manage Modal Workspaces/Deployment/Models/Nodes become dense ops
  rows with status dots, not cards.

## M10 — Mix Studio Preferences sheet (settings grammar)

- Source: Preferences dialog (~860px centered sheet).
- Evidence: left icon rail (87×58 items, 11px/800 labels, active = blue-wash
  gradient + 1px blue border + 14px radius), right pane with 20px/700 section title
  + muted subtitle, hairline-separated setting rows (15px semibold title + 12px
  muted desc left, single control right), boxed groups only for special clusters
  (slider group), top search field.
- ADAPT → Studio Settings: left-category rail + main pane, hairline setting rows,
  single control right. (Rail active state uses OUR blue accent wash, neutral bg.)
- Consequence: Settings rewrite after gate uses this exact composition.

## M11 — Mix Studio icon-btn + focus

- Source: `style.css` + live.
- Evidence: `.icon-btn` 38×38, radius 12px, 1px `line` border, `panel-soft` bg,
  `:active scale(.94)`. Global `:focus-visible` = 2px `rgba(116,147,255,.9)` ring +
  3px offset. Motion ease `cubic-bezier(.2,.8,.2,1)`, 160–260ms.
- ADOPT → Studio icon buttons 34–38px + same focus ring (blue) + same ease.
- Consequence: shared control CSS; no per-component focus inventions.

## M12 — Mix Studio queue popover (operations pattern)

- Source: Queue button → popover.
- Evidence: small centered popover (~600px), title + X header, list zone, footer
  action row (ghost `Clear history` left, red-ghost `Hard reset` right). No heavy
  chrome.
- ADOPT → Studio run/queue popovers: compact sheet, footer action row, danger as
  red-ghost text button.
- Consequence: run controller UI stays compact; no full-page queue takeovers.

## M13 — Mix Studio dark tokens (luminance source, NOT hue source)

- Source: `:root` in style.css.
- Evidence: `--page-bg:#000; --ink:#f6f8ff; --ink-soft:#c9d2e7; --muted:#8e99b7;
  --muted-2:#68728d; --panel:rgba(7,9,13,.78); --panel-strong:rgba(10,12,18,.96);
  --panel-soft:rgba(17,21,30,.68); --line:rgba(226,232,255,.08);
  --line-strong:rgba(226,232,255,.2); radii 12/18/24.`
- ADAPT → Studio tokens: same LUMINANCE architecture (page near-black, 2–3 raised
  neutral steps, 8% hairlines) but TRUE-NEUTRAL hues (no blue-tinted ink/lines).
  Accent = clean blue (Mix's `#4257ff` family is the right territory), used sparingly.
- REJECT: Mix's blue-tinted whites (`#f6f8ff`, `226,232,255` lines) and its
  blue→violet gradient accent as environmental wash. Our surfaces stay neutral;
  blue is action-only.
- Consequence: fresh token table in design-language-draft.md; 70/20/10 balance.

---

## S1 — Stimma separator law (20% weight: discipline)

- Source: Stimma `frontend/DESIGN.md` §1.3a.
- Law: a hairline may only exist BETWEEN two peers. Never above first / below last
  (use `divide-y`-style stacking). Children indent, never fenced. One boundary per
  edge (rule OR box OR gutter). Headings are labels, never underlined. Tall content
  separates by whitespace.
- ADOPT verbatim → Studio lists, wizard sections, settings rows, manage rows.
- Consequence: audit every hairline in implementation; each must name its two peers.

## S2 — Stimma depth budget

- Source: DESIGN.md §1.4. Background + at most ONE raised container per region.
  Inside: hairlines + whitespace, never another box. Shadows only on true overlays.
  Hairline OR fill, never both (inputs fill-only; panels hairline-only).
- ADOPT verbatim → kills both failed extremes (card soup AND fieldset soup).
- Consequence: workflows workspace = regions separated by spacing + one hairline;
  selected workflow pane gets the ONE raised step per region.

## S3 — Stimma radius roles

- Source: DESIGN.md §1.3. Media 0–2px, controls 6px, containers 8px, circular full.
  Radius signals what a thing IS.
- ADAPT → Studio: media 4px, controls 8px, containers 12px, pills full.
  (Slightly larger than Stimma to match Mix Studio's softer 12/18/24 rhythm, but
  the ROLE discipline is Stimma's.)
- Consequence: tokenized radii; banned: card-soup large radii on rows, square
  buttons.

## S4 — Stimma type voices

- Source: DESIGN.md §1.5. UI sans default (`text-xs` dense, `text-sm` primary,
  semibold view titles); FACTS = mono tabular (ids, dims, counts, durations);
  ONE section micro-label variant (sentence-case there; ours uppercase 11px per M4);
  `font-bold` banned outside display.
- ADOPT → Studio: 12px dense / 13–14px primary / 20px semibold view titles;
  all numeric/factual metadata in mono; semibold max 600–700, no black weights
  except the primary CTA.
- Consequence: workflow meta, history meta, run stats all mono; kills scattered
  type sizes.

## S5 — Stimma selection vs action split

- Source: DESIGN.md §§1.1/1.8. Selection ≠ action: indigo selection ring/tint,
  teal action accent, magenta live. Focus-visible rings keyboard-only.
- ADAPT → Studio: selection = blue-tinted wash + inset accent bar (single hue
  family as action, but DIFFERENT treatment: wash+bar vs solid); running/live =
  blue pulse dot; danger = red. Focus ring blue, `:focus-visible` only.
- Consequence: selected workflow row / history item / bound target share one
  selected-state pattern, distinct from buttons.

## S6 — Stimma settings + list-row grammar

- Source: DESIGN.md §§3.2 + canonical patterns. Setting = hairline row,
  label+desc left, ONE control right, `py-2.5`. List row = full-bleed hover tint,
  hover-revealed controls. KeyValue facts: muted label left, mono value right.
- ADOPT → Studio settings rows, manage rows, workflow detail facts, wizard review.
- Consequence: no bordered field tiles for read-only facts; no stacked outline buttons.

## S7 — Stimma ToolView flagship composition (adapted)

- Source: DESIGN.md §3.3. Controls column · hero center · queue rail right.
  Exactly ONE solid-accent button per screen. Quiet monochrome control column so
  run bar + results carry energy. Prompt = fill-only field. Params = editable
  label-left/mono-value-right rows.
- ADAPT → Workflows workspace: library rail (left) · selected-workflow hero
  (center) · inspector/bindings rail (right, contextual). One primary per surface.
- Consequence: the three-region composition is the Studio standard layout.

---

## O1 — Mooshie progressive disclosure (10% weight: clarity)

- Source: mooshieui.com + app screenshot (left icon rail, controls panel, central
  image hero, RIGHT inspector with collapsible Model/VAE/LoRA/Sampler sections).
- Pattern: narrow icon rail → panel → hero → inspector; inspector sections are
  collapsible rows (label + chevron), each row label-left/control-right with
  sliders + numeric mono readouts; advanced settings behind disclosures; plain
  next-action language ("Apply", "Add LoRA").
- ADOPT → Wizard inspector sections collapse progressively (feature → controls →
  bindings → review shown step by step, earlier steps collapse to value-first
  summary rows); empty states use plain guided language with one obvious action.
- REJECT: Mooshie must not override Mix spatial grammar (denser 13–14px type,
  tighter 8–12px gaps, rail widths from M5/M8, not Mooshie's roomier marketing UI).
- Consequence: wizard steps show ONE active section expanded; completed steps read
  as value rows (Stimma S6 grammar).

---

## Rejected outright (do not carry into Studio)

- R1: Blue/zinc environmental tint (Mix's blue-tinged ink + lines; any slate soup).
- R2: Gradient-wash-everywhere (Mix model cards / rail active gradients → ours is a
  flat neutral wash + 2px blue inset bar for selection).
- R3: Centered wizard modal (contradicts the hard requirement; M5 is the pattern).
- R4: Card-soup dashboards and fieldset-soup forms (both failed extremes; S2 kills).
- R5: ALL-CAPS body text, bold-everywhere titles, invented accent hues per surface.
