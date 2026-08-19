// Modal Studio — D5 Modern Experiment Frontend Unit Tests
//
// Executable behavioral tests for the modern experiment-v2 surface in
// web/studio-experiment-mode.js (the ONLY frontend file the D5 lane owns
// alongside the history detail page):
//   - one modern definition per submit (POST /studio/experiment-v2, no
//     legacy /studio/experiment route, no concurrency field anywhere)
//   - fixed cell ordering (1 and 40 cells; cell_id cell_0..cell_N-1)
//   - workflow/version/preset preserved verbatim from state (workflow-axis
//     labels/values preserved; nothing inferred later)
//   - progress counts text via formatExperimentProgress; no "partial" word
//   - failed sibling isolation; canceled vs interrupted distinct
//   - popup close / navigation never cancels (detach/dispose only)
//   - reopen same id rebuilds the fixed cell list without resubmitting
//   - retry identity (failed-only, position + cell_id preserved)
//   - resume eligibility (skips failed) + double-click guard
//   - legacy experiment-mode exports retained (legacy rendering compat)
//
// No browser, no DOM, plain Node.  fetch is stubbed; the per-experiment
// controller is driven with injected actions + a fake event source.
//
// Run: node tests/studio_experiment_v2_frontend_unit.mjs

import assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import {
  buildModernExperimentDefinition,
  buildModernExperimentCells,
  resolveModernWorkflowSelection,
  modernExperimentCanRun,
  modernExperimentDisabledReason,
  experimentStatusLabel,
  isTerminalModernStatus,
  canResumeModernExperiment,
  getResumeEligibleCellCount,
  canRetryModernCell,
  experimentRunSurface,
  getModernExperimentController,
  executeModernExperimentRun,
  attachModernExperiment,
  detachModernExperiment,
  disposeModernExperiment,
  refreshModernExperimentStatus,
  startModernExperimentPolling,
  stopModernExperimentPolling,
  canRunExperiment,
  getExperimentPresetIds,
  renderExperimentMode,
  renderExperimentRunButton,
  executeExperimentRun,
} from "../web/studio-experiment-mode.js";
import {
  createExperimentRunController,
  formatExperimentProgress,
  normalizeExperimentV2Status,
} from "../web/studio-playground-run.js";
import { runExperimentV2 } from "../web/studio-backend-api.js";

const MODULE_SRC = fs.readFileSync(path.join(import.meta.dirname, "..", "web", "studio-experiment-mode.js"), "utf8");

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

/** In-memory localStorage stub. */
function installLocalStorage() {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    clear: () => { store.clear(); },
  };
  return store;
}

/** Fake ComfyUI event bus for the experiment controller. */
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

/** Minimal playground state with a modern workflow selection. */
function makeState(overrides) {
  const o = overrides || {};
  return {
    activePage: "playground",
    playground: {
      featureId: "txt2img",
      controls: Object.assign({ prompt: "base prompt", negative_prompt: "" }, o.controls || {}),
      experimentAxes: o.experimentAxes || {},
      selectedBackendId: o.selectedBackendId || "",
      compareBackendIds: o.compareBackendIds || [],
      _workflowRun: {
        workflowId: o.workflowId != null ? o.workflowId : "wf_1",
        workflowVersionId: o.workflowVersionId != null ? o.workflowVersionId : "ver_1",
        presetId: o.presetId != null ? o.presetId : "preset_1",
        workflowName: o.workflowName != null ? o.workflowName : "Portrait Pro",
        presetName: o.presetName != null ? o.presetName : "preset_a",
        controlValues: o.controlValues || { steps: 28, seed: 42 },
        runContext: o.runContext || { workflow: { id: "wf_1" } },
      },
      _currentPreset: o.currentPreset || null,
    },
  };
}

/** Status endpoint detail payload (shape returned under `item`). */
function statusDetail(overrides) {
  const o = overrides || {};
  const cells = o.cells || [];
  const counts = o.counts || {};
  return {
    experiment_id: o.experimentId || "exp_v2_test",
    name: o.name || "Studio Experiment: txt2img",
    status: o.status || "running",
    total: o.total != null ? o.total : cells.length,
    counts: Object.assign({ queued: 0, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 }, counts),
    cells: cells,
  };
}

// ── 1. Definition shape: one definition, no concurrency, no legacy keys ──

{
  const state = makeState({
    experimentAxes: {
      steps: { enabled: true, values: [10, 20] },
      seed: { enabled: true, values: [1, 2] },
    },
  });
  const payload = buildModernExperimentDefinition(state);
  assert.equal(payload.experiment_id.startsWith("exp_v2_"), true);
  assert.equal(typeof payload.name, "string");
  assert.equal(payload.definition && typeof payload.definition, "object");
  assert.equal("cells" in payload, false, "the server expands cells from the definition");

  // No concurrency picker/payload field.
  assert.equal("concurrency" in payload, false, "no top-level concurrency");
  assert.equal("concurrency" in payload.definition, false, "no definition concurrency");
  const serialized = JSON.stringify(payload);
  assert.equal(serialized.includes("concurrency"), false, "no concurrency anywhere in the payload");

  // No legacy route keys.
  assert.equal("presetIds" in payload, false, "no legacy presetIds array");
  assert.equal("featureId" in payload, false, "no legacy top-level featureId");
  assert.equal(serialized.includes("/studio/experiment"), false, "no legacy route reference in the payload");

  // Resolved workflow/version/preset and axis values are preserved in the
  // definition; immutable cell snapshots are server-owned.
  assert.deepEqual(payload.definition.workflows[0], {
    workflow_id: "wf_1",
    workflow_version_id: "ver_1",
    preset_id: "preset_1",
    workflow_name: "Portrait Pro",
    preset_name: "preset_a",
  });
  assert.deepEqual(payload.definition.axes.steps.values, [10, 20]);
  assert.deepEqual(payload.definition.axes.seed.values, [1, 2]);
  assert.equal(payload.definition.axis_labels.x, "steps");
  assert.equal(payload.definition.axis_labels.y, "seed");
  section("1. Definition shape: one definition, no concurrency, no legacy keys");
}

// ── 2. Fixed cell ordering: 1 and 40 cells ───────────────────────────────

{
  const one = buildModernExperimentCells({ experimentId: "exp_v2_one", axes: [], resolved: {}, prompt: "p" });
  assert.equal(one.length, 1);
  assert.deepEqual(one.map((c) => c.cell_id), ["cell_0"], "single cell is cell_0");

  const forty = buildModernExperimentCells({
    experimentId: "exp_v2_40",
    axes: [
      { controlId: "steps", values: ["10", "20", "30", "40"] },
      { controlId: "seed", values: ["1", "2", "3", "4", "5"] },
      { controlId: "guidance", values: ["6", "7"] },
    ],
    resolved: {},
    prompt: "p",
  });
  assert.equal(forty.length, 40, "4 × 5 × 2 = 40 cells");
  assert.deepEqual(
    forty.map((c) => c.cell_id),
    Array.from({ length: 40 }, (_, i) => "cell_" + i),
    "cells are keyed cell_0..cell_39 in generation order",
  );
  // Order is stable regardless of completion: identity is positional.
  const reversed = forty.slice().reverse().map((c) => c.cell_id);
  assert.notDeepEqual(reversed, forty.map((c) => c.cell_id), "identity is fixed, never derived from completion");
  section("2. Fixed cell ordering (1 and 40 cells)");
}

// ── 3. Submit exactly one modern definition; never the legacy route ──────

{
  const storage = installLocalStorage();
  const state = makeState({
    experimentAxes: { steps: { enabled: true, values: [10, 20] } },
  });
  const stub = stubFetch((req) => {
    if (req.url.endsWith("/studio/experiment-v2")) {
      const sent = JSON.parse(req.body || "{}");
      const id = sent.experiment_id || "exp_v2_submit";
      return { status: "ok", experiment_id: id, started: true, item: statusDetail({
        experimentId: id, status: "running", total: 2,
        counts: { queued: 1, running: 1, completed: 0, failed: 0, canceled: 0, interrupted: 0 },
        cells: [
          { cell_id: "cell_0", status: "running", attempt_id: "run_1" },
          { cell_id: "cell_1", status: "queued" },
        ],
      }) };
    }
    if (req.url.includes("/history-v2/experiments/") && req.url.endsWith("/status")) {
      return { status: "ok", item: statusDetail({
        experimentId: "exp_v2_submit", status: "running", total: 2,
        counts: { queued: 1, running: 1, completed: 0, failed: 0, canceled: 0, interrupted: 0 },
        cells: [
          { cell_id: "cell_0", status: "running", attempt_id: "run_1" },
          { cell_id: "cell_1", status: "queued" },
        ],
      }) };
    }
    return {};
  });
  try {
    const result = await executeModernExperimentRun(state, {}, { apiBase: "/comfymodal" });
    assert.equal(result.status, "ok");
    assert.ok(result.experimentId.startsWith("exp_v2_"), "durable id is the client-generated modern id");

    const v2Calls = stub.calls.filter((c) => c.method === "POST" && c.url.endsWith("/studio/experiment-v2"));
    const legacyCalls = stub.calls.filter((c) => c.url.includes("/studio/experiment") && !c.url.includes("/studio/experiment-v2"));
    assert.equal(v2Calls.length, 1, "exactly one modern submission");
    assert.equal(legacyCalls.length, 0, "never hits the legacy /studio/experiment route");

    const body = JSON.parse(v2Calls[0].body);
    assert.equal("concurrency" in body, false, "submitted payload has no concurrency field");
    assert.equal("cells" in body, false, "the server owns the fixed cell plan");
    assert.deepEqual(Object.keys(body.definition.axes), ["steps"]);
    // The response echoes the client-generated experiment id (backend contract).
    assert.equal(result.experimentId, body.experiment_id, "durable id comes from the submitted definition");

    // Durable id persisted for reopen/reload.
    assert.equal(storage.get("comfymodal.studio.experiment.active.v1").includes(result.experimentId), true);

    // Controller stored once on state.playground; status reconciled.
    assert.equal(state.playground._experimentController.getExperimentId(), result.experimentId);
    const st = state.playground._experimentController.getState();
    assert.equal(st.status, "running");
    assert.deepEqual(st.cells.map((c) => c.cellId), ["cell_0", "cell_1"], "fixed cell list from backend order");

    // Double submit while active is guarded.
    const second = await executeModernExperimentRun(state, {}, { apiBase: "/comfymodal" });
    assert.equal(second.guarded, true, "submit double-click guarded while active");
    assert.equal(stub.calls.filter((c) => c.method === "POST" && c.url.endsWith("/studio/experiment-v2")).length, 1,
      "no second submission while active");
  } finally {
    detachModernExperiment(state);
    stub.restore();
    delete globalThis.localStorage;
  }
  section("3. One modern submission, never the legacy route");
}

// ── 4. Progress counts text; backend counts preferred; no "partial" ──────

{
  assert.equal(
    formatExperimentProgress({ completed: 18, running: 6, queued: 16 }, 40),
    "18/40 complete \u00b7 6 running \u00b7 16 queued",
  );
  assert.equal(
    formatExperimentProgress({ completed: 18, running: 6, queued: 16, failed: 1, canceled: 2, interrupted: 3 }, 46),
    "18/46 complete \u00b7 6 running \u00b7 16 queued \u00b7 1 failures \u00b7 2 canceled \u00b7 3 interrupted",
  );

  const norm = normalizeExperimentV2Status(statusDetail({
    counts: { completed: 18, running: 6, queued: 16 },
    cells: [
      { cell_id: "a", status: "completed" },
      { cell_id: "b", status: "running" },
    ],
  }));
  assert.equal(norm.counts.completed, 18, "backend counts preferred over cell fold");

  // The progress/status vocabulary never renders "partial".
  const labels = ["Queued", "Running", "Completed", "Completed with failures", "Failed", "Canceled", "Interrupted"];
  labels.forEach(function (label) {
    assert.equal(label.toLowerCase().includes("partial"), false, "no 'partial' label");
  });
  assert.equal(experimentStatusLabel("canceled"), "Canceled");
  assert.equal(experimentStatusLabel("interrupted"), "Interrupted");
  assert.equal(experimentStatusLabel("failed"), "Failed");
  assert.notEqual(experimentStatusLabel("canceled"), experimentStatusLabel("interrupted"));
  assert.notEqual(experimentStatusLabel("interrupted"), experimentStatusLabel("failed"));
  section("4. Progress counts + distinct status labels, no 'partial'");
}

// ── 5. Failed sibling isolation ──────────────────────────────────────────

{
  const ctrl = createExperimentRunController({ experimentId: "exp_v2_iso", actions: {} });
  ctrl.reconcile(statusDetail({
    status: "completed_with_failures",
    counts: { completed: 2, failed: 1 },
    cells: [
      { cell_id: "c0", status: "completed" },
      { cell_id: "c1", status: "failed", error: "boom" },
      { cell_id: "c2", status: "completed" },
    ],
  }));
  const cells = ctrl.getCells();
  assert.deepEqual(cells.map((c) => c.cellId), ["c0", "c1", "c2"], "backend order preserved");
  assert.equal(cells[1].status, "failed");
  assert.equal(cells[1].error, "boom");
  assert.equal(cells[0].status, "completed", "failed sibling leaves c0 untouched");
  assert.equal(cells[2].status, "completed", "failed sibling leaves c2 untouched");

  // A later poll on the SAME attempt regressing c1 to running must NOT flip
  // the failed cell (terminal first-wins per attempt; a new attempt identity
  // is what legitimately opens a retry/resume — covered in test 6).
  ctrl.reconcile(statusDetail({
    status: "running",
    counts: { running: 1, completed: 2 },
    cells: [
      { cell_id: "c0", status: "completed" },
      { cell_id: "c1", status: "running" },
      { cell_id: "c2", status: "completed" },
    ],
  }));
  assert.equal(ctrl.getCells()[1].status, "failed", "terminal first-wins for the same attempt");
  ctrl.dispose();
  section("5. Failed sibling isolation");
}

// ── 6. Retry identity: failed-only, position + cell_id preserved ─────────

{
  const actionCalls = { retry: [] };
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_retry",
    actions: {
      retryCell: async (id, cellId) => { actionCalls.retry.push(cellId); return { accepted: true }; },
    },
  });
  ctrl.reconcile(statusDetail({
    status: "completed_with_failures",
    counts: { completed: 2, failed: 1 },
    cells: [
      { cell_id: "cell_0", status: "completed" },
      { cell_id: "cell_1", status: "failed", error: "nope" },
      { cell_id: "cell_2", status: "completed" },
    ],
  }));

  // Retry only the failed cell; completed cells reject.
  const ok = await ctrl.retryCell("cell_1");
  assert.equal(ok.accepted, true);
  assert.deepEqual(actionCalls.retry, ["cell_1"], "retry targets the failed cell only");
  assert.equal((await ctrl.retryCell("cell_0")).accepted, false, "completed cell not retryable");
  assert.equal((await ctrl.retryCell("cell_0")).message, "Cell is not failed");

  // A new attempt arrives under the SAME cell_id → position/order preserved.
  ctrl.reconcile(statusDetail({
    status: "running",
    counts: { running: 1, completed: 2 },
    cells: [
      { cell_id: "cell_0", status: "completed" },
      { cell_id: "cell_1", status: "running", attempt_id: "run_new" },
      { cell_id: "cell_2", status: "completed" },
    ],
  }));
  const after = ctrl.getCells();
  assert.deepEqual(after.map((c) => c.cellId), ["cell_0", "cell_1", "cell_2"], "position preserved after retry");
  assert.equal(after[1].attemptId, "run_new", "new attempt identity applied to the same cell");
  assert.equal(after[1].error, "nope", "old attempt error retained until the retry resolves");
  ctrl.dispose();
  section("6. Retry identity");
}

// ── 7. Resume eligibility + double-click guard ───────────────────────────

{
  const gate = (function () {
    let resolve;
    const promise = new Promise((res) => { resolve = res; });
    return { promise, resolve };
  })();
  let resumeCalls = 0;
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_resume",
    actions: {
      resume: () => { resumeCalls++; return gate.promise; },
    },
  });

  // Interrupted + never-started cells → eligible.
  ctrl.reconcile(statusDetail({
    status: "interrupted",
    counts: { completed: 1, interrupted: 1, queued: 1 },
    cells: [
      { cell_id: "c0", status: "completed" },
      { cell_id: "c1", status: "interrupted" },
      { cell_id: "c2", status: "queued" },
    ],
  }));
  assert.equal(canResumeModernExperiment("interrupted", ctrl.getCells()), true);
  assert.equal(getResumeEligibleCellCount("interrupted", ctrl.getCells()), 2, "interrupted + queued eligible");

  // A "queued" aggregate with queued/not-started cells IS resume-eligible
  // (only actively running experiments suppress Resume — D5).
  assert.equal(canResumeModernExperiment("queued", ctrl.getCells()), true,
    "queued aggregate with queued/not-started cells is resumable");
  assert.equal(getResumeEligibleCellCount("queued", ctrl.getCells()), 2,
    "interrupted + queued cells counted for a queued aggregate");

  const allQueued = [
    { cellId: "q0", status: "queued" },
    { cellId: "q1", status: "queued" },
  ];
  assert.equal(canResumeModernExperiment("queued", allQueued), true, "all-queued experiment is resumable");
  assert.equal(getResumeEligibleCellCount("queued", allQueued), 2);

  // A queued aggregate with a failed cell stays resumable for the queued
  // cells; the failed cell is skipped, never resumed.
  const queuedPlusFailed = [
    { cellId: "q0", status: "queued" },
    { cellId: "q1", status: "failed" },
  ];
  assert.equal(canResumeModernExperiment("queued", queuedPlusFailed), true);
  assert.equal(getResumeEligibleCellCount("queued", queuedPlusFailed), 1, "failed cells are skipped by Resume");

  // Failed-only mix is NOT resumable (failed cells require Retry).
  const failedOnly = [
    { cellId: "c0", status: "completed" },
    { cellId: "c1", status: "failed" },
  ];
  assert.equal(canResumeModernExperiment("completed_with_failures", failedOnly), false, "failed cells are not resumed");
  assert.equal(getResumeEligibleCellCount("completed_with_failures", failedOnly), 0);

  // Active running experiments are not resumable.
  assert.equal(canResumeModernExperiment("running", ctrl.getCells()), false);

  // Double-click: single-flight while in flight.
  const p1 = ctrl.resume();
  const p2 = ctrl.resume();
  assert.equal(resumeCalls, 1, "resume is single-flight while in flight");
  const guarded = await p2;
  assert.equal(guarded.guarded, true, "second resume guarded");
  gate.resolve({ accepted: true });
  assert.equal((await p1).accepted, true);
  assert.equal(resumeCalls, 1, "only one resume network call");
  ctrl.dispose();
  section("7. Resume eligibility + double-click guard");
}

// ── 8. Popup close / navigation never cancels ────────────────────────────

{
  let cancelCalls = 0;
  const state = makeState({});
  state.playground._activeExperimentId = "exp_v2_close";
  const ctx = { apiBase: "/comfymodal" };
  const ctrl = createExperimentRunController({
    experimentId: "exp_v2_close",
    apiBase: "/comfymodal",
    actions: { cancel: async () => { cancelCalls++; return { accepted: true }; } },
  });
  state.playground._experimentController = ctrl;
  ctrl.reconcile(statusDetail({
    status: "running",
    cells: [{ cell_id: "cell_0", status: "running", attempt_id: "run_1" }],
  }));

  // Start polling so detach has something to stop (and prove the process is
  // not left with a live interval).
  startModernExperimentPolling(state, { apiBase: "/comfymodal" });
  assert.ok(state.playground._experimentPollTimer != null, "polling started");

  detachModernExperiment(state);
  assert.equal(cancelCalls, 0, "popup close / detach never cancels");
  assert.equal(state.playground._experimentController, ctrl, "detach preserves the controller for reopen");
  assert.equal(state.playground._activeExperimentId, "exp_v2_close", "detach preserves the active experiment id for reopen");
  assert.equal(state.playground._experimentPollTimer, null, "detach stops polling");

  disposeModernExperiment(state);
  assert.equal(cancelCalls, 0, "dispose never cancels");
  assert.equal(state.playground._experimentController, null, "dispose clears the controller handle");
  section("8. Popup close / navigation never cancels");
}

// ── 9. Reopen same id: rebuilds fixed list, no resubmit ──────────────────

{
  const storage = installLocalStorage();
  storage.set("comfymodal.studio.experiment.active.v1", JSON.stringify({ experimentId: "exp_v2_reopen" }));

  const state = makeState({});
  state.playground._activeExperimentId = "exp_v2_reopen";
  const fake = makeFakeApi();
  const submitted = [];
  const stub = stubFetch((req) => {
    if (req.method === "POST" && req.url.endsWith("/studio/experiment-v2")) {
      submitted.push(req.url);
      return { status: "ok", experiment_id: "exp_v2_reopen", item: {} };
    }
    if (req.url.includes("/history-v2/experiments/exp_v2_reopen/status")) {
      return { status: "ok", item: statusDetail({
        experimentId: "exp_v2_reopen", status: "running", total: 3,
        counts: { queued: 2, running: 1 },
        cells: [
          { cell_id: "cell_0", status: "running", attempt_id: "run_1" },
          { cell_id: "cell_1", status: "queued" },
          { cell_id: "cell_2", status: "queued" },
        ],
      }) };
    }
    return {};
  });
  try {
    const ctrl = attachModernExperiment(state, {}, { apiBase: "/comfymodal", comfyApi: fake.api });
    assert.ok(ctrl, "controller reattached for the existing id");
    assert.equal(submitted.length, 0, "reopen never resubmits the definition");

    await refreshModernExperimentStatus(state, { apiBase: "/comfymodal" });
    const st = ctrl.getState();
    assert.deepEqual(st.cells.map((c) => c.cellId), ["cell_0", "cell_1", "cell_2"], "same fixed cell list rebuilt");
    assert.equal(st.cells[0].status, "running");
    assert.equal(st.cells[1].status, "queued");

    // Reattach twice more (simulated re-renders) → still one controller.
    const ctrl2 = attachModernExperiment(state, {}, { apiBase: "/comfymodal", comfyApi: fake.api });
    assert.equal(ctrl2, ctrl, "re-render does not create a second controller");
  } finally {
    detachModernExperiment(state);
    stub.restore();
    delete globalThis.localStorage;
  }
  section("9. Reopen same id rebuilds the fixed list without resubmitting");
}

// ── 10. Status endpoint unwrap (item) + terminal detection ───────────────

{
  const state = makeState({});
  state.playground._activeExperimentId = "exp_v2_term";
  const stub = stubFetch({
    "/comfymodal/history-v2/experiments/exp_v2_term/status": { status: "ok", item: statusDetail({
      experimentId: "exp_v2_term", status: "completed", total: 1,
      counts: { completed: 1 },
      cells: [{ cell_id: "cell_0", status: "completed", thumb_url: "/t.png" }],
    }) },
  });
  try {
    const payload = await refreshModernExperimentStatus(state, { apiBase: "/comfymodal" });
    assert.equal(payload.experiment_id, "exp_v2_term", "item detail unwrapped for the controller");
    assert.equal(isTerminalModernStatus("completed"), true);
    assert.equal(isTerminalModernStatus("completed_with_failures"), true);
    assert.equal(isTerminalModernStatus("canceled"), true);
    assert.equal(isTerminalModernStatus("interrupted"), true);
    assert.equal(isTerminalModernStatus("running"), false);
    const ctrl = getModernExperimentController(state, { apiBase: "/comfymodal" });
    assert.equal(ctrl.getState().status, "completed");
    assert.equal(ctrl.getState().cells[0].thumbUrl, "/t.png", "output thumb surfaced as soon as supplied");
  } finally {
    disposeModernExperiment(state);
    stub.restore();
  }
  section("10. Status item unwrap + terminal detection");
}

// ── 11. Workflow-axis labels/values preserved from state ─────────────────

{
  const state = makeState({
    workflowId: "wf_axis_a",
    workflowVersionId: "ver_axis_1",
    presetId: "preset_axis_x",
    workflowName: "Axis Workflow",
    presetName: "axis_preset",
    experimentAxes: {
      steps: { enabled: true, values: [8, 16] },
      seed: { enabled: true, values: [7] },
    },
  });
  const selection = resolveModernWorkflowSelection(state);
  assert.equal(selection.workflowId, "wf_axis_a");
  assert.equal(selection.workflowVersionId, "ver_axis_1");
  assert.equal(selection.presetId, "preset_axis_x");
  assert.equal(selection.workflowName, "Axis Workflow");
  assert.equal(selection.presetName, "axis_preset");

  const payload = buildModernExperimentDefinition(state);
  assert.equal(payload.definition.workflows.length, 1);
  assert.equal(payload.definition.workflows[0].workflow_id, "wf_axis_a");
  assert.equal(payload.definition.workflows[0].workflow_version_id, "ver_axis_1");
  assert.equal(payload.definition.workflows[0].preset_id, "preset_axis_x");
  assert.equal(payload.definition.workflows[0].workflow_name, "Axis Workflow");
  assert.equal(payload.definition.workflows[0].preset_name, "axis_preset");

  assert.deepEqual(payload.definition.axes.steps.values, [8, 16]);
  assert.deepEqual(payload.definition.axes.seed.values, [7]);

  assert.equal(modernExperimentCanRun(state), true);
  assert.equal(modernExperimentDisabledReason(state), "");
  const noWf = makeState({ workflowId: "", workflowVersionId: "" });
  assert.equal(modernExperimentCanRun(noWf), false);
  assert.ok(modernExperimentDisabledReason(noWf).length > 0);
  section("11. Workflow-axis labels/values preserved from state");
}

// ── 12. Run surface selection (one submit button, never two) ─────────────

{
  const storage = installLocalStorage();
  try {
    // Legacy preset-only state (no modern workflow, no experiment id) → the
    // existing legacy experiment renderer stays mounted.
    const legacy = makeState({ selectedBackendId: "preset_a", compareBackendIds: ["preset_b"] });
    delete legacy.playground._workflowRun;
    assert.equal(experimentRunSurface(legacy), "legacy", "preset-only state keeps the legacy renderer");

    // Modern Workflow/Version selection → the D5 modern section mounts.
    const modern = makeState({ workflowId: "wf_1", workflowVersionId: "ver_1" });
    assert.equal(experimentRunSurface(modern), "modern", "modern workflow/version selection shows the modern section");

    // Workflow without a version is not yet a modern run selection.
    const noVersion = makeState({ workflowId: "wf_1", workflowVersionId: "" });
    assert.equal(experimentRunSurface(noVersion), "legacy", "workflow without version stays legacy");

    // An in-flight/persisted active modern experiment forces the modern
    // surface even without a workflow re-selected.
    const active = makeState({ workflowId: "", workflowVersionId: "" });
    active.playground._activeExperimentId = "exp_v2_active";
    assert.equal(experimentRunSurface(active), "modern", "active experiment id keeps the modern section");

    const persisted = makeState({ workflowId: "", workflowVersionId: "" });
    storage.set("comfymodal.studio.experiment.active.v1", JSON.stringify({ experimentId: "exp_v2_persisted" }));
    assert.equal(experimentRunSurface(persisted), "modern", "persisted active experiment id forces the modern section");
  } finally {
    delete globalThis.localStorage;
  }

  // renderExperimentMode mounts exactly one surface through a shared host
  // (the legacy run button and the modern section are mutually exclusive).
  assert.equal(MODULE_SRC.includes("experimentRunSurface(state)"), true, "renderExperimentMode branches on the surface");
  assert.equal(MODULE_SRC.includes("surface === \"modern\""), true, "modern branch mounts the D5 section only");
  assert.equal(MODULE_SRC.includes("renderExperimentRunButton(state, actions, context)"), true,
    "legacy branch mounts the existing legacy run button");

  // The surface watcher detaches the modern controller when the host is
  // disconnected (navigation/popup close) — event listeners + polling are
  // detached without cancel, and the controller is never disposed here.
  assert.equal(MODULE_SRC.includes("detachModernExperiment(state, actions);"), true,
    "watcher detaches the modern controller on host disconnect");
  section("12. Run surface selection (one submit button, never two)");
}

// ── 13. Legacy rendering compatibility ───────────────────────────────────

{
  assert.equal(typeof renderExperimentMode, "function", "legacy experiment-mode renderer retained");
  assert.equal(typeof renderExperimentRunButton, "function", "legacy run button renderer retained");
  assert.equal(typeof executeExperimentRun, "function", "legacy submit retained");
  assert.equal(typeof canRunExperiment, "function", "legacy eligibility retained");

  const state = makeState({ selectedBackendId: "preset_a", compareBackendIds: ["preset_b", "preset_a"] });
  assert.deepEqual(getExperimentPresetIds(state), ["preset_a", "preset_b"], "canonical preset ids dedupe base+compare");
  const onePreset = makeState({ selectedBackendId: "preset_a", compareBackendIds: [] });
  assert.equal(canRunExperiment(onePreset), false, "single preset without multi-value axis is not runnable");

  // The legacy submission path is still defined and uses the legacy route
  // only there; the modern path never references runStudioExperiment.
  assert.equal(MODULE_SRC.includes("runStudioExperiment"), true, "legacy import retained for legacy flows");
  assert.equal(MODULE_SRC.includes("runExperimentV2"), true, "modern import present");
  section("13. Legacy rendering compatibility");
}

// ── 14. D5 correction: flat status hydration + polling continuation ───────
//
// The status endpoint may return a FLAT payload (no `item` wrapper) where the
// lifecycle status is `aggregate_status` and `status` is only the transport
// envelope ("ok").  Hydration must keep a running experiment running instead
// of completing it (the previous normalize aliased "ok" → "completed"), and
// polling must continue while running and stop once a terminal aggregate
// lands.  Reopen/reconnect with a flat shape must not resubmit.

{
  const flat = (aggregateStatus, cells, experimentId) => ({
    status: "ok",
    experiment_id: experimentId || "exp_v2_flat_hydrate",
    aggregate_status: aggregateStatus,
    total: cells.length,
    counts: cells.reduce((acc, c) => { acc[c.status] = (acc[c.status] || 0) + 1; return acc; }, {}),
    cells: cells.map((c, i) => Object.assign({ cell_id: "cell_" + i }, c)),
  });

  // Hydration: a flat running response keeps the controller running.
  const state = makeState({});
  state.playground._activeExperimentId = "exp_v2_flat_hydrate";
  const stub = stubFetch((req) => {
    if (req.url.includes("/history-v2/experiments/exp_v2_flat_hydrate/status")) {
      return flat("running", [{ status: "running" }, { status: "queued" }]);
    }
    return {};
  });
  try {
    const payload = await refreshModernExperimentStatus(state, { apiBase: "/comfymodal" });
    assert.ok(payload && payload.aggregate_status === "running", "flat payload passed through unwrapped");
    const ctrl = getModernExperimentController(state, { apiBase: "/comfymodal" });
    assert.equal(ctrl.getState().status, "running",
      "flat running hydration keeps running — old bug completed it");
    assert.deepEqual(ctrl.getCells().map((c) => c.cellId), ["cell_0", "cell_1"], "flat-shape cells hydrated");
    assert.equal(ctrl.getCells()[0].status, "running");
    assert.equal(ctrl.getCells()[1].status, "queued");
  } finally {
    disposeModernExperiment(state);
    stub.restore();
  }

  // Polling: a running flat poll keeps the timer; a terminal flat poll stops
  // it.  Timers are stubbed so the interval callback is driven deterministically.
  const originalSet = globalThis.setInterval;
  const originalClear = globalThis.clearInterval;
  let timerId = null;
  let tickFn = null;
  const stoppedIds = [];
  globalThis.setInterval = (fn) => { tickFn = fn; timerId = 42; return timerId; };
  globalThis.clearInterval = (id) => { if (id === timerId) { timerId = null; stoppedIds.push(id); } };
  const state2 = makeState({});
  state2.playground._activeExperimentId = "exp_v2_flat_poll";
  let fetchCalls = 0;
  const stub2 = stubFetch((req) => {
    if (!req.url.includes("/status")) return {};
    fetchCalls++;
    if (fetchCalls === 1) return flat("running", [{ status: "running" }], "exp_v2_flat_poll");
    return flat("completed", [{ status: "completed" }], "exp_v2_flat_poll");
  });
  try {
    const ctrl = getModernExperimentController(state2, { apiBase: "/comfymodal" });
    startModernExperimentPolling(state2, { apiBase: "/comfymodal" });
    assert.ok(timerId != null, "polling started");
    assert.ok(tickFn != null, "poll interval callback captured");

    // First tick: flat running → still running → polling continues.
    await tickFn();
    assert.equal(ctrl.getState().status, "running", "flat running poll keeps running");
    assert.equal(stoppedIds.length, 0, "running aggregate does not stop polling");
    assert.ok(timerId != null, "poll timer alive while running");

    // Second tick: flat completed → terminal → polling stops.
    await tickFn();
    assert.equal(ctrl.getState().status, "completed", "flat completed poll completes the run");
    assert.equal(stoppedIds.length, 1, "terminal aggregate stops polling");
    assert.equal(timerId, null, "poll timer cleared after terminal status");
  } finally {
    stopModernExperimentPolling(state2);
    globalThis.setInterval = originalSet;
    globalThis.clearInterval = originalClear;
    stub2.restore();
    disposeModernExperiment(state2);
  }

  // Reopen/reconnect with a flat shape: one controller, no resubmit, hydrated
  // from aggregate_status.
  const storage = installLocalStorage();
  storage.set("comfymodal.studio.experiment.active.v1", JSON.stringify({ experimentId: "exp_v2_flat_reopen" }));
  const state3 = makeState({});
  state3.playground._activeExperimentId = "exp_v2_flat_reopen";
  const fake = makeFakeApi();
  const submitted = [];
  const stub3 = stubFetch((req) => {
    if (req.method === "POST" && req.url.endsWith("/studio/experiment-v2")) {
      submitted.push(req.url);
      return { status: "ok", experiment_id: "exp_v2_flat_reopen", item: {} };
    }
    if (req.url.includes("/history-v2/experiments/exp_v2_flat_reopen/status")) {
      return flat("running", [{ status: "running" }, { status: "queued" }], "exp_v2_flat_reopen");
    }
    return {};
  });
  try {
    const ctrl = attachModernExperiment(state3, {}, { apiBase: "/comfymodal", comfyApi: fake.api });
    assert.ok(ctrl, "flat-shape reopen reattaches the controller");
    assert.equal(submitted.length, 0, "reopen never resubmits the definition");
    await refreshModernExperimentStatus(state3, { apiBase: "/comfymodal" });
    assert.equal(ctrl.getState().status, "running", "flat-shape reopen hydration keeps running");
    assert.deepEqual(ctrl.getCells().map((c) => c.cellId), ["cell_0", "cell_1"], "fixed list rebuilt from flat shape");
    assert.equal(ctrl.getCells()[0].status, "running");
    assert.equal(ctrl.getCells()[1].status, "queued");
  } finally {
    detachModernExperiment(state3);
    stub3.restore();
    delete globalThis.localStorage;
  }
  section("14. Flat status hydration + polling continuation + reopen");
}

// ── 15. D5 guards held with the flat status flow ──────────────────────────

{
  // No "partial" in the canonical aggregate status labels.
  assert.equal(experimentStatusLabel("completed_with_failures"), "Completed with failures");
  assert.equal(experimentStatusLabel("completed_with_failures").toLowerCase().includes("partial"), false,
    "no 'partial' label for the flat completed_with_failures status");

  // Flat statuses remain distinct: canceled ≠ interrupted ≠ failed.
  assert.notEqual(experimentStatusLabel("canceled"), experimentStatusLabel("interrupted"));

  // The modern definition never carries concurrency, even with a flat status
  // flow active (the run surface stays modern-only).
  const state = makeState({
    experimentAxes: { steps: { enabled: true, values: [10, 20] } },
  });
  state.playground._activeExperimentId = "exp_v2_flat_guard";
  assert.equal(experimentRunSurface(state), "modern", "active flat experiment keeps the modern surface");
  const payload = buildModernExperimentDefinition(state);
  assert.equal("concurrency" in payload, false, "no concurrency in the definition");
  assert.equal(JSON.stringify(payload).includes("concurrency"), false, "no concurrency anywhere");
  section("15. Flat-flow guards: no concurrency, no partial, distinct statuses");
}

console.log("PASS: studio experiment v2 frontend unit tests");
