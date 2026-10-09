// Byte-identity contract between the two full-size output overlays.
//
// The Playground canvas preview and the History generation detail mount the
// SAME viewer from the SAME durable record.  This spec proves it in a real
// browser: it runs a workflow, captures the Playground overlay's HTML, then
// captures the History overlay's HTML for THE SAME run and requires them to be
// byte-identical — same markup, same classes, same data, zero surface-specific
// naming left in the shared viewer.
//
// Two resolution paths are proven, because production splits run identity
// from record identity (a run id never resolves as a generation id):
//   1. bridged — the run response carries the backend-stamped generation id;
//   2. derived — without it, the preview maps the run through its legacy
//      history entry (which carries both ids) onto the same record.
// Both must render byte-identical DOM for the same run.

import { test, expect } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { setupFakeTest } from "./helpers.mjs";

const WORKFLOW = '[data-testid="workflow-selector"]';

// Viewer naming must be surface-neutral.  The asset URL path is the durable
// backend's route (a data concern, not the viewer's vocabulary), so the guard
// targets class/testid attributes — the viewer's own naming.
const FORBIDDEN_ATTRS = [
  'class="comfymodal-studio-history-v2-',
  'data-testid="history-v2-',
  'data-testid="note-editor',
  'data-testid="note-textarea"',
  'data-testid="note-save-btn',
  'data-testid="note-cancel-btn',
];

async function selectWorkflow(page) {
  await page.locator(WORKFLOW).selectOption("wf_text2img");
  await expect(page.locator('[data-testid="shelf-input-prompt"]')).toBeVisible({ timeout: 15000 });
}

async function viewerHtml(page) {
  return page.evaluate(() => {
    const content = document.querySelector(".comfymodal-studio-viewer-content");
    return content ? content.outerHTML : null;
  });
}

function checkNaming(playgroundHtml, historyHtml) {
  for (const needle of FORBIDDEN_ATTRS) {
    expect(playgroundHtml, `viewer must not reference ${JSON.stringify(needle)}`).not.toContain(needle);
    expect(historyHtml, `viewer must not reference ${JSON.stringify(needle)}`).not.toContain(needle);
  }
  expect(playgroundHtml).toContain('class="comfymodal-studio-viewer-content"');
  expect(playgroundHtml).toContain('data-testid="viewer-timing"');
  expect(playgroundHtml).toContain('data-testid="preview-parameters"');
}

test.describe("shared viewer parity", () => {
  test("playground preview and history detail are byte-identical (bridged)", async ({ page }) => {
    const genRequests = [];
    page.on("request", (r) => {
      if (/history-v2\/generations\//.test(r.url())) genRequests.push(r.url());
    });

    const fx = await setupFakeTest(page);
    try {
      await selectWorkflow(page);
      await page.locator('[data-testid="shelf-input-prompt"]').fill("A blue fox beside a silver lake");
      await page.locator('[data-testid="run-btn"]').click();
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 15000 });

      // ── Playground preview ───────────────────────────────────────────
      await page.locator('[data-testid="canvas-output"]').click();
      const playgroundOverlay = page.locator(".comfymodal-studio-viewer-overlay");
      await expect(playgroundOverlay).toBeVisible();
      await expect(playgroundOverlay.locator('[data-testid="viewer-timing"]')).toBeVisible({ timeout: 15000 });
      const playgroundHtml = await viewerHtml(page);
      const playgroundRequests = [...genRequests];
      await page.keyboard.press("Escape");
      await expect(page.locator(".comfymodal-studio-viewer-overlay")).toHaveCount(0);

      // ── History detail (same run) ────────────────────────────────────
      await fx.gotoPage("history");
      await page.locator('[data-testid="history-v2-generation-card"]').first().click();
      const historyOverlay = page.locator(".comfymodal-studio-viewer-overlay");
      await expect(historyOverlay).toBeVisible();
      await expect(historyOverlay.locator('[data-testid="viewer-timing"]')).toBeVisible({ timeout: 15000 });
      const historyHtml = await viewerHtml(page);

      fs.mkdirSync(path.join(process.cwd(), "test-results"), { recursive: true });
      fs.writeFileSync(
        path.join(process.cwd(), "test-results", "shared-viewer-parity.json"),
        JSON.stringify({
          playgroundGenerationRequests: playgroundRequests,
          historyGenerationRequests: genRequests.slice(playgroundRequests.length),
          playgroundLen: playgroundHtml.length,
          historyLen: historyHtml.length,
        }, null, 2),
      );

      checkNaming(playgroundHtml, historyHtml);

      // The preview resolved the durable record through the bridged
      // generation id — exactly one detail fetch, no run-id miss — and
      // History fetches that same record.
      expect(playgroundRequests).toHaveLength(1);
      expect(playgroundRequests[0]).toMatch(/\/generations\/gen_[0-9a-f]{12}$/);
      expect(genRequests.slice(playgroundRequests.length)).toEqual(playgroundRequests);

      // The rendered DOM is byte-identical.
      expect(playgroundHtml).not.toBeNull();
      expect(playgroundHtml).toBe(historyHtml);

      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("playground preview resolves an unbridged run through its history entry", async ({ page }) => {
    // Strip the bridged generation id from the run response AND the legacy
    // history entry: the preview must still reach the same durable record via
    // the legacy entry's internal run id, exactly like a run recorded before
    // the bridge existed.
    await page.route("**/comfymodal/studio/run", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      delete body.historyGenerationId;
      delete body.history_generation_id;
      await route.fulfill({
        status: res.status(),
        headers: res.headers(),
        body: JSON.stringify(body),
      });
    });
    await page.route("**/comfymodal/history?*", async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      if (body && Array.isArray(body.items)) {
        for (const item of body.items) {
          delete item.history_generation_id;
          delete item.historyGenerationId;
        }
      }
      await route.fulfill({
        status: res.status(),
        headers: res.headers(),
        body: JSON.stringify(body),
      });
    });

    const genRequests = [];
    page.on("request", (r) => {
      if (/history-v2\/generations\//.test(r.url())) genRequests.push(r.url());
    });

    const fx = await setupFakeTest(page);
    try {
      await selectWorkflow(page);
      await page.locator('[data-testid="shelf-input-prompt"]').fill("A blue fox beside a silver lake");
      await page.locator('[data-testid="run-btn"]').click();
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 15000 });

      await page.locator('[data-testid="canvas-output"]').click();
      const playgroundOverlay = page.locator(".comfymodal-studio-viewer-overlay");
      await expect(playgroundOverlay).toBeVisible();
      await expect(playgroundOverlay.locator('[data-testid="viewer-timing"]')).toBeVisible({ timeout: 15000 });
      const playgroundHtml = await viewerHtml(page);
      const playgroundRequests = [...genRequests];
      await page.keyboard.press("Escape");
      await expect(page.locator(".comfymodal-studio-viewer-overlay")).toHaveCount(0);

      await fx.gotoPage("history");
      await page.locator('[data-testid="history-v2-generation-card"]').first().click();
      const historyOverlay = page.locator(".comfymodal-studio-viewer-overlay");
      await expect(historyOverlay).toBeVisible();
      await expect(historyOverlay.locator('[data-testid="viewer-timing"]')).toBeVisible({ timeout: 15000 });
      const historyHtml = await viewerHtml(page);

      checkNaming(playgroundHtml, historyHtml);

      // The preview reached the same durable record History fetches for this
      // run — through the legacy entry's internal run id, since the response
      // carried no bridge.  What matters is the outcome (same record id on
      // both sides), not how many misses preceded it.
      const previewIds = playgroundRequests.map((u) => u.split("/generations/")[1]);
      const historyIds = genRequests.slice(playgroundRequests.length)
        .map((u) => u.split("/generations/")[1]);
      expect(previewIds.length).toBeGreaterThanOrEqual(1);
      expect(previewIds[previewIds.length - 1]).toMatch(/^gen_[0-9a-f]{12}$/);
      expect(historyIds).toEqual([previewIds[previewIds.length - 1]]);

      expect(playgroundHtml).not.toBeNull();
      expect(playgroundHtml).toBe(historyHtml);

      // A run-id miss 404s truthfully; nothing else may error.
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });
});
