// Phase-E deterministic contract scenarios against the fake History V2 API.
//
// These tests use the real Studio frontend and the production-shaped fake
// History V2 envelopes. They prove UI/state-machine behavior only; they do not
// prove SQLite persistence, producer materialization, remote Modal output, or
// codec timing.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const PHASE_E_IDS = {
  previewOnly: "gen_phase_e_preview_only",
  failedOriginal: "gen_phase_e_preview_failed_original",
  successfulOriginal: "gen_phase_e_preview_original",
  rerenderFailed: "gen_phase_e_rerender_failed",
  remoteOriginal: "gen_phase_e_remote_original",
  sparseFailed: "gen_phase_e_sparse_failed",
  sparseInterrupted: "gen_phase_e_sparse_interrupted",
  experiment: "exp_phase_e_preview",
};

async function seedPhaseE(fx) {
  const seeded = await fx.seedHistory("history_v2_phase_e");
  expect(seeded).toMatchObject({ status: "ok", scenario: "history_v2_phase_e", v2: true });
  expect(seeded.count).toBe(8);
}

async function getGeneration(page, sessionId, id) {
  const res = await page.request.get(
    `/comfymodal/history-v2/generations/${id}?session=${encodeURIComponent(sessionId)}`
  );
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.status).toBe("ok");
  return body.item;
}

async function getAsset(page, url, sessionId) {
  const res = await page.request.get(`${url}?session=${encodeURIComponent(sessionId)}`);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toMatch(/^image\/png/);
  expect((await res.body()).length).toBeGreaterThan(20);
  return res;
}

async function openGenerationDetail(page, id) {
  await page.locator(`.comfymodal-studio-history-v2-generation-card[data-id="${id}"]`).click();
  const overlay = page.locator('.comfymodal-studio-history-v2-overlay[aria-label="Generation detail"]');
  await expect(overlay).toBeVisible({ timeout: 10000 });
  return overlay;
}

test.describe("Studio Phase-E contract harness (fake backend)", () => {
  test("A. Preview-only Generation has a Preview Attempt and managed Preview asset", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      const item = await getGeneration(page, fx.sessionId, PHASE_E_IDS.previewOnly);
      const output = item.outputs[0];

      expect(item.status).toBe("completed");
      expect(item.preview_only).toBe(true);
      expect(item.original_available).toBe(false);
      expect(output.preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(output.original_url).toBe("");
      expect(output.original_failed).toBe(false);
      expect(item.attempts.map((a) => [a.mode, a.status])).toEqual([["preview", "completed"]]);
      await getAsset(page, output.preview_url, fx.sessionId);

      await fx.gotoPage("history");
      const overlay = await openGenerationDetail(page, PHASE_E_IDS.previewOnly);
      await expect(overlay.locator(".comfymodal-studio-history-v2-slot-title").filter({ hasText: "Preview" })).toBeVisible();
      await expect(overlay).toContainText("No original");
      expect(await page.locator('[data-testid="history-v2-generate-original"]').count()).toBe(1);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("B. Failed Original preserves Preview and exposes truthful failure", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      const item = await getGeneration(page, fx.sessionId, PHASE_E_IDS.failedOriginal);
      const output = item.outputs[0];

      expect(output.preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(output.original_url).toBe("");
      expect(output.original_failed).toBe(true);
      expect(item.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", "failed"],
      ]);
      expect(item.errors).toEqual([{ code: "attempt_failed", message: "Original replay failed" }]);
      await getAsset(page, output.preview_url, fx.sessionId);

      await fx.gotoPage("history");
      const overlay = await openGenerationDetail(page, PHASE_E_IDS.failedOriginal);
      await expect(overlay.getByTestId("history-v2-original-failed-badge")).toContainText("Original failed");
      await expect(overlay).toContainText("preview retained");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("C. Successful Original retains Preview and prefers Original availability", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      const item = await getGeneration(page, fx.sessionId, PHASE_E_IDS.successfulOriginal);
      const output = item.outputs[0];

      expect(item.preview_only).toBe(false);
      expect(item.original_available).toBe(true);
      expect(output.preview_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(output.original_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(item.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", "completed"],
      ]);
      await getAsset(page, output.preview_url, fx.sessionId);
      await getAsset(page, output.original_url, fx.sessionId);

      await fx.gotoPage("history");
      const overlay = await openGenerationDetail(page, PHASE_E_IDS.successfulOriginal);
      await expect(overlay.locator('img[alt="Original"]')).toBeVisible();
      await expect(overlay.locator('img[alt="Preview"]')).toBeVisible();
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("D. Failed Original rerender keeps the earlier Original available", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      const item = await getGeneration(page, fx.sessionId, PHASE_E_IDS.rerenderFailed);
      const output = item.outputs[0];

      expect(output.original_url).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      expect(output.original_failed).toBe(false);
      expect(item.attempts.map((a) => [a.mode, a.status])).toEqual([
        ["preview", "completed"],
        ["original", "completed"],
        ["original", "failed"],
      ]);
      expect(item.errors).toEqual([{ code: "attempt_failed", message: "Rerender timed out" }]);
      await getAsset(page, output.original_url, fx.sessionId);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("E. Remote-backed Original is served through the managed History URL", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      const item = await getGeneration(page, fx.sessionId, PHASE_E_IDS.remoteOriginal);
      const serialized = JSON.stringify(item);
      const originalUrl = item.outputs[0].original_url;

      expect(serialized).not.toContain("modal://");
      expect(originalUrl).toMatch(/^\/comfymodal\/history-v2\/assets\//);
      await getAsset(page, originalUrl, fx.sessionId);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("F. Sparse failure/interruption records keep production-shaped empty outputs", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      for (const [id, status] of [
        [PHASE_E_IDS.sparseFailed, "failed"],
        [PHASE_E_IDS.sparseInterrupted, "interrupted"],
      ]) {
        const item = await getGeneration(page, fx.sessionId, id);
        expect(item.status).toBe(status);
        expect(item.outputs).toEqual([]);
        expect(item.params).toEqual({});
        expect(item.attempts).toHaveLength(1);
      }
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test.fixme("F2. Sparse detail overlay waits for E4 nullable-section guard", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      await seedPhaseE(fx);
      await fx.gotoPage("history");
      const overlay = await openGenerationDetail(page, PHASE_E_IDS.sparseFailed);
      await expect(overlay).toContainText("No outputs");
      await expect(overlay).toContainText("Failed");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("G. Modern Experiment accepts one frozen Preview definition without client fanout", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_phase_e_contract";
      const body = {
        sessionId: fx.sessionId,
        experiment_id: experimentId,
        name: "Phase E Preview Sweep",
        definition: {
          feature_id: "txt2img",
          axis_labels: { x: "seed", y: "steps" },
          axes: { seed: { values: [111, 222] }, steps: { values: [20] } },
          modal_options: { enabled: true, codec: "webp", quality: 70 },
          workflows: [{
            workflow_id: "wf_phase_e",
            workflow_version_id: "wv_phase_e",
            preset_id: "preset_phase_e",
            workflow_name: "Phase E Workflow",
            preset_name: "Phase E Preset",
          }],
        },
      };
      expect(Object.prototype.hasOwnProperty.call(body, "cells")).toBe(false);
      expect(Object.prototype.hasOwnProperty.call(body, "concurrency")).toBe(false);
      const res = await page.request.post("/comfymodal/studio/experiment-v2", { data: body });
      expect(res.status()).toBe(200);
      expect(await res.json()).toMatchObject({
        status: "ok",
        experiment_id: experimentId,
        total: 2,
        counts: { queued: 2, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 },
      });

      const state = await fx.getState();
      const accepted = state.modernExperiments.find((entry) => entry.experiment_id === experimentId);
      expect(accepted.frozen_modal_options).toEqual({ enabled: true, codec: "webp", quality: 70 });
      expect(accepted.cells.map((cell) => cell.cell_id)).toEqual(["cell_0", "cell_1"]);
      expect(accepted.cells.map((cell) => cell.position)).toEqual([0, 1]);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
