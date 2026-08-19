# Phase E4 Frontend, Settings, and Experiment Audit

Date: 2026-08-17
Scope: read-only audit of the Studio frontend, Settings persistence, modern Experiment submission/freeze behavior, and History V2 Preview/Original presentation.

## Executive Verdict

**Not ready for the complete Phase E4 contract.** The modern Experiment path already submits one server-owned definition, freezes the matrix before dispatch, avoids browser fanout, and preserves same-Generation retry identity. History V2 already has durable Preview/Original asset types, attempt records, cell identity, and honest Experiment Generate Original deferral. The Preview Settings UI is not wired into the request contracts: Single runs omit Preview enabled/codec/quality from `modal_options`, and modern Experiments omit `modal_options` entirely. The visible Global concurrency control is also inert: it writes `comfymodal_global_concurrency`, while the scheduler remains fixed at six. One concrete user-visible bug remains in Generation Detail: nullable section builders are passed directly to `appendChild`, so sparse or empty records can throw and blank the overlay.

The authoritative post-Phase-D handoff named by the audit request was not present in the workspace. The worktree was already heavily dirty before this audit. No production source files, tests, deployments, live image generations, or commits were made by this audit.

## Contract Baseline

| Contract | Current result | Classification |
| --- | --- | --- |
| Preview default is global and OFF | `comfymodal_preview_default` defaults to `off` in Settings | Aligned UI default, but not attached to requests |
| Preview codec is global WebP | `comfymodal_preview_codec` defaults to `webp` | UI-only contract gap |
| Preview quality is global 70 | `comfymodal_preview_quality` defaults to `70` | UI-only contract gap |
| Preview settings are Settings-only | No per-Preset or per-Experiment Preview controls were found | Aligned ownership |
| New Single run reads current settings | Single reads current ordinary output config at submit time | Preview fields missing |
| Experiment freezes settings at acceptance | Matrix and workflow data freeze correctly; Preview/output options are absent | Contract gap |
| No browser fanout | One `POST /studio/experiment-v2`; server expands cells | Aligned |
| No per-Experiment concurrency control | Modern frontend sends no concurrency field | Aligned payload shape |
| Backend concurrency remains 6 | Scheduler default is six; Settings control does not affect it | Inert Settings bug |
| Generate Original is same Generation, new Attempt | Repository primitives support attempts, but the UI/API action is deferred | Contract gap, intentionally deferred |
| History renders sparse/empty output safely | Most placeholders exist, but nullable sections can be appended directly | Concrete bug |

## Evidence Path

The audit used source inspection plus targeted Node unit tests. The strongest evidence path was:

1. Trace global Settings keys and persistence from `studio-settings.js` through `studio-output-preferences.js` and `/comfymodal/config`.
2. Trace Single submission through `buildStudioModalOptions`, `buildRunPayload`, and `POST /studio/run`.
3. Trace modern Experiment submission through `buildModernExperimentDefinition`, `POST /studio/experiment-v2`, `build_cell_plan`, durable matrix creation, and scheduler execution.
4. Trace History V2 assets, attempts, detail rendering, and Generate Original repository/API seams.
5. Run the narrow lifecycle/status tests without deploying or generating images.

Limitations: no live backend run, browser visual check, deployment, or real image generation was performed. The missing post-Phase-D handoff limits historical intent, so statements below distinguish code facts from contract recommendations.

## Settings Architecture

### Existing Mechanisms

- `web/studio-settings.js:31-35` defines Preview defaults: codec `webp`, quality `70`, and a separate `preview_auto_save` flag.
- `web/studio-settings.js:451-457` renders the global Preview default selector and stores `comfymodal_preview_default`; the UI text explicitly says Preview rendering is not implemented.
- `web/studio-settings.js:993-1034` renders Preview codec, quality, and auto-save as local-only flat keys: `comfymodal_preview_codec`, `comfymodal_preview_quality`, and `comfymodal_preview_auto_save`.
- `web/studio-settings.js:40-58` includes the Preview keys in the modern Settings reset set. There is no per-Preset or per-Experiment Preview persistence namespace.
- `web/studio-output-preferences.js:15-22,48-57,67-125` is the shared ordinary-output persistence mechanism. It uses localStorage, server-authoritative `/comfymodal/config` sync, failure reversion, and a cross-surface change event.
- `__init__.py:4561-4591,4593-4660` exposes and persists ordinary output settings through `/comfymodal/config`; it does not expose or validate Preview settings.

### Correct Attachment Recommendation

Use one global Settings-owned value set and snapshot it at request creation. Do not add Preview state to Presets, Experiment drafts, cell controls, or active-run state.

The least-conflicting existing mechanism is to extend the shared output-preference/config path with the three contract fields, while retaining flat localStorage keys as the cache and reset surface:

```text
preview_default: off | on
preview_codec: webp
preview_quality: 70
```

If the implementation intentionally keeps Preview client-local, `buildStudioModalOptions` must still read the global keys directly at Run-button time. The final contract must not rely on `window._comfyModalOutputOptions` alone because `studio-output-preferences.js` currently rebuilds that object from only six ordinary-output keys.

The existing Settings control for `preview_auto_save` is outside the stated E4 contract. It should not become a hidden second Preview policy; either remove it from the approved surface or explicitly define it separately before implementation.

## Single Generation

### Current Flow

- Modern Single workflow execution builds options immediately before submission at `web/studio-playground.js:2239-2254`.
- `buildStudioModalOptions` at `web/studio-playground.js:46-61` reads `/comfymodal/config` and fallback shared output state, then returns `modal_options`.
- `buildRunPayload` at `web/studio-workflow-run.js:642-663` attaches those options to the Single request.
- The legacy Single path also passes `modal_options` at `web/studio-playground.js:2872-2887` and `3235-3248`.

### Finding

Ordinary output settings use the correct current-at-submit behavior. Preview enabled/codec/quality do not: `buildStudioModalOptions` does not include them, so changing the Preview controls cannot affect a new Single request. This is a contract gap, not a stale active-run bug.

### Required Freeze Point

The Preview snapshot must be read after validation and immediately before constructing the request. A later Settings change must affect a later Run only; it must not mutate an active request or its History record. The snapshot should be stored in the request metadata/`modal_options` path already used by the Single flow.

## Modern Experiment

### Current Flow

- `buildModernExperimentDefinition` at `web/studio-experiment-mode.js:1498-1543` creates one definition containing feature, axes, defaults, prompts, and workflow/version/preset selection.
- `executeModernExperimentRun` at `web/studio-experiment-mode.js:1773-1811` sends exactly one `runExperimentV2` request and persists the returned Experiment ID.
- The server calls `build_cell_plan(definition, node_dir)` at `experiment_modern_routes.py:797-818`.
- The planner accepts `definition.modal_options`, validates it, and freezes it into each `CellPlan` at `experiment_modern_plan.py:877-941,1025-1047`.
- The route commits the complete matrix before dispatch at `experiment_modern_routes.py:817-826`; the durable definition includes cell ordering and per-cell plans at `experiment_modern_routes.py:707-729`.
- The scheduler runs the frozen plans and does not re-resolve workflow selection after acceptance. Retry/resume reuse the same Generation and immutable request snapshot through `history_v2_repository.py:2088-2124`.

### Finding

The server has the correct freeze seam, but the Studio frontend never uses it. The modern definition at `studio-experiment-mode.js:1521-1537` has no `modal_options`; consequently `effective_modal_options` becomes `{}` in the planner. Preview enabled/codec/quality and ordinary output options are therefore not frozen into Experiment cells. A Settings change after acceptance cannot alter existing cells, but there is currently no Preview snapshot to protect.

### Concurrency

- The frontend deliberately sends no top-level or definition concurrency field. This is covered by `tests/studio_experiment_v2_frontend_unit.mjs:162-201,270-280`.
- The server-owned scheduler default is six at `experiment_modern_scheduler.py:57`; constructor and payload overrides are explicitly ignored at `experiment_modern_scheduler.py:895-911,942-951`, and browser fanout is absent.
- The Settings UI at `web/studio-settings.js:495-515` writes `comfymodal_global_concurrency`, but no runtime path reads that key. The visible control is therefore inert and should not be described as functional.
- The planner still accepts `definition.concurrency` at `experiment_modern_plan.py:921-928`, while the modern create validator bans only top-level `concurrency` at `experiment_modern_routes.py:594-628`. This leaves an inconsistent, silently ignored definition-level escape hatch. The implementation should either reject it at the definition boundary or remove the unused acceptance path; it must not add a per-Experiment control.

### Browser Fanout

No production browser fanout was found. The production path sends one definition and the server creates the fixed cell plan. `buildModernExperimentCells` at `studio-experiment-mode.js:1443-1490` is a test-only/dead helper with a client cell-ID scheme different from the server's stable hash-based IDs; it is a maintenance risk but not evidence of production fanout.

## History V2

### Asset and Attempt Model

- `history_v2_models.py:38-50` has distinct `thumbnail`, `preview`, and `original` assets plus `preview` and `original` run modes.
- `history_v2_routes.py:222-263,294-380` projects Preview/Original URLs and `preview_only`/`original_available` state from durable assets.
- `history_v2_routes.py:781-844` projects per-cell Preview/Original assets, stable cell position, status, duration, and error.
- `history_v2_repository.py:524-567` supports adding a new attempt under an existing Generation, including `mode="original"`.
- `history_v2_repository.py:764-835` and `2088-2124` preserve the same Generation and immutable snapshot for cell retries/resumes while appending a new Attempt.
- `web/history-v2-repository.js:740-776` preserves Generation attempts for the detail view. Experiment status/detail uses the modern route registered separately in `__init__.py:7125-7157`.

### Generate Original

Generation Detail exposes a `Generate Original` button at `web/studio-history-v2-detail.js:421-455` and calls `repo.generateOriginal` at lines 437-439. The real V2 repository intentionally returns unavailable at `web/history-v2-repository.js:628-633`; no Generate Original route is registered in the current History V2 route summary. Experiment History explicitly renders a disabled unavailable action at `web/studio-history-v2-experiment.js:197-209,640-648`, and its unit test codifies that deferral.

Classification: **intentional deferred contract gap**, not an accidental working action. The eventual implementation must use the existing Generation/cell identity, create a new `original` Attempt under the same Generation, rerun the frozen request, and refresh History. It must not create a new Generation, mutate the previous Attempt, or silently replace Preview assets.

### Empty and Sparse Outputs

The left side of Generation Detail has explicit placeholders for no outputs and missing Preview/Original at `web/studio-history-v2-detail.js:265-332`. Zero-output failure records are intentionally distinguished from not-found placeholders at lines 579-594.

Concrete bug: `buildRightColumn` directly appends nullable builders at `web/studio-history-v2-detail.js:474-480,483-489,525-540`. `_section` returns `null` when all rows are absent (`lines 201-207`), and `buildParamsSection` returns `null` when parameters are absent (`lines 363-379`). Direct `appendChild(null)` can throw for sparse/empty records and blank the detail overlay. The fix belongs in the detail renderer, not in History data normalization; each nullable section must be appended only when non-null.

## Behavior Matrix

| Scenario | Required E4 behavior | Current behavior |
| --- | --- | --- |
| Settings Preview OFF, new Single | Snapshot `preview_default=off`; no per-run UI override | Global key exists, but request omits it |
| Settings Preview ON, new Single | Snapshot `preview_default=on`, WebP, quality 70 unless changed | Request omits all three Preview fields |
| Settings change during active Single | Existing request remains unchanged; later request sees new values | No Preview snapshot exists; ordinary options are request-local |
| Settings Preview OFF, new Experiment | One definition; Preview state frozen once for all cells | One definition, but no Preview state |
| Settings Preview ON, new Experiment | Same one definition; server expands cells; all cells share frozen settings | Server freezes an empty `modal_options` object |
| Settings change after Experiment acceptance | Existing cells/attempts unchanged; later Experiment gets a new snapshot | Existing frozen plan is stable, but Preview settings were never captured |
| Single History with Preview only | Show Preview; Original remains unavailable/pending | Asset projection and slots exist; Generate Original is deferred |
| Single History with no output | Show status, errors, attempts, and placeholders without blanking | Placeholder paths exist, but nullable section bug can blank the overlay |
| Experiment cell retry | Same cell and Generation; new Attempt; prior Attempt retained | Durable repository semantics are aligned; UI/API coverage remains split across modern routes |
| Experiment Generate Original | Same cell/Generation, new Original Attempt, full rerun | Explicitly unavailable |
| Concurrency | Global backend default six; no per-Experiment control | Backend remains six; Settings control is inert |

The exact backend byte behavior for Preview OFF versus Preview ON cannot be proven from the current source because `studio-settings.js:457` says Preview rendering is not yet implemented and the request contract does not carry the setting. That rendering policy must be made explicit during implementation rather than inferred from the UI labels.

## Findings by Severity

| Severity | Finding | Type | References |
| --- | --- | --- | --- |
| High | Sparse Generation Detail can throw on `appendChild(null)` and blank the overlay | Bug | `web/studio-history-v2-detail.js:201-207,363-379,474-540` |
| High | Preview enabled/codec/quality are not attached to Single requests | Contract gap | `web/studio-settings.js:451-457,993-1034`; `web/studio-playground.js:46-61,2239-2254` |
| High | Preview/output options are absent from modern Experiment definitions and cell snapshots | Contract gap | `web/studio-experiment-mode.js:1498-1543`; `experiment_modern_routes.py:797-818`; `experiment_modern_plan.py:930-941` |
| Medium | Global concurrency Settings control has no consumer | Bug | `web/studio-settings.js:495-515`; `experiment_modern_scheduler.py:57,895-911,942-951` |
| Medium | `definition.concurrency` is accepted by planner but not persisted or honored, despite top-level ban | Contract inconsistency | `experiment_modern_plan.py:921-928`; `experiment_modern_routes.py:594-628,707-729` |
| Medium | Generate Original UI/API is intentionally deferred and cannot yet satisfy same-Generation/new-Attempt behavior | Deferred contract gap | `web/studio-history-v2-detail.js:421-455`; `web/history-v2-repository.js:628-633`; `web/studio-history-v2-experiment.js:640-648` |
| Low | Client-only `buildModernExperimentCells` duplicates server planning with divergent cell IDs | Maintenance/evidence risk | `web/studio-experiment-mode.js:1443-1490`; `experiment_modern_plan.py:541-572` |

## Later-Write Ownership and Conflict Risk

No later-write ownership was changed by this audit. Any implementation should use these ownership boundaries:

- Settings persistence and Preview control semantics: `web/studio-settings.js`, `web/studio-output-preferences.js`, and the `/comfymodal/config` handlers in `__init__.py`.
- Single request snapshot: `web/studio-playground.js` and `web/studio-workflow-run.js`.
- Modern Experiment request snapshot: `web/studio-experiment-mode.js`; backend freeze validation remains in `experiment_modern_plan.py` and `experiment_modern_routes.py`.
- Durable Original Attempt and asset state: `history_v2_repository.py`, `history_v2_models.py`, `history_v2_routes.py`, and the modern Experiment route module where cell actions belong.
- History rendering and sparse-record guard: `web/studio-history-v2-detail.js`, `web/studio-history-v2-experiment.js`, and `web/history-v2-repository.js`.

Highest conflict risk is in already-dirty files: `web/studio-settings.js`, `web/studio-playground.js`, `web/studio-experiment-mode.js`, `__init__.py`, and the untracked History/Experiment V2 modules. Do not treat the current worktree as a clean Phase-D baseline, and do not overwrite unrelated modifications.

## Verification

Passed targeted tests:

```text
node tests/studio_experiment_v2_frontend_unit.mjs
node tests/studio_history_v2_experiment_unit.mjs
node tests/studio_playground_run_unit.mjs
node tests/studio_history_v2_persisted_status_unit.mjs
```

These tests passed their full listed sections. They establish modern lifecycle identity, one-definition submission, fixed cell ordering, status/retry/resume rules, History Experiment labels, and persisted status normalization. They do not establish Preview setting propagation or the sparse Generation Detail path. No browser test, live backend request, deploy, real image generation, Phase-D gate rerun, or commit was performed.

## Recommended Implementation Order

1. Fix nullable History Detail section appends and add a zero-output/sparse-record test.
2. Make Preview settings one global authoritative value set and include a request-time snapshot in Single `modal_options`.
3. Include the same copied `modal_options` in the modern Experiment definition so the existing planner freezes it per cell.
4. Decide and enforce whether `definition.concurrency` is rejected; keep concurrency global-only and either remove or wire the inert Settings control without adding a per-Experiment override.
5. Implement Generate Original only after the backend route can create a new Attempt under the existing Generation/cell and retain Preview plus prior Attempts.

## E4 IMPLEMENTATION FOLLOW-UP A

### E4A Verdict

The E4A frontend/global-settings/request-capture scope is implemented. Preview settings now use the shared server-backed output preference/config path, Single requests capture a fresh Preview/output options object immediately before submission, and modern Experiments attach one copied options object to the single definition POST. The backend Experiment planner/freeze path was left unchanged because it already accepts and freezes `definition.modal_options`. The inert concurrency input was removed from the active modern Settings surface; the backend remains fixed at global width 6 with no per-Experiment field. The sparse Generation Detail nullable-section failure is fixed without inventing History data.

### Settings Now Wired

- `web/studio-output-preferences.js` now owns `preview_default`, `preview_codec`, and `preview_quality` alongside ordinary output preferences.
- Defaults are `off`, `webp`, and `70`.
- Preview settings are POSTed to and hydrated from `/comfymodal/config`.
- LocalStorage cache writes occur only after a successful server response, preserving failure reversion.
- `preview_auto_save` remains out of the active Preview execution/settings path.
- The active codec selector exposes only the product WebP setting.

### Config Fields

`__init__.py` now persists and returns:

```text
preview_default: "off" | "on"
preview_codec: "webp"
preview_quality: integer 1..100
```

Invalid Preview default, codec, or quality values return the existing config error shape and do not update persisted settings.

### Single Freeze Point

`web/studio-playground.js:buildStudioModalOptions` now delegates to the shared `loadModalOptions` helper. The helper reads server config with the local cache fallback and returns a fresh object containing ordinary output fields plus:

```text
preview_default
preview_enabled
preview_codec
preview_quality
```

`web/studio-workflow-run.js:buildRunPayload` shallow-copies `modal_options` into the new request payload. Settings changed after payload construction cannot mutate the captured object.

### Experiment Freeze Point

`web/studio-experiment-mode.js:buildModernExperimentDefinition` accepts the already captured options object through its context and copies it into `definition.modal_options`. `executeModernExperimentRun` captures options once before the one `POST /comfymodal/studio/experiment-v2`. No browser cell construction, fanout, or concurrency field was added. All accepted cells therefore receive the same frozen options object through the existing backend planner seam.

### Concurrency UI Decision

The misleading `settings-global-concurrency` input was removed from the active Settings surface. Settings now states that Experiment scheduling uses the fixed global backend width of 6 and has no per-Experiment override. No backend scheduler or `definition.concurrency` code was changed.

### Sparse Detail Fix

`web/studio-history-v2-detail.js` now uses `appendIfPresent` for nullable Workflow, Parameters, Metadata, Attempts, and Export sections. Empty-output, zero-parameter, failed, interrupted, canceled, and sparse records continue to use their existing placeholders and status/error data without `appendChild(null)` failures. Generate Original UI/backend behavior was not implemented or activated.

### Tests and Results

Added `tests/studio_phase_e_preview_settings_unit.mjs`, covering:

- OFF/WebP/70 defaults;
- shared persistence and failure reversion;
- Single request-time capture;
- one frozen Experiment options object;
- one modern Experiment POST with no fanout or concurrency;
- truthful fixed-concurrency Settings UI;
- config field/validation presence;
- sparse, empty, and failed detail placeholders.

Passed:

```text
node tests/studio_phase_e_preview_settings_unit.mjs
node tests/studio_experiment_v2_frontend_unit.mjs
node tests/studio_history_v2_experiment_unit.mjs
node tests/studio_playground_run_unit.mjs
node tests/studio_history_v2_persisted_status_unit.mjs
```

No deployment, live generation, GPU work, Phase-D rerun, or commit was performed.

### Remaining E4B Work

Generate Original remains deferred. E4B still owns the active History frontend work needed to expose a truthful Generate Original action only after its backend route/state contract exists, using the same Generation/cell identity and a new Attempt rather than creating a new Generation.

## E4 Implementation Follow-Up B — History Presentation

### E4B Verdict

History V2 presentation now follows the remote-only and lightweight-asset policy without activating Generate Original. Feed cards, Experiment covers, and Experiment cells select Thumbnail first, then Preview, and otherwise render a deliberate asset state. Generation Detail selects Preview first, then Thumbnail; an existing Original is represented as availability until the user explicitly chooses View Original. No normal feed, cover, grid, or detail mount assigns an Original URL to an image element automatically.

### Feed and Experiment Fallback

- `web/history-v2-repository.js` now preserves separate `thumbUrl`, `previewUrl`, and `originalUrl` values and exports shared `selectFeedAsset` / `selectDetailAsset` policy helpers.
- `web/studio-history-v2.js` uses the feed selector for generation cards and Experiment covers. A Preview fallback receives a Preview badge; Thumbnail does not. Original-only records render `Original available`, and records without a lightweight asset render `No image`.
- `web/studio-history-v2-experiment.js` applies the same Thumbnail → Preview → state policy to every cell. A remote-only Original cell is a nonblank `Original available` tile, not an Original download.
- Experiment cell normalization now preserves logical `outputs` and attempt records from the cell or its embedded Generation payload. The browser does not regroup outputs by `run_id` or equate attempts with outputs.

### Generation Detail and Existing Original

- `web/studio-history-v2-detail.js` no longer uses `previewUrl || originalUrl` for the featured image. Preview is preferred, then Thumbnail, with an explicit Original-available placeholder when no lightweight asset exists.
- Existing Original bytes are assigned to an image only inside the `View Original` click handler (`data-testid="history-v2-view-original"`). This is display of an existing asset, not Generate Original.
- The disabled `Generate Original (unavailable)` control remains visible as a truthful deferred state and no longer calls `repo.generateOriginal`.
- Attempts display purpose from the existing `mode` (`Preview` or `Original`) separately from lifecycle status. A successful Original remains available when a later Original retry is failed; a Preview plus failed Original retains the Preview and shows the failure state.
- Preview badges are rendered only when the selected asset is explicitly `preview`; no `.webp` or `has_image` inference was added.

### Tests and Results

Added `tests/studio_phase_e_history_presentation_unit.mjs` with 16 deterministic sections covering feed/grid fallback, Original-only placeholders, detail selection, click-only Original loading, Preview badges, corrected failure projection consumption, retained Original after failed retry, mode/status labels, sparse detail safety, and the no-Generate-Original request guard.

Passed:

```text
node tests/studio_phase_e_history_presentation_unit.mjs
node tests/studio_phase_e_preview_settings_unit.mjs
node tests/studio_history_v2_experiment_unit.mjs
node tests/studio_history_v2_persisted_status_unit.mjs
node tests/studio_phase_e_contract_unit.mjs
node tests/studio_playground_run_unit.mjs
python -m unittest tests.test_studio_history_v2_js
node --check web/history-v2-repository.js
node --check web/studio-history-v2.js
node --check web/studio-history-v2-detail.js
node --check web/studio-history-v2-experiment.js
```

`python -m unittest tests.test_phase_e_history_projection` remains blocked by one existing backend-owned E1A failure: `test_failed_original_preserves_preview_and_sets_failure` currently returns an empty `preview_url` for a missing local Preview path. No backend History file was modified by E4B; the E1A lane owns that projection behavior.

### Remaining E4C Work

Generate Original remains unavailable. The later action must use the existing Generation or Experiment-cell identity, create a new Original Attempt, preserve Preview and prior successful Originals, expose queued/running/failed/successful state from durable backend data, and refresh the same History record. E4B intentionally adds no POST, retry, fake success, browser fanout, or Original generation behavior.
