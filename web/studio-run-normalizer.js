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
