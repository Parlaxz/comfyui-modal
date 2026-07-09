// Modal Studio — Backend
//
// Redesigned with two internal sections/tabs: Snapshots | Backend Presets.
// Workflow Snapshots: captures of the current ComfyUI graph.
// Backend Presets: runnable configurations referencing snapshots.
//
// Exports helpers for Playground compare-backends integration.

let _backendCache = null;
let _selectedItemId = null;

function el(tag, props = {}, children = []) {
  const e = document.createElement(tag);
  for (const k in props) {
    if (k === "class") e.className = props[k];
    else if (k === "style") e.style.cssText = props[k];
    else if (k === "text") e.textContent = props[k];
    else if (k.startsWith("on") && typeof props[k] === "function") {
      e.addEventListener(k.slice(2).toLowerCase(), props[k]);
    } else if (k === "value") {
      e.value = props[k];
    } else {
      e.setAttribute(k, props[k]);
    }
  }
  for (const c of (Array.isArray(children) ? children : [children])) {
    if (c == null) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

// ── Status badge helper ────────────────────────────────────────────────

function statusBadge(text, kind) {
  const cls = kind === "ok" ? "comfymodal-studio-status-badge ok"
    : kind === "warn" ? "comfymodal-studio-status-badge warn"
    : kind === "error" ? "comfymodal-studio-status-badge error"
    : "comfymodal-studio-status-badge neutral";
  return el("span", { class: cls, text: text });
}

// ── Features chip grid ─────────────────────────────────────────────────

function renderFeaturesChipGrid(features, onChange) {
  const grid = el("div", { class: "comfymodal-studio-features-chip-grid" });
  const known = ["txt2img", "object_remove", "object_replace"];
  const labels = { txt2img: "Txt2Img", object_remove: "Object Remove", object_replace: "Object Replace" };
  const selected = features || [];
  known.forEach((fid) => {
    const isChecked = selected.includes(fid);
    const chip = el("div", {
      class: "comfymodal-studio-feature-chip" + (isChecked ? " checked" : ""),
      "data-feature": fid,
    }, [
      el("span", { class: "chip-check", text: "\u2713 " }),
      el("span", { text: labels[fid] || fid }),
    ]);
    chip.addEventListener("click", () => {
      const was = chip.classList.contains("checked");
      chip.classList.toggle("checked");
      const updated = [];
      grid.querySelectorAll(".comfymodal-studio-feature-chip").forEach((c) => {
        if (c.classList.contains("checked")) updated.push(c.dataset.feature);
      });
      if (onChange) onChange(updated);
    });
    grid.appendChild(chip);
  });
  return grid;
}

// ── API helpers ────────────────────────────────────────────────────────

export async function getBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends`);
    if (!res.ok) return [];
    const data = await res.json();
    _backendCache = (data && data.backends) || [];
    return _backendCache;
  } catch {
    return [];
  }
}

export async function getCompareBackends(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  try {
    const res = await fetch(`${apiBase}/studio/backends?kind=comparable`);
    if (!res.ok) return [];
    const data = await res.json();
    return (data && data.backends) || [];
  } catch {
    return [];
  }
}

async function apiFetch(apiBase, path, options) {
  try {
    const res = await fetch(`${apiBase}${path}`, options || {});
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

// ── Snapshots API ──────────────────────────────────────────────────────

async function listSnapshots(apiBase) {
  const data = await apiFetch(apiBase, "/studio/snapshots");
  return (data && data.snapshots) || [];
}

async function createSnapshot(apiBase, payload) {
  const data = await apiFetch(apiBase, "/studio/snapshots", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return data;
}

async function updateSnapshot(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function duplicateSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

async function archiveSnapshot(apiBase, id) {
  return apiFetch(apiBase, `/studio/snapshots/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ── Backend Presets API ────────────────────────────────────────────────

async function listPresets(apiBase) {
  const data = await apiFetch(apiBase, "/studio/presets");
  return (data && data.presets) || [];
}

async function createPreset(apiBase, payload) {
  return apiFetch(apiBase, "/studio/presets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function updatePreset(apiBase, id, payload) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

async function duplicatePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}/duplicate`, {
    method: "POST",
  });
}

async function archivePreset(apiBase, id) {
  return apiFetch(apiBase, `/studio/presets/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}

// ── Take Snapshot of Current Graph ─────────────────────────────────────

async function takeSnapshotOfCurrentGraph(apiBase, listContainer, detailContainer, renderFn) {
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
  _selectedItemId = null;
  renderSnapshotsList(listContainer, snapshots, apiBase, detailContainer);
  if (snapshots.length > 0) {
    _selectedItemId = snapshots[snapshots.length - 1].id;
    renderSnapshotDetail(detailContainer, snapshots[snapshots.length - 1], apiBase, listContainer);
  }
}

// ── Main render entry point ────────────────────────────────────────────

export function renderBackend(state, context) {
  const container = el("div", {
    class: "comfymodal-studio-backend",
    "data-testid": "backend-page",
  });

  const apiBase = (context && context.apiBase) || "/comfymodal";

  // Tabs: Snapshots | Backend Presets
  const tabs = el("div", { class: "comfymodal-studio-backend-tabs" });
  let activeTab = "snapshots";

  const body = el("div", { class: "comfymodal-studio-backend-body" });

  // Left list
  const listPanel = el("div", {
    class: "comfymodal-studio-backend-list",
    "data-testid": "backend-list",
  });

  // Right detail
  const detailPanel = el("div", {
    class: "comfymodal-studio-backend-detail",
    "data-testid": "backend-detail",
  });

  body.appendChild(listPanel);
  body.appendChild(detailPanel);

  function switchTab(tabId) {
    activeTab = tabId;
    tabs.querySelectorAll(".comfymodal-studio-backend-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tabId);
    });
    _selectedItemId = null;
    refreshList();
  }

  function makeTab(id, label) {
    const btn = el("button", {
      class: "comfymodal-studio-backend-tab" + (id === activeTab ? " active" : ""),
      "data-tab": id,
      text: label,
      onclick: () => switchTab(id),
    });
    return btn;
  }

  tabs.appendChild(makeTab("snapshots", "Snapshots"));
  tabs.appendChild(makeTab("presets", "Backend Presets"));

  container.appendChild(tabs);
  container.appendChild(body);

  function refreshList() {
    while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
    while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);

    if (activeTab === "snapshots") {
      renderSnapshotsPage(listPanel, detailPanel, apiBase);
    } else {
      renderPresetsPage(listPanel, detailPanel, apiBase);
    }
  }

  refreshList();
  return container;
}

// ── Snapshots page ─────────────────────────────────────────────────────

function renderSnapshotsPage(listPanel, detailPanel, apiBase) {
  const header = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:4px;flex-wrap:wrap;" }, [
    el("h3", {
      text: "Workflow Snapshots",
      style: "margin:0;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;",
    }),
    el("button", {
      class: "comfymodal-primary-btn",
      text: "+ Take Snapshot",
      style: "font-size:10px;padding:3px 8px;width:auto;",
      onclick: () => takeSnapshotOfCurrentGraph(apiBase, listPanel, detailPanel, renderSnapshotsList),
    }),
  ]);
  listPanel.appendChild(header);

  const listContent = el("div", { style: "flex:1;overflow-y:auto;" });
  listPanel.appendChild(listContent);

  listContent.textContent = "Loading snapshots...";
  listSnapshots(apiBase).then((snapshots) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    if (!snapshots || snapshots.length === 0) {
      listContent.appendChild(renderSnapshotsEmpty(apiBase));
      return;
    }
    renderSnapshotsList(listContent, snapshots, apiBase, detailPanel);
    if (snapshots.length > 0 && !_selectedItemId) {
      _selectedItemId = snapshots[0].id;
      renderSnapshotDetail(detailPanel, snapshots[0], apiBase, listContent);
    }
  });
}

function renderSnapshotsEmpty(apiBase) {
  return el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No snapshots yet.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: 'Click "+ Take Snapshot" to capture the current ComfyUI graph.', style: "font-size:12px;color:#555;margin:0 0 8px;" }),
  ]);
}

function renderSnapshotsList(container, snapshots, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);
  snapshots.forEach((snap) => {
    const id = snap.id || "unknown";
    const isActive = _selectedItemId === id;
    const label = snap.name || snap.id || "Unnamed";
    const status = snap.status || "unknown";
    const statusKind = status === "runnable" ? "ok" : status === "Needs bindings" ? "error" : "warn";
    const desc = snap.description || snap.modelSummary || "";
    const featureHint = (snap.compatibleFeatures || []).join(", ");

    const card = el("div", {
      class: "comfymodal-studio-snapshot-card" + (isActive ? " active" : ""),
      onclick: () => {
        _selectedItemId = id;
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

function renderSnapshotDetail(container, snap, apiBase, listContainer) {
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

  // Actions
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const saveBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Save",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      await updateSnapshot(apiBase, snap.id, fieldValues);
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
          _selectedItemId = null;
          const fresh = await listSnapshots(apiBase);
          while (container.firstChild) container.removeChild(container.firstChild);
          renderSnapshotsList(listContainer, fresh, apiBase, container);
          if (fresh.length > 0) {
            _selectedItemId = fresh[0].id;
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

// ── Backend Presets page ────────────────────────────────────────────────

function renderPresetsPage(listPanel, detailPanel, apiBase) {
  const header = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:4px;flex-wrap:wrap;" }, [
    el("h3", {
      text: "Backend Presets",
      style: "margin:0;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;",
    }),
    el("button", {
      class: "comfymodal-secondary-btn",
      text: "+ New Preset",
      style: "font-size:10px;padding:3px 8px;",
      onclick: () => renderPresetForm(null, apiBase, listPanel, detailPanel),
    }),
  ]);
  listPanel.appendChild(header);

  const listContent = el("div", { style: "flex:1;overflow-y:auto;" });
  listPanel.appendChild(listContent);

  // Legacy comparison profile discovery link
  const legacyNote = el("div", { style: "margin-bottom:8px;" }, [
    el("p", { text: "Presets from legacy comparison profiles are auto-discovered.", style: "font-size:10px;color:#555;" }),
  ]);
  listPanel.appendChild(legacyNote);

  listContent.textContent = "Loading presets...";
  listPresets(apiBase).then((presets) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    if (!presets || presets.length === 0) {
      listContent.appendChild(renderPresetsEmpty(apiBase));
      return;
    }
    renderPresetsList(listContent, presets, apiBase, detailPanel);
    if (presets.length > 0 && !_selectedItemId) {
      _selectedItemId = presets[0].id;
      renderPresetDetail(detailPanel, presets[0], apiBase, listContent);
    }
  });
}

// Legacy empty state renderer (kept for backward compatibility with tests)
function renderEmptyState(listContent, detailPanel, context, state) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const emptyCard = el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backends configured via legacy discovery.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: "Use the Snapshots or Backend Presets tabs above.", style: "font-size:12px;color:#555;margin:0 0 8px;" }),
  ]);
  while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
  listContent.appendChild(emptyCard);
}

function renderPresetsEmpty(apiBase) {
  return el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backend presets configured.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: 'Click "+ New Preset" to create one, or legacy comparison profiles will be auto-discovered.', style: "font-size:12px;color:#555;margin:0;" }),
  ]);
}

function renderPresetsList(container, presets, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);
  presets.forEach((preset) => {
    const id = preset.id || "unknown";
    const isActive = _selectedItemId === id;
    const label = preset.label || preset.name || preset.id || "Unnamed";
    const snapshotId = preset.snapshotId || "";
    const disabled = preset.disabledReason || "";
    const desc = preset.description || "";

    const card = el("div", {
      class: "comfymodal-studio-preset-card" + (isActive ? " active" : ""),
      onclick: () => {
        _selectedItemId = id;
        container.querySelectorAll(".comfymodal-studio-preset-card").forEach((c) => c.classList.remove("active"));
        card.classList.add("active");
        while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
        renderPresetDetail(detailPanel, preset, apiBase, container);
      },
    }, [
      el("h4", { text: label.substring(0, 60) }),
      el("p", { text: ((desc || (snapshotId ? `Snapshot: ${snapshotId.substring(0, 12)}` : "") || "No description")).substring(0, 80) }),
    ]);
    if (disabled) {
      card.appendChild(el("p", { text: `Disabled: ${disabled}`, style: "color:#f87171;font-size:10px;margin:2px 0;" }));
    }
    container.appendChild(card);
  });
}

function renderPresetDetail(container, preset, apiBase, listContainer) {
  while (container.firstChild) container.removeChild(container.firstChild);

  const card = el("div", { class: "comfymodal-studio-backend-detail-card" });
  const fieldValues = { ...preset };

  const fields = [
    { key: "label", label: "Label", type: "text", value: preset.label || preset.name || "" },
    { key: "description", label: "Description", type: "textarea", value: preset.description || "" },
    { key: "snapshotId", label: "Snapshot ID", type: "text", value: preset.snapshotId || "" },
    { key: "sourceType", label: "Source Type", type: "text", value: preset.sourceType || "" },
    { key: "sourceId", label: "Source ID", type: "text", value: preset.sourceId || "" },
    { key: "disabledReason", label: "Disabled Reason", type: "text", value: preset.disabledReason || "" },
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
  const chipGrid = renderFeaturesChipGrid(preset.compatibleFeatures || [], (updated) => {
    fieldValues.compatibleFeatures = updated;
  });
  compatGroup.appendChild(chipGrid);
  card.appendChild(compatGroup);

  // Defaults
  const defaults = preset.defaults || {};
  if (Object.keys(defaults).length > 0) {
    const defaultsGroup = el("div", { class: "comfymodal-studio-backend-field" });
    defaultsGroup.appendChild(el("label", { text: "Defaults" }));
    defaultsGroup.appendChild(el("p", { text: JSON.stringify(defaults, null, 2), style: "font-size:10px;color:#555;white-space:pre-wrap;" }));
    card.appendChild(defaultsGroup);
  }

  // Archived/Disabled
  if (preset.archived) {
    card.appendChild(el("p", { text: "\u26a0 Archived", style: "font-size:11px;color:#f87171;margin:4px 0;" }));
  }

  // Actions
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const saveBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Save",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      await updatePreset(apiBase, preset.id, fieldValues);
      const fresh = await listPresets(apiBase);
      renderPresetsList(listContainer, fresh, apiBase, container);
    },
  });
  actions.appendChild(saveBtn);

  const dupBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Duplicate",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      await duplicatePreset(apiBase, preset.id);
      const fresh = await listPresets(apiBase);
      renderPresetsList(listContainer, fresh, apiBase, container);
    },
  });
  actions.appendChild(dupBtn);

  if (!preset.archived) {
    const archiveBtn = el("button", {
      class: "comfymodal-destructive-btn",
      text: "Archive",
      style: "font-size:10px;padding:5px 12px;",
      onclick: async () => {
        if (confirm("Archive this preset?")) {
          await archivePreset(apiBase, preset.id);
          _selectedItemId = null;
          const fresh = await listPresets(apiBase);
          while (container.firstChild) container.removeChild(container.firstChild);
          renderPresetsList(listContainer, fresh, apiBase, container);
          if (fresh.length > 0) {
            _selectedItemId = fresh[0].id;
            renderPresetDetail(container, fresh[0], apiBase, listContainer);
          }
        }
      },
    });
    actions.appendChild(archiveBtn);
  }

  card.appendChild(actions);
  container.appendChild(card);
}

function renderPresetForm(existing, apiBase, listPanel, detailPanel) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const formCard = el("div", { class: "comfymodal-studio-backend-detail-card" });

  const heading = el("h4", {
    text: "New Backend Preset",
    style: "margin:0 0 12px;font-size:12px;color:#d0d0d0;text-transform:uppercase;letter-spacing:0.05em;",
  });
  formCard.appendChild(heading);

  const fieldValues = { label: "", description: "", snapshotId: "", compatibleFeatures: [] };
  const fields = [
    { key: "label", label: "Label", type: "text" },
    { key: "description", label: "Description", type: "textarea" },
    { key: "snapshotId", label: "Snapshot ID", type: "text" },
  ];

  fields.forEach((f) => {
    const fg = el("div", { class: "comfymodal-studio-backend-field" });
    fg.appendChild(el("label", { text: f.label }));
    let input;
    if (f.type === "textarea") {
      input = el("textarea", { rows: 2 });
    } else {
      input = el("input", { type: "text" });
    }
    input.addEventListener("input", () => { fieldValues[f.key] = input.value; });
    fg.appendChild(input);
    formCard.appendChild(fg);
  });

  // Compatible Features
  const compatGroup = el("div", { class: "comfymodal-studio-backend-field" });
  compatGroup.appendChild(el("label", { text: "Compatible Features" }));
  const chipGrid = renderFeaturesChipGrid([], (updated) => {
    fieldValues.compatibleFeatures = updated;
  });
  compatGroup.appendChild(chipGrid);
  formCard.appendChild(compatGroup);

  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const createBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Create",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      const result = await createPreset(apiBase, fieldValues);
      if (result) {
        _selectedItemId = null;
        // Re-render the presets page
        while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
        while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
        renderPresetsPage(listPanel, detailPanel, apiBase);
      }
    },
  });
  actions.appendChild(createBtn);

  const cancelBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Cancel",
    style: "font-size:10px;padding:5px 12px;",
    onclick: () => {
      _selectedItemId = null;
      while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
      while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
      renderPresetsPage(listPanel, detailPanel, apiBase);
    },
  });
  actions.appendChild(cancelBtn);

  formCard.appendChild(actions);
  detailPanel.appendChild(formCard);
}
