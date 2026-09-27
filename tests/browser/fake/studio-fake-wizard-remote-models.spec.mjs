// Modal Studio — Remote model-volume availability overlay (fake backend).
//
// MOCK EVIDENCE. The remote Modal model volume is the availability authority:
// a dependency row with a remote nonzero size reads Installed even when its
// local file is a zero-byte placeholder, and a remote size of 0 stays Missing.
// The "Download all" count and the dependency banner are recomputed from that
// overlay state, never from the local placeholder. Nothing is downloaded:
// the browser only ever reads GET /comfymodal/models.
//
// The shared fake backend has no remote volume, so this spec overrides the
// route with a deterministic inventory and asserts the wizard projection.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const REMOTE_MODELS = {
  checkpoints: [
    {
      name: "krea_model.safetensors",
      size: 6500000000,
      folder: "checkpoints",
      // Local placeholder is intentional: 0 bytes on disk, model on the volume.
      local_placeholder: {
        folder: "checkpoints",
        filename: "krea_model.safetensors",
        exists: true,
        size: 0,
        is_placeholder: true,
        is_real_file: false,
      },
    },
  ],
  vae: [
    {
      name: "untracked.safetensors",
      size: 0,
      folder: "vae",
      local_placeholder: {
        folder: "vae",
        filename: "untracked.safetensors",
        exists: false,
        size: 0,
        is_placeholder: false,
        is_real_file: false,
      },
    },
  ],
};

const DEPS = {
  status: "ok",
  version_id: "wv_fake",
  models: [
    {
      key: "checkpoint|krea_model.safetensors",
      role: "checkpoint",
      filename: "krea_model.safetensors",
      state: "missing",
      folder: "checkpoints",
      source_urls: ["https://example.com/krea_model.safetensors"],
    },
    {
      key: "vae|untracked.safetensors",
      role: "vae",
      filename: "untracked.safetensors",
      state: "missing",
      folder: "vae",
      source_urls: ["https://example.com/untracked.safetensors"],
    },
  ],
  custom_nodes: [],
  summary: { installed: 0, missing: 2, wrong_version: 0, unknown: 0, attention: 2, ready: false },
};

test("remote nonzero size marks the placeholder row Installed; size 0 stays Missing", async ({ page }) => {
  const fx = await setupFakeTest(page);
  const modelsReads = [];
  const mutations = [];
  try {
    // Capture the remote inventory read; do not let it mutate anything. The
    // dependency report is provided deterministically so the overlay is the
    // only thing under test.
    await page.route("**/comfymodal/models", async (route) => {
      modelsReads.push(route.request().method());
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(REMOTE_MODELS),
      });
    });
    await page.route(
      /\/comfymodal\/studio\/workflows\/versions\/wv_fake\/dependencies$/,
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(DEPS),
        });
      }
    );
    // Any mutation route is captured and refused: this test proves no install
    // or model bytes are fetched.
    await page.route("**/comfymodal/models/batch-install", async (route) => {
      mutations.push(route.request().method() + " batch-install");
      await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    });
    await page.route("**/comfymodal/model/install", async (route) => {
      mutations.push(route.request().method() + " model/install");
      await route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    });

    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("workflow-card").first().click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("mapping-setup-button").click();
    const panel = page.locator(".comfymodal-studio-wizard-panel");
    await expect(panel).toBeVisible({ timeout: 10000 });
    await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
    await panel.getByTestId("wizard-features-continue").click();
    await expect(panel.getByTestId("wizard-dependencies-continue")).toBeVisible({ timeout: 10000 });

    // The remote inventory must have been read (read-only GET).
    await expect.poll(() => modelsReads.length).toBeGreaterThanOrEqual(1);
    expect(modelsReads.every((m) => m === "GET")).toBe(true);

    // Remote size > 0: the local 0-byte placeholder row reads Installed.
    const kreaRow = panel
      .getByTestId("dependency-model-row")
      .filter({ hasText: "krea_model.safetensors" });
    await expect(kreaRow.getByTestId("dependency-model-state")).toHaveText("Installed", {
      timeout: 15000,
    });
    // Local placeholder remains as secondary information, never as the state.
    const remoteDetail = kreaRow.getByTestId("dependency-model-remote");
    await expect(remoteDetail).toContainText("remote");
    await expect(remoteDetail).toContainText("local placeholder 0 B");
    // No download/install action for a remote-available model.
    await expect(kreaRow.getByTestId("dependency-model-queue")).toHaveCount(0);
    await expect(kreaRow.getByTestId("dependency-model-install-now")).toHaveCount(0);

    // Remote size 0 remains Missing and keeps its explicit action.
    const untrackedRow = panel
      .getByTestId("dependency-model-row")
      .filter({ hasText: "untracked.safetensors" });
    await expect(untrackedRow.getByTestId("dependency-model-state")).toHaveText("Missing", {
      timeout: 10000,
    });
    await expect(untrackedRow.getByTestId("dependency-model-queue")).toBeVisible();

    // Summary + "Download all" count are recomputed from the overlay: only
    // the remote-missing model still counts as missing.
    await expect(panel.getByTestId("dependency-status")).toContainText(
      "Incomplete \u2014 1 dependency needs attention",
      { timeout: 10000 }
    );
    await expect(panel.getByTestId("wizard-download-all")).toHaveText("Download all (1)");
    // The single remaining missing model has a source URL, so nothing is
    // skipped by Download all.
    await expect(panel.getByTestId("wizard-download-skipped")).toHaveCount(0);

    expect(mutations).toEqual([]);

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});
