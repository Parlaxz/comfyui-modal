// ComfyUI Modal — Shared Progress State Tracker
//
// Extracts progress/status tracking from modal-node.js into a shared module
// so BOTH the standard progress bar AND Studio Playground consume the same
// event stream without duplicating logic.
//
// Provides TWO tracker types:
//
//   1. Global tracker (createProgressTracker) — for the modal-node progress bar;
//      tracks ALL ComfyUI execution events globally.
//
//   2. Scoped tracker (createScopedTracker) — for Studio Playground per-run
//      progress; only responds to execution events matching the active run.
//      Uses a "capture-and-lock" pattern: after start(), the first
//      execution_start locks the tracker to that prompt_id; subsequent events
//      are filtered by captured identity.
//
// Usage:
//   import { createProgressTracker } from "./comfymodal-progress.js";
//   const tracker = createProgressTracker(api);
//   // tracker.state — reactive progress state object
//   // tracker.onProgress(callback) — subscribe to state changes
//   // tracker.dispose() — clean up event listeners

/**
 * Create a shared progress tracker that subscribes to ComfyUI API events.
 * Returns an object with:
 *   .state   — current reactive progress state (read-only snapshot, updated internally)
 *   .onProgress(fn) — subscribe to state changes; fn(newState) called on every update
 *   .dispose() — remove all event listeners
 *
 * @param {object} api - ComfyUI api object (expects api.addEventListener)
 * @returns {object} tracker
 */
export function createProgressTracker(api) {
  if (!api || typeof api.addEventListener !== "function") {
    // Return a no-op tracker if API is not available
    return createNoopTracker();
  }

  // ── State ──────────────────────────────────────────────────────────────
  const state = {
    // Run identity
    runId: null,
    promptId: null,

    // Progress phase: "idle" | "startup" | "queued" | "generating" | "done" | "error"
    stage: "idle",

    // Overall progress percentage (0-100), null when indeterminate
    overallPercent: null,

    // Current executing node info
    currentNodeId: null,
    currentNodeLabel: null,

    // Node counting
    completedNodes: 0,
    totalNodes: 0,

    // Sampler step progress (separate from overallPercent)
    samplerStep: null,
    samplerMaximum: null,
    samplerPercent: null,

    // Timing
    elapsedMs: 0,
    startTime: null,

    // Queue
    queuePosition: 0,

    // Status messages
    message: "",
    error: "",

    // Perf tracking
    timingMilestones: {},
    perNodeDurations: {},

    // Node-level tracking
    _nodeStartTime: null,
    _nodeTimes: {},
    _nodesSeen: null,
  };

  // Internal state
  let _timerInterval = null;
  let _subscribers = [];

  // ── Notify subscribers ─────────────────────────────────────────────────
  function _notify() {
    const snapshot = { ...state };
    // Deep-clone mutable sub-objects
    snapshot.timingMilestones = { ...state.timingMilestones };
    snapshot.perNodeDurations = { ...state._nodeTimes };
    snapshot._nodesSeen = state._nodesSeen ? new Set(state._nodesSeen) : null;
    for (const fn of _subscribers) {
      try { fn(snapshot); } catch (e) { /* subscriber error */ }
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────
  function _reset() {
    _stopTimer();
    state.runId = null;
    state.promptId = null;
    state.stage = "idle";
    state.overallPercent = null;
    state.currentNodeId = null;
    state.currentNodeLabel = null;
    state.completedNodes = 0;
    state.totalNodes = 0;
    state.samplerStep = null;
    state.samplerMaximum = null;
    state.samplerPercent = null;
    state.elapsedMs = 0;
    state.startTime = null;
    state.queuePosition = 0;
    state.message = "";
    state.error = "";
    state.timingMilestones = {};
    state._nodeStartTime = null;
    state._nodeTimes = {};
    state._nodesSeen = new Set();
    _notify();
  }

  // ── Timer ──────────────────────────────────────────────────────────────
  function _startTimer() {
    _stopTimer();
    _timerInterval = setInterval(() => {
      if (state.startTime) {
        state.elapsedMs = Date.now() - state.startTime;
        _notify();
      }
    }, 250);
  }

  function _stopTimer() {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
  }

  // ── Node label resolution ──────────────────────────────────────────────
  // Use a local reference so this module doesn't depend on app.js
  function _getNodeLabel(nodeId) {
    if (typeof _resolveNodeLabel === "function") {
      try { return _resolveNodeLabel(nodeId); } catch {}
    }
    return String(nodeId);
  }

  // ── Event handlers ─────────────────────────────────────────────────────

  function onExecutionStart() {
    // Guard re-entry: already in startup or generating — ignore duplicate
    if (state.stage === "generating" || state.stage === "startup") return;
    // Also guard against reset race: if a reset is scheduled (from error),
    // skip reset and just update the state
    _reset();
    state.stage = "startup";
    state.startTime = Date.now();
    _startTimer();
    _notify();
  }

  function onExecuting(detail) {
    const node = (detail != null && typeof detail === "object") ? detail.node : detail;
    if (node === null || node === undefined) return;

    // Record previous node's wall-clock duration
    if (state.currentNodeId != null && state._nodeStartTime) {
      const prevDur = Date.now() - state._nodeStartTime;
      state._nodeTimes[String(state.currentNodeId)] = prevDur;
    }

    state.currentNodeId = node;
    state._nodeStartTime = Date.now();

    // Resolve label
    const nodeLabel = _getNodeLabel(node);
    state.currentNodeLabel = nodeLabel;

    // Track seen nodes
    if (state._nodesSeen) state._nodesSeen.add(node);
    state.completedNodes = state._nodesSeen ? state._nodesSeen.size : 0;

    // Calculate overall percent
    if (state.totalNodes > 0) {
      state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
    } else {
      state.overallPercent = null;
    }

    // Reset sampler step counter
    state.samplerStep = 0;
    state.samplerMaximum = 0;

    state.stage = "generating";
    _notify();
  }

  function onProgress(detail) {
    const d = detail || {};
    if (d.step != null || d.value != null) {
      state.samplerStep = d.step ?? d.value;
      state.samplerMaximum = d.max ?? d.max_step ?? d.maxStep ?? state.samplerMaximum;
    }
    if (d.queue != null) state.queuePosition = d.queue;
    // Update sampler percent separately — NEVER overwrite overallPercent
    if (state.stage === "generating") {
      if (state.samplerMaximum > 0 && state.samplerStep != null) {
        state.samplerPercent = (state.samplerStep / state.samplerMaximum) * 100;
      }
      _notify();
    }
  }

  function onExecutionCached(detail) {
    const nodes = detail?.nodes;
    if (Array.isArray(nodes)) {
      for (const n of nodes) {
        if (state._nodesSeen) state._nodesSeen.add(n);
      }
      state.completedNodes = state._nodesSeen ? state._nodesSeen.size : 0;
      if (state.totalNodes > 0) {
        state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
      }
      _notify();
    }
  }

  function onExecutionSuccess(event) {
    _stopTimer();
    state.stage = "done";
    state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;

    // Finalize current node time
    if (state.currentNodeId != null && state._nodeStartTime) {
      state._nodeTimes[String(state.currentNodeId)] = Date.now() - state._nodeStartTime;
    }
    state.perNodeDurations = { ...state._nodeTimes };
    state.overallPercent = 100;

    // Capture timing milestones from trace
    const detail = event?.detail || {};
    if (detail.trace) {
      state.timingMilestones = detail.trace;
    }
    if (detail.prompt_id) {
      state.promptId = detail.prompt_id;
    }

    _notify();

    // Schedule reset with a microtask delay to avoid race with a new
    // execution_start that may fire synchronously during the same event loop tick.
    // If a new execution_start fires before this runs, its guard will see
    // stage !== "generating" and proceed normally.
    setTimeout(() => {
      // Only reset if still in "done" or "error" — a new execution_start
      // would have advanced to "startup" or "generating".
      if (state.stage === "done" || state.stage === "error") {
        _reset();
      }
    }, 0);
  }

  function onExecutionError(event) {
    _stopTimer();
    state.stage = "error";
    state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;
    state.error = event?.detail?.message || "Execution error";
    _notify();

    // Schedule return to idle
    setTimeout(() => {
      _reset();
    }, 4000);
  }

  function onModalStatus(detail) {
    const d = detail || {};
    if (!d.prompt_id && !d.phase) return;
    if (d.phase === "startup" || d.phase === "warmup") {
      state.stage = "startup";
      state.message = d.message || "Starting up...";
      state.promptId = d.prompt_id || null;
      _notify();
    }
  }

  // ── Wire up events ─────────────────────────────────────────────────────
  const handlers = [];

  function _addListener(eventName, handler) {
    api.addEventListener(eventName, handler);
    handlers.push(() => {
      try { api.removeEventListener(eventName, handler); } catch {}
    });
  }

  _addListener("execution_start", onExecutionStart);
  _addListener("executing", (e) => onExecuting(e?.detail));
  _addListener("progress", (e) => onProgress(e?.detail));
  _addListener("execution_cached", (e) => onExecutionCached(e?.detail));
  _addListener("execution_success", (e) => onExecutionSuccess(e));
  _addListener("execution_error", (e) => onExecutionError(e));
  _addListener("modal_status", (e) => onModalStatus(e?.detail));

  // ── Public API ─────────────────────────────────────────────────────────
  return {
    state,
    onProgress(fn) {
      _subscribers.push(fn);
      return () => {
        _subscribers = _subscribers.filter(s => s !== fn);
      };
    },
    // Allow external code to set totalNodes (e.g., from intercepted prompt payload)
    setTotalNodes(count) {
      state.totalNodes = count;
      if (state.completedNodes > 0 && state.totalNodes > 0) {
        state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
      }
      _notify();
    },
    // Allow external code to set promptId
    setPromptId(id) {
      state.promptId = id;
      _notify();
    },
    dispose() {
      _stopTimer();
      for (const remove of handlers) {
        try { remove(); } catch {}
      }
      handlers.length = 0;
      _subscribers = [];
    },
  };
}

/**
 * Create a no-op tracker when the API is unavailable.
 */
function createNoopTracker() {
  const noopState = {
    runId: null, promptId: null, stage: "idle", overallPercent: null,
    currentNodeId: null, currentNodeLabel: null,
    completedNodes: 0, totalNodes: 0,
    samplerStep: null, samplerMaximum: null, samplerPercent: null,
    elapsedMs: 0, startTime: null, queuePosition: 0,
    message: "", error: "",
    timingMilestones: {}, perNodeDurations: {},
  };
  return {
    state: noopState,
    onProgress: () => () => {},
    dispose: () => {},
  };
}

// ── Scoped Progress Tracker ──────────────────────────────────────────────
//
// Creates a tracker that only responds to execution events matching the
// active Studio run identity. Uses a capture-and-lock pattern:
//
//   1. start() — begins listening for execution_start
//   2. First execution_start captured → locks to that prompt_id
//   3. Subsequent events filtered by captured identity
//   4. dispose() — removes all listeners
//
// Returns same API shape as createProgressTracker:
//   { state, onProgress(fn), setTotalNodes(count), dispose() }
//
// @param {object} api - ComfyUI api object (expects api.addEventListener)
// @param {object} identity - { runId, experimentId, promptId }
// @returns {object} scopedTracker
//
export function createScopedTracker(api, identity) {
  if (!api || typeof api.addEventListener !== "function") {
    return createNoopTracker();
  }

  // ── State (same shape as global tracker) ──────────────────────────────
  const state = {
    runId: (identity && identity.runId) || null,
    experimentId: (identity && identity.experimentId) || null,
    promptId: (identity && identity.promptId) || null,

    stage: "idle",
    overallPercent: null,

    currentNodeId: null,
    currentNodeLabel: null,

    completedNodes: 0,
    totalNodes: 0,

    samplerStep: null,
    samplerMaximum: null,
    samplerPercent: null,

    elapsedMs: 0,
    startTime: null,

    queuePosition: 0,

    message: "",
    error: "",

    timingMilestones: {},
    perNodeDurations: {},

    _nodeStartTime: null,
    _nodeTimes: {},
    _nodesSeen: null,
  };

  let _timerInterval = null;
  let _subscribers = [];
  let _started = false;
  let _locked = false;
  let _capturedPromptId = null;
  let _disposed = false;

  // Internal copy of identity for updateIdentity
  let _identity = identity ? { ...identity } : {};

  // ── Notify subscribers ─────────────────────────────────────────────────
  function _notify() {
    if (_disposed) return;
    const snapshot = { ...state };
    snapshot.timingMilestones = { ...state.timingMilestones };
    snapshot.perNodeDurations = { ...state._nodeTimes };
    snapshot._nodesSeen = state._nodesSeen ? new Set(state._nodesSeen) : null;
    for (const fn of _subscribers) {
      try { fn(snapshot); } catch (e) { /* subscriber error */ }
    }
  }

  // ── Reset ──────────────────────────────────────────────────────────────
  function _reset() {
    _stopTimer();
    state.runId = _identity.runId || null;
    state.experimentId = _identity.experimentId || null;
    state.promptId = _capturedPromptId || _identity.promptId || null;
    state.stage = "idle";
    state.overallPercent = null;
    state.currentNodeId = null;
    state.currentNodeLabel = null;
    state.completedNodes = 0;
    state.totalNodes = 0;
    state.samplerStep = null;
    state.samplerMaximum = null;
    state.samplerPercent = null;
    state.elapsedMs = 0;
    state.startTime = null;
    state.queuePosition = 0;
    state.message = "";
    state.error = "";
    state.timingMilestones = {};
    state._nodeStartTime = null;
    state._nodeTimes = {};
    state._nodesSeen = new Set();
    _notify();
  }

  // ── Timer ──────────────────────────────────────────────────────────────
  function _startTimer() {
    _stopTimer();
    _timerInterval = setInterval(() => {
      if (!_disposed && state.startTime) {
        state.elapsedMs = Date.now() - state.startTime;
        _notify();
      }
    }, 250);
  }

  function _stopTimer() {
    if (_timerInterval) {
      clearInterval(_timerInterval);
      _timerInterval = null;
    }
  }

  // ── Node label resolution ──────────────────────────────────────────────
  function _getNodeLabel(nodeId) {
    if (typeof _resolveNodeLabel === "function") {
      try { return _resolveNodeLabel(nodeId); } catch {}
    }
    return String(nodeId);
  }

  // ── Event handlers ─────────────────────────────────────────────────────

  function onExecutionStart(event) {
    if (!_started || _disposed) return;

    // If already locked to a promptId, ignore subsequent execution_start
    if (_locked) return;

    // Capture prompt_id from event detail, if available
    const detail = (event && event.detail) || {};
    const eventPromptId = detail.prompt_id || null;

    // Lock to this execution
    _locked = true;
    if (eventPromptId) {
      _capturedPromptId = eventPromptId;
      state.promptId = eventPromptId;
    }

    _reset();
    state.stage = "startup";
    state.startTime = Date.now();
    _startTimer();
    _notify();
  }

  function onExecuting(detail) {
    if (!_started || _disposed || !_locked) return;
    const node = (detail != null && typeof detail === "object") ? detail.node : detail;
    if (node === null || node === undefined) return;

    // Record previous node's wall-clock duration
    if (state.currentNodeId != null && state._nodeStartTime) {
      const prevDur = Date.now() - state._nodeStartTime;
      state._nodeTimes[String(state.currentNodeId)] = prevDur;
    }

    state.currentNodeId = node;
    state._nodeStartTime = Date.now();

    const nodeLabel = _getNodeLabel(node);
    state.currentNodeLabel = nodeLabel;

    if (state._nodesSeen) state._nodesSeen.add(node);
    state.completedNodes = state._nodesSeen ? state._nodesSeen.size : 0;

    if (state.totalNodes > 0) {
      state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
    } else {
      state.overallPercent = null;
    }

    state.samplerStep = 0;
    state.samplerMaximum = 0;
    state.samplerPercent = null;

    state.stage = "generating";
    _notify();
  }

  function onProgress(detail) {
    if (!_started || _disposed || !_locked) return;
    const d = detail || {};
    if (d.step != null || d.value != null) {
      state.samplerStep = d.step ?? d.value;
      state.samplerMaximum = d.max ?? d.max_step ?? d.maxStep ?? state.samplerMaximum;
    }
    if (d.queue != null) state.queuePosition = d.queue;
    if (state.stage === "generating") {
      if (state.samplerMaximum > 0 && state.samplerStep != null) {
        state.samplerPercent = (state.samplerStep / state.samplerMaximum) * 100;
      }
      _notify();
    }
  }

  function onExecutionCached(detail) {
    if (!_started || _disposed || !_locked) return;
    const nodes = detail?.nodes;
    if (Array.isArray(nodes)) {
      for (const n of nodes) {
        if (state._nodesSeen) state._nodesSeen.add(n);
      }
      state.completedNodes = state._nodesSeen ? state._nodesSeen.size : 0;
      if (state.totalNodes > 0) {
        state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
      }
      _notify();
    }
  }

  function onExecutionSuccess(event) {
    if (!_started || _disposed) return;

    // Only respond if we're locked AND the prompt_id matches
    const detail = (event && event.detail) || {};
    const eventPromptId = detail.prompt_id || null;

    if (!_locked) return;
    if (_capturedPromptId && eventPromptId && eventPromptId !== _capturedPromptId) {
      // prompt_id mismatch — not our run
      return;
    }

    _stopTimer();
    state.stage = "done";
    state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;

    if (state.currentNodeId != null && state._nodeStartTime) {
      state._nodeTimes[String(state.currentNodeId)] = Date.now() - state._nodeStartTime;
    }
    state.perNodeDurations = { ...state._nodeTimes };
    state.overallPercent = 100;

    if (detail.trace) {
      state.timingMilestones = detail.trace;
    }
    if (detail.prompt_id) {
      state.promptId = detail.prompt_id;
    }

    _notify();

    // Schedule reset to idle after microtask delay
    setTimeout(() => {
      if (!_disposed && (state.stage === "done" || state.stage === "error")) {
        _locked = false;
        _capturedPromptId = null;
        _reset();
      }
    }, 0);
  }

  function onExecutionError(event) {
    if (!_started || _disposed) return;

    const detail = (event && event.detail) || {};
    const eventPromptId = detail.prompt_id || null;

    if (!_locked) return;
    if (_capturedPromptId && eventPromptId && eventPromptId !== _capturedPromptId) {
      return;
    }

    _stopTimer();
    state.stage = "error";
    state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;
    state.error = detail.message || "Execution error";
    _notify();

    setTimeout(() => {
      if (!_disposed) {
        _locked = false;
        _capturedPromptId = null;
        _reset();
      }
    }, 4000);
  }

  function onModalStatus(detail) {
    if (!_started || _disposed) return;
    const d = detail || {};
    if (!d.prompt_id && !d.phase) return;

    // If locked, only respond to matching prompt_id
    if (_locked && _capturedPromptId && d.prompt_id && d.prompt_id !== _capturedPromptId) {
      return;
    }

    if (d.phase === "startup" || d.phase === "warmup") {
      state.stage = "startup";
      state.message = d.message || "Starting up...";
      state.promptId = d.prompt_id || null;
      _notify();
    }
  }

  // ── Experiment event handlers ──────────────────────────────────────────
  //
  // experiment.worker.progress: carries sampler/queue updates from Modal
  // execution workers during experiment runs. Soft-locks the tracker when
  // the experiment_id matches, enabling progress display even without a
  // standard execution_start event.
  //
  // experiment.event: carries terminal lifecycle events for experiments
  // (completed, stopped, error, failed_fatal).

  function onExperimentWorkerProgress(detail) {
    if (!_started || _disposed) return;
    const d = detail || {};
    const eventExperimentId = d.experiment_id || null;

    // If we have an experimentId in identity and this event matches,
    // soft-lock the tracker so it produces progress even without execution_start
    if (_identity.experimentId && eventExperimentId && eventExperimentId === _identity.experimentId) {
      if (!_locked) {
        _locked = true;
        state.startTime = Date.now();
        state.stage = "generating";
        _startTimer();
      }

      // Update sampler progress fields
      if (d.step != null || d.value != null) {
        state.samplerStep = d.step ?? d.value;
        state.samplerMaximum = d.max ?? d.max_step ?? d.maxStep ?? state.samplerMaximum;
      }
      if (d.queue != null) state.queuePosition = d.queue;

      if (state.samplerMaximum > 0 && state.samplerStep != null) {
        state.samplerPercent = (state.samplerStep / state.samplerMaximum) * 100;
      }

      _notify();
    }
  }

  function onExperimentEvent(event) {
    if (!_started || _disposed) return;
    const detail = (event && event.detail) || {};
    const eventType = detail.type || "";
    const eventExperimentId = detail.experiment_id || null;

    // If the event carries an experiment_id, only respond if our identity matches.
    // Single-run trackers (no experimentId) should reject all experiment events.
    if (eventExperimentId) {
      if (!_identity.experimentId || eventExperimentId !== _identity.experimentId) return;
    }
    // If not locked, don't process experiment events (no matching run)
    if (!_locked) return;

    if (eventType === "experiment.completed" || eventType === "experiment.stopped") {
      _stopTimer();
      state.stage = "done";
      state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;
      state.overallPercent = 100;
      _notify();

      setTimeout(() => {
        if (!_disposed && (state.stage === "done" || state.stage === "error")) {
          _locked = false;
          _capturedPromptId = null;
          _reset();
        }
      }, 0);
    } else if (eventType === "experiment.error" || eventType === "experiment.failed_fatal") {
      _stopTimer();
      state.stage = "error";
      state.elapsedMs = state.startTime ? Date.now() - state.startTime : 0;
      state.error = detail.error || detail.message || "Experiment error";
      _notify();

      setTimeout(() => {
        if (!_disposed) {
          _locked = false;
          _capturedPromptId = null;
          _reset();
        }
      }, 4000);
    }
  }

  // ── Wire up events ─────────────────────────────────────────────────────
  const handlers = [];

  function _addListener(eventName, handler) {
    if (_disposed) return;
    api.addEventListener(eventName, handler);
    handlers.push(() => {
      try { api.removeEventListener(eventName, handler); } catch {}
    });
  }

  _addListener("execution_start", onExecutionStart);
  _addListener("executing", (e) => onExecuting(e?.detail));
  _addListener("progress", (e) => onProgress(e?.detail));
  _addListener("execution_cached", (e) => onExecutionCached(e?.detail));
  _addListener("execution_success", (e) => onExecutionSuccess(e));
  _addListener("execution_error", (e) => onExecutionError(e));
  _addListener("modal_status", (e) => onModalStatus(e?.detail));
  _addListener("experiment.worker.progress", (e) => onExperimentWorkerProgress(e?.detail));
  _addListener("experiment.event", (e) => onExperimentEvent(e));

  // ── Public API ─────────────────────────────────────────────────────────
  return {
    state,

    /** Start listening for execution events. Must be called to activate. */
    start() {
      _started = true;
    },

    /** Update the identity this tracker is scoped to. */
    updateIdentity(newIdentity) {
      if (newIdentity) {
        _identity = { ..._identity, ...newIdentity };
        if (newIdentity.runId != null) state.runId = newIdentity.runId;
        if (newIdentity.experimentId != null) state.experimentId = newIdentity.experimentId;
        if (newIdentity.promptId != null) {
          _capturedPromptId = newIdentity.promptId;
          state.promptId = newIdentity.promptId;
        }
      }
    },

    onProgress(fn) {
      _subscribers.push(fn);
      return () => {
        _subscribers = _subscribers.filter(s => s !== fn);
      };
    },

    setTotalNodes(count) {
      state.totalNodes = count;
      if (state.completedNodes > 0 && state.totalNodes > 0) {
        state.overallPercent = (state.completedNodes / state.totalNodes) * 100;
      }
      _notify();
    },

    setPromptId(id) {
      if (id) {
        _capturedPromptId = id;
        state.promptId = id;
      }
      _notify();
    },

    dispose() {
      _disposed = true;
      _started = false;
      _stopTimer();
      for (const remove of handlers) {
        try { remove(); } catch {}
      }
      handlers.length = 0;
      _subscribers = [];
    },
  };
}

// ── Module-level node label resolver ────────────────────────────────────
// Set this from modal-node.js to enable node label resolution.
let _resolveNodeLabel = null;

export function setNodeLabelResolver(fn) {
  _resolveNodeLabel = fn;
}

// ── Shared singleton tracker ────────────────────────────────────────────
// Enables both modal-node.js and Studio Playground to use the same tracker.
let _sharedTracker = null;

/**
 * Initialize the shared tracker (called once by modal-node.js).
 * @param {object} api - ComfyUI api object
 * @returns {object} tracker
 */
export function initSharedTracker(api) {
  if (!_sharedTracker) {
    _sharedTracker = createProgressTracker(api);
  }
  return _sharedTracker;
}

/**
 * Get the shared tracker instance (returns null before init).
 * @returns {object|null}
 */
export function getSharedTracker() {
  return _sharedTracker;
}
