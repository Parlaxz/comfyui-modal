// Modal Studio — Graph Capture Logic
//
// Captures the current ComfyUI graph. Imported dynamically by the Workflows
// page for "Capture new version" and import-from-graph. The legacy
// snapshot-creation flow is gone with the Snapshots page.

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
