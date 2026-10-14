// Generate Layout editor — Phase 7 (fake backend, bounded).
//
// Proves Generate → Layout against the real frontend: editor shell
// (stage/toolbar/aspect/inspector/preview), add object/text region growth,
// inspector label+desc edits reflected in the deterministic preview,
// delete + reset, aspect persistence (localStorage + stage style),
// Send to Prompt (prompt control + return to Text), and draft survival
// across reload. No runs are submitted; no drag simulation (unreliable in
// the harness — button/input/select interactions only).
//
// Selector source: web/studio-playground.js (_renderLayoutEditor,
// serializeLayout, loadLayoutDraft, SHELL_SUBTOOLS generate submenu).
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
const EDITOR = '[data-testid="layout-editor"]';
const STAGE = '[data-testid="layout-stage"]';
const ADD_OBJ = '[data-testid="layout-add-object"]';
const ADD_TXT = '[data-testid="layout-add-text"]';
const RESET = '[data-testid="layout-reset"]';
const SEND = '[data-testid="layout-send"]';
const ASPECT = '[data-testid="layout-aspect"]';
const INSPECTOR = '[data-testid="layout-inspector"]';
const PREVIEW = '[data-testid="layout-preview"]';
const BOXES = '[data-box-id]';
const LABEL = '[data-testid="layout-box-label"]';
const DESC = '[data-testid="layout-box-desc"]';
const DEL = '[data-testid="layout-box-delete"]';
const PROMPT = '[data-testid="shelf-input-prompt"]';
const LAYOUT_KEY = "comfymodal.studio.layout.v1";

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
  return page.evaluate((key) => {
    try { localStorage.removeItem(key); } catch (_e) {}
  }, LAYOUT_KEY);
}

function readLayoutDraft(page) {
  return page.evaluate((key) => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch (_e) { return null; }
  }, LAYOUT_KEY);
}

// Generate → Layout. The layout editor owns the canvas view when
// activeTool is t2i and the shell subtool is layout (see renderCanvas);
// it is NOT a later-phase placeholder (placeholders are only
// references/guidance/upscale), so no disabled notice is expected.
async function gotoGenerateLayout(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(LAYOUT_SUBTOOL).click();
  await expect(page.locator(LAYOUT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await expect(page.locator(EDITOR)).toBeVisible({ timeout: 10000 });
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
  await expect(page.locator(EDITOR)).toBeVisible({ timeout: 10000 });
}

test.describe("Generate Layout editor (fake backend)", () => {
  test("T1 — Generate → Layout renders editor shell", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await expect(page.locator(STAGE)).toBeVisible();
    await expect(page.locator(ADD_OBJ)).toBeVisible();
    await expect(page.locator(ADD_TXT)).toBeVisible();
    await expect(page.locator(RESET)).toBeVisible();
    await expect(page.locator(SEND)).toBeVisible();
    await expect(page.locator(ASPECT)).toBeVisible();
    await expect(page.locator(INSPECTOR)).toBeVisible();
    await expect(page.locator(PREVIEW)).toBeVisible();
    // Empty draft serializes to the Scene + Canvas envelope.
    await expect(page.locator(PREVIEW)).toContainText("Scene:", { timeout: 10000 });
    await expect(page.locator(PREVIEW)).toContainText("Canvas:", { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — add object then text grows the box count", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await expect(page.locator(BOXES)).toHaveCount(0);
    await page.locator(ADD_OBJ).click();
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    await page.locator(ADD_TXT).click();
    await expect(page.locator(BOXES)).toHaveCount(2, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T3 — inspector label+desc land in preview with geometry", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await page.locator(ADD_OBJ).click();
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    // The new box is auto-selected; click it explicitly to prove selection
    // drives the inspector (pointerdown → selectedId → paintInspector).
    await page.locator(BOXES).first().click();
    await expect(page.locator(LABEL)).toBeVisible({ timeout: 10000 });
    await expect(page.locator(DESC)).toBeVisible({ timeout: 10000 });
    await page.locator(LABEL).fill("lighthouse");
    await page.locator(DESC).fill("tall white tower");
    const preview = page.locator(PREVIEW);
    await expect(preview).toContainText("lighthouse", { timeout: 10000 });
    await expect(preview).toContainText("tall white tower", { timeout: 10000 });
    // Deterministic geometry: integer x=/y= and WxH size (see
    // serializeLayout: `at x=<x>,y=<y> size <w>x<h>`).
    const text = await preview.textContent();
    expect(text).toMatch(/x=\d+,y=\d+/);
    expect(text).toMatch(/size \d+x\d+/);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T4 — delete removes the region; reset clears all", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await page.locator(ADD_OBJ).click();
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    await expect(page.locator(DEL)).toBeVisible({ timeout: 10000 });
    await page.locator(DEL).click();
    await expect(page.locator(BOXES)).toHaveCount(0, { timeout: 10000 });
    await page.locator(ADD_OBJ).click();
    await page.locator(ADD_TXT).click();
    await expect(page.locator(BOXES)).toHaveCount(2, { timeout: 10000 });
    await page.locator(RESET).click();
    await expect(page.locator(BOXES)).toHaveCount(0, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T5 — aspect change persists + stage ratio updates", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await page.locator(ASPECT).selectOption("16:9");
    await expect.poll(async () => {
      const d = await readLayoutDraft(page);
      return d && d.aspect;
    }, { timeout: 10000 }).toBe("16:9");
    // Stage style is set as `aspect-ratio:16 / 9` (colon → " / ").
    await expect.poll(async () => {
      const style = await page.locator(STAGE).getAttribute("style").catch(() => "");
      return (style || "").indexOf("16 / 9") !== -1;
    }, { timeout: 10000 }).toBe(true);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T6 — Send to Prompt fills prompt + returns to Text", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoLayoutWithWorkflow(page);
    await page.locator(ADD_OBJ).click();
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    await page.locator(LABEL).fill("lighthouse");
    await page.locator(SEND).click();
    // Send writes through commitShelfValue("prompt", serialization) and
    // flips the shell back to the Text subtool, so the prompt field shows
    // the serialization on the normal T2I path.
    await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    const prompt = page.locator(PROMPT);
    await expect(prompt).toBeVisible({ timeout: 10000 });
    await expect(prompt).toHaveValue(/Scene:/, { timeout: 10000 });
    await expect(prompt).toHaveValue(/lighthouse/, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T7 — draft persists across reload", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await clearLayoutDraft(page);
    await gotoGenerateLayout(page);
    await page.locator(ADD_OBJ).click();
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    await page.locator(LABEL).fill("lighthouse");
    await expect(page.locator(PREVIEW)).toContainText("lighthouse", { timeout: 10000 });
    // NOTE (harness-correct reload): raw page.reload() drops the
    // __mountStudioForTest harness, so use the shared fx.reload() helper
    // (same session goto + remount, same origin so localStorage survives).
    await fx.reload();
    await gotoGenerateLayout(page);
    await expect(page.locator(BOXES)).toHaveCount(1, { timeout: 10000 });
    await expect(page.locator(PREVIEW)).toContainText("lighthouse", { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });
});
