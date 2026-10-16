# Studio Visual Language (Phase 4.5 Fresh — Accepted)

Derived from Mix Studio (spatial/interaction grammar, measured live),
Stimma Atelier v3 (discipline laws), and Mooshie (clarity). Full provenance:
`reports/studio-phase4_5-fresh/reference-extraction.md`.

## Foundation: true neutrals, blue as action-only

Environmental surfaces are neutral near-blacks with NO blue/zinc tint.
Blue (`#4f7cff` family — never stock Tailwind `#3b82f6`) appears only on
primary actions, focus/selection accents, and status. ~70% base / ~20%
elevation / ~10% accent-status.

| Token | Value | Use |
|---|---|---|
| `--cmst-bg` | `#0b0b0c` | app base |
| `--cmst-surface` | `#131314` | rails, wells, drawer, inspector |
| `--cmst-raised` | `#1b1b1d` | cards, popovers, selected wash |
| `--cmst-hover` | `#222224` | hover fill |
| `--cmst-matte` | `#060607` | media matte (darker than page) |
| `--cmst-fg` / `-secondary-text` / `-muted` | `#f2f2f3` / `#c6c6c9` / `#8f8f96` | text ramp |
| `--cmst-border` | `rgba(255,255,255,.08)` | hairlines (neutral, never blue) |
| `--cmst-primary` / `-hover` | `#4f7cff` / `#6a90ff` | action accent only |
| `--cmst-ok` / `-warn` / `-danger` | `#34c98e` / `#d9a13b` / `#e0655a` | status |

Radii (role-disciplined): media 4px / controls 8px / containers 12px / pills full.
Type: 20px/600 view titles · 14–15px/600 sentence-case sections · 14px/500 object
names · 13px body · 12px dense · mono tabular facts. Micro-labels
(11px/700/uppercase/tracked) are SPARING eyebrows only — never default headings.

## Binding laws

1. **Separator law** — a hairline exists only BETWEEN two peers. No leading/
   trailing rules; children indent, never fenced; rule OR box OR gutter.
2. **Depth budget** — base + ONE raised step per region; hairlines + whitespace
   inside, never nested boxes; shadows on overlays only; hairline OR fill.
3. **Selection ≠ action** — selected = neutral wash + bright text (rows, nav,
   rail, segmented); accent ring only on media tiles. No blue edge/bar as a
   selection signal. Focus ring blue, `:focus-visible` only.
4. **One primary per surface.** The full-width gradient-border hero pill is
   reserved for the ONE true run CTA (Playground Generate, as a split button
   with queue/experiment dropdown). Continue/Save/Install/Import stay compact.
5. **Sentence-case hierarchy.** Uppercase tracked labels only for tiny eyebrows.
6. **Default border = none.** Controls, floating surfaces, dense-row hairlines,
   and focus/selection states earn their lines; sections/groups/headings never
   get boxes. Native button chrome is reset at the base.
7. **Task-relevant information only.** No ids/hashes, no "No folder", no raw
   JSON dumps, no store/server prose on default surfaces. Technical detail
   lives one disclosure down (raw toggles, inspectors, debug layers).
8. **Spacing rhythm** — 4/8/12/16/20/24/32 scale; group gaps visibly larger
   than in-group gaps; page 24–32px, wizard body 16px, settings rows 14px.

## Compositions

- **Shell** — 56px topbar (brand button, view title, ops); NO top tabs.
  Navigation lives in a 330px drawer: Playground + History primary, then a
  STUDIO group (Workflows, Manage Modal, Settings) with hint rows. Route
  changes and Escape close it; opening moves focus inside.
- **Workflows** — library rail (300px: search, segmented filter, human rows)
  + detail editor (spacing-separated sections, mapping summary, quiet dep
  rows). No generation stage, no run bar, no ids in the default surface.
- **Wizard = graph mode (task-mode transition).** Opening Setup Workflow hides
  the Workflows editor (slim setup strip + Exit remains); the ComfyUI graph
  becomes primary with the 360px inspector docked right. Feature → Bindings →
  Controls → Review order frozen. Never a modal: no backdrop, graph visible +
  interactive. Body-teleported above ComfyUI chrome (z-2000) with an in-root
  `data-state=open` marker preserving the host Esc protocol; top offset clears
  ComfyUI's floating cluster.
- **History** — media-first matte grid (2px gutters, no tile borders, human
  titles), inline tile-size slider, accent-ring selection, viewer = large
  media + compact inspector.
- **Manage Modal** — ops console: segmented tabs, dense status-dot rows
  (spacing-separated), mono facts, verb buttons.
- **Settings** — left rail (wash selection, no accent bar) + flat hairline
  setting rows (label+desc left, ONE control right, 14px rhythm), max-width
  pane. Close controls everywhere use the shared quiet 32px icon button.

## References (read before restyling)

- `reports/studio-phase4_5-fresh/reference-extraction.md` (ADOPT/ADAPT/REJECT)
- `reports/studio-phase4_5-fresh/review/` (verdict + product screenshots)
