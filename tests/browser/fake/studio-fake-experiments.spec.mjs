// Modal Studio — seeded experiment records route through History V2 (fake
// backend).
//
// H-WAVE D retired the Playground's legacy experiment surface entirely: the
// experiment-grid-viewport can never render, and "reopening an experiment"
// now means opening its durable History V2 detail page.  These tests keep
// coverage for the compatibility behavior that must survive: a seeded V2
// dataset containing experiments surfaces them as EXP-badged recent-runs
// filmstrip items, clicking one opens [data-testid="history-v2-page"] +
// [data-testid="history-v2-experiment-page"], the legacy grid viewport never
// mounts, and no GET /comfymodal/experiments/ read is made after mount.
//
// Every dataset here is seeded through the fake API BEFORE mount
// (harness-only write); the UI itself only ever reads /history-v2/*.

import { test, expect } from "@playwright/test";
import { setupFakeTest, seedHistory } from "./helpers.mjs";

const LEGACY_EXPERIMENT_READ_RE = /\/comfymodal\/experiments\//;
const GRID_VIEWPORT = '[data-testid="experiment-grid-viewport"]';

/** Track page GETs against the retired legacy experiments read API. */
function trackLegacyExperimentReads(page) {
  const reads = [];
  const onRequest = (request) => {
    if (request.method() === "GET" && LEGACY_EXPERIMENT_READ_RE.test(request.url())) {
      reads.push(request.url());
    }
  };
  page.on("request", onRequest);
  return { reads, dispose() { page.off("request", onRequest); } };
}

async function clickFilmstripExperiment(page, selector = ".comfymodal-studio-carousel-item-experiment") {
  const item = page.locator(selector).first();
  await expect(item).toBeVisible({ timeout: 20000 });
  // Read the id BEFORE clicking — the click navigates to History and the
  // Playground filmstrip unmounts.
  const expId = await item.getAttribute("data-expid");
  await item.click();
  return expId;
}

async function assertOpensHistoryV2Detail(page, fx, tracker) {
  await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 15000 });

  // The retired legacy grid can never mount again.
  expect(await page.locator(GRID_VIEWPORT).count()).toBe(0);
  // And the reopen never consulted the legacy experiments read API.
  expect(tracker.reads).toEqual([]);
  fx.assertNoConsoleErrors();
}

test.describe("Studio filmstrip EXP opens History V2 detail (fake backend, post-Wave-D)", () => {
  test("a. filmstrip EXP item from a seeded V2 dataset opens the History V2 experiment detail", async ({ page }) => {
    let seeded = null;
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        seeded = await seedHistory(p, sessionId, "history_v2_large");
      },
    });
    expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_large", v2: true });
    const tracker = trackLegacyExperimentReads(page);
    try {
      const expId = await clickFilmstripExperiment(page);
      expect(expId).toBeTruthy();

      await assertOpensHistoryV2Detail(page, fx, tracker);
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("b. several EXP filmstrip items each route to their own History V2 detail", async ({ page }) => {
    let seeded = null;
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ page: p, sessionId }) => {
        seeded = await seedHistory(p, sessionId, "history_v2_large");
      },
    });
    expect(seeded).toMatchObject({ status: "ok", v2: true });
    const tracker = trackLegacyExperimentReads(page);
    try {
      // The default fresh-session seed already yields multiple EXP items;
      // exercise the first three deterministically.
      const total = Math.min(3, await page.locator(".comfymodal-studio-carousel-item-experiment").count());
      expect(total).toBeGreaterThanOrEqual(2);
      for (let i = 0; i < total; i++) {
        await fx.gotoPage("playground");
        const item = page.locator(".comfymodal-studio-carousel-item-experiment").nth(i);
        await expect(item).toBeVisible({ timeout: 15000 });
        await item.click();
        await assertOpensHistoryV2Detail(page, fx, tracker);
      }
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });

  test("c. a completed-with-failures experiment also opens the History V2 detail (failed cells stay failed)", async ({ page }) => {
    // Default fresh-session V2 seed: exp_with_failures ("Seed Sweep —
    // partial") carries permanently failed cells; there is no grid to retry
    // them in anymore — the durable detail page is the only owner.
    const fx = await setupFakeTest(page);
    const tracker = trackLegacyExperimentReads(page);
    try {
      await clickFilmstripExperiment(page, '.comfymodal-studio-carousel-item[data-expid="exp_with_failures"]');
      await assertOpensHistoryV2Detail(page, fx, tracker);

      // The failed-cell aggregate is visible on the detail page.
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toContainText("fail", {
        timeout: 10000,
        ignoreCase: true,
      });
    } finally {
      tracker.dispose();
      fx.guard.dispose();
    }
  });
});
