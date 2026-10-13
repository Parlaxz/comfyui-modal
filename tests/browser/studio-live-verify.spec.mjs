// LIVE verification (temporary — delete after green).
import { test, expect } from "@playwright/test";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

async function openViewer(page, genId) {
  await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
  const err = await page.evaluate(async (id) => {
    try {
      const styles = await import("/extensions/comfyui-modal/studio-styles.js");
      if (styles.ensureStudioStyles) styles.ensureStudioStyles();
      const repoMod = await import("/extensions/comfyui-modal/history-v2-repository.js");
      const detailMod = await import("/extensions/comfyui-modal/studio-history-v2-detail.js");
      const repo = await repoMod.createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
      await detailMod.renderGenerationDetail(id, repo, {});
      return "";
    } catch (e) { return String((e && e.stack) || e); }
  }, genId);
  expect(err, "overlay setup failed").toBe("");
  const overlay = page.locator(".comfymodal-studio-viewer-overlay");
  await expect(overlay).toBeVisible({ timeout: 20000 });
  return overlay;
}

function rowByKey(overlay, key) {
  return overlay.locator(".comfymodal-studio-viewer-row", { hasText: key });
}

test.describe("live format truth", () => {
  test("webp-bytes-in-png-name reads webp, variant stays per-record", async ({ page }) => {
    const overlay = await openViewer(page, "gen_0afc7361ddd2");
    await expect(rowByKey(overlay, "Format").locator(".comfymodal-studio-viewer-row-value"))
      .toHaveText("webp");
    await expect(rowByKey(overlay, "Variant").locator(".comfymodal-studio-viewer-row-value"))
      .toHaveText("Original");
    await expect(rowByKey(overlay, "File size").locator(".comfymodal-studio-viewer-row-value"))
      .toHaveText("167.3 KB");
  });

  test("data-saver record still reads Data Saver (no regression)", async ({ page }) => {
    const overlay = await openViewer(page, "gen_f4e1bf7525ea");
    await expect(rowByKey(overlay, "Variant").locator(".comfymodal-studio-viewer-row-value"))
      .toHaveText("Data Saver");
  });
});
