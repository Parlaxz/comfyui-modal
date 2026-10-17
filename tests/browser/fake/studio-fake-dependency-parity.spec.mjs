// Modal Studio — workflow dependency parity (fake backend + interceptions).
//
// Proves the restored legacy dependency semantics in Vue:
// - truthful summary derived from visible rows (required vs optional missing);
// - sourced rows: source link + Install now + Queue install + Find in library;
// - source-less rows: Manager catalog match → install; else URL input + find;
// - installed rows: no install actions;
// - Optional toggles nonessential state only, never installs;
// - custom-node rows: install gated behind a safe Manager/repo match,
//   otherwise Find in registry (library handoff).

import { test, expect } from "@playwright/test";
import { openVuePage } from "./helpers.mjs";

const workflow = { workflow_id: "wf_deppar", name: "Dep Parity", workflow_type: "t2i", latest_version_id: "ver_deppar" };
const version = { workflow_version_id: "ver_deppar", workflow_id: "wf_deppar", version: 1 };

function depRoutes(deps, { nonessential = null, managerModels = null } = {}) {
  const routes = [
    ["**/comfymodal/studio/workflows", async (route) => {
      if (route.request().method() !== "GET") {
        await route.fallback();
        return;
      }
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflows: [workflow] }) });
    }],
    ["**/comfymodal/studio/workflows/wf_deppar", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", workflow }) });
    }],
    ["**/comfymodal/studio/workflows/wf_deppar/versions", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", versions: [version] }) });
    }],
    ["**/comfymodal/studio/workflows/versions/ver_deppar**", async (route) => {
      const tail = new URL(route.request().url()).pathname.split("/").pop();
      const bodies = {
        mapping: { status: "ok", mapping: null },
        dependencies: { status: "ok", ...deps },
        compatibility: { status: "ok" },
        portability: { status: "ok", portability: { risk_level: "low", issue_count: 0 } },
        presets: { status: "ok", presets: [] },
      };
      const body = tail === "ver_deppar" ? { status: "ok", version } : (bodies[tail] ?? { status: "ok" });
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    }],
  ];
  if (nonessential !== null) {
    routes.push(["**/comfymodal/studio/workflows/wf_deppar/dependencies/nonessential", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", nonessential_keys: nonessential }) });
    }]);
  }
  if (managerModels !== null) {
    // Root path (no /manager prefix): Manager serves its API at the server
    // root — verified live against this ComfyUI/Manager build.
    routes.push(["**/externalmodel/getlist*", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(managerModels) });
    }]);
    routes.push(["**/manager/customnode/getlist*", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ node_packs: {} }) });
    }]);
    routes.push(["**/manager/customnode/getmappings*", async (route) => {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({}) });
    }]);
  }
  return routes;
}

async function openDetail(page) {
  await page.click('[data-testid="vue-workflow-wf_deppar"]');
  await page.waitForSelector('[data-testid="vue-dependencies"]', { timeout: 30000 });
}

const SOURCED = {
  models: [
    { key: "m-src", filename: "sourced.safetensors", folder: "diffusion_models", state: "missing", source_urls: ["https://example.com/s.safetensors"] },
    { key: "m-ok", filename: "ready.safetensors", folder: "vae", state: "installed" },
  ],
  custom_nodes: [],
  summary: { installed: 0, missing: 0, ready: false },
};

test.describe("Studio dependency parity", () => {
  test("summary is truthful and sourced rows expose queue/install/source/find", async ({ page }) => {
    const installs = [];
    const queues = [];
    await openVuePage(page, "workflows", [
      ...depRoutes(SOURCED),
      ["**/comfymodal/model/install", async (route) => {
        installs.push(await route.request().postDataJSON());
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
      ["**/comfymodal/studio/models/install-request", async (route) => {
        queues.push(await route.request().postDataJSON());
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
    ]);
    await openDetail(page);
    await expect(page.locator('[data-testid="vue-dependencies"]')).toContainText("1 missing", { timeout: 30000 });
    await expect(page.locator('[data-testid="vue-dependencies"]')).toContainText("attention");
    const row = page.locator('[data-testid="dependency-model-row"]').filter({ hasText: "sourced.safetensors" });
    await expect(row.getByTestId("dependency-model-install-now")).toBeVisible();
    await expect(row.getByTestId("dependency-model-queue")).toBeVisible();
    await expect(row.getByTestId("dependency-model-find")).toBeVisible();
    await expect(row.locator('a:has-text("source")')).toBeVisible();
    await row.getByTestId("dependency-model-queue").click();
    await expect.poll(() => queues.length).toBe(1);
    expect(queues[0].url).toBe("https://example.com/s.safetensors");
    await row.getByTestId("dependency-model-install-now").click();
    await expect.poll(() => installs.length).toBe(1);
    const installed = page.locator('[data-testid="dependency-model-row"]').filter({ hasText: "ready.safetensors" });
    await expect(installed.getByTestId("dependency-model-install-now")).toHaveCount(0);
    await expect(installed.getByTestId("dependency-model-queue")).toHaveCount(0);
  });

  test("optional-only missing reads ready and Optional never installs", async ({ page }) => {
    const posts = [];
    const installs = [];
    const deps = {
      models: [{ key: "m-opt", filename: "opt.safetensors", folder: "loras", state: "missing", nonessential: true }],
      custom_nodes: [],
      summary: { installed: 0, missing: 0, ready: true },
      nonessential_keys: ["m-opt"],
    };
    await openVuePage(page, "workflows", [
      ...depRoutes(deps),
      ["**/comfymodal/studio/workflows/wf_deppar/dependencies/nonessential", async (route) => {
        posts.push(await route.request().postDataJSON());
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
      ["**/comfymodal/model/install", async (route) => {
        installs.push(1);
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
      ["**/comfymodal/studio/models/install-request", async (route) => {
        installs.push(1);
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
    ]);
    await openDetail(page);
    await expect(page.locator('[data-testid="vue-dependencies"]')).toContainText("optional missing", { timeout: 30000 });
    await expect(page.locator('[data-testid="vue-dependencies"]')).toContainText("ready");
    const row = page.locator('[data-testid="dependency-model-row"]').filter({ hasText: "opt.safetensors" });
    await row.locator('input[type="checkbox"]').click();
    await expect.poll(() => posts.length).toBeGreaterThanOrEqual(1);
    expect(installs).toEqual([]);
  });

  test("manager match installs; unmatched gets URL input and library handoff", async ({ page }) => {
    const deps = {
      models: [
        { key: "m-mgr", filename: "managed-model.safetensors", folder: "diffusion_models", state: "missing" },
        { key: "m-none", filename: "mystery.safetensors", folder: "loras", state: "missing" },
      ],
      custom_nodes: [],
      summary: { installed: 0, missing: 2, ready: false },
    };
    await openVuePage(page, "workflows", [
      ...depRoutes(deps, { managerModels: [{ filename: "managed-model.safetensors", url: "https://example.com/m.safetensors", save_path: "diffusion_models", type: "diffusion_model" }] }),
      ["**/comfymodal/model/install", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
    ]);
    await openDetail(page);
    const matched = page.locator('[data-testid="dependency-model-row"]').filter({ hasText: "managed-model.safetensors" });
    await expect(matched.getByTestId("dependency-model-install-now")).toBeVisible({ timeout: 30000 });
    const unmatched = page.locator('[data-testid="dependency-model-row"]').filter({ hasText: "mystery.safetensors" });
    await expect(unmatched.getByTestId("dependency-model-install-now")).toHaveCount(0);
    await expect(unmatched.locator('[data-testid^="dependency-model-url-"]')).toBeVisible();
    await unmatched.getByTestId("dependency-model-find").click();
    await expect(page.locator('[data-testid="vue-library-search"]')).toHaveValue("mystery.safetensors");
  });

  test("node install gated behind safe match; otherwise registry handoff", async ({ page }) => {
    const deps = {
      models: [],
      custom_nodes: [
        { name: "NoMatchNode", state: "missing" },
        { name: "RepoNode", state: "missing", repository_url: "https://github.com/example/RepoNode" },
      ],
      summary: { installed: 0, missing: 2, ready: false },
    };
    await openVuePage(page, "workflows", [
      ...depRoutes(deps, { managerModels: [] }),
      ["**/manager/customnode/install*", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
      }],
    ]);
    await openDetail(page);
    const gated = page.locator('[data-testid="dependency-node-row"]').filter({ hasText: "NoMatchNode" });
    await expect(gated.getByTestId("dependency-node-install-now")).toHaveCount(0);
    await expect(gated.getByTestId("dependency-node-find")).toBeVisible({ timeout: 30000 });
    await gated.getByTestId("dependency-node-find").click();
    await expect(page.locator('[data-testid="vue-library-search"]')).toHaveValue("NoMatchNode");
  });
});
