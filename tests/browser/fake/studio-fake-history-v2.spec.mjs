// Modal Studio — History V2 regression tests against the deterministic fake
// backend.  The Studio's History page runs in "auto" mode (real HTTP adapter,
// see helpers.mjs openStudio), so every assertion exercises the actual
// /comfymodal/history-v2/* endpoints implemented by fake-backend.mjs.
//
// Determinism: every test gets a fresh session (fresh server-side state) and
// a fresh browser context (fresh localStorage view-state).  The default seed
// is 48 records (39 generations + 9 experiments); the newest-first visible
// feed starts gen_ok, gen_interrupted, exp_completed, ...

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

// The default visible statuses the UI sends (completed|running|completed_with_failures|interrupted).
const DEFAULT_VISIBLE_TOTAL = 45;

test.describe("Studio History V2 (fake backend, real adapter)", () => {
  test("1. feed renders cards and result count via the real v2 adapter", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Prove the REAL HTTP adapter is in use: a /history-v2/feed request must
      // fire when the History page mounts, and no fixture "Demo data" banner
      // may render.
      const feedReq = page.waitForRequest((r) => /\/comfymodal\/history-v2\/feed/.test(r.url()));
      await fx.gotoPage("history");
      await feedReq;

      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({
        timeout: 10000,
      });
      await expect(page.locator('[data-testid="history-v2-result-count"]')).toHaveText(
        DEFAULT_VISIBLE_TOTAL + " results",
        { timeout: 10000 }
      );
      await expect(page.locator(".comfymodal-studio-history-v2-mode-banner")).toBeHidden();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("2. generation detail overlay renders prompt, params, attempts and served images", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();

      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      // Record-status chip (the attempt line renders its own completed chip too).
      await expect(
        overlay.locator(".comfymodal-studio-history-v2-run-line .comfymodal-studio-history-v2-chip.status-completed")
      ).toHaveText("Completed");

      // Parameters (9 canonical keys seeded on every generation).
      await expect(overlay.locator(".comfymodal-studio-history-v2-param")).toHaveCount(9);
      await expect(overlay.locator(".comfymodal-studio-history-v2-param-key", { hasText: "Seed" }).first()).toBeVisible();

      // Attempt history (1 attempt) + note/favorite controls present.
      await expect(overlay.locator(".comfymodal-studio-history-v2-attempt")).toHaveCount(1);
      await expect(overlay.locator("textarea.comfymodal-studio-history-v2-notes")).toBeVisible();
      await expect(overlay.locator(".comfymodal-studio-history-v2-fav")).toBeVisible();

      // Featured image is a served PNG that actually loads.
      const featured = overlay.locator(".comfymodal-studio-history-v2-featured-img");
      await expect(featured).toBeVisible();
      const fsrc = await featured.getAttribute("src");
      expect(fsrc).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(await featured.evaluate((img) => img.naturalWidth > 0)).toBe(true);
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb").first()).toBeVisible();

      // Unknown-id contract (not reachable via the UI).
      const r404 = await page.request.get(
        `/comfymodal/history-v2/generations/nope?session=${fx.sessionId}`
      );
      expect(r404.status()).toBe(404);
      expect(await r404.json()).toEqual({ status: "error", message: "generation not found" });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("3. experiment detail renders ordered cells, counts, axes and cell pane", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();

      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator(".comfymodal-studio-history-v2-experiment-title")).toHaveText(
        "Seed Sweep — completed"
      );
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("4 results");
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("4 total cells");
      await expect(page.locator(".comfymodal-studio-history-v2-experiment-axis")).toContainText("Axis X: seed");
      await expect(page.locator(".comfymodal-studio-history-v2-experiment-axis")).toContainText("Axis Y: steps");

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await expect(cells).toHaveCount(4);
      const keys = await cells.evaluateAll((els) => els.map((el) => el.getAttribute("data-key")));
      expect(keys).toEqual([
        "exp_completed_cell_0",
        "exp_completed_cell_1",
        "exp_completed_cell_2",
        "exp_completed_cell_3",
      ]);

      // Completed cells carry served PNG thumbs that load.
      const cellImg = cells.first().locator("img.comfymodal-studio-history-v2-thumb-img");
      await expect(cellImg).toBeVisible();
      const cellSrc = await cellImg.getAttribute("src");
      expect(cellSrc).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(await cellImg.evaluate((img) => img.naturalWidth > 0)).toBe(true);

      // Selecting a cell opens the detail pane.  The tiles are grid cells with
      // role="button"; activate the first one with keyboard (Enter) since the
      // huge matrix cell center sits outside the viewport (a plain click would
      // scroll-fight forever).
      await cells.nth(0).focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-testid="history-v2-cell-detail"]')).toBeVisible();
      await expect(page.locator('[data-testid="history-v2-cell-detail"]')).toContainText("Preview available");

      // Unknown-id contract.
      const r404 = await page.request.get(
        `/comfymodal/history-v2/experiments/nope?session=${fx.sessionId}`
      );
      expect(r404.status()).toBe(404);
      expect(await r404.json()).toEqual({ status: "error", message: "experiment not found" });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("4. favorite toggles and persists server-side across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      const star = card.locator(".comfymodal-studio-history-v2-fav");
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await star.click();
      await expect(star).toHaveAttribute("aria-pressed", "true");

      const state = await fx.getState();
      const entry = state.historyV2.find((r) => r.id === "gen_ok");
      expect(entry.favorite).toBe(true);

      // Reload (same session — the fake server outlives the navigation).
      await fx.reload();
      await fx.gotoPage("history");
      const card2 = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card2).toBeVisible({ timeout: 15000 });
      await expect(card2.locator(".comfymodal-studio-history-v2-fav")).toHaveAttribute(
        "aria-pressed",
        "true"
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("5. generation note persists server-side across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();

      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      const notes = overlay.locator("textarea.comfymodal-studio-history-v2-notes");
      await notes.fill("persisted deterministic note");
      await overlay.getByRole("button", { name: "Save note" }).click();
      // The notes section's status line is the first action-note in the overlay
      // (the Actions/Generate section has its own action-note span).
      await expect(overlay.locator(".comfymodal-studio-history-v2-action-note").first()).toHaveText("Saved", {
        timeout: 5000,
      });

      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_ok").note).toBe("persisted deterministic note");

      await fx.reload();
      await fx.gotoPage("history");
      await page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]').click();
      await expect(overlay.locator("textarea.comfymodal-studio-history-v2-notes")).toHaveValue(
        "persisted deterministic note",
        { timeout: 10000 }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. featured output selection persists server-side across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_multi"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();

      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      const thumbs = overlay.locator(".comfymodal-studio-history-v2-output-thumb");
      await expect(thumbs).toHaveCount(3);
      await expect(thumbs.nth(0)).toHaveClass(/featured/);

      // Open the output-3 action menu and set output 3 as featured.
      await overlay.getByRole("button", { name: "Output 3 actions" }).click();
      await page.getByRole("button", { name: "Set as featured" }).click();
      await expect(thumbs.nth(2)).toHaveClass(/featured/, { timeout: 10000 });

      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_multi").featured_output_index).toBe(2);

      await fx.reload();
      await fx.gotoPage("history");
      await page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_multi"]').click();
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb").nth(2)).toHaveClass(
        /featured/,
        { timeout: 10000 }
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. generation card thumbnails load served PNG assets", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      const thumb = card.locator("img.comfymodal-studio-history-v2-thumb-img");
      const src = await thumb.getAttribute("src");
      expect(src).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(await thumb.evaluate((img) => img.naturalWidth > 0)).toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8. missing original asset 404s and does not break the card", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_original_failed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      // The card thumb is the served preview/thumb (200) — no No-image fallback.
      const thumb = card.locator("img.comfymodal-studio-history-v2-thumb-img");
      await expect(thumb).toBeVisible();
      expect(await thumb.evaluate((img) => img.naturalWidth > 0)).toBe(true);
      await expect(card.locator(".comfymodal-studio-history-v2-noimage")).toHaveCount(0);

      // The original output references a registered-but-unserved asset: the
      // URL is non-empty (original_failed=true) but GET 404s — mirroring a
      // missing managed file in production.
      const detailRes = await page.request.get(
        `/comfymodal/history-v2/generations/gen_original_failed?session=${fx.sessionId}`
      );
      const item = (await detailRes.json()).item;
      const originalUrl = item.outputs[0].original_url;
      expect(originalUrl).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(item.outputs[0].original_failed).toBe(true);
      const r404 = await page.request.get(`${originalUrl}?session=${fx.sessionId}`);
      expect(r404.status()).toBe(404);
      expect(await r404.json()).toEqual({ status: "error", message: "asset not found" });

      // Bogus asset id → the same 404 JSON envelope.
      const rBad = await page.request.get(
        `/comfymodal/history-v2/assets/ast_does_not_exist?session=${fx.sessionId}`
      );
      expect(rBad.status()).toBe(404);
      expect(await rBad.json()).toEqual({ status: "error", message: "asset not found" });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("9. completed_with_failures experiment renders its canonical chip and failed cells", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_with_failures"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      // completed_with_failures is a canonical wire status with its own
      // label/class — no status-running fallback, no raw-status text.
      await expect(card.locator(".comfymodal-studio-history-v2-chip.status-completed_with_failures")).toHaveText(
        "Completed with failures"
      );
      await expect(card.locator(".comfymodal-studio-history-v2-card-name")).toHaveText(
        "Seed Sweep — partial"
      );
      await expect(card.locator(".comfymodal-studio-history-v2-card-counts")).toContainText("2 results");

      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("2 results");
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("2 failed");

      const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
      await expect(cells).toHaveCount(4);
      await expect(cells.nth(2).locator(".comfymodal-studio-history-v2-chip.status-failed")).toHaveText("Failed");
      await expect(cells.nth(3).locator(".comfymodal-studio-history-v2-chip.status-failed")).toHaveText("Failed");
      // Failed cells have no image → the cell shows the "No image" placeholder.
      await expect(cells.nth(2).locator(".comfymodal-studio-history-v2-cell-empty")).toBeVisible();

      // Selecting a failed cell surfaces its error in the detail pane.
      await cells.nth(2).focus();
      await page.keyboard.press("Enter");
      await expect(page.locator('[data-testid="history-v2-cell-detail"]')).toContainText(
        "worker restart exceeded retry budget"
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("10. interrupted generation renders its chip by default", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_interrupted"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await expect(card.locator(".comfymodal-studio-history-v2-chip.status-interrupted")).toHaveText(
        "Interrupted"
      );
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("11. canceled generation renders after toggling canceled visible", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      const toolbar = page.locator(".comfymodal-studio-history-v2-toolbar");
      await toolbar.locator('button[data-status="canceled"]').click();

      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_canceled"]');
      await expect(card).toBeVisible({ timeout: 10000 });
      await expect(card.locator(".comfymodal-studio-history-v2-chip.status-canceled")).toHaveText("Canceled");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("12. sort: all six orders return 200 with correctly ordered feeds", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({ timeout: 10000 });
      const sort = page.locator('[aria-label="Sort history"]');

      // newest (default) → gen_ok (base +6h, the newest completed record).
      await expect(page.locator('.comfymodal-studio-history-v2-card[data-id="gen_ok"]').first()).toBeVisible({
        timeout: 10000,
      });

      // oldest → gen_v2_29 (base −19h44m, the oldest visible record).
      await sort.selectOption("oldest");
      await expect(page.locator('.comfymodal-studio-history-v2-card[data-id="gen_v2_29"]').first()).toBeVisible({
        timeout: 10000,
      });

      // fastest → the shortest-duration visible record (gen_no_image, 1500ms).
      await sort.selectOption("fastest");
      await expect(page.locator('.comfymodal-studio-history-v2-card[data-id="gen_no_image"]').first()).toBeVisible({
        timeout: 10000,
      });

      // slowest → the longest-duration visible record (gen_v2_23, 5300ms).
      await sort.selectOption("slowest");
      await expect(page.locator('.comfymodal-studio-history-v2-card[data-id="gen_v2_23"]').first()).toBeVisible({
        timeout: 10000,
      });

      // Workflow A-Z / Z-A: the production API accepts workflow_asc/desc
      // (the UI dropdown sends those canonical values via the real HTTP
      // adapter) — assert the API names through the real HTTP adapter with
      // the default statuses.
      const feedQuery = `statuses=success,running,partial,interrupted&limit=24&session=${fx.sessionId}`;

      const ascRes = await page.request.get(
        `/comfymodal/history-v2/feed?${feedQuery}&order=workflow_asc`
      );
      expect(ascRes.status()).toBe(200);
      const asc = await ascRes.json();
      expect(asc.items.length).toBeGreaterThan(0);
      // workflow_asc → alphabetically first workflow first (experiment name).
      expect(asc.items[0].id).toBe("exp_completed");

      const descRes = await page.request.get(
        `/comfymodal/history-v2/feed?${feedQuery}&order=workflow_desc`
      );
      expect(descRes.status()).toBe(200);
      const desc = await descRes.json();
      expect(desc.items.length).toBeGreaterThan(0);
      // workflow_desc → alphabetically last workflow first (wf_portrait, oldest first).
      expect(desc.items[0].id).toBe("gen_v2_27");

      // All six orders are accepted now — no intentional 400 responses.
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("13. load more paginates the history_v2_large seed without duplicates", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const seeded = await fx.seedHistory("history_v2_large");
      expect(seeded.count).toBe(80);

      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="history-v2-result-count"]')).toHaveText("72 results", {
        timeout: 10000,
      });
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({ timeout: 10000 });

      const results = page.locator('[data-testid="history-v2-results"]');
      const loadMore = page.locator('[data-testid="history-v2-load-more"]');
      let clicks = 0;
      while ((await loadMore.count()) > 0 && clicks < 10) {
        const before = await results.locator(".comfymodal-studio-history-v2-card").count();
        await loadMore.click();
        await expect
          .poll(async () => results.locator(".comfymodal-studio-history-v2-card").count(), {
            timeout: 10000,
            message: "load more should append cards",
          })
          .toBeGreaterThan(before);
        clicks += 1;
      }

      const ids = await results.locator(".comfymodal-studio-history-v2-card").evaluateAll((els) =>
        els.map((el) => el.getAttribute("data-id"))
      );
      expect(ids.length).toBe(72);
      expect(new Set(ids).size).toBe(72);
      expect(clicks).toBe(2); // 72 = 3 pages of 24 → 2 "Load more" clicks
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("14. search filter is retained across load more", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      const search = page.locator('[data-testid="history-v2-search"]');
      await search.fill("bulk deterministic");
      await expect(page.locator('[data-testid="history-v2-result-count"]')).toHaveText("30 results", {
        timeout: 10000,
      });

      const results = page.locator('[data-testid="history-v2-results"]');
      const loadMore = page.locator('[data-testid="history-v2-load-more"]');
      await expect(loadMore).toBeVisible();
      await loadMore.click();
      await expect
        .poll(async () => results.locator(".comfymodal-studio-history-v2-card").count(), {
          timeout: 10000,
          message: "load more should append the remaining search matches",
        })
        .toBe(30);

      // Filter state retained: the search box keeps its value and every card
      // still matches the query.
      await expect(search).toHaveValue("bulk deterministic");
      const prompts = await results.locator(".comfymodal-studio-history-v2-card-prompt").allTextContents();
      expect(prompts.length).toBe(30);
      for (const p of prompts) expect(p).toContain("bulk deterministic");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("15. simulated feed failure surfaces the real error with no fixture fallback", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const failRes = await page.request.post("/__comfymodal_test/history-v2-fail", {
        data: { mode: "feed", sessionId: fx.sessionId },
      });
      expect(failRes.ok()).toBe(true);

      await fx.reload();
      await fx.gotoPage("history");
      await expect(page.locator(".comfymodal-studio-history-v2-state-error")).toBeVisible({ timeout: 10000 });
      await expect(page.locator(".comfymodal-studio-history-v2-state-error")).toContainText(
        "Could not load history"
      );
      await expect(page.locator(".comfymodal-studio-history-v2-state-error")).toContainText("HTTP 500");
      await expect(page.locator(".comfymodal-studio-history-v2-card")).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-history-v2-mode-banner")).toBeHidden();

      const clearRes = await page.request.post("/__comfymodal_test/history-v2-fail", {
        data: { mode: null, sessionId: fx.sessionId },
      });
      expect(clearRes.ok()).toBe(true);
      await fx.reload();
      await fx.gotoPage("history");
      await expect(page.locator(".comfymodal-studio-history-v2-card").first()).toBeVisible({ timeout: 10000 });
      // The intentional 500 from fail-mode is logged by Chromium as a console
      // resource error — expected for this test.
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("16. missing-duration records render in newest and oldest orders with pagination", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      const toolbar = page.locator(".comfymodal-studio-history-v2-toolbar");
      await toolbar.locator('button[data-status="failed"]').click();
      await toolbar.locator('button[data-status="canceled"]').click();

      // Newest order: the missing-duration records (duration_ms null) sit on
      // the first page and render with their chips.
      await expect(
        page.locator(
          '.comfymodal-studio-history-v2-generation-card[data-id="gen_interrupted"] .comfymodal-studio-history-v2-chip.status-interrupted'
        )
      ).toBeVisible({ timeout: 10000 });
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

      // Oldest order: those same records are at the far end — page through to
      // them (48 records = 2 pages).
      const sort = page.locator('[aria-label="Sort history"]');
      await sort.selectOption("oldest");
      await expect(page.locator('.comfymodal-studio-history-v2-card[data-id="gen_v2_29"]').first()).toBeVisible({
        timeout: 10000,
      });
      const results = page.locator('[data-testid="history-v2-results"]');
      const loadMore = page.locator('[data-testid="history-v2-load-more"]');
      let clicks = 0;
      while ((await loadMore.count()) > 0 && clicks < 10) {
        const before = await results.locator(".comfymodal-studio-history-v2-card").count();
        await loadMore.click();
        await expect
          .poll(async () => results.locator(".comfymodal-studio-history-v2-card").count(), {
            timeout: 10000,
            message: "load more should append cards in oldest order",
          })
          .toBeGreaterThan(before);
        clicks += 1;
      }
      await expect(
        page.locator(
          '.comfymodal-studio-history-v2-generation-card[data-id="gen_interrupted"] .comfymodal-studio-history-v2-chip.status-interrupted'
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

  test("17. failed zero-output generation detail renders status/error/attempt instead of 'not found'", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
      const toolbar = page.locator(".comfymodal-studio-history-v2-toolbar");
      await toolbar.locator('button[data-status="failed"]').click();

      // gen_failed is a legitimate failed generation with ZERO outputs and an
      // attempt error.  The detail overlay must NOT treat it as "not found".
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_failed"]');
      await expect(card).toBeVisible({ timeout: 10000 });
      await card.click();

      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });

      // No "Generation not found" placeholder state (the load_failed/not_found
      // sentinel), and the failed chip renders with the real label.
      await expect(overlay.locator(".comfymodal-studio-history-v2-state")).toHaveCount(0, { timeout: 10000 });
      await expect(overlay.locator(".comfymodal-studio-history-v2-chip.status-failed").first()).toHaveText("Failed");

      // Errors + attempts carry the real server-side error text.
      await expect(overlay.locator(".comfymodal-studio-history-v2-error-line")).toContainText(
        "Modal worker crashed: CUDA out of memory"
      );
      await expect(overlay.locator(".comfymodal-studio-history-v2-attempt")).toHaveCount(1);
      await expect(overlay.locator(".comfymodal-studio-history-v2-attempt-error")).toContainText(
        "Modal worker crashed: CUDA out of memory"
      );

      // Unavailable output/snapshot sections are omitted: no featured image,
      // no other-output thumbnails, and the Generate Original action is
      // disabled (nothing to generate from).
      await expect(overlay.locator(".comfymodal-studio-history-v2-featured-img")).toHaveCount(0);
      await expect(overlay.locator(".comfymodal-studio-history-v2-output-thumb")).toHaveCount(0);
      await expect(overlay.locator('[data-testid="history-v2-generate-original"]')).toBeDisabled();

      // Metadata still renders (Run ID row present).
      await expect(overlay.locator(".comfymodal-studio-history-v2-row-key", { hasText: "Run ID" })).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
