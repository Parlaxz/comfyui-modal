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
  const data = await apiFetch(apiBase, "/studio/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (data && data.status === "error") {
    console.error("[Studio run] backend execution failure", {
      error_code: data.error_code || data.error?.code || "STUDIO_EXECUTION_ERROR",
      operation: data.error?.operation || "studio_run",
      detail: data.error?.detail || data._error_detail || data.message || "",
      backend_error: data.error || null,
      http_status: data._httpStatus || null,
    });
  }
  return data;
}

export async function runStudioExperiment(apiBase, payload) {
  return apiFetch(apiBase, "/studio/experiment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getModalConfig(apiBase) {
  const data = await apiFetch(apiBase, "/config");
  return data && typeof data === "object" ? data : null;
}

export async function getStudioRunStatus(apiBase, id) {
  return apiFetch(apiBase, `/experiments/${encodeURIComponent(id)}`);
}

/**
 * Cancel/stop an experiment or single run by experiment ID.
 * Uses POST /experiments/{id}/stop-now (not /cancel/{client_id}).
 * @param {string} apiBase
 * @param {string} experimentId
 * @returns {Promise<object|null>}
 */
export async function stopExperiment(apiBase, experimentId) {
  if (!experimentId) return null;
  return apiFetch(apiBase, `/experiments/${encodeURIComponent(experimentId)}/stop-now`, {
    method: "POST",
  });
}

// ── Modern Experiment V2 API (D5) ────────────────────────────────────────

/**
 * Submit a modern experiment-v2 run definition.
 * @param {string} apiBase
 * @param {object} payload - Modern definition contract (workflows, axes,
 *   prompts, and resolved defaults). The server expands the fixed cell plan;
 *   no top-level cells or concurrency field is sent here.
 * @returns {Promise<object|null>}
 */
export async function runExperimentV2(apiBase, payload) {
  return apiFetch(apiBase, "/studio/experiment-v2", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

/**
 * Fetch the frozen modern experiment status (History V2 surface).
 * @param {string} apiBase
 * @param {string} experimentId
 * @returns {Promise<object|null>}
 */
export async function getExperimentV2Status(apiBase, experimentId) {
  if (!experimentId) return null;
  return apiFetch(apiBase, `/history-v2/experiments/${encodeURIComponent(experimentId)}/status`);
}

/**
 * Cancel a modern experiment (queued cells cancel without submission;
 * running attempts cancel best-effort; completed outputs preserved).
 * @param {string} apiBase
 * @param {string} experimentId
 * @returns {Promise<object|null>}
 */
export async function cancelExperimentV2(apiBase, experimentId) {
  if (!experimentId) return null;
  return apiFetch(apiBase, `/history-v2/experiments/${encodeURIComponent(experimentId)}/cancel`, {
    method: "POST",
  });
}

/**
 * Resume a modern experiment: submits only interrupted + never-started cells.
 * @param {string} apiBase
 * @param {string} experimentId
 * @returns {Promise<object|null>}
 */
export async function resumeExperiment(apiBase, experimentId) {
  if (!experimentId) return null;
  return apiFetch(apiBase, `/history-v2/experiments/${encodeURIComponent(experimentId)}/resume`, {
    method: "POST",
  });
}

/**
 * Retry ONE failed cell as a new attempt under the same cell/generation.
 * @param {string} apiBase
 * @param {string} experimentId
 * @param {string} cellId
 * @returns {Promise<object|null>}
 */
export async function retryCell(apiBase, experimentId, cellId) {
  if (!experimentId || !cellId) return null;
  return apiFetch(apiBase, `/history-v2/experiments/${encodeURIComponent(experimentId)}/cells/${encodeURIComponent(cellId)}/retry`, {
    method: "POST",
  });
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
/**
 * List real Studio aggregate experiments from /experiments.
 * @param {string} apiBase
 * @returns {Promise<Array|null>}
 */
export async function listExperiments(apiBase) {
  const data = await apiFetch(apiBase, "/experiments");
  if (data === null) return null;
  return (data && data.experiments) || [];
}

export async function listRunHistory(apiBase, params) {
  const query = new URLSearchParams();
  if (params) {
    if (params.limit != null) query.set("limit", String(params.limit));
    if (params.offset != null) query.set("offset", String(params.offset));
    if (params.search) query.set("search", params.search);
    if (params.kind) query.set("kind", params.kind);
    else if (params.type) query.set("kind", params.type);
    if (params.status) query.set("status", params.status);
    if (params.favorite_only) query.set("favorite_only", "true");
    else if (params.favorite) query.set("favorite_only", "true");
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

// ── Phase 7: Unified History API ─────────────────────────────────────────

/**
 * Fetch paginated history from the unified /comfymodal/history endpoint.
 * Supports AbortController for request cancellation.
 *
 * @param {string} apiBase
 * @param {object} params - Query parameters (page, page_size, search, kind, status, etc.)
 * @param {AbortSignal} [signal] - Optional AbortSignal to cancel the request.
 * @returns {Promise<{items: Array, page: number, page_size: number, total: number, has_more: boolean}|null>}
 */
export async function listUnifiedHistory(apiBase, params, signal) {
  const query = new URLSearchParams();
  if (params) {
    if (params.page != null) query.set("page", String(params.page));
    if (params.page_size != null) query.set("page_size", String(params.page_size));
    if (params.search) query.set("search", params.search);
    if (params.kind) query.set("kind", params.kind);
    else if (params.type) query.set("kind", params.type);
    if (params.status) query.set("status", params.status);
    if (params.favorite_only) query.set("favorite_only", "true");
    else if (params.favorite) query.set("favorite_only", "true");
    if (params.preset) query.set("preset", params.preset);
    if (params.feature) query.set("feature", params.feature);
    if (params.date_from) query.set("date_from", params.date_from);
    if (params.date_to) query.set("date_to", params.date_to);
    if (params.has_image) query.set("has_image", "true");
    if (params.sort) query.set("sort", params.sort);
  } else {
    query.set("page", "1");
    query.set("page_size", "50");
  }
  const qs = query.toString();
  try {
    const url = apiBase + "/history" + (qs ? "?" + qs : "");
    const res = await fetch(url, { signal: signal || null });
    let data = null;
    try {
      data = await res.json();
    } catch (parseError) {
      data = { status: "error", message: "History endpoint returned an invalid response" };
    }
    if (!res.ok) {
      const message = data && data.message ? data.message : "History request failed";
      const error = new Error(message);
      error.status = res.status;
      error.errorCode = data && data.error_code ? data.error_code : "history_request_failed";
      error.detail = data && data.detail ? data.detail : "";
      error.responseBody = data;
      console.error("[Studio History] history request failed", {
        url: url,
        status: res.status,
        body: data,
      });
      throw error;
    }
    if (data && data.status === "ok") {
      return {
        items: data.items || [],
        page: data.page || 1,
        page_size: data.page_size || 50,
        total: data.total || 0,
        has_more: !!data.has_more,
      };
    }
    return data || null;
  } catch (err) {
    if (err && err.name === "AbortError") return null;
    console.error("[Studio History] history request error", err);
    throw err;
  }
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
  return apiFetch(apiBase, `/run-history/${encodeURIComponent(runId)}/annotations`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Single-Output Save API ──────────────────────────────────────────────

/**
 * Save a single output of a run to the local outputs folder.
 * The request targets only the selected output (output_index), never
 * saving all outputs of a multi-output record.
 * @param {string} apiBase
 * @param {string} runId
 * @param {object} payload - { output_index: number }
 * @returns {Promise<object|null>}
 */
export async function saveRunOutput(apiBase, runId, payload) {
  if (!runId) return null;
  return apiFetch(apiBase, `/run-history/${encodeURIComponent(runId)}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Studio Workflow API ──────────────────────────────────────────────────

export async function listWorkflows(apiBase, opts = {}) {
  const query = new URLSearchParams();
  if (opts) {
    if (opts.search) query.set("search", opts.search);
    if (opts.tag) query.set("tag", opts.tag);
    if (opts.folder) query.set("folder", opts.folder);
    if (opts.favorite) query.set("favorite", "1");
  }
  const qs = query.toString();
  return apiFetch(apiBase, "/studio/workflows" + (qs ? "?" + qs : ""));
}

export async function createWorkflow(apiBase, payload) {
  return apiFetch(apiBase, "/studio/workflows", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function importWorkflow(apiBase, payload) {
  return apiFetch(apiBase, "/studio/workflows/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getWorkflow(apiBase, workflowId) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}`);
}

export async function updateWorkflow(apiBase, workflowId, payload) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function listWorkflowFolders(apiBase) {
  return apiFetch(apiBase, "/studio/workflows/folders");
}

export async function listWorkflowTags(apiBase) {
  return apiFetch(apiBase, "/studio/workflows/tags");
}

export async function setWorkflowDefaultPreset(apiBase, workflowId, presetId) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}/default-preset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset_id: presetId }),
  });
}

export async function clearWorkflowDefaultPreset(apiBase, workflowId) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}/default-preset`, {
    method: "DELETE",
  });
}

export async function getWorkflowRunContext(apiBase, workflowId, versionId = "") {
  let path = `/studio/workflows/${encodeURIComponent(workflowId)}/run-context`;
  if (versionId) path += `?version_id=${encodeURIComponent(versionId)}`;
  return apiFetch(apiBase, path);
}

// ── Studio Workflow Versions API ─────────────────────────────────────────

export async function listWorkflowVersions(apiBase, workflowId) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}/versions`);
}

export async function captureWorkflowVersion(apiBase, workflowId, capture) {
  return apiFetch(apiBase, `/studio/workflows/${encodeURIComponent(workflowId)}/versions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(capture),
  });
}

export async function getWorkflowVersion(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}`);
}

export async function getVersionState(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/state`);
}

// ── Studio Workflow Mapping API ──────────────────────────────────────────

export async function getMapping(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping`);
}

export async function createMapping(apiBase, versionId, payload) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getMappingCandidates(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping/candidates`);
}

export async function createMappingRevision(apiBase, versionId, payload) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/mapping/revision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

// ── Studio Workflow Presets API ──────────────────────────────────────────

export async function listVersionPresets(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/presets`);
}

export async function createVersionPreset(apiBase, versionId, payload) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/presets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getWorkflowPreset(apiBase, presetId) {
  return apiFetch(apiBase, `/studio/workflows/presets/${encodeURIComponent(presetId)}`);
}

export async function updateWorkflowPreset(apiBase, presetId, payload) {
  return apiFetch(apiBase, `/studio/workflows/presets/${encodeURIComponent(presetId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function deleteWorkflowPreset(apiBase, presetId) {
  return apiFetch(apiBase, `/studio/workflows/presets/${encodeURIComponent(presetId)}`, {
    method: "DELETE",
  });
}

export async function duplicateWorkflowPreset(apiBase, presetId) {
  return apiFetch(apiBase, `/studio/workflows/presets/${encodeURIComponent(presetId)}/duplicate`, {
    method: "POST",
  });
}

export async function copyPresetToVersion(apiBase, presetId, targetVersionId) {
  return apiFetch(apiBase, `/studio/workflows/presets/${encodeURIComponent(presetId)}/copy-to-version`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_version_id: targetVersionId }),
  });
}

export async function bulkCopyPresetsToVersion(apiBase, versionId, presetIds) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/presets/copy-bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset_ids: presetIds }),
  });
}

// ── Studio Model Library API ────────────────────────────────────────────

export async function listModels(apiBase, opts = {}) {
  const query = new URLSearchParams();
  if (opts) {
    if (opts.search) query.set("search", opts.search);
    if (opts.type) query.set("type", opts.type);
    if (opts.state) query.set("state", opts.state);
  }
  const qs = query.toString();
  return apiFetch(apiBase, "/studio/models" + (qs ? "?" + qs : ""));
}

export async function getModel(apiBase, modelId) {
  return apiFetch(apiBase, `/studio/models/${encodeURIComponent(modelId)}`);
}

export async function updateModel(apiBase, modelId, body) {
  return apiFetch(apiBase, `/studio/models/${encodeURIComponent(modelId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function rescanModels(apiBase, forceRehash) {
  return apiFetch(apiBase, "/studio/models/rescan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force_rehash: !!forceRehash }),
  });
}

export async function listModelTypes(apiBase) {
  return apiFetch(apiBase, "/studio/models/types");
}

export async function requestModelInstall(apiBase, body) {
  return apiFetch(apiBase, "/studio/models/install-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function listCustomNodes(apiBase) {
  return apiFetch(apiBase, "/studio/custom-nodes");
}

export async function refreshCustomNodes(apiBase) {
  return apiFetch(apiBase, "/studio/custom-nodes/refresh", { method: "POST" });
}

export async function requestCustomNodeInstall(apiBase, body) {
  return apiFetch(apiBase, "/studio/custom-nodes/install-request", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ── Studio Workflow Version Dependencies / Compatibility API ────────────

export async function getVersionDependencies(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/dependencies`);
}

export async function getVersionCompatibility(apiBase, versionId) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/compatibility`);
}

export async function updateVersionCompatibility(apiBase, versionId, body) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/compatibility`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
