# Phase 5 Playground — Old → Vue Parity Matrix (Playground only)

Oracle: `web/studio-playground*.js`, `web/studio-workflow-run.js`,
`web/studio-experiment-mode.js`, `web/studio-presets.js`,
`web/studio-output-preferences.js`, `web/studio-backend-api.js`.
Target owners: `frontend/src/api/playground.ts`, `frontend/src/stores/playground.ts`,
`PlaygroundView` + Playground-only components. Run controller semantics are
consumed, never reimplemented (frozen contracts §6).

Status legend: PARITY (exists in Vue already) · PORT (built this lane) ·
DIFFERENT (same behavior, new presentation) · DEFER (explicitly out of Phase 5) ·
PARKED (migration contract: Upscale).

| # | Old feature | Old owner / endpoint | Semantics / QoL | Vue target | Status |
|---|-------------|----------------------|-----------------|------------|--------|
| 1 | Workflow/version selection + run-context bundle | `studio-workflow-run.js selectWorkflow/loadRunContext` → `GET /studio/workflows/:id/run-context` | monotonic selection gen, stale-response discard, defaults from graph values verbatim | playgroundStore + api/playground.getRunContext | PORT |
| 2 | Mapped control rendering (order, label, group, defaults, enabled, semantic type) | control_schema from run-context | no coercion; 0/0.0/false/"" preserved; image + model-file roles exempt from enum gating | PlaygroundControls | PORT |
| 3 | Prompt primary input + draft persistence | control draft per preset/feature; `saveControlDraft/loadControlDraft` | draft survives reload; workflow switch clears incompatible values | playgroundStore.draft + persisted draft | PORT |
| 4 | Resolution / width-height / aspect presets | schema width/height roles + output prefs | Mix-compact control; no silent clamping; exact values editable | PlaygroundControls resolution group | PORT |
| 5 | Generate (single run) | `POST /studio/run` via `runStudioWorkflow` | **intent frozen at submit** (structuredClone); submitted source stashed for lineage; busy gate; cancel | playgroundStore.submitRun | PORT |
| 6 | Queue mode (collect → drain chunks via run_batch) | `_enqueueCurrentRun/_drainNextGroup` → `POST /studio/run_batch` variants | radio invariant vs experimentMode; same-workflow chunks; singleton fallback to single path | playgroundStore queue | PORT |
| 7 | Experiment composer (axes → cells → experiment-v2) | `studio-experiment-mode.js` → `POST /studio/experiment-v2` | mode overlay on controls; axis eligibility from schema; one definition submit; History owns entity | playgroundStore experiment draft + composer UI | PORT |
| 8 | Source image ownership (latest-wins, stale discard) | pending handoffs + `_submittedSource` lineage | delayed upload never lands in new context; replace/clear updates base; sketch base change clears overlay | playgroundStore source ownership {ownerKey, token} | PORT |
| 9 | References / multi-image input | `studio_references` companion, `WORKFLOW_REFERENCE_METHODS` | ordered cards; method selection; replace/remove; never inside schema-validated controls | references state + UI | PORT |
| 10 | History picker reuse | shared picker over History V2 | canonical output entity; Data Saver/original respected; no duplicate feed cache | shared HistoryPicker (consume) | PARITY (consume shared) |
| 11 | Sketch handoff ownership | `studio-sketch-shell.js` snapshot/apply/clear | correct base; base swap clears strokes; flattened sketch commits to source field; no stale async | ownership semantics in store; canvas engine | PORT semantics / DEFER engine |
| 12 | Presets image-free + output override | `capturePresetState` + `PRESET_IMAGE_KEYS` strip; `snapshotOutputForPreset` | preset never captures source/references; output choice is run intent, never global Settings mutation; load clears stale ownership | applyPreset in store | PORT |
| 13 | Result / current generation display | runState + carousel + `_handleDirectRunResult` | direct-run fast path; scheduler poll path; History handoff; retry/reuse; download | runState + result panel (historyStore link) | PORT |
| 14 | Modes/subtools shell | `SHELL_MODES/SHELL_SUBTOOLS`, placeholders | generate/edit/post; text/references/layout/sketch/guidance; room rule (collapse empty rails) | mode state + tool strip | PORT |
| 15 | Upscale | `SHELL_PLACEHOLDERS` | visible but execution-disabled | disabled tool entry | PARKED |
| 16 | Golden profile + progress poll | `loadGoldenProfileSelection`, golden progress polling | profile rides top-level; polling is presentation | reuse settingsStore golden selection; operationsStore projection | DIFFERENT (consume existing) |
| 17 | Run gating (method/reference/guidance gates) | `_shellRunGate/_studioMethodGate/...` | honest disabled reason, never silent submit | gate derivation in store | PORT (core gates) |
| 18 | Output preferences (format/save/autosave) | `studio-output-preferences.js` → modal_options | output prefs ride `modal_options`, never mutate Settings | read settingsStore, build modal_options | PORT |
| 19 | Queue viewer / progress | `_refreshQueueViewer`, batch events | per-variant status; cancel | queue panel in Playground | PORT (compact) |
| 20 | Experiment progress/cancel | `createExperimentRunController`, `stopExperiment` | controller is run truth; cancel supported | operationsStore + cancel action | PORT |

Out of scope (frozen): run-controller identity/event adaptation rewrite,
History entity ownership, workflow authority, model inventory authority,
Settings authority, backend execution architecture.

## Implementation status (end of lane)

All PORT items are implemented on `feat/vue-phase5-playground` and proven by
vitest (94/94 full-suite) plus live harness validation against the real built
bundle. Three live-found bugs were fixed during validation:

1. Singleton queue drain deadlocked on its own busy gate (pre-set batch
   presentation state before delegating to the single-run path). Fixed by
   delegating first; regression test added.
2. `freezeIntent` threw on Vue reactive proxies re-read from the store
   (structuredClone rejects proxies), breaking every multi-variant batch.
   Fixed with a JSON-snapshot fallback (payloads are POST bodies by
   contract); regression test added.
3. Shared `HistoryPicker` crashed on open: Teleport mounted with a
   nullish target (portal resolves in onMounted), leaving unmounted vnodes
   that crash the next patch. Fixed by mounting the Teleport only once the
   target exists — heals HistoryView's picker too.
4. `usePicked` always committed to source_image, ignoring the picker role;
   references now branch to `addReference`.
5. Upload endpoint corrected to ComfyUI native `POST /upload/image`
   (was a nonexistent `/comfymodal/studio/uploads`).

Deferred with reason: Sketch canvas drawing engine (ownership semantics
implemented; engine is a legacy-DOM rewrite out of Phase 5 scope).
Parked per contract: Upscale execution.
