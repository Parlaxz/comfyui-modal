// Modal Studio — Mock API for E2E browser tests
//
// Installs a Playwright page.route interceptor that replaces the
// /comfymodal/ backend with an in-memory mock.  Supports both
// snapshot/preset CRUD and experiment/run-history lifecycle.
//
// Usage:
//   import { installStudioMockApi } from "./studio-mock-api.mjs";
//   const api = await installStudioMockApi(page);
//   await page.goto(baseURL);   // navigation AFTER install
//
// No broad cleanup by name/prefix — only explicit ID deletion.

import { randomBytes } from "node:crypto";

// ── Constants ─────────────────────────────────────────────────────────────

const ONE_PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64"
);

// ── ID helpers ───────────────────────────────────────────────────────────

function _makeSnapshotId() {
  return "snap_" + randomBytes(8).toString("hex");
}

function _makePresetId() {
  return "preset_" + randomBytes(8).toString("hex");
}

function _makeExperimentId() {
  return "exp_" + randomBytes(8).toString("hex");
}

function _makeRunId() {
  return "run_" + randomBytes(8).toString("hex");
}

function _makeCheckpointId() {
  return "ck_" + randomBytes(8).toString("hex");
}

// ── Route compiler ───────────────────────────────────────────────────────

/**
 * Convert "/comfymodal/studio/snapshots/:id" → { regex, paramNames }.
 */
function _compilePattern(pattern) {
  const paramNames = [];
  const regex = new RegExp(
    "^" +
      pattern.replace(/:([a-zA-Z_][a-zA-Z0-9_]*)/g, (_, name) => {
        paramNames.push(name);
        return "([^/]+)";
      }) +
      "$"
  );
  return { regex, paramNames };
}

// ── installStudioMockApi ─────────────────────────────────────────────────

/**
 * Install page.route for all /comfymodal/ requests on *page*.
 *
 * Must be called **before** navigation so that mock coverage starts
 * from the first page load.
 *
 * @param {import("playwright").Page} page
 * @param {{}} [options]
 * @returns {Promise<{
 *   state: object,
 *   lastRunRequest: object|null,
 *   lastExperimentRequest: object|null,
 *   activePresets: function(): Array,
 *   activeSnapshots: function(): Array,
 *   reset: function(): void,
 *   failNext: function(method:string, pattern:string): void,
 *   setExperimentBehavior: function(id:string, opts:object): void,
 * }>}
 */
export async function installStudioMockApi(page, options = {}) {
  // ── Internal state ──────────────────────────────────────────────────────
  const state = {
    snapshots: new Map(),
    presets: new Map(),
    experiments: new Map(), // expId → { definition, snapshot, events }
    history: [],
    calls: [],
    unhandledCalls: [], // {method, pathname} from catch-all only
    pollCounts: new Map(), // expId → integer
    saveRequests: [], // { run_id, output_index } from POST /run-history/:id/save
    configPost: null, // last POST /comfymodal/config body (Settings page)
    profileLevel: "off", // in-memory /comfymodal/profile/level stored value
  };

  let lastRunRequest = null;
  let lastExperimentRequest = null;

  // Failure injection queue: [{ method, pattern, status, body }]
  const failQueue = [];

  // Per-experiment behavior overrides
  const experimentBehaviors = new Map();

  // System-wide behavior defaults (overridable per-experiment)
  const _defaultTerminalPoll = options.terminalPoll ?? 5;
  const _defaultFailAfter = options.failAfter ?? Infinity;
  const _defaultForceFailed = options.forceFailed ?? false;

  // ── JSON helpers ────────────────────────────────────────────────────────

  function _json(data, status = 200) {
    return {
      status,
      contentType: "application/json",
      body: JSON.stringify(data),
    };
  }

  function _error(message, httpStatus = 400) {
    return _json({ status: "error", message }, httpStatus);
  }

  function _now() {
    return new Date().toISOString();
  }

  // ── Route handlers ──────────────────────────────────────────────────────
  //
  // Each handler receives (route, url, body, params) and returns
  // { status, contentType, body } or a Promise thereof.

  /** GET /comfymodal/studio/snapshots/:id */
  async function snapshotDetail(route, url, body, params) {
    const s = state.snapshots.get(params.id);
    if (!s || s.archived) return _error("Snapshot not found", 404);
    return _json({ status: "ok", snapshot: { ...s } });
  }

  /** GET /comfymodal/studio/snapshots */
  async function listSnapshots(route, url, body, params) {
    const includeArchived = url.searchParams.get("includeArchived") === "1";
    const snapshots = [];
    for (const s of state.snapshots.values()) {
      if (!includeArchived && s.archived) continue;
      snapshots.push({ ...s });
    }
    return _json({ status: "ok", snapshots });
  }

  /** POST /comfymodal/studio/snapshots */
  async function createSnapshot(route, url, body) {
    const id = _makeSnapshotId();
    const now = _now();
    const compatibleFeatures = Array.isArray(body?.compatibleFeatures)
      ? body.compatibleFeatures
      : ["txt2img"];
    const entry = {
      id,
      name: body?.name || "Untitled Snapshot",
      description: body?.description || "",
      createdAt: now,
      updatedAt: now,
      compatibleFeatures,
      graphJson: body?.graphJson || null,
      apiPromptJson: body?.apiPromptJson || null,
      nodeBindings: body?.nodeBindings || {},
      outputNodeId: body?.outputNodeId || "",
      modelSummary: body?.modelSummary || "",
      source: body?.source || "manual",
      controlSchemas: body?.controlSchemas || {},
      archived: false,
      status: "runnable",
      featureStatus: Object.fromEntries(
        compatibleFeatures.map((fid) => [fid, { status: "runnable", reason: "" }])
      ),
      disabledReason: "",
    };
    state.snapshots.set(id, entry);
    return _json({ status: "ok", snapshot: { ...entry } });
  }

  /** PATCH /comfymodal/studio/snapshots/:id */
  async function updateSnapshot(route, url, body, params) {
    const s = state.snapshots.get(params.id);
    if (!s) return _error("Snapshot not found", 404);
    if (body.name !== undefined) s.name = String(body.name).slice(0, 200);
    if (body.description !== undefined) s.description = String(body.description).slice(0, 2000);
    if (body.compatibleFeatures !== undefined && Array.isArray(body.compatibleFeatures)) {
      s.compatibleFeatures = body.compatibleFeatures;
      s.featureStatus = Object.fromEntries(
        body.compatibleFeatures.map((fid) => [fid, { status: "runnable", reason: "" }])
      );
    }
    if (body.graphJson !== undefined) s.graphJson = body.graphJson;
    if (body.apiPromptJson !== undefined) s.apiPromptJson = body.apiPromptJson;
    if (body.nodeBindings !== undefined && typeof body.nodeBindings === "object") {
      s.nodeBindings = body.nodeBindings;
    }
    if (body.outputNodeId !== undefined) s.outputNodeId = String(body.outputNodeId);
    if (body.modelSummary !== undefined) s.modelSummary = String(body.modelSummary).trim();
    if (body.controlSchemas !== undefined && typeof body.controlSchemas === "object") {
      s.controlSchemas = body.controlSchemas;
    }
    if (body.archived !== undefined) s.archived = Boolean(body.archived);
    s.updatedAt = _now();
    return _json({ status: "ok", snapshot: { ...s } });
  }

  /** DELETE /comfymodal/studio/snapshots/:id (archive) */
  async function deleteSnapshot(route, url, body, params) {
    const s = state.snapshots.get(params.id);
    if (!s) return _error("Snapshot not found", 404);
    s.archived = true;
    s.updatedAt = _now();
    return _json({ status: "ok" });
  }

  /** GET /comfymodal/studio/presets/:id */
  async function presetDetail(route, url, body, params) {
    const p = state.presets.get(params.id);
    if (!p || p.archived) return _error("Preset not found", 404);
    const sid = p.snapshotId || "";
    const snap = sid ? state.snapshots.get(sid) : null;
    return _json({
      status: "ok",
      preset: {
        ...p,
        nodeBindings: snap?.nodeBindings || {},
        outputNodeId: snap?.outputNodeId || "",
        featureStatus: snap?.featureStatus || {},
        hasApiPromptJson: Boolean(snap?.apiPromptJson),
        hasGraphJson: Boolean(snap?.graphJson),
        snapshotSummary: snap
          ? {
              name: snap.name || "",
              status: snap.status || "",
              compatibleFeatures: snap.compatibleFeatures || [],
              modelSummary: snap.modelSummary || "",
              source: snap.source || "",
            }
          : {},
        controlSchemas: snap?.controlSchemas || {},
        defaults: p.defaults || {},
      },
    });
  }

  /** GET /comfymodal/studio/presets */
  async function listPresets(route, url, body, params) {
    const includeArchived = url.searchParams.get("includeArchived") === "1";
    const presets = [];
    for (const p of state.presets.values()) {
      if (!includeArchived && p.archived) continue;
      // Enrich with snapshot-backed runtime fields
      const sid = p.snapshotId || "";
      const snap = sid ? state.snapshots.get(sid) : null;
      presets.push({
        ...p,
        nodeBindings: snap?.nodeBindings || {},
        outputNodeId: snap?.outputNodeId || "",
        featureStatus: snap?.featureStatus || {},
        hasApiPromptJson: Boolean(snap?.apiPromptJson),
        hasGraphJson: Boolean(snap?.graphJson),
        snapshotSummary: snap
          ? {
              name: snap.name || "",
              status: snap.status || "",
              compatibleFeatures: snap.compatibleFeatures || [],
              modelSummary: snap.modelSummary || "",
              source: snap.source || "",
            }
          : {},
        controlSchemas: snap?.controlSchemas || {},
        defaults: p.defaults || {},
      });
    }
    return _json({ status: "ok", presets });
  }

  /** POST /comfymodal/studio/presets */
  async function createPreset(route, url, body) {
    const id = _makePresetId();
    const now = _now();
    const compatibleFeatures = Array.isArray(body?.compatibleFeatures)
      ? body.compatibleFeatures
      : ["txt2img"];
    const entry = {
      id,
      label: body?.label || body?.name || "Untitled Preset",
      description: body?.description || "",
      snapshotId: body?.snapshotId || "",
      compatibleFeatures,
      defaults: body?.defaults || {},
      sourceType: body?.sourceType || "manual",
      sourceId: body?.sourceId || "",
      archived: false,
      createdAt: now,
      updatedAt: now,
      status: "runnable",
      disabledReason: "",
    };
    state.presets.set(id, entry);
    return _json({ status: "ok", preset: { ...entry } });
  }

  /** PATCH /comfymodal/studio/presets/:id */
  async function updatePreset(route, url, body, params) {
    const p = state.presets.get(params.id);
    if (!p) return _error("Preset not found", 404);
    if (body.label !== undefined) p.label = String(body.label).slice(0, 200);
    if (body.description !== undefined) p.description = String(body.description).slice(0, 2000);
    if (body.snapshotId !== undefined) p.snapshotId = String(body.snapshotId);
    if (body.compatibleFeatures !== undefined && Array.isArray(body.compatibleFeatures)) {
      p.compatibleFeatures = body.compatibleFeatures;
    }
    if (body.defaults !== undefined && typeof body.defaults === "object") {
      p.defaults = body.defaults;
    }
    if (body.sourceType !== undefined) p.sourceType = String(body.sourceType);
    if (body.sourceId !== undefined) p.sourceId = String(body.sourceId);
    if (body.archived !== undefined) p.archived = Boolean(body.archived);
    p.updatedAt = _now();
    return _json({ status: "ok", preset: { ...p } });
  }

  /** DELETE /comfymodal/studio/presets/:id (archive) */
  async function deletePreset(route, url, body, params) {
    const p = state.presets.get(params.id);
    if (!p) return _error("Preset not found", 404);
    p.archived = true;
    p.updatedAt = _now();
    return _json({ status: "ok" });
  }

  /** POST /comfymodal/studio/run */
  async function studioRun(route, url, body) {
    lastRunRequest = body;
    const expId = _makeExperimentId();
    const runId = _makeRunId();

    // Create experiment definition
    const now = _now();
    const experimentDef = {
      schema_version: 1,
      experiment_id: expId,
      revision: 1,
      name: `Run ${runId}`,
      notes: "",
      created_at: now,
      updated_at: now,
    };

    // Create experiment state
    state.experiments.set(expId, {
      definition: experimentDef,
      snapshot: {
        status: "running",
        counters: { completed: 0, failed: 0, interrupted: 0 },
        total_cells: 1,
        cell_visible: {},
        checkpoints: {},
        attempts: {},
      },
      events: [
        {
          type: "experiment.started",
          payload: { experiment_id: expId, revision: 1, total_cells: 1 },
        },
      ],
    });
    state.pollCounts.set(expId, 0);

    // Create run history entry
    const runEntry = {
      run_id: runId,
      experiment_id: expId,
      kind: "experiment_cell",
      status: "in_progress",
      started_at: now,
      workflow_name: "Studio Run",
      prompt: body?.controls?.prompt || "",
      negative_prompt: body?.controls?.negative_prompt || "",
      seed: body?.controls?.seed ?? null,
      steps: body?.controls?.steps ?? null,
      guidance: body?.controls?.guidance ?? null,
      sampler: body?.controls?.sampler || "",
      scheduler: body?.controls?.scheduler || "",
      denoise: body?.controls?.denoise ?? null,
      width: body?.controls?.width ?? null,
      height: body?.controls?.height ?? null,
      output_path: "",
      timings: {},
      extra: {
        studio_preset_id: body?.presetId || "",
        studio_feature_id: body?.featureId || "",
        studio_preset_label: "",
      },
    };
    state.history.unshift(runEntry);

    return _json({
      status: "ok",
      runId,
      experimentId: expId,
      message: "Run started",
    });
  }

  /** POST /comfymodal/studio/experiment */
  async function studioExperiment(route, url, body) {
    lastExperimentRequest = body;

    // Reject zero unique presetIds — do not coerce zero to one.
    const presetIds = body?.presetIds || [];
    const uniquePresetCount = [...new Set(presetIds.filter(Boolean))].length;
    if (uniquePresetCount === 0) {
      return _error("At least one preset is required", 400);
    }

    const expId = _makeExperimentId();
    // cellCount = unique presetIds × Cartesian product of enabled axis values × prompts
    let cellCount = 1;
    if (Array.isArray(body?.experiment?.cells)) {
      cellCount = body.experiment.cells.length;
    } else {
      const axisCombos = Object.values(body?.experiment?.axes || {}).reduce(
        (acc, axis) => acc * (axis.values?.length || 1),
        1
      );
      const promptCount = Math.max(body?.experiment?.prompts?.length || 1, 1);
      cellCount = Math.max(uniquePresetCount, 1) * Math.max(axisCombos, 1) * promptCount;
    }
    const now = _now();

    const experimentDef = {
      schema_version: 1,
      experiment_id: expId,
      revision: 1,
      name: body?.experiment?.name || "Studio Experiment",
      notes: "",
      created_at: now,
      updated_at: now,
    };

    state.experiments.set(expId, {
      definition: experimentDef,
      snapshot: {
        status: "running",
        counters: { completed: 0, failed: 0, interrupted: 0 },
        total_cells: cellCount,
        cell_visible: {},
        checkpoints: {},
        attempts: {},
      },
      events: [
        {
          type: "experiment.started",
          payload: {
            experiment_id: expId,
            revision: 1,
            total_cells: cellCount,
          },
        },
      ],
    });
    state.pollCounts.set(expId, 0);

    return _json({
      status: "ok",
      experimentId: expId,
      cellCount,
      message: `Experiment started with ${cellCount} cells`,
    });
  }

  /** POST /comfymodal/experiments/:experiment_id/stop-now */
  async function experimentStopNow(route, url, body, params) {
    const expId = params.experiment_id;
    const exp = state.experiments.get(expId);
    if (!exp) return _error("experiment not found", 404);

    // Mark experiment stopped/cancelled
    const totalCells = exp.snapshot.total_cells || 0;
    exp.snapshot.status = "stopped";
    exp.snapshot.counters.interrupted = totalCells;
    exp.snapshot.counters.completed = 0;
    exp.snapshot.counters.failed = 0;

    // Emit experiment.stopped terminal event (idempotent)
    const hasTerminal = exp.events.some(function (e) {
      return e.type === "experiment.stopped" || e.type === "experiment.completed" || e.type === "experiment.failed_fatal";
    });
    if (!hasTerminal) {
      // Mark incomplete cells as interrupted
      for (var i = 0; i < totalCells; i++) {
        var ck = "cell_" + i;
        var alreadyTerminal = exp.events.some(function (e) {
          return (e.type === "cell.completed" || e.type === "cell.failed" || e.type === "cell.interrupted") &&
            e.payload && e.payload.cell_key === ck;
        });
        if (!alreadyTerminal) {
          exp.events.push({
            type: "cell.interrupted",
            payload: {
              cell_key: ck,
              checkpoint_id: _makeCheckpointId(),
              attempt_id: "a_" + randomBytes(4).toString("hex"),
              reason: "cancelled",
            },
          });
        }
      }
      exp.events.push({
        type: "experiment.stopped",
        payload: {
          completed: 0,
          failed: 0,
          interrupted: totalCells,
          total_cells: totalCells,
        },
      });
    }

    // Sync run history entry
    var runEntry = state.history.find(function (r) { return r.experiment_id === expId; });
    if (runEntry) {
      runEntry.status = "cancelled";
    }

    return _json({ status: "ok" });
  }

  /** GET /comfymodal/experiments/:experiment_id */
  async function experimentDetail(route, url, body, params) {
    const expId = params.experiment_id;
    const exp = state.experiments.get(expId);
    if (!exp) return _error("unknown experiment", 404);

    // Advance poll count
    const pollCount = (state.pollCounts.get(expId) || 0) + 1;
    state.pollCounts.set(expId, pollCount);

    // Check for behavior override (falls back to options defaults)
    const behavior = experimentBehaviors.get(expId) || {};
    const terminalPoll =
      behavior.terminalPoll != null ? behavior.terminalPoll : _defaultTerminalPoll;
    const failAfter =
      behavior.failAfter != null ? behavior.failAfter : _defaultFailAfter;
    const forceFailed =
      behavior.forceFailed != null ? behavior.forceFailed : _defaultForceFailed;
    const omitOutputs =
      behavior.omitOutputs === true;

    let snapshotStatus = "running";

    // Fix: preserve stopped terminal state set by stop-now
    if (exp.snapshot.status === "stopped") {
      // Already stopped by stop-now — keep the stopped snapshot
      return _json({
        status: "ok",
        definition: exp.definition,
        snapshot: {
          status: "stopped",
          counters: exp.snapshot.counters,
          total_cells: exp.snapshot.total_cells,
          total_duration_ms: 1000,
          cell_visible: exp.snapshot.cell_visible,
          checkpoints: exp.snapshot.checkpoints,
          attempts: exp.snapshot.attempts,
        },
        events: exp.events,
      });
    }

    if (pollCount >= terminalPoll || forceFailed) {
      // Determine whether this failure or success
      const shouldFail = forceFailed || pollCount >= failAfter;

      // ── Recompute counters consistent with terminal type ─────────────
      const totalCells = exp.snapshot.total_cells;
      const completed = shouldFail ? 0 : totalCells;
      const failed = shouldFail ? totalCells : 0;

      // Check if we already emitted terminal events (idempotent)
      const hasTerminal = exp.events.some(
        (e) =>
          e.type === "experiment.completed" ||
          e.type === "experiment.failed_fatal"
      );

      if (!hasTerminal) {
        // Emit per-cell events
        for (let i = 0; i < totalCells; i++) {
          const ck = `cell_${i}`;
          const attemptId = `a_${randomBytes(4).toString("hex")}`;
          if (shouldFail) {
            exp.events.push({
              type: "cell.failed",
              payload: {
                cell_key: ck,
                checkpoint_id: _makeCheckpointId(),
                error: "Cell execution failed (mock)",
                attempt_id: attemptId,
                timing_payload: {
                  trace: {
                    deltas_ms: {
                      end_to_end_total_ms: 1200 + i * 100,
                      sampling_ms: 800 + i * 50,
                      clip_encode_ms: 150,
                      vae_decode_ms: 100,
                      model_load_ms: 80,
                    },
                    trace_version: "2.0.0",
                  },
                  timing_quality: "minimal",
                },
              },
            });
          } else {
            // Build cell.completed payload, optionally omitting output
            // evidence to test the "no asset" code path in the poller.
            const cellPayload = {
              cell_key: ck,
              checkpoint_id: _makeCheckpointId(),
              attempt_id: attemptId,
              timing_payload: {
                trace: {
                  deltas_ms: {
                    end_to_end_total_ms: 4523 + i * 200,
                    sampling_ms: 3200 + i * 100,
                    clip_encode_ms: 450,
                    vae_decode_ms: 280,
                    model_load_ms: 120,
                  },
                  trace_version: "2.0.0",
                },
                timing_quality: "complete",
              },
            };
            if (!omitOutputs) {
              cellPayload.output_paths = [`studio_output_${i}.png`];
              cellPayload.primary_asset_id = `asset_${ck}`;
            }
            exp.events.push({ type: "cell.completed", payload: cellPayload });
          }
        }

        // Terminal event
        if (shouldFail) {
          exp.events.push({
            type: "experiment.failed_fatal",
            payload: {
              completed,
              failed,
              interrupted: 0,
              total_cells: totalCells,
              error: forceFailed ? "Mock failure" : "checkpoint failed",
            },
          });
          snapshotStatus = "failed_fatal";
        } else {
          exp.events.push({
            type: "experiment.completed",
            payload: {
              completed,
              failed,
              interrupted: 0,
              total_cells: totalCells,
            },
          });
          snapshotStatus = "completed";
        }

        // Update snapshot counters
        exp.snapshot.counters.completed = completed;
        exp.snapshot.counters.failed = failed;
      } else {
        // Already terminal — read status from last terminal event
        const lastEvent = exp.events[exp.events.length - 1];
        snapshotStatus =
          lastEvent?.type === "experiment.failed_fatal" ? "failed_fatal" : "completed";
      }

      // Keep the run-history entry in sync so frontend refreshRecentRuns
      // finds a completed run with output evidence and timing stages.
      const runEntry = state.history.find(function (r) { return r.experiment_id === expId; });
      if (runEntry && (snapshotStatus === "completed" || snapshotStatus === "failed_fatal")) {
        runEntry.status = snapshotStatus === "completed" ? "completed" : "failed";
        // When omitOutputs is active, skip output_path and timings so the
        // frontend does not fabricate a canvas image from history data.
        if (snapshotStatus === "completed" && !runEntry.output_path && !omitOutputs) {
          // Surface output evidence so resolveRunImageUrl returns a URL
          runEntry.output_path = "studio_output_final.png";
          // Provide canonical timing fields so normalizeTimingStages
          // produces End-to-End Total and Sampling stages.
          runEntry.timings = {
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
      }
    } else if (pollCount < (options.waitingPollCount ?? 2)) {
      snapshotStatus = "waiting";
    }

    // Attach experiment-level wall-clock total for terminal snapshots
    var totalDurationMs;
    if (snapshotStatus === "completed" || snapshotStatus === "failed_fatal") {
      var _tc = exp.snapshot.total_cells || 1;
      totalDurationMs = snapshotStatus === "completed"
        ? 4523 + (_tc - 1) * 200 + 300
        : 1200 + (_tc - 1) * 100 + 200;
    }

    return _json({
      status: "ok",
      definition: exp.definition,
      snapshot: {
        status: snapshotStatus,
        counters: exp.snapshot.counters,
        total_cells: exp.snapshot.total_cells,
        total_duration_ms: totalDurationMs,
        cell_visible: exp.snapshot.cell_visible,
        checkpoints: exp.snapshot.checkpoints,
        attempts: exp.snapshot.attempts,
      },
      events: exp.events,
    });
  }

  /** GET /comfymodal/experiments — aggregate experiment list for recent runs */
  async function listExperiments() {
    const experiments = [];
    for (const [experimentId, exp] of state.experiments.entries()) {
      experiments.push({
        experiment_id: experimentId,
        definition: { ...exp.definition },
        snapshot: {
          ...exp.snapshot,
          counters: { ...exp.snapshot.counters },
        },
      });
    }
    return _json({ status: "ok", experiments });
  }

  /** GET /comfymodal/run-history */
  async function listRunHistory(route, url) {
    const limit = parseInt(url.searchParams.get("limit") || "200", 10);
    const offset = parseInt(url.searchParams.get("offset") || "0", 10);
    const kindFilter = url.searchParams.get("kind") || url.searchParams.get("type") || null;
    const statusFilter = url.searchParams.get("status") || null;
    const search = url.searchParams.get("search") || null;
    const favoriteOnly = url.searchParams.get("favorite_only") === "true" ||
      url.searchParams.get("favorite") === "true";

    let filtered = [...state.history];

    if (kindFilter) {
      filtered = filtered.filter((r) => r.kind === kindFilter);
    }
    if (statusFilter) {
      filtered = filtered.filter((r) => r.status === statusFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      filtered = filtered.filter(
        (r) =>
          (r.prompt || "").toLowerCase().includes(lower) ||
          (r.run_id || "").toLowerCase().includes(lower)
      );
    }
    if (favoriteOnly) {
      filtered = filtered.filter((r) => r.annotations?.favorite);
    }

    const total = filtered.length;
    const runs = filtered.slice(offset, offset + limit);

    return _json({
      status: "ok",
      runs: runs.map((r) => ({
        ...r,
        output_saved: r.output_saved === true || r.extra?.output_saved === true || false,
        annotations: r.annotations || { favorite: false, note: "" },
      })),
      total,
      limit,
      offset,
    });
  }

  /** GET /comfymodal/history — unified paginated history */
  async function listUnifiedHistory(route, url) {
    const page = parseInt(url.searchParams.get("page") || "1", 10);
    const pageSize = parseInt(url.searchParams.get("page_size") || "50", 10);
    const kindFilter = url.searchParams.get("kind") || url.searchParams.get("type") || null;
    const statusFilter = url.searchParams.get("status") || null;
    const sort = url.searchParams.get("sort") || "newest";
    const search = url.searchParams.get("search") || null;

    let filtered = [...state.history];
    if (kindFilter) {
      filtered = filtered.filter((r) => r.kind === kindFilter);
    }
    if (statusFilter) {
      filtered = filtered.filter((r) => r.status === statusFilter);
    }
    if (search) {
      const lower = search.toLowerCase();
      filtered = filtered.filter(
        (r) =>
          (r.prompt || "").toLowerCase().includes(lower) ||
          (r.run_id || "").toLowerCase().includes(lower)
      );
    }
    if (sort === "oldest") filtered.reverse();

    const total = filtered.length;
    const items = filtered.slice((page - 1) * pageSize, page * pageSize);

    return _json({
      status: "ok",
      items: items.map((r) => ({
        ...r,
        output_saved: r.output_saved === true || r.extra?.output_saved === true || false,
        annotations: r.annotations || { favorite: false, note: "" },
      })),
      page,
      page_size: pageSize,
      total,
      has_more: page * pageSize < total,
    });
  }

  /** POST /comfymodal/run-history/:run_id/save — single-output save */
  async function saveRunOutput(route, url, body, params) {
    const run = state.history.find((r) => r.run_id === params.run_id);
    if (!run) return _error("not found", 404);

    const outputIndex = body?.output_index != null ? body.output_index : 0;
    run.output_saved = true;
    if (!run.extra) run.extra = {};
    run.extra.output_saved = true;
    run.extra.output_saved_at = _now();

    state.saveRequests.push({ run_id: run.run_id, output_index: outputIndex });

    return _json({
      status: "ok",
      saved: true,
      run_id: run.run_id,
      output_index: outputIndex,
    });
  }

  /** PATCH /comfymodal/run-history/:run_id/annotations */
  async function patchRunAnnotations(route, url, body, params) {
    const run = state.history.find((r) => r.run_id === params.run_id);
    if (!run) return _error("not found", 404);

    if (!run.annotations) {
      run.annotations = { favorite: false, note: "" };
    }
    if (body.favorite !== undefined) {
      run.annotations.favorite = Boolean(body.favorite);
    }
    if (body.note !== undefined) {
      run.annotations.note = String(body.note).slice(0, 2000);
    }
    run.annotations.updated_at = _now();

    return _json({
      status: "ok",
      annotations: { ...run.annotations },
    });
  }

  /** GET /comfymodal/assets/:asset_id — returns 1-pixel PNG */
  async function serveAsset(route, url) {
    return {
      status: 200,
      contentType: "image/png",
      body: ONE_PIXEL_PNG,
    };
  }

  /** GET /comfymodal/studio/outputs/:filename — returns 1-pixel PNG */
  async function serveStudioOutput(route, url) {
    return {
      status: 200,
      contentType: "image/png",
      body: ONE_PIXEL_PNG,
    };
  }

  /** GET /comfymodal/studio/backends — returns empty array (Playground doesn't need backends) */
  async function listBackends(route, url) {
    return _json({ status: "ok", backends: [] });
  }

  /**
   * Config endpoint — the real backend returns Modal/ComfyUI settings.
   * The Playground does not read this directly; it is called during
   * ComfyUI extension setup for diagnostics.  Return a minimal stub.
   */
  async function serveConfig(route, url, body) {
    return _json({
      status: "ok",
      modal_token_configured: true,
      gpu: "mock-gpu",
      deploy_state: "deployed",
      frontend_version: "0.1.0",
    });
  }

  // ── Settings page routes (used by studio-settings.spec.mjs) ──────────────
  //
  // The redesigned Studio Settings page (web/studio-settings.js) reads a
  // full /comfymodal/config response to populate the Execution Engine and
  // GPU selects and the Outputs section, and it refreshes the deploy status
  // and heavy-tracing profile level on every render.  These handlers stay
  // purely additive — the pre-existing serveConfig handler above remains
  // untouched (the new route entries are registered before it in the table).

  /** GET /comfymodal/config — full settings config (engine, GPU, output prefs). */
  async function serveSettingsConfig(route, url, body) {
    return _json({
      status: "ok",
      // Prior stub fields preserved — ComfyUI extension setup reads these
      modal_token_configured: true,
      gpu: "rtx-pro-6000",
      deploy_state: "deployed",
      frontend_version: "0.1.0",
      // Execution engine options
      execution_mode: "v2",
      available_execution_modes: [
        { value: "v2", label: "V2 - Recommended" },
        { value: "v1", label: "V1 - Legacy fallback" },
      ],
      execution_mode_locked: false,
      // GPU options
      default_gpu: "rtx-pro-6000",
      available_gpus: [
        { value: "rtx-pro-6000", label: "rtx-pro-6000" },
        { value: "a100-40gb", label: "a100-40gb" },
      ],
      // Output preferences (server-side authority for the Outputs section)
      output_format: "original",
      quality: 75,
      webp_lossless_compression: "balanced",
      auto_save_local: false,
      save_folder: "output/modal",
      save_metadata_sidecar: true,
    });
  }

  /** POST /comfymodal/config — record the last posted body and acknowledge. */
  async function saveSettingsConfig(route, url, body) {
    state.configPost = body || null;
    return _json({ status: "ok" });
  }

  /** GET /comfymodal/profile/level — in-memory stored/effective level. */
  async function serveProfileLevel(route, url, body) {
    return _json({
      status: "ok",
      level: state.profileLevel,
      effective: state.profileLevel,
    });
  }

  /** POST /comfymodal/profile/level — persist the requested level. */
  async function saveProfileLevel(route, url, body) {
    if (body && typeof body.level === "string") {
      state.profileLevel = body.level;
    }
    return _json({ status: "ok", level: state.profileLevel });
  }

  /** GET /comfymodal/deploy/status — idle deployment. */
  async function serveDeployStatus(route, url, body) {
    return _json({ status: "ok", state: "idle", message: "" });
  }

  /** Catch-all: 599 JSON for any unhandled /comfymodal/ request */
  async function catchAll(route, url, body) {
    return _error("unhandled mock endpoint", 599);
  }

  // ── Route table ─────────────────────────────────────────────────────────
  //
  // Order matters: more specific routes must come before catch-all.
  // Each entry: [ method, pathPattern, handler ]

  const routeEntries = [
    // Snapshots (detail before list so :id never shadows list)
    ["GET", "/comfymodal/studio/snapshots/:id", snapshotDetail],
    ["GET", "/comfymodal/studio/snapshots", listSnapshots],
    ["POST", "/comfymodal/studio/snapshots", createSnapshot],
    ["PATCH", "/comfymodal/studio/snapshots/:id", updateSnapshot],
    ["DELETE", "/comfymodal/studio/snapshots/:id", deleteSnapshot],

    // Presets (detail before list)
    ["GET", "/comfymodal/studio/presets/:id", presetDetail],
    ["GET", "/comfymodal/studio/presets", listPresets],
    ["POST", "/comfymodal/studio/presets", createPreset],
    ["PATCH", "/comfymodal/studio/presets/:id", updatePreset],
    ["DELETE", "/comfymodal/studio/presets/:id", deletePreset],

    // Studio run & experiment
    ["POST", "/comfymodal/studio/run", studioRun],
    ["POST", "/comfymodal/studio/experiment", studioExperiment],

    // Experiment detail (poll-based lifecycle) & stop-now
    ["GET", "/comfymodal/experiments/:experiment_id", experimentDetail],
    ["POST", "/comfymodal/experiments/:experiment_id/stop-now", experimentStopNow],
    ["GET", "/comfymodal/experiments", listExperiments],

    // Run history
    ["GET", "/comfymodal/run-history", listRunHistory],
    ["GET", "/comfymodal/history", listUnifiedHistory],
    ["PATCH", "/comfymodal/run-history/:run_id/annotations", patchRunAnnotations],
    ["POST", "/comfymodal/run-history/:run_id/save", saveRunOutput],

    // Asset & output serving (1-pixel PNG)
    ["GET", "/comfymodal/assets/:asset_id", serveAsset],
    ["GET", "/comfymodal/studio/outputs/:filename", serveStudioOutput],

    // Backend discovery (returns empty — Playground uses presets instead)
    ["GET", "/comfymodal/studio/backends", listBackends],

    // Settings page (studio-settings.spec.mjs) — full config, profile level,
    // and deploy status. Registered before the legacy stub config entries so
    // the Settings page sees the full payload while /api/comfymodal/config
    // still uses the pre-existing minimal stub.
    ["GET", "/comfymodal/config", serveSettingsConfig],
    ["POST", "/comfymodal/config", saveSettingsConfig],
    ["GET", "/comfymodal/profile/level", serveProfileLevel],
    ["POST", "/comfymodal/profile/level", saveProfileLevel],
    ["GET", "/comfymodal/deploy/status", serveDeployStatus],

    // ComfyUI config endpoint — called during extension setup
    ["GET", "/api/comfymodal/config", serveConfig],
    ["POST", "/api/comfymodal/config", serveConfig],
    ["GET", "/comfymodal/config", serveConfig],
    ["POST", "/comfymodal/config", serveConfig],
  ];

  // Compile routes
  const compiledRoutes = routeEntries.map(([method, pattern, handler]) => {
    const { regex, paramNames } = _compilePattern(pattern);
    return { method, regex, paramNames, handler };
  });

  // ── Install page.route BEFORE navigation ────────────────────────────────

  await page.route("**/comfymodal/**", async (route) => {
    const request = route.request();
    const method = request.method();
    const url = new URL(request.url());
    const pathname = url.pathname;

    // Record call
    state.calls.push({ method, pathname, time: Date.now() });

    // Check failure queue
    for (let i = 0; i < failQueue.length; i++) {
      const f = failQueue[i];
      if (f.method === method && pathname.includes(f.pattern)) {
        failQueue.splice(i, 1);
        return route.fulfill({
          status: f.status || 500,
          contentType: "application/json",
          body: JSON.stringify(f.body || { status: "error", message: "injected failure" }),
        });
      }
    }

    // Parse body for POST/PATCH/PUT
    let body;
    if (["POST", "PATCH", "PUT"].includes(method)) {
      const raw = request.postData();
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch {
          body = undefined;
        }
      }
    }

    // Match route
    for (const entry of compiledRoutes) {
      if (entry.method !== method) continue;
      const match = pathname.match(entry.regex);
      if (!match) continue;
      const params = {};
      for (let i = 0; i < entry.paramNames.length; i++) {
        params[entry.paramNames[i]] = decodeURIComponent(match[i + 1]);
      }
      try {
        const result = await entry.handler(route, url, body, params);
        return route.fulfill({
          status: result.status,
          contentType: result.contentType,
          body: result.body,
        });
      } catch (err) {
        return route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({
            status: "error",
            message: `Mock handler error: ${err.message}`,
          }),
        });
      }
    }

    // Catch-all for unhandled /comfymodal/ paths — track for test assertions
    state.unhandledCalls.push({ method, pathname: url.pathname });
    const result = await catchAll(route, url, body);
    return route.fulfill({
      status: result.status,
      contentType: result.contentType,
      body: result.body,
    });
  });

  // ── Return API control object ───────────────────────────────────────────

  return {
    state,

    get lastRunRequest() {
      return lastRunRequest;
    },

    get lastExperimentRequest() {
      return lastExperimentRequest;
    },

    activePresets() {
      return [...state.presets.values()].filter((p) => !p.archived);
    },

    activeSnapshots() {
      return [...state.snapshots.values()].filter((s) => !s.archived);
    },

    /** Reset all state */
    reset() {
      state.snapshots.clear();
      state.presets.clear();
      state.experiments.clear();
      state.history.length = 0;
      state.calls.length = 0;
      state.unhandledCalls.length = 0;
      state.pollCounts.clear();
      state.saveRequests.length = 0;
      state.configPost = null;
      state.profileLevel = "off";
      lastRunRequest = null;
      lastExperimentRequest = null;
      failQueue.length = 0;
      experimentBehaviors.clear();
    },

    /**
     * Make the next matching request fail with the given status and body.
     * @param {string} method - HTTP method
     * @param {string} pattern - substring to match in pathname
     * @param {number} [status=500]
     * @param {object} [body]
     */
    failNext(method, pattern, status = 500, body) {
      failQueue.push({ method, pattern, status, body });
    },

    /**
     * Assert no unhandled mock calls were made.  Throws with a descriptive
     * message listing any unhandled requests so the caller can either add
     * a proper handler or fix the test to avoid triggering them.
     */
    assertNoUnhandledCalls() {
      if (state.unhandledCalls.length > 0) {
        const lines = state.unhandledCalls.map(function (u) {
          return "  " + u.method + " " + u.pathname;
        });
        throw new Error(
          "Unhandled mock calls (" + state.unhandledCalls.length + "):\n" +
          lines.join("\n") + "\n" +
          "Add a mock handler for these or fix the test to avoid them."
        );
      }
    },

    /**
     * Override experiment lifecycle behavior.
     * @param {string} id - experiment ID
     * @param {object} opts
     * @param {number} [opts.terminalPoll=5] - poll count at which experiment completes
     * @param {number} [opts.failAfter=Infinity] - poll count at which experiment fails
     * @param {boolean} [opts.forceFailed=false] - always end as failed_fatal
     * @param {boolean} [opts.omitOutputs=false] - omit primary_asset_id and
     *   output_paths from cell.completed events to test missing-output path
     */
    setExperimentBehavior(id, opts) {
      experimentBehaviors.set(id, { ...opts });
    },
  };
}
