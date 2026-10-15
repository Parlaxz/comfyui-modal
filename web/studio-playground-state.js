// Modal Studio ΓÇö Playground State
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
const GOLDEN_PROFILE_KEY = "comfymodal.studio.golden.profile.v1";

export function saveGoldenProfileSelection(profileName) {
  if (typeof profileName !== "string" || !profileName.trim()) return;
  try { localStorage.setItem(GOLDEN_PROFILE_KEY, profileName.trim()); } catch (e) {}
}

export function loadGoldenProfileSelection() {
  try {
    const value = localStorage.getItem(GOLDEN_PROFILE_KEY);
    return typeof value === "string" && value.trim() ? value.trim() : "";
  } catch (e) {
    return "";
  }
}

export function clearGoldenProfileSelection() {
  try { localStorage.removeItem(GOLDEN_PROFILE_KEY); } catch (e) {}
}

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
    // localStorage quota exceeded or unavailable ΓÇö silently ignore
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

// ΓöÇΓöÇ Run Result Persistence ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
//
// Persists the last successful run identity per (presetId, featureId) pair
// so that on reload the canvas image, metadata, and controls can be restored
// without waiting for server-side recent runs.
//
// Does NOT store image blobs ΓÇö only the URL reference.
//
// Key format in the results storage:
//   "presetId::featureId" ΓåÆ { id, imageUrl, resolvedControls, timingStages, ... }

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
      generationId: runData.generationId || null,
      imageUrl: runData.imageUrl || null,
      // Persisted alongside imageUrl so a reloaded canvas can resolve the
      // same full-size variant (see _canvasUrlForRun); absent on older
      // entries, which fall back to imageUrl exactly as before.
      featuredOutput: runData.featuredOutput && typeof runData.featuredOutput === "object"
        ? runData.featuredOutput : null,
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
    // localStorage quota exceeded or unavailable ΓÇö silently ignore
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

// ΓöÇΓöÇ Experiment Draft Persistence ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
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
// changes ΓÇö without requiring an experiment run.

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
    // localStorage quota exceeded or unavailable ΓÇö silently ignore
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

// ΓöÇΓöÇ Shelf Playground Persistence ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
//
// The Shelf (Studio Workflow effort, leaf 1.2.2) keeps two strictly separate
// persistence lanes:
//
//   1. Durable lane ΓÇö normal field values + field layout. Values are keyed by
//      workflow+version so a reload restores exactly what the user typed;
//      layout is keyed by workflow type (currently "t2i") so every workflow
//      of the same type shares its card order/rows/Advanced placement.
//   2. Local experiment draft lane ΓÇö experiment-only state (selected
//      workflows, axes, pills, per-workflow unique values). It lives under
//      its own key and never overwrites the durable lane.
//
// No migration: unknown/malformed payloads degrade to empty defaults.

const SHELF_LAYOUT_KEY = "comfymodal.studio.shelf.layout.v1";
const SHELF_VALUES_KEY = "comfymodal.studio.shelf.values.v1";
const SHELF_EXPERIMENT_DRAFT_KEY = "comfymodal.studio.shelf.experiment.v1";
const SKIP_TEXT_GENERATE_KEY = "comfymodal.studio.playground.skip-text-generate.v1";

function _shelfValuesKey(workflowId, versionId) {
  return `${workflowId || ""}::${versionId || ""}`;
}

/**
 * Load the autosaved Shelf layout for a workflow type.
 * @param {string} workflowType
 * @returns {{order: string[], rows: object, advanced: string[]}|null}
 */
export function loadShelfLayout(workflowType) {
  if (!workflowType) return null;
  try {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(SHELF_LAYOUT_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return null;
    const entry = all[String(workflowType)];
    if (!entry || typeof entry !== "object") return null;
    return {
      order: Array.isArray(entry.order) ? entry.order.filter((r) => typeof r === "string") : [],
      rows: entry.rows && typeof entry.rows === "object" ? _deepCloneObject(entry.rows) : {},
      advanced: Array.isArray(entry.advanced) ? entry.advanced.filter((r) => typeof r === "string") : [],
    };
  } catch (e) {
    return null;
  }
}

/**
 * Autosave the Shelf layout for a workflow type. No Save button exists;
 * callers persist on every order/row/Advanced change.
 * @param {string} workflowType
 * @param {{order?: string[], rows?: object, advanced?: string[]}} layout
 */
export function saveShelfLayout(workflowType, layout) {
  if (!workflowType || !layout || typeof layout !== "object") return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(SHELF_LAYOUT_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};
    store[String(workflowType)] = {
      order: Array.isArray(layout.order) ? layout.order.filter((r) => typeof r === "string") : [],
      rows: layout.rows && typeof layout.rows === "object" ? _deepCloneObject(layout.rows) : {},
      advanced: Array.isArray(layout.advanced) ? layout.advanced.filter((r) => typeof r === "string") : [],
    };
    localStorage.setItem(SHELF_LAYOUT_KEY, JSON.stringify(store));
  } catch (e) {
    // Ignore
  }
}

/**
 * Load durably autosaved Shelf field values for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @returns {object} role ΓåÆ value (empty object when nothing saved)
 */
export function loadShelfValues(workflowId, versionId) {
  if (!workflowId) return {};
  try {
    if (typeof localStorage === "undefined") return {};
    const raw = localStorage.getItem(SHELF_VALUES_KEY);
    if (!raw) return {};
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return {};
    const entry = all[_shelfValuesKey(workflowId, versionId)];
    return entry && typeof entry === "object" ? _deepCloneObject(entry) : {};
  } catch (e) {
    return {};
  }
}

/**
 * Durably autosave Shelf field values for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @param {object} values role ΓåÆ value
 */
export function saveShelfValues(workflowId, versionId, values) {
  if (!workflowId) return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(SHELF_VALUES_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};
    store[_shelfValuesKey(workflowId, versionId)] = values && typeof values === "object"
      ? _deepCloneObject(values)
      : {};
    localStorage.setItem(SHELF_VALUES_KEY, JSON.stringify(store));
  } catch (e) {
    // Ignore
  }
}

/**
 * Remove durably autosaved Shelf field values for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 */
export function clearShelfValues(workflowId, versionId) {
  if (!workflowId) return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(SHELF_VALUES_KEY);
    if (!raw) return;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return;
    delete all[_shelfValuesKey(workflowId, versionId)];
    localStorage.setItem(SHELF_VALUES_KEY, JSON.stringify(all));
  } catch (e) {
    // Ignore
  }
}

/**
 * Load the persisted TextGenerate-skip toggle for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @returns {boolean} false when nothing saved
 */
export function loadSkipTextGenerate(workflowId, versionId) {
  if (!workflowId) return false;
  try {
    if (typeof localStorage === "undefined") return false;
    const raw = localStorage.getItem(SKIP_TEXT_GENERATE_KEY);
    if (!raw) return false;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return false;
    return all[_shelfValuesKey(workflowId, versionId)] === true;
  } catch (e) {
    return false;
  }
}

/**
 * Persist the TextGenerate-skip toggle for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @param {boolean} value
 */
export function saveSkipTextGenerate(workflowId, versionId, value) {
  if (!workflowId) return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(SKIP_TEXT_GENERATE_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};
    store[_shelfValuesKey(workflowId, versionId)] = value === true;
    localStorage.setItem(SKIP_TEXT_GENERATE_KEY, JSON.stringify(store));
  } catch (e) {
    // Ignore
  }
}

/**
 * Load the local Shelf experiment draft (experiment-only state).
 * Never touches the durable values/layout lane.
 * @returns {{workflowIds: string[], axes: object, uniqueValues: object}|null}
 */
export function loadShelfExperimentDraft() {
  try {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(SHELF_EXPERIMENT_DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return {
      workflowIds: Array.isArray(parsed.workflowIds)
        ? parsed.workflowIds.filter((id) => typeof id === "string" && id)
        : [],
      axes: parsed.axes && typeof parsed.axes === "object" ? _deepCloneObject(parsed.axes) : {},
      uniqueValues: parsed.uniqueValues && typeof parsed.uniqueValues === "object"
        ? _deepCloneObject(parsed.uniqueValues)
        : {},
    };
  } catch (e) {
    return null;
  }
}

/**
 * Autosave the local Shelf experiment draft (experiment-only state).
 * Never overwrites durable Workflow values.
 * @param {{workflowIds?: string[], axes?: object, uniqueValues?: object}} draft
 */
export function saveShelfExperimentDraft(draft) {
  if (!draft || typeof draft !== "object") return;
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(SHELF_EXPERIMENT_DRAFT_KEY, JSON.stringify({
      workflowIds: Array.isArray(draft.workflowIds)
        ? draft.workflowIds.filter((id) => typeof id === "string" && id)
        : [],
      axes: draft.axes && typeof draft.axes === "object" ? _deepCloneObject(draft.axes) : {},
      uniqueValues: draft.uniqueValues && typeof draft.uniqueValues === "object"
        ? _deepCloneObject(draft.uniqueValues)
        : {},
    }));
  } catch (e) {
    // Ignore
  }
}

/**
 * Remove the local Shelf experiment draft.
 */
export function clearShelfExperimentDraft() {
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.removeItem(SHELF_EXPERIMENT_DRAFT_KEY);
  } catch (e) {
    // Ignore
  }
}

// ΓöÇΓöÇ Workflow Selection Persistence ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
//
// Persists the currently selected workflow/version/preset so the Playground
// can restore the exact selection across page reloads, and stores a one-shot
// "handoff" written by the Workflows page ("run this workflow/version/preset
// in the Playground") that the Playground consumes once on load.
//
// Both keys are versioned (v1) to allow future migration.

const WORKFLOW_SELECTION_STORAGE_KEY = "comfymodal.studio.playground.workflow.v1";
const WORKFLOW_HANDOFF_STORAGE_KEY = "comfymodal.studio.playground.workflow-handoff.v1";
const TOOL_WORKFLOWS_STORAGE_KEY = "comfymodal.studio.playground.tool-workflows.v1";
const TOOL_DEFAULTS_STORAGE_KEY = "comfymodal.studio.playground.tool-defaults.v1";

function _readJsonMap(key) {
  try {
    if (typeof localStorage !== "undefined") {
      const raw = localStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") return parsed;
      }
    }
  } catch (e) { /* fall through to session fallback */ }
  try {
    if (typeof sessionStorage !== "undefined") {
      const raw = sessionStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object") return parsed;
      }
    }
  } catch (e) { /* ignore */ }
  return {};
}

function _writeJsonMap(key, map) {
  const clean = map && typeof map === "object" ? map : {};
  try {
    if (typeof localStorage !== "undefined") {
      localStorage.setItem(key, JSON.stringify(clean));
    }
  } catch (e) { /* quota/unavailable — silently ignore */ }
}

/**
 * Load the remembered last-selected workflow per tool.
 * Durable in localStorage so it survives refresh; older sessionStorage
 * values migrate forward on first read.
 * @returns {object} { [toolId]: workflowId }
 */
export function loadToolWorkflows() {
  return _readJsonMap(TOOL_WORKFLOWS_STORAGE_KEY);
}

/**
 * Persist the remembered last-selected workflow per tool.
 * @param {object} map { [toolId]: workflowId }
 */
export function saveToolWorkflows(map) {
  _writeJsonMap(TOOL_WORKFLOWS_STORAGE_KEY, map);
}

/**
 * Load the explicit default workflow per tool (marked in Workflows tab).
 * @returns {object} { [toolId]: workflowId }
 */
export function loadToolDefaults() {
  return _readJsonMap(TOOL_DEFAULTS_STORAGE_KEY);
}

/**
 * Load the explicit default workflow id for one tool.
 * @param {string} toolId
 * @returns {string} workflow id or ""
 */
export function loadToolDefault(toolId) {
  if (!toolId) return "";
  const id = _readJsonMap(TOOL_DEFAULTS_STORAGE_KEY)[String(toolId)];
  return typeof id === "string" && id ? id : "";
}

/**
 * Mark (or replace) the explicit default workflow for one tool.
 * @param {string} toolId
 * @param {string} workflowId
 */
export function saveToolDefault(toolId, workflowId) {
  if (!toolId || !workflowId) return;
  const all = _readJsonMap(TOOL_DEFAULTS_STORAGE_KEY);
  all[String(toolId)] = String(workflowId);
  _writeJsonMap(TOOL_DEFAULTS_STORAGE_KEY, all);
}

/**
 * Clear the explicit default for one tool, or drop references to a deleted
 * workflow id across all tools when toolId is empty.
 * @param {string} toolId
 * @param {string} workflowId
 */
export function clearToolDefault(toolId, workflowId) {
  const all = _readJsonMap(TOOL_DEFAULTS_STORAGE_KEY);
  if (!toolId && !workflowId) return;
  if (!toolId && workflowId) {
    let changed = false;
    Object.keys(all).forEach((tool) => {
      if (String(all[tool]) === String(workflowId)) {
        delete all[tool];
        changed = true;
      }
    });
    if (changed) _writeJsonMap(TOOL_DEFAULTS_STORAGE_KEY, all);
    return;
  }
  if (toolId && Object.prototype.hasOwnProperty.call(all, String(toolId))) {
    delete all[String(toolId)];
    _writeJsonMap(TOOL_DEFAULTS_STORAGE_KEY, all);
  }
}

/**
 * Normalize a raw selection/handoff object into the canonical string-field
 * shape. Returns null for non-object input.
 * @param {*} raw
 * @returns {{workflowId: string, workflowVersionId: string, workflowName: string}|null}
 */
function _sanitizeSelectionFields(raw) {
  if (!raw || typeof raw !== "object") return null;
  return {
    workflowId: typeof raw.workflowId === "string" ? raw.workflowId : "",
    workflowVersionId: typeof raw.workflowVersionId === "string" ? raw.workflowVersionId : "",
    workflowName: typeof raw.workflowName === "string" ? raw.workflowName : "",
  };
}

/**
 * Save the current workflow selection to localStorage.
 * @param {{workflowId?: string, workflowVersionId?: string, workflowName?: string}} sel
 */
export function saveWorkflowSelection(sel) {
  const clean = _sanitizeSelectionFields(sel);
  if (!clean) return;
  try {
    if (typeof localStorage === "undefined") return;
    localStorage.setItem(WORKFLOW_SELECTION_STORAGE_KEY, JSON.stringify(clean));
  } catch (e) {
    // localStorage quota exceeded or unavailable ΓÇö silently ignore
  }
}

/**
 * Load the persisted workflow selection from localStorage.
 * @returns {{workflowId: string, workflowVersionId: string, workflowName: string}|null}
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
 * @returns {{workflowId: string, workflowVersionId: string, workflowName: string}|null}
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

// ── Phase 1 visible shell (Generate / Edit / Post Processing) ────────────
//
// The visible shell is UI organization only: exactly two values,
// activeMode + activeSubtool, persisted under one versioned key. Internal
// execution types (t2i/i2i/inpaint/outpaint/sketch/postprocess/upscale),
// draft/result keys (presetId::featureId), and the legacy tool key stay
// untouched. Unknown/malformed payloads degrade to null so callers fall
// back to the mode default or migrate from the existing tool key.

const SHELL_KEY = "comfymodal.studio.playground.shell.v1";

export const SHELL_MODES = Object.freeze(["generate", "edit", "post"]);

export const SHELL_SUBTOOLS = Object.freeze({
  generate: Object.freeze(["text", "references", "layout", "sketch", "guidance"]),
  edit: Object.freeze(["text", "references", "select", "expand", "sketch"]),
  post: Object.freeze(["adjust", "color", "detail", "effects", "crop", "heal", "upscale"]),
});

// Later-phase placeholders: visible but with no execution path. Simple
// membership list — labels live with the caller. Single source for the
// shell run gate shared by the playground topbar and experiment submits.
// Phase 9 implements Guidance, so only Upscale remains placeholder here.
export const SHELL_PLACEHOLDERS = Object.freeze(["upscale"]);

/**
 * Honest execution gate for views with no runnable workflow path: Post
 * (local engine) and later-phase placeholders. Returns the user-facing
 * reason, or null when the normal workflow path applies. Unknown input
 * fails open (null) so callers never block on a not-yet-restored shell.
 * @param {string} mode
 * @param {string} subtool
 * @returns {string|null}
 */
export function shellGateReason(mode, subtool) {
  if (mode === "post") {
    if (subtool === "upscale") return "Upscale arrives in a later phase — execution is disabled.";
    if (SHELL_SUBTOOLS.post.indexOf(subtool) !== -1) {
      return "Post Processing runs locally — use Save or Export in the editor below.";
    }
    return null;
  }
  if (SHELL_PLACEHOLDERS.indexOf(subtool) !== -1) {
    if (mode === "generate" || mode === "edit") {
      var labels = { references: "References", layout: "Layout", guidance: "Guidance", upscale: "Upscale" };
      return (labels[subtool] || subtool) + " arrives in a later phase — execution is disabled.";
    }
    return null;
  }
  return null;
}

/**
 * Load the persisted visible shell selection.
 * @returns {{mode: string, subtool: string}|null} null when missing/invalid
 */
export function loadShellSelection() {
  try {
    if (typeof localStorage === "undefined") return null;
    const raw = localStorage.getItem(SHELL_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const mode = typeof parsed.mode === "string" ? parsed.mode : "";
    const subtool = typeof parsed.subtool === "string" ? parsed.subtool : "";
    if (SHELL_MODES.indexOf(mode) === -1) return null;
    if (SHELL_SUBTOOLS[mode].indexOf(subtool) === -1) return null;
    return { mode, subtool };
  } catch (e) {
    return null;
  }
}

/**
 * Persist the visible shell selection. Invalid pairs are ignored.
 * @param {string} mode
 * @param {string} subtool
 */
export function saveShellSelection(mode, subtool) {
  try {
    if (typeof localStorage === "undefined") return;
    if (SHELL_MODES.indexOf(mode) === -1) return;
    if (SHELL_SUBTOOLS[mode].indexOf(subtool) === -1) return;
    localStorage.setItem(SHELL_KEY, JSON.stringify({ mode, subtool }));
  } catch (e) {
    // Ignore
  }
}
// One-shot "use as base" parameter payload (a past run's prompt + sampler
// controls) for the Playground shelf. Deliberately IN-MEMORY, not
// localStorage: it is consumed by the next shelf build in this session,
// and a stale base must never resurrect after a reload.
let _pendingPlaygroundBase = null;

/**
 * Stash a base payload for the next Playground shelf build.
 * @param {object|null|undefined} payload shelf-role keyed values
 */
export function setPendingPlaygroundBase(payload) {
  _pendingPlaygroundBase = payload && typeof payload === "object" ? payload : null;
}

/**
 * Take the stashed base payload, clearing the slot. Exactly-once: a second
 * call returns null until stashed again.
 * @returns {object|null}
 */
export function takePendingPlaygroundBase() {
  const pending = _pendingPlaygroundBase;
  _pendingPlaygroundBase = null;
  return pending;
}

// One-shot image handoff (a past run's output URL + purpose) for the
// Playground. Same exactly-once in-memory discipline as the base payload:
// {url: string, purpose: "current"|"edit-source"|"post", mode: string|null,
// subtool: string|null}. The mode/subtool preselects the destination view
// (Edit/Text, Post/adjust, Post/upscale); null means stay where you are.
// Unknown purposes degrade to "current" at consume time; empty URLs are
// dropped here.
let _pendingPlaygroundImage = null;

/**
 * Stash an image handoff for the next Playground build.
 * @param {{url?: string, purpose?: string, mode?: string, subtool?: string}|null|undefined} payload
 */
export function setPendingPlaygroundImage(payload) {
  var url = payload && typeof payload.url === "string" ? payload.url : "";
  if (!url) {
    _pendingPlaygroundImage = null;
    return;
  }
  var purpose = payload && typeof payload.purpose === "string" ? payload.purpose : "current";
  if (purpose !== "current" && purpose !== "edit-source" && purpose !== "post") purpose = "current";
  var mode = payload && typeof payload.mode === "string" && payload.mode ? payload.mode : null;
  var subtool = payload && typeof payload.subtool === "string" && payload.subtool ? payload.subtool : null;
  _pendingPlaygroundImage = { url: url, purpose: purpose, mode: mode, subtool: subtool };
}

/**
 * Take the stashed image handoff, clearing the slot.
 * @returns {{url: string, purpose: string, mode: string|null, subtool: string|null}|null}
 */
export function takePendingPlaygroundImage() {
  const pending = _pendingPlaygroundImage;
  _pendingPlaygroundImage = null;
  return pending;
}

// ── Per-workflow explicit method preferences ────────────────────────────
//
// Explicit inpaint/expand method + override + expand-pad preferences,
// keyed by workflow id so each workflow remembers its own selection.
// Persists under one versioned localStorage key in the existing style.
// Unknown/malformed payloads degrade to defaults; merge-patch ignores
// unknown keys and invalid workflow ids. No UI, run, or backend logic.

const WORKFLOW_METHODS_KEY = "comfymodal.studio.methods.v1";

const WORKFLOW_INPAINT_METHODS = ["crop_stitch", "conditioning", "dedicated"];
const WORKFLOW_EXPAND_METHODS = ["pad", "pad_preserve", "dedicated"];
// Phase 8 reference methods (Lane C). Frozen ids mirroring
// studio_domain/models.py REFERENCE_METHOD_IDS. No Auto: "" means the user
// has not chosen yet and the run gate requires an explicit choice.
export const WORKFLOW_REFERENCE_METHODS = Object.freeze([
  "conditioning_slots",
  "reference_latent_chain",
  "dedicated",
]);
const WORKFLOW_METHOD_KEYS = [
  "inpaintMethod",
  "inpaintOverride",
  "expandMethod",
  "expandOverride",
  "padTop",
  "padRight",
  "padBottom",
  "padLeft",
  "savedMask",
  "savedMaskSource",
  "referenceMethod",
  "referenceOverride",
];

/**
 * Fresh defaults for per-workflow method preferences.
 * @returns {{inpaintMethod: string, inpaintOverride: string, expandMethod: string, expandOverride: string, padTop: number, padRight: number, padBottom: number, padLeft: number}}
 */
function _defaultWorkflowMethods() {
  return {
    inpaintMethod: "crop_stitch",
    inpaintOverride: "",
    expandMethod: "pad_preserve",
    expandOverride: "",
    padTop: 0,
    padRight: 256,
    padBottom: 0,
    padLeft: 0,
    savedMask: "",
    savedMaskSource: "",
    referenceMethod: "",
    referenceOverride: "",
  };
}

/**
 * Sanitize a pad value to a non-negative int, falling back on mismatch.
 * @param {*} value
 * @param {number} fallback
 * @returns {number}
 */
function _sanitizePadInt(value, fallback) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.floor(value));
  }
  if (typeof value === "string" && value.trim() !== "") {
    const num = Number(value);
    if (Number.isFinite(num)) return Math.max(0, Math.floor(num));
  }
  return fallback;
}

/**
 * Sanitize a raw methods entry into the canonical shape with defaults.
 * @param {*} raw
 * @returns {{inpaintMethod: string, inpaintOverride: string, expandMethod: string, expandOverride: string, padTop: number, padRight: number, padBottom: number, padLeft: number}}
 */
function _sanitizeWorkflowMethods(raw) {
  const defaults = _defaultWorkflowMethods();
  if (!raw || typeof raw !== "object") return defaults;
  return {
    inpaintMethod: WORKFLOW_INPAINT_METHODS.indexOf(raw.inpaintMethod) !== -1
      ? raw.inpaintMethod
      : defaults.inpaintMethod,
    inpaintOverride: typeof raw.inpaintOverride === "string" ? raw.inpaintOverride : "",
    expandMethod: WORKFLOW_EXPAND_METHODS.indexOf(raw.expandMethod) !== -1
      ? raw.expandMethod
      : defaults.expandMethod,
    expandOverride: typeof raw.expandOverride === "string" ? raw.expandOverride : "",
    padTop: _sanitizePadInt(raw.padTop, defaults.padTop),
    padRight: _sanitizePadInt(raw.padRight, defaults.padRight),
    padBottom: _sanitizePadInt(raw.padBottom, defaults.padBottom),
    padLeft: _sanitizePadInt(raw.padLeft, defaults.padLeft),
    savedMask: typeof raw.savedMask === "string" ? raw.savedMask : "",
    savedMaskSource: typeof raw.savedMaskSource === "string" ? raw.savedMaskSource : "",
    // Explicit-choice field: anything outside the frozen ids degrades to ""
    // (not to a default method), so the run gate keeps requiring a choice
    // instead of silently auto-selecting.
    referenceMethod: WORKFLOW_REFERENCE_METHODS.indexOf(raw.referenceMethod) !== -1
      ? raw.referenceMethod
      : "",
    referenceOverride: typeof raw.referenceOverride === "string" ? raw.referenceOverride : "",
  };
}

/**
 * Read the raw methods map ({[workflowId]: entry}) or {} on any failure.
 * @returns {object}
 */
function _readWorkflowMethodsStore() {
  try {
    if (typeof localStorage === "undefined") return {};
    const raw = localStorage.getItem(WORKFLOW_METHODS_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return parsed;
  } catch (e) {
    return {};
  }
}

/**
 * Load sanitized per-workflow method preferences.
 * Unknown workflowId or malformed storage yields defaults.
 * @param {string} workflowId
 * @returns {{inpaintMethod: string, inpaintOverride: string, expandMethod: string, expandOverride: string, padTop: number, padRight: number, padBottom: number, padLeft: number}}
 */
export function loadWorkflowMethods(workflowId) {
  if (typeof workflowId !== "string" || !workflowId) return _defaultWorkflowMethods();
  const store = _readWorkflowMethodsStore();
  return _sanitizeWorkflowMethods(store[workflowId]);
}

/**
 * Merge-patch known method keys for one workflow id and persist.
 * Unknown keys and invalid ids are ignored; values are sanitized.
 * @param {string} workflowId
 * @param {object} patch
 */
export function saveWorkflowMethods(workflowId, patch) {
  if (typeof workflowId !== "string" || !workflowId) return;
  if (!patch || typeof patch !== "object") return;
  try {
    if (typeof localStorage === "undefined") return;
    const store = _readWorkflowMethodsStore();
    const next = _sanitizeWorkflowMethods(store[workflowId]);
    if (Object.prototype.hasOwnProperty.call(patch, "inpaintMethod")
      && WORKFLOW_INPAINT_METHODS.indexOf(patch.inpaintMethod) !== -1) {
      next.inpaintMethod = patch.inpaintMethod;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "inpaintOverride")
      && typeof patch.inpaintOverride === "string") {
      next.inpaintOverride = patch.inpaintOverride;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "expandMethod")
      && WORKFLOW_EXPAND_METHODS.indexOf(patch.expandMethod) !== -1) {
      next.expandMethod = patch.expandMethod;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "expandOverride")
      && typeof patch.expandOverride === "string") {
      next.expandOverride = patch.expandOverride;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "padTop")) {
      next.padTop = _sanitizePadInt(patch.padTop, next.padTop);
    }
    if (Object.prototype.hasOwnProperty.call(patch, "padRight")) {
      next.padRight = _sanitizePadInt(patch.padRight, next.padRight);
    }
    if (Object.prototype.hasOwnProperty.call(patch, "padBottom")) {
      next.padBottom = _sanitizePadInt(patch.padBottom, next.padBottom);
    }
    if (Object.prototype.hasOwnProperty.call(patch, "padLeft")) {
      next.padLeft = _sanitizePadInt(patch.padLeft, next.padLeft);
    }
    if (Object.prototype.hasOwnProperty.call(patch, "savedMask")
      && typeof patch.savedMask === "string") {
      next.savedMask = patch.savedMask;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "savedMaskSource")
      && typeof patch.savedMaskSource === "string") {
      next.savedMaskSource = patch.savedMaskSource;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "referenceMethod")
      && WORKFLOW_REFERENCE_METHODS.indexOf(patch.referenceMethod) !== -1) {
      next.referenceMethod = patch.referenceMethod;
    }
    if (Object.prototype.hasOwnProperty.call(patch, "referenceOverride")
      && typeof patch.referenceOverride === "string") {
      next.referenceOverride = patch.referenceOverride;
    }
    void WORKFLOW_METHOD_KEYS;
    store[workflowId] = next;
    localStorage.setItem(WORKFLOW_METHODS_KEY, JSON.stringify(store));
  } catch (e) {
    // Ignore
  }
}

// ── Per-workflow+version reference cards (Phase 8, Lane C) ─────────────
// Ordered reference collection, separate from ordinary mapped controls:
// never global reference_1..10 controls. Cards are {id, file, label} with a
// stable internal id; display numbering follows submitted (array) order.
// Keyed by workflow+version like the shelf values. Structural bindings live
// in the Mapping (Lane A); this store keeps only the user's card values.
// Shape normalization (id generation, ordering helpers) lives in
// studio-workflow-run.js; here only structural filtering so malformed
// storage degrades to [] and callers normalize after load.

const REFERENCES_VALUES_KEY = "comfymodal.studio.references.v1";

function _referenceCardsKey(workflowId, versionId) {
  return String(workflowId || "") + "::" + String(versionId || "");
}

function _filterReferenceCards(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    out.push({
      id: typeof item.id === "string" ? item.id.slice(0, 80) : "",
      file: typeof item.file === "string" ? item.file.slice(0, 500) : "",
      label: typeof item.label === "string" ? item.label.slice(0, 80) : "",
    });
  }
  return out;
}

/**
 * Load the reference cards for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @returns {Array<{id: string, file: string, label: string}>} [] when nothing saved
 */
export function loadReferenceCards(workflowId, versionId) {
  if (typeof workflowId !== "string" || !workflowId) return [];
  try {
    if (typeof localStorage === "undefined") return [];
    const raw = localStorage.getItem(REFERENCES_VALUES_KEY);
    if (!raw) return [];
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return [];
    return _filterReferenceCards(all[_referenceCardsKey(workflowId, versionId)]);
  } catch (e) {
    return [];
  }
}

/**
 * Persist the reference cards for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 * @param {Array} cards ordered card list
 */
export function saveReferenceCards(workflowId, versionId, cards) {
  if (typeof workflowId !== "string" || !workflowId) return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(REFERENCES_VALUES_KEY);
    const all = raw ? JSON.parse(raw) : {};
    const store = all && typeof all === "object" ? all : {};
    store[_referenceCardsKey(workflowId, versionId)] = _filterReferenceCards(cards);
    localStorage.setItem(REFERENCES_VALUES_KEY, JSON.stringify(store));
  } catch (e) {
    // Ignore
  }
}

/**
 * Remove the reference cards for a workflow+version.
 * @param {string} workflowId
 * @param {string} versionId
 */
export function clearReferenceCards(workflowId, versionId) {
  if (typeof workflowId !== "string" || !workflowId) return;
  try {
    if (typeof localStorage === "undefined") return;
    const raw = localStorage.getItem(REFERENCES_VALUES_KEY);
    if (!raw) return;
    const all = JSON.parse(raw);
    if (!all || typeof all !== "object") return;
    delete all[_referenceCardsKey(workflowId, versionId)];
    localStorage.setItem(REFERENCES_VALUES_KEY, JSON.stringify(all));
  } catch (e) {
    // Ignore
  }
}
