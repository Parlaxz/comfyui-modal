// Visual Style Browser — Phase 5 (fake backend, bounded).
//
// Proves the Generate → Text style browser against the real frontend:
// browser/search/category/grid structure with the 12 catalog cards,
// search + category filtering, card selection (selected name, aria-pressed,
// effective prompt, localStorage persistence), None clearing, favorite
// toggling, and absence in Edit mode. No runs are submitted.
//
// Selector source: web/studio-playground.js (_renderStyleBrowser) +
// web/studio-style-catalog.js. The /comfymodal/sync/status 404 allowlist is
// the pre-existing shell↔fake-server gap (see studio-fake-postprocess.spec.mjs),
// unrelated to this workspace.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const STRIP = '[data-testid="studio-tool-strip"]';
const GEN_TOOL = '[data-testid="studio-tool-generate"]';
const EDIT_TOOL = '[data-testid="studio-tool-edit"]';
const TEXT_SUBTOOL = '[data-testid="studio-subtool-text"]';
const WF = '[data-testid="workflow-selector"]';
const BROWSER = '[data-testid="style-browser"]';
const SEARCH = '[data-testid="style-search"]';
const CATEGORY = '[data-testid="style-category"]';
const GRID = '[data-testid="style-grid"]';
const CARDS = '[data-testid^="style-card-"]';
const SEL_NAME = '[data-testid="style-selected-name"]';
const EFF = '[data-testid="style-effective-prompt"]';
const NONE_BTN = '[data-testid="style-none"]';
const STYLE_KEY = "comfymodal.studio.style.v1";
const NOIR_CARD = '[data-testid="style-card-1940s-film-noir-hard-shadows"]';
const NEON_CARD = '[data-testid="style-card-1980s-neon-night-city-lights"]';

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

// Generate → Text with a T2I workflow: the only shell where the style
// browser renders (see _renderStyleBrowser guards in studio-playground.js).
// The browser is a collapsed-by-default <details> accordion, so expand it
// before asserting on the inner search/grid/cards.
async function gotoGenerateText(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await page.locator(GEN_TOOL).click();
  await expect(page.locator(GEN_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(TEXT_SUBTOOL).click();
  await expect(page.locator(TEXT_SUBTOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
  await page.locator(WF).selectOption("wf_text2img");
  await expect(page.locator(WF)).toHaveValue("wf_text2img", { timeout: 10000 });
  await expect(page.locator('[data-testid="shelf-section"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator(BROWSER)).toBeVisible({ timeout: 10000 });
  const open = await page.locator(BROWSER).evaluate((n) => n.hasAttribute("open"));
  if (!open) await page.locator('[data-testid="style-browser-toggle"]').click();
  await expect(page.locator(GRID)).toBeVisible({ timeout: 10000 });
}

function visibleCardCount(page) {
  return page.evaluate(() => {
    const grid = document.querySelector('[data-testid="style-grid"]');
    if (!grid) return -1;
    return Array.prototype.filter.call(
      grid.children, (c) => c.style.display !== "none").length;
  });
}

function readStyleStore(page) {
  return page.evaluate((key) => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); }
    catch (_e) { return null; }
  }, STYLE_KEY);
}

test.describe("Visual Style Browser (fake backend)", () => {
  test("T0 — browser is a collapsed-by-default accordion", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
    await page.locator(GEN_TOOL).click();
    await page.locator(TEXT_SUBTOOL).click();
    await page.locator(WF).selectOption("wf_text2img");
    await expect(page.locator(BROWSER)).toBeVisible({ timeout: 10000 });
    const tag = await page.locator(BROWSER).evaluate((n) => n.tagName.toLowerCase());
    expect(tag).toBe("details");
    const open = await page.locator(BROWSER).evaluate((n) => n.hasAttribute("open"));
    expect(open).toBe(false);
    await expect(page.locator(GRID)).toBeHidden({ timeout: 10000 });
    await page.locator('[data-testid="style-browser-toggle"]').click();
    await expect(page.locator(GRID)).toBeVisible({ timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T1 — Generate → Text renders browser with 12 catalog cards", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(SEARCH)).toBeVisible();
    await expect(page.locator(CATEGORY)).toBeVisible();
    await expect(page.locator(GRID)).toBeVisible();
    await expect(page.locator(CARDS)).toHaveCount(12, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — search filters cards; clearing restores all", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(CARDS)).toHaveCount(12, { timeout: 10000 });
    // NOTE (selector/behavior drift vs the task brief): the brief says
    // typing "noir" leaves only 1980s-neon-night-city-lights visible, but
    // the catalog (web/studio-style-catalog.js) gives "noir" only to the
    // 1940s card (title + tags); the 1980s haystack (title/category/
    // description/tags) contains no "noir". The honest assertion is below.
    await page.locator(SEARCH).fill("noir");
    await expect.poll(() => visibleCardCount(page), { timeout: 10000 }).toBe(1);
    await expect(page.locator(NOIR_CARD)).toBeVisible();
    await expect(page.locator(NEON_CARD)).toBeHidden();
    await page.locator(SEARCH).fill("");
    await expect.poll(() => visibleCardCount(page), { timeout: 10000 }).toBe(12);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T3 — category filter shows only that category", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(CARDS)).toHaveCount(12, { timeout: 10000 });
    await page.locator(CATEGORY).selectOption("Decades");
    // Decades holds exactly the 1940s + 1980s cards in the catalog.
    await expect.poll(() => visibleCardCount(page), { timeout: 10000 }).toBe(2);
    await expect(page.locator(NOIR_CARD)).toBeVisible();
    await expect(page.locator(NEON_CARD)).toBeVisible();
    await expect(page.locator('[data-testid="style-card-dslr-photo-sharp-shallow-dof"]')).toBeHidden();
    await page.locator(CATEGORY).selectOption("All");
    await expect.poll(() => visibleCardCount(page), { timeout: 10000 }).toBe(12);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T4 — selecting a card sets name, aria-pressed, effective prompt, persists", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    const promptBox = page.locator('[data-testid="shelf-input-prompt"]');
    await expect(promptBox).toBeVisible({ timeout: 10000 });
    await promptBox.fill("a lighthouse at dawn");
    await page.locator(NEON_CARD).click();
    await expect(page.locator(NEON_CARD)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect(page.locator(SEL_NAME)).toContainText("1980s Neon Night", { timeout: 10000 });
    const eff = page.locator(EFF);
    await expect(eff).toContainText("a lighthouse at dawn", { timeout: 10000 });
    await expect(eff).toContainText("pink, cyan and orange neon", { timeout: 10000 });
    await expect.poll(async () => {
      const s = await readStyleStore(page);
      return s && s.selectedId;
    }, { timeout: 10000 }).toBe("1980s-neon-night-city-lights");
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T5 — None clears selection, effective line, persists empty", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(CARDS)).toHaveCount(12, { timeout: 10000 });
    await page.locator(NEON_CARD).click();
    await expect(page.locator(NEON_CARD)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await page.locator(NONE_BTN).click();
    await expect(page.locator(SEL_NAME)).toContainText("No style (plain prompt)", { timeout: 10000 });
    await expect(page.locator(EFF)).toHaveText("", { timeout: 10000 });
    await expect(page.locator(NEON_CARD)).toHaveAttribute("aria-pressed", "false", { timeout: 10000 });
    await expect.poll(async () => {
      const s = await readStyleStore(page);
      return s && s.selectedId;
    }, { timeout: 10000 }).toBe("");
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T6 — favorite star toggles color + localStorage", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(CARDS)).toHaveCount(12, { timeout: 10000 });
    const favId = "1980s-neon-night-city-lights";
    const fav = page.locator(`[data-testid="style-fav-${favId}"]`);
    await expect(fav).toBeVisible({ timeout: 10000 });
    await fav.click();
    await expect.poll(async () => {
      const s = await readStyleStore(page);
      return !!(s && Array.isArray(s.favorites) && s.favorites.indexOf(favId) !== -1);
    }, { timeout: 10000 }).toBe(true);
    // The fav button carries the global secondary-btn 150ms color transition,
    // so poll for the settled color rather than asserting mid-transition.
    await expect.poll(async () => {
      return fav.evaluate((n) => getComputedStyle(n).color);
    }, { timeout: 10000 }).toBe("rgb(232, 185, 62)");
    await fav.click();
    await expect.poll(async () => {
      const s = await readStyleStore(page);
      return !!(s && Array.isArray(s.favorites) && s.favorites.indexOf(favId) !== -1);
    }, { timeout: 10000 }).toBe(false);
    await expect.poll(async () => {
      return fav.evaluate((n) => getComputedStyle(n).color);
    }, { timeout: 10000 }).toBe("rgb(102, 102, 102)");
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T7 — style browser does NOT render in Edit mode", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await gotoGenerateText(page);
    await expect(page.locator(BROWSER)).toBeVisible({ timeout: 10000 });
    await page.locator(EDIT_TOOL).click();
    await expect(page.locator(EDIT_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect(page.locator(BROWSER)).toHaveCount(0, { timeout: 10000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });
});
