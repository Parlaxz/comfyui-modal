// Modal Studio — Shelf Experiment E2E Tests (Studio Workflow effort, leaf 1.2.2)
//
// Drives the Shelf experiment flow against the mocked backend:
// installStudioMockApi FIRST, then installWorkflowsMock (later routes take
// precedence for /comfymodal/studio/workflows*). Uses fresh Playwright Test
// page/context (never MCP/shared session).
//
// Covered contracts:
//   1. Explicit Experiment/Exit Experiment toggle; axis selectors only when
//      enabled.
//   2. Multi-Workflow comparison via the shared picker (mode "many").
//   3. Common compatible fields become axes (blue active, non-axis dimmed);
//      unique fields live in hidden per-Workflow sections (settable, never
//      axes).
//   4. Enter-to-create removable value pills with full text on hover; generic
//      Random/Increment/Decrement/Empty on integer and float fields.
//   5. Matrix run gating (workflows x axis values); results use the existing
//      experiment-v2 grid/output/History surfaces (no second result system).

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  openStudio,
} from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// ── Helpers ──────────────────────────────────────────────────────────────

// ── Primary-extension pin (mirrors studio-workflows.spec.mjs) ─────────
// The mocked suite has no Playwright webServer and navigates to the shared
// ComfyUI instance at 127.0.0.1:8188. Sibling lanes register the same
// extension name, so without pinning the page can load stale sibling code
// instead of this repo's primary copy at /extensions/comfyui-modal/.
async function pinPrimaryExtensionRequests(page) {
  // NOTE: regex, not a "**/extensions/*" glob — in Playwright glob syntax
  // "*" does not cross "/", so that glob would be a no-op.
  await page.route(/\/extensions\//, async (route) => {
    const reqUrl = new URL(route.request().url());
    const match = reqUrl.pathname.match(/^\/extensions\/([^/]+)\/(.*)$/);
    if (match && match[1] !== "comfyui-modal" && /modal/i.test(match[1])) {
      reqUrl.pathname = `/extensions/comfyui-modal/${match[2]}`;
      await route.continue({ url: reqUrl.toString() });
      return;
    }
    await route.continue();
  });
}

async function installMocks(page) {
  const api = await installStudioMockApi(page);
  const wfMock = await installWorkflowsMock(page);
  await pinPrimaryExtensionRequests(page);
  // The Shelf loads the model library on Workflow selection; the shared
  // mock has no /studio/models handler, so stub it here (registered last,
  // takes precedence, never recorded as unhandled).
  await page.route("**/comfymodal/studio/models**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", models: [] }),
    });
  });
  return { api, wfMock };
}

function portraitIds(wfMock) {
  const wf = wfMock.getWorkflow("Portrait Pro");
  expect(wf).toBeTruthy();
  const versions = wfMock.getVersions(wf.workflow_id);
  const current = versions.find((v) => String(v.workflow_version_id) === String(wf.latest_version_id));
  expect(current).toBeTruthy();
  return { workflowId: wf.workflow_id, current: current.workflow_version_id };
}

async function selectPortraitCurrent(page, wfMock) {
  const ids = portraitIds(wfMock);
  const wfSelect = page.locator('[data-testid="workflow-selector"]');
  await expect(wfSelect.locator(`option[value="${ids.workflowId}"]`)).toHaveCount(1, { timeout: 15000 });
  await wfSelect.selectOption(ids.workflowId);
  await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 15000 });
  const versionField = page.locator('[data-testid="workflow-version-selector"]');
  await expect(versionField.locator("option")).toHaveCount(0);
  await expect(versionField).toHaveAttribute("data-version-id", ids.current);
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="workflow-run-gating"]')).toContainText("Ready to run", { timeout: 15000 });
  return ids;
}

async function enableExperiment(page) {
  const toggle = page.locator('[data-testid="experiment-toggle"]');
  await expect(toggle).toBeVisible({ timeout: 10000 });
  if ((await toggle.textContent()).trim() === "Experiment") {
    await toggle.click();
  }
  await expect(page.locator('[data-testid="shelf-exp-panel"]')).toBeVisible({ timeout: 15000 });
}

// Create a second mapped Workflow with a SUBSET of roles (seed, steps,
// positive_prompt) via the mocked workflow API: import, then map a filtered
// candidate list. Returns { workflowId, versionId }.
async function createSubsetWorkflow(page) {
  const imported = await page.evaluate(async () => {
    const res = await fetch("/comfymodal/studio/workflows/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Subset Workflow", graph_json: { nodes: [] }, api_prompt_json: {} }),
    });
    return res.json();
  });
  expect(imported.status).toBe("ok");
  const versionId = imported.version.workflow_version_id;
  const workflowId = imported.workflow.workflow_id;

  const subset = await page.evaluate(async (vid) => {
    const candRes = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(vid)}/mapping/candidates`);
    const cand = await candRes.json();
    const entries = (cand.candidates.entries || []).filter((e) =>
      ["seed", "steps", "positive_prompt"].includes(e.semantic_role)
    );
    const mapRes = await fetch(`/comfymodal/studio/workflows/versions/${encodeURIComponent(vid)}/mapping`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_node_id: "6", entries }),
    });
    return { cand: cand.status, mapped: await mapRes.json() };
  }, versionId);
  expect(subset.cand).toBe("ok");
  expect(subset.mapped.status).toBe("ok");
  return { workflowId, versionId };
}

// Compare Portrait Pro with the subset Workflow via the many-mode picker.
async function compareWithSubset(page, subsetId) {
  await page.locator('[data-testid="shelf-exp-pick-btn"]').click();
  const dialog = page.locator('[data-testid="shelf-exp-picker-dialog"]');
  await expect(dialog).toBeVisible({ timeout: 10000 });
  const options = dialog.locator('[data-testid="workflow-picker-option"]');
  await expect(options).toHaveCount(3, { timeout: 10000 });
  await dialog.locator(`[data-testid="workflow-picker-option"][data-workflow-id="${subsetId}"]`).click();
  await dialog.locator('[data-testid="workflow-picker-confirm"]').click();
  await expect(page.locator(`[data-testid="shelf-exp-workflow-${subsetId}"]`)).toBeVisible({ timeout: 10000 });
}

// ── Tests ────────────────────────────────────────────────────────────────

test.describe("Studio Shelf Experiment", () => {
  test("1. toggle shows shelf panel; axis selectors only when enabled", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const guard = installConsoleGuard(page);

    try {
      await selectPortraitCurrent(page, wfMock);

      // Axis selectors exist only in experiment mode.
      expect(await page.locator('[data-testid="shelf-exp-panel"]').count()).toBe(0);
      const toggle = page.locator('[data-testid="experiment-toggle"]');
      expect((await toggle.textContent()).trim()).toBe("Experiment");
      await toggle.click();
      await expect(page.locator('[data-testid="shelf-exp-panel"]')).toBeVisible({ timeout: 10000 });
      expect((await toggle.textContent()).trim()).toBe("Exit Experiment");

      // Exit hides the panel again.
      await toggle.click();
      await expect(page.locator('[data-testid="shelf-exp-panel"]')).toHaveCount(0, { timeout: 10000 });
      expect((await toggle.textContent()).trim()).toBe("Experiment");

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      guard.dispose();
    }
  });

  test("2. multi-workflow comparison via picker; common axes and unique sections", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    const ids = await selectPortraitCurrent(page, wfMock);
    const subset = await createSubsetWorkflow(page);
    await enableExperiment(page);

    await compareWithSubset(page, subset.workflowId);
    await expect(page.locator('[data-testid="shelf-exp-workflow-list"]')).toContainText("Portrait Pro");

    // Common roles become axis toggles; activating one shows the blue state.
    await expect(page.locator('[data-testid="shelf-axis-seed"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="shelf-axis-steps"]')).toBeVisible();
    await expect(page.locator('[data-testid="shelf-axis-positive_prompt"]')).toBeVisible();
    await page.locator('[data-testid="shelf-axis-seed"]').click();
    const seedToggle = page.locator('[data-testid="shelf-axis-seed"]');
    await expect(seedToggle).toHaveAttribute("aria-pressed", "true");
    expect(await seedToggle.getAttribute("class")).toContain("is-axis");
    // Non-axis rows stay dimmed.
    expect(await page.locator('[data-testid="shelf-axis-steps"]').getAttribute("class")).toContain("is-dimmed");

    // Unique roles (cfg lives only in Portrait Pro) never become axes, and
    // sit in a hidden per-Workflow section with a settable input.
    expect(await page.locator('[data-testid="shelf-axis-cfg"]').count()).toBe(0);
    const unique = page.locator(`[data-testid="shelf-unique-${ids.workflowId}"]`);
    await expect(unique).toBeVisible();
    const uniqueBody = unique.locator(".comfymodal-studio-collapsible-content");
    expect(await uniqueBody.isHidden()).toBe(true);
    await unique.locator(`[data-testid="shelf-unique-toggle-${ids.workflowId}"]`).click();
    const uniqueInput = unique.locator(`[data-testid="shelf-unique-input-${ids.workflowId}-cfg"]`);
    await expect(uniqueInput).toBeVisible({ timeout: 5000 });
    await uniqueInput.fill("9");
    expect(await uniqueInput.inputValue()).toBe("9");

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });

  test("3. pills enter-to-create, hover full text, removable; number ops on int and float", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    await selectPortraitCurrent(page, wfMock);
    await enableExperiment(page);

    // Activate the seed axis (integer field).
    await page.locator('[data-testid="shelf-axis-seed"]').click();
    await expect(page.locator('[data-testid="shelf-pills-seed"]')).toBeVisible({ timeout: 5000 });
    const before = await page.locator('[data-testid^="shelf-pill-seed-"]').count();

    // Enter-to-create with a long prompt-like value; full text on hover.
    const longText = "a very long seed label value that exceeds the pill truncation width for title check";
    await page.locator('[data-testid="shelf-axis-input-seed"]').fill(longText);
    await page.locator('[data-testid="shelf-axis-input-seed"]').press("Enter");
    const pill = page.locator(`[data-testid="shelf-pill-seed-${before}"]`);
    await expect(pill).toBeVisible({ timeout: 5000 });
    expect(await pill.getAttribute("title")).toBe(longText);

    // Removable.
    await pill.locator(`[data-testid="shelf-pill-remove-seed-${before}"]`).click();
    await expect(page.locator(`[data-testid="shelf-pill-seed-${before}"]`)).toHaveCount(0, { timeout: 5000 });

    // Generic integer ops: Random / Increment / Decrement / Empty.
    const intCount = await page.locator('[data-testid^="shelf-pill-seed-"]').count();
    await page.locator('[data-testid="shelf-num-random-seed"]').click();
    await page.locator('[data-testid="shelf-num-inc-seed"]').click();
    await page.locator('[data-testid="shelf-num-dec-seed"]').click();
    await page.locator('[data-testid="shelf-num-empty-seed"]').click();
    expect(await page.locator('[data-testid^="shelf-pill-seed-"]').count()).toBe(intCount + 4);

    // Generic float ops on cfg.
    await page.locator('[data-testid="shelf-axis-cfg"]').click();
    await expect(page.locator('[data-testid="shelf-pills-cfg"]')).toBeVisible({ timeout: 5000 });
    const floatCount = await page.locator('[data-testid^="shelf-pill-cfg-"]').count();
    await page.locator('[data-testid="shelf-num-random-cfg"]').click();
    await page.locator('[data-testid="shelf-num-inc-cfg"]').click();
    await page.locator('[data-testid="shelf-num-dec-cfg"]').click();
    await page.locator('[data-testid="shelf-num-empty-cfg"]').click();
    expect(await page.locator('[data-testid^="shelf-pill-cfg-"]').count()).toBe(floatCount + 4);

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });

  test("4. matrix gating and submission render in the existing experiment-v2 surface", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);

    // Stub the experiment-v2 engine: capture the definition, complete 4 cells.
    let postedBody = null;
    await page.route("**/comfymodal/studio/experiment-v2", async (route) => {
      postedBody = route.request().postDataJSON();
      const cells = [0, 1, 2, 3].map((i) => ({
        cell_id: "cell_" + i,
        status: "completed",
        thumb_url: "/comfymodal/assets/shelf_cell_" + i,
        workflow_id: i < 2 ? "wf_primary" : "wf_second",
      }));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          experiment_id: "exp_shelf_matrix",
          item: {
            experiment_id: "exp_shelf_matrix",
            aggregate_status: "completed",
            total: 4,
            counts: { queued: 0, running: 0, completed: 4, failed: 0, canceled: 0, interrupted: 0 },
            cells,
          },
        }),
      });
    });
    await page.route("**/comfymodal/history-v2/experiments/*/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          item: {
            experiment_id: "exp_shelf_matrix",
            aggregate_status: "completed",
            total: 4,
            counts: { queued: 0, running: 0, completed: 4, failed: 0, canceled: 0, interrupted: 0 },
            cells: [0, 1, 2, 3].map((i) => ({
              cell_id: "cell_" + i,
              status: "completed",
              thumb_url: "/comfymodal/assets/shelf_cell_" + i,
            })),
          },
        }),
      });
    });

    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const guard = installConsoleGuard(page);

    try {
      await selectPortraitCurrent(page, wfMock);
      const subset = await createSubsetWorkflow(page);
      await enableExperiment(page);
      await compareWithSubset(page, subset.workflowId);

      // Gated until an axis has values: enable seed, add a second value.
      const runBtn = page.locator('[data-testid="shelf-exp-run-btn"]');
      await expect(runBtn).toBeDisabled({ timeout: 10000 });
      await page.locator('[data-testid="shelf-axis-seed"]').click();
      await page.locator('[data-testid="shelf-axis-input-seed"]').fill("222");
      await page.locator('[data-testid="shelf-axis-input-seed"]').press("Enter");

      // Matrix summary: 2 workflows x seed[2] = 4 runs; run enabled.
      await expect(page.locator('[data-testid="shelf-exp-matrix"]')).toContainText("2 workflow(s)", { timeout: 10000 });
      await expect(page.locator('[data-testid="shelf-exp-matrix"]')).toContainText("4 run(s)");
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      // ONE definition posted: both workflows, exact seed values.
      await expect.poll(() => postedBody !== null, { timeout: 15000 }).toBe(true);
      const definition = postedBody.definition;
      expect(definition.workflows.length).toBe(2);
      expect(definition.axes.seed).toBeTruthy();
      expect(definition.axes.seed.values.map((v) => Number(v)).sort((a, b) => a - b)).toEqual([42, 222]);
      expect(postedBody.experiment_id).toBeTruthy();

      // Results render in the EXISTING experiment-v2 grid (no second system).
      const grid = page.locator('[data-testid="experiment-v2-grid"]');
      await expect(grid.locator('[data-testid="experiment-v2-cell-cell_0"]')).toBeVisible({ timeout: 15000 });
      expect(await grid.locator('[data-testid^="experiment-v2-cell-cell_"]').count()).toBe(4);
      await expect(page.locator('[data-testid="experiment-v2-progress"]')).toContainText("4/4 complete", { timeout: 15000 });

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      guard.dispose();
    }
  });

  test("5. shelf interactions stay console-clean with full mock coverage", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const guard = installConsoleGuard(page);

    try {
      await selectPortraitCurrent(page, wfMock);
      await enableExperiment(page);

      // Open + close the many-mode picker without confirming.
      await page.locator('[data-testid="shelf-exp-pick-btn"]').click();
      await expect(page.locator('[data-testid="shelf-exp-picker-dialog"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="shelf-exp-picker-close"]').click();
      await expect(page.locator('[data-testid="shelf-exp-picker-dialog"]')).toHaveCount(0, { timeout: 5000 });

      // Toggle an axis on and off; edit a shelf field while in experiment mode.
      await page.locator('[data-testid="shelf-axis-steps"]').click();
      await expect(page.locator('[data-testid="shelf-pills-steps"]')).toBeVisible({ timeout: 5000 });
      await page.locator('[data-testid="shelf-axis-steps"]').click();
      await expect(page.locator('[data-testid="shelf-pills-steps"]')).toHaveCount(0, { timeout: 5000 });
      await page.locator('[data-testid="shelf-input-steps"]').fill("33");
      await page.waitForTimeout(700);

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      guard.dispose();
    }
  });
});
