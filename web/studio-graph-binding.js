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

export function beginGraphBindingCapture({ bindingKey, label, onCapture, onCancel }) {
  if (_captureState.active) {
    cancelGraphBinding();
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
    document.removeEventListener("click", handleClick, true);
    document.removeEventListener("keydown", handleKeydown);
    document.body.classList.remove("comfymodal-binding-capture-active");
    if (hintEl.parentNode) hintEl.parentNode.removeChild(hintEl);
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
    _captureState.cleanup();
    _captureState.active = false;
    _captureState.cleanup = null;
  }
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
  if (node.widgets && Array.isArray(node.widgets)) {
    node.widgets.forEach((w) => {
      if (w && w.name) {
        candidates.push({
          kind: "widget",
          name: w.name,
          type: w.type || "string",
          label: w.label || w.name,
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
