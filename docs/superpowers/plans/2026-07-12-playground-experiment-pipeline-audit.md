# Playground and Experiment Pipeline Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Studio Playground and Experiment pipelines and add deterministic Playwright coverage plus an opt-in live Modal end-to-end test with owned preset cleanup.

**Architecture:** Playwright Test launches isolated Chromium instances against a running ComfyUI frontend. The required project intercepts `/comfymodal/*` at the browser boundary with a stateful mock; the serial live project uses the real backend and Modal only when explicitly enabled. Backend contract tests remain Python `unittest` tests, and production fixes are limited to defects demonstrated by those tests.

**Tech Stack:** Python 3 `unittest`, JavaScript ES modules, `@playwright/test` 1.60, ComfyUI frontend extension APIs, aiohttp routes, Modal runtime.

**Constraint:** Preserve all pre-existing working-tree changes. Do not commit unless the user explicitly requests a commit.

---

## File Structure

- Create `package.json` — project-local Playwright dependency and scripts.
- Create `playwright.config.mjs` — isolated mocked and serial opt-in live projects.
- Create `tests/browser/studio-fixtures.mjs` — Studio launcher, console guard, ownership IDs, API cleanup, workflow-derived payloads.
- Create `tests/browser/studio-mock-api.mjs` — stateful snapshot, preset, run, experiment, history, and asset mock.
- Create `tests/browser/studio-playground.spec.mjs` — deterministic Playground behavior.
- Create `tests/browser/studio-experiment.spec.mjs` — deterministic Experiment behavior.
- Create `tests/browser/studio-live.spec.mjs` — opt-in real Modal Playground and Experiment smoke.
- Modify `tests/browser/modal_testing_suite_smoke.mjs` — align stale labels/selectors and headless configuration.
- Modify `web/studio-playground.js` — polling timeout/unmount cleanup and any test-proven Playground repair.
- Modify `web/studio-experiment-mode.js` — detached-editor guard and any test-proven Experiment repair.
- Modify `__init__.py` — route-level validation only if required after adapter tests fail.
- Modify `studio_run_adapter.py` — reusable preset/schema validation helpers and test-proven runtime repairs.
- Modify `tests/test_studio_runtime.py` — backend regression coverage.
- Modify `tests/test_studio_backend.py` — focused structural assertions for frontend lifecycle safeguards.
- Preserve and extend `tests/test_studio_timing_integration.py` only when a timing regression is demonstrated.

---

### Task 1: Establish the isolated Playwright runner

**Files:**
- Create: `package.json`
- Create: `playwright.config.mjs`
- Modify: `tests/browser/modal_testing_suite_smoke.mjs`

- [ ] **Step 1: Record the baseline without changing files**

Run:

```powershell
python run_tests.py tests.test_studio_runtime tests.test_studio_backend tests.test_studio_timing_integration
node tests/browser/modal_testing_suite_smoke.mjs
```

Expected: Python results are recorded exactly. The old browser smoke either fails because `COMFYUI_URL` is unset or exposes stale `Modal Testing` / `Open Testing Suite` / legacy tab expectations.

- [ ] **Step 2: Add the project-local test dependency and scripts**

Create `package.json`:

```json
{
  "name": "comfyui-modal",
  "private": true,
  "type": "module",
  "scripts": {
    "test:playwright": "playwright test --project=mocked",
    "test:playwright:live": "playwright test --project=live",
    "test:playwright:smoke": "node tests/browser/modal_testing_suite_smoke.mjs"
  },
  "devDependencies": {
    "@playwright/test": "^1.60.0"
  }
}
```

- [ ] **Step 3: Install without downloading another browser while shared browser work is active**

Run:

```powershell
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1"; npm install
```

Expected: `package-lock.json` is created and `@playwright/test` resolves locally. No shared Playwright MCP browser is touched.

- [ ] **Step 4: Configure isolated projects**

Create `playwright.config.mjs`:

```javascript
import { defineConfig } from "@playwright/test";

const baseURL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

export default defineConfig({
  testDir: "./tests/browser",
  testMatch: /studio-.*\.spec\.mjs/,
  outputDir: "test-results",
  fullyParallel: false,
  workers: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  use: {
    baseURL,
    headless: process.env.PLAYWRIGHT_HEADLESS !== "0",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure"
  },
  projects: [
    {
      name: "mocked",
      testIgnore: /studio-live\.spec\.mjs/
    },
    {
      name: "live",
      testMatch: /studio-live\.spec\.mjs/,
      workers: 1,
      timeout: Number(process.env.COMFYMODAL_LIVE_TIMEOUT_MS || 900_000)
    }
  ]
});
```

- [ ] **Step 5: Repair the standalone smoke selectors**

Update `tests/browser/modal_testing_suite_smoke.mjs` to use `Modal GPU`, `Open Studio`, and Studio tabs `Playground`, `History`, `Backend`, `Settings`; launch with:

```javascript
const headless = process.env.PLAYWRIGHT_HEADLESS !== "0";
const browser = await chromium.launch({ headless });
```

Keep `try/finally` browser cleanup.

- [ ] **Step 6: Verify configuration discovery**

Run:

```powershell
npx playwright test --list
```

Expected: configuration loads successfully; later spec files may not exist yet, so zero tests is acceptable at this step.

---

### Task 2: Build stateful Studio fixtures and owned cleanup

**Files:**
- Create: `tests/browser/studio-fixtures.mjs`
- Create: `tests/browser/studio-mock-api.mjs`

- [ ] **Step 1: Write the fixture contract first**

Create exports in `tests/browser/studio-fixtures.mjs` with these exact interfaces:

```javascript
import { expect } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs/promises";

export function createOwnerPrefix() {
  return `pw-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
}

export function createOwnedRecords() {
  return { snapshotIds: [], presetIds: [] };
}

export function installConsoleGuard(page) {
  const errors = [];
  page.on("pageerror", error => errors.push(`pageerror: ${error.message}`));
  page.on("console", message => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  return () => expect(errors, errors.join("\n")).toEqual([]);
}

export async function openStudio(page) {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  const sidebar = page.getByText("Modal GPU", { exact: false }).first();
  await sidebar.waitFor();
  await sidebar.click();
  await page.getByRole("button", { name: "Open Studio" }).click();
  await expect(page.getByTestId("studio-page")).toBeVisible();
}

export async function createOwnedSnapshotAndPresets(page, prefix, count = 1) {
  return page.evaluate(async ({ ownerPrefix, presetCount }) => {
    const snapshotPayload = {
      name: `${ownerPrefix}-snapshot`,
      compatibleFeatures: ["txt2img"],
      graphJson: { nodes: [], links: [] },
      apiPromptJson: {
        "3": { class_type: "KSampler", inputs: { seed: 42, steps: 10 } },
        "9": { class_type: "SaveImage", inputs: { images: [] } }
      },
      nodeBindings: {
        prompt: { kind: "widget", nodeId: "3", widgetName: "text" },
        output: { kind: "output", nodeId: "9" }
      },
      outputNodeId: "9",
      source: "playwright"
    };
    const snapshotResponse = await fetch("/comfymodal/studio/snapshots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(snapshotPayload)
    });
    const snapshotBody = await snapshotResponse.json();
    const presets = [];
    for (let index = 0; index < presetCount; index += 1) {
      const response = await fetch("/comfymodal/studio/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label: `${ownerPrefix}-preset-${index + 1}`,
          snapshotId: snapshotBody.snapshot.id,
          compatibleFeatures: ["txt2img"],
          defaults: { prompt: "owned prompt", steps: 10 },
          sourceType: "manual"
        })
      });
      presets.push((await response.json()).preset);
    }
    return { snapshot: snapshotBody.snapshot, presets };
  }, { ownerPrefix: prefix, presetCount: count });
}
```

Also export `cleanupOwnedRecords(request, baseURL, owned)` that deletes presets before snapshots and ignores only 404 responses:

```javascript
export async function cleanupOwnedRecords(request, baseURL, owned) {
  const failures = [];
  for (const id of [...owned.presetIds].reverse()) {
    const response = await request.delete(`${baseURL}/comfymodal/studio/presets/${encodeURIComponent(id)}`);
    if (!response.ok() && response.status() !== 404) failures.push(`preset ${id}: ${response.status()}`);
  }
  for (const id of [...owned.snapshotIds].reverse()) {
    const response = await request.delete(`${baseURL}/comfymodal/studio/snapshots/${encodeURIComponent(id)}`);
    if (!response.ok() && response.status() !== 404) failures.push(`snapshot ${id}: ${response.status()}`);
  }
  expect(failures).toEqual([]);
}
```

- [ ] **Step 2: Add a workflow-derived live snapshot builder**

In `studio-fixtures.mjs`, read `clean_workflow.json`, locate one `KSampler`, two `CLIPTextEncode` nodes, and one `SaveImage`, then return a snapshot request with bindings for `prompt`, `negative_prompt`, `seed`, `steps`, `guidance`, `sampler`, `scheduler`, `denoise`, and `output`. Throw a descriptive error if any required node is absent; do not use existing user snapshots.

- [ ] **Step 3: Implement the stateful route mock**

`installStudioMockApi(page, options)` in `studio-mock-api.mjs` must own these maps/arrays:

```javascript
const state = {
  snapshots: new Map(),
  presets: new Map(),
  experiments: new Map(),
  history: [],
  calls: [],
  pollCounts: new Map()
};
```

Intercept `**/comfymodal/**` before navigation and implement:

- snapshot/preset list, create, patch, and soft-delete
- `POST /studio/run`
- `POST /studio/experiment`
- `GET /experiments/{id}` with waiting → running → completed or failed transitions
- `GET /run-history`
- annotation patch
- asset and Studio output responses using a one-pixel PNG buffer

Every unhandled `/comfymodal/` request must return status 599 with `{status:"error", message:"Unhandled mock route: METHOD PATH"}` and append to `state.calls`.

- [ ] **Step 4: Verify fixture modules load**

Run:

```powershell
node -e "Promise.all([import('./tests/browser/studio-fixtures.mjs'),import('./tests/browser/studio-mock-api.mjs')]).then(()=>console.log('ok'))"
```

Expected: `ok`.

---

### Task 3: Add deterministic Playground coverage

**Files:**
- Create: `tests/browser/studio-playground.spec.mjs`
- Test: `web/studio-playground.js`
- Test: `web/studio-run-normalizer.js`

- [ ] **Step 1: Write a failing owned-preset success test**

Use `test.beforeEach` to install the mock before `openStudio(page)`. The test must:

```javascript
test("Playground creates, runs, renders timing, and deletes owned presets", async ({ page }) => {
  const api = await installStudioMockApi(page, { terminal: "completed" });
  await openStudio(page);
  const prefix = createOwnerPrefix();
  const { snapshot, presets } = await createOwnedSnapshotAndPresets(page, prefix, 1);
  const preset = presets[0];

  await page.reload({ waitUntil: "domcontentloaded" });
  await openStudio(page);
  await page.getByTestId("backend-select").selectOption(preset.id);
  await page.getByTestId("input-prompt").fill("playwright owned prompt");
  await page.getByTestId("run-btn").click();

  await expect(page.getByTestId("canvas-output")).toBeVisible();
  await expect(page.getByTestId("timing-card")).toContainText("End-to-End Total");
  await expect(page.getByTestId("timing-card")).toContainText("Sampling");
  expect(api.lastRunRequest().controls.prompt).toBe("playwright owned prompt");

  await page.evaluate(async ({ presetId, snapshotId }) => {
    await fetch(`/comfymodal/studio/presets/${encodeURIComponent(presetId)}`, { method: "DELETE" });
    await fetch(`/comfymodal/studio/snapshots/${encodeURIComponent(snapshotId)}`, { method: "DELETE" });
  }, { presetId: preset.id, snapshotId: snapshot.id });
  expect(api.activePresets()).toEqual([]);
});
```

Adapt only locator syntax required by the actual rendered shell; retain behavioral assertions.

- [ ] **Step 2: Run it to verify it fails for a specific reason**

Run:

```powershell
npx playwright test tests/browser/studio-playground.spec.mjs --project=mocked
```

Expected: FAIL because fixture details or production behavior are not yet complete, not because ComfyUI is unavailable. If ComfyUI is unavailable, start it outside this test process and rerun.

- [ ] **Step 3: Add Playground failure and malformed-output cases**

Add tests proving:

- an HTTP error leaves `[data-testid="run-btn"]` enabled and exposes the server message
- `completed_with_failures` renders an error, not an empty success
- a completed event without an asset/output does not create `canvas-output`
- advanced timing diagnostics expand without duplicate Sampling stages
- test-owned soft deletion removes the option while unrelated preset IDs remain

- [ ] **Step 4: Add polling lifecycle coverage using Playwright Clock**

Install `page.clock` before opening Studio, return an unknown empty experiment forever, click Run, advance past five minutes, and assert an actionable timeout. Navigate to History during another in-progress run, advance time, and assert no further status requests occur after unmount.

```javascript
await page.clock.install({ time: new Date("2026-07-12T00:00:00Z") });
await page.clock.fastForward(300_001);
await expect(page.getByText(/timed out/i)).toBeVisible();
```

- [ ] **Step 5: Run all Playground cases and preserve failures as evidence**

Run:

```powershell
npx playwright test tests/browser/studio-playground.spec.mjs --project=mocked --trace=retain-on-failure
```

Expected: tests exposing production defects fail; fixture-only failures are fixed in the fixture before proceeding.

---

### Task 4: Repair Playground polling and rendering defects

**Files:**
- Modify: `web/studio-playground.js:66-208`
- Modify: `tests/test_studio_backend.py`
- Modify: `web/studio-run-normalizer.js` only if a deterministic test demonstrates a duplicate or false-success defect
- Test: `tests/browser/studio-playground.spec.mjs`

- [ ] **Step 1: Add source-level regression assertions**

Append a `PlaygroundPollingLifecycleTests` class in `tests/test_studio_backend.py` asserting that the source contains a finite timeout, checks `container.isConnected`, clears `_pollTimer`, and catches polling errors.

- [ ] **Step 2: Run the focused Python test and confirm RED**

Run:

```powershell
python run_tests.py tests.test_studio_backend
```

Expected: the new lifecycle tests fail against the current `_startPolling` implementation.

- [ ] **Step 3: Implement one idempotent polling cleanup path**

Refactor `_startPolling` around this behavior:

```javascript
const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

function _stopPolling(container, pollTimer) {
  if (pollTimer) clearInterval(pollTimer);
  if (container && container._pollTimer === pollTimer) container._pollTimer = null;
}
```

Before starting, stop any existing `container._pollTimer`. On every tick:

1. stop immediately when `!container.isConnected`
2. transition to error with `Run status timed out after 5 minutes.` once the deadline passes
3. wrap `getStudioRunStatus` in `try/catch`; preserve waiting during transient errors but let the deadline terminate it
4. route every terminal branch through `_stopPolling`

- [ ] **Step 4: Make normalization reject false success only if the test proves it**

If malformed completed payloads currently normalize as success, change `normalizeStudioRun()` so terminal success without output remains a completed metadata record but does not fabricate an image; do not convert genuine metadata-only history entries into errors.

- [ ] **Step 5: Re-run focused browser and Python tests**

Run:

```powershell
python run_tests.py tests.test_studio_backend tests.test_studio_timing_integration
npx playwright test tests/browser/studio-playground.spec.mjs --project=mocked
```

Expected: PASS.

---

### Task 5: Add deterministic Experiment coverage and repair UI lifecycle

**Files:**
- Create: `tests/browser/studio-experiment.spec.mjs`
- Modify: `web/studio-experiment-mode.js:350-363`
- Modify: `tests/test_studio_backend.py`

- [ ] **Step 1: Write the Experiment success test first**

The test must create two runnable mock presets, select one as the base, enable Experiment mode, select the second preset, enable the Steps axis, enter two values, and submit one unified request.

Assert:

```javascript
await expect(page.getByTestId("experiment-mode")).toBeVisible();
await expect(page.getByTestId("matrix-summary")).toContainText(/runs/i);
await page.getByTestId("run-experiment-btn").click();
expect(api.lastExperimentRequest().presetIds).toHaveLength(2);
expect(api.lastExperimentRequest().experiment.axes.steps.values).toEqual([10, 20]);
await expect(page.getByText(/Experiment submitted/i)).toBeVisible();
```

- [ ] **Step 2: Add failure and eligibility tests**

Cover:

- fewer than two canonical preset IDs disables submission
- duplicate base/compare IDs are de-duplicated
- an axis unsupported by either preset is disabled and omitted from the request
- backend `completed_with_failures` / `cell.failed` produces visible failure state
- rapidly toggling an axis while re-rendering does not leave duplicate detached editors
- cleanup archives only the two test-created presets and owned snapshot(s)

- [ ] **Step 3: Run the Experiment spec and confirm the detached-editor case fails**

Run:

```powershell
npx playwright test tests/browser/studio-experiment.spec.mjs --project=mocked
```

Expected: the lifecycle race fails or logs a DOM error against the current deferred insertion.

- [ ] **Step 4: Add the minimal connection guard**

Change the deferred callback to:

```javascript
setTimeout(() => {
  if (!controlEl.isConnected) return;
  const parent = controlEl.parentNode;
  if (!parent || !parent.isConnected) return;
  if (parent.nextSibling) parent.parentNode.insertBefore(editor, parent.nextSibling);
  else parent.parentNode.appendChild(editor);
}, 0);
```

Use the actual intended sibling container after verifying DOM hierarchy; the editor must not be appended inside the control group accidentally.

- [ ] **Step 5: Add a source regression assertion and re-run**

Assert `controlEl.isConnected` and parent connectivity in `tests/test_studio_backend.py`, then run:

```powershell
python run_tests.py tests.test_studio_backend
npx playwright test tests/browser/studio-experiment.spec.mjs --project=mocked
```

Expected: PASS with no console errors.

---

### Task 6: Harden backend preset/schema validation and failed-cell timing

**Files:**
- Modify: `tests/test_studio_runtime.py`
- Modify: `studio_run_adapter.py`
- Modify: `__init__.py:6218-6352`
- Modify: `tests/test_studio_timing_integration.py` only if needed

- [ ] **Step 1: Add failing adapter tests for missing and heterogeneous presets**

Add tests proving:

1. a run referencing a missing/archived snapshot returns the adapter error rather than attempting schema derivation
2. an experiment validates defaults and every axis value against every selected preset schema
3. returned validation errors include `presetId` so the UI can identify the incompatible preset
4. failed-cell timing survives `LocalRemoteInvoker → cell.failed → Studio history`
5. a remote completion/materialization exception is logged and becomes a terminal failure event instead of being swallowed

Use temporary `.studio_snapshots.json` and `.studio_presets.json` files; do not load user data.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
python run_tests.py tests.test_studio_runtime tests.test_studio_timing_integration
```

Expected: new missing-preset and multi-schema assertions fail; existing timing tests establish whether the current timing work already satisfies item 4.

- [ ] **Step 3: Add a reusable validation helper**

In `studio_run_adapter.py`, add a pure helper with this contract:

```python
def validate_studio_request_controls(
    preset_ids: list[str],
    feature_id: str,
    controls: dict,
    axes: dict,
    node_dir: str | Path,
) -> list[dict]:
    """Return preset-scoped load/schema errors for every selected preset."""
```

For each preset ID:

- call `load_preset_and_snapshot`
- on failure append `{"presetId": preset_id, "controlId": "", "message": error}`
- derive that snapshot's schema
- validate shared controls with `strict_unknown_rejection=False`
- validate each enabled axis value independently
- attach `presetId` to each returned error

- [ ] **Step 4: Route both endpoints through the helper**

In `__init__.py`:

- `/studio/run` calls the helper with `[preset_id]`, `controls`, and `{}`
- `/studio/experiment` calls it with every `preset_id`, defaults, and axes
- validation errors return HTTP 400 with the existing message plus `errors`
- unexpected exceptions remain HTTP 500 and logged

Remove the current first-valid-preset shortcut at `__init__.py:6315-6320`.

- [ ] **Step 5: Fix only timing failures demonstrated by the tests**

If failed-cell timing is dropped, replace the fragile `hasattr(self._invoker, "_drive")` decision in `experiment_runner.py` with an explicit invoker capability/property or a single event-emission owner. Ensure exactly one `cell.failed` event is emitted and `timing_payload` is preserved.

If the remote-event callback still contains a blanket `except Exception: pass`, replace it with logged, structured failure handling. Preserve lease validation, emit one terminal failure event with the original error text, and add a regression test that forces output materialization to raise.

- [ ] **Step 6: Verify backend contracts**

Run:

```powershell
python run_tests.py tests.test_studio_runtime tests.test_studio_timing_integration tests.test_integration_acceptance
```

Expected: PASS.

---

### Task 7: Add the opt-in live Modal test with guaranteed owned cleanup

**Files:**
- Create: `tests/browser/studio-live.spec.mjs`
- Use: `clean_workflow.json`
- Use: `tests/browser/studio-fixtures.mjs`

- [ ] **Step 1: Add an explicit skip gate**

Wrap the live test in this suite:

```javascript
const liveEnabled = process.env.COMFYMODAL_LIVE_E2E === "1";
test.describe("live Studio pipelines", () => {
  test.describe.configure({ mode: "serial" });
  test.skip(!liveEnabled, "Set COMFYMODAL_LIVE_E2E=1 to run real Modal generation");

  test("runs Playground and Experiment with owned records", async ({ page, request, baseURL }) => {
    const owned = createOwnedRecords();
    try {
      await createLiveSnapshotAndPresets(request, baseURL, owned, 2);
      await runLivePlayground(page, owned.presetIds[0]);
      await runLiveExperiment(page, owned.presetIds);
    } finally {
      await cleanupOwnedRecords(request, baseURL, owned);
    }
  });
});
```

Require `COMFYUI_URL` only when live execution is enabled.

- [ ] **Step 2: Create records through real Studio APIs**

Use `request.post` to create one snapshot from `clean_workflow.json`, then two uniquely labeled presets referencing that snapshot. Record every returned ID immediately in `owned` before the next operation.

- [ ] **Step 3: Run one real Playground generation through the UI**

Open Studio, select the first owned preset, use a short deterministic prompt and the smallest safe steps value supported by the snapshot schema, click Run, and wait for a terminal state up to `COMFYMODAL_LIVE_TIMEOUT_MS`.

Assert:

- no visible error state
- `canvas-output` is visible and has a `/comfymodal/assets/` or `/comfymodal/studio/outputs/` URL
- timing card has a finite End-to-End value
- History contains the run

- [ ] **Step 4: Run the smallest UI-valid Experiment**

Enable Experiment mode, select the second owned preset, keep one prompt and one value per control/axis, submit, and assert the unified request reaches a terminal state with two completed cells (one checkpoint per preset) and no failed cells.

- [ ] **Step 5: Guarantee teardown in `finally`**

Wrap record creation and both runs:

Use the exact `try/finally` structure from Step 1. Implement `createLiveSnapshotAndPresets`, `runLivePlayground`, and `runLiveExperiment` in `studio-live.spec.mjs`; each helper must throw on a non-2xx response or visible terminal error.

After cleanup, list active presets/snapshots and assert none of the captured IDs are returned. Never delete by broad name matching.

- [ ] **Step 6: Verify skip behavior without credentials**

Run:

```powershell
npx playwright test tests/browser/studio-live.spec.mjs --project=live
```

Expected: one clearly reported skip when `COMFYMODAL_LIVE_E2E` is not `1`.

- [ ] **Step 7: Run live only when the user environment is ready**

Run:

```powershell
$env:COMFYUI_URL="http://127.0.0.1:8188"
$env:COMFYMODAL_LIVE_E2E="1"
npx playwright test tests/browser/studio-live.spec.mjs --project=live
```

Expected: PASS, or an actionable real runtime defect with all owned presets/snapshots still archived by teardown.

---

### Task 8: Complete the audit, review, and full verification

**Files:**
- Review all changed files from Tasks 1-7
- Test: all Python and browser suites

- [ ] **Step 1: Run static change checks**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; all pre-existing user changes remain present.

- [ ] **Step 2: Run the complete Python suite**

Run:

```powershell
python run_tests.py
```

Expected: PASS. Investigate every failure; do not label unrelated failures without reproducing the baseline.

- [ ] **Step 3: Run deterministic Playwright coverage in its own browser processes**

Run:

```powershell
npm run test:playwright
```

Expected: Playground and Experiment specs pass with one worker and no interaction with the shared Playwright MCP session.

- [ ] **Step 4: Run standalone smoke compatibility**

Run:

```powershell
$env:COMFYUI_URL="http://127.0.0.1:8188"
$env:PLAYWRIGHT_HEADLESS="1"
npm run test:playwright:smoke
```

Expected: PASS.

- [ ] **Step 5: Run a senior code review**

Route the final diff to the architecture/code-review specialist. Require review of:

- preset ownership and cleanup safety
- polling timer leaks and timeout behavior
- heterogeneous schema validation
- exactly-once failed-cell events and timing propagation
- mocked/live contract parity
- preservation of current timing changes

Resolve all high-confidence correctness findings and rerun affected tests.

- [ ] **Step 6: Verify the live suite or report its explicit skip**

Run the live project only when the opt-in variables and Modal credentials are available. Record whether it passed or skipped and confirm no owned IDs remain active.

- [ ] **Step 7: Final evidence collection**

Run:

```powershell
git diff --stat
git diff --check
```

Report exact test commands, pass/fail/skip counts, live-test status, defects fixed, and any remaining blocker. Do not claim full live functionality if the live project was skipped.
