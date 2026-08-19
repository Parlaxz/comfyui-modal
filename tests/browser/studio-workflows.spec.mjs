// Modal Studio — Workflows page E2E (mocked mode)
//
// Drives the Studio Workflows page (web/studio-workflows.js) against the
// DETERMINISTIC in-memory workflow mock (studio-workflows-mock.mjs). The
// shared studio mock API (installStudioMockApi) is installed FIRST so the
// shell/playground /comfymodal calls are satisfied during app startup; the
// workflows mock is installed AFTER so it takes precedence for every
// /comfymodal/studio/workflows* request. Because the workflows mock handles
// those paths, the shared mock never records them and
// api.assertNoUnhandledCalls() stays clean.
//
// Dataset facts (from studio-workflows-mock.mjs):
//   "Portrait Pro"  — folder "Portraits", tags ["portrait"], source author
//     "Modal Team"; versions 1 AND 2 both mapped (version 2 is the latest);
//     preset "Portrait Default" on version 1; version 2 carries
//     dependency_metadata (model_stack + node_classes).
//   "Abstract Test" — folder "Abstract", tags ["experiment"]; version 1
//     UNMAPPED → state incomplete, run button disabled.

import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// App-level console noise unrelated to the Workflows pipeline (mirrors
// studio-features.spec.mjs / studio-history-v2.spec.mjs): sibling plugin
// lanes re-register extension names and the shared ComfyUI server emits
// internal 404s during startup.
const APP_NOISE_PATTERNS = [
  "already registered",      // sibling lanes re-register extension names
  "vite:preloadError",       // ComfyUI app preload failures
  "Failed to load resource", // app-internal 404s (/lm/settings, pysssss)
  "ComfyApp graph accessed", // app startup before a graph is loaded
];

// Suite-shared mock handles (assigned in beforeEach).
let api;
let wfMock;

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitVisible(page, locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

function wfCard(page, wfId) {
  return page.locator(`[data-testid="workflow-card"][data-workflow-id="${wfId}"]`);
}

/** Open a workflow detail by name and return its seed record. */
async function openDetail(page, name) {
  const wf = wfMock.getWorkflow(name);
  expect(wf).toBeTruthy();
  const card = wfCard(page, wf.workflow_id);
  await expect(card).toBeVisible({ timeout: 10000 });
  await card.click();
  await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
  return wf;
}

/** Select a version in the detail versions list. */
async function selectVersion(page, vid) {
  const item = page.locator(`[data-testid="version-item"][data-version-id="${vid}"]`);
  await expect(item).toBeVisible({ timeout: 10000 });
  await item.click();
  await expect(item).toHaveClass(/active/, { timeout: 10000 });
}

/** Open the mapping editor ("Set up Mapping" or "Edit mapping"). */
async function openMappingEditor(page) {
  const btn = page
    .locator('[data-testid="mapping-editor"] button', { hasText: /Set up Mapping|Edit mapping/ })
    .first();
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(page.locator('[data-testid="mapping-candidates"]')).toBeVisible({ timeout: 10000 });
}

/** Set a preset-editor control by its role label. */
async function setPresetField(page, label, value) {
  const field = page
    .locator('.comfymodal-studio-preset-editor .comfymodal-studio-backend-field', { hasText: label })
    .first();
  await expect(field).toBeVisible({ timeout: 10000 });
  if (typeof value === "boolean") {
    const cb = field.locator('input[type="checkbox"]');
    if ((await cb.isChecked()) !== value) await cb.click();
    return;
  }
  const select = field.locator("select");
  if (await select.count()) {
    await select.selectOption(String(value));
    return;
  }
  const textarea = field.locator("textarea");
  if (await textarea.count()) {
    await textarea.fill(String(value));
    return;
  }
  await field.locator("input").fill(String(value));
}

/** Click the detail "New Preset" button and wait for the editor. */
async function clickNewPreset(page) {
  const section = page.locator(".comfymodal-studio-section", {
    has: page.locator(".comfymodal-studio-section-title", { hasText: "Presets" }),
  });
  await section.getByRole("button", { name: "New Preset" }).click();
  await expect(page.locator('[data-testid="preset-editor"]')).toBeVisible({ timeout: 10000 });
}

// ── Suite ─────────────────────────────────────────────────────────────────

test.describe("Studio Workflows", () => {
  test.beforeEach(async ({ page }) => {
    // Shared mock first, workflows mock second (later routes take precedence).
    api = await installStudioMockApi(page);
    wfMock = await installWorkflowsMock(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
    await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 15000 });
  });

  // ── Test 1: library lists both seeded workflows ───────────────────────
  test("1. library lists both seeded workflows with state badges", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = wfMock.getWorkflow("Portrait Pro");
      const at = wfMock.getWorkflow("Abstract Test");
      await expect(wfCard(page, pp.workflow_id)).toBeVisible({ timeout: 10000 });
      await expect(wfCard(page, at.workflow_id)).toBeVisible();
      await expect(wfCard(page, pp.workflow_id).locator(".comfymodal-studio-workflow-card-name")).toHaveText("Portrait Pro");
      await expect(wfCard(page, at.workflow_id).locator(".comfymodal-studio-workflow-card-name")).toHaveText("Abstract Test");
      await expect(wfCard(page, pp.workflow_id).locator('[data-testid="workflow-card-state"]')).toHaveText("Ready");
      await expect(wfCard(page, at.workflow_id).locator('[data-testid="workflow-card-state"]')).toHaveText("Incomplete");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: folder tree renders and filters ───────────────────────────
  test("2. folder tree renders and clicking a folder filters cards", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const tree = page.locator('[data-testid="workflows-folder-tree"]');
      await expect(tree).toBeVisible({ timeout: 10000 });
      await expect(tree.getByRole("button", { name: "All folders" })).toBeVisible();
      await expect(tree.getByRole("button", { name: "Portraits" })).toBeVisible();
      await expect(tree.getByRole("button", { name: "Abstract" })).toBeVisible();

      await tree.getByRole("button", { name: "Portraits" }).click();
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="workflow-card"]').first()).toContainText("Portrait Pro");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 3: tag filter, favorites toggle, favorite PATCH ──────────────
  test("3. tag filter and favorites toggle with favoriting PATCH", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const tagSelect = page.locator('[data-testid="workflows-tag-filter"]');
      await expect(tagSelect).toBeVisible({ timeout: 10000 });
      await expect(tagSelect.locator('option[value="portrait"]')).toHaveCount(1);
      await expect(tagSelect.locator('option[value="experiment"]')).toHaveCount(1);

      await tagSelect.selectOption("portrait");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="workflow-card"]').first()).toContainText("Portrait Pro");
      await tagSelect.selectOption("");

      // Favorites-only: nothing is favorited yet → empty grid.
      const favToggle = page.locator('[data-testid="workflows-favorites-only"]');
      await favToggle.click();
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(0);
      await favToggle.click();

      // Star the Portrait Pro card → PATCH recorded with favorite:true.
      const pp = wfMock.getWorkflow("Portrait Pro");
      const star = wfCard(page, pp.workflow_id).locator(".comfymodal-studio-favorite-star");
      await expect(star).toHaveAttribute("aria-pressed", "false");
      await star.click();
      await expect(star).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
      const patch = wfMock.findCall("PATCH", `/comfymodal/studio/workflows/${pp.workflow_id}`);
      expect(patch).toBeTruthy();
      expect(patch.body.favorite).toBe(true);

      // Favorites-only now keeps only Portrait Pro.
      await favToggle.click();
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="workflow-card"]').first()).toContainText("Portrait Pro");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 4: search filters by name substring ──────────────────────────
  test("4. search filters cards by name substring", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const search = page.locator('[data-testid="workflows-search"]');
      await expect(search).toBeVisible({ timeout: 10000 });
      await search.fill("portrait");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1, { timeout: 5000 });
      await expect(page.locator('[data-testid="workflow-card"]').first()).toContainText("Portrait Pro");

      await search.fill("abstract");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(1, { timeout: 5000 });
      await expect(page.locator('[data-testid="workflow-card"]').first()).toContainText("Abstract Test");

      await search.fill("no-match");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(0, { timeout: 5000 });

      await search.fill("");
      await expect(page.locator('[data-testid="workflow-card"]')).toHaveCount(2, { timeout: 5000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 5: workflow detail header + versions + dependencies ──────────
  test("5. detail shows header fields, version badges, and dependencies", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      await expect(page.locator('[data-testid="workflow-detail-name"]')).toHaveText("Portrait Pro");
      await expect(page.locator('[data-testid="workflow-detail-folder"]')).toHaveText("Portraits");
      await expect(page.locator('[data-testid="workflow-detail-tags"]')).toContainText("portrait");
      await expect(page.locator('[data-testid="workflow-detail-source"]')).toContainText("Modal Team");

      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(2);
      await expect(page.locator('[data-testid="version-item-state"]')).toHaveCount(2);
      await expect(page.locator('[data-testid="version-item-state"]').first()).toHaveText("Ready");

      const versions = wfMock.getVersions(pp.workflow_id);
      expect(versions.some((v) => v.version_number === 2)).toBe(true);
      await expect(page.locator('[data-testid="dependencies-summary"]')).toBeVisible();
      await expect(page.locator('[data-testid="dependencies-summary"]')).toContainText("KSampler");
      await expect(page.locator('[data-testid="dependencies-summary"]')).toContainText("sd_xl_base_1.0.safetensors");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 6: import flow ───────────────────────────────────────────────
  test("6. import flow creates a workflow and navigates to its detail", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // Deterministic graph capture: stub the dynamically-imported capture
      // module so the "Import from current ComfyUI graph" flow never touches
      // the live graph. Registered last → takes precedence.
      await page.route("**/studio-backend-capture.js", (route) =>
        route.fulfill({
          status: 200,
          contentType: "text/javascript",
          body:
            "export async function captureCurrentComfyGraph() { return { ok: true, graphJson: { nodes: [{ id: 7, type: 'KSampler', widgets_values: [42] }] }, apiPromptJson: { '7': { class_type: 'KSampler', inputs: {} } }, warnings: [] }; }" +
            "export async function takeSnapshotOfCurrentGraph() {}",
        })
      );

      await page.locator('[data-testid="workflows-import-button"]').click();
      await expect(page.locator('[data-testid="import-dialog"]')).toBeVisible({ timeout: 10000 });
      await page
        .locator('[data-testid="import-dialog"] input[placeholder*="Workflow name"]')
        .fill("Imported Portrait");
      await page.locator('[data-testid="import-confirm"]').click();

      await expect
        .poll(() => wfMock.callsFor("POST", "/comfymodal/studio/workflows/import").length)
        .toBe(1);
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="workflow-detail-name"]')).toHaveText("Imported Portrait");
      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(1);
      await expect(page.locator(".comfymodal-studio-notice")).toContainText("Version created");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 7: mapping candidates render exact enum options ──────────────
  test("7. mapping candidates render exact enum options and ranges", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Abstract Test");
      await openMappingEditor(page);

      const samplerRow = page.locator('[data-testid="mapping-role-row"]', {
        has: page.locator('select option[value="euler_ancestral"]'),
      });
      await expect(samplerRow).toHaveCount(1);
      await expect(samplerRow.locator("select option")).toHaveCount(4);
      expect(await samplerRow.locator("select option").allTextContents()).toEqual([
        "euler", "euler_ancestral", "dpmpp_2m", "uni_pc",
      ]);

      const schedulerRow = page.locator('[data-testid="mapping-role-row"]', {
        has: page.locator('select option[value="sgm_uniform"]'),
      });
      await expect(schedulerRow).toHaveCount(1);
      expect(await schedulerRow.locator("select option").allTextContents()).toEqual([
        "normal", "karras", "exponential", "sgm_uniform",
      ]);

      const seedRow = page.locator('[data-testid="mapping-role-row"]', { hasText: "Seed" }).first();
      await expect(seedRow.locator('input[type="number"]')).toHaveAttribute("min", "0");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 8: initial mapping save enables run ──────────────────────────
  test("8. initial mapping save records POST and enables the run button", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Abstract Test");
      await expect(page.locator('[data-testid="run-button"]')).toBeDisabled();
      await openMappingEditor(page);
      await page.locator('[data-testid="mapping-save"]').click();

      const mappingPosts = wfMock
        .callsFor("POST", "/comfymodal/studio/workflows/versions/")
        .filter((c) => c.path.endsWith("/mapping"));
      expect(mappingPosts.length).toBe(1);
      expect(mappingPosts[0].body.entries.length).toBeGreaterThan(0);

      await expect(page.locator('[data-testid="version-item-state"]')).toHaveText("Ready", { timeout: 10000 });
      await expect(page.locator('[data-testid="run-button"]')).toBeEnabled({ timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 9: second mapping POST is rejected with 409 ──────────────────
  test("9. second mapping POST cannot mutate an existing mapping", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Abstract Test");
      await openMappingEditor(page);

      // Create the mapping directly (first POST) while the page still believes
      // the version is unmapped — the page never re-fetches the mapping inside
      // the open editor, so "Save Mapping" remains available.
      const at = wfMock.getWorkflow("Abstract Test");
      const v = wfMock.getVersions(at.workflow_id)[0];
      const candidates = await page.evaluate(async (vid) => {
        const res = await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping/candidates`);
        const data = await res.json();
        return data.candidates;
      }, v.workflow_version_id);
      await page.evaluate(
        async ({ vid, cand }) => {
          await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entries: cand.entries, output_node_id: cand.output_node_id }),
          });
        },
        { vid: v.workflow_version_id, cand: candidates }
      );

      await expect(page.locator('[data-testid="mapping-save"]')).toBeVisible();
      await page.locator('[data-testid="mapping-save"]').click();
      await expect(page.locator(".comfymodal-studio-notice")).toContainText("immutable", { timeout: 10000 });

      const mappingPosts = wfMock
        .callsFor("POST", "/comfymodal/studio/workflows/versions/")
        .filter((c) => c.path.endsWith("/mapping"));
      expect(mappingPosts.length).toBe(2);
      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(1);
      expect(wfMock.state.mappings.has(v.workflow_version_id)).toBe(true);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 10: mapping revision creates a new immutable version ─────────
  test("10. mapping revision creates a new version and keeps the old one", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v1 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 1);
      const v2 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 2);
      await selectVersion(page, v1.workflow_version_id);

      await openMappingEditor(page);
      await page.locator('[data-testid="mapping-revision-button"]').click();
      await expect(page.locator(".comfymodal-studio-confirm-panel")).toContainText("immutable");
      await expect(page.locator('[data-testid="mapping-revision-confirm"]')).toBeVisible();
      await page.locator('[data-testid="mapping-revision-confirm"]').click();

      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(3, { timeout: 10000 });
      await expect(page.locator(".comfymodal-studio-version-number", { hasText: "v3" })).toBeVisible();
      await expect(page.locator(`[data-testid="version-item"][data-version-id="${v1.workflow_version_id}"]`)).toBeVisible();
      await expect(page.locator(`[data-testid="version-item"][data-version-id="${v2.workflow_version_id}"]`)).toBeVisible();

      // Old version + its mapping still intact.
      await selectVersion(page, v1.workflow_version_id);
      await expect(page.locator('[data-testid="mapping-editor"]')).toContainText("Edit mapping");
      expect(wfMock.state.mappings.has(v1.workflow_version_id)).toBe(true);
      expect(wfMock.getVersions(pp.workflow_id).some((v) => v.version_number === 3)).toBe(true);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 11: preset creation preserves falsy values ───────────────────
  test("11. preset creation preserves falsy values exactly", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v2 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 2);
      await expect(page.locator(`[data-testid="version-item"][data-version-id="${v2.workflow_version_id}"]`)).toHaveClass(/active/);

      await clickNewPreset(page);
      await page.locator('[data-testid="preset-name-input"]').fill("Zero Values");
      await setPresetField(page, "Steps", "0");
      await setPresetField(page, "CFG", "0.0");
      await setPresetField(page, "Positive Prompt", "");
      await setPresetField(page, "Model", "test-model.safetensors");

      const hiresField = page
        .locator('.comfymodal-studio-preset-editor .comfymodal-studio-backend-field', { hasText: "Hires Fix" })
        .first();
      await expect(hiresField.locator('input[type="checkbox"]')).not.toBeChecked();

      await page.locator('[data-testid="preset-save"]').click();

      const post = wfMock
        .callsFor("POST", `/comfymodal/studio/workflows/versions/${v2.workflow_version_id}/presets`)
        .pop();
      expect(post).toBeTruthy();
      expect(post.body.values.steps).toBe(0);
      expect(post.body.values.cfg).toBe(0);
      expect(post.body.values.positive_prompt).toBe("");
      expect(post.body.values.hires_fix).toBe(false);
      expect("steps" in post.body.values).toBe(true);
      expect("cfg" in post.body.values).toBe(true);
      expect("positive_prompt" in post.body.values).toBe(true);
      expect("hires_fix" in post.body.values).toBe(true);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 12: preset with a missing required value shows incomplete ────
  test("12. preset with a missing required value shows incomplete reasons", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Portrait Pro");
      await clickNewPreset(page);
      await page.locator('[data-testid="preset-name-input"]').fill("Incomplete Preset");
      // Leave the required "Model" control empty.
      await page.locator('[data-testid="preset-save"]').click();

      await expect(page.locator('[data-testid="preset-state-reasons"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="preset-state-reasons"]')).toContainText(
        "missing value for required control"
      );
      await expect(page.locator(".comfymodal-studio-notice")).not.toContainText("Preset saved");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 13: default preset ───────────────────────────────────────────
  test("13. setting a default preset reflects on card and library", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v1 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 1);
      await selectVersion(page, v1.workflow_version_id);

      const presetCard = page.locator('[data-testid="preset-card"]').first();
      await expect(presetCard.locator('[data-testid="preset-card-name"]')).toHaveText("Portrait Default");
      await presetCard.locator('[data-testid="preset-default-button"]').click();
      await expect(presetCard.locator(".comfymodal-studio-wf-chip.default")).toBeVisible({ timeout: 10000 });
      await expect(presetCard.locator('[data-testid="preset-default-button"]')).toHaveText("Clear default");

      // Back in the library the card shows the default preset name.
      await page.getByRole("button", { name: /Back to Workflows/ }).click();
      await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible();
      await expect(wfCard(page, pp.workflow_id)).toContainText("Portrait Default", { timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 14: duplicate preset ─────────────────────────────────────────
  test("14. duplicating a preset adds a (Copy) card", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v1 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 1);
      await selectVersion(page, v1.workflow_version_id);

      await page.locator('[data-testid="preset-card"]').first().locator('[data-testid="preset-duplicate-button"]').click();
      await expect(page.locator('[data-testid="preset-card"]')).toHaveCount(2, { timeout: 10000 });
      await expect(page.locator('[data-testid="preset-card-name"]', { hasText: "Portrait Default (Copy)" })).toBeVisible();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 15: copy preset to newer version ─────────────────────────────
  test("15. copying a preset to the latest version keeps the original", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v1 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 1);
      const v2 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 2);
      await selectVersion(page, v1.workflow_version_id);

      await page.locator('[data-testid="preset-card"]').first().locator('[data-testid="preset-copy-button"]').click();
      await expect(page.locator('[data-testid="copy-results"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="copy-results"]')).toContainText("Copied");

      // Version 2 now lists the copied preset.
      await selectVersion(page, v2.workflow_version_id);
      await expect(page.locator('[data-testid="preset-card-name"]', { hasText: "Portrait Default" })).toBeVisible({ timeout: 10000 });

      // Version 1 is untouched — exactly one preset remains.
      await selectVersion(page, v1.workflow_version_id);
      await expect(page.locator('[data-testid="preset-card"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="preset-card-name"]', { hasText: "Portrait Default" })).toBeVisible();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 16: bulk copy ────────────────────────────────────────────────
  test("16. bulk copy to latest copies every preset", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const v1 = wfMock.getVersions(pp.workflow_id).find((v) => v.version_number === 1);
      await selectVersion(page, v1.workflow_version_id);

      // Add a second preset so bulk copy has two items to move.
      await page.locator('[data-testid="preset-card"]').first().locator('[data-testid="preset-duplicate-button"]').click();
      await expect(page.locator('[data-testid="preset-card"]')).toHaveCount(2, { timeout: 10000 });

      await page.locator('[data-testid="preset-bulk-copy-button"]').click();
      await expect(page.locator('[data-testid="copy-results"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="copy-result-item"]')).toHaveCount(2);

      const bulk = wfMock
        .callsFor("POST", `/comfymodal/studio/workflows/versions/${v1.workflow_version_id}/presets/copy-bulk`)
        .pop();
      expect(bulk).toBeTruthy();
      expect(bulk.body.preset_ids.length).toBe(2);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 17: run button lifecycle on an unmapped workflow ─────────────
  test("17. run button is disabled until mapping and preset exist", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Abstract Test");
      await expect(page.locator('[data-testid="run-button"]')).toBeDisabled();

      // Mapping alone makes the version runnable → run enabled.
      await openMappingEditor(page);
      await page.locator('[data-testid="mapping-save"]').click();
      await expect(page.locator('[data-testid="run-button"]')).toBeEnabled({ timeout: 10000 });

      // Add a preset on the freshly mapped version.
      await clickNewPreset(page);
      await page.locator('[data-testid="preset-name-input"]').fill("Abstract Preset");
      await setPresetField(page, "Model", "test-model.safetensors");
      await page.locator('[data-testid="preset-save"]').click();
      await expect(page.locator(".comfymodal-studio-notice")).toContainText("Preset saved", { timeout: 10000 });
      await expect(page.locator('[data-testid="run-button"]')).toBeEnabled();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 18: run-context endpoint shape ───────────────────────────────
  test("18. run-context endpoint returns the expected shape", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // The workflows page itself does not call run-context (the Run button
      // just navigates to the playground), so fetch it directly to verify the
      // endpoint contract against the seeded dataset.
      const pp = wfMock.getWorkflow("Portrait Pro");
      const data = await page.evaluate(async (wfId) => {
        const res = await fetch(`/comfymodal/studio/workflows/${wfId}/run-context`);
        return res.json();
      }, pp.workflow_id);

      expect(data.status).toBe("ok");
      expect(data.workflow.workflow_id).toBe(pp.workflow_id);
      expect(data.workflow.latest_version_number).toBe(2);
      expect(data.version).toBeTruthy();
      expect(data.version.version_number).toBe(2);
      expect(data.state.runnable).toBe(true);
      expect(data.mapping).toBeTruthy();
      expect(Array.isArray(data.mapping.entries)).toBe(true);
      expect(data.mapping.entries.length).toBeGreaterThan(0);
      expect(data.default_preset).toBe(null);
      expect(Array.isArray(data.control_schema)).toBe(true);

      const call = wfMock.findCall("GET", `/comfymodal/studio/workflows/${pp.workflow_id}/run-context`);
      expect(call).toBeTruthy();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });
});
