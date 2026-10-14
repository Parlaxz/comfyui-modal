// Studio image-workspace tools (fake backend, bounded).
//
// Proves the tool-based Playground extension against the real frontend:
// one workspace, five tool buttons, type-filtered workflows, Tool Inputs
// shelf, current-image chaining, paint/outpaint editors, and structured
// prompt authoring. No live ComfyUI needed.

import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { setupFakeTest } from "./helpers.mjs";

const WF = '[data-testid="workflow-selector"]';
const RUN = '[data-testid="run-btn"]';
const STRIP = '[data-testid="studio-tool-strip"]';
const SOURCE_FIXTURE = fileURLToPath(new URL("./fixtures/studio-source.png", import.meta.url));

async function selectWorkflow(page, id) {
  await page.locator(WF).selectOption(id);
  await expect(page.locator(WF)).toHaveValue(id, { timeout: 10000 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
}

async function fillPrompt(page, text) {
  const box = page.locator('[data-testid="shelf-input-prompt"]');
  await expect(box).toBeVisible({ timeout: 10000 });
  await box.fill(text);
}

async function shelfValue(page, role) {
  return page.evaluate((r) => {
    const api = window.__studioApi;
    const st = api && api.getState();
    const store = st && st.playground && st.playground._workflowRun;
    return store && store.controlValues ? store.controlValues[r] : undefined;
  }, role);
}

async function uploadSource(page, role) {
  // Real file-chooser upload through the image Tool Input block.
  await page.locator(`[data-testid="shelf-input-${role}-file"]`).setInputFiles(SOURCE_FIXTURE);
  await expect.poll(() => shelfValue(page, role), { timeout: 10000 }).toBeTruthy();
}

async function paintStroke(page, tool) {
  // Real pointer painting on the editor canvas.
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

async function runAndGetOutput(page, fx) {
  await expect(page.locator(RUN)).toBeEnabled({ timeout: 15000 });
  await page.locator(RUN).click();
  await fx.waitForStatus("Run completed", { timeout: 20000 });
  const state = await fx.getState();
  const runs = state.workflowRuns || [];
  return runs.length ? runs[runs.length - 1] : null;
}

test.describe("Studio image workspace tools (fake backend)", () => {
  test("Story 1 — T2I survives: select, shelf, run, output", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
      for (const tool of ["t2i", "i2i", "inpaint", "sketch", "outpaint"]) {
        await expect(page.locator(`[data-testid="studio-tool-${tool}"]`)).toBeVisible();
      }
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await expect(page.locator('[data-testid="studio-tool-t2i"]')).toHaveAttribute("aria-pressed", "true");
      await selectWorkflow(page, "wf_text2img");
      await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="shelf-prompt-card"]')).toBeVisible();
      await fillPrompt(page, "a red bicycle");
      const run = await runAndGetOutput(page, fx);
      expect(run).toBeTruthy();
      expect(run.featureId).toBe("txt2img");
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 2 — T2I to I2I chaining with truthful type", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await fillPrompt(page, "a blue teapot");
      const first = await runAndGetOutput(page, fx);
      expect(first).toBeTruthy();
      const firstOutput = await page.locator('[data-testid="canvas-output"]').getAttribute("src");
      expect(firstOutput).toBeTruthy();
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await expect(page.locator('[data-testid="studio-tool-i2i"]')).toHaveAttribute("aria-pressed", "true");
      // Previous output stays visible in the same workspace.
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 10000 });
      await selectWorkflow(page, "wf_i2i");
      await expect(page.locator('[data-testid="shelf-field-source_image"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="shelf-input-source_image-use-current"]')).toBeVisible();
      // The previous output chained automatically: the canvas link is on.
      const linkBox = page.locator('[data-testid="shelf-input-source_image-use-current"]');
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      await expect(linkBox).toBeChecked({ timeout: 10000 });
      // Unchecking releases the source; re-checking re-links the canvas.
      await linkBox.click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 10000 }).toBe("");
      await expect(linkBox).not.toBeChecked();
      await linkBox.click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      await expect(linkBox).toBeChecked({ timeout: 10000 });
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 10000 }).toMatch(/studio-current-/);
      await fillPrompt(page, "make it brass");
      const second = await runAndGetOutput(page, fx);
      expect(second).toBeTruthy();
      expect(second.featureId).toBe("i2i");
      expect(String(second.controls.source_image)).toMatch(/studio-current-/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 3 — Inpaint brush/erase/size/clear and bindings", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-inpaint"]').click();
      await selectWorkflow(page, "wf_inpaint");
      await expect(page.locator('[data-testid="inpaint-editor"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="inpaint-brush"]')).toBeVisible();
      await expect(page.locator('[data-testid="inpaint-erase"]')).toBeVisible();
      // Real file-chooser upload through the Source Image Tool Input.
      await uploadSource(page, "source_image");
      const uploadedSource = await shelfValue(page, "source_image");
      expect(String(uploadedSource)).toMatch(/studio-source/);
      // Real pointer painting, then a real mask save (upload + commit).
      await paintStroke(page, "inpaint");
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/has paint/i);
      await page.locator('[data-testid="inpaint-erase"]').click();
      await page.locator('[data-testid="inpaint-brush"]').click();
      await page.locator('[data-testid="inpaint-brush-size"]').fill("48");
      await page.locator('[data-testid="inpaint-clear"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/cleared/i);
      await paintStroke(page, "inpaint");
      await page.locator('[data-testid="inpaint-save"]').click();
      await expect(page.locator('[data-testid="inpaint-mask-preview"]')).toContainText(/Mask saved:/);
      const savedMask = await shelfValue(page, "mask");
      expect(String(savedMask)).toMatch(/studio-mask-/);
      // Submission uses generic Source Image + Mask bindings.
      await fillPrompt(page, "remove the scratch");
      const run = await runAndGetOutput(page, fx);
      expect(String(run.controls.source_image)).toMatch(/studio-source/);
      expect(String(run.controls.mask)).toMatch(/studio-mask-/);
      expect(run.featureId).toBe("inpaint");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 4 — Sketch annotation and generic input", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-sketch"]').click();
      await selectWorkflow(page, "wf_sketch");
      await expect(page.locator('[data-testid="sketch-editor"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="sketch-save"]')).toBeVisible();
      await uploadSource(page, "source_image");
      await paintStroke(page, "sketch");
      await page.locator('[data-testid="sketch-save"]').click();
      await expect(page.locator('[data-testid="sketch-mask-preview"]')).toContainText(/Sketch saved as Source Image:/);
      const flattened = await shelfValue(page, "source_image");
      expect(String(flattened)).toMatch(/studio-sketch-/);
      await fillPrompt(page, "turn the sketch into a cat");
      const run = await runAndGetOutput(page, fx);
      expect(String(run.controls.source_image)).toMatch(/studio-sketch-/);
      expect(run.featureId).toBe("sketch");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 5 — Outpaint expansion controls and generic inputs", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-outpaint"]').click();
      await selectWorkflow(page, "wf_outpaint");
      await expect(page.locator('[data-testid="outpaint-editor"]')).toBeVisible({ timeout: 10000 });
      await uploadSource(page, "source_image");
      await page.locator('[data-testid="outpaint-right"]').fill("128");
      await expect(page.locator('[data-testid="outpaint-preview-note"]')).toContainText(/centered|masked/i);
      // Real expansion save: 16px fixture + 128px right = 144 wide.
      await page.locator('[data-testid="outpaint-save"]').click();
      await expect(page.locator('[data-testid="outpaint-preview-note"]')).toContainText(/144x16/);
      const expSource = await shelfValue(page, "source_image");
      expect(String(expSource)).toMatch(/studio-outpaint-/);
      await fillPrompt(page, "extend the meadow");
      const run = await runAndGetOutput(page, fx);
      expect(String(run.controls.source_image)).toMatch(/studio-outpaint-/);
      expect(run.featureId).toBe("outpaint");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 6 — Structured prompt produces the ordinary prompt input", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await expect(page.locator('[data-testid="shelf-prompt-card"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="shelf-prompt-mode-structured"]').click();
      await expect(page.locator('[data-testid="shelf-prompt-structured"]')).toBeVisible();
      await page.locator('[data-testid="shelf-prompt-structured-subject"]').fill("a lighthouse");
      await page.locator('[data-testid="shelf-prompt-structured-style"]').fill("oil painting");
      await expect(page.locator('[data-testid="shelf-prompt-structured-preview"]')).toContainText(/lighthouse.*oil painting/i);
      const run = await runAndGetOutput(page, fx);
      expect(String(run.controls.prompt)).toMatch(/lighthouse/);
      expect(run.featureId).toBe("txt2img");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 7 — tool filter keeps selection and editor coherent", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      // A mismatched workflow is not offered while T2I is active.
      const t2iOptions = await page.locator('[data-testid="workflow-selector"] option').evaluateAll((els) =>
        els.map((o) => o.getAttribute("value"))
      );
      expect(t2iOptions).not.toContain("wf_inpaint");
      // Switching tools re-filters; the matching workflow then selects.
      await page.locator('[data-testid="studio-tool-inpaint"]').click();
      await selectWorkflow(page, "wf_inpaint");
      await expect(page.locator('[data-testid="studio-tool-inpaint"]')).toHaveAttribute("aria-pressed", "true");
      await expect(page.locator('[data-testid="inpaint-editor"]')).toBeVisible({ timeout: 10000 });
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 8 — structured field breakdown survives mode toggles", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await page.locator('[data-testid="shelf-prompt-mode-structured"]').click();
      await page.locator('[data-testid="shelf-prompt-structured-subject"]').fill("a lighthouse");
      await page.locator('[data-testid="shelf-prompt-structured-style"]').fill("oil painting");
      await page.locator('[data-testid="shelf-prompt-mode-text"]').click();
      await page.locator('[data-testid="shelf-prompt-mode-structured"]').click();
      await expect(page.locator('[data-testid="shelf-prompt-structured-style"]')).toHaveValue("oil painting");
      await expect(page.locator('[data-testid="shelf-prompt-structured-subject"]')).toHaveValue("a lighthouse");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 9 — cross-type handoff remounts strip and editor", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      // Same handoff the Workflows page Run button writes.
      await page.evaluate(() => {
        localStorage.setItem(
          "comfymodal.studio.playground.workflow-handoff.v1",
          JSON.stringify({ workflowId: "wf_inpaint", workflowVersionId: "wv_inpaint" })
        );
      });
      await page.reload({ waitUntil: "domcontentloaded" });
      await page.waitForFunction(() => typeof window.__mountStudioForTest === "function", null, { timeout: 15000 });
      await page.evaluate(() => window.__mountStudioForTest());
      await expect(page.locator('[data-testid="studio-tool-inpaint"]')).toHaveAttribute("aria-pressed", "true", { timeout: 15000 });
      await expect(page.locator('[data-testid="inpaint-editor"]')).toBeVisible({ timeout: 10000 });
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 10 — in-flight upload does not leak into the next workflow", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-sketch"]').click();
      await selectWorkflow(page, "wf_sketch");
      // Hold the upload request mid-flight.
      let releaseUpload;
      const gate = new Promise((res) => { releaseUpload = res; });
      await page.route("**/upload/image", async (route) => {
        await gate;
        await route.continue();
      });
      await page.locator('[data-testid="shelf-input-source_image-file"]').setInputFiles(SOURCE_FIXTURE);
      // Switch tool and workflow while the upload is still in flight.
      await page.locator('[data-testid="studio-tool-inpaint"]').click();
      await selectWorkflow(page, "wf_inpaint");
      releaseUpload();
      await page.waitForTimeout(1000);
      expect((await shelfValue(page, "source_image")) ?? "").toBe("");
      await fx.assertNoConsoleErrors();
      await page.unroute("**/upload/image");
    } finally {}
  });

  test("Story 11 — workspace continues across tools: workflow, values, image", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await fillPrompt(page, "continuity cat");
      await page.locator('[data-testid="shelf-input-seed"]').fill("4242");
      const first = await runAndGetOutput(page, fx);
      expect(first).toBeTruthy();
      // First visit to Image Edit: pick the workflow once.
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_i2i");
      // Prompt and seed carried over from the T2I edit.
      await expect(page.locator('[data-testid="shelf-input-prompt"]')).toHaveValue("continuity cat");
      await expect(page.locator('[data-testid="shelf-input-seed"]')).toHaveValue("4242");
      // Back to T2I and back again: the remembered workflow returns on its
      // own, still carrying the latest values, and the source defaults to
      // the current output with no clicks.
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await expect(page.locator(WF)).toHaveValue("wf_text2img", { timeout: 10000 });
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await expect(page.locator(WF)).toHaveValue("wf_i2i", { timeout: 15000 });
      await expect(page.locator('[data-testid="shelf-input-prompt"]')).toHaveValue("continuity cat");
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 12 — carry bridges graph-era role spellings", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await fillPrompt(page, "alias rivers");
      // Legacy workflow maps the same product input as positive_prompt.
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_legacy_edit");
      await expect(page.locator('[data-testid="shelf-input-positive_prompt"]')).toHaveValue("alias rivers");
      await uploadSource(page, "source_image");
      const run = await runAndGetOutput(page, fx);
      expect(String(run.controls.positive_prompt)).toMatch(/alias rivers/);
      expect(run.featureId).toBe("i2i");
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 17 — sampler tuning neither carries nor poses as shared", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const eitherValue = async (a, b) => {
      const x = await shelfValue(page, a);
      return x !== undefined ? String(x) : String(await shelfValue(page, b));
    };
    try {
      // Record I2I's own tuning values first (fresh: schema defaults).
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_i2i");
      const ownSteps = await eitherValue("steps", "step_count");
      const ownCfg = await eitherValue("cfg", "cfg_scale");
      const ownSched = String(await shelfValue(page, "scheduler"));
      const ownSampler = String(await shelfValue(page, "sampler"));
      // Fresh T2I shelf: tuning starts collapsed in Advanced.
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await expect(page.locator('[data-testid="shelf-advanced-toggle"]')).toContainText(/Advanced \([1-9]/);
      await page.locator('[data-testid="shelf-advanced-toggle"]').click();
      await expect(page.locator('[data-testid="shelf-advanced-section"]')).toBeVisible();
      for (const role of ["steps", "cfg", "scheduler"]) {
        await expect(page.locator(`[data-testid="shelf-advanced-section"] [data-testid="shelf-input-${role}"]`).first()).toBeVisible();
      }
      await expect(page.locator('[data-testid="shelf-advanced-section"] [data-testid="shelf-input-prompt"]')).toHaveCount(0);
      // Distinctive tuning values plus a prompt that must carry.
      await fillPrompt(page, "tuning stays home");
      await page.locator('[data-testid="shelf-input-steps"], [data-testid="shelf-input-step_count"]').first().fill("25");
      await page.locator('[data-testid="shelf-input-cfg"], [data-testid="shelf-input-cfg_scale"]').first().fill("8.5");
      await page.locator('[data-testid="shelf-input-scheduler"]').selectOption("sgm_uniform");
      await page.locator('[data-testid="shelf-input-sampler"]').selectOption("uni_pc");
      expect(ownSteps).not.toBe("25");
      expect(ownCfg).not.toBe("8.5");
      expect(ownSched).not.toBe("sgm_uniform");
      expect(ownSampler).not.toBe("uni_pc");
      // Back to I2I: the remembered workflow returns carrying the prompt,
      // while each workflow keeps its own tuning values.
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await expect(page.locator(WF)).toHaveValue("wf_i2i", { timeout: 15000 });
      await expect(page.locator('[data-testid="shelf-input-prompt"]')).toHaveValue("tuning stays home");
      await expect.poll(() => eitherValue("steps", "step_count"), { timeout: 10000 }).toBe(ownSteps);
      await expect.poll(() => eitherValue("cfg", "cfg_scale"), { timeout: 10000 }).toBe(ownCfg);
      await expect.poll(() => eitherValue("scheduler", "scheduler"), { timeout: 10000 }).toBe(ownSched);
      await expect.poll(async () => String(await shelfValue(page, "sampler")), { timeout: 10000 }).toBe(ownSampler);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 13 — carousel reselect follows the newly current image", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await fillPrompt(page, "first image");
      await runAndGetOutput(page, fx);
      const firstSrc = await page.locator('[data-testid="canvas-output"]').getAttribute("src");
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_i2i");
      await fillPrompt(page, "second image");
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      const sourceForFirst = await shelfValue(page, "source_image");
      await runAndGetOutput(page, fx);
      // Pick the older run from the carousel: canvas and source follow it.
      const items = page.locator('[data-testid="filmstrip"] .comfymodal-studio-carousel-item');
      const idx = await items.evaluateAll((els, want) => {
        for (let i = 0; i < els.length; i++) {
          const img = els[i].querySelector("img");
          if (img && img.getAttribute("src") === want) return i;
        }
        return -1;
      }, firstSrc);
      expect(idx).toBeGreaterThanOrEqual(0);
      await items.nth(idx).click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      const sourceReselected = await shelfValue(page, "source_image");
      expect(String(sourceReselected)).not.toBe(String(sourceForFirst));
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 14 — source picker offers history, PC, and canvas", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // Phase-1 shell: modes on the rail, tools in the submenu —
      // Edit → Text selects the I2I family. NOTE: no run is submitted:
      // run completion is broken tree-wide on this branch (see the
      // postprocess spec header), and the Browse door hydrates from the
      // History V2 feed seed instead, which is exactly what this test
      // needs. The shelf renders before that hydration lands, so remount
      // once with a warm cache when the door is not there yet.
      async function gotoI2I() {
        await page.locator('[data-testid="studio-tool-edit"]').click();
        await page.locator('[data-testid="studio-subtool-text"]').click();
        await selectWorkflow(page, "wf_i2i");
      }
      await gotoI2I();
      const browse = page.locator('[data-testid="shelf-input-source_image-history-browse"]');
      if ((await browse.count()) === 0) {
        await fx.reload();
        await gotoI2I();
      }
      // All three doors are present on the Source Image card.
      await expect(page.locator('[data-testid="shelf-input-source_image-file"]')).toBeVisible();
      await expect(page.locator('[data-testid="shelf-input-source_image-use-current"]')).toBeVisible();
      await expect(browse).toBeVisible({ timeout: 20000 });
      // Pick a history image through the shared visual gallery: browse
      // dialog, click one real card, Use image applies — the Source Image
      // shelf value becomes a real mapped filename and the canvas follows.
      await page.locator('[data-testid="shelf-input-source_image-history-browse"]').click();
      const historyDialog = page.locator('[data-testid="shelf-input-source_image-history-dialog"]');
      await expect(historyDialog).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="history-picker-grid"]')).toBeVisible({ timeout: 10000 });
      const galleryCards = page.locator('[data-testid="history-picker-card"]');
      await expect.poll(async () => galleryCards.count(), { timeout: 15000 }).toBeGreaterThan(0);
      await galleryCards.first().click();
      // Single-select clarity: the picked card shows a checkmark and a
      // compact thumbnail/label sits beside Use image.
      await expect(page.locator('[data-testid="history-picker-selected"]')).toBeVisible({ timeout: 10000 });
      const selection = page.locator('[data-testid="history-picker-selection"]');
      await expect(selection).toBeVisible({ timeout: 10000 });
      await expect(selection).not.toBeEmpty();
      const useImage = page.locator('[data-testid="history-picker-confirm"]');
      await expect(useImage).toBeEnabled({ timeout: 10000 });
      await page.screenshot({ path: "test-results/proof/phase10-browse-history-single.png" });
      await useImage.click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-history-/);
      const canvasSrc = await page.locator('[data-testid="canvas-output"]').getAttribute("src");
      expect(String(canvasSrc)).toMatch(/studio-history-/);
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 15 — lineage links generations to their source", async ({ page }) => {    const fx = await setupFakeTest(page);
    try {
      await page.locator('[data-testid="studio-tool-t2i"]').click();
      await selectWorkflow(page, "wf_text2img");
      await fillPrompt(page, "lineage root");
      const first = await runAndGetOutput(page, fx);
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_i2i");
      await fillPrompt(page, "lineage child");
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 15000 }).toMatch(/studio-current-/);
      const childSource = await shelfValue(page, "source_image");
      await runAndGetOutput(page, fx);
      const tree = await page.evaluate(() => {
        const st = window.__studioApi.getState();
        return (st.playground && st.playground.imageLineage && st.playground.imageLineage.nodes) || {};
      });
      // The I2I result is recorded with the chained source as its parent,
      // and the parent lists it among (possibly many) children. Node keys
      // are canonical (`input:<filename>` for input-directory files).
      const parentKey = "input:" + String(childSource);
      const childKeys = Object.keys(tree).filter((k) => tree[k] && String(tree[k].parent) === parentKey);
      expect(childKeys.length).toBeGreaterThanOrEqual(1);
      childKeys.forEach((k) => {
        expect((tree[parentKey].children || []).join("|")).toContain(k);
      });
      // Root generation has no parent.
      const roots = Object.values(tree).filter((n) => !n.parent);
      expect(roots.length).toBeGreaterThanOrEqual(1);
      // Canvas strip shows the ancestry.
      await expect(page.locator('[data-testid="lineage-strip"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="lineage-parent"]')).toBeVisible();
      await fx.assertNoConsoleErrors();
    } finally {}
  });

  test("Story 16 — canvas files resolve instead of duplicating", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const uploads = [];
    page.on("request", (r) => { if (r.url().includes("/upload/image")) uploads.push(r.url()); });
    try {
      await page.locator('[data-testid="studio-tool-i2i"]').click();
      await selectWorkflow(page, "wf_i2i");
      // One real PC upload, then a run so the output has lineage back to it.
      await uploadSource(page, "source_image");
      const file = await shelfValue(page, "source_image");
      expect(String(file)).toMatch(/studio-source/);
      expect(uploads.length).toBe(1);
      await fillPrompt(page, "resolve round-trip");
      await runAndGetOutput(page, fx);
      await expect(page.locator('[data-testid="lineage-strip"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="lineage-parent"]')).toBeVisible();
      // Clicking the parent makes the canvas a /view URL for the on-drive
      // file; clearing then re-linking must resolve that same file with
      // zero new uploads (no pixel duplicate).
      await page.locator('[data-testid="lineage-parent"]').click();
      await expect.poll(
        () => page.locator('[data-testid="canvas-output"]').getAttribute("src"),
        { timeout: 10000 },
      ).toContain("/view?filename=");
      await page.locator('[data-testid="shelf-input-source_image-clear"]').click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 10000 }).toBe("");
      await page.locator('[data-testid="shelf-input-source_image-use-current"]').click();
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 10000 }).toBe(String(file));
      await expect(page.locator('[data-testid="shelf-input-source_image-use-current"]')).toBeChecked();
      expect(uploads.length).toBe(1);
      // Switching tools carries the same file, still with no re-upload.
      await page.locator('[data-testid="studio-tool-sketch"]').click();
      await selectWorkflow(page, "wf_sketch");
      await expect.poll(() => shelfValue(page, "source_image"), { timeout: 10000 }).toBe(String(file));
      expect(uploads.length).toBe(1);
      await fx.assertNoConsoleErrors();
    } finally {}
  });
});
