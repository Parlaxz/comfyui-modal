// Studio Sketch shell/handoff adapter (Phase 6).
//
// Thin adapter between the Generate/Edit Sketch shell subtools and the
// existing Sketch save contract. It owns NO canvas, NO workflow selection,
// and NO execution path — it only sequences the handoff:
//
//   engine.flattenToBlob()
//     -> uploadImageBlob() (from ./studio-field-blocks.js, dynamic import)
//     -> opts.onCommitted(filename)
//
// The LEAD wires the returned filename into the normal shelf path:
// commitShelfValue(..., "source_image", filename), which ordinary I2I then
// consumes via run-context/Wizard mapping (buildRunPayload,
// studio_workflow_run.py merge/apply). There is NO special Sketch workflow
// for the normal path; the legacy sketch workflow stays compatibility-only.
//
// Persistence / reset contract (documented, enforced by session below):
// - Tool settings persist per session (session.settings; setToolSettings
//   merges, getToolSettings returns a copy). Mode switches and base changes
//   NEVER clear them.
// - Overlay layers reset on mode switch and on source/base change
//   (session.reset() / session.setBaseImage()), preserving tool settings.
// - Generate starts blank: an intentional base canvas with dims defaulting
//   to 1024x1024, or matching the selected workflow dims when the caller
//   passes width/height.
// - Edit uses the current image as the locked base (baseImageUrl required;
//   session.baseLocked === true). Base replacement still resets overlays.
// - Flatten output is named via uniqueImageName("studio-sketch"), i.e.
//   studio-sketch-*.png.
//
// Deliberately NOT here: execution-method selection, new workflow families,
// provenance keys. The normal studio_controls.source_image covers it.

export const SKETCH_DEFAULT_SIZE = 1024;

/**
 * @typedef {object} SketchEngine
 * @property {() => Promise<Blob>} flattenToBlob composite base+overlay PNG
 */

/**
 * @typedef {object} SketchLayerStore
 * Duck-typed overlay layer handle. Any of clearLayers/clear/reset is tried
 * in that order; a missing handle is a no-op (tool settings still persist).
 */

/**
 * Open a Sketch session.
 * @param {object} opts
 * @param {"generate"|"edit"} [opts.mode] shell mode ("generate" default)
 * @param {string|null} [opts.baseImageUrl] locked base for edit; null for blank generate
 * @param {SketchEngine|null} [opts.engine] flatten source (settable later via setEngine)
 * @param {SketchLayerStore|null} [opts.layerStore] overlay layers (reset on mode/base change)
 * @param {number} [opts.width] generate canvas width (default 1024)
 * @param {number} [opts.height] generate canvas height (default 1024)
 * @param {(filename: string) => void} [opts.onCommitted] lead playground wiring hook
 * @returns {{ mode: string, commit: () => Promise<{filename: string, blob: Blob}>, reset: () => void, destroy: () => void, setBaseImage: (url: string|null) => void, setEngine: (engine: SketchEngine|null) => void, setMode: (mode: string) => void, setToolSettings: (patch: object) => object, getToolSettings: () => object, baseLocked: boolean, width: number, height: number }}
 */
export function openSketch(opts) {
  const o = opts && typeof opts === "object" ? opts : {};
  let mode = o.mode === "edit" ? "edit" : "generate";
  let baseImageUrl = typeof o.baseImageUrl === "string" && o.baseImageUrl ? o.baseImageUrl : null;
  let engine = o.engine || null;
  let layerStore = o.layerStore || null;
  const onCommitted = typeof o.onCommitted === "function" ? o.onCommitted : null;
  let settings = {};
  let destroyed = false;

  // Generate canvas dims: intentional default 1024x1024, or the selected
  // workflow dims when the caller provides them.
  const dims = _coerceDims(o.width, o.height);

  function _assertLive() {
    if (destroyed) throw new Error("Sketch session destroyed");
  }

  function _clearLayers() {
    if (!layerStore) return;
    try {
      if (typeof layerStore.clearLayers === "function") { layerStore.clearLayers(); return; }
      if (typeof layerStore.clear === "function") { layerStore.clear(); return; }
      if (typeof layerStore.reset === "function") { layerStore.reset(); return; }
    } catch (_e) {
      // Overlay reset must never break tool settings or the handoff.
    }
  }

  const session = {
    get mode() { return mode; },
    // Edit sessions lock the base image supplied at open; Generate has none.
    get baseLocked() { return mode === "edit"; },
    get width() { return dims.width; },
    get height() { return dims.height; },

    setEngine(next) {
      _assertLive();
      engine = next || null;
    },

    setMode(next) {
      _assertLive();
      const m = next === "edit" ? "edit" : "generate";
      if (m === mode) return;
      mode = m;
      // Mode switch resets overlay layers but preserves tool settings.
      _clearLayers();
    },

    setBaseImage(url) {
      _assertLive();
      baseImageUrl = typeof url === "string" && url ? url : null;
      // Source/base change resets overlay layers but preserves tool settings.
      _clearLayers();
    },

    setToolSettings(patch) {
      _assertLive();
      if (patch && typeof patch === "object") {
        settings = Object.assign({}, settings, patch);
      }
      return Object.assign({}, settings);
    },

    getToolSettings() {
      return Object.assign({}, settings);
    },

    reset() {
      _assertLive();
      // Layers reset; tool settings persist; base image is kept.
      _clearLayers();
    },

    async commit() {
      _assertLive();
      if (!engine || typeof engine.flattenToBlob !== "function") {
        throw new Error("Sketch commit needs an engine with flattenToBlob()");
      }
      const blob = await engine.flattenToBlob();
      if (!blob) throw new Error("Sketch flatten produced no image");
      // Dynamic import: no edit to studio-field-blocks.js, no static cycle
      // with the playground bundle.
      const mod = await import("./studio-field-blocks.js");
      const filename = await mod.uploadImageBlob(blob, mod.uniqueImageName("studio-sketch"));
      if (onCommitted) onCommitted(filename);
      return { filename, blob };
    },

    destroy() {
      destroyed = true;
      engine = null;
      layerStore = null;
      settings = {};
    },
  };

  return session;
}

function _coerceDims(width, height) {
  const w = Math.floor(Number(width));
  const h = Math.floor(Number(height));
  return {
    width: Number.isFinite(w) && w > 0 ? w : SKETCH_DEFAULT_SIZE,
    height: Number.isFinite(h) && h > 0 ? h : SKETCH_DEFAULT_SIZE,
  };
}
