// Modal Studio — Graph Binding Capture Helpers
//
// Safe ComfyUI graph context access and node-binding capture logic.
// Never accesses graph before init.  Exports:
//   getComfyGraphContext()
//   beginGraphBindingCapture(options)
//   cancelGraphBinding()
//   extractNodeCandidates(node)
//   isGraphAvailable()

import { app as comfyApp } from "../../scripts/app.js";

const _captureState = { active: false, resolve: null, cleanup: null };

// ── Graph context access ────────────────────────────────────────────────

export function isGraphAvailable() {
  try {
    const app = getRawApp();
    return !!(app && app.graph && typeof app.graph.serialize === "function");
  } catch {
    return false;
  }
}

function getRawApp() {
  if (comfyApp) return comfyApp;
  if (window.__comfymodal_comfy_app) return window.__comfymodal_comfy_app;
  if (window.app) return window.app;
  return null;
}

export function getComfyGraphContext() {
  const app = getRawApp();
  if (!app) return { ok: false, available: false, reason: "ComfyUI app not found. Open or initialize a graph first." };
  if (!app.graph || typeof app.graph.serialize !== "function") {
    return { ok: false, available: false, reason: "ComfyUI graph is not ready. Open or initialize a graph first." };
  }
  return {
    ok: true,
    available: true,
    app,
    graph: app.graph,
    canvas: app.canvas || null,
  };
}

// ── Capture: begin / cancel ─────────────────────────────────────────────

// Create a CSS class that highlights nodes during capture
const _BINDING_HIGHLIGHT_CLASS = "comfymodal-binding-highlight";

function _injectCaptureStyles() {
  if (document.getElementById("comfymodal-binding-capture-styles")) return;
  const style = document.createElement("style");
  style.id = "comfymodal-binding-capture-styles";
  style.textContent = `
    .comfymodal-binding-highlight {
      outline: 2px solid #dc2626 !important;
      outline-offset: 2px !important;
      cursor: crosshair !important;
    }
    .comfymodal-binding-capture-active .comfy-node {
      cursor: crosshair !important;
    }
    .comfymodal-binding-capture-hint {
      position: fixed;
      bottom: 16px;
      left: 50%;
      transform: translateX(-50%);
      background: #1a1a1a;
      border: 1px solid #dc2626;
      color: #d0d0d0;
      padding: 8px 16px;
      border-radius: 4px;
      font-size: 12px;
      z-index: 9999;
      pointer-events: none;
      white-space: nowrap;
    }
  `;
  document.head.appendChild(style);
}

function _removeCaptureHints() {
  const hints = document.querySelectorAll(".comfymodal-binding-capture-hint");
  hints.forEach((h) => { if (h.parentNode) h.parentNode.removeChild(h); });
}

export function beginGraphBindingCapture({ bindingKey, label, onCapture, onCancel }) {
  // Guard: if already active, cancel cleanly first
  if (_captureState.active) {
    _captureState.active = false;
    if (_captureState.cleanup) {
      _captureState.cleanup();
      _captureState.cleanup = null;
    }
    _removeCaptureHints();
  }

  const ctx = getComfyGraphContext();
  if (!ctx.ok) {
    if (onCancel) onCancel(ctx.reason || "Graph not available");
    return;
  }

  _injectCaptureStyles();

  const hintEl = document.createElement("div");
  hintEl.className = "comfymodal-binding-capture-hint";
  hintEl.textContent = `Waiting for graph click. Click the node used for ${label}. Esc to cancel.`;
  document.body.appendChild(hintEl);

  // Add capture-active class to document for cursor styles
  document.body.classList.add("comfymodal-binding-capture-active");

  _captureState.active = true;

  let _cleanupCalled = false;

  // Temporary click listener on the LiteGraph canvas
  function handleClick(e) {
    // Try to find the clicked node via ComfyUI/LiteGraph
    const targetNode = findClickedNode(e, ctx);
    if (!targetNode) return; // Click was not on a node

    e.preventDefault();
    e.stopPropagation();

    const candidates = extractNodeCandidates(targetNode);
    const result = {
      bindingKey,
      nodeId: String(targetNode.id),
      nodeType: targetNode.type || "",
      nodeTitle: targetNode.title || targetNode.type || `Node ${targetNode.id}`,
      candidates,
      // If there's exactly one widget/output/input and it's unambiguous, set it directly
      widgetName: null,
      inputName: null,
      outputIndex: null,
    };

    // Auto-select if exactly one candidate of a kind exists
    if (candidates.length === 1) {
      const c = candidates[0];
      if (c.kind === "widget") result.widgetName = c.name;
      else if (c.kind === "input") result.inputName = c.name;
      else if (c.kind === "output") result.outputIndex = c.index;
    }

    cleanup();
    _captureState.active = false;
    if (onCapture) onCapture(result);
  }

  // Keyboard handler for Esc to cancel
  function handleKeydown(e) {
    if (e.key === "Escape") {
      cleanup();
      _captureState.active = false;
      if (onCancel) onCancel("Cancelled by user");
    }
  }

  function cleanup() {
    if (_cleanupCalled) return;
    _cleanupCalled = true;
    document.removeEventListener("click", handleClick, true);
    document.removeEventListener("keydown", handleKeydown);
    document.body.classList.remove("comfymodal-binding-capture-active");
    _removeCaptureHints();
    _captureState.cleanup = null;
    _captureState.resolve = null;
  }

  _captureState.cleanup = cleanup;

  // Register listeners (capture phase to intercept before ComfyUI handlers)
  document.addEventListener("click", handleClick, true);
  document.addEventListener("keydown", handleKeydown);

  // Return a cancel function
  return () => {
    if (_captureState.active) {
      cleanup();
      _captureState.active = false;
      if (onCancel) onCancel("Cancelled");
    }
  };
}

export function cancelGraphBinding() {
  if (_captureState.active && _captureState.cleanup) {
    _captureState.active = false;
    _captureState.cleanup();
    _captureState.cleanup = null;
    _captureState.resolve = null;
  }
  _removeCaptureHints();
}

export function getSelectedGraphNodeTarget() {
  const ctx = getComfyGraphContext();
  if (!ctx.ok) return null;

  const selected = ctx.canvas && ctx.canvas.selected_nodes;
  if (!selected) return null;

  const nodes = Array.isArray(selected)
    ? selected
    : Object.values(selected).filter(Boolean);
  const node = nodes[0] || null;
  if (!node) return null;

  return {
    nodeId: String(node.id),
    nodeType: node.type || "",
    nodeTitle: node.title || node.type || `Node ${node.id}`,
    candidates: extractNodeCandidates(node),
    widgetName: null,
    inputName: null,
    outputIndex: null,
  };
}

// ── View a node: center on canvas + magenta highlight ───────────────────
//
// QoL validation aid shared by the wizard's binding rows and suggestion
// proposals.  Centers the node through the LiteGraph canvas (centerOnNode,
// falling back to the DragAndScale scale/offset) and draws a transient DOM
// overlay border for 3s.  Fully null-safe: with no graph/canvas/node the
// helper reports ok:false and callers hide/disable their View control.

const _VIEW_HIGHLIGHT_ID = "comfymodal-node-view-highlight";
const _VIEW_HIGHLIGHT_MS = 3000;
let _viewHighlightTimer = null;

function _injectViewStyles() {
  if (document.getElementById("comfymodal-node-view-styles")) return;
  const style = document.createElement("style");
  style.id = "comfymodal-node-view-styles";
  style.textContent = `
    .comfymodal-node-view-highlight {
      position: fixed;
      pointer-events: none;
      z-index: 10050;
      border: 2px solid #ff00ff !important;
      border-radius: 4px;
      box-shadow: 0 0 0 2px rgba(255, 0, 255, 0.45), 0 0 12px 2px rgba(255, 0, 255, 0.55);
      transition: opacity 0.25s ease;
    }
  `;
  document.head.appendChild(style);
}

function _findGraphNodeById(graph, nodeId) {
  if (!graph || nodeId == null) return null;
  try {
    if (typeof graph.getNodeById === "function") {
      const node = graph.getNodeById(nodeId);
      if (node) return node;
    }
  } catch (e) { /* fall through to list scan */ }
  const byId = graph._nodes_by_id;
  if (byId && byId[nodeId]) return byId[nodeId];
  const nodes = graph.nodes || graph._nodes || [];
  const sid = String(nodeId);
  return nodes.find((n) => n && String(n.id) === sid) || null;
}

/** True when a live graph exists and contains *nodeId*. */
export function isGraphNodeAvailable(nodeId) {
  const ctx = getComfyGraphContext();
  if (!ctx.ok) return false;
  return !!_findGraphNodeById(ctx.graph, nodeId);
}

function _canvasCssSize(canvas) {
  try {
    const el = canvas && (canvas.canvas || canvas);
    if (el && typeof el.getBoundingClientRect === "function") {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return { width: r.width, height: r.height };
    }
    if (el && typeof el.clientWidth === "number" && el.clientWidth > 0) {
      return { width: el.clientWidth, height: el.clientHeight || 0 };
    }
  } catch (e) { /* fall through */ }
  return null;
}

function _asNumPair(value, fallback) {
  // Node geometry across ComfyUI generations: plain arrays, typed arrays /
  // array-likes (0.34 ComfyNode pos/size), or {x,y} / {width,height} shapes.
  try {
    if (Array.isArray(value) && value.length >= 2
      && typeof value[0] === "number" && typeof value[1] === "number") {
      return [value[0], value[1]];
    }
    if (value && typeof value.length === "number" && value.length >= 2
      && typeof value[0] === "number" && typeof value[1] === "number") {
      return [value[0], value[1]];
    }
    if (value && typeof value.x === "number" && typeof value.y === "number") {
      return [value.x, value.y];
    }
    if (value && typeof value.width === "number" && typeof value.height === "number") {
      return [value.width, value.height];
    }
  } catch (e) { /* fall through */ }
  return fallback;
}

function _snapCanvasToNode(canvas, node) {
  // CSS-pixel ds math matching _nodeScreenRect: centers the node in the
  // visible element. Uses client metrics (never the device-pixel backing
  // store) so HiDPI canvases land correctly.
  try {
    const ds = canvas && canvas.ds;
    const size = _canvasCssSize(canvas);
    if (!ds || !size || typeof ds.scale !== "number" || ds.scale <= 0) return false;
    const pos = _asNumPair(node && node.pos, null);
    const off = _asNumPair(ds.offset, null);
    if (!pos || !off) return false;
    const nsize = _asNumPair(node && node.size, [140, 80]);
    const cx = pos[0] + nsize[0] / 2;
    const cy = pos[1] + nsize[1] / 2;
    try {
      ds.offset[0] = size.width / ds.scale / 2 - cx;
      ds.offset[1] = size.height / ds.scale / 2 - cy;
    } catch (e) { return false; }
    if (typeof canvas.setDirty === "function") canvas.setDirty(true);
    if (typeof canvas.draw === "function") canvas.draw(true);
    return true;
  } catch (e) { return false; }
}

function _centerCanvasOnNode(canvas, node) {
  if (!canvas || !node) return false;
  let centered = false;
  try {
    if (typeof canvas.centerOnNode === "function") {
      canvas.centerOnNode(node);
      centered = true;
    }
  } catch (e) { centered = false; }
  // Snap afterwards: idempotent when centerOnNode already centered, and
  // repairs the offset when it is missing, a no-op, or unit-mismatched.
  return _snapCanvasToNode(canvas, node) || centered;
}

function _nodeScreenRect(ctx, node) {
  const canvas = ctx.canvas;
  const el = canvas && (canvas.canvas || canvas);
  let base = { left: 0, top: 0, width: (window && window.innerWidth) || 0, height: (window && window.innerHeight) || 0 };
  try {
    if (el && typeof el.getBoundingClientRect === "function") {
      const r = el.getBoundingClientRect();
      base = { left: r.left, top: r.top, width: r.width, height: r.height };
    }
  } catch (e) { /* keep default */ }
  const ds = (canvas && canvas.ds) || {};
  const scale = typeof ds.scale === "number" && ds.scale > 0 ? ds.scale : 1;
  const offset = _asNumPair(ds.offset, [0, 0]);
  const pos = _asNumPair(node.pos, [0, 0]);
  const size = _asNumPair(node.size, [140, 80]);
  return {
    left: base.left + (pos[0] + offset[0]) * scale,
    top: base.top + (pos[1] + offset[1]) * scale,
    width: Math.max(size[0] * scale, 8),
    height: Math.max(size[1] * scale, 8),
  };
}

function _showNodeViewHighlight(ctx, node) {
  clearNodeViewHighlight();
  const overlay = document.createElement("div");
  overlay.id = _VIEW_HIGHLIGHT_ID;
  overlay.className = "comfymodal-node-view-highlight";
  overlay.setAttribute("data-testid", "node-view-highlight");
  const rect = _nodeScreenRect(ctx, node);
  overlay.style.left = rect.left + "px";
  overlay.style.top = rect.top + "px";
  overlay.style.width = rect.width + "px";
  overlay.style.height = rect.height + "px";
  document.body.appendChild(overlay);
  _viewHighlightTimer = setTimeout(() => {
    _viewHighlightTimer = null;
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }, _VIEW_HIGHLIGHT_MS);
}

/** Remove the transient node highlight (called on re-render/unmount). */
export function clearNodeViewHighlight() {
  if (_viewHighlightTimer) {
    clearTimeout(_viewHighlightTimer);
    _viewHighlightTimer = null;
  }
  const el = document.getElementById(_VIEW_HIGHLIGHT_ID);
  if (el && el.parentNode) el.parentNode.removeChild(el);
}

/**
 * Center *nodeId* on the canvas and flash a magenta border for 3s.
 * Returns { ok, reason } — never throws when the graph/canvas is absent.
 */
export function viewGraphNode(nodeId) {
  const ctx = getComfyGraphContext();
  if (!ctx.ok) return { ok: false, reason: ctx.reason || "Graph unavailable" };
  const node = _findGraphNodeById(ctx.graph, nodeId);
  if (!node) return { ok: false, reason: "Node not found on the canvas" };
  _injectViewStyles();
  _centerCanvasOnNode(ctx.canvas, node);
  _showNodeViewHighlight(ctx, node);
  return { ok: true };
}

// ── Node click detection ────────────────────────────────────────────────

function findClickedNode(e, ctx) {
  // Strategy 1: Try to use LiteGraph's built-in click detection via the graph canvas
  try {
    if (ctx.app.canvas && ctx.app.canvas.graph && ctx.app.graph) {
      const canvasEl = ctx.app.canvas.canvas || ctx.app.canvas;
      if (canvasEl) {
        const rect = canvasEl.getBoundingClientRect();
        const mx = (e.clientX - rect.left) * (canvasEl.width / rect.width || 1);
        const my = (e.clientY - rect.top) * (canvasEl.height / rect.height || 1);
        const node = ctx.app.graph.getNodeOnPos(mx, my);
        if (node) return node;
      }
    }
  } catch { /* fall through */ }

  // Strategy 2: Click on a .comfy-node element in the DOM
  const target = e.target;
  if (target) {
    // Walk up the DOM to find a node element
    let el = target;
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains("comfy-node")) {
        const nodeId = el.getAttribute("data-id") || el.dataset.id;
        const nodeType = el.getAttribute("data-type") || el.dataset.type;
        if (nodeId && ctx.graph) {
          const node = ctx.graph._nodes_by_id ? ctx.graph._nodes_by_id[Number(nodeId)] : null;
          if (node) return node;
          // Fall back to scanning nodes
          for (const n of ctx.graph.nodes || []) {
            if (String(n.id) === nodeId) return n;
          }
        }
        // Return a synthetic node if we can't find it in the graph
        return { id: Number(nodeId) || 0, type: nodeType || "?", title: "" };
      }
      el = el.parentElement;
    }
  }

  return null;
}

// ── Candidate extraction ────────────────────────────────────────────────

export function extractNodeCandidates(node) {
  const candidates = [];
  if (!node) return candidates;

  // Widgets (inputs visible on the node)
  // Phase 4: capture full LiteGraph widget schema metadata so the preset
  // wizard can persist enum options, range, step, precision, multiline,
  // boolean state, and default values directly from the live graph.
  if (node.widgets && Array.isArray(node.widgets)) {
    node.widgets.forEach((w) => {
      if (w && w.name) {
        const opts = w.options || {};
        let schemaType = w.type || "string";
        // Map LiteGraph widget types to schema kinds
        if (schemaType === "combo" || schemaType === "dropdown") schemaType = "enum";
        else if (schemaType === "number") schemaType = "number";
        else if (schemaType === "slider") schemaType = "number";
        else if (schemaType === "toggle") schemaType = "boolean";
        else if (schemaType === "converted-widget") schemaType = "string";

        candidates.push({
          kind: "widget",
          name: w.name,
          type: w.type || "string",
          label: w.label || w.name,
          // Phase 4: widget schema metadata
          schemaType: schemaType,
          enumValues: opts.values || null,
          min: opts.min ?? null,
          max: opts.max ?? null,
          step: opts.step ?? null,
          precision: opts.precision ?? null,
          defaultValue: opts.default !== undefined ? opts.default : (w.value ?? null),
          multiline: !!opts.multiline,
        });
      }
    });
  }

  // Inputs (connections)
  if (node.inputs && Array.isArray(node.inputs)) {
    node.inputs.forEach((inp) => {
      if (inp && inp.name) {
        candidates.push({
          kind: "input",
          name: inp.name,
          type: inp.type || "*",
          label: inp.label || inp.name,
        });
      }
    });
  }

  // Outputs (connections)
  if (node.outputs && Array.isArray(node.outputs)) {
    node.outputs.forEach((out, idx) => {
      if (out && out.name) {
        candidates.push({
          kind: "output",
          name: out.name,
          type: out.type || "*",
          label: out.label || out.name,
          index: idx,
        });
      }
    });
  }

  // If no widgets/inputs/outputs found, add a node-level fallback
  if (candidates.length === 0) {
    candidates.push({
      kind: "node",
      name: "",
      type: node.type || "?",
      label: node.title || node.type || "Unknown",
    });
  }

  return candidates;
}

// ── Reset (for tests and cleanup) ──────────────────────────────────────

export function _resetCaptureStateForTest() {
  cancelGraphBinding();
  _captureState.active = false;
  _captureState.resolve = null;
  _captureState.cleanup = null;
}
