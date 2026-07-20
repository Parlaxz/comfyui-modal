// Modal — Queue Prompt Pre-fetch Timing Unit Tests
//
// Tests the capture/consume logic contract that underlies the pre-fetch
// timing fix.  Validates:
//   1. Captures a timestamp on queuePrompt invocation
//   2. Consumes the capture on fetchApi call
//   3. Single-use semantics: second consume returns null
//   4. Stale captures (>60s) are discarded
//   5. Fresh captures within the 60s window are consumed
//   6. Direct calls (no pending capture) get null
//   7. Queue-to-fetch delta is computable
//
// Run: node tests/browser/test_queue_prompt_timing.mjs

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

// ── Capture/Consume state machine (same contract as modal-node.js) ──────

function createCaptureState() {
  let pendingCapture = null;
  return {
    capture() {
      pendingCapture = { queue_prompt_start_ms: Date.now() };
    },
    consume() {
      const cap = pendingCapture;
      pendingCapture = null;
      if (!cap) return null;
      if (Date.now() - cap.queue_prompt_start_ms > 60000) return null; // stale
      return cap;
    },
    peek() { return pendingCapture; },
  };
}

// ═════════════════════════════════════════════════════════════════════════════
// TESTS
// ═════════════════════════════════════════════════════════════════════════════

// ── 1. Basic Capture & Consume ─────────────────────────────────────────

console.log("\n=== Basic Capture & Consume ===");

{
  const state = createCaptureState();
  assert(state.peek() === null, "Should start with no pending capture");

  state.capture();
  assert(state.peek() !== null, "After capture, pending should exist");

  const cap = state.consume();
  assert(cap !== null, "Consume should return a capture");
  assert(typeof cap.queue_prompt_start_ms === "number",
    `queue_prompt_start_ms should be a number, got ${typeof cap.queue_prompt_start_ms}`);
  assert(state.peek() === null, "After consume, pending should be cleared");
}

// ── 2. Single-Use Semantics ────────────────────────────────────────────

console.log("\n=== Single-Use Semantics ===");

{
  const state = createCaptureState();
  state.capture();
  const first = state.consume();
  assert(first !== null, "First consume should return capture");

  const second = state.consume();
  assert(second === null, "Second consume should return null (single-use)");
}

// ── 3. Stale Capture (>60s) Discarded ─────────────────────────────────

console.log("\n=== Stale Capture Discarded (>60s) ===");

{
  const origDateNow = Date.now;
  let fakeNow = 100000;
  Date.now = () => fakeNow;

  try {
    const state = createCaptureState();
    state.capture();
    fakeNow += 120000; // advance 120s — past 60s limit
    const cap = state.consume();
    assert(cap === null, "Stale capture (>60s) should be discarded");
    assert(state.peek() === null, "After consuming stale, pending should be null");
  } finally {
    Date.now = origDateNow;
  }
}

// ── 4. Fresh Capture Within 60s Window ────────────────────────────────

console.log("\n=== Fresh Capture Within 60s Window ===");

{
  const origDateNow = Date.now;
  let fakeNow = 500000;
  Date.now = () => fakeNow;

  try {
    const state = createCaptureState();
    state.capture();
    fakeNow += 30000; // advance 30s — within 60s window
    const cap = state.consume();
    assert(cap !== null, "Fresh capture (<60s) should be consumed");
    assert(cap.queue_prompt_start_ms === 500000,
      `queue_prompt_start_ms should be 500000, got ${cap.queue_prompt_start_ms}`);
  } finally {
    Date.now = origDateNow;
  }
}

// ── 5. No Pending Capture (direct call) ───────────────────────────────

console.log("\n=== No Pending Capture (direct call) ===");

{
  const state = createCaptureState();
  const cap = state.consume();
  assert(cap === null, "No capture should return null (direct/benchmark call)");
}

// ── 6. Queue-to-Fetch Delta Computable ────────────────────────────────

console.log("\n=== Queue-to-Fetch Delta Computable ===");

{
  const origDateNow = Date.now;
  let fakeNow = 200000;
  Date.now = () => fakeNow;

  try {
    const state = createCaptureState();
    state.capture();

    // Simulate queue-to-fetch delay (e.g. graphToPrompt takes 500ms)
    fakeNow += 500;
    const captureAt = 200000;

    // Consume and compute delta
    const cap = state.consume();
    assert(cap !== null, "Capture should be consumed");
    const delta = fakeNow - cap.queue_prompt_start_ms;
    assert(delta >= 500, `Delta should reflect elapsed time, got ${delta}`);
    assert(delta === 500, `Expected delta of 500ms, got ${delta}`);
  } finally {
    Date.now = origDateNow;
  }
}

// ── 7. Consume Clears Pending (even on stale) ────────────────────────

console.log("\n=== Consume Clears Pending (even on stale) ===");

{
  const origDateNow = Date.now;
  let fakeNow = 300000;
  Date.now = () => fakeNow;

  try {
    const state = createCaptureState();
    state.capture();

    // Advance past 60s
    fakeNow += 70000;
    const cap = state.consume();
    assert(cap === null, "Stale capture returns null");
    assert(state.peek() === null, "Consume must clear pending even when stale");
  } finally {
    Date.now = origDateNow;
  }
}

// ═════════════════════════════════════════════════════════════════════════════
// REPORT
// ═════════════════════════════════════════════════════════════════════════════

console.log("");
if (failures > 0) {
  console.error(`RED: ${failures} of ${tests} test(s) FAILED`);
  process.exit(1);
} else {
  console.log(`GREEN: All ${tests} queue prompt timing tests passed`);
}
