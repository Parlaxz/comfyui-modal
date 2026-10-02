// Modal Studio — Run / Event / State Model Unit Tests
//
// Executable behavioral tests that import and run the actual modules
// (web/studio-run-model.js + web/studio-run-adapters.js) with hand-written
// fixtures. No browser, no DOM, plain Node.
//
// Run: node tests/studio_run_model_unit.mjs

import assert from "node:assert/strict";
import {
  createRunEvent,
  createRunStore,
  getStageSpan,
  getSamplerProgress,
  getWorkflowProgress,
} from "../web/studio-run-model.js";
import {
  adaptLegacyStatus,
  adaptCellLegacyStatus,
  adaptComfyUIWsEvents,
  adaptExperimentWorkerProgress,
  adaptExperimentEvent,
  adaptSnapshot,
  adaptDirectResult,
} from "../web/studio-run-adapters.js";

// ── Helpers ──────────────────────────────────────────────────────────────

let _ts = 0;

/**
 * Build a canonical event with runId defaulting to "run-a" and timestamp
 * defaulting to a counter that advances by 10 per call.
 */
function ev(overrides = {}) {
  const merged = { runId: "run-a", timestamp: _ts, ...overrides };
  if (overrides.timestamp === undefined) _ts += 10;
  return createRunEvent(merged);
}

/** Report a section as passing. */
function section(name) {
  console.log("PASS: " + name);
}

// ── 1. Normal ordered lifecycle ──────────────────────────────────────────

{
  const store = createRunStore();
  const stages = ["created", "submitting", "queued", "starting", "executing", "sampling", "completed"];
  let ts = 0;
  for (const stage of stages) {
    const extra = {};
    if (stage === "executing") extra.progress = { completedNodes: 2, totalNodes: 5 };
    if (stage === "sampling") extra.sampler = { step: 5, max: 10 };
    store.applyEvent(ev({ stage, status: stage, timestamp: ts, ...extra }));
    ts += 10;
    assert.equal(store.getRun("run-a").status, stage, `status should advance to ${stage}`);
  }

  const run = store.getRun("run-a");
  assert.equal(run.status, "completed");
  assert.equal(run.isTerminal, true);
  assert.equal(run.endTs, 60, "endTs should equal terminal timestamp");
  assert.equal(run.created, 0, "created should be earliest created timestamp");
  assert.equal(run.startTs, 0, "startTs should be earliest event timestamp");
  assert.equal(run.stage, "sampling", "stage should stay at highest entered non-terminal stage");

  // stageSpans contains ONLY the stages that were emitted (no completed span).
  assert.deepEqual(
    Object.keys(run.stageSpans).sort(),
    ["created", "executing", "queued", "sampling", "starting", "submitting"],
  );
  const execSpan = run.stageSpans["executing"];
  assert.equal(execSpan.start, 40);
  assert.equal(execSpan.end, 40);
  assert.equal(execSpan.durationMs, 0, "single-emission span duration is 0");

  // Sampler and workflow progress are both retained independently.
  assert.equal(run.sampler.step, 5);
  assert.equal(run.sampler.max, 10);
  assert.equal(run.sampler.percent, 50);
  assert.equal(run.progress.completedNodes, 2);
  assert.equal(run.progress.totalNodes, 5);
  section("1. Normal ordered lifecycle");
}

// ── 2. Duplicate events ──────────────────────────────────────────────────

{
  const store = createRunStore();
  const e1 = ev({ id: "evt-1", stage: "created", status: "created" });
  store.applyEvent(e1);
  store.applyEvent(e1); // the same object twice is a no-op
  assert.equal(store.getRun("run-a").eventCount, 1);
  assert.equal(store.getRun("run-a").status, "created");

  store.applyEvent(ev({ id: "evt-1", stage: "submitting", status: "submitting" }));
  assert.equal(store.getRun("run-a").eventCount, 1, "duplicate id must be dropped");
  assert.equal(store.getRun("run-a").status, "created", "duplicate must not change status");
  section("2. Duplicate event dedupe");
}

// ── 3. Out-of-order arrival ──────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "completed", status: "completed", timestamp: 100 }),
    ev({ stage: "created", status: "created", timestamp: 10 }),
    ev({ stage: "executing", status: "executing", timestamp: 50 }),
    ev({ stage: "sampling", status: "sampling", timestamp: 70 }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.status, "completed", "terminal survives out-of-order arrival");
  assert.equal(run.isTerminal, true);
  assert.equal(run.startTs, 10);
  assert.equal(run.endTs, 100);
  assert.equal(run.stageSpans["created"].start, 10);
  assert.equal(run.stageSpans["executing"].end, 50);
  assert.equal(run.stageSpans["sampling"].end, 70);

  // Same batch, two arrival orders, identical timestamps → identical
  // derived status and stageSpans.
  const batchA = [
    ev({ runId: "det-a", stage: "created", status: "created", timestamp: 10 }),
    ev({ runId: "det-a", stage: "executing", status: "executing", timestamp: 50 }),
    ev({ runId: "det-a", stage: "sampling", status: "sampling", timestamp: 70 }),
    ev({ runId: "det-a", stage: "completed", status: "completed", timestamp: 100 }),
  ];
  const batchB = [
    ev({ runId: "det-b", stage: "completed", status: "completed", timestamp: 100 }),
    ev({ runId: "det-b", stage: "sampling", status: "sampling", timestamp: 70 }),
    ev({ runId: "det-b", stage: "executing", status: "executing", timestamp: 50 }),
    ev({ runId: "det-b", stage: "created", status: "created", timestamp: 10 }),
  ];
  const storeA = createRunStore().applyEvents(batchA);
  const storeB = createRunStore().applyEvents(batchB);
  const runA = storeA.getRun("det-a");
  const runB = storeB.getRun("det-b");
  assert.equal(runA.status, runB.status);
  assert.deepEqual(runA.stageSpans, runB.stageSpans);
  section("3. Out-of-order arrival");
}

// ── 4. Failure ───────────────────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "created", status: "created" }),
    ev({ stage: "submitting", status: "submitting" }),
    ev({ stage: "executing", status: "executing" }),
    ev({ stage: "failed", status: "failed", error: { message: "sampler exploded", type: "execution_error" } }),
  ]);
  let run = store.getRun("run-a");
  assert.equal(run.status, "failed");
  assert.equal(run.isTerminal, true);
  assert.equal(run.error.message, "sampler exploded");
  assert.equal(run.error.type, "execution_error");
  assert.notEqual(run.status, "completed", "failure never implies completion");

  // Terminal is locked: a later executing event does not change status.
  store.applyEvent(ev({ stage: "executing", status: "executing" }));
  run = store.getRun("run-a");
  assert.equal(run.status, "failed");
  assert.equal(run.isTerminal, true);
  section("4. Failure and terminal lock");
}

// ── 5. Cancellation ──────────────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "created", status: "created" }),
    ev({ stage: "executing", status: "executing" }),
    ev({ status: "canceled" }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.status, "canceled");
  assert.equal(run.isTerminal, true);
  section("5. Cancellation");
}

// ── 6. Interruption ──────────────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "created", status: "created" }),
    ev({ stage: "executing", status: "executing" }),
    ev({ status: "interrupted" }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.status, "interrupted");
  assert.equal(run.isTerminal, true);
  section("6. Interruption");
}

// ── 7. Retry as separate attempt ─────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ runId: "run-1", stage: "created", status: "created", timestamp: 0 }),
    ev({ runId: "run-2", stage: "created", status: "created", timestamp: 5 }),
    ev({ runId: "run-1", stage: "executing", status: "executing", timestamp: 10 }),
    ev({ runId: "run-2", stage: "executing", status: "executing", timestamp: 15 }),
    ev({ runId: "run-1", status: "failed", error: { message: "boom", type: "test" }, timestamp: 20 }),
    ev({ runId: "run-2", status: "completed", timestamp: 25 }),
  ]);
  const r1 = store.getRun("run-1");
  const r2 = store.getRun("run-2");
  assert.equal(r1.status, "failed");
  assert.equal(r1.isTerminal, true);
  assert.equal(r2.status, "completed");
  assert.equal(r2.isTerminal, true);
  assert.equal(r1.eventCount, 3, "run-1 unaffected by run-2 events");
  assert.equal(r2.eventCount, 3);
  section("7. Retry as separate attempt");
}

// ── 8. Two simultaneous runs ─────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ runId: "run-A", stage: "created", status: "created", timestamp: 0 }),
    ev({ runId: "run-B", stage: "created", status: "created", timestamp: 1 }),
    ev({ runId: "run-A", stage: "executing", status: "executing", timestamp: 2 }),
    ev({ runId: "run-B", stage: "submitting", status: "submitting", timestamp: 3 }),
    ev({ runId: "run-A", stage: "sampling", status: "sampling", timestamp: 4 }),
    ev({ runId: "run-B", stage: "executing", status: "executing", timestamp: 5 }),
  ]);
  const a = store.getRun("run-A");
  const b = store.getRun("run-B");
  assert.equal(a.status, "sampling");
  assert.equal(b.status, "executing");
  assert.equal(a.stageSpans["sampling"].start, 4);
  assert.equal(b.stageSpans["submitting"].start, 3);
  assert.equal(a.stageSpans["submitting"], undefined, "run-A must not see run-B stages");
  assert.equal(b.stageSpans["sampling"], undefined, "run-B must not see run-A stages");
  assert.equal(a.eventCount, 3);
  assert.equal(b.eventCount, 3);
  section("8. Two simultaneous runs");
}

// ── 9. Two experiment cells ──────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ cellId: "cell-x", stage: "executing", sampler: { step: 1, max: 10 } }),
    ev({ cellId: "cell-y", stage: "executing", sampler: { step: 2, max: 10 } }),
    ev({ cellId: "cell-y", status: "failed", error: { message: "cell boom", type: "cell.failed" } }),
    ev({ cellId: "cell-x", stage: "sampling", sampler: { step: 9, max: 10 } }),
  ]);
  let run = store.getRun("run-a");
  assert.equal(run.cells["cell-y"].status, "failed");
  assert.equal(run.cells["cell-x"].status, null, "cell-x status unchanged (never set)");
  assert.equal(run.cells["cell-x"].sampler.step, 9);
  assert.equal(run.isTerminal, false, "cell failure must not terminate the run");
  assert.ok(
    ["executing", "sampling"].includes(run.status),
    `run.status should stay a running-phase status, got ${run.status}`,
  );

  store.applyEvent(ev({ stage: "completed", status: "completed" }));
  run = store.getRun("run-a");
  assert.equal(run.status, "completed");
  assert.equal(run.isTerminal, true);
  assert.equal(run.cells["cell-y"].status, "failed", "cell state survives run completion");
  section("9. Two experiment cells");
}

// ── 10. Sampler vs workflow progress independence ────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "executing", status: "executing", progress: { value: 2, max: 10, completedNodes: 1, totalNodes: 5 } }),
    ev({ stage: "sampling", status: "sampling", sampler: { step: 3, max: 10 } }),
    ev({ stage: "executing", status: "executing", progress: { value: 5, max: 10, completedNodes: 3, totalNodes: 5 } }),
    ev({ stage: "sampling", status: "sampling", sampler: { step: 7, max: 10 } }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.sampler.step, 7, "sampler comes from sampler events only");
  assert.equal(run.sampler.max, 10);
  assert.equal(run.sampler.percent, 70);
  assert.equal(run.progress.value, 5, "workflow progress comes from progress events only");
  assert.equal(run.progress.completedNodes, 3);
  assert.equal(run.progress.percent, 50);
  assert.equal(run.sampler.value, undefined, "sampler never absorbs progress fields");
  assert.equal(run.progress.step, undefined, "progress never absorbs sampler fields");
  assert.equal(getSamplerProgress(run), run.sampler);
  assert.equal(getWorkflowProgress(run), run.progress);
  section("10. Sampler vs workflow progress independence");
}

// ── 11. Missing stages and absent spans ──────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ stage: "created", status: "created", timestamp: 10 }),
    ev({ stage: "completed", status: "completed", timestamp: 100 }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.status, "completed");
  assert.equal(Object.prototype.hasOwnProperty.call(run.stageSpans, "executing"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(run.stageSpans, "sampling"), false);
  assert.deepEqual(getStageSpan(run, "executing"), { start: null, end: null, durationMs: null });
  assert.deepEqual(run.stageSpans["created"], { start: 10, end: 10, durationMs: 0 });

  // A stage entered at ts=50 and explicitly ended at ts=100 gets a real span.
  const store2 = createRunStore();
  store2.applyEvents([
    ev({ stage: "executing", status: "executing", timestamp: 50 }),
    ev({ stage: "completed", status: "completed", stageEnd: "executing", timestamp: 100 }),
  ]);
  const run2 = store2.getRun("run-a");
  assert.deepEqual(run2.stageSpans["executing"], { start: 50, end: 100, durationMs: 50 });

  // A run with NO events is absent entirely.
  const empty = createRunStore();
  assert.equal(empty.getRun("run-none"), undefined);
  assert.deepEqual(empty.getRuns(), []);
  section("11. Missing stages and absent spans");
}

// ── 12. No completion from stream close ──────────────────────────────────

{
  const raw = [
    { type: "execution_start", prompt_id: "p1", total_nodes: 10 },
    { type: "executing", node: "3", display_node: "KSampler" },
    { type: "progress", step: 5, max: 10, value: 5 },
    { type: "modal_status", prompt_id: "p1", phase: "done", message: "all done" },
  ];
  const events = adaptComfyUIWsEvents(raw, { runId: "run-a" });
  assert.equal(events.length, 4, "all four ws messages adapt to events");
  assert.equal(
    events.some((e) => e.status === "completed" || e.stage === "completed"),
    false,
    "modal_status 'done' must never map to completed",
  );

  const store = createRunStore();
  store.applyEvents(events);
  const run = store.getRun("run-a");
  assert.equal(run.isTerminal, false, "stream close without execution_success is not terminal");
  assert.ok(["executing", "sampling"].includes(run.status), `status should stay running-phase, got ${run.status}`);
  assert.equal(run.sampler.step, 5, "sampler diagnostics still recorded");
  section("12. No completion from stream close");
}

// ── 13. Adapter mapping checks ───────────────────────────────────────────

{
  // Legacy status mapping table.
  assert.equal(adaptLegacyStatus("completed_with_failures"), "failed");
  assert.equal(adaptLegacyStatus("paused"), null);
  assert.equal(adaptLegacyStatus("idle"), null);
  assert.equal(adaptLegacyStatus("unknown"), null);
  assert.equal(adaptLegacyStatus("draft"), "created");
  assert.equal(adaptLegacyStatus("stopped"), "canceled");
  assert.equal(adaptLegacyStatus("done"), "completed");
  assert.equal(adaptLegacyStatus("nonsense"), null);

  // Cell legacy status mapping table (spot checks).
  assert.equal(adaptCellLegacyStatus("pending"), "created");
  assert.equal(adaptCellLegacyStatus("running"), "executing");
  assert.equal(adaptCellLegacyStatus("skipped"), "skipped");
  assert.equal(adaptCellLegacyStatus("cancelled"), "canceled");
  assert.equal(adaptCellLegacyStatus("nonsense"), null);

  // ComfyUI ws adapters.
  const errEvents = adaptComfyUIWsEvents(
    { type: "execution_error", prompt_id: "p", message: "boom" },
    { runId: "run-a" },
  );
  assert.equal(errEvents.length, 1);
  assert.equal(errEvents[0].status, "failed");
  assert.equal(errEvents[0].error.message, "boom");
  assert.equal(errEvents[0].metadata.raw.type, "execution_error", "metadata.raw must carry the payload");

  const okEvents = adaptComfyUIWsEvents({ type: "execution_success", prompt_id: "p" }, { runId: "run-a" });
  assert.equal(okEvents.length, 1);
  assert.equal(okEvents[0].status, "completed");

  // Experiment lifecycle events.
  const stopped = adaptExperimentEvent(
    { experiment_id: "e1", type: "experiment.stopped", payload: {} },
    { runId: "run-a" },
  );
  assert.equal(stopped[0].status, "canceled");

  const fatal = adaptExperimentEvent(
    { experiment_id: "e1", type: "experiment.failed_fatal", payload: { message: "kaboom" } },
    { runId: "run-a" },
  );
  assert.equal(fatal[0].status, "failed");
  assert.equal(fatal[0].error.message, "kaboom");
  assert.equal(fatal[0].error.type, "experiment.failed_fatal");

  // Worker cell.failed is cell-level and never terminates the run.
  const wf = adaptExperimentWorkerProgress(
    { experiment_id: "e1", cell_key: "c1", type: "cell.failed", message: "cell down" },
    { runId: "run-a" },
  );
  assert.equal(wf[0].cellId, "c1");
  assert.equal(wf[0].status, "failed");
  const wstore = createRunStore();
  wstore.applyEvents(wf);
  const wrun = wstore.getRun("run-a");
  assert.equal(wrun.isTerminal, false, "cell.failed must not terminate the run");
  assert.equal(wrun.cells["c1"].status, "failed");

  // Snapshot polls.
  const snap = adaptSnapshot({ status: "completed", counters: { completed: 3, total: 5 } }, { runId: "run-a" });
  assert.equal(snap.length, 1);
  assert.equal(snap[0].status, "completed");
  assert.equal(snap[0].progress.value, 3);
  const sstore = createRunStore();
  sstore.applyEvents(snap);
  assert.equal(sstore.getRun("run-a").isTerminal, true, "snapshot completion is explicit terminal evidence");

  const snapPaused = adaptSnapshot({ status: "paused" }, { runId: "run-a" });
  assert.equal(snapPaused.length, 1);
  assert.equal(snapPaused[0].status, null, "paused maps to null (no status change)");
  assert.equal(snapPaused[0].stage, null);

  // Direct results.
  const drOk = adaptDirectResult({ status: "completed", timings: {}, runHistoryId: "h1" }, { runId: "run-a" });
  assert.equal(drOk[0].status, "completed");
  const drErr = adaptDirectResult({ status: "error", error: "boom" }, { runId: "run-a" });
  assert.equal(drErr[0].status, "failed");
  assert.equal(drErr[0].error.message, "boom");

  // Defensive: unknown message types are skipped gracefully.
  assert.deepEqual(adaptComfyUIWsEvents({ type: "totally.unknown" }, { runId: "run-a" }), []);
  assert.deepEqual(adaptComfyUIWsEvents(null, { runId: "run-a" }), []);
  section("13. Adapter mapping checks");
}

// ── 14. Mode passthrough ─────────────────────────────────────────────────

{
  const store = createRunStore();
  store.applyEvents([
    ev({ mode: "preview", stage: "created", status: "created" }),
    ev({ mode: "preview", stage: "executing", status: "executing" }),
    ev({ mode: "preview", stage: "completed", status: "completed" }),
  ]);
  const run = store.getRun("run-a");
  assert.equal(run.mode, "preview", "mode survives through the store");
  assert.equal(run.status, "completed");
  section("14. Mode passthrough");
}

console.log("PASS: studio run model unit tests");
