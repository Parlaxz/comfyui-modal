// Studio Phase-3 explicit methods (fake backend, bounded).
//
// Proves the per-workflow Inpaint/Expand method dropdowns against the real
// frontend on the fake I2I workflow: fixed option sets, the conditioning
// note element, and method persistence across subtool switches. Backend
// execution is NOT asserted here (no runs are submitted).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

async function selectWorkflow(page, id) {
  await page.locator('[data-testid="workflow-selector"]').selectOption(id);
  await expect(page.locator('[data-testid="workflow-selector"]')).toHaveValue(id, { timeout: 10000 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
}

// Phase-1 shell: Edit → Select renders the inpaint editor on I2I,
// Edit → Expand renders the outpaint editor on I2I.
async function gotoSelect(page) {
  await page.locator('[data-testid="studio-tool-edit"]').click();
  await page.locator('[data-testid="studio-subtool-select"]').click();
}

async function gotoExpand(page) {
  await page.locator('[data-testid="studio-tool-edit"]').click();
  await page.locator('[data-testid="studio-subtool-expand"]').click();
}

// The compat probe is advisory (the backend revalidates at execution); stub
// it so the suite never depends on the fake backend implementing the route.
async function stubMethodCompat(page) {
  await page.route("**/comfymodal/studio/method-compat*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        workflow_id: "wf_i2i",
        version_id: "wv_i2i",
        conditioning: { compatible: true, sampler_id: "1", vae: ["5", 0], reasons: [] },
        crop_stitch: { compatible: true },
        pad: { compatible: true },
      }),
    });
  });
}

test.describe("Studio phase-3 explicit methods (fake backend)", () => {
  test("Select on I2I shows method options; Conditioning keeps a note and persists", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await stubMethodCompat(page);
      await gotoSelect(page);
      await selectWorkflow(page, "wf_i2i");
      // The method row binds the workflow selected at render time (prefs are
      // keyed by workflow id): toggle the subtool once so the row below is
      // bound to wf_i2i before driving it.
      await page.locator('[data-testid="studio-subtool-text"]').click();
      await page.locator('[data-testid="studio-subtool-select"]').click();
      const method = page.locator('[data-testid="inpaint-method"]');
      await expect(method).toBeVisible({ timeout: 10000 });
      await expect(method.locator("option")).toHaveText([
        "Crop + Stitch",
        "Conditioning + Crop/Stitch",
        "Dedicated Workflow",
      ]);
      await expect(method).toHaveValue("crop_stitch");
      await method.selectOption("conditioning");
      await expect(method).toHaveValue("conditioning");
      await expect(page.locator('[data-testid="inpaint-method-note"]')).toBeAttached();
      // Switching away and back remounts the editor; the per-workflow
      // preference (localStorage) must survive.
      await page.locator('[data-testid="studio-subtool-text"]').click();
      await page.locator('[data-testid="studio-subtool-select"]').click();
      await expect(page.locator('[data-testid="inpaint-method"]')).toHaveValue("conditioning", { timeout: 10000 });
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Expand on I2I shows expand method options", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await stubMethodCompat(page);
      await gotoExpand(page);
      await selectWorkflow(page, "wf_i2i");
      await expect(page.locator('[data-testid="outpaint-editor"]')).toBeVisible({ timeout: 10000 });
      const method = page.locator('[data-testid="expand-method"]');
      await expect(method).toBeVisible({ timeout: 10000 });
      await expect(method.locator("option")).toHaveText([
        "Pad Canvas",
        "Pad + Preserve",
        "Dedicated Workflow",
      ]);
      await expect(method).toHaveValue("pad_preserve");
      await fx.assertNoConsoleErrors();
    } finally {}
  });
});
