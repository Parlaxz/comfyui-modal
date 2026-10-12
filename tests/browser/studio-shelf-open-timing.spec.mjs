import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { performance } from "node:perf_hooks";
import { test, expect } from "@playwright/test";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const SHELF_ROLES = [
  "sampler", "scheduler", "seed", "steps", "cfg", "negative_prompt",
  "width", "height", "denoise", "source_image", "hires_fix",
];
const SELECTION_KEY = "comfymodal.studio.playground.workflow.v1";

test("measures Studio-open to fully loaded Playground shelves", async ({ page }, testInfo) => {
  test.setTimeout(45_000);

  const network = [];
  const pendingBodies = [];
  const requestStarts = new Map();
  const mono = () => performance.now();
  let measurement = null;

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
      status: response.status(),
      requestBytes: request.postDataBuffer()?.byteLength || 0,
      startedAtMs: startedAt,
      durationMs: null,
      responseBytes: null,
    };
    const bodyPromise = response.body().then((body) => {
      record.responseBytes = body.byteLength;
    }).catch(() => {}).finally(() => {
      record.durationMs = mono() - startedAt;
    });
    pendingBodies.push(bodyPromise);
    network.push(record);
  });

  const api = await installStudioMockApi(page);
  const workflows = await installWorkflowsMock(page);
  await page.route("**/comfymodal/studio/models**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", models: [] }),
    });
  });

  const portrait = workflows.getWorkflow("Portrait Pro");
  expect(portrait).toBeTruthy();
  const selection = {
    workflowId: portrait.workflow_id,
    workflowVersionId: portrait.latest_version_id,
    workflowName: portrait.name || "Portrait Pro",
  };

  // Navigate first so ComfyUI boot is measured separately from Studio open.
  const navStart = mono();
  await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
  const navDone = mono();

  // Wait for the Studio launcher (extension script load is part of
  // ComfyUI boot, not the Studio-open window).
  await page.waitForFunction(
    () => typeof window.open_testing_modal === "function",
    { timeout: 15_000 },
  );

  // Preseed the saved selection so shelves auto-load on Studio open —
  // no manual workflow pick inside the measured window.
  await page.evaluate(([key, sel]) => {
    try { localStorage.setItem(key, JSON.stringify(sel)); } catch (e) {}
  }, [SELECTION_KEY, selection]);

  const openStartedAt = mono();
  let shelvesReadyAt = null;
  try {
    await page.evaluate(() => window.open_testing_modal());
    await expect(page.locator('[data-testid="studio-page"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="playground-page-title"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="shelf-fields"]')).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-testid="workspace"]')).toBeVisible({ timeout: 15_000 });
    for (const role of SHELF_ROLES) {
      await expect(page.locator(`[data-testid="shelf-field-${role}"]`)).toBeVisible({ timeout: 15_000 });
    }
    shelvesReadyAt = mono();

    await Promise.all(pendingBodies);
    const studioOpenToShelvesReadyMs = shelvesReadyAt - openStartedAt;
    measurement = {
      mode: "mocked",
      comfyuiNavMs: Number((navDone - navStart).toFixed(2)),
      studioOpenToShelvesReadyMs: Number(studioOpenToShelvesReadyMs.toFixed(2)),
      under500ms: studioOpenToShelvesReadyMs < 500,
      shelfRoleCount: SHELF_ROLES.length,
      backend: network.map((entry) => ({
        method: entry.method,
        path: entry.path,
        status: entry.status,
        requestBytes: entry.requestBytes,
        responseBytes: entry.responseBytes,
        durationMs: Number((entry.durationMs || 0).toFixed(2)),
      })),
    };
    console.log(`STUDIO_SHELF_OPEN_TIMING ${JSON.stringify(measurement)}`);
  } finally {
    await Promise.allSettled(pendingBodies);
    const artifactDir = dirname(testInfo.outputPath("network.json"));
    await mkdir(artifactDir, { recursive: true });
    await page.screenshot({ path: testInfo.outputPath("playground-shelves.png"), fullPage: true }).catch(() => {});
    await writeFile(testInfo.outputPath("network.json"), JSON.stringify(network, null, 2));
    await writeFile(testInfo.outputPath("measurement.json"), JSON.stringify(measurement, null, 2));
    api.assertNoUnhandledCalls();
    workflows.assertNoUnhandledWorkflowCalls();
  }
});
