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
