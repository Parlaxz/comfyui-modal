// Modal Studio Vue substrate — one-way canvas compatibility projection.
//
// The Vue settings/server authority projects only values proven to have
// remaining non-Vue readers into the legacy canvas consumers. This is
// one-way after successful server bootstrap; the canvas never writes back
// into settingsStore. Phase-1 rules still preserved:
// - web/modal-node.js, its `/prompt` interception, canvas output settings,
//   and production/pass-through behavior are NOT migrated or broken.
// - Existing localStorage/global compatibility behavior is NOT deleted.
// - Existing localStorage/global compatibility behavior is not deleted.

/** Read-only view of canvas-relevant output preferences (Phase 2 fills this). */
export interface CanvasCompatibilitySnapshot {
  outputFormat: string;
  quality: number | null;
  autoSaveLocal: boolean;
}

const OUTPUT_KEYS = {
  outputFormat: "comfymodal_output_format",
  quality: "comfymodal_quality",
  autoSaveLocal: "comfymodal_auto_save_local",
  saveFolder: "comfymodal_save_folder",
  saveMetadataSidecar: "comfymodal_save_metadata_sidecar",
} as const;

export function projectCanvasCompatibility(settings: Record<string, unknown>): CanvasCompatibilitySnapshot {
  const snapshot: CanvasCompatibilitySnapshot = {
    outputFormat: String(settings.output_format ?? "original"),
    quality: typeof settings.quality === "number" ? settings.quality : null,
    autoSaveLocal: settings.auto_save_local === true,
  };
  if (typeof window === "undefined") return snapshot;
  const options = {
    output_format: snapshot.outputFormat,
    quality: snapshot.quality ?? 75,
    auto_save_local: snapshot.autoSaveLocal,
    save_folder: String(settings.save_folder ?? ""),
    save_metadata_sidecar: settings.save_metadata_sidecar !== false,
  };
  window._comfyModalOutputOptions = options;
  try {
    localStorage.setItem(OUTPUT_KEYS.outputFormat, options.output_format);
    localStorage.setItem(OUTPUT_KEYS.quality, String(options.quality));
    localStorage.setItem(OUTPUT_KEYS.autoSaveLocal, String(options.auto_save_local));
    localStorage.setItem(OUTPUT_KEYS.saveFolder, options.save_folder);
    localStorage.setItem(OUTPUT_KEYS.saveMetadataSidecar, String(options.save_metadata_sidecar));
  } catch {
    // Existing canvas consumers also tolerate unavailable storage.
  }
  window.dispatchEvent(new CustomEvent("comfymodal:output-preferences-changed", { detail: options }));
  return snapshot;
}

/**
 * Phase-2 owner: project the settings store into a CanvasCompatibilitySnapshot
 * and hand it to the modal-node `/prompt` interception path. The bridge is
 * ONE-WAY after successful server bootstrap (settings → legacy canvas
 * consumers); never a two-way sync system. Keep only values proven to have
 * remaining non-Vue readers (output options, canvas pass-through/enable
 * state, production-mode compatibility state if still consumed).
 *
 * Until then, canvas behavior is owned exclusively by web/modal-node.js and
 * the existing settings persistence — untouched by the Vue substrate.
 */
export type CanvasCompatibilityProjection = (
  settings: Record<string, unknown>,
) => CanvasCompatibilitySnapshot;
