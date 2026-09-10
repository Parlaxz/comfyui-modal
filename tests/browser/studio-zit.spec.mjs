// Modal Studio — ZIT end-to-end (live workflows backend + stubbed execution).
//
// Drives the full studio workflow as a real user against the LIVE ComfyUI
// backend for everything the backend owns, with deterministic stubs ONLY
// for execution and history projection:
//
//   LIVE (real backend chain): workflows import (176-node ZIT graph),
//     mapping candidates derivation, mapping POST, presets, run-context,
//     model-stack/dependency metadata.
//   STUBBED (deterministic, no GPU/models): POST /studio/run +
//     /experiments/* polling, POST /studio/experiment-v2 + status,
//     /history-v2/feed + detail + favorite/note, asset bytes.
//
// Flow (single consolidated test):
//   1. Import the ZIT file via setInputFiles (absolute path) → library.
//   2. Wizard: stored-graph suggestions confirmed where the catalog covers
//      them (prompt/model_unet/vae/output); seed + clip bound through the
//      canvas-capture path after loading the ZIT graph onto the canvas.
//      Save → runnable mapping.
//   3. New preset with required values → run-context Ready.
//   4. Playground single run → progress advances/completes → canvas output.
//   5. Seed x prompt 2x2 experiment → 4/4 cells complete.
//   6. History feed shows both → detail + favorite + note → experiment 2x2.
//
// Requires the backend UI-format graph conversion (studio_domain/graph.py
// ui_graph_to_api_prompt) — without it the import yields no candidates and
// the version can never become runnable.

import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { installConsoleGuard, openStudio } from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const ZIT_ABS = "C:\\Users\\parla\\Downloads\\ZIT - Current Favorite.json";
const ZIT_NAME = "ZIT - Current Favorite";

const APP_NOISE_PATTERNS = [
  "already registered",
  "vite:preloadError",
  "Failed to load resource",
  "ComfyApp graph accessed",
];

// ZIT model filenames (from the graph's loader widgets) served through the
// stubbed model library so the preset model pickers can bind them.
const ZIT_MODELS = [
  { model_id: "unet_z_image", filename: "z_image_turbo_bf16.safetensors", display_name: "z_image_turbo_bf16", model_type: "unet", installed: false, size: 0 },
  { model_id: "vae_ae", filename: "ae.safetensors", display_name: "ae", model_type: "vae", installed: false, size: 0 },
  { model_id: "clip_qwen", filename: "qwen_3_4b.safetensors", display_name: "qwen_3_4b", model_type: "clip", installed: false, size: 0 },
];

const PNG_1PX = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64"
);

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

/** Load the ZIT graph onto the ComfyUI canvas (same code path as file-drop). */
async function loadZitOntoCanvas(page, zit) {
  return page.evaluate((graph) => {
    const app = window.app || window.__comfymodal_comfy_app;
    if (!app || typeof app.loadGraphData !== "function") return "no-app";
    try {
      app.loadGraphData(graph);
    } catch (e) {
      return "load-error:" + (e && e.message);
    }
    const n = app.graph && app.graph.nodes ? app.graph.nodes.length : -1;
    return "loaded:" + n;
  }, zit);
}

/** Programmatically select a canvas node by id; returns its widget names. */
async function selectCanvasNode(page, nodeId) {
  return page.evaluate((id) => {
    const app = window.app || window.__comfymodal_comfy_app;
    if (!app || !app.graph) return null;
    const node = app.graph.getNodeById(Number(id));
    if (!node) return null;
    const canvas = app.canvas;
    try {
      if (canvas && typeof canvas.deselectAll === "function") canvas.deselectAll();
    } catch { /* ignore */ }
    try {
      if (canvas && typeof canvas.selectNode === "function") canvas.selectNode(node, false);
      else node.selected = true;
    } catch { node.selected = true; }
    return {
      id: node.id,
      type: node.type,
      widgets: ((node.widgets || []).map((w) => w && w.name).filter(Boolean)),
    };
  }, String(nodeId));
}

/** Read the selected canvas node as the binding-capture path sees it. */
async function readCanvasSelection(page) {
  return page.evaluate(() => {
    const app = window.app || window.__comfymodal_comfy_app;
    const canvas = app && app.canvas;
    const sel = canvas && canvas.selected_nodes;
    const nodes = Array.isArray(sel) ? sel : Object.values(sel || {}).filter(Boolean);
    const node = nodes[0] || null;
    if (!node) return null;
    return { id: String(node.id), type: node.type || "" };
  });
}

test.describe("Studio ZIT E2E", () => {
  test("zit import, wizard setup, preset, playground run, 2x2 experiment, history", async ({ page }) => {
    const zit = JSON.parse(readFileSync(ZIT_ABS, "utf-8"));
    expect(Array.isArray(zit.nodes) && zit.nodes.length > 100).toBe(true);

    const api = await installStudioMockApi(page);
    await pinPrimaryExtensionRequests(page);

    // Workflows stay LIVE: pass /comfymodal/studio/workflows* through to the
    // real backend. Registered AFTER installStudioMockApi so it takes
    // precedence over the shared mock's 599 catch-all (later routes win;
    // route.continue() sends the request to the network, bypassing the mock
    // handler entirely, so these calls are never recorded as unhandled).
    await page.route(/\/comfymodal\/studio\/workflows/, async (route) => {
      await route.continue();
    });

    // Stubbed model library (ZIT models only; workflows/* stays LIVE).
    await page.route("**/comfymodal/studio/models**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", models: ZIT_MODELS }),
      });
    });

    // Stubbed modern experiment engine (mirror studio-experiment.spec.mjs §4).
    let postedExperiment = null;
    const expCells = [0, 1, 2, 3].map((i) => ({
      cell_id: "zit_cell_" + i,
      status: "completed",
      thumb_url: "/comfymodal/assets/zit_cell_" + i,
      workflow_id: "wf_zit",
    }));
    const expItem = {
      experiment_id: "exp_zit_2x2",
      aggregate_status: "completed",
      total: 4,
      counts: { queued: 0, running: 0, completed: 4, failed: 0, canceled: 0, interrupted: 0 },
      cells: expCells,
    };
    await page.route("**/comfymodal/studio/experiment-v2", async (route) => {
      postedExperiment = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", experiment_id: "exp_zit_2x2", item: expItem }),
      });
    });
    await page.route("**/comfymodal/history-v2/experiments/*/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", item: expItem }),
      });
    });

    // Stubbed asset bytes (single-run output + experiment thumbs).
    await page.route("**/comfymodal/assets/*", async (route) => {
      await route.fulfill({ status: 200, contentType: "image/png", body: PNG_1PX });
    });

    // Stubbed History V2 projection for the two stubbed runs (mutable so
    // favorite/note updates are reflected).
    const now = new Date().toISOString();
    const zitState = {
      genFav: false,
      genNote: "",
      expFav: false,
      expNote: "",
    };
    const genItem = () => ({
      id: "gen_zit_single",
      kind: "generation",
      status: "success",
      workflow_id: "wf_zit",
      workflow_name: ZIT_NAME,
      workflow_version: "v1",
      preset_id: "preset_zit",
      preset: "ZIT Base",
      preset_name: "ZIT Base",
      prompt: "zit playground cat",
      negative_prompt: "",
      created_at: now,
      started_at: now,
      completed_at: now,
      duration_ms: 4200,
      favorite: zitState.genFav,
      note: zitState.genNote,
      tags: [],
      models: [{ name: "z_image_turbo_bf16.safetensors" }],
      output_count: 1,
      has_image: true,
      preview_only: false,
      original_available: true,
      featured_output_index: 0,
      outputs: [{ index: 0, output_id: "out_zit_0", thumb_url: "/comfymodal/assets/zit_single", preview_url: "/comfymodal/assets/zit_single", original_url: "/comfymodal/assets/zit_single", status: "success" }],
    });
    const expFeedItem = () => ({
      id: "exp_zit_2x2",
      kind: "experiment",
      status: "completed",
      name: "ZIT seed x prompt",
      workflow: ZIT_NAME,
      preset: "ZIT Base",
      created_at: now,
      started_at: now,
      completed_at: now,
      duration_ms: 9000,
      favorite: zitState.expFav,
      note: zitState.expNote,
      tags: [],
      models: [],
      true_cell_count: 4,
      result_count: 4,
      failed_count: 0,
      interrupted_count: 0,
      axis_labels: { x: "seed", y: "positive_prompt" },
      cells: expCells.slice(0, 4).map((c) => ({ key: c.cell_id, thumb_url: c.thumb_url, status: c.status })),
    });
    await page.route("**/comfymodal/history-v2/feed*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          items: [expFeedItem(), genItem()],
          next_cursor: null,
          limit: 50,
          total: 2,
          has_more: false,
        }),
      });
    });
    await page.route("**/comfymodal/history-v2/generations/gen_zit_single", async (route) => {
      const item = genItem();
      item.attempts = [];
      item.errors = [];
      item.params = { seed: 75739920976641, positive_prompt: "zit playground cat" };
      item.timing = null;
      item.workflow_json = null;
      item.export_state = "none";
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", item }) });
    });
    await page.route("**/comfymodal/history-v2/experiments/exp_zit_2x2", async (route) => {
      const item = expFeedItem();
      item.cells = expCells.map((c, i) => ({
        key: c.cell_id,
        cell_id: c.cell_id,
        status: "completed",
        outputs: [{ index: 0, output_id: "out_zit_cell_" + i, thumb_url: c.thumb_url, preview_url: c.thumb_url, original_url: c.thumb_url, status: "success" }],
        attempts: [],
      }));
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok", item }) });
    });
    await page.route("**/comfymodal/history-v2/generations/*/favorite", async (route) => {
      zitState.genFav = !!route.request().postDataJSON()?.favorite;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/comfymodal/history-v2/generations/*/note", async (route) => {
      zitState.genNote = String(route.request().postDataJSON()?.note || "");
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/comfymodal/history-v2/experiments/*/favorite", async (route) => {
      zitState.expFav = !!route.request().postDataJSON()?.favorite;
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });
    await page.route("**/comfymodal/history-v2/experiments/*/note", async (route) => {
      zitState.expNote = String(route.request().postDataJSON()?.note || "");
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ status: "ok" }) });
    });

    await openStudio(page, COMFYUI_URL);
    await page.locator('.comfymodal-studio-topnav [data-page="workflows"]').click();
    await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 15000 });
    const guard = installConsoleGuard(page);

    // Reuse an existing ZIT workflow on re-runs (import dedupes per
    // workflow, not globally) — keeps the live store to one artifact.
    let sifatida = null;
    try {
      const lib = await page.evaluate(async () => {
        const r = await fetch("/comfymodal/studio/workflows?search=ZIT%20-%20Current%20Favorite");
        return r.json();
      });
      const found = (lib.workflows || []).find((w) => w.name === ZIT_NAME);
      if (found) sifatida = found;
    } catch { /* fall through to import */ }

    let wfId = sifatida ? sifatida.workflow_id : "";
    let verId = "";

    if (!sifatida) {
      // ── 1. Import via file input (absolute ZIT path) ──────────────
      await page.locator('[data-testid="workflows-import-button"]').click();
      await expect(page.locator('[data-testid="import-dialog"]')).toBeVisible({ timeout: 10000 });
      const importRespPromise = page.waitForResponse(
        (resp) => resp.url().includes("/comfymodal/studio/workflows/import") && resp.request().method() === "POST",
        { timeout: 60000 }
      );
      await page.locator('[data-testid="import-file-input"]').setInputFiles(ZIT_ABS);
      const importResp = await importRespPromise;
      expect(importResp.ok()).toBe(true);
      const importBody = await importResp.json();
      expect(importBody.status).toBe("ok");
      wfId = importBody.workflow.workflow_id;
      verId = importBody.version.workflow_version_id;
      console.log("[zit] imported", wfId, verId);

      // ── 2. Wizard opens on the new version ──────────────────────────
      const panel = page.locator(".comfymodal-studio-wizard-panel");
      await expect(panel).toBeVisible({ timeout: 15000 });
      await expect(panel).toContainText("Set up Workflow");
      await expect(panel.locator('[data-testid="wizard-suggest-status"]')).toContainText("stored graph", { timeout: 15000 });

      // Recommender: catalog-covered roles propose concrete stored-graph
      // targets; seed has no KSampler pattern (verified below).
      await panel.locator(".comfymodal-studio-wizard-feature-card").first().click();
      await panel.getByRole("button", { name: "Continue to Bindings" }).click();
      await expect(panel.locator('[data-testid="wizard-required-bindings"]')).toBeVisible({ timeout: 10000 });

      // Rows are keyed by catalog role (data-binding-key); node-type text is
      // not asserted because real graphs carry custom node titles (e.g. ZIT
      // names its CLIPTextEncode nodes "CLIP Text Encode (Positive Prompt)").
      for (const role of ["prompt", "model_unet", "vae", "output"]) {
        const row = panel.locator(`[data-testid="wizard-binding-row"][data-binding-key="${role}"]`);
        await expect(row).toContainText("Suggested", { timeout: 10000 });
        await row.locator('[data-testid="wizard-use-suggestion"]').click();
      }
      // Seed: no catalog suggestion (documents the KSampler-pattern gap).
      const seedRow = panel.locator('[data-testid="wizard-binding-row"][data-binding-key="seed"]');
      await expect(seedRow).toBeVisible({ timeout: 10000 });
      expect(await seedRow.locator('[data-testid="wizard-use-suggestion"]').count()).toBe(0);

      // Load ZIT onto the canvas, then bind seed + clip through capture.
      console.log("[zit] canvas load:", await loadZitOntoCanvas(page, zit));

      async function captureBind(roleKey, nodeId, widgetName) {
        // Keyed by catalog role: text matching is unreliable because real
        // graphs carry custom node titles (ZIT's CLIPLoader is titled
        // "Load CLIP", which also matches the prompt row's bound value).
        const row = panel.locator(`[data-testid="wizard-binding-row"][data-binding-key="${roleKey}"]`);
        await row.click();
        const sel = await selectCanvasNode(page, nodeId);
        console.log("[zit] canvas select", roleKey, JSON.stringify(sel));
        expect(sel).toBeTruthy();
        expect(await readCanvasSelection(page)).toEqual({ id: String(nodeId), type: sel.type });
        await panel.getByRole("button", { name: "Use Selected Node" }).click();
        const dropdown = row.locator("select.comfymodal-studio-select");
        await expect(dropdown).toBeVisible({ timeout: 10000 });
        const options = await dropdown.locator("option").allTextContents();
        console.log("[zit] candidates", roleKey, JSON.stringify(options).slice(0, 400));
        expect(options.some((t) => t.includes(widgetName))).toBe(true);
        await dropdown.selectOption({ label: options.find((t) => t.includes(widgetName)) });
      }

      // Seed lives on ClownsharKSampler_Beta (node 1241 in the ZIT file).
      const samplerNode = zit.nodes.find((n) => n.type === "ClownsharKSampler_Beta");
      expect(samplerNode).toBeTruthy();
      await captureBind("seed", String(samplerNode.id), "seed");
      // CLIP model: CLIPLoader clip_name (the node's widget name).
      const clipNode = zit.nodes.find((n) => n.type === "CLIPLoader");
      expect(clipNode).toBeTruthy();
      await captureBind("clip", String(clipNode.id), "clip_name");

      await expect(panel.locator('[data-testid="wizard-save-gate"]')).toContainText("required bindings complete", { timeout: 10000 });
      // The gate text is substring-loose ("5 of 6 ..." also matches), so
      // assert the button itself is enabled before clicking.
      await expect(panel.getByRole("button", { name: "Continue to Details" })).toBeEnabled({ timeout: 10000 });
      await panel.getByRole("button", { name: "Continue to Details" }).click();
      await expect(panel).toContainText("Confirm Setup");
      const saveBtn = panel.locator('[data-testid="wizard-version-save"]');
      await expect(saveBtn).toBeEnabled({ timeout: 15000 });
      const mappingRespPromise = page.waitForResponse(
        (resp) => resp.url().includes("/mapping") && resp.request().method() === "POST",
        { timeout: 30000 }
      );
      await saveBtn.click();
      const mappingResp = await mappingRespPromise;
      expect(mappingResp.ok()).toBe(true);
      await expect(panel).toContainText("Setup Complete", { timeout: 15000 });
      await panel.locator('[data-testid="wizard-version-done"]').click();

      // Detail: ZIT name, version Ready, run gated on preset only.
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="workflow-detail-name"]')).toHaveText(ZIT_NAME);
      await expect(page.locator('[data-testid="version-item-state"]')).toHaveText("Ready", { timeout: 15000 });
    } else {
      // Re-run with an existing mapped ZIT workflow: open its detail page.
      console.log("[zit] reusing", wfId);
      const card = page.locator('[data-testid="workflow-card"]', { hasText: ZIT_NAME }).first();
      await expect(card).toBeVisible({ timeout: 15000 });
      await card.click();
      await expect(page.locator('[data-testid="workflow-detail"]')).toBeVisible({ timeout: 15000 });
    }

    // ── 3. Preset with required values → run-context Ready ────────────
    const section = page.locator(".comfymodal-studio-section", {
      has: page.locator(".comfymodal-studio-section-title", { hasText: "Presets" }),
    });
    await section.getByRole("button", { name: "New Preset" }).click();
    await expect(page.locator('[data-testid="preset-editor"]')).toBeVisible({ timeout: 10000 });
    const editor = page.locator('[data-testid="preset-editor"]');
    // Wait for the mapping-backed editor (mapping + model library load
    // async; the editor first renders a mapping-less skeleton whose inputs
    // would be discarded by the refresh — never fill before the Values
    // fields and the three model pickers exist). Labels come from the saved
    // mapping display_name ("Prompt"), not the mock's ("Positive Prompt").
    await expect(editor.locator('.comfymodal-studio-backend-field', { hasText: "Prompt" }).first()).toBeVisible({ timeout: 20000 });
    await expect(editor.locator('[data-testid="model-choice-select"]')).toHaveCount(3, { timeout: 20000 });
    await page.locator('[data-testid="preset-name-input"]').fill("ZIT Base");
    // Prompt + seed scalar fields.
    const promptField = editor.locator('.comfymodal-studio-backend-field', { hasText: "Prompt" }).first();
    const ta = promptField.locator("textarea");
    if (await ta.count()) await ta.fill("zit playground cat");
    else await promptField.locator("input").fill("zit playground cat");
    const seedField = editor.locator('.comfymodal-studio-backend-field', { hasText: "Seed" }).first();
    await seedField.locator("input").fill("75739920976641");
    // Model pickers (one per model role): choose the matching ZIT model.
    const modelSelects = editor.locator('[data-testid="model-choice-select"]');
    const selectCount = await modelSelects.count();
    console.log("[zit] model pickers:", selectCount);
    for (let i = 0; i < selectCount; i++) {
      const sel = modelSelects.nth(i);
      const opts = await sel.locator("option").allTextContents();
      const hit = opts.find((t) => t.includes(".safetensors")) || "";
      if (hit) await sel.selectOption({ label: hit });
    }
    const presetRespPromise = page.waitForResponse(
      (resp) => resp.url().includes("/presets") && resp.request().method() === "POST",
      { timeout: 30000 }
    );
    await page.locator('[data-testid="preset-save"]').click();
    const presetResp = await presetRespPromise;
    expect(presetResp.ok()).toBe(true);
    const presetBody = await presetResp.json();
    expect(presetBody.status).toBe("ok");
    const presetId = presetBody.preset.preset_id;
    console.log("[zit] preset", presetId);

    // ── Library shows the ZIT workflow ────────────────────────────────
    // The preset editor lives on the detail page, and the topnav Workflows
    // tab preserves the open detail — go back explicitly to reach the list.
    await page.getByRole("button", { name: "Back to Workflows" }).click();
    await expect(page.locator('[data-testid="workflows-page"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="workflow-card"]', { hasText: ZIT_NAME }).first()).toBeVisible({ timeout: 15000 });

    // ── 4. Playground single run ──────────────────────────────────────
    await page.locator('.comfymodal-studio-topnav [data-page="playground"]').first().click();
    await page.locator('[data-testid="control-panel"]').waitFor({ state: "visible", timeout: 15000 });
    const wfSelect = page.locator('[data-testid="workflow-selector"]');
    await expect(wfSelect.locator(`option[value="${wfId}"]`)).toHaveCount(1, { timeout: 15000 });
    await wfSelect.selectOption(wfId);
    await expect(page.locator('[data-testid="workflow-version-selector"] option')).toHaveCount(2, { timeout: 15000 });
    const presetSelect = page.locator('[data-testid="workflow-preset-selector"]');
    await expect(presetSelect.locator(`option[value="${presetId}"]`)).toHaveCount(1, { timeout: 15000 });
    await presetSelect.selectOption(presetId);
    await expect(page.locator('[data-testid="workflow-run-gating"]')).toContainText("Ready to run", { timeout: 15000 });
    const runBtn = page.locator('[data-testid="run-btn"]');
    await expect(runBtn).toBeEnabled({ timeout: 10000 });
    await runBtn.click();
    // Progress (comfymodal-progress.js) engages, then output completes.
    await expect(page.locator('[data-testid="progress-section"]')).toBeVisible({ timeout: 15000 });
    const canvasOutput = page.locator('[data-testid="canvas-output"]');
    await expect(canvasOutput).toBeVisible({ timeout: 45000 });
    expect(await canvasOutput.getAttribute("src")).toContain("/comfymodal/");
    await expect(runBtn).toBeEnabled({ timeout: 15000 });
    await expect(page.locator('[data-testid="progress-stage"]')).not.toBeEmpty({ timeout: 15000 });

    // ── 5. Seed x prompt 2x2 experiment ───────────────────────────────
    await page.locator('[data-testid="experiment-toggle"]').click();
    await expect(page.locator('[data-testid="shelf-exp-panel"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="shelf-axis-seed"]').click();
    await page.locator('[data-testid="shelf-axis-input-seed"]').fill("75739920970000");
    await page.locator('[data-testid="shelf-axis-input-seed"]').press("Enter");
    await page.locator('[data-testid="shelf-axis-prompt"]').click();
    await page.locator('[data-testid="shelf-axis-input-prompt"]').fill("zit experiment dog");
    await page.locator('[data-testid="shelf-axis-input-prompt"]').press("Enter");
    await expect(page.locator('[data-testid="shelf-exp-matrix"]')).toContainText("4 run(s)", { timeout: 10000 });
    const expRunBtn = page.locator('[data-testid="shelf-exp-run-btn"]');
    await expect(expRunBtn).toBeEnabled({ timeout: 10000 });
    await expRunBtn.click();
    await expect.poll(() => postedExperiment !== null, { timeout: 15000 }).toBe(true);
    expect(postedExperiment.definition.workflows[0].workflow_id).toBe(wfId);
    expect(postedExperiment.definition.axes.seed.values.map(Number).sort((a, b) => a - b).length).toBe(2);
    const grid = page.locator('[data-testid="experiment-v2-grid"]');
    await expect(grid.locator('[data-testid^="experiment-v2-cell-zit_cell_"]')).toHaveCount(4, { timeout: 15000 });
    await expect(page.locator('[data-testid="experiment-v2-progress"]')).toContainText("4/4 complete", { timeout: 15000 });

    // ── 6. History: feed, detail, favorite, note, experiment 2x2 ─────
    await page.locator('.comfymodal-studio-topnav [data-page="history"]').click();
    await expect(page.locator('[data-testid="history-v2-page"]')).toBeVisible({ timeout: 15000 });
    const cards = page.locator('[data-testid="history-v2-generation-card"], [data-testid="history-v2-experiment-card"]');
    await expect(cards).toHaveCount(2, { timeout: 15000 });
    await expect(page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_zit_2x2"]')).toBeVisible();
    await expect(page.locator('[data-testid="history-v2-generation-card"][data-id="gen_zit_single"]')).toBeVisible();

    // Generation detail + favorite + note. The prompt renders on the feed
    // card (established card-prompt contract); the detail dialog shows the
    // canonical 9 params (Seed here) plus run metadata — prompt text is not
    // a params key by contract (pinned 9-param count in sibling specs).
    await expect(page.locator('[data-testid="history-v2-generation-card"][data-id="gen_zit_single"]')).toContainText("zit playground cat");
    await page.locator('[data-testid="history-v2-generation-card"][data-id="gen_zit_single"]').click();
    const dialog = page.getByRole("dialog", { name: "Generation detail" });
    await expect(dialog).toBeVisible({ timeout: 10000 });
    await expect(dialog).toContainText("75739920976641");
    // Favorite star + note box use class hooks (proven pattern in the
    // history-v2 annotation specs); testid variants kept as fallback.
    const favBtn = dialog.locator('.comfymodal-studio-history-v2-fav, [data-testid="history-v2-favorite"], [data-testid="history-favorite"]').first();
    if (await favBtn.count()) await favBtn.click();
    const noteInput = dialog.locator('textarea.comfymodal-studio-history-v2-notes, [data-testid="history-v2-note-input"], [data-testid="history-note-input"], textarea').first();
    if (await noteInput.count()) {
      await noteInput.fill("zit e2e note");
      const noteSave = dialog.getByRole("button", { name: "Save note" });
      if (await noteSave.count()) await noteSave.click();
      else {
        const noteSaveFallback = dialog.locator('[data-testid="history-v2-note-save"], [data-testid="history-note-save"]').first();
        if (await noteSaveFallback.count()) await noteSaveFallback.click();
      }
    }
    await expect.poll(() => zitState.genFav || zitState.genNote !== "", { timeout: 15000 }).toBe(true);
    await page.keyboard.press("Escape");

    // Experiment detail shows the 2x2.
    await page.locator('[data-testid="history-v2-experiment-card"][data-id="exp_zit_2x2"]').click();
    await expect(page.locator('[data-testid="history-v2-experiment-page"], [data-testid="experiment-detail"]')).toBeVisible({ timeout: 15000 });
    expect(await page.locator('[data-testid^="history-v2-cell-"], [data-testid^="experiment-cell-"]').count()).toBeGreaterThanOrEqual(4);

    guard.assertNoErrors(APP_NOISE_PATTERNS);
    api.assertNoUnhandledCalls();

    // Cleanup: delete the preset (workflows have no DELETE route; the ZIT
    // workflow row itself is the intentionally-kept import artifact).
    try {
      await page.evaluate(async (pid) => {
        await fetch(`/comfymodal/studio/workflows/presets/${encodeURIComponent(pid)}`, { method: "DELETE" });
      }, presetId);
    } catch { /* best-effort */ }
  });
});
