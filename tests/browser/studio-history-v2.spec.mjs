// Modal Studio — History V2 feed E2E (fixture mode)
//
// Drives the History V2 feed page (web/studio-history-v2.js) plus the
// generation detail overlay (web/studio-history-v2-detail.js) and the
// experiment detail page (web/studio-history-v2-experiment.js) against the
// DETERMINISTIC fixture repository (web/history-v2-fixtures.js).
//
// Fixture mode is forced via window.__COMFYMODAL_HISTORY_MODE__ = "fixture"
// set with page.addInitScript BEFORE navigation.  In fixture mode the
// repository is fully in-memory: no /comfymodal/history network calls at
// all.  The studio mock API is still installed so the shell/playground's
// other /comfymodal calls are satisfied during app startup.
//
// Dataset facts used by these tests (deterministic, from history-v2-fixtures.js):
//   28 generations: gen_001..gen_028 (14 success, 4 interrupted, 4 failed,
//     4 canceled, 2 running) — gen_003 4 outputs, gen_005
//     preview-ok-original-failed, gen_014 no image, gen_018/gen_022 preview-only.
//   7 experiments: exp_001 (12 cells all success), exp_002 (1), exp_003 (2),
//     exp_004 (3), exp_005 (8 cells: 5 success / 3 failed, partial),
//     exp_006 (4 failed), exp_007 (6 cells: 2 success / 4 interrupted).
//
// Default visible totals (DEFAULT_HIDDEN_STATUSES hides failed + canceled):
//   generations visible = 14 success + 4 interrupted + 2 running = 20
//   experiments visible = exp_001..exp_005 + exp_007                  = 6
//   feed total                                                          = 26
// Enabling the Failed + Canceled toggles → all 28 + 7 = 35.
// Feed page size is 24 → first page 24 cards, "Load more" for the rest.

import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// App-level console noise unrelated to the History V2 pipeline (mirrors
// studio-features.spec.mjs): sibling plugin lanes re-register extension
// names and the shared ComfyUI server emits internal 404s during startup.
// The History V2 fixture path itself makes NO /comfymodal requests.
const APP_NOISE_PATTERNS = [
  "already registered",      // sibling lanes re-register extension names
  "vite:preloadError",       // ComfyUI app preload failures
  "Failed to load resource", // app-internal 404s (/lm/settings, pysssss)
  "ComfyApp graph accessed", // app startup before a graph is loaded
];

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitVisible(page, locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

/** All feed cards (generation + experiment) in render order. */
function historyCards(page) {
  return page.locator(
    '[data-testid="history-v2-generation-card"], [data-testid="history-v2-experiment-card"]'
  );
}

function resultCount(page) {
  return page.locator('[data-testid="history-v2-result-count"]');
}

/** Open a generation card by id and wait for the detail dialog. */
async function openGenerationDetail(page, id) {
  await waitVisible(page, page.locator(`[data-testid="history-v2-generation-card"][data-id="${id}"]`));
  await page.locator(`[data-testid="history-v2-generation-card"][data-id="${id}"]`).click();
  const dialog = page.getByRole("dialog", { name: "Generation detail" });
  await expect(dialog).toBeVisible({ timeout: 10000 });
  return dialog;
}

test.describe("History V2", () => {
  let api;

  test.beforeEach(async ({ page }) => {
    // Force fixture mode BEFORE any navigation (the UI reads
    // window.__COMFYMODAL_HISTORY_MODE__ when the history page mounts).
    await page.addInitScript(() => {
      window.__COMFYMODAL_HISTORY_MODE__ = "fixture";
    });
    api = await installStudioMockApi(page);
    // The Studio shell fetches GET /comfymodal/studio/workflows on startup.
    // installWorkflowsMock registers a narrower route (and no catch-all), so
    // it can sit alongside the shared mock without shadowing its handlers.
    await installWorkflowsMock(page);
    await openStudio(page, COMFYUI_URL);
    // Clear persisted view state so a previous test's filters never leak in.
    await page.evaluate(() => localStorage.clear());
    await page.locator('.comfymodal-studio-topnav [data-page="history"]').click();
    // Feed readiness: the first fetch resolves (default filters) to 26 items.
    await expect(resultCount(page)).toHaveText("26 results", { timeout: 10000 });
  });

  // ── Test 1: mixed feed renders ───────────────────────────────────────
  test("1. mixed feed renders", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible();
      await expect(page.locator('[data-testid="history-v2-generation-card"]').first()).toBeVisible();
      await expect(page.locator('[data-testid="history-v2-experiment-card"]').first()).toBeVisible();

      // Fixture mode banner is visible and labeled "Demo data".
      const banner = page.locator('[data-testid="history-v2-mode-banner"]');
      await expect(banner).toBeVisible({ timeout: 10000 });
      await expect(banner).toHaveText("Demo data");

      // Facet options are populated from the fixture dataset.
      await expect(
        page.locator('select[aria-label="Filter by workflow"] option', { hasText: "Portrait Pro" })
      ).toHaveCount(1);
      await expect(
        page.locator('select[aria-label="Filter by workflow"] option', { hasText: "Clean Workflow" })
      ).toHaveCount(1);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: failed and canceled hidden by default ────────────────────
  test("2. failed and canceled hidden by default", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // No failed/canceled chips on the default page.
      await expect(page.locator(".comfymodal-studio-history-v2-chip.status-failed")).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-history-v2-chip.status-canceled")).toHaveCount(0);
      await expect(resultCount(page)).toHaveText("26 results");

      // Enable both hidden statuses → all 35 items.
      await page.locator('[data-status="failed"]').click();
      await page.locator('[data-status="canceled"]').click();
      await expect(resultCount(page)).toHaveText("35 results", { timeout: 10000 });

      // Failed chips (gen_019..gen_022) are on the first page (newest first)…
      await expect(page.locator(".comfymodal-studio-history-v2-chip.status-failed").first()).toBeVisible();
      // …but the canceled items (gen_023..gen_026) sit on page 2 — load more.
      await page.locator('[data-testid="history-v2-load-more"]').click();
      await expect(page.locator(".comfymodal-studio-history-v2-chip.status-canceled").first()).toBeVisible({ timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 3: interrupted visible by default ───────────────────────────
  test("3. interrupted visible by default", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // gen_015..gen_018 (interrupted) are on the first page.
      await expect(page.locator(".comfymodal-studio-history-v2-chip.status-interrupted").first()).toBeVisible();

      // exp_007 (interrupted) is on page 2 (newest-first order) — load more.
      await page.locator('[data-testid="history-v2-load-more"]').click();
      const exp7 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_007"]');
      await expect(exp7).toBeVisible({ timeout: 10000 });
      await expect(exp7.locator(".comfymodal-studio-history-v2-chip.status-interrupted")).toBeVisible();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 4: search and kind filter interact ──────────────────────────
  test("4. search and kind filter interact", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // "portrait" matches the "Portrait Pro" workflow: gen_001..gen_008
      // (8 generations) + exp_001/exp_002 (2 experiments) = 10.
      const searchInput = page.locator('[data-testid="history-v2-search"]');
      await searchInput.fill("portrait");
      await expect(resultCount(page)).toHaveText("10 results", { timeout: 10000 });

      // Kind filter narrows to generations only.
      await page.locator('[data-kind="generation"]').click();
      await expect(resultCount(page)).toHaveText("8 results", { timeout: 10000 });

      // Back to All keeps the search active.
      await page.locator('[data-kind="all"]').click();
      await expect(resultCount(page)).toHaveText("10 results", { timeout: 10000 });

      // Clear all restores the full default feed.
      await page.getByRole("button", { name: "Clear all" }).click();
      await expect(resultCount(page)).toHaveText("26 results", { timeout: 10000 });
      await expect(searchInput).toHaveValue("");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 5: experiment card uses 2x2 cover ───────────────────────────
  test("5. experiment card uses 2x2 cover", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // exp_001: 4 filled slots, 0 empty.
      const exp1 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_001"]');
      await expect(exp1).toBeVisible();
      await expect(exp1.locator(".comfymodal-studio-history-v2-cover-slot img")).toHaveCount(4);
      await expect(exp1.locator(".comfymodal-studio-history-v2-cover-empty")).toHaveCount(0);

      // exp_002: exactly 1 filled + 3 empty (dashed placeholder) slots.
      const exp2 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_002"]');
      await expect(exp2).toBeVisible();
      await expect(exp2.locator(".comfymodal-studio-history-v2-cover-slot img")).toHaveCount(1);
      await expect(exp2.locator(".comfymodal-studio-history-v2-cover-empty")).toHaveCount(3);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 6: true result count on experiment card ─────────────────────
  test("6. true result count on experiment card", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // exp_001 (12 success) and exp_002 (1 success) are on page 1.
      const exp1 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_001"]');
      await expect(exp1).toBeVisible();
      await expect(exp1).toContainText("12 results");
      const exp2 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_002"]');
      await expect(exp2).toContainText("1 result");

      // exp_005 is on page 2 — load more to surface it.
      await page.locator('[data-testid="history-v2-load-more"]').click();
      const exp5 = page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_005"]');
      await expect(exp5).toBeVisible({ timeout: 10000 });
      // Result count reflects SUCCESSFUL results (5), not total cells (8).
      await expect(exp5).toContainText("5 results");
      await expect(exp5).not.toContainText("8 results");
      await expect(exp5).not.toContainText("+8");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 7: generation detail panel ──────────────────────────────────
  test("7. generation detail panel", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const dialog = await openGenerationDetail(page, "gen_001");

      // Workflow name with version suffix in the Workflow section. The version
      // label arrives pre-prefixed ("v3"), so this also pins that the renderer
      // does not double the "v".
      await expect(dialog.getByText("Portrait Pro v3", { exact: true })).toBeVisible();

      // Params section with the fixture defaults (seed 42, steps 28).
      const paramsSection = dialog.locator(".comfymodal-studio-history-v2-section", { hasText: "Parameters" });
      await expect(paramsSection).toBeVisible();
      await expect(paramsSection.locator(".comfymodal-studio-history-v2-param", { hasText: "Seed" })).toContainText("42");
      await expect(paramsSection.locator(".comfymodal-studio-history-v2-param", { hasText: "Steps" })).toContainText("28");

      // Fixture records carry timing → timing rows, not the diagnostics placeholder.
      await expect(dialog.locator('[data-testid="history-v2-timing-placeholder"]')).toHaveCount(0);
      await expect(dialog.locator(".comfymodal-studio-history-v2-section", { hasText: "Timing" })).toBeVisible();
      await expect(dialog.locator(".comfymodal-studio-history-v2-row-key", { hasText: "End-to-End Total" })).toBeVisible();

      // Close via the X button removes the overlay from the DOM.
      await dialog.locator(".comfymodal-studio-history-v2-overlay-close").click();
      await expect(page.getByRole("dialog", { name: "Generation detail" })).toHaveCount(0);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 8: experiment detail page ───────────────────────────────────
  test("8. experiment detail page", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await waitVisible(page, page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_001"]'));
      await page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_001"]').click();

      const expPage = page.locator('[data-testid="history-v2-experiment-page"]');
      await expect(expPage).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("12 results");
      await expect(page.locator('[data-testid="history-v2-experiment-counts"]')).toContainText("12 total cells");
      await expect(page.locator('[data-testid="history-v2-experiment-cell"]')).toHaveCount(12);
      await expect(page.locator('[data-testid="history-v2-experiment-retry"]')).toBeVisible();

      // Back returns to the feed.
      await page.locator(".comfymodal-studio-history-v2-back").click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toHaveCount(0);
      await expect(resultCount(page)).toBeVisible();
      await expect(resultCount(page)).toHaveText("26 results");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 9: featured output change via menu ──────────────────────────
  test("9. featured output change via menu", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const dialog = await openGenerationDetail(page, "gen_003");

      // Capture the current featured image src (output 0 by default).
      const featuredImg = dialog.locator(".comfymodal-studio-history-v2-featured-img");
      await expect(featuredImg).toBeVisible();
      const beforeSrc = await featuredImg.getAttribute("src");
      expect(beforeSrc).toBeTruthy();

      // Open the overflow menu on output 2 (index 1) and set it as featured.
      // The overflow menu is a body-level popover (position: fixed), so it is
      // NOT a descendant of the dialog.
      await dialog.locator('[aria-label="Output 2 actions"]').click();
      const menuItem = page.locator(".comfymodal-studio-history-v2-menu-item", { hasText: "Set as featured" });
      await expect(menuItem).toBeVisible({ timeout: 5000 });
      await expect(menuItem).toBeEnabled();
      await menuItem.click();

      // The overlay reloads with the new featured output → src must change.
      await page.waitForFunction(
        (prev) => {
          const img = document.querySelector(".comfymodal-studio-history-v2-featured-img");
          return img && img.getAttribute("src") !== prev;
        },
        beforeSrc,
        { timeout: 10000 }
      );
      const afterSrc = await page.locator(".comfymodal-studio-history-v2-featured-img").getAttribute("src");
      expect(afterSrc).not.toBe(beforeSrc);

      // Output 2 (index 1) now carries the featured marker/title.
      await expect(
        page.locator('.comfymodal-studio-history-v2-output-thumb[title="Featured output"]')
      ).toHaveCount(1);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 10: notes and favorites ─────────────────────────────────────
  test("10. notes and favorites", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // Favorite toggle on the gen_001 card.
      const star = page.locator(
        '[data-testid="history-v2-generation-card"][data-id="gen_001"] [data-testid="history-v2-favorite-star"]'
      );
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await expect(star).toHaveText("\u2606");
      await star.click();
      await expect(star).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(star).toHaveText("\u2605");

      // Open the same generation and save a note.
      const dialog = await openGenerationDetail(page, "gen_001");
      const notes = dialog.locator('textarea[aria-label="Note for this generation"]');
      await notes.fill("e2e test note");
      await dialog.getByRole("button", { name: "Save note" }).click();
      await expect(
        dialog.getByTestId("history-v2-note-status", { hasText: "Saved" })
      ).toBeVisible({ timeout: 10000 });

      // Close and reopen — the fixture repository persists in memory, so the
      // note survives within the test.
      await dialog.locator(".comfymodal-studio-history-v2-overlay-close").click();
      await expect(page.getByRole("dialog", { name: "Generation detail" })).toHaveCount(0);
      const dialog2 = await openGenerationDetail(page, "gen_001");
      await expect(dialog2.locator('textarea[aria-label="Note for this generation"]')).toHaveValue("e2e test note", { timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 11: pagination load more ────────────────────────────────────
  test("11. pagination load more", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // Default feed: 26 total → first page exactly 24 cards, Load more shown.
      await expect(historyCards(page)).toHaveCount(24);
      const loadMore = page.locator('[data-testid="history-v2-load-more"]');
      await expect(loadMore).toBeVisible();

      await loadMore.click();
      await expect(historyCards(page)).toHaveCount(26, { timeout: 10000 });
      await expect(loadMore).toHaveCount(0); // removed once hasMore is false

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });
});
