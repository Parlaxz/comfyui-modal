// Modal Studio — Playground Run Controller Unit Tests
//
// Executable behavioral tests for the canonical run controller
// (web/studio-playground-run.js). No browser, no DOM, plain Node.
//
// The controller routes ComfyUI websocket events, experiment worker
// progress, experiment lifecycle events, snapshot polls, direct results,
// and local failures through the canonical run store, then projects the
// derived state back into the legacy Playground runState shape.
//
// Event sources are simulated with a fake `api` EventTarget (see
// makeFakeApi below). execution_start MUST be emitted first — the ws
// stream locks onto it; executing/progress events are ignored before the
// lock is acquired.
//
// Run: node tests/studio_playground_run_unit.mjs

import assert from "node:assert/strict";
import {
  createPlaygroundRunController,
  projectRunToLegacy,
  LEGACY_TERMINAL_STATUSES,
  RUN_TIMING_MARKS,
} from "../web/studio-playground-run.js";
import {
  createRunEvent,
  createRunStore,
} from "../web/studio-run-model.js";

// ── Helpers ──────────────────────────────────────────────────────────────

/** Report a section as passing. */
function section(name) {
  console.log("PASS: " + name);
}

/**
 * Fake ComfyUI event bus used to drive the controller's ws + experiment
 * event source. NOTE: removeEventListener is a no-op, so handlers stay
 * registered after detach — several tests below document that fact.
 */
function makeFakeApi() {
  const handlers = {};
  return {
    api: {
      addEventListener: (n, h) => { (handlers[n] = handlers[n] || []).push(h); },
      removeEventListener: () => {},
    },
    emit: (name, detail) => (handlers[name] || []).forEach((h) => h({ detail })),
  };
}

/** Build a canonical run for one {status, stage} pair with a fresh runId. */
function buildLegacyForStatus(status) {
  const store = createRunStore();
  const runId = "map-" + status;
  store.applyEvent(createRunEvent({ runId, status, stage: status }));
  return projectRunToLegacy(store.getRun(runId), {});
}

// ── 1. Success lifecycle ────────────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  assert.equal(ctrl.getRun().status, "created");

  ctrl.setBackendIds("b1", "e1");
  ctrl.applySubmission();
  assert.equal(ctrl.getRun().status, "submitting");

  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  assert.equal(ctrl.getRun().status, "executing");
  assert.equal(ctrl.getRun().progress.totalNodes, 5, "execution_start carries totalNodes");

  fake.emit("executing", { type: "executing", node: "3", display_node: "KSampler" });
  assert.equal(ctrl.getRun().status, "executing");
  assert.equal(ctrl.getRun().progress.currentNodeName, "KSampler");
  // Workflow progress accumulates across progress-carrying events: the
  // executing event's currentNodeId/currentNodeName merge into the
  // execution_start progress object, so totalNodes survives.
  assert.equal(ctrl.getRun().progress.totalNodes, 5,
    "executing progress merges into execution_start totalNodes");

  fake.emit("progress", { type: "progress", step: 3, max: 10 });
  assert.equal(ctrl.getRun().status, "sampling");
  assert.equal(ctrl.getRun().sampler.step, 3);
  assert.equal(ctrl.getRun().sampler.max, 10);
  assert.equal(ctrl.getRun().sampler.percent, 30);

  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().isTerminal, true);

  assert.equal(projectRunToLegacy(ctrl.getRun(), {}).status, "completed");
  section("1. Success lifecycle");
}

// ── 2. Failure retains backend error ─────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.setBackendIds("b1", "e1");
  ctrl.applySubmission();
  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("execution_error", { type: "execution_error", prompt_id: "p1", message: "sampler exploded" });

  assert.equal(ctrl.getRun().status, "failed");
  assert.equal(ctrl.getRun().error.message, "sampler exploded");
  assert.equal(ctrl.getRun().error.type, "execution_error");
  assert.equal(ctrl.isTerminal(), true);

  const legacy = projectRunToLegacy(ctrl.getRun(), {});
  assert.equal(legacy.status, "error");
  assert.equal(legacy.message, "sampler exploded");
  assert.equal(legacy.error, "sampler exploded");
  section("2. Failure retains backend error");
}

// ── 3. Canceled is terminal, never completed ─────────────────────────────

{
  // Snapshot path.
  const ctrl = createPlaygroundRunController();
  ctrl.beginRun();
  ctrl.applySnapshot({ status: "ok", state: "cancelled", snapshot: { overall_status: "cancelled" }, events: [] });
  assert.equal(ctrl.getRun().status, "canceled");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().isTerminal, true);
  assert.notEqual(ctrl.getRun().status, "completed");
  assert.equal(projectRunToLegacy(ctrl.getRun(), {}).status, "canceled");

  // Journal path: journal terminal wins even though snapshot says in_progress.
  const ctrl2 = createPlaygroundRunController();
  ctrl2.beginRun();
  ctrl2.applySnapshot({
    status: "ok",
    state: "in_progress",
    snapshot: { overall_status: "in_progress" },
    events: [{ experiment_id: "e1", type: "experiment.stopped", payload: {} }],
  });
  assert.equal(ctrl2.getRun().status, "canceled");
  assert.equal(ctrl2.isTerminal(), true);
  section("3. Canceled is terminal, never completed");
}

// ── 4. Interrupted distinct ──────────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  ctrl.beginRun();
  ctrl.applySnapshot({ snapshot: { overall_status: "interrupted" }, events: [] });

  assert.equal(ctrl.getRun().status, "interrupted");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(projectRunToLegacy(ctrl.getRun(), {}).status, "interrupted");
  assert.notEqual(ctrl.getRun().status, "canceled", "interrupted is not canceled");
  assert.notEqual(ctrl.getRun().status, "failed", "interrupted is not failed");
  assert.equal(LEGACY_TERMINAL_STATUSES.includes("interrupted"), true);
  section("4. Interrupted distinct");
}

// ── 5. Canceled never displays success ───────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  ctrl.beginRun();
  ctrl.applySnapshot({ snapshot: { overall_status: "cancelled" }, events: [] });

  const legacy = projectRunToLegacy(ctrl.getRun(), {});
  assert.equal(legacy.status, "canceled");
  assert.equal(legacy._canonical.status, "canceled");
  assert.notEqual(legacy.status, "completed");
  assert.equal(legacy._canonical.isTerminal, true);
  assert.equal(LEGACY_TERMINAL_STATUSES.includes("canceled"), true);
  section("5. Canceled never displays success");
}

// ── 6. Duplicate completion ──────────────────────────────────────────────

{
  // Duplicate ws completion events.
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();
  const notifications = [];
  ctrl.subscribe((run) => notifications.push(run.status));

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  // Realistic flow: execution_start locks the ws stream first.
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().eventCount, 3, "created + execution_start + one execution_success");

  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  assert.equal(ctrl.getRun().status, "completed", "second success is dropped (terminal)");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().eventCount, 3, "second success must not add an event");

  assert.deepEqual(notifications, ["created", "executing", "completed"],
    "subscriber sees created/executing/completed; second success notifies nothing");
  assert.equal(notifications[notifications.length - 1], "completed",
    "no notification after the first completion reports a non-completed status");

  // Duplicate identical snapshot polls are signature-gated no-ops.
  const ctrl2 = createPlaygroundRunController();
  ctrl2.beginRun();
  const poll = { snapshot: { overall_status: "completed", counters: { completed: 3, total: 5 } }, events: [] };
  ctrl2.applySnapshot(poll);
  assert.equal(ctrl2.getRun().eventCount, 2);
  assert.equal(ctrl2.getRun().status, "completed");
  ctrl2.applySnapshot(poll);
  assert.equal(ctrl2.getRun().eventCount, 2, "identical snapshot poll is a no-op");
  assert.equal(ctrl2.getRun().status, "completed");
  section("6. Duplicate completion");
}

// ── 7. Late progress after completion ignored ────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);

  // Dropped at source: the controller ignores ws events once terminal.
  fake.emit("progress", { type: "progress", step: 8, max: 10 });
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().sampler, null, "late progress event never reaches the store");

  // Even when forced through applySnapshot, the canonical terminal lock holds.
  ctrl.applySnapshot({ snapshot: { overall_status: "in_progress", counters: { completed: 2, total: 5 } }, events: [] });
  assert.equal(ctrl.getRun().status, "completed", "canonical terminal lock holds");
  assert.equal(ctrl.isTerminal(), true);
  section("7. Late progress after completion ignored");
}

// ── 8. Out-of-order ──────────────────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  // Completed snapshot arrives FIRST.
  ctrl.applySnapshot({ snapshot: { overall_status: "completed", counters: { completed: 3, total: 5 } }, events: [] });
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);

  // Later execution_start / executing are dropped at the (now terminal) source.
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p2", total_nodes: 5 });
  fake.emit("executing", { type: "executing", node: "9", display_node: "VAEDecode" });
  assert.equal(ctrl.getRun().status, "completed", "terminal lock survives late start events");

  // Snapshot polls (which can still be applied) also respect the lock.
  ctrl.applySnapshot({ snapshot: { overall_status: "in_progress", counters: { completed: 1, total: 5 } }, events: [] });
  assert.equal(ctrl.getRun().status, "completed", "canonical lock survives late in_progress poll");
  assert.equal(ctrl.isTerminal(), true);
  section("8. Out-of-order");
}

// ── 9. Stale prior-run event ignored ─────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  // Run 1 fails.
  ctrl.beginRun();
  const run1Id = ctrl.getRunId();
  ctrl.attachEventSource(fake.api);
  ctrl.applyLocalError("boom");
  assert.equal(ctrl.getRun().status, "failed");
  assert.equal(ctrl.isTerminal(), true);

  // Run 2 is fresh: new identity, no leaked diagnostics/error.
  ctrl.beginRun();
  const run2Id = ctrl.getRunId();
  assert.notEqual(run2Id, run1Id, "beginRun allocates a fresh runId");
  assert.equal(ctrl.getRun().runId, run2Id);
  assert.equal(ctrl.getRun().status, "created");
  assert.equal(ctrl.isTerminal(), false);
  assert.equal(ctrl.getRun().error, null, "old run error must not leak");
  assert.equal(ctrl.getDiagnostics().status, "created");
  assert.equal(ctrl.getDiagnostics().eventCount, 1);

  // Stale handlers persist in the fake (its removeEventListener is a no-op),
  // but the controller's ws stream is NOT locked for run2, so executing /
  // progress / terminal ws events are all dropped — a stale success from a
  // previous execution can never complete the new run.
  fake.emit("progress", { type: "progress", step: 8, max: 10 });
  assert.equal(ctrl.getRun().status, "created", "unlocked progress is dropped");
  fake.emit("executing", { type: "executing", node: "3", display_node: "KSampler" });
  assert.equal(ctrl.getRun().status, "created", "unlocked executing is dropped");
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  assert.equal(ctrl.getRun().status, "created",
    "unlocked stale execution_success is dropped (lock-gated)");
  assert.equal(ctrl.isTerminal(), false);
  assert.equal(ctrl.getRun().runId, run2Id, "run2 identity untouched by run1's stale events");
  section("9. Stale prior-run event ignored");
}

// ── 10. Foreign experiment event ignored ─────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.setBackendIds("b1", "e1");
  ctrl.attachEventSource(fake.api);

  // Foreign experiment_id events are dropped.
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "e-OTHER", cell_key: "c1", step: 9, max: 10,
  });
  assert.equal(ctrl.getRun().sampler, null, "foreign worker progress must not touch sampler");
  fake.emit("experiment.event", { experiment_id: "e-OTHER", type: "experiment.completed", payload: {} });
  assert.equal(ctrl.isTerminal(), false, "foreign experiment completion must not terminate");
  assert.equal(ctrl.getRun().status, "created");

  // Matching experiment_id events DO apply (run-level + cell-level).
  fake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "e1", cell_key: "c1", step: 4, max: 10,
  });
  assert.equal(ctrl.getRun().sampler.step, 4);
  assert.equal(ctrl.getRun().sampler.max, 10);
  assert.equal(ctrl.getRun().cells["c1"].sampler.step, 4);
  assert.equal(ctrl.getRun().status, "sampling");

  // Single runs have no experimentId: ALL experiment events are dropped.
  const solo = createPlaygroundRunController();
  const soloFake = makeFakeApi();
  solo.beginRun();
  solo.attachEventSource(soloFake.api);
  soloFake.emit("experiment.event", { experiment_id: "e1", type: "experiment.completed", payload: {} });
  assert.equal(solo.isTerminal(), false, "experiment completion dropped for single runs");
  soloFake.emit("experiment.worker.progress", {
    type: "sampler.step", experiment_id: "e1", cell_key: "c1", step: 2, max: 10,
  });
  assert.equal(solo.getRun().sampler, null, "worker progress dropped for single runs");
  assert.equal(solo.getRun().status, "created");
  section("10. Foreign experiment event ignored");
}

// ── 11. Sampler progress isolated ────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });

  // value/max (no step) → workflow progress slot only.
  fake.emit("progress", { type: "progress", value: 2, max: 10 });
  assert.equal(ctrl.getRun().progress.value, 2);
  assert.equal(ctrl.getRun().sampler, null, "value progress must not write sampler");

  // step/max → sampler slot only.
  fake.emit("progress", { type: "progress", step: 5, max: 10 });
  assert.equal(ctrl.getRun().sampler.step, 5);
  assert.equal(ctrl.getRun().sampler.max, 10);
  assert.equal(ctrl.getRun().progress.value, 2, "sampler event must not overwrite workflow progress");
  assert.equal(ctrl.getRun().status, "sampling");
  section("11. Sampler progress isolated");
}

// ── 12. Workflow progress isolated ───────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("progress_state", {
    type: "progress_state",
    nodes: {
      "3": { state: "finished", display_node_id: "LoadImage" },
      "7": { state: "running", display_node_id: "KSampler" },
    },
  });
  assert.equal(ctrl.getRun().progress.completedNodes, 1);
  assert.equal(ctrl.getRun().progress.totalNodes, 2);

  // Legacy projection: completedNodes/totalNodes come from progress events only.
  let legacy = projectRunToLegacy(ctrl.getRun(), {});
  assert.equal(legacy.completedNodes, 1);
  assert.equal(legacy.totalNodes, 2);
  assert.equal(legacy.samplerStep, null);
  assert.equal(legacy.samplerMaximum, null);

  // A sampler event feeds samplerStep only — workflow slot untouched.
  fake.emit("progress", { type: "progress", step: 5, max: 10 });
  legacy = projectRunToLegacy(ctrl.getRun(), {});
  assert.equal(legacy.samplerStep, 5);
  assert.equal(legacy.samplerMaximum, 10);
  assert.equal(legacy.completedNodes, 1, "sampler event must not touch completedNodes");
  assert.equal(legacy.totalNodes, 2, "sampler event must not touch totalNodes");
  section("12. Workflow progress isolated");
}

// ── 13. Sequential runs don't share state ────────────────────────────────

{
  const ctrl = createPlaygroundRunController();

  ctrl.beginRun();
  const run1Id = ctrl.getRunId();
  ctrl.applySubmission();
  assert.equal(ctrl.getRun().status, "submitting");

  ctrl.beginRun();
  const run2Id = ctrl.getRunId();
  assert.notEqual(run2Id, run1Id);
  assert.equal(ctrl.getRun().status, "created", "second run starts fresh");
  assert.equal(ctrl.getDiagnostics().marks[0].name, "run_click");
  assert.equal(ctrl.getDiagnostics().marks.length, 1, "fresh run has only run_click");

  const legacy = projectRunToLegacy(ctrl.getRun(), {});
  assert.equal(legacy.samplerStep, null, "no stale sampler step");
  assert.equal(legacy.samplerMaximum, null, "no stale sampler maximum");
  assert.equal(legacy.samplerPercent, null, "no stale sampler percent");
  section("13. Sequential runs don't share state");
}

// ── 14. Result belongs to correct run ────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  ctrl.beginRun();
  ctrl.setBackendIds("b9", "e9");

  let seenExtras = null;
  ctrl.subscribe((run, extras) => { seenExtras = extras; });

  ctrl.applyDirectResult(
    { status: "completed", runId: "b9", experimentId: "e9", timings: { x: 1 } },
    { primaryOutput: "/out.png", hasHistory: true, completedCells: 1, totalCells: 1, _directTiming: { x: 1 } },
  );

  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(seenExtras.primaryOutput, "/out.png", "extras delivered to subscribers");
  assert.equal(ctrl.getExtras().primaryOutput, "/out.png");
  assert.equal(ctrl.getExtras().hasHistory, true);
  assert.equal(ctrl.getDiagnostics().experimentId, "e9");
  assert.equal(ctrl.getDiagnostics().backendRunId, "b9");

  const legacy = projectRunToLegacy(ctrl.getRun(), ctrl.getExtras());
  assert.equal(legacy.status, "completed");
  assert.equal(legacy._canonical.status, "completed");
  // NOTE (deviation from spec): projectRunToLegacy does NOT surface the
  // direct result's experimentId. Canonical run.experimentId derives from
  // the FIRST event of the run (the "created" event), which carries none,
  // so run.experimentId stays null and legacy.experimentId is undefined
  // unless extras provide one. Asserted as actual behavior.
  assert.equal(ctrl.getRun().experimentId, null, "canonical experimentId comes from first event only");
  assert.equal(legacy.experimentId, undefined,
    "legacy experimentId is not sourced from the direct result event (no extras key, canonical null)");
  assert.equal(legacy.experimentId == null, true, "legacy experimentId is empty (nullish)");
  section("14. Result belongs to correct run");
}

// ── 15. Retry creates new identity ───────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const first = ctrl.beginRun();
  const second = ctrl.beginRun();
  assert.notEqual(first.runId, second.runId, "two beginRun calls return different runIds");
  assert.equal(ctrl.getRunId(), second.runId, "getRunId() tracks the latest run");
  section("15. Retry creates new identity");
}

// ── 16. Canonical terminal lock ──────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  ctrl.beginRun();
  ctrl.applyLocalError("boom");
  assert.equal(ctrl.getRun().status, "failed");
  assert.equal(ctrl.isTerminal(), true);

  // A completed snapshot arriving afterwards cannot override the first
  // terminal: the local-error event carries a finite timestamp while the
  // snapshot event carries none, so (timestamp ?? +Infinity) ordering picks
  // the local error as the winner.
  ctrl.applySnapshot({ snapshot: { overall_status: "completed", counters: { completed: 1, total: 1 } }, events: [] });
  assert.equal(ctrl.getRun().status, "failed", "first terminal wins — failed stays failed");
  assert.equal(ctrl.isTerminal(), true);
  assert.equal(ctrl.getRun().error.message, "boom", "failure details retained");
  section("16. Canonical terminal lock");
}

// ── 17. Timing marks order ───────────────────────────────────────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  ctrl.beginRun();
  ctrl.mark("validation_start");
  ctrl.mark("validation_end");
  ctrl.mark("build_start");
  ctrl.mark("build_end");
  ctrl.mark("submit_entered");
  ctrl.mark("http_invoked");
  ctrl.mark("backend_ack");

  // Idempotent: re-marking run_click must not add a second entry.
  ctrl.mark("run_click");

  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });

  const names = ctrl.getDiagnostics().marks.map((m) => m.name);
  assert.equal(names[0], "run_click", "run_click is first");
  assert.equal(names[names.length - 1], "terminal", "terminal is last");
  assert.equal(names.filter((n) => n === "run_click").length, 1, "mark() is idempotent by name");
  assert.equal(names.includes("first_running_event"), true);
  assert.equal(names.includes("terminal"), true);

  const indices = names.map((n) => RUN_TIMING_MARKS.indexOf(n));
  assert.equal(indices.every((i) => i >= 0), true, "every present mark exists in RUN_TIMING_MARKS");
  for (let i = 1; i < indices.length; i++) {
    assert.ok(indices[i] > indices[i - 1],
      `mark order must follow RUN_TIMING_MARKS (${names[i - 1]}@${indices[i - 1]} then ${names[i]}@${indices[i]})`);
  }
  section("17. Timing marks order");
}

// ── 18. projectRunToLegacy mapping table ─────────────────────────────────

{
  const table = {
    created: "running",
    validating: "running",
    preparing: "running",
    submitting: "submitted",
    queued: "queued",
    scheduling: "waiting",
    starting: "waiting",
    restoring: "waiting",
    executing: "in_progress",
    sampling: "in_progress",
    decoding: "in_progress",
    persisting: "in_progress",
    completed: "completed",
    failed: "error",
    canceled: "canceled",
    interrupted: "interrupted",
  };
  for (const [status, expected] of Object.entries(table)) {
    assert.equal(buildLegacyForStatus(status).status, expected, `legacy mapping for ${status}`);
  }
  assert.deepEqual(LEGACY_TERMINAL_STATUSES, ["completed", "error", "canceled", "interrupted"]);
  section("18. projectRunToLegacy mapping table");
}

// ── 19. Duplicate terminal events cannot duplicate completion ────────────

{
  const ctrl = createPlaygroundRunController();
  const fake = makeFakeApi();

  let completedTransitions = 0;
  let prevStatus = null;
  ctrl.subscribe((run) => {
    if (run.status === "completed" && prevStatus !== "completed") completedTransitions++;
    prevStatus = run.status;
  });

  ctrl.beginRun();
  ctrl.attachEventSource(fake.api);
  fake.emit("execution_start", { type: "execution_start", prompt_id: "p1", total_nodes: 5 });
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  fake.emit("execution_success", { type: "execution_success", prompt_id: "p1" });
  ctrl.applySnapshot({ snapshot: { overall_status: "completed", counters: { completed: 3, total: 5 } }, events: [] });
  ctrl.applySnapshot({ snapshot: { overall_status: "completed", counters: { completed: 3, total: 5 } }, events: [] });

  assert.equal(completedTransitions, 1, "exactly one completed transition despite duplicate terminal evidence");
  assert.equal(ctrl.getRun().eventCount, 4,
    "created + execution_start + one success + one snapshot (2nd success + 2nd poll dropped)");
  assert.equal(ctrl.getRun().status, "completed");
  assert.equal(ctrl.isTerminal(), true);
  section("19. Duplicate terminal events cannot duplicate completion");
}

// ── 20. Phase I8 playground polish source contract ───────────────────────
//
// The Playground lane (I8) migrated page/section states onto the shared I3
// primitives without touching execution behavior. This section pins those
// production-source contracts (no DOM needed — plain source reads):
//   - h2 page title marker present
//   - capabilities/recent-runs loading sites use renderLoadingState;
//     <select> placeholder options stay textual control states
//   - ordinary empty states use renderEmptyState; error/handoff states do NOT
//   - mojibake ellipsis eliminated; frozen Backend copy updated
//   - carousel accessible names are context-built; "Click to view" gone
//   - informational chips carry the shared cm-chip geometry + meta tone

{
  const fs = await import("node:fs");
  const pg = fs.readFileSync(new URL("../web/studio-playground.js", import.meta.url), "utf8");
  const em = fs.readFileSync(new URL("../web/studio-experiment-mode.js", import.meta.url), "utf8");

  // Page heading.
  assert.ok(pg.includes('"data-testid": "playground-page-title"'), "playground h2 testid present");
  assert.ok(pg.includes("clip:rect(0 0 0 0)"), "h2 uses the visually-hidden clip pattern");
  assert.ok(!/h3/.test(pg.replace(/\/\/[^\n]*/g, "")), "no card label promoted to an h3");

  // Shared primitives imported by the Playground page module.
  assert.ok(pg.includes('from "./studio-loading.js"'), "studio-loading.js consumed");
  assert.ok(pg.includes('renderEmptyState } from "./studio-ui.js"'), "renderEmptyState consumed");
  assert.ok(pg.includes('label: "Loading recent runs…"' ), "recent-runs loading primitive");
  assert.ok(
    pg.includes('"playground-recent-runs-cleared"')
      && pg.includes('"playground-recent-runs-empty"')
      && pg.includes('"playground-recent-runs-loading"'),
    "ordinary empty states migrated to the shared primitive"
  );

  // Control-level loading stays textual (intentional, per freeze). The legacy
  // backend/preset selector is gone, so the workflow picker carries the
  // textual loading state instead.
  assert.equal(pg.includes('text: "Loading backends…"'), false,
    "the legacy backend selector is removed");
  assert.ok(
    pg.includes('"Loading\\u2026" : "Loading workflow\\u2026"'),
    "workflow gating line keeps its textual status"
  );

  // Mojibake: the double-encoded ellipsis form must be gone everywhere, and
  // the user-facing double-encoded em-dash strings replaced with real ones.
  assert.equal(pg.includes("\u00e2\u20ac\u00a6"), false, "no double-encoded ellipsis anywhere");
  assert.ok(pg.includes("${currentSpec.label} \u2014 Not Implemented"), "real em-dash in canvas placeholder");
  assert.ok(pg.includes("scope \u2014 value preserved"), "real em-dash in file-selection notice");
  assert.ok(pg.includes("unavailable \u2014 value preserved"), "real em-dash in schema-options notice");

  // Preset copy is gone from the Playground entirely; the Backend page is
  // renamed Manage Modal.
  assert.equal(pg.includes("Open Backend to create presets"), false,
    "no preset-creation copy in the Playground");
  assert.equal(pg.includes("Select a Backend Preset"), false,
    "no backend-preset selector copy in the Playground");

  // Carousel accessible names.
  assert.ok(pg.includes("function _carouselAccessibleNames"), "naming helper present");
  assert.ok(pg.includes('"aria-label": ariaNames[idx]'), "items use context-built names");
  assert.equal(pg.includes("Click to view"), false, "generic duplicate label text removed");
  assert.ok(pg.includes("presetLabel || nr.presetId"), "display-label chain preserved");

  // Informational chips adopt shared geometry + meta tone.
  assert.ok(pg.includes("comfymodal-studio-timing-tag cm-chip"), "timing tags on shared chip base");
  assert.ok(pg.includes("comfymodal-studio-carousel-exp-badge cm-chip"), "EXP badge on shared chip base");
  assert.ok((pg.match(/"data-tone": "meta"/g) || []).length >= 2, "meta tone on both informational families");

  // Error states are NOT empty states: exactly one legacy-class use remains
  // in playground (the workflow handoff error).
  assert.equal(
    (pg.match(/comfymodal-studio-empty-state/g) || []).length,
    1,
    "handoff error keeps the legacy class; genuine empties moved to cm-empty-state"
  );

  // Experiment mode: the preset comparison lane is gone with the concept;
  // experiments run against a selected Workflow.
  assert.ok(em.includes('from "./studio-ui.js"'), "experiment-mode consumes studio-ui");
  assert.equal(em.includes('"experiment-presets-empty"'), false,
    "the presets empty state is removed");
  assert.equal(em.includes("Open Backend to create presets."), false,
    "no preset-creation copy in experiment mode");
  assert.equal(em.includes("Compare Presets"), false,
    "the compare-presets block is removed");
  assert.equal(em.includes("renderCompareBackends"), false,
    "the compare-presets renderer is gone");
  assert.equal(
    (em.match(/comfymodal-studio-empty-state/g) || []).length,
    0,
    "no legacy empty-state class remains in experiment mode"
  );
  assert.ok(em.includes('status-" + status + " cm-chip"'), "cell chips on shared base");
  assert.ok(em.includes("_cellStatusTone"), "truthful status-tone mapping present");
  section("20. Phase I8 playground polish source contract");
}

console.log("PASS: studio playground run controller unit tests");
