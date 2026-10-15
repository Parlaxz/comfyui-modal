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
 * Duck-typed overlay layer handle. Overlay reset prefers the store's own
 * delete() path (keeps store + engine in sync); engine.clearOverlays() is
 * the fallback when no store is attached.
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
  const onSettingsChange = typeof o.onSettingsChange === "function" ? o.onSettingsChange : null;
  let settings = {};
  let destroyed = false;

  // Generate canvas dims: intentional default 1024x1024, or the selected
  // workflow dims when the caller provides them.
  const dims = _coerceDims(o.width, o.height);

  function _assertLive() {
    if (destroyed) throw new Error("Sketch session destroyed");
  }

  function _isBaseLayer(l) {
    return !!l && (l.id === "base" || l.locked === true);
  }

  // Real overlay reset: drop every non-base layer through the store so the
  // store list and the engine canvases stay reconciled, then snapshot
  // engine history so Clear/Undo observe the cleared state. Base pixels
  // are kept; tool settings are untouched.
  function _clearOverlaysReal() {
    let storeCleared = false;
    try {
      if (layerStore && Array.isArray(layerStore.layers)
        && typeof layerStore.delete === "function") {
        const ids = layerStore.layers
          .filter((l) => !_isBaseLayer(l))
          .map((l) => l && l.id)
          .filter(Boolean);
        ids.forEach((id) => {
          try { layerStore.delete(id); } catch (_e) { /* per-layer best-effort */ }
        });
        storeCleared = true;
      }
    } catch (_e) {
      // Fall through to the engine fallback below.
    }
    // The store commit path does not reach engine.saveToHistory (it probes
    // snapshot/pushHistory/saveSnapshot/historyPush/commitHistory), so
    // snapshot explicitly — Clear must be undoable and visible to panels.
    try {
      if (engine && typeof engine.saveToHistory === "function") engine.saveToHistory();
    } catch (_e) { /* history is best-effort */ }
    if (!storeCleared) {
      try {
        if (engine && typeof engine.clearOverlays === "function") engine.clearOverlays();
      } catch (_e) { /* overlay reset must never break the handoff */ }
    }
  }

  function _clearLayers() {
    _clearOverlaysReal();
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

    async setBaseImage(url) {
      _assertLive();
      baseImageUrl = typeof url === "string" && url ? url : null;
      // Passthrough to the engine: the new source becomes the locked base
      // bitmap (blank canvas when null). Overlays are then reset so stale
      // strokes from the previous source can never survive the change;
      // tool settings persist.
      try {
        if (engine && typeof engine.setBaseImage === "function") {
          await engine.setBaseImage(baseImageUrl || "blank");
        }
      } catch (_e) {
        // A failed base load still clears stale overlays below.
      }
      _clearLayers();
    },

    setToolSettings(patch) {
      _assertLive();
      if (patch && typeof patch === "object") {
        settings = Object.assign({}, settings, patch);
      }
      // Phase 12: notify the Studio shell that tool config changed (the shell
      // marks its active preset dirty; this module never touches presets).
      try {
        if (typeof onSettingsChange === "function") onSettingsChange(Object.assign({}, settings));
      } catch (_e) { /* edit notification is best-effort */ }
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

// ── Studio V3 preset hooks (Phase 12, frontend lane) ─────────────────────
// Narrow snapshot/apply/reset only, over tool settings (session.
// getToolSettings/setToolSettings). Strokes/overlays are pixels and are never
// snapshotted; the base image URL is never read. Apply reuses the existing
// setToolSettings + reset (overlay clear); base-image clearing stays with
// the playground image-clear step via clearSketchBaseForPreset.

const _SKETCH_PRESET_TOOLS = ["brush", "pencil", "eraser", "line", "rectangle", "circle", "fill", "eyedropper"];

function _presetNum(value, fallback, min, max) {
  const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (typeof n !== "number" || !Number.isFinite(n)) return fallback;
  return Math.max(min, Math.min(max, n));
}

function _presetStr(value, max) {
  if (value == null) return "";
  return String(value).slice(0, max);
}

/**
 * Owner-native sketch snapshot for preset capture: tool settings + canvas
 * dims only. Never pixels, never the base image.
 *
 * The tool panels drive the ENGINE directly (setTool/setSize/setColor/...)
 * and the session only learns settings through setToolSettings, so the live
 * engine state (engine.getState(), when the caller has it) is the true source
 * and wins over stale session settings for the tool keys it carries. Dims
 * still come from the session (the engine mirrors them; the session owns the
 * generate-size contract).
 */
export function snapshotSketchSettingsForPreset(session, engineState) {
  let settings = {};
  try {
    if (session && typeof session.getToolSettings === "function") {
      settings = session.getToolSettings() || {};
    }
  } catch (_e) {
    settings = {};
  }
  try {
    const live = engineState && typeof engineState === "object" ? engineState : null;
    if (live) {
      for (const key of ["tool", "brushSize", "opacity", "hardness", "color", "bgColor"]) {
        if (live[key] !== undefined && live[key] !== null) settings[key] = live[key];
      }
    }
  } catch (_eLive) { /* session settings stand alone */ }
  let width = SKETCH_DEFAULT_SIZE;
  let height = SKETCH_DEFAULT_SIZE;
  try {
    if (session) {
      if (Number.isFinite(Number(session.width))) width = Number(session.width);
      if (Number.isFinite(Number(session.height))) height = Number(session.height);
    }
  } catch (_e2) { /* dims fall back to defaults */ }
  return {
    tool: settings.tool,
    brushSize: settings.brushSize,
    opacity: settings.opacity,
    hardness: settings.hardness,
    color: settings.color,
    bgColor: settings.bgColor,
    width,
    height,
  };
}

/**
 * Apply a preset sketch section via the existing setToolSettings, then reset
 * overlay layers (strokes must never survive a preset load). Returns false
 * when there is no live session (caller falls back to pending defaults).
 */
export function applySketchSettingsFromPreset(session, section) {
  if (!session || typeof session.setToolSettings !== "function") return false;
  const s = section && typeof section === "object" ? section : null;
  const tool = s && _SKETCH_PRESET_TOOLS.indexOf(s.tool) !== -1 ? s.tool : "brush";
  try {
    session.setToolSettings({
      tool,
      brushSize: _presetNum(s && s.brushSize, 8, 0.5, 512),
      opacity: _presetNum(s && s.opacity, 1, 0, 1),
      hardness: _presetNum(s && s.hardness, 0.8, 0, 1),
      color: _presetStr(s && s.color, 32),
      bgColor: _presetStr(s && s.bgColor, 32),
    });
  } catch (_e) {
    return false;
  }
  try {
    if (typeof session.reset === "function") session.reset();
  } catch (_e2) { /* overlay clear is best-effort */ }
  return true;
}

/** Reset sketch tool settings to neutral + clear overlays. */
export function resetSketchForPreset(session) {
  return applySketchSettingsFromPreset(session, null);
}

/**
 * Playground image-clear step: drop the locked base image (edit sessions)
 * so no pixels survive a preset load. Best-effort; never throws.
 */
export function clearSketchBaseForPreset(session) {
  if (!session || typeof session.setBaseImage !== "function") return;
  try {
    const p = session.setBaseImage(null);
    if (p && typeof p.catch === "function") p.catch(function () {});
  } catch (_e) { /* base clear is best-effort */ }
}
