// Modal Studio — Setup-wizard browser-refresh persistence (fake backend).
//
// Requirement 5: a full browser refresh must reopen the SAME workflow/version
// setup wizard at the SAME step. Identity + step + bindings + details live in a
// bounded sessionStorage draft (owned by studio-backend-api.js) and a
// namespaced URL marker that shell canonicalization does not strip on load.
// The in-wizard Refresh stays on the wizard/step; closing/Done clears the
// draft; stale drafts soft-clear.

import { test, expect } from "@playwright/test";
import { setupFakeTest, openVuePage } from "./helpers.mjs";

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
  // Vue behavior: a bounded sessionStorage draft reopens the same
  // workflow/version wizard at the same step after a real reload; closing
  // clears the draft so a further reload does not resume.
  test("resumes the same workflow/version/step after a full reload", async ({ page }) => {
    // Two full reload cycles with app boot: needs headroom over the 30s default.
    test.setTimeout(120000);
    const workflow = { workflow_id: "wf_refresh", name: "Refresh Flow", workflow_type: "t2i", latest_version_id: "ver_refresh" };
    const version = { workflow_version_id: "ver_refresh", version: 1 };
    const workflowRoutes = [
      ["**/comfymodal/studio/workflows", async (route) => {
        if (route.request().method() !== "GET") {
          await route.fallback();
          return;
        }
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
      }],
      ["**/comfymodal/studio/workflows/wf_refresh", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
      }],
      ["**/comfymodal/studio/workflows/wf_refresh/versions", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
      }],
      ["**/comfymodal/studio/workflows/versions/ver_refresh**", async (route) => {
        const tail = new URL(route.request().url()).pathname.split("/").pop();
        const bodies = {
          mapping: { status: "ok", mapping: null },
          dependencies: { status: "ok", models: [], custom_nodes: [] },
          compatibility: { status: "ok" },
          portability: { status: "ok", portability: { risk_level: "low", issue_count: 0 } },
          presets: { status: "ok", presets: [] },
        };
        const body = tail === "ver_refresh" ? { status: "ok", version } : (bodies[tail] ?? { status: "ok" });
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
      }],
    ];
    await openVuePage(page, "workflows", workflowRoutes);
    await page.waitForSelector('[data-testid="vue-workflow-wf_refresh"]', { timeout: 60000 });
    await page.click('[data-testid="vue-workflow-wf_refresh"]');
    await page.click("text=Setup wizard");
    await page.waitForSelector('[data-testid="vue-workflow-wizard"]', { timeout: 30000 });
    await page.click("text=Next");
    await page.waitForTimeout(300);
    const before = await page.evaluate(() => JSON.parse(sessionStorage.getItem("comfymodal.studio.wizard.draft.v1") || "null"));
    expect(before).toBeTruthy();
    expect(before.workflowId).toBe("wf_refresh");
    expect(before.step).toBe("required-bindings");

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => typeof window.__comfymodalOpenVueStudio === "function", null, { timeout: 120000 });
    await page.waitForTimeout(5000);
    await page.evaluate(async () => {
      await window.__comfymodalOpenVueStudio("workflows");
      return 1;
    });
    await page.waitForSelector('[data-testid="vue-workflow-wizard"]', { timeout: 60000 });
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toContainText("required-bindings");
    const after = await page.evaluate(() => JSON.parse(sessionStorage.getItem("comfymodal.studio.wizard.draft.v1") || "null"));
    expect(after.workflowId).toBe(before.workflowId);
    expect(after.step).toBe("required-bindings");

    await page.locator('[data-testid="vue-workflow-wizard"]').getByRole("button", { name: "Close", exact: true }).click();
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toHaveCount(0, { timeout: 10000 });
    expect(await page.evaluate(() => sessionStorage.getItem("comfymodal.studio.wizard.draft.v1"))).toBeNull();

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => typeof window.__comfymodalOpenVueStudio === "function", null, { timeout: 120000 });
    await page.waitForTimeout(5000);
    await page.evaluate(async () => {
      await window.__comfymodalOpenVueStudio("workflows");
      return 1;
    });
    await page.waitForSelector('[data-testid="vue-page-workflows"]', { timeout: 60000 });
    await page.waitForTimeout(1000);
    await expect(page.locator('[data-testid="vue-workflow-wizard"]')).toHaveCount(0);
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
