// Modal Studio — Run Normalizer
//
// Shared helper for resolving image URLs from run-history entries, plus
// timing/annotation normalization consumed by BOTH Playground and History.
// Callers: studio-history.js, studio-playground.js, and any other
// module that needs to display run output images or metadata.
//
// Image URL resolution order (per the spec):
//   1. extra.primary_asset_id  → /assets/<id>
//   2. run.asset_id            → /assets/<id>
//   3. run.output_path         → /studio/outputs/<path>
//
// Returns null when no image source exists on the run.

// ── Nullish-safe helpers ─────────────────────────────────────────────────
//
// These preserve zero/0.0/false values that truthiness checks would hide.
// Use nilTo(x, fallback) to replace null/undefined only, or nilZero(x) to
// treat null/undefined as 0 for numeric fields.

/**
 * Return the value if not null/undefined, otherwise the fallback.
 * Unlike `||`, this preserves 0, 0.0, "", and false.
 * @param {*} value
 * @param {*} fallback
 * @returns {*}
 */
export function nilTo(value, fallback) {
  return value != null ? value : fallback;
}

/**
 * Return the value if not null/undefined, otherwise 0.
 * @param {*} value
 * @returns {*}
 */
export function nilZero(value) {
  return value != null ? value : 0;
}

/**
 * Return the value if not null/undefined and not empty string, otherwise fallback.
 * @param {*} value
 * @param {*} fallback
 * @returns {*}
 */
export function nilOrEmptyTo(value, fallback) {
  if (value == null) return fallback;
  if (typeof value === "string" && value === "") return fallback;
  return value;
}

// ── Timing normalization helpers ─────────────────────────────────────────
//
// Given a raw timings object (or trace) from the backend, produce readable
// stage breakdowns suitable for display in history and playground.

/**
 * Normalize raw timings into readable stages.
 * @param {object} timings - Raw timings/trace object.
 * @returns {Array<{label:string, durationMs:number, source:string}>}
 */
export function normalizeTimingStages(timings) {
  if (!timings || typeof timings !== "object") return [];
  const stages = [];
  const d = timings.deltas_ms || timings;

  // Helper to add a stage if its value exists
  function addStage(label, key) {
    const val = d[key];
    if (val != null && typeof val === "number") {
      stages.push({ label: label, durationMs: val, source: key });
    }
  }

  addStage("Queue", "t0_to_t1");
  addStage("Worker Startup", "t1_to_t2");
  addStage("Workload Load/Validate", "t3_to_t3b");
  addStage("Model/CLIP Load", "clip_load");
  addStage("Prompt Encoding", "clip_encode");
  addStage("Sampling", "sampler");
  addStage("VAE Decode", "vae_decode");
  addStage("Image Save/Transfer", "image_io");
  addStage("Finalization", "t9_to_t10");
  addStage("Remote Inference Total", "inference_total");
  addStage("End-to-End Total", "modal_to_browser");

  // Cold start
  if (d.t2_to_t3 != null) {
    stages.push({ label: "Cold Start (model download)", durationMs: d.t2_to_t3, source: "t2_to_t3" });
  }

  // Graph overhead
  if (d.graph_overhead != null) {
    stages.push({ label: "Graph Overhead", durationMs: d.graph_overhead, source: "graph_overhead" });
  }

  return stages;
}

/**
 * Normalize per-node timings if available.
 * @param {object} timings - Raw timings/trace object.
 * @returns {Array<{nodeId:string, durationMs:number, cached:boolean}>}
 */
export function normalizePerNodeTimings(timings) {
  if (!timings || typeof timings !== "object") return [];
  const perNode = timings.per_node || timings.node_times || timings.nodeTimings || {};
  if (Object.keys(perNode).length === 0) return [];

  return Object.entries(perNode).map(function (_ref) {
    var nodeId = _ref[0];
    var data = _ref[1];
    if (typeof data === "number") {
      return { nodeId: nodeId, durationMs: data, cached: false };
    }
    return {
      nodeId: nodeId,
      durationMs: data.duration_ms || data.duration || 0,
      cached: !!data.cached,
    };
  }).sort(function (a, b) {
    return b.durationMs - a.durationMs;
  });
}

/**
 * Build a timing summary string from stages.
 * @param {Array} stages
 * @returns {string}
 */
export function buildTimingSummary(stages) {
  if (!stages || stages.length === 0) return "";
  var total = stages.filter(function (s) { return s.label === "End-to-End Total" || s.label === "Remote Inference Total"; });
  var primary = total.length > 0 ? total[0] : stages[stages.length - 1];
  var topStages = stages.filter(function (s) {
    return s.label !== "End-to-End Total" && s.label !== "Remote Inference Total" && s.durationMs > 0;
  }).sort(function (a, b) { return b.durationMs - a.durationMs; }).slice(0, 3);

  var parts = [_formatDuration(primary.durationMs)];
  topStages.forEach(function (s) {
    parts.push(s.label + ": " + _formatDuration(s.durationMs));
  });
  return parts.join(" | ");
}

export function _formatDuration(ms) {
  if (ms == null) return "?";
  if (ms < 1000) return ms.toFixed(0) + "ms";
  if (ms < 60000) return (ms / 1000).toFixed(1) + "s";
  var m = Math.floor(ms / 60000);
  var s = (ms % 60000) / 1000;
  return m + "m " + s.toFixed(0) + "s";
}

// ── Annotation normalization ─────────────────────────────────────────────
//
// Annotations (favorite, note) are stored in extra.annotations or
// extra.metadata.annotations on the raw run.

/**
 * Extract annotation fields from a raw run.
 * @param {object} run - Raw run-history entry.
 * @returns {{favorite: boolean, note: string, noteUpdatedAt: string}}
 */
export function normalizeAnnotations(run) {
  if (!run) return { favorite: false, note: "", noteUpdatedAt: "" };
  var extra = (run && run.extra) || {};
  var annotations = extra.annotations || extra.metadata?.annotations || {};

  return {
    favorite: nilTo(annotations.favorite, false),
    note: nilTo(annotations.note, ""),
    noteUpdatedAt: nilTo(annotations.note_updated_at || annotations.noteUpdatedAt, ""),
  };
}

// ── Image URL resolution ─────────────────────────────────────────────────

/**
 * Resolve the best available image URL for a run, or null.
 * @param {object} run - A run-history entry.
 * @param {string} apiBase - API base path (e.g. "/comfymodal").
 * @returns {string|null}
 */
export function resolveRunImageUrl(run, apiBase) {
  if (!run) return null;
  const extra = (run && run.extra) || {};

  // 1. primary_asset_id (from experiment materialization)
  const primaryAssetId = extra.primary_asset_id || run.primary_asset_id || "";
  if (primaryAssetId) {
    return apiBase + "/assets/" + encodeURIComponent(primaryAssetId);
  }

  // 2. run-level asset_id (from ordinary runs)
  const assetId = run.asset_id || extra.asset_id || "";
  if (assetId) {
    return apiBase + "/assets/" + encodeURIComponent(assetId);
  }

  // 3. output_path (fallback for older runs without asset registration)
  const outputPath = run.output_path || extra.output_path || "";
  if (outputPath) {
    return apiBase + "/studio/outputs/" + encodeURIComponent(outputPath);
  }

  return null;
}

/**
 * Check whether a run has any resolvable image URL.
 * @param {object} run
 * @returns {boolean}
 */
export function hasRunImage(run) {
  return resolveRunImageUrl(run, "") !== null;
}

/**
 * Normalize a raw run-history entry into a stable object with all known fields.
 * Tolerates older records and field aliases (run_id, state, created, etc.).
 * @param {object|null|undefined} rawRun - A raw run-history entry.
 * @param {string} apiBase - API base path (e.g. "/comfymodal").
 * @returns {object|null}
 */
export function normalizeStudioRun(rawRun, apiBase) {
  if (!rawRun) return null;
  const extra = (rawRun && rawRun.extra) || {};
  const run = rawRun;

  // Core identifiers — handle aliases
  const id = run.id || run.run_id || extra.experiment_id || "";
  const experimentId = run.experiment_id || run.experimentId || extra.experiment_id || "";
  const status = run.status || run.state || "unknown";
  const imageUrl = resolveRunImageUrl(run, apiBase);
  const outputPath = run.output_path || extra.output_path || "";

  // Studio metadata
  const studioMeta = extra.studio_meta || extra.studio_metadata || {};
  const presetId = extra.studio_preset_id || studioMeta.studio_preset_id || "";
  const presetLabel = extra.studio_preset_label
    || extra.preset_label
    || run.preset_label
    || studioMeta.studio_preset_label
    || "";
  const snapshotId = extra.studio_snapshot_id || studioMeta.studio_snapshot_id || "";
  const featureId = extra.studio_feature_id || studioMeta.studio_feature_id || "";

  // Prompt fields (use nilTo to preserve empty string)
  const prompt = nilTo(extra.prompt, nilTo(run.prompt, ""));
  const negativePrompt = nilTo(extra.negative_prompt, nilTo(run.negative_prompt, ""));

  // Controls
  const resolvedControls = extra.resolved_controls || run.resolved_controls || {};
  const requestedControls = extra.requested_controls || extra.controls || run.controls || {};

  // Timestamps
  const startedAt = run.started_at || run.created_at || run.timestamp || run.created || "";
  const completedAt = run.completed_at || "";

  // Timings detail
  const timings = run.timings || extra.timings || {};

  // Duration: prefer explicit duration_ms, then timings.total_ms (canonical backend field),
  // then legacy run.duration (seconds → ms), else 0.
  // Use nilZero to preserve 0 values rather than falling back to || chains.
  let durationMs = nilZero(run.duration_ms);
  if (!durationMs && timings.total_ms != null) {
    durationMs = timings.total_ms;
  }
  if (!durationMs && run.duration != null) {
    durationMs = typeof run.duration === "number" ? run.duration * 1000 : 0;
  }

  // Workflow hash
  const workflowHash = run.workflow_hash || extra.workflow_hash || "";

  // Error
  const error = nilTo(run.error, nilTo(extra.error, ""));

  // ── Annotations (favorite, note) ────────────────────────────────────
  const annotations = normalizeAnnotations(rawRun);
  const favorite = annotations.favorite;
  const note = annotations.note;
  const noteUpdatedAt = annotations.noteUpdatedAt;

  // ── Timing normalization ────────────────────────────────────────────
  const timingStages = normalizeTimingStages(timings);
  const perNodeTimings = normalizePerNodeTimings(timings);
  const timingSources = {
    duration_ms: "raw",
    timings: "raw",
    stages: "derived",
    per_node: "derived",
  };
  const timingSummary = buildTimingSummary(timingStages);
  const rawTiming = timings;

  return {
    id: id,
    experimentId: experimentId,
    status: status,
    imageUrl: imageUrl,
    outputPath: outputPath,
    presetId: presetId,
    presetLabel: presetLabel,
    snapshotId: snapshotId,
    featureId: featureId,
    prompt: prompt,
    negativePrompt: negativePrompt,
    resolvedControls: resolvedControls,
    requestedControls: requestedControls,
    startedAt: startedAt,
    completedAt: completedAt,
    durationMs: durationMs,
    timings: timings,
    workflowHash: workflowHash,
    error: error,
    raw: rawRun,

    // Annotations (same format for Playground + History)
    favorite: favorite,
    note: note,
    noteUpdatedAt: noteUpdatedAt,

    // Timing summaries
    timingSummary: timingSummary,
    timingStages: timingStages,
    perNodeTimings: perNodeTimings,
    timingSources: timingSources,
    rawTiming: rawTiming,
  };
}
