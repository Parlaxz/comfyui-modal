// Modal Studio — Graph Capture Logic
//
// Captures the current ComfyUI graph and creates a snapshot via the API.
// Imported dynamically by the snapshots page module at runtime.

import { el } from "./studio-ui.js";
import { createSnapshot, listSnapshots } from "./studio-backend-api.js";
import { _STATE } from "./studio-backend.js";
import { getComfyGraphContext } from "./studio-graph-binding.js";

// ── Capture Current Comfy Graph (structured, non-mutating) ──────────────

export async function captureCurrentComfyGraph() {
  const ctx = getComfyGraphContext();
  const warnings = [];

  if (!ctx.ok) return { ok: false, reason: ctx.reason, warnings };

  const { app, graph } = ctx;

  let graphJson = null;
  try {
    if (graph && typeof graph.serialize === "function") {
      graphJson = graph.serialize();
    } else {
      return { ok: false, reason: "ComfyUI graph is not ready.", warnings };
    }
  } catch (e) {
    return { ok: false, reason: `Failed to serialize graph: ${e.message}`, warnings };
  }

  let apiPromptJson = null;
  try {
    if (typeof app.graphToPrompt === "function") {
      apiPromptJson = await app.graphToPrompt();
    } else {
      warnings.push("ComfyUI API prompt generation is unavailable.");
    }
  } catch {
    warnings.push("Could not generate API prompt automatically.");
  }

  return { ok: true, graphJson, apiPromptJson, warnings };
}

// ── Take Snapshot of Current Graph (legacy flow) ────────────────────────

export async function takeSnapshotOfCurrentGraph(apiBase, listContainer, detailContainer, renderFn) {
  const capture = await captureCurrentComfyGraph();
  if (!capture.ok) {
    while (detailContainer.firstChild) detailContainer.removeChild(detailContainer.firstChild);
    const card = el("div", { class: "comfymodal-studio-backend-detail-card" }, [
      el("h4", { text: "Error", style: "color:#f87171;margin:0 0 8px;" }),
      el("p", { text: capture.reason || "Failed to capture graph", style: "color:#aaa;font-size:12px;" }),
    ]);
    detailContainer.appendChild(card);
    return;
  }

  const graphJson = capture.graphJson;
  const apiPromptJson = capture.apiPromptJson;

  // Create snapshot via API
  const payload = {
    name: `Snapshot ${new Date().toLocaleDateString()} ${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`,
    description: "",
    compatibleFeatures: [],
    graphJson: graphJson,
    apiPromptJson: apiPromptJson,
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
