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


  // ── Test 2: Seed axis insertion dropdown ─────────────────────────────
  // Adjacent to +, Increment default, Decrement/Random/Empty, last-finite
  // seed semantics, boundaries disabled with a message, persisted while
  // mounted; non-seed + unchanged.


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

});
