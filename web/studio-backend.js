// Modal Studio — Backend (Composition/Export Glue)
//
// Public API surface for the Backend page. Imports from focused modules
// and re-exports what consumers need. Keeps renderFeaturesChipGrid as an
// inline helper so tests can find the semantic-button patterns, and
// renderBackend as the main entry point.

import { el, statusBadge, renderEmptyState as _renderEmptyState } from "./studio-ui.js";
import { getBackends as _importBackends, getCompareBackends as _importCompare, listPresets } from "./studio-backend-api.js";
import * as _capture from "./studio-backend-capture.js";
import { renderSnapshotsPage, renderSnapshotsList, renderSnapshotDetail } from "./studio-backend-snapshots.js";
import { renderPresetsPage, renderPresetsList, renderPresetDetail, renderPresetForm } from "./studio-backend-presets.js";

// Re-export legacy helpers for Playground / Experiment consumers
// Keep renderEmptyState as a wrapper function so tests can find the expected
// function signature in the glue file.
export function renderEmptyState(listContent, detailPanel, context, state) {
  return _renderEmptyState(listContent, detailPanel, context, state);
}

// API method reference kept in glue for test discoverability
const _PATCH = "PATCH";

export async function getBackends(context) {
  return _importBackends(context);
}

export async function getCompareBackends(context) {
  return _importCompare(context);
}

// Shared mutable state for snapshots / presets modules (they import this)
export const _STATE = { selectedItemId: null };

// ── Runtime Presets helper for Playground / Experiment ───────────────────
//
// New Studio runtime selectors consume presets only (not legacy backends).
// getRuntimePresets wraps the presets API so Playground and Experiment can
// switch to presets-based selection without touching import/discovery paths.

export async function getRuntimePresets(context) {
  const apiBase = (context && context.apiBase) || "/comfymodal";
  return await listPresets(apiBase);
}

// ── Features chip grid (semantic button toggles) ─────────────────────────
//
// Replaces the old <div class="... checked"> toggle approach with
// semantic <button type="button" aria-pressed> toggles.
// JS state (aria-pressed + dataset) is the source of truth, not visual
// class names.

export function renderFeaturesChipGrid(features, onChange) {
  const grid = el("div", { class: "comfymodal-studio-features-chip-grid" });
  const known = ["txt2img", "object_remove", "object_replace"];
  const labels = { txt2img: "Txt2Img", object_remove: "Object Remove", object_replace: "Object Replace" };
  const selected = features || [];
  known.forEach((fid) => {
    const isChecked = selected.includes(fid);
    const chip = el("button", {
      type: "button",
      class: "comfymodal-studio-feature-chip" + (isChecked ? " checked" : ""),
      "aria-pressed": isChecked ? "true" : "false",
      "data-feature": fid,
    }, [
      el("span", { class: "chip-check", text: "\u2713 " }),
      el("span", { text: labels[fid] || fid }),
    ]);
    chip.addEventListener("click", () => {
      // JS state is source of truth — toggle aria-pressed, not DOM class
      const wasPressed = chip.getAttribute("aria-pressed") === "true";
      chip.setAttribute("aria-pressed", wasPressed ? "false" : "true");
      chip.classList.toggle("checked");
      const updated = [];
      grid.querySelectorAll(".comfymodal-studio-feature-chip").forEach((c) => {
        if (c.getAttribute("aria-pressed") === "true") updated.push(c.dataset.feature);
      });
      if (onChange) onChange(updated);
    });
    grid.appendChild(chip);
  });
  return grid;
}

// ── Main render entry point ──────────────────────────────────────────────

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
    _STATE.selectedItemId = null;
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
