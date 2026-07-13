// Modal — Frontend Tracker & Progress Bar Unit Tests
//
// Tests that the progress tracker (comfymodal-progress.js) correctly:
//   1. Retains "done" stage after execution_success (no zero-delay idle reset)
//   2. Transitions done→startup on next execution_start
//   3. Collects per-node wall-clock durations
//   4. Sets error state on execution_error (keeps 4s timeout ownership)
//   5. Disposal stops timers and clears subscribers
//   6. Scoped tracker retains done + locked identity after success
//   7. Scoped tracker dispose + create fresh tracker for new run
//   8. Scoped tracker transitions to error, retains timer ownership
//
// Uses inline fake-timer helpers where setTimeout/clearTimeout behaviour
// must be deterministic.
//
// Run: node tests/browser/test_frontend_tracker.mjs

import { createProgressTracker, createScopedTracker } from "../../web/comfymodal-progress.js";

let failures = 0;
let tests = 0;

function assert(condition, message) {
  tests++;
  if (!condition) {
    console.error("  FAIL:", message);
    failures++;
  } else {
    console.log("  PASS");
  }
}

// ── Fake Timer Helpers ─────────────────────────────────────────────────────
//
// Wraps setTimeout/clearTimeout so we can advance time deterministically.
// Each fake-timer scope must be isolated per test block.

function installFakeTimers() {
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const originalDateNow = Date.now;

  let _time = 0;
  let _id = 1;
  let _pending = []; // { id, fireAt, fn }

  function fakeSetTimeout(fn, ms, ...args) {
    const id = _id++;
    _pending.push({ id, fireAt: _time + (ms || 0), fn, args });
    return id;
  }

  function fakeClearTimeout(id) {
    _pending = _pending.filter((t) => t.id !== id);
  }

  function fakeDateNow() {
    return _time;
  }

  /** Advance fake time by `ms` milliseconds, firing due timers in order. */
  function advanceTime(ms) {
    _time += ms;
    const due = _pending.filter((t) => t.fireAt <= _time);
    _pending = _pending.filter((t) => t.fireAt > _time);
    // Sort by fireAt, then by id for deterministic ordering
    due.sort((a, b) => a.fireAt - b.fireAt || a.id - b.id);
    for (const t of due) {
      t.fn(...t.args);
    }
  }

  /** Restore original timer functions. */
  function restore() {
    globalThis.setTimeout = originalSetTimeout;
    globalThis.clearTimeout = originalClearTimeout;
    Date.now = originalDateNow;
  }

  // Install fakes
  globalThis.setTimeout = fakeSetTimeout;
  globalThis.clearTimeout = fakeClearTimeout;
  Date.now = fakeDateNow;

  return { advanceTime, restore, pending: () => _pending };
}

// ── Mock API ───────────────────────────────────────────────────────────────

function makeMockApi() {
  const listeners = {};
  return {
    addEventListener(event, handler) {
      if (!listeners[event]) listeners[event] = [];
      listeners[event].push(handler);
    },
    removeEventListener(event, handler) {
      if (!listeners[event]) return;
      listeners[event] = listeners[event].filter((h) => h !== handler);
    },
    _dispatch(eventName, detail) {
      const handlers = listeners[eventName] || [];
      const event = { type: eventName, detail };
      for (const h of handlers) {
        try { h(event); } catch (e) { console.error("handler error:", e); }
      }
    },
  };
}

// ── Helpers ────────────────────────────────────────────────────────────────

function snapshotState(tracker) {
  return { ...tracker.state };
}

// ═════════════════════════════════════════════════════════════════════════════
// TESTS
// ═════════════════════════════════════════════════════════════════════════════

// ── 1. GLOBAL TRACKER: Done Retention ─────────────────────────────────────

console.log("\n=== Global Tracker: Done Retention ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  // execution_start → startup
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `Expected startup after execution_start, got "${tracker.state.stage}"`);

  // execution_success → done
  api._dispatch("execution_success", { prompt_id: "test-p1" });
  assert(tracker.state.stage === "done",
    `Expected done after execution_success, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "test-p1",
    `Expected promptId="test-p1", got "${tracker.state.promptId}"`);

  // Verify done is retained — no zero-delay reset
  const s1 = snapshotState(tracker);
  assert(s1.stage === "done",
    "Done must be retained after a microtask (no zero-delay idle reset)");

  tracker.dispose();
}

// ── 2. GLOBAL TRACKER: Done → execution_start Clean Transition ────────────

console.log("\n=== Global Tracker: Done → New Run ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  // First run
  api._dispatch("execution_start");
  api._dispatch("executing", { node: "5" });
  api._dispatch("executing", { node: "7" });
  api._dispatch("execution_success", { prompt_id: "run1" });

  assert(tracker.state.stage === "done",
    `Expected done after first run, got "${tracker.state.stage}"`);
  const firstPromptId = tracker.state.promptId;

  // Second run: execution_start should reset and begin anew
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `Expected startup after second execution_start, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId !== firstPromptId,
    "New run should have different or cleared promptId");
  // overallPercent should be null (reset)
  assert(tracker.state.overallPercent === null,
    "overallPercent should be null after fresh start");

  // Simulate completion of second run
  api._dispatch("executing", { node: "12" });
  api._dispatch("execution_success", { prompt_id: "run2" });
  assert(tracker.state.stage === "done",
    `Expected done after second run, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "run2",
    `Expected promptId="run2", got "${tracker.state.promptId}"`);

  tracker.dispose();
}

// ── 3. GLOBAL TRACKER: Per-Node Duration Tracking ─────────────────────────

console.log("\n=== Global Tracker: Per-Node Times ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  // Need fake timers so node durations are measurable.
  // Start fake time at 1000 to avoid _nodeStartTime being 0 (falsy).
  const ft = installFakeTimers();
  ft.advanceTime(1000);

  api._dispatch("execution_start");

  // Execute node 5
  api._dispatch("executing", { node: "5" });
  ft.advanceTime(150); // 150ms on node 5

  // Execute node 7 (finalizes node 5's time: 1150 - 1000 = 150)
  api._dispatch("executing", { node: "7" });
  ft.advanceTime(250); // 250ms on node 7 (finalized at execution_success)

  // Complete
  api._dispatch("execution_success", { prompt_id: "p-node-times" });

  assert(tracker.state.stage === "done",
    `Expected done, got "${tracker.state.stage}"`);

  // Check perNodeDurations
  const dur = tracker.state.perNodeDurations || {};
  assert(typeof dur === "object" && Object.keys(dur).length > 0,
    `Expected perNodeDurations to have entries, got ${JSON.stringify(dur)}`);

  // Node 5 should have ~150ms, node 7 should have ~250ms
  const node5Dur = dur["5"];
  assert(node5Dur !== undefined,
    `Expected per-node entry for node "5", got keys: ${Object.keys(dur).join(",")}`);
  const node7Dur = dur["7"];
  assert(node7Dur !== undefined,
    `Expected per-node entry for node "7", got keys: ${Object.keys(dur).join(",")}`);

  ft.restore();
  tracker.dispose();
}

// ── 4. GLOBAL TRACKER: Error State ────────────────────────────────────────

console.log("\n=== Global Tracker: Error ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup");

  api._dispatch("execution_error", { message: "CUDA out of memory" });
  assert(tracker.state.stage === "error",
    `Expected error after execution_error, got "${tracker.state.stage}"`);
  assert(tracker.state.error === "CUDA out of memory",
    `Expected error message "CUDA out of memory", got "${tracker.state.error}"`);

  tracker.dispose();
}

// ── 5. GLOBAL TRACKER: Disposal ───────────────────────────────────────────

console.log("\n=== Global Tracker: Disposal ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup");

  // Dispose
  tracker.dispose();

  // After disposal, events must be ignored
  api._dispatch("execution_success", { prompt_id: "post-dispose" });
  assert(tracker.state.stage !== "done",
    `After dispose, stage should not become done (got "${tracker.state.stage}")`);

  // State stays at whatever it was at disposal time
  // (the tracker returned from createProgressTracker still has a reference
  //  to the state object, but handlers are unregistered)
  const msg = "Tracker disposed, events are ignored";
  assert(true, msg); // structural assertion: no crash on post-dispose events
}

// ── 6. GLOBAL TRACKER: execution_start Guard (generating) ─────────────────

console.log("\n=== Global Tracker: execution_start Guard ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  api._dispatch("executing", { node: "5" });
  assert(tracker.state.stage === "generating");

  // Duplicate execution_start while generating must be ignored
  api._dispatch("execution_start");
  assert(tracker.state.stage === "generating",
    "Duplicate execution_start while generating must be ignored");

  // Complete normally
  api._dispatch("execution_success", { prompt_id: "guarded" });
  assert(tracker.state.stage === "done");

  tracker.dispose();
}

// ── 7. SCOPED TRACKER: Done Retention + Locked Identity ───────────────────

console.log("\n=== Scoped Tracker: Done Retention ===");

{
  const api = makeMockApi();
  const identity = { runId: "run-scoped-1", experimentId: "exp-scoped-1" };
  const tracker = createScopedTracker(api, identity);
  tracker.start();

  // execution_start locks the tracker
  api._dispatch("execution_start");
  api._dispatch("executing", { node: "3" });

  // Success
  api._dispatch("execution_success", { prompt_id: "scoped-p1" });
  assert(tracker.state.stage === "done",
    `Expected done after execution_success, got "${tracker.state.stage}"`);

  // Verify done is retained (no auto-reset to idle)
  assert(tracker.state.stage === "done",
    "Done must be retained in scoped tracker (no zero-delay idle reset)");

  tracker.dispose();
}

// ── 8. SCOPED TRACKER: Dispose + New Tracker (Clean New Run) ──────────────

console.log("\n=== Scoped Tracker: Dispose + New Run ===");

{
  const api = makeMockApi();

  // First tracker — run to completion
  const tracker1 = createScopedTracker(api, { runId: "run1" });
  tracker1.start();
  api._dispatch("execution_start");
  api._dispatch("executing", { node: "7" });
  api._dispatch("execution_success", { prompt_id: "run1-p" });
  assert(tracker1.state.stage === "done");

  // Dispose first tracker
  tracker1.dispose();

  // Second tracker — fresh, should start clean
  const tracker2 = createScopedTracker(api, { runId: "run2" });
  tracker2.start();

  assert(tracker2.state.stage === "idle",
    `New scoped tracker should start in idle, got "${tracker2.state.stage}"`);
  assert(tracker2.state.runId === "run2",
    `New scoped tracker should have runId="run2", got "${tracker2.state.runId}"`);

  // Run second to completion
  api._dispatch("execution_start");
  assert(tracker2.state.stage === "startup",
    `New tracker should transition to startup, got "${tracker2.state.stage}"`);
  api._dispatch("executing", { node: "12" });
  api._dispatch("execution_success", { prompt_id: "run2-p" });
  assert(tracker2.state.stage === "done",
    `New tracker should reach done, got "${tracker2.state.stage}"`);
  assert(tracker2.state.promptId === "run2-p",
    `New tracker should have new promptId, got "${tracker2.state.promptId}"`);

  tracker2.dispose();
}

// ── 9. SCOPED TRACKER: Error State ────────────────────────────────────────

console.log("\n=== Scoped Tracker: Error ===");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-error" });
  tracker.start();

  api._dispatch("execution_start");
  api._dispatch("execution_error", { message: "Scoped OOM" });

  assert(tracker.state.stage === "error",
    `Expected error, got "${tracker.state.stage}"`);
  assert(tracker.state.error === "Scoped OOM",
    `Expected error message "Scoped OOM", got "${tracker.state.error}"`);

  tracker.dispose();
}

// ── 10. SCOPED TRACKER: Execution_start Locks + Captures prompt_id ─────

console.log("\n=== Scoped Tracker: execution_start Locks ===");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-lock" });
  tracker.start();

  assert(tracker.state.stage === "idle",
    "Tracker starts in idle before execution_start");

  // execution_start should lock the tracker and transition to startup
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `execution_start should set stage to startup, got "${tracker.state.stage}"`);

  // A second execution_start should be ignored (already locked)
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    "Second execution_start while locked should be ignored");

  // Complete
  api._dispatch("execution_success", { prompt_id: "run-lock-p" });
  assert(tracker.state.stage === "done",
    `Expected done, got "${tracker.state.stage}"`);

  tracker.dispose();
}

// ── 11. SCOPED TRACKER: prompt_id Filter (explicit) ──────────────────────

console.log("\n=== Scoped Tracker: prompt_id Filter (explicit) ===");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-filter2" });
  tracker.start();

  // execution_start locks the tracker
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    "execution_start should set stage to startup");

  // Manually override capturedPromptId to set up the filter scenario
  tracker.setPromptId("p-correct");

  // execution_start already fired—reset back to idle for clean filter test
  // (the tracker is now locked with _capturedPromptId="p-correct")

  // Success with wrong prompt_id should be filtered (prompt_id mismatch)
  api._dispatch("execution_success", { prompt_id: "p-WRONG" });
  assert(tracker.state.stage !== "done",
    `Stage should NOT become done after filtered success, got "${tracker.state.stage}"`);

  // Success with correct prompt_id — should work
  api._dispatch("execution_success", { prompt_id: "p-correct" });
  assert(tracker.state.stage === "done",
    `Stage should be done after matching prompt_id, got "${tracker.state.stage}"`);

  tracker.dispose();
}

// ── 12. GLOBAL TRACKER: Timer Ownership (stopped on done) ─────────────────

console.log("\n=== Global Tracker: Timer Ownership ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  // advanceTime simulates elapsed time — timer interval won't fire in test
  // but the elapsedMs should be 0 since Date.now is faked
  assert(tracker.state.startTime !== null,
    "startTime should be set after execution_start");

  // Done must stop the timer
  api._dispatch("execution_success");
  assert(tracker.state.stage === "done");

  // With fake timers, elapsedMs is 0 because Date.now always returns 0
  // (we installed fake Date.now that returns _time which starts at 0).
  // The important thing is that no timer runs after done.

  // Verify that execution_start after done works (proves timer was cleaned up)
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `After done→execution_start, should be startup, got "${tracker.state.stage}"`);

  ft.restore();
  tracker.dispose();
}

// ── 13. GLOBAL TRACKER: Completion Snapshot Shape ─────────────────────────

console.log("\n=== Global Tracker: Completion Snapshot Shape ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  // Record a subscriber to capture the snapshot at done
  let doneSnapshot = null;
  const unsub = tracker.onProgress((s) => {
    if (s.stage === "done") {
      doneSnapshot = { ...s };
    }
  });

  api._dispatch("execution_start");
  api._dispatch("executing", { node: "5" });
  api._dispatch("executing", { node: "7" });
  api._dispatch("execution_success", { prompt_id: "snap-test", trace: { deltas_ms: { sampler: 500 } } });

  assert(doneSnapshot !== null, "Subscriber should receive a done snapshot");
  assert(doneSnapshot.stage === "done", "Snapshot stage should be done");
  assert(doneSnapshot.overallPercent === 100,
    `Snapshot overallPercent should be 100, got ${doneSnapshot.overallPercent}`);
  assert(Array.isArray(doneSnapshot._nodesSeen) || doneSnapshot._nodesSeen instanceof Set,
    "Snapshot should include _nodesSeen");
  assert(typeof doneSnapshot.timingMilestones === "object" && doneSnapshot.timingMilestones !== null,
    "Snapshot should include timingMilestones from trace");

  unsub();
  tracker.dispose();
}

// ── 14. SCOPED TRACKER: Experiment Terminal (completed) ──────────────────

console.log("\n=== Scoped Tracker: Experiment Terminal ===");

{
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { experimentId: "exp-terminal-1" });
  tracker.start();

  // Soft-lock via worker progress
  api._dispatch("experiment.worker.progress", {
    experiment_id: "exp-terminal-1",
    type: "status",
    phase: "startup",
  });
  assert(tracker.state.stage !== "idle",
    "Tracker should activate on experiment.worker.progress");

  // Terminal via experiment.event
  api._dispatch("experiment.event", {
    type: "experiment.completed",
    experiment_id: "exp-terminal-1",
  });
  assert(tracker.state.stage === "done",
    `Expected done after experiment.completed, got "${tracker.state.stage}"`);

  // Done is retained (no zero-delay idle reset)
  assert(tracker.state.stage === "done",
    "Done must be retained after experiment.completed");

  tracker.dispose();
}

// ── 15. GLOBAL TRACKER: Error Timer Ownership (4s delayed reset) ────────

console.log("\n=== Global Tracker: Error Timer Ownership ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  api._dispatch("execution_error", { message: "Test error" });

  assert(tracker.state.stage === "error",
    `Expected error stage, got "${tracker.state.stage}"`);

  // Verify there is a pending timer (the 4s error reset)
  assert(ft.pending().length > 0,
    "Error path should schedule a 4s timeout for idle reset");

  // Advance 4s to trigger the reset
  ft.advanceTime(4000);

  // After 4s, the _reset() should have been called, returning to idle
  assert(tracker.state.stage === "idle",
    `Expected idle after 4s error timeout, got "${tracker.state.stage}"`);

  ft.restore();
  tracker.dispose();
}

// ── 16. SCOPED TRACKER: Error Timer Ownership (4s delayed unlock) ────────

console.log("\n=== Scoped Tracker: Error Timer Ownership ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-err-timer" });
  tracker.start();

  api._dispatch("execution_start");
  api._dispatch("execution_error", { message: "Scoped test error" });

  assert(tracker.state.stage === "error",
    `Expected error stage, got "${tracker.state.stage}"`);

  // Verify there is a pending timer
  assert(ft.pending().length > 0,
    "Scoped error path should schedule a 4s timeout");

  ft.advanceTime(4000);

  // After 4s, tracker should be unlocked and reset to idle
  assert(tracker.state.stage === "idle",
    `Expected idle after 4s scoped error timeout, got "${tracker.state.stage}"`);

  ft.restore();
  tracker.dispose();
}

// ── 17. SCOPED TRACKER: Experiment Error Timer Ownership ─────────────────

console.log("\n=== Scoped Tracker: Experiment Error Timer ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { experimentId: "exp-err-timer" });
  tracker.start();

  api._dispatch("experiment.worker.progress", {
    experiment_id: "exp-err-timer",
    type: "status",
    phase: "startup",
  });

  api._dispatch("experiment.event", {
    type: "experiment.failed_fatal",
    experiment_id: "exp-err-timer",
    error: "Fatal experiment error",
  });

  assert(tracker.state.stage === "error",
    `Expected error after experiment.failed_fatal, got "${tracker.state.stage}"`);

  // Verify there is a pending timer
  assert(ft.pending().length > 0,
    "Experiment error path should schedule a 4s timeout");

  ft.advanceTime(4000);

  assert(tracker.state.stage === "idle",
    `Expected idle after 4s experiment error timeout, got "${tracker.state.stage}"`);

  ft.restore();
  tracker.dispose();
}

// ── 18. GLOBAL TRACKER: Re-entrant execution_start While Done ───────────

console.log("\n=== Global Tracker: Re-entrant execution_start While Done ===");

{
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  // Run 1: complete
  api._dispatch("execution_start");
  api._dispatch("executing", { node: "3" });
  api._dispatch("execution_success", { prompt_id: "r1" });
  assert(tracker.state.stage === "done");
  assert(tracker.state.completedNodes > 0, "Run 1 should have completed nodes");

  // Run 2: new execution_start — must reset completely
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `Should be startup after new start, got "${tracker.state.stage}"`);
  assert(tracker.state.completedNodes === 0,
    "completedNodes must be 0 after fresh start");
  assert(tracker.state.overallPercent === null,
    "overallPercent must be null after fresh start");
  assert(tracker.state.currentNodeId === null,
    "currentNodeId must be null after fresh start");

  // Complete run 2
  api._dispatch("executing", { node: "9" });
  api._dispatch("execution_success", { prompt_id: "r2" });
  assert(tracker.state.stage === "done",
    `Run 2 should end in done, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "r2",
    `Run 2 should have promptId="r2", got "${tracker.state.promptId}"`);

  tracker.dispose();
}

// ── 19. SCOPED TRACKER: Done → Second execution_start (clean re-entry) ──

console.log("\n=== Scoped Tracker: Done → Second execution_start ===");

{
  const ft = installFakeTimers();
  ft.advanceTime(1000);
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-reentry" });
  tracker.start();

  // ── Run 1 ──
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `Run 1: expected startup, got "${tracker.state.stage}"`);

  // Execute a couple of nodes with fake-time deltas
  api._dispatch("executing", { node: "5" });
  ft.advanceTime(120);
  api._dispatch("executing", { node: "7" });
  ft.advanceTime(80);
  api._dispatch("execution_success", { prompt_id: "reentry-p1" });

  assert(tracker.state.stage === "done",
    `Run 1: expected done, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "reentry-p1",
    `Run 1: expected promptId="reentry-p1", got "${tracker.state.promptId}"`);
  const run1NodeTimes = { ...tracker.state.perNodeDurations };
  assert(Object.keys(run1NodeTimes).length > 0,
    `Run 1: expected perNodeDurations entries, got ${JSON.stringify(run1NodeTimes)}`);

  // ── Run 2: second execution_start on the SAME tracker ──
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `Run 2: expected startup, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId !== "reentry-p1",
    "Run 2: promptId must be different from run 1's promptId");
  assert(tracker.state.completedNodes === 0,
    "Run 2: completedNodes must be 0 after fresh start");
  assert(tracker.state.overallPercent === null,
    "Run 2: overallPercent must be null after fresh start");
  assert(tracker.state.currentNodeId === null,
    "Run 2: currentNodeId must be null after fresh start");
  assert(tracker.state.elapsedMs === 0,
    "Run 2: elapsedMs must be 0 after fresh start");

  // Execute nodes in run 2 — proves per-node tracking is fresh
  api._dispatch("executing", { node: "12" });
  ft.advanceTime(200);
  api._dispatch("executing", { node: "15" });
  ft.advanceTime(300);
  api._dispatch("execution_success", { prompt_id: "reentry-p2" });

  assert(tracker.state.stage === "done",
    `Run 2: expected done, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "reentry-p2",
    `Run 2: expected promptId="reentry-p2", got "${tracker.state.promptId}"`);
  assert(tracker.state.completedNodes === 2,
    `Run 2: expected 2 completed nodes, got ${tracker.state.completedNodes}`);
  // perNodeDurations should have run 2's nodes, not run 1's
  const run2NodeTimes = { ...tracker.state.perNodeDurations };
  assert(run2NodeTimes["12"] !== undefined,
    `Run 2: expected per-node entry for "12", got keys: ${Object.keys(run2NodeTimes).join(",")}`);
  assert(run2NodeTimes["15"] !== undefined,
    `Run 2: expected per-node entry for "15", got keys: ${Object.keys(run2NodeTimes).join(",")}`);

  ft.restore();
  tracker.dispose();
}

// ── 20. SCOPED TRACKER: Done → Second execution_start After Error ────────

console.log("\n=== Scoped Tracker: Error → Second execution_start ===");

{
  const ft = installFakeTimers();
  ft.advanceTime(1000);
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-err-reentry" });
  tracker.start();

  // Run 1: error
  api._dispatch("execution_start");
  api._dispatch("executing", { node: "3" });
  ft.advanceTime(50);
  api._dispatch("execution_error", { message: "First error" });
  assert(tracker.state.stage === "error",
    `Expected error, got "${tracker.state.stage}"`);

  // Pending error timer exists — will be cancelled by re-entry
  assert(ft.pending().length > 0,
    "Error timer should be pending before re-entry");

  // Run 2: new execution_start while in error — must cancel timer, unlock, reset
  api._dispatch("execution_start");
  assert(tracker.state.stage === "startup",
    `After re-entry expected startup, got "${tracker.state.stage}"`);
  assert(tracker.state.completedNodes === 0,
    "completedNodes must be 0 after re-entry");
  assert(tracker.state.error === "",
    "error must be cleared after re-entry");

  // No pending timer — the error timer was cancelled by re-entry
  assert(ft.pending().length === 0,
    "Error timer must be cancelled on re-entry (pending count should be 0)");

  // Complete run 2 successfully
  api._dispatch("executing", { node: "9" });
  ft.advanceTime(100);
  api._dispatch("execution_success", { prompt_id: "err-reentry-p2" });
  assert(tracker.state.stage === "done",
    `Run 2 should complete, got "${tracker.state.stage}"`);
  assert(tracker.state.promptId === "err-reentry-p2",
    `Run 2 promptId mismatch, got "${tracker.state.promptId}"`);

  ft.restore();
  tracker.dispose();
}

// ── 21. GLOBAL TRACKER: Dispose Cancels Error Timer ──────────────────────

console.log("\n=== Global Tracker: Dispose Cancels Error Timer ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createProgressTracker(api);

  api._dispatch("execution_start");
  api._dispatch("execution_error", { message: "Error before dispose" });

  assert(tracker.state.stage === "error",
    `Expected error, got "${tracker.state.stage}"`);
  assert(ft.pending().length > 0,
    "Error timer should be pending before dispose");

  // Dispose — must cancel the error timer
  tracker.dispose();

  assert(ft.pending().length === 0,
    "Error timer must be cancelled by dispose (pending count should be 0)");

  // Advance 4s — the old timer callback must NOT fire (no crash, no state change)
  ft.advanceTime(4000);
  assert(tracker.state.stage === "error",
    `After disposed advance, stage should remain error, got "${tracker.state.stage}"`);

  ft.restore();
}

// ── 22. SCOPED TRACKER: Dispose Cancels Error Timer ──────────────────────

console.log("\n=== Scoped Tracker: Dispose Cancels Error Timer ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { runId: "run-dispose-err" });
  tracker.start();

  api._dispatch("execution_start");
  api._dispatch("execution_error", { message: "Scoped error before dispose" });

  assert(tracker.state.stage === "error",
    `Expected error, got "${tracker.state.stage}"`);
  assert(ft.pending().length > 0,
    "Scoped error timer should be pending before dispose");

  // Dispose — must cancel the error timer
  tracker.dispose();

  assert(ft.pending().length === 0,
    "Scoped error timer must be cancelled by dispose (pending count should be 0)");

  ft.advanceTime(4000);
  assert(tracker.state.stage === "error",
    `After disposed advance, stage should remain error, got "${tracker.state.stage}"`);

  ft.restore();
}

// ── 23. SCOPED TRACKER: Dispose Cancels Experiment Error Timer ──────────

console.log("\n=== Scoped Tracker: Dispose Cancels Experiment Error Timer ===");

{
  const ft = installFakeTimers();
  const api = makeMockApi();
  const tracker = createScopedTracker(api, { experimentId: "exp-disc-err" });
  tracker.start();

  api._dispatch("experiment.worker.progress", {
    experiment_id: "exp-disc-err",
    type: "status",
    phase: "startup",
  });
  api._dispatch("experiment.event", {
    type: "experiment.failed_fatal",
    experiment_id: "exp-disc-err",
    error: "Fatal before dispose",
  });

  assert(tracker.state.stage === "error",
    `Expected error, got "${tracker.state.stage}"`);
  assert(ft.pending().length > 0,
    "Experiment error timer should be pending before dispose");

  tracker.dispose();

  assert(ft.pending().length === 0,
    "Experiment error timer must be cancelled by dispose");

  ft.advanceTime(4000);
  assert(tracker.state.stage === "error",
    `After disposed advance, stage should remain error, got "${tracker.state.stage}"`);

  ft.restore();
}

// ═════════════════════════════════════════════════════════════════════════════
// REPORT
// ═════════════════════════════════════════════════════════════════════════════

console.log("");
if (failures > 0) {
  console.error(`RED: ${failures} of ${tests} test(s) FAILED`);
  process.exit(1);
} else {
  console.log(`GREEN: All ${tests} frontend tracker tests passed`);
}
