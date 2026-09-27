// Modal Studio — Playground Run Controller (canonical lifecycle wiring)
//
// Owns the ONE canonical frontend run identity per Run-button execution and
// routes the existing Playground event sources through the canonical run
// model (web/studio-run-model.js) using its adapters
// (web/studio-run-adapters.js):
//
//   - ComfyUI websocket events        → adaptComfyUIWsEvents
//   - experiment.worker.progress      → adaptExperimentWorkerProgress
//   - experiment.event (journal)      → adaptExperimentEvent
//   - snapshot polls                  → adaptSnapshot (+ journal adaptation)
//   - direct run results              → adaptDirectResult
//   - local validation / timeout      → synthesized failed event
//
// The visible Playground lifecycle state (runState) is then a pure
// projection of the canonical derived run state (projectRunToLegacy) —
// legacy statuses/progress fields are OUTPUTS, never independent inputs.
//
// Identity rules:
//   - Every beginRun() allocates a fresh frontend runId (uuid) which owns
//     events, progress, terminal state, and result identity for that click.
//     Sequential runs never share state.
//   - Foreign events cannot hijack the active run:
//       * ws stream locks onto the first execution_start (like the legacy
//         scoped tracker); later execution_start events are ignored while
//         the stream is active; prompt_id-carrying terminal/modal events
//         must match the captured prompt_id.
//       * experiment.worker.progress / experiment.event must carry the
//         controller's experimentId — single runs have none, so ALL
//         experiment events are dropped there.
//   - Once the canonical run is terminal the event source is detached, so
//     stale/duplicate nonterminal events cannot regress the terminal state
//     (the canonical terminal lock also applies inside the store).
//   - Snapshot/journal polling is signature-gated: repeated polls and
//     duplicate terminal journal entries produce no duplicate behavior.
//
// Lightweight run-click timing marks are recorded (no per-frame tracing)
// and exposed via getDiagnostics() for the future Diagnose Run Details
// waterfall. No Modal scheduling timestamps are invented in the browser.
//
// Pure ESM, no DOM access. Unit-testable in plain Node.

import {
  createRunEvent,
  createRunStore,
} from "./studio-run-model.js";
import {
  adaptComfyUIWsEvents,
  adaptExperimentWorkerProgress,
  adaptExperimentEvent,
  adaptSnapshot,
  adaptDirectResult,
} from "./studio-run-adapters.js";

// ── Timing marks (Task 8: run-click instrumentation) ────────────────────

/**
 * Canonical ordering of run-click timing marks. Recorded with wall + perf
 * clocks; later marks with equal or earlier perf timestamps are rejected so
 * the array always reflects call order.
 * @type {ReadonlyArray<string>}
 */
export const RUN_TIMING_MARKS = Object.freeze([
  "run_click",
  "validation_start",
  "validation_end",
  "build_start",
  "build_end",
  "submit_entered",
  "http_invoked",
  "backend_ack",
  "first_running_event",
  "terminal",
]);

/** Legacy runState statuses that are canonical terminals. */
export const LEGACY_TERMINAL_STATUSES = Object.freeze([
  "completed",
  "error",
  "canceled",
  "interrupted",
]);

const RUNNING_STAGES = Object.freeze([
  "executing",
  "sampling",
  "decoding",
  "persisting",
]);

// ── Small helpers ────────────────────────────────────────────────────────

function _uuid() {
  try {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch (e) { /* fall through */ }
  return "run-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

function _now() {
  return Date.now();
}

function _perfNow() {
  try {
    return typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
  } catch (e) {
    return Date.now();
  }
}

// ── Controller ───────────────────────────────────────────────────────────

/**
 * Create a canonical run controller for ONE Playground execution flow.
 *
 * The controller is created once per page lifecycle and beginRun() is called
 * on every Run-button click (each click → a fresh canonical runId).
 *
 * @returns {object} Controller API.
 */
export function createPlaygroundRunController() {
  const store = createRunStore();
  const subscribers = new Set();

  // ── Identity / lifecycle state ──────────────────────────────────────
  let _runId = null;
  let _requestId = null;
  let _backendRunId = null;
  let _experimentId = null;
  let _capturedPromptId = null;
  let _wsLocked = false;
  let _terminal = false;
  let _disposed = false;
  let _firstRunningMarked = false;
  let _lastSnapshotSig = null;

  let _marks = [];
  let _lastExtras = {};

  // Event source handles (for detach)
  let _sourceApi = null;
  const _sourceHandlers = [];

  // ── Timing marks ────────────────────────────────────────────────────
  function mark(name) {
    if (_marks.some((m) => m.name === name)) return;
    const perfMs = _perfNow();
    const wallMs = _now();
    // Reject out-of-order arrivals for the same logical position.
    const last = _marks[_marks.length - 1];
    if (last && perfMs < last.perfMs && wallMs < last.wallMs) return;
    _marks.push({ name, wallMs, perfMs });
  }

  // ── Store application ────────────────────────────────────────────────
  function _applyEvents(events) {
    if (!Array.isArray(events) || events.length === 0 || _disposed) return;
    const before = _runId ? store.getRun(_runId) : undefined;
    let applied = false;
    for (const ev of events) {
      if (!ev) continue;
      store.applyEvent(ev);
      applied = true;
    }
    if (!applied) return;

    const run = store.getRun(_runId);
    if (!_firstRunningMarked && run && RUNNING_STAGES.includes(run.stage)) {
      _firstRunningMarked = true;
      mark("first_running_event");
    }
    if (run && run.isTerminal && !_terminal) {
      _terminal = true;
      mark("terminal");
      _detachEventSource();
    }
    _notify(run, _lastExtras);
    return before;
  }

  function _notify(run, extras) {
    for (const fn of subscribers) {
      try { fn(run, extras); } catch (e) { /* subscriber errors are isolated */ }
    }
  }

  // ── Event source wiring ──────────────────────────────────────────────
  function _detachEventSource() {
    for (const remove of _sourceHandlers) {
      try { remove(); } catch (e) { /* ignore */ }
    }
    _sourceHandlers.length = 0;
    _sourceApi = null;
  }

  function _onWsEvent(detail) {
    if (!detail || typeof detail !== "object" || _disposed || _terminal) return;
    const type = String(detail.type || "");

    if (type === "execution_start") {
      if (detail.prompt_id) _capturedPromptId = detail.prompt_id;
      if (_wsLocked) return; // stream already locked to an earlier execution
      _wsLocked = true;
    }

    // prompt_id mismatch → foreign execution, never touch this run
    if ((type === "execution_success" || type === "execution_error" || type === "modal_status")
        && detail.prompt_id && _capturedPromptId && detail.prompt_id !== _capturedPromptId) {
      return;
    }

    // execution_success/execution_error belong to a locked ws execution; a
    // terminal ws event arriving before any execution_start is a stale
    // event from a previous execution and must not complete this run.
    if ((type === "execution_success" || type === "execution_error") && !_wsLocked) {
      return;
    }

    // executing/progress streams only belong to a locked ws execution
    if (!_wsLocked
        && (type === "executing" || type === "progress"
            || type === "progress_state" || type === "execution_cached")) {
      return;
    }

    const events = adaptComfyUIWsEvents(detail, { runId: _runId, experimentId: _experimentId });
    _applyEvents(events);
  }

  function _onWorkerProgress(detail) {
    if (!detail || typeof detail !== "object" || _disposed || _terminal) return;
    const expId = detail.experiment_id ?? null;
    if (expId == null) return;
    if (!_experimentId || expId !== _experimentId) return; // foreign / single-run
    const events = adaptExperimentWorkerProgress(detail, { runId: _runId });
    _applyEvents(events);
  }

  function _onExperimentEvent(detail) {
    if (!detail || typeof detail !== "object" || _disposed || _terminal) return;
    const expId = detail.experiment_id ?? null;
    if (expId != null && (!_experimentId || expId !== _experimentId)) return;
    // The tracker bus delivers experiment events either as the journal shape
    // {experiment_id, type, payload} or as a FLAT detail
    // {experiment_id, type, ...fields}. Normalize the flat shape so the
    // adapter can extract error/message/cell evidence.
    const msg = (detail.payload && typeof detail.payload === "object")
      ? detail
      : { experiment_id: detail.experiment_id, type: detail.type, payload: detail };
    const events = adaptExperimentEvent(msg, { runId: _runId });
    _applyEvents(events);
  }

  // ── Public API ──────────────────────────────────────────────────────

  return {
    /**
     * Begin a new run: allocate a fresh canonical runId and emit the
     * "created" event. `extras` (e.g. the expected sampler maximum from the
     * steps control) are passed through to subscribers for the pre-telemetry
     * display. Returns { runId }.
     */
    beginRun(extras) {
      _detachEventSource();
      _runId = _uuid();
      _requestId = _uuid();
      _backendRunId = null;
      _experimentId = null;
      _capturedPromptId = null;
      _wsLocked = false;
      _terminal = false;
      _firstRunningMarked = false;
      _lastSnapshotSig = null;
      _lastExtras = {};
      _marks = [];
      mark("run_click");
      if (extras && typeof extras === "object") {
        _lastExtras = { ...extras };
      }
      store.applyEvent(createRunEvent({
        id: _runId + ":created",
        runId: _runId,
        stage: "created",
        status: "created",
        timestamp: _now(),
        source: "playground.click",
        metadata: { timingMarks: _marks.slice() },
      }));
      _notify(store.getRun(_runId), _lastExtras);
      return { runId: _runId };
    },

    /** Record a timing mark (idempotent by name). */
    mark,

    /** Attach backend identity after the submission response. */
    setBackendIds(backendRunId, experimentId) {
      _backendRunId = backendRunId != null ? backendRunId : null;
      _experimentId = experimentId != null ? experimentId : null;
      return this;
    },

    /**
     * Record that the submission was acknowledged (scheduler path).
     * Emits canonical stage "submitting". `extras` (e.g. expected sampler
     * maximum from the steps control) are passed through to subscribers.
     */
    applySubmission(extras) {
      if (!_runId || _disposed) return this;
      if (extras && typeof extras === "object") {
        _lastExtras = { ..._lastExtras, ...extras };
      }
      _applyEvents([createRunEvent({
        id: _runId + ":submitted",
        runId: _runId,
        stage: "submitting",
        status: "submitting",
        timestamp: _now(),
        source: "playground.submit.ack",
      })]);
      return this;
    },

    /**
     * Attach the ComfyUI event bus (api) to this run. Identity-filtered:
     * ws events lock onto the first execution_start; experiment events must
     * match the controller's experimentId. Detached automatically once the
     * run is terminal, or when a new run begins.
     */
    attachEventSource(api) {
      _detachEventSource();
      if (!api || typeof api.addEventListener !== "function" || !_runId || _disposed) return this;
      _sourceApi = api;
      const add = (name, handler) => {
        api.addEventListener(name, handler);
        _sourceHandlers.push(() => {
          try { api.removeEventListener(name, handler); } catch (e) { /* ignore */ }
        });
      };
      add("execution_start", (e) => _onWsEvent(e && e.detail));
      add("executing", (e) => _onWsEvent(e && e.detail));
      add("progress", (e) => _onWsEvent(e && e.detail));
      add("progress_state", (e) => _onWsEvent(e && e.detail));
      add("execution_cached", (e) => _onWsEvent(e && e.detail));
      add("execution_success", (e) => _onWsEvent(e && e.detail));
      add("execution_error", (e) => _onWsEvent(e && e.detail));
      add("modal_status", (e) => _onWsEvent(e && e.detail));
      add("experiment.worker.progress", (e) => _onWorkerProgress(e && e.detail));
      add("experiment.event", (e) => _onExperimentEvent(e && e.detail));
      return this;
    },

    /** Detach the event source (e.g. on dispose / navigation). */
    detachEventSource() {
      _detachEventSource();
      return this;
    },

    /**
     * Apply one snapshot poll (getStudioRunStatus response). The snapshot
     * status and journal events are adapted; signature gating drops repeated
     * polls and duplicate terminal journal entries. `extras` are passed
     * through to subscribers (grid outputs, cell evidence, timing metadata).
     */
    applySnapshot(data, extras) {
      if (!data || typeof data !== "object" || !_runId || _disposed) return this;
      const snapshot = (data.snapshot && typeof data.snapshot === "object") ? data.snapshot : {};
      const statusSource = snapshot.overall_status != null
        ? snapshot.overall_status
        : (snapshot.status != null ? snapshot.status : data.state);

      const events = [];
      if (statusSource != null) {
        const adapted = adaptSnapshot(
          { ...snapshot, overall_status: statusSource },
          { runId: _runId, experimentId: _experimentId },
        );
        for (const ev of adapted) events.push(ev);
      }
      const journal = Array.isArray(data.events) ? data.events : [];
      for (const ev of journal) {
        const adapted = adaptExperimentEvent(ev, { runId: _runId });
        for (const cev of adapted) events.push(cev);
      }
      if (events.length === 0) return this;

      // Signature gate: identical adapted event content → no-op poll.
      const sig = JSON.stringify(events.map((e) => [
        e.stage, e.status, e.cellId,
        e.sampler && e.sampler.step, e.sampler && e.sampler.max,
        e.progress && e.progress.value, e.progress && e.progress.max,
        e.error && e.error.message,
      ]));
      if (sig === _lastSnapshotSig) return this;
      _lastSnapshotSig = sig;

      _lastExtras = { ..._lastExtras, ...(extras || {}) };
      _applyEvents(events);
      return this;
    },

    /**
     * Apply a direct-run result (already completed on the backend).
     * `extras` carry result association data (timings, output, history ids).
     */
    applyDirectResult(result, extras) {
      if (!result || !_runId || _disposed) return this;
      const events = adaptDirectResult(result, { runId: _runId });
      if (events.length === 0) return this;
      _lastExtras = { ..._lastExtras, ...(extras || {}) };
      _applyEvents(events);
      return this;
    },

    /** Apply a local (non-backend) failure — validation or timeout. */
    applyLocalError(message) {
      if (!_runId || _disposed) return this;
      _applyEvents([createRunEvent({
        id: _runId + ":local-error",
        runId: _runId,
        stage: "failed",
        status: "failed",
        timestamp: _now(),
        source: "playground.local",
        error: {
          message: message != null ? String(message) : null,
          type: "playground.local",
        },
      })]);
      return this;
    },

    /** Canonical derived state of the current run, or undefined. */
    getRun() {
      return _runId ? store.getRun(_runId) : undefined;
    },

    /** Extras passed by the most recent applied source. */
    getExtras() {
      return { ..._lastExtras };
    },

    /** True once the current run reached a canonical terminal state. */
    isTerminal() {
      return _terminal;
    },

    /** Canonical runId of the current run (undefined before beginRun). */
    getRunId() {
      return _runId;
    },

    /**
     * Structured diagnostic data for the future Diagnose Run Details
     * waterfall: identity, canonical status, and ordered timing marks.
     */
    getDiagnostics() {
      const run = _runId ? store.getRun(_runId) : undefined;
      const baseWall = _marks.length > 0 ? _marks[0].wallMs : null;
      return {
        runId: _runId,
        requestId: _requestId,
        backendRunId: _backendRunId,
        experimentId: _experimentId,
        status: run ? run.status : null,
        isTerminal: run ? run.isTerminal : false,
        eventCount: run ? run.eventCount : 0,
        stage: run ? run.stage : null,
        sampler: run ? run.sampler : null,
        progress: run ? run.progress : null,
        marks: _marks.map((m) => ({
          name: m.name,
          wallMs: m.wallMs,
          perfMs: m.perfMs,
          deltaMs: baseWall != null ? m.wallMs - baseWall : null,
        })),
        cells: run && run.cells ? run.cells : null,
      };
    },

    /** Subscribe to canonical updates: fn(run, extras). Returns unsubscribe. */
    subscribe(fn) {
      if (typeof fn === "function") subscribers.add(fn);
      return () => { subscribers.delete(fn); };
    },

    /** Dispose the controller: detach source, drop subscribers. */
    dispose() {
      _disposed = true;
      _detachEventSource();
      subscribers.clear();
    },
  };
}

// ── Legacy projection ────────────────────────────────────────────────────

/**
 * Project canonical derived run state into the legacy Playground runState
 * shape. The legacy fields are OUTPUTS of the canonical state — nothing in
 * the render pipeline may mutate lifecycle status independently.
 *
 * Progress slots are written explicitly (null when absent) so a new run can
 * never inherit stale sampler/workflow fields from a previous run.
 *
 * @param {object} run - Canonical derived run state (from createRunStore).
 * @param {object} extras - Result-association / grid data to preserve
 *   (_snapshot, _events, _cellOutputs, primaryOutput, completedCells,
 *   totalCells, hasHistory, _directTiming, _directMeta, runHistoryId, ...).
 * @returns {object} Legacy runState-shaped object.
 */
export function projectRunToLegacy(run, extras = {}) {
  const out = { ...(extras || {}) };
  if (!run) return out;

  out.runId = run.runId != null ? run.runId : out.runId;
  out.experimentId = run.experimentId != null ? run.experimentId : out.experimentId;

  // ── Status mapping (single authority: canonical terminal / stage) ────
  const s = run.status;
  if (s === "completed") out.status = "completed";
  else if (s === "failed") out.status = "error";
  else if (s === "canceled") out.status = "canceled";
  else if (s === "interrupted") out.status = "interrupted";
  else if (s === "queued") out.status = "queued";
  else if (s === "scheduling" || s === "starting" || s === "restoring") out.status = "waiting";
  else if (s === "executing" || s === "sampling" || s === "decoding" || s === "persisting") {
    out.status = "in_progress";
  } else {
    // created / validating / preparing / submitting / unknown
    out.status = s === "submitting" ? "submitted" : "running";
  }

  // ── Sampler slot (sampler events only) ───────────────────────────────
  if (run.sampler) {
    out.samplerStep = run.sampler.step != null ? run.sampler.step : null;
    out.samplerMaximum = run.sampler.max != null ? run.sampler.max : null;
    out.samplerPercent = run.sampler.percent != null ? run.sampler.percent : null;
  } else {
    // No sampler telemetry yet: null the step, but preserve a UI hint for
    // the expected maximum (e.g. steps control) when the caller supplied one.
    out.samplerStep = null;
    out.samplerPercent = null;
    if (out.samplerMaximum == null) out.samplerMaximum = null;
  }

  // ── Workflow progress slot (progress events only) ────────────────────
  if (run.progress) {
    out.completedNodes = run.progress.completedNodes != null ? run.progress.completedNodes : null;
    out.totalNodes = run.progress.totalNodes != null ? run.progress.totalNodes : (run.progress.max != null ? run.progress.max : null);
    out.overallPercent = run.progress.percent != null ? run.progress.percent : null;
    out.currentNodeLabel = run.progress.currentNodeName != null
      ? run.progress.currentNodeName
      : (run.progress.currentNodeId != null ? run.progress.currentNodeId : null);
  } else {
    out.completedNodes = null;
    out.totalNodes = null;
    out.overallPercent = null;
    out.currentNodeLabel = null;
  }

  out.queuePosition = run.queuePosition != null ? run.queuePosition : null;
  out.stage = run.stage != null ? run.stage : out.stage;
  if (run.error && run.error.message != null) {
    out.error = run.error.message;
    out.message = run.error.message;
  }

  // Canonical snapshot for diagnostics / tests.
  out._canonical = {
    status: run.status,
    isTerminal: run.isTerminal,
    eventCount: run.eventCount,
    startTs: run.startTs,
    endTs: run.endTs,
    cells: run.cells,
  };
  return out;
}

// ── Per-Experiment controller (D5, additive) ─────────────────────────────
//
// One controller owns ONE experiment id and the FIXED ordered cell matrix
// for it.  Cell records are keyed by the stable cell_id and ordered by
// backend position/order (never by completion).  Each active attempt gets
// its own canonical run store (createRunStore) keyed by attempt_id/run_id;
// events are routed per attempt through the shared adapters.  Status
// reconciliation is durable across detach/reattach: the controller keeps the
// last-known backend status/counts/cells and never forgets terminal cells.
//
// Terminal rules:
//   - terminal first-wins per ACTIVE attempt: once a cell's active attempt
//     reaches completed/failed/canceled/interrupted, a later reconcile for
//     the SAME attempt (running or another terminal) cannot change it;
//   - a deliberate Retry/Resume carries a NEW attempt_id/run_id and is
//     allowed to replace the active cell status (same cell position);
//   - stale attempt events (a different attempt_id for the same cell) are
//     dropped before they reach any store;
//   - queued/completed/failed/interrupted/canceled cells are preserved;
//     only resume/retry (explicit user action) opens a NEW attempt.
//
// Ordering: the first reconcile orders new cells by backend position/index;
// later polls never reorder existing cells (omitted cells are kept).
//
// Duplicate action guards: cancel/resume are single-flight; retryCell is
// single-flight per cell.  dispose() never cancels.

/** Canonical cell statuses of the modern experiment surface. */
export const EXPERIMENT_CELL_STATUSES = Object.freeze([
  "queued",
  "running",
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

/** Cell statuses that are terminal (never regress). */
export const EXPERIMENT_TERMINAL_STATUSES = Object.freeze([
  "completed",
  "failed",
  "canceled",
  "interrupted",
]);

const EXPERIMENT_STATUS_ALIASES = {
  completed: "completed", complete: "completed", success: "completed",
  succeeded: "completed", done: "completed", ok: "completed",
  failed: "failed", failure: "failed", error: "failed", errored: "failed",
  canceled: "canceled", cancelled: "canceled", cancel: "canceled", stopped: "canceled",
  interrupted: "interrupted", aborted: "interrupted", abort: "interrupted",
  running: "running", in_progress: "running", active: "running",
  processing: "running", executing: "running",
  queued: "queued", pending: "queued", not_started: "queued",
  created: "queued", scheduled: "queued",
  completed_with_failures: "completed_with_failures", partial: "completed_with_failures",
};

function _canonCellStatus(value) {
  if (value == null) return "queued";
  const key = String(value).toLowerCase().replace(/\s+/g, "_");
  return Object.prototype.hasOwnProperty.call(EXPERIMENT_STATUS_ALIASES, key)
    ? EXPERIMENT_STATUS_ALIASES[key]
    : key;
}

function _firstValue() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v != null && v !== "") return v;
  }
  return null;
}

function _firstInt() {
  for (let i = 0; i < arguments.length; i++) {
    const v = arguments[i];
    if (v != null && v !== "" && !Number.isNaN(Number(v))) return Number(v);
  }
  return null;
}

function _isTerminalStatus(status) {
  return EXPERIMENT_TERMINAL_STATUSES.indexOf(status) !== -1;
}

/**
 * Normalize one raw cell (snake_case or camelCase) into the fixed record.
 * Position/order fields, axis labels/values, output urls, attempt history
 * and workflow/preset ids+names are carried through for the UI grid.
 * @param {object} raw
 * @param {number} index
 * @returns {object} { cellId, index, position, status, attemptId, runId,
 *   error, durationMs, thumbUrl, previewUrl, originalUrl, attempts,
 *   axisLabels, axisValues, workflowId, workflowName, workflowVersionId,
 *   presetId, presetName }
 */
export function normalizeExperimentV2Cell(raw, index) {
  const r = raw && typeof raw === "object" ? raw : {};
  const statusSrc = _firstValue(r.status, r.state, r.cell_status);
  const attempts = Array.isArray(r.attempts) ? r.attempts.map((a) => ({
    attemptId: _firstValue(a.attempt_id, a.attemptId, a.run_id, a.runId),
    runId: _firstValue(a.run_id, a.runId, a.attempt_id, a.attemptId),
    status: _canonCellStatus(_firstValue(a.status, a.state)),
    error: a.error != null ? a.error : null,
    durationMs: _firstInt(a.duration_ms, a.durationMs),
    startedAt: _firstValue(a.started_at, a.startedAt),
  })) : [];
  return {
    cellId: _firstValue(r.cell_id, r.cellId, r.cell_key, r.cellKey, r.key),
    index: _firstInt(r.index, index != null ? index : 0),
    position: _firstInt(r.position, r.index, index != null ? index : 0),
    status: _canonCellStatus(statusSrc),
    attemptId: _firstValue(r.attempt_id, r.attemptId, r.run_id, r.runId),
    runId: _firstValue(r.run_id, r.runId, r.attempt_id, r.attemptId),
    error: r.error != null ? r.error : null,
    durationMs: _firstInt(r.duration_ms, r.durationMs),
    thumbUrl: _firstValue(r.thumb_url, r.thumbUrl),
    previewUrl: _firstValue(r.preview_url, r.previewUrl),
    originalUrl: _firstValue(r.original_url, r.originalUrl),
    attempts: attempts,
    axisLabels: r.axis_labels != null ? r.axis_labels
      : (r.axisLabels != null ? r.axisLabels : null),
    axisValues: r.axis_values != null ? r.axis_values
      : (r.axisValues != null ? r.axisValues : null),
    workflowId: _firstValue(r.workflow_id, r.workflowId),
    workflowName: _firstValue(r.workflow_name, r.workflowName, r.workflow),
    workflowVersionId: _firstValue(r.workflow_version_id, r.workflowVersionId, r.workflow_version),
    presetId: _firstValue(r.preset_id, r.presetId),
    presetName: _firstValue(r.preset_name, r.presetName, r.preset),
  };
}

/**
 * Normalize a raw modern experiment status response (snake_case or
 * camelCase) into the canonical shape.  Backend counts are preferred when
 * supplied; the cell fold is the fallback (used by tests).
 * @param {object} raw
 * @returns {object} { experimentId, status, total, counts, cells }
 */
export function normalizeExperimentV2Status(raw) {
  const r = raw && typeof raw === "object" ? raw : {};
  const cells = (Array.isArray(r.cells) ? r.cells : [])
    .map((c, i) => normalizeExperimentV2Cell(c, i));
  // The modern FLAT status payload carries the experiment lifecycle status in
  // `aggregate_status`; the top-level `status` is only the transport/envelope
  // status (e.g. "ok") and must never be treated as lifecycle evidence (a
  // naive read of `status` first aliased "ok" → "completed", completing a
  // running experiment).  When `aggregate_status` is present it is
  // authoritative; item-wrapped / legacy payloads (no aggregate_status) keep
  // the inner lifecycle status source (status/state/experiment_status).
  const aggregate = _firstValue(r.aggregate_status, r.aggregateStatus);
  const statusSrc = aggregate != null
    ? aggregate
    : _firstValue(r.status, r.state, r.experiment_status);
  const counts = _resolveCountsFromRaw(r, cells);
  return {
    experimentId: _firstValue(r.experiment_id, r.experimentId, r.id),
    status: statusSrc != null ? _canonCellStatus(statusSrc) : null,
    total: _firstInt(r.total, r.cell_count, r.cellCount, cells.length),
    counts: counts,
    cells: cells,
  };
}

function _resolveCountsFromRaw(r, cells) {
  const c = r.counts && typeof r.counts === "object" ? r.counts : {};
  const hasBackendCounts = c.queued != null || c.running != null
    || c.completed != null || c.complete != null || c.failed != null
    || c.canceled != null || c.cancelled != null || c.interrupted != null;
  if (!hasBackendCounts) return countExperimentCells(cells);
  return {
    queued: _firstInt(c.queued, c.pending, 0),
    running: _firstInt(c.running, 0),
    completed: _firstInt(c.completed, c.complete, c.success, 0),
    failed: _firstInt(c.failed, c.failures, 0),
    canceled: _firstInt(c.canceled, c.cancelled, 0),
    interrupted: _firstInt(c.interrupted, 0),
  };
}

/**
 * Fold an ordered cell list into status counts.
 * @param {Array<object>} cells
 * @returns {{queued:number, running:number, completed:number, failed:number, canceled:number, interrupted:number}}
 */
export function countExperimentCells(cells) {
  const counts = { queued: 0, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 };
  (Array.isArray(cells) ? cells : []).forEach((c) => {
    const s = c && c.status != null ? c.status : "queued";
    if (counts[s] != null) counts[s]++;
  });
  return counts;
}

/**
 * Progress text from counts: "18/40 complete · 6 running · 16 queued".
 * Complete is always shown; the other tokens only when non-zero.
 * @param {object} counts
 * @param {number} [total]
 * @returns {string}
 */
export function formatExperimentProgress(counts, total) {
  const c = counts && typeof counts === "object" ? counts : {};
  const done = _firstInt(c.completed, 0);
  const t = _firstInt(total, done + _firstInt(c.running, 0) + _firstInt(c.queued, 0)
    + _firstInt(c.failed, 0) + _firstInt(c.canceled, 0) + _firstInt(c.interrupted, 0));
  const parts = [`${done}/${t} complete`];
  const tokens = [
    ["running", "running"],
    ["queued", "queued"],
    ["failed", "failures"],
    ["canceled", "canceled"],
    ["interrupted", "interrupted"],
  ];
  for (const [key, label] of tokens) {
    const n = _firstInt(c[key], 0);
    if (n > 0) parts.push(`${n} ${label}`);
  }
  return parts.join(" \u00b7 ");
}

/**
 * Create a per-Experiment controller factory.  Additive — the single-run
 * createPlaygroundRunController semantics are untouched.
 *
 * @param {object} [opts]
 * @param {string} [opts.experimentId]
 * @param {string} [opts.apiBase="/comfymodal"]
 * @param {object} [opts.actions] - Optional action overrides for cancel /
 *   resume / retryCell, each (id) => Promise.  Defaults post to the frozen
 *   modern routes under apiBase.
 * @returns {object} Controller API: attach, refresh, reconcile, cancel,
 *   resume, retryCell, subscribe, getState, getCells, getExperimentId,
 *   detachEventSource, dispose.
 */
export function createExperimentRunController(opts) {
  const o = opts && typeof opts === "object" ? opts : {};
  const experimentId = o.experimentId != null ? String(o.experimentId) : null;
  const apiBase = o.apiBase || "/comfymodal";
  const actions = o.actions && typeof o.actions === "object" ? o.actions : {};

  let _disposed = false;
  let _experimentId = experimentId;
  let _status = "queued";
  let _total = 0;
  let _counts = { queued: 0, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 };
  let _cells = [];
  const _cellsById = new Map();
  const _attemptStores = new Map(); // key `${cellId}::${attemptKey}` -> { runId, attemptId, store }
  const _subscribers = new Set();
  const _inflight = { cancel: false, resume: false, retry: new Set() };
  // Deliberate retry/resume intent: cells the user explicitly asked to re-run
  // with a NEW attempt.  A terminal cell only lets a NEW attempt identity
  // replace its status when intent is armed (a bare poll cannot regress it).
  const _pendingRetry = new Set();
  const _pendingResume = new Set();
  let _sourceApi = null;
  const _sourceHandlers = [];

  // ── Small fetch helpers (default actions) ────────────────────────────
  function _post(path) {
    return fetch(apiBase + path, { method: "POST" }).then((res) => {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json().catch(() => ({}));
    });
  }
  function _cancelAction(id) {
    return _post("/history-v2/experiments/" + encodeURIComponent(id || "") + "/cancel");
  }
  function _resumeAction(id) {
    return _post("/history-v2/experiments/" + encodeURIComponent(id || "") + "/resume");
  }
  function _retryCellAction(id, cellId) {
    return _post("/history-v2/experiments/" + encodeURIComponent(id || "")
      + "/cells/" + encodeURIComponent(cellId || "") + "/retry");
  }

  // ── Cell / attempt bookkeeping ───────────────────────────────────────
  function _cellById(id) {
    return id != null ? _cellsById.get(String(id)) : undefined;
  }

  function _attemptKey(cell) {
    return cell.runId || cell.attemptId || null;
  }

  function _ensureStore(cell) {
    const key = _attemptKey(cell);
    if (!key) return null;
    const mapKey = cell.cellId + "::" + key;
    let entry = _attemptStores.get(mapKey);
    if (!entry) {
      const store = createRunStore();
      entry = { runId: key, attemptId: cell.attemptId || key, cellId: cell.cellId, store };
      _attemptStores.set(mapKey, entry);
    }
    return entry;
  }

  function _syncCellFromStore(cell, entry) {
    const run = entry.store.getRun(entry.runId);
    if (!run) return;
    if (run.sampler) cell.sampler = { ...run.sampler };
    if (run.progress) cell.progress = { ...run.progress };
    // Terminal first-wins: a store terminal sets the cell status once.
    // Cell-level terminals (cell.completed/failed/...) live on
    // run.cells[cellId].status; run-level terminals on run.status.
    const cellRun = run.cells && run.cells[entry.cellId];
    const cellTerminal = cellRun && _isTerminalStatus(cellRun.status) ? cellRun.status : null;
    const runTerminal = run.isTerminal && _isTerminalStatus(run.status) ? run.status : null;
    const terminal = cellTerminal || runTerminal;
    if (terminal && !_isTerminalStatus(cell.status)) {
      cell.status = terminal;
    }
  }

  function _resolveCell(detail) {
    const p = detail && detail.payload && typeof detail.payload === "object"
      ? detail.payload
      : detail;
    const cellKey = _firstValue(p.cell_id, p.cellId, p.cell_key, p.cellKey);
    if (cellKey != null) return _cellById(cellKey);
    const promptId = detail && detail.prompt_id != null ? String(detail.prompt_id) : null;
    if (promptId) {
      for (const cell of _cells) {
        if (cell.runId === promptId) return cell;
      }
    }
    return undefined;
  }

  function _routeToCell(detail, adaptFn) {
    if (!detail || typeof detail !== "object" || _disposed) return;
    const expId = _firstValue(detail.experiment_id, detail.experimentId);
    if (expId != null && _experimentId && String(expId) !== String(_experimentId)) return;
    const cell = _resolveCell(detail);
    if (!cell) return;
    const entry = _ensureStore(cell);
    if (!entry) return;
    const payload = detail.payload && typeof detail.payload === "object" ? detail.payload : detail;
    const eventAttempt = _firstValue(payload.attempt_id, payload.attemptId);
    if (eventAttempt != null && eventAttempt !== entry.attemptId) return; // stale attempt
    const events = adaptFn(detail, {
      runId: entry.runId,
      experimentId: _experimentId,
      cellId: cell.cellId,
      attemptId: entry.attemptId,
    });
    if (events && events.length) {
      entry.store.applyEvents(events);
      _syncCellFromStore(cell, entry);
      _notify();
    }
  }

  function _mapExperimentEventStatus(type, payload) {
    if (type === "experiment.completed") return "completed";
    if (type === "experiment.stopped" || type === "experiment.cancelled") return "canceled";
    if (type === "experiment.error" || type === "experiment.failed_fatal") return "failed";
    if (type === "experiment.status" && payload.status != null) return _canonCellStatus(payload.status);
    if (type === "experiment.recovered") return "running";
    return null;
  }

  // ── Event source handlers ────────────────────────────────────────────
  function _onWsEvent(detail) {
    _routeToCell(detail, adaptComfyUIWsEvents);
  }

  function _onWorkerProgress(detail) {
    _routeToCell(detail, adaptExperimentWorkerProgress);
  }

  function _onExperimentEvent(detail) {
    if (!detail || typeof detail !== "object" || _disposed) return;
    const expId = _firstValue(detail.experiment_id, detail.experimentId);
    if (expId != null && _experimentId && String(expId) !== String(_experimentId)) return;
    const type = String(detail.type || "");
    const payload = detail.payload && typeof detail.payload === "object" ? detail.payload : {};
    const cellKey = _firstValue(payload.cell_key, payload.cellKey, payload.cell_id, payload.cellId);
    if (cellKey == null && type.indexOf("cell.") !== 0 && type.indexOf("checkpoint.") !== 0) {
      const mapped = _mapExperimentEventStatus(type, payload);
      if (mapped) _status = mapped;
      _notify();
      return;
    }
    const cellType = payload.type ? String(payload.type) : type;
    _routeToCell({ experiment_id: expId, type: cellType, payload: payload }, adaptExperimentEvent);
  }

  // ── Notify / subscribe ───────────────────────────────────────────────
  function _notify() {
    const state = getState();
    for (const fn of _subscribers) {
      try { fn(state); } catch (e) { /* subscriber errors are isolated */ }
    }
  }

  // ── Aggregate status derivation (fallback when backend omits status) ──
  function _deriveStatus(cells) {
    const counts = countExperimentCells(cells);
    if (counts.queued > 0 || counts.running > 0) return "running";
    if (counts.interrupted > 0 && counts.failed === 0) return "interrupted";
    if (counts.failed > 0 && counts.interrupted === 0 && counts.canceled === 0) return "completed_with_failures";
    if (counts.canceled > 0 && counts.failed === 0 && counts.interrupted === 0) return "canceled";
    if (counts.completed > 0 && counts.failed === 0 && counts.canceled === 0 && counts.interrupted === 0) return "completed";
    return "running";
  }

  // ── Reconciliation ───────────────────────────────────────────────────
  // Attempt identity: the run_id is the canonical per-attempt key (falls
  // back to attempt_id when run_id is absent).  Terminal first-wins applies
  // to the SAME active attempt; a deliberate retry/resume carries a NEW
  // attempt identity and is allowed to replace the cell status.
  function _activeAttemptKey(cell) {
    return cell.runId || cell.attemptId || null;
  }

  function reconcile(data) {
    if (_disposed) return this;
    const raw = data && typeof data === "object" ? data : {};
    const id = _firstValue(raw.experiment_id, raw.experimentId, raw.id);
    if (id != null) _experimentId = String(id);
    const norm = normalizeExperimentV2Status(raw);

    // First build: order new cells by backend position/index.  Later polls
    // never reorder existing cells — they keep their slots.
    const incoming = _cells.length === 0
      ? norm.cells.slice().sort((a, b) => {
          const pa = a.position != null ? a.position : a.index;
          const pb = b.position != null ? b.position : b.index;
          return pa - pb;
        })
      : norm.cells;

    const next = _cells.slice(); // fixed order: existing cells keep their slots
    const byId = new Map(next.map((c) => [c.cellId, c]));
    const seen = new Set();
    for (let i = 0; i < incoming.length; i++) {
      const nc = incoming[i];
      const cellId = nc.cellId || "cell_" + i;
      seen.add(cellId);
      let cell = byId.get(cellId);
      if (!cell) {
        cell = { ...nc, cellId, sampler: null, progress: null };
        byId.set(cellId, cell);
        _cellsById.set(cellId, cell);
        next.push(cell);
      } else {
        const prevKey = _activeAttemptKey(cell);
        const nextKey = _activeAttemptKey(nc);
        // A NEW attempt identity only replaces the active cell status when the
        // user deliberately retried/resumed that cell.  A bare poll reporting
        // a different attempt_id is stale evidence and cannot regress a
        // terminal cell (terminal first-wins for the active attempt).
        const deliberate = _pendingRetry.has(cellId) || _pendingResume.has(cellId);
        const newAttemptIdentity = nextKey != null && nextKey !== prevKey;
        if (_isTerminalStatus(cell.status)) {
          if (deliberate && newAttemptIdentity) {
            _pendingRetry.delete(cellId);
            _pendingResume.delete(cellId);
            cell.status = nc.status;
            cell.attemptId = nc.attemptId;
            cell.runId = nc.runId;
            cell.sampler = null;
            cell.progress = null;
          }
          // Otherwise the terminal status (and active attempt) is kept.
        } else {
          // Non-terminal cells follow the backend (new attempt, status, etc.).
          cell.status = nc.status;
          if (nc.attemptId) cell.attemptId = nc.attemptId;
          if (nc.runId) cell.runId = nc.runId;
        }
        if (nc.index != null) cell.index = nc.index;
        if (nc.position != null) cell.position = nc.position;
        if (nc.error != null) cell.error = nc.error;
        if (nc.durationMs != null) cell.durationMs = nc.durationMs;
        if (nc.thumbUrl) cell.thumbUrl = nc.thumbUrl;
        if (nc.previewUrl) cell.previewUrl = nc.previewUrl;
        if (nc.originalUrl) cell.originalUrl = nc.originalUrl;
        if (nc.attempts.length > 0) cell.attempts = nc.attempts;
        if (nc.axisLabels != null) cell.axisLabels = nc.axisLabels;
        if (nc.axisValues != null) cell.axisValues = nc.axisValues;
        if (nc.workflowId) cell.workflowId = nc.workflowId;
        if (nc.workflowName) cell.workflowName = nc.workflowName;
        if (nc.workflowVersionId) cell.workflowVersionId = nc.workflowVersionId;
        if (nc.presetId) cell.presetId = nc.presetId;
        if (nc.presetName) cell.presetName = nc.presetName;
      }
      _ensureStore(cell);
    }
    // Defensive: preserve existing cells omitted from the newest payload.
    for (const existing of _cells) {
      if (!seen.has(existing.cellId)) _ensureStore(existing);
    }
    _cells = next;

    if (norm.status != null) {
      _status = norm.status;
    } else {
      _status = _deriveStatus(norm.cells);
    }
    _total = norm.total != null ? norm.total : _cells.length;
    _counts = { ...norm.counts };
    _notify();
    return this;
  }

  // ── Actions (single-flight guards) ───────────────────────────────────
  function cancel() {
    if (_disposed || _inflight.cancel) return Promise.resolve({ accepted: false, guarded: true });
    _inflight.cancel = true;
    const fn = typeof actions.cancel === "function" ? actions.cancel : _cancelAction;
    return Promise.resolve(fn(_experimentId))
      .then((res) => ({ accepted: true, ...(res && typeof res === "object" ? res : {}) }))
      .finally(() => { _inflight.cancel = false; });
  }

  function resume() {
    if (_disposed || _inflight.resume) return Promise.resolve({ accepted: false, guarded: true });
    _inflight.resume = true;
    // Arm resume intent for interrupted + never-started cells so a NEW
    // attempt identity arriving in a later poll can replace their status.
    _cells.forEach((c) => {
      if (c.status === "interrupted" || c.status === "queued") {
        _pendingResume.add(c.cellId);
      }
    });
    const fn = typeof actions.resume === "function" ? actions.resume : _resumeAction;
    return Promise.resolve(fn(_experimentId))
      .then((res) => ({ accepted: true, ...(res && typeof res === "object" ? res : {}) }))
      .finally(() => { _inflight.resume = false; });
  }

  function retryCell(cellId) {
    const id = cellId != null ? String(cellId) : "";
    if (_disposed || !id || _inflight.retry.has(id)) {
      return Promise.resolve({ accepted: false, guarded: true });
    }
    const cell = _cellById(id);
    if (!cell || cell.status !== "failed") {
      return Promise.resolve({ accepted: false, message: "Cell is not failed" });
    }
    // Arm retry intent: the next reconcile reporting a NEW attempt identity
    // for this cell is allowed to replace the failed status.
    _pendingRetry.add(id);
    _inflight.retry.add(id);
    const fn = typeof actions.retryCell === "function" ? actions.retryCell : _retryCellAction;
    return Promise.resolve(fn(_experimentId, id))
      .then((res) => ({ accepted: true, ...(res && typeof res === "object" ? res : {}) }))
      .finally(() => { _inflight.retry.delete(id); });
  }

  // ── Event source wiring ──────────────────────────────────────────────
  function detachEventSource() {
    for (const remove of _sourceHandlers) {
      try { remove(); } catch (e) { /* ignore */ }
    }
    _sourceHandlers.length = 0;
    _sourceApi = null;
    return this;
  }

  function attach(eventSource) {
    detachEventSource();
    if (!eventSource || typeof eventSource.addEventListener !== "function" || _disposed) return this;
    const src = eventSource;
    _sourceApi = src;
    const add = (name, handler) => {
      const wrapped = (e) => {
        if (_disposed || _sourceApi !== src) return;
        handler(e && e.detail);
      };
      src.addEventListener(name, wrapped);
      _sourceHandlers.push(() => {
        try { src.removeEventListener(name, wrapped); } catch (e) { /* ignore */ }
      });
    };
    add("execution_start", _onWsEvent);
    add("executing", _onWsEvent);
    add("progress", _onWsEvent);
    add("progress_state", _onWsEvent);
    add("execution_cached", _onWsEvent);
    add("execution_success", _onWsEvent);
    add("execution_error", _onWsEvent);
    add("modal_status", _onWsEvent);
    add("experiment.worker.progress", _onWorkerProgress);
    add("experiment.event", _onExperimentEvent);
    return this;
  }

  // ── Public API ───────────────────────────────────────────────────────
  function getCells() {
    return _cells.map((c) => ({ ...c }));
  }

  function getState() {
    return {
      experimentId: _experimentId,
      status: _status,
      total: _total,
      counts: { ..._counts },
      progressText: formatExperimentProgress(_counts, _total),
      cells: getCells(),
    };
  }

  function subscribe(fn) {
    if (typeof fn === "function") _subscribers.add(fn);
    return () => { _subscribers.delete(fn); };
  }

  function dispose() {
    if (_disposed) return;
    _disposed = true;
    detachEventSource();
    _subscribers.clear();
  }

  return {
    attach,
    refresh: reconcile,
    reconcile,
    cancel,
    resume,
    retryCell,
    subscribe,
    getState,
    getCells,
    getExperimentId: () => _experimentId,
    detachEventSource,
    dispose,
  };
}
