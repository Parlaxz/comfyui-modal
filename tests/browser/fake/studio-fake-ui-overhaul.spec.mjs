import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const WORKFLOW = '[data-testid="workflow-selector"]';

async function selectWorkflow(page) {
  await page.locator(WORKFLOW).selectOption("wf_text2img");
  await expect(page.locator('[data-testid="shelf-input-prompt"]')).toBeVisible({ timeout: 15000 });
}

test.describe("Studio UI overhaul", () => {
  test("shows the Settings deployment-needed hint in Playground", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("comfymodal.studio.golden.profile.v1", "golden_fake");
    });
    await page.route("**/comfymodal/studio/golden/profiles", (route) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        defaultProfile: "golden_fake",
        profiles: [{
          name: "golden_fake",
          deployed: false,
          target: { app: "batch-c0-p8-h100" },
        }],
      }),
    }));
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator('[data-testid="playground-golden-profile-deploy-status"]')).toContainText(
        "Not deployed. Deploying runs v2ctl for golden_fake (batch-c0-p8-h100).",
        { timeout: 10000 },
      );
      await expect(page.locator('[data-testid="playground-golden-profile-deploy"]')).toHaveText("Deploy golden_fake");
      await fx.gotoPage("settings");
      await expect(page.locator('[data-testid="settings-golden-profile-deploy-status"]')).toContainText("Not deployed", { timeout: 10000 });
      await expect(page.locator('[data-testid="settings-golden-profile-deploy"]')).toHaveText("Deploy golden_fake");
      fx.assertNoConsoleErrors([/Failed to load resource/]);
    } finally {
      fx.guard.dispose();
    }
  });

  test("places Redeploy beside the selected Golden profile dropdown", async ({ page }) => {
    let deployPosts = 0;
    await page.route("**/comfymodal/studio/golden/deploy", async (route) => {
      if (route.request().method() === "POST") {
        deployPosts += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "ok", profile: "golden_p1_parallel_c0_p8_h100" }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", state: "done" }),
      });
    });
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("settings");
      const bar = page.locator('[data-testid="settings-golden-profile-bar"]');
      await expect(bar.locator('[data-testid="settings-golden-profile"]')).toBeVisible();
      const redeploy = bar.locator('[data-testid="settings-golden-profile-deploy"]');
      await expect(redeploy).toHaveText("Redeploy");
      await redeploy.click();
      await expect.poll(() => deployPosts).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("keeps Run disabled when the selected workflow version is unrunnable", async ({ page }) => {
    const runPosts = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/comfymodal\/studio\/run$/.test(request.url())) runPosts.push(request.url());
    });
    const fx = await setupFakeTest(page);
    try {
      await page.locator(WORKFLOW).selectOption("wf_incomplete");
      await expect(page.locator('[data-testid="run-btn"]')).toBeDisabled({ timeout: 15000 });
      await expect(page.locator('[data-testid="workflow-run-gating"]')).not.toHaveText("Ready to run");
      expect(runPosts).toEqual([]);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("removes duplicate chrome, shows workflow context, and reorders shelf cards by pointer drag", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflow(page);

      await expect(page.locator(".comfymodal-studio-shelf-head")).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-feature-tabs")).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-metadata-section")).toHaveCount(0);
      await expect(page.locator(".comfymodal-studio-carousel-header")).toHaveCount(0);
      await expect(page.getByText("Version:")).toHaveCount(0);
      await expect(page.locator('[data-testid="workflow-version-selector"]')).toHaveCount(0);
      await expect(page.locator('[data-testid="workflow-type"]')).toContainText("Type:");

      const cards = page.locator('[data-testid^="shelf-field-"]');
      const grips = page.locator('[data-testid^="shelf-drag-"]');
      const count = await cards.count();
      expect(count).toBeGreaterThanOrEqual(2);
      const before = await cards.evaluateAll((els) => els.slice(0, 2).map((el) => el.getAttribute("data-role")));
      expect(await page.locator(`[data-testid="shelf-group-${before[1]}"]`).count()).toBe(0);
      expect(await page.locator(`[data-testid="shelf-advanced-${before[1]}"]`).count()).toBe(0);
      const gripBox = await page.locator(`[data-testid="shelf-drag-${before[1]}"]`).boundingBox();
      const targetBox = await page.locator(`[data-testid="shelf-field-${before[0]}"]`).boundingBox();
      expect(gripBox).toBeTruthy();
      expect(targetBox).toBeTruthy();
      await page.mouse.move(gripBox.x + gripBox.width / 2, gripBox.y + gripBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(targetBox.x + 3, targetBox.y + targetBox.height / 2, { steps: 8 });
      await expect(page.locator('[data-testid^="shelf-row-"]').first()).toHaveClass(/is-drop-target/);
      await page.mouse.move(targetBox.x + targetBox.width - 3, targetBox.y + targetBox.height / 2, { steps: 8 });
      await expect(page.locator('[data-testid^="shelf-row-"]').first()).toHaveClass(/is-drop-target/);
      await page.mouse.up();
      await expect.poll(async () => page.locator(".comfymodal-studio-shelf-row").first().locator('[data-testid^="shelf-field-"]').evaluateAll((els) => els.map((el) => el.getAttribute("data-role")))).toEqual([before[0], before[1]]);

      const rows = page.locator(".comfymodal-studio-shelf-row");
      if (await rows.count() > 1) {
        const secondGrip = await page.locator('[data-testid^="shelf-drag-"]').first().boundingBox();
        const firstRow = await rows.nth(0).boundingBox();
        const secondRow = await rows.nth(1).boundingBox();
        await page.mouse.move(secondGrip.x + secondGrip.width / 2, secondGrip.y + secondGrip.height / 2);
        await page.mouse.down();
        await page.mouse.move(firstRow.x + 10, (firstRow.y + firstRow.height + secondRow.y) / 2, { steps: 8 });
        await expect.poll(async () => rows.evaluateAll((els) => els.some((el) => /is-drop-above|is-drop-below/.test(el.className)))).toBe(true);
        await page.mouse.up();
      }

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("recent runs accordion and progress total layout are user-facing", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflow(page);
      await expect(page.locator(".comfymodal-studio-carousel-item").first()).toBeVisible({ timeout: 15000 });
      const accordion = page.locator(".comfymodal-studio-carousel-accordion");
      await expect(accordion).toBeVisible();
      await expect(accordion.locator("button")).toHaveCount(2);
      await expect(accordion).toContainText("Recent runs");
      await expect(accordion.locator("button")).toHaveText(["↑", "↑"]);
      const track = page.locator(".comfymodal-studio-carousel-track");
      await accordion.locator("button").first().click();
      await expect(track).toBeHidden();
      await expect(accordion.locator("button")).toHaveText(["↓", "↓"]);
      await accordion.locator(".comfymodal-studio-carousel-accordion-label").click();
      await expect(track).toBeVisible();
      await expect(accordion.locator("button")).toHaveText(["↑", "↑"]);

      await fx.setScenario("sampler_progress");
      await page.locator('[data-testid="run-btn"]').click();
      await expect(page.locator('[data-testid="progress-section"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="progress-golden-total"]')).toBeVisible();
      const order = await page.evaluate(() => {
        const row = document.querySelector(".comfymodal-studio-progress-bar-row");
        return Array.from(row.children).map((node) => node.getAttribute("data-testid") || node.className);
      });
      expect(order[0]).toBe("progress-golden-total");
      expect(order[1]).toBe("progress-bar");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("preview overlay keeps prompt, parameters, and notes in a non-overlapping details column", async ({ page }) => {
    const requestBodies = [];
    const progressResponses = [];
    page.on("request", async (request) => {
      if (request.method() === "POST" && /\/comfymodal\/studio\/run$/.test(request.url())) {
        requestBodies.push(request.postDataJSON());
      }
    });
    page.on("response", (response) => {
      if (/\/comfymodal\/studio\/run-progress\//.test(response.url())) progressResponses.push(response.status());
    });
    const fx = await setupFakeTest(page);
    try {
      await selectWorkflow(page);
      const prompt = "A blue fox beside a silver lake";
      await page.locator('[data-testid="shelf-input-prompt"]').fill(prompt);
      await page.locator('[data-testid="run-btn"]').click();
      await fx.waitForStatus("Run completed", { timeout: 20000 });
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 15000 });
      expect(requestBodies.length).toBe(1);
      expect(JSON.stringify(requestBodies[0])).toContain(prompt);
      expect(progressResponses).toEqual([]);

      await page.locator('[data-testid="canvas-output"]').click();
      const overlay = page.locator(".comfymodal-studio-viewer-overlay");
      await expect(overlay).toBeVisible();
      await expect(overlay.locator('[data-testid="preview-details"]')).toContainText(prompt);
      await expect(overlay.locator('[data-testid="preview-parameters"]')).toBeVisible();
      const boxes = await overlay.evaluate(() => {
         const stage = document.querySelector(".comfymodal-studio-viewer-stage").getBoundingClientRect();
         const side = document.querySelector(".comfymodal-studio-viewer-right").getBoundingClientRect();
        return { stageRight: stage.right, sideLeft: side.left, sideWidth: side.width };
      });
      expect(boxes.sideWidth).toBeGreaterThan(0);
      expect(boxes.sideLeft).toBeGreaterThanOrEqual(boxes.stageRight - 1);

      await page.setViewportSize({ width: 480, height: 900 });
      const mobileBoxes = await overlay.evaluate(() => {
         const stage = document.querySelector(".comfymodal-studio-viewer-stage").getBoundingClientRect();
         const side = document.querySelector(".comfymodal-studio-viewer-right").getBoundingClientRect();
        return { stageBottom: stage.bottom, sideTop: side.top, scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth };
      });
      expect(mobileBoxes.sideTop).toBeGreaterThanOrEqual(mobileBoxes.stageBottom - 1);
      expect(mobileBoxes.scrollWidth).toBeLessThanOrEqual(mobileBoxes.clientWidth);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
