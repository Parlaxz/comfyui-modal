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
// Manager install on a missing dependency node, and the dependency→Model
// Library filter handoff.

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

test("custom-node registry browse, explicit refresh, Manager install, and library handoff", async ({ page }) => {
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

    // ── Workflow detail: missing node exposes the single Manager install ──
    await page.getByTestId("models-back").click();
    await expect(page.getByTestId("workflow-card").first()).toBeVisible({ timeout: 10000 });
    await page.getByTestId("workflow-card").first().click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });
    const missingRow = page.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-Missing" });
    await expect(missingRow).toContainText("Missing", { timeout: 10000 });

    const managerInstalls = [];
    await page.route("**/customnode/install/git_url", async (route) => {
      managerInstalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    const installBtn = missingRow.getByTestId("dependency-node-install-now");
    await expect(installBtn).toHaveText("Install now");
    await expect(missingRow.getByTestId("dependency-node-install-request")).toHaveCount(0);
    await installBtn.click();
    await expect.poll(() => managerInstalls.length).toBe(1);
    expect(managerInstalls[0]).toEqual({ url: "https://github.com/example/ComfyUI-Missing" });

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

test("wizard resolves a pure-CNR pack through Manager queue and reads the installed dict", async ({ page }) => {
  const fx = await setupFakeTest(page);
  const installs = [];
  const queue = [];
  const starts = [];
  try {
    // Two missing packs: one installable pure-CNR record, one already
    // installed-but-disabled record matched from Manager's dict response.
    await page.route("**/studio/workflows/versions/wv_fake/dependencies", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.custom_nodes = [
        {
          name: "ComfyUI-DonutNodes",
          state: "missing",
          repository_url: "",
          cnr_id: "donutnodes",
          classes: ["DonutLoaderClass"],
          required_revision: "",
          installed_commit: "",
        },
        {
          name: "DisabledPack",
          state: "missing",
          repository_url: "",
          cnr_id: "disabledpack",
          classes: ["DisabledClass"],
          required_revision: "",
          installed_commit: "",
        },
      ];
      payload.summary = { installed: 0, missing: 2, wrong_version: 0, unknown: 0, attention: 2, ready: false };
      await route.fulfill({ response, json: payload });
    });

    await page.route("**/manager/version", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ version: "abc" }) })
    );
    await page.route("**/externalmodel/getlist**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ models: [] }) })
    );
    // Manager's installed route returns a DICT keyed by module name, not
    // { nodes: [] }; disabled must stay truthful.
    await page.route("**/customnode/installed", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          disabledpack_dir: { ver: "0.9.0", cnr_id: "disabledpack", aux_id: "", enabled: false },
        }),
      })
    );
    await page.route("**/customnode/getlist**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          channel: "default",
          node_packs: {
            donutnodes: {
              title: "ComfyUI-DonutNodes",
              version: "1.2.3",
              install_type: "cnr",
              state: "not-installed",
            },
          },
        }),
      })
    );
    await page.route("**/customnode/getmappings**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ donutnodes: [["DonutLoaderClass"], { title_aux: "ComfyUI-DonutNodes" }] }),
      })
    );
    await page.route("**/customnode/install/git_url", async (route) => {
      installs.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/manager/queue/install", async (route) => {
      queue.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/manager/queue/start", async (route) => {
      starts.push(true);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
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

    // The installed dict's disabled record is reported truthfully: the row
    // stays missing (the registry dict is not class-loaded proof) and explains
    // the package is present but its classes are not loaded.
    const disabledRow = panel.getByTestId("dependency-node-row").filter({ hasText: "DisabledPack" });
    await expect(disabledRow.getByTestId("dependency-node-manager-stale")).toContainText("disabled", { timeout: 10000 });
    await expect(disabledRow.getByTestId("dependency-node-manager-installed")).toHaveCount(0);
    await expect(disabledRow.getByTestId("dependency-node-install-now")).toHaveCount(0);

    // The pure-CNR pack installs through Manager's queue, never git_url.
    const donutRow = panel.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-DonutNodes" });
    const installBtn = donutRow.getByTestId("dependency-node-install-now");
    await expect(installBtn).toHaveText("Install now", { timeout: 10000 });
    await installBtn.click();
    await expect.poll(() => queue.length).toBe(1);
    expect(queue[0]).toMatchObject({
      id: "donutnodes",
      version: "1.2.3",
      selected_version: "latest",
      channel: "default",
    });
    await expect.poll(() => starts.length).toBe(1);
    expect(installs).toEqual([]);
    await expect(panel.getByTestId("wizard-restart-required")).toBeVisible({ timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});

test("workflow detail resolves CNR/aux/class packs through the lazy Manager context", async ({ page }) => {
  const fx = await setupFakeTest(page);
  const queue = [];
  const starts = [];
  const gitInstalls = [];
  try {
    // Three missing packs, one per identity strategy (CNR id, aux repo slug,
    // class mapping). None carries a repository_url, so only the lazy
    // workflow-detail Manager context can resolve them.
    await page.route("**/studio/workflows/versions/wv_fake/dependencies", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.custom_nodes = [
        {
          name: "ComfyUI-DonutNodes", state: "missing", repository_url: "",
          cnr_id: "donutnodes", classes: ["DonutLoaderClass"],
          required_revision: "", installed_commit: "",
        },
        {
          name: "ComfyUI-KJNodes", state: "missing", repository_url: "",
          aux_id: "kijai/ComfyUI-KJNodes", classes: [],
          required_revision: "", installed_commit: "",
        },
        {
          name: "PatternPack", state: "missing", repository_url: "",
          classes: ["ExactClass"], required_revision: "", installed_commit: "",
        },
      ];
      payload.summary = { installed: 1, missing: 3, wrong_version: 0, unknown: 0, attention: 3, ready: false };
      await route.fulfill({ response, json: payload });
    });
    // Generic Manager probes are served by the fake backend's root-relative
    // stubs; only the catalog data and the queue capture need overrides.
    await page.route("**/customnode/getlist**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          channel: "default",
          node_packs: {
            donutnodes: {
              title: "ComfyUI-DonutNodes", version: "1.2.3", install_type: "cnr",
              repository: "https://github.com/DonutsDelivery/ComfyUI-DonutNodes",
            },
            "https://github.com/kijai/ComfyUI-KJNodes": {
              title: "ComfyUI-KJNodes", version: "2.0.0", install_type: "cnr",
              repository: "https://github.com/kijai/ComfyUI-KJNodes",
            },
            patternpack: {
              title: "PatternPack", version: "3.0.0", install_type: "cnr",
              repository: "https://github.com/ex/Pattern",
            },
          },
        }),
      })
    );
    await page.route("**/customnode/getmappings**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ donutnodes: [["DonutLoaderClass"], {}], patternpack: [["ExactClass"], {}] }),
      })
    );
    await page.route("**/manager/queue/install", async (route) => {
      queue.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/manager/queue/start", async (route) => {
      starts.push(true);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/customnode/install/git_url", async (route) => {
      gitInstalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });

    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("workflow-card").first().click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

    // Each identity strategy resolves to the single Manager-backed install.
    for (const name of ["ComfyUI-DonutNodes", "ComfyUI-KJNodes", "PatternPack"]) {
      const row = page.getByTestId("dependency-node-row").filter({ hasText: name });
      await expect(row.getByTestId("dependency-node-install-now")).toHaveText("Install now", { timeout: 10000 });
    }

    // Explicit click → Manager CNR queue (install + start), never git_url.
    const donutRow = page.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-DonutNodes" });
    await donutRow.getByTestId("dependency-node-install-now").click();
    await expect.poll(() => queue.length).toBe(1);
    expect(queue[0]).toMatchObject({
      id: "donutnodes", version: "1.2.3", selected_version: "latest", channel: "default",
    });
    await expect.poll(() => starts.length).toBe(1);
    expect(gitInstalls).toEqual([]);
    // The direct (no onInstallPack) path reports the restart requirement
    // truthfully in the row note; nothing reboots.
    await expect(donutRow.getByTestId("dependency-node-install-note")).toContainText("restart", { timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    fx.guard.dispose();
  }
});

// Test D: source-less missing model row exposes an explicit URL install.
// The URL is handed to the legacy backend install route (the browser never
// fetches model bytes), the row's state badge reports the in-flight truth,
// and the sourced row keeps its two existing actions.
test("source-less dependency model installs from an explicit URL", async ({ page }) => {
  const fx = await setupFakeTest(page);
  const installs = [];
  const statusPolls = [];
  let releaseInstall = null;
  const installGate = new Promise((resolve) => { releaseInstall = resolve; });
  try {
    // Add a source-less missing model to the served dependency report.
    await page.route("**/studio/workflows/versions/wv_fake/dependencies", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.models.push({
        key: "vae|untracked.safetensors",
        role: "vae",
        filename: "untracked.safetensors",
        folder: "vae",
        state: "missing",
        source_urls: [],
      });
      payload.summary.attention = (payload.summary.attention || 0) + 1;
      await route.fulfill({ response, json: payload });
    });

    // Hold the explicit install POST so the in-flight badge is observable.
    await page.route("**/comfymodal/model/install", async (route) => {
      installs.push(route.request().postDataJSON());
      await installGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", download_id: "dl_fake" }),
      });
    });
    await page.route("**/download/status/**", (route) => {
      statusPolls.push(route.request().url());
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", state: "complete" }),
      });
    });

    await fx.gotoPage("workflows");
    await expect(page.getByTestId("workflows-page")).toBeVisible({ timeout: 10000 });
    await page.getByTestId("workflow-card").first().click();
    await expect(page.getByTestId("workflow-detail")).toBeVisible({ timeout: 15000 });

    // Sourced missing row: both existing actions preserved; the redundant
    // "Not installed" detail is replaced by the state badge alone.
    const sourced = page.getByTestId("dependency-model-row").filter({ hasText: "krea_model.safetensors" });
    await expect(sourced.getByTestId("dependency-model-queue")).toHaveText("Queue install", { timeout: 10000 });
    await expect(sourced.getByTestId("dependency-model-install-now")).toHaveText("Install now");
    await expect(sourced.getByTestId("dependency-model-state")).toHaveText("Missing");
    await expect(sourced).not.toContainText("Not installed");

    // Source-less row: no guessed action; explicit URL input + action instead.
    const sourceLess = page.getByTestId("dependency-model-row").filter({ hasText: "untracked.safetensors" });
    await expect(sourceLess.getByTestId("dependency-model-state")).toHaveText("Missing", { timeout: 10000 });
    await expect(sourceLess.getByTestId("dependency-model-queue")).toHaveCount(0);
    await expect(sourceLess.getByTestId("dependency-model-install-now")).toHaveCount(0);
    const urlInput = sourceLess.getByTestId("dependency-model-url-input");
    await expect(urlInput).toBeVisible({ timeout: 10000 });
    await urlInput.fill("https://example.com/untracked.safetensors");

    await sourceLess.getByTestId("dependency-model-url-install").click();
    // In-flight truth on the SAME badge node, before the request resolves.
    await expect(sourceLess.getByTestId("dependency-model-state")).toHaveText("Downloading\u2026");
    await expect.poll(() => installs.length).toBe(1);
    releaseInstall();
    await expect.poll(() => statusPolls.length).toBeGreaterThanOrEqual(1);

    expect(installs[0]).toEqual({
      url: "https://example.com/untracked.safetensors",
      filename: "untracked.safetensors",
      save_path: "vae",
    });

    fx.assertNoConsoleErrors();
  } finally {
    releaseInstall();
    fx.guard.dispose();
  }
});

// Test E (requirement 4): explicit queue actions report on the row's OWN state
// badge — "Queued for download" for a model, "Queued" for a custom node — and
// survive a wizard re-render (no detached supplemental chip). Once an install
// settles the report reconciles the badge truthfully.
test("queued status lives on the row state badge and survives wizard re-renders", async ({ page }) => {
  const fx = await setupFakeTest(page);
  const modelStarts = [];
  const nodeQueue = [];
  let releaseModel = null;
  const modelGate = new Promise((resolve) => { releaseModel = resolve; });
  let releaseQueue = null;
  const queueGate = new Promise((resolve) => { releaseQueue = resolve; });
  try {
    await page.route("**/studio/workflows/versions/wv_fake/dependencies", async (route) => {
      const response = await route.fetch();
      const payload = await response.json();
      payload.custom_nodes = [{
        name: "ComfyUI-DonutNodes", state: "missing", repository_url: "",
        cnr_id: "donutnodes", classes: ["DonutLoaderClass"],
        required_revision: "", installed_commit: "",
      }];
      payload.summary = { installed: 1, missing: 2, wrong_version: 0, unknown: 0, attention: 2, ready: false };
      await route.fulfill({ response, json: payload });
    });
    await page.route("**/manager/version", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ version: "abc" }) })
    );
    await page.route("**/externalmodel/getlist**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ models: [] }) })
    );
    await page.route("**/customnode/installed", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })
    );
    await page.route("**/customnode/getlist**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          channel: "default",
          node_packs: { donutnodes: { title: "ComfyUI-DonutNodes", version: "1.2.3", install_type: "cnr" } },
        }),
      })
    );
    await page.route("**/customnode/getmappings**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ donutnodes: [["DonutLoaderClass"], {}] }),
      })
    );
    // Hold the Manager queue so the node "Queued" badge stays observable.
    await page.route("**/manager/queue/install", async (route) => {
      nodeQueue.push(route.request().postDataJSON());
      await queueGate;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/manager/queue/start", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
    );
    // Hold the async model install so its queued badge stays observable.
    await page.route("**/comfymodal/model/install", async (route) => {
      modelStarts.push(route.request().postDataJSON());
      await modelGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", download_id: "dl_q" }),
      });
    });
    await page.route("**/download/status/**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", state: "complete" }) })
    );
    await page.route("**/comfymodal/studio/models/rescan", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) })
    );

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

    // Model Queue install → the row's own state badge reads "Queued for
    // download"; there is no detached supplemental status chip.
    const modelRow = panel.getByTestId("dependency-model-row").filter({ hasText: "krea_model.safetensors" });
    const modelBadge = modelRow.getByTestId("dependency-model-state");
    await expect(modelBadge).toHaveText("Missing", { timeout: 10000 });
    await expect(panel.getByTestId("dependency-install-status")).toHaveCount(0);
    await modelRow.getByTestId("dependency-model-queue").click();
    await expect(modelBadge).toHaveText("Queued for download");
    await expect.poll(() => modelStarts.length).toBe(1);

    // An in-wizard re-render (Refresh) must not drop the tracked status.
    await panel.getByTestId("wizard-dependencies-refresh").click();
    await expect(modelBadge).toHaveText("Queued for download", { timeout: 10000 });
    await expect(panel.getByTestId("dependency-install-status")).toHaveCount(0);

    // Custom-node install → its missing badge reads "Queued", also surviving a
    // re-render.
    const nodeRow = panel.getByTestId("dependency-node-row").filter({ hasText: "ComfyUI-DonutNodes" });
    const nodeBadge = nodeRow.getByTestId("dependency-node-state");
    await nodeRow.getByTestId("dependency-node-install-now").click();
    await expect(nodeBadge).toHaveText("Queued", { timeout: 10000 });
    await panel.getByTestId("wizard-dependencies-refresh").click();
    await expect(nodeBadge).toHaveText("Queued", { timeout: 10000 });
    await expect.poll(() => nodeQueue.length).toBe(1);

    // Settle both installs: the refreshed report is truth, so the pseudo-status
    // yields to "Missing" (the fake report is unchanged).
    releaseModel();
    await expect(modelBadge).toHaveText("Missing", { timeout: 10000 });
    releaseQueue();
    await expect(nodeBadge).toHaveText("Missing", { timeout: 10000 });

    fx.assertNoConsoleErrors();
  } finally {
    releaseModel();
    releaseQueue();
    fx.guard.dispose();
  }
});
