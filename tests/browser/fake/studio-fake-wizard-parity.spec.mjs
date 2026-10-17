// Modal Studio — setup wizard semantic parity (live ComfyUI + interceptions).
//
// The Bindings step exposes the code-owned role catalog per feature type
// (required + optional), and Review gates saving on the required set.
// Presentation-only assertions: no graph clicks, no backend mutations.

import { test, expect } from "@playwright/test";
import { openVuePage } from "./helpers.mjs";

const workflow = { workflow_id: "wf_wizpar", name: "Wizard Parity", workflow_type: "t2i", latest_version_id: "ver_wizpar" };
const version = { workflow_version_id: "ver_wizpar", workflow_id: "wf_wizpar", version: 1 };

const routes = [
  ["**/comfymodal/studio/workflows", async (route) => {
    if (route.request().method() !== "GET") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
  }],
  ["**/comfymodal/studio/workflows/wf_wizpar", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
  }],
  ["**/comfymodal/studio/workflows/wf_wizpar/versions", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
  }],
  ["**/comfymodal/studio/workflows/versions/ver_wizpar**", async (route) => {
    const tail = new URL(route.request().url()).pathname.split("/").pop();
    const bodies = {
      mapping: { status: "ok", mapping: null },
      dependencies: { status: "ok", models: [], custom_nodes: [] },
      compatibility: { status: "ok" },
      portability: { status: "ok", portability: { risk_level: "low", issue_count: 0 } },
      presets: { status: "ok", presets: [] },
    };
    const body = tail === "ver_wizpar" ? { status: "ok", version } : (bodies[tail] ?? { status: "ok" });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  }],
];

async function openWizard(page) {
  await page.click('[data-testid="vue-workflow-wf_wizpar"]');
  await page.getByRole("button", { name: "Setup workflow" }).click();
  await page.waitForSelector('[data-testid="vue-workflow-wizard"]', { timeout: 30000 });
}

async function goNext(page) {
  await page.locator('[data-testid="vue-workflow-wizard"] button', { hasText: "Next" }).click();
}

test.describe("Studio wizard semantic parity", () => {
  test("bindings step lists the t2i required and optional role sets", async ({ page }) => {
    await openVuePage(page, "workflows", routes);
    await openWizard(page);
    await goNext(page);
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toContainText("Step 2 of 4 · Bindings");
    for (const role of ["prompt", "seed", "model_unet", "vae", "clip"]) {
      await expect(page.locator(`[data-testid="vue-wizard-role-${role}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="vue-wizard-capture-${role}"]`)).toBeVisible();
    }
    for (const role of ["step_count", "cfg_scale", "sampler"]) {
      await expect(page.locator(`[data-testid="vue-wizard-role-${role}"]`).first()).toBeVisible();
    }
  });

  test("review gates saving until required roles and output are bound", async ({ page }) => {
    await openVuePage(page, "workflows", routes);
    await openWizard(page);
    await goNext(page);
    await goNext(page);
    await goNext(page);
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toContainText("Step 4 of 4");
    await expect(page.locator('[data-testid="vue-wizard-gate"]')).toContainText("Prompt");
    await expect(page.locator('[data-testid="vue-wizard-save"]')).toBeDisabled();
  });
});
