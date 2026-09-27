// Modal Studio — Setup-wizard browser-refresh persistence (fake backend).
//
// Requirement 5: a full browser refresh must reopen the SAME workflow/version
// setup wizard at the SAME step. Identity + step + bindings + details live in a
// bounded sessionStorage draft (owned by studio-backend-api.js) and a
// namespaced URL marker that shell canonicalization does not strip on load.
// The in-wizard Refresh stays on the wizard/step; closing/Done clears the
// draft; stale drafts soft-clear.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const DRAFT_KEY = "comfymodal.studio.wizard.draft.v1";

async function mountAfterReload(page) {
  await page.waitForFunction(() => typeof window.__mountStudioForTest === "function", null, {
    timeout: 15000,
  });
  await page.evaluate(() => window.__mountStudioForTest());
  // The shell is mounted synchronously; wizard mode may hide the page
  // container, so wait on the shell handle rather than page visibility.
  await page.waitForFunction(() => !!window.__studioApi, null, { timeout: 15000 });
}

/** Open wf_fake's version-setup wizard and advance to the Dependencies step. */
async function openWizardAtDependencies(page) {
  await page.getByTestId("workflow-card").first().click();
  await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
  await page.getByTestId("mapping-setup-button").click();
  const panel = page.locator(".comfymodal-studio-wizard-panel");
  await expect(panel).toBeVisible({ timeout: 10000 });
  await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
  await panel.getByTestId("wizard-features-continue").click();
  await expect(panel.getByTestId("wizard-dependencies-continue")).toBeVisible({ timeout: 10000 });
  return panel;
}

function readDraft(page) {
  return page.evaluate((key) => {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, DRAFT_KEY);
}

test.describe("Studio wizard browser refresh", () => {
  test("resumes the same workflow/version/step after a full reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
      const panel = await openWizardAtDependencies(page);

      // The draft carries the identity + step, and the URL keeps the marker
      // that only a real reload preserves.
      const before = await readDraft(page);
      expect(before).toBeTruthy();
      expect(before.step).toBe("dependencies");
      expect(before.workflowId).toBeTruthy();
      expect(before.workflowVersionId).toBeTruthy();
      expect(await page.evaluate(() => window.location.hash)).toContain("comfymodal_wizard=1");

      // In-wizard Refresh re-renders the step without leaving the wizard.
      await panel.getByTestId("wizard-dependencies-refresh").click();
      await expect(panel.getByTestId("wizard-dependencies-continue")).toBeVisible({ timeout: 10000 });

      // Full page reload in the same session (hash + sessionStorage survive).
      await page.reload({ waitUntil: "domcontentloaded" });
      await mountAfterReload(page);

      const resumed = page.locator(".comfymodal-studio-wizard-panel");
      await expect(resumed).toBeVisible({ timeout: 15000 });
      // Same step: the Dependencies continue control is present again.
      await expect(resumed.getByTestId("wizard-dependencies-continue")).toBeVisible({ timeout: 10000 });
      const after = await readDraft(page);
      expect(after.workflowId).toBe(before.workflowId);
      expect(after.workflowVersionId).toBe(before.workflowVersionId);
      expect(after.step).toBe("dependencies");

      // Closing the wizard clears the draft: a further reload must NOT resume.
      await resumed.locator(".comfymodal-studio-wizard-close").click();
      await expect(page.locator(".comfymodal-studio-wizard-panel")).toHaveCount(0, { timeout: 10000 });
      expect(await readDraft(page)).toBeNull();

      await page.reload({ waitUntil: "domcontentloaded" });
      await mountAfterReload(page);
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 15000 });
      await expect(page.locator(".comfymodal-studio-wizard-panel")).toHaveCount(0);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("a stale draft for another version soft-clears instead of resuming", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await fx.gotoPage("workflows");
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

      // Seed a well-formed draft whose identity no longer matches any live
      // workflow/version, then mark the URL as a reload.
      await page.evaluate((key) => {
        sessionStorage.setItem(key, JSON.stringify({
          v: 1,
          workflowId: "wf_does_not_exist",
          workflowVersionId: "wv_does_not_exist",
          step: "dependencies",
          selectedFeatures: ["txt2img"],
          bindings: {},
          details: { name: "Stale", description: "" },
        }));
      }, DRAFT_KEY);
      await page.evaluate(() => { window.location.hash = "#comfymodal=workflows&comfymodal_wizard=1"; });

      await page.reload({ waitUntil: "domcontentloaded" });
      await mountAfterReload(page);
      await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 15000 });
      // Stale identity never resurrects a wizard.
      await page.waitForTimeout(500);
      await expect(page.locator(".comfymodal-studio-wizard-panel")).toHaveCount(0);

      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
