// Modal Studio — Output Preferences
//
// Shared output configuration helpers used by both Legacy Settings panel
// (modal-settings.js) and Studio Settings panel (studio-settings.js).
//
// Uses the same localStorage storage keys as the existing modal-settings.js
// code and /comfymodal/config as the server-side authority.
// Both settings surfaces call the same persistence functions so changes
// from one surface are immediately reflected in the other on next access.
//
// Functions are idempotent and safe to call multiple times.

const MODAL_PREFIX = "/comfymodal";

export const STORAGE_KEYS = {
  OUTPUT_FORMAT: "comfymodal_output_format",
  QUALITY: "comfymodal_quality",
  WEBP_LC: "comfymodal_webp_lossless_compression",
  AUTOSAVE: "comfymodal_auto_save_local",
  SAVEFOLDER: "comfymodal_save_folder",
  SIDECAR: "comfymodal_save_metadata_sidecar",
};

export const DEFAULT_OUTPUT_SAVEFOLDER = "output/modal";

/**
 * Normalize a save folder path: strip leading ./, convert backslashes,
 * remove trailing slash, and enforce the default fallback.
 * @param {string} savedFolder
 * @returns {string}
 */
export function normalizeOutputSaveFolder(savedFolder) {
  var normalized = String(savedFolder || "")
    .replace(/\\/g, "/")
    .replace(/^\.?\//, "")
    .replace(/\/+$/, "");
  if (!normalized || normalized.toLowerCase() === "comfyui/output/modal") {
    return DEFAULT_OUTPUT_SAVEFOLDER;
  }
  return normalized;
}

/**
 * Read current output preferences from localStorage.
 * Falls back to values from /comfymodal/config if localStorage is empty.
 * Returns a plain object with all output preference keys.
 */
export function getOutputPreferences() {
  var prefs = {
    output_format: localStorage.getItem(STORAGE_KEYS.OUTPUT_FORMAT) || "original",
    quality: parseInt(localStorage.getItem(STORAGE_KEYS.QUALITY), 10) || 75,
    webp_lossless_compression: localStorage.getItem(STORAGE_KEYS.WEBP_LC) || "balanced",
    auto_save_local: localStorage.getItem(STORAGE_KEYS.AUTOSAVE) === "true",
    save_folder: normalizeOutputSaveFolder(localStorage.getItem(STORAGE_KEYS.SAVEFOLDER)),
    save_metadata_sidecar: localStorage.getItem(STORAGE_KEYS.SIDECAR) !== "false",
  };
  return prefs;
}

/**
 * Write output preferences to localStorage and update the shared window
 * variable. Optionally syncs to the server.
 * @param {object} prefs - Partial preferences object to merge.
 * @param {boolean} [syncToServer=true] - Whether to POST to /comfymodal/config.
 * @returns {object} The merged preferences object.
 */
export async function setOutputPreferences(prefs, syncToServer) {
  if (syncToServer === undefined) syncToServer = true;
  var current = getOutputPreferences();
  var merged = {};
  for (var k in current) {
    if (Object.prototype.hasOwnProperty.call(current, k)) {
      merged[k] = current[k];
    }
  }
  for (var k2 in prefs) {
    if (Object.prototype.hasOwnProperty.call(prefs, k2)) {
      merged[k2] = prefs[k2];
    }
  }

  // Sync to server
  if (syncToServer) {
    try {
      var response = await fetch(MODAL_PREFIX + "/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_format: merged.output_format,
          quality: merged.quality,
          webp_lossless_compression: merged.webp_lossless_compression,
          auto_save_local: merged.auto_save_local,
          save_folder: merged.save_folder,
          save_metadata_sidecar: merged.save_metadata_sidecar,
        }),
      });
      if (!response.ok) throw new Error("Output preferences were rejected");
    } catch (e) {
      throw e;
    }
  }

  // The server is authoritative: only publish local state after persistence
  // succeeds.  This also keeps both settings surfaces from observing a value
  // that the backend rejected.
  try {
    localStorage.setItem(STORAGE_KEYS.OUTPUT_FORMAT, merged.output_format);
    localStorage.setItem(STORAGE_KEYS.QUALITY, String(merged.quality));
    localStorage.setItem(STORAGE_KEYS.WEBP_LC, merged.webp_lossless_compression);
    localStorage.setItem(STORAGE_KEYS.AUTOSAVE, String(merged.auto_save_local));
    localStorage.setItem(STORAGE_KEYS.SAVEFOLDER, merged.save_folder);
    localStorage.setItem(STORAGE_KEYS.SIDECAR, String(merged.save_metadata_sidecar));
  } catch (e) {
    // localStorage unavailable — runtime can still use the returned value
  }
  window._comfyModalOutputOptions = merged;

  // Dispatch a custom event so both Settings surfaces can react
  try {
    window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: merged }));
  } catch (e) {
    // Event dispatch failure — non-critical
  }

  return merged;
}

/**
 * Fetch remote output config from /comfymodal/config and apply server
 * values to local cache.  The server is authoritative on initial sync:
 * server values always overwrite any stale local values.
 * Call once on app initialization (guarded externally to run only once).
 * On POST from either settings surface, only update local/window state
 * and notify AFTER a successful server response.
 */
export async function syncOutputConfigFromServer() {
  try {
    var resp = await fetch(MODAL_PREFIX + "/config");
    if (!resp.ok) return;
    var cfg = await resp.json();
    var updates = {};

    // Server is authoritative: apply all server values regardless of
    // whether localStorage already has a value.  This ensures initial
    // sync always reflects the backend, not stale local overrides.
    if (cfg.output_format !== undefined) {
      updates.output_format = cfg.output_format;
    }
    if (cfg.quality !== undefined) {
      updates.quality = cfg.quality;
    }
    if (cfg.webp_lossless_compression !== undefined) {
      updates.webp_lossless_compression = cfg.webp_lossless_compression;
    }
    if (cfg.auto_save_local !== undefined) {
      updates.auto_save_local = Boolean(cfg.auto_save_local);
    }
    if (cfg.save_folder) {
      updates.save_folder = normalizeOutputSaveFolder(cfg.save_folder);
    }
    if (cfg.save_metadata_sidecar !== undefined) {
      updates.save_metadata_sidecar = cfg.save_metadata_sidecar !== false;
    }

    if (Object.keys(updates).length > 0) {
      setOutputPreferences(updates, false);
    }
  } catch (e) {
    // Server unavailable — local state preserved
  }
}

/**
 * Notify Studio Settings and other surfaces that output preferences
 * changed without re-fetching from the server or creating new global
 * event listeners.  Used by both settings surfaces after a successful
 * POST to /comfymodal/config.
 * @param {object} prefs - The full merged preferences object.
 */
export function notifyOutputPreferencesChanged(prefs) {
  try {
    window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: prefs }));
  } catch (e) {
    // Event dispatch failure — non-critical
  }
}

// ── Concrete helpers ───────────────────────────────────────────────────────

/**
 * Check whether auto-save is enabled.
 * @returns {boolean}
 */
export function isAutoSaveEnabled() {
  return getOutputPreferences().auto_save_local;
}

/**
 * Toggle auto-save without downloading the current image.
 * Fires the comfymodal:output-preferences-changed event.
 * @param {boolean} enabled
 */
export function setAutoSaveEnabled(enabled) {
  return setOutputPreferences({ auto_save_local: !!enabled });
}

export function buildOutputModalOptions(prefs) {
  var source = prefs || getOutputPreferences();
  return {
    output_format: source.output_format,
    quality: source.quality,
    webp_lossless_compression: source.webp_lossless_compression,
    auto_save_local: !!source.auto_save_local,
    save_folder: source.save_folder,
    save_metadata_sidecar: source.save_metadata_sidecar !== false,
  };
}
