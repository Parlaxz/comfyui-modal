// Modal Studio — Playground tests against the deterministic fake backend.
//
// Each test gets a fresh session (isolated server-side state), a console
// guard installed before the Studio mounts, and the real Studio UI mounted
// in the harness page.  See tests/browser/fake/FAKE_BACKEND_GUIDE.md.

import { test, expect } from "@playwright/test";
import {
  setupFakeTest,
  selectPreset,
  submitSingleRun,
} from "./helpers.mjs";

const SEEDED_PRESET_ID = "preset_default";

test.describe("Studio Playground (fake backend)", () => {
  test("a. Studio loads — nav renders and playground is visible", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator('[data-testid="control-panel"]')).toBeVisible({ timeout: 10000 });
      const nav = page.locator(".comfymodal-studio-topnav");
      for (const name of ["Playground", "History", "Backend", "Settings"]) {
        await expect(nav.getByRole("button", { name })).toBeVisible();
      }
      await expect(page.locator('[data-testid="workspace"]')).toBeVisible({ timeout: 10000 });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("b. fake run is submitted and completes", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);

      const runBtn = await submitSingleRun(page);

      // An intermediate status (running/submitted/waiting/queued) must appear
      // before the terminal completion.
      await expect
        .poll(async () => (await runBtn.textContent()).trim(), {
          timeout: 10000,
          message: "expected an intermediate run status on the Run button",
        })
        .toMatch(/Running|Submitted|Waiting|Queued/);

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await expect(runBtn).toBeEnabled();
      await expect(page.locator('[data-testid="run-status-message"]')).toContainText("Run completed");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("c. progress appears during a sampler_progress run", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("sampler_progress");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      // The progress section is display:none until the run enters an active
      // state; the sampler step line is populated by scoped-tracker events.
      await expect(page.locator('[data-testid="progress-section"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="progress-step"]')).toContainText("Sampler:", {
        timeout: 10000,
      });

      await fx.waitForStatus("Run completed", { timeout: 20000 });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("d. completion displays the scenario output asset", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      const canvas = page.locator('[data-testid="canvas-output"]');
      await expect(canvas).toBeVisible({ timeout: 20000 });
      const src = await canvas.getAttribute("src");
      expect(src).toBeTruthy();
      // H-WAVE D: the finalized run is selected from the History V2 feed, so
      // the canvas displays a durable history-v2 asset URL (legacy run
      // outputs may still surface as /assets/ or /studio/outputs/ paths).
      expect(src).toMatch(/\/comfymodal\/(history-v2\/assets|assets|studio\/outputs)\//);

      // Cross-check against the engine's journal: the rendered image must
      // belong to this run — the V2 mirror keys its asset ids off the
      // experiment id, and legacy-shaped URLs embed the primary asset id.
      const state = await fx.getState();
      const experiment = state.experiments && state.experiments[0];
      expect(experiment, "expected one experiment in session state").toBeTruthy();
      const cellCompleted = (experiment.journalDetail || []).find((e) => e.type === "cell.completed");
      expect(cellCompleted, "expected a cell.completed journal entry").toBeTruthy();
      const assetId = cellCompleted.payload && cellCompleted.payload.primary_asset_id;
      if (assetId) {
        const srcMatchesAsset =
          src.indexOf(encodeURIComponent(assetId)) !== -1 ||
          src.indexOf(assetId) !== -1 ||
          src.indexOf(encodeURIComponent(experiment.experiment_id)) !== -1 ||
          src.indexOf(experiment.experiment_id) !== -1;
        expect(srcMatchesAsset, "canvas src correlates to the completed run").toBe(true);
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("e. execution failure shows the Run Failed state with Dismiss/Retry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("execution_failure");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      const section = page.locator(".comfymodal-studio-run-section");
      await expect(section).toContainText("Run Failed", { timeout: 20000 });
      // Dismiss button = explicit failure-state affordance.
      await expect(page.locator('[data-testid="error-dismiss-btn"]')).toBeVisible({ timeout: 5000 });
      // Retry = the Run button is re-enabled after the failure.
      await expect(page.locator('[data-testid="run-btn"]')).toBeEnabled({ timeout: 5000 });
      const reasonText = await section.textContent();
      expect(reasonText.toLowerCase()).toContain("out of memory");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("f. an unrelated fake run does not hijack the active run UI", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.setScenario("success");
      await selectPreset(page, SEEDED_PRESET_ID);
      await submitSingleRun(page);

      const canvas = page.locator('[data-testid="canvas-output"]');
      await expect(canvas).toBeVisible({ timeout: 20000 });
      const srcBefore = await canvas.getAttribute("src");
      expect(srcBefore).toBeTruthy();

      // Inject tracker events for a FOREIGN experiment id — these must not
      // touch the completed run's UI (the scoped tracker is disposed and
      // identity-scoped, and the poller has stopped).
      await fx.injectEvent("experiment.worker.progress", {
        experiment_id: "exp_foreign_hijack",
        cell_key: "cell_0",
        total_nodes: 8,
        type: "sampler.step",
        step: 12,
        max: 20,
        message: "foreign sampler progress",
      });
      await fx.injectEvent("experiment.event", {
        type: "experiment.failed_fatal",
        experiment_id: "exp_foreign_hijack",
        error: "foreign failure — must not appear in the active run UI",
      });

      // Give the 40ms pump time to dispatch both events, then assert the
      // active run UI is unchanged.
      await page.waitForTimeout(400);
      expect(await canvas.getAttribute("src")).toBe(srcBefore);
      await expect(page.locator('[data-testid="run-status-message"]')).toContainText("Run completed");
      await expect(page.locator(".comfymodal-studio-run-section")).not.toContainText("Run Failed");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
