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
//
// Test C (H7 parity) covers the Workflows-owned custom-node registry surface:
// canonical registry rows, explicit-only registry refresh, the click-gated
// install REQUEST on a missing dependency node (approval only — nothing is
// installed), and the dependency→Model Library filter handoff.

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

test("custom-node registry browse, explicit refresh, install request, and library handoff", async ({ page }) => {
  const fx = await setupFakeTest(page);
  try {
    // Serve a modified dependencies payload (adds a MISSING custom node with
    // a repo URL) without touching the shared fake backend.
    await page.route("**/studio/workflows/versions/wv_fake/dependencies", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.custom_nodes.push({
        name: "ComfyUI-Missing",
        state: "missing",
        repository_url: "https://github.com/example/ComfyUI-Missing",
        required_revision: "",
        installed_commit: "",
      });
      payload.summary.attention = 2;
      await route.fulfill({ response, json: payload });
    });

    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });

    // ── Model Library sub-view: canonical custom-node registry section ──
    await page.getByTestId("wf-subnav-models").click();
    await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
    const cnSection = page.getByTestId("custom-nodes-section");
    await expect(cnSection).toBeVisible({ timeout: 10000 });
    const registryRow = page.getByTestId("custom-node-row").filter({ hasText: "ComfyUI-KJNodes" });
    await expect(registryRow).toContainText("Installed", { timeout: 10000 });
    await expect(registryRow).toContainText("abc1234", { timeout: 10000 });

    // Explicit refresh only — the section never refreshes itself.
    await page.getByTestId("custom-nodes-refresh").click();
    await expect(cnSection).toContainText("Registry refreshed", { timeout: 10000 });
    await expect(page.locator('[data-testid="custom-node-row"]')).toHaveCount(1, { timeout: 10000 });

    // ── Workflow detail: missing node exposes an install REQUEST only ──
    await page.getByTestId("models-back").click();
    await expect(page.getByTestId("workflow-card").first()).toBeVisible({ timeout: 10000 });
    await page.getByTestId("workflow-card").first().click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
    const missingRow = page.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-Missing" });
    await expect(missingRow).toContainText("Missing", { timeout: 10000 });

    let installRequests = 0;
    page.on("request", (req) => {
      if (req.method() === "POST" && req.url().includes("/custom-nodes/install-request")) {
        installRequests += 1;
      }
    });
    await missingRow.getByTestId("dependency-node-install-request").click();
    const note = missingRow.getByTestId("dependency-node-install-note");
    await expect(note).toContainText("nothing was installed", { timeout: 10000 });
    expect(installRequests).toBe(1);

    // ── Dependency row → Model Library filter handoff (no second UI) ──
    const kreaRow = page.getByTestId("dependency-model-row").filter({ hasText: "krea_model.safetensors" });
    await kreaRow.getByTestId("dependency-model-find").click();
    await expect(page.getByTestId("models-page")).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId("models-search")).toHaveValue("krea_model.safetensors");
    await expect(page.locator('[data-testid="model-row"]')).toHaveCount(1, { timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});
