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

/** Open the mapping editor ("Set up Mapping" or "Edit mapping"). */
async function openMappingEditor(page) {
  const btn = page
    .locator('[data-testid="mapping-editor"] button', { hasText: /Set up Mapping|Edit mapping/ })
    .first();
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(page.locator('[data-testid="mapping-candidates"]')).toBeVisible({ timeout: 10000 });
}

// ── Primary-extension pin ───────────────────────────────────────────────
// The mocked suite has no Playwright webServer and navigates to the shared
// ComfyUI instance at 127.0.0.1:8188, letting that server's extension
// registry resolve /extensions/.... Sibling lanes register the same
// extension name, so without pinning the page can load stale sibling code
// (e.g. /extensions/comfyui-modal-rx9p-t/) instead of this repo's primary
// copy at /extensions/comfyui-modal/.
//
// Determination: every test in this suite opens the studio through the
// server-selected launcher (beforeEach → openStudio → window.open_testing_modal
// or the sidebar "Modal GPU" entry); no test navigates directly. Tests
// 8/11/12/17/19 exercise page-load behavior and tests 20/21 resolve modules
// dynamically, so all of them must run against the primary copy. This route
// rewrites any sibling-lane request for this plugin's files to the primary
// /extensions/comfyui-modal/ path before the app loads. Unrelated extensions
// pass through untouched.
async function pinPrimaryExtensionRequests(page) {
  // NOTE: regex, not a "**/extensions/*" glob — in Playwright glob syntax
  // "*" does not cross "/", so that glob never matches nested module URLs
  // like /extensions/<dir>/studio-shell.js and the pin would be a no-op.
  await page.route(/\/extensions\//, async (route) => {
    const reqUrl = new URL(route.request().url());
    const match = reqUrl.pathname.match(/^\/extensions\/([^/]+)\/(.*)$/);
    if (match && match[1] !== "comfyui-modal" && /modal/i.test(match[1])) {
      reqUrl.pathname = `/extensions/comfyui-modal/${match[2]}`;
      await route.continue({ url: reqUrl.toString() });
      return;
    }
    await route.continue();
  });
}

/** Open the binding wizard ("Set up Mapping" on an unmapped version). */
async function openSetupWizard(page) {
  await page.locator('[data-testid="mapping-setup-button"]').click();
  const panel = page.locator(".comfymodal-studio-wizard-panel");
  await expect(panel).toBeVisible({ timeout: 10000 });
  await expect(panel).toContainText("Set up Workflow");
  // The legacy mapping editor must NOT render for unmapped versions.
  await expect(page.locator('[data-testid="mapping-candidates"]')).toHaveCount(0);
  return panel;
}

/** Stub the dynamically-imported capture module with the given graph. */
async function stubGraphCapture(page, graphJson) {
  await page.route("**/studio-backend-capture.js", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/javascript",
      body:
        `export async function captureCurrentComfyGraph() { return { ok: true, graphJson: ${JSON.stringify(graphJson)}, apiPromptJson: { '7': { class_type: 'KSampler', inputs: {} } }, warnings: [] }; }` +
        "export async function takeSnapshotOfCurrentGraph() {}",
    })
  );
}

// Rich graph covering every T2I catalog role for wizard suggestion tests.
const RICH_WIZARD_GRAPH = {
  nodes: [
    { id: 3, class_type: "KSampler", title: "KSampler" },
    { id: 6, class_type: "CLIPTextEncode", title: "Positive" },
    { id: 7, class_type: "CheckpointLoaderSimple", title: "Loader" },
    { id: 9, class_type: "SaveImage", title: "Save", outputs: [{ name: "images", type: "IMAGE" }] },
  ],
};

/** Click every wizard "Use suggestion" confirmation button. */
async function confirmAllWizardSuggestions(panel) {
  const buttons = panel.locator('[data-testid="wizard-use-suggestion"]');
  expect(await buttons.count()).toBeGreaterThan(0);
  while ((await buttons.count()) > 0) {
    await buttons.first().click();
  }
}

/** Advance the wizard from the features step to the bindings step (passing
 * through the Dependencies step in version-setup mode). */
async function wizardContinueToBindings(panel) {
  await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
  await panel.locator('[data-testid="wizard-features-continue"]').click();
  const depsContinue = panel.locator('[data-testid="wizard-dependencies-continue"]');
  if (await depsContinue.count()) {
    await depsContinue.click();
  }
  await expect(panel.locator('[data-testid="wizard-required-bindings"]')).toBeVisible({ timeout: 10000 });
}


// ── Suite ─────────────────────────────────────────────────────────────────

test.describe("Studio Workflows", () => {
  test.beforeEach(async ({ page }) => {
    // Shared mock first, workflows mock second (later routes take precedence).
    api = await installStudioMockApi(page);
    wfMock = await installWorkflowsMock(page);
    // Mount-pinning: rewrite sibling-lane extension requests to the primary
    // copy BEFORE the app loads (see pinPrimaryExtensionRequests).
    await pinPrimaryExtensionRequests(page);
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

      // One version per workflow: a single non-selectable row, no version
      // number, no preset count.
      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="version-item-state"]')).toHaveCount(1);
      await expect(page.locator('[data-testid="version-item-state"]').first()).toHaveText("Ready");
      await expect(page.locator('[data-testid="version-item"]')).toContainText("Mapped");
      await expect(page.locator(".comfymodal-studio-version-number")).toHaveCount(0);
      await expect(page.locator('[data-testid="preset-card"]')).toHaveCount(0);

      const versions = wfMock.getVersions(pp.workflow_id);
      expect(versions.length).toBeGreaterThan(0);
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

  // ── Test 6: import opens the binding wizard, cancel lands on detail ──
  test("6. import flow opens the binding wizard and cancel lands on detail", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // Deterministic graph capture: stub the dynamically-imported capture
      // module so the "Import from current ComfyUI graph" flow never touches
      // the live graph. Registered last → takes precedence.
      await stubGraphCapture(page, {
        nodes: [{ id: 7, type: "KSampler", widgets_values: [42] }],
      });

      // "New Workflow" opens the same creation dialog that the former
      // "Import" entry opened (that entry no longer exists).
      await page.locator('[data-testid="workflows-new-button"]').click();
      await expect(page.locator('[data-testid="import-dialog"]')).toBeVisible({ timeout: 10000 });
      await page
        .locator('[data-testid="import-dialog"] input[placeholder*="Workflow name (optional"]')
        .fill("Imported Portrait");
      await page.locator('[data-testid="import-confirm"]').click();

      await expect
        .poll(() => wfMock.callsFor("POST", "/comfymodal/studio/workflows/import").length)
        .toBe(1);

      // Import lands in the unified binding wizard — not on the detail page.
      const panel = page.locator(".comfymodal-studio-wizard-panel");
      await expect(panel).toBeVisible({ timeout: 10000 });
      await expect(panel).toContainText("Set up Workflow");
      await expect(page.locator('[data-testid="workflow-detail"]')).toHaveCount(0);
      // The wizard pre-seeded suggestions from the imported version's stored
      // graph (single KSampler → seed/step_count/cfg_scale/sampler).
      await wizardContinueToBindings(panel);
      await expect(panel.locator('[data-testid="wizard-suggest-status"]')).toContainText(
        "stored graph",
        { timeout: 10000 }
      );

      // Cancel returns to the workflow detail page, as import navigation does
      // today.
      await panel.locator(".comfymodal-studio-wizard-close").click();
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
  // Unmapped versions now open the binding wizard instead of the legacy
  // editor, so this renders through the untouched "Edit mapping" revision
  // path on an already-mapped version.
  test("7. mapping candidates render exact enum options and ranges", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      // One version per workflow: the detail view already targets the
      // workflow's current version, so there is nothing to select.
      const current = wfMock.getVersions(pp.workflow_id);
      expect(current.length).toBeGreaterThan(0);
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

  // ── Test 8: unmapped setup opens the wizard; save maps + enables run ─
  test("8. setup-mapping opens the binding wizard and save enables the run button", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // Rich graph capture so the wizard's "Suggest from current graph"
      // covers every T2I catalog role deterministically.
      await stubGraphCapture(page, RICH_WIZARD_GRAPH);

      await openDetail(page, "Abstract Test");
      await expect(page.locator('[data-testid="run-button"]')).toBeDisabled();

      // "Set up Mapping" opens the unified wizard — not the legacy editor.
      const panel = await openSetupWizard(page);

      // Complete the wizard: feature → suggested bindings (explicit
      // per-role confirmation) → confirm → save.
      await wizardContinueToBindings(panel);
      await panel.locator('[data-testid="wizard-suggest-button"]').click();
      await expect(panel.locator('[data-testid="wizard-suggest-status"]')).toContainText(
        "Confirm each one below",
        { timeout: 10000 }
      );
      await confirmAllWizardSuggestions(panel);
      await expect(panel.locator('[data-testid="wizard-save-gate"]')).toContainText(
        "6 of 6 required bindings complete"
      );
      await panel.getByRole("button", { name: "Continue to Details" }).click();
      await expect(panel).toContainText("Confirm Setup");
      const saveBtn = panel.locator('[data-testid="wizard-version-save"]');
      await expect(saveBtn).toBeEnabled();
      await saveBtn.click();
      await expect(panel).toContainText("Setup Complete", { timeout: 10000 });

      // The wizard persisted a version mapping through the mapping POST
      // route: entries as a dict keyed by semantic role plus output node.
      const mappingPosts = wfMock
        .callsFor("POST", "/comfymodal/studio/workflows/versions/")
        .filter((c) => c.path.endsWith("/mapping"));
      expect(mappingPosts.length).toBe(1);
      expect(Object.keys(mappingPosts[0].body.entries).sort()).toEqual(
        ["cfg_scale", "clip", "model_unet", "prompt", "sampler", "seed", "step_count", "vae"]
      );
      expect(mappingPosts[0].body.output_node_id).toBe("9");
      // Snapshots/presets no longer exist at all, so there is nothing to leak
      // and no mock collection to assert against.

      // Completion returns to the detail page with the version mapped and
      // runnable.
      await panel.locator('[data-testid="wizard-version-done"]').click();
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
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
  // Unmapped versions now open the binding wizard instead of the legacy
  // editor, so the immutability contract is pinned directly against the
  // mapping POST route: the first POST creates, the second is refused, and
  // the version keeps a single mapping.
  test("9. second mapping POST cannot mutate an existing mapping", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await openDetail(page, "Abstract Test");

      const at = wfMock.getWorkflow("Abstract Test");
      const v = wfMock.getVersions(at.workflow_id)[0];
      const candidates = await page.evaluate(async (vid) => {
        const res = await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping/candidates`);
        const data = await res.json();
        return data.candidates;
      }, v.workflow_version_id);
      const firstStatus = await page.evaluate(
        async ({ vid, cand }) => {
          const res = await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entries: cand.entries, output_node_id: cand.output_node_id }),
          });
          return res.status;
        },
        { vid: v.workflow_version_id, cand: candidates }
      );
      expect(firstStatus).toBe(200);
      const second = await page.evaluate(
        async ({ vid, cand }) => {
          const res = await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ entries: cand.entries, output_node_id: cand.output_node_id }),
          });
          return { http: res.status, body: await res.json() };
        },
        { vid: v.workflow_version_id, cand: candidates }
      );
      expect(second.http).toBe(409);
      expect(second.body.message).toMatch(/immutable/);

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
  test("10. mapping revision appends a version and the UI shows the new current one", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const pp = await openDetail(page, "Portrait Pro");
      const before = wfMock.getVersions(pp.workflow_id);
      const currentId = before[before.length - 1].workflow_version_id;

      await openMappingEditor(page);
      await page.locator('[data-testid="mapping-revision-button"]').click();
      await expect(page.locator(".comfymodal-studio-confirm-panel")).toContainText("immutable");
      await expect(page.locator('[data-testid="mapping-revision-confirm"]')).toBeVisible();
      await page.locator('[data-testid="mapping-revision-confirm"]').click();

      // Versions are immutable, so a revision still appends a record. The UI
      // shows exactly ONE current version and adopts the new one.
      await expect(page.locator('[data-testid="version-item"]')).toHaveCount(1, { timeout: 10000 });
      const after = wfMock.getVersions(pp.workflow_id);
      expect(after.length).toBe(before.length + 1);
      const newId = after[after.length - 1].workflow_version_id;
      expect(newId).not.toBe(currentId);
      await expect(
        page.locator(`[data-testid="version-item"][data-version-id="${newId}"]`)
      ).toBeVisible();

      // The historical version and its mapping are still intact on disk.
      expect(wfMock.state.mappings.has(currentId)).toBe(true);
      expect(wfMock.state.mappings.has(newId)).toBe(true);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 11: preset creation preserves falsy values ───────────────────
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

  // ── Test 19: shared picker dialog lists, searches, confirms ────────
  test("19. picker dialog lists workflows, filters by search, confirms into detail", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await page.locator('[data-testid="workflows-picker-button"]').click();
      await expect(page.locator('[data-testid="workflow-picker-dialog"]')).toBeVisible({ timeout: 10000 });
      const picker = page.locator('[data-testid="workflow-picker"]');
      await expect(picker).toHaveAttribute("data-mode", "single");

      const options = page.locator('[data-testid="workflow-picker-option"]');
      await expect(options).toHaveCount(2, { timeout: 10000 });
      await expect(page.locator('[data-testid="workflow-picker-confirm"]')).toBeDisabled();

      // Search narrows through the picker's own debounced list endpoint.
      await page.locator('[data-testid="workflow-picker-search"]').fill("portrait");
      await expect(options).toHaveCount(1, { timeout: 10000 });
      await expect(options.first()).toContainText("Portrait Pro");

      await options.first().click();
      await expect(page.locator('[data-testid="workflow-picker-confirm"]')).toBeEnabled();
      await page.locator('[data-testid="workflow-picker-confirm"]').click();

      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="workflow-detail-name"]')).toHaveText("Portrait Pro");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 20: wizard catalog roles + T2I save gate (pure) ──────────────
  test("20. wizard lists catalog roles and blocks save until the T2I gate passes", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const result = await page.evaluate(async () => {
        // Mount-pinning: import the wizard module from the PRIMARY extension
        // copy only. Resource/script-derived bases can resolve to stale
        // sibling lane copies (e.g. /extensions/comfyui-modal-rx9p-t/), so
        // they are not probed here.
        const url = `${new URL("/extensions/comfyui-modal/", location.href).href}studio-workflow-setup-wizard.js`;
        let m = null;
        try {
          const probe = await fetch(url, { method: "GET" });
          if (!probe.ok) return { error: `HTTP ${probe.status} for ${url}` };
          m = await import(url);
        } catch (e) {
          return { error: (e && e.message) || String(e) };
        }
        const concrete = (nodeId, field) => Object.assign(
          { nodeId, nodeType: "KSampler", kind: "widget", widgetName: null, inputName: null, outputIndex: null },
          field || {}
        );
        const full = {
          prompt: concrete(6, { widgetName: "text" }),
          seed: concrete(3, { widgetName: "seed" }),
          model_unet: concrete(7, { widgetName: "ckpt_name" }),
          vae: concrete(7, { widgetName: "vae_name" }),
          clip: concrete(7, { widgetName: "clip_name" }),
          output: { kind: "output", nodeId: 9, nodeType: "SaveImage", outputIndex: 0 },
        };
        const missingOutput = Object.assign({}, full);
        delete missingOutput.output;
        const missingClipPlusExtra = Object.assign({}, full);
        delete missingClipPlusExtra.clip;
        missingClipPlusExtra.negative_prompt = concrete(6, { widgetName: "text" });
        return {
          required: m.collectRequiredBindings(["txt2img"]).map((b) => b.key),
          requiredAlias: m.collectRequiredBindings(["t2i"]).map((b) => b.key),
          requiredUnknown: m.collectRequiredBindings(["nope"]).map((b) => b.key),
          requiredLabels: m.collectRequiredBindings(["txt2img"]).map((b) => b.label),
          optional: m.FEATURE_DEFS.txt2img.optionalBindings.map((b) => b.key),
          gateKeys: [...m.T2I_SAVE_GATE_KEYS],
          empty: m.checkAllRequiredBindings({ selectedFeatures: ["txt2img"], bindings: {} }),
          nodeOnly: m.checkAllRequiredBindings({
            selectedFeatures: ["txt2img"],
            bindings: { prompt: { nodeId: 6 } },
          }),
          full: m.checkAllRequiredBindings({ selectedFeatures: ["txt2img"], bindings: full }),
          missingOutput: m.checkAllRequiredBindings({ selectedFeatures: ["txt2img"], bindings: missingOutput }),
          nonCatalogExtra: m.checkAllRequiredBindings({
            selectedFeatures: ["txt2img"],
            bindings: missingClipPlusExtra,
          }),
        };
      });

      expect(result.error || "").toBe("");
      // Catalog-only required roles (+ separate output), in catalog order.
      expect(result.required).toEqual(["prompt", "seed", "model_unet", "vae", "clip", "output"]);
      expect(result.requiredAlias).toEqual(result.required);
      expect(result.requiredUnknown).toEqual([]);
      expect(result.requiredLabels).toEqual(["Prompt", "Seed", "Model UNET", "VAE", "CLIP", "Output"]);
      expect(result.optional).toEqual(["step_count", "cfg_scale", "sampler"]);
      expect(result.gateKeys).toEqual(["prompt", "seed", "model_unet", "vae", "clip", "output"]);
      // Gate: blocked until EVERY required role has a concrete binding.
      expect(result.empty).toBe(false);
      expect(result.nodeOnly).toBe(false);
      expect(result.full).toBe(true);
      expect(result.missingOutput).toBe(false);
      // Non-catalog bindings never satisfy the gate.
      expect(result.nonCatalogExtra).toBe(false);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 21: wizard suggestions propose, user confirms (pure) ──────────
  test("21. wizard suggests likely graph targets but only confirmed bindings count", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const result = await page.evaluate(async () => {
        // Mount-pinning: import the wizard module from the PRIMARY extension
        // copy only. Resource/script-derived bases can resolve to stale
        // sibling lane copies (e.g. /extensions/comfyui-modal-rx9p-t/), so
        // they are not probed here.
        const url = `${new URL("/extensions/comfyui-modal/", location.href).href}studio-workflow-setup-wizard.js`;
        let m = null;
        try {
          const probe = await fetch(url, { method: "GET" });
          if (!probe.ok) return { error: `HTTP ${probe.status} for ${url}` };
          m = await import(url);
        } catch (e) {
          return { error: (e && e.message) || String(e) };
        }
        const graph = {
          nodes: [
            { id: 3, class_type: "KSampler", title: "KSampler" },
            { id: 6, class_type: "CLIPTextEncode", title: "Positive" },
            { id: 7, class_type: "CheckpointLoaderSimple", title: "Loader" },
            { id: 9, class_type: "SaveImage", title: "Save", outputs: [{ name: "images", type: "IMAGE" }] },
            { id: 11, class_type: "WeirdCustomNode", title: "Weird" },
          ],
        };
        const seedSug = m.suggestBindingTargets(graph, "seed");
        const promptSug = m.suggestBindingTargets(graph, "prompt");
        const outputSug = m.suggestBindingTargets(graph, "output");
        const unetSug = m.suggestBindingTargets(graph, "model_unet");
        const all = m.suggestAllBindings(graph);
        // Explicit-confirm step on a FRESH state: suggestions alone bind nothing.
        const state = { selectedFeatures: ["txt2img"], bindings: {} };
        const gateBefore = m.checkAllRequiredBindings(state);
        const applied = m.applySuggestedBinding(state, "seed", seedSug[0]);
        const gateAfterOne = m.checkAllRequiredBindings(state);
        return {
          seedSug,
          promptSug,
          outputSug,
          unetSug,
          nonCatalog: m.suggestBindingTargets(graph, "negative_prompt"),
          unknownNodeOnly: m.suggestBindingTargets(
            { nodes: [{ id: 11, class_type: "WeirdCustomNode" }] },
            "seed"
          ),
          allKeys: Object.keys(all).sort(),
          allEmpty: m.suggestAllBindings({ nodes: [] }),
          gateBefore,
          applied,
          seedBinding: state.bindings.seed,
          gateAfterOne,
          applyNonCatalog: m.applySuggestedBinding(
            { selectedFeatures: ["txt2img"], bindings: {} },
            "negative_prompt",
            { nodeId: 6, widgetName: "text" }
          ),
          applyNull: m.applySuggestedBinding(
            { selectedFeatures: ["txt2img"], bindings: {} },
            "seed",
            null
          ),
        };
      });

      expect(result.error || "").toBe("");
      expect(result.seedSug).toEqual([
        { nodeId: 3, nodeType: "KSampler", nodeTitle: "KSampler", widgetName: "seed", inputName: null, outputIndex: null },
      ]);
      expect(result.promptSug).toEqual([
        { nodeId: 6, nodeType: "CLIPTextEncode", nodeTitle: "Positive", widgetName: "text", inputName: null, outputIndex: null },
      ]);
      expect(result.outputSug).toEqual([
        { nodeId: 9, nodeType: "SaveImage", nodeTitle: "Save", widgetName: null, inputName: null, outputIndex: 0 },
      ]);
      expect(result.unetSug).toEqual([
        { nodeId: 7, nodeType: "CheckpointLoaderSimple", nodeTitle: "Loader", widgetName: "ckpt_name", inputName: null, outputIndex: null },
      ]);
      // Non-catalog roles and unknown node types are ignored.
      expect(result.nonCatalog).toEqual([]);
      expect(result.unknownNodeOnly).toEqual([]);
      expect(result.allKeys).toEqual(
        ["cfg_scale", "clip", "model_unet", "output", "prompt", "sampler", "seed", "step_count", "vae"]
      );
      // Confirmation is what counts: one applied suggestion leaves the gate closed.
      expect(result.gateBefore).toBe(false);
      expect(result.applied).toBe(true);
      expect(result.seedBinding.widgetName).toBe("seed");
      expect(result.gateAfterOne).toBe(false);
      expect(result.applyNonCatalog).toBe(false);
      expect(result.applyNull).toBe(false);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 22: mapping read-back contract (ok/null vs 404) ──────────────
  // Known-but-unmapped versions return ok/null (the page treats null as
  // "needs mapping"); only truly unknown version ids are 404. This pins the
  // reconciliation: the wizard slice keeps 404 scoped to unknown versions
  // and preserves ok/null for known ones, which tests 1-18 rely on.
  test("22. mapping GET returns ok/null for known-unmapped versions and 404 for unknown ones", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const at = wfMock.getWorkflow("Abstract Test");
      const v = wfMock.getVersions(at.workflow_id)[0];
      const result = await page.evaluate(async (vid) => {
        const knownRes = await fetch(`/comfymodal/studio/workflows/versions/${vid}/mapping`);
        const known = await knownRes.json();
        const unknownRes = await fetch("/comfymodal/studio/workflows/versions/ver_does_not_exist/mapping");
        const unknown = await unknownRes.json();
        return {
          knownHttp: knownRes.status,
          knownStatus: known.status,
          knownMapping: known.mapping,
          unknownHttp: unknownRes.status,
          unknownStatus: unknown.status,
        };
      }, v.workflow_version_id);

      expect(result.knownHttp).toBe(200);
      expect(result.knownStatus).toBe("ok");
      expect(result.knownMapping).toBe(null);
      expect(result.unknownHttp).toBe(404);
      expect(result.unknownStatus).toBe("error");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 23: setup-mapping cancel returns to detail without mapping ──
  test("23. cancelling the setup wizard returns to detail with no mapping created", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const at = await openDetail(page, "Abstract Test");
      const v = wfMock.getVersions(at.workflow_id)[0];
      await expect(page.locator('[data-testid="run-button"]')).toBeDisabled();

      const panel = await openSetupWizard(page);
      await wizardContinueToBindings(panel);
      // Cancel out of the wizard without saving.
      await panel.locator(".comfymodal-studio-wizard-close").click();

      // Still on the detail page, version untouched: no mapping POST, still
      // unmapped and not runnable.
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="workflow-detail-name"]')).toHaveText("Abstract Test");
      const mappingPosts = wfMock
        .callsFor("POST", "/comfymodal/studio/workflows/versions/")
        .filter((c) => c.path.endsWith("/mapping"));
      expect(mappingPosts.length).toBe(0);
      expect(wfMock.state.mappings.has(v.workflow_version_id)).toBe(false);
      await expect(page.locator('[data-testid="run-button"]')).toBeDisabled();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
      wfMock.assertNoUnhandledWorkflowCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── abs-2 helpers ──────────────────────────────────────────────────────

  /** Open the Backend page's Backend Presets tab (page kept; workflow-backed). */
  async function openBackendPresets(page) {
    await page.locator('.comfymodal-studio-topnav [data-page="backend"]').click();
    await expect(page.locator('[data-testid="backend-page"]')).toBeVisible({ timeout: 15000 });
    await page.locator('.comfymodal-studio-backend-tab[data-tab="presets"]').click();
    await expect(page.locator('[data-testid="backend-presets-count"]')).toContainText("preset", { timeout: 10000 });
  }

  /** Legacy Backend/Preset route calls the migrated UI must never make. */
  function legacyPresetRouteCalls() {
    return api.state.calls.filter((c) =>
      c.pathname === "/comfymodal/studio/presets" ||
      c.pathname.startsWith("/comfymodal/studio/presets/") ||
      c.pathname === "/comfymodal/studio/snapshots" ||
      c.pathname.startsWith("/comfymodal/studio/snapshots/")
    );
  }

  // ── Test 24: Backend Presets page is backed by workflow routes ─────────
});
