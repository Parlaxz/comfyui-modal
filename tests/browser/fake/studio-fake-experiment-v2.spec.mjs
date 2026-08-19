// Modal Studio — Modern Experiment V2 (D5) parity tests against the
// deterministic fake backend.
//
// These tests drive the ADDITIVE modern REST surface directly via
// page.request (deterministic, no real generation):
//
//   POST /comfymodal/studio/experiment-v2                          (create)
//   GET  /comfymodal/history-v2/experiments/{id}/status            (status)
//   POST /comfymodal/history-v2/experiments/{id}/cancel            (cancel)
//   POST /comfymodal/history-v2/experiments/{id}/resume            (resume)
//   POST /comfymodal/history-v2/experiments/{id}/cells/{cid}/retry (retry)
//
// plus the /__comfymodal_test/modern-experiment-state test-control endpoint
// that sets cell statuses for deterministic mixed-state assertions.
//
// The production contract is authoritative and flat (experiment_modern_routes.py,
// PHASE_D_INTERFACE_FREEZE.md §11): flat create envelope, flat status
// projection with fixed position order and canonical cell statuses, and
// "partial" is never emitted.

import { test, expect } from "@playwright/test";
import { setupFakeTest } from "./helpers.mjs";

const BASE_DEFINITION = {
  name: "Fake Modern Sweep",
  feature_id: "txt2img",
  axis_labels: { x: "seed", y: "steps" },
  axes: {
    seed: { enabled: true, values: [111, 222] },
    steps: { enabled: true, values: [20, 30] },
  },
  defaults: { seed: 1000, steps: 20 },
  prompts: [{ text: "deterministic fake prompt", negative: "" }],
  workflows: [
    {
      workflow_id: "wf_text2img",
      workflow_version_id: "wv1_latest",
      preset_id: "wpres_a",
      workflow_name: "Text2Img Workflow",
      preset_name: "Preset A",
    },
  ],
};

// Every cell record of the flat status projection must carry exactly these keys.
const CELL_STATUS_KEYS = [
  "cell_id", "position", "status", "active_attempt_id", "generation_id",
  "workflow_id", "workflow_version_id", "preset_id", "workflow_name",
  "preset_name", "axis_labels", "axis_values", "axes", "error",
  "duration_ms", "thumbnail_url", "output_reference",
].sort();

const SIX_COUNTS = {
  queued: 0, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0,
};

function definitionForCellCount(definition, count) {
  const out = JSON.parse(JSON.stringify(definition));
  if (count === 1) {
    out.axes = { seed: { values: [111] } };
  } else if (count === 2) {
    out.axes = { seed: { values: [111, 222] }, steps: { values: [20] } };
  } else if (count === 3) {
    out.axes = { seed: { values: [111, 222, 333] }, steps: { values: [20] } };
  } else if (count === 4) {
    out.axes = {
      seed: { values: [111, 222] },
      steps: { values: [20, 30] },
    };
  } else {
    out.axes = { seed: { values: Array.from({ length: count }, (_, i) => 111 + i) } };
  }
  return out;
}

async function createExperiment(page, sessionId, experimentId, opts = {}) {
  const payload = {
    experiment_id: experimentId,
    name: "Fake Modern Sweep",
    definition: opts.cellCount != null
      ? definitionForCellCount(opts.definition || BASE_DEFINITION, opts.cellCount)
      : (opts.definition || BASE_DEFINITION),
  };
  const res = await page.request.post("/comfymodal/studio/experiment-v2", {
    data: Object.assign({ sessionId }, payload),
  });
  return { http: res.status(), body: await res.json() };
}

async function getStatus(page, sessionId, experimentId) {
  const res = await page.request.get(
    `/comfymodal/history-v2/experiments/${encodeURIComponent(experimentId)}/status?session=${encodeURIComponent(sessionId)}`
  );
  return { http: res.status(), body: await res.json() };
}

async function setCellStates(page, sessionId, experimentId, cells) {
  const res = await page.request.post("/__comfymodal_test/modern-experiment-state", {
    data: { sessionId, experiment_id: experimentId, cells },
  });
  return { http: res.status(), body: await res.json() };
}

function expectCounts(body, counts) {
  expect(body.counts).toEqual(Object.assign({}, SIX_COUNTS, counts));
}

function expectNoPartial(status) {
  expect(status).not.toBe("partial");
}

test.describe("Studio Modern Experiment V2 (fake backend, D5 parity)", () => {
  test("1. create returns the flat envelope and status returns the flat projection", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_flat_shape";
      const created = await createExperiment(page, fx.sessionId, experimentId, { cellCount: 3 });
      expect(created.http).toBe(200);
      // Flat create envelope (freeze §11.1).
      expect(created.body).toEqual({
        status: "ok",
        experiment_id: experimentId,
        started: true,
        aggregate_status: "running",
        total: 3,
        counts: { queued: 3, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 },
      });

      // Flat status projection (freeze §11.2).
      const st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.http).toBe(200);
      expect(st.body.status).toBe("ok");
      expect(st.body.experiment_id).toBe(experimentId);
      expect(st.body.aggregate_status).toBe("running");
      expect(st.body.total).toBe(3);
      expectCounts(st.body, { queued: 3 });
      expect(Array.isArray(st.body.cells)).toBe(true);
      expect(st.body.cells).toHaveLength(3);

      // Cells are in fixed position order with every frozen field present.
      st.body.cells.forEach((cell, i) => {
        expect(cell.cell_id).toBe("cell_" + i);
        expect(cell.position).toBe(i);
        expect(cell.status).toBe("queued");
        expect(cell.active_attempt_id).toMatch(/^run_/);
        expect(cell.generation_id).toBe("gen_" + experimentId + "_" + i);
        expect(cell.workflow_id).toBe("wf_text2img");
        expect(cell.workflow_version_id).toBe("wv1_latest");
        expect(cell.preset_id).toBe("wpres_a");
        expect(cell.workflow_name).toBe("Text2Img Workflow");
        expect(cell.preset_name).toBe("Preset A");
        expect(cell.axis_labels).toEqual({ seed: String(cell.axis_values.seed), steps: "20" });
        expect(cell.axis_values.steps).toBe(20);
        expect(cell.axes).toEqual(["seed", "steps"]);
        expect(cell.error).toBeNull();
        expect(cell.duration_ms).toBeNull();
        expect(cell.thumbnail_url).toBe("");
        expect(cell.output_reference).toBeNull();
        expect(Object.keys(cell).sort()).toEqual(CELL_STATUS_KEYS);
      });

      // The frozen six counts, never "partial".
      expect(Object.keys(st.body.counts).sort()).toEqual(Object.keys(SIX_COUNTS).sort());
      expectNoPartial(st.body.aggregate_status);
      expect(JSON.stringify(st.body)).not.toContain("partial");

      // Unknown experiment is a truthful 404.
      const missing = await getStatus(page, fx.sessionId, "exp_v2_nope");
      expect(missing.http).toBe(404);
      expect(missing.body).toEqual({
        status: "error",
        message: "experiment not found",
        code: "EXPERIMENT_NOT_FOUND",
        experiment_id: "exp_v2_nope",
      });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("2. cells are derived deterministically from the definition when absent", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      // The server derives the fixed matrix from the definition's axes
      // (cartesian product, fixed order) + workflows[0].
      const experimentId = "exp_v2_derived";
      const created = await createExperiment(page, fx.sessionId, experimentId, {
        definition: BASE_DEFINITION,
      });
      expect(created.http).toBe(200);
      expect(created.body.total).toBe(4);

      const st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.cells).toHaveLength(4);
      const summaries = st.body.cells.map((c) => ({
        cell_id: c.cell_id,
        axis_values: c.axis_values,
        workflow_id: c.workflow_id,
        workflow_version_id: c.workflow_version_id,
        preset_id: c.preset_id,
      }));
      expect(summaries).toEqual([
        { cell_id: "cell_0", axis_values: { seed: 111, steps: 20 }, workflow_id: "wf_text2img", workflow_version_id: "wv1_latest", preset_id: "wpres_a" },
        { cell_id: "cell_1", axis_values: { seed: 111, steps: 30 }, workflow_id: "wf_text2img", workflow_version_id: "wv1_latest", preset_id: "wpres_a" },
        { cell_id: "cell_2", axis_values: { seed: 222, steps: 20 }, workflow_id: "wf_text2img", workflow_version_id: "wv1_latest", preset_id: "wpres_a" },
        { cell_id: "cell_3", axis_values: { seed: 222, steps: 30 }, workflow_id: "wf_text2img", workflow_version_id: "wv1_latest", preset_id: "wpres_a" },
      ]);
      expect(st.body.cells[0].generation_id).toBe("gen_exp_v2_derived_0");

      // Axis-less definition → the planner's single-cell matrix.
      const experimentId2 = "exp_v2_no_axes";
      const created2 = await createExperiment(page, fx.sessionId, experimentId2, {
        definition: {
          name: "No Axis Sweep",
          feature_id: "txt2img",
          workflows: BASE_DEFINITION.workflows,
        },
      });
      expect(created2.body.total).toBe(1);
      const st2 = await getStatus(page, fx.sessionId, experimentId2);
      expect(st2.body.cells.map((c) => c.cell_id)).toEqual(["cell_0"]);
      expect(st2.body.cells[0].workflow_id).toBe("wf_text2img");
      expect(st2.body.cells[0].preset_name).toBe("Preset A");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("3. aggregates settle to the frozen truth table — never partial", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_aggregates";
      const created = await createExperiment(page, fx.sessionId, experimentId, { cellCount: 4 });
      expect(created.body.aggregate_status).toBe("running");

      // all queued → running
      let st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("running");

      // completed + failed → completed_with_failures
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "completed" },
        { cell_id: "cell_2", status: "failed" },
        { cell_id: "cell_3", status: "failed" },
      ]);
      st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("completed_with_failures");
      expectCounts(st.body, { completed: 2, failed: 2 });
      expectNoPartial(st.body.aggregate_status);

      // interrupted beats failed/canceled siblings → interrupted
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "interrupted" },
        { cell_id: "cell_2", status: "failed" },
        { cell_id: "cell_3", status: "canceled" },
      ]);
      st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("interrupted");
      expectCounts(st.body, { completed: 1, interrupted: 1, failed: 1, canceled: 1 });

      // canceled beats failed siblings → canceled
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "canceled" },
        { cell_id: "cell_2", status: "canceled" },
        { cell_id: "cell_3", status: "failed" },
      ]);
      st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("canceled");
      expectCounts(st.body, { completed: 1, canceled: 2, failed: 1 });

      // any queued/running beats everything → running
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "running" },
        { cell_id: "cell_2", status: "failed" },
        { cell_id: "cell_3", status: "canceled" },
      ]);
      st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("running");

      // all completed → completed
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "completed" },
        { cell_id: "cell_2", status: "completed" },
        { cell_id: "cell_3", status: "completed" },
      ]);
      st = await getStatus(page, fx.sessionId, experimentId);
      expect(st.body.aggregate_status).toBe("completed");
      expectCounts(st.body, { completed: 4 });

      // No partial anywhere in the response stream.
      expect(JSON.stringify(st.body)).not.toContain("partial");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("4. cells stay in fixed position order with independent states", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_order";
      await createExperiment(page, fx.sessionId, experimentId, { cellCount: 4 });

      // Set states out of order and mixed.
      const applied = await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_3", status: "running" },
        { cell_id: "cell_1", status: "failed", error: "boom" },
        { cell_id: "cell_0", status: "completed", duration_ms: 4200 },
        { cell_id: "cell_2", status: "queued" },
      ]);
      expect(applied.http).toBe(200);
      expect(applied.body.aggregate_status).toBe("running");

      const st = await getStatus(page, fx.sessionId, experimentId);
      // Fixed position order regardless of set order or completion.
      expect(st.body.cells.map((c) => c.position)).toEqual([0, 1, 2, 3]);
      expect(st.body.cells.map((c) => c.cell_id)).toEqual(["cell_0", "cell_1", "cell_2", "cell_3"]);
      expectCounts(st.body, { completed: 1, failed: 1, running: 1, queued: 1 });

      const c0 = st.body.cells[0];
      expect(c0.status).toBe("completed");
      expect(c0.duration_ms).toBe(4200);
      expect(c0.active_attempt_id).toBeNull(); // terminal → no active attempt
      const c1 = st.body.cells[1];
      expect(c1.status).toBe("failed");
      expect(c1.error).toBe("boom");
      const c2 = st.body.cells[2];
      expect(c2.status).toBe("queued");
      expect(c2.active_attempt_id).toMatch(/^run_/);
      const c3 = st.body.cells[3];
      expect(c3.status).toBe("running");
      expect(c3.active_attempt_id).toMatch(/^run_/);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("5. cancel: queued/running cancel, terminal preserved, idempotent, terminal 409", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_cancel";
      await createExperiment(page, fx.sessionId, experimentId, { cellCount: 4 });

      // Mixed: one completed, one running, two queued.
      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "running" },
      ]);

      const cancelRes = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/cancel?session=${fx.sessionId}`
      );
      expect(cancelRes.status()).toBe(200);
      const cancelBody = await cancelRes.json();
      expect(cancelBody.status).toBe("ok");
      expect(cancelBody.experiment_id).toBe(experimentId);
      // Completed output preserved; running + queued all canceled.
      expectCounts(cancelBody, { completed: 1, canceled: 3 });
      expect(cancelBody.aggregate_status).toBe("canceled");

      const st = await getStatus(page, fx.sessionId, experimentId);
      const byId = Object.fromEntries(st.body.cells.map((c) => [c.cell_id, c]));
      expect(byId.cell_0.status).toBe("completed");
      expect(byId.cell_1.status).toBe("canceled");
      expect(byId.cell_2.status).toBe("canceled");
      expect(byId.cell_3.status).toBe("canceled");
      expect(byId.cell_1.active_attempt_id).toBeNull();
      expect(byId.cell_0.active_attempt_id).toBeNull();

      // The experiment is now terminal (completed + canceled) but NOT all
      // canceled → a repeated cancel is truthfully 409 EXPERIMENT_TERMINAL.
      const again = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/cancel?session=${fx.sessionId}`
      );
      expect(again.status()).toBe(409);
      expect(await again.json()).toEqual({
        status: "error",
        message: "experiment is terminal and cannot be cancelled",
        code: "EXPERIMENT_TERMINAL",
        experiment_id: experimentId,
      });

      // An experiment whose cells were ALL canceled (never-started queued
      // cells canceled without submission) → repeated cancel is idempotent 200.
      const expIdemp = "exp_v2_cancel_idempotent";
      await createExperiment(page, fx.sessionId, expIdemp, { cellCount: 2 });
      const firstCancel = await page.request.post(
        `/comfymodal/history-v2/experiments/${expIdemp}/cancel?session=${fx.sessionId}`
      );
      expect(firstCancel.status()).toBe(200);
      const firstCancelBody = await firstCancel.json();
      expectCounts(firstCancelBody, { canceled: 2 });
      expect(firstCancelBody.aggregate_status).toBe("canceled");
      const secondCancel = await page.request.post(
        `/comfymodal/history-v2/experiments/${expIdemp}/cancel?session=${fx.sessionId}`
      );
      expect(secondCancel.status()).toBe(200);
      expect(await secondCancel.json()).toEqual({
        status: "ok",
        experiment_id: expIdemp,
        message: "experiment is already canceled",
      });

      // A terminal-but-not-canceled experiment cannot be cancelled (409).
      const exp2 = "exp_v2_cancel_terminal";
      await createExperiment(page, fx.sessionId, exp2, { cellCount: 2 });
      await setCellStates(page, fx.sessionId, exp2, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "failed" },
      ]);
      const terminalCancel = await page.request.post(
        `/comfymodal/history-v2/experiments/${exp2}/cancel?session=${fx.sessionId}`
      );
      expect(terminalCancel.status()).toBe(409);
      expect(await terminalCancel.json()).toEqual({
        status: "error",
        message: "experiment is terminal and cannot be cancelled",
        code: "EXPERIMENT_TERMINAL",
        experiment_id: exp2,
      });

      // Unknown experiment → 404.
      const missing = await page.request.post(
        `/comfymodal/history-v2/experiments/exp_v2_nope/cancel?session=${fx.sessionId}`
      );
      expect(missing.status()).toBe(404);
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("6. resume creates fresh attempts only for interrupted + queued, skipping failed", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_resume";
      await createExperiment(page, fx.sessionId, experimentId, { cellCount: 4 });

      const queuedBefore = await getStatus(page, fx.sessionId, experimentId);
      const queuedAttemptId = queuedBefore.body.cells[1].active_attempt_id;

      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_0", status: "interrupted" },
        { cell_id: "cell_2", status: "failed" },
        { cell_id: "cell_3", status: "completed" },
        // cell_1 stays queued (never-started).
      ]);

      const before = await getStatus(page, fx.sessionId, experimentId);
      const interruptedBefore = before.body.cells[0].active_attempt_id;
      expect(interruptedBefore).toBeNull();

      const resumeRes = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/resume?session=${fx.sessionId}`
      );
      expect(resumeRes.status()).toBe(200);
      const resumeBody = await resumeRes.json();
      expect(resumeBody.status).toBe("ok");
      expect(resumeBody.experiment_id).toBe(experimentId);
      expect(resumeBody.resumed).toBe(1);
      expect(resumeBody.created_attempts).toHaveLength(1);
      expect(resumeBody.created_attempts[0].cell_id).toBe("cell_0");
      expect(resumeBody.created_attempts[0].run_id).toMatch(/^run_/);
      expect(resumeBody.resumable_cells).toEqual(["cell_0", "cell_1"]);

      const after = await getStatus(page, fx.sessionId, experimentId);
      const byId = Object.fromEntries(after.body.cells.map((c) => [c.cell_id, c]));
      // Interrupted cell resumed → fresh attempt identity.
      expect(byId.cell_0.status).toBe("queued");
      expect(byId.cell_0.active_attempt_id).toMatch(/^run_/);
      expect(byId.cell_0.active_attempt_id).not.toBe(interruptedBefore);
      // Never-started queued cell keeps its existing queued attempt.
      expect(byId.cell_1.status).toBe("queued");
      expect(byId.cell_1.active_attempt_id).toBe(queuedAttemptId);
      // Failed / completed are skipped.
      expect(byId.cell_2.status).toBe("failed");
      expect(byId.cell_2.active_attempt_id).toBeNull();
      expect(byId.cell_3.status).toBe("completed");
      expectCounts(after.body, { queued: 2, failed: 1, completed: 1 });

      // Double resume: no duplicate attempts — resumed 0, attempts unchanged.
      const again = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/resume?session=${fx.sessionId}`
      );
      expect(again.status()).toBe(200);
      const againBody = await again.json();
      expect(againBody.resumed).toBe(0);
      expect(againBody.created_attempts).toEqual([]);
      const afterAgain = await getStatus(page, fx.sessionId, experimentId);
      const byId2 = Object.fromEntries(afterAgain.body.cells.map((c) => [c.cell_id, c]));
      expect(byId2.cell_0.active_attempt_id).toBe(byId.cell_0.active_attempt_id);
      expect(byId2.cell_1.active_attempt_id).toBe(byId.cell_1.active_attempt_id);

      // No resumable cells → truthful 409.
      const exp2 = "exp_v2_resume_none";
      await createExperiment(page, fx.sessionId, exp2, { cellCount: 2 });
      await setCellStates(page, fx.sessionId, exp2, [
        { cell_id: "cell_0", status: "completed" },
        { cell_id: "cell_1", status: "failed" },
      ]);
      const none = await page.request.post(
        `/comfymodal/history-v2/experiments/${exp2}/resume?session=${fx.sessionId}`
      );
      expect(none.status()).toBe(409);
      expect(await none.json()).toEqual({
        status: "error",
        message: "no resumable cells",
        code: "NO_RESUMABLE_CELLS",
        experiment_id: exp2,
      });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("7. retry keeps cell identity, mints a new attempt, rejects non-failed cells", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const experimentId = "exp_v2_retry";
      await createExperiment(page, fx.sessionId, experimentId, { cellCount: 4 });

      await setCellStates(page, fx.sessionId, experimentId, [
        { cell_id: "cell_1", status: "failed", error: "worker restart exceeded retry budget" },
        { cell_id: "cell_2", status: "completed" },
      ]);

      const before = await getStatus(page, fx.sessionId, experimentId);
      const failedCell = before.body.cells[1];
      expect(failedCell.status).toBe("failed");
      expect(failedCell.active_attempt_id).toBeNull();
      expect(failedCell.generation_id).toBe("gen_" + experimentId + "_1");
      expect(failedCell.position).toBe(1);

      const retryRes = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/cells/cell_1/retry?session=${fx.sessionId}`
      );
      expect(retryRes.status()).toBe(200);
      const retryBody = await retryRes.json();
      expect(retryBody.status).toBe("ok");
      expect(retryBody.experiment_id).toBe(experimentId);
      expect(retryBody.cell_id).toBe("cell_1");
      expect(retryBody.retried).toBe(true);
      expect(retryBody.run_id).toMatch(/^run_/);

      const after = await getStatus(page, fx.sessionId, experimentId);
      const byId = Object.fromEntries(after.body.cells.map((c) => [c.cell_id, c]));
      // Same cell identity, fresh attempt identity, error cleared.
      expect(byId.cell_1.cell_id).toBe("cell_1");
      expect(byId.cell_1.position).toBe(1);
      expect(byId.cell_1.generation_id).toBe("gen_" + experimentId + "_1");
      expect(byId.cell_1.status).toBe("queued");
      expect(byId.cell_1.active_attempt_id).toBe(retryBody.run_id);
      expect(byId.cell_1.active_attempt_id).not.toBe(failedCell.active_attempt_id);
      expect(byId.cell_1.error).toBeNull();
      // cell_0 + cell_1 + cell_3 queued, cell_2 completed.
      expectCounts(after.body, { queued: 3, completed: 1 });

      // A non-failed cell returns 409 CELL_NOT_FAILED.
      const nonFailed = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/cells/cell_2/retry?session=${fx.sessionId}`
      );
      expect(nonFailed.status()).toBe(409);
      expect(await nonFailed.json()).toEqual({
        status: "error",
        message: "only a failed cell can be retried",
        code: "CELL_NOT_FAILED",
        experiment_id: experimentId,
        cell_id: "cell_2",
      });

      // Unknown cell → 404 CELL_NOT_FOUND.
      const missing = await page.request.post(
        `/comfymodal/history-v2/experiments/${experimentId}/cells/cell_99/retry?session=${fx.sessionId}`
      );
      expect(missing.status()).toBe(404);
      expect(await missing.json()).toMatchObject({
        status: "error",
        message: "cell not found",
        code: "CELL_NOT_FOUND",
      });

      // Retry is per-cell: siblings untouched.
      const final = await getStatus(page, fx.sessionId, experimentId);
      expect(final.body.cells[2].status).toBe("completed");
      expect(final.body.cells[3].status).toBe("queued");
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });

  test("8. create validation: missing id 400, duplicate id 409", async ({ page }) => {
    const fx = await setupFakeTest(page);
    try {
      const noId = await page.request.post("/comfymodal/studio/experiment-v2", {
        data: {
          sessionId: fx.sessionId,
          name: "No Id",
          definition: BASE_DEFINITION,
        },
      });
      expect(noId.status()).toBe(400);
      expect(await noId.json()).toEqual({
        status: "error",
        message: "experiment_id is required",
        code: "INVALID_DEFINITION",
        errors: [{ field: "experiment_id" }],
      });

      const banned = await page.request.post("/comfymodal/studio/experiment-v2", {
        data: {
          sessionId: fx.sessionId,
          experiment_id: "exp_v2_banned_cells",
          name: "Banned cells",
          definition: BASE_DEFINITION,
          cells: [],
        },
      });
      expect(banned.status()).toBe(400);
      expect(await banned.json()).toMatchObject({ status: "error", code: "INVALID_DEFINITION" });

      const experimentId = "exp_v2_dup";
      const first = await createExperiment(page, fx.sessionId, experimentId, { cellCount: 2 });
      expect(first.http).toBe(200);

      const second = await createExperiment(page, fx.sessionId, experimentId, { cellCount: 2 });
      expect(second.http).toBe(409);
      expect(second.body).toEqual({
        status: "error",
        message: "experiment already exists",
        code: "EXPERIMENT_EXISTS",
        experiment_id: experimentId,
      });
      fx.assertNoConsoleErrors();
    } finally {
      fx.guard.dispose();
    }
  });
});
