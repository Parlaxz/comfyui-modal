// Modal Studio — Shelf Playground E2E Tests (Studio Workflow effort, leaf 1.2.2)
//
// Drives the Shelf single-run flow against the mocked backend:
// installStudioMockApi FIRST, then installWorkflowsMock (later routes take
// precedence for /comfymodal/studio/workflows*). Uses fresh Playwright Test
// page/context (never MCP/shared session).
//
// Covered contracts:
//   1. Shelf renders bound field cards (catalog names, block inputs) with
//      Prompt fixed at top; output is the right-side result panel.
//   2. No Backend/Preset UI anywhere in the Shelf flow.
//   3. Field edits autosave durably with a subtle autosaved indicator and
//      no Save button; reload restores values.
//   4. Drag reorder, Advanced placement, and same-row grouping persist as
//      workflow-type layout; reload restores it.
//   5. Single run completes into the right-side output panel.
//   6. Workflow switching via the shared picker prompts for value reuse and
//      marks old output stale until a new run completes.
//   7. Experiment-only draft state never overwrites Workflow values.

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  openStudio,
} from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// ── Helpers ──────────────────────────────────────────────────────────────

// ── Primary-extension pin ───────────────────────────────────────────────
// Mirrors studio-workflows.spec.mjs: the mocked suite has no Playwright
// webServer and navigates to the shared ComfyUI instance at 127.0.0.1:8188,
// letting that server's extension registry resolve /extensions/.... Sibling
// lanes register the same extension name, so without pinning the page can
// load stale sibling code instead of this repo's primary copy at
// /extensions/comfyui-modal/.
async function pinPrimaryExtensionRequests(page) {
  // NOTE: regex, not a "**/extensions/*" glob — in Playwright glob syntax
  // "*" does not cross "/", so that glob never matches nested module URLs
  // like /extensions/<dir>/studio-shell.js and the pin would be a no-op.
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

async function installMocks(page, options) {
  const api = await installStudioMockApi(page, options);
  const wfMock = await installWorkflowsMock(page);
  // Mount-pinning: rewrite sibling-lane extension requests to the primary
  // copy BEFORE the app loads (see pinPrimaryExtensionRequests).
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
  const v1 = versions.find((v) => v.version_number === 1);
  const v2 = versions.find((v) => v.version_number === 2);
  expect(v1).toBeTruthy();
  expect(v2).toBeTruthy();
  return { workflowId: wf.workflow_id, v1: v1.workflow_version_id, v2: v2.workflow_version_id };
}

async function selectPortraitV1(page, wfMock) {
  const ids = portraitIds(wfMock);
  const wfSelect = page.locator('[data-testid="workflow-selector"]');
  await expect(wfSelect.locator(`option[value="${ids.workflowId}"]`)).toHaveCount(1, { timeout: 15000 });
  await wfSelect.selectOption(ids.workflowId);
  await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 15000 });
  const verSelect = page.locator('[data-testid="workflow-version-selector"]');
  await verSelect.selectOption(ids.v1);
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="workflow-run-gating"]')).toContainText("Ready to run", { timeout: 15000 });
  return ids;
}

async function shelfValue(page, role) {
  return page.locator(`[data-testid="shelf-input-${role}"]`).inputValue();
}

// ── Tests ────────────────────────────────────────────────────────────────

test.describe("Studio Shelf Playground", () => {
  test("1. shelf renders bound field cards with catalog names, prompt fixed top, output on right", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const guard = installConsoleGuard(page);

    try {
      await selectPortraitV1(page, wfMock);

      // Shelf section with the workflow name + switcher + autosaved note.
      await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible();
      await expect(page.locator('[data-testid="shelf-workflow-name"]')).toContainText("Portrait Pro");
      await expect(page.locator('[data-testid="shelf-workflow-switch"]')).toBeVisible();
      await expect(page.locator('[data-testid="shelf-autosaved"]')).toContainText("Autosaved");

      // Prompt card is fixed at top: first card in the shelf, no drag handle.
      const promptCard = page.locator('[data-testid="shelf-prompt-card"]');
      await expect(promptCard).toBeVisible();
      const firstCard = page.locator('[data-testid="shelf-section"] > div:nth-child(2)');
      expect(await firstCard.getAttribute("data-testid")).toBe("shelf-prompt-card");
      expect(await promptCard.locator('[data-testid^="shelf-drag-"]').count()).toBe(0);

      // Catalog role names (no duplicated catalog): Seed/Sampler from
      // web/studio-bindable-inputs.js; other roles from mapping display names.
      expect(await page.locator('[data-testid="shelf-field-seed"] .comfymodal-studio-shelf-card-label').textContent()).toBe("Seed");
      expect(await page.locator('[data-testid="shelf-field-sampler"] .comfymodal-studio-shelf-card-label').textContent()).toBe("Sampler");
      expect(await page.locator('[data-testid="shelf-field-steps"] .comfymodal-studio-shelf-card-label').textContent()).toBe("Steps");

      // Block inputs: integer seed is a number input; every other bound
      // field carries a drag handle.
      expect(await page.locator('[data-testid="shelf-input-seed"]').getAttribute("type")).toBe("number");
      await expect(page.locator('[data-testid="shelf-drag-seed"]')).toBeVisible();
      await expect(page.locator('[data-testid="shelf-drag-steps"]')).toBeVisible();

      // No Backend/Preset UI anywhere in the Shelf flow.
      expect(await page.locator('[data-testid="backend-select"]').count()).toBe(0);
      expect(await page.locator('[data-testid="controls-container"]').count()).toBe(0);

      // Output is the right-side result panel (canvas + progress + metadata
      // + filmstrip), never a movable card.
      const workspace = page.locator('[data-testid="workspace"]');
      await expect(workspace).toBeVisible();
      expect(await workspace.getAttribute("data-shelf-output-panel")).toBe("true");
      await expect(page.locator('[data-testid="canvas-area"]')).toBeVisible();
      expect(await page.locator('[data-testid^="shelf-field-"]').count()).toBeGreaterThan(3);

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      guard.dispose();
    }
  });

  test("2. field edits autosave durably with no save button; reload restores values", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    await selectPortraitV1(page, wfMock);

    // Edit the seed through the Shelf card (debounced durable autosave).
    await page.locator('[data-testid="shelf-input-seed"]').fill("123");
    await page.waitForTimeout(700);
    const saved = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem("comfymodal.studio.shelf.values.v1") || "{}"); } catch { return {}; }
    });
    const keys = Object.keys(saved);
    expect(keys.length).toBeGreaterThanOrEqual(1);
    const entry = saved[keys.find((k) => saved[k] && saved[k].seed === 123)];
    expect(entry).toBeTruthy();
    expect(entry.seed).toBe(123);

    // Subtle autosaved indicator, and no Save button anywhere in the Shelf.
    await expect(page.locator('[data-testid="shelf-autosaved"]')).toContainText("Autosaved");
    expect(await page.locator('[data-testid="shelf-section"] button', { hasText: /^Save$/ }).count()).toBe(0);

    // Reload: the persisted Workflow selection restores and the Shelf shows
    // the saved value without any manual selection.
    await page.reload();
    await openStudio(page, COMFYUI_URL);
    await expect(page.locator('[data-testid="shelf-input-seed"]')).toHaveValue("123", { timeout: 20000 });

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });

  test("3. drag reorder, advanced placement, and same-row grouping persist as layout", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    await selectPortraitV1(page, wfMock);

    // Deterministic synthetic HTML5 drag-and-drop: seed before steps.
    await page.evaluate(() => {
      const grip = document.querySelector('[data-testid="shelf-drag-seed"]');
      const target = document.querySelector('[data-testid="shelf-field-steps"]');
      if (!grip || !target) throw new Error("shelf drag fixtures missing");
      const dt = new DataTransfer();
      dt.setData("text/shelf-role", "seed");
      grip.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: dt }));
      target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: dt }));
      target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: dt }));
      grip.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: dt }));
    });
    await page.waitForTimeout(300);

    // Advanced placement: cfg moves into the Advanced section.
    await page.locator('[data-testid="shelf-advanced-cfg"]').click();
    await expect(page.locator('[data-testid="shelf-advanced-section"] [data-testid="shelf-field-cfg"]')).toBeVisible({ timeout: 5000 });

    // Same-row grouping: height joins width's row.
    await page.locator('[data-testid="shelf-group-height"]').click();
    const sharedRow = page.locator('[data-testid^="shelf-row-"]', { has: page.locator('[data-testid="shelf-field-width"]') });
    await expect(sharedRow.locator('[data-testid="shelf-field-height"]')).toBeVisible({ timeout: 5000 });

    // Layout autosaved under the workflow-type key.
    const layout = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem("comfymodal.studio.shelf.layout.v1") || "{}"); } catch { return {}; }
    });
    const t2i = layout.t2i;
    expect(t2i).toBeTruthy();
    expect(t2i.order.indexOf("seed")).toBeLessThan(t2i.order.indexOf("steps"));
    expect(t2i.advanced).toContain("cfg");
    expect(t2i.rows.height).toBe(t2i.rows.width);

    // Reload: layout restored (seed still before steps, cfg still Advanced).
    await page.reload();
    await openStudio(page, COMFYUI_URL);
    await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 20000 });
    const order = await page.locator('[data-testid="shelf-fields"] [data-testid^="shelf-field-"]').evaluateAll((els) =>
      els.map((node) => node.getAttribute("data-testid"))
    );
    expect(order.indexOf("shelf-field-seed")).toBeLessThan(order.indexOf("shelf-field-steps"));
    await page.locator('[data-testid="shelf-advanced-toggle"]').click();
    await expect(page.locator('[data-testid="shelf-advanced-section"] [data-testid="shelf-field-cfg"]')).toBeVisible({ timeout: 5000 });

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });

  test("4. single run completes into the right-side output panel", async ({ page }) => {
    const { api, wfMock } = await installMocks(page, { runDelayMs: 300 });
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const guard = installConsoleGuard(page);

    try {
      await selectPortraitV1(page, wfMock);
      await page.locator('[data-testid="shelf-input-positive_prompt"]').fill("shelf test cat");
      await page.evaluate(() => localStorage.setItem(
        "comfymodal.studio.golden.profile.v1",
        "golden_p1_parallel_c0_p8_h100",
      ));

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      // Golden stage polling starts before the delayed POST resolves. The
      // exact stage names and event-owned timing are visible while the POST
      // is still in flight, but the run is not terminal yet.
      await expect(page.locator('[data-testid="progress-golden-stage-row"]')).toHaveCount(2, { timeout: 10000 });
      await expect(page.locator('[data-testid="progress-golden-stages"]')).toContainText("golden_clip_load");
      await expect(page.locator('[data-testid="progress-golden-stages"]')).toContainText("golden_decode");
      await expect(page.locator('[data-testid="progress-golden-stages"]')).toContainText("duration: 40ms");
      await expect(page.locator('[data-testid="run-status-message"]')).toHaveCount(0);

      // Output lands in the right-side canvas (never a movable card).
      const canvasOutput = page.locator('[data-testid="canvas-output"]');
      await expect(canvasOutput).toBeVisible({ timeout: 45000 });
      const src = await canvasOutput.getAttribute("src");
      expect(src).toBeTruthy();
      expect(src).toContain("/comfymodal/");

      // Run button re-enables; submission carried the Shelf field values.
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      expect((await runBtn.textContent()).trim()).toBe("Run");
      const submitted = api.lastRunRequest;
      expect(submitted).toBeTruthy();
      expect(submitted.workflow_id).toBe(portraitIds(wfMock).workflowId);
      expect(submitted.controls.positive_prompt).toBe("shelf test cat");
      expect(submitted.request_id).toBeTruthy();
      expect(submitted.profile_name).toBe("golden_p1_parallel_c0_p8_h100");

      // Metadata + timing surfaces stay on the right-side panel.
      await expect(page.locator('[data-testid="timing-card"]')).toBeVisible({ timeout: 10000 });

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      guard.dispose();
    }
  });

  test("5. picker switching prompts for reuse and marks output stale until next run", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    const ids = await selectPortraitV1(page, wfMock);
    await page.locator('[data-testid="shelf-input-seed"]').fill("444");
    await page.waitForTimeout(700);

    // Complete a run so there is output to mark stale.
    await page.locator('[data-testid="run-btn"]').click();
    await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 45000 });

    // Switch Workflows through the shared picker.
    await page.locator('[data-testid="shelf-workflow-switch"]').click();
    const dialog = page.locator('[data-testid="shelf-picker-dialog"]');
    await expect(dialog).toBeVisible({ timeout: 10000 });
    await expect(dialog.locator('[data-testid="workflow-picker-option"]')).toHaveCount(2, { timeout: 10000 });
    const abstract = wfMock.getWorkflow("Abstract Test");
    await dialog.locator(`[data-testid="workflow-picker-option"][data-workflow-id="${abstract.workflow_id}"]`).click();
    await dialog.locator('[data-testid="workflow-picker-confirm"]').click();

    // Reuse prompt, then the new Workflow's fields load.
    const reuse = page.locator('[data-testid="shelf-reuse-dialog"]');
    await expect(reuse).toBeVisible({ timeout: 10000 });
    await reuse.locator('[data-testid="shelf-reuse-yes"]').click();
    await expect(page.locator('[data-testid="shelf-workflow-name"]')).toContainText("Abstract Test", { timeout: 15000 });

    // Old output is stale until a new run completes.
    await expect(page.locator('[data-testid="shelf-stale-note"]')).toBeVisible({ timeout: 10000 });

    // Switch back; stale persists; a new run clears it.
    await page.locator('[data-testid="shelf-workflow-switch"]').click();
    const dialog2 = page.locator('[data-testid="shelf-picker-dialog"]');
    await expect(dialog2).toBeVisible({ timeout: 10000 });
    await dialog2.locator(`[data-testid="workflow-picker-option"][data-workflow-id="${ids.workflowId}"]`).click();
    await dialog2.locator('[data-testid="workflow-picker-confirm"]').click();
    await expect(page.locator('[data-testid="shelf-reuse-dialog"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="shelf-reuse-no"]').click();
    await expect(page.locator('[data-testid="shelf-workflow-name"]')).toContainText("Portrait Pro", { timeout: 15000 });
    await page.locator('[data-testid="workflow-version-selector"]').selectOption(ids.v1);
    await expect(page.locator('[data-testid="shelf-input-seed"]')).toHaveValue("444", { timeout: 15000 });
    await expect(page.locator('[data-testid="shelf-stale-note"]')).toBeVisible();
    await page.locator('[data-testid="run-btn"]').click();
    await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 45000 });
    await expect(page.locator('[data-testid="shelf-stale-note"]')).toHaveCount(0, { timeout: 10000 });

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });

  test("6. experiment draft autosaves locally without overwriting workflow values", async ({ page }) => {
    const { api, wfMock } = await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });

    await selectPortraitV1(page, wfMock);
    await page.locator('[data-testid="shelf-input-seed"]').fill("777");
    await page.waitForTimeout(700);

    // Enable experiment mode and configure an axis (draft lane).
    await page.locator('[data-testid="experiment-toggle"]').click();
    await expect(page.locator('[data-testid="shelf-exp-panel"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="shelf-axis-seed"]').click();
    await expect(page.locator('[data-testid="shelf-pills-seed"]')).toBeVisible({ timeout: 5000 });

    const draft = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem("comfymodal.studio.shelf.experiment.v1") || "null"); } catch { return null; }
    });
    expect(draft).toBeTruthy();
    expect(draft.axes.seed).toBeTruthy();

    // Reload: Workflow values intact, experiment draft intact and separate.
    await page.reload();
    await openStudio(page, COMFYUI_URL);
    await expect(page.locator('[data-testid="shelf-input-seed"]')).toHaveValue("777", { timeout: 20000 });
    const values = await page.evaluate(() => {
      try { return JSON.parse(localStorage.getItem("comfymodal.studio.shelf.values.v1") || "{}"); } catch { return {}; }
    });
    const flat = Object.values(values);
    expect(flat.some((v) => v && v.seed === 777)).toBe(true);
    await page.locator('[data-testid="experiment-toggle"]').click();
    await expect(page.locator('[data-testid="shelf-pills-seed"]')).toBeVisible({ timeout: 10000 });

    api.assertNoUnhandledCalls();
    wfMock.assertNoUnhandledWorkflowCalls();
  });
});
