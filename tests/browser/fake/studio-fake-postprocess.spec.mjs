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

async function clickPostSubtool(page, subtool) {
  const btn = page.locator(`[data-testid="studio-subtool-${subtool}"]`);
  await expect(btn).toBeVisible({ timeout: 10000 });
  await btn.click();
  await expect(btn).toHaveAttribute("aria-pressed", "true", { timeout: 10000 });
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
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T2 — uploaded source renders; Exposure changes pixels", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
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

    // Preset apply keeps the workspace alive and updates the recipe.
    await page.locator('[data-testid="pp-looks"] button', { hasText: "Punchy" }).click();
    const recipe = await page.evaluate(() => window.__ppRecipe);
    expect(recipe.recipe.contrast).toBe(30);
    await expect(page.locator(PP_WS)).toBeVisible();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T5 — Color category expands color groups, collapses the rest", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);
    const outputBefore = await groupExpanded(page, "output");

    await clickPostSubtool(page, "color");
    // Routing lands: all four Color groups open.
    for (const id of ["color", "curves", "mixer", "grading"]) {
      await expect.poll(() => groupExpanded(page, id), { timeout: 10000 }).toBe("true");
    }
    // Groups outside the category collapse; output stays as the user left it.
    for (const id of ["light", "detail", "effects"]) {
      await expect.poll(() => groupExpanded(page, id), { timeout: 10000 }).toBe("false");
    }
    expect(await groupExpanded(page, "output")).toBe(outputBefore);
    await expect(page.locator(PP_WS)).toBeVisible();
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T6 — Detail category leaves only detail expanded; recipe untouched", async ({ page }) => {
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
    await expect.poll(() => groupExpanded(page, "color"), { timeout: 10000 }).toBe("true");
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);

    await clickPostSubtool(page, "detail");
    await expect.poll(() => groupExpanded(page, "detail"), { timeout: 10000 }).toBe("true");
    for (const id of ["light", "color", "curves", "mixer", "grading", "effects"]) {
      await expect.poll(() => groupExpanded(page, id), { timeout: 10000 }).toBe("false");
    }
    expect(await groupExpanded(page, "output")).toBe(outputBefore);
    // Category switches only change disclosure state — values survive.
    expect(await page.evaluate(() => JSON.stringify(window.__ppRecipe.recipe))).toBe(before);
    expect(await page.evaluate(() => window.__ppRecipe.recipe.exposure)).toBe(2);
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });

  test("T7 — Post Upscale is a real panel: method radios, scale, Run Upscale, no Auto", async ({ page }) => {
    const fx = await setupFakeTest(page);
    const bad = watch4xx(page);
    await openPostprocess(page);
    await uploadSource(page);

    // Post runs locally — no workflow execution from this view.
    const runBtn = page.locator('[data-testid="run-btn"]');
    await expect(runBtn).toBeVisible({ timeout: 10000 });
    await expect(runBtn).toBeDisabled({ timeout: 10000 });
    await expect(page.locator('[data-testid="shell-gate-reason"]')).toContainText("Post Processing runs locally");

    // Upscale category: real Phase 11 remote panel, not a placeholder.
    await clickPostSubtool(page, "upscale");
    const panel = page.locator('[data-testid="upscale-panel"]');
    await expect(panel).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="upscale-method-vosr2"]')).toBeVisible();
    await expect(page.locator('[data-testid="upscale-method-seedvr2"]')).toBeVisible();
    await expect(page.locator('[data-testid="upscale-scale"]')).toBeVisible();
    await expect(page.locator('[data-testid="upscale-run"]')).toContainText("Run Upscale");
    // Exactly two explicit methods — no third/Auto choice in the panel.
    await expect(panel).not.toContainText("Auto");
    // No placeholder notice: the finishing editor unmounts, the upscale
    // shell mounts instead.
    await expect(page.locator('[data-testid="shell-placeholder"]')).toHaveCount(0);
    await expect(page.locator(PP_WS)).toHaveCount(0);
    // Shared workflow run stays parked with a pointer to the panel button.
    await expect(runBtn).toBeDisabled({ timeout: 10000 });
    await expect(page.locator('[data-testid="shell-gate-reason"]')).toContainText("Run Upscale");
    await expect(page.locator('[data-testid="submenu-post-note"]')).toContainText("Run Upscale");
    expectOnlySync404(bad);
    await fx.assertNoConsoleErrors(ALLOW);
  });
});
