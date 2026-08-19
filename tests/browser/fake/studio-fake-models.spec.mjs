// Modal Studio — Workflows dependency system + Model Library tests against
// the deterministic fake backend.
//
// Test A drives the import flow end-to-end: the fake server returns a
// dependency_summary (1 missing model), the import dialog surfaces it, and
// the detail page renders the dependency section (status banner, model row,
// custom-node row) with the run button gated by the incomplete version state.
//
// Test B exercises the Model Library sub-view: list rendering, search + type
// filters, rescan, and the model detail dialog (edit + save via fake PATCH).

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

// Deterministic graph capture stub — same pattern as the live workflows spec:
// replaces the dynamically-imported capture module so the import flow never
// touches a real ComfyUI graph.
async function stubGraphCapture(page) {
  await page.route("**/studio-backend-capture.js", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/javascript",
      body:
        "export async function captureCurrentComfyGraph() { return { ok: true, graphJson: { nodes: [{ id: 7, type: 'KSampler', widgets_values: [42] }] }, apiPromptJson: { '7': { class_type: 'KSampler', inputs: {} } }, warnings: [] }; }" +
        "export async function takeSnapshotOfCurrentGraph() {}",
    })
  );
}

test("dependency summary renders after import and gates the run button", async ({ page }) => {
  // Register the capture stub BEFORE setupFakeTest: routes registered after
  // the harness navigation do not intercept the dynamic capture import.
  await stubGraphCapture(page);
  const fx = await setupFakeTest(page);
  try {
    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

    // Open the import dialog and confirm.
    await page.getByTestId("workflows-import-button").click();
    await expect(page.getByTestId("import-dialog")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("import-confirm").click();

    // The dialog briefly shows the dependency review line before navigating.
    await expect(page.getByTestId("import-dialog")).toContainText("1 dependency needs attention", {
      timeout: 10000,
    });

    // Lands on the workflow detail page; dependencies were fetched on load.
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("dependency-status")).toContainText(
      "Incomplete \u2014 1 dependency needs attention",
      { timeout: 10000 }
    );

    // Missing model row + installed custom node row.
    const modelRow = page.getByTestId("dependency-model-row").filter({
      hasText: "krea_model.safetensors",
    });
    await expect(modelRow).toContainText("Missing", { timeout: 10000 });

    const nodeRow = page.getByTestId("dependency-node-row").filter({
      hasText: "SomeCustomClass",
    });
    await expect(nodeRow).toContainText("Installed", { timeout: 10000 });

    // Incomplete version state → Run stays disabled.
    await expect(page.getByTestId("run-button")).toBeDisabled({ timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});

test("model library lists, filters, rescans, and edits a model", async ({ page }) => {
  const fx = await setupFakeTest(page);
  try {
    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

    // Sub-nav → Model Library sub-view.
    await page.getByTestId("wf-subnav-models").click();
    await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(3, { timeout: 10000 });

    // Search filter narrows to a single row.
    await page.getByTestId("models-search").fill("sd15");
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(1, { timeout: 10000 });
    await page.getByTestId("models-search").fill("");
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(3, { timeout: 10000 });

    // Type filter narrows to the VAE.
    await page.getByTestId("models-type-filter").selectOption("vae");
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(1, { timeout: 10000 });
    await page.getByTestId("models-type-filter").selectOption("");
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(3, { timeout: 10000 });

    // Rescan keeps the deterministic 3-model list.
    await page.getByTestId("models-rescan").click();
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(3, { timeout: 10000 });

    // Model detail dialog shows full metadata (hash) and supports editing.
    await page.locator('[data-testid="model-row"]').first().getByTestId("model-details").click();
    await expect(page.getByTestId("model-detail-dialog")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("model-detail-dialog")).toContainText("aaaa1111", {
      timeout: 10000,
    });

    await page.getByTestId("model-notes-input").fill("edited by test");
    await page.getByTestId("model-detail-save").click();
    await expect(page.getByTestId("model-detail-dialog")).not.toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(3, { timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});
