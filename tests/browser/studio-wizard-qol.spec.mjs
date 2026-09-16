// Modal Studio — Wizard QoL regression coverage.
//
// Pins the two wizard quality-of-life additions:
//   1. "View" on binding rows + suggestion proposals centers the canvas node
//      and flashes a magenta highlight for ~3s (null-safe when no node).
//   2. The version-setup Dependencies step before Bindings: bulk model
//      download, per-pack ComfyUI-Manager install + explicit reboot, and a
//      truthful fallback when Manager is absent.
//
// Runs against the deterministic workflow mock + shared studio mock, with
// /comfymodal/models/batch-install, /studio/models/rescan and the ROOT
// /manager/* + /customnode/* routes stubbed here (the shared mocks don't
// cover them).  api.assertNoUnhandledCalls() must stay clean.

import { test, expect } from "@playwright/test";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

const APP_NOISE_PATTERNS = [
  "already registered",
  "vite:preloadError",
  "Failed to load resource",
  "ComfyApp graph accessed",
];

let api;
let wfMock;

// ── Helpers ────────────────────────────────────────────────────────────────

async function pinPrimaryExtensionRequests(page) {
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

/**
 * Open "Abstract Test" and its unmapped-version setup wizard.
 * `beforeOpen({ wf, version })` runs first so callers can register route
 * overrides (e.g. a richer dependency report) before the wizard prefetches.
 */
async function openAbstractSetupWizard(page, beforeOpen) {
  const at = wfMock.getWorkflow("Abstract Test");
  const version = wfMock.getVersions(at.workflow_id)[0];
  if (typeof beforeOpen === "function") await beforeOpen({ wf: at, version });
  const card = page.locator(`[data-testid="workflow-card"][data-workflow-id="${at.workflow_id}"]`);
  await expect(card).toBeVisible({ timeout: 10000 });
  await card.click();
  await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 10000 });
  await page.locator('[data-testid="mapping-setup-button"]').click();
  const panel = page.locator(".comfymodal-studio-wizard-panel");
  await expect(panel).toBeVisible({ timeout: 10000 });
  await expect(panel).toContainText("Set up Workflow");
  return { panel, wf: at, version };
}

/** Fulfil the version's dependency GET with an explicit report. */
function stubDependencies(page, version, report) {
  return page.route(
    new RegExp(`/comfymodal/studio/workflows/versions/${version.workflow_version_id}/dependencies$`),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(Object.assign({ status: "ok", version_id: version.workflow_version_id }, report)),
      });
    }
  );
}

/** Fulfil the single-version GET with a stored graph the wizard can suggest from. */
function stubVersionGraph(page, version, graphJson) {
  return page.route(
    new RegExp(`/comfymodal/studio/workflows/versions/${version.workflow_version_id}$`),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          version: {
            workflow_version_id: version.workflow_version_id,
            workflow_id: version.workflow_id,
            version_number: 1,
            graph_json: graphJson,
            api_prompt_json: {},
            state: { status: "incomplete", reasons: [], runnable: false },
            mapping_id: null,
            mapping: null,
            preset_count: 0,
            dependency_metadata: { model_stack: [], node_classes: [] },
          },
        }),
      });
    }
  );
}

/**
 * Stub the live canvas with one fake node and record centering calls.
 * The original getNodeById is preserved for every other id.
 */
async function stubCanvasNode(page, nodeId) {
  return page.evaluate((id) => {
    const app = window.app || window.__comfymodal_comfy_app;
    if (!app) return { ok: false, reason: "no-app" };
    window.__comfymodal_comfy_app = app;
    app.graph = app.graph || {};
    app.graph.serialize = app.graph.serialize || (() => ({ nodes: [] }));
    const fake = {
      id,
      type: "KSampler",
      title: "Sampler " + id,
      pos: [50, 60],
      size: [200, 100],
      widgets: [],
    };
    const origGetNodeById = app.graph.getNodeById;
    app.graph.getNodeById = (nid) => {
      if (String(nid) === String(id)) return fake;
      try {
        return typeof origGetNodeById === "function" ? origGetNodeById.call(app.graph, nid) : null;
      } catch (e) { return null; }
    };
    app.graph._nodes_by_id = app.graph._nodes_by_id || {};
    app.graph._nodes_by_id[id] = fake;
    app.canvas = app.canvas || {};
    window.__viewCalls = [];
    const origCenter = app.canvas.centerOnNode;
    app.canvas.centerOnNode = (n) => {
      window.__viewCalls.push(n && n.id);
      try {
        if (typeof origCenter === "function") origCenter.call(app.canvas, n);
      } catch (e) { /* ignore */ }
    };
    app.canvas.ds = app.canvas.ds || { offset: [0, 0], scale: 1 };
    app.canvas.canvas = app.canvas.canvas || document.createElement("canvas");
    return { ok: true, hasWindowApp: !!window.app };
  }, nodeId);
}

// ── Suite ──────────────────────────────────────────────────────────────────

test.describe("Studio wizard QoL", () => {
  test.beforeEach(async ({ page }) => {
    api = await installStudioMockApi(page);
    wfMock = await installWorkflowsMock(page);
    await pinPrimaryExtensionRequests(page);
    await openStudio(page, COMFYUI_URL);
    await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
    await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 15000 });
  });

  // ── Item 3: View button centers + highlights ────────────────────────────
  test("1. View centers the node and flashes a magenta highlight that clears", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      // The stored-graph prefetch (not the live capture path) seeds the
      // KSampler suggestions: seed/steps/cfg/sampler all point at node 4242.
      const { panel } = await openAbstractSetupWizard(page, async ({ version }) => {
        await stubVersionGraph(page, version, {
          nodes: [{ id: 4242, class_type: "KSampler", title: "Sampler 4242" }],
        });
      });

      const stub = await stubCanvasNode(page, 4242);
      expect(stub.ok).toBe(true);

      await expect(panel.locator('[data-testid="wizard-suggest-status"]')).toContainText(
        "Confirm each one below",
        { timeout: 10000 }
      );
      // Dependencies step is unconditional in version-setup: pass through it.
      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.locator('[data-testid="wizard-features-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({ timeout: 10000 });
      await panel.locator('[data-testid="wizard-dependencies-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-required-bindings"]')).toBeVisible({ timeout: 10000 });

      const seedRow = panel.locator('[data-testid="wizard-binding-row"][data-binding-key="seed"]');
      const suggestionView = seedRow.locator('[data-testid="wizard-view-suggestion"]');
      await expect(suggestionView).toBeVisible();
      await expect(suggestionView).toBeEnabled();
      await suggestionView.click();

      // Centering call happened and the highlight overlay is present.
      expect(await page.evaluate(() => window.__viewCalls)).toContain(4242);
      const highlight = page.locator('[data-testid="node-view-highlight"]');
      await expect(highlight).toBeVisible();

      // The transient border clears on its own (~3s), then confirming the
      // suggestion re-renders without leaving a stale overlay behind.
      await expect(highlight).toHaveCount(0, { timeout: 6000 });
      await seedRow.locator('[data-testid="wizard-use-suggestion"]').click();
      await expect(panel.locator('[data-testid="wizard-view-binding"][data-binding-key="seed"]')).toBeEnabled();

      const boundView = panel.locator('[data-testid="wizard-view-binding"][data-binding-key="seed"]');
      await boundView.click();
      expect((await page.evaluate(() => window.__viewCalls)).length).toBeGreaterThanOrEqual(2);
      await expect(highlight).toBeVisible();
      await expect(highlight).toHaveCount(0, { timeout: 6000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Item 4a/b: Dependencies step with Manager present ───────────────────
  test("2. dependencies step downloads models, installs packs, and reboots only on click", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      const seen = { batch: null, rescan: 0, queue: [], starts: 0, gitInstalls: [], reboots: 0, installedCalls: 0 };

      await page.route("**/manager/version", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ version: "abc123" }) });
      });
      await page.route("**/customnode/installed", async (route) => {
        seen.installedCalls += 1;
        // Manager returns a dict keyed by module name, not { nodes: [] }.
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
      });
      // Manager catalog supplies a source URL for the row that has none.
      await page.route("**/externalmodel/getlist**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ models: [
            {
              filename: "no_url.safetensors",
              url: "https://example.com/no_url.safetensors",
              reference: "https://example.com/no_url",
              save_path: "vae",
              name: "no_url.safetensors",
              installed: "False",
            },
          ] }),
        });
      });
      // Manager's default pack catalog + class mappings: the missing Donut
      // row carries only a CNR id, so these authoritative default endpoints
      // are what resolve it to a repository URL.
      await page.route("**/customnode/getlist**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            channel: "default",
            node_packs: {
              donutnodes: {
                title: "ComfyUI-DonutNodes",
                repository: "https://github.com/DonutsDelivery/ComfyUI-DonutNodes",
                state: "not-installed",
              },
            },
          }),
        });
      });
      await page.route("**/customnode/getmappings**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            donutnodes: [["DonutLoaderClass"], { title_aux: "ComfyUI-DonutNodes" }],
          }),
        });
      });
      await page.route("**/manager/queue/install", async (route) => {
        seen.queue.push(route.request().postDataJSON());
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      await page.route("**/manager/queue/start", async (route) => {
        seen.starts += 1;
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      await page.route("**/customnode/install/git_url", async (route) => {
        seen.gitInstalls.push(route.request().postDataJSON());
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      await page.route("**/manager/reboot", async (route) => {
        seen.reboots += 1;
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });
      // Explicit reboot now waits for the reconnect: /system_stats (ComfyUI
      // health) then /manager/version decide success, not the POST response.
      await page.route("**/system_stats", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ system: {} }) });
      });
      await page.route("**/comfymodal/models/batch-install", async (route) => {
        seen.batch = route.request().postDataJSON();
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", results: [] }) });
      });
      await page.route("**/comfymodal/studio/models/rescan", async (route) => {
        seen.rescan += 1;
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      });

      // Register the rich report BEFORE opening: the wizard prefetches
      // dependencies on open. (The detail page's own dependencies GET also
      // uses this override — harmless and keeps the two in sync.)
      const { panel } = await openAbstractSetupWizard(page, async ({ version }) => {
        await stubDependencies(page, version, {
          models: [
            {
              key: "model|needs_url.safetensors",
              role: "checkpoint",
              filename: "needs_url.safetensors",
              folder: "checkpoints",
              state: "missing",
              source_urls: ["https://example.com/needs_url.safetensors"],
            },
            {
              key: "model|no_url.safetensors",
              role: "vae",
              filename: "no_url.safetensors",
              state: "missing",
              source_urls: [],
            },
          ],
          custom_nodes: [
            {
              name: "ComfyUI-DonutNodes",
              state: "missing",
              repository_url: "",
              cnr_id: "donutnodes",
              classes: ["DonutLoaderClass"],
              required_revision: "",
            },
          ],
          summary: { installed: 0, missing: 2, wrong_version: 0, unknown: 0, attention: 2, ready: false },
        });
      });

      // Dependencies step is woven in (actionable report) and ordered first.
      const stepLabels = panel.locator(".comfymodal-studio-wizard-step-label");
      await expect(stepLabels).toHaveCount(4, { timeout: 10000 });
      await expect(stepLabels.nth(1)).toHaveText("Dependencies");
      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.locator('[data-testid="wizard-features-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({ timeout: 10000 });

      // Full report; once the Manager catalog loads, its source URL resolves
      // the source-less model, so nothing is skipped by Download all.
      await expect(panel.locator('[data-testid="dependency-model-row"]')).toHaveCount(2);
      await expect(panel.locator('[data-testid="dependency-node-row"]')).toHaveCount(1);
      await expect(panel.locator('[data-testid="wizard-manager-status"]')).toContainText("ComfyUI-Manager detected", { timeout: 10000 });
      await expect(panel.locator('[data-testid="wizard-download-skipped"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="wizard-download-all"]')).toHaveText("Download all (2)");

      // Missing model row exposes EXACTLY two explicit install actions; the
      // legacy single "Download on Modal" action is gone. The source-less row
      // gains both actions from the Manager catalog.
      const needsUrlRow = panel.locator('[data-testid="dependency-model-row"]').filter({ hasText: "needs_url.safetensors" });
      const noUrlRow = panel.locator('[data-testid="dependency-model-row"]').filter({ hasText: "no_url.safetensors" });
      await expect(needsUrlRow.getByTestId("dependency-model-queue")).toHaveText("Queue install");
      await expect(needsUrlRow.getByTestId("dependency-model-install-now")).toHaveText("Install now");
      await expect(needsUrlRow.getByTestId("dependency-model-download")).toHaveCount(0);
      await expect(noUrlRow.getByTestId("dependency-model-queue")).toBeVisible({ timeout: 10000 });
      await expect(noUrlRow.getByTestId("dependency-model-install-now")).toBeVisible();

      // Missing Donut row carries no repository in the report; Manager's
      // default getlist/getmappings resolve its cnr_id to the pack repo.
      const packRow = panel.locator('[data-testid="dependency-node-row"]').filter({ hasText: "ComfyUI-DonutNodes" });
      await expect(packRow.getByTestId("dependency-node-install-now")).toHaveText("Install now");
      await expect(packRow.locator('a[href="https://github.com/DonutsDelivery/ComfyUI-DonutNodes"]')).toHaveCount(1);
      await expect(panel.locator('[data-testid="dependency-node-install-request"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="dependency-node-manager-install"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="dependency-node-find-registry"]')).toHaveCount(0);

      // Install now on the catalog-sourced row → synchronous single-item batch
      // install with the Manager URL and save path.
      await noUrlRow.getByTestId("dependency-model-install-now").click();
      await expect.poll(() => seen.batch && seen.batch.items && seen.batch.items.length).toBe(1);
      expect(seen.batch.items[0]).toEqual({
        url: "https://example.com/no_url.safetensors",
        filename: "no_url.safetensors",
        save_path: "vae",
      });
      await expect.poll(() => seen.rescan).toBeGreaterThanOrEqual(1);
      seen.batch = null;
      seen.rescan = 0;

      // Download all → both missing models: the report URL model and the
      // Manager-catalog-sourced model (with its catalog save path).
      await panel.locator('[data-testid="wizard-download-all"]').click();
      await expect.poll(() => seen.batch && seen.batch.items && seen.batch.items.length).toBe(2);
      expect(seen.batch.items[0]).toEqual({
        url: "https://example.com/needs_url.safetensors",
        filename: "needs_url.safetensors",
        save_path: "checkpoints",
      });
      expect(seen.batch.items[1]).toEqual({
        url: "https://example.com/no_url.safetensors",
        filename: "no_url.safetensors",
        save_path: "vae",
      });
      await expect(panel.locator('[data-testid="wizard-dependencies-message"]')).toContainText("Requested 2 model downloads", { timeout: 10000 });
      expect(seen.rescan).toBe(1);

      // Per-pack Manager install → restart-required + explicit reboot only.
      const installBtn = panel.locator('[data-testid="dependency-node-install-now"]');
      await expect(installBtn).toBeVisible();
      expect(seen.reboots).toBe(0);
      await installBtn.click();
      await expect(panel.locator('[data-testid="wizard-restart-required"]')).toBeVisible({ timeout: 10000 });
      const rebootBtn = panel.locator('[data-testid="wizard-manager-reboot"]');
      await expect(rebootBtn).toBeVisible();
      expect(seen.reboots).toBe(0); // never before the explicit click
      // The identified Manager pack installs through Manager's queue. Its
      // catalog record carries blank version metadata, which must NOT push it
      // onto the security-gated git_url route.
      expect(seen.queue).toHaveLength(1);
      expect(seen.queue[0]).toMatchObject({
        id: "donutnodes",
        version: "unknown",
        selected_version: "latest",
        channel: "default",
      });
      expect(seen.starts).toBe(1);
      expect(seen.gitInstalls).toEqual([]);

      await rebootBtn.click();
      // Success is decided by the bounded reconnect probes, so the click only
      // reports completion once ComfyUI + Manager answer again.
      await expect(panel.locator('[data-testid="wizard-dependencies-message"]')).toContainText("reconnected", { timeout: 15000 });
      expect(seen.reboots).toBe(1);
      await expect(panel.locator('[data-testid="wizard-restart-required"]')).toHaveCount(0);

      // Continue is always available even though the VAE has no URL.
      const cont = panel.locator('[data-testid="wizard-dependencies-continue"]');
      await expect(cont).toBeEnabled();
      await cont.click();
      await expect(panel.locator('[data-testid="wizard-required-bindings"]')).toBeVisible({ timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Item 4b: Manager absent still exposes the single Manager action ──
  test("3. missing Manager is reported and pack rows keep exactly one Manager install action", async ({ page }) => {
    let guard;
    try {
      guard = installConsoleGuard(page);

      await page.route("**/manager/version", async (route) => {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ status: "error" }) });
      });

      const { panel } = await openAbstractSetupWizard(page, async ({ version }) => {
        await stubDependencies(page, version, {
          models: [],
          custom_nodes: [
            {
              name: "SomePack",
              state: "missing",
              repository_url: "https://github.com/example/SomePack",
              required_revision: "",
            },
          ],
          summary: { installed: 0, missing: 1, wrong_version: 0, unknown: 0, attention: 1, ready: false },
        });
      });

      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.locator('[data-testid="wizard-features-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-dependencies-continue"]')).toBeVisible({ timeout: 10000 });

      await expect(panel.locator('[data-testid="wizard-manager-status"]')).toContainText("Manager not detected", { timeout: 10000 });
      // The single Manager-backed install action is still the row's only
      // action — no record-only request, no second installer, no Find in registry.
      const packRow = panel.locator('[data-testid="dependency-node-row"]').filter({ hasText: "SomePack" });
      await expect(packRow.getByTestId("dependency-node-install-now")).toHaveText("Install now");
      await expect(panel.locator('[data-testid="dependency-node-install-request"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="dependency-node-manager-install"]')).toHaveCount(0);
      await expect(panel.locator('[data-testid="dependency-node-find-registry"]')).toHaveCount(0);

      await panel.locator('[data-testid="wizard-dependencies-continue"]').click();
      await expect(panel.locator('[data-testid="wizard-required-bindings"]')).toBeVisible({ timeout: 10000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });
});
