// Modal Studio — Backend Presets Page
//
// Preset list/detail/form rendering and CRUD wiring.
// Imports shared UI helpers from studio-ui.js and the chip grid / state
// from the glue module (studio-backend.js).

import { el } from "./studio-ui.js";
import { listPresets, createPreset, updatePreset, duplicatePreset, deletePreset } from "./studio-backend-api.js";
import { _STATE, renderFeaturesChipGrid, launchPresetWizardForEdit, invalidateRuntimePresetsCache } from "./studio-backend.js";
import { clearSelection } from "./studio-playground-state.js";
import {
  getPresetCapabilitySummary,
} from "./studio-preset-capabilities.js";

// ── Backend Presets page ──────────────────────────────────────────────────

export function renderPresetsPage(listPanel, detailPanel, apiBase) {
  const header = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:4px;flex-wrap:wrap;" }, [
    el("h3", {
      text: "Backend Presets",
      style: "margin:0;font-size:11px;font-weight:600;color:#888;text-transform:uppercase;letter-spacing:0.05em;",
    }),
    el("button", {
      class: "comfymodal-secondary-btn",
      text: "+ New Preset (Manual)",
      style: "font-size:10px;padding:3px 8px;",
      title: "Advanced: manual creation without binding wizard",
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
    // null or undefined means network/API error (not just empty)
    if (presets === null || presets === undefined) {
      listContent.appendChild(el("div", { class: "comfymodal-studio-card" }, [
        el("p", { text: "Could not load presets from server.", style: "font-weight:600;margin:0 0 4px;color:#f87171;" }),
        el("p", { text: "Check that the backend server is running and the API is accessible.", style: "font-size:11px;color:#888;margin:0;" }),
      ]));
      return;
    }
    if (presets.length === 0) {
      listContent.appendChild(renderPresetsEmpty(apiBase));
      return;
    }
    renderPresetsList(listContent, presets, apiBase, detailPanel);
    if (presets.length > 0 && !_STATE.selectedItemId) {
      _STATE.selectedItemId = presets[0].id;
      renderPresetDetail(detailPanel, presets[0], apiBase, listContent);
    }
  }).catch((err) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    listContent.appendChild(el("div", { class: "comfymodal-studio-card" }, [
      el("p", { text: "Error loading presets.", style: "font-weight:600;margin:0 0 4px;color:#f87171;" }),
      el("p", { text: err.message || "Unknown error", style: "font-size:11px;color:#888;margin:0;" }),
    ]));
  });
}

function renderPresetsEmpty(apiBase) {
  return el("div", { class: "comfymodal-studio-card" }, [
    el("p", { text: "No backend presets configured.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: 'Use "Make Preset" above to create one from the current ComfyUI graph.', style: "font-size:12px;color:#555;margin:0 0 4px;" }),
    el("p", { text: 'Or click "+ New Preset" for manual creation (advanced).', style: "font-size:11px;color:#666;margin:0;font-style:italic;" }),
  ]);
}

/**
 * Render a single preset card (shared by grouped and ungrouped sections).
 */
function _renderPresetCard(preset, apiBase, listContainer, detailPanel) {
  const id = preset.id || "unknown";
  const isActive = _STATE.selectedItemId === id;
  const label = preset.label || preset.name || preset.id || "Unnamed";
  const snapshotId = preset.snapshotId || "";
  const disabled = preset.disabledReason || "";
  const desc = preset.description || "";
  const canEdit = !preset.archived;

  const card = el("div", {
    class: "comfymodal-studio-preset-card" + (isActive ? " active" : ""),
    onclick: function () {
      _STATE.selectedItemId = id;
      var allCards = listContainer.querySelectorAll(".comfymodal-studio-preset-card");
      allCards.forEach(function (c) { c.classList.remove("active"); });
      card.classList.add("active");
      while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
      renderPresetDetail(detailPanel, preset, apiBase, listContainer);
    },
    "data-testid": "preset-card-" + id.replace(/[^a-zA-Z0-9_-]/g, "_"),
  }, [
    el("h4", { text: label.substring(0, 60) }),
    el("p", { text: ((desc || (snapshotId ? "Snapshot: " + snapshotId.substring(0, 12) : "") || "No description")).substring(0, 80) }),
  ]);
  if (preset.group) {
    card.appendChild(el("p", { text: "Group: " + preset.group, style: "color:#666;font-size:9px;margin:2px 0;font-style:italic;" }));
  }
  if (disabled) {
    card.appendChild(el("p", { text: "Disabled: " + disabled, style: "color:#f87171;font-size:10px;margin:2px 0;" }));
  }
  if (canEdit) {
    var rowActions = el("div", { style: "display:flex;gap:4px;margin-top:4px;" });
    var delRowBtn = el("button", {
      class: "comfymodal-destructive-btn",
      text: "Delete preset",
      style: "font-size:9px;padding:2px 6px;",
      onclick: function (e) {
        e.stopPropagation();
        if (confirm("Delete this preset? (soft-delete \u2014 it can be restored via the server)")) {
          deletePreset(apiBase, preset.id).then(function () {
            clearSelection();
            invalidateRuntimePresetsCache();
            _STATE.selectedItemId = null;
            listPresets(apiBase).then(function (fresh) {
              while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
              renderPresetsList(listContainer, fresh, apiBase, detailPanel);
              if (fresh.length > 0) {
                _STATE.selectedItemId = fresh[0].id;
                while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
                renderPresetDetail(detailPanel, fresh[0], apiBase, listContainer);
              } else {
                while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
              }
            });
          });
        }
      },
    });
    rowActions.appendChild(delRowBtn);
    card.appendChild(rowActions);
  }
  return card;
}

export function renderPresetsList(container, presets, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);

  // Group presets by their optional `group` field
  var groups = {};
  var ungrouped = [];
  presets.forEach(function (preset) {
    var g = preset.group;
    if (g && typeof g === "string" && g.trim() !== "") {
      if (!groups[g]) groups[g] = [];
      groups[g].push(preset);
    } else {
      ungrouped.push(preset);
    }
  });

  var groupNames = Object.keys(groups).sort(function (a, b) { return a.localeCompare(b); });

  // Helper to create a collapsible group section
  function _createGroupSection(groupLabel, presetsArr, testIdSuffix) {
    var section = el("div", { class: "comfymodal-studio-backend-group-section" });

    var summary = el("button", {
      class: "comfymodal-studio-collapsible-summary",
      "aria-expanded": "true",
      "data-testid": "preset-group-" + testIdSuffix,
    }, [
      el("span", { class: "arrow", text: "\u25b6" }),
      el("span", { text: groupLabel + " (" + presetsArr.length + ")" }),
    ]);
    summary.addEventListener("click", function () {
      var expanded = summary.getAttribute("aria-expanded") === "true";
      summary.setAttribute("aria-expanded", String(!expanded));
      content.classList.toggle("is-visible");
    });

    var content = el("div", { class: "comfymodal-studio-collapsible-content is-visible" });
    presetsArr.forEach(function (preset) {
      content.appendChild(_renderPresetCard(preset, apiBase, container, detailPanel));
    });

    section.appendChild(summary);
    section.appendChild(content);
    return section;
  }

  // Render each named group
  groupNames.forEach(function (gName) {
    container.appendChild(_createGroupSection(
      gName,
      groups[gName],
      gName.replace(/[^a-zA-Z0-9_-]/g, "_")
    ));
  });

  // Render ungrouped section
  if (ungrouped.length > 0) {
    container.appendChild(_createGroupSection("Ungrouped", ungrouped, "ungrouped"));
  }
}

export function renderPresetDetail(container, preset, apiBase, listContainer) {
  while (container.firstChild) container.removeChild(container.firstChild);

  const card = el("div", { class: "comfymodal-studio-backend-detail-card" });
  const fieldValues = { ...preset };

  const canEdit = !preset.archived;

  // ── Status banner ────────────────────────────────────────────────────
  const isRunnable = preset.status === "runnable" && !preset.archived;
  const bannerClass = "comfymodal-studio-status-banner" +
    (isRunnable ? " runnable" : preset.archived ? " archived" : " not-runnable");
  const statusBanner = el("div", { class: bannerClass });
  statusBanner.textContent = isRunnable ? "\u2713 Runnable" : preset.archived ? "\u26a0 Archived" : "\u26a0 Not Runnable";
  card.appendChild(statusBanner);

  // Disabled reason (read-only, server-derived)
  if (preset.disabledReason && !preset.archived) {
    card.appendChild(el("p", {
      text: `Reason: ${preset.disabledReason}`,
      style: "font-size:10px;color:#f87171;margin:2px 0 6px;",
    }));
  }

  // ── Runnable Checklist ───────────────────────────────────────────────
  const checklistGroup = el("ul", { class: "comfymodal-studio-checklist" });
  checklistGroup.appendChild(el("p", {
    text: "Runnable Checklist",
    style: "font-size:10px;font-weight:600;color:#888;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.05em;",
  }));
  const hasSnapshot = !!(preset.snapshotId);
  const hasCompatFeatures = (preset.compatibleFeatures || []).length > 0;
  const hasApiPrompt = !!(preset.apiPromptJson || preset.graphJson);
  const checklistItems = [
    { label: "Snapshot linked", ok: hasSnapshot },
    { label: "Compatible features assigned", ok: hasCompatFeatures },
    { label: "API prompt available", ok: hasApiPrompt },
  ];
  checklistItems.forEach(function (item) {
    checklistGroup.appendChild(el("li", { class: "comfymodal-studio-checklist-item" }, [
      el("span", { text: item.ok ? "\u2713" : "\u2717", style: "font-size:10px;color:" + (item.ok ? "var(--color-success, #4ade80)" : "var(--color-danger, #ef4444)") + ";" }),
      el("span", { text: item.label, style: "font-size:10px;color:#aaa;" }),
    ]));
  });
  card.appendChild(checklistGroup);

  // ── Capability Summary ──────────────────────────────────────────────
  (preset.compatibleFeatures || []).forEach((fid) => {
    const summary = getPresetCapabilitySummary(preset, fid);
    const summaryGroup = el("div", {
      style: "margin-bottom:6px;padding:6px;background:#0a0a0a;border:1px solid #2a2a2a;border-radius:3px;",
    });
    summaryGroup.appendChild(el("p", {
      text: `${fid} Capability`,
      style: "font-size:10px;font-weight:600;color:#888;margin:0 0 4px;text-transform:uppercase;letter-spacing:0.05em;",
    }));

    // Feature status
    const featStatus = summary.runnable ? "\u2713 Runnable" : `\u26a0 ${summary.disabledReason || "Not runnable"}`;
    summaryGroup.appendChild(el("p", {
      text: `Status: ${featStatus}`,
      style: `font-size:10px;color:${summary.runnable ? "var(--color-success, #4ade80)" : "var(--color-warning, #fbbf24)"};margin:0 0 4px;`,
    }));

    // API graph status
    summaryGroup.appendChild(el("p", {
      text: `API graph: ${summary.hasApiGraph ? "\u2713 available" : "\u2717 missing"}`,
      style: `font-size:10px;color:${summary.hasApiGraph ? "var(--color-success, #4ade80)" : "var(--color-danger, #f87171)"};margin:0 0 2px;`,
    }));

    // Output mapping status
    summaryGroup.appendChild(el("p", {
      text: `Output mapping: ${summary.hasOutputBinding ? "\u2713 mapped" : "\u2717 missing"}`,
      style: `font-size:10px;color:${summary.hasOutputBinding ? "var(--color-success, #4ade80)" : "var(--color-danger, #f87171)"};margin:0 0 4px;`,
    }));

    // Required binding checklist
    summaryGroup.appendChild(el("p", {
      text: `Required bindings: ${summary.totalBoundRequired}/${summary.totalRequired} configured`,
      style: `font-size:10px;color:${summary.allRequiredMet ? "var(--color-success, #4ade80)" : "var(--color-danger, #f87171)"};margin:0 0 2px;`,
    }));

    summary.requiredBindings.forEach((d) => {
      const item = el("div", { style: "display:flex;align-items:center;gap:4px;margin:2px 0;" }, [
        el("span", { text: d.bound ? "\u2713" : "\u2717", style: `font-size:10px;color:${d.bound ? "var(--color-success, #4ade80)" : "var(--color-danger, #f87171)"};` }),
        el("span", { text: d.label, style: "font-size:10px;color:#aaa;" }),
      ]);
      summaryGroup.appendChild(item);
    });

    // Optional exposed controls
    if (summary.totalBoundOptional > 0) {
      summaryGroup.appendChild(el("p", {
        text: `Exposed controls: ${summary.totalBoundOptional} optional`,
        style: "font-size:10px;color:#888;margin:4px 0 2px;",
      }));
      summary.optionalBindings.filter((d) => d.bound).forEach((d) => {
        summaryGroup.appendChild(el("p", {
          text: `  \u2713 ${d.label}`,
          style: "font-size:9px;color:var(--color-success, #4ade80);margin:1px 0;",
        }));
      });
    }

    // Missing optional controls hint
    const missingOpt = summary.optionalBindings.filter((d) => !d.bound);
    if (missingOpt.length > 0) {
      summaryGroup.appendChild(el("p", {
        text: `Missing optional: ${missingOpt.length} (hidden in Playground)`,
        style: "font-size:9px;color:#666;margin:4px 0 0;font-style:italic;",
      }));
    }

    card.appendChild(summaryGroup);
  });

  // ── Fields ──────────────────────────────────────────────────────────
  const fields = [
    { key: "label", label: "Label", type: "text", value: preset.label || preset.name || "" },
    { key: "description", label: "Description", type: "textarea", value: preset.description || "" },
    { key: "group", label: "Group", type: "text", value: preset.group || "" },
    { key: "snapshotId", label: "Snapshot ID", type: "text", value: preset.snapshotId || "" },
    { key: "sourceType", label: "Source Type", type: "text", value: preset.sourceType || "" },
    { key: "sourceId", label: "Source ID", type: "text", value: preset.sourceId || "" },
  ];

  fields.forEach((f) => {
    const fg = el("div", { class: "comfymodal-studio-backend-field" });
    fg.appendChild(el("label", { text: f.label }));
    let input;
    if (f.type === "textarea") {
      input = el("textarea", { value: f.value, rows: 2, disabled: !canEdit });
    } else {
      input = el("input", { type: "text", value: f.value, disabled: !canEdit });
    }
    input.addEventListener("input", () => { fieldValues[f.key] = input.value; });
    fg.appendChild(input);
    card.appendChild(fg);
  });

  // ── Compatible Features chip grid ──────────────────────────────────
  const compatGroup = el("div", { class: "comfymodal-studio-backend-field" });
  compatGroup.appendChild(el("label", { text: "Compatible Features" }));
  const chipGrid = renderFeaturesChipGrid(preset.compatibleFeatures || [], (updated) => {
    fieldValues.compatibleFeatures = updated;
  });
  compatGroup.appendChild(chipGrid);
  card.appendChild(compatGroup);

  // ── Defaults ────────────────────────────────────────────────────────
  const defaults = preset.defaults || {};
  if (Object.keys(defaults).length > 0) {
    const defaultsGroup = el("div", { class: "comfymodal-studio-backend-field" });
    defaultsGroup.appendChild(el("label", { text: "Defaults" }));
    defaultsGroup.appendChild(el("p", { text: JSON.stringify(defaults, null, 2), style: "font-size:10px;color:#555;white-space:pre-wrap;" }));
    card.appendChild(defaultsGroup);
  }

  // ── Archived notice ────────────────────────────────────────────────
  if (preset.archived) {
    card.appendChild(el("p", { text: "\u26a0 Archived", style: "font-size:11px;color:#f87171;margin:4px 0;" }));
  }

  // ── Actions ────────────────────────────────────────────────────────
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  if (canEdit) {
    const saveBtn = el("button", {
      class: "comfymodal-primary-btn",
      text: "Save",
      style: "width:auto;padding:5px 16px;",
      onclick: async () => {
        await updatePreset(apiBase, preset.id, fieldValues);
        invalidateRuntimePresetsCache();
        const fresh = await listPresets(apiBase);
        renderPresetsList(listContainer, fresh, apiBase, container);
      },
    });
    actions.appendChild(saveBtn);

    // Edit Bindings button — opens wizard in edit mode
    const editBindingsBtn = el("button", {
      class: "comfymodal-secondary-btn",
      text: "Edit Bindings",
      style: "font-size:10px;padding:5px 12px;",
      onclick: async () => {
        // Load the snapshot to pass to the wizard
        const { listSnapshots } = await import("./studio-backend-api.js");
        const snapshots = await listSnapshots(apiBase);
        const snapshot = (snapshots || []).find((s) => s.id === preset.snapshotId) || null;
        launchPresetWizardForEdit(preset, snapshot, apiBase);
      },
    });
    actions.appendChild(editBindingsBtn);
  }

  const dupBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Duplicate",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      await duplicatePreset(apiBase, preset.id);
      invalidateRuntimePresetsCache();
      const fresh = await listPresets(apiBase);
      renderPresetsList(listContainer, fresh, apiBase, container);
    },
  });
  actions.appendChild(dupBtn);

  if (canEdit) {
    const deleteBtn = el("button", {
      class: "comfymodal-destructive-btn",
      text: "Delete preset",
      style: "font-size:10px;padding:5px 12px;",
      onclick: async () => {
        if (confirm("Delete this preset? (soft-delete — it can be restored via the server)")) {
          await deletePreset(apiBase, preset.id);
          clearSelection();
          invalidateRuntimePresetsCache();
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
    actions.appendChild(deleteBtn);
  }

  card.appendChild(actions);
  container.appendChild(card);
}

export function renderPresetForm(existing, apiBase, listPanel, detailPanel) {
  while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
  const formCard = el("div", { class: "comfymodal-studio-backend-detail-card" });

  // Advanced banner
  const advBanner = el("div", {
    style: "padding:6px 10px;border-radius:3px;margin-bottom:8px;background:#1a1a0a;border:1px solid #888;color:#d0d0d0;font-size:10px;",
  }, [
    el("p", {
      text: "\u26a0 Advanced: Use \u201cMake Preset\u201d for the primary preset creation flow.",
      style: "margin:0 0 2px;font-weight:600;",
    }),
    el("p", {
      text: "This form creates a raw preset without bindings. You can edit bindings after creation.",
      style: "margin:0;font-size:9px;color:#888;",
    }),
  ]);
  formCard.appendChild(advBanner);

  const heading = el("h4", {
    text: "New Backend Preset (Manual)",
    style: "margin:0 0 12px;font-size:12px;color:#d0d0d0;text-transform:uppercase;letter-spacing:0.05em;",
  });
  formCard.appendChild(heading);

  const fieldValues = { label: "", description: "", group: "", snapshotId: "", compatibleFeatures: [] };
  const fields = [
    { key: "label", label: "Label", type: "text" },
    { key: "description", label: "Description", type: "textarea" },
    { key: "group", label: "Group", type: "text" },
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
        invalidateRuntimePresetsCache();
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
