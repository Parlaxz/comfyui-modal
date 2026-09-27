// Modal Studio — History V2 annotation correctness (F2 follow-up A).
//
// Focused fake-backend coverage for durable favorite/note flows:
//   - feed Generation favorite FAILURE recovery (no stranded control, no
//     unhandled rejection, truthful revert, later retry succeeds)
//   - canonical CELL favorite ownership: a cell's favorite IS its
//     Generation's favorite (repo.setFavorite(cell.generationId, …)), with
//     durable refetch + full-reload persistence
//   - whole-Experiment favorite/note independence + persistence, including
//     clear-to-empty
//   - Generation note clear-to-empty
//
// Failure injection is one-shot/request-scoped: /__comfymodal_test/history-
// v2-fail {mode:"favorite_once"} fails exactly the NEXT favorite PATCH, or a
// page.route gate holds+fails a single request for deterministic in-flight
// assertions.  The backend is never globally broken.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const FAV_FAIL_ROUTE = "**/history-v2/generations/*/favorite";

async function injectFavoriteOnceFailure(page, sessionId) {
  const res = await page.request.post("/__comfymodal_test/history-v2-fail", {
    data: { mode: "favorite_once", sessionId },
  });
  if (!res.ok()) throw new Error(`favorite_once fail-mode injection failed: HTTP ${res.status()}`);
  return res.json();
}

async function openExperimentCellPane(page, experimentCardId) {
  const card = page.locator(`.comfymodal-studio-history-v2-experiment-card[data-id="${experimentCardId}"]`);
  await expect(card).toBeVisible({ timeout: 15000 });
  await card.click();
  await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });
  const cells = page.locator('[data-testid="history-v2-experiment-cell"]');
  await expect(cells.first()).toBeVisible({ timeout: 10000 });
  // Keyboard activation of the cell tile (matrix centers can sit offscreen).
  await cells.nth(0).focus();
  await page.keyboard.press("Enter");
  const paneStar = page.locator('[data-testid="history-v2-cell-detail"] [data-testid="history-v2-cell-favorite"]');
  await expect(paneStar).toBeVisible({ timeout: 10000 });
  return { cells, paneStar };
}

test.describe("Studio History V2 annotations (fake backend, F2A)", () => {

  test("A1. feed favorite failure recovers truthfully and a later retry succeeds", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      const star = card.locator(".comfymodal-studio-history-v2-fav");
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await expect(star).toHaveText("\u2606");
      // Native button semantics.
      expect(await star.evaluate((el) => el.tagName)).toBe("BUTTON");

      // One-shot failure injection: exactly the next favorite PATCH 500s.
      await injectFavoriteOnceFailure(page, fx.sessionId);
      await star.click();

      // Rejected PATCH: star re-enables, prior durable state restored,
      // bounded truthful error surfaced — no stranded control.
      await expect(star).toBeEnabled({ timeout: 10000 });
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await expect(star).toHaveText("\u2606");
      await expect(card.locator(".comfymodal-studio-history-v2-action-note")).toHaveText("Favorite failed");
      const state1 = await fx.getState();
      expect(state1.historyV2.find((r) => r.id === "gen_ok").favorite).toBe(false);

      // No unhandled promise rejection reached the page.
      fx.assertNoConsoleErrors([/Failed to load resource/]);

      // Card remains usable/openable after the failure.
      await card.click();
      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      await page.keyboard.press("Escape");
      await expect(overlay).toBeHidden({ timeout: 10000 });

      // Later retry succeeds through the real backend (keyboard activation).
      await star.focus();
      await page.keyboard.press("Enter");
      await expect(star).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(star).toHaveText("\u2605");
      const state2 = await fx.getState();
      expect(state2.historyV2.find((r) => r.id === "gen_ok").favorite).toBe(true);
      await expect(card.locator(".comfymodal-studio-history-v2-action-note")).toHaveText("");
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("A2. feed star is disabled while the request is in flight and reverts on rejection", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      const star = card.locator(".comfymodal-studio-history-v2-fav");
      await expect(star).toHaveAttribute("aria-pressed", "false");

      // Request-scoped gate: hold the single PATCH open, then fail it.
      let release;
      const gated = new Promise((resolve) => { release = resolve; });
      await page.route(FAV_FAIL_ROUTE, async (route) => {
        await gated;
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ status: "error", message: "simulated favorite failure" }),
        });
      });

      await star.click();
      await expect(star).toBeDisabled();
      await expect(card.locator('[data-testid="history-v2-favorite-star"]')).toBeDisabled();

      release();
      await expect(star).toBeEnabled({ timeout: 10000 });
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await expect(star).toHaveText("\u2606");

      // Duplicate clicks during flight are impossible (disabled guard) and
      // the server never recorded anything.
      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_ok").favorite).toBe(false);

      await page.unroute(FAV_FAIL_ROUTE);
      await star.click();
      await expect(star).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("A3. cell favorite drives the Generation route, persists across reload, leaves the Experiment favorite untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // phase_e seed: exp_phase_e_original's cell carries a REAL Generation
      // record (gen_phase_e_original_cell_0) — canonical production shape.
      const seeded = await fx.seedHistory("history_v2_phase_e_original");
      expect(seeded.count).toBeGreaterThan(0);

      await fx.gotoPage("history");
      const { paneStar } = await openExperimentCellPane(page, "exp_phase_e_original");
      await expect(paneStar).toBeEnabled();
      await expect(paneStar).toHaveAttribute("aria-pressed", "false");

      const expHeaderStar = page.locator(
        ".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav"
      );
      await expect(expHeaderStar).toHaveAttribute("aria-pressed", "false");

      await paneStar.click();

      // Success comes from server acknowledgement + durable refetch: the
      // rebuilt pane reflects the Generation favorite, focus is preserved.
      await expect(paneStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(paneStar).toBeFocused();
      await expect(paneStar).toBeEnabled();

      // Durable truth: the GENERATION carries the favorite; the whole
      // Experiment favorite is unchanged.
      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0").favorite).toBe(true);
      expect(state.historyV2.find((r) => r.id === "exp_phase_e_original").favorite).toBe(false);

      // Full reload preserves the favorite (server truth, no local cache).
      await fx.reload();
      await fx.gotoPage("history");
      const { paneStar: reloadedStar } = await openExperimentCellPane(page, "exp_phase_e_original");
      await expect(reloadedStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(reloadedStar).toHaveText("\u2605");

      // Feed semantics stay consistent wherever that Generation appears.
      await page.getByRole("button", { name: "\u2190 Back to history" }).click();
      await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 10000 });
      const genCard = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_phase_e_original_cell_0"]');
      await expect(genCard.locator(".comfymodal-studio-history-v2-fav")).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      const expCard = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_phase_e_original"]');
      await expect(expCard.locator(".comfymodal-studio-history-v2-fav")).toHaveAttribute("aria-pressed", "false");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("A4. cell favorite failure leaves no local state and reload shows server truth", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.seedHistory("history_v2_phase_e_original");
      await fx.gotoPage("history");
      const { paneStar } = await openExperimentCellPane(page, "exp_phase_e_original");
      await expect(paneStar).toHaveAttribute("aria-pressed", "false");

      await injectFavoriteOnceFailure(page, fx.sessionId);
      await paneStar.click();

      // Rejected write: nothing survives locally as if saved.
      await expect(paneStar).toBeEnabled({ timeout: 10000 });
      await expect(paneStar).toHaveAttribute("aria-pressed", "false");
      await expect(paneStar).toHaveText("\u2606");
      await expect(
        page.locator('[data-testid="history-v2-cell-detail"] .comfymodal-studio-history-v2-action-note').first()
      ).toHaveText("Favorite failed");

      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_phase_e_original_cell_0").favorite).toBe(false);
      expect(state.historyV2.find((r) => r.id === "exp_phase_e_original").favorite).toBe(false);

      // Reload shows server truth.
      await fx.reload();
      await fx.gotoPage("history");
      const { paneStar: reloadedStar } = await openExperimentCellPane(page, "exp_phase_e_original");
      await expect(reloadedStar).toHaveAttribute("aria-pressed", "false", { timeout: 10000 });
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("A5. whole-experiment favorite and note persist across reload; note clears to empty", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="history-v2-experiment-page"]')).toBeVisible({ timeout: 10000 });

      const headerStar = page.locator(
        ".comfymodal-studio-history-v2-experiment-title-row .comfymodal-studio-history-v2-fav"
      );
      await expect(headerStar).toHaveAttribute("aria-pressed", "false");
      await headerStar.click();
      await expect(headerStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });

      const notes = page.locator('textarea[aria-label="Note for this experiment"]');
      await notes.fill("durable experiment note");
      await page.getByRole("button", { name: "Save note" }).click();
      await expect(page.locator(".comfymodal-studio-history-v2-section .comfymodal-studio-history-v2-action-note")).toHaveText(
        "Saved",
        { timeout: 5000 }
      );

      let state = await fx.getState();
      const exp = () => state.historyV2.find((r) => r.id === "exp_completed");
      expect(exp().favorite).toBe(true);
      expect(exp().note).toBe("durable experiment note");

      // Reload/reopen: both persisted.
      await fx.reload();
      await fx.gotoPage("history");
      await page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]').click();
      await expect(headerStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      await expect(notes).toHaveValue("durable experiment note", { timeout: 10000 });

      // Clear-to-empty is a durable clear.
      await notes.fill("");
      await page.getByRole("button", { name: "Save note" }).click();
      await expect(page.locator(".comfymodal-studio-history-v2-section .comfymodal-studio-history-v2-action-note")).toHaveText(
        "Saved",
        { timeout: 5000 }
      );

      await fx.reload();
      await fx.gotoPage("history");
      await page.locator('.comfymodal-studio-history-v2-experiment-card[data-id="exp_completed"]').click();
      await expect(notes).toHaveValue("", { timeout: 10000 });
      // Favorite unaffected by the note operations.
      await expect(headerStar).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });

      state = await fx.getState();
      expect(exp().note).toBe("");
      expect(exp().favorite).toBe(true);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("A6. generation note clears to empty and stays empty across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("history");
      const card = page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]');
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();

      const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
      await expect(overlay).toBeVisible({ timeout: 10000 });
      const notes = overlay.locator("textarea.comfymodal-studio-history-v2-notes");
      // The note-save status lives in the Note section's action row — scope
      // to the row containing the Save control (the F6 download note is an
      // earlier action-note in the overlay).
      const statusEl = overlay
        .locator(".comfymodal-studio-history-v2-action-row")
        .filter({ hasText: "Save note" })
        .locator(".comfymodal-studio-history-v2-action-note");

      await notes.fill("temporary note");
      await overlay.getByRole("button", { name: "Save note" }).click();
      await expect(statusEl).toHaveText("Saved", { timeout: 5000 });

      // Clear to empty — the backend accepts "" as a durable clear.
      await notes.fill("");
      await overlay.getByRole("button", { name: "Save note" }).click();
      await expect(statusEl).toHaveText("Saved", { timeout: 5000 });

      const state = await fx.getState();
      expect(state.historyV2.find((r) => r.id === "gen_ok").note).toBe("");

      await fx.reload();
      await fx.gotoPage("history");
      await page.locator('.comfymodal-studio-history-v2-generation-card[data-id="gen_ok"]').click();
      await expect(overlay.locator("textarea.comfymodal-studio-history-v2-notes")).toHaveValue("", { timeout: 10000 });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
