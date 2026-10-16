# Core-part comparison vs references (2026-10-16)

Compared zoomed live renders against the extraction docs to catch doc gaps
before the full proof suite.

## Part 1 — Nav drawer (`review/shell.png`) vs Mix M9

| Mix M9 evidence | Ours | Verdict |
|---|---|---|
| ~330px slide-over, wordmark+X header | 330px, brand+X header | match |
| Nav rows icon+label+hint, 48–54px, wash hover | same, 48px, hints on secondary | match |
| Micro-section label (LOCAL CONTROLS) | STUDIO eyebrow | match, used sparingly per law 5 |
| Backdrop rgba(0,0,0,.72) | rgba(0,0,0,.6) | close; keep .6 (frame already dims) |
| Drawer adjacent to workspace | initial fixed-viewport build floated over ComfyUI chrome | FIXED → absolute in-frame |

Doc gap found + fixed: extraction never stated the host-frame docking constraint
(overlay z-60 sits under ComfyUI's floating clusters). Draft now records it
under Wizard; same law applies to drawer (absolute) — drawer CSS comment covers it.

## Part 2 — Wizard inspector (`review/wizard-sidebar.png`,
`review/wizard-binding-graph.png`) vs Mix M5 / Mooshie O1 / Stimma S6

| Reference | Ours | Verdict |
|---|---|---|
| Mix M5: 360px inspector, compact header, scroll body, bottom bar | exact composition, thin progress hairline | match |
| Mix: resizable panels (260–520 drag separators) | fixed 360px | GAP accepted → draft corrected (drag separators = follow-up; CSS resize misbehaves on fixed right-docked panels) |
| Mooshie O1: progressive disclosure, value-first summaries | one active step renders; completed steps vanish, no summary rows | GAP accepted for now (semantics preserved; summary rows = enhancement, needs store-neutral presentation only) |
| Stimma S6: hairline rows, one control right | binding rows + footer follow it | match |
| Hard req: graph visible + interactive, no blocking modal | binding banner live, host graph interactive, Esc cancels cleanly | PROVEN live (screenshot + DOM check) |
| ComfyUI floating cluster covers fixed top:104px offset | header fully visible in binding shot | match with documented host-chrome constraint |

## Part 3 — Workflows rail (`review/workflows.png`) vs Mix M8 / Stimma S2

Rail (search 34px + seg + dense 2-line rows + wash/inset selection) vs Mix
library rail: match. Detail stays library/detail/editor — no invented run stage
per correction #3. Sentence-case sections; micro-label used nowhere in this
view (correct per law 5).

## Test evidence (gate surfaces)
- `vue-tsc -b`: clean. `vitest run`: 69/69.
- `studio-fake-wizard-refresh`: 2/2 (after teleport fix; first run caught a REAL
  bug — ComfyUI canvas chrome at z-999/1200 covered the in-overlay inspector
  and stole Playwright clicks. Inspector now teleports to body at z-2000 with
  an in-root `data-state=open` marker preserving the host Esc protocol).
- `studio-fake-models`: 6/6 (in the combined run: 7 pass total with models).
- `studio-fake-wizard-remote-models` "remote nonzero size…": FAILS identically
  on pristine `e51c3b7a` worktree → PRE-EXISTING, legacy-harness path, no
  shared files with this change. Not mine to fix in this lane.

## Doc corrections applied
- Draft: accent `#4f7cff` family (was `#3b82f6`); resize follow-up; top-104px
  host-chrome constraint; split-button hero CTA reserved for Playground;
  sentence-case default with sparse micro-labels; wizard step order frozen.
- No md change needed for M2/M6/M4 beyond the user's corrections (done).
