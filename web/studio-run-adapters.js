// Modal Studio — Run Event Adapters
//
// Compatibility/adaptation layer between the canonical run model
// (web/studio-run-model.js) and the EXISTING message shapes flowing around
// Studio: ComfyUI websocket messages, experiment worker progress messages,
// experiment lifecycle events, snapshot polls, and direct run results.
//
// Every emitted event carries:
//   - source        e.g. "ws.execution_start", "experiment.event.cell.completed",
//                          "snapshot.poll", "direct.result"
//   - metadata.raw  the original payload (for downstream diagnostics)
//   - identity      runId always; experimentId/cellId/attemptId/generationId
//                   where the payload provides them.
//
// Timestamps are NEVER fabricated: timestamp = payload timestamp when the
// payload actually carries one (most do not → null is fine).
//
// Completion is NEVER produced from stream close, timeouts, or absence of
// messages — only from explicit terminal evidence (execution_success,
// snapshot polls, direct results, experiment lifecycle events).
//
// Pure ESM, no DOM access, self-contained (imports only createRunEvent).

import { createRunEvent } from "./studio-run-model.js";

// ── Legacy status mapping ────────────────────────────────────────────────
//
// adaptLegacyStatus maps pre-canonical run status strings into canonical
// run statuses. Unrepresentable / non-progress states map to null (idle =
// nothing running, paused = not representable, unknown = no evidence).
//   draft→created          submitted→submitted    waiting→queued
//   queued→queued          in_progress→executing  running→executing
//   generating→executing   startup→starting       done→completed
//   success→completed      succeeded→completed    completed→completed
//   error→failed           failed→failed          failed_fatal→failed
//   completed_with_failures→failed                cancelled→canceled
//   canceled→canceled      stopped→canceled       interrupted→interrupted
//   idle→null              paused→null            unknown→null
//   anything else→null

const LEGACY_STATUS_MAP = {
  draft: "created",
  submitted: "submitted",
  waiting: "queued",
  queued: "queued",
  in_progress: "executing",
  running: "executing",
  generating: "executing",
  startup: "starting",
  done: "completed",
  success: "completed",
  succeeded: "completed",
  completed: "completed",
  error: "failed",
  failed: "failed",
  failed_fatal: "failed",
  completed_with_failures: "failed",
  cancelled: "canceled",
  canceled: "canceled",
  stopped: "canceled",
  interrupted: "interrupted",
};

/**
 * Map a legacy run status string to a canonical run status, or null when
 * the value is not representable in the canonical vocabulary.
 * @param {*} status - Legacy status string.
 * @returns {string|null}
 */
export function adaptLegacyStatus(status) {
  if (status == null) return null;
  const key = String(status).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(LEGACY_STATUS_MAP, key)
    ? LEGACY_STATUS_MAP[key]
    : null;
}

// ── Legacy cell status mapping ───────────────────────────────────────────
//
// Cell-level vocabulary (see CELL_STATUSES in studio-run-model.js).
//   pending→created        running→executing   in_progress→executing
//   completed→completed    success→completed   failed→failed
//   interrupted→interrupted skipped→skipped    cancelled→canceled
//   canceled→canceled      error→failed
//   anything else→null

const CELL_LEGACY_STATUS_MAP = {
  pending: "created",
  running: "executing",
  in_progress: "executing",
  completed: "completed",
  success: "completed",
  failed: "failed",
  interrupted: "interrupted",
  skipped: "skipped",
  cancelled: "canceled",
  canceled: "canceled",
  error: "failed",
};

/**
 * Map a legacy cell status string to a canonical cell status, or null.
 * @param {*} status - Legacy cell status string.
 * @returns {string|null}
 */
export function adaptCellLegacyStatus(status) {
  if (status == null) return null;
  const key = String(status).trim().toLowerCase();
  return Object.prototype.hasOwnProperty.call(CELL_LEGACY_STATUS_MAP, key)
    ? CELL_LEGACY_STATUS_MAP[key]
    : null;
}

// ── Shared helpers ───────────────────────────────────────────────────────

function coerceFiniteNumber(value) {
  if (value == null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function requireRunId(opts) {
  if (!opts || typeof opts !== "object") return null;
  const runId = opts.runId;
  if (runId == null || String(runId).trim() === "") return null;
  return String(runId);
}

// ── modal_status phase → canonical stage ─────────────────────────────────

const MODAL_STATUS_PHASE_MAP = {
  dispatch: "submitting",
  entry: "submitting",
  restore: "restoring",
  custom_nodes: "starting",
  gpu: "starting",
  warmup: "starting",
  backend_init: "starting",
  backend_ready: "starting",
  auto_save: "starting",
  startup: "starting",
  execution: "executing",
};

function mapPhaseToStage(phase) {
  if (phase == null) return null;
  return MODAL_STATUS_PHASE_MAP[String(phase)] ?? null;
}

// ── ComfyUI websocket message adaptation ─────────────────────────────────

/**
 * Adapt raw ComfyUI websocket message object(s) into canonical RunEvents.
 *
 * Handled message types:
 *   execution_start    → stage "executing", progress.totalNodes
 *   executing          → stage "executing", progress.currentNodeId/Name
 *   progress           → stage "sampling" + sampler{step,max} when step & max
 *                        are present; else stage "executing" + progress{value,max}
 *   progress_state     → stage "executing", progress.completedNodes/totalNodes/
 *                        currentNodeId/currentNodeName
 *   execution_cached   → stage "executing", progress.cachedNodes (metadata-ish)
 *   execution_success  → terminal "completed" (the ONLY ws completion signal)
 *   execution_error    → terminal "failed" with error
 *   modal_status       → stage per phase map; phase "done" emits a metadata-only
 *                        event (it is NOT completion); unknown phases are skipped
 *
 * Unknown message types are skipped entirely. This adapter NEVER produces
 * "completed" from stream close, timeouts, or absence of messages.
 *
 * @param {object|Array<object>} rawEvents - Single or array of WS messages.
 * @param {{runId:string, experimentId?:string, cellId?:string, attemptId?:string, generationId?:string, mode?:string}} opts
 * @returns {Array<object>} Canonical RunEvents.
 */
export function adaptComfyUIWsEvents(rawEvents, opts) {
  const runId = requireRunId(opts);
  if (runId == null) return [];
  const experimentId = opts.experimentId ?? null;
  const cellId = opts.cellId ?? null;
  const attemptId = opts.attemptId ?? null;
  const generationId = opts.generationId ?? null;
  const mode = opts.mode ?? "normal";

  const list = Array.isArray(rawEvents) ? rawEvents : [rawEvents];
  const out = [];
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const type = String(raw.type || "");
    const metadata = { raw: raw };
    const base = {
      runId: runId,
      experimentId: experimentId,
      cellId: cellId,
      attemptId: attemptId,
      generationId: generationId,
      mode: mode,
      metadata: metadata,
    };

    if (type === "execution_start") {
      out.push(createRunEvent({
        ...base,
        source: "ws.execution_start",
        stage: "executing",
        progress: {
          totalNodes: coerceFiniteNumber(raw.total_nodes),
          currentNodeId: null,
        },
      }));
    } else if (type === "executing") {
      out.push(createRunEvent({
        ...base,
        source: "ws.executing",
        stage: "executing",
        rawNodeId: raw.node != null ? raw.node : null,
        rawNodeName: raw.display_node != null ? raw.display_node : null,
        progress: {
          currentNodeId: raw.node != null ? raw.node : null,
          currentNodeName: raw.display_node != null ? raw.display_node : raw.node,
        },
      }));
    } else if (type === "progress") {
      // step+max → sampler slot; value → workflow progress slot. Never both.
      const step = coerceFiniteNumber(raw.step);
      const max = coerceFiniteNumber(raw.max);
      const value = coerceFiniteNumber(raw.value);
      if (step != null && max != null) {
        out.push(createRunEvent({
          ...base,
          source: "ws.progress",
          stage: "sampling",
          sampler: { step: step, max: max },
          queuePosition: raw.queue != null ? coerceFiniteNumber(raw.queue) : null,
        }));
      } else if (value != null) {
        out.push(createRunEvent({
          ...base,
          source: "ws.progress",
          stage: "executing",
          progress: { value: value, max: max },
        }));
      }
    } else if (type === "progress_state") {
      const nodes = raw.nodes && typeof raw.nodes === "object" ? raw.nodes : {};
      const ids = Object.keys(nodes);
      let completedNodes = 0;
      let runningId = null;
      let runningName = null;
      for (const id of ids) {
        const entry = nodes[id];
        if (!entry || typeof entry !== "object") continue;
        if (entry.state === "finished") completedNodes++;
        if (runningId == null && entry.state === "running") {
          runningId = id;
          runningName = entry.display_node_id != null ? entry.display_node_id : id;
        }
      }
      out.push(createRunEvent({
        ...base,
        source: "ws.progress_state",
        stage: "executing",
        progress: {
          completedNodes: completedNodes,
          totalNodes: ids.length,
          currentNodeId: runningId,
          currentNodeName: runningName,
        },
      }));
    } else if (type === "execution_cached") {
      out.push(createRunEvent({
        ...base,
        source: "ws.execution_cached",
        stage: "executing",
        progress: {
          cachedNodes: Array.isArray(raw.nodes) ? raw.nodes.length : 0,
        },
      }));
    } else if (type === "execution_success") {
      out.push(createRunEvent({
        ...base,
        source: "ws.execution_success",
        stage: "completed",
        status: "completed",
        metadata: { raw: raw, trace: raw.trace != null ? raw.trace : null },
      }));
    } else if (type === "execution_error") {
      out.push(createRunEvent({
        ...base,
        source: "ws.execution_error",
        stage: "failed",
        status: "failed",
        error: {
          message: raw.message != null ? raw.message : null,
          type: "execution_error",
        },
      }));
    } else if (type === "modal_status") {
      const stage = mapPhaseToStage(raw.phase);
      if (stage != null) {
        out.push(createRunEvent({
          ...base,
          source: "ws.modal_status",
          stage: stage,
        }));
      } else if (String(raw.phase || "") === "done") {
        // phase "done" is NOT completion — metadata-only event.
        out.push(createRunEvent({
          ...base,
          source: "ws.modal_status",
          stage: null,
          status: null,
        }));
      }
      // Unknown phases are skipped entirely.
    }
    // Unknown message types are skipped.
  }
  return out;
}

// ── Experiment worker progress adaptation ────────────────────────────────

/**
 * Adapt an experiment worker progress message into canonical RunEvents.
 *
 * Message shape (duck-typed):
 *   { experiment_id, cell_key, attempt_id, total_nodes, type, phase, message,
 *     node, step, max, queue }
 *
 *   type "status"          → stage via mapPhaseToStage(phase); phase "done"
 *                            emits a no-op event with null stage/status
 *   type "cell.executing"  → cell-level stage "executing" + totalNodes
 *   type "sampler.step"    → cell-level stage "sampling" + sampler{step,max}
 *                            + queuePosition
 *   type "cell.failed"     → cell-level status "failed" (NEVER a run terminal)
 *   unknown type           → []
 *
 * @param {object} msg - Raw worker progress message.
 * @param {{runId:string, mode?:string}} opts
 * @returns {Array<object>} Canonical RunEvents.
 */
export function adaptExperimentWorkerProgress(msg, opts) {
  const runId = requireRunId(opts);
  if (runId == null) return [];
  if (!msg || typeof msg !== "object") return [];
  const mode = opts.mode ?? "normal";
  const type = String(msg.type || "");
  const metadata = { raw: msg };
  const base = {
    runId: runId,
    experimentId: msg.experiment_id != null ? msg.experiment_id : null,
    cellId: msg.cell_key != null ? msg.cell_key : null,
    attemptId: msg.attempt_id != null ? msg.attempt_id : null,
    mode: mode,
    metadata: metadata,
  };

  if (type === "status") {
    return [createRunEvent({
      ...base,
      source: "experiment.worker.status",
      stage: mapPhaseToStage(msg.phase),
      status: null,
      parentStage: msg.phase != null ? String(msg.phase) : null,
    })];
  }
  if (type === "cell.executing") {
    return [createRunEvent({
      ...base,
      source: "experiment.worker.cell.executing",
      stage: "executing",
      rawNodeId: msg.node != null ? msg.node : null,
      progress: {
        totalNodes: coerceFiniteNumber(msg.total_nodes),
      },
    })];
  }
  if (type === "sampler.step") {
    return [createRunEvent({
      ...base,
      source: "experiment.worker.sampler.step",
      stage: "sampling",
      sampler: {
        step: coerceFiniteNumber(msg.step),
        max: coerceFiniteNumber(msg.max),
      },
      queuePosition: msg.queue != null ? coerceFiniteNumber(msg.queue) : null,
    })];
  }
  if (type === "cell.failed") {
    return [createRunEvent({
      ...base,
      source: "experiment.worker.cell.failed",
      status: "failed",
      error: {
        message: msg.message != null ? msg.message : null,
        type: "cell.failed",
      },
    })];
  }
  return [];
}

// ── Experiment lifecycle event adaptation ────────────────────────────────

/**
 * Adapt an experiment lifecycle event into canonical RunEvents.
 *
 * Message shape (duck-typed):
 *   { experiment_id, type, payload }
 * Payload duck-typing: cell key = payload.cell_key ?? payload.cellKey;
 * message = payload.message ?? payload.error.
 *
 *   experiment.created     → run-level stage/status "created"
 *   experiment.status      → stage/status via adaptLegacyStatus(payload.status)
 *   experiment.recovered   → stage "restoring"
 *   experiment.completed   → terminal "completed"
 *   experiment.stopped     → terminal "canceled"
 *   experiment.cancelled   → terminal "canceled"
 *   experiment.error       → terminal "failed" + error (type experiment.error)
 *   experiment.failed_fatal→ terminal "failed" + error (type experiment.failed_fatal)
 *   journal types (payload has a cell key or payload.type is cell.*):
 *     cell.attempt_created → cell status "created"
 *     cell.started         → cell stage/status "executing"
 *     cell.completed       → cell status "completed"
 *     cell.failed          → cell status "failed" (cell-level, never a run terminal)
 *     cell.interrupted     → cell status "interrupted"
 *     cell.skipped         → cell status "skipped"
 *     checkpoint.*         → metadata-only event (no status/stage change)
 *   unknown types          → []
 *
 * @param {object} msg - Raw experiment event message.
 * @param {{runId:string, mode?:string}} opts
 * @returns {Array<object>} Canonical RunEvents.
 */
export function adaptExperimentEvent(msg, opts) {
  const runId = requireRunId(opts);
  if (runId == null) return [];
  if (!msg || typeof msg !== "object") return [];
  const mode = opts.mode ?? "normal";
  const type = String(msg.type || "");
  const experimentId = msg.experiment_id != null ? msg.experiment_id : null;
  const payload = msg.payload && typeof msg.payload === "object" ? msg.payload : {};
  const metadata = { raw: msg };
  const base = {
    runId: runId,
    experimentId: experimentId,
    mode: mode,
    metadata: metadata,
  };

  const cellKey = payload.cell_key != null ? payload.cell_key : (payload.cellKey != null ? payload.cellKey : null);
  const message = payload.message != null ? payload.message : (payload.error != null ? payload.error : null);
  // Journal entries carry the cell type either nested (payload.type) or at
  // the TOP level (msg.type === "cell.interrupted" etc.). Prefer the nested
  // form when present, else fall back to the top-level type.
  const payloadType = String(payload.type || "");
  const topType = String(type || "");
  const cellType = payloadType !== ""
    ? payloadType
    : (topType.indexOf("cell.") === 0 || topType.indexOf("checkpoint.") === 0 ? topType : "");
  const isCellish = cellKey != null
    || cellType.indexOf("cell.") === 0
    || cellType.indexOf("checkpoint.") === 0;

  if (type === "experiment.created") {
    return [createRunEvent({ ...base, source: "experiment.event.experiment.created", stage: "created", status: "created" })];
  }
  if (type === "experiment.status") {
    const mapped = adaptLegacyStatus(payload.status);
    return [createRunEvent({ ...base, source: "experiment.event.experiment.status", stage: mapped, status: mapped })];
  }
  if (type === "experiment.recovered") {
    return [createRunEvent({ ...base, source: "experiment.event.experiment.recovered", stage: "restoring" })];
  }
  if (type === "experiment.completed") {
    return [createRunEvent({ ...base, source: "experiment.event.experiment.completed", stage: "completed", status: "completed" })];
  }
  if (type === "experiment.stopped") {
    return [createRunEvent({ ...base, source: "experiment.event.experiment.stopped", stage: "canceled", status: "canceled" })];
  }
  if (type === "experiment.cancelled") {
    return [createRunEvent({ ...base, source: "experiment.event.experiment.cancelled", stage: "canceled", status: "canceled" })];
  }
  if (type === "experiment.error") {
    return [createRunEvent({
      ...base,
      source: "experiment.event.experiment.error",
      stage: "failed",
      status: "failed",
      error: { message: message, type: "experiment.error" },
    })];
  }
  if (type === "experiment.failed_fatal") {
    return [createRunEvent({
      ...base,
      source: "experiment.event.experiment.failed_fatal",
      stage: "failed",
      status: "failed",
      error: { message: message, type: "experiment.failed_fatal" },
    })];
  }

  // ── Journal / cell-level types ───────────────────────────────────────
  if (!isCellish) return [];
  if (cellType === "cell.attempt_created") {
    return [createRunEvent({ ...base, source: "experiment.event.cell.attempt_created", cellId: cellKey, status: "created" })];
  }
  if (cellType === "cell.started") {
    return [createRunEvent({ ...base, source: "experiment.event.cell.started", cellId: cellKey, stage: "executing", status: "executing" })];
  }
  if (cellType === "cell.completed") {
    return [createRunEvent({ ...base, source: "experiment.event.cell.completed", cellId: cellKey, status: "completed" })];
  }
  if (cellType === "cell.failed") {
    return [createRunEvent({
      ...base,
      source: "experiment.event.cell.failed",
      cellId: cellKey,
      status: "failed",
      error: { message: message, type: "cell.failed" },
    })];
  }
  if (cellType === "cell.interrupted") {
    return [createRunEvent({ ...base, source: "experiment.event.cell.interrupted", cellId: cellKey, status: "interrupted" })];
  }
  if (cellType === "cell.skipped") {
    return [createRunEvent({ ...base, source: "experiment.event.cell.skipped", cellId: cellKey, status: "skipped" })];
  }
  if (cellType.indexOf("checkpoint.") === 0) {
    return [createRunEvent({ ...base, source: "experiment.event." + cellType, stage: null, status: null })];
  }
  return [];
}

// ── Snapshot poll adaptation ─────────────────────────────────────────────

/**
 * Adapt a snapshot poll result into canonical RunEvents.
 *
 * Message shape (duck-typed):
 *   { status/overall_status/state, counters: { completed, failed, skipped,
 *     interrupted, total }, message }
 *
 * Status source order: overall_status ?? status ?? state. A mapped non-null
 * status becomes a run-level status+stage change (completed/canceled/failed
 * from a snapshot ARE legitimate terminals — polling is explicit evidence,
 * unlike stream close). An unmappable status emits a metadata-only event.
 *
 * When counters.total is finite, the SAME event additionally carries
 * progress { value: completed ?? 0, max: total, percent }.
 *
 * @param {object} snapshot - Raw snapshot poll object.
 * @param {{runId:string, experimentId?:string}} opts
 * @returns {Array<object>} Canonical RunEvents.
 */
export function adaptSnapshot(snapshot, opts) {
  const runId = requireRunId(opts);
  if (runId == null) return [];
  if (!snapshot || typeof snapshot !== "object") return [];
  const experimentId = opts.experimentId != null ? opts.experimentId : null;
  const metadata = { raw: snapshot };

  const statusSource = snapshot.overall_status != null
    ? snapshot.overall_status
    : (snapshot.status != null ? snapshot.status : snapshot.state);
  const mapped = adaptLegacyStatus(statusSource);

  const counters = snapshot.counters && typeof snapshot.counters === "object" ? snapshot.counters : {};
  const total = coerceFiniteNumber(counters.total);
  const event = {
    runId: runId,
    experimentId: experimentId,
    mode: opts.mode != null ? opts.mode : "normal",
    source: "snapshot.poll",
    metadata: metadata,
    stage: mapped,
    status: mapped,
  };
  if (total != null) {
    const completed = coerceFiniteNumber(counters.completed);
    event.progress = { value: completed != null ? completed : 0, max: total };
  }
  return [createRunEvent(event)];
}

// ── Direct run result adaptation ─────────────────────────────────────────

/**
 * Adapt a direct run result into canonical RunEvents.
 *
 * Message shape (duck-typed):
 *   { status, runId, experimentId, runHistoryId, timings, error? }
 *
 *   status "completed"/"success"/"ok" → terminal "completed", metadata carries
 *                                       timings + runHistoryId
 *   status "error"/"failed"           → terminal "failed" with error
 *   anything else                     → []
 *
 * @param {object} result - Raw direct result object.
 * @param {{runId:string, mode?:string}} opts
 * @returns {Array<object>} Canonical RunEvents.
 */
export function adaptDirectResult(result, opts) {
  const runId = requireRunId(opts);
  if (runId == null) return [];
  if (!result || typeof result !== "object") return [];
  const mode = opts.mode ?? "normal";
  const metadata = { raw: result };
  const status = String(result.status || "").trim().toLowerCase();

  if (status === "completed" || status === "success" || status === "ok") {
    return [createRunEvent({
      runId: runId,
      experimentId: result.experimentId != null ? result.experimentId : null,
      mode: mode,
      source: "direct.result",
      stage: "completed",
      status: "completed",
      metadata: {
        raw: result,
        timings: result.timings != null ? result.timings : null,
        runHistoryId: result.runHistoryId != null ? result.runHistoryId : null,
      },
    })];
  }
  if (status === "error" || status === "failed") {
    return [createRunEvent({
      runId: runId,
      experimentId: result.experimentId != null ? result.experimentId : null,
      mode: mode,
      source: "direct.result",
      stage: "failed",
      status: "failed",
      metadata: metadata,
      error: {
        message: result.error != null ? result.error : null,
        type: "direct_result",
      },
    })];
  }
  return [];
}
