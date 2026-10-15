// Modal Studio Vue substrate — canvas compatibility seam (Phase 1: contract only).
//
// What this seam is for: the real settings-to-canvas compatibility
// projection (output settings → web/modal-node.js `/prompt` interception
// and canvas output preferences) is exercised in Phase 2, not here.
//
// Phase-1 rules, preserved from the old Studio:
// - web/modal-node.js, its `/prompt` interception, canvas output settings,
//   and production/pass-through behavior are NOT migrated or broken.
// - Existing localStorage/global compatibility behavior is NOT deleted.
// - This module performs NO reads and NO writes in Phase 1; it only
//   declares the shape the Phase-2 projection will fill, so the later
//   port has one obvious place to implement it.

/** Read-only view of canvas-relevant output preferences (Phase 2 fills this). */
export interface CanvasCompatibilitySnapshot {
  outputFormat: string;
  quality: number | null;
  autoSaveLocal: boolean;
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
