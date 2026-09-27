// ComfyUI Modal — Fake `app` stub for the Playwright harness.
//
// Stands in for ComfyUI's ../../scripts/app.js.  Within the Studio mount
// chain only web/studio-graph-binding.js imports it (`import { app } from
// "../../scripts/app.js"`) and it only touches the object inside guarded
// functions (getRawApp / isGraphAvailable / getComfyGraphContext).  This
// stub provides a safe minimal object so nothing crashes at import time or
// on incidental property access; it is intentionally NOT a LiteGraph
// implementation.  Do not over-engineer — the Studio UI renders from the
// fake REST backend, not from a live graph.

export const app = {
  graph: null,
  canvas: null,
  registerExtension: () => {},
  unregisterExtension: () => {},
  handlePrompt: () => {},
  ui: {
    settings: {
      get: () => undefined,
      set: () => {},
      addSetting: () => {},
    },
  },
  extensionManager: {
    registerExtension: () => {},
  },
};

// Some web modules read window.app as a fallback (see getRawApp in
// studio-graph-binding.js).
if (typeof window !== "undefined") {
  window.app = app;
  window.__comfymodal_comfy_app = app;
}
