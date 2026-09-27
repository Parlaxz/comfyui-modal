// Modal Studio — persistence test against the deterministic fake backend.
//
// Seeds localStorage via page.addInitScript BEFORE any app script runs:
//   - comfymodal.studio.playground.v1        { presetId, featureId }
//   - comfymodal.studio.playground.results.v1  (production reads this as a
//     map keyed by `${presetId}::${featureId}` — see
//     web/studio-playground-state.js loadRunResult, NOT an array)
//
// Then loads the Studio and asserts the selection + persisted result are
// restored, and again after a reload (the ?session= query param survives).

import { test, expect } from "@playwright/test";
import { createSession, installConsoleGuard, getFakeState, openStudio } from "./helpers.mjs";

test("persisted playground selection and result restore across reload", async ({ page }) => {
  const sessionId = await createSession(page);
  const guard = installConsoleGuard(page);

  // Resolve the seeded preset id and a SERVED asset id from the engine.
  // The preset id is deterministic today ("preset_default"); the engine only
  // serves REGISTERED asset ids (fake-backend.mjs getAsset → 404 otherwise),
  // so use one of the deterministic seed-history assets (asset_seed_*) so the
  // canvas image actually resolves.
  const state = await getFakeState(page, sessionId);
  const seededPresetId =
    (state.presets && state.presets[0] && state.presets[0].id) || "preset_default";
  const servedAssetId = (state.assetIds && state.assetIds[0]) || "asset_seed_0";

  // Seed localStorage before the app scripts load.  addInitScript runs on
  // EVERY navigation, so the reload re-seeds the same state deterministically.
  await page.addInitScript(
    ({ presetId, imageUrl }) => {
      localStorage.setItem(
        "comfymodal.studio.playground.v1",
        JSON.stringify({ presetId, featureId: "txt2img" })
      );
      localStorage.setItem(
        "comfymodal.studio.playground.results.v1",
        JSON.stringify({
          [`${presetId}::txt2img`]: {
            id: "persisted-run-1",
            experimentId: "exp-persisted-1",
            imageUrl,
            outputPath: "",
            prompt: "persisted prompt",
            resolvedControls: {},
            timingStages: {},
          },
        })
      );
    },
    { presetId: seededPresetId, imageUrl: `/comfymodal/assets/${servedAssetId}` }
  );

  try {
    await openStudio(page, sessionId);

    // Selection restored: the backend selector hydrates from localStorage.
    await expect
      .poll(async () => page.locator('[data-testid="backend-select"]').inputValue(), {
        timeout: 15000,
        message: "preset selection should be restored from localStorage",
      })
      .toBe(seededPresetId);

    // Persisted result displayed: canvas image + metadata from the record.
    // The image URL uses a SERVED asset id, so the canvas image loads (and
    // the record identity is confirmed via the metadata prompt).
    const canvas = page.locator('[data-testid="canvas-output"]');
    await expect(canvas).toBeVisible({ timeout: 10000 });
    expect(await canvas.getAttribute("src")).toBe(`/comfymodal/assets/${servedAssetId}`);
    expect(await canvas.evaluate((img) => img.naturalWidth > 0)).toBe(true);
    await expect(page.locator(".comfymodal-studio-metadata-prompt")).toContainText("persisted prompt", {
      timeout: 10000,
    });

    // Reload — the session query param survives, addInitScript re-seeds.
    await openStudio(page, sessionId);
    await expect
      .poll(async () => page.locator('[data-testid="backend-select"]').inputValue(), {
        timeout: 15000,
        message: "preset selection should be restored after reload",
      })
      .toBe(seededPresetId);
    const canvasAfterReload = page.locator('[data-testid="canvas-output"]');
    await expect(canvasAfterReload).toBeVisible({ timeout: 10000 });
    expect(await canvasAfterReload.getAttribute("src")).toBe(`/comfymodal/assets/${servedAssetId}`);

    guard.assertNoErrors();
  } finally {
    guard.dispose();
  }
});
