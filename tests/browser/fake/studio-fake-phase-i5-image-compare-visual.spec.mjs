// Phase I5 — bounded visual evidence (fake backend).
//
// Two stable captures of the sanctioned lightweight A/B compare view:
//   - desktop 50/50 comparison
//   - narrow (480px) stacked comparison
//
// Deterministic without masks: the fake engine serves deterministic PNG
// bytes, and every visible compare string is caller-supplied static copy
// ("Preview" / "Original" / fixed hint) — no random asset ids are rendered.
// Regenerate with:
//   npx playwright test --config=playwright.fake.config.mjs \
//     -g "I5 compare visual" --update-snapshots

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

test.describe("I5 compare visual baselines", () => {
  const DIALOG = '[data-testid="cm-compare-dialog"]';

  async function seedAndOpen(page) {
    const t = await setupFakeTest(page);
    await t.gotoPage("history");
    await page.locator('[data-testid="history-v2-generation-card"]').first().waitFor({
      state: "visible",
      timeout: 15000,
    });
    const assetUrl = await page
      .locator("img.comfymodal-studio-history-v2-thumb-img")
      .first()
      .getAttribute("src");
    await page.evaluate(async ({ url }) => {
      const m = await import("/extensions/comfymodal-modal/studio-image-compare.js");
      m.startCompare({ descriptor: { url, label: "Preview", kind: "preview" } });
      m.addToCompareB({ descriptor: { url, label: "Original", kind: "original" } });
      m.openCompareView(null);
    }, { url: assetUrl });
    await expect(page.locator('[data-testid="cm-compare-overlay"]')).toBeVisible();
    await expect(page.locator('[data-testid="cm-compare-img-b"]')).toHaveAttribute(
      "data-loaded",
      "true",
      { timeout: 15000 }
    );
    return t;
  }

  test("desktop 50/50 comparison", async ({ page }) => {
    const t = await seedAndOpen(page);
    try {
      await expect(page.locator(DIALOG)).toHaveScreenshot("i5-compare-desktop.png");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });

  test("narrow stacked comparison (480px)", async ({ page }) => {
    const t = await seedAndOpen(page);
    try {
      await page.setViewportSize({ width: 480, height: 900 });
      await expect(page.locator('[data-testid="cm-compare-stage"]')).toHaveAttribute(
        "data-mode",
        "stacked"
      );
      await expect(page.locator(DIALOG)).toHaveScreenshot("i5-compare-narrow.png");
      t.assertNoConsoleErrors();
    } finally {
      t.guard.dispose();
    }
  });
});
