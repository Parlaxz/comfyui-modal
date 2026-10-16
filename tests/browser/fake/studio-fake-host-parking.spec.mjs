// Modal Studio — host viewport-ownership parking (live ComfyUI + interceptions).
//
// While Vue Studio is open it owns the viewport through pure-CSS parking
// (body[data-cmv-own]): "studio" parks ALL host chrome for fullscreen Studio,
// "graph" returns only the graph canvas for Setup Workflow. Removing the
// attribute restores everything — no DOM removal, no restore bookkeeping.
// Selectors are behavioral (computed display, ownership attribute), never
// tied to Studio's own class names.

import { test, expect } from "@playwright/test";
import { openVuePage } from "./helpers.mjs";

const workflow = { workflow_id: "wf_park", name: "Parking Flow", workflow_type: "t2i", latest_version_id: "ver_park" };
const version = { workflow_version_id: "ver_park", version: 1 };

const workflowRoutes = [
  ["**/comfymodal/studio/workflows", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
  }],
  ["**/comfymodal/studio/workflows/wf_park", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
  }],
  ["**/comfymodal/studio/workflows/wf_park/versions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
  }],
  ["**/comfymodal/studio/workflows/versions/ver_park**", async (route) => {
    const tail = new URL(route.request().url()).pathname.split("/").pop();
    const bodies = {
      mapping: { status: "ok", mapping: null },
      dependencies: { status: "ok", models: [], custom_nodes: [] },
      compatibility: { status: "ok" },
      portability: { status: "ok", portability: { risk_level: "low", issue_count: 0 } },
      presets: { status: "ok", presets: [] },
    };
    const body = tail === "ver_park" ? { status: "ok", version } : (bodies[tail] ?? { status: "ok" });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  }],
];

function displayOf(page, selector) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return "missing";
    return getComputedStyle(el).display;
  }, selector);
}

test.describe("Studio host viewport ownership", () => {
  test("normal Studio parks host chrome; close restores it", async ({ page }) => {
    test.setTimeout(120000);
    await openVuePage(page, "workflows", workflowRoutes);

    await expect.poll(() => page.evaluate(() => document.body.getAttribute("data-cmv-own"))).toBe("studio");
    expect(await displayOf(page, "#vue-app")).toBe("none");
    expect(await displayOf(page, "button#donut-civitai-btn")).toBe("none");
    const frameWidth = await page.evaluate(() => document.querySelector(".comfymodal-vue-studio-frame")?.getBoundingClientRect().width ?? 0);
    expect(frameWidth).toBeGreaterThanOrEqual(await page.evaluate(() => window.innerWidth) - 2);

    await page.click('[data-testid="vue-studio-close"]');
    await expect.poll(() => page.evaluate(() => document.body.getAttribute("data-cmv-own"))).toBeNull();
    expect(await displayOf(page, "#vue-app")).not.toBe("none");
  });

  test("graph mode returns the canvas and keeps chrome parked; exit restores", async ({ page }) => {
    test.setTimeout(120000);
    await openVuePage(page, "workflows", workflowRoutes);

    await page.click('[data-testid="vue-workflow-wf_park"]');
    await page.getByRole("button", { name: "Setup workflow" }).click();
    await page.waitForSelector('[data-testid="vue-workflow-wizard"]', { timeout: 30000 });

    await expect.poll(() => page.evaluate(() => document.body.getAttribute("data-cmv-own"))).toBe("graph");
    expect(await displayOf(page, "#graph-canvas-container canvas")).not.toBe("none");
    expect(await displayOf(page, "#graph-canvas-container > .comfy-menu")).toBe("none");
    expect(await displayOf(page, "button#donut-civitai-btn")).toBe("none");

    await page.keyboard.press("Escape");
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toHaveCount(0, { timeout: 10000 });
    await expect.poll(() => page.evaluate(() => document.body.getAttribute("data-cmv-own"))).toBe("studio");

    await page.click('[data-testid="vue-studio-close"]');
    await expect.poll(() => page.evaluate(() => document.body.getAttribute("data-cmv-own"))).toBeNull();
    expect(await displayOf(page, "#vue-app")).not.toBe("none");
  });
});
