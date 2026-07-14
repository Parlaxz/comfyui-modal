// Modal Studio — Playground E2E Tests
//
// Tests Playground behavior using the mock API.
// Mock is installed BEFORE navigation per isolation contract.
// Uses fresh Playwright Test page/context (never MCP/shared session).

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  createOwnerPrefix,
  createOwnedRecords,
  createOwnedSnapshotAndPresets,
  openStudio,
} from "./studio-fixtures.mjs";
import { installStudioMockApi } from "./studio-mock-api.mjs";

const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// ── Helpers ────────────────────────────────────────────────────────────────

async function waitVisible(locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

async function selectBackendPreset(page, presetLabel) {
  const select = page.locator('[data-testid="backend-select"]');
  await select.waitFor({ state: "visible", timeout: 15000 });
  await select.selectOption(presetLabel);
  await page.waitForTimeout(300);
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Studio Playground", () => {
  let api;

  test.beforeEach(async ({ page }) => {
    api = await installStudioMockApi(page);
  });

  // ── Test 1: Full run lifecycle ──────────────────────────────────────────

  test("1. full run lifecycle with snapshot, preset, run, and completion", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      expect(owned.snapshotIds).toHaveLength(1);
      expect(owned.presetIds).toHaveLength(1);
      const presetId = owned.presetIds[0];

      // Open Studio first, THEN install guard — excludes ComfyUI startup noise
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      guard = installConsoleGuard(page);

      // Perform all Playground interactions under guard
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("a majestic cat in space");

      // Assert no unhandled mock calls before run
      api.assertNoUnhandledCalls();

      const runBtn = page.locator('[data-testid="run-btn"]');
      await runBtn.waitFor({ state: "visible", timeout: 10000 });
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      const canvasOutput = page.locator('[data-testid="canvas-output"]');
      await expect(canvasOutput).toBeVisible({ timeout: 30000 });

      const src = await canvasOutput.getAttribute("src");
      expect(src).toBeTruthy();
      expect(src).toContain("/comfymodal/");

      await expect(runBtn).toBeEnabled({ timeout: 5000 });
      expect((await runBtn.textContent()).trim()).toBe("Run");

      const submitted = api.lastRunRequest;
      expect(submitted).toBeTruthy();
      expect(submitted.controls).toBeTruthy();
      expect(submitted.controls.prompt).toBe("a majestic cat in space");
      expect(submitted.presetId).toBe(presetId);

      // Timing card with End-to-End Total and Sampling
      const timingCard = page.locator('[data-testid="timing-card"]');
      await expect(timingCard).toBeVisible({ timeout: 10000 });
      await expect(timingCard.locator(".comfymodal-studio-timing-e2e")).toBeVisible({ timeout: 5000 });

      const stageTags = timingCard.locator(".comfymodal-studio-timing-tag");
      const allTagTexts = await stageTags.allTextContents();
      expect(allTagTexts.some((t) => t.includes("Sampling"))).toBeTruthy();

      // Expand Advanced diagnostics
      await page.locator('[data-testid="advanced-toggle"]').click();
      const advancedPanel = page.locator(".comfymodal-studio-metadata-advanced");
      await expect(advancedPanel).toBeVisible({ timeout: 5000 });
      expect((await advancedPanel.textContent()).length).toBeGreaterThan(0);

      // Assert pipeline under test emitted no errors
      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: HTTP submit error keeps Run enabled ─────────────────────────

  test("2. HTTP submit error leaves Run enabled and shows error message", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);

      api.failNext("POST", "/studio/run", 500, {
        status: "error",
        message: "Server overloaded, please retry",
      });

      const runBtn = page.locator('[data-testid="run-btn"]');
      await runBtn.waitFor({ state: "visible", timeout: 10000 });
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await expect(page.locator(".comfymodal-studio-disabled-reason")).toBeVisible({ timeout: 5000 });

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 3: forceFailed experiment shows error ──────────────────────────

  test("3. forceFailed experiment shows error state", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      await expect.poll(() => api.state.experiments.size, { timeout: 5000 }).toBeGreaterThan(0);
      // expect.poll guarantees ≥1 experiment — unconditionally set behavior
      api.setExperimentBehavior([...api.state.experiments.keys()][0], {
        forceFailed: true, terminalPoll: 3,
      });

      await expect(runBtn).toBeEnabled({ timeout: 45000 });
      const text = await page.locator(".comfymodal-studio-disabled-reason").textContent();
      expect(text.toLowerCase()).toContain("mock failure");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 4: Missing asset does not fabricate canvas image ───────────────

  test("4. completed event without asset does not show canvas image", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      await expect.poll(() => api.state.experiments.size, { timeout: 5000 }).toBeGreaterThan(0);
      const expIds = [...api.state.experiments.keys()];
      if (expIds.length > 0) {
        api.setExperimentBehavior(expIds[0], { terminalPoll: 3, omitOutputs: true });
      }

      await expect(runBtn).toBeEnabled({ timeout: 45000 });
      await expect(page.locator('[data-testid="canvas-output"]')).toHaveCount(0, { timeout: 5000 });

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 5: Archived preset disappears, unrelated remains ───────────────

  test("5. archived test preset disappears, unrelated preset remains", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const testPresetId = owned.presetIds[0];

      const snapRes = await page.evaluate(async () => {
        const r = await fetch("/comfymodal/studio/snapshots", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: "unrelated-snapshot", compatibleFeatures: ["txt2img"],
            graphJson: {}, apiPromptJson: {},
            nodeBindings: {}, outputNodeId: "1", source: "manual",
          }),
        });
        return (await r.json()).snapshot;
      });
      expect(snapRes.id).toBeTruthy();

      const presRes = await page.evaluate(async (snapId) => {
        const r = await fetch("/comfymodal/studio/presets", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            label: "unrelated-preset", snapshotId: snapId,
            compatibleFeatures: ["txt2img"], defaults: { seed: 99, steps: 20 },
          }),
        });
        return (await r.json()).preset;
      }, snapRes.id);
      expect(presRes.id).toBeTruthy();

      const delRes = await page.evaluate(async (id) => {
        const r = await fetch(`/comfymodal/studio/presets/${encodeURIComponent(id)}`, { method: "DELETE" });
        return r.ok;
      }, testPresetId);
      expect(delRes).toBeTruthy();

      await page.reload();
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      const options = await page.locator('[data-testid="backend-select"] option').allTextContents();
      expect(options.some((t) => t.includes(prefix))).toBeFalsy();
      expect(options.some((t) => t.includes("unrelated-preset"))).toBeTruthy();

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 6: Stalled experiment 5-minute timeout ─────────────────────────

  test("6. stalled experiment reaches 5-minute timeout", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      await page.clock.install();

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      const expIds = [...api.state.experiments.keys()];
      if (expIds.length > 0) {
        api.setExperimentBehavior(expIds[0], { terminalPoll: 999 });
      }

      await page.clock.fastForward(5 * 60 * 1000 + 4000);
      await expect(runBtn).toBeEnabled({ timeout: 5000 });

      const msgText = await page.locator(".comfymodal-studio-disabled-reason").textContent();
      expect(msgText).toContain("timed out after 5 minutes");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 7: Navigating away stops polling ───────────────────────────────

  test("7. navigating away stops polling", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      await page.clock.install();

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      await page.clock.fastForward(4000);

      const calls = () => api.state.calls.filter(
        (c) => c.pathname && c.pathname.includes("/experiments/")
      ).length;

      expect(calls()).toBeGreaterThan(0);

      await page.getByRole("button", { name: "History", exact: true }).click();

      const afterNav = calls();
      await page.clock.fastForward(12000);
      await page.clock.fastForward(0);
      expect(calls()).toBe(afterNav);

      api.assertNoUnhandledCalls();
    } finally {
      // no guard.assertNoErrors
    }
  });

  // ── Test 8: Console/page errors during Playground interaction ───────────
  //
  // Install console guard AFTER Studio is open and the control panel is
  // visible, so ComfyUI startup noise is excluded.  Perform a small
  // Playground interaction, then assert no console.errors or pageerrors
  // were emitted by the pipeline under test.

  test("8. console and page errors are guarded and disposed", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      // Open Studio first — all ComfyUI startup noise happens before guard
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Install guard AFTER startup — only captures Playground interactions
      const guard = installConsoleGuard(page);

      // Perform a small Playground interaction: select preset, switch control
      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      // Verify no console.error or pageerror occurred during interaction
      guard.assertNoErrors();
      api.assertNoUnhandledCalls();

      guard.dispose();
      expect(Array.isArray(guard.pageErrors)).toBe(true);
    } finally {
      // guard is already disposed above
    }
  });

  // ── Test 9: Reload restores last run from localStorage ──────────────────
  //
  // Unlike test 1 which uses server-side recent runs, this test clears the
  // mock API's in-memory history before reload to prove the run identity is
  // persisted client-side in localStorage and survives when server data is
  // unavailable.

  test("9. reload restores selection, controls, canvas image, and run metadata from localStorage", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      // Phase 1: first visit — run a preset to completion
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Clear localStorage before starting to ensure no leftover state
      await page.evaluate(() => localStorage.clear());

      await selectBackendPreset(page, presetId);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("persistent cat");

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      const canvasOutput = page.locator('[data-testid="canvas-output"]');
      await expect(canvasOutput).toBeVisible({ timeout: 30000 });
      const firstImageSrc = await canvasOutput.getAttribute("src");
      expect(firstImageSrc).toBeTruthy();
      expect(firstImageSrc).toContain("/comfymodal/");

      // Verify metadata section is populated (timing card)
      const timingCard = page.locator('[data-testid="timing-card"]');
      await expect(timingCard).toBeVisible({ timeout: 10000 });

      // Verify that run result data was written to localStorage
      const localRunResult = await page.evaluate(() => {
        const raw = localStorage.getItem("comfymodal.studio.playground.results.v1");
        if (!raw) return null;
        try { return JSON.parse(raw); } catch { return null; }
      });
      expect(localRunResult).toBeTruthy();
      const resultKeys = localRunResult ? Object.keys(localRunResult) : [];
      expect(resultKeys.length).toBeGreaterThanOrEqual(1);
      const matchingKey = resultKeys.find(function (k) { return k.startsWith(presetId); });
      expect(matchingKey).toBeTruthy();
      const stored = localRunResult[matchingKey];
      expect(stored).toBeTruthy();
      expect(stored.imageUrl).toBe(firstImageSrc);

      // Phase 2: wipe mock API history so reload cannot restore from server
      api.state.history.length = 0;

      await page.reload();
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Verify same preset is selected
      const selectVal = await page.locator('[data-testid="backend-select"]').inputValue();
      expect(selectVal).toBe(presetId);

      // Verify canvas shows the same image (src matches what we captured)
      const restoredCanvas = page.locator('[data-testid="canvas-output"]');
      await expect(restoredCanvas).toBeVisible({ timeout: 15000 });
      const restoredSrc = await restoredCanvas.getAttribute("src");
      expect(restoredSrc).toBe(firstImageSrc);

      // Verify timing/metadata section is restored
      const restoredTiming = page.locator('[data-testid="timing-card"]');
      await expect(restoredTiming).toBeVisible({ timeout: 10000 });

      // Verify controls are populated (prompt field has the value we set)
      const promptVal = await page.locator('[data-testid="input-prompt"]').inputValue();
      expect(promptVal).toBe("persistent cat");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 10: Deleted preset fallback from localStorage ──────────────────
  //
  // Verifies that when a persisted-and-run preset is deleted on the server,
  // the next reload safely selects another runnable preset or shows the
  // empty state — no dangling selection to a deleted preset.

  test("10. deleted preset falls back to another runnable preset or empty state", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      // Create TWO presets so there is a fallback
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 2, owned);
      const presetA = owned.presetIds[0];
      const presetB = owned.presetIds[1];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Clear localStorage to start fresh
      await page.evaluate(() => localStorage.clear());

      // Select preset A, run it to persist its selection + result
      await selectBackendPreset(page, presetA);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("test A");

      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 30000 });

      // Reload — verify preset A is restored (selection and image)
      await page.reload();
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      let selectVal = await page.locator('[data-testid="backend-select"]').inputValue();
      expect(selectVal).toBe(presetA);

      // Verify that localStorage has the run result for preset A
      const localBefore = await page.evaluate(() => {
        const raw = localStorage.getItem("comfymodal.studio.playground.results.v1");
        return raw ? Object.keys(JSON.parse(raw)) : [];
      });
      expect(localBefore.some(function (k) { return k.startsWith(presetA); })).toBe(true);

      // Now delete preset A (archive via API)
      await page.evaluate(async (id) => {
        await fetch(`/comfymodal/studio/presets/${encodeURIComponent(id)}`, { method: "DELETE" });
      }, presetA);

      // Reload — should now fall back to another preset or empty state
      await page.reload();
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      selectVal = await page.locator('[data-testid="backend-select"]').inputValue();

      // Deleted preset A must NOT be selected — no dangling selection
      expect(selectVal).not.toBe(presetA);

      if (selectVal === presetB) {
        // If auto-selected preset B, canvas should show empty (no run yet)
        const canvasOutput = page.locator('[data-testid="canvas-output"]');
        const hasCanvas = await canvasOutput.isVisible().catch(() => false);
        expect(hasCanvas).toBe(false);
      } else if (selectVal === "") {
        // Empty state — controls area should show "select a preset" card
        await expect(page.locator(".comfymodal-studio-card")).toBeVisible({ timeout: 5000 });
      }

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 11: Per-preset run preview independence ─────────────────────────
  //
  // Verifies that when switching between presets that have both had a
  // successful run, each preset's last run preview (image + metadata) is
  // independently preserved and restored.  Checks metadata source text
  // (which contains the preset ID) to distinguish which preset's run is
  // currently displayed.

  test("11. switching presets preserves independent run previews", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 2, owned);
      const presetA = owned.presetIds[0];
      const presetB = owned.presetIds[1];

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Clear localStorage to start fresh
      await page.evaluate(() => localStorage.clear());

      // Helper: read the metadata-source text (shows presetLabel or presetId)
      async function getMetadataSourceText() {
        const el = page.locator(".comfymodal-studio-metadata-source");
        const visible = await el.isVisible().catch(() => false);
        if (!visible) return null;
        return (await el.textContent()).trim();
      }

      // ── Phase 1: Run with preset A ──
      await selectBackendPreset(page, presetA);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("run A prompt");

      let runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 30000 });

      // Verify metadata for A shows preset A's ID
      let sourceText = await getMetadataSourceText();
      expect(sourceText).toBeTruthy();
      expect(sourceText).toContain(presetA);

      // ── Phase 2: Switch to preset B and run ──
      await selectBackendPreset(page, presetB);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));
      await page.locator('[data-testid="input-prompt"]').fill("run B prompt");

      runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 30000 });

      // Verify metadata for B shows preset B's ID
      sourceText = await getMetadataSourceText();
      expect(sourceText).toBeTruthy();
      expect(sourceText).toContain(presetB);

      // ── Phase 3: Switch back to preset A ──
      await selectBackendPreset(page, presetA);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      // Canvas should show an image (from A's persisted run)
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 15000 });

      // Metadata should reflect preset A's run
      sourceText = await getMetadataSourceText();
      expect(sourceText).toBeTruthy();
      expect(sourceText).toContain(presetA);

      // ── Phase 4: Switch back to preset B ──
      await selectBackendPreset(page, presetB);
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      // Canvas should show an image (from B's persisted run)
      await expect(page.locator('[data-testid="canvas-output"]')).toBeVisible({ timeout: 15000 });

      // Metadata should reflect preset B's run (not A's)
      sourceText = await getMetadataSourceText();
      expect(sourceText).toBeTruthy();
      expect(sourceText).toContain(presetB);

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 12: Preset defaults — width/height ─────────────────────────────
  //
  // Verifies that width and height render as visible, enabled numeric
  // inputs reflecting the preset's fixture defaults (width 768, height 512).
  // After the async preset hydrates and sets _currentPreset, clicking the
  // active feature tab triggers a re-render so the sync hydration block
  // picks up preset defaults.

  test("12. preset defaults — width and height render as visible numeric controls with saved defaults", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create snapshot with nodeBindings for width and height so they show
      const snapPayload = {
        name: prefix + "-snap-wh",
        compatibleFeatures: ["txt2img"],
        graphJson: {},
        apiPromptJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "" } } },
        nodeBindings: {
          prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
          output: { kind: "output", nodeId: "2" },
          seed: { kind: "widget", nodeId: "3", widgetName: "seed" },
          steps: { kind: "widget", nodeId: "3", widgetName: "steps" },
          guidance: { kind: "widget", nodeId: "3", widgetName: "cfg" },
          denoise: { kind: "widget", nodeId: "3", widgetName: "denoise" },
          sampler: { kind: "widget", nodeId: "3", widgetName: "sampler_name" },
          scheduler: { kind: "widget", nodeId: "3", widgetName: "scheduler" },
          width: { kind: "widget", nodeId: "3", widgetName: "width" },
          height: { kind: "widget", nodeId: "3", widgetName: "height" },
        },
        outputNodeId: "2",
        source: "manual",
      };

      const snapRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/snapshots", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).snapshot;
      }, snapPayload);
      expect(snapRes.id).toBeTruthy();
      owned.snapshotIds.push(snapRes.id);

      const presPayload = {
        label: prefix + "-preset-wh",
        snapshotId: snapRes.id,
        compatibleFeatures: ["txt2img"],
        defaults: { width: 768, height: 512, seed: 42, steps: 20, guidance: 7, denoise: 1.0, sampler: "euler", scheduler: "normal" },
      };
      const presRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/presets", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).preset;
      }, presPayload);
      expect(presRes.id).toBeTruthy();
      owned.presetIds.push(presRes.id);
      const presetId = presRes.id;

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);

      // Wait for async preset hydration to set _currentPreset, then click
      // the active feature tab to trigger a re-render so the sync hydration
      // block correctly merges preset defaults into _hydratedControls.
      await page.waitForSelector('[data-testid="input-width"]', { timeout: 10000 });
      await page.locator('[data-testid="feature-tab-txt2img"]').click();
      await page.waitForTimeout(500);

      // Width: visible, enabled, numeric input with fixture default "768"
      const widthInput = page.locator('[data-testid="input-width"]');
      await expect(widthInput).toBeVisible({ timeout: 10000 });
      await expect(widthInput).toBeEnabled();
      expect(await widthInput.evaluate((el) => el.tagName)).toBe("INPUT");
      expect(await widthInput.getAttribute("type")).toBe("number");
      expect(await widthInput.inputValue()).toBe("768");

      // Height: visible, enabled, numeric input with fixture default "512"
      const heightInput = page.locator('[data-testid="input-height"]');
      await expect(heightInput).toBeVisible({ timeout: 10000 });
      await expect(heightInput).toBeEnabled();
      expect(await heightInput.evaluate((el) => el.tagName)).toBe("INPUT");
      expect(await heightInput.getAttribute("type")).toBe("number");
      expect(await heightInput.inputValue()).toBe("512");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 13: Preset defaults — enum schemas (sampler/scheduler) ─────────
  //
  // Verifies that sampler and scheduler render as enabled <select> elements
  // when the preset carries an enum control schema, with the fixture
  // defaults selected (sampler dpmpp_2m, scheduler karras, denoise 0).
  // After the async preset hydrates and sets _currentPreset, clicking the
  // active feature tab triggers a re-render so the sync hydration block
  // picks up preset defaults.

  test("13. preset defaults — with enum schemas, sampler and scheduler render enabled selects with saved dpmpp_2m/karras selected and options present; denoise 0 remains 0", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Snapshot with enum controlSchemas for sampler and scheduler
      const snapPayload = {
        name: prefix + "-snap-enum",
        compatibleFeatures: ["txt2img"],
        graphJson: {},
        apiPromptJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "" } } },
        nodeBindings: {
          prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
          output: { kind: "output", nodeId: "2" },
          seed: { kind: "widget", nodeId: "3", widgetName: "seed" },
          steps: { kind: "widget", nodeId: "3", widgetName: "steps" },
          guidance: { kind: "widget", nodeId: "3", widgetName: "cfg" },
          denoise: { kind: "widget", nodeId: "3", widgetName: "denoise" },
          sampler: { kind: "widget", nodeId: "3", widgetName: "sampler_name" },
          scheduler: { kind: "widget", nodeId: "3", widgetName: "scheduler" },
        },
        outputNodeId: "2",
        source: "manual",
        controlSchemas: {
          sampler: {
            schemaResolved: true,
            kind: "enum",
            options: ["euler", "dpmpp_2m", "dpmpp_3m_sde", "ddim", "uni_pc"],
          },
          scheduler: {
            schemaResolved: true,
            kind: "enum",
            options: ["normal", "karras", "exponential", "sgm_uniform"],
          },
        },
      };

      const snapRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/snapshots", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).snapshot;
      }, snapPayload);
      expect(snapRes.id).toBeTruthy();
      owned.snapshotIds.push(snapRes.id);

      const presPayload = {
        label: prefix + "-preset-enum",
        snapshotId: snapRes.id,
        compatibleFeatures: ["txt2img"],
        defaults: { sampler: "dpmpp_2m", scheduler: "karras", denoise: 0, seed: 42, steps: 20, guidance: 7 },
      };
      const presRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/presets", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).preset;
      }, presPayload);
      expect(presRes.id).toBeTruthy();
      owned.presetIds.push(presRes.id);
      const presetId = presRes.id;

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);

      // Wait for async preset hydration to set _currentPreset, then click
      // the active feature tab to trigger a re-render so the sync hydration
      // block correctly merges preset defaults into _hydratedControls.
      await page.waitForSelector('[data-testid="input-sampler"]', { timeout: 10000 });
      await page.locator('[data-testid="feature-tab-txt2img"]').click();
      await page.waitForTimeout(500);

      // Sampler: enabled <select> with fixture default "dpmpp_2m" and options present
      const samplerInput = page.locator('[data-testid="input-sampler"]');
      await expect(samplerInput).toBeVisible({ timeout: 10000 });
      await expect(samplerInput).toBeEnabled();
      expect(await samplerInput.evaluate((el) => el.tagName)).toBe("SELECT");
      expect(await samplerInput.inputValue()).toBe("dpmpp_2m");
      const samplerOptions = await samplerInput.evaluate((el) => Array.from(el.options).map((o) => o.value));
      expect(samplerOptions).toContain("euler");
      expect(samplerOptions).toContain("dpmpp_2m");
      expect(samplerOptions).toContain("ddim");

      // Scheduler: enabled <select> with fixture default "karras" and options present
      const schedulerInput = page.locator('[data-testid="input-scheduler"]');
      await expect(schedulerInput).toBeVisible({ timeout: 10000 });
      await expect(schedulerInput).toBeEnabled();
      expect(await schedulerInput.evaluate((el) => el.tagName)).toBe("SELECT");
      expect(await schedulerInput.inputValue()).toBe("karras");
      const schedulerOptions = await schedulerInput.evaluate((el) => Array.from(el.options).map((o) => o.value));
      expect(schedulerOptions).toContain("normal");
      expect(schedulerOptions).toContain("karras");
      expect(schedulerOptions).toContain("exponential");

      // Denoise: fixture default 0 renders as "0" (zero-like value preservation)
      const denoiseInput = page.locator('[data-testid="input-denoise"]');
      await expect(denoiseInput).toBeVisible({ timeout: 5000 });
      expect(await denoiseInput.inputValue()).toBe("0");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Mock state helpers ──────────────────────────────────────────────────
  //
  // Injects experiment cell history entries + experiment detail into the mock
  // API's in-memory state for testing history tiles and carousel items.

  function addExperimentToMock(api, expId, presetId, cellCount) {
    var now = new Date().toISOString();
    for (var i = 0; i < cellCount; i++) {
      api.state.history.push({
        run_id: "cell_" + expId + "_" + i,
        experiment_id: expId,
        kind: "experiment_cell",
        status: "completed",
        started_at: now,
        completed_at: now,
        output_path: "studio_output_" + expId + "_" + i + ".png",
        extra: {
          studio_preset_id: presetId,
          studio_feature_id: "txt2img",
          primary_asset_id: "asset_" + expId + "_" + i,
        },
      });
    }
    api.state.experiments.set(expId, {
      definition: {
        schema_version: 1, experiment_id: expId, revision: 1,
        name: "Test Experiment", created_at: now, updated_at: now,
      },
      snapshot: {
        status: "completed", overall_status: "completed",
        counters: { completed: cellCount, failed: 0 },
        total_cells: cellCount,
        cell_visible: {},
        checkpoints: {},
        attempts: {},
      },
      events: [
        {
          type: "experiment.created",
          payload: {
            compilation: {
              cells: Array.from({ length: cellCount }, function (_, idx) {
                return { cell_key: "cell_" + idx, axis_values: {} };
              }),
            },
          },
        },
        { type: "experiment.completed", payload: { completed: cellCount, failed: 0, total_cells: cellCount } },
      ].concat(
        Array.from({ length: cellCount }, function (_, idx) {
          return {
            type: "cell.completed",
            payload: {
              cell_key: "cell_" + idx,
              primary_asset_id: "asset_" + expId + "_" + idx,
              output_paths: ["studio_output_" + expId + "_" + idx + ".png"],
            },
          };
        })
      ),
    });
    // Set terminalPoll=1 so the experiment detail handler returns completed
    api.setExperimentBehavior(expId, { terminalPoll: 1 });
  }

  // ── Test 14: Preset defaults — no enum schemas ──────────────────────────
  //
  // Verifies that sampler and scheduler render as disabled text inputs
  // holding the fixture default values when the preset has no enum schema
  // for them, along with a "Schema unavailable" explanation note.
  // After the async preset hydrates and sets _currentPreset, clicking the
  // active feature tab triggers a re-render so the sync hydration block
  // picks up preset defaults.

  test("14. preset defaults — without enum schemas, sampler and scheduler render disabled text inputs holding saved values and a Schema unavailable explanation", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Snapshot with empty controlSchemas — no enum info for sampler/scheduler
      const snapPayload = {
        name: prefix + "-snap-no-enum",
        compatibleFeatures: ["txt2img"],
        graphJson: {},
        apiPromptJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "" } } },
        nodeBindings: {
          prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
          output: { kind: "output", nodeId: "2" },
          seed: { kind: "widget", nodeId: "3", widgetName: "seed" },
          steps: { kind: "widget", nodeId: "3", widgetName: "steps" },
          guidance: { kind: "widget", nodeId: "3", widgetName: "cfg" },
          denoise: { kind: "widget", nodeId: "3", widgetName: "denoise" },
          sampler: { kind: "widget", nodeId: "3", widgetName: "sampler_name" },
          scheduler: { kind: "widget", nodeId: "3", widgetName: "scheduler" },
        },
        outputNodeId: "2",
        source: "manual",
        controlSchemas: {},
      };

      const snapRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/snapshots", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).snapshot;
      }, snapPayload);
      expect(snapRes.id).toBeTruthy();
      owned.snapshotIds.push(snapRes.id);

      const presPayload = {
        label: prefix + "-preset-no-enum",
        snapshotId: snapRes.id,
        compatibleFeatures: ["txt2img"],
        defaults: { sampler: "dpmpp_2m", scheduler: "karras", seed: 42, steps: 20, guidance: 7, denoise: 1.0 },
      };
      const presRes = await page.evaluate(async (p) => {
        const r = await fetch("/comfymodal/studio/presets", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(p),
        });
        return (await r.json()).preset;
      }, presPayload);
      expect(presRes.id).toBeTruthy();
      owned.presetIds.push(presRes.id);
      const presetId = presRes.id;

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, presetId);

      // Wait for async preset hydration to set _currentPreset, then click
      // the active feature tab to trigger a re-render so the sync hydration
      // block correctly merges preset defaults into _hydratedControls.
      await page.waitForSelector('[data-testid="input-sampler"]', { timeout: 10000 });
      await page.locator('[data-testid="feature-tab-txt2img"]').click();
      await page.waitForTimeout(500);

      // Sampler: disabled text input holding fixture default "dpmpp_2m", with explanation note
      const samplerInput = page.locator('[data-testid="input-sampler"]');
      await expect(samplerInput).toBeVisible({ timeout: 10000 });
      await expect(samplerInput).toBeDisabled();
      expect(await samplerInput.evaluate((el) => el.tagName)).toBe("INPUT");
      expect(await samplerInput.getAttribute("type")).toBe("text");
      expect(await samplerInput.inputValue()).toBe("dpmpp_2m");

      // Scheduler: disabled text input holding fixture default "karras", with explanation note
      const schedulerInput = page.locator('[data-testid="input-scheduler"]');
      await expect(schedulerInput).toBeVisible({ timeout: 10000 });
      await expect(schedulerInput).toBeDisabled();
      expect(await schedulerInput.evaluate((el) => el.tagName)).toBe("INPUT");
      expect(await schedulerInput.getAttribute("type")).toBe("text");
      expect(await schedulerInput.inputValue()).toBe("karras");

      // Verify "Schema unavailable" explanation note is present (at least
      // one .comfymodal-studio-control-note in the control group)
      const schemaNotes = page.locator(".comfymodal-studio-control-note");
      await expect(schemaNotes.first()).toBeVisible({ timeout: 5000 });
      const notesText = await schemaNotes.allTextContents();
      const hasExplanation = notesText.some(function (t) {
        return t.toLowerCase().includes("schema unavailable");
      });
      expect(hasExplanation).toBe(true);

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 15: History experiment tile loads experiment grid ──────────────
  //
  // Injects experiment cell history entries into the mock, navigates to
  // History, verifies a single experiment tile (not individual cards),
  // clicks it, and verifies the Playground shows the experiment grid.

  test("15. history experiment tile loads experiment grid viewport", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      // Inject experiment cell history and experiment detail into mock
      const expId = "exp_hist_" + Date.now().toString(36);
      addExperimentToMock(api, expId, presetId, 3);

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Navigate to History
      await page.getByRole("button", { name: "History", exact: true }).click();
      await waitVisible(page.locator('[data-testid="history-page-info"]'));

      // Verify experiment tile is present (not individual cards)
      const expTile = page.locator('[data-testid="experiment-tile"]');
      await expect(expTile).toBeVisible({ timeout: 10000 });
      // Verify EXP badge is displayed
      await expect(expTile.locator(".comfymodal-studio-exp-tile-badge")).toBeVisible({ timeout: 5000 });
      // Verify status text contains cell count
      const tileText = await expTile.textContent();
      expect(tileText).toContain("3 cells");

      // Click the experiment tile to load experiment grid in Playground
      await expTile.click();

      // Wait for experiment grid viewport to appear
      await expect(page.locator('[data-testid="experiment-grid-viewport"]')).toBeVisible({ timeout: 15000 });
      // Verify grid outer container is present (cells rendered)
      await expect(page.locator('[data-testid="experiment-grid-outer"]')).toBeVisible({ timeout: 10000 });

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 16: Carousel experiment item has distinctive styling ──────────
  //
  // Verifies that experiment cell entries in the carousel have the
  // experiment-item CSS class and EXP badge.  Also verifies clicking
  // the experiment item navigates to the experiment grid viewport.

  test("16. carousel experiment item shows EXP badge and opens experiment grid", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const presetId = owned.presetIds[0];

      // Inject experiment cell history entries + experiment detail
      const expId = "exp_car_" + Date.now().toString(36);
      addExperimentToMock(api, expId, presetId, 2);

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Wait for carousel to load (refreshRecentRuns fetches injected history)
      // The carousel track appears after async refresh resolves
      const carouselItem = page.locator('.comfymodal-studio-carousel-item-experiment').first();
      await expect(carouselItem).toBeVisible({ timeout: 15000 });

      // Verify the EXP badge is present on experiment items
      const expBadge = carouselItem.locator('.comfymodal-studio-carousel-exp-badge');
      await expect(expBadge).toBeVisible({ timeout: 5000 });

      // Verify the experiment item has data-expid attribute
      const dataExpId = await carouselItem.getAttribute('data-expid');
      expect(dataExpId).toBeTruthy();

      // Click the experiment carousel item and verify it opens the grid
      await carouselItem.click();
      await expect(page.locator('[data-testid="experiment-grid-viewport"]')).toBeVisible({ timeout: 15000 });

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });
});
