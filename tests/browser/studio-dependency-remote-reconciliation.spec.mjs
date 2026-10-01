// Modal Studio — server-owned dependency reconciliation.

import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

const APP_NOISE_PATTERNS = [
  "already registered",
  "vite:preloadError",
  "Failed to load resource",
  "ComfyApp graph accessed",
];

let api;
let wfMock;
let modelRequests;

async function pinPrimaryExtensionRequests(page) {
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

async function openWorkflow(page, name) {
  const workflow = wfMock.getWorkflow(name);
  const card = page.locator(
    `[data-testid="workflow-card"][data-workflow-id="${workflow.workflow_id}"]`
  );
  await expect(card).toBeVisible({ timeout: 10000 });
  await card.click();
  await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
  return workflow;
}

test.describe("server-owned remote dependency reconciliation", () => {
  test.beforeEach(async ({ page }) => {
    modelRequests = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (request.method() === "GET" && url.pathname === "/comfymodal/models") {
        modelRequests.push(request.url());
      }
    });

    api = await installStudioMockApi(page);
    wfMock = await installWorkflowsMock(page);
    await pinPrimaryExtensionRequests(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
    await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 15000 });
  });

  test("renders the server answer on the detail page without a model inventory fetch", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openWorkflow(page, "Portrait Pro");
      const section = page.locator('[data-testid="dependencies-summary"]');
      await expect(section).toBeVisible();

      const installed = section.locator('[data-testid="dependency-model-row"]').filter({
        hasText: "sd_xl_base_1.0.safetensors",
      });
      await expect(installed.locator('[data-testid="dependency-model-state"]')).toHaveText("Installed");
      await expect(installed.locator('[data-testid="dependency-model-remote"]')).toContainText("4.0 GB");
      await expect(installed.locator('[data-testid="dependency-model-queue"]')).toHaveCount(0);
      await expect(installed.locator('[data-testid="dependency-model-install-now"]')).toHaveCount(0);
      await expect(section.locator('[data-testid="dependency-status"]')).toHaveText("Ready");

      await page.locator('.comfymodal-studio-detail-top button').click();
      await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 10000 });
      await openWorkflow(page, "Abstract Test");
      const missing = page.locator('[data-testid="dependencies-summary"]')
        .locator('[data-testid="dependency-model-row"]')
        .filter({ hasText: "abstract_missing.safetensors" });
      await expect(missing.locator('[data-testid="dependency-model-state"]')).toHaveText("Missing");
      await expect(missing.locator('[data-testid="dependency-model-remote"]')).toHaveCount(0);
      await expect(missing.locator('[data-testid="dependency-model-queue"]')).toHaveCount(0);
      await expect(missing.locator('[data-testid="dependency-model-install-now"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="dependency-status"]')).toHaveText(
        "Incomplete — 1 dependency needs attention"
      );

      expect(modelRequests).toEqual([]);
      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  test("Not needed marks the row Optional and survives a re-read", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openWorkflow(page, "Abstract Test");
      const row = page.locator('[data-testid="dependency-model-row"]').filter({
        hasText: "abstract_missing.safetensors",
      });
      await expect(row.locator('[data-testid="dependency-model-state"]')).toHaveText("Missing");

      const posted = [];
      page.on("request", (r) => {
        if (r.method() === "POST" && r.url().includes("/dependencies/nonessential")) {
          posted.push(r.postData());
        }
      });

      await row.locator('[data-testid="dependency-model-nonessential-toggle"]').click();

      // The row must actually flip, which means the POST round-tripped and the
      // re-read report carried the override back.
      await expect(row).toHaveAttribute("data-nonessential", "true", { timeout: 15000 });
      await expect(row.locator('[data-testid="dependency-model-state"]')).toHaveText("Optional");
      await expect(row.locator('[data-testid="dependency-model-nonessential"]'))
        .toHaveText("marked unnecessary");
      expect(posted.length, "toggle must POST the override").toBeGreaterThan(0);

      // Restoring puts the blocking state back.
      await row.locator('[data-testid="dependency-model-restore"]').click();
      await expect(row.locator('[data-testid="dependency-model-state"]')).toHaveText("Missing", {
        timeout: 15000,
      });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  test("a failed override surfaces an error instead of failing silently", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);
      await openWorkflow(page, "Abstract Test");
      const row = page.locator('[data-testid="dependency-model-row"]').filter({
        hasText: "abstract_missing.safetensors",
      });

      await page.route(/\/dependencies\/nonessential$/, (route) =>
        route.fulfill({ status: 500, contentType: "application/json", body: '{"status":"error","message":"boom"}' })
      );

      await row.locator('[data-testid="dependency-model-nonessential-toggle"]').click();

      // A silent no-op was the original defect: the click must leave evidence.
      await expect(page.locator('[data-testid="dependency-model-error"]')).toBeVisible({
        timeout: 15000,
      });
      await expect(row.locator('[data-testid="dependency-model-state"]')).toHaveText("Missing");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
    } finally {
      if (guard) guard.dispose();
    }
  });

  test("renders the same server answer in the wizard Dependencies step", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);
      const workflow = wfMock.getWorkflow("Abstract Test");
      const card = page.locator(`[data-testid="workflow-card"][data-workflow-id="${workflow.workflow_id}"]`);
      await card.click();
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="mapping-setup-button"]').click();

      const panel = page.locator(".comfymodal-studio-wizard-panel");
      await expect(panel).toBeVisible({ timeout: 10000 });
      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.locator('[data-testid="wizard-features-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({ timeout: 10000 });

      const missing = panel.locator('[data-testid="dependency-model-row"]')
        .filter({ hasText: "abstract_missing.safetensors" });
      await expect(missing.locator('[data-testid="dependency-model-state"]')).toHaveText("Missing");
      await expect(missing.locator('[data-testid="dependency-model-remote"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="dependency-status"]')).toHaveText(
        "Incomplete — 1 dependency needs attention"
      );

      expect(modelRequests).toEqual([]);
      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });
});
