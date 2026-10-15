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

import { publishStudioSync } from "./studio-sync.js";

const MODAL_PREFIX = "/comfymodal";

export const STORAGE_KEYS = {
  OUTPUT_FORMAT: "comfymodal_output_format",
  QUALITY: "comfymodal_quality",
  WEBP_LC: "comfymodal_webp_lossless_compression",
  AUTOSAVE: "comfymodal_auto_save_local",
  SAVEFOLDER: "comfymodal_save_folder",
  SIDECAR: "comfymodal_save_metadata_sidecar",
  PREVIEW_DEFAULT: "comfymodal_preview_default",
  PREVIEW_CODEC: "comfymodal_preview_codec",
  PREVIEW_QUALITY: "comfymodal_preview_quality",
  DATA_SAVER_DEFAULT: "comfymodal_data_saver_default",
  DATA_SAVER_CODEC: "comfymodal_data_saver_codec",
  DATA_SAVER_QUALITY: "comfymodal_data_saver_quality",
};

export const DEFAULT_OUTPUT_SAVEFOLDER = "output/modal";

export const PREVIEW_DEFAULTS = Object.freeze({
  preview_default: "off",
  preview_codec: "webp",
  preview_quality: 70,
});

function _previewQuality(value) {
  var quality = typeof value === "number" ? value : parseInt(value, 10);
  return Number.isInteger(quality) && quality >= 1 && quality <= 100
    ? quality
    : PREVIEW_DEFAULTS.preview_quality;
}

function _readPreviewPreferences() {
  // Data Saver is canonical; preview_* keys are legacy aliases.
  var saverDefault = localStorage.getItem(STORAGE_KEYS.DATA_SAVER_DEFAULT);
  if (saverDefault === null) saverDefault = localStorage.getItem(STORAGE_KEYS.PREVIEW_DEFAULT);
  var saverCodec = localStorage.getItem(STORAGE_KEYS.DATA_SAVER_CODEC);
  if (saverCodec === null) saverCodec = localStorage.getItem(STORAGE_KEYS.PREVIEW_CODEC);
  var saverQualityRaw = localStorage.getItem(STORAGE_KEYS.DATA_SAVER_QUALITY);
  if (saverQualityRaw === null) saverQualityRaw = localStorage.getItem(STORAGE_KEYS.PREVIEW_QUALITY);
  var resolved = {
    preview_default: saverDefault === "on" ? "on" : PREVIEW_DEFAULTS.preview_default,
    preview_codec: saverCodec === "webp" ? saverCodec : PREVIEW_DEFAULTS.preview_codec,
    preview_quality: _previewQuality(saverQualityRaw),
  };
  resolved.data_saver_default = resolved.preview_default;
  resolved.data_saver_codec = resolved.preview_codec;
  resolved.data_saver_quality = resolved.preview_quality;
  return resolved;
}

export function normalizePreviewPreferences(prefs) {
  var source = prefs || {};
  var normalized = {};
  if (source.preview_default !== undefined) {
    if (source.preview_default !== "off" && source.preview_default !== "on") {
      throw new Error("Invalid preview_default");
    }
    normalized.preview_default = source.preview_default;
  }
  if (source.preview_codec !== undefined) {
    if (source.preview_codec !== "webp") throw new Error("Invalid preview_codec");
    normalized.preview_codec = source.preview_codec;
  }
  if (source.preview_quality !== undefined) {
    var quality = source.preview_quality;
    if (typeof quality !== "number" || !Number.isInteger(quality) || quality < 1 || quality > 100) {
      throw new Error("Invalid preview_quality");
    }
    normalized.preview_quality = quality;
  }
  return normalized;
}

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
  var preview = _readPreviewPreferences();
  var prefs = {
    output_format: localStorage.getItem(STORAGE_KEYS.OUTPUT_FORMAT) || "original",
    quality: parseInt(localStorage.getItem(STORAGE_KEYS.QUALITY), 10) || 75,
    webp_lossless_compression: localStorage.getItem(STORAGE_KEYS.WEBP_LC) || "balanced",
    auto_save_local: localStorage.getItem(STORAGE_KEYS.AUTOSAVE) === "true",
    save_folder: normalizeOutputSaveFolder(localStorage.getItem(STORAGE_KEYS.SAVEFOLDER)),
    save_metadata_sidecar: localStorage.getItem(STORAGE_KEYS.SIDECAR) !== "false",
    preview_default: preview.preview_default,
    preview_codec: preview.preview_codec,
    preview_quality: preview.preview_quality,
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
  var normalizedPreview = normalizePreviewPreferences(merged);
  merged.preview_default = normalizedPreview.preview_default;
  merged.preview_codec = normalizedPreview.preview_codec;
  merged.preview_quality = normalizedPreview.preview_quality;
  merged.data_saver_default = merged.preview_default;
  merged.data_saver_codec = merged.preview_codec;
  merged.data_saver_quality = merged.preview_quality;

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
          preview_default: merged.preview_default,
          preview_codec: merged.preview_codec,
          preview_quality: merged.preview_quality,
          data_saver_default: merged.data_saver_default,
          data_saver_codec: merged.data_saver_codec,
          data_saver_quality: merged.data_saver_quality,
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
    localStorage.setItem(STORAGE_KEYS.PREVIEW_DEFAULT, merged.preview_default);
    localStorage.setItem(STORAGE_KEYS.PREVIEW_CODEC, merged.preview_codec);
    localStorage.setItem(STORAGE_KEYS.PREVIEW_QUALITY, String(merged.preview_quality));
    localStorage.setItem(STORAGE_KEYS.DATA_SAVER_DEFAULT, merged.data_saver_default);
    localStorage.setItem(STORAGE_KEYS.DATA_SAVER_CODEC, merged.data_saver_codec);
    localStorage.setItem(STORAGE_KEYS.DATA_SAVER_QUALITY, String(merged.data_saver_quality));
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

  if (syncToServer) publishStudioSync("settings");

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
    if (cfg.data_saver_default !== undefined) {
      updates.preview_default = cfg.data_saver_default;
      updates.data_saver_default = cfg.data_saver_default;
    } else if (cfg.preview_default !== undefined) {
      updates.preview_default = cfg.preview_default;
      updates.data_saver_default = cfg.preview_default;
    }
    if (cfg.data_saver_codec !== undefined) {
      updates.preview_codec = cfg.data_saver_codec;
      updates.data_saver_codec = cfg.data_saver_codec;
    } else if (cfg.preview_codec !== undefined) {
      updates.preview_codec = cfg.preview_codec;
      updates.data_saver_codec = cfg.preview_codec;
    }
    if (cfg.data_saver_quality !== undefined) {
      updates.preview_quality = cfg.data_saver_quality;
      updates.data_saver_quality = cfg.data_saver_quality;
    } else if (cfg.preview_quality !== undefined) {
      updates.preview_quality = cfg.preview_quality;
      updates.data_saver_quality = cfg.preview_quality;
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

export function buildPreviewModalOptions(prefs) {
  var source = prefs || getOutputPreferences();
  var preview = normalizePreviewPreferences({
    preview_default: source.preview_default || PREVIEW_DEFAULTS.preview_default,
    preview_codec: source.preview_codec || PREVIEW_DEFAULTS.preview_codec,
    preview_quality: source.preview_quality != null ? source.preview_quality : PREVIEW_DEFAULTS.preview_quality,
  });
  return {
    preview_default: preview.preview_default,
    preview_enabled: preview.preview_default === "on",
    preview_codec: preview.preview_codec,
    preview_quality: preview.preview_quality,
  };
}

export function buildModalOptions(prefs) {
  var source = prefs || getOutputPreferences();
  return Object.assign({}, buildOutputModalOptions(source), buildPreviewModalOptions(source));
}

export async function loadModalOptions(apiBase) {
  var base = apiBase || MODAL_PREFIX;
  var config = {};
  try {
    var response = await fetch(base + "/config");
    if (response.ok) {
      var remote = await response.json();
      if (remote && typeof remote === "object") config = remote;
    }
  } catch (e) {
    // Local cache remains the request-time fallback when config is unavailable.
  }
  var source = Object.assign({}, getOutputPreferences(), config);
  var mode = source.execution_mode;
  if (!mode && typeof window !== "undefined") {
    mode = window._comfyModalExecutionMode;
  }
  return Object.assign(
    {
      execution_mode: mode || "v2",
      golden_profile: typeof (config.golden_profile || config.profile_name || config.profile) === "string"
        ? (config.golden_profile || config.profile_name || config.profile) : null,
    },
    buildModalOptions(source),
  );
}

// ── Studio V3 preset hooks (Phase 12, frontend lane) ─────────────────────
// Narrow snapshot/override only. Preset output settings are a Playground-
// scoped override: they NEVER POST global settings and never write
// localStorage. The override rides the single run payload via
// resolveEffectiveOutputOptions (web/studio-workflow-run.js).

var PRESET_OUTPUT_FORMATS = ["original", "png", "jpeg", "webp"];

function _presetOutputUnsafe(value) {
  return /^(data:|blob:|https?:|wss?:)/i.test(String(value).trim());
}

function _presetOutputStr(value, max) {
  if (value == null) return "";
  var s = String(value);
  if (_presetOutputUnsafe(s)) return "";
  return s.slice(0, max);
}

/**
 * Owner-native output snapshot for preset capture (format/quality/save +
 * preview options only). Reads the existing getOutputPreferences lane.
 */
export function snapshotOutputForPreset() {
  var prefs = null;
  try {
    prefs = getOutputPreferences();
  } catch (_e) {
    return null;
  }
  if (!prefs || typeof prefs !== "object") return null;
  return {
    format: prefs.output_format,
    quality: prefs.quality,
    auto_save_local: !!prefs.auto_save_local,
    save_folder: prefs.save_folder,
    save_metadata_sidecar: prefs.save_metadata_sidecar !== false,
    preview_default: prefs.preview_default,
    preview_quality: prefs.preview_quality,
  };
}

/**
 * Build the Playground-scoped output override from a preset output section.
 * Flat contract shape (mirrors the backend output section): output_format,
 * quality, auto_save_local, save_folder, save_metadata_sidecar, preview_*
 * scalars. webp_lossless_compression is backend-bool while the lane stores a
 * name, so it is never carried. Pure: no persistence, no network. Returns
 * null when the section is absent (no override; global options apply).
 */
export function buildPresetOutputOverride(section) {
  var s = section && typeof section === "object" ? section : null;
  if (!s) return null;
  var override = {};
  if (typeof s.output_format === "string" && s.output_format
    && PRESET_OUTPUT_FORMATS.indexOf(s.output_format) !== -1) {
    override.output_format = s.output_format;
  }
  if (typeof s.quality === "number" && isFinite(s.quality)) {
    override.quality = Math.max(1, Math.min(100, Math.floor(s.quality)));
  }
  if (typeof s.auto_save_local === "boolean") override.auto_save_local = s.auto_save_local;
  var folder = _presetOutputStr(s.save_folder, 500);
  if (folder) override.save_folder = folder;
  if (typeof s.save_metadata_sidecar === "boolean") {
    override.save_metadata_sidecar = s.save_metadata_sidecar;
  }
  ["preview_default", "preview_codec", "preview_quality"].forEach(function (key) {
    var value = s[key];
    if (typeof value === "string" && value && !_presetOutputUnsafe(value)) {
      override[key] = value.slice(0, 40);
    } else if (typeof value === "number" && isFinite(value)) {
      override[key] = value;
    } else if (typeof value === "boolean") {
      override[key] = value;
    }
  });
  return Object.keys(override).length ? override : null;
}
