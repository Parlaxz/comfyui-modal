// Modal Studio — History tests against the deterministic fake backend.
//
// The Studio's History page is the History V2 feed (web/studio-history-v2.js).
// helpers.mjs openStudio() defaults to history mode "auto", so the page talks
// to the real HTTP adapter backed by the fake engine's /comfymodal/history-v2/*
// endpoints (see fake-backend.mjs).  The fake engine's legacy /history +
// /run-history endpoints still back the Playground carousel; they are
// exercised in test "a" via fx.seedHistory (the legacy seed control).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

test.describe("Studio History V2 (fake backend, real adapter)", () => {
  test("a. history renders the engine-backed grid, cards and pagination", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Exercise the engine's legacy history-seed control (backs the
      // Playground carousel via /history — the V2 feed is unaffected).
      const seeded = await fx.seedHistory("history_large");
      expect(seeded.total).toBeGreaterThan(0);

      await fx.gotoPage("history");

      const pageEl = page.locator('[data-testid="history-v2-page"]');
      await expect(pageEl).toBeVisible({ timeout: 15000 });
      const results = page.locator('[data-testid="history-v2-results"]');
      await expect(results.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({
        timeout: 10000,
      });

      // Result count + "Load more" pagination.  The default V2 seed has 45
      // records matching the default visible statuses (24 per page → hasMore).
      await expect(page.locator('[data-testid="history-v2-result-count"]')).toContainText("results", {
        timeout: 10000,
      });
      const loadMore = page.locator('[data-testid="history-v2-load-more"]');
      await expect(loadMore).toBeVisible();
      const countBefore = await results.locator(".comfymodal-studio-history-v2-card").count();
      await loadMore.click();
      await expect
        .poll(async () => results.locator(".comfymodal-studio-history-v2-card").count(), {
          timeout: 10000,
          message: "load more should append additional cards",
        })
        .toBeGreaterThan(countBefore);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("b. completed generation records show prompt, completed chip and a served PNG image", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });

      // gen_ok is the newest completed generation in the default seed and is
      // the first card in the newest-first feed.
      const genCard = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(genCard).toBeVisible({ timeout: 10000 });
      await expect(genCard.locator(".comfymodal-studio-history-v2-chip.status-completed")).toHaveText(
        "Completed",
        { timeout: 5000 }
      );
      await expect(genCard.locator(".comfymodal-studio-history-v2-card-prompt")).not.toBeEmpty({
        timeout: 5000,
      });
      const thumb = genCard.locator("img.comfymodal-studio-history-v2-thumb-img");
      await expect(thumb).toBeVisible({ timeout: 10000 });
      const src = await thumb.getAttribute("src");
      // Engine-served deterministic PNG, not a fixture SVG data-URI.
      expect(src).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(await thumb.evaluate((img) => img.naturalWidth > 0)).toBe(true);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("c. failed and canceled statuses render without breaking after toggling", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({
        timeout: 10000,
      });

      // Interrupted is visible by default (DEFAULT_HIDDEN_STATUSES hides only
      // failed + canceled).  gen_interrupted is the 2nd card in the feed.
      await expect(
        page.locator(
          '.comfymodal-studio-history-v2-generation-card[data-id="gen_interrupted"] .comfymodal-studio-history-v2-chip.status-interrupted'
        )
      ).toBeVisible({ timeout: 10000 });

      // failed + canceled are hidden by default; toggling them on must render
      // their cards.  Both records are newer than everything on page 1, so no
      // Load More is needed (unlike the old fixture dataset).
      const toolbar = page.locator(".comfymodal-studio-history-v2-toolbar");
      await toolbar.locator('button[data-status="failed"]').click();
      await toolbar.locator('button[data-status="canceled"]').click();

      await expect(
        page.locator(
          '.comfymodal-studio-history-v2-generation-card[data-id="gen_failed"] .comfymodal-studio-history-v2-chip.status-failed'
        )
      ).toBeVisible({ timeout: 10000 });
      await expect(
        page.locator(
          '.comfymodal-studio-history-v2-generation-card[data-id="gen_canceled"] .comfymodal-studio-history-v2-chip.status-canceled'
        )
      ).toBeVisible({ timeout: 10000 });

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
