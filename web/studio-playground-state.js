// Modal Studio — Playground State
//
// Lightweight persisted selection state for Playground.
// Persists only preset id and feature id to localStorage.
// Does NOT persist image blobs or authoritative run metadata.
//
// Key is versioned (v1) to allow future migration.

const STORAGE_KEY = "comfymodal.studio.playground.v1";
const DRAFTS_STORAGE_KEY = "comfymodal.studio.playground.drafts.v1";
const RESULTS_STORAGE_KEY = "comfymodal.studio.playground.results.v1";
const CAROUSEL_CLEARED_KEY = "comfymodal.studio.playground.carousel-cleared.v1";

function makeDraftKey(presetId, featureId) {
  return `${presetId || ""}::${featureId || ""}`;
}

/**
 * Save the selected preset id and feature id to localStorage.
 * @param {string} presetId
 * @param {string} featureId
 */
export function saveSelection(presetId, featureId) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ presetId, featureId }));
  } catch (e) {
    // localStorage quota exceeded or unavailable — silently ignore
  }
}

/**
 * Load persisted selection state from localStorage.
 * @returns {{presetId: string, featureId: string}|null}
 */
export function loadSelection() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return {
          presetId: typeof parsed.presetId === "string" ? parsed.presetId : "",
          featureId: typeof parsed.featureId === "string" ? parsed.featureId : "txt2img",
        };
      }
    }
  } catch (e) {
    // Ignore parse errors or quota issues
  }
  return null;
}

/**
 * Clear persisted selection state from localStorage.
 */
export function clearSelection() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {
    // Ignore
  }
}

/**
 * Persist the carousel-cleared flag so the carousel stays empty across
 * page refreshes until a new run completes.
 * @param {boolean} cleared
 */
export function setCarouselCleared(cleared) {
  try {
    if (cleared) {
      localStorage.setItem(CAROUSEL_CLEARED_KEY, "true");
    } else {
      localStorage.removeItem(CAROUSEL_CLEARED_KEY);
    }
  } catch (e) {
    // Ignore
  }
}

/**
 * Check whether the carousel was explicitly cleared by the user.
 * @returns {boolean}
 */
export function isCarouselCleared() {
  try {
    return localStorage.getItem(CAROUSEL_CLEARED_KEY) === "true";
  } catch (e) {
    return false;
  }
}

export function loadControlDraft(presetId, featureId) {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    if (!parsed || typeof parsed !== "object") {
      return {};
    }
    const draft = parsed[makeDraftKey(presetId, featureId)];
    return draft && typeof draft === "object" ? draft : {};
  } catch (e) {
    return {};
  }
}

export function saveControlDraft(presetId, featureId, controls) {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    const next = parsed && typeof parsed === "object" ? parsed : {};
    next[makeDraftKey(presetId, featureId)] = controls && typeof controls === "object" ? controls : {};
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(next));
  } catch (e) {
    // Ignore
  }
}

export function clearControlDraft(presetId, featureId) {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    const next = parsed && typeof parsed === "object" ? parsed : {};
    delete next[makeDraftKey(presetId, featureId)];
    localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(next));
  } catch (e) {
    // Ignore
  }
}

// ── Run Result Persistence ─────────────────────────────────────────────────
//
// Persists the last successful run identity per (presetId, featureId) pair
// so that on reload the canvas image, metadata, and controls can be restored
// without waiting for server-side recent runs.
//
// Does NOT store image blobs — only the URL reference.
//
// Key format in the results storage:
//   "presetId::featureId" → { id, imageUrl, resolvedControls, timingStages, ... }

/**
 * Save the last successful run result for a preset+feature pair.
 * Extracts the fields needed to restore canvas output, metadata, and controls.
 * @param {string} presetId
 * @param {string} featureId
 * @param {object} runData - Normalized run object (from normalizeStudioRun or _selectedRun).
 */
export function saveRunResult(presetId, featureId, runData) {
  if (!presetId || !featureId || !runData) return;
  try {
    const key = makeDraftKey(presetId, featureId);
    const raw = localStorage.getItem(RESULTS_STORAGE_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};

    store[key] = {
      id: runData.id || null,
      experimentId: runData.experimentId || null,
      imageUrl: runData.imageUrl || null,
      outputPath: runData.outputPath || null,
      prompt: runData.prompt || null,
      negativePrompt: runData.negativePrompt || null,
      resolvedControls: runData.resolvedControls || {},
      requestedControls: runData.requestedControls || {},
      presetId: presetId,
      featureId: featureId,
      status: runData.status || "completed",
      durationMs: runData.durationMs != null ? runData.durationMs : null,
      startedAt: runData.startedAt || null,
      completedAt: runData.completedAt || null,
      workflowHash: runData.workflowHash || null,
      presetLabel: runData.presetLabel || null,
      timingStages: Array.isArray(runData.timingStages) ? runData.timingStages : [],
      timingSummary: runData.timingSummary || null,
      _timingQuality: runData._timingQuality || null,
      favorite: !!runData.favorite,
      note: runData.note || "",
      noteUpdatedAt: runData.noteUpdatedAt || null,
      error: runData.error || null,
      rawTiming: runData.rawTiming || null,
      advancedTiming: runData.advancedTiming || null,
      perNodeTimings: Array.isArray(runData.perNodeTimings) ? runData.perNodeTimings : [],
      timingSources: runData.timingSources || null,
    };

    localStorage.setItem(RESULTS_STORAGE_KEY, JSON.stringify(store));
  } catch (e) {
    // localStorage quota exceeded or unavailable — silently ignore
  }
}

/**
 * Load the persisted run result for a preset+feature pair.
 * @param {string} presetId
 * @param {string} featureId
 * @returns {object|null}
 */
export function loadRunResult(presetId, featureId) {
  if (!presetId || !featureId) return null;
  try {
    const raw = localStorage.getItem(RESULTS_STORAGE_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return null;
    return all[makeDraftKey(presetId, featureId)] || null;
  } catch (e) {
    return null;
  }
}

/**
 * Remove the persisted run result for a specific preset+feature pair.
 * @param {string} presetId
 * @param {string} featureId
 */
export function clearRunResult(presetId, featureId) {
  if (!presetId || !featureId) return;
  try {
    const raw = localStorage.getItem(RESULTS_STORAGE_KEY);
    if (!raw) return;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return;
    delete all[makeDraftKey(presetId, featureId)];
    localStorage.setItem(RESULTS_STORAGE_KEY, JSON.stringify(all));
  } catch (e) {
    // Ignore
  }
}

/**
 * Clear all persisted run results.
 */
export function clearAllRunResults() {
  try {
    localStorage.removeItem(RESULTS_STORAGE_KEY);
  } catch (e) {
    // Ignore
  }
}

// ── Experiment Draft Persistence ──────────────────────────────────────────
//
// Persists experiment axes configuration and compare-preset selections
// per (presetId, featureId) pair so that experiment mode state survives
// page reloads without requiring a run to save it.
//
// Only stores validated deep-copies of experimentAxes and compareBackendIds.
// Key is versioned (v1) to allow future migration.
//
// The draft is loaded synchronously during first render after saved selection
// (see renderControlPanel in studio-playground.js).  It is persisted when
// axes values/toggles, prompt-axis first value, or compare preset selection
// changes — without requiring an experiment run.

const EXPERIMENT_DRAFT_KEY = "comfymodal.studio.experiment.draft.v1";

/**
 * Save experiment draft for a preset+feature pair.
 * Stores a validated deep-copy of experimentAxes and compareBackendIds.
 * @param {string} presetId
 * @param {string} featureId
 * @param {object} experimentAxes
 * @param {string[]} compareBackendIds
 */
export function saveExperimentDraft(presetId, featureId, experimentAxes, compareBackendIds) {
  if (!presetId || !featureId) return;
  try {
    const key = makeDraftKey(presetId, featureId);
    const raw = localStorage.getItem(EXPERIMENT_DRAFT_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};

    store[key] = {
      experimentAxes: _deepCloneObject(experimentAxes),
      compareBackendIds: Array.isArray(compareBackendIds) ? compareBackendIds.slice() : [],
    };

    localStorage.setItem(EXPERIMENT_DRAFT_KEY, JSON.stringify(store));
  } catch (e) {
    // localStorage quota exceeded or unavailable — silently ignore
  }
}

/**
 * Load experiment draft for a preset+feature pair.
 * Returns a validated deep-copy or null if no draft exists.
 * @param {string} presetId
 * @param {string} featureId
 * @returns {{experimentAxes: object, compareBackendIds: string[]}|null}
 */
export function loadExperimentDraft(presetId, featureId) {
  if (!presetId || !featureId) return null;
  try {
    const raw = localStorage.getItem(EXPERIMENT_DRAFT_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return null;
    const entry = all[makeDraftKey(presetId, featureId)];
    if (!entry || typeof entry !== "object") return null;

    const axes = (entry.experimentAxes && typeof entry.experimentAxes === "object")
      ? _deepCloneObject(entry.experimentAxes)
      : {};
    const ids = Array.isArray(entry.compareBackendIds)
      ? entry.compareBackendIds.slice()
      : [];

    return { experimentAxes: axes, compareBackendIds: ids };
  } catch (e) {
    return null;
  }
}

/**
 * Remove experiment draft for a specific preset+feature pair.
 * @param {string} presetId
 * @param {string} featureId
 */
export function clearExperimentDraft(presetId, featureId) {
  if (!presetId || !featureId) return;
  try {
    const raw = localStorage.getItem(EXPERIMENT_DRAFT_KEY);
    if (!raw) return;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return;
    const key = makeDraftKey(presetId, featureId);
    if (key in all) {
      delete all[key];
      localStorage.setItem(EXPERIMENT_DRAFT_KEY, JSON.stringify(all));
    }
  } catch (e) {
    // Ignore
  }
}

/**
 * Deep-clone a plain object (JSON-safe values only).
 * @param {*} obj
 * @returns {*}
 */
function _deepCloneObject(obj) {
  if (obj === null || obj === undefined) return {};
  if (typeof obj !== "object") return {};
  try {
    return JSON.parse(JSON.stringify(obj));
  } catch (e) {
    return {};
  }
}

// ── Workflow Selection Persistence ─────────────────────────────────────────
//
// Persists the currently selected workflow/version/preset so the Playground
// can restore the exact selection across page reloads, and stores a one-shot
// "handoff" written by the Workflows page ("run this workflow/version/preset
// in the Playground") that the Playground consumes once on load.
//
// Both keys are versioned (v1) to allow future migration.

const WORKFLOW_SELECTION_STORAGE_KEY = "comfymodal.studio.playground.workflow.v1";
const WORKFLOW_HANDOFF_STORAGE_KEY = "comfymodal.studio.playground.workflow-handoff.v1";

/**
 * Normalize a raw selection/handoff object into the canonical string-field
 * shape. Returns null for non-object input.
 * @param {*} raw
 * @returns {{workflowId: string, workflowVersionId: string, presetId: string, workflowName: string, presetName: string}|null}
 */
function _sanitizeSelectionFields(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    workflowId: typeof raw.workflowId === "string" ? raw.workflowId : "",
    workflowVersionId: typeof raw.workflowVersionId === "string" ? raw.workflowVersionId : "",
    presetId: typeof raw.presetId === "string" ? raw.presetId : "",
    workflowName: typeof raw.workflowName === "string" ? raw.workflowName : "",
    presetName: typeof raw.presetName === "string" ? raw.presetName : "",
  };
}

/**
 * Save the current workflow selection to localStorage.
 * @param {{workflowId?: string, workflowVersionId?: string, presetId?: string, workflowName?: string, presetName?: string}} sel
 */
export function saveWorkflowSelection(sel) {
  const clean = _sanitizeSelectionFields(sel);
  if (!clean) return;
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(WORKFLOW_SELECTION_STORAGE_KEY, JSON.stringify(clean));
  } catch (e) {
    // localStorage quota exceeded or unavailable — silently ignore
  }
}

/**
 * Load the persisted workflow selection from localStorage.
 * @returns {{workflowId: string, workflowVersionId: string, presetId: string, workflowName: string, presetName: string}|null}
 */
export function loadWorkflowSelection() {
  try {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(WORKFLOW_SELECTION_STORAGE_KEY);
    if (!raw) return null;
    return _sanitizeSelectionFields(JSON.parse(raw));
  } catch (e) {
    // Ignore parse errors or quota issues
  }
  return null;
}

/**
 * Clear the persisted workflow selection from localStorage.
 */
export function clearWorkflowSelection() {
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.removeItem(WORKFLOW_SELECTION_STORAGE_KEY);
  } catch (e) {
    // Ignore
  }
}

/**
 * Persist a one-shot workflow handoff (from the Workflows page) that the
 * Playground consumes on load via takeWorkflowHandoff().
 * @param {{workflowId?: string, workflowVersionId?: string, presetId?: string, workflowName?: string, presetName?: string}} sel
 */
export function saveWorkflowHandoff(sel) {
  const clean = _sanitizeSelectionFields(sel);
  if (!clean) return;
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(WORKFLOW_HANDOFF_STORAGE_KEY, JSON.stringify(clean));
  } catch (e) {
    // Ignore
  }
}

/**
 * Read and remove the one-shot workflow handoff. The write is consumed
 * exactly once: the value is returned AND deleted from localStorage.
 * @returns {{workflowId: string, workflowVersionId: string, presetId: string, workflowName: string, presetName: string}|null}
 */
export function takeWorkflowHandoff() {
  try {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(WORKFLOW_HANDOFF_STORAGE_KEY);
    if (!raw) return null;
    localStorage.removeItem(WORKFLOW_HANDOFF_STORAGE_KEY);
    return _sanitizeSelectionFields(JSON.parse(raw));
  } catch (e) {
    return null;
  }
}
