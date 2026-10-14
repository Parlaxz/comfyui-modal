// Modal Studio — KJNodes Layout Editor E2E Tests (mocked backend).
//
// Drives the delegated editor (web/studio-layout-editor.js via the
// web/studio-playground.js seam) against the mocked backend: installMocks
// FIRST (installStudioMockApi, then installWorkflowsMock — later routes take
// precedence), then openStudio. Uses fresh Playwright Test page/context
// (never MCP/shared session). No runs are submitted.
//
// Selector source: web/studio-playground.js (_renderLayoutEditor seam owns
// layout-editor/layout-mount/layout-preview/layout-send) and
// web/studio-layout-editor.js (vanilla .stlay-* DOM: .stlay-canvas,
// .stlay-lrow, .stlay-pre, titled list buttons, titled bbox inputs).
//
// Sequencing note (stale-closure behavior, pinned by
// tests/studio_layout_editor_unit.mjs): light touches re-normalize the draft
// without re-rendering the side panel, so side-panel controls are always
// re-queried after a full touch (change/click) and a list-row click resyncs
// the panel before the next control is used. Canvas flows are index-based
// and need no resync.

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  openStudio,
} from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";
import { installWorkflowsMock } from "./studio-workflows-mock.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";
const KJ_KEY = "comfymodal.studio.layout.kj.v1";
const LEGACY_KEY = "comfymodal.studio.layout.v1";

const STRIP = '[data-testid="studio-tool-strip"]';
const GEN_TOOL = '[data-testid="studio-tool-generate"]';
const TEXT_SUBTOOL = '[data-testid="studio-subtool-text"]';
const LAYOUT_SUBTOOL = '[data-testid="studio-subtool-layout"]';
const WF = '[data-testid="workflow-selector"]';
const EDITOR = '[data-testid="layout-editor"]';
const PREVIEW = '[data-testid="layout-preview"]';
const SEND = '[data-testid="layout-send"]';
const PROMPT = '[data-testid="shelf-input-prompt"]';
const CANVAS = ".stlay-canvas";
const ROWS = ".stlay-lrow";
const JSON_PRE = ".stlay-pre";

// ── Primary-extension pin ───────────────────────────────────────────────
// Mirrors studio-playground.spec.mjs: the mocked suite has no Playwright
// webServer and navigates to the shared ComfyUI instance at 127.0.0.1:8188,
// letting that server's extension registry resolve /extensions/.... Sibling
// lanes register the same extension name, so without pinning the page can
// load stale sibling code instead of this repo's primary copy at
// /extensions/comfyui-modal/.
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

async function installMocks(page) {
  const api = await installStudioMockApi(page);
  const wfMock = await installWorkflowsMock(page);
  // Mount-pinning: rewrite sibling-lane extension requests to the primary
  // copy BEFORE the app loads (see pinPrimaryExtensionRequests).
  await pinPrimaryExtensionRequests(page);
  // The Shelf loads the model library on Workflow selection; the shared
  // mock has no /studio/models handler, so stub it here (registered last,
  // takes precedence, never recorded as unhandled).
  await page.route("**/comfymodal/studio/models**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ status: "ok", models: [] }),
    });
  });
  return { api, wfMock };
}

async function gotoGenerateLayout(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(LAYOUT_SUBTOOL).click();
  await expect(page.locator(LAYOUT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await expect(page.locator(EDITOR)).toBeVisible({ timeout: 10000 });
  await expect(page.locator(CANVAS)).toBeVisible({ timeout: 10000 });
}

// Generate → Text with a T2I-capable workflow selected, then over to Layout,
// so Send to Prompt has a real prompt-role target for commitShelfValue.
async function gotoLayoutWithWorkflow(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(TEXT_SUBTOOL).click();
  await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(WF).selectOption({ index: 1 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
  const before = await page.locator(WF).inputValue();
  await page.locator(LAYOUT_SUBTOOL).click();
  await expect(page.locator(LAYOUT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await expect(page.locator(EDITOR)).toBeVisible({ timeout: 10000 });
  return before;
}

function clearDrafts(page) {
  return page.evaluate(([kj, legacy]) => {
    try { localStorage.removeItem(kj); } catch (_e) {}
    try { localStorage.removeItem(legacy); } catch (_e) {}
  }, [KJ_KEY, LEGACY_KEY]);
}

function readKJ(page) {
  return page.evaluate((key) => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch (_e) { return null; }
  }, KJ_KEY);
}

function previewJSON(page) {
  return page.locator(PREVIEW).textContent().then((t) => JSON.parse(t));
}

// Draw a region by dragging across the canvas in CSS px offsets.
async function drawBox(page, x1, y1, x2, y2) {
  const box = await page.locator(CANVAS).boundingBox();
  await page.mouse.move(box.x + x1, box.y + y1);
  await page.mouse.down();
  await page.mouse.move(box.x + x2, box.y + y2, { steps: 5 });
  await page.mouse.up();
}

async function clickAt(page, x, y, options = {}) {
  const box = await page.locator(CANVAS).boundingBox();
  await page.mouse.move(box.x + x, box.y + y);
  await page.mouse.down(options);
  await page.mouse.up(options);
}

// Click a region-list row to select it AND resync the side panel (see the
// stale-closure sequencing note above).
async function selectRow(page, index) {
  await page.locator(ROWS).nth(index).click();
}

test.describe("KJNodes layout editor (mocked backend)", () => {
  test("L1 — Generate → Layout renders the delegated editor with JSON preview", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await expect(page.locator('[data-testid="layout-mount"]')).toBeVisible();
    await expect(page.locator(SEND)).toBeVisible();
    // Empty draft serializes to Ideogram JSON: the compositional envelope
    // with an empty element list, never the legacy Scene:/Canvas: prose.
    const json = await previewJSON(page);
    expect(json.compositional_deconstruction).toBeTruthy();
    expect(json.compositional_deconstruction.elements).toEqual([]);
    await expect(page.locator(PREVIEW)).not.toContainText("Scene:");
    guard.assertNoErrors();
  });

  test("L2 — draw/select/move/resize update the JSON bbox", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await expect(page.locator(ROWS)).toHaveCount(0);
    await drawBox(page, 20, 20, 120, 80);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.length).toBe(1);
    const first = json.compositional_deconstruction.elements[0].bbox;
    expect(first.length).toBe(4);
    // Move the body by (+40,+40)px: ymin/xmin grow, size preserved.
    const canvas = page.locator(CANVAS);
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + 40, box.y + 40);
    await page.mouse.down();
    await page.mouse.move(box.x + 80, box.y + 80, { steps: 5 });
    await page.mouse.up();
    json = await previewJSON(page);
    const moved = json.compositional_deconstruction.elements[0].bbox;
    expect(moved[0]).toBeGreaterThan(first[0]);
    expect(moved[1]).toBeGreaterThan(first[1]);
    expect(moved[2] - moved[0]).toBe(first[2] - first[0]);
    expect(moved[3] - moved[1]).toBe(first[3] - first[1]);
    // Resize from the SE corner: ymax/xmax grow.
    const rect = await canvas.boundingBox();
    const h = (moved[2] / 1000) * rect.height + rect.y;
    const w = (moved[3] / 1000) * rect.width + rect.x;
    await page.mouse.move(w - 2, h - 2);
    await page.mouse.down();
    await page.mouse.move(w + 40, h + 40, { steps: 5 });
    await page.mouse.up();
    json = await previewJSON(page);
    const grown = json.compositional_deconstruction.elements[0].bbox;
    expect(grown[2] - grown[0]).toBeGreaterThan(moved[2] - moved[0]);
    expect(grown[3] - grown[1]).toBeGreaterThan(moved[3] - moved[1]);
    guard.assertNoErrors();
  });

  test("L3 — Alt-click cycles overlapping regions", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 140, 100);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("alpha");
    await drawBox(page, 60, 40, 180, 120);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("beta");
    // Plain click in the overlap selects the front (beta) box.
    await clickAt(page, 100, 70);
    await page.locator(CANVAS).press("Delete");
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.map((e) => e.desc)).toEqual(["alpha"]);
    // Redraw beta, then Alt-click the overlap to reach the box underneath.
    await drawBox(page, 60, 40, 180, 120);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("beta");
    await page.mouse.move((await page.locator(CANVAS).boundingBox()).x + 100, (await page.locator(CANVAS).boundingBox()).y + 70);
    await page.mouse.down({ modifiers: ["Alt"] });
    await page.mouse.up({ modifiers: ["Alt"] });
    await page.locator(CANVAS).press("Delete");
    json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.map((e) => e.desc)).toEqual(["beta"]);
    guard.assertNoErrors();
  });

  test("L4 — object/text switch keeps exact text; unplaced omits bbox", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 120, 80);
    await selectRow(page, 0);
    // Object elements carry no text key.
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements[0].type).toBe("obj");
    expect("text" in json.compositional_deconstruction.elements[0]).toBe(false);
    // Switch to text and set the exact payload.
    await page.locator(".stlay-side select").selectOption("text");
    await page.locator('.stlay-side input[placeholder="text (text elements only)"]').fill("SALE NOW");
    json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements[0].type).toBe("text");
    expect(json.compositional_deconstruction.elements[0].text).toBe("SALE NOW");
    // Unplacing omits bbox; re-placing restores it.
    await selectRow(page, 0);
    await page.locator('.stlay-side input[type="checkbox"]').uncheck();
    json = await previewJSON(page);
    expect("bbox" in json.compositional_deconstruction.elements[0]).toBe(false);
    await page.locator('.stlay-side input[type="checkbox"]').check();
    json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements[0].bbox.length).toBe(4);
    guard.assertNoErrors();
  });

  test("L5 — element and style palettes land uppercased in JSON", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 120, 80);
    await selectRow(page, 0);
    // Style palette only serializes under a style mode: pick photo first.
    await page.locator("select", { has: page.locator('option[value="photo"]') }).selectOption("photo");
    await page.locator('.stlay-side button[title="Add a color (uses the clipboard color if it is one)"]').click();
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements[0].color_palette.length).toBe(1);
    expect(json.compositional_deconstruction.elements[0].color_palette[0]).toBe("#FFFFFF");
    guard.assertNoErrors();
  });

  test("L6 — bbox px and 0-1000 grid fields sync to the JSON bbox", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 120, 80);
    await selectRow(page, 0);
    await page.locator('.stlay-side input[title="bbox ymin (0-1000)"]').fill("100");
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements[0].bbox[0]).toBe(100);
    await selectRow(page, 0);
    await page.locator('.stlay-side input[title="bbox x in px"]').fill("60");
    json = await previewJSON(page);
    // 60px of the 1024px default canvas width rounds to grid 59.
    expect(json.compositional_deconstruction.elements[0].bbox[1]).toBe(59);
    guard.assertNoErrors();
  });

  test("L7 — reorder, duplicate, and delete via the region list", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 100, 60);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("first");
    // Duplicate (Ctrl+D is the keyboard twin; the list ⧉ button is covered here).
    await page.locator('.stlay-lrow button[title="Duplicate"]').first().click();
    let json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.length).toBe(2);
    // Bring the back box toward the front: order swaps.
    await page.locator('.stlay-lrow button[title="Bring toward front"]').last().click();
    json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.length).toBe(2);
    // Delete one region.
    await page.locator('.stlay-lrow button[title="Delete"]').first().click();
    json = await previewJSON(page);
    expect(json.compositional_deconstruction.elements.length).toBe(1);
    guard.assertNoErrors();
  });

  test("L8 — globals land in JSON; editor and seam previews agree", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await page.locator('input[placeholder="High-level description (optional, blank = omitted)"]').fill("epic vista");
    await page.locator("select", { has: page.locator('option[value="photo"]') }).selectOption("photo");
    await page.locator('textarea[placeholder="Background description (required scene background)"]').fill("city dusk");
    const json = await previewJSON(page);
    expect(json.high_level_description).toBe("epic vista");
    expect("photo" in json.style_description).toBe(true);
    expect(json.compositional_deconstruction.background).toBe("city dusk");
    // The editor's structured preview and the seam preview carry the same JSON.
    const inner = await page.locator(JSON_PRE).textContent().then((t) => JSON.parse(t));
    expect(inner).toEqual(json);
    guard.assertNoErrors();
  });

  test("L9 — draft persists across reload under the kj key", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    await gotoGenerateLayout(page);
    await drawBox(page, 20, 20, 120, 80);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("lighthouse");
    await expect(page.locator(PREVIEW)).toContainText("lighthouse", { timeout: 10000 });
    const saved = await readKJ(page);
    expect(saved.boxes.length).toBe(1);
    await page.reload({ waitUntil: "domcontentloaded" });
    await openStudio(page, COMFYUI_URL);
    await gotoGenerateLayout(page);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await expect(page.locator(PREVIEW)).toContainText("lighthouse", { timeout: 10000 });
    guard.assertNoErrors();
  });

  test("L10 — Send to Prompt delivers JSON to Generate Text; workflow unchanged", async ({ page }) => {
    await installMocks(page);
    await openStudio(page, COMFYUI_URL);
    const guard = installConsoleGuard(page);
    await clearDrafts(page);
    const workflowBefore = await gotoLayoutWithWorkflow(page);
    await drawBox(page, 20, 20, 120, 80);
    await selectRow(page, 0);
    await page.locator('.stlay-side textarea[placeholder="desc (always emitted)"]').fill("lighthouse");
    await page.locator(SEND).click();
    // Returns to the ordinary Text prompt with the serialization visible.
    await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    const prompt = page.locator(PROMPT);
    await expect(prompt).toBeVisible({ timeout: 10000 });
    const value = await prompt.inputValue();
    const sent = JSON.parse(value);
    expect(sent.compositional_deconstruction.elements[0].desc).toBe("lighthouse");
    // No workflow switching: the selected T2I workflow is untouched, so the
    // next run is the normal T2I path with the JSON in its prompt field.
    expect(await page.locator(WF).inputValue()).toBe(workflowBefore);
    guard.assertNoErrors();
  });
});
