// Modal Studio — Backend Presets Page
//
// Preset list/detail/form rendering and CRUD wiring.
// Imports shared UI helpers from studio-ui.js and the chip grid / state
// from the glue module (studio-backend.js).

import { el } from "./studio-ui.js";
import { listPresets, createPreset, updatePreset, duplicatePreset, archivePreset } from "./studio-backend-api.js";
import { _STATE, renderFeaturesChipGrid } from "./studio-backend.js";

// ── Backend Presets page ──────────────────────────────────────────────────

export function renderPresetsPage(listPanel, detailPanel, apiBase) {
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
    if (presets.length > 0 && !_STATE.selectedItemId) {
      _STATE.selectedItemId = presets[0].id;
      renderPresetDetail(detailPanel, presets[0], apiBase, listContent);
    }
  });
}

function renderPresetsEmpty(apiBase) {
  return el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backend presets configured.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: 'Click "+ New Preset" to create one, or legacy comparison profiles will be auto-discovered.', style: "font-size:12px;color:#555;margin:0;" }),
  ]);
}

export function renderPresetsList(container, presets, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);
  presets.forEach((preset) => {
    const id = preset.id || "unknown";
    const isActive = _STATE.selectedItemId === id;
    const label = preset.label || preset.name || preset.id || "Unnamed";
    const snapshotId = preset.snapshotId || "";
    const disabled = preset.disabledReason || "";
    const desc = preset.description || "";

    const card = el("div", {
      class: "comfymodal-studio-preset-card" + (isActive ? " active" : ""),
      onclick: () => {
        _STATE.selectedItemId = id;
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

export function renderPresetDetail(container, preset, apiBase, listContainer) {
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
          _STATE.selectedItemId = null;
          const fresh = await listPresets(apiBase);
          while (container.firstChild) container.removeChild(container.firstChild);
          renderPresetsList(listContainer, fresh, apiBase, container);
          if (fresh.length > 0) {
            _STATE.selectedItemId = fresh[0].id;
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

export function renderPresetForm(existing, apiBase, listPanel, detailPanel) {
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
        _STATE.selectedItemId = null;
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
      _STATE.selectedItemId = null;
      while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
      while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
      renderPresetsPage(listPanel, detailPanel, apiBase);
    },
  });
  actions.appendChild(cancelBtn);

  formCard.appendChild(actions);
  detailPanel.appendChild(formCard);
}
