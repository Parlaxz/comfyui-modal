// Modal Studio — Golden stage progress
//
// Pure state for the cursor-based Golden stage stream.  The stream is not a
// lifecycle terminal: the POST remains authoritative for completion because
// output materialization and History V2 commit happen after the last stage.

const GOLDEN_STAGE_TYPES = new Set(["golden_stage"]);
// Remote "status" events (Modal/container lifecycle: scheduling, restoring,
// snapshot, plan_received, ...) share the cursor stream. They are NOT stages
// and must never affect the percent denominator — they only feed the Modal
// status line.
const STATUS_EVENT_TYPES = new Set(["status", "modal_status"]);
// Node-level detail (per-node loader/execute spans, the same family the
// terminal Gantt renders as "Node: ..." rows). Duck-typed and bounded: the
// remote may or may not emit these yet, so unknown shapes are ignored rather
// than rendered as fabricated rows.
const NODE_EVENT_TYPES = new Set(["gantt_span", "node_progress"]);
const TERMINAL_EVENT_TYPES = new Set(["result", "error", "cancelled"]);
const MAX_NODE_SPANS = 512;
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
  if (value == null || value === "") return null;
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
    // Latest remote lifecycle phase (scheduling/restoring/...), never a stage.
    statusPhase: null,
    statusMessage: null,
    // Bounded live node rows, newest last. Shape: {key,label,durationMs,phase}.
    nodeSpans: [],
    // Terminal structured forensics attached to the result event, when the
    // remote includes them (same payload the log Gantt is rendered from).
    gantt: null,
    waterfall: null,
  };
}

/**
 * Coerce a duck-typed node detail event into a bounded row, or null when the
 * event carries no usable node identity. Duration is best-effort: present
 * when the event carries an explicit duration or a closable interval, else
 * null (rendered as a live/ticking row, never a fabricated zero).
 */
function coerceNodeSpan(event) {
  const rawLabel = event.name != null ? event.name
    : event.label != null ? event.label
    : event.node != null ? event.node
    : event.stage != null ? event.stage
    : event.name != null ? event.name
    : event.label != null ? event.label : null;
  if (rawLabel == null || String(rawLabel).trim() === "") return null;
  const label = String(rawLabel).slice(0, 120);
  let duration = null;
  if (event.durationMs != null) {
    const n = Number(event.durationMs);
    if (Number.isFinite(n) && n >= 0) duration = n;
  }
  if (duration == null) duration = durationMs(event);
  const phase = String(event.phase || "").trim() || "started";
  const key = event.span_id || label + ":" + (event.entry_monotonic_ns ?? "");
  return { key, label, durationMs: duration, phase,
    startMonotonicNs: finite(event.entry_monotonic_ns),
    endMonotonicNs: finite(event.end_monotonic_ns), observedAtMs: Date.now() };
}

function upsertNodeSpan(state, nodeSpan) {
  if (!Array.isArray(state.nodeSpans)) state.nodeSpans = [];
  const at = state.nodeSpans.findIndex((row) => row && row.key === nodeSpan.key);
  if (at !== -1) {
    if (state.nodeSpans[at].phase !== "started" && nodeSpan.phase === "started") return;
    state.nodeSpans[at] = { ...nodeSpan, observedAtMs: state.nodeSpans[at].observedAtMs };
    return;
  }
  state.nodeSpans.push(nodeSpan);
  while (state.nodeSpans.length > MAX_NODE_SPANS) state.nodeSpans.shift();
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
    if (event.request_id != null && String(event.request_id) !== state.requestId) continue;
    const eventType = String(event.type || "");

    // Lifecycle status: latest wins, no dedup key needed beyond cursor order
    // (the store already cursors pages, so each event is seen once).
    if (STATUS_EVENT_TYPES.has(eventType)) {
      const phase = String(event.phase || "").trim();
      if (phase) state.statusPhase = phase;
      if (event.message != null) state.statusMessage = String(event.message);
      continue;
    }

    // Node-level detail rows: duck-typed, bounded, never fabricated.
    if (NODE_EVENT_TYPES.has(eventType)) {
      const nodeSpan = coerceNodeSpan(event);
      if (nodeSpan) upsertNodeSpan(state, nodeSpan);
      continue;
    }

    // Terminal result: retain structured forensics when attached.
    if (TERMINAL_EVENT_TYPES.has(eventType)) {
      const data = event.data != null && typeof event.data === "object" ? event.data : event;
      if (data.gantt_telemetry != null && typeof data.gantt_telemetry === "object") {
        state.gantt = data.gantt_telemetry;
      }
      if (data.waterfall != null && typeof data.waterfall === "object") {
        state.waterfall = data.waterfall;
      }
      if (eventType === "error") {
        state.error = state.error || (event.message != null ? String(event.message) : "run failed");
      }
      continue;
    }

    if (!GOLDEN_STAGE_TYPES.has(eventType)) continue;
    const stage = String(event.stage || "").trim();
    const phase = String(event.phase || "").trim();
    if (!stage || !["started", "completed", "failed"].includes(phase)) continue;
    upsertNodeSpan(state, coerceNodeSpan({ ...event, name: stage, span_id: stage }));

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

export function progressSpanView(golden, nowMs = Date.now()) {
  const labels = {
    golden_restore: "Restoring", "restore method": "Restoring",
    golden_clip_load: "CLIP load", golden_unet_load: "UNET load", golden_vae_load: "VAE load",
    golden_clip_forward: "CLIP forward", golden_sampling: "Sampling", sampling: "Sampling",
    golden_vae_decode: "VAE decode", "VAE decode": "VAE decode",
    golden_output: "Output encode", "output encode": "Output encode",
  };
  const finalSpans = golden?.gantt?.spans;
  const records = Array.isArray(finalSpans) ? finalSpans.map((span) => ({
    key: span.name + ":" + span.start_mono_ns,
    label: span.name, phase: "completed", durationMs: span.duration_ms,
    startMonotonicNs: span.start_mono_ns, endMonotonicNs: span.end_mono_ns,
  })) : (golden?.nodeSpans || []);
  const rows = new Map();
  for (const span of records) {
    const active = span.phase === "started" && !golden?.terminalResult;
    const elapsedMs = active ? Math.max(0, nowMs - span.observedAtMs) : finite(span.durationMs);
    if (elapsedMs == null || elapsedMs <= 100) continue;
    const raw = String(span.label || "");
    const label = labels[raw] || (raw.startsWith("golden_") ? raw.slice(7).replaceAll("_", " ") : raw);
    const row = { ...span, label, active, elapsedMs };
    const previous = rows.get(label);
    if (!previous || (active && !previous.active) || (active === previous.active && elapsedMs > previous.elapsedMs)) {
      rows.set(label, row);
    }
  }
  const visible = [...rows.values()].sort((a, b) => (a.startMonotonicNs || 0) - (b.startMonotonicNs || 0));
  const groups = [];
  for (const span of visible) {
    const start = span.startMonotonicNs || 0;
    const end = span.endMonotonicNs ?? start + span.elapsedMs * 1e6;
    const previous = groups.at(-1);
    if (previous && start < previous.end) {
      previous.spans.push(span);
      previous.end = Math.max(previous.end, end);
    } else groups.push({ start, end, spans: [span] });
  }
  for (const group of groups) {
    group.key = group.spans.map((span) => span.key).join("+");
  }
  return { visible, active: visible.filter((span) => span.active), groups };
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
    statusPhase: state.statusPhase != null ? state.statusPhase : null,
    statusMessage: state.statusMessage != null ? state.statusMessage : null,
    nodeSpans: Array.isArray(state.nodeSpans) ? state.nodeSpans.map((row) => ({ ...row })) : [],
    gantt: state.gantt != null ? state.gantt : null,
    waterfall: state.waterfall != null ? state.waterfall : null,
  };
}
