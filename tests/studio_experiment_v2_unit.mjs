// Modal Studio — D5 Modern Experiment API + Controller Unit Tests
//
// Executable behavioral tests for the additive D5 surface:
//   - API helpers (web/studio-backend-api.js): URL + payload wiring for
//     runExperimentV2 / getExperimentV2Status / cancelExperimentV2 /
//     resumeExperiment / retryCell.
//   - repository methods (web/history-v2-repository.js): retryExperiment /
//     resumeExperiment / retryCell / cancelExperiment on the modern routes.
//   - per-Experiment controller (web/studio-playground-run.js): fixed cell
//     order, progress counts/text, stale-attempt isolation, terminal
//     first-wins, duplicate action guards, popup detach behavior.
//
// No browser, no DOM, plain Node.  fetch is stubbed where API paths are
// exercised; the controller is driven with injected actions + a fake event
// source so nothing touches the network.
//
// Run: node tests/studio_experiment_v2_unit.mjs

import assert from "node:assert/strict";
import {
  runExperimentV2,
  getExperimentV2Status,
  cancelExperimentV2,
  resumeExperiment,
  retryCell,
} from "../web/studio-backend-api.js";
import {
  createHistoryRepository,
} from "../web/history-v2-repository.js";
import {
  createExperimentRunController,
  normalizeExperimentV2Cell,
  normalizeExperimentV2Status,
  countExperimentCells,
  formatExperimentProgress,
} from "../web/studio-playground-run.js";

// ── Helpers ──────────────────────────────────────────────────────────────

function section(name) {
  console.log("PASS: " + name);
}

/** Stub global fetch, recording {url, method, body}. */
function stubFetch(responses) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = function (url, options) {
    const req = {
      url: String(url),
      method: (options && options.method) || "GET",
      body: options && options.body != null ? options.body : null,
    };
    calls.push(req);
    const data = responses && typeof responses === "function"
      ? responses(req)
      : (responses && typeof responses === "object" ? responses[req.url] : {});
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve(data || {}),
    });
  };
  return {
    calls,
    restore() { globalThis.fetch = original; },
  };
}

/** Fake ComfyUI event bus used to drive the experiment controller. */
function makeFakeApi() {
  const handlers = {};
  return {
    api: {
      addEventListener: (n, h) => { (handlers[n] = handlers[n] || []).push(h); },
      removeEventListener: (n, h) => {
        if (!handlers[n]) return;
        const idx = handlers[n].indexOf(h);
        if (idx !== -1) handlers[n].splice(idx, 1);
      },
    },
    emit: (name, detail) => (handlers[name] || []).forEach((h) => h({ detail })),
  };
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

// ── 1. API: runExperimentV2 POSTs to /studio/experiment-v2 ───────────────

{
  const stub = stubFetch({ "/comfymodal/studio/experiment-v2": { experiment_id: "exp_v2_1", cell_count: 4 } });
  try {
    const res = await runExperimentV2("/comfymodal", { workflow_id: "wf1", concurrency: 6 });
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url, "/comfymodal/studio/experiment-v2");
    assert.deepEqual(JSON.parse(stub.calls[0].body), { workflow_id: "wf1", concurrency: 6 });
    assert.equal(res.experiment_id, "exp_v2_1");
  } finally { stub.restore(); }
  section("1. runExperimentV2 POST /studio/experiment-v2");
}

// ── 2. API: status is the frozen modern route ────────────────────────────

{
  const stub = stubFetch({ "/comfymodal/history-v2/experiments/exp_v2_1/status": { status: "running" } });
  try {
    const res = await getExperimentV2Status("/comfymodal", "exp_v2_1");
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].method, "GET");
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/experiments/exp_v2_1/status");
    assert.equal(stub.calls[0].body, null);
    assert.equal(res.status, "running");
    assert.equal(await getExperimentV2Status("/comfymodal", ""), null, "missing id → null");
  } finally { stub.restore(); }
  section("2. getExperimentV2Status GET /history-v2/experiments/{id}/status");
}

// ── 3. API: cancel / resume / retryCell POST to modern routes, no bodies ──

{
  const stub = stubFetch({
    "/comfymodal/history-v2/experiments/exp_v2_1/cancel": { accepted: true },
    "/comfymodal/history-v2/experiments/exp_v2_1/resume": { accepted: true },
    "/comfymodal/history-v2/experiments/exp_v2_1/cells/cell_7/retry": { accepted: true },
  });
  try {
    await cancelExperimentV2("/comfymodal", "exp_v2_1");
    await resumeExperiment("/comfymodal", "exp_v2_1");
    await retryCell("/comfymodal", "exp_v2_1", "cell_7");

    assert.equal(stub.calls.length, 3);
    const [cancelReq, resumeReq, retryReq] = stub.calls;
    assert.equal(cancelReq.method, "POST");
    assert.equal(cancelReq.url, "/comfymodal/history-v2/experiments/exp_v2_1/cancel");
    assert.equal(cancelReq.body, null, "cancel sends no JSON body");
    assert.equal(resumeReq.method, "POST");
    assert.equal(resumeReq.url, "/comfymodal/history-v2/experiments/exp_v2_1/resume");
    assert.equal(resumeReq.body, null, "resume sends no JSON body");
    assert.equal(retryReq.method, "POST");
    assert.equal(retryReq.url, "/comfymodal/history-v2/experiments/exp_v2_1/cells/cell_7/retry");
    assert.equal(retryReq.body, null, "retryCell sends no JSON body");
  } finally { stub.restore(); }
  section("3. cancel/resume/retryCell POST modern routes, no bodies");
}

// ── 4. Repository: retryCell/resume/cancel use modern routes; retryExperiment is unavailable ──

{
  const statusPayload = {
    experiment_id: "exp_v2_9",
    status: "completed_with_failures",
    cells: [
      { cell_id: "c1", status: "completed" },
      { cell_id: "c2", status: "failed" },
      { cell_id: "c3", status: "failed" },
    ],
  };
  const stub = stubFetch((req) => {
    if (req.url.indexOf("/status") !== -1) return statusPayload;
    if (req.url.indexOf("/retry") !== -1) return { accepted: true };
    return { accepted: true };
  });
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });

    // D5 forbids automatic Retry-all: retryExperiment is unavailable and must
    // never submit failed cells through the cell retry route.
    const retried = await repo.retryExperiment("exp_v2_9");
    assert.equal(retried.accepted, false, "retryExperiment is unavailable");
    const retryCallsAfterExperiment = stub.calls.filter((c) => c.url.indexOf("/retry") !== -1);
    assert.equal(retryCallsAfterExperiment.length, 0,
      "retryExperiment never calls any cell retry route");

    // Per-cell retry is the ONLY retry path.
    stub.calls.length = 0;
    await repo.retryCell("exp_v2_9", "c2");
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].method, "POST");
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/experiments/exp_v2_9/cells/c2/retry");

    stub.calls.length = 0;
    await repo.resumeExperiment("exp_v2_9");
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/experiments/exp_v2_9/resume");
    assert.equal(stub.calls[0].method, "POST");

    stub.calls.length = 0;
    await repo.cancelExperiment("exp_v2_9");
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].url, "/comfymodal/history-v2/experiments/exp_v2_9/cancel");

    const deferredGen = await repo.generateOriginal("gen_1", 0);
    assert.equal(deferredGen.accepted, false, "generateOriginal stays deferred");
    const deferredCell = await repo.generateOriginalForCell("exp_v2_9", "c1");
    assert.equal(deferredCell.accepted, false, "generateOriginalForCell stays deferred");
  } finally { stub.restore(); }
  section("4. Repository: retryCell-only retry; retryExperiment unavailable");
}

// ── 5. Normalization: snake_case + camelCase, backend counts preferred ───

{
  const norm = normalizeExperimentV2Status({
    experiment_id: "exp_v2_2",
    status: "running",
    total: 3,
    counts: { queued: 1, running: 1, completed: 1 },
    cells: [
      { cell_id: "c1", status: "success", attempt_id: "run_1", duration_ms: 1200 },
      { cellId: "c2", status: "in_progress", runId: "run_2" },
      { cell_id: "c3", status: "pending" },
    ],
  });
  assert.equal(norm.experimentId, "exp_v2_2");
  assert.equal(norm.status, "running");
  assert.equal(norm.total, 3);
  assert.equal(norm.counts.completed, 1, "backend counts preferred");
  assert.equal(norm.counts.running, 1);
  assert.equal(norm.counts.queued, 1);
  assert.equal(norm.cells.length, 3);
  assert.equal(norm.cells[0].status, "completed", "success alias → completed");
  assert.equal(norm.cells[0].attemptId, "run_1");
  assert.equal(norm.cells[0].durationMs, 1200);
  assert.equal(norm.cells[1].status, "running", "in_progress alias → running");
  assert.equal(norm.cells[1].cellId, "c2", "camelCase cellId read");
  assert.equal(norm.cells[1].runId, "run_2", "camelCase runId read");
  assert.equal(norm.cells[2].status, "queued", "pending alias → queued");

  const derived = normalizeExperimentV2Status({
    cells: [
      { cell_id: "c1", status: "completed" },
      { cell_id: "c2", status: "failed" },
    ],
  });
  assert.equal(derived.counts.completed, 1, "cell-fold fallback when no backend counts");
  assert.equal(derived.counts.failed, 1);

  // D1 status payload fields: position, axis labels/values, output urls,
  // attempts, workflow/preset ids + names (snake_case and camelCase).
  const rich = normalizeExperimentV2Cell({
    cell_id: "cell_7",
    position: 3,
    index: 3,
    status: "running",
    attempt_id: "run_5",
    axis_labels: { x: "Seed", y: "Steps" },
    axis_values: { x: "42", y: "20" },
    preview_url: "/preview.png",
    original_url: "/original.png",
    workflow_id: "wf_1",
    workflow_name: "Portrait Pro",
    workflow_version_id: "ver_9",
    preset_id: "preset_a",
    preset_name: "Classic",
    attempts: [
      { run_id: "run_4", status: "failed", duration_ms: 900 },
      { run_id: "run_5", status: "running", duration_ms: 400 },
    ],
  }, 3);
  assert.equal(rich.cellId, "cell_7");
  assert.equal(rich.position, 3, "position normalized");
  assert.equal(rich.status, "running");
  assert.equal(rich.attemptId, "run_5");
  assert.deepEqual(rich.axisLabels, { x: "Seed", y: "Steps" }, "axis_labels snake_case read");
  assert.deepEqual(rich.axisValues, { x: "42", y: "20" }, "axis_values snake_case read");
  assert.equal(rich.previewUrl, "/preview.png");
  assert.equal(rich.originalUrl, "/original.png");
  assert.equal(rich.workflowId, "wf_1");
  assert.equal(rich.workflowName, "Portrait Pro", "workflow_name read");
  assert.equal(rich.workflowVersionId, "ver_9");
  assert.equal(rich.presetId, "preset_a");
  assert.equal(rich.presetName, "Classic", "preset_name read");
  assert.equal(rich.attempts.length, 2, "attempt history normalized");
  assert.equal(rich.attempts[0].attemptId, "run_4");
  assert.equal(rich.attempts[0].status, "failed");
  assert.equal(rich.attempts[0].durationMs, 900);

  // camelCase variant of the same fields.
  const camel = normalizeExperimentV2Cell({
    cellId: "cell_8",
    position: 1,
    status: "queued",
    runId: "run_6",
    axisLabels: { x: "CFG" },
    axisValues: { x: "7" },
    previewUrl: "/p.png",
    originalUrl: "/o.png",
    workflowId: "wf_2",
    workflowName: "Landscape",
    workflowVersionId: "ver_2",
    presetId: "preset_b",
    presetName: "Wide",
  }, 1);
  assert.equal(camel.cellId, "cell_8");
  assert.equal(camel.position, 1);
  assert.equal(camel.runId, "run_6");
  assert.deepEqual(camel.axisLabels, { x: "CFG" }, "axisLabels camelCase read");
  assert.deepEqual(camel.axisValues, { x: "7" }, "axisValues camelCase read");
  assert.equal(camel.previewUrl, "/p.png");
  assert.equal(camel.originalUrl, "/o.png");
  assert.equal(camel.workflowName, "Landscape");
  assert.equal(camel.workflowVersionId, "ver_2");
  assert.equal(camel.presetName, "Wide");
  section("5. normalizeExperimentV2Status snake/camel + counts preference");
}

// ── 6. countExperimentCells + formatExperimentProgress ───────────────────

{
  const counts = countExperimentCells([
    { status: "completed" }, { status: "completed" }, { status: "running" },
    { status: "queued" }, { status: "failed" }, { status: "canceled" },
    { status: "interrupted" },
  ]);
  assert.deepEqual(counts, {
    queued: 1, running: 1, completed: 2, failed: 1, canceled: 1, interrupted: 1,
  });
  assert.equal(
    formatExperimentProgress({ completed: 18, running: 6, queued: 16 }, 40),
    "18/40 complete \u00b7 6 running \u00b7 16 queued",
  );
  assert.equal(
    formatExperimentProgress({ completed: 2, failed: 1, canceled: 1, interrupted: 1 }, 5),
    "2/5 complete \u00b7 1 failures \u00b7 1 canceled \u00b7 1 interrupted",
  );
  section("6. countExperimentCells + formatExperimentProgress");
}

// ── 7. Controller: fixed order + progress, backend counts preferred ──────

{
  const actionCalls = { cancel: 0, resume: 0, retry: [] };
  const actions = {
    cancel: async () => { actionCalls.cancel++; return { accepted: true }; },
    resume: async () => { actionCalls.resume++; return { accepted: true }; },
    retryCell: async (id, cellId) => { actionCalls.retry.push(cellId); return { accepted: true }; },
  };
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_3", actions });

  // Backend order: completed cell first, running second, queued third.
  ctrl.reconcile({
    experiment_id: "exp_v2_3",
    status: "running",
    total: 3,
    counts: { queued: 1, running: 1, completed: 1 },
    cells: [
      { cell_id: "c2", status: "completed" },
      { cell_id: "c1", status: "running", attempt_id: "run_1" },
      { cell_id: "c3", status: "queued" },
    ],
  });
  const state = ctrl.getState();
  assert.equal(state.experimentId, "exp_v2_3");
  assert.equal(state.status, "running");
  assert.deepEqual(state.cells.map((c) => c.cellId), ["c2", "c1", "c3"], "backend order preserved, never sorted by completion");
  assert.deepEqual(state.counts, { queued: 1, running: 1, completed: 1, failed: 0, canceled: 0, interrupted: 0 });
  assert.equal(state.progressText, "1/3 complete \u00b7 1 running \u00b7 1 queued");

  // A later poll that omits cells must not drop existing records.
  ctrl.reconcile({ experiment_id: "exp_v2_3", status: "running", total: 3, counts: { running: 1 }, cells: [
    { cell_id: "c1", status: "running" },
  ] });
  const kept = ctrl.getCells();
  assert.equal(kept.length, 3, "existing cells preserved when payload omits them");
  assert.equal(kept[0].cellId, "c2");
  assert.equal(kept[0].status, "completed", "terminal cell never regresses");
  section("7. Controller fixed cell order + progress");
}

// ── 7b. First build orders by position/index; later polls never reorder ──

{
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_3b", actions: {} });

  // Backend returns cells OUT of order; first build must use position.
  ctrl.reconcile({
    experiment_id: "exp_v2_3b",
    status: "running",
    total: 3,
    cells: [
      { cell_id: "c3", status: "queued", position: 2, index: 2 },
      { cell_id: "c1", status: "running", attempt_id: "run_1", position: 0, index: 0 },
      { cell_id: "c2", status: "queued", position: 1, index: 1 },
    ],
  });
  assert.deepEqual(ctrl.getCells().map((c) => c.cellId), ["c1", "c2", "c3"],
    "first build orders cells by backend position");

  // A later poll with a different array order must not reorder existing cells.
  ctrl.reconcile({
    experiment_id: "exp_v2_3b",
    status: "running",
    total: 3,
    cells: [
      { cell_id: "c2", status: "running", attempt_id: "run_2", position: 1, index: 1 },
      { cell_id: "c3", status: "queued", position: 2, index: 2 },
      { cell_id: "c1", status: "completed", attempt_id: "run_1", position: 0, index: 0 },
    ],
  });
  const later = ctrl.getCells();
  assert.deepEqual(later.map((c) => c.cellId), ["c1", "c2", "c3"], "later polls never reorder existing cells");
  assert.equal(later[0].status, "completed");
  assert.equal(later[1].status, "running", "same-attempt running poll applies to non-terminal cell");
  assert.equal(later[1].attemptId, "run_2");
  ctrl.dispose();
  section("7b. First build position order; later polls fixed");
}

// ── 8. Controller: terminal first-wins via event source ──────────────────

{
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_4",
    actions: { cancel: async () => ({ accepted: true }) },
  });
  const fake = makeFakeApi();
  ctrl.attach(fake.api);
  ctrl.reconcile({
    experiment_id: "exp_v2_4",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "running", attempt_id: "run_1" }],
  });

  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_4", cell_key: "c1", attempt_id: "run_1", step: 3, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler.step, 3, "matching attempt progress applied");

  fake.emit("experiment.event", {
    experiment_id: "exp_v2_4", type: "cell.completed",
    payload: { cell_key: "c1", attempt_id: "run_1" },
  });
  assert.equal(ctrl.getCells()[0].status, "completed", "cell terminal applied");

  // A later running poll cannot regress the terminal cell.
  ctrl.reconcile({ experiment_id: "exp_v2_4", status: "running", total: 1, cells: [
    { cell_id: "c1", status: "running", attempt_id: "run_1" },
  ] });
  assert.equal(ctrl.getCells()[0].status, "completed", "terminal first-wins on reconcile");
  ctrl.dispose();
  section("8. Controller terminal first-wins");
}

// ── 8b. Same-attempt terminal first-wins holds against other terminals ───

{
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_4b", actions: {} });
  ctrl.reconcile({
    experiment_id: "exp_v2_4b",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "running", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "running", attempt_id: "run_1", index: 1 },
    ],
  });
  // c1 completes; c2 fails — both terminal on attempt run_1.
  ctrl.reconcile({
    experiment_id: "exp_v2_4b",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "completed", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "failed", attempt_id: "run_1", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[0].status, "completed");
  assert.equal(ctrl.getCells()[1].status, "failed");

  // SAME attempt, DIFFERENT terminal status → first terminal wins.
  ctrl.reconcile({
    experiment_id: "exp_v2_4b",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "failed", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "completed", attempt_id: "run_1", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[0].status, "completed",
    "same-attempt failed poll cannot overwrite completed");
  assert.equal(ctrl.getCells()[1].status, "failed",
    "same-attempt completed poll cannot overwrite failed");

  // SAME attempt, non-terminal poll → terminal still holds.
  ctrl.reconcile({
    experiment_id: "exp_v2_4b",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "running", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "running", attempt_id: "run_1", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[0].status, "completed", "same-attempt running cannot regress completed");
  assert.equal(ctrl.getCells()[1].status, "failed", "same-attempt running cannot regress failed");
  ctrl.dispose();
  section("8b. Same-attempt terminal first-wins against other terminals");
}

// ── 8c. New-attempt retry/resume replaces the active cell status ─────────

{
  const actionCalls = { retry: [], resume: 0 };
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_4c",
    actions: {
      retryCell: async (id, cellId) => { actionCalls.retry.push(cellId); return { accepted: true }; },
      resume: async () => { actionCalls.resume++; return { accepted: true }; },
    },
  });
  ctrl.reconcile({
    experiment_id: "exp_v2_4c",
    status: "completed_with_failures",
    total: 2,
    cells: [
      { cell_id: "c1", status: "completed", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "failed", attempt_id: "run_1", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[1].status, "failed");

  // Retry c2 → NEW attempt run_2, still the same cell position.
  assert.equal((await ctrl.retryCell("c2")).accepted, true);
  assert.deepEqual(actionCalls.retry, ["c2"], "retry action targets the failed cell");
  ctrl.reconcile({
    experiment_id: "exp_v2_4c",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "completed", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "running", attempt_id: "run_2", index: 1 },
    ],
  });
  const afterRetry = ctrl.getCells();
  assert.equal(afterRetry[1].cellId, "c2", "cell keeps its position on retry");
  assert.equal(afterRetry[1].status, "running", "deliberate retry replaces the failed status");
  assert.equal(afterRetry[1].attemptId, "run_2", "new attempt identity recorded");

  // c2 completes on run_2; a stale run_1 completion must not regress it.
  ctrl.reconcile({
    experiment_id: "exp_v2_4c",
    status: "completed",
    total: 2,
    cells: [
      { cell_id: "c1", status: "completed", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "completed", attempt_id: "run_2", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[1].status, "completed");
  assert.equal(ctrl.getCells()[1].attemptId, "run_2");

  // A poll saying interrupted on the SAME attempt run_1 cannot regress c1.
  ctrl.reconcile({
    experiment_id: "exp_v2_4c",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "interrupted", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "completed", attempt_id: "run_2", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[0].status, "completed",
    "same-attempt interrupted poll cannot regress completed");
  ctrl.dispose();
  section("8c. New-attempt retry replaces active cell status");
}

// ── 8e. Deliberate resume opens a new attempt on interrupted cells ───────

{
  const actionCalls = { resume: 0 };
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_4e",
    actions: { resume: async () => { actionCalls.resume++; return { accepted: true }; } },
  });
  ctrl.reconcile({
    experiment_id: "exp_v2_4e",
    status: "interrupted",
    total: 2,
    cells: [
      { cell_id: "c1", status: "interrupted", attempt_id: "run_1", index: 0 },
      { cell_id: "c2", status: "completed", attempt_id: "run_1", index: 1 },
    ],
  });
  assert.equal(ctrl.getCells()[0].status, "interrupted");

  // Resume opens a NEW attempt for the interrupted cell (run_3).
  assert.equal((await ctrl.resume()).accepted, true);
  assert.equal(actionCalls.resume, 1);
  ctrl.reconcile({
    experiment_id: "exp_v2_4e",
    status: "running",
    total: 2,
    cells: [
      { cell_id: "c1", status: "running", attempt_id: "run_3", index: 0 },
      { cell_id: "c2", status: "completed", attempt_id: "run_1", index: 1 },
    ],
  });
  const resumed = ctrl.getCells();
  assert.equal(resumed[0].cellId, "c1", "resume keeps cell position");
  assert.equal(resumed[0].status, "running", "deliberate resume replaces interrupted with new attempt");
  assert.equal(resumed[0].attemptId, "run_3");
  assert.equal(resumed[1].status, "completed", "completed cell untouched by resume");
  ctrl.dispose();
  section("8e. Deliberate resume opens a new attempt on interrupted cells");
}

// ── 8d. Bare poll with a different attempt_id cannot regress a terminal ──

{
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_4d", actions: {} });
  ctrl.reconcile({
    experiment_id: "exp_v2_4d",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "failed", attempt_id: "run_1", index: 0 }],
  });
  // No retryCell/resume was requested: a poll reporting a new attempt_id is
  // stale evidence and must NOT replace the failed status.
  ctrl.reconcile({
    experiment_id: "exp_v2_4d",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "running", attempt_id: "run_OTHER", index: 0 }],
  });
  assert.equal(ctrl.getCells()[0].status, "failed", "bare new-attempt poll cannot regress terminal cell");
  assert.equal(ctrl.getCells()[0].attemptId, "run_1", "active attempt identity unchanged");
  ctrl.dispose();
  section("8d. Bare new-attempt poll cannot regress a terminal cell");
}

// ── 9. Controller: stale attempt events are ignored ──────────────────────

{
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_5", actions: {} });
  const fake = makeFakeApi();
  ctrl.attach(fake.api);
  ctrl.reconcile({
    experiment_id: "exp_v2_5",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "running", attempt_id: "run_2" }],
  });

  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_5", cell_key: "c1", attempt_id: "run_1", step: 9, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler, null, "stale attempt progress dropped");

  fake.emit("experiment.event", {
    experiment_id: "exp_v2_5", type: "cell.completed",
    payload: { cell_key: "c1", attempt_id: "run_1" },
  });
  assert.equal(ctrl.getCells()[0].status, "running", "stale attempt terminal dropped");

  fake.emit("experiment.event", {
    experiment_id: "exp_v2_5", type: "cell.completed",
    payload: { cell_key: "c1", attempt_id: "run_2" },
  });
  assert.equal(ctrl.getCells()[0].status, "completed", "active attempt terminal applied");
  ctrl.dispose();
  section("9. Controller stale attempt isolation");
}

// ── 10. Controller: duplicate cancel/resume/retry guards ─────────────────

{
  const gate = deferred();
  let cancelCalls = 0;
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_6",
    actions: {
      cancel: () => { cancelCalls++; return gate.promise; },
      resume: async () => ({ accepted: true }),
      retryCell: async (id, cellId) => ({ accepted: true }),
    },
  });
  ctrl.reconcile({
    experiment_id: "exp_v2_6",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "failed" }],
  });

  const p1 = ctrl.cancel();
  const p2 = ctrl.cancel();
  const p3 = ctrl.cancel();
  assert.equal(cancelCalls, 1, "cancel is single-flight while in flight");
  const guarded2 = await p2;
  const guarded3 = await p3;
  assert.equal(guarded2.guarded, true, "duplicate cancel guarded while in flight");
  assert.equal(guarded3.guarded, true, "all duplicates guarded while in flight");
  gate.resolve({ accepted: true });
  const done = await p1;
  assert.equal(done.accepted, true);
  assert.equal(cancelCalls, 1, "only one network cancel despite three calls");

  const r1 = ctrl.resume();
  const r2 = ctrl.resume();
  assert.equal((await r1).accepted, true, "first resume accepted");
  assert.equal((await r2).guarded, true, "duplicate resume guarded (single-flight)");

  const t1 = ctrl.retryCell("c1");
  const t2 = ctrl.retryCell("c1");
  assert.equal((await t1).accepted, true, "first retry accepted");
  assert.equal((await t2).guarded, true, "duplicate retry guarded (single-flight per cell)");
  assert.equal((await ctrl.retryCell("c2")).accepted, false, "retry of missing cell rejected");
  assert.equal((await ctrl.retryCell("c2")).message, "Cell is not failed");
  ctrl.dispose();
  section("10. Controller duplicate action guards");
}

// ── 11. Controller: popup detach / reattach / dispose without cancel ─────

{
  const fake = makeFakeApi();
  let cancelCalls = 0;
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_7",
    actions: { cancel: async () => { cancelCalls++; return { accepted: true }; } },
  });
  ctrl.reconcile({
    experiment_id: "exp_v2_7",
    status: "running",
    total: 1,
    cells: [{ cell_id: "c1", status: "running", attempt_id: "run_1" }],
  });

  ctrl.attach(fake.api);
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_7", cell_key: "c1", attempt_id: "run_1", step: 4, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler.step, 4, "attached source applies events");

  // Detach: events stop arriving even though the fake bus still holds them.
  ctrl.detachEventSource();
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_7", cell_key: "c1", attempt_id: "run_1", step: 8, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler.step, 4, "detached source events are dropped");

  // Reattach: events flow again, and durable state survived the detach.
  ctrl.attach(fake.api);
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_7", cell_key: "c1", attempt_id: "run_1", step: 7, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler.step, 7, "reattached source applies events");
  assert.equal(ctrl.getState().status, "running", "durable state survives detach/reattach");

  // dispose detaches and drops subscribers but never cancels.
  const subscribed = ctrl.subscribe(() => {});
  subscribed();
  ctrl.dispose();
  assert.equal(cancelCalls, 0, "dispose never calls cancel");
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_7", cell_key: "c1", attempt_id: "run_1", step: 9, max: 10,
  });
  assert.equal(ctrl.getCells()[0].sampler.step, 7, "post-dispose events are ignored");
  section("11. Controller popup detach/reattach + dispose without cancel");
}

// ── 12. Controller: subscribe delivers snapshots ─────────────────────────

{
  const seen = [];
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_8", actions: {} });
  const unsub = ctrl.subscribe((s) => seen.push(s.status));
  ctrl.reconcile({
    experiment_id: "exp_v2_8",
    status: "running",
    total: 2,
    cells: [{ cell_id: "c1", status: "queued" }],
  });
  ctrl.reconcile({
    experiment_id: "exp_v2_8",
    status: "completed",
    total: 2,
    cells: [{ cell_id: "c1", status: "completed" }],
  });
  assert.deepEqual(seen, ["running", "completed"], "subscriber sees each reconcile snapshot");
  unsub();
  ctrl.reconcile({ experiment_id: "exp_v2_8", status: "canceled", total: 2, cells: [] });
  assert.deepEqual(seen, ["running", "completed"], "unsubscribe stops notifications");
  ctrl.dispose();
  section("12. Controller subscribe snapshots");
}

// ── 13. D5 correction: flat modern status payload ─────────────────────────
//
// The modern status endpoint returns a FLAT payload whose lifecycle status
// lives in `aggregate_status` while the top-level `status` is only the
// transport/envelope marker ("ok").  The previous normalize read `status`
// first and aliased "ok" → "completed", so a running experiment appeared
// complete.  These tests pin the correction: aggregate_status is
// authoritative when present and the envelope status never becomes lifecycle
// evidence.  Item-wrapped / legacy payloads (no aggregate_status) keep the
// inner lifecycle status source.

{
  const flat = (aggregateStatus, cellStatuses, experimentId) => ({
    status: "ok",
    experiment_id: experimentId || "exp_v2_flat",
    aggregate_status: aggregateStatus,
    total: cellStatuses.length,
    counts: countExperimentCells(cellStatuses.map((s) => ({ status: s }))),
    cells: cellStatuses.map((s, i) => ({ cell_id: "cell_" + i, status: s })),
  });

  // Exact flat shapes: every aggregate status is preserved verbatim.
  const running = normalizeExperimentV2Status(flat("running", ["queued", "running"]));
  assert.equal(running.status, "running",
    "aggregate_status 'running' survives — the old bug turned it into 'completed'");
  assert.equal(running.experimentId, "exp_v2_flat");

  assert.equal(
    normalizeExperimentV2Status(flat("completed", ["completed", "completed"])).status,
    "completed",
  );
  assert.equal(
    normalizeExperimentV2Status(flat("completed_with_failures", ["completed", "failed"])).status,
    "completed_with_failures",
  );
  assert.equal(
    normalizeExperimentV2Status(flat("interrupted", ["completed", "interrupted"])).status,
    "interrupted",
  );
  assert.equal(
    normalizeExperimentV2Status(flat("canceled", ["completed", "canceled"])).status,
    "canceled",
  );

  // The envelope status is never lifecycle evidence when aggregate is
  // present: the same "ok" envelope resolves to the aggregate for each shape.
  assert.notEqual(running.status, "completed", "envelope 'ok' not aliased to completed");

  // Cell statuses completed/running/queued/failed pass through unchanged.
  const mix = normalizeExperimentV2Status(flat("running", ["completed", "running", "queued", "failed"]));
  assert.deepEqual(mix.cells.map((c) => c.status),
    ["completed", "running", "queued", "failed"],
    "flat payload cell statuses unchanged");
  assert.deepEqual(mix.counts,
    { queued: 1, running: 1, completed: 1, failed: 1, canceled: 0, interrupted: 0 },
    "flat payload counts preserved");

  // camelCase aggregateStatus is accepted too.
  assert.equal(
    normalizeExperimentV2Status({ status: "ok", experimentId: "exp_v2_camel", aggregateStatus: "interrupted", cells: [] }).status,
    "interrupted",
    "camelCase aggregateStatus read",
  );

  // Item-wrapped / legacy payloads (no aggregate_status) keep the inner
  // lifecycle status source — status/state/experiment_status are unchanged.
  assert.equal(normalizeExperimentV2Status({ status: "running", cells: [] }).status, "running",
    "item-wrapped inner status still valid");
  assert.equal(normalizeExperimentV2Status({ experiment_status: "canceled", cells: [] }).status, "canceled",
    "experiment_status fallback unchanged");
  assert.equal(normalizeExperimentV2Status({ state: "queued", cells: [] }).status, "queued",
    "state fallback unchanged");
  section("13. Flat modern status payload: aggregate_status authoritative");
}

// ── 14. D5 correction: controller lifecycle from flat payloads ────────────

{
  const flat = (aggregateStatus, cellStatuses, experimentId) => ({
    status: "ok",
    experiment_id: experimentId || "exp_v2_ctrl_flat",
    aggregate_status: aggregateStatus,
    total: cellStatuses.length,
    counts: countExperimentCells(cellStatuses.map((s) => ({ status: s }))),
    cells: cellStatuses.map((s, i) => ({ cell_id: "cell_" + i, status: s, attempt_id: "run_" + i })),
  });

  // A running flat poll keeps the experiment running (NOT completed).
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_ctrl_flat", actions: {} });
  ctrl.reconcile(flat("running", ["running", "queued"]));
  let st = ctrl.getState();
  assert.equal(st.status, "running", "flat running aggregate stays running — old bug completed it");
  assert.equal(ctrl.getCells()[0].status, "running");
  assert.equal(ctrl.getCells()[1].status, "queued");

  // The same "ok" envelope with a completed aggregate completes the run.
  ctrl.reconcile(flat("completed", ["completed", "completed"]));
  st = ctrl.getState();
  assert.equal(st.status, "completed", "flat completed aggregate completes the run");
  assert.equal(st.cells[0].status, "completed");

  // Terminal aggregate statuses land as-is on the controller.
  const terminalAggregates = {
    completed_with_failures: ["completed", "failed"],
    interrupted: ["completed", "interrupted"],
    canceled: ["completed", "canceled"],
  };
  for (const agg of Object.keys(terminalAggregates)) {
    const cellStatuses = terminalAggregates[agg];
    const c = createExperimentRunController({ experimentId: "exp_v2_term_" + agg, actions: {} });
    c.reconcile(flat(agg, cellStatuses));
    assert.equal(c.getState().status, agg, "flat aggregate " + agg + " preserved");
    assert.deepEqual(c.getCells().map((x) => x.status), cellStatuses, "cells for " + agg + " unchanged");
    c.dispose();
  }

  // Polling/status hydration continuation: running then completed flat polls
  // advance one controller and the subscriber sees both statuses.
  const seen = [];
  const sub = ctrl.subscribe((s) => seen.push(s.status));
  ctrl.reconcile(flat("running", ["running", "queued"]));
  ctrl.reconcile(flat("completed", ["completed", "completed"]));
  assert.deepEqual(seen, ["running", "completed"], "flat polls continue and hydrate status");
  sub();

  // Reconnect: durable state survives detach/reattach with flat payloads and
  // the attached event source streams against the flat-hydrated controller.
  const rc = createExperimentRunController({ experimentId: "exp_v2_reconnect", actions: {} });
  const fake = makeFakeApi();
  rc.reconcile(flat("running", ["running", "queued"], "exp_v2_reconnect"));
  rc.attach(fake.api);
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_reconnect", cell_key: "cell_0", attempt_id: "run_0", step: 2, max: 8,
  });
  assert.equal(rc.getCells()[0].sampler.step, 2, "flat-hydrated attached source streams");
  rc.detachEventSource();
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_reconnect", cell_key: "cell_0", attempt_id: "run_0", step: 9, max: 8,
  });
  assert.equal(rc.getCells()[0].sampler.step, 2, "detached flat-shape events dropped");
  rc.attach(fake.api);
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "exp_v2_reconnect", cell_key: "cell_0", attempt_id: "run_0", step: 5, max: 8,
  });
  assert.equal(rc.getCells()[0].sampler.step, 5, "reattached source streams after reconnect");
  assert.equal(rc.getState().status, "running", "flat-hydrated state survives reconnect");
  rc.dispose();
  ctrl.dispose();
  section("14. Controller lifecycle from flat payloads");
}

// ── 15. D5 guards held with the flat status flow ──────────────────────────

{
  // The aggregate vocabulary never leaks "partial": the flat
  // completed_with_failures shape normalizes to the canonical aggregate
  // status, not a partial alias.
  const withFailures = normalizeExperimentV2Status({
    status: "ok", experiment_id: "exp_v2_guard", aggregate_status: "completed_with_failures",
    counts: { completed: 1, failed: 1 }, total: 2,
    cells: [{ cell_id: "c0", status: "completed" }, { cell_id: "c1", status: "failed" }],
  });
  assert.equal(withFailures.status, "completed_with_failures", "completed_with_failures canonical");
  assert.equal(withFailures.status.includes("partial"), false, "no 'partial' in the aggregate status");

  // Generate Original remains deferred on the modern repository (no network).
  const stub = stubFetch({});
  try {
    const repo = await createHistoryRepository({ mode: "v2", apiBase: "/comfymodal" });
    const deferredGen = await repo.generateOriginal("gen_guard", 0);
    assert.equal(deferredGen.accepted, false, "generateOriginal stays deferred");
    const deferredCell = await repo.generateOriginalForCell("exp_v2_guard", "c0");
    assert.equal(deferredCell.accepted, false, "generateOriginalForCell stays deferred");
    assert.equal(stub.calls.length, 0, "deferred generateOriginal never calls the network");
  } finally { stub.restore(); }

  // Item-wrapped payload (inner lifecycle status) remains fully supported.
  const wrapped = normalizeExperimentV2Status({
    experiment_id: "exp_v2_wrap", status: "running", counts: { running: 1 }, total: 1,
    cells: [{ cell_id: "c0", status: "running" }],
  });
  assert.equal(wrapped.status, "running", "item-wrapped inner lifecycle status valid");
  section("15. D5 guards held with the flat status flow");
}

console.log("PASS: studio experiment v2 unit tests");
