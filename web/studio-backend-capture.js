// Modal Studio — Graph Capture Logic
//
// Captures the current ComfyUI graph and creates a snapshot via the API.
// Imported dynamically by the snapshots page module at runtime.

import { el } from "./studio-ui.js";
import { createSnapshot, listSnapshots } from "./studio-backend-api.js";
import { _STATE, renderFeaturesChipGrid } from "./studio-backend.js";

// ── Take Snapshot of Current Graph ────────────────────────────────────────

export async function takeSnapshotOfCurrentGraph(apiBase, listContainer, detailContainer, renderFn) {
  // Attempt to serialize the current ComfyUI graph
  const app = window.__comfymodal_comfy_app;
  let graphJson = null;
  let apiPromptJson = null;
  let error = null;

  try {
    if (app && app.graph && typeof app.graph.serialize === "function") {
      graphJson = app.graph.serialize();
    } else {
      // Try alternate methods
      const canvas = document.querySelector(".comfy-graph canvas") ||
                     document.querySelector("canvas");
      if (window.app && window.app.graph && typeof window.app.graph.serialize === "function") {
        graphJson = window.app.graph.serialize();
      } else {
        error = "Cannot access ComfyUI graph API. Open the main ComfyUI tab first.";
      }
    }
  } catch (e) {
    error = `Failed to serialize graph: ${e.message}`;
  }

  if (error) {
    // Show error in detail panel
    while (detailContainer.firstChild) detailContainer.removeChild(detailContainer.firstChild);
    const card = el("div", { class: "comfymodal-studio-backend-detail-card" }, [
      el("h4", { text: "Error", style: "color:#f87171;margin:0 0 8px;" }),
      el("p", { text: error, style: "color:#aaa;font-size:12px;" }),
    ]);
    detailContainer.appendChild(card);
    return;
  }

  // Attempt to generate API prompt safely
  let status = "Needs API prompt";
  try {
    if (app && typeof app.graphToPrompt === "function") {
      apiPromptJson = await app.graphToPrompt();
      status = "runnable";
    } else if (window.comfyAPI && window.comfyAPI.prompt && typeof window.comfyAPI.prompt.graphToPrompt === "function") {
      apiPromptJson = await window.comfyAPI.prompt.graphToPrompt();
      status = "runnable";
    } else {
      // Try ComfyUI's built-in mechanism
      const w = typeof comfyUI !== "undefined" ? comfyUI : null;
      if (w && w.graphToPrompt) {
        apiPromptJson = await w.graphToPrompt();
        status = "runnable";
      } else {
        apiPromptJson = null;
        status = "Needs API prompt";
      }
    }
  } catch (e) {
    apiPromptJson = null;
    status = "Needs bindings";
  }

  // Create snapshot via API
  const payload = {
    name: `Snapshot ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`,
    description: "",
    compatibleFeatures: [],
    graphJson: graphJson,
    apiPromptJson: apiPromptJson,
    status: status,
  };

  const result = await createSnapshot(apiBase, payload);
  if (!result) {
    while (detailContainer.firstChild) detailContainer.removeChild(detailContainer.firstChild);
    const card = el("div", { class: "comfymodal-studio-backend-detail-card" }, [
      el("h4", { text: "Error", style: "color:#f87171;margin:0 0 8px;" }),
      el("p", { text: "Failed to save snapshot via API.", style: "color:#aaa;font-size:12px;" }),
    ]);
    detailContainer.appendChild(card);
    return;
  }

  // Refresh the list
  const snapshots = await listSnapshots(apiBase);
  _STATE.selectedItemId = null;
  const { renderSnapshotsList, renderSnapshotDetail } = await import("./studio-backend-snapshots.js");
  renderSnapshotsList(listContainer, snapshots, apiBase, detailContainer);
  if (snapshots.length > 0) {
    _STATE.selectedItemId = snapshots[snapshots.length - 1].id;
    renderSnapshotDetail(detailContainer, snapshots[snapshots.length - 1], apiBase, listContainer);
  }
}
