// Modal Studio — Backend Presets Page
//
// Preset list/detail/form rendering and CRUD wiring.
//
// abs-2 (legacy absorption): this page is backed by the WORKFLOWS domain
// only — presets are aggregated per workflow version through
// listWorkflows / listWorkflowVersions / listVersionPresets, and every
// mutation goes through the workflow preset routes (updateWorkflowPreset,
// duplicateWorkflowPreset, deleteWorkflowPreset, and the abs-1 verified
// from-legacy route for legacy-shaped creates). The unscoped legacy
// /studio/presets route is never called here: there is no second authority
// and no old-data migration. Legacy snapshotId linking is retired —
// presets are version-scoped (see the workflows domain); binding edits live
// in the Workflows tab mapping editor, the single bindings authority.
// The page itself is kept (deletion with caller proof belongs to abs-3).

import { el } from "./studio-ui.js";
import { renderLoadingState } from "./studio-loading.js";
import {
  listWorkflows,
  listWorkflowVersions,
  listVersionPresets,
  getWorkflowPreset,
  updateWorkflowPreset,
  duplicateWorkflowPreset,
  deleteWorkflowPreset,
  createPresetFromLegacy,
} from "./studio-backend-api.js";
import { _STATE, invalidateRuntimePresetsCache } from "./studio-backend.js";
import { clearSelection } from "./studio-playground-state.js";

// ── Workflow-backed preset loading ───────────────────────────────────────
//
// A flattened item carries the workflow preset plus the scope it was
// resolved from so every management action can hit the version-scoped
// workflow routes.

async function loadWorkflowPresets(apiBase) {
  const items = [];
  const wfResp = await listWorkflows(apiBase, {});
  const workflows = (wfResp && wfResp.workflows) || [];
  for (const wf of workflows) {
    const wfId = (wf && wf.workflow_id) || "";
    if (!wfId) continue;
    const verResp = await listWorkflowVersions(apiBase, wfId);
    const versions = (verResp && verResp.versions) || [];
    for (const v of versions) {
      const vid = (v && v.workflow_version_id) || "";
      if (!vid) continue;
      const presResp = await listVersionPresets(apiBase, vid);
      const presets = (presResp && presResp.presets) || [];
      presets.forEach((p) => {
        items.push({
          preset: p,
          workflowId: wfId,
          workflowName: (wf && wf.name) || "",
          versionId: vid,
          versionNumber: (v && v.version_number) != null ? v.version_number : null,
        });
      });
    }
  }
  return items;
}

function _presetIdOf(item) {
  return (item && item.preset && item.preset.preset_id) || "";
}

function _presetLabelOf(item) {
  const p = (item && item.preset) || {};
  return p.name || p.preset_id || "Unnamed";
}

function _stateOf(preset) {
  const st = (preset && preset.state) || {};
  return {
    status: st.status || "unknown",
    reasons: Array.isArray(st.reasons) ? st.reasons : [],
    runnable: !!st.runnable,
  };
}

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
      title: "Advanced: manual creation on a workflow version",
      onclick: () => renderPresetForm(null, apiBase, listPanel, detailPanel),
    }),
  ]);
  listPanel.appendChild(header);

  const countLine = el("p", {
    "data-testid": "backend-presets-count",
    style: "font-size:10px;color:#555;margin:0 0 8px;",
    text: "",
  });
  listPanel.appendChild(countLine);

  const listContent = el("div", { style: "flex:1;overflow-y:auto;" });
  listPanel.appendChild(listContent);

  // Presets live on workflow versions; binding edits happen in the
  // Workflows tab mapping editor.
  const domainNote = el("div", { style: "margin-bottom:8px;" }, [
    el("p", { text: "Presets are stored on workflow versions. Edit bindings in the Workflows tab.", style: "font-size:10px;color:#555;" }),
  ]);
  listPanel.appendChild(domainNote);

  listContent.appendChild(renderLoadingState({
    label: "Loading presets\u2026",
    size: "page",
    testid: "backend-presets-loading",
  }));
  loadWorkflowPresets(apiBase).then((items) => {
    while (listContent.firstChild) listContent.removeChild(listContent.firstChild);
    // null or undefined means network/API error (not just empty)
    if (items === null || items === undefined) {
      listContent.appendChild(el("div", { class: "comfymodal-studio-card" }, [
        el("p", { text: "Could not load presets from server.", style: "font-weight:600;margin:0 0 4px;color:#f87171;" }),
        el("p", { text: "Check that the backend server is running and the API is accessible.", style: "font-size:11px;color:#888;margin:0;" }),
      ]));
      return;
    }
    countLine.textContent = items.length === 1
      ? "1 preset"
      : `${items.length} presets`;
    if (items.length === 0) {
      listContent.appendChild(renderPresetsEmpty(apiBase));
      return;
    }
    renderPresetsList(listContent, items, apiBase, detailPanel);
    if (items.length > 0 && !_STATE.selectedItemId) {
      _STATE.selectedItemId = _presetIdOf(items[0]);
      renderPresetDetail(detailPanel, items[0], apiBase, listContent);
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
    el("p", { text: "No workflow presets configured.", style: "font-weight:600;margin:0 0 8px;color:#888;" }),
    el("p", { text: "Create presets in the Workflows tab version view.", style: "font-size:12px;color:#555;margin:0 0 4px;" }),
    el("p", { text: 'Or click "+ New Preset" for manual creation on a mapped version (advanced).', style: "font-size:11px;color:#666;margin:0;font-style:italic;" }),
  ]);
}

function _refreshPresetsList(listContainer, detailPanel, apiBase) {
  return loadWorkflowPresets(apiBase).then((fresh) => {
    while (listContainer.firstChild) listContainer.removeChild(listContainer.firstChild);
    renderPresetsList(listContainer, fresh, apiBase, detailPanel);
    const scope = (listContainer && listContainer.parentNode) || null;
    const countEl = scope && scope.querySelector
      ? scope.querySelector('[data-testid="backend-presets-count"]')
      : null;
    if (countEl) {
      countEl.textContent = fresh.length === 1 ? "1 preset" : `${fresh.length} presets`;
    }
    return fresh;
  });
}

/**
 * Render a single preset card (shared by grouped and ungrouped sections).
 */
function _renderPresetCard(item, apiBase, listContainer, detailPanel) {
  const preset = (item && item.preset) || {};
  const id = preset.preset_id || "unknown";
  const isActive = _STATE.selectedItemId === id;
  const label = _presetLabelOf(item);
  const desc = preset.description || "";
  const state = _stateOf(preset);
  const scope = `Workflow: ${(item && item.workflowName) || (item && item.workflowId) || ""}`
    + ((item && item.versionNumber != null) ? ` \u00b7 v${item.versionNumber}` : "");

  const card = el("div", {
    class: "comfymodal-studio-preset-card" + (isActive ? " active" : ""),
    onclick: function () {
      _STATE.selectedItemId = id;
      var allCards = listContainer.querySelectorAll(".comfymodal-studio-preset-card");
      allCards.forEach(function (c) { c.classList.remove("active"); });
      card.classList.add("active");
      while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
      renderPresetDetail(detailPanel, item, apiBase, listContainer);
    },
    "data-testid": "preset-card-" + id.replace(/[^a-zA-Z0-9_-]/g, "_"),
  }, [
    el("h4", { text: label.substring(0, 60) }),
    el("p", { text: (desc || "No description").substring(0, 80) }),
    el("p", { text: scope.substring(0, 80), style: "color:#666;font-size:9px;margin:2px 0;font-style:italic;" }),
  ]);
  if (!state.runnable) {
    card.appendChild(el("p", { text: "Not runnable" + (state.reasons.length ? `: ${state.reasons[0]}` : ""), style: "color:#fbbf24;font-size:10px;margin:2px 0;" }));
  }
  var rowActions = el("div", { style: "display:flex;gap:4px;margin-top:4px;" });
  var delRowBtn = el("button", {
    class: "comfymodal-destructive-btn",
    text: "Delete preset",
    style: "font-size:9px;padding:2px 6px;",
    onclick: function (e) {
      e.stopPropagation();
      if (confirm("Delete this preset? (soft-delete \u2014 it can be restored via the server)")) {
        deleteWorkflowPreset(apiBase, preset.preset_id).then(function () {
          clearSelection();
          invalidateRuntimePresetsCache();
          _STATE.selectedItemId = null;
          _refreshPresetsList(listContainer, detailPanel, apiBase).then(function (fresh) {
            if (fresh.length > 0) {
              _STATE.selectedItemId = _presetIdOf(fresh[0]);
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
  return card;
}

export function renderPresetsList(container, items, apiBase, detailPanel) {
  while (container.firstChild) container.removeChild(container.firstChild);

  // Group presets by their workflow so versions stay distinguishable
  var groups = {};
  var ungrouped = [];
  (items || []).forEach(function (item) {
    var g = item && (item.workflowName || item.workflowId);
    if (g && typeof g === "string" && g.trim() !== "") {
      if (!groups[g]) groups[g] = [];
      groups[g].push(item);
    } else {
      ungrouped.push(item);
    }
  });

  var groupNames = Object.keys(groups).sort(function (a, b) { return a.localeCompare(b); });

  // Helper to create a collapsible group section
  function _createGroupSection(groupLabel, groupItems, testIdSuffix) {
    var section = el("div", { class: "comfymodal-studio-backend-group-section" });

    var summary = el("button", {
      class: "comfymodal-studio-collapsible-summary",
      "aria-expanded": "true",
      "data-testid": "preset-group-" + testIdSuffix,
    }, [
      el("span", { class: "arrow", text: "\u25b6" }),
      el("span", { text: groupLabel + " (" + groupItems.length + ")" }),
    ]);
    summary.addEventListener("click", function () {
      var expanded = summary.getAttribute("aria-expanded") === "true";
      summary.setAttribute("aria-expanded", String(!expanded));
      content.classList.toggle("is-visible");
    });

    var content = el("div", { class: "comfymodal-studio-collapsible-content is-visible" });
    groupItems.forEach(function (item) {
      content.appendChild(_renderPresetCard(item, apiBase, container, detailPanel));
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

export function renderPresetDetail(container, item, apiBase, listContainer) {
  while (container.firstChild) container.removeChild(container.firstChild);
  const preset = (item && item.preset) || {};
  const presetId = preset.preset_id || "";
  const state = _stateOf(preset);

  const card = el("div", { class: "comfymodal-studio-backend-detail-card" });
  const fieldValues = { name: preset.name || "", description: preset.description || "" };

  // ── Status banner (workflow-domain truth) ────────────────────────────
  const isRunnable = state.status === "ready" && state.runnable;
  const bannerClass = "comfymodal-studio-status-banner" + (isRunnable ? " runnable" : " not-runnable");
  const statusBanner = el("div", { class: bannerClass });
  statusBanner.textContent = isRunnable ? "\u2713 Runnable" : "\u26a0 Not Runnable";
  card.appendChild(statusBanner);

  if (state.reasons.length > 0) {
    card.appendChild(el("p", {
      text: `Reason: ${state.reasons[0]}`,
      style: "font-size:10px;color:#fbbf24;margin:2px 0 6px;",
    }));
  }

  // ── Workflow scope (read-only) ───────────────────────────────────────
  const scopeGroup = el("div", { class: "comfymodal-studio-backend-field" });
  scopeGroup.appendChild(el("label", { text: "Workflow Scope" }));
  scopeGroup.appendChild(el("p", {
    text: `${(item && item.workflowName) || (item && item.workflowId) || ""}`
      + ((item && item.versionNumber != null) ? ` \u00b7 v${item.versionNumber}` : ""),
    style: "font-size:10px;color:#888;margin:0;",
  }));
  scopeGroup.appendChild(el("p", {
    text: `Preset ID: ${presetId}`,
    style: "font-size:9px;color:#666;margin:2px 0 0;",
  }));
  card.appendChild(scopeGroup);

  // ── Fields (workflow preset contract: name + description editable) ───
  const fields = [
    { key: "name", label: "Name", type: "text", value: preset.name || "" },
    { key: "description", label: "Description", type: "textarea", value: preset.description || "" },
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

  // ── Values (canonical workflow keys, read-only here) ─────────────────
  const values = preset.values || {};
  if (Object.keys(values).length > 0) {
    const valuesGroup = el("div", { class: "comfymodal-studio-backend-field" });
    valuesGroup.appendChild(el("label", { text: "Values" }));
    valuesGroup.appendChild(el("p", { text: JSON.stringify(values, null, 2), style: "font-size:10px;color:#555;white-space:pre-wrap;" }));
    card.appendChild(valuesGroup);
  }

  // ── Actions (all through the workflow preset routes) ─────────────────
  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const saveBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Save",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      await updateWorkflowPreset(apiBase, presetId, fieldValues);
      invalidateRuntimePresetsCache();
      const fresh = await _refreshPresetsList(listContainer, container, apiBase);
      void fresh;
    },
  });
  actions.appendChild(saveBtn);

  const dupBtn = el("button", {
    class: "comfymodal-secondary-btn",
    text: "Duplicate",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      await duplicateWorkflowPreset(apiBase, presetId);
      invalidateRuntimePresetsCache();
      await _refreshPresetsList(listContainer, container, apiBase);
    },
  });
  actions.appendChild(dupBtn);

  const deleteBtn = el("button", {
    class: "comfymodal-destructive-btn",
    text: "Delete preset",
    style: "font-size:10px;padding:5px 12px;",
    onclick: async () => {
      if (confirm("Delete this preset? (soft-delete \u2014 it can be restored via the server)")) {
        await deleteWorkflowPreset(apiBase, presetId);
        clearSelection();
        invalidateRuntimePresetsCache();
        _STATE.selectedItemId = null;
        const fresh = await _refreshPresetsList(listContainer, container, apiBase);
        while (container.firstChild) container.removeChild(container.firstChild);
        if (fresh.length > 0) {
          _STATE.selectedItemId = _presetIdOf(fresh[0]);
          renderPresetDetail(container, fresh[0], apiBase, listContainer);
        }
      }
    },
  });
  actions.appendChild(deleteBtn);

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
      text: "\u26a0 Advanced: prefer creating presets in the Workflows tab version view.",
      style: "margin:0 0 2px;font-weight:600;",
    }),
    el("p", {
      text: "This form creates a preset on a mapped workflow version through the legacy-absorption route.",
      style: "margin:0;font-size:9px;color:#888;",
    }),
  ]);
  formCard.appendChild(advBanner);

  const heading = el("h4", {
    text: "New Backend Preset (Manual)",
    style: "margin:0 0 12px;font-size:12px;color:#d0d0d0;text-transform:uppercase;letter-spacing:0.05em;",
  });
  formCard.appendChild(heading);

  const fieldValues = { name: "", description: "" };
  const statusEl = el("p", { style: "font-size:10px;color:#f87171;margin:0 0 8px;display:none;" });
  formCard.appendChild(statusEl);

  // Legacy/admin surface: presets remain version-scoped for compatibility,
  // so this form may target an immutable revision explicitly. The Shelf does
  // not expose this chooser.
  const workflowSelect = el("select", { class: "comfymodal-studio-select", "aria-label": "Workflow" });
  const versionSelect = el("select", { class: "comfymodal-studio-select", "aria-label": "Version" });
  const scopeGroup = el("div", { class: "comfymodal-studio-backend-field" });
  scopeGroup.appendChild(el("label", { text: "Workflow" }));
  scopeGroup.appendChild(workflowSelect);
  formCard.appendChild(scopeGroup);
  const versionGroup = el("div", { class: "comfymodal-studio-backend-field" });
  versionGroup.appendChild(el("label", { text: "Version" }));
  versionGroup.appendChild(versionSelect);
  formCard.appendChild(versionGroup);

  async function _loadWorkflowsIntoSelect() {
    while (workflowSelect.firstChild) workflowSelect.removeChild(workflowSelect.firstChild);
    const wfResp = await listWorkflows(apiBase, {});
    const workflows = (wfResp && wfResp.workflows) || [];
    workflows.forEach((w) => {
      const opt = el("option", { value: w.workflow_id || "", text: w.name || w.workflow_id || "" });
      workflowSelect.appendChild(opt);
    });
    await _loadVersionsIntoSelect();
  }

  async function _loadVersionsIntoSelect() {
    while (versionSelect.firstChild) versionSelect.removeChild(versionSelect.firstChild);
    const wfId = workflowSelect.value || "";
    if (!wfId) return;
    const verResp = await listWorkflowVersions(apiBase, wfId);
    const versions = (verResp && verResp.versions) || [];
    versions.forEach((v) => {
      const label = v.version_number != null ? `v${v.version_number}` : (v.workflow_version_id || "");
      const opt = el("option", { value: v.workflow_version_id || "", text: label });
      versionSelect.appendChild(opt);
    });
  }

  workflowSelect.addEventListener("change", () => { _loadVersionsIntoSelect(); });
  _loadWorkflowsIntoSelect();

  const fields = [
    { key: "name", label: "Name", type: "text" },
    { key: "description", label: "Description", type: "textarea" },
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

  const actions = el("div", { class: "comfymodal-studio-backend-actions" });

  const createBtn = el("button", {
    class: "comfymodal-primary-btn",
    text: "Create",
    style: "width:auto;padding:5px 16px;",
    onclick: async () => {
      statusEl.style.display = "none";
      const versionId = versionSelect.value || "";
      const name = (fieldValues.name || "").trim();
      if (!versionId || !name) {
        statusEl.textContent = "Choose a workflow version and enter a preset name.";
        statusEl.style.display = "block";
        return;
      }
      // Legacy-shaped entry payload → the abs-1 verified from-legacy
      // route translates keys (LEGACY_ROLE_MAP) and persists through
      // create_preset_from_legacy → create_preset under the version scope.
      const result = await createPresetFromLegacy(apiBase, versionId, {
        name,
        description: fieldValues.description || "",
      });
      if (!result || result.status === "error" || !result.preset) {
        statusEl.textContent = (result && (result.message || result.error)) || "Server rejected preset creation";
        statusEl.style.display = "block";
        return;
      }
      invalidateRuntimePresetsCache();
      _STATE.selectedItemId = null;
      // Re-render the presets page
      while (listPanel.firstChild) listPanel.removeChild(listPanel.firstChild);
      while (detailPanel.firstChild) detailPanel.removeChild(detailPanel.firstChild);
      renderPresetsPage(listPanel, detailPanel, apiBase);
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
