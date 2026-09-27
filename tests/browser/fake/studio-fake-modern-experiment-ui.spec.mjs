// Modal Studio — modern Experiment V2 user-facing flow against the fake API.

import { test, expect } from "@playwright/test";
import { setupFakeTest, enableExperimentMode } from "./helpers.mjs";

const WORKFLOW_SELECTOR = '[data-testid="workflow-selector"]';

test.describe("Studio Modern Experiment V2 UI (fake backend)", () => {
  test("submits one definition-derived matrix and hydrates flat status", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const createBodies = [];
    const onRequest = (request) => {
      if (request.method() === "POST" && request.url().endsWith("/studio/experiment-v2")) {
        createBodies.push(JSON.parse(request.postData() || "{}"));
      }
    };
    page.on("request", onRequest);

    try {
      await page.locator(WORKFLOW_SELECTOR).selectOption("wf_text2img");
      await expect(page.locator('[data-testid="workflow-control-seed"]')).toBeVisible({ timeout: 10000 });
      await enableExperimentMode(page);

      await expect(page.getByTestId("experiment-v2-section")).toBeVisible();
      await expect(page.getByTestId("run-experiment-inline-btn")).toHaveCount(0);

      await page.getByTestId("modern-experiment-submit-btn").click();
      await expect.poll(() => createBodies.length, { timeout: 10000 }).toBe(1);

      const body = createBodies[0];
      expect(body.experiment_id).toMatch(/^exp_v2_/);
      expect(body.definition.workflows[0]).toMatchObject({
        workflow_id: "wf_text2img",
        workflow_version_id: "wv1_latest",
        preset_id: "wpres_a",
      });
      expect(Object.prototype.hasOwnProperty.call(body, "cells")).toBe(false);
      expect(Object.prototype.hasOwnProperty.call(body, "concurrency")).toBe(false);

      const readActiveExperimentId = () => page.evaluate(() => {
        const raw = localStorage.getItem("comfymodal.studio.experiment.active.v1");
        return raw ? JSON.parse(raw).experimentId : "";
      });
      await expect.poll(readActiveExperimentId, { timeout: 10000 }).toBe(body.experiment_id);
      const experimentId = await readActiveExperimentId();
      expect(experimentId).toBe(body.experiment_id);

      const grid = page.getByTestId("experiment-v2-grid");
      await expect(grid).toBeVisible({ timeout: 10000 });
      await expect(grid.locator('[data-testid="experiment-v2-cell-cell_0"]')).toHaveCount(1);

      const stateRes = await page.request.post("/__comfymodal_test/modern-experiment-state", {
        data: {
          sessionId: fx.sessionId,
          experiment_id: experimentId,
          cells: [{ cell_id: "cell_0", status: "completed" }],
        },
      });
      expect(stateRes.ok()).toBe(true);

      await expect(
        grid.locator('[data-testid="experiment-v2-cell-cell_0"]')
      ).toHaveAttribute("data-cell-status", "completed", { timeout: 10000 });
      await expect(page.getByTestId("experiment-v2-progress")).toHaveText("1/1 complete");

      // The accepted modern experiment is also visible through the real
      // History V2 adapter/detail surface, not only the polling route.
      await fx.gotoPage("history");
      const card = page.locator(
        `.comfymodal-studio-history-v2-experiment-card[data-id="${experimentId}"]`
      );
      await expect(card).toBeVisible({ timeout: 10000 });
      await card.click();
      await expect(page.getByTestId("history-v2-experiment-page")).toBeVisible();
      await expect(page.locator('[data-testid="history-v2-experiment-cell"]')).toHaveCount(1);
      fx.assertNoConsoleErrors();
    } finally {
      page.off("request", onRequest);
      fx.guard.dispose();
    }
  });
});
