import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { performance } from "node:perf_hooks";
import { test, expect } from "@playwright/test";
import { openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const SHELF_ROLES = [
  "sampler", "scheduler", "seed", "steps", "cfg", "negative_prompt",
  "width", "height", "denoise", "source_image", "hires_fix",
];

async function pinPrimaryExtensionRequests(page) {
  await page.route(/\/extensions\//, async (route) => {
    const requestUrl = new URL(route.request().url());
    const match = requestUrl.pathname.match(/^\/extensions\/([^/]+)\/(.*)$/);
    if (match && match[1] !== "comfyui-modal" && /modal/i.test(match[1])) {
      requestUrl.pathname = `/extensions/comfyui-modal/${match[2]}`;
      await route.continue({ url: requestUrl.toString() });
      return;
    }
    await route.continue();
  });
}

test("measures Studio open to fully loaded Playground shelves", async ({ page }, testInfo) => {
  test.setTimeout(45_000);

  const network = [];
  const pendingBodies = [];
  const requestStarts = new Map();
  const consoleEvents = [];
  const pageErrors = [];
  const mono = () => performance.now();
  let measurement = null;

  page.on("console", (message) => {
    consoleEvents.push({ type: message.type(), text: message.text(), atMs: mono() });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ text: error.message, atMs: mono() });
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (!url.pathname.startsWith("/comfymodal/")) return;
    requestStarts.set(request, mono());
  });
  page.on("response", (response) => {
    const request = response.request();
    const startedAt = requestStarts.get(request);
    if (startedAt == null) return;
    const record = {
      method: request.method(),
      path: new URL(request.url()).pathname,
      url: request.url(),
      status: response.status(),
      requestBytes: request.postDataBuffer()?.byteLength || 0,
      startedAtMs: startedAt,
      durationMs: null,
      responseBytes: null,
      responseText: null,
    };
    const bodyPromise = response.body().then((body) => {
      record.responseBytes = body.byteLength;
      record.responseText = body.toString("utf8");
    }).catch((error) => {
      record.bodyError = error.message;
    }).finally(() => {
      record.durationMs = mono() - startedAt;
    });
    pendingBodies.push(bodyPromise);
    network.push(record);
  });

  const api = await installStudioMockApi(page);
  const workflows = await installWorkflowsMock(page);
  await pinPrimaryExtensionRequests(page);
  await page.route("**/comfymodal/studio/models**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", models: [] }),
    });
  });

  const openStartedAt = mono();
  let shelvesReadyAt = null;
  try {
    await openStudio(page, COMFYUI_URL);
    await expect(page.locator('[data-testid="playground-page-title"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="workflow-selector"]')).toBeVisible({ timeout: 15_000 });

    const portrait = workflows.getWorkflow("Portrait Pro");
    expect(portrait).toBeTruthy();
    const selector = page.locator('[data-testid="workflow-selector"]');
    await expect(selector.locator(`option[value="${portrait.workflow_id}"]`)).toHaveCount(1, { timeout: 15_000 });
    await selector.selectOption(portrait.workflow_id);

    await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="workspace"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="shelf-prompt-card"]')).toBeVisible({ timeout: 15_000 });
    for (const role of SHELF_ROLES) {
      await expect(page.locator(`[data-testid="shelf-field-${role}"]`)).toBeVisible({ timeout: 15_000 });
    }
    shelvesReadyAt = mono();

    const workflowListResponses = network.filter(
      (entry) => entry.method === "GET" && entry.path === "/comfymodal/studio/workflows",
    );
    expect(workflowListResponses.length).toBeGreaterThan(0);
    const workflowList = workflowListResponses[workflowListResponses.length - 1];
    expect(workflowList.status).toBe(200);
    const workflowPayload = JSON.parse(workflowList.responseText);
    expect(workflowPayload.status).toBe("ok");
    expect(workflowPayload.workflows).toHaveLength(2);

    await Promise.all(pendingBodies);
    const pageOpenToShelvesReadyMs = shelvesReadyAt - openStartedAt;
    const backendSummary = network.map((entry) => ({
      method: entry.method,
      path: entry.path,
      status: entry.status,
      requestBytes: entry.requestBytes,
      responseBytes: entry.responseBytes,
      durationMs: Number((entry.durationMs || 0).toFixed(2)),
    }));
    measurement = {
      mode: "mocked",
      pageOpenToShelvesReadyMs: Number(pageOpenToShelvesReadyMs.toFixed(2)),
      under500ms: pageOpenToShelvesReadyMs < 500,
      shelfRoleCount: SHELF_ROLES.length,
      workflowList: {
        status: workflowList.status,
        responseBytes: workflowList.responseBytes,
        durationMs: Number((workflowList.durationMs || 0).toFixed(2)),
        workflowCount: workflowPayload.workflows.length,
      },
      backend: backendSummary,
    };
    console.log(`STUDIO_SHELF_TIMING ${JSON.stringify(measurement)}`);
    await expect(page.locator('[data-testid="shelf-fields"]')).toBeVisible();
  } finally {
    await Promise.allSettled(pendingBodies);
    const artifactDir = dirname(testInfo.outputPath("network.json"));
    await mkdir(artifactDir, { recursive: true });
    await page.screenshot({ path: testInfo.outputPath("playground-shelves.png"), fullPage: true }).catch(() => {});
    await writeFile(testInfo.outputPath("network.json"), JSON.stringify(network, null, 2));
    await writeFile(testInfo.outputPath("console.json"), JSON.stringify({ consoleEvents, pageErrors }, null, 2));
    await writeFile(testInfo.outputPath("measurement.json"), JSON.stringify(measurement, null, 2));
    api.assertNoUnhandledCalls();
    workflows.assertNoUnhandledWorkflowCalls();
  }
});
