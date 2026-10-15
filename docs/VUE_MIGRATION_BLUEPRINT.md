# Modal Studio Vue Migration Blueprint — Revised Phase 0

**Status:** AUTHORITATIVE migration contract  
**Audited baseline:** `9ea749bd2bdf2f2ef5316f5490834dc7ec0a869c`  
**Date:** 2026-10-15  
**Scope:** frontend replacement and frontend-state consolidation. Backend/execution semantics are reused unless this document identifies a concrete seam that must be preserved.

This document supersedes the Vue-migration architecture in `docs/FRONTEND_MODERNIZATION_PLAN.md` and the earlier Phase-0 draft.

Historical reports/tests remain behavioral evidence, but this file is the migration architecture authority.

---

# 1. Goal

The migration is:

```text
CURRENT BACKEND + CURRENT PRODUCT SEMANTICS
                    ↓
         CONSOLIDATED FRONTEND OWNERSHIP
                    ↓
             FRESH VUE UI
```

It is **not** a backend redesign, execution redesign, or reimplementation of Studio V3 Phases 1–13.

Primary goals:

1. fresh modern UI;
2. fewer bugs caused by split frontend state;
3. one obvious owner for shared application reality;
4. shared UI where behavior is genuinely shared;
5. shared endpoint/client logic where operations are genuinely the same;
6. make the correct implementation path obvious to future agents;
7. replace existing bespoke async/state plumbing where a small shared primitive can delete it;
8. low maintenance;
9. minimal creative freedom around settled product semantics.

---

# 2. Architecture rule

> **Merge things whose differences are parameters. Separate things whose responsibilities are actually different.**

And:

> **An abstraction is desirable when it eliminates more duplicated state/lifecycle/error-handling code than it adds, and gives future developers one obvious place to solve that problem.**

Good:

```text
15 stale-request counters → createLatestTask()
9 bespoke busy/progress records → operationStore
```

Bad:

```text
store → repository → service → adapter → API
```

when those layers do not remove duplication or establish meaningful ownership.

---

# 3. Approved stack

Use:

- Vue 3
- TypeScript
- Pinia
- Vue Router
- Tailwind CSS 4
- shadcn-vue / Reka
- Lucide
- Zod
- VueUse
- Vite

Do **not** add by default:

- TanStack Query
- XState/general state-machine framework
- Pinia persistence plugin
- generic repository layer
- generic event-bus library
- generic operation executor
- generic cache framework
- universal form engine
- Shadow DOM

TanStack Query may be reconsidered after Phase 1/2 if implementation evidence shows we are recreating query-cache behavior at meaningful scale.

---

# 4. One Vue application

There is exactly **one** Studio Vue app and **one** Pinia instance.

Do not mount a separate Vue app per page.

```text
ComfyUI
└── thin host extension
    └── ONE Vue Studio
        ├── ONE Pinia
        ├── Vue Router
        ├── API layer
        ├── async primitives
        ├── compatibility bridge
        └── pages
            ├── Playground
            ├── History
            ├── Workflows
            ├── Manage Modal
            └── Settings
```

Docs remain a separate Help surface.

---

# 5. Stores

Start with exactly six shared/domain stores:

```text
stores/
├── infrastructure.ts
├── workflows.ts
├── history.ts
├── playground.ts
├── settings.ts
└── operations.ts
```

Do not create `appStore` initially.

- navigation belongs to Vue Router;
- modal open/close belongs to the ComfyUI host boundary;
- tiny root initialization state can stay in the root component/composable.

If substantial genuinely shared app-level state later appears, adding `appStore` is allowed.

---

# 6. `operationStore`: shared registry, not executor

`operationStore` exists to:

- make long-running work discoverable;
- prevent future agents from inventing another operation registry;
- give progress/busy/error presentation one shared shape;
- enable one optional activity/progress UI;
- delete duplicated `{busy,status,progress,message}` structures.

It does **not** own execution semantics.

Reasonable starting shape:

```ts
type OperationKind =
  | "generation"
  | "experiment"
  | "deploy"
  | "workspace-swap"
  | "model-download"
  | "node-sync"
  | "inventory-sync"
  | "workflow-import"
  | "other"

type OperationStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "canceled"

type Operation = {
  id: string
  kind: OperationKind
  label: string
  status: OperationStatus
  progress?: number
  message?: string
  startedAt: number
  finishedAt?: number
  workspaceId?: string
}
```

The real type may be smaller if repo evidence supports less.

Public API should remain boring:

```ts
operations.start(...)
operations.patch(id, ...)
operations.finish(id, ...)
operations.fail(id, ...)
operations.cancel(id, ...)
operations.remove(id)
```

## `operationStore` does NOT decide

- whether generation is terminal;
- how websocket run identity works;
- what deploy status means;
- whether reboot disconnect is expected;
- whether a model download is complete;
- what retry means;
- workspace-swap phase semantics;
- Experiment cell semantics.

Those stay in the owning domain.

```text
operationStore = WHAT is visibly happening?
domain store   = WHAT does it mean?
API            = HOW do we talk to the backend?
async utility  = HOW do we safely wait/read?
```

The existing run controller remains the authority on run lifecycle; it may project a summary into `operationStore`, but `operationStore` must not wrap/reimplement it.

---

# 7. Vue Router

Use Vue Router because navigation should have one standard, obvious owner.

However, preserve the existing external Studio route contract:

```text
#comfymodal=playground
#comfymodal=history&focus=<opaque-id>
#comfymodal=workflows
#comfymodal=backend
#comfymodal=settings
```

Required behavior:

- page change creates browser history;
- same-page focus change replaces current history entry;
- Back/Forward restores page/focus;
- unrelated ComfyUI hashes are left alone;
- malformed Studio hashes fail softly;
- explicit programmatic opener/alias wins for that invocation;
- explicit close clears auto-reopen state;
- hash presence alone must not forcibly reopen Studio after explicit close.

A small Vue-Router history/serialization adapter is acceptable to preserve these semantics.

Do **not** silently change the public URL format to `#/history/:id`.

---

# 8. Small async primitives

The current frontend contains many bespoke versions of:

- generation counters;
- owner tokens;
- stale selection checks;
- `isConnected` guards;
- `AbortController` usage;
- current-request identity;
- duplicate polling ownership.

Create only:

```text
async/
├── latest.ts
└── polling.ts
```

Their purpose is to delete repeated mechanics, not create an async framework.

---

# 9. `latest.ts`

Purpose:

> only the newest read tied to a changing selection/query may commit.

Useful for:

- workflow/version detail;
- History query/focus/detail;
- model/node refresh;
- image ingest tied to current selection;
- settings subresource reads;
- workspace/inventory refresh.

Desired behavior:

1. newer invocation aborts old request when abort is supported;
2. prior commit token is invalidated even if transport cannot physically abort;
3. old response cannot overwrite newer state.

Example shape:

```ts
const task = createLatestTask()

const result = await task.run((signal) =>
  workflowsApi.getVersion(versionId, { signal })
)

if (result.stale) return
state.version = result.value
```

Do not use latest-wins blindly for mutations.

---

# 10. `polling.ts`

Purpose:

> delete repeated polling boilerplate without stealing domain semantics.

Example:

```ts
await pollUntil({
  signal,
  intervalMs: 2000,
  run: () => goldenApi.getDeployStatus(profile),
  done: (value) => value.state === "done" || value.state === "failed",
})
```

The utility owns:

- delay;
- abort handling;
- loop lifecycle;
- generic repeat mechanics.

The domain owns:

- endpoint;
- interpretation;
- success/failure messages;
- retry/refusal semantics;
- `operationStore` updates.

Do not build a polling scheduler framework.

---

# 11. Explicit state models where they delete boolean spaghetti

Do not introduce a mandatory state-machine library.

But when a real lifecycle is currently represented by interdependent booleans, prefer a discriminated union/state model.

Bad:

```ts
isLoading
isDeploying
isRestarting
didFail
didComplete
pendingCancel
```

Better:

```ts
type DeployState =
  | { status: "idle" }
  | { status: "starting" }
  | { status: "deploying"; operationId: string }
  | { status: "completed" }
  | { status: "failed"; error: string }
```

Good candidates to evaluate:

- deployment/redeploy;
- workspace swap;
- custom-node publication/rebuild;
- workflow wizard lifecycle;
- model install/download.

Use XState only if a concrete lifecycle proves complex enough that the library removes more code than it adds.

The existing run controller already embodies complex lifecycle logic and should be reused/ported rather than replaced merely for consistency.

---

# 12. Zod

Zod is part of the stack.

Use it at meaningful trust boundaries:

- important HTTP responses;
- localStorage/sessionStorage from previous Studio versions;
- persisted drafts/templates/preferences;
- imported external data where browser-side validation is required.

Do not use Zod as an internal type system.

Rule:

```text
external / untrusted / durable boundary → Zod is appropriate
internal ephemeral data                → normal TypeScript
```

Avoid schemas for every component prop, local object, and intermediate transformation.

---

# 13. VueUse

VueUse is part of the stack.

Use it where it deletes repeated browser/Vue lifecycle plumbing, e.g.:

- media queries;
- ResizeObserver;
- MutationObserver;
- event listeners;
- element size;
- debounce/throttle;
- keyboard helpers;
- pointer helpers;
- selected explicit storage helpers.

VueUse is a utility library, not an authority layer.

Do not wrap every browser API just because VueUse has a composable for it.

---

# 14. TanStack Query

Do not add it in Phase 1 by default.

Reconsider after Phase 1/2 if we are manually rebuilding significant amounts of:

- query dedupe;
- stale-time behavior;
- automatic refetch;
- query invalidation;
- retry/cache lifecycle.

If added later, ownership must be explicit, for example:

```text
TanStack Query = remote query cache
Pinia           = application/session state
```

Do not create two caches for the same records accidentally.

---

# 15. No generic repository layer

Target:

```text
component
   ↓
Pinia store
   ↓
domain API
   ↓
HTTP
```

The API module owns backend communication.
The store owns application state.

A repository needs a distinct third responsibility to justify itself.

The existing History repository had historical fixture/bridge/V2 reasons. The Vue production app should use History V2 directly while reusing useful pure normalizers/action-state helpers.

---

# 16. Persistence

Do not use whole-store persistence.

Create one small explicit helper:

```text
persistence/
└── persistence.ts
```

Use Zod for nontrivial durable shapes.

Good persistence candidates:

- History filters/sort/columns;
- selected workflow/version preference;
- Playground mode/subtool preference;
- shelf layout/drafts;
- workflow method choices;
- Experiment draft;
- Layout templates/draft;
- Post recipe/Looks/LUT favorites;
- interface width;
- refresh interval;
- Golden favorites;
- Phase-12 image-free preset working draft.

Do not persist by default:

- Generation entities;
- run/websocket identity;
- active server operation state;
- compare A/B selection;
- uploaded image ownership;
- Sketch pixels/layers;
- selection overlays;
- loading/error flags.

---

# 17. Canvas compatibility bridge

The Vue Studio is not the normal ComfyUI canvas path.

Current canvas code still consumes some browser globals/local keys.

Do not delete them at cutover.

Target:

```text
server settings / Vue settingsStore
              ↓
      compatibility projection
              ↓
legacy canvas consumers
```

The bridge becomes one-way after successful server bootstrap.

Keep only values proven to have remaining non-Vue readers, such as:

- output options;
- canvas pass-through/enable state;
- production-mode compatibility state if still consumed.

Do not create a two-way sync system.

---

# 18. Cross-tab invalidation

Keep a tiny BroadcastChannel invalidation mechanism because Pinia is per-tab.

Messages carry only coarse invalidation kinds:

```text
settings
workspace
history
workflows
```

The receiving store refetches server truth.

Do not broadcast full entities or build another app event bus.

Same-tab cache-sync events should disappear where shared Pinia state makes them unnecessary.

---

# 19. Non-negotiable product contracts

## Five Studio pages

At cutover:

- Playground
- History
- Workflows
- Manage Modal (`backend` route key)
- Settings

Docs remain separate.

## Host lifecycle

Preserve:

- sidebar launcher;
- fallback launcher;
- `window.open_testing_modal`;
- `window.close_testing_modal`;
- focus restoration;
- body scroll lock;
- background inert/aria-hidden;
- Escape/backdrop behavior;
- same-tab refresh auto-reopen;
- explicit-close suppression;
- listener/timer cleanup.

Prefer one mounted Vue app shown/hidden rather than remounting the whole app on every open.

## Workflow-wizard graph interaction

During graph binding, underlying ComfyUI graph interaction must be possible.

Use a direct host bridge such as:

```ts
host.setGraphInteractionEnabled(true | false)
```

instead of inventing a new event architecture.

## Phase-13 canvas rule

Central image stage contains only:

- image/content;
- spatial direct-manipulation overlays.

Persistent normal controls/forms live outside it.

## Frozen request intent

Run/Queue/Experiment submission freezes relevant intent. Later UI edits cannot mutate the queued/submitted request.

## Run identity

Preserve current strict run semantics:

- fresh frontend identity per click;
- stale/foreign websocket events rejected;
- prompt IDs matched;
- experiment events require matching Experiment ID;
- terminal state cannot regress;
- duplicate snapshot/journal data ignored;
- Golden progress is presentation only;
- authoritative request result owns completion/output.

Reuse/port the existing run controller. Do not wrap it in a generic execution engine.

## Source/base image ownership

Late uploads cannot commit into newer selection/workflow state.
Changing base image clears incompatible overlays while preserving editor tool settings where current behavior requires it.

## Phase-12 saved workflow state

Saved workflow state/presets are image-free configuration.

They do not capture source/reference/mask/generated/Sketch pixels or Compare images.

Output values in a saved workflow state are Playground/run overrides and do not mutate global Settings.

Post Processing saved styles are **Looks**, not workflow presets.

## Upscale

Remain parked/placeholder. Do not implement it during migration.

## Model/provider neutrality

Do not add model-family/provider frontend branches unless current contract evidence requires one.

---

# 20. Store ownership

## `infrastructureStore`

Own:

- workspaces;
- active workspace ID;
- deployment/readiness/log state;
- inventory state;
- models/custom nodes shared across surfaces;
- node publication/rebuild state;
- relevant credentials/repair state.

In-flight operations freeze target workspace only where submission semantics require it.

## `workflowsStore`

Own:

- workflows/folders/tags;
- versions;
- shared workflow/version selection;
- mappings/candidates/revisions;
- dependencies;
- compatibility;
- portability;
- workflow-version presets;
- shared guidance mappings.

Do not copy the whole current `studio-workflows.js::_view` into Pinia. Local dialog/editor state stays local when it has one owner.

## `historyStore`

Own:

- History V2 feed;
- loaded Generations;
- loaded Experiments;
- selected/focused History entity;
- recent runs;
- History picker source;
- transient compare selection.

Do not build a generic entity framework.

## `playgroundStore`

Own:

- mode/subtool;
- selected workflow/version reference;
- working controls;
- source-image state;
- references/layout/guidance/method selections;
- queue/experiment draft;
- active saved-workflow/preset identity and dirty state;
- current displayed generation ID/reference.

Large editor internals remain inside their editor/session implementation if moving them into Pinia adds no shared-owner value.

## `settingsStore`

Own:

- server `/config`;
- selected GPU;
- Outputs/Data Saver;
- `skip_plan_validation`;
- profile/tracing settings;
- Golden catalog/selection state needed by Settings;
- active Golden GPU order map;
- intentional interface preferences.

## `operationsStore`

Own only shared visible operation summaries as defined above.

---

# 21. Async policy

| Operation | Policy |
|---|---|
| selection-bound read | latest wins |
| History query/focus read | latest query/focus wins |
| image upload/ingest | latest matching selection wins |
| settings mutation | mutation completes; server ack/revert |
| favorite/note/delete | mutation completes even after navigation |
| deployment | domain-owned long operation + poll |
| node publication | domain-owned long operation + poll/status ID |
| model install/download | server operation identity |
| Run | frozen request + existing run-controller identity |
| batch | frozen per-item request + NDJSON stream |
| Experiment V2 | frozen definition + experiment/cell IDs |
| Golden progress | presentation only |

Do not use `latest.ts` for arbitrary mutations.

---

# 22. API structure

Start with:

```text
api/
├── http.ts
├── assets.ts
├── runs.ts
├── history.ts
├── workflows.ts
├── infrastructure.ts
├── settings.ts
└── golden.ts
```

Files may be combined if one remains trivial.

`http.ts` owns only common normal request mechanics:

- `/comfymodal` base;
- JSON headers/body;
- structured error extraction;
- optional AbortSignal;
- JSON/text parsing.

Do not impose one universal timeout.

Keep specialized transports explicit:

- `/studio/run_batch` NDJSON;
- `/upload/image` FormData;
- blobs/manifest downloads;
- Manager reboot disconnect/reconnect;
- long polls.

---

# 23. History

History V2 is the modern production history authority.

The Vue app should call it directly.

Preserve:

- Generate Original != Retry Original;
- Single Resume != Original;
- Experiment retry is per-cell;
- configured-folder Export != browser Download;
- immutable execution parameters are not resent by the browser for replay actions.

Do not recreate legacy bridge/fixture production architecture unless a real current consumer requires it.

---

# 24. Golden

Keep distinct:

1. normal selected GPU;
2. selected Golden profile;
3. deploy-baked Golden region/GPU configuration;
4. active per-profile GPU order A/B;
5. Golden deploy status.

Active A/B switches the already-deployed function used by the next run and does not itself require redeploy.

`skip_plan_validation` is not a universal “ignore everything” flag. Preserve current semantics, including model blockers where applicable.

---

# 25. “Sync” terminology

Keep separate:

1. **inventory reconciliation** — local/remote model/node inventory;
2. **custom-node publication/rebuild** — its own backend operation/status identity;
3. **cross-tab invalidation** — browser BroadcastChannel notice.

Do not build one universal `sync()` abstraction.

---

# 26. Reusable UI

Likely shared components:

- StudioViewer
- ImageCard
- ImageGrid
- ImageStrip
- CompareViewer
- HistoryPicker
- WorkflowPicker
- ModelPicker
- StatusBadge
- EmptyState
- ErrorState
- Search/filter primitives
- Settings field/section primitives
- optional operations/activity UI driven by `operationStore`

Good:

```text
ImageCard
  ├── ImageGrid
  └── ImageStrip
```

Bad:

```text
UniversalImageCollection with 25 behavior props
```

---

# 27. Playground target

```text
PlaygroundPage
├── PlaygroundHeader
│   ├── ModeSwitcher
│   ├── SubtoolSwitcher
│   ├── WorkflowPicker
│   ├── VersionPicker
│   └── Saved Workflow / Preset Picker
├── Inspector
├── ImageStage
├── RecentRunsStrip
└── RunBar
```

Generate:

- Text
- References
- Layout
- Sketch
- Guidance

Edit:

- Text
- Select/Inpaint
- Expand
- Sketch

Post:

- Adjust
- Color
- Detail
- Effects
- Crop
- Heal
- Upscale placeholder

---

# 28. Styling isolation

The Vue app imports neither:

- `studio-styles.js`
- `testing-styles.js`

and does not copy their selectors as a visual compatibility layer.

Use:

- Tailwind utility prefix;
- no global Tailwind Preflight reset against ComfyUI;
- Studio-scoped design tokens;
- no broad global element selectors.

Do not add Shadow DOM unless normal isolation proves inadequate.

---

# 29. Portal strategy

Create a Studio-contained portal target:

```html
<div data-comfymodal-studio>
  <div data-studio-app></div>
  <div data-studio-portals></div>
</div>
```

Configure shadcn/Reka portals to target the Studio portal node.

This is a target element/configuration, not a portal-management system.

---

# 30. Vite / ComfyUI integration

This is a high-risk Phase-1 proof.

ComfyUI custom-node `WEB_DIRECTORY` discovery can auto-import `.js` extension assets. Do not casually dump a normal Vite multi-chunk `.js` build into `web/`.

Preferred proof:

```text
web/modal-testing.js          # tiny normal ComfyUI extension
web/assets/studio/*.mjs       # explicitly imported Vue entry/chunks
web/assets/studio/studio.css  # explicitly loaded once
```

or another equally simple proven non-auto-discovered arrangement.

The host explicitly imports one stable Vue entry.

Production must not require a Vite dev server.

Do not invent an asset-manifest framework unless stable filenames/chunk configuration cannot solve it.

---

# 31. Docs

Docs remain separate from the five Studio routes.

Create a fresh flow-oriented placeholder shell later:

```text
Start Here
Use Images
Organize
Review
Manage Modal
Settings
Help
```

Do not write full docs before the Vue UI stabilizes.

---

# 32. Testing philosophy

Historical exhaustive tests/reports are behavioral oracles, not DOM/CSS freezes.

Preserve semantics around:

- routing/back-forward;
- modal/focus/inert behavior;
- wizard graph interaction;
- upload/source races;
- run identity;
- queue intent freeze;
- generation failure;
- History actions;
- Experiment cancel/resume/retry;
- workspace switching;
- cross-tab convergence;
- Settings authority;
- canvas compatibility;
- responsive usability;
- Phase-13 canvas rule.

Prefer semantic/accessibility selectors and a small set of stable meaningful `data-testid`s.

Chrome DevTools MCP is the primary live UI acceptance path when available.
Automated tests supplement it.
Do not use agent-browser.

---

# 33. Implementers MAY decide

Without owner approval, implementers may choose:

- exact Vue component filenames;
- whether a small component remains inline;
- exact Tailwind token values/spacing;
- which shadcn components directly fit;
- local computed vs Pinia getter;
- AbortController vs token details inside `latest.ts`;
- whether a tiny API file combines with a neighbor;
- responsive breakpoints;
- internal TS names that do not change product/backend vocabulary.

---

# 34. Implementers MAY NOT decide

Without explicit owner approval, implementers may not:

- add/remove Studio pages;
- change public Studio URL semantics;
- alter execution methods;
- invent Auto method selection;
- redesign backend execution;
- alter queue/run snapshot semantics;
- change History replay semantics;
- replace History V2;
- rewrite backend endpoints merely for frontend neatness;
- remove canvas compatibility before remaining consumers are migrated;
- persist image pixels/Compare pairs into durable shared state;
- make saved workflow presets capture images/pixels;
- make preset output overrides mutate global Settings;
- add model/provider-specific frontend branches without contract evidence;
- implement Upscale;
- turn `operationStore` into a universal executor;
- turn async primitives into an async framework;
- add a generic repository/service/adapter chain;
- create a second state authority;
- merge semantically distinct sync systems;
- reinterpret Golden A/B as ordinary GPU selection;
- weaken model blockers because `skip_plan_validation` is enabled;
- add Experiment retry-all.

---

# 35. Migration phases

## Phase 0 — contract freeze

**COMPLETE.** This document is the result.

## Phase 1 — substrate + shared plumbing proof

Implement:

- Vue 3 + TypeScript + Pinia;
- Vue Router preserving current hash contract;
- Tailwind 4;
- shadcn-vue / Reka;
- Lucide;
- Zod;
- VueUse;
- one Vue root;
- six minimal stores;
- narrow `operationStore`;
- `async/latest.ts`;
- `async/polling.ts`;
- explicit persistence helper;
- Studio portal root;
- Vite static-build proof under ComfyUI;
- host open/close/mount proof;
- zero old Studio CSS imports.

Do not port major product pages in Phase 1.
Use a minimal representative shell/page to prove routing, styling, Pinia, portals, host lifecycle and build delivery.

## Phase 2 — Settings + Manage Modal

Port real server-backed Settings and infrastructure.

Use this phase to prove:

- `operationStore` with real deployment/download/sync operations;
- latest-task cancellation where applicable;
- polling helper;
- canvas compatibility projection;
- cross-tab invalidation.

## Phase 3 — History + shared media

Port History V2 and shared media primitives.
Eliminate duplicated Playground Generation cache when shared History ownership is ready.

## Phase 4 — Workflows + Models + Setup Wizard

Port workflow/version/mapping/dependency/compatibility/portability/presets and graph-binding wizard.

## Phase 5 — Playground

Port in behavioral slices:

1. shell + Text + core execution;
2. recent runs;
3. References;
4. Layout;
5. Select/Inpaint + Expand;
6. Sketch;
7. Guidance;
8. Post;
9. Queue/Experiment;
10. Phase-12 saved workflow state.

## Phase 6 — Docs placeholders

Create new docs shell and flow-oriented placeholder content.

## Phase 7 — cutover + retirement

Switch production Studio to Vue, run full behavioral acceptance, then perform a reachability audit and delete obsolete frontend/state/CSS systems.

Backend endpoint retirement is a separate evidence-based cleanup.

---

# 36. Existing logic to reuse/port preferentially

Do not translate giant DOM modules wholesale.

Prefer framework-independent logic that already solves real problems:

- run model/controller/adapters;
- run normalization;
- workflow execution request building;
- Guidance mapping;
- Phase-12 preset snapshot/apply logic;
- Layout coordinate/serialization logic;
- Sketch session/geometry logic;
- History normalization/action-state helpers;
- graph-binding discovery/capture logic where practical;
- Post-processing math/engine behavior where practical.

Rule:

> **Port the behavior engine; replace the presentation and ownership shell.**

---

# 37. Existing systems expected to disappear when replaced

After the matching Vue owner exists and reachability is proven, candidates include:

- Playground full run-result localStorage cache;
- same-tab recent-run deletion bus;
- workflow handoff localStorage used only to bridge old separate pages;
- duplicate page-specific entity caches;
- duplicate polling loops replaced by `polling.ts`;
- duplicate stale-request counters replaced by `latest.ts`;
- duplicate operation busy/progress records replaced by `operationStore`;
- raw page-level fetch wrappers replaced by domain APIs;
- old Studio visual CSS;
- old shell/page renderers after cutover;
- dead legacy frontend modules already proven unreachable.

Do not delete canvas integration modules simply because Studio moved to Vue.

---

# 38. Target source shape

```text
frontend/
└── src/
    ├── app/
    │   ├── StudioApp.vue
    │   └── router/
    ├── stores/
    │   ├── infrastructure.ts
    │   ├── workflows.ts
    │   ├── history.ts
    │   ├── playground.ts
    │   ├── settings.ts
    │   └── operations.ts
    ├── api/
    │   ├── http.ts
    │   ├── assets.ts
    │   ├── runs.ts
    │   ├── history.ts
    │   ├── workflows.ts
    │   ├── infrastructure.ts
    │   ├── settings.ts
    │   └── golden.ts
    ├── async/
    │   ├── latest.ts
    │   └── polling.ts
    ├── persistence/
    │   └── persistence.ts
    ├── compatibility/
    │   └── canvas.ts
    ├── components/
    ├── pages/
    └── docs/
```

This is a target shape, not a requirement to create empty files/directories before they contain useful code.

---

# 39. Phase-0 conclusion

The right architecture for this repo is not “avoid systems.”

It is:

> **Create a small number of obvious shared systems that let us delete the large number of bespoke systems already accumulated.**

Approved shared infrastructure:

- Vue Router for navigation ownership;
- six Pinia stores, including a deliberately narrow `operationStore`;
- Zod at trust/persistence boundaries;
- VueUse for repeated browser/Vue mechanics;
- `latest.ts` for latest-read-wins races;
- `polling.ts` for polling mechanics;
- explicit persistence;
- tiny cross-tab invalidation;
- one-way canvas compatibility projection.

Everything else must earn its existence by deleting more complexity than it introduces.
