// Modal Studio — Focused feature checks against the PRIMARY copy
//
// The running ComfyUI server also loads sibling plugin copies (agent/dc8
// lanes) whose launchers shadow the primary.  To validate THIS repo's code
// deterministically, these tests mount the studio shell and/or shared UI
// components directly from /extensions/comfyui-modal/* (the primary copy).
//
// Mock is installed BEFORE navigation per isolation contract.

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  createOwnerPrefix,
  createOwnedRecords,
} from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// The shared ComfyUI server also hosts sibling plugin lanes (agent/dc8
// copies) whose duplicate extension registrations and unrelated asset
// 404s produce console.error noise during app startup.  These patterns
// are app-level and unrelated to the pipeline under test; uncaught
// pageerrors are still always reported.
const APP_NOISE_PATTERNS = [
  "already registered",        // sibling lanes re-register extension names
  "vite:preloadError",         // ComfyUI app preload failures
  "Failed to load resource",   // app-internal 404s (/lm/settings, pysssss)
  "ComfyApp graph accessed",   // app startup before a graph is loaded
];

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitVisible(locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

async function selectBackendPreset(page, presetLabel) {
  const select = page.locator('[data-testid="backend-select"]');
  await select.waitFor({ state: "visible", timeout: 15000 });
  await select.selectOption(presetLabel);
  await page.waitForTimeout(300);
}

/** Mount the studio shell from the primary extension copy. */
async function mountPrimaryStudio(page) {
  const ok = await page.evaluate(async () => {
    try {
      const shellMod = await import("/extensions/comfyui-modal/studio-shell.js");
      const stylesMod = await import("/extensions/comfyui-modal/studio-styles.js");
      if (stylesMod.ensureStudioStyles) stylesMod.ensureStudioStyles();
      const host = document.createElement("div");
      host.id = "studio-focused-host";
      host.style.cssText = "position:fixed;inset:0;z-index:99999;background:#0d0d0f;overflow:auto;";
      document.body.appendChild(host);
      window.__studioFocusedShell = shellMod.mountStudioShell(host, { apiBase: "/comfymodal" });
      return true;
    } catch (err) {
      window.__studioMountError = String(err && err.stack ? err.stack : err);
      return false;
    }
  });
  expect(ok, await page.evaluate(() => window.__studioMountError || "")).toBe(true);
  await waitVisible(page.locator('[data-testid="control-panel"]'));
}

/** Import a shared UI component from the primary copy and build a preview overlay. */
async function buildPreviewOverlay(page, opts) {
  const payload = {
    imageUrl: opts.imageUrl || null,
    alt: opts.alt || "preview",
    sideColumnText: opts.sideColumnText || null,
    saveBehavior: opts.saveBehavior || "resolve", // resolve | reject | none
    saveErrorMessage: opts.saveErrorMessage || "Save failed",
  };
  return page.evaluate(async (p) => {
    const { createImagePreviewOverlay } = await import("/extensions/comfyui-modal/studio-ui.js");
    const host = document.createElement("div");
    host.id = "preview-host";
    host.style.cssText = "position:fixed;inset:0;z-index:100000;";
    document.body.appendChild(host);

    const overlayOpts = {
      imageUrl: p.imageUrl,
      alt: p.alt,
      onClose: () => {},
    };
    if (p.sideColumnText) {
      const col = document.createElement("div");
      col.className = "comfymodal-studio-experiment-grid-detail-axes";
      col.textContent = p.sideColumnText;
      overlayOpts.sideColumn = col;
    }
    if (p.saveBehavior !== "none") {
      overlayOpts.saveOutput = {
        saved: false,
        errorMessage: p.saveErrorMessage,
        onSave: async () => {
          if (p.saveBehavior === "reject") throw new Error("disk full");
          return true;
        },
      };
    }
    const overlay = createImagePreviewOverlay(overlayOpts);
    host.appendChild(overlay.overlay);
    window.__previewHost = host;
    window.__previewOverlay = overlay;
    return true;
  }, payload);
}

/** Create a snapshot + preset with explicit bindings and defaults. */
async function createSnapshotAndPreset(page, owned, opts) {
  const snapPayload = {
    name: opts.name,
    compatibleFeatures: ["txt2img"],
    graphJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "test" } } },
    apiPromptJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "" } } },
    nodeBindings: opts.bindings,
    outputNodeId: "1",
    source: "manual",
  };
  const snapResult = await page.evaluate(async (p) => {
    const res = await fetch("/comfymodal/studio/snapshots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    });
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const data = await res.json();
    return data.snapshot || data;
  }, snapPayload);
  expect(snapResult.error).toBeFalsy();
  expect(snapResult.id).toBeTruthy();
  owned.snapshotIds.push(snapResult.id);

  const presResult = await page.evaluate(async (p) => {
    const res = await fetch("/comfymodal/studio/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(p),
    });
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const data = await res.json();
    return data.preset || data;
  }, {
    label: opts.presetLabel,
    snapshotId: snapResult.id,
    compatibleFeatures: ["txt2img"],
    defaults: opts.defaults,
  });
  expect(presResult.error).toBeFalsy();
  expect(presResult.id).toBeTruthy();
  owned.presetIds.push(presResult.id);
  return presResult.id;
}

const WIDGET_BINDINGS = {
  prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
  seed: { kind: "widget", nodeId: "1", widgetName: "seed" },
  steps: { kind: "widget", nodeId: "1", widgetName: "steps" },
};

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Studio focused features (primary copy)", () => {
  let api;

  test.beforeEach(async ({ page }) => {
    api = await installStudioMockApi(page, { terminalPoll: 2 });
  });

  // ── Test 1: Steps recommendation ─────────────────────────────────────
  // Preset-backed, available before runs, updates on selection changes,
  // same action for the Steps axis, no hard-coded quick values, and
  // trustworthy hide/disable.

  test("1. steps recommendation is preset-backed, shared with the axis, hides/disables truthfully", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      const preset24 = await createSnapshotAndPreset(page, owned, {
        name: prefix + "-snap-a", presetLabel: prefix + "-preset-a",
        bindings: WIDGET_BINDINGS, defaults: { seed: 1, steps: 24 },
      });
      await createSnapshotAndPreset(page, owned, {
        name: prefix + "-snap-b", presetLabel: prefix + "-preset-b",
        bindings: WIDGET_BINDINGS, defaults: { seed: 2, steps: 30 },
      });
      await createSnapshotAndPreset(page, owned, {
        name: prefix + "-snap-d", presetLabel: prefix + "-preset-d",
        bindings: WIDGET_BINDINGS, defaults: { seed: 3 },
      });

      await mountPrimaryStudio(page);
      guard = installConsoleGuard(page);

      // Select preset with steps default 24 — recommendation visible BEFORE any run
      await selectBackendPreset(page, preset24);
      await waitVisible(page.locator('[data-testid="input-steps"]'));
      // Re-render (via the active feature tab) so hydration picks up the
      // preset default; then the recommendation equals the current value.
      await page.locator('[data-testid="feature-tab-txt2img"]').click();
      await page.waitForTimeout(500);
      await expect(page.locator('[data-testid="input-steps"]')).toHaveValue("24", { timeout: 5000 });
      const mainRec = page.locator('[data-testid="steps-recommended-btn"]');
      await expect(mainRec).toBeVisible({ timeout: 5000 });
      await expect(mainRec).toHaveText("Use recommended (24)");

      // Current value already equals the recommendation -> disabled truthfully
      await expect(mainRec).toBeDisabled();

      // No hard-coded quick-value chips (exact text 10/20/30/50)
      const exactQuick = page.locator('button:has-text("10"), button:has-text("30"), button:has-text("50")');
      const quickTexts = await exactQuick.allTextContents();
      expect(quickTexts.filter((t) => /^(10|20|30|50)$/.test(t.trim()))).toHaveLength(0);

      // Same action for the Steps axis
      await page.locator('[data-testid="experiment-toggle"]').click();
      await waitVisible(page.locator('[data-testid="experiment-mode"]'));
      const axisCb = page.locator('[data-axis="steps"]');
      await axisCb.check();
      await waitVisible(page.locator('[data-testid="axis-editor-steps"]'));
      const axisRec = page.locator('[data-testid="axis-steps-recommended-btn"]');
      await expect(axisRec).toBeVisible({ timeout: 5000 });
      await expect(axisRec).toHaveText("Use recommended (24)");
      // Steps axis default value is 24 -> applying would be a no-op -> disabled
      await expect(axisRec).toBeDisabled();
      await expect(page.locator('[data-testid="steps-recommended-note"]')).toContainText("Already applied");

      // The main control hides its own button while the steps axis owns the action
      await expect(page.locator('[data-testid="steps-recommended-btn"]')).toHaveCount(0);

      // No hard-coded quick chips inside the steps axis editor either
      const editorQuick = page.locator('[data-testid="axis-editor-steps"] button');
      const editorTexts = await editorQuick.allTextContents();
      expect(editorTexts.filter((t) => /^(10|20|30|50)$/.test(t.trim()))).toHaveLength(0);

      // Updating on selection changes: switch to the preset with steps default 30
      await selectBackendPreset(page, owned.presetIds[1]);
      await expect(page.locator('[data-testid="axis-steps-recommended-btn"]')).toHaveText("Use recommended (30)", { timeout: 5000 });

      // Trustworthy hide: preset without a workflow steps default shows no action
      await selectBackendPreset(page, owned.presetIds[2]);
      await expect(page.locator('[data-testid="steps-recommended-btn"]')).toHaveCount(0, { timeout: 5000 });
      await expect(page.locator('[data-testid="axis-steps-recommended-btn"]')).toHaveCount(0);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: Seed axis insertion dropdown ─────────────────────────────
  // Adjacent to +, Increment default, Decrement/Random/Empty, last-finite
  // seed semantics, boundaries disabled with a message, persisted while
  // mounted; non-seed + unchanged.

  test("2. seed axis insertion dropdown: modes, last-finite semantics, boundaries, persistence", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      const presetId = await createSnapshotAndPreset(page, owned, {
        name: prefix + "-snap-seed", presetLabel: prefix + "-preset-seed",
        bindings: WIDGET_BINDINGS, defaults: { seed: 100, steps: 20 },
      });

      await mountPrimaryStudio(page);
      guard = installConsoleGuard(page);

      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-seed"]'));

      await page.locator('[data-testid="experiment-toggle"]').click();
      await waitVisible(page.locator('[data-testid="experiment-mode"]'));
      const seedAxisCb = page.locator('[data-axis="seed"]');
      await seedAxisCb.check();
      await waitVisible(page.locator('[data-testid="axis-editor-seed"]'));

      // Dropdown adjacent to + with the four modes, Increment default
      const modeSelect = page.locator('[data-testid="seed-insert-mode"]');
      await expect(modeSelect).toBeVisible({ timeout: 5000 });
      const options = await modeSelect.locator("option").allTextContents();
      expect(options).toEqual(["Increment", "Decrement", "Random", "Empty"]);
      await expect(modeSelect).toHaveValue("increment");

      // Axis starts with the preset seed default [100]
      const seedInput0 = page.locator('[data-testid="axis-value-seed-0"]');
      await expect(seedInput0).toHaveValue("100");

      // Increment: appends last finite seed + 1 (100 -> 101)
      await page.locator('[data-testid="axis-add-value-seed"]').click();
      await expect(page.locator('[data-testid="axis-value-seed-1"]')).toHaveValue("101", { timeout: 5000 });

      // Persisted while mounted: mode stays increment after the re-render
      await expect(modeSelect).toHaveValue("increment");

      // Last-finite semantics: [100, 50] -> decrement appends 49 (not 99)
      await page.locator('[data-testid="axis-value-seed-1"]').fill("50");
      await modeSelect.selectOption("decrement");
      await page.locator('[data-testid="axis-add-value-seed"]').click();
      await expect(page.locator('[data-testid="axis-value-seed-2"]')).toHaveValue("49", { timeout: 5000 });
      // Mode persisted across the value-list rebuild
      await expect(modeSelect).toHaveValue("decrement");

      // Random: appends a numeric seed in [0, max]
      await modeSelect.selectOption("random");
      await page.locator('[data-testid="axis-add-value-seed"]').click();
      const rndVal = await page.locator('[data-testid="axis-value-seed-3"]').inputValue();
      const rndNum = Number(rndVal);
      expect(Number.isInteger(rndNum)).toBe(true);
      expect(rndNum).toBeGreaterThanOrEqual(0);
      expect(rndNum).toBeLessThanOrEqual(2147483647);

      // Empty: appends a blank value
      await modeSelect.selectOption("empty");
      await page.locator('[data-testid="axis-add-value-seed"]').click();
      await expect(page.locator('[data-testid="axis-value-seed-4"]')).toHaveValue("", { timeout: 5000 });

      // Boundaries: single max value -> increment disabled with message
      for (let i = 4; i >= 1; i--) {
        await page.locator(`[data-testid="axis-remove-value-seed-${i}"]`).click();
      }
      await seedInput0.fill("2147483647");
      await modeSelect.selectOption("increment");
      await expect(page.locator('[data-testid="seed-insert-boundary"]')).toContainText("Maximum seed reached", { timeout: 5000 });
      await expect(page.locator('[data-testid="axis-add-value-seed"]')).toBeDisabled();

      // Switching to decrement clears the boundary and enables the add
      await modeSelect.selectOption("decrement");
      await expect(page.locator('[data-testid="axis-add-value-seed"]')).toBeEnabled({ timeout: 5000 });
      await page.locator('[data-testid="axis-add-value-seed"]').click();
      await expect(page.locator('[data-testid="axis-value-seed-1"]')).toHaveValue("2147483646", { timeout: 5000 });

      // Decrement floor: seed 0 -> decrement disabled with message
      await page.locator('[data-testid="axis-remove-value-seed-1"]').click();
      await seedInput0.fill("0");
      await modeSelect.selectOption("decrement");
      await expect(page.locator('[data-testid="seed-insert-boundary"]')).toContainText("Minimum finite seed reached", { timeout: 5000 });
      await expect(page.locator('[data-testid="axis-add-value-seed"]')).toBeDisabled();
      await modeSelect.selectOption("increment");
      await expect(page.locator('[data-testid="axis-add-value-seed"]')).toBeEnabled({ timeout: 5000 });

      // Non-seed + unchanged: steps axis editor has no dropdown and its +
      // still appends a blank value
      await page.locator('[data-axis="steps"]').check();
      await waitVisible(page.locator('[data-testid="axis-editor-steps"]'));
      await expect(page.locator('[data-testid="axis-editor-steps"] [data-testid="seed-insert-mode"]')).toHaveCount(0);
      const stepsBefore = await page.locator('[data-testid^="axis-value-steps-"]').count();
      await page.locator('[data-testid="axis-add-value-steps"]').click();
      await expect(page.locator('[data-testid^="axis-value-steps-"]')).toHaveCount(stepsBefore + 1, { timeout: 5000 });
      const lastStepsVal = await page.locator('[data-testid^="axis-value-steps-"]').last().inputValue();
      expect(lastStepsVal).toBe("");

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 3: Shared preview pan/zoom + toolbar layout ─────────────────
  // Pointer pan (grab/grabbing), pointer-centered wheel zoom with scroll
  // prevention only over the viewer, reset rules and keyboard layering,
  // toolbar below the image with save-before-fullscreen ordering, no
  // transient status text, right-side axis column without shifting the
  // centered image.

  test("3. preview overlay: pan/zoom, toolbar below image, save/fullscreen ordering, side column", async ({ page }) => {
    let guard;
    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await waitVisible(page.locator("body"));
      // Let the ComfyUI app settle so startup noise is not attributed to the
      // pipeline under test (mirrors openStudio-then-guard ordering).
      await page.waitForTimeout(2500);
      guard = installConsoleGuard(page);

      await buildPreviewOverlay(page, {
        imageUrl: "/comfymodal/studio/outputs/focused.png",
        alt: "focused preview",
        saveBehavior: "resolve",
        sideColumnText: "Axis values column",
      });

      // Toolbar below the image (zoom controls come after the image container)
      const imgContainer = page.locator(".comfymodal-studio-zoom-image-container");
      const controls = page.locator(".comfymodal-studio-zoom-controls");
      await expect(imgContainer).toBeVisible({ timeout: 5000 });
      await expect(controls).toBeVisible();
      const imgIdx = await page.evaluate(() => {
        const parent = document.querySelector(".comfymodal-studio-zoom-wrap");
        const kids = Array.from(parent.children);
        return {
          imgIdx: kids.indexOf(parent.querySelector(".comfymodal-studio-zoom-image-container")),
          controlsIdx: kids.indexOf(parent.querySelector(".comfymodal-studio-zoom-controls")),
        };
      });
      expect(imgIdx.imgIdx).toBeLessThan(imgIdx.controlsIdx);

      // Save comes BEFORE fullscreen in the toolbar row; close is first
      const toolbarOrder = await page.evaluate(() => {
        const row = document.querySelector(".comfymodal-studio-zoom-controls");
        return Array.from(row.children).map((c) => c.getAttribute("data-testid") || c.className);
      });
      const saveIdx = toolbarOrder.findIndex((t) => t === "save-output-btn");
      const fsIdx = toolbarOrder.findIndex((t) => t === "zoom-fullscreen");
      const closeIdx = toolbarOrder.findIndex((t) => t.includes("preview-overlay-close"));
      expect(saveIdx).toBeGreaterThan(-1);
      expect(closeIdx).toBeGreaterThan(-1);
      expect(fsIdx).toBeGreaterThan(-1);
      expect(closeIdx).toBeLessThan(saveIdx);
      expect(saveIdx).toBeLessThan(fsIdx);

      // No transient status text nodes in the toolbar (only buttons + label)
      const toolbarText = await page.evaluate(() => {
        const row = document.querySelector(".comfymodal-studio-zoom-controls");
        return Array.from(row.children).filter((c) => c.tagName !== "BUTTON" && c.tagName !== "SPAN");
      });
      expect(toolbarText).toHaveLength(0);

      // Zoom in -> label shows percentage
      const zoomLabel = page.locator('[data-testid="zoom-label"]');
      await expect(zoomLabel).toHaveText("Fit");
      await page.locator('[data-testid="zoom-in"]').click();
      await expect(zoomLabel).toHaveText("125%");

      // Pointer-centered wheel zoom over the viewer (scroll prevented, label changes)
      const viewer = page.locator(".comfymodal-studio-zoom-image-container");
      const box = await viewer.boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.wheel(0, -100);
      const afterWheel = (await zoomLabel.textContent()).trim();
      expect(afterWheel).not.toBe("Fit");
      expect(afterWheel.endsWith("%")).toBe(true);

      // Pointer drag pans (transform gains a translate)
      const transformBefore = await page.evaluate(() => {
        return document.querySelector(".comfymodal-studio-zoom-image-container img").style.transform;
      });
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 30, { steps: 5 });
      await page.mouse.up();
      const transformAfter = await page.evaluate(() => {
        return document.querySelector(".comfymodal-studio-zoom-image-container img").style.transform;
      });
      expect(transformAfter).toContain("translate(");
      expect(transformAfter).not.toBe(transformBefore);

      // Escape resets to fit (reset rules + keyboard layering preserved)
      await page.keyboard.press("Escape");
      await expect(zoomLabel).toHaveText("Fit");

      // Numpad zoom keys still work (keyboard layering)
      await page.keyboard.press("NumpadAdd");
      await expect(zoomLabel).toHaveText("125%");
      await page.keyboard.press("NumpadSubtract");
      await expect(zoomLabel).toHaveText("Fit");

      // Right-side vertical axis column does not shift the centered image
      const sideColStyle = await page.evaluate(() => {
        const col = document.querySelector(".comfymodal-studio-experiment-grid-detail-axes");
        const wrap = document.querySelector(".comfymodal-studio-zoom-wrap");
        const content = document.querySelector(".comfymodal-studio-preview-overlay-content");
        return {
          position: col && getComputedStyle(col).position,
          right: col && getComputedStyle(col).right,
          isChildOfContent: content.contains(col),
          wrapIsSiblingOfCol: wrap && col ? wrap.parentElement === content : null,
        };
      });
      expect(sideColStyle.position).toBe("absolute");
      expect(sideColStyle.right).toBe("0px");
      expect(sideColStyle.isChildOfContent).toBe(true);

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 4: Save output button (component) ───────────────────────────
  // Success hides the button; failure shows an error and keeps the button.

  test("4. save output button: success hides, failure surfaces error", async ({ page }) => {
    let guard;
    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await waitVisible(page.locator("body"));
      await page.waitForTimeout(2500);
      guard = installConsoleGuard(page);

      // Success path
      await buildPreviewOverlay(page, {
        imageUrl: "/comfymodal/studio/outputs/focused-save.png",
        alt: "save preview",
        saveBehavior: "resolve",
      });
      const saveBtn = page.locator('[data-testid="save-output-btn"]');
      await expect(saveBtn).toBeVisible({ timeout: 5000 });
      await saveBtn.click();
      // Success hides the button (record saved)
      await expect(saveBtn).toBeHidden({ timeout: 5000 });
      await page.evaluate(() => { if (window.__previewOverlay) window.__previewOverlay.close(); });

      // Failure path
      await buildPreviewOverlay(page, {
        imageUrl: "/comfymodal/studio/outputs/focused-save-fail.png",
        alt: "save preview fail",
        saveBehavior: "reject",
        saveErrorMessage: "Save failed",
      });
      const saveBtn2 = page.locator('[data-testid="save-output-btn"]');
      await expect(saveBtn2).toBeVisible({ timeout: 5000 });
      await saveBtn2.click();
      await expect(page.locator('[data-testid="save-output-error"]')).toContainText("Save failed: disk full", { timeout: 5000 });
      await expect(saveBtn2).toBeVisible();
      await expect(saveBtn2).toBeEnabled();

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 5: Save output (history flow) ───────────────────────────────
  // Button visibility from record saved state; request targets only the
  // selected output (output_index); success updates the record; failure
  // shows an error and keeps the button.

  test("5. history preview save: visibility from saved state, selected-output-only request, failure behavior", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      const presetId = await createSnapshotAndPreset(page, owned, {
        name: prefix + "-snap-save", presetLabel: prefix + "-preset-save",
        bindings: WIDGET_BINDINGS, defaults: { seed: 1, steps: 20 },
      });

      await mountPrimaryStudio(page);
      guard = installConsoleGuard(page);

      // Run once so the mock has a completed record with an output
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("save flow cat");
      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 30000 });

      // Navigate to History and open the run's preview
      await page.locator('[data-page="history"]').click();
      await waitVisible(page.locator('[data-testid="history-gallery"]'));
      const card = page.locator(".comfymodal-studio-history-card").first();
      await card.waitFor({ state: "visible", timeout: 15000 });
      await card.click();

      // Unsaved record -> Save button visible; save requests the selected output only
      const saveBtn = page.locator('[data-testid="save-output-btn"]');
      await expect(saveBtn).toBeVisible({ timeout: 5000 });
      await saveBtn.click();

      // Assert the request targeted only the selected output
      expect(api.state.saveRequests.length).toBeGreaterThan(0);
      expect(api.state.saveRequests[api.state.saveRequests.length - 1].output_index).toBe(0);

      // Success -> button disappears (record now saved)
      await expect(page.locator('[data-testid="save-output-btn"]')).toHaveCount(0, { timeout: 5000 });
      await page.keyboard.press("Escape");

      // Failure path with a second, unsaved record
      await page.locator('[data-page="playground"]').click();
      await waitVisible(page.locator('[data-testid="run-btn"]'));
      await page.locator('[data-testid="input-prompt"]').fill("save flow cat 2");
      await runBtn.click();
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 30000 });
      await page.locator('[data-page="history"]').click();
      await waitVisible(page.locator('[data-testid="history-gallery"]'));
      const card2 = page.locator(".comfymodal-studio-history-card").first();
      await card2.waitFor({ state: "visible", timeout: 15000 });
      await card2.click();

      api.failNext("POST", "/save", 500, { status: "error", message: "disk full" });
      const saveBtn2 = page.locator('[data-testid="save-output-btn"]');
      await expect(saveBtn2).toBeVisible({ timeout: 5000 });
      await saveBtn2.click();
      await expect(page.locator('[data-testid="save-output-error"]')).toContainText("Save failed", { timeout: 5000 });
      await expect(saveBtn2).toBeVisible();
      await expect(saveBtn2).toBeEnabled();
      await page.keyboard.press("Escape");

      // A pre-saved record shows NO save button (visibility from saved state)
      // Mark the newest (currently unsaved) record saved via a direct call.
      const newestRunId = api.state.history[0].run_id;
      await page.evaluate(async (runId) => {
        await fetch(`/comfymodal/run-history/${encodeURIComponent(runId)}/save`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ output_index: 0 }),
        });
      }, newestRunId);
      await page.locator('[data-page="playground"]').click();
      await waitVisible(page.locator('[data-testid="run-btn"]'));
      await page.locator('[data-page="history"]').click();
      await waitVisible(page.locator('[data-testid="history-gallery"]'));
      const card3 = page.locator(".comfymodal-studio-history-card").first();
      await card3.waitFor({ state: "visible", timeout: 15000 });
      await card3.click();
      await expect(page.locator('[data-testid="save-output-btn"]')).toHaveCount(0, { timeout: 5000 });

      guard.assertNoErrors(APP_NOISE_PATTERNS);
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });
});
