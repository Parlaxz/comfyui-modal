// Modal Studio — Run Normalizer
//
// Shared helper for resolving image URLs from run-history entries.
// Callers: studio-history.js, studio-playground.js, and any other
// module that needs to display run output images.
//
// Image URL resolution order (per the spec):
//   1. extra.primary_asset_id  → /assets/<id>
//   2. run.asset_id            → /assets/<id>
//   3. run.output_path         → /studio/outputs/<path>
//
// Returns null when no image source exists on the run.

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

  // Prompt fields
  const prompt = extra.prompt || run.prompt || "";
  const negativePrompt = extra.negative_prompt || run.negative_prompt || "";

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
  let durationMs = run.duration_ms || 0;
  if (!durationMs && timings.total_ms != null) {
    durationMs = timings.total_ms;
  }
  if (!durationMs && run.duration) {
    durationMs = typeof run.duration === "number" ? run.duration * 1000 : 0;
  }

  // Workflow hash
  const workflowHash = run.workflow_hash || extra.workflow_hash || "";

  // Error
  const error = run.error || extra.error || "";

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
  };
}
