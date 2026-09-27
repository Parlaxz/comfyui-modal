// Modal Studio — Canonical Run / Event / State Model
//
// THE single source of truth for Studio run lifecycle state. Replaces the
// 7+ conflicting status vocabularies and 6+ progress trackers spread across
// the Studio UI with ONE vocabulary (RUN_STATUSES / CELL_STATUSES) and ONE
// deterministic reducer (createRunStore).
//
// Design rules (implemented exactly):
//   1.  Event dedupe by event.id (first id wins; duplicates dropped entirely).
//   2.  Terminal states come ONLY from explicit run-level terminal events
//       (cellId null + status in TERMINAL_STATUSES). First terminal by
//       (timestamp ?? +Infinity, arrivalIndex) wins; later non-terminal
//       events are recorded as diagnostics but never change status/stage.
//   3.  For non-terminal runs, status/stage = the STAGE_ORDER stage with the
//       highest index among all entered stages / set statuses.
//   4.  Stage spans are per-stage [start, end] intervals derived from event
//       timestamps (min/max). durationMs is only computed when both ends are
//       finite and end >= start. Un-emitted stages are absent, never zeroed.
//   5.  Sampler state changes ONLY from events carrying `sampler`; workflow
//       progress ONLY from events carrying `progress`. Never overwrite each
//       other.
//   6.  Cell events (cellId set) update cells[cellId] only. Per-cell status
//       never changes run.status; run-level terminals only come from events
//       with cellId null.
//   7.  Everything is keyed by runId; separate runs never interact.
//   8.  startTs = earliest event timestamp; endTs = winning terminal's
//       timestamp (or latest event timestamp); created = earliest "created".
//   9.  Terminal status is NEVER inferred from stream close, timeouts, or
//       absence of events — it requires an explicit terminal event.
//  10.  The derived state is a pure function of the applied event set +
//       arrival order; status and stageSpans are arrival-order independent.
//
// Pure ESM, no DOM access, self-contained (no imports from other web modules).
// Consumers: Studio run/experiment UI wiring that currently reads ad-hoc
// status fields. Mirrors the header style of web/studio-run-normalizer.js.

// ── Canonical vocabularies ───────────────────────────────────────────────

/**
 * Canonical run-level statuses in progression order (terminal ones last).
 * @type {ReadonlyArray<string>}
 */
export const RUN_STATUSES = Object.freeze([
  "created",
  "validating",
  "preparing",
  "submitting",
  "queued",
  "scheduling",
  "starting",
  "restoring",
  "executing",
  "sampling",
  "decoding",
  "persisting",
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

/**
 * Statuses that end a run. Only explicit run-level events (cellId null)
 * with one of these statuses may transition a run to terminal.
 * @type {ReadonlyArray<string>}
 */
export const TERMINAL_STATUSES = Object.freeze([
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

/**
 * The 13 non-terminal stages in progression order. Used ONLY as a tie-break
 * for deriving current status from multiple entered stages (status = stage
 * with the highest index among entered). Skipped stages are simply absent.
 * @type {ReadonlyArray<string>}
 */
export const STAGE_ORDER = Object.freeze([
  "created",
  "validating",
  "preparing",
  "submitting",
  "queued",
  "scheduling",
  "starting",
  "restoring",
  "executing",
  "sampling",
  "decoding",
  "persisting",
]);

/**
 * Cell-level status vocabulary. 'skipped' / 'created' (as cell pre-start) are
 * cell-only concepts; a cell status never changes the run status.
 * @type {ReadonlyArray<string>}
 */
export const CELL_STATUSES = Object.freeze([
  "created",
  "queued",
  "executing",
  "sampling",
  "completed",
  "failed",
  "interrupted",
  "skipped",
  "canceled",
]);

// ── Value coercion helpers ───────────────────────────────────────────────

function coerceFiniteNumber(value) {
  if (value == null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function toText(value) {
  return value != null && value !== "" ? value : null;
}

function computePercent(part, whole) {
  if (part == null || whole == null) return null;
  if (whole <= 0) return null;
  return Math.min(100, (part / whole) * 100);
}

/**
 * Normalize a raw sampler payload into the canonical sampler shape.
 * Percent is recomputed from step/max whenever both are finite and max > 0.
 * Unknown extra fields survive for metadata-ish values.
 */
function normalizeSampler(raw, timestamp) {
  if (!raw || typeof raw !== "object") return null;
  const sampler = { ...raw };
  sampler.step = coerceFiniteNumber(raw.step);
  sampler.max = coerceFiniteNumber(raw.max);
  sampler.percent = computePercent(sampler.step, sampler.max);
  if (sampler.percent == null && raw.percent != null) {
    const explicit = coerceFiniteNumber(raw.percent);
    if (explicit != null) sampler.percent = Math.min(100, explicit);
  }
  sampler.updatedAt = timestamp != null ? timestamp : null;
  return sampler;
}

/**
 * Normalize a raw workflow-progress payload into the canonical shape.
 * Percent is recomputed from value/max whenever both are finite and max > 0.
 * Unknown extra fields (e.g. cachedNodes) survive for metadata-ish values.
 */
function normalizeProgress(raw, timestamp) {
  if (!raw || typeof raw !== "object") return null;
  const progress = { ...raw };
  progress.value = coerceFiniteNumber(raw.value);
  progress.max = coerceFiniteNumber(raw.max);
  progress.percent = computePercent(progress.value, progress.max);
  if (progress.percent == null && raw.percent != null) {
    const explicit = coerceFiniteNumber(raw.percent);
    if (explicit != null) progress.percent = Math.min(100, explicit);
  }
  progress.completedNodes = coerceFiniteNumber(raw.completedNodes);
  progress.totalNodes = coerceFiniteNumber(raw.totalNodes);
  progress.currentNodeId = raw.currentNodeId != null ? raw.currentNodeId : null;
  progress.currentNodeName = raw.currentNodeName != null ? raw.currentNodeName : null;
  progress.updatedAt = timestamp != null ? timestamp : null;
  return progress;
}

/**
 * Normalize a raw error payload into the canonical {message, type} shape.
 */
function normalizeError(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    message: raw.message != null ? raw.message : null,
    type: raw.type != null ? raw.type : null,
  };
}

// ── Event normalization ──────────────────────────────────────────────────

/**
 * Normalize one partial event into a canonical RunEvent object.
 *
 * Defaults:
 *   { id: null, runId, experimentId: null, cellId: null, attemptId: null,
 *     generationId: null, mode: "normal", stage: null, status: null,
 *     stageEnd: null, timestamp: null, source: "unknown", parentStage: null,
 *     rawNodeId: null, rawNodeName: null, sampler: null, progress: null,
 *     queuePosition: null, error: null, metadata: {} }
 *
 * - runId is REQUIRED (TypeError when missing/empty).
 * - timestamp accepts a number or numeric string; anything else becomes null.
 * - mode defaults to "normal"; any provided string passes through unchanged.
 * - metadata stores whatever the caller passes (adapters place raw payloads
 *   there); percent is computed from step/max or value/max when max > 0.
 *
 * @param {object} partial - Partial event fields.
 * @returns {object} Canonical RunEvent.
 */
export function createRunEvent(partial) {
  const p = partial && typeof partial === "object" ? partial : {};
  const runId = toText(p.runId);
  if (runId == null) {
    throw new TypeError("createRunEvent: runId is required");
  }
  const timestamp = coerceFiniteNumber(p.timestamp);
  const mode = typeof p.mode === "string" && p.mode !== "" ? p.mode : "normal";

  return {
    id: p.id != null ? p.id : null,
    runId: runId,
    experimentId: p.experimentId != null ? p.experimentId : null,
    cellId: p.cellId != null ? p.cellId : null,
    attemptId: p.attemptId != null ? p.attemptId : null,
    generationId: p.generationId != null ? p.generationId : null,
    mode: mode,
    stage: toText(p.stage),
    status: toText(p.status),
    stageEnd: toText(p.stageEnd),
    timestamp: timestamp,
    source: toText(p.source) || "unknown",
    parentStage: toText(p.parentStage),
    rawNodeId: p.rawNodeId != null ? p.rawNodeId : null,
    rawNodeName: p.rawNodeName != null ? p.rawNodeName : null,
    sampler: normalizeSampler(p.sampler, timestamp),
    progress: normalizeProgress(p.progress, timestamp),
    queuePosition: coerceFiniteNumber(p.queuePosition),
    error: normalizeError(p.error),
    metadata: p.metadata != null && typeof p.metadata === "object" ? p.metadata : {},
  };
}

// ── Derived-state helpers ────────────────────────────────────────────────

const NO_SPAN = Object.freeze({ start: null, end: null, durationMs: null });

/**
 * Return the non-terminal canonical stage a single event contributes, or
 * null when the event carries none (stage wins over status when both are set).
 */
function candidateStage(event) {
  if (event.stage != null && STAGE_ORDER.includes(event.stage)) return event.stage;
  if (event.status != null && STAGE_ORDER.includes(event.status)) return event.status;
  return null;
}

function bestStageIndex(events) {
  let best = -1;
  for (const e of events) {
    const s = candidateStage(e);
    if (s != null) {
      const idx = STAGE_ORDER.indexOf(s);
      if (idx > best) best = idx;
    }
  }
  return best;
}

function buildStageSpans(events) {
  const spans = {};
  for (const e of events) {
    if (e.stage != null && STAGE_ORDER.includes(e.stage) && e.timestamp != null) {
      const span = spans[e.stage] || (spans[e.stage] = { start: null, end: null });
      if (span.start === null || e.timestamp < span.start) span.start = e.timestamp;
      if (span.end === null || e.timestamp > span.end) span.end = e.timestamp;
    }
    // Explicit stageEnd: "stageName" extends that stage's end boundary.
    if (e.stageEnd != null && STAGE_ORDER.includes(e.stageEnd) && e.timestamp != null) {
      const span = spans[e.stageEnd] || (spans[e.stageEnd] = { start: null, end: null });
      if (span.end === null || e.timestamp > span.end) span.end = e.timestamp;
    }
  }
  for (const key of Object.keys(spans)) {
    const span = spans[key];
    if (span.start != null && span.end != null && span.end >= span.start) {
      span.durationMs = span.end - span.start;
    } else {
      span.durationMs = null;
    }
  }
  return spans;
}

function latestNonNullField(events, field) {
  for (let i = events.length - 1; i >= 0; i--) {
    const value = events[i][field];
    if (value != null) return value;
  }
  return null;
}

/**
 * Recompute the full derived run state from the canonical event list.
 * Pure function of (events, arrival order) — no external state.
 */
function deriveRun(events) {
  const first = events[0];
  const last = events[events.length - 1];

  // ── Rule 2: winning terminal ─────────────────────────────────────────
  // Terminal = event with cellId null and a TERMINAL_STATUSES status.
  // Winner sorts first by (timestamp ?? +Infinity, arrivalIndex).
  let winningTerminal = null;
  let winningKey = null;
  const terminalEvents = [];
  for (let i = 0; i < events.length; i++) {
    const e = events[i];
    if (e.cellId == null && TERMINAL_STATUSES.includes(e.status)) {
      terminalEvents.push({ event: e, index: i });
      const key = e.timestamp != null ? e.timestamp : Infinity;
      const arrival = i;
      if (winningKey === null || key < winningKey[0] || (key === winningKey[0] && arrival < winningKey[1])) {
        winningKey = [key, arrival];
        winningTerminal = e;
      }
    }
  }

  const isTerminal = winningTerminal !== null;
  const terminalStatus = isTerminal ? winningTerminal.status : null;

  // ── Rules 3: status + stage ──────────────────────────────────────────
  let status = "unknown";
  if (isTerminal) {
    status = terminalStatus;
  } else {
    const best = bestStageIndex(events);
    if (best >= 0) status = STAGE_ORDER[best];
  }

  // stage = derived status when it is a stage, else the highest entered
  // stage. For terminal runs the stage is frozen at the terminal boundary:
  // events timestamped strictly after the winning terminal cannot advance
  // the stage (still arrival-order independent because the boundary is a
  // time, not an arrival position).
  let stage = null;
  if (isTerminal) {
    const boundary = winningTerminal.timestamp;
    const candidates = [];
    for (const e of events) {
      if (boundary != null && (e.timestamp ?? Infinity) > boundary) continue;
      candidates.push(e);
    }
    const best = bestStageIndex(candidates);
    if (best >= 0) stage = STAGE_ORDER[best];
  } else if (status !== "unknown") {
    stage = status;
  }

  // ── Rule 8: created / startTs / endTs ────────────────────────────────
  let created = null;
  let startTs = null;
  let latestTs = null;
  for (const e of events) {
    if (e.timestamp == null) continue;
    if (startTs === null || e.timestamp < startTs) startTs = e.timestamp;
    if (latestTs === null || e.timestamp > latestTs) latestTs = e.timestamp;
    if ((e.stage === "created" || e.status === "created") && (created === null || e.timestamp < created)) {
      created = e.timestamp;
    }
  }

  let endTs = null;
  if (isTerminal) {
    // Duplicate same-status terminals may extend endTs (max).
    for (const t of terminalEvents) {
      if (t.event.status !== terminalStatus) continue;
      if (t.event.timestamp != null && (endTs === null || t.event.timestamp > endTs)) {
        endTs = t.event.timestamp;
      }
    }
    if (endTs === null) endTs = winningTerminal.timestamp;
  } else {
    endTs = latestTs;
  }

  // ── Rule 4: stage spans ──────────────────────────────────────────────
  const stageSpans = buildStageSpans(events);

  // ── Rules 5: sampler / progress independence ─────────────────────────
  // Sampler is a replace-slot (sampler events always carry step/max).
  // Workflow progress ACCUMULATES across progress-carrying events (shallow
  // non-null merge, later events win per field) so e.g. totalNodes from
  // execution_start survives a subsequent executing event that only carries
  // currentNodeId/currentNodeName (normalization fills absent fields with
  // explicit nulls, which must not clobber earlier evidence). The slot still
  // changes ONLY from events carrying `progress` — never from sampler events.
  const sampler = latestNonNullField(events, "sampler");
  let progress = null;
  for (const e of events) {
    if (e.progress == null) continue;
    if (progress == null) {
      progress = { ...e.progress };
      continue;
    }
    for (const key of Object.keys(e.progress)) {
      if (e.progress[key] != null) progress[key] = e.progress[key];
    }
  }
  const queuePosition = latestNonNullField(events, "queuePosition");

  // ── Rule 7 (error): last explicit run-level error event ──────────────
  let error = null;
  for (const e of events) {
    if (e.cellId != null) continue;
    if (e.error != null) error = e.error;
  }

  // ── Rule 6: cell isolation ───────────────────────────────────────────
  const cells = {};
  for (const e of events) {
    if (e.cellId == null) continue;
    const cell = cells[e.cellId] || (cells[e.cellId] = {
      status: null,
      stage: null,
      sampler: null,
      progress: null,
      startedAt: null,
      endedAt: null,
    });
    if (e.status != null && CELL_STATUSES.includes(e.status)) cell.status = e.status;
    if (e.stage != null) cell.stage = e.stage;
    if (e.sampler != null) cell.sampler = e.sampler;
    if (e.progress != null) cell.progress = e.progress;
    if (e.timestamp != null) {
      if (cell.startedAt === null || e.timestamp < cell.startedAt) cell.startedAt = e.timestamp;
      if (cell.endedAt === null || e.timestamp > cell.endedAt) cell.endedAt = e.timestamp;
    }
  }

  return {
    runId: first.runId,
    experimentId: first.experimentId,
    cellId: first.cellId,
    attemptId: first.attemptId,
    generationId: first.generationId,
    mode: first.mode,
    status: status,
    isTerminal: isTerminal,
    stage: stage,
    created: created,
    startTs: startTs,
    endTs: endTs,
    error: error,
    stageSpans: stageSpans,
    sampler: sampler,
    progress: progress,
    queuePosition: queuePosition,
    cells: cells,
    eventCount: events.length,
    lastEventAt: last.timestamp,
    events: events.slice(),
  };
}

// ── Store ────────────────────────────────────────────────────────────────

/**
 * Create a run store: an append-only event log per runId plus a derived
 * state reducer. The derived state is recomputed deterministically from the
 * event list on every apply (out-of-order safe).
 *
 * @returns {{
 *   applyEvent: function, applyEvents: function, getRun: function,
 *   getRuns: function, hasRun: function, subscribe: function, clear: function
 * }}
 */
export function createRunStore() {
  const runs = new Map(); // runId -> { events: [], seenIds: Set }
  const subscribers = new Set();

  function notify(payload) {
    for (const fn of subscribers) {
      try { fn(payload); } catch (e) { /* subscriber errors are isolated */ }
    }
  }

  return {
    /**
     * Apply a single event (partial or canonical). Deduplicated by event.id.
     * @param {object} event
     */
    applyEvent(event) {
      const canonical = createRunEvent(event);
      let entry = runs.get(canonical.runId);
      if (!entry) {
        entry = { events: [], seenIds: new Set() };
        runs.set(canonical.runId, entry);
      }
      if (canonical.id != null && entry.seenIds.has(canonical.id)) {
        // Rule 1: duplicate dropped entirely — no re-derive, no notify.
        return this;
      }
      if (canonical.id != null) entry.seenIds.add(canonical.id);
      entry.events.push(canonical);
      notify({
        type: "run.updated",
        runId: canonical.runId,
        run: deriveRun(entry.events),
      });
      return this;
    },

    /**
     * Apply a batch of events. Returns this for chaining.
     * @param {Array<object>} events
     */
    applyEvents(events) {
      if (Array.isArray(events)) {
        for (const e of events) this.applyEvent(e);
      }
      return this;
    },

    /**
     * Derived run state for a runId, or undefined when no events were applied.
     * @param {string} runId
     */
    getRun(runId) {
      const entry = runs.get(runId);
      if (!entry || entry.events.length === 0) return undefined;
      return deriveRun(entry.events);
    },

    /**
     * Derived run states for all known runs, in first-seen order.
     * @returns {Array<object>}
     */
    getRuns() {
      const out = [];
      for (const entry of runs.values()) {
        if (entry.events.length > 0) out.push(deriveRun(entry.events));
      }
      return out;
    },

    /**
     * Whether any event has been applied for the runId.
     * @param {string} runId
     * @returns {boolean}
     */
    hasRun(runId) {
      const entry = runs.get(runId);
      return !!entry && entry.events.length > 0;
    },

    /**
     * Subscribe to derived-state updates. Called with
     * { type: "run.updated", runId, run } after every applied event.
     * Returns an unsubscribe function.
     * @param {function} fn
     * @returns {function}
     */
    subscribe(fn) {
      if (typeof fn === "function") subscribers.add(fn);
      return () => { subscribers.delete(fn); };
    },

    /** Drop all runs (subscribers are retained). */
    clear() {
      runs.clear();
    },
  };
}

// ── Selectors ────────────────────────────────────────────────────────────

/**
 * Select a single stage's span from a derived run, or the all-null span when
 * the stage was never emitted.
 * @param {object} run - Derived run state.
 * @param {string} stage - Canonical stage name.
 * @returns {{start: number|null, end: number|null, durationMs: number|null}}
 */
export function getStageSpan(run, stage) {
  if (!run || !run.stageSpans || typeof run.stageSpans !== "object") return NO_SPAN;
  const span = run.stageSpans[stage];
  if (!span) return NO_SPAN;
  return { start: span.start, end: span.end, durationMs: span.durationMs };
}

/**
 * Select the run's sampler progress (from `sampler` events only), or null.
 * @param {object} run - Derived run state.
 * @returns {object|null}
 */
export function getSamplerProgress(run) {
  return run ? run.sampler : null;
}

/**
 * Select the run's workflow progress (from `progress` events only), or null.
 * @param {object} run - Derived run state.
 * @returns {object|null}
 */
export function getWorkflowProgress(run) {
  return run ? run.progress : null;
}
