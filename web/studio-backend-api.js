// Modal Studio — Backend API Layer
//
// All API communication for snapshots, presets, and backend discovery.
// No rendering logic — only fetch/response helpers.

// ── Internal fetch helper ─────────────────────────────────────────────────

let _backendCache = null;

async function apiFetch(apiBase, path, options) {
  try {
    const res = await fetch(`${apiBase}${path}`, options || {});
    const data = await res.json();
    // Return error JSON as-is so callers can inspect status/message
    if (!res.ok && data && typeof data === "object") {
      data._httpStatus = res.status;
      return data;
    }
    if (!res.ok) return null;
    return data;
  } catch { return null; }
}

// ── Legacy Backend Discovery API ──────────────────────────────────────────

export async function getBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends`);
    if (!res.ok) return [];
    const data = await res.json();
    _backendCache = (data && data.backends) || [];
    return _backendCache;
  } catch {
    return [];
  }
}

export async function getCompareBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends?kind=comparable`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data && data.backends) || [];
  } catch {
    return [];
  }
}

// ── Snapshots API ─────────────────────────────────────────────────────────

export async function listSnapshots(apiBase) {
  const data = await apiFetch(apiBase, "/studio/snapshots");
  if (data === null) return null; // network/API error
  return (data && data.snapshots) || [];
}

export async function createSnapshot(apiBase, payload) {
  return apiFetch(apiBase, "/studio/snapshots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updateSnapshot(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function duplicateSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

export async function archiveSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ── Backend Presets API ───────────────────────────────────────────────────

export async function listPresets(apiBase) {
  const data = await apiFetch(apiBase, "/studio/presets");
  if (data === null) return null; // network/API error
  return (data && data.presets) || [];
}

export async function createPreset(apiBase, payload) {
  return apiFetch(apiBase, "/studio/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function updatePreset(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function duplicatePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

export async function deletePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ── Studio Run / Experiment API ──────────────────────────────────────────

export async function runStudioPreset(apiBase, payload) {
  return apiFetch(apiBase, "/studio/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function runStudioExperiment(apiBase, payload) {
  return apiFetch(apiBase, "/studio/experiment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getStudioRunStatus(apiBase, id) {
  return apiFetch(apiBase, `/experiments/${encodeURIComponent(id)}`);
}

// ── Run History API (with pagination, filter, sort) ──────────────────────

/**
 * List run history with pagination, filtering, and sorting.
 * @param {string} apiBase
 * @param {object} params - Query parameters.
 * @param {number} [params.limit=50] - Maximum records to return.
 * @param {number} [params.offset=0] - Offset for pagination.
 * @param {string} [params.search] - Search text.
 * @param {string} [params.type] - Filter by type (run, experiment, etc.).
 * @param {string} [params.status] - Filter by status.
 * @param {boolean} [params.favorite] - Filter favorite only.
 * @param {string} [params.preset] - Filter by preset ID.
 * @param {string} [params.feature] - Filter by feature ID.
 * @param {string} [params.date_from] - Start date for range filter.
 * @param {string} [params.date_to] - End date for range filter.
 * @param {boolean} [params.has_image] - Filter runs with images.
 * @param {string} [params.sort] - Sort order (newest, oldest, fastest, slowest, preset_az, preset_za).
 * @returns {Promise<{runs: Array, total: number}|null>}
 */
export async function listRunHistory(apiBase, params) {
  const query = new URLSearchParams();
  if (params) {
    if (params.limit != null) query.set("limit", String(params.limit));
    if (params.offset != null) query.set("offset", String(params.offset));
    if (params.search) query.set("search", params.search);
    if (params.type) query.set("type", params.type);
    if (params.status) query.set("status", params.status);
    if (params.favorite) query.set("favorite", "true");
    if (params.preset) query.set("preset", params.preset);
    if (params.feature) query.set("feature", params.feature);
    if (params.date_from) query.set("date_from", params.date_from);
    if (params.date_to) query.set("date_to", params.date_to);
    if (params.has_image) query.set("has_image", "true");
    if (params.sort) query.set("sort", params.sort);
  } else {
    query.set("limit", "50");
    query.set("offset", "0");
  }
  const qs = query.toString();
  return apiFetch(apiBase, "/run-history" + (qs ? "?" + qs : ""));
}

// ── Run Annotation API ───────────────────────────────────────────────────

/**
 * Update a run's annotation (favorite, note).
 * Uses PATCH to allow partial updates.
 * @param {string} apiBase
 * @param {string} runId
 * @param {object} payload - { favorite?: boolean, note?: string }
 * @returns {Promise<object|null>}
 */
export async function updateRunAnnotation(apiBase, runId, payload) {
  if (!runId) return null;
  return apiFetch(apiBase, `/run-history/${encodeURIComponent(runId)}/annotation`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
