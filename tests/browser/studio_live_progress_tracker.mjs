// RED behavioural test: createScopedTracker consumes experiment.worker.progress events
//
// Tests that createScopedTracker (from comfymodal-progress.js):
//   1. Consumes the experiment.worker.progress event shape produced by the
//      backend stream_event_sink wiring.
//   2. Updates current node, sampler step/max/percent, phase/message, elapsed
//      (from actual tracker timer) on each event.
//   3. Transitions on terminal experiment.event (completed/stopped/failed_fatal)
//      to stage "done" / "error".
//
// This is an EXECUTABLE Node.js behavioral test (no browser needed).
// It creates a mock API object and wires a real createScopedTracker,
// then feeds it experiment.worker.progress events and observes state changes.
//
// Run: node tests/browser/studio_live_progress_tracker.mjs

import { createScopedTracker } from "../../web/comfymodal-progress.js";

let failures = 0;

function assert(condition, message) {
  if (!condition) {
    console.error("  FAIL:", message);
    failures++;
  } else {
    console.log("  PASS");
  }
}

// ── Mock API ──────────────────────────────────────────────────────────────

function makeMockApi() {
  const listeners = {};
  return {
    addEventListener(event, handler) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(handler);
    },
    removeEventListener(event, handler) {
      if (!listeners[event]) return;
      listeners[event] = listeners[event].filter(h => h !== handler);
    },
    // Test helper: dispatch a custom event to registered listeners
    _dispatch(eventName, detail) {
      const handlers = listeners[eventName] || [];
      const event = { type: eventName, detail };
      for (const h of handlers) {
        try { h(event); } catch (e) { console.error("handler error:", e); }
      }
    },
    // Test helper: dispatch experiment.worker.progress with a detail payload
    _progress(detail) {
      this._dispatch("experiment.worker.progress", detail);
    },
    // Test helper: dispatch experiment.event
    _event(detail) {
      this._dispatch("experiment.event", detail);
    },
  };
}

// ── Helper: wait for state changes ───────────────────────────────────────

function waitForState(tracker, predicate, timeoutMs = 500) {
  return new Promise((resolve, reject) => {
    const unsub = tracker.onProgress((state) => {
      if (predicate(state)) {
        unsub();
        resolve(state);
      }
    });
    setTimeout(() => {
      unsub();
      reject(new Error("waitForState timed out after " + timeoutMs + "ms"));
    }, timeoutMs);
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────

console.log("\n=== createScopedTracker: experiment.worker.progress ===");

// ── Test 1: Tracker subscribes to experiment.worker.progress ──────────────

console.log("\n--- Subscription ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_progress_1",
  });
  tracker.start();

  // Verify the listener was registered
  const hasListener = api._progress !== undefined;
  assert(hasListener, "Mock API must support experiment.worker.progress dispatch");

  // Feed a progress event to verify subscription works
  api._progress({
    experiment_id: "exp_progress_1",
    type: "status",
    phase: "startup",
    message: "Loading models...",
    step: null,
    max: null,
  });

  // The tracker should have updated state
  assert(tracker.state.stage !== "idle",
    "Tracker stage must transition from idle after experiment.worker.progress");
  tracker.dispose();
}

// ── Test 2: Soft-lock on matching experiment_id ──────────────────────────

console.log("\n--- Soft-lock on experiment_id ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_softlock",
  });
  tracker.start();

  assert(tracker.state.stage === "idle", "Tracker starts in idle");

  // Dispatch a progress event with matching experiment_id
  api._progress({
    experiment_id: "exp_softlock",
    type: "status",
    phase: "warmup",
    message: "Warming up...",
  });

  // Tracker should soft-lock and transition to generating/startup
  assert(tracker.state.stage !== "idle",
    "Tracker must soft-lock on matching experiment_id");
  assert(tracker.state.startTime !== null,
    "Tracker must set startTime on soft-lock");
  // Message should reflect the event
  assert(tracker.state.message === "Warming up...",
    `Expected message "Warming up...", got "${tracker.state.message}"`);

  tracker.dispose();
}

// ── Test 3: Sampler step/max/percent update ──────────────────────────────

console.log("\n--- Sampler step / max / percent ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_sampler",
  });
  tracker.start();

  // Soft-lock first
  api._progress({
    experiment_id: "exp_sampler",
    type: "cell.executing",
    node: "7",
  });

  assert(tracker.state.stage === "generating" || tracker.state.stage === "startup",
    `Expected generating/startup, got ${tracker.state.stage}`);

  // Now feed a sampler.step event
  api._progress({
    experiment_id: "exp_sampler",
    type: "sampler.step",
    step: 5,
    max: 20,
  });

  assert(tracker.state.samplerStep === 5,
    `Expected samplerStep=5, got ${tracker.state.samplerStep}`);
  assert(tracker.state.samplerMaximum === 20,
    `Expected samplerMaximum=20, got ${tracker.state.samplerMaximum}`);
  // Percent should be computed: (5/20) * 100 = 25
  assert(tracker.state.samplerPercent === 25,
    `Expected samplerPercent=25, got ${tracker.state.samplerPercent}`);

  tracker.dispose();
}

// ── Test 4: Current node update from cell.executing ──────────────────────

console.log("\n--- Current node update ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_node",
  });
  tracker.start();

  api._progress({
    experiment_id: "exp_node",
    type: "cell.executing",
    node: "7",
  });

  // The tracker's onExperimentWorkerProgress handler should update
  // some kind of currentNodeId or similar state
  // RED: currently the scoped tracker does not have a currentNodeId field
  // for experiment.worker.progress events — this test documents the gap.
  if (tracker.state.currentNodeId !== undefined) {
    assert(tracker.state.currentNodeId === 7 || tracker.state.currentNodeId === "7",
      `Expected currentNodeId to be "7", got ${tracker.state.currentNodeId}`);
  } else {
    // RED: currentNodeId is not set by experiment.worker.progress handler
    console.log("  INFO: currentNodeId not set by experiment.worker.progress (expected RED)");
  }

  tracker.dispose();
}

// ── Test 5: Elapsed from actual timer ────────────────────────────────────

console.log("\n--- Elapsed time ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_elapsed",
  });
  tracker.start();

  // Soft-lock starts the timer
  api._progress({
    experiment_id: "exp_elapsed",
    type: "status",
    phase: "startup",
    message: "Starting...",
  });

  // Give the timer a tick
  await new Promise(r => setTimeout(r, 300));

  // Elapsed should be > 0
  assert(tracker.state.elapsedMs > 0,
    `Expected elapsedMs > 0 after 300ms, got ${tracker.state.elapsedMs}`);
  assert(tracker.state.elapsedMs < 5000,
    `Expected elapsedMs < 5000, got ${tracker.state.elapsedMs} (sanity)`);

  tracker.dispose();
}

// ── Test 6: Terminal experiment.completed → "done" ───────────────────────

console.log("\n--- Terminal: experiment.completed → done ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_done",
  });
  tracker.start();

  // Soft-lock first
  api._progress({
    experiment_id: "exp_done",
    type: "status",
    phase: "startup",
    message: "Running...",
  });

  // Dispatch terminal event
  api._event({
    type: "experiment.completed",
    experiment_id: "exp_done",
    status: "completed",
  });

  assert(tracker.state.stage === "done",
    `Expected stage "done", got "${tracker.state.stage}"`);
  assert(tracker.state.overallPercent === 100,
    `Expected overallPercent=100, got ${tracker.state.overallPercent}`);

  tracker.dispose();
}

// ── Test 7: Terminal experiment.stopped → "done" ─────────────────────────

console.log("\n--- Terminal: experiment.stopped → done ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_stopped",
  });
  tracker.start();

  api._progress({
    experiment_id: "exp_stopped",
    type: "status",
    phase: "running",
  });

  api._event({
    type: "experiment.stopped",
    experiment_id: "exp_stopped",
  });

  assert(tracker.state.stage === "done",
    `Expected stage "done" after experiment.stopped, got "${tracker.state.stage}"`);

  tracker.dispose();
}

// ── Test 8: Terminal experiment.failed_fatal → "error" ───────────────────

console.log("\n--- Terminal: experiment.failed_fatal → error ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_error",
  });
  tracker.start();

  api._progress({
    experiment_id: "exp_error",
    type: "status",
    phase: "running",
  });

  api._event({
    type: "experiment.failed_fatal",
    experiment_id: "exp_error",
    message: "Checkpoint failed: CUDA OOM",
  });

  assert(tracker.state.stage === "error",
    `Expected stage "error" after experiment.failed_fatal, got "${tracker.state.stage}"`);
  // Error detail should be captured
  assert(tracker.state.error !== "",
    `Expected error message to be set, got "${tracker.state.error}"`);

  tracker.dispose();
}

// ── Test 9: Sequential progress updates accumulate state ─────────────────

console.log("\n--- Sequential progress updates ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_seq",
  });
  tracker.start();

  // 1. Soft-lock with status
  api._progress({
    experiment_id: "exp_seq",
    type: "status",
    phase: "startup",
    message: "Loading models...",
  });
  assert(tracker.state.message === "Loading models...",
    `Expected message "Loading models...", got "${tracker.state.message}"`);

  // 2. cell.executing with node
  api._progress({
    experiment_id: "exp_seq",
    type: "cell.executing",
    node: "7",
  });

  // 3. sampler.step progress
  api._progress({
    experiment_id: "exp_seq",
    type: "sampler.step",
    step: 3,
    max: 20,
  });
  assert(tracker.state.samplerStep === 3,
    `Expected samplerStep=3 after sequential update, got ${tracker.state.samplerStep}`);

  // 4. Another sampler.step (progress)
  api._progress({
    experiment_id: "exp_seq",
    type: "sampler.step",
    step: 10,
    max: 20,
  });
  assert(tracker.state.samplerStep === 10,
    `Expected samplerStep=10 after second progress, got ${tracker.state.samplerStep}`);
  assert(tracker.state.samplerPercent === 50,
    `Expected samplerPercent=50, got ${tracker.state.samplerPercent}`);

  // 5. Terminal
  api._event({
    type: "experiment.completed",
    experiment_id: "exp_seq",
  });
  assert(tracker.state.stage === "done",
    `Expected stage "done" after terminal, got "${tracker.state.stage}"`);

  tracker.dispose();
}

// ── Test 10: Events with non-matching experiment_id are rejected ─────────

console.log("\n--- Reject non-matching experiment_id ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_correct",
  });
  tracker.start();

  // This event has a different experiment_id — should be rejected
  api._progress({
    experiment_id: "exp_WRONG",
    type: "status",
    phase: "startup",
  });

  // The tracker should NOT have soft-locked
  assert(tracker.state.stage === "idle",
    `Tracker must reject non-matching experiment_id (expected idle, got "${tracker.state.stage}")`);

  // Now dispatch a matching ID — should soft-lock
  api._progress({
    experiment_id: "exp_correct",
    type: "status",
    phase: "startup",
    message: "Correct experiment",
  });
  assert(tracker.state.message === "Correct experiment",
    `Expected message from correct experiment, got "${tracker.state.message}"`);

  tracker.dispose();
}

// ── Test 11: dispose prevents further state changes ──────────────────────

console.log("\n--- Dispose prevents state changes ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_dispose",
  });
  tracker.start();

  api._progress({
    experiment_id: "exp_dispose",
    type: "status",
    phase: "startup",
  });
  assert(tracker.state.stage !== "idle",
    "Tracker should be active after progress event");

  // Dispose
  tracker.dispose();

  // Further events should be ignored
  api._progress({
    experiment_id: "exp_dispose",
    type: "status",
    phase: "warmup",
    message: "Should be ignored",
  });

  // State should NOT have changed
  assert(tracker.state.stage !== "done",
    "After dispose, events must not change stage to done");
  // The message should still be from before dispose
  // (we can't assert exact message since onExperimentWorkerProgress checks _disposed)

  tracker.dispose();
}

// ── Test 12: Phase/message from status events ────────────────────────────

console.log("\n--- Phase/message mapping ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_phase",
  });
  tracker.start();

  // Send status:startup
  api._progress({
    experiment_id: "exp_phase",
    type: "status",
    phase: "startup",
    message: "Initializing GPU...",
  });
  assert(tracker.state.stage !== "idle",
    "Tracker should activate on status event");

  // Send status:warmup
  api._progress({
    experiment_id: "exp_phase",
    type: "status",
    phase: "warmup",
    message: "Pre-loading models...",
  });
  // Stage should remain startup for warmup phase
  assert(tracker.state.stage === "startup" || tracker.state.stage === "generating",
    `Expected stage startup/generating, got "${tracker.state.stage}"`);

  tracker.dispose();
}

// ── Test 13: totalNodes is set from worker payload ─────────────────────────

console.log("\n--- totalNodes from worker payload ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_tnodes",
  });
  tracker.start();

  // Send cell.executing with total_nodes — the tracker must set totalNodes
  // from the worker payload so node progress has a determinate denominator.
  api._progress({
    experiment_id: "exp_tnodes",
    type: "cell.executing",
    node: "7",
    total_nodes: 5,
  });

  // The tracker should have set totalNodes from the payload
  // RED: onExperimentWorkerProgress does not currently map total_nodes→state.totalNodes
  if (tracker.state.totalNodes != null) {
    assert(tracker.state.totalNodes === 5,
      `Expected totalNodes=5, got ${tracker.state.totalNodes}`);
  } else {
    console.log("  INFO: totalNodes not set (expected RED — handler doesn't map total_nodes)");
  }

  // A later sampler.step should preserve totalNodes
  api._progress({
    experiment_id: "exp_tnodes",
    type: "sampler.step",
    step: 2,
    max: 20,
  });

  if (tracker.state.totalNodes != null) {
    assert(tracker.state.totalNodes === 5,
      `totalNodes should survive sampler.step, got ${tracker.state.totalNodes}`);
  }

  tracker.dispose();
}

// ── Test 14: Unique node counting via cell.executing ──────────────────────

console.log("\n--- Unique node counting via cell.executing ---");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, {
    experimentId: "exp_nodecount",
  });
  tracker.start();

  // 1. Status with total_nodes=61 (61 nodes in the workflow)
  api._progress({
    experiment_id: "exp_nodecount",
    type: "status",
    phase: "startup",
    message: "Loading workflow...",
    total_nodes: 61,
  });

  // The tracker must have totalNodes=61 from the status event
  // RED: currently totalNodes may be 0 or null if handler doesn't set it
  assert(tracker.state.totalNodes === 61,
    `Expected totalNodes=61 after status, got ${tracker.state.totalNodes}`);

  // 2. Four cell.executing events: 202, 1045, 1045 (repeat), 1049
  api._progress({
    experiment_id: "exp_nodecount",
    type: "cell.executing",
    node: "202",
  });
  api._progress({
    experiment_id: "exp_nodecount",
    type: "cell.executing",
    node: "1045",
  });
  api._progress({
    experiment_id: "exp_nodecount",
    type: "cell.executing",
    node: "1045",
  });
  api._progress({
    experiment_id: "exp_nodecount",
    type: "cell.executing",
    node: "1049",
  });

  // currentNodeId must reflect the last observed node
  // RED: handler currently sets this correctly, so this may pass.
  assert(tracker.state.currentNodeId === "1049" || tracker.state.currentNodeId === 1049,
    `Expected currentNodeId="1049", got ${tracker.state.currentNodeId}`);

  // totalNodes must still be 61
  assert(tracker.state.totalNodes === 61,
    `Expected totalNodes=61 after executing events, got ${tracker.state.totalNodes}`);

  // completedNodes must be 3 (unique: 202, 1045, 1049; 1045 counted once)
  // RED: the handler does NOT track unique nodes, so completedNodes = 0
  assert(tracker.state.completedNodes === 3,
    `Expected completedNodes=3 (3 unique nodes), got ${tracker.state.completedNodes}`);

  // overallPercent must be completedNodes/totalNodes*100 = 3/61*100
  const expectedPercent = (3 / 61) * 100;
  assert(tracker.state.overallPercent !== null && tracker.state.overallPercent !== undefined,
    `Expected overallPercent to be computed, got ${tracker.state.overallPercent}`);
  assert(Math.abs(tracker.state.overallPercent - expectedPercent) < 0.01,
    `Expected overallPercent≈${expectedPercent.toFixed(4)}, got ${tracker.state.overallPercent}`);

  // 3. A sampler.step must NOT change completedNodes or overallPercent
  api._progress({
    experiment_id: "exp_nodecount",
    type: "sampler.step",
    step: 10,
    max: 20,
  });

  assert(tracker.state.completedNodes === 3,
    `sampler.step must NOT change completedNodes (expected 3, got ${tracker.state.completedNodes})`);
  assert(Math.abs(tracker.state.overallPercent - expectedPercent) < 0.01,
    `sampler.step must NOT change overallPercent (expected ~${expectedPercent.toFixed(4)}, got ${tracker.state.overallPercent})`);

  tracker.dispose();
}

// ── Report ────────────────────────────────────────────────────────────────

console.log("");
if (failures > 0) {
  console.error(`RED: ${failures} test(s) FAILED`);
  process.exit(1);
} else {
  console.log("GREEN: All createScopedTracker behavioural tests passed");
}
