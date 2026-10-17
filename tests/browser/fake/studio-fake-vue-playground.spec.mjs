// Modal Studio Vue Phase 5 — Playground parity against the live bundle with
// deterministic endpoint interceptions (no Modal/GPU work).
//
// Covers the frozen contracts: workflow/run-context resolution, submission
// freeze, queue collect/drain, experiment-v2 only, source-image ownership via
// the shared History picker.

import { test, expect } from "@playwright/test";
import { openVuePage } from "./helpers.mjs";

const CONFIG = {};
const PROFILE = { status: "ok", level: "off", effective: "off" };
const WORKFLOWS = {
  status: "ok",
  workflows: [{ workflow_id: "wf-1", name: "Parity Workflow", latest_version_id: "v-1" }],
};
const VERSIONS = {
  status: "ok",
  versions: [{ workflow_version_id: "v-1", workflow_id: "wf-1", version: 1 }],
};
const RUN_CONTEXT = {
  status: "ok",
  workflow: { workflow_id: "wf-1", workflow_type: "t2i" },
  version: { workflow_version_id: "v-1", runnable: true },
  mapping: { bindings: {} },
  control_schema: {
    prompt: { label: "Prompt", control_kind: "text", required: true, default: "" },
    steps: { label: "Steps", data_type: "INT", default: 20, minimum: 1, maximum: 100 },
    width: { label: "Width", data_type: "INT", default: 512, minimum: 64, maximum: 2048 },
    height: { label: "Height", data_type: "INT", default: 512, minimum: 64, maximum: 2048 },
  },
};
const FEED = { status: "ok", items: [], next_cursor: null, has_more: false };

function baseRoutes(extra = []) {
  return [
    ["**/comfymodal/config", (route) => route.fulfill(json(CONFIG))],
    ["**/comfymodal/profile/level", (route) => route.fulfill(json(PROFILE))],
    ["**/comfymodal/history-v2/feed?*", (route) => route.fulfill(json(FEED))],
    ["**/comfymodal/studio/workflows/folders", (route) => route.fulfill(json({ status: "ok", folders: [] }))],
    ["**/comfymodal/studio/workflows/tags", (route) => route.fulfill(json({ status: "ok", tags: [] }))],
    ["**/comfymodal/studio/workflows/wf-1/run-context*", (route) =>
      route.fulfill(json(RUN_CONTEXT))],
    ["**/comfymodal/studio/workflows/wf-1/versions", (route) =>
      route.fulfill(json(VERSIONS))],
    ["**/comfymodal/studio/workflows/wf-1", (route) =>
      route.fulfill(json({ status: "ok", workflow: WORKFLOWS.workflows[0] }))],
    ["**/comfymodal/studio/workflows?*", (route) => route.fulfill(json(WORKFLOWS))],
    ["**/comfymodal/studio/workflows", (route) => route.fulfill(json(WORKFLOWS))],
    ...extra,
  ];
}

function json(body) {
  return { status: 200, contentType: "application/json", body: JSON.stringify(body) };
}

test.describe("Vue Playground Phase 5 (fake routes, live bundle)", () => {
  test("1. workflow resolves to mapped controls and an enabled Generate", async ({ page }) => {
    await openVuePage(page, "playground", baseRoutes());
    await expect(page.locator('[data-testid="vue-playground-workflow"]')).toBeVisible({ timeout: 30000 });
    await page.waitForSelector('[data-testid="vue-playground-control-prompt"]', { timeout: 30000 });
    await expect(page.locator('[data-testid="vue-playground-control-steps"]')).toBeVisible();
    await expect(page.locator('[data-testid="vue-playground-control-width"]')).toBeVisible();
    await expect(page.locator('[data-testid="vue-generate-submit"]')).toBeEnabled();
  });

  test("2. Generate posts the frozen intent to /studio/run", async ({ page }) => {
    let posted = null;
    await openVuePage(
      page,
      "playground",
      baseRoutes([
        [
          "**/comfymodal/studio/run",
          (route) => {
            posted = JSON.parse(route.request().postData() || "{}");
            route.fulfill(json({ status: "ok", runId: "r-1", direct_run: true }));
          },
        ],
      ]),
    );
    await page.waitForSelector('[data-testid="vue-playground-control-prompt"]', { timeout: 30000 });
    // Center prompt is the hero input; inspector prompt roles are hidden.
    await page.fill('[data-testid="vue-playground-prompt-prompt"]', "frozen intent probe");
    await page.click('[data-testid="vue-generate-submit"]');
    await page.waitForSelector('[data-testid="vue-playground-run-status"]', { timeout: 30000 });
    await expect(page.locator('[data-testid="vue-playground-run-status"]')).toContainText("Run completed");
    expect(posted).not.toBeNull();
    expect(posted.controls.prompt).toBe("frozen intent probe");
    expect(posted.workflow_id).toBe("wf-1");
    expect(posted.metadata.source).toBe("studio_playground_vue");
  });

  test("3. Queue collects frozen variants and drains through run_batch", async ({ page }) => {
    let batched = null;
    await openVuePage(
      page,
      "playground",
      baseRoutes([
        [
          "**/comfymodal/studio/run_batch",
          (route) => {
            batched = JSON.parse(route.request().postData() || "{}");
            route.fulfill(json({ status: "ok" }));
          },
        ],
      ]),
    );
    await page.waitForSelector('[data-testid="vue-playground-control-prompt"]', { timeout: 30000 });
    await page.click('[data-testid="vue-generate-menu-button"]');
    await page.click('[data-testid="vue-generate-intent-queue"]');
    await page.waitForSelector('[data-testid="vue-playground-queue"]', { timeout: 30000 });
    await expect(page.locator('[data-testid="vue-generate-submit"]')).toContainText("Queue (1)");
    await page.click('[data-testid="vue-playground-drain"]');
    await expect(page.locator('[data-testid="vue-playground-run-status"]')).toContainText("Batch submitted", { timeout: 30000 });
    expect(batched).not.toBeNull();
    expect(batched.variants).toHaveLength(1);
    expect(batched.workflow_id).toBe("wf-1");
  });

  test("4. Experiment submits only to experiment-v2", async ({ page }) => {
    const posts = [];
    await openVuePage(page, "playground", [
      ...baseRoutes(),
      [
        "**/comfymodal/studio/*",
        (route) => {
          if (route.request().method() === "POST") posts.push(route.request().url());
          route.continue();
        },
      ],
      [
        "**/comfymodal/studio/experiment-v2",
        (route) => route.fulfill(json({ status: "ok", experiment_id: "e-1" })),
      ],
    ]);
    await page.waitForSelector('[data-testid="vue-playground-control-prompt"]', { timeout: 30000 });
    await page.click('[data-testid="vue-generate-menu-button"]');
    await page.click('[data-testid="vue-generate-intent-experiment"]');
    await page.waitForSelector('[data-testid="vue-playground-composer"]', { timeout: 30000 });
    await page.check('[data-testid="vue-playground-axis-steps"]');
    await page.fill('[data-testid="vue-playground-axis-values-steps"]', "20, 30");
    await page.click('[data-testid="vue-playground-composer-submit"]');
    await page.waitForSelector('[data-testid="vue-playground-run-status"]', { timeout: 30000 });
    const v2 = posts.filter((url) => /\/studio\/experiment-v2$/.test(url));
    expect(v2).toHaveLength(1);
    expect(posts.filter((url) => /\/studio\/experiment$/.test(url) && !/v2/.test(url))).toHaveLength(0);
  });

  test("5. History picker commits source ownership without a duplicate feed", async ({ page }) => {
    const feedItem = {
      id: "gen_src",
      kind: "generation",
      status: "completed",
      workflow: "Parity Workflow",
      featured: 0,
      outputs: [{ asset_id: "asset_src", filename: "src.png" }],
    };
    await openVuePage(
      page,
      "playground",
      baseRoutes([
        [
          "**/comfymodal/history-v2/feed?*",
          (route) =>
            route.fulfill(
              json({ status: "ok", items: [feedItem], next_cursor: null, has_more: false }),
            ),
        ],
      ]),
    );
    await page.waitForSelector('[data-testid="vue-playground-control-prompt"]', { timeout: 30000 });
    await page.click('[data-testid="vue-playground-subtool-references"]');
    await page.click('[data-testid="vue-playground-add-reference"]');
    await page.waitForSelector('[data-testid="vue-history-picker"]', { timeout: 30000 });
    await page.click('[data-testid="vue-picker-option-gen_src"]');
    await page.waitForSelector('[data-testid^="vue-playground-reference-"]', { timeout: 30000 });
    expect(await page.locator('[data-testid^="vue-playground-reference-"]').count()).toBe(1);
  });
});
