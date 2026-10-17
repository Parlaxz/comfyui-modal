# Visual Verdict — Phase 4.5 Parity Pass (PASS)

Prior verdicts stand; this pass added behavior with presentation discipline.
New/changed surfaces re-verified on the final build in live ComfyUI:

- `normal-studio-workflows-fullscreen.png` — bounded detail (max-w-4xl),
  dep rows with local action groups (source/URL + Install/Queue + Find),
  truthful summary, manifest import entry. No 1500px eye travel. PASS.
- `workflows-library.png` — searchable browsable inventory (92 models,
  35 nodes), type filter, expandable provenance, note editor, used-by line.
  PASS.
- `settings-in-studio.png` — Preferences sheet over dimmed Studio; golden
  GPU order A/B with active radio rendered from live profiles. PASS.
- Wizard inspector (roles + gate) covered by `wizard-binding.png` grammar;
  role rows verified live (capture → bind → View → centered on graph).
- History/manage shots unchanged since last PASS (no visual changes there
  this pass except dep-adjacent rows, re-verified in workflows shot).

Audits hold: borders name peers; spacing rhythm kept; selection wash-only;
no ids/arch prose on default surfaces; single Studio close; fullscreen
ownership intact (re-verified via parking spec 2/2 on final build).

## Acceptance set (all current)

- `normal-studio-history-fullscreen.png` — zero ComfyUI chrome: no tabs, rail,
  toolbars, toasts, badges, zoom controls. Standalone gallery app. PASS.
- `normal-studio-workflows-fullscreen.png` — same ownership; human rows,
  surfaced metadata editor, truthful mapping summary. PASS.
- `nav-drawer-fullscreen.png` — in-frame drawer, wash selection, quiet X. PASS.
- `settings-in-studio.png` — Studio context behind; integrated rail (no cage),
  flat 14px rows, no arch copy. PASS.
- `manage-workspaces-fullscreen.png` — selected wash + Active signal, no
  ledger walls, quiet seg. PASS.
- `manage-models-fullscreen.png` — dense rows keep faint peer hairlines only;
  calm ledger, no cards. PASS.
- `wizard-graph-clean.png` (`wizard-graph-mode.png`) — GRAPH PRIMARY: real
  nodes/wires across the viewport, no Studio editor, no setup slab, docked
  inspector. PASS.
- `wizard-binding-clean.png` (`wizard-binding.png`) — live binding state +
  host banner + graph; Esc restores (DOM-verified). PASS.
- `wizard-graph-narrow-clean.png` (`wizard-graph-mode-narrow.png`, ~1075px) —
  no clipping; inspector readable; graph usable. PASS (with noted host-chrome
  overlap at narrow widths, which is ComfyUI's own chrome, not ours).
- `studio-closed-host-restored.png` — attribute removed, canvas/toasts/badges
  back, scroll lock off. PASS.

## Audit results

- Host: every non-Studio element in prior shots classified; normal mode parks
  canvas+chrome+toasts+badges via reversible CSS; graph mode returns canvas
  only. Esc layer fixed (frame no longer self-blocks). Cycles verified.
- Borders: each remaining line names two peers (control edges, dense-row
  hairlines, drawer/inspector separation, rail-free settings).
- Padding: 24/32 gutters, 16px wizard body, 14px settings rows, 12px manage
  rows, 20–24px section gaps; semantic gaps exceed internal gaps.
- Information: ids/hashes/"No folder"/raw JSON/arch prose gone from defaults
  (raw mapping toggle, testids, inspector layers retain them); deps
  missing-first; "Optional" replaces "nonessential".
- Selection: wash + bright text throughout; accent ring on media only;
  understandable with blue removed.
- Reference check: Mix (workspace modes are real modes; content over chrome;
  few permanent borders) ✓ · Stimma (separator law, one elevation step,
  hairline-or-fill, selection≠action) ✓ · Mooshie (task concepts, obvious
  next action, wiring hidden) ✓.
