# Phase 5 Playground — live evidence (isolated harness, real built bundle)

Harness: TEMP-only stub backend (`$env:TEMP\pg5-harness`, never committed)
serving this branch's `web/assets/studio` bundle plus deterministic
`/comfymodal/*` fixtures. No Modal/GPU work; assets are 1×1 PNGs.
Screenshots use the final built Vue bundle. No DevTools UI, no host chrome
(the harness has none by construction).

| File | Proves |
|---|---|
| `playground-default-wide.png` | Fullscreen composition: topbar selectors, mode/subtool rails, media matte workspace, inspector, hero Generate split |
| `playground-workflow-controls.png` | Inspector: image role, resolution pair, seed+random, numeric, toggle, enum, ordered prompt-first |
| `playground-generated-result.png` | Current-generation media + served-asset URL + Open-in-History |
| `playground-generate-split-menu.png` | Split intent menu: Generate / Queue / Experiment |
| `playground-experiment.png` | Experiment composer with axis values |
| `playground-history-picker.png` | Shared History picker over Studio (teleported, no crash) |
| `playground-source-image.png` | Source-image ownership via picker: canvas preview + control value + Clear |
| `playground-drawer.png` | Navigation drawer over the Playground workspace |
| `playground-medium-width.png` | 1075px: single-column workspace + inspector, no horizontal overflow (verified: scrollW == clientW) |

Committed regression spec (runs post-rebase against live ComfyUI):
`tests/browser/fake/studio-fake-vue-playground.spec.mjs` — not yet executed
because live ComfyUI currently serves the main-checkout bundle, not this
branch. Every assertion in it was validated manually through this harness.

Network truths observed live: frozen single-run POST to `/studio/run`
(prompt, workflow_id, `studio_playground_vue` source, settings-derived
modal_options); two-variant frozen POST to `/studio/run_batch`;
experiment POST only to `/studio/experiment-v2` with axes; cancel via
stop-now seam; references ride top-level `studio_references`, never inside
controls; draft + generation id survive reload; preset applies image-free.
