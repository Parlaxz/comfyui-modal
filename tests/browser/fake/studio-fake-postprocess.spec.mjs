// Post Processing workspace (TinyLuma-based) — fake-backend e2e.
//
// T1: opening the tool never blanks the page (regression for the empty
//     studio-page report sent from the live app).
// T2: upload-driven path — source loads, moving Exposure changes rendered
//     pixels, recipe is exposed for the engine lane.
// T3: undo/redo, compare toggle, preset apply.
//
// NOTE: sourcing from a T2I run output is intentionally not covered here:
// run completion ("Run completed") is currently broken tree-wide in this
// working tree (pre-existing specs fail the same way), so these tests use
// the upload door — the other honest source path — until that is fixed.
// The /comfymodal/sync/status 404 allowlist below is the same pre-existing
// fake-server gap, unrelated to this workspace.

import { test, expect } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { setupFakeTest } from "./helpers.mjs";

const STRIP = '[data-testid="studio-tool-strip"]';
const PP_TOOL = '[data-testid="studio-tool-post"]';
const PP_WS = '[data-testid="pp-workspace"]';
const SOURCE_FIXTURE = fileURLToPath(new URL("./fixtures/studio-source.png", import.meta.url));
// Pre-existing shell↔fake-server gap: web/studio-shell.js polls
// `${apiBase}/sync/status`, which the fake server does not implement. It is
// timing-dependent (not tool-specific) and unrelated to this workspace — the
// module's only fetch is the opt-in PNG-metadata byte read. The console text
// carries no URL, so track 4xx URLs directly and assert sync/status is the
// only one; any other 4xx (fixture, module, image) fails the test.
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

async function openPostprocess(page) {
  await expect(page.locator(STRIP)).toBeVisible({ timeout: 10000 });
  await expect(page.locator(PP_TOOL)).toBeVisible({ timeout: 10000 });
  await page.locator(PP_TOOL).click();
  await expect(page.locator(PP_TOOL)).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
}

async function uploadSource(page) {
  const chooserP = page.waitForEvent("filechooser", { timeout: 10000 });
  await page.locator('[data-testid="pp-upload-empty"]').click();
  const chooser = await chooserP;
  await chooser.setFiles(SOURCE_FIXTURE);
  await expect(page.locator('[data-testid="pp-view"]')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('[data-testid="pp-filmstrip"] .pp-thumb')).toHaveCount(1, { timeout: 10000 });
  // First real render (requires the decoded image) publishes the recipe.
  await expect.poll(() => page.evaluate(() => !!window.__ppRecipe), { timeout: 15000 }).toBe(true);
}

async function viewSignature(page) {
  return page.evaluate(() => {
    const c = document.querySelector('[data-testid="pp-view"]');
    if (!c || !c.width) return null;
    const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
    let sr = 0, sg = 0, sb = 0;
    const n = d.length / 4;
    for (let i = 0; i < d.length; i += 16) { sr += d[i]; sg += d[i + 1]; sb += d[i + 2]; }
    const k = n / 4;
    return { w: c.width, h: c.height, r: Math.round(sr / k), g: Math.round(sg / k), b: Math.round(sb / k) };
  });
}

async function groupExpanded(page, id) {
  return page.evaluate((gid) => {
    const g = document.querySelector(`[data-testid="pp-inspector"] .pp-group[data-group="${gid}"]`);
    if (!g) return null;
    const head = g.querySelector(".pp-grouphead");
    return head ? head.getAttribute("aria-expanded") : null;
  }, id);
}

async function groupVisible(page, id) {
  return page.locator(`[data-testid="pp-inspector"] .pp-group[data-group="${id}"]`).isVisible();
}

async function clickPostSubtool(page, subtool) {
  // Phase-4 dedup: passive categories navigate via the canonical sidebar
  // grid (the top row keeps only Crop/Heal/Upscale modes).
  const grid = { adjust: "light", color: "color", detail: "detail", effects: "effects" };
  if (grid[subtool]) {
    await clickPpTab(page, grid[subtool]);
    return;
  }
  const btn = page.locator(`[data-testid="studio-subtool-${subtool}"]`);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(btn).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
}

async function clickPpTab(page, tab) {
  const btn = page.locator(`[data-testid="pp-sidebar"] [data-testid="pp-tab-${tab}"]`);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(btn).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
}

async function ppTabCount(page, tab) {
  return page.locator(`[data-testid="pp-sidebar"] [data-testid="pp-tab-${tab}"]`).count();
}

async function sectionVisible(page, sel) {
  return page.locator(`[data-testid="pp-sidebar"] ${sel}`).isVisible();
}

test.describe("Post Processing workspace (fake backend)", () => {
  test("T1 — tool opens without blanking the page", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    // The reported bug: studio-page rendered completely empty.
    const pageKids = await page.locator('[data-testid="studio-page"] > *').count();
    expect(pageKids).toBeGreaterThan(0);
    await expect(page.locator(PP_WS)).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="pp-toolbar"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-inspector"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-filmstrip"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-upload-empty"]')).toBeVisible();
    // Phase 4 corrective contract: the one engine's inspector is native to
    // the left rail while its same stage is the central image surface.
    await expect(page.locator('[data-testid="pp-sidebar"]')).toBeVisible();
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="pp-canvas"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-shell"]')).toHaveCount(0);
    // Phase-4 polish: the default Adjust view opens with its section tabs.
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tabs"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-light"]')).toHaveAttribute("aria-pressed", "true");
    // Oracle audit fix: the generation empty-state must not show beside the
    // engine stage — in Post the stage IS the image surface.
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="canvas-empty"]')).toBeHidden();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — uploaded source renders; Exposure changes pixels", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-slider-exposure"]')).toBeVisible();
    const before = await viewSignature(page);
    expect(before).toBeTruthy();

    const slider = page.locator('[data-testid="pp-slider-exposure"] input[type="range"]');
    await expect(slider).toBeVisible({ timeout: 10000 });
    await slider.fill("2");
    // fill() fires input+change in Chromium; wait for the re-render.
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && before && (now.r !== before.r || now.g !== before.g || now.b !== before.b);
    }, { timeout: 10000 }).toBe(true);

    const recipe = await page.evaluate(() => window.__ppRecipe);
    expect(recipe).toBeTruthy();
    expect(recipe.recipe.exposure).toBe(2);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T4 — edits survive a full playground remount", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    const base = await viewSignature(page);
    expect(base).toBeTruthy();
    await page.locator('[data-testid="pp-slider-exposure"] input[type="range"]').fill("2");
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && base && (now.r !== base.r || now.g !== base.g || now.b !== base.b);
    }, { timeout: 10000 }).toBe(true);
    const edited = await viewSignature(page);

    // Force a full Studio re-render (new workspace mount, same document).
    await page.locator('[data-testid="studio-tool-generate"]').click();
    await openPostprocess(page);
    await expect(page.locator('[data-testid="pp-view"]')).toBeVisible({ timeout: 15000 });
    // Recipe, slider position, and pixels all restored without re-upload.
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.exposure),
      { timeout: 15000 }).toBe(2);
    await expect(page.locator('[data-testid="pp-slider-exposure"] input[type="number"]')).toHaveValue("2");
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && edited && now.r === edited.r && now.g === edited.g && now.b === edited.b;
    }, { timeout: 15000 }).toBe(true);
    // Undo history survived the remount too.
    await page.locator('[data-testid="pp-undo"]').click();
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && base && now.r === base.r && now.g === base.g && now.b === base.b;
    }, { timeout: 10000 }).toBe(true);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T3 — undo/redo, compare toggle, preset apply", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    const base = await viewSignature(page);
    expect(base).toBeTruthy();

    // Brightness up (a mean-moving control), then undo returns to baseline.
    await page.locator('[data-testid="pp-slider-brightness"] input[type="range"]').fill("30");
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && base && (now.r !== base.r || now.g !== base.g || now.b !== base.b);
    }, { timeout: 10000 }).toBe(true);
    await page.locator('[data-testid="pp-undo"]').click();
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && base && now.r === base.r && now.g === base.g && now.b === base.b;
    }, { timeout: 10000 }).toBe(true);
    await page.locator('[data-testid="pp-redo"]').click();
    await expect.poll(async () => {
      const now = await viewSignature(page);
      return now && base && (now.r !== base.r || now.g !== base.g || now.b !== base.b);
    }, { timeout: 10000 }).toBe(true);
    // Contrast wires through to the recipe + marks the Light group edited
    // (contrast pivots around mid-gray, so it need not move the mean).
    await page.locator('[data-testid="pp-slider-contrast"] input[type="range"]').fill("40");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.contrast),
      { timeout: 10000 }).toBe(40);
    await expect(page.locator('[data-testid="pp-inspector"] .pp-group[data-group="light"]')).toHaveClass(/has-edits/);

    // Compare toggle shows the divider.
    await page.locator('[data-testid="pp-compare"]').click();
    await expect(page.locator('[data-testid="pp-compare-divider"]')).toBeVisible({ timeout: 5000 });

    // Preset apply (via the Looks tab) keeps the workspace alive and updates the recipe.
    await clickPpTab(page, "looks");
    await page.locator('[data-testid="pp-looks"] button', { hasText: "Punchy" }).click();
    const recipe = await page.evaluate(() => window.__ppRecipe);
    expect(recipe.recipe.contrast).toBe(30);
    await expect(page.locator(PP_WS)).toBeVisible();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T5 — Color shows the global grid; every section reachable, recipe untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    const before = await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe));
    const outputBefore = await groupExpanded(page, "output");

    await clickPostSubtool(page, "color");
    // ONE persistent grid across Post: all eleven panels, everywhere.
    for (const id of ["light", "color", "curves", "detail", "effects", "looks", "mixer", "grading", "lut", "histogram", "output"]) {
      await expect(page.locator(`[data-testid="pp-sidebar"] [data-testid="pp-tab-${id}"]`)).toBeVisible({ timeout: 10000 });
    }
    // Landing panel is Color: only the Color group shows.
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-color"]'))
      .toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect.poll(() => groupVisible(page, "color"), { timeout: 10000 }).toBe(true);
    for (const id of ["light", "curves", "mixer", "grading", "detail", "effects", "output"]) {
      await expect.poll(() => groupVisible(page, id), { timeout: 10000 }).toBe(false);
    }
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"]'), { timeout: 10000 }).toBe(false);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-histogram"]'), { timeout: 10000 }).toBe(false);

    // One visible section at a time — walk every tab, recipe never moves.
    await clickPpTab(page, "curves");
    await expect.poll(() => groupVisible(page, "curves"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "color"), { timeout: 10000 }).toBe(false);
    await clickPpTab(page, "mixer");
    await expect.poll(() => groupVisible(page, "mixer"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "curves"), { timeout: 10000 }).toBe(false);
    await clickPpTab(page, "grading");
    await expect.poll(() => groupVisible(page, "grading"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "mixer"), { timeout: 10000 }).toBe(false);
    await clickPpTab(page, "lut");
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"]'), { timeout: 10000 }).toBe(true);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"] [data-pp-section="lut"]'), { timeout: 10000 }).toBe(true);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"] [data-pp-section="looks"]'), { timeout: 10000 }).toBe(false);
    await expect.poll(() => groupVisible(page, "grading"), { timeout: 10000 }).toBe(false);
    await clickPpTab(page, "histogram");
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-histogram"]'), { timeout: 10000 }).toBe(true);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"]'), { timeout: 10000 }).toBe(false);
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    // Back to the Color panel; the Output disclosure stays as the user left it.
    await clickPpTab(page, "color");
    expect(await groupExpanded(page, "output")).toBe(outputBefore);
    await expect(page.locator(PP_WS)).toBeVisible();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T6 — Detail/Effects keep coherent views under the persistent grid; recipe untouched", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    // A real recipe value to guard against switch-driven resets.
    await page.locator('[data-testid="pp-slider-exposure"] input[type="range"]').fill("2");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.exposure),
      { timeout: 10000 }).toBe(2);
    const before = await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe));
    const outputBefore = await groupExpanded(page, "output");

    await clickPostSubtool(page, "color");
    await expect.poll(() => groupVisible(page, "color"), { timeout: 10000 }).toBe(true);
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);

    // Detail: single coherent group + output under the same persistent grid.
    await clickPostSubtool(page, "detail");
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tabs"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-detail"]'))
      .toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect.poll(() => groupVisible(page, "detail"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "output"), { timeout: 10000 }).toBe(true);
    for (const id of ["light", "color", "curves", "mixer", "grading", "effects"]) {
      await expect.poll(() => groupVisible(page, id), { timeout: 10000 }).toBe(false);
    }
    // Effects: same contract — one group under the persistent grid.
    await clickPostSubtool(page, "effects");
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tabs"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-effects"]'))
      .toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect.poll(() => groupVisible(page, "effects"), { timeout: 10000 }).toBe(true);
    for (const id of ["light", "color", "detail"]) {
      await expect.poll(() => groupVisible(page, id), { timeout: 10000 }).toBe(false);
    }
    expect(await groupExpanded(page, "output")).toBe(outputBefore);
    // Category switches only change disclosure state — values survive.
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    expect(await page.evaluate(() => window.__ppRecipe.recipe.exposure)).toBe(2);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T8 — subtool views preserve the recipe, remember tabs, keep the canvas central", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    await page.locator('[data-testid="pp-slider-exposure"] input[type="range"]').fill("2");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.exposure),
      { timeout: 10000 }).toBe(2);
    // A Mixer value so the Color tab memory has something to protect.
    await clickPostSubtool(page, "color");
    await clickPpTab(page, "mixer");
    await page.locator('[data-testid="pp-slider-red-h"] input[type="range"]').fill("20");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.mixer[0].h),
      { timeout: 10000 }).toBe(20);
    const before = await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe));

    // Adjust shows only its Light section; the Color work is untouched.
    // The grid is global now: Color panels stay visible as one-click targets.
    await clickPostSubtool(page, "adjust");
    await expect.poll(() => groupVisible(page, "light"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "output"), { timeout: 10000 }).toBe(false);
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-light"]'))
      .toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    await expect(page.locator('[data-testid="pp-sidebar"] [data-testid="pp-tab-curves"]')).toBeVisible({ timeout: 10000 });
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="pp-canvas"]')).toBeVisible();

    // Back to Mixer with ONE direct panel click (no Color parent first):
    // explicit panel choice wins, value and recipe intact.
    await clickPpTab(page, "mixer");
    await expect.poll(() => groupVisible(page, "mixer"), { timeout: 10000 }).toBe(true);
    await expect(page.locator('[data-testid="pp-slider-red-h"] input[type="number"]')).toHaveValue("20");
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="pp-canvas"]')).toBeVisible();

    // Effects keeps its coherent single-group view.
    await clickPostSubtool(page, "effects");
    await expect.poll(() => groupVisible(page, "effects"), { timeout: 10000 }).toBe(true);
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="pp-canvas"]')).toBeVisible();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T7 — RUN stays disabled in Post; Upscale is an honest placeholder", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);

    // Post runs locally — no workflow execution from this view.
    const runBtn = page.locator('[data-testid="run-btn"]');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await expect(runBtn).toBeDisabled({ timeout: 10000 });
    await expect(page.locator('[data-testid="shell-gate-reason"]')).toContainText("Post Processing runs locally");

    // Upscale category: editor unmounts, placeholder notice + disabled run.
    await clickPostSubtool(page, "upscale");
    await expect(page.locator('[data-testid="shell-placeholder"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="shell-placeholder"]')).toContainText("Upscale");
    await expect(page.locator(PP_WS)).toHaveCount(0);
    await expect(runBtn).toBeDisabled({ timeout: 10000 });
    await expect(page.locator('[data-testid="shell-gate-reason"]')).toContainText("Upscale arrives in a later phase");
    await expect(page.locator('[data-testid="submenu-post-note"]')).toContainText("Upscale arrives in a later phase");
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T9 — Adjust tab matrix, value persistence across tabs, sticky action row", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);

    // The global grid is bounded and Post-specific: eleven panels, everywhere.
    for (const id of ["light", "color", "curves", "detail", "effects", "looks", "mixer", "grading", "lut", "histogram", "output"]) {
      await expect(page.locator(`[data-testid="pp-sidebar"] [data-testid="pp-tab-${id}"]`)).toBeVisible({ timeout: 10000 });
    }

    // Adjust→Light→Exposure change→Looks→preset→back to Light (values persist).
    await page.locator('[data-testid="pp-slider-exposure"] input[type="range"]').fill("1.5");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.exposure),
      { timeout: 10000 }).toBe(1.5);
    await clickPpTab(page, "looks");
    await expect.poll(() => groupVisible(page, "light"), { timeout: 10000 }).toBe(false);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"] [data-pp-section="looks"]'), { timeout: 10000 }).toBe(true);
    // The 1.5 exposure survives the Light→Looks travel (tabs never touch values).
    expect(await page.evaluate(() => window.__ppRecipe.recipe.exposure)).toBe(1.5);
    await page.locator('[data-testid="pp-looks"] button', { hasText: "Clean Portrait" }).click();
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.texture),
      { timeout: 10000 }).toBe(-18);
    // Engine semantics (unchanged): a preset replaces the whole look, so the
    // post-preset recipe is the new baseline that tab travel must preserve.
    const postPreset = await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe));
    await clickPpTab(page, "output");
    await expect.poll(() => groupVisible(page, "output"), { timeout: 10000 }).toBe(true);
    await clickPpTab(page, "histogram");
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-histogram"]'), { timeout: 10000 }).toBe(true);
    await clickPpTab(page, "light");
    await expect.poll(() => groupVisible(page, "light"), { timeout: 10000 }).toBe(true);
    // Post-preset values survived the full tab travel.
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(postPreset);
    expect(await page.evaluate(() => window.__ppRecipe.recipe.texture)).toBe(-18);

    // Action row: the utility set stays; duplicates moved to their owners.
    for (const id of ["pp-undo", "pp-redo", "pp-compare", "pp-save", "pp-export"]) {
      await expect(page.locator(`[data-testid="pp-sidebar"] [data-testid="${id}"]`)).toBeVisible({ timeout: 10000 });
    }
    // Compare stays in the row: the Studio top-bar Compare is a History A/B
    // picker, a different system from the engine before/after.
    for (const id of ["pp-crop", "pp-heal", "pp-wb"]) {
      await expect(page.locator(`[data-testid="pp-sidebar"] [data-testid="${id}"]`)).toBeHidden({ timeout: 10000 });
    }
    // Real owners still exist: WB picker in the Color panel, Crop/Heal subtools.
    await clickPostSubtool(page, "color");
    await expect(page.locator('[data-testid="pp-inspector"] button', { hasText: "WB picker" })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="studio-subtool-crop"]')).toBeVisible();
    await expect(page.locator('[data-testid="studio-subtool-heal"]')).toBeVisible();

    // Save confirms locally; Export renders and names the edited file.
    await clickPostSubtool(page, "adjust");
    await page.locator('[data-testid="pp-save"]').click();
    await expect(page.locator('[data-testid="pp-status"]')).toContainText("saved locally", { timeout: 10000 });
    await page.locator('[data-testid="pp-export"]').click();
    await expect(page.locator('[data-testid="pp-status"]')).toContainText("Exported", { timeout: 15000 });
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T10 — one panel click reaches any panel; modes stay separate; values hold", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    await page.locator('[data-testid="pp-slider-exposure"] input[type="range"]').fill("1.5");
    await expect.poll(() => page.evaluate(() => window.__ppRecipe && window.__ppRecipe.recipe.exposure),
      { timeout: 10000 }).toBe(1.5);
    // Dedup contract: the top row keeps ONLY interaction modes — no passive
    // Adjust/Color/Detail/Effects buttons may exist there anymore.
    for (const sub of ["crop", "heal", "upscale"]) {
      await expect(page.locator(`[data-testid="studio-subtool-${sub}"]`)).toBeVisible({ timeout: 10000 });
    }
    for (const sub of ["adjust", "color", "detail", "effects"]) {
      expect(await page.locator(`[data-testid="studio-subtool-${sub}"]`).count()).toBe(0);
    }
    const panelPressed = (tab) => page.locator(`[data-testid="pp-sidebar"] [data-testid="pp-tab-${tab}"]`);

    // Light → Histogram: same category, exactly one panel click.
    await clickPpTab(page, "histogram");
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-histogram"]'), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "light"), { timeout: 10000 }).toBe(false);
    await expect(panelPressed("histogram")).toHaveAttribute("aria-pressed", "true");

    const before = await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe));

    // Histogram → Curves: cross-category in ONE panel click, no Color first.
    await clickPpTab(page, "curves");
    await expect.poll(() => groupVisible(page, "curves"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-histogram"]'), { timeout: 10000 }).toBe(false);
    await expect(panelPressed("curves")).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });

    // Curves → LUT → Light: hops across categories, recipe identical throughout.
    await clickPpTab(page, "lut");
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"] [data-pp-section="lut"]'), { timeout: 10000 }).toBe(true);
    await expect.poll(() => groupVisible(page, "curves"), { timeout: 10000 }).toBe(false);
    await clickPpTab(page, "light");
    await expect.poll(() => groupVisible(page, "light"), { timeout: 10000 }).toBe(true);
    await expect.poll(() => sectionVisible(page, '[data-testid="pp-looks"]'), { timeout: 10000 }).toBe(false);
    await expect(panelPressed("light")).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);

    // The canvas stays central and no second workspace ever mounts.
    await expect(page.locator('[data-testid="canvas-area"] [data-testid="pp-canvas"]')).toBeVisible();
    await expect(page.locator('[data-testid="pp-shell"]')).toHaveCount(0);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });
});
