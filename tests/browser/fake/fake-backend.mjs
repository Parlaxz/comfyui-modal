// Modal Studio — Deterministic Fake Backend (scenario engine)
//
// Pure in-memory scenario engine for the Playwright browser harness.
// Contains NO http code; fake-server.mjs exposes it over HTTP.  A session
// owns presets, snapshots, backends, experiments, run history, the
// pending scenario, the tracker-bus event queue, and registered assets.
//
// Scenario execution model:
//   A scenario (see scenarios.mjs) is a declarative definition:
//     { kind, cellCount, submit, initialStatus, initialJournal,
//       initialTracker, steps: [{at, status?, journal?, tracker?}],
//       terminal: {delay, status, journal, tracker},
//       postTerminalTracker, registerAssets, missingAssets, seed }
//   The engine creates an experiment + run-history record at submit,
//   resolves `{token}` placeholders against per-experiment generated ids,
//   then applies timeline entries on real timers (ms after submit),
//   poll-count triggers ("poll:N"), and a terminal entry.  Journal events
//   accumulate into GET /experiments/:id responses; tracker events are
//   appended to a session event queue the harness api-stub drains.

import { randomBytes } from "node:crypto";
import { SCENARIOS, getScenario } from "./scenarios.mjs";

// ── Deterministic PNG bytes ─────────────────────────────────────────────
// Fixed 4x4 solid-color PNGs (precomputed).  Same id → same bytes every time.
const PNG_TABLE = [
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGNwa7rzHxkzkC4AAIbHKjFzVihiAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGPwWR/wHxkzkC4AAM/wJKGneA2pAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGN4HxzwHxkzkC4AAHNHKRHLvTVqAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGP4fUD3PzJmIF0AAC+2LnE6ndjqAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGNY7b7nPzJmIF0AAKSnKtFgeOMPAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGP4P4PhPzJmIF0AAIQPKWHbUabgAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGNQWzbrPzJmIF0AAAM3JlHsVyHzAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGOYNm3af2TMQLoAANDXLBHpXtsEAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGOIior6j4wZSBcAAEyoINH9oieQAAAAAElFTkSuQmCC",
  "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAYAAACp8Z5+AAAAEklEQVR4nGM4YVPxHxkzkC4AAD7nJ7HZufPFAAAAAElFTkSuQmCC",
];
const PNG_CACHE = new Map();

function _pngFor(key) {
  let bytes = PNG_CACHE.get(key);
  if (bytes) return bytes;
  let h = 0;
  const s = String(key);
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  const idx = h % PNG_TABLE.length;
  bytes = Buffer.from(PNG_TABLE[idx], "base64");
  PNG_CACHE.set(key, bytes);
  return bytes;
}

// ── Id / time helpers ───────────────────────────────────────────────────

function _hex(n = 8) {
  return randomBytes(n).toString("hex");
}
function _makeExperimentId() { return "exp_" + _hex(); }
function _makeRunId() { return "run_" + _hex(); }
function _makePromptId() { return "prompt_" + _hex(); }
function _makeCheckpointId() { return "ck_" + _hex(); }
function _makeAttemptId() { return "a_" + _hex(4); }
function _makeSnapshotId() { return "snap_" + _hex(); }
function _makePresetId() { return "preset_" + _hex(); }
function _now() { return new Date().toISOString(); }

// ── Token interpolation ─────────────────────────────────────────────────

const TOKEN_RE = /\{([a-z][a-z0-9_]*)\}/g;

function _interpolate(value, ctx) {
  if (typeof value === "string") {
    return value.replace(TOKEN_RE, (_, name) => (ctx[name] != null ? String(ctx[name]) : `{${name}}`));
  }
  if (Array.isArray(value)) return value.map((v) => _interpolate(v, ctx));
  if (value && typeof value === "object") {
    const out = {};
    for (const k of Object.keys(value)) out[k] = _interpolate(value[k], ctx);
    return out;
  }
  return value;
}

// ── Session factory ─────────────────────────────────────────────────────

const SESSIONS = new Map(); // sessionId → session object
let _sessionSeq = 0;

export function createSession() {
  const sessionId = "sess_" + (++_sessionSeq).toString(36) + _hex(4);
  const session = {
    sessionId,
    presets: new Map(),
    snapshots: new Map(),
    backends: [
      {
        id: "backend_default",
        name: "Default Backend (fake)",
        kind: "modal",
        status: "deployed",
        gpu: "A10G",
        description: "Seeded fake backend",
      },
    ],
    experiments: new Map(), // experimentId → experiment record
    modernExperiments: new Map(), // experimentId → modern V2 experiment record (D5)
    history: [],            // newest-first raw run-history records (legacy)
    historyV2: [],          // History V2 records (generations + experiments)
    historyV2Fail: {},      // simulated-failure flags, e.g. { feed: true }
    profileLevel: "off",    // per-session profile level (off|summary|detailed|trace|trace_verbose)
    pendingScenario: null,  // { name, overrides }
    eventQueue: [],         // tracker-bus events {type, detail} awaiting the pump
    assets: new Map(),      // assetId → Buffer
    assetOrigins: new Map(), // internal producer origins; never a wire field
    outputs: new Map(),     // output filename → Buffer
    saveRequests: [],
    workflowRuns: [],       // captured POST /studio/run bodies (modern workflow lane)
    workflowRunSeq: 0,      // per-session sequence for deterministic run ids
    workflowSeed: null,     // lazy-built Studio Workflow platform seed dataset
  };
  _seedPresetAndSnapshot(session);
  _seedDefaultHistory(session);
  _seedDefaultHistoryV2(session);
  SESSIONS.set(sessionId, session);
  return { sessionId };
}

export function getSession(id) {
  const session = SESSIONS.get(id);
  if (!session) {
    const err = new Error(`unknown fake session: ${id}`);
    err.code = "UNKNOWN_SESSION";
    throw err;
  }
  return session;
}

export function resetSession(id) {
  const session = SESSIONS.get(id);
  if (!session) return { status: "ok", reset: false };
  for (const experiment of session.experiments.values()) {
    _clearExperimentTimers(experiment);
  }
  session.presets.clear();
  session.snapshots.clear();
  session.experiments.clear();
  session.modernExperiments.clear();
  session.history.length = 0;
  session.historyV2.length = 0;
  session.historyV2Fail = {};
  session.profileLevel = "off";
  session.eventQueue.length = 0;
  session.assets.clear();
  session.assetOrigins.clear();
  session.outputs.clear();
  session.saveRequests.length = 0;
  session.workflowRuns.length = 0;
  session.workflowRunSeq = 0;
  session.workflowSeed = null;
  session.pendingScenario = null;
  _seedPresetAndSnapshot(session);
  _seedDefaultHistory(session);
  _seedDefaultHistoryV2(session);
  return { status: "ok", reset: true };
}

export function deleteSession(id) {
  const session = SESSIONS.get(id);
  if (session) {
    for (const experiment of session.experiments.values()) {
      _clearExperimentTimers(experiment);
    }
    SESSIONS.delete(id);
  }
  return { status: "ok" };
}

// ── Seeded catalog ──────────────────────────────────────────────────────

function _seedPresetAndSnapshot(session) {
  const now = _now();
  const snapshotId = "snap_default";
  const snapshot = {
    id: snapshotId,
    name: "Default Snapshot (fake)",
    description: "Seeded snapshot for fake-backend tests",
    createdAt: now,
    updatedAt: now,
    compatibleFeatures: ["txt2img"],
    graphJson: null,
    apiPromptJson: null,
    nodeBindings: { prompt: { nodeId: "3", widgetName: "text" } },
    outputNodeId: "5",
    modelSummary: "sdxl-base-1.0",
    source: "manual",
    controlSchemas: {},
    archived: false,
    status: "runnable",
    featureStatus: { txt2img: { status: "runnable", reason: "" } },
    disabledReason: "",
  };
  session.snapshots.set(snapshotId, snapshot);

  const presetId = "preset_default";
  const preset = {
    id: presetId,
    label: "Default Preset (fake)",
    description: "Seeded preset for fake-backend tests",
    snapshotId,
    compatibleFeatures: ["txt2img"],
    defaults: {
      prompt: "a deterministic fake image",
      negative_prompt: "",
      seed: 42,
      steps: 20,
      guidance: 7,
      sampler: "euler",
      scheduler: "normal",
      denoise: 1,
      width: 1024,
      height: 1024,
    },
    sourceType: "manual",
    sourceId: "",
    archived: false,
    createdAt: now,
    updatedAt: now,
    status: "runnable",
    disabledReason: "",
  };
  session.presets.set(presetId, preset);
}

function _seedDefaultHistory(session) {
  const now = Date.now();
  const records = [];
  for (let i = 0; i < 5; i++) {
    records.push(_makeSeedRecord(session, i, {
      statuses: ["completed", "failed", "in_progress", "completed", "queued"],
      imageEvery: 2,
      presetCount: 2,
      favoriteEvery: 9,
      registerAssets: true,
      startOffsetMs: i * 3600_000,
      now,
    }));
  }
  for (const r of records) session.history.push(r);
  _registerSeedAssets(session, records, true);
}

// ── Scenario selection (test control) ───────────────────────────────────

export function setPendingScenario(id, scenarioName, overrides = null) {
  const session = getSession(id);
  if (scenarioName == null || scenarioName === "") {
    session.pendingScenario = null;
    return { status: "ok", scenario: null };
  }
  const def = getScenario(scenarioName);
  if (!def) {
    return {
      status: "error",
      message: `Unknown scenario "${scenarioName}". Known: ${Object.keys(SCENARIOS).join(", ")}`,
    };
  }
  session.pendingScenario = { name: scenarioName, overrides: overrides || null };
  return { status: "ok", scenario: scenarioName };
}

function _resolveScenario(session, fallbackName) {
  const pending = session.pendingScenario;
  let name = fallbackName || "success";
  let overrides = null;
  if (pending && pending.name) {
    name = pending.name;
    overrides = pending.overrides;
  }
  let def = getScenario(name);
  if (!def) {
    name = "success";
    def = getScenario(name);
  }
  if (overrides) {
    def = _mergeOverrides(def, overrides);
  }
  return { name, def };
}

function _mergeOverrides(def, overrides) {
  const out = JSON.parse(JSON.stringify(def));
  if (overrides.delays && typeof overrides.delays === "object") {
    out.delays = Object.assign({}, out.delays || {}, overrides.delays);
  }
  if (overrides.submit && typeof overrides.submit === "object") {
    out.submit = Object.assign({}, out.submit || {}, overrides.submit);
  }
  if (overrides.extraInitialJournal && Array.isArray(overrides.extraInitialJournal)) {
    out.initialJournal = [...(out.initialJournal || []), ...overrides.extraInitialJournal];
  }
  if (overrides.extraInitialTracker && Array.isArray(overrides.extraInitialTracker)) {
    out.initialTracker = [...(out.initialTracker || []), ...overrides.extraInitialTracker];
  }
  if (overrides.terminalDelay != null) {
    out.terminal = Object.assign({}, out.terminal || {}, { delay: overrides.terminalDelay });
  }
  return out;
}

// ── Experiment creation ─────────────────────────────────────────────────

function _buildCtx(expId, runId, cellCount, outputsPerCell) {
  const ctx = {
    experiment_id: expId,
    run_id: runId,
    run_history_id: runId,
    prompt_id: _makePromptId(),
  };
  for (let i = 0; i < cellCount; i++) {
    ctx["cell_key_" + i] = "cell_" + i;
    ctx["checkpoint_" + i] = _makeCheckpointId();
    ctx["attempt_" + i] = _makeAttemptId();
    ctx["asset_" + i] = "asset_" + _hex();
    ctx["preview_asset_" + i] = "preview_" + _hex();
  }
  for (let i = 0; i < cellCount * outputsPerCell; i++) {
    ctx["output_" + i] = "studio_output_" + _hex() + ".png";
  }
  return ctx;
}

function _createExperiment(session, payload, scenario, kind) {
  const expId = _makeExperimentId();
  const runId = _makeRunId();
  const cellCount = kind === "experiment"
    ? Math.max(1, Number(scenario.cellCount) || 1)
    : 1;
  const outputsPerCell = Math.max(1, Number(scenario.outputsPerCell) || 1);
  const ctx = _buildCtx(expId, runId, cellCount, outputsPerCell);
  const now = _now();

  const uniquePresetIds = [...new Set((payload && payload.presetIds || []).filter(Boolean))];
  const isExperiment = kind === "experiment";

  const definition = {
    schema_version: 1,
    experiment_id: expId,
    revision: 1,
    name: isExperiment
      ? "Studio Experiment: " + ((payload && payload.experiment && payload.experiment.name) || "Experiment")
      : "Run " + runId,
    notes: "",
    created_at: now,
    updated_at: now,
  };
  if (isExperiment && uniquePresetIds.length > 0) {
    definition.studio_meta = { studio_preset_ids: uniquePresetIds };
  }

  const experiment = {
    experiment_id: expId,
    run_id: runId,
    kind,
    scenarioName: scenario.name,
    definition,
    ctx,
    journal: [],
    snapshot: {
      status: scenario.initialStatus || "running",
      overall_status: scenario.initialStatus || "running",
      counters: { completed: 0, failed: 0, interrupted: 0 },
      total_cells: cellCount,
      totalCells: cellCount,
      cell_visible: {},
      checkpoints: {},
      attempts: {},
      created_at: now,
      updated_at: now,
    },
    cellStates: {},   // cell_key → "completed"|"failed"|"interrupted"|"skipped"
    pollCount: 0,
    pollSteps: [],    // { atPoll, step }
    terminalApplied: false,
    terminalTimer: null,
    timers: [],
    stopRequested: false,
    firstOutputFilename: "",
    firstPrimaryAssetId: "",
  };

  // Build poll triggers from scenario.steps with at:"poll:N"
  const steps = scenario.steps || [];
  for (const step of steps) {
    if (step.at === "submit") {
      _applyStep(session, experiment, step);
    } else if (typeof step.at === "string" && step.at.startsWith("poll:")) {
      const n = parseInt(step.at.slice(5), 10);
      if (!Number.isNaN(n)) experiment.pollSteps.push({ atPoll: n, step });
    } else if (step.at && typeof step.at === "object" && typeof step.at.ms === "number") {
      _scheduleMsStep(session, experiment, step.at.ms, step);
    } else {
      // Unknown trigger — ignore (scenarios must be authored correctly).
    }
  }

  // Apply initial journal/tracker/status
  const initialJournal = scenario.initialJournal || [];
  for (const ev of initialJournal) _appendJournal(session, experiment, ev);
  const initialTracker = scenario.initialTracker || [];
  for (const ev of initialTracker) _queueTracker(session, experiment, ev);
  _setStatus(experiment, scenario.initialStatus || "running");

  // Schedule terminal
  const terminal = scenario.terminal || {};
  const terminalDelay = _scenarioDelay(scenario, "terminal", terminal.delay, 650);
  experiment.terminalTimer = _schedule(session, experiment, terminalDelay, () => {
    _applyTerminal(session, experiment, scenario);
  });

  // Post-terminal tracker events (out_of_order) fire shortly after terminal
  if (Array.isArray(scenario.postTerminalTracker) && scenario.postTerminalTracker.length > 0) {
    _schedule(session, experiment, terminalDelay + 120, () => {
      for (const ev of scenario.postTerminalTracker) _queueTracker(session, experiment, ev);
    });
  }

  return experiment;
}

function _scenarioDelay(scenario, key, explicit, fallback) {
  if (typeof explicit === "number") return explicit;
  if (scenario.delays && typeof scenario.delays[key] === "number") return scenario.delays[key];
  return fallback;
}

// ── Scheduling primitives ───────────────────────────────────────────────

function _schedule(session, experiment, delayMs, fn) {
  const timer = setTimeout(() => {
    const idx = experiment.timers.indexOf(timer);
    if (idx !== -1) experiment.timers.splice(idx, 1);
    try { fn(); } catch (e) { /* scenario timer error — keep engine alive */ }
  }, Math.max(0, delayMs));
  experiment.timers.push(timer);
  return timer;
}

function _scheduleMsStep(session, experiment, ms, step) {
  _schedule(session, experiment, ms, () => _applyStep(session, experiment, step));
}

function _clearExperimentTimers(experiment) {
  if (!experiment) return;
  for (const t of experiment.timers || []) clearTimeout(t);
  experiment.timers = [];
  if (experiment.terminalTimer) { clearTimeout(experiment.terminalTimer); experiment.terminalTimer = null; }
}

// ── Step application ────────────────────────────────────────────────────

function _applyStep(session, experiment, step) {
  if (step.status) _setStatus(experiment, step.status);
  if (step.journal) for (const ev of step.journal) _appendJournal(session, experiment, ev);
  if (step.tracker) for (const ev of step.tracker) _queueTracker(session, experiment, ev);
}

function _setStatus(experiment, status) {
  if (!status) return;
  experiment.snapshot.status = status;
  experiment.snapshot.overall_status = status;
  experiment.snapshot.updated_at = _now();
}

function _appendJournal(session, experiment, rawEvent) {
  const event = _interpolate(rawEvent, experiment.ctx);
  experiment.journal.push(event);
  experiment.snapshot.updated_at = _now();
  _trackCellEvent(experiment, event);
  _registerAssetsFromEvent(session, experiment, event);
}

function _queueTracker(session, experiment, rawEvent) {
  const event = _interpolate(rawEvent, experiment.ctx);
  session.eventQueue.push(event);
}

function _trackCellEvent(experiment, event) {
  const payload = event.payload || {};
  const cellKey = payload.cell_key;
  if (!cellKey) return;
  const type = event.type;
  const counters = experiment.snapshot.counters;
  if (type === "cell.completed" && experiment.cellStates[cellKey] !== "completed") {
    experiment.cellStates[cellKey] = "completed";
    counters.completed += 1;
    if (!experiment.firstOutputFilename) {
      if (Array.isArray(payload.output_paths) && payload.output_paths.length > 0) {
        experiment.firstOutputFilename = payload.output_paths[0];
      }
      if (payload.primary_asset_id) experiment.firstPrimaryAssetId = payload.primary_asset_id;
    }
  } else if (type === "cell.failed" && !experiment.cellStates[cellKey]) {
    experiment.cellStates[cellKey] = "failed";
    counters.failed += 1;
  } else if (type === "cell.interrupted" && !experiment.cellStates[cellKey]) {
    experiment.cellStates[cellKey] = "interrupted";
    counters.interrupted += 1;
  } else if (type === "cell.skipped" && !experiment.cellStates[cellKey]) {
    experiment.cellStates[cellKey] = "skipped";
    counters.interrupted += 1;
  }
}

function _applyTerminal(session, experiment, scenario) {
  if (experiment.terminalApplied || experiment.stopRequested) return;
  experiment.terminalApplied = true;
  const terminal = scenario.terminal || {};
  const status = terminal.status || "completed";

  // Interrupt any still-pending cells so counters are consistent with
  // the terminal status (only when the scenario did not already complete them).
  const total = experiment.snapshot.total_cells || 1;
  for (let i = 0; i < total; i++) {
    const ck = "cell_" + i;
    if (experiment.cellStates[ck]) continue;
    if (status === "cancelled" || status === "stopped") {
      const ev = {
        type: "cell.interrupted",
        payload: {
          cell_key: ck,
          checkpoint_id: experiment.ctx["checkpoint_" + i] || _makeCheckpointId(),
          attempt_id: experiment.ctx["attempt_" + i] || _makeAttemptId(),
          reason: "cancelled",
        },
      };
      experiment.journal.push(ev);
      _trackCellEvent(experiment, ev);
    }
  }

  if (terminal.journal) for (const ev of terminal.journal) _appendJournal(session, experiment, ev);
  if (terminal.tracker) for (const ev of terminal.tracker) _queueTracker(session, experiment, ev);
  _setStatus(experiment, status);
  _syncHistoryOnTerminal(session, experiment, status);
}

// ── Asset registration ──────────────────────────────────────────────────

function _registerAssetsFromEvent(session, experiment, event) {
  const scenario = getScenario(experiment.scenarioName);
  if (scenario && scenario.registerAssets === false) return;
  const missing = new Set((scenario && scenario.missingAssets || []).map((t) => _interpolate(t, experiment.ctx)));
  const payload = event.payload || {};
  const candidates = [];
  for (const key of ["primary_asset_id", "preview_asset_id", "asset_id"]) {
    if (payload[key]) candidates.push({ kind: "asset", id: payload[key] });
  }
  if (Array.isArray(payload.asset_ids)) {
    for (const aid of payload.asset_ids) candidates.push({ kind: "asset", id: aid });
  }
  for (const key of ["output_path", "output_paths"]) {
    const v = payload[key];
    if (typeof v === "string") candidates.push({ kind: "output", id: v });
    else if (Array.isArray(v)) for (const f of v) candidates.push({ kind: "output", id: f });
  }
  for (const c of candidates) {
    if (missing.has(c.id)) continue;
    if (c.kind === "asset") session.assets.set(c.id, _pngFor(c.id));
    else session.outputs.set(c.id, _pngFor(c.id));
  }
}

// ── Run history sync ────────────────────────────────────────────────────

function _makeHistoryRecord(session, experiment, payload, scenario, kind) {
  const controls = (payload && (payload.controls || payload.resolved_controls || {})) || {};
  const uniquePresetIds = [...new Set((payload && payload.presetIds || []).filter(Boolean))];
  const now = _now();
  const extra = {
    studio_preset_id: (payload && payload.presetId) || uniquePresetIds[0] || "",
    studio_feature_id: (payload && payload.featureId) || "txt2img",
    studio_preset_label: (payload && payload.presetLabel) || "",
  };
  if (controls.prompt !== undefined) extra.prompt = controls.prompt;
  if (controls.negative_prompt !== undefined) extra.negative_prompt = controls.negative_prompt;
  if (controls.seed !== undefined) extra.seed = controls.seed;

  return {
    run_id: experiment.run_id,
    experiment_id: experiment.experiment_id,
    kind: kind === "experiment" ? "experiment" : "experiment_cell",
    status: "in_progress",
    started_at: now,
    workflow_name: "Studio Run",
    prompt: controls.prompt || "",
    negative_prompt: controls.negative_prompt || "",
    seed: controls.seed ?? null,
    steps: controls.steps ?? null,
    guidance: controls.guidance ?? null,
    sampler: controls.sampler || "",
    scheduler: controls.scheduler || "",
    denoise: controls.denoise ?? null,
    width: controls.width ?? null,
    height: controls.height ?? null,
    output_path: "",
    timings: {},
    extra,
    annotations: { favorite: false, note: "" },
  };
}

function _canonicalTimings() {
  return {
    end_to_end_total_ms: 4523,
    studio_queue_ms: 210,
    workflow_validation_ms: 85,
    model_load_ms: 120,
    clip_load_ms: 95,
    clip_encode_ms: 450,
    sampling_ms: 3200,
    vae_decode_ms: 280,
    image_io_ms: 60,
    remote_inference_total_ms: 4020,
    local_output_materialization_ms: 180,
    scheduler_execution_ms: 3500,
  };
}

function _syncHistoryOnTerminal(session, experiment, status) {
  const record = session.history.find((r) => r.experiment_id === experiment.experiment_id);
  if (!record) return;
  if (status === "completed" || status === "succeeded") {
    record.status = "completed";
    if (experiment.firstOutputFilename && !record.output_path) {
      record.output_path = experiment.firstOutputFilename;
    }
    if (experiment.firstPrimaryAssetId) {
      record.extra.primary_asset_id = experiment.firstPrimaryAssetId;
    }
    record.timings = _canonicalTimings();
    record.extra.output_paths = experiment.firstOutputFilename ? [experiment.firstOutputFilename] : [];
    record.extra.output_count = experiment.firstOutputFilename ? 1 : 0;
    record.completed_at = _now();
  } else if (status === "failed_fatal" || status === "error" || status === "failed") {
    record.status = "failed";
    record.completed_at = _now();
  } else if (status === "cancelled" || status === "stopped") {
    record.status = "cancelled";
    record.completed_at = _now();
  }
}

// ── Public: submissions ─────────────────────────────────────────────────

export function handleStudioRun(id, payload = {}) {
  const session = getSession(id);
  const { name, def } = _resolveScenario(session, "success");

  if (def.submit && def.submit.error) {
    // Validation / submission failure: still create the experiment record so
    // tests can inspect the journal experiment.error, but respond with the
    // error object (no runId/experimentId) exactly like the real backend.
    const experiment = _createExperiment(session, payload, def, "single");
    session.experiments.set(experiment.experiment_id, experiment);
    _setStatus(experiment, "error");
    return Object.assign({}, def.submit.error);
  }

  const experiment = _createExperiment(session, payload, def, "single");
  session.experiments.set(experiment.experiment_id, experiment);

  const record = _makeHistoryRecord(session, experiment, payload, def, "single");
  session.history.unshift(record);
  experiment._historyRecord = record;

  return {
    status: "ok",
    runId: experiment.run_id,
    experimentId: experiment.experiment_id,
    message: "Run started",
  };
}

export function handleStudioExperiment(id, payload = {}) {
  const session = getSession(id);
  const uniquePresetIds = [...new Set((payload.presetIds || []).filter(Boolean))];
  if (uniquePresetIds.length === 0) {
    return { status: "error", message: "At least one preset is required" };
  }
  const { name, def } = _resolveScenario(session, "experiment_two_cell");
  if (def.kind !== "experiment") {
    // A single-run scenario was selected but an experiment was submitted:
    // force a 2-cell experiment so the frontend always gets cellCount ≥ 2.
    def.cellCount = Math.max(2, Number(def.cellCount) || 2);
  }

  const experiment = _createExperiment(session, payload, def, "experiment");
  session.experiments.set(experiment.experiment_id, experiment);

  const record = _makeHistoryRecord(session, experiment, payload, def, "experiment");
  session.history.unshift(record);
  experiment._historyRecord = record;

  return {
    status: "ok",
    experimentId: experiment.experiment_id,
    cellCount: experiment.snapshot.total_cells,
    message: `Experiment started with ${experiment.snapshot.total_cells} cells`,
  };
}

// ── Public: experiment polling / control ────────────────────────────────

export function getExperimentStatus(id, experimentId) {
  const session = getSession(id);
  const experiment = session.experiments.get(experimentId);
  if (!experiment) {
    return { status: "error", message: "unknown experiment", _httpStatus: 404 };
  }

  experiment.pollCount += 1;
  // Apply any poll-triggered steps whose trigger count is now reached.
  const applicable = experiment.pollSteps.filter((p) => p.atPoll <= experiment.pollCount);
  if (applicable.length > 0) {
    experiment.pollSteps = experiment.pollSteps.filter((p) => p.atPoll > experiment.pollCount);
    for (const { step } of applicable) _applyStep(session, experiment, step);
  }

  const snapshot = Object.assign({}, experiment.snapshot, {
    counters: Object.assign({}, experiment.snapshot.counters),
  });
  const isTerminal = ["completed", "succeeded", "cancelled", "stopped", "failed_fatal", "error", "failed"].includes(snapshot.status);
  if (isTerminal) {
    snapshot.total_duration_ms = _terminalDuration(experiment);
  }
  return {
    status: "ok",
    definition: experiment.definition,
    snapshot,
    events: experiment.journal,
  };
}

function _terminalDuration(experiment) {
  const counters = experiment.snapshot.counters;
  const total = experiment.snapshot.total_cells || 1;
  if (experiment.snapshot.status === "completed" || experiment.snapshot.status === "succeeded") {
    return 4523 + (total - 1) * 200 + 300;
  }
  if (experiment.snapshot.status === "failed_fatal" || experiment.snapshot.status === "error" || experiment.snapshot.status === "failed") {
    return 1200 + (total - 1) * 100 + 200;
  }
  return 800 + total * 100;
}

export function stopExperiment(id, experimentId) {
  const session = getSession(id);
  const experiment = session.experiments.get(experimentId);
  if (!experiment) {
    return { status: "error", message: "unknown experiment", _httpStatus: 404 };
  }
  if (experiment.stopRequested) return { status: "ok", stopped: true };

  _clearExperimentTimers(experiment);
  experiment.stopRequested = true;

  const total = experiment.snapshot.total_cells || 0;
  const counters = experiment.snapshot.counters;
  const hasTerminal = experiment.journal.some((e) =>
    ["experiment.completed", "experiment.stopped", "experiment.cancelled", "experiment.failed_fatal"].includes(e.type)
  );

  if (!hasTerminal) {
    for (let i = 0; i < total; i++) {
      const ck = "cell_" + i;
      if (experiment.cellStates[ck]) continue;
      const ev = {
        type: "cell.interrupted",
        payload: {
          cell_key: ck,
          checkpoint_id: experiment.ctx["checkpoint_" + i] || _makeCheckpointId(),
          attempt_id: experiment.ctx["attempt_" + i] || _makeAttemptId(),
          reason: "cancelled",
        },
      };
      experiment.journal.push(ev);
      _trackCellEvent(experiment, ev);
    }
    const payload = {
      completed: counters.completed,
      failed: counters.failed,
      interrupted: counters.interrupted,
      total_cells: total,
    };
    experiment.journal.push({ type: "experiment.stopped", payload });
    _setStatus(experiment, "stopped");
    _queueTracker(session, experiment, {
      type: "experiment.event",
      detail: { type: "experiment.stopped", experiment_id: experiment.experiment_id },
    });
  }

  _syncHistoryOnTerminal(session, experiment, "stopped");
  return { status: "ok", stopped: true };
}

export function listExperiments(id) {
  const session = getSession(id);
  const experiments = [];
  for (const experiment of session.experiments.values()) {
    experiments.push({
      experiment_id: experiment.experiment_id,
      definition: experiment.definition,
      snapshot: Object.assign({}, experiment.snapshot, {
        counters: Object.assign({}, experiment.snapshot.counters),
      }),
    });
  }
  return { status: "ok", experiments };
}

// ── Public: history ─────────────────────────────────────────────────────

function _filterHistory(session, query) {
  let filtered = [...session.history]; // newest-first already
  const q = query || {};
  if (q.kind || q.type) {
    const kind = q.kind || q.type;
    filtered = filtered.filter((r) => r.kind === kind);
  }
  if (q.status) {
    filtered = filtered.filter((r) => r.status === q.status);
  }
  if (q.search) {
    const lower = String(q.search).toLowerCase();
    filtered = filtered.filter((r) =>
      String(r.prompt || "").toLowerCase().includes(lower) ||
      String(r.run_id || r.id || "").toLowerCase().includes(lower) ||
      String((r.extra && r.extra.studio_preset_label) || "").toLowerCase().includes(lower)
    );
  }
  if (q.favorite_only || q.favorite) {
    filtered = filtered.filter((r) => (r.annotations && r.annotations.favorite) === true);
  }
  if (q.preset) {
    filtered = filtered.filter((r) => (r.extra && r.extra.studio_preset_id) === q.preset);
  }
  if (q.feature) {
    filtered = filtered.filter((r) => (r.extra && r.extra.studio_feature_id) === q.feature);
  }
  if (q.date_from) {
    const from = Date.parse(q.date_from);
    if (!Number.isNaN(from)) filtered = filtered.filter((r) => Date.parse(r.started_at || r.created_at || 0) >= from);
  }
  if (q.date_to) {
    const to = Date.parse(q.date_to);
    if (!Number.isNaN(to)) filtered = filtered.filter((r) => Date.parse(r.started_at || r.created_at || 0) <= to);
  }
  if (q.has_image) {
    filtered = filtered.filter(_hasImage);
  }
  if (q.sort && q.sort !== "newest") {
    const sort = q.sort;
    if (sort === "oldest") filtered = filtered.slice().reverse();
    else if (sort === "fastest" || sort === "slowest") {
      const dir = sort === "fastest" ? 1 : -1;
      filtered = filtered.slice().sort((a, b) => dir * (_durationMs(a) - _durationMs(b)));
    } else if (sort === "preset_az" || sort === "preset_za") {
      const dir = sort === "preset_az" ? 1 : -1;
      filtered = filtered.slice().sort((a, b) =>
        dir * String(a.extra && a.extra.studio_preset_label || "").localeCompare(String(b.extra && b.extra.studio_preset_label || ""))
      );
    }
  }
  return filtered;
}

function _hasImage(r) {
  const extra = r.extra || {};
  return !!(extra.primary_asset_id || r.asset_id || extra.asset_id || r.output_path || extra.output_path || r.primary_image_path);
}

function _durationMs(r) {
  const extra = r.extra || {};
  const timings = r.timings || extra.timings || {};
  if (typeof r.duration_ms === "number") return r.duration_ms;
  if (typeof timings.end_to_end_total_ms === "number") return timings.end_to_end_total_ms;
  if (typeof timings.total_ms === "number") return timings.total_ms;
  return 0;
}

function _withDefaults(r) {
  return Object.assign({}, r, {
    output_saved: r.output_saved === true || (r.extra && r.extra.output_saved === true) || false,
    annotations: r.annotations || { favorite: false, note: "" },
  });
}

export function listHistory(id, params = {}) {
  const session = getSession(id);
  const filtered = _filterHistory(session, params);
  const page = Math.max(1, parseInt(params.page, 10) || 1);
  const pageSize = Math.max(1, parseInt(params.page_size, 10) || 50);
  const total = filtered.length;
  const items = filtered.slice((page - 1) * pageSize, page * pageSize).map(_withDefaults);
  return {
    status: "ok",
    items,
    page,
    page_size: pageSize,
    total,
    has_more: page * pageSize < total,
  };
}

export function listRunHistory(id, params = {}) {
  const session = getSession(id);
  const filtered = _filterHistory(session, params);
  const limit = Math.max(1, parseInt(params.limit, 10) || 200);
  const offset = Math.max(0, parseInt(params.offset, 10) || 0);
  const total = filtered.length;
  const runs = filtered.slice(offset, offset + limit).map(_withDefaults);
  return { status: "ok", runs, total, limit, offset };
}

export function updateAnnotations(id, runId, payload = {}) {
  const session = getSession(id);
  const record = session.history.find((r) => r.run_id === runId || r.id === runId);
  if (!record) return { status: "error", message: "not found", _httpStatus: 404 };
  if (!record.annotations) record.annotations = { favorite: false, note: "" };
  if (payload.favorite !== undefined) record.annotations.favorite = Boolean(payload.favorite);
  if (payload.note !== undefined) record.annotations.note = String(payload.note).slice(0, 2000);
  record.annotations.updated_at = _now();
  return { status: "ok", annotations: Object.assign({}, record.annotations) };
}

export function saveRunOutput(id, runId, payload = {}) {
  const session = getSession(id);
  const record = session.history.find((r) => r.run_id === runId || r.id === runId);
  if (!record) return { status: "error", message: "not found", _httpStatus: 404 };
  const outputIndex = payload.output_index != null ? payload.output_index : 0;
  record.output_saved = true;
  if (!record.extra) record.extra = {};
  record.extra.output_saved = true;
  record.extra.output_saved_at = _now();
  session.saveRequests.push({ run_id: record.run_id, output_index: outputIndex });
  return { status: "ok", saved: true, run_id: record.run_id, output_index: outputIndex };
}

// ── History V2 (deterministic production-shaped dataset) ─────────────────
//
// Session-scoped History V2 store: `session.historyV2` holds raw internal
// records (kind "generation" | "experiment").  Wire feed/detail shapes are
// derived on read so mutations (favorite/note/featured) reflect immediately.
// All timestamps derive from a fixed base — no Math.random()/Date.now() in
// record generation.

const V2_BASE_MS = Date.parse("2026-08-10T12:00:00.000Z");
const V2_WORKFLOWS = ["Portrait Pro", "Landscape Ultra", "Concept Lab"];
const V2_WORKFLOW_IDS = ["wf_portrait", "wf_landscape", "wf_concept"];
const V2_PRESETS = [
  { id: "preset_a", name: "Preset A" },
  { id: "preset_b", name: "Preset B" },
];
const V2_PROFILE_LEVELS = ["off", "summary", "detailed", "trace", "trace_verbose"];
const V2_PARAM_DEFAULTS = {
  seed: 1000, steps: 20, cfg: 7, guidance: 7, sampler: "euler",
  scheduler: "normal", denoise: 1, width: 1024, height: 1024,
};
// Terminal experiment statuses → completed_at is set (production routes.py:52-55).
const V2_TERMINAL_EXPERIMENT_STATUSES = [
  "completed", "failed", "completed_with_failures", "interrupted", "canceled", "stopped",
];
// UI status aliases → backend statuses, per kind (production routes.py:60-79).
const V2_GEN_STATUS_ALIASES = {
  success: ["completed"],
  completed: ["completed"],
  partial: ["completed"],
  running: ["running", "pending", "queued"],
  failed: ["failed"],
  canceled: ["canceled"],
  interrupted: ["interrupted"],
  completed_with_failures: [],
};
const V2_EXP_STATUS_ALIASES = {
  success: ["completed"],
  completed: ["completed"],
  partial: ["completed_with_failures"],
  running: ["running", "pending", "queued"],
  failed: ["failed"],
  canceled: ["canceled"],
  interrupted: ["interrupted"],
  completed_with_failures: ["completed_with_failures"],
};
const V2_TRUE_VALUES = new Set(["1", "true", "yes", "on"]);
const V2_FALSE_VALUES = new Set(["0", "false", "no", "off"]);

function _v2T(baseMs, offsetMin) {
  return new Date(baseMs + offsetMin * 60000).toISOString();
}

function _v2AssetUrl(aid) {
  return aid ? "/comfymodal/history-v2/assets/" + aid : "";
}

function _registerV2Asset(session, aid, managedPath = null) {
  if (!aid) return;
  session.assets.set(aid, _pngFor(aid));
  if (managedPath) session.assetOrigins.set(aid, managedPath);
}

function _parseV2Bool(value) {
  if (value == null) return null;
  const text = String(value).trim().toLowerCase();
  if (V2_TRUE_VALUES.has(text)) return true;
  if (V2_FALSE_VALUES.has(text)) return false;
  return null;
}

function _mapV2Statuses(kind, status, statuses) {
  const aliases = kind === "experiment" ? V2_EXP_STATUS_ALIASES : V2_GEN_STATUS_ALIASES;
  const had = status != null || (Array.isArray(statuses) && statuses.length > 0);
  const mapped = [];
  if (status != null) {
    const hit = aliases[status];
    mapped.push.apply(mapped, hit !== undefined ? hit : [status]);
  }
  for (const value of statuses || []) {
    const hit = aliases[value];
    mapped.push.apply(mapped, hit !== undefined ? hit : [value]);
  }
  return { mapped, had };
}

// ── Internal record builders (deterministic) ────────────────────────────

function _makeV2Generation(session, cfg) {
  const o = Object.assign({
    id: "gen_v2",
    status: "completed",
    workflow_id: "wf_portrait",
    workflow_name: "Portrait Pro",
    workflow_version: "wv_1",
    preset_id: "preset_a",
    preset_name: "Preset A",
    prompt: "",
    negative_prompt: "",
    createdAtMs: V2_BASE_MS,
    durationMs: null,
    favorite: false,
    note: "",
    modelNames: ["Krea Model"],
    outputs: [],      // [{ thumb, preview, original, originalFailed, originalFilename }]
    unregistered: [], // asset ids referenced but NOT registered (original-failure case)
    error: null,
    params: null,
    workflowJson: null,
    exportState: "none",
    attempts: null,       // optional exact production-shaped Attempt list
    remoteAssetIds: [],   // internal producer origins; never exposed on the wire
    featuredAssetId: null,
    previewCodec: null,
    previewQuality: null,
  }, cfg);
  const createdAt = new Date(o.createdAtMs).toISOString();
  const finishedAt = o.durationMs == null ? null : new Date(o.createdAtMs + o.durationMs).toISOString();
  const defaultAttempt = {
    run_id: "run_" + o.id,
    mode: o.status === "completed" ? "quality" : "fast",
    status: o.status,
    started_at: createdAt,
    finished_at: finishedAt,
    error: o.error || null,
    timing: o.status === "completed" && finishedAt
      ? _canonicalTimings()
      : (o.error ? { end_to_end_total_ms: 1200, sampling_ms: 900 } : null),
  };
  const attempts = Array.isArray(o.attempts)
    ? o.attempts.map((raw, i) => {
      const spec = raw && typeof raw === "object" ? raw : {};
      const status = spec.status || "queued";
      const startedAt = spec.started_at || _v2T(o.createdAtMs, i);
      const hasFinishedAt = Object.prototype.hasOwnProperty.call(spec, "finished_at");
      const finishedAtForAttempt = hasFinishedAt
        ? spec.finished_at
        : (status === "completed" || status === "failed" || status === "canceled" || status === "interrupted"
          ? _v2T(o.createdAtMs, i + 1)
          : null);
      const attempt = {
        run_id: spec.run_id || "run_" + o.id + "_a" + i,
        mode: spec.mode || "original",
        status,
        started_at: startedAt,
        finished_at: finishedAtForAttempt,
        error: spec.error || null,
        timing: spec.timing !== undefined
          ? spec.timing
          : (status === "completed" ? _canonicalTimings() : (spec.error ? { end_to_end_total_ms: 1200 } : null)),
      };
      if (spec.logical_output_key != null) attempt.logical_output_key = String(spec.logical_output_key);
      if (spec.codec != null) attempt.codec = String(spec.codec);
      if (spec.quality != null) attempt.quality = Number(spec.quality);
      return attempt;
    })
    : [defaultAttempt];
  const outputs = o.outputs.map((spec, i) => {
    const base = o.id + "_o" + i;
    const originalAssetIds = Array.isArray(spec.originalAssetIds)
      ? spec.originalAssetIds.slice()
      : (spec.original ? [base + "_orig"] : []);
    const thumb = spec.thumb ? base + "_thumb" : null;
    const preview = spec.preview ? base + "_preview" : null;
    const original = spec.preferredOriginalAssetId || originalAssetIds[originalAssetIds.length - 1] || null;
    const logicalOutputKey = spec.logicalOutputKey || o.id + "_o" + i;
    const attemptIds = Array.isArray(spec.attemptIds)
      ? spec.attemptIds.slice()
      : attempts.map((attempt) => attempt.run_id);
    const provenance = [];
    if (thumb) provenance.push({ asset_id: thumb, asset_type: "thumbnail", attempt_id: attemptIds[0] || null });
    if (preview) provenance.push({ asset_id: preview, asset_type: "preview", attempt_id: attemptIds[0] || null });
    originalAssetIds.forEach((assetId, originalIndex) => {
      provenance.push({
        asset_id: assetId,
        asset_type: "original",
        attempt_id: attemptIds[Math.min(originalIndex + 1, Math.max(0, attemptIds.length - 1))] || null,
      });
    });
    return {
      index: i,
      logical_output_key: logicalOutputKey,
      asset_id: original || preview || thumb,
      thumb_asset_id: thumb,
      preview_asset_id: preview,
      original_asset_id: original,
      original_asset_ids: originalAssetIds,
      attempt_ids: attemptIds,
      asset_provenance: provenance,
      preview_codec: preview ? (spec.previewCodec || o.previewCodec || "webp") : "",
      preview_quality: preview ? (spec.previewQuality != null ? spec.previewQuality : (o.previewQuality != null ? o.previewQuality : 70)) : null,
      original_failed: !!spec.originalFailed,
      original_filename: spec.originalFilename || null,
    };
  });
  const remoteAssetIds = new Set(o.remoteAssetIds || []);
  for (const out of outputs) {
    for (const aid of [out.thumb_asset_id, out.preview_asset_id, ...(out.original_asset_ids || [])]) {
      if (aid && o.unregistered.indexOf(aid) === -1) {
        const origin = remoteAssetIds.has(aid) ? "modal://phase-e/fake/" + aid : null;
        _registerV2Asset(session, aid, origin);
      }
    }
  }
  return {
    id: o.id,
    kind: "generation",
    status: o.status,
    workflow_id: o.workflow_id,
    workflow_name: o.workflow_name,
    workflow_version: o.workflow_version,
    preset_id: o.preset_id,
    preset_name: o.preset_name,
    prompt: o.prompt,
    negative_prompt: o.negative_prompt,
    created_at: createdAt,
    favorite: !!o.favorite,
    note: o.note,
    model_names: o.modelNames,
    outputs,
    featured_asset_id: o.featuredAssetId || null,
    preview_codec: o.previewCodec,
    preview_quality: o.previewQuality,
    attempts,
    // Feed-level duration (mirrors production's computed attempt duration;
    // used as the fastest/slowest sort key).
    duration_ms: o.durationMs == null ? null : o.durationMs,
    params: o.params || Object.assign({}, V2_PARAM_DEFAULTS),
    workflow_json: o.workflowJson,
    export_state: o.exportState,
  };
}

function _makeV2Experiment(session, cfg) {
  const o = Object.assign({
    id: "exp_v2",
    status: "completed",
    name: "Experiment",
    workflow: "Portrait Pro",
    preset: "preset_a",
    createdAtMs: V2_BASE_MS,
    updatedMs: null,
    favorite: false,
    note: "",
    axisLabels: { x: "seed", y: "steps" },
    cells: [], // [{ status, axisX, axisY, durationMs, error, thumb, preview, original, originalFailed, favorite }]
    modalOptions: null,
  }, cfg);
  const createdAt = new Date(o.createdAtMs).toISOString();
  const cells = o.cells.map((c, i) => {
    const key = o.id + "_cell_" + i;
    const base = o.id + "_c" + i;
    const thumb = c.thumb ? base + "_thumb" : null;
    const preview = c.preview ? base + "_preview" : null;
    const original = c.original ? base + "_orig" : null;
    _registerV2Asset(session, thumb);
    _registerV2Asset(session, preview);
    if (original && !c.originalFailed) _registerV2Asset(session, original);
    return {
      key,
      index: i,
      status: c.status || "pending",
      axis: { x: c.axisX || "", y: c.axisY || "" },
      error: c.error || null,
      generation_id: c.genId || null,
      thumb_asset_id: thumb,
      preview_asset_id: preview,
      original_asset_id: original,
      original_failed: !!c.originalFailed,
      duration_ms: c.durationMs != null ? c.durationMs : null,
      favorite: !!c.favorite,
    };
  });
  const cellDurations = cells
    .map((c) => c.duration_ms)
    .filter((d) => d != null);
  return {
    id: o.id,
    kind: "experiment",
    status: o.status,
    name: o.name,
    workflow: o.workflow,
    preset: o.preset,
    created_at: createdAt,
    updated_at: o.updatedMs ? new Date(o.updatedMs).toISOString() : createdAt,
    favorite: !!o.favorite,
    note: o.note,
    axis_labels: o.axisLabels,
    modal_options: o.modalOptions ? JSON.parse(JSON.stringify(o.modalOptions)) : null,
    true_cell_count: cells.length,
    cells,
    // Record-level duration (max completed-cell duration, deterministic);
    // used as the fastest/slowest sort key.  The feed item keeps its null
    // duration so experiment cards render exactly as before.
    duration_ms: cellDurations.length ? Math.max.apply(null, cellDurations) : null,
  };
}

function _modernHistoryRecord(exp) {
  const cells = exp.cells.map((cell) => {
    const axisKeys = Object.keys(cell.axis_values || {});
    const axisValues = cell.axis_values || {};
    return {
      key: cell.cell_id,
      index: cell.position,
      status: _modernCanonicalCellStatus(cell.status),
      axis: {
        x: axisKeys[0] != null ? String(axisValues[axisKeys[0]]) : "",
        y: axisKeys[1] != null ? String(axisValues[axisKeys[1]]) : "",
      },
      error: cell.error || null,
      generation_id: cell.generation_id || null,
      thumb_asset_id: null,
      preview_asset_id: null,
      original_asset_id: null,
      original_failed: false,
      duration_ms: cell.duration_ms != null ? cell.duration_ms : null,
      favorite: false,
    };
  });
  const first = exp.cells[0] || {};
  const definition = exp.definition || {};
  const workflow = (definition.workflows && definition.workflows[0]) || {};
  return {
    id: exp.experiment_id,
    kind: "experiment",
    status: _modernAggregateFromCounts(_modernCountsFromCells(exp.cells)),
    name: exp.name || "",
    workflow: first.workflow_name || workflow.workflow_name || first.workflow_id || workflow.workflow_id || "",
    preset: first.preset_name || workflow.preset_name || first.preset_id || workflow.preset_id || "",
    created_at: exp.created_at,
    updated_at: exp.updated_at || exp.created_at,
    favorite: !!exp.favorite,
    note: exp.note || "",
    axis_labels: definition.axis_labels || { x: "", y: "" },
    true_cell_count: cells.length,
    cells,
    duration_ms: null,
  };
}

function _historyV2Records(session) {
  return session.historyV2.concat([...session.modernExperiments.values()].map(_modernHistoryRecord));
}

// ── Default session seed (Task 3 requirement set) ───────────────────────

function _seedDefaultHistoryV2(session) {
  const records = [];
  const hour = 3600 * 1000;

  // 1/7. successful generation: preview + original, duration set
  records.push(_makeV2Generation(session, {
    id: "gen_ok", status: "completed",
    workflow_id: "wf_portrait", workflow_name: "Portrait Pro",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "successful portrait of a deterministic person",
    createdAtMs: V2_BASE_MS + 6 * hour, durationMs: 4523,
    outputs: [{ thumb: true, preview: true, original: true }],
  }));
  // 2. failed generation (error recorded)
  records.push(_makeV2Generation(session, {
    id: "gen_failed", status: "failed",
    workflow_id: "wf_landscape", workflow_name: "Landscape Ultra",
    preset_id: "preset_b", preset_name: "Preset B",
    prompt: "failed landscape render",
    createdAtMs: V2_BASE_MS + 5 * hour, durationMs: 1832,
    error: "Modal worker crashed: CUDA out of memory",
    outputs: [],
  }));
  // 3. canceled generation
  records.push(_makeV2Generation(session, {
    id: "gen_canceled", status: "canceled",
    workflow_id: "wf_concept", workflow_name: "Concept Lab",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "canceled concept sketch",
    createdAtMs: V2_BASE_MS + 4 * hour, durationMs: 976,
    outputs: [],
  }));
  // 4. interrupted generation (duration_ms null — missing-duration record)
  records.push(_makeV2Generation(session, {
    id: "gen_interrupted", status: "interrupted",
    workflow_id: "wf_portrait", workflow_name: "Portrait Pro",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "interrupted portrait run",
    createdAtMs: V2_BASE_MS + 3 * hour, durationMs: null,
    outputs: [],
  }));
  // 5. preview-only generation (preview output, NO original)
  records.push(_makeV2Generation(session, {
    id: "gen_preview_only", status: "completed",
    workflow_id: "wf_landscape", workflow_name: "Landscape Ultra",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "preview-only pass",
    createdAtMs: V2_BASE_MS + 2 * hour, durationMs: 2110,
    outputs: [{ thumb: true, preview: true }],
  }));
  // 6. preview success + original failure (original asset unregistered → 404)
  records.push(_makeV2Generation(session, {
    id: "gen_original_failed", status: "completed",
    workflow_id: "wf_concept", workflow_name: "Concept Lab",
    preset_id: "preset_b", preset_name: "Preset B",
    prompt: "preview succeeded, original failed",
    createdAtMs: V2_BASE_MS + 1 * hour, durationMs: 2890,
    outputs: [{ thumb: true, preview: true, original: true, originalFailed: true }],
    unregistered: ["gen_original_failed_o0_orig"],
  }));
  // 8. multi-output generation (3 outputs)
  records.push(_makeV2Generation(session, {
    id: "gen_multi", status: "completed",
    workflow_id: "wf_portrait", workflow_name: "Portrait Pro",
    preset_id: "preset_b", preset_name: "Preset B",
    prompt: "multi-output batch",
    createdAtMs: V2_BASE_MS, durationMs: 3620,
    outputs: [
      { thumb: true, preview: true, original: true },
      { thumb: true, preview: true, original: true },
      { thumb: true, preview: true, original: true },
    ],
  }));
  // 9. missing image (no outputs → has_image:false, "No image" fallback)
  records.push(_makeV2Generation(session, {
    id: "gen_no_image", status: "completed",
    workflow_id: "wf_landscape", workflow_name: "Landscape Ultra",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "missing image record",
    createdAtMs: V2_BASE_MS - 1 * hour, durationMs: 1500,
    outputs: [],
  }));
  // 10. duplicate filenames but DISTINCT asset ids
  records.push(_makeV2Generation(session, {
    id: "gen_dupe_names", status: "completed",
    workflow_id: "wf_concept", workflow_name: "Concept Lab",
    preset_id: "preset_a", preset_name: "Preset A",
    prompt: "duplicate filenames, distinct asset ids",
    createdAtMs: V2_BASE_MS - 2 * hour, durationMs: 2740,
    outputs: [
      { thumb: true, preview: true, original: true, originalFilename: "shared_out.png" },
      { thumb: true, preview: true, original: true, originalFilename: "shared_out.png" },
    ],
  }));

  // Bulk completed / running / interrupted generations for pagination.
  for (let i = 0; i < 30; i++) {
    let status = "completed";
    if (i >= 24 && i < 27) status = "running";
    if (i >= 27) status = "interrupted";
    const wf = V2_WORKFLOWS[i % 3];
    const preset = V2_PRESETS[i % 2];
    const hasImage = i % 2 === 0;
    const durationMs = status === "completed" ? 2500 + (i % 8) * 400 : null;
    records.push(_makeV2Generation(session, {
      id: "gen_v2_" + String(i).padStart(2, "0"),
      status,
      workflow_id: V2_WORKFLOW_IDS[i % 3], workflow_name: wf,
      preset_id: preset.id, preset_name: preset.name,
      prompt: "bulk deterministic generation #" + i + " — searchable text for feed tests",
      createdAtMs: V2_BASE_MS - (i + 3) * 37 * 60000,
      durationMs,
      favorite: i === 5,
      outputs: hasImage ? [{ thumb: true, preview: true, original: true }] : [],
    }));
  }

  // 11. experiment completed (all cells completed)
  records.push(_makeV2Experiment(session, {
    id: "exp_completed", status: "completed", name: "Seed Sweep — completed",
    workflow: "Portrait Pro", preset: "preset_a",
    createdAtMs: V2_BASE_MS + 3 * hour,
    updatedMs: V2_BASE_MS + 3 * hour + 4523,
    cells: [0, 1, 2, 3].map((i) => ({
      status: "completed", axisX: "111", axisY: "20",
      durationMs: 4000 + i * 120, thumb: true, preview: true, original: true,
    })),
  }));
  // 12. experiment completed_with_failures (some failed cells)
  records.push(_makeV2Experiment(session, {
    id: "exp_with_failures", status: "completed_with_failures", name: "Seed Sweep — partial",
    workflow: "Landscape Ultra", preset: "preset_b",
    createdAtMs: V2_BASE_MS + 2 * hour,
    updatedMs: V2_BASE_MS + 2 * hour + 5100,
    cells: [
      { status: "completed", axisX: "111", axisY: "20", durationMs: 4100, thumb: true, preview: true, original: true },
      { status: "completed", axisX: "222", axisY: "20", durationMs: 4250, thumb: true, preview: true, original: true },
      { status: "failed", axisX: "111", axisY: "24", error: "Cell failed: worker restart exceeded retry budget (3 tries)" },
      { status: "failed", axisX: "222", axisY: "24", error: "Cell failed: OOM" },
    ],
  }));
  // 13. experiment interrupted
  records.push(_makeV2Experiment(session, {
    id: "exp_interrupted", status: "interrupted", name: "Seed Sweep — interrupted",
    workflow: "Concept Lab", preset: "preset_a",
    createdAtMs: V2_BASE_MS + 1 * hour,
    updatedMs: V2_BASE_MS + 1 * hour + 3000,
    cells: [
      { status: "completed", axisX: "111", axisY: "20", durationMs: 4000, thumb: true, preview: true },
      { status: "completed", axisX: "222", axisY: "20", durationMs: 4100, thumb: true, preview: true },
      { status: "interrupted", axisX: "111", axisY: "24" },
      { status: "interrupted", axisX: "222", axisY: "24" },
    ],
  }));
  // 14. experiment canceled
  records.push(_makeV2Experiment(session, {
    id: "exp_canceled", status: "canceled", name: "Seed Sweep — canceled",
    workflow: "Portrait Pro", preset: "preset_b",
    createdAtMs: V2_BASE_MS,
    updatedMs: V2_BASE_MS + 1500,
    cells: [
      { status: "interrupted", axisX: "111", axisY: "20" },
      { status: "interrupted", axisX: "222", axisY: "20" },
      { status: "interrupted", axisX: "111", axisY: "24" },
      { status: "interrupted", axisX: "222", axisY: "24" },
    ],
  }));
  // 15. experiments with 1 / 2 / 3 / 4+ completed cells (cover pads to 4)
  records.push(_makeV2Experiment(session, {
    id: "exp_1", status: "completed", name: "Single-cell sweep",
    workflow: "Portrait Pro", preset: "preset_a",
    createdAtMs: V2_BASE_MS - 2 * hour, updatedMs: V2_BASE_MS - 2 * hour + 4523,
    cells: [{ status: "completed", axisX: "111", axisY: "20", durationMs: 4523, thumb: true, preview: true, original: true }],
  }));
  records.push(_makeV2Experiment(session, {
    id: "exp_2", status: "completed", name: "Two-cell sweep",
    workflow: "Landscape Ultra", preset: "preset_b",
    createdAtMs: V2_BASE_MS - 3 * hour, updatedMs: V2_BASE_MS - 3 * hour + 4600,
    cells: [
      { status: "completed", axisX: "111", axisY: "20", durationMs: 4100, thumb: true, preview: true, original: true },
      { status: "completed", axisX: "222", axisY: "20", durationMs: 4250, thumb: true, preview: true, original: true },
    ],
  }));
  records.push(_makeV2Experiment(session, {
    id: "exp_3", status: "completed", name: "Three-cell sweep",
    workflow: "Concept Lab", preset: "preset_a",
    createdAtMs: V2_BASE_MS - 4 * hour, updatedMs: V2_BASE_MS - 4 * hour + 4700,
    cells: [0, 1, 2].map((i) => ({
      status: "completed", axisX: "111", axisY: "20",
      durationMs: 4100 + i * 90, thumb: true, preview: true, original: true,
    })),
  }));
  // Running experiments for status variety.
  records.push(_makeV2Experiment(session, {
    id: "exp_running_1", status: "running", name: "Seed Sweep — running",
    workflow: "Landscape Ultra", preset: "preset_a",
    createdAtMs: V2_BASE_MS - 5 * hour,
    cells: [
      { status: "completed", axisX: "111", axisY: "20", durationMs: 4100, thumb: true, preview: true },
      { status: "running", axisX: "222", axisY: "20" },
      { status: "pending", axisX: "111", axisY: "24" },
      { status: "pending", axisX: "222", axisY: "24" },
    ],
  }));
  records.push(_makeV2Experiment(session, {
    id: "exp_running_2", status: "running", name: "Two-cell running sweep",
    workflow: "Portrait Pro", preset: "preset_b",
    createdAtMs: V2_BASE_MS - 6 * hour,
    cells: [
      { status: "completed", axisX: "111", axisY: "20", durationMs: 4100, thumb: true, preview: true },
      { status: "pending", axisX: "222", axisY: "20" },
    ],
  }));

  session.historyV2 = records;
}

// ── Large History V2 seed (history_v2_large scenario) ───────────────────

function _buildV2Seed(session, key) {
  if (key === "phase_e") {
    const t = (runId, mode, status, offset, error = null) => ({
      run_id: runId,
      mode,
      status,
      started_at: _v2T(V2_BASE_MS + 14 * 3600000, offset),
      finished_at: status === "queued" || status === "running" ? null : _v2T(V2_BASE_MS + 14 * 3600000, offset + 1),
      error,
      timing: status === "completed" ? _canonicalTimings() : (error ? { end_to_end_total_ms: 1200 } : null),
    });
    const records = [];

    // A completed Preview Attempt with no Original Attempt yet.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_preview_only",
      status: "completed",
      prompt: "phase e preview only",
      createdAtMs: V2_BASE_MS + 14 * 3600000,
      params: {},
      attempts: [t("run_phase_e_preview_only_preview", "preview", "completed", 0)],
      outputs: [{ thumb: true, preview: true }],
    }));

    // Preview remains available after an Original Attempt fails before an
    // Original asset is produced.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_preview_failed_original",
      status: "completed",
      prompt: "phase e preview with failed original",
      createdAtMs: V2_BASE_MS + 13 * 3600000,
      params: {},
      attempts: [
        t("run_phase_e_failed_preview", "preview", "completed", 0),
        t("run_phase_e_failed_original", "original", "failed", 2, "Original replay failed"),
      ],
      outputs: [{ thumb: true, preview: true, originalFailed: true }],
    }));

    // Preview and a later successful Original are both retained; Original is
    // the preferred output because it is present in the output projection.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_preview_original",
      status: "completed",
      prompt: "phase e preview and original",
      createdAtMs: V2_BASE_MS + 12 * 3600000,
      attempts: [
        t("run_phase_e_success_preview", "preview", "completed", 0),
        t("run_phase_e_success_original", "original", "completed", 2),
      ],
      outputs: [{ thumb: true, preview: true, original: true }],
    }));

    // A successful Original remains available after a later failed rerender.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_rerender_failed",
      status: "completed",
      prompt: "phase e original rerender failed",
      createdAtMs: V2_BASE_MS + 11 * 3600000,
      attempts: [
        t("run_phase_e_rerender_preview", "preview", "completed", 0),
        t("run_phase_e_rerender_original", "original", "completed", 2),
        t("run_phase_e_rerender_retry", "original", "failed", 4, "Rerender timed out"),
      ],
      outputs: [{ thumb: true, preview: true, original: true }],
    }));

    // The internal origin is modal://, but the browser only sees and requests
    // the stable managed History URL. The fake server returns deterministic
    // bytes for that URL.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_remote_original",
      status: "completed",
      prompt: "phase e remote original",
      createdAtMs: V2_BASE_MS + 10 * 3600000,
      attempts: [t("run_phase_e_remote_original", "original", "completed", 0)],
      outputs: [{ original: true }],
      remoteAssetIds: ["gen_phase_e_remote_original_o0_orig"],
    }));

    // Sparse records intentionally have no output or parameter rows. This is
    // a pending frontend proof until nullable detail sections are guarded.
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_sparse_failed",
      status: "failed",
      prompt: "",
      createdAtMs: V2_BASE_MS + 9 * 3600000,
      params: {},
      error: "sparse phase e failure",
      attempts: [t("run_phase_e_sparse_failed", "original", "failed", 0, "sparse phase e failure")],
      outputs: [],
    }));
    records.push(_makeV2Generation(session, {
      id: "gen_phase_e_sparse_interrupted",
      status: "interrupted",
      prompt: "",
      createdAtMs: V2_BASE_MS + 8 * 3600000,
      params: {},
      attempts: [t("run_phase_e_sparse_interrupted", "preview", "interrupted", 0)],
      outputs: [],
    }));

    // Experiment cells retain stable Generation identities and Preview-only
    // output projections. This is fake acceptance state, not scheduler proof.
    records.push(_makeV2Experiment(session, {
      id: "exp_phase_e_preview",
      status: "completed",
      name: "Phase E Preview Sweep",
      workflow: "Portrait Pro",
      preset: "preset_a",
      createdAtMs: V2_BASE_MS + 7 * 3600000,
      updatedMs: V2_BASE_MS + 7 * 3600000 + 4523,
      cells: [0, 1].map((i) => ({
        status: "completed",
        axisX: String(111 + i),
        axisY: "20",
        durationMs: 4200 + i * 100,
        genId: "gen_exp_phase_e_preview_" + i,
        thumb: true,
        preview: true,
      })),
    }));
    return records;
  }
  if (key === "phase_e_wave2") {
    const records = [];
    const addGeneration = (cfg) => records.push(_makeV2Generation(session, cfg));
    const previewAttempt = (runId, logicalKey) => ({
      run_id: runId,
      mode: "preview",
      status: "completed",
      logical_output_key: logicalKey,
      codec: "webp",
      quality: 70,
      started_at: _v2T(V2_BASE_MS + 16 * 3600000, 0),
      finished_at: _v2T(V2_BASE_MS + 16 * 3600000, 1),
      timing: _canonicalTimings(),
    });
    const originalAttempt = (runId, logicalKey, offset, error = null) => ({
      run_id: runId,
      mode: "original",
      status: error ? "failed" : "completed",
      logical_output_key: logicalKey,
      started_at: _v2T(V2_BASE_MS + 16 * 3600000, offset),
      finished_at: _v2T(V2_BASE_MS + 16 * 3600000, offset + 1),
      error,
      timing: error ? { end_to_end_total_ms: 1200 } : _canonicalTimings(),
    });

    const logicalKey = "gen_wave2_logical_o0";
    addGeneration({
      id: "gen_phase_e_wave2_logical",
      status: "completed",
      createdAtMs: V2_BASE_MS + 16 * 3600000,
      attempts: [
        previewAttempt("run_wave2_preview", logicalKey),
        originalAttempt("run_wave2_original_old", logicalKey, 2),
        originalAttempt("run_wave2_original_new", logicalKey, 4),
      ],
      outputs: [{
        thumb: true,
        preview: true,
        logicalOutputKey: logicalKey,
        originalAssetIds: ["gen_wave2_logical_old_orig", "gen_wave2_logical_new_orig"],
        attemptIds: ["run_wave2_preview", "run_wave2_original_old", "run_wave2_original_new"],
      }],
      previewCodec: "webp",
      previewQuality: 70,
    });

    const retryKey = "gen_wave2_retry_o0";
    addGeneration({
      id: "gen_phase_e_wave2_retry",
      status: "completed",
      createdAtMs: V2_BASE_MS + 15 * 3600000,
      attempts: [
        previewAttempt("run_wave2_retry_preview", retryKey),
        originalAttempt("run_wave2_retry_original_failed", retryKey, 2, "Original upload failed"),
        originalAttempt("run_wave2_retry_original", retryKey, 4),
      ],
      outputs: [{
        thumb: true,
        preview: true,
        logicalOutputKey: retryKey,
        originalAssetIds: ["gen_wave2_retry_orig"],
        attemptIds: ["run_wave2_retry_preview", "run_wave2_retry_original_failed", "run_wave2_retry_original"],
      }],
      previewCodec: "webp",
      previewQuality: 70,
    });

    const twoKeys = ["gen_wave2_two_o0", "gen_wave2_two_o1"];
    addGeneration({
      id: "gen_phase_e_wave2_two",
      status: "completed",
      createdAtMs: V2_BASE_MS + 14 * 3600000,
      attempts: [
        previewAttempt("run_wave2_two_preview_o0", twoKeys[0]),
        originalAttempt("run_wave2_two_original_o0", twoKeys[0], 2),
        previewAttempt("run_wave2_two_preview_o1", twoKeys[1]),
      ],
      outputs: [
        {
          thumb: true,
          preview: true,
          logicalOutputKey: twoKeys[0],
          originalAssetIds: ["gen_wave2_two_o0_orig"],
          attemptIds: ["run_wave2_two_preview_o0", "run_wave2_two_original_o0"],
        },
        {
          thumb: true,
          preview: true,
          logicalOutputKey: twoKeys[1],
          originalAssetIds: [],
          attemptIds: ["run_wave2_two_preview_o1"],
        },
      ],
      previewCodec: "webp",
      previewQuality: 70,
    });

    const featuredVariants = [
      {
        variant: "thumbnail",
        featuredAssetId: "gen_phase_e_wave2_featured_thumbnail_o0_thumb",
      },
      {
        variant: "preview",
        featuredAssetId: "gen_phase_e_wave2_featured_preview_o1_preview",
      },
      {
        variant: "older_original",
        featuredAssetId: "gen_wave2_featured_older_original_o1_old_orig",
      },
    ];
    for (const [variantIndex, { variant, featuredAssetId }] of featuredVariants.entries()) {
      const id = "gen_phase_e_wave2_featured_" + variant;
      const key0 = id + "_o0";
      const key1 = id + "_o1";
      addGeneration({
        id,
        status: "completed",
        createdAtMs: V2_BASE_MS + (13 - variantIndex) * 3600000,
        featuredAssetId,
        attempts: [
          previewAttempt("run_wave2_featured_preview_" + variant, key0),
          originalAttempt("run_wave2_featured_original_old_" + variant, key1, 2),
          originalAttempt("run_wave2_featured_original_new_" + variant, key1, 4),
        ],
        outputs: [
          { thumb: true, preview: true, logicalOutputKey: key0, originalAssetIds: [id + "_o0_orig"], attemptIds: ["run_wave2_featured_preview_" + variant] },
          { thumb: true, preview: true, logicalOutputKey: key1, originalAssetIds: [
            variant === "older_original" ? "gen_wave2_featured_older_original_o1_old_orig" : id + "_o1_old_orig",
            variant === "older_original" ? "gen_wave2_featured_older_original_o1_new_orig" : id + "_o1_new_orig",
          ], attemptIds: [
            "run_wave2_featured_preview_" + variant,
            "run_wave2_featured_original_old_" + variant,
            "run_wave2_featured_original_new_" + variant,
          ] },
        ],
        previewCodec: "webp",
        previewQuality: 70,
      });
    }

    const previewOnlyKey = "gen_wave2_preview_only_o0";
    addGeneration({
      id: "gen_phase_e_wave2_preview_only",
      status: "completed",
      createdAtMs: V2_BASE_MS + 10 * 3600000,
      attempts: [previewAttempt("run_wave2_preview_only", previewOnlyKey)],
      outputs: [{
        thumb: false,
        preview: true,
        logicalOutputKey: previewOnlyKey,
        originalAssetIds: [],
        attemptIds: ["run_wave2_preview_only"],
      }],
      previewCodec: "webp",
      previewQuality: 70,
    });

    const remoteKey = "gen_wave2_remote_only_o0";
    addGeneration({
      id: "gen_phase_e_wave2_remote_only",
      status: "completed",
      createdAtMs: V2_BASE_MS + 9 * 3600000,
      attempts: [originalAttempt("run_wave2_remote_original", remoteKey, 0)],
      outputs: [{
        thumb: false,
        preview: false,
        logicalOutputKey: remoteKey,
        originalAssetIds: ["gen_wave2_remote_only_orig"],
        attemptIds: ["run_wave2_remote_original"],
      }],
      remoteAssetIds: ["gen_wave2_remote_only_orig"],
    });

    records.push(_makeV2Experiment(session, {
      id: "exp_phase_e_wave2",
      status: "completed",
      name: "Phase E Wave 2 Preview Sweep",
      workflow: "Portrait Pro",
      preset: "preset_a",
      createdAtMs: V2_BASE_MS + 8 * 3600000,
      modalOptions: { enabled: true, codec: "webp", quality: 70 },
      cells: [0, 1].map((i) => ({
        status: "completed",
        axisX: String(111 + i),
        axisY: "20",
        durationMs: 4200 + i * 100,
        genId: "gen_phase_e_wave2_cell_" + i,
        thumb: true,
        preview: true,
      })),
    }));
    return records;
  }
  if (key !== "large") return [];
  const records = [];
  for (let i = 0; i < 60; i++) {
    let status = "completed";
    if (i % 10 === 3) status = "failed";
    else if (i % 10 === 6) status = "running";
    else if (i % 10 === 8) status = "interrupted";
    const wf = V2_WORKFLOWS[i % 3];
    const preset = V2_PRESETS[i % 2];
    const hasImage = i % 3 !== 2; // some missing-image records
    const previewOnly = i % 7 === 5; // preview-only subset
    const durationMs = status === "completed" ? 3200 + (i % 9) * 400 : null;
    records.push(_makeV2Generation(session, {
      id: "gen_v2_lg_" + String(i).padStart(3, "0"),
      status,
      workflow_id: V2_WORKFLOW_IDS[i % 3], workflow_name: wf,
      preset_id: preset.id, preset_name: preset.name,
      prompt: "large seed generation #" + i + " — " + wf,
      createdAtMs: V2_BASE_MS - i * 25 * 60000,
      durationMs,
      favorite: i % 13 === 0,
      error: status === "failed" ? "simulated failure for record " + i : null,
      outputs: !hasImage
        ? []
        : (previewOnly ? [{ thumb: true, preview: true }] : [{ thumb: true, preview: true, original: true }]),
    }));
  }
  for (let j = 0; j < 20; j++) {
    let status = "completed";
    if (j % 10 === 3) status = "running";
    else if (j % 10 === 5) status = "interrupted";
    else if (j % 10 === 7) status = "canceled";
    else if (j % 10 === 0 && j > 0) status = "completed_with_failures";
    const cellCount = 1 + (j % 4);
    const wf = V2_WORKFLOWS[j % 3];
    const preset = V2_PRESETS[j % 2];
    const cells = [];
    for (let c = 0; c < cellCount; c++) {
      if (status === "completed") {
        cells.push({ status: "completed", axisX: "111", axisY: "20", durationMs: 3800 + c * 110, thumb: true, preview: true, original: true });
      } else if (status === "completed_with_failures") {
        cells.push(c === 0
          ? { status: "failed", axisX: "111", axisY: "20", error: "cell failure in large seed" }
          : { status: "completed", axisX: "111", axisY: "20", durationMs: 3900, thumb: true, preview: true, original: true });
      } else if (status === "interrupted") {
        cells.push(c === 0
          ? { status: "interrupted", axisX: "111", axisY: "20" }
          : { status: "completed", axisX: "111", axisY: "20", durationMs: 3900, thumb: true, preview: true, original: true });
      } else if (status === "canceled") {
        cells.push({ status: "interrupted", axisX: "111", axisY: "20" });
      } else { // running
        cells.push(c === 0
          ? { status: "running", axisX: "111", axisY: "20" }
          : { status: "pending", axisX: "111", axisY: "20" });
      }
    }
    records.push(_makeV2Experiment(session, {
      id: "exp_v2_lg_" + String(j).padStart(3, "0"),
      status,
      name: "Large sweep #" + j,
      workflow: wf, preset: preset.id,
      createdAtMs: V2_BASE_MS - (j + 1) * 95 * 60000,
      updatedMs: V2_TERMINAL_EXPERIMENT_STATUSES.indexOf(status) !== -1
        ? V2_BASE_MS - (j + 1) * 95 * 60000 + 4800
        : null,
      favorite: j % 7 === 0,
      cells,
    }));
  }
  return records;
}

// ── Feed / detail builders (wire shapes) ────────────────────────────────

function _featuredIndex(rec) {
  const fid = rec.featured_asset_id;
  if (!fid) return 0;
  for (const out of rec.outputs || []) {
    if (out.asset_id === fid) return out.index;
    if (out.thumb_asset_id === fid || out.preview_asset_id === fid) return out.index;
    if ((out.original_asset_ids || []).indexOf(fid) !== -1) return out.index;
    if ((out.asset_provenance || []).some((entry) => entry && entry.asset_id === fid)) return out.index;
  }
  return 0;
}

function _generationFeedItem(rec) {
  const attempts = rec.attempts || [];
  let completedAt = null;
  let durationMs = null;
  const finished = attempts.filter((a) => a.finished_at).map((a) => a.finished_at);
  if (finished.length) completedAt = finished.reduce((m, v) => (v > m ? v : m), "");
  const pairs = attempts.filter((a) => a.started_at && a.finished_at);
  if (pairs.length) {
    let minS = Infinity;
    let maxF = -Infinity;
    for (const a of pairs) {
      const s = Date.parse(a.started_at);
      const f = Date.parse(a.finished_at);
      if (s < minS) minS = s;
      if (f > maxF) maxF = f;
    }
    durationMs = maxF - minS;
  }
  const outputs = (rec.outputs || []).map((o) => ({
    index: o.index,
    logical_output_key: o.logical_output_key,
    asset_id: o.asset_id,
    thumb_url: _v2AssetUrl(o.thumb_asset_id),
    preview_url: _v2AssetUrl(o.preview_asset_id),
    original_url: _v2AssetUrl(o.original_asset_id),
    original_urls: (o.original_asset_ids || []).map(_v2AssetUrl),
    attempt_ids: (o.attempt_ids || []).slice(),
    asset_provenance: (o.asset_provenance || []).map((entry) => Object.assign({}, entry, { url: _v2AssetUrl(entry.asset_id) })),
    preview_codec: o.preview_codec || "",
    preview_quality: o.preview_quality != null ? o.preview_quality : null,
    original_failed: !!o.original_failed,
    status: "success",
  }));
  const hasPreview = (rec.outputs || []).some((o) => o.preview_asset_id);
  const hasOriginal = (rec.outputs || []).some((o) => o.original_asset_id);
  const hasImage = (rec.outputs || []).some((o) => o.thumb_asset_id || o.preview_asset_id || o.original_asset_id);
  return {
    id: rec.id,
    kind: "generation",
    status: rec.status,
    workflow_id: rec.workflow_id,
    workflow_name: rec.workflow_name,
    workflow_version: rec.workflow_version,
    preset_id: rec.preset_id,
    preset: rec.preset_name || rec.preset_id || "",
    preset_name: rec.preset_name,
    prompt: rec.prompt || "",
    negative_prompt: rec.negative_prompt || "",
    created_at: rec.created_at,
    started_at: rec.created_at,
    completed_at: completedAt,
    duration_ms: durationMs,
    favorite: !!rec.favorite,
    note: rec.note || "",
    tags: [],
    models: (rec.model_names || []).map((name) => ({ name })),
    output_count: outputs.length,
    has_image: hasImage,
    preview_only: !!(hasPreview && !hasOriginal),
    original_available: hasOriginal,
    featured_output_index: _featuredIndex(rec),
    featured_asset_id: rec.featured_asset_id || null,
    preview_codec: rec.preview_codec || null,
    preview_quality: rec.preview_quality != null ? rec.preview_quality : null,
    outputs,
  };
}

function _cellThumbUrl(cell) {
  return _v2AssetUrl(cell.thumb_asset_id) || _v2AssetUrl(cell.preview_asset_id) || "";
}

function _experimentFeedItem(rec) {
  const cells = rec.cells || [];
  const status = rec.status;
  const isTerminal = V2_TERMINAL_EXPERIMENT_STATUSES.indexOf(status) !== -1;
  const cover = cells.slice(0, 4).map((c) => ({
    key: c.key,
    thumb_url: _cellThumbUrl(c),
    status: c.status,
  }));
  return {
    id: rec.id,
    kind: "experiment",
    status,
    name: rec.name || "",
    workflow: rec.workflow || "",
    preset: rec.preset || "",
    created_at: rec.created_at,
    started_at: rec.created_at,
    completed_at: isTerminal ? rec.updated_at : null,
    duration_ms: null,
    favorite: !!rec.favorite,
    note: rec.note || "",
    tags: [],
    models: [],
    true_cell_count: cells.length,
    result_count: cells.filter((c) => c.status === "completed").length,
    failed_count: cells.filter((c) => c.status === "failed").length,
    interrupted_count: cells.filter((c) => c.status === "interrupted" || c.status === "canceled").length,
    axis_labels: {
      x: (rec.axis_labels && rec.axis_labels.x) || "",
      y: (rec.axis_labels && rec.axis_labels.y) || "",
    },
    cells: cover,
  };
}

function _generationDetailItem(rec) {
  const item = _generationFeedItem(rec);
  item.attempts = (rec.attempts || []).map((a) => {
    // Mirror production _attempt_dict (routes.py:533-549): duration_ms is
    // computed from started_at/finished_at, not stored on the attempt.
    let attemptDuration = null;
    if (a.started_at && a.finished_at) {
      const startMs = Date.parse(a.started_at);
      const finishMs = Date.parse(a.finished_at);
      if (!Number.isNaN(startMs) && !Number.isNaN(finishMs)) attemptDuration = finishMs - startMs;
    }
    const detailAttempt = {
      run_id: a.run_id,
      mode: a.mode,
      status: a.status,
      started_at: a.started_at,
      finished_at: a.finished_at,
      duration_ms: attemptDuration,
      error: a.error || null,
      timing: a.timing || null,
    };
    if (a.logical_output_key != null) detailAttempt.logical_output_key = a.logical_output_key;
    if (a.codec != null) detailAttempt.codec = a.codec;
    if (a.quality != null) detailAttempt.quality = a.quality;
    return detailAttempt;
  });
  item.errors = (rec.attempts || [])
    .filter((a) => a.error)
    .map((a) => ({ code: "attempt_failed", message: a.error }));
  item.export_state = rec.export_state || "none";
  const params = {};
  for (const key of ["seed", "steps", "cfg", "guidance", "sampler", "scheduler", "denoise", "width", "height"]) {
    if (rec.params && rec.params[key] !== undefined && rec.params[key] !== null) params[key] = rec.params[key];
  }
  item.params = params;
  const candidates = (rec.attempts || [])
    .filter((a) => a.timing && a.finished_at)
    .sort((a, b) => (a.finished_at < b.finished_at ? -1 : 1));
  item.timing = candidates.length ? candidates[candidates.length - 1].timing : null;
  item.workflow_json = rec.workflow_json || null;
  return item;
}

function _experimentDetailItem(rec) {
  const item = _experimentFeedItem(rec);
  item.cells = (rec.cells || []).map((c) => ({
    key: c.key,
    index: c.index != null ? c.index : 0,
    status: c.status,
    axis: { x: c.axis.x, y: c.axis.y },
    error: c.error || null,
    generation_id: c.generation_id || null,
    thumb_url: _v2AssetUrl(c.thumb_asset_id),
    preview_url: _v2AssetUrl(c.preview_asset_id),
    original_url: _v2AssetUrl(c.original_asset_id),
    original_failed: !!c.original_failed,
    duration_ms: c.duration_ms != null ? c.duration_ms : null,
    favorite: !!c.favorite,
  }));
  const cover = (rec.cells || []).slice(0, 4).map((c) => ({
    thumb_url: _cellThumbUrl(c),
    cellKey: c.key,
  }));
  while (cover.length < 4) cover.push(null);
  item.cover = cover;
  if (rec.modal_options) item.modal_options = JSON.parse(JSON.stringify(rec.modal_options));
  return item;
}

// ── Cursor encode / decode (production mirror) ──────────────────────────

function _encodeKeyset(createdAt, id, key) {
  return Buffer.from(
    JSON.stringify({ k: key == null ? null : key, created_at: createdAt, id }),
    "utf8"
  ).toString("base64url");
}

function _decodeKeyset(cursor) {
  try {
    const payload = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
    const createdAt = String(payload.created_at);
    const id = String(payload.id);
    if (!createdAt || !id) return { ok: false };
    return { ok: true, k: payload.k == null ? null : payload.k, created_at: createdAt, id };
  } catch {
    return { ok: false };
  }
}

// V2 stateless mixed cursor: {"v": 2, "g", "e"} (production routes.py:569-581).
const _MIXED_CURSOR_VERSION = 2;

function _encodeMixedCursor(gCursor, eCursor) {
  return Buffer.from(
    JSON.stringify({ v: _MIXED_CURSOR_VERSION, g: gCursor, e: eCursor }),
    "utf8"
  ).toString("base64url");
}

function _decodeMixedCursor(cursor) {
  try {
    const payload = JSON.parse(Buffer.from(cursor, "base64url").toString("utf8"));
    if (!payload || typeof payload !== "object") return { ok: false };
    const version = payload.v;
    if (version == null) {
      // Legacy V1 payload {g, e, gs, es}: tolerated on decode like production
      // (routes.py:604-611); the broken skip counts are validated but ignored
      // and every emitted cursor upgrades to V2.
      const gs = parseInt(payload.gs, 10);
      const es = parseInt(payload.es, 10);
      if (Number.isNaN(gs) || Number.isNaN(es) || gs < 0 || es < 0) return { ok: false };
      return {
        ok: true,
        g: payload.g == null ? null : String(payload.g),
        e: payload.e == null ? null : String(payload.e),
      };
    }
    if (version !== _MIXED_CURSOR_VERSION) return { ok: false };
    if (payload.g != null && typeof payload.g !== "string") return { ok: false };
    if (payload.e != null && typeof payload.e !== "string") return { ok: false };
    return {
      ok: true,
      g: payload.g == null ? null : String(payload.g),
      e: payload.e == null ? null : String(payload.e),
    };
  } catch {
    return { ok: false };
  }
}

// ── Sorting / filtering ─────────────────────────────────────────────────

function _cmpV2Records(a, b, order) {
  const ta = _v2SortTuple(a, order);
  const tb = _v2SortTuple(b, order);
  if (_tupleLess(ta, tb)) return -1;
  if (_tupleLess(tb, ta)) return 1;
  return 0;
}

// Mirror production _sort_tuple (routes.py:505-542): the total order used both
// for per-stream sorting and for the two-pointer mixed merge.
function _v2DescStringKey(s) {
  const out = [];
  for (const ch of String(s || "")) out.push(-ch.charCodeAt(0));
  return out;
}

function _v2SortTuple(item, order) {
  const ts = Date.parse(item.created_at || "");
  const isExp = item.kind === "experiment" ? 1 : 0;
  const id = item.id || "";
  if (order === "newest") return [-ts, isExp, id.split("").reverse().join("")];
  if (order === "oldest") return [ts, isExp, id];
  const durRaw = item.duration_ms;
  const durNone = durRaw == null ? 1 : 0;
  const dur = Number(durRaw || 0);
  if (order === "fastest") return [durNone, dur, ts, id];
  if (order === "slowest") return [durNone, -dur, ts, id];
  if (order === "workflow_asc" || order === "workflow_desc") {
    // Generation items sort by workflow_id, experiment items by name
    // (production routes.py:532-541 — the repo's "sensible equivalent").
    const wfKey = isExp ? String(item.name || "") : String(item.workflow_id || "");
    const wfNone = wfKey ? 0 : 1;
    if (order === "workflow_asc") return [wfNone, wfKey.toLowerCase(), ts, id];
    return [wfNone, _v2DescStringKey(wfKey), ts, id];
  }
  throw new Error("unknown order: " + order);
}

function _tupleLess(a, b) {
  const len = Math.max(a.length, b.length);
  for (let k = 0; k < len; k++) {
    const x = a[k];
    const y = b[k];
    if (Array.isArray(x) && Array.isArray(y)) {
      // A differing nested key DECIDES the comparison (like a first differing
      // scalar element); only equal nested keys fall through to later elements.
      if (_tupleLess(x, y)) return true;
      if (_tupleLess(y, x)) return false;
      continue;
    }
    if (x === y) continue;
    if (x == null) return true;
    if (y == null) return false;
    return x < y;
  }
  return false;
}

function _mergeV2Streams(genItems, expItems, order) {
  const merged = [];
  let i = 0;
  let j = 0;
  while (i < genItems.length && j < expItems.length) {
    if (_tupleLess(_v2SortTuple(genItems[i], order), _v2SortTuple(expItems[j], order))) {
      merged.push(genItems[i]);
      i += 1;
    } else {
      merged.push(expItems[j]);
      j += 1;
    }
  }
  while (i < genItems.length) merged.push(genItems[i++]);
  while (j < expItems.length) merged.push(expItems[j++]);
  return merged;
}

// Sort key embedded in a keyset cursor, mirroring production
// _cursor_sort_key (repository.py:1226-1246).
function _v2CursorSortKey(order, rec) {
  if (order === "fastest" || order === "slowest") {
    return rec.duration_ms == null ? null : rec.duration_ms;
  }
  if (order === "workflow_asc" || order === "workflow_desc") {
    return rec.kind === "experiment" ? rec.name || "" : rec.workflow_id || "";
  }
  return null;
}

// Rebuild the total-order tuple of the row a keyset cursor points at.
function _v2CursorTuple(order, kind, k, created_at, id) {
  const isExp = kind === "experiment" ? 1 : 0;
  const ts = Date.parse(created_at || "");
  if (order === "newest") return [-ts, isExp, String(id).split("").reverse().join("")];
  if (order === "oldest") return [ts, isExp, String(id)];
  const durNone = k == null ? 1 : 0;
  const dur = Number(k || 0);
  if (order === "fastest") return [durNone, dur, ts, String(id)];
  if (order === "slowest") return [durNone, -dur, ts, String(id)];
  if (order === "workflow_asc" || order === "workflow_desc") {
    const wfKey = k == null ? "" : String(k);
    const wfNone = wfKey ? 0 : 1;
    if (order === "workflow_asc") return [wfNone, wfKey.toLowerCase(), ts, String(id)];
    return [wfNone, _v2DescStringKey(wfKey), ts, String(id)];
  }
  throw new Error("unknown order: " + order);
}

function _v2KeysetAfter(records, decoded, order) {
  const kind = records.length ? records[0].kind : "generation";
  const cursorTuple = _v2CursorTuple(order, kind, decoded.k, decoded.created_at, decoded.id);
  return records.filter((r) => _tupleLess(cursorTuple, _v2SortTuple(r, order)));
}

// Re-anchor a stream's keyset cursor after its last EMITTED item; a stream
// that emitted nothing keeps its previous position so its un-emitted tail is
// re-fetched and re-merged on the next page (production routes.py:619-633).
function _v2StreamCursorAfter(emitted, order, previous) {
  if (!emitted.length) return previous;
  const last = emitted[emitted.length - 1];
  return _encodeKeyset(last.created_at, last.id, _v2CursorSortKey(order, last));
}

function _genMatchesV2(rec, f) {
  if (f.statuses && f.statuses.length && f.statuses.indexOf(rec.status) === -1) return false;
  if (f.workflow_id && rec.workflow_id !== f.workflow_id) return false;
  if (f.preset_id && rec.preset_id !== f.preset_id) return false;
  if (f.favorite != null && !!rec.favorite !== f.favorite) return false;
  if (f.date_from && rec.created_at < f.date_from) return false;
  if (f.date_to && rec.created_at > f.date_to) return false;
  if (f.has_preview && !(rec.outputs || []).some((o) => o.preview_asset_id)) return false;
  if (f.has_original && !(rec.outputs || []).some((o) => o.original_asset_id)) return false;
  if (f.preview_only) {
    const hasPreview = (rec.outputs || []).some((o) => o.preview_asset_id);
    const hasOriginal = (rec.outputs || []).some((o) => o.original_asset_id);
    if (!(hasPreview && !hasOriginal)) return false;
  }
  if (f.interrupted && !(rec.attempts || []).some((a) => a.status === "interrupted")) return false;
  if (f.failed_or_canceled && !(rec.attempts || []).some((a) => a.status === "failed" || a.status === "canceled")) return false;
  if (f.model_name) {
    const hay = JSON.stringify(rec.model_names || []).toLowerCase();
    if (hay.indexOf('"' + f.model_name.toLowerCase() + '"') === -1) return false;
  }
  if (f.has_image && !(rec.outputs || []).some((o) => o.thumb_asset_id || o.preview_asset_id || o.original_asset_id)) return false;
  if (f.search) {
    const s = String(f.search).toLowerCase();
    const fields = [rec.id, rec.workflow_id, rec.preset_id, rec.preset_name, rec.prompt, rec.negative_prompt, rec.note];
    if (!fields.some((v) => String(v || "").toLowerCase().indexOf(s) !== -1)) return false;
  }
  return true;
}

function _expMatchesV2(rec, f) {
  if (f.statuses && f.statuses.length && f.statuses.indexOf(rec.status) === -1) return false;
  if (f.date_from && rec.created_at < f.date_from) return false;
  if (f.date_to && rec.created_at > f.date_to) return false;
  if (f.search) {
    const s = String(f.search).toLowerCase();
    const fields = [rec.id, rec.name, rec.workflow, rec.preset];
    if (!fields.some((v) => String(v || "").toLowerCase().indexOf(s) !== -1)) return false;
  }
  return true;
}

// ── Stream query (keyset) ───────────────────────────────────────────────

function _queryV2Stream(records, matchFn, cursor, fetchLimit, order) {
  const matched = records.filter(matchFn).sort((a, b) => _cmpV2Records(a, b, order));
  let window = matched;
  if (cursor) {
    const decoded = _decodeKeyset(cursor);
    if (!decoded.ok) throw _v2Error("invalid cursor", 400);
    window = _v2KeysetAfter(matched, decoded, order);
  }
  return {
    items: window.slice(0, fetchLimit),
    has_more: window.length > fetchLimit,
    total: matched.length,
  };
}

function _v2Error(message, status) {
  return { status: "error", message, _httpStatus: status };
}

// ── Public: feed ────────────────────────────────────────────────────────

export function listHistoryV2(id, params = {}) {
  const session = getSession(id);
  if (session.historyV2Fail && session.historyV2Fail.feed) {
    return _v2Error("simulated feed failure", 500);
  }
  const kind = params.kind || "mixed";
  if (kind !== "generation" && kind !== "experiment" && kind !== "mixed") return _v2Error("invalid kind", 400);

  const limitRaw = params.limit;
  let limit = 24;
  if (limitRaw != null && limitRaw !== "") {
    const trimmed = String(limitRaw).trim();
    if (!/^\d+$/.test(trimmed)) return _v2Error("limit must be an integer between 1 and 200", 400);
    const n = parseInt(trimmed, 10);
    if (n < 1 || n > 200) return _v2Error("limit must be between 1 and 200", 400);
    limit = n;
  }

  const order = params.order || "newest";
  // All six production orders (routes.py:794, repository _ORDERS).
  if (["newest", "oldest", "fastest", "slowest", "workflow_asc", "workflow_desc"].indexOf(order) === -1) {
    return _v2Error("invalid order", 400);
  }

  const status = params.status || null;
  const statuses = (params.statuses || "").split(",").filter(Boolean);
  const workflowId = params.workflow_id || params.workflow || null;
  const presetId = params.preset_id || params.preset || null;
  const favorite = _parseV2Bool(params.favorite);
  const dateFrom = params.date_from || null;
  const dateTo = params.date_to || null;
  const previewOnly = _parseV2Bool(params.preview_only);
  let hasPreview = _parseV2Bool(params.has_preview);
  let hasOriginal = _parseV2Bool(params.has_original);
  if (hasOriginal == null) hasOriginal = _parseV2Bool(params.original_available);
  const interrupted = _parseV2Bool(params.interrupted);
  const failedOrCanceled = _parseV2Bool(params.failed_or_canceled);
  const model = params.model || null;
  const hasImage = _parseV2Bool(params.has_image);
  const search = params.search || null;

  // Generation filters include every supported filter; experiments only
  // receive search/date_from/date_to (production routes.py:690-709).
  const genFilters = {
    statuses: null, workflow_id: workflowId, preset_id: presetId, favorite,
    date_from: dateFrom, date_to: dateTo, has_preview: hasPreview, has_original: hasOriginal,
    preview_only: previewOnly, interrupted, failed_or_canceled: failedOrCanceled,
    model_name: model, has_image: hasImage, search,
  };
  const expFilters = { statuses: null, date_from: dateFrom, date_to: dateTo, search };

  const genMapped = _mapV2Statuses("generation", status, statuses);
  const expMapped = _mapV2Statuses("experiment", status, statuses);
  genFilters.statuses = genMapped.mapped;
  expFilters.statuses = expMapped.mapped;

  let items;
  let nextCursor = null;
  let total;

  if (kind === "generation" || kind === "experiment") {
    const mapped = kind === "generation" ? genMapped : expMapped;
    if (mapped.had && !mapped.mapped.length) {
      items = [];
      total = 0;
    } else {
      const filters = kind === "generation" ? genFilters : expFilters;
      const cursor = params.cursor || null;
      try {
        const res = _queryV2Stream(
          _historyV2Records(session).filter((r) => r.kind === kind),
          (r) => (kind === "generation" ? _genMatchesV2(r, filters) : _expMatchesV2(r, filters)),
          cursor,
          limit,
          order
        );
        items = res.items.map((r) => (kind === "generation" ? _generationFeedItem(r) : _experimentFeedItem(r)));
        const last = res.items[res.items.length - 1];
        nextCursor = res.has_more && res.items.length
          ? _encodeKeyset(last.created_at, last.id, _v2CursorSortKey(order, last))
          : null;
        total = res.total;
      } catch (err) {
        if (err && err._httpStatus) return err;
        throw err;
      }
    }
  } else {
    // Mixed two-stream merge with the production V2 cursor shape
    // {"v":2,"g","e"} (stateless keysets; no skip counts).
    try {
      let gCursor = null;
      let eCursor = null;
      if (params.cursor) {
        const decoded = _decodeMixedCursor(params.cursor);
        if (!decoded.ok) return _v2Error("invalid cursor", 400);
        gCursor = decoded.g;
        eCursor = decoded.e;
      }

      const records = _historyV2Records(session);
      const genRecords = records.filter((r) => r.kind === "generation");
      const expRecords = records.filter((r) => r.kind === "experiment");

      if (genMapped.had && !genMapped.mapped.length) {
        gCursor = null;
      }
      if (expMapped.had && !expMapped.mapped.length) {
        eCursor = null;
      }

      let genRes;
      let expRes;
      if (genMapped.had && !genMapped.mapped.length) {
        genRes = { items: [], has_more: false, total: 0 };
      } else {
        genRes = _queryV2Stream(genRecords, (r) => _genMatchesV2(r, genFilters), gCursor, limit, order);
      }
      if (expMapped.had && !expMapped.mapped.length) {
        expRes = { items: [], has_more: false, total: 0 };
      } else {
        expRes = _queryV2Stream(expRecords, (r) => _expMatchesV2(r, expFilters), eCursor, limit, order);
      }

      const merged = _mergeV2Streams(genRes.items, expRes.items, order);
      const emitted = merged.slice(0, limit);
      const genEmitted = emitted.filter((m) => m.kind === "generation");
      const expEmitted = emitted.filter((m) => m.kind === "experiment");

      // Re-anchor each stream after its last emitted item; a stream that
      // emitted nothing keeps its previous position (its un-emitted tail is
      // re-fetched and re-merged on the next page — nothing is skipped).
      const newGCursor = _v2StreamCursorAfter(genEmitted, order, gCursor);
      const newECursor = _v2StreamCursorAfter(expEmitted, order, eCursor);

      const gMore = (genRes.items.length - genEmitted.length) > 0 || genRes.has_more;
      const eMore = (expRes.items.length - expEmitted.length) > 0 || expRes.has_more;
      if (gMore || eMore) {
        nextCursor = _encodeMixedCursor(newGCursor, newECursor);
      }
      total = genRes.total + expRes.total;
      items = emitted.map((m) => (m.kind === "generation" ? _generationFeedItem(m) : _experimentFeedItem(m)));
    } catch (err) {
      if (err && err._httpStatus) return err;
      throw err;
    }
  }

  const response = {
    status: "ok",
    items,
    next_cursor: nextCursor,
    limit,
    total,
    has_more: nextCursor !== null,
  };
  if (params._timing === "1") {
    response._diagnostic_timing_ms = { params: 0, query: 0, enrich: 0, total: 0 };
  }
  return response;
}

// ── Public: detail ──────────────────────────────────────────────────────

export function getHistoryV2Generation(id, genId) {
  const session = getSession(id);
  const rec = session.historyV2.find((r) => r.kind === "generation" && r.id === genId);
  if (!rec) return _v2Error("generation not found", 404);
  return { status: "ok", item: _generationDetailItem(rec) };
}

export function getHistoryV2Experiment(id, expId) {
  const session = getSession(id);
  const rec = _historyV2Records(session).find((r) => r.kind === "experiment" && r.id === expId);
  if (!rec) return _v2Error("experiment not found", 404);
  return { status: "ok", item: _experimentDetailItem(rec) };
}

// ── Public: mutations (mutate in place → persist for session lifetime) ──

function _v2BodyIsValid(body) {
  return !!(body && typeof body === "object" && !Array.isArray(body) && body._raw === undefined);
}

export function setHistoryV2Favorite(id, kind, recordId, body) {
  const session = getSession(id);
  if (!_v2BodyIsValid(body)) return _v2Error("Invalid JSON body", 400);
  const favorite = body.favorite;
  if (typeof favorite !== "boolean") return _v2Error("favorite must be a boolean", 400);
  const rec = session.historyV2.find((r) => r.kind === kind && r.id === recordId);
  if (!rec && kind === "experiment") {
    const modern = session.modernExperiments.get(recordId);
    if (modern) {
      modern.favorite = favorite;
      return { status: "ok", favorite };
    }
  }
  if (!rec) {
    return _v2Error(kind === "generation" ? "generation not found" : "experiment not found", 404);
  }
  rec.favorite = favorite;
  return { status: "ok", favorite };
}

export function setHistoryV2Note(id, kind, recordId, body) {
  const session = getSession(id);
  if (!_v2BodyIsValid(body)) return _v2Error("Invalid JSON body", 400);
  const note = body.note;
  if (typeof note !== "string") return _v2Error("note must be a string", 400);
  if (note.length > 2000) return _v2Error("note exceeds 2000 characters (legacy limit)", 400);
  const rec = session.historyV2.find((r) => r.kind === kind && r.id === recordId);
  if (!rec && kind === "experiment") {
    const modern = session.modernExperiments.get(recordId);
    if (modern) {
      modern.note = note;
      return { status: "ok", note };
    }
  }
  if (!rec) {
    return _v2Error(kind === "generation" ? "generation not found" : "experiment not found", 404);
  }
  rec.note = note;
  return { status: "ok", note };
}

export function setHistoryV2Featured(id, genId, body) {
  const session = getSession(id);
  if (!_v2BodyIsValid(body)) return _v2Error("Invalid JSON body", 400);
  const rec = session.historyV2.find((r) => r.kind === "generation" && r.id === genId);
  if (!rec) return _v2Error("generation not found", 404);

  let assetId = null;
  if (body.output_index !== undefined) {
    const index = body.output_index;
    if (typeof index !== "number" || !Number.isInteger(index)) return _v2Error("invalid output_index", 400);
    const outputs = rec.outputs || [];
    if (index < 0 || index >= outputs.length) return _v2Error("invalid output_index", 400);
    assetId = outputs[index].asset_id;
  } else if (body.asset_id !== undefined) {
    assetId = body.asset_id;
    if (typeof assetId !== "string" || !assetId) return _v2Error("invalid asset_id", 400);
    const owned = (rec.outputs || []).some((o) =>
      o.asset_id === assetId || o.thumb_asset_id === assetId || o.preview_asset_id === assetId || o.original_asset_id === assetId
    );
    if (!owned) return _v2Error("invalid asset_id", 400);
  } else {
    return _v2Error("missing output_index or asset_id", 400);
  }
  if (assetId == null) return _v2Error("missing output_index or asset_id", 400);
  rec.featured_asset_id = assetId;
  return { status: "ok", featured_asset_id: assetId };
}

// ── Public: deploy status / profile level ───────────────────────────────

export function getDeployStatus(id) {
  getSession(id);
  return {
    state: "ready",
    message: "Fake deployment ready",
    warning: false,
    details: "",
    deploy_state: {
      path: ".deploy_state.json",
      legacy_path: "",
      loaded: true,
      source: "json",
      parse_error: "",
      comfyapp_version: null,
      custom_nodes_fingerprint: null,
      deployed_at: null,
      deployment_command: null,
    },
    has_log: true,
  };
}

export function getProfileLevel(id) {
  const session = getSession(id);
  return { status: "ok", level: session.profileLevel, effective: session.profileLevel };
}

export function setProfileLevel(id, body) {
  const session = getSession(id);
  if (!_v2BodyIsValid(body)) return _v2Error("Invalid JSON body", 400);
  const raw = body.level;
  const level = typeof raw === "string" ? raw.trim().toLowerCase() : "";
  if (V2_PROFILE_LEVELS.indexOf(level) === -1) return _v2Error("invalid level", 400);
  session.profileLevel = level;
  return { status: "ok", level };
}

// ── Public: test control (simulated feed failure) ───────────────────────

export function setHistoryV2FailMode(id, mode) {
  const session = getSession(id);
  if (mode == null || mode === "") {
    session.historyV2Fail = {};
    return { status: "ok", mode: null };
  }
  if (mode === "feed") {
    session.historyV2Fail = { feed: true };
    return { status: "ok", mode };
  }
  return { status: "error", message: `unknown fail mode "${mode}"` };
}

// ── Modern Experiment V2 (D5) ──────────────────────────────────────────────
//
// Deterministic in-memory parity for the production modern contract
// (experiment_modern_routes.py / PHASE_D_INTERFACE_FREEZE.md §11).  The D5
// request shape is the frontend's cell-plan payload:
//
//     { experiment_id, name, definition }
//
// where `definition` carries workflows/axes/prompts. Cell statuses
// use the canonical vocabulary only — queued/running/completed/failed/canceled/
// interrupted — and the aggregate is the frozen truth table (any queued or
// running → "running", else interrupted → canceled → failed →
// completed_with_failures → completed).  `partial` is never emitted.
// Cells stay queued on create (one queued attempt each, like production's
// create_modern_matrix); tests advance cell statuses through the
// /__comfymodal_test/modern-experiment-state test-control endpoint.

const MODERN_CELL_TERMINAL = new Set(["completed", "failed", "canceled", "interrupted"]);
const MODERN_CELL_VALID = new Set(["queued", "running", "completed", "failed", "canceled", "interrupted"]);

function _modernCanonicalCellStatus(status) {
  if (status === "pending" || status === "queued") return "queued";
  if (MODERN_CELL_VALID.has(status)) return status;
  return "queued";
}

function _modernAggregateFromCounts(counts) {
  if (counts.queued > 0 || counts.running > 0) return "running";
  if (counts.interrupted > 0) return "interrupted";
  if (counts.canceled > 0) return "canceled";
  if (counts.failed > 0) return "completed_with_failures";
  return "completed";
}

function _modernCountsFromCells(cells) {
  const counts = { queued: 0, running: 0, completed: 0, failed: 0, canceled: 0, interrupted: 0 };
  for (const cell of cells) counts[_modernCanonicalCellStatus(cell.status)] += 1;
  return counts;
}

// Flat status projection (production §11.2): fixed position order, canonical
// per-cell statuses, current queued/running attempt id (null when terminal).
function _modernStatusDetail(exp) {
  const cells = exp.cells.slice().sort((a, b) => a.position - b.position);
  const counts = _modernCountsFromCells(cells);
  const activeAttemptIds = [];
  const workflowIds = new Set();
  const workflowVersionIds = new Set();
  const presetIds = new Set();
  const cellRecords = [];
  for (const c of cells) {
    if (c.active_attempt_id) activeAttemptIds.push(c.active_attempt_id);
    if (c.workflow_id) workflowIds.add(c.workflow_id);
    if (c.workflow_version_id) workflowVersionIds.add(c.workflow_version_id);
    if (c.preset_id) presetIds.add(c.preset_id);
    const axes = Array.isArray(c.axes) && c.axes.length
      ? c.axes
      : Object.keys(c.axis_values || {});
    cellRecords.push({
      cell_id: c.cell_id,
      position: c.position,
      status: _modernCanonicalCellStatus(c.status),
      active_attempt_id: c.active_attempt_id,
      generation_id: c.generation_id,
      workflow_id: c.workflow_id,
      workflow_version_id: c.workflow_version_id,
      preset_id: c.preset_id,
      workflow_name: c.workflow_name || "",
      preset_name: c.preset_name || "",
      axis_labels: Object.assign({}, c.axis_labels || {}),
      axis_values: Object.assign({}, c.axis_values || {}),
      axes,
      error: c.error != null ? c.error : null,
      duration_ms: c.duration_ms != null ? c.duration_ms : null,
      thumbnail_url: c.thumbnail_url || "",
      output_reference: c.output_reference != null ? c.output_reference : null,
    });
  }
  return {
    status: "ok",
    experiment_id: exp.experiment_id,
    name: exp.name || "",
    aggregate_status: _modernAggregateFromCounts(counts),
    total: cells.length,
    counts,
    active_attempt_ids: activeAttemptIds,
    workflow_ids: [...workflowIds].sort(),
    workflow_version_ids: [...workflowVersionIds].sort(),
    preset_ids: [...presetIds].sort(),
    cells: cellRecords,
  };
}

// Flat action envelope (production _ok_status_response): the status projection
// minus the heavy cells list.
function _modernFlatEnvelope(exp) {
  const d = _modernStatusDetail(exp);
  return {
    status: "ok",
    experiment_id: exp.experiment_id,
    aggregate_status: d.aggregate_status,
    total: d.total,
    counts: d.counts,
  };
}

function _modernNotFound(experimentId) {
  return {
    status: "error",
    message: "experiment not found",
    code: "EXPERIMENT_NOT_FOUND",
    experiment_id: experimentId,
    _httpStatus: 404,
  };
}

function _modernExperimentError(message, code, status, extra) {
  const err = { status: "error", message, code, _httpStatus: status };
  if (extra) Object.assign(err, extra);
  return err;
}

const MODERN_BANNED_CREATE_KEYS = [
  "concurrency",
  "cells",
  "raw",
  "immutable_request",
  "execution_plan",
  "workflow_snapshot",
];

function _validateModernCreateBody(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { error: "request body must be a JSON object", errors: [{ field: "body" }] };
  }
  for (const key of MODERN_BANNED_CREATE_KEYS) {
    if (Object.prototype.hasOwnProperty.call(body, key)) {
      return {
        error: `top-level ${key} is not accepted by the modern create contract`,
        errors: [{ field: key }],
      };
    }
  }
  if (typeof body.experiment_id !== "string" || body.experiment_id.trim() === "") {
    return { error: "experiment_id is required", errors: [{ field: "experiment_id" }] };
  }
  if (body.name != null && typeof body.name !== "string") {
    return { error: "name must be a string", errors: [{ field: "name" }] };
  }
  if (!body.definition || typeof body.definition !== "object" || Array.isArray(body.definition)) {
    return { error: "definition must be an object", errors: [{ field: "definition" }] };
  }
  return null;
}

// Derive a small fixed ordered cell list from the D5 definition. Cartesian
// product of the axis values is capped for determinism; an axis-less
// definition is the single-cell matrix accepted by the production planner.
function _modernDeriveCellsFromDefinition(body, experimentId) {
  const definition = (body && body.definition && typeof body.definition === "object")
    ? body.definition
    : {};
  const workflows = Array.isArray(definition.workflows) ? definition.workflows : [];
  const wf = (workflows[0] && typeof workflows[0] === "object") ? workflows[0] : {};
  const axes = definition.axes && typeof definition.axes === "object" ? definition.axes : {};
  const enabled = [];
  for (const controlId of Object.keys(axes)) {
    const axisDef = axes[controlId];
    if (axisDef && Array.isArray(axisDef.values) && axisDef.values.length > 0) {
      enabled.push({ controlId, values: axisDef.values });
    }
  }
  let combos = [{}];
  for (const axis of enabled) {
    const next = [];
    for (const combo of combos) {
      for (const value of axis.values) {
        next.push(Object.assign({}, combo, { [axis.controlId]: value }));
        if (next.length >= 16) break;
      }
      if (next.length >= 16) break;
    }
    combos = next;
    if (combos.length >= 16) break;
  }
  return combos.map((combo, i) => {
    const axisLabels = {};
    const axisValues = {};
    for (const controlId of Object.keys(combo)) {
      axisLabels[controlId] = String(combo[controlId]);
      axisValues[controlId] = combo[controlId];
    }
    return {
      cell_id: "cell_" + i,
      generation_id: "gen_" + experimentId + "_" + i,
      workflow_id: wf.workflow_id || "",
      workflow_version_id: wf.workflow_version_id || "",
      preset_id: wf.preset_id || "",
      workflow_name: wf.workflow_name || "",
      preset_name: wf.preset_name || "",
      axis_labels: axisLabels,
      axis_values: axisValues,
    };
  });
}

function _modernCellRecord(rawCell, index, definition, experimentId) {
  const wf = (definition && definition.workflows && Array.isArray(definition.workflows) && definition.workflows[0])
    ? definition.workflows[0]
    : {};
  const axisLabels = rawCell && rawCell.axis_labels && typeof rawCell.axis_labels === "object"
    ? rawCell.axis_labels : {};
  const axisValues = rawCell && rawCell.axis_values && typeof rawCell.axis_values === "object"
    ? rawCell.axis_values : {};
  return {
    cell_id: String((rawCell && rawCell.cell_id) || "cell_" + index),
    position: index,
    status: "queued",
    active_attempt_id: _makeRunId(),
    generation_id: String((rawCell && rawCell.generation_id) || "gen_" + experimentId + "_" + index),
    workflow_id: String((rawCell && rawCell.workflow_id) || wf.workflow_id || ""),
    workflow_version_id: String((rawCell && rawCell.workflow_version_id) || wf.workflow_version_id || ""),
    preset_id: String((rawCell && rawCell.preset_id) || wf.preset_id || ""),
    workflow_name: String((rawCell && rawCell.workflow_name) || wf.workflow_name || ""),
    preset_name: String((rawCell && rawCell.preset_name) || wf.preset_name || ""),
    axis_labels: Object.assign({}, axisLabels),
    axis_values: Object.assign({}, axisValues),
    axes: Array.isArray(rawCell && rawCell.axes) ? rawCell.axes.slice() : Object.keys(axisValues),
    error: (rawCell && rawCell.error != null) ? rawCell.error : null,
    duration_ms: (rawCell && rawCell.duration_ms != null) ? rawCell.duration_ms : null,
    thumbnail_url: "",
    output_reference: null,
  };
}

// ── Public: modern experiment submissions / polling / control ─────────────

export function handleModernExperimentCreate(id, payload = {}) {
  const session = getSession(id);
  const body = payload && typeof payload === "object" ? payload : {};
  const validation = _validateModernCreateBody(body);
  if (validation) {
    return _modernExperimentError(validation.error, "INVALID_DEFINITION", 400, {
      errors: validation.errors,
    });
  }
  const experimentId = String(body.experiment_id || "").trim();
  if (!experimentId) {
    return _modernExperimentError("experiment_id is required", "INVALID_DEFINITION", 400);
  }
  if (session.modernExperiments.has(experimentId)) {
    return _modernExperimentError("experiment already exists", "EXPERIMENT_EXISTS", 409, { experiment_id: experimentId });
  }
  const definition = body.definition && typeof body.definition === "object" ? body.definition : {};
  const rawCells = _modernDeriveCellsFromDefinition(body, experimentId);
  const exp = {
    experiment_id: experimentId,
    name: body.name != null ? String(body.name) : "",
    definition,
    cells: rawCells.map((rc, i) => _modernCellRecord(rc, i, definition, experimentId)),
    created_at: _now(),
    updated_at: _now(),
    favorite: false,
    note: "",
  };
  session.modernExperiments.set(experimentId, exp);
  const d = _modernStatusDetail(exp);
  return {
    status: "ok",
    experiment_id: experimentId,
    started: true,
    aggregate_status: d.aggregate_status,
    total: d.total,
    counts: d.counts,
  };
}

export function getModernExperimentStatus(id, experimentId) {
  const session = getSession(id);
  const exp = session.modernExperiments.get(experimentId);
  if (!exp) return _modernNotFound(experimentId);
  return _modernStatusDetail(exp);
}

export function cancelModernExperiment(id, experimentId) {
  const session = getSession(id);
  const exp = session.modernExperiments.get(experimentId);
  if (!exp) return _modernNotFound(experimentId);

  const canonical = exp.cells.map((c) => _modernCanonicalCellStatus(c.status));
  const allTerminal = canonical.every((s) => MODERN_CELL_TERMINAL.has(s));
  if (allTerminal) {
    if (canonical.every((s) => s === "canceled")) {
      // Repeated cancel of an already-canceled experiment is idempotent 200.
      return { status: "ok", experiment_id: experimentId, message: "experiment is already canceled" };
    }
    return _modernExperimentError(
      "experiment is terminal and cannot be cancelled",
      "EXPERIMENT_TERMINAL",
      409,
      { experiment_id: experimentId }
    );
  }

  // Fake semantics: a remote-cancel primitive is always available, so both
  // queued (cancel without submission) and running cells cancel truthfully.
  // Terminal cells (completed/failed/interrupted) are never rewritten.
  for (const cell of exp.cells) {
    const s = _modernCanonicalCellStatus(cell.status);
    if (s === "queued" || s === "running") {
      cell.status = "canceled";
      cell.active_attempt_id = null;
    }
  }
  return _modernFlatEnvelope(exp);
}

export function resumeModernExperiment(id, experimentId) {
  const session = getSession(id);
  const exp = session.modernExperiments.get(experimentId);
  if (!exp) return _modernNotFound(experimentId);

  const interrupted = [];
  const queued = [];
  for (const cell of exp.cells) {
    const s = _modernCanonicalCellStatus(cell.status);
    if (s === "interrupted") interrupted.push(cell);
    else if (s === "queued") queued.push(cell);
  }
  if (interrupted.length === 0 && queued.length === 0) {
    return _modernExperimentError(
      "no resumable cells",
      "NO_RESUMABLE_CELLS",
      409,
      { experiment_id: experimentId }
    );
  }

  // Interrupted cells get a FRESH queued attempt (append-only attempt history);
  // never-started queued cells keep their existing queued attempt.  Failed,
  // completed, and canceled cells are skipped.
  const created = [];
  for (const cell of interrupted) {
    const attemptId = _makeRunId();
    created.push({ cell_id: cell.cell_id, run_id: attemptId });
    cell.active_attempt_id = attemptId;
    cell.status = "queued";
    cell.error = null;
  }

  const envelope = _modernFlatEnvelope(exp);
  return Object.assign({}, envelope, {
    resumed: created.length,
    created_attempts: created,
    resumable_cells: interrupted.concat(queued).map((c) => c.cell_id),
  });
}

export function retryModernCell(id, experimentId, cellId) {
  const session = getSession(id);
  const exp = session.modernExperiments.get(experimentId);
  if (!exp) return _modernNotFound(experimentId);

  const cell = exp.cells.find((c) => c.cell_id === cellId);
  if (!cell) {
    return _modernExperimentError("cell not found", "CELL_NOT_FOUND", 404, {
      experiment_id: experimentId,
      cell_id: cellId,
    });
  }
  if (_modernCanonicalCellStatus(cell.status) !== "failed") {
    return _modernExperimentError("only a failed cell can be retried", "CELL_NOT_FAILED", 409, {
      experiment_id: experimentId,
      cell_id: cellId,
    });
  }

  // New attempt under the same cell/generation (identity preserved), fresh run id.
  const runId = _makeRunId();
  cell.active_attempt_id = runId;
  cell.status = "queued";
  cell.error = null;
  cell.duration_ms = null;

  const envelope = _modernFlatEnvelope(exp);
  return Object.assign({}, envelope, {
    cell_id: cellId,
    run_id: runId,
    retried: true,
  });
}

// ── Public: test control (deterministic mixed-state setup) ────────────────

export function setModernExperimentState(id, body = {}) {
  const session = getSession(id);
  const experimentId = body && body.experiment_id != null ? String(body.experiment_id) : "";
  const exp = experimentId ? session.modernExperiments.get(experimentId) : null;
  if (!exp) return _modernNotFound(experimentId);

  const changes = Array.isArray(body.cells) ? body.cells : [];
  if (changes.length === 0) {
    return _modernExperimentError("no cells supplied", "INVALID_REQUEST", 400, { experiment_id: experimentId });
  }
  for (const change of changes) {
    const rawStatus = change && change.status;
    if (rawStatus == null || !MODERN_CELL_VALID.has(rawStatus)) {
      return _modernExperimentError(
        `invalid status "${rawStatus}"`,
        "INVALID_STATUS",
        400,
        { experiment_id: experimentId }
      );
    }
  }
  for (const change of changes) {
    const cellId = change && change.cell_id != null ? String(change.cell_id) : "";
    const cell = exp.cells.find((c) => c.cell_id === cellId);
    if (!cell) continue;
    const status = _modernCanonicalCellStatus(change.status);
    cell.status = status;
    if (MODERN_CELL_TERMINAL.has(status)) {
      cell.active_attempt_id = null;
    } else if (!cell.active_attempt_id) {
      // Simulate a fresh submission/attempt for a cell entering active state.
      cell.active_attempt_id = _makeRunId();
    }
    if (change.error !== undefined) cell.error = change.error;
    if (change.duration_ms !== undefined) cell.duration_ms = change.duration_ms;
  }
  exp.updated_at = _now();
  const envelope = _modernFlatEnvelope(exp);
  return Object.assign({}, envelope, { experiment_id: experimentId });
}

// ── Studio Workflow platform (modern workflow-run lane) ──────────────────
//
// Session-scoped deterministic seed for the modern workflow surface:
//   * wf_text2img  — 2 immutable versions (wv1_latest v2 / wv1_old v1),
//     presets wpres_a (default) + wpres_b, and old-version presets.
//   * wf_incomplete — one version whose state.runnable=false (missing
//     mapping + a dependency reason) — the Run button must stay disabled.
//   * wf_fail      — runnable, but POST /studio/run returns an error so the
//     UI shows the canonical failed terminal.
// Every version's executable_prompt matches the control schema exactly
// (prompt/negative_prompt/seed/steps/cfg/sampler/scheduler/denoise/model/
// width/height/bool_toggle).  modelCompatibility semantics: the model role
// enum options are checked against compatible_models, and the model library
// records installed=sd15_v2.safetensors / missing=krea_model.safetensors.

const WF_GRAPH_LATEST = {
  "3": {
    class_type: "KSampler",
    inputs: {
      model: ["9", 0], seed: 0, steps: 20, cfg: 7.0,
      sampler_name: "euler", scheduler: "normal",
      positive: ["6", 0], negative: ["7", 0], latent_image: ["5", 0],
      denoise: 1.0,
    },
  },
  "6": { class_type: "CLIPTextEncode", inputs: { text: "hello world", clip: ["9", 1] } },
  "7": { class_type: "CLIPTextEncode", inputs: { text: "negative", clip: ["9", 1] } },
  "5": { class_type: "EmptyLatentImage", inputs: { width: 512, height: 512, batch_size: 1 } },
  "9": { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "sd15_v2.safetensors" } },
  "8": { class_type: "SomeBooleanNode", inputs: { boolean: false } },
  "4": { class_type: "SaveImage", inputs: { images: ["3", 0] } },
};

function _deepCopyWFGraph() {
  return JSON.parse(JSON.stringify(WF_GRAPH_LATEST));
}

function _wfGraphOld() {
  const graph = _deepCopyWFGraph();
  graph["3"].inputs.seed = 5;
  graph["3"].inputs.steps = 22;
  graph["3"].inputs.sampler_name = "dpmpp_2m";
  graph["3"].inputs.scheduler = "karras";
  graph["3"].inputs.cfg = 6.5;
  graph["6"].inputs.text = "old world prompt";
  graph["7"].inputs.text = "old negative";
  graph["9"].inputs.ckpt_name = "krea_model.safetensors";
  return graph;
}

// graph hashes: 64 lowercase hex chars (content-hash-shaped but stable).
const WF_HASH_LATEST = "ab" + "01".repeat(31);
const WF_HASH_OLD = "cd" + "23".repeat(31);
const WF_HASH_INCOMPLETE = "ef" + "45".repeat(31);
const WF_HASH_FAIL = "12" + "67".repeat(31);

const WF_MAPPING_ENTRIES = [
  { semantic_role: "prompt", node_id: "6", input_name: "text", kind: "node_input", control_kind: "multiline", data_type: "STRING", multiline: true, required: true },
  { semantic_role: "negative_prompt", node_id: "7", input_name: "text", kind: "node_input", control_kind: "multiline", data_type: "STRING", multiline: true, required: false },
  { semantic_role: "seed", node_id: "3", input_name: "seed", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: -1, maximum: 281474976710655, step: 1, required: true },
  { semantic_role: "steps", node_id: "3", input_name: "steps", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 1, maximum: 100, step: 1, required: true },
  { semantic_role: "cfg", node_id: "3", input_name: "cfg", kind: "node_input", control_kind: "number", data_type: "FLOAT", minimum: 0, maximum: 30, step: 0.5, required: false },
  { semantic_role: "sampler", node_id: "3", input_name: "sampler_name", kind: "node_input", control_kind: "enum", data_type: "ENUM", enum_options: ["euler", "dpmpp_2m", "uni_pc"], required: true },
  { semantic_role: "scheduler", node_id: "3", input_name: "scheduler", kind: "node_input", control_kind: "enum", data_type: "ENUM", enum_options: ["normal", "karras", "sgm_uniform"], required: true },
  { semantic_role: "denoise", node_id: "3", input_name: "denoise", kind: "node_input", control_kind: "number", data_type: "FLOAT", minimum: 0, maximum: 1, step: 0.01, required: false },
  { semantic_role: "model", node_id: "9", input_name: "ckpt_name", kind: "node_input", control_kind: "file", data_type: "CHECKPOINT", enum_options: ["sd15_v2.safetensors", "krea_model.safetensors", "evil_model.safetensors"], required: true },
  { semantic_role: "width", node_id: "5", input_name: "width", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 64, maximum: 2048, step: 8, required: true },
  { semantic_role: "height", node_id: "5", input_name: "height", kind: "node_input", control_kind: "integer", data_type: "INT", minimum: 64, maximum: 2048, step: 8, required: true },
  { semantic_role: "bool_toggle", node_id: "8", input_name: "boolean", kind: "node_input", control_kind: "boolean", data_type: "BOOLEAN", required: false },
];

const WF_PRESET_DEFS = {
  wpres_a: {
    workflow_version_id: "wv1_latest", workflow_id: "wf_text2img", name: "Preset A",
    values: {
      prompt: "preset A prompt", negative_prompt: "no A", seed: 111, steps: 25, cfg: 7.5,
      sampler: "euler", scheduler: "karras", denoise: 1.0, width: 768, height: 768,
      bool_toggle: true,
    },
    model_choices: { model: "sd15_v2.safetensors" },
  },
  wpres_b: {
    workflow_version_id: "wv1_latest", workflow_id: "wf_text2img", name: "Preset B",
    values: {
      prompt: "preset B prompt", negative_prompt: "no B", seed: 222, steps: 30, cfg: 8.0,
      sampler: "uni_pc", scheduler: "sgm_uniform", denoise: 0.9, width: 640, height: 640,
      bool_toggle: false,
    },
    model_choices: { model: "krea_model.safetensors" },
  },
  wpres_old_a: {
    workflow_version_id: "wv1_old", workflow_id: "wf_text2img", name: "Old Preset A",
    values: {
      prompt: "old preset prompt", negative_prompt: "old no", seed: 55, steps: 22, cfg: 6.0,
      sampler: "dpmpp_2m", scheduler: "karras", denoise: 1.0, width: 512, height: 512,
      bool_toggle: false,
    },
    model_choices: { model: "krea_model.safetensors" },
  },
  wpres_old_b: {
    workflow_version_id: "wv1_old", workflow_id: "wf_text2img", name: "Old Preset B",
    values: {
      prompt: "old preset B prompt", negative_prompt: "old no b", seed: 66, steps: 24, cfg: 6.5,
      sampler: "euler", scheduler: "normal", denoise: 1.0, width: 512, height: 512,
      bool_toggle: true,
    },
    model_choices: { model: "sd15_v2.safetensors" },
  },
  wpres_fail: {
    workflow_version_id: "wv_fail", workflow_id: "wf_fail", name: "Fail Preset",
    values: {
      prompt: "fail run", negative_prompt: "", seed: 1, steps: 20, cfg: 7.0,
      sampler: "euler", scheduler: "normal", denoise: 1.0, width: 512, height: 512,
      bool_toggle: false,
    },
    model_choices: { model: "sd15_v2.safetensors" },
  },
  wpres_cancel: {
    workflow_version_id: "wv_cancel", workflow_id: "wf_cancel", name: "Cancel Preset",
    values: {
      prompt: "cancel run", negative_prompt: "", seed: 2, steps: 20, cfg: 7.0,
      sampler: "euler", scheduler: "normal", denoise: 1.0, width: 512, height: 512,
      bool_toggle: false,
    },
    model_choices: { model: "sd15_v2.safetensors" },
  },
  wpres_interrupt: {
    workflow_version_id: "wv_interrupt", workflow_id: "wf_interrupt", name: "Interrupt Preset",
    values: {
      prompt: "interrupt run", negative_prompt: "", seed: 3, steps: 20, cfg: 7.0,
      sampler: "euler", scheduler: "normal", denoise: 1.0, width: 512, height: 512,
      bool_toggle: false,
    },
    model_choices: { model: "sd15_v2.safetensors" },
  },
};

function _wfPresetRecord(pid, def, isDefault) {
  return {
    preset_id: pid,
    workflow_version_id: def.workflow_version_id,
    workflow_id: def.workflow_id,
    name: def.name,
    values: Object.assign({}, def.values),
    model_choices: Object.assign({}, def.model_choices),
    state: { status: "ready", reasons: [], runnable: true },
    is_default: isDefault,
  };
}

/** Build the immutable, per-session (deep-copied) workflow seed dataset. */
function _buildWorkflowSeed() {
  const mappings = {
    wm1_latest: { mapping_id: "wm1_latest", workflow_version_id: "wv1_latest", output_node_id: "4", entries: WF_MAPPING_ENTRIES.map((e) => Object.assign({}, e)) },
    wm1_old: { mapping_id: "wm1_old", workflow_version_id: "wv1_old", output_node_id: "4", entries: WF_MAPPING_ENTRIES.map((e) => Object.assign({}, e)) },
    wm_fail: { mapping_id: "wm_fail", workflow_version_id: "wv_fail", output_node_id: "4", entries: WF_MAPPING_ENTRIES.map((e) => Object.assign({}, e)) },
    wm_cancel: { mapping_id: "wm_cancel", workflow_version_id: "wv_cancel", output_node_id: "4", entries: WF_MAPPING_ENTRIES.map((e) => Object.assign({}, e)) },
    wm_interrupt: { mapping_id: "wm_interrupt", workflow_version_id: "wv_interrupt", output_node_id: "4", entries: WF_MAPPING_ENTRIES.map((e) => Object.assign({}, e)) },
  };
  const presets = {};
  for (const [pid, def] of Object.entries(WF_PRESET_DEFS)) {
    const isDefault =
      (pid === "wpres_a" && def.workflow_version_id === "wv1_latest") ||
      (pid === "wpres_old_a" && def.workflow_version_id === "wv1_old") ||
      pid === "wpres_fail" ||
      pid === "wpres_cancel" ||
      pid === "wpres_interrupt";
    presets[pid] = _wfPresetRecord(pid, def, isDefault);
  }

  const versions = [
    {
      workflow_version_id: "wv1_latest", workflow_id: "wf_text2img", version_number: 2,
      created_at: "2026-01-02T00:00:00.000Z", updated_at: "2026-01-02T00:00:00.000Z",
      graph_hash: WF_HASH_LATEST, mapping_id: "wm1_latest", mapping: mappings.wm1_latest,
      preset_count: 2, executable_prompt: WF_GRAPH_LATEST,
      state: { status: "ready", reasons: [], runnable: true },
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      default_preset_id: "wpres_a",
    },
    {
      workflow_version_id: "wv1_old", workflow_id: "wf_text2img", version_number: 1,
      created_at: "2026-01-01T00:00:00.000Z", updated_at: "2026-01-01T00:00:00.000Z",
      graph_hash: WF_HASH_OLD, mapping_id: "wm1_old", mapping: mappings.wm1_old,
      preset_count: 2, executable_prompt: _wfGraphOld(),
      state: { status: "ready", reasons: [], runnable: true },
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      default_preset_id: "wpres_old_a",
    },
    {
      workflow_version_id: "wv_incomplete", workflow_id: "wf_incomplete", version_number: 1,
      created_at: "2026-01-01T00:00:00.000Z", updated_at: "2026-01-01T00:00:00.000Z",
      graph_hash: WF_HASH_INCOMPLETE, mapping_id: null, mapping: null,
      preset_count: 0, executable_prompt: _deepCopyWFGraph(),
      state: {
        status: "incomplete",
        reasons: ["missing mapping", "missing custom node 'SomeCustomClass'"],
        runnable: false,
      },
      compatible_models: [],
      default_preset_id: "",
    },
    {
      workflow_version_id: "wv_fail", workflow_id: "wf_fail", version_number: 1,
      created_at: "2026-01-01T00:00:00.000Z", updated_at: "2026-01-01T00:00:00.000Z",
      graph_hash: WF_HASH_FAIL, mapping_id: "wm_fail", mapping: mappings.wm_fail,
      preset_count: 1, executable_prompt: _deepCopyWFGraph(),
      state: { status: "ready", reasons: [], runnable: true },
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      default_preset_id: "wpres_fail",
    },
    {
      workflow_version_id: "wv_cancel", workflow_id: "wf_cancel", version_number: 1,
      created_at: "2026-01-01T00:00:00.000Z", updated_at: "2026-01-01T00:00:00.000Z",
      graph_hash: WF_HASH_FAIL, mapping_id: "wm_cancel", mapping: mappings.wm_cancel,
      preset_count: 1, executable_prompt: _deepCopyWFGraph(),
      state: { status: "ready", reasons: [], runnable: true },
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      default_preset_id: "wpres_cancel",
    },
    {
      workflow_version_id: "wv_interrupt", workflow_id: "wf_interrupt", version_number: 1,
      created_at: "2026-01-01T00:00:00.000Z", updated_at: "2026-01-01T00:00:00.000Z",
      graph_hash: WF_HASH_FAIL, mapping_id: "wm_interrupt", mapping: mappings.wm_interrupt,
      preset_count: 1, executable_prompt: _deepCopyWFGraph(),
      state: { status: "ready", reasons: [], runnable: true },
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      default_preset_id: "wpres_interrupt",
    },
  ];

  const workflows = [
    {
      workflow_id: "wf_text2img", name: "Text2Img Workflow",
      description: "Seeded txt2img workflow", folder: "", tags: ["txt2img"],
      favorite: false, latest_version_id: "wv1_latest", latest_version_number: 2,
      latest_version_state: { status: "ready", reasons: [], runnable: true },
      default_preset_id: "wpres_a", default_preset_name: "Preset A",
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      version_count: 2, updated_at: "2026-01-02T00:00:00.000Z",
    },
    {
      workflow_id: "wf_incomplete", name: "Incomplete Workflow",
      description: "Seeded workflow with an unrunnable version", folder: "",
      tags: [], favorite: false, latest_version_id: "wv_incomplete",
      latest_version_number: 1,
      latest_version_state: {
        status: "incomplete",
        reasons: ["missing mapping", "missing custom node 'SomeCustomClass'"],
        runnable: false,
      },
      default_preset_id: "", default_preset_name: null,
      compatible_models: [], version_count: 1, updated_at: "2026-01-01T00:00:00.000Z",
    },
    {
      workflow_id: "wf_fail", name: "Fail Workflow",
      description: "Runnable workflow whose run always fails", folder: "",
      tags: [], favorite: false, latest_version_id: "wv_fail",
      latest_version_number: 1,
      latest_version_state: { status: "ready", reasons: [], runnable: true },
      default_preset_id: "wpres_fail", default_preset_name: "Fail Preset",
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      version_count: 1, updated_at: "2026-01-01T00:00:00.000Z",
    },
    {
      workflow_id: "wf_cancel", name: "Cancel Workflow",
      description: "Runnable workflow whose run follows the pending scenario terminal", folder: "",
      tags: [], favorite: false, latest_version_id: "wv_cancel",
      latest_version_number: 1,
      latest_version_state: { status: "ready", reasons: [], runnable: true },
      default_preset_id: "wpres_cancel", default_preset_name: "Cancel Preset",
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      version_count: 1, updated_at: "2026-01-01T00:00:00.000Z",
    },
    {
      workflow_id: "wf_interrupt", name: "Interrupt Workflow",
      description: "Runnable workflow whose run follows the pending scenario terminal", folder: "",
      tags: [], favorite: false, latest_version_id: "wv_interrupt",
      latest_version_number: 1,
      latest_version_state: { status: "ready", reasons: [], runnable: true },
      default_preset_id: "wpres_interrupt", default_preset_name: "Interrupt Preset",
      compatible_models: ["sd15_v2.safetensors", "krea_model.safetensors"],
      version_count: 1, updated_at: "2026-01-01T00:00:00.000Z",
    },
  ];

  return { workflows, versions, mappings, presets };
}

function _workflowSeed(session) {
  if (!session.workflowSeed) session.workflowSeed = _buildWorkflowSeed();
  return session.workflowSeed;
}

// ── Public: workflow platform read APIs ──────────────────────────────────

export function listFakeWorkflows(id, opts = {}) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  let list = seed.workflows;
  const search = String((opts && opts.search) || "").toLowerCase();
  if (search) {
    list = list.filter((w) =>
      String(w.name || "").toLowerCase().includes(search) ||
      String(w.description || "").toLowerCase().includes(search)
    );
  }
  const tag = String((opts && opts.tag) || "");
  if (tag) list = list.filter((w) => (w.tags || []).includes(tag));
  const folder = String((opts && opts.folder) || "");
  if (folder) {
    list = list.filter((w) => String(w.folder || "") === folder ||
      String(w.folder || "").startsWith(folder + "/"));
  }
  return { status: "ok", workflows: list.map((w) => Object.assign({}, w)) };
}

export function getFakeWorkflow(id, wfId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const wf = seed.workflows.find((w) => w.workflow_id === wfId);
  if (!wf) return { status: "error", message: "workflow not found", _httpStatus: 404 };
  return { status: "ok", workflow: Object.assign({}, wf) };
}

export function listFakeWorkflowVersions(id, wfId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const wf = seed.workflows.find((w) => w.workflow_id === wfId);
  if (!wf) return { status: "error", message: "workflow not found", _httpStatus: 404 };
  const versions = seed.versions
    .filter((v) => v.workflow_id === wfId)
    .map((v) => _cloneWfVersion(v));
  return { status: "ok", versions };
}

export function getFakeWorkflowVersion(id, versionId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const v = seed.versions.find((x) => x.workflow_version_id === versionId);
  if (!v) return { status: "error", message: "version not found", _httpStatus: 404 };
  return { status: "ok", version: _cloneWfVersion(v) };
}

export function getFakeMapping(id, versionId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const v = seed.versions.find((x) => x.workflow_version_id === versionId);
  const mapping = v && v.mapping_id ? seed.mappings[v.mapping_id] : null;
  return { status: "ok", mapping: mapping ? _cloneWfMapping(mapping) : null };
}

export function listFakeVersionPresets(id, versionId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const presets = Object.values(seed.presets)
    .filter((p) => p.workflow_version_id === versionId)
    .map((p) => Object.assign({}, p, { values: Object.assign({}, p.values), model_choices: Object.assign({}, p.model_choices) }));
  return { status: "ok", presets };
}

export function getFakeWorkflowPreset(id, presetId) {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const p = seed.presets[presetId];
  if (!p) return { status: "error", message: "preset not found", _httpStatus: 404 };
  return {
    status: "ok",
    preset: Object.assign({}, p, { values: Object.assign({}, p.values), model_choices: Object.assign({}, p.model_choices) }),
  };
}

export function getFakeWorkflowRunContext(id, wfId, versionId = "") {
  const session = getSession(id);
  const seed = _workflowSeed(session);
  const wf = seed.workflows.find((w) => w.workflow_id === wfId);
  if (!wf) {
    return { status: "error", message: "workflow not found", _httpStatus: 404 };
  }
  const resolvedVersionId = versionId || wf.latest_version_id || "";
  const version = seed.versions.find((v) => v.workflow_version_id === resolvedVersionId) || null;
  const mapping = version && version.mapping_id ? seed.mappings[version.mapping_id] : null;
  const state = version
    ? Object.assign({}, version.state)
    : { status: "incomplete", reasons: ["no versions"], runnable: false };
  const defaultPreset = wf.default_preset_id ? seed.presets[wf.default_preset_id] || null : null;
  const controlSchema = {};
  if (mapping) {
    for (const entry of mapping.entries) {
      if (entry && entry.semantic_role) controlSchema[entry.semantic_role] = Object.assign({}, entry);
    }
  }
  return {
    status: "ok",
    workflow: Object.assign({}, wf),
    version: version ? _cloneWfVersion(version) : null,
    mapping: mapping ? _cloneWfMapping(mapping) : null,
    default_preset: defaultPreset ? Object.assign({}, defaultPreset) : null,
    state,
    control_schema: controlSchema,
  };
}

function _cloneWfVersion(v) {
  return Object.assign({}, v, {
    mapping: v.mapping ? _cloneWfMapping(v.mapping) : null,
    executable_prompt: JSON.parse(JSON.stringify(v.executable_prompt || {})),
    state: Object.assign({}, v.state),
    compatible_models: (v.compatible_models || []).slice(),
  });
}

function _cloneWfMapping(m) {
  return {
    mapping_id: m.mapping_id,
    workflow_version_id: m.workflow_version_id,
    output_node_id: m.output_node_id,
    entries: (m.entries || []).map((e) => Object.assign({}, e)),
  };
}

// ── Public: modern workflow run handler ──────────────────────────────────

/**
 * Handle POST /comfymodal/studio/run for a modern workflow request (body
 * carries workflow_version_id).  Captures the ENTIRE request body into
 * session.workflowRuns (for state assertions), creates a completed History
 * V2 generation carrying the modern identity + request params + the applied
 * workflow_json (topology probe), and returns the direct-run shape the
 * frontend expects (direct_run: true) — mirroring the legacy studio/run
 * success envelope.
 *
 * The special workflow_id "wf_fail" returns the canonical error envelope so
 * the UI exercises its failure terminal.
 */
export function handleStudioWorkflowRun(id, body = {}) {
  const session = getSession(id);
  const captured = JSON.parse(JSON.stringify(body || {}));
  session.workflowRuns.push(captured);

  if (captured.workflow_id === "wf_fail") {
    return {
      status: "error",
      error_code: "WORKFLOW_EXECUTION_FAILED",
      message: "Simulated workflow execution failure",
    };
  }

  const seed = _workflowSeed(session);
  const workflowId = String(captured.workflow_id || "");
  const versionId = String(captured.workflow_version_id || captured.workflowVersionId || "");
  const presetId = String(captured.preset_id || captured.presetId || "");
  const controls = (captured.controls && typeof captured.controls === "object") ? captured.controls : {};

  // Cancel / interrupt lanes route through the scenario engine so the run
  // settles on the pending scenario's terminal (submission response shape,
  // NOT a direct-run result — the frontend then polls and observes the
  // cancelled/interrupted terminal like a normal scheduler run).
  if (captured.workflow_id === "wf_cancel" || captured.workflow_id === "wf_interrupt") {
    const submitted = handleStudioRun(id, {
      presetIds: [presetId],
      featureId: "txt2img",
      controls: controls,
    });
    if (submitted && submitted.status === "ok") {
      // Attach the response identity to the captured request record.
      captured.runId = submitted.runId;
      captured.experimentId = submitted.experimentId;
      captured.runHistoryId = submitted.runId;
      return {
        status: "ok",
        runId: submitted.runId,
        experimentId: submitted.experimentId,
        message: "Run started",
      };
    }
    return submitted;
  }

  const wf = seed.workflows.find((w) => w.workflow_id === workflowId) || {
    workflow_id: workflowId, name: "Unknown Workflow",
  };
  const version = seed.versions.find((v) => v.workflow_version_id === versionId) || null;
  const preset = presetId ? seed.presets[presetId] || null : null;

  session.workflowRunSeq += 1;
  const seq = session.workflowRunSeq;
  const genId = "gen_wf_" + String(seq).padStart(3, "0");
  const runId = "run_wf_" + String(seq).padStart(3, "0");
  const outputFilename = "studio_wf_" + String(seq).padStart(3, "0") + ".png";
  session.outputs.set(outputFilename, _pngFor(outputFilename));

  // Applied workflow_json: version graph + controls written verbatim into
  // the mapped node inputs (same semantics as the backend adapter).  Node
  // ids are never added/removed — the topology is the version's graph.
  const workflowJson = JSON.parse(JSON.stringify((version && version.executable_prompt) || {}));
  const mapping = version && version.mapping_id ? seed.mappings[version.mapping_id] : null;
  if (mapping) {
    for (const entry of mapping.entries || []) {
      const value = controls[entry.semantic_role];
      if (value === undefined) continue;
      const node = workflowJson[entry.node_id];
      if (node && node.inputs) node.inputs[entry.input_name] = value;
    }
  }

  const createdAtMs = Date.now();
  const generation = _makeV2Generation(session, {
    id: genId,
    status: "completed",
    workflow_id: workflowId,
    workflow_name: wf.name || "",
    workflow_version: version ? String(version.version_number) : "",
    preset_id: presetId,
    preset_name: (preset && preset.name) || "",
    prompt: controls.prompt || "",
    negative_prompt: controls.negative_prompt || "",
    createdAtMs,
    durationMs: 4523,
    params: {
      seed: controls.seed, steps: controls.steps, cfg: controls.cfg,
      sampler: controls.sampler, scheduler: controls.scheduler,
      denoise: controls.denoise, width: controls.width, height: controls.height,
    },
    outputs: [{ thumb: true, preview: true, original: true, originalFilename: outputFilename }],
    workflowJson,
  });
  session.historyV2.push(generation);

  const now = _now();
  // Attach the response identity to the captured request record so state
  // assertions can correlate request → run/history identity.
  captured.runId = runId;
  captured.runHistoryId = runId;
  captured.experimentId = genId;
  return {
    status: "ok",
    runId,
    runHistoryId: runId,
    experimentId: genId,
    message: "Run started",
    completed_at: now,
    output_paths: [outputFilename],
    output_path: outputFilename,
    timings: _canonicalTimings(),
    meta: {
      workflow_id: workflowId,
      workflow_version_id: versionId,
      preset_id: presetId,
      workflow_name: wf.name || "",
      preset_name: (preset && preset.name) || "",
      workflow_hash: (version && version.graph_hash) || "",
      requested_controls: Object.assign({}, controls),
      output_count: 1,
      output_paths: [outputFilename],
      production_plan_used: "no",
    },
    direct_run: true,
    production_plan_used: "no",
  };
}

// ── Public: presets / snapshots CRUD ────────────────────────────────────

function _enrichPreset(p) {
  const s = _lookupSnapshotFor(p);
  return Object.assign({}, p, {
    nodeBindings: (s && s.nodeBindings) || {},
    outputNodeId: (s && s.outputNodeId) || "",
    featureStatus: (s && s.featureStatus) || {},
    hasApiPromptJson: Boolean(s && s.apiPromptJson),
    hasGraphJson: Boolean(s && s.graphJson),
    snapshotSummary: s
      ? {
          name: s.name || "",
          status: s.status || "",
          compatibleFeatures: s.compatibleFeatures || [],
          modelSummary: s.modelSummary || "",
          source: s.source || "",
        }
      : {},
    controlSchemas: (s && s.controlSchemas) || {},
    defaults: p.defaults || {},
  });
}

function _lookupSnapshotFor(preset) {
  // Snapshot map is global across sessions via id prefix; fall back to any session.
  if (!preset || !preset.snapshotId) return null;
  for (const s of SESSIONS.values()) {
    const snap = s.snapshots.get(preset.snapshotId);
    if (snap) return snap;
  }
  return null;
}

export function listPresets(id, includeArchived = false) {
  const session = getSession(id);
  const presets = [];
  for (const p of session.presets.values()) {
    if (!includeArchived && p.archived) continue;
    presets.push(_enrichPreset(p));
  }
  return { status: "ok", presets };
}

export function getPreset(id, presetId) {
  const session = getSession(id);
  const p = session.presets.get(presetId);
  if (!p || p.archived) return { status: "error", message: "Preset not found", _httpStatus: 404 };
  return { status: "ok", preset: _enrichPreset(p) };
}

export function createPreset(id, body = {}) {
  const session = getSession(id);
  const presetId = _makePresetId();
  const now = _now();
  const compatibleFeatures = Array.isArray(body.compatibleFeatures) ? body.compatibleFeatures : ["txt2img"];
  const entry = {
    id: presetId,
    label: body.label || body.name || "Untitled Preset",
    description: body.description || "",
    snapshotId: body.snapshotId || "",
    compatibleFeatures,
    defaults: body.defaults || {},
    sourceType: body.sourceType || "manual",
    sourceId: body.sourceId || "",
    archived: false,
    createdAt: now,
    updatedAt: now,
    status: "runnable",
    disabledReason: "",
  };
  session.presets.set(presetId, entry);
  return { status: "ok", preset: Object.assign({}, entry) };
}

export function updatePreset(id, presetId, body = {}) {
  const session = getSession(id);
  const p = session.presets.get(presetId);
  if (!p) return { status: "error", message: "Preset not found", _httpStatus: 404 };
  if (body.label !== undefined) p.label = String(body.label).slice(0, 200);
  if (body.description !== undefined) p.description = String(body.description).slice(0, 2000);
  if (body.snapshotId !== undefined) p.snapshotId = String(body.snapshotId);
  if (body.compatibleFeatures !== undefined && Array.isArray(body.compatibleFeatures)) {
    p.compatibleFeatures = body.compatibleFeatures;
  }
  if (body.defaults !== undefined && typeof body.defaults === "object") p.defaults = body.defaults;
  if (body.sourceType !== undefined) p.sourceType = String(body.sourceType);
  if (body.sourceId !== undefined) p.sourceId = String(body.sourceId);
  if (body.archived !== undefined) p.archived = Boolean(body.archived);
  p.updatedAt = _now();
  return { status: "ok", preset: _enrichPreset(p) };
}

export function deletePreset(id, presetId) {
  const session = getSession(id);
  const p = session.presets.get(presetId);
  if (!p) return { status: "error", message: "Preset not found", _httpStatus: 404 };
  p.archived = true;
  p.updatedAt = _now();
  return { status: "ok" };
}

export function duplicatePreset(id, presetId) {
  const session = getSession(id);
  const p = session.presets.get(presetId);
  if (!p) return { status: "error", message: "Preset not found", _httpStatus: 404 };
  const copy = Object.assign({}, p, {
    id: _makePresetId(),
    label: p.label + " (copy)",
    archived: false,
    createdAt: _now(),
    updatedAt: _now(),
  });
  session.presets.set(copy.id, copy);
  return { status: "ok", preset: _enrichPreset(copy) };
}

export function listSnapshots(id, includeArchived = false) {
  const session = getSession(id);
  const snapshots = [];
  for (const s of session.snapshots.values()) {
    if (!includeArchived && s.archived) continue;
    snapshots.push(Object.assign({}, s));
  }
  return { status: "ok", snapshots };
}

export function getSnapshot(id, snapshotId) {
  const session = getSession(id);
  const s = session.snapshots.get(snapshotId);
  if (!s || s.archived) return { status: "error", message: "Snapshot not found", _httpStatus: 404 };
  return { status: "ok", snapshot: Object.assign({}, s) };
}

export function createSnapshot(id, body = {}) {
  const session = getSession(id);
  const snapshotId = _makeSnapshotId();
  const now = _now();
  const compatibleFeatures = Array.isArray(body.compatibleFeatures) ? body.compatibleFeatures : ["txt2img"];
  const entry = {
    id: snapshotId,
    name: body.name || "Untitled Snapshot",
    description: body.description || "",
    createdAt: now,
    updatedAt: now,
    compatibleFeatures,
    graphJson: body.graphJson || null,
    apiPromptJson: body.apiPromptJson || null,
    nodeBindings: body.nodeBindings || {},
    outputNodeId: body.outputNodeId || "",
    modelSummary: body.modelSummary || "",
    source: body.source || "manual",
    controlSchemas: body.controlSchemas || {},
    archived: false,
    status: "runnable",
    featureStatus: Object.fromEntries(compatibleFeatures.map((f) => [f, { status: "runnable", reason: "" }])),
    disabledReason: "",
  };
  session.snapshots.set(snapshotId, entry);
  return { status: "ok", snapshot: Object.assign({}, entry) };
}

export function updateSnapshot(id, snapshotId, body = {}) {
  const session = getSession(id);
  const s = session.snapshots.get(snapshotId);
  if (!s) return { status: "error", message: "Snapshot not found", _httpStatus: 404 };
  if (body.name !== undefined) s.name = String(body.name).slice(0, 200);
  if (body.description !== undefined) s.description = String(body.description).slice(0, 2000);
  if (body.compatibleFeatures !== undefined && Array.isArray(body.compatibleFeatures)) {
    s.compatibleFeatures = body.compatibleFeatures;
    s.featureStatus = Object.fromEntries(body.compatibleFeatures.map((f) => [f, { status: "runnable", reason: "" }]));
  }
  if (body.graphJson !== undefined) s.graphJson = body.graphJson;
  if (body.apiPromptJson !== undefined) s.apiPromptJson = body.apiPromptJson;
  if (body.nodeBindings !== undefined && typeof body.nodeBindings === "object") s.nodeBindings = body.nodeBindings;
  if (body.outputNodeId !== undefined) s.outputNodeId = String(body.outputNodeId);
  if (body.modelSummary !== undefined) s.modelSummary = String(body.modelSummary).trim();
  if (body.controlSchemas !== undefined && typeof body.controlSchemas === "object") s.controlSchemas = body.controlSchemas;
  if (body.archived !== undefined) s.archived = Boolean(body.archived);
  s.updatedAt = _now();
  return { status: "ok", snapshot: Object.assign({}, s) };
}

export function deleteSnapshot(id, snapshotId) {
  const session = getSession(id);
  const s = session.snapshots.get(snapshotId);
  if (!s) return { status: "error", message: "Snapshot not found", _httpStatus: 404 };
  s.archived = true;
  s.updatedAt = _now();
  return { status: "ok" };
}

export function duplicateSnapshot(id, snapshotId) {
  const session = getSession(id);
  const s = session.snapshots.get(snapshotId);
  if (!s) return { status: "error", message: "Snapshot not found", _httpStatus: 404 };
  const copy = Object.assign({}, s, {
    id: _makeSnapshotId(),
    name: s.name + " (copy)",
    archived: false,
    createdAt: _now(),
    updatedAt: _now(),
  });
  session.snapshots.set(copy.id, copy);
  return { status: "ok", snapshot: Object.assign({}, copy) };
}

// ── Public: backends / config / assets ──────────────────────────────────

export function getBackends(id) {
  const session = getSession(id);
  return { status: "ok", backends: session.backends.map((b) => Object.assign({}, b)) };
}

export function getConfig(id) {
  getSession(id); // validate session
  return {
    status: "ok",
    execution_mode: "v2",
    output_format: "original",
    quality: 75,
    webp_lossless_compression: "balanced",
    auto_save_local: false,
    save_folder: "output/modal",
    save_metadata_sidecar: true,
    modal_token_configured: true,
    gpu: "A10G",
    deploy_state: "deployed",
    frontend_version: "0.1.0",
  };
}

export function setConfig(id, body = {}) {
  getSession(id);
  return { status: "ok", config: getConfig(id), applied: body };
}

export function getAsset(id, assetId) {
  const session = getSession(id);
  const bytes = session.assets.get(assetId);
  if (!bytes) return { ok: false };
  return { ok: true, contentType: "image/png", bytes };
}

export function getOutput(id, filename) {
  const session = getSession(id);
  const bytes = session.outputs.get(filename);
  if (!bytes) return { ok: false };
  return { ok: true, contentType: "image/png", bytes };
}

// ── Public: test control ────────────────────────────────────────────────

export function injectEvent(id, { type, detail } = {}) {
  const session = getSession(id);
  if (!type) return { status: "error", message: "type is required" };
  session.eventQueue.push({ type, detail: detail == null ? {} : detail });
  return { status: "ok", queued: 1 };
}

export function drainEvents(id, cursor = 0) {
  const session = getSession(id);
  const start = Number(cursor) || 0;
  const events = session.eventQueue.slice(start);
  return { events, cursor: start + events.length };
}

export function seedHistory(id, scenarioName = null) {
  const session = getSession(id);
  const name = scenarioName || (session.pendingScenario && session.pendingScenario.name) || "history_large";
  const def = getScenario(name);
  if (!def || def.kind !== "seed") {
    return {
      status: "error",
      message: `"${name}" is not a history seed scenario. Known seeds: ${Object.keys(SCENARIOS).filter((k) => SCENARIOS[k].kind === "seed").join(", ")}`,
    };
  }
  if (def.v2) {
    // History V2 seed: populate session.historyV2 (replacing it).  Legacy
    // session.history is left untouched, matching the per-store seeding model.
    session.historyV2 = _buildV2Seed(session, def.v2);
    return {
      status: "ok",
      scenario: name,
      count: session.historyV2.length,
      total: session.historyV2.length,
      v2: true,
    };
  }
  const seed = def.seed || {};
  const now = Date.now();
  const records = [];
  const count = Math.max(0, Number(seed.count) || 0);
  for (let i = 0; i < count; i++) {
    records.push(_makeSeedRecord(session, i, Object.assign({}, seed, { now })));
  }
  session.history = records;
  _registerSeedAssets(session, records, seed.registerAssets !== false);
  return { status: "ok", scenario: name, count: records.length, total: session.history.length };
}

function _makeSeedRecord(session, i, seed) {
  const now = seed.now || Date.now();
  const startedAt = new Date(now - i * 3600_000 - (seed.startOffsetMs || 0)).toISOString();
  const statuses = seed.statuses || ["completed", "failed"];
  const status = statuses[i % statuses.length];
  const presetIndex = i % Math.max(1, seed.presetCount || 4);

  if (seed.legacy) {
    // Deliberately minimal: only id/status/created_at.
    return { id: "run_legacy_" + i, status, created_at: startedAt };
  }

  const hasImage = seed.imageEvery ? i % seed.imageEvery === 0 : false;
  const sharedFilename = seed.sharedOutputFilename || null;
  const sharedAssetId = seed.sharedAssetId || null;
  const assetId = sharedAssetId || (hasImage ? (seed.assetIdPrefix || "asset_seed_") + i : "");
  const filename = sharedFilename || (hasImage ? "seed_output_" + i + ".png" : "");

  const isCompleted = status === "completed" || status === "success" || status === "done";
  const extra = {
    studio_preset_id: "preset_seed_" + presetIndex,
    studio_preset_label: "Seed Preset " + presetIndex,
    studio_feature_id: "txt2img",
    prompt: "seeded prompt #" + i + " — deterministic fake text for search/filter tests",
  };
  if (hasImage) extra.primary_asset_id = assetId;
  if (isCompleted && hasImage) {
    extra.output_saved = i % 7 === 0;
  }

  return {
    run_id: "run_seed_" + i,
    experiment_id: "exp_seed_" + i,
    kind: "experiment_cell",
    status,
    started_at: startedAt,
    completed_at: isCompleted ? new Date(Date.parse(startedAt) + 4523).toISOString() : "",
    workflow_name: "Seed Run",
    prompt: extra.prompt,
    negative_prompt: "",
    seed: 1000 + i,
    steps: 20,
    guidance: 7,
    sampler: "euler",
    scheduler: "normal",
    denoise: 1,
    width: 1024,
    height: 1024,
    output_path: filename,
    timings: isCompleted ? _canonicalTimings() : {},
    extra,
    annotations: {
      favorite: seed.favoriteEvery ? i % seed.favoriteEvery === 0 : false,
      note: seed.favoriteEvery && i % seed.favoriteEvery === 0 ? "favorited seed record " + i : "",
    },
  };
}

function _registerSeedAssets(session, records, shouldRegister) {
  if (shouldRegister === false) return;
  for (const r of records) {
    const extra = r.extra || {};
    if (extra.primary_asset_id) session.assets.set(extra.primary_asset_id, _pngFor(extra.primary_asset_id));
    if (r.asset_id) session.assets.set(r.asset_id, _pngFor(r.asset_id));
    if (r.output_path) session.outputs.set(r.output_path, _pngFor(r.output_path));
  }
}

// ── Public: diagnostics ─────────────────────────────────────────────────

export function dumpState(id) {
  const session = getSession(id);
  const experiments = [];
  for (const experiment of session.experiments.values()) {
    experiments.push({
      experiment_id: experiment.experiment_id,
      run_id: experiment.run_id,
      kind: experiment.kind,
      scenario: experiment.scenarioName,
      status: experiment.snapshot.status,
      counters: Object.assign({}, experiment.snapshot.counters),
      total_cells: experiment.snapshot.total_cells,
      pollCount: experiment.pollCount,
      terminalApplied: experiment.terminalApplied,
      journal: experiment.journal.map((e) => e.type),
      journalDetail: experiment.journal,
    });
  }
  return {
    status: "ok",
    sessionId: session.sessionId,
    pendingScenario: session.pendingScenario ? session.pendingScenario.name : null,
    presets: [...session.presets.values()].map((p) => ({ id: p.id, label: p.label, archived: p.archived })),
    snapshots: [...session.snapshots.values()].map((s) => ({ id: s.id, name: s.name, archived: s.archived })),
    backends: session.backends.map((b) => b.id),
    experiments,
    historyCount: session.history.length,
    historyStatuses: session.history.reduce((acc, r) => { acc[r.status] = (acc[r.status] || 0) + 1; return acc; }, {}),
    runHistoryCount: session.history.length,
    historyV2Count: session.historyV2.length,
    historyV2: session.historyV2.map((r) => ({
      id: r.id,
      kind: r.kind,
      status: r.status,
      favorite: !!r.favorite,
      note: r.note || "",
      featured_output_index: r.kind === "generation" ? _featuredIndex(r) : null,
      output_count: r.outputs ? r.outputs.length : (r.cells ? r.cells.length : 0),
    })),
    modernExperiments: [...session.modernExperiments.values()].map((e) => ({
      experiment_id: e.experiment_id,
      name: e.name || "",
      frozen_modal_options: e.definition && e.definition.modal_options
        ? JSON.parse(JSON.stringify(e.definition.modal_options))
        : null,
      aggregate_status: _modernAggregateFromCounts(_modernCountsFromCells(e.cells)),
      total: e.cells.length,
      counts: _modernCountsFromCells(e.cells),
      cells: e.cells.map((c) => ({
        cell_id: c.cell_id,
        position: c.position,
        status: _modernCanonicalCellStatus(c.status),
        active_attempt_id: c.active_attempt_id,
      })),
    })),
    profileLevel: session.profileLevel,
    eventQueueCount: session.eventQueue.length,
    eventQueue: session.eventQueue.slice(0, 200),
    assetIds: [...session.assets.keys()],
    outputFilenames: [...session.outputs.keys()],
    saveRequests: session.saveRequests,
    workflowRuns: JSON.parse(JSON.stringify(session.workflowRuns)),
    workflowRunSeq: session.workflowRunSeq,
  };
}

export { SCENARIOS };
