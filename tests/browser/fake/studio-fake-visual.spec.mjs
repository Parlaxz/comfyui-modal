// Modal Studio — visual baseline tests against the deterministic fake backend.
//
// Four stable-state screenshots.  Baselines live next to this spec in
// studio-fake-visual-spec snapshots/ (Playwright default naming).  Regenerate
// with:  npx playwright test --config=playwright.fake.config.mjs --update-snapshots
//
// Determinism notes:
//   - The engine serves deterministic PNGs, but per-run asset ids are RANDOM,
//     so experiment cell images are masked.
//   - The running state's progress section updates text/bar widths on 250ms
//     timers, so it is masked in the running capture.

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  selectPreset,
  submitSingleRun,
} from "./helpers.mjs";

const SEEDED_PRESET_ID = "preset_default";
const PAGE = ".comfymodal-studio-pagecontainer";

test.describe("Studio visual baselines (fake backend)", () => {
  test("playground idle", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectPreset(page, SEEDED_PRESET_ID);
      // Wait for the async preset load to settle (Run enabled) and for the
      // recent-runs filmstrip to hydrate from History V2 (the default fresh
      // session seed already yields /history-v2/feed items) before capturing.
      await expect(page.locator('[data-testid="run-btn"]')).toBeEnabled({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-carousel-item").first()).toBeVisible({
        timeout: 15000,
      });
      await expect(page.locator(PAGE)).toHaveScreenshot("playground-idle.png");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("playground running with progress", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("sampler_progress");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // Stable mid-run condition: the progress section is visible with a
      // sampler line populated by scoped-tracker events.
      await expect(page.locator('[data-testid="progress-section"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="progress-step"]')).toContainText("Sampler:", {
        timeout: 10000,
      });

      await expect(page.locator(PAGE)).toHaveScreenshot("playground-running.png", {
        // Elapsed timer (250ms), sampler burst (40ms), stage transitions and
        // bar fill all mutate during the run — mask the dynamic region.
        mask: [page.locator('[data-testid="progress-section"]')],
      });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("history grid", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");

      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({
        timeout: 10000,
      });
      // The default V2 seed serves deterministic PNG thumbs from
      // /comfymodal/history-v2/assets/* — wait for every page-1 thumbnail to
      // actually load (naturalWidth > 0) so the capture is stable.
      await expect
        .poll(async () => {
          const thumbs = page.locator("img.comfymodal-studio-history-v2-thumb-img");
          const n = await thumbs.count();
          if (n === 0) return false;
          const widths = await thumbs.evaluateAll((els) =>
            els.map((el) => el.naturalWidth)
          );
          return widths.every((w) => w > 0);
        }, { timeout: 15000, message: "all page-1 thumbnails should load" })
        .toBe(true);

      await expect(page.locator(PAGE)).toHaveScreenshot("history-grid.png");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("playground filmstrip with EXP-badged item", async ({ page }) => {
    // H-WAVE D: the legacy experiment grid visual baseline is retired — the
    // grid viewport can never render.  The Playground-side experiment
    // presence is now the recent-runs filmstrip EXP item, hydrated from the
    // default fresh-session History V2 seed.
    const fx = await setupFakeTest(page);
    try {
      await selectPreset(page, SEEDED_PRESET_ID);
      await expect(page.locator('[data-testid="run-btn"]')).toBeEnabled({ timeout: 15000 });

      const expItem = page.locator(".comfymodal-studio-carousel-item-experiment").first();
      await expect(expItem).toBeVisible({ timeout: 15000 });
      await expect(expItem.locator(".comfymodal-studio-carousel-exp-badge")).toHaveText("EXP");
      expect(await expItem.getAttribute("data-expid")).toBeTruthy();

      // Stable condition: every filmstrip thumbnail has actually loaded so
      // the capture is deterministic.
      await expect
        .poll(async () => {
          const thumbs = page.locator("img.comfymodal-studio-carousel-thumb");
          const n = await thumbs.count();
          if (n === 0) return false;
          const widths = await thumbs.evaluateAll((els) => els.map((el) => el.naturalWidth));
          return widths.every((w) => w > 0);
        }, { timeout: 15000, message: "all filmstrip thumbnails should load" })
        .toBe(true);

      await expect(page.locator(PAGE)).toHaveScreenshot("playground-filmstrip.png");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
