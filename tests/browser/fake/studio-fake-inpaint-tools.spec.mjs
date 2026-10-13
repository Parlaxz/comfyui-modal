// Studio inpaint advanced tools (fake backend, bounded).
//
// Proves the new Mask editor controls against the real frontend:
// sub-tools (lasso/rect/object/text), undo/redo history, mask ops
// (grow/shrink/feather/invert/fill-holes), and SAM UI gating.
// SAM network calls are NOT exercised here (no SAM3 in fake backend);
// only the local canvas behavior and UI states are asserted.

import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { setupFakeTest } from "./helpers.mjs";

const SOURCE_FIXTURE = fileURLToPath(new URL("./fixtures/studio-source.png", import.meta.url));

async function selectWorkflow(page, id) {
  await page.locator('[data-testid="workflow-selector"]').selectOption(id);
  await expect(page.locator('[data-testid="workflow-selector"]')).toHaveValue(id, { timeout: 10000 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
}

// Phase-1 shell: modes on the rail, tools in the submenu. Mask lives at
// Edit → Select, Draw at Edit → Sketch.
async function gotoMask(page) {
  await page.locator('[data-testid="studio-tool-edit"]').click();
  await page.locator('[data-testid="studio-subtool-select"]').click();
  await expect(page.locator('[data-testid="inpaint-editor"]')).toBeVisible({ timeout: 10000 });
}

async function gotoSketch(page) {
  await page.locator('[data-testid="studio-tool-edit"]').click();
  await page.locator('[data-testid="studio-subtool-sketch"]').click();
  await expect(page.locator('[data-testid="sketch-editor"]')).toBeVisible({ timeout: 10000 });
}

async function openInpaintWithSource(page) {
  await gotoMask(page);
  await selectWorkflow(page, "wf_inpaint");
  await expect(page.locator('[data-testid="inpaint-editor"]')).toBeVisible({ timeout: 10000 });
  await page.locator('[data-testid="shelf-input-source_image-file"]').setInputFiles(SOURCE_FIXTURE);
  // The uploaded source shows on the MAIN canvas; the paint overlay mounts
  // over it (no separate editor canvas anymore).
  await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="inpaint-canvas"]')).toBeVisible({ timeout: 10000 });
  await expect(page.locator('[data-testid="inpaint-base-image"]')).toBeHidden();
}

async function paintStroke(page, tool) {
  const canvas = page.locator(`[data-testid="${tool}-canvas"]`);
  await expect(canvas).toBeVisible({ timeout: 10000 });
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();
  const x0 = box.x + box.width * 0.3;
  const y0 = box.y + box.height * 0.5;
  await page.mouse.move(x0, y0);
  await page.mouse.down();
  await page.mouse.move(x0 + Math.max(4, box.width * 0.4), y0, { steps: 5 });
  await page.mouse.up();
}

async function canvasAlphaSum(page, tool) {
  return page.evaluate((t) => {
    const c = document.querySelector(`[data-testid="${t}-canvas"]`);
    if (!c || !c.width || !c.height) return -1;
    const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
    let sum = 0;
    for (let i = 3; i < d.length; i += 4) sum += d[i];
    return sum;
  }, tool);
}

test.describe("Studio inpaint advanced tools (fake backend)", () => {
  test("New controls exist and SAM row is hidden until smart mode", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await openInpaintWithSource(page);
      for (const id of ["brush", "erase", "lasso", "rect", "object", "text",
        "undo", "redo", "grow", "shrink", "feather", "invert", "fill-holes",
        "radius", "combine", "clear", "save"]) {
        await expect(page.locator(`[data-testid="inpaint-${id}"]`)).toBeVisible();
      }
      // Phase 2 user-facing language: Object / Detect (SAM3 stays an
      // implementation detail; testids are unchanged).
      await expect(page.locator('[data-testid="inpaint-text"]')).toHaveText("Detect");
      await expect(page.locator('[data-testid="inpaint-rect"]')).toHaveText("Rectangle");
      await expect(page.locator('[data-testid="inpaint-sam-row"]')).toBeHidden();
      await expect(page.locator('[data-testid="inpaint-combine"]')).toHaveValue("add");
      await page.locator('[data-testid="inpaint-text"]').click();
      await expect(page.locator('[data-testid="inpaint-sam-chips"]')).toBeVisible();
      await expect(page.locator('[data-testid="inpaint-sam-chip-person"]')).toBeVisible();
      await expect(page.locator('[data-testid="inpaint-sam-scan"]')).toBeVisible();
      // Overlay lives on the main canvas: the same wrap holds the output
      // image and the paint canvas stacked over it.
      const wrap = page.locator('[data-testid="inpaint-canvas-wrap"]');
      await expect(wrap.locator('[data-testid="canvas-output"]')).toBeVisible();
      await expect(wrap.locator('[data-testid="inpaint-canvas"]')).toBeVisible();
      // Paint mode must not blow up the workspace: the wrap stays within
      // the column and the image height is viewport-capped.
      const cap = await wrap.evaluate((w) => {
        const img = w.querySelector('[data-testid="canvas-output"]');
        return {
          wrapMaxWidth: getComputedStyle(w).maxWidth,
          imgMaxHeight: img ? getComputedStyle(img).maxHeight : "",
        };
      });
      expect(cap.wrapMaxWidth).toBe("100%");
      expect(cap.imgMaxHeight).not.toBe("none");
      await page.locator('[data-testid="inpaint-text"]').click();
      await expect(page.locator('[data-testid="inpaint-sam-row"]')).toBeVisible();
      await expect(page.locator('[data-testid="inpaint-sam-text"]')).toHaveAttribute("placeholder", /person/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Undo/redo round-trips a brush stroke", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await openInpaintWithSource(page);
      await paintStroke(page, "inpaint");
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/has paint/i);
      const painted = await canvasAlphaSum(page, "inpaint");
      expect(painted).toBeGreaterThan(0);
      await page.locator('[data-testid="inpaint-undo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "inpaint"), { timeout: 10000 }).toBe(0);
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Undone/i);
      await page.locator('[data-testid="inpaint-redo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "inpaint"), { timeout: 10000 }).toBe(painted);
      // New edit clears redo: undo, paint again, redo must stay disabled.
      await page.locator('[data-testid="inpaint-undo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "inpaint"), { timeout: 10000 }).toBe(0);
      await paintStroke(page, "inpaint");
      await expect(page.locator('[data-testid="inpaint-redo"]')).toBeDisabled();
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Lasso fills a region and invert reverses it", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await openInpaintWithSource(page);
      await page.locator('[data-testid="inpaint-lasso"]').click();
      const canvas = page.locator('[data-testid="inpaint-canvas"]');
      const box = await canvas.boundingBox();
      expect(box).toBeTruthy();
      const cx = box.x + box.width / 2;
      const cy = box.y + box.height / 2;
      const r = Math.min(box.width, box.height) * 0.15;
      await page.mouse.move(cx + r, cy);
      await page.mouse.down();
      for (let k = 1; k <= 8; k++) {
        const a = (k / 8) * Math.PI * 2;
        await page.mouse.move(cx + Math.cos(a) * r, cy + Math.sin(a) * r, { steps: 2 });
      }
      await page.mouse.up();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Shape added/i);
      const before = await canvasAlphaSum(page, "inpaint");
      expect(before).toBeGreaterThan(0);
      await page.locator('[data-testid="inpaint-invert"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Inverted/i);
      const after = await canvasAlphaSum(page, "inpaint");
      expect(after).toBeGreaterThan(before);
      // Undo restores the pre-invert mask exactly.
      await page.locator('[data-testid="inpaint-undo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "inpaint"), { timeout: 10000 }).toBe(before);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Grow expands, shrink contracts, save still works", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await openInpaintWithSource(page);
      // Fixture canvas is tiny (16px), so shrink the brush: a full-canvas
      // stroke cannot grow further.
      await page.locator('[data-testid="inpaint-brush-size"]').fill("4");
      await page.locator('[data-testid="inpaint-radius"]').fill("2");
      await paintStroke(page, "inpaint");
      const base = await canvasAlphaSum(page, "inpaint");
      expect(base).toBeGreaterThan(0);
      await page.locator('[data-testid="inpaint-grow"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Grown/i);
      const grown = await canvasAlphaSum(page, "inpaint");
      expect(grown).toBeGreaterThan(base);
      await page.locator('[data-testid="inpaint-shrink"]').click();
      const shrunk = await canvasAlphaSum(page, "inpaint");
      expect(shrunk).toBeLessThan(grown);
      await page.locator('[data-testid="inpaint-save"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Mask saved:/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Sketch paints on the main canvas too", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await gotoSketch(page);
      await selectWorkflow(page, "wf_sketch");
      await page.locator('[data-testid="shelf-input-source_image-file"]').setInputFiles(SOURCE_FIXTURE);
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
      const wrap = page.locator('[data-testid="sketch-canvas-wrap"]');
      await expect(wrap.locator('[data-testid="canvas-output"]')).toBeVisible();
      await expect(wrap.locator('[data-testid="sketch-canvas"]')).toBeVisible();
      await expect(page.locator('[data-testid="sketch-base-image"]')).toBeHidden();
      await expect(page.locator('[data-testid="sketch-undo"]')).toBeVisible();
      await paintStroke(page, "sketch");
      await page.locator('[data-testid="sketch-undo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "sketch"), { timeout: 10000 }).toBe(0);
      await paintStroke(page, "sketch");
      await page.locator('[data-testid="sketch-save"]').click();
      await expect(page.locator('[data-testid="sketch-mask-preview"]')).toContainText(/Sketch saved as Source Image:/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Scan list renders and Apply refines boxes in one undo step", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await gotoMask(page);
      await selectWorkflow(page, "wf_inpaint");
      await page.locator('[data-testid="shelf-input-source_image-file"]').setInputFiles(SOURCE_FIXTURE);
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
      await page.waitForTimeout(1200);
      await page.locator('[data-testid="inpaint-text"]').click();
      const scanItems = [
        { label: "person", confidence: 0.85, box: { x: 1, y: 1, w: 1, h: 1 }, thumb_png: null },
        { label: "car", confidence: 0.5, box: { x: 2, y: 2, w: 2, h: 2 }, thumb_png: null },
      ];
      await page.route("**/comfymodal/studio/sam3/scan-yolo", async (route) => {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, width: 16, height: 16, items: scanItems }) });
      });
      await page.locator('[data-testid="inpaint-sam-scan"]').click();
      await expect(page.locator('[data-testid="inpaint-sam-item-0"]')).toContainText(/person.*85%/i);
      await expect(page.locator('[data-testid="inpaint-sam-item-1"]')).toContainText(/car.*50%/i);
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/2 items found/i);
      // Uncheck the second box: only the first reaches the refine call.
      await page.locator('[data-testid="inpaint-sam-check-1"]').click();
      let boxesBody = null;
      await page.route("**/comfymodal/studio/sam3/boxes", async (route) => {
        boxesBody = route.request().postDataJSON();
        const empty = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, width: 16, height: 16, mask_png: empty }) });
      });
      await page.locator('[data-testid="inpaint-sam-apply"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/1 item applied/i);
      expect(boxesBody).toBeTruthy();
      expect(boxesBody.boxes).toHaveLength(1);
      expect(boxesBody.boxes[0].x).toBe(1);
      expect(String(boxesBody.image_b64 || "")).toMatch(/^data:image\//);
      // One undo step removes the whole apply.
      await page.locator('[data-testid="inpaint-undo"]').click();
      await expect.poll(() => canvasAlphaSum(page, "inpaint"), { timeout: 10000 }).toBe(0);
      await page.unroute("**/comfymodal/studio/sam3/scan-yolo");
      await page.unroute("**/comfymodal/studio/sam3/boxes");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("SAM UI gates: no source, empty text", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await gotoMask(page);
      await selectWorkflow(page, "wf_inpaint");
      // Object click with no source uploaded.
      await page.locator('[data-testid="inpaint-object"]').click();
      const canvas = page.locator('[data-testid="inpaint-canvas"]');
      await expect(canvas).toBeVisible({ timeout: 10000 });
      const box = await canvas.boundingBox();
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Upload a Source Image first/i);
      // Text find with empty query (upload first: a shelf commit can
      // remount the editor and reset the mode).
      await page.locator('[data-testid="shelf-input-source_image-file"]').setInputFiles(SOURCE_FIXTURE);
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
      // The upload commit schedules a shelf refresh; let it settle so the
      // editor we drive is the mounted one.
      await page.waitForTimeout(1200);
      await page.locator('[data-testid="inpaint-text"]').click();
      await expect(page.locator('[data-testid="inpaint-sam-row"]')).toBeVisible();
      await page.locator('[data-testid="inpaint-sam-find"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Type what to select first/i);
      // With a query, Find posts the canvas pixels (not a filename ref)
      // and reports a human message with a restart hint, never a raw
      // JSON.parse error.
      let samBody = null;
      await page.route("**/comfymodal/studio/sam3/text", async (route) => {
        samBody = route.request().postDataJSON();
        await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      });
      await page.locator('[data-testid="inpaint-sam-text"]').fill("person");
      await page.locator('[data-testid="inpaint-sam-find"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Detect failed.*restart ComfyUI/i);
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).not.toContainText(/JSON\.parse/i);
      expect(samBody).toBeTruthy();
      expect(String(samBody.image_b64 || "")).toMatch(/^data:image\//);
      expect(samBody.filename).toBeUndefined();
      await page.unroute("**/comfymodal/studio/sam3/text");
      // Chips fill the query and run Find (fake backend 404s, proving the call).
      await page.locator('[data-testid="inpaint-sam-chip-face"]').click();
      await expect(page.locator('[data-testid="inpaint-sam-text"]')).toHaveValue("face");
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Detect failed.*restart ComfyUI/i);
      // Scan posts the canvas pixels for YOLO proposing; the fake
      // backend 404s, proving the call.
      let scanBody = null;
      await page.route("**/comfymodal/studio/sam3/scan-yolo", async (route) => {
        scanBody = route.request().postDataJSON();
        await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
      });
      await page.locator('[data-testid="inpaint-sam-scan"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Scan failed.*restart ComfyUI/i);
      expect(scanBody).toBeTruthy();
      expect(String(scanBody.image_b64 || "")).toMatch(/^data:image\//);
      await page.unroute("**/comfymodal/studio/sam3/scan-yolo");
      // The failed fetch logs a 404 resource error; the SAM route does not
      // exist on the fake backend by design.
      await fx.assertNoConsoleErrors([/404/]);
    } finally {}
  });

  test("source Clear wipes paint and history (Undo cannot resurrect)", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await openInpaintWithSource(page);
      await paintStroke(page, "inpaint");
      expect(await canvasAlphaSum(page, "inpaint")).toBeGreaterThan(0);
      await page.locator('[data-testid="shelf-input-source_image-clear"]').click();
      await expect(page.locator('[data-testid="shelf-input-source_image-empty"]')).toBeVisible({ timeout: 10000 });
      expect(await canvasAlphaSum(page, "inpaint")).toBe(0);
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Mask cleared/i);
      // History belonged to the removed source: Undo must stay a no-op.
      await page.locator('[data-testid="inpaint-undo"]').click();
      expect(await canvasAlphaSum(page, "inpaint")).toBe(0);
      await expect(page.locator('[data-testid="inpaint-undo"]')).toBeDisabled();
      await fx.assertNoConsoleErrors();
    } finally {}
  });
});
