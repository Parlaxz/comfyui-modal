// Modal Studio — Snapshots Page
//
// Snapshot list/detail rendering and CRUD wiring.
// Imports shared UI helpers from studio-ui.js and the chip grid / state
// from the glue module (studio-backend.js).

import { el, statusBadge } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import { listSnapshots, updateSnapshot, duplicateSnapshot, archiveSnapshot } from "./studio-backend-api.js";
import { _STATE, renderFeaturesChipGrid, invalidateRuntimePresetsCache } from "./studio-backend.js";
import { getPresetCapabilitySummary } from "./studio-preset-capabilities.js";

// ── Snapshots page ────────────────────────────────────────────────────────

export function renderSnapshotsPage(listPanel, detailPanel, apiBase) {
  const header = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:4px;flex-wrap:wrap;" }, [
    el("h3", {
      text: "Workflow Snapshots",
      style: "margin:0;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;",
    }),
    el("button", {
      class: "comfymodal-secondary-btn",
      text: "+ Take Snapshot (Advanced)",
      style: "font-size:10px;padding:3px 8px;width:auto;",
      title: "Advanced: Use Make Preset for the primary creation flow",
      onclick: () => {
        if (!confirm("This is an advanced action. Snapshots are normally created automatically by 'Make Preset'. Continue?")) return;
        import("./studio-backend-capture.js").then(({ takeSnapshotOfCurrentGraph }) => {
          takeSnapshotOfCurrentGraph(apiBase, listPanel, detailPanel, renderSnapshotsList);
        });
      },
    }),
  ]);
  listPanel.appendChild(header);

  const listContent = el("div", { style: "flex:1;overflow-y:auto;" });
  listPanel.appendChild(listContent);

  listContent.appendChild(renderLoadingState({
    label: "Loading snapshots\u2026",
    size: "page",
    testid: "backend-snapshots-loading",
  }));
  listSnapshots(apiBase).then((snapshots) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    // null or undefined means network/API error
    if (snapshots === null || snapshots === undefined) {
      listContent.appendChild(el("div", { class: "comfymodal-studio-card" }, [
        el("p", { text: "Could not load snapshots from server.", style: "font-weight:600;margin:0 0 4px;color:#f87171;" }),
        el("p", { text: "Check that the backend server is running and the API is accessible.", style: "font-size:11px;color:#888;margin:0;" }),
      ]));
      return;
    }
    if (snapshots.length === 0) {
      listContent.appendChild(renderSnapshotsEmpty(apiBase));
      return;
    }
    renderSnapshotsList(listContent, snapshots, apiBase, detailPanel);
    if (snapshots.length > 0 && !_STATE.selectedItemId) {
      _STATE.selectedItemId = snapshots[0].id;
      renderSnapshotDetail(detailPanel, snapshots[0], apiBase, listContent);
    }
  }).catch((err) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    listContent.appendChild(el("div", { class: "comfymodal-studio-card" }, [
      el("p", { text: "Error loading snapshots.", style: "font-weight:600;margin:0 0 4px;color:#f87171;" }),
      el("p", { text: err.message || "Unknown error", style: "font-size:11px;color:#888;margin:0;" }),
    ]));
  });
}

function renderSnapshotsEmpty(apiBase) {
  return el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No snapshots yet.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: 'Use "Make Preset" above to create presets (snapshots are created automatically).', style: "font-size:12px;color:#555;margin:0 0 8px;" }),
    el("p", { text: 'Or use "+ Take Snapshot (Advanced)" for manual capture.', style: "font-size:11px;color:#666;margin:0;font-style:italic;" }),
  ]);
}

export function renderSnapshotsList(container, snapshots, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);
  snapshots.forEach((snap) => {
    const id = snap.id || "unknown";
    const isActive = _STATE.selectedItemId === id;
    const label = snap.name || snap.id || "Unnamed";
    const status = snap.status || "unknown";
    const statusKind = status === "runnable" ? "ok" : status === "Needs bindings" ? "error" : "warn";
    const desc = snap.description || snap.modelSummary || "";
    const featureHint = (snap.compatibleFeatures || []).join(", ");

    const card = el("div", {
      class: "comfymodal-studio-snapshot-card" + (isActive ? " active" : ""),
      onclick: () => {
        _STATE.selectedItemId = id;
        container.querySelectorAll(".comfymodal-studio-snapshot-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
        renderSnapshotDetail(detailPanel, snap, apiBase, container);
      },
    }, [
      el("h4", { text: label.substring(0, 60) }),
      el("p", { style: "margin:2px 0;" }, [statusBadge(status, statusKind)]),
      el("p", { text: (desc || featureHint || "").substring(0, 80) }),
    ]);
    container.appendChild(card);
  });
}

export function renderSnapshotDetail(container, snap, apiBase, listContainer) {
  while (container.firstChild) container.removeChild(container.firstChild);

  const card = el("div", { class: "comfymodal-studio-backend-detail-card" });

  // Status
  const status = snap.status || "unknown";
  const statusKind = status === "runnable" ? "ok" : status === "Needs bindings" ? "error" : "warn";
  card.appendChild(el("div", { style: "margin-bottom:8px;" }, [statusBadge(status, statusKind)]));

  const fieldValues = { ...snap };
  const fields = [
    { key: "name", label: "Name", type: "text", value: snap.name || "" },
    { key: "description", label: "Description", type: "textarea", value: snap.description || "" },
    { key: "modelSummary", label: "Model Summary", type: "textarea", value: snap.modelSummary || "" },
  ];

  fields.forEach((f) => {
    const fg = el("div", { class: "comfymodal-studio-backend-field" });
    fg.appendChild(el("label", { text: f.label }));
    let input;
    if (f.type === "textarea") {
      input = el("textarea", { value: f.value, rows: 2 });
    } else {
      input = el("input", { type: "text", value: f.value });
    }
    input.addEventListener("input", () => { fieldValues[f.key] = input.value; });
    fg.appendChild(input);
    card.appendChild(fg);
  });

  // Compatible Features chip grid
  const compatGroup = el("div", { class: "comfymodal-studio-backend-field" });
  compatGroup.appendChild(el("label", { text: "Compatible Features" }));
  const chipGrid = renderFeaturesChipGrid(snap.compatibleFeatures || [], (updated) => {
    fieldValues.compatibleFeatures = updated;
  });
  compatGroup.appendChild(chipGrid);
  card.appendChild(compatGroup);

  // Graph JSON summary
  if (snap.graphJson) {
    const nodeCount = snap.graphJson.nodes ? snap.graphJson.nodes.length : "?";
    const linkCount = snap.graphJson.links ? snap.graphJson.links.length : "?";
    const graphGroup = el("div", { class: "comfymodal-studio-backend-field" });
    graphGroup.appendChild(el("label", { text: "Graph" }));
    graphGroup.appendChild(el("p", { text: `${nodeCount} nodes, ${linkCount} links`, style: "font-size:11px;color:#555;margin:2px 0;" }));
    card.appendChild(graphGroup);
  }

  // API Prompt status
  if (snap.apiPromptJson) {
    card.appendChild(el("p", { text: "\u2713 API prompt available", style: "font-size:11px;color:#4ade80;margin:4px 0;" }));
  } else if (status === "Needs bindings" || status === "Needs API prompt") {
    card.appendChild(el("p", { text: "\u26a0 " + (status === "Needs bindings" ? "Missing required bindings or output mapping" : "API prompt not yet generated"), style: "font-size:11px;color:#fbbf24;margin:4px 0;" }));
  }

  // Source info
  const source = snap.source || "";
  if (source) {
    card.appendChild(el("p", { text: `Source: ${source}`, style: "font-size:11px;color:#555;margin:4px 0;" }));
  }

  // Timestamps
  const created = snap.createdAt || "";
  const updated = snap.updatedAt || "";
  if (created) card.appendChild(el("p", { text: `Created: ${created}`, style: "font-size:10px;color:#555;margin:2px 0;" }));
  if (updated) card.appendChild(el("p", { text: `Updated: ${updated}`, style: "font-size:10px;color:#555;margin:2px 0;" }));

  // Archived
  if (snap.archived) {
    card.appendChild(el("p", { text: "\u26a0 Archived", style: "font-size:11px;color:#f87171;margin:4px 0;" }));
  }
  if (snap.disabledReason) {
    card.appendChild(el("p", { text: `Disabled: ${snap.disabledReason}`, style: "font-size:11px;color:#f87171;margin:4px 0;" }));
  }

  // ── Capability summary per feature ──────────────────────────────────
  (snap.compatibleFeatures || []).forEach((fid) => {
    const summary = getPresetCapabilitySummary(snap, fid);
    const summaryGroup = el("div", {
      style: "margin-bottom:6px;padding:6px;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:3px;",
    });
    summaryGroup.appendChild(el("p", {
      text: `${fid} Capability`,
      style: "font-size:10px;font-weight:600;color:#888;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.05em;",
    }));

    // Feature status
    const featStatus = summary.runnable ? "\u2713 Runnable" : `\u26a0 ${summary.disabledReason || "Needs attention"}`;
    summaryGroup.appendChild(el("p", {
      text: `Status: ${featStatus}`,
      style: `font-size:10px;color:${summary.runnable ? "#4ade80" : "#fbbf24"};margin:0 0 4px;`,
    }));

    // API graph status
    summaryGroup.appendChild(el("p", {
      text: `API graph: ${summary.hasApiGraph ? "\u2713 present" : "\u2717 missing"}`,
      style: `font-size:10px;color:${summary.hasApiGraph ? "#4ade80" : "#f87171"};margin:0 0 2px;`,
    }));

    // Output mapping status
    summaryGroup.appendChild(el("p", {
      text: `Output mapped: ${summary.hasOutputBinding ? "\u2713 yes" : "\u2717 no"}`,
      style: `font-size:10px;color:${summary.hasOutputBinding ? "#4ade80" : "#f87171"};margin:0 0 2px;`,
    }));

    // Required bindings
    const bindCount = snap.nodeBindings ? Object.keys(snap.nodeBindings).length : 0;
    summaryGroup.appendChild(el("p", {
      text: `Node bindings: ${bindCount} total`,
      style: "font-size:10px;color:#888;margin:0 0 2px;",
    }));

    summaryGroup.appendChild(el("p", {
      text: `Required bindings: ${summary.totalBoundRequired}/${summary.totalRequired}`,
      style: `font-size:10px;color:${summary.allRequiredMet ? "#4ade80" : "#f87171"};margin:0 0 2px;`,
    }));

    summary.requiredBindings.forEach((d) => {
      const item = el("div", { style: "display:flex;align-items:center;gap:4px;margin:2px 0;" }, [
        el("span", { text: d.bound ? "\u2713" : "\u2717", style: `font-size:10px;color:${d.bound ? "#4ade80" : "#f87171"};` }),
        el("span", { text: d.label, style: "font-size:10px;color:#aaa;" }),
        d.binding ? el("span", {
          text: `\u2192 ${d.binding.nodeTitle || d.binding.nodeId || ""}`,
          style: "font-size:9px;color:#666;margin-left:4px;",
        }) : null,
      ]);
      summaryGroup.appendChild(item);
    });

    // Missing required notice
    if (!summary.allRequiredMet) {
      summaryGroup.appendChild(el("p", {
        text: `Missing required: ${summary.missingRequired.length}`,
        style: "font-size:9px;color:#f87171;margin:4px 0 0;",
      }));
    }

    card.appendChild(summaryGroup);
  });

  // Actions
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const saveBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Save",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      await updateSnapshot(apiBase, snap.id, fieldValues);
      invalidateRuntimePresetsCache();
      const fresh = await listSnapshots(apiBase);
      renderSnapshotsList(listContainer, fresh, apiBase, container);
    },
  });
  actions.appendChild(saveBtn);

  const dupBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Duplicate",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      await duplicateSnapshot(apiBase, snap.id);
      invalidateRuntimePresetsCache();
      const fresh = await listSnapshots(apiBase);
      renderSnapshotsList(listContainer, fresh, apiBase, container);
    },
  });
  actions.appendChild(dupBtn);

  if (!snap.archived) {
    const archiveBtn = el("button", {
      class: "comfymodal-destructive-btn",
      text: "Archive",
      style: "font-size:10px;padding:5px 12px;",
      onclick: async () => {
        if (confirm("Archive this snapshot?")) {
          await archiveSnapshot(apiBase, snap.id);
          invalidateRuntimePresetsCache();
          _STATE.selectedItemId = null;
          const fresh = await listSnapshots(apiBase);
          while (container.firstChild) container.removeChild(container.firstChild);
          renderSnapshotsList(listContainer, fresh, apiBase, container);
          if (fresh.length > 0) {
            _STATE.selectedItemId = fresh[0].id;
            renderSnapshotDetail(container, fresh[0], apiBase, listContainer);
          }
        }
      },
    });
    actions.appendChild(archiveBtn);
  }

  card.appendChild(actions);
  container.appendChild(card);
}
