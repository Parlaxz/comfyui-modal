// Modal Studio — Experiment-mode tests against the deterministic fake backend.
//
// The fake session seeds ONE preset; experiment mode needs 2+ unique presets,
// so every test creates a compare snapshot+preset via the fake REST API in
// `beforeMount` (before the Studio's first preset fetch — web/studio-backend.js
// caches runtime presets per apiBase).

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  createComparePreset,
  selectPreset,
  enableExperimentMode,
  selectComparePreset,
  submitExperiment,
} from "./helpers.mjs";

const SEEDED_PRESET_ID = "preset_default";

async function cellStatus(grid, cellKey) {
  const vals = await grid
    .locator(`[data-testid="experiment-cell-${cellKey}"]`)
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-cell-status")));
  return vals[0] || null;
}

test.describe("Studio Experiments (fake backend)", () => {
  test("a. two-cell experiment renders exactly two cell cards", async ({ page }) => {
    let compareId = "";
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ sessionId }) => {
        compareId = await createComparePreset(page, sessionId);
      },
    });
    try {
      await fx.setScenario("experiment_two_cell");
      await selectPreset(page, SEEDED_PRESET_ID);
      await enableExperimentMode(page);
      await selectComparePreset(page, compareId);
      await submitExperiment(page);

      const grid = page.locator('[data-testid="experiment-grid-viewport"]');
      await expect(grid).toBeVisible({ timeout: 20000 });
      const cells = grid.locator(".comfymodal-studio-experiment-grid-cell");
      await expect(cells).toHaveCount(2, { timeout: 15000 });

      // Both cells eventually complete (terminal arrives ~700ms after submit,
      // the UI observes it on the first 3s poll).
      await expect
        .poll(async () => {
          const statuses = await cells.evaluateAll((els) =>
            els.map((el) => el.getAttribute("data-cell-status"))
          );
          return statuses.filter((s) => s === "completed").length;
        }, { timeout: 20000, message: "both experiment cells should complete" })
        .toBe(2);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("b. cells update independently as fake responses arrive", async ({ page }) => {
    let compareId = "";
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ sessionId }) => {
        compareId = await createComparePreset(page, sessionId);
      },
    });
    try {
      // delayed_cells: cell_0 completes at ~220ms, cell_1 at ~1500ms,
      // cell_2 at ~3200ms; terminal at ~3600ms.  The UI observes these on
      // its 3s poll, so at the first poll cell_0 is done while cell_2 is
      // still pending, and the second poll shows everything completed.
      await fx.setScenario("delayed_cells");
      await selectPreset(page, SEEDED_PRESET_ID);
      await enableExperimentMode(page);
      await selectComparePreset(page, compareId);
      await submitExperiment(page);

      const grid = page.locator('[data-testid="experiment-grid-viewport"]');
      await expect(grid).toBeVisible({ timeout: 20000 });

      await expect
        .poll(async () => {
          const c0 = await cellStatus(grid, "cell_0");
          const c2 = await cellStatus(grid, "cell_2");
          return c0 === "completed" && c2 === "pending";
        }, {
          timeout: 20000,
          message: "cell_0 should complete while cell_2 is still pending",
        })
        .toBe(true);

      await expect
        .poll(
          async () => {
            const c0 = await cellStatus(grid, "cell_0");
            const c1 = await cellStatus(grid, "cell_1");
            const c2 = await cellStatus(grid, "cell_2");
            return c0 === "completed" && c1 === "completed" && c2 === "completed";
          },
          { timeout: 25000, message: "all cells should eventually complete" }
        )
        .toBe(true);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("c. a failed cell remains failed", async ({ page }) => {
    let compareId = "";
    const fx = await setupFakeTest(page, {
      beforeMount: async ({ sessionId }) => {
        compareId = await createComparePreset(page, sessionId);
      },
    });
    try {
      // experiment_one_failed_cell: 3 cells, cell_1 fails, the other two
      // complete (partial success terminal).
      await fx.setScenario("experiment_one_failed_cell");
      await selectPreset(page, SEEDED_PRESET_ID);
      await enableExperimentMode(page);
      await selectComparePreset(page, compareId);
      await submitExperiment(page);

      const grid = page.locator('[data-testid="experiment-grid-viewport"]');
      await expect(grid).toBeVisible({ timeout: 20000 });

      const failedCell = grid.locator('[data-testid="experiment-cell-cell_1"]');
      await expect
        .poll(() => cellStatus(grid, "cell_1"), {
          timeout: 20000,
          message: "cell_1 should be failed",
        })
        .toBe("failed");
      await expect(failedCell.locator(".cm-exp-cell-icon-fail")).toBeVisible({ timeout: 5000 });

      // The other cells completed (partial success is still a valid grid).
      await expect.poll(() => cellStatus(grid, "cell_0"), { timeout: 20000 }).toBe("completed");
      await expect.poll(() => cellStatus(grid, "cell_2"), { timeout: 20000 }).toBe("completed");

      // Wait one full poll cadence — the failed cell must NOT flip or vanish.
      await page.waitForTimeout(3500);
      expect(await cellStatus(grid, "cell_1")).toBe("failed");

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
