# Frontend modernization plan: endpoints → store → Vue port

Status: **plan only — no implementation yet.** Execute in a new git worktree, page by page.
Prerequisite: backend phases 0A–0C landed (or explicitly deferred per page).

---

## 1. Endpoint consolidation ("universal list")

`web/studio-backend-api.js` is the catalog. Everything else must call it.

### 1a. Raw-fetch sites to migrate (all read-verified)

| Site | What it does | Migrate to |
|---|---|---|
| `web/studio-shell.js` `readDeployState`, `fetchSyncStatus`, `redeployFromSyncError`, `syncCustomNodes` | deploy/status, sync/status, POST /deploy, POST /sync/custom-nodes via raw `fetch` | `getDeployStatus` + `normalizeDeployStatus`, add `getSyncStatus` / `triggerSyncCustomNodes` to the catalog |
| `web/studio-settings.js:1019` `refreshDeployStatus`, `:1414` golden deploy POST | raw deploy status + deploy trigger with own status checks | `getDeployStatus`, `triggerGoldenProfileDeploy` |
| `web/studio-playground.js` playground redeploy reader (inline `getDeployStatus` wrapper) | ad-hoc `{state,message}` projection | `normalizeDeployStatus` (already imported in this file's scope) |
| `web/testing-api.js:8`, `testing-profiles.js:37`, `testing-results.js:34`, `testing-setup.js:109` | four near-identical `fetchJson` copies | one shared helper; keep throw-vs-null adapter variants where callers depend on them |
| `web/history-v2-repository.js:963` `_safeFetchJson`, `:1217` `_v2FetchJson` | null-returning vs throwing conventions | document both, route new code through the catalog |

### 1b. Transport contract

- One deadline/AbortSignal owner for browser HTTP (see operations audit G1/G4). Every catalog call gets a default timeout; callers may override, never remove.
- One error-extraction pure function in the catalog (replacing `syncResultText` / `syncServiceErrorText` / inline `message \|\| error` variants). Precedence must be pinned by test: string → `.message` → `.error` → nested `detail/message/code` → HTTP fallback.
- Rule going forward: **no raw `fetch` in page code.** AST-check in review (or extend `tests/test_safety_architecture.py` to frontend sources).

### 1c. Acceptance

- `node tests/studio_backend_operations_unit.mjs`, `studio_custom_node_sync_unit.mjs`, `studio_deploy_failure_tail_unit.mjs` green.
- Playwright baseline spec re-run: identical DOM + payload proofs (spec lives at `C:\Users\parla\AppData\Local\Temp\opencode\studio_baseline_spec.py`, artifacts per run-dir).

---

## 2. Vanilla state manager (zustand-shaped, no framework)

A ~100-line store; no dependency. Pattern per module:

```js
// web/studio-store.js
const listeners = new Set();
let state = { deploy: {...}, sync: {...}, operations: {...} };
export function getState() { return state; }
export function setState(patch) { state = {...state, ...patch}; emit(); }
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
// Selectors derive banners/buttons — pages never read raw state.
export function selectSyncBanner(s) { ... }
```

### 2a. Modules (in this order)

1. **operations** — job records `{id, kind, state, progress, result}`, replaces per-button busy flags + poll loops. Pairs with backend `operations.py` when it lands; until then wraps existing endpoints.
2. **deploy** — single deploy-status holder; replaces shell locals (`lastSyncError/Result/Data`, `redeployInFlight`, `syncInFlight`) and deployment-page `state.status`.
3. **sync** — sync snapshot + validity (feeds 0B observation work).

### 2b. Adoption order (page by page, each independently shippable)

settings → backend → history → workflows → playground (last — 15k lines, most tangled state).

Each page migration: wire UI events to store actions, replace direct DOM writes with subscriptions, keep all `data-testid`s stable, keep Playwright spec green before/after.

### 2c. Acceptance per page

- Corresponding `studio_*_unit.mjs` suites green.
- Playwright page spec: same DOM assertions + same endpoint payloads as vanilla version.

---

## 3. Vue port (new worktree)

### 3a. Worktree setup

```text
git worktree add ../comfyui-modal-vue -b vue-port
```

Port work happens **only** there. It tracks the same backend; page migrations merge back one page at a time. Never mix vanilla page edits and Vue port edits in one diff.

### 3b. Rules

- **Strangler, not rewrite.** Vanilla shell keeps routing, overlay lifecycle, ComfyUI extension registration (`web/modal-testing.js`), wizard handoffs. Each tab body becomes one Vue app root.
- **Vue 3, SFC optional.** Match ComfyUI core (Vue) so future integration is cheap. No Vuex/Pinia at first — the vanilla store (§2) ports 1:1 to composables (`useDeployStatus`, `useSyncStatus`, `useOperations`).
- **Contract freeze.** Before porting any page, record: all its `data-testid`s, custom events in/out, `window.*` bridges, poll cadences, and exact request/response shapes. The port must preserve all of them; diffs need explicit justification + test updates.
- **Pure helpers first.** Extract framework-free logic to shared modules imported by both old and new UI; existing `studio_*_unit.mjs` suites become the port safety net.
- **Order:** settings → backend → history → workflows → playground.

### 3c. Per-page checklist

1. Contract inventory recorded.
2. Playwright before-artifacts captured on vanilla.
3. Vue implementation behind the same tab, same testids.
4. Unit suites + Playwright after-artifacts green; DOM and payload diffs reviewed line by line.
5. Merge that page; move to the next.

### 3d. Effort envelope

Prep (§1+§2 + backend 0A–0C): 2–4 weeks alongside roadmap. Port: settings/backend days each; history/workflows 1–2 weeks; playground 2–4 weeks (budget untangling, not translation). Total ~6–10 weeks part-time, shippable per page, zero flag days.

### 3e. Top risks

1. Behavioral drift in translation (reordered gating conditions, changed cadences) — answered by before/after Playwright specs.
2. ComfyUI extension-API coupling in shell/wizard files — hence shell stays vanilla.
3. Porting against unstable backend contracts — hence prerequisite 0A–0C.

---

## 4. Sequencing with the backend roadmap

1. §1 endpoint consolidation (feeds everything).
2. §2 store, operations module first (pairs with backend Phase 1).
3. Backend 0A → 0B → 0C.
4. §3 Vue port, page by page, against stabilized contracts.

Live acceptance per step (Playwright DOM + payload proofs). Local unit tests alone never ship a step.
