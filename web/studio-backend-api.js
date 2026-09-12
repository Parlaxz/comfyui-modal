// Modal Studio — Backend API Layer
//
// All API communication for snapshots, presets, runs, experiments, workflows,
// models, and backend operations. No rendering logic — only fetch/response
// helpers.
//
// H18 Wave G: caller-proven dead helpers removed (getBackends,
// getCompareBackends, runStudioExperiment, listExperiments, listRunHistory,
// listUnifiedHistory, getModalConfig). Live compatibility helpers retained:
// updateRunAnnotation/saveRunOutput (run-history COMPAT_WRITE),
// getStudioRunStatus/stopExperiment (protected Single seams).

// ── Internal fetch helper ─────────────────────────────────────────────────

import { publishStudioSync } from "./studio-sync.js";

function syncKindForMutation(path, method) {
  if (method === "GET" || method === "HEAD") return null;
  if (
    path === "/studio/run" ||
    path === "/studio/experiment-v2" ||
    /^\/(?:history-v2|run-history|experiments)(?:\/|$)/.test(path)
  ) return "history";
  if (/^\/studio\/(?:workflows|models|custom-nodes)(?:\/|$)/.test(path)) return "workflows";
  if (
    /^\/(?:workspaces|deploy|manifest\/repair|hf-token|civitai-token)(?:\/|$)/.test(path) ||
    /^\/studio\/(?:snapshots|presets)(?:\/|$)/.test(path)
  ) return "workspace";
  return null;
}

async function apiFetch(apiBase, path, options) {
  try {
    const request = options || {};
    const method = String(request.method || "GET").toUpperCase();
    const syncKind = syncKindForMutation(path.split("?", 1)[0], method);
    const res = await fetch(`${apiBase}${path}`, request);
    const data = await res.json();
    // Return error JSON as-is so callers can inspect status/message
    if (!res.ok && data && typeof data === "object") {
      data._httpStatus = res.status;
      return data;
    }
    if (!res.ok) return null;
    if (syncKind && !(data && data.status === "error")) publishStudioSync(syncKind);
    return data;
  } catch { return null; }
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

// ── Run History API ──────────────────────────────────────────────────────
//
// listRunHistory/listUnifiedHistory/listExperiments were deleted in Wave G:
// zero importers since the H13 recent-runs migration (History V2 is the sole
// feed authority; /run-history reads and /history remain server-side compat).

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

// ── Legacy absorption bridge (abs-2) ────────────────────────────────────
//
// Client for the abs-1 verified route
// POST /comfymodal/studio/workflows/versions/{version_id}/presets/from-legacy
// (``create_preset_from_legacy`` on the domain service). The payload is an
// UNSCOPED legacy preset shape (``name``/``label``, ``description``,
// ``values`` / ``model_choices`` keyed by old semantic roles); the server
// translates it via ``translate_legacy_preset`` (LEGACY_ROLE_MAP) and
// persists it through the verified ``create_preset`` path under the URL
// version scope. The browser never translates keys itself — unknown keys
// pass through verbatim server-side and surface via preset state.

export async function createPresetFromLegacy(apiBase, versionId, legacyPayload) {
  return apiFetch(apiBase, `/studio/workflows/versions/${encodeURIComponent(versionId)}/presets/from-legacy`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(legacyPayload || {}),
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

// ── Bulk model install + ComfyUI-Manager integration (wizard deps step) ──
//
// Bulk install maps the wizard's "Download all" action onto the existing
// synchronous /models/batch-install route.  The Manager helpers talk to the
// ROOT-relative ComfyUI-Manager routes (not under /comfymodal), so they use a
// status-preserving fetch that also tolerates plain-text error bodies.

export async function batchInstallModels(apiBase, items) {
  return apiFetch(apiBase, "/models/batch-install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items: items || [] }),
  });
}

async function managerFetch(path, options) {
  try {
    const res = await fetch(path, options);
    let text = "";
    try { text = await res.text(); } catch (e) { text = ""; }
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = { message: text }; }
    }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return null;
  }
}

/** GET /manager/version — presence probe for ComfyUI-Manager. */
export async function getManagerVersion() {
  return managerFetch("/manager/version");
}

/** POST /customnode/install/git_url — explicit user-triggered pack install. */
export async function managerInstallNode(url) {
  return managerFetch("/customnode/install/git_url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

/** GET /customnode/installed — match which packs are already installed. */
export async function listManagerInstalled() {
  return managerFetch("/customnode/installed");
}

/** POST /manager/reboot — only ever called from an explicit Reboot click. */
export async function managerReboot() {
  return managerFetch("/manager/reboot", { method: "POST" });
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

// ── Backend Operations API (H6 re-home) ──────────────────────────────────
//
// Request helpers for the modern Backend page's operational sections.
// These consume the SAME server routes the legacy settings panel uses.
// No state authority lives here — every helper is a fetch/normalize only.

// Workspaces (server authority: .modal_workspaces.json)

export async function listWorkspacesRegistry(apiBase) {
  return apiFetch(apiBase, "/workspaces");
}

export async function upsertWorkspace(apiBase, payload) {
  return apiFetch(apiBase, "/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function activateWorkspace(apiBase, workspaceId) {
  return apiFetch(apiBase, "/workspaces/active", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId }),
  });
}

export function workspaceSwapEndpointPath() {
  return "/workspaces/swap";
}

export function workspaceSwapStatusEndpointPath(swapId) {
  return `/workspaces/swap/${encodeURIComponent(swapId)}`;
}

export async function requestWorkspaceSwap(apiBase, payload) {
  return apiFetch(apiBase, workspaceSwapEndpointPath(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getWorkspaceSwapStatus(apiBase, swapId) {
  if (!swapId) return null;
  return apiFetch(apiBase, workspaceSwapStatusEndpointPath(swapId));
}

/** Pure: confirmed-swap request body (exact existing contract). */
export function buildSwapConfirmPayload(workspaceId, selectedKeys) {
  return {
    workspace_id: workspaceId,
    confirm: true,
    selected_keys: (selectedKeys || []).slice(),
  };
}

/** Pure: bounded progress text for a running swap job payload. */
export function swapPhaseMessage(data) {
  const phase = (data && data.phase) || "";
  if (phase === "downloading_models") {
    const msg = data.download_message || "";
    const done = data.download_completed || 0;
    const total = (data.download_total || 0) + (data.download_skipped || 0);
    return msg || `Preparing downloads\u2026 ${done}/${total}`;
  }
  if (phase === "syncing_custom_nodes") {
    return data.sync_message || "Syncing custom nodes to Modal\u2026";
  }
  if (phase === "deploying") {
    return data.deploy_message || "Deploying workspace\u2026";
  }
  return phase ? `Phase: ${String(phase).replace(/_/g, " ")}` : "";
}

/** Pure: safe display metadata for a workspace registry envelope. */
export function summarizeWorkspaces(envelope) {
  const items = (envelope && Array.isArray(envelope.workspaces)) ? envelope.workspaces : [];
  const activeId = (envelope && envelope.active_workspace_id) || null;
  let activeLabel = null;
  const rows = items.map((ws) => {
    if (activeId && ws.id === activeId && ws.label) activeLabel = ws.label;
    return {
      id: ws.id,
      label: ws.label || ws.id,
      isActive: !!activeId && ws.id === activeId,
      lastDeployStatus: ws.last_deploy_status || "idle",
      lastUsedAt: ws.last_used_at || null,
    };
  });
  if (!activeLabel && rows.length === 1) activeLabel = rows[0].label;
  return { activeId, activeLabel, rows };
}

// Deployment

export function deployStatusEndpointPath() {
  return "/deploy/status";
}

export async function getDeployStatus(apiBase) {
  return apiFetch(apiBase, deployStatusEndpointPath());
}

export async function triggerDeploy(apiBase) {
  return apiFetch(apiBase, "/deploy", { method: "POST" });
}

export async function getDeployLog(apiBase) {
  return apiFetch(apiBase, "/deploy/log");
}

/** Pure: verbatim server-truth projection of a deploy status payload. */
export function normalizeDeployStatus(data) {
  if (!data || typeof data !== "object") {
    return { state: "unknown", message: "", details: "", available: false };
  }
  const deployState = (data.deploy_state && typeof data.deploy_state === "object")
    ? data.deploy_state
    : {};
  return {
    state: String(data.state || "unknown"),
    message: String(data.message || ""),
    details: String(data.details || ""),
    comfyappVersion: deployState.comfyapp_version || null,
    deployedAt: deployState.deployed_at || null,
    hasLog: !!data.has_log,
    available: true,
  };
}

/** Pure: states in which a deploy is still in flight (no invented states). */
export function isDeployInFlight(state) {
  return state === "deploying" || state === "starting" || state === "unknown";
}

/** Pure: last N lines of a log body. */
export function tailLines(text, maxLines) {
  const n = Math.max(1, Number(maxLines) || 50);
  const lines = String(text || "").split("\n");
  return lines.slice(-n).join("\n");
}

// Credentials / auth (existing routes; values are never surfaced here)

export async function getAuthStatus(apiBase) {
  return apiFetch(apiBase, "/auth/status");
}

export function credentialEndpointPath(kind) {
  return kind === "civitai" ? "/civitai-token" : "/hf-token";
}

export async function getCredentialStatus(apiBase, kind) {
  return apiFetch(apiBase, credentialEndpointPath(kind));
}

export async function saveCredentialToken(apiBase, kind, token) {
  return apiFetch(apiBase, credentialEndpointPath(kind), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
}

/**
 * Pure: configured/not-configured from a credential GET response.
 * Deliberately discards any token material — callers can never echo it.
 */
export function credentialConfigured(data) {
  return !!(data && typeof data === "object"
    && typeof data.token === "string"
    && data.token !== "");
}

// Runtime health (read-only readiness probe)

export async function getRuntimeHealth(apiBase) {
  return apiFetch(apiBase, "/health?mode=deploy");
}

// Model-manifest repair (deployment-bootstrap prerequisite for swaps)

export async function scanManifestIssues(apiBase) {
  return apiFetch(apiBase, "/manifest/repair/scan", { method: "POST" });
}

export async function applyManifestRepairs(apiBase, updates) {
  return apiFetch(apiBase, "/manifest/repair/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ updates }),
  });
}

export async function deleteManifestPlaceholder(apiBase, folder, filename) {
  return apiFetch(apiBase, "/manifest/repair/delete-placeholder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, filename }),
  });
}

/** Pure: source-kind inference used by the repair URL editor (legacy parity). */
export function inferSourceKind(url) {
  if (/huggingface\.co/i.test(url || "")) return "huggingface";
  if (/civitai\.com/i.test(url || "")) return "civitai";
  if (/^https?:\/\//i.test(url || "")) return "direct";
  return "unknown";
}

// ── Studio Workflow Portability API (Phase G12) ─────────────────────────

/** Endpoint path builder (pure; unit-testable). */
export function portabilityEndpointPath(versionId) {
  return `/studio/workflows/versions/${encodeURIComponent(versionId)}/portability`;
}

/** Endpoint path builder for manifest export (pure; unit-testable). */
export function exportManifestEndpointPath(versionId, includePresets) {
  return `/studio/workflows/versions/${encodeURIComponent(versionId)}/export` +
    `?include_presets=${includePresets ? "1" : "0"}`;
}

/** Query string for import-manifest (pure; unit-testable). */
export function importManifestQuery(dryRun) {
  return "?dry_run=" + (dryRun ? "1" : "0");
}

/**
 * Fetch the G5 portability report for one immutable version.
 * Response envelope: { status:"ok", portability: report }.
 */
export async function getVersionPortability(apiBase, versionId) {
  return apiFetch(apiBase, portabilityEndpointPath(versionId));
}

function _contentDispositionFilename(header) {
  if (!header) return "";
  const ext = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (ext) {
    try { return decodeURIComponent(ext[1].trim()); } catch (e) { /* fall through */ }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain ? plain[1].trim() : "";
}

/**
 * Read-only Workflow manifest export download.
 * Returns { ok:true, blob, filename } on success or
 * { ok:false, status, message } on failure. The backend is the manifest
 * authority — no manifest JSON is built in the browser.
 */
export async function fetchWorkflowManifestExport(apiBase, versionId, includePresets) {
  const path = exportManifestEndpointPath(versionId, includePresets);
  try {
    const res = await fetch(`${apiBase}${path}`);
    if (!res.ok) {
      let payload = null;
      try { payload = await res.json(); } catch (e) { payload = null; }
      const message = (payload && payload.message)
        || (payload && payload.error)
        || "HTTP " + res.status;
      return { ok: false, status: res.status, message };
    }
    const blob = await res.blob();
    const filename = _contentDispositionFilename(res.headers.get("Content-Disposition"));
    return { ok: true, status: res.status, blob, filename };
  } catch (e) {
    return { ok: false, status: 0, message: "network error" };
  }
}

/**
 * Manifest import (dry-run preview by default).
 * body may be a parsed manifest object OR raw text (invalid JSON reaches the
 * backend so IT stays the authority on malformed manifests). On commit
 * (dryRun=false) the two frozen policy fields are added to the body.
 */
export async function importWorkflowManifest(apiBase, body, opts) {
  const o = opts || {};
  const dryRun = o.dryRun !== false;
  const payload = typeof body === "string"
    ? body
    : JSON.stringify(
        dryRun
          ? (body || {})
          : Object.assign({}, body || {}, {
              import_presets: !!o.importPresets,
              apply_default_preset: !!o.applyDefaultPreset,
            })
      );
  return apiFetch(apiBase, "/studio/workflows/import-manifest" + importManifestQuery(dryRun), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  });
}
