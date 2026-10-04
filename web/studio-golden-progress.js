// Modal Studio — Golden stage progress
//
// Pure state for the cursor-based Golden stage stream.  The stream is not a
// lifecycle terminal: the POST remains authoritative for completion because
// output materialization and History V2 commit happen after the last stage.

const GOLDEN_STAGE_TYPES = new Set(["golden_stage"]);
const GOLDEN_PROGRESS_REQUEST_UNAVAILABLE = "unknown or expired request_id";

/**
 * Classify a cursor response without treating event-store registration lag as
 * a Golden stage failure. The POST/run controller remains authoritative for
 * lifecycle failure; the cursor can be unavailable before registration or
 * after the run has already terminated.
 */
export function goldenProgressResponseAction(page, runTerminal = false) {
  const message = page && (page.message || page.error);
  if (String(message || "").trim() === GOLDEN_PROGRESS_REQUEST_UNAVAILABLE) {
    return runTerminal ? "stop" : "retry";
  }
  if (page && page.status === "ok") return "apply";
  return "error";
}

function finite(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function durationMs(event) {
  const monoStart = finite(event.entry_monotonic_ns);
  const monoEnd = finite(event.end_monotonic_ns);
  if (monoStart != null && monoEnd != null && monoEnd >= monoStart) {
    return (monoEnd - monoStart) / 1e6;
  }
  const wallStart = finite(event.entry_wall_ns);
  const wallEnd = finite(event.end_wall_ns);
  if (wallStart != null && wallEnd != null && wallEnd >= wallStart) {
    return (wallEnd - wallStart) / 1e6;
  }
  return null;
}

export function createGoldenProgressState(requestId) {
  return {
    requestId: requestId != null ? String(requestId) : "",
    currentStage: null,
    failedStage: null,
    stages: [],
    byStage: new Map(),
    seenEvents: new Set(),
    percent: null,
    terminalResult: false,
    streamTerminal: false,
    error: null,
  };
}

/**
 * Apply one cursor page. Duplicate rows are keyed by request + sequence +
 * phase, so a repeated page cannot duplicate the visible stage timeline.
 */
export function applyGoldenProgressPage(state, page) {
  if (!state || !page || typeof page !== "object") return state;
  if (page.request_id != null && String(page.request_id) !== state.requestId) return state;

  const events = Array.isArray(page.events) ? page.events : [];
  for (const event of events) {
    if (!event || typeof event !== "object") continue;
    if (!GOLDEN_STAGE_TYPES.has(String(event.type || ""))) continue;
    if (event.request_id != null && String(event.request_id) !== state.requestId) continue;
    const stage = String(event.stage || "").trim();
    const phase = String(event.phase || "").trim();
    if (!stage || !["started", "completed", "failed"].includes(phase)) continue;

    const sequence = finite(event.sequence);
    const key = `${sequence == null ? "event" : sequence}:${stage}:${phase}`;
    if (state.seenEvents.has(key)) continue;
    state.seenEvents.add(key);

    let record = state.byStage.get(stage);
    if (!record) {
      record = {
        stage,
        sequence,
        phase: "started",
        started: null,
        completed: null,
        failed: null,
        durationMs: null,
      };
      state.byStage.set(stage, record);
      state.stages.push(record);
    }
    if (sequence != null && (record.sequence == null || sequence < record.sequence)) {
      record.sequence = sequence;
    }
    const snapshot = {
      sequence: record.sequence,
      entryWallNs: event.entry_wall_ns ?? null,
      entryMonotonicNs: event.entry_monotonic_ns ?? null,
      endWallNs: event.end_wall_ns ?? null,
      endMonotonicNs: event.end_monotonic_ns ?? null,
      ok: event.ok ?? null,
      error: event.error != null ? String(event.error) : null,
      durationMs: durationMs(event),
    };
    if (phase === "started") {
      record.started = snapshot;
      record.phase = "started";
      state.currentStage = stage;
    } else if (phase === "completed") {
      record.completed = snapshot;
      record.phase = "completed";
      record.durationMs = snapshot.durationMs;
      state.currentStage = stage;
    } else {
      record.failed = snapshot;
      record.phase = "failed";
      record.durationMs = snapshot.durationMs;
      state.failedStage = stage;
      state.currentStage = stage;
      state.error = snapshot.error || `${stage} failed`;
    }
  }

  state.stages.sort((a, b) => {
    if (a.sequence == null && b.sequence == null) return 0;
    if (a.sequence == null) return 1;
    if (b.sequence == null) return -1;
    return a.sequence - b.sequence;
  });
  const completed = state.stages.filter((stage) => stage.phase === "completed").length;
  if (state.stages.length > 0) {
    // The observed stage order is the only available denominator. Reserve the
    // final percentage point for the POST terminal result; it is not stage
    // completion and must not be inferred from the last stage event.
    state.percent = Math.min(99, (completed / state.stages.length) * 100);
  }
  state.streamTerminal = page.terminal === true;
  return state;
}

export function markGoldenPostTerminal(state) {
  if (!state) return state;
  state.terminalResult = true;
  state.percent = 100;
  return state;
}

export function goldenProgressSnapshot(state) {
  if (!state) return null;
  return {
    requestId: state.requestId,
    currentStage: state.currentStage,
    failedStage: state.failedStage,
    stages: state.stages.map((stage) => ({ ...stage })),
    percent: state.percent,
    terminalResult: state.terminalResult,
    streamTerminal: state.streamTerminal,
    error: state.error,
  };
}
