# Fake-Backend Playwright Suite — Extension Guide

The Modal Studio deterministic fake-backend suite lives in `tests/browser/fake/`.
It mounts the **real Studio frontend** (`web/*`) inside a harness page against a
**fake backend** that replays scripted scenarios, so Playwright tests get
deterministic runs without a live ComfyUI instance or a paid Modal deployment.

This guide documents the architecture and every extension point. It is grounded
in what actually exists in this directory — read the referenced files for the
authoritative detail.

---

## 1. Architecture overview

```
tests/browser/fake/
├── scenarios.mjs          Declarative scenario definitions (data only)
├── fake-backend.mjs       In-memory engine: sessions, experiments, history,
│                          assets, tracker-bus event queue, timers
├── fake-server.mjs        node:http server exposing the engine + harness + web/
├── harness/
│   ├── index.html           Bare page with #comfymodal-test-host
│   ├── harness-bootstrap.js ?session= → cookie; __mountStudioForTest()
│   └── scripts/             api.js (fake `api` + 40ms event pump),
│                            app.js (fake `app` stub)
├── helpers.mjs            Test-side helpers (this suite's shared utilities)
└── studio-fake-*.spec.mjs The Playwright specs
```

**Session model.** `POST /__comfymodal_test/session` creates an isolated session
(`sess_…`) owning presets, snapshots, backends, experiments, run history, the
History V2 store, the pending scenario, the tracker event queue, and registered
assets. Tests navigate the harness page to `/?session=<id>`; the bootstrap
publishes that id as cookie `comfymodal_fake_session`, so every `/comfymodal/*`
fetch targets the right session. Test-control POSTs pass `sessionId` explicitly
(the server also accepts the cookie or `?session=`).

**Studio mount.** The harness exposes `window.__mountStudioForTest()`, importing
the fake api stub, Studio styles, and `mountStudioShell` from the real `web/`
into `#comfymodal-test-host`. The shell api is published as
`window.__studioApi = { setPage, getState, destroy }`; nav renders
`data-page="playground|history|backend|settings"`.

**Event pump.** The fake api stub polls `GET /__comfymodal_test/events?session&cursor`
every 40ms and dispatches each queued `{type, detail}` as a real `CustomEvent`
onto itself; scenario "tracker" events (`execution_start`, `modal_status`,
`experiment.worker.progress`, `execution_success`, …) flow through this seam to
`web/comfymodal-progress.js`.

**REST surface** (all under `/comfymodal`): presets, snapshots, backends,
`/studio/run`, `/studio/experiment`, `/experiments[/:id][/stop-now]`,
`/run-history[/:id/*]`, `/history`, `/history-v2/*` (see §3), `/deploy/status`,
`/profile/level`, `/assets/:id`, `/studio/outputs/:filename`, `/view`, `/config`.
Static harness files and the real `web/` modules are served under both
`/extensions/comfymodal-modal/*` and `/extensions/comfyui-modal/*`.

**Test-control endpoints** (`/__comfymodal_test/`):

| Endpoint | Purpose |
| --- | --- |
| `POST /session` | create a fresh session → `{ sessionId }` |
| `GET /events?session&cursor` | drain queued tracker events (pump reads this) |
| `POST /scenario` | `{ scenario, sessionId, overrides? }` — pick scenario for the NEXT submit |
| `POST /history-seed` | `{ scenario, sessionId }` — seed legacy history or History V2 (`kind:"seed"` scenarios) |
| `POST /history-v2-fail` | `{ mode:"feed", sessionId }` — next `/history-v2/feed` fails HTTP 500; `mode:""` clears |
| `POST /emit` | `{ sessionId, type, detail }` — inject arbitrary tracker events |
| `GET /state?session` | dump session diagnostics (experiments, journalDetail, history summaries, assetIds, …) |

---

## 2. How to ADD a new fake run scenario

Scenarios are pure data in `tests/browser/fake/scenarios.mjs`. The engine
(`fake-backend.mjs`) creates an experiment at submit time, resolves `{token}`
placeholders (experiment/run/prompt ids, `{asset_N}`, `{output_N}`, `{cell_key_N}`,
`{checkpoint_N}`, `{attempt_N}`), and applies timeline entries on real timers
(`at: { ms: N }`), on poll counts (`at: "poll:N"`), or at submit (`at: "submit"`).

Def shape (`kind: "single"` example — see `success` in scenarios.mjs):

```js
const my_new_scenario = {
  kind: "single",                       // "single" | "experiment" | "seed"
  outputsPerCell: 1,                    // outputs generated per cell
  initialStatus: "running",             // snapshot status right after submit
  initialJournal: [started(1)],         // journal events appended at submit
  initialTracker: [executionStart()],   // tracker events queued at submit
  steps: [
    { at: { ms: 200 }, journal: [attemptCreated(0)], tracker: [cellExecuting(0, "4", "KSampler")] },
    { at: { ms: 300 }, tracker: [samplerStep(0, 10)] },
  ],
  terminal: {
    delay: 650,                         // ms after submit
    status: "completed",
    journal: [cellCompleted(0), completed(1, 0, 0, 1)],
    tracker: [experimentEvent("experiment.completed")],
  },
};
```

Then register it in the `SCENARIOS` export; use it from a test via
`await fx.setScenario("my_new_scenario")`.

For experiments (`kind: "experiment"`) the engine derives cells from `cellCount`
and optional `axes` (see `experimentDef()` helper in scenarios.mjs). History
seeds are `kind: "seed"` — legacy seeds carry a `seed` descriptor (see §4), and
History V2 seeds carry a `v2` flag (see §3.6).

### Scenario overrides (server-side)

`POST /__comfymodal_test/scenario` accepts an `overrides` object merged over the
def: `{ delays: {...}, submit: {...}, extraInitialJournal: [...],
extraInitialTracker: [...], terminalDelay: N }` (see `_mergeOverrides` in
`fake-backend.mjs`). Handy for tightening/loosening timing without a new scenario.

### Journal event builders

`scenarios.mjs` exports builders used by definitions: `started`, `created`,
`attemptCreated`, `cellCompleted`, `cellFailed`, `cellInterrupted`, `cellSkipped`,
`completed`, `failedFatal`, `cancelled`, `experimentError`; tracker builders:
`executionStart`, `executionSuccess`, `modalStatus`, `progressQueue`,
`workerStatus`, `cellExecuting`, `samplerStep`, `workerFailed`, `experimentEvent`.

---

## 3. History V2: endpoints, storage, and seeding

### 3.1 Mode wiring: auto (default) vs fixture (opt-in)

The Studio's History page is **History V2** (`web/studio-history-v2.js` →
`history-v2-repository.js`); the mode comes from `context.historyMode` →
`window.__COMFYMODAL_HISTORY_MODE__` → `"auto"`. `"auto"`/`"v2"` use the real
HTTP adapter calling `/comfymodal/history-v2/*` (failures surface truthfully, no
fixture fallback); `"fixture"` uses the frontend's own dataset
(`web/history-v2-fixtures.js`: 28 generations + 7 experiments, SVG data-URI
thumbs); `"bridge"` maps the legacy `/history` shape. `helpers.mjs openStudio()`
now defaults History mode to **`"auto"`** — the V2 page runs through its normal
HTTP repository against the fake engine. Fixture is an **explicit opt-in** only
(`historyMode: "fixture"`) for isolated UI work.

### 3.2 REST surface — `/comfymodal/history-v2/*` (+ deploy/status, profile/level)

All routes live in the `ROUTES` array of `fake-server.mjs` (see §6) and delegate
to `fake-backend.mjs` (§3.3 store, §3.7 assets).

| Endpoint | Behavior |
| --- | --- |
| `GET /history-v2/feed` | envelope `{status, items, next_cursor, limit, total, has_more}`; `has_more` = `next_cursor !== null` |
| `GET /history-v2/generations/:id` | feed item + `attempts[]` (`run_id, mode, status, started_at, finished_at, duration_ms, error, timing`), `errors[]` (`{code:"attempt_failed", message}`), `export_state` ("none" default), `params` (set keys only), `timing` (last finished attempt, else null), `workflow_json` (null default); 404 `generation not found` |
| `GET /history-v2/experiments/:id` | feed item + ordered `cells[]` (`key, index, status, axis{x,y}, error, generation_id, thumb_url, preview_url, original_url, original_failed, duration_ms, favorite`) + `cover` (first 4 as `{thumb_url, cellKey}`, null-padded to 4); 404 `experiment not found` |
| `PATCH /history-v2/generations/:id/favorite` | `{favorite: bool}` → `{status:"ok", favorite}`; 400 `favorite must be a boolean` / `Invalid JSON body`; 404 `generation not found` |
| `PATCH /history-v2/generations/:id/note` | `{note: string}` → `{status:"ok", note}`; 400 `note must be a string` / `note exceeds 2000 characters (legacy limit)`; 404 `generation not found` |
| `PATCH /history-v2/generations/:id/featured` | `{output_index}` or `{asset_id}` → `{status:"ok", featured_asset_id}`; 400 `missing output_index or asset_id` / `invalid output_index` / `invalid asset_id` (empty or not owned); 404 `generation not found` — generations only |
| `PATCH /history-v2/experiments/:id/favorite` | `{favorite: bool}` → `{status:"ok", favorite}`; same 400s; 404 `experiment not found` |
| `PATCH /history-v2/experiments/:id/note` | `{note: string}` → `{status:"ok", note}`; same 400s; 404 `experiment not found` |
| `GET /history-v2/assets/:id` | deterministic PNG (see §3.7); 404 `asset not found` |
| `GET /deploy/status` | fixed ready payload (identical for every valid session) |
| `GET \| POST /profile/level` | `{status:"ok", level, effective}`; POST `{level}` ∈ `off\|summary\|detailed\|trace\|trace_verbose` else 400 `invalid level` |

`/deploy/status` and `/profile/level` are the **Settings** page endpoints
(`web/studio-settings.js`; see `studio-fake-settings.spec.mjs`): the deploy-state
row renders `state — message`, the Heavy tracing select shows the effective level
and POSTs `{level}` on change (rolling back on a non-ok response). Both are
per-session: level persists in `session.profileLevel`, deploy status is a fixed
payload.

**Feed query params:**

| Param | Meaning |
| --- | --- |
| `kind` | `generation` \| `experiment` \| `mixed` (default); else 400 `invalid kind` |
| `limit` | default 24; integer 1–200; non-integer → 400 `limit must be an integer between 1 and 200`; out-of-range → 400 `limit must be between 1 and 200` |
| `order` | `newest` \| `oldest` \| `fastest` \| `slowest` \| `workflow_asc` \| `workflow_desc` (default `newest`); else 400 `invalid order` (see §3.8) |
| `status` / `statuses` | UI status alias(es), comma-separated; mapped per kind via `V2_GEN_STATUS_ALIASES` / `V2_EXP_STATUS_ALIASES` in fake-backend.mjs |
| `workflow_id` / `workflow`, `preset_id` / `preset` | exact id match — generations only |
| `favorite` | boolean (`1/true/yes/on`, `0/false/no/off`) |
| `date_from`, `date_to` | ISO bounds on `created_at` (both kinds) |
| `preview_only`, `has_preview`, `has_original` (alias `original_available`), `interrupted`, `failed_or_canceled`, `has_image`, `model` | boolean/name filters — generations only |
| `search` | substring over gen `id/workflow_id/preset_id/preset_name/prompt/negative_prompt/note`; exp `id/name/workflow/preset` |
| `cursor` | opaque keyset — single-kind `{k, created_at, id}` base64url; mixed `{"v":2,"g","e"}` (see §3.8) |

Mixed-kind merges both streams via production's V2 `{"v":2,"g","e"}` cursor
shape (stateless per-stream keysets anchored at the last **emitted** item; the
un-emitted window tail re-enters the next page).  Legacy V1 `{g,e,gs,es}`
cursors are tolerated on decode and upgrade to V2.

`listFacets` is client-side (a `limit: 200` feed fetch). For favorite/note the
frontend calls **generations first**, retrying **experiments once on a 404**
(featured is generations-only); any non-object/`{_raw}` body → 400
`Invalid JSON body`. A `_timing=1` query param adds `_diagnostic_timing_ms` to
the envelope (feed diagnostics only).

### 3.3 Session storage: `session.historyV2` records + in-place mutations

`session.historyV2` is an array of internal records (`kind: "generation"` |
`"experiment"`) built once per session by `_seedDefaultHistoryV2()`; wire
feed/detail shapes are **derived on read**, so mutations reflect immediately.

| Record | Fields |
| --- | --- |
| generation | `id, kind, status, workflow_id, workflow_name, workflow_version, preset_id, preset_name, prompt, negative_prompt, created_at, favorite, note, model_names, featured_asset_id, export_state, params, workflow_json, duration_ms, outputs[{index, asset_id, thumb_asset_id, preview_asset_id, original_asset_id, original_failed, original_filename}], attempts[{run_id, mode, status, started_at, finished_at, error, timing}]` |
| experiment | `id, kind, status, name, workflow, preset, created_at, updated_at, favorite, note, axis_labels{x,y}, true_cell_count, duration_ms, cells[{key, index, status, axis{x,y}, error, generation_id, thumb_asset_id, preview_asset_id, original_asset_id, original_failed, duration_ms, favorite}]` |

Supporting state: `session.profileLevel` (default `"off"`; `off|summary|detailed|
trace|trace_verbose`) and `session.historyV2Fail` (`{}` or `{feed:true}`).

Mutations (`setHistoryV2Favorite/Note/Featured`) mutate the internal record **in
place** (`rec.favorite`, `rec.note`, `rec.featured_asset_id`). Sessions live in
the server process keyed by `sessionId`; with `reuseExistingServer: true` the
server **outlives page reloads**, so a fresh mount on `/?session=<id>` sees every
prior mutation until a new session POST (`setupFakeTest` starts each test with
one; engine `resetSession()`/`deleteSession()` exist but are not HTTP-exposed).

`GET /__comfymodal_test/state` exposes `historyV2Count` + `historyV2: [{id, kind,
status, favorite, note, featured_output_index (generations only, else null),
output_count}]`, plus `profileLevel`.

### 3.4 Default session seed (48 records)

Every fresh session gets a deterministic 48-record V2 store via
`_seedDefaultHistoryV2()` (base `2026-08-10T12:00:00.000Z`, hour offsets, no
`Math.random()`/`Date.now()`):

| id | status | Edge case covered |
| --- | --- | --- |
| `gen_ok` | completed | happy path — preview + original, duration set |
| `gen_failed` | failed | error recorded (`CUDA out of memory`) |
| `gen_canceled` | canceled | canceled status |
| `gen_interrupted` | interrupted | `duration_ms: null` (missing-duration record) |
| `gen_preview_only` | completed | preview output only, no original → `preview_only` |
| `gen_original_failed` | completed | preview served + original referenced but 404 (see §3.7) |
| `gen_multi` | completed | 3 outputs (multi-output card) |
| `gen_no_image` | completed | no outputs → `has_image:false` ("No image" fallback) |
| `gen_dupe_names` | completed | duplicate output filenames, distinct asset ids |
| `gen_v2_00`…`gen_v2_29` | mixed | bulk pagination (24–26 running, 27+ interrupted; `gen_v2_05` favorited) |
| `exp_completed` | completed | all cells completed |
| `exp_with_failures` | completed_with_failures | failed cells (partial card) |
| `exp_interrupted` | interrupted | interrupted cells |
| `exp_canceled` | canceled | canceled cells |
| `exp_1` / `exp_2` / `exp_3` | completed | 1 / 2 / 3-cell sweeps — cover pads to 4 |
| `exp_running_1` / `exp_running_2` | running | running + pending cells |

### 3.5 `history_v2_large` seed

`await fx.seedHistory("history_v2_large")` → `{status:"ok", count:80, total:80,
v2:true}`. Replaces `session.historyV2` (legacy untouched). 60 gens
`gen_v2_lg_000..059` + 20 exps `exp_v2_lg_000..019`. Gen statuses: `i%10`
3→failed (with an error string), 6→running, 8→interrupted, else completed;
`i%3===2` no image, `i%7===5` preview-only, `i%13===0` favorited. Exp statuses:
`j%10` 3→running, 5→interrupted, 7→canceled, 0 (j>0)→completed_with_failures;
`cellCount = 1+(j%4)`. Timestamps step back 25 min/gen, 95 min/exp — 3+ mixed
pages at limit 24.

### 3.6 Adding a new v2 seed

Add `const my_v2_seed = { kind: "seed", v2: "mykey" };` to scenarios.mjs and
`SCENARIOS`; add a matching `mykey` branch to `_buildV2Seed(session, key)` in
fake-backend.mjs pushing `_makeV2Generation`/`_makeV2Experiment` records.
`seedHistory()` dispatches on `def.v2` and replaces `session.historyV2`. Keep it
**deterministic**: fixed ids, timestamps from
`V2_BASE_MS = Date.parse("2026-08-10T12:00:00.000Z")` + fixed offsets, no
`Math.random()`/`Date.now()`.

### 3.7 Asset ids

Ids are deterministic per record — `<genId>_o<i>_thumb|_preview|_orig` /
`<expId>_c<i>_thumb|_preview|_orig` (production's opaque `ast_*` ids replaced so
tests can predict URLs). Registration happens at build/seed time
(`_registerV2Asset`); never-registered ids are guaranteed 404. `_pngFor` hashes
the id into one of 10 fixed 4×4 solid-color PNGs — same id, same pixels; served
as `image/png`, unknown ids → 404 `asset not found`. Output
`thumb_url`/`preview_url`/`original_url` → `/comfymodal/history-v2/assets/{id}`;
an **empty URL string means missing image** (never arbitrary file paths).

`gen_original_failed` covers the broken-original case: its output carries an
`original_asset_id` (non-empty `original_url`) in the record's `unregistered`
set — intentionally **not registered**, so that URL 404s while thumb/preview
serve (experiment cells: `original_failed: true`).

### 3.8 Known production-contract mismatches

The fake mirrors production where it matters and deviates only on purpose:

| # | Production | Fake | Note |
| --- | --- | --- | --- |
| 1 | feed accepts all six orders: `newest`, `oldest`, `fastest`, `slowest`, `workflow_asc`, `workflow_desc` (routes.py:794) | same six orders; any other `order` → 400 `invalid order` | the UI dropdown sends `workflow_az`/`workflow_za` for Workflow A-Z/Z-A, which neither production nor the fake accepts — a frontend naming mismatch (web/*.js out of scope) |
| 2 | `workflow_name = workflow_id` (routes.py:305) | human-readable names (`Portrait Pro`, …) | intentional — keeps workflow facets readable |
| 3 | experiment detail `axis.x/y` emit label NAMES (routes.py:585-590) | emits axis values (`"111"`, `"20"`) | frontend-correct |
| 4 | mixed-kind cursor V2 `{"v":2,"g","e"}` (routes.py:572-616), stateless per-stream keysets anchored at the last emitted item | identical `{"v":2,"g","e"}` shape; legacy V1 `{g,e,gs,es}` payloads tolerated on decode, responses upgrade to V2 | pagination is gap-free (test requirement) |
| 5 | profile level persists in `.profile_config.json` (file-level) | per-session (`session.profileLevel`) | cleared on session reset |

### 3.9 Workflow Portability (G12)

Deterministic G5-shaped contract payloads — NO rule logic is simulated. Routes:

| Endpoint | Behavior |
| --- | --- |
| `GET /studio/workflows/versions/:vid/portability` | `{status:"ok", portability}` from the armed mode (`matrix` default = Medium workflow + High environment + Local low/Modal low/RunPod medium/RunComfy unknown/Comfy Cloud high/Baseten medium); other modes `low`/`high`/`unknown_main`; 404 unknown version. Every served report is cached per-session so list/detail chips derive fresh summaries (`stale:false`). |
| `GET /studio/workflows/versions/:vid/export?include_presets=0\|1` | deterministic manifest bytes + `Content-Disposition` filename `<name>-v<n>-<hash8>.workflow.json`; one-shot 409 credential refusal when armed; every success logged to `manifestExports`. NOTE: Chromium re-requests attachment URLs internally for its download manager, so one user click can log >1 server hit — assert dedupe on PAGE network requests. |
| `POST /studio/workflows/import-manifest?dry_run=1\|0` | seeded previews (`valid` default / `invalid` / `missing_deps`) or atomic commit creating `wf_import_<n>` + Version #1 + Mapping + optional presets honoring `import_presets`/`apply_default_preset`; every request logged to `manifestImports`. |

Test-control endpoints:

| Endpoint | Purpose |
| --- | --- |
| `POST /__comfymodal_test/portability {sessionId, mode}` | arm report mode: `matrix\|low\|high\|unknown_main` |
| `POST /__comfymodal_test/portability-export-fail {sessionId, mode}` | `credential` arms a one-shot 409 credential-like refusal; `""` clears |
| `POST /__comfymodal_test/import-manifest-arm {sessionId, preview_mode?, commit_fail_once?}` | seed preview scenario and/or arm a one-shot atomic commit failure |

`dumpState` extras: `portabilityMode`, `portabilityRequests`, `manifestExports`, `manifestImports`. The seeded `wf_incomplete` carries a STALE `portability_summary` for chip-transition tests; imported workflows are appended to the platform seed so list/detail see them.

---

## 4. Legacy history endpoints + record field contract

The legacy history endpoints are still part of the contract (they back the
Playground recent-runs carousel; the History V2 page does **not** use them):

- `GET /comfymodal/history` → `{ status, items, page, page_size, total, has_more }`
  (consumed by `listUnifiedHistory` and the Playground recent-runs carousel).
- `GET /comfymodal/run-history` → `{ status, runs, total, limit, offset }`.
- `POST /comfymodal/run-history/:id/annotations`, `POST .../save`.
- `POST /__comfymodal_test/history-seed { scenario, sessionId }` replaces the
  session's legacy history from a `kind:"seed"` scenario. Existing seeds:
  `history_large` (300 records, statuses `[completed, failed, cancelled,
  in_progress, queued]`, image every other record), `history_missing_image`
  (image assets intentionally 404), `history_duplicate_filenames` (shared
  output filename), `history_legacy` (minimal `{ id, status, created_at }`).
  (`history_v2_large` seeds the V2 store instead — see §3.5.)

`seed` descriptor contract (see `_makeSeedRecord` in fake-backend.mjs):
`{ count, statuses, imageEvery, presetCount, favoriteEvery, startOffsetMs }`
with optional `registerAssets: false`, `assetIdPrefix`, `sharedOutputFilename`,
`sharedAssetId`, `legacy: true`.

Records carry the fields the frontend normalizer reads (`web/studio-run-normalizer.js`
`normalizeStudioRun`): `run_id`, `experiment_id`, `kind`, `status`, `started_at`,
`completed_at`, `prompt`, `steps`, `sampler`, `output_path`, `timings`,
`extra.{studio_preset_id, studio_preset_label, studio_feature_id, prompt,
primary_asset_id}`, `annotations.{favorite, note}`. Image URL order:
`extra.primary_asset_id` → `/assets/<id>`, `asset_id` → `/assets/<id>`,
`output_path` → `/studio/outputs/<filename>`.

**Asset serving is strict**: `GET /comfymodal/assets/:id` and
`/comfymodal/studio/outputs/:filename` return 404 unless the id/filename was
registered (from a journal `cell.completed` payload or a seed). A test asserting
on image **serving** must use ids that exist — read
`GET /__comfymodal_test/state` (`assetIds`, `outputFilenames`,
`experiments[].journalDetail`) to find real ids. Every fresh session registers
deterministic `asset_seed_*` assets via its default history seed.

---

## 5. How to add a new Playwright flow

Everything test-side goes through `tests/browser/fake/helpers.mjs`. The standard
entry point is:

```js
import { test, expect } from "@playwright/test";
import { setupFakeTest, selectPreset, submitSingleRun } from "./helpers.mjs";

test("my deterministic flow", async ({ page }) => {
  const fx = await setupFakeTest(page);          // session + guard + mount
  try {
    await fx.setScenario("success");             // pick scenario for the next submit
    await selectPreset(page, "preset_default");
    await submitSingleRun(page);
    await fx.waitForStatus("Run completed");
    await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible();
    fx.assertNoConsoleErrors();                  // always end with a guard check
  } finally {
    fx.guard.dispose();
  }
});
```

**Rules of thumb** (hard rules in the orchestrator contract):

- Prefer auto-waiting locators + `expect.poll` over sleeps.
- Every spec ends with a console-error check where meaningful.
- If a flow needs server-side setup before the app's first fetch — e.g. a second
  preset for experiment mode — pass a `beforeMount` hook:

```js
let compareId = "";
const fx = await setupFakeTest(page, { beforeMount: async ({ sessionId }) => {
  compareId = await createComparePreset(page, sessionId);
} });
```

  This matters because `web/studio-backend.js` caches runtime presets per
  `apiBase`; a preset created after the first fetch won't be seen until cache
  invalidation.

- To prove isolation (foreign runs don't hijack the UI): `fx.injectEvent(type, detail)`
  with a foreign `experiment_id`, wait a pump cycle (~400ms), assert unchanged.

### Known selectors (from production code — reuse, don't invent)

| UI element | Selector |
| --- | --- |
| Studio page container | `.comfymodal-studio-pagecontainer` / `[data-testid="studio-page"]` (`web/studio-shell.js`) |
| Top nav buttons | `.comfymodal-studio-topnav button[data-page="playground"]` (etc.) |
| Control panel | `[data-testid="control-panel"]` (`web/studio-playground.js`) |
| Backend/preset selector | `[data-testid="backend-select"]` (option value = preset id) |
| Run button | `[data-testid="run-btn"]` (text: Running…/Submitted/Waiting…/Queued…/Run) |
| Run status message | `[data-testid="run-status-message"]` |
| Failure state | `.comfymodal-studio-run-section` text `Run Failed` + `[data-testid="error-dismiss-btn"]` |
| Canvas output | `[data-testid="canvas-output"]` |
| Progress section | `[data-testid="progress-section"]`, `progress-stage/step/elapsed/nodes/queue/bar-fill` |
| Experiment toggle | `[data-testid="experiment-toggle"]` |
| Experiment mode block | `[data-testid="experiment-mode"]` |
| Compare presets | `[data-testid="compare-backends"]`; checkboxes `[data-testid="compare-preset-<id>"]`; expand via `button.comfymodal-studio-collapsible-summary` |
| Run Experiment button | `[data-testid="run-experiment-inline-btn"]` |
| Experiment grid | `[data-testid="experiment-grid-viewport"]`, `experiment-grid-outer`; cells `[data-testid="experiment-cell-<cell_key>"]` with `data-cell-status`; cell images `img.cm-exp-cell-image`, fail icon `.cm-exp-cell-icon-fail` |
| History V2 page | `[data-testid="history-v2-page"]`, results `[data-testid="history-v2-results"]`, cards `.comfymodal-studio-history-v2-card` (`.comfymodal-studio-history-v2-generation-card` / `-experiment-card`), status chip `.comfymodal-studio-history-v2-chip.status-<key>`, thumb `img.comfymodal-studio-history-v2-thumb-img`, prompt `.comfymodal-studio-history-v2-card-prompt`, result count `[data-testid="history-v2-result-count"]`, pagination `[data-testid="history-v2-load-more"]`, toolbar `.comfymodal-studio-history-v2-toolbar button[data-status="failed"]` |

### localStorage persistence keys

- `comfymodal.studio.playground.v1` → `{ presetId, featureId }`
- `comfymodal.studio.playground.results.v1` → **map keyed by `"<presetId>::<featureId>"`**
  (NOT an array) → `{ id, experimentId, imageUrl, … }` — `web/studio-playground-state.js`
- `comfymodal.studio.experiment.draft.v1` → `{ experimentAxes, compareBackendIds }`

---

## 6. How to add future API routes

New `/comfymodal/*` surface is a small change across two files:

1. **Register** in the `ROUTES` array (`fake-server.mjs`, ~line 335):
   `[method, pattern, async (res, body, params, sid) => …]`. `:name` segments
   become `([^/]+)` capture groups via `_compilePattern` (anchored regex).
2. **Handle.** Query params from `res._url.searchParams`; session from `res._sid`;
   respond via `_json(res, data, 200)`, `_error(res, message, 404)`, or
   `_buffer(res, bytes, contentType)`. Engine functions signal HTTP status by
   returning `{ status:"error", message, _httpStatus }` — the route writes
   `r._httpStatus || 200` (feed validators use `|| 400`). Wrap session reads in
   `_sessionOrError(res, sid, fn)` (`UNKNOWN_SESSION` → 404).
3. **Implement the engine function** in `fake-backend.mjs` in the matching block
   (e.g. History V2, ~line 939) and export it; add per-session state to
   `createSession()`/`resetSession()` and surface it in `dumpState()`.

Conventions:

- **Static before `:id`**: routes match top-down over `COMPILED`, so list static
  leaves before catch-alls (see `/studio/workflows/folders` before
  `/studio/workflows/:id`).
- **Bodies**: POST/PATCH/PUT JSON arrives via `_readBody`; an unparseable body
  arrives as `{ _raw }`, which validators like `_v2BodyIsValid` reject.
- **Test-control endpoints**: add one (in `handleTestControl`) only for state
  **not** reachable through the normal REST surface (seeds, fail-mode toggles,
  event injection, session lifecycle). POSTs pass `sessionId` in the body
  (`_sessionIdFromRequest` also honors cookie/`?session=`).

---

## 7. How to run everything

### Fake suite (fast, self-contained, no ComfyUI needed)

```bash
npm run test:fake                  # full fake suite (boots the fake server itself)
npm run test:fake:headed           # headed chromium, for debugging
npm run test:fake:update           # update visual baselines (--update-snapshots)
```

Or directly: `npx playwright test --config=playwright.fake.config.mjs`. The
config boots the server on `STUDIO_FAKE_PORT` (default 8377) via `webServer`
(`reuseExistingServer: true` reuses a running server and its in-memory
sessions). Reports land in `test-results/fake/` and `test-results/fake-report/`.

### Existing live-ComfyUI mocked suite

```bash
npm run test:playwright            # --project=mocked (needs a real ComfyUI on COMFYUI_URL)
```

The mocked project ignores `tests/browser/fake/**` via `testIgnore` in
`playwright.config.mjs`, so the two suites never collide despite the same
`testDir: tests/browser`.

### Real paid smoke tests (live backend)

```bash
COMFYMODAL_LIVE_E2E=1 npm run test:playwright:live   # --project=live
```

The `live` project matches only `studio-live.spec.mjs` and expects a real,
deployed Modal backend — expensive paid smoke tests, never run by the fake suite.

---

## 8. Visual baselines

The four screenshot tests live in `studio-fake-visual.spec.mjs` and use
`expect(page.locator(".comfymodal-studio-pagecontainer")).toHaveScreenshot(...)`.
Baselines use Playwright's default naming and are stored beside the spec
(`studio-fake-visual-spec/<name>.png`). Regenerate them after intentional UI
changes:

```bash
npm run test:fake:update
```

Determinism guards already in place (keep them when editing):
- `expect.toHaveScreenshot.animations: "disabled"` in `playwright.fake.config.mjs`.
- Experiment cell images are **masked** — the engine generates random per-run
  asset ids (→ random PNG colors).
- The running-state capture masks `[data-testid="progress-section"]` because its
  text and bar width mutate on 250ms/40ms timers.
- History thumbs come from deterministic History V2 `_pngFor` PNGs — no masking
  needed; tests wait for the first thumbnail before capturing.

---

## 9. Debugging

- `FAKE_SERVER_DEBUG=1 node tests/browser/fake/fake-server.mjs` logs every request.
- `GET /__comfymodal_test/state?session=<id>` dumps experiments (with
  `journalDetail`), legacy history counts/statuses, the History V2 summary
  (`historyV2Count` + `historyV2[]` with id/kind/status/favorite/note/
  featured_output_index), `profileLevel`, event queue, `assetIds`,
  `outputFilenames`, save requests.
- `POST /__comfymodal_test/emit` lets you inject events by hand to reproduce
  tracker-bus behaviors without a scenario.
- `POST /__comfymodal_test/history-v2-fail { mode: "feed" }` forces the feed to
  500 so you can observe the UI's error state.
- Run a single spec: `npx playwright test --config=playwright.fake.config.mjs
  tests/browser/fake/studio-fake-playground.spec.mjs`; add `--headed` and
  `--trace on` for deeper debugging.

---

## 10. History V2 quick test recipes

```js
// Seed the big dataset and render the mixed feed.
await fx.seedHistory("history_v2_large");          // count: 80, v2: true
await fx.gotoPage("history");

// Load More — unfiltered page 1 = 24 items; the next request carries cursor.
const before = await page.locator(".comfymodal-studio-history-v2-card").count();
await page.locator('[data-testid="history-v2-load-more"]').click();
await expect(page.locator(".comfymodal-studio-history-v2-card")).toHaveCount(before + 24);

// Filter by status — the toolbar re-requests feed with statuses=….
await page.locator('.comfymodal-studio-history-v2-toolbar button[data-status="failed"]').click();
await expect(page.locator(".comfymodal-studio-history-v2-chip.status-failed").first()).toBeVisible();

// Favorite persistence — mutations live in the server, survive reloads, and
// are visible in the state dump.
await page.request.patch("/comfymodal/history-v2/generations/gen_ok/favorite", { data: { favorite: true } });
expect((await fx.getState()).historyV2.find((r) => r.id === "gen_ok").favorite).toBe(true);

// Fail-mode — next feed 500s; clear with mode: "".
await page.request.post("/__comfymodal_test/history-v2-fail", { data: { mode: "feed", sessionId: fx.sessionId } });
expect((await page.request.get("/comfymodal/history-v2/feed")).status()).toBe(500);

// Sort — all six orders are accepted; fastest returns the shortest-duration
// visible record first (gen_no_image, 1500ms).
const sortRes = await page.request.get(
  "/comfymodal/history-v2/feed?order=fastest&statuses=success,running,partial,interrupted"
);
expect(sortRes.status()).toBe(200);
const sortBody = await sortRes.json();
expect(sortBody.items[0].id).toBe("gen_no_image");
// An unknown order is still truthfully rejected.
const badSortRes = await page.request.get("/comfymodal/history-v2/feed?order=bogus");
expect(badSortRes.status()).toBe(400);
expect(await badSortRes.json()).toMatchObject({ message: "invalid order" });
```

Note: `page.request.patch`/`page.request.post` against `/comfymodal/*` without a
session param falls back to the cookie `comfymodal_fake_session` set by the
harness — either works.
