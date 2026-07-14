// Modal Studio — Experiment Mode E2E Tests
//
// Tests experiment mode behaviors using the mock API.
// Mock is installed BEFORE navigation per isolation contract.
// Uses fresh Playwright Test page/context.
//
// Required behaviors:
//   1. Full experiment lifecycle with two presets, Steps axis, completion
//   2. Disabled run button with <2 unique presets, enabled with 2+
//   3. Axis eligibility considers base + compare presets (not compare only)
//   4. Failed experiment shows precise Mock failure terminal UI
//   5. Rapid axis toggle produces exactly one connected editor, no errors
//   6. Archive/delete only owned preset IDs; unrelated remains
//   7. Matrix summary deduplicates base present in compare list
//   8. Zero unique presetIds returns HTTP 400 error

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
  // wait for the control panel to reflect the new preset (re-render driven
  // by setPage from the select change handler)
  await expect(page.locator('[data-testid="input-prompt"]')).toBeVisible({ timeout: 10000 });
}

async function enableExperimentMode(page) {
  const toggle = page.locator('[data-testid="experiment-toggle"]');
  await toggle.waitFor({ state: "visible", timeout: 10000 });
  const text = await toggle.textContent();
  if (text && text.trim() === "Experiment") {
    await toggle.click();
  }
  // Wait for experiment mode container
  await page.locator('[data-testid="experiment-mode"]').waitFor({ state: "visible", timeout: 10000 });
}

async function checkComparePreset(page, presetIdOrLabel) {
  const compareSections = page.locator(
    '[data-testid="compare-backends"] button.comfymodal-studio-collapsible-summary'
  );
  for (let i = 0; i < await compareSections.count(); i++) {
    const section = compareSections.nth(i);
    if ((await section.getAttribute("aria-expanded")) !== "true") {
      await section.click();
    }
  }
  const cb = page.locator(`[data-testid="compare-preset-${presetIdOrLabel}"], [data-backend-id="${presetIdOrLabel}"]`).first();
  await cb.waitFor({ state: "visible", timeout: 10000 });
  const isChecked = await cb.isChecked();
  if (!isChecked) {
    await cb.check();
    // Wait for the checkbox to reflect the checked state (the change handler
    // triggers context.setPage("playground") which re-renders the section).
    await expect(cb).toBeChecked({ timeout: 5000 });
  }
}

async function enableStepsAxis(page) {
  const axisCb = page.locator('[data-axis="steps"]');
  await axisCb.waitFor({ state: "visible", timeout: 10000 });
  await axisCb.check();
  // wait for the axis editor to appear (re-render driven by
  // toggleExperimentAxis which calls context.setPage("playground"))
  await expect(page.locator('[data-testid="axis-editor-steps"]')).toBeVisible({ timeout: 5000 });
  await expect(page.locator('[data-testid="input-steps"]')).toHaveCount(0);
}

async function setStepsAxisValues(page, values) {
  // The axis editor should be visible after enabling the axis
  const editor = page.locator('[data-testid="axis-editor-steps"]');
  await editor.waitFor({ state: "visible", timeout: 5000 });

  // Use quick-add buttons if available
  for (const v of values) {
    const btn = editor.locator(`button:has-text("${v}")`);
    const btnCount = await btn.count();
    if (btnCount > 0) {
      await btn.first().click();
      // brief pause deliberately creates a race-like rapid-add sequence
      await page.waitForTimeout(50);
    }
  }
}

async function submitExperiment(page) {
  const runBtn = page.locator('[data-testid="run-experiment-inline-btn"]');
  await runBtn.waitFor({ state: "visible", timeout: 10000 });
  await expect(runBtn).toBeEnabled({ timeout: 10000 });
  await runBtn.click();
}

async function waitForExperimentTerminal(page, timeout = 60000) {
  // Wait until run-experiment-inline-btn is re-enabled (terminal state)
  const runBtn = page.locator('[data-testid="run-experiment-inline-btn"]');
  await expect(runBtn).toBeEnabled({ timeout });
}

async function getDisabledReasonText(page) {
  const reason = page.locator('[data-testid="experiment-run-section"]');
  await reason.waitFor({ state: "visible", timeout: 10000 });
  return (await reason.textContent()) || "";
}

/**
 * Create a snapshot with optional steps binding via POST /comfymodal/studio/snapshots.
 * Returns the snapshot object from the response.
 */
async function createSnapshot(page, opts) {
  return page.evaluate(async (payload) => {
    const res = await fetch("/comfymodal/studio/snapshots", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const data = await res.json();
    return data.snapshot || data;
  }, opts);
}

/**
 * Create a preset via POST /comfymodal/studio/presets.
 * Returns the preset object from the response.
 */
async function createPreset(page, opts) {
  return page.evaluate(async (payload) => {
    const res = await fetch("/comfymodal/studio/presets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const data = await res.json();
    return data.preset || data;
  }, opts);
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Studio Experiment", () => {
  let api;

  test.beforeEach(async ({ page }) => {
    api = await installStudioMockApi(page, { terminalPoll: 4 });
  });

  // ── Test 1: Full experiment lifecycle ─────────────────────────────────
  //
  // Create two owned runnable presets with steps binding, select base and
  // second compare preset, enable Experiment, enable Steps axis, set values
  // [10,20], submit ONE unified /studio/experiment request. Assert:
  //   - presetIds unique length 2
  //   - axes values exact
  //   - mock cellCount = 4 (2 presets × 2 axis values)
  //   - terminal counters: completed = 4, failed = 0
  //   - completed UI visible, no failed cells, no console errors

  test("1. full experiment lifecycle with two presets and Steps axis", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create two owned presets with steps binding
      for (let i = 0; i < 2; i++) {
        const snapResult = await createSnapshot(page, {
          name: `${prefix}-snapshot-${i}`,
          compatibleFeatures: ["txt2img"],
          graphJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "test" } } },
          apiPromptJson: { "1": { class_type: "CLIPTextEncode", inputs: { text: "" } } },
          nodeBindings: {
            prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
            steps: { kind: "widget", nodeId: "1", widgetName: "text" },
          },
          outputNodeId: "1",
          source: "manual",
        });
        expect(snapResult.error).toBeFalsy();
        expect(snapResult.id).toBeTruthy();
        owned.snapshotIds.push(snapResult.id);

        const presResult = await createPreset(page, {
          label: `${prefix}-preset-${i}`,
          snapshotId: snapResult.id,
          compatibleFeatures: ["txt2img"],
          defaults: { seed: 42, steps: 20, guidance: 7.0, sampler_name: "euler", scheduler: "normal", denoise: 1.0 },
        });
        expect(presResult.error).toBeFalsy();
        expect(presResult.id).toBeTruthy();
        owned.presetIds.push(presResult.id);
      }
      expect(owned.presetIds).toHaveLength(2);

      // Open Studio
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Select the first preset as base
      await selectBackendPreset(page, owned.presetIds[0]);

      // Install guard AFTER startup
      guard = installConsoleGuard(page);

      // Enable experiment mode
      await enableExperimentMode(page);

      // Check the second preset as compare
      await checkComparePreset(page, owned.presetIds[1]);

      // Enable Steps axis and set values [10, 20]
      await enableStepsAxis(page);
      await setStepsAxisValues(page, [10, 20]);

      // Assert no unhandled calls before experiment run
      api.assertNoUnhandledCalls();

      // Submit experiment
      await submitExperiment(page);

      // Wait for experiment to reach terminal state
      await waitForExperimentTerminal(page);

      // ── Assertions ────────────────────────────────────────────────

      // The lastExperimentRequest must have correct presetIds and axes
      const submitted = api.lastExperimentRequest;
      expect(submitted).toBeTruthy();

      // Unique presetIds length = 2
      const presetIds = submitted.presetIds || [];
      const uniquePresetIds = [...new Set(presetIds.filter(Boolean))];
      expect(uniquePresetIds).toHaveLength(2);

      // Axes values exact
      const axes = submitted.experiment?.axes || {};
      expect(axes.steps).toBeTruthy();
      expect(axes.steps.enabled).toBe(true);
      const stepsValues = axes.steps.values || [];
      expect(stepsValues.map((v) => Number(v)).sort()).toEqual([10, 20]);

      // cellCount should be 4 (2 presets × 2 axis values × 1 prompt)
      const expIds = [...api.state.experiments.keys()];
      expect(expIds.length).toBeGreaterThan(0);

      // Find the last experiment's terminal snapshot
      const lastExp = api.state.experiments.get(expIds[expIds.length - 1]);
      expect(lastExp).toBeTruthy();
      expect(lastExp.snapshot.total_cells).toBe(4);
      expect(lastExp.snapshot.counters.completed).toBe(4);
      expect(lastExp.snapshot.counters.failed).toBe(0);

      // Completed UI: button should say "Run" (re-enabled after terminal)
      const runBtn = page.locator('[data-testid="run-experiment-inline-btn"]');
      const btnText = (await runBtn.textContent()).trim();
      expect(btnText).toBe("Run Experiment");

      // Completion message shows exact cell count via canonical testid
      await expect(page.locator('[data-testid="run-status-message"]')).toContainText("Run completed (4 cell(s)).");

      // No failed cell events
      const failedEvents = lastExp.events.filter((e) => e.type === "cell.failed");
      expect(failedEvents).toHaveLength(0);

      // Assert no console errors
      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  test("cancels a running experiment through the stop-now endpoint", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 2, owned);
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, owned.presetIds[0]);

      guard = installConsoleGuard(page);
      await enableExperimentMode(page);
      await checkComparePreset(page, owned.presetIds[1]);
      await submitExperiment(page);

      const cancelBtn = page.locator('[data-testid="cancel-experiment-btn"]');
      await cancelBtn.waitFor({ state: "visible", timeout: 10000 });
      await expect.poll(() => api.state.experiments.size, { timeout: 5000 }).toBeGreaterThan(0);
      const expId = [...api.state.experiments.keys()][0];

      await cancelBtn.click();
      await waitForExperimentTerminal(page, 15000);

      const stopCalls = api.state.calls.filter(function (call) {
        return call.method === "POST" && call.pathname === "/comfymodal/experiments/" + expId + "/stop-now";
      });
      expect(stopCalls.length).toBeGreaterThan(0);
      expect(api.state.experiments.get(expId).snapshot.status).toBe("stopped");
      expect(api.state.experiments.get(expId).events.some((event) => event.type === "experiment.stopped")).toBe(true);
      await expect(page.locator('[data-testid="cancel-experiment-btn"]')).toHaveCount(0);

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 2: Disabled with less than 2 presets ───────────────────────
  //
  // With only base or duplicate base compare selection, run-experiment
  // disabled with exact at-least-2 reason; adding distinct second enables it.
  // The compare checkbox change handler now calls context.setPage("playground")
  // after updating state, so the Run button re-renders automatically.

  test("2. run-experiment disabled until at least 2 unique presets selected", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });
      await createOwnedSnapshotAndPresets(page, prefix, 2, owned);
      expect(owned.presetIds).toHaveLength(2);

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Select first preset as base
      await selectBackendPreset(page, owned.presetIds[0]);

      // Enable experiment mode
      await enableExperimentMode(page);

      // With only base (no compare), should be disabled
      const runBtn = page.locator('[data-testid="run-experiment-inline-btn"]');
      await runBtn.waitFor({ state: "visible", timeout: 10000 });

      // Poll for disabled state (button state computed after async preset load)
      await expect.poll(async () => runBtn.isDisabled(), { timeout: 5000 }).toBe(true);

      // Check reason text contains "at least 2"
      const reasonTextInitial = await getDisabledReasonText(page);
      expect(reasonTextInitial.toLowerCase()).toContain("at least 2");

      // Now check the second preset as compare.
      // The compare checkbox change handler calls context.setPage("playground")
      // which re-renders the control panel including the run button.
      await checkComparePreset(page, owned.presetIds[1]);

      // The run button should become enabled after re-render driven by
      // context.setPage in the compare change handler.
      await expect(runBtn).toBeEnabled({ timeout: 5000 });
      const title = await runBtn.getAttribute("title");
      expect(title).toBeFalsy(); // no disabled title

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 3: Axis eligibility with base + compare ────────────────────
  //
  // Build base preset/snapshot WITHOUT steps support and compare preset
  // WITH steps support; Steps axis checkbox must be disabled and omitted
  // from submitted request. Current recalcEligibleAxes uses only compareIds
  // — write RED first, then fix to use canonical getExperimentPresetIds(state).

  test("3. Steps axis checkbox disabled and omitted when base preset lacks steps binding", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create base snapshot WITHOUT steps binding
      const snapBase = await createSnapshot(page, {
        name: "base-no-steps", compatibleFeatures: ["txt2img"],
        graphJson: {}, apiPromptJson: {},
        nodeBindings: { prompt: { kind: "widget", nodeId: "1", widgetName: "text" } },
        outputNodeId: "1", source: "manual",
      });
      expect(snapBase.id).toBeTruthy();
      owned.snapshotIds.push(snapBase.id);

      const presBase = await createPreset(page, {
        label: `${prefix}-base-no-steps`, snapshotId: snapBase.id,
        compatibleFeatures: ["txt2img"], defaults: { seed: 1, steps: 20 },
      });
      expect(presBase.id).toBeTruthy();
      owned.presetIds.push(presBase.id);

      // Create compare snapshot WITH steps binding
      const snapCompare = await createSnapshot(page, {
        name: "compare-with-steps", compatibleFeatures: ["txt2img"],
        graphJson: {}, apiPromptJson: {},
        nodeBindings: {
          prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
          steps: { kind: "widget", nodeId: "1", widgetName: "text" },
        },
        outputNodeId: "1", source: "manual",
      });
      expect(snapCompare.id).toBeTruthy();
      owned.snapshotIds.push(snapCompare.id);

      const presCompare = await createPreset(page, {
        label: `${prefix}-compare-with-steps`, snapshotId: snapCompare.id,
        compatibleFeatures: ["txt2img"], defaults: { seed: 2, steps: 30 },
      });
      expect(presCompare.id).toBeTruthy();
      owned.presetIds.push(presCompare.id);

      // Open Studio
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Select base preset (no steps)
      await selectBackendPreset(page, presBase.id);

      // Install guard after open
      guard = installConsoleGuard(page);

      // Enable experiment mode
      await enableExperimentMode(page);

      // Check compare preset (with steps).
      // The compare change handler now calls context.setPage("playground")
      // which re-renders, so we don't need toggle-off/on workaround.
      await checkComparePreset(page, presCompare.id);

      // When base preset lacks steps binding AND only prompt binding, Steps
      // control is not in the visible control list (steps is optional and
      // not bound). Consequently the axis checkbox wrapper for Steps is
      // absent from the DOM entirely (not just disabled).
      const stepsAxisWrapper = page.locator('[data-testid="axis-checkbox-steps"]');
      await expect.poll(async () => stepsAxisWrapper.count(), { timeout: 5000 }).toBe(0);

      // Also verify Steps control itself is not rendered
      const stepsControl = page.locator('[data-testid="control-steps"]');
      const stepsControlCount = await stepsControl.count();
      expect(stepsControlCount).toBe(0);

      // The axis editor for steps should NOT exist
      const stepsEditor = page.locator('[data-testid="axis-editor-steps"]');
      const editorCount = await stepsEditor.count();
      expect(editorCount).toBe(0);

      // Submit experiment
      await submitExperiment(page);
      await waitForExperimentTerminal(page);

      // Assert Steps axis is NOT in the submitted request
      const submitted = api.lastExperimentRequest;
      expect(submitted).toBeTruthy();
      const axes = submitted.experiment?.axes || {};
      expect(axes.steps).toBeFalsy();

      // No console errors from the eligibility / absence path
      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 4: Failed experiment shows Mock failure terminal UI ─────────

  test("4. failed experiment shows Mock failure terminal UI", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create two presets with steps binding
      for (let i = 0; i < 2; i++) {
        const snapResult = await createSnapshot(page, {
          name: `fail-test-snap-${i}`, compatibleFeatures: ["txt2img"],
          graphJson: {}, apiPromptJson: {},
          nodeBindings: {
            prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
            steps: { kind: "widget", nodeId: "1", widgetName: "text" },
          },
          outputNodeId: "1", source: "manual",
        });
        expect(snapResult.id).toBeTruthy();
        owned.snapshotIds.push(snapResult.id);

        const presResult = await createPreset(page, {
          label: `${prefix}-fail-${i}`, snapshotId: snapResult.id,
          compatibleFeatures: ["txt2img"],
          defaults: { seed: i + 1, steps: 20 },
        });
        expect(presResult.id).toBeTruthy();
        owned.presetIds.push(presResult.id);
      }

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, owned.presetIds[0]);

      guard = installConsoleGuard(page);

      await enableExperimentMode(page);
      await checkComparePreset(page, owned.presetIds[1]);
      await enableStepsAxis(page);
      await setStepsAxisValues(page, [10, 20]);

      // Submit experiment
      await submitExperiment(page);

      // Wait for at least one experiment to exist, then force it to fail
      await expect.poll(() => api.state.experiments.size, { timeout: 5000 }).toBeGreaterThan(0);
      const expId = [...api.state.experiments.keys()][0];
      api.setExperimentBehavior(expId, { forceFailed: true, terminalPoll: 3 });

      // Wait for terminal state
      await waitForExperimentTerminal(page, 45000);

      // Should show "Mock failure" error
      const reasonText = await getDisabledReasonText(page);
      expect(reasonText.toLowerCase()).toContain("mock failure");

      // Terminal snapshot counters should show all failed
      const exp = api.state.experiments.get(expId);
      expect(exp).toBeTruthy();
      expect(exp.snapshot.counters.failed).toBeGreaterThan(0);
      expect(exp.snapshot.counters.completed).toBe(0);

      // Should have cell.failed events
      const failedEvents = exp.events.filter((e) => e.type === "cell.failed");
      expect(failedEvents.length).toBeGreaterThan(0);

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 5: Rapid axis toggle ────────────────────────────────────────
  //
  // Rapidly toggle Steps axis across re-renders; assert exactly one
  // connected axis-editor-steps when axis ends enabled, no pageerror/
  // console error, and no duplicate matching elements in the DOM.
  // Current deferred insertion uses parent.insertBefore(editor,
  // parent.nextSibling) incorrectly and lacks isConnected guard — RED
  // then minimal fix using controlEl.isConnected, parent.isConnected,
  // and parent.parentNode.insertBefore with stale-editor removal.

  test("5. rapid axis toggle produces exactly one connected editor and no errors", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create two presets with steps binding
      for (let i = 0; i < 2; i++) {
        const snapResult = await createSnapshot(page, {
          name: `rapid-snap-${i}`, compatibleFeatures: ["txt2img"],
          graphJson: {}, apiPromptJson: {},
          nodeBindings: {
            prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
            steps: { kind: "widget", nodeId: "1", widgetName: "text" },
          },
          outputNodeId: "1", source: "manual",
        });
        owned.snapshotIds.push(snapResult.id);

        const presResult = await createPreset(page, {
          label: `${prefix}-rapid-${i}`, snapshotId: snapResult.id,
          compatibleFeatures: ["txt2img"],
          defaults: { seed: i + 1, steps: 20 },
        });
        owned.presetIds.push(presResult.id);
      }

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));
      await selectBackendPreset(page, owned.presetIds[0]);
      await enableExperimentMode(page);
      await checkComparePreset(page, owned.presetIds[1]);

      // Install guard AFTER open so ComfyUI startup noise is excluded
      guard = installConsoleGuard(page);

      // Rapidly toggle Steps axis checkbox multiple times
      const stepsAxisCb = page.locator('[data-axis="steps"]');
      await stepsAxisCb.waitFor({ state: "visible", timeout: 10000 });

      // Toggle on->off->on->off->on quickly to create a race between
      // deferred insertions and unmounts. 50ms between clicks is
      // intentionally brief.
      for (let t = 0; t < 5; t++) {
        await stepsAxisCb.click();
        await page.waitForTimeout(50);
      }

      // Final state: checked (5 toggles from unchecked = checked)
      const isChecked = await stepsAxisCb.isChecked();
      expect(isChecked).toBe(true);

      // Wait for deferred insertions to settle: poll until the editor
      // count stabilizes (no change across two consecutive polls).
      const editorLocator = page.locator('[data-testid="axis-editor-steps"]');
      let stableCount = -1;
      await expect.poll(async () => {
        const current = await editorLocator.count();
        if (current === stableCount) return { stable: true, count: current };
        stableCount = current;
        return { stable: false, count: current };
      }, { timeout: 5000, message: "editor count did not stabilise" }).toMatchObject({ stable: true });

      // Assert exactly one editor, connected, with no duplicate elements
      const finalCount = await editorLocator.count();
      expect(finalCount).toBe(1);
      const editor = editorLocator.first();
      const isConnected = await editor.evaluate((el) => el.isConnected);
      expect(isConnected).toBe(true);

      // No page errors or console errors from the toggle dance
      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 6: Archive/delete only owned presets ────────────────────────

  test("6. archive owned presets, unrelated preset remains", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      await createOwnedSnapshotAndPresets(page, prefix, 1, owned);
      const testPresetId = owned.presetIds[0];

      // Create an unrelated preset
      const snapRes = await createSnapshot(page, {
        name: "unrelated-snapshot-exp", compatibleFeatures: ["txt2img"],
        graphJson: {}, apiPromptJson: {},
        nodeBindings: {}, outputNodeId: "1", source: "manual",
      });
      expect(snapRes.id).toBeTruthy();

      const presRes = await createPreset(page, {
        label: "unrelated-preset-exp", snapshotId: snapRes.id,
        compatibleFeatures: ["txt2img"], defaults: { seed: 99, steps: 20 },
      });
      expect(presRes.id).toBeTruthy();

      // Delete the owned preset via API
      const delRes = await page.evaluate(async (id) => {
        const r = await fetch(`/comfymodal/studio/presets/${encodeURIComponent(id)}`, { method: "DELETE" });
        return r.ok;
      }, testPresetId);
      expect(delRes).toBeTruthy();

      // Reload Studio and check select options
      await page.reload();
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      const options = await page.locator('[data-testid="backend-select"] option').allTextContents();
      // Owned preset should be gone (archived)
      expect(options.some((t) => t.includes(prefix))).toBeFalsy();
      // Unrelated should remain
      expect(options.some((t) => t.includes("unrelated-preset-exp"))).toBeTruthy();

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });

  // ── Test 7: Matrix summary de-duplication ────────────────────────────
  //
  // Verify matrix summary estimated runs and request canonical IDs
  // de-duplicate base selected in compare list.

  test("7. matrix summary deduplicates base present in compare list", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();
    let guard;

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create two presets WITH steps binding
      for (let i = 0; i < 2; i++) {
        const snapResult = await createSnapshot(page, {
          name: `${prefix}-snap-${i}`, compatibleFeatures: ["txt2img"],
          graphJson: {}, apiPromptJson: {},
          nodeBindings: {
            prompt: { kind: "widget", nodeId: "1", widgetName: "text" },
            steps: { kind: "widget", nodeId: "1", widgetName: "text" },
          },
          outputNodeId: "1", source: "manual",
        });
        owned.snapshotIds.push(snapResult.id);

        const presResult = await createPreset(page, {
          label: `${prefix}-preset-${i}`, snapshotId: snapResult.id,
          compatibleFeatures: ["txt2img"],
          defaults: { seed: i + 1, steps: 20 },
        });
        owned.presetIds.push(presResult.id);
      }

      expect(owned.presetIds).toHaveLength(2);

      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Select first preset as base
      await selectBackendPreset(page, owned.presetIds[0]);

      // Install guard
      guard = installConsoleGuard(page);

      // Enable experiment mode
      await enableExperimentMode(page);

      // Check the first preset ALSO in compare (self-reference to test deduplication)
      await checkComparePreset(page, owned.presetIds[0]);

      // Also add the second preset as compare
      await checkComparePreset(page, owned.presetIds[1]);

      // Enable Steps axis (which triggers re-render via toggleExperimentAxis action)
      await enableStepsAxis(page);

      // The getExperimentPresetIds should deduplicate: base (preset0) + compare [preset0, preset1]
      // should yield [preset0, preset1] -> length 2
      // Wait for the matrix summary to reflect the deduplicated count.
      const matrixSummary = page.locator('[data-testid="matrix-summary"]');
      await matrixSummary.waitFor({ state: "visible", timeout: 5000 });
      await expect.poll(async () => (await matrixSummary.textContent()) || "", {
        timeout: 5000,
      }).toContain("Selected backends: 2");

      // Now submit and verify the request has canonical IDs without dupes
      await setStepsAxisValues(page, [10]);
      await submitExperiment(page);
      await waitForExperimentTerminal(page);

      const submitted = api.lastExperimentRequest;
      expect(submitted).toBeTruthy();

      // Canonical preset IDs should be unique - base + compare should not duplicate
      const presetIds = submitted.presetIds || [];
      const uniquePresetIds = [...new Set(presetIds.filter(Boolean))];
      expect(uniquePresetIds).toHaveLength(2);
      expect(presetIds.length).toBe(uniquePresetIds.length);

      // cellCount = 2 presets x axis values x 1 prompt.
      // The axis editor starts with a default value (20 from CONTROL_DEFS),
      // then quick-add of [10] adds a second value, giving [20, 10] = 2 values.
      // Expected: 2 presets x 2 axis values x 1 prompt = 4 cells.
      const expIds = [...api.state.experiments.keys()];
      if (expIds.length > 0) {
        const lastExp = api.state.experiments.get(expIds[expIds.length - 1]);
        expect(lastExp).toBeTruthy();
        expect(lastExp.snapshot.total_cells).toBe(4);
      }

      guard.assertNoErrors();
      api.assertNoUnhandledCalls();
    } finally {
      if (guard) guard.dispose();
    }
  });

  // ── Test 8: Zero presetIds rejected ──────────────────────────────────
  //
  // Mock /studio/experiment must return HTTP 400 error when canonical
  // unique presetIds is zero; do not coerce zero to one.

  test("8. experiment request with zero presetIds returns HTTP 400", async ({ page }) => {
    const prefix = createOwnerPrefix();
    const owned = createOwnedRecords();

    try {
      await page.goto(COMFYUI_URL, { waitUntil: "domcontentloaded" });

      // Create one snapshot but skip preset creation — we will POST the
      // experiment request directly with an empty presetIds array.
      const snapResult = await createSnapshot(page, {
        name: `${prefix}-snapshot-0`,
        compatibleFeatures: ["txt2img"],
        graphJson: {}, apiPromptJson: {},
        nodeBindings: { prompt: { kind: "widget", nodeId: "1", widgetName: "text" } },
        outputNodeId: "1", source: "manual",
      });
      expect(snapResult.id).toBeTruthy();
      owned.snapshotIds.push(snapResult.id);

      // Submit an experiment with empty presetIds via direct fetch
      const response = await page.evaluate(async () => {
        const res = await fetch("/comfymodal/studio/experiment", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            presetIds: [],
            featureId: "txt2img",
            experiment: { name: "Empty preset test", axes: {}, prompts: [{ text: "test" }] },
            metadata: { source: "studio_experiment" },
          }),
        });
        return { status: res.status, body: await res.json() };
      });

      expect(response.status).toBe(400);
      expect(response.body.status).toBe("error");
      expect(response.body.message).toBeTruthy();
      expect(response.body.message.toLowerCase()).toContain("preset");

      api.assertNoUnhandledCalls();
    } finally {
      // no guard
    }
  });
});
