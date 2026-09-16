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

/**
 * POST /manager/queue/install — queue a KNOWN Manager pack by its record
 * (id, version, selected_version, channel, mode, repository, files, ui_id).
 * This is Manager's normal CNR install path and does NOT require the
 * dedicated allow_git_url_install flag, so it avoids the git_url 403 gate.
 */
export async function managerQueueInstall(packRecord) {
  return managerFetch("/manager/queue/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(packRecord || {}),
  });
}

/**
 * POST /manager/queue/start — explicitly start the queued installs. Manager
 * rejects form-simple content types here, so send JSON.
 */
export async function managerQueueStart() {
  return managerFetch("/manager/queue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
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

/**
 * GET /system_stats — ComfyUI's own health endpoint (ROOT-relative, not under
 * /comfymodal). Used to detect that the ComfyUI process is back after an
 * explicit Manager reboot. Bounded by an AbortController so a hung socket can
 * never stall the wizard. Returns null on transport failure/timeout.
 */
export async function getComfySystemStats(timeoutMs) {
  const ms = Number.isFinite(timeoutMs) && timeoutMs > 0 ? timeoutMs : 5000;
  let timer = null;
  try {
    const controller = typeof AbortController === "function" ? new AbortController() : null;
    if (controller) timer = setTimeout(() => controller.abort(), ms);
    const res = await fetch("/system_stats", controller ? { signal: controller.signal } : undefined);
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    return { ok: res.ok, status: res.status, data };
  } catch (e) {
    return null;
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export const REBOOT_RECONNECT_TIMEOUT_MS = 90000;
export const REBOOT_RECONNECT_INTERVAL_MS = 2000;

/**
 * Explicit-reboot completion probe. Fires the reboot request, then treats the
 * expected connection drop as normal: it waits (bounded) for ComfyUI to
 * reconnect by polling /system_stats, and — when Manager was detected before
 * the reboot — waits for /manager/version to answer again.
 *
 * Resolution is only decided by the probes, never by the reboot POST itself:
 * a transport failure/timeout on POST is expected and ignored. Failure is
 * reported only after the shared timeout is exhausted.
 *
 * All side-effect seams are injectable (reboot/probeSystem/probeManager/
 * now/sleep) so the reconnect contract is unit-testable without timers.
 *
 * @returns {{ok: boolean, phase: "reconnect"|"manager"|"ready", message: string}}
 */
export async function managerRebootAndWait(options) {
  const o = options || {};
  const now = typeof o.now === "function" ? o.now : () => Date.now();
  const sleep = typeof o.sleep === "function"
    ? o.sleep
    : (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const doReboot = typeof o.reboot === "function" ? o.reboot : managerReboot;
  const probeSystem = typeof o.probeSystem === "function" ? o.probeSystem : getComfySystemStats;
  const probeManager = typeof o.probeManager === "function" ? o.probeManager : getManagerVersion;
  const expectManager = o.expectManager === true;
  const timeoutMs = Number.isFinite(o.timeoutMs) && o.timeoutMs > 0
    ? o.timeoutMs
    : REBOOT_RECONNECT_TIMEOUT_MS;
  const intervalMs = Number.isFinite(o.intervalMs) && o.intervalMs > 0
    ? o.intervalMs
    : REBOOT_RECONNECT_INTERVAL_MS;
  const onPhase = typeof o.onPhase === "function" ? o.onPhase : null;

  // The reboot POST very often drops the connection; that is the expected
  // shape of a successful reboot, so it is never treated as a failure.
  try { await doReboot(); } catch (e) { /* expected connection drop */ }

  const deadline = now() + timeoutMs;
  if (onPhase) onPhase("reconnect");
  let systemBack = false;
  while (now() <= deadline) {
    let stats = null;
    try { stats = await probeSystem(); } catch (e) { stats = null; }
    if (stats && stats.ok) { systemBack = true; break; }
    if (now() >= deadline) break;
    await sleep(intervalMs);
  }
  if (!systemBack) {
    return {
      ok: false,
      phase: "reconnect",
      message: "ComfyUI did not reconnect after the reboot request — restart it manually if needed.",
    };
  }

  if (expectManager) {
    if (onPhase) onPhase("manager");
    let managerBack = false;
    while (now() <= deadline) {
      let version = null;
      try { version = await probeManager(); } catch (e) { version = null; }
      if (version && version.ok) { managerBack = true; break; }
      if (now() >= deadline) break;
      await sleep(intervalMs);
    }
    if (!managerBack) {
      return {
        ok: false,
        phase: "manager",
        message: "ComfyUI reconnected, but ComfyUI-Manager did not come back in time.",
      };
    }
  }

  return { ok: true, phase: "ready", message: "ComfyUI rebooted and reconnected." };
}

// ── Setup-wizard draft contract (bounded, namespaced) ────────────────────
//
// The version-setup wizard persists its identity + current step + bindings +
// details to sessionStorage (and a marker in the Studio URL hash) so a browser
// refresh can reopen the same workflow/version wizard at the same step.
// These pure builders/parsers live here (no DOM) so the bounded schema is
// unit-testable in Node; web/studio-preset-wizard.js owns the storage + URL
// side effects.

export const WIZARD_DRAFT_KEY = "comfymodal.studio.wizard.draft.v1";
export const WIZARD_DRAFT_SCHEMA = 1;
export const WIZARD_DRAFT_MAX_CHARS = 12000;

const WIZARD_DETAIL_NAME_MAX = 200;
const WIZARD_DETAIL_DESC_MAX = 2000;
const WIZARD_FEATURES_MAX = 8;
const WIZARD_BINDING_KEYS_MAX = 16;
const WIZARD_BINDING_STR_MAX = 80;

function _draftStr(value, max) {
  const s = typeof value === "string" ? value : (value == null ? "" : String(value));
  return s.length > max ? s.slice(0, max) : s;
}

/** Normalize one binding to the bounded draft shape; null when unusable. */
function _draftBindingValue(val) {
  if (!val || typeof val !== "object" || val.nodeId == null) return null;
  const out = {
    nodeId: val.nodeId,
    nodeType: _draftStr(val.nodeType || "", WIZARD_BINDING_STR_MAX),
    nodeTitle: _draftStr(val.nodeTitle || "", WIZARD_BINDING_STR_MAX),
  };
  if (val.widgetName) out.widgetName = _draftStr(val.widgetName, WIZARD_BINDING_STR_MAX);
  if (val.inputName) out.inputName = _draftStr(val.inputName, WIZARD_BINDING_STR_MAX);
  if (val.outputIndex != null) out.outputIndex = val.outputIndex;
  if (!out.widgetName && !out.inputName && out.outputIndex == null) return null;
  return out;
}

/**
 * Bounded draft for a version-setup wizard. Returns null for any other mode
 * (preset/edit wizards are not resumed by the workflows page).
 */
export function buildWizardDraft(state) {
  if (!state || !state.isVersionSetup) return null;
  const workflowId = _draftStr(state.workflowId || "", WIZARD_BINDING_STR_MAX);
  const workflowVersionId = _draftStr(state.workflowVersionId || "", WIZARD_BINDING_STR_MAX);
  if (!workflowId || !workflowVersionId) return null;

  const bindings = {};
  let count = 0;
  Object.keys(state.bindings || {}).sort().forEach((key) => {
    if (count >= WIZARD_BINDING_KEYS_MAX) return;
    const b = _draftBindingValue(state.bindings[key]);
    if (!b) return;
    bindings[_draftStr(key, WIZARD_BINDING_STR_MAX)] = b;
    count += 1;
  });

  const features = Array.isArray(state.selectedFeatures)
    ? state.selectedFeatures.map((f) => _draftStr(f, WIZARD_BINDING_STR_MAX)).filter(Boolean).slice(0, WIZARD_FEATURES_MAX)
    : [];

  return {
    v: WIZARD_DRAFT_SCHEMA,
    step: _draftStr(state.step || "", WIZARD_BINDING_STR_MAX),
    workflowId: workflowId,
    workflowVersionId: workflowVersionId,
    selectedFeatures: features,
    bindings: bindings,
    details: {
      name: _draftStr((state.details && state.details.name) || "", WIZARD_DETAIL_NAME_MAX),
      description: _draftStr((state.details && state.details.description) || "", WIZARD_DETAIL_DESC_MAX),
    },
    at: Date.now(),
  };
}

/**
 * Validate + bound an untrusted draft string. Returns null for anything that
 * is not a current-schema version-setup draft — stale/malformed storage is
 * dropped softly, never thrown.
 */
export function parseWizardDraft(raw) {
  if (typeof raw !== "string" || raw === "") return null;
  if (raw.length > WIZARD_DRAFT_MAX_CHARS * 2) return null;
  let obj = null;
  try { obj = JSON.parse(raw); } catch (e) { return null; }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null;
  if (obj.v !== WIZARD_DRAFT_SCHEMA) return null;
  const workflowId = typeof obj.workflowId === "string" ? obj.workflowId.slice(0, WIZARD_BINDING_STR_MAX) : "";
  const workflowVersionId = typeof obj.workflowVersionId === "string" ? obj.workflowVersionId.slice(0, WIZARD_BINDING_STR_MAX) : "";
  if (!workflowId || !workflowVersionId) return null;

  const bindings = {};
  if (obj.bindings && typeof obj.bindings === "object" && !Array.isArray(obj.bindings)) {
    Object.keys(obj.bindings).slice(0, WIZARD_BINDING_KEYS_MAX).forEach((key) => {
      const b = _draftBindingValue(obj.bindings[key]);
      if (b) bindings[key.slice(0, WIZARD_BINDING_STR_MAX)] = b;
    });
  }

  const features = Array.isArray(obj.selectedFeatures)
    ? obj.selectedFeatures.filter((f) => typeof f === "string").slice(0, WIZARD_FEATURES_MAX)
    : [];
  const details = obj.details && typeof obj.details === "object" && !Array.isArray(obj.details) ? obj.details : {};

  return {
    v: WIZARD_DRAFT_SCHEMA,
    step: typeof obj.step === "string" ? obj.step.slice(0, WIZARD_BINDING_STR_MAX) : "",
    workflowId: workflowId,
    workflowVersionId: workflowVersionId,
    selectedFeatures: features,
    bindings: bindings,
    details: {
      name: _draftStr(details.name || "", WIZARD_DETAIL_NAME_MAX),
      description: _draftStr(details.description || "", WIZARD_DETAIL_DESC_MAX),
    },
  };
}

/**
 * Merge a parsed draft into a fresh wizard state, but ONLY when the identity
 * matches exactly. `validSteps` is the mode's ordered step list; an unknown
 * step falls back to the freshly-computed default. Returns true when applied.
 */
export function applyWizardDraft(state, draft, validSteps) {
  if (!state || !draft || !state.isVersionSetup) return false;
  if (String(draft.workflowId) !== String(state.workflowId || "")) return false;
  if (String(draft.workflowVersionId) !== String(state.workflowVersionId || "")) return false;
  const steps = Array.isArray(validSteps) && validSteps.length
    ? validSteps
    : ["features", "dependencies", "bindings", "details"];
  if (draft.step && steps.indexOf(draft.step) !== -1) state.step = draft.step;
  if (draft.selectedFeatures && draft.selectedFeatures.length && state.selectedFeatures.length === 0) {
    state.selectedFeatures = draft.selectedFeatures.slice();
  }
  Object.keys(draft.bindings || {}).forEach((key) => {
    state.bindings[key] = Object.assign({}, draft.bindings[key]);
  });
  if (draft.details) {
    if (draft.details.name) state.details.name = draft.details.name;
    if (draft.details.description) state.details.description = draft.details.description;
  }
  return true;
}

/**
 * GET /externalmodel/getlist?mode=default — authoritative Manager model
 * catalog for source/download URLs (falls back to the cached channel only
 * when the default channel is unavailable).
 */
export async function getManagerModels() {
  const fresh = await managerFetch("/externalmodel/getlist?mode=default");
  if (fresh && fresh.ok && fresh.data && Array.isArray(fresh.data.models)) {
    return fresh.data.models;
  }
  const cached = await managerFetch("/externalmodel/getlist?mode=cache");
  if (cached && cached.ok && cached.data && Array.isArray(cached.data.models)) {
    return cached.data.models;
  }
  return [];
}

/**
 * GET /customnode/getlist?mode=default&skip_update=true — Manager custom-node
 * pack catalog. Returns the raw envelope ({ channel, node_packs }) or null.
 */
export async function getManagerPackList() {
  const res = await managerFetch("/customnode/getlist?mode=default&skip_update=true");
  return (res && res.ok && res.data) ? res.data : null;
}

/**
 * GET /customnode/getmappings?mode=default — Manager class → pack mapping.
 * Returns the raw map or null.
 */
export async function getManagerMappings() {
  const res = await managerFetch("/customnode/getmappings?mode=default");
  return (res && res.ok && res.data) ? res.data : null;
}

/** POST /comfymodal/model/install — async single download, returns download_id. */
export async function installSingleModel(apiBase, item) {
  return apiFetch(apiBase, "/model/install", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(item || {}),
  });
}

/** GET /comfymodal/download/status/{id} — poll a single download. */
export async function modelDownloadStatus(apiBase, downloadId) {
  return apiFetch(apiBase, `/download/status/${encodeURIComponent(downloadId || "")}`);
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
