// Modal Studio — Playground State
//
// Lightweight persisted selection state for Playground.
// Persists only preset id and feature id to localStorage.
// Does NOT persist image blobs or authoritative run metadata.
//
// Key is versioned (v1) to allow future migration.

const STORAGE_KEY = "comfymodal.studio.playground.v1";

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
