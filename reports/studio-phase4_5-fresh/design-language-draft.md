# Studio Visual Language — Fresh Draft (Phase 4.5)

Derived 2026-10-16 from Mix Studio (spatial/interaction), Stimma Atelier v3
(discipline), Mooshie (clarity). True-neutral foundation, blue accent only.

## Tokens

```css
/* page + elevation: true neutrals, warm-free */
--st-page:    #0b0b0c;  /* app base, near-black neutral */
--st-surface: #131314;  /* raised one step: rails, wells */
--st-raised:  #1b1b1d;  /* cards, popovers, selected wash base */
--st-hover:   #222224;  /* hover fill */
--st-matte:   #060607;  /* media matte, darker than page */

/* text */
--st-ink:     #f2f2f3;
--st-ink-2:   #c6c6c9;
--st-muted:   #8f8f96;
--st-faint:   #626268;

/* lines: neutral white @ alpha, never blue-tinted */
--st-line:    rgba(255,255,255,.08);
--st-line-2:  rgba(255,255,255,.16);

/* accent: custom clean blue, action-only. NOT Tailwind blue-500.
   Tuned from Mix #4257FF territory toward #4F7CFF; verify rendered. */
--st-accent:        #4f7cff;
--st-accent-hover:  #6a90ff;
--st-accent-wash:   rgba(79,124,255,.14);
--st-accent-line:   rgba(79,124,255,.45);

/* status */
--st-ok:   #34c98e;
--st-warn: #d9a13b;
--st-bad:  #e0655a;
--st-live: #3b82f6;   /* running = accent pulse dot */

/* shape */
--st-r-media: 4px;
--st-r-ctl:   8px;
--st-r-box:  12px;
--st-r-pill: 999px;

/* type */
--st-t-title: 20px/1.3 600 -.01em;   /* view titles */
--st-t-sect:  14px/1.4 600;          /* section heads */
--st-t-obj:   14px/1.4 500;          /* row/object names */
--st-t-body:  13px/1.5 400;          /* primary content */
--st-t-dense: 12px/1.45 400;         /* dense rows */
--st-t-label: 11px/1.4 700 .12em uppercase muted;  /* MICRO-label only: tiny
   eyebrows over compact groups (rails, drawer sections). NEVER the default
   section heading — sections use sentence-case --st-t-sect. Overuse reads
   vibe-coded. */
--st-t-fact:  12px mono tabular muted;             /* facts: ids, dims, counts */

/* chrome */
--st-topbar: 56px;
--st-rail-l: 300px;   /* library/master rail */
--st-rail-r: 340px;   /* inspector rail */
--st-row:    40px;    /* settings/manage row min-height */
--st-ctl:    34px;    /* input/button height */
--st-ease: cubic-bezier(.2,.8,.2,1);
```

Balance: ~70% `--st-page`, ~20% surface/raised elevation, ~10% blue/status.

## Laws (from Stimma, binding)

1. Separator law: a hairline exists only BETWEEN two peers. Stack lists with
   top-rules on items 2..n; never a trailing rule; children indent, never fenced.
2. Depth budget: base + ONE raised step per region. Inside: hairlines +
   whitespace, never a nested box. Shadows on overlays only. Hairline OR fill.
3. Radius roles: media 4 / controls 8 / containers 12 / pills full. Never mixed.
4. Facts are mono: ids, dims, seeds, counts, durations, sizes, timestamps.
5. Selection ≠ action: selected row = `--st-raised` fill + 2px accent inset bar
   left; primary button = solid accent pill. Focus ring 2px accent, `:focus-visible`.
6. Exactly one primary action per surface. Danger = red-ghost text button.
7. No `font-black` outside the primary CTA; titles 600.

## Compositions

### Shell — drawer navigation, no top tab strip
56px topbar: brand button left (opens nav drawer); current-view title center-left;
ops right (run status, queue, menu icon-btns 36px). Hairline below. NO top tabs:
Playground + History are the primary destinations (first drawer items, and the two
views reachable without the drawer); Workflows / Manage Modal / Settings live in
the drawer under a second group, Mix-style (icon + label + muted hint rows,
48–54px, wash hover). Drawer ≈330px, backdrop rgba(0,0,0,.72), z below modals.
Content fills below; fullscreen app; no page-level cards.

### Workflows — library / detail / editor (NOT a generation stage)
- Left 300px rail: search (34px) + segmented filter + dense workflow rows
  (name 14/500 + mono meta line, hairline-separated, selected = wash + inset bar)
  + ghost "+ New workflow" as LAST child inside the divide.
- Center detail: title row (20px/600 + status + actions incl. Setup workflow) →
  editor sections on flat background separated by hairlines (metadata fields,
  mapping, dependencies, portability, presets, guidance). NO hero well, NO footer
  run bar, NO invented generation behavior. Spatial discipline only.
- Right 340px rail (contextual): bindings summary / inspector when selection
  warrants; otherwise detail uses full width.
- Step order and wizard semantics (Feature → Bindings → Controls → Review) are
  engine contract and NEVER change for presentation reasons.

### Wizard = right inspector (360px; drag-resize is a follow-up)
- Slides/docks right of the live ComfyUI graph; graph stays visible + interactive.
- Fixed 360px for now (Mix panels resize via drag separators; a native CSS resize
  handle misbehaves on a right-docked fixed panel, so proper separators ship later).
- Viewport-fixed, docked to the host frame's right edge; top starts below
  ComfyUI's own floating top-right cluster (host-chrome constraint, ~100px).
- Header (compact): step x of n + title + close. Progress = thin accent hairline,
  not chunky dots.
- Body scroll: ONE active section expanded (feature → controls → bindings →
  review); completed steps collapse to value-first rows (label left, mono value
  right, accent value when modified).
- Binding state: instruction line (plain language, one verb) + target chip
  (mono `node.widget` when bound, dashed empty when awaiting) + bound rows use
  selected-state pattern. Graph target highlight is host-driven; sidebar reflects.
- Footer: persistent bar, ghost Back + compact primary Continue/Finish, hairline
  above. The full-width gradient-border hero pill is reserved for the ONE true run
  CTA (Playground Generate, as a split button with queue/experiment dropdown);
  wizard/ordinary actions (Save, Install, Import, Next) stay compact.

### History (after gate)
Media-first: filter pill row + search + thumbnail-size slider (Mix pattern);
tiles on matte, 2px gutters, 4px radius, selected = accent ring; viewer = large
media well + 300px compact inspector (facts KV, actions). Compare + picker reuse
viewer grammar.

### Manage Modal (after gate)
Ops console: dense 48px rows (status dot + name + mono detail + verb button),
hairline-separated, grouped under micro-labels. No cards.

### Playground run CTA (after gate)
The ONE hero action: full-width pill, split button — main Generate segment +
dropdown arrow segment opening queue/experiment options. Gradient-border
treatment reserved for THIS control only; gradients used sparingly everywhere
else (never as environmental wash).

## Phase 5 visual contract (DOCUMENT ONLY — do not implement yet)

- Bottom Generate action inspired by Mix Studio (full-width hero pill).
- Split Generate button: main segment = normal generation; dropdown segment =
  Queue / Experiment choices.
- Resolution control treatment inspired by Mix (quiet value-first row opening
  a compact picker, not a wall of inputs).
- Playground uses this same visual language; no duplicate run paths.

### Settings (after gate) — a modal, not a page of tabs
The ONE hero action: full-width pill, split button — main Generate segment +
dropdown arrow segment opening queue/experiment options. Gradient-border
treatment reserved for THIS control only; gradients used sparingly everywhere
else (never as environmental wash).
Centered sheet (~860px) with left icon rail (88px items, active = accent wash +
1px accent border) + main pane (max ~720px): title + subtitle, hairline setting
rows (label+desc left, ONE control right). Danger zone last, red-ghost actions,
confirm in dialog.
