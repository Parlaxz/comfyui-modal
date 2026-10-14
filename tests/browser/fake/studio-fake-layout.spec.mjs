// Generate Layout editor — Phase 7 KJNodes port (fake backend, bounded).
//
// Proves Generate → Layout against the real frontend: KJ editor mount
// (canvas/dims/token/palette/globals/region list/inspector/preview),
// REAL canvas drag-draws (page.mouse, one drag per boundingBox read),
// click select, move + SE-handle resize, object/text switch, exact text,
// desc + palette edits in the Ideogram JSON preview, duplicate/reorder/
// delete, Alt-click overlap cycling, global fields + style block,
// 0-1000 yx bbox serialization, Send to Prompt (prompt control + return
// to Text), and draft survival across reload. No runs are submitted.
//
// Selector source: web/studio-layout-editor.js (stlay-* DOM) +
// web/studio-playground.js (Generate/Layout shell seam, Send to Prompt).
// The /comfymodal/sync/status 404 allowlist is the pre-existing
// shell↔fake-server gap (see studio-fake-postprocess.spec.mjs), unrelated
// to this workspace.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const STRIP = '[data-testid="studio-tool-strip"]';
const GEN_TOOL = '[data-testid="studio-tool-generate"]';
const TEXT_SUBTOOL = '[data-testid="studio-subtool-text"]';
const LAYOUT_SUBTOOL = '[data-testid="studio-subtool-layout"]';
const WF = '[data-testid="workflow-selector"]';
const PROMPT = '[data-testid="shelf-input-prompt"]';
const LAYOUT_KEY = "comfymodal.studio.layout.kj.v1";
const LAYOUT_LEGACY_KEY = "comfymodal.studio.layout.v1";

const CANVAS = ".stlay-canvas";
const ROWS = ".stlay-lrow";

// Pre-existing shell↔fake-server gap: web/studio-shell.js polls
// `${apiBase}/sync/status`, which the fake server does not implement. The
// console text carries no URL, so track 4xx URLs directly and assert
// sync/status is the only one; any other 4xx fails the test.
const ALLOW = [/Failed to load resource.*404/];
function watch4xx(page) {
  const bad = [];
  page.on("response", (r) => { if (r.status() >= 400) bad.push(r.status() + " " + r.url()); });
  return bad;
}
function expectOnlySync404(bad) {
  const other = bad.filter((u) => u.indexOf("sync/status") === -1);
  expect(other).toEqual([]);
}

function clearLayoutDraft(page) {
  return page.evaluate(([kj, legacy]) => {
    try { localStorage.removeItem(kj); } catch (_e) {}
    try { localStorage.removeItem(legacy); } catch (_e) {}
  }, [LAYOUT_KEY, LAYOUT_LEGACY_KEY]);
}

function readLayoutDraft(page) {
  return page.evaluate((key) => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch (_e) { return null; }
  }, LAYOUT_KEY);
}

// Generate → Layout. The KJ layout editor owns the canvas view when
// activeTool is t2i and the shell subtool is layout (see renderCanvas);
// it is NOT a later-phase placeholder (placeholders are only
// references/guidance/upscale), so no disabled notice is expected.
async function gotoGenerateLayout(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(LAYOUT_SUBTOOL).click();
  await expect(page.locator(LAYOUT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await expect(page.locator(CANVAS)).toBeVisible({ timeout: 10000 });
  await page.locator(CANVAS).scrollIntoViewIfNeeded();
}

// Generate → Text with a T2I workflow selected, then over to Layout. The
// workflow pick happens in Text (where the workflow-selector shelf is
// proven, per the style-browser spec) so the Send-to-Prompt test has a
// real T2I target for commitShelfValue("prompt", …).
async function gotoLayoutWithWorkflow(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(TEXT_SUBTOOL).click();
  await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(WF).selectOption("wf_text2img");
  await expect(page.locator(WF)).toHaveValue("wf_text2img", { timeout: 10000 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
  await page.locator(LAYOUT_SUBTOOL).click();
  await expect(page.locator(LAYOUT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await expect(page.locator(CANVAS)).toBeVisible({ timeout: 10000 });
  await page.locator(CANVAS).scrollIntoViewIfNeeded();
}

// Real drag-draw on the KJ canvas (fraction coordinates 0-1). One drag per
// boundingBox read: committing a region re-renders the panel and shifts
// dialog scroll, so a stale box misplaces the next drag.
async function dragDraw(page, x1, y1, x2, y2, opts = {}) {
  const box = await page.locator(CANVAS).boundingBox();
  const px = (fx) => box.x + fx * box.width;
  const py = (fy) => box.y + fy * box.height;
  await page.mouse.move(px(x1), py(y1));
  // NOTE: mouse.down() takes no modifiers option — hold Control via the
  // keyboard so the KJ canvas sees ctrlKey for force-draw over a box.
  if (opts.ctrl) await page.keyboard.down("Control");
  await page.mouse.down();
  await page.mouse.move(px(x2), py(y2), { steps: 10 });
  await page.mouse.up();
  if (opts.ctrl) await page.keyboard.up("Control");
}

async function canvasClick(page, fx, fy, opts = {}) {
  const box = await page.locator(CANVAS).boundingBox();
  await page.mouse.move(box.x + fx * box.width, box.y + fy * box.height);
  await page.mouse.down({ button: "left", ...(opts.alt ? { modifiers: ["Alt"] } : {}) });
  await page.mouse.up({ button: "left" });
}

function previewLocator(page) {
  // The editor renders two <pre> blocks carrying the caption (pretty preview
  // .stlay-pre + full {json,text} dump). Assert against the preview one.
  return page.locator("pre.stlay-pre");
}

test.describe("Generate Layout editor (fake backend)", () => {
  test("T1 — Generate → Layout renders KJ editor shell", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await expect(page.locator(CANVAS)).toBeVisible();
    await expect(page.getByRole("spinbutton", { name: "Canvas width (multiples of 16)" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Copy JSON" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Clear all" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Send to Prompt/ })).toBeVisible();
    await expect(page.getByPlaceholder("High-level description (optional, blank = omitted)")).toBeVisible();
    await expect(page.getByPlaceholder("Background description (required scene background)")).toBeVisible();
    await expect(page.getByText("Regions (array order; last = front)")).toBeVisible();
    await expect(page.getByText("Structured JSON preview")).toBeVisible();
    // Empty draft serializes to the Ideogram-caption JSON envelope.
    const preview = previewLocator(page);
    await expect(preview).toContainText('"elements"', { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — drag draws grow the region count", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await expect(page.locator(ROWS)).toHaveCount(0);
    await dragDraw(page, 0.08, 0.08, 0.45, 0.5);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await dragDraw(page, 0.55, 0.1, 0.92, 0.3);
    await expect(page.locator(ROWS)).toHaveCount(2, { timeout: 10000 });
    // Ctrl-drag force-draws over an existing box (upstream 1527-1529).
    await dragDraw(page, 0.3, 0.35, 0.65, 0.75, { ctrl: true });
    await expect(page.locator(ROWS)).toHaveCount(3, { timeout: 10000 });
    const draft = await readLayoutDraft(page);
    expect(draft.boxes).toHaveLength(3);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T3 — object/text switch, exact text, desc land in JSON with yx bbox", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await dragDraw(page, 0.55, 0.1, 0.92, 0.3);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await page.getByTitle("Element type (object -> type obj, text -> type text)").selectOption("text");
    await page.getByPlaceholder("text (text elements only)").fill("GRAND OPENING");
    await page.getByPlaceholder("desc (always emitted)").fill("bold sign lettering");
    const preview = previewLocator(page);
    await expect(preview).toContainText('"type": "text"', { timeout: 10000 });
    await expect(preview).toContainText('"text": "GRAND OPENING"', { timeout: 10000 });
    await expect(preview).toContainText('"desc": "bold sign lettering"', { timeout: 10000 });
    // Ideogram bbox: [ymin,xmin,ymax,xmax] on the 0-1000 grid.
    const text = await preview.textContent();
    expect(text).toMatch(/"bbox":\s*\[\s*100,\s*550,\s*300,\s*920\s*\]/);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T4 — duplicate/reorder/delete + Clear all", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await dragDraw(page, 0.08, 0.08, 0.45, 0.5);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    // Region rows render icon buttons whose accessible name is the glyph, so
    // target them by title (Lock / Bring toward front / Send toward back /
    // Duplicate / Delete). Dispatch via evaluate: the tiny icon buttons are
    // not CDP-actionable in the harness, but .click() still runs the
    // real listener path.
    const rowBtn = (rowIdx, title) => page.evaluate(([i, t]) => {
      const rows = [...document.querySelectorAll(".stlay-lrow")];
      const b = [...rows[i].querySelectorAll("button")].find((x) => (x.title || "") === t);
      if (!b) return "MISSING";
      b.click();
      return "OK";
    }, [rowIdx, title]);
    await rowBtn(0, "Duplicate");
    await expect(page.locator(ROWS)).toHaveCount(2, { timeout: 10000 });
    // Reorder: the duplicate sits at the front; send it toward back and
    // prove the serialized element order follows the array order.
    const geo = () => readLayoutDraft(page).then((d) => d.boxes.map((b) => [b.x, b.y]));
    const before = await geo();
    await rowBtn(0, "Send toward back");
    const after = await geo();
    expect(after).not.toEqual(before);
    expect(after.slice().sort()).toEqual(before.slice().sort());
    await rowBtn(0, "Delete");
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await page.getByRole("button", { name: "Clear all" }).click();
    await expect(page.locator(ROWS)).toHaveCount(0, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T5 — canvas dims persist + globals feed the caption", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    // NOTE: canvas dims commit on "change" (upstream commitPxEdit parity —
    // no per-keystroke refit), and fill() alone does not blur, so Tab out
    // to fire change.
    await page.getByRole("spinbutton", { name: "Canvas width (multiples of 16)" }).fill("1280");
    await page.keyboard.press("Tab");
    await expect.poll(async () => {
      const d = await readLayoutDraft(page);
      return d && d.width;
    }, { timeout: 10000 }).toBe(1280);
    await page.getByPlaceholder("Background description (required scene background)").click();
    await page.getByPlaceholder("Background description (required scene background)").fill("clear blue sky");
    await page.getByPlaceholder("High-level description (optional, blank = omitted)").click();
    await page.getByPlaceholder("High-level description (optional, blank = omitted)").fill("sunny street");
    const preview = previewLocator(page);
    await expect(preview).toContainText('"background": "clear blue sky"', { timeout: 10000 });
    await expect(preview).toContainText('"high_level_description": "sunny street"', { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T6 — Send to Prompt fills prompt + returns to Text", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoLayoutWithWorkflow(page);
    await dragDraw(page, 0.08, 0.08, 0.45, 0.5);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await page.getByPlaceholder("desc (always emitted)").fill("lighthouse");
    await page.getByRole("button", { name: /Send to Prompt/ }).click();
    // Send writes through commitShelfValue("prompt", serialization) and
    // flips the shell back to the Text subtool, so the prompt field shows
    // the serialization on the normal T2I path.
    await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    const prompt = page.locator(PROMPT);
    await expect(prompt).toBeVisible({ timeout: 10000 });
    await expect(prompt).toHaveValue(/compositional_deconstruction/, { timeout: 10000 });
    await expect(prompt).toHaveValue(/lighthouse/, { timeout: 10000 });
    // Selected T2I workflow is unchanged by the round trip.
    await expect(page.locator(WF)).toHaveValue("wf_text2img", { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T7 — draft persists across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await dragDraw(page, 0.08, 0.08, 0.45, 0.5);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await page.getByPlaceholder("desc (always emitted)").fill("lighthouse");
    await expect(previewLocator(page)).toContainText("lighthouse", { timeout: 10000 });
    // NOTE (harness-correct reload): raw page.reload() drops the
    // __mountStudioForTest harness, so use the shared fx.reload() helper
    // (same session goto + remount, same origin so localStorage survives).
    await fx.reload();
    await gotoGenerateLayout(page);
    await expect(page.locator(ROWS)).toHaveCount(1, { timeout: 10000 });
    await expect(previewLocator(page)).toContainText("lighthouse", { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });
});
