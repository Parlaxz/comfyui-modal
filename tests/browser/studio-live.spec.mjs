// Modal Studio — Live E2E Tests
//
// Opt-in live test suite against a real ComfyUI + Modal Studio backend.
// Gated by COMFYMODAL_LIVE_E2E=1 (Playwright-native test.skip).
// Uses Playwright APIRequestContext for backend CRUD and real browser
// navigation for Playground and Experiment interaction.
//
// One consolidated serial test to minimise setup/teardown overhead:
//   1. Create one snapshot + two presets via POST
//   2. UI Playground run with first preset
//   3. UI Experiment with base + compare, no axis
//   4. Strict ID-only cleanup and verification

import { test, expect } from "@playwright/test";
import {
  installConsoleGuard,
  createOwnedRecords,
  buildLiveSnapshotPayload,
  openStudio,
} from "./studio-fixtures.mjs";

const LIVE_ENABLED = process.env.COMFYMODAL_LIVE_E2E === "1";
const COMFYUI_URL = process.env.COMFYUI_URL || "http://127.0.0.1:8188";

// ── Module-level pre-check (only when live enabled) ─────────────────────

let builderResult = null;
let builderError = null;
let defaults = null;

if (LIVE_ENABLED) {
  if (!process.env.COMFYUI_URL) {
    throw new Error(
      "COMFYMODAL_LIVE_E2E=1 requires COMFYUI_URL to be set. " +
      "Set COMFYUI_URL=http://127.0.0.1:8188 (or your instance URL)."
    );
  }

  try {
    builderResult = buildLiveSnapshotPayload();
    console.log(
      "[studio-live] Builder OK: KSampler=%s CLIPEncode=%s Output=%s hasNegative=%s",
      builderResult.ksamplerNodeId,
      builderResult.clipEncodeNodeIds.join(","),
      builderResult.outputNodeId,
      "negative_prompt" in builderResult.bindings,
    );

    // Derive defaults from actual KSampler inputs
    const ks = builderResult.snapshotPayload.graphJson[builderResult.ksamplerNodeId];
    const inputs = ks.inputs;
    console.log("[studio-live] KSampler inputs:", JSON.stringify({
      seed: inputs.seed,
      steps_connected: Array.isArray(inputs.steps),
      cfg: inputs.cfg,
      sampler_name: inputs.sampler_name,
      scheduler: inputs.scheduler,
      denoise: inputs.denoise,
    }));

    // Trace steps connection one level
    let stepsVal = null;
    if (Array.isArray(inputs.steps)) {
      const connectedNode = builderResult.snapshotPayload.graphJson[inputs.steps[0]];
      if (connectedNode?.inputs?.value !== undefined) stepsVal = connectedNode.inputs.value;
    } else if (typeof inputs.steps === "number") {
      stepsVal = inputs.steps;
    }

    defaults = {
      seed: typeof inputs.seed === "number" ? inputs.seed : 42,
      steps: stepsVal ?? 20,
      guidance: typeof inputs.cfg === "number" ? inputs.cfg : 7.0,
      sampler: typeof inputs.sampler_name === "string" ? inputs.sampler_name : "euler",
      scheduler: typeof inputs.scheduler === "string" ? inputs.scheduler : "normal",
      denoise: typeof inputs.denoise === "number" ? inputs.denoise : 1.0,
    };
    console.log("[studio-live] Derived defaults:", JSON.stringify(defaults));
  } catch (e) {
    builderError = e.message || String(e);
    console.error("[studio-live] Builder FAILED:", builderError);
  }

  if (builderError) {
    throw new Error(
      `buildLiveSnapshotPayload pre-check FAILED: ${builderError}. ` +
      "Fix the builder before running live tests."
    );
  }
}

// ── Helpers (only used when live enabled) ───────────────────────────────

/**
 * Delete owned records and verify they are gone using native Node fetch.
 *
 * Uses fetch() directly — never touches the Playwright APIRequestContext
 * (which may be torn down during failure scoping).  Only exact owned IDs
 * are touched; no prefix matching.
 *
 * Accepts 2xx and 404 from DELETE.  Collects all errors and throws
 * at the end so every failure is reported.
 */
async function cleanupAndVerify(baseURL, owned) {
  const errors = [];

  // Delete presets first (they reference snapshots)
  for (const id of owned.presetIds) {
    if (!id) continue;
    try {
      const res = await fetch(
        `${baseURL}/comfymodal/studio/presets/${encodeURIComponent(id)}`,
        { method: "DELETE" },
      );
      if (res.status !== 404 && !res.ok) {
        errors.push(`DELETE preset ${id}: HTTP ${res.status}`);
      }
    } catch (err) {
      errors.push(`DELETE preset ${id}: ${err.message}`);
    }
  }

  // Then delete snapshots
  for (const id of owned.snapshotIds) {
    if (!id) continue;
    try {
      const res = await fetch(
        `${baseURL}/comfymodal/studio/snapshots/${encodeURIComponent(id)}`,
        { method: "DELETE" },
      );
      if (res.status !== 404 && !res.ok) {
        errors.push(`DELETE snapshot ${id}: HTTP ${res.status}`);
      }
    } catch (err) {
      errors.push(`DELETE snapshot ${id}: ${err.message}`);
    }
  }

  // List active records and assert every captured ID is absent
  let activePresetIds = [];
  let activeSnapshotIds = [];
  try {
    const presRes = await fetch(`${baseURL}/comfymodal/studio/presets`);
    if (presRes.ok) {
      const body = await presRes.json();
      activePresetIds = (body.presets || []).map((p) => p.id);
    }
  } catch (err) {
    errors.push(`list presets: ${err.message}`);
  }
  try {
    const snapRes = await fetch(`${baseURL}/comfymodal/studio/snapshots`);
    if (snapRes.ok) {
      const body = await snapRes.json();
      activeSnapshotIds = (body.snapshots || []).map((s) => s.id);
    }
  } catch (err) {
    errors.push(`list snapshots: ${err.message}`);
  }

  for (const pid of owned.presetIds) {
    if (pid && activePresetIds.includes(pid)) {
      errors.push(`preset ${pid} still present after deletion`);
    }
  }
  for (const sid of owned.snapshotIds) {
    if (sid && activeSnapshotIds.includes(sid)) {
      errors.push(`snapshot ${sid} still present after deletion`);
    }
  }

  if (errors.length > 0) {
    throw new Error(
      `cleanupAndVerify: ${errors.length} issue(s):\n  ${errors.join("\n  ")}`,
    );
  }
}

async function waitVisible(locator, timeout = 15000) {
  await locator.waitFor({ state: "visible", timeout });
  return locator;
}

// ── Gate ────────────────────────────────────────────────────────────────

test.describe("Studio Live", () => {
  test.skip(!LIVE_ENABLED, "Set COMFYMODAL_LIVE_E2E=1 to enable live tests");

  // ── Consolidated live E2E test ──────────────────────────────────────

  test("consolidated live e2e: create, playground run, experiment run, cleanup", async ({ page, request }) => {
    const { snapshotPayload } = builderResult;
    const owned = createOwnedRecords();
    let guard;

    const liveTimeout = parseInt(
      process.env.COMFYMODAL_LIVE_TIMEOUT_MS || "300000",
      10,
    );

    const promptText = `live-${Date.now()}`;
    let preset1Id, preset2Id;
    let testError = null;
    let cleanupError = null;

    try {
      // ═════════════════════════════════════════════════════════════════
      // PHASE 1: Create one snapshot + two presets via API
      // ═════════════════════════════════════════════════════════════════

      // 1a. Create snapshot
      const snapResponse = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/snapshots`,
        { data: { ...snapshotPayload, name: `live-snap-${promptText}` } },
      );
      expect(snapResponse.ok()).toBeTruthy();
      const snapBody = await snapResponse.json();
      expect(snapBody.status).toBe("ok");
      expect(snapBody.snapshot).toBeTruthy();
      expect(snapBody.snapshot.id).toBeTruthy();
      const snapshotId = snapBody.snapshot.id;
      owned.snapshotIds.push(snapshotId);

      // 1b. Create preset 1 (base / playground)
      const label1 = `live-base-${promptText}`;
      const pres1Response = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/presets`,
        { data: { label: label1, snapshotId, compatibleFeatures: ["txt2img"], defaults } },
      );
      expect(pres1Response.ok()).toBeTruthy();
      const pres1Body = await pres1Response.json();
      expect(pres1Body.status).toBe("ok");
      expect(pres1Body.preset).toBeTruthy();
      expect(pres1Body.preset.id).toBeTruthy();
      expect(pres1Body.preset.status).toBe("runnable");
      preset1Id = pres1Body.preset.id;
      owned.presetIds.push(preset1Id);

      // 1c. Create preset 2 (compare)
      const label2 = `live-compare-${promptText}`;
      const pres2Response = await request.post(
        `${COMFYUI_URL}/comfymodal/studio/presets`,
        { data: { label: label2, snapshotId, compatibleFeatures: ["txt2img"], defaults } },
      );
      expect(pres2Response.ok()).toBeTruthy();
      const pres2Body = await pres2Response.json();
      expect(pres2Body.status).toBe("ok");
      expect(pres2Body.preset).toBeTruthy();
      expect(pres2Body.preset.id).toBeTruthy();
      expect(pres2Body.preset.status).toBe("runnable");
      preset2Id = pres2Body.preset.id;
      owned.presetIds.push(preset2Id);

      // ═════════════════════════════════════════════════════════════════
      // PHASE 2: UI Playground run with first preset
      // ═════════════════════════════════════════════════════════════════

      // Open Studio (ComfyUI startup noise happens here)
      await openStudio(page, COMFYUI_URL);
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Install console guard AFTER startup — spans Playground + Experiment
      guard = installConsoleGuard(page);

      // Select preset 1
      const select = page.locator('[data-testid="backend-select"]');
      await select.waitFor({ state: "visible", timeout: 15000 });
      await expect(select.locator(`option[value="${preset1Id}"]`)).toHaveCount(1, {
        timeout: 15000,
      });
      await select.selectOption(preset1Id);

      // Fill unique prompt
      const playgroundPrompt = `playground ${promptText}`;
      const promptInput = page.locator('[data-testid="input-prompt"]');
      await promptInput.waitFor({ state: "visible", timeout: 10000 });
      await promptInput.fill(playgroundPrompt);

      // Explicitly fill/select every visible derived scalar control from defaults.
      // This makes the live runtime test independent of the server hydration bug
      // (unit/mock tests cover the hydration path).
      for (const ctrl of ["steps", "guidance", "denoise", "seed", "sampler", "scheduler"]) {
        const el = page.locator(`[data-testid="input-${ctrl}"]`);
        await el.waitFor({ state: "visible", timeout: 10000 });
        const tag = await el.evaluate((n) => n.tagName);
        const val = defaults[ctrl];
        if (tag === "SELECT") {
          await el.selectOption(String(val));
        } else {
          await el.fill(String(val));
        }
      }
      // Assert steps inputValue parses to the integer defaults.steps (not blank/array)
      const stepsEl = page.locator('[data-testid="input-steps"]');
      const stepsRaw = await stepsEl.inputValue();
      const stepsParsed = parseInt(stepsRaw, 10);
      expect(stepsParsed).toBe(defaults.steps);
      expect(Number.isNaN(stepsParsed)).toBe(false);

      // Capture the run response (POST /studio/run is triggered by the frontend)
      const runResponsePromise = page.waitForResponse(
        (resp) => resp.url().includes("/comfymodal/studio/run") && resp.request().method() === "POST",
      );

      // Click Run (Playground mode uses data-testid="run-btn")
      const runBtn = page.locator('[data-testid="run-btn"]');
      await expect(runBtn).toBeEnabled({ timeout: 10000 });
      await runBtn.click();

      // Await run response and assert it before proceeding.
      // Parse body first so assertion failure includes the server message.
      const runResponse = await runResponsePromise;
      const runBody = await runResponse.json();
      if (!runResponse.ok()) {
        throw new Error(`run POST failed: ${JSON.stringify(runBody)}`);
      }
      expect(runBody.status).toBe("ok");
      // Playground run returns runId and optionally experimentId
      expect(runBody.runId || runBody.experimentId).toBeTruthy();

      // Wait for canvas output
      const canvasOutput = page.locator('[data-testid="canvas-output"]');
      await expect(canvasOutput).toBeVisible({ timeout: liveTimeout });

      // Assert canvas output URL points to asset or studio outputs
      const src = await canvasOutput.getAttribute("src");
      expect(src).toBeTruthy();
      expect(src).toMatch(/\/comfymodal\/(assets|studio\/outputs)/);

      // Assert timing card shows a finite numeric E2E duration
      const timingCard = page.locator('[data-testid="timing-card"]');
      await expect(timingCard).toBeVisible({ timeout: 15000 });
      const timingText = await timingCard.textContent();
      // Match a numeric duration like "1234ms", "1.2s", "0:05.123"
      const durationMatch = timingText.match(/\d+\.?\d*\s*(ms|s|m|seconds|milliseconds)/i);
      expect(durationMatch).toBeTruthy();

      // Assert Run button re-enabled
      await expect(runBtn).toBeEnabled({ timeout: 10000 });

      // Verify run was recorded via run-history API
      const historyRes = await request.get(
        `${COMFYUI_URL}/comfymodal/run-history?preset=${encodeURIComponent(preset1Id)}`,
      );
      expect(historyRes.ok()).toBeTruthy();
      const historyBody = await historyRes.json();
      expect(historyBody.runs).toBeTruthy();

      // Match via fields confirmed present by diagnostics:
      //   extra.prompt, extra.requested_controls.prompt, extra.resolved_controls.prompt,
      //   extra.studio_preset_id
      const matchingRun = (historyBody.runs || []).find(
        (r) =>
          r.extra?.prompt === playgroundPrompt ||
          r.extra?.requested_controls?.prompt === playgroundPrompt ||
          r.extra?.resolved_controls?.prompt === playgroundPrompt ||
          r.extra?.studio_preset_id === preset1Id,
      );
      expect(matchingRun).toBeTruthy();

      // Navigate to History UI and assert owned run is visible by prompt text or preset label
      await page.getByRole("button", { name: "History", exact: true }).click();
      await waitVisible(page.locator('[data-testid="studio-page"]'));
      // The History page must show text containing the unique playground prompt
      // or the owned preset label somewhere in the visible DOM
      await expect(page.getByText(playgroundPrompt).first()).toBeVisible({ timeout: 10000 });
      // ═════════════════════════════════════════════════════════════════
      // PHASE 3: UI Experiment with base + compare
      // ═════════════════════════════════════════════════════════════════

      // Navigate back to Playground
      await page.getByRole("button", { name: "Playground", exact: true }).click();
      await waitVisible(page.locator('[data-testid="control-panel"]'));

      // Ensure preset 1 is still selected (base)
      await select.waitFor({ state: "visible", timeout: 15000 });
      const currentVal = await select.inputValue();
      if (currentVal !== preset1Id) {
        await select.selectOption(preset1Id);
      }
      await waitVisible(page.locator('[data-testid="input-prompt"]'));

      // Enable experiment mode
      const toggle = page.locator('[data-testid="experiment-toggle"]');
      await toggle.waitFor({ state: "visible", timeout: 10000 });
      const toggleText = await toggle.textContent();
      if (toggleText && toggleText.trim() === "Experiment") {
        await toggle.click();
      }
      await waitVisible(page.locator('[data-testid="experiment-mode"]'));

      // Check preset 2 as compare (prefer stable data-testid, fall back to data-backend-id)
      const compareCb = page.locator(
        `[data-testid="compare-preset-${preset2Id}"], [data-backend-id="${preset2Id}"]`,
      ).first();
      await compareCb.waitFor({ state: "visible", timeout: 10000 });
      const isChecked = await compareCb.isChecked();
      if (!isChecked) {
        await compareCb.check();
        await expect(compareCb).toBeChecked({ timeout: 5000 });
      }

      // Fill experiment prompt
      const experimentPrompt = `experiment ${promptText}`;
      await page.locator('[data-testid="input-prompt"]').fill(experimentPrompt);

      // Re-apply scalar controls before experiment submit so the live test
      // is not dependent on cross-navigation hydration.
      for (const ctrl of ["steps", "guidance", "denoise", "seed", "sampler", "scheduler"]) {
        const el = page.locator(`[data-testid="input-${ctrl}"]`);
        await el.waitFor({ state: "visible", timeout: 10000 });
        const tag = await el.evaluate((n) => n.tagName);
        const val = defaults[ctrl];
        if (tag === "SELECT") {
          await el.selectOption(String(val));
        } else {
          await el.fill(String(val));
        }
      }

      // Capture experiment response to get experimentId
      const experimentResponsePromise = page.waitForResponse(
        (resp) => resp.url().includes("/comfymodal/studio/experiment") && resp.request().method() === "POST",
      );

      // Submit experiment (experiment mode uses data-testid="run-experiment-btn")
      const expRunBtn = page.locator('[data-testid="run-experiment-btn"]');
      await expect(expRunBtn).toBeEnabled({ timeout: 10000 });
      await expRunBtn.click();

      // Capture experiment response.
      // Parse body first so assertion failure includes the server message.
      const experimentResponse = await experimentResponsePromise;
      const expBody = await experimentResponse.json();
      if (!experimentResponse.ok()) {
        throw new Error(`experiment POST failed: ${JSON.stringify(expBody)}`);
      }
      expect(expBody.status).toBe("ok");
      expect(expBody.experimentId).toBeTruthy();
      const experimentId = expBody.experimentId;

      // Wait for experiment terminal (run button re-enabled)
      await expect(expRunBtn).toBeEnabled({ timeout: liveTimeout });

      // ── Experiment API verification ────────────────────────────────
      const expDetailRes = await request.get(
        `${COMFYUI_URL}/comfymodal/experiments/${experimentId}`,
      );
      expect(expDetailRes.ok()).toBeTruthy();
      const expDetail = await expDetailRes.json();
      expect(expDetail.status).toBe("ok");
      expect(expDetail.snapshot).toBeTruthy();

      // Expected 2 cells (one per preset, no axis values)
      expect(expDetail.snapshot.total_cells).toBe(2);
      expect(expDetail.snapshot.counters.completed).toBe(2);
      expect(expDetail.snapshot.counters.failed).toBe(0);

      // No cell.failed events
      const failedEvents = (expDetail.events || []).filter(
        (e) => e.type === "cell.failed",
      );
      expect(failedEvents).toHaveLength(0);

      // ── Experiment UI verification ─────────────────────────────────
      // Verify terminal state: button text should be "Run"
      const btnText = (await expRunBtn.textContent()).trim();
      expect(btnText).toBe("Run");

      // Stable testid for completion message added by production hook
      // in web/studio-playground.js renderRunButton().
      await expect(page.locator('[data-testid="run-status-message"]')).toContainText(
        "Run completed (2 cell(s)).",
        { timeout: 5000 },
      );

      // No pipeline errors throughout Playground + Experiment
      guard.assertNoErrors();
    } catch (e) {
      testError = e;
    } finally {
      // Always clean up: dispose guard, then cleanup records
      if (guard) {
        try { guard.dispose(); } catch (e) { cleanupError = e; }
      }
      try {
        await cleanupAndVerify(COMFYUI_URL, owned);
      } catch (e) {
        cleanupError = cleanupError || e;
      }
    }

    // Re-throw: AggregateError when both failed, otherwise the single error
    if (testError && cleanupError) {
      throw new AggregateError(
        [testError, cleanupError],
        "Test failed AND cleanup also failed",
      );
    }
    if (cleanupError) throw cleanupError;
    if (testError) throw testError;
  });
});
