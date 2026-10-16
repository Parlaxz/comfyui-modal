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
import { setupFakeTest, openVuePage } from "./helpers.mjs";

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
  // Vue behavior: importing a workflow refreshes the library; selecting it
  // shows the server dependency summary (installed/missing/ready state).
  // Run-button gating itself is Phase 5 (no run controls exist yet); the
  // version readiness line is the Vue-owned parity surface.
  const workflow = { workflow_id: "wf_dep", name: "Dep Flow", workflow_type: "t2i", latest_version_id: "ver_dep" };
  const version = { workflow_version_id: "ver_dep", version: 1, runnable: false };
  await openVuePage(page, "workflows", [
    ["**/comfymodal/studio/workflows/import", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow_id: "wf_dep", workflow_version_id: "ver_dep" }) });
    }],
    ["**/comfymodal/studio/workflows**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/comfymodal/studio/workflows" && route.request().method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
      } else if (url.pathname === "/comfymodal/studio/workflows/wf_dep") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
      } else if (url.pathname === "/comfymodal/studio/workflows/wf_dep/versions") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
      } else if (url.pathname.startsWith("/comfymodal/studio/workflows/versions/ver_dep")) {
        const tail = url.pathname.split("/").pop();
        const bodies = {
          mapping: { status: "ok", mapping: null },
          dependencies: { status: "ok", models: [{ key: "ckpt|krea_model.safetensors", filename: "krea_model.safetensors", folder: "checkpoints", state: "missing" }], custom_nodes: [], summary: { installed: 0, missing: 1, attention: 1, ready: false } },
          compatibility: { status: "ok" },
          portability: { status: "ok", portability: { risk_level: "high", issue_count: 1 } },
          presets: { status: "ok", presets: [] },
          state: { status: "ok", runnable: false },
        };
        const body = tail === "ver_dep" ? { status: "ok", version } : (bodies[tail] ?? { status: "ok" });
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
      } else {
        await route.fallback();
      }
    }],
  ]);
  await page.waitForSelector('[data-testid="vue-workflow-wf_dep"]', { timeout: 60000 });
  await page.fill('[data-testid="vue-workflow-import-input"]', JSON.stringify({ name: "Dep Flow", static_graph: {} }));
  await page.click('[data-testid="vue-workflow-import"]');
  await page.waitForSelector('[data-testid="vue-workflow-wf_dep"]', { timeout: 30000 });
  await page.click('[data-testid="vue-workflow-wf_dep"]');
  await expect(page.locator('[data-testid="vue-dependencies"]')).toContainText("1 missing", { timeout: 30000 });
  await expect(page.locator('[data-testid="vue-version-runnable"]')).toContainText("Not runnable", { timeout: 15000 });
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
  // Vue behavior: the Models tab browses the shared registry with
  // explicit-only refresh; a missing workflow dependency node installs
  // through the single Manager path (git fallback for unmatched packs).
  const gitInstalls = [];
  const workflow = { workflow_id: "wf_nodes", name: "Node Flow", workflow_type: "t2i", latest_version_id: "ver_nodes" };
  const version = { workflow_version_id: "ver_nodes", version: 1, runnable: false };
  const nodePayload = {
    status: "ok",
    models: [],
    custom_nodes: [{ name: "ComfyUI-Missing", state: "missing", repository_url: "https://github.com/example/ComfyUI-Missing", required_revision: "", installed_commit: "" }],
    summary: { installed: 0, missing: 1, attention: 1, ready: false },
  };
  await openVuePage(page, "workflows", [
    ["**/comfymodal/studio/workflows**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/comfymodal/studio/workflows" && route.request().method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
      } else if (url.pathname === "/comfymodal/studio/workflows/wf_nodes") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
      } else if (url.pathname === "/comfymodal/studio/workflows/wf_nodes/versions") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
      } else if (url.pathname.startsWith("/comfymodal/studio/workflows/versions/ver_nodes")) {
        const tail = url.pathname.split("/").pop();
        if (tail === "dependencies") {
          await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nodePayload) });
        } else if (tail === "ver_nodes") {
          await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", version }) });
        } else {
          await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
        }
      } else {
        await route.fallback();
      }
    }],
    ["**/customnode/getlist**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ channel: "default", node_packs: {} }) })],
    ["**/customnode/getmappings**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) })],
    ["**/customnode/install/git_url", async (route) => {
      gitInstalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
  ]);
  await page.waitForSelector('[data-testid="vue-workflow-wf_nodes"]', { timeout: 60000 });
  await page.click('[data-testid="vue-workflow-wf_nodes"]');
  const missingRow = page.locator('[data-testid="dependency-node-row"]').filter({ hasText: "ComfyUI-Missing" });
  await expect(missingRow).toContainText("missing", { timeout: 30000 });
  const installBtn = missingRow.getByTestId("dependency-node-install-now");
  await expect(installBtn).toHaveText("Install now");
  await installBtn.click();
  await expect.poll(() => gitInstalls.length).toBe(1);
  expect(gitInstalls[0]).toEqual({ url: "https://github.com/example/ComfyUI-Missing" });
  await expect(missingRow).toContainText("restart", { timeout: 15000 });
});

test("wizard resolves a pure-CNR pack through Manager queue and reads the installed dict", async ({ page }) => {
  // Vue behavior: a missing node identified by the Manager catalog (CNR id,
  // aux slug, or class) installs through the Manager CNR queue + start —
  // never the git_url gate — with a truthful restart note. Unmatched packs
  // without a repository report no target instead of guessing a URL.
  const queue = [];
  const starts = [];
  const gitInstalls = [];
  const workflow = { workflow_id: "wf_cnr", name: "CNR Flow", workflow_type: "t2i", latest_version_id: "ver_cnr" };
  const version = { workflow_version_id: "ver_cnr", version: 1, runnable: false };
  const nodePayload = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "ComfyUI-DonutNodes", state: "missing", repository_url: "", cnr_id: "donutnodes", classes: ["DonutLoaderClass"], required_revision: "", installed_commit: "" },
    ],
    summary: { installed: 0, missing: 1, wrong_version: 0, unknown: 0, attention: 1, ready: false },
  };
  await openVuePage(page, "workflows", [
    ["**/comfymodal/studio/workflows", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
    }],
    ["**/comfymodal/studio/workflows/wf_cnr", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
    }],
    ["**/comfymodal/studio/workflows/wf_cnr/versions", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
    }],
    ["**/comfymodal/studio/workflows/versions/ver_cnr**", async (route) => {
      const tail = new URL(route.request().url()).pathname.split("/").pop();
      if (tail === "dependencies") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nodePayload) });
      } else if (tail === "ver_cnr") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", version }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }
    }],
    ["**/customnode/getlist**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ channel: "default", node_packs: { donutnodes: { title: "ComfyUI-DonutNodes", version: "1.2.3", install_type: "cnr" } } }) })],
    ["**/customnode/getmappings**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ donutnodes: [["DonutLoaderClass"], {}] }) })],
    ["**/customnode/install/git_url", async (route) => {
      gitInstalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
    ["**/manager/queue/install", async (route) => {
      queue.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
    ["**/manager/queue/start", async (route) => {
      starts.push(true);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
  ]);
  await page.waitForSelector('[data-testid="vue-workflow-wf_cnr"]', { timeout: 60000 });
  await page.click('[data-testid="vue-workflow-wf_cnr"]');
  const donutRow = page.locator('[data-testid="dependency-node-row"]').filter({ hasText: "ComfyUI-DonutNodes" });
  await expect(donutRow).toContainText("missing", { timeout: 30000 });
  const installBtn = donutRow.getByTestId("dependency-node-install-now");
  await expect(installBtn).toHaveText("Install now");
  await installBtn.click();
  await expect.poll(() => queue.length).toBe(1);
  expect(queue[0]).toMatchObject({ id: "donutnodes", version: "1.2.3", selected_version: "latest", channel: "default" });
  await expect.poll(() => starts.length).toBe(1);
  expect(gitInstalls).toEqual([]);
  await expect(donutRow.getByTestId("dependency-node-install-note")).toContainText("restart", { timeout: 15000 });
});

test("workflow detail resolves CNR/aux/class packs through the lazy Manager context (Vue)", async ({ page }) => {
  // Vue behavior: each identity strategy (CNR id, aux repo slug, class
  // mapping) resolves through the lazily loaded Manager catalog to the
  // single Manager-backed install.
  const queue = [];
  const starts = [];
  const gitInstalls = [];
  const workflow = { workflow_id: "wf_ctx", name: "Context Flow", workflow_type: "t2i", latest_version_id: "ver_ctx" };
  const version = { workflow_version_id: "ver_ctx", version: 1, runnable: false };
  // Three missing packs, one per identity strategy (CNR id, aux repo slug,
  // class mapping). None carries a repository_url, so only the lazy
  // workflow-detail Manager context can resolve them.
  const nodePayload = {
    status: "ok",
    models: [],
    custom_nodes: [
      { name: "ComfyUI-DonutNodes", state: "missing", repository_url: "", cnr_id: "donutnodes", classes: ["DonutLoaderClass"], required_revision: "", installed_commit: "" },
      { name: "ComfyUI-KJNodes", state: "missing", repository_url: "", aux_id: "kijai/ComfyUI-KJNodes", classes: [], required_revision: "", installed_commit: "" },
      { name: "PatternPack", state: "missing", repository_url: "", classes: ["ExactClass"], required_revision: "", installed_commit: "" },
    ],
    summary: { installed: 1, missing: 3, wrong_version: 0, unknown: 0, attention: 3, ready: false },
  };
  await openVuePage(page, "workflows", [
    ["**/comfymodal/studio/workflows", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
    }],
    ["**/comfymodal/studio/workflows/wf_ctx", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
    }],
    ["**/comfymodal/studio/workflows/wf_ctx/versions", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
    }],
    ["**/comfymodal/studio/workflows/versions/ver_ctx**", async (route) => {
      const tail = new URL(route.request().url()).pathname.split("/").pop();
      if (tail === "dependencies") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(nodePayload) });
      } else if (tail === "ver_ctx") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", version }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }
    }],
    // Generic Manager probes are served by root-relative stubs; only the
    // catalog data and the queue capture need overrides.
    ["**/customnode/getlist**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ channel: "default", node_packs: {
        donutnodes: { title: "ComfyUI-DonutNodes", version: "1.2.3", install_type: "cnr", repository: "https://github.com/DonutsDelivery/ComfyUI-DonutNodes" },
        "https://github.com/kijai/ComfyUI-KJNodes": { title: "ComfyUI-KJNodes", version: "2.0.0", install_type: "cnr", repository: "https://github.com/kijai/ComfyUI-KJNodes" },
        patternpack: { title: "PatternPack", version: "3.0.0", install_type: "cnr", repository: "https://github.com/ex/Pattern" },
      } }) })],
    ["**/customnode/getmappings**", (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ donutnodes: [["DonutLoaderClass"], {}], patternpack: [["ExactClass"], {}] }) })],
    ["**/manager/queue/install", async (route) => {
      queue.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
    ["**/manager/queue/start", async (route) => {
      starts.push(true);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
    ["**/customnode/install/git_url", async (route) => {
      gitInstalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
  ]);
  await page.waitForSelector('[data-testid="vue-workflow-wf_ctx"]', { timeout: 60000 });
  await page.click('[data-testid="vue-workflow-wf_ctx"]');

  // Each identity strategy resolves to the single Manager-backed install.
  for (const name of ["ComfyUI-DonutNodes", "ComfyUI-KJNodes", "PatternPack"]) {
    const row = page.locator('[data-testid="dependency-node-row"]').filter({ hasText: name });
    await expect(row.getByTestId("dependency-node-install-now")).toHaveText("Install now", { timeout: 30000 });
  }

  // Explicit click → Manager CNR queue (install + start), never git_url.
  const donutRow = page.locator('[data-testid="dependency-node-row"]').filter({ hasText: "ComfyUI-DonutNodes" });
  await donutRow.getByTestId("dependency-node-install-now").click();
  await expect.poll(() => queue.length).toBe(1);
  expect(queue[0]).toMatchObject({
    id: "donutnodes", version: "1.2.3", selected_version: "latest", channel: "default",
  });
  await expect.poll(() => starts.length).toBe(1);
  expect(gitInstalls).toEqual([]);
  // The direct path reports the restart requirement truthfully in the row
  // note; nothing reboots.
  await expect(donutRow.getByTestId("dependency-node-install-note")).toContainText("restart", { timeout: 15000 });
});

// Test D: source-less missing model row exposes an explicit URL install.
// Vue behavior: the Models tab URL installer hands the URL to the legacy
// backend install route (the browser never fetches model bytes) with the
// inferred filename + save path, and reports acceptance truthfully.
test("source-less dependency model installs from an explicit URL", async ({ page }) => {
  const installs = [];
  await openVuePage(page, "backend", [
    ["**/comfymodal/model/install", async (route) => {
      installs.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    }],
  ]);
  await page.click('[data-testid="vue-backend-tab-models"]');
  await page.fill('[data-testid="vue-model-url"]', "https://example.com/untracked.safetensors");
  await page.click('[data-testid="vue-model-install"]');
  await expect.poll(() => installs.length).toBe(1);
  expect(installs[0]).toEqual({
    url: "https://example.com/untracked.safetensors",
    filename: "untracked.safetensors",
    save_path: "diffusion_models",
  });
  await expect(page.locator('[data-testid="vue-model-install-message"]')).toContainText("accepted");
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
